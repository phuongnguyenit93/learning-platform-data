# Conditional Compilation, Warnings, and Compiler Parameters in PL/SQL

PL/SQL provides several mechanisms to control source code directly at compile time. Three groups are often used together while serving distinct purposes:

- **Conditional compilation** selects which code sections are included in the compiled unit, based on static conditions and compile-time flags.
- **Compiler warnings** flag suspicious or potentially buggy code patterns, such as unreachable code or exception handlers that swallow errors.
- **Compiler parameters** determine how the compiler optimizes, generates interpreted/native code, collects analysis metadata, and handles warnings.

For example, a package can contain a debug branch included only in development builds, while production enables strict warnings and uses the same set of compiler settings across every build:

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'debug:FALSE, feature_orders:TRUE';

ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';

ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
```

These settings affect subsequent PL/SQL compilations within their scope. They do not alter the logic of an already-compiled object on their own; to apply new settings, the corresponding object must be recompiled.

## 1. What Is Conditional Compilation?

### 1.1. Selecting Code at Compile Time

Conditional compilation lets the compiler choose a code branch based on a static expression. Unselected branches do not become executable code in the compiled unit.

Basic syntax:

```sql
$IF static_boolean_expression $THEN
    -- Code included when condition is TRUE
$ELSIF another_static_expression $THEN
    -- Alternative branch
$ELSE
    -- Default branch
$END
```

Example:

```sql
CREATE OR REPLACE PROCEDURE show_build_mode AS
BEGIN
    $IF $$DEBUG_BUILD $THEN
        DBMS_OUTPUT.PUT_LINE('Debug build');
    $ELSE
        DBMS_OUTPUT.PUT_LINE('Production build');
    $END
END;
/
```

If compile flag `DEBUG_BUILD` is TRUE, the compiler keeps the debug branch. If FALSE, the compiler keeps the production branch. The other branch is omitted from compiled code.

### 1.2. Differences from Runtime IF

Regular `IF` and `CASE` determine execution flow while the program runs. Conditional compilation determines which branches exist in the compiled unit.

| Criterion | Runtime IF | Conditional Compilation |
|---|---|---|
| Decision timing | At runtime | At compile time |
| Condition | Can use variables, parameters, runtime data | Static expression / compile-time flag |
| Unselected branch | Still compiled | Excluded from compiled unit |
| Purpose | Business control flow | Differences by version/build/configuration |
| Changing behavior | Change inputs/runtime state | Must recompile to switch branches |

Runtime example:

```sql
IF p_debug_mode THEN
    DBMS_OUTPUT.PUT_LINE('Debug');
ELSE
    NULL;
END IF;
```

Compile-time example:

```sql
$IF $$DEBUG_BUILD $THEN
    DBMS_OUTPUT.PUT_LINE('Debug');
$ELSE
    NULL;
$END
```

Do not use conditional compilation for business conditions that must vary per request. That belongs in runtime `IF` statements or data-driven configuration.

### 1.3. When Should It Be Used?

Appropriate use cases:

- Supporting multiple Oracle versions with differing APIs or syntax.
- Enabling/disabling instrumentation or diagnostic code between development and production.
- Selecting an implementation by platform or build profile.
- Enabling experimental features when compiling a dedicated build.
- Dropping backward-compatibility code when building for newer database versions.
- Embedding build/unit info into logs or diagnostic output.

Conditional compilation is not an authorization mechanism. Never rely on compile flags to decide whether a user is allowed to view or modify data.

## 2. Compile-Time Flags and PLSQL_CCFLAGS

### 2.1. Declaring Flags

The `PLSQL_CCFLAGS` parameter accepts a comma-separated list of name/value pairs:

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'debug:TRUE, trace:FALSE, feature_orders:TRUE';
```

Flags can hold static Boolean or integer values. Flag names are referenced in source with two dollar signs:

```sql
$IF $$DEBUG $THEN
    -- Compile debug branch
$END
```

The flag name in the example is `DEBUG`. Flags are supplied at compile time, not PL/SQL variables assigned at runtime.

### 2.2. Using Multiple Flags

```sql
$IF $$FEATURE_ORDERS AND NOT $$TRACE $THEN
    DBMS_OUTPUT.PUT_LINE('Orders feature without trace');
$ELSIF $$TRACE $THEN
    DBMS_OUTPUT.PUT_LINE('Trace build');
$ELSE
    NULL;
$END
```

Conditional expressions can combine Boolean operators and static values. Define explicit defaults in build scripts to avoid relying on undeclared flags.

### 2.3. Numeric Values

Numeric flags can represent compatibility levels or implementation choices:

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'api_level:2, debug:FALSE';
```

In source:

```sql
$IF $$API_LEVEL >= 2 $THEN
    l_result := new_api_call();
$ELSE
    l_result := legacy_api_call();
$END
```

Numeric values must be static values valid under `PLSQL_CCFLAGS` rules. Never pass runtime strings or user content into compile flags.

### 2.4. Combining Flags with Packages

```sql
CREATE OR REPLACE PACKAGE build_features AS
    FUNCTION feature_name RETURN VARCHAR2;
END build_features;
/

CREATE OR REPLACE PACKAGE BODY build_features AS
    FUNCTION feature_name RETURN VARCHAR2 IS
    BEGIN
        $IF $$FEATURE_ORDERS $THEN
            RETURN 'ORDERS_ENABLED';
        $ELSE
            RETURN 'ORDERS_DISABLED';
        $END
    END;
END build_features;
/
```

When changing flags and recompiling the package body, the chosen implementation changes. If the package specification stays unchanged, callers usually do not need signature changes, though deployment and dependency checks still apply.

### 2.5. Undeclared Flags

Do not rely on implicit values for unconfigured flags. Always set `PLSQL_CCFLAGS` completely in your build pipeline and inspect stored object settings after compilation. In multi-profile environments, record compile flags in artifact/build metadata for exact reproducibility.

## 3. Inquiry Directives

Inquiry directives are values provided by the compiler during compilation. They are written with a `$$` prefix and can be used in static expressions or eligible PL/SQL code.

### 3.1. $$PLSQL_UNIT

`$$PLSQL_UNIT` returns the name of the PL/SQL unit currently being compiled. It can be used for diagnostics:

```sql
CREATE OR REPLACE PROCEDURE process_orders AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Unit=' || $$PLSQL_UNIT
    );
END;
/
```

Unit names are useful when similar code or helpers are compiled across multiple objects.

### 3.2. $$PLSQL_LINE

`$$PLSQL_LINE` provides the source line number at the directive's position. It is useful for tracing or error context:

```sql
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'At line ' || $$PLSQL_LINE ||
        ' in ' || $$PLSQL_UNIT
    );
END;
```

When source code changes, line numbers shift accordingly. Do not use line numbers as durable business identifiers.

### 3.3. Other Inquiry Directives

Oracle provides additional directives about the unit and compile environment, depending on version:

| Directive | Meaning |
|---|---|
| $$PLSQL_UNIT | Name of the unit being compiled |
| $$PLSQL_LINE | Source line number at the directive's location |
| $$PLSQL_UNIT_OWNER | Owner of the unit in supported versions |
| $$PLSQL_UNIT_TYPE | Type of the unit in supported versions |
| $$PLSQL_COMPILATION_PARAMETER('name') | Compiler parameter value used for the compilation |
| $$flag_name | Compile-time flag value provided by PLSQL_CCFLAGS |

Verify the list of supported directives in your exact Oracle release. Do not assume newer directives exist on every database version.

### 3.4. Reading Compiler Parameters

`$$PLSQL_COMPILATION_PARAMETER` lets source code inspect a compiler parameter's value at compile time:

```sql
CREATE OR REPLACE PROCEDURE show_compile_settings AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Optimize level=' ||
        $$PLSQL_COMPILATION_PARAMETER('PLSQL_OPTIMIZE_LEVEL')
    );
    DBMS_OUTPUT.PUT_LINE(
        'Code type=' ||
        $$PLSQL_COMPILATION_PARAMETER('PLSQL_CODE_TYPE')
    );
END;
/
```

This is the value bound to the current compilation, not a dynamic query of instance parameters on every call. Recompiling with different settings changes the value embedded in the unit.

### 3.5. Using Directives in Diagnostics

```sql
CREATE OR REPLACE PROCEDURE log_compile_context AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Unit=' || $$PLSQL_UNIT ||
        ', line=' || $$PLSQL_LINE ||
        ', optimize=' ||
        $$PLSQL_COMPILATION_PARAMETER('PLSQL_OPTIMIZE_LEVEL')
    );
END;
/
```

Avoid printing this information on every production request if it creates excessive log volume. It is useful in diagnostics, support bundles, or leveled logging.

## 4. Conditional Compilation Structure

### 4.1. $IF, $ELSIF, $ELSE, and $END

A selection directive starts with `$IF` and ends with `$END`. You can have multiple `$ELSIF` branches and one `$ELSE`:

```sql
$IF $$API_LEVEL >= 3 $THEN
    l_result := implementation_v3();
$ELSIF $$API_LEVEL = 2 $THEN
    l_result := implementation_v2();
$ELSE
    l_result := implementation_v1();
$END
```

Each branch must be valid PL/SQL when selected. Ensure branches satisfy the same datatypes/contracts required for the rest of the code to compile.

### 4.2. Nested Conditional Compilation

```sql
$IF $$FEATURE_ORDERS $THEN
    $IF $$DEBUG $THEN
        log_debug('Orders enabled');
    $END
    process_orders;
$ELSE
    raise_application_error(-20091, 'Orders feature unavailable');
$END
```

Nesting helps when a branch depends on multiple conditions. Keep nesting shallow and give flags descriptive names so readers understand build profiles.

### 4.3. In Declaration Sections

You can conditionally compile constants, variables, or subprograms:

```sql
CREATE OR REPLACE PACKAGE BODY build_config AS
    $IF $$DEBUG $THEN
        c_log_level CONSTANT PLS_INTEGER := 5;
    $ELSE
        c_log_level CONSTANT PLS_INTEGER := 1;
    $END

    PROCEDURE show_level IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(c_log_level);
    END;
END build_config;
/
```

Names and types referenced later must exist across every supported profile.

### 4.4. Selecting Implementations by Version

Example selecting code based on database version:

```sql
$IF DBMS_DB_VERSION.VERSION >= 12 $THEN
    -- Implementation for newer versions.
$ELSE
    -- Backward-compatible implementation.
$END
```

`DBMS_DB_VERSION` provides Oracle version constants. Verify the exact version/feature boundary of the APIs you need; do not infer a feature exists solely because a major version threshold was reached.

### 4.5. $ERROR to Intentionally Fail Compilation

The `$ERROR` directive lets the compiler raise a developer-defined error when build requirements are unmet:

```sql
$IF $$API_LEVEL < 2 $THEN
    $ERROR 'This package requires API_LEVEL 2 or later' $END
$END
```

This fails the build early on incompatible configurations. Error text should clearly state the requirement and how the flag must be set.

## 5. Version-Based and Feature-Based Conditional Compilation

### 5.1. Version Checks

When a package supports multiple Oracle releases, conditional compilation can choose the appropriate implementation:

```sql
$IF DBMS_DB_VERSION.VERSION >= 19 $THEN
    -- Branch for newer releases.
$ELSE
    -- Legacy-compatible branch.
$END
```

Version checks should align with actual features and supported releases/RUs. Availability may depend on patch level, options, or configuration, not just major version.

### 5.2. Build Feature Flags

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'feature_bulk_api:TRUE, feature_json:FALSE';
```

```sql
$IF $$FEATURE_BULK_API $THEN
    call_bulk_implementation;
$ELSE
    call_legacy_implementation;
$END
```

Compile-time flags work well for producing distinct build artifacts. They are not runtime feature toggles that administrators can flip without recompiling.

### 5.3. Avoid Unmanageable Build Sprawl

If every customer or environment uses a bespoke combination of flags, artifact permutations multiply rapidly. Maintain a clear matrix:

| Profile | DEBUG | FEATURE_ORDERS | API_LEVEL | Purpose |
|---|---:|---:|---:|---|
| Development | TRUE | TRUE | 3 | Debugging and feature testing |
| Test | FALSE | TRUE | 3 | Production-like testing |
| Production | FALSE | TRUE | 3 | Deployment artifact |
| Legacy | FALSE | FALSE | 2 | Legacy system compatibility |

Never ship untested profiles. Record build flags, compiler settings, and database release alongside every artifact.

### 5.4. Do Not Store Sensitive Data in Flags

Flags are stored in compile settings and visible through data dictionary views depending on privileges. Never put passwords, secrets, tokens, or user data in `PLSQL_CCFLAGS`. Compile-time flags are build configuration, not a secrets store.

## 6. Compiler Warnings

### 6.1. Warnings Differ from Compile Errors

A compiler warning reports suspicious or suboptimal code patterns. Warnings typically do not prevent an object from being created unless configured to escalate warnings to errors.

Oracle uses warning codes formatted as `PLW-nnnnn`. Warnings are not runtime exceptions and do not prove a program is wrong, but they should be reviewed before release.

### 6.2. Enabling All Warnings

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
```

This setting applies to subsequent compilations in the session within compiler support limits. If warnings are enabled in one session while builds run in another, settings may differ.

### 6.3. Enabling by Category

Oracle supports three primary warning categories:

- SEVERE: serious issues.
- PERFORMANCE: performance improvement opportunities.
- INFORMATIONAL: supplemental information.

Example:

```sql
ALTER SESSION SET PLSQL_WARNINGS =
    'ENABLE:SEVERE, ENABLE:PERFORMANCE';
```

You can enable or disable by category and by specific warning number. Define a project-wide policy rather than relying on ad-hoc personal settings.

### 6.4. Disabling Warnings

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'DISABLE:ALL';
```

Disabling warnings can hide important issues. In CI/build pipelines, enable at least `SEVERE` and preferably `ALL` for full visibility; if a warning must be suppressed, document the rationale and narrow its scope.

### 6.5. Escalating Warnings to Errors

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'ERROR:06002';
```

You can promote specific warnings or categories to compile errors. Example policy:

```sql
ALTER SESSION SET PLSQL_WARNINGS =
    'ENABLE:ALL, ERROR:06002';
```

When the compiler detects a warning promoted to an error, compilation fails. This is effective for blocking anti-patterns from entering builds.

## 7. Warning Examples and How to Read Them

### 7.1. Unreachable Code

An unreachable branch can trigger a warning:

```sql
CREATE OR REPLACE PROCEDURE unreachable_demo AS
BEGIN
    RETURN;
    DBMS_OUTPUT.PUT_LINE('This statement cannot run');
END;
/
```

The compiler may report `PLW-06002` for unreachable code. Review control flow to remove dead code or fix conditions/returns.

### 7.2. OTHERS Handler That Does Not Re-Raise

Example:

```sql
CREATE OR REPLACE PROCEDURE swallow_error_demo AS
BEGIN
    risky_operation;
EXCEPTION
    WHEN OTHERS THEN
        log_error(SQLERRM);
        -- No RAISE: caller may assume the operation succeeded.
END;
/
```

The compiler can warn `PLW-06009` when an `OTHERS` handler does not end with `RAISE` or `RAISE_APPLICATION_ERROR`. Usually a better pattern is:

```sql
EXCEPTION
    WHEN OTHERS THEN
        log_error(SQLERRM);
        RAISE;
```

If an error is intentionally translated into a business return status, make the contract explicit and ensure the caller receives complete error representation.

### 7.3. Performance Warnings

Some warnings highlight optimization hints such as parameters that might benefit from `NOCOPY` or expressions/variables that could be written more efficiently. Never blindly add `NOCOPY` just to silence a warning: `NOCOPY` can change semantics when an exception occurs because an `OUT`/`IN OUT` parameter may already be partially modified.

Read the specific warning number and Oracle documentation before changing code. Performance warnings are suggestions to evaluate via benchmarks, not mandatory directives.

### 7.4. Warnings Do Not Replace Testing

The compiler cannot prove business logic correctness, transaction correctness, or runtime data validity. Enabling warnings is one static control layer to combine with unit/integration tests, static analysis, and runtime monitoring.

## 8. Reading Compiler Warnings and Errors

### 8.1. USER_ERRORS

After compiling, inspect errors and warnings:

```sql
SELECT name,
       type,
       sequence,
       line,
       position,
       attribute,
       message_number,
       text
FROM user_errors
ORDER BY name, type, sequence;
```

`ATTRIBUTE` and `MESSAGE_NUMBER` distinguish `ERROR` vs. `WARNING` and show the message code. Use `ALL_ERRORS`/`DBA_ERRORS` when broader scope is needed and privileges permit.

### 8.2. Filtering by Object

```sql
SELECT name,
       type,
       line,
       position,
       attribute,
       text
FROM user_errors
WHERE name = 'UNREACHABLE_DEMO'
ORDER BY sequence;
```

Object names in the data dictionary are normally stored in uppercase unless created as quoted identifiers.

### 8.3. SHOW ERRORS

In SQL*Plus or SQLcl:

```sql
SHOW ERRORS PROCEDURE unreachable_demo;
```

`SHOW ERRORS` is convenient for interactive work. In build automation, querying data dictionary views is usually easier to collect and archive.

### 8.4. Checking Object Status

```sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_name = 'UNREACHABLE_DEMO';
```

An `INVALID` object typically has compilation errors or dependency issues to resolve. A `VALID` object can still carry warnings; warnings do not automatically make an object invalid.

## 9. DBMS_WARNING

### 9.1. Controlling Warnings Programmatically

`DBMS_WARNING` provides an API to read and set warning settings from PL/SQL:

```sql
DECLARE
    l_old_setting VARCHAR2(4000);
BEGIN
    l_old_setting :=
        DBMS_WARNING.GET_WARNING_SETTING_STRING('SESSION');

    DBMS_WARNING.SET_WARNING_SETTING_STRING(
        'ENABLE:ALL',
        'SESSION'
    );

    -- Perform required compilations in the session.

    DBMS_WARNING.SET_WARNING_SETTING_STRING(
        l_old_setting,
        'SESSION'
    );
END;
/
```

The example demonstrates saving the previous setting and restoring it afterward. Changing settings without restoring them can unexpectedly affect subsequent compilations in the same session.

### 9.2. SESSION and SYSTEM Scopes

`DBMS_WARNING` supports `SESSION` and `SYSTEM` scopes per API. Changing `SYSTEM` alters wider defaults and requires appropriate privileges; never change system-wide warning policy just to compile one module.

### 9.3. Setting by Warning Number

`DBMS_WARNING` provides APIs for specific warning numbers, such as `GET_WARNING_SETTING_NUM` and `ADD_WARNING_SETTING_NUM`. Use these when managing individual warning codes programmatically. Check warning names and categories against your Oracle release.

### 9.4. When to Use DBMS_WARNING

Suitable for PL/SQL-driven build/deployment scripts or administrative tools that need to save and restore warning policies. For straightforward SQL pipelines, `ALTER SESSION SET PLSQL_WARNINGS` is usually easier to read.

## 10. Important Compiler Parameters

Compiler parameters affect how PL/SQL units are generated. Manage them as part of your build configuration.

### 10.1. PLSQL_OPTIMIZE_LEVEL

`PLSQL_OPTIMIZE_LEVEL` controls PL/SQL optimization intensity. Common levels:

| Level | General Meaning |
|---:|---|
| 0 | Minimal optimization, helpful for certain debugging/compatibility scenarios |
| 1 | Basic optimizations |
| 2 | Typical default in modern releases |
| 3 | Aggressive optimization, potentially including more inlining opportunities |

Example:

```sql
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
```

Higher optimization does not guarantee every program runs faster. Measure real workloads, verify behavior, and review routines with side effects or execution-order dependencies.

### 10.2. PLSQL_CODE_TYPE

`PLSQL_CODE_TYPE` selects code generation mode:

- INTERPRETED: PL/SQL executes via the interpreted runtime.
- NATIVE: PL/SQL compiles to native code per database/platform capabilities and configuration.

Example:

```sql
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
```

`NATIVE` can improve CPU-bound PL/SQL workloads, though you must consider platform requirements, native compilation setup, compile times, operations, and deployment portability. Never assume native is automatically faster for every application.

### 10.3. PLSQL_WARNINGS

`PLSQL_WARNINGS` defines the warning policy: `ENABLE`, `DISABLE`, or `ERROR` by `ALL`, category, or warning number. This setting determines which messages are emitted and which warnings fail compilation.

### 10.4. PLSQL_CCFLAGS

`PLSQL_CCFLAGS` passes compile-time flags for conditional compilation. Manage values consistently in build scripts; changing flags requires recompiling units to switch selected branches.

### 10.5. PLSQL_DEBUG

`PLSQL_DEBUG` relates to debug information generation for compatible releases/tools. Usage and necessity depend on Oracle version and debugger. Do not confuse `PLSQL_DEBUG` with an application flag named `DEBUG` or with printing `DBMS_OUTPUT`. Check documentation for your running release before standardizing this setting.

### 10.6. PLSCOPE_SETTINGS

`PLSCOPE_SETTINGS` controls compiler metadata collection for PL/SQL identifiers and statements, supporting source/dependency analysis:

```sql
ALTER SESSION SET PLSCOPE_SETTINGS =
    'IDENTIFIERS:ALL, STATEMENTS:ALL';
```

Metadata can be queried via `USER_IDENTIFIERS` and `USER_STATEMENTS` in supported releases. Collecting extra metadata incurs some storage/compile overhead; enable according to code analysis and tooling needs.

### 10.7. NLS_LENGTH_SEMANTICS

`NLS_LENGTH_SEMANTICS` can affect `CHAR`/`VARCHAR2` length declarations when compiling source that omits explicit `BYTE` or `CHAR` qualifiers. Consequently, identical source compiled in sessions with differing `NLS_LENGTH_SEMANTICS` can yield different metadata. Prefer explicit `CHAR`/`BYTE` semantics in critical schemas/source and record build settings.

## 11. Scope and How to Apply Compiler Settings

### 11.1. ALTER SESSION

`ALTER SESSION` changes settings for the current session and affects subsequent eligible compilations:

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
ALTER SESSION SET PLSQL_CCFLAGS = 'debug:FALSE, feature_orders:TRUE';
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
```

This is typically the cleanest approach for build scripts connecting via a dedicated session.

### 11.2. ALTER SYSTEM

`ALTER SYSTEM` sets values at the instance/system level depending on parameter modifiability and chosen scope:

```sql
ALTER SYSTEM SET PLSQL_WARNINGS = 'ENABLE:ALL' SCOPE=BOTH;
```

This requires appropriate DBA privileges and affects multiple sessions/builds. Never use `ALTER SYSTEM` inside a module build script when `ALTER SESSION` suffices.

### 11.3. Object-Level Compile Options

You can pass compiler options when recompiling a single object:

```sql
ALTER PROCEDURE unreachable_demo COMPILE
    PLSQL_WARNINGS = 'ENABLE:ALL';
```

For packages, specification and body can be compiled separately:

```sql
ALTER PACKAGE build_features COMPILE SPECIFICATION;
ALTER PACKAGE build_features COMPILE BODY;
```

Verify exact `ALTER ... COMPILE` syntax for your object type and Oracle release.

### 11.4. REUSE SETTINGS

`REUSE SETTINGS` instructs Oracle to reuse the compiler settings previously stored with the object when recompiling, instead of picking up the current session's defaults in the usual manner.

Example:

```sql
ALTER PROCEDURE unreachable_demo COMPILE REUSE SETTINGS;
```

This is helpful when recompiling an object while preserving its prior build configuration. When you want to change flags or warnings, pass new settings via supported syntax or recreate the object in a properly configured build session.

### 11.5. CREATE OR REPLACE

`CREATE OR REPLACE` creates/compiles the unit using the compiler settings active in the compilation environment. Build scripts must therefore configure parameters before executing DDL to create packages/procedures/functions.

Never assume an object created on a developer laptop receives the same settings as one created in CI or production.

## 12. Inspecting Settings Used by an Object

### 12.1. USER_PLSQL_OBJECT_SETTINGS

The `USER_PLSQL_OBJECT_SETTINGS` view stores compiler settings for PL/SQL objects in the schema:

```sql
SELECT name,
       type,
       plsql_optimize_level,
       plsql_code_type,
       plsql_debug,
       plsql_warnings,
       plsql_ccflags,
       plscope_settings,
       nls_length_semantics
FROM user_plsql_object_settings
ORDER BY type, name;
```

`ALL_PLSQL_OBJECT_SETTINGS` or `DBA_PLSQL_OBJECT_SETTINGS` can be used for wider scope if privileges allow. View columns can vary by release; inspect your system's data dictionary.

### 12.2. Comparing Across Objects

```sql
SELECT name,
       type,
       plsql_optimize_level,
       plsql_code_type,
       plsql_warnings,
       plsql_ccflags
FROM user_plsql_object_settings
WHERE name IN ('BUILD_FEATURES', 'SHOW_COMPILE_SETTINGS')
ORDER BY name, type;
```

If a package spec/body pair or units in the same module show inconsistent settings, determine whether that is intentional or build drift.

### 12.3. Recording a Build Manifest

A build manifest can record:

- Oracle database version/RU.
- Schema owner and object list.
- `PLSQL_OPTIMIZE_LEVEL`.
- `PLSQL_CODE_TYPE`.
- `PLSQL_WARNINGS`.
- `PLSQL_CCFLAGS`.
- `PLSCOPE_SETTINGS`.
- `NLS_LENGTH_SEMANTICS`.
- Source revision/build ID.

A manifest enables reproducible artifacts and diagnosing environment discrepancies.

## 13. Example Controlled Compilation Workflow

### 13.1. Configure Compiler Settings

```sql
ALTER SESSION SET PLSQL_WARNINGS = 'ENABLE:ALL';
ALTER SESSION SET PLSQL_CCFLAGS =
    'debug:FALSE, feature_orders:TRUE, api_level:3';
ALTER SESSION SET PLSQL_OPTIMIZE_LEVEL = 2;
ALTER SESSION SET PLSQL_CODE_TYPE = INTERPRETED;
ALTER SESSION SET PLSCOPE_SETTINGS =
    'IDENTIFIERS:ALL, STATEMENTS:ALL';
```

### 13.2. Create the Object

```sql
CREATE OR REPLACE PROCEDURE compile_profile_demo AS
BEGIN
    $IF $$DEBUG $THEN
        DBMS_OUTPUT.PUT_LINE('Diagnostic enabled');
    $END

    $IF $$FEATURE_ORDERS $THEN
        DBMS_OUTPUT.PUT_LINE('Orders feature enabled');
    $ELSE
        DBMS_OUTPUT.PUT_LINE('Orders feature disabled');
    $END
END;
/
```

### 13.3. Inspect Warnings/Errors

```sql
SELECT name, type, line, position, attribute, text
FROM user_errors
WHERE name = 'COMPILE_PROFILE_DEMO'
ORDER BY sequence;
```

### 13.4. Inspect Object Status and Settings

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name = 'COMPILE_PROFILE_DEMO';

SELECT name,
       type,
       plsql_optimize_level,
       plsql_code_type,
       plsql_warnings,
       plsql_ccflags,
       plscope_settings
FROM user_plsql_object_settings
WHERE name = 'COMPILE_PROFILE_DEMO';
```

### 13.5. Build Another Profile

```sql
ALTER SESSION SET PLSQL_CCFLAGS =
    'debug:TRUE, feature_orders:FALSE, api_level:2';

CREATE OR REPLACE PROCEDURE compile_profile_demo AS
BEGIN
    $IF $$DEBUG $THEN
        DBMS_OUTPUT.PUT_LINE('Diagnostic enabled');
    $END

    $IF $$FEATURE_ORDERS $THEN
        DBMS_OUTPUT.PUT_LINE('Orders feature enabled');
    $ELSE
        DBMS_OUTPUT.PUT_LINE('Orders feature disabled');
    $END
END;
/
```

This compilation produces a different artifact. When maintaining multiple profiles, track source revision and settings separately for each artifact.

## 14. Impact on Dependencies and Deployment

### 14.1. Conditional Compilation Alters Object Contents

Two compilations of identical source with differing `PLSQL_CCFLAGS` can produce different implementations. This can affect:

- Procedure/function behavior.
- Dependencies on objects referenced in only one branch.
- Compiled SQL statements.
- Runtime performance and diagnostics.
- Package body size and metadata.

### 14.2. Out-of-Sync Compile Flags Across Objects

If package A is compiled with `FEATURE_X=TRUE` while package B is compiled with `FALSE`, the two objects may expect incompatible contracts. Build pipelines must apply a consistent profile across all interdependent objects.

### 14.3. Recompiling Dependent Objects

Changing a package specification or object dependency can cause Oracle to invalidate dependent objects. Conditional compilation does not bypass dependency rules. After deployment, inspect `USER_OBJECTS`, `USER_ERRORS`, and recompile in dependency order.

### 14.4. Reproducing Artifacts

Do not store source code alone. Store database version, compiler parameters, flags, and build scripts. Without flags, recompiling on another environment can select a different branch even with unchanged source.

### 14.5. Deployment Rollback

If a new build fails, rollback must restore both the corresponding source and compiler settings. Running `CREATE OR REPLACE` with old source under new flags can produce an artifact different from the prior release. Retain previous artifact manifests for exact reconstruction.

## 15. Common Errors and Misconceptions

| Symptom | Cause | Resolution |
|---|---|---|
| Debug branch still appears after changing flag | Object was not recompiled | Recompile object after changing PLSQL_CCFLAGS |
| Flag holds unexpected value | Build session omitted flag or misspelled name/value | Check compile script and USER_PLSQL_OBJECT_SETTINGS |
| Code using newer API fails to compile | Conditional branch picked incompatible implementation | Verify version/flags and compilation environment |
| Warnings do not appear | PLSQL_WARNINGS disabled or compiled in another session | Enable warnings in the actual build session |
| Warnings fail the build | Category or warning code set to ERROR | Review policy and specific PLW code |
| Object is VALID yet has warnings | Warnings are not compile errors | Query USER_ERRORS and decide remediation |
| Recompile uses different settings | REUSE SETTINGS omitted or session defaults differ | Set parameters explicitly and verify metadata |
| Dev build differs from production | Flags/parameters/versions differ | Use controlled profiles and build manifests |
| NLS lengths differ across environments | Differing NLS_LENGTH_SEMANTICS | Declare CHAR/BYTE explicitly and standardize settings |
| Warnings swallowed by pipeline | Script only checks exit code or INVALID objects | Query USER_ERRORS and fail per warning policy |

## 16. Design and Operational Guidelines

### 16.1. Keep the Number of Compile Profiles Small

Every profile multiplies artifacts to build, test, and deploy. Create profiles only for clear purposes, such as DEV, TEST, PROD, or a supported legacy profile.

### 16.2. Use Descriptive Flag Names

Names like `DEBUG`, `FEATURE_ORDERS`, and `API_LEVEL` are clearer than cryptic short flags. Document valid values and defaults.

### 16.3. Always Set Flags Explicitly

Build scripts must explicitly set all required flags before compiling. Never rely on leftover session state from an earlier build step.

### 16.4. Enable Warnings in CI

CI should compile under a fixed warning policy, collect `USER_ERRORS`, and fail on errors or policy-escalated warnings. Never rely solely on `VALID` object status.

### 16.5. Escalate Warnings Intentionally

`ERROR:ALL` can break builds on legacy or unaddressed warnings. Start with `ENABLE:ALL`, triage warnings, fix or record time-boxed exceptions, and then escalate critical codes to `ERROR`.

### 16.6. Do Not Disable Warnings System-Wide for One Object

Use `ALTER SESSION` or object-level compile options when adjusting a single build. Reserve `ALTER SYSTEM` for deliberate global administrative decisions.

### 16.7. Measure Before Changing Optimize/Code Type

Changing `PLSQL_OPTIMIZE_LEVEL` or `PLSQL_CODE_TYPE` can affect compile time, runtime performance, debugging, and operations. Benchmark with representative workloads and record settings per artifact.

### 16.8. Conditional Compilation Does Not Replace Versioned APIs

If alternative implementations have substantially different contracts, consider adapter packages or separate modules. Do not cram excessive compile-time branches into a hard-to-read package.

## 17. Hands-on Exercises

Run these in a dedicated lab schema without modifying system-wide compiler settings.

### Step 1 — Basic Compile Profile

Set `PLSQL_CCFLAGS` with `DEBUG` TRUE and `FEATURE_ORDERS` FALSE. Create a procedure with two conditional compilation branches. Compile and observe output.

### Step 2 — Change Flags

Switch `DEBUG` to FALSE and `FEATURE_ORDERS` to TRUE, then recompile the procedure. Compare output and `USER_PLSQL_OBJECT_SETTINGS`.

### Step 3 — Inquiry Directives

Create a procedure printing `$$PLSQL_UNIT`, `$$PLSQL_LINE`, and `PLSQL_OPTIMIZE_LEVEL` via `$$PLSQL_COMPILATION_PARAMETER`. Edit source lines to observe the line number change.

### Step 4 — Version Branch

Create two branches based on `DBMS_DB_VERSION` or an `API_LEVEL` compile flag. Compile on a supported database release and verify which branch was selected.

### Step 5 — Test $ERROR

Set `API_LEVEL` lower than required and use `$ERROR` to make compilation fail. Fix the flag and recompile.

### Step 6 — Enable Compiler Warnings

Set `PLSQL_WARNINGS` to `ENABLE:ALL`. Create a procedure with unreachable code and an `OTHERS` handler without `RAISE`. Inspect warning codes in `USER_ERRORS`.

### Step 7 — Escalate a Warning to Error

Pick a specific warning code and set `ERROR` for it. Recompile and observe object status and messages.

### Step 8 — DBMS_WARNING

Read the current warning setting, alter it at `SESSION` scope, then restore it. Confirm the final setting matches the initial one.

### Step 9 — Compiler Parameters

Compile a procedure at optimize level 2, then test level 3. Measure compile time and runtime on a stable workload. Do not draw conclusions from a single run.

### Step 10 — PLSCOPE

Enable `IDENTIFIERS` and `STATEMENTS`, and compile a package. Query `USER_IDENTIFIERS`/`USER_STATEMENTS` if supported by your release.

### Step 11 — REUSE SETTINGS

Compile an object with chosen flags/warnings. Recompile using `REUSE SETTINGS` and inspect `USER_PLSQL_OBJECT_SETTINGS`. Compare against compiling in a session with new settings.

### Step 12 — Build Manifest

Create a manifest file recording database version, source revision, flags, warnings, optimize level, code type, PLSCOPE, and `NLS_LENGTH_SEMANTICS`. Reproduce the build in another environment and compare.

## 18. Self-Check Questions

1. At what stage does conditional compilation choose code branches?
2. How does conditional compilation differ from runtime `IF`?
3. How do `$IF`, `$ELSIF`, `$ELSE`, and `$END` syntax work?
4. What is `PLSQL_CCFLAGS` used for?
5. What syntax references a compile-time flag in source code?
6. Why must flags be set explicitly in a build pipeline?
7. What information do `$$PLSQL_UNIT` and `$$PLSQL_LINE` provide?
8. What is `$$PLSQL_COMPILATION_PARAMETER` used for?
9. When should `DBMS_DB_VERSION` be used in conditional compilation?
10. How does `$ERROR` help enforce build controls?
11. How do compiler warnings differ from compile errors?
12. What do the `SEVERE`, `PERFORMANCE`, and `INFORMATIONAL` categories mean?
13. How can `PLSQL_WARNINGS` escalate a warning to an error?
14. Which columns in `USER_ERRORS` store warnings and errors?
15. Why can a `VALID` object still have warnings?
16. Which scopes does `DBMS_WARNING` support?
17. How does `PLSQL_OPTIMIZE_LEVEL` affect compilation?
18. How does `PLSQL_CODE_TYPE` `INTERPRETED` differ from `NATIVE`?
19. What work does metadata collected by `PLSCOPE_SETTINGS` support?
20. How can `NLS_LENGTH_SEMANTICS` affect compiled source?
21. How do `ALTER SESSION` and `ALTER SYSTEM` differ in impact scope?
22. How is `REUSE SETTINGS` useful during recompilation?
23. What does `USER_PLSQL_OBJECT_SETTINGS` help verify?
24. Why must every profile with conditional branches be compiled and tested?
25. Why must conditional compilation never be used as an authorization mechanism?

**Principle to remember:** conditional compilation selects code at compile time; `PLSQL_WARNINGS` controls warnings and can promote warnings to compile errors; compiler parameters govern how PL/SQL is optimized, generated, and instrumented with metadata. Set `PLSQL_CCFLAGS` and compiler settings explicitly in build pipelines, recompile whenever flags change, and inspect `USER_ERRORS` and `USER_PLSQL_OBJECT_SETTINGS` to verify results. Keep profiles minimal, test each profile, and retain build manifests so deployed artifacts can be reproduced accurately.
