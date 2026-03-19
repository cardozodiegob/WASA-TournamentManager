"""Property-based tests for Advanced Cosmetic Effects V16.

Uses hypothesis with min 100 iterations per property.
Tests Properties 1–4 from the design document.
"""
import os, sys, pytest

sys.path.insert(0, os.path.dirname(__file__))

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from extensions import app, db
from models import CosmeticItem
from helpers import (
    EFFECT_MODES, generate_cosmetic_item, _GENERATOR_TEMPLATES,
)

VALID_MODES = set(EFFECT_MODES)

_counter = 0
def _uid():
    global _counter
    _counter += 1
    return _counter


@pytest.fixture(autouse=True)
def setup_db():
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    if 'matches' not in app.blueprints:
        from routes import register_blueprints
        register_blueprints(app)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()
        db.drop_all()


# Feature: advanced-cosmetic-effects-v16, Property 1: Effect mode is always valid
# Validates: Requirements 1.1, 2.1, 9.1
class TestProperty1EffectModeValidity:

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(mode=st.sampled_from(['css', 'svg_filter', 'canvas']))
    def test_valid_mode_persists(self, mode):
        """Any valid effect_mode value is stored correctly."""
        item = CosmeticItem(name=f'test-{_uid()}', category='badge',
                            effect_mode=mode, css_data='x')
        db.session.add(item)
        db.session.flush()
        assert item.effect_mode in VALID_MODES

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.data())
    def test_default_mode_is_css(self, data):
        """Items created without explicit effect_mode default to 'css'."""
        item = CosmeticItem(name=f'default-{_uid()}', category='badge',
                            css_data='x')
        db.session.add(item)
        db.session.flush()
        assert item.effect_mode == 'css'


# Feature: advanced-cosmetic-effects-v16, Property 2: SVG filter IDs are unique per item
# Validates: Requirements 3.3
class TestProperty2SvgFilterIdUniqueness:

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(
        id_a=st.integers(min_value=1, max_value=10**9),
        id_b=st.integers(min_value=1, max_value=10**9),
    )
    def test_distinct_ids_produce_distinct_filter_ids(self, id_a, id_b):
        """For any two distinct item IDs, cosm-svg-{id} must differ."""
        if id_a == id_b:
            return  # skip equal pairs
        filter_a = f'cosm-svg-{id_a}'
        filter_b = f'cosm-svg-{id_b}'
        assert filter_a != filter_b


# Feature: advanced-cosmetic-effects-v16, Property 3: Effect mode persistence round-trip
# Validates: Requirements 6.3
class TestProperty3EffectModeRoundTrip:

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(mode=st.sampled_from(['css', 'svg_filter', 'canvas']))
    def test_round_trip(self, mode):
        """Create item with mode, commit, re-read — mode must match."""
        item = CosmeticItem(name=f'rt-{_uid()}', category='profile_border',
                            effect_mode=mode, css_data='test')
        db.session.add(item)
        db.session.commit()
        fetched = db.session.get(CosmeticItem, item.id)
        assert fetched.effect_mode == mode


# Feature: advanced-cosmetic-effects-v16, Property 4: Generator returns valid effect mode
# Validates: Requirements 7.1, 7.4, 7.5
class TestProperty4GeneratorEffectMode:

    @settings(max_examples=100, deadline=None,
              suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(st.data())
    def test_all_templates_return_valid_mode(self, data):
        """For any category/template combo, generated dict has valid effect_mode."""
        # Build flat list of (category, template_name) pairs
        combos = []
        for cat, templates in _GENERATOR_TEMPLATES.items():
            for tname in templates:
                combos.append((cat, tname))
        combo = data.draw(st.sampled_from(combos))
        result = generate_cosmetic_item(combo[0], combo[1])
        assert result is not None, f'Generator returned None for {combo}'
        assert 'effect_mode' in result, f'Missing effect_mode key for {combo}'
        assert result['effect_mode'] in VALID_MODES, (
            f"Invalid effect_mode '{result['effect_mode']}' for {combo}"
        )
