import os, zipfile, hashlib, xml.etree.ElementTree as ET

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
    zip_path = os.path.join(ZIPS_DIR, zip_name)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _, files in os.walk(addon_path):
            for f in files:
                filepath = os.path.join(dirpath, f)
                arcname = os.path.relpath(filepath, ADDONS_DIR)
                zf.write(filepath, arcname)
    print(f"Zipped: {zip_name}")

addons_xml_str = ET.tostring(addons_xml_root, encoding="unicode")
with open("zips/addons.xml", "w") as f:
    f.write(addons_xml_str)

md5 = hashlib.md5(addons_xml_str.encode()).hexdigest()
with open("zips/addons.xml.md5", "w") as f:
    f.write(md5)

print("Done: addons.xml + addons.xml.md5 generated")