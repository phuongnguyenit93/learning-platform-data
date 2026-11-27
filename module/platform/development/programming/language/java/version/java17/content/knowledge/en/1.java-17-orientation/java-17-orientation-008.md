# Java 17 Learning Sequence: Prerequisites and Completion Criteria

Java 17 is a Java LTS (Long-Term Support) release widely adopted as a compatibility baseline across projects. To learn effectively, separate **learning the Java language**, **understanding the Java SE standard library**, **using development tools**, and finally **building and testing applications**. This guide lays out a sequence from foundational concepts to independently shipping a complete Java 17 program.

The content focuses on knowledge that remains practical in modern software development. Features introduced in newer Java releases can be learned later, but must not be mistaken for features built into Java 17.

## 1. End Goal of the Learning Path

Upon completion, a learner should be able to independently:

1. Set up a JDK 17 environment, compile, run, and debug programs; understand the relationship between source code, bytecode, and the JVM.
2. Write well-structured programs using classes, objects, interfaces, generics, exceptions, and essential standard APIs.
3. Choose appropriate data structures; apply collections, lambdas, and Streams when they make code clearer and easier to test.
4. Handle user input, date/time, files, and external resources in a controlled way without swallowing errors or leaking resources.
5. Apply finalized Java 17 features properly, especially records, sealed classes/interfaces, switch expressions, text blocks, and pattern matching for `instanceof`.
6. Write unit tests, read error messages, use Git and a build tool like Maven or Gradle, and deliver a program that others can reproduce and run.

**Deliverable:** a small-scale Java 17 application with source code, run instructions, automated tests, and a list of handled scenarios. There is no need to learn web frameworks before achieving these fundamentals.

## 2. Foundational Knowledge

### 2.1. Minimum baseline before starting

| Knowledge Area | What You Should Understand | Self-Check |
|---|---|---|
| Programming mindset | Variables, data types, conditionals, loops, functions, and return values | Explain an algorithm to find the maximum number in a list; write pseudocode on your own |
| Data | Numbers, strings, booleans, arrays/lists; difference between values and references | Predict what happens when modifying an object via two variables referencing the same instance |
| Basic logic | AND, OR, NOT, comparisons, boundary conditions | Write test cases for an input-validation function |
| Computer and terminal | Directories, paths, files, commands to run programs | Navigate to a project directory, list files, and run a compile command |
| Reading documentation | Distinguish examples, API contracts, parameters, return types, and exceptions | Look up a method in the Java 17 API Documentation |

Complete beginners can learn programming concepts alongside the initial stage. Learners who already know another language can start directly from Java's syntax and object model.

### 2.2. Setting up the Java 17 environment

- Install **JDK 17** from a vendor-supported distribution, such as Eclipse Temurin, Oracle JDK, or an OpenJDK distribution suited to your project.
- Check both `java -version` and `javac -version`; both commands must point to the intended JDK/JVM. If multiple JDKs are installed, check `JAVA_HOME`, `PATH`, and your IDE's JDK settings.
- Pick a Java-capable IDE (IntelliJ IDEA, Eclipse, or VS Code with Java extensions). Practice using breakpoints, step into, inspecting variables, and viewing the call stack.
- Install Git and get comfortable with `status`, `add`, `commit`, and `diff`. Choose **one** build tool for practice projects: Maven **or** Gradle.
- Set the target language/API level to **17**. When using `javac`, `--release 17` enforces both syntax and APIs available in the target release. With Maven/Gradle, configure the corresponding release level or toolchain and verify the JDK used at runtime.

Test your first program in `Hello.java`:

```java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Java 17 ready");
    }
}
```

```bash
javac --release 17 -encoding UTF-8 Hello.java
java Hello
```

Expected output: `Java 17 ready`. If it does not run, resolve JDK, class name, file name, or working directory issues before moving on.

## 3. Recommended Learning Sequence

This is a **dependency order of concepts**, not a rigid day-by-day schedule. You can move faster through stages you already master, but complete each stage's proof-of-learning exercise before advancing.

| Stage | Core Topics | Milestone Practice Exercise |
|---|---|---|
| **0. Environment and how Java runs** | JDK, JVM, bytecode, `javac`, `java`, classpath, project layout, Git | Compile and run a class from the terminal; debug a simple bug in an IDE |
| **1. Syntax and control flow** | Primitive/reference types, variables, operators, casting, `String`, comparisons, `if`, `switch`, loops, methods, arrays | Write an input-reading/validation app; handle missing, blank, and invalid inputs |
| **2. Object model** | Classes, objects, constructors, access modifiers, encapsulation, `static`, inheritance, interfaces, polymorphism, `enum`, `record` | Build classes modeling a small business domain with clear separation of responsibilities |
| **3. Collections and generics** | `List`, `Set`, `Map`, iteration, sorting, `Comparator`, `equals`/`hashCode`, generics, immutability | Manage a collection of objects: search, filter, aggregate, and handle duplicate entries |
| **4. Pragmatic functional style** | Lambdas, method references, functional interfaces, Stream, `Optional`, choosing loops vs. Streams | Implement filtering, grouping, counting, and sorting over real data; explain the pipeline |
| **5. Working with the environment** | Exceptions, `try-with-resources`, `Path`/`Files`, UTF-8, `java.time`, basic HTTP client | Read/write files, handle I/O errors, manipulate due dates, and separate user errors from system errors |
| **6. Code quality and tooling** | Unit testing, JUnit 5, debugger, logging, Maven/Gradle, dependencies, packages, Git, reading stack traces | Write tests for business rules and edge cases; run build/tests cleanly from the terminal |
| **7. JVM and basic concurrency** | Conceptual heap/stack, garbage collection, threads, `ExecutorService`, race conditions, synchronization, closing resources | Explain a shared-data bug; run independent tasks with an executor when needed |
| **8. Finalized Java 17 features and integration** | Records, sealed types, switch expressions, text blocks, `instanceof` pattern matching; combining everything above | Complete the capstone application and explain why each construct was chosen |

### Stage 1: Solidify syntax before writing clever shortcuts

Learn how to declare values, invoke methods, and branch cleanly before compressing statements. Distinguish clearly:

- `int`, `long`, `double`, and `boolean` are primitives; `String`, arrays, and other objects are accessed via references.
- `==` on objects compares references; use `equals()` when comparing equality by content/value as defined by the type.
- `String` is immutable. When concatenating strings repeatedly in a loop, consider `StringBuilder`.
- `null` represents the absence of a reference; define input contracts explicitly instead of letting `NullPointerException` happen unpredictably.
- `var` supports type inference for initialized local variables; types remain static and never become dynamic.

Practice example: write a method summing valid values in an array, deciding explicitly how to handle empty arrays, negative values, and overflow risk.

### Stage 2: Design objects with clear responsibilities

Create classes to model **cohesive state and behavior**, rather than dumping every operation into a single utility class. A task class might validate its title, due date, and status; a storage class handles file I/O. Unrelated responsibilities do not belong in the same place.

Learn interfaces to separate contracts from implementations, enums for finite state sets, records for transparent data carriers, and sealed types when restricting allowed subtypes. Use inheritance only when a genuine **is-a** relationship exists and substitutability holds under the supertype's contract; many problems are better solved with composition.

### Stage 3: Choose data structures by behavior

| Need | Common Choice | Watch Out For |
|---|---|---|
| Ordered list allowing duplicates | `List<T>` | Search and insert/delete costs vary by implementation |
| Collection of unique elements | `Set<T>` | Correctness of `equals()` and `hashCode()` |
| Key → value mapping | `Map<K,V>` | Keys must remain stable while stored in the map |
| Sorting by criteria | `Comparator<T>` | Must define total order and tie-breaking behavior |
| Data that must not be mutated via returned API | `List.copyOf(...)`, `List.of(...)` | Distinguish an unmodifiable collection from mutable element objects |

Know how to use generics (`List<Task>` instead of raw `List`), iterate safely, and reason about basic time complexity. You do not need to memorize every implementation class; you should be able to explain why the chosen structure fits the problem's queries.

### Stage 4: Streams are data-transformation pipelines

A sensible progression is: write loops → write lambdas → understand `filter`, `map`, `sorted`, `collect`, and terminal operations like `count` → then learn `groupingBy` or advanced collectors. Streams normally execute only when a terminal operation runs and should not be used to hide side effects.

`Optional<T>` is suitable when **an API may return no result**; there is no need to turn every nullable field or parameter into an `Optional`. When data can be missing, define clearly whether to return empty, throw an exception, or supply a default.

### Stage 5: Files, date/time, and exceptions

Use `Path` and `Files` for standard file operations, `try-with-resources` for closeable resources, and specify encoding explicitly (usually UTF-8). Read API contracts to know which exceptions can occur; catch exceptions only where you can recover or add useful context. Avoid `catch (Exception e)` and silently ignoring it.

Prefer `java.time`: `LocalDate` for calendar dates, `LocalDateTime` for date-time without a time zone, `Instant` for points on the timeline, and `ZonedDateTime` when time zones matter. Avoid mistaking `LocalDateTime` for a global instant. For money, learn `BigDecimal` and explicit rounding modes instead of using `double` for exact monetary amounts.

When learning HTTP, `java.net.http.HttpClient` is the standard API in Java 17; understand status codes, timeouts, network errors, and closing streams when applicable. Writing a full HTTP implementation or custom JSON/CSV parser from scratch is not the goal of this stage; external libraries must be declared explicitly as dependencies.

### Stages 6–7: Test before expanding, concurrency after understanding state

Unit tests should verify observable outcomes for given inputs, especially boundary cases: empty lists, duplicate IDs, blank strings, tasks due today, overdue tasks, and read/write failures. Use the debugger to find root causes rather than tweaking code until a single sample passes.

Understand threads, tasks, and executors before sharing data across multiple threads. Recognize that mutating shared state can cause race conditions; learn to minimize shared mutable state, apply synchronization only when truly needed, and shut down `ExecutorService`/resources properly. **Virtual threads were finalized in Java 21, not as a standard Java 17 feature.** Advanced concurrent programming should only be introduced when the problem actually calls for it.

## 4. Modern Java Features: Identify the Exact Version

Not every feature showcased in “Modern Java” articles belongs to Java 17. The following table lists features that are finalized **and usable when targeting Java 17**:

| Feature | Finalized Since | When to Use |
|---|---|---|
| `var` for local variables | Java 10 | Inferred type is obvious, reducing repetitive declarations |
| HTTP Client (`java.net.http`) | Java 11 | Making HTTP requests with the standard API |
| Switch expressions | Java 14 | Selecting a value across clear branches |
| Text blocks (`"""..."""`) | Java 15 | Multi-line strings such as text templates, SQL, or JSON |
| Records | Java 16 | Data carriers with component-based accessors, `equals`, `hashCode`, `toString` |
| Pattern matching for `instanceof` | Java 16 | Testing a type and binding a cast variable in the matching branch |
| `Stream.toList()` | Java 16 | Collecting Stream output into an unmodifiable list |
| Sealed classes/interfaces | Java 17 | Restricting which classes/interfaces may directly extend or implement |

Standalone example of pattern matching for `instanceof`:

```java
static String describe(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        return "String of length " + text.length() + " characters";
    }
    return "No valid string";
}
```

**Version boundary:** pattern matching for `switch` is still *preview* in Java 17 and should not be put into standard Java 17 programs unless you intentionally opt into and understand the preview mechanism. Virtual threads, sequenced collections, and syntax finalized after Java 17 are also outside the completion requirements. The goal is to write solid Java 17 programs while keeping habits that carry forward cleanly when upgrading the JDK.

## 5. Integrated Example: Overdue Task List

The example below combines records, enums, switch expressions, `java.time`, collections, and Streams. It runs on JDK 17 with no external libraries.

Save as `Main.java`:

```java
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;

public class Main {
    enum Status {
        TODO, IN_PROGRESS, DONE
    }

    record Task(long id, String title, LocalDate due, Status status) {
        Task {
            if (id <= 0) {
                throw new IllegalArgumentException("id must be positive");
            }
            title = Objects.requireNonNull(title, "title").trim();
            if (title.isBlank()) {
                throw new IllegalArgumentException("title must not be blank");
            }
            Objects.requireNonNull(due, "due");
            Objects.requireNonNull(status, "status");
        }

        boolean isOverdue(LocalDate today) {
            return status != Status.DONE && due.isBefore(today);
        }
    }

    static String statusLabel(Status status) {
        return switch (status) {
            case TODO -> "To Do";
            case IN_PROGRESS -> "In Progress";
            case DONE -> "Done";
        };
    }

    public static void main(String[] args) {
        var today = LocalDate.of(2030, 6, 10);
        var tasks = List.of(
                new Task(1, "Learn Streams",
                        LocalDate.of(2030, 6, 9), Status.IN_PROGRESS),
                new Task(2, "Write unit tests",
                        LocalDate.of(2030, 6, 11), Status.TODO),
                new Task(3, "Install JDK",
                        LocalDate.of(2030, 6, 1), Status.DONE)
        );

        tasks.stream()
                .filter(task -> task.isOverdue(today))
                .forEach(task -> System.out.println(
                        task.title() + ": " + statusLabel(task.status())));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Output:

```text
Learn Streams: In Progress
```

Key points you should be able to explain: `record` automatically generates accessors like `title()`; the compact constructor validates data at creation time; `List.of` creates an unmodifiable list; the Stream filters overdue tasks; and the switch expression returns a label per status. `LocalDate.of(...)` is used instead of the system clock so the example produces repeatable output.

In real applications, separate types and business logic into named packages instead of keeping everything inside `Main`. When a task's status needs updating, construct a new `Task` record with the updated status rather than mutating the record internally.

### Illustrating business-logic testing

Once a project declares **JUnit Jupiter (JUnit 5)** as a test dependency, a test class can be written as shown below; this illustrates testing the `Main` design above and belongs under `src/test/java`:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;

class TaskTest {
    @Test
    void openTaskPastDeadlineIsOverdue() {
        var task = new Main.Task(1, "Review Java",
                LocalDate.of(2030, 6, 9), Main.Status.TODO);
        assertTrue(task.isOverdue(LocalDate.of(2030, 6, 10)));
    }

    @Test
    void completedTaskIsNotOverdue() {
        var task = new Main.Task(2, "Completed",
                LocalDate.of(2030, 6, 1), Main.Status.DONE);
        assertFalse(task.isOverdue(LocalDate.of(2030, 6, 10)));
    }

    @Test
    void blankTitleIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> new Main.Task(3, "   ",
                        LocalDate.of(2030, 6, 10), Main.Status.TODO));
    }
}
```

JUnit is **not bundled in the JDK**; to run it with Maven or Gradle, add the dependency and configure the appropriate test runner. The lesson here is turning small business rules into repeatable, automated checks.

## 6. Capstone Project for the Learning Path

**Proposal: a personal task-management CLI application**, running on JDK 17 with no machine-specific assumptions. Learners may pick an equivalent domain (book catalog, mock orders, study schedule) while keeping comparable complexity.

### Functional requirements

1. Add tasks with ID, title, status, and due date; validate valid ID, non-blank title, supported status, and date format.
2. List, look up by ID, filter by status, sort by due date, and mark tasks as completed.
3. Summarize total count, completed count, and overdue count; clearly define “overdue” as **before** the reference date and **not** yet completed.
4. Persist/load data from files using `Path`/`Files` and UTF-8; report clear errors when the file does not exist, data is corrupted, or read permissions are missing.
5. Provide an intuitive menu/command interface that exits cleanly without crashing on common malformed input.

To store structured data, choose a well-defined format. If using JSON or CSV for non-trivial cases, pick an appropriate library and declare its dependency; **Java 17 has no built-in general-purpose JSON binding library**. Do not write a naive comma-splitting parser assuming every field is trivial.

### Design and technical requirements

- Separate at least **model/domain**, **service/business logic**, **storage**, and **CLI interface**. Name classes and methods meaningfully rather than putting the entire program in one class.
- Use `enum` for status, `LocalDate` for dates, and properly typed collections/generics; consider records for immutable data. Avoid passing `null` as a control-flow mechanism across layers.
- Never swallow exceptions; display user-friendly messages for input mistakes while preserving root causes for system errors during investigation.
- Write unit tests for business rules, covering normal cases, edge cases, and invalid inputs. Storage read/write code should have integration tests using temporary directories rather than relying on pre-existing local files.
- Track changes with Git; declare JDK target 17 and dependencies in the project; ensure run instructions do not rely on personal machine paths.

### Scenarios you must prove yourself

| Scenario | Expected Behavior |
| --- | --- |
| Add a valid task | Saved and retrievable with exact ID, title, status, and due date |
| Title consisting only of whitespace | Rejected with a clear reason |
| Duplicate ID | Does not create a second record with the same ID |
| Due date is yesterday, not done | Counted as overdue |
| Due date is today | Not counted as overdue under the definition above |
| Completed task with past due date | Not counted as overdue |
| Empty list | Displays an empty result without errors |
| Reading a corrupted or malformed file | Handled gracefully; never silently treats corrupted data as valid |
| Save, restart, and reload | Persisted data reloads intact without losing information |

## 7. Verifiable Completion Criteria

A stage is considered complete when the learner can **explain the concepts in their own words, write the practice exercise independently, and handle edge cases**. Watching videos end-to-end or copying examples does not demonstrate practical Java proficiency.

Across the entire path, verify these competency areas:

| Competency Area | Evidence of Completion |
|---|---|
| **Environment** | Can check out the project and run build/tests/app from the terminal; Java 17 target is clearly configured |
| **Language and OOP** | Can explain primitives/references, `equals`, encapsulation, interfaces, records, and enums, and apply them properly in code |
| **APIs and data** | Chooses `List`/`Set`/`Map`, generics, Streams, `java.time`, and `Files` appropriately; handles errors properly |
| **Java 17 features** | Uses suitable finalized features and recognizes features introduced or finalized only in newer JDKs |
| **Testing** | Automated tests pass; cover happy paths, failure cases, and edge cases; can reproduce and fix newly reported bugs |
| **Handover** | Includes source code, a `README` with run instructions, usage examples, key design decisions, and known limitations |
| **Technical explanation** | Can walk through the data flow from input → processing → storage → output, and justify at least one design or data-structure choice |

**Suggested passing bar:**

- All required capstone features work without data-loss bugs across the test scenarios listed above.
- Compiles and runs at the Java 17 level; does not require preview flags or a higher JDK version to run.
- Business-logic unit tests and key integration checks pass in a clean environment with declared dependencies.
- The learner independently fixes at least one newly introduced bug (such as duplicate IDs, due date equal to today, or malformed file input) by reproducing it, finding the root cause, fixing it, and adding a regression test.
- Looking at any piece of their own code, the learner can explain **why** they chose that approach rather than merely reading each line aloud.

If any area falls short, revisit the corresponding stage and add focused practice exercises rather than restarting from scratch. Once core competencies are solid, move on to next topics such as SQL/JDBC, web APIs, Spring, performance tuning, security, or upgrading to newer LTS JDKs depending on project needs.

## 8. How to Study Without Forgetting What You Learned Earlier

Follow this loop in each stage: **understand the concept → write a small example without looking at solutions → test edge cases → read the API docs → integrate into the project**. Keep a brief log of what you learned, bugs you hit, and how you proved your understanding.

Principles to keep your knowledge sharp:

- **Master one standard workflow first:** terminal + one IDE + one build tool. Add extra tools only with a clear purpose.
- **Separate standard APIs from external libraries:** JUnit, Jackson, and frameworks do not come bundled merely because the JDK is installed.
- **Read full error messages:** check exception type, location, call stack, and offending data before making edits.
- **Do not overuse new features:** use loops when clearer than Streams; use regular classes when records do not fit; use inheritance/sealed types only when the domain calls for them.
- **Invest time in testing:** passing on one sample input does not prove correctness under real-world cases.
- **Keep code Java 17 compatible:** when reading guides written for Java 21/25 or later, verify features and APIs before applying them.

Prioritize authoritative primary sources: [dev.java — Learn Java](https://dev.java/learn/), [Java SE 17 API Documentation](https://docs.oracle.com/en/java/javase/17/docs/api/index.html), and the [OpenJDK JEP Index](https://openjdk.org/jeps/0). Use API documentation to verify actual method contracts, and use JEPs to verify when features were introduced and whether they are preview or final.
