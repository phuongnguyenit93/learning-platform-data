# Architecture of ApplicationArguments and DefaultApplicationArguments in Spring Boot

## 1. Overview: how do arguments flow from main to the application?

When running a Spring Boot application with Java, the `main(String[] args)` method receives the **application arguments** passed after the JAR name or main class. `SpringApplication.run(..., args)` receives that array to start the application. Spring Boot provides a structured abstraction named **`ApplicationArguments`** so beans can read back the **raw argument strings**, **option arguments**, and **non-option arguments** without having to parse strings manually by splitting characters.

`DefaultApplicationArguments` is the **default implementation** of the `ApplicationArguments` interface. It accepts `String... args`, preserves access to the source arguments, and builds a parsed representation for option/non-option arguments. In a typical Spring Boot application, you only need to inject the **`ApplicationArguments` interface**; there is no need to instantiate a `DefaultApplicationArguments` yourself in every bean.

~~~mermaid
flowchart TD
  OS["Startup command / terminal"] --> MAIN["main(String[] args)"]
  MAIN --> RUN["SpringApplication.run(App.class, args)"]
  RUN --> PARSE["DefaultApplicationArguments"]
  PARSE --> RAW["getSourceArgs(): raw String[]"]
  PARSE --> OPT["Option args: --key=value, --flag"]
  PARSE --> NON["Non-option args: file.csv, import"]
  RUN --> ENV["CommandLinePropertySource in Environment (default)"]
  PARSE --> BEAN["ApplicationArguments bean"]
  BEAN --> AR["ApplicationRunner.run(ApplicationArguments)"]
  BEAN --> INJECT["Constructor injection into any bean"]
~~~

This diagram illustrates the logical data flow; it does not assert that every node is a separate thread or bean. `ApplicationArguments` and `CommandLinePropertySource` use arguments from the same source, but have different APIs and purposes.

### Three typical cases

~~~bash
java -jar app.jar --spring.profiles.active=dev --debug input.csv
~~~

- `--spring.profiles.active=dev`: an option named `spring.profiles.active`, with value `dev`.
- `--debug`: a **flag** option, present but **not supplied with a value**.
- `input.csv`: a non-option/positional argument.
- `getSourceArgs()` returns the entire original string array in exact order, not just the recognized options.

Do not confuse `-Dspring.profiles.active=dev` with `--spring.profiles.active=dev`. The `-D...` form is a **JVM system property** when placed before `-jar`; it is not an application argument in `String[] args`. The `--...` form placed after the JAR is passed to the application.

## 2. ApplicationArguments: interface contract

The `org.springframework.boot.ApplicationArguments` interface describes the operations code can perform on the arguments of a `SpringApplication` run.

| API | Return Type | Purpose |
| --- | --- | --- |
| `getSourceArgs()` | `String[]` | The **raw** argument array, not transformed into options |
| `getOptionNames()` | `Set<String>` | Set of option names recognized by the parser |
| `containsOption(String name)` | `boolean` | Checks whether an option is present |
| `getOptionValues(String name)` | `List<String>` or `null` | Gets the list of values for an option, supporting repeated occurrences of the same name |
| `getNonOptionArgs()` | `List<String>` | Arguments that do not belong to the option group |

These methods do not execute business logic. They return data from parsing arguments so that a service/runner can decide how to behave.

### 2.1 getSourceArgs(): preserving input order

For example, passing exactly four application arguments:

~~~bash
java -jar app.jar --region=vn --dry-run --region=sg orders.csv
~~~

The corresponding value of `getSourceArgs()`:

~~~text
[--region=vn, --dry-run, --region=sg, orders.csv]
~~~

The array has **four elements** after the JAR name. In Java code, it can be printed with:

~~~java
System.out.println(java.util.Arrays.toString(
        arguments.getSourceArgs()));
~~~

`getSourceArgs()` lets you store or inspect source tokens, including tokens not mapped to properties. However, you should not dump this array to production logs if operators might pass tokens, passwords, access keys, or private data via the CLI.

### 2.2 getOptionNames(): a set of names, not a list of values

From the previous command, the option names are `region` and `dry-run`. Because `getOptionNames()` returns a `Set`, do not rely on iteration order in tests or output. If deterministic output is needed:

~~~java
System.out.println(new java.util.TreeSet<>(
        arguments.getOptionNames()));
~~~

Corresponding output:

~~~text
[dry-run, region]
~~~

Repeating `--region=...` does not produce two `region` entries in the name set; option values are held separately via `getOptionValues(...)`.

### 2.3 containsOption(): checking flag presence

~~~java
boolean dryRun = arguments.containsOption("dry-run");
~~~

When the command has `--dry-run`, the expression is `true` even without `=true`. This is the appropriate way to check a **present/absent flag**.

Do not assume `containsOption("dry-run")` checks whether a string value can be converted to a boolean. If the user passes `--dry-run=false`, the option is **still present**, so `containsOption("dry-run")` still evaluates to `true`; to interpret the false value, you must read `getOptionValues("dry-run")` or bind to a typed configuration according to the appropriate rules.

### 2.4 getOptionValues(): three states that must be handled properly

The `ApplicationArguments` Javadoc specifies three important cases:

| Command Line | `containsOption("mode")` | `getOptionValues("mode")` |
| --- | --- | --- |
| No `--mode` | `false` | `null` |
| `--mode` | `true` | Empty list `[]` |
| `--mode=fast` | `true` | Single-element list `["fast"]` |
| `--mode=fast --mode=safe` | `true` | Two-element list `["fast", "safe"]` |
| `--mode=` | `true` | List with **one empty string** `[""]` |

The last case is especially easy to misinterpret: `List.of("").toString()` also prints like `[]` because an empty string does not visibly render between brackets. Therefore, do **not** rely solely on `toString()` output to distinguish a `--mode` flag from `--mode=`. Checking `size()` and `get(0).isEmpty()` is clearer.

~~~java
import java.util.List;

List<String> modes = arguments.getOptionValues("mode");

if (modes == null) {
    System.out.println("mode option is absent");
} else if (modes.isEmpty()) {
    System.out.println("mode is a flag without a value");
} else if (modes.get(0).isEmpty()) {
    System.out.println("mode has an explicitly empty value");
} else {
    System.out.println("first mode value=" + modes.get(0));
}
~~~

This is an illustrative snippet inside a method receiving an `arguments` variable of type `ApplicationArguments`, not a standalone Java file. When an option is repeated multiple times, you must decide the business policy: accept only one value, accept a list, or report an error. Do **not** arbitrarily pick "last value wins" for every use case unless the specification defines it.

### 2.5 getNonOptionArgs(): positional arguments

An argument that does not start in option form `--name` or `--name=value` is normally classified by the parser into the non-option group. For example:

~~~bash
java -jar app.jar --format=csv import customers.csv
~~~

~~~text
getNonOptionArgs() => [import, customers.csv]
~~~

This is the basis for designing simple CLI applications such as `import`, `export`, input file paths, or task names. This parser does not itself provide a positional schema, validate extensions, or check whether files exist; that is the responsibility of application code.

## 3. DefaultApplicationArguments: implementation and how it parses

`org.springframework.boot.DefaultApplicationArguments` implements `ApplicationArguments` and has the constructor:

~~~java
public DefaultApplicationArguments(String... args)
~~~

It is suitable for **unit tests**, components that need to parse an argument array for their own purposes, or demonstrating the contract. During a normal `SpringApplication` run, Boot provides an `ApplicationArguments` bean corresponding to the args passed to `run(...)`. Depend on the interface when writing services/runners, avoiding locking application code into implementation details.

### Creating the parser manually outside the context

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

ApplicationArguments parsed = new DefaultApplicationArguments(
        "--user=Lan",
        "--tag=red",
        "--tag=blue",
        "--dry-run",
        "orders.csv"
);

System.out.println(parsed.containsOption("dry-run"));
System.out.println(parsed.getOptionValues("tag"));
System.out.println(parsed.getNonOptionArgs());
~~~

These lines reside inside a method or unit test. Output:

~~~text
true
[red, blue]
[orders.csv]
~~~

**Important:** creating `new DefaultApplicationArguments(...)` only creates a Java object that parses strings; it **does not start Spring Boot**, **does not modify `Environment`**, and **does not automatically become the `ApplicationArguments` bean** in the running context.

### Relationship with Spring Framework command-line parsing

The default implementation leverages Spring Framework's option-parsing functionality, related to `SimpleCommandLinePropertySource`/command-line parser components. Observed rules:

- An option has the form `--optionName` or `--optionName=value`.
- The value must be in the same token, joined by `=`, with no space between the name and the equals sign.
- `--name=Lan` is an option with a value; `--name Lan` consists of an option `name` **with no value**, while `Lan` is a non-option.
- `--list=red,blue` is **one** value string `"red,blue"` in `getOptionValues("list")`; the `ApplicationArguments` parser does not split it into two elements by default just because of the comma.
- `--list=red --list=blue` produces **two** values for the same option.
- `--flag` is an option with no value; `--flag=` has one empty value.
- A standalone `--` token marks the end of options according to the Spring Framework parser: tokens after it are treated as non-options, even tokens that look like `--key=value`.
- A mistyped token like `-mode=fast` is not treated as an option named `mode` under the `--` syntax; check non-options rather than assuming it becomes a property.

This is a simple parser, not a full-featured CLI library with subcommands, auto-completion, type validation, and usage help. If you need a large CLI application, you can use a dedicated library like Picocli and integrate it appropriately into the Boot lifecycle, without confusing a custom parser with the default contract of `ApplicationArguments`.

### Assumptions to avoid in code

1. **Do not assume `Set` order:** option names are returned in a `Set<String>`, with no contract to preserve CLI order.
2. **Do not assume a single value:** the same option may appear multiple times.
3. **Do not assume an absent option is an empty list:** absent returns `null`.
4. **Do not assume a flag implies boolean `true`:** a flag only indicates presence; choosing boolean semantics is a code decision.
5. **Do not assume a non-option is a valid file path:** the parser only classifies tokens.
6. **Do not assume options are converted to data types:** `getOptionValues` returns strings; parsing integers/dates/enums must be done by the application or delegated to a `Binder` with validation.
7. **Do not assume instantiating `DefaultApplicationArguments` again changes Spring `Environment` values:** these are two separate API paths.

## 4. How ApplicationArguments differs from Environment and JVM arguments

Each layer of data has a distinct purpose:

| Source or API | Where it comes from | How to inspect it | Example |
| --- | --- | --- | --- |
| `String[] args` in `main` | Tokens after main class/JAR | Directly in Java | `--app.mode=dev` |
| `ApplicationArguments` | Args passed to `SpringApplication.run` | `containsOption`, `getOptionValues`, `getNonOptionArgs` | `--tag=alpha` |
| `DefaultApplicationArguments` | `String... args` passed to constructor | `ApplicationArguments` API | Creating parser in tests |
| `Environment` | Merges multiple `PropertySource`s | `getProperty(key)` | `app.mode` value from CLI/YAML/OS/JVM |
| Java system properties | `-Dname=value` on JVM before `-jar` | `System.getProperty(name)` / `Environment` | `-Dapp.mode=dev` |
| OS environment variables | Process environment | `System.getenv(name)` / `Environment` | `APP_MODE=dev` |
| Spring config data | `application.yaml`/`application.properties` and profile-specific files | `Environment`, `@ConfigurationProperties` | `app.mode: production` |

By default, Spring Boot turns command-line options of the form `--key=value` into Spring properties in `Environment` via `CommandLinePropertySource`. This source typically has higher precedence than application config files. For example:

~~~yaml
# src/main/resources/application.yaml
app:
  mode: "configured"
~~~

~~~bash
java -jar app.jar --app.mode=cli
~~~

With Boot's defaults, `environment.getProperty("app.mode")` returns `"cli"`. At the same time, `ApplicationArguments.getOptionValues("app.mode")` contains `["cli"]`. Both paths yield corresponding values in this simple case, yet their APIs differ.

### What happens when the command-line PropertySource is disabled?

You can customize `SpringApplication` before `run`:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

This snippet requires an appropriate `MyApplication` class. With the flag set to `false`:
- `ApplicationArguments` **still parses and retains** the passed args.
- Spring Boot **no longer automatically adds** the default command-line `PropertySource` to `Environment`.
- If relying solely on `--app.mode=cli`, `environment.getProperty("app.mode")` will not necessarily be `cli`; it may come from YAML, OS env, JVM properties, or another source.
- Likewise, `--spring.profiles.active=dev` is no longer automatically added to `Environment` via the usual CLI mechanism, so you must not assume the `dev` profile becomes active just because that token exists.

This is the clearest verification that **`ApplicationArguments` is not identical to `Environment`**.

### Java command: ordering of -D and --key=value

~~~bash
# JVM property must appear before -jar.
java -Dapp.mode=jvm -jar app.jar

# Application argument appears after the JAR name.
java -jar app.jar --app.mode=cli
~~~

The first example can be read via `System.getProperty("app.mode")`. In the second example, `System.getProperty("app.mode")` is not automatically added by the JVM just because a CLI option is present, whereas Spring's `Environment` can read it through the command-line `PropertySource`.

### Why might getOptionValues and Environment not have the same meaning?

`getOptionValues("tag")` can return a list of multiple values, whereas `Environment.getProperty("tag")` is a single property string that has gone through the `PropertySource` mechanism with its own representation and precedence rules. If the application needs to **preserve exact repeated values and order**, use `ApplicationArguments`. If the application needs **typed configuration, defaults, and precedence order**, prefer `@ConfigurationProperties`/Binder or `Environment`.

Do not use `Environment` to fetch arbitrary non-option tokens. By default, positional tokens do not automatically become Spring properties with names you invent.

## 5. Injecting ApplicationArguments into beans and runners

### Constructor injection

Spring Boot registers `ApplicationArguments` as a bean so components can receive it via constructor:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.stereotype.Component;

@Component
class ImportOptions {
    private final ApplicationArguments arguments;

    ImportOptions(ApplicationArguments arguments) {
        this.arguments = arguments;
    }

    boolean dryRun() {
        return arguments.containsOption("dry-run");
    }
}
~~~

A component can access args as soon as it is created. However, you should avoid running heavy business tasks in the constructor; only store dependencies or perform lightweight validation as appropriate.

### ApplicationRunner and CommandLineRunner

These two runner types execute in the late stage of startup, after `ApplicationContext` is refreshed and before `ApplicationReadyEvent` (on the successful startup path).

| Interface | Method | Argument received | When to use |
| --- | --- | --- | --- |
| `ApplicationRunner` | `run(ApplicationArguments args)` | Raw and parsed arguments via the interface | When you want to read option/non-option args in a structured way |
| `CommandLineRunner` | `run(String... args)` | Raw string argument array | When you want to process raw tokens yourself or pass them to another parser |

Skeleton examples:

~~~java
@Bean
ApplicationRunner parsedArgumentsTask() {
    return args -> {
        System.out.println(args.containsOption("dry-run"));
    };
}
~~~

~~~java
@Bean
CommandLineRunner rawArgumentsTask() {
    return args -> {
        System.out.println(java.util.Arrays.toString(args));
    };
}
~~~

These two snippets are **two illustrative options** placed inside a `@Configuration` or `@SpringBootApplication` class with `@Bean` and the corresponding interfaces imported; they are not two complete programs. If you use multiple runners and need ordering, configure `@Order` or `Ordered` as required; do not rely on arbitrary bean iteration order. An exception from a runner can cause startup to fail before the ready milestone.

### Do not instantiate DefaultApplicationArguments yourself when Boot already provides it

Code like:

~~~java
new DefaultApplicationArguments("--mode=fixed");
~~~

only creates a new parser containing the `--mode=fixed` argument. It cannot be used to "replace" the args Boot passed into the `ApplicationArguments` bean, nor does it alter the command-line properties already processed for the current context.

If you need to parse a subset of tokens with custom logic, creating a parser manually may make sense. If you only need the current startup's data, inject `ApplicationArguments`. This principle keeps code testable, consistent, and cleanly separated in responsibility.

## 6. Complete Spring Boot example, Java 17+, Maven

This example focuses on observing the `ApplicationArguments` structure and requires no web server. It uses Spring Boot 3.5.16 and Java 17+ with the foundational starter.

Create the files:

~~~text
args-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/args/ArgsDemoApplication.java
    └── resources/application.yaml
~~~

### File pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>args-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
~~~

### File src/main/resources/application.yaml

~~~yaml
spring:
  application:
    name: args-demo
  main:
    banner-mode: "off"

app:
  mode: "from-yaml"
~~~

The `app.mode` section demonstrates that a command-line option can override YAML through `Environment`.

### File src/main/java/com/example/args/ArgsDemoApplication.java

~~~java
package com.example.args;

import java.util.Arrays;
import java.util.List;
import java.util.TreeSet;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ArgsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ArgsDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showArguments(
            ApplicationArguments injectedArguments,
            Environment environment) {

        return parsed -> {
            System.out.println(
                    "source=" + Arrays.toString(parsed.getSourceArgs()));
            System.out.println(
                    "names=" + new TreeSet<>(parsed.getOptionNames()));
            System.out.println(
                    "verbosePresent="
                            + parsed.containsOption("verbose"));
            System.out.println(
                    "verboseValues="
                            + parsed.getOptionValues("verbose"));
            System.out.println(
                    "tags=" + parsed.getOptionValues("tag"));
            System.out.println(
                    "missing=" + parsed.getOptionValues("missing"));
            System.out.println(
                    "nonOptions=" + parsed.getNonOptionArgs());
            System.out.println(
                    "injectedSource="
                            + Arrays.toString(
                                    injectedArguments.getSourceArgs()));
            System.out.println(
                    "modeFromEnv="
                            + environment.getProperty("app.mode", "none"));

            List<String> tagValues = parsed.getOptionValues("tag");
            System.out.println(
                    "tagCount="
                            + (tagValues == null ? 0 : tagValues.size()));
        };
    }
}
~~~

**Why does this code work?**

- `@SpringBootApplication` enables component scanning and basic auto-configuration.
- `@Bean` registers an `ApplicationRunner` whose factory method receives two dependencies managed by Boot/the context: `ApplicationArguments` and `Environment`.
- Inside the runner lambda, `parsed` is the `ApplicationArguments` passed directly by Boot via the interface. `injectedArguments` also accesses the startup arguments of that same run.
- `TreeSet` is used solely to sort option names before printing, avoiding assumptions about `Set` order.
- `getOptionValues("missing")` is printed directly to illustrate the `null` value when an option is absent.
- `app.mode` has a fallback value in YAML, but when passed from the CLI, `Environment` can pick the CLI value with higher precedence.

### Build and run

In the `args-demo` directory:

~~~bash
mvn -q -DskipTests package
java -jar target/args-demo-0.0.1-SNAPSHOT.jar \
  --app.mode=cli \
  --verbose \
  --tag=alpha \
  --tag=beta \
  import.csv
~~~

The `\` line continuation only applies to Bash/Unix-style shells. On Windows PowerShell or cmd, you can put the entire `java -jar...` command on **one line**. The JAR name matches the version/artifact in `pom.xml` above.

**Lines printed by `showArguments`** in the exact order of the example:

~~~text
source=[--app.mode=cli, --verbose, --tag=alpha, --tag=beta, import.csv]
names=[app.mode, tag, verbose]
verbosePresent=true
verboseValues=[]
tags=[alpha, beta]
missing=null
nonOptions=[import.csv]
injectedSource=[--app.mode=cli, --verbose, --tag=alpha, --tag=beta, import.csv]
modeFromEnv=cli
tagCount=2
~~~

Spring Boot may still emit startup logs; the block above **only** lists the runner's output, not asserting that all of stdout contains only these lines.

Line-by-line explanation:
1. `source` contains the exact **five** application arguments following the JAR name: mode, verbose, two tags, and the filename.
2. `names` is sorted by option name. `import.csv` is not an option name.
3. `verbosePresent=true` because `--verbose` is present, even without an equals sign.
4. `verboseValues=[]` is a **zero-element** list for an option without a value.
5. `tags` has two elements from the two `--tag=...` occurrences.
6. `missing=null` because no `--missing` option was provided.
7. `nonOptions` contains the positional argument `import.csv`.
8. `injectedSource` shows that the injected `ApplicationArguments` bean uses the same startup data.
9. `modeFromEnv=cli` shows that the command-line `PropertySource` overrides `app.mode: from-yaml` by default.
10. `tagCount=2` confirms that repeated options with the same name are kept as a list without losing elements when accessed via the parsed API.

### Running with no options

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar
~~~

Key lines:

~~~text
source=[]
names=[]
verbosePresent=false
verboseValues=null
tags=null
missing=null
nonOptions=[]
injectedSource=[]
modeFromEnv=from-yaml
tagCount=0
~~~

Without the `--verbose` option, `getOptionValues("verbose")` returns **null**, unlike `verboseValues=[]` in the run with the flag. This is a distinction worth writing tests for.

### Running with empty values and a non-option after options

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar \
  --verbose= \
  --tag= \
  report.csv
~~~

In this example:
- `containsOption("verbose")` equals `true`.
- `getOptionValues("verbose")` is a **single-element** list, where that element is an empty string.
- `getOptionValues("tag")` also contains one empty string, so `tagCount=1`.
- `getNonOptionArgs()` is `[report.csv]`.

If you only print `verboseValues` or `tags` via `List.toString()`, an empty string is not visually shown; therefore looking like `[]` is not enough to conclude the list is empty. To distinguish them, check `size()`.

## 7. Unit testing DefaultApplicationArguments without a Spring context

One benefit of `DefaultApplicationArguments` is that you can test the parser directly without starting Spring Boot. Add the test dependency in `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

This block goes **inside `<dependencies>`** of the existing POM. It adds JUnit Jupiter and testing utilities managed by the starter.

Create `src/test/java/com/example/args/ArgumentsParsingTest.java`:

~~~java
package com.example.args;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.*;

class ArgumentsParsingTest {

    @Test
    void parsesRepeatedValuesFlagsAndPositionalArgs() {
        ApplicationArguments a = new DefaultApplicationArguments(
                "--region=vn",
                "--region=sg",
                "--dry-run",
                "orders.csv");

        assertArrayEquals(
                new String[] {
                    "--region=vn",
                    "--region=sg",
                    "--dry-run",
                    "orders.csv"
                },
                a.getSourceArgs());

        assertEquals(
                Set.of("region", "dry-run"),
                a.getOptionNames());

        assertEquals(
                List.of("vn", "sg"),
                a.getOptionValues("region"));

        assertTrue(a.containsOption("dry-run"));
        assertNotNull(a.getOptionValues("dry-run"));
        assertTrue(a.getOptionValues("dry-run").isEmpty());

        assertNull(a.getOptionValues("absent"));
        assertEquals(List.of("orders.csv"), a.getNonOptionArgs());
    }

    @Test
    void distinguishesEmptyStringFromNoValue() {
        ApplicationArguments a = new DefaultApplicationArguments(
                "--empty=",
                "--flag");

        assertTrue(a.containsOption("empty"));
        assertEquals(1, a.getOptionValues("empty").size());
        assertEquals("", a.getOptionValues("empty").get(0));

        assertTrue(a.containsOption("flag"));
        assertEquals(0, a.getOptionValues("flag").size());
    }

    @Test
    void separateTokenIsNotAutomaticallyOptionValue() {
        ApplicationArguments a = new DefaultApplicationArguments(
                "--name",
                "Lan");

        assertTrue(a.containsOption("name"));
        assertTrue(a.getOptionValues("name").isEmpty());
        assertEquals(List.of("Lan"), a.getNonOptionArgs());
    }
}
~~~

Run:

~~~bash
mvn test
~~~

With Spring Boot Starter Test and a compatible Java version, the three JUnit tests express expectations on the parser. `assertEquals(Set.of(...), a.getOptionNames())` is order-independent because it compares two `Set`s. In contrast, `List.of("vn","sg")` intentionally verifies the order of the two option values.

**Note:** this is a unit test for `DefaultApplicationArguments`, not a test that all `PropertySource`s are prepared or all profiles are active. To test interaction with `Environment` and config data, a corresponding Spring Boot startup/integration test is needed.

## 8. Token classification rules: quick reference examples

| Input Token | Parser Group | Observed Behavior |
| --- | --- | --- |
| `--debug` | Option | Name `debug` present; empty value list |
| `--debug=true` | Option | Name `debug`; list `["true"]` |
| `--debug=false` | Option | Name `debug` still present; list `["false"]` |
| `--port=8081` | Option | Name `port`; list `["8081"]`; not yet an integer in `ApplicationArguments` |
| `--port=` | Option | Name `port`; one empty string |
| `--item=a --item=b` | Two occurrences of same option | `getOptionValues("item")` is `["a", "b"]` |
| `--item=a,b` | One option | `getOptionValues("item")` is `["a,b"]` |
| `--item a` | Option + positional | `item` has no value, `a` is a non-option |
| `--help` | Option | Just a flag; Boot does not auto-build command usage help for every app |
| `input.txt` | Non-option | Element in `getNonOptionArgs()` |
| `-Dmy.flag=on` before `-jar` | JVM option | Java system property; not part of `String[] args` |
| `--` | End-of-options marker | Following tokens are treated as non-options by the parser |

**Do not confuse parsed options with typed binding.** The parser provides strings. If you want to verify `--port=abc` is a valid port number, the application must parse/validate it or use Spring's binding mechanism with validation support. Errors from invalid type parsing in business logic differ from parser syntax errors.

### When an option has multiple values

Common handling strategies:
- **Single-value strict:** throw an error when the list has more than one value.
- **List-value:** accept repeated options and process the whole list in order of appearance.
- **Last-value override:** take only the last element **only if the application's CLI contract** explicitly specifies it.
- **Optional flag:** use `containsOption` without requiring a value; if the user types `--flag=false`, check semantics carefully because `containsOption` is still true.

Single-value strict example, handling null/empty/multiple itself:

~~~java
static String requireSingleValue(
        ApplicationArguments args, String name) {

    List<String> values = args.getOptionValues(name);

    if (values == null || values.isEmpty()) {
        throw new IllegalArgumentException(
                "Missing option value: --" + name);
    }
    if (values.size() != 1) {
        throw new IllegalArgumentException(
                "Expected exactly one value for --" + name);
    }
    if (values.get(0).isBlank()) {
        throw new IllegalArgumentException(
                "Blank value is not allowed: --" + name);
    }
    return values.get(0);
}
~~~

This is a **method** to place inside a class and import `ApplicationArguments`/`List`; usable on Java 17. It does not distinguish absent vs. flag in the message because both are considered missing a value, by design for a required option. If detailed error reporting is needed, separate the two cases.

## 9. Common mistakes and how to fix them

### Passing --debug causes getOptionValues("debug").get(0) to throw

`--debug` is an option **without a value**, so `getOptionValues("debug")` returns an empty list. Use `containsOption("debug")` if this is a flag, or require users to pass `--debug=true` if the design needs a value.

### Omitting --mode causes getOptionValues("mode").isEmpty() to throw NullPointerException

An absent option has `getOptionValues(...) == null`. Check for null first, then check empty. Unit tests should cover absent, flag, and explicitly empty value.

### Passing --mode fast does not make the application see fast as the value

The parser's option-value syntax is `--mode=fast`. The two tokens `--mode` and `fast` are not equivalent: `fast` is a non-option. Use an equals sign with no spaces between the name and the value.

### Two --tag options provided, but only one value is retrieved

If code uses `getOptionValues("tag").get(0)`, it silently discards subsequent values. The API can return **multiple** elements; you must decide whether to accept repeats, deduplicate, or report an error.

### JVM -D does not appear in getSourceArgs()

`-D...` is a JVM option and must appear before `-jar` or the main class for the JVM to process it. To read a JVM property, use `System.getProperty(...)`/`Environment`. To pass data via `ApplicationArguments`, use `--...` after the JAR name.

### application.yaml has a different value than getOptionValues

`ApplicationArguments` reflects the **CLI args** of the run, not an aggregation of all config sources. `Environment` merges CLI, files, OS environment, and JVM system properties with its own precedence order. If a CLI option is absent while YAML has the key, `getOptionValues(key)` can still be `null`, whereas `Environment.getProperty(key)` has a value.

### Not receiving CLI options in Environment

Check whether the application calls `setAddCommandLineProperties(false)`, passes the right args to `SpringApplication.run`, and formats options as `--key=value`. Also check that the key being read matches the exact name and appropriate property source.

### Runner does not see args even though main received them

A basic mistake is forgetting to pass `args`:

~~~java
// Wrong if you want to pass arguments from main to Boot:
SpringApplication.run(ArgsDemoApplication.class);
~~~

Fix:

~~~java
SpringApplication.run(ArgsDemoApplication.class, args);
~~~

When calling without passing `args`, Boot sees an empty argument array from that `run` call. Do not fetch CLI info elsewhere in the runner and treat that as the standard contract.

### getOptionNames() changes order across test runs

`Set` does not guarantee CLI order. Tests should compare sets of elements, or sort when stable display output is needed. In the runnable example, `new TreeSet<>(...)` is used to guarantee alphabetical order.

### Logging passwords and causing leaks

`getSourceArgs()` returns raw strings, which may contain secrets from operators. Do not log all arguments in production, and avoid passing access tokens in shell commands when a secret manager or safer mechanism can be used. When debugging, print only option names or appropriately masked values.

### Putting heavy tasks in a constructor just to read args

Reading `ApplicationArguments` via constructor works, but you should not run an entire I/O job inside a constructor. For work requiring a refreshed context, use `ApplicationRunner` or `CommandLineRunner`. Remember that runners execute before `ApplicationReadyEvent` and can delay readiness.

## 10. Real-world application scenarios

### Data import CLI

An ETL application might receive:

~~~bash
java -jar etl.jar --source=customers.csv --dry-run
~~~

- `getOptionValues("source")` retrieves the input path.
- `containsOption("dry-run")` signals check-only mode without writing.
- Business logic validates the path, read permissions, and CSV structure; the parser does not do this for you.
- If `source` is required, use a validation method like `requireSingleValue` above.

### Selecting a Spring profile at runtime

~~~bash
java -jar app.jar --spring.profiles.active=dev
~~~

`ApplicationArguments` still receives the `spring.profiles.active` option. By Boot's defaults, CLI properties are added to `Environment` early enough for the system to select profiles and load matching config data. However, if `setAddCommandLineProperties(false)` is set, do not assume a token in `ApplicationArguments` still automatically activates the profile.

### Passing a series of tags

~~~bash
java -jar app.jar --tag=blue --tag=green --tag=red
~~~

If the API expects a list, read `getOptionValues("tag")`; this yields three elements. Do not use the `--tag=blue,green,red` notation and assume `getOptionValues` always returns three elements.

### Passing positional input files

~~~bash
java -jar app.jar validate schema.json payload.json
~~~

`getNonOptionArgs()` has three elements in order: `validate`, `schema.json`, and `payload.json`. The application must validate the count, subcommand name, and file validity itself. For complex CLIs with many subcommands, use a dedicated parser.

## 11. Pre-production checklist

1. Forward `String[] args` properly from `main` to `SpringApplication.run`.
2. Use `ApplicationArguments` for structured CLI data instead of manually splitting a string by spaces.
3. Remember `DefaultApplicationArguments` is an implementation you can instantiate in tests, not a bean to `new` inside every component.
4. Handle **absent/null**, **flag/empty list**, and **explicit empty string/single-element list**.
5. Define clear semantics if the same option appears multiple times.
6. Do not rely on iteration order of `getOptionNames()`; sort when printing or compare as `Set`s.
7. Distinguish application CLI options, JVM `-D`, and OS environment variables.
8. If you need effective configuration, read from `Environment`/`@ConfigurationProperties`, without assuming CLI args contain all YAML/profile values.
9. Never put passwords/tokens/raw source args into production logs.
10. If input validation is needed before ready, place validation in a runner or appropriate phase and handle failures intentionally.
11. Unit-test the pure parser with `new DefaultApplicationArguments(...)`, but verify integrated configuration with a real Spring Boot test.
12. Cross-check API documentation against the exact Boot/Spring Framework version in use.

## 12. Self-check questions

**1. Is `ApplicationArguments` a concrete class that must be instantiated with `new`?**  
No. It is an interface; Boot normally provides the `ApplicationArguments` bean. `DefaultApplicationArguments` is the default implementation.

**2. How does `getSourceArgs()` differ from `getOptionValues("tag")`?**  
`getSourceArgs()` returns the raw token array; `getOptionValues` returns only the parsed value list for one option.

**3. When passing `--dry-run`, what do `containsOption("dry-run")` and `getOptionValues("dry-run")` return?**  
`true` and an empty list.

**4. When omitting `--dry-run`, what does `getOptionValues("dry-run")` return?**  
`null`, not an empty list.

**5. When passing `--dry-run=`, what is different?**  
There is one empty-string element in the value list; use `size()`/`get(0)` to distinguish it from a valueless flag.

**6. How many values does `--tag=red --tag=blue` produce in `getOptionValues("tag")`?**  
Two strings: `red` and `blue`.

**7. Does `--tag=red,blue` automatically produce two values?**  
No, under this parser contract; it is one string `red,blue`.

**8. Does `--name Lan` make `Lan` the value of `name`?**  
No; option `name` has no value, and `Lan` is a non-option.

**9. Why can `Environment.getProperty("app.mode")` have a value even when `getOptionValues("app.mode")` is `null`?**  
Because `Environment` has other `PropertySource`s such as YAML, system properties, or OS env.

**10. Does calling `setAddCommandLineProperties(false)` erase data in `ApplicationArguments`?**  
No; it disables adding CLI options to `Environment` via the default source, without disabling the parsed args API.

**11. What type does `ApplicationRunner` receive, and what type does `CommandLineRunner` receive?**  
`ApplicationRunner` receives `ApplicationArguments`; `CommandLineRunner` receives `String... args`.

**12. Should `Arrays.toString(getSourceArgs())` be printed in production logs?**  
Not by default, because raw args may contain secrets.

## 13. Official references

- [Spring Boot 3.5 — ApplicationArguments API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationArguments.html): contract of the five methods.
- [Spring Boot 3.5 — DefaultApplicationArguments API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/DefaultApplicationArguments.html): implementation and constructor accepting `String... args`.
- [Spring Boot 3.5 — SpringApplication and Accessing Application Arguments](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): injecting `ApplicationArguments`, runners, and startup path.
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): command-line `PropertySource` and precedence order.
- [Spring Framework 6.2 — SimpleCommandLinePropertySource](https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html): `--optName[=value]` syntax, repeated values, `--`.
- [Spring Boot 3.5 — SpringApplication API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/SpringApplication.html): `run(...)` parameters and `setAddCommandLineProperties(false)`.

Examples reflect Spring Boot 3.5.x and Java 17+. When applying to another project, verify the exact library versions and application CLI conventions before relying on default behaviors in business code.