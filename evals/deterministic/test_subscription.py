import pytest

from minihermes.ops.procurement import review_subscription


@pytest.mark.parametrize("seats,basis,expected", [
    (5, None, None), (5, "per_seat", "7200.00"),
    (5, "all_seats", "1440.00"), (8, "per_seat", "11520.00"),
])
def test_monthly_quote_scope(seats, basis, expected):
    result = review_subscription(dict(item="设计软件", purpose="出图", amount="120",
                                      seats=seats, months=12, billing_period="monthly", price_basis=basis))
    assert result["estimated_total_cny"] == expected
    if basis is None:
        question, = result["questions"]
        assert question["field"] == "price_basis"
        assert question["clause"] in result["clauses"]
    else:
        assert result["status"] == "ready_for_review"
