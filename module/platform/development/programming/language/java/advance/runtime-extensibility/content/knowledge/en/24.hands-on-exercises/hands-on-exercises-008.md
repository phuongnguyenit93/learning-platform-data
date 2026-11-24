# Synthesizing Criteria for Selecting Extensibility Mechanisms by Requirements, Operations, and Trust Level

## 1. Objectives of the Synthesis Exercise

"A Java application needs plugin support" is not yet a specific enough requirement to choose a technology. Some systems only select among known implementations at startup; others accept new JARs at runtime; some compile partner-submitted Java source; and some must handle code from **untrusted** users. Those scenarios demand different architectures.

This exercise builds a **decision framework** based on three groups of criteria:

1. **Business requirements:** who develops extensions, what input format is used, when extensions are added/replaced, and whether zero downtime is required?
2. **Operations and maintainability:** start/stop lifecycle, dependencies, versioning, rollback, CI/CD, error monitoring, latency, and resource leaks.
3. **Trust level:** what data can plugins access, what is the impact of a bug or attack, and is OS/process-level isolation required?

Expected outcome: select one mechanism or a **combination of mechanisms**, justify it via mandatory constraints and trade-offs, build a Java 17 prototype, and plan testing, rollout, and rollback. The guide does not assume "the more dynamic, the better" and does not treat a classloader as a security sandbox.

## 2. Responsibility Map: Never Confuse Discovery, Loading, Compiling, and Isolation

An extensibility system typically spans several independent layers:

~~~text
Extension code source
    |
    +-- Implementation compiled at build/deploy time
    +-- Provider JAR supplied at runtime
    +-- Java source requiring compilation
    +-- Interactive snippet / script
    +-- Request sent to an extension service
    |
    v
Discover / select implementation
    +-- Factory / strategy / DI container / registry
    +-- ServiceLoader / JPMS services
    |
    v
Create or load code
    +-- Application classpath
    +-- Separate URLClassLoader per generation
    +-- JPMS module path / ModuleLayer
    +-- JavaCompiler / JShell / external engine
    |
    v
Execute
    +-- Same JVM: shares process privileges and resources
    +-- Separate worker JVM: IPC + OS policy
    +-- Separate service: HTTP/gRPC/message transport
    |
    v
Lifecycle and operations
    +-- Verify -> Start -> Activate -> Quiesce -> Stop -> Release
    +-- Metrics, tracing, version, health, rollback, cleanup
~~~

**ServiceLoader** primarily solves provider discovery by service contract. **URLClassLoader** solves loading classes/resources from URLs and enables separate class namespaces. **JPMS** governs module readability, exports, opens, and service binding. **JavaCompiler** compiles source into bytecode. **JShell** evaluates Java snippets inside an interactive session. Only a **process/service boundary** can enforce independent privilege, CPU, RAM, and termination policies for a misbehaving extension, provided the OS is properly configured.

Therefore, the question "should we choose ServiceLoader or URLClassLoader?" often misses a layer: the two tools can work together. Specifically, the host can call `ServiceLoader.load(Plugin.class, loader)` on a separate `URLClassLoader` to both discover providers and load a JAR dropped in at runtime. However, that combination **does not inherently provide security isolation**.

## 3. Comparison Matrix of Java Extensibility Options

| Option | When to consider | Strengths | Main limitations |
| --- | --- | --- | --- |
| **Strategy / Factory / DI** | Implementations are known at build time; select behavior via config | Type-safe, few moving parts, simple testing and debugging | Adding new code usually requires rebuilding/redeploying |
| **ServiceLoader at startup** | SPI providers packaged as JARs alongside release | Standard JDK discovery, host depends on interface | Does not auto-download new JARs or build hot-reload lifecycles |
| **ServiceLoader + URLClassLoader** | Trusted provider JARs loaded/swapped while running | Host needs no import of implementations; per-generation loaders | Dependency identity, threads, registries, shutdown, and rollback are harder |
| **JPMS / ModuleLayer** | Need named modules and explicit requires/exports/uses/provides | Module readability/encapsulation, service binding | Module graph, layers, exports/opens; not a sandbox |
| **Reflection + registry** | Controlled runtime selection of classes/methods | Flexible, no compile-time knowledge of implementations | Runtime/access/signature errors; neither discovers providers nor protects host |
| **JavaCompiler API** | Accepting authorized Java source for dynamic compilation | Compiles Java with diagnostics, classpath, module path, --release | Must manage compiler, dependencies, outputs, annotation processors; not a sandbox |
| **JShell API** | REPLs, educational tools, Java snippet consoles | Great for interactive sessions and snippet state | Not a deployment manager; eval has side effects, not a sandbox |
| **ScriptEngine JSR 223** | Scripting when a packaged engine and governance exist | Common API for installed engines | JDK 17 does not guarantee a JavaScript engine; Nashorn is no longer bundled |
| **Separate worker JVM/process** | Need bounded blast radius, OS privileges, resources, or independent kill | Quotas/restart/kill, independent runtime versions | IPC, latency, cross-process logging, OS policies, more complex deployment |
| **Out-of-process service** | Polyglot partners, independent deployment/scaling | Versioned protocol, decoupled lifecycle, separate deployment | Network latency, auth, timeouts, retries, consistency, schema versioning |

Choose based on **the role to solve**, rather than forcing one mechanism to do everything. For example, extensions submitted as Java source can use `JavaCompiler` inside a worker process, where the worker then loads the compiled bytecode. Yet if you only need to switch between Formatter A and B already inside the host, factory/DI suffices.

## 4. Clarify Requirements Before Comparing Technologies

An architecture selection workshop can use the following questionnaire:

| Category | Questions to answer with concrete data |
| --- | --- |
| Extension author | Internal team, contracted partner, admin, or untrusted user? |
| Input format | Class/JAR, named module, Java source, snippet, script, or API request? |
| Change frequency | Quarterly, weekly, several times a day, or per request? |
| Downtime | Can the JVM restart? Is zero-downtime/hot swap required? |
| Compatibility | How are plugin API versions, JDK releases, schemas, ABIs, and dependencies pinned? |
| Access rights | May extensions open files, networks, subprocesses, secrets, or databases? |
| Failure containment | Can a hung/crashed plugin slow down or crash the host? |
| Performance | p50/p95/p99 latency, throughput, startup/reload time, RAM/metaspace budget? |
| Operations | Who releases/reviews artifacts, rolls back, monitors, cancels work, and cleans up resources? |
| Observability | Are plugin ID/version, loader generation, CodeSource, module, and trace ID logged? |
| Portability | Are polyglot plugins or distinct runtimes required? |
| Quality | Compatibility tests, negative tests, memory leaks, concurrent hot swaps? |

**Never answer "trusted" based on gut feeling.** Trust is a property of the source, artifact verification pipeline, granted privileges, and blast-radius containment. A plugin from a "contracted" partner allowed to execute arbitrary bytecode can still introduce bugs or disrupt the host; actual risk must be evaluated.

## 5. Hard Gates: Eliminate Before Scoring

### Gate 1 — Untrusted code and blast radius

If an extension can execute arbitrary Java code supplied by untrusted users, while the host holds private data or must not crash/hang, then `URLClassLoader`, JPMS, reflection, `JavaCompiler`, and `JShell` **are not sandboxes**. They run inside the JVM or orchestrate code with side effects, providing no secure OS privilege boundary.

The architecture must consider a separate worker process/container, a least-privilege execution identity, CPU/RAM/PID/disk limits, filesystem isolation, network policies, secret restrictions, timeouts, task cancellation, and process-tree termination. A separate process running with the same unrestricted file/network permissions is **still not enough** to be considered safe.

### Gate 2 — Mandatory ability to terminate hung work

If the host must stop an uncooperative extension without affecting other plugins, it cannot rely solely on `Thread.interrupt()` or `URLClassLoader.close()` in the same JVM. Interruption is cooperative; closing a loader does not stop threads or destroy loaded classes. For reliable hard-kill guarantees, favor process boundaries and OS policies.

### Gate 3 — Release policies prohibiting runtime code loading

Many organizations permit only artifacts that passed CI/CD, approvals, and release windows. Without an approval workflow for runtime loading, building complex hot-reload machinery may **violate policy**. In such cases, startup `ServiceLoader` or factory/DI is usually more appropriate.

### Gate 4 — Toolchain and input format

`JavaCompiler` requires an available system compiler; `ToolProvider.getSystemJavaCompiler()` can return `null` if the runtime image omits the compiler. `JShell` requires the `jdk.jshell` module at runtime and fits snippets, not full-project compilation. `ScriptEngine` depends on an actually installed engine; **never** assume JDK 17 ships Nashorn.

### Gate 5 — API boundaries and compatibility

If the host casts a plugin to an interface, host and implementation must share the exact **class identity** of the API. Two classes both named `demo.api.Plugin` defined by two different defining loaders are not equivalent. For in-process plugins, place the shared SPI/API in an appropriate parent or module. For IPC, version schemas/protocols and run compatibility tests.

If an option violates a hard gate, **eliminate it upfront**; never use high throughput or developer convenience scores to offset a security hole or an inability to meet job-termination SLAs.

## 6. Quick Decision Tree

~~~text
Runs untrusted code or requires blast-radius/kill isolation?
  |
  +-- YES --> Separate worker process/container or service
  |           + OS policy, quota, auth, IPC, health/restart
  |
  +-- NO --> Is input an interactive Java snippet?
                 |
                 +-- YES --> JShell (within permitted scope)
                 |
                 +-- NO --> Is input Java source compiled at runtime?
                                |
                                +-- YES --> JavaCompiler (trusted context)
                                |          + output + loader/module layer
                                |
                                +-- NO --> Implementation already exists at build time?
                                               |
                                               +-- YES --> Strategy/DI/factory
                                               |          or startup ServiceLoader
                                               |
                                               +-- NO --> Approved provider JAR?
                                                              |
                                                              +-- NO --> Design/approve SPI
                                                              |
                                                              +-- YES --> Needs loading/swapping
                                                                         while JVM is running?
                                                                       |
                                                                       +-- NO --> Startup SPI
                                                                       |
                                                                       +-- YES --> URLClassLoader
                                                                                  + ServiceLoader
                                                                                  + lifecycle
~~~

If extensions are named modules requiring JPMS contracts, replace classpath loaders with intentional module paths/layers. For multi-language or independent deployment needs, a service API can beat classloaders altogether. A decision tree does not replace a risk review; it quickly rules out options at the wrong layer.

## 7. Weighted Scoring After Passing Hard Gates

To compare qualifying options, pick suitable weights and score 1–5 (5 is best). An **illustrative** weight set:

| Criterion | Weight |
| --- | ---: |
| Fit for reload/lifecycle needs | 25% |
| Operational, rollout, and rollback cost | 20% |
| Compatibility and dependency management | 20% |
| Latency, throughput, and resources | 15% |
| Diagnostics, monitoring, and testing | 10% |
| Development/maintenance complexity | 10% |
| **Total** | **100%** |

Formula:

~~~text
weighted_score = SUM(weight_percent_i * rating_i) / 100

rating_i from 1 to 5.
If it fails a hard gate, eliminate the option; do not evaluate weighted_score.
~~~

For the scenario of **approved provider JARs requiring swaps while the JVM is running**, scoring might look like this. Scores are workshop assumptions, not benchmarks:

| Option | Reload 25 | Ops 20 | Compatibility 20 | Performance 15 | Diagnosis 10 | Simplicity 10 | Score / 5 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ServiceLoader startup/restart | 1 | 5 | 4 | 5 | 4 | 5 | **3.70** |
| ServiceLoader + per-generation URLClassLoader | 5 | 3 | 4 | 4 | 4 | 3 | **3.95** |
| Separate worker process | 5 | 2 | 4 | 2 | 5 | 2 | **3.45** |

Checking the middle option's formula:

~~~text
(25*5 + 20*3 + 20*4 + 15*4 + 10*4 + 10*3) / 100
= (125 + 60 + 80 + 60 + 40 + 30) / 100
= 395 / 100
= 3.95
~~~

For startup SPI: `(25 + 100 + 80 + 75 + 40 + 50)/100 = 3.70`. For worker process: `(125 + 40 + 80 + 30 + 50 + 20)/100 = 3.45`. Scores are computed consistently using the same weights.

**Interpretation:** under these assumptions, dynamic SPI scores highest overall. However, if restarts are **disallowed**, startup SPI fails the lifecycle hard gate; if code is untrusted and needs isolation, dynamic SPI fails the security hard gate despite its higher score. Validate ratings with benchmarks and operational trials rather than treating 3.95 as absolute truth.

## 8. Common Architectural Combinations

### 8.1. Stable internal code: Factory, DI, or startup SPI

If the product team owns all implementations and releases on a regular cadence, a small interface with a factory or dependency injection usually suffices. When libraries should advertise implementations without the host importing concrete classes, startup `ServiceLoader` fits well. No per-generation loaders or `JavaCompiler` are needed.

Strength: lowers classloader leak risk and works through standard CI/CD. Weakness: adding a new provider typically requires releasing/restarting the host. This can be an excellent trade-off if hot reload is not a real requirement.

### 8.2. Trusted JARs requiring in-JVM loading and updates

Choose a **shared API/SPI**, per-generation loaders, and `ServiceLoader` for discovery. Define a `Plugin.id()/start()/stop()/close()` contract or appropriate registration handles; maintain an ID/version/generation → artifact/loader/instance mapping.

The plugin manager must ensure: artifacts are verified before loading; routing switches only after candidate health checks pass; old versions accept no new calls; in-flight calls drain; executors/listeners/schedulers stop; TCCL is restored and ThreadLocals are cleared on the proper threads; loaders close and cache/registry references are dropped.

**`URLClassLoader.close()` does not destroy already-loaded classes.** Old instances can still be invoked if the host retains references. Enforce lifecycle states to block calls rather than expecting loader closure to automatically disable code.

### 8.3. Named modules and JPMS

When module descriptors, `requires`, `exports`, `opens`, and `uses/provides` bring genuine value for dependency control and encapsulation, consider named modules and module layers. Do not place every JAR on the module path just to feel "more modern". Named modules are not a process-level security boundary; layer/class lifecycles still depend on reachability and GC.

### 8.4. Java source supplied by authorized users

`JavaCompiler` accepts options like `--class-path`, `--module-path`, `-d`, and `--release 17` to produce bytecode. Compile into an isolated directory, capture diagnostics, restrict annotation processing and library versions, and verify outputs before loading. If sources come from untrusted users, move both compilation and execution into an appropriately isolated worker.

### 8.5. Consoles/snippets or scripts

`JShell` fits interactive Java snippets: use `SourceCodeAnalysis.analyzeCompletion` to split complete snippets before `eval`, and close sessions when finished. For other scripting, JSR 223 is only a facade; you need a real engine and execution policy. Both can execute code with side effects under process privileges, so never use them as sandboxes.

### 8.6. Process/service extensions

When blast-radius containment, privilege separation, or independent restarts/scaling are needed, choose a worker process or out-of-JVM service. Define IPC schemas, authentication, timeouts, retries, backpressure, idempotency, health checks, process limits, and observability. The added cost is latency and infrastructure; the benefit is OS-enforced isolation and independent deployment.

## 9. Java 17 Hands-On: SPI Discovery via a Dedicated Loader

We will implement a **trusted provider JAR** using `ServiceLoader` + `URLClassLoader`. This is the minimal step showing how an API contract, discovery, and a loader generation fit together. The example does not pretend to provide a sandbox or full hot reload, as a real lifecycle needs additional components.

### 9.1. Project structure

Create the following files inside `plugin-choice-demo`:

~~~text
plugin-choice-demo/
  src/
    api/demo/api/Formatter.java
    provider/demo/provider/UppercaseFormatter.java
    provider-resources/META-INF/services/demo.api.Formatter
    host/demo/host/HostApp.java
  build/                        (generated by compile commands)
~~~

**File `src/api/demo/api/Formatter.java`:**

~~~java
package demo.api;

public interface Formatter {
    String id();
    String format(String input);
}
~~~

This is the SPI referenced by both host and provider. The API class is loaded by the **parent/application loader**; plugin implementations must not define their own copy of the API in a child loader.

**File `src/provider/demo/provider/UppercaseFormatter.java`:**

~~~java
package demo.provider;

import demo.api.Formatter;
import java.util.Locale;

public final class UppercaseFormatter implements Formatter {
    public UppercaseFormatter() {
    }

    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
~~~

The provider has a public zero-argument constructor matching classpath SPI rules. In a JPMS named module, a provider can also be declared via `provides ... with ...`; this demo intentionally uses classpath metadata.

**File `src/provider-resources/META-INF/services/demo.api.Formatter`:**

~~~text
demo.provider.UppercaseFormatter
~~~

The **descriptor filename** is the fully qualified name of the interface (`demo.api.Formatter`). Its content is the fully qualified name of the implementation, with no `.class` suffix or JSON. If the descriptor is not packaged at the exact path, `ServiceLoader` will not automatically find this implementation.

**File `src/host/demo/host/HostApp.java`:**

~~~java
package demo.host;

import demo.api.Formatter;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class HostApp {
    private HostApp() {
    }

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("build/provider.jar");
        if (!Files.isRegularFile(jar)) {
            throw new IllegalStateException("Missing provider JAR");
        }

        ClassLoader parent = HostApp.class.getClassLoader();
        URL[] urls = {jar.toUri().toURL()};

        try (URLClassLoader loader = new URLClassLoader(
                "formatter-generation-1", urls, parent)) {

            ServiceLoader<Formatter> providers =
                    ServiceLoader.load(Formatter.class, loader);

            int count = 0;
            for (Formatter formatter : providers) {
                if (!"uppercase".equals(formatter.id())) {
                    continue;
                }

                count++;
                System.out.println("provider=" + formatter.id());
                System.out.println(
                        "result=" + formatter.format("hello plugin"));
                System.out.println("loader="
                        + formatter.getClass().getClassLoader().getName());
            }

            if (count != 1) {
                throw new IllegalStateException(
                        "Expected one uppercase provider; found " + count);
            }
        }
    }
}
~~~

**Explanation:**

1. The host does not import `demo.provider.UppercaseFormatter`. It knows only the `Formatter` SPI.
2. `URLClassLoader` receives a URL pointing to the provider JAR and a generation name. Its parent is the host's loader, holding the shared API.
3. `ServiceLoader.load(Formatter.class, loader)` finds the SPI descriptor inside the JAR and instantiates the provider. The host does not use reflection to guess implementation class names.
4. When the provider is loaded by the child loader, `getClass().getClassLoader().getName()` returns the loader name set in the demo.
5. Try-with-resources closes the loader when the host finishes. If a provider owns background tasks, streams, or listeners, stop them **before** closing the loader in a real plugin manager.
6. A malformed descriptor or a provider lacking a matching constructor can raise `ServiceConfigurationError`; the host must log the cause rather than swallowing it and silently using another implementation.

### 9.2. Compile and run

From `plugin-choice-demo`, with JDK 17+ and Bash:

~~~bash
mkdir -p build/api build/provider build/host

javac --release 17 -encoding UTF-8 \
  -d build/api src/api/demo/api/Formatter.java
jar --create --file build/api.jar -C build/api .

javac --release 17 -encoding UTF-8 \
  -cp build/api.jar -d build/provider \
  src/provider/demo/provider/UppercaseFormatter.java

jar --create --file build/provider.jar \
  -C build/provider . \
  -C src/provider-resources META-INF/services/demo.api.Formatter

javac --release 17 -encoding UTF-8 \
  -cp build/api.jar -d build/host \
  src/host/demo/host/HostApp.java

# Provider JAR must not be added to the application classpath.
java -cp "build/host:build/api.jar" demo.host.HostApp
~~~

**Exact stdout** when packaged properly:

~~~text
provider=uppercase
result=HELLO PLUGIN
loader=formatter-generation-1
~~~

On Windows PowerShell, the run command uses semicolons:

~~~powershell
java -cp "build/host;build/api.jar" demo.host.HostApp
~~~

Multi-line Bash commands use `` for line continuation. On PowerShell, write `javac`/`jar` commands on one line or use PowerShell's line-continuation syntax.

To inspect the packaged JAR:

~~~bash
jar --list --file build/provider.jar
~~~

The JAR must contain `demo/provider/UppercaseFormatter.class` and `META-INF/services/demo.api.Formatter`. Do not place `build/provider.jar` on the host's classpath because the parent could load the implementation first, invalidating the loader-generation experiment.

### 9.3. Five intentional experiments

**Experiment A — Remove the SPI descriptor:** Package a JAR containing only the implementation class. `ServiceLoader` will not find the provider without the descriptor; the host reports that it failed to find exactly one provider. This confirms discovery is not equivalent to "having a class in a JAR".

**Experiment B — Change the provider name to a non-existent class:** Point the descriptor to a fake class. When the iterator loads providers, JShell is unrelated; `ServiceLoader` reports a configuration error (`ServiceConfigurationError`) instead of "guessing" a class.

**Experiment C — Test parent/child separation:** Add the provider JAR to the application classpath and observe `getClassLoader().getName()`. Parent delegation may cause the implementation to be defined by the parent; logs will no longer show the expected child generation. This illustrates how deployment classpaths affect identity.

**Experiment D — Create generation 2:** Use a second provider JAR with the same binary class name but different code, creating a new `URLClassLoader` named generation 2. Keep the shared API in the parent and verify two `Class<?>` instances can have different defining loaders. Never try "unloading" merely by calling `close()` while holding old callbacks.

**Experiment E — Stop during an active invocation:** Add a slow-running provider task and call stop concurrently. The host must block new invocations, wait for in-flight work to finish or cancel with a timeout, and only then close the loader. This test matters far more than simply verifying the basic demo prints stdout.

## 10. From Example to a Lifecycle-Aware Plugin Manager

A plugin manager can use these states:

~~~text
DISCOVERED -> VERIFIED -> PREPARED -> ACTIVE
                                   |
                                   v
                                QUIESCING -> STOPPED -> RELEASED
                    [failures are cleaned up and reported clearly by stage]
~~~

This is an **application-designed state machine**, not a built-in feature of `ServiceLoader` or `URLClassLoader`.

- **DISCOVER:** locate artifacts, read plugin descriptors and capabilities, determine API version.
- **VERIFY:** verify hashes/signatures, publisher origin, dependency allowlist, and trust policy. If code is untrusted, route to an appropriate execution boundary.
- **PREPARE:** create loader/module layer/worker, load classes, instantiate, validate contract, start provider, and run health checks. On failure, clean up the candidate.
- **ACTIVE:** publish routing, record plugin ID/version/generation, issue per-request context, measure latency and error rate.
- **QUIESCING:** reject new requests, track in-flight requests, wait or cancel per policy; stop background schedulers/tasks.
- **STOPPED:** invoke lifecycle hooks, cancel listener/event-bus registrations, shut down executors/connections, clean up ThreadLocals/TCCL on the right threads.
- **RELEASED:** close streams/JARs/loaders (or workers), drop caches, provider references, and old generation registries. Never claim "classes unloaded" without JVM evidence.

### Upgrading versions never means overwriting the JAR in place

Use immutable artifact names/paths: ID + version + digest or build ID. When introducing v2, do not overwrite a v1 JAR still open in a loader. Validate v2 during preparation, switch routing atomically, retain a tested rollback path, and clean up v1 only after zero in-flight calls remain.

If v2 fails initialization or health checks, close the v2 candidate and keep v1 serving (if policy permits). If v2 fails after cutover, either roll routing back to a still-valid generation or instantiate a fresh copy of the approved version; never try reusing a closed loader.

### Observability for plugins

At minimum, events `plugin.discovered`, `plugin.verified`, `plugin.loaded`, `plugin.activated`, `plugin.invocation.failed`, `plugin.deactivated`, and `plugin.released` should include plugin ID/version, artifact digest, deployment generation, loader identity/CodeSource, and module where applicable. Correlate invocations with request/trace IDs.

Capture metadata along the lifecycle to avoid repeated reflection on the hot path. Snapshots should store pure data and be discarded on stop; a singleton cache holding `Class<?>` or `ClassLoader` can inadvertently keep an old loader alive.

## 11. Decision Scenarios with Answers and Verification Criteria

### 11.1. Internal formatters changed only during release windows

An application has three fixed formatters written by an internal team on a monthly release cycle; tenants switch formatters via config with no runtime code loading needed.

**Choice:** Strategy/DI or startup SPI. No JavaCompiler/JShell or dynamic loader needed. **Verification points:** unit tests per implementation, API contract integration tests, config switches without source edits, rollback via approved releases.

### 11.2. Approved partner JAR plugins, hot reload without restarts

Partners supply signed JARs with vetted dependencies; the host must swap versions inside the same JVM without dropping active requests.

**Choice:** Shared API + `ServiceLoader` + per-generation loaders, or ModuleLayer when named modules bring clear value. **Verification points:** load/validate v2, route new requests to v2, quiesce v1, stop tasks/listeners, close loader, verify old loaders are not retained across many cycles; rollback never overwrites JARs.

### 11.3. Website allowing arbitrary users to run Java source

The host stores customer data; users may submit infinite loops, file/network operations, and exceptions.

**Choice:** build/run inside an OS-restricted worker process. `JavaCompiler` can run inside the worker, but **never** bring untrusted code into the host JVM simply because compiler and JShell are available. **Verification points:** timeouts and process-tree kills; CPU/RAM/disk quotas; unauthorized file/network access blocked; worker crash does not crash host; per-tenant audit/quotas.

### 11.4. Internal Java console for operations engineers

Requirement is running short Java snippets per session with approved code and proper access policies.

**Choice:** JShell API, parsing input with `SourceCodeAnalysis.analyzeCompletion` before `eval`. If the console has broad impact or must serve untrusted users, execution isolation is still required. **Verification points:** multi-line snippets, diagnostics, session cleanup, timeouts/permissions, and audit logs.

### 11.5. Two plugins with conflicting dependencies

Two plugins require different versions of a library, while the host API must preserve a single class identity.

**Choice:** deliberate loader graph or module layers if JPMS packaging is truly needed. Keep the shared API in the appropriate parent/layer. **Verification points:** no duplicate API classes, no `ClassCastException`, matching dependency versions, unload/stop leaves no stray tasks or static host caches.

### 11.6. Polyglot extensions with independent deployment

Partners write in Java, Go, and Python, needing independent scaling and release schedules separate from the host.

**Choice:** service extension over API/gRPC/messaging, with schema versioning, authentication, retries/timeouts, idempotency, and tracing. **Verification points:** p95/p99 meets SLA, partial outages do not stall the host, rolling deployments preserve backward compatibility, secrets and network segmentation are enforced.

## 12. Common Technical Traps

| Misconception | Consequence | Correct approach |
| --- | --- | --- |
| "ServiceLoader auto-loads new JARs from any path" | Provider not found | Configure classpath/loader/module layer and SPI descriptor |
| "URLClassLoader.close() unloads plugins" | Old instances/threads/listeners stay alive | Quiesce, stop, unregister, close, drop references |
| "JPMS is an OS permission sandbox" | Plugins still hold host process privileges | Use OS/process isolation matching the threat model |
| "Feeding source to JavaCompiler is safe" | Annotation processors/source/bytecode cause side effects | Control toolchain and run in a worker if untrusted |
| "JShell.eval compiles entire projects" | Snippet/file boundaries and session state mishandled | Use SourceCodeAnalysis/Compiler API per intended role |
| "JDK 17 surely includes a JavaScript engine" | ScriptEngine not found | Check/install an explicit engine, pin version and policy |
| "Separate process equals full sandbox" | Same file/network/secret access remains dangerous | Least privilege, quotas, filesystem/network isolation |
| "High score offsets a security failure" | Violates mandatory requirements | Apply hard gates first, weighted scoring second |
| "Logging class name alone suffices for diagnosis" | Cannot distinguish v1/v2 or parent delegation | Log ID/version/generation, CodeSource, defining loader |
| "Hot reload is just swapping a registry pointer" | v1 listeners, ThreadLocals, executors keep running | Manage in-flight calls, stop, and clean up |
| "System.gc() proves unloading" | Flaky tests, false leak conclusions | Track GC roots, JFR/threads/heap across many cycles |
| "Renaming a JAR while in use is always fine" | File handles and OS behavior vary | Immutable artifacts; handle files per lifecycle |

## 13. Operational Measurement and Test Plan

A high theoretical score is not enough for production. Before finalizing, evaluate under realistic workloads:

1. **Latency/throughput:** measure p50/p95/p99, warm-up, throughput at target plugin counts, and tail latency during hot reloads.
2. **Startup/reload:** how long do discover, verify, build/load, health check, cutover, quiesce, and stop take?
3. **Memory:** heap, metaspace, live loader counts, threads, and file descriptors/JAR handles across many reload cycles.
4. **Failure containment:** how do plugin exceptions, deadlocks, infinite loops, network drops, or OOM/worker crashes affect the host?
5. **Compatibility:** changing API methods, module exports/opens, dependency versions, or IPC schemas—are errors caught before activation?
6. **Rollback:** v2 fails in prepare, fails post-cutover, or v1 cleanup fails—is there a path back to an approved artifact without dropping requests?
7. **Trust boundary:** can untrusted code access disallowed files, egress network, secrets, or process/host resources?
8. **Supportability:** are ID/version/generation, CodeSource/loader/module, correlation IDs, diagnostics, and metrics sufficient for root-cause analysis?
9. **Operational limits:** concurrent job scale, release velocity, log/storage budgets, and artifact distribution capacity.
10. **Developer workflow quality:** does adding a new provider take few steps, run tests independently, and offer clear templates/validation?

Never judge solely from one GC cycle or one p50 measurement. Stability and cleanup must be proven across multiple start/stop cycles with concurrency and error paths.

## 14. Architecture Decision Record (ADR) Template for Submission

~~~text
Title: Choosing a Java Extensibility Mechanism for ...

Context:
  - Code supplier, extension format
  - Need to change at build/start/runtime
  - Trust classification and blast radius
  - JDK, dependency, and API compatibility
  - SLA / availability / operational constraints

Hard gates:
  - Security and isolation
  - Stop/kill guarantees
  - Release governance
  - Toolchain/runtime availability
  - API/IPC contract compatibility

Options:
  - Strategy/ServiceLoader
  - Dynamic loader/ModuleLayer
  - Compiler/JShell
  - Worker/service boundary

Evaluation:
  - Weights + scores + benchmark evidence
  - Options eliminated by hard gates

Decision:
  - Selected combination
  - Why it fits requirements and remaining trade-offs

Lifecycle:
  - Verify -> Prepare -> Activate -> Quiesce -> Stop -> Release
  - Rollback and cleanup failure handling

Evidence:
  - Source/demo/test, stdout, latency, memory, security tests
  - Observability, audit, artifact provenance

Review triggers:
  - Code source changes trust level
  - Reload frequency, SLA, or plugin language changes
  - Incident/leak/compatibility breach
~~~

### Exercises and Acceptance Requirements

**Exercise A:** For three internal formatters released via CI/CD, choose between factory/DI or startup SPI. State why hot reload is **not** used, test config changes, and document rollback.

**Exercise B:** For trusted provider JARs needing reload, extend the section 9 example: use distinct v1/v2 JARs, each with its own loader name/generation. Log CodeSource/defining loader of the implementation; test unregistering old listeners/tasks and stopping while in-flight calls run.

**Exercise C:** For untrusted Java source from web users, list at least six hard requirements for the worker: OS identity, CPU/memory/time, process kill, filesystem/network, secrets, and audit/quotas. Present a threat model and negative-path tests.

**Exercise D:** Pick three options that pass hard gates, set weights and ratings, compute the arithmetic scorecard accurately, and attach benchmarks. Explain why scores never replace policy or operational reality.

**Exercise E:** A request still returns v1 results after routing switched to v2. List hypotheses covering parent delegation, cached providers, old listeners, ThreadLocal/TCCL, or in-flight requests; design log fields to rule out each hypothesis.

## 15. Rubric and Completion Checklist

| Item | Suggested Points | Criterion |
| --- | ---: | --- |
| Requirements/trust analysis and hard gates | 25 | Never uses in-process mechanisms as a sandbox when isolation is required |
| Accurate distinction of mechanism roles | 20 | Understands discovery, loaders, compilers, JPMS, IPC |
| Decision backed by matrix and rationale | 20 | Accurate scoring, trade-offs, and clear elimination criteria |
| Java 17 demo, stdout, negative tests | 15 | SPI descriptor, provider JAR, dedicated loader, reproducible results |
| Lifecycle, rollout/rollback/observability | 15 | Generations, quiesce, stop, metrics, and cleanup |
| Presentation and reproducibility | 5 | Clear structure, commands, assumptions, and boundaries |
| **Total** | **100** | |

Final checklist:

- [ ] Does the requirement truly need adding new bytecode while the JVM runs, or merely switching existing strategies?
- [ ] Have code sources been classified by trust with an artifact verification policy?
- [ ] Have hard gates for security, stop/kill, release governance, and API contracts been applied?
- [ ] Are `ServiceLoader` vs classloaders, `JavaCompiler` vs execution sandboxes, and JPMS vs OS permissions kept distinct?
- [ ] Are versioned API/IPC schemas, dependency policies, artifact digests, and rollback in place?
- [ ] Are loader/worker generations and event logs sufficient to diagnose class identity, CodeSource/module?
- [ ] Are quiesce/stop/cleanup implemented for executors, listeners, ThreadLocals, TCCL, and file resources?
- [ ] Do performance, soak, failure-injection, compatibility, and security tests exist?
- [ ] Is the scorecard calculated accurately and backed by benchmarks instead of guesses?
- [ ] Is the decision recorded as an ADR with triggers to revisit when requirements change?

**Conclusion:** The right extensibility mechanism is the one that solves **the right layer of need**, passes hard gates for trust and operations, and only then optimizes performance and complexity. For trusted Java plugins needing reload, SPI + dedicated loaders is often a useful combination; for Java source needing compilation, use JavaCompiler; for interactive snippets, use JShell; for untrusted code or strong failure isolation, use process/service boundaries with OS policies. An architecture is only truly complete when it includes versioning, lifecycle, rollback, observability, and reproducible tests.
