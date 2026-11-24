# Handling Repeated or Valueless Options in Spring Boot

## 1. Lesson objectives

Spring Boot lets applications receive command-line arguments such as `--mode=batch`, `--verbose`, or `--tag=red --tag=blue`. For options that appear only once and always have a value, reading parameters is straightforward. Complexity starts when:

- An option name appears **multiple times**, each time possibly with a different value.
- An option appears as a **valueless flag**, such as `--dry-run`.
- An option has an equals sign whose **value is an empty string**, such as `--name=`.
- An option **does not appear at all**.
- The same name appears both with and without a value, such as `--tag --tag=red`.
- A user passes malformed syntax like `--tag red`, assuming `red` is the value of `tag`.

To handle these properly, you must understand the contract of `org.springframework.boot.ApplicationArguments` and Spring Framework's argument-parsing rules. This lesson focuses on **application arguments** in Spring Boot Runtime, not JVM arguments, shell configuration systems, or arbitrary CLI tool parameter syntax.

After this lesson, you will be able to distinguish four important states: **absent**, **present without a value**, **one empty value**, and **one or more actual values**; and then build an appropriate input validation policy instead of guessing implicitly.

## 2. Option syntax parsed by Spring Boot

Spring Boot uses `ApplicationArguments` to interpret the arguments passed to `SpringApplication.run(args)`. With the standard argument parser, the syntax of an option is:

~~~text
--optionName[=optionValue]
~~~

Option names begin with **two hyphens**. When a value is present, `=` must directly join the name and value within the **same argument token**.

Examples:

| Argument | Classification | Meaning |
| --- | --- | --- |
| `--verbose` | Option | `verbose` option present, no value passed |
| `--verbose=true` | Option | `verbose` option present with string value `"true"` |
| `--verbose=false` | Option | `verbose` option present with string value `"false"` |
| `--name=` | Option | `name` option present with **one empty-string value** |
| `--tag=red` | Option | `tag` has value `red` |
| `--tag=red --tag=blue` | Two option tokens | Same name `tag` has **two values** |
| `--tag=red,blue` | One option token | Has **one** string `red,blue`; the parser does not auto-split commas |
| `report.csv` | Non-option | Positional argument, not belonging to an option name |
| `--tag report.csv` | Two tokens | `tag` has no value; `report.csv` is a non-option |
| `-v` | Non-option in this parser | Does not automatically equate to `--verbose` |
| `--` | End-of-options marker | Subsequent tokens are treated as non-options |

For example, the tokens passed to `main(String[] args)` as:

~~~text
["--tag=red", "--tag=blue", "--verbose", "report.csv"]
~~~

produce an option set with two values for `tag`, a valueless flag `verbose`, and a non-option `report.csv`.

**Important shell note:** when passing a value containing spaces, quote it so the shell passes it as one token, for example:

~~~bash
java -jar app.jar --title="daily report"
~~~

Spring receives a single argument corresponding to `--title=daily report`. The shell itself processes quotes; the Java parser only receives already-tokenized strings. Quoting behavior on PowerShell, cmd.exe, and Bash can differ in complex cases.

### The `--` end marker

The `--` token (just two hyphens, with no option name) marks the end of option parsing under standard parser syntax. For example:

~~~bash
java -jar app.jar --verbose -- --tag=not-an-option report.csv
~~~

Here `verbose` remains an option; tokens after `--`, even strings starting with `--tag=`, are treated as non-options. This is useful when passing filenames or positional data that start with `--`.

Do not confuse the `--` end-of-options delimiter with `--tag`: a token with a name is a valueless option; a token containing only `--` is a delimiter.

## 3. ApplicationArguments API you need to know

Spring Boot provides the `org.springframework.boot.ApplicationArguments` interface. In real applications, you can inject it into beans or receive it via `ApplicationRunner.run(ApplicationArguments args)`.

| API | Return Value | When to use? |
| --- | --- | --- |
| `containsOption(String name)` | `boolean` | Determine whether an option is present, even without a value |
| `getOptionValues(String name)` | `List<String>` or `null` | Get **all values** of a repeated option |
| `getOptionNames()` | `Set<String>` | Get **unique option names** |
| `getNonOptionArgs()` | `List<String>` | Get positional arguments that are not options |
| `getSourceArgs()` | `String[]` | Get **all raw tokens** passed to `SpringApplication.run(...)` |

Specifically, `getOptionValues(name)` has a clear contract documented in the Spring Boot 3.5 Javadoc:

| How it is passed | `containsOption("foo")` | `getOptionValues("foo")` | Interpretation |
| --- | --- | --- | --- |
| No `--foo` | `false` | `null` | Option **absent** |
| `--foo` | `true` | `[]` | Option present, **no value** |
| `--foo=bar` | `true` | `["bar"]` | One value |
| `--foo=bar --foo=baz` | `true` | `["bar", "baz"]` | Multiple values |
| `--foo=` | `true` | Single-element list `[""]` | **One empty value**, not an empty list |

**Do not write `getOptionValues(name).isEmpty()` without accounting for a `null` return.** When the option is absent, that code throws `NullPointerException`.

One misleading detail when debugging Java: `List.of("").toString()` renders looking like `[]`, even though the list actually has one empty-string element. Check **`size()` and element length** to distinguish them reliably.

### Four states, not just two

A safe decision model:

~~~text
containsOption("foo")?
   |
   +-- false ---------------------------> ABSENT
   |
   +-- true
         |
         +-- getOptionValues("foo")      [non-null]
                |
                +-- size() == 0 --------> PRESENT_NO_VALUE
                |
                +-- size() >= 1
                       |
                       +-- element "" --> EXPLICIT_EMPTY_STRING
                       |
                       +-- other elem --> VALUE(S)
~~~

If a repeated option contains both an empty element and actual values, define the business policy: accept, filter out empty strings, or report an error.

### getOptionNames does not tell occurrence counts

`getOptionNames()` returns `Set<String>`. Therefore:

~~~bash
--tag=red --tag=blue --tag=red
~~~

still has only **one name `tag`** in the set. If you need all three values, use `getOptionValues("tag")`. If you want to know exactly how many times an option name appeared, including valueless occurrences, you may need to inspect raw tokens via `getSourceArgs()`.

## 4. Why are repeated options stored as a list?

Some applications naturally require value sets:

- `--include=*.java --include=*.xml`: multiple file filter patterns.
- `--tag=finance --tag=priority`: multiple tags.
- `--endpoint=https://a.example --endpoint=https://b.example`: multiple addresses to try in order.
- `--role=reader --role=writer`: multiple requested permissions.
- `--feature=A --feature=B`: list of features to enable in a job.

The value collection carries business meaning. For instance:

~~~java
List<String> tags = arguments.getOptionValues("tag");
if (tags == null) {
    tags = List.of();
}
~~~

This is **an illustrative snippet inside a scope that already has `ApplicationArguments arguments`**, not a standalone runnable Java file. It maps an absent option to an empty list under an *optional multi-value* policy. However, it erases the difference between **absent** and **present without a value**; only use this approach when both states are permitted to mean the same thing.

If the strict requirement is that whenever the user enters `--tag` it must include a value, check separately:

~~~java
boolean present = arguments.containsOption("tag");
List<String> values = arguments.getOptionValues("tag");

if (present && (values == null || values.isEmpty())) {
    throw new IllegalArgumentException(
            "--tag requires at least one value");
}
~~~

This snippet is also **not standalone**; it needs the `List` import and variable `arguments`. Checking `values == null` when `present` is defensive; in standard Spring Boot implementations, a present option receives a list.

**Important note:** `getOptionValues("tag")` reflects only **values attached to that name**. If input mixes `--tag --tag=red`, the valueless `--tag` occurrence might not produce a `null` element in the list, while `red` is still present. If rules forbid *any* valueless occurrence, you must inspect raw tokens or use a CLI library with a stricter contract; inspecting the value list alone may not be enough.

## 5. Valueless flags: choosing an explicit boolean policy

A flag like `--dry-run` is usually understood as enabling a feature. Yet the same name can be passed as `--dry-run=false`. The application must **choose and document** one of these contracts:

**Policy A — presence-only flag:** `--dry-run` means enabled; `--dry-run=false` is treated as invalid syntax. Suitable for simple command-line utilities.

**Policy B — flag or explicit boolean:** `--dry-run` means `true`, `--dry-run=true` is `true`, `--dry-run=false` is `false`. When absent, use a default value (usually `false`).

**Policy C — explicit `true|false` value required:** `--dry-run` without `=` is treated as an error. Suitable when ambiguity could cause dangerous side effects.

Do not take `containsOption("dry-run")` as the final boolean if you intend to support `--dry-run=false`: `containsOption` still returns **true** in that case.

Example implementing Policy B, accepting exactly one boolean value:

~~~java
static boolean booleanFlag(ApplicationArguments args,
                           String name, boolean defaultValue) {
    if (!args.containsOption(name)) {
        return defaultValue;
    }

    List<String> values = args.getOptionValues(name);
    if (values == null || values.isEmpty()) {
        return true; // "--name" without a value.
    }
    if (values.size() != 1) {
        throw new IllegalArgumentException(
                "--" + name + " accepts only one boolean value");
    }

    return switch (values.get(0).toLowerCase(Locale.ROOT)) {
        case "true" -> true;
        case "false" -> false;
        default -> throw new IllegalArgumentException(
                "--" + name + " must be true or false");
    };
}
~~~

This is an **illustrative method**, requiring imports for `ApplicationArguments`, `List`, and `Locale`. It can be placed in the complete Java class in section 7.

Under Policy B, the cases are:

| Input | Result |
| --- | --- |
| Option absent | `defaultValue` |
| `--dry-run` | `true` |
| `--dry-run=true` | `true` |
| `--dry-run=false` | `false` |
| `--dry-run=` | Error: empty value |
| `--dry-run=yes` | Error if only `true|false` is accepted |
| `--dry-run=true --dry-run=false` | Error: multiple conflicting values |

Strict boolean parsing is **better** than calling `Boolean.parseBoolean(...)` unchecked: Java turns any string other than `"true"` into `false`, quietly hiding typos.

## 6. Distinguishing valueless options from empty-string values

This is the hardest bug to spot when only reading a list's `toString()`.

### 6.1. --flag: no value

~~~bash
java -jar app.jar --flag
~~~

According to `ApplicationArguments`:

~~~text
containsOption("flag")  -> true
getOptionValues("flag") -> []
size()                  -> 0
~~~

The list has **no elements**, so you must not call `get(0)` immediately.

### 6.2. --flag=: one value equal to ""

~~~bash
java -jar app.jar --flag=
~~~

According to `ApplicationArguments`:

~~~text
containsOption("flag")  -> true
getOptionValues("flag") -> list containing ""
size()                  -> 1
get(0).length()         -> 0
~~~

The list has **one element**, whose length is 0. Printing directly with `List.toString()` can be misleading, so print the element count or wrap strings in quotes when debugging.

At the business layer, handling differs:

- A flag option may accept `--flag` but reject `--flag=`.
- A string option may accept `--name=` if the user wants to **clear an old value**; this does not necessarily mean the same as an absent option.
- A required option expecting real data must reject both `--name` and `--name=`.
- A repeatable option may need to reject an empty `""` element mixed among valid values.

### 6.3. Do not equate "" with null

The states below are not equivalent:

~~~text
null       => option has no registration in ApplicationArguments
[]         => option is present, with no values
[""]       => option is present, one empty string
["alpha"]  => option is present, one value "alpha"
~~~

Especially in update (patch) configuration logic or feature toggles, `null`, an empty list, and an empty string can lead to three distinct behaviors.

## 7. Complete Java 17+ example (Spring Boot 3.5.16)

The following example directly demonstrates three categories: repeated option `tag`, valueless flag `verbose`, and empty-string value `empty`. The program also illustrates a flag with value `enabled=false`, absent option `missing`, non-option `invoice.csv`, and validating input before processing.

For clear observation, the app sets `WebApplicationType.NONE`: no HTTP server is opened, and program output lines can be checked independently of Spring Boot startup logs.

### 7.1. Maven structure

~~~text
args-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/example/argsdemo/
                └── ArgsDemoApplication.java
~~~

**File `pom.xml`:**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
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

This is a Maven project for JDK 17+ and Spring Boot 3.5.16. `spring-boot-starter-web` is omitted because the goal is to demonstrate receiving and parsing arguments; web apps still use the exact same `ApplicationArguments` API.

### 7.2. Complete Java file

**File `src/main/java/com/example/argsdemo/ArgsDemoApplication.java`:**

~~~java
package com.example.argsdemo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.stream.Collectors;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ArgsDemoApplication {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(
                ArgsDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }

    @Bean
    ApplicationRunner inspectArgs() {
        return args -> {
            System.out.println("tag -> " + describe(args, "tag"));
            System.out.println("verbose -> " + describe(args, "verbose"));
            System.out.println("empty -> " + describe(args, "empty"));
            System.out.println("missing -> " + describe(args, "missing"));
            System.out.println("enabled -> " + describe(args, "enabled"));

            System.out.println(
                    "nonOptions=" + args.getNonOptionArgs());
            System.out.println(
                    "sourceArgCount=" + args.getSourceArgs().length);

            // Multi-valued option: if present, must have values.
            List<String> tags = requiredValues(args, "tag");
            System.out.println("tagsValidated=" + tags);

            // Flag policy: present without value => true.
            System.out.println(
                    "verboseFlag=" + booleanFlag(
                            args, "verbose", false));
            System.out.println(
                    "enabledFlag=" + booleanFlag(
                            args, "enabled", true));
        };
    }

    private static String describe(ApplicationArguments args,
                                   String name) {
        if (!args.containsOption(name)) {
            return "ABSENT";
        }

        List<String> values = args.getOptionValues(name);
        if (values == null || values.isEmpty()) {
            return "PRESENT_NO_VALUE";
        }

        // Mark empty strings so List.toString() does not mislead.
        String display = values.stream()
                .map(v -> v.isEmpty() ? "<empty-string>" : v)
                .collect(Collectors.joining(", ", "[", "]"));

        return "VALUES(" + values.size() + ")=" + display;
    }

    private static List<String> requiredValues(
            ApplicationArguments args, String name) {

        if (!args.containsOption(name)) {
            return List.of();
        }

        List<String> values = args.getOptionValues(name);
        if (values == null || values.isEmpty()) {
            throw new IllegalArgumentException(
                    "--" + name + " must have at least one value");
        }

        List<String> clean = new ArrayList<>();
        for (String value : values) {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException(
                        "--" + name + " must not have blank values");
            }
            clean.add(value);
        }
        return List.copyOf(clean);
    }

    private static boolean booleanFlag(
            ApplicationArguments args,
            String name,
            boolean defaultValue) {

        if (!args.containsOption(name)) {
            return defaultValue;
        }

        List<String> values = args.getOptionValues(name);
        if (values == null || values.isEmpty()) {
            return true;
        }

        if (values.size() != 1) {
            throw new IllegalArgumentException(
                    "--" + name + " accepts only one boolean value");
        }

        return switch (values.get(0).toLowerCase(Locale.ROOT)) {
            case "true" -> true;
            case "false" -> false;
            default -> throw new IllegalArgumentException(
                    "--" + name + " must be true or false");
        };
    }
}
~~~

**Points to observe in the code:**

1. `ApplicationRunner` is a bean invoked by Spring Boot after context refresh. It receives the `ApplicationArguments` for the same run via the `run()` parameter.
2. `describe(...)` distinguishes absent, no value, and one or more values; it **never prints a list containing an empty string without marking it**.
3. `requiredValues(...)` uses the parsed value list, rejecting bare `--tag` without a value and `--tag=` with an empty value. It **does not yet inspect each raw token** to reject a valueless `--tag` alongside `--tag=red`; section 10 shows how to solve that if the contract must be stricter.
4. `booleanFlag(...)` applies the policy: absent uses default; `--verbose` enables; `--enabled=false` disables; multiple boolean values raise an error.
5. `@Bean` does not require splitting `String[]` manually; `ApplicationArguments` is the API built for this scenario.
6. All classes and methods reside in a single Java file, without depending on a database, network, or any additional startup mechanism.

### 7.3. Run command and expected stdout

In the directory containing `pom.xml`:

~~~bash
mvn package
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag=red --tag=blue --verbose --empty= --enabled=false invoice.csv
~~~

The command passes **six tokens** to the application, in exact order:

~~~text
--tag=red
--tag=blue
--verbose
--empty=
--enabled=false
invoice.csv
~~~

The lines **printed by the demo code** (ignoring Spring Boot/Maven banners and logs) have exact content:

~~~text
tag -> VALUES(2)=[red, blue]
verbose -> PRESENT_NO_VALUE
empty -> VALUES(1)=[<empty-string>]
missing -> ABSENT
enabled -> VALUES(1)=[false]
nonOptions=[invoice.csv]
sourceArgCount=6
tagsValidated=[red, blue]
verboseFlag=true
enabledFlag=false
~~~

Why is the output accurate?

- `tag` has two `--tag=value` occurrences, so the list has two elements `red`, `blue`.
- `verbose` appears as `--verbose`, so it is present with an empty value list.
- `empty` appears as `--empty=`, so it has one empty value: `VALUES(1)`, not `PRESENT_NO_VALUE`.
- `missing` does not appear at all, hence `ABSENT`.
- `enabled=false` holds string value `false`; the boolean policy turns it into `false`.
- `invoice.csv` has no `--` prefix, so it is a non-option.
- `getSourceArgs().length` counts raw tokens, not unique option names.
- `tagsValidated` preserves the order of valid values; `verboseFlag` resolves to `true` under the present-without-value convention.

Try replacing `--empty=` with `--empty`. That output line switches from `VALUES(1)=[<empty-string>]` to `PRESENT_NO_VALUE`.

### 7.4. Additional test commands

**Only one tag value:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag=red
~~~

Here the tag output will be `VALUES(1)=[red]`, `tagsValidated=[red]`, `verboseFlag=false` (absent, default false), `enabledFlag=true` (absent, default true), `sourceArgCount=1`, and `nonOptions=[]`.

**Valueless tag:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag
~~~

The line describing tag is `PRESENT_NO_VALUE`; then `requiredValues(...)` throws `IllegalArgumentException`. Startup does not complete on the success path because the runner failed. Exception logs and exit codes may vary by environment.

**Tag with one empty element:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag=
~~~

The description line is `VALUES(1)=[<empty-string>]`, after which `requiredValues(...)` rejects it due to the blank value.

**Repeating a flag with two values:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --enabled=true --enabled=false
~~~

The `enabled` line shows `VALUES(2)=[true, false]`; `booleanFlag(...)` throws an error because the policy **accepts only one boolean value**. It does not implicitly enforce a "last wins" rule.

**One option and one non-option caused by space separation:**

~~~bash
java -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag red
~~~

`--tag` remains an option **without a value**; `red` is a non-option. Do not treat this as equivalent to `--tag=red`.

## 8. Should you use ApplicationArguments or Environment/@Value?

Spring Boot also puts command-line arguments into `Environment` as a `CommandLinePropertySource` (unless the application explicitly disables adding command-line properties). Hence, in many projects you can read a value via `Environment.getProperty("name")`, `@Value`, or `@ConfigurationProperties`.

However, **the two APIs have different goals**:

| Need | Prefer |
| --- | --- |
| Know whether an option was passed, including valueless `--flag` | `ApplicationArguments.containsOption()` |
| Keep every value of `--tag=a --tag=b` | `ApplicationArguments.getOptionValues()` |
| Distinguish absent, no value, empty string | `ApplicationArguments` + size check |
| Count exact occurrences of a token | `getSourceArgs()` and custom parser if needed |
| Read a configuration property across sources with precedence | `Environment` or `@ConfigurationProperties` |
| Bind typed app config with validation and defaults | `@ConfigurationProperties` and validation |
| Access raw original argument array | `getSourceArgs()` or `CommandLineRunner` |

**Do not convert a value list into a single string and treat it as raw data.** `CommandLinePropertySource` is a `PropertySource` serving the configuration system; converting multiple values into a single property string can lose original separation or make it look like a comma-containing value. If you need to keep `["red", "blue"]` distinct, read `getOptionValues("tag")` directly.

For example, `--tag=red,blue` is only **one** value `red,blue` per `ApplicationArguments`; whereas `--tag=red --tag=blue` is **two** values. If business logic wants to accept both forms, document the contract clearly and apply a validated comma-splitting step yourself. If data may validly contain commas, naive `String.split(",")` can corrupt data.

### Can @ConfigurationProperties replace ApplicationArguments?

Not completely. `@ConfigurationProperties` excels at binding configuration into typed beans, especially when the app has multiple configuration sources. However, it is **not an API that expresses every CLI token-level distinction**, such as an absent option versus a present valueless option.

If this is a CLI with multiple multi-valued options, flags, presence/absence rules, and error reporting tied closely to the command line, `ApplicationArguments` (or a dedicated CLI library like picocli if the system truly needs it) is usually the clearer entry point.

## 9. Repeated values, defaults, and merge strategies

An option having multiple values does not automatically tell the application how to process them. Define a contract:

| Option Kind | Example | Recommended Policy |
| --- | --- | --- |
| Multi-valued list | `--tag=red --tag=blue` | Preserve order, validate each element |
| Deduplicated set | `--feature=A --feature=A` | Optionally deduplicate intentionally, log/report clearly |
| Single unique value | `--mode=fast` | Reject multiple values rather than picking arbitrarily |
| Boolean flag | `--dry-run` | Present without value => true per policy |
| Explicit boolean | `--dry-run=false` | Parse `true|false` strictly |
| Clearable string | `--label=` | Optionally allow `""` to mean "clear" |
| Required string | `--endpoint=https://...` | Reject missing or empty strings |
| Positional argument | `report.csv` | Process with `getNonOptionArgs()` |

There is no single policy right for every business domain. For critical data (environment targets, permissions, delete operations), do not silently apply "last value wins" if the user passes two conflicting values. If selecting first or last is required, document it in CLI docs and test it.

### Is an absent option different from a false flag?

It can be. Consider a configuration-update program:

- No `--enabled`: **do not change existing configuration**.
- `--enabled=true`: set to true.
- `--enabled=false`: set to false.

In this problem, a primitive `boolean` cannot express all three states. You can use a nullable `Boolean` or an enum/record representing `UNSPECIFIED`, `TRUE`, `FALSE`. Avoid equating absent with false automatically, as doing so can accidentally alter configuration when the user did not ask for it.

Likewise, `--name=` may mean **clearing** an old value, unlike omitting `--name`. Evaluate business requirements before normalizing empty strings to null.

## 10. A subtle issue: repeating options both with and without values

Suppose the user passes:

~~~bash
java -jar app.jar --tag --tag=red --tag=blue
~~~

`containsOption("tag")` is true. The list from `getOptionValues("tag")` may still contain only **actual values** such as `["red", "blue"]`; the valueless `--tag` occurrence does not necessarily appear as a null element. This is a consequence of the API **representing values**, not being a complete log of every option occurrence.

If business rules require every `--tag` occurrence to have `=value`, inspect the raw tokens. The following is a helper that can be placed in the class from section 7:

~~~java
private static boolean hasValuelessOccurrence(
        ApplicationArguments arguments, String name) {

    String token = "--" + name;

    for (String raw : arguments.getSourceArgs()) {
        if ("--".equals(raw)) {
            break; // After delimiter are non-options.
        }
        if (raw.equals(token)) {
            return true;
        }
    }
    return false;
}
~~~

This is **a syntactically complete Java method, though not a standalone program**, because it needs `ApplicationArguments` and an enclosing class.

Then, when `tag` is a required multi-valued option:

~~~java
if (hasValuelessOccurrence(args, "tag")) {
    throw new IllegalArgumentException(
            "Every --tag must have the form --tag=value");
}
List<String> tags = requiredValues(args, "tag");
~~~

This snippet **illustrates usage within the section 7 class**: add the helper method above to the class. This blocks mixed inputs that include a valueless `--tag`. It intentionally stops at the `--` end delimiter so a positional token starting with `--tag` is not mistaken for an option.

If you want to count option occurrences accurately, you can also iterate `getSourceArgs()` and count tokens matching `"--tag".equals(raw)` or `raw.startsWith("--tag=")` before the delimiter. **Do not use `raw.startsWith("--tag")` alone** because it would miscount `--tags`, `--tag-extra`, and other names.

### Notes on ordering and preprocessing

Reserve `getSourceArgs()` for cases where token-level details are genuinely needed, not because `ApplicationArguments` is "bad". For most applications, the list from `getOptionValues` suffices to read parsed values; writing a diverging custom parser can cause syntax mismatches with Spring.

If CLI requirements grow complex—such as short aliases (`-v`), required option groups, subcommands, auto-generated help, type conversion, and detailed error messages—consider a dedicated CLI library instead of maintaining a large homegrown parser.

## 11. Differences between application arguments and JVM arguments

Not everything called an "argument" passes through `ApplicationArguments`:

~~~bash
java -Xmx512m -Dapp.mode=fast -jar app.jar --tag=red --verbose
~~~

Distinction:

- `-Xmx512m` is a **JVM** option, not present in the application's `String[] args`.
- `-Dapp.mode=fast` sets a **Java system property**, also not an application token when placed before `-jar`.
- `--tag=red` and `--verbose` sit **after the JAR name**, are passed by Java to `main(String[] args)`, and then put into `ApplicationArguments` by Spring Boot.

Placing tokens in the wrong position can completely change how the Java launcher and the application interpret parameters. For Docker/Kubernetes applications, check `ENTRYPOINT` and `CMD`/`args` carefully: a shell-form command string can be processed differently from the argv array supplied by the container runtime.

### When running via Maven

You can pass application arguments to the `spring-boot:run` goal via the corresponding plugin parameter (such as `spring-boot.run.arguments`), though quoting syntax depends on the shell and Maven. To test repeated cases or `--name=` reliably, the lesson's **`mvn package` + `java -jar ...`** approach makes observing input much simpler.

## 12. Common mistakes and fixes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `NullPointerException` when calling `getOptionValues(...).size()` | Absent option returns null | Check `containsOption` or null before using |
| `--verbose` is treated as false | Reading only empty list or using wrong boolean parser | Define policy: present/no-value => true if flag semantics desired |
| `--verbose=false` is still treated as true | Using only `containsOption` | Read and parse `getOptionValues` |
| `--name=` is confused with `--name` | `List.toString()` prints ambiguously | Print size, length, and mark empty strings |
| `--tag=a --tag=b` retains only one value | Using `Environment.getProperty` or overwriting a `Map<String,String>` | Use `getOptionValues("tag")` |
| `--tag a` does not set tag to `a` | Parser requires same token `--tag=a` | Fix user syntax, or use another CLI parser if needed |
| `--tag=a,b` does not yield two elements | Comma is inside one string value | Choose an explicit comma-splitting policy if supporting it |
| `--tag --tag=a` misses the valueless occurrence | Parsed list retains values only | Check `getSourceArgs()` before delimiter |
| `--flag=true --flag=false` runs unpredictably | No duplicate policy or implicit first/last value | Reject duplicates or publish clear precedence rules |
| `-v` does not enable verbose | Default parser does not auto-map short aliases | Use `--verbose` or a CLI library supporting aliases |
| An option after `--` is not parsed | That is the end-of-options delimiter | Use proper syntax or inspect non-options |
| `getOptionNames()` omits duplicate names | Method returns a Set | Use `getOptionValues` or source args as needed |
| Data with spaces gets split | Shell did not quote the value | Quote as one token according to the active shell |
| Output contains secrets | Logging raw args or passwords/tokens | Print only safe info; redact before logging |
| Runner errors after Started log | Runner executes after `ApplicationStartedEvent` | Diagnose inside `ApplicationRunner` and startup failure; do not treat Started log as ready |

### Practical troubleshooting guide

1. Determine the **actual token array** received by `main(String[] args)`, not the shell-altered command line.
2. Check `containsOption(name)` to distinguish absent from present.
3. Check `getOptionValues(name) == null`, then `size()` and each element's content; do not rely solely on `toString()`.
4. Check `getNonOptionArgs()` if the user typed `--name value` or used the `--` delimiter.
5. If you must identify every occurrence, use `getSourceArgs()` and count exact tokens, stopping at the delimiter.
6. Classify each option as **flag, single-valued, or multi-valued**, then apply duplicate, missing, and empty policies accordingly.
7. When parsing fails, raise **actionable** errors: e.g., "Every --tag must have the form --tag=value", rather than letting NPE or `IndexOutOfBoundsException` escape.
8. Never print the entire command line containing tokens, passwords, or sensitive info. For production diagnostics, logging allowed option names and structural info is safer than logging values.

## 13. Security and operability

**Do not log secrets via the command line.** Arguments like `--token=...`, `--password=...` may appear in logs, command history, or process-inspection tools depending on the OS. When displaying usage/debug info, mask sensitive values; for real secrets, prefer properly designed secret-management mechanisms.

**Validate multi-value data before use.** An option containing a list of endpoints, paths, or permissions must have every value validated. Never pass raw user strings into shell/SQL commands, and do not treat the command-line parser as a data-sanitization layer.

**Set reasonable limits.** If a repeated option can appear multiple times, consider bounding the count and length of each value. A user or misconfigured deployment might pass thousands of values, impacting memory, startup time, and I/O cost.

**Do not let ambiguous flags trigger dangerous actions.** Commands like `--delete`, `--force`, `--allow-unsafe` need explicit contracts; they may require confirmation or dedicated validation rather than inferring from mere option presence.

**Do not turn the parser into mutable runtime configuration.** `ApplicationArguments` describes input at the start of `SpringApplication.run`. If configuration needs updating while the app is running, use an appropriate configuration/state management mechanism rather than assuming CLI values change dynamically.

## 14. Knowledge check questions

**Q1:** Without passing `--debug`, what is `getOptionValues("debug")`?

**Answer:** `null`, and `containsOption("debug")` is false.

**Q2:** What happens when passing `--debug` without an equals sign?

**Answer:** `containsOption("debug")` is true, while `getOptionValues("debug")` is an empty list. Depending on business rules, this can be treated as an enabled flag.

**Q3:** Is passing `--debug=` the same as `--debug`?

**Answer:** No. The form with an equals sign contains **one empty string** in the value list; the form without an equals sign is a **zero-element list**.

**Q4:** When passing `--tag=red --tag=blue`, what does `getOptionValues("tag")` return?

**Answer:** A list containing two elements `red` and `blue` in parsed order.

**Q5:** Does `getOptionNames()` return `tag` twice when `tag` is repeated twice?

**Answer:** No, because the result is a `Set<String>` of unique option names, not a token log.

**Q6:** When passing `--foo bar`, is the value of `foo` equal to `bar`?

**Answer:** Not under this parser. `--foo` is a valueless option and `bar` is a non-option. To supply a value, you must use `--foo=bar`.

**Q7:** Is `--tag=red,blue` automatically split into two values?

**Answer:** No. The parser stores a single string `red,blue`. If comma splitting is desired, the application must define and perform the conversion step itself.

**Q8:** Does `--flag=false` make `containsOption("flag")` return false?

**Answer:** No. `containsOption` checks name presence; it does not parse boolean values.

**Q9:** With `--tag --tag=red`, can you reliably detect the valueless occurrence using only `getOptionValues("tag").size()`?

**Answer:** No. The API primarily stores values attached to the name. To verify each occurrence, inspect raw tokens in `getSourceArgs()` according to parser syntax.

**Q10:** Why should `getSourceArgs()` not be logged in production?

**Answer:** Because tokens may contain passwords, tokens, credentials, or private data. Redact and use safe structured logging instead.

## 15. Practice exercises

### Exercise A — distinguishing four states

Run the example with the inputs:

~~~text
(no --name)
--name
--name=
--name=Alice
~~~

Update the `describe` line to inspect option `name`. Record `containsOption`, `getOptionValues` result, element count, and desired business handling.

### Exercise B — controlling repeated options

Run:

~~~text
--tag=red --tag=blue --tag=red
~~~

Implement three alternative policies: keep all three, deduplicate values, and throw an error on duplicate values. Use `LinkedHashSet` if you need deduplication while preserving appearance order. Explain the impact of each choice on the output.

### Exercise C — checking valueless occurrences

Run:

~~~text
--tag --tag=red --tag=blue
~~~

Add the `hasValuelessOccurrence` helper from section 10 to the program and reject input if any `--tag` token lacks `=value`. Then run:

~~~text
--tag=red -- --tag
~~~

Explain why the `--tag` token **after the delimiter** must be treated as a non-option, not an error on the `tag` option.

### Exercise D — strict booleans

Test four cases:

~~~text
--enabled
--enabled=true
--enabled=false
--enabled=
~~~

Compare with using `containsOption` alone. Explain why a policy supporting explicit `false` cannot rely solely on `containsOption`.

### Exercise E — JVM arguments vs. application arguments

Run:

~~~bash
java -Dapp.note=test -jar target/args-demo-0.0.1-SNAPSHOT.jar --tag=red
~~~

Verify that Spring Boot's `getSourceArgs()` does not contain `-Dapp.note=test`, because it is a Java system property passed to the JVM before `-jar`.

## 16. References and key takeaways

Official sources to cross-check against your project's actual version:

- Spring Boot 3.5 — [ApplicationArguments Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/ApplicationArguments.html): contract of `containsOption`, `getOptionValues`, `getOptionNames`, `getSourceArgs`, and non-options.
- Spring Boot 3.5 — [DefaultApplicationArguments Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/DefaultApplicationArguments.html): default implementation and constructor accepting `String... args`.
- Spring Boot 3.5 — [SpringApplication: Accessing Application Arguments](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): injecting `ApplicationArguments`, comparing runners, and command-line properties.
- Spring Framework 6.2 — [SimpleCommandLinePropertySource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html): `--name[=value]` syntax, repeated options, empty strings, and the `--` delimiter.
- Spring Framework 6.2 — [CommandLineArgs](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/core/env/CommandLineArgs.html): data structure holding options and their value lists.

**Key takeaways:**

1. `ApplicationArguments.getOptionValues(name)` has **three basic return categories**: `null` if the option is absent, an empty list if present without a value, and a list of one/more strings if values are present.
2. **`--foo` differs from `--foo=`**: no value differs from one empty-string value.
3. **`--tag=red --tag=blue`** has two values; **`--tag=red,blue`** has one value containing a comma.
4. Use `containsOption` to check **presence**, not alone to parse a boolean that may accept `false`.
5. A repeated option can include a valueless occurrence; to check **each occurrence**, inspect `getSourceArgs()` and match exact tokens.
6. With the standard parser, **`--tag red` is not equivalent to `--tag=red`**, and tokens after the `--` delimiter are non-options.
7. `getOptionNames()` returns **unique names** only; `getNonOptionArgs()` returns positional args; `getSourceArgs()` returns raw input.
8. Applications should explicitly define **single-valued/multi-valued/boolean options**, how empty values, duplicates, and input errors are handled, avoiding surprising defaults.
9. To read properties through the configuration system, use `Environment`/`@ConfigurationProperties`; to preserve CLI structure and multi-values, use `ApplicationArguments`.
10. Never log sensitive arguments; bound inputs and report clear errors before executing business tasks.
