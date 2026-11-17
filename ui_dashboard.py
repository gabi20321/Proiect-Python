import os
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from PIL import Image, ImageDraw
from collections import Counter

from config import THEME, BASE_DIR
from database import get_all_tracks, search_local_tracks
from providers import search_online_catalog, ensure_initial_catalog
from engine import recommend_for_user
import auth


class ToolTip:
    def __init__(self, widget, text: str):#configurare caseta text informativa la hover
        self.widget, self.text, self.tip_win, self.after_id = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _=None):#programare afisare cu intarziere
        self._cancel()
        self.after_id = self.widget.after(450, self._show)

    def _cancel(self):#anulare cronometru afisare
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def _show(self):#creare si afisare fereastra tooltip
        if self.tip_win or not self.text or not self.widget.winfo_exists():
            return
        x, y = self.widget.winfo_rootx() + 10, self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip_win = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, bg=THEME["bg_input"], fg=THEME["text_main"], font=(THEME["font"], 9),
                 padx=8, pady=4, relief="solid", borderwidth=1, wraplength=260, justify="left").pack()

    def _hide(self, _=None):#ascundere si distrugere fereastra tooltip
        self._cancel()
        if self.tip_win:
            self.tip_win.destroy()
            self.tip_win = None


class HalfStarRating(tk.Canvas):
    def __init__(self, parent, on_change=None):#initializare selector nota cu jumatati de stea
        super().__init__(parent, width=190, height=34, bg=THEME["bg_card"], highlightthickness=0, cursor="hand2")
        self.on_change, self.half_stars, self.hover_half = on_change, 0, None
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._redraw()

    def set_value(self, half_stars: int):#setare nota curenta
        self.half_stars = max(0, min(10, int(half_stars or 0)))
        self._redraw()

    def _calc(self, x: int) -> int:#calculare numar jumatati de stea dupa pozitia mouse-ului
        return 0 if x < 10 else max(1, min(10, int(((x - 10) / 17.0) + 1)))

    def _on_motion(self, e):#actualizare afisare cand misti mouse-ul peste stele
        if (h := self._calc(e.x)) != self.hover_half:
            self.hover_half = h
            self._redraw()

    def _on_leave(self, _):#revenire la nota salvata cand iei mouse-ul
        self.hover_half = None
        self._redraw()

    def _on_click(self, e):#salvare nota cand dai click
        c = self._calc(e.x)
        self.half_stars = 0 if c == self.half_stars else c
        self._redraw()
        if self.on_change:
            self.on_change(self.half_stars)

    def _redraw(self):#desenare stele pe canvas
        self.delete("all")
        val = self.hover_half if self.hover_half is not None else self.half_stars
        for i in range(5):
            cx, full_t, half_t = 10 + i * 34, (i + 1) * 2, i * 2 + 1
            self.create_text(cx, 17, text="*", anchor="w", font=(THEME["font"], 22, "bold"), fill=THEME["border"])
            if val >= full_t:
                self.create_text(cx, 17, text="*", anchor="w", font=(THEME["font"], 22, "bold"), fill=THEME["accent"])
            elif val == half_t:
                self.create_text(cx, 17, text="*", anchor="w", font=(THEME["font"], 22, "bold"), fill=THEME["accent"])
                self.create_rectangle(cx + 9, 2, cx + 26, 32, fill=THEME["bg_card"], outline="")


class DashboardUI:
    def __init__(self, root: ctk.CTk, current_user: str, on_logout):#configurare fereastra principala dashboard
        self.root, self.current_user, self.on_logout = root, current_user, on_logout
        self.user_obj = auth.get_user_by_username(current_user) or {"id": 1, "username": current_user, "email": "", "avatar_path": ""}
        self.user_id = self.user_obj["id"]

        self.root.title(f"Musicmeter v2 - {self.current_user}")
        self.root.geometry("1240x768")
        self.root.minsize(900, 600)
        self.root.configure(fg_color=THEME["bg_main"])

        self.current_view, self.library_filter = "explore", "favorites"
        self.current_tracks, self.selected_track, self.current_half_stars = [], None, 0
        self.image_cache, self.card_registry, self.lazy_slots = {}, {}, []
        self._lazy_after_id, self.last_cols = None, 0
        self._search_after_id = None
        self._resize_after_id = None
        self.placeholder_img = self._build_placeholder_ctk((140, 140))

        self.build_shell()
        self._setup_smooth_scroll()
        threading.Thread(target=self._init_catalog_bg, daemon=True).start()

    def _build_placeholder_ctk(self, size):#creare imagine implicita pt posterele fara coperta
        img = Image.new("RGB", size, THEME["bg_header"])
        cx, cy = size[0] // 2, size[1] // 2
        ImageDraw.Draw(img).ellipse((cx - 18, cy - 18, cx + 18, cy + 18), outline=THEME["border"], width=2)
        return ctk.CTkImage(light_image=img, dark_image=img, size=size)

    def _init_catalog_bg(self):#incarcare catalog initial in fundal
        ensure_initial_catalog()
        self.root.after(0, self.show_explore_view)

    def build_shell(self):#construire bara de sus si structura paginii
        nav = ctk.CTkFrame(self.root, height=64, fg_color=THEME["bg_header"], corner_radius=0, border_width=1, border_color=THEME["border"])
        nav.pack(fill="x", side="top")
        nav_in = ctk.CTkFrame(nav, fg_color="transparent")
        nav_in.pack(fill="x", padx=24, pady=12)

        #logo aplicatie
        brand = ctk.CTkFrame(nav_in, fg_color="transparent")
        brand.pack(side="left", padx=(0, 24))
        ctk.CTkLabel(brand, text="o", text_color=THEME["accent"], font=(THEME["font"], 18, "bold")).pack(side="left")
        ctk.CTkLabel(brand, text=" MUSICMETER", text_color=THEME["text_main"], font=(THEME["font"], 15, "bold")).pack(side="left", padx=(4, 0))

        #butoane meniu navigare
        self.nav_buttons = {}
        for k, text in [("explore", "EXPLOREAZA"), ("foryou", "PENTRU TINE"), ("library", "BIBLIOTECA"), ("profile", "PROFIL")]:
            btn = ctk.CTkButton(nav_in, text=text, width=108, height=36, corner_radius=8, fg_color="transparent",
                                hover_color=THEME["bg_card_hover"], text_color=THEME["text_muted"],
                                font=(THEME["font"], 12, "bold"), command=lambda key=k: self.switch_tab(key))
            btn.pack(side="left", padx=4)
            self.nav_buttons[k] = btn

        #buton deconectare si avatar
        ctk.CTkButton(nav_in, text="IESIRE", width=72, height=36, corner_radius=8, fg_color=THEME["bg_card"],
                      hover_color=THEME["danger"], text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold"),
                      command=self.on_logout).pack(side="right", padx=(8, 0))

        self.nav_avatar_lbl = ctk.CTkLabel(nav_in, text="", cursor="hand2")
        self.nav_avatar_lbl.pack(side="right", padx=8)
        self.nav_avatar_lbl.bind("<Button-1>", lambda _: self.switch_tab("profile"))
        self.refresh_avatar_widgets()

        #bara de cautare si buton cautare online
        self.search_btn = ctk.CTkButton(nav_in, text="Cauta Online", width=104, height=36, corner_radius=8,
                                        fg_color=THEME["accent"], hover_color=THEME["accent_hover"], text_color="#000000",
                                        font=(THEME["font"], 12, "bold"), command=self.trigger_online_search)
        self.search_btn.pack(side="right", padx=8)

        self.search_entry = ctk.CTkEntry(nav_in, width=240, height=36, corner_radius=8, fg_color=THEME["bg_input"],
                                         border_color=THEME["border"], text_color=THEME["text_main"],
                                         placeholder_text="Cauta piesa, artist, gen...")
        self.search_entry.pack(side="right", padx=4)
        self.search_entry.bind("<KeyRelease>", self.on_live_search_key)
        self.search_entry.bind("<Return>", lambda _: self.trigger_online_search())
        self.search_entry.bind("<FocusIn>", lambda _: self.search_entry.configure(border_color=THEME["accent"]))
        self.search_entry.bind("<FocusOut>", lambda _: self.search_entry.configure(border_color=THEME["border"]))

        #zona principala cu panoul de detalii in dreapta si grila in stanga
        self.body = ctk.CTkFrame(self.root, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=24, pady=16)

        self.inspector = ctk.CTkFrame(self.body, width=328, fg_color=THEME["bg_header"], corner_radius=16,
                                      border_width=1, border_color=THEME["border"])
        self.inspector.pack(side="right", fill="y", padx=(16, 0))
        self.inspector.pack_propagate(False)
        self.build_track_inspector()

        self.left_panel = ctk.CTkFrame(self.body, fg_color="transparent")
        self.left_panel.pack(side="left", fill="both", expand=True)

        self.header_bar = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.header_bar.pack(fill="x", pady=(0, 8))
        self.section_title = ctk.CTkLabel(self.header_bar, text="EXPLOREAZA CATALOGUL", text_color=THEME["text_main"], font=(THEME["font"], 14, "bold"))
        self.section_title.pack(side="left")
        self.section_subtitle = ctk.CTkLabel(self.header_bar, text="", text_color=THEME["text_muted"], font=(THEME["font"], 12))
        self.section_subtitle.pack(side="right")

        self.sub_filter_bar = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.divider_line = ctk.CTkFrame(self.left_panel, height=1, fg_color=THEME["border"])
        self.divider_line.pack(fill="x", pady=(0, 12))

        #canvas scrollabil pt afisarea cardurilor
        self.scroll_host = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        self.scroll_host.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.scroll_host, bg=THEME["bg_main"], highlightthickness=0, bd=0, yscrollincrement=24)
        self.scrollbar = ctk.CTkScrollbar(self.scroll_host, orientation="vertical", command=self._on_scrollbar_drag,
                                          fg_color="transparent", button_color=THEME["border"], button_hover_color=THEME["accent"])
        self.content_inner = ctk.CTkFrame(self.canvas, fg_color=THEME["bg_main"], corner_radius=0)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y", padx=(4, 0))

        self.content_inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_scrollbar_drag(self, *args):#miscare scroll si incarcare imagini vizibile
        self.canvas.yview(*args)
        self._schedule_lazy_load()

    def _on_inner_configure(self, _):#actualizare dimensiune zona de scroll
        if bbox := self.canvas.bbox("all"):
            self.canvas.configure(scrollregion=(0, 0, bbox[2], max(self.canvas.winfo_height(), bbox[3] - bbox[1])))

    def _on_canvas_configure(self, event):#rearanjare coloane la redimensionarea ferestrei
        self.canvas.itemconfig(self.canvas_window, width=event.width)
        if self.current_view in ("explore", "foryou", "library") and self.current_tracks:
            new_cols = max(2, event.width // 176)
            if new_cols != self.last_cols:
                if self._resize_after_id:
                    self.root.after_cancel(self._resize_after_id)
                self._resize_after_id = self.root.after(150, lambda: self.render_poster_grid(self.current_tracks))

    def _setup_smooth_scroll(self):#configurare scroll din rotita mouse-ului
        def _in_canvas(w) -> bool:
            while w is not None:
                if w in (self.scroll_host, self.canvas):
                    return True
                if w == self.inspector:
                    return False
                w = getattr(w, "master", None)
            return False

        def _on_wheel(e):
            if not _in_canvas(e.widget):
                return "break"
            top, bottom = self.canvas.yview()
            if top <= 0.0 and bottom >= 1.0:
                return "break"
            units = -3 if e.num == 4 else (3 if e.num == 5 else (-int(e.delta / 120) * 3 if abs(e.delta) >= 120 else (-1 if e.delta > 0 else 1)))
            if (units < 0 and top <= 0.0) or (units > 0 and bottom >= 1.0):
                return "break"
            self.canvas.yview_scroll(units, "units")
            self._schedule_lazy_load()
            return "break"

        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, _on_wheel)

    def refresh_avatar_widgets(self):#actualizare poza de profil in bara de sus
        self.user_obj = auth.get_user_by_username(self.current_user) or self.user_obj
        pil_nav = auth.build_circular_avatar_pil(self.user_obj, 34)
        self.nav_avatar_ctk = ctk.CTkImage(light_image=pil_nav, dark_image=pil_nav, size=(34, 34))
        self.nav_avatar_lbl.configure(image=self.nav_avatar_ctk)

    def build_track_inspector(self):#construire panou lateral cu detaliile piesei selectate
        self.cover_box = ctk.CTkLabel(self.inspector, text="NO COVER", width=200, height=200, fg_color=THEME["bg_card"],
                                      corner_radius=12, font=(THEME["font"], 16, "bold"), text_color=THEME["text_muted"])
        self.cover_box.pack(pady=(16, 12))

        self.lbl_title = ctk.CTkLabel(self.inspector, text="Selecteaza o piesa", text_color=THEME["text_main"],
                                      font=(THEME["font"], 15, "bold"), wraplength=280, justify="center")
        self.lbl_title.pack(pady=(0, 2), padx=12)

        self.lbl_artist = ctk.CTkLabel(self.inspector, text="Click pe orice card din grila", text_color=THEME["accent"],
                                       font=(THEME["font"], 12, "bold"), wraplength=280, justify="center")
        self.lbl_artist.pack(pady=(0, 6), padx=12)

        self.lbl_meta = ctk.CTkLabel(self.inspector, text="", text_color=THEME["text_sub"],
                                     font=(THEME["font"], 11), wraplength=280, justify="center")
        self.lbl_meta.pack(pady=(0, 8), padx=12)

        self.tags_frame = ctk.CTkFrame(self.inspector, fg_color="transparent")
        self.tags_frame.pack(pady=(0, 10))

        #butoane actiune like, exclude si lista de ascultat
        act_row = ctk.CTkFrame(self.inspector, fg_color="transparent")
        act_row.pack(pady=(0, 12))
        self.btn_like = ctk.CTkButton(act_row, text="Like", width=92, height=34, corner_radius=8, fg_color=THEME["bg_card"],
                                      hover_color=THEME["accent_hover"], text_color=THEME["text_main"], font=(THEME["font"], 11, "bold"),
                                      command=lambda: self._toggle_flag("like"))
        self.btn_like.pack(side="left", padx=4)

        self.btn_dislike = ctk.CTkButton(act_row, text="Exclude", width=88, height=34, corner_radius=8, fg_color=THEME["bg_card"],
                                         hover_color=THEME["danger_hover"], text_color=THEME["text_main"], font=(THEME["font"], 11, "bold"),
                                         command=lambda: self._toggle_flag("dislike"))
        self.btn_dislike.pack(side="left", padx=4)

        self.btn_watch = ctk.CTkButton(act_row, text="+ Lista", width=80, height=34, corner_radius=8, fg_color=THEME["bg_card"],
                                       hover_color=THEME["bg_card_hover"], text_color=THEME["text_main"], font=(THEME["font"], 11, "bold"),
                                       command=lambda: self._toggle_flag("watch"))
        self.btn_watch.pack(side="left", padx=4)

        #sectiune acordare stele si recenzie text
        rating_box = ctk.CTkFrame(self.inspector, fg_color=THEME["bg_card"], corner_radius=12)
        rating_box.pack(fill="x", padx=16, pady=(0, 12))
        self.lbl_rating_val = ctk.CTkLabel(rating_box, text="RATINGUL TAU: Fara nota", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold"))
        self.lbl_rating_val.pack(pady=(6, 2))
        self.star_widget = HalfStarRating(rating_box, on_change=self.on_star_rating_changed)
        self.star_widget.pack(pady=(0, 6))

        ctk.CTkLabel(self.inspector, text="RECENZIE PERSONALA", text_color=THEME["text_sub"], font=(THEME["font"], 10, "bold")).pack(anchor="w", padx=18, pady=(0, 4))
        self.review_text = ctk.CTkTextbox(self.inspector, height=68, fg_color=THEME["bg_input"], border_width=1,
                                          border_color=THEME["border"], text_color=THEME["text_main"], corner_radius=8)
        self.review_text.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkButton(self.inspector, text="Salveaza Recenzia & Nota", height=34, corner_radius=8, fg_color=THEME["accent"],
                      hover_color=THEME["accent_hover"], text_color="#000000", font=(THEME["font"], 12, "bold"),
                      command=self.save_review_and_rating).pack(fill="x", padx=16, pady=(0, 12))

    def switch_tab(self, tab_key: str):#schimbare pagina activa din meniu
        self.current_view = tab_key
        for k, btn in self.nav_buttons.items():
            btn.configure(fg_color=THEME["accent"] if k == tab_key else "transparent",
                          text_color="#000000" if k == tab_key else THEME["text_muted"],
                          hover_color=THEME["accent_hover"] if k == tab_key else THEME["bg_card_hover"])
        self.sub_filter_bar.pack_forget()
        {"explore": self.show_explore_view, "foryou": self.show_foryou_view,
         "library": self.show_library_view, "profile": self.show_profile_view}[tab_key]()

    def clear_content(self):#stergere carduri afisate si resetare scroll
        self.lazy_slots.clear()
        self.card_registry.clear()
        for w in self.content_inner.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)

    def show_explore_view(self):#afisare toate piesele din catalog
        self.current_view = "explore"
        self.switch_tab_visual("explore")
        self.current_tracks = get_all_tracks()
        self.section_title.configure(text="EXPLOREAZA CATALOGUL")
        self.section_subtitle.configure(text=f"{len(self.current_tracks)} piese")
        self.render_poster_grid(self.current_tracks, "Catalogul este gol momentan",
                                "Foloseste bara de cautare de sus si apasa Enter pentru a aduce piese noi.")

    def switch_tab_visual(self, tab_key: str):#evidentiere buton activ in meniu
        for k, btn in self.nav_buttons.items():
            btn.configure(fg_color=THEME["accent"] if k == tab_key else "transparent",
                          text_color="#000000" if k == tab_key else THEME["text_muted"])

    def show_foryou_view(self):#afisare pagina cu recomandari personalizate
        self.current_view = "foryou"
        self.current_tracks = recs = recommend_for_user(self.user_id, top_k=24)
        self.section_title.configure(text="RECOMANDATE PENTRU TINE")
        self.section_subtitle.configure(text=f"{len(recs)} recomandari personalizate")
        self.render_poster_grid(recs, "Nu avem inca suficiente date pentru recomandari",
                                "Marcheaza cateva piese ca Favorite sau acorda minim 3.5 stele in Exploreaza!",
                                "Mergi la Exploreaza", lambda: self.switch_tab("explore"))

    def show_library_view(self, sub_tab: str = None):#afisare biblioteca utilizatorului pe categorii
        self.current_view = "library"
        if sub_tab:
            self.library_filter = sub_tab
        for w in self.sub_filter_bar.winfo_children():
            w.destroy()
        self.sub_filter_bar.pack(fill="x", pady=(0, 8), before=self.divider_line)

        lib = auth.get_user_library(self.user_id)
        for key, label in [("favorites", f"Favorite ({len(lib['favorites'])})"),
                           ("watchlist", f"+ Lista de ascultat ({len(lib['watchlist'])})"),
                           ("reviewed", f"Evaluate ({len(lib['reviewed'])})"),
                           ("excluded", f"Excluse ({len(lib['excluded'])})")]:
            act = self.library_filter == key
            ctk.CTkButton(self.sub_filter_bar, text=label, height=32, corner_radius=8,
                          fg_color=THEME["accent"] if act else THEME["bg_card"],
                          text_color="#000000" if act else THEME["text_sub"],
                          hover_color=THEME["accent_hover"] if act else THEME["bg_card_hover"],
                          font=(THEME["font"], 12, "bold"), command=lambda k=key: self.show_library_view(k)).pack(side="left", padx=(0, 8))

        self.current_tracks = selected = lib.get(self.library_filter, [])
        meta = {
            "favorites": ("BIBLIOTECA - PIESE FAVORITE", "Nu ai inca piese favorite", "Apasa pe 'Like' in dreptul pieselor preferate pentru a le salva aici."),
            "watchlist": ("BIBLIOTECA - LISTA DE ASCULTAT", "Lista ta de ascultat este goala", "Foloseste butonul '+ Lista' pentru a salva piese pe care vrei sa le asculti."),
            "reviewed": ("BIBLIOTECA - PIESE EVALUATE", "Nu ai evaluat nicio piesa inca", "Acorda stele sau scrie o recenzie in panoul din dreapta."),
            "excluded": ("BIBLIOTECA - PIESE EXCLUSE", "Nu ai exclus nicio piesa", "Piesele marcate cu 'Exclude' apar aici si sunt evitate la recomandari."),
        }[self.library_filter]
        self.section_title.configure(text=meta[0])
        self.section_subtitle.configure(text=f"{len(selected)} piese")
        self.render_poster_grid(selected, meta[1], meta[2], "Exploreaza Catalogul", lambda: self.switch_tab("explore"))

    def show_profile_view(self):#afisare pagina de profil cu statistici si recenzii
        self.current_view, self.current_tracks = "profile", []
        self.clear_content()
        stats, lib = auth.get_user_profile_stats(self.user_id), auth.get_user_library(self.user_id)
        self.user_obj = auth.get_user_by_username(self.current_user) or self.user_obj

        self.section_title.configure(text="CONTUL SI STATISTICILE TALE")
        self.section_subtitle.configure(text=f"Membru din {self.user_obj.get('created_at', '2026')}")

        #antet profil cu poza si date utilizator
        prof_header = ctk.CTkFrame(self.content_inner, fg_color=THEME["bg_header"], corner_radius=12, border_width=1, border_color=THEME["border"])
        prof_header.pack(fill="x", padx=8, pady=(0, 16))
        pil_av = auth.build_circular_avatar_pil(self.user_obj, 88)
        self.prof_avatar_ctk = ctk.CTkImage(light_image=pil_av, dark_image=pil_av, size=(88, 88))
        ctk.CTkLabel(prof_header, image=self.prof_avatar_ctk, text="").pack(side="left", padx=24, pady=16)

        u_info = ctk.CTkFrame(prof_header, fg_color="transparent")
        u_info.pack(side="left", pady=16)
        ctk.CTkLabel(u_info, text=self.current_user, text_color=THEME["text_main"], font=(THEME["font"], 20, "bold")).pack(anchor="w")
        ctk.CTkLabel(u_info, text=self.user_obj.get("email") or "Email verificat", text_color=THEME["text_muted"], font=(THEME["font"], 12)).pack(anchor="w", pady=(2, 8))

        btn_row = ctk.CTkFrame(u_info, fg_color="transparent")
        btn_row.pack(anchor="w")
        ctk.CTkButton(btn_row, text="Schimba poza", width=124, height=32, corner_radius=8, fg_color=THEME["accent"],
                      hover_color=THEME["accent_hover"], text_color="#000000", font=(THEME["font"], 11, "bold"),
                      command=self.change_profile_picture).pack(side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Vezi colectia in Biblioteca ->", width=180, height=32, corner_radius=8,
                      fg_color=THEME["bg_card"], hover_color=THEME["bg_card_hover"], text_color=THEME["text_main"],
                      font=(THEME["font"], 11, "bold"), command=lambda: self.switch_tab("library")).pack(side="left")

        #bara cu numarul de piese favorite, evaluate si media notelor
        stats_bar = ctk.CTkFrame(self.content_inner, fg_color=THEME["bg_header"], corner_radius=12, border_width=1, border_color=THEME["border"])
        stats_bar.pack(fill="x", padx=8, pady=(0, 16))
        for val, lbl in [(str(stats["favorites_count"]), "FAVORITE"), (str(stats["reviews_count"]), "EVALUATE"),
                         (f"{stats['avg_rating']}", "MEDIA NOTELOR"), (str(stats["watchlist_count"]), "IN LISTA"),
                         (str(stats["excluded_count"]), "EXCLUSE")]:
            box = ctk.CTkFrame(stats_bar, fg_color="transparent")
            box.pack(side="left", expand=True, pady=16)
            ctk.CTkLabel(box, text=val, text_color=THEME["accent"], font=(THEME["font"], 20, "bold")).pack()
            ctk.CTkLabel(box, text=lbl, text_color=THEME["text_sub"], font=(THEME["font"], 10, "bold")).pack(pady=(2, 0))

        #sectiune distributie rating-uri si top afinitati
        mid_row = ctk.CTkFrame(self.content_inner, fg_color="transparent")
        mid_row.pack(fill="x", padx=8, pady=(0, 16))
        mid_row.grid_columnconfigure(0, weight=3)
        mid_row.grid_columnconfigure(1, weight=2)

        chart_card = ctk.CTkFrame(mid_row, fg_color=THEME["bg_header"], corner_radius=12, border_width=1, border_color=THEME["border"])
        chart_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(chart_card, text="DISTRIBUTIA RATING-URILOR", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold")).pack(anchor="w", padx=16, pady=(12, 8))
        max_bin = max(1, max(stats["star_bins"].values()) if stats["star_bins"] else 1)
        for star in range(5, 0, -1):
            cnt = stats["star_bins"].get(star, 0)
            rf = ctk.CTkFrame(chart_card, fg_color="transparent")
            rf.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(rf, text="*" * star, width=64, anchor="w", text_color=THEME["accent"], font=(THEME["font"], 14, "bold")).pack(side="left")
            bar = ctk.CTkProgressBar(rf, height=10, progress_color=THEME["accent"], fg_color=THEME["bg_card"])
            bar.set(cnt / max_bin)
            bar.pack(side="left", fill="x", expand=True, padx=12)
            ctk.CTkLabel(rf, text=str(cnt), width=28, text_color=THEME["text_sub"], font=(THEME["font"], 11)).pack(side="right")

        aff_card = ctk.CTkFrame(mid_row, fg_color=THEME["bg_header"], corner_radius=12, border_width=1, border_color=THEME["border"])
        aff_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        ctk.CTkLabel(aff_card, text="PROFIL MUZICAL (TOP AFINITATI)", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold")).pack(anchor="w", padx=16, pady=(12, 8))
        favs = lib["favorites"]
        top_art = Counter(t.get("artist", "") for t in favs if t.get("artist")).most_common(3)
        top_gen = Counter(t.get("genre", "") for t in favs if t.get("genre")).most_common(3)
        ctk.CTkLabel(aff_card, text="Artisti preferati:", text_color=THEME["text_muted"], font=(THEME["font"], 11)).pack(anchor="w", padx=16, pady=(4, 0))
        ctk.CTkLabel(aff_card, text=", ".join(f"{a} ({c})" for a, c in top_art) or "Nicio piesa apreciata inca",
                     text_color=THEME["text_main"], font=(THEME["font"], 12, "bold"), wraplength=240, justify="left").pack(anchor="w", padx=16, pady=(0, 10))
        ctk.CTkLabel(aff_card, text="Genuri dominante:", text_color=THEME["text_muted"], font=(THEME["font"], 11)).pack(anchor="w", padx=16)
        ctk.CTkLabel(aff_card, text=", ".join(f"{g} ({c})" for g, c in top_gen) or "Niciun gen conturat inca",
                     text_color=THEME["accent"], font=(THEME["font"], 12, "bold"), wraplength=240, justify="left").pack(anchor="w", padx=16, pady=(0, 12))

        #lista cu recenziile scrise de utilizator
        ctk.CTkLabel(self.content_inner, text="RECENZIILE SI NOTELE TALE", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold")).pack(anchor="w", padx=8, pady=(4, 8))
        rev_list = [t for t in lib["reviewed"] if t.get("user_review") or t.get("user_rating")]
        if not rev_list:
            empty_rev = ctk.CTkFrame(self.content_inner, fg_color=THEME["bg_header"], corner_radius=12, border_width=1, border_color=THEME["border"])
            empty_rev.pack(fill="x", padx=8, pady=(0, 16))
            ctk.CTkLabel(empty_rev, text="Nu ai scris inca nicio recenzie. Selecteaza o piesa si adauga o nota sau impresie in panoul din dreapta!",
                         text_color=THEME["text_muted"], font=(THEME["font"], 12)).pack(pady=24, padx=16)
        for item in rev_list[:15]:
            rc = ctk.CTkFrame(self.content_inner, fg_color=THEME["bg_header"], corner_radius=10, border_width=1, border_color=THEME["border"])
            rc.pack(fill="x", padx=8, pady=4)
            tr = ctk.CTkFrame(rc, fg_color="transparent")
            tr.pack(fill="x", padx=14, pady=(10, 4))
            ctk.CTkLabel(tr, text=f"{item.get('title')} - {item.get('artist')}", text_color=THEME["text_main"], font=(THEME["font"], 13, "bold")).pack(side="left")
            if item.get("user_rating"):
                ctk.CTkLabel(tr, text=f"Nota: {item['user_rating'] / 2.0:.1f}/5.0", text_color=THEME["accent"], font=(THEME["font"], 12, "bold")).pack(side="right")
            if item.get("user_review"):
                ctk.CTkLabel(rc, text=f"\"{item['user_review']}\"", text_color=THEME["text_sub"], font=(THEME["font"], 12), wraplength=720, justify="left").pack(anchor="w", padx=14, pady=(0, 10))

    def change_profile_picture(self):#alegere si salvare poza noua de profil
        if not (path := filedialog.askopenfilename(title="Alege poza de profil (PNG, JPG - max 5 MB)", filetypes=[("Imagini", "*.png *.jpg *.jpeg")])):
            return
        ok, msg = auth.update_user_avatar(self.user_id, path)
        if not ok:
            messagebox.showerror("Eroare imagine", msg)
            return
        self.refresh_avatar_widgets()
        self.show_profile_view()

    def render_poster_grid(self, tracks, empty_title="Nicio piesa gasita", empty_sub="", cta_text=None, cta_cmd=None):#afisare grila cu posterele pieselor
        self.clear_content()
        holder = ctk.CTkFrame(self.content_inner, fg_color="transparent")
        holder.pack(fill="both", expand=True)
        if not tracks:
            eb = ctk.CTkFrame(holder, fg_color=THEME["bg_header"], corner_radius=12, border_width=1, border_color=THEME["border"])
            eb.pack(fill="x", padx=16, pady=32)
            ctk.CTkLabel(eb, text=empty_title, text_color=THEME["text_main"], font=(THEME["font"], 16, "bold")).pack(pady=(24, 4))
            if empty_sub:
                ctk.CTkLabel(eb, text=empty_sub, text_color=THEME["text_muted"], font=(THEME["font"], 12)).pack(pady=(0, 20), padx=24)
            if cta_text and cta_cmd:
                ctk.CTkButton(eb, text=cta_text, height=36, corner_radius=8, fg_color=THEME["accent"], hover_color=THEME["accent_hover"],
                              text_color="#000000", font=(THEME["font"], 12, "bold"), command=cta_cmd).pack(pady=(0, 24))
            return

        w = self.canvas.winfo_width()
        self.last_cols = cols = max(2, (780 if w <= 20 else w) // 176)
        fav_ids = {t["id"] for t in auth.get_user_library(self.user_id)["favorites"]}
        for idx, track in enumerate(tracks[:48]):
            self._create_poster_card(holder, track, idx // cols, idx % cols, track["id"] in fav_ids)
        self._schedule_lazy_load()

    def _create_poster_card(self, parent, track, row, col, is_liked: bool):#construire card individual pt o piesa din grila
        is_sel = self.selected_track and self.selected_track["id"] == track["id"]
        card = ctk.CTkFrame(parent, width=160, height=248, fg_color=THEME["bg_card"], corner_radius=12,
                            border_width=2, border_color=THEME["accent"] if is_sel else THEME["border"])
        card.grid(row=row, column=col, padx=8, pady=8)
        card.grid_propagate(False)
        self.card_registry[track["id"]] = card

        rel_cover = track.get("cover_path", "")
        cache_key = (rel_cover, (140, 140))
        img_lbl = ctk.CTkLabel(card, image=self.image_cache.get(cache_key, self.placeholder_img), text="", width=140, height=140)
        img_lbl.pack(pady=(8, 8))

        if is_liked:
            ctk.CTkLabel(card, text="FAV", width=32, height=22, fg_color=THEME["bg_header"], text_color=THEME["accent"],
                         corner_radius=6, font=(THEME["font"], 9, "bold")).place(x=114, y=14)

        full_title, full_artist = track.get("title", "Unknown"), track.get("artist", "Unknown")
        title_lbl = ctk.CTkLabel(card, text=full_title, text_color=THEME["text_main"], font=(THEME["font"], 12, "bold"),
                                 wraplength=142, height=36, anchor="n", justify="center")
        title_lbl.pack(padx=8, pady=(0, 2))

        is_rec = "match_score" in track and self.current_view == "foryou"
        sub_lbl = ctk.CTkLabel(card, text=f"{track['match_score']}% | {full_artist}" if is_rec else full_artist,
                               text_color=THEME["accent"] if is_rec else THEME["text_sub"], font=(THEME["font"], 11),
                               wraplength=142, height=20, anchor="n")
        sub_lbl.pack(padx=8)

        tip = f"{full_title} - {full_artist}\nAlbum: {track.get('album', 'Single')} ({track.get('release_year', 2018)})"
        ToolTip(card, tip)
        ToolTip(title_lbl, tip)

        if rel_cover and cache_key not in self.image_cache:
            self.lazy_slots.append({"card": card, "label": img_lbl, "path": rel_cover, "size": (140, 140), "loaded": False})

        def on_enter(_):#evidentiere card cand pui mouse-ul pe el
            card.configure(fg_color=THEME["bg_card_hover"], border_color=THEME["accent"])

        def on_leave(_):
            curr = self.selected_track and self.selected_track["id"] == track["id"]
            card.configure(fg_color=THEME["bg_card"], border_color=THEME["accent"] if curr else THEME["border"])

        for w in (card, img_lbl, title_lbl, sub_lbl):
            w.bind("<Enter>", on_enter, add="+")
            w.bind("<Leave>", on_leave, add="+")
            w.bind("<Button-1>", lambda _, t=track: self.select_track(t))

    def _schedule_lazy_load(self):#programare incarcare imagini vizibile
        if self._lazy_after_id:
            self.root.after_cancel(self._lazy_after_id)
        self._lazy_after_id = self.root.after(30, self._process_visible_covers)

    def _process_visible_covers(self):#verificare ce carduri sunt vizibile pe ecran pt a le incarca imaginea
        self._lazy_after_id = None
        if not self.canvas.winfo_exists():
            return
        top_r = self.canvas.winfo_rooty() - 220
        bot_r = top_r + self.canvas.winfo_height() + 440
        to_decode = []
        for slot in self.lazy_slots:
            if slot["loaded"]:
                continue
            if not slot["card"].winfo_exists():
                slot["loaded"] = True
                continue
            if top_r <= slot["card"].winfo_rooty() <= bot_r:
                slot["loaded"] = True
                key = (slot["path"], slot["size"])
                if key in self.image_cache:
                    slot["label"].configure(image=self.image_cache[key])
                else:
                    to_decode.append(slot)
        if to_decode:
            threading.Thread(target=self._decode_covers_bg, args=(to_decode,), daemon=True).start()

    def _decode_covers_bg(self, slots):#decodare si redimensionare coperte in fundal
        for slot in slots:
            rel, sz = slot["path"], slot["size"]
            full = rel if os.path.isabs(rel) else os.path.join(BASE_DIR, rel)
            if os.path.exists(full):
                try:
                    with Image.open(full) as im:
                        pil_cp = im.convert("RGB").resize(sz, Image.Resampling.BILINEAR)
                    self.root.after(0, self._apply_decoded_cover, slot["label"], rel, sz, pil_cp)
                except Exception:
                    pass

    def _apply_decoded_cover(self, lbl, rel_path: str, sz: tuple, pil_img: Image.Image):#aplicare imagine incarcata pe card
        key = (rel_path, sz)
        if key not in self.image_cache:
            self.image_cache[key] = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=sz)
        if lbl.winfo_exists():
            lbl.configure(image=self.image_cache[key], text="")

    def select_track(self, track):#afisare detalii in panoul din dreapta cand selectezi o piesa
        prev_id = self.selected_track["id"] if self.selected_track else None
        self.selected_track = track
        if prev_id in self.card_registry and self.card_registry[prev_id].winfo_exists():
            self.card_registry[prev_id].configure(border_color=THEME["border"])
        if track["id"] in self.card_registry and self.card_registry[track["id"]].winfo_exists():
            self.card_registry[track["id"]].configure(border_color=THEME["accent"])

        self.lbl_title.configure(text=track.get("title", "Unknown"))
        self.lbl_artist.configure(text=track.get("artist", "Unknown"))
        meta = f"Album: {track.get('album', 'Single')}\nAn: {track.get('release_year', 2018)}  |  BPM: {int(track.get('bpm', 120))}"
        self.lbl_meta.configure(text=f"{meta}\nMotiv: {track['reason']}" if "reason" in track else meta)

        for w in self.tags_frame.winfo_children():
            w.destroy()
        for tg in (track.get("tags") or [track.get("genre", "Pop")])[:3]:
            ctk.CTkLabel(self.tags_frame, text=f" #{tg} ", fg_color=THEME["bg_card"], text_color=THEME["accent"],
                         corner_radius=6, font=(THEME["font"], 11, "bold")).pack(side="left", padx=4)

        rel_cover = track.get("cover_path", "")
        key_big = (rel_cover, (200, 200))
        if key_big in self.image_cache:
            self.cover_box.configure(image=self.image_cache[key_big], text="")
        elif rel_cover:
            self.cover_box.configure(image=self.placeholder_img, text="")
            threading.Thread(target=self._decode_covers_bg, args=([{"label": self.cover_box, "path": rel_cover, "size": (200, 200)}],), daemon=True).start()
        else:
            self.cover_box.configure(image=None, text="NO COVER")

        state = auth.get_track_user_state(self.user_id, track["id"])
        self.current_half_stars = state["rating"] or 0
        self.star_widget.set_value(self.current_half_stars)
        self._update_rating_label(self.current_half_stars)
        self.review_text.delete("1.0", "end")
        if state.get("review"):
            self.review_text.insert("1.0", state["review"])
        self.refresh_inspector_buttons(state)

    def refresh_inspector_buttons(self, state):#actualizare aspect butoane like, exclude si lista
        sig, watch = state.get("signal", 0), state.get("watchlist", 0)
        self.btn_like.configure(fg_color=THEME["accent"] if sig == 1 else THEME["bg_card"],
                                text_color="#000000" if sig == 1 else THEME["text_main"],
                                text="Favorita" if sig == 1 else "Like")
        self.btn_dislike.configure(fg_color=THEME["danger"] if sig == -1 else THEME["bg_card"],
                                   text_color="#FFFFFF" if sig == -1 else THEME["text_main"],
                                   text="Exclusa" if sig == -1 else "Exclude")
        self.btn_watch.configure(fg_color=THEME["accent"] if watch == 1 else THEME["bg_card"],
                                 text_color="#000000" if watch == 1 else THEME["text_main"],
                                 text="In Lista" if watch == 1 else "+ Lista")

    def _update_rating_label(self, half_stars: int):#actualizare text nota deasupra stelelor
        if not half_stars:
            self.lbl_rating_val.configure(text="RATINGUL TAU: Fara nota", text_color=THEME["text_sub"])
        else:
            s = half_stars / 2.0
            self.lbl_rating_val.configure(text=f"RATINGUL TAU: {'*' * int(s)}{'.5' if s % 1 != 0 else ''} ({s:.1f}/5.0)", text_color=THEME["accent"])

    def on_star_rating_changed(self, half_stars: int):#salvare automata cand schimbi nota pe stele
        self.current_half_stars = half_stars
        self._update_rating_label(half_stars)
        if self.selected_track:
            rat = half_stars if half_stars > 0 else None
            auth.save_interaction(self.user_id, self.selected_track, signal=1 if (rat and rat >= 8) else None, rating=rat)
            self.refresh_inspector_buttons(auth.get_track_user_state(self.user_id, self.selected_track["id"]))
            if self.current_view == "profile":
                self.show_profile_view()

    def _toggle_flag(self, mode: str):#actiune la apasarea butoanelor like, exclude sau lista
        if not self.selected_track:
            return
        st = auth.get_track_user_state(self.user_id, self.selected_track["id"])
        if mode == "like":
            auth.save_interaction(self.user_id, self.selected_track, signal=0 if st["signal"] == 1 else 1)
        elif mode == "dislike":
            auth.save_interaction(self.user_id, self.selected_track, signal=0 if st["signal"] == -1 else -1)
        elif mode == "watch":
            auth.save_interaction(self.user_id, self.selected_track, watchlist=0 if st["watchlist"] == 1 else 1)
        self.select_track(self.selected_track)
        if self.current_view in ("library", "profile", "foryou"):
            self.switch_tab(self.current_view)

    def save_review_and_rating(self):#salvare recenzie scrisa si nota
        if not self.selected_track:
            messagebox.showinfo("Info", "Selecteaza mai intai o piesa!")
            return
        rev = self.review_text.get("1.0", "end").strip()
        rat = self.current_half_stars if self.current_half_stars > 0 else None
        auth.save_interaction(self.user_id, self.selected_track, signal=1 if (rat and rat >= 8) else None, rating=rat, review=rev)
        self.select_track(self.selected_track)
        if self.current_view in ("profile", "library"):
            self.switch_tab(self.current_view)
        messagebox.showinfo("Salvat", "Nota si recenzia au fost salvate!")

    def on_live_search_key(self, event):#filtrare piese din baza locala in timp ce tastezi
         if event.keysym == "Return":
            return
        if self._search_after_id:
            self.root.after_cancel(self._search_after_id)
        self._search_after_id = self.root.after(250, self._execute_live_search)

    def trigger_online_search(self):#pornire cautare si descarcare piese noi de pe internet
        if not (q := self.search_entry.get().strip()):
            return
        self.search_btn.configure(text="Se cauta...", state="disabled")
        threading.Thread(target=lambda: (search_online_catalog(q, limit=24), self.root.after(0, self._on_search_complete, q)), daemon=True).start()

    def _on_search_complete(self, q: str):#afisare rezultate dupa terminarea cautarii online
        self.search_btn.configure(text="Cauta Online", state="normal")
        self.sub_filter_bar.pack_forget()
        self.current_tracks = hits = search_local_tracks(q)
        self.section_title.configure(text=f"REZULTATE PENTRU \"{q.upper()}\"")
        self.section_subtitle.configure(text=f"{len(hits)} piese gasite")
        self.render_poster_grid(hits)
