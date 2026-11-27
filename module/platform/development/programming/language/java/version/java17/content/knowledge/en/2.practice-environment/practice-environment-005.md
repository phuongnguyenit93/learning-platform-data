# Creating a Small Java 17 Project, Compiling, and Running from the Command Line

When learning Java, you do not need an IDE to get started. The JDK toolset lets you create source files, compile them to bytecode, run the program, and package the application right in the terminal. This lesson builds a **command-line task manager (Task CLI)** application that can add, list, and mark tasks as completed, giving you end-to-end practice with the Java 17 development workflow.

The application uses **Java 17**, the JDK standard library, and three source files. No Maven, Gradle, or third-party libraries are required. Working with `javac`, `java`, and `jar` remains a valuable foundation when working with modern Java versions.

## 1. Objectives and Prerequisites

After completing this lesson, you will be able to:

- Distinguish **JDK**, **`.java` source code**, **`.class` bytecode**, and the **JVM**.
- Create a project structure using `package` declarations and organize multiple Java classes.
- Compile with Java 17 compatibility, specify where `.class` files are written, and run a class with `main`.
- Read common error messages when compiling and running from the terminal.
- Package compiled classes into a JAR file with an entry point, then run it with `java -jar`.

You need **JDK 17 or a newer JDK supporting the `--release 17` option**. To follow the lesson closely, using JDK 17 is recommended. Open a terminal in a writable directory and verify:

~~~text
java -version
javac -version
jar --version
~~~

For example, when using JDK 17, the output of `java -version` and `javac -version` contains version `17`. The JDK vendor and patch numbers may differ. `java` launches the JVM, `javac` compiles source code, and `jar` creates/reads JAR archives. If `java` runs but `javac` does not exist, verify that a **full JDK** is installed and check your `PATH` configuration.

### From Source Code to Running Program

~~~text
src/main/java/.../*.java
          |
          | javac --release 17 -d out ...
          v
out/.../*.class  (bytecode)
          |
          | java -cp out vn.example.taskcli.Main
          v
JVM runs the program
          |
          | jar --create ... -C out .
          v
taskcli.jar       (package runnable with java -jar)
~~~

`javac` catches syntax errors and performs type checking at compile time; the JVM executes the bytecode afterward. Compiling a Java application does not automatically turn it into a standalone `.exe` executable; `.class` files and JARs still require a compatible Java runtime to execute.

## 2. Designing the Task CLI Project

We organize the source files into directories matching the package name. The project has the following structure:

~~~text
task-cli/
├── src/
│   └── main/
│       └── java/
│           └── vn/
│               └── example/
│                   └── taskcli/
│                       ├── Main.java
│                       ├── Task.java
│                       └── TaskManager.java
├── out/                  (generated during compilation)
└── taskcli.jar           (generated during packaging)
~~~

The three classes have clear responsibilities:

| Component | Role |
|---|---|
| `Task` | Represents a task: ID, title, and completion status. |
| `TaskManager` | Manages the list of tasks in memory; provides add, list, and complete operations. |
| `Main` | Reads user commands from the terminal, calls `TaskManager`, and prints output. |

**Scope note:** Data in this example is kept in memory. When you exit and reopen the program, the task list starts empty. For persistent storage, you can add file or database persistence in a follow-up step.

### Creating Directories

Open a terminal, create the `task-cli` project folder, and change into it. In **PowerShell on Windows**:

~~~powershell
mkdir task-cli
cd task-cli
New-Item -ItemType Directory -Force -Path src/main/java/vn/example/taskcli | Out-Null
New-Item -ItemType Directory -Force -Path out | Out-Null
~~~

In **Bash/Zsh on Linux or macOS**:

~~~bash
mkdir task-cli
cd task-cli
mkdir -p src/main/java/vn/example/taskcli out
~~~

Paths use `/` in the examples for consistency. You can write the source files in any text editor and save the three `.java` files in the exact locations shown below. Save the files with UTF-8 encoding.

## 3. Writing the Source Code

### 3.1. Data Model — `Task.java`

Create `src/main/java/vn/example/taskcli/Task.java`:

~~~java
package vn.example.taskcli;

public record Task(int id, String title, boolean completed) {
    public Task {
        if (id <= 0) {
            throw new IllegalArgumentException("Task id must be positive");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("Task title must not be blank");
        }
        title = title.strip();
    }

    public Task markCompleted() {
        return new Task(id, title, true);
    }
}
~~~

`record` is a standard feature in Java 17 suited for representing simple data carriers. Java automatically generates the canonical constructor, accessor methods `id()`, `title()`, `completed()`, along with `equals()`, `hashCode()`, and `toString()`. The `public Task { ... }` block is a *compact constructor*: it validates the data and normalizes the title before storing it.

A `record` object is immutable after creation. Therefore, `markCompleted()` **returns a new `Task`** with `completed = true` instead of mutating the existing object directly. This approach keeps state transitions intentional.

### 3.2. List Management — `TaskManager.java`

Create `src/main/java/vn/example/taskcli/TaskManager.java`:

~~~java
package vn.example.taskcli;

import java.util.ArrayList;
import java.util.List;

public final class TaskManager {
    private final List<Task> tasks = new ArrayList<>();
    private int nextId = 1;

    public Task add(String title) {
        Task task = new Task(nextId, title, false);
        tasks.add(task);
        nextId++;
        return task;
    }

    public List<Task> all() {
        return List.copyOf(tasks);
    }

    public boolean markCompleted(int id) {
        for (int i = 0; i < tasks.size(); i++) {
            Task current = tasks.get(i);
            if (current.id() == id) {
                tasks.set(i, current.markCompleted());
                return true;
            }
        }
        return false;
    }
}
~~~

`ArrayList` is a resizable list that supports appending and replacing elements. `nextId` generates sequential IDs within a single run. `List.copyOf(tasks)` returns an unmodifiable list so callers cannot mutate it directly, ensuring all modifications go through `TaskManager` methods. When marking a task completed, the program finds the matching ID and replaces the old `Task` with a new record instance.

In this small application, linear search with a loop is straightforward to follow. For larger datasets or persistent storage, you can consider other data structures and storage mechanisms.

### 3.3. Command-Line Interface — `Main.java`

Create `src/main/java/vn/example/taskcli/Main.java`:

~~~java
package vn.example.taskcli;

import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import java.util.Scanner;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        TaskManager manager = new TaskManager();
        printHelp();

        try (Scanner scanner = new Scanner(System.in, StandardCharsets.UTF_8)) {
            boolean running = true;

            while (running) {
                System.out.print("task> ");
                System.out.flush();

                if (!scanner.hasNextLine()) {
                    break;
                }

                String line = scanner.nextLine().strip();
                if (line.isEmpty()) {
                    continue;
                }

                String[] parts = line.split("\\s+", 2);
                String command = parts[0].toLowerCase(Locale.ROOT);

                switch (command) {
                    case "add" -> {
                        if (parts.length < 2 || parts[1].isBlank()) {
                            System.out.println("Usage: add <title>");
                        } else {
                            Task task = manager.add(parts[1]);
                            System.out.printf(
                                    "Added #%d: %s%n", task.id(), task.title());
                        }
                    }
                    case "list" -> {
                        List<Task> tasks = manager.all();
                        if (tasks.isEmpty()) {
                            System.out.println("No tasks yet.");
                        } else {
                            for (Task task : tasks) {
                                String check = task.completed() ? "x" : " ";
                                System.out.printf(
                                        "[%s] #%d %s%n",
                                        check, task.id(), task.title());
                            }
                        }
                    }
                    case "done" -> {
                        if (parts.length < 2) {
                            System.out.println("Usage: done <id>");
                        } else {
                            try {
                                int id = Integer.parseInt(parts[1].strip());
                                if (manager.markCompleted(id)) {
                                    System.out.println("Completed #" + id);
                                } else {
                                    System.out.println("Task not found: #" + id);
                                }
                            } catch (NumberFormatException exception) {
                                System.out.println("Id must be an integer.");
                            }
                        }
                    }
                    case "help" -> printHelp();
                    case "exit" -> running = false;
                    default -> System.out.println(
                            "Unknown command. Type help for instructions.");
                }
            }
        }

        System.out.println("Goodbye!");
    }

    private static void printHelp() {
        System.out.println("Commands:");
        System.out.println("  add <title>  - create a task");
        System.out.println("  list         - show all tasks");
        System.out.println("  done <id>    - mark a task as completed");
        System.out.println("  help         - show commands");
        System.out.println("  exit         - quit");
    }
}
~~~

Notable points:

- `public static void main(String[] args)` is the entry point when running `Main`. The fully qualified class name is `vn.example.taskcli.Main`.
- `Scanner` reads lines from `System.in`. `try (...)` closes the scanner on exit; checking `hasNextLine()` allows clean exit when the user sends EOF.
- `String.strip()` removes leading/trailing whitespace. `split("\\s+", 2)` splits into **at most two parts**: the command name and the entire remainder of the line, so task titles can contain spaces.
- `switch` with `case "..." ->` branches is standard syntax in Java 17. `Locale.ROOT` normalizes command names consistently, independent of the OS locale.
- `Integer.parseInt()` can throw `NumberFormatException` if the user enters a non-integer ID; the program catches the exception and prints an error rather than crashing abruptly.
- `StandardCharsets.UTF_8` is specified when reading input. To enter Vietnamese or other non-ASCII characters on Windows, the terminal must also be configured to support UTF-8; terminal font and encoding settings affect character rendering.

The source code uses ASCII text in its messages so it runs identically across terminals; users can still enter Unicode task titles when terminal input supports UTF-8.

## 4. Compiling with `javac`

Make sure the terminal is in the `task-cli` root directory (the directory containing `src` and `out`). Run **the same command in PowerShell, Bash, and Zsh**:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/main/java/vn/example/taskcli/Task.java src/main/java/vn/example/taskcli/TaskManager.java src/main/java/vn/example/taskcli/Main.java
~~~

If successful, `javac` typically finishes **without printing any output**. Inspect the output directory:

~~~text
out/
└── vn/
    └── example/
        └── taskcli/
            ├── Main.class
            ├── Task.class
            └── TaskManager.class
~~~

Explanation of the components:

| Component | Meaning |
|---|---|
| `javac` | The Java compiler included in the JDK. |
| `--release 17` | Compiles for Java 17-compatible APIs and bytecode version, even when using a newer JDK. |
| `-encoding UTF-8` | Reads `.java` source files as UTF-8, avoiding reliance on the machine's default encoding. |
| `-d out` | Writes `.class` files into the `out` directory, automatically creating subdirectories matching the package. |
| The `.java` paths | Explicitly lists the source files to compile. |

The file list is written out explicitly rather than using a `*.java` wildcard; this can be copied directly into PowerShell and common shells, because wildcard expansion rules for external commands are not completely identical across shells.

The directory structure under `-d` mirrors the `package vn.example.taskcli;` declaration. You do **not** need to manually create `out/vn/example/taskcli` before compiling.

### Observing a Compilation Error

If you intentionally change `task.title()` to `task.unknownMethod()` in `Main.java` and recompile, `javac` will report an error like `cannot find symbol` and indicate the line number with the nonexistent method. Restore `task.title()` and recompile to continue.

This is a **compile-time error**—no instructions have executed on the JVM yet. Input errors like `done abc` shown later are handled **at runtime while the program is executing**.

## 5. Running with `java` and Using the Application

After compiling successfully:

~~~bash
java -cp out vn.example.taskcli.Main
~~~

In this command:

- `java` starts the JVM.
- `-cp out` (long form `--class-path out`) tells the JVM where to look for compiled classes. `out` is the **classpath root**, not `out/vn/example/taskcli`.
- `vn.example.taskcli.Main` is the *fully qualified class name*. When running a class from the classpath, do not add the `.class` extension and do not write it as a file path.

You will see the command list and the `task>` prompt. An example interactive session:

~~~text
Commands:
  add <title>  - create a task
  list         - show all tasks
  done <id>    - mark a task as completed
  help         - show commands
  exit         - quit
task> add Read chapter 1
Added #1: Read chapter 1
task> add Practice Java CLI
Added #2: Practice Java CLI
task> list
[ ] #1 Read chapter 1
[ ] #2 Practice Java CLI
task> done 1
Completed #1
task> list
[x] #1 Read chapter 1
[ ] #2 Practice Java CLI
task> done abc
Id must be an integer.
task> exit
Goodbye!
~~~

`[ ]` indicates an incomplete task, while `[x]` indicates completed. `add` supports multi-word titles. `done` expects an integer; when an ID does not exist, the program prints `Task not found`. Pressing Enter on an empty line prints the next prompt; `exit` or EOF ends the input loop.

Whenever you edit `.java` source files, you must rerun `javac ...` to regenerate bytecode before running `java -cp ...`. `java -cp` runs the existing `.class` files; it does not automatically recompile a multi-file project.

### Testing with Predefined Input

For a program reading from `System.in`, you can pipe a sequence of commands to inspect output quickly without typing line by line.

PowerShell:

~~~powershell
@('add Read Java 17', 'add Build a CLI', 'list', 'done 1', 'list', 'exit') | java -cp out vn.example.taskcli.Main
~~~

Bash/Zsh:

~~~bash
printf 'add Read Java 17\nadd Build a CLI\nlist\ndone 1\nlist\nexit\n' | java -cp out vn.example.taskcli.Main
~~~

Both commands use ASCII input to avoid differences in shell input encoding settings. This is a manual smoke-test step suitable for a small example; as an application grows, you can write automated tests for the business-logic classes.

## 6. Packaging and Running from a JAR

Once `.class` files are in `out`, create a **JAR with a declared main class** using:

~~~bash
jar --create --file taskcli.jar --main-class vn.example.taskcli.Main -C out .
~~~

Meaning:

- `--create`: creates a JAR archive.
- `--file taskcli.jar`: writes to `taskcli.jar` in the current directory.
- `--main-class vn.example.taskcli.Main`: sets the entry point in the JAR manifest.
- `-C out .`: packages the contents **inside** `out` as the archive root; class paths inside the JAR start with `vn/example/taskcli/...`.

Run the packaged program:

~~~bash
java -jar taskcli.jar
~~~

The behavior matches running via the classpath. This JAR contains the bytecode of the three classes and the entry-point metadata; it is **not** a JAR that bundles a JVM. The target machine still needs a Java 17 runtime or a compatible newer version. Because this project has no external libraries, the JAR already holds all required application classes; projects with external dependencies require an appropriate packaging or classpath strategy.

You can list the files inside the archive with:

~~~bash
jar --list --file taskcli.jar
~~~

You will see entries such as `META-INF/MANIFEST.MF` and `vn/example/taskcli/Main.class`. If you modify the source code, the sequence to update the JAR is **recompile `.class` → rerun `jar --create ...` → run `java -jar ...`**.

### Comparing Common Ways to Run

| Way to Run | When to Use | Key Takeaway |
|---|---|---|
| `java -cp out vn.example.taskcli.Main` | Working with classes compiled into a directory. | Specify the classpath root and the fully qualified class name. |
| `java -jar taskcli.jar` | Running a packaged application with `Main-Class`. | The JVM reads the entry point from the JAR's manifest. |
| `java Hello.java` | Quickly running a supported single-file source program. | Source-code launch mode exists since Java 11; it does not replace structuring and compiling multi-file projects as in this lesson. |

Example of single-file source-code mode (independent of Task CLI), create `Hello.java`:

~~~java
public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello, Java 17!");
    }
}
~~~

Then run `java Hello.java`. This is a convenient modern feature for short snippets; for multi-file projects like Task CLI, the `javac` + `java -cp` workflow helps you understand bytecode, packages, and the classpath clearly.

## 7. Common Errors When Working from the Terminal

| Symptom | Common Cause | How to Check/Fix |
|---|---|---|
| `javac` is not recognized | JDK is not installed or the JDK `bin` folder is not in `PATH`. | Check `javac -version`; configure the full JDK and open a new terminal. |
| `error: file not found` | Running in the wrong directory or wrong source file path/name. | Change into `task-cli` and verify the exact `src/main/java/...` path. |
| `cannot find symbol` | Wrong class/method name, missing import, or required file omitted from compile command. | Read the reported symbol name and line number; compile all three example files together. |
| `Could not find or load main class ...` | Wrong classpath root or package/class name; missing `.class` file. | Verify `out/vn/example/taskcli/Main.class` exists and run `java -cp out vn.example.taskcli.Main`. |
| `UnsupportedClassVersionError` | Runtime is older than the compiled bytecode. | Check both `java -version` and `javac -version`; use Java 17+ runtime and `--release 17` when compiling. |
| `no main manifest attribute` when running `java -jar` | JAR has no `Main-Class` declared. | Recreate with `jar --create --file taskcli.jar --main-class vn.example.taskcli.Main -C out .`. |
| Non-ASCII/Vietnamese characters render garbled | Mismatched source file, input, or terminal encoding. | Save files as UTF-8, compile with `-encoding UTF-8`, and set the terminal to UTF-8. |
| Edited code still produces old behavior | Running older bytecode or an older JAR built before the edit. | Recompile, repackage if using a JAR, and run the updated output. |

For package-related errors, remember that three things must match: **`package` declaration → class path inside `out` → fully qualified class name at launch**. For example, `package vn.example.taskcli;` maps to `out/vn/example/taskcli/Main.class` and the command `java -cp out vn.example.taskcli.Main`.

There is no need to touch `sun.*` APIs or rely on JDK internals to solve any of these errors. This example uses only public, standard Java 17 APIs.

## 8. Extending This Small Project

Once the basic program works, you can practice further in this order:

1. Add a `remove <id>` command to delete a task and handle nonexistent IDs.
2. Add `list pending` / `list done` to filter by status; consider using `Stream` or a clear loop.
3. Write unit tests for `TaskManager`: adding tasks, incrementing IDs, marking completed, and handling missing IDs. You can integrate JUnit using a build tool when learning dependency management.
4. Save tasks to a text or JSON file in a defined format and reload them on startup. Handle file I/O errors and use UTF-8 encoding.
5. Once a project grows to many files and libraries, transition to Maven or Gradle to automate compilation, testing, and packaging. Understanding `javac`, `java`, packages, and classpath remains the foundation for knowing what build tools do under the hood.

**Knowledge check:** Why must you use `-cp out` instead of `-cp out/vn/example/taskcli`? If compiling with a newer JDK while targeting Java 17, which flag should you keep? Why does `java -jar taskcli.jar` not require passing the `Main` class name? When modifying `TaskManager.java`, which steps must be rerun so the JAR contains the new code?

You have completed a full practical cycle: creating a project → writing multiple packaged classes → compiling to Java 17-compatible bytecode → running on the JVM → packaging and running a JAR. You can apply this same workflow to other small CLI applications before adopting an IDE or build tool.
