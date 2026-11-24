# Validating Input, Usage Messages, and Avoiding Logging Secrets in Spring Boot

## 1. The problem: startup arguments are also untrusted data

A Spring Boot application can receive parameters from the command line:

```bash
java -jar job.jar --mode=import --input=data.csv
```

This example has two options: `mode` and `input`. Users can omit an option, mistype a name, repeat an option, supply an empty value, or accidentally pass a password in a place visible to the OS or logging system.

A program with reliable startup behavior needs to coordinate three tasks:

1. **Input validation:** define supported options, value counts, required constraints, formats, and cross-option relationships.
2. **Usage/help messages:** explain valid syntax, run examples, and rejection reasons without exposing sensitive data.
3. **Protecting secrets:** never print tokens, passwords, keys, connection strings with credentials, or raw arguments into logs, exceptions, metrics, or error messages.

In Spring Boot, we typically use `ApplicationArguments` inside `ApplicationRunner` to validate arguments after the container is built. `CommandLineRunner` receives the raw `String[]` array if manual string processing is truly required. Choose the approach matching the timing of validation.

**Core principle:** command-line data is external input; do not trust it simply because it was passed to `main(String[] args)`.

## 2. How does Spring Boot process application parameters?

A Java application has an entry point:

```java
public static void main(String[] args) {
    SpringApplication.run(MyApplication.class, args);
}
```

The lines above are illustrative, requiring a Spring Boot–configured class `MyApplication` and an import of `SpringApplication`. The `args` array is provided by the JVM after the shell has split arguments according to shell rules.

Spring Boot creates an `ApplicationArguments` object at startup. Primary APIs:

| API | Meaning |
| --- | --- |
| `getSourceArgs()` | Returns the raw argument array. **May contain secrets**; do not log directly |
| `getOptionNames()` | Set of recognized option names, e.g., `mode`, `input` |
| `containsOption("mode")` | Whether an option named `mode` appeared |
| `getOptionValues("mode")` | List of values attached to the option; `null` if option is absent |
| `getNonOptionArgs()` | Arguments not following option syntax, e.g., `data.csv` |
| `ApplicationRunner.run(ApplicationArguments)` | Callback after refresh, receiving the classified arguments object |
| `CommandLineRunner.run(String...)` | Callback after refresh, receiving raw strings |

**Specific notes on `getOptionValues`:**

- Option **absent**: returns `null`.
- Option **present without a value**, such as `--verbose`: returns an empty list.
- Option `--mode=import`: returns a list containing `"import"`.
- Repeated option, such as `--mode=check --mode=import`: can yield multiple values; explicit rules are needed to reject or process them.
- Option with an empty value `--mode=`: must not be considered a valid mode, even though the parser creates the option entry.

Distinguishing `null` from `List.of()` is vital: a valueless `--help` flag is valid, whereas valueless `--mode` is invalid in a CLI requiring a specific mode.

### Use consistent option syntax

With Spring Boot, the easiest form to control is:

```bash
java -jar job.jar --mode=check
java -jar job.jar --mode=import --input=data.csv
java -jar job.jar --help
```

When supplying a value for an option, prefer `--key=value`. Do not assume:

```bash
java -jar job.jar --mode import
```

is interpreted like `--mode=import`. In Spring Boot's command-line option classifier, `--mode` may be treated as a valueless flag and `import` as a non-option argument. That is why usage guides must document exact syntax and validation must inspect **both option values and positional arguments**.

Other shell/CLI tools may accept `--mode import`; do not carry that parser's assumptions into `ApplicationArguments` without testing.

## 3. Three validation layers: syntax, semantics, and environment

Do not check only "whether an option exists". A reliable program distinguishes:

| Layer | Question | Example Error | How to Handle |
| --- | --- | --- | --- |
| Syntax | Are option names and formatting valid? | `--mdoe=check`, `--mode`, repeated `--mode` | Show valid syntax, reject input |
| Semantics | Are values in allowed domains? Are options compatible? | `--mode=erase`, import mode missing input | State valid values and required conditions |
| Environment | Are required resources and configs accessible? | Missing file, missing read permission, credentials unavailable | Report environment error safely without leaking data |

Example rules for a tool:

- `--help`: print usage and execute no business logic.
- `--mode=check`: run check, do not accept `--input`.
- `--mode=import --input=data.csv`: run data import workflow; `input` is required.
- Reject positional arguments.
- Reject unknown options in a simple CLI.
- Reject modes outside the set `check` / `import`.
- Reject blank or repeated values for single-valued options.
- Do not accept API tokens via command-line options. Supply credentials via environment or an appropriate secret manager.

These rules must be documented and tested. An option can be syntactically valid yet semantically invalid: `--mode=import` is structurally valid yet missing `--input`.

## 4. Fail fast without exposing user data

When required parameters are missing or wrong, the program should reject **before performing business work**, while printing actionable guidance.

Example good message:

```text
Input error: --mode must be check or import.
Usage:
  java -jar job.jar --mode=check
  java -jar job.jar --mode=import --input=data.csv
  java -jar job.jar --help
```

Example message to avoid:

```text
Invalid args: [--mode=import, --input=/private/customer-list.csv,
               --api-token=secret-value-here]
```

Not every path is a secret, yet paths can reveal system layout, customer names, or internal locations. An API token on the command line is even riskier because it can appear in shell history, process lists, crash reports, or logs.

Therefore:

- **Name the parameter to fix** if that name is a program-controlled constant.
- For invalid values, prefer describing the allowed domain rather than echoing the raw value.
- Do not print the `args` array or `ApplicationArguments.getSourceArgs()`.
- Do not concatenate secrets into exception messages.
- Use error codes/exceptions with non-sensitive messages.
- Print usage to `System.err` on bad input and `System.out` when the user requests `--help`.
- Do not silently ignore unknown options; a typo can cause the program to run in the wrong mode.

**"Fail fast" here means failing before business logic inside the runner**, not that Spring Boot has not created a context yet. `ApplicationRunner` runs **after** refresh, potentially after beans or a web server have initialized. If a required value must be valid **before creating beans**, validate configuration earlier; section 11 explains this distinction.

## 5. Complete example: Spring Boot CLI with safe validation and usage

The example below uses Java 17+ and Spring Boot 3.3.x. It runs non-web so no HTTP port opens. The code intentionally **does not actually read a file**: it focuses on parameter validation and safe logging policies so you can observe the results cleanly without real data.

### 5.1. Project structure

```text
safe-args-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          args/
            SafeArgsApplication.java
      resources/
        application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'safe-args-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Version 3.3.13 is chosen to illustrate Spring Boot 3.3 branch behavior; real deployed projects should use a version still supported and receiving security updates by your organization. To run with `./gradlew`, the project needs a compatible Gradle wrapper; the build file above does not generate a wrapper automatically.

`src/main/resources/application.properties`:

```properties
spring.application.name=safe-args-demo
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
```

### 5.2. Java 17+ source

File `src/main/java/demo/args/SafeArgsApplication.java`:

```java
package demo.args;

import java.io.PrintStream;
import java.util.List;
import java.util.Set;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class SafeArgsApplication {

    private static final Set<String> ALLOWED_OPTIONS =
            Set.of("help", "mode", "input");

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(SafeArgsApplication.class, args)) {
            // Explicitly close context after runner finishes.
        }
    }

    @Bean
    ApplicationRunner checkedJobRunner() {
        return arguments -> {
            // Support only published option names.
            if (!ALLOWED_OPTIONS.containsAll(arguments.getOptionNames())) {
                reject("Unsupported option.");
            }

            // --help must stand alone and take no value.
            if (arguments.containsOption("help")) {
                List<String> helpValues =
                        arguments.getOptionValues("help");

                if (!helpValues.isEmpty()
                        || arguments.getOptionNames().size() != 1
                        || !arguments.getNonOptionArgs().isEmpty()) {
                    reject("Use --help without other arguments.");
                }

                printUsage(System.out);
                return;
            }

            // Disallow unexpected positional arguments.
            if (!arguments.getNonOptionArgs().isEmpty()) {
                reject("Unexpected positional argument.");
            }

            String mode = oneValue(arguments, "mode", true);
            String input = oneValue(arguments, "input", false);

            if (!Set.of("check", "import").contains(mode)) {
                reject("--mode must be check or import.");
            }

            if ("import".equals(mode) && input == null) {
                reject("--input is required for import mode.");
            }

            if ("check".equals(mode) && input != null) {
                reject("--input is only supported in import mode.");
            }

            // Log only the validated mode and boolean presence.
            // Never log the input path or raw arguments.
            System.out.println("validated mode=" + mode);
            System.out.println("input supplied=" + (input != null));

            // Actual business logic runs only after validation.
        };
    }

    private static String oneValue(
            ApplicationArguments args, String name, boolean required) {
        List<String> values = args.getOptionValues(name);

        if (values == null) {
            if (required) {
                reject("Missing required --" + name + ".");
            }
            return null;
        }

        if (values.size() != 1
                || values.get(0) == null
                || values.get(0).isBlank()) {
            reject("--" + name + " requires exactly one nonempty value.");
        }

        return values.get(0);
    }

    private static void reject(String message) {
        System.err.println("Input error: " + message);
        printUsage(System.err);

        // Do not put raw arguments into the exception message.
        throw new IllegalArgumentException("Invalid command-line arguments.");
    }

    private static void printUsage(PrintStream out) {
        out.println("Usage:");
        out.println("  ./gradlew bootRun --args='--mode=check'");
        out.println(
                "  ./gradlew bootRun --args='--mode=import --input=data.csv'");
        out.println("  ./gradlew bootRun --args='--help'");
    }
}
```

**Explaining each decision:**

1. `SafeArgsApplication` is the Spring Boot entry point. `SpringApplication.run` creates/refreshes the context and calls the runner.
2. `checkedJobRunner` is an `ApplicationRunner` registered via `@Bean`. It checks options before executing work.
3. `ALLOWED_OPTIONS` holds only option names supported by the CLI. The program does not print unknown option names supplied by the user so unwanted data does not enter logs.
4. `--help` is handled before the `mode` requirement. Users can view usage before knowing the syntax.
5. `--help` is accepted **only when standing alone**. `--help=anything` or `--help --mode=check` will be rejected.
6. `oneValue` distinguishes absent options, valueless options, empty values, and multiple values.
7. `mode` is checked against an allowlist before printing. `input` is logged only as a boolean, not the actual path.
8. `reject` prints the message and usage to stderr, then throws an exception with a fixed message containing no user data.
9. `try-with-resources` closes the context after `run` succeeds, fitting short-lived CLI apps. For web/daemon applications, do not copy this immediate context closing.
10. If the runner throws an error, `run` does not return a context to the try block; Spring Boot has its own startup-failure handling path. Do not expect startup-failure logs to consist solely of the lines in `reject`.

### 5.3. Running valid cases

When the project has a Gradle wrapper, run:

```bash
./gradlew bootRun --args='--mode=check'
```

Lines printed by the demo code:

```text
validated mode=check
input supplied=false
```

Try import mode:

```bash
./gradlew bootRun --args='--mode=import --input=data.csv'
```

Lines:

```text
validated mode=import
input supplied=true
```

No `data.csv` path appears in the code's output, even though the program received and syntactically validated the option. The demo **does not read the file yet**; in a real application, check the path and permissions in the appropriate business layer.

### 5.4. Helping the user

Run:

```bash
./gradlew bootRun --args='--help'
```

Lines printed by `printUsage`:

```text
Usage:
  ./gradlew bootRun --args='--mode=check'
  ./gradlew bootRun --args='--mode=import --input=data.csv'
  ./gradlew bootRun --args='--help'
```

After printing usage, the runner returns normally. **Spring Boot can still publish `ApplicationReadyEvent`** because `--help` is not an error in this code; it merely causes the runner to skip business work. For a short-lived non-web CLI, the context closes at the end of `try` in `main`.

If the application has multiple runners, `return` in one runner **does not stop other runners**. If `--help` must suppress all other work, use explicit coordination or a single runner managing all startup tasks rather than relying on a local return.

### 5.5. Reproducible error cases

**Missing mode:**

```bash
./gradlew bootRun
```

Initial message from code:

```text
Input error: Missing required --mode.
Usage:
  ./gradlew bootRun --args='--mode=check'
  ./gradlew bootRun --args='--mode=import --input=data.csv'
  ./gradlew bootRun --args='--help'
```

Afterward, Spring Boot may log a startup failure and stack trace; Gradle may report the `bootRun` task failed. Do not treat the block above as **the entirety** of process stdout/stderr.

**Invalid mode:**

```bash
./gradlew bootRun --args='--mode=delete'
```

Main message:

```text
Input error: --mode must be check or import.
```

**Missing input in import mode:**

```bash
./gradlew bootRun --args='--mode=import'
```

Message:

```text
Input error: --input is required for import mode.
```

**Repeated mode:**

```bash
./gradlew bootRun --args='--mode=check --mode=import'
```

Message:

```text
Input error: --mode requires exactly one nonempty value.
```

**Empty mode value:**

```bash
./gradlew bootRun --args='--mode='
```

Validation result can be:

```text
Input error: --mode requires exactly one nonempty value.
```

All error cases above also print usage from `reject`. The logic does not echo raw invalid input values into messages, except literal values predefined in code describing the valid domain.

**Unknown option:**

```bash
./gradlew bootRun --args='--mdoe=check'
```

Message:

```text
Input error: Unsupported option.
```

Thus mistyping an option name is not silently treated as running a default mode. Not echoing unknown option names is a cautious logging policy: option names can be arbitrarily supplied by users and sometimes contain sensitive strings.

## 6. When to use ApplicationRunner vs. CommandLineRunner?

Input can be validated in either interface:

```java
@Component
public final class RawArgsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        // Must classify options and positional arguments manually.
    }
}
```

This is an illustrative class snippet needing `Component` and `CommandLineRunner` imports, placed in `RawArgsRunner.java` in a scanned package. It does not provide `getOptionValues` or `getNonOptionArgs`.

`ApplicationRunner` is usually more convenient because it uses `ApplicationArguments`:

```java
@Component
public final class StructuredArgsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        boolean dryRun = args.containsOption("dry-run");
        System.out.println("dryRun=" + dryRun);
    }
}
```

This snippet requires importing `Component`, `ApplicationRunner`, and `ApplicationArguments`. A `--dry-run` flag needs no value; yet if you want to accept only the flag form, verify no unexpected value is attached:

```java
if (args.containsOption("dry-run")) {
    List<String> values = args.getOptionValues("dry-run");

    if (values != null && !values.isEmpty()) {
        throw new IllegalArgumentException(
                "--dry-run must not have a value.");
    }
}
```

This snippet sits inside a method with a variable `args` of type `ApplicationArguments`, with `java.util.List` imported. Do not log any actual value when raising the error.

**Do not register both `RawArgsRunner` and `StructuredArgsRunner` into the full demo in section 5 and expect unchanged output.** These snippets are variants explaining the API; if added as real beans, they participate in runner ordering and may print extra output.

## 7. How does ApplicationArguments receive multi-valued options?

Some CLIs allow repeated options:

```bash
java -jar job.jar --tag=finance --tag=nightly
```

Then `getOptionValues("tag")` can hold two elements. The application must decide **whether multiple values are allowed**.

If an option may only appear once, `oneValue` in section 5 requires exactly one element.

If repeating is valid, verify the list is non-empty and each element meets constraints:

```java
List<String> tags = args.getOptionValues("tag");

if (tags == null) {
    tags = List.of();
}

for (String tag : tags) {
    if (tag == null || !tag.matches("[a-zA-Z0-9_-]{1,32}")) {
        throw new IllegalArgumentException("Invalid --tag option.");
    }
}
```

This is a snippet placed in a method with `args` of type `ApplicationArguments`; `java.util.List` import is needed. The regex restricts allowed characters, preventing an arbitrary tag from causing log injection or unbounded metric labels.

**Note:** Regex checks only syntax; it does not determine whether a tag is valid in business logic. If a tag represents a customer code or environment name, check an appropriate allowlist/registry before using it.

Avoid:

```java
System.out.println("tags=" + tags);
```

in production code without verifying whether tags can contain PII or sensitive data. A seemingly harmless field can become a data-leak vector as inputs expand later.

## 8. Why should secrets never be put in command-line arguments?

Examples to avoid:

```bash
java -jar job.jar --api-token=my-super-secret-token
java -Dservice.password=my-super-secret-password -jar job.jar
```

These two lines are **anti-pattern examples**, not recommended syntax. Even if code never logs them, secrets can still be exposed via:

- **Shell history:** commands may be saved in terminal history.
- **Process lists:** depending on OS, permissions, and monitoring tools, process arguments can be visible.
- **Orchestration systems:** command specs, job logs, or deployment metadata can contain arguments.
- **Crash/error reporting:** launch metadata may be collected for diagnostics.
- **CI/CD logs:** steps may echo executed commands or passed parameters.
- **Support tickets and screenshots:** users often capture the whole terminal when reporting bugs.

**Not logging secrets** is necessary, yet **not passing secrets in the CLI in the first place** eliminates much more risk.

### Better secret delivery channels

Depending on the deployment environment:

1. **Platform secret manager:** supplies secrets via identity and access-controlled mechanisms; preferred when infrastructure supports it.
2. **Mounted secret files with restricted permissions:** container or host provides files and the app reads them safely. Never commit such files to source repositories.
3. **Environment variables:** convenient in demos and some environments, yet **not completely risk-free**; readable by anyone with access to process environment, deployment config, or debugging tools.
4. **Short-lived identity/role mechanisms:** avoid static credentials when tokens can be obtained via workload identity.

Across these channels, control lifecycle, least-privilege access, rotation, non-logging, and incident response if a secret leaks. No single channel creates an absolute guarantee on its own.

### Example reading a secret from the environment without printing its value

```java
String token = System.getenv("APP_API_TOKEN");

if (token == null || token.isBlank()) {
    throw new IllegalStateException(
            "Required credential APP_API_TOKEN is unavailable.");
}

// Use token with a properly configured client.
// Do not print token, do not concatenate token into exception messages.
```

This snippet belongs inside a Java method with access to `System.getenv`. Real integration needs the appropriate SDK/HTTP client and credential-protection policy. Never do `System.out.println(token)` or `log.debug("token={}", token)`, even in development environments.

**Key mindset:** missing-secret error messages state the **configuration key** defined by code, never the secret value or internal data.

## 9. Logging habits that easily leak secrets

### 9.1. Printing all args

```java
// Avoid: may contain passwords, tokens, or sensitive paths.
System.out.println(Arrays.toString(args));

// Avoid: source data can contain every option passed.
log.info("startup args={}", applicationArguments.getSourceArgs());
```

Both snippets show patterns **to avoid**; importing `Arrays` and having `log`/`applicationArguments` variables are required if placed in a real class.

Replace with:

```java
log.info(
        "Startup validation completed, mode={}, inputSupplied={}",
        safeMode,
        input != null);
```

This snippet assumes an SLF4J logger `log`, a `safeMode` checked against an allowlist, and an `input` variable. It is not a standalone compilable program. Logged parameters should be data **verified as non-sensitive**, not merely renamed from `rawArgs` to `safeMode`.

### 9.2. Concatenating input into exceptions

Avoid:

```java
throw new IllegalArgumentException(
        "Invalid token: " + suppliedToken);
```

Exceptions can reach Spring Boot's automatic logs, APM, or crash-reporting systems. Replace with:

```java
throw new IllegalArgumentException(
        "Invalid credential configuration.");
```

This is an illustrative snippet. When reporting authentication/validation errors, also avoid revealing too much detail that helps unauthorized users infer internal state.

### 9.3. Logging raw Environment or properties

```java
// Avoid in uncontrolled startup diagnostics:
environment.getPropertySources().forEach(System.out::println);
```

Some property sources or debug representations can contain sensitive configuration; unfiltered logging can expose data.

When configuration observability is needed:

- Log only allowlisted **property names** or `configured=true/false` flags.
- Log values **only after verifying they are safe** (e.g., an allowlisted mode).
- Use sanitize/redact features of operations tools when available, without relying solely on default filters.
- Audit log fields of agents, reverse proxies, job orchestrators, and diagnostic endpoints.

### 9.4. Is partially masking a token enough?

For example, `token=abc****xyz` still reveals partial information and can create risk when correlated with other logs. Unless there is a clear operational need, **do not log tokens in any form**. When correlation is needed, log a non-sensitive identifier managed separately by the system, not a slice of the secret.

### 9.5. Log injection via newlines or control characters

User arguments can contain newlines, tabs, or control characters. When written verbatim to logs, a string can forge new log lines or break log-parsing structures.

Example:

```text
--operator=alice
WARN: system compromised
```

This illustrates multi-line data, not a shell command to run. Ways to mitigate risk:

- Log only validated fields with bounded value sets.
- If free-form text must be logged, use structured logging, encode/escape, and bound length.
- Never place free-form user data into log keys, metric names, or unbounded-cardinality labels.
- Keep error messages built from fixed templates without concatenating raw user input.

## 10. How should help/usage messages be designed?

A good help message answers four questions:

1. What does the program do?
2. What is the valid run syntax?
3. Which options are required/optional?
4. What valid examples can be copied and adapted?

Friendly template:

```text
Usage:
  java -jar job.jar --mode=check
  java -jar job.jar --mode=import --input=data.csv
  java -jar job.jar --help

Options:
  --mode=check    Verify configuration without importing.
  --mode=import   Import a supported file.
  --input=FILE    Required only for import mode.
  --help          Show this help text.

Security:
  Supply credentials via an approved secret mechanism.
  Do not pass passwords or API tokens on the command line.
```

Not every program must print this exact template. In the runnable section 5 example, `printUsage` is intentionally concise so output is easy to verify. For real CLIs, add descriptions, OS-appropriate Linux/Windows command examples, and document guaranteed exit codes.

**What not to do:**

- Cram all options onto a single overly long line with no line breaks.
- Report only `Invalid input` without showing how to fix it.
- Print all user arguments on every error.
- Display current secret values as "defaults" in help output.
- Suggest passing tokens via `--password=...` in default instructions.
- Include options the application does not actually support, breaking copy-pasted examples.

### stdout and stderr

Helpful conventions:

- Valid `--help`: print usage to **stdout** and exit normally.
- Invalid input: print error/usage to **stderr**, and mark startup failure appropriately.
- Operational logs: use the logging framework under controlled policies.
- Machine-readable output: if the CLI is used in scripts, keep stdout formatted consistently without mixing JSON/CSV with progress logs.

Using `System.err` to report an error does not automatically produce a non-zero exit code; failure handling/exit codes require an explicit mechanism. Conversely, throwing an exception without printing usage may yield a failure exit code yet poor user experience.

## 11. Validation timing: ApplicationRunner does not block pre-refresh side effects

`ApplicationRunner` is invoked by Spring Boot **after the context has refreshed** and after `ApplicationStartedEvent`, yet before `ApplicationReadyEvent`.

```text
main(args)
   |
   +-- Create SpringApplication
   +-- Prepare Environment and configuration
   +-- Create context
   +-- Load bean definitions, refresh
   |      +-- create required singletons
   |      +-- may start web server
   |
   +-- ApplicationStartedEvent
   |
   +-- ApplicationRunner / CommandLineRunner
   |      +-- Validate CLI arguments
   |      +-- Execute work if valid
   |
   +-- ApplicationReadyEvent
   |
   +-- run() returns if successful
```

Therefore, "validate early" advice has boundaries:

- For a CLI tool without a web server, a runner is a sensible place to validate **before business execution**.
- For a web application, the web server can begin listening during refresh **before the runner**. Do not rely solely on a runner to prevent all HTTP interactions when startup configuration is invalid.
- A `@PostConstruct` or singleton initializer may already have opened a database connection or made external calls before the runner; a runner cannot roll back those side effects.
- If a configuration value determines which beans are created, validate it during the appropriate binding/configuration lifecycle.

### Configuration validation via @ConfigurationProperties

For structured configuration data (unlike a bespoke option parser), you can use:

```java
@ConfigurationProperties(prefix = "job")
@Validated
public record JobProperties(
        @NotBlank String mode,
        @NotBlank String destination) {
}
```

This is an **illustrative pattern requiring additional setup**: import `ConfigurationProperties`, `Validated`, and `jakarta.validation.constraints.NotBlank`; register the properties bean (e.g., `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`), and include a Bean Validation provider, typically via `spring-boot-starter-validation`. `job.mode` / `job.destination` are bound from standard property sources when configured.

Property example:

```properties
job.mode=check
job.destination=output
```

If a field is unconfigured or violates constraints, binding/validation errors can stop startup during the relevant bean-creation phase, **before reaching `ApplicationRunner`**. However, this does not guarantee checks occur before **every** bean or side effect; dependency order also depends on the refresh process.

Avoid placing validation annotations like `@NotBlank` expecting them to take effect automatically without registering the provider/binding configuration properly.

### When is EnvironmentPostProcessor needed?

`EnvironmentPostProcessor` is designed to interact with the environment very early, before the context is fully built. If you need to enforce a **property-source** policy or detect misconfiguration before refresh, you can use this extension point appropriately. However, it requires proper registration and has no business beans available for normal injection.

Do not move all CLI logic into an overly early hook simply because of the phrase "fail fast": operations using repositories, transactions, or Spring-managed components require the post-refresh context.

## 12. Exit codes and failure semantics

CLIs invoked by shells, schedulers, or CI/CD often require exit codes:

- `0`: success, including printing valid `--help` if that is the application's policy.
- Non-zero: syntax error, configuration error, data processing error, or infrastructure error.
- Different codes may be categorized per CLI contract, provided code executes them consistently on every path.

In the section 5 example, `IllegalArgumentException` escaping the runner causes `SpringApplication.run` to fail and the process may terminate with an error. **The example does not guarantee a specific exit code such as 2**, because exit code policy also depends on how the app is run, Boot failure handling, and the launcher.

Spring Boot provides `ExitCodeGenerator` and `SpringApplication.exit(...)` for scenarios requiring exit-code control. Example of an exception declaring an error code:

```java
import org.springframework.boot.ExitCodeGenerator;

public final class InvalidCliOptionsException
        extends RuntimeException implements ExitCodeGenerator {

    public InvalidCliOptionsException() {
        super("Invalid command-line arguments.");
    }

    @Override
    public int getExitCode() {
        return 2;
    }
}
```

This is a complete Java class that can live in `InvalidCliOptionsException.java`. Implementing `ExitCodeGenerator` lets Boot **extract an exit code from the exception during startup**; whether the JVM actually returns code 2 also depends on the handling path and how the app/launcher exits, so test end-to-end.

Example stopping an application after `run` **succeeds** with the exit code computed from the context:

```java
ConfigurableApplicationContext context =
        SpringApplication.run(SomeApplication.class, args);

int code = SpringApplication.exit(context);
System.exit(code);
```

This is an **illustrative** snippet requiring `SomeApplication` to exist and importing `SpringApplication` and `ConfigurableApplicationContext`. If `run` throws an exception, the code obtaining `context` does not execute; this snippet alone cannot handle every parameter error. Additionally, `System.exit` terminates the JVM, so never place it arbitrarily inside shared libraries or servers.

### A note on --help

A runner that prints help and calls `return` is normally treated by Boot as **a runner completing successfully**, not "aborting the entire startup". If the program has multiple runners or is a web service, other beans/runners can still execute. To support `--help` as a true CLI command with deterministic exit-code/short-circuit behavior, design the entry point or orchestration specifically instead of assuming `return` in one runner stops the entire `SpringApplication`.

## 13. Validating file paths without leaking sensitive details

With `--input=...`, checking "non-empty string" is only the first step. If the application actually reads a file, it typically needs to:

1. Convert the string to a `Path` using system semantics.
2. Resolve absolute/relative paths, working directory, and an allowed base directory.
3. Verify the file exists, is a regular file, is readable, and matches a supported format.
4. Account for symlinks, canonical paths, and allowed directory boundaries.
5. Avoid error messages containing sensitive paths or file contents.
6. Read using proper resource handling, such as `try-with-resources`.
7. Never assume a prior `Files.exists` check guarantees the file still exists at open time—changes can occur between check and use.

Illustrative snippet:

```java
Path path = Path.of(inputPath).toAbsolutePath().normalize();

if (!Files.isRegularFile(path) || !Files.isReadable(path)) {
    throw new IllegalArgumentException(
            "Input file is missing or unreadable.");
}
```

This snippet requires importing `java.nio.file.Path` and `java.nio.file.Files`, with variable `inputPath` already present. It **does not yet fully solve traversal/symlink issues and access control**. In systems handling untrusted files, establish an allowed base directory, consider `toRealPath` when appropriate, and enforce permissions at open time.

Never log:

```java
System.err.println("Cannot open secret input: " + inputPath);
```

if the path could leak information. Safe messages should have fixed error codes and generic guidance, logging only pre-classified safe context inside access-controlled diagnostics systems.

## 14. Avoiding confusing application arguments with Spring Boot internal configuration

When receiving `--key=value`, Spring Boot can also add command-line properties into `Environment` as a high-precedence config source, if the command-line property mechanism is enabled.

Example:

```bash
java -jar job.jar --spring.profiles.active=prod --mode=check
```

`spring.profiles.active` has meaning to Spring Boot, whereas `mode` is a business CLI option.

**Be mindful of the allowlist in the section 5 example.** `ALLOWED_OPTIONS` only contains `help`, `mode`, and `input`, because it is a **small CLI intentionally supporting only three options**. Thus it will reject `--spring.profiles.active=prod` if passed alongside them into `ApplicationArguments`.

In real applications needing both Boot flags and CLI flags, there are several options:

- Intentionally expand the allowlist for Bootstrap settings allowed via CLI.
- Provide Spring Boot configuration via files/environment or a separate configuration channel, not mixed into business CLI syntax.
- Use a dedicated command-line parser for complex commands, clearly defining which options belong to the framework and which belong to business logic.

**Do not assume every `spring.*` name is safe** just because it belongs to the framework namespace: some properties can alter runtime environment, logging, web server, or security behavior.

If the application is an HTTP-serving service, command-line validation design must align with deployment policy. For an isolated batch CLI, a strict allowlist as in the example is a sound choice.

## 15. Data types requiring stricter validation than plain strings

A CLI may also accept record counts, timeouts, dates, or booleans. Do not treat successful parsing alone as valid.

### 15.1. Bounded integers

```java
int batchSize;
try {
    batchSize = Integer.parseInt(rawBatchSize);
} catch (NumberFormatException ex) {
    throw new IllegalArgumentException(
            "--batch-size must be an integer.");
}

if (batchSize < 1 || batchSize > 1000) {
    throw new IllegalArgumentException(
            "--batch-size must be between 1 and 1000.");
}
```

This snippet expects `rawBatchSize` as a string retrieved from an option already checked for value count. Do not embed raw `rawBatchSize` in the error; if it contains sensitive data or newlines, logs remain safer.

### 15.2. Allowlisted mode enum

```java
Set<String> modes = Set.of("check", "import");

if (!modes.contains(mode)) {
    throw new IllegalArgumentException(
            "--mode must be check or import.");
}
```

`mode` here is already verified to be a non-blank string. The benefit of an allowlist is that only controlled values enter business logic and logs, rather than allowing arbitrary strings to drive state.

### 15.3. Duration

An input `--timeout=15s` must be parsed per published syntax and checked for min/max bounds—for instance, positive and not exceeding safety limits. You can use `Duration.parse("PT15S")` if adopting ISO-8601 syntax, or Spring Boot's unit-friendly parsing API when appropriate. **Do not silently accept arbitrary units from different parsers** if usage documents only one standard.

### 15.4. Boolean flags

A valueless `--dry-run` flag can be checked via `containsOption`. If published syntax is `--dry-run=true|false`, parse and validate the value rather than checking option presence alone. Mixing up the two styles easily causes `--dry-run=false` to be treated as enabled when code only calls `containsOption`.

### 15.5. Dates/times

For `--date=2026-11-09`, use `LocalDate.parse` and validate the business date range. Avoid `new Date(...)` with arbitrary strings or relying on default timezones when calculations depend on time instants. Data that Java parses successfully is not automatically valid under the CLI API contract.

## 16. Testing: matrix of cases to verify

Good tests separate the **parser/validator** from business logic so checks run quickly. Reference matrix:

| Command Line | Expected Result |
| --- | --- |
| `--help` | Prints usage to stdout, skips corresponding runner business logic |
| `--mode=check` | Valid, no input needed |
| `--mode=import --input=data.csv` | Valid parameters |
| No args | Reports missing `--mode` |
| `--mode` | Reports mode needs a value |
| `--mode=` | Reports empty mode value |
| `--mode=delete` | Reports mode not in allowlist |
| `--mode=check --mode=import` | Reports mode declared repeatedly |
| `--mode=import` | Reports missing `--input` |
| `--mode=check --input=data.csv` | Reports input invalid in check mode |
| `--mode=import --input=` | Reports empty input value |
| `--mdoe=check` | Reports unsupported option |
| `--mode=check extra.csv` | Reports positional argument |
| `--help --mode=check` | Reports help must stand alone |
| `--help=something` | Reports help takes no value |
| `--mode=check --api-token=SECRET` | Rejects unknown option; does not echo secret |

**Never use real secrets in tests.** The string `SECRET` in the last row is dummy data only. What must be verified is that output, exceptions, and logs contain no dummy payload labeled as sensitive.

### Unit testing without starting the entire context

Spring Boot provides `DefaultApplicationArguments` to build an instance from a string array:

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

ApplicationArguments args = new DefaultApplicationArguments(
        "--mode=import", "--input=data.csv");

System.out.println(args.getOptionValues("mode"));
System.out.println(args.getNonOptionArgs().size());
```

Output:

```text
[import]
0
```

This is a snippet placed in a method or JShell configured with a Spring Boot classpath; it is not plain Java runnable with `javac` without adding libraries.

When validation is extracted into a service accepting `ApplicationArguments`, you can test that service with `DefaultApplicationArguments` without starting the whole context.

### Testing that output contains no sensitive data

Approach:

1. Create a dummy secret with an easily recognizable string, e.g., `SENSITIVE_TEST_VALUE_123`.
2. Pass the dummy secret in an unsupported option or deliberately invalid input.
3. Capture stdout, stderr, and logging output within the test scope.
4. Assert **the dummy secret appears in no output channel**.
5. Assert error messages include usage guidance and appropriate failure status.

**Caution:** in-process tests do not cover external channels like shell history, process lists, and scheduler logs. To ensure deployment safety, audit the command-execution infrastructure too.

### Integration testing for ApplicationRunner

An `ApplicationRunner` bean is invoked by `SpringApplication` during startup. If you only construct an `ApplicationContext` using a bean-definition check tool, **do not assume** the runner will execute. Integration tests should use the proper `SpringApplication.run` bootstrap path or test the `run` method directly after decoupling dependencies.

Do not test by shutting down the cached context of an entire test suite just to observe an exit code, as that can disrupt other tests.

## 17. Common mistakes and troubleshooting

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `args.getOptionValues("mode").get(0)` throws NPE | Option `mode` did not appear | Check `null` before reading elements |
| Calling `get(0)` throws `IndexOutOfBoundsException` | User passed `--mode` without a value | Check size and value first |
| A repeated option is still accepted | Only reading first element, ignoring others | Require exactly one value for single-valued options |
| `--mode import` gives unexpected result | Parser treats `--mode` as a flag, `import` as positional | Use `--mode=import` and document syntax |
| Typo in option name yet job still runs | Option names list not checked | Enforce an allowlist of supported option names |
| `--help` prints fine yet other runners still run | `return` only exits the current runner | Use an orchestrator or dedicated entry-point design |
| `--help` does not show usage | Logic requires `mode` before checking `help` | Process valid help before mandatory options |
| Input error yet exit code stays 0 | Only printed to stderr and returned | Use a real error/exit-code mechanism |
| Logs contain `--password=...` | Logging `args`, `getSourceArgs`, or exception messages containing input | Never log raw args; use fixed error messages |
| Token masked in logs yet leaked via CI | Command containing secret echoed by scheduler | Do not pass secrets via CLI; change delivery mechanism |
| `--input` with newline breaks logs | Printing raw input verbatim | Do not echo, or encode/escape with bounds |
| Runner validation fails yet web server opened | Runner runs after context refresh | Validate config earlier / gate readiness |
| Path check passed yet reading still fails | Race condition, symlink, permissions, or deleted file | Check at file open time and handle exceptions safely |
| Valid mode yet code performs dangerous action | Validation checked syntax only, not authorization/business rules | Add authorization and policy checks before side effects |
| Passes locally yet behaves differently as JAR | Different args, environment, or working directory | Test exact command line, config sources, and packaging |
| Enabling debug exposes configuration | Overly verbose log levels/diagnostics without redaction | Limit logs and audit secret hygiene in runtime environments |

Quick diagnostic workflow:

1. Capture a **secret-sanitized command syntax**; never ask users to send raw tokens.
2. Determine whether each argument is an option, flag, or positional arg.
3. Check for absent, blank, repeated, or out-of-domain values.
4. Check validation order: help, allowlist, positional args, required options, cross-option relationships.
5. Check when validation runs: pre-refresh or post-refresh; what side effects happened earlier?
6. Verify error messages and exit codes against the CLI contract.
7. Inspect stdout, stderr, stack traces, application logs, and infrastructure logs for data leaks.
8. Test success, error, and dummy-secret cases before deployment.

## 18. Production readiness checklist

Before putting a Spring Boot CLI into CI/CD, cron, or batch systems, verify:

- [ ] Clear usage documentation, valid examples, and table of required/optional options.
- [ ] `ApplicationArguments` used where options and positional args must be distinguished.
- [ ] Unsupported option names checked and typos caught.
- [ ] Absent options, empty values, value counts, and repeated values checked.
- [ ] Allowlists/ranges enforced for modes, counts, and duration limits.
- [ ] Cross-option relationships validated, not just individual options in isolation.
- [ ] `--help` has clear semantics, output, and termination conditions.
- [ ] Input errors return failure status rather than merely printing logs.
- [ ] No business side effects occur prior to proper validation.
- [ ] `args`, `getSourceArgs`, secrets, and raw property sources are never logged.
- [ ] Raw input is never concatenated into exception messages.
- [ ] Credentials come from mechanisms safer than the command line.
- [ ] File paths are checked for permissions, file type, allowed directory, and symlink risks.
- [ ] Unusual inputs, repeated options, newlines, and dummy sensitive data are tested.
- [ ] Appropriate log retention, access control, and redaction policies exist.
- [ ] End-to-end tests verify exit codes and output in a real deployment environment.
- [ ] Runners do not block indefinitely, and async work is explicitly coordinated.
- [ ] `ApplicationReadyEvent`/true readiness is not confused with a runner merely spawning a thread.

## 19. Key takeaways

- **CLI input is untrusted input**, even when passed from `main`.
- **`ApplicationArguments`** classifies options, values, and non-option args. `getOptionValues` can be `null` or an empty list; handle both.
- **Good validation** covers syntax, value domains, cross-option relationships, and environment preconditions.
- **Good help/usage** gives valid run syntax and how to fix errors without printing unnecessary user data.
- **Never log all args**: secrets can leak through application logs, exceptions, shell history, process lists, CI/CD, or orchestration.
- **Do not put tokens on the command line when better protection exists**; prefer secret managers, workload identity, or properly access-controlled secret mechanisms.
- **`ApplicationRunner` executes after refresh.** It fits pre-business CLI checks, not replacing early config validation when beans/web servers must not start.
- **Exit codes must be designed and tested end-to-end.** Printing to stderr does not change the exit code automatically; returning on `--help` from one runner does not stop other runners.
- **Logged values must be explicitly allowlisted**, not merely raw input renamed.

### References

- [Spring Boot 3.3 — Using ApplicationRunner or CommandLineRunner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): runner timing in startup and application arguments.
- [Spring Boot 3.3 — ApplicationArguments API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html): `containsOption`, `getOptionValues`, `getNonOptionArgs`, and `getSourceArgs` methods.
- [Spring Boot 3.3 — DefaultApplicationArguments API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html): utility for constructing/testing arguments.
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): command-line property sources and external configuration.
- [Spring Boot 3.3 — Exit Codes](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): `ExitCodeGenerator` and exit code management.
- [Spring Framework — Binding and Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation): `@ConfigurationProperties` validation.
