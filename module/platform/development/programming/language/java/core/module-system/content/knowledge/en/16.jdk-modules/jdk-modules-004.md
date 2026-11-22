# JDK Internal Modules Are Not Public APIs

Since Java 9, the Java Platform Module System (JPMS) organizes the JDK into many named modules. Some modules provide standard Java SE APIs, some provide JDK-specific APIs or tools, and many modules contain **internal** packages intended solely for the implementation of the JVM or core libraries.

The most important point: **a class existing in the JDK does not mean it is a supported public API for applications to depend on directly**. A module or package name may be discoverable in the runtime image, yet module boundaries still govern whether a package is exported/opened to external code. Even when a boundary can be bypassed using JVM flags, an internal API does not thereby become a stable compatibility contract.

This lesson explains how to recognize internal APIs, distinguish `java.*` and `jdk.*` modules, understand compile/runtime access errors, clarify the meaning of `--add-exports` and `--add-opens`, and follow a workflow for migrating to supported APIs.

## 1. Three Tiers of APIs to Distinguish

In a modern JDK, at least three categories should be distinguished:

| Category | Examples | Usage |
| --- | --- | --- |
| Public Java SE API | `java.lang`, `java.util`, `java.net.http`, `java.sql` | Standard APIs with corresponding Java SE contracts and documentation |
| Documented JDK-specific API | Certain APIs in `jdk.jfr`, `com.sun.source.*` in `jdk.compiler` | Use only when intentionally depending on the JDK and backed by appropriate support docs |
| JDK internal implementation API | `jdk.internal.*`, many `com.sun.tools.javac.*` or `com.sun.org.apache.*.internal` packages | Do not treat as stable application APIs; avoid direct imports and reflection |

**You cannot evaluate a package solely by its prefix.** Not every class prefixed with `com.sun` is internal, and not every API inside a `jdk.*` module is off-limits. To determine the real boundary, inspect the module descriptor, JDK documentation, and the API's support policy.

For example:

- `java.base` contains both `java.util` — a public API — and `jdk.internal.misc` — an implementation detail.
- `jdk.compiler` exports Compiler Tree API packages such as `com.sun.source.tree`, yet does not export every compiler implementation package.
- `jdk.unsupported` contains certain APIs retained for compatibility, such as `sun.misc.Unsafe`; the word "unsupported" serves as a warning not to treat them as a foundation for new designs.

A module's name and a package's support level are **two separate questions**.

## 2. A Module Being Present Does Not Mean Its Packages Are Public

In JPMS, a named module can:

- Contain multiple packages.
- Export certain packages externally.
- Export certain packages only to designated named modules.
- Open packages for deep reflection.
- Keep the remaining packages encapsulated.

Conceptual example:

~~~java
module com.acme.engine {
    exports com.acme.engine.api;
    exports com.acme.engine.spi to com.acme.plugins;
    opens com.acme.engine.persistence to com.acme.orm;
}
~~~

A consumer reading `com.acme.engine` cannot automatically import classes from every package in the module.

Similarly, `java.base` is implicitly read by every named module, but that **does not mean every package in `java.base` is exported**.

Access relationships can be summarized as:

~~~text
Does Module A read Module B?
         │
         ▼
Does B export package P to A?
         │
         ├── Yes → A can use public types/members in P,
         │         still obeying Java access modifiers
         │
         └── No  → Java source in A cannot import P
                   as a normal API

Deep reflection?
         │
         ▼
Does B open package P to the caller module?
         │
         ├── Yes → Reflection can request bypassing
         │         access checks within permitted limits
         │
         └── No  → setAccessible may fail
~~~

`requires`, `exports`, and `opens` address different concerns. Adding `requires java.base` does not grant access to an unexported internal package.

## 3. Viewing JDK Modules with the Java Launcher

List the modules published by the current runtime image:

~~~bash
java --list-modules
~~~

Shortened example output:

~~~text
java.base@21.0.2
java.logging@21.0.2
java.sql@21.0.2
jdk.compiler@21.0.2
jdk.jfr@21.0.2
jdk.unsupported@21.0.2
...
~~~

Actual versions and module sets depend on the JDK or runtime image in use.

This command shows observable modules, **not confirmation that every package in a module is a public API**. Moreover, a custom runtime image from `jlink` may omit modules present in a full JDK.

Describe a specific module:

~~~bash
java --describe-module java.base
java --describe-module jdk.compiler
java --describe-module jdk.unsupported
~~~

Distinguish the lines in the descriptor:

- `exports package.name`: package exported unrestrictedly to modules with appropriate readability.
- `exports package.name to module.one,module.two`: qualified export only to the listed modules.
- `opens package.name`: package opened for deep reflection.
- `contains package.name`: package belongs to the module, **not a promise of export**.
- `requires other.module`: module dependency.
- `uses`/`provides`: service consumption/provider metadata.

When seeing `contains jdk.internal.misc`, do not infer that application code is allowed to import `jdk.internal.misc`. `contains` merely reflects package ownership by the module.

## 4. Compile-Time Example: Internal Package Is Not Visible

Suppose a modular application tries to use an internal API:

~~~java
// src/com.acme.app/module-info.java
module com.acme.app {
}
~~~

~~~java
// src/com.acme.app/com/acme/app/Main.java
package com.acme.app;

import jdk.internal.misc.Unsafe;

public class Main {
    public static void main(String[] args) {
        System.out.println(Unsafe.class.getName());
    }
}
~~~

Compile:

~~~bash
javac --module-source-path src \
      -d out \
      -m com.acme.app
~~~

On a JDK with strong encapsulation, the compiler may report an error like:

~~~text
package jdk.internal.misc is not visible
(package jdk.internal.misc is declared in module java.base,
 which does not export it to module com.acme.app)
~~~

This error has a specific meaning:

1. The class/package may **exist** in the JDK.
2. The `java.base` module owns that package.
3. The package is **not exported** to `com.acme.app`.
4. Code cannot import it as a normal API.

This is neither a "missing Maven dependency" error nor an error from omitting `requires java.base`. Every named module already reads `java.base` implicitly; what is blocked is the **package export**.

When a dependency is not a public API, the preferred fix is switching to a supported API. Adding boundary-relaxing flags should only be used for diagnosis or maintaining compatibility during a transition period.

## 5. JPMS Boundaries Still Apply When Running on the Classpath

An application without `module-info.java` typically runs on the classpath:

~~~bash
java -cp app.jar com.acme.app.Main
~~~

Code on the classpath belongs to the **unnamed module** of the corresponding class loader. The unnamed module can read modules permitted by JPMS rules, but it **does not automatically bypass package encapsulation**.

Consequently, moving an application from the module path back to the classpath does not guarantee that imports of `jdk.internal.*` or reflection into private JDK state will work.

In error messages, you may see:

~~~text
module java.base does not export jdk.internal.misc to unnamed module
~~~

or:

~~~text
module java.base does not "opens java.lang" to unnamed module
~~~

`unnamed module` in the message indicates where the calling code resides; the source module remains a named JDK module.

## 6. Distinguishing Public API Access from Deep Reflection

Two categories of errors are commonly confused:

### 6.1. Public Class Whose Package Is Not Exported

For example, code importing `jdk.internal.misc.Unsafe`. If the package is not exported, the compiler or JVM may reject access to the class even though the class has the `public` access modifier.

This is an **exports** issue, not necessarily related to reflection.

### 6.2. Valid Class Whose Private Members Are Not Opened

For example, reflecting on a field of `java.lang.String`:

~~~java
import java.lang.reflect.Field;

public class ReflectString {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
~~~

On modern JDKs, `setAccessible(true)` can throw:

~~~text
java.lang.reflect.InaccessibleObjectException:
Unable to make field ... java.lang.String.value accessible:
module java.base does not "opens java.lang" to unnamed module
~~~

Here `java.lang` is an exported package for normal API use, but that **does not mean private members in the package are opened for deep reflection**.

Distinguish `exports` from `opens`. Fixing the wrong kind of permission can lead maintainers to add multiple JVM flags while the application still fails.

## 7. --add-exports: Temporarily Relaxing Public API Import Permissions

JPMS provides the option:

~~~text
--add-exports SOURCE_MODULE/PACKAGE=TARGET_MODULE
~~~

Example granting module `com.acme.app` permission to use public types from an unexported package:

~~~bash
javac \
  --add-exports java.base/jdk.internal.misc=com.acme.app \
  --module-source-path src \
  -d out \
  -m com.acme.app
~~~

If the application still relies on that access at runtime, the corresponding flag may be needed:

~~~bash
java \
  --add-exports java.base/jdk.internal.misc=com.acme.app \
  --module-path out \
  --module com.acme.app/com.acme.app.Main
~~~

If the caller sits on the classpath, the target can be the launcher token `ALL-UNNAMED`:

~~~bash
java \
  --add-exports java.base/jdk.internal.misc=ALL-UNNAMED \
  -cp app.jar \
  com.acme.app.Main
~~~

However:

- `--add-exports` **does not change** `private` access modifiers into `public`.
- It **does not turn an internal API into an API committed to JDK support**.
- It may need to be repeated across compile, test, and production configurations.
- Internal class or method changes in a future JDK can still break the code.

This is a **controlled migration measure**, not a recommended architecture.

## 8. --add-opens: Temporarily Relaxing Deep Reflection Permissions

When a framework reflects on private members, the corresponding flag is:

~~~text
--add-opens SOURCE_MODULE/PACKAGE=TARGET_MODULE
~~~

Example opening `java.lang` of `java.base` for code running on the classpath:

~~~bash
java \
  --add-opens java.base/java.lang=ALL-UNNAMED \
  -cp app.jar \
  com.acme.app.Main
~~~

For a named framework module, you can grant permission to that exact module:

~~~bash
java \
  --add-opens java.base/java.lang=com.acme.framework \
  --module-path mods \
  --module com.acme.app/com.acme.app.Main
~~~

Permission is granted to **the module actually performing the reflection**, not necessarily the module containing `main` or a module calling a high-level framework API.

Comparison table:

| What do you need? | Appropriate mechanism | Limitations |
| --- | --- | --- |
| Use public types/members of an unexported package | `--add-exports` | Does not allow unrestricted reading of private fields |
| Use `setAccessible` or private lookup into an unopened package | `--add-opens` | Does not automatically create a compile-time export |
| Consumer reading a normal named module | `requires` or proper readability relationship | Does not bypass package encapsulation |
| Expose an API from a module you maintain | `exports` in `module-info.java` | Only exported APIs |
| Let a framework reflect on a package you maintain | `opens package to framework.module` | Permission applies only to the target module |

If you own the application's own modules, prefer fixing the design with `exports` or narrowly scoped qualified `opens` rather than spreading JVM flags across environments.

## 9. Strong Encapsulation Milestones When Upgrading the JDK

Since Java 9, module boundaries have changed how legacy applications use JDK internals.

| Milestone | Meaning for migration |
| --- | --- |
| Pre-Java 9 | Some applications directly accessed internal JDK classes despite the APIs being unsupported |
| Java 9 | JPMS introduced; a transitional grace period relaxed certain legacy reflective accesses to aid migration |
| Java 11–15 | Some accesses still ran while emitting `illegal reflective access` warnings |
| Java 16 | Strong encapsulation became the default under JEP 396; temporary opt-out mechanisms remained during transition |
| Java 17 onward | JEP 403 tightened strong encapsulation; `--illegal-access` no longer restores broad permissive access as before |

Remember:

- A warning on an older JDK **does not guarantee** the code will run on a newer JDK.
- `--illegal-access=permit` is a legacy migration option, not a durable solution on Java 17+.
- `--add-exports` and `--add-opens` are more targeted mechanisms, but do not guarantee an internal API will still exist in the future.
- Certain special APIs in `jdk.unsupported` are kept for compatibility; do not extrapolate this exception to all of `jdk.internal.*`.

When migrating, verify the exact Java version used for the compiler, unit tests, integration tests, and production runtime.

## 10. jdk.compiler: Example Distinguishing Published APIs from Implementation

`jdk.compiler` is a JDK module. Inside it are exported APIs, such as packages belonging to the Compiler Tree API:

~~~java
module com.acme.analyzer {
    requires jdk.compiler;
}
~~~

Application code can import a type from an exported package:

~~~java
import com.sun.source.tree.Tree;
~~~

Meanwhile, implementation packages such as `com.sun.tools.javac.util` are not by default exported as public APIs for consumers.

For instance, importing:

~~~java
import com.sun.tools.javac.util.Context;
~~~

may be rejected by the compiler because `jdk.compiler` does not export that package to the application module.

Both packages share the `com.sun` prefix, yet their support levels and export permissions differ. The right question is **does the descriptor export that package to you, and does the JDK documentation publish that API for use?**

Additionally, `jdk.compiler` is a JDK-specific API and not every custom runtime image includes it. If an application needs an API from `jdk.compiler`, ensure that module is present in the runtime environment.

## 11. jdk.unsupported and sun.misc.Unsafe: An Exception, Not a Precedent

Some high-performance software or older frameworks used to depend on `sun.misc.Unsafe`. To aid compatibility, the JDK includes the `jdk.unsupported` module, with the `sun.misc` package exposed according to the module's descriptor.

A named module may need to declare:

~~~java
module com.acme.legacy {
    requires jdk.unsupported;
}
~~~

However, this does not make `sun.misc.Unsafe` a stably supported Java SE API. Methods involving memory manipulation and object state may change or become restricted over time.

Distinguish:

- `sun.misc.Unsafe` belongs to the `jdk.unsupported` module, retained under a specific compatibility policy.
- `jdk.internal.misc.Unsafe` belongs to `java.base`, and its package is encapsulated.
- Neither class is a promise that each other's capabilities are interchangeable or will exist indefinitely.

When encountering `Unsafe` in a dependency, investigate the actual use case before choosing a replacement.

## 12. Detecting Dependencies on Internal JDK APIs with jdeps

The JDK's `jdeps` tool can analyze classes/JARs to locate static references to JDK internals.

Example:

~~~bash
jdeps --jdk-internals libs/legacy-library.jar
~~~

For an application JAR:

~~~bash
jdeps --jdk-internals app.jar
~~~

For a multi-release JAR, specify the release to analyze:

~~~bash
jdeps --multi-release 17 --jdk-internals libs/legacy-library.jar
~~~

Output can identify the class calling the internal API, the module/package containing that API, and sometimes suggest an appropriate replacement.

Usage workflow:

1. Scan the application artifact.
2. Scan key dependencies or dependencies appearing in stack traces.
3. Record the internal API, the calling class, and the artifact/version owning that class.
4. Separate direct usage in your source from indirect usage via libraries.
5. Propose public replacement APIs or newer dependency versions compatible with the target JDK.

Limitations of `jdeps`:

- Analysis is primarily based on class file metadata.
- `Class.forName("...")`, string-based reflection, dynamic proxies, or dynamically generated bytecode may not be fully detected.
- Having no warnings from `jdeps --jdk-internals` **does not prove** the program uses zero internals.

Combine this with testing on the target JDK, especially for serialization, ORMs, instrumentation, and libraries that generate bytecode at runtime.

## 13. Do Not Confuse JDK Internal APIs with Deprecated APIs or Removed Modules

Three situations must be categorized separately:

**JDK internal API:** a package/class that is an implementation detail and may be encapsulated. For example, a class in `jdk.internal.*`.

**Deprecated public API:** a public API carrying a warning advising migration to a newer API. A deprecated public API may still be exported and usable for now. Use `jdeprscan` or compiler warnings to evaluate.

**Removed module or API:** components that were once part of the JDK but no longer exist in later releases. A `module not found` or `ClassNotFoundException` error may stem from the module no longer being present, rather than encapsulation.

Do not treat every case with `--add-opens`:

- If a module does not exist, opening a package will not create the missing module.
- If a class has been removed, `--add-exports` will not recreate the class.
- If a public API is merely deprecated, read its replacement roadmap instead of assuming it is a JDK internal.

Accurate classification avoids pointless JVM flags and shortens diagnostic time.

## 14. Replacement Directions for Common Internal APIs

There is no single replacement applicable to every JDK internal API. Identify **the capability the application actually needs**.

| Legacy need | Replacement direction or what to check |
| --- | --- |
| Base64 encoding/decoding via legacy JDK classes | `java.util.Base64` |
| Field access with special memory semantics via `Unsafe` | `VarHandle`, `MethodHandles`, `AtomicInteger`, and public concurrency APIs |
| Managing resource cleanup via implementation details | `java.lang.ref.Cleaner`, `AutoCloseable`, or appropriate resource APIs |
| XML parsing via `com.sun.org.apache.*.internal` | JAXP, DOM, SAX, or XML libraries with public APIs |
| Handling keys, signatures, or certificates with internal security classes | `java.security`, `java.security.cert`, or supported libraries |
| Exploiting compiler implementation details | Exported and documented compiler/tree APIs, or official tools/compiler plugins |
| Reflection to read private fields of JDK classes | Public accessors, factories, interfaces, or alternative data models |

Example using the standard Base64 API:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class EncodingExample {
    public static void main(String[] args) {
        byte[] raw = "hello".getBytes(StandardCharsets.UTF_8);

        String encoded = Base64.getEncoder().encodeToString(raw);
        byte[] decoded = Base64.getDecoder().decode(encoded);

        System.out.println(encoded);
        System.out.println(new String(decoded, StandardCharsets.UTF_8));
    }
}
~~~

Output:

~~~text
aGVsbG8=
hello
~~~

This example requires no internal class imports or relaxed module boundaries. This is the preferred direction whenever the JDK already provides a public API that meets the need.

### VarHandle Instead of Certain Uses of Unsafe

If an application needs atomic operations on a field it owns itself, it can use the public `VarHandle` API:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public final class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException exception) {
            throw new ExceptionInInitializerError(exception);
        }
    }

    public int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
~~~

This snippet uses standard APIs for atomic field operations without needing to access `sun.misc.Unsafe`.

However, `VarHandle` does not mean every `Unsafe` feature has a 1:1 equivalent API. Native memory operations, object layout, or low-level runtime operations must be evaluated individually to choose a public API suited to the target JDK version.

## 15. When Errors Come from Third-Party Libraries

An application may not directly import internal classes yet still encounter errors because a dependency performs reflection or internal access.

A hypothetical stack trace:

~~~text
java.lang.reflect.InaccessibleObjectException: ...
    at third.party.mapper.InternalAccessor.open(...)
    at third.party.mapper.Mapper.read(...)
    at com.acme.app.Main.main(...)
~~~

Here, code inside the mapper library is what requests deep reflection.

Recommended steps:

1. Identify the actual artifact containing `third.party.mapper.InternalAccessor`.
2. Record the dependency version actually running, not just the version in build declarations.
3. Check whether the library has a release supporting the target JDK.
4. Prefer upgrading the library or changing framework configuration.
5. Run tests on the exact runtime image/JDK used for production.
6. If a temporary `--add-opens` is needed, grant permission to the exact module invoking reflection.
7. Remove the flag after updating the dependency.

With Maven, you can inspect the dependency tree:

~~~bash
mvn dependency:tree
~~~

With Gradle:

~~~bash
./gradlew dependencies
~~~

Checking transitive dependencies is important because an older library version can be pulled in via another framework even if the project already updated direct dependencies.

## 16. Error Patterns and Diagnostic Guide

| Symptom | Common meaning | How to handle |
| --- | --- | --- |
| `package ... is not visible` | Package belongs to a named module but is not exported to the consumer | Use a supported API or review exports |
| `module X does not export P to Y` | Public types/members in P are blocked by module boundary | Identify source module, package, and target module |
| `InaccessibleObjectException` | Deep reflection into an unopened package | Identify the reflecting module, remove dependency on private fields if possible |
| `IllegalAccessError` at runtime | Runtime disallows access requested by bytecode | Compare compile/runtime flags and the API being called |
| `ClassNotFoundException` | Class not found by loader; may have been removed or dependency is missing | Check module path, JDK version, and artifacts |
| `NoSuchMethodError` | Binary calls a method absent in the loaded class | Check binary compatibility, versions, and internal API usage |
| `illegal reflective access` warning on older JDK | Code relies on a compatibility mechanism tightened in newer JDKs | Upgrade the library and remove unsupported reflection |
| `--illegal-access` does not resolve the error | On modern JDKs the option no longer opens access as before | Fix the code or apply targeted measures during migration |

An incident logging template:

~~~text
Java version:
  java --version

Runtime command:
  java ... --module-path ... -m ...

Source module:
  java.base

Package:
  jdk.internal.misc

Caller module:
  com.acme.app (or unnamed module)

Access type:
  normal access / deep reflection

Dependency:
  com.acme:legacy-lib:version

Planned resolution:
  upgrade dependency / use public API / temporary scoped flag
~~~

Do not automatically open numerous packages just because exceptions keep appearing. Every flag should be tied to a specific cause and a concrete removal plan.

## 17. Workflow for Migrating to a Newer JDK

For applications with legacy dependencies, a controlled workflow can be applied:

**Step 1 — Define the target JDK.** Align compiler, CI, staging, and production. Record `java --version` and the actual executable path.

**Step 2 — Scan code and dependencies.** Search for `sun.*`, `jdk.internal.*`, or unsupported imports; run `jdeps --jdk-internals`.

**Step 3 — Test on the target JDK.** Record compilation, runtime linkage, and reflection errors separately.

**Step 4 — Inspect module descriptors.** Use `java --describe-module` to see which packages are exported/opened to whom. For library JARs with module descriptors, use `jar --describe-module --file library.jar`.

**Step 5 — Classify dependencies.** Separate application code from third-party libraries; identify versions needing upgrades.

**Step 6 — Replace with public APIs.** Prefer Java SE APIs or suitable documented JDK-specific APIs.

**Step 7 — Grant temporary permissions if unavoidable.** Use `--add-exports` or `--add-opens` with exact source/package/target, tracked in build/deploy configurations.

**Step 8 — Test on the real runtime image.** Especially with custom images from `jlink`, where not every `jdk.*` module is packaged.

**Step 9 — Gradually remove workarounds.** After upgrading dependencies, test removing each flag to avoid keeping unnecessary access to internals.

If the application is a library used by many other projects, removing JDK internal types from public signatures is even more critical. A public API depending on an unexported type can prevent consumers from compiling even if the library's implementation runs in its own environment.

## 18. Design Checklist Before Depending on a JDK Module

Before adding `requires jdk.some.module` or importing a class from the JDK:

- [ ] Is the package exported to your module by the module descriptor?
- [ ] Does the API have public documentation and an appropriate support policy?
- [ ] Does the API belong to Java SE or only to a JDK-specific module?
- [ ] Does the deployment runtime image contain that module?
- [ ] Is there a Java SE API that fulfills the same requirement?
- [ ] Are you relying on reflection or private fields of the JDK?
- [ ] Are JVM flags relaxing encapsulation needed to run or compile?
- [ ] If a workaround is needed, is there a documented reason and removal plan?
- [ ] Are third-party dependencies compatible with the target JDK?
- [ ] Have you tested on the module path configuration and real runtime?

**Practical rule:** rely only on packages published by the module and backed by documentation commitments; keep dependencies on implementation details minimal or eliminate them entirely.

## Conclusion

A modularized JDK does not mean every class in the JDK is a public API. `java.base` contains both Java SE APIs and internal packages; `jdk.compiler` contains both published APIs and implementation packages; `jdk.unsupported` preserves certain APIs for compatibility without providing Java SE-level stability guarantees.

To decide whether to use an API, inspect **the module descriptor, exports/opens, and support documentation**, not just class names or whether a JAR/JMOD can be found. When migration hits `package is not visible`, `IllegalAccessError`, or `InaccessibleObjectException`, identify the exact access type, scan dependencies with `jdeps --jdk-internals`, and prefer public API replacements. `--add-exports`/`--add-opens` can help temporarily, but **opening a package does not turn a JDK internal API into a long-term supported contract**.
