# Java 17 Example Scope: Final, Applicable APIs Without Old Experimental APIs

> **Context:** Java 17 → Java 17 Orientation. Examples in this documentation and throughout learning prioritize finalized language features, documented Java SE APIs, and idioms still appropriate for new source code. **The compatibility baseline for examples is Java 17**, even though certain features may have been finalized or added in newer Java releases.

## 1. Why Define a Clear Scope?

When reading Java material, you easily run into snippets from different eras: legacy APIs kept for backward compatibility, features once in *preview*, *incubator* modules, JDK-internal APIs, and APIs introduced only in Java 21 or later. Those snippets are not all equally suitable as examples in a Java 17 course.

The scope used here has three goals:

1. **Run on JDK 17 with standard configuration:** examples do not require enabling preview, adding incubator modules, or accessing internal packages.
2. **Teach knowledge still useful today:** prioritize modern, finalized APIs and practices that remain applicable in real-world projects.
3. **Clearly separate versions and status:** an API finalized in a newer Java release does not automatically exist in Java 17; an older API that still compiles is not necessarily the right choice for new code.

Here, an **API** refers to classes, interfaces, methods, packages, and modules used by a program. A **language feature** refers to Java syntax or rules, such as `record`, `sealed`, or `switch` expressions. Both must be checked against the Java 17 baseline.

## 2. Rules for Selecting APIs and Features

| Category | Use in Java 17 Examples? | Decision Rule |
| --- | --- | --- |
| Standard, documented Java SE 17 APIs that remain suitable | **Yes** | Verify package, class, and method in the [Java SE 17 API Specification](https://docs.oracle.com/en/java/javase/17/docs/api/index.html). |
| Language features finalized (*final*) in or before Java 17 | **Yes** | Compile with Java 17 without needing `--enable-preview`. |
| Older supported APIs that have better alternatives for new code | **Only when explaining compatibility/migration** | State why they exist and prefer the replacement API in primary examples. |
| *Preview* features in Java 17 | **No** | Not yet finalized language features at the Java 17 milestone; do not turn on `--enable-preview` to use them. |
| *Incubator* modules/APIs or internal JDK APIs | **No** | May change names, change behavior, or disappear; not considered stable Java SE APIs. |
| APIs added only in Java 18+ | **No** | Even if finalized in newer versions, outside the scope of running on Java 17. |
| Third-party libraries | **Not by default** | Include only when a lesson explicitly requires them, and clearly state they are external dependencies not part of the JDK. |

### 2.1. Standard APIs to prefer

| Need | Appropriate API in Java 17 | Usage Notes |
| --- | --- | --- |
| Date, time, time zones | `java.time.LocalDate`, `Instant`, `ZonedDateTime`, `DateTimeFormatter` | Distinguish absolute instants, calendar dates, and zoned date-times. |
| Files and paths | `java.nio.file.Path`, `Files` | Use `Path.of(...)`, `Files.readString(...)`, `Files.writeString(...)`; specify charset explicitly when needed. |
| Lists, maps, sets | `List`, `Map`, `Set`, `List.of(...)`, `Map.of(...)` | The `of` factory methods return collections that cannot be mutated directly. |
| Pipeline data processing | `java.util.stream.Stream`, `Collectors` | `Stream.toList()` exists in Java 17 and returns an unmodifiable list. |
| Potentially absent values | `java.util.Optional` | Useful for return types; do not turn every field into `Optional` out of habit. |
| HTTP client | `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse` | Standard API finalized since Java 11. |
| Asynchronous and concurrent processing | `ExecutorService`, `CompletableFuture`, `BlockingQueue` | Uses the traditional thread model; do not assume Java 17 has virtual threads. |
| Exact decimal monetary values | `java.math.BigDecimal` | Do not use `double` to represent money requiring decimal precision. |
| JDBC, security, cryptography | `java.sql`, `javax.sql`, `java.security`, `javax.crypto` | These `javax.*` namespaces remain part of Java SE; do not equate all `javax.*` with legacy. |

Not all of these APIs were **introduced** in Java 17. The criterion is that they are **available, officially supported, and well suited for writing code running on Java 17**.

### 2.2. Language features finalized in Java 17

- **Switch expressions:** return a value from `switch`, using the `->` arrow and `yield` when a branch needs a block of statements.
- **Text blocks:** multi-line strings delimited by `"""`, helpful for writing sample data or multi-line content.
- **Records:** define concise data-carrying objects with value semantics.
- **Pattern matching for `instanceof`:** check a type and declare a cast pattern variable directly in the condition.
- **Sealed classes/interfaces:** restrict which types may inherit or implement, using `sealed`, `permits`, `final`, `sealed`, and `non-sealed`.

All of these were finalized in or before Java 17. By contrast, **pattern matching in `switch`** is still preview in Java 17, so it is omitted from examples targeting this baseline. Sharing the phrase “pattern matching” does not mean they share the same maturity status.

## 3. Complete Example: Using Only Standard Java 17

The following example combines `record`, `java.time`, `List.of`, `Stream.toList`, `Path`, and `Files`. The program creates a temporary file, writes and reads UTF-8 text, and deletes the temporary file when finished. It requires no framework or dependencies outside the JDK.

**File `Java17Example.java`:**

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;

public class Java17Example {
    record Lesson(String title, LocalDate publishedOn) {
        Lesson {
            Objects.requireNonNull(title, "title");
            Objects.requireNonNull(publishedOn, "publishedOn");
            if (title.isBlank()) {
                throw new IllegalArgumentException("Title must not be blank");
            }
        }
    }

    public static void main(String[] args) throws IOException {
        List<Lesson> lessons = List.of(
            new Lesson("Java 17", LocalDate.of(2024, 1, 1)),
            new Lesson("Standard API", LocalDate.of(2024, 1, 2))
        );

        List<String> titles = lessons.stream()
            .map(Lesson::title)
            .filter(title -> title.length() >= 7)
            .toList();

        Path file = Files.createTempFile("java17-api-", ".txt");
        try {
            Files.writeString(
                file,
                String.join(System.lineSeparator(), titles),
                StandardCharsets.UTF_8
            );
            String savedText = Files.readString(file, StandardCharsets.UTF_8);
            System.out.println(savedText);
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run with JDK 17:

~~~shell
java -version
javac -version
javac --release 17 Java17Example.java
java Java17Example
~~~

Printed output:

~~~text
Java 17
Standard API
~~~

Why does this example fit the scope?

1. `record` has been a finalized language feature since Java 16, so Java 17 supports it without preview flags.
2. `LocalDate` avoids legacy date representations; `Objects.requireNonNull` and the `isBlank()` check validate input data.
3. `List.of` and `Stream.toList` are official APIs in Java 17. Both resulting lists forbid adding or removing elements—a contract you must keep in mind when choosing an API.
4. `Files.createTempFile`, `writeString`, `readString`, and `deleteIfExists` manage files without manually joining paths or pulling in external libraries.
5. `finally` attempts to delete the file even if reading/writing fails. If deletion fails, an I/O exception can still be thrown; the example does not silently assume filesystem operations always succeed.

> **Note:** `--release 17` restricts the language level, bytecode, and platform APIs to Java 17 when compiling with a supporting JDK. It does not automatically verify external dependencies outside the JDK or runtime behavior. At runtime, the environment needs a Java version compatible with the generated class files.

## 4. Example: Combining Finalized Language Features

The example below uses a sealed interface and pattern matching for `instanceof`. It avoids preview `switch` pattern matching.

**File `Java17Language.java`:**

~~~java
public class Java17Language {
    sealed interface Result permits Success, Failure {
    }

    record Success(String value) implements Result {
    }

    record Failure(String message) implements Result {
    }

    static String describe(Result result) {
        if (result instanceof Success success) {
            return "Success: " + success.value();
        }
        if (result instanceof Failure failure) {
            return "Failure: " + failure.message();
        }
        throw new IllegalStateException("Unhandled result type");
    }

    static String levelName(int level) {
        return switch (level) {
            case 1 -> "Basic";
            case 2 -> "Advanced";
            default -> "Unknown";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success("Java 17")));
        System.out.println(levelName(2));
    }
}
~~~

~~~shell
javac --release 17 Java17Language.java
java Java17Language
~~~

In this example, `sealed` controls which types may implement `Result`; `record` implements the concrete data types; `instanceof Success success` performs type matching and binds `success`; and `switch` is a **value-returning switch expression**, not switch pattern matching. All of these constructs work in standard Java 17.

## 5. Platform API Example for HTTP

When sending simple HTTP requests, introduce Java SE's `java.net.http.HttpClient` before reaching for external HTTP libraries for specialized requirements.

**File `Java17Http.java`:**

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class Java17Http {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://example.com/"))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();

        HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());

        System.out.println("HTTP status: " + response.statusCode());
    }
}
~~~

~~~shell
javac --release 17 Java17Http.java
java Java17Http
~~~

This example requires network connectivity to succeed; status code, speed, and reachability depend on the environment. All HTTP classes used belong to Java SE 17 and do not require libraries such as OkHttp or Apache HttpClient. In production applications, handle I/O exceptions, timeouts, non-success HTTP statuses, and context-specific security policies.

## 6. APIs, Syntax, and Techniques Outside Scope

### 6.1. Preview features in Java 17

A *preview feature* is made available for developers to test before becoming a permanent part of the language or platform. Its design and syntax can evolve across versions. Java 17 requires explicit flags to enable such features.

A prominent example is **pattern matching for switch**, introduced in preview in Java 17 (JEP 406). Do not use the following snippet as a standard Java 17 example:

~~~java
// Do not use in Java 17 lessons: switch pattern matching is preview in JDK 17.
// static String inspect(Object value) {
//     return switch (value) {
//         case String text -> text;
//         case Integer number -> number.toString();
//         default -> "Other";
//     };
// }
~~~

Instead, for Java 17 use finalized `instanceof` pattern matching, or a switch expression using only the case kinds stably supported by Java 17. The fact that switch pattern matching became final in a later Java release does not change its status **within Java 17**.

### 6.2. Incubator and JDK internal APIs

*Incubator* modules expose APIs for experimentation and feedback; they do not carry the compatibility guarantees of stable Java SE APIs. Examples to exclude from foundational lessons:

- `jdk.incubator.vector`: Vector API is still in incubator stage in Java 17 (JEP 414).
- `jdk.incubator.foreign`: Foreign Function & Memory API is in incubator stage in Java 17 (JEP 412). Old usages of this module are not standard patterns to copy into Java 17 projects.
- Internal packages such as `jdk.internal.*` and `sun.misc.Unsafe`: not meant as a normal application platform; having to force access with `--add-exports` or `--add-opens` is a sign to revisit the design.

Do not assume every API prefixed with `jdk.*` or `com.sun.*` belongs to Java SE, nor infer support status solely from the package name. Always check the documentation for the specific API, module, and target version.

### 6.3. APIs belonging to newer Java versions

The following examples fall outside the Java 17 baseline even though they are valuable in later Java versions:

| API/Feature | Final Milestone | Why Excluded from Java 17 Examples? |
| --- | --- | --- |
| Virtual threads, `Thread.ofVirtual()` | Java 21 | Does not exist in the Java 17 standard API. |
| `SequencedCollection` | Java 21 | This interface does not exist in Java 17. |
| Final FFM API in `java.lang.foreign` | Java 22 | Differs from the old incubator module; not part of Java SE 17. |
| Pattern matching for `switch` (finalized) | Java 21 | The form present in Java 17 is still preview. |

If you want to write dedicated examples for Java 21/22+, **clearly state the newer Java milestone** and update the tooling, dependencies, and run instructions; do not mix them straight into lessons targeting Java 17 compatibility.

### 6.4. Legacy, deprecated APIs and third-party software

Not every old API has been removed from the JDK, and **deprecated** differs from **preview**:

- `java.util.Date` and `Calendar` still appear in legacy systems, but for new date/time logic start with `java.time`. When bridging legacy code, show the conversion explicitly.
- `Thread.stop()` and forced thread termination are not safe concurrency patterns. Use cooperative cancellation such as `interrupt()` and implement cancellation protocols properly.
- Applets, removed platform APIs, or guides tied to obsolete Java environments are not appropriate introductory examples for Java 17.
- Spring, Jackson, Guava, Lombok, JUnit, and similar libraries are external components. They can be useful, yet they must be introduced with explicit dependencies, versions, and purpose; never imply they ship with Java SE 17.
- Do not lump every `javax.*` namespace into the obsolete bucket: for instance, `javax.crypto` and `javax.sql` remain standard APIs in Java 17. Status must be verified on **each specific API**.

## 7. How to Spot a Worthwhile Example

When reading a snippet on a blog, forum, or older answer, ask in order:

1. **Version:** Which Java version is the author using? Was the snippet introduced or altered in Java 18+?
2. **Official source:** Is the class or syntax documented in Java SE 17 docs or finalized feature specifications?
3. **Status:** Does it mention *preview*, *incubator*, *experimental*, or *internal*, or require `--enable-preview` or `--add-modules jdk.incubator.*`?
4. **Modernity:** Is the API still suitable for new code, or does it exist solely for legacy compatibility?
5. **Reproducibility:** Does it clearly state the JDK, compilation command, network/file prerequisites, dependencies, and expected observable behavior?

In-scope examples generally have a clean structure, minimal dependencies, no special activation flags, and a clear rationale for the chosen API. For code using networking, databases, or filesystems, state the environmental conditions that affect results.

**Compiling with `--release 17`** is a practical way to catch accidental usage of language features or platform APIs beyond the Java 17 milestone. For projects with dependencies, the build tool must also configure the Java version, verify library compatibility, and test against the intended runtime.

## 8. Frequently Misunderstood Questions

**Java 17 is an LTS release, so everything inside JDK 17 is stable?** No. Java 17 is an LTS release, yet it can still ship preview features, incubator modules, and internal APIs. LTS is not a stability stamp on every individual API.

**If a feature became final in Java 21/22, can it be used in Java 17 lessons?** No, if the requirement is to run on Java 17. Check the status and existence of the API specifically at the Java 17 milestone.

**Should learners only study APIs released in the year Java 17 shipped?** No. Much of Java 17's standard platform builds on stable APIs from prior versions. Older APIs that remain suitable are still great learning targets.

**If code compiles with `--enable-preview`, does it meet the requirement?** Not yet. The goal is examples based on finalized features running under standard Java 17 configuration.

**Should all libraries outside the JDK be banned?** No need to ban them. Foundational material should begin with standard APIs so learners know what Java provides out of the box. When a lesson needs a framework or library, declare the dependency openly and explain why it is needed.

## 9. Reference Materials

- [Java SE 17 API Specification — Oracle](https://docs.oracle.com/en/java/javase/17/docs/api/index.html): look up classes, interfaces, packages, and modules in version 17.
- [Java 17 Language Updates — Oracle](https://docs.oracle.com/en/java/javase/17/language/index.html): review language updates.
- [JEP 12 — Preview Language and VM Features](https://openjdk.org/jeps/12): explains the lifecycle of preview features.
- [JEP 11 — Incubator Modules](https://openjdk.org/jeps/11): explains the purpose and characteristics of incubator modules.
- [JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): example of a feature not yet final in Java 17.
- [JEP 412 — Foreign Function & Memory API (Incubator)](https://openjdk.org/jeps/412) and [JEP 414 — Vector API (Second Incubator)](https://openjdk.org/jeps/414): two Java 17-related incubator API cases.

**Guiding principle throughout:** use Java SE 17 and finalized syntax as the baseline; use documented APIs still suited for new code; for technologies from other milestones or experimental statuses, introduce them separately with the corresponding labels and prerequisites.
