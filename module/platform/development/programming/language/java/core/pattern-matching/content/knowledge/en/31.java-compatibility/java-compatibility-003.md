# Version Milestones of Record Patterns in Java: From Preview to Final Feature

## 1. Goal: Knowing Exactly Which Java Version Supports Record Patterns

When reading Java examples with syntax like `obj instanceof Point(var x, var y)` or `case Order(Customer(var name), var quantity) -> ...`, the first question when a build fails is **which language version is the project using?** Having records in a program **does not mean** you can use a **record pattern** to deconstruct a record.

**Milestones to remember:** record patterns first appeared as a **preview in Java 19** (JEP 405), received a **second preview in Java 20** (JEP 432), and became a **final feature in Java 21** (JEP 440). Starting from Java 21, standard record pattern code does not require `--enable-preview`.

This lesson belongs to the **Java Compatibility** group, focusing on:

- Distinguishing **record class** from **record pattern** and pattern matching for `instanceof`/`switch`.
- Understanding the Java 14–22 timeline, preview/final status, and corresponding JEP numbers.
- Understanding why **Java 17 has records but not record patterns**, and how to write an alternative.
- Knowing how to use `javac --release` and preview flags in the appropriate environment.
- Understanding a few syntax changes from the two preview rounds to Java 21, without copying old syntax mechanically.
- Examining a complete Java 21 program using nested record patterns, `instanceof`, `switch`, `when`, and generic inference.
- Distinguishing Java 21 record patterns from the **unnamed pattern `_`**, which became final in Java 22.

A common mistake is saying "record patterns have existed since Java 16" just because **records** became final in Java 16. That is incorrect: **declaring a record** and **deconstructing a record with a pattern** are two separate evolutionary steps in Java.

## 2. Three Related but Non-Overlapping Features

### 2.1. Record class: data type, final in Java 16

A record declares immutable data at the component level (component fields are `private final`; a record may still hold references to internal mutable objects). For example:

```java
record Point(int x, int y) {}

Point p = new Point(2, 3);
System.out.println(p.x()); // 2
System.out.println(p.y()); // 3
```

A record automatically provides accessors `x()`, `y()`, a canonical constructor, and `equals`/`hashCode`/`toString` according to record rules. The language supported records along this timeline:

- **Java 14:** Record Classes first preview (JEP 359).
- **Java 15:** Record Classes second preview (JEP 384).
- **Java 16:** Records become final (JEP 395).
- **Java 17:** Records work normally as a standard feature, but **record patterns do not exist yet**.

Therefore, the program above can exist in a Java 17 project. No record pattern is needed to create objects or call accessors.

### 2.2. Type pattern: type test and variable binding, final in Java 16

Since Java 16, `instanceof` supports type patterns:

```java
static String summary(Object input) {
    if (input instanceof Point point) {
        return point.x() + "," + point.y();
    }
    return "not a point";
}
```

Here `Point point` tests and binds **the entire object** to a variable of type `Point`. We still call `point.x()`, `point.y()`; this code is not yet deconstruction via a record pattern. This feature was standardized through **JEP 394** in Java 16.

### 2.3. Record pattern: record test and component deconstruction, final in Java 21

With Java 21:

```java
static String summary21(Object input) {
    if (input instanceof Point(var x, var y)) {
        return x + "," + y;
    }
    return "not a point";
}
```

The pattern `Point(var x, var y)` tests whether the object matches the `Point` record, and then extracts each component into variables `x`, `y`. There is no need to declare a whole-object variable `point` and explicitly call accessors in the consuming code.

The two methods `summary` and `summary21` above can produce the same result, but **they require different compiler versions**. This is the core of source compatibility.

## 3. Key Version Milestone Table

| Version | Record class status | Record patterns status | Related JEPs | Impact on project |
| --- | --- | --- | --- | --- |
| **Java 14** | First preview | Not supported | JEP 359 | Cannot write `Point(var x, var y)` yet. |
| **Java 15** | Second preview | Not supported | JEP 384 | No record deconstruction pattern yet. |
| **Java 16** | **Final** | Not supported | JEP 395; type pattern `instanceof` JEP 394 | Use `record` and `instanceof Point point`, access via accessors. |
| **Java 17** | Final | Not supported | Standard record; `switch` pattern separate preview JEP 406 | Cannot use `Point(var x, var y)` as record pattern syntax. |
| **Java 18** | Final | Not supported | `switch` pattern separate second preview JEP 420 | Preview flag for switch does not enable record patterns. |
| **Java 19** | Final | **First preview** | **JEP 405** | Compiling/running record patterns requires enabling preview on JDK 19. |
| **Java 20** | Final | **Second preview** | **JEP 432** | Still requires preview on JDK 20; includes feature changes compared to Java 19. |
| **Java 21** | Final | **Final** | **JEP 440** | Use record patterns directly, no preview flag needed. |
| **Java 22+** | Final | Final | JEP 440; unnamed patterns JEP 456 (Java 22) | Can also use `_` syntax to ignore unused components. |

Do not equate `switch` patterns with record patterns: **pattern matching for `switch`** had its own preview timeline starting in **Java 17** (JEP 406), through Java 18 (JEP 420), Java 19 (JEP 427), Java 20 (JEP 433), and then became final in **Java 21** (JEP 441). Meanwhile, **record patterns** only started previewing in **Java 19**.

**Practical milestone:** If you are developing on Java 17 LTS and need a codebase without preview features, use `record` with accessors or type patterns. If you are using Java 21 LTS, you can use record patterns in both `instanceof` and `switch` as a stable feature.

## 4. Java 19 — JEP 405: First Preview

**JEP 405 — Record Patterns (Preview)** introduced the ability to deconstruct records based on patterns. The idea is to allow developers to express the data structure to match declaratively, instead of writing consecutive `instanceof` checks, casts, and accessor calls.

An example of the concept (using stable Java 21 syntax to explain the mechanism):

```java
record Point(int x, int y) {}

static int sum(Object raw) {
    if (raw instanceof Point(var x, var y)) {
        return x + y;
    }
    return 0;
}
```

In Java 19, record patterns were still in **preview**, so using the feature required JDK 19 and enabling preview for **release 19**. For example, with a program written to match Java 19 syntax and APIs:

```bash
# Only when actually using JDK 19 and preview source valid for Java 19:
javac --enable-preview --release 19 RecordPatternPreviewDemo.java
java --enable-preview RecordPatternPreviewDemo
```

The filename `RecordPatternPreviewDemo.java` in this command pair is an illustrative name for a separate Java 19-compatible program, **not the filename of the full runnable program in Section 8**. Do not assume you can take a Java 21 file with guards, inference, or newer syntax as-is and run it unchanged on Java 19.

**What is a preview feature?** A feature that has been implemented for experimentation and feedback, but does not yet carry the stability commitment of a final feature. Syntax and rules may change between preview releases and the final release. Therefore, in projects requiring long-term compatibility, preview code should have its version boundaries clearly marked and be tested on the exact target JDK.

## 5. Java 20 — JEP 432: Second Preview and Notable Changes

**JEP 432 — Record Patterns (Second Preview)** brought record patterns back in Java 20 with refinements based on feedback from Java 19. Two points worth knowing when reading historical code:

1. **Type argument inference for generic record patterns** was expanded, reducing the need to explicitly write some type arguments in contexts already known to the compiler. This was an important step forward for nested/generic record deconstruction.
2. **Named record patterns**, which were supported in the Java 19 preview, were no longer supported in the Java 20 preview. Therefore, do not copy old preview syntax from Java 19 articles into Java 20/21 code without checking.

Additionally, in the **Java 20 preview**, record patterns could appear in the loop variable declaration of an **enhanced `for`** statement. This capability **is not present in the final record patterns of Java 21**. That means preview code that used to be valid in a loop may need refactoring when upgrading to Java 21; keep `for (var element : list)` and then use `instanceof Record(...)` inside the loop body when appropriate.

Java 20 still required enabling preview when using record patterns:

```bash
# JDK 20 only; the separate example code must be valid for Java 20 preview:
javac --enable-preview --release 20 RecordPatternPreviewDemo.java
java --enable-preview RecordPatternPreviewDemo
```

You must **match the JDK version and the preview release**. A modern JDK cannot arbitrarily enable preview for an old feature using `--enable-preview --release 19`/`20` to accurately emulate an old environment: preview is only enabled for the release supported by the current compiler. To truly test Java 19/20 preview code, use the corresponding Java 19/20 toolchain.

**Compatibility warning:** When migrating Java 19 → 20 → 21, read compiler warnings about preview features, removed syntax, type inference behavior, and contexts where record patterns are allowed. The goal is not just changing the release number, but also updating source code where the language changed.

## 6. Java 21 — JEP 440: Record Patterns Become a Final Feature

Starting from **Java 21**, record patterns are standardized (JEP 440). Typical scenarios include:

- **`instanceof` with a record pattern:** `input instanceof Point(var x, var y)`.
- **Nested record patterns:** `input instanceof ColoredPoint(Point(var x, var y), var color)`.
- **`switch` with a record pattern:** `case Point(var x, var y) -> ...` when the selector has a compatible type.
- **`when` guard in `switch`:** `case Point(var x, var y) when x == y -> ...` (requires pattern matching for switch, which also became final via JEP 441 in Java 21).
- **Generic record patterns:** the compiler can infer type arguments in appropriate cases.

Java 21 does not require `--enable-preview` to use the standard syntax above. Example of a project targeting release level 21:

```bash
javac --release 21 RecordPatternVersionDemo.java
java RecordPatternVersionDemo
```

The command above is for **the complete file in Section 8**. `--release 21` requires a JDK compiler that supports target Java 21; it is not a flag that enables preview features. A project built with JDK 17 cannot compile Java 21 source by adding `--release 21` because the JDK 17 compiler does not support that target.

**Important note:** Having `record` in source code alone does not make it record pattern code. For example, `record Point(int x, int y)`, `new Point(1, 2)`, and `point.x()` already work on Java 16/17. Only places that test and deconstruct using `Point(...)` syntax inside a pattern require record patterns.

## 7. Java 21 and Java 22: Do Not Confuse Record Patterns with Unnamed Pattern _

In Java 21 **without preview enabled**, when a component is unused, you may still have to write all positions and name the variable:

```java
record Point(int x, int y) {}

// Stable Java 21: includes both components, even though y is unused.
static int xOnly(Object value) {
    if (value instanceof Point(var x, var ignoredY)) {
        return x;
    }
    return -1;
}
```

The **unnamed pattern `_`** syntax had its own timeline:

- **Java 21:** *Unnamed Patterns and Variables* was in **preview** via **JEP 443**; it is not a default standard feature of Java 21.
- **Java 22:** *Unnamed Variables & Patterns* became **final** via **JEP 456**.

With Java 22+ you can write:

```java
// Java 22+, not standard syntax in default Java 21.
record Point(int x, int y) {}

static int xOnly(Object input) {
    return switch (input) {
        case Point(var x, _) -> x;
        default -> -1;
    };
}
```

If you are writing Java 21 code without preview enabled, choose `var ignoredY` instead of `_` to ensure compatibility. **The underscore does not remove a component from the pattern list**: a record pattern must still match the exact number and order of components.

A project may use JDK 22 or newer while setting `--release 21` to ship code for Java 21; in that case, features that only became standard in Java 22 (such as unnamed patterns `_`) are **invalid** at source level 21. The installed JDK version and the compiled source level are two different things.

## 8. Complete Java 21 Example: Records, instanceof, switch, Nested, and Generic

Create the file **`RecordPatternVersionDemo.java`**:

```java
public class RecordPatternVersionDemo {
    record Point(int x, int y) {}
    record ColoredPoint(Point point, String color) {}
    record Pair<T>(T first, T second) {}

    static String legacy(Object input) {
        if (!(input instanceof ColoredPoint value)) return "not-colored-point";
        if (value.point() == null) return "missing-point";
        return value.color() + ":" + value.point().x() + "," + value.point().y();
    }

    static String withInstanceof(Object input) {
        if (input instanceof ColoredPoint(Point(var x, var y), var color)) {
            return color + ":" + x + "," + y;
        }
        if (input instanceof ColoredPoint(var point, var color)) return "missing-point";
        return "not-colored-point";
    }

    static String withSwitch(Object input) {
        return switch (input) {
            case null -> "null-input";
            case ColoredPoint(Point(var x, var y), var color) when x == y ->
                    "diagonal:" + color + ":" + x;
            case ColoredPoint(Point(var x, var y), var color) ->
                    "point:" + color + ":" + x + "," + y;
            case ColoredPoint(var point, var color) -> "missing-point";
            case Point(var x, var y) -> "bare-point:" + x + "," + y;
            default -> "other";
        };
    }

    static String generic(Pair<String> pair) {
        if (pair instanceof Pair(var first, var second)) {
            return first + "|" + second;
        }
        return "null-pair";
    }

    public static void main(String[] args) {
        Object normal = new ColoredPoint(new Point(2, 3), "red");
        Object diagonal = new ColoredPoint(new Point(4, 4), "blue");
        Object absent = new ColoredPoint(null, "none");

        System.out.println("record=" + normal.getClass().getSimpleName());
        System.out.println("legacy=" + legacy(normal));
        System.out.println("instanceof=" + withInstanceof(normal));
        System.out.println("switch=" + withSwitch(normal));
        System.out.println("diagonal=" + withSwitch(diagonal));
        System.out.println("missing.legacy=" + legacy(absent));
        System.out.println("missing.instanceof=" + withInstanceof(absent));
        System.out.println("missing.switch=" + withSwitch(absent));
        System.out.println("bare=" + withSwitch(new Point(8, 9)));
        System.out.println("null=" + withSwitch(null));
        System.out.println("other=" + withSwitch("java"));
        System.out.println("generic=" + generic(new Pair<>("A", "B")));
        System.out.println("generic.null=" + generic(null));
        System.out.println("equal=" + legacy(normal).equals(withInstanceof(normal)));
    }
}
```

Compile and run with **JDK 21+**:

```bash
javac --release 21 RecordPatternVersionDemo.java
java RecordPatternVersionDemo
```

**Expected stdout:**

```text
record=ColoredPoint
legacy=red:2,3
instanceof=red:2,3
switch=point:red:2,3
diagonal=diagonal:blue:4
missing.legacy=missing-point
missing.instanceof=missing-point
missing.switch=missing-point
bare=bare-point:8,9
null=null-input
other=other
generic=A|B
generic.null=null-pair
equal=true
```

**Points to read carefully:**

1. **`legacy`** uses the type pattern `instanceof ColoredPoint value` (standard since Java 16), then calls accessors. This is a Java 17-friendly implementation.
2. **`withInstanceof`** uses the nested record pattern `ColoredPoint(Point(var x, var y), var color)`, which requires **Java 21** as a standard feature. When `point == null`, the nested `Point(...)` does not match; the subsequent `ColoredPoint(var point, var color)` branch catches that case.
3. **`withSwitch`** uses record patterns in `case` and `when x == y`. When `Point(4,4)` satisfies the diagonal condition, the first branch returns `diagonal:blue:4`; for `Point(2,3)`, the guard is false so the unguarded record branch below returns `point:red:2,3`.
4. **`generic`** accepts `Pair<String>`. The pattern `Pair(var first, var second)` infers the component types from context. If `pair == null`, `instanceof` returns false and the result is `null-pair`.
5. **`case null`** catches a null selector in `switch`. In a pattern `switch` without null handling, `default` does not automatically substitute for a null-handling policy and can throw `NullPointerException`.
6. **`equal=true`** confirms that `legacy` and `withInstanceof` return the same result for the normal input tested; it does not automatically prove they are equivalent for all data.

The program only uses features that are **stable in Java 21**, without using unnamed pattern `_` or preview syntax removed in Java 20/21.

## 9. When Building with Java 17: Record Class Code Is Valid, Deconstruction Pattern Is Invalid

Java 17 supports record classes and `instanceof` type patterns, so record patterns can be replaced with explicit accessors:

```java
// Record + type pattern: runs on Java 17.
public class CompatibleWith17 {
    record Point(int x, int y) {}

    static String show(Object input) {
        if (input instanceof Point point) {
            return point.x() + "," + point.y();
        }
        return "other";
    }

    public static void main(String[] args) {
        System.out.println(show(new Point(2, 3)));
        System.out.println(show(null));
    }
}
```

Commands:

```bash
javac --release 17 CompatibleWith17.java
java CompatibleWith17
```

Output:

```text
2,3
other
```

If in the same Java 17 mode you write:

```java
// DOES NOT COMPILE with source/release 17:
if (input instanceof Point(var x, var y)) {
    return x + "," + y;
}
```

The compiler rejects the deconstruction syntax because record patterns **did not exist in Java 17**, not because the `Point` record is invalid. With a newer compiler supporting `--release 17`, the error message may look like **“deconstruction patterns are not supported in -source 17”**.

**Do not fix this by adding `--enable-preview` to the Java 17 command.** Java 17's preview features apply to features that were provided in Java 17; record patterns were only introduced later, in Java 19. To use record patterns as a standard feature, upgrade source/release to **21** and use a toolchain that supports Java 21.

## 10. Effects of --release, --source, --enable-preview

For Java:

- `java -version` shows the JVM runtime currently used in the terminal session.
- `javac -version` shows the Java compiler version selected via `PATH`/toolchain.
- `javac --release N` instructs the compiler to compile source according to the language/API/class file format matching version `N` supported by the compiler. A newer JDK can target an older Java version, but **cannot use language features newer than the target**.
- `--enable-preview` enables preview features belonging to the corresponding version. It is **not a switch to “turn on all future features”**.

### Verification Recipe by Version

| Target | Required JDK | Example compile command | How to run |
| --- | --- | --- | --- |
| Java 17 record class + type pattern | JDK 17+ supporting target 17 | `javac --release 17 CompatibleWith17.java` | `java CompatibleWith17` on a compatible runtime |
| Java 19 record pattern preview | **JDK 19** | `javac --enable-preview --release 19 PreviewDemo19.java` | `java --enable-preview PreviewDemo19` on JDK 19 |
| Java 20 record pattern second preview | **JDK 20** | `javac --enable-preview --release 20 PreviewDemo20.java` | `java --enable-preview PreviewDemo20` on JDK 20 |
| Java 21 final record pattern | JDK 21+ supporting target 21 | `javac --release 21 RecordPatternVersionDemo.java` | `java RecordPatternVersionDemo` on JDK 21+ |

The names `PreviewDemo19.java` and `PreviewDemo20.java` in the table are **example filenames for a separate project** using each version's preview syntax; they are not files with source code provided in this lesson. The complete program with source code and verified stdout is `RecordPatternVersionDemo.java` in Section 8.

Projects must also check the **deployment runtime version**. For example, compiling a file with target Java 21 produces class files compatible with Java 21; copying those classes onto a Java 17 runtime can cause `UnsupportedClassVersionError`, regardless of whether the record pattern syntax is valid.

If you are using an IDE or CI, "the JDK installed on the machine" may not match the JDK actually invoked by Maven, Gradle, the IDE, or the pipeline. Therefore, when encountering unexpected errors, check **the actual compiler and source/release level**, not just the runtime printed in another terminal.

## 11. Setting Java 21 for Maven/Gradle and Handling Compatibility Errors

### Maven

For a project that truly wants to use standard Java 21:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

This is an illustrative configuration snippet placed in `pom.xml`, with Maven Compiler Plugin/build settings that support this property. Ensure Maven uses a JDK capable of targeting Java 21. Then Java 21 record patterns compile as a final feature, **without adding preview flags**.

If you need to keep Java 17 compatibility, set `maven.compiler.release` to `17` and refactor record patterns to `instanceof Type variable`/accessors.

### Gradle Groovy DSL

Example Java 21 toolchain:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Place this in the `build.gradle` file of an appropriate Java project. Depending on the build, you can configure `options.release = 21` if you need to explicitly constrain the target. Do not just install JDK 21 on the OS and assume Gradle/IDE will automatically change the source level.

### How to Read Compiler Errors

- **“deconstruction patterns are not supported in -source 17”**: compiling record pattern code with an unsupported source level.
- **“invalid source release: 21”** (or equivalent message): the compiler is too old to target Java 21; upgrade the JDK compiler/toolchain.
- **“preview features are disabled by default”** with Java 19/20 preview code: preview must be enabled on the matching version.
- **“preview features ... only supported for release ...”**: the compiler refuses to arbitrarily enable preview for an older target version; use the proper toolchain.
- **“cannot find symbol”** or pattern inference errors: may be caused by code copied from preview with changed syntax, wrong type arguments, missing components, or missing imports; not necessarily only a version issue.

Always read the **source/release** section in the build log and check the actual class/method failing before making broad configuration changes.

## 12. Preview Changes That Easily Cause Confusion When Upgrading

### 12.1. Named record patterns from Java 19 preview

The first preview had certain record pattern forms that were not kept later. JEP 432 in Java 20 removed **named record patterns**, whereas Java 21 uses the stable record pattern form:

```java
// Java 21: deconstruct components, use variables in the branch scope.
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

The snippet above is placed where `input` has an appropriate type, not as a standalone file. If you need to keep a variable pointing to **the entire record**, use a separate type pattern:

```java
if (input instanceof Point point) {
    System.out.println(point.x() + point.y());
}
```

Do not splice named record pattern syntax from Java 19 preview blog posts into a Java 21 project and expect the compiler to understand it. When migrating, rewrite it to a standard **record pattern** or **type pattern**.

### 12.2. Enhanced for with record patterns in Java 20 preview, absent in Java 21 final

JEP 432 experimented with allowing record patterns in the header of a `for-each` loop. JEP 440 **removed that support** from the final syntax. The safe Java 21 way to write it is:

```java
// Java 21 pattern: iterate elements in for-each, then deconstruct inside.
for (Object element : values) {
    if (element instanceof Point(var x, var y)) {
        System.out.println(x + y);
    }
}
```

This is a snippet that requires a `values` variable from program context. It does not form a standalone file and cannot run without `values` data. The key point is deconstructing in the **loop body**, instead of relying on syntax that Java 20 preview used to allow.

### 12.3. Generic record patterns

Generic code like `record Pair<T>(T first, T second) {}` requires the compiler to determine component types and matching rules. The preview roadmap improved type argument inference, especially starting from JEP 432. In Java 21, if the context is clear enough, you can write `Pair(var first, var second)` as in the `generic` method in Section 8.

However, generic type erasure still exists. Do not assume that a check from `Object` like `instanceof List<String>` can prove every element is a `String` at runtime; it is invalid in normal situations. Use `List<?>` and check elements or use an appropriate schema. Record pattern generic inference **does not eliminate** runtime type erasure limitations.

## 13. Upgrade Process from Java 17/19/20 to Java 21

Suppose a project is preparing to use record patterns while still having older build parts:

1. **Identify the deployment target:** does the production/CI runtime support Java 21? Are there modules or libraries required to run on Java 17? If so, those parts must remain Java 17-compatible or be separated appropriately.
2. **Read the actual source level:** check `javac -version`, `java -version`, `--release`, Maven/Gradle toolchains, and IDE language level.
3. **Distinguish records from record patterns:** record types can stay on Java 17; only deconstruction pattern code requires Java 21 if you want to avoid preview.
4. **For Java 19/20 preview code:** review named pattern syntax, record patterns in enhanced-for headers, and generic type inference; do not just remove `--enable-preview` and keep all syntax unchanged.
5. **Upgrade compiler/source level to 21:** set the JDK/toolchain and target release 21 consistently across the project. Remove preview flags if no other preview features are used.
6. **Compile all tests:** verify that `case` with `when`, `null`, nested record patterns, and `switch` exhaustiveness are valid.
7. **Run tests on a Java 21 runtime:** test match paths, non-match paths, null nested records, null components, boundary values, and exceptions.
8. **Check libraries and pipelines:** frameworks, build plugins, static analyzers, code formatters, coverage tools, and code generators must understand Java 21 syntax/bytecode.
9. **Do not mix in Java 22 syntax:** if Java 21 support is required, keep `var ignored` instead of unnamed pattern `_` even if developer machines have a newer JDK.
10. **Update version documentation:** clearly state Java 21 minimum for modules using record patterns, so readers do not run `javac --release 17` and misread the error.

**Conservative option:** If the code only needs one or two components and still must run on Java 17, use `instanceof Point point` and then accessors. Record patterns are syntax that makes structural deconstruction clearer, not a mandatory requirement to work with record data.

## 14. Common Version Milestone Pitfalls Table

| Claim or Error | Reality | How to Fix |
| --- | --- | --- |
| “Records exist since Java 16, so record patterns also exist since Java 16” | Java 16 standardized **records** (JEP 395) and `instanceof` type patterns (JEP 394); record patterns only started previewing in Java 19. | Distinguish the three features; use accessors on Java 17. |
| “Java 17 already has pattern switch preview, so it has record patterns” | Pattern matching for switch and record patterns have separate development timelines. | For standard record patterns, use Java 21+. |
| “Java 19 already has stable support for record patterns” | Java 19 was the **first preview** (JEP 405). | Enable preview with JDK 19 if you must use preview code; consider upgrading to 21. |
| “Java 20 is the final release” | Java 20 was the **second preview** (JEP 432). | Wait for / upgrade to Java 21 for standard usage. |
| “Java 21 still requires --enable-preview for record patterns” | Java 21 is **final** (JEP 440). | Use `javac --release 21` normally. |
| “Java 21 has _ as a standard unnamed pattern” | Java 21 JEP 443 is **preview**; Java 22 JEP 456 made it final. | Use `var ignored` on Java 21 without preview. |
| “Enhanced-for record pattern code from Java 20 preview must run on Java 21” | Support in enhanced-for headers was **removed** in Java 21. | Move `instanceof Record(...)` into the loop body. |
| “Using JDK 24 with --release 17 still allows record patterns” | `--release 17` selects Java 17 language/API. | Upgrade release to 21 or remove record patterns. |
| “Just pass --enable-preview --release 19 with any newer JDK” | Preview only applies to the release supported by the compiler at that time. | Use the exact JDK 19/20 for historical preview code. |
| “Pair(var x, var y) checks generic runtime types completely” | The compiler infers types from context, but erasure still limits runtime checks. | Validate data contracts; do not turn generic inference into a `List<String>` assertion. |
| “With --release 21, the class can run on JRE 17” | Class file and runtime must be compatible; Java 17 cannot run target 21 classes. | Ensure production runtime is Java 21+ or ship Java 17-compatible code. |
| “Not matching a nested record pattern means every component is non-null” | A null nested record will not match; a component bound by `var` can still be null. | Test null at both nested record levels and individual components. |

## 15. Self-Check Exercises on Versions and Solution Choices

### Scenario A: A project requires Java 17

You have:

```java
record User(String name, int age) {}

static String label(Object raw) {
    if (raw instanceof User(var name, var age)) {
        return name + ":" + age;
    }
    return "other";
}
```

**Question:** Why does the Java 17 project fail to compile? Do you have to remove `record User`?

**Answer:** You do not need to remove the record. Java 17 already supports record classes, but does not yet support record deconstruction patterns. Refactor to a type pattern + accessors:

```java
static String label(Object raw) {
    if (raw instanceof User user) {
        return user.name() + ":" + user.age();
    }
    return "other";
}
```

Both methods are snippets placed inside a class declaring `record User`. The second version is compatible with Java 17.

### Scenario B: A Java 20 preview project upgrading to 21

Old source uses record patterns in an enhanced `for` header. The project team changes `--release 20` to `--release 21`, but the compiler reports an error.

**Answer:** Review the historical syntax: Java 20 preview supported record patterns in enhanced-for headers, but final Java 21 removed it. Use a normal element variable in `for (var element : collection)` and then deconstruct with `instanceof Record(...)` inside the loop body. Also check generic inference and any named record patterns from old previews.

### Scenario C: Developer machine has JDK 22, production is Java 21

A developer wants to write `case Point(var x, _) -> ...` in a module targeting Java 21.

**Answer:** Do not use standard Java 22 `_` syntax when compiling with `--release 21`. Write `case Point(var x, var ignoredY) -> ...` or choose a type pattern and accessors. Having a newer JDK running the compiler does not mean the target source level is automatically newer.

### Scenario D: Quick quiz questions

- Which Java version made record classes final? **Java 16, JEP 395**.
- Which Java version first previewed record patterns? **Java 19, JEP 405**.
- Which Java version had the second preview of record patterns? **Java 20, JEP 432**.
- Which Java version made record patterns final? **Java 21, JEP 440**.
- Which Java version made pattern matching for `switch` final? **Java 21, JEP 441**.
- Which Java version made unnamed patterns `_` final? **Java 22, JEP 456**.

## 16. Summary to Remember

- **Record ≠ record pattern.** A record is a data type final since Java 16; a record pattern that deconstructs a record only became final in Java 21.
- **Java 19 → 20 → 21:** **JEP 405 preview → JEP 432 second preview → JEP 440 final**.
- **Java 17:** use `record`, type pattern `instanceof Point point`, and accessors; **do not** use `Point(var x, var y)`.
- **Java 21:** use nested record patterns in `instanceof`/`switch` without `--enable-preview`; pattern matching for switch is also final in Java 21.
- **Java 22:** unnamed patterns `_` become final; Java 21 only has a separate preview.
- **Preview migration is not just removing a flag:** check historical named patterns, enhanced-for, generic inference, source/release, and runtime.
- **To run properly:** ensure the compiler, target release, preview flags (if applicable), and runtime are consistent; test match, null, and fallback paths.

**Official references:**

- [JEP 359 — Records (Preview, Java 14)](https://openjdk.org/jeps/359)
- [JEP 384 — Records (Second Preview, Java 15)](https://openjdk.org/jeps/384)
- [JEP 395 — Records (Java 16)](https://openjdk.org/jeps/395)
- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 405 — Record Patterns (Preview, Java 19)](https://openjdk.org/jeps/405)
- [JEP 432 — Record Patterns (Second Preview, Java 20)](https://openjdk.org/jeps/432)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 443 — Unnamed Patterns and Variables (Preview, Java 21)](https://openjdk.org/jeps/443)
- [JEP 456 — Unnamed Variables & Patterns (Java 22)](https://openjdk.org/jeps/456)
- [Oracle Java 21 — Java Language Changes by Release](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
