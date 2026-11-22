# Why Successful Compilation Does Not Create a Safe Runtime Environment

## 1. Meaning of "Compiled Successfully"

In Java, `javac` parses source code, checks language rules, types, names, access rights, and many compile-time constraints. If there are no errors halting compilation, it produces bytecode (usually `.class` files) that the JVM can load and execute later.

**Successful compilation proves that the code passed the compiler's checks in that exact compilation context. It does not prove that every execution path is correct, safe, has resources, has access permissions, or uses the right libraries at runtime.**

Separate three questions:

1. **Does it compile?** Are the source code and the dependencies visible to the compiler valid under the current JDK/flags?
2. **Can it launch and operate?** Can the JVM load, verify, and link the required classes; are the environment, libraries, configuration, files, and services suitable?
3. **Does it run safely, accurately, and stably?** Are input data, execution flows, access permissions, concurrent state, memory, resources, and exceptions under control?

A program can answer "yes" to question 1 yet "no" to question 2 or 3. Conversely, a program that runs on a development machine does not by itself prove that it is safe in production.

### Intuitive Example

```java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Hello, " + args[0]);
    }
}
```

Save as `Greeting.java` and run on Java 17+:

```powershell
javac Greeting.java
java Greeting World
```

Output:

```text
Hello, World
```

However, if you run `java Greeting` without passing arguments, the program throws `ArrayIndexOutOfBoundsException` at the expression `args[0]`. `javac` cannot know in advance how many elements the argument array will have at runtime.

This is the fundamental difference between **type validity** and **runtime-condition validity**.

## 2. What Does the Compiler Guarantee, and Where Are Its Limits?

| What `javac` can check | What it cannot guarantee for every run |
| --- | --- |
| Valid syntax, names, and declarations per language version | Users always enter valid data |
| Static type compatibility where sufficient information is available | All runtime values satisfy business constraints |
| Conditions such as definite assignment and unreachable code per Java rules | Every real branch is tested |
| Existence/signatures of APIs on the current compile classpath | Runtime has the same dependency versions and environment |
| Certain warnings about raw types, unchecked operations, and deprecated APIs when appropriate lint flags are enabled | Code has no logic bugs, race conditions, or security vulnerabilities |
| Bytecode generation matching the specified target/version | Target JVM has the right classes, resources, permissions, and configuration |

Java is a statically typed language, yet static types do not express all data rules: `int` permits the value 0; `String` can be empty, contain dangerous characters, or be malformed; a reference of type `User` can be `null` wherever Java permits.

For example, `10 / divisor` is type-valid even though `divisor` might be 0. `Files.readString(path)` is API-valid even though the file might not exist. `List<String>` helps the compiler check list usage in source code, but does not prevent the application from receiving wrongly typed data via reflection, raw types, serialization, or an unchecked integration boundary.

**Do not confuse three control layers:** compile-time checking, runtime boundary checking, and behavioral testing. Each layer addresses a different set of risks.

## 3. Lifecycle from Source Code to JVM: Still Many Points of Failure

A typical path:

```text
.java + compile dependencies
          |
          v
javac: parse / static checks / generate .class
          |
          v
Build: test / package / create JAR or image
          |
          v
Deploy: deliver artifact + configuration + dependencies
          |
          v
JVM: load -> link (verify/prepare/resolve) -> initialize
          |
          v
Execute: handle data, threads, I/O, network, resources
          |
          v
Runtime outcome: correct / incorrect / exception / hang / resource exhaustion
```

The diagram provides an overview. According to the JVMS, linking consists of *verification*, *preparation*, and *resolution*; some resolution steps may be performed lazily, when a reference is actually used. Class initialization may occur when a class is first used under specific conditions.

### 3.1. Class Loading and Linking

The compiler compiles a call like `service.execute()` based on the method signature and classes present on the **compile classpath/module path**. At runtime, the JVM must locate the right class and link the necessary references.

If a runtime dependency is missing or differs from the compile version, the program can encounter:

- `NoClassDefFoundError` when the JVM needs a class definition but cannot find/recover it (possibly due to a missing dependency or a prior initialization failure).
- `NoSuchMethodError` when bytecode references a method whose matching signature no longer exists at runtime.
- `NoSuchFieldError` or `IncompatibleClassChangeError` when binary structure changes incompatibly.
- `UnsupportedClassVersionError` if the JVM is too old for the bytecode format of the class to be loaded.

These errors belong to the `LinkageError` family or load/link-related `Error` types; many only appear when an execution path actually uses the class/member involved. A successful build of artifact A does not prove that the dependency version the JVM runs with is the one the compiler saw.

### 3.2. Bytecode Verification Is Not Business Testing

The JVM has a bytecode verification step to protect structural constraints and type safety of the virtual machine. This is crucial, yet it **does not check algorithm correctness, validity of user data, endpoint security, or the availability of external services**.

A program with validly verified bytecode can still throw `NullPointerException`, miscalculate prices, deadlock, or overwrite data. Verification and behavioral testing perform two different jobs.

### 3.3. Class Initialization Can Still Fail

Java allows initializing static fields via code executed at runtime:

```java
public class Settings {
    static final int PORT = Integer.parseInt(
        System.getProperty("service.port")
    );
}
```

This is an **illustrative code snippet**, not a program with `main`. The code compiles, yet if during `Settings` initialization the `service.port` property is missing or not a valid integer, the `Integer.parseInt` call can throw an exception; an error during initialization can surface as `ExceptionInInitializerError`. Subsequent accesses to the failed class may encounter `NoClassDefFoundError`.

The compiler cannot guarantee that every required system property will exist upon deployment.

## 4. Experiment: Compilation Succeeds Yet Runtime Data Causes Errors

**Standalone file `UnsafeDivide.java` on Java 17+:**

```java
public class UnsafeDivide {
    public static void main(String[] args) {
        int divisor = Integer.parseInt(args[0]);
        System.out.println(100 / divisor);
    }
}
```

Commands:

```powershell
javac --release 17 UnsafeDivide.java
java UnsafeDivide 4
```

Stdout:

```text
25
```

With the exact same `.class` file, the following arguments produce different outcomes:

| Command | Runtime behavior |
| --- | --- |
| `java UnsafeDivide 4` | Prints `25`, exits normally |
| `java UnsafeDivide` | `ArrayIndexOutOfBoundsException` because `args[0]` is missing |
| `java UnsafeDivide abc` | `NumberFormatException` because `abc` is not an integer |
| `java UnsafeDivide 0` | `ArithmeticException: / by zero` |
| `java UnsafeDivide 3` | Prints `33` due to integer division, which may be inappropriate if the problem requires decimals |

Full messages and stack traces depend on JDK/code location; the table focuses on failure types and outcomes. Nothing changed in the source code or bytecode between runs. What changed was the **runtime input**.

`javac`'s success only states that `args[0]` is a `String` expression, `parseInt` returns `int` when successful, and dividing two integers is permitted by the language. It cannot prove `args.length >= 1`, that the value is parseable, or that the denominator is non-zero.

### 4.1. Version with Input Condition Checks

**File `ValidatedDivide.java`:**

```java
public class ValidatedDivide {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("ERROR: expected one integer argument");
            return;
        }

        final int divisor;
        try {
            divisor = Integer.parseInt(args[0]);
        } catch (NumberFormatException ex) {
            System.err.println("ERROR: argument is not an integer");
            return;
        }

        if (divisor == 0) {
            System.err.println("ERROR: divisor must not be zero");
            return;
        }

        System.out.println("RESULT=" + (100 / divisor));
    }
}
```

Run:

```powershell
javac --release 17 ValidatedDivide.java
java ValidatedDivide 4
java ValidatedDivide 0
java ValidatedDivide abc
```

Corresponding output:

```text
RESULT=25
```

The next two commands write to **stderr**, one line each:

```text
ERROR: divisor must not be zero
ERROR: argument is not an integer
```

The new version intentionally handles bad input instead of letting uncaught exceptions escape from `main`. However, this **still does not guarantee the entire application is safe**: the example is limited to integer division and does not automatically solve rounding requirements, access permissions, system resources, or concurrency state. In a production CLI, add a non-zero exit code for error branches so scripts/CI detect failure; the `return` statements in `main` here primarily illustrate data validation.

### 4.2. Condition Checking Is a Runtime Contract

Questions to ask at data-intake boundaries:

1. Is **enough** data present? Could it be `null`, missing a field, missing an argument, or missing a key?
2. Is the **format** valid? Date/number parsing, charset, identifiers?
3. Is it within the **value domain**? Non-zero number, range 1 to 100, non-negative amount?
4. Are **relationships** between fields valid? Is the start date no later than the end date?
5. Does it fit **permissions and system state**? Does the resource exist, is the caller authorized, does the transaction state permit the transition?
6. If conditions fail, does the application **fail cleanly under control** or fall into unexpected behavior?

Never replace validation with a forced cast, `@SuppressWarnings`, or a single successful compilation.

## 5. Compile-Time Type Safety Does Not Eliminate All Runtime Type Errors

Java generics help the compiler prevent many invalid assignments, yet **type erasure** exists alongside boundaries where static types lack sufficient information.

The following example is not a recommended practice:

```java
import java.util.ArrayList;
import java.util.List;

public class UnsafeGeneric {
    public static void main(String[] args) {
        @SuppressWarnings({"rawtypes", "unchecked"})
        List<String> words = new ArrayList();

        @SuppressWarnings({"rawtypes", "unchecked"})
        List raw = words;
        raw.add(123);

        System.out.println(words.get(0).length());
    }
}
```

The code can compile on Java 17+, even with those warnings suppressed. Yet at runtime a `ClassCastException` occurs when `words.get(0)` is placed in a `String` context. The compiler accepted the type assumption provided by the code, while the list actually contains an `Integer`.

**Suppressing warnings does not fix type errors.** For safety, eliminate raw types, validate data boundaries, and prefer APIs that accurately express data types. Similarly, reflection, deserialization, or external libraries may supply values outside static assumptions; verify the values actually received.

Note: the case above throws an exception because a cast to `String` is inserted per generic semantics; the failure usually occurs when reading an element through `List<String>`, not when inserting `123` via the raw view.

## 6. Compiling Against One Library, Running Against Another

This is an especially common cause in multi-module Java applications and CI/CD pipelines.

```text
Compile time                  Runtime
------------------            ---------------------
app source                     app.jar
  + library-v2.jar   --->        + library-v1.jar
  |                               |
javac checks v2 signature      JVM loads and links against v1
  |                               |
compile PASS                    linkage error or old behavior
```

For instance, a client is compiled to call `Api.newFeature()` present in library v2. If runtime instead loads v1 lacking a method with the matching name/signature, `NoSuchMethodError` can occur when the call is linked. Of course, exact conditions depend on name, descriptor, static/instance nature, and actual bytecode.

Variants worth investigating:

- A dependency is missing from the runtime classpath.
- Multiple JARs contain the same class name; the class loader picks a version different from the expected one.
- A dependency was restructured while the client has not been recompiled/re-released.
- The project compiles with a newer JDK while the server runs an older JVM.
- The artifact was built correctly, yet the deployment pipeline uses an old image/JAR.
- The service loads a different config/file version than the development machine.

### 6.1. How to Inspect Loaded Classes and Versions

Useful commands:

```powershell
java -version
javac -version
jar tf path/to/app.jar
javap -classpath path/to/app.jar -verbose example.Main
```

`jar tf` lists packaged entries; `javap -verbose` displays class details, constant pool, and bytecode major version. They help inspect artifacts, but do not by themselves prove the running process is executing that exact file.

To trace classes loaded by the JVM on Java 17+:

```powershell
java -Xlog:class+load=info -cp "app.jar;libs/*" example.Main
```

This is a **sample command**: replace `example.Main`, `app.jar`, and the libs directory to match your actual application. On Windows use `;` to separate classpath entries; on Linux/macOS use `:`. Logs are typically long; filter for relevant classes.

In diagnostic code, a class can retrieve its `CodeSource`:

```java
System.out.println(
    SomeLibraryClass.class.getProtectionDomain().getCodeSource()
);
```

This is **illustrative code placed inside a method**, not a standalone program. `CodeSource` can be `null` depending on the class loader/protection policy, so cross-check with class-loading logs and actual artifacts.

### 6.2. Meaning and Limitations of `--release`

`javac --release 17` instructs the compiler to compile against the language, class-file target, and standard Java APIs provided for release 17. It helps prevent accidentally calling standard APIs only present in newer Java releases. However, this option **does not automatically verify all third-party libraries**, does not guarantee the server has enough resources, and does not check runtime behavior.

For example, class files compiled for Java 21 may not run on a Java 17 JVM because the class file format is unsupported. Compiling with `--release 17` establishes an appropriate baseline, yet you still must **test running on the exact target JRE/JDK** and inspect bundled libraries.

## 7. I/O Resources, Environment, and External Services

A valid call such as:

```java
String text = java.nio.file.Files.readString(
    java.nio.file.Path.of("config.txt")
);
```

is only **illustrative code that must be placed inside a method** handling/declaring `IOException`. At runtime, it can fail if the file does not exist, the path is wrong, permissions are lacking, storage malfunctions, or the charset/content is unsuitable.

DB connections, HTTP, queues, and third-party services pose the same issue: the compiler sees the API/client library, but does not know whether the network is reachable, TLS certificates are valid, the server responds in time, or credentials are right.

### File-Reading Example with Error Handling

**File `ReadConfig.java`:**

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class ReadConfig {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("ERROR: expected one file path");
            return;
        }

        try {
            String content = Files.readString(
                Path.of(args[0]), StandardCharsets.UTF_8
            );
            System.out.println("CHARS=" + content.length());
        } catch (IOException | SecurityException ex) {
            System.err.println("ERROR: unable to read file");
        }
    }
}
```

Run:

```powershell
javac --release 17 ReadConfig.java
java ReadConfig missing-config.txt
```

If the file does not exist in the current directory, the program prints to stderr:

```text
ERROR: unable to read file
```

The example intentionally avoids printing the absolute path, file contents, or sensitive information in the error message. In real systems, internal logs should capture enough context for operations while avoiding leaking secrets. Additionally, `Path.of` can throw `InvalidPathException` (an unchecked exception) if the input path is invalid, and other severe resource errors can still happen. Catching these two types here illustrates **handling an expected set of failures**, not an error-free guarantee.

Good practices for I/O and resources:

- Validate mandatory configuration at startup (fail fast), reporting which setting is missing without exposing secret values.
- Handle timeouts, bounded retries, and backoff on remote operations when appropriate for idempotency.
- Use `try-with-resources` for streams, connections, and resources that need closing, even when exceptions occur.
- Set data size limits, connection limits, and timeouts to reduce resource exhaustion risks.
- Check access permissions and allowlist paths/hosts based on business needs. Do not treat checking `Files.exists` before opening a file as race-proof (TOCTOU), since file state can change in between.
- For external services, use health/readiness checks, metrics, and error alerts instead of relying on a "green compile."

## 8. Successful Compilation Does Not Prevent Concurrency Bugs

The compiler permits multiple threads to access the same mutable variable. It does not automatically turn `counter++` into an *atomic* increment. Because `counter++` involves multiple read/compute/write steps, two threads can overwrite each other's updates; without synchronization mechanisms, there are also visibility issues under the Java Memory Model.

Example **at risk of a data race**:

```java
public class RacyCounter {
    static int count = 0;

    public static void main(String[] args) throws InterruptedException {
        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                count++;
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(count);
    }
}
```

Save as `RacyCounter.java`, run `javac --release 17 RacyCounter.java` and `java RacyCounter`. The program **compiles**, yet the result can be less than 200000 due to lost updates. Sometimes it still prints 200000; **never use one lucky run to prove the absence of a race condition**. Results vary depending on scheduling/JIT/hardware.

A proper fix for the simple counter problem is `AtomicInteger`:

**File `AtomicCounter.java`:**

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounter {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger count = new AtomicInteger();

        Runnable task = () -> {
            for (int i = 0; i < 100_000; i++) {
                count.incrementAndGet();
            }
        };

        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(count.get());
    }
}
```

Run:

```powershell
javac --release 17 AtomicCounter.java
java AtomicCounter
```

Stdout after both threads finish:

```text
200000
```

Here `incrementAndGet()` guarantees an atomic increment, and `join()` makes main wait for both threads. For more complex state, merely replacing individual variables with atomics may not preserve invariants spanning multiple variables; locks, immutable state, transactions, or clear ownership design may be required.

The compiler also does not automatically detect all deadlocks, livelocks, starvation, transaction ordering errors, or races across requests. Concurrency tests, Java Memory Model reviews, and observation of real systems are needed.

## 9. Security Safety Does Not Come from Compiling Successfully

Dangerous code or code lacking permission checks can still be valid Java. For example, a program using JDBC that concatenates input directly into SQL can compile cleanly while introducing a SQL injection vulnerability.

**Illustration of the wrong approach (not runnable as a standalone program):**

```java
String sql = "SELECT * FROM users WHERE username = '" + username + "'";
```

If `username` comes from an untrusted source, string concatenation turns user data into part of the SQL syntax. The right approach with JDBC is using a parameterized query:

```java
String sql = "SELECT * FROM users WHERE username = ?";
try (java.sql.PreparedStatement statement =
         connection.prepareStatement(sql)) {
    statement.setString(1, username);
    try (java.sql.ResultSet rows = statement.executeQuery()) {
        // Process results with authorization and data checks.
    }
}
```

The JDBC snippet is **illustrative code inside a method with a valid `connection` and `username`, handling `SQLException`**; it is not a standalone program. Parameter binding separates input from query syntax. However, safer queries do not replace authorization: the user still might not be permitted to view the returned record.

Runtime controls to consider depending on the application:

- **Authentication and authorization:** every request/operation must be permission-checked against a specific identity and resource.
- **Context-aware validation and encoding:** check format, value domain, output encoding, and proper parameter binding; do not just generically "filter weird characters."
- **Protect secrets:** load sensitive data from managed configuration sources, restrict read permissions, and avoid logging secrets or exposing them in external stack traces.
- **Dependencies and configuration:** track library vulnerabilities, control versions, TLS, and access rights; the compiler does not verify dependency trustworthiness.
- **Resource limits:** size/timeouts/rate limits/concurrency limits to prevent inputs from exhausting memory, CPU, or connections.
- **Data and transactions:** verify business invariants, record ownership, and commit/rollback boundaries.

Security flaws require threat modeling, testing, and configuration reviews; you cannot infer "secure" solely because `javac` emitted `.class` files without errors.

## 10. Resources and Exceptions: Catching Everything Is Not Safe

Java distinguishes `Exception` and `Error`; many runtime failures are unchecked exceptions or system-related error types. `NullPointerException`, `IndexOutOfBoundsException`, and `IllegalArgumentException` are examples of unchecked exceptions; `OutOfMemoryError`, `StackOverflowError`, and linkage errors belong to the `Error` group.

Do not handle all failures with `catch (Throwable t)` and proceed as normal. After a severe VM, memory, or class-initialization error, remaining state may not be fit to continue safely. Determine which errors are recoverable and which must fail gracefully, log, and terminate/restart the appropriate component.

**Checked exceptions** (such as `IOException`) force code to catch or declare `throws` on corresponding calls; this does not guarantee the error is handled properly in business terms. For instance, `throws IOException` makes the program compile-valid, yet file reading can still fail in production.

For resources supporting `AutoCloseable`, prefer:

```java
try (var input = java.nio.file.Files.newInputStream(path)) {
    // Read data within the usage scope.
} // input is closed when exiting the block, even if an exception is thrown.
```

This is an **illustrative code snippet**, requiring `path` to be defined and `IOException` handled/declared. `try-with-resources` closes resources, yet exceptions can still happen when opening, reading, or closing; handle them according to application policy.

## 11. Post-Compilation Testing and Verification

To move from "compiles" to "reliable at runtime," build multiple layers of checks. Each layer catches a distinct class of defects; no single layer replaces all the others.

| Layer | Primary check | Remaining blind spots |
| --- | --- | --- |
| `javac`, `-Xlint`, `-Werror` | Syntax/types/warnings provided by the compiler | Business logic, runtime environment |
| Static analysis and dependency scan | Certain bug patterns, known vulnerabilities, coding patterns | Behavior under real data and configuration |
| Unit tests | Logic branches, edge cases, exceptions | Real connections, actual classpath/deployment |
| Integration/contract tests | Module coordination, DB/API, serialization | Heavy load, production-only issues |
| Runtime testing on exact JDK/JAR/image | Linkage, classpath, class initialization, configuration | Unsimulated data and traffic |
| Load/stress/concurrency tests | Races, throughput, latency, resource usage | Not all schedules can be covered |
| Security tests/reviews | Authorization, injection, secret management, configuration | Emerging threats or uncovered surfaces |
| Production observability | Logs, metrics, traces, alerts, crash evidence | Detects after an incident occurs if prevention is lacking |

### 11.1. Data Matrix for an Operation

Example with `ValidatedDivide`:

| Data group | Sample input | What to verify |
| --- | --- | --- |
| Normal | `4` | Output `25` |
| Error boundary | `0` | Controlled error, no crash |
| Invalid format | `abc` | Parse failure message |
| Missing | No arguments | Reports missing argument |
| More than expected | `4 5` | Reports wrong argument count |
| Negative value | `-4` | Integer division result matches requirements |
| Very large value | `999999999999` | Does not pass parsing as if valid |

If business requirements demand decimal division, Java printing `33` for `100 / 3` is **language-correct yet potentially business-wrong**. Tests must specify the expected contract (e.g., using `BigDecimal` and rounding rules) rather than merely verifying the code throws no exceptions.

### 11.2. Configuration Layers to Verify

- **Build:** JDK, `--release`, compiler flags, compile classpath, dependency graph, generated sources.
- **Artifact:** JAR contents, metadata/version, packaged config files, runtime libraries.
- **Runtime:** actual `java -version` on host/container, classpath/module path, and actual loaded class sources.
- **Infrastructure:** file/network permissions, DNS, certificates, database, resource limits, clock/timezone, environment configuration.
- **Operations:** startup checks, readiness, health, error logs, alerts, timeouts, rollback, and deployment procedures.

Do not just run unit tests from an IDE: try running the **exact released artifact** in an environment as close to the deployment target as possible.

## 12. Diagnostic Workflow When "Build Is Green but Execution Breaks"

Follow sequentially to avoid fixing the wrong root cause:

1. **Record the symptoms clearly:** run command, environment, JDK, artifact/version, input, timestamp, exception/error, and the first meaningful stack trace.
2. **Classify the failure stage:** startup/load/link/init, or a failure inside a request/worker after the application was already running?
3. **Confirm the actual artifact and dependencies:** JAR hash/version, classpath/module path, class-loading logs, image/container tag, and runtime configuration.
4. **If caused by input:** reproduce with minimal input data, identify the missing precondition, and add validation/contract tests.
5. **If caused by the environment:** compare permissions, environment variables, files, DNS, credentials, ports, external services, quotas, and timeouts.
6. **If caused by concurrency:** inspect shared mutable state, synchronization boundaries, transactions, thread dumps, and load tests. One passing test does not rule out a data race.
7. **If a security issue:** trace untrusted data paths, authentication, authorization, parameter binding, and least-privilege resources.
8. **Fix the root cause and verify:** recompile, run relevant tests, execute the built artifact in a near-production environment, and monitor for recurrence.

A quick triage table:

| Symptom | Primary area to investigate |
| --- | --- |
| `NoClassDefFoundError` when invoking a feature | Missing dependency, class initialization failure, or class loader |
| `NoSuchMethodError` | Compile/runtime dependency mismatch, binary API change |
| `UnsupportedClassVersionError` | Runtime JDK older than class-file target |
| `ExceptionInInitializerError` | Error inside static initializer or static field initialization |
| `NumberFormatException`, `IndexOutOfBoundsException` | Input validation and code assumptions |
| `IOException`, connection timeout | Files, permissions, network, dependent services |
| Random wrong results under concurrent load | Data race, missing synchronization, transaction conflict |
| `OutOfMemoryError` | Memory limits, leaks, oversized input, backpressure |
| Unauthorized data access without exceptions | Authorization and security logic |
| Works on local machine, fails on server | Different artifact, JDK, configuration, or environment |

**Do not handle LinkageError by catching a broad exception and ignoring it.** For version and classpath problems, fixing dependencies/deployment is the root solution. For data errors, fix preconditions and define clear error behavior. For resource errors, apply usage limits and operational policies.

## 13. Common Misconceptions

**"Java is statically typed, so `ClassCastException` cannot happen."** False. Runtime casts, generic erasure, raw types, and reflection can still produce type errors at runtime.

**"No warnings means no bugs."** False. Compiler diagnostics only cover the patterns it checks; `-Xlint:all` does not prove business logic or security either.

**"Using `--release` properly guarantees deployment will run."** False. It sets the compilation baseline for standard APIs and bytecode, but does not check external dependencies, configuration, or required services.

**"Once the JVM verifies bytecode, the code is safe."** False. Verification protects virtual machine structural/type-safety rules; it does not ensure business correctness, access permissions, or service availability.

**"Catching `Exception` stops all failures."** False. There are `Error` types; even caught exceptions can leave invalid business state if handled carelessly.

**"The code worked once, so there is no race."** False. Scheduling is not predetermined in a fixed order; concurrency bugs may only surface under load or in rare timing windows.

**"Checking `exists` guarantees the file is still there when opened."** False. That is a time-of-check to time-of-use (TOCTOU) bug; the environment can change after the check.

**"Compile PASS means the software is secure."** False. The compiler does not enforce authorization, scan every dependency vulnerability, or know which data a user is permitted to view.

## 14. Self-Assessment Exercises

1. **`args[0]` has type `String`. Why does the code still throw an error when arguments are missing?**  
   Because the static type does not guarantee the actual size of the args array. You must check `args.length`.

2. **Code calling a new library method compiled, yet deployment throws `NoSuchMethodError`. What should you check?**  
   Check the dependency used for compilation and the JAR actually loaded at runtime, along with the corresponding bytecode signature.

3. **Does `@SuppressWarnings("unchecked")` make a generic cast safe?**  
   No. It only affects compiler diagnostics; properly typed data or boundary validation is still needed.

4. **Why is `counter++` unsafe even though `int` and both threads are properly typed?**  
   The increment is not atomic and can lose updates; synchronization/atomic semantics are a runtime design responsibility.

5. **A file-reading API declares `throws IOException` and compiles. What does that guarantee?**  
   It only guarantees that checked-exception handling rules were respected at compile time. Files/permissions/devices can still fail.

6. **An operation returns another user's data without throwing an exception. What category of bug is this?**  
   An authorization/security logic bug. Normal compilation and execution do not prove access control is enforced.

7. **To reduce the risk of "green build, broken production," what should be added?**  
   Validation, appropriate unit/integration/contract/security/load tests, JDK and runtime dependency checks, running the exact artifact, environment configuration checks, and operational observability.

## 15. Pre-Release Checklist

- [ ] CI compiler and JDK/toolchain are specified; `--release` is used when a runtime baseline is needed.
- [ ] Build addresses relevant warnings; `javac` PASS is not equated with whole-system quality.
- [ ] All untrusted inputs check format, bounds, consistency, and access permissions.
- [ ] Missing/empty/invalid/boundary cases are tested; error paths have appropriate messages and state.
- [ ] Dependency/runtime classpath, class loader, and JDK on the target environment are verified.
- [ ] Required configuration, permissions, secrets, paths, and external services are verified.
- [ ] I/O/connections have resource limits, timeouts, and proper exception handling.
- [ ] Shared mutable state and transactions have proper synchronization/atomic/transaction mechanisms.
- [ ] Tests and smoke checks run on the exact artifact intended for release.
- [ ] Logs/metrics/alerts and a rollback plan are in place when runtime behavior exceeds assumptions.

**Core takeaway:** `javac` checks the static validity of code in the compilation environment. **Runtime safety** also depends on data, actually loaded bytecode and libraries, class initialization, configuration, resources, concurrency, security, and testing. Use the compiler as the first line of defense, then prove runtime contracts with validation, tests, and real-world observability.

## Further Reading

- [Java Language Specification — §12: Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html)
- [Java Virtual Machine Specification — §5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html)
- [Java SE 21 — javac Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [Java SE 21 — java Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Java SE 21 — Throwable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Throwable.html)
- [Java SE 21 — AtomicInteger](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)