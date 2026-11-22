# NoSuchMethodError, NoSuchFieldError, and mismatched dependencies

During **Java Advance Compatibility Migration**, a frustrating situation is an application that still compiles successfully yet when run on a new JDK reports:

```text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String com.example.codec.JsonWriter.write(java.lang.Object)'
```

Or:

```text
java.lang.NoSuchFieldError: DEFAULT_TIMEOUT
```

These two errors are usually signs that **the running bytecode cannot find a method or field matching the reference that the caller's bytecode was compiled to call**. Common causes are that a library used at compile time has a different API from the version actually loaded at runtime: direct and transitive versions are out of sync, an old JAR remains in the WAR, a shaded artifact is packaged incorrectly, the application server provides a different version, or a class is loaded by an unexpected classloader.

Key takeaway: **`NoSuchMethodError` and `NoSuchFieldError` are runtime linkage errors, not another name for compile errors**. You should not solve them by randomly switching JDKs, clearing caches and retrying, or forcing a dependency version without first identifying the exact class loaded, the binary signature requested by the caller, and the API the runtime class actually provides.

This lesson presents how to read stack traces and JVM linkage, reproduce the error using two JAR versions, use `javap` to inspect binary descriptors, find duplicate classes in Maven/Gradle/WAR/fat JARs, distinguish related error families, handle adapter/framework/JDK migrations, build a production diagnostic workflow, and set up CI gates to prevent recurrence.

> **Scope:** Package, group/artifact, and version examples in this article are created for illustration; they do not represent an actual dependency. Maven/Gradle and JVM commands should be adjusted for the build tool version, JDK, operating system, and project structure in use.

## 1. Which group do these two errors belong to?

### 1.1. LinkageError occurs after the compilation phase

The Java compiler compiles source based on the **API it sees on the compile classpath/module path**. The generated `.class` file stores symbolic references to classes, methods, and fields, rather than hardcoding memory addresses of every method.

At runtime, the JVM loads classes and resolves those references according to the rules of the Java Virtual Machine Specification. If the target class does not provide the method/field requested by the caller, the linkage process can throw an error from the `LinkageError` family.

Diagram:

```text
              Compile time                         Runtime
          ------------------                  ------------------
          application source
                 |
                 v
         library-api-v1.jar
          method greet(String)
                 |
                 v
           javac -> App.class
                 |                          App.class
                 |                              |
                 +------------------------------+
                                                |
                                                v
                                        class loader selects
                                        library-api-v2.jar
                                        only has greet(Object)
                                                |
                                                v
                                         NoSuchMethodError
```

In this example, the application source did not change. The difference lies in the **library's ABI at runtime**.

### 1.2. Position in the Throwable hierarchy

```text
java.lang.Throwable
  |
  +-- java.lang.Error
        |
        +-- java.lang.LinkageError
              |
              +-- IncompatibleClassChangeError
              |     |
              |     +-- NoSuchMethodError
              |     +-- NoSuchFieldError
              |     +-- AbstractMethodError
              |     +-- IllegalAccessError
              |     +-- ...
              |
              +-- NoClassDefFoundError
              +-- UnsupportedClassVersionError
              +-- ...
```

The diagram illustrates several common branches and does not list every subclass. Both `NoSuchMethodError` and `NoSuchFieldError` are `Error`s, not checked exceptions.

Because these are typically binary incompatibility or deployment errors, the primary remediation is **fixing the dependency/classloading/build artifact**, rather than wrapping every call in `try/catch (Error)` and continuing execution.

### 1.3. Why can the error appear only when hitting an endpoint?

Resolution of symbolic references can happen at different times depending on JVM/linking and execution paths. A service can start up successfully and return normal healthchecks, yet on the first visit to an export feature it calls a method that no longer exists:

```text
Startup                     -> success
Healthcheck                 -> success
Login                       -> success
Export report               -> NoSuchMethodError
```

A startup smoke test must not be taken as proof that the entire binary graph is valid. Tests must exercise real feature branches, especially after replacing frameworks, serialization, ORM, logging, or HTTP libraries.

## 2. What does NoSuchMethodError mean precisely?

### 2.1. The JVM looks up methods by binary reference

When caller bytecode requests a method, the reference involved is not merely a simple name. It also carries a descriptor describing parameter types and return type; the reference kind and invocation opcode also matter.

Source example:

```java
package demo.lib;

public final class Greeter {
    public String greet(String name) {
        return "Hello " + name;
    }
}
```

Descriptor of the method:

```text
greet(Ljava/lang/String;)Ljava/lang/String;
```

Meaning:

- Method name: `greet`.
- One parameter of type `java.lang.String`.
- Returns `java.lang.String`.

If the JAR at runtime only has `greet(Object)`, that is **not** the method with the descriptor the caller demands.

### 2.2. Changing a parameter is a binary break

Library v1:

```java
public String greet(String name) {
    return "Hello " + name;
}
```

Library v2:

```java
public String greet(CharSequence name) {
    return "Hello " + name;
}
```

With recompiled source code, the Java compiler can accept a call passing a `String` to a method taking `CharSequence`. However, the old `App.class` still references descriptor `(Ljava/lang/String;)Ljava/lang/String;`. If library v2 does not retain the old method, the runtime can report `NoSuchMethodError`.

**Source compatibility after recompilation does not imply binary compatibility for existing artifacts.**

### 2.3. Changing the return type can also break binary compatibility

In Java source, return types alone cannot be used to overload two methods with the same name and parameters. In a JVM method descriptor, however, **the return type is part of the descriptor**.

For example, a library changes:

```java
public String normalize(String input);
```

to:

```java
public CharSequence normalize(String input);
```

The old caller requests:

```text
normalize(Ljava/lang/String;)Ljava/lang/String;
```

But the runtime only has:

```text
normalize(Ljava/lang/String;)Ljava/lang/CharSequence;
```

A recompile can update the reference; old bytecode cannot. In cases of overriding with a covariant return, the Java compiler may generate a **bridge method** to preserve corresponding dispatch relationships, yet one must not assume every return-type change produces a bridge that preserves ABI.

### 2.4. Constructors can also cause NoSuchMethodError

In bytecode, constructors use the special name `<init>`. For example:

```java
public Client(String endpoint, int timeout);
```

is referenced by descriptor:

```text
<init>(Ljava/lang/String;I)V
```

If the new version only has a constructor taking `Duration` instead of `int`, the old caller can fail when executing `new Client(...)`.

The JVM message usually shows the constructor signature, though the exact error formatting depends on the runtime version.

### 2.5. Overloading, autoboxing, and varargs do not auto-patch ABI

The compiler can select a different overload when source is recompiled. Already-built bytecode, however, stores the exact call.

For example:

```java
// v1
void send(Integer count);

// v2
void send(int count);
```

Two different descriptors:

```text
(Ljava/lang/Integer;)V
(I)V
```

Autoboxing is a compiler capability at the source level, not an arbitrary method-descriptor substitution when the JVM resolves old bytecode.

## 3. What does NoSuchFieldError mean precisely?

### 3.1. A field reference consists of name and field descriptor

Library v1 example:

```java
package demo.lib;

public final class RetryPolicy {
    public static int DEFAULT_RETRIES = 3;
}
```

Caller:

```java
int retries = RetryPolicy.DEFAULT_RETRIES;
```

Bytecode may contain a `getstatic` reference to field:

```text
demo/lib/RetryPolicy.DEFAULT_RETRIES:I
```

`I` is the descriptor for `int`.

If library v2 changes the field to:

```java
public static long DEFAULT_RETRIES = 3L;
```

then the runtime field has descriptor `J` (long), so there is no longer a field with the exact name and type `I` requested by caller bytecode. The result can be `NoSuchFieldError`.

### 3.2. Changes that create risk

- Removing a public/protected field referenced by callers.
- Renaming a field.
- Changing field type from `int` to `long`, `String` to another type.
- Moving a field to a class without the same resolution behavior.
- Changing library version so the runtime class lacks the field expected by callers.
- A bytecode enhancer or shaded library introducing a different class definition.

Do not conclude merely by looking at the field name. **The field descriptor must match the binary reference.**

### 3.3. Static/instance mismatches must be distinguished

If a field keeps the same name and type but changes from static to instance, or vice versa, an `IncompatibleClassChangeError` related to field access semantics may appear instead of a plain `NoSuchFieldError`.

Similarly, changing a method from instance to static can make `invokevirtual` and `invokestatic` incompatible. Therefore, inspect **both the field/method descriptor and bytecode opcode**, rather than assuming every ABI discrepancy throws the exact same error.

### 3.4. Compile-time constants are often inlined

A diagnostic trap:

```java
public static final int MAX_ATTEMPTS = 3;
```

If this is a **constant variable** per the Java Language Specification, the compiler can embed the value `3` directly into the caller's bytecode. At runtime, the caller does not necessarily still access the field via `getstatic`.

Consequences:

- Removing or changing the field value does not necessarily cause `NoSuchFieldError` for already-compiled callers.
- Old callers may still use the **old inlined value**.
- Recompiling the caller will read the new value during compilation, changing behavior.
- Do not rely on “no NoSuchFieldError” to conclude ABI/data semantics are right.

Example of a field that is not a compile-time constant:

```java
public static final Integer MAX_ATTEMPTS =
    Integer.valueOf(3);
```

This reference field usually requires runtime access; removing or changing the type of such fields is more likely to surface. For enum constants, linkage and serialization rules differ from ordinary primitive/String constant fields.

### 3.5. Changing a field accessor into a method is not binary-compatible

If v1 exposes:

```java
public static int DEFAULT_TIMEOUT = 30;
```

and v2 only keeps:

```java
public static int defaultTimeout() {
    return 30;
}
```

caller source must change from `Config.DEFAULT_TIMEOUT` to `Config.defaultTimeout()`. Old caller bytecode still looks for the field; the new method does not automatically satisfy a field reference.

When designing long-lived public APIs, it is usually advisable to avoid exposing mutable fields so implementations can be changed while keeping a stable method contract.

## 4. Demonstrating how to reproduce NoSuchMethodError with two JARs

### 4.1. Demo structure

```text
demo/
  lib-v1/
    demo/lib/Greeter.java
  lib-v2/
    demo/lib/Greeter.java
  app/
    demo/app/Main.java
```

File v1:

```java
package demo.lib;

public final class Greeter {
    public String greet(String name) {
        return "v1: " + name;
    }
}
```

File v2:

```java
package demo.lib;

public final class Greeter {
    public String greet(CharSequence name) {
        return "v2: " + name;
    }
}
```

Caller:

```java
package demo.app;

import demo.lib.Greeter;

public final class Main {
    public static void main(String[] args) {
        System.out.println(
            new Greeter().greet("Java")
        );
    }
}
```

### 4.2. Compiling the caller against v1

An illustrative command sequence for a Unix-like shell:

```shell
mkdir -p build/lib-v1 build/lib-v2 build/app

javac -d build/lib-v1 \
  lib-v1/demo/lib/Greeter.java

jar --create --file build/lib-v1.jar \
  -C build/lib-v1 .

javac -cp build/lib-v1.jar \
  -d build/app app/demo/app/Main.java
```

With a JDK providing `jar --create`, the commands generate JAR v1 and compile the caller against API v1. You do not need to re-run these commands if a real project already has a build tool; this is a model to understand the mechanism.

### 4.3. Running with JAR v1

```shell
java -cp "build/app:build/lib-v1.jar" demo.app.Main
```

Expected output:

```text
v1: Java
```

### 4.4. Compiling library v2 without recompiling the caller

```shell
javac -d build/lib-v2 \
  lib-v2/demo/lib/Greeter.java

jar --create --file build/lib-v2.jar \
  -C build/lib-v2 .
```

Then use `Main.class` compiled in the v1 step while swapping the runtime JAR:

```shell
java -cp "build/app:build/lib-v2.jar" demo.app.Main
```

The runtime may report an error like:

```text
java.lang.NoSuchMethodError:
  'java.lang.String demo.lib.Greeter.greet(java.lang.String)'
```

Stack trace formatting may vary by JDK. The cause is that class `Main` still contains a `Methodref` to `greet(String):String`, whereas runtime `Greeter` only has `greet(CharSequence):String`.

### 4.5. Why can recompiling the caller clear the error?

If `Main.java` is rebuilt with v2, the compiler will pick the new method matching the source. That proves **source can adapt**, not that binary compatibility is preserved for all un-recompiled callers.

If a public library has many external consumers, you cannot rely on every consumer immediately rebuilding to eliminate the error.

## 5. Demonstrating how to reproduce NoSuchFieldError

V1:

```java
package demo.lib;

public final class Limits {
    public static int MAX_PENDING = 100;
}
```

Caller v1:

```java
package demo.app;

import demo.lib.Limits;

public final class Main {
    public static void main(String[] args) {
        System.out.println(Limits.MAX_PENDING);
    }
}
```

V2:

```java
package demo.lib;

public final class Limits {
    public static long MAX_PENDING = 100L;
}
```

If JAR v1 is simply replaced by v2 while keeping the old `Main.class`, the runtime may report `NoSuchFieldError: MAX_PENDING`. The caller was compiled to read field descriptor `I`, whereas v2 only has `J`.

Do not use `static final int` with a compile-time constant to demonstrate this case: the value may be inlined and hide the runtime field-read behavior.

## 6. Diagnostic methodology: three mandatory questions

When encountering either error, determine in turn:

1. **Who is the caller?** Which class/method in the stack trace was compiled to call which symbol?
2. **Where did the JVM load the implementation from?** What is the actual JAR path, module, classloader, or deployment layer?
3. **Which symbol does the runtime class actually expose?** Are the descriptor, access modifier, and method/field kind right?

Decision diagram:

```text
NoSuchMethodError / NoSuchFieldError
               |
               v
        Read full stack trace
               |
               v
      Identify caller + symbol
               |
               v
        Find where the JVM
       actually loaded the class from
               |
               v
        javap caller + callee
               |
        +------+-------+
        |              |
        v              v
    Different ABI  ABI looks right
        |              |
        v              v
  Fix dependency   Check classloader,
  or keep ABI      method kind, module,
                   generated/shaded classes
               |
               v
    Test the exact packaged artifact
               |
               v
      Pin graph + CI guard
```

Do not skip inspecting the runtime class. A file sitting in a repository or build cache is not guaranteed to be the file the target JVM loaded.

## 7. Reading stack traces properly

### 7.1. Identifying the symbol and first useful frame

For example:

```text
Exception in thread "main" java.lang.NoSuchMethodError:
  'com.example.json.JsonNode
   com.example.json.JsonMapper.parse(java.lang.String)'
    at com.example.order.JsonAdapter.decode(JsonAdapter.java:48)
    at com.example.order.OrderService.load(OrderService.java:105)
    at com.example.order.Main.main(Main.java:18)
```

There are two classes to distinguish:

- `com.example.json.JsonMapper` is the **callee class** in which the JVM searches for the method.
- `com.example.order.JsonAdapter` is the **caller** whose bytecode generated the call missing the method.

Line `JsonAdapter.java:48` is where investigation should start. The bug is not necessarily in that source line; the runtime dependency may differ from what was used at build time.

### 7.2. Wrapper exceptions can hide LinkageError

In frameworks, the error can sit deep underneath:

```text
BeanCreationException
  caused by: InvocationTargetException
    caused by: NoSuchMethodError
```

Read the entire cause chain and extract the **root linkage error**. Errors such as `IllegalStateException` or initialization failures are merely wrappers.

### 7.3. Recording the environment when the error occurs

At a minimum:

```text
Service:
Source commit:
Artifact checksum:
JDK vendor/full version:
Framework version:
Runtime module/classpath:
Container image digest:
First failing request/job:
Caller class:
Missing symbol:
Loaded JAR location:
Classloader:
```

Do not record secrets, tokens, passwords, or sensitive user data in diagnostic records.

## 8. Using javap to inspect actual methods and fields

### 8.1. Viewing public APIs and descriptors

```shell
javap -classpath path/to/lib-v1.jar \
  -p -s demo.lib.Greeter
```

`-p` displays non-public members as well; `-s` prints internal descriptors.

Illustrative output:

```text
public java.lang.String greet(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
```

Try with JAR v2:

```shell
javap -classpath path/to/lib-v2.jar \
  -p -s demo.lib.Greeter
```

If only this remains:

```text
public java.lang.String greet(java.lang.CharSequence);
  descriptor: (Ljava/lang/CharSequence;)Ljava/lang/String;
```

a direct mismatch has been found.

### 8.2. Viewing caller bytecode

```shell
javap -classpath "path/to/app.jar:path/to/lib-v1.jar" \
  -c -v demo.app.Main
```

Look for:

- `Methodref` or `InterfaceMethodref` in the constant pool.
- The descriptor the caller actually demands.
- Opcode `invokevirtual`, `invokeinterface`, `invokestatic`, or `invokespecial`.
- Class/interface containing the symbol.

For fields, look for `Fieldref` and opcodes `getstatic`, `putstatic`, `getfield`, `putfield`.

These parts help distinguish the symbol **actually used by bytecode** from current source code (source in checkout may have changed after building the failing artifact).

### 8.3. Common descriptor table

| Java type | JVM descriptor |
|---|---|
| `void` | `V` |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `Object` | `Ljava/lang/Object;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

For example:

```text
Java:       long sum(int a, long b)
Descriptor: (IJ)J

Java:       void setNames(String[] names)
Descriptor: ([Ljava/lang/String;)V
```

`javap -s` is useful when method overloading, return types, arrays, or generic types make source-level messages easy to misinterpret.

### 8.4. Generics and type erasure

For example, `List<String>` and `List<Integer>` both have the erased JVM type `java.util.List`. Do not assume differing generic arguments necessarily produce a new method descriptor.

Conversely, changing an erased parameter type from `List` to `Collection` can change the descriptor and break ABI.

Use `javap -v` to inspect the `Signature` attribute, bridge methods, and descriptors; **JVM linkage relies on descriptors and corresponding VM rules**, not simply on source-form Java generic signatures.

## 9. Identifying the JAR actually loaded by the JVM

### 9.1. JVM class loading logs on JDK 9+

On HotSpot/JDK JVMs with unified logging:

```shell
java -Xlog:class+load=info \
  -cp "app.jar:lib/*" \
  com.example.Main
```

Logs can show which class was loaded and its source file or module. Depending on JDK and logger, exact details vary.

In production, class loading logs can be very large. Enable selectively or on staging with suitable traffic, log rotation, and internal data handling.

### 9.2. JDK 8 and verbose class loading

A traditional diagnostic approach:

```shell
java -verbose:class \
  -cp "app.jar:lib/*" \
  com.example.Main
```

This can also be used on some newer JDKs, though output formatting is not guaranteed to be identical. Do not write parsers overly coupled to log formats across JDKs.

### 9.3. Obtaining the class CodeSource when possible

In a sufficiently trusted environment, you can log:

```java
import java.net.URL;
import java.security.CodeSource;

public final class ClassOrigin {
    public static String locationOf(Class<?> type) {
        if (type.getProtectionDomain() == null) {
            return "<no protection domain>";
        }

        CodeSource source =
            type.getProtectionDomain().getCodeSource();

        if (source == null) {
            return "<no code source>";
        }

        URL location = source.getLocation();

        return location == null
            ? "<unknown location>"
            : location.toExternalForm();
    }
}
```

Example call:

```java
System.out.println(
    ClassOrigin.locationOf(demo.lib.Greeter.class));
```

Not every class has a `CodeSource`; classes from the bootstrap loader, generated classes, or custom loaders may return null or incomplete locations. For containers/fat JARs, the URL may also represent a nested archive. This is a signal, not the sole source of truth.

### 9.4. Listing duplicate resources

On the classpath:

```java
import java.net.URL;
import java.util.Enumeration;

Enumeration<URL> found =
    Thread.currentThread()
        .getContextClassLoader()
        .getResources("demo/lib/Greeter.class");

while (found.hasMoreElements()) {
    System.out.println(found.nextElement());
}
```

If multiple different locations supply `Greeter.class`, this is a sign of duplicate classes. However, the context classloader may differ from the loader that actually loaded the callee, and JPMS/custom loading does not necessarily behave like a plain classpath. Cross-check with `Greeter.class.getClassLoader()` and class-loading logs.

### 9.5. Caution when printing classpaths in production

Classpaths may contain internal paths, usernames, or mount paths. If application secrets sit in JVM flags/system properties, do not output the entire command line to unauthorized parties. Redact before sharing logs with vendors or public venues.

## 10. Inspecting JARs, WARs, EARs, and the final artifact

### 10.1. Regular JAR

List contents:

```shell
jar --list --file path/to/library.jar
```

Look up the target class, manifest, and version. Run `javap` directly on that JAR copy, rather than guessing from a copy in the local Maven/Gradle cache.

### 10.2. Executable/fat JARs with nested dependencies

Some frameworks package:

```text
application.jar
  BOOT-INF/classes/...
  BOOT-INF/lib/json-core-a.jar
  BOOT-INF/lib/json-core-b.jar
  META-INF/...
```

Class loading does not necessarily use a flat classpath like the IDE. If the fat JAR contains an old version of `json-core`, changing the dependency in `pom.xml` without rebuilding the artifact will not fix runtime.

Inspect `BOOT-INF/lib` or the framework's corresponding layout, identifying the exact nested JAR and checksum.

### 10.3. WAR/EAR and application servers

A server may provide JARs in:

```text
server/lib/
deployment/WEB-INF/lib/
deployment/WEB-INF/classes/
shared modules/
```

Parent-first/child-first classloader policy, server modules, and deployment isolation determine which class gets selected. The same WAR file may run on an embedded server yet fail on an external server because container-provided libraries differ.

Check the classloading policy of the exact server/version, rather than assuming every server prioritizes application JARs.

### 10.4. Shading and relocation

A shading plugin can:

- Rename class packages while missing metadata/service files.
- Put two versions of the same class into the fat JAR.
- Strip methods when minimizing.
- Leave compiled callers referencing old symbols.
- Package a module of an unexpected version.

You must inspect the **post-shading artifact**. A clean dependency tree before packaging does not guarantee the classes inside the final JAR are clean.

### 10.5. Multi-release JAR

An MR-JAR may contain:

```text
com/example/Codec.class
META-INF/versions/17/com/example/Codec.class
META-INF/versions/21/com/example/Codec.class
```

A newer JVM can load the appropriate versioned class when the `Multi-Release: true` manifest entry is used properly. If you only inspect the base class or a random entry, you may miss the actual API selected by the runtime.

For MR-JARs, cross-check the runtime JDK version, manifest, class variants, and tooling supporting `--multi-release` during analysis. Do not collapse all entries into a single ABI without version context.

## 11. Maven: finding dependency mediation and the selected version

### 11.1. Dependency tree

```shell
./mvnw dependency:tree
```

In multi-module:

```shell
./mvnw -pl order-service dependency:tree
```

Use Maven Dependency Plugin filters matching the version in use to focus on suspect groups/artifacts; if reproducibility is required, pin plugin versions in the build.

### 11.2. Maven nearest-definition

Suppose:

```text
order-service
   |
   +-- web-client:2.0
   |      |
   |      +-- json-core:1.5
   |
   +-- report-sdk:3.0
          |
          +-- json-core:2.1
```

Maven normally applies dependency mediation by **nearest definition**; at equal depth it can be affected by dependency declaration order unless `dependencyManagement` or other rules determine the version. Therefore, do not assume “Maven always picks the highest version”.

If a caller was compiled to use a method present in `json-core:2.1` while runtime selects `1.5`, `NoSuchMethodError` can occur.

### 11.3. Using dependencyManagement/BOM

In a parent POM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>json-core</artifactId>
            <version>2.1.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
```

This example helps steer the version when the dependency participates in the graph. It **does not** prove `2.1.0` is compatible with all framework modules; use the framework's BOM/version matrix if available and run tests.

### 11.4. Effective POM and profiles

```shell
./mvnw help:effective-pom
./mvnw help:active-profiles
```

A profile can change dependencies or be activated by JDK/OS. During migration, a Java 21 CI may resolve a different graph than a Java 17 CI even when source code has not changed.

Save the effective POM, active profiles, and runtime dependency tree for the release artifact. Reading only the root `pom.xml` can miss parent/configurations used by the real build.

### 11.5. Purposeful exclusions

If a dependency pulls in an old transitive JAR:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>web-client</artifactId>
    <version>2.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>json-core</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

After exclusion, another dependency path must supply the right version of `json-core`. Exclusion can remove needed classes or push runtime onto a version that `web-client` does not yet support.

Do not treat exclude as a harmless way to “reduce duplicates”; it alters the dependency graph and requires regression testing.

### 11.6. Maven Enforcer

The Maven Enforcer Plugin can use rules such as `dependencyConvergence` and `requireUpperBoundDeps` to detect certain inconsistent versions. However, a graph converging on a single version can still have the wrong ABI relative to a caller.

Therefore, Enforcer is a **dependency-graph prevention gate**, not a substitute for runtime compatibility tests and API/binary diffs.

## 12. Gradle: finding version conflicts and dependencyInsight

### 12.1. Runtime graph

```shell
./gradlew :order-service:dependencies \
  --configuration runtimeClasspath
```

This command displays the resolved graph within the configuration scope. When linkage errors occur, **runtimeClasspath** is usually more important than the list of `implementation` declarations.

### 12.2. Explaining why a version was selected

```shell
./gradlew :order-service:dependencyInsight \
  --dependency json-core \
  --configuration runtimeClasspath
```

`dependencyInsight` helps trace the path to a dependency, the selected version, and related reasons/constraints per Gradle version.

### 12.3. Conflict resolution mechanism

Gradle has a version selection mechanism based on dependency metadata, conflict resolution, and constraints; in many conflicting compatible-version scenarios, Gradle prefers the higher version. However, `strictly`, `prefer`, `require`, platforms, capabilities, variants, and custom rules can alter the outcome.

Do not copy “Maven nearest wins” reasoning onto Gradle. Inspect the actual resolved graph and selection reasons from the running build tool.

### 12.4. Constraints and platforms

Groovy DSL example:

```groovy
dependencies {
    implementation platform(
        'com.example:framework-bom:5.1.0'
    )

    constraints {
        implementation('com.example:json-core') {
            version {
                strictly('2.1.0')
            }
            because 'ABI tương thích đã được xác nhận'
        }
    }
}
```

Constraints can help fail clearly when a dependency demands an incompatible version. However, do not use `strictly` or `force` to coerce a version not yet tested with the framework in use.

### 12.5. Dependency locking

Lockfiles help keep resolved versions stable across builds. If fixing a `NoSuchMethodError` caused by version skew, update version declarations/constraints properly according to the compatibility matrix, update locks via the official workflow, and review the diff.

**Do not** hand-edit a lockfile and treat that as proof that the right production JAR was found. Rebuild the application artifact and inspect runtime classes.

### 12.6. Different compile and runtime classpaths

In Gradle:

- `compileClasspath` and `runtimeClasspath` may resolve differently.
- `compileOnly` does not automatically become a runtime dependency.
- `runtimeOnly` does not appear on the compile classpath.
- `api`/`implementation` expresses exposure of library types.
- Custom configurations or plugins may add different dependencies.

A library compiled with `json-core:2.1` while application runtime uses `1.5` is a classic linkage error scenario. What needs fixing is the publication/consumer graph, not only that source module.

## 13. Comparing compile-time and runtime dependency graphs

### 13.1. Same dependency, two versions

```text
Compile time:
  order-service:1.0
     -> json-core:2.1  (has parse(String))

Runtime:
  order-service:1.0
     -> json-core:1.5  (does not have parse(String))
```

Caller bytecode contains:

```text
invokevirtual JsonMapper.parse(Ljava/lang/String;)LJsonNode;
```

Yet the runtime class lacks that descriptor. This is purely an illustration of how the error occurs.

### 13.2. Build pipeline and deployment pipeline may use different graphs

Example CI build:

```text
mvn verify
  -> application.jar
  -> dependencies in target/lib
```

But deployment:

```text
application.jar
  + old shared/lib/json-core-1.5.jar
  + new target/lib/json-core-2.1.jar
```

Classpath ordering/classloader policy may pick one of the two. Fixing source/`pom.xml` without changing the deployment layout will not solve it.

### 13.3. Local cache differs from actual runtime

Maven/Gradle caches may contain multiple JAR versions. Merely seeing `json-core-2.1.jar` in the local cache does not mean that is the copy running.

Evidence from production class-loading origin, artifact checksums, or the exact deployment image is needed. Cache cleanup is useful to rule out certain local issues, but does not replace root-cause investigation.

## 14. Commonly confused errors and how to distinguish them

| Error | Typical meaning | Priority check |
|---|---|---|
| `NoSuchMethodError` | Method descriptor needed by caller could not be resolved | `javap` caller/callee; runtime JAR |
| `NoSuchFieldError` | Field name+descriptor needed by caller could not be resolved | `Fieldref`, field descriptor, runtime JAR |
| `NoClassDefFoundError` | Class cannot be defined/loaded when needed, or previously failed initialization | Missing JAR, classloader, cause chain |
| `ClassNotFoundException` | Class lookup via API can throw checked exception | Classpath/module path, dynamic load name |
| `IncompatibleClassChangeError` | Static/instance or class/interface assumptions no longer hold | Opcode, class kind, ABI |
| `AbstractMethodError` | Method call resolved, but runtime lacks matching concrete implementation | Interface evolution, implementation version |
| `IllegalAccessError` | JVM denies access to member/class after visibility/module change | Access flags, JPMS exports/opens |
| `UnsupportedClassVersionError` | Class-file version is too new for the JVM | Runtime JVM and class major |
| `NoSuchMethodException` | Reflection API did not find method matching criteria | Reflection lookup, visibility, parameters |
| `NoSuchFieldException` | Reflection API did not find field | Reflection lookup, inheritance, declared/public |

Do not apply one “upgrade dependency” solution to every error. Each type signals a different point of failure.

### 14.1. NoSuchMethodException is not NoSuchMethodError

Reflection:

```java
Class<?> type = Class.forName("demo.lib.Greeter");
type.getDeclaredMethod("greet", String.class);
```

can throw `NoSuchMethodException`, a checked exception, if the method is not found under reflection rules.

Conversely, already-compiled `invokevirtual` bytecode pointing to an unresolvable method can throw `NoSuchMethodError`. Investigations are related but not identical.

### 14.2. IllegalAccessError and JPMS

If the method exists and the descriptor matches, yet runtime accessibility is invalid, the error may be `IllegalAccessError`. With reflection on newer JDKs, `InaccessibleObjectException` can also arise due to module strong encapsulation.

Do not use `--add-opens` to fix `NoSuchMethodError` when the method was actually removed. Opening module access does not recreate an old binary method.

### 14.3. AbstractMethodError when changing interfaces

An interface adding a new abstract method while an older implementation class has not implemented it can lead to `AbstractMethodError` when the method is invoked in certain binary evolution scenarios.

Do not conclude every interface addition breaks binary compatibility immediately upon loading; check how callers invoke and whether implementations actually have the method.

## 15. Specifics when upgrading JDK 8 to 17/21/25

### 15.1. Upgrading the JDK does not recreate removed methods

A `NoSuchMethodError` in a third-party library after upgrading the JDK can result from:

- Framework/BOM changing dependency versions.
- A newer Gradle/Maven plugin selecting a different transitive graph.
- Application server changing provided libraries.
- Incompatible bytecode enhancer or agent.
- Changed runtime path or classloader.
- Modified JDK internal classes/APIs.

Do not attribute the cause directly to the JDK before determining whether the callee class is in the JDK or a third-party artifact.

### 15.2. If the callee is a Java SE API class

If the stack trace points to `java.*` or `javax.*`/`jdk.*`, determine:

- Does the method belong to a public API or a JDK internal API?
- Does it exist in the actual Java release?
- Did the compiler use an appropriate `--release`?
- Does a dependency bundle JDK API classes itself or cause shadowing?
- Do frameworks/agents rely on internal APIs?
- Which JDK version and vendor is the actual runtime?

For example, when compiling with JDK 21, setting only `-source 17 -target 17` can allow referencing Java 21 APIs depending on how compiler/platform APIs are configured, while the artifact runs on Java 17. With modern `javac`, `--release 17` is a better way to restrict Java SE APIs to release 17.

### 15.3. JDK internals and APIs without stability guarantees

An older library may call `sun.*` or `jdk.internal.*` APIs not committed as Java SE public APIs. When upgrading the JDK, internal classes/methods may change or have access blocked.

In that case, the long-term solution is updating the framework/agent/library to a version supporting the target JDK or migrating to supported APIs. Flags `--add-exports`/`--add-opens` only address certain access issues, and do not restore removed methods.

### 15.4. Upgrading compiler target and dependencies together

A Java 21 bytecode library (major 65) cannot run on Java 17, even if code calls a method sharing the same name as a Java 17 API. Conversely, a Java 17 bytecode library can still use a binary-incompatible dependency when the app runtime picks a different version.

Check all four:

1. Class-file level.
2. Java platform API level.
3. Dependency ABI.
4. Runtime behavior.

## 16. Framework migration and BOM mismatches

### 16.1. Why do errors often appear after upgrading frameworks?

Frameworks usually publish a set of dependency versions tested together. For instance, a framework release line replaces ORM/JSON/HTTP libraries. If only the framework core is upgraded while some old starters/plugins remain, the runtime may contain modules with differing API expectations.

```text
framework-core:v5 -> calls codec.normalize(String)
adapter-plugin:v3 -> brings codec:v1
framework-bom:v5  -> expects codec:v2
```

When the runtime chooses v1, core may throw `NoSuchMethodError`. The solution is not forcing the “latest version on the internet” but selecting a supported and tested framework/plugin/BOM combination.

### 16.2. Spring and its module ecosystem

When using Spring Framework/Boot/Data/Security/Cloud, read the compatibility matrix of the **exact release lines**, rather than mixing “latest” modules on your own.

If working with a WAR on an external server, server-provided dependencies may differ from an executable JAR. Identify the embedded/external server version and corresponding Java/Jakarta namespace.

### 16.3. Jakarta migration

Moving from `javax.*` to `jakarta.*` commonly changes binary class names, leading to `ClassNotFoundException`/`NoClassDefFoundError` or method signature mismatches when libraries mix two API generations.

Do not assume every error during Jakarta migration will be `NoSuchMethodError`. Inspect actual class/method descriptors and data/API compatibility.

### 16.4. Logging bindings and bridge libraries

An application may carry multiple bindings/bridges or logging plugins at a different version from the logging API. Linkage errors can occur when logger callers are compiled against a newer API while runtime picks an older JAR.

Separate the modules:

- Logging API.
- Logging implementation.
- Bridges/adapters.
- Framework logging starter.
- Application-server-provided bindings.

Then cross-check the graph and the copy actually loaded by the classloader.

### 16.5. Jackson, Hibernate, and Netty as groups needing attention

Serialization, ORM, and networking libraries often have multiple artifacts within one ecosystem. If the core module and companion modules diverge too far in version, linkage errors can surface in rarely executed code paths.

It is not necessary to force every module to have identical version strings if the vendor publishes another compatible matrix; prefer the official BOM or matrix of that framework and run regression tests.

## 17. Java records, enums, sealed classes, and binary APIs

### 17.1. Record accessor changes

Java 17 record example:

```java
public record Customer(String name, long id) {
}
```

The record has accessors `name():String` and `id():long`. If a new version changes component `name` to `CharSequence`, the accessor descriptor changes. Old callers compiled to call `name():String` may encounter `NoSuchMethodError` when runtime only has the new accessor.

Evaluate record evolution as an API/serialization contract; do not assume keeping the same record name is enough.

### 17.2. Enum constants and field references

Enum constants are represented as static fields of the enum type. Removing or renaming an enum constant can leave old code using `getstatic` on a nonexistent field and lead to `NoSuchFieldError`.

With serialized/JSON data containing enum names, there is also protocol compatibility to consider. The solution should include versioning and mapping/unknown-value policies rather than merely recompiling.

### 17.3. Sealed classes and pattern matching

Converting a type hierarchy to sealed can change the set of permitted implementations and the behavior of exhaustive switches in newer Java versions. Not every error will be `NoSuchMethodError`, yet binary/API compatibility must be reviewed alongside migration.

### 17.4. Kotlin/Groovy/Scala and generated code

Other JVM languages have compiler conventions, bridges, default methods, and binary metadata distinct from plain Java source. When upgrading compiler plugins or libraries, older Java code may call symbols no longer present at runtime.

Inspect **actual bytecode descriptors** with `javap`, rather than inferring from Kotlin/Groovy/Scala source-level APIs. Bytecode generated by annotation processors/AOP must also be verified after the build.

## 18. Bytecode generation and instrumentation

### 18.1. Byte Buddy, ASM, Javassist, proxies

Frameworks can generate classes at runtime, create subclasses, or instrument bytecode. If they rely on a method version that no longer exists, the error can surface inside a generated class instead of project source.

Investigate:

- Does the stack trace contain generated/proxy class names?
- What are the agent/transformer versions?
- Do they support the target JDK class-file version?
- From which interface version was the proxy generated?
- Are there cached generated classes from a prior build?
- Does the error occur when loading the class, invoking the method, or reflecting the method?

### 18.2. Be careful with bridge methods

The Java compiler can generate bridge/synthetic methods to preserve polymorphism after type erasure or covariant returns. A transformer/minimizer stripping bridge methods assuming they are “unused” can cause linkage errors.

Use:

```shell
javap -classpath path/to/library.jar \
  -p -s -v com.example.SomeClass
```

Check `ACC_BRIDGE` and `ACC_SYNTHETIC` flags as appropriate. Do not strip generated methods from artifacts without knowing compatibility requirements.

### 18.3. Annotation processors and Lombok

Part of a library's methods/fields may be generated at compile time by Lombok/processors. If IDE and CI use different processor versions, bytecode artifacts can differ even when sources look identical.

Inspect compiled classes inside the published JAR, not just annotations or expected generated source.

### 18.4. Agent version differing from JVM

An APM agent or mocking agent that does not support a new JDK may instrument classes incorrectly or call changed APIs. When diagnosing, test the application with and without the agent in a controlled environment and check the agent compatibility matrix.

Do not permanently disable a production agent just to hide an error; upgrade or select a supported configuration.

## 19. Classloader isolation, plugin architecture, and application servers

### 19.1. Same class name does not mean the same class

In the JVM, a class's identity depends on both its binary name and its **defining classloader**. Two loaders can load two definitions named `com.example.json.JsonMapper` from two JARs.

```text
Parent loader
  -> json-core:v1

Child plugin loader
  -> json-core:v2

Caller from plugin -> expects API v2
Runtime binding -> may resolve v1 or v2
depending on loader delegation/isolation
```

If a plugin was compiled against v2 while the runtime class is selected from parent v1, `NoSuchMethodError` can occur.

### 19.2. Parent-first and child-first

There is no single universal rule across all frameworks:

- Some containers prioritize parent JARs.
- Some plugin systems use child-first.
- OSGi/modules have different import/export models.
- JPMS uses resolution/readability and module layers.
- Spring Boot executable JARs use their own launcher/classloader layout.

Read the classloader configuration of the runtime in use and obtain class-origin evidence.

### 19.3. Duplicate API classes in plugin JARs

If host and plugin package two copies of a similarly named interface under different loaders, `ClassCastException` or other linkage errors can happen. A well-behaved plugin should use the API contract shared by the host rather than arbitrarily shading/repackaging API classes with shared identity logic.

### 19.4. Hot reload/redeploy

Some application servers retain shared classloaders or caches across redeploys. Replacing a WAR while an old shared library version remains in the process can trigger errors.

Do not merely copy a new JAR and assume the runtime loaded it. Confirm deployment lifecycle, classloader state, process restart requirements, and actual class-loading logs.

## 20. JPMS: module paths can also drift in version

### 20.1. Module resolution

When an application uses `module-info.java`, the JVM/module system resolves named modules along the module path. A module graph valid for readability can still contain a module version with a different API from compile time.

Determine:

- Module name and version metadata.
- Module path used by the launcher.
- `requires` of callers.
- `exports`/`opens` of callees.
- Module layer/custom loader.
- Artifact actually resolved.

### 20.2. Module errors differ from missing method errors

A module not found can cause `FindException` during resolution. Invalid access permissions can cause `IllegalAccessError` or reflection-related exceptions.

If the module loads yet a method descriptor is gone, `NoSuchMethodError` remains a possibility. Do not use `--add-reads`/`--add-opens` as a generic workaround for nonexistent symbols.

### 20.3. Automatic modules and split packages

A legacy JAR placed on the module path can become an automatic module; split packages or conflicting module names make resolution differ from the classpath. When migrating from JDK 8 to 17+, verify both packaging mechanisms and the module graph, not merely switching `-cp` to `--module-path`.

## 21. Sustainable error fixes

### 21.1. Restoring the old binary API when maintaining a library

If you are the library publisher and accidentally changed a method signature, one way to preserve ABI is keeping the old overload:

```java
public final class Greeter {
    // New API:
    public String greet(CharSequence name) {
        return "Hello " + name;
    }

    // Compatibility method for legacy callers:
    @Deprecated
    public String greet(String name) {
        return greet((CharSequence) name);
    }
}
```

Old callers find `greet(String):String`; new callers can use the modern API. This method must actually exist in the runtime JAR and maintain appropriate behavior.

If the old method had a return descriptor that changed, keeping an adapter API or separate major version may be needed, since you cannot always add an overload differing only by return type in Java source.

### 21.2. Selecting the right dependency version for runtime

If callers use API v2 while runtime provides v1, there are two paths:

- Upgrade the runtime library to a version compatible with callers and the entire framework.
- Keep runtime v1 and recompile/re-release callers appropriately if v1 is mandatory.

Do not fix by picking the highest version randomly. Consider binary compatibility, security, minimum Java level, and the ecosystem's support matrix.

### 21.3. Rebuilding all dependent modules when necessary

In a monorepo, if an API changes intentionally, rebuild downstream modules against the new version, verify the complete binary graph, and repackage.

For a published library with external consumers, however, internal rebuilding is not enough. You may need to retain binary-compatible methods or release a major migration version.

### 21.4. Removing duplicate JARs from deployment

If the runtime has the same class in multiple JARs, find the cause:

- App bundle contains two versions.
- Server shared libraries override WAR libs.
- Shadow plugin bundles both old and new versions.
- Container layer retains an old artifact.
- Plugin repackages shared libraries.

Remove/isolate the wrong copy by design and test the exact deployment layout after fixing.

### 21.5. Changing classloader policy only when understanding scope

Switching to child-first may allow a plugin to use v2 yet break APIs shared with the host or create class identity conflicts. Changing delegation is an architectural decision with broad impact; only do so after defining shared contracts and testing other plugins.

## 22. What not to do when handling incidents

**Do not catch `NoSuchMethodError` and continue business flow as if nothing happened.** This is a symptom of inconsistent deployment/ABI; it can leave data partially written or fail in another code path.

**Do not only clear the Maven/Gradle cache and declare it done.** Caching may be a factor, but you must prove the actual JAR changed and why.

**Do not change the JDK version arbitrarily.** A newer JDK does not restore a method removed by a library.

**Do not force a version with force/strictly without checking caller requirements.** One version may suit one module while breaking another.

**Do not inspect only source declarations.** The JVM runs actual bytecode and artifacts; source in checkout may not match the release.

**Do not run only unit tests with the compile classpath.** Production apps may have runtime-only dependencies, WAR libs, nested JARs, and different agents.

**Do not use `--add-opens` to recreate a missing method/field.** Module access differs from symbolic resolution.

**Do not assume the same version string means the same artifact bytes.** Mutable repositories or poisoned caches can give identical coordinates different checksums.

**Do not ignore the first stack trace.** Later wrapper errors may be consequences rather than the cause.

## 23. Production incident handling workflow

### Step 1: Preserve evidence

Save the full stack trace and cause chain. Record service version, source commit, image digest, JDK vendor/full version, deployment platform, failure timestamp, request/job type, and recent changes.

### Step 2: Determine scope

Does the error appear on:

- Every request or only a specific feature?
- One pod/VM or the entire fleet?
- Java 21 only or Java 17 as well?
- Only when the APM agent is enabled?
- Only the WAR on an external server?
- Only the canary release after changing a dependency?

Grouping helps narrow down versions/environments instead of hunting random source files.

### Step 3: Find the missing symbol

Read the `NoSuchMethodError` or `NoSuchFieldError` message and record the class, name, and expected descriptor if available. Identify the exact caller frame where the error arises.

### Step 4: Find the runtime JAR

Use class-loading logs, `CodeSource`, runtime bundle inspection, or server classloader diagnostics. Do not rely on the local cache as sole evidence.

### Step 5: Compare bytecode

Run `javap -p -s -v` on caller and callee; identify the exact missing descriptor/opcode/field kind.

### Step 6: Analyze dependency resolution

Check Maven `dependency:tree` or Gradle `dependencies`/`dependencyInsight`, along with BOM, plugin versions, and runtime deployment graph.

### Step 7: Decide on containment

If the incident affects production, consider rolling back to a **tested combination of artifact + dependencies + runtime**, or disabling the feature in a controlled way. Do not swap a single JAR on a running system without knowing dependency coupling.

### Step 8: Fix the root cause

Update dependencies/BOM, restore compatibility methods/fields, fix packaging, adjust verified classloader policy, or fix the build pipeline depending on root cause.

### Step 9: Verify

Test on the production-like JDK, OS, classloaders, agents, and final deployment artifact. Exercise both the failing functionality and related regression/contract tests.

### Step 10: Prevent recurrence

Pin the graph, add binary/API checks, log artifact provenance, and block duplicates/mismatched variants in CI.

## 24. Specific case matrix

| Symptom | Signal | First checkpoint |
|---|---|---|
| Error after adding a new library | Transitive version changed | Resolved runtime dependency tree |
| Error only on application server | Different shared libs/classloader | Server libs and class origin |
| Error only in fat JAR | Wrong nested/shaded libs | Post-packaging artifact |
| Error after upgrading Spring/ORM | Out-of-sync BOM/release train | Framework compatibility matrix |
| Error after upgrading JDK | Plugin/agent/framework internal API changed | Callee origin and JDK-specific calls |
| Error only when calling endpoint | Lazy method resolution | Caller bytecode and integration path |
| Error on canary pod | Image/version mismatch | Image digest and exact JAR checksums |
| `NoSuchFieldError` with enum | Constant removed/renamed | Enum binary fields and schema |
| Error disappears after full rebuild | Leftover v1 ABI caller | Build/release provenance and stale artifacts |
| Error only after hot reload | Old classloader/JAR | Redeploy process state |
| Error after shading/minimizing | Bridge or method stripped | Final JAR disassembly |
| Error only on one JDK | MR-JAR class variant | `META-INF/versions` and runtime selection |

## 25. CI gates to prevent NoSuchMethodError and NoSuchFieldError

### 25.1. Pin the dependency graph

- Use BOM/platform/dependencyManagement for framework families.
- Do not use dynamic versions in release paths without locking/governance.
- Commit the Gradle lockfile when using dependency locking.
- Review dependency diffs on every PR upgrading framework/JDK.
- Verify repository artifact integrity when needed.
- Do not publish mutable release JARs with the same coordinates.

### 25.2. API/binary compatibility checks for libraries

Use tools like `japicmp`, `Revapi`, or equivalent solutions to compare API/ABI between the released version and candidate version.

Understand tool scope: it helps detect changes to public/protected APIs, method descriptors, field types, and certain signature changes, yet does not replace runtime tests, reflection contracts, or protocol compatibility.

### 25.3. Test compile/runtime classpaths

A job can compare resolved compile/runtime graphs and check intentional differences. Pay special attention to:

- `compileOnly`/`provided`.
- Optional dependencies.
- Test-only libraries.
- Application-server-provided JARs.
- Plugin classpath.
- Shaded/nested JARs.
- OS/JDK conditional dependencies.

Do not require the two graphs to be identical since some dependencies are runtime-only, but prove every runtime caller receives the right ABI.

### 25.4. Scan for duplicate classes

Managed build plugins or scripts can detect the same binary class name across multiple runtime JARs. Duplicate classes are not always an error if valid isolation exists, yet must be reviewed rather than ignored.

Reports should specify:

```text
Class:
  com.example.json.JsonMapper

Origins:
  json-core-1.5.jar
  json-core-2.1.jar

Expected loader:
  application runtime loader

Decision:
  select one compatible JAR or isolate intentionally
```

### 25.5. Test the final artifact

Before release, run:

```text
Compile -> Test -> Package -> Inspect artifact
                         |
                         v
                Run packaged release
                         |
                         v
                 Integration tests
                         |
                         v
                Staging / canary
```

A test running only inside Maven/Gradle before packaging does not guarantee the deployed WAR/uber JAR/container image uses the right JAR.

### 25.6. Test minimum and target JDKs

If a library commits to supporting Java 17 and Java 21:

- The compiler produces the appropriate class-file target.
- The runtime graph uses dependency versions supporting Java 17.
- Run tests on actual Java 17.
- Run tests on actual Java 21.
- Verify agents, native code, frameworks, and MR-JAR variants if any.

Do not treat running the application on Java 21 as proof of Java 17 compatibility.

## 26. Hands-on exercises

### Exercise 1: Method with changed parameter

A library v1 exposes:

```java
public String render(String value);
```

v2 only keeps:

```java
public String render(CharSequence value);
```

The old caller was compiled against v1.

State the v1/v2 descriptors, explain `NoSuchMethodError`, test with `javap`, and propose an appropriate ABI fix if old binary consumers must be supported.

### Exercise 2: Field with changed type

A library v1 exposes:

```java
public static int TIMEOUT = 30;
```

v2 changes to:

```java
public static long TIMEOUT = 30;
```

Describe the field descriptors, the opcode reading the static field, and why old callers can hit `NoSuchFieldError`.

Compare with the case:

```java
public static final int TIMEOUT = 30;
```

and explain how constant inlining can prevent the error from appearing while the value used remains old.

### Exercise 3: Maven conflict

```text
app
  +-- A -> codec:1.0
  +-- B -> codec:2.0
```

Callers in B need a method only present in 2.0. Use dependency tree and dependencyManagement to analyze. Do not pick a version until A/B binary compatibility is confirmed.

### Exercise 4: Gradle runtime graph

A project compiles with `codec:2.0` yet runtimeClasspath selects `codec:1.0` due to a custom resolution rule.

Describe the `dependencyInsight` command, how to read the selection reason, and verifying with `javap` on the actual JAR.

### Exercise 5: WAR behaves differently from executable JAR

An application runs when using an embedded server yet throws `NoSuchMethodError` on an external application server. Lay out the sequence for collecting:

- Application and server versions.
- WAR contents.
- Shared server libraries.
- Parent-first/child-first policy.
- Class origin.
- Runtime method descriptor.

### Exercise 6: MR-JAR

A class has a base implementation and a variant under `META-INF/versions/21`. The error appears only on Java 21. Determine the selected class version, manifest, and symbol in the variant, then explain why inspecting only the base class is not enough.

### Exercise 7: Designing CI prevention

Design a pipeline with dependency locks/BOMs, API binary diffs, duplicate-class scans, artifact inspection, and runtime integration tests. State the error types each gate can detect and the error types it cannot prove.

## 27. Quick diagnostic checklist

### Gathering evidence

- [ ] Have full exception message and cause chain.
- [ ] Identified caller, callee, method/field, and descriptor.
- [ ] Recorded exact JDK vendor/version and deployment artifact digest.
- [ ] Know which functional path the error appears on.
- [ ] Have class-loading source or runtime JAR location.
- [ ] Have classloader/module path info if needed.
- [ ] Did not share secrets in diagnostic logs.

### Bytecode analysis

- [ ] Used `javap -p -s` on the exact runtime class.
- [ ] Used `javap -c -v` to inspect caller references/opcodes.
- [ ] Checked return type and argument descriptors.
- [ ] Checked static/instance kind and access flags.
- [ ] Checked synthetic/bridge methods if relevant.
- [ ] Checked enum/record/MR-JAR specifics when applicable.
- [ ] Distinguished current compiled source from deployed bytecode.

### Dependencies and packaging

- [ ] Verified Maven/Gradle runtime dependency graph.
- [ ] BOM/platform/plugin versions match the release line.
- [ ] Differences between compile/runtime classpaths have a clear reason.
- [ ] No unintended old JARs/duplicate classes remain.
- [ ] Inspected the final WAR/fat/nested/shaded artifact.
- [ ] Reviewed application server shared libs/classloader policy.
- [ ] Identified agents/native/plugin dependencies when used.

### Remediation and prevention

- [ ] Chose a supported version/ABI rather than upgrading randomly.
- [ ] Rebuilt callers or preserved compatibility APIs where appropriate.
- [ ] Ran integration tests on the exact runtime JDK.
- [ ] Used a binary/API checker for published libraries.
- [ ] Pinned the dependency graph and reviewed version diffs.
- [ ] Have canary/rollback with immutable artifacts.
- [ ] Added tests for the exact code path that caused the error.

## Conclusion

`NoSuchMethodError` and `NoSuchFieldError` are two classic signs of **binary linkage mismatch**: caller bytecode requests a method or field that does not exist with the **exact name and descriptor** in the runtime class chosen by the JVM. They can appear after upgrading the JDK/framework not because the compiler spontaneously broke, but because dependency resolution, classloading, bytecode generation, or packaging caused **compile-time API and runtime API to diverge**.

The most effective way to resolve them is evidence-driven: read the full stack trace, identify the caller and symbolic reference, find the right JAR/module/classloader, compare descriptors with `javap`, analyze the Maven/Gradle graph, and inspect the final artifact. Then choose a compatible version or restore the old binary API, run tests on the target JDK/deployment, and put CI gates in place for dependencies, ABI, duplicate classes, and release provenance. Following this sequence helps Java Advance Compatibility Migration avoid errors that only erupt when a feature is actually called in production.
