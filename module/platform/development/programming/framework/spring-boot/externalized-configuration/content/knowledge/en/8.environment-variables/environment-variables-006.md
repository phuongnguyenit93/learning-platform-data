# Passing `--key=value` Arguments and Distinguishing Them from Regular Arguments in Spring Boot

## 1. Why distinguish arguments at launch time?

A Spring Boot application can be launched as follows:

~~~bash
java -jar demo.jar --server.port=9090 --app.batch-size=200 import customers.csv
~~~

After the JAR filename, four strings are passed to the program:

~~~text
--server.port=9090
--app.batch-size=200
import
customers.csv
~~~

Although all of them look like "command-line parameters", Spring Boot processes them in **two different groups**:

- `--server.port=9090` and `--app.batch-size=200` are **option arguments**. Each has a name and a value. By default, Spring Boot adds them to `Environment` as configuration properties.
- `import` and `customers.csv` are **non-option arguments**. They represent the business command and input data for the program; Spring Boot does not automatically convert them into named properties in `Environment`.

This distinction is especially useful when an application both has technical configuration and receives a job to execute: choosing a profile, service address, or processing limit, alongside the task name and file path.

Lesson goals:

1. Understand `--key=value`, `--flag`, `key=value`, and unprefixed argument syntax.
2. Know which arguments enter `Environment` and which belong only to the input operand list.
3. Read them accurately via `ApplicationArguments`, `Environment`, `@Value`, and `@ConfigurationProperties`.
4. Distinguish Spring Boot arguments, Java System properties, and OS environment variables.
5. Pass strings with spaces, multiple arguments, profiles, and options when running from terminal, IDE, or Gradle.
6. Recognize common errors such as writing `--key value` instead of `--key=value` or mistaking a regular argument for a configuration property.

## 2. Flow of arguments from terminal to application

When you type a command in a shell, the shell splits the command line into arguments according to quoting rules. The JVM consumes Java's own options and then forwards the strings after the JAR filename to the application's `main(String[] args)` method.

~~~text
Terminal / shell
       |
       | java -Duser.timezone=UTC -jar demo.jar --app.mode=fast import data.csv
       v
JVM processes -Duser.timezone=UTC and -jar demo.jar
       |
       | main(String[] args):
       |   ["--app.mode=fast", "import", "data.csv"]
       v
SpringApplication.run(DemoApplication.class, args)
       |
       +--> ApplicationArguments
       |      +--> option: app.mode = ["fast"]
       |      +--> non-option: ["import", "data.csv"]
       |
       +--> Command-line PropertySource (default)
              +--> app.mode = fast
                        |
                        v
                   Environment
                        |
                        +--> getProperty("app.mode")
                        +--> @Value
                        +--> @ConfigurationProperties
~~~

`-Duser.timezone=UTC` is processed by the JVM as a **Java System property**, not as a `--key=value` element in `args`. Conversely, `--app.mode=fast` is an application argument that Spring Boot can turn into a property in `Environment`.

Minimal launcher class:

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

**Forwarding `args` intact** into `SpringApplication.run(...)` is essential. If you call another launch API that omits `args`, parameters typed after the JAR filename will not be received by Spring Boot through the standard flow.

## 3. Syntax of an option argument

Spring Boot's standard form is:

~~~text
--key=value
~~~

Where:

- `--`: marker identifying an **option argument**.
- `key`: option name or property name.
- `=`: boundary between name and value.
- `value`: value passed as a string; Spring Boot can convert its type afterward.

Example:

~~~bash
java -jar demo.jar --server.port=9090 --spring.profiles.active=dev --app.retries=3
~~~

By default, Spring Boot creates configuration properties:

| Property name | Initial string value | Purpose |
| --- | --- | --- |
| `server.port` | `9090` | Sets the embedded web server port. |
| `spring.profiles.active` | `dev` | Activates a profile. |
| `app.retries` | `3` | Application-specific configuration. |

String values can be converted to target types during configuration binding: `server.port` to a number, `app.retries` to `int` if an appropriate `@ConfigurationProperties` class exists.

**Not every `--key=value` key is understood by Spring Boot as a built-in setting.** For example, `--app.retries=3` is an application-defined property; to use it, your code must read it from `Environment`, bind it into a bean, or handle it according to your application rules.

### Key names with dots and hyphens

A common style is using the exact same property names as in YAML/Properties files:

~~~yaml
app:
  export:
    output-dir: "./out"
    max-items: 100
~~~

You can override them with:

~~~bash
java -jar demo.jar --app.export.output-dir=./results --app.export.max-items=500
~~~

With `@ConfigurationProperties(prefix = "app.export")`, Spring Boot performs *relaxed binding* between configuration names and corresponding Java properties. With `Environment.getProperty(...)`, prefer the canonical key names you actually declared.

## 4. What is a non-option argument?

Arguments not classified by Spring Boot as options belong to the **non-option** group. They are typically business keywords, filenames, directories, or positional information interpreted by the application itself.

Example:

~~~bash
java -jar demo.jar import customers.csv
~~~

The non-option list is:

~~~text
["import", "customers.csv"]
~~~

Spring Boot does not automatically create properties named `import` or `customers.csv`. The application might define a convention:

- First element: action name, such as `import`, `export`, or `validate`.
- Second element: file path.
- Subsequent elements: additional positional parameters.

That is a **convention written in your application code**, not automatic mapping into Config Data properties.

### A key=value string is not necessarily an option

The command:

~~~bash
java -jar demo.jar app.retries=3
~~~

contains `app.retries=3` **without two leading hyphens**. Spring Boot treats this as a non-option. It is not equivalent to:

~~~bash
java -jar demo.jar --app.retries=3
~~~

In the second command, `app.retries` is an option and enters `Environment` by default.

This explains a common mistake: an operator thinks "I already passed `app.retries=3`", yet `Environment.getProperty("app.retries")` still returns the file value or `null` because `--` was missing.

## 5. `--key value` is not a key–value pair

A very common misconception:

~~~bash
java -jar demo.jar --app.mode fast
~~~

In Spring Boot's `ApplicationArguments` syntax, `--app.mode` is an **option with no value**, while `fast` is a separate **non-option argument**.

It differs from:

~~~bash
java -jar demo.jar --app.mode=fast
~~~

In the second example, `app.mode` has the value `fast`.

To see why, inspect the strings passed by the shell to Java:

| Text after JAR name | `args` array | Interpretation |
| --- | --- | --- |
| `--app.mode=fast` | `["--app.mode=fast"]` | One option with value `fast`. |
| `--app.mode fast` | `["--app.mode", "fast"]` | One option without a value and one non-option `fast`. |
| `app.mode=fast` | `["app.mode=fast"]` | One non-option; adds no CLI property. |
| `fast` | `["fast"]` | One non-option. |
| `--verbose` | `["--verbose"]` | One option present without a value. |
| `--verbose=true` | `["--verbose=true"]` | One option with string value `true`. |

For configuration needing an explicit value, use `--key=value`. The `--flag` syntax is convenient when you only need to check presence via `ApplicationArguments.containsOption(...)`.

### What does an option without a value mean?

The command:

~~~bash
java -jar demo.jar --verbose
~~~

indicates **the `verbose` option is present**. It does not mean every piece of Java code automatically receives Boolean `true` from a bound property. If you want an explicit Boolean configuration flag, usually write:

~~~bash
java -jar demo.jar --app.verbose=true
~~~

For a business flag needing only presence detection, use:

~~~java
boolean verboseRequested = args.containsOption("verbose");
~~~

Above, `args` is the `ApplicationArguments` instance supplied to the application.

## 6. ApplicationArguments: the API for classifying arguments

Spring Boot provides the `org.springframework.boot.ApplicationArguments` interface. It exposes **the raw input array** and **the classified arguments**.

Main methods:

| Method | Result |
| --- | --- |
| `getSourceArgs()` | Raw input `String[]` passed to the application, before classification. |
| `getOptionNames()` | Set of option names present. |
| `containsOption("name")` | `true` if an option with that name is present. |
| `getOptionValues("name")` | List of values for the option; see details below. |
| `getNonOptionArgs()` | List of non-option arguments, in input order. |

You can inject `ApplicationArguments` into a bean or receive it in `ApplicationRunner.run(...)`.

### Example running and reading arguments

Run:

~~~bash
java -jar demo.jar --app.mode=fast --verbose import customers.csv
~~~

A bean reading the data:

~~~java
package com.example.demo;

import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ArgumentReporter implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("Raw: " +
                Arrays.toString(args.getSourceArgs()));

        System.out.println("Option names: " +
                args.getOptionNames());

        System.out.println("app.mode values: " +
                args.getOptionValues("app.mode"));

        System.out.println("Verbose flag: " +
                args.containsOption("verbose"));

        System.out.println("Non-option: " +
                args.getNonOptionArgs());
    }
}
~~~

Substantive output:

~~~text
Raw: [--app.mode=fast, --verbose, import, customers.csv]
Option names: [app.mode, verbose]
app.mode values: [fast]
Verbose flag: true
Non-option: [import, customers.csv]
~~~

The `getOptionNames()` set should not be relied on as an ordered list. Display order in a `Set` may vary across runs; classification and values are what matter.

### Cases for getOptionValues

Suppose we call `args.getOptionValues("app.mode")`:

| Input argument | `containsOption("app.mode")` | `getOptionValues("app.mode")` |
| --- | --- | --- |
| `--app.mode=fast` | `true` | `["fast"]` |
| `--app.mode=fast --app.mode=safe` | `true` | `["fast", "safe"]` |
| `--app.mode` | `true` | Empty list `[]`. |
| `--app.mode` omitted | `false` | `null`. |
| `app.mode=fast` | `false` | `null`. |

Important distinction: **missing option** and **present option with no value** differ. One returns `null`, the other returns an empty list. For `--key=` with an equals sign and empty content, the application should validate empty strings according to business needs.

### Reading arguments defensively

~~~java
import java.util.List;
import org.springframework.boot.ApplicationArguments;

public final class Options {

    private Options() {
    }

    public static String requiredSingleValue(
            ApplicationArguments args, String name) {

        List<String> values = args.getOptionValues(name);

        if (values == null || values.size() != 1
                || values.get(0).isBlank()) {
            throw new IllegalArgumentException(
                    "Exactly one value is required for --" + name + "=...");
        }

        return values.get(0);
    }
}
~~~

This works well when a parameter **must have exactly one value**. It catches missing options, valueless options, blank values, and repeated options.

For standard Spring Boot configuration, you do not necessarily need to write the helper above; `@ConfigurationProperties` and validation can handle property types and validity. The helper merely shows how to read arguments as an application-defined command interface.

## 7. Repeating an option multiple times

Spring Boot allows the same option name to appear multiple times in the input:

~~~bash
java -jar demo.jar --tag=java --tag=spring --tag=boot import source.csv
~~~

With `ApplicationArguments`:

~~~java
List<String> tags = args.getOptionValues("tag");
~~~

The `tags` list holds the three values in order of appearance:

~~~text
[java, spring, boot]
~~~

This is useful when you want a business command to accept multiple filters or labels. However, do not assume a **single property** bound via `@Value` or `Environment` has the same semantics as a repeated option list. `CommandLinePropertySource` conversion may represent multi-valued options using its own rules; to preserve "repeated three times" semantics, read `ApplicationArguments.getOptionValues(...)` directly.

If you want a configuration property carrying a list, design appropriate syntax and data types for `@ConfigurationProperties`, and verify the corresponding binding behavior. Do not arbitrarily mix the two handling styles for the same parameter without a clear contract.

## 8. Environment: why can `--key=value` override application.yaml?

By default, `SpringApplication` converts **option arguments** starting with `--` into a `CommandLinePropertySource` in `Environment`.

Example configuration file:

~~~yaml
# src/main/resources/application.yaml
app:
  mode: safe
  batch-size: 50
  greeting: "Hello"
~~~

Launch:

~~~bash
java -jar demo.jar --app.mode=fast --app.batch-size=300
~~~

Typical effective values:

| Key | YAML file | Command line | Effective value |
| --- | --- | --- | --- |
| `app.mode` | `safe` | `fast` | `fast` |
| `app.batch-size` | `50` | `300` | `300` |
| `app.greeting` | `Hello` | Absent | `Hello` |

The command line overrides **key by key**. It does not erase the rest of `application.yaml`.

Reading from Java:

~~~java
package com.example.demo;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class RuntimeSettings {
    private final Environment environment;

    public RuntimeSettings(Environment environment) {
        this.environment = environment;
    }

    public String mode() {
        return environment.getProperty("app.mode", "safe");
    }

    public int batchSize() {
        return environment.getProperty(
                "app.batch-size", Integer.class, 50);
    }
}
~~~

`getProperty("app.mode")` returns the value resolved by Spring from active sources. If there is no CLI source for this key, it can still come from an environment variable, Java System property, or configuration file.

### Why precedence order matters

In a normal run, Spring Boot places command-line properties higher than many other common sources, including `application.yaml`, OS environment variables, and Java System properties.

Example in a Unix-style shell:

~~~bash
APP_MODE=environment \
java -Dapp.mode=system -jar demo.jar --app.mode=cli
~~~

Without any other special source intervening, `Environment.getProperty("app.mode")` is `cli`.

Remove `--app.mode=cli`, and Java System property `app.mode=system` can beat the environment variable; also remove `-Dapp.mode=system`, and the environment variable can beat the default in the file.

Note that test-specific configuration sources, or DevTools when enabled, can have special precedence orders. The rule above describes a **standard application run**, not every test context.

## 9. Accessing via @Value and @ConfigurationProperties

`--key=value` data can be consumed just like other configuration properties.

### 9.1. @Value for a single property

~~~java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class GreetingConfig {

    private final String greeting;

    public GreetingConfig(
            @Value("${app.greeting:Hello}") String greeting) {
        this.greeting = greeting;
    }

    public String greeting() {
        return greeting;
    }
}
~~~

If run with:

~~~bash
java -jar demo.jar --app.greeting="Hello from command line"
~~~

`greeting` is injected from `Environment` with the value `Hello from command line`. If the property is absent, `@Value` uses the declared default `Hello`.

### 9.2. @ConfigurationProperties for a typed group

~~~java
package com.example.demo;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppCliProperties(
        String mode,
        int batchSize,
        boolean verbose) {
}
~~~

Register this record with `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(AppCliProperties.class)` in configuration.

Default file:

~~~yaml
app:
  mode: safe
  batch-size: 100
  verbose: false
~~~

Command:

~~~bash
java -jar demo.jar --app.mode=fast --app.batch-size=500 --app.verbose=true
~~~

The binder takes the effective values and converts them to `String`, `int`, and `boolean` respectively. `app.batch-size` binds to the Java field `batchSize` via relaxed binding.

When a group of parameters configures application behavior and requires validation, `@ConfigurationProperties` generally provides cleaner organization than scattered `getProperty(...)` calls.

**Unlike business arguments:** the two non-options `import customers.csv` are not automatically bound by `@ConfigurationProperties` into `mode` or `batchSize`. They still must be parsed separately by the application, such as via `ApplicationArguments`.

## 10. @Value is not an API for reading regular argument lists

Someone might try:

~~~java
@Value("${customers.csv}")
String fileName;
~~~

when running:

~~~bash
java -jar demo.jar import customers.csv
~~~

This does not work as intended: `customers.csv` is a **non-option argument**, not a property name created by Spring Boot. `@Value` only queries keys in `Environment`.

To read the input file, use:

~~~java
List<String> operands = args.getNonOptionArgs();
~~~

or define a named option yourself:

~~~bash
java -jar demo.jar --input=customers.csv
~~~

then you can read:

~~~java
String input = environment.getProperty("input");
~~~

Named options can be passed at any position on the command line; positional arguments make command syntax concise. Depending on the task, you can use both under a clear contract.

## 11. Complete example: an import command with options and non-options

Design an application accepting the command:

~~~bash
java -jar importer.jar \
  --spring.main.web-application-type=none \
  --app.batch-size=250 \
  --dry-run \
  import customers.csv
~~~

Intent:

- `--spring.main.web-application-type=none`: configures Spring Boot not to start a web server.
- `--app.batch-size=250`: configuration value setting the batch size limit.
- `--dry-run`: business flag indicating simulation only.
- `import`: job name.
- `customers.csv`: path to source data.

### 11.1. Base configuration

~~~yaml
# application.yaml
app:
  batch-size: 100
~~~

### 11.2. Runner consuming both argument groups

~~~java
package com.example.importer;

import java.util.List;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements ApplicationRunner {

    private final Environment environment;

    public ImportRunner(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> operands = args.getNonOptionArgs();

        if (operands.size() != 2 ||
                !"import".equals(operands.get(0))) {
            throw new IllegalArgumentException(
                    "Usage: [options] import <file>");
        }

        String file = operands.get(1);
        boolean dryRun = args.containsOption("dry-run");

        Integer batchSize = environment.getProperty(
                "app.batch-size", Integer.class, 100);

        if (batchSize == null || batchSize <= 0) {
            throw new IllegalArgumentException(
                    "app.batch-size must be a positive integer");
        }

        System.out.println("Operation = import");
        System.out.println("File = " + file);
        System.out.println("Batch size = " + batchSize);
        System.out.println("Dry run = " + dryRun);

        // Illustrates input classification; does not read or modify a real file.
    }
}
~~~

Main output:

~~~text
Operation = import
File = customers.csv
Batch size = 250
Dry run = true
~~~

Note: `ImportRunner` only illustrates argument handling. For a real CLI tool, design exit codes for invalid arguments, application shutdown behavior, and business error handling; Spring Boot does not generate a subcommand framework for you.

### 11.3. If the user omits the equals sign

The command:

~~~bash
java -jar importer.jar --app.batch-size 250 import customers.csv
~~~

is classified as:

- Option `app.batch-size`: **present without a value**.
- Non-options: `250`, `import`, `customers.csv`.

The runner above will see **three** non-options and throw a usage error instead of silently treating `250` as the batch size.

The correct syntax is:

~~~bash
java -jar importer.jar --app.batch-size=250 import customers.csv
~~~

This example shows how clear classification produces helpful errors instead of continuing with unexpected values.

## 12. Distinguishing from Java System properties: -Dkey=value

Two syntaxes are easy to confuse:

~~~bash
java -Dapp.mode=fast -jar demo.jar
~~~

and:

~~~bash
java -jar demo.jar --app.mode=fast
~~~

Both **can supply property `app.mode` to `Environment`**, but they come from different sources.

| Syntax | Read first by | Appears in `main(String[] args)`? | Source in Spring `Environment` |
| --- | --- | --- | --- |
| `-Dapp.mode=fast` placed before `-jar` | JVM | No | Java System properties. |
| `--app.mode=fast` placed after `demo.jar` | Application/Spring Boot | Yes | Default command-line property source. |
| `app.mode=fast` placed after `demo.jar` | Application | Yes, as non-option | Does not automatically become a property. |

Example:

~~~bash
java -Dapp.mode=system -jar demo.jar --app.mode=cli
~~~

`ApplicationArguments.getOptionValues("app.mode")` reflects `cli` from the option. `System.getProperty("app.mode")` reflects `system`. `Environment.getProperty("app.mode")` normally reflects `cli` because the command-line property source takes higher priority than Java System properties in a standard run.

If you place `-Dapp.mode=system` **after** the JAR filename, it is no longer a JVM option in the valid position, but rather a string passed to the application. Keep JVM options before `-jar` and application arguments after the JAR name.

## 13. Distinguishing from operating system environment variables

An environment variable is a process property supplied by the operating system or deployment environment. It **does not need** to appear in `String[] args`.

In a Unix-style shell:

~~~bash
export APP_BATCHSIZE=120
java -jar demo.jar
~~~

According to environment variable mapping rules for `@ConfigurationProperties`, canonical property `app.batch-size` corresponds to `APP_BATCHSIZE`: replace dots with underscores, remove hyphens, then uppercase.

If running simultaneously:

~~~bash
APP_BATCHSIZE=120 java -jar demo.jar --app.batch-size=300
~~~

then the effective configuration from CLI is typically `300`, because the command-line source takes precedence over environment variables.

Comparison:

| Source | Typical syntax | Present in `main(args)`? |
| --- | --- | --- |
| Environment variable | `APP_BATCHSIZE=120` | No |
| Java System property | `-Dapp.batch-size=120` before `-jar` | No |
| Spring Boot command-line option | `--app.batch-size=120` after JAR | Yes |
| Non-option argument | `customers.csv` after JAR | Yes |

**Do not equate environment variables and command-line options.** Both can supply values to `Environment`, yet differ in declaration syntax, delivery timing, and precedence. That is why this lesson sits within the Spring Boot externalized configuration track.

## 14. Syntax with spaces, equals signs, and special characters

The shell must turn each multi-word value into a single argument. Example:

~~~bash
java -jar demo.jar --app.message="Hello user" import "my data.csv"
~~~

In common shells, Java receives:

~~~text
["--app.message=Hello user", "import", "my data.csv"]
~~~

Quotes tell the shell to keep spaces inside one argument. Spring Boot then classifies `--app.message=...` as an option with a value and `my data.csv` as a non-option.

### Multiple equals signs in a value

Example URL containing query parameters:

~~~bash
java -jar demo.jar '--app.endpoint=https://example.test/search?q=java&sort=asc'
~~~

In Unix shells, single quotes wrap the entire argument so `&` is not interpreted by the shell as a control operator. Spring Boot splits the option name at the first equals sign; everything after remains part of the value:

~~~text
Option name: app.endpoint
Value: https://example.test/search?q=java&sort=asc
~~~

If input comes from Windows or another runner, apply that environment's quoting rules. Spring Boot's parser only sees arguments **after the shell has processed them**.

### Empty values vs. valueless options

~~~bash
java -jar demo.jar --app.label=
~~~

and:

~~~bash
java -jar demo.jar --app.label
~~~

are different. The first explicitly passes an equals sign with an empty value; the second supplies an option without a value. Design validation rules according to application needs, especially for required strings and Booleans.

### Spaces around the equals sign

Do not write:

~~~bash
java -jar demo.jar --app.mode = fast
~~~

because shells usually split it into three separate arguments: `--app.mode`, `=`, and `fast`. The correct form is:

~~~bash
java -jar demo.jar --app.mode=fast
~~~

## 15. Multiple options and non-options in the same command

Options can be interspersed with non-option arguments in an application command:

~~~bash
java -jar demo.jar import --app.batch-size=500 customers.csv --dry-run
~~~

When parsed by Spring Boot, `--...` options remain options:

- `app.batch-size` has value `500`.
- `dry-run` is present without a value.
- Non-options are `import` and `customers.csv`.

This does not mean every **external CLI library** uses the exact same rules as `ApplicationArguments`. If you later integrate Picocli, Spring Shell, or another parser library, follow the contract of the parser in use.

For a pure Spring Boot application, relying on `ApplicationArguments` explains the built-in classification provided by Spring Boot.

## 16. Working with SpringApplication.run and ApplicationRunner

`SpringApplication.run(...)` creates the application, prepares `Environment`, builds `ApplicationContext`, and finally invokes the appropriate runners.

Two common interfaces:

~~~java
ApplicationRunner
CommandLineRunner
~~~

Both run after Spring Boot initializes the context, but receive different arguments:

| Interface | Method | Input |
| --- | --- | --- |
| `ApplicationRunner` | `run(ApplicationArguments args)` | Classified option/non-option data. |
| `CommandLineRunner` | `run(String... args)` | Raw argument strings. |

Example with `CommandLineRunner`:

~~~java
import java.util.Arrays;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
class RawRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(Arrays.toString(args));
    }
}
~~~

Command:

~~~bash
java -jar demo.jar --app.mode=fast import customers.csv
~~~

prints:

~~~text
[--app.mode=fast, import, customers.csv]
~~~

Here you must parse each string yourself if you want to separate options from non-options. For that need, `ApplicationRunner` and `ApplicationArguments` provide built-in support, usually with less code.

You can inject `ApplicationArguments` via constructor injection without becoming an `ApplicationRunner`:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.stereotype.Service;

@Service
class JobSelection {
    private final ApplicationArguments args;

    JobSelection(ApplicationArguments args) {
        this.args = args;
    }

    String operationOrDefault() {
        return args.getNonOptionArgs().isEmpty()
                ? "help"
                : args.getNonOptionArgs().get(0);
    }
}
~~~

Spring Boot can inject the `ApplicationArguments` bean so you can query it wherever needed.

## 17. Disabling command-line options from entering Environment

Normally `--app.mode=fast` serves two roles:

1. An option inside `ApplicationArguments`.
2. Added as a configuration property into `Environment`.

Spring Boot lets you disable the **second role**:

~~~java
import org.springframework.boot.SpringApplication;

public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setAddCommandLineProperties(false);
        application.run(args);
    }
}
~~~

Then, application options are no longer added as the default `CommandLinePropertySource`. `application.yaml`, environment variables, or Java System properties can still supply the same property name.

However, arguments are still passed to `SpringApplication.run(args)` and can still be read from `ApplicationArguments`; disabling the command-line property source does not delete input strings.

### When should you consider disabling it?

- The application wants to use `--...` as its own business command language without letting those strings accidentally override Spring configuration.
- Software must restrict which configuration keys operators are allowed to change.
- A specialized design wants all configuration loaded from selected sources and CLI handled by a separate parser.

Most Spring Boot applications keep the default behavior because it is convenient for deployment and testing. If disabled, pay close attention: an argument like `--spring.profiles.active=dev` will no longer take effect through the standard command-line source, so supply profiles from another source or handle them explicitly per application design.

## 18. Built-in Spring Boot parameters vs. application-defined parameters

Not every argument starting with `--` is a special Spring Boot command.

Some common built-in properties:

| Example | Role |
| --- | --- |
| `--server.port=9090` | Selects the HTTP port of a Spring Boot web application. |
| `--spring.profiles.active=prod` | Activates the production profile. |
| `--spring.config.location=optional:file:./config/` | Specifies where to locate Config Data from early startup. |
| `--spring.main.web-application-type=none` | Disables starting a web application. |
| `--logging.level.root=DEBUG` | Sets the root log level. |

Application-defined properties:

~~~bash
java -jar demo.jar --app.export.format=csv --app.export.max-items=1000
~~~

Spring Boot puts them into `Environment`, yet the application must read and use them. If no bean or code references `app.export.format`, passing it may produce no visible behavior change. **Do not assume every option is a command automatically executed by Spring Boot.**

### Note on --debug

~~~bash
java -jar demo.jar --debug
~~~

This is an example of a well-known flag Spring Boot recognizes to enable diagnostic output. However, `--debug` does not prove that **every** valueless option automatically converts to Boolean `true` when bound to application properties. For custom business Booleans, use an explicit convention:

~~~bash
java -jar demo.jar --app.trace-enabled=true
~~~

Or explicitly check presence:

~~~java
boolean requested = args.containsOption("trace");
~~~

## 19. Running from IDE, Gradle, and deployment tools

The option/non-option distinction **does not depend** on running the JAR directly versus via another tool; what matters is the final strings reaching `main(args)`.

### 19.1. In an IDE

Typically run configurations have separate fields:

- **Program arguments / Application arguments**: enter `--app.mode=fast import data.csv`.
- **VM options / JVM arguments**: enter `-Dapp.mode=system`.
- **Environment variables**: declare `APP_MODE=environment`.

If you enter `--app.mode=fast` in VM options instead of Program arguments, the JVM may reject it because it is not a JVM option. Conversely, if you enter `-Dapp.mode=system` in Program arguments, it is just an application string and will not become a Java System property in the standard way.

Field labels differ across IntelliJ IDEA, Eclipse, VS Code, or other runners, but the **JVM–application boundary** remains the same.

### 19.2. With Gradle bootRun

When using the Spring Boot Gradle plugin's `bootRun` task, you can pass program arguments via Gradle's `--args` option:

~~~bash
./gradlew bootRun --args='--app.mode=fast import data.csv'
~~~

In a Unix shell, single quotes ensure the entire `--args` value is passed to Gradle as one string for it to split into application arguments. In PowerShell or CMD, apply that OS's quoting syntax.

Note `--args` is an option **of the Gradle task running Java**, while `--app.mode=fast` is an option **forwarded to the Spring Boot application**. Do not confuse passing arguments to Gradle with passing arguments to the Java process.

### 19.3. Containers and orchestrators

When deploying in Docker or Kubernetes, an orchestrator can pass process arguments as a list. Ensure each option is a clean string:

~~~text
--spring.profiles.active=prod
--app.batch-size=500
import
/data/customers.csv
~~~

Do not manually add literal quote characters inside array elements if the platform already accepts a string array. For secrets, use a secrets management mechanism instead of passing passwords on the command line.

## 20. When to use options vs. positional arguments?

The choice should start from **data semantics**.

| Need | Suggested representation | Reason |
| --- | --- | --- |
| HTTP port, profile, log level | `--server.port=9090` | Spring Boot configuration property. |
| Named application value overridable by other sources | `--app.batch-size=300` | Easy to access via `Environment` or `@ConfigurationProperties`. |
| Specifying a business action | `import` | Meaningful positional keyword by CLI convention. |
| Input path following job name | `customers.csv` | Simple when position is unambiguous. |
| Specifying path independent of position | `--input=customers.csv` | Key name clarifies intent. |
| Flag only needing presence on/off | `--dry-run` | Read via `containsOption(...)`. |
| Boolean intended for configuration binding | `--app.dry-run=true` | Carries explicit Boolean value. |

A good CLI design clearly documents **accepted syntax**, **required values**, **default values**, **error reporting**, and **handling of repeated options**.

For example, for an import tool:

~~~text
Usage:
  importer.jar [options] import <file>

Options:
  --app.batch-size=<positive-integer>
  --app.mode=<safe|fast>
  --dry-run
~~~

This is a readable input contract. Cases like missing files, missing values, or invalid batch sizes can all fail with explicit errors.

## 21. Common mistakes and how to recognize them

### Mistake 1: Missing double dashes

~~~bash
java -jar demo.jar app.mode=fast
~~~

`app.mode=fast` is a non-option. If you want to override a property in `Environment`, use:

~~~bash
java -jar demo.jar --app.mode=fast
~~~

### Mistake 2: Splitting key and value into two arguments

~~~bash
java -jar demo.jar --app.mode fast
~~~

`fast` is a non-option. Use `--app.mode=fast`.

### Mistake 3: Placing -D after the JAR name

~~~bash
java -jar demo.jar -Dapp.mode=fast
~~~

`-Dapp.mode=fast` is now application input and not a JVM option in a valid position. Use:

~~~bash
java -Dapp.mode=fast -jar demo.jar
~~~

### Mistake 4: Reading a non-option with @Value

~~~bash
java -jar demo.jar import customers.csv
~~~

`customers.csv` does not become a property automatically. Read it with `ApplicationArguments.getNonOptionArgs()`.

### Mistake 5: Assuming --flag has value true

An option without a value can be detected via `containsOption("flag")`. If you want to configure a Boolean in `@ConfigurationProperties`, explicitly pass `--app.flag=true` or `--app.flag=false`.

### Mistake 6: Assuming an option is used automatically

Passing `--app.some-key=abc` into an application does not make Spring Boot create a feature named `some-key`. It merely supplies a property; application code or a configuration component must consume that property.

### Mistake 7: Not handling repeated options

~~~bash
java -jar demo.jar --tag=a --tag=b
~~~

`ApplicationArguments` provides multiple values. If business logic requires exactly one, report an error; if multiple are allowed, process the list. Do not pick the first or last arbitrarily without a rule.

### Mistake 8: Forgetting quotes when a value contains spaces

~~~bash
java -jar demo.jar --app.message=Hello world
~~~

The shell may split it into an option `--app.message=Hello` and a non-option `world`. Use:

~~~bash
java -jar demo.jar --app.message="Hello world"
~~~

### Mistake 9: Using the command line to pass secret data

Process arguments can appear in process inspection tools, runtime logs, or command history. Avoid passing tokens, passwords, or secret keys directly in `--password=...`. Use infrastructure secrets solutions, restrict read access, and never log sensitive data from `ApplicationArguments`.

### Mistake 10: Thinking setAddCommandLineProperties(false) erases args

Disabling the command-line property source does not delete arguments passed to the application. `ApplicationArguments` remains the right tool to read business command inputs.

### Mistake 11: Confusing configuration docs with a full CLI framework

Spring Boot provides option and property classification. It does not automatically build `--help`, validate all required operands, suggest subcommands, format usage messages, or recover from missing files per business rules. Those requirements belong to your application CLI design or an integrated CLI library.

## 22. Practice: observing how Spring classifies arguments

Create a Spring Boot application with a runner:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
class ArgumentExplorer implements ApplicationRunner {
    private final Environment environment;

    ArgumentExplorer(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("RAW: " +
                Arrays.toString(args.getSourceArgs()));
        System.out.println("OPTIONS: " + args.getOptionNames());
        System.out.println("NON_OPTIONS: " + args.getNonOptionArgs());

        System.out.println("app.mode values: " +
                args.getOptionValues("app.mode"));

        System.out.println("effective app.mode: " +
                environment.getProperty("app.mode", "(missing)"));
    }
}
~~~

Use the file:

~~~properties
app.mode=default
~~~

### Exercise 1: passing a valid option

~~~bash
java -jar demo.jar --app.mode=fast import file.csv
~~~

Prediction:

- `getOptionValues("app.mode")` returns a single-element list `fast`.
- `getNonOptionArgs()` returns `["import", "file.csv"]`.
- `Environment.getProperty("app.mode")` gets `fast` by normal rules.

### Exercise 2: missing --

~~~bash
java -jar demo.jar app.mode=fast import file.csv
~~~

Prediction:

- The option list does not contain `app.mode`.
- Non-options are `["app.mode=fast", "import", "file.csv"]`.
- The value of `app.mode` from the file remains `default`.

### Exercise 3: missing equals sign

~~~bash
java -jar demo.jar --app.mode fast import file.csv
~~~

Prediction:

- `containsOption("app.mode")` is `true`.
- `getOptionValues("app.mode")` is an empty list.
- Non-options are `["fast", "import", "file.csv"]`.
- No CLI value `fast` is assigned to `app.mode` from this string.

### Exercise 4: comparing sources

~~~bash
java -Dapp.mode=system -jar demo.jar --app.mode=cli import file.csv
~~~

Prediction:

- `System.getProperty("app.mode")` is `system`.
- `getOptionValues("app.mode")` contains `cli`.
- `Environment.getProperty("app.mode")` is `cli` in a default run.

### Exercise 5: duplicate option names

~~~bash
java -jar demo.jar --tag=one --tag=two export result.csv
~~~

Prediction:

- `getOptionValues("tag")` contains two elements: `one` and `two`.
- `getNonOptionArgs()` contains `export` and `result.csv`.
- The application decides whether to accept multiple tags or report an error.

### Exercise 6: disabling the command-line source

In the launcher class, use `setAddCommandLineProperties(false)` and run:

~~~bash
java -jar demo.jar --app.mode=cli
~~~

Observe that `ApplicationArguments.getOptionValues("app.mode")` still contains `cli`, yet `Environment` no longer receives that override through the default CLI source. If the file still has `app.mode=default`, the effective value from the file will be `default` when no other source overrides it.

### Exercise 7: combining options and non-options

Design the command:

~~~bash
java -jar demo.jar --spring.profiles.active=dev --app.batch-size=150 --dry-run import "input data.csv"
~~~

Classify each string and explain:

- Why does `spring.profiles.active` take effect during startup?
- Why can `app.batch-size` be read via `@ConfigurationProperties`?
- Why does `--dry-run` fit `containsOption("dry-run")`?
- Why must `import` and `input data.csv` be read from `getNonOptionArgs()`?

Answer: the three strings starting with `--` are options; `import` and `input data.csv` are non-options. Configuration options can enter `Environment`; a flag needing only presence detection is checked via `ApplicationArguments`; the two non-options carry the business request according to application convention.

## 23. Summary table: predicting destination from syntax

| Input supplied | Handled by JVM or received by SpringApplication? | Where to read? |
| --- | --- | --- |
| `-Dapp.mode=fast` before `-jar` | JVM processes into System property. | `System.getProperty(...)`, `Environment`. |
| `--app.mode=fast` after JAR | SpringApplication receives as option. | `ApplicationArguments`; by default also `Environment`. |
| `--dry-run` after JAR | SpringApplication receives as valueless option. | `ApplicationArguments.containsOption(...)`. |
| `app.mode=fast` after JAR | Application receives as non-option. | `ApplicationArguments.getNonOptionArgs()`. |
| `import` after JAR | Application receives as non-option. | `ApplicationArguments.getNonOptionArgs()`. |
| `APP_MODE=fast` supplied by OS | Process environment variable. | `System.getenv(...)`; `Environment` via mapping. |
| `app.mode=fast` in application.properties | Config Data loaded from file. | `Environment`; `@Value`; `@ConfigurationProperties`. |

In short, **argument syntax and position determine how Spring Boot handles it**. `--key=value` supplies a named option, converted by default into a configuration property; regular arguments serve as business inputs and are read from `ApplicationArguments`. `-Dkey=value` is a JVM mechanism, while environment variables belong to the OS; all can influence final configuration yet are not the same kind of input.

When building a CLI tool with Spring Boot, clearly separate three things: **application configuration**, **command control flags**, and **positional business arguments**. Using the right API for each makes launching easy to understand, error handling transparent, and prevents accidental configuration overrides.

## References

- [Spring Boot 3.3 — Externalized Configuration: Accessing Command Line Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
- [Spring Boot 3.3 — SpringApplication: Accessing Application Arguments](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html).
- [Spring Boot — ApplicationArguments API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationArguments.html).
