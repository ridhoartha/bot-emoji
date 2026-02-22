const { Telegraf } = require('telegraf');
const axios = require('axios');

// Token diambil dari Environment Variable di Render agar aman
// Jika dijalankan lokal tanpa env, akan menggunakan token default di bawah
const BOT_TOKEN = process.env.BOT_TOKEN || '8346678690:AAH8NYRyZ723rj56GLuIMhtxBh-YFOrDags';
const bot = new Telegraf(BOT_TOKEN);

// URL Website utama
const WEBSITE_URL = 'https://rensidesign.my.id';

// Perintah /start
bot.start((ctx) => {
    ctx.reply(
        `Halo ${ctx.from.first_name}!\n\nSelamat datang di Bot Store Emoji Vektor (ALICIZATION).\nBot ini berjalan di Render dan terhubung ke: ${WEBSITE_URL}\n\nKetik /help untuk melihat menu.`
    );
});

// Perintah /help
bot.help((ctx) => {
    ctx.reply(
        "Daftar Perintah:\n" +
        "/status - Cek koneksi ke website\n" +
        "/web - Link akses website\n" +
        "/karya - Spesifikasi vektor emoji\n" +
        "/buatpack [nama] - Buat nama pack (Contoh: /buatpack rensi)"
    );
});

// Fitur Buat Pack (Sesuai permintaan: [nama] pack's @rensidesign)
bot.command('buatpack', (ctx) => {
    const args = ctx.message.text.split(' ').slice(1).join(' ');
    
    // Jika user tidak memasukkan nama setelah perintah, gunakan nama depan Telegramnya
    const namaPrefix = args ? args : ctx.from.first_name;
    
    const namaFullPack = `${namaPrefix} pack's @rensidesign`;
    
    ctx.reply(`📦 Nama Pack Berhasil Dibuat:\n\n\`${namaFullPack}\``, { parse_mode: 'Markdown' });
});

// Cek Status Website
bot.command('status', async (ctx) => {
    try {
        const response = await axios.get(WEBSITE_URL);
        if (response.status === 200) {
            ctx.reply(`✅ Website ${WEBSITE_URL} sedang Online!`);
        } else {
            ctx.reply(`⚠️ Website merespon dengan kode: ${response.status}`);
        }
    } catch (error) {
        ctx.reply(`❌ Website sedang Offline atau tidak dapat dijangkau.`);
    }
});

// Info Spesifikasi Karya (Sesuai instruksi: No BG, No Gradient, No Shadow, No Neon)
bot.command('karya', (ctx) => {
    ctx.reply(
        `🎨 *Spesifikasi Vektor Emoji*\n\n` +
        `• *Format:* Vektor murni (Sangat mudah di-Image Trace)\n` +
        `• *Background:* Transparan / Tanpa Background\n` +
        `• *Warna:* Solid (Tanpa Gradasi)\n` +
        `• *Efek:* Tanpa Shadow & Tanpa Efek Neon\n\n` +
        `Cocok untuk kebutuhan desain yang bersih dan tajam.`,
        { parse_mode: 'Markdown' }
    );
});

// Link Web
bot.command('web', (ctx) => {
    ctx.reply(`Kunjungi koleksi kami di: ${WEBSITE_URL}`);
});

// Respon pesan teks biasa
bot.on('text', (ctx) => {
    const msg = ctx.message.text.toLowerCase();
    if (msg.includes('halo') || msg === 'p') {
        ctx.reply('Halo! Ada yang bisa dibantu? Ketik /help untuk menu.');
    }
});

// Menjalankan Bot
bot.launch().then(() => {
    console.log('Bot is running on Render...');
});

// Penanganan penghentian bot agar aman
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));
