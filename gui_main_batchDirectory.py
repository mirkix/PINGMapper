
import sys
sys.path.insert(0, 'src')
import os
import PySimpleGUI as sg
import matplotlib.pyplot as plt

from funcs_common import *
from main_readFiles import read_master_func
from main_rectify import rectify_master_func
from main_mapSubstrate import map_master_func
import json

# Get processing script's dir so we can save it to file
scriptDir = os.getcwd()

# For the logfile
oldOutput = sys.stdout

start_time = time.time()

#============================================

# Default Values
# Edit values below to change default values in gui
default_params_file = "./user_params.json"
if not os.path.exists(default_params_file):
    default_params_file = "./default_params.json"
with open(default_params_file) as f:
    default_params = json.load(f)


layout = [
    [sg.Text('Parent Folder of Recordings to Process')],
    [sg.In(size=(80,1)), sg.FolderBrowse(initial_folder=os.path.join(os.getcwd(), 'exampleData'))],
    [sg.Text('Output Folder')],
    [sg.In(size=(80,1)), sg.FolderBrowse(initial_folder=os.path.join(os.getcwd(), 'procData'))],
    # [sg.Text('Project Name', size=(15,1)), sg.InputText(size=(50,1))],
    [sg.Checkbox('Overwrite Existing Project', default=default_params['project_mode'])],
    [sg.HorizontalSeparator()],
    [sg.Text('General Parameters')],
    [sg.Text('Temperature [C]', size=(20,1)), sg.Input(default_params['tempC'], size=(10,1))],
    [sg.Text('Chunk Size', size=(20,1)), sg.Input(default_params['nchunk'], size=(10,1))],
    [sg.Text('Crop Range [m]', size=(20,1)), sg.Input(default_params['cropRange'], size=(10,1))],
    [sg.Checkbox('Export Unknown Ping Attributes', default=default_params['exportUnknown'])],
    [sg.Checkbox('Locate and flag missing pings', default=default_params['fixNoDat'])],
    [sg.Text('Thread Count [0==All Threads]', size=(30,1)), sg.Input(default_params['threadCnt'], size=(10,1))],
    [sg.HorizontalSeparator()],
    [sg.Text('Position Corrections')],
    [sg.Text('Transducer Offset [X]:', size=(22,1)), sg.Input(default_params['x_offset'], size=(10,1)), sg.VerticalSeparator(), sg.Text('Transducer Offset [Y]:', size=(22,1)), sg.Input(default_params['y_offset'], size=(10,1))],
    [sg.HorizontalSeparator()],
    [sg.Text('Sonar Intensity Corrections')],
    [sg.Checkbox('Empiracal Gain Normalization (EGN)', default=default_params['egn'])],
    [sg.Text('EGN Stretch', size=(10,1)), sg.Combo(['Min-Max', 'Percent Clip'], default_value=default_params['egn_stretch']), sg.VerticalSeparator(), sg.Text('EGN Stretch Factor', size=(20,1)), sg.Input(default_params['egn_stretch_factor'], size=(10,1))],
    [sg.HorizontalSeparator()],
    [sg.Text('Sonagram Tile Exports')],
    [sg.Checkbox('WCP', default=default_params['wcp']), sg.Checkbox('WCR', default=default_params['wcr']), sg.Text('Image Format:', size=(12,1)), sg.Combo(['.jpg', '.png'], default_value=default_params['tileFile'])],
    [sg.HorizontalSeparator()],
    [sg.Text('Speed Corrected Sonagram Exports')],
    [sg.Text('Export Sonograms', size=(20,1)), sg.Combo(['False', 'True: Keep WC & Shadows', 'True: Mask WC & Shadows'], default_value=default_params['lbl_set'])],
    [sg.Text('Speed Correction', size=(20,1)), sg.Input(default_params['spdCor'], size=(10,1)), sg.VerticalSeparator(), sg.Checkbox('Max Crop', default=default_params['maxCrop'])],
    [sg.HorizontalSeparator()],
    [sg.Text('Depth Detection and Shadow Removal')],
    [sg.Text('Shadow Removal', size=(20,1)), sg.Combo(['False', 'Remove all shadows', 'Remove only bank shadows'], default_value=default_params['remShadow'])],
    [sg.Text('Depth Detection', size=(20,1)), sg.Combo(['Sensor', 'Auto'], default_value=default_params['detectDep']), sg.VerticalSeparator(), sg.Checkbox('Smooth Depth', default=default_params['smthDep']), sg.VerticalSeparator(), sg.Text('Adjust Depth [m]'), sg.Input(default_params['adjDep'], size=(10,1)), sg.VerticalSeparator(()), sg.Checkbox('Plot Bedpick', default=default_params['pltBedPick'])],
    [sg.HorizontalSeparator()],
    [sg.Text('Sonar Georectification Exports')],
    [sg.Checkbox('WCP', default=default_params['rect_wcp']), sg.Checkbox('WCR', default=default_params['rect_wcr']), sg.Text('Sonar Colormap'), sg.Combo(plt.colormaps(), default_value=default_params['son_colorMap'])],
    [sg.HorizontalSeparator()],
    [sg.Text('Substrate Mapping')],
    [sg.Checkbox('Predict Substrate', default=default_params['pred_sub']), sg.VerticalSeparator(), sg.Checkbox('Export Substrate Plots', default=default_params['pltSubClass'])],
    [sg.Checkbox('Map Substrate [Raster]', default=default_params['map_sub']), sg.VerticalSeparator(), sg.Checkbox('Map Substrate [Polygon]', default=default_params['export_poly']), sg.VerticalSeparator(), sg.Text('Classification Method'), sg.Combo(['max'], default_value=default_params['map_class_method'])],
    [sg.HorizontalSeparator()],
    [sg.Text('Mosaic Exports')],
    [sg.Text('Pixel Size [m, 0==Default Size]'), sg.Input(default_params['pix_res'], size=(10,1)), sg.VerticalSeparator(), sg.Text('# Chunks per Mosaic [0==All Chunks]'), sg.Input(default_params['mosaic_nchunk'], size=(10,1))],
    [sg.Text('Export Sonar Mosaic'), sg.Combo(['False', 'GTiff', 'VRT'], default_value=default_params['mosaic']), sg.VerticalSeparator(), sg.Text('Export Substrate Mosaic'), sg.Combo(['False', 'GTiff', 'VRT'], default_value=default_params['map_mosaic'])],
    [sg.HorizontalSeparator()],
    [sg.Submit(), sg.Quit()]
]



window = sg.Window('Process Single Humminbird Sonar Recording', layout)
while True:
    event, values = window.read()
    if event == "Quit" or event == 'Submit':
        break
    if event == "Save Defaults":
        saveDefaultParams(values)

window.close()

if event == "Quit":
    sys.exit()

inDir = values[0]
outDir = values[1]

#################################
# Convert parameters if necessary

# EGN Stretch
egn_stretch = values[16]
if egn_stretch == 'Min-Max':
    egn_stretch = 0
elif egn_stretch == 'Percent Clip':
    egn_stretch = 1
egn_stretch = int(egn_stretch)

# Speed Corrected Sonograms
lbl_set = values[24]
if lbl_set == 'False':
    lbl_set = 0
elif lbl_set == 'True: Keep WC & Shadows':
    lbl_set = 1
elif lbl_set == 'True: Mask WC & Shadows':
    lbl_set = 2
lbl_set = int(lbl_set)

# Shadow removal
remShadow = values[29]
if remShadow == 'False':
    remShadow = 0
elif remShadow == 'Remove all shadows':
    remShadow = 1
elif remShadow == 'Remove only bank shadows':
    remShadow = 2
remShadow = int(remShadow)

# Depth detection
detectDep = values[30]
if detectDep == 'Sensor':
    detectDep = 0
elif detectDep == 'Auto':
    detectDep = 1
detectDep = int(detectDep)

# Sonar mosaic
mosaic = values[54]
if mosaic == 'False':
    mosaic = 0
elif mosaic == 'GTiff':
    mosaic = 1
elif mosaic == 'VRT':
    mosaic = 2
mosaic = int(mosaic)

# Substrate mosaic
map_mosaic = values[56]
if map_mosaic == 'False':
    map_mosaic = 0
elif map_mosaic == 'GTiff':
    map_mosaic = 1
elif map_mosaic == 'VRT':
    map_mosaic = 2
map_mosaic = int(map_mosaic)


params = {
    # 'humFile':values[0],
    # 'projDir':os.path.join(values[1], values[2]),
    'project_mode':int(values[2]),
    'tempC':float(values[4]),
    'nchunk':int(values[5]),
    'cropRange':float(values[6]),
    'exportUnknown':values[7],
    'fixNoDat':values[8],
    'threadCnt':int(values[9]),
    'x_offset':float(values[11]),
    'y_offset':float(values[13]),
    'egn':values[15],
    'egn_stretch':egn_stretch,
    'egn_stretch_factor':float(values[18]),
    'wcp':values[20],
    'wcr':values[21],
    'tileFile':values[22],
    'lbl_set':lbl_set,
    'spdCor':float(values[25]),
    'maxCrop':values[27],
    'remShadow':remShadow,
    'detectDep':detectDep,
    'smthDep':values[32],
    'adjDep':float(values[34]),
    'pltBedPick':values[36],
    'rect_wcp':values[38],
    'rect_wcr':values[39],
    'son_colorMap':values[40],
    'pred_sub':values[42],
    'pltSubClass':values[44],
    'map_sub':values[45],
    'export_poly':values[47],
    'map_class_method':values[49],
    'pix_res':float(values[51]),
    'mosaic_nchunk':int(values[53]),
    'mosaic':mosaic,
    'map_mosaic':map_mosaic
}

globals().update(params)

#============================================

# Find all DAT and SON files in all subdirectories of inDir
inFiles=[]
for root, dirs, files in os.walk(inDir):
    for file in files:
        if file.endswith('.DAT'):
            inFiles.append(os.path.join(root, file))

inFiles = sorted(inFiles)

for i, f in enumerate(inFiles):
    print(i, ":", f)

for datFile in inFiles:
    # try:
    copied_script_name = os.path.basename(__file__).split('.')[0]+'_'+time.strftime("%Y-%m-%d_%H%M")+'.py'
    script = os.path.join(scriptDir, os.path.basename(__file__))

    logfilename = 'log_'+time.strftime("%Y-%m-%d_%H%M")+'.txt'

    start_time = time.time()  

    inPath = os.path.dirname(datFile)
    humFile = datFile
    recName = os.path.basename(humFile).split('.')[0]
    sonPath = humFile.split('.DAT')[0]
    sonFiles = sorted(glob(sonPath+os.sep+'*.SON'))

    projDir = os.path.join(outDir, recName)

    #============================================

    # =========================================================
    # Determine project_mode
    print(project_mode)
    if project_mode == 0:
        # Create new project
        if not os.path.exists(projDir):
            os.mkdir(projDir)
        else:
            projectMode_1_inval()

    elif project_mode == 1:
        # Overwrite existing project
        if os.path.exists(projDir):
            shutil.rmtree(projDir)

        os.mkdir(projDir)        

    elif project_mode == 2:
        # Update project
        # Make sure project exists, exit if not.
        
        if not os.path.exists(projDir):
            projectMode_2_inval()

    # =========================================================
    # For logging the console output

    logdir = os.path.join(projDir, 'meta', 'logs')
    if not os.path.exists(logdir):
        os.makedirs(logdir)

    logfilename = os.path.join(logdir, logfilename)

    sys.stdout = Logger(logfilename)

    for k, v in params.items():
        print(k, v)

    #============================================
    # Add ofther params
    params['sonFiles'] = sonFiles
    params['logfilename'] = logfilename
    params['script'] = [script, copied_script_name]
    params['projDir'] = projDir
    params['humFile'] = humFile



    print('sonPath',sonPath)
    print('\n\n\n+++++++++++++++++++++++++++++++++++++++++++')
    print('+++++++++++++++++++++++++++++++++++++++++++')
    print('***** Working On *****')
    print(humFile)
    print('Start Time: ', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))

    print('\n===========================================')
    print('===========================================')
    print('***** READING *****')
    read_master_func(**params)
    # read_master_func(sonFiles, humFile, projDir, t, nchunk, exportUnknown, wcp, wcr, detectDepth, smthDep, adjDep, pltBedPick, threadCnt)

    if rect_wcp or rect_wcr:
        print('\n===========================================')
        print('===========================================')
        print('***** RECTIFYING *****')
        rectify_master_func(**params)
        # rectify_master_func(sonFiles, humFile, projDir, nchunk, rect_wcp, rect_wcr, mosaic, threadCnt)

    #==================================================
    #==================================================
    if pred_sub or map_sub or export_poly or pltSubClass:
        print('\n===========================================')
        print('===========================================')
        print('***** MAPPING SUBSTRATE *****')
        print("working on "+projDir)
        map_master_func(**params)

    sys.stdout.log.close()

    # except:
    #     print('Could not process:', datFile)

    sys.stdout = oldOutput

    gc.collect()
    print("\n\nTotal Processing Time: ",datetime.timedelta(seconds = round(time.time() - start_time, ndigits=0)))

