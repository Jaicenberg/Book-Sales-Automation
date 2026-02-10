from string import Template

MISSING_INFO_TEMPLATE = Template(
    "Hey $name,\n"
    "\n"
    "Thanks so much for your book purchase! I'm $sender_name, Nick's assistant, "
    "and I'll be handling the shipping for your copy of The 2-Hour Cocktail Party.\n"
    "\n"
    "Before I can get it sent out, I just need a couple things from you:\n"
    "\n"
    "$missing_list\n"
    "\n"
    "Once I have that, I'll get your book ordered and on its way!\n"
    "\n"
    "Best,\n"
    "$sender_name"
)

ORDER_CONFIRMATION_TEMPLATE = Template(
    "Hey $name,\n"
    "\n"
    "Your copy of The 2-Hour Cocktail Party is on its way! "
    "You should receive it by $estimated_delivery.\n"
    "\n"
    "You'll get a shipping confirmation from Amazon with tracking info shortly.\n"
    "\n"
    "Enjoy the read!\n"
    "\n"
    "Best,\n"
    "$sender_name\n"
    "\n"
    "P.S. If you find the book helpful, a review on Amazon goes a long way: "
    "https://www.amazon.com/dp/B09VKY415G"
)

# Field labels for the missing info template
FIELD_LABELS = {
    "name": "Your full name",
    "phone": "Your phone number",
    "shipping_address": "Your full shipping address (street, city, state, ZIP, country)",
}


def format_missing_fields(missing_fields: list[str]) -> str:
    """Convert a list of missing field keys into a friendly bullet list."""
    lines = []
    for field in missing_fields:
        label = FIELD_LABELS.get(field, field.replace("_", " ").title())
        lines.append(f"  - {label}")
    return "\n".join(lines)
