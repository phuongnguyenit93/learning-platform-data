# Reading `SnippetEvent`, Status, Results, and Diagnostics in Embedded JShell

## 1. Four Distinct Sources of Information

Java has provided the JShell API since Java 9 via the `jdk.jshell` module. In an embedded application, calling `JShell.eval(String)` returns a `List<SnippetEvent>`, which can contain multiple events for a single input: an event for the new snippet plus events updating dependent snippets or overwritten older snippets.

To accurately present compilation and evaluation results, distinguish between:

- `SnippetEvent` describes a **state transition** of a snippet, including status, value, and exception.
- `Snippet` holds the identifier `id()`, source text `source()`, and kind `kind()`.
- `Diag` holds compiler diagnostics obtained via `JShell.diagnostics(snippet)`; there is no `event.getDiagnostics()` API.
- Output from `System.out`/`System.err` inside a snippet is routed through JShell's configured streams and is not synonymous with `event.value()`.

## 2. `SnippetEvent` Getters

| Getter | Meaning | When Might Something Be Absent? |
| --- | --- | --- |
| `snippet()` | The snippet associated with the event | Read to correlate UI/session state |
| `status()` | Status **after** the event | Must be read for every event |
| `previousStatus()` | Status **before** the event | Can be `NONEXISTENT` for a new snippet |
| `causeSnippet()` | Snippet that triggered an indirect update | `null` for direct evaluation |
| `isSignatureChange()` | Whether the snippet's signature changed | Not a measure of runtime success |
| `value()` | String representation of result when present | `null` for imports, methods, or statements without a value |
| `exception()` | Error thrown while running the snippet | `null` even when compilation is rejected |

**`status() == VALID` does not guarantee the code ran without error**: an expression that compiles cleanly can still throw an exception at runtime. Likewise, `value() == null` does not mean compilation failed.

## 3. `Snippet.Status` Values

- `VALID`: the snippet was accepted and is active.
- `RECOVERABLE_DEFINED`: the declaration has missing references but could still be defined/recovered once dependencies are supplied.
- `RECOVERABLE_NOT_DEFINED`: the declaration cannot be fully defined yet due to missing dependencies; still recoverable.
- `REJECTED`: the snippet was rejected by syntax/type checks or compilation rules.
- `OVERWRITTEN`: an older snippet was replaced by a new declaration.
- `DROPPED`: the snippet was removed via a drop operation.
- `NONEXISTENT`: the snippet does not exist in the referenced state.

These are statuses of **snippets in JShell state**, not a single `success` boolean. A single `eval` call can affect multiple snippets; consumers must iterate over the entire event list.

## 4. Runnable Java 17+ Example

The following example creates a JShell instance and evaluates a variable, an expression, and a compile error. The program prints kind/status/value and the number of error diagnostics. No extra JavaScript engine or Nashorn installation is needed; this is **JShell Java code**, not JSR 223.

File `EmbeddedJShellDemo.java`:

```java
import jdk.jshell.Diag;
import jdk.jshell.JShell;
import jdk.jshell.Snippet;
import jdk.jshell.SnippetEvent;
import java.util.List;

public final class EmbeddedJShellDemo {
    static void inspect(JShell shell, String code) {
        System.out.println("INPUT: " + code);
        List<SnippetEvent> events = shell.eval(code);
        for (SnippetEvent event : events) {
            Snippet snippet = event.snippet();
            System.out.println("  kind=" + snippet.kind()
                    + ", status=" + event.status());
            if (event.value() != null) {
                System.out.println("  value=" + event.value());
            }
            if (event.exception() != null) {
                System.out.println("  exception="
                        + event.exception().getClass().getSimpleName());
            }
            long errors = shell.diagnostics(snippet)
                    .filter(Diag::isError).count();
            System.out.println("  errors=" + errors);
        }
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            inspect(shell, "int x = 10;");
            inspect(shell, "x + 5");
            inspect(shell, "int broken = missingName;");
        }
    }
}
```

Run on JDK 17+ with `jdk.jshell`:

```bash
javac --add-modules jdk.jshell EmbeddedJShellDemo.java
java --add-modules jdk.jshell EmbeddedJShellDemo
```

Typical output on JDK 17:

```text
INPUT: int x = 10;
  kind=VAR, status=VALID
  value=10
  errors=0
INPUT: x + 5
  kind=VAR, status=VALID
  value=15
  errors=0
INPUT: int broken = missingName;
  kind=VAR, status=REJECTED
  errors=1
```

JShell can create a scratch variable when evaluating the expression `x + 5`, which is why `kind` is `VAR` above. Exact compiler messages can vary across JDK versions and locales. The example intentionally counts errors instead of comparing message strings.

## 5. Reading Diagnostics with `Diag`

Standard API for retrieving diagnostics:

```java
shell.diagnostics(snippet).forEach(diag -> {
    System.out.println((diag.isError() ? "error" : "warning")
            + ": " + diag.getMessage(java.util.Locale.ROOT));
    System.out.println("start=" + diag.getStartPosition()
            + ", end=" + diag.getEndPosition());
});
```

This is an **illustrative snippet inside a method** that already has `JShell shell` and `Snippet snippet`, not a standalone program. `Diag.getStartPosition()`, `getEndPosition()`, and `getPosition()` return offsets within the snippet's source, or `-1` if no position applies. Do not treat offsets as line numbers.

Example helper mapping an offset to line/column in UTF-16 code units of Java source (without special handling for tab widths, grapheme clusters, or source preprocessing):

```java
static String lineColumn(String source, long offset) {
    if (offset < 0 || offset > source.length()) return "unknown";
    int line = 1;
    int column = 1;
    for (int i = 0; i < offset; i++) {
        if (source.charAt(i) == '\n') {
            line++;
            column = 1;
        } else {
            column++;
        }
    }
    return line + ":" + column;
}
```

With multi-file inputs, source transformations, or editors counting code points differently from Java, a proper source map is needed. Do not map a short snippet's line/column directly onto an original file if the application concatenated or preprocessed code.

## 6. Compile Errors vs. Runtime Errors

**Compile failure:** a snippet such as `int n = noSuchIdentifier;` typically yields `REJECTED`; check `JShell.diagnostics(event.snippet())`, because `exception()` is not the channel for compile errors.

**Runtime failure:** a snippet such as `1 / 0` can compile successfully yet fail during evaluation. `event.exception()` may then be a `jdk.jshell.EvalException`; additional details include `getExceptionClassName()` and the stack trace. Some snippets with missing references can throw `UnresolvedReferenceException`. Never use `value()` alone to determine success.

Example (inside a method with variable `shell`):

```java
for (SnippetEvent event : shell.eval("1 / 0")) {
    if (event.exception() instanceof jdk.jshell.EvalException ex) {
        System.out.println(ex.getExceptionClassName());
    }
}
```

For runtime exceptions, the UI can display the exception type and message while logging retains the stack trace appropriately. Never pass unescaped message or stack trace text directly into HTML.

## 7. Tracking Secondary Events, Overwrites, and Drops

JShell state persists across `eval` calls. When the same variable/method/type is redeclared, JShell can report the new snippet alongside `OVERWRITTEN` for the old snippet. When a declaration is added or modified, dependent snippets may be updated. Iterate over all events:

```java
for (SnippetEvent event : events) {
    Snippet changed = event.snippet();
    Snippet cause = event.causeSnippet();
    System.out.println("id=" + changed.id()
            + " previous=" + event.previousStatus()
            + " now=" + event.status()
            + " signatureChange=" + event.isSignatureChange()
            + " cause=" + (cause == null ? "direct" : cause.id()));
}
```

This is an illustrative snippet inside a method with `List<SnippetEvent> events`. When the host maintains a UI or registry, keys must include **session identity** alongside snippet identity; `snippet.id()` is only meaningful within a single JShell session. Do not retain stale status/values after `OVERWRITTEN` or `DROPPED` events.

## 8. Separating `stdout`/`stderr` from `value`

`System.out.println("hello")` called by a snippet writes text to the output stream; **it does not turn that text into `event.value()`**. When constructing JShell, you can configure streams:

```java
try (JShell shell = JShell.builder()
        .out(System.out)
        .err(System.err)
        .build()) {
    shell.eval("System.out.println(\"hello\")");
}
```

In a real application, each session/request should have its own stream or buffer. Sharing `System.out` across sessions can interleave output. UI sections should present these separately: compile diagnostics, runtime errors, expression values, and `stdout`/`stderr`.

## 9. Designing the API Result Structure

An example data contract might include:

| Field | Source | Meaning |
| --- | --- | --- |
| `sessionId` | Host-generated | Prevents snippet ID collisions across sessions |
| `snippetId` | `snippet.id()` | Identifier of the snippet within the session |
| `source` | `snippet.source()` | Source accepted by JShell |
| `kind` | `snippet.kind()` | Snippet kind |
| `previousStatus`, `status` | `SnippetEvent` | State transition |
| `value` | `SnippetEvent.value()` | Result string if present |
| `runtimeException` | `SnippetEvent.exception()` | Error during execution |
| `diagnostics` | `JShell.diagnostics(snippet)` | Compiler errors/warnings |
| `stdout`, `stderr` | JShell builder streams | Text printed by the code |

When returning results to a web application, escape source text, messages, and output. Cap buffer sizes and keep in mind that output from untrusted code can expose sensitive data.

## 10. Lifecycle and Security

JShell is a stateful environment: variables, imports, methods, and classes persist across snippets. Use `try-with-resources` or `close()` when finished. Avoid sharing a single instance across multiple users without session and concurrency controls.

Embedded JShell is **not an automatic security sandbox**. When running untrusted code, control the execution engine, OS permissions, CPU/memory/time budgets, and process/container isolation as appropriate. Never accept arbitrary code input and execute it in a host process with broad privileges.

## 11. Common Mistakes

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Reading only the first event | Misses status updates on dependent snippets | Iterate through all events |
| Treating `VALID` as execution success | Misses runtime exceptions | Check `exception()` separately |
| Treating `value()` as `System.out` | Incorrect output display | Separate streams and values |
| Not reading diagnostics | Cannot explain why a snippet was `REJECTED` | Call `JShell.diagnostics` |
| Treating `Diag` offsets as line numbers | Highlights wrong positions | Map offsets onto source text |
| Retaining old state after overwrite | UI displays stale information | Update from the latest event |
| Using `snippet.id` across sessions | ID collisions | Scope by host session ID |
| Not closing JShell | Resource leaks | Close every session |

## 12. Checklist

- [ ] Iterate over the entire `List<SnippetEvent>` from each `eval` call.
- [ ] Inspect both previous/current status, cause, and signature change.
- [ ] Distinguish compiler diagnostics, runtime exceptions, values, and `stdout`.
- [ ] Handle `REJECTED` and recoverable statuses accurately.
- [ ] Use `Diag` for messages and positions; map offsets carefully.
- [ ] Clean up state after overwrite/drop without retaining stale data.
- [ ] Close sessions and enforce isolation policies for untrusted code.

**Conclusion:** `SnippetEvent` tells you **what changed** in JShell, `status()` gives the snippet's state, `value()` is the expression result if any, `exception()` reports evaluation errors, and `Diag` provides compiler diagnostics. Reading each of these sources distinctly lets an embedded application explain errors and update its UI accurately.
