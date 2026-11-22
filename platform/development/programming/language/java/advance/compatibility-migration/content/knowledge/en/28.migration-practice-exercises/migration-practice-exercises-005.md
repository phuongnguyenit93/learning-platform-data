# Comparing APIs Before and After Changes Using Automated Tools

When upgrading Java, a framework, or a library shared by multiple applications, looking at two source files and remarking "not much seems to have changed" is insufficient. A method whose return type changed, an interface receiving a new abstract method, or a package no longer exported can cause consumer applications to fail compilation or hit `NoSuchMethodError` at runtime. Conversely, an implementation change that looks large yet preserves the public API may have zero impact on most consumers.

**Automated API comparison** helps identify structural differences between two library versions. Tools analyze class files, signatures, modifiers, inheritance relationships, or API metadata to generate a report of added, removed, and modified elements. In a reliable migration, that report is combined with **recompiling consumer code**, **testing previously compiled binaries**, and **behavioral testing**.

This hands-on exercise belongs to the **Practice Exercises** chapter of the **Java Advance Compatibility Migration** module. Learners will build two small JARs, run automated tools to uncover API breaks, verify each category via the compiler/runtime, and then build a quality gate applicable to a real Java library.

## 1. Objectives of the Practice Exercise

After practicing, you will be able to:

1. Distinguish **public API**, **binary interface (ABI)**, **source compatibility**, and **behavioral compatibility**.
2. Create two JARs sharing the same library coordinates with different versions and intentional API changes.
3. Use `javap` and a JAR comparison tool such as **japicmp** to collect reproducible differences.
4. Identify removed methods, return-type changes, narrowed visibility, added interface methods, and new overloads.
5. Explain why a "binary compatible" report is insufficient to prove all source consumers still compile.
6. Recompile consumers against old/new versions to detect source breaks, especially overload ambiguity.
7. Run old consumer binaries against the new library to detect linkage errors.
8. Produce an evidence-backed API differences report, classify impact severity, and integrate it into CI.
9. Recognize tool limitations around JPMS, multi-release JARs, reflection, serialization, and behavioral changes.
10. Propose ways to preserve compatibility or guide consumer migration when breaking changes are intentional.

## 2. Context: Why Compare APIs When Upgrading Java?

Suppose library `billing-api` is used by three services:

```text
billing-api 1.x
    |
    +----> checkout-service
    +----> invoice-batch
    +----> reporting-service
```

The library-owning team prepares to upgrade the JDK and framework while releasing `billing-api 2.x`. Some changes are implementation-only; others directly impact consumers:

- Changing a method's return type.
- Removing a public constructor.
- Changing a `public` method to package-private.
- Renaming a class or package.
- Adding an overload that can make existing calls ambiguous.
- Adding an abstract method to an interface that consumers implement themselves.
- Changing `module-info.java`, making a package no longer visible.
- Changing generic signatures or annotation processing contracts.

If you only build `billing-api 2.x`, all of those changes may remain completely valid for the library's own source code. What breaks resides in **the consumer's code**, which is not necessarily included in the library's unit tests.

A good pipeline needs to answer three separate questions:

| Question | Core check method |
| --- | --- |
| Where did v1 and v2 API/ABI change? | Automated tools reading both JARs, e.g., japicmp or Revapi. |
| Does old consumer source still compile with v2? | Recompile **the exact same source snapshot** against v1 and v2. |
| Do old consumer binaries still link and run with v2? | Run classes/JARs compiled from v1 against library v2, combined with ABI checks. |

Additionally, when **behavior changes while signatures stay identical**, regression/contract tests must be used. No API diff tool can automatically prove all business logic remains right.

## 3. Core Concepts Before Running Tools

### 3.1. Public API

The public API is not just a list of every method with a `public` modifier. The actual contract may also include:

- Supported public/protected types, constructors, methods, and fields.
- Generic bounds, annotations, and checked exceptions affecting source consumers.
- Interface abstract/default methods.
- Type hierarchy and subclassing/implementation capabilities.
- Exported packages and module names under JPMS.
- Public configuration keys, service interfaces, or wire schemas if part of the product contract.

JAR comparison tools generally focus on the **Java class-file/API surface**. Contracts outside bytecode, such as HTTP JSON schemas and SQL schemas, require different tools or tests.

### 3.2. ABI and Binary Compatibility

On the JVM, a method call references a name and a descriptor tied to parameter/return types. For example:

```java
public int total(int base, int tax);
```

The method descriptor has the form:

```text
(II)I
```

If the return type changes to `long`:

```java
public long total(int base, int tax);
```

The new descriptor is:

```text
(II)J
```

Consumer binaries compiled against the old descriptor can encounter `NoSuchMethodError` when run with the new JAR, even though the method name in source remains `total`.

### 3.3. Source Compatibility

A change can **preserve binary compatibility** yet still break recompiling old consumer source. For instance, adding a new overload can make a call like `format("abc")` ambiguous.

Therefore, even if a tool reports a change does not break the binary interface, check source compatibility as well, especially for:

- Overload resolution.
- Generics and type inference.
- Lambdas and method references.
- Interface implementations.
- Checked exceptions.
- Java language level and annotation processors.

### 3.4. Behavioral Compatibility

Changing tax rounding logic from "round down" to "round half-even" may not change any Java signature. An API diff reports no changes, yet invoice figures change.

Hence, reports should separate results into:

```text
API/ABI changes      -> automated checks on JAR
Source compatibility -> recompile consumer
Binary runtime       -> test old consumer binary
Behavior             -> regression/contract/integration tests
```

## 4. Tools Used in This Exercise

| Tool | Role | What must NOT be inferred from output |
| --- | --- | --- |
| `javap` (JDK) | Displays bytecode signatures, modifiers, and method descriptors. | Does not automatically classify all compatibility rules. |
| `diff` / `git diff` | Compares two text outputs of signatures. | Text diff does not fully understand Java language/JVM rules. |
| **japicmp** | Compares two JARs, identifying API changes and supported binary/source incompatibilities. | Does not guarantee all consumer sources/behaviors stay compatible. |
| **Revapi** | Analyzes API changes via extensions, filters, and policy/reporting. | Requires proper configuration of extensions, artifacts, and API scope. |
| `javac` / Maven / Gradle | Recompiles consumer source against the candidate artifact. | Passing compilation does not prove old binaries or behavior work. |
| `java` | Runs old binary client against the new library. | A few runtime calls do not cover every code path. |
| `jdeps` | Inspects static dependencies, especially JDK internal APIs or module dependencies. | Does not fully detect reflection and dynamic class loading. |

In this lab, **japicmp** is the primary API comparison tool; `javap` explains the findings; Maven builds both JARs and compiles the consumer. Revapi is introduced as an alternative/deeper option for CI.

**Tool version note:** the Maven example below pins `maven-compiler-plugin 3.13.0` and Java release 17 for illustration. For japicmp/Revapi, choose a CLI/plugin version documented by the tool itself to support the JDK/class-file version being analyzed. Do not assume an example version here is "latest" or guaranteed on every future JDK.

## 5. Lab Layout

We set up three separate projects:

```text
api-comparison-lab/
├── api-v1/
│   ├── pom.xml
│   └── src/main/java/com/example/api/
│       ├── PriceCalculator.java
│       └── PaymentPlugin.java
├── api-v2/
│   ├── pom.xml
│   └── src/main/java/com/example/api/
│       ├── PriceCalculator.java
│       └── PaymentPlugin.java
├── consumer/
│   ├── pom.xml
│   └── src/main/java/com/example/consumer/
│       ├── CheckoutClient.java
│       └── ExternalPaymentPlugin.java
└── reports/                 # Where API diff and compile logs are stored
```

`api-v1` and `api-v2` intentionally share the same Maven `groupId` and `artifactId` with different versions:

```text
com.example.lab:sample-api:1.0.0
com.example.lab:sample-api:2.0.0
```

The consumer accepts the version via a property so comparisons run **without altering source**.

### 5.1. Environment Requirements

- JDK 17 or a JDK compatible with the lab's `--release 17`.
- Maven 3.x compatible with the chosen JDK.
- A text editor to create files.
- japicmp CLI JAR from the project's official release, runnable on the chosen JDK.
- A suitable shell; illustrative commands use Bash. On Windows, PowerShell can be used with equivalent paths and commands.

Environment verification commands:

```bash
java -version
javac -version
mvn -version
```

No large framework or database is needed. The goal of the lab is isolating **Java API changes**.

### 5.2. Intentional Changes Planted

| ID | Change from v1 to v2 | Initial prediction |
| --- | --- | --- |
| A1 | `total(int,int)` return type changes from `int` to `long`. | Consumer source and binary may break. |
| A2 | `flush()` narrows from `public` to package-private. | Code outside package loses access. |
| A3 | Adds `normalize(Serializable)` alongside `normalize(CharSequence)`. | Old binary may still run; source `normalize("text")` may become ambiguous. |
| A4 | `PaymentPlugin` adds abstract method `audit()`. | Concrete consumer implementers must update. |
| A5 | Changes method implementation while keeping signature. | API diff may not report anything; behavior tests needed. |

Keep v1's consumer source untouched until the end of the comparison; editing it prior to measurement masks the source breaks we want to detect.

## 6. Creating the API v1 Project

### 6.1. File `api-v1/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.lab</groupId>
    <artifactId>sample-api</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. File `api-v1/src/main/java/com/example/api/PriceCalculator.java`

```java
package com.example.api;

public class PriceCalculator {
    public int total(int base, int tax) {
        return base + tax;
    }

    public String normalize(CharSequence value) {
        return value.toString().trim();
    }

    public void flush() {
        // V1: public API, illustrative only.
    }
}
```

### 6.3. File `api-v1/src/main/java/com/example/api/PaymentPlugin.java`

```java
package com.example.api;

public interface PaymentPlugin {
    String name();
}
```

v1 defines a simple contract: consumers call `total`, `normalize`, `flush`, and can implement the `PaymentPlugin` interface.

## 7. Creating API v2 With Changes to Detect

### 7.1. File `api-v2/pom.xml`

Same content as `api-v1/pom.xml`, changing only:

```xml
<version>2.0.0</version>
```

Keep `groupId`, `artifactId`, compiler plugin, and Java release identical to isolate API effects.

### 7.2. File `api-v2/src/main/java/com/example/api/PriceCalculator.java`

```java
package com.example.api;

import java.io.Serializable;

public class PriceCalculator {
    // A1: change return type; method descriptor changes.
    public long total(int base, int tax) {
        return (long) base + tax;
    }

    // Old method keeps the exact signature.
    public String normalize(CharSequence value) {
        return value.toString().trim();
    }

    // A3: add overload that can make consumer source ambiguous.
    public String normalize(Serializable value) {
        return value.toString().trim();
    }

    // A2: from public to package-private.
    void flush() {
        // No longer public API.
    }
}
```

### 7.3. File `api-v2/src/main/java/com/example/api/PaymentPlugin.java`

```java
package com.example.api;

public interface PaymentPlugin {
    String name();

    // A4: old concrete implementers need to add this method.
    void audit();
}
```

### 7.4. Why Does v2 Still Compile on Its Own?

There is no Java source error in changing a return type, narrowing visibility, or adding an abstract method to an interface when **compiling only library v2 itself**. Since the library does not contain legacy consumers, the v2 build can succeed.

That is the problem API comparison and consumer recompilation solve.

## 8. Building an Unchanged Consumer Between Both Versions

### 8.1. File `consumer/pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.lab</groupId>
    <artifactId>sample-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <api.version>1.0.0</api.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.example.lab</groupId>
            <artifactId>sample-api</artifactId>
            <version>${api.version}</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

The Maven property `api.version` allows switching the dependency version **without modifying Java files**. This is required for a valid source compatibility test.

### 8.2. File `consumer/src/main/java/com/example/consumer/CheckoutClient.java`

```java
package com.example.consumer;

import com.example.api.PriceCalculator;

public final class CheckoutClient {
    public static void main(String[] args) {
        PriceCalculator calculator = new PriceCalculator();

        // Written for v1: total returns int.
        int total = calculator.total(100, 20);

        // String implements both CharSequence and Serializable.
        String label = calculator.normalize("  item  ");

        // Public in v1.
        calculator.flush();

        System.out.println(total + " / " + label);
    }
}
```

### 8.3. File `consumer/src/main/java/com/example/consumer/ExternalPaymentPlugin.java`

```java
package com.example.consumer;

import com.example.api.PaymentPlugin;

public final class ExternalPaymentPlugin implements PaymentPlugin {
    @Override
    public String name() {
        return "external";
    }
}
```

This consumer uses v1 APIs in valid ways. The goal is **not editing the source during comparison**, even knowing v2 will fail.

## 9. Building Both Artifacts and Baseline Consumer

From `api-comparison-lab`:

```bash
mvn -f api-v1/pom.xml clean install
mvn -f api-v2/pom.xml clean install
```

Both JARs are generated at standard Maven paths:

```text
api-v1/target/sample-api-1.0.0.jar
api-v2/target/sample-api-2.0.0.jar
```

Each is installed into the local Maven repository under its own version without overwriting the other.

### 9.1. Compiling Consumer Against v1

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile
```

Expected outcome: **BUILD SUCCESS**. `CheckoutClient` and `ExternalPaymentPlugin` are valid against API v1.

### 9.2. Saving Baseline for Comparison

You can save logs or artifacts in the exercise's `reports` directory:

```bash
mkdir -p reports

mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile > reports/consumer-v1-compile.log 2>&1
```

This example uses Bash redirection. In CI, also record the toolchain/JDK, commit, JAR checksums, and dependency graph; a compiler log alone is insufficient to prove the build used the right candidate.

### 9.3. Do Not Rush to Compile Consumer Against v2

First, gather the **API diff** from the two JARs to predict which errors may appear. That is the purpose of running automated tools first.

## 10. Inspecting Class Files With `javap`

`javap` ships with the JDK and is useful when dedicated tools are not installed yet or when verifying a failing method descriptor.

### 10.1. Extracting v1 Public API

```bash
javap -classpath api-v1/target/sample-api-1.0.0.jar \
  -public -s \
  com.example.api.PriceCalculator \
  > reports/price-v1.txt
```

### 10.2. Extracting v2 Public API

```bash
javap -classpath api-v2/target/sample-api-2.0.0.jar \
  -public -s \
  com.example.api.PriceCalculator \
  > reports/price-v2.txt
```

### 10.3. Comparing Outputs

```bash
diff -u reports/price-v1.txt reports/price-v2.txt
```

This is an **automated text comparison**. Expected output shows:

- `total(int,int)` changed return type `int` → `long`.
- New method `normalize(java.io.Serializable)` appeared.
- `flush()` is no longer in v2's **public API view**.

To verify `flush()` still exists but is non-public, run:

```bash
javap -classpath api-v2/target/sample-api-2.0.0.jar \
  -p -s \
  com.example.api.PriceCalculator
```

`-p` displays non-public members too. Note this is for **inspection**, not a recommendation to call non-public APIs in consumers.

### 10.4. Inspecting the Interface

```bash
javap -classpath api-v1/target/sample-api-1.0.0.jar \
  -public com.example.api.PaymentPlugin

javap -classpath api-v2/target/sample-api-2.0.0.jar \
  -public com.example.api.PaymentPlugin
```

v2 added abstract method `audit()`. This finding suggests checking consumer classes implementing the interface.

### 10.5. Limitations of `javap + diff`

Text comparison lacks sufficient semantic knowledge to determine:

- Does a newly added method make overload resolution ambiguous?
- To what extent does a generic signature change break source compatibility?
- Is a subclass method inherited/overridden per JVM rules?
- Which specific consumers are affected by an interface change?
- Is a public type no longer accessible due to JPMS?
- Are third-party classes impacted by transitive dependencies?

Therefore, `javap` is a useful observation step, but **does not replace** japicmp/Revapi or consumer compilation tests.

## 11. Comparing APIs With japicmp

### 11.1. What Does japicmp Do?

**japicmp** compares two versions of a Java library at the JAR/class-file level, focusing on API differences and the binary/source compatibility information supported by the tool.

It can detect many types of changes, such as:

- Added, removed, or modified classes/interfaces.
- Added or removed methods/constructors/fields.
- Visibility/modifier changes.
- Return type or parameter type changes.
- Hierarchy/interface changes.
- Certain generic signature changes and compatibility categories classified by the tool.

Exact coverage depends on version, options, and the scope of classes analyzed. Do not assume every "compatible" report is an absolute guarantee across all JDKs/consumers.

### 11.2. Preparing the CLI

Obtain the **japicmp CLI artifact** from the project's official release channel, select a version documented to support the lab's JDK, and verify it runs.

In this guide, the notation:

```text
/path/to/japicmp-CLI.jar
```

represents the path to the CLI JAR containing required dependencies for your chosen japicmp release (some releases ship a "jar-with-dependencies" distribution). Do not use that literal placeholder as an actual filename.

Check usage with:

```bash
java -jar /path/to/japicmp-CLI.jar --help
```

### 11.3. Running Comparison Between Two JARs

```bash
java -jar /path/to/japicmp-CLI.jar \
  --old api-v1/target/sample-api-1.0.0.jar \
  --new api-v2/target/sample-api-2.0.0.jar
```

If your CLI version supports `--only-modified`, use it to reduce noise:

```bash
java -jar /path/to/japicmp-CLI.jar \
  --old api-v1/target/sample-api-1.0.0.jar \
  --new api-v2/target/sample-api-2.0.0.jar \
  --only-modified
```

Syntax and option names must be checked against `--help` of **the exact release**. Never guess an option name from another version when configuring CI.

### 11.4. Saving the Report

```bash
java -jar /path/to/japicmp-CLI.jar \
  --old api-v1/target/sample-api-1.0.0.jar \
  --new api-v2/target/sample-api-2.0.0.jar \
  --only-modified \
  > reports/japicmp-api-diff.txt
```

This command saves stdout. If the CLI is configured to fail the build with a non-zero exit code on incompatibilities, your shell/CI must handle that exit code per policy; in this exercise where breaking changes are intentional, a non-zero status may be the **expected gate outcome**, not a reason to tweak the tool.

### 11.5. Interpreting the Report

The report is expected to reflect:

| ID | Created change | Meaning |
| --- | --- | --- |
| A1 | `total(int,int)` no longer has an `int`-returning signature; v2 has `long`-returning signature. | Old binary clients may invoke a descriptor that no longer exists. |
| A2 | `flush()` narrowed visibility. | Callers outside the package no longer have v1 access. |
| A3 | Added overload `normalize(Serializable)`. | Old method was not removed, yet source compilation needs separate verification. |
| A4 | `PaymentPlugin` added abstract `audit()`. | External implementers need attention. |
| A5 | Changed implementation without changing API signature. | API diff may miss behavioral regressions. |

**This is not verbatim output from a specific japicmp release.** Exact symbols, severity levels, and binary/source compatibility labels depend on the tool and version. When doing the exercise, read **the actual report**, mapping each line to the methods/classes in the JARs.

### 11.6. Scope Filtering and Dependencies

If an API JAR contains many internal packages, configure include/exclude filters supported by the tool to focus solely on the committed API.

However, **accidentally filtering out a public package** can mask a breaking change. Define API boundaries before applying filters. Furthermore, if an API class inherits from or references a type in another dependency, the tool may need an extra classpath to analyze accurately. Do not carelessly turn on "ignore missing classes" and treat the report as complete.

## 12. Which Findings Are Binary Breaking Changes?

### 12.1. Changing Return Type Can Change the JVM Descriptor

v1:

```text
public int total(int, int)
descriptor: (II)I
```

v2:

```text
public long total(int, int)
descriptor: (II)J
```

Consumer binaries compiled against v1 reference the old descriptor. If runtime provides only v2, the JVM may fail to locate that method signature, leading to `NoSuchMethodError`.

Merely seeing the same `total` name in source code is not enough. This is why a tool that inspects class files beats comparing method names with `grep`.

### 12.2. Narrowing Visibility

`public void flush()` in v1 versus package-private `void flush()` in v2 is an accessibility change. Old consumers in other packages are no longer permitted to invoke the method if only v2 is present.

When recompiling source with v2, diagnostics typically mention the member is "not public" or "cannot be accessed from outside package". With old consumer binaries, `IllegalAccessError` can occur.

### 12.3. Adding an Abstract Method to an Interface

`PaymentPlugin` v2 adds `audit()`. A consumer source class implementing v1 without `audit()` may no longer compile against v2.

Regarding binary compatibility, the behavior of **adding an abstract method to an interface** must be distinguished from source compatibility: the old binary class may still load, yet invoking the new method when the implementation lacks it can lead to `AbstractMethodError`. Do not naively equate "adding an abstract method" with "removing a method".

### 12.4. Adding Overloads and Binary Compatibility

v2 keeps:

```java
public String normalize(CharSequence value)
```

and adds:

```java
public String normalize(Serializable value)
```

Binaries compiled with v1 still reference the `normalize(CharSequence)` overload. They do not re-run overload resolution when the JVM invokes the method.

However, when **recompiling source** `normalize("  item  ")` against v2, the compiler sees `String` implements **both `CharSequence` and `Serializable`**. Neither overload type is a subtype of the other to make one more specific, so the call can become ambiguous.

This is the clearest illustration of why **binary compatible does not necessarily mean source compatible**.

## 13. Recompiling the Consumer to Find Source Compatibility Breaks

### 13.1. Baseline v1

If not already run or to capture cleanly:

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile
```

Expected outcome: consumer source compiles cleanly.

### 13.2. Candidate v2

Keep both consumer Java files unchanged, altering only the dependency version:

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=2.0.0 \
  clean compile
```

This compile is **designed to fail**. Expected diagnostics may include:

1. `int total = calculator.total(...)`: `long` cannot be assigned to `int` implicitly; incompatible types or possible lossy conversion error.
2. `calculator.normalize("  item  ")`: ambiguous overload.
3. `calculator.flush()`: method is no longer public to callers in another package.
4. `ExternalPaymentPlugin`: class fails to implement the new abstract method `audit()`.

Exact diagnostic wording/formatting varies by compiler and JDK, while the underlying failures are governed by Java type/access rules.

### 13.3. Interpreting Results Properly

| v1 compile | v2 compile | Conclusion |
| --- | --- | --- |
| PASS | FAIL | Source compatibility regression exists in the pinned consumer and environment. |
| PASS | PASS | No source break found in compiled sources; does not prove the entire ecosystem. |
| FAIL | FAIL | Invalid baseline or pre-existing blocker; do not blame all errors on v2. |
| FAIL | PASS | Candidate may have resolved an error, yet you must explain why baseline failed. |

**Do not edit the consumer before compiling against v2.** If you already edited code to cast `(int) total`, cast for `normalize`, or add `audit()`, that becomes a **migration readiness** test—no longer a test of whether v2 preserves source compatibility for unmodified old consumers.

### 13.4. Distinguishing Source Breaks From Infrastructure Failures

A non-zero Maven exit code is not automatically an API regression. Classify:

- Compiler diagnostic pointing at Java source/API: candidate source break.
- Dependency resolution failure: failed to fetch the right artifact version.
- Plugin/JDK incompatibility: toolchain error.
- Annotation processor crash: processor compatibility.
- JDK class-file mismatch: dependency requires a newer Java version.
- Repository authentication/network issue: environment error.
- Skipped test tasks: coverage does not match compile gate expectations.

When pinpointing causes, inspect the dependency tree or effective POM to see which version was actually selected.

## 14. Testing Old Binary Clients Against the New Library

### 14.1. Preserving the v1-Compiled Binary

After compiling the consumer cleanly against v1, preserve its output folder or package a JAR. Example:

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile
```

Output contains:

```text
consumer/target/classes/com/example/consumer/CheckoutClient.class
```

**Do not re-run `clean compile` against v2** when testing old binaries; that command deletes or overwrites the output.

### 14.2. Running Old Binaries With the v2 JAR

On Bash/Unix, the classpath separator is `:`:

```bash
java -cp \
  consumer/target/classes:api-v2/target/sample-api-2.0.0.jar \
  com.example.consumer.CheckoutClient
```

On Windows, use `;` in the classpath, for example:

```powershell
java -cp "consumer\target\classes;api-v2\target\sample-api-2.0.0.jar" com.example.consumer.CheckoutClient
```

No Maven dependency resolution is needed here because the lab has a single simple API JAR.

Expected result: when the JVM reaches the `total(int,int)` call, the old binary asks for an `int`-returning descriptor, whereas the v2 JAR provides only a `long`-returning descriptor. Typical error:

```text
java.lang.NoSuchMethodError: ...
```

That is **binary linkage** evidence, distinct from compiler errors when recompiling against v2 source.

### 14.3. Why Is a Separate Runtime Pass Needed?

If you recompile the consumer with v2, the compiler emits the new reference descriptors. Running that newly built binary eliminates certain linkage failures that occur solely with older binaries.

To catch binary compatibility breaks, pin **consumer class files compiled against v1**, then swap the library JAR at runtime.

### 14.4. Limitations of Smoke Tests

A single execution of `CheckoutClient` exercises only a subset of methods. It does not prove the entire binary contract. API comparison tools help detect broader structural changes; integration tests continue verifying real call paths.

## 15. Fixing the API to Preserve Phased Compatibility

### 15.1. Keep the Old Method, Add a New Differently Named Method

If the library wants to widen calculation to `long`, instead of changing return type in place it can:

```java
public class PriceCalculator {
    @Deprecated
    public int total(int base, int tax) {
        return Math.addExact(base, tax);
    }

    public long totalLong(int base, int tax) {
        return (long) base + tax;
    }
}
```

`Math.addExact` in this example may throw `ArithmeticException` on overflow. If v1 used wraparound `int` addition, that is a **behavioral change**, so API compatibility requires a behavioral contract review too.

If the goal is preserving exact v1 semantics, the old method's implementation must honor the committed contract; never arbitrarily change behavior just to illustrate type widening.

### 15.2. Avoid Potentially Ambiguous Overloads

Instead of adding `normalize(Serializable)` alongside `normalize(CharSequence)`, consider a differently named method or designing the API with a clean hierarchy:

```java
public String normalize(CharSequence text);
public String normalizeSerialized(Serializable value);
```

Do not treat "merely adding a method" as guaranteed source-compatible. Test against a consumer corpus before release.

### 15.3. Keep Old Public Methods While Consumers Remain

If `flush()` was public in v1, narrowing visibility can break both source and binary clients.

You can keep the method public as an adapter/deprecated method during the compatibility window while moving internal logic to a separate method, scheduling removal for a future major release.

### 15.4. Add Default Methods When Appropriate

If new functionality must be added to `PaymentPlugin` without immediately forcing all legacy implementations to update, one option is a default method:

```java
public interface PaymentPlugin {
    String name();

    default void audit() {
        // Default must have accurate and safe semantics.
    }
}
```

This keeps many source implementers compiling. However, default methods carry risks when a class implements multiple interfaces with conflicting methods, or when default behavior does not fit business rules. Consumer recompilation and behavioral testing remain required.

### 15.5. Intentional Breaking Changes

Sometimes maintaining source/binary compatibility is unnecessary (e.g., a major API rewrite with an explicit migration window). Even then:

- API diff tools still need to run to identify **all changes**.
- Reports must distinguish accepted breaks from unintended breaks.
- Have a migration guide and consumer owners.
- Have tests proving **updated** consumers build/run properly.
- Have versioning and release notes.
- Have a rollback plan aligned with API/data changes.

Never turn off all quality gates simply because a major version permits breaking changes.

## 16. Revapi and Extended Comparison Strategies

### 16.1. When to Consider Revapi?

**Revapi** is an API change analysis ecosystem featuring extensions and filters. It often fits when a project wants to:

- Compare APIs across artifacts/releases.
- Define policies over permitted changes.
- Exclude certain implementation details per contract.
- Embed reports/checks into Maven builds.
- Manage an allowlist of accepted differences with justifications.

For projects with strict release policies, it can complement or replace japicmp.

### 16.2. What Must Be Configured Before Using

With Revapi or another API analyzer, clearly define:

1. Old and new artifacts: group/artifact/version/file/checksum.
2. Java API extension used and compatible version.
3. Committed public/protected API surface.
4. Dependencies needed by the analyzer to resolve type hierarchies.
5. Filters excluding generated/internal code if truly outside the contract.
6. Severity/policy for binary/source changes.
7. Suppression/waiver mechanism with owners and reasons.
8. Outputs collected by CI and how the gate fails.

Plugin/extension syntax varies across releases; in this lab, do not copy a hypothetical plugin config that has not been verified against the installed version. Official docs and `--help` of the exact release are the authority for CI parameters.

### 16.3. Comparing japicmp and Revapi

| Question | japicmp | Revapi |
| --- | --- | --- |
| Compares Java classes/JARs before–after | Yes, core focus. | Yes, via Java API analysis extension. |
| Classifies binary/API differences | Yes. | Yes, per extension/rule sets. |
| Build/CI integration | CLI and plugins depending on setup. | Plugins/extensions for builds/policies. |
| Excludes/filters | Configured per tool. | Supports filters/transformations. |
| Checks business behavior | No. | No. |
| Proves all consumer sources compile | No. | No; must recompile corpus. |

Do not choose a tool merely by the number of "compatible/incompatible" labels in output. Prioritize what fits your Java baseline, API policy, build system, and team maintainability.

## 17. API Diff in CI: From Report to Quality Gate

### 17.1. Minimum Pipeline

```text
Build candidate library
         |
         v
Verify artifact identity / checksum
         |
         v
Compare old release JAR vs candidate JAR (japicmp/Revapi)
         |
         +------> Generate machine-readable/human-readable report
         |
         v
Check binary/source policy
         |
         v
Recompile representative consumer snapshots
         |
         v
Run old consumer binary against candidate
         |
         v
Integration / contract / runtime tests
         |
         v
Release decision + migration notes
```

Each step has a distinct scope. Even if the CLI report detects no binary breaks, **consumer compilation and behavioral tests must still run** per the library's commitments.

### 17.2. Pinning an Immutable Baseline

A gate is untrustworthy if `old` points to an overwritten SNAPSHOT while `new` points to a source branch different from the published artifact.

Record:

```text
Library:
Old coordinate:
Old checksum:
New coordinate/file:
New checksum:
Source commit:
JDK:
Analyzer + version:
Analyzer config:
Consumer corpus revision:
Report location:
CI result:
```

When using a Maven artifact repository, prefer release versions or candidate artifacts with immutable checksums/identifiers.

### 17.3. Running the CLI in CI

If your chosen japicmp release supports options that fail on binary incompatibility, you can enforce a policy like:

```bash
java -jar /path/to/japicmp-CLI.jar \
  --old api-v1/target/sample-api-1.0.0.jar \
  --new api-v2/target/sample-api-2.0.0.jar \
  --error-on-binary-incompatibility
```

**Verify exact option names via `--help` of your specific japicmp version before putting them in CI.** Different tool versions or plugins may have different option/configuration names.

In this lab, breaking changes are intentional so the binary compatibility quality gate is **expected to fail**. For production libraries, that failure blocks the release unless policy permits the break or an approved waiver exists.

### 17.4. Do Not Automatically "Fail Every Difference"

Adding a public method is often a valid change. Changing internal implementations may also leave the public API untouched.

A tiered policy might look like:

- **Block:** removing/narrowing public API, incompatible descriptor changes when the release commits to ABI stability.
- **Review:** adding overloads, changing generic bounds, adding abstract/default methods, changing annotation contracts.
- **Information:** additive new APIs, planned deprecations.
- **Separate gate:** behavior, serialization/schemas, security, and performance.

Avoid overly blunt rules that push the team into routinely suppressing warnings just to get builds green.

### 17.5. Waivers Require Evidence

Template:

```text
Change ID: API-202
Type: Return type int -> long
Public symbol: com.example.api.PriceCalculator.total(int,int)
Detected by: japicmp
Affected consumers: checkout-service, invoice-batch
Decision: Breaking change accepted for major v2
Migration: Replace call with totalLong or adapt type
Owner: API team
Approval: Architecture/release owner
Expiry/review: Before next release line
Verification: Consumer recompilation + runtime test reports
```

A waiver is only valid when the specific symbol/change has been evaluated. Avoid turning off the entire analyzer or ignoring all incompatibilities after one break gets approved.

## 18. Adding Consumer Recompilation to CI

### 18.1. Consumer Corpus

When multiple projects use a library, curate a list of representative consumers:

- Consumers frequently calling the public API.
- Consumers extending classes/implementing interfaces.
- Consumers at differing Java source levels.
- Consumers running on classpath and module path.
- Consumers using annotation processors/codegen.
- Business-critical production consumers.
- Consumers built in other JVM languages if within support scope.

Pin each consumer's commit to hold source constant between baseline and candidate runs.

### 18.2. Two Compile Passes

For a Maven consumer in the lab:

```bash
mvn -f consumer/pom.xml \
  -Dapi.version=1.0.0 \
  clean compile

mvn -f consumer/pom.xml \
  -Dapi.version=2.0.0 \
  clean compile
```

The second command failing is a meaningful signal **only when the baseline pass succeeded in the same environment**.

When multiple consumers run concurrently, prevent them from overwriting each other's outputs, mutable local snapshots, and reports. Use isolated workspaces or a stable artifact repository when needed.

### 18.3. Why Not Fix Source Before Measuring?

If the application has already been migrated to v2 with updated call sites, compiler success only answers:

> "Does the consumer **after migration** compile against v2?"

It does not answer:

> "Does API v2 stay compatible with **unmodified v1 consumers**?"

Both answers are useful, yet they belong to two different gates.

### 18.4. Tracking Test Coverage Scope

If the baseline corpus consists of 25 consumers while the candidate job compiles only 8 consumers, never report an overall PASS.

Reports should include:

```text
planned_consumers
executed_consumers
baseline_pass
candidate_pass
source_break
environment_error
skipped_with_reason
skipped_unexpected
```

A consumer skipped due to missing credentials or a missing artifact is not a consumer that passed compatibility.

## 19. API Diff Edge Cases Requiring Closer Inspection

### 19.1. Generics and Type Erasure

Example:

```java
// v1
public java.util.List<Number> values();

// v2
public java.util.List<Integer> values();
```

Both JVM descriptors still erase their return type to `java.util.List`, yet source:

```java
java.util.List<Number> result = api.values();
```

is no longer valid under v2 because `List<Integer>` is not a subtype of `List<Number>`.

Tools inspecting generic signatures may warn about the difference, while **recompiling consumers is the direct test** for specific type inference/assignment issues.

### 19.2. Checked Exceptions

Example v1:

```java
public void save();
```

v2:

```java
public void save() throws java.io.IOException;
```

Adding a checked exception can break source consumers if callers neither catch nor declare `throws`. JVM method descriptors do not encode checked exceptions the way the compiler enforces them on source.

This is a classic example of the gap between **source-level contracts** and **binary linkage**.

### 19.3. Method References and Lambdas

When adding an overload, a method reference like:

```java
java.util.function.Function<String, String> f =
        calculator::normalize;
```

can encounter different overload resolution/type inference rules than a direct method invocation. Test against real consumer source.

### 19.4. Inheritance and Default Methods

If a library adds an abstract method to an interface, consumer classes not implementing it can fail recompilation. If it adds a default method, conflicts may arise between two interfaces implemented by a consumer.

An API diff showing only "method added" is not enough to conclude all implementers are safe.

### 19.5. Protected API

A library may commit to supporting external subclassing. In that case, `protected` constructors and methods are part of the source/binary contract.

Do not apply an API filter showing only `public` methods while dropping all `protected` members if the project has extension/subclass consumers.

### 19.6. Public API Exposing Transitive Dependencies

A public method may return a type from a third-party library:

```java
public com.vendor.json.Document parse(String source);
```

If that dependency undergoes a major upgrade or relocation, consumers can suffer breaking changes even though the main library's method name did not change.

Document transitive dependency API types, compare effective dependency graphs, and inspect published POM/module metadata.

## 20. Module System (JPMS) Is Also Part of Compatibility

### 20.1. `exports` and Java Source

A modular JAR has:

```java
module com.example.api {
    exports com.example.api;
}
```

If v2 drops the export or renames the module, source consumers can fail compilation on the module path even while the `.class` remains inside the JAR.

For accurate comparison, inspect `module-info.class` and module descriptors alongside class-level API diffs.

### 20.2. Inspecting Descriptors

```bash
jar --describe-module \
  --file api-v1/target/sample-api-1.0.0.jar

jar --describe-module \
  --file api-v2/target/sample-api-2.0.0.jar
```

In **the current lab**, neither JAR contains `module-info.class`, so output may show automatic module metadata if placed on the module path. Do not mistake that for a deliberately authored explicit module descriptor.

### 20.3. Ordinary Access vs Deep Reflection

- `exports` governs access to public types/members from eligible modules.
- `opens` permits deep reflection into a package per policy.
- `--add-exports` and `--add-opens` are overrides for specific cases.

API comparison based on public/protected class signatures may fail to catch that a serializer framework will throw `InaccessibleObjectException` at runtime because the target module did not open the package.

When releasing modular libraries, add real reflection/framework tests rather than relying on source compilation alone.

### 20.4. Multi-Release JARs

A library may contain:

```text
com/example/api/PriceCalculator.class
META-INF/versions/17/com/example/api/PriceCalculator.class
META-INF/versions/21/com/example/api/PriceCalculator.class
```

Different JDKs can load different class variants. When comparing APIs, check whether the tool understands multi-release JARs and which view of the artifact it analyzes.

If a product commits to running on Java 11, 17, and 21, never conclude compatibility from analyzing only the root entries or a single JDK. Choose an appropriate tool/matrix and compile/run consumers across all supported JDKs.

## 21. Serialization, SPI, and Reflection Lie Outside Signature Diffs

### 21.1. Java Serialization

A library can keep all public method signatures intact while renaming classes, altering `serialVersionUID`, or changing serialized object layouts. Data persisted under v1 may become unreadable in v2.

Migration tests with **real v1 serialized fixtures** are required, not just comparing method signatures.

### 21.2. `META-INF/services` and `ServiceLoader`

A service provider can be registered via:

```text
META-INF/services/com.example.spi.Provider
```

If the new JAR lacks the resource or contains a wrong provider name, `ServiceLoader` will fail to find the implementation. Class-level API diff tools may report nothing because the `.class` still exists.

When shading/relocating dependencies during migration, inspect service metadata and run real tests through `ServiceLoader.load(...)`.

### 21.3. Reflection by Class Name

Example:

```java
Class<?> type = Class.forName(configuredProviderClass);
```

Class names can reside in properties, YAML, XML, DBs, or environment variables. If a package is renamed, source compilation may still succeed while runtime throws `ClassNotFoundException`.

Resource/configuration compatibility tests and an explicit alias/migration list are necessary.

### 21.4. Wire Schemas

JSON/Avro/Protobuf/HTTP contracts are not fully verified by Java API diffs. If a Java DTO keeps the same public getters yet serialization config renames a property, clients can still break.

Use schema diffs, consumer-driven contracts, and golden payload fixtures matching the real system.

## 22. Comparing APIs When Upgrading JDK or Framework

### 22.1. Isolating Library Changes From Compiler Changes

To isolate an API break caused by the library:

```text
Consumer source S fixed
Compiler/JDK E fixed
Lib v1 -> compile
Lib v2 -> compile
```

To isolate JDK impact:

```text
Consumer source S fixed
Lib version L fixed in supported combination
Old JDK -> compile
New JDK -> compile
```

Only then run the final combination `New JDK + new lib`. Changing JDK, compiler, BOM, and library simultaneously can make compiler errors impossible to trace back.

### 22.2. `--release` and Minimum Java Version

Example:

```bash
javac --release 17 \
  -cp api-v2/target/sample-api-2.0.0.jar \
  -d out \
  path/to/Consumer.java
```

`--release` constrains source/target and Java SE APIs during compilation. It **does not automatically guarantee** every third-party dependency runs on a Java 17 runtime.

In CI, record the JDK running the compiler, the Java release target, the JDK running tests, and the Java runtime in production simultaneously.

### 22.3. Jakarta EE Namespace Changes

A framework major upgrade may change source APIs from `javax.persistence`/`javax.servlet` to `jakarta.persistence`/`jakarta.servlet`. This is a Java API ecosystem and dependency shift, making API diffs and recompilation tests valuable.

However, **do not replace every `javax.*` with `jakarta.*`**; Java SE packages such as `javax.sql` retain their names. Follow the exact migration guide for your framework and target version.

### 22.4. Binary Clients Before Upgrading

An application compiled under Java 11 may run on newer JVMs if bytecode/dependencies are compatible, though this is not guaranteed in every case due to removed APIs, internal access restrictions, class loaders, and framework changes.

Use API diffs to evaluate dependency versions, then test old binaries on the new runtime and watch for errors like:

```text
NoSuchMethodError
NoClassDefFoundError
IllegalAccessError
IncompatibleClassChangeError
UnsupportedClassVersionError
```

Do not lump all of these errors into one cause. They may reflect distinct classpath, API change, visibility, or JVM version issues.

## 23. API Comparison Report Template

A good report does not merely print "breaking: yes/no". It links changes to consumers and concrete actions:

| ID | API symbol | Change | Risk category | Affected consumer | Decision |
| --- | --- | --- | --- | --- | --- |
| API-01 | `PriceCalculator.total(int,int)` | Return `int` → `long` | Binary/source break | Checkout | Keep adapter or major migration. |
| API-02 | `PriceCalculator.flush()` | Public → package-private | Binary/source access break | Checkout | Preserve public contract or update client. |
| API-03 | `normalize(Serializable)` | Added overload | Source ambiguity risk | Checkout | Rename API or adjust overload. |
| API-04 | `PaymentPlugin.audit()` | Added abstract method | Implementer source break | External plugins | Default method or migration guide. |
| API-05 | Behavior `total` | Logic changed if any | Behavioral | Billing consumers | Dedicated regression tests. |

Add governance fields:

```text
Library coordinates:
Old version/checksum:
New version/checksum:
JDK/compiler:
Analyzer + version:
Analyzer configuration:
Build/dependency resolution:
Consumer corpus:
Report artifact:
Decision/owner:
Waiver/migration ticket:
Verification evidence:
```

### 23.1. Severity Classification

- **Blocker:** unplanned breaking change to an API committed to binary compatibility, or critical consumer fails compilation.
- **High:** planned breaking change lacking a migration path for critical consumers.
- **Medium:** mechanically fixable change with a clear plan.
- **Info:** additive API, deprecation, or documented change not breaking contracts within defined scope.

Severity depends on **release policy and API usage footprint**, not just a tool's label.

### 23.2. Precision in Conclusion Phrasing

Use exact phrasing:

- "No binary incompatibilities detected within the scope of JARs inspected by the analyzer."
- "Consumer corpus 12/12 compiled cleanly on JDK 17 against API v2."
- "Old consumer binary passed 5 integration scenarios."
- "No verification data available for external plugin consumers."
- "Serialization compatibility has not been tested yet."

Never write "the library is 100% compatible" based solely on a single japicmp report.

## 24. Common Mistakes When Using API Diff Tools

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| Empty report despite source edits | Only implementation/private code changed, or wrong JARs compared. | Verify checksums, `jar tf`, and class signatures. |
| Empty report yet consumer fails compilation | Overload/generics/processor/JPMS not caught by rules. | Recompile consumer; inspect compiler diagnostics. |
| API diff reports class removed | Class relocated/shaded or entry missing from artifact. | Check FQCN, packaging, and include/exclude filters. |
| Analyzer missing-class error | Missing dependency classpath/type hierarchy. | Supply appropriate dependencies; do not ignore by default. |
| Results vary across CI jobs | Mutable SNAPSHOT, dependency cache, or differing JDK/tool version. | Pin artifacts and toolchains/checksums. |
| Binary diff passes yet runtime throws `NoSuchMethodError` | Runtime loads a different JAR or tool skipped an API. | Print class origin, dependency graph, and `javap`. |
| Consumer compile fails on new JDK | JDK/toolchain/release incompatibility. | Run matrix isolating JDK and library. |
| CI reports PASS while few consumers ran | Jobs skipped or corpus failed to load completely. | Track planned/executed counts. |
| API report flooded with internal changes | Filters do not reflect API policy. | Categorize packages; retain true protected/public API. |
| Suppressions hide new breaking changes | Waiver too broad or lacks expiration. | Narrow to exact symbol/change and review. |
| Same-version JARs differ in content | Overwritten SNAPSHOT/local install. | Use immutable coordinates/checksums. |
| v2 source compiles yet old client fails | Recompilation emits new bytecode; old binary remains mismatched. | Run binary client compiled against v1. |

## 25. Extended Exercises

### Exercise 1: Changing Generics

Change an API from:

```java
public java.util.List<Number> values();
```

to:

```java
public java.util.List<Integer> values();
```

Then:

1. Use `javap -s` to inspect the descriptor in both versions.
2. Use japicmp to check generic signature differences if supported by the tool.
3. Create a consumer assigning the result to `List<Number>`.
4. Compile baseline/candidate and record results.
5. Explain why erasure can make binary compatibility differ from source compatibility.

### Exercise 2: Changing Checked Exceptions

v1:

```java
public void send();
```

v2:

```java
public void send() throws java.io.IOException;
```

Compile a consumer having a `process()` method that neither catches nor declares `IOException`. Compare API diff and compiler outputs. Explain why checked exceptions belong to the source contract even though they do not alter the JVM method descriptor like parameter/return types do.

### Exercise 3: Testing Module Descriptor APIs

Create a modular library containing:

```java
module com.example.lab.api {
    exports com.example.api;
}
```

v2 removes the `com.example.api` export. Use `jar --describe-module` to observe the change and compile a named-module consumer. Observe that the class may still exist inside the JAR while consumer source can no longer see the package.

### Exercise 4: Adding a Public Method Without Breaking Source

Add a differently named method that does not affect overload resolution. Observe japicmp recording the new API while v1/v2 consumers still compile. Explain why a quality gate should not block every detected change.

### Exercise 5: Behavior Changes While Signature Stays Identical

Keep `total(int,int)` yet alter overflow or negative-value handling. Run API diff, then write regression tests with boundary inputs. Conclude why API comparison does not replace behavioral testing.

### Exercise 6: Defining Policy for a Real Library

Pick a library used in your system (with supported versions and permission to test). Define:

- Committed public API surface.
- Old/candidate coordinates.
- API analyzer and tool version.
- Consumer corpus.
- Thresholds blocking binary/source breaks.
- Waiver workflow.
- Test/report artifacts stored in CI.

Do not turn every internal implementation detail into an API contract if the team has not committed to maintaining it.

## 26. Lab Completion Criteria

An exercise meets its goals when backed by the following **technical evidence**:

- Two JARs v1/v2 built cleanly from source with distinct versions/checksums.
- `javap` shows changed return descriptor and visibility.
- japicmp or an equivalent tool produces API differences from both JARs.
- Learner identifies A1/A2/A3/A4 as distinct risk categories.
- Unchanged consumer source passes compilation with v1 and fails with v2 on the designed errors.
- Binary client compiled against v1 is run against v2 to observe the linkage break.
- At least one compatibility-preserving fix or intentional breaking-change migration plan exists.
- Report states limitations clearly: does not automatically prove reflection, serialization, or behavior.
- Proposes a CI gate that does not ignore skipped consumers or mutable artifacts.

Note: these criteria are **learner requirements in this lab**, and do not replace separate Content QA processes for documentation.

## 27. Real-Project Adoption Checklist

### Before Running

- [ ] Identified library, old/new versions, and source/binary compatibility commitments.
- [ ] Locked artifact coordinates/checksums, compiler/JDK, and dependency versions.
- [ ] Defined public/protected API surface and uncommitted internal packages.
- [ ] Selected an API analyzer supporting the target JDK's class-file level.
- [ ] Assembled consumer corpus and source snapshots at fixed commits.
- [ ] Checked Maven/Gradle profiles, modules, annotation processors, and generated sources.

### During Comparison

- [ ] Ran analyzer on the exact two artifacts, saved stdout/report.
- [ ] Inspected `javap -s` for methods with differing binary descriptors.
- [ ] Checked changes in inheritance, interfaces, generics, and overloads.
- [ ] Compiled consumer against v1 to establish a PASS baseline.
- [ ] Compiled exact same source against v2 in the same environment.
- [ ] Separated compiler diagnostics from repository/toolchain errors.
- [ ] Ran old consumer binaries against the new library where ABI is committed.
- [ ] Checked module descriptors if using JPMS.
- [ ] Tested reflection/SPI/serialization/configuration if applicable.

### Before Release

- [ ] Mapped each breaking change to affected consumers, owners, and decisions.
- [ ] Prepared adapter/deprecation plans or migration guides for accepted breaks.
- [ ] Added regression/contract tests for behavioral changes.
- [ ] Stored CI report artifacts and actual executed consumer coverage.
- [ ] Ensured no overly broad waivers mask new changes.
- [ ] Verified the tested artifact is the exact artifact to be released.
- [ ] Updated release notes and support/migration policy.

## 28. Conclusion

**Comparing APIs before and after changes using automated tools** is an essential step of Java Advance Compatibility Migration because it turns differences in library code into a structured report of classes, methods, fields, and compatibility risks. In this lab, `javap` reveals JVM signatures, japicmp helps identify API changes, consumer recompilation catches source breaks like overload ambiguity, and runtime tests with old binaries expose linkage breaks.

The core principle is **each tool answers a bounded question**. API diffs do not substitute for testing consumer sources; source compilation does not guarantee old binaries run; binary linking does not prove semantics stayed intact. By combining these verification layers properly, locking artifacts/toolchains, and enforcing policies in CI, teams can upgrade JDKs, frameworks, and shared libraries while catching contract-breaking changes early.
