import pyspark.sql.functions as func
from pyspark import SparkContext, SparkConf, SparkFiles
from pyspark.sql import SQLContext, Row
import ConfigParser as configparser
import os
from datetime import datetime
from vina_utils import get_directory_pdb_analysis, get_ligand_from_receptor_ligand_model
from database_io import load_database

def save_result_only_pose_normalized_residues_filtered_by_list(path_file_result_file_only_pose, df_result):    
    f_file = open(path_file_result_file_only_pose, "w")
    header = "# poses and normalized buried area by residues that were filtered by residues from buried area\n"
    f_file.write(header)                
    for row in df_result.collect():
        normalized_value  = "{:.4f}".format(row.normalized_buried_area)
        line = str(row.pose)+"\t"+str(normalized_value)+"\n"
        f_file.write(line)                
    f_file.close()


def save_result_only_pose(path_file_result_file_only_pose, df_result):    
    f_file = open(path_file_result_file_only_pose, "w")
    header = "# poses and sum of buried area by residues that were filtered by residues from buried area\n"
    f_file.write(header)                
    for row in df_result.collect():
        line = str(row.pose)+"\t"+str(row.sum_buried_area_res)+"\n"
        f_file.write(line)                
    f_file.close()

def save_result(path_file_result_file, df_result):
    f_file = open(path_file_result_file, "w")
    header = "# residue\tburied_area_residue[nm2]\tresidue_sasa_buried[%]\tpose\n"
    f_file.write(header)                
    for row in df_result.collect():
        line = str(row.residue)+"\t"+str(row.buried_area_residue)+"\t"+str(row.residue_sasa_buried_perc)+"\t"+str(row.pose)+"\n"
        f_file.write(line)                
    f_file.close()

def save_log(finish_time, start_time):
    log_file_name = 'buried_area_residue_selection.log'
    current_path = os.getcwd()
    path_file = os.path.join(current_path, log_file_name)
    log_file = open(path_file, 'w')

    diff_time = finish_time - start_time
    msg = 'Starting ' + str(start_time) +'\n'
    log_file.write(msg)
    msg = 'Finishing ' + str(finish_time) +'\n'
    log_file.write(msg)
    msg = 'Time Execution (seconds): ' + str(diff_time.total_seconds()) +'\n'
    log_file.write(msg)


def main():

    config = configparser.ConfigParser()
    config.read('config.ini')

    #Number of poses to select by buried area
    number_poses_to_select_buried_area = int(config.get('DRUGDESIGN', 'number_poses_to_select_buried_area') )
    # list of residues to select buried area
    file_select_buried_area = config.get('DRUGDESIGN', 'file_residue_to_select_buried_area')
    #Path that contains all files for analysis
    path_analysis = config.get('DEFAULT', 'path_analysis')    
    #File for saving the filtered buried area
    result_file_to_select_buried_area = config.get('DRUGDESIGN', 'result_file_to_select_buried_area')    
    #File for saving the filtered buried area only poses
    result_file_to_select_buried_area_only_pose = config.get('DRUGDESIGN', 'result_file_to_select_buried_area_only_pose')
    result_file_to_select_normalized_buried_area_only_pose = config.get('DRUGDESIGN', 'result_file_to_select_normalized_buried_area_only_pose')    
    #Ligand Database file
    ligand_database  = config.get('DEFAULT', 'ligand_database_path_file')    
    #Path where all pdb receptor are
    path_receptor = config.get('DEFAULT', 'pdb_path')    
    #Path for saving pdb files of models generated by VS
    path_ligand = get_directory_pdb_analysis(path_analysis)    
    #Path where saved the selected compelex
    path_to_save = os.path.join("selected_complexo", "buried_area_residue")
    path_to_save = os.path.join(path_analysis, path_to_save)
    if not os.path.exists(path_to_save):
        os.makedirs(path_to_save)
    #Path where saved the normalized selected compelex    
    path_to_save_normalized = os.path.join("selected_complexo", "normalized_buried_area")
    path_to_save_normalized = os.path.join(path_analysis, path_to_save_normalized)
    if not os.path.exists(path_to_save_normalized):
        os.makedirs(path_to_save_normalized)
    #Path where saved the normalized by residue list selected compelex    
    path_to_save_normalized_residue = os.path.join("selected_complexo", "normalized_buried_area_residue")
    path_to_save_normalized_residue = os.path.join(path_analysis, path_to_save_normalized_residue)
    if not os.path.exists(path_to_save_normalized_residue):
        os.makedirs(path_to_save_normalized_residue)

    # Create SPARK config
    maxResultSize = str(config.get('SPARK', 'maxResultSize'))
    conf = (SparkConf().set("spark.driver.maxResultSize", maxResultSize))

    # Create context
    sc = SparkContext(conf=conf)
    sqlCtx = SQLContext(sc)

    start_time = datetime.now()

    #Broadcast
    path_to_save_b = sc.broadcast(path_to_save) 
    path_receptor_b = sc.broadcast(path_receptor) 
    path_ligand_b = sc.broadcast(path_ligand) 

    #Adding Python Source file
    #Path for drugdesign project
    path_spark_drugdesign = config.get('DRUGDESIGN', 'path_spark_drugdesign')    
    sc.addPyFile(os.path.join(path_spark_drugdesign,"vina_utils.py"))
    sc.addPyFile(os.path.join(path_spark_drugdesign,"pdb_io.py"))
    sc.addPyFile(os.path.join(path_spark_drugdesign,"database_io.py"))

    #load all-residue_buried_areas.dat file
    path_file_buried_area = os.path.join(path_analysis, "all-residue_buried_areas.dat")
    all_residue    = sc.textFile(path_file_buried_area)
    header = all_residue.first() #extract header    

    #Spliting file by \t
    all_residue_split = all_residue.filter(lambda x:x !=header).map(lambda line: line.split("\t"))
    all_residue_split = all_residue_split.map(lambda p: Row( residue=str(p[0]), buried_area_residue=float(p[1]), residue_sasa_buried_perc=float(p[2]), pose=str(p[3]) ))

    #Creating all_residue Dataframe
    df_all_residue = sqlCtx.createDataFrame(all_residue_split)    
    df_all_residue.registerTempTable("all_residue")

    if os.path.isfile(file_select_buried_area):
        #Creating resudue list as Dataframe
        residue_list = sc.textFile(file_select_buried_area)    
        header = residue_list.first() #extract header        
        #Spliting file by \t
        residue_listRDD = residue_list.filter(lambda x:x !=header).map(lambda line: line)
        residue_listRDD = residue_listRDD.map(lambda p: Row( residue=str(p).strip() ))

        df_residue_list = sqlCtx.createDataFrame(residue_listRDD)    
        df_residue_list.registerTempTable("residue_list")

        #Getting all information based on list of residues
        sql = """
           SELECT all_residue.*
           FROM all_residue 
           JOIN residue_list ON residue_list.residue = all_residue.residue           
          """
        df_result = sqlCtx.sql(sql)
        df_result.registerTempTable("residues_filtered_by_list")    

        #Saving result
        path_file_result_file = os.path.join(path_analysis, result_file_to_select_buried_area)
        save_result(path_file_result_file, df_result)    

        #Grouping
        sql = """
           SELECT pose, sum(buried_area_residue) as sum_buried_area_res
           FROM residues_filtered_by_list 
           GROUP BY pose
           ORDER BY sum_buried_area_res DESC 
          """    
        df_result = sqlCtx.sql(sql)            

        #Saving result only pose
        path_file_result_file_only_pose = os.path.join(path_analysis, result_file_to_select_buried_area_only_pose)
        save_result_only_pose(path_file_result_file_only_pose, df_result)    

        #Loading poses
        only_poseRDD = sc.textFile(path_file_result_file_only_pose)
        header = only_poseRDD.first() #extract header        
        #Spliting file by \t
        only_poseRDD = only_poseRDD.filter(lambda x:x !=header).map(lambda line: line.split("\t"))
        only_poseRDD = only_poseRDD.map(lambda p: Row( pose=str(p[0]).strip(), sum_buried_area_res=float(str(p[1]).strip() ), f_name=str(p[1]).strip()+"_nm2_"+str(p[0]).strip()  ))

        only_pose_takeRDD = only_poseRDD.take(number_poses_to_select_buried_area)

        #Calculating normalized buried area by residues
        #Loading database
        rdd_database = load_database(sc, ligand_database)
        #Creating Dataframe
        database_table = sqlCtx.createDataFrame(rdd_database)    
        database_table.registerTempTable("database")

        normalizedRDD = df_result.map(lambda p: Row(sum_buried_area_res=float(p.sum_buried_area_res), ligand=get_ligand_from_receptor_ligand_model(p.pose), pose=str(p.pose) ) ).collect()
        #Creating Dataframe
        normalized_residues_filtered_by_list_table = sqlCtx.createDataFrame(normalizedRDD)    
        normalized_residues_filtered_by_list_table.registerTempTable("normalized_residues_filtered_by_list")        
        sql = """
            SELECT pose, (b.sum_buried_area_res / a.heavyAtom) as normalized_buried_area
            FROM database a 
            JOIN normalized_residues_filtered_by_list b ON b.ligand = a.ligand
            ORDER BY normalized_buried_area DESC 
          """
        df_result = sqlCtx.sql(sql)            

        #Saving result only pose by normalized buried area
        path_file_result_file_only_pose = os.path.join(path_analysis, result_file_to_select_normalized_buried_area_only_pose)
        save_result_only_pose_normalized_residues_filtered_by_list(path_file_result_file_only_pose, df_result)    

        #Loading poses - normalized_residues_filtered_by_list
        only_pose_normalizedRDD = sc.textFile(path_file_result_file_only_pose)
        header = only_pose_normalizedRDD.first() #extract header        
        #Spliting file by \t
        only_pose_normalizedRDD = only_pose_normalizedRDD.filter(lambda x:x !=header).map(lambda line: line.split("\t"))
        only_pose_normalizedRDD = only_pose_normalizedRDD.map(lambda p: Row( pose=str(p[0]).strip(), sum_buried_area_res=float(str(p[1]).strip() ), f_name=str(p[1]).strip()+"_nm2_"+str(p[0]).strip()  ))

        only_pose_normalizedRDD = only_pose_normalizedRDD.take(number_poses_to_select_buried_area)

#************** END OF RESIDUE LIST

    #Loading normalized poses
    path_file_normalized_pose = os.path.join(path_analysis, "summary_normalized_buried_areas.dat")
    normalized_poseRDD = sc.textFile(path_file_normalized_pose)
    header = normalized_poseRDD.first() #extract header        
    #Spliting file by \t
    normalized_poseRDD = normalized_poseRDD.filter(lambda x:x !=header).map(lambda line: line.split("\t"))
    normalized_poseRDD = normalized_poseRDD.map(lambda p: Row( pose=str(p[1]).strip(), normalized=float(str(p[0]).strip()), f_name=str(p[0]).strip()+"_hb_"+str(p[1]).strip() ) )
    #Filtering full normalized 
    normalized_poseToSaveRDD = normalized_poseRDD.take(number_poses_to_select_buried_area)

    df_normalized_residue_list = sqlCtx.createDataFrame(normalized_poseRDD)    
    df_normalized_residue_list.registerTempTable("normalized_poses")

# ******************** STARTED FUNCTION ********************************
    def build_complex_from_pose_file_name(p_name):
        from vina_utils import get_receptor_from_receptor_ligand_model, get_ligand_from_receptor_ligand_model, get_model_from_receptor_ligand_model, get_separator_filename_mode
        #Broadcast
        path_to_save = path_to_save_b.value
        path_receptor = path_receptor_b.value
        path_ligand = path_ligand_b.value
        #Based on row value from dataframe
        pose_file_name = p_name.pose

        #Receptor
        receptor_file_name = get_receptor_from_receptor_ligand_model(pose_file_name)                
        receptor_file = os.path.join(path_receptor, receptor_file_name+".pdb")
        f_receptor_file = open(receptor_file,"r")
        #ligand file name
        ligand_file_name = os.path.join(path_ligand, pose_file_name+".pdb")
        f_ligand_file_name = open(ligand_file_name,"r")

        #Open file for writting the complex
        full_path_for_save_complex = os.path.join(path_to_save, p_name.f_name+".pdb")
        f_compl = open(full_path_for_save_complex, "w")
        #Insert lines of receptor
        for item in  f_receptor_file:
            if str(item).find("END") == -1:
                f_compl.write(item)
        #Insert lines of model
        for item in f_ligand_file_name:        
            if str(item).find("REMARK") == -1:
                f_compl.write(item)
        #Closing files
        f_compl.close()
        f_ligand_file_name.close()
        f_receptor_file.close()
# ******************** FINISHED FUNCTION ********************************

    #Selecting poses by residues filtered
    if os.path.isfile(file_select_buried_area):        
        sc.parallelize(only_pose_takeRDD).foreach(build_complex_from_pose_file_name)
        path_to_save_b = sc.broadcast(path_to_save_normalized_residue) #Updated path to save complex
        sc.parallelize(only_pose_normalizedRDD).foreach(build_complex_from_pose_file_name)            

    #Selecting poses by normalized
    #Broadcast
    path_to_save_b = sc.broadcast(path_to_save_normalized) #Updated path to save complex
    sc.parallelize(normalized_poseToSaveRDD).foreach(build_complex_from_pose_file_name)
    
    finish_time = datetime.now()

    save_log(finish_time, start_time)

main()