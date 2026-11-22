# Using OpenRewrite or IDE Tools for Automatable Changes

During a Java migration, many edits repeat across hundreds of files: renaming packages or types, replacing deprecated APIs, updating build configurations, fixing imports, adjusting annotations, or modernizing syntax to match a newer Java release. Editing every location manually risks omissions; running regex string replacements risks breaking code in unrelated contexts. IDE refactoring tools and OpenRewrite automate rule-based transformations while offering previews and scope control.

**OpenRewrite** is a framework for automatically transforming source code and certain configurations via composable, reusable, repeatable **recipes**. **IDE refactoring tools** analyze the project structure to execute operations such as rename, move, change signature, or structural search and replace. Both reduce repetitive work, yet outputs still require review and verification against builds, tests, and application behavior.

Choose the tool based on the nature of the change: local, symbol- and project-aware operations fit IDE refactorings; rule-based transformations spanning many modules or repositories fit repeatable automation recipes. Changes requiring business decisions, data handling, or architectural redesign still require developers to define semantics before automating code edits.

## 1. Identifying Automatable Changes

A change suitable for automation typically has these traits:

- Rules can be defined deterministically from code structure, symbol names, types, annotations, or configuration.
- Affected files, modules, and versions can be clearly scoped.
- Expected outcomes are concrete enough to verify before and after.
- Changes apply uniformly across many sites without per-business-case decisions.
- Automated verification exists via compilation, tests, contract tests, or diffs.

Good examples include replacing an old type with a new type, renaming methods per a new API, adding imports, removing unused imports, updating dependency versions, transforming Java syntax per an established recipe, or rewriting keys in properties/YAML files under clear rules.

The following cases demand extra caution:

- Identical method names whose semantics differ depending on overload or receiver type.
- Changes in how `null`, exceptions, transactions, retries, or side-effect ordering are handled.
- API changes requiring data transformation, configuration adjustments, or business behavior changes.
- Simultaneously migrating multiple modules with different dependencies and upgrade sequences.
- Changes valid only given runtime context, deployment configuration, or external consumers.

A recipe can swap an API name, yet cannot infer on its own how many retries the new policy should allow, which transactions must roll back, or how historical data should convert if those decisions were never specified.

## 2. How Does OpenRewrite Work?

OpenRewrite executes transformations through **recipes**. A recipe describes one specific transformation or composes multiple smaller transformations. Recipes can be authored in YAML to configure and combine existing recipes, or implemented in Java when custom analysis/transformation logic is needed.

Instead of matching raw text strings, OpenRewrite parses source into syntax trees enriched with type information wherever possible. For Java, the framework uses a syntax tree model that preserves formatting and source trivia, known as a Lossless Semantic Tree (LST). This lets recipes target specific types, method invocations, annotations, or constructs without replacing every identically named string across a file.

High-level workflow:

```text
Source code / build files / configuration
                  |
                  v
        Parse and build the model
                  |
                  v
       Apply the selected recipe
                  |
                  v
     Produce changes on the model
                  |
          +-------+-------+
          |               |
          v               v
       Dry run          Run
          |               |
          v               v
     Review diff     Write modified source
          |               |
          +-------+-------+
                  |
                  v
       Review, compile, and test
```

Syntactic models and type attribution give recipes deeper understanding than regex, yet output quality still depends on the parser, classpath, recipe, and completeness of project metadata. When type attribution is missing or dependencies fail to resolve, a type-based recipe may miss some target sites.

### 2.1. Standalone vs Composite Recipes

A standalone recipe performs a single narrowly scoped transformation. A composite recipe combines multiple recipes toward one migration goal, such as changing types, updating imports, and adjusting related configuration.

A recipe typically specifies:

- A unique identifier name, usually a fully qualified name.
- A description of purpose and transformation scope.
- Configuration parameters if the recipe needs old/new type names, versions, or values.
- A child recipe list if composite.
- Logic determining which nodes to inspect and how to modify them.

Recipes may include preconditions, running only when a project, file, or type meets specified criteria. Restricting scope avoids accidentally modifying out-of-scope code.

### 2.2. YAML Recipe Example

Suppose a library renames `com.legacy.client.JsonClient` to `com.modern.client.JsonClient`. A composite recipe can be defined as:

```yaml
type: specs.openrewrite.org/v1beta/recipe
name: com.example.migration.ReplaceLegacyJsonClient
displayName: Replace legacy JSON client type
description: Replace the legacy client type and clean obsolete imports.
recipeList:
  - org.openrewrite.java.ChangeType:
      oldFullyQualifiedTypeName: com.legacy.client.JsonClient
      newFullyQualifiedTypeName: com.modern.client.JsonClient
  - org.openrewrite.java.RemoveUnusedImports
```

This is a structural recipe example; the recipe must be placed where the build plugin discovers it, and referenced recipes must reside in corresponding recipe dependencies. Recipe names, parameters, and containing artifacts must be verified against the OpenRewrite version pinned in your project.

The `ChangeType` recipe targets a Java type by fully qualified name. It updates type references recognized by the parser rather than replacing every literal `JsonClient` string in source. The import cleanup recipe removes imports no longer needed after conversion.

However, changing a type does not automatically guarantee the new library shares the same methods, constructors, exceptions, or semantics. If the new API differs, pair additional recipes for well-understood syntactic shifts and manually update parts requiring behavioral decisions.

### 2.3. Custom Java Recipes

When built-in recipes cannot express a rule, write a recipe in Java. Custom recipes typically use visitors to traverse LST nodes, inspect node kinds and type metadata, and return modified nodes. For example, an internal recipe might transform method calls on a specific type only after checking argument counts or return types.

A well-written recipe should:

- Modify only nodes within the documented scope.
- Not rely unnecessarily on line positions or whitespace.
- Check types/symbols whenever rules depend on semantics.
- Preserve unrelated comments, formatting, and untouched code.
- Have tests covering matched cases, non-matched cases, and syntactic variations.
- Be idempotent: running it again produces zero new diffs once code reaches the target state.

Never write a custom recipe solely for simple string edits when an existing recipe or IDE refactoring already handles the task accurately. Recipe code itself requires maintenance and testing just like production code.

## 3. Integrating OpenRewrite With Gradle

OpenRewrite provides a Gradle plugin to discover and run recipes in a project. Exact configuration depends on plugin version, recipe artifacts, and Gradle version in use; pin versions instead of relying on `latest.release` in pipelines.

Groovy DSL configuration example:

```groovy
plugins {
    id 'org.openrewrite.rewrite' version '<rewrite-plugin-version>'
}

repositories {
    mavenCentral()
}

dependencies {
    rewrite 'org.openrewrite.recipe:rewrite-migrate-java:<recipe-version>'
}

rewrite {
    activeRecipe 'org.openrewrite.java.migrate.UpgradeToJava17'
}
```

`<rewrite-plugin-version>` and `<recipe-version>` are placeholders; replace them with verified versions pinned in your repository. The illustrative recipe name must exist in the declared recipe artifact. In real projects, verify the catalog/recipe discovery of the exact dependency before activating.

Common commands:

```bash
./gradlew rewriteDiscover
./gradlew rewriteDryRun
./gradlew rewriteRun
```

- `rewriteDiscover` lists recipes available under the current configuration.
- `rewriteDryRun` generates expected patches/diffs for review without modifying source files, serving dry-run purposes.
- `rewriteRun` executes the recipe and writes edits back to source.

Task names and detailed configuration options must match your selected plugin version. In multi-project builds, verify whether tasks apply at root, per subproject, or across specific modules; avoid running recipes repository-wide if targeting a single module.

### 3.1. Choosing the Right Gradle Scope

In Gradle multi-project builds, a recipe can apply across many subprojects. Before running, determine:

- Whether the recipe is activated at root or per subproject.
- Which projects contain source sets requiring migration.
- Whether build logic, convention plugins, or generated sources are in scope.
- Whether test sources and integration tests need matching updates.
- Whether generated or vendored files are allowed to be modified.

If the project uses Java toolchains, keep compiler/runtime toolchain settings aligned with the migration. OpenRewrite does not replace Gradle toolchain verification and does not prove the application runs on the target JDK.

## 4. Integrating OpenRewrite With Maven

With Maven, configure `rewrite-maven-plugin` alongside recipe artifacts. Illustrative example:

```xml
<plugin>
    <groupId>org.openrewrite.maven</groupId>
    <artifactId>rewrite-maven-plugin</artifactId>
    <version>${rewrite.maven.plugin.version}</version>
    <configuration>
        <activeRecipes>
            <recipe>org.openrewrite.java.migrate.UpgradeToJava17</recipe>
        </activeRecipes>
        <recipeArtifactCoordinates>
            <recipeArtifactCoordinate>
                org.openrewrite.recipe:rewrite-migrate-java:${rewrite.recipe.version}
            </recipeArtifactCoordinate>
        </recipeArtifactCoordinates>
    </configuration>
</plugin>
```

Version properties must be defined and pinned in the project. Recipes must exist inside the loaded artifacts; verify recipe names against the exact version before running.

Common goals:

```bash
mvn rewrite:discover
mvn rewrite:dryRun
mvn rewrite:run
```

Dry run generates a diff for review prior to modifying source. After review and approval, `rewrite:run` applies the recipe. In Maven multi-module builds, check reactor/module selection, active profiles, and plugin inheritance so edits stay within scope.

## 5. Selecting and Using Migration Recipes

OpenRewrite ships recipes for Java, libraries, frameworks, and build files. Recipes are commonly grouped by goal—such as Java upgrades, API conversions, Spring upgrades, dependency edits, or Maven/Gradle standardization.

When selecting a recipe, verify:

1. **Name and version:** does the recipe exist in the pinned artifact/version?
2. **Target:** which release, library, and scope does the recipe upgrade to?
3. **Preconditions:** what source level, dependencies, or classpath does the recipe require?
4. **Accompanying edits:** does it alter build files, imports, annotations, configs, or tests?
5. **Limitations:** which parts require manual work or lack support for your framework?
6. **Reporting:** does it emit data tables or outputs showing changed files and symbols?

Never pick a recipe solely because its name sounds close to your goal. Inspect its description, source, changelog, and tests when migrations have wide blast radius. Composite recipes bundle many steps; know everything they alter before executing.

### 5.1. Discovering Recipes Before Activating

Use the plugin's discovery task to list available recipes. Identify the fully qualified recipe name, read its documentation, and pilot it on a small module or test branch.

If a recipe is not found, verify whether the recipe artifact is declared in the right configuration, whether Maven repositories are reachable, and whether the recipe name changed between versions. Never guess recipe names.

### 5.2. Breaking Large Migrations Into Small Batches

For example, upgrading from an older framework to a newer one might break down into:

- Updating dependency and plugin versions.
- Migrating packages or APIs.
- Replacing changed annotations or methods.
- Updating YAML/properties configuration files.
- Updating tests, mocks, or test fixtures.
- Editing code requiring semantic decisions or manual handling.

Not everything must run in one pass. Splitting into focused recipes simplifies diff review and fault isolation. Each batch should pass appropriate builds/tests before advancing to the next batch.

## 6. Using IDE Refactoring Tools

Modern IDEs maintain syntax models, symbol indexes, type resolution, and project models. Consequently, built-in IDE refactorings are generally far safer than plain text search-and-replace when changing classes, methods, packages, or reference links.

Popular IDEs like IntelliJ IDEA and Eclipse offer rich refactorings; VS Code provides operations depending on installed Java extensions and language servers. Menu names and support depth vary across IDE versions.

### 6.1. Common Refactorings

| Operation | Purpose | What to review |
|---|---|---|
| Rename | Rename class, method, field, package, or variable | Impact on reflection, string-based configs, JSON/JPA names, or public APIs |
| Change Signature | Add/remove/change parameters or return types | Consumers, overloads, constructors, method references, and binary compatibility |
| Move | Move class/package | Package visibility, imports, module boundaries, resource paths, and scan configs |
| Extract Method | Extract code block into a method | Captured variables, exceptions, side-effect order, and visibility |
| Inline | Inline method/variable body into call sites | Assess call-site count and readability |
| Safe Delete | Remove symbol and IDE-detected references | Reflection, external dependencies, and string configs may escape detection |
| Encapsulate Field | Generate accessors and replace direct field access | Framework binding, serialization, JPA, and public field contracts |
| Organize Imports | Sort and prune unused imports | Static imports, wildcards, and formatter conventions |

These refactorings update references across the project in bulk, yet cannot guarantee catching references outside indexed source. For example, class names written in `application.yml`, XML, scripts, databases, or plugin registries might not be updated by IDE Rename.

### 6.2. Using Previews and Checking Scope

When the IDE provides a preview, inspect the file list and individual changes before confirming. Verify whether scope targets the current project, current module, or entire workspace. For public libraries, renaming or changing signatures can break source/binary compatibility for consumers outside the workspace.

Operations like Safe Delete rely on references analyzed by the IDE. They do not prove a symbol is unused via reflection, service loaders, dependency injection, config strings, or external systems. For public APIs, search external consumers and apply versioning/deprecation policies.

### 6.3. Structural Search and Replace

Some IDEs support Structural Search and Replace. This uses syntactic patterns and placeholders rather than arbitrary string matching. It fits repetitive transformations over well-defined code constructs, such as converting one method-call shape into another.

Before running Replace All, test the pattern on a few hits, verify placeholders and filter constraints, and use preview. Overly broad patterns can match unintended overloads or expressions with different semantics. Structural search does not fully replace type-aware recipes when transformations depend on distinguishing types, inheritance, or dependency APIs.

## 7. Comparing OpenRewrite, IDE Refactoring, and Regex

| Criterion | OpenRewrite | IDE refactoring | Regex/search-replace |
|---|---|---|---|
| Code understanding | Parser/LST, type attribution per recipe | Syntax tree, symbol index, and project model | Plain text/characters |
| Scope | Repeatable across multiple modules/repositories | Typically current open workspace/project | Searched files or file sets |
| Reusability | Recipes version-controlled and runnable in CI | Usually interactive; some IDEs save structural templates | Patterns can be saved yet lack semantic understanding |
| Review | Dry run/diff and reports | Refactoring preview | Match list and diff |
| Best suited for | Rule-based, wide-ranging, repeatable migrations | Context-aware in-project changes and familiar refactors | Simple, strictly bounded text edits |
| Primary risks | Insufficient recipe/classpath/attribution or missed edge cases | Index misses external consumers or string references | Accidentally altering comments, string literals, overloads, or syntax |

No single tool fits every change. Use OpenRewrite for large-scale repeatable batches, IDE tools for interactive or edge-case changes, and regex solely for tightly bounded plain-text edits. Choose based on semantics and scope, not raw speed alone.

## 8. Safe Automation Workflow in Migrations

### Step 1: Define Transformation Rules

Specify exact before and after states. Explicitly list target symbols, types, annotations, configs, or files. Identify edge cases and edits requiring human decisions.

Example: "Replace type `com.legacy.client.JsonClient` with `com.modern.client.JsonClient` in Java sources of the orders module; update imports; keep method calls untouched; do not edit generated sources or production configs in this step." Such concrete framing keeps recipes and review scope sharp.

### Step 2: Pick Tools and Verify Capabilities

Choose OpenRewrite if a verified recipe exists; choose IDE refactoring if tied closely to symbols in the current project; choose structural search if syntactic patterns are clear. Reserve regex strictly for text edits needing no Java syntax awareness.

Before running broadly, verify parsers, classpaths, JDK version, build plugins, and recipe dependencies. In multi-module codebases, ensure the tool has sufficient classpath metadata to resolve types.

### Step 3: Create Restore Points and Limit Scope

Start from a clean, reviewable working tree with any existing changes isolated. Use a dedicated branch or commit for the migration; never clobber unrelated work. Exclude generated sources, vendor code, build outputs, and unowned files unless the recipe explicitly targets them.

Pilot on one representative module or file subset to verify the recipe fits real project structure. If diffs reveal unexpected edits, stop and refine rules before widening scope.

### Step 4: Dry Run and Diff Review

In OpenRewrite, run `rewriteDryRun` or `rewrite:dryRun` depending on the build tool. In IDEs, inspect refactoring previews. In structural search, review all matches and test edge cases.

Review checklist:

- Which files changed and why?
- Were any modules or source sets missed?
- Were comments, string literals, generated code, or test fixtures modified unintentionally?
- Were imports, packages, generic types, and overloads transformed accurately?
- Did the recipe add/remove dependencies or modify build files unexpectedly?
- Are there semantic shifts requiring human sign-off?

A dry run proves only what diff the tool plans to produce; it never proves the diff is business-correct or runtime-compatible.

### Step 5: Apply in Small Batches

After review, execute the recipe or refactoring over the approved scope. Group edits into verifiable batches: Java source, build files, configs, tests, or documentation. Keep high-risk batches in separate diffs and commits for clean traceability.

### Step 6: Build, Test, and Verify Behavior

Run compilation, unit tests, integration tests, and relevant contract tests. For API migrations, verify error cases, nulls, ordering, side effects, and runtime configuration. If dependencies changed, check actually resolved artifacts and loaded classes.

Source automation never substitutes for dependency and runtime verification. A recipe can rewrite API call sites while failing to verify whether the target library exists in deployment or preserves semantics.

### Step 7: Re-Run to Check Stability

A recipe converting state A to state B must stop producing edits when run a second time on state B. Re-run dry run after applying; an empty diff or only documented exceptions confirms idempotency.

If the second pass keeps generating diffs, investigate: non-idempotent recipe, order-dependent child recipes, oscillating formatting, or unstable project state. Never place an automation loop generating endless diffs into a pipeline.

### Step 8: Record Outcomes and Exceptions

Archive plugin versions, recipe artifacts, recipe names, commands, module scopes, diffs, and build/test outcomes. List every site the recipe could not migrate along with reasons so developers can handle them manually. Reports should distinguish automatically modified files from files awaiting decisions.

## 9. Testing Recipes and Automated Refactorings

Custom recipes must have dedicated tests. Tests typically supply input source, the recipe to run, and expected output source. Include both matching and non-matching cases to verify boundaries.

A test suite for a type-replacement recipe should cover:

- Imports and variable declarations using the old type convert to the new type.
- Old types inside generics, fields, parameters, return types, or annotations are handled as specified.
- Another class sharing the same simple name in a different package stays untouched.
- Comments and string literals mentioning the old name stay intact if the recipe targets only type references.
- Code lacking sufficient type attribution follows defined policy rather than silently skipping without notice.
- A second execution of the recipe produces no further changes.

IDE refactorings do not always support automated recipe unit tests. Verify them via compile/test runs, diffs, and representative consumer suites. When an edit repeats frequently across projects, consider codifying the stable rule as a versioned recipe tested in CI.

## 10. Common Mistakes When Automating Migrations

- **Using regex for semantic edits:** identical strings appear across code, comments, log messages, JSON keys, and docs; global replacement breaks contracts.
- **Assuming the recipe fixed everything:** parser gaps, missing classpaths, incomplete type attribution, and preconditions can leave sites untouched.
- **Not pinning recipe/plugin versions:** identical recipe names in newer versions may alter logic or dependencies, hurting reproducibility.
- **Running repository-wide too early:** huge diffs overwhelm reviews and risk touching generated/vendor code.
- **Inspecting diffs without building:** code may look syntactically neat yet fail compilation due to mismatched dependencies or APIs.
- **Compiling without testing:** runtime behavior, ordering, exceptions, or side effects may have changed.
- **Ignoring config and data:** source migrations often require matching updates to build files, YAML, properties, schemas, or deployment data.
- **Skipping the idempotency re-run:** non-idempotent recipes keep mutating source on every run.
- **Running Safe Delete/Rename while forgetting reflection:** string-based lookups, framework classpath scans, and out-of-workspace consumers go unseen by IDE indexes.
- **Failing to track exceptions:** non-automatable sites get forgotten without explicit reports and owners.

## 11. Checklist Before Accepting Automated Changes

- [ ] Transformation rules and module/file scopes are clearly documented.
- [ ] Tools, plugins, recipes, and versions are pinned.
- [ ] Parsers/classpaths are sufficient to resolve relevant types.
- [ ] Dry run or preview has been reviewed.
- [ ] Diffs did not accidentally alter comments, strings, generated code, or out-of-scope files.
- [ ] Cases uncovered by the recipe are listed.
- [ ] Source, dependency, and configuration changes are all addressed.
- [ ] Builds, tests, and behavioral checks passed.
- [ ] Re-running the recipe produces no unexpected diffs.
- [ ] Tool versions, commands, diffs, and test evidence are saved for reproducibility.

## 12. Conclusion

OpenRewrite and IDE refactorings transform source code structurally and cut down repetitive work during Java migrations. OpenRewrite excels with versioned recipes runnable across multiple modules; IDE refactorings excel with interactive symbol- and project-model-aware edits; regex should remain limited to cleanly bounded text edits. Define rules upfront, restrict scope, review dry runs, apply in small batches, then build, test, and verify idempotency. Automation is complete only once diffs are understood and the application still satisfies its contracts after migration.
