# Saving and Loading Sessions in JShell

## 1. What Is a Session in JShell?

**JShell** is the JDK's interactive REPL (Read-Eval-Print Loop) tool. You can enter expressions, declare variables, methods, and classes, and run them immediately without creating a full Java project.

A **JShell session** is the working state inside a running JShell process. This state consists of the snippets you have entered or loaded, the active declarations, and the execution state that JShell maintains within that process.

For example, within the same session:

~~~java
String project = "Java";
int version = 17;

int nextVersion(int current) {
    return current + 1;
}

nextVersion(version)
~~~

Declarations can be used in subsequent snippets. If you exit JShell, the process terminates and the in-memory runtime state is lost.

To continue your work in a later run, JShell provides commands to save source or history and reload the content. The most important commands are:

- **/save:** saves the source of the active snippets.
- **/save -history:** saves the sequential history of commands and snippets entered in the current session.
- **/open:** reads a file or URL as JShell input.
- **/reload:** resets and replays the valid history in the current session.
- **/reload -restore:** restores the history from before a reset, reload, or env change within the same process.

It is important to distinguish saving source for replay from capturing a full JVM memory dump. JShell saves re-executable content; it does not create a snapshot of the object graph, threads, sockets, file handles, or external state.

## 2. Starting JShell and Creating a Session

Check your JDK and JShell versions:

~~~bash
java --version
jshell --version
~~~

Start interactive mode:

~~~bash
jshell
~~~

You can select a feedback mode right at startup:

~~~bash
jshell --feedback concise
~~~

Available feedback modes include:

| Mode | Purpose |
|---|---|
| silent | Minimizes JShell feedback messages; output printed by your code still appears. |
| concise | Brief feedback, suitable for everyday work. |
| normal | Default feedback, balancing detail and brevity. |
| verbose | Displays more detailed information about snippets and results. |

Inside a session, enter snippets line by line or as blocks:

~~~java
String course = "Java Core";
int lessons = 12;

int remaining(int completed) {
    return lessons - completed;
}

System.out.println(course + ": " + remaining(5) + " lessons left");
~~~

JShell evaluates a snippet as soon as it receives a complete declaration or expression. Declared variables, methods, and classes can be used in later snippets within the same session.

Slash commands such as /list, /save, /open, and /exit are JShell control commands, not Java statements. Do not put a semicolon at the end of a slash command.

## 3. Viewing Snippets and History Before Saving

Before saving, you should inspect what content currently exists.

Command:

~~~text
/list
~~~

/list displays the active snippets along with their snippet IDs. These IDs are useful when you want to save only part of a session.

View all snippets, including failed, overwritten, dropped, and startup snippets:

~~~text
/list -all
~~~

View the input history in the current session:

~~~text
/history
~~~

View the history from the current session and previous sessions:

~~~text
/history -all
~~~

The /list and /history commands answer two different questions:

- /list shows which snippets currently exist or have existed.
- /history shows the sequence of commands and snippets entered over time.

A snippet may be edited or replaced during your work. Therefore, the content in the history does not necessarily match the list of active snippets. Choose the type of data you want to save before using /save.

## 4. Saving Active Snippets with /save

Basic syntax:

~~~text
/save <file>
~~~

This command saves the source of active snippets to the specified file. For example:

~~~text
/save java-session.jsh
~~~

The file **java-session.jsh** contains source code that can be reloaded in JShell. The .jsh extension is a recognizable convention for JShell scripts; other filenames can still be used if the content is appropriate.

The regular /save command focuses on currently active snippets. It is suitable when you want to keep useful declarations for continued use, such as:

- Required imports.
- Variables and constants for experimentation.
- Helper methods.
- Classes or records declared in the REPL.
- Expressions or statements that you want to run again.

If a snippet has been replaced, dropped, or failed to compile, it is not part of the normal active snippet set. When you need to keep those cases as well, see /save -all or /save -history.

Note: /save writes source to the file path received by JShell. Check your current working directory to know where the file is created; relative paths are resolved from the working directory of the JShell process.

## 5. Saving All Snippets with /save -all

Syntax:

~~~text
/save -all <file>
~~~

The -all option saves the source of all snippets, including:

- Active snippets.
- Overwritten snippets.
- Failed or invalid snippets.
- Dropped snippets.
- Startup code.

Example:

~~~text
/save java-session-all.jsh
/save -all java-session-complete.jsh
~~~

The first command saves only the active snippet set; the second additionally saves inactive snippets and startup code.

Use -all when you need a complete record to review how an experiment unfolded. This file may contain invalid source or duplicate declarations, so it is not always a clean script to reload in a new session.

If your goal is to create a file that can be re-run reliably, prefer /save for active snippets, then review the file and check the declaration order before using it.

## 6. Saving Command History with /save -history

Syntax:

~~~text
/save -history <file>
~~~

Example:

~~~text
/save -history java-session-history.jsh
~~~

The -history option saves the sequential history of commands and snippets entered since the JShell tool was launched in the current session.

Key differences:

| Save Option | Content |
|---|---|
| /save file | Source of active snippets. |
| /save -all file | Source of all snippets, including failed, overwritten, dropped, and startup. |
| /save -history file | Sequential history of commands and snippets entered in the current session. |
| /save -start file | Current startup definitions. |

History is useful when you need to reproduce an experimentation process, including adjustments and slash commands. However, it may contain control commands, failed snippets, file-writing operations, or external actions. Read and review the history file before reloading it.

The /history -all command can display history from previous sessions, whereas /save -history is documented to save the history since the current JShell tool instance was launched. Do not assume a single /save -history call will export the entire history of every JShell process ever run.

## 7. Saving One or a Group of Snippets by ID

If you only want to save part of a session, use snippet IDs:

~~~text
/save <id> <file>
~~~

For example, view the IDs:

~~~text
/list
~~~

Then save a single snippet:

~~~text
/save 3 selected-snippet.jsh
~~~

You can save multiple IDs or an ID range:

~~~text
/save 1-4 selected-snippets.jsh
~~~

This approach is useful when a session has many experiments but only a subset of declarations needs to be shared. Before choosing IDs, check /list to avoid accidentally saving an old or inactive snippet.

IDs are specific to a given session. Do not assume a snippet's ID will remain the same after opening the file in a new session, because JShell assigns snippet IDs as it loads and re-evaluates them.

## 8. Loading Files with /open

Syntax:

~~~text
/open <file>
~~~

Example:

~~~text
/open java-session.jsh
~~~

JShell reads the file and processes its contents as tool input. The file can contain source snippets and valid JShell commands. Declarations are evaluated in the order they appear in the file.

The /open command also supports URLs:

~~~text
/open https://example.org/scripts/java-session.jsh
~~~

When opening a URL, JShell downloads the content and uses it as input. Only open files or URLs from trusted sources, because Java snippets and JShell commands can execute code in your process.

You can load files when starting JShell:

~~~bash
jshell java-session.jsh
~~~

Or combine this with a feedback mode:

~~~bash
jshell --feedback silent java-session.jsh
~~~

This is convenient for scripts that need to run from scratch or for simple smoke tests. If you want to load content into an already open JShell instance, use /open instead of starting a new process.

If the file redeclares a variable, method, or class name that already exists in the current session, JShell may report an error or produce an unexpected state. When replaying an entire file, it is better to use a new session or reset the session before loading.

## 9. Complete Example: Saving and Reopening a Session

Create an interactive session:

~~~bash
jshell --feedback concise
~~~

Enter the snippets:

~~~java
String project = "JShell";
int attempts = 3;

int retryDelay(int attempt) {
    return attempt * 2;
}

System.out.println(project + " / delay=" + retryDelay(attempts));
~~~

Save the active snippets:

~~~text
/save jshell-session.jsh
~~~

Exit the session:

~~~text
/exit
~~~

Open a new JShell process and load the saved file:

~~~bash
jshell --feedback silent jshell-session.jsh
~~~

Stdout of the example:

~~~text
JShell / delay=6
~~~

This example was verified with JShell 24.0.2. The script file contains Java declarations and statements; when the file is opened, JShell re-evaluates them and the println statement prints the result.

You can do the same inside a new session with the command:

~~~text
/open jshell-session.jsh
~~~

The key point to remember is that the result is recreated by executing the source. This is not a saved snapshot of variable values from the old process.

## 10. Restoring History in the Same Process with /reload

/reload is not a command for reading a saved file. It operates on the snippet history of the current JShell tool instance.

Syntax:

~~~text
/reload
~~~

This command resets the code and execution state, then replays the valid snippets and /drop commands in the order they were entered since JShell was launched or since the most recent /reset or /reload.

You can use it when you want to re-run declarations from scratch after experimenting or when the current state is no longer consistent.

The -restore option:

~~~text
/reload -restore
~~~

-restore restores and replays the previous history within the same process, starting from when JShell was launched or from the most recent /reset, /reload, or /env point. It is useful when you want to recover the session state from before a reset or an evaluation context change.

You can reduce feedback during replay:

~~~text
/reload -quiet
/reload -restore -quiet
~~~

The -quiet option hides normal replay output, though errors are still displayed.

You cannot use /reload after completely exiting an old process to recover that process's memory. To continue in a new process, save your source or history to a file and then use /open or pass the file at startup.

## 11. Differences Between /reset, /reload, and /reload -restore

These three commands have different effects:

| Command | Effect |
|---|---|
| /reset | Clears entered code, restarts the execution state, and re-runs startup code. |
| /reload | Resets and then replays valid history since the most recent checkpoint. |
| /reload -restore | Replays the history from before the most recent reset, reload, or env change to restore the previous session in the same process. |

Example:

~~~text
int base = 10;
base * 2
/reset
~~~

After /reset, the `base` declaration is no longer in the current session. If you need to restore the snippets from before the reset, you can use:

~~~text
/reload -restore
~~~

The /reset command discards existing declarations and restarts the execution state. If you are not sure you can rebuild the state, save the source before resetting.

Do not treat /reload as an undo operation for all side effects. If a snippet wrote a file, sent a network request, updated a database, or modified an external system, replaying may perform that action again.

## 12. Saving Startup Definitions and Reusing Them at Launch

JShell has startup definitions, which are declarations loaded when the tool starts. You can save the current startup definitions with:

~~~text
/save -start jshell-startup.jsh
~~~

Then use the startup file for a single launch:

~~~bash
jshell --startup jshell-startup.jsh
~~~

The --startup option replaces the default startup definitions for that run. If you want to skip the default startup definitions without providing a replacement file, you can use:

~~~bash
jshell --no-startup
~~~

Startup files are well suited for helper imports, methods, or classes used repeatedly across multiple work sessions. For example, a team can prepare a startup file containing helpers for formatting JSON or generating test data.

Startup definitions differ from session files:

- A startup file prepares the shared declaration environment when JShell starts.
- A session file contains the snippets and commands for a specific lab exercise or task.
- A history file records the sequence of entered operations.

You should separate shared helpers from experimental commands that have side effects so that the startup file remains easy to reuse.

## 13. Reloading Sessions with Dependencies and Evaluation Context

A session file may use external libraries or modules. When reloading it, JShell must be started with the appropriate classpath or module path.

Example with a JAR library in the `lib` directory:

~~~bash
jshell --class-path "lib/example.jar" java-session.jsh
~~~

If there are multiple directories or JARs on Windows, use a semicolon to separate classpath entries:

~~~powershell
jshell --class-path "lib\one.jar;lib\two.jar" java-session.jsh
~~~

On Linux/macOS, the classpath separator is typically a colon:

~~~bash
jshell --class-path "lib/one.jar:lib/two.jar" java-session.jsh
~~~

With modules:

~~~bash
jshell --module-path mods --add-modules com.example.lib java-session.jsh
~~~

Beyond dependencies, pay attention to:

- The JDK version and APIs used by the snippets.
- Whether preview features are enabled with `--enable-preview`.
- JVM options for the JShell runtime.
- Compiler options passed with `-C`.
- Runtime options specifically for running snippets passed with `-R`.
- Working directory, environment variables, and resource files accessed by the snippets.

Example enabling preview features:

~~~bash
jshell --enable-preview --source 24 java-session.jsh
~~~

Depending on the JDK version, the source and preview options must match the release in use. Check `jshell --help` for your target JDK before using these options in automated scripts.

Not every evaluation context setting is saved in a `/save` file. When reopening, pass the classpath, module path, modules to resolve, and any required options again.

## 14. Designing Reusable Session Files

A good session file should have a clear structure and be runnable from top to bottom.

Example:

~~~java
// 1. Imports
import java.time.LocalDate;

// 2. Shared values
String projectName = "Java Core";
LocalDate today = LocalDate.now();

// 3. Helper methods
String label(String name) {
    return projectName + " / " + name;
}

// 4. Demonstration
System.out.println(label(today.toString()));
~~~

It is best to organize the file in this order:

1. Imports.
2. Constants and configuration variables.
3. Helper methods.
4. Supporting classes or records.
5. Practice snippets or demonstration statements.

If a session has multiple steps, you can split it into several files:

~~~text
jshell-lab/
├── 01-imports.jsh
├── 02-models.jsh
├── 03-helpers.jsh
└── 04-demo.jsh
~~~

Load them in order:

~~~text
/open 01-imports.jsh
/open 02-models.jsh
/open 03-helpers.jsh
/open 04-demo.jsh
~~~

Or pass multiple load files when starting JShell:

~~~bash
jshell --feedback concise 01-imports.jsh 02-models.jsh 03-helpers.jsh 04-demo.jsh
~~~

Only split into multiple files when doing so clarifies responsibilities and dependency order. For short sessions, a single file is usually easier to manage.

## 15. Side Effects and Safety When Replaying Sessions

Opening a file or replaying history means re-executing snippets. This matters if the session contains commands with external side effects.

Example:

~~~java
Files.writeString(Path.of("result.txt"), "done");
~~~

Every time this snippet runs, `result.txt` may be overwritten. A snippet that sends an HTTP request or writes to a database can also trigger new side effects when reopened.

Before using `/open`, `/reload`, or loading a history file, check:

- Are there commands that delete, overwrite, or move files?
- Are there requests sent to external services?
- Are there database insert, update, or delete operations?
- Does it send emails, messages, or trigger jobs?
- Does it read tokens, passwords, or personal data from files or environment variables?
- Do any snippets depend on state that only existed in a previous run?

Do not store secrets directly in session or history files. Use environment variables or an appropriate secret provisioning mechanism, and protect file permissions on session files.

Do not open JShell scripts from untrusted URLs. Downloaded content may contain Java code and control commands; opening the file can execute them with the current user's permissions.

## 16. Common Errors When Saving and Loading Sessions

| Symptom | Possible Cause | Resolution |
|---|---|---|
| /open cannot find the file | Relative path is resolved from a different working directory than expected. | Check the current directory or use a full path. |
| File loads, but a variable does not exist | The variable declaration snippet failed or was not evaluated successfully. | Check feedback, `/list`, and the file contents. |
| Method or class is declared twice | The file was opened with `/open` in a session that already had declarations with the same names. | Use a new session or `/reset` before loading. |
| /save does not include a recently tried snippet | The snippet failed, was dropped, or is no longer active. | Use `/list -all` or `/save -history` if you need to keep the history. |
| Reloading a history file produces many errors | History contains old snippets, control commands, or experimental code that is no longer valid. | Review the history file and create a clean session script. |
| Reopened session cannot find libraries | Classpath or module path was not passed again. | Launch with the required `--class-path`, `--module-path`, and `--add-modules` options. |
| Output differs from the previous run | JDK, dependencies, working directory, external data, or time has changed. | Document the required environment and input data clearly. |
| /reload does not restore after closing JShell | /reload only uses the history of the current process. | Save source or history before `/exit` and reload it in a new process. |
| Replay writes files or updates data again | The snippet has side effects. | Review the source, use test data, and design idempotent operations. |
| Startup helpers do not appear | JShell was started with `--no-startup` or a different startup file. | Check `--startup` and your startup configuration. |
| Snippet IDs changed | IDs are reassigned when the file is loaded in a different session. | Look up the new IDs using `/list` after loading. |

## 17. Workflow for Saving, Verifying, and Restoring Sessions

A safe workflow for everyday work:

1. Use `/list` to inspect active snippets.
2. Use `/history` if you need to review the sequence of operations.
3. Choose `/save` to save active source or `/save -history` to save the experimentation process.
4. Inspect the saved file, removing unnecessary commands and any secrets before sharing.
5. Record the JDK version, dependencies, classpath/module path, and required options.
6. Open a new JShell process and load the file with `jshell file.jsh` or `/open file.jsh`.
7. Verify that snippets load cleanly and demonstration outputs are correct.
8. Only use `/reload -restore` when you need to recover history within the same process.
9. After editing a session file, run it from scratch to confirm it can reproduce the results.
10. Store session files in version control if they serve as lab materials or shared procedures.

For scripts used in CI, prefer passing the file at startup, choosing an appropriate feedback mode, and checking the exit code. Avoid relying on interactive prompts or manual steps.

## 18. Checklist for Working with JShell Sessions

- [ ] Distinguished runtime session state from saved source/history files.
- [ ] Used `/list` and `/history` to understand what needs to be saved.
- [ ] Chose appropriately between `/save`, `/save -all`, `/save -history`, and `/save -start`.
- [ ] Used the correct snippet IDs when saving only a partial session.
- [ ] Understood that `/open` loads a file or URL as JShell input.
- [ ] Reviewed the file before replaying because snippets may re-execute side effects.
- [ ] Distinguished `/reload` from `/reload -restore` and `/reset`.
- [ ] Understood that `/reload` only works within the current process.
- [ ] Passed the required classpath/module path and options again.
- [ ] Distinguished startup files from session files.
- [ ] Avoided storing secrets in session or history files.
- [ ] Reopened the file in a new session to verify reproducibility.

JShell saves and loads sessions by storing source code or history and re-evaluating it in a process. By choosing the right `/save` option, reviewing files before `/open`, and preserving the necessary dependencies and evaluation context, you can reuse Java experiments in a controlled way.