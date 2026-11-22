# Snippets in JShell

JShell is the REPL (Read-Eval-Print Loop) tool included with the JDK that lets you enter and run Java code piece by piece without creating a class with a `main` method for every test. Each piece of Java code that JShell recognizes and processes is called a **snippet**.

A snippet can be an expression, statement, variable, method, class, interface, or import. Once entered, JShell parses and compiles the snippet, executes it when appropriate, and maintains state so subsequent snippets can use earlier declarations. This allows developers to try out APIs, test expressions, explore libraries, and develop a Java idea step by step.

## 1. What Is a Snippet?

In a standard Java file, executable code is typically organized inside classes and methods. With JShell, you can enter a variable declaration or expression directly at the top level:

~~~java
int quantity = 4
quantity * 3
~~~

JShell accepts these two pieces of code as two separate snippets:

- The first snippet declares the `quantity` variable.
- The second snippet is an expression that uses the declared variable.
- The expression is evaluated immediately, and JShell stores the result in a temporary variable named something like `$2`.

There is no need to write a `Main` class, declare `public static void main(String[] args)`, or manually compile with `javac` for every small change.

A snippet is not an arbitrary line of text. JShell parses Java syntax to determine a complete unit of code. A snippet can span multiple lines—for example, a method or class declaration whose body is enclosed in curly braces.

## 2. Types of Snippets

The `jdk.jshell` API categorizes snippets by their content. The main kinds include:

| Kind | Meaning | Example |
|---|---|---|
| `IMPORT` | Import declaration | `import java.time.LocalDate;` |
| `TYPE_DECL` | Class, interface, enum, record, or annotation type declaration | `class User { }` |
| `METHOD` | Top-level method declaration | `int doubleIt(int x) { return x * 2; }` |
| `VAR` | Variable declaration | `int count = 3;` |
| `EXPRESSION` | Expression to evaluate | `count * 2` |
| `STATEMENT` | Java statement | `System.out.println(count);` |
| `ERRONEOUS` | Input that cannot be parsed into a valid Java snippet | `int = ;` |

For example, a session might include:

~~~java
import java.time.LocalDate
LocalDate today = LocalDate.now()
class Customer {
    String name;
    Customer(String name) { this.name = name; }
}
Customer customer = new Customer("Linh")
customer.name
~~~

Declared imports, variables, and types remain in the current JShell state until they are replaced, dropped, or the session is reset.

Not every line entered is a snippet. Commands starting with `/`, such as `/list` or `/vars`, are **JShell commands** used to control the tool. They are not Java statements and are not stored as regular Java snippets.

## 3. Starting JShell and Entering Snippets

Check the JDK:

~~~bash
java -version
jshell --version
~~~

Start an interactive session:

~~~bash
jshell
~~~

When you see the prompt:

~~~text
jshell>
~~~

you can enter Java code directly:

~~~text
jshell> int count = 3
count ==> 3

jshell> count * 2
$2 ==> 6

jshell> System.out.println("Ready")
Ready
~~~

The lines above illustrate a typical feedback mode. The exact output may vary depending on the JDK version or feedback mode.

- `count` is a user-declared named variable.
- `$2` is the temporary variable name JShell generates for the expression result.
- `System.out.println(...)` is a statement with a side effect; it prints to the console and does not need to create a result variable.

You can include a semicolon at the end of a snippet. For many top-level declarations or expressions, JShell can usually detect snippet boundaries without a semicolon, though using semicolons keeps code consistent with standard Java source.

## 4. Complete Example: Multiple Snippets Sharing State

Create a file named `demo.jsh`:

~~~java
int quantity = 4
quantity * 3
String name = "Ada"
void greet(String who) {
    System.out.println("Hello, " + who);
}
greet(name)
/list
/vars
/methods
/exit
~~~

Run it from the terminal:

~~~bash
jshell --feedback concise demo.jsh
~~~

With JDK 24.0.2 and the `concise` feedback mode, the output of this example is:

~~~text
Hello, Ada

   1 : int quantity = 4;
   2 : quantity * 3
   3 : String name = "Ada";
   4 : void greet(String who) {
           System.out.println("Hello, " + who);
       }
   5 : greet(name)
  int quantity = 4
  int $2 = 12
  String name = "Ada"
  void greet(String)
~~~

This example demonstrates:

1. `quantity` is declared in the first snippet.
2. The expression `quantity * 3` uses that variable and produces the result `$2`.
3. The variable `name` is retained in the session.
4. The `greet` method is declared once and can be called in a subsequent snippet.
5. `/list`, `/vars`, and `/methods` inspect the current declarations.

A `.jsh` file can contain both Java snippets and JShell commands. When using a file, snippets are processed sequentially in the order they appear.

## 5. Multi-Line Snippets and How JShell Determines Boundaries

A snippet can span multiple lines. JShell continues accepting input when the syntax is incomplete, such as when inside a method, class, or block body.

Example of direct input:

~~~text
jshell> void printRange(int start, int end) {
   ...>     for (int i = start; i <= end; i++) {
   ...>         System.out.println(i);
   ...>     }
   ...> }
~~~

The `...>` prompt indicates that JShell is waiting for the rest of the snippet. Only when all braces are closed and the syntax is complete is the snippet processed.

You can declare a multi-line class:

~~~java
class Product {
    private final String code;

    Product(String code) {
        this.code = code;
    }

    String code() {
        return code;
    }
}
~~~

Then create an instance:

~~~java
Product product = new Product("P-100")
product.code()
~~~

JShell parses the syntax to determine when a snippet is complete. Therefore, you should not assume each input line corresponds to one snippet. A multi-line declaration is still a single snippet.

## 6. Expressions and Automatic Result Variables

When you enter a standalone expression, JShell evaluates it and stores the result in a temporary variable if the expression returns a value.

For example:

~~~java
10 + 5
Math.sqrt(81)
"java".toUpperCase()
~~~

The results are assigned to temporary variables such as `$1`, `$2`, and `$3`, depending on the snippet order in the session.

You can use a temporary result in a subsequent snippet:

~~~java
$1 * 2
~~~

Temporary variable names are assigned automatically by JShell. If you need long-term references or more readable code, assign the result to an explicitly named variable:

~~~java
int total = 10 + 5
double root = Math.sqrt(81)
String language = "java".toUpperCase()
~~~

You can then use `total`, `root`, and `language` directly.

A statement such as:

~~~java
System.out.println("Hello")
~~~

performs a console print action. It does not produce an expression value to store in a temporary variable.

## 7. Snippet IDs and Reviewing Entered Code

JShell assigns an ID to snippets entered in a session. IDs are typically sequential numbers; snippets initialized from startup definitions may use a different prefix.

The most important command for viewing snippets is:

~~~text
/list
~~~

`/list` displays active snippets along with their IDs. You can view a specific snippet by ID:

~~~text
/list 3
~~~

View the full snippet history, including erroneous, overwritten, dropped, and startup snippets:

~~~text
/list -all
~~~

View startup snippets:

~~~text
/list -start
~~~

Several other commands also support lookup by ID or name. IDs are only meaningful within the current session's history; after a reset, do not assume old IDs still represent the same snippets.

Commands starting with `/` are not assigned snippet IDs. For example, `/list` does not become the next numbered snippet.

## 8. Inspecting Variables, Methods, Types, and Imports

JShell provides dedicated commands to inspect existing declarations.

### Inspecting variables with /vars

~~~text
/vars
~~~

This command displays the type, name, and value of active variables. You can filter by name or ID:

~~~text
/vars total
/vars 2
/vars -all
~~~

`/vars -all` includes variables that have been overwritten, dropped, failed, or declared in startup snippets.

### Inspecting methods with /methods

~~~text
/methods
~~~

This command displays method names, parameter types, and return types. You can filter by name:

~~~text
/methods greet
~~~

Or view the entire method history:

~~~text
/methods -all
~~~

### Inspecting classes and interfaces with /types

~~~text
/types
/types Product
/types -all
~~~

This command lets you inspect active type declarations, including classes, interfaces, and other Java type declarations supported by JShell.

### Inspecting imports with /imports

~~~text
/imports
~~~

This command displays active imports, including those from startup definitions.

These commands help you observe the current state without having to scroll back through every line you entered.

## 9. Snippet Lifecycle and Status

A snippet has a lifecycle tied to its compilation and execution state. In the `jdk.jshell` API, `Snippet.Status` defines statuses such as:

| Status | General Meaning |
|---|---|
| `VALID` | The snippet compiled/evaluated validly and is active. |
| `RECOVERABLE_DEFINED` | A declaration is defined, but it has unresolved references. |
| `RECOVERABLE_NOT_DEFINED` | The snippet cannot be fully defined yet due to missing dependencies. |
| `DROPPED` | The snippet has been removed from active state by the user. |
| `OVERWRITTEN` | The snippet has been replaced by a new declaration. |
| `REJECTED` | The snippet was rejected due to an unrecoverable compilation or parse error. |
| `NONEXISTENT` | No corresponding snippet exists in the queried state. |

These are JShell API statuses; typical REPL users do not need to memorize the entire enum. When you need to inspect history, `/list -all` is the most direct way to see both current and inactive snippets.

A snippet may be syntactically valid yet depend on a type or variable that has not been declared yet. JShell can retain the information so the status recovers once the dependency appears. Conversely, unrecoverable syntax errors cause the snippet to be rejected.

It is important to distinguish snippet status from execution outcome. A snippet can compile successfully yet throw an exception at runtime. In that case, the runtime error is displayed, but that does not mean the snippet has a syntax error or is automatically removed from history.

## 10. Replacing and Dropping Snippets

If you redeclare a variable with the same name, JShell replaces the previous declaration:

~~~java
int score = 10
score + 1
int score = 20
score
~~~

After the final declaration, `score` holds the new value. The older declaration snippet is marked as overwritten in history.

You can verify this with:

~~~text
/list -all
/vars -all
~~~

To remove a snippet from active state, use:

~~~text
/drop 3
~~~

You can also drop by name:

~~~text
/drop score
~~~

`/drop` makes the snippet inactive in the JShell state. If other snippets depend on the dropped declaration, those dependent snippets may become unusable until the dependency is redefined.

Dropping a declaration is not the same as deleting a line in a regular source file. JShell manages history and dependency relationships between snippets; use `/list -all` to review what happened.

## 11. Editing Snippets with /edit

You can open a snippet in an external editor:

~~~text
/edit 4
~~~

Or edit by name:

~~~text
/edit greet
~~~

The editor is configured with `/set editor`. If not configured, JShell checks the `JSHELLEDITOR`, `VISUAL`, and `EDITOR` environment variables before falling back to its built-in simple editor if needed.

Example configuration in an environment with `notepad`:

~~~text
/set editor notepad
~~~

After editing and saving in the editor, JShell reads the updated code and re-evaluates the corresponding snippet. Dependent declarations may be updated based on the new compilation results.

You can edit all active snippets at once:

~~~text
/edit
~~~

Or edit the entire history, including erroneous, overwritten, dropped, and startup snippets:

~~~text
/edit -all
~~~

When editing multiple snippets, maintain a valid order and dependency relationships. If a method uses another class, that class must be defined or resolvable within the session.

## 12. Saving and Loading Snippets with /save and /open

To save active snippets to a file:

~~~text
/save session.jsh
~~~

Save all snippets, including erroneous, overwritten, dropped, and startup snippets:

~~~text
/save -all full-session.jsh
~~~

Save the sequential history of entered commands and snippets:

~~~text
/save -history command-history.txt
~~~

You can save a specific snippet by ID:

~~~text
/save 3 selected-snippet.jsh
~~~

To load a file back into the session:

~~~text
/open session.jsh
~~~

JShell reads the file and processes its contents as interactive input, including both snippets and JShell commands in the file. Snippets are executed in the order they appear in the file.

A `.jsh` file can be used to share examples, create lab exercises, prepare demo environments, or reproduce bugs. However, `/open` executes the Java code and JShell commands in the file. Only load files from trusted sources; do not open an unfamiliar script as if it were plain text documentation.

## 13. Resetting and Reloading Sessions

The `/reset` command restarts the JShell execution state and clears snippets entered in the current session. Startup definitions are re-executed:

~~~text
/reset
~~~

Save your work before resetting if you need to keep your code.

`/reload` resets the state and then replays valid snippets and drop commands in the order they were entered in the current history span:

~~~text
/reload
~~~

You can use:

~~~text
/reload -quiet
~~~

to reduce output during replay, though errors are still reported.

`/reload -restore` can restore history from the previous session span according to JShell's rules. This is a session recovery mechanism within the REPL, not a substitute for saving source code to a file when long-term storage is needed.

Key differences:

- `/reset`: discards current code state and starts fresh.
- `/reload`: resets and then re-runs valid history from the current session span.
- `/save`: saves source/history to a file for use in another session.

## 14. Startup Definitions and Feedback Modes

At startup, JShell typically loads a set of startup snippets, including common imports and several helper definitions. As a result, certain classes in `java.util` or `java.io` can be used without explicit imports.

View current imports:

~~~text
/imports
~~~

You can disable startup definitions:

~~~bash
jshell --no-startup
~~~

Or specify a custom startup file:

~~~bash
jshell --startup my-startup.jsh
~~~

Startup definitions can alter the initial session environment. When reproducible results are needed, specify the JDK version, startup file, and startup options used.

The feedback mode determines how much information JShell prints after processing a snippet. Built-in modes include `normal`, `concise`, `silent`, and `verbose`.

You can select one at startup:

~~~bash
jshell --feedback concise
~~~

Or switch during a session:

~~~text
/set feedback concise
~~~

- `normal`: displays relatively detailed result information and feedback.
- `concise`: reduces feedback, suitable for demos or scripts.
- `silent`: minimizes standard feedback.
- `verbose`: displays more detailed information about processing.

Feedback mode only changes how results are presented. It does not change the Java semantics of a snippet.

## 15. Using Snippets with External Libraries and Modules

If a snippet uses classes in an external JAR, add the JAR to JShell's classpath.

For example:

~~~bash
jshell --class-path "lib/customer-api.jar;lib/common.jar"
~~~

On Windows, the classpath uses semicolons. On Linux/macOS, it uses colons:

~~~bash
jshell --class-path "lib/customer-api.jar:lib/common.jar"
~~~

After opening the session, you can import and use classes from the library:

~~~java
import com.acme.api.Customer
Customer customer = new Customer("Linh")
~~~

For modular applications, JShell supports `--module-path` and `--add-modules`:

~~~bash
jshell --module-path mods --add-modules com.acme.customer
~~~

Modules must be resolvable from the module path. If unsure, check the module descriptor and dependencies before running JShell.

The `-C` option passes flags to the compiler inside JShell:

~~~bash
jshell -C-Xlint
~~~

You can pass a compiler flag with its own argument by using `-C` for each part:

~~~bash
jshell -C--release=17
~~~

The `-R` option passes flags to the runtime when snippets are executed. For example:

~~~bash
jshell -R-Dapp.mode=demo
~~~

The snippet can then read the property:

~~~java
System.getProperty("app.mode")
~~~

Do not confuse `-J` with `-R`: `-J` passes flags to the JVM process running the JShell tool itself; `-R` applies to the runtime executing snippets via the execution engine.

## 16. Snippets in Learning and Development Workflows

JShell is well suited for tasks that benefit from quick feedback:

- Testing a small expression or algorithm.
- Exploring an API's methods.
- Checking how a library class behaves.
- Experimenting with strings, collections, date/time, and streams.
- Verifying type conversions or generics behavior.
- Creating short examples for lessons or demos.
- Reproducing a bug with a few minimal snippets.

Example exploring the Stream API:

~~~java
import java.util.List
List<Integer> numbers = List.of(2, 4, 6, 8)
numbers.stream().map(n -> n * n).toList()
~~~

Example testing Date/Time:

~~~java
import java.time.LocalDate
LocalDate.of(2026, 11, 10).plusDays(7)
~~~

Once an experiment stabilizes and needs to become part of an application, move the code into `.java` files, add a package structure, write tests, and build with your project's build tool. JShell is great for rapid exploration, but it does not replace the compiler/build/test pipeline of a full application.

## 17. Common Errors and How to Resolve Them

| Symptom | Common Cause | Resolution |
|---|---|---|
| `cannot find symbol` | The variable, method, class, or import does not yet exist in the session. | Declare the dependency first; check `/vars`, `/methods`, `/types`, and `/imports`. |
| JShell keeps showing the `...>` prompt | A multi-line snippet has unclosed braces or incomplete syntax. | Complete the block, close braces, or check syntax. |
| Snippet fails to run due to syntax error | Invalid Java code or incomplete declaration. | Read the diagnostic, fix the snippet, and re-enter it or use `/edit`. |
| Method worked earlier but is no longer available | The method or a dependency was dropped or overwritten. | Use `/list -all`, check status, and redefine the dependency. |
| Variable value differs from expected | The variable was redeclared or a dependent snippet was evaluated earlier. | Use `/vars -all`, `/list -all`, and re-run the expression you want to check. |
| Class in JAR not found | Missing classpath or module path. | Start with the appropriate `--class-path`, `--module-path`, and `--add-modules` options. |
| `/edit` does not open the desired editor | Editor is not configured or environment variables are incorrect. | Use `/set editor` or configure `JSHELLEDITOR`, `VISUAL`, or `EDITOR`. |
| Code lost after closing session | Snippets were not saved to a file. | Use `/save` or `/save -history` before exiting. |
| `/open` file causes batch errors | File contains invalid snippets, out-of-order dependencies, or inappropriate commands. | Inspect the file section by section and load from a reviewed version. |
| Output differs from guide | Different JDK version, feedback mode, startup definitions, or environment. | Check `jshell --version`, `/set`, `/imports`, and startup options. |

A runtime error like `NullPointerException` can occur after a snippet has compiled successfully. Distinguish compilation diagnostics from runtime exceptions: one requires fixing source/types, while the other requires inspecting data and execution logic.

## 18. Recommended Workflow

An easy-to-follow JShell session can follow this sequence:

1. Check the JDK version with `jshell --version`.
2. Start with an appropriate feedback mode.
3. Import the required libraries.
4. Declare variables and types before using them.
5. Enter small expressions or statements to verify behavior.
6. Declare methods or classes when you want to reuse logic.
7. Use `/list`, `/vars`, `/methods`, `/types`, and `/imports` to inspect state.
8. Use `/edit` or `/drop` when you need to modify the session.
9. Use `/save` to save source snippets before exiting.
10. Move stabilized code into source files and run formal builds and tests.

If investigating a bug, save a small `.jsh` file that reproduces the issue, noting the JDK version and required dependencies. A minimal example with a clear snippet order usually helps others re-run it and identify the root cause faster.

## 19. Key Takeaways

A snippet is the unit of Java code that JShell parses, evaluates, and stores in the REPL state. A snippet can be an import, type, method, variable, expression, or statement; multiple snippets can build on previously entered declarations.

Commands like `/list`, `/vars`, `/methods`, `/types`, and `/imports` help you inspect the session. `/edit`, `/drop`, `/save`, `/open`, `/reload`, and `/reset` help manage the lifecycle of entered code. Once you understand snippet boundaries, IDs, dependencies, and active state, JShell becomes a fast, saveable, and reproducible Java experimentation environment.
