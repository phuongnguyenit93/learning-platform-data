# Cross-Platform Argument Quoting: Bash, PowerShell, cmd.exe, and Java

**Argument quoting** is the practice of ensuring a value is passed to a program as intended, even when the value contains spaces, quotes, backslashes, Unicode characters, or shell special characters. This topic is critical when writing build scripts, invoking Java CLIs, running Maven/Gradle in CI, or spawning child processes from Java.

A command string often passes through multiple parsing layers. A shell may expand variables, split words, or process pipes and wildcards before the program is launched. On Windows, `CreateProcess` receives a command-line string, and the target program parses that string into arguments itself. The Java launcher, `cmd.exe`, PowerShell, and Bash each have different rules.

The reliable approach is to understand which layer is parsing the command, keep each argument as a separate value for as long as possible, and test round-trips by observing the exact `args[]` received by the target program.

## 1. Why Is Argument Quoting Error-Prone?

Suppose a program needs to receive exactly three arguments:

~~~text
--file
C:\Build Output\release candidate.jar
--label
nightly build
~~~

If the shell splits the string on spaces, a path may be broken into multiple arguments. If the shell expands `$HOME`, `*`, or `%TEMP%`, the program receives a modified value. If quotes are stripped by the shell at the wrong layer, the program no longer receives the literal quotes required by the data.

Common failures:

- Paths with spaces are split into multiple arguments.
- `&`, `|`, `;`, `(`, or `)` are interpreted by the shell as operators.
- `$name`, `%NAME%`, or `!NAME!` are unexpectedly replaced with environment variables.
- The `*` wildcard is expanded by the shell into a list of files.
- Double quotes inside a value close the string prematurely.
- Trailing backslashes in a path interact with the closing quote on Windows.
- A script works on a developer's machine but breaks on a runner using a different shell.
- User-supplied values are concatenated into a command string, leading to command injection.

Proper quoting must preserve both **argument boundaries** and **the content of each argument**. These two requirements are related, but not identical.

## 2. Shell Command Strings vs. Argument Vectors

A Java program receives arguments via:

~~~java
public static void main(String[] args)
~~~

Each element `args[i]` is one argument. The shell is not part of this array; the shell parses the command text before launching the program.

Bash example:

~~~bash
java -cp "out classes" com.example.Main "two words"
~~~

The shell strips the quotes surrounding `out classes` and `two words`, then passes each value as a separate argument. The syntactic quotes do not appear in `args[]`.

In Java:

~~~java
String[] args = {
    "-cp",
    "out classes",
    "com.example.Main",
    "two words"
};
~~~

This array already represents the argument boundaries. There is no need to join the elements into a quoted string and hope every shell interprets it the same way.

On POSIX, the operating system creates a process using an array of arguments. On Windows, `CreateProcess` receives a command-line string; the target program's runtime typically parses that string into `argv` itself. Therefore, the same value may require different representations depending on the platform and the receiving program.

## 3. Parsing Layers in a Command

A Java invocation from CI may pass through the following layers:

~~~text
YAML workflow / CI configuration
             |
             v
       Shell parser
   Bash / PowerShell / cmd.exe
             |
             v
      OS process creation
      POSIX argv / Windows
             |
             v
     Java launcher parser
       java / javac / jcmd
             |
             v
       Application parser
       main(String[] args)
~~~

There is no single escaping rule that works across every layer.

- YAML quoting protects the YAML value, not the shell command itself.
- Shell quoting protects tokens in the current shell.
- Windows command-line quoting depends on how the target program parses the command line.
- The Java launcher has its own syntax for `@argument-files`.
- The application may further parse an argument into an option, path, expression, or mini-language.

When an error occurs, identify the first layer that alters the data. Do not randomly add `\` or `"` everywhere.

## 4. Which Characters Usually Require Attention?

| Character/Value | Bash | PowerShell | cmd.exe | Java ProcessBuilder |
|---|---|---|---|---|
| Space | Splits words if unquoted | Splits arguments if unquoted | Splits arguments if unquoted | Preserved within a list element |
| `$` | Variable/command substitution expansion | Variable expansion or `$()` | Usually a literal character | No shell meaning if no shell is invoked |
| `&` | Control operator | Call operator | Command chaining operator | Treated as data if the target receives it properly |
| `;` | Command separator | Statement separator | Not a primary command separator | Treated as data |
| `|` | Pipe | Pipe | Pipe | Treated as data if no shell is invoked |
| `*` | May glob into filenames | Does not glob like Bash by default | Does not glob like Bash | Treated as data; Java launcher has its own classpath wildcard |
| `"` | Quote, with specific escape rules | Quote, with interpolation | Quote, with shell-specific rules | On Windows, also depends on the target's parser |
| `\` | Escapes outside quotes; only in some cases inside double quotes | Not a PowerShell escape character | Not a cmd escape character | May participate in Windows CRT quoting or Java argfile escaping |
| `%NAME%` | Literal characters unless expanded by the shell in another way | Usually literal characters | Environment expansion | Data if cmd is not invoked |
| `!NAME!` | Usually literal characters | History/other depending on context | Delayed expansion if enabled | Data if cmd is not invoked |

This table is a directional guide. Actual syntax depends on the shell version, parsing mode, and the type of executable invoked.

## 5. Quoting in Bash

Bash has three common mechanisms: single quotes, double quotes, and backslash escaping.

**Single quotes** preserve every character inside them literally. A literal single quote cannot be placed directly inside a pair of single quotes.

~~~bash
java -cp 'out classes' com.example.Main '$HOME & (x); *'
~~~

In this example, `$HOME`, `&`, the semicolon, and `*` are all literal data.

To include a single quote in a string, close the quote, escape the single quote, and reopen the quote:

~~~bash
printf '%s\n' 'it'\''s a build'
~~~

**Double quotes** preserve spaces and most metacharacters, but `$`, backticks, and certain backslash cases still have special meaning:

~~~bash
java -Dbuild.label="$BUILD_LABEL" -cp "$CLASSPATH" com.example.Main
~~~

**Backslash** escapes the next character when outside quotes:

~~~bash
printf '%s\n' two\ words
~~~

In scripts, use positional parameters or arrays to preserve arguments:

~~~bash
set -- -cp "$CLASSPATH" com.example.Main --label "$BUILD_LABEL" --path "$OUTPUT_PATH"
java "$@"
~~~

`"$@"` expands each positional parameter into a separate argument. Avoid using `"$*"` or concatenating all arguments into a single string if the goal is to preserve argument boundaries.

When forwarding all arguments of a script, use `"$@"`:

~~~bash
#!/usr/bin/env bash
exec java -jar app.jar "$@"
~~~

Do not use `eval` to execute user-supplied strings. `eval` forces the shell to re-parse the content and can turn data into commands.

## 6. Quoting in PowerShell

PowerShell uses the backtick as its escape character. A backslash `\` is typically a path character, not a PowerShell escape character.

A **single-quoted string** is literal. To represent a single quote inside, write two consecutive single quotes:

~~~powershell
$value = 'it''s a build'
~~~

A **double-quoted string** allows variable expansion and subexpressions:

~~~powershell
$label = "build-$env:BUILD_NUMBER"
$path = "output/$($env:BUILD_LABEL)"
~~~

To invoke a native executable with an argument array:

~~~powershell
$exe = Join-Path $env:JAVA_HOME 'bin/java.exe'
$args = @(
    '-cp'
    'out classes'
    'com.example.Main'
    '--label'
    'nightly build'
    '$HOME & (x); *'
)

& $exe @args
~~~

The call operator `&` executes the specified executable. Splatting `@args` passes array elements as separate arguments. This is much more readable than concatenating a command string.

PowerShell 7.3 changed how arguments are passed to native executables. The `$PSNativeCommandArgumentPassing` variable has `Legacy`, `Standard`, and `Windows` modes. On Windows, the default mode is `Windows`; this mode has special handling for `cmd.exe`, batch files, and certain script hosts. Windows PowerShell 5.1 has legacy behavior, so scripts with literal quotes may behave differently between 5.1 and PowerShell 7.3+.

You can check the current mode:

~~~powershell
$PSVersionTable.PSVersion
$PSNativeCommandArgumentPassing
~~~

The `--%` token is the stop-parsing token for native commands on Windows. It can be useful for a fixed command with many metacharacters, but the remainder of the line is treated as literal and the ability to use dynamic PowerShell expressions is limited. Do not treat `--%` as a general quoting solution for untrusted data.

For PowerShell 7+ scripts that need to construct a process programmatically, `System.Diagnostics.ProcessStartInfo.ArgumentList` allows adding arguments one by one:

~~~powershell
$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $exe
$psi.ArgumentList.Add('-cp')
$psi.ArgumentList.Add('out classes')
$psi.ArgumentList.Add('com.example.Main')
$psi.ArgumentList.Add('two words')

$process = [System.Diagnostics.Process]::Start($psi)
$process.WaitForExit()
$process.ExitCode
~~~

`ArgumentList` avoids manually concatenating `ProcessStartInfo.Arguments` into a single string. The target program on Windows still has its own parser, so values containing literal quotes should be tested against the actual executable.

## 7. Quoting in cmd.exe

`cmd.exe` uses double quotes to preserve paths or arguments containing spaces:

~~~bat
"%JAVA_HOME%\bin\java.exe" -cp "out classes" com.example.Main "two words"
~~~

Common metacharacters include:

- `&`: runs the next command.
- `&&`: runs the next command if the previous command succeeded.
- `||`: runs the next command if the previous command failed.
- `|`: pipe.
- `<` and `>`: input/output redirection.
- `(` and `)`: command grouping.
- `^`: escape character in cmd.

Example using a caret to escape an ampersand:

~~~bat
echo A^&B
~~~

Double quotes are usually sufficient to protect `&`, `|`, spaces, and certain metacharacters, but cmd has several additional processing steps. `%NAME%` is expanded into an environment variable. When delayed expansion is enabled (`cmd /v:on` or `EnableDelayedExpansion`), `!NAME!` is also expanded.

Do not assume that placing `%USER_INPUT%` inside quotes disables all expansion. `cmd /c` and especially `cmd /s /c` also have their own command-string processing rules; `/s` can strip leading/trailing quotes according to cmd's rules.

If you must invoke a batch file, account for the fact that arguments pass through `cmd.exe`. If you only need to run an `.exe` executable, invoking the executable directly avoids an extra layer of shell parsing.

## 8. Windows Command Line and the Microsoft C Runtime

Windows `CreateProcess` accepts a command-line string. It does not accept an `argv[]` array like POSIX `execve`. The target program decides how to parse the string into arguments.

The Microsoft C runtime has important rules for quotes:

- Spaces and tabs separate arguments when outside quotes.
- `\"` represents a literal double quote.
- Backslashes are preserved literally unless they appear immediately before a double quote.
- If there are `n` backslashes immediately before `"`, the parser checks whether `n` is even or odd: each pair of backslashes produces one literal backslash; any remaining odd backslash escapes the quote.
- Trailing backslashes at the end of a quoted argument must be handled specially so they do not accidentally escape the closing quote.

For example, to pass the value `a"b` under Microsoft C runtime rules, the command line may need to represent it as:

~~~text
"a\"b"
~~~

To pass a literal backslash immediately before a literal quote, you must double that backslash according to the rule above.

Not every Windows executable uses the Microsoft C runtime. Some programs have custom parsers or use older parsers. Therefore, an escaping function that works for `java.exe` does not automatically work for every `.exe`, `.bat`, or `.cmd`.

## 9. Using Java ProcessBuilder to Invoke Programs

`ProcessBuilder` accepts a command as a `List<String>` or `String...`. Each element describes the executable or a single argument:

~~~java
Path java = Path.of(
        System.getProperty("java.home"),
        "bin",
        isWindows() ? "java.exe" : "java"
);

List<String> command = List.of(
        java.toString(),
        "-cp",
        classPath,
        "com.example.Main",
        "--label",
        "nightly build"
);

Process process = new ProcessBuilder(command).start();
~~~

Do not manually add quotes around paths inside individual elements:

~~~java
// Wrong: quotes may become literal characters in the value.
new ProcessBuilder("java", "-cp", "\"out classes\"", "com.example.Main");

// Correct: pass the path as a single argument.
new ProcessBuilder("java", "-cp", "out classes", "com.example.Main");
~~~

`ProcessBuilder` does not invoke Bash, PowerShell, or cmd on its own. If the command is a direct executable, shell metacharacters are not executed as shell operators.

However, the API still has to translate arguments into a representation understood by the OS and the target executable. The Java API explicitly notes that the validity of the command list is operating-system dependent. On Windows, passing a literal double quote requires considering the target program's parser.

## 10. ProcessBuilder Does Not Replace a Shell Parser

The following strings do not automatically create pipes, redirection, or wildcard expansion when passed directly to `ProcessBuilder`:

~~~java
new ProcessBuilder("grep", "error", "*.log");
new ProcessBuilder("java", "-jar", "app.jar", ">", "build.log");
~~~

Here `*.log` may be passed verbatim to `grep`; `>` may become an ordinary argument. The shell is the layer that normally expands wildcards and handles redirection.

If you need a pipeline, Java 9+ provides `ProcessBuilder.startPipeline`:

~~~java
List<Process> pipeline = ProcessBuilder.startPipeline(List.of(
    new ProcessBuilder("find", "src", "-type", "f"),
    new ProcessBuilder("grep", "\\.java$")
));
~~~

The example above illustrates a pipeline on a POSIX environment with `find` and `grep`. On Windows, you need equivalent tools or to implement stream processing in Java.

If you intentionally invoke a shell:

~~~java
new ProcessBuilder("bash", "-c", "echo hello");
~~~

or:

~~~java
new ProcessBuilder("cmd.exe", "/c", "echo hello");
~~~

then shell parsing comes back into play. Any dynamic values concatenated into the script must be escaped for that specific shell, or passed via stdin/environment/file. Avoid concatenating untrusted data into `-c` or `/c` arguments.

## 11. Complete Java Example: Testing Argument Round-Trips

The following example launches a child JVM using `ProcessBuilder`. The program tests values containing spaces, an empty argument, quotes, backslashes, a Windows path, shell characters, and Unicode.

On Windows, the `encodeForWindowsCrt` method applies only to targets using Microsoft C runtime parsing. It doubles backslashes preceding a quote and adds a backslash so the quote is interpreted literally. On POSIX, values are passed as-is because the OS already receives an argument vector.

File `ArgRoundTrip.java`:

~~~java
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public final class ArgRoundTrip {
    private static final String[] EXPECTED = {
        "two words",
        "",
        "quote\"inside",
        "space and quote \"inside\"",
        "trailing-backslash\\",
        "C:\\Program Files\\Java\\bin",
        "$HOME & (x); *",
        "Ti\u1EBFng Vi\u1EC7t \u2013 \u6771\u4EAC",
        "-leading-option",
        "one-backslash\\\"then-quote"
    };

    public static void main(String[] args) throws Exception {
        if (args.length > 0 && args[0].equals("--child")) {
            for (int i = 1; i < args.length; i++) {
                System.out.println("ARG[" + (i - 1) + "]=" + escape(args[i]));
            }
            return;
        }

        Path javaExecutable = Path.of(System.getProperty("java.home"), "bin",
                isWindows() ? "java.exe" : "java").toAbsolutePath();

        List<String> command = new ArrayList<>();
        command.add(javaExecutable.toString());
        command.add("-cp");
        command.add(System.getProperty("java.class.path"));
        command.add(ArgRoundTrip.class.getName());
        command.add("--child");

        for (String argument : EXPECTED) {
            command.add(isWindows()
                    ? encodeForWindowsCrt(argument)
                    : argument);
        }

        Process process = new ProcessBuilder(command)
                .redirectErrorStream(true)
                .start();

        String output = new String(
                process.getInputStream().readAllBytes(),
                java.nio.charset.StandardCharsets.UTF_8);

        int exit = process.waitFor();
        if (exit != 0) {
            throw new IllegalStateException(
                    "Child exit code " + exit + ": " + output);
        }

        String[] lines = output.stripTrailing().split("\\R", -1);
        if (lines.length != EXPECTED.length) {
            throw new AssertionError(
                    "Expected " + EXPECTED.length
                    + " arguments, received " + lines.length + ": " + output);
        }

        for (int i = 0; i < EXPECTED.length; i++) {
            String expectedLine = "ARG[" + i + "]=" + escape(EXPECTED[i]);
            if (!expectedLine.equals(lines[i])) {
                throw new AssertionError(
                        "Argument " + i + " mismatch. Expected "
                        + expectedLine + " but got " + lines[i]);
            }
        }

        System.out.println("ARGUMENT_COUNT=" + EXPECTED.length);
        System.out.println("ARGUMENT_ROUND_TRIP=PASS");
        for (String line : lines) {
            System.out.println(line);
        }
    }

    private static String encodeForWindowsCrt(String value) {
        StringBuilder encoded = new StringBuilder();
        int backslashes = 0;

        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);

            if (current == '\\') {
                backslashes++;
                continue;
            }

            if (current == '"') {
                encoded.append("\\".repeat(backslashes * 2 + 1));
            } else {
                encoded.append("\\".repeat(backslashes));
            }

            encoded.append(current);
            backslashes = 0;
        }

        encoded.append("\\".repeat(backslashes));
        return encoded.toString();
    }

    private static String escape(String value) {
        StringBuilder escaped = new StringBuilder();

        value.codePoints().forEach(cp -> {
            if (cp == '\\') escaped.append("\\\\");
            else if (cp == '"') escaped.append("\\\"");
            else if (cp < 32 || cp > 126) {
                escaped.append(String.format("\\u%04X", cp));
            } else {
                escaped.appendCodePoint(cp);
            }
        });

        return escaped.toString();
    }

    private static boolean isWindows() {
        return System.getProperty("os.name")
                .toLowerCase()
                .contains("win");
    }
}
~~~

Compile and run from Bash, PowerShell, or cmd. Use the same output directory name containing a space to test the classpath:

~~~bash
javac --release 17 -d "out classes" ArgRoundTrip.java
java -cp "out classes" ArgRoundTrip
~~~

PowerShell can also use single quotes:

~~~powershell
javac --release 17 -d 'out classes' ArgRoundTrip.java
java -cp 'out classes' ArgRoundTrip
~~~

Verified stdout on Windows 11 with Azul OpenJDK 24.0.2:

~~~text
ARGUMENT_COUNT=10
ARGUMENT_ROUND_TRIP=PASS
ARG[0]=two words
ARG[1]=
ARG[2]=quote\"inside
ARG[3]=space and quote \"inside\"
ARG[4]=trailing-backslash\\
ARG[5]=C:\\Program Files\\Java\\bin
ARG[6]=$HOME & (x); *
ARG[7]=Ti\u1EBFng Vi\u1EC7t \u2013 \u6771\u4EAC
ARG[8]=-leading-option
ARG[9]=one-backslash\\\"then-quote
~~~

The example was compiled with `javac --release 17` and ran successfully. It verifies both the argument count and the content of each argument after crossing the process boundary.

**Important limitation:** `encodeForWindowsCrt` is an example for parsers following Microsoft C runtime rules, tested with `java.exe`. Do not use this function for arbitrary Windows executables without knowing the target's parser. When a target uses custom rules, use a response file/argument file, stdin or a data file, or write an adapter matching the target's parser.

## 12. Runtime.exec and Command String Concatenation Pitfalls

`Runtime.exec(String)` is not a general-purpose shell invocation mechanism. It does not understand Bash syntax, pipes, or redirection. Command string splitting can also be implementation-dependent.

Avoid writing:

~~~java
String command = "java -jar app.jar --name " + userInput;
Runtime.getRuntime().exec(command);
~~~

If `userInput` contains spaces, quotes, or shell metacharacters, the result may be incorrect. If the command is later routed through `sh -c` or `cmd /c`, data can turn into executable syntax.

Use `ProcessBuilder` with a list of arguments:

~~~java
List<String> command = List.of(
        javaExecutable.toString(),
        "-jar",
        jarPath.toString(),
        "--name",
        userInput
);

Process process = new ProcessBuilder(command).start();
~~~

This keeps each argument separate and does not require writing shell escaping for a command string. You still need to understand the target's parser rules on Windows when an argument contains literal quotes.

## 13. Paths, Classpath, and Working Directory

Use `Path` to construct paths instead of manually concatenating `/` or `\`:

~~~java
Path projectDir = Path.of("build", "workspace");
Path jar = projectDir.resolve("app.jar");
Path log = projectDir.resolve("logs").resolve("compile.log");
~~~

`Path.toString()` returns the operating system's native path representation. When passing it to `ProcessBuilder`, provide the path as a separate element:

~~~java
new ProcessBuilder(
        javaExecutable.toString(),
        "-jar",
        jar.toString()
);
~~~

Set the working directory using the API:

~~~java
ProcessBuilder builder = new ProcessBuilder(command);
builder.directory(projectDir.toFile());
~~~

Do not change the working directory by prepending `cd ... && ...` to a command string when no shell is needed.

Classpaths use different path separators:

- Windows: semicolon `;`.
- Linux/macOS: colon `:`.

Use `File.pathSeparator` when joining a classpath in Java:

~~~java
String classPath = String.join(
        java.io.File.pathSeparator,
        libraryPaths
);
~~~

If invoking a shell, remember that `;` can act as a command separator in Bash/PowerShell. When invoking via `ProcessBuilder`, the classpath is a separate argument and does not require shell quoting.

## 14. Java Launcher Argument Files (`@argfile`)

The Java launcher supports argument files to pass a list of options, classpath entries, the main class, and arguments via a text file. This is useful when the command line is too long or contains many paths with spaces.

Create `run.args`:

~~~text
-cp
"out classes"
ArgRoundTrip
--child
"two words"
""
"trailing-backslash\\"
"C:\\Program Files\\Java\\bin"
"$HOME & (x); *"
"quote\"inside"
~~~

Run:

~~~bash
java @run.args
~~~

In PowerShell, quote the `@run.args` token to prevent PowerShell from interpreting `@` as splatting syntax:

~~~powershell
java '@run.args'
~~~

Inside an argument file:

- Use whitespace or newlines to separate arguments.
- Enclose options/paths containing spaces in double quotes.
- Backslash is the escape character, so you must write `\\` to pass a literal backslash.
- `#` starts a comment until the end of the line.
- Relative paths are resolved from the current working directory, not the directory containing the argfile.
- Wildcards in an argfile are not expanded by the shell.
- The Java launcher supports `--disable-@files` to disable expansion.
- Recursive nesting of `@file` is not supported.

`@argfile` is Java launcher syntax. An arbitrary program will not understand this file unless it implements response-file parsing itself.

## 15. Shell Wildcards vs. Java Classpath Wildcards

In Bash, `*.jar` can be expanded into a list of files before the program runs:

~~~bash
java -cp "lib/*" com.example.Main
~~~

Here the wildcard is inside quotes, so the shell does not expand it. The Java launcher can handle the classpath wildcard within the classpath entry.

If you write:

~~~bash
java -cp lib/* com.example.Main
~~~

Bash may expand `lib/*` before the Java launcher receives the command, altering argument boundaries and results.

PowerShell and cmd have different wildcard rules than Bash. Do not rely on shell globbing if you want a script to work across multiple operating systems. Let the Java launcher handle classpath wildcards using its own syntax, or generate the classpath explicitly from your build tool.

## 16. Using Environment Variables and Stdin for Complex Data

If data is long, contains many quotes, or may contain control characters, passing it via stdin or a file can be easier to control than via the command line.

`ProcessBuilder` allows modifying the environment:

~~~java
ProcessBuilder builder = new ProcessBuilder(command);
builder.environment().put("BUILD_LABEL", buildLabel);
builder.directory(projectDir.toFile());
Process process = builder.start();
~~~

Sending content via stdin:

~~~java
try (var writer = process.outputWriter(
        java.nio.charset.StandardCharsets.UTF_8)) {
    writer.write(configurationJson);
}
~~~

Only use environment variables for data appropriate for the process environment. Secrets in the environment can still be exposed through diagnostics or process inspection; do not log signing keys or credentials. For large payloads or complex structures, a JSON/YAML file with restricted permissions is often easier to inspect.

## 17. Quoting in Maven and Gradle Scripts

Build tools typically receive arguments via a wrapper, then parse options using their own syntax.

Maven:

~~~bash
./mvnw --batch-mode -DskipTests=false -Dbuild.label="nightly build" clean verify
~~~

PowerShell:

~~~powershell
.\mvnw.cmd --batch-mode '-Dbuild.label=nightly build' clean verify
~~~

Gradle:

~~~bash
./gradlew -PbuildLabel="nightly build" clean build
~~~

In PowerShell:

~~~powershell
.\gradlew '-PbuildLabel=nightly build' clean build
~~~

Shell quotes only preserve a single argument. After the wrapper receives the argument, Maven/Gradle parses the `-D...` or `-P...` option.

If a property value comes from a user, pass it through a properly quoted variable for the current shell. Do not concatenate raw values into scripts or use `eval`.

## 18. Quoting in GitHub Actions and YAML

A GitHub Actions workflow has at least two layers: the YAML parser and the shell selected by the runner. YAML block scalars help preserve multiline scripts:

~~~yaml
steps:
  - name: Compile
    shell: bash
    env:
      BUILD_LABEL: ${{ github.ref_name }}
    run: |
      java -version
      ./mvnw --batch-mode "-Dbuild.label=$BUILD_LABEL" clean verify
~~~

If using PowerShell:

~~~yaml
steps:
  - name: Compile on Windows
    shell: pwsh
    env:
      BUILD_LABEL: ${{ github.ref_name }}
    run: |
      java -version
      .\mvnw.cmd --batch-mode "-Dbuild.label=$env:BUILD_LABEL" clean verify
~~~

YAML quoting does not replace shell quoting. `run: |` only preserves the block text; Bash or PowerShell still parses the content according to its own syntax.

For user-supplied values in event payloads, prefer passing them via `env:` and referencing them as quoted variables. Avoid interpolating untrusted data directly into shell scripts before execution.

Choose `shell` explicitly when consistent behavior is needed. Linux runners typically use Bash; Windows runners typically use PowerShell. Do not copy a Bash command line verbatim into `cmd` or PowerShell without adapting the syntax.

## 19. Shell Injection and Security Principles

Command injection occurs when data is interpreted as executable syntax instead of data.

Dangerous example:

~~~java
String script = "sh -c \"grep " + userPattern + " app.log\"";
new ProcessBuilder("sh", "-c", script).start();
~~~

If `userPattern` contains quotes or shell operators, the content can alter the executed command.

Safer approach:

~~~java
new ProcessBuilder(
        "grep",
        "--",
        userPattern,
        "app.log"
).start();
~~~

`--` is an end-of-options marker supported by many CLIs, preventing values starting with `-` from being misinterpreted as options. Confirm that the target program supports `--`; not every CLI follows this convention.

Key principles:

- Prefer `ProcessBuilder(List<String>)`.
- Do not invoke a shell if you only need to launch an executable.
- Do not concatenate untrusted data into `sh -c`, `bash -c`, `cmd /c`, or `powershell -Command`.
- Validate options/values against the application contract.
- Use an allowlist of executables and paths when possible.
- Do not use `eval`.
- Do not put secrets on the command line, because process arguments can appear in diagnostics/process listings.
- When a target requires a script, create a script file with restricted permissions and pass data separately via file/stdin.

Quoting does not replace validation. A properly quoted argument can still cause the target application to perform a dangerous action if that value is passed to an inappropriate option.

## 20. Unicode and Encoding

Quoting protects argument boundaries; encoding determines how bytes or code units are converted into characters.

For Java processes:

- `String` stores data in UTF-16.
- Windows command lines use Unicode APIs when creating processes.
- POSIX arguments are byte strings; conversion depends on the environment and encoding.
- stdout/stderr have their own encodings; do not assume every console uses UTF-8 unless configured.
- Argument/response files use the encoding specified by the tool's documentation.

If CI involves Vietnamese, Japanese, or non-ASCII characters, test both input and output. Set the encoding explicitly for the compiler/resources:

~~~xml
<project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
~~~

In Java code, when reading process output, choose the charset agreed upon with the child program:

~~~java
String output = new String(
        process.getInputStream().readAllBytes(),
        java.nio.charset.StandardCharsets.UTF_8
);
~~~

Do not rely implicitly on the default charset if output is transferred between Windows and Linux runners.

## 21. Reading Child Process stdout, stderr, and Exit Code

A process may succeed while writing warnings to stderr; it may also write results to stdout and then exit with a non-zero exit code.

Read the two streams separately:

~~~java
Process process = new ProcessBuilder(command).start();

byte[] stdout = process.getInputStream().readAllBytes();
byte[] stderr = process.getErrorStream().readAllBytes();
int exitCode = process.waitFor();
~~~

For programs that may write large amounts of output, read stdout and stderr concurrently or redirect them to files. If you only read one stream while the other stream's buffer fills up, the child process may block and never terminate.

Merge stderr into stdout when log ordering matters:

~~~java
Process process = new ProcessBuilder(command)
        .redirectErrorStream(true)
        .start();
~~~

CI should fail when the exit code is non-zero, while preserving logs and test reports. Do not infer a successful build solely from a `BUILD SUCCESS` line if the final process returned a non-zero exit code.

## 22. Common Quoting Errors

| Symptom | Cause | Resolution |
|---|---|---|
| Path with spaces is split | Argument is not quoted at the shell layer | Quote the entire value in the active shell or pass a single list element |
| `$HOME` disappears | Bash/PowerShell expands the variable | Use single quotes for literals or pass via an array |
| `&` runs another command | cmd/Bash/PowerShell treats `&` as an operator | Quote/escape for the shell or bypass the shell with ProcessBuilder |
| `*.jar` becomes multiple arguments | Shell glob expansion | Quote the wildcard or let the Java launcher handle classpath wildcards |
| Literal quotes are lost on Windows | Target parser treats quotes as delimiters | Escape per Microsoft CRT when the parser matches; test the target |
| Trailing backslash breaks quotes | Backslash before a closing quote is special in Windows CRT | Avoid trailing slashes in paths if unnecessary; otherwise test the specific parser |
| Script works in PS 7 but fails in PS 5.1 | Native argument passing differs across versions | Check version/mode or use `ProcessStartInfo.ArgumentList` in modern PowerShell |
| `cmd /c` behaves differently from direct command | Adds a layer of cmd parsing | Remove `/c` if shell syntax is not needed |
| ProcessBuilder does not create a pipe | ProcessBuilder does not invoke a shell | Use `startPipeline` or connect streams in Java |
| CI receives corrupted Vietnamese characters | Encoding mismatch across shell, file, and process | Specify UTF-8 and verify output encoding |
| Value starting with `-` is treated as an option | CLI parses the value as an option | Use `--` if supported by the program or pass using `--name=value` syntax |

## 23. How to Debug Actual Arguments

When a command does not behave as expected, print each argument on the target program side rather than only printing the command string on the caller side.

Example:

~~~java
for (int i = 0; i < args.length; i++) {
    System.out.printf("args[%d]=<%s>%n", i, args[i]);
}
~~~

Use test data that includes:

- Strings with spaces.
- Empty strings.
- Literal double quotes.
- Backslashes in the middle and at the end of a string.
- Paths with spaces.
- `&`, `|`, `;`, `$`, `%`, `!`, `*`.
- Strings starting with `-`.
- Accented Unicode and non-ASCII characters.

Compare the expected value with the received value at each index. Do not compare only the total argument count, because one split argument could coincidentally produce the same count.

In PowerShell, you can use `Trace-Command -Name ParameterBinding` to inspect how arguments are bound. In Java, logging `ProcessBuilder.command()` only shows the input list; it does not prove the target received the exact arguments. Use an echo-args utility or a test child process.

## 24. Cross-Platform Testing in CI

A quoting test suite should run on at least one Windows runner and one Linux runner if the product supports both.

Example matrix:

~~~yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, windows-latest]

runs-on: ${{ matrix.os }}
steps:
  - uses: actions/checkout@v7
  - uses: actions/setup-java@v6
    with:
      distribution: temurin
      java-version: '17'
  - name: Compile argument test
    shell: bash
    run: |
      javac --release 17 -d "out classes" ArgRoundTrip.java
      java -cp "out classes" ArgRoundTrip
~~~

In a real workflow, if using `shell: bash` on Windows, the runner must have Bash available. If the project wants to test PowerShell and cmd specifically, create separate jobs using `shell: pwsh` or `shell: cmd`.

Testing the same dataset across OSes helps uncover bugs in the shell layer, process creation, path handling, and target parser. If you only run a sample build command, edge cases such as empty arguments or embedded quotes may go undetected.

## 25. Checklist Before Writing Scripts That Invoke Java

- Identify the actual shell: Bash, PowerShell, cmd.exe, or no shell.
- Identify the target executable and its parser.
- Keep each argument as a separate element; do not concatenate into a command string.
- Quote according to the current shell layer; do not copy syntax from another shell.
- Use `Path` and `File.pathSeparator` in Java instead of manually concatenating paths.
- On Windows, verify quotes and backslashes against the target's parser.
- For the Java launcher, consider `@argfile` for long commands.
- Pass complex payloads via stdin or a file with an explicit encoding.
- Use `--` if the CLI supports it and a value may start with `-`.
- Never pass untrusted input into `eval`, `sh -c`, `cmd /c`, or `powershell -Command`.
- Read stdout/stderr, check the exit code, and avoid deadlocks.
- Test argument round-trips on every supported OS/shell.
- Record the JDK, shell, and runner versions when diagnosing issues.

Argument quoting is not a single escaping formula that applies everywhere. It is about preserving data across every parser along the path from script to program. By using argument arrays, understanding the differences between shells and OSes, and verifying the actual values received by the target, Java tooling can run consistently on Windows, Linux, and macOS.

## References

- Oracle Java SE 24 — [ProcessBuilder API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/ProcessBuilder.html).
- Oracle JDK — [The java Command and Argument Files](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html).
- Microsoft Learn — [PowerShell about_Parsing](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing).
- Microsoft Learn — [cmd Command](https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/cmd).
- Microsoft Learn — [Parsing C Command-Line Arguments](https://learn.microsoft.com/en-us/cpp/c-language/parsing-c-command-line-arguments).
- GNU Bash Manual — [Quoting](https://www.gnu.org/software/bash/manual/html_node/Quoting.html).
- GNU Bash Manual — [Shell Syntax](https://www.gnu.org/software/bash/manual/bash.html).
