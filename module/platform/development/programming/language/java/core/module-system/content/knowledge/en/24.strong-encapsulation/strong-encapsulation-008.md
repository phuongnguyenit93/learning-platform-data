# Evaluating Risks When Using Command-Line Escape Hatches

## Objectives

After this lesson, you will be able to:

- Explain why JPMS provides command-line escape hatches even though the module system encapsulates packages by default.
- Precisely distinguish the effects of `--add-exports`, `--add-opens`, `--add-reads`, and `--patch-module`.
- Recognize the difference between compile-time and runtime access permissions.
- Evaluate compatibility, maintainability, and blast-radius risks of each option.
- Choose long-term fixes instead of keeping access-opening flags indefinitely.
- Establish, test, and manage escape hatches that have narrow scope, an owner, and an expiration plan.

## 1. Why Are Command-Line Escape Hatches Needed?

The Java Platform Module System (JPMS) encapsulates packages inside named modules. A module exposes packages only through `exports` declarations; it can allow deep reflection through `opens`. Other modules must have appropriate readability relationships before using that module's APIs.

Strong encapsulation protects this boundary. When a legacy library needs access to an internal JDK package, or a framework needs reflection into an unopened package, an application may encounter errors such as:

- `package ... is not visible` at compile time.
- `IllegalAccessError` when accessing an unexported type or member.
- `InaccessibleObjectException` when reflection attempts deep access into an encapsulated member.
- `module ... does not read ...` when a readability relationship is missing.

Command-line escape hatches allow operators to relax part of a module boundary for a specific run or build configuration. They are useful during migration, legacy library integration, testing, or dealing with a limitation that cannot be fixed immediately.

However, each flag changes a different rule. Using the wrong flag may fail to resolve the error while making the application configuration broader and harder to control.

## 2. Four Permission Types to Distinguish

Before choosing a flag, identify the exact operation being blocked:

1. **Readability**: is the calling module allowed to read the module containing the API?
2. **Export**: does the package expose public types/members to the calling module?
3. **Open for reflection**: does the package allow deep reflection into non-public members?
4. **Module content**: which classes/resources actually belong to the module's contents?

The corresponding options:

| Option | What Does It Change? | Primary Scope |
|---|---|---|
| `--add-reads` | Adds a readability relationship | Allows one module to read another module |
| `--add-exports` | Exports a package to a target module | Access to public types in the package |
| `--add-opens` | Opens a package for deep reflection | Runtime reflection |
| `--patch-module` | Augments or replaces module contents | Classes/resources loaded as part of the module |

No flag serves as a general way to "turn off JPMS." Identify the missing rule and pick the smallest change.

## 3. --add-exports: Opening Access to a Package's Public API

### 3.1. Meaning

Syntax:

~~~bash
--add-exports <source-module>/<package>=<target-module>
~~~

This option adds a qualified export from the source module's package to the target module. The target module can access public types in that package under Java access rules.

For example, an application depending on the internal `sun.nio.ch` API of `java.base`:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED -d out @sources.txt
~~~

When running the corresponding application on the classpath:

~~~bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp out com.acme.Main
~~~

The two commands illustrate two different phases:

- The flag passed to `javac` allows the compiler to check source code referencing that package.
- The flag passed to `java` creates the corresponding export permission at runtime.

If the application is a named module, specify the target module explicitly instead of using `ALL-UNNAMED`:

~~~bash
java --add-exports java.base/sun.nio.ch=com.acme.app --module-path mods -m com.acme.app/com.acme.Main
~~~

### 3.2. What Does This Flag Not Do?

`--add-exports` does not open a package for deep reflection. It allows access to the package's public API under export rules; it does not automatically allow frameworks to access private fields or invoke private methods via reflection.

It also does not turn an internal API into an API stably supported by the JDK. The package may change or disappear between JDK releases.

### 3.3. Risks

- **High compatibility risk** if the package belongs to internal JDK implementation.
- **Scope risk** if using `ALL-UNNAMED`, because all code in the unnamed module can receive that export permission.
- **Dependency risk** if multiple libraries rely on internal packages and each requires its own flags.
- **Deployment risk** if the flag is added only at compile time while forgetting runtime configuration, or vice versa.

Use `--add-exports` when the real issue is code needing access to public types in an unexported package. If the error is deep reflection, evaluate `--add-opens` rather than adding exports mechanically.

## 4. --add-opens: Allowing Deep Reflection

### 4.1. Meaning

Syntax:

~~~bash
--add-opens <source-module>/<package>=<target-module>
~~~

`--add-opens` opens a package at runtime so the target module can perform deep reflective access, including accessing non-public members when other reflection conditions are satisfied.

For example, a legacy framework needing reflection into private members in package `java.lang`:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

If only one named module needs that permission:

~~~bash
java --add-opens java.base/java.lang=com.acme.framework --module-path mods -m com.acme.app/com.acme.Main
~~~

`ALL-UNNAMED` is a special target representing unnamed modules, typically code running on the classpath. It does not mean every named module receives permission.

### 4.2. Difference from exports

| Criterion | `--add-exports` | `--add-opens` |
|---|---|---|
| Purpose | Access public types in a package | Deep reflection into a package |
| Compile time | Can be used with javac | Not a compile-time option |
| Runtime | Effective | Effective |
| Private fields/methods | Does not grant deep reflection permission | Allows deep reflection under reflection rules |
| Public API change | Creates an export to the target | Does not create an export for ordinary Java access |

If a library calls `setAccessible(true)` or `trySetAccessible()` on a member in a closed package, the error usually involves openness. Adding an export may not solve that error.

### 4.3. Risks

`--add-opens` has a stronger reach than public API access needs: a framework can inspect and manipulate internal package structures. This makes the application brittle when implementations change.

Common risks:

- Frameworks depend on field names, object layouts, or private methods that are not stable contracts.
- JDK or library upgrades can cause reflection to fail even when application code does not change.
- Using `ALL-UNNAMED` can open the package to unexpected libraries on the classpath.
- Errors may surface only on lightly tested execution paths, such as serialization, proxies, ORM, or dependency injection.

Open only the exact required packages and only to the exact target module. Do not open all of `java.base` or every package of a module just to make a reflection error vanish.

## 5. --add-reads: Adding a Readability Relationship

### 5.1. Meaning

Syntax:

~~~bash
--add-reads <source-module>=<target-module>
~~~

This option adds a readability edge: the source module is allowed to read the target module. It neither exports packages nor opens packages.

For example, named module `com.acme.app` needs to read code in the unnamed module:

~~~bash
java --add-reads com.acme.app=ALL-UNNAMED --module-path mods -cp legacy-lib.jar -m com.acme.app/com.acme.Main
~~~

Another scenario is when the source module needs to read the target module in a special configuration, yet the current descriptor does not declare the corresponding `requires`.

### 5.2. Readability does not equal accessibility

A module reading another module does not guarantee access to every package of that module.

For code to use a public type, usually all of the following are required simultaneously:

- The calling module has readability to the module containing the type.
- The package containing the type is exported to the calling module.
- The type/member satisfies Java access rules.

If a package is not exported, `--add-reads` does not replace `--add-exports`. If a framework needs deep reflection, `--add-reads` also does not replace `--add-opens`.

### 5.3. Risks

- Makes the module graph depend on deployment configuration instead of descriptors.
- Masks a dependency that has not been declared in `module-info.java`.
- When switching environments or running tests with a different configuration, the readability edge may be missing.
- Creates the illusion that the module has an explicit dependency contract, when in reality it is only wired by runtime flags.

If the dependency is a stable module relationship, consider declaring `requires` in `module-info.java`. Use `--add-reads` for temporary integration cases or when descriptors cannot be edited immediately.

## 6. --patch-module: Altering Module Contents

### 6.1. Meaning

Syntax:

~~~bash
--patch-module <module>=<path>
~~~

`--patch-module` specifies additional or replacement classes/resources loaded as part of the chosen module's contents. It is commonly used in testing, special patch builds, or controlled migration scenarios.

For example, an application already has module `com.acme.app` in the `mods` directory. A patch directory contains compiled classes:

~~~bash
java --patch-module com.acme.app=patch-out --module-path mods -m com.acme.app/com.acme.Main
~~~

You can use `javac` to compile patch sources in the context of the module:

~~~bash
javac --module-path mods --patch-module com.acme.app=src/patch -d patch-out @patch-sources.txt
~~~

In these commands:

- `com.acme.app` is the module being patched.
- `patch-out` is the compiled content that will be loaded with the module at runtime.
- `src/patch` is the source path of classes to compile as part of that module.

### 6.2. Patching is neither export nor open

`--patch-module` changes the set of classes/resources belonging to the module. It is not a way to expose packages to other modules.

If the goal is to let other modules access public types, look at exports. If the goal is deep reflection, look at opens. If the goal is adding a read relationship, look at readability.

### 6.3. Risks

- Can replace classes used by the module, causing behavior to differ from the released artifact.
- Patch contents can drift out of sync with the original module version.
- Hard to reproduce bugs if patch paths differ across developer, test, and production environments.
- Can break assumptions about module integrity or create a runtime that does not correspond to the tested/approved artifact.
- When patching a JDK module, compatibility and support risks increase substantially.

Prefer using patches in tests or developer tooling. If a patch must remain in production, manage it as part of the artifact and release process, with versioning, checksums, an owner, and compatibility testing.

## 7. What About --illegal-access?

In early JPMS Java versions, `--illegal-access` supported migration by relaxing reflective access to certain internal JDK packages.

Important status:

- JDK 9 through JDK 15 had a migration period with various warning/permit levels.
- JDK 16 moved to stricter default strong encapsulation.
- Starting in JDK 17, `--illegal-access` is no longer a way to restore the previous broad access behavior. This flag does not replace explicitly scoped options such as `--add-opens` or `--add-exports`.

Do not add `--illegal-access=permit` to modern scripts expecting to resolve module errors. Identify the exact package, source module, target module, and actual type of access required.

## 8. Risk Assessment by Scenario

| Actual Need | Potentially Suitable Flag | Main Risk |
|---|---|---|
| Access public types in an unexported package | `--add-exports` | Dependency on an unpublished package |
| Framework needs deep reflection into private members | `--add-opens` | Dependency on internal implementation |
| Module needs to read another module without a readability edge | `--add-reads` | Dependency hidden in configuration |
| Replace/augment module classes or resources | `--patch-module` | Runtime differs from original artifact |
| Want every package to be accessible | No safe general flag | Scope exceeds need; revisit the design |

A responsible evaluation should answer at least five questions:

1. **Who needs access?** Which specific module is performing the access?
2. **What permission is needed?** Readability, public access, deep reflection, or content modification?
3. **How broad is it needed?** One package, one target module, or all unnamed modules?
4. **How long will it exist?** Just one test, one library version, or the entire application lifecycle?
5. **Is there an exit path?** Can you change the API, upgrade the library, or fix the descriptor?

## 9. Decision Workflow Before Adding a Flag

### Step 1: Identify the root error

Read the full exception and determine:

- Source module.
- Blocked package.
- Target module.
- Error phase: compile time, class loading, ordinary access, or reflection.

Do not choose a flag based merely on keywords like `module` or `access` in the error message.

### Step 2: Confirm the dependency causing the access

Locate the library or code performing the access. For third-party libraries, check the version supporting the current JDK and review vendor issues/documentation.

Use dependency analysis tools when appropriate:

~~~bash
jdeps --jdk-internals application.jar
~~~

This command helps detect references to JDK internal APIs in the analyzed bytecode. The result is an investigative lead; it does not prove every code path fails or identify all dynamic reflection.

You can check module descriptors and dependencies with:

~~~bash
jdeps --check com.acme.app --module-path mods
~~~

### Step 3: Choose the minimal change

- Only missing readability: consider `--add-reads`.
- Need public types in an unexported package: consider `--add-exports`.
- Need deep reflection at runtime: consider `--add-opens`.
- Need to modify classes/resources belonging to a module: consider `--patch-module` and verify why a patch is truly required.

Do not add multiple flags at once to "try making it run." Change one flag at a time, rerun relevant tests, and record which flag actually solves the error.

### Step 4: Restrict the target

Prefer a specific target module:

~~~bash
java --add-opens java.base/java.lang=com.acme.framework --module-path mods -m com.acme.app/com.acme.Main
~~~

Use `ALL-UNNAMED` only when the code needing permission actually runs in the unnamed module, such as a library on the classpath. Do not use it as the default for every situation.

### Step 5: Set an expiration and removal plan

Each escape hatch should document:

- Technical reason and original exception.
- Source module/package and target module.
- Where the flag is configured: test task, application launcher, container, or service script.
- Tested JDK and library versions.
- Owner responsible for removing the flag.
- Condition or target version for removal.

Without an owner and an exit condition, a temporary flag very easily becomes a permanent part of the configuration.

## 10. Risks of Placing Flags in the Wrong Location

A flag can be added across multiple configuration layers:

- Local run command.
- Gradle/Maven test JVM.
- Application plugin or startup script.
- Docker image, service unit, or startup script.
- Environment variables affecting multiple JVM processes.

The same application might run locally yet fail in production because the flag exists in only one environment. Conversely, a flag placed in a global environment variable can silently open permissions for other unrelated JVMs.

Place the flag at the layer closest to the consumer needing permission. For example, if only tests use an older framework requiring reflection, confine the flag to the test JVM. Put it in the production launcher only when the application genuinely requires it and that configuration has been tested.

Avoid letting multiple configuration sources declare different flags without a single canonical place of management. When investigating runtime issues, you must be able to see the exact actual JVM arguments.

## 11. Long-Term Solutions Instead of Escape Hatches

Prioritize in order:

1. **Use public APIs** of the JDK or library instead of internal APIs.
2. **Upgrade the library** to a version supporting strong encapsulation and the target JDK.
3. **Change the integration mechanism** to an SPI, service provider, callback, or documented extension point.
4. **Update the module descriptor** of team-owned modules with appropriate `exports`, qualified exports, `opens`, or `requires`.
5. **Reduce reliance on reflection** into private implementation; use APIs designed for extensibility.
6. **Keep a scoped escape hatch** if immediate replacement is not possible, while creating a removal plan.

If the application's own module needs to grant reflection access to a framework, a qualified `opens` in the descriptor may express the contract more clearly than a launcher flag applied across environments. Still, open only the packages truly needed and only to the exact target module.

Do not treat a JDK internal API as an internally supported dependency merely because `--add-exports` makes the build succeed. Escape hatches do not change the API provider's compatibility commitment.

## 12. Checklist for Reviewing an Escape Hatch

Before merging or releasing a configuration containing an escape hatch, verify:

- [ ] The original exception or technical evidence is recorded.
- [ ] The source module, package, and target module are accurately identified.
- [ ] The correct permission type is selected: reads, exports, opens, or patch.
- [ ] The narrowest possible target is used; `ALL-UNNAMED` is not used unnecessarily.
- [ ] The flag is placed on the right JVM/build task.
- [ ] Tested on the target JDK and library versions.
- [ ] Relevant reflection/class-loading execution paths have been tested.
- [ ] Owner and removal criteria are documented.
- [ ] An issue or migration task exists for the long-term solution.

## Conclusion

Command-line escape hatches are controlled migration and integration tools. `--add-reads` modifies readability; `--add-exports` grants access to public types in a package; `--add-opens` allows deep reflection; `--patch-module` alters contents loaded as part of a module. Each flag addresses a different type of boundary and introduces a distinct form of risk.

Treat every escape hatch as owned compatibility debt: **small scope, specific target, clear configuration location, tested in the right environment, and with a removal condition**. Whenever possible, replace it with public APIs or explicitly declared module contracts.
