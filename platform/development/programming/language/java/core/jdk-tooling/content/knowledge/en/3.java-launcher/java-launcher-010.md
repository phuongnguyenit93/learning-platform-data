# Java launcher exit codes

An exit code (also called an exit status or process exit status) is the status code that a process returns to the operating system when it terminates. When running an application with the **java** command, this code indicates whether the Java process finished successfully or reported an error according to the application's convention. Shells, deployment scripts, build tools, and CI systems can read the status code to decide the next step.

The Java launcher starts the JVM and the application. When the process terminates, the JVM's exit status is passed to the operating system. Therefore, understanding exit codes requires knowing how a Java application terminates and how external programs read that status.

## 1. Exit code conventions

The common convention is:

- **0**: the process terminated successfully.
- **Non-zero**: the process reported an error or a special status defined by the application.

The operating system does not enforce a universal meaning table for all non-zero codes. Each application defines which codes represent input errors, configuration errors, connection errors, or business logic errors, and documents those conventions clearly.

For example, a program might define:

| Exit code | Application-defined meaning |
|---:|---|
| 0 | Success |
| 1 | Unclassified error |
| 2 | Missing or invalid command-line arguments |
| 3 | Unable to read configuration file |

This is only an example. Another application may assign different meanings to code 2 or 3. When integrating an external program, always read that program's own documentation.

An exit code is different from the output printed to the screen. A program can print an error message and still return 0; conversely, a program can print nothing and terminate with a non-zero code. Therefore, scripts should check the exit code instead of just searching for the word “error” in the output.

## 2. Where does the Java launcher get the exit code from?

With the traditional way of running Java, the **java** launcher starts the JVM, loads the main class, and invokes the entry point method, which typically has the form:

~~~java
public static void main(String[] args)
~~~

The **main** method has a **void** return type. The return value of the main method is not used as the exit code. The **return;** statement only exits the method; you cannot write **return 5;** to set the status code.

When the application finishes normally and the JVM completes shutdown, the default exit code is **0**. An application can explicitly set the status code using **System.exit(int status)**. The launcher can also return a non-zero code when it fails to launch the application, such as when the main class, JAR, or module cannot be found, or when an invalid launcher option is provided.

There are two sources of errors to distinguish:

1. **Launch errors:** the launcher or JVM cannot start the application. Examples include an incorrect class name, a missing JAR, a module not found, or invalid command-line options.
2. **Application errors:** the JVM successfully launches the application, but program logic detects an error and terminates with a non-zero code.

In both cases, the caller usually only needs to know whether the process succeeded. When diagnostics are needed, check both the status code and the messages on standard error.

## 3. Normal termination

If the entry point method finishes without requesting termination with an error code, the Java process typically exits with code **0** after all non-daemon threads have finished.

For example, create the file **HelloExit.java**:

~~~java
public class HelloExit {
    public static void main(String[] args) {
        System.out.println("Application completed.");
    }
}
~~~

Compile and run:

~~~bash
javac HelloExit.java
java HelloExit
~~~

Output:

~~~text
Application completed.
~~~

On Linux/macOS, read the exit code immediately after the command:

~~~bash
java HelloExit
status=$?
echo "Exit code: $status"
~~~

Result:

~~~text
Application completed.
Exit code: 0
~~~

On Windows PowerShell:

~~~powershell
java HelloExit
$LASTEXITCODE
~~~

The result is **0**.

The JVM does not necessarily terminate immediately when the main method returns. If the application has created non-daemon threads that are still running, the process stays alive until those threads finish or the JVM is requested to shut down. Thus, “main has returned” and “the process has exited” can be two different points in time.

## 4. Explicitly setting the status code with System.exit

**System.exit(int status)** requests the JVM to begin the shutdown sequence and terminate the process with the given status code.

- **System.exit(0)** typically indicates success.
- **System.exit(n)** with a non-zero n typically indicates an error or a special outcome.
- This call initiates JVM shutdown and does not return control in the normal way.

For example, create the file **ExitCodeDemo.java**:

~~~java
public class ExitCodeDemo {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java ExitCodeDemo <name>");
            System.exit(2);
        }

        System.out.println("Hello, " + args[0]);
    }
}
~~~

Compile:

~~~bash
javac ExitCodeDemo.java
~~~

Run with a valid argument:

~~~bash
java ExitCodeDemo Ada
~~~

Output:

~~~text
Hello, Ada
~~~

The exit code is **0** because the program terminated normally.

Run with a missing argument:

~~~bash
java ExitCodeDemo
~~~

Output on standard error:

~~~text
Usage: java ExitCodeDemo <name>
~~~

The exit code is **2**, following the example's “invalid usage” convention.

In real-world programs, you should separate business logic from the decision to terminate the process:

~~~java
public class BatchApplication {
    public static void main(String[] args) {
        int status = runBatch(args);

        if (status != 0) {
            System.exit(status);
        }
    }

    private static int runBatch(String[] args) {
        if (args.length == 0) {
            System.err.println("Missing input file.");
            return 2;
        }

        // Perform the work and return the appropriate status code.
        return 0;
    }
}
~~~

This structure allows the business logic method to be tested independently. The application's entry point is responsible for translating the result into the process exit code.

You should not arbitrarily call **System.exit** inside shared libraries or utility classes. A library might be running inside an IDE, an application server, a test runner, or another Java process. If a library calls System.exit on its own, it can shut down the entire host JVM. Libraries should throw exceptions or return results; only the top-level application should decide the exit code.

## 5. Exit codes when an exception occurs

An uncaught exception in the main thread usually causes the JVM to print a stack trace to standard error and the Java launcher process to exit with a **non-zero** code (typically **1**).

Example:

~~~java
public class UncaughtExceptionDemo {
    public static void main(String[] args) {
        throw new IllegalStateException("Unexpected state");
    }
}
~~~

Compile and run:

~~~bash
javac UncaughtExceptionDemo.java
java UncaughtExceptionDemo
~~~

Partial output:

~~~text
Exception in thread "main" java.lang.IllegalStateException: Unexpected state
    at UncaughtExceptionDemo.main(UncaughtExceptionDemo.java:3)
~~~

The process terminates with a non-zero code. For errors where the launcher cannot load a class or start the application, the launcher also typically writes an error message to standard error and returns a non-zero code. You should not rely on a specific error value for every kind of launch failure across all versions and platforms; rely on the application's own conventions when the application itself sets the code.

Not every exception in any thread produces a non-zero exit code. If a worker thread throws an uncaught exception, the default handler typically prints a stack trace and terminates that thread; this by itself does not necessarily terminate the entire JVM with an error code. If the main thread and the remaining non-daemon threads finish normally, the process can still exit with code **0**.

If an error in a worker thread must cause the entire batch job to fail, the program needs to propagate the error back to the coordinating thread, record the failure state, and set an explicit exit code. You should not rely on a stack trace appearing in logs for a CI system to automatically detect a failure.

Example of converting an exception into a failure status at the application boundary:

~~~java
public class SafeBatch {
    public static void main(String[] args) {
        try {
            run(args);
        } catch (Exception e) {
            System.err.println("Batch failed: " + e.getMessage());
            System.exit(1);
        }
    }

    private static void run(String[] args) {
        if (args.length == 0) {
            throw new IllegalArgumentException("Input is required");
        }
        System.out.println("Batch completed.");
    }
}
~~~

For larger applications, categorize exceptions and map them to status codes according to a documented contract, rather than lumping all errors into a single code without a convention.

## 6. Shutdown hooks and Runtime.halt

When **System.exit(status)** is called, the JVM begins the shutdown sequence. Registered shutdown hooks run in separate threads. They are commonly used to close resources, flush data, or perform final cleanup tasks.

Example:

~~~java
public class ShutdownHookDemo {
    public static void main(String[] args) {
        Runtime.getRuntime().addShutdownHook(new Thread(() ->
            System.out.println("Shutdown hook executed.")
        ));

        System.exit(4);
    }
}
~~~

When run, the program prints:

~~~text
Shutdown hook executed.
~~~

The process exit code is **4**.

The JVM does not guarantee execution order among multiple shutdown hooks. If a hook hangs, the shutdown process can be delayed. Therefore, hooks should perform brief, bounded cleanup work and avoid depending on the order of other hooks.

**System.exit** does not guarantee that **finally** blocks on the calling thread's stack will execute as they would during a normal method return. Shutdown hooks are the cleanup mechanism during shutdown; close resources using try-with-resources or finally before requesting shutdown if you need guaranteed ordering.

**Runtime.getRuntime().halt(status)** terminates the JVM immediately, bypassing shutdown hooks and the normal shutdown sequence. Finally blocks are not guaranteed to run either. This is a special operation for emergency JVM termination; normal applications should use System.exit or let the program terminate naturally.

## 7. Reading exit codes in shells

The Java launcher runs as a child process of a terminal or script. Each operating system has its own way of retrieving the exit code.

### Linux and macOS

The special variable **$?** holds the exit status of the most recent command. It must be read immediately after the command being checked, because the next command will overwrite this value.

~~~bash
java ExitCodeDemo Ada
status=$?

if [ "$status" -eq 0 ]; then
    echo "Java application succeeded"
else
    echo "Java application failed with code $status"
fi
~~~

You can save the output for investigation:

~~~bash
java ExitCodeDemo Ada >app.log 2>&1
status=$?
cat app.log
echo "Exit code: $status"
~~~

When using pipes, be careful: by default, the exit status of a pipeline in POSIX shells is usually the status of the last command. For example:

~~~bash
java ExitCodeDemo Ada 2>&1 | tee app.log
~~~

If Java fails but **tee** writes the log successfully, the pipeline's return code can be 0. In Bash, enable **pipefail** so the pipeline returns the appropriate error status when any command in the pipeline fails:

~~~bash
set -o pipefail
java ExitCodeDemo Ada 2>&1 | tee app.log
status=$?
~~~

### Windows PowerShell

For native programs such as **java.exe**, PowerShell provides the **$LASTEXITCODE** variable to read the integer exit code of the process that just ran:

~~~powershell
java ExitCodeDemo Ada
$status = $LASTEXITCODE

if ($status -eq 0) {
    Write-Output "Java application succeeded"
} else {
    Write-Error "Java application failed with code $status"
}
~~~

**$?** is the Boolean success/failure status of the most recent PowerShell command, not the integer exit code of a native process. When you need the numeric code from Java, use **$LASTEXITCODE**.

In Command Prompt (**cmd.exe**), use the **%ERRORLEVEL%** variable:

~~~bat
java ExitCodeDemo Ada
echo Exit code: %ERRORLEVEL%
~~~

Save the status code immediately after the Java command if the script runs additional commands, because subsequent commands can change the status reported by the shell.

## 8. Exit codes in scripts, builds, and CI

An exit code is a contract between a Java program and an orchestration tool. A script can use it to halt a pipeline, mark a job as failed, or choose a recovery step.

Bash example:

~~~bash
#!/usr/bin/env bash
set -e

javac ExitCodeDemo.java
java ExitCodeDemo Ada
echo "Continue only if Java succeeded"
~~~

With **set -e**, Bash typically stops the script when a simple command returns a non-zero code, aside from exception contexts defined by shell rules. If you need to handle individual error codes, use an if statement or check $? explicitly instead of relying solely on set -e.

In CI, a Java command returning non-zero usually causes the step or job to fail. This helps catch failed unit or integration tests, incomplete batch imports/exports, code generator failures, applications that fail to start in smoke tests, or deployment scripts that fail to complete a required step.

A Java program must return reliable exit codes. If it catches an exception, only prints a stack trace, and still exits normally, the pipeline may mark the job as successful even though the work failed. Similarly, a script that does not check exit codes or loses the error status across a pipe can also mask failures.

In Maven or Gradle, distinguish the exit code of the build command from the exit code of an application run as part of a task. A build tool can report a build failure when a test task fails, even if the JVM process running the build functioned normally until it finished. Check the logs and test reports to identify which component failed.

## 9. Getting the exit code of a child Java process with ProcessBuilder

A Java application can launch another Java program or an operating system process using **ProcessBuilder**. The **waitFor()** method waits for the child process to finish and returns its exit code.

Example:

~~~java
import java.io.IOException;

public class ProcessExitCodeDemo {
    public static void main(String[] args) throws IOException, InterruptedException {
        Process process = new ProcessBuilder("java", "-version")
                .inheritIO()
                .start();

        int childExitCode = process.waitFor();
        System.out.println("Child exit code: " + childExitCode);
    }
}
~~~

In this example, **inheritIO()** connects the child process's standard input, standard output, and standard error to the corresponding streams of the parent process. **waitFor()** returns when the child process terminates. If the child process fails to start, **start()** may throw IOException; if the thread is interrupted while waiting, waitFor() throws InterruptedException.

Passing the command as separate string elements, as shown in the example, avoids manually assembling a long command line according to shell quoting rules. When you need to run a specific JDK, pass the full path to the desired Java executable instead of just using the name **java**, because the bare name is resolved through the parent process's PATH.

Do not call **Process.exitValue()** before the process has finished; this method throws IllegalThreadStateException if the process is still running. You can call waitFor() to wait, or isAlive() to check before retrieving the exit value.

## 10. Designing and testing exit codes

A command-line program should have a clear, stable, and easy-to-use exit code contract:

1. Use **0** for success.
2. Use non-zero codes for errors or special outcomes that callers need to recognize.
3. Document the meaning of each code, the conditions that trigger it, and how to handle it.
4. Print error messages to standard error; reserve standard output for primary results if the output is consumed as data.
5. Never swallow significant exceptions and return success.
6. Place the process termination decision at the entry point layer; avoid calling System.exit from libraries.
7. Test standard output, standard error, and exit codes, especially for invalid inputs and runtime errors.
8. Keep status codes within a range that transfers cleanly across operating systems. On many Unix-like shells, exit statuses are represented in the range 0–255; do not rely on negative or large numbers being preserved identically across all platforms.

You can test the exit code of a Java program by running it as a child process and using **Process.waitFor()** to retrieve the return code. This is also the appropriate way to test when the application calls System.exit, because calling main directly in the same JVM would affect the test runner process.

There is no single mandatory universal set of Java error codes for all applications. What matters is that the application's convention remains consistent across source code, documentation, scripts, monitoring systems, and CI pipelines.

## 11. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Returning an int from main sets the exit code. | The traditional Java entry point returns void; a method's return value is not the exit code. |
| Printing “ERROR” tells the shell the program failed. | Shells typically rely on the exit status; the program must return a non-zero code to signal an error. |
| An exception in any thread always makes the JVM return a non-zero code. | An exception in a worker thread usually terminates only that thread; the application must propagate the error to the coordinating thread and set the process status explicitly. |
| System.exit is the same as returning from main. | return only exits the method; System.exit initiates shutdown of the entire JVM. |
| System.exit guarantees all finally blocks will run. | Stack frames are not guaranteed to unwind; use try-with-resources/finally before requesting shutdown. |
| Runtime.halt is a normal way to shut down. | halt bypasses shutdown hooks and stops the JVM abruptly. |
| $? in PowerShell is the numeric exit code. | $? is a Boolean; use $LASTEXITCODE for native processes such as java.exe. |
| A pipeline logging successfully means Java succeeded. | A pipeline can return the exit code of its last command; use pipefail in Bash when you need to preserve Java's failure. |

## 12. Checklist for command-line Java applications

Before integrating an application into scripts or CI, verify the following scenarios:

- Run with valid input and confirm the exit code is **0**.
- Run with missing or invalid arguments and confirm the exit code is **non-zero**.
- Run with a missing configuration file or missing dependency; confirm the error is reported to standard error.
- Trigger an unhandled error in the main thread and observe that the launcher returns an error status.
- If worker threads are used, verify that errors from workers are propagated to the main process and not masked.
- Run through a shell or logging pipeline to ensure the error code is preserved.
- Test behavior in CI or the deployment environment, where Java versions and shells may differ from the development machine.

Exit codes are part of the interface a Java application provides to the operating system and external tools. When a program uses 0 for success, non-zero codes for intentional errors, writes messages to the proper streams, and preserves error statuses through scripts, the Java launcher can integrate reliably with build tools, automation, and CI.
