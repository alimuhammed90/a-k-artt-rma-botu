
import discord
from discord.ext import commands, tasks
from logic import DatabaseManager, hide_img
from config import TOKEN, DATABASE
import os
from datetime import datetime, timedelta

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

manager = DatabaseManager(DATABASE)
manager.create_tables()

os.makedirs("img", exist_ok=True)
os.makedirs("hidden_img", exist_ok=True)

last_sent = datetime.now() - timedelta(days=1)


@bot.command()
async def start(ctx):
    user_id = ctx.author.id

    if user_id in manager.get_users():
        await ctx.send("Zaten kayıtlısınız!")
    else:
        manager.add_user(user_id, ctx.author.name)
        await ctx.send("Başarıyla kayıt oldunuz!")


@bot.command()
async def bonus(ctx):
    points = manager.get_bonus_points(ctx.author.id)
    await ctx.send(f"Bonus puanınız: {points}")


@bot.command()
async def ozel_al(ctx, prize_id: int):
    result = manager.redeem_special(ctx.author.id, prize_id)

    if result == "points":
        await ctx.send("Yeterli bonus puanınız yok!")

    elif result == "not_found":
        await ctx.send("Özel resim bulunamadı!")

    elif result == "owned":
        await ctx.send("Bu resmi zaten almışsınız!")

    elif result == "success":
        img = manager.get_prize_img(prize_id)

        if img and os.path.exists(f"img/{img}"):
            await ctx.send(
                "Tebrikler! Özel resmi kazandınız!",
                file=discord.File(f"img/{img}")
            )


@bot.command()
async def rating(ctx):
    res = manager.get_rating()

    if not res:
        await ctx.send("Henüz derecelendirme bulunmuyor!")
        return

    result = "| USER_NAME | COUNT_PRIZE |\n"
    result += "_" * 30 + "\n"

    for user_name, count in res:
        result += f"| {user_name:<15} | {count:<10} |\n"

    await ctx.send(f"```{result}```")


@bot.command()
@commands.has_permissions(administrator=True)
async def resim_ekle(ctx):
    if not ctx.message.attachments:
        await ctx.send("Lütfen bir resim gönderin!")
        return

    attachment = ctx.message.attachments[0]
    filename = os.path.basename(attachment.filename)

    if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        await ctx.send("Desteklenmeyen resim formatı!")
        return

    await attachment.save(f"img/{filename}")
    manager.add_prize(filename)

    await ctx.send(f"Resim eklendi: {filename}")


@bot.command()
@commands.has_permissions(administrator=True)
async def ozel_resim_ekle(ctx, cost: int):
    if cost <= 0:
        await ctx.send("Fiyat sıfırdan büyük olmalıdır!")
        return

    if not ctx.message.attachments:
        await ctx.send("Lütfen bir resim gönderin!")
        return

    attachment = ctx.message.attachments[0]
    filename = os.path.basename(attachment.filename)

    if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        await ctx.send("Desteklenmeyen resim formatı!")
        return

    await attachment.save(f"img/{filename}")

    prize_id = manager.add_prize(
        filename,
        is_special=1,
        bonus_cost=cost
    )

    await ctx.send(
        f"Özel resim eklendi! ID: {prize_id}\n"
        f"Fiyat: {cost} bonus puan\n"
        f"Almak için: !ozel_al {prize_id}"
    )


@bot.command()
@commands.has_permissions(administrator=True)
async def ayar(ctx, setting: str, value: int):
    if value <= 0:
        await ctx.send("Değer sıfırdan büyük olmalıdır!")
        return

    if setting.lower() == "dakika":
        manager.update_setting("interval_minutes", value)
        await ctx.send(f"Resim gönderme sıklığı {value} dakika oldu!")

    elif setting.lower() == "bonus":
        manager.update_setting("bonus_per_win", value)
        await ctx.send(f"Kazanma başına bonus puan {value} oldu!")

    else:
        await ctx.send("Geçersiz ayar! Örnek: !ayar dakika 5")


@tasks.loop(seconds=30)
async def send_message():
    global last_sent

    settings = manager.get_settings()
    interval = settings["interval_minutes"]

    if (datetime.now() - last_sent).total_seconds() < interval * 60:
        return

    prize = manager.get_random_prize()

    if prize is None:
        print("Gönderilecek resim kalmadı!")
        return

    prize_id, img = prize

    if not os.path.exists(f"img/{img}"):
        print(f"Resim bulunamadı: {img}")
        manager.mark_prize_used(prize_id)
        return

    hide_img(img)

    for user_id in manager.get_users():
        try:
            user = await bot.fetch_user(user_id)
            await send_image(user, f"hidden_img/{img}", prize_id)
        except discord.Forbidden:
            print("Kullanıcıya DM gönderilemedi!")
        except discord.HTTPException as error:
            print(f"Discord hatası: {error}")

    manager.mark_prize_used(prize_id)
    last_sent = datetime.now()


async def send_image(user, image_path, prize_id):
    if not os.path.exists(image_path):
        return

    with open(image_path, "rb") as img:
        file = discord.File(img)

        button = discord.ui.Button(
            label="Al!",
            custom_id=str(prize_id)
        )

        view = discord.ui.View()
        view.add_item(button)

        await user.send(file=file, view=view)


@bot.event
async def on_interaction(interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id")

    if not custom_id or not custom_id.isdigit():
        return

    prize_id = int(custom_id)
    user_id = interaction.user.id

    result = manager.claim_prize(user_id, prize_id)

    if result == "not_found":
        await interaction.response.send_message(
            "Bu ödül bulunamadı!",
            ephemeral=True
        )

    elif result == "owned":
        await interaction.response.send_message(
            "Bu resmi zaten kazandınız!",
            ephemeral=True
        )

    elif result == "full":
        await interaction.response.send_message(
            "Bu resmin kazanan sayısı doldu!",
            ephemeral=True
        )

    elif result == "success":
        img = manager.get_prize_img(prize_id)

        if img and os.path.exists(f"img/{img}"):
            await interaction.response.send_message(
                file=discord.File(f"img/{img}"),
                content="Tebrikler! Resmi kazandınız ve bonus puan aldınız!"
            )
        else:
            await interaction.response.send_message(
                "Resim dosyası bulunamadı!",
                ephemeral=True
            )


@resim_ekle.error
@ozel_resim_ekle.error
@ayar.error
async def admin_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("Bu komutu kullanmak için yönetici olmalısınız!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Komut için gerekli bilgileri girmediniz!")
    else:
        await ctx.send(f"Bir hata oluştu: {error}")


@bot.event
async def on_ready():
    print(f"{bot.user} olarak giriş yapıldı!")

    if not send_message.is_running():
        send_message.start()


bot.run(TOKEN)
