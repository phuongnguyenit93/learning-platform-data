# How to Read Documentation by JDK Version and Separate Rules from Implementation Details

When learning the JVM, the same descriptive statement can be a **mandatory rule of Java**, a **contract of an API**, a **capability of a JDK version**, or merely **how a specific JVM is currently implemented**. Confusing these four categories leads to wrong conclusions when switching from Java 17 to 21, upgrading to a JDK from another vendor, or tuning program runtime flags. The goal of this lesson is to find the right documentation for the right version and know exactly what is guaranteed.

## 1. Distinguish Documentation Layers and Described Subjects

| Question | Source to read first | Type of conclusion that can be drawn |
| --- | --- | --- |
| Java syntax, data types, overloading, class initialization, Java Memory Model? | **JLS** (Java Language Specification) of the corresponding Java SE | Java language rules, e.g., when an assignment is valid and happens-before constraints |
| Bytecode, `.class` structure, loading/linking, runtime data areas, JVM instructions? | **JVMS** (Java Virtual Machine Specification) of the exact version | Constraints on a specification-compliant JVM; does not by default mandate implementation algorithms |
| What do `HashMap`, `LinkedHashMap`, `Thread`, `String` guarantee? | **Java SE API Specification/Javadoc** of the exact version | Public API contract, exceptions, ordering, usage conditions |
| What options do `java`, `javac`, `jcmd` have? | **JDK tool guides/man pages** of the JDK in use | How to invoke the tools and the scope of support for that version/distribution |
| When was a feature introduced, standardized, or still in preview? | **Release notes**, feature documentation, and **JEP**, cross-checked against the final specification | History, motivation, status changes; a JEP does not replace a released API contract/specification |
| Which collector, JIT, object layout, or optimization thresholds does HotSpot use? | **Specific VM documentation**, options/help, source code, and measurements on the exact build | Implementation behavior under defined conditions; do not generalize to all JVMs |

**JDK** is the toolset/distribution used to develop and run applications; **Java SE** is the platform with specifications and APIs; **JVM** is the virtual machine that executes class files; **HotSpot** is one JVM implementation. A JDK typically contains HotSpot, but HotSpot must not be equated with the JVMS itself. Saying “the JVM always uses C2/G1” or “every object always has a 12-byte header” is wrong about the scope of the guarantee.

A passage in documentation should be recorded together with its **version, documentation type, and statement scope**. “Java 17” must be clarified as the Java SE 17 specification, the JDK 17 compiler, or a specific 17 runtime build.

## 2. Lock the Exact Version Before Reading

On both the build machine and the runtime machine, check independently:

```text
java -version
javac -version
java -XshowSettings:properties -version
```

- `java -version`: the runtime selected by PATH or the current path; typically displays version, vendor/build, and VM.
- `javac -version`: the selected compiler; may belong to a different JDK from the `java` command.
- In the properties output, inspect `java.version`, `java.vendor`, `java.vm.name`, `java.home`; actual values depend on the environment. If using an IDE, Gradle, Maven, a container, or CI, check the **actual JDK** that tool invokes.
- Also record the operating system, architecture, vendor, build/patch, and VM flags if comparing performance or GC behavior.

Numbers to distinguish:

1. **Language version**: the syntax accepted by the compiler, e.g., Java 17.
2. **Public API version**: the methods/classes allowed to be called on the target platform.
3. **Class file version**: the bytecode format that the JVM can load.
4. **Actual runtime version**: the JVM and libraries running in production.

Examples of corresponding class-file major versions: Java 8 → 52, Java 11 → 55, Java 17 → 61, Java 21 → 65, Java 25 → 69, Java 27 → 71. This is the class file format version introduced, **not** definitive proof of which JDK produced the file: a newer JDK compiler can emit bytecode for an older target.

When compiling for a Java 17 runtime using a `javac` that supports release 17, one typically uses:

```bash
javac --release 17 ReadContracts.java
javap -verbose ReadContracts
java ReadContracts
```

In `javap -verbose`, look for the line `major version: 61`. The `--release 17` option restricts the language version, class file format, **and documented platform API** that the compiler allows using. Setting only `-source 17 -target 17` is not enough to ensure you do not accidentally reference an API that only exists on a newer JDK. `--release` also does not prove that all external libraries, native libraries, and environment behaviors are compatible with Java 17; you must build/test with the target runtime.

Running a class file requires support for the corresponding major/minor version. `UnsupportedClassVersionError` usually indicates the runtime cannot read the class file version; before concluding, check the major version line, the actual runtime in use, and whether the project uses a **preview feature** (preview class files have their own rules, and may require `--enable-preview` and the exact release).

## 3. Finding Documentation Along a Verifiable “Path”

**Step 1 — Identify which category the question belongs to.** For example: “Does the JVM require storing objects on the heap?” relates to JVMS/JLS; “Which GC is the default?” relates to the build's VM options; “Does `Map` have a stable iteration order?” requires reading the API contract of the specific `Map` implementation.

**Step 2 — Choose the edition, not just the first search result.** Specification pages usually have `se17`, `se21`, `se27`; Javadoc/man pages are usually under `/en/java/javase/17/`, `/21/`, etc. Do not combine a JLS 17 quote with an API 27 excerpt and treat them as the same contract. When the problem involves *two* runtimes, open **both** documentation versions and compare the corresponding clauses.

**Step 3 — Read the normative text verbatim in context.** Check headings, preconditions, exceptions, “must/shall”, “may”, “typically”, “implementation note”, “since”, “deprecated”, “preview”, “unspecified”, “implementation-specific”. Do not turn words like “typically”, “may”, or “for example” into “always” or “mandatory”. Code examples in documentation help clarify rules but do not necessarily cover every case.

**Step 4 — Cross-check version changes.** From design requirements or feature docs, go to the final specification/Javadoc of that exact release; use release notes to identify modifications, removals, or default changes. If there is a JEP, check its status and target release, especially for preview/incubator features.

**Step 5 — Verify actual behavior when the question is about performance.** Record the JVM vendor/build and startup flags, and reproduce the benchmark/profile on the exact machine. A single observation cannot “promote” a HotSpot detail into a Java rule.

### Strength of Evidence

Conclusions can be phrased using the template: “**According to [document + edition + section], under [condition], behavior [X] is guaranteed/not guaranteed; observation [Y] belongs to [runtime/build]**”.

| Signal in documentation | Safe interpretation |
| --- | --- |
| JLS/JVMS rule or mandatory requirement in the API | What every compliant implementation within that scope must satisfy |
| Javadoc describing a specific order/exception/case | Contract for that class/method and stated conditions; do not generalize to other classes |
| `Implementation Note` or “in this implementation” | Information about the current implementation, which may change across JDKs/builds |
| “Typically”, “usually”, “may” | Describes a common case/possibility; not a guarantee every time |
| “No guarantee”, “unspecified” | The program **must not depend** on that value/order, even if it is observed repeatedly |
| JEP, bug ticket, blog post, benchmark | Historical explanation or observation; cross-check against standard documentation and the released version |

“Unspecified” does not mean a random bug: an implementation may produce the same result for a long time, yet the public contract does not promise that result. Conversely, “implementation-dependent” does not allow claiming any arbitrary behavior is valid; the implementation must still satisfy other mandatory constraints.

## 4. Example 1 — A Result That Works on My Machine Is Not Yet an API Contract

The Java 17 Javadoc for `HashMap` explicitly states it makes **no guarantees** as to the order of elements and does not guarantee that the order will remain constant over time. The `LinkedHashMap` Javadoc describes predictable iteration order; with the default constructor, that is key insertion order.

Create the file **`ReadContracts.java`**:

```java
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

public class ReadContracts {
    public static void main(String[] args) {
        Map<String, Integer> ordered = new LinkedHashMap<>();
        ordered.put("beta", 2);
        ordered.put("alpha", 1);
        System.out.println(ordered.keySet());

        Map<String, Integer> unordered = new HashMap<>();
        unordered.put("beta", 2);
        unordered.put("alpha", 1);
        System.out.println(unordered.containsKey("alpha"));
    }
}
```

Compile/run on JDK 17 or later supporting `--release 17`:

```bash
javac --release 17 ReadContracts.java
java ReadContracts
```

**Stdout**:

```text
[beta, alpha]
true
```

- The first line is stable under the contract of `LinkedHashMap` using insertion-order mode. If choosing the `accessOrder=true` constructor, the ordering rules differ; always read the exact constructor.
- The second line only asks whether `HashMap` contains the key. Do not take the order of `unordered.keySet()` printed on one machine to write tests or business logic.
- A class file compiled with `--release 17` has major version 61; the fact that the source code runs fine on a JDK 27 does not mean this contract was read from “Javadoc 27”. What is being demonstrated here relies on the Java 17 API.

How to fix code that depends on the wrong contract: if the UI/JSON/report needs insertion order, choose a structure that guarantees ordering and write tests according to the contract; if only key lookup is needed, do not tie tests to `HashMap` order.

## 5. Example 2 — Distinguish Standard Memory Areas from HotSpot Storage

The JVMS describes **run-time data areas** such as the heap, Java Virtual Machine stacks, method area, run-time constant pool, and related constraints. The specification makes clear that a JVM is free to choose various storage organizations to satisfy observable requirements.

Separate two statements:

- **Specification level:** The JVM provides a heap as a memory area shared among all threads for allocating class instances and arrays; this area is automatically managed, and the JVM is not required to choose a specific garbage collection algorithm.
- **Implementation level:** on a HotSpot build, an object has an object header of a certain size, the JVM uses compressed references or a specific collector, or the JIT compiles a method after a number of invocations. These are choices tied to the build/configuration/architecture.

Therefore, from the heap diagram in the JVMS **it does not follow** that every object has the same number of bytes, has a stable observable address, must use G1, must be JIT-compiled, or is represented with a fixed layout. If the question is “Why does the application consume X MB?”, use a profiler/GC logs/HotSpot documentation and the specific configuration, rather than citing only the heap definition from the specification.

Similarly, the fact that a GC is the **default** in one JDK does not imply that the Java standard forces other JVMs to choose that GC. Defaults and VM flags can change by version, platform, or vendor.

## 6. Example 3 — Distinguish Feature Introduction from Target Runtime Availability

Suppose the development team wants to use virtual threads. Ask sequentially:

1. In which release is the feature finalized, or is it still in preview? Read the JEP history, then confirm the API in the Javadoc of the target release.
2. Are the compiler, build tool, and production runtime at the same release level?
3. Does code using that API pass `javac --release <production-version>`? For example, the standard virtual threads API was finalized in Java 21; code using `Thread.ofVirtual()` is not in the Java SE 17 API.
4. Which behavior constraints are public API, and what is merely scheduling, pinning, or a current choice of one VM? Read the corresponding documentation instead of guessing from a thread dump snapshot.

Do not treat a JEP as an immutable contract from the time it is proposed: a feature can go through preview rounds and change before becoming finalized. If the application only supports Java 17, having JDK 21/27 installed on a developer's machine does not automatically expand production's API.

## 7. Separate “It Runs” from “It Is Guaranteed” When Upgrading the JDK

Compatibility dimensions must be examined **separately**, avoiding lumping them into a single phrase “Java is backward compatible”:

| Dimension | Verification question | Evidence to gather |
| --- | --- | --- |
| Source compatibility | Does old source code still compile? Have keywords/language/preview features changed? | JLS and `javac` documentation of the target release |
| Binary compatibility | Can old class files still load and link? Have API signatures changed? | JVMS class-file/loading and JLS binary compatibility, release notes |
| API compatibility | Are used public methods/classes/modules still present, and have their contracts changed? | Version-matched Javadoc, `@since`, deprecation/removal notes |
| Runtime behavior | Is the program still correct despite differences in unspecified ordering, timing, GC, locale, etc.? | Specification + tests on the target runtime |
| Operational compatibility | Do JVM flags, logging, monitoring, container limits, or vendor/build differ? | Man pages, VM guide, and operational testing |

Running stably across multiple versions is **useful empirical evidence** but weaker than a documented guarantee. Conversely, if a scenario depends on an unspecified detail, a program can “pass” for years before breaking due to a JDK change or data volume.

## 8. How to Take Auditable JVM Knowledge Notes

For each technical statement, record a traceable entry:

```text
Claim: LinkedHashMap iterates in insertion order by default.
Scope: Java SE 17 API; java.util.LinkedHashMap; default constructor.
Source: Java SE 17 Javadoc, class and constructor descriptions.
Guarantee: Insertion order for this case; does not imply HashMap has the same order.
Verification: ReadContracts.java on JDK 17 and target runtime.
Implementation detail: A linked list structure is described, but there is no need
                     to depend directly on node layout or byte size.
```

For a claim such as “HotSpot version X, architecture Y, with Z enabled uses an N-byte object header”, explicitly record the VM identification command, build, configuration, and measurement tool; do not turn it into “a JVM object is always N bytes”. When documentation differs across versions, present **before/after** and cite each version. If there is no guaranteeing source yet, mark it as an observation or hypothesis to be confirmed.

## 9. Common Documentation Reading Mistakes

- **Confusing “JVM” with “HotSpot”:** taking HotSpot's GC/JIT documentation as JVMS rules.
- **Confusing the installed JDK with the supported platform:** build machine is newer than production machine; missing `--release` and CI running on the target runtime.
- **Using the wrong Javadoc version:** relying on new APIs when the application still runs on older Java, or imposing old Java details onto a new version.
- **Turning examples into rules:** inferring from one output, a specific compiler's bytecode, a profiler screenshot, or one benchmark that every JVM must behave that way.
- **Omitting contract conditions:** `LinkedHashMap` insertion-order differs from access-order; configuration, concurrency, mutability, null, and exceptions can change the meaning of a conclusion.
- **Reading JEP titles without checking status:** confusing proposed/preview/incubator with a finalized feature in the release being used.
- **Mixing “works right now” with “long-term stability”:** relying on internal APIs, undocumented `-XX` flags, timing, and memory layout can cause failures upon upgrade.

## 10. Checklist for a Statement About Java/JVM

1. Have I identified the actual **JDK/compiler/runtime version, vendor, and build**?
2. Is the question about **the language, class-file/JVM, API, tools, or VM implementation**?
3. Which **edition** am I viewing, and which clause specifies that behavior?
4. Is the sentence I am citing **must/guaranteed**, or only “may/typically/implementation note”?
5. Are there constraints regarding constructors, options, OS, architecture, concurrency, or preview?
6. If upgrading from release A to B, have I compared **both** sets of documentation and tested on B?
7. Am I using a local observation as a general guarantee?

If you answer these seven questions clearly, you will distinguish between **rules you can rely on when writing code** and **characteristics that must be re-measured/re-verified when changing JVMs**.

## Primary Sources for Versioned Reference

- [Java SE Language and JVM Specifications — edition index](https://docs.oracle.com/javase/specs/): select the edition matching the Java SE being studied.
- [JLS Java SE 17](https://docs.oracle.com/javase/specs/jls/se17/html/): language rules, chapters on threads/memory model and binary compatibility.
- [JVMS Java SE 17](https://docs.oracle.com/javase/specs/jvms/se17/html/): JVM structure, class file, loading/linking, run-time data areas.
- [Java SE 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/index.html): read the contract of each class/method; directly compare [HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html) with [LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html).
- [Java SE 17 javac command documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release`, `-source`, `-target`.
- [OpenJDK JEP Index](https://openjdk.org/jeps/0): proposal history and status; always cross-check the specification/API in the shipped release.

**Reading principle:** cite the right source, the right edition, and the right conditions before deciding whether to depend on that behavior or treat it only as an implementation detail.
