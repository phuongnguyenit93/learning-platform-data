# Limits of `--illegal-access` Across JDK Generations

When upgrading Java from JDK 8 to versions with the Java Platform Module System (JPMS), an application that was running stably may suddenly encounter reflection errors when accessing internal JDK classes, constructors, methods, or fields. To support the transition from the traditional classpath, JDK 9 introduced the `--illegal-access` option to temporarily relax part of access control. However, this mechanism is **only transitional**: the default behavior changed starting in JDK 16, and starting in **JDK 17, `--illegal-access` no longer opens internal packages**.

This is an important change in Java Advance Compatibility Migration. A deployment script that previously worked around an error using `--illegal-access=permit` on JDK 11 cannot continue relying on the same command on JDK 17. At the same time, this option was never a general-purpose solution for accessing all internal JDK APIs.

This lesson explains the scope of each mode, changes across JDK generations, differences between `--illegal-access` and targeted package open/export options, error diagnosis, and a migration strategy that does not depend on temporary mechanisms.

## 1. Background: Reflection Before and After JPMS

### 1.1. Java 8 and Earlier Versions

In the traditional classpath model, some frameworks use reflection to deeply access JDK or library implementations. For example, they may call `setAccessible(true)` to bypass Java language access restrictions on non-public members.

```java
import java.lang.reflect.Field;

public class InspectString {
    public static void main(String[] args) throws Exception {
        Field field = String.class.getDeclaredField("value");
        field.setAccessible(true);
        System.out.println(field.getType());
    }
}
```

This is only an **example of the kind of access that needs to be investigated**, not a way to access `String` internals that should be used in a real application. The implementation of `String` can change across releases; even relying on a field named `value` is already an unstable dependency.

Java 8 does not have JPMS and does not support `--illegal-access`. Some reflective accesses in legacy classpath code may work, but that does not constitute a guarantee that internal fields or methods will exist and remain accessible on newer Java versions.

### 1.2. JPMS Starting in JDK 9

JPMS introduces the concepts of **named module**, **unnamed module**, and `reads`, `exports`, and `opens` relationships:

- `exports` allows code in other modules to access public types in the exported package, according to JPMS rules.
- `opens` allows deep reflection into a package within the specified scope.
- Packages that are not exported/opened can be encapsulated even when the class or member exists in the runtime image.
- Code loaded from the classpath belongs to the unnamed module and is subject to the corresponding module rules.
- Code on the module path may belong to an explicit named module or an automatic named module.

When legacy classpath applications were moved onto JDK 9, a large number of libraries still depended on pre-JPMS reflection capabilities. Therefore, the JDK provided `--illegal-access` as a migration bridge, not as a long-term guaranteed API.

### 1.3. What Does Strong Encapsulation Protect?

Strong encapsulation restricts access to module implementation details. For example, the package `java.base/java.lang` is not opened by default to code on the classpath just because `java.lang.String` is a public class.

When a framework attempts to call `setAccessible(true)` on a private field in an unopened package, modern JDKs can throw:

```text
java.lang.reflect.InaccessibleObjectException:
  Unable to make field ... accessible:
  module java.base does not "opens java.lang" to unnamed module ...
```

The message identifies the module owning the package, the blocked package, and the module performing the access. This is more accurate evidence than guessing that "Java 17 does not support reflection".

**Reflection is still supported in modern Java.** The issue is that the code is requesting deep access into something not opened under the module contract.

## 2. Timeline of `--illegal-access`

You cannot understand `--illegal-access` without considering the JDK version. The same launch parameter can have different meanings or no longer take effect.

| JDK generation | `--illegal-access` status | Main behavior and consequences |
|---|---|---|
| JDK 8 and earlier | Option does not exist | No JPMS yet; the flag cannot be used to handle issues |
| JDK 9–15 | Active; default mode is `permit` | Temporarily relaxes some internal packages that existed in JDK 8 for code in unnamed modules; warns on illegal access |
| JDK 16 | Strong encapsulation becomes the default per JEP 396 | Modes `permit`/`warn`/`debug` can still be used to re-enable the corresponding relaxation mechanism, but should not be relied on long-term |
| JDK 17 | `--illegal-access` is disabled per JEP 403 | The flag no longer reopens packages; may emit a warning that the option is ignored |
| Post-17 JDKs | Flag should not be treated as a way to open packages | Rely on public APIs and targeted `--add-opens`/`--add-exports` options when genuinely needed; check documentation of the deployed JDK |

Two milestones to remember:

1. **JDK 16: default switches to strong encapsulation.** Moving from JDK 11 to 16 can expose reflection errors that JDK 11 previously permitted.
2. **JDK 17: `--illegal-access=permit` cannot be used to restore the previous relaxed behavior.** Moving from JDK 11 or 16 to 17 requires fixing dependencies, updating code, or opening the exact package with a targeted mechanism.

The basis for these changes includes JEP 261 (JPMS), JEP 396 (Strongly Encapsulate JDK Internals by Default), and JEP 403 (Strongly Encapsulate JDK Internals). These are Java platform milestones, not changes specific to Spring, Maven, or Gradle.

## 3. Modes of `--illegal-access` on JDKs That Still Support It

In releases where the option is still effective, common syntax is:

```bash
java --illegal-access=permit -jar app.jar
java --illegal-access=warn   -jar app.jar
java --illegal-access=debug  -jar app.jar
java --illegal-access=deny   -jar app.jar
```

The modes described below represent the **historical behavior of the transitional mechanism**, not instructions for re-enabling it on JDK 17.

### 3.1. `permit` — Relaxation with Initial Warning

The `permit` mode allows certain illegal reflective access operations on JDK packages in the transitionally supported set. This was the default in JDK 9–15.

When the first illegal access is detected, the runtime may print a warning like:

```text
WARNING: An illegal reflective access operation has occurred
WARNING: Illegal reflective access by ...
WARNING: Please consider reporting this to the maintainers ...
WARNING: All illegal access operations will be denied in a future release
```

The warning indicates that the application or a library depends on access that is about to be tightened. **Having no immediate error does not mean the code is compatible with future JDKs.**

### 3.2. `warn` — Warning for Each Detected Access

```bash
java --illegal-access=warn -jar app.jar
```

In supporting JDKs, `warn` maintains the corresponding relaxation scope while emitting more detailed warnings for illegal reflective access operations.

This mode is useful when preparing a migration from JDK 11: it shows which code paths still use reflection into JDK internals, instead of seeing only the first warning.

However, if a flow only runs on a schedule or when an error occurs, it still might not appear in the logs. It needs to be combined with testing and dependency analysis.

### 3.3. `debug` — Warning with Trace Information

```bash
java --illegal-access=debug -jar app.jar
```

The `debug` mode provides information such as a stack trace to trace which code is performing the access. It is especially useful when the issue originates from a transitively loaded library that the application does not call directly.

For example, when analyzing the output, look for:

- The JAR name and class invoking reflection.
- The method/framework calling `setAccessible` or an equivalent API.
- The accessed JDK package and module.
- The version of the library causing the access.
- Which execution path triggers the behavior.

This debug-level logging should not be left enabled regularly in production if it produces high log volume or exposes unnecessary implementation details.

### 3.4. `deny` — Denying Access Relaxation

```bash
java --illegal-access=deny -jar app.jar
```

In supporting JDK 9–16 releases, `deny` instructs the runtime not to open packages under the default relaxation mechanism. This used to be a useful way to **test early how much the application depends on illegal reflective access** before moving to JDK 17.

For example, a JDK 11 application that only runs with `permit` but fails with `deny` is a clear sign that there are dependencies that need fixing before migration.

Do not interpret `deny` as blocking all reflection: public APIs and properly opened packages can still be used according to Java/JPMS rules.

### 3.5. Differences Among the Four Modes

| Mode | Relaxes the corresponding scope? | Purpose in JDK 9–16 |
|---|---|---|
| `permit` | Yes | Transition for legacy applications, logs initial warning |
| `warn` | Yes | Finds more illegal access points via warnings |
| `debug` | Yes | Traces the source of access via trace information |
| `deny` | No | Detects reliance on the relaxation mechanism early |

Starting from JDK 17, this table is only relevant for **understanding operational history or reading legacy configurations**. You cannot rely on `permit`, `warn`, or `debug` to restore relaxation on JDK 17.

## 4. The Very Narrow Scope of the Relaxation Mechanism

Even when `--illegal-access=permit` was active, it never meant "allow everything".

### 4.1. Only Serves a Group of JDK Packages with Pre-JPMS History

The relaxation mechanism initially targeted internal packages of runtime modules that already existed in JDK 8, making it easier for legacy classpath applications to transition.

Packages introduced after Java 8 or not belonging to the transitionally supported group **are not automatically opened** just because the user sets `permit`.

Therefore, two reflection errors in the same application may react differently to the flag: one belonging to the relaxed group may disappear on JDK 11, while another remains blocked.

### 4.2. Primarily Applies to Code in the Unnamed Module

Historically, `--illegal-access` targeted code on the classpath, i.e., unnamed modules. It is not a mechanism for granting access to open every package to every named module on the module path.

If a library is moved from the classpath to an explicit named module, it may lose the relaxation behavior that the runtime previously applied to unnamed modules. In that case, `exports`, `opens`, `requires`, and the actual target module name must be examined.

Do not confuse:

```text
Classpath code  -> unnamed module
Module-path JAR -> automatic or explicit named module
```

The two contexts have different access rules.

### 4.3. Does Not Solve Direct References to All JDK Internal APIs

For example, code compiled directly against a `sun.*` type or an unexported package can fail at compile time. `--illegal-access` was designed primarily for transitional **illegal reflective access**; it is not a general tool for exporting all internal APIs to the compiler.

When code genuinely needs to reference a public type in an unexported package, you must distinguish `--add-exports` (for type access) from `--add-opens` (for deep reflection).

### 4.4. Does Not Restore APIs or Tools Removed from the JDK

If a class, module, or tool has been removed from the JDK, opening a package will not make that class reappear.

Examples:

- JAXB/JAX-WS modules were removed from the JDK starting in Java 11.
- The Nashorn JavaScript engine was removed from the JDK starting in Java 15.
- Several older JDK tools or internal APIs disappeared across different milestones.

Missing-class errors caused by a module no longer existing require replacement dependencies, API changes, or redesigning functionality. `--illegal-access` and `--add-opens` do not solve missing artifacts.

### 4.5. Does Not Replace Behavioral Compatibility Testing

Even when reflection into a private field succeeds, object layout, field types, and internal invariants can still change across JDKs. Code that directly accesses `String` internals, collection internals, or memory internals may read incorrect data or break invariants.

Success of `setAccessible(true)` is not proof that the internal API is safe for long-term use.

## 5. Why Are JDK 16 and JDK 17 Two Turning Points?

### 5.1. JDK 16: Strong Encapsulation Becomes the Default

Before JDK 16, many classpath applications received warnings yet still ran thanks to the default `permit` mode. With JDK 16, strong encapsulation became the default per JEP 396.

Consequences:

- Without additional flags, previously relaxed accesses can throw exceptions.
- `--illegal-access=permit` can still be used in JDK 16 to fall back to the transitional mechanism within its historical scope.
- Migration teams have a transition window to find and upgrade libraries before JDK 17.

Therefore, if a system is on JDK 11 and aims to upgrade to JDK 17, success with `--illegal-access=deny` on JDK 11/15 should be treated as a positive signal, **but not sufficient proof**. You must run on JDK 17 because there are many other changes across the intermediate releases.

### 5.2. JDK 17: The Flag No Longer Opens Packages

JEP 403 removed the ability to re-enable relaxed strong encapsulation using `--illegal-access`. If you still pass:

```bash
java --illegal-access=permit -jar app.jar
```

on JDK 17, the runtime may warn that the option was ignored. Deep reflection accesses to unopened packages are still denied.

A configuration that worked on JDK 11 **cannot be kept as-is and treated as a fix on JDK 17**. You must identify the exact package, the calling module, and a specific solution.

### 5.3. An Exception to Understand Correctly: `jdk.unsupported`

The JDK still includes the `jdk.unsupported` module providing certain APIs retained for special compatibility needs, such as some types under `sun.misc` and `sun.reflect`. These APIs have their own policies and risk levels, which does not mean every `sun.*` package is open.

Do not interpret "JDK 17 encapsulates more strongly" as "all sun.* accesses disappear". For each package, you need to determine its owning module and actual export/open status. Moving to standard APIs whenever possible remains the best approach.

## 6. `--add-opens`: A Targeted Measure When Deep Reflection Is Still Needed

If a library cannot be replaced immediately, the JDK allows opening a specific package using `--add-opens`.

Syntax:

```text
--add-opens <source-module>/<package>=<target-module>
```

For example, a classpath application needing to reflect into the `java.lang` package of `java.base`:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
```

Meaning:

- `java.base`: the module owning the package.
- `java.lang`: the package being opened.
- `ALL-UNNAMED`: all unnamed modules, typically including code from the classpath.

Unlike the historical `--illegal-access=permit`, this option **only opens the specified package**, and does not automatically open an entire set of internal packages.

### 6.1. If the Caller Is a Named Module

For a modular application:

```java
module com.example.app {
    requires com.example.reflection.lib;
}
```

if code in `com.example.reflection.lib` genuinely needs deep reflection into `java.base/java.lang`, you can use the configuration:

```bash
java --add-opens java.base/java.lang=com.example.reflection.lib \
  --module-path mods \
  --module com.example.app/com.example.app.Main
```

Do not automatically use `ALL-UNNAMED` for code belonging to a named module; permission must be granted to the exact module name performing the reflection.

### 6.2. Choose the Target Module from the Stack Trace, Do Not Guess

An error typically provides a message similar to:

```text
module java.base does not "opens java.lang" to unnamed module @...
```

In that case, the suggested flag might be:

```text
--add-opens java.base/java.lang=ALL-UNNAMED
```

However, if the message indicates `com.example.framework` as the caller, the target must be the appropriate module name instead of specifying the wrong module.

Always inspect the stack trace to determine **which library is performing the access**, because the caller may not be application code.

### 6.3. Opening a Package Does Not Restore Removed APIs

`--add-opens` only affects access permissions. It does not create deleted classes, methods, or fields, does not fix method descriptor mismatches, and does not guarantee stable implementation details.

If the `String.value` field changes type between two JDKs, opening `java.lang` does not revert the field to its old type.

### 6.4. The Cost of `ALL-UNNAMED`

`ALL-UNNAMED` opens the package to code in every unnamed module within the runtime scope. If the classpath contains many unaudited libraries, this may be broader than necessary.

Therefore:

- Prioritize upgrading libraries to remove dependencies on internal deep reflection.
- Only open packages when there is concrete evidence.
- Avoid copying a long list of `--add-opens` flags from another environment.
- Record an owner and expected removal timeframe for each flag.
- For named modules, prefer a specific target when feasible.

## 7. How Does `--add-exports` Differ from `--add-opens`?

Both options relate to JPMS but solve different problems.

| Option | Primary purpose | Example |
|---|---|---|
| `--add-exports` | Allows other code to reference public types/members in an otherwise unexported package | Compile/runtime access to an internal public class |
| `--add-opens` | Allows deep reflection into a package, including non-public members under reflection rules | A framework using `setAccessible(true)` |

Example of exporting a package containing an internal public type to unnamed modules:

```bash
java --add-exports java.base/sun.nio.ch=ALL-UNNAMED -cp "lib/*:app.jar" com.example.Main
```

Example of opening a package for deep reflection:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED -cp "lib/*:app.jar" com.example.Main
```

If source code imports a type in an unexported package, the compiler may need `--add-exports` at compile time. If code calls `setAccessible` on a private field in an unopened package, the JVM may need `--add-opens` at runtime.

Using one flag does not mean all remaining rules can be bypassed. Some situations may require separate compile and runtime configurations; you should not add both unless proven necessary.

### 7.1. `opens` in `module-info.java`

If you **own** a module, a more sustainable approach is to declare the appropriate opening directly in the descriptor:

```java
module com.example.domain {
    exports com.example.domain.api;
    opens com.example.domain.model to com.example.json;
}
```

Here, the domain module opens `com.example.domain.model` only to `com.example.json`, provided these two modules exist with those exact names at deployment time. This differs from using `--add-opens` to intervene in packages owned by the JDK or another library.

When dealing with a library you do not own, the long-term solution should still come from a maintainer-supported library version, rather than modifying the command line in every deployment by default.

## 8. Full Example: Same Source, Different Results Between JDK 11 and 17

Consider the following illustrative program:

```java
import java.lang.reflect.Field;

public class DeepReflectionDemo {
    public static void main(String[] args) throws Exception {
        Field valueField = String.class.getDeclaredField("value");
        valueField.setAccessible(true);

        System.out.println("Accessible: " + valueField.getName());
    }
}
```

Compile:

```bash
javac DeepReflectionDemo.java
```

On historical JDKs that allowed relaxation:

```bash
java --illegal-access=permit DeepReflectionDemo
```

On JDK 11, this deep reflection operation can usually succeed due to the transitional mechanism while emitting an illegal reflective access warning.

To inspect the code path on JDK 11:

```bash
java --illegal-access=debug DeepReflectionDemo
```

On JDK 16 without flags, this operation may fail due to default strong encapsulation. Trying `--illegal-access=permit` on JDK 16 can temporarily reopen the historical scope.

On JDK 17:

```bash
java --illegal-access=permit DeepReflectionDemo
```

relaxation is no longer activated; `setAccessible(true)` may throw `InaccessibleObjectException`.

A targeted transitional configuration:

```bash
java --add-opens java.base/java.lang=ALL-UNNAMED DeepReflectionDemo
```

can permit this operation from an access control standpoint. However, this is **not a recommendation to access internal `String` fields in real applications**. Using standard APIs such as `String` methods or appropriate text-processing tools remains the safe approach.

### 8.1. Illustrative Result Matrix

| Runtime | No flag | `--illegal-access=permit` | `--add-opens java.base/java.lang=ALL-UNNAMED` |
|---|---|---|---|
| JDK 11 | May be relaxed by default, with warning | May be relaxed, with warning | Opens the exact package |
| JDK 16 | Usually denied for illegal deep reflection | May re-enable historical relaxation scope | Opens the exact package |
| JDK 17 | Denied if the package is not opened | Flag does not reopen the package | Opens the exact package |

The table describes an illustrative scenario with the `java.base/java.lang` package, not a rule applicable to every package or every reflection tool. Results also depend on the caller module, runtime arguments, and specific implementation.

## 9. Error Diagnosis: Distinguishing the Right Cause

Not every class-loading or reflection error is caused by `--illegal-access`.

### 9.1. `InaccessibleObjectException`

Symptom:

```text
java.lang.reflect.InaccessibleObjectException
module java.base does not "opens java.lang" to ...
```

The cause is usually deep reflection into an unopened package.

Resolution approach:

1. Identify the library invoking reflection.
2. Upgrade the library or switch to a public API.
3. If transition is mandatory, consider `--add-opens` for the exact package and exact caller.
4. Retest on the target JDK.

### 9.2. `IllegalAccessError`

A class may have compiled relying on access to a class/member that the new runtime does not permit. The issue may be exports, visibility, or a linkage change, not merely deep reflection.

Inspect the stack trace and bytecode dependencies. If a public type belongs to an unexported package, `--add-exports` may be relevant; if the member is non-public, exporting alone will not let code access it as a public API.

### 9.3. `ClassNotFoundException` or `NoClassDefFoundError`

If the class or module is not included at runtime, a flag that opens a package will not help find it. Check:

- Is the dependency on the classpath or module path?
- Has the module been removed from the JDK or replaced by a separate artifact?
- Are there version or classloader conflicts?
- Does the package actually exist in the deployed version?

### 9.4. `NoSuchMethodError` or `NoSuchFieldError`

The bytecode references a method/field not present in the runtime class. This is usually a sign of binary incompatibility or an implementation detail change.

`--illegal-access` and `--add-opens` do not restore methods/fields that were renamed, changed descriptors, or removed.

### 9.5. `SecurityException`, Permissions, or Sandbox Restrictions

Some environments have security or policy mechanisms distinct from module encapsulation. Read the exception type, message, and stack trace to distinguish them.

Do not add a bunch of JVM flags just because you see the word "access" in an exception.

## 10. Tools for Finding Access to JDK Internals

### 10.1. `jdeps --jdk-internals`

`jdeps` can analyze static bytecode references to certain JDK internal APIs:

```bash
jdeps --jdk-internals --recursive \
  --class-path "lib/*" app.jar
```

The output helps identify code referencing internal classes and may suggest replacement APIs.

Limitation: `jdeps` **does not fully detect** string-based reflection, dynamically generated class names, or access via JNI/native code. Therefore, no warnings from `jdeps` does not prove the entire application uses no JDK internals.

### 10.2. `jdeprscan`

`jdeprscan` helps scan for deprecated APIs used in bytecode:

```bash
jdeprscan --release 17 --class-path "lib/*" app.jar
```

This tool provides an additional perspective on deprecated APIs, but is not intended to replace detecting all illegal reflective accesses.

### 10.3. Logs and Stack Traces in Older JDKs

If you still have a JDK 11/15 environment:

```bash
java --illegal-access=warn -jar app.jar
java --illegal-access=debug -jar app.jar
```

Run a sufficiently representative test suite to exercise the code paths that need checking. Collect the accessed class names, libraries, methods, and packages. Then test JDK 17 in a test environment matching production.

Do not apply `--illegal-access=debug` on JDK 17 and expect to receive stack traces from the old warning mechanism.

### 10.4. Inventory Current JVM Arguments

Relevant configurations may exist in many places:

- `JAVA_TOOL_OPTIONS` or Java launch environment variables.
- Dockerfile and container entrypoint.
- Kubernetes manifests, Helm values, or systemd configurations.
- Maven Surefire/Failsafe `argLine`.
- Gradle `Test.jvmArgs`, `JavaExec.jvmArgs`, or `applicationDefaultJvmArgs`.
- IDE Run Configurations.
- Batch/shell scripts and service managers.
- Agent/instrumentation configurations for monitoring or profiling.

A common mistake is adding `--add-opens` to the JVM running the Gradle daemon while **tests actually run in a separate forked JVM**. In that case, the flag must be passed to the exact JVM containing the failing reflection code.

### 10.5. Verify the Actual Running Runtime

On a machine with multiple JDKs, the `java -version` output in a terminal does not necessarily reflect the runtime of a container or forked test JVM. Record:

```bash
java -version
java --list-modules
```

If diagnosing a running Java process, you can use an appropriate tool to inspect its actual command line, such as:

```bash
jcmd <pid> VM.command_line
```

Only run diagnostic tools when properly authorized and in permitted environments. Also check the JDK vendor/build to avoid drawing conclusions from a different runtime.

## 11. Migration Configuration in Maven, Gradle, and Containers

The examples below illustrate where to place configuration **in the JVM that will execute the application or tests**. Not every project needs these flags.

### 11.1. Maven Surefire

If tests run on JDK 17 and an older library genuinely needs deep reflection into `java.base/java.lang`:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <argLine>
                    --add-opens java.base/java.lang=ALL-UNNAMED
                </argLine>
            </configuration>
        </plugin>
    </plugins>
</build>
```

In projects with JaCoCo or other plugins that use `argLine`, coordinate configuration so as not to overwrite JVM arguments supplied by plugins. If integration tests run via Failsafe or another plugin, configure the corresponding JVM accordingly.

### 11.2. Gradle Test Task

```groovy
tasks.withType(Test).configureEach {
    jvmArgs '--add-opens', 'java.base/java.lang=ALL-UNNAMED'
}
```

With Gradle Kotlin DSL:

```kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("--add-opens", "java.base/java.lang=ALL-UNNAMED")
}
```

This option applies to the test worker JVM configured by the task. It does not automatically apply to the artifact running in production or to every `JavaExec` task.

### 11.3. Docker / Container Runtime

Launcher example:

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY app.jar /app/app.jar
ENTRYPOINT ["java", "--add-opens", "java.base/java.lang=ALL-UNNAMED", "-jar", "/app/app.jar"]
```

This is only a syntax example; this flag should not be added to every image. Once the library is upgraded and no longer needs deep reflection, remove the flag.

Do not use `--illegal-access=permit` as a fix for container errors on JDK 17, because that mechanism no longer opens packages.

### 11.4. Named Module on the Module Path

If the caller is a named module, you can configure a specific target:

```bash
java --add-opens java.base/java.lang=com.example.framework \
  --module-path mods \
  --module com.example.app/com.example.app.Main
```

You must confirm that `com.example.framework` actually exists as a named module at runtime. If the library is still on the classpath, the appropriate target may be `ALL-UNNAMED`.

## 12. Strategy for Replacing Code Dependent on JDK Internals

JVM flags should only be a transitional measure. Sustainable migration focuses on eliminating the reason internal access is needed.

### 12.1. Upgrade Dependencies to Versions Supporting the Target JDK

Some older libraries use reflection to optimize serialization, proxies, ORM, mocking, or bytecode generation. Newer versions may have changed how they interact with the JDK.

The process should include:

1. Identify the JAR and version causing the access.
2. Find the version supported by the maintainer on the target JDK.
3. Upgrade the dependency and related transitive dependencies.
4. Run tests on the target runtime.
5. Remove transitional JVM flags if no longer needed.

Do not add `--add-opens` simply because an online issue suggests doing so without checking the actual dependency version.

### 12.2. Use Public APIs Instead of Implementation Details

If custom code is accessing private JDK fields, look for standard APIs:

- Accessing string contents: use the `String` API instead of internal fields.
- Encoding/decoding Base64: use `java.util.Base64`.
- File operations: use `java.nio.file`.
- Synchronization and concurrency: use `java.util.concurrent`.
- Date/time operations: use `java.time`.
- Classpath/module analysis: use `jdeps`, `ModuleLayer`, or supported APIs/module tools as needed.

There is no one-to-one replacement for every internal detail; some legacy optimizations need to be redesigned.

### 12.3. If You Own the Module Being Reflected Into

For internally developed modules, you can declare selective `opens`:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.serializer;
}
```

This expresses the reflection contract clearly. Avoid `open module` for the entire module if only one package needs to be opened.

### 12.4. When Immediate Replacement Is Not Yet Possible

If there is a valid operational reason to keep an `--add-opens`:

- Record the source package name and target module.
- Record the library and version requiring the flag.
- Record the cause along with a stack trace or reproducing test.
- Assign an owner responsible for removing it.
- Schedule dependency upgrades or code fixes.
- Place the flag consistently in configurations across test and production environments.
- Do not treat the flag as a compatibility guarantee in subsequent JDKs.

## 13. Practical Migration Workflow from JDK 11 to 17

### Step 1: Freeze the Baseline

Save the JDK vendor/version, dependency graph, startup scripts, JVM args, and test reports while the application is still running on JDK 11.

### Step 2: Find All `--illegal-access` and Similar Flags

Audit CI/CD, containers, build tools, IDEs, and scripts. Distinguish:

```text
--illegal-access=permit
--illegal-access=warn
--illegal-access=debug
--illegal-access=deny
--add-opens
--add-exports
```

Determine which flags are still used at actual runtime and which are legacy artifacts in documentation.

### Step 3: Collect Evidence from an Environment That Still Supports the Flag

If JDK 11 is available, use `warn`/`debug` mode with a representative test suite to locate illegal reflective accesses. You can run with `deny` to check readiness for strong encapsulation within the scope of that JDK.

### Step 4: Classify Each Finding

| Category | Example | Remediation approach |
|---|---|---|
| Older library reflects into JDK internals | Proxy/serializer/ORM | Upgrade version or replace library |
| Application itself reflects into JDK fields | `String.value` | Rewrite using public APIs |
| Code calls public type in unexported package | Importing `sun.nio.ch` | Replace API or evaluate transitional `--add-exports` |
| Reflection into internal module owned by the team itself | DTO/field in named module | Configure selective `opens` |
| Class/module already removed from JDK | Legacy API no longer present | Add replacement dependency or redesign |
| Error due to mismatched runtime dependencies | `NoSuchMethodError` | Align dependencies and binary contracts |

### Step 5: Upgrade Frameworks and Dependencies

Prefer versions supporting JDK 17. Check both direct and transitive dependencies, especially ASM, Byte Buddy, CGLIB, JAXB/Jackson, ORM, testing tools, and instrumentation agents if used.

### Step 6: Run on JDK 17 Without Relying on `--illegal-access`

Test startup, unit/integration tests, and flows using reflection. If errors occur, collect full stack traces and identify the exact package/module rather than opening packages wholesale.

### Step 7: Add Only Necessary `--add-opens` During the Transition Period

If a library cannot yet be upgraded but the system needs to move to JDK 17, add the flag for the exact package and exact caller as a temporary measure. Link it to a technical issue and recheck after each dependency upgrade.

### Step 8: Verify the Real Deployment Environment

Run the artifact using the same runtime image, classpath/module path, agents, and configuration as production. A test passing in an IDE does not prove that the JVM in the container received the right flags.

### Step 9: Remove Outdated Configuration

Remove `--illegal-access`, which no longer has any effect on JDK 17, and progressively remove `--add-opens` flags that are no longer needed. Update documentation and pipelines so meaningless parameters are not carried into subsequent JDK upgrades.

## 14. Common Misconceptions

### "`--illegal-access=permit` Fixes Reflection Errors on Java 17"

**False.** Starting in JDK 17, the flag does not re-enable relaxed strong encapsulation. You need to fix the dependency/code or, if unavoidable, open the exact package with `--add-opens`.

### "`--illegal-access` Used to Open All JDK Packages"

**False.** The transitional mechanism had a limited historical scope and did not apply broadly to every package, module, or access type.

### "If Running on JDK 11 Produces No Warnings, It Is Definitely Safe"

**False.** The `permit` mode usually prints only an initial warning; unexecuted code paths do not appear in logs. Dynamic reflection or JNI may also not be fully detected.

### "`--add-opens` and `--add-exports` Are the Same"

**False.** One option mainly relates to deep reflection; the other permits access to public types in unexported packages. Read the exact error and requirement carefully.

### "Opening a Package Means the Internal API Is Stable"

**False.** Opening only addresses the access control barrier. Classes, fields, methods, or semantics can still change or disappear.

### "Adding Flags to Maven/Gradle Automatically Applies Them to Production"

**False.** The JVM running the build, the forked test JVM, and the JVM running the application are different processes. Flags must be applied to the right process.

### "Just Open All Packages to `ALL-UNNAMED` to Avoid Errors"

**Not recommended.** This makes the access scope wider than necessary, hides outdated dependencies, and increases future migration effort.

## 15. Checklist Before Removing `--illegal-access`

- [ ] Identified the exact JDK runtime and understood the change milestones in JDK 16/17.
- [ ] Audited all `--illegal-access` JVM arguments across build, test, and deployment.
- [ ] Distinguished whether the caller belongs to an unnamed module or a named module.
- [ ] Collected stack traces, source packages, and owning modules when reflection fails.
- [ ] Ran `jdeps --jdk-internals` to locate relevant static references.
- [ ] Upgraded frameworks and dependencies that rely on JDK internals.
- [ ] Replaced custom code with public APIs where feasible.
- [ ] Avoided using `--illegal-access=permit` as a JDK 17 workaround.
- [ ] Where needed, used `--add-opens` or `--add-exports` of the right type, for the right package, and to the right target.
- [ ] Assigned an owner, evidence, and removal plan for each transitional flag.
- [ ] Tested both the actual runtime/module path and forked test JVMs.
- [ ] Verified business flows using reflection, serialization, proxies, and instrumentation.
- [ ] Removed flags that are no longer needed and recorded the final launch configuration.

## 16. Conclusion

`--illegal-access` was introduced in the early stage of JPMS to help legacy classpath applications transition when the JDK began encapsulating internal packages. On JDK 9–15, the default `permit` mode could allow certain illegal reflective accesses with warnings; JDK 16 switched the default to strong encapsulation while retaining a transitional relaxation mechanism; by JDK 17, `--illegal-access` no longer opens packages.

For a sustainable migration, stop relying on `--illegal-access=permit`. Identify exactly which code is accessing internals, upgrade libraries or switch to public APIs, use targeted `--add-opens`/`--add-exports` when genuinely required, and test on the final deployment JVM. This approach keeps the system proactive with respect to JDK encapsulation changes rather than dependent on a compatibility mechanism that has already ended.
