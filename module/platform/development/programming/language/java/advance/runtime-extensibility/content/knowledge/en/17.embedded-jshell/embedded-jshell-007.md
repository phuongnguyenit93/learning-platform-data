# Closing a JShell Session and Distinguishing a REPL Environment from a Stable Plugin Contract

**Embedded JShell** lets a Java program create a Read–Eval–Print Loop (REPL) session using the **jdk.jshell.JShell** API, submit code fragments (snippets), and receive results and diagnostics per turn. It is a very effective tool for exploring APIs, demonstrating concepts, testing algorithms, or building an interactive console. However, the lifecycle of a JShell session is fundamentally different from the lifecycle of a **packaged and released plugin under a stable contract**.

This article focuses on two practical questions: **how should a JShell session be closed to release resources on time?** and **why should live snippet state in a REPL not serve as a production plugin interface?** We will experiment on Java 17+, build a plugin JAR with an explicit SPI interface for comparison, and define safe boundaries for the host.

## 1. What Does Embedded JShell Actually Hold?

When calling JShell.create() or JShell.builder().build(), the host creates a **JShell state engine**. Each session holds:

- **Source state:** evaluated imports, variables, methods, types, and other snippets.
- **Compilation state:** relationships between snippets, compilation/name-resolution status, diagnostics, and declaration replacements.
- **Execution state:** the runtime environment for expressions/statements and the values or side effects created by executed code.
- **Operational resources:** the JShell engine, code execution mechanism, listener/subscription objects, and associated references. The default execution configuration typically uses a separate environment for snippet code, though that must not be mistaken for a security sandbox.

A snippet is **not the same as a complete .java file**, and a JShell session is **not the same as a plugin JAR**. JShell allows individual expressions, statements, or declarations to be evaluated via eval(String). Each eval call should contain **one complete snippet**. When receiving arbitrary text containing multiple snippets, use SourceCodeAnalysis.analyzeCompletion(...) to split boundaries deliberately.

For example, within a single session:

~~~java
// Illustrative statements, assuming shell is an open JShell instance:
shell.eval("int width = 6;");
shell.eval("int area(int height) { return width * height; }");
shell.eval("area(7)");
~~~

The third call can use width and area because they belong to the same session. If you create **another JShell**, those declarations do not automatically appear in the new session. If the declaration of width or area is overwritten or dropped, dependent snippets may also change status.

**A REPL enables continuous experimentation and editing**; a stable plugin contract requires well-defined interface names, parameter types, return types, versioning, loading rules, and resource responsibilities even when an implementation is replaced with a newer release.

## 2. The Proper Lifecycle: create → eval/query → close

In Java 17, **JShell implements AutoCloseable**. The API instructs calling close() when the state engine is no longer needed to release resources. The preferred pattern is **try-with-resources**, rather than waiting on the garbage collector:

~~~java
import jdk.jshell.JShell;

try (JShell shell = JShell.create()) {
    shell.eval("int result = 2 + 3;");
    // Read events or diagnostics while the session is still open.
}
// close() is called upon exiting the block.
~~~

This is a structural example; a complete program with class and main is in section 4.

The lifecycle should be understood as follows:

~~~text
NEW
 |
 | JShell.create() / JShell.builder().build()
 v
OPEN SESSION
 |  eval(), drop(), status(), diagnostics()
 |  declarations/expressions may mutate state
 |  snippets may be REJECTED or overwritten
 |
 +---- close() / exit try-with-resources ----+
 |                                           |
 v                                           v
CLOSED                                 release resources
 |
 | eval() after close()
 v
IllegalStateException
~~~

**close() is not merely clearing a Java variable**: it terminates the state engine and requests resource release. Keeping a Java reference variable holding the closed object does not make the session usable again. For example, calling eval(String) on a closed JShell throws **IllegalStateException**.

Conversely, **drop(Snippet) does not close the session**. It only makes an active declaration inactive and updates dependent snippets. JShell can still accept new eval calls after drop(). Closing the state engine is not a "drop all snippets and start over"; to get a fresh environment, create a new JShell instance and rebuild state according to host policy.

In practice, a session can also terminate **before the host explicitly calls close**, such as when the remote snippet execution environment terminates. Therefore, the host must handle abnormal session states, not only the happy path.

## 3. Events and Statuses Not to Confuse with a Plugin API

**JShell.eval(String)** returns **List<SnippetEvent>**. Each event describes a change when compiling/executing the snippet or an indirect effect on another snippet depending on it. A single eval call can produce **multiple events**, so generic code should never assume the list always has a single element.

Concepts to keep distinct:

| Component | What It Represents | Design Note |
| --- | --- | --- |
| Snippet | A source snippet belonging to one JShell instance | Not a Java SPI contract to share across sessions |
| Snippet.Status.VALID | Valid snippet whose definition/result is active in current state | Can change after another eval/drop call |
| Snippet.Status.REJECTED | Snippet was not accepted | Inspect diagnostics; do not treat as plugin startup failure |
| Snippet.Status.RECOVERABLE_DEFINED / RECOVERABLE_NOT_DEFINED | Declaration has unresolved dependency errors and may recover conditionally | Does not mean a plugin deployed successfully |
| Snippet.Status.OVERWRITTEN | Old declaration was replaced by a new declaration | Avoid implicit reliance on old definitions |
| Snippet.Status.DROPPED | Declaration was removed from source state | Not equivalent to JShell.close() |
| SnippetEvent.value() | Display string of the result if the event has a value | May be null; not a typed DTO with a stable schema |
| SnippetEvent.exception() | Exception thrown by snippet code during execution | Distinct from compile errors; must be recorded separately |
| shell.diagnostics(snippet) | Diagnostics from the snippet's most recent evaluation | Not the same as stdout/stderr from executed code |
| shell.status(snippet) | Current status of the snippet in the session | Distinct from the status recorded in an older event |

For example, redeclaring a variable in a REPL can cause the first snippet to enter OVERWRITTEN while the new declaration is VALID. A user might change a method's return type right inside the session without re-releasing an interface JAR; that behavior supports **experimentation**, not a compatibility guarantee for plugin consumers.

**Do not pass Snippet or SnippetEvent objects as a stable API to other plugins.** They are tied to a specific state engine, carry REPL session semantics, and do not represent a versioned artifact with an explicit ABI.

## 4. Java 17+ Lab: Closing the Session Even When Snippet Errors Occur

The following program uses a single Java file, creates a JShell, submits valid and invalid snippets, tests drop(), closes the session via try-with-resources, confirms eval() is rejected after close, and creates a new independent session. The goal is observing the lifecycle, **not executing untrusted Java code**.

Create **EmbeddedJshellLifecycle.java**:

~~~java
import jdk.jshell.JShell;
import jdk.jshell.SnippetEvent;

public final class EmbeddedJshellLifecycle {
    public static void main(String[] args) {
        JShell shell = JShell.create();

        // Java 9+ allows effectively final variables in try-with-resources.
        try (shell) {
            SnippetEvent defined = shell.eval("int factor = 7;").get(0);
            System.out.println("defined=" + defined.status());

            SnippetEvent value = shell.eval("factor * 6").get(0);
            System.out.println("value=" + value.value());

            SnippetEvent bad = shell.eval("int broken = ;").get(0);
            System.out.println("invalid=" + bad.status());
            System.out.println("diagnostic="
                    + (shell.diagnostics(bad.snippet()).count() > 0));

            // Remove one declaration; does not terminate the entire session.
            shell.drop(defined.snippet());
            System.out.println("dropped="
                    + shell.status(defined.snippet()));
        }

        boolean rejectedAfterClose = false;
        try {
            shell.eval("1 + 1");
        } catch (IllegalStateException expected) {
            rejectedAfterClose = true;
        }
        System.out.println("closed-eval-error=" + rejectedAfterClose);

        try (JShell fresh = JShell.create()) {
            System.out.println("fresh-variables="
                    + fresh.variables().count());
        }
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --add-modules jdk.jshell -encoding UTF-8 EmbeddedJshellLifecycle.java
java --add-modules jdk.jshell EmbeddedJshellLifecycle
~~~

**Expected stdout** in a JDK 17 environment capable of launching JShell's execution engine normally:

~~~text
defined=VALID
value=42
invalid=REJECTED
diagnostic=true
dropped=DROPPED
closed-eval-error=true
fresh-variables=0
~~~

**Line-by-line explanation:**

1. The definition int factor = 7; is valid, so the event returns status VALID.
2. The expression factor * 6 uses the current session state and produces the string value **42**. This string is for display and must not be treated as an Integer object passing through a plugin contract.
3. int broken = ; is syntactically invalid and becomes REJECTED. Reading diagnostics while the shell is still open finds at least one diagnostic.
4. drop(defined.snippet()) transitions the factor declaration to DROPPED in the session. Other snippets are not necessarily deleted simultaneously; dependent statuses update per JShell rules.
5. Upon exiting the try (shell) block, close() runs whether the inner operations return normally or throw an exception under normal Java finally/close execution.
6. Attempting eval after close hits IllegalStateException; the program catches this exact error type and prints true.
7. The new fresh session has no active variables from the old session. Creating another JShell does not "reopen" closed state.

**Important caveat:** if the execution engine fails to initialize, the process errors out, or the snippet execution environment terminates early, output may differ. The scenario above is a valid lab on a standard JDK 17, not a guarantee that every permission-restricted or overloaded environment will succeed.

### 4.1. Why Must Results Be Read Before Closing?

Operations like shell.status(snippet), shell.diagnostics(snippet), shell.varValue(...), and shell.eval(...) require an open state engine. After close, state-dependent queries and evaluations may throw IllegalStateException. Hence a practical flow should:

1. Submit the snippet;
2. Collect SnippetEvents, diagnostics, and values to retain while the session is still open;
3. Normalize results into DTOs belonging to the host's API;
4. Close JShell;
5. Return the normalized DTO to the caller.

Do not rely on retaining a Snippet object and querying JShell minutes later when a client calls an API to interpret it. Once the session is closed, keep needed result data **by value**, without holding references to the state engine.

### 4.2. Separating Compile Errors from Execution Errors

A snippet can be REJECTED due to syntax or type-checking errors without throwing an exception from user code. Conversely, a snippet can compile validly yet throw an exception during execution; in that case **SnippetEvent.exception()** reports the exception from the JShell environment. Returning a list of events successfully from JShell.eval(...) **does not automatically mean every snippet executed cleanly**.

Production tests should check status, exceptions, diagnostics, and results independently. Also account for indirect events when a new declaration overwrites an old one.

## 5. Managing `close()` in Real Embedded Code

### 5.1. `try-with-resources` Is Preferred

For a session scoped to a single request or short operation:

~~~java
// Illustrative snippet: not a standalone program.
try (JShell session = JShell.create()) {
    var events = session.eval(sourceSnippet);
    return normalize(events, session);
}
~~~

The normalize function must convert JShell data into host-controlled types while the session is still open. When return executes, try-with-resources still calls close before the result is handed to the caller.

If a framework cannot use try-with-resources because a session spans multiple interactions, the host must enforce a clear owner and termination point. For example:

~~~java
// Illustrative snippet: sessionOwner is responsible for closing this session.
JShell session = JShell.create();
try {
    sessionOwner.register(session);
    sessionOwner.serveUntilFinished(session);
} finally {
    sessionOwner.unregister(session);
    session.close();
}
~~~

The pattern above assumes register/serveUntilFinished/unregister are defined. In a real system, if unregister() throws an exception, session.close() in the same finally block might not run; prefer an AutoCloseable owner and ordered multi-resource cleanup with proper error isolation.

### 5.2. `close()` vs. `drop()`, `stop()`, and Request Cancellation

- **drop(Snippet)**: mutates declaration state for an open session.
- **stop()**: attempts to halt ongoing execution. Per the JDK API, this is best-effort; cases exist where it fails, such as code blocked in I/O or catching interrupts.
- **close()**: closes the state engine and releases resources; should be the lifecycle endpoint when the session is no longer needed.
- **Future.cancel(true)** if the host runs eval on a worker thread: primarily issues an interrupt request, not a forced kill across every execution engine.
- **Terminating a host-owned process/container**: a stronger boundary when time or memory limits are needed for untrusted code; also requires cleaning up process trees, filesystems, and IPC.

**Never call only stop() or drop() and treat the session as closed.** For session pools, mark state non-reusable, cancel active callbacks/tasks, and genuinely close the session before releasing the slot. If user code hangs, a close/stop call does not replace proper isolation policies and watchdogs.

### 5.3. Subscriptions and Callbacks

JShell lets you register listeners via onSnippetEvent(...) and onShutdown(...). onShutdown notifies when a session terminates, including when the execution environment exits unexpectedly. Registration methods return a **JShell.Subscription**; the host can call unsubscribe(token) when observation is no longer needed.

Illustrative code:

~~~java
// Assuming shell is open and log is the host's logger.
JShell.Subscription subscription =
        shell.onSnippetEvent(event -> log(event.status()));
try {
    shell.eval("int n = 1;");
} finally {
    shell.unsubscribe(subscription);
}
~~~

This code assumes a hypothetical log variable and is not a standalone example. Registering a callback does not amount to starting a stable "plugin runtime." Callbacks can retain references to host objects; unsubscribing and closing sessions under clear ownership reduces the risk of retaining unnecessary references.

### 5.4. Do Not Share a JShell Session Arbitrarily Across Threads

JDK 17 documentation states **JShell is not thread-safe**, except for explicitly documented methods. Do not let two requests concurrently call eval/drop/close on the same session and expect predictable state ordering. One solution is assigning each session to a dedicated single worker or serial queue; the lifecycle manager prevents new requests once closing begins.

If an async job is using a session, do not close it immediately upon an HTTP request timeout without coordinating with the worker; follow a cancellation protocol, mark the session non-reusable, wait for or terminate the isolated worker, and then clean up. Memory, listeners, streams, and session references must all be released under one owner.

## 6. REPL vs. Plugin: Comparing by Contract, Not Just How Code Is Invoked

Both mechanisms let behavior appear after the host starts, yet their goals differ:

| Aspect | Embedded JShell/REPL | Stable Plugin with SPI/JAR |
| --- | --- | --- |
| Source unit | Snippet (expression, statement, declaration) | Compiled classes/modules and built artifact |
| When changes happen | Mid-session via eval/drop/redeclaration | By releasing a new versioned artifact |
| Public contract | Usually session state and interpreted values | Interfaces/DTOs, method signatures, API versions |
| Identity | Snippet ID/state bound to a JShell instance | Plugin ID/version + implementation class/module |
| Compatibility checks | In-session compilation status and snippet dependencies | Compile/runtime compatibility, API versioning, contract tests |
| Result | SnippetEvent.value() is a contextual String representation | Typed Java objects/DTOs with defined semantics |
| Lifecycle | create → eval/query → close | install → validate → start → serve → stop/unload |
| Dependencies | imports, classpath/session setup, turn-by-turn state | Managed dependency graph and class loader/module layer |
| Implementation discovery | Submitting source in order or selecting snippets | SPI/ServiceLoader, registry, or manifest |
| State isolation | Session-scoped state; execution may have side effects | State scoped to defined plugin instances/lifecycles |
| Redeployment | Create a new session and replay source if needed | Load new artifact, migrate state if contract requires |
| Reliability | Great for exploration and prototyping | Suited for long-lived integration when contracts are tested |

**Principle:** do not use a bundle of strings naming JShell variables/methods as a production plugin API just because "it works in the current session." A session depends on eval history, classpath, and runtime state; another caller or a fresh session may lack those declarations.

A SnippetEvent.value() like "42" carries no type or version metadata for inter-component messaging. When exposing results externally, the host must convert them into an explicit-schema DTO, such as **CompileResult(status, diagnostics, output)** or **EvaluationResult(type, displayText, errors)**. Define encoding, length bounds, errors, and compatibility contracts.

## 7. Comparison Lab: A Classpath Plugin with a Fixed SPI Contract

To see the difference, let's build a simple plugin with a stable Java interface. Here the host does not eval arbitrary code strings, but invokes a pre-built **MessagePlugin interface**; the implementation and service registration are packaged in a separate JAR.

### 7.1. File Tree

~~~text
plugin-lab/
├── src/
│   ├── api/demo/api/MessagePlugin.java
│   ├── plugin/demo/plugins/UpperPlugin.java
│   └── host/demo/host/Host.java
├── resources/
│   └── META-INF/services/demo.api.MessagePlugin
├── build/                      (created during compilation)
└── dist/                       (created when packaging JAR)
~~~

### 7.2. The SPI Contract Shared by Host and Plugin

File **src/api/demo/api/MessagePlugin.java**:

~~~java
package demo.api;

public interface MessagePlugin {
    String id();
    String transform(String input);
}
~~~

The interface signature is the **compile-time and runtime contract**. Callers know id() and transform(String) upfront and can write standard tests. Changing parameter or return types arbitrarily is nothing like redefining a snippet; changing signatures can break **binary compatibility** for existing implementations.

### 7.3. Implementation Released as a JAR

File **src/plugin/demo/plugins/UpperPlugin.java**:

~~~java
package demo.plugins;

import demo.api.MessagePlugin;
import java.util.Locale;

public final class UpperPlugin implements MessagePlugin {
    public UpperPlugin() {}

    @Override
    public String id() {
        return "upper";
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

File **resources/META-INF/services/demo.api.MessagePlugin** has no extension and contains exactly one line:

~~~text
demo.plugins.UpperPlugin
~~~

The descriptor must sit at the root of the JAR. The filename is the **fully qualified name of the service interface**, and the file contents name the provider class. This is a **classpath** SPI example; module path setups with explicit named modules can use uses/provides declarations in module-info.java, which is a different configuration mechanism.

### 7.4. Host Loads the Plugin via SPI and Calls the Stable Interface

File **src/host/demo/host/Host.java**:

~~~java
package demo.host;

import demo.api.MessagePlugin;
import java.util.ServiceLoader;

public final class Host {
    public static void main(String[] args) {
        int found = 0;
        for (MessagePlugin plugin :
                ServiceLoader.load(MessagePlugin.class)) {
            if ("upper".equals(plugin.id())) {
                System.out.println("plugin=" + plugin.id());
                System.out.println("result="
                        + plugin.transform("hello"));
                found++;
            }
        }
        System.out.println("matched=" + found);
    }
}
~~~

The host does not need to know the UpperPlugin class at compile time. It knows only MessagePlugin, while packaging ensures the implementation can be loaded and instantiated under the classpath ServiceLoader contract (a public provider class with a valid public no-arg constructor).

### 7.5. Building and Running with JDK 17+

From the **plugin-lab/** root directory using a bash/POSIX shell:

~~~bash
mkdir -p build/api build/plugin build/host dist

javac --release 17 -encoding UTF-8 -d build/api src/api/demo/api/MessagePlugin.java
jar --create --file dist/api.jar -C build/api .

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d build/plugin src/plugin/demo/plugins/UpperPlugin.java
jar --create --file dist/upper-plugin.jar -C build/plugin . -C resources .

javac --release 17 -encoding UTF-8 -cp dist/api.jar -d build/host src/host/demo/host/Host.java
java -cp "build/host:dist/api.jar:dist/upper-plugin.jar" demo.host.Host
~~~

**Exact expected stdout** with one descriptor/provider as above:

~~~text
plugin=upper
result=HELLO
matched=1
~~~

On Windows when invoking Java in PowerShell/CMD, the classpath separator is **;** instead of **:**. The mkdir -p command is bash syntax; create directories beforehand using Windows shell tools if not using bash.

Compare this with the JShell example in section 4: here the host makes no eval() calls, stores no SnippetEvents, and does not depend on a user's declaration history. A new implementation can swap in safely only if it adheres to the published interface, API compatibility, and host versioning policy. **Runtime extensibility** is still achieved, but bounded by artifacts and contracts.

**Inspecting the artifact:** jar --list --file dist/upper-plugin.jar must find demo/plugins/UpperPlugin.class and META-INF/services/demo.api.MessagePlugin. Do not bundle a duplicate copy of demo/api/MessagePlugin.class inside this lab's plugin JAR; host and plugin share the same API class identity over the shared classpath. If separate copies of the SPI interface are loaded by different loaders, two identically named types may not be compatible.

## 8. The Sensible Boundary: JShell for Exploration, Plugins for Operation

A product can combine both mechanisms without blurring their roles:

~~~text
Experimental source code
      |
      v
JShell sandboxed development environment
      |
      | eval + diagnostics + quick test
      v
Decide functionality meets requirements
      |
      | convert to .java/module-info source + tests
      v
Build/CI → contract tests → versioned JAR artifact
      |
      | verify signature/origin/dependencies and compatibility
      v
Plugin manager / ServiceLoader / ModuleLayer
      |
      | start → invoke public API → stop/unload
      v
Host production
~~~

In the diagram, "sandboxed development environment" refers to a **development environment isolated by the application/OS**, not a security guarantee provided by the JShell API itself. If JShell is embedded in a system where users submit untrusted code, use a dedicated process/container with explicit quotas and policies.

A controlled integration approach:

1. Users experiment with snippets in a JShell session with an explicit **session ID**, expiration time, and ownership.
2. The host limits input, output, concurrency, and execution time; normalizes diagnostics/results; and closes the session upon expiration or completion.
3. Once a prototype is stable enough, convert the code into named `.java` source files/classes/packages, compile, and run tests.
4. Publish only builds with well-defined interfaces/DTOs, semantic versioning, and policy-compliant checksums/signatures.
5. The plugin manager verifies the artifact, discovers providers, checks API versions, and invokes them through the contract.
6. When unloading a plugin, stop active requests/callbacks/threads and resources; **close any experimental JShell session** if still open, and manage the plugin runtime loader/lifecycle separately.

If you only need short, host-controlled expressions, a well-managed JShell engine may be an appropriate internal tool. However, to extend a system long-term, accept independently versioned plugins, or support upgrades and rollbacks, a Java SPI contract or packaged API is a far more verifiable choice.

## 9. Security and Resource Boundaries: `close()` Is Not a Sandbox

A dangerous misconception is: "JShell has a separate default execution engine, so running arbitrary code is safe." That is **false**. JShell executes Java code, and that code can cause side effects, load libraries, access files or the network, or consume resources within granted permissions. Execution engine behavior and classpath configuration can also vary. Calling close() releases the state engine, **which does not mean undoing every side effect** already caused.

In production environments, separate the safeguards:

| Concern | What JShell API Provides | What the Host Must Still Do |
| --- | --- | --- |
| Valid session expiration | AutoCloseable, close() | Track owner, enforce timeout, never reuse closed instances |
| Syntax/compile errors | SnippetEvent.status() and diagnostics | Normalize errors, cap result size, log |
| Snippet runtime errors | SnippetEvent.exception() | Determine request status and recovery policy |
| Long-running snippets | stop() best-effort halt | Isolation, watchdog, and hard deadlines at process/container level |
| Excessive retained state | drop(), new session creation, close() | Quotas on source/snippets/output/heap and concurrent sessions |
| Untrusted code | No full sandbox via JShell alone | OS, network, disk, and resource limits plus process isolation |
| Long-term plugin integration | REPL does not provide a fixed plugin contract | SPI/DTO/API versioning, contract tests, and artifact management |

Do not merge snippet evaluations from multiple tenants into a single shared JShell just to save startup overhead: data and declarations would share the same state engine, and JShell is not thread-safe. For untrusted users, choose per-context isolated workers/processes with strict lifecycle limits.

**Java 17 note:** The jdk.jshell API lives in a separate JDK module; execution requires a JDK containing this module. A minimal Java runtime image built without jdk.jshell cannot run code depending on the JShell API. Meanwhile, plugin JARs running against standard Java APIs have module/classpath requirements defined by their own contract. This is another reason production plugin interfaces should never depend directly on JShell.Snippet.

## 10. Common Errors and Diagnostics

| Symptom | Cause to Check | Resolution |
| --- | --- | --- |
| eval() throws IllegalStateException | JShell was already closed or execution state terminated | Do not reuse the instance; create a new session per policy |
| Variable from an earlier turn is missing | Call went to a different JShell, or declaration was dropped/overwritten | Track session IDs, statuses, and eval ordering |
| One eval produces unexpectedly many events | Snippet change affected dependent declarations | Iterate over the full List<SnippetEvent>; do not hard-code get(0) in generic handlers |
| status is VALID yet value is null | Snippet has no display value, such as an import or method declaration | Inspect status, kind, exception, and value according to snippet kind |
| Result string has quotes or unexpected formatting | SnippetEvent.value() is a display string, not a DTO | Normalize into a caller schema; do not parse as an ABI |
| Diagnostics present but no runtime exception | Compile error, not a plugin method throwing an exception | Handle diagnostics and REJECTED separately |
| Snippet threw an exception despite compiling cleanly | Code executed and threw at runtime | Check SnippetEvent.exception() and handle at the evaluation boundary |
| Session expired yet worker/CPU stays busy | stop/cancel/close does not replace independent process termination | Enforce isolation, watchdogs, and worker lifecycle cleanup |
| Plugin updated yet host runs old version | Old instance, class loader, JAR, or registry entry still retained | Stop/unregister, create new loader/version, verify compatibility |
| Plugin discovered but cannot be cast to API | SPI class defined by a different loader | Share stable API with unified class identity |
| Works in JShell but real source build fails | Snippet syntax and default REPL state/imports differ from project source | Convert to full files/modules and compile/test via the official pipeline |

When checking "is the session closed?", do not merely check whether the JShell reference variable is non-null. Check lifecycle state in the host and verify close() was called by the proper owner; probing a shell with eval() just to see if it is open introduces side effects and must not be used as a production health check.

When checking "is the plugin stable?", do not treat a single successful JShell evaluation as the sole criterion. Verify API contracts, dependencies, JDK version, loading paths, configuration, failure behavior, and tests across versions.

## 11. Reinforcement Exercises

**Exercise A — simulate an error then close:** In the section 4 lab, replace the invalid snippet with a valid declaration whose execution throws RuntimeException. Observe SnippetEvent.exception() and confirm try-with-resources still closes the session after host handling. Distinguish snippet runtime exceptions from IllegalStateException caused by a closed JShell.

**Exercise B — status and redefinition:** Evaluate int factor = 7; then evaluate int factor = 9; in the same session. Observe the statuses of both old and new snippets via shell.status(snippet). Try creating a new JShell and verify it lacks the prior factor declaration.

**Exercise C — listener lifecycle:** Register onSnippetEvent, save the Subscription, and unsubscribe before closing. Compare collecting events directly from eval() versus via callback. Never store JShell.Subscription as an API for clients to invoke after the session ends.

**Exercise D — plugin contract:** Change transform(String) to transform(Object) on the interface and try compiling the old provider. Explain why this is a potentially breaking API change, fundamentally different from redefining a method snippet in a REPL.

**Exercise E — SPI packaging:** Remove META-INF/services/demo.api.MessagePlugin from the plugin JAR, run the host, and observe matched=0. The plugin class still exists, yet ServiceLoader no longer discovers it. Fix this via packaging, not via JShell.eval.

**Exercise F — shutdown and concurrency:** Simulate two requests sharing one JShell. Instead of concurrent eval calls, build a session-dedicated queue and an OPEN → CLOSING → CLOSED state machine in the session manager. Ensure no new tasks are accepted once closing begins.

## 12. Operational Checklist and API References

Before shipping embedded JShell code in an application, verify:

- **Ownership:** Every session has an owner, session ID, termination criteria, and session count limits; never share JShell across threads without serialization.
- **Close:** Use try-with-resources for short sessions; long-lived sessions must call close within managed cleanup/lifecycle hooks. Never treat drop/stop as close.
- **State/results:** Read the entire List<SnippetEvent>, separate compile status/diagnostics from runtime exceptions, and normalize results before closing.
- **Failure:** Handle already-closed JShell, remote execution engine termination, evaluation timeouts, lingering threads/tasks, and errors during close/cleanup.
- **Security:** Never execute untrusted source in a privileged JVM merely because JShell is convenient; use process isolation, quotas, and privilege restrictions as needed.
- **Plugin contract:** Interfaces/DTOs and versions independent of JShell, unified API class identity, verified JAR/module artifacts, and startup/rollback tests.
- **Clean unload:** Stop requests/callbacks/threads, close experimental JShell sessions, and manage plugin runtime loaders/lifecycles separately; never assume GC immediately reclaims all class loaders.

JDK 17 standard documentation: [JShell API](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/JShell.html), [package jdk.jshell](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/package-summary.html), [Snippet and Status](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jshell/jdk/jshell/Snippet.html), [Java Shell User's Guide](https://docs.oracle.com/en/java/javase/17/jshell/), and [ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html).

**Conclusion:** treat **JShell as a stateful, time-bounded experimentation session**: create, evaluate, collect results, and close to release resources. When a capability becomes a long-term integration component, **graduate it to a stable plugin contract** (versioned SPI/DTOs and built/tested artifacts) rather than relying on snippet history or REPL display strings.
