# -*- coding: utf-8 -*-
import serial
import serial.tools.list_ports
import datetime
import os
import time
import winsound
import threading
import sys
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import json
import pystray
from PIL import Image, ImageDraw
from plyer import notification

# Postavke teme i izgleda (Black Night stil)
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

# Putanja za log - kreira mapu u Documents ako ne postoji
LOG_DIR = os.path.join(os.path.expanduser("~"), "Documents")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
LOG_PATH = os.path.join(LOG_DIR, "antena_master_log.txt")
CONFIG_PATH = os.path.join(LOG_DIR, "station_hub_config.json")

class StationHubApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("9A5CW - Station Hub (Antena Master & ASMC Controller)")
        self.geometry("750x590")
        self.resizable(False, False)
        self.configure(fg_color="#121212")

        # Postavljanje ikone (podržava i skriptu i kompajlirani .exe)
        # Postavljanje ikone (podržava i skriptu i kompajlirani .exe)
        try:
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(sys._MEIPASS, "hub.ico")
            else:
                icon_path = "hub.ico"
            self.iconbitmap(icon_path)
        except Exception:
            pass

        # Varijable za Antena Master
        self.ser_antena = None
        self.current_mode = "M"
        self.stanje_r1 = False
        self.stanje_r2 = False
        self.log_to_file = tk.BooleanVar(value=True)
        self.beep_enabled = tk.BooleanVar(value=True)
        self.show_log_window = tk.BooleanVar(value=True)

        # Varijable za ASMC StackMatch
        self.ser_asmc = None
        self.asmc_running = False
        self.rx_states = [False, False, False]
        self.tx_states = [False, False, False]
        self.ptt_active = False
        self.flex_mode = False

        # Kreiranje glavnih kartica (Tabs)
        self.tabview = ctk.CTkTabview(self, fg_color="#181818", segmented_button_fg_color="#222", segmented_button_selected_color="#2980b9")
        self.tabview.pack(padx=10, pady=10, fill="both", expand=True)

        self.tab_antena = self.tabview.add("Antena Master PRO")
        self.tab_asmc = self.tabview.add("ASMC 1-3 Controller")

        # Inicijalizacija sučelja za oba dijela
        self.setup_antena_tab()
        self.setup_asmc_tab()

        # Učitavanje spremljenih portova iz JSON-a, pokretanje GUI petlje i auto-osvježavanja
        self.ucitaj_postavke()
        self.update_antena_gui()
        self.after(2500, self.pokreni_automatsko_osvjezavanje_portova)

        self.log("=== SUSTAV POKRENUT (Unified Hub) ===")
    
    def prikazi_obavijest(self, naslov, poruka):
        """Prikazuje Windows pop-up (toast) obavijest u kutu ekrana."""
        try:
            notification.notify(
                title=naslov,
                message=poruka,
                app_name="Station Hub",
                timeout=2 # Trajanje obavijesti u sekundama
            )
        except Exception as e:
            print(f"Greška kod obavijesti: {e}")

    def sakrij_u_tray(self):
        """Sakriva glavni prozor i postavlja pravu ikonu u system tray."""
        self.withdraw() # Sakriva prozor aplikacije
        
        # Učitavamo pravu hub.ico ikonu za tray
        try:
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(sys._MEIPASS, "hub.ico")
            else:
                icon_path = "hub.ico"
            image = Image.open(icon_path)
        except Exception:
            # Fallback ako ikona slučajno nije pronađena
            image = Image.new('RGB', (64, 64), color=(18, 18, 18))

        # Definiramo izbornik kad se klikne desnim klikom na ikonu
        menu = pystray.Menu(
            pystray.MenuItem("Otvori Station Hub", self.otvori_iz_traya),
            pystray.MenuItem("Izlaz", self.ugasi_iz_traya)
        )

        self.tray_icon = pystray.Icon("StationHub", image, "9A5CW Station Hub", menu)
        
        # Pokrećemo tray u pozadinskoj dretvi
        import threading
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def otvori_iz_traya(self, icon, item):
        """Vraća prozor natrag na ekran iz system traya."""
        icon.stop()
        self.after(0, self.deiconify) # Prikazuje prozor ponovno

    def ugasi_iz_traya(self, icon, item):
        """Gasi aplikaciju preko tray izbornika."""
        icon.stop()
        self.after(0, self.close_event)
        
    def provjeri_zauzetost_portova(self):
        """Detektira sve COM portove, provjerava status i pokušava prepoznati tip uređaja (2in1 ili ASMC)."""
        dostupni_portovi = []
        detaljni_ispis = []

        ports = serial.tools.list_ports.comports()
        
        for port in ports:
            status_poruka = "SLOBODAN"
            uredaj_tip = "Nepoznat uređaj"
            
            # 1. Prvo provjeravamo je li port uopće zauzet od strane neke aplikacije
            try:
                test_ser = serial.Serial(port.device, 9600, timeout=0.5)
                test_ser.close()
            except (serial.SerialException, OSError):
                status_poruka = "ZAUZET / U UPOTREBI"
                
                # Ako je zauzet, pokušavamo pogoditi koji je naš uređaj prema opisu čipa ili nazivu u sustavu
                desc_lower = port.description.lower()
                if "ch340" in desc_lower or "arduino" in desc_lower:
                    # Ovdje možemo napraviti aktivni test ako je port otvoren unutar programa, 
                    # ili prepoznati prema vašoj uobičajenoj konfiguraciji portova.
                    pass

            # 2. Pametna identifikacija prema opisu proizvođača (Description)
            desc = port.description
            if "CH340" in desc or "FTDI" in desc:
                uredaj_tip = "Mogući Arduino / Kontroler"
            elif "CP210x" in desc:
                uredaj_tip = "Silicon Labs (Mogući Radio/Interface)"
            elif "Communications Port" in desc:
                uredaj_tip = "Serijski port (COM1)"

            # 3. Ako je naš uređaj trenutno spojen u programu, znamo točno tko je!
            if self.ser_antena and self.ser_antena.is_open and self.ser_antena.port == port.device:
                uredaj_tip = ">>> ANTENA MASTER PRO (2in1) [AKTIVAN] <<<"
            elif self.ser_asmc and self.ser_asmc.is_open and self.ser_asmc.port == port.device:
                uredaj_tip = ">>> ASMC 1-3 STACKMATCH [AKTIVAN] <<<"

            opis = f"{port.device} ({port.description}) - [{status_poruka}] -> {uredaj_tip}"
            detaljni_ispis.append(opis)
            dostupni_portovi.append(port.device)

        # Ispisujemo detaljan izvještaj u log prozor
        log_tekst = "--- PAMETNA IDENTIFIKACIJA COM PORTOVA ---\n" + ("\n".join(detaljni_ispis) if detaljni_ispis else "Niti jedan COM port nije pronađen.")
        self.log(log_tekst)
        
    def ucitaj_postavke(self):
        """Učitava spremljene COM portove iz JSON datoteke ako postoji."""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    antena_port = data.get("antena_port", "")
                    asmc_port = data.get("asmc_port", "")

                    # Postavi spremljene portove ako postoje u opcijama
                    if antena_port:
                        self.var_port_antena.set(antena_port)
                    if asmc_port:
                        self.port_combo_asmc.set(asmc_port)
            except Exception as e:
                print(f"Greška pri učitavanju konfiguracije: {e}")

    def spremi_postavke(self):
        """Sprema trenutno odabrane COM portove u JSON datoteku."""
        data = {
            "antena_port": self.var_port_antena.get(),
            "asmc_port": self.port_combo_asmc.get()
        }
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Greška pri spremanju konfiguracije: {e}")

    def pokreni_automatsko_osvjezavanje_portova(self):
        """Automatski provjerava i osvježava dostupne COM portove svakih 2.5 sekunde."""
        try:
            ports = serial.tools.list_ports.comports()
            dostupni_portovi = [p.device for p in ports] or ["COM3"]

            # 1. Ažuriranje izbornika za Antena Master PRO
            try:
                trenutni_antena = self.var_port_antena.get()
                self.option_port_antena.configure(values=dostupni_portovi)
                if trenutni_antena not in dostupni_portovi and dostupni_portovi:
                    self.var_port_antena.set(dostupni_portovi[0])
            except Exception:
                pass

            # 2. Ažuriranje izbornika za ASMC Controller
            try:
                trenutni_asmc = self.port_combo_asmc.get()
                self.port_combo_asmc.configure(values=dostupni_portovi)
                if trenutni_asmc not in dostupni_portovi and dostupni_portovi:
                    self.port_combo_asmc.set(dostupni_portovi[0])
            except Exception:
                pass
        except Exception:
            pass

        self.after(2500, self.pokreni_automatsko_osvjezavanje_portova)
             
    # ==========================================
    # DIO 1: ANTENA MASTER PRO
    # ==========================================
    def setup_antena_tab(self):
        top = ctk.CTkFrame(self.tab_antena, fg_color="#1e1e1e", corner_radius=10)
        top.pack(fill="x", padx=10, pady=10)

        ports = [p.device for p in serial.tools.list_ports.comports()] or ["COM3"]
        self.var_port_antena = tk.StringVar(value=ports[0])
        
        self.option_port_antena = ctk.CTkOptionMenu(top, variable=self.var_port_antena, values=ports, width=110, fg_color="#333333", button_color="#444444")
        self.option_port_antena.pack(side="left", padx=10, pady=10)

        self.btn_connect_antena = ctk.CTkButton(top, text="POVEŽI", command=self.connect_antena, width=90, fg_color="#34495e", hover_color="#2c3e50")
        self.btn_connect_antena.pack(side="left", padx=5, pady=10)

        self.btn_emergency = ctk.CTkButton(top, text="⚠ SAFETY", fg_color="#c0392b", hover_color="#962d22", text_color="white", font=("Arial", 11, "bold"), width=90, command=lambda: self.send_antena_cmd('0'))
        self.btn_emergency.pack(side="right", padx=10, pady=10)

        self.btn_help = ctk.CTkButton(top, text="Help", command=self.prikazi_help, width=70, fg_color="#d4ac0d", hover_color="#b7950b", text_color="black")
        self.btn_help.pack(side="right", padx=2, pady=10)
        # Gumb za provjeru zauzetosti portova (dodajte ga u 'top' frame)
        self.btn_provjeri_portove = ctk.CTkButton(top, text="Provjeri portove", command=self.provjeri_zauzetost_portova, width=110, fg_color="#16a085", hover_color="#1abc9c", text_color="white")
        self.btn_provjeri_portove.pack(side="left", padx=5, pady=10)
        
        cfg_frame = ctk.CTkFrame(self.tab_antena, fg_color="transparent")
        cfg_frame.pack(pady=2)
        ctk.CTkCheckBox(cfg_frame, text="Log File", variable=self.log_to_file, text_color="#ccc").pack(side="left", padx=10)
        ctk.CTkCheckBox(cfg_frame, text="Beep", variable=self.beep_enabled, text_color="#ccc").pack(side="left", padx=10)
        ctk.CTkCheckBox(cfg_frame, text="Show Log", variable=self.show_log_window, command=self.toggle_log_visibility, text_color="#ccc").pack(side="left", padx=10)

        self.lbl_status_antena = ctk.CTkLabel(self.tab_antena, text="STATUS: NIJE POVEZAN", text_color="grey", font=("Arial", 12, "bold"))
        self.lbl_status_antena.pack(pady=5)

        m_frame = ctk.CTkFrame(self.tab_antena, fg_color="#1e1e1e", corner_radius=10)
        m_frame.pack(pady=8, padx=10, fill="x")

        self.btn_auto1 = ctk.CTkButton(m_frame, text="AUTO 1 (X)", width=140, command=lambda: self.send_antena_cmd('X'), fg_color="#333", hover_color="#444")
        self.btn_auto1.pack(side="left", padx=10, pady=10)
        self.btn_auto2 = ctk.CTkButton(m_frame, text="AUTO 2 (Y)", width=140, command=lambda: self.send_antena_cmd('Y'), fg_color="#333", hover_color="#444")
        self.btn_auto2.pack(side="left", padx=5, pady=10)
        self.btn_manual = ctk.CTkButton(m_frame, text="MANUAL (M)", width=140, command=lambda: self.send_antena_cmd('M'), fg_color="#2980b9", hover_color="#1f618d")
        self.btn_manual.pack(side="left", padx=10, pady=10)

        ptt_frame = ctk.CTkFrame(self.tab_antena, fg_color="#181818", corner_radius=10)
        ptt_frame.pack(pady=5, padx=10, fill="x")

        self.lbl_ptt = ctk.CTkLabel(ptt_frame, text="○ PRIJEM (RX READY)", font=("Arial", 15, "bold"), text_color="#2ecc71")
        self.lbl_ptt.pack(pady=5)
        self.lbl_linear = ctk.CTkLabel(ptt_frame, text="LINEAR PTT: OFF", font=("Arial", 11, "bold"), text_color="grey")
        self.lbl_linear.pack(pady=2)

        self.btn1 = ctk.CTkButton(self.tab_antena, text="ANT1: OFF", fg_color="#27ae60", hover_color="#1e8449", text_color="white", font=("Arial", 12, "bold"), height=40, command=lambda: self.send_antena_cmd('2' if self.stanje_r1 else '1'))
        self.btn1.pack(pady=5, padx=10, fill="x")

        self.btn2 = ctk.CTkButton(self.tab_antena, text="ANT2: OFF", fg_color="#27ae60", hover_color="#1e8449", text_color="white", font=("Arial", 12, "bold"), height=40, command=lambda: self.send_antena_cmd('4' if self.stanje_r2 else '3'))
        self.btn2.pack(pady=5, padx=10, fill="x")

        self.log_display = ctk.CTkTextbox(self.tab_antena, width=700, height=130, font=("Consolas", 10), fg_color="#0a0a0a", text_color="#00ffcc")
        self.log_display.pack(pady=5, padx=10)
        self.log_display.configure(state="disabled")
    
    def connect_antena(self):
        try:
            if self.ser_antena:
                self.ser_antena.close()
            port = self.var_port_antena.get()
            self.ser_antena = serial.Serial(port, 9600, timeout=0.1)
            time.sleep(1.5)
            self.lbl_status_antena.configure(text=f"SPOJEN: {port}", text_color="#3498db")
            self.log(f"POVEZANO NA {port}")
            self.send_antena_cmd('M')
            self.spremi_postavke()
        except Exception:
            messagebox.showerror("Greška", "Antena Master port nedostupan!")

    def send_antena_cmd(self, char):
        if self.ser_antena and self.ser_antena.is_open:
            self.ser_antena.write(char.encode())

    def toggle_log_visibility(self):
        if self.show_log_window.get():
            self.log_display.pack(pady=5, padx=10)
        else:
            self.log_display.pack_forget()

    def update_antena_gui(self):
        if self.ser_antena and self.ser_antena.is_open:
            while self.ser_antena.in_waiting > 0:
                line = self.ser_antena.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    self.process_antena_line(line)
        self.after(50, self.update_antena_gui)

    def process_antena_line(self, l):
        if l in ["X", "Y", "M", "0"]:
            self.current_mode = l
            self.update_antena_mode_ui()
            self.log(f"POTVRDA MODA: {l}")
        elif l == "L":
            if self.beep_enabled.get():
                winsound.Beep(1000, 80)
            self.lbl_ptt.configure(text="● PREDAJA (TX)", text_color="#e74c3c")
            self.lbl_linear.configure(text="LINEAR: ACTIVE", text_color="#e74c3c")
            self.log("PTT -> TX")
        elif l == "U":
            if self.beep_enabled.get():
                winsound.Beep(600, 80)
            self.lbl_ptt.configure(text="○ PRIJEM (RX)", text_color="#2ecc71")
            self.lbl_linear.configure(text="LINEAR: OFF", text_color="grey")
            self.log("PTT -> RX")
        elif l == "A":
            self.stanje_r1 = True
            self.update_antena_vis(1)
            self.log("ANTENA 1: ON")
        elif l == "B":
            self.stanje_r1 = False
            self.update_antena_vis(1)
            self.log("ANTENA 1: OFF")
        elif l == "C":
            self.stanje_r2 = True
            self.update_antena_vis(2)
            self.log("ANTENA 2: ON")
        elif l == "D":
            self.stanje_r2 = False
            self.update_antena_vis(2)
            self.log("ANTENA 2: OFF")

    def update_antena_mode_ui(self):
        self.btn_auto1.configure(fg_color="#333333")
        self.btn_auto2.configure(fg_color="#333333")
        self.btn_manual.configure(fg_color="#333333")
        if self.current_mode == "X":
            self.btn_auto1.configure(fg_color="#d35400")
        elif self.current_mode == "Y":
            self.btn_auto2.configure(fg_color="#d35400")
        elif self.current_mode == "M":
            self.btn_manual.configure(fg_color="#2980b9")
        st = "normal" if self.current_mode == "M" else "disabled"
        self.btn1.configure(state=st)
        self.btn2.configure(state=st)

    def update_antena_vis(self, num):
        if num == 1:
            color = "#c0392b" if self.stanje_r1 else "#27ae60"
            hover = "#962d22" if self.stanje_r1 else "#1e8449"
            self.btn1.configure(fg_color=color, hover_color=hover, text=f"ANT1: {'ON' if self.stanje_r1 else 'OFF'}")
        else:
            color = "#c0392b" if self.stanje_r2 else "#27ae60"
            hover = "#962d22" if self.stanje_r2 else "#1e8449"
            self.btn2.configure(fg_color=color, hover_color=hover, text=f"ANT2: {'ON' if self.stanje_r2 else 'OFF'}")

    def zapisi_u_file(self, tekst):
        if not self.log_to_file.get():
            return
        vrijeme = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mod_ime = "MANUAL" if self.current_mode == "M" else ("AUTO1" if self.current_mode == "X" else "AUTO2")
        if self.current_mode == "0":
            mod_ime = "SAFETY"
        antene = f"A1:{'ON' if self.stanje_r1 else 'OFF'}|A2:{'ON' if self.stanje_r2 else 'OFF'}"
        linija = f"[{vrijeme}] [MOD:{mod_ime}] [{antene}] {tekst}\n"
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(linija)
        except Exception:
            pass

    def log(self, tekst):
        v = datetime.datetime.now().strftime("%H:%M:%S")
        try:
            self.log_display.configure(state="normal")
            self.log_display.insert("end", f"[{v}] {tekst}\n")
            self.log_display.see("end")
            self.log_display.configure(state="disabled")
        except Exception:
            pass
        self.zapisi_u_file(tekst)

    def prikazi_help(self):
        h = ctk.CTkToplevel(self)
        h.title("Antena Master PRO v5.2.5 - Dokumentacija")
        h.geometry("620x620")
        h.configure(fg_color="#121212")
        
        # Postavljanje ikone na help prozor
        try:
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(sys._MEIPASS, "hub.ico")
            else:
                icon_path = "hub.ico"
            h.iconbitmap(icon_path)
        except Exception:
            pass

        txt_area = ctk.CTkTextbox(h, font=("Consolas", 11), fg_color="#0a0a0a", text_color="#ffffff")
        upute = """      ANTENA MASTER PRO v5.2.5 - TEHNIČKA DOKUMENTACIJA
============================================================
Operater: 9A5CW | Sustav: Antena Sequencer & Diversity Switch

1. HARDVERSKI PINOUT (ARDUINO NANO/UNO):
------------------------------------------------------------
[D02] PTT ULAZ         - Aktivni LOW (GND iz radija)
[D03] RUČNA TIPKA 1    - Tipkalo Antena 1 (Manual Mode)
[D04] RUČNA TIPKA 2    - Tipkalo Antena 2 (Manual Mode)
[D05] MODE TIPKA       - Fizička promjena moda (1x, 2x, 3x)
[D06] LINEAR PTT OUT   - Izlaz za pojačalo (Sequencer)
[D07] RELEJ 1          - Kontrola releja za Antenu 1
[D08] RELEJ 2          - Kontrola releja za Antenu 2
[D09] LED ZELENA       - Status Antene 1
[D10] LED CRVENA       - Status Antene 2
[D11] LED PLAVA        - Vizualni CW monitor (Sidetone)

2. MODOVI RADA:
------------------------------------------------------------
[M] MANUAL MODE: Ručna kontrola, Diversity podržan.
[X] AUTO MODE 1: RX: Antena 1, TX: Antena 2.
[Y] AUTO MODE 2: RX: Antena 2, TX: Antena 1.
[0] RF SAFETY  : Isključuje sve releje i linear.

3. CW SEQUENCER TAJMING (OPTIMIZIRANO):
------------------------------------------------------------
- TX SEQ: Antena ON -> 20 ms pauza -> Linear ON
- RX SEQ: Linear OFF -> 10 ms pauza -> Antena RX

4. SERIJSKE KOMANDE (PC -> ARD):
------------------------------------------------------------
'X' : Auto 1  | 'Y' : Auto 2 | 'M' : Manual | '0' : Safety
'1'/'2' : Antena 1 ON/OFF | '3'/'4' : Antena 2 ON/OFF
============================================================
                        73 de 9A5CW
"""
        txt_area.insert("end", upute)
        txt_area.configure(state="disabled")
        txt_area.pack(expand=True, fill="both", padx=15, pady=15)
        
        ctk.CTkButton(h, text="Zatvori", command=h.destroy, fg_color="#444", hover_color="#555").pack(pady=10)

    # ==========================================
    # DIO 2: ASMC 1-3 STACKMATCH CONTROLLER
    # ==========================================
    def setup_asmc_tab(self):
        conn_frame = ctk.CTkFrame(self.tab_asmc, fg_color="#1e1e1e", corner_radius=10)
        conn_frame.pack(padx=10, pady=10, fill="x")
        # Gumb za provjeru portova na ASMC kartici
                
        ctk.CTkLabel(conn_frame, text="COM Port:", font=("Arial", 12, "bold")).pack(side="left", padx=10, pady=10)
        self.connect_btn_asmc = ctk.CTkButton(conn_frame, text="Poveži", fg_color="green", hover_color="darkgreen", command=self.toggle_asmc_connection)
        self.connect_btn_asmc.pack(side="right", padx=15, pady=10)
        
        ports = [p.device for p in serial.tools.list_ports.comports()] or ["COM3"]
        self.port_combo_asmc = ctk.CTkComboBox(conn_frame, values=ports)
        self.port_combo_asmc.pack(side="left", padx=10, pady=10)
        if ports:
            self.port_combo_asmc.set(ports[0])
                
        refresh_btn_check = ctk.CTkButton(conn_frame, text="Provjeri portove", command=self.provjeri_zauzetost_portova, width=110, fg_color="#16a085", hover_color="#1abc9c", text_color="white")
        refresh_btn_check.pack(side="left", padx=5, pady=10)
        
        refresh_btn = ctk.CTkButton(conn_frame, text="Osvježi", width=80, command=self.update_asmc_ports, fg_color="#333")
        refresh_btn.pack(side="left", padx=5, pady=10)

        

        main_frame = ctk.CTkFrame(self.tab_asmc, fg_color="transparent")
        main_frame.pack(padx=10, pady=5, fill="both", expand=True)

        ant_names = ["Antena A (TOP)", "Antena B (MID)", "Antena C (BOT)"]

        # RX Stupac
        rx_frame = ctk.CTkFrame(main_frame, fg_color="#181818")
        rx_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(rx_frame, text="RX (Prijem)", font=("Arial", 12, "bold")).pack(pady=(10, 5))

        self.rx_btns = []
        for i in range(3):
            btn = ctk.CTkButton(rx_frame, text=ant_names[i], width=150, height=40, font=("Arial", 11, "bold"), fg_color="gray30", command=lambda idx=i: self.send_rx_toggle(idx))
            btn.pack(padx=15, pady=6)
            self.rx_btns.append(btn)

        ctk.CTkButton(rx_frame, text="ODABERI SVE", width=150, height=35, fg_color="#1f538d", command=lambda: self.send_asmc_cmd("SET:111")).pack(padx=15, pady=10)

        # TX Stupac
        tx_frame = ctk.CTkFrame(main_frame, fg_color="#181818")
        tx_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        ctk.CTkLabel(tx_frame, text="TX (Predaja)", font=("Arial", 12, "bold")).pack(pady=(10, 5))

        self.tx_btns = []
        for i in range(3):
            btn = ctk.CTkButton(tx_frame, text=ant_names[i], width=150, height=40, font=("Arial", 11, "bold"), fg_color="gray30", command=lambda idx=i: self.send_tx_toggle(idx))
            btn.pack(padx=15, pady=6)
            self.tx_btns.append(btn)

        ctk.CTkButton(tx_frame, text="ODABERI SVE", width=150, height=35, fg_color="#1f538d", command=lambda: self.send_asmc_cmd("SETTX:111")).pack(padx=15, pady=10)

        # Statusi i mod
        status_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        status_frame.grid(row=0, column=2, padx=10, pady=10, sticky="nsew")

        self.ptt_indicator = ctk.CTkLabel(status_frame, text="PTT: RX", width=140, height=50, font=("Arial", 14, "bold"), fg_color="green", text_color="white", corner_radius=8)
        self.ptt_indicator.pack(pady=15)

        self.mode_label = ctk.CTkLabel(status_frame, text="Mod rada: EXCLUSIVE", font=("Arial", 11))
        self.mode_label.pack(pady=5)

        ctk.CTkButton(status_frame, text="PROMIJENI MOD", width=140, height=40, fg_color="purple", hover_color="#512e5f", command=lambda: self.send_asmc_cmd("TOGGLE_MODE")).pack(pady=10)

        main_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.statusbar_asmc = ctk.CTkLabel(self.tab_asmc, text="Status: Nije povezano", anchor="w", font=("Arial", 11))
        self.statusbar_asmc.pack(side="bottom", fill="x", padx=10, pady=5)

    def update_asmc_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo_asmc.configure(values=ports)
        if ports:
            self.port_combo_asmc.set(ports[0])

    def toggle_asmc_connection(self):
        if self.ser_asmc and self.ser_asmc.is_open:
            self.asmc_running = False
            try:
                self.ser_asmc.close()
            except Exception:
                pass
            self.connect_btn_asmc.configure(text="Poveži se", fg_color="green", hover_color="darkgreen")
            self.statusbar_asmc.configure(text="Status: Veza prekinuta.")
        else:
            selected_port = self.port_combo_asmc.get()
            if not selected_port:
                return
            try:
                self.ser_asmc = serial.Serial(selected_port, 9600, timeout=0.1)
                self.asmc_running = True
                self.connect_btn_asmc.configure(text="Prekini vezu", fg_color="red", hover_color="darkred")
                self.statusbar_asmc.configure(text=f"Status: Povezan na {selected_port}")
                threading.Thread(target=self.read_from_asmc_arduino, daemon=True).start()
                self.spremi_postavke()
            except Exception as e:
                self.statusbar_asmc.configure(text=f"Greška: {str(e)}")

    def read_from_asmc_arduino(self):
        while self.asmc_running:
            if self.ser_asmc and self.ser_asmc.is_open:
                try:
                    if self.ser_asmc.in_waiting > 0:
                        line = self.ser_asmc.readline().decode("utf-8", errors="ignore").strip()
                        if line.startswith("RX:"):
                            self.parse_asmc_status(line)
                except Exception:
                    break
            time.sleep(0.02)

    def parse_asmc_status(self, data_str):
        try:
            parts = data_str.split(" ")
            if len(parts) >= 4:
                rx_part = parts[0].split(":")[1]
                tx_part = parts[1].split(":")[1]
                ptt_part = parts[2].split(":")[1]
                mod_part = parts[3].split(":")[1]

                self.rx_states = [char == "1" for char in rx_part]
                self.tx_states = [char == "1" for char in tx_part]
                self.ptt_active = ptt_part == "TX"
                self.flex_mode = mod_part == "FLEX"

                self.after(0, self.update_asmc_gui_elements)
        except Exception:
            pass

    def update_asmc_gui_elements(self):
        for i in range(3):
            color = "#2ecc71" if self.rx_states[i] else "gray30"
            self.rx_btns[i].configure(fg_color=color)
        for i in range(3):
            color = "#e67e22" if self.tx_states[i] else "gray30"
            self.tx_btns[i].configure(fg_color=color)

        if self.ptt_active:
            self.ptt_indicator.configure(text="PTT: TRANSMIT", fg_color="red")
        else:
            self.ptt_indicator.configure(text="PTT: RECEIVE", fg_color="green")

        if self.flex_mode:
            self.mode_label.configure(text="Mod rada: FLEXIBLE (Multi)")
        else:
            self.mode_label.configure(text="Mod rada: EXCLUSIVE (Single)")

    def send_asmc_cmd(self, cmd):
        if self.ser_asmc and self.ser_asmc.is_open:
            try:
                self.ser_asmc.write((cmd + "\n").encode("utf-8"))
            except Exception:
                pass

    def send_rx_toggle(self, index):
        new_rx = list(self.rx_states)
        if self.flex_mode:
            new_rx[index] = not new_rx[index]
        else:
            new_rx = [False, False, False]
            new_rx[index] = True
        self.send_asmc_cmd("SET:" + "".join(["1" if x else "0" for x in new_rx]))

    def send_tx_toggle(self, index):
        new_tx = list(self.tx_states)
        new_tx[index] = not new_tx[index]
        self.send_asmc_cmd("SETTX:" + "".join(["1" if x else "0" for x in new_tx]))

    def close_event(self):
        """Ova metoda se poziva kada stvarno gasimo aplikaciju (zatvara portove i gasi proces)."""
        self.asmc_running = False
        for s in [self.ser_antena, self.ser_asmc]:
            if s and s.is_open:
                try:
                    s.close()
                except Exception:
                    pass
        try:
            if hasattr(self, 'tray_icon') and self.tray_icon:
                self.tray_icon.stop()
        except Exception:
            pass
        self.destroy()
        sys.exit(0)

    def ugasi_iz_traya(self, icon, item):
        """Gasi aplikaciju preko tray izbornika."""
        icon.stop()
        self.after(0, self.close_event)
        

if __name__ == "__main__":
    app = StationHubApp()
    # Umjesto starog protokola za brisanje, stavljamo da X sakriva u tray:
    app.protocol("WM_DELETE_WINDOW", app.sakrij_u_tray)
    app.mainloop()