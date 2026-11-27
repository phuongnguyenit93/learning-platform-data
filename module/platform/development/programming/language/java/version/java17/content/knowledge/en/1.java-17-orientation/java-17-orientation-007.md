# How to Look Up the Language Specification, API Docs, and Release Notes in Java 17

When working with Java 17, finding a snippet that runs is not enough to conclude that it is correct, stable, or usable across all Java 17 environments. You need to know **which document holds the answer, which version to read, and how to separate language rules from library contracts**. The three primary reference sources are the **Java Language Specification (JLS)**, **Java SE/JDK API Documentation (Javadoc)**, and **JDK Release Notes**. **JEP (JDK Enhancement Proposal)** documents explain the design context and rollout history of features into the JDK.

This lesson focuses on lookup techniques that remain practical when developing, maintaining, or upgrading applications running on Java 17. All examples use APIs and syntax available in Java 17; features in *preview* status are explicitly labeled.

## 1. Pick the Right Source for the Right Question

| When you need to answer… | Open first | Additional sources if needed |
| --- | --- | --- |
| How are `sealed`, `record`, generics, overloading, or `switch` allowed to be written and how do they behave? | **Java SE 17 JLS** | Language guides, corresponding JEP |
| How does the compiler emit and the JVM process class files, bytecode, linking, or class loading? | **Java Virtual Machine Specification (JVMS) 17** | JVM docs and JDK tool specifications |
| What do `Stream.toList()`, `List.of()`, or `Files.readString()` return, what exceptions do they throw, and can the result be mutated? | **Java SE 17 API Docs (Javadoc)** | JLS when the question involves syntax or types |
| Why was a feature proposed, in which release did it ship, and is it a preview feature? | **JEPs and the JDK 17 feature list** | Java 17 JLS/API Docs to confirm finalized behavior |
| An upgrade from an older JDK failed, JVM flags changed, or compatibility/security changes apply? | **Release Notes for the exact JDK version** | Migration Guide, JEPs, JDK vendor advisories |
| Does a behavior depend on a `17.0.x` patch, OS, or JDK vendor? | **Release Notes/advisories of the distribution in use** | JDK bug tracker and corresponding deployment docs |

**Priority rule:** JLS/JVMS define the specification rules; API Docs define the public library contract; Release Notes record what changed in a release. JEPs explain goals and design, yet an idea described in a JEP does not automatically become usable syntax or API in Java 17. Blog posts or forum answers are hints for finding keywords, not replacements for these primary sources.

## 2. Pin the Version Before Looking Things Up

Every documentation page must match your **program's target version**, not necessarily the latest published Java release. For a project running Java 17, start from URLs containing `se17` or `/java/javase/17/`.

```bash
java -version
javac -version
java -XshowSettings:properties -version
```

The first two commands report the Java runtime and compiler currently selected in your environment; they can point to two different installations. The third command displays properties such as `java.home`, `java.vendor`, and `java.version`. If the application runs in a container, CI, or server, check **directly inside that environment** rather than only on your development laptop.

Example:

```text
openjdk version "17.0.x" ...
javac 17.0.x
```

In the version string `17.0.x`, **17** is the language/platform feature release to look up; **17.0.x** specifies the actual update release. Update releases may include bug fixes, security patches, certificates, time zone data updates, and operational fixes without introducing new syntax from later Java generations into Java 17.

If you build with a newer JDK while the application must run on Java 17, use the compiler option:

```bash
javac --release 17 Example.java
```

`--release 17` instructs the compiler to check both syntax and platform APIs supported by Java 17; setting `-source 17` alone does not fully prevent accidentally calling APIs from newer versions. In Maven/Gradle projects, configure the equivalent `release` setting in your build tool and verify the JDK used at runtime.

### Official reference links

| Document | URL |
| --- | --- |
| Java Language Specification, Java SE 17 | <https://docs.oracle.com/javase/specs/jls/se17/html/index.html> |
| Java Virtual Machine Specification, Java SE 17 | <https://docs.oracle.com/javase/specs/jvms/se17/html/index.html> |
| Java SE 17 & JDK 17 API Specification | <https://docs.oracle.com/en/java/javase/17/docs/api/index.html> |
| JDK 17 Tool Guides and Specifications | <https://docs.oracle.com/en/java/javase/17/docs/specs/index.html> |
| Language Changes in Java SE 17 | <https://docs.oracle.com/en/java/javase/17/language/java-language-changes-release.html> |
| JDK 17 Project JEP List | <https://openjdk.org/projects/jdk/17/> |
| Initial JDK 17 Release Notes | <https://www.oracle.com/java/technologies/javase/17-relnote-issues.html> |
| Oracle JDK 17 Update Release Notes Index | <https://www.oracle.com/java/technologies/javase/17u-relnotes.html> |
| JDK 17 Migration Guide | <https://docs.oracle.com/en/java/javase/17/migrate/index.html> |

These are fixed starting points for Java 17. For distributions other than Oracle JDK, also check patch notes and support information from the vendor you use; do not assume every distribution follows the same update schedule.

## 3. Reading the Java Language Specification (JLS)

### 3.1. What does the JLS answer?

The JLS specifies the rules of **Java source code**, such as:

- Valid syntax for class, interface, and record declarations, expressions, and statements.
- Rules for name scope, accessibility, inheritance, data types, casting, and type inference.
- Method overload resolution, overriding rules, and compile-time error checks.
- Semantics of expressions, control flow, object initialization, and exception handling.

The JLS is not a catalog of library methods. To find out whether `List.copyOf()` allows `null`, look up the API Docs; to find out whether a generic expression is accepted by the compiler, that is a classic JLS question.

### 3.2. How to read and cite a section

1. Open **JLS SE 17** and search keywords in the table of contents or via in-page search.
2. Select the relevant chapter: *Types, Values, and Variables*; *Conversions and Contexts*; *Classes*; *Interfaces*; *Expressions*; or *Statements*.
3. Navigate to a numbered subsection such as `§8.1.1.2`. Read the definition, restrictions, and cross-references to other clauses.
4. Distinguish normative rules (*compile-time error*, *must*, *may*) from illustrative examples; if verification is needed, create a minimal source example and compile with `javac --release 17`.
5. When writing notes or technical discussions, cite both the **version and section**, such as “JLS Java SE 17, §8.1.1.2”.

Useful links for Java 17:

- [JLS §8.1.1.2 — `sealed`, `non-sealed`, and `final` classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2).
- [JLS §8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6).
- [JLS §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10).
- [JLS §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12) when studying overloading and method selection.

### 3.3. Example: Is `sealed` combined with `record` valid in Java 17?

In Java 17, **sealed classes/interfaces are finalized** ([JEP 409](https://openjdk.org/jeps/409)); `record` was finalized in Java 16 and continues to work stably in Java 17. You can write a `ShapeDemo.java` file as follows:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

public class ShapeDemo {
    static double area(Shape shape) {
        if (shape instanceof Circle circle) {
            return Math.PI * circle.radius() * circle.radius();
        }
        if (shape instanceof Rectangle rectangle) {
            return rectangle.width() * rectangle.height();
        }
        throw new IllegalArgumentException("Unsupported shape");
    }

    public static void main(String[] args) {
        System.out.println(area(new Circle(2)));
    }
}
```

```bash
javac --release 17 ShapeDemo.java
java ShapeDemo
```

To understand **why** this code is valid, trace three questions: how `sealed` restricts direct subtypes (JLS §8.1.1.2, §8.1.6, and the corresponding interface sections); which members `record` generates (JLS §8.10); and how `instanceof` with a pattern variable works (the `instanceof` section in the JLS). Do not infer from this example that all forms of pattern matching are finalized in Java 17.

### 3.4. When to open the JVMS instead of the JLS?

When the question shifts from **source code** to **bytecode and the virtual machine**, consult the JVMS: class file structure, bytecode verification rules, class loading/linking/initialization, and the JVM instruction set. For example, you can inspect the compiled file structure using:

```bash
javap -v ShapeDemo
```

`javap` output helps you observe the class file; **JVMS 17** is the authoritative source for its structures, fields, and opcodes. Do not infer an API's contract solely from bytecode or from implementation details of one specific JVM.

## 4. Reading Java SE 17 API Docs (Javadoc)

### 4.1. Navigating from module to package, class, and method

Java 17 Javadoc pages are organized by **Module → Package → Class/Interface → Field/Constructor/Method**. For instance, to look up `Stream.toList()`:

1. Open the [Java SE 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/index.html).
2. Search for `Stream` and select `java.util.stream.Stream` in module `java.base`.
3. On the [`Stream` page](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), find `toList()` in the *Method Summary* or method detail section.
4. Read the **contract description** and sections such as *Returns*, *Parameters*, *Throws*, *Since*, *API Note*, *Implementation Requirements*, and *Implementation Note*.
5. If overloads exist, select the exact method signature; two methods with the same name can differ in parameters, exceptions, and return behavior.

When looking up a class, also read the top-of-page class overview: constraints that apply across the entire class are often not repeated in full on every method. Check `@since` to see when an API was added, keeping in mind that **`Since: 16` does not mean the API was removed in Java 17**. Read *Deprecated* and *for removal* notices carefully when evaluating an API's lifecycle.

### 4.2. Read the API contract instead of guessing from the method name

For example, the [Java 17 Javadoc for `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html) explicitly states:

- The result is a `List` containing the stream elements in encounter order if the stream has one.
- The returned list is **unmodifiable**; calling `add`, `remove`, `set`, etc. throws `UnsupportedOperationException`.
- There are no guarantees regarding the concrete implementation class or serializability.
- This API has existed since **Java 16** and is usable in **Java 17**.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ApiDocsExample {
    public static void main(String[] args) {
        List<String> readOnly = Stream.of("An", "Binh").toList();
        System.out.println(readOnly); // [An, Binh]

        // readOnly.add("Chi"); // UnsupportedOperationException at runtime

        List<String> editable = Stream.of("An", "Binh")
                .collect(Collectors.toCollection(ArrayList::new));
        editable.add("Chi");
        System.out.println(editable); // [An, Binh, Chi]
    }
}
```

```bash
javac --release 17 ApiDocsExample.java
java ApiDocsExample
```

Key distinction: `Stream.toList()` **guarantees** an unmodifiable list; `Collectors.toList()` **makes no guarantees** about list type or mutability; `Collectors.toCollection(ArrayList::new)` lets you explicitly request a mutable `ArrayList`. That is why you should never write code based on “on my machine it returned an `ArrayList`.” Consult the [Javadoc for `Collectors`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html) to compare each collector's contract.

### 4.3. Common labels in Javadoc

| Label / Section | How to Read Properly |
| --- | --- |
| *Type Parameters*, *Parameters* | Meaning and constraints of type parameters or method parameters. |
| *Returns* | Return value and guaranteed constraints. |
| *Throws* | Specified exceptions; do not assume only listed exceptions can arise from all runtime failures. |
| *Since* | First release providing the API; verify against your target version. |
| *Deprecated* / *for removal* | API is discouraged or slated for removal; read the exact details on replacements and compatibility. |
| *API Note* | Guidance on how to use the API, often with examples. |
| *Implementation Requirements* | Requirements on how an implementation of the API must behave when present. |
| *Implementation Note* | Information about a particular implementation; not automatically part of the general contract for all implementations. |

**Note:** An *unmodifiable* result does not mean the objects inside it are immutable; element immutability and whether underlying data sources can mutate must be checked in their own contracts. Likewise, words like `copyOf` or `of` in a method name are not enough by themselves to deduce how `null`, duplicates, or element ordering are handled.

## 5. Reading JEPs and Distinguishing Final vs. Preview Features

A **JEP** presents the motivation, goals, design alternatives, and proposal history of a JDK change. When reading one, check at minimum the **JEP number, status, target release, and whether the feature is final or still preview/incubator**. Then verify the feature in the Java 17 JLS or API Docs.

Commonly confused cases:

| Feature | Status in Java 17 | Where to Verify |
| --- | --- | --- |
| `sealed` class/interface | **Final in Java 17** | [JEP 409](https://openjdk.org/jeps/409), JLS SE 17 |
| `record` | **Final since Java 16**, usable in Java 17 | [JEP 395](https://openjdk.org/jeps/395), JLS §8.10 |
| Pattern matching for `instanceof` | **Final since Java 16**, usable in Java 17 | [JEP 394](https://openjdk.org/jeps/394), JLS SE 17 |
| Pattern matching for `switch` | **Preview in Java 17**; not default stable Java 17 syntax | [JEP 406](https://openjdk.org/jeps/406), Java 17 language docs |
| Enhanced Pseudo-Random Number Generators | Final API present in Java 17 | [JEP 356](https://openjdk.org/jeps/356), `java.util.random` Javadoc |

A classic example: Java 17 supports standard `switch` expressions standardized earlier, whereas **pattern matching in `switch`** is preview in Java 17. Do not read an overview of `switch` from a newer Java release and assume every `case Type x -> ...` syntax runs by default in Java 17.

If you **deliberately experiment** with a preview feature on JDK 17, you must enable preview at both compile time and runtime:

```bash
javac --enable-preview --release 17 PreviewExample.java
java --enable-preview PreviewExample
```

Preview features can change between Java releases; class files compiled with preview features also carry version restrictions. In code meant to remain stable on Java 17, prefer finalized features and confirm support constraints before using preview features.

## 6. Reading Release Notes for the Right Version and Purpose

Release Notes answer **“What changed in this JDK release?”**; they typically cover new features, behavioral changes, compatibility issues, JVM option changes, deprecated/removed features, bug fixes, security notes, and known issues.

### 6.1. Distinguish the initial release from update releases

- **Java/JDK 17 GA:** check the [JDK 17 Release Notes](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html) to understand major changes when moving to Java 17 from earlier releases.
- **JDK 17.0.x:** check the [JDK 17 Release Notes index](https://www.oracle.com/java/technologies/javase/17u-relnotes.html) and choose the **exact update number** you are running. Specific patches may alter certificates, time zones, security behavior, or bug fixes.
- **Other distributions:** consult your JDK vendor's release notes/advisories for patches, support schedules, build configurations, and packaging differences.

Reading only the initial `17` release notes can miss changes in `17.0.x`; conversely, reading release notes for a newer JDK does not mean those changes automatically exist in Java 17.

### 6.2. Workflow for diagnosing upgrade failures

Suppose an application uses reflection on JDK internal details and throws `java.lang.reflect.InaccessibleObjectException` after moving to Java 17.

1. Record `java -version`, JDK vendor, update version, OS, and the full stack trace.
2. Search the Java 17 Release Notes for keywords like `encapsulation`, `internal API`, and `reflection`.
3. Read [JEP 403 — Strongly Encapsulate JDK Internals](https://openjdk.org/jeps/403) to understand internal JDK encapsulation changes in Java 17.
4. Identify the library or line of code depending on JDK internals; use `jdeps` to find static dependencies where applicable.
5. Replace with supported public APIs or upgrade the library. If it cannot be fixed immediately, a targeted `--add-opens` option **specifying the exact module/package** may be needed after auditing the actual dependency; that is a narrow compatibility bridge, not a long-term API substitute.

Example diagnostic tools:

```bash
jdeps --jdk-internals path/to/app.jar
jdeprscan --release 17 path/to/app.jar
```

`jdeps --jdk-internals` detects certain dependencies on JDK internal APIs via bytecode analysis; it is not guaranteed to catch all dynamic reflective accesses. `jdeprscan` scans for APIs marked deprecated based on the tool's catalog. Read the output alongside stack traces, the dependency tree, and the relevant library's upgrade notes. See also the [JDK 17 tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/index.html).

A common pitfall: the `--illegal-access` option from earlier transition releases **no longer effectively relaxes encapsulation on JDK 17**. Do not blindly reuse legacy instructions when fixing Java 17 compatibility issues.

### 6.3. Reading deprecated, for removal, and removed statuses

These three terms have distinct meanings:

- **Deprecated:** the API/feature may still be present, yet is discouraged for new code; check the docs for replacements.
- **Deprecated for removal:** slated for removal in a future release, yet **does not mean it has already been deleted from JDK 17**.
- **Removed:** the stated API/feature is no longer present in that release; code or dependency configuration must be updated.

For example, JEP 411 marks **Security Manager as deprecated for removal in Java 17**; that is an API lifecycle notice and must not be misread as “Security Manager was already removed in Java 17.” When working on real applications, cross-check both the API Docs and Release Notes for the exact version.

## 7. Six-Step Lookup Workflow: From Question to Verifiable Answer

Apply these six steps to any technical question:

1. **Rewrite the question concretely.** For example: “In Java 17, does `Stream.toList()` allow `add()`?” instead of “Stream is broken.”
2. **Identify the environment.** Record `JDK 17.0.x`, vendor, runtime, compiler version, and the project's `--release` setting.
3. **Choose the primary source.** Syntax/types → JLS; methods/libraries → Javadoc; changes between JDK releases → Release Notes; feature goals and status → JEP.
4. **Read the exact clause or API signature.** Check normative wording, exceptions, `Since`, `Deprecated`, and `Preview`; be careful not to treat implementation details as the contract.
5. **Verify with a minimal example on Java 17.** If it is a compatibility error, reproduce it in the same JDK and dependency environment. Empirical tests aid diagnosis, yet do not replace the specification.
6. **Record the conclusion with its source.** Note the versioned URL, JLS section or method signature, patch version if relevant, and lookup date for long-lived documentation.

### Useful lookup note template for a project

```text
Question: Can elements be added to the list returned by Stream.toList()?
Environment: JDK 17, built with --release 17
Source: Java SE 17 API Docs → java.util.stream.Stream → toList()
Contract: result is unmodifiable; mutators throw UnsupportedOperationException
Solution: use Collectors.toCollection(ArrayList::new) if a mutable List is needed
Verification: compiled and ran a minimal example on JDK 17
```

For a `sealed` syntax error, you can record the source as “JLS SE 17 §8.1.1.2, §8.1.6”; for a post-upgrade failure, record “JDK 17 Release Notes + JEP 403 + specific update version and vendor.” This helps teammates re-verify conclusions months later when maintaining code.

## 8. Mistakes to Avoid When Reading Java 17 Documentation

| Common Mistake | Correct Practice |
| --- | --- |
| Search results open Java 21/25/26 API Docs while the project runs Java 17. | Check the address bar for `/java/javase/17/`; if a method does not exist on the Java 17 page, do not assume you can use it. |
| Reading a blog post on newer Java syntax and assuming Java 17 already supports it. | Check the JEP, preview status, and Java SE 17 JLS. |
| Thinking `Since: 16` means the API is only for Java 16. | Understand `Since` as the first release where it appeared; verify the API is still present in Java 17 Javadoc. |
| Seeing one example return an `ArrayList` and assuming the method always guarantees an `ArrayList`. | Read *Returns*, *Implementation Note*, and guarantees on list type, mutability, null handling, and thread safety. |
| Reading only the GA Release Notes when a bug appears in a `17.0.x` patch. | Read the release notes for the **exact patch version** and JDK vendor. |
| Reusing workarounds from JDK 8/11 without re-verifying. | Prefer currently supported public APIs; cross-check the Java 17 Migration Guide and Release Notes. |
| Conflating deprecated, for removal, and removed. | Read the exact label and status applicable to **Java 17**, and plan migration when an API is deprecated. |
| Passing `-source 17` and accidentally calling platform APIs from a newer JDK. | When using a newer compiler, set `--release 17` or the equivalent build tool configuration. |

## 9. Guided Lookup Exercises

**Exercise 1 — Language rules.** Which classes are allowed to directly `implements` a `sealed interface`? Open JLS SE 17, locate the sections on sealed interfaces and permitted subclasses, and write an example with two permitted implementations. Explain why a third unpermitted class is rejected by the compiler.

**Exercise 2 — API contract.** Compare `Stream.toList()`, `Collectors.toList()`, and `Collectors.toCollection(ArrayList::new)` using the Java 17 Javadoc. For each API, note: return type, mutability guarantee, and what is **unspecified**.

**Exercise 3 — Feature status.** Check JEP 409 and JEP 406: which feature is enabled by default in Java 17, and which requires preview? Briefly explain why you should not extrapolate from newer Java syntax.

**Exercise 4 — Post-upgrade changes.** An application migrating from JDK 11 to JDK 17 hits a reflective access error. List the environment details to record, the Release Notes/JEP pages to consult, and how `jdeps` can aid investigation. Propose a fix based on supported public APIs.

Upon completing each exercise, accompany every answer with **an official documentation link for the exact Java 17 version and evidence from the specification clause or API contract**. That habit matters more than memorizing page names: it lets you independently verify facts as JDK versions, libraries, and technical docs continue to evolve.
