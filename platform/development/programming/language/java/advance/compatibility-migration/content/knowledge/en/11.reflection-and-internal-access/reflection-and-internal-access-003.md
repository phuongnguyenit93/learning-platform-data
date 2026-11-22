# --add-exports and --add-opens: distinguishing ordinary access from deep reflection

When upgrading an application from Java 8 to Java 11, 17, 21, or newer Java versions, some legacy libraries begin reporting errors related to unexported packages or reflection not being permitted to access internal members. Two JVM options that commonly appear in resolution approaches are `--add-exports` and `--add-opens`. Their names look similar, yet they address **two different types of access**: ordinary Java language access and deep access via reflection.

Confusing the two options can lead to ineffective fixes. For example, adding `--add-exports` does not mean a framework is allowed to read a `private` field; conversely, adding `--add-opens` does not turn an internal package into a public API so that you can arbitrarily `import` and compile Java code.

This lesson belongs to the **Reflection and Internal APIs** group of the **Java Advance Compatibility Migration** module. The goal is to understand the boundaries of the Java Platform Module System (JPMS), choose the right option at the right stage, and know when to remove workarounds in favor of upgrading libraries or fixing the architecture.

## 1. Learning outcomes

After this lesson, you can:

- Distinguish *module readability*, *package export*, *package open*, and member access permissions under Java language rules.
- Explain what `--add-exports` allows and what it does **not** allow.
- Explain what `--add-opens` allows and what it does **not** allow.
- Recognize the difference between compile-time errors and runtime errors.
- Choose the appropriate target for a named module or code on the classpath via `ALL-UNNAMED`.
- Read `IllegalAccessError`, `IllegalAccessException`, and `InaccessibleObjectException` errors in proper context.
- Apply these options in a scoped manner in the Java command, Maven, Gradle, testing, and production environments.
- Plan the replacement of dependencies on internal APIs instead of keeping access-opening flags permanently.

## 2. JPMS fundamentals: module readability, package exports, and member access

### 2.1. Named modules and unnamed modules

Since Java 9, JPMS has organized Java components into modules. An explicitly named module can declare `module-info.java`:

```java
module com.example.application {
    requires com.example.library;
}
```

Classes loaded from the traditional classpath typically belong to an **unnamed module** of the corresponding class loader. Classes in a JAR with a descriptor, when placed on the module path, typically belong to a **named module**. A JAR without a descriptor on the module path can become an **automatic module**, carrying its own compatibility rules.

Using a newer JDK does **not** require the entire application to have `module-info.java`. Many legacy systems still run on the classpath, yet the classes inside the JDK already belong to named modules such as `java.base` and `java.sql`, so accessing internal APIs is still subject to JPMS restrictions.

### 2.2. Three distinct conditions for ordinary API access

Suppose the `com.example.application` module needs to call a `public` class belonging to the `com.example.library` module. At least three layers must be considered:

1. **Module readability:** can the calling module read the module containing the class?
2. **Package export:** does the module containing the class export that package to the calling module?
3. **Java access control:** do the class and member have `public`, `protected`, or appropriate access level in the calling context?

Example:

```java
module com.example.library {
    exports com.example.library.api;
}
```

```java
module com.example.application {
    requires com.example.library;
}
```

Here, `com.example.application` can reference `public` types in `com.example.library.api`. It cannot automatically access the `com.example.library.internal` package if that package is not exported.

You can remember this with a diagram:

```text
Does the calling module read the target module?
         |
         +-- No --> Missing readability
         |
         +-- Yes
              |
              v
Is the package exported to the calling module?
         |
         +-- No --> Blocked at package boundary
         |
         +-- Yes
              |
              v
Do public/protected/package/private rules allow it?
         |
         +-- No --> Blocked at member boundary
         |
         +-- Yes ----> Ordinary access is allowed
```

**`requires` and `exports` address two different conditions.** Adding `requires` does not turn an internal package into a public API; adding an export also does not turn a `private` method into `public`.

### 2.3. Ordinary reflection and deep reflection

Reflection is not a single type of access.

**Ordinary reflection** can read metadata or invoke `public` members through APIs such as `Class.getMethod` and `Method.invoke`. When accessing types/members of another module, module export rules and access checks still apply.

**Deep reflection** occurs when code wants to bypass ordinary checks to access non-public constructors, methods, or fields, for example using:

```java
Field field = type.getDeclaredField("secret");
field.setAccessible(true);
Object value = field.get(null);
```

Deep reflection generally requires the target package to be **open** to the module performing reflection. Simply exporting the package is not enough to allow `private` access.

An application may be able to call a `public` method yet still be blocked when a serializer or ORM tries to read a `private` field of the same class.

## 3. `--add-exports`: opening ordinary access to a package

### 3.1. Syntax and meaning

General syntax:

```text
--add-exports <source-module>/<package>=<target-module>
```

You can specify multiple target modules as a comma-separated list, or use the special value `ALL-UNNAMED` to grant access to unnamed modules.

Illustrative example with modules owned by the project itself:

```bash
java --add-exports com.example.core/com.example.internal=com.example.client \
     --module-path mods \
     -m com.example.client/com.example.client.Main
```

This command specifies that package `com.example.internal` of module `com.example.core` is additionally exported to `com.example.client`.

This is a **qualified export added via launch-time configuration**. It does not modify the JAR file or `module-info.class` stored in the artifact.

### 3.2. What does `--add-exports` allow?

Once the calling module has the appropriate readability relationship and satisfies Java access control rules, `--add-exports` can allow:

- Importing `public` types in a package that is not exported by default.
- Calling `public` constructors or methods accessible under Java rules.
- Referencing `public` fields or members with appropriate access levels.
- Using these APIs from source code when the compiler is configured with the corresponding `--add-exports`.
- Allowing bytecode to perform public access at runtime when the JVM is also configured accordingly.

Example of an internal package containing a `public` class:

```java
package com.example.internal;

public final class InternalApi {
    private InternalApi() {}

    public static String message() {
        return "Xin chào từ internal API";
    }

    private static String secret = "demo-only";
}
```

If this package has not yet been exported to the client, the following import will be invalid in a normal explicit named module:

```java
import com.example.internal.InternalApi;
```

The compiler may report that the package is not exported to the module being compiled. When the proper export is added at compile time, the import and the `InternalApi.message()` call can become valid.

### 3.3. What does `--add-exports` not allow?

This option does **not**:

- Grant permission to read `private` methods or fields via deep reflection.
- Change `private` into `public`.
- Automatically create a module readability relationship if the required readability does not already exist.
- Make a missing class appear on the classpath/module path.
- Prove that an internal API is guaranteed to be supported by the vendor.
- Guarantee that an internal class or method retains the same name and behavior in future JDKs.

If a framework does:

```java
Field field = InternalApi.class.getDeclaredField("secret");
field.setAccessible(true);
```

then exporting the package so that calling code sees `InternalApi` is still **not enough** to ensure `setAccessible(true)` succeeds. This is a situation where `opens` or `--add-opens` should be considered.

## 4. `--add-opens`: allowing deep reflection into a package

### 4.1. Syntax and meaning

General syntax:

```text
--add-opens <source-module>/<package>=<target-module>
```

Example:

```bash
java --add-opens com.example.core/com.example.internal=com.example.client \
     --module-path mods \
     -m com.example.client/com.example.client.ReflectionMain
```

The command instructs the JVM to **open** package `com.example.internal` from module `com.example.core` to module `com.example.client`. The purpose is to allow deep reflection operations within this open scope, such as `setAccessible(true)` on non-public members.

### 4.2. Why do frameworks need opens?

Many frameworks create objects or map data through reflection:

- **ORM:** reading/writing non-public entity fields, creating instances via constructors.
- **Serializer/deserializer:** discovering fields, setters, constructors, and metadata.
- **Dependency injection:** creating beans, injecting fields, calling lifecycle methods.
- **Proxy/AOP:** handling methods and classes generated at runtime.
- **Testing/mocking:** inspecting or replacing members that are normally non-public.

Example:

```java
Class<?> type = Class.forName("com.example.internal.InternalApi");
Field field = type.getDeclaredField("secret");
field.setAccessible(true);
String value = (String) field.get(null);
```

With a target named module that does not open the package, `getDeclaredField` can find the metadata, but `setAccessible(true)` is rejected. When the package is opened to the module performing reflection, the operation can be allowed within the corresponding JPMS scope.

### 4.3. How does `--add-opens` differ from `exports`?

`--add-opens` is not another way to write `--add-exports`:

- `--add-exports` serves **ordinary API access**, especially public types/members.
- `--add-opens` serves **deep reflection** at runtime into the opened package.
- Adding `--add-opens` to a `javac` command is not a way to grant compile-time access for `import` statements in source code; the compiler may report that this option has no effect during compilation.
- An open package can support reflection on public and non-public members under reflection rules, but that is not equivalent to an export for source code to access in the ordinary way.

Correctness also depends on the module performing reflection and the class loader in use. You should not open a package to a module that the framework does not actually belong to.

### 4.4. `opens` in the descriptor vs. `--add-opens` at launch time

If you own the module's source, you can declare:

```java
module com.example.core {
    opens com.example.internal to com.example.client;
}
```

If you do not own or cannot yet edit the module descriptor, use the runtime option:

```bash
java --add-opens com.example.core/com.example.internal=com.example.client ...
```

Both approaches serve a similar goal but have different governance scopes:

| Approach | Where declared | Scope |
| --- | --- | --- |
| `opens p to m` | `module-info.java` | Part of the module contract published by the author. |
| `opens p` | `module-info.java` | Opens the package to all modules under JPMS rules. |
| `open module m` | `module-info.java` | Opens all packages of the module for deep reflection. |
| `--add-opens m/p=t` | Runtime option | Adds open access to the target for that specific run. |

When you have permission to edit the source, prefer `opens` on the exact package and the exact module needing access, rather than opening the entire module. For third-party libraries, prioritize upgrading to a version supporting the target JDK before using a long-term workaround.

## 5. Direct comparison of `--add-exports` and `--add-opens`

| Criterion | `--add-exports` | `--add-opens` |
| --- | --- | --- |
| Primary purpose | Ordinary Java access to an unexported package. | Allows deep reflection into a package. |
| Can it help `import` an unexported public class? | Yes, if the compiler and remaining conditions are properly configured. | No, it does not replace an export at compile time. |
| Can it help call a public method in the ordinary way? | Yes. | Not the purpose of the option; does not grant ordinary compile-time permission. |
| Can it help access private fields/methods via `setAccessible(true)`? | Not enough. | Yes, when opened to the exact calling module and no other restriction applies. |
| Stage of use | Typically needed at compile time and runtime if source uses unexported APIs. | Mainly at runtime; also needed in the JVM running tests/frameworks that use reflection. |
| Target | Named module or `ALL-UNNAMED`. | Named module or `ALL-UNNAMED`. |
| Does it automatically create a `requires` dependency? | No. | No. |
| Does it make internal APIs stable? | No. | No. |
| Risk | Application depends on implementation APIs that may change. | Exposes further access to internals, hard to control if the scope is too broad. |

**Quick selection rule:** source uses `import internal.package.Type` and errors on an unexported package → investigate `--add-exports`. Framework uses `setAccessible(true)` and is blocked → investigate `--add-opens`. If the class does not exist or the module is not loaded, neither is the right solution yet.

## 6. Hands-on with two named modules: compilation errors and reflection errors

The example below uses two modules that we define ourselves. This approach demonstrates the difference without relying on a specific internal JDK API that might change across versions.

### 6.1. Directory structure

```text
demo/
├── src/
│   ├── com.example.core/
│   │   ├── module-info.java
│   │   └── com/example/internal/InternalApi.java
│   └── com.example.client/
│       ├── module-info.java
│       └── com/example/client/
│           ├── DirectClient.java
│           └── ReflectionMain.java
└── mods/
```

Source module:

```java
// src/com.example.core/module-info.java
module com.example.core {
    // Intentionally do not export package com.example.internal.
}
```

```java
// src/com.example.core/com/example/internal/InternalApi.java
package com.example.internal;

public final class InternalApi {
    private InternalApi() {}

    public static String message() {
        return "Public method trong package nội bộ";
    }

    private static String secret = "Thông tin minh họa";
}
```

Client module:

```java
// src/com.example.client/module-info.java
module com.example.client {
    requires com.example.core;
}
```

### 6.2. Case A: ordinary access requiring exports

Direct client:

```java
// src/com.example.client/com/example/client/DirectClient.java
package com.example.client;

import com.example.internal.InternalApi;

public final class DirectClient {
    public static void main(String[] args) {
        System.out.println(InternalApi.message());
    }
}
```

Compile the core module:

```bash
javac -d mods/com.example.core \
  src/com.example.core/module-info.java \
  src/com.example.core/com/example/internal/InternalApi.java
```

If the client is compiled as a named module without an additional export, importing `InternalApi` will be rejected because `com.example.internal` is not exported from `com.example.core`.

You can specify the export at compile time:

```bash
javac --module-path mods \
  --add-exports com.example.core/com.example.internal=com.example.client \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/DirectClient.java \
  src/com.example.client/com/example/client/ReflectionMain.java
```

When running the direct client, you also need to declare the corresponding export:

```bash
java --module-path mods \
  --add-exports com.example.core/com.example.internal=com.example.client \
  -m com.example.client/com.example.client.DirectClient
```

If you only use the option at compile time, runtime may deny access and throw `IllegalAccessError`. Conversely, only adding the option at runtime does not fix the `import` error when the compiler is still blocked.

### 6.3. Case B: deep reflection requiring opens

Another client does not import `InternalApi` but looks up the class and field by name:

```java
// src/com.example.client/com/example/client/ReflectionMain.java
package com.example.client;

import java.lang.reflect.Field;

public final class ReflectionMain {
    public static void main(String[] args) throws Exception {
        Class<?> type =
                Class.forName("com.example.internal.InternalApi");
        Field field = type.getDeclaredField("secret");

        field.setAccessible(true);
        System.out.println(field.get(null));
    }
}
```

The `ReflectionMain` class does not need source-level access to the `InternalApi` type, so compiling this class alone does not require `--add-exports` for the internal package.

Compile the client with the module path and descriptor file:

```bash
javac --module-path mods \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/ReflectionMain.java
```

Run without open permission:

```bash
java --module-path mods \
  -m com.example.client/com.example.client.ReflectionMain
```

In this configuration, `field.setAccessible(true)` may throw `java.lang.reflect.InaccessibleObjectException` because `com.example.internal` has not been opened to `com.example.client`.

Run with open permission:

```bash
java --module-path mods \
  --add-opens com.example.core/com.example.internal=com.example.client \
  -m com.example.client/com.example.client.ReflectionMain
```

The deep reflection operation can succeed even though `com.example.internal` is still not exported for `import` at compile time.

**Hands-on note:** The two compilation flows are presented to illustrate each permission separately. If deploying both clients to the same output directory, preserve the build configuration and ensure the classes were compiled in the corresponding scenario. In a real project, separate the two tests into two independent tasks/configurations to reproduce each error.

## 7. `ALL-UNNAMED` and the difference between classpath and module path

### 7.1. When the framework is on the classpath

Many legacy applications use the classpath and have no module descriptor. Their code typically belongs to an unnamed module. To open a named module's package to this code, the commonly used syntax is:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED \
     -jar application.jar
```

Or, if classpath source code directly references a public API in an unexported package:

```bash
java --add-exports java.base/jdk.internal.misc=ALL-UNNAMED \
     -jar application.jar
```

These two commands are **only to illustrate the syntax and principles**. You should not blindly add these flags to production without an error and documentation confirming the package actually needs to be accessed. APIs in `jdk.internal.*` are implementation details and can change or disappear.

`ALL-UNNAMED` is the group of unnamed modules, **not the name of a single JAR**. Therefore, the granted scope may be broader than desired, especially if multiple libraries run on the classpath of one or more class loaders.

### 7.2. When the framework is in a named module

If the framework is a named module, for example `com.example.framework`, specify that exact name:

```bash
java --add-opens java.base/java.lang=com.example.framework \
     --module-path mods \
     -m com.example.app/com.example.app.Main
```

The target value must correspond to the **module of the code performing reflection**, not necessarily the module launching the application. If the ORM is loaded by a module with a different name, opening the package to the app module may still fail to resolve the error.

### 7.3. Automatic modules

A legacy JAR on the module path can become an automatic module. It has a module name and its own compatibility characteristics. Do not assume that using an old JAR always means the target is `ALL-UNNAMED`; if the JAR is already running as an automatic module, the target must be based on its actual resolved module name.

Look up a JAR's module information:

```bash
jar --describe-module --file path/to/library.jar
```

Moving a JAR from the classpath to the module path can change its module identity, which can therefore also change the target that `--add-opens` or `--add-exports` needs to specify.

## 8. Why is a readability relationship still needed?

`--add-exports` and `--add-opens` only handle exporting/opening packages. They are not a general solution for every module dependency error.

Example:

```java
module com.example.app {
    // If you need to call module com.example.core from ordinary Java source:
    requires com.example.core;
}
```

If the calling module cannot yet read the target module, inspect `requires`, the module graph, and in special cases `--add-reads`:

```text
--add-reads <source-module>=<target-module>
```

For classpath code, the `ALL-UNNAMED` target can appear in transitional scenarios. This is a **different** mechanism from export/open.

A useful way to think when troubleshooting errors:

- **Module not found:** check the module path and module resolution.
- **Cannot read module:** check `requires` or `--add-reads` when genuinely needed.
- **Cannot see public package:** check `exports` or `--add-exports`.
- **Deep reflection blocked:** check `opens` or `--add-opens`.
- **Class/JAR not found:** check the classpath, class loader, dependency scope, and deployment environment.

## 9. Error types and how to interpret them

### 9.1. Compile error: package is not visible

A message might read similarly to:

```text
package com.example.internal is not visible
(package com.example.internal is declared in module com.example.core,
 which does not export it to module com.example.client)
```

**Meaning:** the compiler sees the package in the named module, but the package is not exported to the calling module. If using this API is intentional, an appropriate export can be added. However, if it is an internal package, a better solution is to replace it with the vendor's public API.

### 9.2. `IllegalAccessError` at runtime

A compiled binary can encounter an error when the JVM accesses a type/member blocked by the module system:

```text
java.lang.IllegalAccessError:
  class ... cannot access class ...
  because module ... does not export ... to module ...
```

**Meaning:** the actual execution path lacks export/readability or there is a mismatch between compile and runtime configurations. Do not assume that just because source compilation succeeded, the production JVM has the same flags.

### 9.3. `InaccessibleObjectException` with deep reflection

Typical error:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field ... accessible:
  module ... does not "opens ..." to ...
```

**Meaning:** reflection attempted to bypass Java access checks, but the package is not open to the module performing the operation. Identify the source module/package/target directly from the error message; prioritize upgrading the framework or fixing the descriptor. `--add-exports` alone usually does not help.

### 9.4. `IllegalAccessException` and reflection checks

`IllegalAccessException` can also occur when invoking a constructor or method via reflection without proper access permissions. The difference usually relates to the operation the reflection API is performing and whether suppressing access checks was requested.

`trySetAccessible()` can return `false` instead of throwing `InaccessibleObjectException` when access override cannot be enabled, allowing the situation to be handled in a controlled manner. However, it does not create new access permissions.

### 9.5. `ClassNotFoundException` is not an export/open error

If the class loader cannot find a class:

```text
java.lang.ClassNotFoundException: com.vendor.LegacyProvider
```

then adding `--add-opens` or `--add-exports` will not make the missing JAR appear. You must check runtime dependencies, module resolution, plugin directories, and class loaders.

### 9.6. Reflection code may not appear in application source

A framework may use reflection inside third-party library code. The stack trace typically contains the name of the framework/serializer/proxy library. Even if the application does not call `setAccessible` itself, the error can still come from a framework pulled in by the application's dependencies.

Therefore, when diagnosing, explicitly note the **module performing reflection**, the module containing the target package, and the version of the offending dependency.

## 10. Differences across Java versions

### 10.1. Java 8: no JPMS yet

Java 8 does not have `module-info.java` and does not support the JPMS options `--add-exports`/`--add-opens`. Java 8 applications may have accessed many internal JDK classes or reflected into platform classes without encountering the same enforcement mechanism as Java 9+.

When upgrading the JDK, you cannot simply keep all JVM options as-is and assume the runtime will behave equivalently.

### 10.2. Java 9 to 15: transitional mechanisms

Java 9 introduced JPMS, while many early JDK releases used a *relaxed strong encapsulation* policy for certain packages that had existed in JDK 8. `--illegal-access` was once provided to partially control this mechanism, and applications could see `Illegal reflective access` warnings.

The transitional mechanism did not mean every internal API was permitted to be accessed. Cases already explicitly blocked still required code fixes, library upgrades, or proper configuration declarations.

### 10.3. Java 16 and Java 17+: stricter encapsulation

In Java 16, strong encapsulation became the default in many cases. Starting in Java 17, JEP 403 strongly encapsulated JDK internals; the old `--illegal-access` option became obsolete and no longer opens access as before.

Therefore, a workaround relying on ignoring warnings on JDK 11 may no longer allow the application to start on JDK 17+. You need to upgrade frameworks and use public APIs, or apply `--add-opens`/`--add-exports` **targetedly** during the transition period.

### 10.4. Not everything in `sun.*` has the same status

Some specific APIs have their own compatibility mechanisms, such as critical APIs provided via the `jdk.unsupported` module. Do not infer that every package starting with `sun.` or `com.sun.` shares the same boundary. You need to inspect the actual module containing the class, package exports, and official documentation of the target JDK.

The sustainable approach remains replacing internal APIs with supported public APIs whenever possible.

## 11. Integrating options into build and test

### 11.1. Compile flags and runtime flags must be placed in the right location

If ordinary Java code **imports** a public class in an unexported package, the build process may need `--add-exports` on `javac`; the running program may also need the same export on `java`.

If a framework performs **deep reflection**, the JVM executing tests or the application may need `--add-opens`. Placing `--add-opens` only in compiler arguments does not resolve reflection errors when tests or production run.

Each place with its own JVM may require separate configuration:

- The JVM running unit tests.
- The JVM running integration tests.
- The JVM running the application/server.
- The JVM running code generators or annotation processors, if those tools actually use reflection.
- The JVM inside the production container image or application server.

Do not blindly copy flags into every JVM. Add them only to the processes that actually need access.

### 11.2. Gradle example

Illustration of a project needing an export at compile time and an open when running tests:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '--add-exports',
        'java.base/jdk.internal.misc=ALL-UNNAMED'
    ]
}

tasks.withType(Test).configureEach {
    jvmArgs(
        '--add-opens',
        'java.base/java.lang=ALL-UNNAMED'
    )
}
```

This is an example of **where to configure**, not a recommendation to use these internal JDK packages. Gradle may use different toolchains, test launchers, or JavaExec tasks; you must verify the actual JVM running each task. If a project uses `--release` for an older Java version, certain combinations of `--add-exports` with `--release` may be rejected by the compiler; you should resolve the API requirement instead of forcing the compiler to bypass the release target.

If the application runs via `JavaExec` or a separate plugin, `Test.jvmArgs` does not automatically apply to that process.

### 11.3. Maven example

If the goal is only to open a package for the JVM running tests, Maven Surefire can configure JVM arguments, for example:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <argLine>
            --add-opens java.base/java.lang=ALL-UNNAMED
        </argLine>
    </configuration>
</plugin>
```

For projects already using `argLine` for JaCoCo or another agent, you must **merge** the arguments according to the plugin's mechanism so as not to overwrite existing parameters. Fork behavior and plugin version also affect flag application.

If an export is needed for source compilation, configure the compiler plugin using `compilerArgs` or the method supported by the plugin version. Do not use the test runner's `argLine` hoping to fix compilation errors.

### 11.4. JVMs in containers and production environments

For services deployed in containers, flags can be configured in the startup command or in platform-managed JVM options. Clearly document where the flags live:

```text
Local Java command
       |
       +-- Build JVM / compiler
       +-- Unit-test JVM
       +-- Integration-test JVM
       +-- Application JVM
       +-- Production container / application server
```

Not every JVM in the diagram reads the same environment variable or the same configuration file. After deployment, verify that the Java process runs with the expected actual arguments, rather than relying only on the README or build scripts.

## 12. Why should these flags not be considered a final solution?

### 12.1. Depending on internal APIs makes long-term upgrades difficult

APIs in internal packages can change class names, signatures, semantics, or disappear between JDK versions. `--add-exports` only opens access; it does **not** keep that API stable.

A project using `jdk.internal.*` may work today and break after changing the JDK, even if the export flag is kept.

### 12.2. Opening deep reflection impacts encapsulation

`--add-opens` allows other modules to perform deep reflection into the opened package. With the `ALL-UNNAMED` target, multiple libraries on the classpath can benefit from that opened access. This is why you should:

- Restrict to the exact package.
- Restrict to the exact module whenever possible.
- Avoid opening all of `java.base` or opening an unverified list of packages.
- Not assume JPMS is a complete security sandbox.
- Treat access-opening flags as a configuration change that must be controlled and reviewed.

### 12.3. Workarounds easily mask outdated dependencies

When an old framework requires many `--add-opens` flags, this may be a sign that it does not yet support the target JDK. Adding flags repeatedly makes future upgradability increasingly dependent on JDK implementation details.

A sensible order of priority:

1. Upgrade the framework/library to a version supporting the target JDK.
2. Switch to a public API or supported plugin/service mechanism.
3. If you own the target module, update `module-info.java` with exact `exports`/`opens`.
4. If it cannot be fixed immediately, use minimal `--add-exports`/`--add-opens` with an owner and a removal plan.

## 13. Error investigation workflow in migration projects

### Step 1: Record the error and environment

Collect the full stack trace or diagnostic; JDK vendor/version; source/target/release; framework version; classpath/module path; and actual JVM arguments of the failing process.

### Step 2: Classify the error

Determine whether the error belongs to:

- Module resolution or class loading.
- Readability.
- Compile-time ordinary access.
- Runtime ordinary access.
- Deep reflection.

Do not pick a flag solely based on the phrase “access denied” without checking the operation type and target module.

### Step 3: Identify the source module, package, and target module

Read a message such as:

```text
module java.base does not "opens java.lang" to unnamed module ...
```

We have:

- Source module: `java.base`.
- Package: `java.lang`.
- Target: an unnamed module; in a classpath application example, the flag target is typically `ALL-UNNAMED`.
- Problem type: requires deep reflection, so inspect `--add-opens` rather than `--add-exports`.

If the error states “does not export”, that is usually a sign of ordinary access/export. Still, inspect the stack trace and access type to avoid applying the wrong fix.

### Step 4: Inspect the module graph and artifacts

Some reference commands:

```bash
java --list-modules

java --describe-module java.base

jar --describe-module --file path/to/dependency.jar

java --show-module-resolution \
     --module-path mods \
     -m com.example.app/com.example.app.Main
```

You can use `jdeps` to find some static dependencies on internal APIs:

```bash
jdeps --recursive --jdk-internals path/to/application.jar
```

These tools do not fully detect reflection, classes loaded by configured names, or plugins appearing at runtime. Therefore, a negative result does not prove the application has no dependencies on internal APIs.

### Step 5: Choose the least-permissive solution

If a replacement public API exists, prioritize switching APIs. If temporary flags must be used:

- Exact **source module/package**.
- Exact **target module**, or `ALL-UNNAMED` when genuinely necessary.
- Exact **permission type** (export or open).
- Exact **process** (compiler, test runtime, app runtime).
- Include an explanation and a review milestone.

### Step 6: Verify on a representative configuration

Build and test on the target JDK. Check startup, reflection, serialization, database drivers, logging, agents, and business flows using the relevant frameworks.

If the app runs on JDK 11 but the target is JDK 17 or 21, test on the target JDK; do not treat warnings on the older version as proof that it will run on the newer version.

### Step 7: Document the workaround and removal plan

Create a brief record using the template:

| Field | Content |
| --- | --- |
| JVM flag | Full `--add-exports` or `--add-opens` flag. |
| Source module/package | For example, `java.base/java.lang`. |
| Target module | Specific module or `ALL-UNNAMED`. |
| Offending component | Artifact, framework, and version. |
| Access type | Compile-time ordinary, runtime ordinary, or deep reflection. |
| Evidence | Stack trace, compiler diagnostic, test log. |
| Scope of application | Build, test, server, or container. |
| Long-term resolution | Upgrade dependency, fix code, or update descriptor. |
| Owner | Responsible team. |
| Review milestone | Next release or migration phase. |

## 14. Common misconceptions

**“`--add-exports` opens everything in the package.”** No. It does not change `private` visibility or automatically allow deep reflection.

**“`--add-opens` lets you `import` any internal class.”** No. It mainly handles deep reflection at runtime; ordinary source access still requires an export and the other conditions.

**“Having `requires` lets you use every package.”** No. Module readability and package export are two separate boundaries.

**“`ALL-UNNAMED` only grants access to app.jar.”** No. It represents unnamed modules, which may include multiple classpath libraries and class loaders.

**“Flags in the build will be picked up by production.”** No. The JVMs running the build, tests, and application can be different.

**“Just adding `--add-opens` fixes every `ClassNotFoundException`.”** False. Class-not-found errors are usually caused by dependencies, class loaders, or module resolution.

**“JDK 11 only warns, so JDK 17 will also run.”** Not necessarily. Strong encapsulation policies have changed across Java versions.

**“Having many access-opening flags is normal after migration.”** Some temporary flags may be needed, but they should be inventoried and removed once frameworks, dependencies, or source code become compatible.

## 15. Checklist before concluding the issue is resolved

- [ ] Confirmed whether the error belongs to ordinary access or deep reflection.
- [ ] Identified the module containing the package and the module performing the access.
- [ ] Checked the module path, classpath, module readability, and class loader.
- [ ] Distinguished `exports`/`opens` in the descriptor from runtime flags.
- [ ] Used `--add-exports` for cases needing ordinary access and placed it at the appropriate compile/runtime stage.
- [ ] Used `--add-opens` for deep reflection on the JVM executing the relevant component.
- [ ] Verified whether the target is a named module or `ALL-UNNAMED`, without guessing from the JAR name.
- [ ] Confirmed that replacing with a public API or newer library version is not possible before keeping a workaround.
- [ ] Tested on the target JDK and a production-like configuration.
- [ ] Recorded the access-opening risk, scope, owner, and flag removal plan.

## 16. Summary

**`--add-exports` addresses another module accessing types/members via ordinary Java language access in an unexported package. `--add-opens` addresses a framework or other code needing deep reflection into an unopened package.** Both options share the same syntax for specifying module/package/target, yet differ in the type of access they grant.

In Java compatibility migration, do not treat JVM flags as trial-and-error guesswork. Identify the module graph, access type, where the error occurs, and which JVM needs configuration, then grant the least access possible. Long-term solutions should be public APIs, libraries supporting the target JDK, and clear module descriptors; access-opening flags should only serve as controlled bridges during the transition.
