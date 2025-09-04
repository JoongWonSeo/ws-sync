import re

from pydantic.json_schema import (
    CoreModeRef,
    DefsRef,
    GenerateJsonSchema,
    JsonRef,
    JsonSchemaMode,
    _DefinitionsRemapping,
)

# ======================= OUR CUSTOMIZATION START =======================
# We alter naming so that:
# - serialization uses base (unprefixed) name when possible
# - validation uses the same name when schemas are identical
# - validation uses a 'Create' prefix when schemas diverge
# This deviates from pydantic's default which uses '-Output'/'-Input' suffixes.
_MODE_TITLE_MAPPING: dict[JsonSchemaMode, str] = {
    "validation": "Create",  # custom prefix used only in validation when diverging
    "serialization": "Ser",  # internal seed only; not used in final names
}
# ======================== OUR CUSTOMIZATION END ========================


class CustomGenerateJsonSchema(GenerateJsonSchema):
    def get_defs_ref(self, core_mode_ref: CoreModeRef) -> DefsRef:
        """
        Override this method to change the way that definitions keys are generated from a core reference.

        Args:
            core_mode_ref: The core reference.

        Returns:
            The definitions key.
        """
        # Split the core ref into "components"; generic origins and arguments are each separate components
        core_ref, mode = core_mode_ref
        components = re.split(r"([\][,])", core_ref)
        # Remove IDs from each component
        components = [x.rsplit(":", 1)[0] for x in components]
        core_ref_no_id = "".join(components)
        # Remove everything before the last period from each "component"
        components = [
            re.sub(r"(?:[^.[\]]+\.)+((?:[^.[\]]+))", r"\1", x) for x in components
        ]
        short_ref = "".join(components)

        mode_title = _MODE_TITLE_MAPPING[mode]

        # It is important that the generated defs_ref values be such that at least one choice will not
        # be generated for any other core_ref. Currently, this should be the case because we include
        # the id of the source type in the core_ref
        name = DefsRef(self.normalize_name(short_ref))
        module_qualname = DefsRef(self.normalize_name(core_ref_no_id))
        module_qualname_id = DefsRef(self.normalize_name(core_ref))
        occurrence_index = self._collision_index.get(module_qualname_id)
        if occurrence_index is None:
            self._collision_counter[module_qualname] += 1
            occurrence_index = self._collision_index[module_qualname_id] = (
                self._collision_counter[module_qualname]
            )

        module_qualname_occurrence = DefsRef(f"{module_qualname}__{occurrence_index}")
        # ======================= OUR CUSTOMIZATION START =======================
        # Use a mode-tagged seed to distinguish modes initially; we remap to final names later.
        module_qualname_mode = DefsRef(f"{module_qualname}-{mode_title}")
        module_qualname_occurrence_mode = DefsRef(
            f"{module_qualname_mode}__{occurrence_index}"
        )

        if mode == "serialization":
            # Prefer base names for serialization; fall back to qualified/occurrence; keep seed as last resort
            choices = [
                name,
                module_qualname,
                module_qualname_occurrence,
                module_qualname_occurrence_mode,
            ]
        else:  # validation
            # Include base to allow identical schemas to converge on the same name.
            # For divergent schemas, remapping will choose 'Create'+base.
            choices = [
                name,
                DefsRef(f"Create{module_qualname_occurrence}"),
                DefsRef(f"Create{module_qualname}"),
                DefsRef(f"Create{name}"),
                module_qualname,
                module_qualname_occurrence,
                module_qualname_occurrence_mode,
            ]

        self._prioritized_defsref_choices[module_qualname_occurrence_mode] = choices
        # ======================== OUR CUSTOMIZATION END ========================

        return module_qualname_occurrence_mode

    # ======================= OUR CUSTOMIZATION START =======================
    # We override the remapping phase to enforce our naming policy described above.
    def _build_definitions_remapping(self) -> _DefinitionsRemapping:  # type: ignore[override]
        defs_to_json: dict[DefsRef, JsonRef] = {}
        for seed in self._prioritized_defsref_choices:
            json_ref = JsonRef(self.ref_template.format(model=seed))
            defs_to_json[seed] = json_ref

        # Helper: find group key per seed based on unmodeled occurrence alternative present in choices
        def group_key_for_seed(seed: DefsRef) -> DefsRef:
            alts = self._prioritized_defsref_choices[seed]
            # prefer plain occurrence without any prefixes/suffixes
            for alt in alts:
                # Normalize a Create-prefixed occurrence to the plain occurrence for grouping
                if alt.startswith("Create") and re.search(r"__\d+$", alt):
                    stripped = DefsRef(alt.removeprefix("Create"))
                    return stripped
                if (
                    re.search(r"__\d+$", alt)
                    and "-" not in alt
                    and not alt.startswith("Create")
                ):
                    return alt
            # fallback to seed without mode tag before occurrence
            return DefsRef(re.sub(r"-(Ser|Create)(?=__\d+$)", "", seed))

        # Group seeds by model-occurence
        grouped: dict[DefsRef, dict[str, DefsRef]] = {}
        for seed in self._prioritized_defsref_choices:
            core_mode_ref = self.defs_to_core_refs.get(seed)
            mode = core_mode_ref[1] if core_mode_ref else "serialization"
            key = group_key_for_seed(seed)
            g = grouped.setdefault(key, {})
            g[mode] = seed

        assigned_defs: dict[DefsRef, DefsRef] = {}
        assigned_json: dict[JsonRef, JsonRef] = {}
        used_names: dict[str, dict] = {}  # name -> schema json

        def pick_unique(
            name: DefsRef, schema: dict, fallbacks: list[DefsRef]
        ) -> DefsRef:
            # choose a name not used for a different schema
            base = name
            if (s := used_names.get(base)) is None:
                used_names[base] = schema
                return base
            if s == schema:
                return base
            # try fallbacks
            for fb in fallbacks:
                if (s := used_names.get(fb)) is None:
                    used_names[fb] = schema
                    return fb
                if s == schema:
                    return fb
            # last resort: keep the seed-derived unique name (first fallback if provided)
            if fallbacks:
                return fallbacks[-1]
            return name

        # First pass: handle groups with both modes
        for modes in grouped.values():
            ser_seed = modes.get("serialization")
            val_seed = modes.get("validation")
            if not ser_seed and not val_seed:
                continue

            ser_alts = self._prioritized_defsref_choices[ser_seed] if ser_seed else []
            val_alts = self._prioritized_defsref_choices[val_seed] if val_seed else []

            def find_base(alts: list[DefsRef]) -> DefsRef | None:
                for alt in alts:
                    if alt.startswith("Create"):
                        continue
                    return alt
                return None

            base_name = find_base(ser_alts) or find_base(val_alts)
            if not base_name:
                continue

            ser_schema = self.definitions.get(ser_seed) if ser_seed else None
            val_schema = self.definitions.get(val_seed) if val_seed else None

            if ser_seed:
                # prefer base for serialization
                ser_fallbacks = [cand for cand in ser_alts if cand != base_name]
                target = pick_unique(base_name, ser_schema or {}, ser_fallbacks)
                assigned_defs[ser_seed] = target
                assigned_json[defs_to_json[ser_seed]] = JsonRef(
                    self.ref_template.format(model=target)
                )

            if val_seed:
                if ser_seed is None:
                    # Only validation requested: keep base name (no prefix)
                    val_target = base_name
                    val_fallbacks = [c for c in val_alts if c != base_name]
                elif val_schema is None:
                    # Shouldn't happen in practice, but fall back to base
                    val_target = base_name
                    val_fallbacks = [c for c in val_alts if c != base_name]
                elif ser_schema == val_schema:
                    # Both modes present and identical: use base for validation
                    val_target = base_name
                    val_fallbacks = [c for c in val_alts if c != base_name]
                else:
                    # Both modes present and different: use Create+base for validation
                    create_base = DefsRef(f"Create{base_name}")
                    val_target = create_base
                    val_fallbacks = [c for c in val_alts if c != base_name]

                chosen = pick_unique(val_target, val_schema or {}, val_fallbacks)
                assigned_defs[val_seed] = chosen
                assigned_json[defs_to_json[val_seed]] = JsonRef(
                    self.ref_template.format(model=chosen)
                )

        # Handle any remaining seeds that weren't assigned (e.g., single-mode defs)
        for seed, alts in self._prioritized_defsref_choices.items():
            if seed in assigned_defs:
                continue
            schema = self.definitions.get(seed, {})
            chosen = None
            for cand in alts:
                existing = used_names.get(cand)
                if existing is None or existing == schema:
                    chosen = cand
                    break
            if chosen is None:
                chosen = seed
            assigned_defs[seed] = chosen
            assigned_json[defs_to_json[seed]] = JsonRef(
                self.ref_template.format(model=chosen)
            )

        return _DefinitionsRemapping(assigned_defs, assigned_json)

    # ======================== OUR CUSTOMIZATION END ========================
