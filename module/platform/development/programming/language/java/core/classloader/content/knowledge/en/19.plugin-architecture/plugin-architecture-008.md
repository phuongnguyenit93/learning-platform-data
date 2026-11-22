# Boundaries of hot reload and state in use

## 1. What does hot reload actually change?

**Plugin hot reload** within the same JVM is typically implemented by creating a new ClassLoader, loading the new version's implementation, and then routing new requests to the new instance without restarting the entire application. However, changing a variable pointing to the plugin **does not automatically update** the code, objects, stack frames, or state that in-flight requests have already acquired earlier.

With `URLClassLoader` and plugin JARs, it is necessary to distinguish:

| Object/task | When switching from v1 to v2 |
|---|---|
| Incoming new requests | Can be routed to the v2 provider |
| Requests already holding a reference to the v1 provider | Still use the v1 object/class unless custom transfer logic exists |
| Runtime class `plugin.EchoPlugin` already defined by the v1 loader | Does not change bytecode to match the new JAR file |
| Static fields of the v1 implementation | Are not automatically copied to static fields of the v2 implementation |
| Sessions, callbacks, streams, threads created by v1 | Are not automatically destroyed or transferred in ownership |
| Databases, files, message brokers | Are not automatically migrated or rolled back because the loader was replaced |
| `URLClassLoader.close()` | Closes lookup sources/JAR handles; does not guarantee class unloading |

**Core boundary:** *Routing future work* is different from *completing, migrating, or cancelling current work/state*. A safe plugin system requires a protocol for **version/generation, pinning, drain/quiescence, migration, and disposal**, not just `new URLClassLoader(...)`.

## 2. Why does a new version need a new defining loader?

The JVM identifies a runtime class by **(binary name, defining loader)**. When `demo.plugin.EchoPlugin` V1 and V2 are **actually defined by two separate loaders**, they can coexist but are not the same `Class<?>`, so V1's objects/static fields do not automatically become V2's. Both must implement APIs/DTOs defined by the **host/shared parent** in order to communicate normally. Calling `loadClass` again on the old loader or replacing the JAR file does not automatically redefine code; instrumentation is a separate mechanism with its own limitations. This distinction forms the basis for the exercise below to examine **state pinned to each generation**.

## 3. Defining a Generation and usage boundaries

A **generation** is a collection sharing the same lifecycle:

- The ID/version of the plugin release and immutable artifact.
- The ClassLoader used to load that release.
- The provider instance and implementation classes of that release.
- A counter of active usages (*leases*, *in-flight*).
- Lifecycle state: ACTIVE, RETIRING, QUIESCENT, CLOSED.
- Resources managed by the generation: streams, callbacks, schedulers, executors, service registrations.

A request **acquires** a generation before starting work and **releases** it once it is completely done using it. On reload, the host switches the source for issuing new leases to v2; v1 transitions to **RETIRING**. Only when v1 has no remaining leases and no out-of-lease activity are v1's class/resource sources closed.

~~~text
Time t0: current = v1
  Request A -> acquire(v1) ------------------------- release(v1)
                        |
Time t1:                +-- reload / current = v2
                            Request B -> acquire(v2) -- release(v2)

v1 does not issue new leases after t1.
v1 can still serve A after t1.
v1 closes only when A has actually completed and v1 resources have been cleaned up.
~~~

**Do not execute `currentPlugin = newPlugin; oldLoader.close();` immediately afterward** while tasks are still using v1. According to Java SE 17, if one thread is loading a class through `URLClassLoader` while another thread calls `close()`, the outcome of that concurrent load is **undefined**. Already-loaded classes may continue to work, but the first attempt needing a new dependency/resource after closing may fail.

## 4. Separating state categories before reload

### 4.1. State residing in the old loader

Object fields, static fields in the implementation, caches, `Class<?>`, reflection metadata, private singletons, and processing sessions of v1 may still be retained by requests or the host. When the v2 implementation class is defined by the new loader, **v2's static fields are different fields**, even if the source code declares them identically.

### 4.2. State owned by the host

Shared DTO/API types, singletons in the parent loader, HTTP routers, session repositories, shared thread pools, generation routing tables, and host caches can survive across reloads. They are **a source of compatibility or a source of leaks**, depending on whether they accidentally retain old instances/classes.

### 4.3. State outside the JVM

Databases, message brokers, files, distributed caches, and external sessions live independently of the ClassLoader. They do not automatically support hot migration. If both v1 and v2 write to a schema undergoing changes, business logic errors can occur even when classloading is completely accurate.

**Conclusion on state:** "v2 code is ready" does not mean "data/sessions/jobs have been safely migrated." Design a dedicated migration protocol with versioned schemas and a rollback policy.

## 5. Java 17+ example: two plugin versions with a shared interface

This experiment will demonstrate via deterministic stdout:

1. Request A acquires plugin v1 before reload and runs with v1.
2. After reload, new request B acquires v2.
3. v1 and v2 have implementation classes with the same FQCN but different runtime identities.
4. Both implementations use **a shared API type** from the parent.
5. Request A, still holding v1, can still invoke v1 after the cutover.
6. v2's static counter starts anew, without inheriting v1's counter.
7. The v1 loader closes only after request A releases its lease; the v2 loader closes when the manager shuts down.

### 5.1. Directory structure

~~~text
hot-reload-demo/
├── api-src/
│   └── demo/api/PluginService.java
├── host-src/
│   └── HotReloadDemo.java
├── v1-src/
│   └── demo/plugin/EchoPlugin.java
├── v2-src/
│   └── demo/plugin/EchoPlugin.java
├── v1-resources/
│   └── META-INF/services/demo.api.PluginService
└── v2-resources/
    └── META-INF/services/demo.api.PluginService
~~~

The two `EchoPlugin.java` files share the same package/FQCN but have different contents and are compiled **into two separate output directories**, then packaged into two separate JARs. At runtime, **only the API and host** are on the application classpath.

### 5.2. Shared API

File **`api-src/demo/api/PluginService.java`**:

~~~java
package demo.api;

public interface PluginService {
    String version();
    String handle(String input);
}
~~~

Do not expose plugin implementation-only classes in the API signatures if the host needs to call across multiple loaders. Any DTOs/exceptions/callbacks exchanged between both sides should also be defined by the shared loader.

### 5.3. Plugin v1

File **`v1-src/demo/plugin/EchoPlugin.java`**:

~~~java
package demo.plugin;

import demo.api.PluginService;

public final class EchoPlugin implements PluginService {
    private static int calls;

    public EchoPlugin() {
    }

    @Override
    public String version() {
        return "v1";
    }

    @Override
    public String handle(String input) {
        return "v1#" + (++calls) + ":" + input;
    }
}
~~~

`calls` is static state belonging to the v1 class. The demo performs sequential calls; `++calls` is not thread-safe if the plugin handles multiple concurrent requests. Production code requires `AtomicInteger` or an appropriate synchronization mechanism.

### 5.4. Plugin v2

File **`v2-src/demo/plugin/EchoPlugin.java`**:

~~~java
package demo.plugin;

import demo.api.PluginService;

public final class EchoPlugin implements PluginService {
    private static int calls;

    public EchoPlugin() {
    }

    @Override
    public String version() {
        return "v2";
    }

    @Override
    public String handle(String input) {
        return "v2#" + (++calls) + ":" + input;
    }
}
~~~

The v2 static counter value starts from 0 in the v2 runtime class, independent of the number of calls v1 has processed.

### 5.5. Service descriptor

Both files:

- `v1-resources/META-INF/services/demo.api.PluginService`
- `v2-resources/META-INF/services/demo.api.PluginService`

each contain exactly one line:

~~~text
demo.plugin.EchoPlugin
~~~

`ServiceLoader.load(PluginService.class, child)` will locate the provider inside the JAR visible to `child`. The `PluginService` interface is defined by the parent loader, so both v1 and v2 share the same API identity.

### 5.6. Host managing leases and generations

File **`host-src/HotReloadDemo.java`**:

~~~java
import demo.api.PluginService;

import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ServiceLoader;

public final class HotReloadDemo {
    private HotReloadDemo() {
    }

    private static final class Generation {
        final URLClassLoader loader;
        final PluginService provider;
        final String version;

        private int leases;
        private boolean retiring;
        private boolean closed;

        private Generation(URLClassLoader loader, PluginService provider) {
            this.loader = loader;
            this.provider = provider;
            this.version = provider.version();
        }

        static Generation load(Path jar) throws IOException {
            Path file = jar.toAbsolutePath().normalize();
            if (!Files.isRegularFile(file)) {
                throw new IllegalArgumentException("Missing JAR: " + file);
            }

            URL[] urls = {file.toUri().toURL()};
            ClassLoader parent = PluginService.class.getClassLoader();
            URLClassLoader child = new URLClassLoader(urls, parent);

            try {
                PluginService plugin =
                        ServiceLoader.load(PluginService.class, child)
                                .findFirst().orElseThrow();
                if (plugin.getClass().getClassLoader() != child) {
                    throw new IllegalStateException(
                            "Provider must be defined by child");
                }
                return new Generation(child, plugin);
            } catch (RuntimeException | Error problem) {
                try {
                    child.close();
                } catch (IOException cleanup) {
                    problem.addSuppressed(cleanup);
                }
                throw problem;
            }
        }

        synchronized void pin() {
            if (retiring) {
                throw new IllegalStateException("Generation retiring");
            }
            leases++;
        }

        synchronized void unpin() throws IOException {
            if (leases <= 0) {
                throw new IllegalStateException("Unbalanced release");
            }
            leases--;
            closeIfIdle();
        }

        synchronized void retire() throws IOException {
            retiring = true;
            closeIfIdle();
        }

        private void closeIfIdle() throws IOException {
            if (retiring && leases == 0 && !closed) {
                closed = true;
                loader.close();
                System.out.println("loader closed: " + version);
            }
        }
    }

    private static final class Session implements AutoCloseable {
        private final Generation generation;
        private boolean closed;

        Session(Generation generation) {
            this.generation = generation;
        }

        synchronized String call(String input) {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }
            return generation.provider.handle(input);
        }

        synchronized Class<?> implementationClass() {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }
            return generation.provider.getClass();
        }

        synchronized Class<?> apiType() {
            if (closed) {
                throw new IllegalStateException("Session closed");
            }
            return generation.provider.getClass().getInterfaces()[0];
        }

        @Override
        public synchronized void close() throws IOException {
            if (!closed) {
                closed = true;
                generation.unpin();
            }
        }
    }

    private static final class PluginManager implements AutoCloseable {
        private Generation current;

        PluginManager(Path initialJar) throws IOException {
            current = Generation.load(initialJar);
        }

        synchronized Session open() {
            if (current == null) {
                throw new IllegalStateException("Manager closed");
            }
            current.pin();
            return new Session(current);
        }

        synchronized void reload(Path jar) throws IOException {
            if (current == null) {
                throw new IllegalStateException("Manager closed");
            }

            // Publish only after the candidate loads successfully.
            Generation next = Generation.load(jar);
            Generation old = current;
            current = next;
            old.retire();
        }

        @Override
        public synchronized void close() throws IOException {
            if (current != null) {
                Generation old = current;
                current = null;
                old.retire();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                    "Usage: HotReloadDemo <v1.jar> <v2.jar>");
        }

        Path v1 = Path.of(args[0]);
        Path v2 = Path.of(args[1]);

        try (PluginManager manager = new PluginManager(v1)) {
            try (Session held = manager.open()) {
                Class<?> oldImpl = held.implementationClass();

                System.out.println("before reload: " + held.call("A"));
                manager.reload(v2);

                try (Session fresh = manager.open()) {
                    System.out.println("after reload: "
                            + fresh.call("B"));
                    System.out.println("same implementation class: "
                            + (oldImpl == fresh.implementationClass()));
                    System.out.println("shared API identity: "
                            + (held.apiType() == fresh.apiType()));
                }

                System.out.println("old pinned: " + held.call("C"));

                // The last lease of v1 ends: the v1 loader now closes.
                held.close();
            }

            try (Session next = manager.open()) {
                System.out.println("new next: " + next.call("D"));
            }
        }
    }
}
~~~

**Properties in the example:**

- `PluginManager.open()/reload()` are both `synchronized`, so selecting the generation and incrementing the lease cannot be interleaved by a cutover.
- A `Session` holds the acquired `Generation`. It **does not** look up `current` again on each call.
- `Session.call()` and `Session.close()` are both synchronized on the same session, preventing closing the same session in the middle of a synchronous call.
- `Generation.retire()` stops issuing new leases and only closes the loader if `leases == 0`.
- `Generation.load` closes the candidate loader if provider discovery fails before publishing; the old current is still retained.
- `PluginManager.reload` loads the candidate **inside the lock**, so new `open()` calls may briefly wait. Production code should consider preparing/health-checking the candidate outside the lock and then committing in a short/atomic step.
- This is a **synchronous model**: leases only track work known to the host, and do not automatically reclaim plugin threads, callbacks, `CompletableFuture`, or external resources.

An error-handling note: in the demo code, if `old.retire()` throws an `IOException` while closing the old loader after cutover, `current` **already points to v2**. Production code must explicitly record the partially successful cutover state and the close failure, rather than inaccurately reporting "reload failed, still on v1".

## 6. Compiling and running with Java 17+

Requires JDK 17+; from the `hot-reload-demo/` directory, create the exact files shown above.

### Bash (Linux/macOS/Git Bash)

~~~bash
mkdir -p build/api build/host build/v1 build/v2 dist

javac -encoding UTF-8 -d build/api \
  api-src/demo/api/PluginService.java

javac -encoding UTF-8 -cp build/api -d build/host \
  host-src/HotReloadDemo.java

javac -encoding UTF-8 -cp build/api -d build/v1 \
  v1-src/demo/plugin/EchoPlugin.java

javac -encoding UTF-8 -cp build/api -d build/v2 \
  v2-src/demo/plugin/EchoPlugin.java

cp -R v1-resources/META-INF build/v1/
cp -R v2-resources/META-INF build/v2/

jar --create --file dist/v1.jar -C build/v1 .
jar --create --file dist/v2.jar -C build/v2 .

java -cp "build/api:build/host" \
  HotReloadDemo dist/v1.jar dist/v2.jar
~~~

### Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force build/api,build/host,build/v1,build/v2,dist | Out-Null

javac -encoding UTF-8 -d build/api api-src/demo/api/PluginService.java

javac -encoding UTF-8 -cp build/api -d build/host host-src/HotReloadDemo.java

javac -encoding UTF-8 -cp build/api -d build/v1 v1-src/demo/plugin/EchoPlugin.java

javac -encoding UTF-8 -cp build/api -d build/v2 v2-src/demo/plugin/EchoPlugin.java

Copy-Item v1-resources/META-INF -Destination build/v1 -Recurse -Force
Copy-Item v2-resources/META-INF -Destination build/v2 -Recurse -Force

jar --create --file dist/v1.jar -C build/v1 .
jar --create --file dist/v2.jar -C build/v2 .

java -cp "build/api;build/host" HotReloadDemo dist/v1.jar dist/v2.jar
~~~

Inspect the JARs:

~~~bash
jar --list --file dist/v1.jar
jar --list --file dist/v2.jar
~~~

Each JAR must contain at least `demo/plugin/EchoPlugin.class` and `META-INF/services/demo.api.PluginService`. Do not package the API inside the plugin JAR, and do not place the plugin JAR on the host classpath of the `java` command.

### Exact stdout

~~~text
before reload: v1#1:A
after reload: v2#1:B
same implementation class: false
shared API identity: true
old pinned: v1#2:C
loader closed: v1
new next: v2#2:D
loader closed: v2
~~~

Explanation:

1. The old session receives v1, so the first output is `v1#1:A`.
2. After reload, the new acquisition receives v2; v2's counter starts at 1.
3. The classes of the two implementations are not equal because they have **different defining loaders**.
4. The API interface that both implementations directly implement is the same `PluginService.class` defined by the parent.
5. The old session still receives `v1#2:C` after current switches to v2.
6. Only when `held.close()` releases the last lease of v1 does `loader closed: v1` appear.
7. The subsequent new acquisition uses v2 and increments v2's counter to 2.
8. When the manager finishes, the v2 loader is closed after the final sessions.

## 7. Cutover does not convert old objects to the new class

The cutover step essentially changes the mapping for **the next lease requests**:

~~~java
// Excerpt from PluginManager.reload.
Generation next = Generation.load(jar);
Generation old = current;
current = next;
old.retire();
~~~

This is not a mechanism for migrating the code of live stack frames or objects. A v1 object remains an instance of the v1 class; static fields of the v1 class still belong to the v1 defining loader. Two implementation classes with the same FQCN defined by two loaders can exist **simultaneously** in the JVM.

Changing `current` does not guarantee that after the cutover point all responses are produced by v2. A v1 request acquired before cutover may still complete afterward. For systems requiring a **strict version switch**, v1 must be drained before publishing v2, or an appropriate session affinity/transaction boundary must be applied.

## 8. Dangerous races in reference counting

A naive model:

~~~java
// Illustrative code that is unsafe under concurrent swap.
Generation generation = current.get();
generation.active.incrementAndGet();
~~~

Between the two lines, the reload thread may switch `current` to v2, observe v1's count at 0, and close v1. Thread A then increments the counter too late and uses an already-closed loader.

The key point is not "having AtomicInteger is enough," but rather that **acquiring a generation and recording its usage must belong to a protocol synchronized** with retire/close.

For example, `synchronized open()/reload()` is a simple, easy-to-prove solution: selecting current and pinning occur within a single critical section; reload cannot retire the same generation between the two operations. Larger systems may use ReadWriteLock, a CAS state machine, epoch reclamation, or a versioned router, but must prove there is no acquire-vs-retire race.

Release must also happen **exactly once**; place it in `try-with-resources` or `finally` so exceptions do not keep old pins held indefinitely. If asynchronous APIs are used, the lease must extend until all work depending on the generation has actually finished.

## 9. Defining "no one is using v1 anymore" carefully

A plugin may remain active after the request handler returns:

- `CompletableFuture`, background callbacks, asynchronous stream processing.
- Scheduled jobs, event bus subscriptions, message consumers.
- Thread pool tasks that are queued or currently running.
- `ThreadLocal` and Thread Context ClassLoader (TCCL) still holding the old loader.
- Listeners, `Class<?>`, reflection `Method`, lambdas, proxies, and host caches.
- Streams/sockets/files/JAR handles opened by the plugin itself.
- Objects returned by plugin v1 and retained by the caller outside the lease.
- Database/cache resources outside the JVM.

If a plugin returns a `CompletionStage` while still performing asynchronous processing, releasing the lease **immediately upon receiving the stage** may close the loader prematurely. Ownership must be retained until actual completion/cancellation, along with cleanup of dependent tasks.

A manager cannot rely on `URLClassLoader.close()` to automatically terminate threads or listeners. Without managing those resources, even if the session ref-count drops to 0, the system is **still not quiescent**.

## 10. Safe quiescing, draining, and disposal

~~~text
ACTIVE v1
   |
   | prepare, validate v2 first
   v
READY v2
   |
   | atomic cutover, v1 stops issuing new leases
   v
RETIRING v1 + ACTIVE v2
   |
   | drain v1 tasks and stop v1 schedulers/listeners
   v
QUIESCENT v1
   |
   | close plugin-owned resources, restore TCCL
   | close URLClassLoader, drop references
   v
CLOSED v1
~~~

Do not treat `ExecutorService.shutdown()` as completion of draining: this method only stops accepting new tasks; you must still call `awaitTermination(...)` or track Futures/in-flight tasks, with a timeout and a clear cancellation policy.

**Do not automatically close the loader immediately upon timeout** if the old code may still execute or load additional classes. If hard-stopping an untrusted plugin is required, a separate process boundary is usually more practical than a ClassLoader within the same JVM.

`URLClassLoader.close()` closes the loader's own class/resource search sources and files opened by the loader, but **does not immediately unload** classes that have already been defined. Still-reachable old classes persist; old code needing an unloaded dependency may fail after close. If class loading occurs concurrently with close, the Javadoc describes the result as **undefined**.

## 11. State migration must be a separate contract

V1 and v2 may have completely different static fields, object graphs, caches, and session data. Java does not copy those fields between two loaders. Do not cast `EchoPlugin` v1 to `EchoPlugin` v2 expecting state transfer: their runtime types are different.

A migration protocol typically includes:

1. Freeze/quiesce the state region that needs to be snapshotted.
2. Export via a stable DTO/schema owned by the host/API.
3. Version and validate the snapshot; transform data if needed.
4. Import/restore into v2 before cutover or according to the session policy.
5. Cutover according to the agreed consistency model.
6. Clean up old state once no v1 requests remain.

For persistent state, prefer a database/event log or a versioned format rather than serializing implementation objects. Java native serialization does not automatically guarantee class loader compatibility, schema migration, or safety for untrusted data.

If v1/v2 run concurrently during overlap, **do not blindly allow** both to write to the same database schema or queue offsets under different contracts. Backward/forward compatibility, idempotency, event versioning, background job ownership, and rollback rules are required.

## 12. Rollback and failures at two different points in time

**Candidate failure before publish:** Close the candidate loader, retain current v1, and report the error. Do not switch the router to an unready v2. The demo does this for provider discovery failures.

**Failure after publish:** The router already points to v2, and there may still be in-flight v1/v2 work. Rollback requires choosing:

- Keep v1 on standby if policy allows and it has not been closed; leases/resources must still be managed.
- Or create a **new v1 generation** from the stored old artifact, without "resurrecting" the old v1 bytecode/class objects.
- If a database migration is already backward-incompatible, rolling back code alone may be unsafe. State restoration, a compensating transaction, or a forward fix is needed.

A close failure of the old loader after cutover does not mean the cutover failed. Log the exact failing **phase** and the true current state, avoiding blind retries that create multiple generations.

## 13. TCCL, ServiceLoader, and API identity

If a framework uses `ServiceLoader.load(service)` or searches for resources via TCCL, set the plugin loader within the invocation scope **on the executing thread itself**, then restore it in `finally`. Plugin provider types must use the parent's shared API; for JPMS, module layers/service declarations also apply. Do not let old worker threads retain V1's TCCL after cutover.

## 14. Leaks and global JVM state

Symptoms to monitor across multiple reloads: requests still returning V1 results, growing classloader/Metaspace usage, lingering worker threads, unclosed JAR handles, and registrations/`ServiceLoader` caches still pointing to V1. Cross-check the request's generation and defining loader before concluding the cutover broke; use thread/heap dumps and GC-root paths to find references retaining V1. Closing a loader does not mean immediate unloading, and a single `System.gc()` call cannot be used to confirm cleanliness.

## 15. When should hot reload be avoided?

A restart/rolling deployment may be safer when:

- The shared API changes in a binary-incompatible way (`NoSuchMethodError`, `AbstractMethodError`, `LinkageError`).
- The plugin uses JNI/native libraries or process-global state that is hard to tear down.
- Many long-lived sessions require guaranteeing a single consistent version.
- Schema migration does not support coexistence between v1 and v2.
- The plugin spawns threads and side effects that the host cannot control.
- Resource ownership is unclear; quiescence cannot be proven.
- System-wide transactional rollback or strong security boundaries are required.

Do not force hot reload if the business value does not outweigh the lifecycle and consistency complexity.

## 16. Implementation checklist

1. Do the shared API/DTOs/exceptions have **a single runtime identity** defined by the common loader?
2. Does each version have its own immutable artifact, loader, and generation ID?
3. Is the candidate loaded/validated/health-checked before publishing?
4. Are lease acquisition + selecting current synchronized with retire/cutover?
5. Does the lease cover all synchronous and asynchronous work that actually uses the plugin?
6. Is state migration/serialization versioned with a verifiable schema?
7. Are new tasks stopped, old tasks drained, and callbacks/threads/TCCL cleaned up?
8. Are close failures, timeouts, stuck tasks, and phase-based rollbacks handled?
9. Does data outside the JVM allow v1/v2 coexistence?
10. Are per-generation metrics and leak detection sufficient to confirm cleanup?
11. Is there a restart fallback policy when hot reload is unsafe?

## 17. Self-check

**Question 1.** Request A has already acquired plugin v1 and then the host reloads v2. Does A automatically run v2 code?

**Answer:** No. A's reference and v1 runtime class do not automatically change.

**Question 2.** Why do the two `demo.plugin.EchoPlugin` classes from v1/v2 have the same name yet `==` is false?

**Answer:** They are defined by two different defining loaders.

**Question 3.** Does v2 inherit v1's static field `calls`?

**Answer:** No. The static fields of the two runtime classes are independent; transferring state requires explicit migration.

**Question 4.** After current switches to v2, can `oldLoader.close()` be called immediately?

**Answer:** Only when v1 is truly quiescent, with no tasks still needing to load classes/resources or using sources owned by the loader; in-flight work must drain.

**Question 5.** A `CompletableFuture` has not completed yet, though the handler has returned; can the lease be released?

**Answer:** No, if the asynchronous work still depends on the plugin; the lease must extend until usage ends.

**Question 6.** If the v2 candidate fails before publishing, what should be done?

**Answer:** Clean up the candidate and retain current v1 without switching routing to the unready v2.

**Question 7.** Is it guaranteed that no v1 responses will appear after cutover?

**Answer:** No, if a v1 request was already pinned. A strict drain or session-affinity policy is needed if business requirements demand it.

## 18. Official references

- [Java SE 17 — URLClassLoader.close](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close()) — close, JAR handles, and concurrent class loading.
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — class identity, delegation.
- [Java SE 17 — ServiceLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) — provider discovery.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html) — shutdown and awaitTermination.
- [Java SE 17 — AutoCloseable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/AutoCloseable.html) — scoped resources/leases.
- [JVMS 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) — loading, linking, initialization.

**Key takeaway:** Hot reload using a new ClassLoader only changes where **future requests** obtain code. Work currently using v1 must be **pinned, drained, and released at the right time**; state migration and side effects outside the JVM must have a separate protocol.
