# Part of PING-Mapper software
#
# Co-Developed by Cameron S. Bodine and Dr. Daniel Buscombe
#
# Inspired by PyHum: https://github.com/dbuscombe-usgs/PyHum
#
# MIT License
#
# Copyright (c) 2022-23 Cameron S. Bodine
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.


from funcs_common import *

from class_rectObj import rectObj
from class_mapSubstrateObj import mapSubObj
from class_portstarObj import portstarObj
from funcs_model import *

import itertools

#===============================================================================
def map_master_func(logfilename='',
                    project_mode=0,
                     script='',
                     humFile='',
                     sonFiles='',
                     projDir='',
                     tempC=10,
                     nchunk=500,
                     cropRange=0,
                     exportUnknown=False,
                     fixNoDat=False,
                     threadCnt=0,
                     x_offset=0,
                     y_offset=0,
                     tileFile=False,
                     egn=False,
                     egn_stretch=0,
                     egn_stretch_factor=1,
                     wcp=False,
                     wcr=False,
                     lbl_set=False,
                     spdCor=0,
                     maxCrop=False,
                     USE_GPU=False,
                     remShadow=0,
                     detectDep=0,
                     smthDep=0,
                     adjDep=0,
                     pltBedPick=False,
                     rect_wcp=False,
                     rect_wcr=False,
                     son_colorMap='Greys',
                     pred_sub=0,
                     map_sub=0,
                     export_poly=False,
                     map_predict=0,
                     pltSubClass=False,
                     map_class_method='max',
                     pix_res=0.0,
                     mosaic_nchunk=50,
                     mosaic=False,
                     map_mosaic=0):

    '''
    Main script to map substrates from side scan sonar imagery.

    ----------
    Parameters
    ----------

    -------
    Returns
    -------
    '''

    ############
    # Parameters
    flip = False #Flip port/star
    filter = int(nchunk*0.1) #Filters trackline coordinates for smoothing
    filterRange = filter #int(nchunk*0.05) #Filters range extent coordinates for smoothing


    # Specify multithreaded processing thread count
    if threadCnt==0: # Use all threads
        threadCnt=cpu_count()
    elif threadCnt<0: # Use all threads except threadCnt; i.e., (cpu_count + (-threadCnt))
        threadCnt=cpu_count()+threadCnt
        if threadCnt<0: # Make sure not negative
            threadCnt=1
    else: # Use specified threadCnt if positive
        pass

    if threadCnt>cpu_count(): # If more than total avail. threads, make cpu_count()
        threadCnt=cpu_count();
        print("\nWARNING: Specified more process threads then available, \nusing {} threads instead.".format(threadCnt))


    ############################################################################
    # Create mapObj() instance from previously created sonObj() instance       #
    ############################################################################

    ####################################################
    # Check if sonObj pickle exists, append to metaFiles
    metaDir = os.path.join(projDir, "meta")
    if os.path.exists(metaDir):
        metaFiles = sorted(glob(metaDir+os.sep+"*.meta"))
    else:
        sys.exit("No SON metadata files exist")
    del metaDir

    ############################################
    # Create a mapObj instance from pickle files
    sonObjs = []
    for meta in metaFiles:
        son = mapSubObj(meta) # Initialize mapObj()
        sonObjs.append(son) # Store mapObj() in mapObjs[]
    del meta, metaFiles

    #####################################
    # Determine which sonObj is port/star
    mapObjs = []
    for son in sonObjs:
        beam = son.beamName
        if beam == "ss_port" or beam == "ss_star":
            mapObjs.append(son)
        else:
            pass # Don't add non-port/star objects since they can't be rectified
    del son, beam, sonObjs

    ################################################
    # Prepare output directory and update attributes
    for son in mapObjs:
        son.substrateDir = os.path.join(son.projDir, 'substrate')
        # son.map_sub = map_sub

    outDir = son.substrateDir
    if not os.path.exists(outDir):
        os.mkdir(outDir)

    del son

    ##########################################################
    # If pred_sub == 0, make sure data was previously exported
    if pred_sub == 0:
        try:
            files = mapObjs[0]._getSubstrateNpz()
        except:
            error_noSubNpz()

    #########################################################
    # If map_sub == 0, make sure data was previously exported
    if not map_sub and map_mosaic:
        # Get directory
        mapPath = os.path.join(mapObjs[0].substrateDir, 'map_substrate_raster')
        maps = glob(os.path.join(mapPath, '*.tif'))

        if len(maps) == 0:
            if export_poly:
                error_noSubMap_poly()
            if map_mosaic:
                error_noSubMap_mosaic()

    #############################################
    # Determine if smoothed trackline was created
    if hasattr(mapObjs[0], 'smthTrkFile'):
        smthTrk = True
    else:
        smthTrk = False


    ############################################################################
    # Smooth trackline and calculate range extent if necessary                 #
    ############################################################################
    # Smoothing Trackline
    # Tool:
    # https://docs.scipy.org/doc/scipy-0.14.0/reference/tutorial/interpolate.html#spline-interpolation
    # Adapted from:
    # https://github.com/remisalmon/gpx_interpolate

    # smthTrk = True # For debugging
    if smthTrk:
        print("\nUsing existing smoothed trackline.")
    else:
        start_time = time.time()
        print("\nNo smoothed trackline available!\nSmoothing trackline...")

        # As side scan beams use same transducer/gps coords, we will smooth one
        ## beam's trackline and use for both. Use the beam with the most sonar records.
        maxRec = 0 # Stores index of recording w/ most sonar records.
        maxLen = 0 # Stores length of ping
        for i, son in enumerate(mapObjs):
            son._loadSonMeta() # Load ping metadata
            sonLen = len(son.sonMetaDF) # Number of sonar records
            if sonLen > maxLen:
                maxLen = sonLen
                maxRec = i

        # Now we will smooth using sonar beam w/ most records.
        son0 = mapObjs[maxRec]
        sonDF = son0.sonMetaDF # Get ping metadata
        sDF = son._interpTrack(df=sonDF, dropDup=True, filt=filter, deg=3) # Smooth trackline and reinterpolate trackpoints along spline
        del sonDF

        ####################################
        ####################################
        # To remove gap between sonar tiles:
        # For chunk > 0, use coords from previous chunks second to last ping
        # and assign as current chunk's first ping coords
        chunks = pd.unique(sDF['chunk_id'])

        i = 1
        while i <= max(chunks):
            # Get second to last row of previous chunk
            lastRow = sDF[sDF['chunk_id'] == i-1].iloc[[-2]]
            # Get index of first row of current chunk
            curRow = sDF[sDF['chunk_id'] == i].iloc[[0]]
            curRow = curRow.index[0]
            # Update current chunks first row from lastRow
            sDF.at[curRow, "lons"] = lastRow["lons"]
            sDF.at[curRow, "lats"] = lastRow["lats"]
            sDF.at[curRow, "utm_es"] = lastRow["utm_es"]
            sDF.at[curRow, "utm_ns"] = lastRow["utm_ns"]
            sDF.at[curRow, "cog"] = lastRow["cog"]

            i+=1
        del lastRow, curRow, i

        son0.smthTrk = sDF # Store smoothed trackline coordinates in rectObj.

        # Do positional correction
        if x_offset != 0.0 or y_offset != 0.0:
            son0._applyPosOffset(x_offset, y_offset)

        # Update other channel with smoothed coordinates
        # Determine which rectObj we need to update
        for i, son in enumerate(mapObjs):
            if i != maxRec:
                son1 = son # rectObj to update

        sDF = son0.smthTrk.copy() # Make copy of smoothed trackline coordinates
        # Update with correct record_num
        son1._loadSonMeta() # Load ping metadata
        df = son1.sonMetaDF
        sDF['chunk_id'] = df['chunk_id'] # Update chunk_id for smoothed coordinates
        sDF['record_num'] = df['record_num'] # Update record_num for smoothed coordinates
        son1.smthTrk = sDF # Store smoothed trackline coordinates in rectObj

        del sDF, df, son0, son1

        # Save smoothed trackline coordinates to file
        for son in mapObjs:
            outCSV = os.path.join(son.metaDir, "Trackline_Smth_"+son.beamName+".csv")
            son.smthTrk.to_csv(outCSV, index=False, float_format='%.14f')
            son.smthTrkFile = outCSV
            son._cleanup()
        del son, outCSV
        print("Done!")
        print("Time (s):", round(time.time() - start_time, ndigits=1))
        gc.collect()
        printUsage()

        ############################################################################
        # Calculate range extent coordinates                                       #
        ############################################################################
        start_time = time.time()
        print("\nCalculating, smoothing, and interpolating range extent coordinates...")
        Parallel(n_jobs= np.min([len(mapObjs), threadCnt]), verbose=10)(delayed(son._getRangeCoords)(flip, filterRange) for son in mapObjs)
        print("Done!")
        print("Time (s):", round(time.time() - start_time, ndigits=1))
        gc.collect()
        printUsage()

    for son in mapObjs:
        son._pickleSon()

    ############################################################################
    # For Substrate Prediction                                                 #
    ############################################################################

    if pred_sub > 0:
        start_time = time.time()

        print('\n\nAutomatically predicting and segmenting substrate...')

        outDir = os.path.join(mapObjs[0].substrateDir, 'predict_npz')
        if not os.path.exists(outDir):
            os.mkdir(outDir)

        # Get chunk id for mapping substrate
        for son in mapObjs:
            # Set outDir
            son.outDir = outDir

            # Get chunk id's
            chunks = son._getChunkID()

            # Prepare model
            if pred_sub == 1:
                # Load model weights
                # son.weights = r'./models/substrate/substrate_202211219_v1.h5'
                # son.configfile = son.weights.replace('.h5', '.json')
                # son.weights = r'./models/substrate/SegFormer_SpdCor_Substrate_inclShadow/weights/SegFormer_SpdCor_Substrate_inclShadow_fullmodel.h5'
                # son.configfile = son.weights.replace('weights', 'config').replace('_fullmodel.h5', '.json')

                if son.egn:
                    son.weights = r'./models/substrate/EGN_Substrate_Segformer/1_EGN_Substrate_GoodLabel_Segformer_fullmodel.h5'
                    son.configfile = son.weights.replace('_fullmodel.h5', '.json')

                    if not os.path.exists(son.weights):
                        downloadSubstrateModels()

                else:
                    # ! # !
                    # Update with Raw_Substrate_Segformer model once trained
                    # son.weights = r'./models/substrate/SegFormer_SpdCor_Substrate_inclShadow/weights/SegFormer_SpdCor_Substrate_inclShadow_fullmodel.h5'
                    # son.configfile = son.weights.replace('weights', 'config').replace('_fullmodel.h5', '.json')
                    son.weights = r'./models/substrate/Raw_Substrate_Segformer/2_Raw_Substrate_GoodLabel_Segformer_fullmodel.h5'
                    son.configfile = son.weights.replace('_fullmodel.h5', '.json')

                    if not os.path.exists(son.weights):
                        downloadSubstrateModels()

            # Do prediction (make parallel later)
            print('\n\tPredicting substrate for', len(chunks), son.beamName, 'chunks')

            Parallel(n_jobs=np.min([len(chunks), threadCnt]), verbose=10)(delayed(son._detectSubstrate)(i, USE_GPU) for i in chunks)

            # For debug
            # for c in chunks:
            #     print('\n\n\n\n****Chunk', c)
            #     son._detectSubstrate(c, USE_GPU)
            #     # sys.exit()
            #     break

            son._cleanup()
            son._pickleSon()
            del chunks

        del son
        print("\nDone!")
        print("Time (s):", round(time.time() - start_time, ndigits=1))
        gc.collect()
        printUsage()

    ############################################################################
    # Fot Substrate Plotting                                                   #
    ############################################################################

    print(pltSubClass)

    if pltSubClass:
        start_time = time.time()

        print('\n\nExporting substrate plots...')

        # Determine if probabilities or logits are plotted
        if map_predict == 1:
            probs = True
        elif map_predict == 2:
            probs = False
        else:
            probs = True


        # Out directory
        outDir = os.path.join(mapObjs[0].substrateDir, 'plots')
        if not os.path.exists(outDir):
            os.mkdir(outDir)

        # Get chunk id for mapping substrate
        for son in mapObjs:
            # Set outDir
            son.outDir = outDir

            # Get Substrate npz's
            toMap = son._getSubstrateNpz()

            print('\n\tExporting substrate plots for', len(toMap), son.beamName, 'chunks:')

            # Plot substrate classification
            # for c, f in toMap.items():
            #     print('\n\n\n\n****Chunk', c)
            #     son._pltSubClass(map_class_method, c, f, spdCor=spdCor, maxCrop=maxCrop)
            # #     sys.exit()
            # sys.exit()
            Parallel(n_jobs=np.min([len(toMap), threadCnt]), verbose=10)(delayed(son._pltSubClass)(map_class_method, c, f, spdCor=spdCor, maxCrop=maxCrop, probs=probs) for c, f in toMap.items())
            son._pickleSon()
            del toMap

        del son
        print("\nDone!")
        print("Time (s):", round(time.time() - start_time, ndigits=1))
        gc.collect()
        printUsage()


    ############################################################################
    # For Substrate Mapping                                                    #
    ############################################################################

    if map_sub > 0:
        start_time = time.time()

        print('\n\nMapping substrate classification...')

        # Set output directory
        outDir = os.path.join(mapObjs[0].substrateDir, 'map_substrate_raster')
        if not os.path.exists(outDir):
            os.mkdir(outDir)

        # Get each son's npz's
        for son in mapObjs:
            son.map_sub = map_sub

            # Set outDir
            son.outDir = outDir

            # Store substrate npz filenames
            npz = son._getSubstrateNpz()

            # Create dictionary to store port/star pairs
            if not 'toMap' in locals():
                toMap = npz
            else:
                for k, v in npz.items():
                    # Get existing npz file
                    e = toMap[k]

                    # Add existing and new npz as list. Add port as first element
                    if 'port' in e:
                        toMap[k] = [e, v]
                    else:
                        toMap[k] = [v, e]

        del son



        # Do rectification as portstarObj to eliminate NoData at NADIR
        print('\n\tMapping substrate classification. Processing', len(toMap), 'port and starboard pairs...')
        # Create portstarObj
        psObj = portstarObj(mapObjs)

        Parallel(n_jobs=np.min([len(toMap), threadCnt]), verbose=10)(delayed(psObj._mapSubstrate)(map_class_method, c, f) for c, f in toMap.items())

        # # For debug
        # for c, f in toMap.items():
        #     psObj._mapSubstrate(map_class_method, c, f)
        # #     sys.exit()

        del toMap
        print("\nDone!")
        print("Time (s):", round(time.time() - start_time, ndigits=1))
        gc.collect()
        printUsage()

    ############################################################################
    # For Substrate Mosaic                                                     #
    ############################################################################

    overview = True # False will reduce overall file size, but reduce performance in a GIS
    if map_mosaic > 0:
        start_time = time.time()
        print("\nMosaicing GeoTiffs...")

        # Create portstar object
        psObj = portstarObj(mapObjs)

        # Switch off rect_wcp and rect_wcr
        psObj.port.rect_wcp = False
        psObj.port.rect_wcr = False
        psObj.port.map_predict = False

        # Make sure map_sub is set to true
        psObj.port.map_sub = True

        # Create the mosaic
        psObj._createMosaic(mosaic=map_mosaic, overview=overview, threadCnt=threadCnt, son=False, maxChunk=mosaic_nchunk)

        # Revert rect_wcp and rect_wcr
        psObj.port.rect_wcp = rect_wcp
        psObj.port.rect_wcr = rect_wcr
        psObj.port.map_predict = map_predict
        psObj.port.map_substrate = map_sub

        del psObj
        print("\nDone!")
        print("Time (s):", round(time.time() - start_time, ndigits=1))
        gc.collect()
        printUsage()

    ############################################################################
    # For Substrate Polygon                                                    #
    ############################################################################

    if export_poly:
         start_time = time.time()
         print("\nConverting substrate rasters into shapefile...")

         # Create portstar object
         psObj = portstarObj(mapObjs)

         # Switch off rect_wcp and rect_wcr
         psObj.port.rect_wcp = False
         psObj.port.rect_wcr = False
         psObj.port.map_predict = False

         # Make sure map_sub is set to true
         psObj.port.map_sub = True

         psObj._rasterToPoly(map_mosaic, threadCnt, mosaic_nchunk)

         # Revert rect_wcp and rect_wcr
         psObj.port.rect_wcp = rect_wcp
         psObj.port.rect_wcr = rect_wcr
         psObj.port.map_predict = map_predict
         psObj.port.map_sub = map_sub

         del psObj
         print("\nDone!")
         print("Time (s):", round(time.time() - start_time, ndigits=1))
         gc.collect()
         printUsage()

    ############################################################################
    # For Prediction Mapping                                                   #
    ############################################################################


    if map_predict > 0:
        start_time = time.time()

        if map_predict == 1:
            a = 'probability'
        else:
            a = 'logit'
        print('\n\nMapping substrate prediction as ***{}***...'.format(a.upper()))

        # Set output directory
        outDir = os.path.join(mapObjs[0].substrateDir, 'map_'+a+'_raster')
        if not os.path.exists(outDir):
            os.mkdir(outDir)

        # Get each son's npz's
        for son in mapObjs:
            # Set outDir
            son.outDir = outDir

            # Store map_predict
            son.map_predict = map_predict

            # Store substrate npz filenames
            npz = son._getSubstrateNpz()

            # Create dictionary to store port/star pairs
            if not 'toMap' in locals():
                toMap = npz
            else:
                for k, v in npz.items():
                    # Get existing npz file
                    e = toMap[k]

                    # Add existing and new npz as list. Add port as first element
                    if 'port' in e:
                        toMap[k] = [e, v]
                    else:
                        toMap[k] = [v, e]
        del son


        # Do rectification as portstarObj to eliminate NoData at NADIR
        print('\n\tMapping substrate predictions. Processing', len(toMap), 'port and starboard pairs...')
        # Create portstarObj
        psObj = portstarObj(mapObjs)

        # for c, f in toMap.items():
        #     psObj._mapPredictions(map_predict, 'map_'+a, c, f)
        #     sys.exit()

        Parallel(n_jobs=np.min([len(toMap), threadCnt]), verbose=10)(delayed(psObj._mapPredictions)(map_predict, 'map_'+a, c, f) for c, f in toMap.items())

        del toMap, psObj
        print("\nDone!")
        print("Time (s):", round(time.time() - start_time, ndigits=1))
        gc.collect()
        printUsage()


    ############################################################################
    # For Prediction Mosaic                                                    #
    ############################################################################

    overview = True # False will reduce overall file size, but reduce performance in a GIS
    if map_predict > 0 and mosaic > 0:
        start_time = time.time()
        print("\nMosaicing GeoTiffs...")

        # for son in mapObjs:
        #     son.map_predict = map_predict
        # del son

        # Create portstar object
        psObj = portstarObj(mapObjs)

        # Switch off rect_wcp, rect_wcr, and mapSub
        psObj.port.rect_wcp = False
        psObj.port.rect_wcr = False
        psObj.port.map_sub = True
        psObj.port.map_predict = False

        # Create the mosaic
        psObj._createMosaic(mosaic=1, overview=overview, threadCnt=threadCnt, son=False, maxChunk=mosaic_nchunk)

        # Revert rect_wcp, rect_wcr, mapSub
        psObj.port.rect_wcp = rect_wcp
        psObj.port.rect_wcr = rect_wcr
        psObj.port.map_sub = map_sub
        psObj.port.map_predict = map_predict

        del psObj
        print("Done!")
        print("Time (s):", round(time.time() - start_time, ndigits=1))
        gc.collect()
        printUsage()

    ##############################################
    # Let's pickle sonObj so we can reload later #
    ##############################################

    for son in mapObjs:
        son._cleanup()
        son._pickleSon()
    gc.collect()
    printUsage()
