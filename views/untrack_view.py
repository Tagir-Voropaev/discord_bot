import discord
import subscriptions as subs_db


class UntrackView(discord.ui.View):
    def __init__(self, user_subs):
        super().__init__(timeout=300)
        self.user_subs = user_subs

        options = [
            discord.SelectOption(
                label=s["name"][:100],
                value=s["item_id"],
                description=f"Порог: {s['max_price']:,}",
            )
            for s in user_subs[:25]
        ]
        select = discord.ui.Select(
            placeholder="🗑️ Выберите подписку для удаления…",
            options=options,
        )
        select.callback = self.on_delete
        self.add_item(select)

    async def on_delete(self, interaction: discord.Interaction):
        item_id = interaction.data["values"][0]
        item = next((s for s in self.user_subs if s["item_id"] == item_id), None)

        subs_db.remove_sub(interaction.user.id, item_id)

        embed = discord.Embed(
            title="🗑️ Подписка удалена",
            description=f"Предмет **{item['name']}** больше не отслеживается.",
            color=discord.Color.red(),
        )
        await interaction.response.edit_message(embed=embed, view=None)