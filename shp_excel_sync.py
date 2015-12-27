from sets import Set
from datetime import datetime

from qgis._core import QgsMessageLog, QgsMapLayerRegistry, QgsFeatureRequest, QgsFeature
from qgis.utils import iface
from PyQt4.QtCore import QFileSystemWatcher
from PyQt4 import QtGui

def layer_from_name(layerName):
    # Important: If multiple layers with same name exist, it will return the first one it finds
    for (id, layer) in QgsMapLayerRegistry.instance().mapLayers().iteritems():
        if unicode(layer.name()) == layerName:
            return layer
    return None

# configurable
logTag="OpenGIS" # in which tab log messages appear
# excel layer
excelName="Beispiel"
excelKeyName="EFKey"
excelPath=layer_from_name(excelName).publicSource()
areaKey="Field9"
centroidKey="Field14"
# shpfile layer
shpName="Beispiel_Massnahmepool"
shpKeyName="ef_key"


# state variables 
filewatcher=None
shpAdd = {}
shpChange = {}
shpRemove = Set([])


def reload_excel():
    path = excelPath
    layer = layer_from_name(excelName)
    import os
    fsize=os.stat(excelPath).st_size 
    info("fsize "+str(fsize))
    if fsize==0:
        info("File empty. Won't reload yet")
        return
    layer.dataProvider().forceReload()

def showWarning(msg):
    QtGui.QMessageBox.information(iface.mainWindow(),'Warning',msg)


def get_fk_set(layerName, fkName, skipFirst=True, fids=None):
    layer = layer_from_name(layerName)
    freq = QgsFeatureRequest()
    if fids is not None:
        freq.setFilterFids(fids)
    feats = [f for f in layer.getFeatures(freq)]
    fkSet = []
    first=True
    for f in feats:
        if skipFirst and first:
            first=False
            continue
        fk = f.attribute(fkName)
        fkSet.append(fk)
    return fkSet
       

def info(msg):
    QgsMessageLog.logMessage(str(msg), logTag, QgsMessageLog.INFO)

def warn(msg):
    QgsMessageLog.logMessage(str(msg), logTag)
    showWarning(str(msg))

def error(msg):
    QgsMessageLog.logMessage(str(msg), logTag, QgsMessageLog.CRITICAL)

def excel_changed():
    info("Excel changed in disk - need to sync")
    reload_excel()
    update_shp_from_excel()

def added_geom(layerId, feats):
    info("added feats "+str(feats))
    fks_to_add = [feat.attribute(shpKeyName) for feat in feats]
    global shpAdd
    shpAdd = {k:v for (k,v) in zip(fks_to_add, feats)}


def removed_geom(layerId, fids):
    fks_to_remove = get_fk_set(shpName,shpKeyName,skipFirst=False,fids=fids)
    global shpRemove
    shpRemove = Set(fks_to_remove)

def changed_geom(layerId, geoms):
    fids = geoms.keys()
    freq = QgsFeatureRequest() 
    freq.setFilterFids(fids)
    feats = list(layer_from_name(shpName).getFeatures(freq))
    fks_to_change = get_fk_set(shpName,shpKeyName,skipFirst=False,fids=fids)
    global shpChange
    shpChange = {k:v for (k,v) in zip(fks_to_change, feats)}
    #info("changed"+str(shpChange))


def update_excel_programmatically():
    import pandas as pd #0.17
    df = pd.read_excel(excelPath)
    keyField = df.columns[0] # FIXME: this should be settable
    areaField = df.columns[8]
    cField = df.columns[13]
    df = df.set_index(keyField, drop=False)
    #info(str(df))
    df = df[~df[keyField].isin(shpRemove)]
    for key in shpChange.keys():
       shpf = shpChange[key]
       area = str(shpf.geometry().area())
       centroid = str(shpf.geometry().centroid().asPoint())
       df.loc[key,areaField] = area
       df.loc[key,cField] = centroid
    
    for key in shpAdd.keys():
       shpf = shpAdd[key]
       area = str(shpf.geometry().area())
       centroid = str(shpf.geometry().centroid().asPoint())
       df2 = pd.DataFrame([['']*len(df.columns)],columns=df.columns)
       df2.loc[0,areaField] = area
       df2.loc[0,cField] = centroid
       df2.loc[0,keyField] = key
       #TODO what about the other fields? 
       df = df.append(df2)
        

    #df2 = pd.DataFrame(columns=df.columns)
    #info("changed?")
    #info(str(df))

    df.to_excel(excelPath, index=False, columns=None)

def update_excel_via_qgis():
    # This function doesn't work for xls files
    layer = layer_from_name(excelName)
    shp = layer_from_name(shpName)
    layer.startEditing()
    feats = [f for f in layer.getFeatures()]

    for f in feats:
        key = f.attribute(excelKeyName)
        flds = f.fields()
        if key in shpRemove:
            layer.deleteFeature(f.id())
        if key in shpChange.keys():
           shpf = shpChange[key]
           f.setAttribute(areaKey, str(shpf.geometry().area()))
           f.setAttribute(centroidKey, str(shpf.geometry().centroid().asPoint()))
           layer.updateFeature(f)
           #info("Set {} area to {}".format(key,str(shpf.geometry().area() )))

    for key in shpAdd.keys():
        shpf = shpAdd[key]
        f = QgsFeature(flds)
        f.setAttribute(areaKey, str(shpf.geometry().area()))
        f.setAttribute(centroidKey, str(shpf.geometry().centroid().asPoint()))
        f.setAttribute(excelKeyName, key)
        #TODO: What about other attributes
        layer.addFeature(f)
        

    layer.commitChanges()

def update_excel_from_shp():
    info("Will now update excel from edited shapefile")
    info("changing:"+str(shpChange))
    info("adding:"+str(shpAdd))
    info("removing"+str(shpRemove))
    update_excel_programmatically()
    #update_excel_via_qgis()
    global shpAdd
    global shpChange
    global shpRemove
    shpAdd = {}
    shpChange = {}
    shpRemove = Set([]) 


def updateShpLayer(fksToRemove):
    layer = layer_from_name(shpName)
    feats = [f for f in layer.getFeatures()]
    layer.startEditing()
    for f in feats:
         if f.attribute(shpKeyName) in fksToRemove:
             layer.deleteFeature(f.id())
    layer.commitChanges()
     

def update_shp_from_excel():
   
    excelFks = Set(get_fk_set(excelName, excelKeyName,skipFirst=False))
    if not excelFks:
        warn("Qgis thinks that the Excel file is empty. That probably means something went horribly wrong. Won't sync.")
        return
    shpFks = Set(get_fk_set(shpName,shpKeyName,skipFirst=False))
    # TODO somewhere here I should refresh the join
    # TODO also special warning if shp layer is in edit mode
    info("Keys in excel"+str(excelFks))
    info("Keys in shp"+str(shpFks))
    if shpFks==excelFks:
        info("Excel and Shp layer have the same rows. No update necessary")
        return
    inShpButNotInExcel = shpFks - excelFks
    inExcelButNotInShp = excelFks - shpFks
    if inExcelButNotInShp:
         warn("There are rows in the excel file with no matching geometry {}. Can't update shapefile from those.".format(inExcelButNotInShp))
    if inShpButNotInExcel:
        info("Will remove features "+str(inShpButNotInExcel)+"from shapefile because they have been removed from excel")
        updateShpLayer(inShpButNotInExcel)

def init(filename):
    info("Initial Syncing excel to shp")
    update_shp_from_excel()
    global filewatcher # otherwise the object is lost
    filewatcher = QFileSystemWatcher([filename])
    filewatcher.fileChanged.connect(excel_changed)
    shpLayer = layer_from_name(shpName)
    shpLayer.committedFeaturesAdded.connect(added_geom)
    shpLayer.committedFeaturesRemoved.connect(removed_geom)
    shpLayer.committedGeometriesChanges.connect(changed_geom)
    shpLayer.editingStopped.connect(update_excel_from_shp)