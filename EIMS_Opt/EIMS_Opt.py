
#import required modules
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import matplotlib
from matplotlib.sankey import Sankey
import seaborn as sns
import time
#%%
#Path stuff damit die relativen Verweise immer Funktionieren
cwd = os.getcwd()  # Get the current working directory (cwd)
print("Working DIR: ", cwd)
os.chdir(os.path.dirname(os.path.abspath(__file__))) #Set new working directory
cwd = os.getcwd()  # Get the current working directory (cwd)
print("Working DIR new: ", cwd)
#%%

class cla_Gebäude():
    def __init__(self, var_BGF, var_EV):
        self.BGF = var_BGF   #m²
        self.EV = var_EV * self.BGF / 1000   #kW
        self.CO2 = 227 #g/kWh
        self.CO2_PV = 45 #g/kWh //Von Ele-Map
        self.CO2_Bat = 60 #g/kWh //Annahme
        self.CO2_Gesamt = 0
        self.Prim_Factor = 1.63
        self.Prim_Gesamt = 0
        
class cla_PV_Anlage():
    def __init__(self, var_PV_kWp,var_PV_EK):
        self.PV = var_PV_kWp #kW
        self.PV_EK = self.PV * var_PV_EK / 1000 #kW
   
class cla_Batterie():
    
    def __init__(self, var_EntTiefe, var_Effizienz, var_kapMAX, var_LadeEntladeLeistung = 0):
        self.Entladetiefe = var_kapMAX * var_EntTiefe / 100  #%
        self.Effizienz = var_Effizienz # Einheit %/100
        self.Kapazität = 0 #kWh
        self.Kapazität_MAX = var_kapMAX #kWh
        self.Leistung = var_LadeEntladeLeistung #kW
        self.Leistung_MAX = var_kapMAX * 0.5 #kW
        self.Verlust = 0 #kW


    def Entladen(self,arg_Reslast):
        #self.Leistung ist der Teil der anschließend von der Reslast abgezogen wird
        
        var_ResLast_mit_Verlust = arg_Reslast + (arg_Reslast*(1-self.Effizienz))
        if var_ResLast_mit_Verlust < self.Leistung_MAX and var_ResLast_mit_Verlust < self.Kapazität:
            #Kann die Residuallast + Verlust gedeckt werden?
            self.Verlust = arg_Reslast * (1-self.Effizienz)  
            self.Leistung = arg_Reslast# - self.Verlust
        else:
            self.Verlust = arg_Reslast * (1-self.Effizienz) 
            self.Leistung = arg_Reslast 

        #Kontrolle der Leistung
        if self.Leistung + self.Verlust > self.Kapazität:
            #Wenn nicht genügend Kapazität vorhanden ist wird die Leistung gekappt
            self.Verlust = self.Kapazität * (1-self.Effizienz)
            self.Leistung = self.Kapazität - self.Verlust
            
        #Ausführen des Entladevorgangs
        self.Kapazität -= self.Leistung + self.Verlust
        arg_Reslast -= self.Leistung 

        return arg_Reslast
    
    def Laden(self,arg_Reslast):
        if arg_Reslast > self.Leistung_MAX:
            #Wenn ja wird gekappt
            self.Verlust = self.Leistung_MAX * (1-self.Effizienz)
            self.Leistung = self.Leistung_MAX * self.Effizienz 
            
        else:
            #Wenn nein, g2g
            self.Verlust = arg_Reslast * (1-self.Effizienz)
            self.Leistung = arg_Reslast * self.Effizienz 
            
        #Kontrolle ob die Batterie über die Maximale Kapazität geladen werden würde
        if self.Kapazität + self.Leistung > self.Kapazität_MAX:
            self.Verlust = (self.Kapazität_MAX - self.Kapazität) * (1-self.Effizienz)
            self.Leistung = (self.Kapazität_MAX - self.Kapazität) * self.Effizienz
            
            
        #Ausführen des Ladevorgangs
        self.Kapazität += self.Leistung
        arg_Reslast -= (self.Leistung + self.Verlust)
        
        return arg_Reslast
    
class cla_Data_Tracking():    
    def __init__(self,arg_PV_Anlage,arg_Gebäude,arg_Battery):
        self.PV_kWp = arg_PV_Anlage.PV
        self.Bat_kWh = arg_Battery.Kapazität_MAX
        self.PV_Erzeugung = arg_PV_Anlage.PV_EK
        self.Gebäudeverbrauch = arg_Gebäude.EV
        self.PV_Direktverbrauch = np.zeros(8760)
        self.Batteriekapazität = np.zeros(8760)
        self.Batterieeinspeisung = np.zeros(8760)
        self.Batterieentladung = np.zeros(8760)
        self.Batterieverluste = np.zeros(8760)
        self.Netzeinspeisung = np.zeros(8760)
        self.Netzbezug = np.zeros(8760)    
        
    #CleanData sorgt dafür dass alle Datenpunkte positiv sind
    def CleanData(self):
        for attr,val in self.__dict__.items():
            #Kontrolle ob unsere Variable iterierbar ist
            try:
                iter(val)
            except TypeError:
                continue
            if any(val < 0):
                setattr(self, attr, abs(val))

class cla_Costs():

    def __init__(self, obj_Datatracker):
        self.PV_kWp = obj_Datatracker.PV_kWp
        self.Bat_kWh = obj_Datatracker.Bat_kWh
        self.PV_cost = 700 # €/kWp
        self.battery_cost = 200         # €/kWh
        self.Cost_Operation_Percent = 1 # % der Investmestkosten pro Jahr
        self.price_feed_in = 0.05  # €/kWh
        self.price_grid = 0.19  # €/kWh 
        self.Life = 10 #Years
        self.Investment_costs = self.PV_kWp * self.PV_cost + self.Bat_kWh * self.battery_cost
        self.Operation_costs = self.Get_Operationcosts(obj_Datatracker)
        self.total_costs = self.Get_Costs()



    def Get_Costs(self):
         return self.Investment_costs + self.Operation_costs * self.Life

    def Get_Operationcosts(self, obj_Datatracker):
         return sum(obj_Datatracker.Netzbezug) * self.price_grid - sum(obj_Datatracker.Netzeinspeisung) * self.price_feed_in





#%%
class cla_Plotting():       
    
    def __init__(self, obj_Datatracker):
        time = np.arange('2021-01-01', '2022-01-01', dtype='datetime64[h]')
        self.dat_Daten = pd.DataFrame(vars(obj_Datatracker), index = time)
    
    def Lineplot_Leistung(self, li_toPLot = [], str_toSave = "temp"):
        fig, ax = plt.subplots(2,1,figsize=(10,12),gridspec_kw={'height_ratios': [3, 2]})
        
        df_Plot = self.dat_Daten[li_toPLot]
        df_Plot = df_Plot.resample("d").mean()
        
        sns.lineplot(data = df_Plot, ax = ax[0])
        ax[0].set_ylabel("Leistung [kW]")
        ax[0].set_title(li_toPLot)
        ax[0].yaxis.grid(linewidth=0.5)
        
        sns.boxenplot(data = self.dat_Daten[li_toPLot], ax = ax[1])
        
        ax[1].set_title("Boxenplot der Daten")
        ax[1].yaxis.grid(linewidth=0.5)
        ax[1].set_ylabel("Leistung [kW]")
        
        plt.savefig("./Bilder/"+str_toSave+"", bbox_inches = 'tight',pad_inches = 0.08)
        
    def Break_Even_Plot(self,obj_Costs,str_toSave): 
        return
        fig, ax = plt.subplots(figsize=(12,8))
        
        
        df_Plot = pd.DataFrame()
        df_Plot["Kosten"] = obj_Costs.LifeCosts
        df_Plot["Vergütung"] = obj_Costs.LifeRevenue
        df_Plot["Cashflow"] = df_Plot["Kosten"] - df_Plot["Vergütung"]
        
        sns.lineplot(data = df_Plot, ax = ax, palette = ["red","green","blue"], linewidth = 2,marker='o')
        ax.yaxis.grid(linewidth=0.5)
        ax.set_title("Kosten, Vergütung und Cashflow der Anlage")
        ax.set_ylabel("Cashflow [€]")
        ax.set_xlabel("Jahre")
        plt.savefig("./Bilder/"+str_toSave+"", bbox_inches = 'tight',pad_inches = 0.08)

        
    def Sankeyplot(self,obj_Datatracker):
        fig, ax = plt.subplots(figsize=(10,12))
        flows_Batterie = [obj_Datatracker.Batterieentladung.sum(),obj_Datatracker.Batterieeinspeisung.sum()*-1,obj_Datatracker.Batterieverluste.sum()*-1]
        flows_Gebäude = [obj_Datatracker.Batterieeinspeisung.sum(),obj_Datatracker.Batterieentladung.sum()*-1,
                         obj_Datatracker.PV_Erzeugung.sum(),obj_Datatracker.Gebäudeverbrauch.sum()*-1,
                         obj_Datatracker.Netzbezug.sum()*-1,obj_Datatracker.Netzeinspeisung.sum()]
        flows_Netz = [obj_Datatracker.Netzbezug.sum(),obj_Datatracker.Netzeinspeisung.sum()*-1]
        
        labels_Batterie = ["Batterieentladung","Batterieeinspeisung","Batterieverluste"]
        labels_Gebäude = ["","","PV_Erzeugung","Gebäudeverbrauch","",""]
        labels_Netz  = ["Netzbezug","Netzeinspeisung"]
        
        orientation_Batterie = [1,1,0]
        orientation_Gebäude = [1,1,0,0,-1,-1]
        orientation_Netz = [-1,-1]
                
        sankey = Sankey(ax=ax, scale=0.8, unit = "kWh")
        sankey.add(flows=flows_Gebäude, label=labels_Gebäude, edgecolor = '#000000', facecolor = 'lightgrey',
           orientations=orientation_Gebäude, trunklength = 5000, pathlengths = [2500,1000,1000,1000,1000,1000])
        
        sankey.add(flows=flows_Batterie, label=labels_Batterie,edgecolor = '#000000', facecolor = 'lightblue',
           orientations=orientation_Batterie, trunklength = 5000, pathlengths = 500,prior=0,connect=(1, 0))
        
        sankey.add(flows=flows_Netz, label=labels_Netz,edgecolor = '#000000', facecolor = 'khaki',
           orientations=orientation_Netz, trunklength = 5000, pathlengths = 500,prior=0,connect=(4, 0))
    
        sankey.finish()
            
        plt.savefig("./Bilder/SankeyTest", bbox_inches = 'tight',pad_inches = 0.08)   
#%%
class Model():

    def Simulate(self,var_BGF, var_PV_kWP, var_battery_kWh,verbose = False):
        Test_hourly = []
        obj_Gebäude = cla_Gebäude(var_BGF,np.genfromtxt(".\\Data\\ED_Wh_per_m2.csv"))
        obj_PV_Anlage = cla_PV_Anlage(var_PV_kWP,np.genfromtxt(".\\Data\\PV_1kWp.csv"))
        obj_Batterie = cla_Batterie(var_EntTiefe = 20, var_Effizienz = 0.95,var_kapMAX = var_battery_kWh)
        obj_Datatracker = cla_Data_Tracking(arg_PV_Anlage = obj_PV_Anlage, arg_Gebäude = obj_Gebäude, arg_Battery = obj_Batterie)
        t0 = time.time() #Timekeeping
        for it_hour in range(8760):
            #Rediuallast
            var_ResLast = obj_PV_Anlage.PV_EK[it_hour] - obj_Gebäude.EV[it_hour]
            #Tracking des Direktverbrauches
            obj_Datatracker.PV_Direktverbrauch[it_hour] = min(obj_PV_Anlage.PV_EK[it_hour], obj_Gebäude.EV[it_hour])
     
            #Debug Prints
            if verbose == True:
                print("PV_Ertrag: ", obj_PV_Anlage.PV_EK[it_hour])
                print("Gebäude_Bezug: ", obj_Gebäude.EV[it_hour])
                print("ResLast_Davor: ", var_ResLast)
            
            if var_ResLast > 0: 
                #Einspeisefall
                var_ResLast = obj_Batterie.Laden(var_ResLast)
                obj_Datatracker.Batterieeinspeisung[it_hour] = obj_Batterie.Leistung
                #Restverwertung via Netz + Tracking
                obj_Datatracker.Netzeinspeisung[it_hour] = var_ResLast

            elif var_ResLast < 0:
                #Entladefall
                var_ResLast = abs(var_ResLast) #Die späteren Funktionen gehen immer von einer Positiven Zahl aus.
                var_ResLast = obj_Batterie.Entladen(var_ResLast)
                obj_Datatracker.Batterieentladung[it_hour] = obj_Batterie.Leistung + obj_Batterie.Verlust
                #Restverwertung via Netz + Tracking
                obj_Datatracker.Netzbezug[it_hour] = var_ResLast
        
            #Tracking der allgemeinen Daten
            obj_Datatracker.Batterieverluste[it_hour] = obj_Batterie.Verlust
            obj_Datatracker.Batteriekapazität[it_hour] = obj_Batterie.Kapazität
        
            #Debug Prints
            if verbose == True:
                print("ResLast_Danach: ", var_ResLast)
                print("Bat_Kapazität: ", obj_Batterie.Kapazität)
                print("Bat_Ladeleistung: ", obj_Batterie.Leistung)
                print("Bat_Verlust: ", obj_Batterie.Verlust)
                print("Netzbezug: ", obj_Datatracker.Netzbezug[it_hour])
                print("NetzEinspeisung: ", obj_Datatracker.Netzeinspeisung[it_hour])    
                
                print(it_hour)
            flows_in_hour = abs(obj_Datatracker.Netzbezug[it_hour]) + abs(obj_Datatracker.Batterieentladung[it_hour]) + abs(obj_Datatracker.PV_Erzeugung[it_hour])
            flows_out_hour = abs(obj_Datatracker.Netzeinspeisung[it_hour]) + abs(obj_Datatracker.Batterieeinspeisung[it_hour]) + \
                            abs(obj_Datatracker.Batterieverluste[it_hour]) + abs(obj_Datatracker.Gebäudeverbrauch[it_hour])

            Test_hourly.append(flows_in_hour - flows_out_hour)
        #print("PV_Erzeugung: ", round(obj_PV_Anlage.PV_EK.sum(),2), " kWh")  
        #print("Gebäudeverbrauch: ", round(obj_Gebäude.EV.sum(),2), " kWh") 
        #print("PV Direktverbrauch: ", round(obj_Datatracker.PV_Direktverbrauch.sum(),2), " kWh") 
        #print("Batterieentladung: ", round(obj_Datatracker.Batterieentladung.sum(),2), " kWh")
        #print("Netzeinspeisung: ", round(obj_Datatracker.Netzeinspeisung.sum(),2), " kWh")
        #Test ob die Energiebilanz stimmt
        obj_Datatracker.CleanData()
        flows_in = [obj_Datatracker.Netzbezug.sum(),obj_Datatracker.Batterieentladung.sum(), obj_Datatracker.PV_Erzeugung.sum()]
        flows_out = [obj_Datatracker.Netzeinspeisung.sum(),obj_Datatracker.Batterieeinspeisung.sum(), 
                            obj_Datatracker.Batterieverluste.sum(),obj_Datatracker.Gebäudeverbrauch.sum()]
        Test = sum(flows_in) - sum(flows_out)
        if abs(Test) > 0.0000001:
            pass
            #raise ValueError("ENERGIEBILANZ STIMMT NICHT!")
        t1 = time.time() #Timekeeping
        #print("Done Simulating in ",round(t1-t0,3)," Seconds")      
    
        # plot your results:
        obj_Plotter = cla_Plotting(obj_Datatracker)
        #obj_Plotter.Sankeyplot(obj_Datatracker) WiP
        #obj_Plotter.Lineplot_Leistung(li_toPLot = ["Batterieverluste","Batterieeinspeisung","Batterieentladung"],str_toSave = "Bat_Leistungen")
        #obj_Plotter.Lineplot_Leistung(li_toPLot = ["Batteriekapazität"],str_toSave = "Bat_Kapazität")
        #obj_Plotter.Lineplot_Leistung(li_toPLot = ["PV_Direktverbrauch"],str_toSave = "PV_Direktverbrauch")
        #print("Batterieeinspeisung: ", round(obj_Datatracker.Batterieeinspeisung.sum(),2), " kWh")
        #print("Batterieverlust: ", round(obj_Datatracker.Batterieverluste.sum(),2), " kWh")
        #print("Netzbezug: ", round(obj_Datatracker.Netzbezug.sum(),2), " kWh")
        #obj_Plotter.Lineplot_Leistung(li_toPLot = ["Netzeinspeisung","Netzbezug"],str_toSave = "Netz_IO")
        t2 = time.time() #Timekeeping
        #print("Done Plotting in ",round(t2-t1,3)," Seconds")


        # calc Primary Energy
        obj_Gebäude.Prim_Gesamt = (sum(obj_Datatracker.Netzbezug) * obj_Gebäude.Prim_Factor - sum(obj_Datatracker.Netzeinspeisung)) / obj_Gebäude.BGF

        # calc CO2 
        obj_Gebäude.CO2_Gesamt = ((sum(obj_Datatracker.Netzbezug) * obj_Gebäude.CO2 - sum(obj_Datatracker.Netzeinspeisung) * obj_Gebäude.CO2) / 1000) / obj_Gebäude.BGF

        # calculate cost [€/life cycle]
        obj_Costs = cla_Costs(obj_Datatracker)
        #obj_Plotter.Break_Even_Plot(obj_Costs,str_toSave = "Cashflow")
        # investment cost [€/life cycle]
    
        # operational cost [€/life cycle]
        result = {
            "Gesamtkosten" : obj_Costs.total_costs,
            "Investmentkosten" : obj_Costs.Investment_costs,
            "Operationskosten" : obj_Costs.Operation_costs,
            "Emissionen" : obj_Gebäude.CO2_Gesamt,
            "Primärenergie" : obj_Gebäude.Prim_Gesamt,
            "Netzeinspeisung" : sum(obj_Datatracker.Netzeinspeisung),
            "Netzbezug" : sum(obj_Datatracker.Netzbezug),
            "PV_Erzeugung" : sum(obj_Datatracker.PV_Erzeugung),
            "Gebäudeverbrauch" : sum(obj_Datatracker.Gebäudeverbrauch),
            "Batterieeinspeisung" : sum(obj_Datatracker.Batterieeinspeisung),
            "Batterieentladung" : sum(obj_Datatracker.Batterieentladung),
            "Batterieverluste" : sum(obj_Datatracker.Batterieverluste)
            }
        self.total_costs = obj_Costs.total_costs
        self.emissions = obj_Gebäude.CO2_Gesamt
        self.prim_energy = obj_Gebäude.Prim_Gesamt 

        return result
#%%





def main():
    #this should work
    model = Model()
    result = model.Simulate(var_BGF=5000, var_PV_kWP=1, var_battery_kWh=1, verbose = False)
    print(f"Gesamtkosten: {result['Gesamtkosten']:.2f} €")
    print(f"Investmentkosten: {result['Investmentkosten']:.2f} €")
    print(f"Operationskosten: {result['Operationskosten']:.2f}")
    print(f"Emissionen: {result['Emissionen']:.2f} kgCO2/m²a")
    print(f"Primärenergie: {result['Primärenergie']:.2f} kWh/m²a")
    print(f"Netzeinspeisung: {result['Netzeinspeisung']:.2f} kWh")
    print(f"Netzbezug: {result['Netzbezug']:.2f} kWh")

if __name__ == "__main__":  # https://www.youtube.com/watch?v=sugvnHA7ElY
    main() 