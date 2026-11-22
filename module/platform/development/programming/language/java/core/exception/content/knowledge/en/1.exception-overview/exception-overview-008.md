# Java Core Scope and How to Cross-Reference JDK Versions When Learning Exceptions

> Topic: Java Core – Exception · Group: Overview. Content applies to Java SE and the JDK, with version milestones cross-referenced as of 18/10/2026.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish which Exception knowledge belongs to the Java language, the Java SE standard library, the JVM, and JDK tools.
2. Identify which parts are relatively stable core rules and which parts depend on the Java version, patch release, or runtime environment.
3. Read Java documentation accurately by version; distinguish between compilation version, target API version, and the JVM version running the application.
4. Independently verify an exception handling example across multiple JDKs using concrete commands, rather than guessing from error messages.

## 2. What Does "Java Core" Mean in the Context of Exceptions?

```text
Java Core (a learning term, not the name of an independent specification)
├── Java Language Specification (JLS)
│   └── throw, throws, try, catch, finally, checked/unchecked,
│       multi-catch, try-with-resources
├── Java SE API
│   └── Throwable, Exception, Error, RuntimeException,
│       IOException, AutoCloseable, APIs that may throw exceptions
├── JVM / Java Virtual Machine Specification (JVMS)
│   └── bytecode loading/execution, class initialization, class linkage errors,
│       stack traces and runtime behavior governed by the specification/implementation
└── JDK
    └── javac, java, javap, API documentation, diagnostic tools
```

"Java Core" usually refers to the Java fundamentals you need to know before using frameworks; this term is **not** synonymous with a module, a release, or an official specification suite. To cross-reference Exception behavior, you need to determine which layer it belongs to:

| Layer | Question to ask | Appropriate reference source |
| --- | --- | --- |
| Syntax and compile-time checks | Is `throws` required? Is `catch` valid? | JLS for the exact version, especially the chapters on exceptions and `try` |
| Standard library | Does the method declare `throws IOException`? | Java SE API docs by version and exact overload |
| JVM / runtime | How do class loading errors, stack traces, and `NullPointerException` messages behave? | JVMS, JEPs, release notes, and testing on the target JVM |
| Tools | What can `javac --release` check? | The `javac` manual for the exact JDK in use |
| External libraries/frameworks | What type does an API wrap an exception into? | Documentation and version of that library itself |

For example, `java.io.IOException` is an exception type belonging to the standard API; the rule requiring checked exceptions to be handled or declared is a language rule; whereas the string in `getMessage()` may depend on where it is thrown and the implementation version.

### Core Topics to Master

- The `Throwable` inheritance hierarchy; distinguishing checked exceptions, unchecked exceptions, and `Error`.
- How to throw (`throw`), declare (`throws`), catch, and propagate exceptions; `catch` ordering, multi-catch.
- `try`/`catch`/`finally`; `try-with-resources`, `AutoCloseable`, and suppressed exceptions when closing resources.
- Cause (`getCause()`), suppressed exceptions (`getSuppressed()`), stack traces; wrapping exceptions while preserving the original cause.
- API boundaries: `IOException`, `NumberFormatException`, `ClassNotFoundException`, `InterruptedException`, `IllegalArgumentException` are familiar examples. Retry policies, HTTP errors, transactions, or Spring's `DataAccessException` require consulting the specific framework/library contract.

## 3. Foundational Exception Rules

```text
java.lang.Throwable
├── java.lang.Error                       unchecked
│   └── e.g., LinkageError, OutOfMemoryError
└── java.lang.Exception
    ├── java.lang.RuntimeException        unchecked
    │   └── e.g., IllegalArgumentException, NullPointerException
    └── checked branches
        └── e.g., IOException, ReflectiveOperationException
```

According to the JLS, an exception type is **checked** if it is a `Throwable` (or a subclass thereof) that is **not** `RuntimeException`, `Error`, or any of their subclasses. The compiler requires handling or declaring checked exceptions that a call or method may throw according to Java's exception analysis rules. `RuntimeException` and `Error` (along with their subclasses) are **unchecked**, so they are not subject to this `catch`/`throws` requirement.

Note the following distinctions:

- `throw new IOException("...")` actually creates and throws an exception object; `throws IOException` only declares the possibility of it being thrown out of a method or constructor.
- With `catch (Exception e)`, `RuntimeException`s can also be caught, whereas `Error` is not a subclass of `Exception`. You should not habitually catch `Error` to "save" an application from severe failures.
- When there are multiple `catch` clauses, a clause for a subclass must precede a clause catching its superclass. An unreachable clause because a preceding clause already catches everything results in a compile-time error.
- `finally` normally executes when leaving `try`/`catch`, though it is not guaranteed in all situations such as abrupt JVM termination. Avoid `return` or throwing a new exception inside `finally` because it can mask the return value or the original exception.
- When handling `InterruptedException`, merely catching and ignoring it is usually wrong; let it propagate or consider restoring the interrupt flag with `Thread.currentThread().interrupt()` if it cannot be rethrown.
- A checked exception does not mean an error "will definitely happen"; an unchecked exception does not mean "no handling needed". Handling decisions depend on the API contract and recoverability.

Example illustrating the compile-time contract, **this is only a method snippet, not a standalone program**:

```java
import java.io.IOException;

static String readValue() throws IOException {
    throw new IOException("Không đọc được dữ liệu");
}

static void process() {
    try {
        System.out.println(readValue());
    } catch (IOException ex) {
        System.out.println("Đã xử lý: " + ex.getMessage());
    }
}
```

If you remove `catch` in `process()`, you must declare `throws IOException` on `process()`, otherwise compilation fails. You do not need `throws` just to throw `IllegalStateException` because it is an unchecked exception. Do not apply the same assumption across all versions of an API method: always read the declaration for the exact version.

## 4. Table of JDK Milestones Relevant to Exceptions

| Java SE / JDK Milestone | Points to cross-reference when learning Exceptions | What not to over-conclude |
| --- | --- | --- |
| 7 (2011) | `try-with-resources`; `AutoCloseable`; suppressed exceptions; multi-catch (`catch (A \| B e)`), certain exception type inference rules on rethrow | Not all resources close automatically; only objects compatible with `AutoCloseable` inside the resource management construct |
| 8 (2014) | Java 7 Exception mechanisms continue to apply; this is a common legacy baseline requiring compatibility | Do not assume APIs or syntax introduced in Java 9+ are available |
| 9 (2017) | Pre-declared `final` or effectively final variables can be used in `try (resource)`; the module system affects class lookup/loading; `javac --release` introduced | Not every classpath/module error behavior is a "new Exception" |
| 11 (2018, LTS) | Common milestone for checking application compatibility; standard APIs added since 8, e.g., `Files.readString` from Java 11 | Having an API on 11 does not mean it runs on a Java 8 runtime |
| 14 (2020) | JEP 358 added helpful `NullPointerException` messages, initially requiring a VM option to enable | Message content is not a stable interface for applications to parse |
| 15 (2020) | `ShowCodeDetailsInExceptionMessages` enabled by default in JDK 15 HotSpot | Manually created `new NullPointerException("...")` does not automatically get the expression description like a JVM-generated NPE |
| 17 (2021, LTS) | Common baseline for building/testing modern Java; core checked/unchecked rules continue | Do not attribute every JDK 9–17 change to `try/catch` syntax itself |
| 21 (2023, LTS) | Another LTS runtime milestone requiring re-running error-handling, API, and dependency tests | Do not assume every stack trace or library behavior will be identical to 17 |
| 25 (2025, LTS) | Latest LTS milestone as of 18/10/2026, relevant when choosing a long-term target | "LTS" is a release support model, not a type of Exception mechanism |
| 27 (15/09/2026, feature release) | Latest GA JDK as of 18/10/2026; cross-reference release notes and test in practice if used | The latest version is not automatically the right deployment choice for every organization |

Years and milestones only help you select documentation; they **cannot** replace checking the JLS, API docs, and release notes for both the specific version and patch updates (e.g., 17.0.x, 21.0.x). Oracle JDK, OpenJDK builds, and other vendor distributions also have different support policies and configurations.

### Changes Worth Remembering

**Java 7: multiple exceptions and safer resource management.** `try-with-resources` closes resources in the reverse order of their opening; if the `try` body has already thrown an exception, errors from `close()` are typically attached to the primary exception as `suppressed`. `Throwable.getSuppressed()` reads this array. Multi-catch reduces code duplication when different error types share the same handling logic; types within the same multi-catch must not have a subclass–superclass relationship.

**Java 9: reusing resource variables.** Starting in Java 9, you can write `try (reader)` if `reader` is an already assigned, valid variable that is not reassigned (final/effectively final). On Java 7/8, a resource declaration is required inside the parentheses, such as `try (BufferedReader in = reader)`.

**Java 14/15: more helpful NPE messages.** HotSpot added details about the null dereference operation per JEP 358. Java 14 had the opt-in flag `-XX:+ShowCodeDetailsInExceptionMessages`; starting in JDK 15, HotSpot enables it by default. Messages depend on bytecode and context; manually instantiated NPEs, disabling the option, or bytecode lacking debug info may produce different results. Tests should assert **exception type, cause, and behavior**, avoiding exact assertions on the full message string.

**Newer LTS milestones:** Core rules for `throw`, `throws`, `catch`, and checked/unchecked are not redefined with every release. However, APIs, runtime, classpath/modules, libraries, JVM flags, bug fixes, and diagnostic details can change. Therefore, always separate "language rules" from "specific application behavior".

## 5. Runnable Example from Java 7+: Primary and Suppressed Exceptions

Create `ExceptionScopeDemo.java`:

```java
import java.io.IOException;

public class ExceptionScopeDemo {
    static final class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            System.out.println("close");
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (Resource resource = new Resource()) {
            System.out.println("work");
            throw new IllegalStateException("work failed");
        } catch (Exception ex) {
            System.out.println("primary="
                    + ex.getClass().getSimpleName() + ": " + ex.getMessage());

            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("suppressed="
                        + suppressed.getClass().getSimpleName()
                        + ": " + suppressed.getMessage());
            }
        }
    }
}
```

Compile/run on a JDK that supports `--release 8` (e.g., JDK 17):

```bash
javac --release 8 ExceptionScopeDemo.java
java ExceptionScopeDemo
```

On JDK 8, use `javac ExceptionScopeDemo.java` because the JDK 8 compiler does not have `--release`. Exact standard output:

```text
work
close
primary=IllegalStateException: work failed
suppressed=IOException: close failed
```

Explanation: `IllegalStateException` from the `try` body is the primary exception; `close()` still runs and throws `IOException`; the exception during closing is attached to `getSuppressed()`, without erasing the original error cause. Because it explicitly prints the type and message instead of the full stack trace, the example produces more stable output across JDK versions. This is not an example of `getCause()`: **cause** represents the causal relationship when wrapping an exception, whereas **suppressed** describes additional errors, typically from closing resources.

## 6. Example Distinguishing Java 8 and Java 9 Syntax

Create `ReuseResourceDemo.java` (requires Java 9+):

```java
import java.io.BufferedReader;
import java.io.StringReader;

public class ReuseResourceDemo {
    public static void main(String[] args) throws Exception {
        BufferedReader reader = new BufferedReader(new StringReader("hello"));
        try (reader) {
            System.out.println(reader.readLine());
        }
    }
}
```

```bash
javac --release 9 ReuseResourceDemo.java
java ReuseResourceDemo
```

```text
hello
```

When trying `javac --release 8 ReuseResourceDemo.java` on a compiler that supports both release 8 and 9, the `try (reader)` syntax is rejected at the Java 8 source level. For Java 8, rewrite the `try` part as follows (replacement snippet in the program above):

```java
try (BufferedReader managed = reader) {
    System.out.println(managed.readLine());
}
```

The `close()` method still works according to the resource contract. The difference here belongs to **syntax allowed by the source version**, not because `BufferedReader` was invented in Java 9.

## 7. Distinguishing Compilation JDK, Target API, and Execution JVM

Three things must be stated explicitly whenever reporting "code runs on Java X":

| Component | Example | Meaning |
| --- | --- | --- |
| JDK used to compile | `javac 17.0.x` | Determines the compiler and which `--release` targets are supported |
| Target Java SE/API version | `--release 8` | Restricts Java 8 syntax, class-file target, and the corresponding platform API |
| JVM used to run | `java 8`, `java 17`, or `java 21` | Determines the runtime environment, API implementation, diagnostics, dependencies, and execution |

Check the current machine:

```bash
java -version
javac -version
javac --help
```

`java -version` typically prints to stderr; `java --version` is the long-form syntax introduced in Java 9. `javac --help` shows the `--release` levels supported by **that specific javac version**; do not assume a very recent compiler still supports every older level.

With JDK 9+ when the compiler still supports target 8:

```bash
javac --release 8 ExceptionScopeDemo.java
java ExceptionScopeDemo
```

`--release 8` simultaneously enforces Java 8 syntax, Java 8 bytecode format, and the platform API available in Java 8. Using only `-source 8 -target 8` with a newer JDK is **not equivalent** unless you control the standard API set visible to the compiler; the program could accidentally call an API that only exists on the newer JDK. For larger projects, configure `release` in Maven/Gradle and run CI on the target JVM.

Concrete API example: `Files.readString(Path)` was introduced in Java 11. A program calling that method is invalid when checking against the Java 8 target API even though the method-call syntax looks identical to Java 8. Conversely, the `try (reader)` example earlier fails with `--release 8` due to **syntax**. The two cases can produce different compile-time errors and should not be conflated.

### Forward/Backward Compatibility and Class Files

Bytecode compiled for a newer Java version can be rejected by an older runtime with `UnsupportedClassVersionError` (a `LinkageError`, i.e., an `Error`). Common class-file major versions: Java 8 = 52, 11 = 55, 17 = 61, 21 = 65, 25 = 69, 27 = 71. This is a **diagnostic** tool, not a guarantee that "matching the major version is enough to run": the runtime also needs compatible APIs, modules, native libraries, dependencies, and environment.

For Java 8 source running on a newer JDK, compatibility is generally good but not absolute. Upgrading the JDK can expose removed APIs, restricted JDK internal access, different encryption/security configurations, or runtime changes; read migration guides and run tests.

## 8. Process for Cross-Referencing JDK Versions for an Exception Issue

When encountering a discrepancy, follow these steps in order:

1. **Document the test case clearly:** full exception name (e.g., `java.lang.NoClassDefFoundError` rather than just "class error"), minimal source code, inputs, expected result, and actual result.
2. **Capture the three versions:** output of `java -version`, `javac -version`, `--release`/build tool configuration; include OS and dependency versions when relevant.
3. **Classify the source of the change:** compiler error (checked/unchecked, `catch`, syntax) → JLS; API type/contract → API docs; class loading/VM message → JVMS/JEP/release notes; external library behavior → library release notes.
4. **Cross-reference documentation for the exact milestones:** read the JLS and API docs for both old and new versions; check "Since", `@since`, `throws`, side-effect descriptions, release notes, and migration guides. Do not rely solely on a blog post saying "newer Java changed Exceptions".
5. **Compile under controlled settings:** on an appropriate compiler, test `--release N`, keeping in mind it does not replace running on JVM N. If the compiler no longer supports N, use a toolchain/JDK that supports N.
6. **Run the same test suite on the supported runtimes:** verify the exact exception type, resource handling/closing order, cause/suppressed, and recovery behavior; use an equivalent isolated environment when needed.
7. **Record an evidence-backed conclusion:** state which version the behavior changed in, reproduction steps, documentation lines or official issues, and the code/configuration change that resolves it.

Minimal test matrix you can use when upgrading from JDK 8 to 17/21/25:

| Test case | Verification expectation |
| --- | --- |
| Checked `IOException` | Compiler requires catching or declaring when a method can throw it; code handles the flow properly |
| Unchecked `IllegalArgumentException` | No mandatory `throws` needed; catch at application boundary if recoverable |
| `try-with-resources` when `close()` also fails | Primary exception is preserved; closing exception appears in `getSuppressed()` |
| `try (reader)` syntax | Valid from Java 9; invalid with source target 8 |
| `NullPointerException` from dereference | Message may vary by JVM; test by exception type and behavior |
| Java 11+ only API | `--release 8` build is rejected even if running on a newer JDK |
| Class loading/dependency errors | Check both `ClassNotFoundException` (checked) and `NoClassDefFoundError` (`Error`) in the right context |

Difference between the last two errors: `ClassNotFoundException` typically comes from explicit class-loading operations like `Class.forName`; `NoClassDefFoundError` typically occurs when the JVM cannot define/initialize a required class during use, including cases where the class is missing or a prior class initialization failed. They belong to different branches of the `Throwable` hierarchy, so do not lump them into a single `catch (Exception)` assuming both are handled.

## 9. Common Learning and Implementation Mistakes

- **Treating Java Core as a single standalone version:** use "Java SE N" or "JDK N, vendor, update" when making specific conclusions.
- **Using newer Java docs to draw conclusions about Java 8:** open the corresponding API/JLS; pay attention to `@since` and removed APIs.
- **Only looking at `java -version`:** the CLI `javac`, Maven/Gradle toolchain, and the Java binary used to run the app can differ.
- **Confusing compile-time errors with runtime exceptions:** an unhandled checked exception can prevent the program from compiling; it is not an `Exception` object thrown at runtime.
- **Catching `Exception` or `Throwable` too broadly:** easily hides logic bugs, mishandles `InterruptedException`, or accidentally swallows severe errors. Only catch errors that the current layer is responsible for handling.
- **Matching `getMessage()`/stack traces verbatim in tests:** runtime details, paths, line numbers, locale, and configuration can differ; test the contract instead of unguaranteed display strings.
- **Assuming `finally` is always safe when throwing errors:** an exception or `return` in `finally` can lose the original error information; prefer `try-with-resources` for eligible resources.
- **Equating cause with suppressed:** use `getCause()` to trace wrapped errors, and `getSuppressed()` to inspect additional errors such as those from closing resources.
- **Assuming compiling with `--release 8` means it is tested on Java 8:** it controls source/API/class file compatibility, but you still need to run tests on an actual Java 8 runtime with the target dependencies.

## 10. Knowledge Self-Check

1. Why must `IOException` usually be caught or declared while `IllegalStateException` does not? Answer based on the `Throwable` hierarchy, not the class names.
2. If both the `try-with-resources` body and `close()` throw exceptions, which object is primary and which one is in `getSuppressed()`?
3. Why does `try (reader)` work on Java 9+ but need to be rewritten when compiling for Java 8?
4. Does a program that compiles cleanly with `javac --release 8` on JDK 17 prove it runs properly on JVM 8? What else needs to be checked?
5. When migrating from JDK 8 to JDK 21 and noticing that the `NullPointerException` message changed, which documentation should you read and what kind of assertion should you update in tests?

Answer hints: (1) checked vs. unchecked; (2) the body's error is primary, the closing error is suppressed; (3) Java 9 extended syntax; (4) no, must run tests on runtime 8 with the appropriate dependencies; (5) JEP 358, release notes, avoid hardcoding the message in assertions if the API does not guarantee it.

## 11. Primary References for Cross-Checking

- Java Language Specification: https://docs.oracle.com/javase/specs/ (select the exact Java SE version; §14, §11, and relevant `try`/`throw`/`throws` sections).
- Java SE API docs: https://docs.oracle.com/en/java/javase/ (select `java.lang.Throwable`, `AutoCloseable`, and the target package by version).
- Oracle: Java SE 7 try-with-resources and suppressed exceptions: https://www.oracle.com/technical-resources/articles/java/trywithresources.html
- Java 9, concise resource syntax: https://docs.oracle.com/en/java/javase/13/language/try-resources.html
- OpenJDK JEP 358 – Helpful NullPointerExceptions: https://openjdk.org/jeps/358
- JDK 15 release notes on default NPE flag: https://www.oracle.com/java/technologies/javase/15all-relnotes.html
- `javac`, `--release`, and compatibility limits: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html
- Release notes index for comparing JDK 8–27: https://www.oracle.com/java/technologies/javase/jdk-relnotes-index.html
- JDK 27 GA on 15/09/2026: https://www.oracle.com/java/technologies/javase/27all-relnotes.html

**Completion criteria:** Given a specific Exception issue, you can identify the responsible layer (language/API/JVM/library), the applicable JDK milestone, the required compile and runtime commands, a reproducible test, and an authoritative reference source for your conclusion.