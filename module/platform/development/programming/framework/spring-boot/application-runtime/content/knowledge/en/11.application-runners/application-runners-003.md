# Choosing ApplicationArguments or a String[] Array in Spring Boot Runners

## 1. The Problem: Both Handle Startup Arguments, but at What Level?

When running a Spring Boot application, an operator might pass arguments such as:

~~~bash
java -jar app.jar --mode=batch --tag=one --tag=two --dry-run report.csv
~~~

A runner may need to read **mode**, check the **dry-run** flag, receive multiple **tag** values, or obtain the filename **report.csv**. Spring Boot provides two interfaces that execute logic after the ApplicationContext has refreshed:

- **ApplicationRunner**: the **run(ApplicationArguments args)** callback receives an object containing both the raw arguments and data parsed according to Boot's option syntax.
- **CommandLineRunner**: the **run(String... args)** callback receives **the raw argument strings**, in the exact order passed to SpringApplication, not yet categorized into options and non-options.

These are **two ways of representing input data**, not two different lifecycle types. Both are discovered by Spring Boot as **beans**, invoked during SpringApplication's runners step after context refresh succeeds and before **ApplicationReadyEvent**.

**Quick selection rule:**

- Choose **ApplicationRunner** when the business logic cares about Spring Boot's **--name[=value]** syntax, flags such as **--dry-run**, repeated options, or unnamed arguments (non-options).
- Choose **CommandLineRunner** when you need to preserve the **original String[]** for a custom tool/parser, a legacy API, or when the application's argument-parsing conventions do not match Spring's option convention.
- If you only need stable configuration values that can come from files, Environment, CLI, and deployment settings, consider **@ConfigurationProperties**, **Environment**, or Spring Boot's binding mechanism instead of manually parsing the command line in a runner.

This lesson uses **Java 17+ and Spring Boot 3.3.x** as its baseline, focusing on choosing the right argument type in a **Runner**.

## 2. The Two Interfaces and Their Exact Signatures

### 2.1. ApplicationRunner

The **org.springframework.boot.ApplicationRunner** interface declares:

~~~java
@FunctionalInterface
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}
~~~

**ApplicationArguments** is an abstraction with the following methods:

| Method | Meaning | Return Type |
| --- | --- | --- |
| **getSourceArgs()** | The raw argument tokens received by SpringApplication | **String[]** |
| **getOptionNames()** | Parsed option names, excluding the **--** prefix | **Set<String>** |
| **containsOption("name")** | Whether an option named **name** is present | **boolean** |
| **getOptionValues("name")** | Values of the option; follows rules distinguishing absent vs. valueless | **List<String>** or **null** |
| **getNonOptionArgs()** | Tokens not classified as options | **List<String>** |

Example of an **ApplicationRunner** method in a Spring bean:

~~~java
@Override
public void run(ApplicationArguments args) {
    boolean dryRun = args.containsOption("dry-run");
    List<String> tags = args.getOptionValues("tag");
    List<String> files = args.getNonOptionArgs();
    // Process categorized data.
}
~~~

This is a snippet assuming the class implements **ApplicationRunner** and has imported **java.util.List**. You **do not have to write a String[] loop to recognize --tag=...**, because Boot already provides an option-reading interface.

### 2.2. CommandLineRunner

The **org.springframework.boot.CommandLineRunner** interface declares:

~~~java
@FunctionalInterface
public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
~~~

**String... args** is Java **varargs** syntax; at runtime, this parameter has type **String[]**. Writing the implementation method as **run(String[] args)** or **run(String... args)** is signature-compatible in Java, though overriding usually uses the varargs syntax matching the interface.

~~~java
@Override
public void run(String... args) {
    for (String token : args) {
        System.out.println(token);
    }
}
~~~

The runner sees each raw token, such as **--mode=batch**, **--dry-run**, **report.csv**. It **cannot directly call getOptionValues**, because it does not receive ApplicationArguments as a parameter. If you need Boot-style option parsing, you can inject ApplicationArguments separately into the bean, yet when most logic uses parsed data, **ApplicationRunner** expresses intent more clearly.

### 2.3. Comparison Table

| Criterion | ApplicationRunner | CommandLineRunner |
| --- | --- | --- |
| Callback | **run(ApplicationArguments)** | **run(String... args)** |
| Primary input | Data parsed per Spring Boot conventions | Raw strings/tokens |
| Reading flag **--dry-run** | **containsOption("dry-run")** | Check tokens manually or use another parser |
| Reading **--tag=one --tag=two** | **getOptionValues("tag") → ["one","two"]** | Receives both tokens verbatim |
| Getting positional arguments | **getNonOptionArgs()** | Manually decide which tokens are positional |
| Preserving original input | **getSourceArgs()** | **args** itself |
| Supports **@Order** | Yes | Yes |
| Callback timing | After refresh, before ready | After refresh, before ready |
| Best suited for | Simple structured CLIs following Boot conventions | Forwarding raw args or using a custom parser |

**There is no rule that "ApplicationRunner always runs before CommandLineRunner."** When both are present, Boot sorts runners using **Ordered** or **@Order**. Do not rely on class or interface name ordering.

## 3. Option Syntax Understood by ApplicationArguments

Spring Boot uses Spring's command-line argument parsing mechanism, with the main rule:

~~~text
--optionName[=optionValue]
~~~

An option begins with **two hyphens**. The value, if present, follows the **=** sign within **the same token**.

Example:

~~~text
--mode=batch
--dry-run
--tag=one
--tag=two
report.csv
~~~

With this set of tokens:

| Query | Result |
| --- | --- |
| **containsOption("mode")** | **true** |
| **getOptionValues("mode")** | **["batch"]** |
| **containsOption("dry-run")** | **true** |
| **getOptionValues("dry-run")** | **[]** |
| **getOptionValues("tag")** | **["one", "two"]** |
| **getOptionValues("missing")** | **null** |
| **getNonOptionArgs()** | **["report.csv"]** |
| **getSourceArgs()** | Array of all five tokens, in exact input order |

### 3.1. Three Cases of getOptionValues You Must Distinguish

**getOptionValues(name)** has three distinct states per the API:

1. **Option is absent:** returns **null**.
2. **Option is present without a value**, e.g., **--dry-run**: returns **an empty list []**.
3. **Option has one or more values**, e.g., **--mode=batch** or **--tag=one --tag=two**: returns a non-empty list.

Because of this, the code below is **unsafe**:

~~~java
String mode = args.getOptionValues("mode").get(0);
~~~

If **--mode** is absent, it throws **NullPointerException**; if **--mode** is present without a value, it can throw **IndexOutOfBoundsException**.

An explicit check:

~~~java
List<String> values = args.getOptionValues("mode");

if (values == null || values.size() != 1 ||
        values.get(0).isBlank()) {
    throw new IllegalArgumentException(
            "Exactly one --mode=<value> is required");
}

String mode = values.get(0);
~~~

This snippet assumes the method is inside **ApplicationRunner.run(...)** and **List** is imported. It actively rejects **missing, blank, or repeated mode** rather than silently picking one value.

### 3.2. Presence Flags Are Not the Same as Boolean Options

**containsOption("dry-run")** returns **true** whenever the option is present, even if the token is:

~~~text
--dry-run=false
~~~

Because that is still an option named **dry-run**. If the application wants to support **--dry-run=true/false** syntax, it must read and parse **getOptionValues("dry-run")** according to boolean rules, or use appropriate configuration binding.

Conversely, for a pure **--dry-run** flag without **=**, **getOptionValues("dry-run")** is **[]**. Do not call **get(0)** to retrieve a boolean. Choose one of two contracts clearly:

- **Presence flag**: only support **--dry-run**, read via containsOption, and reject invalid value assignments.
- **Boolean-valued option**: support **--dry-run=true/false**, use a boolean parser, and validate allowed values.

Do not mix the two rules arbitrarily, as **--dry-run=false** can easily be misinterpreted as enabled.

### 3.3. Repeated Options

Given the input:

~~~text
--tag=one --tag=two --tag=three
~~~

**getOptionValues("tag")** returns a list of three values in order of appearance. If the application designs **tag** as a multi-value collection, this is useful behavior.

If an option should only have **one value** such as **--output=...**, check **size() == 1**; do not default to taking the first/last element without stating a clear policy. For the **Set<String>** returned by getOptionNames, you should also not rely on iteration order of option names.

### 3.4. Positional Arguments and Common Syntax Mistakes

Tokens not recognized as options appear in **getNonOptionArgs()**. For example:

~~~text
--mode=batch report.csv
~~~

**report.csv** is a non-option. However:

~~~text
--mode batch
~~~

**does not mean the same thing as --mode=batch** to Spring's simple command-line parser. **--mode** is an option present without a value; **batch** is a non-option. This is a common mistake for developers used to GNU/POSIX-style CLI parsers that allow a space between option name and value.

To pass **a value containing spaces** while keeping it a single token, the shell must preserve **--name=value** as one argument, for example in a shell supporting quoting:

~~~bash
java -jar app.jar "--report-title=Monthly Report"
~~~

When it reaches Java, the token contains the space inside the value; the quotes used by the shell normally do not become part of the Java token.

### 3.5. The -- Marker Ending the Option Section

Spring's parser supports **--** as a boundary ending option parsing. Subsequent tokens are treated as non-options, even if they themselves start with two hyphens.

Example:

~~~text
--mode=batch -- --literal-option report.csv
~~~

This is useful when passing the remainder of the CLI as raw data to another tool. However, the syntax and how the shell/build tool forwards **--** should be tested in your runtime environment. If the application's CLI is more complex, use a dedicated parser.

## 4. Both Receive Arguments in the Same Lifecycle Phase

In Spring Boot, after ApplicationContext refresh succeeds, Boot publishes **ApplicationStartedEvent**, then invokes **ApplicationRunner/CommandLineRunner** beans, and only then publishes **ApplicationReadyEvent** and marks readiness via the availability mechanism.

~~~text
SpringApplication.run(raw String[] args)
    |
    +-- Prepare Environment, create ApplicationContext
    +-- Load definitions, refresh context
    +-- ApplicationStartedEvent
    |
    +-- Collect Runner beans
    +-- Sort by Ordered / @Order
    +-- ApplicationRunner.run(ApplicationArguments)
    +-- CommandLineRunner.run(String...)
    |   (order between both types decided by order)
    |
    +-- ApplicationReadyEvent
    +-- ReadinessState.ACCEPTING_TRAFFIC
    +-- SpringApplication.run(...) returns context
~~~

The two runners are not two distinct default phases. Both run in **a single callRunners phase** after refresh. Developers can declare multiple beans of both types—for instance, beans checking configuration, warming caches, or running startup tasks.

**Operational consequences:**

- A long-running synchronous runner can delay **ApplicationReadyEvent** and readiness.
- An unhandled exception from a runner can cause startup **to fail**; there is no ApplicationReadyEvent for that failed run.
- The web server may already have started before runners finish, so "port open" is not equivalent to "ready."
- If a bean is **@Lazy** or has multi-layered dependencies, ensure Boot still discovers the runners as intended; do not use lazy initialization as an ad-hoc way to control runner timing.
- Do not manually call **runner.run(...)** in main; Boot already calls registered runner beans.

If multiple runners need deterministic order, add **@Order** or implement **Ordered**. Smaller order values are generally called first. Do not rely on method order in the source file.

## 5. Complete Maven/Java 17+ Example Comparing the Same Input

The example runs an application **without an HTTP server** so stdout is easy to inspect. It creates two runner beans: an **ApplicationRunner** printing the parsed form and a **CommandLineRunner** printing raw args. **@Order** makes the order of the two runners predictable.

### 5.1. Creating the Project

Use Java 17+, Maven 3.9+, and Spring Boot 3.3.13. Structure:

~~~text
runner-args-demo/
  pom.xml
  src/main/java/com/example/runner/RunnerArgsApplication.java
~~~

Contents of **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>runner-args-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

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

### 5.2. Spring Boot Code

File **src/main/java/com/example/runner/RunnerArgsApplication.java**:

~~~java
package com.example.runner;

import java.util.Arrays;
import java.util.TreeSet;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class RunnerArgsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(RunnerArgsApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }

    @Component
    @Order(10)
    public static class ParsedRunner implements ApplicationRunner {

        @Override
        public void run(ApplicationArguments args) {
            // TreeSet is only to keep option name order stable when printing.
            System.out.println("PARSED | names="
                    + new TreeSet<>(args.getOptionNames()));
            System.out.println("PARSED | mode="
                    + args.getOptionValues("mode"));
            System.out.println("PARSED | tags="
                    + args.getOptionValues("tag"));
            System.out.println("PARSED | dry-run="
                    + args.containsOption("dry-run"));
            System.out.println("PARSED | dry-run values="
                    + args.getOptionValues("dry-run"));
            System.out.println("PARSED | missing="
                    + args.getOptionValues("missing"));
            System.out.println("PARSED | positionals="
                    + args.getNonOptionArgs());
            System.out.println("PARSED | source="
                    + Arrays.toString(args.getSourceArgs()));
        }
    }

    @Component
    @Order(20)
    public static class RawRunner implements CommandLineRunner {

        @Override
        public void run(String... args) {
            System.out.println("RAW | args="
                    + Arrays.toString(args));
        }
    }
}
~~~

In a real application, the two runners can be separated into their own class files for easier maintenance. The example keeps them as **public static nested classes** annotated with **@Component** to present everything in one file; Spring Boot component scanning still manages them as beans.

### 5.3. Building and Running with Specific Arguments

Inside the **runner-args-demo** directory:

~~~bash
mvn -q -DskipTests package
java -jar target/runner-args-demo-1.0.0.jar --mode=batch --tag=one --tag=two --dry-run report.csv
~~~

With Maven Wrapper on Windows PowerShell, the corresponding build command is:

~~~powershell
.\mvnw.cmd -q -DskipTests package
java -jar target/runner-args-demo-1.0.0.jar --mode=batch --tag=one --tag=two --dry-run report.csv
~~~

Running **java -jar** after building avoids confusing Maven/plugin flags with arguments passed to the Java program. None of the tokens in the command contain spaces, so they behave similarly across common shells.

**Lines printed by the program itself in the exact expected order:**

~~~text
PARSED | names=[dry-run, mode, tag]
PARSED | mode=[batch]
PARSED | tags=[one, two]
PARSED | dry-run=true
PARSED | dry-run values=[]
PARSED | missing=null
PARSED | positionals=[report.csv]
PARSED | source=[--mode=batch, --tag=one, --tag=two, --dry-run, report.csv]
RAW | args=[--mode=batch, --tag=one, --tag=two, --dry-run, report.csv]
MAIN | active=true
~~~

Spring Boot, Maven, or JVM logs may be interleaved, yet **the lines printed by the sample code** have the exact content above when run with the right command and no other runner customizations.

**Why is the output right?**

- **ParsedRunner** carries **@Order(10)** so it runs before **RawRunner** carrying **@Order(20)**.
- **ApplicationArguments** recognizes three option names **mode**, **tag**, **dry-run**; **TreeSet** is used during printing for stable alphabetical order.
- **--tag=one --tag=two** becomes a two-element list.
- **--dry-run** is a present flag, so **containsOption** is true while the value list is empty.
- **missing** does not appear, so **getOptionValues** returns null.
- **report.csv** is a non-option; with **getSourceArgs** and RawRunner, every token remains intact in original order.
- **MAIN** is only printed after both synchronous runners finish and **SpringApplication.run(...)** returns the active context.

**Note:** the sample application uses **WebApplicationType.NONE** and **try-with-resources** to exit cleanly after the CLI example. For a web service meant to serve HTTP traffic long-term, do not close the context right after **run(...)** like this.

## 6. Decisions in Real-World Scenarios

### 6.1. Using ApplicationRunner for Commands with Options and Positional Arguments

Example import utility:

~~~text
java -jar importer.jar --format=csv --dry-run data/input.csv
~~~

You want:

- **format** to have exactly one value such as **csv** or **json**.
- **dry-run** as a presence flag.
- **data/input.csv** as the sole positional path.

This model fits ApplicationRunner well:

~~~java
@Override
public void run(ApplicationArguments args) {
    List<String> formats = args.getOptionValues("format");

    if (formats == null || formats.size() != 1) {
        throw new IllegalArgumentException(
                "Must specify exactly one --format=csv|json");
    }

    String format = formats.get(0);
    if (!format.equals("csv") && !format.equals("json")) {
        throw new IllegalArgumentException(
                "Unsupported format: " + format);
    }

    if (args.getNonOptionArgs().size() != 1) {
        throw new IllegalArgumentException(
                "Exactly one input file path is required");
    }

    boolean dryRun = args.containsOption("dry-run");
    String inputFile = args.getNonOptionArgs().get(0);

    // Invoke the import service injected into the runner via DI.
}
~~~

This is a **snippet** used inside a class implementing ApplicationRunner and requires importing **List**. Validation logic should be extracted into a separate method/class if complex, so it can be tested without starting the entire context.

### 6.2. Using CommandLineRunner to Forward Raw Tokens Verbatim

Suppose an application embeds a specialized parser that needs to preserve every token, including **-v**, **--**, **-Dkey=value**, and original ordering:

~~~java
@Component
class CustomCliRunner implements CommandLineRunner {

    private final CustomArgumentParser parser;

    CustomCliRunner(CustomArgumentParser parser) {
        this.parser = parser;
    }

    @Override
    public void run(String... args) {
        parser.execute(args);
    }
}
~~~

This is a **design snippet**, where **CustomArgumentParser** is an application interface/class you build yourself or select from an appropriate library. It is not a standalone program. CommandLineRunner is suitable because the parser may have syntax different from **--name[=value]** and requires keeping raw tokens intact.

**Do not rewrite a complex parser from scratch** if the CLI has subcommands, help output, type checking, mutually exclusive options, or tricky quoting. A dedicated CLI library can do that job better; CommandLineRunner is simply the bridge to the parser.

### 6.3. What If You Only Need a Configuration Property?

Suppose a web service needs a setting **app.batch-size** that can be placed in:

~~~properties
app.batch-size=500
~~~

and overridden with:

~~~bash
java -jar app.jar --app.batch-size=1000
~~~

If this is **application configuration**, you should usually use **@ConfigurationProperties** to bind and validate, or **Environment**. By default, Spring Boot adds command-line options to a **CommandLinePropertySource**, allowing CLI property sources to participate in configuration precedence.

**ApplicationArguments** is appropriate when you need the exact tokens/flags/repeated options of **this specific launch**. **@ConfigurationProperties** is appropriate when the value is **structured configuration** coming from multiple sources. Do not use ApplicationRunner to manually re-parse all YAML files, environment variables, and the property source hierarchy.

### 6.4. ApplicationRunner Can Still Obtain String[] If Needed

Choosing ApplicationRunner does not lose the original information:

~~~java
@Override
public void run(ApplicationArguments args) {
    String[] original = args.getSourceArgs();
    // Can forward original to an API expecting String[].
}
~~~

If a runner needs **both structured options and the raw array**, **ApplicationRunner** is the natural choice because it provides **both**. CommandLineRunner does not provide the parsed method suite directly in its callback parameter.

## 7. Testing ApplicationArguments Without Starting Spring

Spring Boot provides **DefaultApplicationArguments**, an implementation using the same option syntax so you can test input-parsing logic.

In a project with the test dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **src/test/java/com/example/runner/ArgumentsParsingTest.java**:

~~~java
package com.example.runner;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ArgumentsParsingTest {

    @Test
    void parsesOptionsFlagsAndPositionals() {
        String[] source = {
                "--mode=batch",
                "--tag=one",
                "--tag=two",
                "--dry-run",
                "report.csv"
        };

        ApplicationArguments args =
                new DefaultApplicationArguments(source);

        assertArrayEquals(source, args.getSourceArgs());
        assertEquals(List.of("batch"), args.getOptionValues("mode"));
        assertEquals(List.of("one", "two"), args.getOptionValues("tag"));
        assertTrue(args.containsOption("dry-run"));
        assertEquals(List.of(), args.getOptionValues("dry-run"));
        assertNull(args.getOptionValues("missing"));
        assertEquals(List.of("report.csv"), args.getNonOptionArgs());
        assertFalse(args.containsOption("missing"));
    }

    @Test
    void missingValueIsDifferentFromMissingOption() {
        ApplicationArguments args =
                new DefaultApplicationArguments(
                        "--format",
                        "--other=csv",
                        "input.csv");

        assertTrue(args.containsOption("format"));
        assertEquals(List.of(), args.getOptionValues("format"));
        assertNull(args.getOptionValues("not-provided"));
        assertEquals(List.of("csv"), args.getOptionValues("other"));
        assertEquals(List.of("input.csv"), args.getNonOptionArgs());
    }
}
~~~

Run command:

~~~bash
mvn test
~~~

**These tests directly verify the semantics of ApplicationArguments**: preserving source args, repeated options, valueless flags, distinguishing **null** and **[]**, and non-option args. You do not need to open an HTTP server or call SpringApplication.run to know the parser accepts tokens properly.

### 7.1. Testing Runner Business Logic

A better step is to **extract argument decoding and validation** into a small class:

~~~text
ApplicationRunner.run(ApplicationArguments)
       |
       v
OptionsParser.parse(ApplicationArguments)
       |
       v
ImportOptions(format, dryRun, inputFile)
       |
       v
ImportService.execute(ImportOptions)
~~~

Then:

- Unit test **OptionsParser** using **DefaultApplicationArguments** and assert **ImportOptions** or exceptions.
- Unit test **ImportService** business logic with plain Java data.
- Write only a few integration tests to confirm Spring creates the runner bean, injects the service properly, and calls it during startup as needed.

Separating it this way prevents the runner from becoming a class that parses args, calls network/database, and runs business logic all at once—which is hard to test and easily slows down startup.

### 7.2. Testing CommandLineRunner

For a CommandLineRunner receiving **String[]**, the easiest way to unit test is to call the raw-array processing logic directly, avoiding booting the full Spring context:

~~~java
String[] raw = {"-v", "--", "--literal"};
customParser.execute(raw);
// Assert the parser's result for each given token.
~~~

This is a snippet assuming an application **customParser**; it is not a complete test. If the runner depends on DI and you want to verify startup order, use a test with a real SpringApplication/context rather than testing the parser alone.

### 7.3. Testing Thoroughly with Bad Inputs

A reliable CLI test suite should cover:

- No arguments passed.
- Missing required option.
- **--key** present without a value.
- **--key=** with an empty value.
- A single-valued option appearing twice.
- A boolean flag passed as **--flag=false**.
- Non-options containing spaces or Unicode and how the shell tokenizes them.
- Unknown or misspelled options.
- Filenames starting with two hyphens, handled via **--** if appropriate.

In particular, choose a **clear policy** for unknown options: reject, warn, or allow forwarding. **getOptionNames()** can help inspect which option names actually appeared so you can validate against an allowlist.

## 8. Same Input, Yet How Does Environment Differ from ApplicationArguments?

When the application runs with:

~~~text
--app.mode=import --verbose data.csv
~~~

**ApplicationArguments** answers:

- Is the **app.mode** option present? Yes.
- What are the specific values for option **app.mode**? **["import"]**.
- Is the **verbose** flag present? Yes; with no value.
- Which positional arguments were supplied? **["data.csv"]**.

**Environment** answers a different question: after combining all PropertySources by precedence, what is the current value of property **app.mode**? It could be a value from CLI, system properties, environment variables, or Config Data.

| Case | Should Use |
| --- | --- |
| Need to know **whether the CLI explicitly passed --app.mode** | **ApplicationArguments.containsOption("app.mode")** |
| Need to know **every repeated --tag value** | **ApplicationArguments.getOptionValues("tag")** |
| Need to preserve **original token order** | **ApplicationArguments.getSourceArgs()** or **CommandLineRunner String[]** |
| Need to read **the final configuration** after precedence is applied | **Environment** or **@ConfigurationProperties** |
| Need binding for numbers, durations, booleans, configuration validation | **@ConfigurationProperties** / Boot Binder |
| Need complex subcommands (**import**, **export**, **migrate**) | **Dedicated CLI parser**, potentially invoked via CommandLineRunner |

### 8.1. When Disabling the CLI Property Source

SpringApplication has an API **setAddCommandLineProperties(false)** to avoid adding CLI arguments as an Environment PropertySource. This **does not mean String[] or ApplicationArguments disappears**: SpringApplication still receives the tokens and provides them to runners. Keep the two mechanisms separate:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

This is a snippet assuming a **MyApplication** class. When the CLI property source is disabled, an option like **--app.mode=import** no longer automatically overrides **app.mode** in Environment via the normal CLI property source path, yet ApplicationArguments still lets you inspect options belonging to that launch's arguments.

Therefore, do not confuse **parsing arguments** with **property resolution**.

### 8.2. Avoid Logging Secrets

Both **String[] args** and **ApplicationArguments.getSourceArgs()** can contain passwords, tokens, API keys, or sensitive values. The example printed raw tokens to learn how the two APIs differ; **do not copy that raw args logging snippet into production**.

In production, logs should be restricted to safe option names and masked values. Configuration containing secrets should use a secret store or appropriate configuration source rather than exposing secrets on the command line where they risk showing up in process lists or logs.

## 9. Common Mistakes When Choosing and Reading Arguments

### 9.1. Calling getOptionValues(...).get(0) Immediately

If the option is absent, the result is **null**; if present without a value, the list is empty. Check both states and the element count before calling get(0).

### 9.2. Misunderstanding --name value

With Spring's simple parser, option values should be in **--name=value** form within the same token. **--name value** is a valueless option and a non-option, not two parts of the same option.

### 9.3. Treating containsOption as Boolean Parsing

**containsOption("enabled")** is **true** for both **--enabled** and **--enabled=false**. If you need a real boolean, read the value and parse it according to your CLI contract.

### 9.4. Dropping Repeated Options

**getOptionValues("tag")** returns **List<String>**. If you only take the first element without stating a policy, the application can silently drop tags provided later. Design for single or multiple values and validate accordingly.

### 9.5. Manually Calling split(" ") on a Command String

**String[] args** has already been split into tokens by the shell/JVM per program invocation rules. If you join them back together and call **split(" ")**, quoted values containing spaces can be broken. Use the tokens directly from args or a dedicated parser.

### 9.6. Mixing Up JVM Arguments and Application Arguments

Example:

~~~bash
java -Xmx512m -jar app.jar --mode=batch
~~~

**-Xmx512m** is a JVM option, not a token SpringApplication receives in **main(String[] args)**. Runners only receive the application arguments forwarded to SpringApplication.run. The same applies to flags meant specifically for the Maven/Gradle wrapper.

### 9.7. Relying on ApplicationRunner Preceding CommandLineRunner

Both execute in the same phase. If order is needed, use **@Order** or **Ordered**; if one task depends on another task's output, design an explicit dependency rather than hoping for luck.

### 9.8. Long-Running Runners or Uncontrolled Exceptions

Runners can delay readiness; exceptions can fail startup. Choose timeouts, failure strategies, retries, and task criticality. If you simply need a background task running after startup, do not block the runner with an infinite loop.

### 9.9. Trying to Use ApplicationArguments for a Complex CLI

**ApplicationArguments** has a simple option parser, not a full framework for subcommands, help messages, multi-option validation, and shell completion. For a complex CLI, use a dedicated parser and pass raw args via CommandLineRunner, or another suitable CLI architecture.

### 9.10. Choosing String[] Just to Print Arguments

If you want to check flags, read multi-valued options, and read non-options without a custom parser, **ApplicationRunner** is clearer. It still preserves the raw data via **getSourceArgs()**.

## 10. Checklist Before Writing a Runner

- [ ] Do you need standard **--name[=value]** option syntax or custom syntax?
- [ ] Do you need **option names, flags, multiple values, non-options**? If so, prefer ApplicationArguments.
- [ ] Do you need **raw tokens and order**? String[] or getSourceArgs.
- [ ] Do you need to distinguish **null**, **[]**, **[""]**?
- [ ] Have you checked missing, repeated, or malformed value cases?
- [ ] Are you misusing **containsOption** to read booleans?
- [ ] Is the value **multi-source configuration** or a launch-specific CLI parameter?
- [ ] Have you avoided logging raw args containing secrets?
- [ ] Does the runner complete within a reasonable duration before readiness?
- [ ] If multiple runners have dependencies, is **@Order/Ordered** order defined?
- [ ] Are parsers/validators extracted so they can be unit tested without starting Spring?

## 11. Self-Check Questions

**Question 1.** An application needs option **--format=csv**, flag **--dry-run**, and one positional file path. Which runner should you choose?

**Answer:** **ApplicationRunner** is generally suitable because **ApplicationArguments** already provides **getOptionValues("format")**, **containsOption("dry-run")**, and **getNonOptionArgs()**.

**Question 2.** Does CommandLineRunner.run(String... args) receive different token contents than ApplicationArguments.getSourceArgs()?

**Answer:** In a normal SpringApplication launch with the same raw arguments, they reflect **the corresponding original input tokens**. ApplicationArguments also adds structured queries. **String...** is just Java varargs, represented as String[].

**Question 3.** When does **getOptionValues("trace")** return **null** and when does it return **[]**?

**Answer:** **null** when the option is absent; **[]** when the option is present without a value, e.g., **--trace**.

**Question 4.** Does **--enabled=false** make **containsOption("enabled")** return false?

**Answer:** **No**. The option is still present, so containsOption returns true; for a boolean, you must read and parse the value.

**Question 5.** Given **--tag=a --tag=b**, should you call **getOptionValues("tag").get(0)** and discard the rest?

**Answer:** Only if the application explicitly documents a policy of taking the first value. If tags are a list, process all of them; if only one tag is allowed, reject inputs with multiple values.

**Question 6.** Is **--output result.txt** recognized as option output with value result.txt by Spring's default parser?

**Answer:** No. **--output** is recognized as a valueless option; **result.txt** is a non-option. Use **--output=result.txt**.

**Question 7.** Can you use ApplicationRunner and still pass a raw String[] to a legacy library?

**Answer:** Yes, via **ApplicationArguments.getSourceArgs()**.

**Question 8.** Why might **@ConfigurationProperties** be better than reading ApplicationArguments if the application needs a configurable timeout?

**Answer:** Because a timeout is configuration that can come from Config Data, Environment, or CLI and can be bound/validated uniformly. ApplicationArguments only describes launch arguments, not multi-source configuration.

**Question 9.** Does Boot automatically call ApplicationRunner before every CommandLineRunner?

**Answer:** No. Both are sorted by order; use **@Order/Ordered** if order matters.

**Question 10.** Why do unit tests for **DefaultApplicationArguments** not need to start all of Spring Boot?

**Answer:** Because it is a plain Java object providing the argument-parsing logic directly; you can instantiate it with String[] and assert return values without an ApplicationContext.

## 12. Conclusion and Official Documentation

**ApplicationRunner** and **CommandLineRunner** run at the same point after refresh and before **ApplicationReadyEvent**; **the main difference is argument representation**. Choose **ApplicationArguments** to handle **--name[=value]** options, flags, repeated values, non-options, while still retaining raw args. Choose **String[]** when forwarding raw tokens verbatim or using another syntax parser.

Specifically remember the three states of **getOptionValues()**: **null** (option absent), **[]** (option present without value), and **non-empty list** (has value). Validate inputs, separate parsing from business logic, avoid logging secrets, and do not let runners prolong startup unnecessarily.

Official documentation (for Spring Boot 3.3.13 / Spring Framework 6.1):

- **Spring Boot 3.3 — SpringApplication, Accessing Application Arguments, Using ApplicationRunner or CommandLineRunner:** https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- **Spring Boot 3.3 — ApplicationRunner API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- **Spring Boot 3.3 — CommandLineRunner API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html
- **Spring Boot 3.3 — ApplicationArguments API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- **Spring Boot 3.3 — DefaultApplicationArguments API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- **Spring Framework 6.1 — SimpleCommandLinePropertySource API:** https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html