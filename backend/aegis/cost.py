import contextvars

# Context variable to hold cost accumulated during the current node execution
node_cost_usd = contextvars.ContextVar("node_cost_usd", default=0.0)


def add_cost(cost: float):
    current = node_cost_usd.get()
    node_cost_usd.set(current + cost)
