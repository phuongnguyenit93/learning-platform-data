# ApplicationArguments, Option Arguments, and Non-Option Arguments

When running a Spring Boot application from a terminal, you can pass arguments to choose an execution mode, toggle a feature, specify input files, or adjust configuration without modifying source code. Spring Boot receives those arguments via **SpringApplication** and exposes the **ApplicationArguments** API so your application can read them in a structured way.

ApplicationArguments distinguishes two groups:

- **Option arguments**: arguments starting with two hyphens **--**, typically written as **--name=value**.
- **Non-option arguments**: arguments not starting with **--**, usually used for positional input values such as filenames or task codes.

Example:

~~~bash
java -jar app.jar --dry-run --format=csv input.csv --tag=urgent --tag=nightly
~~~

Spring Boot can read **dry-run**, **format**, and **tag** as options and **input.csv** as a non-option argument. This API is useful when building command-line tools with Spring Boot, running import/export jobs, executing administrative tasks, or controlling application startup modes.

## 1. How Do Arguments Enter SpringApplication?

A Spring Boot application typically starts at the `main` method:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

**args** is the `String` array passed by the JVM to `main`. When calling **SpringApplication.run(...)**, the application forwards that array to Spring Boot.

Running a JAR example:

~~~bash
java -jar demo.jar --app.mode=import --dry-run orders.csv
~~~

The strings after the JAR filename are passed into the application as command-line arguments. Spring Boot parses them and builds an **ApplicationArguments** object to supply to startup runners.

If you omit `args` when calling `SpringApplication.run`, Spring Boot cannot read those parameters through `ApplicationArguments`:

~~~java
public static void main(String[] args) {
    SpringApplication.run(DemoApplication.class);
}
~~~

In that case, the `args` array is not forwarded. Use the overload that accepts `args` whenever the application needs to process command-line arguments.

## 2. What Is ApplicationArguments?

**ApplicationArguments** is an interface in package:

~~~java
org.springframework.boot.ApplicationArguments
~~~

Spring Boot provides the default implementation **DefaultApplicationArguments**. This object represents the arguments passed to `SpringApplication.run(...)` and allows accessing both the raw data and the parsed argument groups.

Core APIs:

| Method | Meaning |
|---|---|
| **getSourceArgs()** | Returns the original raw argument array passed to SpringApplication. |
| **getOptionNames()** | Returns the set of recognized option names. |
| **containsOption(name)** | Checks whether a given option is present. |
| **getOptionValues(name)** | Returns the list of values associated with an option. |
| **getNonOptionArgs()** | Returns the list of non-option arguments. |

For example, given:

~~~text
--format=csv input.csv --dry-run
~~~

you can obtain:

- **getSourceArgs()**: the original strings in the order passed.
- **getOptionNames()**: option names such as `format`, `dry-run`.
- **containsOption("dry-run")**: `true`.
- **getOptionValues("format")**: a list containing `csv`.
- **getNonOptionArgs()**: a list containing `input.csv`.

`ApplicationArguments` only parses argument strings. It does not perform file imports, business validation, or automatic conversion of every value into arbitrary Java types.

## 3. What Is an Option Argument?

An **option argument** is an argument beginning with two hyphens **--**.

Examples:

~~~text
--profile=production
--server.port=8085
--app.mode=import
--dry-run
~~~

The option name is the portion following `--`. When an equals sign is present, the portion after `=` is the value:

~~~text
--app.mode=import
    └──────┘ └───┘
      name   value
~~~

Option names can contain dots or hyphens, so names like `server.port`, `app.mode`, and `dry-run` are all common.

### 3.1. Options with values: --name=value

This is the clearest syntax for passing a value:

~~~bash
java -jar app.jar --app.mode=import --batch.size=500
~~~

Spring Boot recognizes:

| Option name | Value |
|---|---|
| app.mode | import |
| batch.size | 500 |

Values are retrieved through `getOptionValues(...)` as `String` objects. If you need integers, booleans, enums, or domain types, convert them yourself or use Spring's property-binding mechanism.

### 3.2. Flag-style options: --name

An option can appear without a value:

~~~bash
java -jar app.jar --dry-run
~~~

In this case:

- **containsOption("dry-run")** returns `true`.
- The `dry-run` option is recognized as present.
- It has no regular text value such as `true` or `false`.

For flag-style options, check presence with `containsOption(...)` rather than assuming every option carries a non-null value.

Example:

~~~java
if (args.containsOption("dry-run")) {
    System.out.println("Dry-run mode, no data will be written");
}
~~~

If you want to pass an explicit boolean value to bind into configuration, use:

~~~text
--app.dry-run=true
~~~

The two forms mean different things at the parser level: `--dry-run` is an option with no value; `--app.dry-run=true` is an option named `app.dry-run` with string value `true`.

### 3.3. An option can appear multiple times

Spring Boot allows repeating the same option:

~~~bash
java -jar app.jar --tag=urgent --tag=nightly --tag=finance
~~~

`getOptionNames()` returns a set of option names, so `tag` appears once in the set. To retrieve all values, use:

~~~java
List<String> tags = args.getOptionValues("tag");
~~~

The result can be:

~~~text
["urgent", "nightly", "finance"]
~~~

This is useful for filters, environment lists, multiple configuration files, or tags that a caller wants to repeat.

### 3.4. Options with empty values

With:

~~~text
--app.label=
~~~

the `app.label` option is present and its value is an empty string. This differs from an option with no value:

~~~text
--app.label
~~~

Therefore, when handling options, distinguish:

- Option does not appear.
- Option appears without a value.
- Option appears with an empty value.
- Option appears with one or more actual values.

If a value is mandatory, validate it explicitly before executing the task.

## 4. What Is a Non-Option Argument?

A **non-option argument** is an argument that does not start with **--**.

Example:

~~~bash
java -jar app.jar orders.csv customers.csv
~~~

Both `orders.csv` and `customers.csv` are non-option arguments.

They are typically used for positional inputs:

- Input filenames.
- Subcommand names.
- Identifiers of items to process.
- Directory paths.
- Positional arguments to a command-line tool.

Retrieve the list with:

~~~java
List<String> inputFiles = args.getNonOptionArgs();
~~~

Example:

~~~java
@Component
public class FileImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        List<String> files = args.getNonOptionArgs();

        for (String file : files) {
            System.out.println("Input file: " + file);
        }
    }
}
~~~

Non-option arguments have no parser-assigned names. If you need to distinguish whether a string represents an input, output, or config path, the application must enforce positional ordering or adopt a structured command parser.

## 5. How Spring Boot Parses Options and Non-Options

Basic rules:

1. An argument starting with `--` is treated as an option.
2. With `--name=value`, the part before `=` is the name and the part after is the value.
3. With `--name` and no `=`, the option is recognized with no value.
4. An argument not starting with `--` goes into the non-option list.

Example:

~~~text
--dry-run --format=csv input.csv --tag=urgent
~~~

Parsed as:

| Input Token | Classification | Name | Value |
|---|---|---|---|
| --dry-run | Option | dry-run | No value |
| --format=csv | Option | format | csv |
| input.csv | Non-option | — | input.csv |
| --tag=urgent | Option | tag | urgent |

### 5.1. Do not assume --name value equals --name=value

This is a frequent pitfall when first using `ApplicationArguments`.

With Spring Boot's parser:

~~~text
--format=csv
~~~

is one option named `format` with value `csv`.

Whereas:

~~~text
--format csv
~~~

is parsed into:

- Option `format` with no value.
- Non-option argument `csv`.

The parser does not consume the next token as the value of an option lacking an equals sign. When writing commands for Spring Boot applications, always use `--name=value` to prevent misunderstandings.

If you must support `--name value` syntax, build a custom parser or adopt a dedicated command-line library and document the parsing rules clearly.

### 5.2. Short options like -p are not options under this rule

`ApplicationArguments` detects options by the `--` prefix. The string:

~~~text
-p
~~~

is not treated as an option under this syntax; it is a non-option argument. `ApplicationArguments` does not automatically provide short-option aliases like `-p` for `--port`.

If a CLI requires short options, mutually exclusive/required option groups, subcommands, help text, or rich type checking, consider a dedicated library such as picocli.

## 6. Reading ApplicationArguments in ApplicationRunner

**ApplicationRunner** is a convenient place to read `ApplicationArguments` after the Spring `ApplicationContext` has refreshed.

Example:

~~~java
package com.example.demo.startup;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (args.containsOption("dry-run")) {
            System.out.println("Dry-run mode enabled");
        }

        List<String> formats = args.getOptionValues("format");
        if (!formats.isEmpty()) {
            String format = formats.get(0);
            System.out.println("Format: " + format);
        }

        List<String> inputFiles = args.getNonOptionArgs();
        System.out.println("Input file count: " + inputFiles.size());
    }
}
~~~

Run:

~~~bash
java -jar app.jar --dry-run --format=csv orders.csv
~~~

The runner can:

- Check execution flags.
- Read valued options.
- Retrieve file lists or positional arguments.
- Validate inputs.
- Invoke services to perform the task.

### 6.1. Why use ApplicationRunner?

`ApplicationRunner` receives an `ApplicationArguments` instance directly, so your code does not have to split `--`, `=`, or repeated values manually.

Spring Boot calls runners after the `ApplicationContext` has refreshed and before publishing `ApplicationReadyEvent`. If a runner executes synchronous work, that work completes before the application reaches ready in the standard startup flow.

If a runner throws an unhandled exception, startup fails. This is desirable when input arguments are invalid or a mandatory task cannot succeed.

### 6.2. Multiple runners and execution order

An application can declare multiple `ApplicationRunner` beans. When a specific order is needed, use `@Order` or `Ordered`.

~~~java
@Component
@Order(10)
public class ValidateArgumentsRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Validate arguments.
    }
}
~~~

~~~java
@Component
@Order(20)
public class ExecuteImportRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Perform import after validation.
    }
}
~~~

Runners are ordered according to Spring's ordering mechanism. If two steps are tightly coupled, a single coordinating runner often makes the sequence easier to follow.

## 7. How Do ApplicationRunner and CommandLineRunner Differ?

Spring Boot offers two interfaces commonly used for startup tasks:

**ApplicationRunner**:

~~~java
@Component
public class AppRunner implements ApplicationRunner {
    @Override
    public void run(ApplicationArguments args) {
        // Read parsed options and non-options.
    }
}
~~~

**CommandLineRunner**:

~~~java
@Component
public class RawArgsRunner implements CommandLineRunner {
    @Override
    public void run(String... args) {
        // Receive the raw String array.
    }
}
~~~

Comparison:

| Criterion | ApplicationRunner | CommandLineRunner |
|---|---|---|
| Received parameter | ApplicationArguments | String... args |
| Option names | Has `getOptionNames()` API | Parse manually |
| Option values | Has `getOptionValues()` API | Parse manually |
| Non-option args | Has `getNonOptionArgs()` API | Parse manually |
| Raw args | Has `getSourceArgs()` | Received directly |
| Best suited for | Tasks reading structured options | Simple tasks needing raw strings |

When handling `--format=csv`, repeated options, or distinguishing options from positional arguments, `ApplicationRunner` is usually more convenient.

`CommandLineRunner` remains suitable when a program simply forwards the raw argument array to another API or applies its own parser.

## 8. Complete Example: File Import Program

Let's build a runner accepting:

~~~bash
java -jar importer.jar --format=csv --dry-run --tag=nightly --tag=finance orders.csv customers.csv
~~~

Conventions:

- `--format=csv`: file format.
- `--dry-run`: validate only without writing data.
- `--tag=...`: may appear multiple times.
- Non-option arguments are the list of input files.

### 8.1. Create the processing service

~~~java
package com.example.importer;

import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ImportService {

    public void importFiles(
            List<String> files,
            String format,
            List<String> tags,
            boolean dryRun) {

        System.out.println("Format: " + format);
        System.out.println("Tags: " + tags);
        System.out.println("Dry run: " + dryRun);

        for (String file : files) {
            System.out.println("Processing: " + file);
            if (!dryRun) {
                // Invoke actual read and write logic.
            }
        }
    }
}
~~~

### 8.2. Create the runner to read arguments

~~~java
package com.example.importer;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportApplicationRunner implements ApplicationRunner {

    private final ImportService importService;

    public ImportApplicationRunner(ImportService importService) {
        this.importService = importService;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> formats = args.getOptionValues("format");
        if (formats.isEmpty() || formats.get(0) == null
                || formats.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Must pass --format=csv or a supported format");
        }

        String format = formats.get(0);
        List<String> tags = args.getOptionValues("tag");
        List<String> files = args.getNonOptionArgs();
        boolean dryRun = args.containsOption("dry-run");

        if (files.isEmpty()) {
            throw new IllegalArgumentException(
                    "Must pass at least one input file");
        }

        if (formats.size() > 1) {
            throw new IllegalArgumentException(
                    "Only one --format may be passed");
        }

        importService.importFiles(files, format, tags, dryRun);
    }
}
~~~

This example validates that the `format` option has a non-blank value, collects repeated tags, checks that input files exist, and passes the parsed inputs to the service.

In a real CLI, validate further:

- Do the files exist and have read permissions?
- Is the format in the supported set?
- Are multiple files permitted?
- Is `--dry-run` allowed alongside other options?
- If one file fails, should the whole batch abort or continue to the next file?

Do not cram parsing, validation, and file processing into one oversized `run` method. The runner should act as the startup coordinator.

## 9. Argument Parsing Example Table

Suppose the command is:

~~~text
java -jar app.jar --mode=export --compress --format=json report.json --tag=daily --tag=finance
~~~

The values after `app.jar` passed into `SpringApplication` are:

~~~text
--mode=export
--compress
--format=json
report.json
--tag=daily
--tag=finance
~~~

Results:

| API | Result |
|---|---|
| getOptionNames() | mode, compress, format, tag |
| containsOption("compress") | true |
| getOptionValues("mode") | ["export"] |
| getOptionValues("format") | ["json"] |
| getOptionValues("tag") | ["daily", "finance"] |
| getNonOptionArgs() | ["report.json"] |

`getOptionNames()` returns a set of names, so it does not preserve how many times an option appeared. `getOptionValues("tag")` reveals all passed values.

`getSourceArgs()` preserves the original strings in input order. When logging or forwarding the full argument list, this API is cleaner than reconstructing it from option and non-option lists.

## 10. Option Arguments and the Spring Environment

Besides `ApplicationArguments`, Spring Boot by default also adds command-line option arguments into the **Environment** as a property source.

Example:

~~~bash
java -jar app.jar --server.port=8090 --demo.greeting.prefix=Hello
~~~

Valued properties can be read via:

~~~java
import org.springframework.core.env.Environment;

@Component
public class GreetingSettingsReader {
    private final Environment environment;

    public GreetingSettingsReader(Environment environment) {
        this.environment = environment;
    }

    public String prefix() {
        return environment.getProperty("demo.greeting.prefix");
    }
}
~~~

or bound via `@ConfigurationProperties`.

This gives two ways to access the same input:

- **ApplicationArguments**: reads options and non-options with command-line structure.
- **Environment**: reads options acting as Spring configuration properties.

### 10.1. When to use ApplicationArguments?

Use `ApplicationArguments` when arguments represent command invocations:

- Input filenames.
- `--dry-run`.
- `--format=csv`.
- Multiple `--tag=...`.
- Positional arguments requiring validation.

### 10.2. When to use Environment or @ConfigurationProperties?

Use `Environment` or `@ConfigurationProperties` when values are application configuration:

- `server.port`.
- `spring.profiles.active`.
- `demo.greeting.prefix`.
- `app.import.batch-size`.
- Timeouts, retries, endpoints, or feature flags.

Properties example:

~~~java
@ConfigurationProperties(prefix = "app.import")
public class ImportProperties {
    private int batchSize = 500;

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
~~~

When run:

~~~bash
java -jar app.jar --app.import.batch-size=1000
~~~

Spring Boot can bind `1000` into `batchSize`.

### 10.3. Disabling the command-line property source

`SpringApplication` allows disabling adding command-line arguments to the Environment:

~~~java
SpringApplication application =
        new SpringApplication(DemoApplication.class);
application.setAddCommandLineProperties(false);
application.run(args);
~~~

When disabled, command-line arguments are not added as a property source in the Environment. That does not erase the original argument array; `ApplicationArguments` remains the argument-parsing API created by Spring Boot from the passed arguments.

Only disable the command-line property source when you have a clear reason, as many applications rely on overriding configuration via `--property=value`.

### 10.4. Command-line options have high configuration precedence

When the command-line property source is enabled, values like:

~~~text
--server.port=8090
~~~

can override corresponding values in `application.yml` according to Spring Boot's property source precedence. This makes deploying the same artifact across environments convenient without editing config files.

Avoid passing sensitive secrets directly on the command line if the OS, process listings, shell history, or monitoring tools might record arguments. For secrets, use a secret management mechanism suited to your deployment environment.

## 11. Distinguishing JVM Arguments from Application Arguments

When running:

~~~bash
java -Dapp.region=ap-southeast-1 -jar app.jar --mode=import input.csv
~~~

there are two separate groups of arguments:

- **-Dapp.region=ap-southeast-1** appears before `-jar`, making it a JVM system property.
- **--mode=import** and **input.csv** appear after the JAR filename, making them arguments passed to the application's `main` method.

You can read the system property:

~~~java
String region = System.getProperty("app.region");
~~~

You can read the application option:

~~~java
args.getOptionValues("mode");
~~~

These are distinct sources. Placing `-D...` after the JAR filename prevents the JVM from treating it as a system property; instead, it becomes an application argument.

## 12. Validating and Converting Values

`ApplicationArguments` returns values as `String`. Applications must validate them before use.

Example reading a batch size:

~~~java
private int readBatchSize(ApplicationArguments args) {
    List<String> values = args.getOptionValues("batch-size");

    if (values.isEmpty() || values.get(0) == null) {
        return 500;
    }

    try {
        int size = Integer.parseInt(values.get(0));
        if (size <= 0) {
            throw new IllegalArgumentException(
                    "--batch-size must be greater than 0");
        }
        return size;
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException(
                "--batch-size must be an integer", ex);
    }
}
~~~

Command:

~~~bash
java -jar app.jar --batch-size=1000
~~~

passes the string `1000` to the application; your code parses it as `int` and enforces the valid range.

If a value is persistent configuration, using `@ConfigurationProperties` with typed fields and validation is usually cleaner than manually parsing every option inside a runner.

### 12.1. Handling required options

Example requiring `--source`:

~~~java
private String requireOption(ApplicationArguments args, String name) {
    List<String> values = args.getOptionValues(name);
    if (values.isEmpty() || values.get(0) == null
            || values.get(0).isBlank()) {
        throw new IllegalArgumentException(
                "Missing option --" + name + "=<value>");
    }
    if (values.size() > 1) {
        throw new IllegalArgumentException(
                "Option --" + name + " may only be passed once");
    }
    return values.get(0);
}
~~~

This helper verifies:

- Does the option exist?
- Does it have a value?
- Is the value non-blank?
- Was it passed only once?

For flag-style options, do not use this helper since flags take no value.

## 13. Testing ApplicationArguments

You can test the parser directly with **DefaultApplicationArguments** without booting the entire Spring Boot application.

JUnit 5 and AssertJ example:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

class ApplicationArgumentsTests {

    @Test
    void separatesOptionsAndNonOptions() {
        ApplicationArguments args = new DefaultApplicationArguments(
                "--dry-run",
                "--format=csv",
                "input.csv",
                "--tag=urgent",
                "--tag=nightly"
        );

        assertThat(args.containsOption("dry-run")).isTrue();
        assertThat(args.getOptionValues("format"))
                .containsExactly("csv");
        assertThat(args.getOptionValues("tag"))
                .containsExactly("urgent", "nightly");
        assertThat(args.getNonOptionArgs())
                .containsExactly("input.csv");
    }
}
~~~

This test verifies:

- Options without a value are still recognized.
- Options with a value are split into name and value.
- Repeated options preserve multiple values.
- Strings not starting with `--` land in the non-option list.

### 13.1. Testing --name value syntax

~~~java
@Test
void doesNotConsumeNextTokenAsOptionValue() {
    ApplicationArguments args = new DefaultApplicationArguments(
            "--format",
            "csv"
    );

    assertThat(args.containsOption("format")).isTrue();
    assertThat(args.getNonOptionArgs()).containsExactly("csv");
}
~~~

This test highlights that the parser does not treat the next token as the value of an option without an equals sign. If `format` needs a value, pass `--format=csv`.

### 13.2. Testing repeated options

~~~java
@Test
void collectsRepeatedOptionValues() {
    ApplicationArguments args = new DefaultApplicationArguments(
            "--tag=one",
            "--tag=two",
            "--tag=three"
    );

    assertThat(args.getOptionNames()).contains("tag");
    assertThat(args.getOptionValues("tag"))
            .containsExactly("one", "two", "three");
}
~~~

Do not check `getOptionNames()` alone when you need to verify the count or order of values for a repeated option.

### 13.3. Testing runners with a context

If you want to test runner logic alongside dependency injection, create a Spring test context and provide suitable `ApplicationArguments`/runner beans. For pure parsing tests, `DefaultApplicationArguments` is lighter and more focused.

In a full application, you can use `@SpringBootTest` to verify the runner is invoked with arguments passed when launching the test context. Be careful not to let tests perform real imports, write data, or call external services accidentally; use mock services or test configurations.

## 14. Limitations of ApplicationArguments

`ApplicationArguments` handles Spring Boot's lightweight argument parsing well, yet it is not a full-fledged CLI framework.

It does not provide out of the box:

- Short options like `-p`.
- Automatic `--name value` syntax.
- Strong typing for arbitrary options.
- Auto-generated help text and CLI documentation.
- Rejection of unsupported options against a declarative schema.
- Subcommands and complex option groups.
- Annotation-based default values and validation for positional arguments.
- Automatic mapping of positional arguments to named business parameters.

If an application has only a few options and input files, `ApplicationArguments` is usually plenty. When a CLI becomes a full product interface with numerous commands and syntax rules, consider a specialized tool.

## 15. When to Use picocli or a Dedicated CLI Library?

A large command-line tool may require:

- Subcommands such as `import`, `export`, `validate`.
- Both short and long options.
- Required options.
- Default values.
- Typed parameters and converters.
- File/path validation.
- Help and usage text.
- Shell completion.
- Consistent error messages.

Libraries like **picocli** offer a command/subcommand model and annotations for declaring CLIs. Spring Boot can integrate with picocli via its starter or appropriate configuration.

There is no need to pull a CLI library into every Spring Boot application. Start with `ApplicationArguments` when needs are modest; move to a dedicated parser when command-line rules grow complex and must be documented and tested as an API.

## 16. Common Mistakes

### 16.1. Forgetting to pass args to SpringApplication.run

**Symptom:** `getOptionNames()` is empty even though arguments were passed on the command line.

**Cause:** `main` did not forward the `args` array.

**Fix:**

~~~java
SpringApplication.run(DemoApplication.class, args);
~~~

### 16.2. Passing --format csv and expecting a value

**Symptom:** `getOptionValues("format")` has no value as expected and `csv` appears in the non-option list.

**Cause:** the parser splits options on `=`; the following token does not automatically become the value.

**Fix:** use `--format=csv`.

### 16.3. Calling getOptionValues without checking the list

**Symptom:** code accesses element zero and hits an index error or mishandles null.

**Cause:** the option may be absent or present without a value.

**Fix:** check for an empty list, null, and blank strings before using the value.

### 16.4. Reading only getOptionNames and losing repeated values

**Symptom:** you know `tag` appeared, but cannot retrieve all tags.

**Cause:** `getOptionNames()` returns a set of names, not every occurrence.

**Fix:** use `getOptionValues("tag")`.

### 16.5. Confusing non-option arguments with option values

**Symptom:** an input filename gets read as the value of `--format`.

**Cause:** the command omitted `=` and placed the value in the next token.

**Fix:** enforce `--name=value` syntax and inspect the non-option list separately.

### 16.6. Using ApplicationArguments for long-lived configuration

**Symptom:** multiple runners manually parse timeouts, batch sizes, endpoints, and retry counts.

**Cause:** mixing command parameters with application configuration.

**Fix:** use `Environment` or `@ConfigurationProperties` for typed configuration and defaults.

### 16.7. Confusing -D with application options

**Symptom:** system property is missing from `getOptionNames()` or `--mode` is missing from `System.getProperty`.

**Cause:** `-D...` before `-jar` is a JVM system property; `--...` after the JAR filename is an application argument.

**Fix:** read from the right source: `System.getProperty`, `Environment`, or `ApplicationArguments`.

### 16.8. Executing destructive tasks before validating arguments

**Symptom:** the application begins writing data before validating all arguments.

**Cause:** the runner mixes parsing, validation, and execution.

**Fix:** separate phases: parse → validate → call service. With `--dry-run`, verify the service genuinely writes nothing.

## 17. Common Misconceptions

**“Every argument after the JAR filename is an option.”**  
No. Strings starting with `--` are options; other strings are non-options under Spring Boot's parser.

**“--name value is equivalent to --name=value.”**  
No. The value token is classified as a non-option if the preceding option has no `=`.

**“-p is a short option equivalent to --port.”**  
No. `ApplicationArguments` does not automatically support short-option aliases.

**“An option without a value means false.”**  
No. `--dry-run` indicates the option is present with no text value. Check it with `containsOption`.

**“getOptionNames tells you how many times an option appeared.”**  
No. It returns a set of names; use `getOptionValues` to get repeated values.

**“ApplicationArguments automatically converts strings to int or boolean.”**  
No. Values are exposed as `String`; parse them yourself or use property binding.

**“CommandLineRunner and ApplicationRunner receive the same parameter type.”**  
No. `ApplicationRunner` receives `ApplicationArguments`; `CommandLineRunner` receives a `String` array.

**“Command-line arguments can only be read inside a runner.”**  
No. You can use `ApplicationArguments` in runners, and matching options can also be exposed in the `Environment` via the default command-line property source.

**“Disabling addCommandLineProperties removes data from ApplicationArguments.”**  
No. That setting disables adding the command-line property source to the Environment; it does not alter the argument array passed into `SpringApplication`.

**“ApplicationReadyEvent occurs before runners.”**  
No. `ApplicationRunner` and `CommandLineRunner` execute before `ApplicationReadyEvent` in the standard startup flow.

## Key Takeaways

**ApplicationArguments** is Spring Boot's API for reading arguments passed to `SpringApplication.run(...)`. Option arguments begin with **--**; explicit valued syntax is **--name=value**; flag-style options like **--dry-run** are checked with `containsOption`. Non-option arguments do not start with `--` and usually serve as positional parameters like filenames.

`getOptionNames()` returns the set of option names, `getOptionValues(name)` returns the associated values, `getNonOptionArgs()` returns positional arguments, and `getSourceArgs()` preserves the raw string array. **ApplicationRunner** is convenient when you want parsed arguments; **CommandLineRunner** receives raw strings. Use `ApplicationArguments` for command-line inputs, `Environment` or `@ConfigurationProperties` for application configuration, and explicitly handle missing values, empty values, and repeated options before executing work.
