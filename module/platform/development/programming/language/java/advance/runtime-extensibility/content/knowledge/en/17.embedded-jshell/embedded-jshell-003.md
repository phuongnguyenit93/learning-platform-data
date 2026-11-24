# Analyzing Complete Code Snippets Before Calling `JShell.eval`

## 1. Goal: Never Evaluate an Incomplete Java Fragment

When embedding JShell in a Java application, the host typically receives code line by line from a terminal, editor, web UI, or a string containing multiple declarations. Not every line is an independently runnable Java snippet. For instance, a user might enter a method across three lines:

~~~java
int square(int x) {
    return x * x;
}
~~~

If the host calls `JShell.eval("int square(int x) {")` as soon as it receives the first line, it sends **incomplete code** into the engine. Conversely, if the host concatenates an entire file containing multiple statements and calls `eval` once, that is also unreliable: by the API contract, `eval(String)` expects **one complete snippet** (a statement, expression, import, variable declaration, method, or class).

The API designed for this scenario is:

~~~java
SourceCodeAnalysis analysis = jshell.sourceCodeAnalysis();
SourceCodeAnalysis.CompletionInfo info =
        analysis.analyzeCompletion(pendingSource);
~~~

This is an illustrative snippet; `jshell` and `pendingSource` must exist beforehand. `SourceCodeAnalysis` finds the boundary of the **first snippet**, reports whether it is complete or requires more input, and returns the remaining text for the next iteration. Only when a qualified snippet is ready does the host pass it to `JShell.eval`.

After this lesson, you will be able to build a REPL buffer that is safe in terms of **syntactic splitting**: accumulating multi-line code, accepting multiple snippets in a single submission, understanding the six completeness states, reading `source()`/`remaining()`, handling eval errors, and avoiding confusing "syntactically complete" with "semantically valid or safe to run."

## 2. Three Key Objects in the JShell API

### 2.1. `JShell` Holds Evaluation State

`jdk.jshell.JShell` is the engine holding definitions and values from prior calls. A shell that has evaluated `int n = 7;` can use `n` in the next snippet:

~~~java
// Illustration of two calls, not a standalone program.
jshell.eval("int n = 7;");
jshell.eval("n * 3;");
~~~

`JShell.eval` returns `List<SnippetEvent>`, rather than returning the expression value directly. For each event, inspect `status()`, `value()` (if present), `exception()`, and diagnostics when a snippet is rejected. A single `eval` call can trigger secondary events on dependent snippets when state changes, so never assume the list always has a single element.

### 2.2. `SourceCodeAnalysis` Analyzes Without Executing

Obtain the analyzer from the exact shell instance you will use for `eval`:

~~~java
SourceCodeAnalysis analysis = jshell.sourceCodeAnalysis();
~~~

`analysis.analyzeCompletion(text)` locates the **first snippet** in `text` and analyzes its completeness. This analysis **does not execute** Java statements, does not define variables or methods in JShell, and does not imply that all referenced type or method names are valid.

Other `SourceCodeAnalysis` methods such as `completionSuggestions` or `sourceToSnippets` solve different problems. Specifically, `sourceToSnippets` can produce `Snippet` objects for previewing, but it does not replace the input-splitting loop for `eval` and does not install declarations into shell state.

### 2.3. `CompletionInfo` Is the Analysis Result

`SourceCodeAnalysis.CompletionInfo` provides three essential methods:

| Method | Question Answered |
| --- | --- |
| `completeness()` | Is the first snippet complete, does it need more code, or was analysis inconclusive? |
| `source()` | The string of the **first snippet** to pass to `eval`; a semicolon may have been appended if needed |
| `remaining()` | The **remaining input after the first snippet**, which must be fed back into the analyzer |

Given `"int a = 1; int b = 2;"`, we should not feed the entire string into a single `eval` call. Instead, analyze and extract `int a = 1;`; keep the remainder and analyze `int b = 2;` on the next iteration.

**Important:** never replace `source()` with `substring` slicing at `;` or `}`. The parser understands semicolons inside `for (...)`, braces inside strings and comments, text blocks, and Java syntax; plain text splitting easily corrupts code.

## 3. The Six `SourceCodeAnalysis.Completeness` Values

`Completeness` is an enum inside `SourceCodeAnalysis`. Distinguishing its values tells the host **when to wait, when to eval**, and when to report input errors.

| Value | Meaning | Typical Behavior |
| --- | --- | --- |
| `COMPLETE` | Input begins with a snippet that is already complete as written | Take `source()` and call `eval` |
| `COMPLETE_WITH_SEMI` | The snippet becomes complete if a trailing `;` is added | Depends on UI policy: accept `source()` (with `;` appended) or wait for user confirmation |
| `DEFINITELY_INCOMPLETE` | More source is strictly required; adding `;` is not enough | **Wait** for more input, keep buffer |
| `CONSIDERED_INCOMPLETE` | Cases such as a statement ending with an unterminated empty statement; auto-appending `;` rarely matches intent | **Wait** for more input, do not force `;` |
| `EMPTY` | Only whitespace/comments or no snippet present | Do not eval; processed blank input may be discarded |
| `UNKNOWN` | Analysis was blocked by malformed code; completeness cannot be determined | The API **treats it as complete** so `eval` can emit diagnostics; do not treat this as valid code |

`DEFINITELY_INCOMPLETE`, `CONSIDERED_INCOMPLETE`, and `EMPTY` are **incomplete** according to `isComplete()`. Conversely, `UNKNOWN` is treated as complete so the engine can report accurate errors. Therefore:

~~~java
// Common rule for a REPL authorized to evaluate input:
if (info.completeness().isComplete()) {
    jshell.eval(info.source());
}
~~~

This snippet illustrates only the condition; it **does not yet handle `remaining`, whitespace, diagnostics, or security policies**. The runnable example in section 5 handles all of those properly.

Two common cases:

- `"class Counter {"` or `"int x ="`: required syntax is missing; more lines are needed.
- `"1 + 2"`: can be completed by appending `;`. `source()` will hold the completed code ready to evaluate if policy allows.

Completeness analysis is a **boundary check**, not a type-checking compiler, not an authorization step, and not a check for whether runtime exceptions will occur.

## 4. Pre-`eval` Buffering Algorithm

The host should maintain a dedicated `pending` buffer for each JShell session. Whenever a new line or batch arrives, the host does:

1. **Append** the new source to `pending`, preserving newlines when joining lines. Never send just the first line of a method or class to `eval`.
2. Call `analyzeCompletion(pending)`; if completeness is `EMPTY`, clear the whitespace/comments that contain no snippet; if not complete, keep the buffer and wait.
3. If complete, take **`info.source()`**, not the entire buffer. Pass that exact string to `jshell.eval`.
4. Process **all** returned `SnippetEvent`s: `VALID`, `REJECTED`, recoverable statuses, expression values, exceptions, diagnostics, and any needed indirect updates.
5. Set `pending = info.remaining()` and loop back to step 2 to process subsequent snippets **within the same batch**.
6. Guard against infinite loops: verify each extraction makes forward progress, cap buffer size and snippet count, and close JShell when the session ends.

`COMPLETE_WITH_SEMI` can automatically append a semicolon. This does **not always match user intent** if they plan to enter an operator or continue an expression on the next line. CLIs often commit on Enter, whereas multi-line editors may use a Run button or Ctrl+Enter as the boundary. Define clearly when the host permits auto-completing with `;`. The example in section 5 uses inputs that already end with `;` to keep stdout deterministic.

### Do Not Parse Manually by Counting Braces

Techniques such as `source.endsWith(";")`, counting `{`/`}`, or splitting with `String.split(";")` fail on valid Java code:

~~~java
String s = "};";
// The } and ; above are inside string literal content.
for (int i = 0; i < 2; i++) {
    System.out.println(i);
}
~~~

These are **two illustrative snippets**. The `for` statement contains two `;` characters inside its header and a method call inside its body; input cannot be split on arbitrary `;` characters. Likewise, comments, escape sequences, annotations, generic types, lambdas, and text blocks make regex-based splitting unreliable.

## 5. Runnable Java 17 Example: Line-by-Line Analysis Before `eval`

The program below compiles and runs on **JDK 17 or newer with the `jdk.jshell` module**. It creates a `JShell`, feeds input line by line, waits for a method's closing `}`, splits two snippets on the same line, and prints the status and value returned by the engine. Only `source()` from a complete snippet is passed to `eval`.

### 5.1. File Creation and Structure

~~~text
jshell-completion-demo/
  src/
    CompletionGateDemo.java
  out/              (created during compilation)
~~~

**File `src/CompletionGateDemo.java`:**

~~~java
import java.util.List;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;
import jdk.jshell.SourceCodeAnalysis;

public final class CompletionGateDemo {
    private CompletionGateDemo() {
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            SourceCodeAnalysis analysis = shell.sourceCodeAnalysis();
            StringBuilder pending = new StringBuilder();

            List<String> lines = List.of(
                    "int square(int x) {",
                    "    return x * x;",
                    "}",
                    "square(4); int n = 7;",
                    "n + square(2);"
            );

            for (String line : lines) {
                accept(line, pending, shell, analysis);
            }

            if (!pending.toString().isBlank()) {
                System.out.println("incomplete input at EOF");
            }
        }
    }

    private static void accept(
            String line,
            StringBuilder pending,
            JShell shell,
            SourceCodeAnalysis analysis) {

        pending.append(line).append('\n');

        while (true) {
            SourceCodeAnalysis.CompletionInfo info =
                    analysis.analyzeCompletion(pending.toString());
            SourceCodeAnalysis.Completeness state =
                    info.completeness();

            if (state == SourceCodeAnalysis.Completeness.EMPTY) {
                pending.setLength(0);
                return;
            }

            if (!state.isComplete()) {
                System.out.println("waiting");
                return;
            }

            String snippet = info.source();
            String rest = info.remaining();
            if (snippet == null || snippet.isBlank()) {
                throw new IllegalStateException(
                        "Analyzer returned an empty complete snippet");
            }
            if (rest == null) {
                rest = "";
            }
            if (rest.equals(pending.toString())) {
                throw new IllegalStateException(
                        "No progress while extracting a snippet");
            }

            pending.setLength(0);
            pending.append(rest);

            for (SnippetEvent event : shell.eval(snippet)) {
                // Indirect events have causeSnippet != null.
                if (event.causeSnippet() != null) {
                    continue;
                }

                System.out.println("status=" + event.status());
                if (event.value() != null) {
                    System.out.println("value=" + event.value());
                }
                if (event.exception() != null) {
                    System.out.println(
                            "exception=" +
                            event.exception().getClass().getSimpleName());
                }
                if (event.status() == Snippet.Status.REJECTED) {
                    shell.diagnostics(event.snippet())
                            .forEach(d -> System.err.println(
                                    "diagnostic=" + d.getMessage(null)));
                }
            }
        }
    }
}
~~~

**Why does this code split snippets properly?**

- `pending` holds consecutive lines of the method until `analyzeCompletion` returns a state where `isComplete() == true`.
- `info.source()` is the snippet **identified by the parser**; `eval` never receives the raw `pending` buffer containing multiple snippets.
- `info.remaining()` is retained and analyzed in the `while` loop, because the fourth line contains both `square(4);` and `int n = 7;`.
- `EMPTY` clears leftover whitespace after all snippets are consumed.
- `isComplete()` lets `UNKNOWN` proceed to `eval` for error reporting. In production systems, you may reject earlier depending on policy, but never label `UNKNOWN` as "compiled cleanly."
- `SnippetEvent` can represent dependent updates; the demo prints only primary events (`causeSnippet() == null`). A tool that needs to display all changes should not skip secondary events like this.
- `try (JShell shell = ...)` closes the JShell session upon completion, avoiding leaking the engine and execution resources past the application lifecycle.

### 5.2. Compiling and Running

Open a terminal in the `jshell-completion-demo` directory after creating the source file above:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -d out src/CompletionGateDemo.java
java -cp out CompletionGateDemo
~~~

If a minimal compiler/launcher environment does not automatically resolve the `jdk.jshell` module, verify the runtime image includes it and configure root modules appropriately (e.g., `--add-modules jdk.jshell` on the launcher); on a full JDK 17, the example runs with the commands above.

**Stdout when snippets are complete and error-free:**

~~~text
waiting
waiting
status=VALID
status=VALID
value=16
status=VALID
value=7
status=VALID
value=11
~~~

The two `waiting` lines correspond to `"int square(int x) {"` and `"return x * x;"`: the method still lacks a closing `}`. The `"}"` line completes the method, so the engine defines it with status `VALID`. The line containing two snippets causes the `while` loop to evaluate them **separately**, yielding `16` for `square(4)` and `7` for variable `n`. The final evaluation computes `n + square(2) = 7 + 4 = 11`.

This stdout applies to this exact demo source and input; it is **not** a promise that every Java snippet emits a single event. In practice, updating a declaration can trigger secondary events; errors can produce diagnostics/exceptions or non-`VALID` statuses.

### 5.3. Step-by-Step Analysis Sequence

| New Input | Expected State | Call `eval`? | Remaining Buffer |
| --- | --- | --- | --- |
| `int square(int x) {` | `DEFINITELY_INCOMPLETE` | No | Keeps first line |
| `return x * x;` | Still missing method body closing | No | Keeps both lines |
| `}` | `COMPLETE` | Yes: method definition | No snippets left |
| `square(4); int n = 7;` | Two consecutive complete snippets | Yes: **two `eval` calls** | No snippets left |
| `n + square(2);` | `COMPLETE` | Yes: expression | No snippets left |

An important detail: evaluating in exact snippet order ensures `n` exists before `n + square(2)` is evaluated. Calling `eval` on the whole block or changing order produces different results and can cause errors.

## 6. Another Standalone Example: Checking Completeness Without `eval`

When designing an editor, the UI may want to show a "more input needed" indicator without running code yet. A small program (independent of section 5) can use `SourceCodeAnalysis` alone:

**File `src/InspectCompletion.java`:**

~~~java
import jdk.jshell.JShell;
import jdk.jshell.SourceCodeAnalysis;

public final class InspectCompletion {
    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            SourceCodeAnalysis analysis = shell.sourceCodeAnalysis();
            for (String source : new String[] {
                    "int x =",
                    "int x = 10;",
                    "x + 2"
            }) {
                SourceCodeAnalysis.CompletionInfo info =
                        analysis.analyzeCompletion(source);
                System.out.println(
                        "complete=" + info.completeness().isComplete()
                        + ", state=" + info.completeness());
            }
        }
    }
}
~~~

Run in the same demo directory after creating the file:

~~~bash
javac --release 17 -encoding UTF-8 -d out src/InspectCompletion.java
java -cp out InspectCompletion
~~~

**Expected stdout:**

~~~text
complete=false, state=DEFINITELY_INCOMPLETE
complete=true, state=COMPLETE
complete=true, state=COMPLETE_WITH_SEMI
~~~

`"int x ="` needs an expression after it; a `;` is not enough. `"int x = 10;"` is a complete declaration. `"x + 2"` is an expression that can be completed with a semicolon without changing internal syntax; this is a boundary check and **does not mean variable `x` already exists**, because this program never calls `eval`.

When writing tests, also check `source()` (e.g., in `COMPLETE_WITH_SEMI` where `;` has been appended) and `remaining()` for inputs with two snippets. Do not inspect only the status while ignoring the other two fields.

## 7. Distinguishing Complete, Valid, and Safe

These three properties are not equivalent:

1. **Complete:** the parser recognizes a snippet boundary; the code is structurally ready to pass to JShell for evaluation.
2. **Semantically valid:** the code is compiled and accepted by JShell in the current state (matching imports, variables, classpath, and methods). `analyzeCompletion` does not verify all of that.
3. **Safe to execute:** the code is permitted to run under application policy. "Valid" Java code can still write files, open network sockets, spawn threads, burn CPU, or invoke external code.

Example:

~~~java
missingMethod(42);
~~~

This is a **structurally complete snippet** that may still be rejected by JShell because `missingMethod` is undefined. In that case, check `SnippetEvent.status() == REJECTED` and `jshell.diagnostics(snippet)` to explain the error to the user; do not "fix" it by appending a semicolon or waiting for more input.

Another example:

~~~java
while (true) {
    // non-terminating loop unless stopped by the execution environment
}
~~~

This is also syntactically complete code, yet executing it can hang. The host needs appropriate timeouts, resource limits, cancellation, and isolation. `SourceCodeAnalysis` is **not a security filter**, and JShell is **not a sandbox** for untrusted code. Never automatically `eval` every HTTP request just because `isComplete()` returns true.

Several runtime behaviors to keep in mind:

- `JShell.eval` can throw `IllegalStateException` if the shell is already closed. Code inside a snippet can throw exceptions captured via `SnippetEvent.exception()` or cause the execution engine to reset or terminate depending on the scenario.
- A faulty declaration can emit a `REJECTED` event or a recoverable status if dependencies are unresolved. Do not infer from "eval was called" that the code executed successfully.
- If a snippet updates an earlier definition, JShell can emit `OVERWRITTEN` events or alter the status of dependent snippets; the tool must refresh its state view after processing all events.
- Commands like `/exit`, `/list`, and `/imports` are **`jshell` CLI commands**, not Java source snippets to pass directly to `JShell.eval`. The host must build its own command handler if it wants to support slash-command syntax.
- A JShell snippet is not wholly synonymous with a `.java` file containing a `package` declaration and multiple top-level declarations. When accepting whole files, consider the Java Compiler API rather than assuming `eval` handles an entire file as a compilation unit.

## 8. Edge Cases and Errors When Accumulating Input

### 8.1. Whitespace or Comments Only

If input contains only whitespace or comments, completeness may be `EMPTY`. The host should not send `eval("")` for a business-logic call. Depending on policy, discard input that produces no snippet, or retain comments if the editor needs to reconstruct the original text. In the example, `EMPTY` clears the buffer.

### 8.2. Unfinished Code at End of Session

If the user submits:

~~~java
class Report {
    int total() {
~~~

and ends input, the host must report an **incomplete snippet**, neither silently dropping the buffer nor automatically inserting closing `}` braces. The `CompletionGateDemo` example prints `incomplete input at EOF` if non-whitespace content remains in the buffer. In a real application, prompt for the remaining lines or let the user save a draft.

### 8.3. Auto-Appended Semicolons

If the input is `"1 + 2"`, `COMPLETE_WITH_SEMI` indicates the source becomes complete if a `;` is appended. `info.source()` returns the snippet ready for `eval`; do not blindly append a second semicolon.

For editors supporting multi-line editing, policy might require the user to click **Run** before allowing auto-semi, while pressing Enter simply inserts a newline to keep typing. Avoid prematurely evaluating an expression when the user intends to append another operator.

### 8.4. `UNKNOWN` Does Not Mean "Valid"

`UNKNOWN` is treated as complete by `isComplete()` so `eval` can emit errors. If the host wants to avoid executing unverified input, it can report an error or route to an isolated environment instead of calling `eval`. Never describe this status as "syntactically valid."

### 8.5. Strings and Text Blocks Containing Delimiters

Java syntax allows `;`, `{`, and `}` inside string literals and text blocks. The parser tracks token boundaries, whereas slicing via `indexOf(';')` cannot tell them apart. With text blocks (Java 17), `"""` delimiters can also span multiple lines; the buffer must preserve newlines verbatim.

### 8.6. Multiple Snippets and Errors in a Middle Snippet

A batch might contain `"int a = 1; missingMethod(); int b = 2;"`. Each piece must be extracted separately via `source()`/`remaining()`. If the second snippet is `REJECTED`, host policy determines whether to **continue** evaluating the third snippet or abort the batch on error. Never unconsciously treat evaluating the entire batch as an atomic transaction: JShell has already persisted state changes from snippets prior to the error.

### 8.7. Multi-Session and Concurrency

Never share a single `pending` buffer across different users or sessions. Each session should own its own `JShell`, analyzer, and buffer (or enforce strict synchronization and isolation). Avoid having two threads concurrently mutate the same `StringBuilder` and invoke `eval` in non-deterministic order. For multiple users, use per-shell queues/coordinators, timeouts, and explicit cancellation.

### 8.8. Input Size and Iteration Limits

Do not let `pending` grow unboundedly when a user submits an unclosed declaration. Enforce policy limits on bytes/characters, maximum snippets per request, and execution time. When finished, call `JShell.close()` to reclaim engine resources; do not retain `SnippetEvent`/`ClassLoader`/context objects beyond the session lifecycle without reason.

## 9. Testing and Checklist

A test suite for a host using `SourceCodeAnalysis` before `eval` should cover:

| Input | What to Verify |
| --- | --- |
| Multi-line method/class | Does not eval while closing braces are missing; evaluates once when complete |
| Two declarations on one line | Extracted twice and evaluated in order, not merged into one snippet |
| Expression without trailing `;` | `COMPLETE_WITH_SEMI` status and explicit auto-semi policy |
| Statement ending in `;` but missing an operand | Not mistaken for complete when the parser reports insufficient tokens |
| Whitespace, comments | Does not evaluate an empty snippet |
| String/text block containing `;` or `}` | Does not split inside tokens via character search |
| Type error or nonexistent method name | Completion does not replace diagnostics from `eval` |
| `UNKNOWN` | Not labeled "valid code" just because `isComplete` returns true |
| Multi-snippet batch with a failing middle snippet | Accurate boundaries and clear continue/stop policy |
| Incomplete input at EOF | Reports incomplete and retains/prompts user for completion |
| Multiple users or threads | Isolated sessions/buffers and consistent eval ordering |
| Untrusted code or infinite loop | Separate execution policy/limits, not relying on the parser |

Production checklist:

- [ ] Obtain `SourceCodeAnalysis` from the exact `JShell` instance in use.
- [ ] Accumulate source until `completeness().isComplete()` per policy; handle `EMPTY` and `UNKNOWN` accurately.
- [ ] Pass `info.source()` to a single `eval` call; never split manually via regex or semicolons.
- [ ] Loop with `info.remaining()` so remaining snippets in a batch are not dropped.
- [ ] Handle `SnippetEvent` status, value, exception, and diagnostics; never assume all are `VALID`.
- [ ] Do not treat completeness as type checking or security screening.
- [ ] Enforce limits on buffer size, snippet count, and execution time; maintain session/lifecycle boundaries.
- [ ] Close `JShell` and associated resources when finished.

**Conclusion:** In embedded JShell, `eval` is the step that **evaluates** a single snippet, not an accumulator for arbitrary source lines. `SourceCodeAnalysis.analyzeCompletion` determines when the **first complete snippet** is ready, `source()` gives the exact code to evaluate, and `remaining()` gives what must be analyzed next. Proper use of buffers, the completeness enum, and event diagnostics keeps a REPL application reliable across multi-line and multi-snippet inputs while preserving clear boundaries between parsing, compilation, and execution.
