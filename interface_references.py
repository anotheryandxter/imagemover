import tkinter as tk
import pywinstyles

# Create the main window
root = tk.Tk()
root.title("Simple Tkinter GUI with Aero Style")
root.geometry("400x300")

# Apply the Aero style
pywinstyles.apply_style(root, style='aero')

# Add some widgets
label = tk.Label(root, text="Hello, World!", font=("Helvetica", 16))
label.pack(pady=20)

button = tk.Button(root, text="Click Me", font=("Helvetica", 14))
button.pack(pady=10)

# Start the main loop
root.mainloop()
