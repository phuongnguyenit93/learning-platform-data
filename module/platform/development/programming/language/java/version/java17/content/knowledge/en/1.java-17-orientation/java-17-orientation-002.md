# Java 17 in the Learning Path After Java 8 and Java 11

## 1. Why Learn Java 17 After Java 8 and Java 11?

Java 17 is a **Long-Term Support (LTS)** release launched in September 2021. On a Java learning path, Java 17 marks the transition from the familiar Java 8/11 baseline to a more modern coding style: cleaner data models, stricter type-based state modeling, more readable branching, and a runtime with stricter encapsulation of JDK internals.

It is a **milestone with practical learning and production value**, not the newest Java version at every point in time. Newer LTS releases exist after Java 17, including Java 21 and Java 25. Choosing a JDK to run a system should be based on product requirements, frameworks, libraries, vendor support policies, and infrastructure, rather than assuming the highest version number is always the best fit.

You can think of the three knowledge milestones as follows:

| Learning Milestone | Core Focus | Target Outcome |
|---|---|---|
| **Java 8** | Lambdas, Stream API, Optional, `java.time`, `CompletableFuture`, OOP fundamentals, and Collections | Build modern Java applications at a foundational level; understand functional syntax and data processing |
| **Java 9–11** | Module system, local variable type inference `var`, standard HTTP Client API, Collections/Files/String improvements; getting used to JDK changes | Understand how Java evolved as a platform, not just in syntax |
| **Java 12–17** | Switch expressions, text blocks, records, pattern matching for `instanceof`, sealed classes/interfaces, strong encapsulation of JDK internals | Write clearer, intent-revealing code, design better data models, and operate/upgrade applications more safely |

**Lesson goal:** After completing this lesson, you should be able to explain why a feature appeared at a particular stage, when to use it, when not to use it, and how to move a Java 8/11 project to Java 17 in a controlled manner.

## 2. Prerequisites Before Java 17

### 2.1. Java 8 skills you should genuinely know how to apply

Before learning new syntax in Java 17, make sure you can reliably apply:

- **Language fundamentals:** classes/interfaces, inheritance and polymorphism, generics, exceptions, immutable objects, access modifiers, and encapsulation principles.
- **Collections:** distinguishing `List`, `Set`, and `Map`; understanding the `equals()` and `hashCode()` contract; knowing when data structures are mutable.
- **Lambdas and method references:** expressing behavior concisely with functional interfaces while keeping code readable.
- **Stream API:** `filter`, `map`, `flatMap`, `reduce`, `collect`; understanding intermediate vs. terminal operations, side effects, and laziness.
- **Optional:** representing potentially absent return values at appropriate boundaries; not overusing `Optional` for every field or parameter.
- **Date and Time API:** `Instant`, `LocalDate`, `LocalDateTime`, `ZonedDateTime`, `Duration`; understanding the difference between an instant in time and zoned date-time values.
- **Basic concurrency:** `Thread`, `ExecutorService`, `CompletableFuture`, thread safety, and resource management.

Example showing Java 8 skills remaining foundational in Java 17:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

class Java8Foundation {
    static Map<String, Long> countByDepartment(List<Employee> employees) {
        return employees.stream()
                .filter(Employee::active)
                .collect(Collectors.groupingBy(
                        Employee::department,
                        Collectors.counting()
                ));
    }

    interface Employee {
        boolean active();
        String department();
    }
}
~~~

This snippet uses Streams and method references familiar from Java 8. Java 17 **adds expressive tools**, rather than replacing all of these techniques.

### 2.2. Java 9–11 knowledge that helps you understand the platform

The **Java Platform Module System (JPMS)** was introduced in Java 9, declaring modules with `module-info.java`. You should understand `requires`, `exports`, and the difference between the *classpath* and the *module path*. However, **you are not required to modularize every project** when using Java 17; many applications continue to work fine on the classpath.

Java 10 introduced `var` for **local variables** whose type can be inferred from their initializer. It does not turn Java into a dynamically typed language and does not replace type declarations on fields or method return types.

~~~java
var names = List.of("An", "Binh", "Chi"); // Inferred type: List<String>
// var value; // Invalid: no initializer expression to infer type from
~~~

Java 11 finalized the standard HTTP Client in the `java.net.http` package and added convenient APIs such as `String.isBlank()`, `String.lines()`, and `Files.readString()`. You should know when to use standard APIs where appropriate, while understanding that dedicated HTTP libraries remain useful when specialized capabilities or integrations are needed.

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

class Java11HttpExample {
    static String getExamplePage() throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com"))
                .GET()
                .build();
        return client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        ).body();
    }
}
~~~

Throughout the path, distinguish between **Java 8 knowledge**, **Java 9–11 changes**, and **Java 12–17 changes**. This helps you read older codebases accurately and avoid mistaking an earlier standardized feature for a “new Java 17 feature.”

## 3. Key Language Enhancements to Learn When Moving to Java 17

### 3.1. Switch expressions — returning a value from a selection branch

Switch expressions were standardized in **Java 14** and are available in Java 17. Unlike traditional `switch` statements that often require `break`, a switch expression evaluates to a value, and arrow syntax prevents accidental *fall-through*.

~~~java
enum Priority { LOW, MEDIUM, HIGH }

class PriorityExample {
    static int responseHours(Priority priority) {
        return switch (priority) {
            case HIGH -> 2;
            case MEDIUM -> 8;
            case LOW -> 24;
        };
    }
}
~~~

For branches with multiple statements, use `yield` to supply a value for the expression:

~~~java
int fee = switch (customerType) {
    case "VIP" -> 0;
    case "STANDARD" -> 10;
    default -> {
        System.out.println("Applying default fee");
        yield 20;
    }
};
~~~

**When to use:** mapping an enum or state to a clear result. **Keep in mind:** branches must cover all possible inputs; use `default` when appropriate, though with enums, listing all constants explicitly sometimes helps the compiler catch newly added unhandled cases. Avoid turning a switch expression into an overly long block of business logic.

### 3.2. Text blocks — more readable multi-line strings

Text blocks were standardized in **Java 15**. They are useful for sample JSON, multi-line SQL, HTML content, or formatted messages. The opening and closing delimiters are three double quotes.

~~~java
String query = """
        SELECT id, full_name, email
        FROM students
        WHERE active = true
        ORDER BY full_name
        """;
~~~

Text blocks process line breaks and indentation according to Java's rules; inspect the actual output when whitespace matters. **Never concatenate user input directly into SQL statements**: even when writing SQL with a text block, you must still use prepared statements and bound parameters. For dynamic JSON, use a serialization library instead of string concatenation.

### 3.3. Records — representing data with less boilerplate

Records were standardized in **Java 16** and are well suited for representing data passed across layers, query results, messages, or DTOs.

~~~java
import java.util.Objects;

public record StudentResponse(long id, String fullName) {
    public StudentResponse {
        if (id <= 0) {
            throw new IllegalArgumentException("id must be positive");
        }
        Objects.requireNonNull(fullName, "fullName");
        if (fullName.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
    }
}
~~~

The compiler generates the constructor, `id()` and `fullName()` accessors, `equals()`, `hashCode()`, and `toString()`. A record is a data type with fixed state across its components: there are no setters to mutate fields after creation.

However, **records do not guarantee deep immutability**. If a component references a mutable list or object, callers outside can still modify that object's contents. Perform defensive copying when needed:

~~~java
import java.util.List;

public record ClassRoom(String name, List<String> students) {
    public ClassRoom {
        students = List.copyOf(students);
    }
}
~~~

Here `List.copyOf` creates an unmodifiable list via the reference stored in the record (and also rejects `null` elements). If the elements themselves are mutable objects, additional measures are needed to protect the elements.

**Do not mechanically use records** for JPA entities, which have specific requirements around identity, lifecycle, and mutable state. In ORM projects, records are usually a better fit for DTOs/projections when supported by the framework and library versions in use.

### 3.4. Pattern matching for instanceof — test and bind in one step

Standardized in **Java 16**, pattern matching for `instanceof` eliminates redundant casts.

~~~java
static String describe(Object value) {
    if (value instanceof String text && !text.isBlank()) {
        return "Valid string: " + text;
    }
    if (value instanceof Integer count && count > 0) {
        return "Positive integer: " + count;
    }
    return "Other value";
}
~~~

The variable `text` can only be used where the compiler knows the type test succeeded. This is *flow scoping*; do not assume a pattern variable always has the same scope as a variable declared at the top of a block.

**Important distinction:** pattern matching in `switch` is still a **preview** feature in JDK 17, not stable Java 17 syntax. Standard Java 17 lessons should use `instanceof` pattern matching as above and switch expressions with ordinary cases. Pattern matching for `switch` was only standardized later, in Java 21.

### 3.5. Sealed classes and sealed interfaces — controlling the set of subtypes

Sealed types were standardized in **Java 17**. They state that an interface or class allows only a specified set of direct subtypes. This is an appropriate tool for representing processing results and domain states with a finite set of cases.

~~~java
public sealed interface PaymentResult
        permits PaymentAccepted, PaymentRejected {
}

record PaymentAccepted(String transactionId) implements PaymentResult {
}

record PaymentRejected(String reason) implements PaymentResult {
}
~~~

A direct subtype of a sealed type must explicitly declare how it continues inheritance: `final`, `sealed`, or `non-sealed` (records are implicitly `final`). Permitted subtypes must reside in the same named module; if using the unnamed module, they must be in the same package.

Sealed types work well with records to represent the alternatives of a result:

~~~java
static String message(PaymentResult result) {
    if (result instanceof PaymentAccepted accepted) {
        return "Payment accepted: " + accepted.transactionId();
    }
    if (result instanceof PaymentRejected rejected) {
        return "Rejected: " + rejected.reason();
    }
    throw new IllegalStateException("Unsupported case");
}
~~~

**When to use:** a set of results, commands, or states designed with a clear boundary. **When not to use:** an open API hierarchy meant for plugins or third parties to extend freely. Sealed types alter the API extension contract, so weigh this carefully when designing public libraries.

### 3.6. Notable new APIs from this period

| Feature/API | Introduced | Practical Meaning |
|---|---|---|
| `List.of`, `Set.of`, `Map.of` | Java 9 | Create unmodifiable collections through the API |
| `List.copyOf`, `Set.copyOf`, `Map.copyOf` | Java 10 | Copy into an unmodifiable collection |
| `String.isBlank()`, `String.strip()` | Java 11 | Handle Unicode whitespace properly in many scenarios |
| `Files.readString()`, `Files.writeString()` | Java 11 | Read and write text files conveniently |
| `Stream.toList()` | Java 16 | Collect stream results into an unmodifiable list |
| `RandomGenerator` and related APIs | Java 17 | More unified interfaces for multiple pseudo-random number generators |

Example:

~~~java
List<String> activeNames = names.stream()
        .filter(name -> !name.isBlank())
        .map(String::strip)
        .toList();
~~~

The list returned by `Stream.toList()` **does not allow modification operations**. Do not assume `Collectors.toList()` has the same contract; the specification of that collector does not guarantee a concrete list type or mutability. When you need a mutable list, express it explicitly:

~~~java
List<String> editable = names.stream()
        .filter(name -> !name.isBlank())
        .collect(java.util.stream.Collectors.toCollection(java.util.ArrayList::new));
~~~

## 4. Combined Example Runnable on Java 17

The following example combines Streams from Java 8, `var` from Java 10, switch expressions, records, a sealed interface, and pattern matching. Save everything as **LearningPathDemo.java**:

~~~java
import java.util.List;

public class LearningPathDemo {
    sealed interface EnrollmentResult permits Accepted, Rejected {}

    record Accepted(String student, String course) implements EnrollmentResult {}

    record Rejected(String reason) implements EnrollmentResult {}

    static EnrollmentResult enroll(String student, String course) {
        if (student == null || student.isBlank()) {
            return new Rejected("Invalid student name");
        }
        return new Accepted(student.strip(), course);
    }

    static String describe(EnrollmentResult result) {
        if (result instanceof Accepted accepted) {
            return "Enrollment succeeded: " + accepted.student()
                    + " -> " + accepted.course();
        }
        if (result instanceof Rejected rejected) {
            return "Enrollment failed: " + rejected.reason();
        }
        throw new IllegalStateException("Unknown result");
    }

    public static void main(String[] args) {
        var students = List.of("An", " ", "Binh", "Chi");

        List<String> validStudents = students.stream()
                .filter(name -> !name.isBlank())
                .toList();

        String course = switch (validStudents.size()) {
            case 0 -> "No students yet";
            case 1 -> "Java 8";
            default -> "Java 17";
        };

        for (String student : validStudents) {
            System.out.println(describe(enroll(student, course)));
        }
        System.out.println(describe(enroll(" ", course)));
    }
}
~~~

Run in the directory containing the file with JDK 17:

~~~shell
java -version
javac --release 17 LearningPathDemo.java
java LearningPathDemo
~~~

Expected output:

~~~text
Enrollment succeeded: An -> Java 17
Enrollment succeeded: Binh -> Java 17
Enrollment succeeded: Chi -> Java 17
Enrollment failed: Invalid student name
~~~

In this example, the newer constructs reduce boilerplate and make intent explicit. Even so, input validation rules, separation of responsibilities across methods, and testing remain just as important as before.

## 5. What Does Java 17 Change About Running and Deploying Applications?

Learning Java 17 does not stop at syntax. Many issues when upgrading projects stem from the **JDK runtime, library dependencies, and build tools**.

### 5.1. Stronger encapsulation of JDK internals

Java 17 enforces **strong encapsulation** of JDK internal components (JEP 403). Applications and libraries should not depend on internal classes such as `sun.*` or use unauthorized reflective access on non-open members of JDK modules.

- Code using public Java APIs is generally much easier to upgrade than code relying on internal APIs.
- Older frameworks or reflection-heavy libraries may encounter `InaccessibleObjectException`; prioritize upgrading dependencies to versions that support Java 17.
- The `--add-opens` flag can provide a transitional workaround in specific cases, but it should be narrowly scoped and scheduled for removal. The `--illegal-access` option from earlier JDK releases is no longer a way to re-enable such access on Java 17.

Example of a transitional flag once you have identified the exact library needing access:

~~~shell
java --add-opens java.base/java.lang=ALL-UNNAMED -jar app.jar
~~~

Do not add this flag to every application out of habit. Only use it after reading the error, knowing which module/package needs to be opened, and identifying which library needs upgrading.

### 5.2. Libraries previously bundled with the JDK may no longer be included

Several components commonly used in Java 8 applications were split out or removed from the JDK in milestones prior to Java 17:

- JDK-bundled Java EE/CORBA modules were removed from Java SE starting in Java 11; for example, legacy apps using JAXB may need to declare a standalone dependency.
- JavaFX is no longer bundled in standard JDK builds starting in Java 11; desktop applications need to configure OpenJFX or an appropriate runtime.
- The Nashorn JavaScript engine was removed from the JDK starting in Java 15; if you depend on it, you need an evaluated alternative.

These are **practical compatibility issues when upgrading from Java 8/11**, not a reason to keep relying on removed APIs.

### 5.3. Class file versions and binary compatibility

| Java version used to compile | Major class file version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |

A Java 8 or Java 11 JVM cannot directly run class files compiled for Java 17. A common error is `UnsupportedClassVersionError`. In many cases, a newer JDK can run bytecode compiled for an older JDK, yet the application may still fail due to removed APIs, behavior changes, or incompatible dependencies. **Bytecode compatibility does not equal full application compatibility.**

To specify the compilation target on a supporting JDK, use:

~~~shell
javac --release 17 MyClass.java
~~~

`--release` aligns the language level, class file version, and available Java SE APIs for the target release; this is clearer and safer than only setting `-source` and `-target` when building for an older Java release than the JDK in use. Note: `--release` does not verify compatibility of external libraries outside the JDK or runtime configuration.

### 5.4. Build tools, frameworks, and runtimes

In real-world projects, distinguish among:

1. **The JDK running the build** (Maven/Gradle daemon, plugins).
2. **The target JDK or release for compilation**.
3. **The JDK in the runtime environment** (server, container, CI).

These can differ and must be configured deliberately. For example, with the Maven Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <release>17</release>
    </configuration>
</plugin>
~~~

With Gradle, you can specify the compilation JDK via Java toolchains:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

Every build tool, plugin, annotation processor, and framework has its own compatibility matrix. Before upgrading, confirm that the **actual versions** in use are compatible with Java 17. For instance, Spring Boot 3 uses Java 17 as its baseline and moves to Jakarta EE APIs; changing `javax.*` to `jakarta.*` in that case comes from the framework/Jakarta EE generation, **not an automatic requirement of Java 17 syntax itself**.

### 5.5. Observability and performance

Java 17 continues to include modern JVM observability tools and mechanisms. You should be aware that:

- G1 is the default garbage collector in common HotSpot configurations on JDK 17; other GCs may suit specific workloads and distributions.
- Unified JVM logging uses the `-Xlog` option, such as `-Xlog:gc*` for GC analysis.
- Java Flight Recorder (JFR) and Java Mission Control are valuable tools for investigating performance, latency, memory allocation, and application behavior.
- Do not tune GC based on generic advice. Measure latency, throughput, heap usage, pauses, and realistic load before making adjustments.

Java 17 also does not guarantee code automatically runs faster merely by bumping the version number. Performance depends on the application, libraries, JVM settings, and measurement conditions.

## 6. Practical Roadmap: From Knowing Java 8/11 to Working Effectively with Java 17

This roadmap is based on **target competencies**, not fixed day counts.

### Stage 1 — Solidify the unchanged fundamentals

Build a small application on your own involving collections, streams, exceptions, date/time, HTTP APIs, or file operations. The goal is to make sure you understand data semantics, API contracts, and error handling before adopting new syntax.

**Exercise:** Process a list of orders containing creation timestamp, status, and amount; use Streams to calculate monthly revenue and group by status. Test empty lists, timestamps across different time zones, and invalid values.

### Stage 2 — Rewrite appropriate pieces of code using Java 17

Practice step by step:

1. Convert pure mapping switch statements into switch expressions.
2. Convert simple DTO data classes into records when they fit the data contract.
3. Convert `instanceof` checks plus manual casts into pattern matching.
4. Use sealed interfaces to model processing results with a finite set of cases.
5. Use text blocks for multi-line strings that genuinely benefit from formatting.
6. Compare `Stream.toList()` with collecting into a mutable list to pick the right contract.

**Exercise:** Design an API returning enrollment results: `Accepted`, `Rejected`, `PendingReview`. Use a sealed interface and records, validate inputs, and format results into messages. Add another state later to observe which handling locations must be updated.

### Stage 3 — Understand migration from Java 8/11

Practice analyzing a legacy project (or creating a representative sample project) with this workflow:

1. **Capture a baseline:** record JDK and framework/dependency versions, build status, tests, existing issues, and deployment requirements.
2. **Audit dependencies:** libraries touching JDK internals, reflection, annotation processing, JAXB/JavaFX/Nashorn APIs, or outdated framework versions.
3. **Upgrade the JDK and build plugins per the support matrix:** align compiler release and runtime; avoid letting CI use a different JDK than local environments.
4. **Compile, run tests, and scan runtime errors:** watch for `ClassNotFoundException`, `NoClassDefFoundError`, `InaccessibleObjectException`, and `UnsupportedClassVersionError`.
5. **Run integration tests:** database drivers, HTTP/TLS, serialization, timezones, locales, message brokers, and real business flows.
6. **Re-measure performance, package, and deploy:** test container images, startup time, memory, throughput, and logs; keep a rollback plan ready if problems arise.

To detect dependencies on internal JDK APIs, you can consult the `jdeps` tool:

~~~shell
jdeps --jdk-internals app.jar
~~~

The output is a signal for further investigation; it cannot replace runtime testing or cover all dynamic reflection behavior.

### Stage 4 — Apply the knowledge in business code

Write a small module consisting of a request receiver, processor, response returned, and tests. Prefer:

- Records for requests/responses when the data contract fits.
- Sealed types for results with a controlled set of states.
- Switch expressions for simple mappings.
- Stream API when transforming datasets; ordinary loops remain reasonable for complex logic with side effects.
- Java 11+ standard APIs (HTTP Client, Files, String) when they meet requirements.

Do not refactor an entire codebase just to “use Java 17 features.” Changes should improve naming, reduce boilerplate, clarify data contracts, or mitigate specific error risks.

## 7. Misconceptions to Avoid While Learning

| Misconception | Accurate Understanding |
|---|---|
| “Every modern feature first appeared in Java 17.” | Java 17 is an LTS milestone accumulating changes from Java 9 through 17; know the standardization release of each feature. |
| “Using Java 17 means converting all classes to records.” | Records suit fixed-data models; domain entities with lifecycles or mutable state may still need regular classes. |
| “Records are deeply immutable.” | Records protect component references from reassignment, but referenced objects can still be mutable. |
| “`var` makes Java dynamically typed.” | Java remains statically typed at compile time. |
| “A sealed interface always replaces a regular interface.” | Sealed fits closed hierarchies; open interfaces remain right when third-party extension is needed. |
| “`switch` pattern matching is a stable Java 17 feature.” | In Java 17 it is preview; only `instanceof` pattern matching was standardized. |
| “`Stream.toList()` returns a list you can add/remove elements from.” | The returned list cannot be modified through the API. |
| “If it compiles, the app is already Java 17 compatible.” | You still need to check runtime behavior, reflection, libraries, integrations, and performance. |
| “Every Java 17 project requires `module-info.java`.” | Classpath-based projects remain supported; modularization is a separate architectural choice. |
| “Upgrading to Java 17 automatically requires changing every `javax` to `jakarta`.” | That depends on the framework and Jakarta EE version in use, not the Java language upgrade itself. |
| “Java 17 has stable virtual threads.” | Virtual threads were standardized in Java 21; do not assume they are a stable built-in Java 17 API. |

Java 17 examples should avoid relying on preview features merely to shorten code. Preview features can require extra compile/run flags and their language contracts may still change.

## 8. When Should You Move On from Java 17 to Java 21/25?

Java 17 is a great place to learn an important shift in the language and ecosystem. Once you have mastered it, you can continue to newer LTS versions based on job or project requirements:

- **Java 21:** explore virtual threads, finalized pattern matching for `switch`, record patterns, and sequenced collections.
- **Java 25:** study newly stabilized changes in JDK 25 from the official documentation and check your project's compatibility matrix before upgrading.

Do not bring syntax or APIs introduced only in Java 21/25 into examples required to run on Java 17. Also, **LTS is a support policy tied to each vendor/distribution**, so verify actual security update timelines and support terms rather than inferring them solely from the LTS label.

When planning a team roadmap, answer three questions: **which version must the system run on, which feature set must learners master, and which JDK distribution is supported?** The three answers may be different.

## 9. Self-Assessment After the Lesson

You have achieved the lesson goals when you can:

1. Clearly identify which Java 8 skills remain foundational in Java 17 and which Java 9–11 improvements are worth learning.
2. State the exact standardization version of switch expressions, text blocks, records, `instanceof` pattern matching, and sealed types.
3. Write Java 17 code using these features, compiling and running with JDK 17 without enabling preview flags.
4. Explain the differences among a record DTO, a mutable-state entity, an open hierarchy, and a sealed hierarchy.
5. Recognize the limits of `var`, records, and `Stream.toList()` without guessing.
6. Identify upgrade risks from Java 8/11: internal JDK APIs, libraries split out from the JDK, compiler release flags, dependencies, reflection, and runtime behavior.
7. Draft an upgrade plan covering build, unit tests, integration tests, operational metrics, and a rollback strategy.
8. Identify which features belong to Java 21 or later so they are not mistakenly introduced into a Java 17 project.

### Critical-Thinking Questions

**Question 1.** An API returns a bundle of data consisting of a user ID and name, with no requirement to mutate individual fields after creation. Should you consider a record or a regular class?

**Hint:** A record is usually a good fit for a fixed-data DTO, though you must consider validation, nested data structures, and framework requirements.

**Question 2.** Why might an application compile on Java 17 yet fail at startup with `InaccessibleObjectException`?

**Hint:** A dependency may be using reflection to access JDK internal members; prioritize upgrading the library and checking module-opening requirements.

**Question 3.** Why can't `Stream.toList()` be used in source code required to compile for Java 11?

**Hint:** That API was introduced in Java 16. Compiling with `--release 11` protects you from accidentally using Java SE APIs newer than the target release.

**Question 4.** When is a sealed interface a poor choice?

**Hint:** When you need to allow a plugin system or library consumers to implement new subtypes outside the list you control.

**Question 5.** Can you use stable record patterns, virtual threads, or pattern matching for `switch` directly in Java 17?

**Hint:** No. Those capabilities belong to later releases; in particular, pattern matching for `switch` is only preview in Java 17.

## 10. References for Further Learning

- [dev.java — Learn Java](https://dev.java/learn/): practical documentation on the Java language, APIs, and tools.
- [OpenJDK — JDK 17](https://openjdk.org/projects/jdk/17/): list of Java 17 features/JEPs, with links to the original JEPs.
- [Oracle — JDK 17 Migration Guide](https://docs.oracle.com/en/java/javase/17/migrate/): guide to compatibility considerations when migrating to JDK 17.
- [Oracle — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/): verify whether an API actually exists in Java 17 before writing code.

**Next direction:** Treat Java 17 as a foundation for learning how to pick the right language tool for the job and upgrade systems with verification. Java 8/11 fundamentals remain in everyday use; Java 17 helps you express data models more clearly and understand the constraints of the modern JVM more deeply.
