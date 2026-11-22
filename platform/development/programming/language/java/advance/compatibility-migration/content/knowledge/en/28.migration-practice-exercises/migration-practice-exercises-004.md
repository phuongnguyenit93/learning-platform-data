# Creating a New Library That Breaks Old Consumer Artifacts

In **Java Advance Compatibility Migration**, a hard-to-spot bug occurs when **a new library compiles cleanly, a new application compiles cleanly, yet a previously compiled consumer artifact breaks at runtime**. The root cause is **binary compatibility**: the consumer's bytecode still contains calls targeting the old class name, method name, and method descriptor, whereas the new library removed or altered that portion of the API.

This hands-on exercise builds a small system consisting of the **library** `catalog-core` and the **consumer** `legacy-client`. In library version v1, the method `formatPrice(int)` exists. In v2, the library author changes that method to `formatPrice(long)` intending to "widen the numeric type, surely that's compatible". The old client source code **can still recompile** against v2, because Java allows widening `int` to `long`. However, `legacy-client.jar`, compiled against v1, still invokes descriptor `(I)Ljava/lang/String;`, resulting in `NoSuchMethodError` when run alongside v2.

Starting from an intentional failure case, you will learn how to reproduce it, inspect bytecode, distinguish source compatibility from binary compatibility, fix it using a **compatibility bridge**, and then design a regression gate to detect the issue before releasing a library.

> **Scope:** This is a self-contained lesson. Commands and outputs in this lesson are **expected guides/simulations**, not reports claiming they were executed in a real environment. The lesson uses Java 17+ for `jar --create` syntax and the `javac --release 17` option. No Maven, Gradle, database, or network is required to complete the core exercise.

## 1. Objectives After This Exercise

After completing this exercise, you will be able to:

1. Describe the difference among **source compatibility**, **binary compatibility**, and **behavioral compatibility**.
2. Produce two independent artifacts: a library JAR and a consumer JAR.
3. Keep the compiled consumer JAR unchanged and swap the library at runtime to reproduce a linkage error.
4. Understand why `formatPrice(int)` and `formatPrice(long)` differ even though the call in source code looks unchanged.
5. Use `javap` to observe the method descriptor the JVM actually requires.
6. Distinguish `NoSuchMethodError` from compile errors, `ClassNotFoundException`, and `NoClassDefFoundError`.
7. Fix v2 using a bridge/overload preserving the old API, **without rebuilding the old consumer artifact**.
8. Propose source, binary, and runtime checks for a library claiming support for previously released consumers.

## 2. Real-World Context

Imagine a system consisting of three groups:

~~~text
Library team
  catalog-core v1
       |
       +--> releases catalog-core-1.0.jar
                         |
                         v
Consumer team
  compiles legacy-client.jar
  against v1's public API
                         |
                         v
Operations team
  replaces runtime library with catalog-core-2.0.jar
  WITHOUT recompiling legacy-client.jar
~~~

The library team assumed changing the `int` parameter to `long` was a safe improvement because every `int` can convert to `long` in Java source code. That conclusion considers only **source invocation** when the compiler gets to run again. Previously released consumer artifacts do not re-run the compiler's overload resolution mechanism; they carry a fixed binary invocation.

This kind of scenario is especially critical for:

- SDKs/JARs embedded by client applications at runtime.
- Plugin frameworks allowing library updates without rebuilding plugins.
- Agents, JDBC driver wrappers, and adapters shared across independent services.
- Multi-module applications where modules are released on separate schedules.
- Containers or application servers providing shared libraries.
- Internal libraries published to a Maven repository with multiple consumers not yet on synchronized versions.

Not every project commits to supporting old binary consumers. However, when one does, **"the new library works with new source"** is an insufficient standard.

## 3. Three Types of Compatibility to Distinguish

| Type | Question | Test |
|---|---|---|
| **Source compatibility** | Does the old consumer source recompile against the new API? | Re-run `javac` on consumer source with library v2 |
| **Binary compatibility** | Does old consumer bytecode link and run against library v2? | Use the **exact old `consumer.jar`** together with library v2 |
| **Behavioral compatibility** | Do results, errors, side effects, and business contracts remain accurate? | Unit/integration/contract tests with matching data |

Outcomes can differ:

| Source v1 with lib v2 | Binary consumer v1 with lib v2 | Interpretation |
|---|---|---|
| PASS | PASS | Potentially compatible at both levels; behavioral tests still needed |
| PASS | FAIL | **Focus of this lesson:** source recompiles yet old artifact fails |
| FAIL | PASS | Possible with certain changes that alter source resolution while old bytecode can still link |
| FAIL | FAIL | Change clearly breaks multiple forms of compatibility |

**Important:** Binary compatibility does not promise behavioral compatibility. A method keeping the exact same signature while changing from `HALF_UP` to `DOWN` rounding can be binary-compatible yet break business logic.

## 4. Environment Setup and Project Structure

Use JDK 17 or newer to have `javac`, `jar`, `java`, and `javap`. A **full JDK** is needed, not just a minimal JRE image.

Verify versions when running on your study machine:

~~~bash
java -version
javac -version
jar --help
javap -help
~~~

Suggested directory structure:

~~~text
binary-compat-lab/
  src/
    lib-v1/
      com/example/catalog/PriceService.java
    lib-v2/
      com/example/catalog/PriceService.java
    lib-v2-fixed/
      com/example/catalog/PriceService.java
    client/
      com/example/client/ClientMain.java
  out/
    lib-v1/
    lib-v2/
    lib-v2-fixed/
    client/
    client-new/
  dist/
    catalog-v1.jar
    catalog-v2.jar
    catalog-v2-fixed.jar
    client-original.jar
    client-recompiled.jar
~~~

The `src/...` directories contain sources for you to create. `out/` and `dist/` hold generated artifacts for this exercise. When redoing the exercise, delete only the generated `out`/`dist` directories and recreate them to avoid accidentally picking up stale classes. Do not delete directories outside the exercise.

### 4.1. Platform Notes

Commands in the main steps use **Bash on Linux/macOS**. On Windows PowerShell, the same `javac`/`jar`/`java` tools work, except:

- The classpath separator is **`;`** instead of **`:`**.
- Create directories using `New-Item -ItemType Directory` or an equivalent command.
- Do not copy a Bash line containing `mkdir -p` verbatim into PowerShell expecting identical behavior.
- Relative paths in examples assume commands run from the `binary-compat-lab` directory.

Example creating output directories in Bash:

~~~bash
mkdir -p out/lib-v1 out/lib-v2 out/lib-v2-fixed
mkdir -p out/client out/client-new dist
~~~

Create the source files following the code snippets in subsequent sections before invoking the compiler.

## 5. Creating Library v1: Initial Public API

File: `src/lib-v1/com/example/catalog/PriceService.java`

~~~java
package com.example.catalog;

public class PriceService {

    public String formatPrice(int cents) {
        return cents + " VND";
    }
}
~~~

In this minimal example, the parameter name `cents` is merely a parameter name representing an integer quantity; printing `VND` is used for readability. This is **not** a currency business model involving exchange-rate calculations or subunit conversion.

What matters is the **public API**:

~~~java
public String formatPrice(int cents)
~~~

At the JVM level, the method has:

- Name: `formatPrice`.
- Parameter: one `int`.
- Return type: `java.lang.String`.
- Method descriptor: `(I)Ljava/lang/String;`.

The symbol `I` in the descriptor means `int`; `J` means `long`. A descriptor consists of parameter types inside parentheses followed by the return type after the parentheses. The JVM uses this binary information when linking calls.

### 5.1. Building `catalog-v1.jar`

Run from the exercise root directory:

~~~bash
javac --release 17 -encoding UTF-8 \
  -d out/lib-v1 \
  src/lib-v1/com/example/catalog/PriceService.java

jar --create --file dist/catalog-v1.jar \
  -C out/lib-v1 .
~~~

Explanation:

- `--release 17` instructs the compiler to produce bytecode/API compatibility for Java 17; the compiler must be a JDK supporting this release.
- `-d out/lib-v1` places the class in the matching package directory.
- `jar --create --file` packages classes into a JAR.
- `-C out/lib-v1 .` takes contents from the classes directory without embedding an `out/lib-v1` prefix into package paths inside the JAR.

The v1 artifact now contains the class:

~~~text
com/example/catalog/PriceService.class
~~~

## 6. Creating a Consumer Using Library v1

File: `src/client/com/example/client/ClientMain.java`

~~~java
package com.example.client;

import com.example.catalog.PriceService;

public final class ClientMain {

    public static void main(String[] args) {
        PriceService service = new PriceService();
        String output = service.formatPrice(1200);
        System.out.println(output);
    }
}
~~~

Looking at the source:

~~~java
service.formatPrice(1200)
~~~

The compiler sees that literal `1200` has type `int` and resolves the call to `formatPrice(int)` in `catalog-v1.jar`. That exact method reference is recorded in the consumer's bytecode.

### 6.1. Compiling the Consumer Against v1

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp dist/catalog-v1.jar \
  -d out/client \
  src/client/com/example/client/ClientMain.java

jar --create --file dist/client-original.jar \
  -C out/client .
~~~

**This is a critical milestone in the exercise:** After this command, treat `dist/client-original.jar` as an artifact already released by the consumer team. **Do not modify or recompile this JAR** during the binary-failure reproduction steps.

You can save the artifact checksum before testing:

~~~bash
sha256sum dist/client-original.jar
~~~

On systems without `sha256sum`, use an equivalent checksum utility such as PowerShell `Get-FileHash`. The goal is proving you use the exact same consumer artifact across all runs.

### 6.2. Running the Baseline With Library v1

On Linux/macOS:

~~~bash
java -cp "dist/catalog-v1.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

Expected output:

~~~text
1200 VND
~~~

On Windows PowerShell, use `;` as the classpath separator:

~~~powershell
java -cp "dist/catalog-v1.jar;dist/client-original.jar" com.example.client.ClientMain
~~~

At this point:

- Consumer bytecode was built against v1.
- Runtime provides `PriceService` from v1.
- The method has the descriptor requested by the consumer.
- The JVM successfully linking the call is expected.

## 7. Creating Library v2 With a Seemingly Harmless Change

The library author wants to support values larger than the `int` limit. They **replace** the old method with one accepting `long`, without keeping the old overload.

File: `src/lib-v2/com/example/catalog/PriceService.java`

~~~java
package com.example.catalog;

public class PriceService {

    public String formatPrice(long cents) {
        return cents + " VND";
    }
}
~~~

This code **no longer has**:

~~~java
public String formatPrice(int cents)
~~~

Instead there is only:

~~~java
public String formatPrice(long cents)
~~~

In Java source code, a call passing `int` can still match a method taking `long` via **primitive widening conversion**. However, at the bytecode level, the old and new methods have different descriptors:

| Version | Public method | JVM method descriptor |
|---|---|---|
| v1 | `String formatPrice(int)` | `(I)Ljava/lang/String;` |
| v2 | `String formatPrice(long)` | `(J)Ljava/lang/String;` |

**v2 fails to provide the method descriptor requested by the old consumer.**

### 7.1. Building v2 Independently

~~~bash
javac --release 17 -encoding UTF-8 \
  -d out/lib-v2 \
  src/lib-v2/com/example/catalog/PriceService.java

jar --create --file dist/catalog-v2.jar \
  -C out/lib-v2 .
~~~

Do not include `catalog-v1.jar` inside `catalog-v2.jar`. The exercise requires a v2 JAR containing **only the new version** of `PriceService`.

## 8. Reproducing the Failure: Swap the Library While Keeping the Consumer Binary

Run the **exact original consumer JAR** against library v2:

~~~bash
java -cp "dist/catalog-v2.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

On Windows:

~~~powershell
java -cp "dist/catalog-v2.jar;dist/client-original.jar" com.example.client.ClientMain
~~~

Expected output is an error similar to:

~~~text
Exception in thread "main" java.lang.NoSuchMethodError:
  'java.lang.String com.example.catalog.PriceService.formatPrice(int)'
    at com.example.client.ClientMain.main(ClientMain.java:...)
~~~

Line numbers, descriptor formatting, and stack trace details may vary across JDKs/compilers. The **core meaning** remains the same: the consumer binary requests `formatPrice(int)`, which the v2 class does not provide.

### 8.1. What Happened?

~~~text
Build time                         Runtime

catalog-v1.jar                     catalog-v2.jar
  formatPrice(int)                   formatPrice(long)
        |                                   |
        v                                   |
javac compiles client                     |
        |                                   |
        v                                   |
client-original.jar                         |
  invokevirtual                            |
  PriceService.formatPrice:(I)Ljava/lang/String;
        |                                   |
        +---------- runtime link ----------+
                                            |
                                  Cannot find method
                                  descriptor (I)...
                                            |
                                       NoSuchMethodError
~~~

The JVM **does not re-run javac's overload selection** when linking old bytecode. A method with the same name taking `long` is not a binary replacement for a method taking `int`.

### 8.2. Why Might the Error Not Appear Immediately at Startup?

The JVM can defer resolving certain symbolic references until the code path actually executes. If `formatPrice(int)` is only called when generating an invoice, an application may start up and pass health checks yet fail when handling a specific request.

Therefore, **a passing startup smoke test** does not guarantee all consumer invocations are compatible. Contract/integration tests that genuinely invoke the published public API are required.

## 9. Evidence: Using `javap` to Read Method Descriptors

`javap` is a JDK tool for inspecting binary class signatures. There is no need to guess from source when you have the artifact.

### 9.1. Inspecting Library v1's API

~~~bash
javap -s -classpath dist/catalog-v1.jar \
  com.example.catalog.PriceService
~~~

Expected output to observe:

~~~text
public java.lang.String formatPrice(int);
  descriptor: (I)Ljava/lang/String;
~~~

### 9.2. Inspecting Library v2's API

~~~bash
javap -s -classpath dist/catalog-v2.jar \
  com.example.catalog.PriceService
~~~

Key portion:

~~~text
public java.lang.String formatPrice(long);
  descriptor: (J)Ljava/lang/String;
~~~

These lines illustrate **what parts to look for**, not the complete raw output captured from the tool.

### 9.3. Inspecting the Call in the Original Consumer Artifact

~~~bash
javap -c -p -classpath dist/client-original.jar \
  com.example.client.ClientMain
~~~

A disassembler comment on the `invokevirtual` instruction may look like:

~~~text
Method com/example/catalog/PriceService.formatPrice:(I)Ljava/lang/String;
~~~

The evidence has three parts:

1. The old consumer requires descriptor `(I)Ljava/lang/String;`.
2. Library v2 provides only descriptor `(J)Ljava/lang/String;`.
3. When executing that code path, the runtime cannot find the old method and throws `NoSuchMethodError`.

That is the **binary root cause**, not a cast error during source compilation.

### 9.4. Why Does the Return Type Also Matter?

In a JVM method descriptor, **the return type is part of the descriptor**. Changing `String` to `Object` without a compatible method/bridge can also break old calls, even if an assignment in Java source might still compile in certain contexts.

Conversely, the Java compiler may generate bridge methods in some covariant-return/generics cases to preserve polymorphism. Do not rely on the compiler always auto-generating a bridge for arbitrary API changes. For the `int` to `long` change in this lesson, the compiler **does not automatically preserve** `formatPrice(int)`.

## 10. Attempting to Recompile the Consumer Source With v2

Run compilation on the exact same `ClientMain.java` source file, placing library v2 on the compile classpath:

~~~bash
javac --release 17 -encoding UTF-8 \
  -cp dist/catalog-v2.jar \
  -d out/client-new \
  src/client/com/example/client/ClientMain.java

jar --create --file dist/client-recompiled.jar \
  -C out/client-new .
~~~

Compilation is expected to **succeed** because `formatPrice(1200)` passes an `int` that widens to `long` for the v2 method.

Run the **newly compiled** artifact:

~~~bash
java -cp "dist/catalog-v2.jar:dist/client-recompiled.jar" \
  com.example.client.ClientMain
~~~

Expected output:

~~~text
1200 VND
~~~

Now two distinct states are clear:

| Consumer artifact | Library runtime | Expected result |
|---|---|---|
| `client-original.jar` built with v1 | `catalog-v1.jar` | PASS |
| `client-original.jar` built with v1 | `catalog-v2.jar` | **FAIL: NoSuchMethodError** |
| `client-recompiled.jar` built with v2 | `catalog-v2.jar` | PASS |

This is the central lesson: **source compatibility does not mean binary compatibility**.

### 10.1. Do Not Use "Rebuild Everything" to Prove a Library Is Still Compatible

If a product permits requiring consumers to rebuild on major version upgrades, that can be a valid policy. However, that decision must be documented in the release contract.

If the goal is **not breaking old consumer artifacts**, simply showing that recompiling the consumer succeeds **does not satisfy the requirement**. The final test must use the original `client-original.jar`.

## 11. Fixing v2 With a Compatibility Bridge

The solution in this exercise is keeping the old API while adding the new API. The old method can delegate to the method accepting `long`.

File: `src/lib-v2-fixed/com/example/catalog/PriceService.java`

~~~java
package com.example.catalog;

public class PriceService {

    /**
     * Legacy entry point used by consumers compiled with v1.
     */
    @Deprecated(since = "2.0", forRemoval = false)
    public String formatPrice(int cents) {
        return formatPrice((long) cents);
    }

    /**
     * New API accepting a wider numeric range.
     */
    public String formatPrice(long cents) {
        return cents + " VND";
    }
}
~~~

This mechanism is commonly called a **compatibility overload** or **manual bridge**. It differs from compiler-generated synthetic bridge methods for certain generics/covariant-return scenarios; here the library author **deliberately** preserves the old method in the public ABI.

### 11.1. Why Cast `(long)` Inside the Overload?

~~~java
public String formatPrice(int cents) {
    return formatPrice((long) cents);
}
~~~

Using the cast makes it explicit that the call delegates to the new `long` overload. It avoids ambiguity when reading code and ensures you do not accidentally recurse back into `formatPrice(int)`.

### 11.2. When Should You Not Just Delegate?

In this example, v1 and v2 behavior matches for `int` inputs. In a real API, however, there may be:

- Boundary `int` values handled differently in v2.
- Changes in rounding, timezone, or encoding.
- Changes in checked/unchecked exceptions.
- Changes in parameter semantics.
- Different side effects, retries, transactions, or ordering.

In such cases, preserving the old descriptor **is not enough**. The bridge must preserve the behavioral contract for consumers still calling the old API, or changes must be clearly announced.

## 12. Building the Fixed Library

~~~bash
javac --release 17 -encoding UTF-8 \
  -d out/lib-v2-fixed \
  src/lib-v2-fixed/com/example/catalog/PriceService.java

jar --create --file dist/catalog-v2-fixed.jar \
  -C out/lib-v2-fixed .
~~~

Inspect with `javap`:

~~~bash
javap -s -classpath dist/catalog-v2-fixed.jar \
  com.example.catalog.PriceService
~~~

Expected output contains both methods:

~~~text
public java.lang.String formatPrice(int);
  descriptor: (I)Ljava/lang/String;

public java.lang.String formatPrice(long);
  descriptor: (J)Ljava/lang/String;
~~~

The `@Deprecated` annotation alerts writers of new source code about the legacy API; it **does not remove the method from bytecode** and does not break old consumers merely because the method is marked deprecated. On JDKs earlier than Java 9, `@Deprecated`'s `since`/`forRemoval` attributes are unavailable, so source code must match the actual baseline.

## 13. Retesting With the Exact Old Consumer Artifact

This is the most important test in the exercise. **Do not recompile `client-original.jar`.**

Run:

~~~bash
java -cp "dist/catalog-v2-fixed.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

Expected output:

~~~text
1200 VND
~~~

Matrix after the fix:

| Consumer | Library | Expectation |
|---|---|---|
| Original v1-compiled JAR | v1 | PASS |
| Original v1-compiled JAR | v2 broken | FAIL |
| Original v1-compiled JAR | v2 fixed | **PASS** |
| Recompiled-v2 JAR | v2 fixed | PASS if contract matches |

If the four outcomes match expectations, the exercise has proven:

- Changing `int` to `long` **by removing the old method** breaks binary compatibility.
- Recompiling the consumer adapts its source, yet does not make the old artifact work with v2 broken.
- Preserving the exact old method descriptor allows the old consumer artifact to link successfully.
- Verifying business results is still needed after the method links successfully.

### 13.1. What Must Stay Immutable?

`client-original.jar` must keep the exact same **content/checksum** from when it was created in step 6. Accidentally rebuilding or overwriting this file invalidates the final backward binary compatibility proof.

In real teams, old consumer artifacts should come from published releases or a separately version-controlled/packaged fixture JAR, never rebuilt against the new dependency prior to each check.

## 14. Why Is `NoSuchMethodError` a `LinkageError`?

`NoSuchMethodError` is a subtype of `IncompatibleClassChangeError` in the `LinkageError` branch. It typically occurs when executing code was compiled against one API version, yet at runtime another class is provided lacking the requested binary method.

Logical illustration:

~~~text
Compile classpath:
  catalog-core 1.0.0

Consumer bytecode:
  invokes PriceService.formatPrice:(I)Ljava/lang/String;

Runtime classpath:
  catalog-core 2.0.0

Runtime symbol resolution:
  PriceService loaded
  method name = formatPrice
  descriptor = (I)Ljava/lang/String;
  matching method absent
  => NoSuchMethodError
~~~

It is not a numeric conversion failure or a missing Java object on the heap. At this stage, the JVM found the `PriceService` class, yet failed to find **the exact method** in the class/hierarchy under linking rules.

### 14.1. How Does It Differ From `NoClassDefFoundError`?

| Error | Common meaning |
|---|---|
| `NoSuchMethodError` | Class resolved, yet missing the called method with matching descriptor |
| `NoSuchFieldError` | Bytecode references a field that changed or was removed |
| `NoClassDefFoundError` | JVM lacks a needed class definition while using the class; can also stem from an earlier class initialization failure |
| `ClassNotFoundException` | A class-loading-by-name API (e.g., `Class.forName`) could not find the class |
| `IllegalAccessError` | Access or linkage change leaves code without permission to access a member/class |
| `IncompatibleClassChangeError` | Incompatible change to class/member shape, e.g., instance/static mismatch |
| `AbstractMethodError` | Call requires a method implementation, yet runtime lacks a valid implementation |
| `UnsupportedClassVersionError` | Runtime does not understand a too-new class-file version |

When debugging, read **the class name + method name + descriptor in the message**, rather than randomly changing dependencies.

## 15. Investigating When Multiple JARs at Runtime Contain the Same Class

In real applications, failure can still happen even when the new library file **has the right method**, because the JVM loads `PriceService` from **a different JAR** due to classpath/module loading.

Example:

~~~text
lib/catalog-v2-fixed.jar   (has formatPrice(int))
lib/catalog-v2-broken.jar  (has only formatPrice(long))
app/legacy-client.jar
~~~

If both library versions sit on the classpath, the class loader may pick the unintended version. Do not rely on reordering JARs as a long-term release strategy.

### 15.1. Checking Duplicate Classes and Class Load Origins

First, list JAR contents:

~~~bash
jar --list --file dist/catalog-v1.jar
jar --list --file dist/catalog-v2.jar
jar --list --file dist/catalog-v2-fixed.jar
~~~

On JDK 9+, class-loading logs can be used:

~~~bash
java -Xlog:class+load=info \
  -cp "dist/catalog-v2.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

Use `-Xlog:class+load=info` for a targeted diagnostic session since log volume can be large. Output can show the source of loaded classes; search for `com.example.catalog.PriceService` to identify which JAR actually supplied the class.

### 15.2. Printing `CodeSource` to Aid Diagnosis

If you can modify source code in a diagnostic utility:

~~~java
import com.example.catalog.PriceService;

public class SourceProbe {
    public static void main(String[] args) {
        var location =
            PriceService.class.getProtectionDomain()
                .getCodeSource();

        System.out.println(
            location == null
                ? "No CodeSource available"
                : location.getLocation());
    }
}
~~~

This snippet is a supporting aid, not conclusive evidence for every custom class loader; `CodeSource` can be `null`. In applications using fat JARs, module paths, or container class loaders, the class source may be represented differently.

## 16. Common Mistake: Putting Both v1 and v2 on the Classpath

An unclean run:

~~~bash
java -cp "dist/catalog-v1.jar:dist/catalog-v2.jar:dist/client-original.jar" \
  com.example.client.ClientMain
~~~

The outcome can be **misleading**: if the JVM loads the class from v1 first, the client passes even though broken v2 is present. Reversing the order can make it fail. Even when you know classpath order, bundling multiple versions of the same class into one loader is never a reliable compatibility solution.

In this exercise, each run must include **only one** of the v1, v2, or v2-fixed library JARs alongside exactly one client JAR. That controls variables so the root cause is clear.

### 16.1. Multiple Class Loaders Can Complicate Matters Further

In application servers or plugin systems, class loaders can isolate namespaces for identically named classes. However, "duplicate classes across two loaders" can trigger `ClassCastException`, service provider mismatches, or type identity conflicts. This exercise uses a simple classpath to isolate binary method resolution.

Do not add multiple library versions at runtime expecting loaders to automatically "pick the right version for each consumer". Side-by-side isolation requires explicit class loader/module boundary design, not a default fallback.

## 17. Recognizing the Same Bug in Gradle

A Gradle project may compile a consumer against catalog-core v1 yet resolve v2 at runtime due to another dependency or configuration. This can happen through transitive dependencies, version constraints, platforms/BOMs, or build/packaging using inconsistent dependency sets.

Gradle investigation examples:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency catalog-core
~~~

Commands are illustrative only, **not executed tests**. In multi-project builds, target the appropriate project and configuration, e.g., `:consumer:dependencies`. Also check:

- Library version on `compileClasspath`.
- Library version on `runtimeClasspath`.
- Dependencies transitively requesting a different version.
- Gradle dependency constraints and resolution strategy.
- Which JARs are actually packaged into the distribution/container.
- Whether artifacts come from an internal repository or cache.
- Whether the old consumer JAR gets rebuilt or not.

### 17.1. Compile Success Does Not Reflect the Runtime Graph

Gradle can resolve compile and runtime configurations differently. If runtime ends up with only the broken v2 library, an old consumer JAR can still throw `NoSuchMethodError` even when the new library build is green.

To catch this, include a **consumer compatibility test** taking the previously published artifact and running it against the candidate library, rather than only running unit tests inside the library module.

### 17.2. Do Not Force an Old Version as an Indefinite Workaround

Pinning to v1 can restore a service during an incident, yet if security fixes or features on v2 are needed, a sustainable upgrade path is required. The team must decide to:

- Publish v2-fixed with method bridges.
- Upgrade/rebuild all consumers in a controlled rollout.
- Release a major breaking version under contract with a migration guide.
- Use a dedicated adapter with a clear contract when the library cannot be modified.

## 18. Recognizing the Same Bug in Maven

In Maven, the dependency tree helps identify which version was actually selected:

~~~bash
./mvnw dependency:tree
~~~

For a target artifact, you can filter by group/artifact depending on the plugin version in use. Inspect parent POMs, dependency management, BOMs, and transitive resolution.

An illustrative dependency declaration:

~~~xml
<dependency>
  <groupId>com.example</groupId>
  <artifactId>catalog-core</artifactId>
  <version>2.0.0</version>
</dependency>
~~~

If a consumer JAR compiled against version 1.0.0 is dropped into an application running 2.0.0 at runtime, the dependency declaration above **does not automatically recompile the consumer binary**. Maven only resolves classpaths/artifacts; the JVM still links method descriptors from the actual bytecode present.

A passing `mvn clean verify` on new source does not replace testing the original consumer artifact. For public libraries, consider maintaining a compatibility fixture project whose binary is not automatically updated.

## 19. What Other API Changes Can Break Old Artifacts?

This exercise used `int` → `long`, yet binary breaks take many forms.

| Library change | Risk to compiled consumers |
|---|---|
| Remove/rename a public method | `NoSuchMethodError` |
| Change parameter type | Different method descriptor; possible `NoSuchMethodError` |
| Change return type | Different descriptor; possible linkage error |
| Change instance method to static or vice versa | `IncompatibleClassChangeError` |
| Remove public field or change field type | `NoSuchFieldError` |
| Narrow `public` to `private`/package-private | `IllegalAccessError` or linkage error |
| Remove a public class referenced by consumer | `NoClassDefFoundError` or loading failure |
| Change abstract/concrete hierarchy | Possible `AbstractMethodError` on invocation |
| Rename package `javax.*` to `jakarta.*` | Different type identity; old consumers need adapter or rebuild |
| Add a new overload | Usually preserves old bytecode calls if old method remains, yet can make recompiled source ambiguous |
| Change logic while keeping signature | Can break **behavioral compatibility** even while binary links fine |

These are **risk directions**, not guarantees that the JVM will always throw one exact exception regardless of hierarchy/call site. Exact outcomes depend on how the method is invoked, supertypes, class loaders, and actual metadata. Consult JLS Chapter 13 and JVMS resolution rules when exact conclusions are needed.

## 20. Adding Overloads Usually Preserves Binary Compatibility Yet Can Alter Source

Example library v1:

~~~java
public String describe(Object input) {
    return "object";
}
~~~

Library v2 keeps the old method and adds:

~~~java
public String describe(String input) {
    return "string";
}
~~~

A consumer **already compiled** against v1 calling `describe(null)` still holds a reference to `describe(Object)`. After rebuilding against v2, the compiler may select `describe(String)` because it is more specific, changing runtime behavior.

In another case, adding two unrelated overloads can make a source call `describe(null)` **ambiguous**. Thus:

- Adding overloads is generally safer for binary compatibility if the old method remains.
- Not every overload addition guarantees source/behavioral compatibility.
- Test both original binaries and source recompilation if claiming both forms of compatibility.

## 21. SemVer: Changing the Version Does Not Guarantee API Compatibility

Many libraries follow Semantic Versioning conventions:

- Patch: bug fixes, no intentional incompatible API changes.
- Minor: compatible feature additions.
- Major: breaking changes permitted when announced.

In this exercise, removing `formatPrice(int)` is **binary breaking**, even though typical source code still recompiles. Such a change normally requires a **major release** if the library follows SemVer and commits to API/ABI stability.

However, simply assigning version `2.0.0` **does not make old consumer artifacts magically work**. Versioning is how you **communicate the contract**, while binary compatibility is a technical property that must be tested.

### 21.1. How Long Should a Bridge Be Kept?

Depends on library policy:

- If the library commits to long-term binary compatibility, keep the old method until a concrete major breaking plan.
- If a major migration requiring consumer rebuilds has been announced, a bridge might not be necessary—provided there is a consumer upgrade plan.
- If the old method carries security risks, weigh deprecating/disabling per policy instead of retaining indefinitely.
- If a bridge method preserves semantics at low cost, it is usually a good way to reduce rollout risk.

Do not slap `forRemoval=true` and delete it in the very next release without a transition period and checking real consumers.

## 22. Putting Compatibility Tests Into the Library Release Pipeline

A robust pipeline for libraries with legacy consumers typically runs two independent tracks:

~~~text
Candidate catalog-core v2
        |
        +--> Library's own tests
        |       compile new sources
        |       test new API
        |
        +--> Binary consumer compatibility tests
                take client-original.jar from v1 fixture
                load candidate catalog-core v2
                invoke published API calls
                inspect linkage and behavior
                |
                +--> PASS: candidate keeps old contract
                +--> FAIL: breaking change found
~~~

The second branch must never silently rebuild the old consumer against v2. When creating binary test fixtures, build them **once against the old API**, store the artifact/checksum in a controlled location, and reuse them.

### 22.1. What Should Be a Release Gate?

| Gate | What it checks | Evidence |
|---|---|---|
| Build candidate | Library v2 compiles and packages properly | JAR + build report |
| API surface diff | How public classes/method descriptors changed | Tool report |
| Source compatibility | Whether old consumer source recompiles | Compiler report |
| Binary compatibility | Whether old consumer bytecode runs against candidate | Runtime/JUnit test |
| Behavior compatibility | Whether outputs/exceptions/side effects stay accurate | Contract tests |
| Dependency resolution | No unintended duplicate class versions | Resolved graph, artifact scan |
| JDK runtime matrix | Runs on min/supported JDKs | Runtime logs and test report |
| Release policy | Breaking changes announced/approved | Changelog/migration guide |

Projects may select different gates depending on their guarantees. Crucially, never use one gate as fake proof for another gate.

## 23. API/ABI Diff Tools

When comparing two library JARs, beyond `javap`, API/binary compatibility tools can be used, such as:

- **japicmp**: compares classes/interfaces/method descriptors and compatibility change categories between two JARs.
- **Revapi**: analyzes API changes based on configuration and policy.
- **bnd baseline**: evaluates API/package versioning in OSGi contexts where appropriate.
- **jdeps**: analyzes dependency/module relationships and references; not a complete verification tool for method-level binary compatibility across all consumers.

These tools must be configured for the plugin/tool version supporting your JDK and scoped to the public API. They do not automatically detect every breaking behavioral change.

Example policy-level requirement:

~~~text
Compare:
  catalog-v1.jar
  catalog-v2.jar

Reject release if:
  public method formatPrice:(I)Ljava/lang/String;
  disappears without an approved breaking change.

Allow release if:
  v2 keeps descriptor (I)...
  and contract test using original consumer JAR passes.
~~~

Do not treat this example as a valid configuration file for any specific plugin. Each tool has its own schema/version.

## 24. Which Artifacts Should an Automated Test Run?

To avoid false passes, the test harness should reference directly:

~~~text
Original binary fixture:
  dist/client-original.jar
    compiled with catalog-v1.jar

Candidate runtime library:
  dist/catalog-v2-fixed.jar
    built from current candidate

Runtime:
  java -cp catalog-v2-fixed.jar:client-original.jar
  com.example.client.ClientMain
~~~

If using Gradle, a custom `JavaExec` task can put both artifacts on the classpath, while avoiding:

- Putting `catalog-v1.jar` on the runtime classpath alongside the candidate.
- Automatically triggering compilation of client source against the candidate before running.
- Using a project dependency that causes Gradle to pick class files instead of the published JAR.
- Pulling a consumer fixture of the wrong version from cache.
- Running tests on a different JDK than the declared runtime.
- Checking only the exit code while business output is wrong.

If an app has multiple consumer modules, maintain a suite of **consumer fixtures** across supported versions so tests are not limited to one sample client.

## 25. Difference Between Java Bytecode Version and API Binary Compatibility

A consumer JAR compiled for Java 17 can typically run on newer JDKs supporting that class-file version, yet that **does not promise** runtime libraries preserve their binary API.

Two distinct issues:

- `UnsupportedClassVersionError`: JVM is too old to read bytecode compiled for a newer version.
- `NoSuchMethodError`: JVM can read the class, yet when resolving a method reference finds no matching binary method.

Thus, an SDK targeting Java 17 bytecode can still break a Java 17 consumer if it alters a public method. Conversely, a library keeping all method APIs intact yet built with Java 21 bytecode will fail to run on Java 17 even though the method descriptors exist.

### 25.1. `--release` Does Not Check the ABI of Packaged Dependencies

When running:

~~~bash
javac --release 17 ...
~~~

the compiler checks the Java language/API baseline for the source being compiled. It does not verify "whether library v2 keeps every method descriptor from library v1 for all previously released consumers". Knowing that requires API diffs and binary consumer tests.

## 26. Extended Exercise A: Changing the Return Type

Create a variant of library v2 (in a separate practice directory, **without overwriting the v2 already used**) with method:

~~~java
public Object formatPrice(int cents) {
    return cents + " VND";
}
~~~

Consumer source:

~~~java
String output = service.formatPrice(1200);
~~~

no longer compiles if the method genuinely returns only `Object`. The old consumer binary still requests `(I)Ljava/lang/String;`, whereas the new library provides `(I)Ljava/lang/Object;`, creating a linkage failure risk.

**Question:** Why does the return type appear in a JVM descriptor even though the Java language forbids overloading methods by return type alone?

Hint: inspect `javap -s` and method descriptor rules in the JVMS. Do not confuse source-level overload resolution rules with method representation in class files.

## 27. Extended Exercise B: Instance Method to Static

Try transforming:

~~~java
public static String formatPrice(int cents) {
    return cents + " VND";
}
~~~

in another library with the same class name. Consumer binary v1 compiled the call as an **instance invocation**, whereas the new method is **static**. This is an incompatible class/member change that can throw `IncompatibleClassChangeError` in a suitable runtime.

**Question:** Why is keeping the exact same name, parameter, and return type still not enough?

Hint: the bytecode invocation opcode (`invokevirtual` vs `invokestatic`) and method kind are part of the linkage contract.

No need to build a web app or add dependencies to test this; keep the exercise small and change one variable at a time.

## 28. Extended Exercise C: Removing a Public Class

Replace `com.example.catalog.PriceService` with a new class `com.example.catalog.PricingService` without keeping the old class. Consumer artifact v1 still references `PriceService`. Depending on the code path/class loading, the runtime can encounter `NoClassDefFoundError`.

A legacy adapter class can help:

~~~java
package com.example.catalog;

@Deprecated
public final class PriceService {
    private final PricingService delegate =
            new PricingService();

    public String formatPrice(int cents) {
        return delegate.formatPrice((long) cents);
    }
}
~~~

This example assumes `PricingService` exists with a matching method and the behavioral contract is preserved. The goal is preserving the old class + method name for consumers, not just changing source imports.

## 29. Extended Exercise D: Failures in Interfaces and Plugins

Suppose a public interface in library v1:

~~~java
package com.example.spi;

public interface PricePlugin {
    String formatPrice(int cents);
}
~~~

A plugin compiled against v1:

~~~java
public final class LegacyPricePlugin
        implements PricePlugin {

    @Override
    public String formatPrice(int cents) {
        return cents + " VND";
    }
}
~~~

If interface v2 replaces `formatPrice(int)` with `formatPrice(long)`, the old plugin binary does not magically gain an implementation of the new method. When a caller invokes the new method through the interface, linkage errors such as `AbstractMethodError` may occur depending on the exact call and hierarchy.

Solutions to consider:

- Keep the old interface method during a transition period.
- Use default methods/adapters **after analyzing semantics and binary contracts**.
- Release a plugin SPI major version with rebuild instructions.
- Test old plugin JARs distributed independently.

Interface scenarios are usually more complex than concrete class methods due to dispatch, inheritance, and default methods. Do not assume an interface bridge automatically preserves every consumer.

## 30. Why Library Unit Tests Alone Often Miss This Bug

Catalog v2's unit test might be written as:

~~~java
@Test
void formatsLargeValues() {
    PriceService service = new PriceService();
    assertEquals("1200 VND", service.formatPrice(1200L));
}
~~~

If this test is compiled together with v2, it only exercises `formatPrice(long)`. It never checks whether the method v1 previously provided—`formatPrice(int)`—is still present.

Even if the test calls `service.formatPrice(1200)` (an `int` literal), the compiler building against v2 selects the `long` method and the test still passes. **What is missing is the artifact compiled against v1.**

Therefore, library unit tests and compatibility tests are **two complementary layers**, not substitutes for each other.

## 31. Completion Criteria for Learners

After carrying out the hands-on steps in your study environment, collect:

| Check | Expected outcome |
|---|---|
| Build `catalog-v1.jar` | JAR created successfully |
| Build `client-original.jar` with v1 | JAR created successfully |
| Run original client + v1 | Prints `1200 VND` |
| Build `catalog-v2.jar` | JAR created successfully |
| Run original client + v2 | **`NoSuchMethodError`** |
| `javap` original client | References `formatPrice:(I)Ljava/lang/String;` |
| `javap` v2 | Only has `formatPrice(long)`, descriptor `(J)...` |
| Recompile client source with v2 | Succeeds |
| Run recompiled client + v2 | Prints `1200 VND` |
| Build v2-fixed | Contains both `int` and `long` methods |
| Run **original** client + v2-fixed | Prints `1200 VND` |
| Original client checksum | Unchanged between baseline and final run |

These outcomes are **expected results for the exercise**, not a report of executed tests. If your results differ, first verify the classpath contains only one library version and the original consumer JAR was not rebuilt.

### 31.1. Comprehension Check Questions

1. Why does `formatPrice(1200)` recompile against `long` yet fail to link with old bytecode?
2. What is the JVM descriptor of `formatPrice(int)`? Of `formatPrice(long)`?
3. Why can new library v2 unit tests PASS even while a v1 consumer binary FAILS?
4. Under what circumstances is it acceptable for v2 to break binary compatibility?
5. What is the difference between `NoSuchMethodError` and `UnsupportedClassVersionError`?
6. If two JARs at runtime both contain `PriceService`, why is a single passing run unreliable?
7. Is adding an overload/bridge sufficient to guarantee behavioral compatibility?
8. To prevent this bug automatically, which artifact should be kept as a fixture in CI?

## 32. Incident Investigation Report Template

~~~yaml
incident:
  title: "Legacy consumer fails after catalog-core upgrade"
  type: "BINARY_COMPATIBILITY"
  consumer:
    artifact: "client-original.jar"
    compiledAgainst: "catalog-core 1.0"
    rebuiltDuringTest: false
  runtime:
    candidateLibrary: "catalog-core 2.0"
    jdk: "record exact java -version"
  failure:
    error: "java.lang.NoSuchMethodError"
    symbol: "PriceService.formatPrice:(I)Ljava/lang/String;"
  evidence:
    v1Descriptor: "(I)Ljava/lang/String;"
    v2Descriptor: "(J)Ljava/lang/String;"
    originalConsumerChecksum: "record sha256"
    javapReport: "attach disassembly excerpt"
  remediation:
    approach: "restore legacy overload"
    candidate: "catalog-core 2.0.1"
  validation:
    baselineRun: "NOT_YET_RUN"
    incompatibleRun: "NOT_YET_RUN"
    fixedRun: "NOT_YET_RUN"
  owner: "library-maintainers"
~~~

This illustrative template must be populated with **real test results** if used in a project. Never change `NOT_YET_RUN` to PASS before evidence exists. In a real incident, also record runtime classpath, dependency graph, class loader origin, JDK vendor/build, container image, and consumer impact.

## 33. Release Process for a Library With Legacy Consumers

### Step 1 — Inventory Public API

List public classes, constructors, methods, fields, interfaces, generic signatures, and module exports. Define what constitutes a stable contract versus internal/experimental parts.

### Step 2 — Preserve Baseline Versions

Keep old releases and consumer artifacts compiled against them. Save checksums and contract test suites without rebuilding fixtures against the candidate.

### Step 3 — Build the Candidate

Produce the new JAR using the compiler/JDK matching the declared minimum runtime. Do not rely solely on an IDE build succeeding.

### Step 4 — Compare API/ABI

Use `javap` or tools such as `japicmp`/Revapi to detect removed/altered public method descriptors. Enforce explicit breaking-change policies.

### Step 5 — Run Binary Consumer Tests

Place the candidate library and original consumer JARs into a clean runtime without duplicate old library classes. Execute code paths exercising the published API.

### Step 6 — Run Source Compile Tests

Recompile consumer sources against the candidate to catch source incompatibilities. Do not use this result as a substitute for Step 5.

### Step 7 — Run Behavioral Regressions

Verify outputs, exceptions, validation, database, serialization, security, and concurrency against the consumer contract.

### Step 8 — Check Dependency Graph and Environment

Verify the runtime loads the right library/JDK/OS/class loader. Separate binary API failures from bytecode version or native dependency issues.

### Step 9 — Classify Breaking Changes

For each break, decide whether to keep a bridge, provide an adapter, release a major version, or require consumer rebuilds. Document consumer owners and rollout plans.

### Step 10 — Release Decision

Mark compatible only when corresponding gates have evidence. Publish the version, changelog, migration guide, known incompatibilities, and rollback plan when needed.

## 34. Common Misconceptions

**"If source still compiles, old binaries will definitely run."** False. This exercise demonstrated `int → long`: source recompiles, yet original bytecode still invokes the old descriptor.

**"The JVM automatically widens `int` to `long` when linking the old method."** No. Widening during Java compiler overload resolution does not replace the fixed symbolic method reference in bytecode.

**"`NoSuchMethodError` is always caused by a missing class."** No. The class may exist while lacking the exact required method descriptor.

**"Successfully rebuilding the consumer means the library is non-breaking."** That only proves consumer source can be updated/compiled; previously built artifacts can still fail.

**"Keeping the method name is enough."** No. Parameters, return descriptor, static/instance kind, and accessibility all affect linkage.

**"Adding `@Deprecated` stops old consumers from calling the method."** No. Deprecation is a compiler/documentation signal; the method remains present unless deleted.

**"Adding an overload always keeps all source consumers compatible."** No. A new overload can make overload resolution ambiguous or pick a different method upon recompilation.

**"Bumping the major version makes the runtime understand the old API."** No. Versions communicate contracts; the JVM still requires the actual classes/methods.

**"Having both v1 and v2 on the classpath guarantees every consumer gets its own version."** No. Duplicate classes in the same loader are a hazard, not a compatibility layer.

**"If API diff passes, runtime tests aren't needed."** API diffs are valuable yet cannot verify behavior, class loading, or every integration path.

**"Because the JDK is the same, binaries must be compatible."** No. The JDK and library ABI are two separate axes.

**"Keeping a compatibility bridge means behavior cannot change."** No. A bridge may delegate to new logic with different semantics, so contract tests remain necessary.

## 35. Checklist for Library Maintainers

- [ ] Identified which consumers may use old binary JARs.
- [ ] Saved catalog-core v1 and the original consumer JAR along with checksums.
- [ ] Verified the original consumer compiled against `formatPrice(int)`.
- [ ] Built v2 independently without mixing v1 classes into the v2 JAR.
- [ ] Reproduced the error using the original consumer + v2.
- [ ] Used `javap` to confirm descriptor `(I)Ljava/lang/String;`.
- [ ] Verified v2 contains only descriptor `(J)Ljava/lang/String;`.
- [ ] Distinguished source recompilation from binary runtime testing.
- [ ] Retained compatibility overloads/bridges where required by contract.
- [ ] Ran original consumer + v2-fixed without rebuilding the consumer.
- [ ] Checked output/business behavior, not just absence of exceptions.
- [ ] Verified runtime loads only one library version.
- [ ] Inspected dependency graph and class loaders when multiple artifacts exist.
- [ ] Stated Java minimum runtime and class-file version.
- [ ] Evaluated API diff and binary tests as release gates.
- [ ] Classified breaking changes, SemVer, and consumer migration policy.
- [ ] Recorded JDK/vendor/build, artifacts, checksums, and logs in the report.
- [ ] Assigned owners, changelog, rollout, and rollback/roll-forward plans if this is a production library.

## 36. Foundational References

For authoritative rules on compatibility and linking:

- **Java Language Specification, Chapter 13 — Binary Compatibility:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html
- **Java Virtual Machine Specification, Chapter 4 — Class File Format:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **Java Virtual Machine Specification, Chapter 5 — Loading, Linking, and Initializing:** https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
- **JDK `javap` command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html
- **JDK `jar` command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
- **JDK `javac` command:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

The links above use Java 21 as a stable conceptual reference. When a project uses another JDK, check command syntax and runtime support for that specific release.

## Conclusion

**A new library can break old consumer artifacts even when consumer source still recompiles cleanly.** Replacing `PriceService.formatPrice(int)` with `formatPrice(long)` without keeping the old overload leaves previously compiled consumer JARs calling descriptor `(I)Ljava/lang/String;` and risking `NoSuchMethodError`. This proves **source compatibility does not guarantee binary compatibility**.

The proper workflow is keeping the consumer artifact untouched to reproduce the failure, using `javap` to confirm method descriptors, checking the actual classpath, and then fixing the library with a bridge or executing an intentional breaking-change migration. After fixing, you must **re-run the exact old consumer artifact**, while also verifying behavioral contracts and the target JDK environment. Putting API/ABI diffs alongside binary consumer tests into your release pipeline catches issues at library release time instead of waiting for downstream services/plugins to fail at runtime.
