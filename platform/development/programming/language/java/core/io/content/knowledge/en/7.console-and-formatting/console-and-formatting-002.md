# Process-Level Input, Output, and Error Redirection in Java I/O

## 1. The Three Standard Channels of a Process

When a Java program runs, it normally receives three standard communication channels prepared by the launch environment:

| Channel | Name | Common POSIX File Descriptor | Java API | Meaning |
| --- | --- | --- | --- | --- |
| Standard input | stdin | 0 | **System.in**, type InputStream | Reads input data |
| Standard output | stdout | 1 | **System.out**, type PrintStream | Writes normal results |
| Standard error | stderr | 2 | **System.err**, type PrintStream | Writes errors or diagnostic information |

When launched directly from a terminal, stdin usually receives input from the keyboard; stdout and stderr usually appear together in the terminal. However, **the destinations of the two output streams remain logically independent**. The shell or parent process can connect each stream separately to a file, pipe, terminal, or log collection service.

**Process-level I/O redirection (process redirection)** means changing a process's stdin source or stdout/stderr destination. If the environment redirects stdout into a file, calling **System.out.println(...)** in Java works as usual; the content goes to the file instead of the screen.

~~~text
                 +-------------------------+
input.txt ------>| stdin   System.in       |
                 |                         |
                 |     Java process        |
                 |                         |
output.txt <-----| stdout  System.out      |
error.txt  <-----| stderr  System.err      |
                 +-------------------------+
~~~

**Why separate stdout and stderr?** When a program generates output for another tool to process (such as JSON, CSV, file names, or result codes), error lines printed into stdout can break parsing on the reading side. Separating stderr lets you extract clean results from stdout while still tracking diagnostic messages.

## 2. Shell Redirection

On **Linux and macOS Bash/sh** and **Windows cmd.exe**, familiar operators have these meanings:

| Operator | Action |
| --- | --- |
| **< input.txt** | Connects the program's stdin from a file |
| **> output.txt** or **1> output.txt** | Redirects stdout to a file; usually creates a new file or overwrites an existing one |
| **>> output.txt** | Appends stdout to a file |
| **2> error.txt** | Redirects stderr to a file; usually creates a new file or overwrites an existing one |
| **2>> error.txt** | Appends stderr |
| **> both.txt 2>&1** | Redirects stdout to a file, then points stderr to stdout's current destination |
| **2> error.txt > output.txt** | Redirects the two streams to two separate files |

Regarding the numbers **0, 1, 2**, these are the file descriptor numbers used by the shell: 0 is stdin, 1 is stdout, and 2 is stderr. The operator **2>&1** means duplicating stdout's current destination for stderr; it is not an operation that concatenates two String contents in Java.

### Redirection Order Matters Greatly

~~~bash
java Example > combined.log 2>&1
~~~

The shell evaluates from left to right: first stdout is directed to combined.log, then stderr is attached to that same destination. Both results and errors can go into one file.

~~~bash
java Example 2>&1 > only-stdout.log
~~~

In the second command, stderr is attached to the **original stdout destination** before stdout is redirected to only-stdout.log. If the original destination was the terminal, errors may still appear in the terminal. The two commands are **not equivalent**.

When redirecting both into a single file, do not rely on the exact interleaving order of individual stdout and stderr lines in all situations: the two streams have independent buffers and write schedules, and log collection tools can also affect the observed order.

## 3. A Java 17+ Program Using All Three Streams

Create the file **StandardStreamsDemo.java**, saved with UTF-8 source encoding:

~~~java
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;

public class StandardStreamsDemo {
    public static void main(String[] args) throws IOException {
        BufferedReader input = new BufferedReader(
                new InputStreamReader(
                        System.in, StandardCharsets.UTF_8));

        String line = input.readLine();

        if (line == null) {
            System.out.println("OUT:<EOF>");
        } else {
            System.out.println("OUT:" + line);
        }
        System.err.println("ERR:diagnostic");
    }
}
~~~

Explanation:

- **System.in** supplies input bytes. InputStreamReader decodes bytes into characters as UTF-8; BufferedReader provides **readLine()**.
- If stdin has ended without any line, **readLine() returns null**, and the program prints OUT:<EOF>.
- Results or status go to stdout via System.out; diagnostic messages go to stderr via System.err.
- The program reads exactly **one line** and exits, making it suitable for testing file redirection. The example intentionally avoids closing System.in so it does not close the standard channel when other parts of a program still need it.

Compile with JDK 17 or later:

~~~bash
javac -encoding UTF-8 StandardStreamsDemo.java
~~~

On **Bash/sh**:

~~~bash
printf 'xin chao\n' > input.txt
java StandardStreamsDemo < input.txt > output.txt 2> error.txt
cat output.txt
cat error.txt
~~~

On **cmd.exe**:

~~~bat
echo xin chao>input.txt
java StandardStreamsDemo < input.txt > output.txt 2> error.txt
type output.txt
type error.txt
~~~

Both approaches create an input consisting of one line `xin chao` and separate the two streams. Contents of **output.txt**:

~~~text
OUT:xin chao
~~~

Contents of **error.txt**:

~~~text
ERR:diagnostic
~~~

If you omit **2> error.txt** while keeping **> output.txt**, the ERR:diagnostic message will continue going to the original stderr, usually the terminal. If you use **> combined.txt 2>&1**, both lines are directed into combined.txt.

### PowerShell Has Its Own Syntax and Rules

Do not assume Bash/cmd examples like **< input.txt** apply verbatim to PowerShell, especially Windows PowerShell 5.1. In PowerShell, you can use Start-Process with three separate redirection parameters:

~~~powershell
$p = Start-Process -FilePath java -ArgumentList 'StandardStreamsDemo' -RedirectStandardInput 'input.txt' -RedirectStandardOutput 'output.txt' -RedirectStandardError 'error.txt' -NoNewWindow -Wait -PassThru
$p.ExitCode
~~~

The example assumes input.txt already exists, the class is compiled in the current working directory, and Java is on PATH. **-Wait** waits for the process to complete, and **-PassThru** returns the process object so you can inspect ExitCode.

PowerShell also has its own stream system and redirection encoding behavior, which varies by version. If you need binary data preserved byte-for-byte, prefer Java byte APIs rather than assuming every shell will preserve raw bytes across text-processing pipelines.

## 4. Exit Codes Are Independent of Stdout and Stderr

**Error messages** and **process exit codes** are two distinct concepts:

- A program can write warnings to stderr and still exit with code 0.
- A program can write nothing to stderr yet return a non-zero exit code.
- A program can write partial data to stdout and then fail.
- Redirecting stderr to a file does not turn a failed operation into a successful one.

In Bash, the **$?** variable immediately after a command holds the exit status of the most recent command; cmd.exe typically uses **%ERRORLEVEL%**; PowerShell supports **$LASTEXITCODE** for native processes. In Java, **Process.waitFor()** returns the child process's exit code after it terminates. By common convention, 0 indicates success, though exact meanings follow each program's contract.

To define the exit code for a Java application yourself, you can use **System.exit(code)** where appropriate. Do not use that method arbitrarily to terminate from a library because it shuts down the entire current JVM.

## 5. ProcessBuilder: Configuring Standard Channels of a Child Process

When Java needs to run an external program, use **ProcessBuilder**. Unlike a shell, ProcessBuilder accepts a **list of command and arguments**, and provides APIs to wire stdin/stdout/stderr before calling **start()**.

By default, the child process's three channels use **PIPE**:

~~~text
               Java parent process
                       |
    write to child stdin: process.getOutputStream()
                       |
                       v
                  Java child
                       |
     +-----------------+-----------------+
     |                                   |
 child stdout                        child stderr
     |                                   |
     v                                   v
process.getInputStream()      process.getErrorStream()
~~~

Method names follow the **parent's perspective**: getOutputStream() is where the parent **writes to the child's stdin**, while getInputStream() is where the parent **reads the child's stdout**. This is a common source of confusion when starting out with the Process API.

### Runnable Program: Redirect from Files and Capture Two Separate Outputs

Create file **ProcessRedirectionDemo.java**:

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

public class ProcessRedirectionDemo {
    public static void main(String[] args) throws Exception {
        if (args.length > 0 && "child".equals(args[0])) {
            BufferedReader input = new BufferedReader(
                    new InputStreamReader(
                            System.in, StandardCharsets.UTF_8));

            String first = input.readLine();
            String second = input.readLine();

            System.out.println("received=" + first + "|" + second);
            System.err.println("warning=demo");
            System.exit(7);
            return;
        }

        Path dir = Files.createTempDirectory("redirect-java-");
        Path source = dir.resolve("source.txt");
        Path normal = dir.resolve("normal.txt");
        Path errors = dir.resolve("errors.txt");

        try {
            Files.writeString(source, "alpha\nbeta\n",
                    StandardCharsets.UTF_8);

            String os = System.getProperty("os.name")
                    .toLowerCase(Locale.ROOT);
            String javaName = os.contains("win") ? "java.exe" : "java";
            Path executable = Path.of(
                    System.getProperty("java.home"),
                    "bin", javaName);

            ProcessBuilder builder = new ProcessBuilder(
                    executable.toString(),
                    "-cp",
                    System.getProperty("java.class.path"),
                    ProcessRedirectionDemo.class.getName(),
                    "child");

            builder.redirectInput(source.toFile());
            builder.redirectOutput(normal.toFile());
            builder.redirectError(errors.toFile());

            Process child = builder.start();
            int exit = child.waitFor();

            String stdout = Files.readString(
                    normal, StandardCharsets.UTF_8).strip();
            String stderr = Files.readString(
                    errors, StandardCharsets.UTF_8).strip();

            System.out.println("exit=" + exit);
            System.out.println("stdout=" + stdout);
            System.out.println("stderr=" + stderr);
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(normal);
            Files.deleteIfExists(errors);
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ProcessRedirectionDemo.java
java ProcessRedirectionDemo
~~~

Stdout from **parent**:

~~~text
exit=7
stdout=received=alpha|beta
stderr=warning=demo
~~~

What happened?

1. The parent creates a temporary file containing alpha and beta, one value per line.
2. The parent uses the path to the running JDK's Java executable and launches **a child JVM**, running the same class with the `child` argument.
3. **redirectInput(source)** feeds the file contents as the child's stdin.
4. **redirectOutput(normal)** and **redirectError(errors)** split stdout and stderr into two separate files.
5. The child reads two lines, prints received=alpha|beta to stdout, prints warning=demo to stderr, and explicitly exits with code 7.
6. The parent calls **waitFor()** before reading the result files, ensuring the child has finished. Only then does the parent print the file contents.
7. The parent deletes the temporary files in finally.

**System.exit(7)** in the child branch terminates only the **child JVM**, not the parent JVM. Exit code 7 was chosen to demonstrate that the parent can receive a non-zero exit code.

The example assumes standard classpath execution as shown in the commands. For applications running on a module path, fat JAR, or custom classloader, the child JVM invocation must be adjusted to match the packaging. Strings in the example output use only ASCII so no console encoding difference arises; with Unicode text, encoding must be agreed upon on both sides.

## 6. Redirection Modes Provided by Java

| ProcessBuilder Mechanism | Meaning | When to Use |
| --- | --- | --- |
| **Redirect.PIPE** | Connected via a pipe owned by the Java parent; default | Parent processes output or supplies input at runtime |
| **Redirect.INHERIT** | Child uses the parent's existing standard channels | Interactive child program or sharing the parent's logs |
| **Redirect.from(file)** | Child reads stdin from a file | Pre-existing finite input data |
| **Redirect.to(file)** | Child writes stdout/stderr to a file, replacing old content | Creating a new report/log |
| **Redirect.appendTo(file)** | Appends stdout/stderr to a file | Preserving previous logs |
| **Redirect.DISCARD** | Discards stdout/stderr | Output is unnecessary |

Some illustrative configurations, placed **before** builder.start():

~~~java
// Code snippet; builder is a ProcessBuilder, logPath is a Path.
builder.inheritIO(); // Inherit stdin/stdout/stderr from parent.
~~~

Or:

~~~java
builder.redirectOutput(
        ProcessBuilder.Redirect.appendTo(logPath.toFile()));
builder.redirectError(ProcessBuilder.Redirect.INHERIT);
~~~

The two snippets illustrate **alternative configuration options**, not calls to chain sequentially if you want to keep all three redirects from inheritIO.

**Note on the Process API:** when a child's stdout has already been redirected to a file or INHERIT, the corresponding **process.getInputStream()** is typically a *null input stream* with no stdout content for the parent to read. Similarly, when stderr is redirected, getErrorStream() no longer holds a separate stderr data stream; when stdin comes from a file/INHERIT, getOutputStream() is a *null output stream*. Do not simultaneously expect to redirect directly to a file and read all content via the default PIPE.

**inheritIO()** inherits the standard channels of the **parent process**, and the parent itself may already have been redirected by the shell beforehand. Inherit mode does not necessarily mean the child connects to a physical screen.

## 7. Merging Stdout and Stderr in Java

If a command only needs combined logging, you can enable **redirectErrorStream(true)**:

~~~java
// Code snippet: builder has already been configured with the appropriate command.
builder.redirectErrorStream(true);
Process process = builder.start();

try (var input = process.getInputStream()) {
    input.transferTo(System.out);
}
int exitCode = process.waitFor();
~~~

At this point, the child's stderr is merged into stdout, and the parent reads the combined data from **getInputStream()**. Separate redirectError(...) configurations are ignored when redirectErrorStream(true) is set. If stdout remains a PIPE, input.transferTo(System.out) consumes the pipe while the child runs; once the stream finishes, waitFor() collects the exit code.

If you want to save both together into a file:

~~~java
builder.redirectErrorStream(true);
builder.redirectOutput(
        ProcessBuilder.Redirect.appendTo(logPath.toFile()));
~~~

**Drawback of merging:** error messages can interleave inside JSON/CSV expected to be solely on stdout, breaking parsing. Choose merging when you truly want a unified log; keep stderr separate when stdout carries structured data.

The relative order of messages after merging does not necessarily reproduce exact programmatic order due to buffering, flushing, and execution scheduling.

## 8. Deadlock Risk When PIPEs Are Not Drained

A common bug occurs when the parent calls:

~~~java
// UNSAFE if the child's stdout/stderr remain PIPEs
// and the child writes enough data.
Process child = builder.start();
int code = child.waitFor();
// Only afterward does it start reading stdout and stderr.
~~~

**Why can it hang?** Pipes have a finite buffer. If the child writes too much to stdout or stderr, the pipe fills up; the child must wait for the parent to read. Meanwhile, the parent is blocked in **waitFor()**, waiting for the child to exit. Both sides wait on each other:

~~~text
child write() -> pipe full -> waits for parent to read
parent waitFor() -> waits for child to finish
=> deadlock
~~~

Options to resolve this:

1. Redirect the child's stdout and stderr **directly to files**, as in ProcessRedirectionDemo.
2. Use **inheritIO()** if an environment is already consuming output and sharing the parent's standard channels is acceptable.
3. If a single combined stream is desired, set **redirectErrorStream(true)** and read the combined stream while the child runs.
4. If results and errors must remain separate, **read stdout and stderr concurrently**, for instance each stream in its own task or thread; then wait for the child to finish.

Another blocking scenario involves stdin: when the child's stdin defaults to PIPE, the child program may wait for data or EOF. Once the parent finishes writing to **process.getOutputStream()**, it must **close the write end** to signal end of input when the protocol requires EOF. Otherwise, the child may wait indefinitely.

**waitFor() does not set an automatic timeout.** If a child risks hanging, use the waitFor(timeout, unit) overload, handle the timeout case, and decide whether to terminate the process per application requirements. A timeout also does not replace managing active reading streams.

## 9. Encoding and Data Integrity

Redirection only changes **data wiring**; it does not automatically choose a charset or understand file formats. Java Strings must be **encoded** into bytes when written to a channel; bytes from stdin must be **decoded** if the program processes them as characters.

For example, **InputStreamReader(System.in, StandardCharsets.UTF_8)** means the application expects stdin to carry UTF-8 text. If the actual file is Windows-1252 or UTF-16LE and the program decodes it as UTF-8, text may become garbled or characters replaced. Conversely, stdout/stderr PrintStreams have their own runtime-configured encoding; if the receiver expects Unicode text, agree on the encoding or write using an OutputStreamWriter with an explicit charset.

If stdout contains **images, ZIP archives, or binary data**, do not read it with a Reader and write it as Strings. Transfer raw bytes using InputStream/OutputStream; for instance, input.transferTo(output) copies bytes without decoding them to characters. For text, use BufferedReader/BufferedWriter with the proper charset.

Mind **buffering**: when a program writes to a pipe or file, data can sit in a buffer before reaching the underlying channel. Appropriate flushing may be required in interactive protocols so the receiver sees data promptly. However, flushing does not guarantee the file is durably synced to disk or that the receiver has finished processing it.

**Do not treat stderr as stdout data** just because both appear together on screen. If another application needs to parse stdout, choose structured data on stdout and diagnostics on stderr from the very beginning of the design.

## 10. System.setIn/out/err Is Not OS Redirection of Child Processes

Java can replace the standard channel objects within the **current JVM**:

~~~java
System.setIn(otherInputStream);
System.setOut(otherPrintStream);
System.setErr(otherPrintStream);
~~~

This is an **illustrative code snippet**: otherInputStream is an InputStream, and otherPrintStream is a PrintStream provided by the program. It swaps the objects accessed by Java code via System.in/out/err. Because the effect is JVM-wide, multiple threads or libraries sharing System.out may be affected.

However, **System.setOut is not equivalent to OS-level stdout redirection** and does not automatically configure stdout for any launched child processes. Native code or libraries holding references to the old stream may not follow the new stream. To control a **child process's** standard channels, prefer ProcessBuilder; to redirect when a user runs a command, use the shell.

| Approach | Scope | Purpose |
| --- | --- | --- |
| Bash/cmd redirection | Process launched by the shell | Running a program with files or pipes |
| ProcessBuilder redirects | Child process created by Java | Capturing output, supplying input, saving logs, inheriting terminal |
| System.setIn/out/err | Standard channel objects of the current JVM | Swapping I/O referenced by current Java code |
| System.console() | API for interactive console if present | Prompting/reading console, not a replacement for redirection |

**System.console() can return null** when running in an IDE, CI, pipeline, or whenever the environment has no suitable console. Do not use a null value alone to conclude specifically which file stdout has been redirected to.

## 11. Real-World Scenarios

**Outputting results while keeping errors separate:** A JSON-generating tool should print JSON to stdout and parse/argument errors to stderr. When redirected, the caller receives a clean JSON file while still having an error file to investigate.

**Invoking a compiler from Java:** The parent uses ProcessBuilder with a command/argument list; redirects stdout and stderr to files or reads them concurrently; and checks the exit code to tell whether compilation succeeded. Having log output does not mean the exit code is 0.

**Long-running logging:** Redirect.appendTo(logFile) can be used when previous logs should be kept, though file growth and log rotation must be considered; redirection does not manage disk space on its own.

**Commands needing input:** If stdin comes from a file, use redirectInput(file). If the parent needs to send dynamic data, leave stdin as PIPE, write to process.getOutputStream(), and close the write end at the right time. If the child needs to interact with the terminal, consider inheritIO().

**Multi-process pipelines:** Shells can connect process A's stdout to process B's stdin. In Java, ProcessBuilder.startPipeline(...) exists for certain pipeline setups; you still must manage stderr errors, each process's exit code, and the lifecycle of the entire pipeline. Do not assume the last process's exit code reflects all errors in earlier stages unless the protocol defines that.

## 12. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using >file and assuming stderr also goes to the file | Errors still go to the old stderr | Add 2>otherfile or 2>&1 |
| Reversing the order of >file and 2>&1 | stderr destination is not as expected | Evaluate redirects from left to right |
| Calling waitFor before draining large PIPEs | Child may block, parent waits forever | Drain concurrently or redirect to file |
| Not closing stdin PIPE when finished | Child may keep waiting for EOF | Close getOutputStream() after writing |
| Treating stderr output as a failed exit code | Misjudging program status | Read both exit code and program contract |
| Merging stderr into JSON stdout | Output may become unparseable | Keep the two streams separate |
| Passing > into ProcessBuilder as an argument | Child receives literal string >, no redirection | Use redirectOutput |
| Replacing System.out and assuming child changes too | Child has its own OS standard channels | Configure ProcessBuilder |
| Assuming stdout is valid Unicode everywhere | Encoding may differ | Agree on charset at both ends |
| Using Reader/Writer for image files over PIPE | May alter bytes, corrupting files | Use byte streams |
| Reading stdout via getInputStream after redirectOutput(file) | That stream has no data left to read | Read the redirected file or keep PIPE |
| Forgetting to close streams or clean up on error | Resource/temp-file leaks | try-with-resources, finally |

## 13. Self-Check Exercises

**Question 1.** If you run java App >out.txt 2>err.txt, where do System.out and System.err go?  
**Answer:** System.out goes into out.txt; System.err goes into err.txt. System.in keeps its previous source unless redirected separately.

**Question 2.** How does java App >both.txt 2>&1 differ from java App 2>&1 >both.txt?  
**Answer:** The first command attaches stderr to stdout's destination after stdout was redirected to the file; the second duplicates stdout's original destination for stderr before redirecting stdout, so errors may stay on the terminal.

**Question 3.** Why does the Java parent's Process.getOutputStream() write to the child's stdin?  
**Answer:** Method names are chosen from the parent's perspective: it is an output stream from the parent **to** the child's input.

**Question 4.** Does Process.waitFor() guarantee no hang when the child prints lots of errors?  
**Answer:** No. If the stderr PIPE fills up and the parent does not read it, the child can block. Drain stderr concurrently or redirect it to a file/merge it.

**Question 5.** If the parent wants to parse JSON from the child's stdout, should redirectErrorStream(true) be enabled?  
**Answer:** Usually no. It mixes stderr with stdout, which can break JSON validity.

**Question 6.** Does a program writing ERR:warning to stderr with exit code 0 necessarily indicate failure?  
**Answer:** No. Exit codes and stderr content are defined separately in the tool's contract.

**Question 7.** Does System.setOut(newStream) automatically change stdout for all other processes?  
**Answer:** No. It changes the current JVM's System.out reference; ProcessBuilder or the shell configures a child process's stdio.

**Question 8.** Does binary data redirected via a file or PIPE automatically turn into text?  
**Answer:** No. Redirection simply connects bytes between channels, while byte meaning depends on format and encoding; preserve bytes intact if the data is binary.

## 14. Reference Java APIs

- [Java SE 17 — System](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): System.in, System.out, System.err, and setIn/setOut/setErr.
- [Java SE 17 — ProcessBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.html): redirectInput, redirectOutput, redirectError, redirectErrorStream, inheritIO.
- [Java SE 17 — ProcessBuilder.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ProcessBuilder.Redirect.html): PIPE, INHERIT, DISCARD, from, to, appendTo.
- [Java SE 17 — Process](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Process.html): getInputStream, getOutputStream, getErrorStream, waitFor.

**Key takeaway:** Stdin, stdout, and stderr are three distinct standard channels of a process. The shell or ProcessBuilder connects them to a terminal, file, or PIPE; Java code continues operating through System.in/out/err. To work reliably, you must also manage charsets, PIPE consumption, input EOF, exit codes, and the distinction between diagnostic logs and output data.
