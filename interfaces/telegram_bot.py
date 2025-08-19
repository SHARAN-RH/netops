import os, requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

AGENT_URL = "http://localhost:7001"  # we call agent script locally via HTTP? We'll shell exec instead.
# Simpler: call decision_agent as library
from agent.decision_agent import decide_and_act

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Use /status <router_id> or /upgrade <router_id>")

async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: return await update.message.reply_text("Usage: /status R1")
    rid = ctx.args[0]
    from agent.decision_agent import rule_decision
    d = rule_decision(rid)
    await update.message.reply_text(f"{rid}: {'OK to upgrade' if d.approve else 'Do NOT upgrade'}\n{d.reason}")

async def upgrade_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args: return await update.message.reply_text("Usage: /upgrade R1")
    rid = ctx.args[0]
    res = decide_and_act(rid, dry_run=False)
    await update.message.reply_text(f"Upgrade result: {res}")

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("upgrade", upgrade_cmd))
    app.run_polling()
