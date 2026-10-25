from datetime import date

from app import referee
from app.models import Leaver, Offer, Seeker

L = Leaver(id="L", name="J", neighborhood="n", address="a", zip="1", lat=0, lng=0, available_from=date(2027, 5, 20),
           available_to=date(2027, 8, 10), flex_days=10, asking_rent=850, floor_rent=750)
S = Seeker(id="S", name="A", office_name="o", office_lat=0, office_lng=0, need_from=date(2027, 6, 1),
           need_to=date(2027, 8, 15), flex_days=5, target_rent=800, max_rent=900)


def offer(rent, i=date(2027, 6, 1), o=date(2027, 8, 15)):
    return Offer(move_in=i, move_out=o, monthly_rent=rent)


def test_leaver_cannot_go_below_floor():
    fixed, flags = referee.check_offer("leaver", offer(700), L)
    assert fixed.monthly_rent == 750 and flags


def test_seeker_cannot_go_above_max():
    fixed, _ = referee.check_offer("seeker", offer(950), S)
    assert fixed.monthly_rent == 900


def test_leaver_dates_clamped_to_window_plus_flex():
    fixed, _ = referee.check_offer("leaver", offer(800, o=date(2027, 8, 30)), L)
    assert fixed.move_out == date(2027, 8, 20)


def test_accept_rules():
    assert referee.can_accept("leaver", offer(800, o=date(2027, 8, 20)), L)
    assert not referee.can_accept("leaver", offer(740, o=date(2027, 8, 20)), L)
    assert not referee.can_accept("seeker", offer(800, o=date(2027, 8, 5)), S)  # ends too early for the internship


def test_scrub_redacts_private_numbers_and_protected_words():
    text, flags = referee.scrub("I can't go under $750, and we prefer female roommates", [750])
    assert "750" not in text and "female" not in text and len(flags) == 2
    text, flags = referee.scrub("Asking 850 with utilities", [750])
    assert text == "Asking 850 with utilities" and not flags


def test_midpoint_uses_public_offers_only():
    assert referee.midpoint(850, 780, L, S) == 815
    assert referee.midpoint(1000, 990, L, S) is None  # outside the seeker's max


def test_stay_total_prorates():
    assert referee.stay_total(offer(900, date(2027, 6, 1), date(2027, 7, 1))) == 900
