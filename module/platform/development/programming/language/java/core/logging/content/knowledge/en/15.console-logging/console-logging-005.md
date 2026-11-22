# Terminal Colors in Java Console Logging

**Terminal colors** are a way to highlight information when a program writes logs to the console: for example, displaying the `ERROR` level in red, `WARN` in yellow, and `INFO` in green or gray. Most terminals accomplish this using **ANSI escape sequences**, which are control bytes inserted into the output string. Terminals that understand those bytes change the text color or style; systems that do not understand them may display garbled characters such as `^[ [31m` or store the raw control bytes in a file.

Color is strictly a **presentation layer**. An `ERROR` event does not become more severe because it is red, and an `INFO` event does not lose its meaning when colors are disabled. In real-world logging, deciding **which events to record** belongs to the logger/level/filter; **where to write them** belongs to the console handler/appender; and **how to display colors** typically belongs to the formatter/layout/encoder.

Goals of this lesson: understand ANSI SGR, choose meaningful colors, distinguish a TTY from a file/CI environment, and enable/disable colors properly in Java 17 as well as in **Logback**, **Log4j 2**, and **java.util.logging (JUL)** configurations. The examples clearly explain when colors are actual bytes in stdout and when they are merely how the terminal renders them.

## 1. How Do Terminal Colors Work?

An ANSI-capable terminal can receive the following sequence:

```text
ESC [ 31 m   ERROR   ESC [ 0 m
```

Here, `ESC` is the control character U+001B (hex `1B`, decimal `27`), `[` begins a *Control Sequence Introducer*, and `31m` is the command to set the foreground text color to red. `0m` is the **reset** command to return to the default display attributes. On a supported screen, the user sees the word `ERROR` in red; in the byte stream, the ESC characters and SGR parameters are still present.

In Java, you can create a red prefix with:

```java
String red = "\u001B[31m";
String reset = "\u001B[0m";
System.out.println(red + "ERROR" + reset + " | event=job.failed");
```

This is an **illustrative snippet inside a method**, not a standalone Java class. Color only appears if the terminal receiving stdout supports ANSI; if output is redirected to a file, the file may contain the ESC bytes. The complete program in Section 6 includes a mechanism to toggle color on or off to avoid this.

**ANSI SGR** (*Select Graphic Rendition*) is a group of commands that change display attributes such as foreground, background, bold, underline, and reset. The part after `[` consists of numeric codes, usually separated by `;` and ending with `m`. Not every terminal renders the exact same shade; users can change themes, palettes, contrast, and brightness.

### Basic SGR Codes

| Code | Common Meaning | Java String Representation |
| --- | --- | --- |
| `0` | Reset SGR attributes. | `"\u001B[0m"` |
| `1` | Bold or increased intensity depending on the terminal. | `"\u001B[1m"` |
| `2` | Dim/faint when supported by the terminal. | `"\u001B[2m"` |
| `4` | Underline. | `"\u001B[4m"` |
| `30`–`37` | Standard foreground colors: black, red, green, yellow, blue, magenta, cyan, white. | `"\u001B[31m"` is red |
| `90`–`97` | Bright foreground colors when supported. | `"\u001B[91m"` is bright red |
| `40`–`47` | Standard background colors. | `"\u001B[43m"` is yellow background |
| `39` | Restore the terminal's default foreground color. | `"\u001B[39m"` |
| `49` | Restore the terminal's default background color. | `"\u001B[49m"` |

For example, green text is `ESC[32m`, yellow is `ESC[33m`, and red is `ESC[31m`. In common usage, the closing sequence is `ESC[0m`; you should reset immediately after **the exact segment you want to color** so that the rest of the console output does not remain colored.

### 256-Color and True Color

Some modern terminals also support:

- **256-color:** `ESC[38;5;196m` selects a foreground color from the 256-color palette; `ESC[48;5;N m` is the conceptual pattern for background color (remove the space before `m` and replace `N` with a value from 0–255).
- **RGB/true color:** `ESC[38;2;255;80;80m` sets an RGB (255,80,80) foreground if the terminal supports it.
- **Combined:** `ESC[1;31m` typically means bold + red.

Numeric codes do not guarantee exact visual appearance: a terminal may not support 256-color/true color, may remap the palette, or may use a dark/light theme. The standard color table is a sensible starting point for logging; never rely on exact RGB codes to convey severity.

## 2. Which Information in Logs Should Be Colored?

Coloring an entire log line by level can be glaring and hard to read when messages are long. A convention that is usually easier to follow is to **color only the level label** or a few stable fields:

```text
INFO  | event=service.ready
WARN  | event=cache.fallback outcome=recovered
ERROR | event=job.failed outcome=failed
```

In this plain-text block, colors are not encoded; when a real terminal supports ANSI, each level can carry its own color. A suggested mapping when **designing your own**:

| Level | Reference Color | Purpose |
| --- | --- | --- |
| `TRACE` / `DEBUG` | Gray or soft cyan | Diagnostic information that does not need to stand out excessively. |
| `INFO` | Default color or green | Normal progress worth following. |
| `WARN` / `WARNING` | Yellow | Unusual situation, possibly recovered. |
| `ERROR` / `SEVERE` | Red | Actual failure requiring investigation. |
| `FATAL` when the API/backend has this level | Dark red or bold | Critical severity according to the backend's convention. |

**There is no mandatory standard saying "INFO must be green, WARN must be yellow"** across all frameworks. For instance, `%highlight` in Logback and Log4j 2 have **different default palettes**; use your backend's own color configuration or customize it explicitly if your organization needs consistency.

### Never Use Color as the Only Signal

Users may use monochrome terminals, high-contrast modes, or accessibility tools; some people have difficulty distinguishing red and green. Therefore, always keep the **level text**, **event name**, **outcome**, and **errorCode**. Color only helps the eye scan faster:

```text
ERROR | event=payment.failed paymentId=pay-42 errorCode=UPSTREAM_TIMEOUT
```

This line must still be understandable when copied to Slack, CI logs, centralized logging systems, or printed in black and white. Avoid blinking text or foreground/background combinations that hurt readability.

## 3. TTY, Console, Pipe, File, and CI Are Different Environments

When running directly in an interactive terminal, colors can be helpful. However, stdout can also be:

- Redirected with `> application.log` or `2> error.log`.
- Piped through `grep`, `awk`, `tee`, `less`, or a parser program.
- Collected by Docker/Kubernetes or an agent reading stdout/stderr.
- Recorded into CI/CD job logs with varying levels of color support.
- Displayed in an IDE Output window, where ANSI support depends on version and configuration.

If a program always outputs color bytes, files or pipelines may receive extra `0x1B` and `[31m` sequences; a parser looking for the level at the start of a line may fail to recognize `ERROR`, and exact-match expressions may fail. With structured JSON logs, control codes are unnecessary and can break downstream consumer expectations.

**Recommended rule for operational applications:** enable color only when the destination is a capable terminal and the user has not requested disabling it; when outputting to files, CI, or collectors, default to **plain text** or **structured logging** without color. This rule should be enforced via application/backend configuration, not just left to the author's personal preference.

### Checking for a Terminal in Java

`System.console() != null` is a **heuristic** indicating that the JVM has an interactive console. If stdout is redirected or run through an IDE, this value may be `null`. However, it is **not a complete test for ANSI support**: some capable terminals still return `null` under launchers/IDEs, while some consoles are present yet cannot handle all color codes.

The `TERM` environment variable may contain `dumb`, suggesting an environment without standard terminal capabilities. `COLORTERM` and similar variables are merely **hints**, not a 100% guarantee for a JVM. On Windows, behavior also depends on Windows Terminal, PowerShell, Console Host, and Virtual Terminal Processing mode; do not treat every `cmd.exe` window as identical.

**Conclusion:** use `auto` mode as a sensible default while allowing users to explicitly set `always` or `never`.

## 4. The NO_COLOR Convention and Explicit Color Control

`NO_COLOR` is a community convention for CLI tools: when this environment variable **exists and is non-empty**, a program that outputs color by default should **not add color**. For example:

```bash
NO_COLOR=1 java TerminalColorDemo --color=auto
```

The command above uses Bash-style shell syntax; on Windows PowerShell you can use:

```powershell
$env:NO_COLOR = "1"
java TerminalColorDemo --color=auto
```

Note: this is a **voluntary convention**, not an automatically enabled JVM feature. If your code or logging framework does not read `NO_COLOR`, setting this variable **will not make colors disappear on its own**. You must support it in your code or corresponding runtime configuration.

A well-designed interface offers three modes:

| Mode | When to Use | Meaning |
| --- | --- | --- |
| `auto` | Default for CLI | Colorize only if the interactive environment is capable and no color-disable request is present. |
| `always` | Explicitly requested by the user | Emit ANSI even if stdout is piped; useful when downstream genuinely understands ANSI. |
| `never` | Files, CI, collectors, machine-readable output | Always output plain text, avoiding ANSI control codes. |

When a user **explicitly** requests `--color=always`, that mode may take precedence over `NO_COLOR` according to the application's own policy. Document the policy clearly. Never force color when the terminal does not support it just because `TERM` contains `xterm`.

Convention reference: [NO_COLOR – disabling ANSI color output by default](https://no-color.org/).

## 5. ANSI Codes Are Not Ordinary Display Characters

In Java:

```java
String label = "\u001B[31mERROR\u001B[0m";
```

`label.length()` is **greater** than the length of the word `ERROR`, because the string includes the control codes. The terminal does not treat those bytes as normal-width characters, so aligning columns using `String.length()` can become misaligned if calculated improperly before or after inserting colors.

For example:

```text
Rendered message:
ERROR | event=job.failed

Byte inspection representation (ESC and LF notation):
ESC[31mERRORESC[0m | event=job.failedLF
```

The two representations are not identical at the byte level. When column alignment is needed, format **the visible text first**, then wrap the already-padded label with color codes. With complex Unicode, display width is also affected by combining characters, CJK, and emoji; `String.length()` is not a general-purpose terminal column-width function.

### Never Forget to Reset

If you forget `ESC[0m`, subsequent printed characters may continue to carry the previous color or style. If an exception is thrown while applying color, make sure to reset in the exit/cleanup path. With standard `System.out.println(...)`, building a complete string of prefix + content + reset reduces the risk of "color bleeding" onto the next line.

Using `ESC[0m` does not solve every log injection risk: user data itself can contain ESC codes that control the terminal. Sanitize untrusted data before printing to the console; do not allow arbitrary input containing control sequences into an administrative terminal unnecessarily.

## 6. Complete Java 17 Example: --color=auto/always/never

The program below is a **console presentation demonstration**, not a complete logging framework. It uses plain JDK 17 with no dependencies. The `INFO`, `WARN`, and `ERROR` labels are colored when color is enabled; the entire message remains intact so it is searchable when color is disabled.

Save as **`TerminalColorDemo.java`**:

```java
public final class TerminalColorDemo {
    private static final String ESC = "\u001B[";
    private static final String RESET = ESC + "0m";

    private static boolean autoColor() {
        String noColor = System.getenv("NO_COLOR");
        String term = System.getenv("TERM");

        boolean noColorRequested =
                noColor != null && !noColor.isEmpty();

        return System.console() != null
                && !noColorRequested
                && !"dumb".equalsIgnoreCase(term);
    }

    private static boolean shouldColor(String mode) {
        return switch (mode) {
            case "--color=always" -> true;
            case "--color=never" -> false;
            case "--color=auto" -> autoColor();
            default -> throw new IllegalArgumentException(
                    "Expected --color=auto, --color=always or --color=never"
            );
        };
    }

    private static void printEvent(
            String level, String eventName, boolean color) {
        String code = switch (level) {
            case "INFO" -> "32";
            case "WARN" -> "33";
            case "ERROR" -> "31";
            default -> "0";
        };

        String label = color
                ? ESC + code + "m" + level + RESET
                : level;

        System.out.println(label + " | event=" + eventName);
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            throw new IllegalArgumentException(
                    "Provide at most one --color option"
            );
        }

        String mode = args.length == 0 ? "--color=auto" : args[0];
        boolean color = shouldColor(mode);

        printEvent("INFO", "service.ready", color);
        printEvent("WARN", "cache.fallback", color);
        printEvent("ERROR", "job.failed", color);
    }
}
```

Compile and run with **JDK 17 or later**:

```bash
javac TerminalColorDemo.java
java TerminalColorDemo --color=never
```

**Exact standard output** of the `--color=never` command:

```text
INFO | event=service.ready
WARN | event=cache.fallback
ERROR | event=job.failed
```

None of the lines contain ANSI codes, so they can be compared as plain text and redirected to a file. Try color mode (in a supported terminal):

```bash
java TerminalColorDemo --color=always
```

**Visual result:** the INFO label is green, WARN is yellow, ERROR is red; the ` | event=...` content remains in the default color. The byte stream contains the ANSI sequences:

```text
ESC[32mINFOESC[0m | event=service.ready
ESC[33mWARNESC[0m | event=cache.fallback
ESC[31mERRORESC[0m | event=job.failed
```

**Note:** the three lines above use the text `ESC` to **represent** the control character, not literal stdout; actual stdout contains byte `0x1B` before `[`. Colors will not necessarily display properly in a tool that does not support ANSI. With `--color=auto` and no interactive terminal output, the example automatically switches to no color.

### Why Is This Code Worth Noting?

1. `ESC` uses Java's `\u001B[` escape; each level label has its own SGR, with reset `0m` placed right after the label.
2. The `switch` expression is valid Java 17 syntax; no libraries outside the JDK are needed.
3. `autoColor()` checks `System.console()`, `NO_COLOR`, and `TERM=dumb`. This is a **limited heuristic**, not a comprehensive detection of all terminal capabilities.
4. `--color=always` is an explicit request that can emit ANSI codes even when piped to a file; `--color=never` is always plain text.
5. The level values in the demo are for presentation only and **do not replace actual level classification, filters, loggers, or appenders**.
6. Events use fixed text so `--color=never` output does not depend on timestamps, working directory, or thread scheduling.

### Testing Redirection

To ensure a file intended for a collector contains no ANSI:

```bash
java TerminalColorDemo --color=never > application.log
```

The contents of `application.log` are the three plain-text lines shown in the standard output above. If changed to `--color=always`, ANSI bytes will be written to the file even if they may not be visible in a text editor. When exact verification is needed, use a hex viewer such as `od`/`xxd` on POSIX systems or an appropriate hex viewer; do not guess based on how an editor renders colors.

**Portability:** modern Windows terminals can support ANSI, though Virtual Terminal Processing enablement depends on the host; legacy terminals or certain applications/IDEs do not support it. There is no reason to force ANSI output in all circumstances.

## 7. Logback: Using PatternLayout to Color Levels

In the **SLF4J + Logback Classic** ecosystem, colors are commonly configured via conversion words in **PatternLayout**, passed into the `PatternLayoutEncoder` of a `ConsoleAppender`. Logback documentation supports `%highlight(...)` and color conversion words such as `%red(...)`, `%cyan(...)`, and `%yellow(...)`.

Example **`src/main/resources/logback.xml`** file in an application using Logback as its backend:

```xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %highlight(%-5level) %cyan(%logger{36}) - %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

In this configuration:

- `%d{HH:mm:ss.SSS}` prints the time; it only includes local time, so it is insufficient as an absolute timestamp for distributed systems without a timezone.
- `%highlight(%-5level)` colors the **level label**, left-aligned with a minimum width of five characters.
- `%cyan(%logger{36})` colors the logger name cyan and abbreviates it when needed.
- `%msg%n` prints the message and a newline.
- The `CONSOLE` appender writes to `System.out`; this only takes effect when Logback is the active backend and the configuration is loaded.

**Logback's default colors differ from the Java example in Section 6.** In the `%highlight` converter, Logback uses its own color scheme: ERROR is typically bold red, WARN is red, INFO is blue, and other levels use the default color. Do not assume INFO is always green or WARN is always yellow as in the suggested table.

If the application runs in CI, redirects to a file, or feeds a log collector that does not understand ANSI, use a **colorless configuration** for that environment, such as:

```xml
<pattern>%d{HH:mm:ss.SSS} %-5level %logger{36} - %msg%n</pattern>
```

This is a **single replacement configuration line**, not a complete file. Never force a file appender to receive color sequences just because a pattern was copied from the console.

### Windows and Jansi

Logback documentation describes the `<withJansi>true</withJansi>` option for the console to support translating/stripping escape sequences in certain environments, with a compatible Jansi dependency. **Do not add `withJansi` out of habit**: requirements, versions, and support levels vary across Logback, Jansi, JDK, and Windows terminal versions. On many modern terminals, ANSI is already supported directly. If you use Jansi, verify dependencies/runtime and actual output, especially when redirecting.

Documentation: [Logback Manual – Layouts, Coloring](https://logback.qos.ch/manual/layouts.html).

## 8. Log4j 2: Using %highlight{...} and ANSI Options

In **Log4j 2 Core**, `PatternLayout` supports the conversion words `%highlight{pattern}` and `%style{pattern}{style}`, using curly-brace syntax that **differs** from Logback's `%highlight(...)`.

Example **`src/main/resources/log4j2.xml`** file in an application running Log4j2 Core:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="CONSOLE" target="SYSTEM_OUT">
            <PatternLayout
                pattern="%d{HH:mm:ss.SSS} %highlight{%-5level} %logger - %msg%n"
                noConsoleNoAnsi="true"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="INFO">
            <AppenderRef ref="CONSOLE"/>
        </Root>
    </Loggers>
</Configuration>
```

For Log4j 2 versions that support these attributes:

- `%highlight{%-5level}` prints the level with a color depending on the level.
- `noConsoleNoAnsi="true"` disables ANSI codes if `System.console()` is `null`, which is useful when output is piped or run non-interactively. This is still a heuristic; IDE terminals may be an exception.
- `disableAnsi="true"` on `PatternLayout` is an option to **unconditionally disable ANSI** when colorless output is required, such as for collectors or files.
- `%style{%logger}{cyan}` is an example of coloring a segment with a specific color.
- Log4j2's default palette typically uses green for INFO, yellow for WARN, bright/bold red for ERROR, and cyan for DEBUG; the actual mapping can be customized via `%highlight` options.

The XML above illustrates Log4j2; **do not use it verbatim for Logback**. Likewise, do not mix Logback's `%highlight(%-5level)` into Log4j2 because the syntax is different.

Example configuration that **only disables color** in Log4j2 when exporting logs to another system:

```xml
<PatternLayout pattern="%d{ISO8601} %-5level %logger - %msg%n"
               disableAnsi="true"/>
```

This is a **configuration snippet** that must be placed inside a valid appender. Official documentation: [Log4j 2 – Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html).

## 9. JUL: No Built-in %highlight Conversion Word

`java.util.logging` (**JUL**) in the JDK uses the **Logger → Handler → Formatter** model. `ConsoleHandler` and `SimpleFormatter` do not provide a `%highlight` conversion word like Logback or Log4j2. If you want ANSI colors by level, you can write a custom `Formatter`, but you must handle:

- `LogRecord.getLevel()` to get the record's level, such as `SEVERE`, `WARNING`, `INFO`, or `FINE`.
- `Formatter.formatMessage(record)` to format JUL's `{0}` placeholders before coloring.
- `LogRecord.getThrown()` to decide how to print the stack trace/cause; never drop exceptions from important logs.
- An option to enable colors based on the environment, rather than always inserting ANSI.
- A `Handler` may write to stderr, stdout, or a file depending on its type; do not assume `ConsoleHandler` writes to stdout by default.
- `setUseParentHandlers(false)` when needed to prevent records from reaching parent handlers and causing unwanted duplicate output.

The simple `Formatter` snippet below colors only the **level** and **does not print stack traces**; therefore, it is **not sufficient for production if `Throwable` logging is needed**:

```java
// Illustrative snippet within code that already has the required class/variables.
java.util.logging.Formatter colored = new java.util.logging.Formatter() {
    @Override
    public String format(java.util.logging.LogRecord r) {
        String label = r.getLevel().getName();
        String sgr = r.getLevel().intValue() >=
                java.util.logging.Level.SEVERE.intValue()
                ? "\u001B[31m"
                : "\u001B[0m";
        return sgr + label + "\u001B[0m"
                + " | " + formatMessage(r) + "\n";
    }
};
```

In applications with standardization requirements, use an appropriate formatter/encoder for your actual logging backend instead of duplicating color logic across multiple places. Include a colorless mode, escape data, and test redirection behavior.

## 10. Colors When Writing Files, Structured JSON, and Centralized Logging Systems

In production, the critical value of logs lies in **timestamp**, **level**, **logger/service**, **event**, **requestId/traceId**, **outcome**, and **exception**, rather than color. Log collectors need consistent data to parse and search; ANSI codes can break those assumptions.

A common policy:

| Destination | ANSI Color | Data to Preserve |
| --- | --- | --- |
| Interactive developer terminal | May enable `auto` | Level, component, message, correlation ID. |
| Console collected by CI | Disabled by default, unless CI supports it and the user explicitly wants it | Clear plain text; do not depend on color. |
| Log file for grep/parsing | Disabled | Stable text with timestamp and event ID. |
| JSON/NDJSON for log collector | Disabled | Structured fields, timestamp with timezone, requestId/traceId. |
| Observability dashboard | Color decided by the **UI** | Severity as a field, not escape codes from the application. |

Once logs are structured, the dashboard can easily color WARN/ERROR in the UI **based on the level field**, without the application embedding color codes into stored data.

### Removing Escape Sequences from Existing Logs

For legacy log data containing ANSI codes, you may need to filter them when viewing or migrating data. However, hand-written regexes to strip all escape sequences can miss other types of control sequences and accidentally corrupt data, so **prefer fixing it at the source**: disable colors in the encoder/appender before sending logs to the collector. If historical data must be cleaned, use a parser/utility verified against representative data and keep the original copy for reference.

### Storing Exceptions

Stack traces can span multiple lines; a logger/collector should preserve `Throwable` and its cause through the proper API. When coloring ERROR, color only the label or necessary segment—do not insert ANSI into every stack frame unnecessarily. Color does not replace multiline handling or structured exception fields.

## 11. Common Pitfalls

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Displays `^[ [31m` or garbled characters | Console does not understand ANSI or logs are redirected. | Disable color using `never` mode or plain config; check terminal support. |
| File `application.log` contains bytes `1B 5B` | Appender/formatter embedded ANSI. | Use a colorless layout for files; verify with a hex viewer. |
| Entire remaining terminal turns red | Forgot to reset `ESC[0m` or error while building string. | Reset right after the colored segment; ensure reset on exception paths. |
| `--color=auto` does not enable color in IDE | `System.console()` is `null` even though the output window supports ANSI. | Allow an explicit `always` option for verified environments. |
| `NO_COLOR=1` does not change Logback colors | Framework/layout does not support this convention automatically. | Choose a plain config, check adapters, or add logic to read the env var. |
| Color appears on stdout but not in file | The two appenders have separate patterns/encoders. | This may be the intended design; compare destination configs. |
| INFO/WARN colors differ between backends | Logback and Log4j2 have different default palettes. | Use explicit color configuration or rely on level labels for consistency. |
| `%highlight` prints literally | Wrong syntax/backend used or converter not loaded. | Check `%highlight(...)` vs `%highlight{...}` syntax and version. |
| Column alignment is off | ANSI string is longer than visible column count. | Pad the visible text first, then wrap with color codes. |
| CI parser fails to recognize level | Line starts with an escape code instead of `ERROR`. | Disable color at the source when outputting for machine consumption. |
| JSON logs fail to parse | ANSI inserted into JSON/plain text or manual JSON concatenation failed. | Use a standard structured encoder without ANSI. |
| User logs contain control codes | Unsanitized input can trigger unintended terminal effects. | Escape/strip dangerous control characters before logging. |
| Relying solely on color to judge errors | Terminal themes and color vision vary. | Keep level, eventName, outcome, and errorCode as clear text. |

## 12. Terminal Color Implementation Checklist

1. **Log source:** is the application using JUL, Logback, Log4j2, or another library? Choose the right configuration method for the actual backend.
2. **Output destination:** is it an interactive terminal, CI, file, container stdout, or JSON collector? Do not treat them all the same.
3. **Defaults:** does it default to no-color when redirected/piped? Is there `auto/always/never` or an equivalent config?
4. **User preferences:** are `NO_COLOR` (when non-empty) and environment configurations respected according to a documented policy?
5. **ANSI syntax:** does it use valid `ESC[...m` and reset `ESC[0m`? Does color leak into subsequent messages/lines?
6. **Readability:** is it readable without color, on different background colors, for users with color vision deficiency, or when copied to other systems?
7. **Formatter/layout:** does it preserve logger name, timestamp, message, correlation ID, and required exceptions?
8. **Data safety:** are user inputs, stack traces, secrets, and control characters sanitized before output?
9. **Performance:** does it build expensive colored/formatted strings when the level is disabled or under high load? Have you evaluated console I/O?
10. **QA:** have you tested directly in a terminal, with `> file` redirection, pipes, CI, IDEs, Windows/Linux, and `NO_COLOR`?
11. **Collector:** have you verified that machine-readable logs contain no ANSI and do not break JSON/multiline parsing?
12. **Operability:** do dashboards and alerts still evaluate severity using fields rather than depending on color?

## 13. Self-Check Questions

**Question 1.** An `ERROR` event is written to a file, and `[31m` appears in the file. Should you change the level from ERROR to WARN?

**Answer:** No. The issue is with the formatter/layout adding ANSI, not the severity. Use a colorless layout for files and keep the correct business level.

**Question 2.** Does `System.console() == null` prove the terminal does not support ANSI?

**Answer:** No. It is only a heuristic; IDEs or pipelines may handle display differently. Allow users to select a color mode explicitly.

**Question 3.** When does `NO_COLOR=1` take effect?

**Answer:** When the program/framework **supports checking** that variable or is configured with equivalent semantics. The JVM does not automatically disable ANSI codes across all libraries.

**Question 4.** What is the difference between `%highlight(%-5level)` and `%highlight{%-5level}`?

**Answer:** The parenthesis form is the conversion word commonly used in **Logback**; the curly-brace form is used in **Log4j 2 PatternLayout**. Using the wrong one for your backend may prevent it from being parsed as intended.

**Question 5.** Should ANSI codes be used to trigger alerts in a centralized logging system?

**Answer:** No. Systems should rely on the level and fields/events; the dashboard UI decides display colors, while stored records keep a stable format.

## 14. References

- [Logback Manual – Layouts: Coloring](https://logback.qos.ch/manual/layouts.html): `%highlight(...)` and color conversion words.
- [Apache Log4j 2 – Pattern Layout](https://logging.apache.org/log4j/2.x/manual/pattern-layout.html): `%highlight{...}`, `%style{...}`, `disableAnsi`, `noConsoleNoAnsi`.
- [NO_COLOR – convention for disabling ANSI color](https://no-color.org/): non-empty `NO_COLOR` environment variable and explicit override precedence.

**Conclusion:** Terminal color is a **presentation** feature of console logging. It makes INFO/WARN/ERROR labels easier to spot when reading directly, but it does not replace levels, messages, trace IDs, or safe log design. Only enable ANSI when the destination is genuinely appropriate, always provide a colorless mode, reset properly after the colored segment, and test output across terminals, files, pipes, CI, and collectors.