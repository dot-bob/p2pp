__author__ = 'Tom Van den Eede'
__copyright__ = 'Copyright 2018, Palette2 Splicer Post Processing Project'
__credits__ = ['Tom Van den Eede',
               'Tim Brookman'
               ]
__license__ = 'GPL'
__version__ = '1.0.0'
__maintainer__ = 'Tom Van den Eede'
__email__ = 'P2PP@pandora.be'
__status__ = 'Beta'

import os

from p2pp.formatnumbers import hexify_short, hexify_long, hexify_float


#########################################
# Variable default values
#########################################

# Filament Transition Table
paletteInputsUsed = [False, False, False, False]
filamentType = ["", "", "", ""]
filemantDescription = ["Unnamed", "Unnamed", "Unnamed", "Unnamed"]
filamentColorCode = ["-", "-", "-", "-"]
defaultSpliceAlgorithm = "D000 D000 D000"
processWarnings = []
spliceAlgorithmTable = []
spliceAlgorithmDictionary = {}


printerProfileString = ''  # A unique ID linked to a printer configuration profile in the Palette 2 hardware.

processedGCode = []  # final output array with Gcode

# spliceoffset allows for a correction of the position at which the transition occurs.   When the first transition is scheduled
# to occur at 120mm in GCode, you can add a number of mm to push the transition further in the purge tower.  This serves a similar
# function as the transition offset in chroma
spliceOffset = 0.0

# these  variables are used to build the splice information table (Omega-30 commands in GCode) that will drive the Palette2
spliceExtruderPosition = []
spliceUsedTool = []
spliceLength = []


# ping text is a text variable to store information about the PINGS generated by P2PP.   this information is pasted after
# the splice information right after the Palette2 header
pingExtruderPosition = []


# Hotswapcount is the number of hotswaps generated during the print.... not sure what this is used for, this variable is
# only used to complete the header
hotSwapCount = 0

# TotalExtrusion keeps track of the total extrusion in mm for the print taking into account the Extruder Multiplier set
# in the GCode settings.
totalMaterialExtruded = 0

# The next 3 variables are used to generate pings.   A ping is scheduled every ping interval.  The LastPing option
# keeps the last extruder position where a ping was generated.  It is set to -100 to pring the first PING forward...
# Not sure this is a good idea.   Ping distance increases over the print in an exponential way.   Each ping is 1.03 times
# further from the previous one.   Pings occur in random places!!! as the are non-intrusive and don't causes pauses in the
# print they aren ot restricted to the wipe tower and they will occur as soon as the interval length for ping is exceeded.
lastPingExtruderPosition = 0
pingIntervalLength = 350
maxPingIntervalLength = 3000
pingLengthMultiplier = 1.03


# currenttool/lastLocation are variables required to generate O30 splice info.   splice info is generated at the end of the tool path
# and not at the start hence the requirement to keep the toolhead and lastlocation to perform the magic
currentTool = -1
previousToolChangeLocation = 0

currentLayer = "No Layer Info"  # Capture layer information for short splice texts
extrusionMultiplier = 0.95  # Monitors M221 commands during the print.  Default is 0.95 (default in MK3 Firmware)
currentprintFeedrate = 100  # Monitors the current feedrate
currentprintFeed = 2000
extraRunoutFilament = 150  # Provide extra filament at the end of the print.
minimalSpliceLength = 80  # Minimum overall splice length.
minimalStartSpliceLength = 100  # Minimum first splice length.
withinToolchangeBlock = False  # keeps track if the processed G-Code is part of a toolchange or a regular path.
allowFilamentInformationUpdate = False  # TBA



#################################################################
########################## COMPOSE WARNING BLOCK ################
#################################################################


def log_warning(text):
    global processWarnings
    processWarnings.append(";"+text)


# ################################################################
# ######################### ALGORITHM PROCESSING ################
# ################################################################


def algorithm_createprocessstring(heating, compression, cooling):
    return "{} {} {}".format(hexify_short(int(heating)),
                             hexify_short(int(compression)),
                             hexify_short(int(cooling))
                             )


def algorithm_processmaterialconfiguration(splice_info):
    global defaultSpliceAlgorithm, spliceAlgorithmDictionary

    fields = splice_info.split("_")
    numfields = len(fields)

    if fields[0] == "DEFAULT" and numfields == 4:
        defaultSpliceAlgorithm = algorithm_createprocessstring(fields[1],
                                                               fields[2],
                                                               fields[3])

    if numfields == 5:
        key = "{}-{}".format(fields[0],
                             fields[1])
        spliceAlgorithmDictionary[key] = algorithm_createprocessstring(fields[2],
                                                                       fields[3],
                                                                       fields[4])


def algorithm_createtable():
    global spliceAlgorithmTable, processWarnings
    for i in range(4):
        for j in range(4):
            if  not paletteInputsUsed[i] or not paletteInputsUsed[j]:
                continue
            try:
                algo =  spliceAlgorithmDictionary["{}-{}".format(filamentType[i],
                                                                 filamentType[j])]
            except:
                log_warning("WARNING: No Algorithm defined for transitioning {} to {}.  Using Default.\n".format(filamentType[i],
                                                                                                               filamentType[j]))
                algo =  defaultSpliceAlgorithm

            spliceAlgorithmTable.append("D{}{} {}".format(i + 1,
                                                          j + 1,
                                                          algo
                                                          )
                                        )



# Generate the Omega - Header that drives the Palette to generate filament
def header_generateomegaheader(Name, splice_offset):

    if printerProfileString == '':
        log_warning("Printerprofile identifier is missing, add \n;P2PP PRINTERPROFILE=<your printer profile ID> to the Printer Start GCode block\n")
    if len(spliceExtruderPosition) == 0:
        log_warning("This does not look lie a multi color file......\n")

    algorithm_createtable()

    header = []
    summary = []
    warnings = []
    header.append('O21 ' + hexify_short(20) + "\n")  # MSF2.0
    header.append('O22 D' + printerProfileString + "\n")  # printerprofile used in Palette2
    header.append('O23 D0001' + "\n")              # unused
    header.append('O24 D0000' + "\n")              # unused

    header.append("O25 ")

    for i in range(4):
        if paletteInputsUsed[i]:
            if filamentType[i] == "":
                log_warning(
                    "Filament #{} is missing Material Type, make sure to add ;P2PP FT=[filament_type] to filament GCode".format(
                        i))
            if filemantDescription[i] == "Unnamed":
                log_warning(
                    "Filament #{} is missing Name, make sure to add ;P2PP FN=[filament_preset] to filament GCode".format(
                        i))
            if filemantDescription[i] == "-":
                log_warning(
                    "Filament #{} is missing Color info, make sure to add ;P2PP FC=[extruder_colour] to filament GCode".format(
                        i))
                filemantDescription[i] = '000000'

            header.append( "D{}{}{} ".format(i + 1,
                                        filamentColorCode[i],
                                        filemantDescription[i]
                                        ))
        else:
            header.append( "D0 " )

    header.append( "\n")

    header.append('O26 ' + hexify_short(len(spliceExtruderPosition)) + "\n")
    header.append('O27 ' + hexify_short(len(pingExtruderPosition)) + "\n")
    header.append('O28 ' + hexify_short(len(spliceAlgorithmTable)) + "\n")
    header.append('O29 ' + hexify_short(hotSwapCount) + "\n")

    for i in range(len(spliceExtruderPosition)):
        header.append("O30 D{:0>1d} {}\n".format(spliceUsedTool[i],
                                                 hexify_float(spliceExtruderPosition[i])
                                                 )
                      )

    for i in range(len(spliceAlgorithmTable)):
        header.append("O32 {}\n".format(spliceAlgorithmTable[i]))

    if len(spliceExtruderPosition) > 0:
        header.append("O1 D{} {}\n".format(Name, hexify_float(spliceExtruderPosition[-1])))
    else:
        header.append("O1 D{} {}\n".format(Name, hexify_float(totalMaterialExtruded + splice_offset)))

    header.append("M0\n")
    header.append("T0\n")

    summary.append(";------------------:\n")
    summary.append(";SPLICE INFORMATION:\n")
    summary.append(";------------------:\n")
    summary.append(";       Splice Offset = {:-8.2f}mm\n\n".format(splice_offset))

    for i in range(len(spliceExtruderPosition)):
        summary.append(";{:04}   Tool: {}  Location: {:-8.2f}mm   length {:-8.2f}mm \n".format(i + 1,
                                                                                        spliceUsedTool[i],
                                                                                        spliceExtruderPosition[i],
                                                                                        spliceLength[i],
                                                                                      )
                      )

    summary.append("\n")
    summary.append(";------------------:\n")
    summary.append(";PING  INFORMATION:\n")
    summary.append(";------------------:\n")

    for i in range(len(pingExtruderPosition)):
        summary.append(";Ping {:04} at {:-8.2f}mm\n".format(i + 1,
                                                           pingExtruderPosition[i]
                                                           )
                       )

    warnings.append("\n")
    warnings.append(";------------------:\n")
    warnings.append(";PROCESS WARNINGS:\n")
    warnings.append(";------------------:\n")

    if len(processWarnings) == 0:
        warnings.append(";None")
    else:
        for i in range(len(processWarnings)):
            warnings.append("{}\n".format(processWarnings[i]))

    return {'header': header, 'summary': summary, 'warnings': warnings}


#################### GCODE PROCESSING ###########################

def gcode_processtoolchange(newTool, Location, splice_offset):
    global currentTool, previousToolChangeLocation
    global paletteInputsUsed, currentLayer
    global spliceExtruderPosition, spliceUsedTool, spliceLength, spliceTime, totalSpliceTime

    # some commands are generated at the end to unload filament, they appear as a reload of current filament - messing up things
    if newTool == currentTool:
        return

    Location += splice_offset


    if newTool == -1:
        Location += extraRunoutFilament
    else:
        paletteInputsUsed[newTool] = True

    Length = Location - previousToolChangeLocation

    if currentTool != -1:
        spliceExtruderPosition.append(Location)
        spliceLength.append(Length)
        spliceUsedTool.append(currentTool)


        if len(spliceExtruderPosition)==1:
            if spliceLength[0] < minimalStartSpliceLength:
                log_warning(";Warning : Short first splice (<{}mm) Length:{}\n".format(Length, minimalStartSpliceLength))
        else:
            if spliceLength[-1] < minimalSpliceLength:
                log_warning(";Warning: Short splice (<{}mm) Length:{} Layer:{} Tool:{}\n".format(minimalSpliceLength, Length, currentLayer, currentTool))

    previousToolChangeLocation = Location
    currentTool = newTool

# Gcode remove speed information from a G1 statement
def gcode_removespeedinfo(gcode):
    result = ""
    parts = gcode.split(" ")

    for subcommand in parts:
        if subcommand == "":
            continue
        if subcommand[0] != "F":
            result += subcommand+" "

    if len(result) < 4:
        return ";P2PP Removed "+gcode

    return result+"\n"

def gcode_filtertoolchangeblock(line, gcode_command_2, gcode_command_4):
    # --------------------------------------------------------------
    # Do not perform this part of the GCode for MMU filament unload
    # --------------------------------------------------------------
    discarded_moves = ["E-15.0000",
                       "G1 E10.5000",
                       "G1 E3.0000",
                       "G1 E1.5000"
                       ]

    if gcode_command_2 == "G1":
        for gcode_filter in discarded_moves:
            if gcode_filter in line:         # remove specific MMU2 extruder moves
                return ";P2PP removed "+line
        return gcode_removespeedinfo(line)

    if gcode_command_4 == "M907":
        return ";P2PP removed " + line   # remove motor power instructions

    if gcode_command_4 == "M220":
        return ";P2PP removed " + line   # remove feedrate instructions

    if line.startswith("G4 S0"):
        return ";P2PP removed " + line   # remove dwelling instructions

    return line


def get_gcode_parameter(gcode, parameter):
    fields = gcode.split()
    for parm in fields:
        if parm[0] == parameter:
            return float(parm[1:])
    return ""


# G Code parsing routine
def gcode_parseline(splice_offset, gcodeFullLine):
    global totalMaterialExtruded,extrusionMultiplier, currentLayer, printerProfileString, currentprintFeedrate
    global lastPingExtruderPosition, pingLengthMultiplier, pingIntervalLength
    global withinToolchangeBlock, CurrentTool, withinToolchangeBlock, allowFilamentInformationUpdate
    global minimalStartSpliceLength, minimalSpliceLength, processedGCode, totalSpliceTime, currentprintFeed

    if not gcodeFullLine[0]==";":
        gcodeFullLine = gcodeFullLine.split(';')[0]

    gcodeFullLine = gcodeFullLine.rstrip('\n')

    if len(gcodeFullLine) < 2:
        return {'gcode': gcodeFullLine, 'splice_offset': splice_offset}


    gcodeCommand2 = gcodeFullLine[0:2]
    gcodeCommand4 = gcodeFullLine[0:4]


    # Processing of extrusion speed commands
    #############################################
    if gcodeCommand4 == "M220":
        newFeedrate = get_gcode_parameter(gcodeFullLine, "S")
        if (newFeedrate != ""):
            currentprintFeedrate = newFeedrate/100


    # Processing of extrusion multiplier commands
    #############################################
    if gcodeCommand4 == "M221":
        newMultiplier = get_gcode_parameter(gcodeFullLine , "S")
        if (newMultiplier != ""):
            extrusionMultiplier = newMultiplier/100

    # Processing of Extruder Movement commands
    # and generating ping at threshold intervals
    #############################################


    if gcodeCommand2 == "G1":


            extruderMovement = get_gcode_parameter(gcodeFullLine, "E")

            if extruderMovement != "":

                actualExtrusionLength =  extruderMovement * extrusionMultiplier
                totalMaterialExtruded += actualExtrusionLength

                if (totalMaterialExtruded - lastPingExtruderPosition) > pingIntervalLength:
                    pingIntervalLength = pingIntervalLength * pingLengthMultiplier

                    pingIntervalLength = min(maxPingIntervalLength, pingIntervalLength)

                    lastPingExtruderPosition = totalMaterialExtruded
                    pingExtruderPosition.append(lastPingExtruderPosition)
                    processedGCode.append(";Palette 2 - PING\n")
                    processedGCode.append("G4 S0\n")
                    processedGCode.append("O31 {}\n".format(hexify_float(lastPingExtruderPosition)))


    # Process Toolchanges. Build up the O30 table with Splice info
    ##############################################################
    if gcodeFullLine[0] == 'T':
        newTool = int(gcodeFullLine[1])
        gcode_processtoolchange(newTool, totalMaterialExtruded, splice_offset)
        allowFilamentInformationUpdate = True
        return {'gcode': ';P2PP removed ' + gcodeFullLine, 'splice_offset': splice_offset}

    # Build up the O32 table with Algo info
    #######################################
    if gcodeFullLine.startswith(";P2PP FT=") and allowFilamentInformationUpdate:  # filament type information
        filamentType[currentTool] = gcodeFullLine[9:]

    if gcodeFullLine.startswith(";P2PP FN=") and allowFilamentInformationUpdate:  # filament color information
        p2ppinfo = gcodeFullLine[9:].strip("\n-+!@#$%^&*(){}[];:\"\',.<>/?").replace(" ", "_")
        filemantDescription[currentTool] = p2ppinfo

    if gcodeFullLine.startswith(";P2PP FC=#") and allowFilamentInformationUpdate:  # filament color information
        p2ppinfo = gcodeFullLine[10:]
        filamentColorCode[currentTool] = p2ppinfo

    # Other configuration information
    # this information should be defined in your Slic3r printer settings, startup GCode
    ###################################################################################
    if gcodeFullLine.startswith(";P2PP PRINTERPROFILE=") and printerProfileString == '':   # -p takes precedence over printer defined in file
        printerProfileString = gcodeFullLine[21:]

    if gcodeFullLine.startswith(";P2PP SPLICEOFFSET="):
        splice_offset = float(gcodeFullLine[19:])

    if gcodeFullLine.startswith(";P2PP MINSTARTSPLICE="):
        minimalStartSpliceLength = float(gcodeFullLine[21:])
        if minimalStartSpliceLength < 100:
            minimalStartSpliceLength = 100

    if gcodeFullLine.startswith(";P2PP MINSPLICE="):
        minimalSpliceLength = float(gcodeFullLine[16:])
        if minimalSpliceLength < 40:
            minimalSpliceLength = 40

    if gcodeFullLine.startswith(";P2PP MATERIAL_"):
        algorithm_processmaterialconfiguration(gcodeFullLine[15:])

    # Next section(s) clean up the GCode generated for the MMU
    # specially the rather violent unload/reload required for the MMU2
    ###################################################################
    if "TOOLCHANGE START" in gcodeFullLine:
        allowFilamentInformationUpdate = False
        withinToolchangeBlock = True
    if "TOOLCHANGE END" in gcodeFullLine:
        withinToolchangeBlock = False
    if "TOOLCHANGE UNLOAD" in gcodeFullLine:
        processedGCode.append(";P2PP Set Wipe Speed\n")
        processedGCode.append("G1 F2000\n")
        currentprintFeed = 2000.0/60.0

    # Layer Information
    if gcodeFullLine.startswith(";LAYER "):
        currentLayer = gcodeFullLine[7:]
        return {'gcode': gcodeFullLine, 'splice_offset': splice_offset}

    if withinToolchangeBlock:
        return {'gcode': gcode_filtertoolchangeblock(gcodeFullLine, gcodeCommand2, gcodeCommand4), 'splice_offset': splice_offset}

    # Catch All
    return {'gcode': gcodeFullLine, 'splice_offset': splice_offset}




def generate(input_file, output_file, printer_profile, splice_offset, silent):

    global printerProfileString
    printerProfileString = printer_profile

    basename = os.path.basename(input_file)
    _taskName = os.path.splitext(basename)[0]

    with open(input_file) as opf:
        gcode_file = opf.readlines()


    # Process the file
    ##################
    for line in gcode_file:
        # gcode_parseline now returns splice_offset from print file if it exists, keeping everything consistent.
        # splice_offset from gcode takes precedence over splice_offset from CLI.
        result = gcode_parseline(splice_offset, line)
        splice_offset = float(result['splice_offset'])
        processedGCode.append(result['gcode']+"\n")
    gcode_processtoolchange(-1, totalMaterialExtruded, splice_offset)
    omega_result = header_generateomegaheader(_taskName, splice_offset)
    header = omega_result['header'] + omega_result['summary'] + omega_result['warnings']

    if not silent:
        print (''.join(omega_result['summary']))
        print (''.join(omega_result['warnings']))

    # write the output file
    ######################
    if not output_file:
        output_file = input_file

    opf = open(output_file, "w")
    opf.writelines(header)
    opf.writelines(processedGCode)
