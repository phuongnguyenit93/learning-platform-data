# Managing Snippet Dependencies, Redeclarations, and Drops in Embedded JShell

## 1. Why Snippets in JShell Are Not Independent

When embedding JShell in a Java application, you are not merely executing isolated code strings. A \`jdk.jshell.JShell\` session maintains state consisting of **snippets**: variable, method, type, and import declarations, as well as expressions/statements. A later snippet can reference names declared by an earlier snippet; when a declaration is replaced or removed, dependent snippets can change status.

For example, within a JShell session:

\`\`\`java
int factor = 2;
int multiply(int x) { return x * factor; }
multiply(3);
\`\`\`

The \`multiply\` method depends on the variable \`factor\`. If you modify or \`drop\` the declaration of \`factor\`, JShell must re-evaluate whether related snippets can still compile and link. Therefore, managing snippets in an embedded application means **managing a state and dependency graph**, not simply calling \`eval()\` and forgetting the source.

JShell provides a standard API in the \`jdk.jshell\` module, including:

- \`JShell\`: interactive session, \`eval(String)\`, \`drop(Snippet)\`, \`snippets()\`, \`variables()\`, \`methods()\`, \`types()\`, \`imports()\`, \`status(Snippet)\`.
- \`Snippet\` and subclasses such as \`VarSnippet\`, \`MethodSnippet\`, \`TypeDeclSnippet\`, \`ImportSnippet\`.
- \`SnippetEvent\`: information about state transitions after \`eval\` or \`drop\`.
- \`Snippet.Status\`: statuses such as \`VALID\`, \`RECOVERABLE_DEFINED\`, \`RECOVERABLE_NOT_DEFINED\`, \`REJECTED\`, \`DROPPED\`, \`OVERWRITTEN\`, \`NONEXISTENT\`.
- \`Diag\`: compiler error diagnostics associated with a snippet.

**Key point:** \`eval()\` returns a **list** of events. A single redeclaration can change the status of multiple snippets, not just the snippet you just submitted.

## 2. The Dependency and State Model

Example:

\`\`\`text
VarSnippet: int base = 10
           |
           v
MethodSnippet: int addBase(int x) { return x + base; }
           |
           v
Expression: addBase(5)
\`\`\`

The final expression is not a long-lived declaration in the same sense as a variable or method, yet its evaluation result depends on the session state at runtime.

Each snippet has a **session-scoped ID**, \`source()\`, \`kind()\`, and status. A \`SnippetEvent\` contains:

| Property | Meaning |
|---|---|
| \`snippet()\` | The affected snippet |
| \`previousStatus()\` | Status before the event; may be \`null\` for a new snippet |
| \`status()\` | Status after the event |
| \`isSignatureChange()\` | Whether the declaration signature changed |
| \`causeSnippet()\` | Another snippet that caused this change, if any |
| \`value()\` | String value when the event produces a result |
| \`exception()\` | Execution error if one occurred |

Do not design a UI that only shows "the just-submitted snippet succeeded." You must handle **every event** and update the status of previously affected snippets as well.

## 3. Statuses You Need to Understand

| Status | Practical Interpretation |
|---|---|
| \`VALID\` | The snippet was accepted and is usable |
| \`RECOVERABLE_DEFINED\` | The declaration has dependency errors yet still has a definition that other declarations can reference under certain conditions |
| \`RECOVERABLE_NOT_DEFINED\` | The snippet can become valid once missing dependencies appear, but is not currently defined for execution |
| \`REJECTED\` | The snippet was rejected; typically syntax errors or compile errors not recoverable under JShell's rules |
| \`OVERWRITTEN\` | The declaration was replaced by another declaration |
| \`DROPPED\` | The snippet was removed from the session via \`drop\` |
| \`NONEXISTENT\` | The snippet does not exist in the session or is not validly defined in that API context |

Recoverable statuses are especially important when users author code out of order. For example, declaring a method that references an as-yet-undeclared type can be held in a recoverable state; once that type is declared, JShell can automatically update its status.

**Do not equate \`VALID\` status with "all logic ran cleanly"**: a declaration can be valid while calling the method later still throws an exception.

## 4. Redeclaration: Overwriting Instead of Deleting Every Snippet

Within a session, you can re-enter a variable, method, or type following JShell's redeclaration rules:

\`\`\`java
int price = 10;
int price = 20;
\`\`\`

The new declaration replaces the prior version. \`SnippetEvent\` can report the old declaration transitioning to \`OVERWRITTEN\` and the new declaration becoming \`VALID\`. If a method signature or type changes, dependent code may need re-analysis or transition to a recoverable status.

Two distinct situations:

- **Updating a variable's value:** \`price = 20;\` is an assignment statement, not a variable redeclaration.
- **Redeclaring a variable:** \`int price = 20;\` creates a new declaration version under JShell semantics and can replace the old snippet.

For methods, JShell allows redeclaring with the same signature. If the new method references a missing dependency, other methods calling it can change status. The API does not guarantee preserving the old snippet's identity after an overwrite.

In embedded applications, store the **ID and `Snippet` object** you received rather than looking up solely by name. A name can be reused across multiple declaration/overwrite cycles, whereas snippet objects reflect session history.

## 5. Drop: Controlled Removal of Declarations

\`JShell.drop(Snippet)\` requests removing a droppable snippet from the session. It returns \`List<SnippetEvent>\` notifying both the dropped snippet and any affected dependent snippets.

Example usage:

\`\`\`java
// Integration snippet, assuming shell and savedVariable are valid snippets.
List<SnippetEvent> events = shell.drop(savedVariable);
for (SnippetEvent event : events) {
    System.out.printf("%s: %s -> %s%n",
            event.snippet().id(),
            event.previousStatus(),
            event.status());
}
\`\`\`

Not every snippet kind has the same drop capability; obtain objects from \`shell.variables()\`, \`methods()\`, \`types()\`, \`imports()\`, or \`eval\` results and inspect their status before dropping. If a snippet is already \`OVERWRITTEN\` or \`DROPPED\`, do not assume subsequent operations behave the same as on an active declaration.

**Dropping does not undo side effects that have already happened.** For example, if code wrote a file, sent an HTTP request, or mutated a Java object outside the JShell session, dropping the declaration only updates JShell state; it does not roll back external effects.

## 6. Complete Java 17+ Example: Eval, Overwrite, and Drop

Create **\`JShellDependencyDemo.java\`** with the following contents (this is the version to compile):

\`\`\`java
import jdk.jshell.JShell;
import jdk.jshell.SnippetEvent;
import jdk.jshell.VarSnippet;
import java.util.List;

public class JShellDependencyDemo {
    static void printEvents(String label, List<SnippetEvent> events) {
        System.out.println("-- " + label + " --");
        for (SnippetEvent e : events) {
            String cause = e.causeSnippet() == null
                    ? "-"
                    : e.causeSnippet().id();
            System.out.println(e.snippet().id() + " "
                    + e.previousStatus() + " -> "
                    + e.status() + " cause=" + cause);
        }
    }

    public static void main(String[] args) {
        try (JShell shell = JShell.create()) {
            List<SnippetEvent> first = shell.eval("int base = 10;");
            VarSnippet oldBase = (VarSnippet) first.get(0).snippet();
            printEvents("declare base", first);

            printEvents("declare method",
                    shell.eval("int plusBase(int n) { return n + base; }"));

            printEvents("redeclare base", shell.eval("int base = 20;"));
            System.out.println("old base status: " + shell.status(oldBase));

            VarSnippet current = shell.variables()
                    .filter(v -> v.name().equals("base"))
                    .findFirst()
                    .orElseThrow();

            printEvents("drop base", shell.drop(current));
            System.out.println("current base status: "
                    + shell.status(current));
            System.out.println("method status: "
                    + shell.methods()
                        .filter(m -> m.name().equals("plusBase"))
                        .findFirst()
                        .map(shell::status)
                        .orElse(null));
        }
    }
}
\`\`\`

Compile and run on JDK 17+:

\`\`\`bash
javac --add-modules jdk.jshell JShellDependencyDemo.java
java --add-modules jdk.jshell JShellDependencyDemo
\`\`\`

Exact IDs and event sequences depend on snippet creation order and state transitions, so do not write tests by hard-coding the entire log; the core assertions to verify are:

- the initial variable declaration has status \`VALID\`;
- after redeclaration, the old variable snippet transitions to \`OVERWRITTEN\`;
- \`shell.variables()\` returns the currently active \`base\` declaration;
- after \`drop(current)\`, the current variable's status is \`DROPPED\`;
- dependent declarations may be marked no longer valid or recoverable.

**Note:** \`shell.methods()\` lists method snippets per the API and does not automatically filter all to the same status; when accuracy is needed, read \`shell.status(m)\` for each item.

## 7. Reading `SnippetEvent` Without Missing Cascading Effects

Every \`eval\` or \`drop\` call should process the entire event list:

\`\`\`java
// Integration snippet.
List<SnippetEvent> events = shell.eval(source);
for (SnippetEvent event : events) {
    Snippet snippet = event.snippet();
    Snippet.Status current = event.status();
    Snippet.Status previous = event.previousStatus();

    updateUi(snippet.id(), current);
    recordDependencyImpact(event.causeSnippet(), snippet);
}
\`\`\`

\`updateUi\` and \`recordDependencyImpact\` are application functions, not JShell APIs. \`causeSnippet()\` identifies the trigger when present; it does not provide a complete dependency graph. If the application needs an exact graph, add source analysis, metadata, or a dedicated tracking mechanism.

When encountering \`REJECTED\` or an invalid status, call \`shell.diagnostics(snippet)\` to read \`Diag\` entries with error details. Do not rely solely on \`event.exception()\` to detect compile errors: exceptions reflect execution errors, whereas compiler diagnostics have their own channel.

Example:

\`\`\`java
// Integration snippet; events were returned from eval/drop.
for (SnippetEvent event : events) {
    shell.diagnostics(event.snippet())
            .forEach(diag -> System.err.println(diag.getMessage(null)));
}
\`\`\`

## 8. Managing Dependencies in an Embedded Application

A plugin host often manages multiple user-provided scripts. You can organize metadata like this:

\`\`\`text
ScriptUnit {
    scriptId
    source
    revision
    declaredDependencies
    activeSnippetIds
}
\`\`\`

This is a conceptual structure, not a built-in JShell class. Whenever a script changes:

1. Identify the target JShell session; never mix snippets across sessions.
2. Validate the new source, quotas, and editor permissions.
3. Run \`eval\` and collect all \`SnippetEvent\`s.
4. Update the registry of snippet IDs, names, statuses, and revisions.
5. Check dependent snippets that transitioned to recoverable or rejected.
6. Publish the new script revision only when all required entry points are in an acceptable status.
7. If rollback is needed, consider rebuilding the session from the **approved source list**; JShell does not provide generic transactional rollback for side effects.

A crucial principle is **do not treat each snippet as an independently restorable artifact**. Dependency state belongs to the entire session.

## 9. Reload and Snapshots: Managing Changes More Safely

In environments requiring reproducibility, rather than mutating a live session serving requests, apply a staging pattern:

\`\`\`text
Active JShell (revision A)
        |
   snapshot sources
        |
        v
Staging JShell (revision B)
        |
   eval in dependency order
        |
   check diagnostics/status
        |
      PASS?
      /   \
    no     yes
    |       |
discard B   route new requests to B
            |
          drain A
            |
          close A
\`\`\`

\`JShell\` does not offer built-in serialization of an entire session into a reliable snapshot. The host must manage the source list, replay order, dependencies, and external state. If a script reads the current time, randomness, files, or the network, replay is not guaranteed to produce identical side effects or results.

Running two sessions side by side consumes more resources, but cleanly isolates validation state from active traffic. When an application uses hot-reloading plugins or custom class loaders, ensure callbacks or references from the old session do not stay alive indefinitely.

## 10. Important Limitations

**Identifiers and state are session-scoped.** A snippet from JShell A cannot be passed to \`drop\` in JShell B as if they shared history. IDs are meaningful only within the session that created them.

**JShell is not a JAR dependency manager.** Snippet dependencies are dependencies between Java declarations/code; supplying a classpath/module path to a session is a separate mechanism, such as via configuration or \`addToClasspath\` per the corresponding API. Do not conflate the two dependency layers.

**Redeclaration does not clean up external state.** If code spawns threads, opens sockets, writes data, or registers callbacks, overwriting or dropping does not automatically call \`close\` on those resources.

**Not thread-safe by default.** Concurrent access to a single \`JShell\` instance must be coordinated so multiple requests calling \`eval\`/\`drop\` do not create non-deterministic ordering. Isolate sessions per tenant/user or serialize operations as needed.

**JShell is not a sandbox.** Java code executed via JShell can have broad impact depending on the environment. For untrusted code, enforce process isolation, filesystem/network restrictions, and appropriate resource quotas.

## 11. Common Pitfalls and Checklist

Common pitfalls:

- Reading only \`events.get(0)\` after \`eval\` and ignoring events affecting other snippets.
- Storing only variable/method names instead of tracking the ID and status of each snippet.
- Treating \`OVERWRITTEN\` like \`DROPPED\`; they reflect two distinct operations.
- Dropping an active snippet and expecting dependent methods to always remain \`VALID\`.
- Assuming variable redeclaration and variable assignment are the same action.
- Treating syntactically successful \`eval\` as a guarantee that all methods run error-free.
- Confusing \`SnippetEvent.exception()\` with compiler diagnostics.
- Assuming drop/overwrite can undo external side effects.
- Sharing a single \`JShell\` across all tenants without isolating state and permissions.
- Trying to reuse snippet objects from a closed session or a different session.

Checklist when building embedded JShell:

1. Is there a registry mapping source/revision → snippet IDs and statuses?
2. After every \`eval\`/\`drop\`, are **all** \`SnippetEvent\`s processed?
3. Are \`diagnostics\` used to explain rejected/recoverable statuses?
4. Do you distinguish redeclaration, value assignment, and \`drop\`?
5. Are replay order and dependencies controlled when rebuilding a session?
6. Are lifecycle, resource cleanup, and class loaders handled properly?
7. Is there a session-level staging/rollback strategy instead of expecting automatic rollback?
8. Is execution isolated with appropriate quotas for untrusted code?

**Remember:** in embedded JShell, a snippet is part of a **dependent session state**. \`eval\` and \`drop\` can affect multiple snippets; managing them reliably requires tracking \`SnippetEvent\`, \`Snippet.Status\`, source versions, and full session lifecycles—not just the outcome of a single call.
