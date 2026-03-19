import os, zipfile, hashlib, shutil, xml.etree.ElementTree as ET

ADDONS_DIR = "addons"
ZIPS_DIR = "zips"
os.makedirs(ZIPS_DIR, exist_ok=True)

addons_xml_root = ET.Element("addons")

for addon_id in os.listdir(ADDONS_DIR):
    addon_path = os.path.join(ADDONS_DIR, addon_id)
    addon_xml_path = os.path.join(addon_path, "addon.xml")
    if not os.path.isfile(addon_xml_path):
        continue

    tree = ET.parse(addon_xml_path)
    root = tree.getroot()
    version = root.get("version")
    addons_xml_root.append(root)

    zip_name = f"{addon_id}-{version}.zip"
    
    # ZIP do podsložky (pro instalaci z repozitáře)
    addon_zip_dir = os.path.join(ZIPS_DIR, addon_id)
    os.makedirs(addon_zip_dir, exist_ok=True)
    zip_path = os.path.join(addon_zip_dir, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, files in os.walk(addon_path):
            for f in files:
                filepath = os.path.join(dirpath, f)
                arcname = os.path.relpath(filepath, ADDONS_DIR)
                zf.write(filepath, arcname)
    
    # Kopie ZIP přímo do zips/ (pro instalaci ze souboru ZIP)
    shutil.copy(zip_path, os.path.join(ZIPS_DIR, zip_name))
    print(f"Zipped: {zip_name}")

addons_xml_str = ET.tostring(addons_xml_root, encoding="unicode")
with open("zips/addons.xml", "w") as f:
    f.write(addons_xml_str)

md5 = hashlib.md5(addons_xml_str.encode()).hexdigest()
with open("zips/addons.xml.md5", "w") as f:
    f.write(md5)

# Generate index.html
zip_files = [f for f in os.listdir(ZIPS_DIR) if f.endswith('.zip')]
with open("zips/index.html", "w") as f:
    f.write("<html><body>\n")
    f.write('<a href="addons.xml">addons.xml</a><br>\n')
    f.write('<a href="addons.xml.md5">addons.xml.md5</a><br>\n')
    for z in sorted(zip_files):
        f.write(f'<a href="{z}">{z}</a><br>\n')
    f.write("</body></html>\n")

print("Done: addons.xml + addons.xml.md5 generated")
