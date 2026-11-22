# What Is JShell?

**JShell** is the JDK's interactive command-line tool that operates on the REPL (*Read–Eval–Print Loop*) model: it reads a snippet of Java code, evaluates it, prints the result, and waits for the next input. JShell lets you immediately try out expressions, statements, variable declarations, methods, and classes without creating a full project or writing a `main` method for every test.

JShell was introduced in Java 9. It is well-suited for learning Java syntax, exploring APIs, prototyping small algorithms, and quickly testing an idea before adding it to project source code.

## 1. What Problem Does JShell Solve?

When learning Java or trying out an API, the traditional approach is to create a `.java` file, declare a class, write `main()`, compile with `javac`, and then run with `java`. That workflow is necessary for real applications, but it can feel slow when you only want to test a few lines of code.

JShell shortens this loop:

1. Enter a Java expression or declaration.
2. JShell parses and compiles the snippet.
3. The snippet is executed inside the JShell session.
4. The result or error message is displayed immediately.
5. Valid declarations remain available for use in subsequent snippets.

For example, you can type directly:

```java
2 + 3
```

JShell evaluates the expression and displays the value. There is no need to create a class just to test addition.

JShell is useful when:

- Learning syntax, data types, collections, lambdas, and the Stream API.
- Quickly trying out a method in the Java standard library.
- Testing date/time, string, number, or regular expression formatting.
- Prototyping a small algorithm before writing unit tests.
- Exploring an API's methods and return types.
- Demonstrating Java during a class or technical walkthrough.

## 2. Checking and Starting JShell

JShell has been included with the JDK since Java 9. Open Command Prompt, PowerShell, or a terminal and check:

```bash
java -version
javac -version
jshell --version
```

These commands verify that the Java runtime, compiler, and JShell are available in your current environment. JShell is a JDK tool; if a machine only has a runtime without an appropriate JDK, the `jshell` command may not exist.

Start JShell:

```bash
jshell
```

When the tool starts successfully, you will see a prompt similar to:

```text
|  Welcome to JShell -- Version 17
|  For an introduction type: /help intro

jshell>
```

The version and welcome banner vary depending on the installed JDK. The `jshell>` prompt indicates that the tool is waiting for a Java snippet or a JShell command.

Exit the session:

```text
jshell> /exit
```

You can view startup options with:

```bash
jshell --help
```

## 3. Entering Java Expressions and Statements

In JShell, you can enter Java expressions and statements directly.

Example:

```text
jshell> 10 + 20
$1 ==> 30

jshell> String language = "Java";
language ==> "Java"

jshell> int major = 17;
major ==> 17

jshell> language + " " + major
$4 ==> "Java 17"
```

This is an illustrative transcript using the default feedback mode; temporary variable names such as `$1` or sequence numbers may vary depending on session history.

Key points to understand:

- An expression that produces a value may be stored and displayed by JShell in a temporary variable such as `$1`.
- When you declare a named variable, you can use that variable in subsequent snippets.
- Statements such as `System.out.println(...)` perform an action and print to the console.
- Valid declarations and variables are retained in the current session's state.
- Each entry does not have to live inside a class with `main()`.

Example of printing a message:

```text
jshell> System.out.println("Hello, JShell!");
Hello, JShell!
```

JShell still follows Java syntax. Statements require a semicolon according to Java rules; a standalone expression can be entered directly to inspect its result.

## 4. Declaring Methods and Classes in a Session

JShell allows you to declare methods without creating an enclosing class in source code.

Example of entering a method:

```java
int square(int number) {
    return number * number;
}
```

Once declared, call the method immediately in the session:

```text
jshell> square(6)
$2 ==> 36
```

You can declare a class:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    String greeting() {
        return "Xin chào, " + name;
    }
}
```

Create an object and call its method:

```text
jshell> Person person = new Person("Lan");
person ==> Person@...

jshell> person.greeting()
$4 ==> "Xin chào, Lan"
```

The address portion shown in the object representation may vary. The value returned by `greeting()` is the result of interest.

If you enter a multi-line block, JShell displays a continuation prompt, typically `...`, until the snippet is complete. The tool then evaluates the entire declaration.

## 5. Using Imports and Exploring Java APIs

You can import packages or classes just like in a regular Java file:

```java
import java.time.LocalDate;
import java.time.Period;
```

Then use the imported classes:

```text
jshell> LocalDate start = LocalDate.of(2024, 1, 1);
start ==> 2024-01-01

jshell> LocalDate end = LocalDate.of(2024, 1, 10);
end ==> 2024-01-10

jshell> Period.between(start, end).getDays()
$3 ==> 9
```

Imports are retained in the session. JShell also includes a set of default imports for convenience while experimenting; use the `/imports` command to see which imports are currently active.

Example of trying the Stream API on JDK 17:

```text
jshell> import java.util.List;

jshell> List<String> names = List.of("An", "Binh", "Chi");
names ==> [An, Binh, Chi]

jshell> names.stream().filter(name -> name.length() > 2).toList()
$3 ==> [Binh, Chi]
```

The `Stream.toList()` method was introduced in Java 16, so this example is suitable for JDK 17 and later.

## 6. Types of Snippets in JShell

JShell calls each unit of entered code a *snippet*. Common snippet types include:

| Type | Example |
| --- | --- |
| Expression | `1 + 2` |
| Variable declaration | `int count = 10;` |
| Method declaration | `int square(int x) { return x * x; }` |
| Class declaration | `class User { }` |
| Interface declaration | `interface Formatter { String format(String s); }` |
| Import declaration | `import java.time.LocalDate;` |
| Statement | `System.out.println("test");` |

Each snippet is evaluated individually, but successful declarations can reference each other within the same session. For example, a method declaration can use a variable or class declared earlier.

If you modify a declaration, JShell can update the state and re-evaluate dependent snippets. When there is a syntax or type error, a message is shown so you can fix and re-enter it; the JShell session remains active.

## 7. Important JShell Commands

Besides Java code, JShell has its own commands starting with a forward slash `/`. These are session control commands, not Java syntax.

| Command | Purpose |
| --- | --- |
| `/help` | Display help |
| `/help intro` | Introduce how to use JShell |
| `/list` | List snippets in the session |
| `/vars` | List declared variables |
| `/methods` | List declared methods |
| `/types` | List declared classes, interfaces, enums, and types |
| `/imports` | List current imports |
| `/history` | Display session input history |
| `/drop <id>` | Drop a snippet by ID |
| `/edit` | Open a snippet in an editor |
| `/save <file>` | Save session snippets to a file |
| `/open <file>` | Read and execute file contents in the session |
| `/reset` | Reset the session, clearing current snippet state |
| `/reload` | Reload session snippets from history |
| `/set feedback <mode>` | Change how feedback is displayed |
| `/exit` | Exit JShell |

You can view help for individual commands, for example:

```text
jshell> /help /save
jshell> /help /open
```

Command names, arguments, and detailed output may differ slightly across JDK versions. When you need exact syntax, run `/help` directly in your active session.

## 8. Managing Variables, Methods, and Snippets

When trying out many ideas, a JShell session can accumulate many declarations. Listing commands help you inspect the current state:

```text
jshell> /vars
jshell> /methods
jshell> /types
jshell> /imports
jshell> /list
```

The `/list` command displays snippets along with their IDs. You can use an ID to inspect or drop a specific snippet.

Example:

```text
jshell> int temporary = 99;
temporary ==> 99

jshell> /vars
```

If you want to remove the `temporary` declaration, first check its ID with `/list`, then run:

```text
jshell> /drop <id>
```

Replace `<id>` with the actual ID shown. Do not type the angle brackets literally.

`/drop` removes the snippet from JShell's state; if other snippets depend on it, dependent state may be affected and need to be re-evaluated.

## 9. Saving and Reopening a Session

Snippets in a session are kept in memory. If you exit JShell without saving, you should not assume declarations will automatically persist the next time you open it.

Save snippets:

```text
jshell> /save experiment.jsh
```

Reopen the file in a session:

```text
jshell> /open experiment.jsh
```

The file can contain Java statements and content suitable for JShell to execute. The `.jsh` extension is commonly used for JShell scripts to distinguish them from regular Java source files.

You can also pass a file as input on startup:

```bash
jshell experiment.jsh
```

Useful save options:

- `/save <file>`: save current snippets.
- `/save -history <file>`: save input history.
- `/save -all <file>`: also save replaced or dropped snippets, depending on the JShell version's capabilities.

To check the exact options supported by your version, run `/help /save`.

Distinguishing `/history` and `/save`: history reflects the inputs that were entered; save creates a file so you can reuse the content in another JShell session.

## 10. Adjusting Feedback and the Editor

JShell supports multiple feedback modes to suit learning or demonstrations.

Example:

```text
jshell> /set feedback concise
```

Commonly used modes:

- `normal`: default feedback, balancing detail and brevity.
- `concise`: shorter output.
- `verbose`: more detailed output.
- `silent`: minimal feedback.

You can view current settings with:

```text
jshell> /set
```

To change the editor used by `/edit`, see the help:

```text
jshell> /help /set editor
```

After configuring an editor, use `/edit` or `/edit <id>` to edit a snippet. This is useful when a method or class spans many lines and editing directly at the prompt becomes inconvenient.

## 11. Using External Libraries with the Classpath

JShell can use external JAR libraries. When starting JShell, pass the library path using `--class-path`:

```bash
jshell --class-path lib/helper.jar
```

Then import classes from the library:

```java
import com.example.helper.TextHelper;
TextHelper.normalize("  Java  ")
```

The package and method names in the example above depend on the actual library. Replace them with the API provided by your project's JAR.

If multiple JARs are needed:

**Windows:**

```powershell
jshell --class-path "lib\helper.jar;lib\logging.jar"
```

**macOS/Linux:**

```bash
jshell --class-path "lib/helper.jar:lib/logging.jar"
```

The classpath separator is a semicolon on Windows and a colon on macOS/Linux. Wrap the value in quotes if it contains spaces or characters with special meaning to the shell.

You can change the session's classpath environment using the `/env` command; see `/help /env` for the syntax of your JDK version. After changing the environment, some snippets may need to be re-evaluated.

## 12. Using the Module Path

For libraries packaged as named modules, you can pass the module path and modules to add when starting JShell:

```bash
jshell --module-path mods --add-modules com.example.library
```

Where:

- `--module-path mods`: specifies where the modules are located.
- `--add-modules com.example.library`: requests that the module be added to the session's module configuration.

You can then import public types exported by the module:

```java
import com.example.library.Utility;
```

The module must resolve properly and its packages must be exported according to JPMS rules. The module path does not replace the classpath; use the appropriate option based on how the library is packaged.

If you encounter module-not-found or unexported-package errors, check the module name, module descriptor, paths, and `requires`/`exports` relationships.

## 13. Hands-On Example: Testing a String-Processing Function

Start JShell:

```bash
jshell
```

Enter each snippet:

```java
import java.util.Locale;

String normalize(String text) {
    return text.trim().toLowerCase(Locale.ROOT);
}

normalize("  HELLO JAVA  ")
```

Result of the last expression:

```text
$3 ==> "hello java"
```

The temporary variable number may differ if the session already had earlier snippets.

Try more data:

```java
List<String> values = List.of(" Java ", " JSHELL ", " JDK ");

values.stream()
    .map(value -> normalize(value))
    .toList()
```

Top-level method declarations in JShell are placed in a static snippet context. Therefore, you cannot use `this::normalize`: there is no `this` instance in that context. A lambda calling the top-level method directly is the appropriate way to write it. If `normalize` is a static method on a compiled class, you can use `ClassName::normalize`; if it is an instance method, create an explicit instance and reference that instance:

```java
values.stream()
    .map(value -> normalize(value))
    .toList()
```

Result:

```text
$5 ==> [java, jshell, jdk]
```

This example shows how JShell is well-suited for step-by-step experimentation: declaring imports, writing a method, creating data, and calling the Stream API without creating a separate project.

## 14. How Does JShell Handle Errors?

When a snippet is invalid, JShell displays a diagnostic message and continues waiting for input. For example:

```text
jshell> int total = "Java";
|  Error:
|  incompatible types: java.lang.String cannot be converted to int
|  int total = "Java";
|              ^----^
```

You can re-enter it with the correct type:

```text
jshell> String total = "Java";
total ==> "Java"
```

Common errors:

- **Syntax error:** missing parentheses, semicolons, or invalid Java structure.
- **Type mismatch:** assigning a value incompatible with the variable's type.
- **Cannot find symbol:** undeclared variable/method or missing class import.
- **Package does not exist:** missing JAR on the classpath or module on the module path.
- **Conflicting declaration:** a variable or method already exists with an incompatible signature.
- **Runtime error:** the snippet compiles but throws an exception during execution.

Read the error location and type message before re-entering. If the session state becomes hard to follow, use `/list` to inspect snippets or `/reset` to start a fresh session.

## 15. How Does JShell Differ from javac and java?

| Criterion | JShell | javac | java |
| --- | --- | --- | --- |
| Role | REPL for interactive code testing | Compiles source code | Launches a Java application/class |
| Input | Snippets or JShell scripts | Java source files and compiler options | Class, module, or JAR with an entry point |
| Need class/`main` for small tests | No | Normally application source needs valid class structure | Application needs an appropriate entry point |
| State across inputs | Retained in current session | No interactive session | Each process run has its own lifecycle |
| Best suited for | Learning, API testing, prototyping ideas | Building source code | Running compiled applications |

JShell does not replace Maven, Gradle, an IDE, unit tests, or a build pipeline. It helps you test a piece of code quickly; a real project still needs source organization, dependencies, tests, packaging, and version control.

## 16. When Should You Use and Not Use JShell?

**Use it when:**

- You want to quickly test an expression or API.
- You need to demonstrate Java syntax in a classroom.
- You want to check the output of a short piece of code.
- You are exploring a library or checking return types.
- You need to reproduce a small issue before writing a test.

**Do not rely solely on JShell when:**

- Developing a multi-module or multi-dependency application.
- Needing reproducible builds in CI.
- Managing configuration, resources, logging, and packaging.
- Needing automated unit tests or integration tests.
- Conducting serious performance testing; benchmarks require a dedicated setup to avoid skew from JIT compilation and runtime state.

When an experiment proves valuable, save your snippets with `/save`, move the stable code into source files, and add appropriate tests.

## 17. Common Startup and Usage Issues

| Symptom | Common Cause | How to Resolve |
| --- | --- | --- |
| `jshell` is not recognized | JDK 9+ is not installed or `PATH` does not point to the JDK | Check `JAVA_HOME`, install a JDK, and update `PATH` |
| JShell uses a different Java version than expected | Multiple JDKs installed and `PATH` order is not as expected | Use `where.exe jshell` on Windows or `command -v jshell` on macOS/Linux |
| Cannot import library class | Missing JAR or wrong package | Start with `--class-path` and verify the class name |
| Module not found | Incorrect module path or module not added | Check `--module-path`, `--add-modules`, and the module descriptor |
| Variable or method no longer exists | Session was reset or snippet was dropped | Check `/list`, reopen the script, or redeclare it |
| Previous session's code is missing | Previous session was not saved | Use `/save` before exiting and `/open` to restore |
| Output displays too much information | Feedback mode is set to verbose | Use `/set feedback concise` or another appropriate mode |
| `/edit` does not open the expected editor | Editor is not configured or the editor command is invalid | Check `/help /set editor` and reconfigure it |

## 18. A Workflow for Learning and Experimenting with JShell

A simple workflow:

1. Run `jshell --version` to confirm the right JDK.
2. Start a session with `jshell`.
3. Use `/help intro` for a quick introduction.
4. Enter imports, variables, and expressions to test.
5. Extract reusable methods or classes into snippets.
6. Use `/vars`, `/methods`, `/types`, and `/list` to inspect state.
7. When errors occur, read the diagnostics and fix the snippet.
8. Save useful results with `/save`.
9. Reopen with `/open` to verify the script can run again.
10. Move stabilized code into your project and write tests as needed.

## 19. Key Takeaways

- JShell is the REPL bundled with the JDK, introduced in Java 9.
- You can test expressions, statements, variables, methods, classes, and imports without creating a class with `main()` for each experiment.
- Valid snippets are retained in the current session and can be used by later snippets.
- Commands starting with `/` such as `/help`, `/list`, `/vars`, `/save`, `/open`, and `/exit` manage the session.
- Use `--class-path` for JAR libraries and `--module-path`/`--add-modules` for modules.
- Save snippets before exiting if you want to reuse them later.
- JShell is great for quick experiments; real applications still require proper project builds and testing.

JShell bridges the gap between reading Java documentation and trying out APIs directly. Once you are comfortable with the REPL, you can test ideas faster, see the exact result of each expression, and turn useful experiments into structured source code.
