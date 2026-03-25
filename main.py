import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import MessageHandler, CallbackQueryHandler, filters, ContextTypes
from database import config, save_config, admin_states, b_conns, client_states, last_bot_msgs, is_admin

CAT_MAP = {"Text Emoji": "C1", "Character Emoji": "C2", "Special Effect": "C3", "More Emoji": "C4"}
REV_CAT_MAP = {v: k for k, v in CAT_MAP.items()}

def get_category_data():
    cats = {c: [] for c in CAT_MAP.values()}
    for emj, prc in config["prices"].items():
        cat_name = config.get("emoji_categories", {}).get(emj, "More Emoji")
        cat_code = CAT_MAP.get(cat_name, "C4")
        cats[cat_code].append({"emoji": emj, "price": prc})
    return cats

def get_price_range_text(cat_emojis):
    if not cat_emojis: return ""
    prices = [int(item["price"]) for item in cat_emojis]
    min_p, max_p = min(prices)//1000, max(prices)//1000
    if min_p == max_p: return f" ({min_p}K)"
    return f" ({min_p}K - {max_p}K)"

async def send_typing(context, chat_id, b_conn_id):
    try:
        await context.bot.send_chat_action(chat_id=chat_id, action='typing', business_connection_id=b_conn_id)
        await asyncio.sleep(1.5)
    except: pass

async def send_tracked(context, chat_id, b_conn_id, text, reply_markup=None, reply_to=None):
    if chat_id in last_bot_msgs:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=last_bot_msgs[chat_id])
        except: pass
    try:
        msg = await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, business_connection_id=b_conn_id, parse_mode='HTML', reply_to_message_id=reply_to)
        last_bot_msgs[chat_id] = msg.message_id
    except: pass

# --- UI FORM KLIEN (SINGLE BUBBLE) ---
async def render_order_form(chat_id, context, b_conn_id):
    state = client_states.get(chat_id)
    if not state: return

    t_val = state.get("text", "-")
    c_val = state.get("color", "-")

    text_disp = f"DI bantu isi format nya ya kak\nteks : {t_val}\nwarna : {c_val}"
    btn_t = "📝 Edit Teks" if t_val != "-" else "📝 Isi Teks"
    btn_c = "🎨 Edit Warna" if c_val != "-" else "🎨 Isi Warna"

    kb = [
        [InlineKeyboardButton(btn_t, callback_data="form_edit_text")],
        [InlineKeyboardButton(btn_c, callback_data="form_edit_color")]
    ]

    if t_val != "-" and c_val != "-":
        kb.append([InlineKeyboardButton("💳 Lanjut Pembayaran", callback_data="form_pay")])

    if "form_msg_id" in state:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=state["form_msg_id"], text=text_disp, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML', business_connection_id=b_conn_id)
            return
        except: pass

    msg = await context.bot.send_message(chat_id=chat_id, text=text_disp, reply_markup=InlineKeyboardMarkup(kb), business_connection_id=b_conn_id, parse_mode='HTML')
    state["form_msg_id"] = msg.message_id

# --- UI DRAFT ADMIN ---
admin_draft_selections = {}
admin_draft_temp_cat = {}

async def render_draft_panel(user_id, chat_id, context, page=0):
    drafts = config.get("drafts", [])
    if not drafts:
        await send_tracked(context, chat_id, b_conns.get(user_id), "🎉 <b>GUDANG DRAFT KOSONG!</b>\nSemua emoji berhasil masuk ke Pricelist.")
        return

    per_page = 10
    total_pages = max(1, (len(drafts) - 1) // per_page + 1)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    current_drafts = drafts[start:start + per_page]
    
    selections = admin_draft_selections.setdefault(user_id, set())
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    
    lines, row_buttons, kb = [], [], []
    for i, emj in enumerate(current_drafts):
        lines.append(f"{number_emojis[i]}  {emj}")
        btn_text = f"✅ {i+1}" if emj in selections else f"{i+1}"
        row_buttons.append(InlineKeyboardButton(btn_text, callback_data=f"draft_tgl_{start+i}_{page}"))
        if len(row_buttons) == 5:
            kb.append(row_buttons)
            row_buttons = []
    if row_buttons: kb.append(row_buttons)
    
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("«", callback_data=f"draft_page_{page-1}"))
    if page < total_pages - 1: nav_row.append(InlineKeyboardButton("»", callback_data=f"draft_page_{page+1}"))
    if nav_row: kb.append(nav_row)
    
    kb.append([InlineKeyboardButton(f"🚀 PROSES ({len(selections)})", callback_data=f"draft_process_{page}")])
    kb.append([InlineKeyboardButton(f"🗑️ Hapus ({len(selections)})", callback_data=f"draft_del_{page}")])
    kb.append([InlineKeyboardButton("Keluar", callback_data="draft_cancel")])
    
    text_disp = f"📦 <b>GUDANG DRAFT ({len(drafts)} Total)</b>\nHal {page+1}/{total_pages}\n\n" + "\n\n".join(lines)
    await send_tracked(context, chat_id, b_conns.get(user_id), text_disp, InlineKeyboardMarkup(kb))

# --- MEGA MESSAGE HANDLER ---
async def mega_msg_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # AUTO SEDOT
    if update.channel_post:
        msg = update.channel_post
        emojis = re.findall(r'<tg-emoji[^>]*>.*?</tg-emoji>', msg.text_html or msg.caption_html or "")
        if emojis:
            if "drafts" not in config: config["drafts"] = []
            for e in set(emojis):
                if e not in config["prices"] and e not in config["drafts"]:
                    config["drafts"].append(e)
            save_config(config)
        return

    msg = update.business_message or update.message
    if not msg: return
    user = msg.from_user
    chat_id = msg.chat_id
    text = msg.text or ""
    html_text = msg.text_html or msg.caption_html or ""
    b_conn_id = getattr(msg, "business_connection_id", None)
    if b_conn_id: b_conns[user.id] = b_conn_id

    # --- BAGIAN ADMIN ---
    if is_admin(user.id):
        if msg.forward_origin and not update.business_message:
            emojis = re.findall(r'<tg-emoji[^>]*>.*?</tg-emoji>', html_text)
            if emojis:
                added = 0
                for e in set(emojis):
                    if e not in config["prices"] and e not in config.get("drafts", []):
                        config["drafts"].append(e)
                        added += 1
                if added > 0:
                    save_config(config)
                    await msg.reply_text(f"✅ <b>{added} EMOJI DISEDOT!</b>\nKetik /draft", parse_mode='HTML')
            return

        if user.id in admin_states:
            state = admin_states[user.id]
            if state == "wait_draft_price":
                input_val = text.strip()
                if not input_val.isdigit(): return
                act_price = str(int(input_val) * 1000) if int(input_val) < 1000 else input_val
                cat_name = REV_CAT_MAP.get(admin_draft_temp_cat.get(user.id, "C4"), "More Emoji")
                for emj in admin_draft_selections.get(user.id, set()):
                    config["prices"][emj] = act_price
                    config.setdefault("emoji_categories", {})[emj] = cat_name
                config["drafts"] = [e for e in config.get("drafts", []) if e not in admin_draft_selections.get(user.id, set())]
                save_config(config)
                admin_draft_selections[user.id] = set()
                del admin_states[user.id]
                await render_draft_panel(user.id, chat_id, context, 0)
                return
            elif state.startswith("edit_text_"):
                config["texts"][state.split("_")[2]] = html_text
                save_config(config)
                del admin_states[user.id]
                await msg.reply_text("✅ Teks diupdate!")
                return
            elif state.startswith("edit_harga_baru_"):
                emoji_key = state.replace("edit_harga_baru_", "")
                input_val = int(text.strip())
                config["prices"][emoji_key] = str(input_val * 1000) if input_val < 1000 else str(input_val)
                save_config(config)
                del admin_states[user.id]
                await msg.reply_text("✅ Harga diubah!")
                return

        if text.startswith("/draft"):
            await render_draft_panel(user.id, chat_id, context, 0)
            return

        # 🔮 OPERASI BEDAH .acc MUTLAK (PREMIUM AMAN)
        if text.startswith(".acc"):
            if not config.get("log_channel_id"): return await msg.reply_text("❌ /setchannel dulu!")
            
            content = ""
            if msg.reply_to_message:
                # Sedot 100% Wujud HTML dari balasan (Foto maupun Teks)
                content = msg.reply_to_message.text_html or msg.reply_to_message.caption_html or ""
            else:
                # Sedot 100% Wujud HTML dari pesan langsung
                content = html_text.replace(".acc ", "", 1).replace(".acc", "", 1).strip()
                
            if content.strip():
                try:
                    await context.bot.send_message(
                        config["log_channel_id"], 
                        f"📋 <b>ORDER MANUAL</b>\n\n{content}", 
                        parse_mode='HTML', 
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏳ Menunggu Konfirmasi", callback_data="dummy")]])
                    )
                    await msg.reply_text("✅ Masuk antrian! (Premium Aman 💎)")
                except Exception as e:
                    await msg.reply_text(f"❌ Gagal mengirim ke channel log: {e}")
            else:
                await msg.reply_text("❌ Teks orderan kosong atau tidak terbaca.")
            return

        if text in [".getqris", ".getform", ".getpricelist", ".addbl", ".start", ".cleanghost"]:
            try: await msg.delete()
            except: pass
            if text == ".getqris":
                client_states[chat_id] = {"step": "waiting_payment", "final_form": "Manual Order"}
                try: await context.bot.send_photo(chat_id, open('qris.png', 'rb'), caption="Silakan bayar via QRIS ini kak!", business_connection_id=b_conn_id)
                except: pass
            elif text == ".getform":
                await context.bot.send_message(chat_id, f"Silakan isi form:\n\n<pre>{config['texts']['form_template'].replace('{username}','Client').replace('{harga}','Custom').replace('{teks_klien}','-').replace('{warna_klien}','-')}</pre>", parse_mode='HTML', business_connection_id=b_conn_id)
            elif text == ".getpricelist":
                cats = get_category_data()
                kb = []
                for c_name, c_code in CAT_MAP.items():
                    if cats[c_code]: kb.append([InlineKeyboardButton(f"{c_name}{get_price_range_text(cats[c_code])}", callback_data=f"plist_nav_{c_code}_0")])
                if kb: await context.bot.send_message(chat_id, "📋 <b>KATALOG RENSI DESIGN</b>\nPilih kategori desain yang kamu mau kak: 👇", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML', business_connection_id=b_conn_id)
                else: await context.bot.send_message(chat_id, "Katalog masih kosong kak!", business_connection_id=b_conn_id)
            elif text == ".addbl":
                if "blacklist" not in config: config["blacklist"] = []
                if chat_id not in config["blacklist"]:
                    config["blacklist"].append(chat_id)
                    save_config(config)
                    await context.bot.send_message(config["admin_id"], f"🔇 Bot dinonaktifkan untuk chat ini.")
            elif text == ".start":
                if "blacklist" not in config: config["blacklist"] = []
                if chat_id in config["blacklist"]:
                    config["blacklist"].remove(chat_id)
                    save_config(config)
                    await context.bot.send_message(config["admin_id"], f"🔊 Bot diaktifkan kembali untuk chat ini.")
            elif text == ".cleanghost":
                ghosts = 0
                for emj, prc in list(config["prices"].items()):
                    if config.get("emoji_categories", {}).get(emj) == "More Emoji" or not str(prc).isdigit():
                        del config["prices"][emj]
                        if emj not in config["drafts"]: config["drafts"].append(emj)
                        ghosts += 1
                save_config(config)
                await msg.reply_text(f"🧹 {ghosts} hantu dibersihkan!")
            return

        if text.startswith("/setting"):
            kb = [
                [InlineKeyboardButton("📝 Welcome", callback_data="set_welcome"), InlineKeyboardButton("📝 Form", callback_data="set_form_template")],
                [InlineKeyboardButton("📝 Tutorial", callback_data="set_tutorial"), InlineKeyboardButton("📝 Review", callback_data="set_closing_review")],
                [InlineKeyboardButton("📝 ACC Teks", callback_data="set_acc_payment"), InlineKeyboardButton("📝 REJ Teks", callback_data="set_rej_payment")]
            ]
            await msg.reply_text("⚙️ <b>PANEL SETTING</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
            return
            
        if text.startswith("/setharga") and msg.reply_to_message:
            match = re.search(r'<tg-emoji[^>]*>.*?</tg-emoji>', msg.reply_to_message.text_html)
            emj = match.group(0) if match else msg.reply_to_message.text_html[0]
            val = int(text.split()[1])
            config["prices"][emj] = str(val * 1000) if val < 1000 else str(val)
            config.setdefault("emoji_categories", {})[emj] = "More Emoji"
            save_config(config)
            kb = [[InlineKeyboardButton("Text", callback_data="setcat_C1"), InlineKeyboardButton("Character", callback_data="setcat_C2")], [InlineKeyboardButton("Effect", callback_data="setcat_C3"), InlineKeyboardButton("Abaikan", callback_data="setcat_C4")]]
            admin_states[user.id] = f"wait_cat_{emj}"
            await msg.reply_text("✅ Harga diset! Pilih kategori:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if text.startswith("/editharga"):
            cats = get_category_data()
            kb = [[InlineKeyboardButton(c_name, callback_data=f"eh_nav_{c_code}_0")] for c_name, c_code in CAT_MAP.items() if cats[c_code]]
            await msg.reply_text("Pilih kategori untuk diedit:", reply_markup=InlineKeyboardMarkup(kb))
            return

        if text.startswith("/setchannel"):
            config["log_channel_id"] = text.split()[1]
            save_config(config)
            await msg.reply_text("✅ Channel diset!")
            return

        if text.startswith("/done"):
            kb = [[InlineKeyboardButton("🌟 Berikan Review", url=config["urls"]["review"])]]
            await context.bot.send_message(chat_id, config["texts"]["closing_review"].replace("{nama}", "Kak"), reply_markup=InlineKeyboardMarkup(kb), business_connection_id=b_conn_id)
            if str(chat_id) in config["log_map"]:
                try: await context.bot.edit_message_reply_markup(config["log_channel_id"], config["log_map"][str(chat_id)], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ CLEAR / HAPUS", callback_data=f"log_clear_{chat_id}")]]))
                except: pass
            return

    # --- BAGIAN KLIEN ---
    if not config["is_open"] or chat_id in config.get("blacklist", []): return

    if chat_id in client_states:
        state = client_states[chat_id]
        if state.get("step") in ["wait_form_text", "wait_form_color"] and text:
            state["text"] = text if state["step"] == "wait_form_text" else state["text"]
            state["color"] = text if state["step"] == "wait_form_color" else state["color"]
            state["step"] = "form_idle"
            try: await msg.delete()
            except: pass
            await render_order_form(chat_id, context, b_conn_id)
            return

        if state.get("step") == "waiting_payment" and msg.photo and not msg.forward_origin:
            await send_typing(context, chat_id, b_conn_id)
            if config.get("log_channel_id"):
                try:
                    log_msg = await context.bot.send_message(config["log_channel_id"], f"📋 <b>ORDER BARU</b>\n\n{state['final_form']}", parse_mode='HTML', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⏳ Menunggu Konfirmasi", callback_data="dummy")]]))
                    config["log_map"][str(chat_id)] = log_msg.message_id
                    save_config(config)
                except: pass
            if config.get("admin_id"):
                await context.bot.send_message(config["admin_id"], f"🚨 <b>ORDER MASUK!</b> @{user.username or user.first_name}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ ACC", callback_data=f"acc_{user.id}_{msg.message_id}"), InlineKeyboardButton("❌ REJ", callback_data=f"rej_{user.id}_{msg.message_id}")]]), parse_mode='HTML')
            del client_states[chat_id]
            return

    if text.lower() == "/pricelist":
        cats = get_category_data()
        kb = [[InlineKeyboardButton(f"{c_name}{get_price_range_text(cats[c_code])}", callback_data=f"plist_nav_{c_code}_0")] for c_name, c_code in CAT_MAP.items() if cats[c_code]]
        if kb: await send_tracked(context, chat_id, b_conn_id, "📋 <b>KATALOG RENSI DESIGN</b>", InlineKeyboardMarkup(kb))
        return

    if msg.forward_origin and html_text:
        found_emoji = next((e for e in config["prices"] if e in html_text), None)
        if found_emoji:
            await send_typing(context, chat_id, b_conn_id)
            harga = config["prices"][found_emoji]
            praise = random.choice(config.get("forward_praises", ["KEREN BET KAN? 🔥"]))
            kb = [[InlineKeyboardButton("🔍 Cari Design Lain", url=config["urls"]["channel"]), InlineKeyboardButton("🟢 ORDER", callback_data=f"wiz_start_{harga}")]]
            client_states[chat_id] = {"temp_emoji": found_emoji}
            await send_tracked(context, chat_id, b_conn_id, f"{praise}\n\nHarga emoji ini: Rp {harga}", InlineKeyboardMarkup(kb))
            return

    text_clean = re.sub(r'[^\w\s]', '', text.lower())
    if any(t in text_clean.split() for t in config["triggers"]):
        await send_typing(context, chat_id, b_conn_id)
        kb = [[InlineKeyboardButton("📋 Pricelist", callback_data="plist_main"), InlineKeyboardButton("💬 Chat", callback_data="close_welcome")]]
        await send_tracked(context, chat_id, b_conn_id, config["texts"]["welcome"].replace("{nama}", user.first_name), InlineKeyboardMarkup(kb))


# --- MEGA CALLBACK HANDLER ---
async def mega_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user, chat_id, data = query.from_user, query.message.chat_id, query.data
    b_conn_id = getattr(query.message, "business_connection_id", None)
    try: await query.answer()
    except: pass

    # ADMIN CALLBACKS
    if is_admin(user.id):
        if data.startswith("log_clear_"):
            try: 
                await query.message.delete()
                if data.split('_')[2] in config["log_map"]: del config["log_map"][data.split('_')[2]]; save_config(config)
            except: pass
        elif data.startswith("acc_") or data.startswith("rej_"):
            action, c_id = data.split('_')[0], int(data.split('_')[1])
            try: await query.message.delete()
            except: pass
            if action == "acc":
                try: await context.bot.send_message(c_id, config["texts"]["acc_payment"].replace("{nama}", "Kak"), business_connection_id=b_conns.get(c_id))
                except: pass
                if str(c_id) in config["log_map"]:
                    try: await context.bot.edit_message_reply_markup(config["log_channel_id"], config["log_map"][str(c_id)], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💬 Chat", url=f"tg://user?id={c_id}")]]))
                    except: pass
            else:
                try: await context.bot.send_message(c_id, config["texts"]["rej_payment"], business_connection_id=b_conns.get(c_id))
                except: pass
                if str(c_id) in config["log_map"]:
                    try: await context.bot.edit_message_reply_markup(config["log_channel_id"], config["log_map"][str(c_id)], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ DITOLAK", callback_data="dummy"), InlineKeyboardButton("🗑️ CLEAR", callback_data=f"log_clear_{c_id}")]]))
                    except: pass
        elif data.startswith("draft_"):
            act = data.replace("draft_", "")
            if act.startswith("tgl_"):
                emj = config["drafts"][int(act.split("_")[1])]
                sel = admin_draft_selections.setdefault(user.id, set())
                sel.remove(emj) if emj in sel else sel.add(emj)
                await render_draft_panel(user.id, chat_id, context, int(act.split("_")[2]))
            elif act.startswith("page_"): await render_draft_panel(user.id, chat_id, context, int(act.split("_")[1]))
            elif act.startswith("process_"):
                if admin_draft_selections.get(user.id):
                    kb = [[InlineKeyboardButton("Text", callback_data="draft_cat_C1"), InlineKeyboardButton("Char", callback_data="draft_cat_C2")], [InlineKeyboardButton("Effect", callback_data="draft_cat_C3"), InlineKeyboardButton("More", callback_data="draft_cat_C4")]]
                    try: await query.message.edit_text("Pilih kategori:", reply_markup=InlineKeyboardMarkup(kb))
                    except: pass
            elif act.startswith("del_"):
                config["drafts"] = [e for e in config.get("drafts", []) if e not in admin_draft_selections.get(user.id, set())]
                save_config(config)
                admin_draft_selections[user.id] = set()
                await render_draft_panel(user.id, chat_id, context, int(act.split("_")[1]))
            elif act.startswith("cat_"):
                admin_draft_temp_cat[user.id] = act.split("_")[1]
                kb = [[InlineKeyboardButton(f"{int(p)//1000}K", callback_data=f"draft_prc_{p}") for p in sorted(set(config["prices"].values()), key=int)]]
                admin_states[user.id] = "wait_draft_price"
                try: await query.message.edit_text("Pilih harga atau ketik manual:", reply_markup=InlineKeyboardMarkup(kb))
                except: pass
            elif act.startswith("prc_"):
                prc, cat = act.split("_")[1], REV_CAT_MAP[admin_draft_temp_cat.get(user.id, "C4")]
                for e in admin_draft_selections.get(user.id, set()):
                    config["prices"][e] = prc; config.setdefault("emoji_categories", {})[e] = cat
                config["drafts"] = [e for e in config.get("drafts", []) if e not in admin_draft_selections.get(user.id, set())]
                save_config(config); admin_draft_selections[user.id] = set()
                if user.id in admin_states: del admin_states[user.id]
                await render_draft_panel(user.id, chat_id, context, 0)
            elif act == "cancel":
                if user.id in admin_states: del admin_states[user.id]
                try: await query.message.delete()
                except: pass
        elif data.startswith("setcat_"):
            config["emoji_categories"][admin_states[user.id].replace("wait_cat_", "")] = REV_CAT_MAP[data.split("_")[1]]
            save_config(config)
            del admin_states[user.id]
            try: await query.message.edit_text("✅ Disimpan!")
            except: pass
        elif data.startswith("set_"):
            admin_states[user.id] = f"edit_text_{data.replace('set_', '')}"
            await context.bot.send_message(chat_id, f"Kirim teks baru untuk {data.replace('set_', '')}:")

    # KLIEN CALLBACKS
    if data == "form_edit_text" and chat_id in client_states:
        client_states[chat_id]["step"] = "wait_form_text"
        try: await query.message.edit_text("✏️ <b>Ketik teks custom:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Batal", callback_data="form_cancel")]]), parse_mode='HTML')
        except: pass
    elif data == "form_edit_color" and chat_id in client_states:
        client_states[chat_id]["step"] = "wait_form_color"
        try: await query.message.edit_text("🎨 <b>Ketik warnanya:</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Batal", callback_data="form_cancel")]]), parse_mode='HTML')
        except: pass
    elif data == "form_cancel" and chat_id in client_states:
        client_states[chat_id]["step"] = "form_idle"
        await render_order_form(chat_id, context, b_conn_id)
    elif data == "form_pay" and chat_id in client_states:
        st = client_states[chat_id]
        st["final_form"] = f"{st['emoji']}\n\n✦ FORM ORDER ✦\nUser: @{user.username}\nTeks: {st['text']}\nWarna: {st['color']}\nHarga: Rp{st['price']}"
        st["step"] = "waiting_payment"
        try: await query.message.delete()
        except: pass
        try: await context.bot.send_photo(chat_id, open('qris.png','rb'), caption="Sip! Silakan bayar via QRIS & kirim bukti SS nya.", business_connection_id=b_conn_id)
        except: pass
    elif data.startswith("wiz_start_") or data.startswith("plist_sel_"):
        try: await query.message.delete()
        except: pass
        if data.startswith("wiz_start_"): hrg, emj = data.replace("wiz_start_", ""), client_states.get(chat_id, {}).get("temp_emoji", "Emoji")
        else:
            item = get_category_data().get(data.split('_')[2], [])[int(data.split('_')[3])]
            hrg, emj = item['price'], item['emoji']
        client_states[chat_id] = {"step": "form_idle", "emoji": emj, "price": hrg, "text": "-", "color": "-"}
        await context.bot.send_message(chat_id, emj, parse_mode='HTML', business_connection_id=b_conn_id)
        await render_order_form(chat_id, context, b_conn_id)
    elif data == "plist_main":
        cats = get_category_data()
        kb = [[InlineKeyboardButton(f"{c_name}{get_price_range_text(cats[c_code])}", callback_data=f"plist_nav_{c_code}_0")] for c_name, c_code in CAT_MAP.items() if cats[c_code]]
        try: await query.message.edit_text("📋 <b>KATALOG RENSI DESIGN</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except: pass
    elif data.startswith("plist_nav_"):
        cat_code, page = data.split('_')[2], int(data.split('_')[3])
        items = get_category_data().get(cat_code, [])
        if not items: return
        page = max(0, min(page, (len(items)-1)//5))
        curr = items[page*5:page*5+5]
        disp = "\n\n".join([f"{['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣'][i]}  {item['emoji']} > {int(item['price'])//1000}K" for i, item in enumerate(curr)])
        row = [InlineKeyboardButton(['1️⃣','2️⃣','3️⃣','4️⃣','5️⃣'][i], callback_data=f"plist_prev_{cat_code}_{page*5+i}_{page}") for i in range(len(curr))]
        nav = []
        if page > 0: nav.append(InlineKeyboardButton("«", callback_data=f"plist_nav_{cat_code}_{page-1}"))
        if page < (len(items)-1)//5: nav.append(InlineKeyboardButton("»", callback_data=f"plist_nav_{cat_code}_{page+1}"))
        kb = [row, nav, [InlineKeyboardButton("Kembali", callback_data="plist_main")]] if nav else [row, [InlineKeyboardButton("Kembali", callback_data="plist_main")]]
        try: await query.message.edit_text(f"<b>Kategori: {REV_CAT_MAP[cat_code]}</b>\n\n{disp}", reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except: pass
    elif data.startswith("plist_prev_"):
        cat_code, idx, page = data.split('_')[2], int(data.split('_')[3]), data.split('_')[4]
        item = get_category_data().get(cat_code, [])[idx]
        kb = [[InlineKeyboardButton("🟢 ORDER", callback_data=f"plist_sel_{cat_code}_{idx}")], [InlineKeyboardButton("Kembali", callback_data=f"plist_nav_{cat_code}_{page}")]]
        try: await query.message.edit_text(item['emoji'], reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
        except: pass
    elif data == "close_welcome":
        try: await query.message.delete()
        except: pass


def setup(application):
    # Daftarin Mesin ke Bot Core, PAKE REGEX ANTI-SERAKAH biar gak tabrakan sama /help
    application.add_handler(MessageHandler(filters.ALL, mega_msg_handler), group=2)
    application.add_handler(CallbackQueryHandler(mega_callback_handler, pattern="^(?!help_).*"), group=2)

    # 🔮 INJEKSI VIRTUAL MODULES ALA HIKARI USERBOT 🔮
    import __main__
    if hasattr(__main__, 'PLUGIN_REGISTRY'):
        reg = __main__.PLUGIN_REGISTRY
        
        # Bersihin Papan Nama Lama Kalo Ada
        if "Panel Admin" in reg: del reg["Panel Admin"]
        
        # Bikin 8 Modul Virtual Biar Tombol Menu Help Penuh & Estetik
        reg["Draft Engine"] = "Mesin otomatis penyedot emoji.\n\n<b>Commands:</b>\n• <code>/draft</code> : Buka panel manajemen draft.\n• Forward pesan emoji dari channel ke bot untuk sedot harga otomatis."
        reg["Set Harga"] = "Modul pemberian harga.\n\n<b>Commands:</b>\n• <code>/setharga [nominal]</code> : Reply ke pesan emoji untuk langsung memberi harga. Contoh: <code>/setharga 35</code>."
        reg["Edit Katalog"] = "Modul manajemen desain.\n\n<b>Commands:</b>\n• <code>/editharga</code> : Buka panel interaktif untuk ubah harga, pindah kategori, atau hapus emoji dari katalog."
        reg["Pricelist"] = "Modul display katalog klien.\n\n<b>Commands:</b>\n• <code>/pricelist</code> : Memunculkan menu UI katalog desain berjenjang."
        reg["Bot Settings"] = "Modul pengatur teks bot.\n\n<b>Commands:</b>\n• <code>/setting</code> : Buka panel untuk mengedit teks bot (Welcome, Tutorial, Reject, dll)."
        reg["Channel Logs"] = "Modul pengatur tujuan log orderan.\n\n<b>Commands:</b>\n• <code>/setchannel [ID_CHANNEL]</code> : Mengatur channel tempat orderan masuk."
        reg["Shortcuts"] = "Modul perintah kilat admin.\n\n<b>Commands:</b>\n• <code>.getqris</code> : Kirim QRIS\n• <code>.getform</code> : Kirim form\n• <code>.getpricelist</code> : Kirim katalog\n• <code>.cleanghost</code> : Bersih DB\n• <code>.acc [format]</code> : Forward log"
        reg["Blacklist"] = "Modul kontrol akses user.\n\n<b>Commands:</b>\n• <code>.addbl</code> : Matikan respon bot di chat ini.\n• <code>.start</code> : Nyalakan kembali."
