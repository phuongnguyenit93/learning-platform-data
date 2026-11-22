# Slash Commands in JShell

## 1. What Are Slash Commands in JShell?

**JShell** is the REPL (Read-Eval-Print Loop) tool included with the JDK that lets you enter and run Java declarations, statements, and expressions incrementally. You can try a piece of code, see the result immediately, and continue using the variables and methods you declared within the same session.

At the JShell prompt, there are two types of input:

- **Java snippets**: expressions, statements, variable declarations, methods, classes, interfaces, enums, or records.
- **Slash commands**: commands for managing the JShell session, always starting with `/`.

Example:

~~~text
jshell> int total = 10;
jshell> total * 2
$2 ==> 20
jshell> /vars
|    int total = 10
|    int $2 = 20
~~~

The line `total * 2` is a Java expression. `/vars` is a slash command to view the variables currently in the session. Slash commands are handled by JShell; they are not Java syntax and cannot be placed in a `.java` file as program statements.

Slash commands help you look up help, review entered code, edit or remove snippets, save and load sessions, change the classpath, configure display output, and exit JShell.

## 2. Looking Up Help and Command Lists

When you do not remember the syntax, use the built-in help right at the JShell prompt:

~~~text
/help
~~~

`/help` lists all slash commands and help topics. You can also use the alias `/?`:

~~~text
/?
~~~

To view details for a specific command, append the command name after `/help`:

~~~text
/help /list
/help /save
/help /reload
~~~

Some useful topics:

| Command | Description |
|---|---|
| `/help intro` | Introduction to using JShell |
| `/help keys` | Navigation and line-editing keys |
| `/help id` | Snippet IDs and how to reference them |
| `/help shortcuts` | Shortcuts, auto-completion, and help |
| `/help context` | Classpath, module path, and evaluation context |
| `/help rerun` | How to rerun previously entered snippets |

Help output depends on the JDK version in use. If an option is not recognized, check `/help` and `/help <command-name>` on that exact JDK instead of guessing the syntax.

## 3. Reviewing Snippets and Session State

JShell assigns an ID to each entered snippet. IDs let you view, edit, drop, or rerun a specific piece of code.

### /list

Displays active snippets that you have entered or loaded with `/open`:

~~~text
/list
~~~

Example:

~~~text
   1 : int base = 10;
   2 : int twice(int value) { return value * 2; }
   3 : twice(base)
~~~

Options:

- `/list -all`: view all snippets, including failed, overwritten, dropped, and startup snippets.
- `/list -start`: view the startup snippets evaluated when JShell starts.
- `/list <id>`: view a snippet by ID.
- `/list <name>`: view a snippet by declaration name.

IDs are assigned per session and may differ when you run the code again in a new session. Check `/list` before using an ID in another command.

### /vars, /methods, /types, and /imports

These commands let you inspect what has been declared:

| Command | Description |
|---|---|
| `/vars` | Variables and their current values |
| `/methods` | Methods and method signatures |
| `/types` | Classes, interfaces, enums, records, and declared types |
| `/imports` | Currently active imports |

Example:

~~~text
/vars
/methods
/types
/imports
~~~

You can filter by name or ID; depending on the command, `-all` and `-start` let you view inactive or startup snippets as well.

These commands are very helpful when a session has accumulated many snippets and you no longer remember which variable names, methods, or imports are in use.

### /history

`/history` displays the snippets and commands entered in the current session:

~~~text
/history
~~~

`/history -all` displays the history of the current session and previous sessions saved by JShell. History helps you find past actions; it differs from `/list`, which focuses on snippets and code state.

## 4. Editing and Dropping Snippets

### /edit

Opens snippets in an external editor for modification:

~~~text
/edit
~~~

Common forms:

~~~text
/edit 2
/edit twice
/edit -all
/edit -start
~~~

- `/edit <id>` edits a snippet by ID.
- `/edit <name>` edits a snippet by name.
- `/edit -all` edits all snippets, including failed, overwritten, dropped, and startup snippets.
- `/edit -start` edits the startup snippets in the current session.

The editor is configured with `/set editor`. If not configured, JShell checks the environment variables `JSHELLEDITOR`, `VISUAL`, and `EDITOR` in order; if none are set, JShell may open a simple built-in editor.

Example editor configuration:

~~~text
/set editor notepad
~~~

The editor command name and argument-passing behavior depend on the operating system. Use `/help /set editor` to see the syntax for your installed version.

### /drop

Removes a snippet from the active state:

~~~text
/drop 1
/drop base
~~~

After dropping, the snippet is no longer used as an active declaration. However, it may still appear in `/list -all` and in the history; `/drop` does not delete files on disk.

Example:

~~~text
jshell> int base = 10;
jshell> /drop base
jshell> base
|  Error:
|  cannot find symbol
|    symbol:   variable base
~~~

Use `/drop` when an experimental declaration is no longer needed or when you want to replace a snippet with a different version.

## 5. Saving and Loading Code with /save and /open

### /save

Saves snippets or history to a file:

~~~text
/save session.jsh
~~~

Main forms:

| Command | Saved Content |
|---|---|
| `/save <file>` | Source of active snippets |
| `/save -all <file>` | Source of all snippets, including failed, overwritten, dropped, and startup |
| `/save -history <file>` | Sequential history of commands and snippets entered in the session |
| `/save -start <file>` | Current startup definitions |
| `/save <id> <file>` | Snippet with the specified ID |

Distinguish between the two needs:

- To save active code so you can continue using it, choose `/save <file>`.
- To save all entered actions for review, choose `/save -history <file>`.

A history file can contain slash commands, failed commands, and experimental expressions. Therefore, it is not necessarily a standalone Java program or a clean source file to compile with `javac`.

### /open

Loads a file's contents as JShell input:

~~~text
/open session.jsh
~~~

JShell reads the file and processes its contents as snippets and commands entered at the prompt. The file can contain multiple Java declarations and slash commands.

Example `session.jsh` file:

~~~java
int limit = 5;
int square(int n) { return n * n; }
System.out.println(square(limit));
/vars
~~~

Loading the file:

~~~text
/open session.jsh
~~~

Output printed:

~~~text
25
~~~

The `/open` command also accepts URLs and several built-in filenames such as `DEFAULT`, `PRINTING`, `TOOLING`, and `JAVASE`. These built-in files provide utility imports or definitions for JShell.

### Saving and Restoring a Session

A simple workflow:

~~~text
/save my-session.jsh
/exit
~~~

Open JShell next time and reload it:

~~~bash
jshell --feedback concise
~~~

~~~text
/open my-session.jsh
~~~

Declarations are loaded in the order they appear in the file. If a later snippet depends on an earlier one, keep the proper order so loading succeeds.

## 6. Rerunning Snippets

JShell supports rerunning snippets without retyping the code.

| Syntax | Meaning |
|---|---|
| `/!` | Rerun the most recent snippet |
| `/<id>` | Rerun the snippet by ID |
| `/<id>-<id>` | Rerun a range of IDs |
| `/-<n>` | Rerun the nth-previous snippet from recent history |

Example:

~~~text
jshell> int value = 4;
jshell> value + 3
$2 ==> 7
jshell> /!
$3 ==> 7
~~~

`/!` reruns the most recent expression. In this example, JShell re-evaluates `value + 3` and creates a new result.

You can use `/help rerun` to see the rules for IDs, ID ranges, and counting previous snippets.

Note: rerunning a snippet may repeat side effects. If a snippet writes to a file, sends a request, updates a database, or increments a counter, the rerun command will perform that action again. Check the snippet before rerunning it.

## 7. Classpath, Module Path, and /env

JShell needs to know where to find the classes and modules used by your snippets.

### Configuring at Startup

You can pass the classpath when starting JShell:

~~~bash
jshell --class-path lib/math-utils.jar
~~~

For modular applications, you can specify the module path and modules to resolve:

~~~bash
jshell --module-path mods --add-modules com.example.math
~~~

Classpath and module path are two different mechanisms. Regular JARs are typically placed on the classpath; named modules are located via the module path.

### Viewing or Changing the Evaluation Context

Use `/env` to view the current context:

~~~text
/env
~~~

Change the classpath:

~~~text
/env -class-path lib/math-utils.jar
~~~

Change the module path or resolve modules:

~~~text
/env -module-path mods -add-modules com.example.math
~~~

When `/env` receives options, JShell updates the evaluation context, restarts the execution state, and replays valid snippets. If a snippet can no longer compile under the new context, an error is displayed.

The separator for multiple paths depends on the operating system: Windows uses a semicolon `;`, while Linux and macOS use a colon `:`.

JShell uses `/env -class-path` to change the classpath within a session; there is no general `/classpath` slash command in the JShell 24.0.2 command list.

## 8. Resetting and Reloading a Session

Both commands can restart the execution state, but they serve different purposes.

### /reset

~~~text
/reset
~~~

`/reset` clears all entered code from the JShell state, restarts the execution state, and reruns the startup code. Variables, methods, and types declared in the session will no longer be active.

You can pass evaluation context options to `/reset`, for example:

~~~text
/reset -class-path lib/math-utils.jar
~~~

Save any code you want to keep before resetting.

### /reload

~~~text
/reload
~~~

`/reload` resets the code and execution state, then replays all valid snippets and `/drop` commands in the order they were entered since the last time you started JShell or ran `/reset` or `/reload`.

Some options:

- `/reload -quiet`: suppresses replay output, though errors are still reported.
- `/reload -restore`: restores and replays the history from the previous session span, useful when you want to recover a prior JShell session.
- Can be combined with evaluation context options such as `-class-path`, `-module-path`, or `-add-modules`.

Example:

~~~text
/reload -quiet
/reload -restore
~~~

Key difference: `/reset` clears current declarations; `/reload` rebuilds the state by replaying valid snippets in the corresponding history.

Because reloading re-executes code, side effects such as writing files, updating data, or calling external services may occur again. Review your history before using it in a session with non-idempotent operations.

## 9. Configuring JShell with /set

`/set` controls how JShell initializes and displays results. Run `/set` with no arguments to view the current configuration.

Common forms:

| Command | Purpose |
|---|---|
| `/set editor <command>` | Choose the editor for `/edit` |
| `/set start <file>` | Choose the default startup file |
| `/set feedback <mode>` | Choose the feedback level |
| `/set mode ...` | Create or modify a feedback mode |
| `/set prompt ...` | Customize the prompt |
| `/set truncation ...` | Limit the display length of values |
| `/set format ...` | Customize feedback formatting |
| `/set indent <number>` | Set the number of spaces for automatic indentation |

### Feedback Mode

JShell has built-in modes:

- `verbose`: displays detailed information.
- `normal`: standard level of output.
- `concise`: compact output.
- `silent`: minimal feedback.

You can choose a mode at startup:

~~~bash
jshell --feedback concise
~~~

Or change it during a session:

~~~text
/set feedback concise
~~~

Feedback mode only changes how JShell presents results and messages. It does not change the execution semantics of Java snippets.

### Startup Definitions

`/set start <file>` sets the startup snippets and commands. When JShell starts, those definitions are loaded as part of initialization.

At the command-line level, you can use:

~~~bash
jshell --startup startup.jsh
~~~

Or disable the default startup:

~~~bash
jshell --no-startup
~~~

A startup file is suitable for declaring imports, helper methods, or utility configurations commonly used during learning and experimentation. Avoid putting operations with major side effects into startup if you do not want them to run every time you open JShell or reset.

## 10. Example Workflow: Experimenting, Saving, and Reloading

Suppose you are testing a simple tax calculation function.

Open JShell:

~~~bash
jshell --feedback concise
~~~

Enter the snippets:

~~~java
double taxRate = 0.1;

double totalWithTax(double price) {
    return price * (1 + taxRate);
}

totalWithTax(200)
~~~

Result:

~~~text
$3 ==> 220.0
~~~

Check what is currently active:

~~~text
/list
/vars
/methods
~~~

Save the code:

~~~text
/save tax-demo.jsh
~~~

Exit:

~~~text
/exit
~~~

Reopen and restore:

~~~bash
jshell --feedback concise
~~~

~~~text
/open tax-demo.jsh
~~~

After loading, you can continue:

~~~text
totalWithTax(500)
~~~

The return value is `550.0`. The temporary variable name JShell generates to display the result depends on the number of snippets already in the session.

This workflow works well for trying out APIs, testing expressions, writing small helper methods, and saving useful code snippets as JShell scripts.

## 11. Common Mistakes When Using Slash Commands

### Typing Slash Commands as Java Code

For example, `/vars` is a JShell command. If you place it inside a Java method body or a `.java` file, the compiler will report a syntax error. Enter the command at the JShell prompt or place it in a file loaded with `/open`.

### Using the Wrong Command Name

Not every JDK tool option has a corresponding slash command. For example, JShell does not have a `/classpath` command; use `/env -class-path` in a session or `--class-path` at startup.

When unsure, use `/help` to see the list of commands supported by the current version.

### Confusing /list with /history

`/list` focuses on snippets and code state. `/history` records the sequence of snippets and commands entered. To save active code, use `/save`; to save the entire input history, use `/save -history`.

### Using /drop and Expecting History to Disappear

`/drop` only makes a snippet inactive. It can still appear in `/list -all` and in the history. To view the current active state, use `/list`; to inspect all snippets, use `/list -all`.

### Losing Code After /reset

`/reset` clears entered code from the execution state. Use `/save` before resetting if you want to keep your active snippets.

### /reload Causing Operations to Run Twice

`/reload` replays valid snippets. If the code writes files, updates a database, or calls an API, those actions may be repeated. Check the history and side effects before reloading.

### /open or /save Cannot Find a File

Paths are resolved according to the operating system environment and the current working directory. Use the exact path, check read/write permissions, and avoid mixing up path separators. If a path contains spaces, check the syntax supported by your JShell version; do not assume every slash command handles quotes the same way as a shell.

### Editor Does Not Open

Check `/set editor`, then check the `JSHELLEDITOR`, `VISUAL`, and `EDITOR` environment variables. If no external editor is configured, JShell may use its simple built-in editor.

## 12. Quick Reference Table

| Need | Command |
|---|---|
| View all help | `/help` or `/?` |
| View help for one command | `/help /list` |
| View active snippets | `/list` |
| View old/failed/dropped snippets too | `/list -all` |
| View variables | `/vars` |
| View methods | `/methods` |
| View types | `/types` |
| View imports | `/imports` |
| View input history | `/history` |
| Edit a snippet | `/edit <id>` |
| Drop a snippet | `/drop <id>` |
| Save active code | `/save file.jsh` |
| Save full history | `/save -history file.txt` |
| Load a file | `/open file.jsh` |
| Rerun the most recent snippet | `/!` |
| Rerun by ID | `/<id>` |
| Change classpath | `/env -class-path <path>` |
| View evaluation context | `/env` |
| Replay snippets | `/reload` |
| Restore previous history | `/reload -restore` |
| Clear session state | `/reset` |
| Change feedback | `/set feedback concise` |
| Exit JShell | `/exit` |

## 13. Checklist for Using JShell Effectively

- [ ] Use `/help` to verify command syntax on your current JDK.
- [ ] Use `/list`, `/vars`, `/methods`, and `/types` to understand the session state.
- [ ] Use `/history` to find previously entered actions.
- [ ] Use `/edit` to modify long snippets instead of retyping them repeatedly.
- [ ] Use `/drop` to remove experimental declarations that are no longer needed.
- [ ] Use `/save` to save active snippets before resetting.
- [ ] Use `/open` to reload scripts in the proper dependency order.
- [ ] Use `/env` when you need to change the classpath or module path.
- [ ] Check for side effects before using `/!`, rerun, or `/reload`.
- [ ] Use `/set feedback` and `/set start` to tailor your workflow experience.
- [ ] Use `/exit` to end the session after saving any code you want to keep.
