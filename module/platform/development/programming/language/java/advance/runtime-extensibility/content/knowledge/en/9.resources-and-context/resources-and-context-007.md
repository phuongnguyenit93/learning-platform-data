# Closing Streams and Avoiding Retaining Resources or Context Beyond Plugin Lifecycle

## 1. The Problem in a Runtime-Extensible System

A host application can load a plugin from a JAR, let the plugin read resources, use a host-provided context object, and then stop the plugin when configuration or versions change. Every such cycle creates **lifecycle-bound** resources: file streams, JAR handles, sockets, executors, listeners, classloaders, context objects, and indirect references from threads.

If a plugin opens an `InputStream` without closing it, retains the context of a finished request, or leaves a thread pointing to an old classloader, the host can suffer file descriptor leaks, inability to replace JARs on certain operating systems, memory bloat, stale configuration usage, continued execution of stopped plugin code, or uncollectable old classloaders.

The goal of this lesson is managing **the right timing**, not merely remembering to call a `close()` method:

- **Operation lifecycle:** resources serving a single read/write. Open within a narrow scope and close immediately after consumption, even if the operation throws an exception.
- **Plugin lifecycle:** plugin-owned components that live across multiple calls, such as executors, schedulers, listeners, sockets, or registrations. Stop and release them before discarding the plugin.
- **Context lifecycle:** data/capabilities granted by the host may only be valid for a single request or plugin session. The plugin must not arbitrarily store them in `static` fields, caches, or background tasks.
- **Classloader lifecycle:** the host may use a dedicated loader to load the plugin JAR. Close the loader after stopping related work and clear references holding it; `close()` does not automatically unload classes still in use.

Here "context" has two meanings to distinguish: **PluginContext** (the host-provided object, e.g., operation ID and permitted services) and the **thread context classloader** (TCCL, the value on `Thread` assisting class/resource/service lookup). Each has its own cleanup rules.

## 2. Ownership: Who Opens, Who Closes, and Who May Retain?

Practical rule: **the party that creates and owns a resource closes it; a party that only borrows it must not close a shared resource unless the contract transfers ownership**.

| Resource | Typical Owner | When to Terminate | What to Avoid |
| --- | --- | --- | --- |
| `InputStream` from `getResourceAsStream` to read config | Caller opening the resource, usually the plugin | End of read operation | Storing in a field or forgetting to close on error paths |
| `Reader`, `BufferedReader`, `JarFile`, `ZipFile` | Party opening the reader/file | Once consumed | Returning a lazy stream outside after closing the source |
| `URLClassLoader` created by plugin manager | Host/plugin manager | After plugin quiesces, stops, and halts tasks | Assuming `close()` destroys all live objects/classes |
| Executor/timer/socket created by plugin | Plugin | Plugin's `stop()`/`close()` | Letting background tasks use plugin after unload |
| Listener/callback registered by plugin with host | Registering party or plugin manager per contract | When plugin stops | Host registry continuing to hold the plugin instance |
| `PluginContext` passed by host per request | Host owns, plugin borrows | End of call or granted lease | Caching the whole context, using after request expires |
| TCCL on thread temporarily swapped by host | Code swapping it on that thread | End of call block, inside `finally` | Thread pool continuing to point to old plugin loader |
| Logger, client, or executor managed and shared by host | Host | Per host lifecycle | Plugin closing a host service and breaking other plugins |

For example: if a plugin is permitted to receive an `InputStream` from a factory under a **caller owns stream** contract, the plugin closes the stream. But if the host passes a shared `DataSource` for the plugin to run queries, the plugin must not close the `DataSource` when finishing a request. Access rights and closing rights are two distinct permissions.

When designing a plugin API, explicitly document: whether context may be retained long-term or used only immediately, whether returned objects remain valid after `execute()`, whether `close()` is idempotent, and how the host handles in-flight calls during shutdown.

## 3. Reading JAR Resources with the Right Classloader and Scope

Two common APIs:

~~~java
// Illustrative snippet placed inside a plugin implementation class.
InputStream first = getClass().getResourceAsStream("/demo/plugin/message.txt");
InputStream second = getClass().getClassLoader()
        .getResourceAsStream("demo/plugin/message.txt");
~~~

This is **illustrative code**; if used, both streams must be wrapped in try-with-resources or closed properly. Naming rules:

- `Class.getResourceAsStream("/demo/plugin/message.txt")`: leading slash is an absolute resource path from the classpath/module root.
- `Class.getResourceAsStream("message.txt")`: name relative to the class's package.
- `ClassLoader.getResourceAsStream("demo/plugin/message.txt")`: passed resource name normally has no leading slash.
- Calls may return `null` if not found; check for missing resources and report a clear cause.

When a plugin has its own classloader, using `getClass().getClassLoader()` ties resource lookup to the loader that defined the plugin class. Mistakenly using the system loader or TCCL may fail to see the plugin JAR. Even so, parent-first delegation can still find a same-named resource in a parent; avoid generic names and prefer dedicated namespaces, such as `demo/plugin/message.txt`.

Safe read pattern for small resources:

~~~java
// Illustrative method; requires imports java.io.* and java.nio.charset.StandardCharsets.
String readText(ClassLoader loader, String path) {
    try (InputStream in = loader.getResourceAsStream(path)) {
        if (in == null) {
            throw new IllegalArgumentException("Missing resource: " + path);
        }
        return new String(in.readAllBytes(), StandardCharsets.UTF_8);
    } catch (IOException ex) {
        throw new UncheckedIOException("Cannot read: " + path, ex);
    }
}
~~~

`try-with-resources` invokes `close()` when exiting the block, including on exception paths. If `in` is `null`, Java skips calling `close()` and the check branch throws the error. When both reading and closing fail, the close exception appears in the primary exception's suppressed exceptions list (`Throwable.getSuppressed()`). Therefore, do not replace the above with a manual `open → read → close` sequence lacking `finally`.

`InputStream.readAllBytes()` works for small, trusted files; if the source is large or externally supplied, cap the bytes read, use buffering, and enforce resource limits. Do not return an `InputStream` or lazily read `Stream<String>` from a closed block. If streaming across boundaries is genuinely required, the contract must transfer stream ownership to the receiver and require the receiver to call `close()`; for small configuration data, returning a `String` or materialized data is usually simpler.

Other resources must also follow scoped closing: `Files.lines(path)`, `Files.list(path)`, and `Files.walk(path)` return a `Stream` that can hold I/O resources, so use them in try-with-resources; `JarFile`/`ZipFile` must also be closed. Do not hold open JAR handles in caches if the plugin does not need them across calls.

## 4. Runnable Java 17 Program: Plugin JAR and Resource

The example consists of a **shared API**, a **standalone plugin JAR** containing a text resource, and a **host** that loads the plugin itself. It demonstrates reading and closing the stream in each invocation, using context within the `execute` scope, calling `plugin.close()`, restoring the TCCL, and closing the `URLClassLoader`.

### 4.1. Directory Structure

~~~text
plugin-resource-example/
  src/
    api/demo/api/Plugin.java
    api/demo/api/PluginContext.java
    plugin/demo/plugin/GreetingPlugin.java
    plugin-resources/demo/plugin/message.txt
    host/demo/host/HostApp.java
  build/                     (created during compilation)
~~~

The API defines only the contract; the host **does not** import `GreetingPlugin`. The plugin JAR does not include a copy of `demo.api.Plugin` to prevent two distinct definitions of the same interface between the host and plugin loader.

### 4.2. Shared Host-Owned API

**`src/api/demo/api/Plugin.java`**

~~~java
package demo.api;

public interface Plugin extends AutoCloseable {
    void execute(PluginContext context);

    @Override
    void close();
}
~~~

**`src/api/demo/api/PluginContext.java`**

~~~java
package demo.api;

import java.util.Objects;

public record PluginContext(String invocationId) {
    public PluginContext {
        Objects.requireNonNull(invocationId, "invocationId");
    }
}
~~~

`PluginContext` holds an ID for a single invocation and uses a Java 17 record. The plugin may only use it while handling the invocation. If in practice the context carries host services or callbacks, the contract must specify the validity window; a `record` only guarantees that the `String` field reference is immutable, not that every object contained in a record is automatically immutable.

### 4.3. Implementation Reading Its Own JAR's Resource

**`src/plugin/demo/plugin/GreetingPlugin.java`**

~~~java
package demo.plugin;

import demo.api.Plugin;
import demo.api.PluginContext;
import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

public final class GreetingPlugin implements Plugin {
    private boolean closed;

    public GreetingPlugin() {
    }

    @Override
    public void execute(PluginContext context) {
        if (closed) {
            throw new IllegalStateException("Plugin already closed");
        }

        try (InputStream in = getClass().getClassLoader()
                .getResourceAsStream("demo/plugin/message.txt")) {
            if (in == null) {
                throw new IllegalStateException("Missing message.txt");
            }

            String message = new String(
                    in.readAllBytes(), StandardCharsets.UTF_8).strip();
            System.out.println(
                    "plugin[" + context.invocationId() + "]: " + message);
        } catch (IOException ex) {
            throw new UncheckedIOException(
                    "Reading plugin message failed", ex);
        }
    }

    @Override
    public void close() {
        if (!closed) {
            closed = true;
            System.out.println("plugin closed");
        }
    }
}
~~~

**`src/plugin-resources/demo/plugin/message.txt`**

~~~text
Xin chào từ JAR
~~~

The stream is opened inside `execute()` and closed immediately when done, never stored in a field. The resulting string is decoupled from the stream. The file may have a trailing newline; `strip()` removes it for stable output. The plugin reads `context.invocationId()` only during processing and does not retain the context across sessions.

The `closed` field is a single-threaded example. If the host allows `execute()` and `close()` concurrently, you need synchronization and tracking of in-flight calls; a plain `boolean` is not safe enough in a multi-threaded setting. `close()` here merely prints a message because the plugin owns no long-lived resources; in real products, add proper cleanup for any executors, listeners, or connections the plugin actually creates.

### 4.4. Host Restores Context and Closes Loader

**`src/host/demo/host/HostApp.java`**

~~~java
package demo.host;

import demo.api.Plugin;
import demo.api.PluginContext;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;

public final class HostApp {
    private HostApp() {
    }

    public static void main(String[] args) throws Exception {
        Path jar = Path.of("build/greeting-plugin.jar");
        if (!Files.isRegularFile(jar)) {
            throw new IllegalStateException("Plugin JAR missing: " + jar);
        }

        ClassLoader original =
                Thread.currentThread().getContextClassLoader();

        System.out.println("host started");
        URL[] urls = {jar.toUri().toURL()};

        try (URLClassLoader pluginLoader = new URLClassLoader(
                urls, HostApp.class.getClassLoader())) {
            try {
                Thread.currentThread()
                        .setContextClassLoader(pluginLoader);

                Class<?> type = Class.forName(
                        "demo.plugin.GreetingPlugin", true, pluginLoader);
                Plugin plugin = (Plugin) type
                        .getDeclaredConstructor().newInstance();

                try (plugin) {
                    plugin.execute(new PluginContext("req-001"));
                }
            } finally {
                Thread.currentThread()
                        .setContextClassLoader(original);
            }
        }

        System.out.println(
                "tccl restored=" +
                (Thread.currentThread().getContextClassLoader() == original));
        System.out.println("host finished");
    }
}
~~~

Here the host creates a loader containing only the plugin JAR with the application classloader as its parent. Host and plugin share `demo.api.Plugin` from the parent. `Class.forName(..., true, pluginLoader)` selects the loader and initializes the class; reflection creates the instance via the public constructor.

Cleanup sequence on a successful run:

1. `plugin.execute` opens and closes the read stream internally.
2. `try (plugin)` calls `plugin.close()` before leaving the plugin scope.
3. `finally` restores the TCCL **on the very thread that changed it**.
4. The outer try-with-resources calls `pluginLoader.close()` once the plugin is finished.
5. The host prints confirmation that the TCCL returned to the original loader object.

If `execute()` or `close()` throws an exception, the `finally`/try-with-resources blocks still execute. The final success lines only run if the program does not let an exception escape `main`. Never swallow cleanup exceptions and falsely report success.

### 4.5. Compiling and Running

In the `plugin-resource-example` directory, after creating the five files above, use JDK 17+ with Bash:

~~~bash
mkdir -p build/api build/plugin build/host

javac --release 17 -encoding UTF-8 \
  -d build/api \
  src/api/demo/api/Plugin.java src/api/demo/api/PluginContext.java
jar --create --file build/plugin-api.jar -C build/api .

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar \
  -d build/plugin src/plugin/demo/plugin/GreetingPlugin.java
jar --create --file build/greeting-plugin.jar \
  -C build/plugin . -C src/plugin-resources demo/plugin/message.txt

javac --release 17 -encoding UTF-8 \
  -cp build/plugin-api.jar \
  -d build/host src/host/demo/host/HostApp.java

java -cp "build/host:build/plugin-api.jar" demo.host.HostApp
~~~

**Exact stdout when JAR/resource are complete:**

~~~text
host started
plugin[req-001]: Xin chào từ JAR
plugin closed
tccl restored=true
host finished
~~~

Windows PowerShell command uses semicolons to separate classpath entries:

~~~powershell
java -cp "build/host;build/plugin-api.jar" demo.host.HostApp
~~~

The multi-line `javac`/`jar` commands above use backslashes for line continuation per Bash syntax; in PowerShell you can put each command on a single line. The host does not place `build/greeting-plugin.jar` on the compile classpath or application classpath; the host loads that JAR via `URLClassLoader`.

To verify packaging:

~~~bash
jar --list --file build/greeting-plugin.jar
~~~

You should find `demo/plugin/GreetingPlugin.class` and `demo/plugin/message.txt`. If you forget to include the resource in the JAR, the missing-file branch will report `Missing message.txt`; `plugin.close()` and TCCL restoration still happen before the error escapes `main`. This code demonstrates the closing control flow, yet **does not prove the classloader has been garbage-collected/unloaded**.

## 5. How Is Context Outliving the Plugin Dangerous?

### 5.1. Thread Context Classloader (TCCL)

The TCCL is a reference field on `Thread`, often used by libraries/frameworks to find resources, classes, or services. When a host temporarily swaps the TCCL for a plugin and returns the thread to a pool without restoring it, a long-lived thread can keep holding the plugin loader and mistakenly access stale libraries.

**Incorrect snippet** (assuming `pluginLoader`, `plugin`, and `context` exist):

~~~java
Thread.currentThread().setContextClassLoader(pluginLoader);
plugin.execute(context);  // If this throws, TCCL still points to pluginLoader.
~~~

Better:

~~~java
ClassLoader old = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    plugin.execute(context);
} finally {
    Thread.currentThread().setContextClassLoader(old);
}
~~~

Restoration must happen on the **same thread** that changed the TCCL. Another thread cannot clear a worker's TCCL simply by changing its own TCCL. `URLClassLoader.close()` also does not automatically clear a TCCL still pointing to the old loader.

### 5.2. ThreadLocal and Per-Request Data

Host thread pools commonly reuse the same thread for different requests. `ThreadLocal` binds values to the thread, not automatically to the request lifecycle; if it retains context, tokens, callbacks, or plugin objects, it can leak data or use stale values.

When `ThreadLocal` is truly needed, set and clean up within the same scope:

~~~java
// Illustrative; CONTEXT and processRequest() are defined by the application.
CONTEXT.set(context);
try {
    processRequest();
} finally {
    CONTEXT.remove();
}
~~~

Prefer passing context explicitly via parameters whenever possible. `remove()` must run on the **thread that called `set`**; removing from a coordinator thread does not clear values residing in other worker threads. A `PluginContext` object borrowed from the host must not be stored by the plugin in a `static` field or a long-lived future's closure.

### 5.3. Executors, Threads, and Scheduled Tasks

Newly created threads can inherit the creating thread's TCCL. If a plugin starts an executor while the current thread points to the plugin loader, worker threads may retain that loader for the lifetime of the executor. Lambdas/Runnables in queues can also capture plugin instances or request contexts.

For plugin-owned executors, `close()`/`stop()` must block new work, cancel recurring schedules, call `shutdown()`, wait for `awaitTermination` with a defined timeout, and then apply a policy if tasks are still running. `shutdownNow()` only attempts to interrupt threads and does not guarantee tasks that ignore interrupts will stop immediately. Before closing the loader, ensure no tasks remain using plugin classes or resources.

If the executor is **host**-provided, a plugin must not arbitrarily shut down the shared executor; the host must provide an API to cancel tasks **belonging to this plugin**. Every task must clean up its executing thread's TCCL and `ThreadLocal` in `finally`.

### 5.4. Listeners, Callbacks, Registries, and Caches

A singleton host event bus holding a callback registered by a plugin keeps the plugin instance alive. Similarly, `Map<Class<?>, ...>`, `Method`, `ServiceLoader`, provider lists, or reflection result caches can retain classes and defining classloaders that the plugin manager thought were discarded.

When stopping a plugin, unregister listeners, close registration handles, or let the host remove all entries by plugin ID. `ServiceLoader.reload()` clears the provider cache of **that `ServiceLoader` instance**, yet does not clear references the host saved in other lists, registries, or callbacks.

A classloader can normally only be garbage-collected when no live references remain to the associated classes/loader. Thus `URLClassLoader.close()` is necessary for owned loaders, but **not sufficient** to guarantee unloading; there is no guarantee GC happens immediately.

### 5.5. PluginContext Is a Time-Limited Capability

Real-world contexts may carry configuration, request ID, principal, logger, service proxies, transactions, or host-supplied callbacks. If a plugin retains the context after `execute()` returns, data/access permissions may expire and reference chains can pin the whole request/host.

An appropriate contract rule:

> An invocation's context is valid only for that invocation. The plugin may read and use it within the granted scope. When asynchronous work is needed, pass only a small, immutable, retention-safe snapshot, or use an async API whose lifecycle and explicit revocation are managed by the host.

Do not close shared services contained in the context, do not push the entire context into a global cache, and do not keep callbacks active after the plugin has been stopped. If the host genuinely grants a long-lived capability, it must have an explicit scope, revocation mechanism, and owner.

## 6. Designing Plugin Lifecycle from Start to Unload

A suggested lifecycle flow:

~~~text
NEW -> STARTING -> ACTIVE -> QUIESCING -> STOPPED -> RELEASED
                       \-> FAILED -> CLEANUP
~~~

This is an **architectural model**, not a built-in JVM state machine. Responsibilities:

1. **STARTING:** create the loader and plugin instance, check API/version, open required resources. On partial failure, clean up everything created so far.
2. **ACTIVE:** issue properly scoped contexts, track active invocation counts, close per-operation streams, track plugin-owned tasks and registrations.
3. **QUIESCING:** reject new calls, detach entry points/listeners, wait for in-flight calls to finish or cancel them per contract. Do not close the classloader while tasks are still using it.
4. **STOPPED:** invoke the plugin's `close()`/`stop()` hook, shut down private executors, release sockets, watchers, timers, `ThreadLocal`s, and contexts on used threads.
5. **RELEASED:** remove references from registries/caches, close the loader if host-owned, log cleanup errors, and ensure no further operations target the old plugin.

When resources depend on each other, close them in **reverse order of acquisition**, similar to try-with-resources. The plugin object typically must stop before the loader because it may still need to read resources during shutdown.

**Safe state when `stop` races with `execute`:** block new calls, track in-flight calls, drain/cancel per policy, and only then allow closing. A plain boolean `closed` flag is insufficient if multiple threads read/write concurrently. Use synchronization, reference counting/invocation scopes, or proper lifecycle management tools. Never catch all `Throwable`s and declare the plugin stopped while threads/registrations remain active.

## 7. Common Errors and How to Check

| Symptom | Possible Root Cause | How to Address |
| --- | --- | --- |
| Cannot reliably replace old JAR; handle count rises | `InputStream`/`JarFile` left open or `URLClassLoader` unclosed | Use try-with-resources; inspect open file handles and stop order |
| Plugin reports missing resource | Resource not packaged, wrong path, wrong loader used | `jar --list --file`; verify `/` and classloader |
| Intermittent errors during reload | Old tasks still running when loader closes or registry changes | Quiesce and await in-flight tasks before closing |
| Heap/metaspace grows after multiple cycles | TCCL, `ThreadLocal`, listeners, or `Class`/`Method`/provider caches retain loader | Inspect thread dumps, heap dominators, classloader identity |
| New request sees old context | `ThreadLocal` not removed on thread pool | `try/finally` set/use/remove on the actual worker thread |
| Other host components get disconnected | Plugin closed a client/executor shared by the host | Separate ownership; close only self-owned resources |
| Plugin stopped yet callbacks still fire | Event bus, timer, or future still holds callback/instance | Unregister, cancel schedules, block new calls |
| GC has not unloaded classes despite `close` | References still alive or GC has not run yet | Measure retained references across multiple cycles; never infer from a single GC |

When testing for leaks, do not look only at total heap at a single point in time. The JVM may keep memory regions reserved for reuse. Observe **thread counts, file descriptors, live classloaders, heap reference chains, and task states** across multiple start/stop cycles, including failure branches.

## 8. Checks to Ensure Proper Cleanup

- **Successful read path:** run the example in section 4 and verify the exact five stdout lines; ensure the resource closes as soon as `execute` finishes.
- **Missing resource:** package the plugin JAR without `message.txt` and verify a contextual error message; `close()` and `finally` still execute. Error scenarios must not expect the success stdout.
- **I/O error:** use a mock/fake `InputStream` that throws `IOException` on read and verify `close()` is still invoked and the primary error is not lost due to a close error.
- **Context/TCCL:** invoke the plugin on a thread pool, including exception cases, then verify TCCL is restored and `ThreadLocal` holds no previous request values.
- **Stop under active call:** run a slow operation, trigger `stop` concurrently, verify the loader is not closed prematurely and no new calls are accepted after quiescing.
- **Repeated cycles:** start/execute/stop multiple times, verify no lingering background tasks or callbacks remain, references to old loaders drop, and handle counts do not grow.
- **Ownership:** plugin closes exactly the resources it created; does not close host executors/services shared across plugins.
- **JAR metadata:** run `jar --list` to verify resources are packaged properly; verify host code depends only on the shared API.

## 9. Operational Checklist

- [ ] Every `InputStream`, `Reader`, and JAR handle has a clear owner and closing point.
- [ ] `try-with-resources` encloses operations that can throw; lazy streams never outlive closed sources.
- [ ] Resources are looked up with the appropriate loader and exact relative/absolute names.
- [ ] `PluginContext` is not retained past the granted request or session; host services/callbacks are not held past expiration.
- [ ] TCCL is restored in `finally` on the same thread; `ThreadLocal` is removed.
- [ ] Plugin executors/timers/schedulers support stopping, canceling schedules, and awaiting completion with timeouts.
- [ ] Plugin listeners, registrations, caches, and `ServiceLoader` providers have references dropped by the host on stop.
- [ ] Host blocks new calls and drains/cancels in-flight calls before closing the plugin/loader.
- [ ] Do not confuse `URLClassLoader.close()` with immediate class unloading.
- [ ] Test both failure paths and multiple reload cycles, observing actual file handles, threads, and references.

**Conclusion:** Reading resources properly solves only part of runtime extensibility. Safety when stopping or replacing plugins depends on closing short-lived streams, terminating long-lived resources, restoring context on the right thread, and dropping host-to-plugin references. Explicit ownership and lifecycle contracts allow the host to swap plugins without unintentionally pinning an older version.