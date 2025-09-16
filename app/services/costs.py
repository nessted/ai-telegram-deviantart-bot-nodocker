def calc_cost_openai(tokens_in: int, tokens_out: int, price_in: float = 0.00015, price_out: float = 0.0006) -> float:
    return (tokens_in/1000.0)*price_in + (tokens_out/1000.0)*price_out

def calc_cost_image_job(price: float = 0.02) -> float:
    return price
