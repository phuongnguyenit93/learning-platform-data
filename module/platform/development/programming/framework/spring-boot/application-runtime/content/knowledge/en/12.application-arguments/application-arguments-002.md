# Distinguishing Option Arguments from Non-Option Arguments in Spring Boot

## Learning Objectives

When calling `SpringApplication.run(args)`, the application receives a list of command-line arguments. Spring Boot lets you read two different groups: **option arguments** (named option arguments) and **non-option arguments** (unnamed arguments, often also called *positional arguments*). Distinguishing the two groups properly helps you build CLIs/batch jobs, validate input parameters, route tasks, and avoid configuration errors.

After this lesson, you will be able to:

1. Recognize Spring Boot option syntax `--name` and `--name=value` versus elements without the `--` prefix.
2. Use `ApplicationArguments` to read `getOptionNames()`, `containsOption()`, `getOptionValues()`, `getNonOptionArgs()`, and `getSourceArgs()`.
3. Distinguish **an absent option**, **a valueless option flag**, and **an option whose value is an empty string**.
4. Explain why `--mode=import` differs from `--mode import`, and why `-v` is not the `--v` option in the default parser.
5. Understand the relationship between `ApplicationArguments`, `CommandLineRunner`, `ApplicationRunner`, and `Environment`.
6. Run a **Java 17+ / Spring Boot 3.3.13 / Gradle** example illustrating both structured reading and raw arguments, with clear output.
7. Design safe validation for positional arguments, boolean flags, file paths, integers, and inputs that may contain sensitive information.

**Context:** Spring Boot Application Runtime → Application Arguments. This lesson focuses on **classifying command-line arguments** and how applications use the two argument groups; it does not replace a full guide on Spring Boot configuration binding or dedicated CLI libraries.

## 1. Where do the two argument groups differ?

Suppose a user runs an import program:

~~~bash
java -jar app.jar --mode=import --dry-run customers.csv archive.csv
~~~

Here:

- `--mode=import` is an **option named** `mode` with value `import`.
- `--dry-run` is an **option named** `dry-run` without an accompanying value (a *flag*).
- `customers.csv` and `archive.csv` are two **non-option arguments**, with no key/name; the program can define them by convention as the input file and output file respectively.
- `java`, `-jar`, and `app.jar` belong to the JVM invocation syntax, **not** three elements that `ApplicationArguments` receives when the application runs from a JAR.

From the perspective of `main(String[] args)`, the four elements entering the array are:

~~~text
[--mode=import, --dry-run, customers.csv, archive.csv]
~~~

Spring Boot classifies those exact elements; it does not "read the literal shell command" and does not automatically know that `customers.csv` is a valid file. The meaning of the first/second file is defined by the **application**.

### Comparison Table

| Criterion | Option argument | Non-option argument |
| --- | --- | --- |
| Syntax in default parser | `--name` or `--name=value` | Without `--name` option prefix |
| Examples | `--mode=import`, `--dry-run` | `customers.csv`, `archive.csv`, `-v` |
| Has a name for lookup? | Yes: `mode` or `dry-run` | No: typically uses list position |
| Primary read API | `containsOption("mode")`, `getOptionValues("mode")` | `getNonOptionArgs()` |
| Preserves order? | Name list is a `Set`; do not use it to infer original order | Positional list preserves order after parser processing |
| Can have multiple items? | Multiple option names; repeating same name depends on parser/version | Multiple positional arguments |
| Auto-converted to Java types? | No: values must be parsed/validated | No: each element must be parsed/validated |
| Can affect Spring Environment? | By default, command-line options are added to `Environment` | Do not automatically become named properties under the same rule |

**Important:** "Option" here is the name of the **syntax** category (*option*), not a statement that the parameter is permitted to be missing in business logic. An application may require `--mode=...` even though its syntax is an *option argument*.

## 2. Spring Boot option syntax

Spring Boot uses Spring Framework's simple command-line argument parsing mechanism. For the versions within the scope of this lesson, the standard option form is:

~~~text
--optionName[=optionValue]
~~~

Square brackets in the notation only express the **optional part**, not characters to type in the terminal.

Common forms:

| Input | Classification | Meaning |
| --- | --- | --- |
| `--debug` | Option named `debug` | Named, without a value |
| `--mode=import` | Option named `mode` | One value `import` |
| `--port=8080` | Option named `port` | One string value `8080`, not automatically an `int` |
| `--empty=` | Option named `empty` | One zero-length value (empty string) |
| `--name=Lan` | Option named `name` | One value `Lan` |
| `--name="Lan Anh"` | Option (if shell passes as one token) | One value with space `Lan Anh` |
| `input.csv` | Non-option | A positional element |
| `-v` | Non-option in this default parser | Not interpreted as short option for `--verbose` |
| `2026` | Non-option | String `2026`, can be parsed as year |
| `-12` | Non-option | String `-12`, needs parsing if used as negative number |

### Option names have no prefix when calling the API

Even though the raw token has `--`, query code uses only the **name**:

~~~java
boolean hasDebug = args.containsOption("debug");
List<String> modes = args.getOptionValues("mode");
~~~

Do not pass `containsOption("--debug")` or `getOptionValues("--mode")` to look up tokens written with the prefix. The API already strips `--` from the option name during classification.

### Equals sign is the name/value boundary

`--mode=import` is **one element of the `String[]` array**. The parser splits at the first `=` after the name. If the value contains an equals sign, such as `--token=a=b`, the value part is `a=b`.

Conversely, two tokens:

~~~text
--mode import
~~~

are not read by the default parser as a key/value pair without an equals sign. The grouping result is:

- `--mode`: a present option **with no directly attached value**.
- `import`: a non-option argument.

This is one of the most common mistakes when migrating from another CLI library to `ApplicationArguments`.

### Single dash differs from double dash

In other CLI frameworks, `-v` is often shorthand for `--verbose`. However, the default parser of `ApplicationArguments` focuses on the `--` prefix; a `-v` token can still appear in `getNonOptionArgs()`. **Do not implicitly apply short-option rules** from GNU getopt, picocli, or Apache Commons CLI.

If you want to support `-v` as an actual option, the application must implement its own rules or use a suitable CLI parser.

## 3. ApplicationArguments: interface for reading both argument groups

Spring Boot provides `org.springframework.boot.ApplicationArguments`, built from the arguments passed to `SpringApplication.run(...)` and injectable into a bean/runner.

Methods:

| Method | Return Type | Meaning |
| --- | --- | --- |
| `getSourceArgs()` | `String[]` | Raw token array, unclassified |
| `getOptionNames()` | `Set<String>` | Names of recognized options |
| `containsOption(String name)` | `boolean` | Whether an option with this name exists |
| `getOptionValues(String name)` | `List<String>` or `null` | Values associated with the option name |
| `getNonOptionArgs()` | `List<String>` | Positional/non-option list after parsing |

Example of a runner:

~~~java
@Component
public class InputReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(args.getOptionNames());
        System.out.println(args.getNonOptionArgs());
    }
}
~~~

This is an **illustrative snippet**; it requires imports for `ApplicationRunner`, `ApplicationArguments`, `Component`, and a Spring Boot project. `ApplicationRunner` is a bean callback invoked by Boot after context refresh and before `ApplicationReadyEvent`. A complete project will be shown in section 7.

### Why do we need both getSourceArgs and getNonOptionArgs?

Suppose the source args are in this order:

~~~text
[input.csv, --mode=import, output.csv, --dry-run]
~~~

`getSourceArgs()` preserves all four tokens in their original order, while `getNonOptionArgs()` contains only:

~~~text
[input.csv, output.csv]
~~~

If you want the two file positions, use `getNonOptionArgs()` and validate the element count. If you want to log **all tokens** for diagnostics, `getSourceArgs()` is useful, though secrets must be filtered before logging.

A program must not assume "the third element of raw args is always the output file" because option positions can shift and skew indices. After parsing, the positional list is much clearer.

## 4. Three states of getOptionValues that are easily confused

This is the most important part when working with option arguments.

Suppose a program receives one of the following cases:

~~~text
Case A: no --dry-run
Case B: --dry-run
Case C: --dry-run=
Case D: --dry-run=false
~~~

By the API contract:

| Case | `containsOption("dry-run")` | `getOptionValues("dry-run")` | Element count |
| --- | --- | --- | --- |
| A: absent | `false` | `null` | No list |
| B: valueless flag | `true` | Empty list `[]` | 0 |
| C: has one empty string | `true` | List containing `""` | 1 |
| D: value `false` | `true` | List containing `"false"` | 1 |

**Java printing trap:** `List.of("").toString()` also produces `[]`, making it easy to confuse with a zero-element list. Therefore, when you need to distinguish `--flag` from `--flag=`, **check size and string content**, do not just inspect `List.toString()` logs.

Helper function (placed in an appropriate class) for accurate reporting:

~~~java
private static String describeOption(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);

    if (values == null) {
        return "absent";
    }
    if (values.isEmpty()) {
        return "present, 0 values";
    }
    return "present, " + values.size()
            + " value(s); firstLength=" + values.get(0).length();
}
~~~

This snippet requires importing `java.util.List` and `org.springframework.boot.ApplicationArguments`. The complete example uses this exact method.

### A flag does not automatically become a boolean

For `--dry-run`:

~~~java
boolean dryRun = args.containsOption("dry-run");
~~~

This interprets the **presence** of the flag. Yet with `--dry-run=false`, the expression above **still evaluates to true** because the option is present, only with a different value.

If the application accepts `--dry-run`, `--dry-run=true`, and `--dry-run=false`, write an explicit parser:

~~~java
private static boolean readBooleanFlag(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);
    if (values == null) {
        return false;
    }
    if (values.isEmpty()) {
        return true;
    }
    if (values.size() != 1) {
        throw new IllegalArgumentException(
                "Expected at most one value for --" + name);
    }
    if ("true".equalsIgnoreCase(values.get(0))) {
        return true;
    }
    if ("false".equalsIgnoreCase(values.get(0))) {
        return false;
    }
    throw new IllegalArgumentException(
            "Expected --" + name + "=true or =false");
}
~~~

This is **illustrative code**, not a standalone Java class; it requires the aforementioned imports and a calling context. This method defines a clear policy: a valueless flag means `true`, while `--flag=` is rejected. In real systems, the policy may differ, but it must be consistent, tested, and emit clear error messages.

## 5. Unnamed arguments are positional, not "unnecessary"

Non-option arguments are strings not treated by the parser as named options. Common example:

~~~bash
java -jar importer.jar --mode=import customers.csv archive.csv
~~~

The application specifies:

- `getNonOptionArgs().get(0)` is the input file path;
- `getNonOptionArgs().get(1)` is the output file path;
- `--mode=import` is an option controlling execution behavior.

However, the parser **does not know** whether those two files exist, whether the order is valid, or whether permissions exist. Validation is needed:

~~~java
List<String> files = args.getNonOptionArgs();

if (files.size() != 2) {
    throw new IllegalArgumentException(
            "Expected input and output file arguments");
}

Path input = Path.of(files.get(0));
Path output = Path.of(files.get(1));
~~~

This is an illustrative snippet requiring `List` and `Path` imports and a variable `args` of type `ApplicationArguments`. Constructing `Path` alone does not guarantee the files can be read/written; I/O checks and safe path handling are needed when actually using them.

### Do not rely on raw token indices to find positional arguments

With both invocations:

~~~text
--mode=import customers.csv archive.csv
customers.csv --mode=import archive.csv
~~~

`getNonOptionArgs()` yields a two-element list containing the input/output files in the order of **the non-options**. By contrast, `getSourceArgs()[0]` is an option in the first example, whereas it is the input file in the second example.

**Design rule:** For a CLI command, cleanly separate control options (*mode*, *verbose*, *timeout*) from positional operands (*input*, *output*, *jobId*).

### Tokens that are easily misunderstood

- `-n` is not `--name` under this simple parser's syntax; do not promise it will be treated as a short option.
- `-5` is a non-option in the form of a negative-number string in this parser's context.
- `=abc` can still be a non-option; the parser only recognizes options with the exact `--` prefix.
- `--name=value` is a named option; a path or filename **starting with `--`** may be classified as an option, so define clear passing conventions. Do not rely on POSIX parser behavior of other tools without testing the version in use.
- `--tag=a,b` contains a single string value `a,b`; Spring does not automatically turn the comma into two elements in `getOptionValues("tag")`. If business logic wants a list, define a splitting step and escaping rules separately.

## 6. The default parser is not a full CLI framework

Spring Boot provides a mechanism sufficient for common application needs, but do not mistake it for a dedicated CLI parser.

### No automatic full schema validation

`ApplicationArguments` does not know that `--mode` may only accept `import` or `validate`; it does not automatically convert `--port=8080` to `int`, and does not automatically report an error when a business-required positional operand is missing.

### Other tools' syntaxes are not supported by default

Other CLI tools may accept `-v`, `-o file`, bundled short flags `-abc`, nested subcommands, the `--` end-of-options marker, or spaces between key and value. **Do not assume all those syntaxes share the same semantics in Spring Boot 3.3**.

For Spring Framework 6.1 within this lesson's scope, the `SimpleCommandLinePropertySource` documentation specifies the `--name[=value]` form and does not promise a general parser contract like POSIX getopt. If you need multiple subcommands, required options, auto-generated help, shell completion, or short-option support, consider a dedicated CLI library such as picocli (with dedicated integration) rather than stitching strings together in many places.

### Repeating the same option name is parser/version dependent

`ApplicationArguments.getOptionValues(name)` returns a list and describes multiple values when the underlying parser supports it. However, **do not treat that as proof** that every version of `SimpleCommandLineArgsParser` accepts repeating `--tag=alpha --tag=beta`. Spring Framework 6.1 documentation even listed repeating the same option among invalid examples, whereas newer versions changed behavior.

Therefore, the runnable example in this lesson uses:

~~~text
--tag=alpha,beta
~~~

as **one option containing exactly one string `alpha,beta`**. When list support is needed, split the string with explicit rules or use a parser/version confirmed to support repeated options. Do not write tests relying on behavior that differs from your actual Spring Framework dependency.

## 7. Complete example: observing option and non-option args in Spring Boot

The example uses **Java 17+**, **Spring Boot 3.3.13**, and Gradle. It runs non-web and requires no database. There are two runners:

- `StructuredArgumentsRunner implements ApplicationRunner`: reads the groups from `ApplicationArguments`.
- `RawArgumentsRunner implements CommandLineRunner`: prints the passed string array verbatim for comparison.

The two runners are ordered with `@Order` so output lines do not depend on component scanning order.

### 7.1. File structure

~~~text
application-arguments-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/args/
    ├── ArgumentsDemoApplication.java
    ├── StructuredArgumentsRunner.java
    └── RawArgumentsRunner.java
~~~

**`settings.gradle`:**

~~~groovy
rootProject.name = 'application-arguments-demo'
~~~

**`build.gradle`:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
}

springBoot {
    mainClass = 'com.example.args.ArgumentsDemoApplication'
}
~~~

Uses Gradle compatible with Spring Boot 3.3 and JDK 17+. Dependencies are downloaded from Maven Central if not already cached. `spring-boot-starter-web` is not needed because the lesson only observes arguments and runners.

### 7.2. Main: passing args to SpringApplication

**`src/main/java/com/example/args/ArgumentsDemoApplication.java`:**

~~~java
package com.example.args;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class ArgumentsDemoApplication {

    public static void main(String[] args) {

        SpringApplication application =
                new SpringApplication(ArgumentsDemoApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("MAIN: run returned");
        }

        System.out.println("MAIN: context closed");
    }
}
~~~

`SpringApplication.run(args)` is where Spring Boot receives the string array. After context refresh, Boot invokes the runners. `WebApplicationType.NONE` ensures the example does not start an HTTP server. The `try-with-resources` block closes the context after runners finish; this is an **illustrative CLI application**, not a pattern for long-running web servers.

### 7.3. ApplicationRunner: reading option/non-option groups

**`src/main/java/com/example/args/StructuredArgumentsRunner.java`:**

~~~java
package com.example.args;

import java.util.List;
import java.util.TreeSet;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(10)
public final class StructuredArgumentsRunner
        implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {

        System.out.println("APP: options="
                + new TreeSet<>(args.getOptionNames()));

        System.out.println("APP: mode="
                + args.getOptionValues("mode"));

        System.out.println("APP: tag="
                + args.getOptionValues("tag"));

        System.out.println("APP: hasDryRun="
                + args.containsOption("dry-run"));

        System.out.println("APP: dryRun="
                + describeOption(args, "dry-run"));

        System.out.println("APP: empty="
                + describeOption(args, "empty"));

        System.out.println("APP: missing="
                + describeOption(args, "missing"));

        System.out.println("APP: nonOptions="
                + args.getNonOptionArgs());
    }

    private static String describeOption(
            ApplicationArguments args, String name) {

        List<String> values = args.getOptionValues(name);

        if (values == null) {
            return "absent";
        }
        if (values.isEmpty()) {
            return "present, 0 values";
        }
        return "present, " + values.size()
                + " value(s); firstLength="
                + values.get(0).length();
    }
}
~~~

Here:

- `new TreeSet<>(...)` is only used to **sort option names when printing**, avoiding inferring order from `Set`. It does not alter the original arguments.
- `getOptionValues("tag")` returns a list containing one string `alpha,beta` in the next section's command.
- `describeOption(...)` separates three cases: absent, valueless flag, and one or more values; it accurately distinguishes `--dry-run` and `--empty=`.
- `getNonOptionArgs()` returns the list of non-option tokens, preserving their order of appearance in the input.
- `@Order(10)` ensures this runner executes before `RawArgumentsRunner`, which has `@Order(20)`.

### 7.4. CommandLineRunner: observing all raw args

**`src/main/java/com/example/args/RawArgumentsRunner.java`:**

~~~java
package com.example.args;

import java.util.Arrays;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Component
@Order(20)
public final class RawArgumentsRunner
        implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("CMD: raw="
                + Arrays.toString(args));
    }
}
~~~

`CommandLineRunner` receives the raw array and provides no option/non-option classification API. Both runner interfaces execute in the **same startup phase**; the order in the example comes from `@Order`, not because `ApplicationRunner` always runs before `CommandLineRunner`.

### 7.5. Running with both argument types

From the `application-arguments-demo` directory, run Gradle:

~~~bash
gradle bootRun --args="--mode=import --tag=alpha,beta input.csv --dry-run -v --empty="
~~~

If the project has a Gradle Wrapper, use `./gradlew bootRun --args="..."` on Linux/macOS or `.\gradlew.bat bootRun --args="..."` on Windows. The example project does not generate a wrapper itself, so you need Gradle installed or to add a wrapper via project tooling.

In this command, the actual **application arguments** are:

~~~text
--mode=import
--tag=alpha,beta
input.csv
--dry-run
-v
--empty=
~~~

All tokens above are passed to `main(String[] args)`; the outer `--args=...` belongs to Gradle `bootRun` syntax, not an option seen by the application's `ApplicationArguments`.

### 7.6. Expected output

Ignoring other Gradle/Spring Boot log lines, the lines printed by the three demo Java classes themselves are:

~~~text
APP: options=[dry-run, empty, mode, tag]
APP: mode=[import]
APP: tag=[alpha,beta]
APP: hasDryRun=true
APP: dryRun=present, 0 values
APP: empty=present, 1 value(s); firstLength=0
APP: missing=absent
APP: nonOptions=[input.csv, -v]
CMD: raw=[--mode=import, --tag=alpha,beta, input.csv, --dry-run, -v, --empty=]
MAIN: run returned
MAIN: context closed
~~~

Reading line by line:

1. `APP: options` contains **option names without `--`**, sorted by `TreeSet`.
2. `APP: mode=[import]` illustrates an option with one value.
3. `APP: tag=[alpha,beta]` contains **one** string element `alpha,beta`, not two separate values: if needed, you must parse the comma yourself.
4. `APP: hasDryRun=true` confirms the flag is present.
5. `APP: dryRun=present, 0 values` confirms the `--dry-run` flag **has no value**.
6. `APP: empty=present, 1 value(s); firstLength=0` confirms `--empty=` is **one empty string**.
7. `APP: missing=absent` shows that `getOptionValues("missing")` returns `null`.
8. `APP: nonOptions=[input.csv, -v]` shows that the default parser does not treat `-v` as a double-dash option.
9. `CMD: raw` preserves **all** six tokens in order.
10. `MAIN: run returned` and `MAIN: context closed` indicate this is a CLI program that terminates normally on its own.

**Comparison note:** Different Gradle/plugin versions or environments may print additional system lines. Since the output is generated from application code, match *the lines prefixed with `APP`, `CMD`, and `MAIN`* rather than every line on the console.

## 8. Experiments comparing edge cases

Re-run each example with the same project; if you want shorter output, watch only the `mode` and `nonOptions` lines along with the related classification lines.

### 8.1. With equals sign vs. without equals sign

**Command A:**

~~~bash
gradle bootRun --args="--mode=import input.csv"
~~~

In the program:

~~~text
APP: mode=[import]
APP: nonOptions=[input.csv]
~~~

**Command B:**

~~~bash
gradle bootRun --args="--mode import input.csv"
~~~

With the default parser, the relevant parts become:

~~~text
APP: mode=[]
APP: nonOptions=[import, input.csv]
~~~

The line `APP: mode=[]` in command B means **the list has no values** because `--mode` is a flag. It does not mean `mode` contains an empty string or the word `import`.

### 8.2. Absent option vs. empty option

Compare:

~~~text
Case 1: input.csv
Case 2: --empty input.csv
Case 3: --empty= input.csv
~~~

For `getOptionValues("empty")`:

- Case 1: `null`.
- Case 2: a list with **0** elements.
- Case 3: a list with **1** element, where that element is `""` of length 0.

If you only print `List.toString()`, cases 2 and 3 can both appear as `[]`. This is why the example project prints the element count.

### 8.3. Strings containing spaces

With a shell that supports quoting as in the example:

~~~bash
gradle bootRun --args="--name='Lan Anh' input.csv"
~~~

How shells/Gradle handle quotes can vary by environment; do not assume every terminal preserves one quoting style. The key point is: if `main` receives **one** token `--name=Lan Anh` (with an internal space), the parser treats everything after the equals sign as **one string value**, without splitting it into two non-options.

In production, check `getSourceArgs()` or use a test that constructs `DefaultApplicationArguments` directly to confirm exact tokens, rather than guessing from how quotes appear in the shell.

### 8.4. Commas do not automatically split option values

~~~text
--tag=a,b,c
~~~

This is one token with value `a,b,c`. If you want to build a list:

~~~java
List<String> tags = Arrays.stream(value.split(","))
        .map(String::trim)
        .filter(s -> !s.isEmpty())
        .toList();
~~~

This snippet is **illustrative**, requiring a `String` variable `value` and importing `java.util.Arrays`. The application itself decides whether to allow empty items, commas inside data, escaping, or quoting. If inputs have complex formatting, use a CSV parser or suitable CLI framework rather than just `split(",")`.

### 8.5. Negative numbers and short flags

~~~text
--limit=10 -5 -v
~~~

- `--limit=10` is an option with one value `10`.
- `-5` and `-v` are non-options in this parser.
- `getNonOptionArgs()` is `[-5, -v]`.
- `getOptionValues("limit")` contains the string `"10"`, not automatically converted to an integer.

If you want to pass a negative number into a named option, use:

~~~text
--offset=-5
~~~

Then option `offset` has value `"-5"`; you can call `Integer.parseInt` in the validation step.

## 9. ApplicationArguments and Environment are not the same thing

Some command-line options also participate in Spring Boot configuration:

~~~bash
java -jar app.jar --server.port=9090 --spring.profiles.active=dev
~~~

By default, Spring Boot adds **named command-line options** to `Environment` as a property source, with configuration precedence defined by the framework. Consequently, `--server.port=9090` can determine the server port and `--spring.profiles.active=dev` can participate in configuring profiles when applied properly during bootstrap.

However:

- `ApplicationArguments` is **the parser model for argv**.
- `Environment` is **the property resolution system** across command line, environment variables, system properties, Config Data, and other sources.
- `getNonOptionArgs()` returns positional operands; it does not create properties like `server.port` just by placing an unnamed token.
- `@ConfigurationProperties` is the choice for binding complex configuration, validating types, and defaults; it does not replace positional parsing when the CLI needs ordered operands.

### Disabling the command-line property source while still reading args

Spring Boot allows calling before `run`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

This is an **illustrative snippet**, assuming a `MyApplication` class exists. This setting prevents adding command-line options to `Environment` via the default mechanism, but does not make the `args` array passed to `run` disappear; `ApplicationArguments` can still classify them.

This is useful if you want CLI arguments to serve solely as business data and not accidentally override system configuration. Conversely, if your deployment actively uses `--spring...` to configure the environment, understand the impact of disabling the property source before using it.

### Do not equate an option with a Spring property

An option named `--mode=import` **may** appear in the command-line property source, yet the application may not have defined a valid `mode` property. Nor does every property in `Environment` come from the command line. To know where a setting came from, inspect the property sources / Actuator `env` when enabled and control access to sensitive data.

## 10. How do ApplicationRunner and CommandLineRunner handle args?

| Interface | Callback parameter | Strength |
| --- | --- | --- |
| `ApplicationRunner` | `run(ApplicationArguments args)` | Directly reads options/non-options, avoiding writing a parser yourself |
| `CommandLineRunner` | `run(String... args)` | Receives raw array; suits tools wanting custom parsing or forwarding |

Both are **Spring bean callbacks**, invoked by Spring Boot after application context refresh and before the `ApplicationReadyEvent` milestone. Ordering between the two types is not determined by interface name; the example in section 7 uses `@Order(10)`/`@Order(20)`.

If a runner encounters invalid arguments and throws `IllegalArgumentException`, Spring Boot generally treats that as a startup failure and does not proceed to successful readiness. Therefore, put necessary validation in the runner and write short, clear error messages that do not expose secrets.

**Do not confuse with request parameters.** In Spring MVC/WebFlux, `@RequestParam` parses query parameters of **each HTTP request**, completely different from arguments passed at process startup. `--mode=import` only appears at startup, not on every user URL request.

## 11. Input validation by CLI contract

Do not rely solely on parser syntax. Define a business contract for each command.

Example command:

~~~text
importer [--mode=import|validate] [--dry-run] INPUT_FILE [OUTPUT_FILE]
~~~

Here the brackets in the line above represent **CLI description syntax**, not characters passed to `main`. The contract might be:

- `--mode` is required, with exactly one value from the set `import` or `validate`.
- `--dry-run` is optional; if without a value, it is interpreted as enabled.
- `INPUT_FILE` is a required positional operand.
- `OUTPUT_FILE` is permitted only in `import` mode; in `validate` mode it must be absent.
- Any option outside the allowed list is rejected to catch typos.

Example mode validation snippet:

~~~java
List<String> modes = args.getOptionValues("mode");

if (modes == null || modes.size() != 1
        || modes.get(0).isBlank()) {
    throw new IllegalArgumentException(
            "Expected exactly one --mode=import|validate");
}

String mode = modes.get(0);

if (!mode.equals("import") && !mode.equals("validate")) {
    throw new IllegalArgumentException(
            "Unsupported mode: " + mode);
}
~~~

This is an **illustrative snippet inside `ApplicationRunner`**, requiring `java.util.List` and a variable `args` of type `ApplicationArguments`. Do not add this validation snippet to the section 7 example project if you want to preserve the classification-demo stdout.

### Validating positional arguments

~~~java
List<String> files = args.getNonOptionArgs();

if (files.isEmpty() || files.size() > 2) {
    throw new IllegalArgumentException(
            "Expected INPUT_FILE and optional OUTPUT_FILE");
}
~~~

If file paths must exist on disk, handle `Path.of(...)`, `Files.isRegularFile(...)`, and appropriate I/O exceptions, without assuming an index in the list guarantees a safe file. In particular, if the application runs with broad write permissions, watch out for path traversal and restrict read/write locations.

### Checking unknown options

~~~java
Set<String> supported =
        Set.of("mode", "dry-run", "timeout");

for (String optionName : args.getOptionNames()) {
    if (!supported.contains(optionName)) {
        throw new IllegalArgumentException(
                "Unknown option: --" + optionName);
    }
}
~~~

This snippet requires importing `java.util.Set` and a variable `args` of type `ApplicationArguments`. In real Spring Boot applications, many `spring.*` options may be used for framework configuration. **Do not blindly forbid all unknown options** if the application needs to support standard Boot or library options. Decide on a clear CLI policy that aligns with your configuration approach.

### Sensitive information

Do not log the entire `getSourceArgs()` in production if arguments may contain tokens, passwords, API keys, DSNs with credentials, or sensitive paths. Arguments can be visible via process lists, shell history, CI logs, and telemetry. Use a secret manager, mounted secrets, or appropriate platform mechanisms; in logs, print only filtered option names needed for diagnostics.

## 12. Testing the parser without starting the entire application

If you only want to test syntax and classification, you can instantiate `DefaultApplicationArguments` directly in a Java test instead of waiting for Spring Boot startup.

Example body of a test:

~~~java
ApplicationArguments parsed = new DefaultApplicationArguments(
        "--mode=import",
        "input.csv",
        "--dry-run",
        "--empty=");

System.out.println(parsed.containsOption("mode"));       // true
System.out.println(parsed.getOptionValues("mode"));       // [import]
System.out.println(parsed.getNonOptionArgs());            // [input.csv]
System.out.println(parsed.getOptionValues("dry-run").size()); // 0
System.out.println(parsed.getOptionValues("empty").size());   // 1
~~~

This is an **illustrative snippet**, requiring imports for `org.springframework.boot.ApplicationArguments` and `org.springframework.boot.DefaultApplicationArguments`. End-of-line comments describe expected values, not compiler-generated output. Place the code in a runnable Java method within a Spring Boot project that has dependencies configured.

If you want to test classification with varying inputs, use JUnit:

~~~java
@Test
void bareFlagAndEmptyValueAreDifferent() {
    ApplicationArguments parsed =
            new DefaultApplicationArguments(
                    "--dry-run", "--empty=");

    assertTrue(parsed.containsOption("dry-run"));
    assertEquals(0, parsed.getOptionValues("dry-run").size());
    assertEquals(1, parsed.getOptionValues("empty").size());
    assertEquals("", parsed.getOptionValues("empty").get(0));
    assertNull(parsed.getOptionValues("missing"));
}
~~~

This is an **illustrative test snippet**, not a standalone JUnit file. It requires `spring-boot-starter-test` (test scope), Gradle's `useJUnitPlatform()` configuration, and JUnit Jupiter `@Test`/assertion imports. The key point is that the test must distinguish `null`, a size-0 list, and a size-1 list containing an empty string.

### What additional scenarios should be tested?

- Order of positional operands when options appear interspersed.
- Option with an equals sign in the value (`--token=a=b`).
- Paths with spaces via a `String[]` array directly, avoiding shell dependency.
- Zero positional args, one positional arg, too many positional args.
- Negative numbers (`-5` token), `-v` token, and `--offset=-5` option.
- Flag with value `--dry-run=false` versus valueless flag `--dry-run`.
- Handling of unknown options, blank values, and type conversion errors.
- Syntax for passing arguments from Gradle, Maven, IDEs, Docker/Kubernetes.
- Parser differences across Spring Framework versions, especially when using repeated-option syntax or the option delimiter.

## 13. Common mistakes and how to fix them

**1. "Every token starting with a dash is an option."** False. The default parser is described by `--name[=value]`; `-v` and `-12` do not automatically become valid short options.

**2. "`--mode import` is equivalent to `--mode=import`."** False under the default parser. `--mode` has no value attached via `=`; `import` is positional.

**3. "`getOptionValues` returning `[]` means the option is absent."** False. `null` represents absent, whereas a size-0 list represents a flag that is present without a value.

**4. "`--empty=` is the same as `--empty`."** False: one case has **one empty string** and the other has **no value**.

**5. "`containsOption('dry-run')` checks the option's boolean value."** False. It checks whether the option is present; `--dry-run=false` still has `containsOption == true`.

**6. "`getOptionNames` returns the same order as argv."** Do not rely on `Set` order. If you need original token order, use `getSourceArgs()`; if you just want alphabetical logging of names, sort the `Set` as in the example.

**7. "`getNonOptionArgs` contains all arguments."** No. It only contains positional/non-option args; tokens of the form `--name=value` are placed in the option group.

**8. "Unnamed arguments can always be ignored."** No. A positional argument such as an input file may be required data for a CLI command.

**9. "`--tag=a,b` automatically creates two option values."** No: that is one string value `a,b`. Split on commas if the business contract requires it.

**10. "Having `List<String>` means repeating `--tag=a --tag=b` is always supported."** No. The list contract and parser/version support are two separate matters. Do not bring newer Spring Framework syntax back to Spring Boot 3.3 without verifying.

**11. "`CommandLineRunner` and `ApplicationRunner` handle different types of arguments."** Both receive input from the same argv source. The difference is that `ApplicationRunner`'s callback has a classified wrapper, whereas `CommandLineRunner` receives raw strings.

**12. "Simply declaring `--server.port` means it is only used for business CLI logic."** By default, command-line options can also participate in `Environment`, so avoid option names colliding with framework configuration unless intended.

**13. "Logging all raw args in production has no risk."** False. Secrets can leak in logs, process lists, and pipelines; classify, filter, or choose another secret-delivery channel.

**14. "Once the application is running, changing argv immediately updates beans."** No. Arguments are parsed at startup; runtime configuration changes have a different contract and do not automatically re-initialize every bean.

**15. "Every HTTP request passes through `ApplicationArguments`."** No: `ApplicationArguments` is tied to the `SpringApplication.run` invocation. HTTP request query parameters are handled by the web framework, not the startup parser.

**16. "Spring Boot automatically raises an error when positional `input.csv` is missing."** The parser only classifies. Required conditions, file types, permissions, and validation are business responsibilities.

## 14. Practice exercises

1. Classify manually: `--mode=import input.csv --dry-run output.csv`. How many option names are there? How many positional arguments?
2. Compare `--mode=import` with `--mode import` in the project. What happens to `getOptionValues("mode")` and `getNonOptionArgs()`?
3. Compare `--flag`, `--flag=`, `--flag=false`, and the case without the flag. Why is using only `containsOption` insufficient to parse a three-state boolean?
4. Run the section 7 demo. Why does `APP: tag=[alpha,beta]` not prove there are two elements in the list? Print `getOptionValues("tag").size()`.
5. Replace `--tag=alpha,beta` with `--tag=alpha`. How does the output change?
6. Pass two positional operands before the options. Does `getNonOptionArgs()` preserve the order of the two operands?
7. Pass `-5` and `--offset=-5`. Which group does each negative value belong to?
8. Pass `--name="Lan Anh"` via IDE program arguments. Then print `getSourceArgs()` and check whether it becomes one or two tokens; which part is affected by shell quoting?
9. Write validation for the contract: mode must be `import`/`validate` and there must be one input file. When input is missing, what error should be reported to the user?
10. Modify the runner to fail startup when mode is invalid. What happens to `ApplicationReadyEvent`?
11. In a web project, pass `--server.port=9090` and inspect the application environment. Why are not all CLI options purely for business logic?
12. Try `SpringApplication.setAddCommandLineProperties(false)` before `run`. Why does `ApplicationArguments` still have the arguments while `Environment` does not add the default command-line property source?
13. Write a JUnit test for `DefaultApplicationArguments("--dry-run", "--empty=")`, asserting size and string length. Why should you not compare only `List.toString()`?
14. Design a CLI accepting multiple file paths where one path has spaces or starts with a dash. What quoting and validation rules will you set so it does not depend unpredictably on the shell?
15. If you need short flags, subcommands, help, completion, and schema validation, why should you consider picocli instead of trying to turn `ApplicationArguments` into a full parser?
16. If the `--api-token` option contains a secret, why is logging `Arrays.toString(args)` risky? Which configuration channels are more suitable in production?

## Key Takeaways

- **Option** in the default parser: `--name` or `--name=value`. **Non-option**: tokens not recognized under option syntax, typically positional operands.
- `getOptionNames()` and `containsOption(name)` work with **names without the `--` prefix**.
- `getOptionValues(name)` has three states: **`null`** when absent, an **empty list** for a present valueless flag, or a **list with values**; `--name=` has one empty-string value.
- `getNonOptionArgs()` returns only positional operands, while `getSourceArgs()` preserves the entire raw argv array.
- **`--mode import` is not `--mode=import`**. The equals sign separates the name and value of the same token.
- `ApplicationRunner` provides the classified API via `ApplicationArguments`; `CommandLineRunner` provides raw `String...`, and both execute in the startup phase after refresh.
- The parser only classifies; **it does not perform business validation**. Validate counts, data, required options, paths, and error policies yourself.
- Command-line options can participate in `Environment` by default, whereas positional operands do not automatically become named configuration properties.
- When advanced CLI syntax or repeated options are needed, check the **actual parser version** or use a dedicated CLI library.

### References

- Spring Boot 3.3 — Application Arguments: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3 — ApplicationArguments API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Boot 3.3 — DefaultApplicationArguments API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- Spring Framework 6.1 — SimpleCommandLinePropertySource: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html
- Spring Framework 6.1 — CommandLinePropertySource: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/env/CommandLinePropertySource.html
- Spring Boot 3.3 — ApplicationRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- Spring Boot 3.3 — CommandLineRunner API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
