import threading
import customtkinter as ctk
from tkinter import messagebox
from config import THEME
import auth


class AuthUI:
    def __init__(self, root: ctk.CTk, on_login_success):#initializare interfata autentificare
        self.root = root
        self.on_login_success = on_login_success
        self.container = ctk.CTkFrame(self.root, fg_color=THEME["bg_main"], corner_radius=0)
        self.container.pack(fill="both", expand=True)

    def clear_frame(self):#curatare elemente din container
        for w in self.container.winfo_children():
            w.destroy()

    def _build_card(self, title: str, subtitle: str) -> ctk.CTkFrame:#creare card central pt login si register
        card = ctk.CTkFrame(
            self.container,
            width=432,
            fg_color=THEME["bg_header"],
            corner_radius=16,
            border_width=1,
            border_color=THEME["border"],
        )
        card.place(relx=0.5, rely=0.5, anchor="center")

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=32, pady=32)

        logo_row = ctk.CTkFrame(inner, fg_color="transparent")
        logo_row.pack(anchor="w")
        ctk.CTkLabel(
            logo_row, text="o", text_color=THEME["accent"], font=(THEME["font"], 18, "bold")
        ).pack(side="left")
        ctk.CTkLabel(
            logo_row,
            text="  MUSICMETER",
            text_color=THEME["text_main"],
            font=(THEME["font"], 13, "bold"),
        ).pack(side="left")

        ctk.CTkLabel(
            inner, text=title, text_color=THEME["text_main"], font=(THEME["font"], 24, "bold")
        ).pack(anchor="w", pady=(16, 4))
        ctk.CTkLabel(
            inner,
            text=subtitle,
            text_color=THEME["text_muted"],
            font=(THEME["font"], 12),
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(0, 24))
        return inner

    def _style_focus(self, entry: ctk.CTkEntry):#schimbare culoare contur cand dai click pe input
        entry.bind("<FocusIn>", lambda e: entry.configure(border_color=THEME["accent"]))
        entry.bind("<FocusOut>", lambda e: entry.configure(border_color=THEME["border"]))

    def show_login_screen(self):#afisare formular de autentificare
        self.clear_frame()
        inner = self._build_card("Bun venit inapoi", "Autentifica-te in colectia ta muzicala")

        #camp introducere utilizator
        ctk.CTkLabel(
            inner, text="UTILIZATOR", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold")
        ).pack(anchor="w", pady=(0, 4))
        self.user_entry = ctk.CTkEntry(
            inner,
            width=368,
            height=40,
            corner_radius=8,
            fg_color=THEME["bg_input"],
            border_color=THEME["border"],
            text_color=THEME["text_main"],
            placeholder_text="Nume utilizator",
        )
        self.user_entry.pack(pady=(0, 16))
        self._style_focus(self.user_entry)

        #camp introducere parola
        ctk.CTkLabel(
            inner, text="PAROLA", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold")
        ).pack(anchor="w", pady=(0, 4))
        self.pass_entry = ctk.CTkEntry(
            inner,
            width=368,
            height=40,
            corner_radius=8,
            show="*",
            fg_color=THEME["bg_input"],
            border_color=THEME["border"],
            text_color=THEME["text_main"],
            placeholder_text="Parola",
        )
        self.pass_entry.pack(pady=(0, 24))
        self._style_focus(self.pass_entry)
        self.pass_entry.bind("<Return>", lambda e: self.attempt_login())

        #butoane conectare si trecere la inregistrare
        ctk.CTkButton(
            inner,
            text="CONECTARE",
            width=368,
            height=40,
            corner_radius=8,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            text_color="#000000",
            font=(THEME["font"], 13, "bold"),
            command=self.attempt_login,
        ).pack(pady=(0, 8))

        ctk.CTkButton(
            inner,
            text="Nu ai cont? Creeaza unul",
            width=368,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=THEME["bg_card"],
            text_color=THEME["text_sub"],
            font=(THEME["font"], 12),
            command=self.show_register_screen,
        ).pack()

    def show_register_screen(self):#afisare formular creare cont nou
        self.clear_frame()
        inner = self._build_card(
            "Creeaza cont", "Introdu o adresa de email valida pentru a-ti crea contul"
        )

        #camp utilizator nou
        ctk.CTkLabel(
            inner, text="UTILIZATOR", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold")
        ).pack(anchor="w", pady=(0, 4))
        self.reg_user = ctk.CTkEntry(
            inner,
            width=368,
            height=40,
            corner_radius=8,
            fg_color=THEME["bg_input"],
            border_color=THEME["border"],
            text_color=THEME["text_main"],
            placeholder_text="Minim 3 caractere",
        )
        self.reg_user.pack(pady=(0, 16))
        self._style_focus(self.reg_user)

        #camp adresa de email
        ctk.CTkLabel(
            inner, text="EMAIL VALID", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold")
        ).pack(anchor="w", pady=(0, 4))
        self.reg_email = ctk.CTkEntry(
            inner,
            width=368,
            height=40,
            corner_radius=8,
            fg_color=THEME["bg_input"],
            border_color=THEME["border"],
            text_color=THEME["text_main"],
            placeholder_text="nume@domeniu.ro",
        )
        self.reg_email.pack(pady=(0, 16))
        self._style_focus(self.reg_email)

        #camp parola cont nou
        ctk.CTkLabel(
            inner, text="PAROLA", text_color=THEME["text_sub"], font=(THEME["font"], 11, "bold")
        ).pack(anchor="w", pady=(0, 4))
        self.reg_pass = ctk.CTkEntry(
            inner,
            width=368,
            height=40,
            corner_radius=8,
            show="*",
            fg_color=THEME["bg_input"],
            border_color=THEME["border"],
            text_color=THEME["text_main"],
            placeholder_text="Minim 6 caractere",
        )
        self.reg_pass.pack(pady=(0, 24))
        self._style_focus(self.reg_pass)
        self.reg_pass.bind("<Return>", lambda e: self.attempt_register())

        #butoane trimitere formular si inapoi la login
        self.btn_reg_submit = ctk.CTkButton(
            inner,
            text="FINALIZARE CREARE CONT",
            width=368,
            height=40,
            corner_radius=8,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            text_color="#000000",
            font=(THEME["font"], 13, "bold"),
            command=self.attempt_register,
        )
        self.btn_reg_submit.pack(pady=(0, 8))

        ctk.CTkButton(
            inner,
            text="Inapoi la autentificare",
            width=368,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=THEME["bg_card"],
            text_color=THEME["text_sub"],
            font=(THEME["font"], 12),
            command=self.show_login_screen,
        ).pack()

    def attempt_login(self):#verificare date si autentificare utilizator
        u = self.user_entry.get().strip()
        p = self.pass_entry.get().strip()
        if not u or not p:
            messagebox.showwarning("Atentie", "Completeaza utilizatorul si parola.")
            return
        user_obj = auth.login_user(u, p)
        if user_obj:
            self.on_login_success(user_obj["username"])
        else:
            messagebox.showerror("Eroare", "Utilizator sau parola incorecta.")

    def attempt_register(self):#validare campuri si pornire inregistrare in fundal
        u = self.reg_user.get().strip()
        e = self.reg_email.get().strip()
        p = self.reg_pass.get().strip()
        if not u or not e or not p:
            messagebox.showwarning("Atentie", "Completeaza toate campurile.")
            return

        self.btn_reg_submit.configure(text="Se verifica emailul...", state="disabled")

        def _worker():#fir de executie pt verificare si salvare cont
            ok, msg = auth.register_user(u, e, p)
            self.root.after(0, lambda: self._on_register_done(ok, msg))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_register_done(self, ok: bool, msg: str):#afisare rezultat dupa inregistrare
        if self.btn_reg_submit.winfo_exists():
            self.btn_reg_submit.configure(text="FINALIZARE CREARE CONT", state="normal")
        if ok:
            messagebox.showinfo("Succes", msg)
            self.show_login_screen()
        else:
            messagebox.showerror("Inregistrare esuata", msg)