import os
import re
import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- KONFIGURASI ID ---
ADMIN_ID = 7698417558  # ID BOS (ONlCKAlRl)
LOG_CHANNEL = "-1003560127110" # Channel Antrian
SOURCE_CHANNEL = "-1002754647835" # Channel Sedot Emoji

# --- DATABASE SEDERHANA ---
DB_FILE = "db_store.json"
def load_db():
    if not os.path.exists(DB_FILE):
        return {"prices": {}, "categories": {}, "drafts": []}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=4)

db = load_db()

# --- STATE MANAGEMENT (RAM) ---
client_states = {} # Lacak isian form klien
admin_states = {}  # Lacak proses admin (kayak .acc manual)

# --- HELPER KATEGORI ---
CAT_MAP = {"TEXT": "Text", "CHARA": "Character Emoji", "EFFECT": "Special Effect"}
def get_cat_range(cat_name):
    prices = [int(p) for e, p in db["prices"].items() if db["categories"].get(e) == cat_name]
    if not prices: return "Kosong"
    min_p, max_p = min(prices)//1000, max(prices)//1000
    if min_p == max_p: return f"{min_p}K"
    return f"{min_p}K - {max_p}K"

# ==========================================
# 1. MESSAGE HANDLER (NANGKAP CHAT / FOTO)
# ==========================================
async def store_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # A. AUTO SEDOT DARI CHANNEL PREVIEW
    if update.channel_post and str(update.channel_post.chat_id) == SOURCE_CHANNEL:
        msg = update.channel_post
        emojis = re.findall(r'<tg-emoji[^>]*>.*?</tg-emoji>', msg.text_html or msg.caption_html or "")
        if emojis:
            added = 0
            for e in set(emojis):
                if e not in db["prices"] and e not in db["drafts"]:
                    db["drafts"].append(e)
                    added += 1
            if added > 0: save_db(db)
        return

    msg = update.message
    if not msg: return
    user = msg.from_user
    chat_id = msg.chat_id
    text = msg.text or ""
    html_text = msg.text_html or msg.caption_html or ""

    # B. AREA ADMIN (ID BOS)
    if user.id == ADMIN_ID:
        # Fitur Admin: Setup Harga Cepat (Format: /set TEXT 25000 [emoji])
        if text.startswith("/set"):
            try:
                parts = text.split(" ", 2)
                cat_code = parts[1] # TEXT, CHARA, EFFECT
                price = parts[2]
                
                # Cek reply emoji
                if not msg.reply_to_message: return await msg.reply_text("Reply emojinya bos!")
                emj_match = re.search(r'<tg-emoji[^>]*>.*?</tg-emoji>', msg.reply_to_message.text_html)
                if not emj_match: return await msg.reply_text("Nggak ada custom emojinya!")
                emj = emj_match.group(0)
                
                db["prices"][emj] = price
                db["categories"][emj] = CAT_MAP.get(cat_code, "Text")
                if emj in db["drafts"]: db["drafts"].remove(emj)
                save_db(db)
                return await msg.reply_text(f"✅ Disimpan!\nKategori: {CAT_MAP.get(cat_code)}\nHarga: Rp{price}")
            except Exception as e:
                return await msg.reply_text("Format: /set TEXT 25000 (sambil reply emojinya)")

        # Fitur Admin: .getform
        if text == ".getform":
            try: await msg.delete()
            except: pass
            form_text = "Silahkan isi data berikut ini\nteks : -\nwarna : -\nUsername : @"
            return await msg.reply_text(form_text)

        # Fitur Admin: .acc (Manual Order)
        if text.startswith(".acc"):
            if not msg.reply_to_message: return await msg.reply_text("Reply form yang udah diisi klien bos!")
            content = msg.reply_to_message.text_html or msg.reply_to_message.caption_html or ""
            
            kb = [
                [InlineKeyboardButton("✅ KONFIRMASI ORDER", callback_data=f"man_conf_{user.id}")],
                [InlineKeyboardButton("❌ TOLAK ORDER", callback_data=f"man_rej_{user.id}")]
            ]
            admin_states[user.id] = {"temp_form": content}
            return await msg.reply_text("<b>ORDER MANUAL</b>\nApa bos mau memproses orderan ini?", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

        # Fitur Admin: Nangkap emoji preview setelah klik konfirmasi manual
        if admin_states.get(user.id, {}).get("step") == "wait_emoji_preview":
            emj_match = re.search(r'<tg-emoji[^>]*>.*?</tg-emoji>', html_text)
            if emj_match:
                preview_emj = emj_match.group(0)
                form_data = admin_states[user.id]["temp_form"]
                
                # Kirim ke log channel
                log_text = f"{preview_emj}\n\n{form_data}"
                kb = [[InlineKeyboardButton("💬 CHAT PEMBELI", url=f"tg://user?id={admin_states[user.id].get('client_id', user.id)}")]]
                await context.bot.send_message(LOG_CHANNEL, log_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
                
                await msg.reply_text("✅ Order manual sukses dilempar ke Channel Antrian!")
                del admin_states[user.id]
            else:
                await msg.reply_text("❌ Itu bukan custom emoji bos! Forward yang bener.")
            return

    # C. AREA KLIEN
    # 1. Start Menu
    if text == "/start":
        kb = [
            [InlineKeyboardButton("📝 MANUAL ORDER", callback_data="menu_manual")],
            [InlineKeyboardButton("🤖 OTOMATIS ORDER", callback_data="menu_auto")]
        ]
        return await msg.reply_text(f"Halo {user.first_name}, ada yang bisa aku bantu?", reply_markup=InlineKeyboardMarkup(kb))

    # 2. Tangkap Input Form (Teks / Warna)
    if chat_id in client_states:
        state = client_states[chat_id]
        if state.get("step") in ["wait_text", "wait_color"]:
            if state["step"] == "wait_text": state["teks"] = text
            if state["step"] == "wait_color": state["warna"] = text
            state["step"] = "idle"
            
            # Render Ulang Form
            try: await msg.delete()
            except: pass
            
            txt_btn = "📝 EDIT TEKS" if state["teks"] != "-" else "📝 ISI TEKS"
            col_btn = "🎨 EDIT WARNA" if state["warna"] != "-" else "🎨 ISI WARNA"
            kb = [
                [InlineKeyboardButton(txt_btn, callback_data="f_txt")],
                [InlineKeyboardButton(col_btn, callback_data="f_col")]
            ]
            if state["teks"] != "-" and state["warna"] != "-":
                kb.append([InlineKeyboardButton("💳 LANJUT PEMBAYARAN", callback_data="f_pay")])
            
            form_msg = f"Silahkan isi data berikut ini\nteks : {state['teks']}\nwarna : {state['warna']}"
            return await context.bot.edit_message_text(chat_id=chat_id, message_id=state["msg_id"], text=form_msg, reply_markup=InlineKeyboardMarkup(kb))

        # 3. Tangkap Bukti TF (Screenshot)
        if state.get("step") == "wait_tf" and msg.photo:
            # Kirim form & bukti ke Admin
            caption = f"<b>[BUKTI TF]</b>\nORDER EMOJI\n@{user.username or user.first_name}\n\n{state['emoji']}\n\nteks : {state['teks']}\nwarna : {state['warna']}"
            kb_admin = [
                [InlineKeyboardButton("✅ KONFIRMASI ORDERAN", callback_data=f"ord_acc_{chat_id}")],
                [InlineKeyboardButton("❌ TOLAK ORDERAN", callback_data=f"ord_rej_{chat_id}")]
            ]
            await context.bot.send_photo(ADMIN_ID, photo=msg.photo[-1].file_id, caption=caption, reply_markup=InlineKeyboardMarkup(kb_admin), parse_mode='HTML')
            
            await msg.reply_text("✅ Bukti TF berhasil dikirim! Menunggu konfirmasi admin...")
            del client_states[chat_id]
            return

    # 4. Tangkap Forward Emoji untuk Manual Order Cek Harga
    if msg.forward_origin and html_text:
        emj_match = re.search(r'<tg-emoji[^>]*>.*?</tg-emoji>', html_text)
        if emj_match:
            emj = emj_match.group(0)
            if emj in db["prices"]:
                return await msg.reply_text(f"{emj}\n\nHarga: Rp{db['prices'][emj]}", parse_mode='HTML')

# ==========================================
# 2. CALLBACK QUERY HANDLER (TOMBOL)
# ==========================================
async def store_cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    chat_id = query.message.chat_id
    data = query.data
    try: await query.answer()
    except: pass

    # --- MENU AWAL ---
    if data == "menu_manual":
        kb = [[InlineKeyboardButton("🔙 KEMBALI", callback_data="menu_start")]]
        await query.message.edit_text("Cara order : masuk ke ch @rensidesign dan forward emoji yang kamu mau ke roomchat ini. otomatis bot akan menampilkan harga emoji yang kamu forward.", reply_markup=InlineKeyboardMarkup(kb))
    
    elif data == "menu_start":
        kb = [[InlineKeyboardButton("📝 MANUAL ORDER", callback_data="menu_manual")], [InlineKeyboardButton("🤖 OTOMATIS ORDER", callback_data="menu_auto")]]
        await query.message.edit_text(f"Halo {user.first_name}, ada yang bisa aku bantu?", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "menu_auto":
        txt_r = get_cat_range("Text")
        chr_r = get_cat_range("Character Emoji")
        eff_r = get_cat_range("Special Effect")
        msg = f"<b>Pricelist emoji :</b>\ntext > {txt_r}\ncharacter emoji > {chr_r}\nSpesial effect > {eff_r}"
        kb = [
            [InlineKeyboardButton("TEXT", callback_data="cat_TEXT"), InlineKeyboardButton("CHARA", callback_data="cat_CHARA")],
            [InlineKeyboardButton("SPESIAL EFFECT", callback_data="cat_EFFECT")],
            [InlineKeyboardButton("ALL EMOJI", callback_data="cat_ALL")],
            [InlineKeyboardButton("🔙 KEMBALI", callback_data="menu_start")]
        ]
        await query.message.edit_text(msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

    # --- PAGINATION KATALOG ---
    elif data.startswith("cat_") or data.startswith("page_"):
        cat_name = data.split("_")[1]
        page = int(data.split("_")[2]) if data.startswith("page_") else 0
        
        # Filter Emoji
        if cat_name == "ALL":
            emojis = list(db["prices"].keys())
        else:
            real_cat = CAT_MAP.get(cat_name)
            emojis = [e for e, p in db["prices"].items() if db["categories"].get(e) == real_cat]
        
        if not emojis:
            return await query.message.edit_text("Kategori ini masih kosong!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("KEMBALI", callback_data="menu_auto")]]))

        # Paginate (5 per page)
        total_pages = max(1, (len(emojis) - 1) // 5 + 1)
        page = max(0, min(page, total_pages - 1))
        curr_emojis = emojis[page*5 : page*5+5]

        # Susun UI
        display_emojis = "".join(curr_emojis)
        btn_numbers = [InlineKeyboardButton(f"[{i+1}]", callback_data=f"buy_{list(db['prices'].keys()).index(e)}") for i, e in enumerate(curr_emojis)]
        
        nav_btns = []
        if page > 0: nav_btns.append(InlineKeyboardButton("<", callback_data=f"page_{cat_name}_{page-1}"))
        if page < total_pages - 1: nav_btns.append(InlineKeyboardButton(">", callback_data=f"page_{cat_name}_{page+1}"))

        kb = [btn_numbers]
        if nav_btns: kb.append(nav_btns)
        kb.append([InlineKeyboardButton("KEMBALI", callback_data="menu_auto")])

        await query.message.edit_text(display_emojis, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

    # --- PREVIEW 1 EMOJI ---
    elif data.startswith("buy_"):
        idx = int(data.split("_")[1])
        emj = list(db["prices"].keys())[idx]
        kb = [
            [InlineKeyboardButton("📝 MINTA FORM", callback_data=f"reqform_{idx}")],
            [InlineKeyboardButton("🔙 KEMBALI", callback_data="menu_auto")]
        ]
        await query.message.edit_text(emj, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

    # --- SISTEM FORM ---
    elif data.startswith("reqform_"):
        idx = int(data.split("_")[1])
        emj = list(db["prices"].keys())[idx]
        client_states[chat_id] = {"emoji": emj, "teks": "-", "warna": "-", "step": "idle", "msg_id": query.message.message_id}
        
        kb = [[InlineKeyboardButton("📝 ISI TEKS", callback_data="f_txt")], [InlineKeyboardButton("🎨 ISI WARNA", callback_data="f_col")]]
        await query.message.edit_text("Silahkan isi data berikut ini\nteks : -\nwarna : -", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "f_txt" or data == "f_col":
        if chat_id not in client_states: return
        client_states[chat_id]["step"] = "wait_text" if data == "f_txt" else "wait_color"
        target = "teks" if data == "f_txt" else "warna"
        kb = [[InlineKeyboardButton("🔙 KEMBALI", callback_data="f_back")]]
        await query.message.edit_text(f"Silahkan masukan {target} yang kamu mau", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "f_back":
        if chat_id not in client_states: return
        client_states[chat_id]["step"] = "idle"
        state = client_states[chat_id]
        txt_btn = "📝 EDIT TEKS" if state["teks"] != "-" else "📝 ISI TEKS"
        col_btn = "🎨 EDIT WARNA" if state["warna"] != "-" else "🎨 ISI WARNA"
        kb = [[InlineKeyboardButton(txt_btn, callback_data="f_txt")], [InlineKeyboardButton(col_btn, callback_data="f_col")]]
        if state["teks"] != "-" and state["warna"] != "-":
            kb.append([InlineKeyboardButton("💳 LANJUT PEMBAYARAN", callback_data="f_pay")])
        await query.message.edit_text(f"Silahkan isi data berikut ini\nteks : {state['teks']}\nwarna : {state['warna']}", reply_markup=InlineKeyboardMarkup(kb))

    # --- QRIS PAYMENT ---
    elif data == "f_pay":
        if chat_id not in client_states: return
        client_states[chat_id]["step"] = "wait_tf"
        try: await query.message.delete()
        except: pass
        try:
            await context.bot.send_photo(chat_id, open('qris.jpg', 'rb'), caption="Silakan lakukan pembayaran via QRIS ini.\nJika sudah, kirimkan screenshot buktinya ke sini yaa.")
        except Exception as e:
            await context.bot.send_message(chat_id, "❌ Error menampilkan QRIS. Pastikan file qris.jpg ada di server.")

    # --- ADMIN: KONFIRMASI AUTO ORDER ---
    elif data.startswith("ord_acc_") or data.startswith("ord_rej_"):
        if user.id != ADMIN_ID: return
        client_id = int(data.split("_")[2])
        is_acc = data.startswith("ord_acc_")
        
        try: await query.message.edit_reply_markup(reply_markup=None)
        except: pass

        if is_acc:
            # Info ke klien
            kb_done = [[InlineKeyboardButton("✅ DONE", callback_data="done_order")]]
            await context.bot.send_message(client_id, "ORDERAN DI TERIMA, di tunggu maksimal 3 hari. terima kasih", reply_markup=InlineKeyboardMarkup(kb_done))
            
            # Ekstrak data dari caption untuk dikirim ke Log Channel
            caption = query.message.caption_html
            # Cari emoji premiumnya
            emj_match = re.search(r'<tg-emoji[^>]*>.*?</tg-emoji>', caption)
            emj = emj_match.group(0) if emj_match else "Emoji"
            
            # Ambil detail form
            form_detail = caption.split("\n\nteks : ")[1] if "\n\nteks : " in caption else "-"
            teks = form_detail.split("\nwarna : ")[0] if "\nwarna : " in form_detail else "-"
            warna = form_detail.split("\nwarna : ")[1] if "\nwarna : " in form_detail else "-"
            
            log_text = f"{emj}\n\nteks : {teks}\nwarna : {warna}"
            kb_log = [[InlineKeyboardButton("💬 CHAT PEMBELI", url=f"tg://user?id={client_id}")]]
            await context.bot.send_message(LOG_CHANNEL, log_text, reply_markup=InlineKeyboardMarkup(kb_log), parse_mode='HTML')
            await context.bot.send_message(ADMIN_ID, "✅ Orderan dikonfirmasi & dilempar ke Channel Antrian!")
        else:
            await context.bot.send_message(client_id, "❌ Maaf, orderan ditolak / bukti TF tidak valid.")
            await context.bot.send_message(ADMIN_ID, "❌ Orderan ditolak.")

    # --- ADMIN: TOMBOL DONE (HANYA BISA DIKLIK BOS) ---
    elif data == "done_order":
        if user.id != ADMIN_ID:
            return await query.answer("❌ Cuma @ONlCKAlRl yang bisa mencet ini!", show_alert=True)
        try: await query.message.edit_text(query.message.text + "\n\n<b>[ ✓ SELESAI DIKERJAKAN ]</b>", reply_markup=None, parse_mode='HTML')
        except: pass

    # --- ADMIN: KONFIRMASI MANUAL ORDER (.acc) ---
    elif data.startswith("man_conf_") or data.startswith("man_rej_"):
        if user.id != ADMIN_ID: return
        is_conf = data.startswith("man_conf_")
        
        try: await query.message.delete()
        except: pass

        if is_conf:
            admin_states[user.id]["step"] = "wait_emoji_preview"
            # Asumsi username ada di teks
            temp_f = admin_states[user.id]["temp_form"]
            c_id_match = re.search(r'tg://user\?id=(\d+)', temp_f)
            if c_id_match: admin_states[user.id]["client_id"] = int(c_id_match.group(1))
            await context.bot.send_message(ADMIN_ID, "✅ Order manual diterima.\nSekarang <b>FORWARD emoji premium</b> yang dipesan klien ke sini untuk preview di channel antrian!")
        else:
            if user.id in admin_states: del admin_states[user.id]
            await context.bot.send_message(ADMIN_ID, "❌ Order manual dibatalkan.")


def setup(application):
    application.add_handler(MessageHandler(filters.ALL, store_msg_handler), group=4)
    application.add_handler(CallbackQueryHandler(store_cb_handler), group=4)
