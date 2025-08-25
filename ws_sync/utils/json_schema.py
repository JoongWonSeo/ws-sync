import re

from pydantic.json_schema import (
    CoreModeRef,
    DefsRef,
    GenerateJsonSchema,
    JsonSchemaMode,
)

# ========== START OF MODIFICATION ========== #
_MODE_TITLE_MAPPING: dict[JsonSchemaMode, str] = {
    "validation": "CreateSynced",
    "serialization": "Synced",
}
# ========== END OF MODIFICATION ========== #


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
        name_mode = DefsRef(f"{mode_title}{self.normalize_name(short_ref)}")
        module_qualname = DefsRef(self.normalize_name(core_ref_no_id))
        module_qualname_mode = DefsRef(f"{mode_title}{module_qualname}")
        module_qualname_id = DefsRef(self.normalize_name(core_ref))
        occurrence_index = self._collision_index.get(module_qualname_id)
        if occurrence_index is None:
            self._collision_counter[module_qualname] += 1
            occurrence_index = self._collision_index[module_qualname_id] = (
                self._collision_counter[module_qualname]
            )

        module_qualname_occurrence = DefsRef(f"{module_qualname}__{occurrence_index}")
        module_qualname_occurrence_mode = DefsRef(
            f"{module_qualname_mode}__{occurrence_index}"
        )

        self._prioritized_defsref_choices[module_qualname_occurrence_mode] = [
            name,
            name_mode,
            module_qualname,
            module_qualname_mode,
            module_qualname_occurrence,
            module_qualname_occurrence_mode,
        ]

        return module_qualname_occurrence_mode
