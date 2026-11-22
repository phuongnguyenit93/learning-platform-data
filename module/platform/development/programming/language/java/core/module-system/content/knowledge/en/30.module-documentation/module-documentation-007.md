# Documenting Still-Required add-opens or add-exports

## 1. Purpose

When migrating a Java application to the Java Platform Module System (JPMS), certain libraries or frameworks may need access to packages that the owning module has not exported, or deep reflection into packages that have not been opened. During the transition period, the JVM or `javac` may be configured with `--add-exports` and `--add-opens`.

If these flags sit in startup scripts without explanation, maintainers struggle to know why they still exist, which flags are needed at compile time, which are needed at runtime, and when they can be removed. Upgrading JDK versions, replacing frameworks, or building custom runtime images can expose those configuration assumptions.

Therefore, documentation should record for **each access exception**:

1. The exact flag including source module, package, and target module.
2. The component or framework that actually uses the access permission.
3. The error or use case proving the need.
4. Where it applies: `javac`, test JVM, application JVM, plugin host, or container.
5. The tested JDK version and dependency version.
6. Risk level and why it must be kept temporarily.
7. Responsible person/team, alternative approach, and removal criteria.

The goal is to manage genuinely necessary exceptions, not to open access broadly across the board.

## 2. JPMS strong encapsulation mechanics

A named module can contain `public` classes, yet other modules do not automatically gain access to them. If a package has not been exported, regular Java code in another module cannot import public types simply by adding to the module path.

Example engine module:

~~~java
module com.acme.engine {
    exports com.acme.engine.api;
}
~~~

This module exposes package `com.acme.engine.api` but does not expose `com.acme.engine.internal`. Public classes inside `internal` remain implementation details.

For deep reflection, such as a serializer attempting to access private fields via `setAccessible(true)`, an exported package is still not necessarily sufficient. JPMS distinguishes normal Java access permissions from opening a package for deep reflection.

Hence, clearly separate two questions:

- **Can another module import and call public types/members?** Check `requires`/readability and `exports`.
- **Can a framework perform deep reflection on non-public members?** Check `opens` or `--add-opens`.

Setting the wrong flag may fail to fix the error or grant unnecessary permissions.

## 3. Distinguishing related mechanisms

| Mechanism | Function | Phase |
|---|---|---|
| `requires B` | Allows module A to read module B per descriptor | Compile and runtime |
| `exports p` | Exposes public types in package `p` | Compile and runtime |
| `exports p to A` | Exposes package `p` only to module A | Compile and runtime |
| `opens p to A` | Opens `p` for deep reflection from A | Runtime |
| `--add-exports B/p=A` | Adds a temporary qualified export | `javac` or JVM |
| `--add-opens B/p=A` | Adds temporary package opening for deep reflection | JVM runtime |
| `--add-reads A=B` | Adds a readability edge; does not export packages | Per tool/support |

`--add-exports` does not turn private fields into public ones and does not create readability by itself. `--add-opens` is not a way for `javac` to import internal packages. If the runtime reports module not found or a class is actually missing, neither flag replaces fixing the module path or dependencies.

## 4. Syntax must be recorded verbatim

Targeted export:

~~~text
--add-exports <source-module>/<package>=<target-module>[,<target-module>...]
~~~

Targeted package open:

~~~text
--add-opens <source-module>/<package>=<target-module>[,<target-module>...]
~~~

Example exporting a public class in an internal package to a named module:

~~~bash
--add-exports com.acme.engine/com.acme.engine.internal=com.acme.client
~~~

Example opening a model package to a named serializer:

~~~bash
--add-opens com.acme.orders/com.acme.orders.model=com.acme.serializer
~~~

The special target `ALL-UNNAMED` grants permission to unnamed modules, typically code running on the classpath:

~~~bash
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

Do not guess the target module name from a JAR filename or Maven coordinate. Inspect the actual module loading the calling code. If the framework resides in a named module, prefer the specific target instead of `ALL-UNNAMED`.

## 5. Example of --add-exports at compile and run time

Suppose module `engine` contains a public class `EngineFlags` in package `com.acme.engine.internal`, but the descriptor does not export that package.

~~~java
module com.acme.engine {
    // com.acme.engine.internal is not exported
}
~~~

Consumer module:

~~~java
module com.acme.client {
    requires com.acme.engine;
}
~~~

Consumer code:

~~~java
package com.acme.client;

import com.acme.engine.internal.EngineFlags;

public final class Main {
    public static void main(String[] args) {
        System.out.println(EngineFlags.current());
    }
}
~~~

While the client cannot yet be updated to use the official public API, the compile command may require:

~~~bash
javac --module-source-path src \
      --add-exports com.acme.engine/com.acme.engine.internal=com.acme.client \
      -d mods \
      -m com.acme.engine,com.acme.client
~~~

The run command may require the same export permission:

~~~bash
java --module-path mods \
     --add-exports com.acme.engine/com.acme.engine.internal=com.acme.client \
     -m com.acme.client/com.acme.client.Main
~~~

Documentation must record **both where the compiler receives the flag and where the JVM runtime receives the flag**, if both truly need it. Options passed to `javac` are not written into the modular JAR for the launcher to apply automatically.

If code compiles thanks to the flag but lacks it at runtime, an `IllegalAccessError` may occur. Do not keep this access permission as a long-term API; a better fix is replacing the internal class with an interface or public type in an exported package.

## 6. Example of --add-opens for deep reflection

A serialization framework may access private model state:

~~~java
package com.acme.orders.model;

public final class Order {
    private String id;

    private Order() {
    }
}
~~~

Module `orders`:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

If the framework runs inside the named module `com.acme.serializer`, you can temporarily configure:

~~~bash
java --module-path mods \
     --add-opens com.acme.orders/com.acme.orders.model=com.acme.serializer \
     -m com.acme.app/com.acme.app.Main
~~~

If the framework actually sits on the classpath, the target may be `ALL-UNNAMED`:

~~~bash
java --module-path mods \
     --add-opens com.acme.orders/com.acme.orders.model=ALL-UNNAMED \
     -m com.acme.app/com.acme.app.Main
~~~

The two examples are different options for different callers. Use one option only after verifying the framework's actual module identity.

When the source module is under your project's control, the long-term solution may be:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
    opens com.acme.orders.model to com.acme.serializer;
}
~~~

Or replace reflection with supported public accessors, constructors, factories, or DTOs. Do not open the entire module when only one package is needed.

## 7. Each exception needs its own record

A centralized registry helps prevent flags from being duplicated across multiple scripts.

Example summary table:

| ID | Flag | Consuming component | Phase | Owner | Goal |
|---|---|---|---|---|---|
| JPMS-001 | `--add-opens java.base/java.lang=ALL-UNNAMED` | Legacy framework | Test | Platform team | Upgrade framework |
| JPMS-002 | `--add-exports com.acme.engine/com.acme.engine.internal=com.acme.client` | Client module | Compile, Run | Engine team | Public API |
| JPMS-003 | `--add-opens com.acme.orders/com.acme.orders.model=com.acme.serializer` | Serializer | Run | Orders team | Narrow opens/DTO |

Module and framework names in the table are examples; real systems must substitute confirmed artifacts and versions.

For each ID, the detailed record should include:

- Exact source module name, package, and target module.
- Which functionality uses the permission (class or framework).
- Stack trace, compile error, or test case proving the need.
- Which tools/processes receive the configuration.
- Verified JDK vendor, version, and dependency version.
- Risk and breadth of the opened permission.
- Owner and review date or release milestone.
- Long-term solution and flag removal criteria.

A table simply listing flags is insufficient if readers still do not know why each flag exists.

## 8. Markdown record template for repository use

A centralized document can be stored at `docs/jpms-access-exceptions.md`:

~~~markdown
### JPMS-003 — Serializer accessing Orders model

- Option: --add-opens com.acme.orders/com.acme.orders.model=com.acme.serializer
- Source: com.acme.orders / com.acme.orders.model
- Target: com.acme.serializer (named module)
- Caller: serializer when reading private fields
- Symptom without flag: InaccessibleObjectException
- Reproduction: order processing integration test
- Required in: application JVM, integration test JVM
- Not required in: javac
- Configuration owner: Orders team
- JDK tested: specify exact version/vendor
- Dependency tested: specify group, artifact, version
- Risk: exposes private members in the model package to the serializer
- Alternative: public DTO/constructor or qualified opens in descriptor
- Removal criterion: tests and release launcher pass without the option
- Tracking issue: link to issue or PR
- Status: still required
~~~

Do not fill in “tested” values without real verification data. If an item has not been verified, mark it unverified with the corresponding release constraint rather than guessing module names or versions.

## 9. How to prove a flag is still required

You need a reproducible test rather than relying solely on word-of-mouth explanations.

Recommended procedure:

1. Pin the current JDK, artifacts, and run command.
2. Confirm the use case works when the option is present.
3. In a test environment, remove only the option under evaluation.
4. Re-run the use case that exercises the access permission.
5. Capture the exception, stack trace, source package, and caller module.
6. Restore the option and confirm the use case works again.
7. Record the findings in the exception entry.

Examples:

- “Package not visible” at compile time indicates checking readability/`exports`.
- `IllegalAccessError` at runtime may relate to regular bytecode access.
- `InaccessibleObjectException` usually relates to deep reflection.
- “Module not found” is normally a module path/name problem and is not fixed by `opens`.

Never test removing flags directly in production if doing so could disrupt service. Run every step in a test environment with equivalent data and use cases.

## 10. Verifying the actual module name and caller

Maven artifact names, Gradle project paths, or JAR filenames are not necessarily JPMS module names. Inspect the descriptor:

~~~bash
jar --describe-module --file libs/example.jar
~~~

For a system module:

~~~bash
java --describe-module java.base
~~~

Observe the module graph at runtime:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

If diagnostic code can be executed, inspect a class's module identity via:

~~~java
Module owner = SomeClass.class.getModule();
System.out.println(owner.getName());
System.out.println(owner.isNamed());
~~~

An unnamed module returns `null` from `getName()`. This distinguishes cases needing `ALL-UNNAMED` from cases needing a specific named module target.

Applications creating custom `ModuleLayer`s must check the caller's module/layer. Do not assume every launcher option resolves access permissions for dynamically created layers; module descriptors or `ModuleLayer.Controller` may be needed within layer rules and limits.

## 11. Specifying the usage phase: javac, test, run, plugin

A single project can spawn multiple Java processes:

- `javac` compiler.
- JVM running unit tests.
- JVM running integration tests.
- Gradle/Maven `JavaExec` or Application Plugin.
- Executable JAR/distribution JVM.
- Container entrypoint.
- JVMs launched by workers or plugin hosts.
- Self-packaged runtime image.

A flag only takes effect in the process configured with it. A flag on a Gradle `run` task does not mean the production distribution automatically receives it; likewise, a flag on the application launcher does not automatically apply to the test JVM.

The record must state separately: “Required at compile”, “Required in test JVM”, and “Required in production JVM” as three distinct conclusions. Do not copy every option across all processes for convenience.

`--add-opens` primarily serves runtime deep reflection, and does not resolve `javac` errors when importing unexported packages. For `--add-exports`, configuration may be required at both compile and run time if source/bytecode directly accesses public types in internal packages.

## 12. Documenting inside Linux startup scripts

With a distribution layout:

~~~text
distribution/
  bin/run.sh
  mods/com.acme.app.jar
  mods/com.acme.orders.jar
~~~

Script:

~~~sh
#!/bin/sh
set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
APP_HOME="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"

# JPMS-003: serializer requires reflective access to model.
# See docs/jpms-access-exceptions.md before changing.
exec java \
  --module-path "$APP_HOME/mods" \
  --add-opens com.acme.orders/com.acme.orders.model=com.acme.serializer \
  -m com.acme.app/com.acme.app.Main "$@"
~~~

Comments link the flag to the documented record with an owner and replacement plan. `APP_HOME` is computed from the script's location rather than depending on the caller's working directory.

In Windows PowerShell, a single-line command avoids line-continuation differences:

~~~powershell
& java --module-path "C:\Apps\Acme\mods" --add-opens "com.acme.orders/com.acme.orders.model=com.acme.serializer" -m com.acme.app/com.acme.app.Main
~~~

The real command should compute the module path relative to the distribution location and verify the flag reaches the right JVM.

## 13. Documenting in Gradle

If using the Gradle Application Plugin:

~~~groovy
plugins {
    id 'application'
}

application {
    mainModule = 'com.acme.app'
    mainClass = 'com.acme.app.Main'

    // JPMS-003: runtime flag still tracked in the access exceptions registry.
    applicationDefaultJvmArgs = [
        '--add-opens=com.acme.orders/com.acme.orders.model=com.acme.serializer'
    ]
}
~~~

If only tests need reflection from an unnamed module:

~~~groovy
tasks.withType(Test).configureEach {
    // JPMS-004: test framework requires private-field introspection.
    jvmArgs '--add-opens=com.acme.orders/com.acme.orders.model=ALL-UNNAMED'
}
~~~

If source code must use a non-exported public class, the compiler may need:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    // JPMS-002: limit to only the modules/tasks that truly need it in the project.
    options.compilerArgs += [
        '--add-exports',
        'com.acme.engine/com.acme.engine.internal=com.acme.client'
    ]
}
~~~

The `JavaCompile` example shows where compiler flags can be passed; in a monorepo, configure only the client module's task rather than applying it globally without need.

If runtime also requires the export, configure the same option on the Application Plugin or relevant `JavaExec` task. With `javac --release` and system modules, using `--add-exports` to access JDK internal APIs has its own restrictions; do not treat this flag as a way around `--release`.

## 14. Maven, CI, and containers

With Maven, distinguish where options are received:

- Maven Compiler Plugin for compiler arguments.
- Maven Surefire/Failsafe for test JVMs.
- Application runner plugins or startup scripts for the real application.
- Dockerfile/entrypoint or deployment manifest for containers.

Exact XML configuration names depend on plugin versions, so records should point to actual configuration files and record verified build commands.

In CI, confirm flags are passed to the right task, not merely sitting as a string in the repository. In containers, verify the final startup script and image entrypoint use the same tested parameters.

`JAVA_TOOL_OPTIONS` or `JDK_JAVA_OPTIONS` can affect multiple processes broadly; if used, document their scope and avoid abusing them as an implicit wide-permission channel.

A deployment matrix should have columns for local, CI compile, unit test, integration test, staging, and production, with “flag required yes/no” and links to configuration.

## 15. Frameworks, annotation processors, and test-only flags

Some flags may only be needed by test frameworks, mocking libraries, or bytecode instrumentation:

~~~bash
--add-opens com.acme.app/com.acme.app.internal=ALL-UNNAMED
~~~

This flag makes sense if the framework truly runs in the unnamed module and performs deep reflection on an internal package.

If the framework is loaded as a named module, use the actual module name. If only a test needs reflection, do not carry that permission into the production launcher.

Annotation processors may need permissions inside the compiler process or another module/process. Never add `--add-opens` to the product's runtime just for a build-time processor. Record the exact calling component and the phase in which it runs.

Whenever upgrading JUnit, Mockito, serializers, or compiler plugins, re-verify related exceptions. Newer framework versions may no longer require the same permissions as older ones.

## 16. External libraries and JDK internal APIs

Legacy applications may access packages like `jdk.internal.*` or use deep reflection into `java.base` packages.

Syntax examples:

~~~bash
--add-exports java.base/jdk.internal.misc=ALL-UNNAMED
~~~

~~~bash
--add-opens java.base/java.lang=ALL-UNNAMED
~~~

This is **not** advice to use internal JDK APIs in new code. A flag that keeps the program running today does not guarantee internal classes stay stable across JDK upgrades.

If a library requires a flag touching JDK internals, the record should state:

- Library group/artifact/version and call site.
- Tested JDK version.
- Stack trace or analysis result.
- Whether an alternative library version supports newer JDKs.
- Public Java APIs usable as replacements.
- Specific tests confirming flag removal.

You can use `jdeps` to locate many static references to JDK internal APIs:

~~~bash
jdeps --jdk-internals --recursive \
      --class-path "lib/*" \
      app.jar
~~~

`jdeps` does not detect all string-based reflection. Supplement it with source/config searches and real integration tests.

`--illegal-access` is no longer a reliable blanket way to open permissions on modern JDKs. Remaining `--add-opens` or `--add-exports` flags must have owners and removal plans.

## 17. Narrowing permission scope and risk

When assessing safety:

- `--add-exports` can cause consumers to depend on public types in packages meant to remain internal.
- `--add-opens` lets callers perform deep reflection on non-public members where reflection permissions apply.
- `ALL-UNNAMED` is broader than a specific named module.
- Flags attached to every JVM process can grant scope beyond the required use case.
- Future JDK upgrades may change or remove internal classes.

Prefer least privilege: the exact source module, exact package, exact target, and exact execution phase. Do not open entire packages or other modules just for a quick fix.

JPMS is an encapsulation and module access-control mechanism, not a complete security sandbox. Risk notes should relate to the actual data and invariants inside the opened package.

## 18. When can a flag be removed?

An exception can be removed when:

1. Consumers have moved to a public API exported by the owning module.
2. Frameworks no longer perform deep reflection on the old package, or the descriptor has an intentional `opens`.
3. Dependencies on the offending internal JDK API are gone.
4. Tests exercising the relevant functionality pass with **only that flag removed**.
5. Startup scripts, CI, Gradle/Maven, and containers run on the target JDK without the flag.
6. The release has been tested on final artifacts.
7. The owner confirms documentation and migration changelog updates.

Do not remove all flags at once. Remove one flag at a time, run the affected tests, then remove it from all relevant configuration locations. A single successful startup is insufficient because reflection errors may only trigger when a rarely used endpoint or task is invoked.

Keep a brief history of removed flags, removal versions, and past rationales to aid regression analysis during future JDK upgrades.

## 19. Periodic checklist when upgrading JDK or dependencies

- [ ] List all `--add-opens` and `--add-exports` from the repository and deployment configs.
- [ ] Every option has an ID/record and owner.
- [ ] Source module/package verified from actual descriptors and artifacts.
- [ ] Target module is the real caller, not guessed from a filename.
- [ ] `ALL-UNNAMED` is used only when justified.
- [ ] Access purpose distinguishes regular export from deep reflection.
- [ ] Compile, test, run, or plugin host phase is explicitly stated.
- [ ] Tested JDK/vendor and library versions are up to date.
- [ ] A reproduction case exists showing failure when the option is omitted.
- [ ] Test-only flags are not kept in production unnecessarily.
- [ ] Flags in scripts/containers/Gradle/Maven match the registry.
- [ ] Risk, review milestone, owner, and alternatives are documented.
- [ ] Attempted removing flags individually after upgrading frameworks or redesigning APIs.
- [ ] Not relying on `--illegal-access` as a long-term migration plan.
- [ ] Not using access flags to mask missing modules, split packages, or missing classes.

## 20. Conclusion

A maintainable JPMS system treats still-required `--add-opens` and `--add-exports` flags as **accountable, removable access exceptions**, not permanent default startup arguments.

For each flag, clearly record **who uses the permission, which package is opened, to which module, why it is needed, at which compile/test/run phase it applies, what evidence proves it, who owns it, and what criteria allow removal**.

`--add-exports` is for regular access to public types in unexported packages; `--add-opens` is for runtime deep reflection. Neither replaces `requires`, module resolution, or a well-designed public API. As libraries are upgraded and migrated to supported APIs, remove each exception alongside representative tests to restore intentional strong encapsulation.
