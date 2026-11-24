# Reading Option Names, Presence, and Value Lists with ApplicationArguments — Spring Boot 3.3

## 1. Objectives

When running a Spring Boot application from the command line, we often pass arguments such as `--mode=import`, `--region=apac`, `--verbose`, or the name of a file to process. Spring Boot provides **`org.springframework.boot.ApplicationArguments`** to read those arguments in a structured way instead of manually splitting elements of `String[] args` in `main()`.

This lesson focuses on three main operations:

1. **Reading the list of option names** via `getOptionNames()`.
2. **Checking whether an option was passed** via `containsOption(name)`.
3. **Reading all values of an option** via `getOptionValues(name)`.

In particular, you will distinguish **absent option**, **option present without a value**, **empty value**, and **an option repeated multiple times**. These are the four error-prone cases in CLI applications.

The lesson uses **Java 21 + Spring Boot 3.3.13 + Maven**, with a runnable example, deterministic stdout, JUnit tests, and guidance for applying them in `ApplicationRunner`. No web server or database is required.

## 2. What kinds of application arguments exist?

Consider the command:

```bash
java -jar app.jar --mode=import --region=apac --region=eu --verbose orders.csv
```

Java passes `main(String[] args)` an array containing the following strings, in order:

```text
--mode=import
--region=apac
--region=eu
--verbose
orders.csv
```

Spring Boot distinguishes:

| Token | Classification | Meaning |
| --- | --- | --- |
| `--mode=import` | Option with value | Option `mode`, one value `import` |
| `--region=apac` | Option with value | Option `region`, first value |
| `--region=eu` | Repeated option name | `region` gains another value `eu` |
| `--verbose` | Option without value | Name `verbose` appears, no `=value` part |
| `orders.csv` | Non-option argument | Positional argument, does not start with `--` |

**Standard option syntax:** `--name` or `--name=value`. The name passed into `ApplicationArguments` is **`name`**, without the two leading dashes.

For example, spaces within a value must be passed by the shell as **one token**:

```bash
java -jar app.jar "--label=morning batch"
```

The value part is `morning batch`. Specific quoting rules depend on the operating system and shell; `ApplicationArguments` only processes the token array after the JVM has received it.

### 2.1. A single dash is not the same as two dashes

`-v` is not treated by Spring Boot's simple option parser as option name `v` under the `--name` syntax. It belongs to the non-option arguments group in this model.

Similarly, the command:

```bash
java -jar app.jar --mode import
```

does not have the same meaning as `--mode=import`: `--mode` is an **option with no attached value**, while `import` is a **non-option**. If you want to pass a value, use `=` inside the **same token**.

### 2.2. A comma does not mean multiple option values

```bash
java -jar app.jar --region=apac,eu
```

With the syntax above, `getOptionValues("region")` has **one element**, the string `apac,eu`, not two elements `apac` and `eu`.

If you want Spring to keep two separate values, repeat the option:

```bash
java -jar app.jar --region=apac --region=eu
```

If business logic requires splitting a CSV-like list, splitting on commas must be done intentionally by your code, including handling escaping/quoting appropriately.

## 3. What methods does ApplicationArguments provide?

The `org.springframework.boot.ApplicationArguments` interface provides the core operations:

| Method | Return Type | Explanation |
| --- | --- | --- |
| `getOptionNames()` | `Set<String>` | Set of **distinct names** of options that appeared |
| `containsOption(String name)` | `boolean` | Whether an option with this name appeared |
| `getOptionValues(String name)` | `List<String>` or `null` | Values of the option; **`null` when absent** |
| `getNonOptionArgs()` | `List<String>` | List of arguments not belonging to options |
| `getSourceArgs()` | `String[]` | Source argument array, unclassified, preserving token order |

Notes:

- `getOptionNames()` returns a **Set**, so a name repeated multiple times still appears **only once in the name set**.
- This Set **is not an API that guarantees alphabetical sorting**. If stable output is needed, use `new TreeSet<>(args.getOptionNames())`.
- `containsOption("mode")` takes the name string **without** the `--` prefix. `containsOption("--mode")` checks a **different name**, not what you want.
- Option names may contain dots such as `spring.profiles.active`; check with the exact passed name, e.g., `containsOption("spring.profiles.active")`.
- `getOptionValues` does not parse into `boolean`, `int`, `Duration`, or enums. Elements remain **strings**; the application is responsible for validation and type conversion.
- `getSourceArgs()` is useful for debugging and forwarding raw arguments, but should not be logged indiscriminately because command lines can contain sensitive information.

## 4. Four states to distinguish when reading values

This is the most important API contract of the lesson:

| Input | `containsOption("flag")` | `getOptionValues("flag")` | Meaning |
| --- | --- | --- | --- |
| Omit `flag` | `false` | `null` | Option does not exist |
| `--flag` | `true` | `[]` | Option exists but **has no value** |
| `--flag=` | `true` | `[""]` | Option exists, has **one empty-string value** |
| `--flag=yes` | `true` | `["yes"]` | Option has one value |
| `--flag=a --flag=b` | `true` | `["a", "b"]` | Option repeated with multiple values |

The three values **`null`**, **`[]`**, and **`[""]`** have different meanings.

### 4.1. Why is `values == null` not the same as `values.isEmpty()`?

Example:

```java
List<String> values = args.getOptionValues("flag");
if (values == null) {
    System.out.println("--flag was not passed");
}
else if (values.isEmpty()) {
    System.out.println("--flag is present without a value");
}
else {
    System.out.println("Has values: " + values);
}
```

This snippet is **an illustration inside `ApplicationRunner.run(...)`**, where variable `args` has type `ApplicationArguments`. Check order matters: calling `values.isEmpty()` **before** checking `null` can throw `NullPointerException`.

### 4.2. Why does `List.toString()` easily cause confusion with empty strings?

This is a Java display behavior, not a Spring Boot bug:

```java
System.out.println(List.of());   // []
System.out.println(List.of("")); // []
```

Both can print as `[]` because `List.toString()` does not add quotes around elements. Therefore, if you want to **distinguish an empty list from a list with one empty string in logs**, print each element with quotes or also print `values.size()`.

For example: `[]` has `size()==0`; `[""]` has `size()==1` and its first element is an empty string. The complete program in section 6 uses a dedicated formatting helper to print `['']` instead of relying only on `List.toString()`.

### 4.3. Repeating an option name does not create multiple names

With:

```text
--region=apac --region=eu --region=us
```

- `getOptionNames()` contains `"region"` **once**.
- `containsOption("region")` is `true`.
- `getOptionValues("region")` returns `["apac", "eu", "us"]` in the order values appeared in the arguments.
- There is no need to iterate `getSourceArgs()` manually to look for tokens starting with `--region=`.

**Note:** if the same name is passed multiple times and one occurrence is a valueless flag, the returned list contains only the **actually specified values**. `containsOption` confirms the name appeared; `getOptionValues` is not a list of every occurrence with `null` markers.

### 4.4. Distinguishing presence from "enabled"

`containsOption("trace") == true` only proves **the option is present**. If the command is:

```text
--trace=false
```

then `containsOption("trace")` is still `true`, while `getOptionValues("trace")` contains the string `"false"`. Thus, do not use `containsOption` alone to interpret a valued option as a boolean.

There are two common designs:

- **Presence-only switch:** by convention `--trace` means enable trace, accepting no `=true/false`; the application checks presence and **rejects** disallowed values.
- **Boolean-valued option:** by convention `--trace=true` or `--trace=false`; read exactly **one string**, validate `true`/`false`, then convert to Boolean.

Choosing which design to use is **the application's CLI contract**, not something `containsOption` decides on its own.

## 5. When is ApplicationArguments used in Spring Boot?

### 5.1. ApplicationRunner is a convenient entry point

Spring Boot invokes beans implementing `ApplicationRunner` after `ApplicationContext` is refreshed and before `ApplicationReadyEvent`. The method:

```java
void run(ApplicationArguments args) throws Exception;
```

receives the structured arguments object right at startup. `ApplicationRunner` fits CLI apps, data imports, app-managed migrations, one-shot run modes, and startup parameter validation.

`CommandLineRunner` also runs in this phase, but receives raw `String... args`:

```java
void run(String... args) throws Exception;
```

If you need `getOptionNames`, `containsOption`, and `getOptionValues`, prefer `ApplicationRunner` over writing your own parser on `String[]`.

### 5.2. Injecting ApplicationArguments into beans

Spring Boot also provides `ApplicationArguments` as an injectable object within the `SpringApplication` context. Illustrative example:

```java
@Component
public class ImportOptions {
    private final ApplicationArguments arguments;

    public ImportOptions(ApplicationArguments arguments) {
        this.arguments = arguments;
    }

    public boolean isDryRun() {
        return arguments.containsOption("dry-run");
    }
}
```

This is a **supplementary pattern**, requiring imports for `@Component` and `ApplicationArguments`. It is not a standalone Java program. The advantage is that services reading options do not need `static` variables or global `String[]` passing. However, do not assume passing args to `SpringApplication` automatically turns all of their contents into type-checked configuration.

### 5.3. How does it differ from Environment and @ConfigurationProperties?

`ApplicationArguments` provides a view of **the exact set of tokens received by that `SpringApplication.run` call**. `Environment` is Spring Boot's property source system, which can combine command-line properties with `application.yaml`, environment variables, JVM system properties, and other configuration sources. `@ConfigurationProperties` binds properties into typed objects and supports validation.

Therefore:

- To know **whether the operator actually passed `--dry-run`**: `containsOption("dry-run")`.
- To read **every `--region=...` passed**: `getOptionValues("region")`.
- For configuration with defaults, multi-source overrides, and type validation: `@ConfigurationProperties`.
- To drive a pure CLI mode from a few arguments: `ApplicationRunner` + `ApplicationArguments` is very clear.

Do not confuse "the option value was not passed" with "the application has no corresponding property": a property can still come from `application.yaml` or another source.

### 5.4. JVM options differ from application options

Example:

```bash
java -Dapp.mode=demo -jar app.jar --mode=import
```

`-Dapp.mode=demo` is a **JVM system property**, not an element in the application's `String[] args` array. `--mode=import` after `-jar app.jar` is the **application argument** that `ApplicationArguments` will parse.

Dash placement and token position on the command line matter greatly. Avoid confusing JVM `-D` with application `--name=value`.

## 6. Complete Maven example: printing names, presence, and values

We build a **non-web** Spring Boot app solely to inspect arguments. The example uses no database or REST controller and has deterministic output for the lines it explicitly prints.

### 6.1. Project structure

```text
cli-arguments-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/args/
    │   └── CliArgumentsApplication.java
    └── test/java/com/example/args/
        └── ApplicationArgumentsContractTest.java
```

### 6.2. pom.xml

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>cli-arguments-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` suffices for creating a console app, while `spring-boot-starter-test` provides JUnit Jupiter in test scope. The example selects Java 21; Spring Boot 3.3 supports Java 17 and above.

### 6.3. Application code

File `src/main/java/com/example/args/CliArgumentsApplication.java`:

```java
package com.example.args;

import java.util.Arrays;
import java.util.List;
import java.util.TreeSet;
import java.util.stream.Collectors;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CliArgumentsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CliArgumentsApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }

    @Bean
    ApplicationRunner showArguments() {
        return args -> {
            System.out.println("option names: "
                    + new TreeSet<>(args.getOptionNames()));

            show(args, "region");
            show(args, "trace");
            show(args, "blank");
            show(args, "missing");
            show(args, "mode");

            System.out.println("non-options: " + args.getNonOptionArgs());
            System.out.println("raw: " + Arrays.toString(args.getSourceArgs()));
        };
    }

    private static void show(ApplicationArguments args, String name) {
        List<String> values = args.getOptionValues(name);

        System.out.println(name
                + ": present=" + args.containsOption(name)
                + ", values=" + describe(values));
    }

    private static String describe(List<String> values) {
        if (values == null) {
            return "<absent>";
        }

        return values.stream()
                .map(value -> "'" + value + "'")
                .collect(Collectors.joining(", ", "[", "]"));
    }
}
```

**Why is the code written this way?**

- `ApplicationRunner` lets Boot inject `ApplicationArguments` directly into the `run` callback.
- `new TreeSet<>(args.getOptionNames())` ensures **names are printed alphabetically**, avoiding tests depending on unguaranteed `Set` iteration order.
- `show(...)` prints both `containsOption` and the values to distinguish absent vs. present.
- `describe(null)` returns `<absent>`; `describe(List.of())` returns `[]`; `describe(List.of(""))` returns `['']`.
- The `describe` helper is only for illustration with values that contain no single quotes. For general logging, use a serializer with escaping or print explicit lengths/sizes; do not log secrets.
- `WebApplicationType.NONE` avoids starting an HTTP server; the app focuses on CLI operations.

### 6.4. Build and run

From the `cli-arguments-demo` directory, requiring JDK 21, Maven, and downloadable dependencies:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/cli-arguments-demo-0.0.1-SNAPSHOT.jar --region=apac --region=eu --trace --blank= --mode=sync reports.csv
```

Lines **explicitly printed by the program** in order:

```text
option names: [blank, mode, region, trace]
region: present=true, values=['apac', 'eu']
trace: present=true, values=[]
blank: present=true, values=['']
missing: present=false, values=<absent>
mode: present=true, values=['sync']
non-options: [reports.csv]
raw: [--region=apac, --region=eu, --trace, --blank=, --mode=sync, reports.csv]
```

Spring Boot may also print a banner and logs depending on configuration; the block above **is not all of stdout**. The values match because `region` appeared twice, `trace` had no `=...`, `blank` had one empty value, `missing` did not appear, and `reports.csv` is a non-option.

### 6.5. Trying a different option-passing style

Try:

```bash
java -jar target/cli-arguments-demo-0.0.1-SNAPSHOT.jar --mode run.csv
```

The notable lines will be:

```text
option names: [mode]
region: present=false, values=<absent>
trace: present=false, values=<absent>
blank: present=false, values=<absent>
missing: present=false, values=<absent>
mode: present=true, values=[]
non-options: [run.csv]
raw: [--mode, run.csv]
```

This proves `--mode run.csv` does **not** make `run.csv` the value of `mode`: you must use `--mode=run.csv` if you want it as the option's value.

### 6.6. Example with a comma-containing value

Try:

```bash
java -jar target/cli-arguments-demo-0.0.1-SNAPSHOT.jar --region=apac,eu
```

Then the `region` line is:

```text
region: present=true, values=['apac,eu']
```

There is no automatic splitting on commas; it is a single string value.

## 7. Unit tests for null, empty, empty-string, and multi-value contracts

Although the demo above is a full Boot application, you can test the argument-parsing logic separately **without running the whole context** using `DefaultApplicationArguments`.

File `src/test/java/com/example/args/ApplicationArgumentsContractTest.java`:

```java
package com.example.args;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ApplicationArgumentsContractTest {

    @Test
    void readsOptionNamesExistenceAndValues() {
        ApplicationArguments args = new DefaultApplicationArguments(
                "--region=apac",
                "--region=eu",
                "--trace",
                "--blank=",
                "reports.csv");

        assertEquals(Set.of("region", "trace", "blank"),
                args.getOptionNames());

        assertTrue(args.containsOption("region"));
        assertTrue(args.containsOption("trace"));
        assertFalse(args.containsOption("missing"));

        assertEquals(List.of("apac", "eu"),
                args.getOptionValues("region"));
        assertEquals(List.of(),
                args.getOptionValues("trace"));
        assertEquals(List.of(""),
                args.getOptionValues("blank"));
        assertNull(args.getOptionValues("missing"));

        assertEquals(List.of("reports.csv"), args.getNonOptionArgs());
        assertArrayEquals(new String[] {
                "--region=apac", "--region=eu",
                "--trace", "--blank=", "reports.csv"
        }, args.getSourceArgs());
    }

    @Test
    void separateTokenIsNotAnOptionValue() {
        ApplicationArguments args =
                new DefaultApplicationArguments("--mode", "import");

        assertTrue(args.containsOption("mode"));
        assertEquals(List.of(), args.getOptionValues("mode"));
        assertEquals(List.of("import"), args.getNonOptionArgs());
    }

    @Test
    void commaSeparatedInputIsSingleValue() {
        ApplicationArguments args =
                new DefaultApplicationArguments("--region=apac,eu");

        assertEquals(List.of("apac,eu"), args.getOptionValues("region"));
    }
}
```

Run:

```bash
mvn test
```

Maven is expected to report **3 tests, 0 failures, 0 errors** (alongside Maven plugin output). This is a unit test for `ApplicationArguments` on the Spring Boot classpath; `@SpringBootTest` is not needed because we are not testing dependency injection or `ApplicationContext` here.

**Benefit of these tests:** they directly verify the API behavior, avoiding conclusions based on `List.toString()`, which easily confuses `[]` with `[""]`.

## 8. Reading options safely in production code

### 8.1. Required option with exactly one value

Suppose the program requires `--mode=import` and disallows blank or repeated values:

```java
static String requireSingleNonBlank(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);

    if (values == null) {
        throw new IllegalArgumentException(
                "Missing option --" + name + "=...");
    }
    if (values.size() != 1 || values.get(0).isBlank()) {
        throw new IllegalArgumentException(
                "Option --" + name + " must have exactly one non-blank value");
    }
    return values.get(0);
}
```

This is a **helper method added to a Java class that imports `ApplicationArguments` and `List`**; it does not run standalone. It rejects:

- Option not passed: `values == null`.
- Only `--mode` passed: empty list.
- `--mode=` passed: list with one empty string.
- Repeated `--mode=a --mode=b`: list longer than one.
- Whitespace passed when non-blank is required: `String.isBlank()` catches whitespace-only values.

If `mode` has a finite set of values, validate further with `switch` or an enum rather than accepting an arbitrary string.

### 8.2. Presence-only option

Suppose `--dry-run` is only an enable flag:

```java
static boolean dryRunEnabled(ApplicationArguments args) {
    if (!args.containsOption("dry-run")) {
        return false;
    }
    List<String> values = args.getOptionValues("dry-run");
    if (values != null && !values.isEmpty()) {
        throw new IllegalArgumentException(
                "--dry-run does not accept a value; use --dry-run only");
    }
    return true;
}
```

This is an **illustrative method**. `--dry-run=false` does not mean "not dry-run"; it is input that violates the presence-only contract, so the example explicitly rejects it. This avoids accidentally enabling a feature by checking only the name.

### 8.3. True boolean option

If the CLI allows `--audit=true` or `--audit=false`, validate explicitly:

```java
static boolean readBoolean(ApplicationArguments args, String name) {
    String value = requireSingleNonBlank(args, name);
    if ("true".equalsIgnoreCase(value)) {
        return true;
    }
    if ("false".equalsIgnoreCase(value)) {
        return false;
    }
    throw new IllegalArgumentException(
            "--" + name + " only accepts true or false");
}
```

**This snippet uses the `requireSingleNonBlank` method above.** It does not silently treat arbitrary strings as false like `Boolean.parseBoolean` (which returns `false` for many strings other than `"true"`).

### 8.4. Repeated options and multi-element data

```java
List<String> regions = args.getOptionValues("region");
if (regions == null || regions.isEmpty()) {
    throw new IllegalArgumentException(
            "At least one --region=value is required");
}

for (String region : regions) {
    if (region.isBlank()) {
        throw new IllegalArgumentException("Region code must not be blank");
    }
    // Use region in order of appearance if the application requires it.
}
```

This is an **illustrative snippet inside a runner**, where `args` of type `ApplicationArguments` is available. If `region` must belong to an allowed list, validate it instead of passing untrusted strings into queries or file paths.

### 8.5. When should you not parse `ApplicationArguments` manually?

For application configuration with many defaults, profiles, `.yaml` files, environment variables, and type conversion, `@ConfigurationProperties` with Bean Validation is easier to maintain. `ApplicationArguments` is particularly suited for:

- One-shot CLI modes.
- Repeated options with the same name where the value list must be preserved.
- Needing to know accurately whether an option was passed via the command line.
- Working with non-option positional arguments.
- Deciding startup workflow in `ApplicationRunner`.

Do not stuff all long-lived configuration into `ApplicationRunner` when it actually belongs in Boot's configuration model.

## 9. Option names, data types, ordering, and encoding

### 9.1. Option names are keys, not `--key` strings

Correct:

```java
args.containsOption("mode");
args.getOptionValues("mode");
```

Semantically wrong:

```java
args.containsOption("--mode");
args.getOptionValues("--mode");
```

The wrong calls do not find the option named `"mode"`; the API does not strip `--` from the name passed to these methods.

### 9.2. Option names are not raw CLI order

Suppose:

```text
--region=apac --mode=import --region=eu
```

`getOptionNames()` is the set `{region, mode}`, not the token stream `[region, mode, region]`. If you want the order of **all raw tokens**, use `getSourceArgs()`. If you want the list of **values for `region` alone**, use `getOptionValues("region")`.

To print names in a readable order, wrap in `TreeSet`; do not rely on `Set` iteration order.

### 9.3. Arguments containing spaces

Shells can handle quoting differently across PowerShell, cmd, Bash, and zsh. Spring Boot does not receive an unsplit command-line string; it receives a `String[]`. So to include spaces in a value, quote it so the shell passes it as a single element:

```bash
java -jar app.jar "--output-dir=monthly reports"
```

In Java, the value is `monthly reports` without outer quotes. To verify in practice, you can print `Arrays.toString(args.getSourceArgs())` **only in test environments free of secrets**.

### 9.4. Multiple values do not mean configuration is validated

`--region=apac --region=unknown` is syntactically valid, yet `unknown` may be invalid in business logic. `ApplicationArguments` does **not** distinguish supported regions, valid integers, existing files, quotas, or permissions for you.

Separate **parsing** (Boot API) from **validation** (application rules), and only then execute the action.

## 10. Common errors and troubleshooting

| Error or symptom | Cause | How to fix |
| --- | --- | --- |
| `NullPointerException` on `getOptionValues(...).isEmpty()` | Option was not passed; API returns `null` | Check `null` first or call `containsOption` |
| `containsOption("--debug")` returns `false` | Passed name includes `--` | Use `containsOption("debug")` |
| `--mode import` is not read as `mode=import` | Parser treats `--mode` as a flag and `import` as a non-option | Use `--mode=import` |
| `--trace=false` is still treated as "trace enabled" | `containsOption` checks presence, not Boolean parsing | Use a presence-only convention or validate boolean values |
| `--blank=` and `--blank` print identically with `List.toString()` | A list containing `""` and an empty list both easily display as `[]` | Check `size()`, print with quotes, or use explicit serialization |
| `--region=apac,eu` has only one element | Parser does not auto-split on commas | Repeat `--region=...` or parse CSV intentionally |
| Option names print in different order across runs | `Set` does not guarantee alphabetical order | Use `TreeSet` for presentation |
| `-v` is not picked up by `containsOption("v")` | Does not follow `--name` syntax | Use `--verbose` or implement a parser supporting short options |
| JVM `-Dmode=x` is absent from `getOptionNames()` | It is a system property, not an app arg | Access via `Environment`, without mixing the two types |
| Value-reading code rejects multiple occurrences | Multiple `--name=value` args make the list longer than one | State single/multi-value rules clearly and validate |
| Passing secrets via options, then logging raw args | Secrets easily leak in logs or process inspection | Prefer env vars or secret stores; do not log secrets |
| Runner executes before beans are ready? | Lifecycle misunderstanding | `ApplicationRunner` runs after context refresh |
| Using `getOptionValues` expecting YAML defaults | API only reads args passed to `SpringApplication` | Use `Environment` or `@ConfigurationProperties` to merge config |

### 10.1. Step-by-step debugging

1. Check that the Java command places `--option` **after** the JAR/main class name.
2. Check that each token follows `--name=value` syntax.
3. Check that the name passed to `containsOption` or `getOptionValues` has **no** `--`.
4. Print the **sorted list of names** and non-options, only when test data is safe.
5. Distinguish `null`, `[]`, `[""]`, and `["a", "b"]`.
6. Check type validation logic and required constraints.
7. If expected behavior involves `application.yaml` or env variables, check whether you are confusing the CLI API with property binding.

### 10.2. When startup fails due to arguments

If an `ApplicationRunner` throws `IllegalArgumentException` due to a missing required option, Spring Boot may treat it as a **startup failure** and not complete the normal ready flow. For CLI apps, print a clear message showing usage syntax; for long-running services, consider whether that option should really abort startup.

`ApplicationReadyEvent` only fires after runners return successfully. Do not perform critical work in a runner before verifying required options are valid and having a clear error-handling policy.

## 11. Real-world scenarios

### 11.1. Region-based data import CLI

Requirement:

```bash
java -jar importer.jar --region=apac --region=eu --mode=incremental files.csv
```

Solution:

- `containsOption("mode")` or `requireSingleNonBlank(args, "mode")` to validate the required mode.
- `getOptionValues("region")` retrieves **two values** instead of raw string parsing.
- `getNonOptionArgs()` retrieves `files.csv`; validate that there is exactly one filename if business rules require it.
- Verify `region` is in the supported set and the file path stays within allowed bounds.

### 11.2. Safe dry-run

Requirement:

```bash
java -jar importer.jar --dry-run input.csv
```

Design `--dry-run` as **presence-only**; use `containsOption("dry-run")`, and reject `--dry-run=false` if it is not part of the CLI contract. When the flag is set, never perform actual write steps.

### 11.3. Operator passing multiple endpoints

Requirement:

```bash
java -jar worker.jar --endpoint=https://a.example --endpoint=https://b.example
```

`getOptionValues("endpoint")` holds two URL strings. The application must validate scheme, host, connectivity permissions, and timeouts. Just because the parser returns two strings does not mean the endpoints are safe or ready.

### 11.4. Import mode via property sources

If the application has a default `app.import.mode` in YAML and the deployment environment also has an env variable override, use `@ConfigurationProperties` to receive the value resolved by Spring precedence. `ApplicationArguments.containsOption("app.import.mode")` only returns `true` if that name **actually appeared in a CLI token**; it cannot replace resolving property sources.

## 12. Exercises and self-check questions

1. With `--foo=bar --debug`, what does `getOptionNames()` contain? What is `getOptionValues("debug")`?
2. Why is `getOptionValues("missing") == null` different from `getOptionValues("debug").isEmpty()`?
3. With `--blank=`, how many elements are in the list? Why is `List.toString()` not enough to prove it?
4. With `--region=apac --region=eu`, how many times does `"region"` appear in `getOptionNames()` and how many elements are in `getOptionValues()`?
5. Why is `--mode import` not equivalent to `--mode=import`?
6. If only `--trace=false` is passed, what does `containsOption("trace")` return? Write an appropriate Boolean validation rule.
7. What makes `new TreeSet<>(args.getOptionNames())` suitable when writing log assertions?
8. Modify the demo yourself to require exactly one option `--mode=sync` or `--mode=async`, rejecting missing, blank, and repeated values.
9. Check `getNonOptionArgs()` when also passing `reports.csv` and `2026-11.csv`.
10. Write a JUnit test for `--flag`, `--flag=`, `--flag=yes`, and the absent option case.
11. Use `new DefaultApplicationArguments("--mode=export", "--mode=import")` and explain why you should not just call `get(0)` if the app requires a single mode.
12. Why is `ApplicationRunner` more convenient than `CommandLineRunner` for reading option names and value lists?
13. When should you use `@ConfigurationProperties` instead of reading `ApplicationArguments` directly?
14. Write an actionable error message when the user passes `--region=` or `--region` while the app requires a non-empty region code.
15. Why should you not print all `getSourceArgs()` values in production logs?
16. Write a test to distinguish `--region=apac,eu` from `--region=apac --region=eu` without relying on list formatting.
17. Review `java -Dapp.mode=demo -jar app.jar --mode=import`: which token is handled by the JVM, and which belongs to application arguments?
18. For a new CLI syntax requiring short options, positional groups, and complex subcommands, why might you need a dedicated CLI parser library instead of overusing `ApplicationArguments`?

**Completion criteria:** be able to write code using `getOptionNames`, `containsOption`, and `getOptionValues` accurately, check the three states **null / empty list / list containing an empty string**, retrieve multiple values when repeating `--name=value`, explain program output accurately, and know when to switch to typed configuration.

## 13. Official references

- Spring Boot 3.3 — `ApplicationArguments` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — `DefaultApplicationArguments` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- Spring Boot 3.3 — SpringApplication, runners, and command-line access: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Framework 6.1 — `SimpleCommandLinePropertySource` and option syntax: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html
- Spring Boot 3.3 — Externalized Configuration: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
