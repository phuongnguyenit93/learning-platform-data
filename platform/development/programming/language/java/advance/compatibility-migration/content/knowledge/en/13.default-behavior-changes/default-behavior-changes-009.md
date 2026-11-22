# ProcessBuilder Behavior and Passing Arguments Across Operating Systems

During a Java application upgrade or migration, code invoking an external program may work on a developer machine yet fail on Windows, Linux, or macOS. The cause does not necessarily lie in the JDK version; many failures stem from differences between the **argument list passed by Java**, **how the operating system creates processes**, **the target program's command-line parsing rules**, and **shell syntax if the application explicitly invokes a shell**.

`java.lang.ProcessBuilder` is the standard API for configuring and launching child processes. Using the API properly helps avoid many issues with paths containing spaces, empty arguments, special characters, working directories, and data streams. However, ProcessBuilder **does not guarantee every operating system interprets command lines identically**, and it does not automatically turn a shell command string into pipelines or redirections.

This lesson explains ProcessBuilder's contract, points out Windows/Unix-like differences, illustrates correct and incorrect commands, guides managing stdin/stdout/stderr, environments, and process lifecycles, and provides a testing procedure when migrating Java applications to a new JDK or platform.

## 1. Distinguishing Four Layers of Command Processing

When Java needs to run an external program, separate four layers:

1. **Java code** builds the command's `List<String>` element list: the executable, followed by each argument.
2. **The JDK** translates that configuration into the platform's process-creation call.
3. **The operating system** creates the process, providing the environment, working directory, and handles or file descriptors.
4. **The target program** receives and parses the arguments according to its runtime, libraries, or custom conventions.

When Java invokes a shell such as `/bin/sh` or `cmd.exe`, there is an additional shell syntax processing layer before the target program is launched.

Diagram:

```text
Java ProcessBuilder
      |
      | command = [executable, arg1, arg2, ...]
      v
JDK process-launch implementation
      |
      +-- Unix-like: process/exec with separate argv
      |
      +-- Windows: CreateProcess and a command-line string
      |
      v
Child process
      |
      +-- receives argv per runtime/program rules
      +-- uses environment, cwd, and I/O streams
```

If invoking a shell:

```text
Java
  |
  v
ProcessBuilder("/bin/sh", "-c", "echo ... | grep ...")
  |
  v
Shell parses quotes, $, |, >, ...
  |
  v
One or more child processes
```

**First principle:** when the executable and arguments are known, pass each argument as a separate element in ProcessBuilder. Only use a shell when shell syntax or features are genuinely required.

## 2. ProcessBuilder: Pass a List, Not a Shell Command String

### 2.1. Correct Example with Arguments Containing Spaces

```java
import java.io.IOException;
import java.util.List;

public final class LaunchExample {
    public static void main(String[] args)
            throws IOException, InterruptedException {

        List<String> command = List.of(
            "my-tool",
            "--output",
            "reports/final report.txt",
            "--title",
            "Annual Report"
        );

        Process process = new ProcessBuilder(command)
            .inheritIO()
            .start();

        int exitCode = process.waitFor();
        System.out.println("Exit code: " + exitCode);
    }
}
```

This is a command construction pattern; the executable `my-tool` is only an illustrative name and must actually exist in the runtime environment. ProcessBuilder receives four arguments after the executable: `--output`, `reports/final report.txt`, `--title`, `Annual Report`. Spaces inside the second and fourth arguments do **not** cause Java to split them into multiple arguments.

### 2.2. Incorrect Example: Combining the Entire Command into One Element

```java
// Wrong if expecting Java to parse the command line:
new ProcessBuilder(
    "my-tool --output reports/final report.txt"
).start();
```

Here Java will try to launch an executable named after that entire string, rather than looking up `my-tool` and splitting arguments. The command may throw `IOException` because the executable cannot be found.

Another incorrect variant:

```java
String output = "reports/final report.txt";

new ProcessBuilder(
    "my-tool",
    "--output " + output
).start();
```

The second argument here is **a single element** whose content is `--output reports/final report.txt`. If the target program expects an `--output` option followed by a path, it will not interpret it properly.

Correct way:

```java
new ProcessBuilder(
    "my-tool",
    "--output",
    output
).start();
```

### 2.3. Do Not Manually Insert Double Quotes to “Protect” Spaces

```java
String path = "C:\\Program Files\\Example Tool\\data.txt";

// Do not manually add quotes to argument data:
new ProcessBuilder("my-tool", "\"" + path + "\"");
```

If the intention is to pass the path without quotes as data, use:

```java
new ProcessBuilder("my-tool", path);
```

For programs that accept arguments under common conventions, the JDK handles the necessary wrapping for the process launch call. Manually adding quotes can cause the program to receive the quotes as part of the value or cause parser discrepancies across platforms.

The exception is when you **deliberately invoke a shell** and supply command code to the shell. In that case, quoting belongs to shell syntax rather than the regular list-passing API; this is examined separately in a later section.

### 2.4. An Argument List Is Not Equivalent to a Logged String

If logged using `String.join(" ", command)`, boundaries of arguments containing spaces or empty strings become ambiguous.

Example:

```text
["tool", "--name", "Alice Smith", ""]
```

A space-joined log line can look like four or more arguments; it does not accurately reproduce how the target program receives the arguments.

For diagnostics, log each argument with its index and an unambiguous representation (while masking or omitting secrets):

```java
for (int i = 0; i < command.size(); i++) {
    System.out.printf(
        "arg[%d] length=%d%n",
        i,
        command.get(i).length()
    );
}
```

Do not print passwords, access tokens, private keys, or sensitive contents into logs just to verify quoting.

## 3. Platform Differences: Unix-Like vs. Windows

### 3.1. Linux and macOS: Executable with Separate argv

On Unix-like OSes, the process-creation call typically reaches a form of `exec` that accepts an executable path and an array of argument strings. Without going through a shell, characters such as spaces, `*`, `$`, `|`, `>`, and `;` do not automatically become shell syntax.

Example:

```java
new ProcessBuilder(
    "/usr/bin/printf",
    "%s\\n",
    "hello world",
    "*.txt",
    "$HOME"
).inheritIO().start().waitFor();
```

As intended, the `printf` program receives `hello world`, `*.txt`, and `$HOME` as separate arguments. There is no step expanding `*.txt` into filenames via globbing or expanding `$HOME` to the home directory just because those two strings appear in ProcessBuilder.

When you need `$HOME` resolved to a concrete value, read the environment in Java or intentionally invoke a shell. When searching files by pattern, use `Files.newDirectoryStream`, `Files.walk`, or appropriate file APIs rather than expecting implicit globbing.

### 3.2. Windows: CreateProcess Receives a Command-Line String

Windows passes a command-line string to the process-creation call. Many Windows programs use the C/C++ runtime or a custom parser to build `argv` from that string. The JDK must convert the argument list supplied by Java into a command-line string according to the platform's rules.

Consequences:

- Java still expects each argument as a separate element.
- The JDK handles quoting/escaping for many common cases.
- The target program may use a parser that differs from Microsoft C runtime conventions.
- Batch scripts, `cmd.exe`, and PowerShell add their own syntax layers.
- Characters such as quotes, backslashes, and spaces must be tested with the **actual target program**.

Do not manually construct a Windows command-line string and pass the entire string as a single element in ProcessBuilder. That does not behave “like cmd.exe” and usually corrupts the executable path.

### 3.3. Quick Comparison

| Scenario | Linux/macOS without shell | Windows without shell |
|---|---|---|
| Argument with spaces | One Java element is passed as one argument | JDK quotes when needed; target program's parser determines final result |
| `*.txt` | No automatic glob expansion | Do not assume automatic glob expansion |
| `$HOME` or `%USERPROFILE%` | No automatic shell variable substitution | No automatic cmd variable substitution |
| `|`, `>`, `&&` | Not a pipe/redirection | Not a pipe/redirection unless run via a shell |
| `.sh` file | Needs an interpreter or valid executable script | Not a standard Windows executable |
| `.bat`/`.cmd` file | Not a standard Unix script | Note handling by the command processor |
| Executable path with spaces | Pass the exact path as the first element | Pass the exact path as the first element |
| PATH separator | Colon | Semicolon |
| Case sensitivity | Usually case-sensitive | Usually case-insensitive on common filesystems |

These descriptions of filesystems and argument parsing reflect common characteristics, not absolute rules for every filesystem, runtime, or executable on each platform.

## 4. Executable Paths: Absolute, Relative, and PATH

### 4.1. Use Absolute Paths When Reproducibility Is Needed

Windows example:

```java
String exe = "C:\\Program Files\\Example Tool\\my-tool.exe";

ProcessBuilder builder = new ProcessBuilder(
    exe,
    "--version"
);
```

There is no need to wrap `C:\Program Files\...` with quotes. The full path is a single element of `command()`.

Unix example:

```java
ProcessBuilder builder = new ProcessBuilder(
    "/usr/local/bin/my-tool",
    "--version"
);
```

Absolute paths eliminate part of the dependency on PATH, reduce the risk of picking the wrong binary with the same name, and make environments easier to reproduce. However, verify that the path exists on every machine/container and has execute permissions.

### 4.2. Running Programs via PATH

```java
new ProcessBuilder("git", "--version")
    .inheritIO()
    .start();
```

Here `git` must be found by the system according to the JDK/OS executable lookup mechanism in the active environment. Results depend on how Java is launched, PATH configuration, shell/IDE/service/container, and platform.

Do not assume `git` is on PATH simply because typing `git --version` succeeds in another terminal. An interactive terminal may load shell profiles or set an environment different from the service running Java.

If you need to guarantee the right binary, configure an environment-specific absolute path instead of assuming its location.

### 4.3. `directory()` Is Not a Way to Set the Executable Path

```java
import java.nio.file.Path;

Path work = Path.of("/opt/app/work");

ProcessBuilder builder =
    new ProcessBuilder("/usr/bin/my-tool", "input.txt");

builder.directory(work.toFile());
```

`directory()` sets the working directory for the child process. It does not mean every PATH lookup for the executable automatically switches to searching in that working directory. To avoid ambiguity across operating systems, use an absolute executable path when needed.

The path `input.txt` opened by the child program itself is typically resolved relative to the process's working directory (unless that program defines its own rules). Ensure the directory exists and the service account has access permissions.

### 4.4. Launching a Child Java Process with the Current Runtime

If the parent program needs to launch a child Java process using the same JDK currently running, you can locate the launcher via `java.home`:

```java
import java.nio.file.Path;
import java.util.Locale;

static boolean isWindows() {
    return System.getProperty("os.name")
        .toLowerCase(Locale.ROOT)
        .contains("win");
}

static Path javaLauncher() {
    String file = isWindows() ? "java.exe" : "java";
    return Path.of(
        System.getProperty("java.home"),
        "bin",
        file
    );
}
```

Usage:

```java
Path java = javaLauncher();

Process process = new ProcessBuilder(
    java.toString(),
    "-version"
).inheritIO().start();

int exitCode = process.waitFor();
```

This is a common strategy, though you still need to confirm the runtime image contains the appropriate launcher. A custom packaged application or embedded environment may have a different layout from a full JDK.

## 5. Do Not Confuse ProcessBuilder with a Shell

### 5.1. Pipes and Redirections Do Not Work Automatically

Wrong when expecting shell processing:

```java
new ProcessBuilder(
    "find",
    ".",
    "|",
    "grep",
    ".java"
).start();
```

This attempts to run `find` with the arguments `.`, `|`, `grep`, and `.java`. It does not create a pipeline between two processes.

Similarly:

```java
new ProcessBuilder(
    "my-tool",
    "--output",
    ">",
    "result.txt"
).start();
```

The `>` character is just an argument without a shell; it does not automatically redirect stdout to a file.

If you want to send stdout to a file, ProcessBuilder provides a redirect API:

```java
import java.io.File;

ProcessBuilder builder = new ProcessBuilder(
    "my-tool",
    "--version"
);

builder.redirectOutput(
    ProcessBuilder.Redirect.to(new File("result.txt"))
);

Process process = builder.start();
int exitCode = process.waitFor();
```

### 5.2. If a Shell Is Genuinely Needed on Unix

Fixed shell command example:

```java
Process process = new ProcessBuilder(
    "/bin/sh",
    "-c",
    "printf '%s\\n' hello | grep hello"
).inheritIO().start();

int exitCode = process.waitFor();
```

The shell parses `printf ... | grep ...`, sets up the pipe, and creates the required processes. This is an appropriate option when shell capabilities are genuinely required.

However, user-supplied data must **not** be concatenated directly into the shell command string. If you need to pass dynamic data into a Unix script, pass it via the shell's positional parameters rather than string interpolation:

```java
String userValue = "a b; $(not-a-command)";

Process process = new ProcessBuilder(
    "/bin/sh",
    "-c",
    "printf '%s\\n' \"$1\"",
    "sh",
    userValue
).inheritIO().start();
```

In this case, `userValue` is a separate argument accessed by the shell via `"$1"`. Because it is placed inside double quotes in the fixed script, the value is treated as data rather than re-parsed as shell code. The `$` and `;` inside the variable value will not become command substitution or a new command separator.

For simple operations like printing strings, still prefer invoking the executable directly to avoid needing a shell.

### 5.3. If `cmd.exe` Is Needed on Windows

Fixed cmd command example:

```java
Process process = new ProcessBuilder(
    "cmd.exe",
    "/c",
    "echo Hello from cmd"
).inheritIO().start();
```

`cmd.exe` has its own grammar for characters like `&`, `|`, `<`, `>`, `^`, `%`, and environment variable expansion rules; when delayed expansion is enabled, `!` is also processed. Therefore, concatenating untrusted data into the `/c` command string can cause command injection or corrupted values.

Do not mechanically apply Bash escaping rules to cmd.exe. If dynamic values must be passed, design a safe protocol via stdin, environment variables, or a controlled data file; or better yet, invoke the target executable directly without going through cmd.

### 5.4. PowerShell Has Different Syntax from cmd

When running a PowerShell script, invoke the interpreter with the script path and separate arguments:

```java
Process process = new ProcessBuilder(
    "powershell.exe",
    "-NoProfile",
    "-NonInteractive",
    "-File",
    "C:\\Scripts\\report.ps1",
    "-OutputPath",
    "C:\\Reports\\Monthly report.csv"
).inheritIO().start();
```

`powershell.exe` is Windows PowerShell if installed/available. PowerShell 7 typically uses the `pwsh` launcher and is more cross-platform; do not assume `pwsh` is always present on every machine. `-File` is suitable for running script files; `-Command` evaluates PowerShell expressions and has different quoting and parameter binding rules.

When arguments contain special characters, empty paths, or nested quoting, verify the actual script with end-to-end testing. Do not share a single quoting pattern across `cmd`, PowerShell, and `sh`.

## 6. `.sh`, `.bat`, and `.cmd` Scripts

### 6.1. Unix Shell Scripts

A script on Linux/macOS may have a shebang:

```sh
#!/bin/sh
printf 'Argument: %s\n' "$1"
```

If the file has execute permissions and the environment supports shebangs, it can be run directly via its executable path. Otherwise, pass the interpreter explicitly:

```java
new ProcessBuilder(
    "/bin/sh",
    "/opt/app/scripts/process.sh",
    "file with spaces.txt"
).inheritIO().start();
```

Shell paths and options can vary across Linux, macOS, or minimal containers. Do not use `bash` if the script only needs `sh` unless Bash-specific features are truly required.

Note that scripts checked out or copied from Windows may have CRLF line endings, causing shebang or interpreter failures on Unix. Execute permissions and case sensitivity must also be checked.

### 6.2. Windows Batch Scripts

On Windows, `.bat` or `.cmd` files are interpreted according to command processor rules. One explicit approach is invoking `cmd.exe` and the script under controlled configuration. However, passing values containing `&`, `%`, quotes, or control characters can undergo additional cmd parsing and batch parameter expansion layers.

Example using only simple names and arguments:

```java
new ProcessBuilder(
    "cmd.exe",
    "/c",
    "C:\\Scripts\\build-report.cmd",
    "daily"
).inheritIO().start();
```

Do not treat this simple example as a general-purpose escaping solution for all arguments. If the script path or arguments contain spaces/special characters, test specifically with Windows, the JDK, and the target script. For untrusted data, avoid batch scripts and switch to a program accepting arguments directly or receiving data via stdin/file.

### 6.3. Detecting the Platform Before Choosing the Launcher

Pattern using two different command shapes by OS:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

static List<String> buildCommand(String input) {
    boolean windows = System.getProperty("os.name")
        .toLowerCase(Locale.ROOT)
        .contains("win");

    List<String> cmd = new ArrayList<>();

    if (windows) {
        cmd.add("C:\\Tools\\analyzer.exe");
    } else {
        cmd.add("/usr/local/bin/analyzer");
    }

    cmd.add("--input");
    cmd.add(input);
    return cmd;
}
```

Even if only the executable path differs, option handling still requires verifying that the programs on both platforms share the same CLI contract. Do not assume executable names, path separators, or stdout charsets are identical.

## 7. Windows Command-Line Parsing: Why Argument Lists Still Require Testing

ProcessBuilder provides a platform-independent argument list API, yet on Windows a program receives a command-line string from the operating system. Each runtime or executable may interpret quotes and backslashes differently.

Examples of values prone to issues:

```text
a b
"quoted"
C:\data\folder\
value&other
100%complete
empty argument: ""
text with non-ASCII characters
```

A program compiled with the common C/C++ runtime may receive `argv` according to specific quote/backslash rules; another program may call `GetCommandLineW` and parse it manually. A batch script is parsed by `cmd.exe` under yet another set of rules.

Therefore:

- For regular native executables, pass each argument via ProcessBuilder and test in practice.
- Do not pre-escape arguments as if typing a command into a shell.
- Do not use `cmd.exe /c` when you only need to launch an `.exe`.
- For batch/PowerShell, verify the interpreter's rules and the script's contract.
- For complex data, use a UTF-8 file or stdin when supported by the target program.

### 7.1. Argument Round-Trip Test

You can write a child Java program that prints the count and each argument:

```java
public final class ArgsPrinter {
    public static void main(String[] args) {
        System.out.println("argc=" + args.length);

        for (int i = 0; i < args.length; i++) {
            String value = args[i];
            System.out.println(
                i + ": length=" + value.length()
                    + ", value=[" + value + "]"
            );
        }
    }
}
```

Parent code:

```java
import java.nio.file.Path;
import java.util.List;

List<String> command = List.of(
    javaLauncher().toString(),
    "-cp",
    Path.of("build", "classes")
        .toAbsolutePath()
        .toString(),
    "ArgsPrinter",
    "hello world",
    "",
    "a\"b",
    "C:\\Temp\\some folder\\",
    "Tiếng Việt"
);

Process process = new ProcessBuilder(command)
    .inheritIO()
    .start();

int code = process.waitFor();
```

`javaLauncher()` is the helper defined in the previous section. The classpath directory is illustrative and must contain the compiled `ArgsPrinter` class. If tests use Maven/Gradle, obtain the actual classpath from the build tool rather than hardcoding a directory.

Run on the target JDK and OS to verify that ordering, empty arguments, quotes, spaces, backslashes, and Unicode are preserved across the launch boundary to the target Java program.

### 7.2. Empty Arguments and Whitespace

There is a difference between:

- Passing no argument.
- Passing an empty argument `""`.
- Passing an argument containing only spaces.
- Passing a path with spaces inside it.

Example:

```java
new ProcessBuilder(
    "my-tool",
    "--value",
    ""
);
```

These are three elements, where the third element is an empty string. A CLI parser may treat “option present with an empty value” differently from “option absent”. Test this rather than collapsing with `String.trim()` and losing the distinction.

## 8. Environment Variables and Operating System Differences

### 8.1. Child Process Environment

`ProcessBuilder.environment()` returns a mutable map for processes created by that builder:

```java
ProcessBuilder builder = new ProcessBuilder(
    "/usr/bin/env"
);

builder.environment().put("APP_MODE", "integration-test");
builder.environment().put("LANG", "C.UTF-8");

builder.inheritIO();

Process process = builder.start();
int exitCode = process.waitFor();
```

`/usr/bin/env` and the `C.UTF-8` locale value are Unix-like examples; neither is guaranteed to exist on every system. In production, use the actual executable and check locales supported by the OS.

The environment map is a copy for configuring the child process; modifying it does not mutate the parent Java process's environment or system-wide environment variables.

### 8.2. Mismatch Between Terminal and Service Environments

A Java application running from an IDE, systemd, Windows Service, container, or CI may receive different `PATH`, `HOME`, `TEMP`, `JAVA_HOME`, or proxy settings compared to an interactive terminal.

For example, a login shell may source `.bashrc` or a profile, whereas a service does not read those files. If Java runs in a container, PATH may contain only directories built into the image.

Therefore, when an executable is found only in one environment, inspect the actual environment of the Java process rather than checking a separate terminal.

### 8.3. Case Sensitivity of Environment Variable Names

On many Unix-like OSes, environment variable names are case-sensitive: `PATH` and `Path` can be two distinct names. Windows generally handles environment variable names case-insensitively.

The Java `Map` returned by `environment()` has platform-dependent behavior. Avoid writing code that relies on storing `PATH` and `Path` simultaneously and expecting identical behavior across all OSes.

### 8.4. Changing PATH Is Not the Best Strategy for Selecting an Executable

Some code modifies `builder.environment().put("PATH", ...)` and expects the JDK to always search for the executable along the new PATH. Executable lookup details can depend on the JDK and OS, because command resolution and setting up the child's environment are not necessarily the same step.

To select an executable reliably, prefer a configured and validated absolute path. Setting PATH in the environment is appropriate when the **child program** or its descendant processes need that PATH environment.

### 8.5. Secrets in the Environment

Environment variables can help avoid exposing secrets on the command line, but they are not an absolute secret vault: diagnostic tools, crash reports, or processes with the same privileges may read them depending on the OS.

Do not log the entire `builder.environment()`, print access tokens, or place secrets in `ProcessBuilder.command()` if a safer channel exists. For sensitive secrets, prefer a secret manager, restricted-permission files, or IPC aligned with the application's security model.

## 9. Working Directory and Path Handling

### 9.1. Setting the Working Directory

```java
import java.nio.file.Files;
import java.nio.file.Path;

Path workDir = Path.of("work", "jobs", "42").toAbsolutePath();

Files.createDirectories(workDir);

ProcessBuilder builder =
    new ProcessBuilder("/usr/local/bin/analyzer", "input.csv");

builder.directory(workDir.toFile());

Process process = builder.start();
```

On Windows, the executable path must be replaced with a valid path. If the target program opens `input.csv` using a relative path, it will typically look for the file relative to the supplied working directory.

`directory(null)` (the default) typically uses the parent Java process's working directory. Do not assume the working directory is always the directory containing the JAR; it depends on how the application was launched.

### 9.2. Use `Path` Instead of Concatenating Separators

Do not construct file paths by manual string concatenation:

```java
String file = base + "/" + subfolder + "/" + name;
```

Instead use:

```java
Path input = basePath
    .resolve("data")
    .resolve("report 2026.csv")
    .toAbsolutePath();

new ProcessBuilder(
    executable.toString(),
    "--input",
    input.toString()
);
```

`Path` handles separators according to Java's filesystem provider. However, if a command expects a URL, a POSIX path on Windows, or an application-specific path syntax, convert according to that program's CLI contract rather than blindly calling `Path.toString()`.

### 9.3. Do Not Rely on Relative Paths in CI

In CI, the project root, temporary directory, and runner working directory may differ. Use `Path.toAbsolutePath()` when preparing resources, or set `builder.directory()` explicitly. Log the intended directory and executable path, while avoiding printing sensitive data.

Verify read/write/execute permissions of the service account or user running Java. On Unix, file existence does not imply executability; on Windows, file extensions and associations also affect how scripts are executed.

## 10. Standard Input, Output, and Error

### 10.1. Three Process Streams

`Process` provides:

- `getOutputStream()`: Java writes to the **child process's stdin**.
- `getInputStream()`: Java reads from the **child process's stdout**.
- `getErrorStream()`: Java reads from the **child process's stderr**.

The method names can be confusing because they are named from the parent Java process's perspective:

```text
Java parent                     Child process
-----------                     -------------
getOutputStream() --------->    stdin
getInputStream()  <---------    stdout
getErrorStream()  <---------    stderr
```

There is no interactive console automatically. By default, ProcessBuilder creates appropriate pipes unless streams are redirected or inherited.

### 10.2. `inheritIO()` for Interactive Command-Line Tools

```java
Process process = new ProcessBuilder(
    "git",
    "--version"
).inheritIO().start();

int exitCode = process.waitFor();
```

`inheritIO()` lets the child process use the parent Java process's standard input/output/error. This is suitable for CLIs where output does not need to be captured separately or tools that an operator wants to watch directly.

Do not use `inheritIO()` if the application needs to parse output into machine data. When running inside a service/container, inherited streams may go into the container's stdout/stderr logging rather than a user console.

### 10.3. Why Improperly Reading stdout/stderr Causes Deadlock

If the child process writes a large amount of data to stdout or stderr without Java reading it, the pipe buffer can fill up, blocking the child process on writes. Meanwhile Java waits in `waitFor()`, while the child waits for Java to drain the pipe: the application can hang.

Dangerous example:

```java
Process process = new ProcessBuilder("very-verbose-tool").start();

// Can hang if child fills stdout/stderr:
int exitCode = process.waitFor();
```

You must consume the output, redirect it to a file, use `inheritIO()`, or merge streams appropriately. If a tool produces substantial output, do not read all of stdout before reading stderr, as either pipe can still fill up.

### 10.4. Merging stderr into stdout

```java
import java.nio.charset.StandardCharsets;

ProcessBuilder builder = new ProcessBuilder(
    "my-tool",
    "--version"
);

builder.redirectErrorStream(true);

Process process = builder.start();

try (var reader = new java.io.BufferedReader(
        new java.io.InputStreamReader(
            process.getInputStream(),
            StandardCharsets.UTF_8))) {

    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}

int exitCode = process.waitFor();
```

With `redirectErrorStream(true)`, stderr is merged into stdout and Java only needs to read one pipe. The drawback is that it is hard to tell which lines are errors, and programs may write different kinds of content to the two streams.

`StandardCharsets.UTF_8` is only correct if the **child emits UTF-8 output**. Do not assume every Windows program uses UTF-8; some applications use a legacy code page or locale-dependent encoding.

### 10.5. Redirecting Output Directly to Files

```java
import java.io.File;

ProcessBuilder builder = new ProcessBuilder(
    "my-tool",
    "--run"
);

builder.redirectOutput(
    ProcessBuilder.Redirect.to(
        new File("logs/tool.stdout.log")
    )
);

builder.redirectError(
    ProcessBuilder.Redirect.appendTo(
        new File("logs/tool.stderr.log")
    )
);

Process process = builder.start();
int exitCode = process.waitFor();
```

The `logs` directory must exist and the user running Java must have write permissions. When redirecting to a file, do not simultaneously assume `process.getInputStream()` still carries stdout data to read: output has been routed to another destination.

Consider log rotation, disk space, and log security if the tool produces large output.

### 10.6. Writing stdin for the Child Process

If a tool accepts input via stdin, avoid concatenating data into shell commands. You can write using Java:

```java
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;

Process process = new ProcessBuilder(
    "my-tool",
    "--read-stdin"
).start();

try (OutputStreamWriter writer =
        new OutputStreamWriter(
            process.getOutputStream(),
            StandardCharsets.UTF_8)) {

    writer.write("one record\n");
    writer.write("two records\n");
}

int exitCode = process.waitFor();
```

Close the output stream to send EOF to the child when the protocol expects end-of-input. However, this example still needs to handle stdout/stderr if the child writes noticeably to those two streams; in real systems, separate tasks for input/output or appropriate redirects may be needed to avoid bidirectional deadlock.

## 11. Charset and Unicode Across Process Boundaries

### 11.1. Java Strings Are Unicode, but I/O Bytes Depend on Encoding

A Java argument is a `String`, whereas the process environment and the target program's libraries have their own encoding/decoding rules. On Windows, Unicode command lines are supported by the OS, yet older native programs may use ANSI APIs or convert through a code page, losing characters.

On Unix-like OSes, argument bytes and locale/encoding must also be compatible with the target program. A Vietnamese string may pass cleanly from Java to a modern child Java process, yet a legacy native CLI may process it differently.

Do not assume “Java defaults to UTF-8” means all child programs, shells, and terminals use UTF-8. JDK 18 changed the default charset under JEP 400, yet the encoding of the child process or console must still be verified independently.

### 11.2. Avoid Implicit Decoding with the Machine Charset

Unstable example:

```java
new InputStreamReader(process.getInputStream());
```

This constructor uses the parent Java process's default charset, which may not match the child program's output.

If the child has a UTF-8 contract:

```java
new InputStreamReader(
    process.getInputStream(),
    java.nio.charset.StandardCharsets.UTF_8
);
```

For native tools, check whether options like `--encoding UTF-8` or locale configuration are available. If Unicode support is weak, consider passing complex data via a controlled UTF-8 file or an appropriate IPC protocol.

### 11.3. Different Line Endings

Windows typically uses CRLF and Unix-like OSes typically use LF for text files. `BufferedReader.readLine()` handles common newline styles, but when transmitting binary data or protocols requiring CRLF, do not convert line endings arbitrarily.

If a command generates configuration files, specify the required encoding and newline style instead of relying on `System.lineSeparator()` of the build machine.

## 12. Exit Codes, Timeouts, and Process Lifecycles

### 12.1. Successful Process Start Does Not Mean Command Success

`ProcessBuilder.start()` creates the child process, yet the tool can report an error and exit with a non-zero exit code:

```java
Process process = new ProcessBuilder(
    "my-tool",
    "--validate"
).inheritIO().start();

int exitCode = process.waitFor();

if (exitCode != 0) {
    throw new IllegalStateException(
        "Tool failed with exit code " + exitCode
    );
}
```

Some executables use specialized exit codes per contract; do not assume every non-zero code has the same business meaning. Read the tool's documentation and distinguish startup errors (IOException on `start()`) from errors after the process has run.

### 12.2. Setting Timeouts to Avoid Waiting Indefinitely

```java
import java.util.concurrent.TimeUnit;

Process process = new ProcessBuilder(
    "my-tool",
    "--long-task"
).redirectErrorStream(true)
 .inheritIO()
 .start();

boolean finished = process.waitFor(30, TimeUnit.SECONDS);

if (!finished) {
    process.destroy();

    if (!process.waitFor(5, TimeUnit.SECONDS)) {
        process.destroyForcibly();
        process.waitFor();
    }

    throw new IllegalStateException("Process timed out");
}

int exitCode = process.exitValue();
```

This example illustrates a timeout for the direct process. The 30/5-second durations are only sample values; set them based on SLOs and workload characteristics. `destroy()` requests termination via platform mechanisms, while `destroyForcibly()` attempts forced termination.

If blocked reading a stream and the child does not exit, placing a timeout solely around `waitFor` may not suffice. A production solution needs to manage pipe-reading tasks, closing streams, canceling tasks, and cleanup.

### 12.3. Child Processes Can Spawn Descendant Processes

If Java launches a shell or build tool, that process may spawn additional processes. Calling `destroy()` on the direct process does not automatically guarantee all descendants are terminated on every OS.

Starting in Java 9, `ProcessHandle` allows inspecting PIDs, descendants, and related information:

```java
ProcessHandle handle = process.toHandle();

System.out.println("PID: " + handle.pid());

handle.descendants()
    .forEach(child ->
        System.out.println("Child PID: " + child.pid()));
```

Managing a process tree requires synchronization, OS permissions, and race handling; the descendants list can change while being read. For services needing to stop an entire job, consider process groups/job objects, schedulers, or the corresponding container isolation mechanisms.

### 12.4. When the Java Thread Is Interrupted

`waitFor()` can throw `InterruptedException`. Do not swallow the exception and leave the child running indefinitely without an owner. Depending on the contract:

- Terminate the child or transfer ownership to another coordinator.
- Restore the interrupt flag via `Thread.currentThread().interrupt()` if upper layers need to know.
- Clean up pipes and output-reading tasks.
- Do not leave the process alive because code exits early along an exception path.

## 13. ProcessBuilder.startPipeline Without a Shell

Java 9 added `ProcessBuilder.startPipeline`, allowing stdout of one process to be connected to stdin of the next without manually writing `|` syntax in a shell.

Conceptual example on a system with `grep` and `sort`:

```java
import java.util.List;

ProcessBuilder grep = new ProcessBuilder(
    "grep",
    "java",
    "README.txt"
);

ProcessBuilder sort = new ProcessBuilder(
    "sort"
);

List<Process> processes = ProcessBuilder.startPipeline(
    List.of(grep, sort)
);
```

In a pipeline, Java wires the pipe connections between processes. The application must still manage stderr, final stdout, exit codes, and lifecycles **of all** processes, while also choosing OS-appropriate executables.

For example, `grep` and `sort` are not available by default on Windows. If a portable pipeline is needed, perform text processing directly in Java or use a clearly packaged/declared cross-platform program.

`startPipeline` does not resolve shell syntax such as variable expansion or globbing. It creates a pipeline from ProcessBuilders with separated commands and arguments.

## 14. Security When Passing Commands and Arguments

### 14.1. Distinguishing Command Injection from Argument Injection

**Command injection** commonly occurs when concatenating untrusted data into a shell command string:

```java
// Unsafe:
String command = "some-tool " + userInput;

new ProcessBuilder(
    "/bin/sh",
    "-c",
    command
).start();
```

If `userInput` contains `;`, pipes, substitution, or other shell syntax, the shell can interpret it as unintended commands.

Using separate arguments reduces the risk of shell injection:

```java
new ProcessBuilder(
    "/usr/local/bin/some-tool",
    userInput
).start();
```

However, **argument injection** can still occur if the tool interprets user data starting with a hyphen as an option. For example, a filename `--delete-all` might be treated by the CLI parser as an option rather than a file.

If the target program supports `--` to terminate option parsing:

```java
new ProcessBuilder(
    "/usr/local/bin/some-tool",
    "--",
    userProvidedFilename
).start();
```

Confirm that the tool actually supports `--`; not all CLIs share the same contract.

### 14.2. Use an Allowlist for Executables and Operations

Do not let users supply full executable paths or command templates and run them directly in a privileged Java process. If the application needs to support a set of operations, declare an allowlist:

```java
enum Operation {
    REPORT,
    VALIDATE
}

static List<String> commandFor(
        Operation operation,
        String inputPath) {

    return switch (operation) {
        case REPORT ->
            List.of("/opt/tools/report", "--input", inputPath);
        case VALIDATE ->
            List.of("/opt/tools/validate", "--input", inputPath);
    };
}
```

The example illustrates Unix paths; Windows requires the corresponding binaries. `inputPath` must still be validated against permission policies and allowed filesystem areas. Argument lists do not by themselves prevent path traversal or dangerous tool behavior.

### 14.3. Restricting Child Process Privileges

Child processes typically inherit the identity and many OS privileges of the parent Java process. If a Java service runs with elevated privileges, an arbitrary command can access extensive resources.

Therefore:

- Use a least-privilege service account.
- Restrict filesystem/network access in a container or appropriate OS sandbox.
- Do not execute untrusted executables merely because a shell was avoided.
- Set timeouts and CPU/memory limits if supported by the infrastructure.
- Control environment variables and secrets passed to the child.
- Verify executable paths and binary provenance.

`ProcessBuilder` is a process management API, **not** a security sandbox.

## 15. Comparing ProcessBuilder with Runtime.exec

Older Java code often used:

```java
Runtime.getRuntime().exec("my-tool --input report.txt");
```

The `Runtime.exec(String)` overload performs simple tokenization rather than running the command through a default shell. It is not a full Bash or Windows cmd parser, so it can break strings containing spaces and quotes.

Example:

```java
String path = "C:\\Reports\\Monthly report.csv";

// Error-prone if expecting shell-style quoting:
Runtime.getRuntime().exec(
    "my-tool --input \"" + path + "\""
);
```

For new code or migration, prefer ProcessBuilder with a list:

```java
new ProcessBuilder(
    "my-tool",
    "--input",
    path
).start();
```

`Runtime.exec(String[])` also accepts an argument array, but `ProcessBuilder` provides clearer configuration for environment, working directory, redirects, and I/O.

### 15.1. Upgrading the JDK Can Expose Old Bugs

A script may work when inputs contain no spaces or special characters, and then fail upon moving to a new environment with paths such as:

```text
C:\Program Files\Vendor\tool.exe
/home/build agent/workspace/input.csv
/Users/Example User/My Documents/report.txt
```

This is usually a pre-existing flaw in command construction design, not necessarily a JDK regression. Migration is a good time to switch to tested command lists.

## 16. ProcessBuilder Migration Procedure from JDK 8 to Modern JDKs

### Phase 1: Inventory Process Invocation Sites

Search for APIs and patterns:

- `new ProcessBuilder(...)`.
- `Runtime.getRuntime().exec(...)`.
- `ProcessBuilder.command(...)` or dynamic command list mutations.
- `/bin/sh -c`, `bash -c`, `cmd.exe /c`, `powershell -Command`.
- Invoking `.sh`, `.bat`, `.cmd`, `.exe`.
- Concatenating arguments into a single string.
- Calling `getInputStream()`/`getErrorStream()` and `waitFor()`.
- `System.getenv()`, `builder.environment()`, and `builder.directory()`.

Example repository search:

```shell
rg -n "ProcessBuilder|Runtime\\.getRuntime\\(\\)\\.exec" src
rg -n "cmd\\.exe|powershell|pwsh|/bin/sh|bash" src
rg -n "redirectErrorStream|inheritIO|waitFor\\(" src
```

The commands are only initial queries; also inspect CI scripts, plugins, and third-party libraries if they launch processes themselves.

### Phase 2: Categorize by Purpose

| Group | Sign | Handling approach |
|---|---|---|
| Running executable with options | `tool --input file` | Command list, no shell |
| Running scripts | `.sh`, `.cmd`, `.ps1` | Appropriate interpreter and clear contract |
| Needing pipes/redirection | `|`, `>`, `2>` | ProcessBuilder redirection/pipeline or fixed shell |
| Finding command on PATH | Short executable name | Verify environment or use absolute path |
| Processing output | Reading stream/process log | Charset, pipe draining, and exit code |
| Running long tasks | Wait, timeout, kill | Lifecycle, cancellation, and descendants |
| Passing user data | String concatenation or options | Separate arguments, validation, restrict shell |

Different purposes require different solutions; do not replace everything with a single shell wrapper.

### Phase 3: Separate Executable, Arguments, and Environment

Create a clear command structure, for example:

```java
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

static ProcessBuilder createExporter(
        Path exporter,
        Path input,
        Path output) {

    List<String> command = new ArrayList<>();

    command.add(exporter.toAbsolutePath().toString());
    command.add("--input");
    command.add(input.toAbsolutePath().toString());
    command.add("--output");
    command.add(output.toAbsolutePath().toString());

    return new ProcessBuilder(command);
}
```

This structure allows testing the argument list before execution and avoids manual quoting bugs.

If a tool has different paths or options per OS, build two separate adapters and apply the same contract test suite for input/output data.

### Phase 4: Choose an I/O Strategy

Each command needs an explicit policy:

- Send output directly to the terminal/service logs via `inheritIO()`.
- Capture output with a size limit and appropriate charset.
- Redirect output/error to files.
- Use two concurrent reading tasks for stdout and stderr.
- Use `redirectErrorStream(true)` if errors and data do not need separation.
- Close stdin to signal EOF if the child waits for input.

Do not merely call `waitFor()` and ignore stdout/stderr.

### Phase 5: Set Timeouts and Check Exit Codes

Define these cases:

- Start fails: `IOException`.
- Process runs, but exit code is non-zero.
- Timeout.
- Caller is interrupted.
- Child does not return expected output.
- Child spawns descendants.
- Errors when closing or redirecting streams.

For each case, know which processes remain running and who is responsible for cleanup.

### Phase 6: Test on Each Target OS/JDK

Do not infer from a passing test on Windows that a command will work on Linux. The matrix should cover the OSes/architectures/JDKs/vendors committed to by the product:

| Test | Windows | Linux | macOS |
|---|---|---|---|
| Executable path containing spaces | Yes | Yes | Yes |
| Arguments with quotes/backslashes | Yes | Yes | Yes |
| Unicode and empty arguments | Yes | Yes | Yes |
| OS-specific native scripts | `cmd`/PowerShell | `sh`/Bash if available | `sh`/Bash/zsh depending on system |
| CWD and relative paths | Yes | Yes | Yes |
| Env/PATH, case sensitivity | Yes | Yes | Yes |
| Large stdout/stderr | Yes | Yes | Yes |
| Timeout, interruption, and descendants | Yes | Yes | Yes |

A project does not necessarily support every operating system. Include only committed targets in the acceptance gate, and do not use unsupported configurations to draw compatibility conclusions.

## 17. Common Failure Scenarios

### 17.1. `CreateProcess error=2` or “No such file or directory”

**Symptom:** `start()` throws `IOException`; the executable cannot be found.

**Cause:** wrong path, first command element includes options, incorrect PATH, or the service environment is missing the binary.

**Resolution:** print the executable path with sensitive data masked, verify file existence/execute permissions, and use an absolute path. Do not append quotes to the executable path.

### 17.2. Executable Runs but Receives the Wrong Number of Arguments

**Symptom:** the tool reports “unknown option”, “missing value”, or receives a split filename.

**Cause:** joining `--input file` into one argument or manually splitting values on whitespace.

**Resolution:** use `List<String>`, with each option and value as its own element if required by the CLI. Verify using `ArgsPrinter` or a similar mock program.

### 17.3. `|` or `>` Appears in Output Instead of Creating a Pipe

**Cause:** passing shell syntax as ordinary arguments.

**Resolution:** use `redirectOutput`, `redirectInput`, `startPipeline`, or intentionally invoke a shell. Do not assume ProcessBuilder automatically invokes a shell.

### 17.4. Batch Script Fails Only When Paths Contain Spaces

**Cause:** an extra parsing layer from `cmd.exe` and quoting rules that differ from ordinary executables.

**Resolution:** avoid batch scripts if an equivalent executable exists; if batch is required, use a Windows script/adapter tested with paths containing spaces, quotes, and metacharacters. Avoid concatenating untrusted data into `/c` strings.

### 17.5. Garbled Characters in Unicode Output

**Cause:** the child emits data using a code page other than UTF-8, or the parent reads with the wrong charset.

**Resolution:** establish the child's encoding, configure the tool if supported, and read the stream using the matching charset; do not infer the child's encoding from Java source encoding.

### 17.6. Java Hangs While Waiting for a Child Process

**Cause:** stdout or stderr pipe is full; child is waiting for input; process does not exit; missing timeout; or output-reading executor is blocked.

**Resolution:** drain/redirect streams, send EOF when needed, set timeouts, and manage interruption and the process tree.

### 17.7. Tool Runs in Terminal but Fails from a Java Service

**Cause:** differing PATH, environment, user permissions, working directory, or shell profile.

**Resolution:** capture the environment from the actual service runtime, use an absolute executable path, set cwd and env explicitly, and check filesystem/network permissions.

### 17.8. Child Process Finishes but the Service Does Not Shut Down

**Cause:** pipe-reading task has not finished, descendant processes remain, streams were not closed, thread pool waits indefinitely, or shutdown hook is uncoordinated.

**Resolution:** design a clear lifecycle, close resources by owner, await/cancel tasks with timeouts, and monitor descendants and metrics.

## 18. Designing a Stable Helper API for Applications

To prevent each module from building commands differently, you can provide a small abstraction managing command lists and I/O. However, the abstraction should not hide all OS details or implicitly invoke a shell.

Example helper for a non-interactive command with small output:

```java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.Charset;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

record CommandResult(int exitCode, String output) {}

static CommandResult runCommand(
        List<String> command,
        Charset outputCharset,
        Duration timeout)
        throws IOException, InterruptedException {

    ProcessBuilder builder = new ProcessBuilder(command);
    builder.redirectErrorStream(true);

    Process process = builder.start();

    // Only suitable when output is bounded and the process exits
    // on time; production code should read asynchronously so timeout
    // takes effect even if the child does not close the pipe.
    try {
        if (!process.waitFor(
                timeout.toMillis(),
                TimeUnit.MILLISECONDS)) {

            process.destroyForcibly();
            process.waitFor();
            throw new IOException("Process timed out");
        }

        StringBuilder output = new StringBuilder();

        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(
                    process.getInputStream(), outputCharset))) {

            String line;
            while ((line = reader.readLine()) != null) {
                output.append(line).append('\n');
            }
        }

        return new CommandResult(
            process.exitValue(), output.toString()
        );
    } finally {
        if (process.isAlive()) {
            process.destroyForcibly();
        }
    }
}
```

**Limitations of the example:** even with a timeout, waiting for the process before consuming the pipe can still deadlock if stdout/stderr is large. This sample illustrates result structure and timeout management rather than being a **production helper safe for every workload**. For tools with unbounded output, redirect to a file or start concurrent readers before waiting on the process.

In a production implementation, separate into components:

- `CommandSpec`: executable path, arguments, working directory, environment delta.
- `OutputPolicy`: inherit, file, bounded capture, or streaming callback.
- `TimeoutPolicy`: deadline, graceful shutdown, forced stop.
- `CommandResult`: exit code, output metadata, elapsed time.
- `DiagnosticPolicy`: redacted path and argument logs, without recording secrets.

Such a design makes testing easier and avoids duplicating quoting, timeout, and charset logic across modules.

## 19. ProcessBuilder Compatibility Checklist

### Command List

- [ ] Each argument is passed as a separate `String` element.
- [ ] The entire command is not merged into the first element.
- [ ] Quotes are not manually added as data around paths just to handle spaces.
- [ ] Empty arguments, quotes, backslashes, Unicode, and special characters have been tested.
- [ ] User-supplied options have validation or a `--` delimiter if supported by the tool.

### Platform and Environment

- [ ] Executable exists and has run permissions on the target OS.
- [ ] Does not assume a shell, `git`, `bash`, `cmd.exe`, or `pwsh` always exists on every target.
- [ ] Separate adapters exist for `.sh`, `.bat`/`.cmd`, `.ps1` when needed.
- [ ] Working directory and input/output file paths are explicitly specified.
- [ ] Service/container PATH and environment have been verified.
- [ ] No secrets are leaked in command lines or logs.

### I/O and Lifecycle

- [ ] Stdout/stderr are drained, redirected, or inherited deliberately.
- [ ] Output/input charsets match the child program.
- [ ] Stdin is closed or EOF is sent when required by the protocol.
- [ ] Exit code is checked according to the tool's contract.
- [ ] Timeout, interruption handling, and cleanup are implemented.
- [ ] Process descendants are managed if the command spawns additional processes.
- [ ] Streams that were redirected to files are not read.

### Migration and Testing

- [ ] Reviewed `Runtime.exec(String)` and concatenated command strings.
- [ ] Removed shell invocations where no shell is needed.
- [ ] Argument round-trip tests run on every supported OS/JDK.
- [ ] Tested paths with spaces and real CI/service environments.
- [ ] Tested large output, timeouts, start failures, and non-zero exit codes.
- [ ] Deployment documentation specifies executables, permissions, working directory, and encoding.

## Conclusion

`ProcessBuilder` provides an explicit API to launch processes and pass argument lists, yet it is not a portable shell. Do not think “if I can type it in the terminal, putting the whole string into ProcessBuilder will run”. On Unix-like OSes, arguments typically pass through `argv`; on Windows, the JDK must translate that list into a command-line string for `CreateProcess` and the target program may apply its own parser. When explicitly invoking `sh`, `cmd.exe`, or PowerShell, shell rules add yet another processing layer.

For a reliable migration, separate the executable from each argument, use absolute paths and working directories when needed, avoid concatenating data into shell commands, manage environment variables and encoding, properly drain or redirect stdout/stderr, and check exit codes and timeouts. Finally, test with tricky strings such as spaces, empty arguments, Unicode, and special characters on the exact supported OSes and JDKs. That way, “works on this machine but breaks on another” bugs are caught by tests instead of appearing after deployment.
