import customtkinter as ctk
from config import THEME
from ui_auth import AuthUI
from ui_dashboard import DashboardUI

#setare tema intunecata implicita
ctk.set_appearance_mode("dark")


class MainApp:
    def __init__(self, root: ctk.CTk):#configurare fereastra principala a aplicatiei
        self.root = root
        self.root.title("Musicmeter v2")
        self.root.geometry("1220x760")
        self.root.configure(fg_color=THEME["bg_main"])
        self.current_user = None
        self.show_auth()

    def clear_root(self):#stergere elemente din fereastra principala
        for widget in self.root.winfo_children():
            widget.destroy()

    def show_auth(self):#afisare ecran autentificare
        self.clear_root()
        self.auth_ui = AuthUI(self.root, self.on_login_success)
        self.auth_ui.show_login_screen()

    def show_dashboard(self):#afisare ecran principal dashboard
        self.clear_root()
        self.dashboard_ui = DashboardUI(self.root, self.current_user, self.logout)

    def on_login_success(self, username: str):#actiune la conectare reusita
        self.current_user = username
        self.show_dashboard()

    def logout(self):#deconectare utilizator si intoarcere la login
        self.current_user = None
        self.show_auth()


if __name__ == "__main__":#pornire aplicatie
    root = ctk.CTk()
    app = MainApp(root)
    root.mainloop()