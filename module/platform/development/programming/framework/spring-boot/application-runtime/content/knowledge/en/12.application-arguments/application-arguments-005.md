# Reading Raw Arguments with getSourceArgs in Spring Boot

## 1. What is getSourceArgs?

When running a Spring Boot application, users may pass parameters:

~~~bash
java -jar app.jar --mode=batch --tag=one --tag=two --dry-run "report 2026.csv"
~~~

A program may need access to **the exact tokens the application received**, including options, flags, positional arguments, and the order in which they appeared. The **org.springframework.boot.ApplicationArguments** interface provides the method:

~~~java
String[] originalTokens = arguments.getSourceArgs();
~~~

**getSourceArgs() returns a String[] containing the unclassified arguments of the SpringApplication.run(...) call**. In the example above, with **Arrays.toString(originalTokens)**, the result is:

~~~text
[--mode=batch, --tag=one, --tag=two, --dry-run, report 2026.csv]
~~~

The array has five elements; **report 2026.csv** is a single element containing a space. The two tokens **--tag=one** and **--tag=two** remain in their original positions and have not been merged into one list.

**Note on the word "raw":** these are the tokens **passed to SpringApplication**, not the verbatim command line before shell processing. Shell quoting marks have typically already been stripped before Java receives the arguments. Likewise, getSourceArgs does not collect properties from application.properties, environment variables, or JVM options.

This lesson focuses on the mechanics, timing, usage, and testing of **getSourceArgs()** on Spring Boot 3.3.x with Java 17+.

## 2. Comparing getSourceArgs with other ApplicationArguments APIs

**ApplicationArguments** lets you view both the raw tokens and the result of Spring's option syntax parsing.

| API | Data | Purpose |
| --- | --- | --- |
| **getSourceArgs()** | **String[]** of all original tokens | Preserves tokens and order |
| **getOptionNames()** | **Set<String>** of option names | Lists names of **--name** style options |
| **containsOption(name)** | **boolean** | Checks whether an option is present |
| **getOptionValues(name)** | **List<String>** or **null** | Gets the values of an option |
| **getNonOptionArgs()** | **List<String>** | Gets tokens not treated as options by the parser |

Example input:

~~~text
--mode=batch --tag=one --tag=two --dry-run report.csv
~~~

Corresponding results:

| Expression | Result |
| --- | --- |
| **Arrays.toString(args.getSourceArgs())** | **[--mode=batch, --tag=one, --tag=two, --dry-run, report.csv]** |
| **getOptionValues("mode")** | **[batch]** |
| **getOptionValues("tag")** | **[one, two]** |
| **containsOption("dry-run")** | **true** |
| **getOptionValues("dry-run")** | **[]** |
| **getOptionValues("unknown")** | **null** |
| **getNonOptionArgs()** | **[report.csv]** |

There are two key points:

1. **getSourceArgs() loses no information** when the framework provides option classification APIs; both views coexist.
2. **getSourceArgs() does not parse values**. It returns the string **--mode=batch**, not **batch** alone. For option semantics, use the classified methods or another parser.

### 2.1. Do not rely on the ordering of getOptionNames

**getSourceArgs()** is an array with explicit ordering. Conversely, **getOptionNames()** returns a **Set**; you should not infer original token order from set iteration order. If you need every token in exact appearance order, use **getSourceArgs()**.

### 2.2. Repeated options

With input:

~~~text
--tag=one --mode=batch --tag=two
~~~

getSourceArgs gives:

~~~text
[--tag=one, --mode=batch, --tag=two]
~~~

getOptionValues("tag") gives:

~~~text
[one, two]
~~~

The values list is useful when handling multiple values under the same name, yet it no longer shows **mode** appearing between the two tag tokens. When a custom parser needs to read interleaved ordering, the raw array is the better input.

## 3. From shell to SpringApplication: what does "raw" mean?

Typical sequence:

~~~text
User-entered command line
    |
    | shell handles quoting, escaping, expansion...
    v
JVM calls main(String[] args)
    |
    | code passes String[] to SpringApplication.run(...)
    v
SpringApplication builds ApplicationArguments
    |
    +--> getSourceArgs()       : unclassified tokens
    |
    +--> getOptionValues(...) : parsed values
    |
    +--> getNonOptionArgs()   : non-option tokens
~~~

Example:

~~~bash
java -jar app.jar "--description=Monthly Report"
~~~

The typical Java element is:

~~~text
--description=Monthly Report
~~~

This **is one token**, not two tokens. Quotes only help the shell keep the space inside one element; they **are not characters remaining in the Java string** after shell processing.

**You cannot use getSourceArgs to reconstruct how the user placed quotes, multiple spaces between tokens, or expansions performed by the shell.** The raw data at the Spring layer is a Java array, not a complete recording of terminal history.

### 3.1. Not necessarily identical to main args if code replaces arguments

Typical code:

~~~java
public static void main(String[] args) {
    SpringApplication.run(App.class, args);
}
~~~

Then the tokens ApplicationArguments receives correspond to main's **args**. However, if a developer writes:

~~~java
public static void main(String[] args) {
    String[] replacement = {"--mode=internal", "input.csv"};
    SpringApplication.run(App.class, replacement);
}
~~~

then getSourceArgs for this SpringApplication run reflects **replacement**, not the original parameters the terminal passed to main.

Both snippets above assume a class **App** and an import of **SpringApplication**.

### 3.2. JVM options are not program arguments

~~~bash
java -Xmx512m -Dregion=asia -jar app.jar --mode=batch
~~~

**-Xmx512m** and **-Dregion=asia** before **-jar** are JVM options. **--mode=batch** after the JAR is a program argument passed to the application. getSourceArgs in a typical run reflects **--mode=batch**, without adding the JVM options.

If a token prefixed with **-D** sits after the JAR name, it is an ordinary program argument and does not automatically become a system property set via the JVM launcher. Position in the command matters.

### 3.3. File config and environment variables do not appear automatically

Suppose:

~~~properties
app.mode=nightly
~~~

is set in application.properties, while the program launches with no arguments. **Environment.getProperty("app.mode")** can read **nightly**, yet **getSourceArgs()** remains an empty array.

Do not use raw source args to determine the complete final configuration across files, command line, OS environment, system properties, and Config Data. That is the responsibility of **Environment**, **@ConfigurationProperties**, and the binding mechanism.

## 4. Tokens to watch out for in practice

### 4.1. Valued options in Spring syntax

Spring Boot supports the syntax:

~~~text
--name=value
~~~

to parse options. With:

~~~text
--mode batch
~~~

getSourceArgs holds **two elements**:

~~~text
[--mode, batch]
~~~

Yet when using Spring's simple command-line parser, **--mode** is an option **without a value**, while **batch** is a non-option. Do not assume they are equivalent to **--mode=batch**.

If a CLI genuinely uses **--mode batch** or **-m batch** syntax, the raw array can be forwarded to a dedicated parser for that contract.

### 4.2. Valueless flags

~~~text
--dry-run
~~~

The raw array preserves **--dry-run**. ApplicationArguments interprets:

- **containsOption("dry-run") = true**
- **getOptionValues("dry-run") = []**

When the option is completely absent, **getOptionValues("dry-run") = null**. Clearly distinguish **absent** from **present without a value**.

Do not call **getOptionValues("mode").get(0)** before checking for null, empty list, and value count.

### 4.3. Unparsed booleans

The token:

~~~text
--dry-run=false
~~~

is still a **present dry-run option**: **containsOption("dry-run")** returns true. If business logic needs a boolean value, parse **getOptionValues("dry-run")** per your application's contract or use configuration binding. Do not infer false from containsOption.

### 4.4. Tokens with spaces, Unicode, and equals signs

getSourceArgs preserves each received Java string, for example:

~~~text
--title=Báo cáo tháng 11
--signature=a=b=c
đơn-hàng-001.csv
~~~

If the shell created three tokens with the contents above, the array still has three elements. Do not use **split(" ")** to re-split the whole line because it breaks strings with spaces. Do not use unbounded **split("=")** if values may also contain equals signs.

### 4.5. Empty array and index checks

With no program arguments, getSourceArgs returns an array with **length = 0**. Safe code:

~~~java
String[] source = args.getSourceArgs();

if (source.length == 0) {
    System.out.println("No program arguments");
} else {
    System.out.println(source[0]);
}
~~~

This snippet sits inside a method with a variable **args** of type ApplicationArguments. Accessing **source[0]** when the array is empty throws **ArrayIndexOutOfBoundsException**.

## 5. Runnable Java 17+ example: comparing raw and parsed

The following program uses **Spring Boot 3.3.13**, **Java 17+**, and Maven. It includes an **ApplicationRunner** to read getSourceArgs and parsed APIs, alongside a **CommandLineRunner** receiving String... for comparison. Both runners are managed as Spring beans and execute after context refresh succeeds.

### 5.1. Creating the project

~~~text
source-args-demo/
  pom.xml
  src/main/java/com/example/args/SourceArgsDemo.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>source-args-demo</artifactId>
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

**src/main/java/com/example/args/SourceArgsDemo.java**:

~~~java
package com.example.args;

import java.util.Arrays;

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
public class SourceArgsDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(SourceArgsDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.setBannerMode(Banner.Mode.OFF);
        app.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println("MAIN | active=" + context.isActive());
        }
    }
}

@Component
@Order(10)
class SourceArgumentsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        String[] raw = args.getSourceArgs();

        System.out.println("SOURCE | " + Arrays.toString(raw));
        System.out.println("COUNT | " + raw.length);
        System.out.println("FIRST | "
                + (raw.length == 0 ? "<none>" : raw[0]));
        System.out.println("MODE | " + args.getOptionValues("mode"));
        System.out.println("TAG | " + args.getOptionValues("tag"));
        System.out.println("DRY-RUN | " + args.containsOption("dry-run"));
        System.out.println("FILES | " + args.getNonOptionArgs());
    }
}

@Component
@Order(20)
class RawCommandRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("COMMAND | " + Arrays.toString(args));
    }
}
~~~

**Why are three top-level classes in one file valid?** Java allows one public top-level class **SourceArgsDemo** and two non-public package-private classes in the same file. **@Component** is in the scanned package, so both runners are registered by Spring. **@Order(10)** and **@Order(20)** establish a clear invocation order.

### 5.2. Build and run

In the project directory, using JDK 17+ and Maven 3.9+:

~~~bash
mvn -q -DskipTests package
java -jar target/source-args-demo-1.0.0.jar --mode=batch --tag=one --tag=two --dry-run "report 2026.csv"
~~~

On Windows PowerShell, when the project includes Maven Wrapper, you can build with:

~~~powershell
.\mvnw.cmd -q -DskipTests package
java -jar target/source-args-demo-1.0.0.jar --mode=batch --tag=one --tag=two --dry-run "report 2026.csv"
~~~

**Lines printed by the application itself, in expected order:**

~~~text
SOURCE | [--mode=batch, --tag=one, --tag=two, --dry-run, report 2026.csv]
COUNT | 5
FIRST | --mode=batch
MODE | [batch]
TAG | [one, two]
DRY-RUN | true
FILES | [report 2026.csv]
COMMAND | [--mode=batch, --tag=one, --tag=two, --dry-run, report 2026.csv]
MAIN | active=true
~~~

Spring Boot or build tool logs may appear interspersed. Do not expect all of stdout to contain only these lines; these are **the lines explicitly printed by the example code**.

### 5.3. Explaining stdout

1. The shell turns **"report 2026.csv"** into **one token** containing a space; thus the array has five elements.
2. **SpringApplication.run(args)** keeps the input to construct **ApplicationArguments**.
3. **SourceArgumentsRunner** reads raw tokens via getSourceArgs while also using the parsed methods.
4. **getOptionValues("mode")** is **[batch]**; the **tag** option appeared twice, yielding **[one, two]**.
5. **containsOption("dry-run")** is true, because the flag appeared.
6. **getNonOptionArgs()** contains **report 2026.csv**.
7. **RawCommandRunner** receives the equivalent tokens via **String... args**. **@Order** keeps the order of both runners deterministic in the example.
8. **SpringApplication.run(...)** only returns after synchronous runners finish; hence **MAIN** prints afterward. **try-with-resources** closes the CLI program's context right after.

**Do not close the context immediately after run in a web application that must keep serving HTTP**; the pattern above suits non-web practice exercises.

## 6. getSourceArgs in ApplicationRunner, CommandLineRunner, and beans

### 6.1. Reading directly inside ApplicationRunner

~~~java
@Component
class StartupRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        String[] rawTokens = args.getSourceArgs();
        // Parse/validate according to actual requirements.
    }
}
~~~

This is a snippet inside a package with matching imports. **ApplicationRunner** is the convenient choice if a task needs **both the raw array and parsed queries**.

### 6.2. Comparing with CommandLineRunner

~~~java
@Component
class AnotherRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        String[] rawTokens = args;
        // Use rawTokens when Boot's parsed API is not needed.
    }
}
~~~

**String...** is fundamentally **String[]**. In a normal SpringApplication run, CommandLineRunner receives the corresponding program arguments; choosing between interfaces mainly depends on **input-parsing needs**.

There is no default ordering where "ApplicationRunner always runs before CommandLineRunner". If ordering is needed, use **@Order** or **Ordered**.

### 6.3. Injecting ApplicationArguments into an ordinary bean

Spring Boot also allows injecting **ApplicationArguments**:

~~~java
@Component
class StartupInputSnapshot {

    private final String[] raw;

    StartupInputSnapshot(ApplicationArguments args) {
        this.raw = args.getSourceArgs().clone();
    }

    public String[] getRawCopy() {
        return raw.clone();
    }
}
~~~

This is a snippet requiring **@Component** and **ApplicationArguments** imports. It does not trigger a runner itself. It simply stores a **snapshot** so other beans can retrieve a copy when genuinely needed.

**Why clone?** A **String[]** array can be mutated by code holding a reference. The API must not be used as a channel to mutate configuration. Cloning stores **a copy with clear ownership**. Because array elements are immutable **String**s, cloning the array is sufficient to isolate the element list in this example.

### 6.4. Do not assume every Spring context has an ApplicationArguments bean

When an application is bootstrapped with **SpringApplication**, Boot registers an ApplicationArguments instance for injection. However, if you manually create a plain **AnnotationConfigApplicationContext** and refresh it without SpringApplication, do not assume that context already has an ApplicationArguments bean. When unit-testing the API, you can construct **DefaultApplicationArguments** yourself without a context.

## 7. Applying to parsing and validation

### 7.1. When should you use the raw array?

Use **getSourceArgs()** when you need to:

- Forward exact tokens to a dedicated CLI parser.
- Preserve interleaved ordering among flags, options, and positional arguments.
- Support non-Spring syntax, such as **-v**, **-f input.csv**, subcommands, or options with spaces between name and value.
- Build snapshots for testing compatibility with an API accepting **String[]**.
- Inspect the exact tokens the caller passed, as opposed to reading final resolved configuration.

### 7.2. When should you not use the raw array?

No need to parse raw args yourself if you only want to read:

~~~text
--mode=batch --tag=a --tag=b --dry-run file.csv
~~~

In that case:

~~~java
String mode = args.getOptionValues("mode").get(0);
boolean dryRun = args.containsOption("dry-run");
List<String> tags = args.getOptionValues("tag");
List<String> files = args.getNonOptionArgs();
~~~

This is an illustrative snippet; in production code, **check null/empty/count** before **get(0)**. This approach avoids writing string-parsing loops when the syntax fits Spring.

### 7.3. Separating parsing from business logic

A better design than passing String[] throughout the application:

~~~text
ApplicationRunner.run(ApplicationArguments)
       |
       +-- getSourceArgs() or getOptionValues(...)
       v
ArgumentParser / Validator
       |
       v
BatchOptions(mode, inputPath, dryRun)
       |
       v
BatchService.execute(BatchOptions)
~~~

**BatchOptions** can be an immutable Java record. The parser is unit-tested independently with input data; the business service does not need to know Boot has ApplicationArguments. The runner merely acts as an adapter for lifecycle and DI.

If a complex CLI tool has subcommands, help, short flags, and advanced option validation, consider a dedicated CLI library instead of building a parser out of split and startsWith.

## 8. How Environment differs from source arguments

With configuration:

~~~properties
# application.properties
app.mode=from-file
~~~

and command:

~~~bash
java -jar app.jar --app.mode=from-cli
~~~

**getSourceArgs()** supplies the token **--app.mode=from-cli** because it is a program argument. Under the default configuration mechanism, **Environment.getProperty("app.mode")** can return **from-cli** because the CLI source has higher precedence than the file.

Yet without CLI arguments:

- **getSourceArgs()** returns an empty array.
- **Environment.getProperty("app.mode")** can read **from-file**.

The two APIs therefore answer two different questions:

| Question | Appropriate API |
| --- | --- |
| Which CLI tokens did the program receive? | **getSourceArgs()** |
| Did the user pass an option named mode? | **containsOption("mode")** |
| Which values did the user pass for tag? | **getOptionValues("tag")** |
| What is the final configured value of app.mode? | **Environment/@ConfigurationProperties** |

### 8.1. setAddCommandLineProperties(false)

SpringApplication supports:

~~~java
SpringApplication app = new SpringApplication(MyApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
~~~

This snippet assumes a **MyApplication** class exists. This setting **prevents adding CLI options as the default command-line PropertySource** in Environment. It **does not mean source args vanish**. ApplicationArguments still reflects tokens passed to **app.run(args)**, and CommandLineRunner still receives raw arguments as usual.

Therefore, **parsing arguments** and **exposing CLI properties into Environment** are two distinct capabilities. Do not use getSourceArgs to check the final effective property.

## 9. Data safety and immutability

### 9.1. Do not mutate the framework array to change startup

Do not do:

~~~java
args.getSourceArgs()[0] = "--mode=changed";
~~~

This is not an API for updating Environment or parsed options, and can fail if there are no elements. It also depends on whether the implementation returns a copy or an internal reference, which should never be a design assumption.

When you want to store or transform locally, create a snapshot:

~~~java
String[] snapshot = args.getSourceArgs().clone();
~~~

Then parse/validate on your **snapshot** and return a clear result object.

### 9.2. Do not print raw arguments in production

The raw array can contain:

- **--password=...**
- **--api-token=...**
- Internal paths or private URLs.
- Personal data or sensitive business values.

Printing **Arrays.toString(args.getSourceArgs())** can leak all of it into logs, CI, monitoring, and traces. The example in section 5 uses non-sensitive illustrative data only.

In real systems, **never log raw args by default**; if observability is genuinely needed, log token count or safe keys, masking values under a strict allowlist. Secrets should be delivered via an appropriate secret-management mechanism rather than on the command line where they risk appearing in process lists.

### 9.3. Do not join tokens to re-execute in a shell

Do not take String[] and do:

~~~java
String combined = String.join(" ", args.getSourceArgs());
~~~

and pass **combined** to a shell for execution. You lose token boundaries when spaces exist and risk command injection with untrusted input.

If you need to forward arguments to a program with a fixed, trusted executable, use an API taking **a separate token list** such as **ProcessBuilder**, while still validating inputs and controlling the target executable. Never run arbitrary tools from raw tokens just because SpringApplication provided them.

## 10. Unit testing with DefaultApplicationArguments

To test getSourceArgs, you do not need to start an ApplicationContext. Spring Boot provides **DefaultApplicationArguments**, accepting **String...** or **String[]**.

Add the test dependency in pom.xml:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **src/test/java/com/example/args/SourceArgsTest.java**:

~~~java
package com.example.args;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.DefaultApplicationArguments;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SourceArgsTest {

    @Test
    void preservesSourceTokenOrder() {
        String[] input = {
                "--mode=batch",
                "--tag=one",
                "--tag=two",
                "--dry-run",
                "report 2026.csv"
        };
        ApplicationArguments args = new DefaultApplicationArguments(input);

        assertArrayEquals(input, args.getSourceArgs());
        assertEquals(List.of("one", "two"), args.getOptionValues("tag"));
        assertTrue(args.containsOption("dry-run"));
        assertEquals(List.of("report 2026.csv"), args.getNonOptionArgs());
    }

    @Test
    void rawTokensCanDifferFromParsedValues() {
        ApplicationArguments args = new DefaultApplicationArguments(
                "--mode",
                "batch",
                "-v"
        );

        assertArrayEquals(
                new String[] {"--mode", "batch", "-v"},
                args.getSourceArgs()
        );
        assertTrue(args.containsOption("mode"));
        assertEquals(List.of(), args.getOptionValues("mode"));
        assertEquals(List.of("batch", "-v"), args.getNonOptionArgs());
    }

    @Test
    void emptyArgumentsAreSupported() {
        ApplicationArguments args = new DefaultApplicationArguments();

        assertEquals(0, args.getSourceArgs().length);
        assertFalse(args.containsOption("mode"));
        assertNull(args.getOptionValues("mode"));
        assertEquals(List.of(), args.getNonOptionArgs());
    }

    @Test
    void cloneCreatesAnIndependentArray() {
        ApplicationArguments args =
                new DefaultApplicationArguments("--mode=batch", "file.csv");

        String[] returned = args.getSourceArgs();
        String[] snapshot = returned.clone();
        snapshot[0] = "--mode=changed";

        assertEquals("--mode=batch", returned[0]);
        assertEquals("--mode=changed", snapshot[0]);
    }
}
~~~

Run:

~~~bash
mvn test
~~~

The tests verify that **the raw array still has the exact tokens**, **order is preserved**, **options are parsed separately**, **zero arguments are supported**, and **clone creates an independent array**. The last test compares the snapshot with the array returned in that call; it does not assume the implementation stores or returns an internal reference in a particular way.

### 10.1. When integration tests are needed

DefaultApplicationArguments tests the parsing API in isolation; it does not yet verify:

- Whether commands passed by the shell, Docker, Maven/Gradle plugins, or CI systems reach main intact.
- Whether the real application forwards main args properly to SpringApplication.run.
- Whether runners are registered as beans and execute after refresh.
- Whether values received from the actual launcher match user expectations.

When these factors matter, run an integration/startup test with a real SpringApplication or execute **java -jar** in the target environment, and check safe tokens. Do not run only unit tests and assume every shell's quoting/escaping works identically.

## 11. Common mistakes

### 11.1. Assuming source arguments represent all runtime configuration

**getSourceArgs()** does not merge values from application.properties, OS environment, or Config Data. Final configuration belongs to Environment and Binder.

### 11.2. Assuming source arguments include JVM options

Flags like **-Xmx** or **-D** placed before **-jar** are processed by the JVM launcher and usually do not appear in args passed to main. Check command argument positions.

### 11.3. Splitting the entire string by spaces manually

A token containing **report 2026.csv** gets split into two strings if you join and split. Keep the **String[]/List<String>** structure.

### 11.4. Reading source[0] when there are no args

When the user passes no arguments, the array may be empty. Check **length** before indexing.

### 11.5. Misunderstanding --name value

Spring's simple option parser typically requires **--name=value**. With **--name value**, getSourceArgs still preserves both tokens, yet the parser classifies them under different semantics.

### 11.6. Using containsOption as a boolean parser

**containsOption("flag")** returns true for both **--flag** and **--flag=false**, because the option is still present. For booleans, read and validate the value.

### 11.7. Treating the array returned by getSourceArgs as mutable config

Do not mutate the array directly expecting Boot to update config. Clone it and parse into a separate application object.

### 11.8. Printing all raw args to production logs

Raw args may contain passwords or tokens. Record safe values intentionally and avoid storing unnecessary data.

### 11.9. Using runners at the wrong lifecycle point

ApplicationRunner and CommandLineRunner are invoked after refresh and before **ApplicationReadyEvent**. If callbacks run long tasks or throw exceptions, startup/readiness may be affected. If you only need input data for DI, inject ApplicationArguments into a bean; if business I/O is needed, choose the appropriate lifecycle and control errors.

### 11.10. Expecting a default order between the two runner types

Do not assume ApplicationRunner always runs before CommandLineRunner. If ordering is needed, use **Ordered/@Order**. In the example, ordering was specified explicitly.

### 11.11. Using getSourceArgs to reconstruct the verbatim command line

You cannot accurately recover quotes and escapes processed by the shell before Java received the tokens. "Raw" here means **raw relative to Spring's parser**, not raw relative to the terminal.

## 12. Adoption checklist

- [ ] Understand clearly that **getSourceArgs()** reflects tokens passed to **SpringApplication.run**.
- [ ] Know how to distinguish main args, JVM options, CLI properties, and Environment effective values.
- [ ] Preserve exact order when forwarding tokens to a dedicated parser.
- [ ] Never join and re-split by spaces.
- [ ] Know that **getOptionValues** is better when you only need parsed options.
- [ ] Check for an empty array before indexing.
- [ ] Clone if an independent snapshot is needed.
- [ ] Do not mutate the source array to alter configuration.
- [ ] Never log raw secrets; avoid writing sensitive data to traces/metrics.
- [ ] Never pass untrusted tokens to a shell.
- [ ] Test repeated options, spaces, Unicode, and zero-argument cases.
- [ ] Test via the actual launcher when token forwarding is critical.

## 13. Self-check questions

**Question 1.** What type does **ApplicationArguments.getSourceArgs()** return?

**Answer:** **String[]** containing the original program arguments passed to the SpringApplication run.

**Question 2.** If the shell passes **"--title=Monthly Sales"** as one token, do quotes remain in the Java string from getSourceArgs?

**Answer:** Normally no. The Java string is **--title=Monthly Sales**; quotes only helped the shell keep it as one token.

**Question 3.** With input **--mode batch**, how many elements does getSourceArgs have?

**Answer:** Two: **--mode** and **batch**. Under Spring's simple command-line parser, the following token does not automatically become the previous option's value.

**Question 4.** If application.properties has **app.mode=prod** but the user passes no CLI args, does getSourceArgs contain **--app.mode=prod**?

**Answer:** No. Configuration files do not generate source args.

**Question 5.** Inside ApplicationRunner, how do you get raw tokens without switching to CommandLineRunner?

**Answer:** Call **args.getSourceArgs()** inside **run(ApplicationArguments args)**.

**Question 6.** Why is **getSourceArgs()** unsuitable for determining the final configured value of **app.mode**?

**Answer:** Because the final value also depends on other PropertySources and configuration precedence. Use Environment/@ConfigurationProperties.

**Question 7.** If command-line PropertySource is disabled via **setAddCommandLineProperties(false)**, does getSourceArgs lose tokens?

**Answer:** No. Allowing CLI to override Environment is separate from SpringApplication receiving arguments.

**Question 8.** Why must **Arrays.toString(args.getSourceArgs())** be avoided in production?

**Answer:** Because tokens may contain secrets, personal data, and confidential operational details.

**Question 9.** How do you preserve token boundaries when forwarding to another parser?

**Answer:** Pass String[] or List<String> directly; do not join into a string and split by spaces.

**Question 10.** Can you create ApplicationArguments in a unit test without starting Spring Boot?

**Answer:** Yes. Use **new DefaultApplicationArguments(String...)** to test raw tokens and parsed options.

## 14. Key takeaways and official references

**getSourceArgs()** returns a **String[] containing the raw tokens of a SpringApplication run**, preserving the exact order the program passed to Boot. This API is suited when you need original tokens, forwarding to another parser, or testing input. It does **not** represent all Environment values and does **not** reconstruct the verbatim shell command.

When you only need **--name=value** options, flags, or non-options, use the parsing APIs of ApplicationArguments. When you need precedence-aware configuration, use Environment or @ConfigurationProperties. Treat the raw array as read-only, clone when a snapshot is needed, protect sensitive data, and test via the real launcher when necessary.

References:

- **Spring Boot 3.3.13 — SpringApplication / Accessing Application Arguments:** https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- **Spring Boot 3.3 — ApplicationArguments API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- **Spring Boot 3.3 — DefaultApplicationArguments API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/DefaultApplicationArguments.html
- **Spring Boot 3.3 — ApplicationRunner API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationRunner.html
- **Spring Boot 3.3 — CommandLineRunner API:** https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/CommandLineRunner.html