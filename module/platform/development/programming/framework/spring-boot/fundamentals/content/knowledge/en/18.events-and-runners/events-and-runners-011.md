# CommandLineRunner with the Command-Line Arguments Array

In Spring Boot, many applications need to perform work right after the Spring container initializes: printing startup info, reading CLI arguments, checking configuration, importing data, or triggering a batch job. `CommandLineRunner` is an interface provided by Spring Boot for this scenario.

The defining feature of the interface is the method:

```java
void run(String... args) throws Exception;
```

The `String... args` parameter contains the application arguments passed from the launch command into the program. Inside the method, `args` behaves like a `String[]` array. The runner can inspect each element to decide what work to perform.

This lesson explains how to declare a `CommandLineRunner`, how arguments travel from the terminal into `run`, how to read and validate the array, the runner's role in the Spring Boot lifecycle, and key differences from `ApplicationRunner`.

## 1. What Is CommandLineRunner?

`CommandLineRunner` is a Spring Boot functional interface in package `org.springframework.boot`. Its main signature is:

```java
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

This is a simplified form focusing on the method to implement. When a Spring bean implements this interface, Spring Boot invokes `run(...)` while completing startup.

Characteristics:

- A runner is a **Spring bean**; it can receive dependencies via constructor injection.
- The `run` method is called after the application context has refreshed.
- Runners execute before Spring Boot publishes `ApplicationReadyEvent`.
- The `args` parameter contains the application arguments passed to `SpringApplication.run(...)`.
- Multiple runners can be registered and ordered with `@Order` or `Ordered`.
- Unhandled exceptions from a runner can cause startup to fail.

Example use case: an application dedicated to importing data from CSV. You want to initialize services/repositories via dependency injection and perform the import once per **application startup**. A runner provides an appropriate execution point.

However, "once per startup" is not "once across an entire cluster": if three processes start concurrently, the runner executes in all three processes.

## 2. The `String... args` Array in Java

The ellipsis `...` in `String... args` is Java's varargs syntax. Inside the method body, this parameter can be used just like a regular string array.

```java
@Override
public void run(String... args) {
    System.out.println("Argument count: " + args.length);

    for (int i = 0; i < args.length; i++) {
        System.out.println("args[" + i + "] = " + args[i]);
    }
}
```

Basic operations:

- `args.length`: number of elements.
- `args[0]`: first element, if present.
- `args[args.length - 1]`: last element, if the array is non-empty.
- `for (String arg : args)`: iterate sequentially.
- `Arrays.toString(args)`: string representation for inspection, provided no sensitive data is included.

In Java, varargs are represented as an array at runtime. Therefore `String... args` and `String[] args` behave almost identically inside the method body, while the varargs form matches the exact API signature.

**Important note:** the array can be empty. Accessing `args[0]` without checking length causes an `ArrayIndexOutOfBoundsException` when no arguments are supplied.

## 3. Minimal Example: Printing Arguments at Startup

Create the application class:

```java
package com.example.cli;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CliApplication {
    public static void main(String[] args) {
        SpringApplication.run(CliApplication.class, args);
    }
}
```

Create the runner:

```java
package com.example.cli;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class ArgumentsPrinter implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Argument count: " + args.length);
        for (int i = 0; i < args.length; i++) {
            System.out.println("args[" + i + "] = " + args[i]);
        }
    }
}
```

Run the application:

```bash
java -jar app.jar hello spring boot
```

Output produced by the runner looks like:

```text
Argument count: 3
args[0] = hello
args[1] = spring
args[2] = boot
```

Other Spring Boot startup logs may appear before or around these lines. They do not alter the array contents.

`@Component` makes Spring register the runner class as a bean if it lies within component scan scope. Merely writing `implements CommandLineRunner` without placing the object into the Spring container will not cause Boot to call the method.

## 4. Data Flow: From Terminal to `run`

The command:

```bash
java -jar app.jar import orders.csv
```

is passed by the Java launcher as application arguments into:

```java
public static void main(String[] args) {
    SpringApplication.run(CliApplication.class, args);
}
```

Spring Boot captures this array on startup; after initializing the context, Boot forwards it to startup runners.

```text
Terminal / shell
     │
     ▼
java -jar app.jar import orders.csv
     │
     ▼
main(String[] args)
     │
     ▼
SpringApplication.run(CliApplication.class, args)
     │
     ▼
Spring ApplicationContext is refreshed
     │
     ▼
CommandLineRunner.run(String... args)
     │
     ▼
args[0] = "import"
args[1] = "orders.csv"
```

For proper forwarding, pass `args` into `SpringApplication.run`. If bootstrapping manually with a `SpringApplication` instance, the equivalent is:

```java
public static void main(String[] args) {
    SpringApplication application =
            new SpringApplication(CliApplication.class);
    application.run(args);
}
```

Developers define the **meaning** of each element; Spring Boot does not automatically treat the string `import` as a subcommand.

## 5. Positional Arguments vs. Named Options

Two CLI argument forms are common.

### 5.1. Positional Arguments

```bash
java -jar app.jar import data/orders.csv
```

Array:

```text
["import", "data/orders.csv"]
```

You establish by convention that the first element is the command name and the second is the file. This is concise syntax for small CLIs.

### 5.2. Named Options

```bash
java -jar app.jar --job=import --input=data/orders.csv --dry-run
```

`CommandLineRunner` receives the strings verbatim:

```text
["--job=import", "--input=data/orders.csv", "--dry-run"]
```

It **does not automatically split** `--job=import` into two fields `job` and `import`; if you want them split, you must parse the strings manually or use `ApplicationArguments`.

### 5.3. Paths with Spaces

```bash
java -jar app.jar import "data/orders November.csv"
```

When the shell processes quotes properly, the runner receives two elements:

```text
args[0] = import
args[1] = data/orders November.csv
```

Quoting, escaping, and command-line splitting rules can differ across Bash, PowerShell, and Windows CMD. Verify with the actual runtime shell.

### 5.4. JVM Options Differ from Application Arguments

```bash
java -Duser.timezone=UTC -jar app.jar --job=import orders.csv
```

`-Duser.timezone=UTC` is handled by the Java launcher as a JVM system property; it does not enter `main(String[] args)`. Meanwhile, `--job=import` and `orders.csv` come after the JAR name and are application arguments.

## 6. Spring Boot Can Use Named Options as Properties

Spring Boot normally adds `--key=value` arguments into the `Environment`'s property sources when command-line property support is enabled.

Example:

```bash
java -jar app.jar --spring.profiles.active=dev --server.port=9090
```

These values can be used by Spring Boot to activate profiles or set the port, while runners still see both raw strings inside `args`.

Distinguish three sources:

| Source | Data Received | Used For What? |
|---|---|---|
| `CommandLineRunner.run(String... args)` | Raw application arguments array | Custom CLI logic |
| `Environment` | Properties resolved across multiple sources | Configuring beans and Boot |
| `ApplicationArguments` | API with option names/values and non-option arguments | Easier named CLI parsing |

An argument prefixed with `--spring....` can configure Boot while still appearing in the array passed to runners. Therefore, index-based code—such as always treating `args[0]` as the job name—can break if an operator passes extra properties beforehand.

## 7. Validate Argument Count Before Using It

Never assume every startup includes arguments.

Wrong:

```java
@Override
public void run(String... args) {
    String job = args[0]; // Can fail if args.length == 0
    System.out.println(job);
}
```

Minimal safe handling:

```java
@Override
public void run(String... args) {
    if (args.length == 0) {
        System.out.println("No command requested.");
        return;
    }

    String job = args[0];

    if ("import".equals(job)) {
        System.out.println("Running import");
    } else {
        System.out.println("Unrecognized command: " + job);
    }
}
```

If the application is strictly for batch runs and **requires** a command, you can throw `IllegalArgumentException` with usage instructions instead of silently skipping. For a web application with an optional runner, having zero arguments may be completely normal.

The business contract determines behavior when the array is empty.

## 8. Practical Example: CSV Import Runner

Suppose the defined CLI syntax is:

```text
import <file.csv>
```

A runner delegating to a business service:

```java
package com.example.cli;

import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class CsvImportRunner implements CommandLineRunner {

    private final CsvImportService importService;

    public CsvImportRunner(CsvImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(String... args) throws Exception {
        if (args.length == 0) {
            return;
        }

        if (!"import".equals(args[0])) {
            return;
        }

        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: import <file.csv>"
            );
        }

        Path file = Path.of(args[1]);

        if (!Files.isRegularFile(file)) {
            throw new IllegalArgumentException(
                    "File not found: " + file
            );
        }

        importService.importFile(file);
    }
}
```

The example assumes `CsvImportService` is registered as a Spring bean and exposes `importFile(Path)`.

Command line:

```bash
java -jar app.jar import data/orders.csv
```

Execution steps:

1. The runner receives exactly two elements.
2. Confirms the command is `import`.
3. Converts the path string to a `Path`.
4. Verifies the input is a regular file.
5. Delegates data processing to the service.

This organization keeps the runner focused on **startup orchestration and CLI parsing**, while CSV reading, record validation, and database writes live in a separately testable service.

**Limitation of this example:** if additional options precede `import`, the current parser does not understand them. That is why you should document exact syntax or use a structured parser for complex CLIs.

## 9. Manually Parsing Simple Options

For small syntax such as:

```bash
java -jar app.jar --job=export --output=data/report.csv --dry-run
```

you can iterate over the array:

```java
@Override
public void run(String... args) throws Exception {
    boolean exportRequested = false;
    boolean dryRun = false;
    String output = null;

    for (String arg : args) {
        if ("--job=export".equals(arg)) {
            exportRequested = true;
        } else if ("--dry-run".equals(arg)) {
            dryRun = true;
        } else if (arg.startsWith("--output=")) {
            output = arg.substring("--output=".length());
        }
    }

    if (!exportRequested) {
        return;
    }

    if (output == null || output.isBlank()) {
        throw new IllegalArgumentException(
                "Missing --output=<path>"
        );
    }

    exportService.exportTo(Path.of(output), dryRun);
}
```

The example assumes `exportService` is Spring-injected and provides `exportTo(Path, boolean)`.

This parser is intentionally minimal to illustrate `String... args`. It does not handle duplicate options, conflicting flags, unknown options, or rich help messages. When the option count grows, prefer `ApplicationRunner` or a proper CLI library.

Another note: `String.startsWith(...)` does not interpret quotes or shell rules itself. By the time the runner receives the strings, the shell has already built the JVM argument vector.

## 10. CommandLineRunner vs. ApplicationRunner

Spring Boot also provides `ApplicationRunner`, likewise invoked during startup yet receiving an `ApplicationArguments` object:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
```

Comparison:

| Criterion | CommandLineRunner | ApplicationRunner |
|---|---|---|
| `run` parameter | `String... args` | `ApplicationArguments` |
| Data form | Raw strings | Parsed options and non-option arguments |
| Checking `--dry-run` | Search array manually | `containsOption("dry-run")` |
| Reading `--input=file.csv` | Split string manually | `getOptionValues("input")` |
| Getting positional arguments | Custom index/parser | `getNonOptionArgs()` |
| Getting raw array | Received directly | `getSourceArgs()` |
| Startup ordering | Supports `@Order` | Supports `@Order` |

Both are startup runners invoked by Boot when registered as context beans. The most important difference is the **argument-reading API**, not lifecycle timing.

## 11. ApplicationArguments When a CLI Has Many Named Options

Alternative to the manual option parser:

```java
import java.nio.file.Path;
import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class StructuredImportRunner implements ApplicationRunner {

    private final CsvImportService service;

    public StructuredImportRunner(CsvImportService service) {
        this.service = service;
    }

    @Override
    public void run(ApplicationArguments args) throws Exception {
        List<String> jobs = args.getOptionValues("job");
        if (jobs == null || !jobs.contains("import")) {
            return;
        }

        List<String> files = args.getOptionValues("input");
        if (files == null || files.size() != 1 ||
                files.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Exactly one --input=<file.csv> is required"
            );
        }

        boolean dryRun = args.containsOption("dry-run");

        service.importFile(
                Path.of(files.get(0)),
                dryRun
        );
    }
}
```

The example assumes the service has an overload `importFile(Path, boolean)`.

With the command:

```bash
java -jar app.jar --job=import --input=data/orders.csv --dry-run
```

`ApplicationArguments` provides:

- `getOptionValues("job")`: list containing `import`.
- `getOptionValues("input")`: list containing `data/orders.csv`.
- `containsOption("dry-run")`: `true`.
- `getNonOptionArgs()`: list of non-option elements.
- `getSourceArgs()`: original string array.

`getOptionValues(...)` returns `null` if the option is absent. For a valueless flag that is present, it returns an empty list; when merely checking presence, `containsOption` is usually clearer.

**Do not register two runners handling the same import command simultaneously** when you only want one execution. The examples show both interfaces for comparison, not because Boot will pick only one of them if both are beans.

## 12. Declaring Runners with `@Bean` and Lambdas

Because `CommandLineRunner` is a functional interface, you can create a runner directly with a lambda from a `@Bean` method:

```java
import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class StartupConfiguration {

    @Bean
    CommandLineRunner greetingRunner() {
        return args -> {
            System.out.println(
                    "Startup argument count: " + args.length
            );
        };
    }
}
```

Spring Boot calls this lambda at startup as long as the configuration is loaded and the bean is registered.

If a service is needed:

```java
@Configuration(proxyBeanMethods = false)
public class JobConfiguration {

    @Bean
    CommandLineRunner jobRunner(JobService jobService) {
        return args -> jobService.execute(args);
    }
}
```

Here `JobService` needs an `execute(String[])` method or compatible overload for the string array.

Distinction:

- `@Component` + class implementing the interface: fits complex parsers, constructor injection, and isolated testing.
- `@Bean` + lambda: fits short startup tasks that read clearly inline.
- Business logic should still live in dedicated services, avoiding putting full domain processing inside factory methods or runners.

## 13. When Runners Are Invoked in the Lifecycle

Key milestones of a successful startup:

```text
main(String[] args)
       │
       ▼
SpringApplication.run(...)
       │
       ▼
Prepare Environment and ApplicationContext
       │
       ▼
Refresh context, initialize required beans
       │
       ▼
ApplicationStartedEvent
       │
       ▼
ApplicationRunner / CommandLineRunner
       │
       ▼
ApplicationReadyEvent
       │
       ▼
Application is considered ready
```

`ApplicationStartedEvent` is published after the context refreshes, before runners are invoked. `ApplicationReadyEvent` is published after runners complete successfully.

Consequences:

- Runners can use Spring-injected repositories/services.
- Long-running runners extend the time before the application is marked ready.
- Runners throwing unhandled exceptions can prevent startup from completing.
- Runners do not re-execute on every incoming HTTP request.

In web applications, the embedded server may already bind its port during context refresh. However, "listening port" and "application achieving readiness" are two distinct states; in deployment, rely on proper readiness/liveness mechanisms.

### 13.1. Difference from `@PostConstruct`

`@PostConstruct` is a per-bean callback invoked while that bean is initializing. `CommandLineRunner` runs after the application context has refreshed, making it more appropriate for tasks needing multiple ready beans.

If you need to validate an object's configuration, use `@ConfigurationProperties` validation. If you need to bootstrap work built on services, a runner can fit. Avoid cramming all initialization logic into runners by habit.

## 14. Multiple Runners and `@Order`

An application can have multiple `CommandLineRunner` and `ApplicationRunner` beans. Spring Boot sorts startup runners by order metadata.

```java
@Component
@Order(10)
public class PrepareRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Prepare");
    }
}
```

```java
@Component
@Order(20)
public class ExecuteRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Execute");
    }
}
```

In the ordering mechanism, lower numbers take precedence first:

```text
PrepareRunner (10)
       │
       ▼
ExecuteRunner (20)
```

You can implement `Ordered` instead of `@Order`:

```java
@Component
public class CleanupRunner
        implements CommandLineRunner, Ordered {

    @Override
    public int getOrder() {
        return 30;
    }

    @Override
    public void run(String... args) {
        System.out.println("Cleanup");
    }
}
```

Keep these distinctions in mind:

- Order controls **runner invocation order**, not the creation order of every bean in the container.
- `ApplicationRunner` participates in the same ordering mechanism.
- If runners share the same order, do not rely on their appearance order in Java files.
- If step B strictly depends on the result of step A, an explicit orchestration service calling A then B is usually easier to maintain than two separate runners linked only by order numbers.

## 15. Exception Handling and Startup Failures

`run(String... args)` is allowed to throw `Exception`:

```java
@Override
public void run(String... args) throws Exception {
    if (args.length == 0) {
        throw new IllegalArgumentException(
                "Missing task arguments"
        );
    }

    jobService.execute(args);
}
```

If an exception escapes a runner, Spring Boot typically considers startup failed. `ApplicationReadyEvent` is not published as in a successful startup; the application may publish `ApplicationFailedEvent` and close the context.

Sometimes fail-fast is right: a mandatory batch job should fail when a file is missing or arguments are invalid. For a web server, an auxiliary task should not unintentionally block HTTP serving unless business requirements demand it.

Example error handling with logging:

```java
@Override
public void run(String... args) throws Exception {
    try {
        jobService.execute(args);
    } catch (IOException ex) {
        log.error("Failed to process input", ex);
        throw ex;
    }
}
```

This example assumes the class has a `log` logger and the service can throw `IOException`. Rethrowing preserves the startup failure semantics; avoid logging the exact same error redundantly across multiple layers.

If an error is recoverable, implement retries/compensation inside an appropriate service or job infrastructure. Never catch every exception silently and let the context falsely report ready.

## 16. Do Runners Execute in Web Applications?

Yes. `CommandLineRunner` operates in `WebApplicationType.NONE`, `SERVLET`, or `REACTIVE` applications whenever registered as a bean.

Example:

```java
@Component
public class StartupNoticeRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        System.out.println("Application context started");
    }
}
```

This runner still gets invoked if the program is a web server. It runs only at startup, not when users send HTTP requests.

For batch/CLI tools, disable the web server with:

```properties
spring.main.web-application-type=none
```

`NONE` does not disable dependency injection or runners. It only instructs Spring Boot to create a non-web application context.

If the same codebase serves both web and batch modes, control which runners are registered so an import task does not run unintentionally every time the web server redeploys.

## 17. Enabling Runners Only When Needed: Profiles and Conditions

You can use `@Profile` to restrict a runner:

```java
@Component
@Profile("batch-import")
public class BatchImportRunner implements CommandLineRunner {

    private final CsvImportService service;

    public BatchImportRunner(CsvImportService service) {
        this.service = service;
    }

    @Override
    public void run(String... args) throws Exception {
        service.runImport(args);
    }
}
```

Run when the matching profile is enabled:

```bash
java -jar app.jar --spring.profiles.active=batch-import --job=import --input=data/orders.csv
```

Note that `args` will include `--spring.profiles.active=batch-import`, so your service/parser needs to handle those strings or use `ApplicationRunner` for named options.

You can use conditional bean registration:

```java
@Component
@ConditionalOnProperty(
    prefix = "jobs.csv-import",
    name = "enabled",
    havingValue = "true"
)
public class ConditionalImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        // Invoked only when jobs.csv-import.enabled=true.
    }
}
```

When the condition is not satisfied, the runner bean is not registered and Boot will not call it.

Combining profiles/conditions with argument validation clarifies three separate decisions: *when a job is available*, *which job the user requested*, and *which arguments are mandatory for the job*.

## 18. Batch Runners, Process Exit, and Exit Codes

A runner does not automatically terminate the JVM when `run` finishes. Even with `NONE`, the JVM may exit only when no non-daemon threads or components keep the process alive. A listener, scheduler, or connection pool might keep the process running depending on configuration.

If you want a batch application to run and return an exit status to a scheduler, manage the context and exit code at the entry point:

```java
@SpringBootApplication
public class BatchApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(BatchApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        ConfigurableApplicationContext context = app.run(args);
        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }
}
```

`SpringApplication.exit(context)` closes the context and resolves the exit code from registered `ExitCodeGenerator` beans. `System.exit(exitCode)` terminates the process with that code.

This example is meant for intentional batch entry points. Do not put `System.exit` inside a web service runner because it will shut down the HTTP server immediately after startup.

If you need conventions like 0 = success, 2 = bad arguments, 3 = missing input, define and test your own exit code policy. `CommandLineRunner` does not supply such a mapping on its own.

## 19. Runners and Transactions

Runners can invoke repositories through services:

```java
@Component
public class SeedRunner implements CommandLineRunner {

    private final SeedService service;

    public SeedRunner(SeedService service) {
        this.service = service;
    }

    @Override
    public void run(String... args) {
        service.seedIfNeeded();
    }
}
```

Business service:

```java
@Service
public class SeedService {

    private final ProductRepository repository;

    public SeedService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void seedIfNeeded() {
        if (repository.count() == 0) {
            repository.save(new Product("DEMO"));
        }
    }
}
```

The example assumes entity/repository and transaction infrastructure are configured. `CommandLineRunner` itself does not wrap `run(...)` in a transaction; defining transaction boundaries belongs in service design.

With multiple application instances, checking `repository.count() == 0` then inserting can race across processes. To maintain data consistency, use unique constraints, migrations, or proper concurrency coordination. Runners do not provide distributed locks or exactly-once guarantees.

## 20. Common Mistakes When Using `String... args`

| Symptom | Cause | Remediation |
|---|---|---|
| `ArrayIndexOutOfBoundsException` | Reading `args[0]` when array is empty. | Check `args.length`. |
| Arguments not received | `main` did not pass `args` to `SpringApplication.run` or bad CLI call. | Check bootstrap and command line. |
| `--job=import` not split | `CommandLineRunner` receives raw strings. | Parse strings manually or use `ApplicationRunner`. |
| Path with spaces split into parts | Incorrect quoting/escaping for the shell. | Quote paths per the actual shell. |
| Runner not invoked | Class is not a bean or profile/condition unmet. | Check component scan, `@Bean`, profiles, and conditions. |
| Job runs again on web server restart | Runner executes on every context startup. | Gate jobs conditionally and design for idempotence. |
| Duplicate import | Multiple runners handle the command or multiple instances start. | Assign a single owner and control concurrency. |
| Startup never reaches ready | Runner blocks for a long time or throws an exception. | Pick proper lifecycle and handle errors intentionally. |
| `@Order` does not affect bean creation | Ordering applies to runner invocations. | Express creation dependencies directly via DI/services. |
| `-Dkey=value` missing from args | That is a JVM option. | Use System properties or application options `--key=value`. |

Also, do not print the entire raw command line in production if it may contain tokens, passwords, or sensitive paths. Log job names, status, and safe operational metadata; mask or omit secrets.

## 21. Testing Runners

### 21.1. Unit Testing via Direct Invocation

Since a runner is a regular Java object, you can instantiate it with mock/fake services and invoke `run(...)`:

```java
@Test
void ignoresUnknownCommand() throws Exception {
    CsvImportService service = mock(CsvImportService.class);
    CsvImportRunner runner = new CsvImportRunner(service);

    runner.run("help");

    verifyNoInteractions(service);
}
```

This example uses Mockito and JUnit; include corresponding test imports/dependencies in the project. There is no need to start a web server just to test a command-parsing branch.

For valid import test cases, use `@TempDir` to create a temporary file, call the runner with `"import"` and the path, and verify the service was invoked properly. Also test empty args, missing paths, and nonexistent paths.

### 21.2. Integration Testing with `@SpringBootTest`

`@SpringBootTest` supports passing application arguments to a Spring application test:

```java
@SpringBootTest(args = {"--mode=test", "--dry-run"})
class StartupArgumentsTest {

    @Autowired
    ApplicationArguments arguments;

    @Test
    void hasDryRunFlag() {
        assertTrue(arguments.containsOption("dry-run"));
    }
}
```

The example requires Spring Boot Test/JUnit and the corresponding imports.

**Note:** runner beans can still execute when `@SpringBootTest` creates an application context. Avoid letting integration tests accidentally trigger production imports or call live services. Gate startup jobs with profiles/conditions or substitute dependencies with appropriate mocks/fakes.

## 22. Practice Exercises

### Exercise A — Observe the Argument Array

Create `ArgumentsPrinter` as in section 3. Run:

```bash
java -jar app.jar one two three
```

and:

```bash
java -jar app.jar one "two three"
```

Compare `args.length` and each element's content.

### Exercise B — File Import Command

Design a runner accepting `import <file.csv>`. When the file argument is missing, report usage syntax; when the file does not exist, report a clear error. Extract CSV reading into a service.

### Exercise C — Named Options

Parse `--job=export --output=report.csv --dry-run` using `CommandLineRunner`. Then rewrite it using `ApplicationRunner` and compare parser complexity.

### Exercise D — Multiple Runners

Create two `CommandLineRunner` beans with `@Order(10)` and `@Order(20)`. Observe the order. Add an `ApplicationRunner` with an intermediate order value and verify the combined order.

### Exercise E — Profiles and Readiness

Use `@Profile("batch")` so the import runner registers only in the batch profile. Observe behavior when the profile is inactive, when active with valid arguments, and when input is missing.

### Exercise F — Startup Failure

Have the runner throw `IllegalArgumentException` on invalid input. Observe the startup outcome. Then design error reporting and exit codes for a batch job without swallowing exceptions.

### Exercise G — Multi-Instance

Simulate two application instances starting simultaneously with a data-seeding runner. Explain why the runner can execute twice and how to preserve data consistency using transactions, unique constraints, migrations, or coordination mechanisms.

## 23. Key Takeaways

1. `CommandLineRunner` is a startup hook invoked by Spring Boot when a bean implementing this interface exists in the context.
2. `run(String... args)` receives the raw application arguments array in the order passed to `SpringApplication.run`.
3. `String...` is varargs; inside the method it can be used just like `String[]`.
4. Always check `args.length` before indexing into the array.
5. `--key=value` options remain single strings in `CommandLineRunner`; `ApplicationRunner` fits better when named options must be parsed.
6. Runners must be registered via `@Component`, `@Bean`, or appropriate Spring bean registration mechanisms.
7. Multiple runners can be registered and ordered using `@Order` or `Ordered`.
8. Runners execute after context refresh and before `ApplicationReadyEvent`; unhandled exceptions can cause startup failure.
9. Runners also run in web applications if registered as beans; they are not HTTP request handlers.
10. Runners run on every application startup, without guaranteeing cluster-wide exactly-once execution.
11. Separate CLI parsing, validation, business logic, and transactions into clear responsibilities.
12. For batch processes, explicitly decide the web application type, shutdown behavior, and exit codes.

When designing a `CommandLineRunner`, define clearly: **which strings the user passes, which conditions the runner validates, and which service executes the business logic?** Then choose how the runner is enabled, its execution order, and its failure policy so startup behavior stays predictable and easy to operate.
