# Quotes and Special Characters When Running in PowerShell or Unix Shells

## 1. Why does Spring Boot configuration get altered right before the application receives it?

In Spring Boot 3.3, you can supply configuration using environment variables or startup arguments. At first glance, these two commands look like setting a simple string:

```bash
APP_MESSAGE="Welcome $USER" java -jar app.jar
```

```powershell
$env:APP_MESSAGE = "Welcome $HOME"
java -jar .\app.jar
```

However, **the shell processes quotes and special characters before Java or Spring Boot ever reads the value**. In Bash, `$USER` can be replaced with the username; in PowerShell, `$HOME` can be replaced with the user home directory path. Quotes are only shell syntax and usually do not appear in the value received by the Java process.

If a URL contains `&`, a string contains `$`, a test password contains `!`, or a path contains spaces, the launch command can yield unexpected results, split into multiple arguments, or even be interpreted by the shell as control operators.

This lesson helps you:

- Distinguish the string you **type in the terminal** from the value Spring Boot **actually sees**.
- Know when to choose **single quotes** versus **double quotes** in Bash on Unix and in PowerShell.
- Pass values containing spaces, `$`, `#`, `&`, `;`, `|`, `*`, `?`, quotes, backslashes, and JSON into environment variables correctly.
- Understand differences between passing via **environment variable**, **`--key=value` argument**, and **JVM `-Dkey=value` property**.
- Verify the received result from `Environment` or `@ConfigurationProperties` in Spring Boot 3.3.

Examples use Java 17+, Spring Boot 3.3.x, **Bash** for Unix shells, and **PowerShell** for Windows/cross-platform. `app.jar` is an illustrative JAR name; substitute your application's JAR path.

## 2. Three layers to distinguish: shell → Java process → Spring Boot

A configuration bug can occur at one of three layers:

```text
You type text in the terminal
          |
          v
Bash or PowerShell parses the command
- determines argument boundaries
- strips syntactic quotes
- performs variable interpolation when applicable
- handles $, &, ;, |, *, ?, spaces, escapes...
          |
          v
Java process receives
- environment variable table (environment)
- startup argument array (arguments)
- JVM system properties (system properties)
          |
          v
Spring Boot 3.3 builds PropertySource / Environment
- converts environment variable names to configuration keys
- selects effective values by precedence
- resolves placeholders when applicable
- binds values into Java types
          |
          v
Beans consume configuration
```

Example in Bash:

```bash
APP_MESSAGE='Hello $USER & goodbye' java -jar app.jar
```

With single quotes, the shell preserves `$USER` and `&` literally in `APP_MESSAGE`. Java does not receive the two outer quotes. When Spring Boot reads `APP_MESSAGE` under key `app.message`, the supplied content is:

```text
Hello $USER & goodbye
```

Meanwhile:

```bash
APP_MESSAGE="Hello $USER & goodbye" java -jar app.jar
```

Bash replaces `$USER` with the value of `USER` if set, while `&` sits **inside double quotes** so it remains literal text. If `USER=alice`, the value will be:

```text
Hello alice & goodbye
```

Two strings look nearly identical, yet produce different outcomes because **the shell interpolated first**. This is not Spring Boot-specific behavior.

## 3. Naming environment variables for Spring Boot properties

You must get both the **variable name** and the **variable value** right. For example, `application.properties` has:

```properties
app.message=Default value
app.timeout=5s
app.feature-enabled=false
```

When using `@ConfigurationProperties`, Spring Boot uses **relaxed binding** to map canonical configuration names to environment variables.

Rule for converting lowercase hyphenated property names to environment variables:

1. Replace dots `.` with underscores `_`.
2. Remove hyphens `-`.
3. Convert to uppercase.

Examples:

| Spring Boot key | Environment variable name |
| --- | --- |
| `app.message` | `APP_MESSAGE` |
| `app.timeout` | `APP_TIMEOUT` |
| `app.feature-enabled` | `APP_FEATUREENABLED` |
| `app.client.connect-timeout` | `APP_CLIENT_CONNECTTIMEOUT` |
| `spring.main.log-startup-info` | `SPRING_MAIN_LOGSTARTUPINFO` |
| `server.port` | `SERVER_PORT` |

In particular, `app.feature-enabled` corresponds to **`APP_FEATUREENABLED`**; do not assume inserting `_` where the hyphen stood is always equivalent. Variable names on Unix are also case-sensitive; follow the uppercase convention.

Quotes around a **value**, such as `'Hello world'`, do not alter rules for **variable names**. Before suspecting a quoting bug, verify the application is querying the right key.

In typical cases, the environment variable source can override `application.properties`/YAML files. However, command-line arguments, JVM properties, JSON sources, profiles, and other sources participate in Spring Boot's precedence order. Sometimes an environment variable was passed correctly, yet the final value was overridden by a higher-priority source.

## 4. Bash on Unix: single quotes

Single quotes `'...'` are the simplest choice when you want to **preserve characters inside verbatim**. Bash does not interpolate `$VARIABLE`, does not execute `$(...)`, and does not treat `&`, `;`, `|`, `*`, or `?` as shell operators when inside single quotes.

Example:

```bash
APP_MESSAGE='Price $5; use A&B | C#1 * ?.txt' java -jar app.jar
```

The `APP_MESSAGE` environment variable receives the exact text:

```text
Price $5; use A&B | C#1 * ?.txt
```

No extra commands are executed by `;`, `&`, or `|` inside the quoted string. The `*.txt` pattern is also not expanded into a filename list.

An example with a URL containing query parameters:

```bash
APP_ENDPOINT='https://api.example.test/search?q=red+blue&page=2&sort=desc' \
  java -jar app.jar
```

The `&` in the URL remains part of the value. The trailing `\` at the end of the line in the example is **Bash line-continuation syntax**; it is not part of the URL.

An example string containing double quotes:

```bash
APP_MESSAGE='He said "run now" & stopped.' java -jar app.jar
```

The `"` inside single quotes is ordinary text. Java can receive:

```text
He said "run now" & stopped.
```

### 4.1. What if you need a literal single quote?

Bash does not allow embedding a single quote inside `'...'` merely with `\'` **inside** the quotes. The standard pattern is closing the single quote, inserting an escaped single quote outside, and reopening:

```bash
APP_MESSAGE='It'\''s ready' java -jar app.jar
```

Result:

```text
It's ready
```

Another simple case can use double quotes if the content contains no characters requiring interpolation:

```bash
APP_MESSAGE="It's ready" java -jar app.jar
```

For complex configurations with many quotes and special characters, consider putting the content in an appropriate configuration file instead of crafting hard-to-read shell strings.

### 4.2. The `!` character in interactive Bash

Bash has **history expansion**, often enabled in interactive sessions. The `!` character can carry special meaning, even inside some double-quoted strings.

Example string:

```bash
APP_MESSAGE='Hello! Please retry!' java -jar app.jar
```

Single quotes keep the `!` characters literal.

Do not rely on how interactive Bash handles:

```bash
APP_MESSAGE="Hello! Please retry!" java -jar app.jar
```

because history expansion can alter string parsing depending on situation and shell settings. In many non-interactive scripts, history expansion is off by default, yet choosing single quotes remains more predictable when literal `!` characters are needed.

## 5. Bash on Unix: double quotes

Double quotes `"..."` preserve spaces and most special characters as part of a value, while **still allowing variable interpolation, command substitution, and certain backslash escapes**.

Example:

```bash
USER_LABEL='Lan'
APP_MESSAGE="Hello $USER_LABEL" java -jar app.jar
```

The passed value is:

```text
Hello Lan
```

In Bash, `$(...)` also executes a command and substitutes its output:

```bash
APP_MESSAGE="Built on $(date +%Y-%m-%d)" java -jar app.jar
```

If you **want to keep** the string `$(date +%Y-%m-%d)` verbatim for the application to read as text, you must use single quotes:

```bash
APP_MESSAGE='Built on $(date +%Y-%m-%d)' java -jar app.jar
```

Or escape the special characters properly inside double quotes:

```bash
APP_MESSAGE="Literal \$HOME and \"quoted\"" java -jar app.jar
```

Expected value:

```text
Literal $HOME and "quoted"
```

Inside Bash double quotes, `\` has special meaning before `$`, double quote, backslash, backtick, and newline. Therefore, **there is no single "one backslash escapes everything" rule for every case**.

### 5.1. Why do `'$HOME'` and `"$HOME"` differ?

```bash
APP_MESSAGE='$HOME' java -jar app.jar
```

Passes the exact five characters `$HOME`.

```bash
APP_MESSAGE="$HOME" java -jar app.jar
```

Passes the value of the `HOME` variable, such as `/home/lan`.

Double quotes do not mean "keep text literal"; they mean **keep as a single string while still performing allowed interpolations**.

### 5.2. Backslash without quotes

Outside quotes, `\` in Bash usually escapes the meaning of the character immediately following it:

```bash
APP_MESSAGE=Hello\ World java -jar app.jar
```

Produces the value `Hello World`.

However, when values contain multiple special characters, long strings filled with `\` are harder to maintain than writing:

```bash
APP_MESSAGE='Hello World' java -jar app.jar
```

**Easy rule to remember:** use single quotes when you want verbatim text; use double quotes when you intentionally want the shell to insert variable values or command output.

## 6. Bash: setting variables for one command vs. exporting for multiple commands

### 6.1. Applying to a single command only

In Bash and common POSIX shells, you can place variable assignments directly before the command:

```bash
APP_MESSAGE='Only for this run' APP_TIMEOUT='2s' java -jar app.jar
```

These variables are passed to that command's Java process. Once the command finishes, this assignment style does not persist settings for subsequent runs.

This is very handy when comparing two runs:

```bash
APP_MESSAGE='Run A' java -jar app.jar
APP_MESSAGE='Run B' java -jar app.jar
```

### 6.2. Using `export` for subsequent child processes

```bash
export APP_MESSAGE='Exported for the current shell'
export APP_TIMEOUT='4s'

java -jar app.jar
```

Once a variable is exported, Java processes launched from that shell can inherit it. If you only write:

```bash
APP_MESSAGE='Not exported'
java -jar app.jar
```

do not expect the Java process to receive the variable; a normal shell variable must be exported for child processes to inherit it.

You can also use the `env` utility on Unix:

```bash
env APP_MESSAGE='Value with space & $' APP_TIMEOUT='4s' java -jar app.jar
```

This command supplies environment variables to the invoked process. **Do not copy `env NAME=value command` verbatim into PowerShell assuming it is equivalent PowerShell syntax.**

### 6.3. Checking in the shell before running the application

With **non-sensitive illustrative values**:

```bash
export APP_MESSAGE='A & B; literal $HOME'
printf '%s\n' "$APP_MESSAGE"
```

Output:

```text
A & B; literal $HOME
```

Use `"$APP_MESSAGE"` in `printf` to avoid unexpected word splitting or filename globbing.

When finished practicing:

```bash
unset APP_MESSAGE
unset APP_TIMEOUT
```

Note that `unset` in the current shell does not remove configuration already received by another Java process when it started.

## 7. PowerShell: single quotes

In PowerShell, `'...'` is also a **literal/verbatim string**: no `$name` interpolation and no `$(...)` expression evaluation inside.

Example:

```powershell
$env:APP_MESSAGE = 'Price $5; use A&B | C#1 * ?.txt'
java -jar .\app.jar
```

Java receives:

```text
Price $5; use A&B | C#1 * ?.txt
```

The major difference from Bash lies in **environment variable assignment syntax**:

```powershell
$env:APP_MESSAGE = 'Hello from PowerShell'
java -jar .\app.jar
```

PowerShell uses the `Env:` drive provider via `$env:NAME`. The syntax:

```bash
APP_MESSAGE='Hello' java -jar app.jar
```

is common in Bash, **not PowerShell's direct environment variable assignment syntax**.

Another PowerShell command with a path containing spaces:

```powershell
$env:APP_MESSAGE = 'Hello A & B'
java -jar 'C:\Workspaces\My Demo\app.jar'
```

Single quotes around the path ensure PowerShell treats the JAR path as one argument. The syntactic quotes are not part of the path.

### 7.1. Literal single quotes inside a PowerShell string

Inside PowerShell single-quoted strings, write **two consecutive single quotes** to represent one literal single quote:

```powershell
$env:APP_MESSAGE = 'It''s ready'
```

Actual value:

```text
It's ready
```

This is **not** Bash's `'It'\''s ready'` syntax. If writing scripts intended for both shells, separate the syntax for each.

### 7.2. Double quotes inside single quotes

```powershell
$env:APP_MESSAGE = 'He said "Hello!" and left.'
```

PowerShell preserves both `"` and `!` inside the string:

```text
He said "Hello!" and left.
```

When values contain multiple `$`, double quotes, and control characters, using PowerShell single-quoted strings is usually more readable than escaping every character.

## 8. PowerShell: double quotes, interpolation, and backtick

Double quotes in PowerShell allow variable and expression interpolation:

```powershell
$name = 'Lan'
$env:APP_MESSAGE = "Hello $name"
```

The value passed to the child process is:

```text
Hello Lan
```

With an environment variable:

```powershell
$env:APP_MESSAGE = "Home: $env:USERPROFILE"
```

If `USERPROFILE` has a value, PowerShell substitutes it into the string. In other environments `$HOME` may be used, yet **that is a PowerShell variable** and its expansion still belongs to the shell layer.

PowerShell uses the **backtick** (`` ` ``) to escape certain characters in double-quoted strings, not backslash as in Bash.

Example:

```powershell
$env:APP_MESSAGE = "Literal `$HOME and `"quoted`""
```

Expected value:

```text
Literal $HOME and "quoted"
```

Inside double-quoted strings, `` `n `` represents a newline and `` `t `` represents a tab:

```powershell
$env:APP_MESSAGE = "First line`nSecond line"
```

The received value contains an actual newline character between `First line` and `Second line`.

Put the same string in single quotes:

```powershell
$env:APP_MESSAGE = 'First line`nSecond line'
```

and the two characters backtick and `n` remain literal, without converting into a newline.

### 8.1. PowerShell does not use backslash as a general quote escape

Do not carry Bash habits straight into PowerShell:

```powershell
$env:APP_MESSAGE = "He said \"hello\""
```

`\` is not a quote escape character in PowerShell string syntax. The statement may parse differently than expected.

Simpler ways to write it:

```powershell
$env:APP_MESSAGE = 'He said "hello"'
```

Or:

```powershell
$env:APP_MESSAGE = "He said `"hello`""
```

When no interpolation is needed, single quotes are clearer and less error-prone.

### 8.2. Note when passing arguments directly to native programs

PowerShell invokes `java.exe` as a **native command**. How arguments containing embedded quotes are forwarded to native programs has historically differed between Windows PowerShell 5.1 and PowerShell 7.x; newer PowerShell versions also have settings affecting argument passing.

For simple values with spaces, you can write:

```powershell
java -jar .\app.jar '--app.message=Hello world'
```

However, for long JSON payloads or strings containing double quotes, single quotes, and backslashes simultaneously, **prefer explicitly assigned environment variables**, or verify how your specific PowerShell version passes argv to `java.exe`.

In PowerShell, the `&` call operator can be used to **invoke a program from a quoted path**, for example:

```powershell
& 'C:\Program Files\Java\jdk-17\bin\java.exe' -jar '.\app.jar'
```

That is `&` in command-invocation syntax position. An `&` inside a single-quoted string like `'A&B'` is just literal text. Do not confuse command invocation syntax with configuration value content.

## 9. Quoting comparison table: Bash and PowerShell

| Scenario | Bash on Unix | PowerShell |
| --- | --- | --- |
| Keep `$HOME` literal | `'$HOME'` | `'$HOME'` |
| Let shell interpolate `name` | `"$name"` | `"$name"` |
| Keep `$(...)` literal | `'$(date)'` | `'$(Get-Date)'` |
| Include `"` in value | `'He said "go"'` | `'He said "go"'` |
| Include one `'` in literal string | `'It'\''s'` | `'It''s'` |
| Keep `&`, `;`, `\|` literal | `'A&B;C\|D'` | `'A&B;C\|D'` |
| Keep `!` literal | `'Hello!'` | `'Hello!'` |
| Insert newline via shell syntax | `$'A\nB'` (Bash-specific) | `"A`nB"` |
| Escape `$` in double quotes | `"\$HOME"` | `` "`$HOME" `` |
| Assign environment variable | `export APP_MESSAGE='value'` | `$env:APP_MESSAGE = 'value'` |
| Set variable for one command only | `APP_MESSAGE='value' java -jar app.jar` | Set `$env:`, run command, remove variable afterward |

**Note on the table:** many snippets across the two columns look alike, yet subtle differences exist for single quotes, escape characters, and passing arguments to native programs. When copying a command from Linux to Windows, update **all shell syntax appropriately**, not just `/` to `\`.

## 10. Common special characters in configuration values

### 10.1. Spaces and tabs

Do not pass URLs, filenames, or messages containing whitespace as unquoted arguments:

```bash
java -jar app.jar --app.message=Hello World
```

In Bash, `World` can become a separate argument. In PowerShell similarly, native argument passing should not rely on the shell guessing intent.

Instead use:

```bash
java -jar app.jar '--app.message=Hello World'
```

In PowerShell:

```powershell
java -jar .\app.jar '--app.message=Hello World'
```

Or set an environment variable before invoking the application:

```bash
APP_MESSAGE='Hello World' java -jar app.jar
```

```powershell
$env:APP_MESSAGE = 'Hello World'
java -jar .\app.jar
```

Keeping the entire `--app.message=Hello World` inside **one argument** prevents text from splitting into multiple parameters.

### 10.2. `&` in URLs

Example value to preserve:

```text
https://api.example.test/items?size=10&sort=desc
```

Bash:

```bash
APP_ENDPOINT='https://api.example.test/items?size=10&sort=desc' java -jar app.jar
```

PowerShell:

```powershell
$env:APP_ENDPOINT = 'https://api.example.test/items?size=10&sort=desc'
java -jar .\app.jar
```

Without quotes, the shell can interpret `&` as a command-control operator. When values contain `?`, `&`, `=`, or `#`, keep them intact in a quoted string.

### 10.3. `$` and backticks

If the value to preserve is:

```text
Price $100; literal $(calc)
```

Bash:

```bash
APP_MESSAGE='Price $100; literal $(calc)' java -jar app.jar
```

PowerShell:

```powershell
$env:APP_MESSAGE = 'Price $100; literal $(calc)'
```

Putting a string in double quotes when no interpolation is intended is a frequent source of confusion. Moreover, backticks perform command substitution in Bash when unprotected, while serving as the escape character in PowerShell. Single quotes protect these cases in both shells.

### 10.4. `#` and `;`

In both Bash and PowerShell, `#` can start a comment in appropriate syntactic positions. In Bash, `;` separates commands. In PowerShell, `;` also acts as a statement separator.

Example to pass:

```text
Release #2; mode=trial
```

Bash:

```bash
APP_MESSAGE='Release #2; mode=trial' java -jar app.jar
```

PowerShell:

```powershell
$env:APP_MESSAGE = 'Release #2; mode=trial'
```

Inside quoted strings, `#` and `;` remain literal text instead of acting as statement boundaries.

### 10.5. `*`, `?`, parentheses, and `|`

Bash can expand filename patterns containing `*` and `?` when unquoted; `|` can create a pipeline. PowerShell also treats certain characters as command syntax and has wildcard handling in cmdlets.

Illustrative value:

```text
pattern=(a|b)*?.txt
```

Pass it as:

```bash
APP_PATTERN='pattern=(a|b)*?.txt' java -jar app.jar
```

```powershell
$env:APP_PATTERN = 'pattern=(a|b)*?.txt'
```

What matters is ensuring **the string entering the Java process keeps its data meaning**; the application can decide whether it represents a regex, glob, or plain text based on business rules. The shell should not interpret it on the application's behalf.

### 10.6. Backslashes and Windows paths

In PowerShell, write:

```powershell
$env:APP_DIR = 'C:\Program Files\Demo App\data'
```

Inside PowerShell single quotes, `\` characters are preserved as-is.

In Bash running in a Unix environment, a path containing `\` that genuinely needs to stay literal text should also use single quotes:

```bash
APP_DIR='C:\Program Files\Demo App\data' java -jar app.jar
```

However, **valid string syntax does not mean a Windows path exists on Unix**. That is an independent filesystem concern. When running an application on Linux, normally use corresponding Linux paths.

### 10.7. `=` inside values

For an illustrative URL or token containing multiple `=` signs:

```text
a=b=c
```

Bash:

```bash
APP_MESSAGE='a=b=c' java -jar app.jar
```

PowerShell:

```powershell
$env:APP_MESSAGE = 'a=b=c'
```

The shell splits the assignment per its syntax; remaining `=` signs stay inside the value once you construct one string properly. Spring Boot does not treat every `=` inside an environment variable value as a new configuration pair.

## 11. Passing configuration via `--key=value`, `-Dkey=value`, and environment variables

There are three common channels:

| Delivery method | Example | Which process handles it |
| --- | --- | --- |
| Environment variable | `APP_MESSAGE='Hello'` / `$env:APP_MESSAGE = 'Hello'` | Shell assigns, Java inherits, Spring reads from environment |
| Spring Boot argument | `--app.message=Hello` | Shell constructs argument; Spring Boot reads at startup |
| JVM system property | `-Dapp.message=Hello` | Shell constructs argument; JVM handles system property |

### 11.1. Bash with Spring Boot arguments

```bash
java -jar app.jar '--app.message=A&B; literal $HOME'
```

The entire `--app.message=A&B; literal $HOME` is one argument; single quotes are stripped by Bash during command parsing.

### 11.2. PowerShell with Spring Boot arguments

```powershell
java -jar .\app.jar '--app.message=A&B; literal $HOME'
```

For this simple string, single quotes keep `$HOME` literal. If you need to keep double quotes **inside the argument**, keep PowerShell version differences in mind when forwarding arguments to native programs, or switch to environment variables to reduce multi-layer escaping.

### 11.3. JVM properties must sit in the right position

Bash:

```bash
java '-Dapp.message=Hello world' -jar app.jar
```

PowerShell:

```powershell
java '-Dapp.message=Hello world' -jar .\app.jar
```

`-Dapp.message=...` is a **JVM** option so it belongs **before** `-jar`. If placed after the JAR path, it is no longer the same way to set a JVM system property; everything after the JAR is passed as application arguments.

### 11.4. Quotes are not part of Spring syntax

Example:

```bash
java -jar app.jar '--app.message=Hello world'
```

In Bash, single quotes protect the argument during shell parsing. Spring Boot receives:

```text
--app.message=Hello world
```

Spring does not receive the two outer `'` characters. If the final value should contain `'`, write the quote **as data** using shell syntax, rather than expecting outer argument-wrapping quotes to be retained.

### 11.5. Do not confuse precedence order

In Spring Boot 3.3's typical precedence order, **application command-line arguments** can override **JVM system properties**, and JVM system properties can override **OS environment variables**; these sources generally outrank values in config data (`application.properties`/YAML). However, test-specific sources and additional mechanisms can alter the full picture.

If you set `APP_MESSAGE=A`, yet run with `--app.message=B`, the application usually receives `B`. Quoting of `A` or `B` is not the cause; **source precedence order** is what matters.

## 12. Runnable practice with Spring Boot 3.3

Create a Java 17, Spring Boot 3.3.x project with the `spring-boot-starter` dependency (which can be generated via Spring Initializr). The example uses `@ConfigurationProperties` to observe final values from environment variables.

### Step 1 — default configuration

Create `src/main/resources/application.properties`:

```properties
spring.application.name=shell-quoting-lab

app.message=Default hello
app.timeout=5s
app.feature-enabled=false
```

### Step 2 — create configuration object

`src/main/java/example/shellquoting/AppSettings.java`:

```java
package example.shellquoting;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppSettings(
        String message,
        Duration timeout,
        boolean featureEnabled
) {
}
```

Spring Boot binds `app.message`, `app.timeout`, and `app.feature-enabled` to the corresponding Java types. `Duration` makes it easy to inspect a duration like `2s` instead of parsing time strings manually in the application.

### Step 3 — read values in the application

`src/main/java/example/shellquoting/ShellQuotingApplication.java`:

```java
package example.shellquoting;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ShellQuotingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShellQuotingApplication.class, args);
    }

    @Bean
    ApplicationRunner showValues(AppSettings settings, Environment env) {
        return args -> {
            System.out.println("message=" + settings.message());
            System.out.println("timeout=" + settings.timeout());
            System.out.println("featureEnabled=" + settings.featureEnabled());
            System.out.println("rawProperty=" + env.getProperty("app.message"));
        };
    }
}
```

`@ConfigurationPropertiesScan` registers `AppSettings` and Spring injects that bean into `showValues(...)`. `app.message` does not need to be manually read from files in Java code.

If run without overriding sources, the lines printed by `ApplicationRunner` are expected to be:

```text
message=Default hello
timeout=PT5S
featureEnabled=false
rawProperty=Default hello
```

`PT5S` is the standard `Duration` string representation for 5 seconds.

### Step 4 — run from Bash

After packaging as a JAR, for example:

```bash
APP_MESSAGE='Unix literal: $HOME & "quoted" #1' \
APP_TIMEOUT='2s' \
APP_FEATUREENABLED='true' \
java -jar app.jar
```

Expected values in the application:

```text
message=Unix literal: $HOME & "quoted" #1
timeout=PT2S
featureEnabled=true
rawProperty=Unix literal: $HOME & "quoted" #1
```

Because everything after `=` is inside single quotes, `$HOME` is preserved verbatim. `&` and `#` do not split the command.

### Step 5 — run from PowerShell

In PowerShell:

```powershell
$env:APP_MESSAGE = 'PowerShell literal: $HOME & "quoted" #1'
$env:APP_TIMEOUT = '2s'
$env:APP_FEATUREENABLED = 'true'

java -jar .\app.jar
```

Expected output lines:

```text
message=PowerShell literal: $HOME & "quoted" #1
timeout=PT2S
featureEnabled=true
rawProperty=PowerShell literal: $HOME & "quoted" #1
```

PowerShell does not expand `$HOME` inside single quotes. `APP_FEATUREENABLED` illustrates the environment variable name corresponding to `app.feature-enabled`.

### Step 6 — intentionally replace single quotes with double quotes

Bash:

```bash
APP_MESSAGE="Unix user: $USER" java -jar app.jar
```

PowerShell:

```powershell
$env:APP_MESSAGE = "PowerShell home: $HOME"
java -jar .\app.jar
```

Observe the final value. You will see the part after `$USER` or `$HOME` substituted by the shell according to its environment before Java receives it.

### Step 7 — test argument overriding environment variable

In Bash:

```bash
APP_MESSAGE='From environment' \
java -jar app.jar '--app.message=From command line'
```

In PowerShell:

```powershell
$env:APP_MESSAGE = 'From environment'
java -jar .\app.jar '--app.message=From command line'
```

In normal setups, `app.message` will be `From command line`. This distinguishes a **shell quoting** bug from **Spring Boot selecting a higher-priority source**.

### Step 8 — clean up variables after practicing

Bash:

```bash
unset APP_MESSAGE APP_TIMEOUT APP_FEATUREENABLED
```

PowerShell:

```powershell
Remove-Item Env:APP_MESSAGE
Remove-Item Env:APP_TIMEOUT
Remove-Item Env:APP_FEATUREENABLED
```

These commands affect the current shell session; they do not automatically alter the environment of previously launched Java processes.

## 13. JSON in the `SPRING_APPLICATION_JSON` environment variable

Spring Boot supports `SPRING_APPLICATION_JSON` to supply multiple configuration keys from a single JSON string. This is error-prone because there are **two independent syntax rule sets**:

1. The shell handles quotes, `$`, backticks, and escapes when assigning the variable.
2. The **JSON** parser handles `"`, `\`, `\n`, and escape sequences once the string enters the Java process.

### 13.1. Bash: wrap JSON in single quotes

```bash
SPRING_APPLICATION_JSON='{"app":{"message":"Hello $USER & friends","timeout":"4s","feature-enabled":true}}' \
  java -jar app.jar
```

The JSON string passes through the shell verbatim, so `$USER` is not interpolated by Bash. Spring Boot then parses the JSON and supplies the corresponding properties.

If you want to interpolate shell values into JSON, do not concatenate strings casually, especially when values contain double quotes or backslashes. Use a proper JSON generator or the deployment platform's structured configuration mechanism.

### 13.2. PowerShell: single quotes keep JSON literal

```powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"message":"Hello $HOME & friends","timeout":"4s","feature-enabled":true}}'
java -jar .\app.jar
```

This is convenient because double quotes inside the JSON are JSON syntax, while outer single quotes are PowerShell syntax. The shell does not substitute `$HOME`.

### 13.3. Literal double quotes inside a JSON value

Suppose you want the value to be:

```text
He said "go"
```

Valid JSON must escape double quotes inside the value:

```json
{
  "app": {
    "message": "He said \"go\""
  }
}
```

Bash:

```bash
SPRING_APPLICATION_JSON='{"app":{"message":"He said \"go\""}}' java -jar app.jar
```

PowerShell:

```powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"message":"He said \"go\""}}'
java -jar .\app.jar
```

Here the `\` before the double quote is **JSON escaping**; because the JSON is wrapped in shell single quotes, `\` survives intact for the JSON parser to process.

### 13.4. Paths with backslashes in JSON

To represent a path in a JSON value:

```text
C:\Program Files\Demo App
```

JSON content must express `\` per JSON syntax, using `\\`:

```json
{"app":{"directory":"C:\\Program Files\\Demo App"}}
```

PowerShell:

```powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"directory":"C:\\Program Files\\Demo App"}}'
```

Bash:

```bash
SPRING_APPLICATION_JSON='{"app":{"directory":"C:\\Program Files\\Demo App"}}' java -jar app.jar
```

`\\` in JSON becomes `\` in the final value. Do not confuse **shell** escaping with **JSON** escaping.

### 13.5. Which layer reports an error for invalid JSON?

Example:

```json
{"app":{"message":"He said "go""}}
```

This string is invalid JSON syntax because the inner double quotes are unescaped. Even if you wrap the string properly in Bash or PowerShell single quotes, Spring Boot still cannot parse that JSON.

Separate the issues:

- If the shell reports a syntax error, the command may not have launched Java at all.
- If the Java process starts and Spring Boot reports a JSON parse error, inspect JSON syntax and inner escapes.
- If JSON is valid yet the final value is wrong, check key names, data types, and precedence order across configuration sources.

**Proper shell quoting alone is not enough to make JSON content valid.**

## 14. Spring placeholders are a separate processing layer

There is a subtle point when wanting to keep strings containing `${...}` syntax verbatim.

Bash example:

```bash
APP_MESSAGE='The text is ${HOME}' java -jar app.jar
```

Or PowerShell:

```powershell
$env:APP_MESSAGE = 'The text is ${HOME}'
```

Single quotes stop the shell from **interpolating** `${HOME}`. However, when the application reads the value through an API that performs **Spring placeholder resolution**, `${HOME}` can still be interpreted as a property reference at the **Spring** layer. Therefore, do not assume protecting characters from the shell protects them from every downstream string-processing layer.

Distinguish:

```text
$HOME       -> Bash/PowerShell variable interpolation syntax in appropriate contexts
${HOME}     -> can also be shell syntax; also resembles a Spring placeholder
$(command)  -> shell command/expression substitution syntax
```

If the application genuinely needs to store literal `${...}` as data, verify how the Spring configuration-reading API handles placeholders and use appropriate escaping or storage mechanisms. This is a **placeholder resolution** issue, distinct from choosing single or double quotes in the shell.

For ordinary messages, strings like `$HOME` without braces `{}` are more convenient for demonstrating literal `$` preservation without triggering Spring's `${...}` placeholder form.

## 15. Common errors and how to recognize them

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `Hello $USER` becomes `Hello alice` | Bash double quotes interpolated `$USER` | Use single quotes to keep `$USER` literal |
| Text after `&` treated as another command | URL/string not properly quoted | Wrap the whole value in appropriate quotes |
| Argument split into multiple words | Value with spaces not kept in one argument | Quote the whole `--key=value` |
| Bash reports error related to `!` | Interactive shell history expansion | Use single quotes for literal strings |
| PowerShell rejects `NAME=value command` | Copied Bash syntax into PowerShell | Use `$env:NAME = 'value'` then invoke program |
| PowerShell keeps `\` before `"` | Mistook backslash for PowerShell quote escape | Use outer single quotes or backtick inside double quotes |
| JSON with inner quotes fails | JSON syntax missing `\"` | Fix JSON first, then check shell quoting |
| `C:\...` path in JSON fails | JSON needs `\` escaped as `\\` | Use `C:\\...` at the JSON layer |
| App still has old value | Higher-priority source or old process not restarted | Check `Environment`, overriding sources, and restart |
| Variable present in shell, invisible to Java | Not exported in Bash or process runs elsewhere | Use `export`, inline prefix, or exact launch config |
| `APP_FEATURE_ENABLED` does not bind as expected | Env name violates relaxed binding for `-` keys | Use `APP_FEATUREENABLED` |
| Value has extra blank lines/weird characters | Literal newlines, CRLF, copy/paste, or wrong shell escape | Inspect input safely and check each layer |
| `-D` option has no effect | Placed after `-jar`, or shell split arguments | Move `-D...` before `-jar` |
| `${...}` still replaced despite single quotes | Spring or another tool resolved placeholders after shell | Check placeholder layer, not only shell syntax |

## 16. How to verify properly when configuration has special characters

When seeing an unexpected value, trace from outside to inside:

**Step 1 — identify the actual shell.** Are you using Bash, Zsh, PowerShell 5.1, PowerShell 7, or another shell? Bash examples do not automatically work on Zsh or PowerShell. This lesson covers Bash and PowerShell specifically.

**Step 2 — identify the configuration delivery channel.** Are you setting an environment variable, using `--app.key=value`, or `-Dapp.key=value`? Each requires proper syntax and placement.

**Step 3 — check the value after shell processing.** Do this only with non-sensitive test strings:

Bash:

```bash
export APP_MESSAGE='A&B; literal $HOME'
printf '%s\n' "$APP_MESSAGE"
```

PowerShell:

```powershell
$env:APP_MESSAGE = 'A&B; literal $HOME'
Write-Output $env:APP_MESSAGE
```

If the value is already wrong at this step, fix shell syntax first.

**Step 4 — confirm the Java process receives the right variable.** A shell might hold an unexported variable, the Java process might run from an IDE, service, Docker, or another terminal, and child process environments can differ from the observed shell session.

**Step 5 — check property names and precedence order.** For example, `APP_MESSAGE` corresponds to `app.message`; `--app.message=...` can override the environment variable. Do not confuse precedence issues with quoting issues.

**Step 6 — read the effective value in Spring.** In development, use `Environment#getProperty("app.message")` or a `@ConfigurationProperties` bean as illustrated. Only print sample values, never real secrets.

**Step 7 — if using JSON, verify both layers.** The shell must preserve the JSON string intact; the JSON string itself must be valid. Check `"` and `\` at the JSON layer.

**Step 8 — check whether a restart is needed.** Environment variables are passed when the Java process starts; changing variables in a terminal after the application is already running generally does not update existing beans automatically.

A simple Java check independent of Spring is inspecting the environment variable received by the JVM:

```java
String value = System.getenv("APP_MESSAGE");
System.out.println(value);
```

Use only with non-sensitive sample strings. If `System.getenv` is already wrong, the bug lies in passing the variable into the process. If `System.getenv` is right yet `Environment#getProperty("app.message")` differs, check name mapping, precedence order, and placeholder resolution.

## 17. Deployment environments, scripts, and important differences

### 17.1. Current terminal vs. already-running process

PowerShell example:

```powershell
$env:APP_MESSAGE = 'First'
java -jar .\app.jar
$env:APP_MESSAGE = 'Second'
```

Assigning `Second` does not alter a Java process launched earlier. A newly launched application run from PowerShell can inherit the new variable.

Bash behaves similarly: a child process receives a snapshot of the environment at launch time. If a program must update configuration while running, a dedicated refresh mechanism must be designed.

### 17.2. A `.env` file does not automatically equal Spring environment variables

Spring Boot does not by default treat any `.env` file in a project folder as an automatic configuration source like `application.properties`. Tools like Docker Compose, IDEs, or scripts can read `.env` and convert entries into environment variables, but that is **a separate tool step**.

Do not blindly run `source` on a `.env` file unless it is written in valid shell syntax and reviewed for trustworthiness. Docker Compose YAML files also have their own quoting and interpolation rules, distinct from interactive Bash/PowerShell.

### 17.3. Running from an IDE does not necessarily use the open terminal

If the application is launched using the IDE's Run button, the IDE can inject environment variables from its own run configuration. Variables you just exported in an external terminal might not exist in the IDE process's environment.

When investigating, identify the **actual launch mechanism**: terminal, script, Gradle/Maven, IDE, container, or OS service.

### 17.4. Windows PowerShell and `cmd.exe` differ

Examples in this lesson use PowerShell:

```powershell
$env:APP_MESSAGE = 'Hello'
```

In `cmd.exe`, environment variable assignment syntax differs. Therefore, not every "Windows" command is PowerShell. When project docs provide Windows commands, explicitly state which shell to use.

### 17.5. Variable names and Unicode characters

Environment variable names should generally use Latin letters, digits, and underscores, such as `APP_MESSAGE`. **Values** can contain Vietnamese and many Unicode characters. However, terminal display and character encoding can differ across operating systems, terminals, or script source files.

When Unicode text renders garbled, distinguish:

- Was the string corrupted before entering Java, or only when displayed?
- Which encoding are the script and terminal using?
- How is Java writing text to the console?

Not every Unicode display issue stems from choosing single versus double quotes incorrectly.

## 18. Self-check exercises

### Exercise 1 — predict Bash interpolation

Suppose `USER=an`:

```bash
APP_MESSAGE='Hello $USER' java -jar app.jar
APP_MESSAGE="Hello $USER" java -jar app.jar
```

What will `app.message` be in both runs?

**Answer:** the first run is `Hello $USER`; the second run is `Hello an`, assuming `USER` equals `an`.

### Exercise 2 — protecting a URL

URL:

```text
https://shop.example.test/search?term=a+b&sort=price
```

Write one Bash command and one PowerShell snippet to pass the URL via `APP_ENDPOINT`, keeping `?`, `&`, and `=` intact.

**Bash answer:**

```bash
APP_ENDPOINT='https://shop.example.test/search?term=a+b&sort=price' java -jar app.jar
```

**PowerShell answer:**

```powershell
$env:APP_ENDPOINT = 'https://shop.example.test/search?term=a+b&sort=price'
java -jar .\app.jar
```

### Exercise 3 — `$`, double quotes, and exclamation mark

Suppose the application must receive exactly:

```text
Cost $20! He said "yes".
```

**Bash answer:**

```bash
APP_MESSAGE='Cost $20! He said "yes".' java -jar app.jar
```

**PowerShell answer:**

```powershell
$env:APP_MESSAGE = 'Cost $20! He said "yes".'
```

Outer single quotes are shell syntax; inner double quotes are content.

### Exercise 4 — single quotes inside the value

Suppose the application must receive:

```text
It's John's app
```

**Bash answer:**

```bash
APP_MESSAGE='It'\''s John'\''s app' java -jar app.jar
```

**PowerShell answer:**

```powershell
$env:APP_MESSAGE = 'It''s John''s app'
```

### Exercise 5 — multi-layer JSON

Suppose `SPRING_APPLICATION_JSON` must set `app.message` to exactly `He said "go"`.

**Bash answer:**

```bash
SPRING_APPLICATION_JSON='{"app":{"message":"He said \"go\""}}' java -jar app.jar
```

**PowerShell answer:**

```powershell
$env:SPRING_APPLICATION_JSON = '{"app":{"message":"He said \"go\""}}'
java -jar .\app.jar
```

`\"` belongs to the JSON layer; single quotes belong to the shell layer.

### Exercise 6 — variable name via relaxed binding

Configuration key:

```properties
app.client.connect-timeout=5s
```

What is the appropriate environment variable name according to the rule for `@ConfigurationProperties`?

**Answer:** `APP_CLIENT_CONNECTTIMEOUT`. Replace dots with `_`, remove `-`, and uppercase.

### Exercise 7 — distinguishing quoting from precedence

```bash
APP_MESSAGE='Environment Value' java -jar app.jar '--app.message=CLI Value'
```

Which value might the application receive? Why?

**Answer:** `CLI Value` according to Spring Boot's typical precedence order. Single quotes on the environment variable were already valid; the higher-priority command-line argument supplies the final value.

### Exercise 8 — distinguishing shell and Spring placeholders

```bash
APP_MESSAGE='${HOME}' java -jar app.jar
```

Can you conclude every Java/Spring API will receive the exact characters `${HOME}`?

**Answer:** No. Single quotes protect `${HOME}` from Bash interpolation, yet Spring APIs capable of placeholder resolution may process this expression afterward. Clarify which API and processing layer are involved.

## 19. Practical principles for Spring Boot projects

Several conventions reduce bugs when moving commands between Unix and Windows:

1. **Use single quotes for literal values** when interpolation is unnecessary: in both Bash and PowerShell, this is usually the most predictable choice.
2. **Use double quotes intentionally** when you actually want `$VARIABLE` or shell expressions substituted.
3. **Label the shell at the top of examples**: `bash`, `powershell`; never create a single snippet mixing two different variable assignment syntaxes.
4. **In PowerShell, use `$env:NAME = 'value'`** to set variables for child processes. In Bash, use `export` or inline assignments before the command.
5. **Quote the entire `--key=value` argument** if the value has spaces or shell control characters.
6. **If using JSON, validate JSON syntax separately**, especially `\"` and `\\`.
7. **Name environment variables following Spring Boot rules**, especially for hyphenated properties.
8. **Inspect values inside the actual running Java process**, not just variables in another terminal.
9. **Restrict printing configuration in examples** to non-sensitive values.
10. **Never put real passwords or tokens directly on the command line or in logs**; valid quoting syntax does not equal secret protection. In real deployments, use infrastructure-appropriate secret management.

If a value contains many quote types, nested JSON, newlines, and escape sequences, placing it in a configuration file or structured configuration source is generally more maintainable than a long terminal command.

## 20. Core takeaways

```text
Layer 1 — Bash / PowerShell:
  Single quotes -> usually preserve literal text
  Double quotes -> can interpolate variables / expressions
  Environment assignment syntax differs between the two shells

Layer 2 — Java process:
  Receives environment, argv, and -D after shell parsing

Layer 3 — Spring Boot:
  Maps variable names -> selects prioritized source -> binds into beans
  May also resolve placeholders or parse JSON
```

When configuring Spring Boot 3.3 with environment variables, always answer in order: **Which shell is running? What is the real value after shell parsing? Did Java receive the right variable? Which source did Spring Boot ultimately pick?** Separating into these three layers reveals the root cause of nearly all quoting and special-character issues.

## References

- Spring Boot 3.3 Reference — Externalized Configuration, Property Source Order, and Binding From Environment Variables: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- GNU Bash Reference Manual — Quoting, Single Quotes, Double Quotes, and Shell Expansions: https://www.gnu.org/software/bash/manual/bash.html
- GNU Bash Reference Manual — History Interaction: https://www.gnu.org/software/bash/manual/html_node/History-Interaction.html
- Microsoft Learn — PowerShell about_Quoting_Rules: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules
- Microsoft Learn — PowerShell about_Parsing: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing
