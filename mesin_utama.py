import logging
import os
import importlib
import sys
from telegram.ext import Application
from database import TOKEN

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Kamus untuk nyimpen info plugin buat auto-generate menu /help
PLUGIN_REGISTRY = {}

def load_plugins(application):
    plugins_dir = "plugins"
    if not os.path.exists(plugins_dir):
        os.makedirs(plugins_dir)
        
    for filename in os.listdir(plugins_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"{plugins_dir}.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)
                # Kalo di file plugin ada fungsi setup(), jalanin!
                if hasattr(module, "setup"):
                    module.setup(application)
                    
                # Simpan info plugin buat menu /help
                if hasattr(module, "PLUGIN_NAME") and hasattr(module, "PLUGIN_DESC"):
                    PLUGIN_REGISTRY[module.PLUGIN_NAME] = module.PLUGIN_DESC
                    
                logger.info(f"✅ Plugin dimuat: {module.PLUGIN_NAME if hasattr(module, 'PLUGIN_NAME') else filename}")
            except Exception as e:
                logger.error(f"❌ Gagal memuat {filename}: {e}")

def main():
    application = Application.builder().token(TOKEN).build()
    
    logger.info("Mencari dan memuat plugin...")
    load_plugins(application)
    
    # Injeksi registry ke bot data biar bisa diakses command /help
    application.bot_data["plugin_registry"] = PLUGIN_REGISTRY
    
    logger.info("Mesin Modular 7.0 menyala! Gass bos!")
    application.run_polling()

if __name__ == '__main__':
    main()