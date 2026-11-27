# Strong Encapsulation of JDK Internals from Java 17

Starting with Java 17, Java enforces **strong encapsulation** on JDK internal APIs. Internal packages that are not exported by JDK modules are no longer accessible by default from applications, even when the application runs on the classpath. Just because a library used to access them via reflection or import a `sun.*` class does not mean that approach remains supported.

This change was completed by **JEP 403 – Strongly Encapsulate JDK Internals** in Java 17. The goal is to protect module boundaries, enabling the JDK to evolve internal implementations without maintaining dependencies outside public contracts.

This lesson explains the meaning of strong encapsulation, distinguishes `exports` from `opens`, shows how to handle `IllegalAccessError` and `InaccessibleObjectException`, covers using `--add-exports`/`--add-opens` during migration, and explains how to find libraries that still depend on JDK internals. The content focuses on current Java 17 mechanisms; it does not use `--illegal-access` as a workaround to reopen access.

## 1. What Are JDK Internals?

The JDK provides documented public APIs in Java SE, for example:

- `java.lang.String`, `java.util.List`, `java.time.Instant`.
- `java.nio.file.Files`, `java.net.http.HttpClient`.
- `java.lang.invoke.MethodHandles`, `java.lang.invoke.VarHandle`.

Beyond those APIs, the JDK also has classes and packages for internal implementation. They may carry names like `sun.*`, `com.sun.*`, `jdk.internal.*`, or reside in other packages not exported by their respective modules.

Common examples in legacy code:

~~~java
import sun.misc.Unsafe;
import sun.nio.ch.DirectBuffer;
import jdk.internal.misc.Unsafe;
~~~

These are internal APIs or outside the public Java SE contract. Package names are a signal to investigate, though you should not judge solely by prefix: some `com.sun.*` packages are documented and exported as public APIs. Always verify the module, API documentation, and actual support status.

**Rule:** Rely only on documented, supported APIs for applications. Internal classes may be renamed, moved across packages, change signatures, or be removed between JDK releases without source or binary compatibility guarantees.

## 2. The Module System and Access Boundaries

Since Java 9, the JDK has been organized into modules. Each module can declare:

- Which modules it depends on via `requires`.
- Which packages are exposed to other modules via `exports`.
- Which packages permit deep reflective access via `opens`.

Applications running on the classpath typically belong to the **unnamed module**. JARs running on the module path can become named modules if they have `module-info.class` or be resolved as automatic modules.

Strong encapsulation applies to both classpath and module-path applications. Running an application on the classpath does not make internal packages of JDK modules public.

### 2.1. Export and open have different meanings

| Mechanism | What does it allow? | Used at which phase? |
| --- | --- | --- |
| `exports package` | Other modules access permitted `public` types and members in the package | Compile time and runtime |
| `opens package` | Allows deep reflection into types in the package, including non-`public` members, per module rules | Runtime |
| `exports package to module` | Exports package only to specified modules | Compile time and runtime |
| `opens package to module` | Opens package for reflection only from specified modules | Runtime |
| `open module` | Opens all packages of the module for deep reflection | Runtime |

`exports` does not automatically allow reflection into `private` fields. `opens` does not turn `private` classes into Java APIs that can be imported and called directly in source code.

## 3. What Does Strong Encapsulation Change Starting in Java 17?

A brief history helps explain why an application that ran on an older JDK may fail when upgraded to Java 17:

| Version | Related change |
| --- | --- |
| Java 9 | Module system introduced; JDK began encapsulating modules with temporary compatibility mechanisms for internal access |
| Java 9–15 | Relaxed encapsulation allowed some legacy reflective access to continue working; `--illegal-access` was used during the transition |
| Java 16 | Strong encapsulation became the default under JEP 396; the transition option could still relax access in some configurations |
| **Java 17** | **JEP 403** completes strong encapsulation; `--illegal-access` no longer restores relaxed access for internal packages |

From Java 17 onward, adding `--illegal-access=permit` to the launch command is not a way to reopen JDK packages. This option is obsolete and no longer relaxes encapsulation; the runtime may emit a warning about its use.

Stop including `--illegal-access=permit` in scripts, build configurations, or deployment documentation. Upgrade libraries or identify the exact packages and modules that need opening during transition.

### 3.1. Exceptions exist for certain internal APIs

JEP 403 preserves access to a few critical internal APIs, such as `sun.misc.Unsafe`, via module `jdk.unsupported`. This **does not turn them into stable, supported Java SE APIs**. Current accessibility is not a guarantee that implementations, signatures, or behavior will remain unchanged in future JDK versions.

Therefore, do not assume every `sun.*` name is strictly blocked; nor assume that an accessible class is safe for long-term use. Clearly distinguish **accessible in this runtime** from **supported public API**.

## 4. Common Errors When Applications Hit JDK Internals

Different kinds of errors occur depending on how access is attempted.

### 4.1. Compilation error due to unexported package

When source imports a type belonging to an unexported package from a JDK module, the compiler may report that the package is not visible or that the module does not export it.

Example illustrating the use of internal type `sun.nio.ch.DirectBuffer`:

~~~java
import java.nio.ByteBuffer;
import sun.nio.ch.DirectBuffer;

public class InternalAccessDemo {
    public static long addressOf(ByteBuffer buffer) {
        return ((DirectBuffer) buffer).address();
    }
}
~~~

Standard compilation on Java 17 can be rejected because `java.base` does not export `sun.nio.ch` to the application.

This signals that the source depends on internal implementation details. Do not default to adding flags as a permanent fix; first check whether a public API meets the requirement.

### 4.2. IllegalAccessError at runtime

A program might have compiled in an environment where the package was exported, yet when run in a runtime without the corresponding permission, the JVM can throw `IllegalAccessError`.

This is a linkage/runtime access error. It differs from missing class or method errors such as `NoClassDefFoundError` and `NoSuchMethodError`.

### 4.3. InaccessibleObjectException when using reflection

A library might call `setAccessible(true)` attempting to access a `private` field or method of the JDK:

~~~java
import java.lang.reflect.Field;

public class ReflectStringDemo {
    public static void main(String[] args) throws Exception {
        Field value = String.class.getDeclaredField("value");
        value.setAccessible(true);
    }
}
~~~

On Java 17, deep access into `java.lang` of module `java.base` is closed to normal applications. Calling `setAccessible(true)` can throw `InaccessibleObjectException`.

If you only want to test whether access can be enabled without throwing an exception when impossible, use `trySetAccessible()`:

~~~java
boolean opened = value.trySetAccessible();
System.out.println("opened = " + opened);
~~~

If the package is not opened to the caller's module, the result is typically `false`. Do not rely on reflection into private JDK fields to build application features.

## 5. Distinguishing --add-exports and --add-opens

Java 17 provides targeted options to open a module boundary when temporary compatibility is required.

### 5.1. --add-exports: accessing public types in a package

Syntax:

~~~text
--add-exports <source-module>/<package>=<target-module>
~~~

For example, to allow classpath code to access `public` types in package `sun.nio.ch`:

~~~bash
javac --add-exports java.base/sun.nio.ch=ALL-UNNAMED -d out InternalAccessDemo.java
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp out InternalAccessDemo
~~~

`ALL-UNNAMED` refers to unnamed modules, typically code running on the classpath.

If the application is a named module, specify the target module name instead of `ALL-UNNAMED`:

~~~text
--add-exports java.base/sun.nio.ch=com.example.app
~~~

Appropriate configuration is needed at both compile time and runtime if source directly references types in that package. `--add-exports` only grants access to `public` types/members according to export rules; it does not open `private` fields for deep reflection.

### 5.2. --add-opens: allowing deep reflection at runtime

Syntax:

~~~text
--add-opens <source-module>/<package>=<target-module>
~~~

Example opening `java.lang` of `java.base` to classpath code:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp out ReflectStringDemo
~~~

This option permits deep reflection from the target module into the specified package. It does **not** allow directly importing non-public types or using them in source code as an exported API.

`--add-opens` is a runtime option, not a replacement for `--add-exports` when compiling source that accesses public types in an unexported package.

### 5.3. Quick comparison

| Scenario | Option to consider |
| --- | --- |
| Source imports a `public` type in an unexported package | `javac --add-exports ...` |
| Application needs access to that `public` type at runtime | `java --add-exports ...` |
| Framework uses reflection on `private` fields/methods of a JDK package | `java --add-opens ...` |
| Deep reflection needed into an application module's package | Declare `opens` in `module-info.java` or appropriate open configuration |
| Wanting to restore full legacy relaxed encapsulation | No general way via `--illegal-access` in Java 17 |

Open only the exact package, exact target module, and only for as long as needed. Avoid opening an entire module to `ALL-UNNAMED` if only one named framework module requires reflective access.

## 6. Opening Application Module Packages with module-info.java

Strong encapsulation does not apply solely to the JDK. Modular applications must also design clear package boundaries.

Suppose module `com.example.app` has an API package and a model package that a framework needs to read/write via reflection:

~~~java
module com.example.app {
    requires com.fasterxml.jackson.databind;

    exports com.example.api;

    opens com.example.model to com.fasterxml.jackson.databind;
}
~~~

Meaning:

- `requires com.fasterxml.jackson.databind` declares the dependency on the framework module.
- `exports com.example.api` lets other modules access public APIs in that package.
- `opens com.example.model to com.fasterxml.jackson.databind` lets the specified framework perform deep reflection on the model.

The framework's module name must match its actual runtime module name; check the library's metadata rather than guessing from the Maven artifact name.

### 6.1. Qualified exports and qualified opens

Permissions can be restricted to a specific module:

~~~java
exports com.example.api to com.example.client;
opens com.example.model to com.example.json;
~~~

This avoids exposing packages or opening reflection to every module.

### 6.2. open module

Declaring:

~~~java
open module com.example.app {
    requires some.framework;
}
~~~

opens all packages of the module for deep reflection at runtime. This can be convenient for legacy frameworks, though its scope is broader than necessary in many applications. Prefer `opens package to module` when only a few packages and frameworks need access.

You cannot edit `module-info.java` of `java.base` or JDK modules to turn internal packages into public APIs. For JDK modules, launcher/compiler options only create access exceptions for that specific process.

## 7. Where to Place Module-Opening Options?

If a library cannot be upgraded immediately, options must be passed where the JVM is actually launched.

Example for a classpath application:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar application.jar
~~~

For a named module:

~~~bash
java --add-opens java.base/java.lang=com.example.app --add-exports java.base/sun.nio.ch=com.example.app -m com.example.app/com.example.Main
~~~

When using Maven or Gradle, test JVM configuration and application runtime JVM configuration may be separate places. Adding flags to tests does not mean the production process is configured, and vice versa.

Points to check:

- The actual launch command in the container, service manager, or deployment script.
- Test runner JVM configuration.
- IDE configuration if the error only appears when running from the IDE.
- Whether the target module is a named module or unnamed module.
- That the flags apply to the exact source module and package needing access.

Do not add a long list of `--add-opens` flags by trial-and-error until errors disappear. Each flag should map to a specific dependency and reason.

## 8. Finding JDK Internal Dependencies with jdeps

JDK 17 includes the `jdeps` tool to analyze dependencies at the bytecode level. The `--jdk-internals` option helps detect references to JDK internal APIs in classes or JARs.

Example:

~~~bash
jdeps --jdk-internals application.jar
~~~

For multi-release JARs, you can specify the version to analyze:

~~~bash
jdeps --jdk-internals --multi-release 17 application.jar
~~~

The output can tell you:

- Which class references an internal API.
- Which package or module contains that API.
- Suggested replacements when the tool has corresponding information.

You can combine this with:

~~~bash
jdeps --print-module-deps application.jar
~~~

This command helps identify which JDK modules the application requires, useful when preparing modular runtime images. It does not replace finding internal APIs; use `--jdk-internals` for that goal.

### 8.1. Limitations of static analysis

`jdeps` analyzes dependencies it can recognize from bytecode. It cannot guarantee detecting every dynamic access case, such as:

- Reflection with class/package names constructed from runtime strings.
- Class names loaded via custom class loaders.
- Access from native code/JNI.
- Behavior inside dependencies not included in the analysis scope.

Therefore, a warning-free result does not prove an application is completely free of JDK internals. Combine dependency analysis, testing on JDK 17, and runtime configuration checks.

### 8.2. Reading a JAR's module descriptor

For a modular JAR, you can inspect its descriptor:

~~~bash
jar --describe-module --file application.jar
~~~

If the JAR lacks an explicit module descriptor, the tool can describe the automatic module or report corresponding metadata. This metadata helps determine the module name to use in `exports`, `opens`, or `--add-exports`/`--add-opens`.

## 9. Replacing Internal APIs with Supported APIs

The sustainable fix is replacing dependencies on implementations with public APIs that have clear contracts.

| Legacy dependency or goal | Replacement direction to consider |
| --- | --- |
| `sun.misc.BASE64Encoder` / `BASE64Decoder` | `java.util.Base64` |
| Storing per-class metadata without a class-keyed map | `ClassValue<T>` where appropriate |
| Typed variable access or atomic operations with `Unsafe` | `VarHandle`, `MethodHandles`, `ByteBuffer`, or suitable concurrency APIs |
| Reflection into private fields of JDK classes to read state | Find public accessors or a public API designed for that need |
| Accessing internal NIO implementations | Use `java.nio`, `ByteBuffer`, `FileChannel`, and documented APIs |
| Accessing internals for date/time handling | Use `java.time` |

These are **purpose-based** replacement directions, not one-to-one mappings. For instance, `VarHandle` can replace certain low-level variable access operations, but is not a general drop-in clone of every `Unsafe` feature.

### 9.1. Example: Base64

Legacy code might rely on internal/unsupported classes. In current Java, use `java.util.Base64`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

byte[] input = "Java 17".getBytes(StandardCharsets.UTF_8);

String encoded = Base64.getEncoder().encodeToString(input);
byte[] decoded = Base64.getDecoder().decode(encoded);

System.out.println(encoded);
System.out.println(new String(decoded, StandardCharsets.UTF_8));
~~~

This API is an official Java SE API and requires no opening of JDK packages.

### 9.2. Example: VarHandle

When typed variable operations with well-defined memory access semantics are needed, `VarHandle` is a public API in `java.lang.invoke`:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;

public class Counter {
    private volatile int value;

    private static final VarHandle VALUE;

    static {
        try {
            VALUE = MethodHandles.lookup()
                    .findVarHandle(Counter.class, "value", int.class);
        } catch (ReflectiveOperationException ex) {
            throw new ExceptionInInitializerError(ex);
        }
    }

    public int incrementAndGet() {
        return (int) VALUE.getAndAdd(this, 1) + 1;
    }
}
~~~

`VarHandle` provides access modes with clear memory semantics. Choose the right mode (`get`, `set`, `getVolatile`, `compareAndSet`, `getAndAdd`, etc.) according to synchronization requirements; do not replace every operation with a single mode.

## 10. Why Should --add-opens Not Be Kept Long Term?

A module-opening option can keep a legacy application working during an upgrade, but it also weakens encapsulation boundaries.

The risks:

- Libraries continue depending on JDK internal implementations.
- JDK upgrades can change internal packages, fields, or behavior.
- Deep reflection permissions are broader than the application needs.
- Production launch configurations become hard to understand and control.
- Tests pass only with flags present, while production environments might lack those flags.

If a transitional flag must be kept:

1. Document the exact dependency and error that the flag addresses.
2. Restrict source module/package and target module to the narrowest scope.
3. Place the flag in managed launch configuration rather than scattering it across multiple places.
4. Create a task to upgrade the library or replace the API.
5. Test after removing the flag to confirm the dependency has been eliminated.
6. Remove the flag once it is no longer needed.

Do not open all packages of `java.base` or all modules to `ALL-UNNAMED` just to make errors go away. Overly broad configurations can hide unrelated dependencies.

## 11. Packaging an Application Does Not Remove Strong Encapsulation

Creating a fat JAR, shaded JAR, executable JAR, or runtime image does not turn JDK internals into public APIs.

- **Fat/shaded JAR:** bundles application dependencies into one artifact; does not change the module descriptor of `java.base`.
- **Classpath:** application is in the unnamed module; still subject to export/open boundaries of JDK modules.
- **Module path:** application has module descriptors; access is governed by `requires`, `exports`, `opens`, and runtime options.
- **jlink runtime image:** creates a runtime containing only required modules; not a mechanism to open internal packages.
- **jpackage:** packages the application and runtime; does not replace fixing dependencies that access JDK internals.

If `--add-opens` or `--add-exports` are needed to run, ensure the options are present in the launcher configuration of the deployed artifact. Do not configure them only in a development terminal and assume users running the JAR elsewhere will also receive the flags.

## 12. Workflow for Upgrading an Application to Java 17

You can follow this process when migrating a runtime from an older JDK to JDK 17:

1. **Run on the exact target JDK.** Confirm both `java -version` and `javac -version` are JDK 17 in build/test/run environments.
2. **Find internal dependencies.** Run `jdeps --jdk-internals` on the application and analyzable libraries.
3. **Reproduce errors.** Distinguish compilation errors, `IllegalAccessError`, `InaccessibleObjectException`, missing class errors, and missing method errors.
4. **Find replacement APIs.** Prefer Java SE APIs or public APIs supported by the library vendor.
5. **Upgrade dependencies.** Use library versions compatible with Java 17 that no longer require internal package access.
6. **Use temporary flags only if mandatory.** Choose the exact `--add-exports` or `--add-opens`, exact package, and target module.
7. **Test without flags.** Verify the application and tests pass after removing access exceptions.
8. **Verify packaged artifacts.** Run using the exact script/container/runtime image used in deployment.

Examples of basic diagnostic commands:

~~~bash
java -version
javac -version
jdeps --jdk-internals application.jar
jar --describe-module --file application.jar
~~~

Do not use `jdeprscan` as a replacement for `jdeps --jdk-internals`: that tool focuses on deprecated APIs, whereas an internal API may not be marked deprecated yet still be unsupported.

## 13. Common Errors Table

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Compiler reports package not visible/not exported | Source imports a type in an unexported module package | Find a public API; if transition is truly needed, configure `--add-exports` for the compiler |
| `IllegalAccessError` at runtime | Runtime module does not export the package to the application's module | Upgrade dependency or configure narrow, temporary `--add-exports` |
| `InaccessibleObjectException` from reflection | Package is not opened for deep reflection | Upgrade framework; if not yet possible, consider `--add-opens` for the exact package |
| `trySetAccessible()` returns `false` | Caller lacks permission to open the member | Check module/package and change the access mechanism |
| `--illegal-access=permit` fails to fix error | Transition option no longer enables relaxed access in Java 17 | Remove option; fix dependency or use targeted flags during transition |
| Works in IDE but fails in container | JVM args or actual JDK differs | Compare runtime versions and full VM options |
| `jdeps` reports nothing yet reflection errors still occur | Dynamic access is not visible in bytecode | Inspect stack traces, dependencies, and reflection configuration |
| Packaged JAR still fails | Packaging does not alter JDK module boundaries | Fix dependencies and launcher options |
| A `sun.*` API is still accessible | Exception exists or module exports that package | Check support contract; accessibility does not guarantee stability |
| Package opened too broadly | Using `ALL-UNNAMED` or opening unnecessary packages | Restrict target module, package, and usage duration |

## 14. Practice Exercises

### Exercise 1 — Distinguishing exports and opens

Write module `com.example.app` containing packages `com.example.api` and `com.example.model`. Export the API package and open the model package to a specified framework module. Explain why `exports` does not replace `opens` when a framework needs to read private fields via reflection.

### Exercise 2 — Observing reflection errors

Run the `ReflectStringDemo` example on JDK 17 without VM options. Observe `InaccessibleObjectException`. Then run with:

~~~bash
java --add-opens java.base/java.lang=ALL-UNNAMED ReflectStringDemo
~~~

Note the difference and explain why this is only a runtime exception for the specified package.

### Exercise 3 — Checking internal APIs

Run:

~~~bash
jdeps --jdk-internals application.jar
~~~

If the output shows internal dependencies, identify the application or library class responsible, then find an appropriate public API.

### Exercise 4 — Comparing add-exports and add-opens

Use the `InternalAccessDemo` example to explore why accessing a `public` type in an unexported package requires `--add-exports`, whereas accessing a private field via reflection requires `--add-opens`.

### Exercise 5 — Removing exceptions

Temporarily add a required `--add-opens` for a legacy library, upgrade the library to a version supporting Java 17, then re-run tests and the application without the flag. Confirm the exception configuration is no longer needed.

## 15. Principles to Remember

- Java 17 completes strong encapsulation of JDK internals under JEP 403.
- Internal APIs are not compatibility contracts for applications; do not rely on internal class names or implementation behavior.
- `exports` permits access to public types/members; `opens` permits runtime deep reflection.
- `--add-exports` and `--add-opens` open the exact package to the specified target module; use them as controlled transitional exceptions.
- `--illegal-access` is no longer a way to restore relaxed encapsulation in Java 17.
- Use `jdeps --jdk-internals` to locate internal dependencies, while remembering the limits of static analysis.
- Prefer Java SE APIs and library upgrades to eliminate the need to open packages.
- Fat JARs, classpath, module path, `jlink`, or `jpackage` do not automatically bypass JDK module boundaries.

Strong encapsulation keeps applications depending on public contracts rather than JDK implementation details. When upgrading to Java 17, identify the exact blocked access point, replace it with a supported API, and keep module exceptions narrowly scoped during the transition period.
