# NoSuchMethodError and NoSuchFieldError Due to Library Version Mismatch in Java

A Java program can **compile successfully**, yet throw at runtime:

```text
java.lang.NoSuchMethodError: ...
java.lang.NoSuchFieldError: ...
```

These two errors commonly occur when **client code was compiled against the API of library version A**, while at execution time the JVM loads a **class definition from version B that no longer has the member with the exact name and descriptor**. This is a **binary linkage / binary compatibility** error, not simply the compiler “not finding a method” in source code.

In Java, bytecode stores **symbolic references** to methods/fields in the *constant pool* of the caller class. When linking a reference, the JVM must find **the exact class and member with the name and descriptor** that the bytecode recorded. If the loaded class exists but the referenced method/field **no longer matches**, the JVM may throw `NoSuchMethodError` or `NoSuchFieldError`.

This article belongs to the **Common Errors** group in Java core – classloader, focusing on: version mismatch causes, symbolic resolution mechanics, name + descriptor (including return type and field type), a Java 17+ example reproducing **both errors**, how to inspect which loader actually loaded a class, resolving dependency conflicts, JAR/fat JAR packaging, plugin/classloader systems, and prevention strategies.

## 1. Understanding the Error Type Correctly: LinkageError, Not an Ordinary Exception

Important hierarchy:

```text
java.lang.Throwable
├── java.lang.Exception
│   └── java.lang.ReflectiveOperationException
│       └── java.lang.NoSuchMethodException
└── java.lang.Error
    └── java.lang.LinkageError
        ├── java.lang.IncompatibleClassChangeError
        │   ├── java.lang.NoSuchMethodError
        │   ├── java.lang.NoSuchFieldError
        │   ├── java.lang.IllegalAccessError
        │   ├── java.lang.AbstractMethodError
        │   └── ...
        ├── java.lang.NoClassDefFoundError
        ├── java.lang.VerifyError
        └── ...
```

`NoSuchMethodError` and `NoSuchFieldError` are **Errors** belonging to the **IncompatibleClassChangeError → LinkageError** family, typically indicating that the binary classes combined at runtime **are no longer compatible with each other**.

**Do not confuse:**

- `NoSuchMethodException`: a reflection API such as `Class.getMethod("m", ...)` fails to find a member using reflection lookup, and the caller can handle this checked exception.
- `NoSuchMethodError`: compiled bytecode references the method, but when the JVM resolves the runtime symbolic reference, a matching method does not exist.
- `NoSuchFieldException`: reflection `Class.getDeclaredField("x")` cannot find the field.
- `NoSuchFieldError`: bytecode contains a symbolic reference to a field, and JVM field resolution cannot find a matching field.

In production, you should not use `catch (NoSuchMethodError e) { /* bỏ qua */ }` as a long-term fix. Catching the error can be useful in diagnostic examples; real applications need to **fix the dependency/runtime classpath and restore binary compatibility**.

## 2. Why Does Source Compile While Runtime Still Fails?

Imagine there are three artifacts:

```text
vendor-api-v1.jar      client.jar       vendor-api-v2.jar
    |                     |                    |
    |  compile dependency |                    |
    +-------------------->|                    |
                          | client bytecode     |
                          | stores method/field |
                          | v1 symbols          |
                          |                     |
                          +------------------->| Runtime classloader
                                               | loads Vendor from v2
                                               |
                                               v
                                   v1 method/field does not exist
                                   with the exact descriptor in v2
                                               |
                                               v
                                       LinkageError at runtime
```

At compile time, `javac` sees `lib.Vendor.format()` and `lib.Vendor.LEVEL` in v1. The compiler generates bytecode and a constant pool that explicitly record the **symbolic references** that the calls will use. Afterward, the build or deployment **does not necessarily bundle the exact v1 binary**: the library may be upgraded, downgraded, excluded by dependency mediation, or shadowed by another JAR on the classpath.

If you simply run the **old client.class** against **vendor-api-v2.jar**, the JVM does not “recompile” the caller to automatically replace `Vendor.format()` with a new method name, nor does it automatically treat a different field as a replacement.

As a result:

- **Compile-time API:** the set of members that the client was compiled against.
- **Runtime definition:** the set of members of the class that the JVM **actually loads**.
- **Linkage:** the JVM attempts to link the symbolic reference in the client with the runtime definition.
- **Mismatch:** the member does not exist with the exact name/descriptor → corresponding error.

This point is especially important in multi-module applications, plugins, application servers, Gradle/Maven projects with many dependencies, and libraries with transitive dependencies.

## 3. What Does Method Resolution Actually Look For?

A method symbolic reference in a class file stores:

1. **Owner class/interface** by binary name.
2. **Method name**, for example `format`.
3. **Method descriptor** consisting of the **parameter types** and **return type**.

Java example:

```java
public static String format()
```

is represented in a JVM descriptor (no parameters, returning `java.lang.String`) as:

```text
format:()Ljava/lang/String;
```

An overload:

```java
public static int format(int n)
```

uses the descriptor:

```text
format:(I)I
```

Common notations:

| Java type | JVM field descriptor |
| --- | --- |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `void` (method result only) | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

**The return type is also included in the JVM method descriptor**, even though certain source-level overloading rules in Java do not allow distinguishing methods based solely on return type. Therefore, a return type change can break binary linkage even when the method name and parameter list look identical at a glance.

According to JVMS 17 `5.4.3.3`, method resolution uses the name and descriptor of the reference. If lookup fails, `NoSuchMethodError` may be thrown. However, a method may still be found in a superclass or interface according to the resolution rules; **simply removing a local declaration from a class does not mean every client immediately fails** if a compatible inherited method still exists.

### Which Changes Commonly Lead to NoSuchMethodError?

| API the client compiled against | Different runtime API | Risk |
| --- | --- | --- |
| `String format()` | Remove `format()` | High: old reference cannot be resolved |
| `String format()` | Rename to `describe()` | High: different name |
| `String format()` | Change to `String format(String mode)` | High: different parameter descriptor |
| `String format()` | Change to `Object format()` | Possible NoSuchMethodError due to **different return descriptor** |
| `Vendor()` public no-arg | Only constructor `Vendor(int)` remains | Possible `NoSuchMethodError: <init>()V` |
| `format()` instance | `format()` static with same descriptor | Possible **IncompatibleClassChangeError**, not necessarily NoSuchMethodError |
| Method remains but visibility is reduced | For example, public to private | Possible `IllegalAccessError` instead of NoSuchMethodError |

Do not lump every API modification into a single error: the JVM distinguishes between **not finding the member**, **lacking access permission**, and **mismatched static/instance kind**.

## 4. Field Resolution and Why Field Type Matters

Similarly, a symbolic reference to a field stores:

1. Owner class/interface.
2. Field name.
3. **Field descriptor** = type of the field.

Example:

```java
public static int LEVEL = 7;
```

creates the field reference:

```text
lib/Vendor.LEVEL:I
```

If runtime has `public static long LEVEL = 7L;`, the name `LEVEL` still exists, but the **descriptor changes from `I` to `J`**. The old reference `LEVEL:I` can fail with `NoSuchFieldError` because the JVM is looking for a field with **the exact name and descriptor**, not just a “similar name”.

According to JVMS 17 `5.4.3.2`, lookup inspects the owner class/interface and its superinterfaces/superclasses according to the rules, and if no field with the name+descriptor is found, it throws `NoSuchFieldError`. Some structural changes remain compatible thanks to inherited fields; you need to examine the actual binaries rather than guessing from a source diff.

### Field Changes and Possible Error Types

| V1 compile API | V2 runtime API | Notes |
| --- | --- | --- |
| `public static int LEVEL` | Remove `LEVEL` | Usually leads to `NoSuchFieldError` |
| `public int level` | Rename to `count` | Old reference does not find the name |
| `public static int LEVEL` | `public static long LEVEL` | Different descriptor; possible `NoSuchFieldError` |
| `public int count` | `public static int count` | Mismatched field access opcode; possible `IncompatibleClassChangeError` |
| `public int count` | `private int count` | Possible `IllegalAccessError` |
| `public static final int VERSION = 1` | Change value to 2 | **May not error** because the constant was inlined into the client; still sees the old value |

**The `static final` compile-time constant case** is very special: if a field is a *constant variable* (`static final` primitive or `String` with a constant expression), `javac` may **inline the value** into the client instead of emitting a `getstatic` instruction. When the field is changed or removed at runtime, the old client might **not throw `NoSuchFieldError`** because the bytecode **no longer has a symbolic field reference** at that usage site, yet the value becomes stale.

That is why the exact reproduction example in the next section uses a **non-final `public static int LEVEL`**, to force the client bytecode to contain `getstatic`.

## 5. Java 17+ Example Reproducing Both Errors Using v1/v2

The example has three independent source sets: library v1, library v2, and a client compiled only against v1. **The client is NOT recompiled when switching runtime to v2** — this is the condition that produces the binary mismatch error.

### 5.1 Structure

```text
linkage-demo/
├── v1-src/
│   └── lib/Vendor.java
├── v2-src/
│   └── lib/Vendor.java
├── client-src/
│   └── app/Client.java
├── v1-classes/          (v1 library output)
├── v2-classes/          (v2 library output)
└── client-classes/      (output of client compiled against v1)
```

Create the output directories before running. Do not place both `lib/Vendor.java` files into **a single source root** at the same time, because they are **two different versions of the same binary class name**.

### 5.2 Library v1

File `v1-src/lib/Vendor.java`:

```java
package lib;

public final class Vendor {
    public static int LEVEL = 7; // Non-final: client must use getstatic.

    public static String format() {
        return "v1 format";
    }
}
```

The client will compile successfully because v1 has both the `format()` method and the `LEVEL` field.

### 5.3 Incompatible Library v2

File `v2-src/lib/Vendor.java`:

```java
package lib;

public final class Vendor {
    public static int REVISION = 2;

    public static String describe() {
        return "v2 describe";
    }
}
```

The class **`lib.Vendor` still exists**, but the two members the client used were renamed: `format()` is gone, and `LEVEL` is gone. If you compile the client directly against v2, `javac` will report that the symbols cannot be found; the issue here is that **client.class was compiled earlier against v1**, so the errors only appear at runtime.

### 5.4 Client Compiled Against v1

File `client-src/app/Client.java`:

```java
package app;

import lib.Vendor;

public class Client {
    public static void main(String[] args) {
        try {
            System.out.println("method=" + Vendor.format());
        } catch (NoSuchMethodError error) {
            System.out.println("method link="
                    + error.getClass().getSimpleName());
        }

        try {
            System.out.println("field=" + Vendor.LEVEL);
        } catch (NoSuchFieldError error) {
            System.out.println("field link="
                    + error.getClass().getSimpleName());
        }

        System.out.println("actual loaded class="
                + Vendor.class.getName());
    }
}
```

**For learning purposes only:** the two `catch` blocks are intentionally placed so the program continues after each error and demonstrates both errors independently. In real applications, linkage errors indicate an inconsistent dependency graph; you should fail fast and fix the artifacts rather than using `catch(Error)` to treat the state as normal.

### 5.5 Compile All Three Groups in the Correct Order

Using JDK 17+ from the `linkage-demo` directory:

```bash
javac --release 17 -d v1-classes v1-src/lib/Vendor.java
javac --release 17 -cp v1-classes -d client-classes client-src/app/Client.java
javac --release 17 -d v2-classes v2-src/lib/Vendor.java
```

The order matters:

1. Compiling v1 produces the class containing the API the client needs.
2. Compile the client **only against v1**. The constant pool of `app.Client` records references to the v1 API.
3. Compile v2 into a different output directory without touching the already generated `client-classes`.
4. Change the classpath only **at runtime**, without recompiling the client.

### 5.6 Run with v1: Matching Binaries

**Windows:**

```bash
java -cp "client-classes;v1-classes" app.Client
```

**Linux/macOS:**

```bash
java -cp "client-classes:v1-classes" app.Client
```

Stdout **verified with `javac --release 17` and the JVM**:

```text
method=v1 format
field=7
actual loaded class=lib.Vendor
```

The client and runtime are using the same v1 API, so both symbolic references resolve successfully.

### 5.7 Run the Old Client Against v2 Only: Reproducing the Errors

**Windows:**

```bash
java -cp "client-classes;v2-classes" app.Client
```

**Linux/macOS:**

```bash
java -cp "client-classes:v2-classes" app.Client
```

Stdout **verified**:

```text
method link=NoSuchMethodError
field link=NoSuchFieldError
actual loaded class=lib.Vendor
```

Interpretation:

- `NoSuchMethodError`: the caller still has a reference to `lib.Vendor.format:()Ljava/lang/String;`, but v2 does not define that member.
- `NoSuchFieldError`: the caller still has a reference to `lib.Vendor.LEVEL:I`, but v2 does not define that field.
- `actual loaded class=lib.Vendor`: the binary name is still the same, showing that **finding the class does not guarantee finding the required method/field**. This line **does not prove whether the v1 or v2 file was loaded**, because both have the same name — to see the exact source, you must check CodeSource/class-loading diagnostics.

It is precisely the difference between **succeeding with v1** and **getting both errors when substituting only the runtime with v2** that clarifies the root cause of **binary incompatibility**.

## 6. Using javap to Confirm Which Descriptor the Bytecode Requires

The `javap` tool allows reading the constant pool and bytecode of the **old client.class**:

```bash
javap -classpath client-classes -c -verbose app.Client
```

In the verified example output, the key sections include:

```text
Methodref ... // lib/Vendor.format:()Ljava/lang/String;
Fieldref  ... // lib/Vendor.LEVEL:I
invokestatic ... // Method lib/Vendor.format:()Ljava/lang/String;
getstatic    ... // Field lib/Vendor.LEVEL:I
```

`invokestatic` is emitted because the client compiled against a static method. `getstatic` is emitted because the client reads a static field that is **not a compile-time constant**. The entries in the constant pool explicitly record **owner/name/descriptor**.

Then inspect the **runtime version**:

```bash
javap -classpath v2-classes -public lib.Vendor
```

Version v2 has `REVISION` and `describe()`, without `format()`/`LEVEL`. On a production classpath, replace `v2-classes` with the path to the **JAR actually loaded by the JVM** (not just the dependency that the IDE displays).

### Why Not Just Look at the Source?

The current source may be a different version compared to:

- Class files compiled last week.
- Artifacts in `build/libs` or `target` of another module.
- JARs from the Maven/Gradle local cache or repository.
- JARs copied into the server `lib`, plugin folder, or Docker image.
- Classes shadowed by shading/relocation or a class loader.

**Diagnosing linkage requires looking at the caller bytecode and runtime binaries**, not just the source code currently open.

## 7. Which Runtime Version of a Class Does ClassLoader Choose?

The JVM resolves a class symbolic reference through **the defining loader of the caller class and the relevant class loading rules**, not by “searching all JARs and automatically choosing an API matching the method”.

On a standard application classpath, the same binary name appearing in two JARs can lead to a situation where **the earlier JAR or the loader policy determines which class is defined first**, causing the client to load an unexpected version. With custom loaders, **parent-first/child-first**, module mapping, code source, and class identity all have an effect.

Example:

```text
Client.class (compiled with Vendor v2 API)
         |
         v
Application loader
   |
   +-- old-v1.jar contains lib/Vendor.class
   +-- new-v2.jar contains lib/Vendor.class
         |
         v
JVM may load the version found first
         |
         v
NoSuchMethodError / NoSuchFieldError
```

**There is no automatic “if a method is missing, try another JAR” mechanism.** Once `lib.Vendor` has been defined by the corresponding loader, it has a fixed identity and members; the JVM does not pick a second file just because a symbolic reference to a method fails to resolve.

If different plugin loaders are used, the same name `lib.Vendor` can be defined by two independent **defining class loaders** into two separate runtime types. When the client and provider communicate through a shared API, a mismatch between class loaders can additionally cause `ClassCastException` or `LinkageError`/loader constraint violations, in addition to the versioning errors being examined.

### Printing the Code Source and Defining Loader

A debug snippet placed in code that actually sees `lib.Vendor`:

```java
Class<?> type = lib.Vendor.class;

System.out.println("name=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());

java.security.ProtectionDomain pd = type.getProtectionDomain();
java.security.CodeSource cs = (pd == null) ? null : pd.getCodeSource();

System.out.println("source="
        + (cs == null ? "<unknown>" : cs.getLocation()));
```

This is an **illustrative snippet inside a Java method**, with no fixed stdout because the loader/module/path varies by runtime. `CodeSource` can be `null` (especially for platform classes, custom loaders, or specific policies); you must not assume every class has a file URL.

The most important points to inspect are: **which loader defines the class, which module contains the class, which CodeSource it comes from, and which API descriptors the JAR/runtime artifact contains**.

### JVM Class Loading Logs

With HotSpot Java 17+:

```bash
java -Xlog:class+load=info -cp "client-classes;v2-classes" app.Client
```

This command illustrates Windows; on Linux/macOS, change `;` to `:`. The JVM logs class loading information; search for `lib.Vendor` in the log to find **the source from which the VM loaded it**, depending on format/version. In production, you should use controlled log output because `class+load=info` can generate many lines.

Another common option for inspecting class artifacts is the command:

```bash
jar --list --file path/to/vendor-api.jar
```

Verify the exact `lib/Vendor.class` and that there are no unwanted duplicate versions.

## 8. Not Just Renaming: Changing Return Type or Field Type Also Breaks the Binary API

A very realistic incident:

**V1:**

```java
package lib;
public class Settings {
    public String mode() { return "safe"; }
    public int timeout = 10;
}
```

**V2:**

```java
package lib;
public class Settings {
    public CharSequence mode() { return "safe"; }
    public long timeout = 10;
}
```

The two snippets are **two versions of the same `lib.Settings`**, not compiled simultaneously in the same source root. Source-level code such as:

```java
System.out.println(settings.mode());
System.out.println(settings.timeout);
```

may still look similar, but **the JVM references have changed**:

```text
V1 method: lib/Settings.mode:()Ljava/lang/String;
V2 method: lib/Settings.mode:()Ljava/lang/CharSequence;

V1 field:  lib/Settings.timeout:I
V2 field:  lib/Settings.timeout:J
```

For a client compiled against v1, simply replacing the runtime `Settings.class` with v2 **can** produce `NoSuchMethodError` and `NoSuchFieldError` when the old reference can no longer be found in the class hierarchy.

An exception to understand: the compiler may generate **bridge methods** in certain generics/covariant override scenarios to preserve method descriptors, and JVM resolution performs lookups in the hierarchy. Therefore, **do not draw definitive conclusions from a Java source diff**; you must inspect the actual bytecode using `javap -s -p` or `javap -verbose`.

## 9. Why Can the Error Appear Only When a Specific Code Path Runs?

The JVM distinguishes between loading, linking (verification/preparation/resolution), and initialization. Resolution of symbolic references may be performed by the JVM at different times in accordance with the specification, and many errors only become observable when **the specific reference is used**.

Example:

```java
if (featureEnabled) {
    lib.Vendor.format();
}
```

This is an illustrative snippet, assuming `featureEnabled` is defined and the client was compiled against an API containing `format()`.

- If the code path does not reach the method, the application may run for some time.
- When the missing reference is executed, a linkage error may occur.
- The JVM may resolve some references eagerly, but resolution errors must be observed according to the corresponding specification bounds; you should not rely on a single fixed timing across all JVM/JIT modes.

This is why integration tests that call only a very narrow happy path may **fail to detect a dependency mismatch**. Libraries still need to be tested across real features/entrypoints, including optional features deployed later.

**Do not confuse an error detected late with “a method disappearing on its own while the program is running”.** In the JVM, the caller bytecode still holds the old reference; it is only when resolution occurs that we observe the preexisting incompatibility.

## 10. Distinguishing from Other Classloading and Access Errors

| Error | Typical cause | How is it different from the two core errors? |
| --- | --- | --- |
| `ClassNotFoundException` | The loader was asked to find a binary class name but could not find it | Usually a checked exception from a lookup API such as `loadClass` |
| `NoClassDefFoundError` | The VM needs a class whose definition is unavailable or whose earlier initialization failed | The class/dependency is unavailable; not a “missing member” |
| `NoSuchMethodError` | A method symbolic reference fails to resolve | The owner class may have been loaded, but the method name+descriptor does not match |
| `NoSuchFieldError` | A field symbolic reference fails to resolve | The class may exist, but the field name+descriptor does not match |
| `IllegalAccessError` | The member/class exists, but runtime access checks do not permit access | The member has not necessarily disappeared |
| `IncompatibleClassChangeError` | A change in class/member kind, e.g., static ↔ instance mismatches expectations | The member with name+descriptor may still exist, but the opcode does not match |
| `AbstractMethodError` | Runtime invocation selects an abstract method / lacks a suitable concrete implementation in certain cases | Different from `NoSuchMethodError` at resolution time |
| `ClassCastException` | Runtime types are incompatible, potentially because two loaders defined the same binary name | Type identity/casting is different from field/method resolution |
| `VerifyError` | Class bytecode fails verification | A bytecode validity issue, not necessarily an API version issue |

You should not write a generic handler that catches `Throwable` and turns everything into a “Class not found” message: the owner class, method/field name, and descriptor in the stack trace are key to identifying the wrong dependency.

## 11. Common Real-World Causes of Version Mismatch

### 11.1 Transitive Dependency Conflict

An app depends on libraries A and B; A compiled against `vendor-core:2.x` while B pulls in `vendor-core:1.x`. Maven/Gradle dependency resolution may select one specific version according to build rules, and the chosen runtime artifact may **not match the version one of the dependencies was compiled against**.

```text
app
├── feature-a -> vendor-core v2
└── feature-b -> vendor-core v1
                     |
                     v
                runtime chooses 1 version
                     |
                     v
        the other branch's client binary may be incompatible
```

There is no universally valid rule that “picking the higher version fixes the error”: the v2 API might have removed v1 members, or the v1 library might not support the new runtime. You must choose a **compatible set of versions** and verify in practice.

### 11.2 Duplicated JAR on the Classpath/Server

`app/lib/vendor-v2.jar` and `server/lib/vendor-v1.jar` both contain `lib.Vendor`. The app classloader may delegate to its parent and receive the v1 class from the server before searching for v2 itself. The symptom looks like “I already added v2 to the app, yet it still fails”.

### 11.3 Shaded/Fat JAR Packaging an Old Version

The build tool creates an uber-JAR but merges classes/resources incorrectly, keeping an old `lib/Vendor.class` even though dependency metadata shows v2. You need to inspect the **final artifact that actually runs**, not just declared dependencies.

### 11.4 Unclean IDE/Build Cache or Incremental Build

One module recompiled v2, while another client module still uses old class files. The runtime picks up the new binary while the caller bytecode has not been recompiled, causing a mismatch. A clean rebuild needs to go together with inspecting the dependency graph; “clearing the cache” does not always fix a real dependency conflict.

### 11.5 Plugin/Shared Framework Version Skew

A plugin is compiled against host SDK v2, but the container runtime only exports shared API v1. Because the host parent loader defines the shared API, even if the plugin bundles the v2 JAR, it may still delegate to v1 and hit `NoSuchMethodError`.

### 11.6 Stale Deployment Artifacts

The server, Docker image, or classpath script is referencing an old JAR, while the developer is looking at a newer file on another machine. Inspecting `CodeSource` and the build artifact hash/version is necessary.

## 12. Ordered Debugging Workflow, Avoiding Guesswork Fixes

When a stack trace contains `NoSuchMethodError` or `NoSuchFieldError`, follow these steps:

**Step 1 — Record the exact error and caller frame.**

Hypothetical example:

```text
java.lang.NoSuchMethodError:
  'java.lang.String lib.Vendor.format()'
  at app.Client.main(Client.java:7)
```

From the message and frame, we know the **caller** is `app.Client`, the owner is `lib.Vendor`, and the expected method is `format()` returning `String`. A field error may similarly include the field name and expected type. Message formatting is **not fixed** across JVM versions, so do not hard-parse message strings as application logic.

**Step 2 — Find the class actually loaded at runtime.**

Print:

```java
System.out.println(lib.Vendor.class.getClassLoader());
System.out.println(lib.Vendor.class.getModule());
System.out.println(lib.Vendor.class.getProtectionDomain()
        .getCodeSource());
```

This illustrative snippet needs to handle null protection domain/code source cases in real usage; if the class under investigation cannot be loaded directly from source, use `-Xlog:class+load=info` or a debugger.

**Step 3 — Inspect the methods/fields present in the runtime class.**

```bash
javap -classpath path/to/runtime-vendor.jar -p -s lib.Vendor
```

For the JAR containing that exact class name, `javap` prints the descriptors rather than just pretty Java signatures.

**Step 4 — Check what the caller bytecode was compiled against.**

```bash
javap -classpath path/to/client.jar -verbose -c app.Client
```

Look for `Methodref`/`Fieldref` and the opcode. Compare **owner + name + descriptor** against the runtime API.

**Step 5 — Find the actual dependency version in the build.**

- Maven: `mvn dependency:tree`, inspect scoped/transitive/excluded versions.
- Gradle: `./gradlew dependencies --configuration runtimeClasspath`, or `dependencyInsight` for the suspected module (the Windows Gradle wrapper is `gradlew.bat`).
- If using a plugin/container: inspect both **host/server libs and plugin classpaths**, not just a single build file.

**Step 6 — Fix dependency constraints and artifacts.**

Choose an API version supported by **all caller binaries**. If the breaking API change is intentional, rebuild the consumers against the new version and update their code. Eliminate duplicate JAR/parent conflicts. If two versions are genuinely required, isolate them using classloaders/processes and share only a stable API.

**Step 7 — Clean build, redeploy, and re-run along the same runtime path.**

Do not merely reload the IDE. Deliberately remove old deployment artifacts, rebuild client modules if the API changed, verify container image/server library placement, and run integration tests covering the previously failing code paths.

### Minimum Log Checklist for Production Support

```text
Error type: NoSuchMethodError / NoSuchFieldError
Caller class and stack frame
Symbolic owner/name/descriptor
Defining loader of caller
Defining loader of owner
Module/layer if named modules used
Owner CodeSource / actual JAR
Classpath/module-path and deployment version
Actual method/field descriptors (javap)
Build dependency graph
```

This information is usually sufficient to distinguish among “runtime JAR is too old”, “runtime JAR is too new and removed the API”, “parent loader shadows the right version”, and “client.class has not been rebuilt”.

## 13. The Right Fixes and What Not to Do

| Approach | Assessment |
| --- | --- |
| Align compile-time and runtime dependency versions | **Recommended**, but verify actual binary compatibility |
| Rebuild the client when the dependency API changes | **Recommended**, especially for breaking changes |
| Remove duplicate JARs or configure an appropriate classloader policy | **Recommended**, based on verified CodeSource/loader |
| Use dependency management/constraints/locking | **Recommended** for reproducible builds |
| Add a compatibility overload/deprecated method keeping the old descriptor | **Helpful** when library authors need to preserve binary compatibility |
| Maintain an adapter/bridge at the API boundary | **Possible**, if the version contract is clearly designed |
| Catch and ignore `NoSuchMethodError` | **Not recommended** in normal business logic |
| Simply append the v2 JAR at the end of the classpath when v1 is already loaded by the parent | **Insufficient**; the loader may still pick v1 |
| Change TCCL and assume `Class.forName(String)`/bytecode linkage will all use the new loader | **Incorrect**; loader selection differs across APIs |
| Call `System.gc()`/`URLClassLoader.close()` to “make the new method appear” | **Incorrect**; an already defined loader/class does not automatically swap its API |
| Blindly clear all caches | **Not recommended**; identify the source of the conflict and fix it |
| Rely on uncontrolled classpath ordering | **Risky**; prefer a single controlled and verified version |

If you publish a library:

- Keep public methods/fields that consumers already use, or provide a **binary-compatible bridge/overload** whenever possible.
- When changing parameter/return/field types, evaluate the impact on *bytecode descriptors*, not just Java source compilation.
- Follow a clear versioning policy, and announce breaking changes and runtime requirements.
- Test by running **binaries compiled against the previous version** against the new version to catch linkage errors.
- Distinguish **source compatibility** from **binary compatibility**: some changes allow source recompilation to succeed while breaking old binaries, and vice versa.
- Do not accidentally drop a public no-arg constructor that callers have already compiled against.

## 14. Advanced Scenarios: Method Signatures and Field Constants

### 14.1 Adding a New Overload Usually Does Not Break Old Binaries

If v1 has:

```java
public String convert(int value)
```

and v2 keeps that method and **adds**:

```java
public String convert(long value)
```

then the old symbolic reference `convert:(I)Ljava/lang/String;` can still resolve normally. “Adding an overload” is fundamentally different from “changing the parameter of an existing method”.

If you completely replace the v1 method with an overload taking `long` and remove the `int` version, the old client does not automatically switch descriptors; `NoSuchMethodError` can occur.

### 14.2 Changing an Instance Method to Static: Not Necessarily NoSuchMethodError

If the v1 client has `invokevirtual` targeting an instance method, and runtime v2 has the same name/descriptor but the method became static: the typical error is **`IncompatibleClassChangeError`** because the opcode requires an instance method while the runtime member is static. You should inspect the `invokevirtual` / `invokestatic` opcode and the error message rather than forcing every linkage failure to be treated as a missing method.

### 14.3 Changing a Static Field to Instance: Not Necessarily NoSuchFieldError

If the v1 client has `getstatic` while the new runtime field is an instance field, the JVM may throw **`IncompatibleClassChangeError`**. If the field also changed its data type, `NoSuchFieldError` may occur earlier during lookup. The order depends on the reference and the actual kind of change.

### 14.4 Compile-Time Constants Can Cause Silent “Stale Value Bugs”

V1:

```java
public static final int BUILD_ID = 101;
```

v2:

```java
public static final int BUILD_ID = 202;
```

A client compiled against v1 typically embeds the literal `101` due to constant inlining. When running against v2, the client may **still print 101 without throwing `NoSuchFieldError`**. You need to recompile the consumer to update the value, or avoid relying on public constant variables when the value is expected to change at runtime.

For a `static final` object that is not a compile-time constant (for example, a `List` or an expression that is not a constant expression), the client may still emit a field reference and be subject to normal linkage rules.

### 14.5 Generics, Erasure, and Bridge Methods

A generic Java method:

```java
public java.util.List<String> items()
```

typically has the erased JVM return descriptor `()Ljava/util/List;` (generic metadata is additionally stored via the Signature attribute). Changing the generic argument from `String` to `Object` may not change the **erased descriptor** and therefore might not throw `NoSuchMethodError`, even though type-safety/behavior issues may arise.

Changing the raw return type, parameter erasure, or bridge methods, on the other hand, can affect descriptors. When suspecting a mismatch, **`javap -s -p` is the accurate source of truth**, rather than inferring from angle brackets in source code.

## 15. Considerations When Implementing Plugins and Custom ClassLoaders

In a plugin architecture, the host may already have loaded an older SDK/API version via the **parent loader**. Even if the plugin JAR bundles the newer SDK, a child loader using **parent-first delegation** may obtain the API class from the host. When plugin code compiled against the newer API calls a method missing from the older API, it throws `NoSuchMethodError`.

```text
Host/System loader: api.Shared v1
       ^
       | parent-first
Plugin loader:
   - plugin.Entry compiled against api.Shared v2
   - plugin.jar may contain api.Shared v2
       |
       v
At runtime, plugin.Entry calls api.Shared.newMethod()
       |
       v
api.Shared v1 defined by parent -> NoSuchMethodError
```

How to handle it:

1. **Define a host-plugin API compatibility matrix.** Plugins must declare a minimum host API version and be checked before loading.
2. **Keep the shared API in a common loader** so the host and plugins use the same runtime types. Do not arbitrarily apply “child-first for `api.*` as well”, as that can create duplicate API classes causing `ClassCastException`/loader constraints.
3. **Isolate implementation dependencies** when they are not part of the shared contract, preventing the parent from shadowing the version the plugin needs.
4. **Fail fast at bootstrap:** check versions/required capabilities upfront instead of waiting for a specific method to be called hours later.
5. **Do not hot-replace a JAR underneath a live loader** and expect class definitions and method tables to update accordingly. Use a new deployment/loader with a proper lifecycle if reloading is needed.
6. **If using JPMS**, check the module graph and exports/opens in addition to class loading. An `IllegalAccessError` may be caused by module access restrictions rather than a version mismatch.
7. **Print the class loader of the owner class**, not just that of the plugin entrypoint: the same plugin thread can still call an API defined by the parent.

Another scenario: a ServiceLoader provider is loaded via the right plugin TCCL, yet it calls a host API that is missing a method. **Successful service discovery does not guarantee that the provider is binary-compatible** with the host class definitions. Integration contract tests must be run.

## 16. Diagnosing with Dependency Graphs and Artifact Consistency

Before fixing, reconstruct the path from the client binary to the runtime class:

```text
Client.class
    |
    | constant_pool Methodref/Fieldref
    v
Required Owner + Name + Descriptor
    |
    | JVM class resolution
    v
Actual Class<?> (defining loader, module, CodeSource)
    |
    | field/method resolution
    v
Runtime available members
    |
    +-- exact match -----------> OK (if access/opcode are valid)
    |
    +-- missing match ---------> NoSuchMethodError / NoSuchFieldError
    |
    +-- access mismatch -------> IllegalAccessError
    |
    +-- static mismatch -------> IncompatibleClassChangeError
```

Once the **exact runtime JAR** is identified, compare its manifest/version/checksum against the build manifest. Do not compare filenames alone: two artifacts can share the name `vendor.jar` while having different bytecode, and a “version 2.1” artifact may have been repackaged/shaded or still contain old classes.

**Build reproducibility**:

- Manage dependency versions centrally and lock released versions.
- Do not use wildcards/uncontrolled directories when servers/plugins require specific APIs.
- In CI, check for dependency conflicts and run tests with the **exact same artifacts/JRE/runtime classpath** as production.
- For libraries publishing an API, consider tools that compare binary APIs across releases and run old-client-binary compatibility tests.
- Ensure that container/server restarts or redeploys cause the runtime to use the new artifacts, avoiding stale classloaders persisting under another plugin deployment.

## 17. Self-Check with Answers

**Question 1.** A client uses `Vendor.format()`, compiled against v1; at runtime, `Vendor` v2 is loaded without that method. Why did the code compile successfully?

**Answer:** `javac` only saw the v1 API at compile time; the runtime v2 class definition is different. The JVM links the old symbolic method reference and cannot find the name+descriptor, resulting in `NoSuchMethodError`.

**Question 2.** Is `NoSuchMethodException` the same as `NoSuchMethodError`?

**Answer:** No. `NoSuchMethodException` is a checked reflection exception; `NoSuchMethodError` is a `LinkageError` thrown when a bytecode symbolic method reference fails to resolve.

**Question 3.** If the runtime `Vendor` still has `format()` but returns `Object` instead of `String`, is it guaranteed not to fail?

**Answer:** No. A JVM method descriptor includes the return type; a client expecting `()Ljava/lang/String;` when runtime only has `()Ljava/lang/Object;` can trigger `NoSuchMethodError`, except under specific compatible inheritance/bridge conditions.

**Question 4.** Why can changing `int LEVEL` to `long LEVEL` throw `NoSuchFieldError`?

**Answer:** A field reference includes name + type descriptor; `LEVEL:I` is different from `LEVEL:J`.

**Question 5.** If an instance field is changed to a static field with the same name/type, what error can occur?

**Answer:** `IncompatibleClassChangeError` due to an incompatible `getfield`/`getstatic` opcode, not necessarily `NoSuchFieldError`.

**Question 6.** Why can the error persist even after adding the new JAR to the classpath?

**Answer:** Parent-first delegation, classpath precedence, server-provided libraries, or duplicate JARs may still cause the runtime to load the old version. Print the defining loader, module, and CodeSource of the actual class.

**Question 7.** How can you verify which method descriptor client.class references?

**Answer:** `javap -classpath client-classes -verbose -c app.Client`, and inspect `Methodref`/`Fieldref` and the opcode.

**Question 8.** Why does changing the value of a public `static final int` sometimes not throw an error, while the client still sees the old value?

**Answer:** `javac` may inline the constant into the client bytecode; there is no longer a field lookup at that usage site. Recompile the client or change the API design if the value needs to update dynamically.

**Question 9.** Does `NoSuchFieldError` prove that the entire class is missing?

**Answer:** No. The owner class may have loaded successfully, but the field name+descriptor is absent in the runtime hierarchy. If the class itself is missing, the error is typically different, such as `ClassNotFoundException`/`NoClassDefFoundError` depending on context.

**Question 10.** A plugin is compiled against SDK v2, while the host only provides SDK v1. Will changing the TCCL definitely fix the error?

**Answer:** No. The TCCL only affects APIs that actively use it; if the API class was already defined by the parent from v1, changing the TCCL does not automatically alter its metadata/method table. Version compatibility or a different classloader architecture is needed.

**Question 11.** Why does the error only appear when a rarely used feature is enabled?

**Answer:** Symbolic references along that code path may only be resolved at execution time; startup tests do not necessarily touch the mismatched member. Integration tests for key features are needed.

**Question 12.** What is the thorough fix?

**Answer:** Identify the exact binary client expectations and actual runtime API; align/ensure binary-compatible library versions, rebuild callers when breaking APIs change, eliminate duplicate/classloader conflicts, package and redeploy the right artifacts, and run end-to-end tests.

## 18. Quick Pre-Deployment Checklist

1. **Preserve the full stack trace** and identify the missing owner/member/descriptor.
2. **Record the exact version of the client artifact** that was compiled and deployed.
3. **Use `javap`** to inspect symbolic method/field references in the caller class.
4. **Identify the actual runtime class** using class-loading logs, CodeSource, and the defining loader.
5. **Read runtime descriptors** using `javap -p -s`.
6. **Check for duplicate classes/JARs** on the classpath, module path, and server directories.
7. **Inspect the dependency graph** for both compileClasspath and runtimeClasspath (Maven/Gradle).
8. **Review the plugin/host parent-first policy** if the library runs inside a container.
9. **Fix binary compatibility**, not just the source API as viewed in the IDE.
10. **Rebuild/clean deploy** all affected caller modules if method/field descriptors changed.
11. **Test against the real runtime**: old client binaries against the new library, as well as rare code paths.
12. **Manage versioning and API evolution**: avoid removing or modifying public members without a migration plan.
13. **Do not rely on `System.gc()`/`URLClassLoader.close()`** to fix a linkage mismatch in an already defined class.
14. **Distinguish error types**: `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError`, `IncompatibleClassChangeError`, and `NoClassDefFoundError` have different root causes.

## Conclusion

**`NoSuchMethodError` and `NoSuchFieldError` usually indicate that the caller bytecode and the runtime class definitions do not share the same binary API**. The JVM does not look up methods/fields by approximate names or recompile the client automatically; it resolves **symbolic owner + member name + descriptor** according to the classloader and JVMS rules. Changing the name, parameters, return type, or field type can prevent old binaries from linking, even when the owner class itself loads successfully.

The reliable fix: **find the class actually loaded → compare `javap` client/runtime descriptors → resolve dependency version/loader conflicts → rebuild and deploy compatible artifacts → run tests against the real runtime artifacts**. This addresses the root cause rather than masking `Error` with a catch block or adding JARs at random.

**Java SE 17 Reference Documentation:**

- [JVMS 17 `5.1` – Runtime Constant Pool](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.1): symbolic references for classes, methods, and fields.
- [JVMS 17 `5.4.3.2` – Field Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.2): field name+descriptor, `NoSuchFieldError`, and access/link checks.
- [JVMS 17 `5.4.3.3` – Method Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.3): method lookup and `NoSuchMethodError`.
- [JLS 17 Chapter 13 – Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): source/binary changes that preserve or break compatibility.
- [`NoSuchMethodError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html) and [`NoSuchFieldError` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchFieldError.html).
- [`ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): defining loader and delegation.
