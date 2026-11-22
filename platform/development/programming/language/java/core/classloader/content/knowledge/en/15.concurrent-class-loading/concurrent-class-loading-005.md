# Avoiding the race condition between `findLoadedClass` and `defineClass`

> **Java Core → ClassLoader → Concurrent Loading.** This lesson focuses on a very specific bug in custom class loaders: **two threads both see a binary name as not yet loaded and both attempt to define that class in the same loader**. The goal is to understand the invariant that must be preserved, how the default `ClassLoader.loadClass` coordinates concurrency, when to use `getClassLoadingLock`, `registerAsParallelCapable`, how to reproduce the bug in a controlled manner, and how to test when implementing a plugin/child-first loader.

## 1. The most important invariant

For a normal runtime class/interface, type identity is based on the pair **(binary name, defining class loader)**. For each binary name, a defining loader must avoid attempting to `defineClass` the same class **twice** within its own namespace. Loading one name by two threads concurrently must result in **the same `Class<?>` object** if both succeed, rather than two duplicate definitions of the same name.

The APIs:

- `findLoadedClass(String name)`: returns the `Class<?>` recorded by the VM with this loader as an **initiating loader** of the corresponding name, or `null` if not yet seen. It is not a **reservation** operation or a lock command on the class name.
- `defineClass(String name, byte[] b, int off, int len)`: converts bytecode into a runtime `Class<?>` defined by the current loader. Defining a duplicate binary name within the same loader is not permitted; the JVM typically throws `LinkageError`.
- `loadClass(String name, boolean resolve)`: according to the default implementation, performs a sequence of operations consisting of checking if already loaded → delegating to the parent → `findClass` if needed → `resolveClass` when the `resolve=true` flag is set, synchronized using `getClassLoadingLock(name)`.
- `getClassLoadingLock(String name)`: provides the appropriate lock for **the entire critical section** of a class loading request. If the loader is **not parallel capable**, the lock is the loader itself; if registered as parallel capable, it is typically a dedicated lock for the binary name.
- `registerAsParallelCapable()`: declares that the subclass supports concurrent class loading with proper locking. It **does not automatically fix an unsynchronized `loadClass` override**.

**Key point:** `findLoadedClass(name) == null` at a point in time **does not grant exclusive rights** to call `defineClass(name, ...)`. Checking and defining must be coordinated within a consistent locking/ownership protocol.

## 2. How does the check-then-act race happen?

Incorrect pattern:

~~~java
// BUG ILLUSTRATION ONLY: inside a ClassLoader subclass.
// Do not use this pattern in a production loader.
Class<?> c = findLoadedClass(name);
if (c == null) {
    byte[] bytes = fetchClassBytes(name);
    c = defineClass(name, bytes, 0, bytes.length);
}
return c;
~~~

`fetchClassBytes` is a hypothetical method. When two threads enter `loadClass` on **the same loader instance**, the following can happen:

~~~text
                 Thread T1                       Thread T2
                    |                               |
findLoadedClass(X) -> null                         |
                    |               findLoadedClass(X) -> null
                    |                               |
       fetch bytes(X)                       fetch bytes(X)
                    |                               |
         defineClass(X) OK                    |
                    |                          defineClass(X)
                    |                               |
                    |                            LinkageError
                    v
          Class<?> X already exists
~~~

This is a **time-of-check to time-of-use (TOCTOU)** race: the `null` result is only valid at the moment of reading; there is no assignment between the two threads determining which one is the **sole** definer of the class.

**Do not treat `LinkageError` as an alternative synchronization mechanism.** The JVM protects the type identity invariant by rejecting duplicate definitions, but the application can fail randomly under load. In particular, you should not catch `LinkageError`, treat it as `ClassNotFoundException`, and silently try another loader: doing so can mask corrupted bytecode, loader constraints, or version conflicts.

### 2.1. What does not fix the race

- `volatile boolean loaded` does not make the “check → bytes → define” sequence atomic.
- `ConcurrentHashMap<String, byte[]>` only makes the bytes map thread-safe; it does not automatically protect the `defineClass` operation if both sides pass the check concurrently.
- Calling `Thread.sleep(...)` to stagger timing is not a fix; it only changes the probability of the error occurring.
- Placing `synchronized` on `findClass` alone is not guaranteed to be sufficient if another place calls `defineClass` outside the same lock, or if `loadClass` makes incorrect recursive/delegation calls.
- Registering `registerAsParallelCapable` while manually overriding `loadClass` and omitting `synchronized(getClassLoadingLock(name))` is still wrong.
- `resolveClass(c)` only links the class; it does not replace protecting `defineClass` and does not run the initializer.

## 3. How the default `ClassLoader` solves the problem

Java `ClassLoader` recommends **overriding `findClass` whenever possible**, rather than overriding all of `loadClass`. According to the Javadoc, the default implementation of `loadClass(name, resolve)` is essentially:

~~~java
// PSEUDOCODE: illustrates the idea; not source code to copy.
synchronized (getClassLoadingLock(name)) {
    Class<?> c = findLoadedClass(name);
    if (c == null) {
        try {
            c = parentLoadClass(name);
        } catch (ClassNotFoundException notInParent) {
            // Will look in the current loader.
        }
        if (c == null) {
            c = findClass(name);
        }
    }

    if (resolve) {
        resolveClass(c);
    }
    return c;
}
~~~

`parentLoadClass` here is a **placeholder notation** to explain delegation to the parent/VM bootstrap; it is not a method in the `ClassLoader` API. The key takeaway to keep in mind is that **all** of checking, delegation, finding, and optional linking happen under **the same loading lock**.

With two threads concurrently requesting binary name X:

1. T1 acquires the lock for X.
2. T2 waits for the lock for X, instead of also seeing `findLoadedClass(X)==null` inside the same protected region.
3. T1 locates the class from the parent or calls `findClass` to create a class, and then returns.
4. T2 acquires the lock, re-checks `findLoadedClass(X)` after T1 completes, and receives the exact class that was loaded/recorded.
5. Both succeed and return **the same `Class<?>`**. If there is an actual error with bytecode/parent/linking, the appropriate error must still be handled, not “swallowed” by the lock.

This is why the **check and define** steps must remain together inside the critical section, not:

~~~java
// WRONG: checking outside the lock and not rechecking before define.
Class<?> c = findLoadedClass(name);
if (c == null) {
    synchronized (getClassLoadingLock(name)) {
        c = defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

Both T1 and T2 may have seen `null` before the lock; as each thread acquires the lock in turn, T2 will still call `defineClass` again. If using a double-check pattern, you **must recheck** inside the proper lock, though with custom class loaders it is usually clearer to put the entire block under the lock.

## 4. The safest approach: only override `findClass`

If you only need to read bytecode from a custom directory/JAR/service, keep the default `loadClass`:

~~~java
public final class BytesLoader extends ClassLoader {
    public BytesLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        byte[] bytes = readBytesFromTrustedStore(name);
        return defineClass(name, bytes, 0, bytes.length);
    }

    private byte[] readBytesFromTrustedStore(String name)
            throws ClassNotFoundException {
        throw new ClassNotFoundException(name); // Illustrates the extension point.
    }
}
~~~

The file `BytesLoader.java` compiles on Java 17+, but the `readBytesFromTrustedStore` method is left **for illustration only**: it always reports not found, rather than being a real byte-loading implementation. For a real project, replace this method with logic to read bytes by binary name, verify the source, close streams, and translate I/O errors appropriately.

Benefit: the default `ClassLoader.loadClass` already manages locking via `getClassLoadingLock` and calls `findLoadedClass`. You have fewer dangerous concurrency details to write yourself.

However, **do not** call `customLoader.findClass(name)` directly from the rest of the application to “bypass delegation”: `findClass` is a protected hook, not a standard public entrypoint. Even if you expose a public wrapper that calls `findClass` directly, it can **bypass locking and the already-loaded check** if poorly designed. Callers should use `loadClass(name)`.

## 5. If you must override `loadClass`: lock around the entire check/define

A child-first loader may need to load owned packages before delegating; you must be especially careful. Skeleton:

~~~java
public final class PackageLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "parallel-capable registration failed");
        }
    }

    public PackageLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> loadClass(String name, boolean resolve)
            throws ClassNotFoundException {
        synchronized (getClassLoadingLock(name)) {
            Class<?> c = findLoadedClass(name);

            if (c == null) {
                if (name.startsWith("myplugin.impl.")) {
                    try {
                        c = findClass(name);
                    } catch (ClassNotFoundException missingLocally) {
                        c = super.loadClass(name, false);
                    }
                } else {
                    c = super.loadClass(name, false);
                }
            }

            if (resolve) {
                resolveClass(c);
            }
            return c;
        }
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        throw new ClassNotFoundException(name); // Find bytes here.
    }
}
~~~

The file `PackageLoader.java` is a **Java 17+ compilable skeleton**, but `findClass` is only a behavioral placeholder (always throwing `ClassNotFoundException`), so it does not load a real plugin. The key part to learn is locking on `getClassLoadingLock(name)` and checking `findLoadedClass` **inside** the critical section.

**Special notes on child-first + parallel loading:**

- `registerAsParallelCapable()` must be called during **class initialization of the subclass itself**, before creating any instances; every classloader superclass must also be properly registered. The base `ClassLoader` is already registered, but an intermediate custom superclass might not be registered, causing the child's registration to fail.
- If the loader is **not yet parallel capable**, `getClassLoadingLock(name)` returns the loader object itself. When registration succeeds, per-name locking allows **different names** to be loaded concurrently, while **the same name** must still proceed sequentially.
- You should not use `synchronized(this)` if the goal is parallel loading of different names: locking the entire loader can reduce concurrency or cause deadlocks when the delegation graph is not strictly hierarchical. However, using a shared lock can still be appropriate if the loader does not support parallel loading.
- `getClassLoadingLock` is protected and returns different locks depending on the loader type; do not maintain locks in a separate map that is not synchronized with other loading paths.
- `super.loadClass(name,false)` in the skeleton is how the default parent-first semantics are used once fallback has been decided, though you must ensure it does not create a delegation cycle between loaders and that no code calls back into an infinite loop.
- Catch **only `ClassNotFoundException`** when intentional fallback is needed. Do not catch all `Throwable`/`LinkageError` to pretend the class does not exist.
- `resolveClass(c)` performs linking if `resolve=true`; it does **not** cause `<clinit>` to run; static initialization is a separate phase.

Unless there is a very clear child-first requirement, prefer `findClass` with the default `loadClass` implementation.

## 6. Reproducible experiment: forcing the race and fixing it with proper locking

The experiment uses **two Java 17+ files**. We use the same bytecode of `PluginTask` while creating separate loaders to test the two policies. `UnsafeLoader` is intentionally broken and places a `CyclicBarrier` after `findLoadedClass` so that **both threads perform the check before either calls `defineClass`**; this is a controlled race-reproduction technique for the lab exercise, not intended for production.

### 6.1. File `PluginTask.java`

~~~java
public class PluginTask {
    public String result() {
        return "ok";
    }
}
~~~

This class resides in the default package to keep run commands simple. It does not actively spawn threads and requires no dependencies outside the JDK.

### 6.2. File `RaceDemo.java`

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RaceDemo {
    private static final String TARGET = "PluginTask";

    // INTENTIONALLY WRONG: missing class-loading lock.
    static class UnsafeLoader extends ClassLoader {
        private final byte[] bytes;
        private final CyclicBarrier twoChecks = new CyclicBarrier(2);

        UnsafeLoader(byte[] bytes) {
            super(RaceDemo.class.getClassLoader());
            this.bytes = bytes;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            Class<?> found = findLoadedClass(name);
            if (found == null) {
                try {
                    // Both threads reach here while the class is still undefined.
                    twoChecks.await();
                } catch (Exception ex) {
                    throw new ClassNotFoundException(name, ex);
                }
                found = defineClass(name, bytes, 0, bytes.length);
            }

            if (resolve) {
                resolveClass(found);
            }
            return found;
        }
    }

    // CORRECT: for two requests with the same name, only one thread is allowed to define.
    static class SafeLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "parallel registration failed");
            }
        }

        private final byte[] bytes;

        SafeLoader(byte[] bytes) {
            super(RaceDemo.class.getClassLoader());
            this.bytes = bytes;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = defineClass(name, bytes, 0, bytes.length);
                }
                if (resolve) {
                    resolveClass(found);
                }
                return found;
            }
        }
    }

    static void test(String label, ClassLoader loader)
            throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Class<?>> request = () -> {
            start.await();
            return loader.loadClass(TARGET);
        };

        try {
            Future<Class<?>> first = workers.submit(request);
            Future<Class<?>> second = workers.submit(request);
            start.countDown();

            int successes = 0;
            int linkageErrors = 0;
            Class<?> firstResult = null;
            boolean sameClass = true;

            for (Future<Class<?>> f :
                    java.util.List.of(first, second)) {
                try {
                    Class<?> result = f.get();
                    successes++;
                    if (firstResult == null) {
                        firstResult = result;
                    } else {
                        sameClass &= firstResult == result;
                    }
                } catch (ExecutionException ex) {
                    if (ex.getCause() instanceof LinkageError) {
                        linkageErrors++;
                    } else {
                        throw ex;
                    }
                }
            }

            System.out.println(label + ": success=" + successes
                    + ", linkageError=" + linkageErrors
                    + ", sameClass=" + sameClass);
        } finally {
            workers.shutdownNow();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = Files.readAllBytes(Path.of("PluginTask.class"));
        test("unsafe", new UnsafeLoader(bytes));
        test("safe", new SafeLoader(bytes));
    }
}
~~~

**Commands** from the directory containing both sources:

~~~bash
javac --release 17 PluginTask.java RaceDemo.java
java -cp . RaceDemo
~~~

**Expected output when `UnsafeLoader` is forced through the barrier**:

~~~text
unsafe: success=1, linkageError=1, sameClass=true
safe: success=2, linkageError=0, sameClass=true
~~~

On the unsafe line, one thread succeeds and one thread is rejected by the VM due to a duplicate definition; `sameClass=true` appears only because **one** thread returned a `Class`, so there are not two successful results to compare. On the safe line, both succeed and return **the exact same `Class<?>`**, because the second thread sees the already-loaded class under the lock.

**Experiment limitations:**

- The `CyclicBarrier` in unsafe is only there to deterministically force the race; if replaced with `sleep` or `yield`, the output could become nondeterministic and fail to prove the root cause.
- The code intentionally bypasses parent-first for **the exact name `PluginTask`** so the loader defines the class itself; all other names go through `super.loadClass`. Do not use this approach for all of `java.*` or shared API packages.
- `PluginTask.class` may reside on the application classpath because `javac` generates the file; overriding a single binary name causes the experimental loader to still define it itself. Do not generalize this to conclude that system-wide child-first is a safe policy.
- The `PluginTask.class` file must exist in the **current working directory** when running. The commands above satisfy this if the exact structure is used.
- Counting `LinkageError` is for demonstration purposes only; production code should handle errors appropriately by type rather than ignoring them.
- When measuring real performance/concurrency, you must examine byte sources, I/O, delegation, class initialization, and JIT warm-up; this lab only isolates the check-then-define race.

### 6.3. Why must `findLoadedClass` still be inside the lock?

Suppose `SafeLoader` omits the `findLoadedClass` step inside the lock:

~~~java
synchronized (getClassLoadingLock(name)) {
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

Both T1 and T2 can pass through the lock one after the other and **both call `defineClass`**. The lock only guarantees non-concurrency, **not** by itself that the class is defined only once. You must **recheck while holding the lock**, and return the existing `Class<?>`.

Conversely, if you only check outside the lock and then enter the lock without rechecking, you still get a duplicate definition. Only the **same lock + recheck** pair properly solves the problem.

## 7. Same-name race vs. loading multiple names in parallel
`getClassLoadingLock(name)` protects each binary name individually once the loader is parallel-capable; if the subclass has not registered, the default lock is the loader itself. The registration prerequisites are **before creating any instance** and **every superclass loader must be registered**. Two names X/Y can proceed concurrently, but two threads for the same name X still require **the lock + `findLoadedClass` inside the lock**.
```text
T1: lock(X) → findLoadedClass(X)==null → defineClass(X) → unlock
T2: wait for lock(X) → findLoadedClass(X)==Class X → reuse
```
If loader A loads X while waiting for loader B to load Y, and B in turn waits for A, a deadlock can occur even when using per-name locks. Design the delegation graph to have a terminating point. This is a separate issue from the check-then-define race addressed in this lesson.

## 8. Distinguishing class definition races from class initialization races

**Loading/linking** and **initialization** are two different phases:

- Two threads concurrently calling `loadClass("X")` require coordination so that **one runtime `Class`** is returned and `defineClass` is not duplicated.
- Two threads concurrently performing active use (for example `new X()` or a static nonconstant field) have their **class initialization** coordinated by the JVM per JLS `12.4.2`. On success, `<clinit>` of a runtime class runs only once, and other threads wait when needed.
- `resolveClass(c)` only requests linking; it **does not replace** either of the two mechanisms above.
- `synchronized (getClassLoadingLock(name))` in a custom loader resolves the class definition/lookup race; it is **not** the lock you should use to guard mutable static state after initialization.

Therefore, it is possible to have thread-safe class-loading code while the service inside the class still has a **data race** on static fields when updated after initialization. The two categories of bugs require different remedies.

## 9. Identity, initiating loader, and parent-first

`findLoadedClass` returns the class for which the current loader has been recorded as an **initiating loader**, not necessarily a class that this loader directly defined. If loader L delegates the name `java.lang.String` to the bootstrap loader, `String.class.getClassLoader()` typically returns `null`; L can still participate in the initiating loader record.

**Do not redefine a class already provided by the parent** merely because you want global child-first loading; doing so can break type identity. For a plugin system:

- Shared APIs such as `host.api.PluginContract` should be defined in the **shared parent**.
- A separate implementation `plugin.impl.Handler` can be defined by the plugin loader.
- If two plugin loaders both define `plugin.impl.Handler`, they are **two different runtime types**, which is valid when plugin isolation is intentional.
- However, a single loader **must not define two versions of the same binary name** merely for hot reload. Create a new-generation loader, switch request routing in a controlled manner, and clean up the old loader once no references remain.

Test the type contract using `sharedTypeFromHost == sharedTypeFromPlugin` and `SharedApi.class.isAssignableFrom(implType)`; do not use `getName().equals` as proof of type compatibility.

## 10. Other concurrency pitfalls in custom class loaders

### 10.1. Safe byte caching differs from safe Class caching

You can use a pre-read immutable `byte[]` or a thread-safe byte-cache map to reduce I/O, but **ensuring a single definer of the class** still requires the proper lock. If bytes can be updated concurrently, you must also ensure each definition reads **an intact snapshot**, without using a `byte[]` that is mutated after verification/checksum.

### 10.2. Concurrent loader closing and class loading

With `URLClassLoader.close()`, the Javadoc does not guarantee class-loading outcomes when `close` runs concurrently with `loadClass`. This is a **lifecycle** race distinct from duplicate `defineClass`. You need to reject new work, drain running tasks, and then close the loader; the `getClassLoadingLock(name)` lock only protects loading and does not automatically manage the entire plugin lifecycle.

### 10.3. Exception classification

| Error | Common meaning | What not to do |
| --- | --- | --- |
| `ClassNotFoundException` | The loader did not find a class with the requested name | Swallow the exception and return `null` from `loadClass` |
| `LinkageError` on duplicate define | Loading coordination bug or runtime identity conflict | Catch the error to pretend the class was not found |
| `ClassFormatError`/`VerifyError` | Invalid bytecode or verification violation | Retry infinitely with the same bytes |
| `UnsupportedClassVersionError` | Bytecode is too new for the runtime | Use locks instead of fixing the runtime/target |
| `ClassCircularityError` | Invalid circular superclass/interface relationship | Remove locks to try to bypass it |
| `NoClassDefFoundError` | Missing runtime class, previous initialization failure, or linkage cause | Immediately conclude that only a JAR is missing |

**Note:** The errors in the table do not necessarily occur at a single fixed point in time because the JVM may perform eager or lazy linking/resolution. Examine the root cause and the initial logs.

### 10.4. Attempting to register as parallel capable without checking the return value

`registerAsParallelCapable()` returns a boolean. If false, `getClassLoadingLock(name)` may not provide the per-name lock you expect. Do not assume parallel performance just because this static call is present; verify the superclass hierarchy requirements and test.

### 10.5. Changing loading policy at runtime

A loader that has already returned/defined `foo.Bar` cannot “redefine” `foo.Bar` in place within the same namespace when the JAR file changes on disk. Treat the package ownership/delegation policy as **immutable** for the lifetime of the loader, and do not allow one thread to mutate the prefix map while another thread is looking up a class.

## 11. Practical testing beyond the lab

A production custom loader should include the following tests:

1. **Concurrent same name:** instantiate a new loader, use a `CountDownLatch` to launch multiple concurrent tasks all calling `loadClass(X)`; verify all succeed and the `Class<?>` objects share the same identity.
2. **Concurrent different names:** use multiple classes `X,Y,Z` and verify that a parallel-capable loader allows valid concurrent loading without deadlock; do not judge by a fixed output order.
3. **Duplicate name fail-fast:** intentionally create a broken implementation in a separate test; assert that it fails rather than burying the error.
4. **Delegation:** shared API is defined by the parent; plugin class is defined by the child; `Class.getClassLoader()` and `isAssignableFrom` are correct.
5. **I/O errors:** missing/corrupted bytes, closing JAR, name mismatch in the class file; exceptions are classified properly.
6. **Lifecycle:** stop the plugin while workers are active; ensure the URLClassLoader is not closed before in-flight loads finish.
7. **Repeated reload:** create a new loader per generation, and do not retain TCCL/thread caches/host registry references that keep the old loader reachable.
8. **Module/access:** if using JPMS, test readability/exports/opens; proper locking cannot fix a module access violation.
9. **Stress:** run multiple iterations, enable logging, and inspect stack traces; do not rely on a single non-reproducing race test run.
10. **Timeout/deadlock:** test cancellation, capture thread dumps, and avoid hanging indefinitely in CI.

### 11.1. Do not use sleep calls to “test for races”

A program running 100,000 times without error **does not prove** the code is race-free; the scheduler may simply not have produced an unfavorable interleaving. Using a barrier in tests like `RaceDemo` forces two threads past the check together to demonstrate the bug in a controlled way. For production, rely on **invariants and proper locking**, and use stress testing/observability as a supplement.

### 11.2. Observing with JDK tools

~~~bash
java -version
javap -c -p RaceDemo
java -Xlog:class+load=info -cp . RaceDemo
~~~

`-Xlog` is a diagnostic feature of JVMs supporting unified logging such as HotSpot; output and tag support depend on the runtime. When a deadlock is suspected, you can take a thread dump (`jcmd <pid> Thread.print` if supported by the runtime) and inspect which thread is holding the loading lock; do not substitute parsing the `class+load` log ordering as a JLS contract.

## 12. Checklist when reviewing `loadClass`

- [ ] Is overriding `loadClass` actually necessary, or is `findClass` sufficient?
- [ ] Does every load of the same name use the proper `getClassLoadingLock(name)`?
- [ ] Is `findLoadedClass(name)` **inside the critical section**, and checked before calling `defineClass`?
- [ ] Is the recheck inside the lock missing? If so, fix it.
- [ ] Is `resolveClass(c)` called only when `resolve=true` and the class token is valid?
- [ ] Is the parent delegation/child-first package policy consistent and cycle-free?
- [ ] Is `Throwable`/`LinkageError` caught broadly and retried blindly?
- [ ] Is `registerAsParallelCapable` called at the right time and supported by the superclass hierarchy?
- [ ] Are class-loading tasks concurrent with close/unload coordinated via lifecycle management?
- [ ] Do tests with multiple threads loading the same name return **a single `Class<?>`**?
- [ ] Are shared APIs prevented from being redefined by the custom loader?
- [ ] Does the code distinguish between class loading, linking, and initialization?

## 13. Self-check questions

1. Why does `findLoadedClass(name)==null` not guarantee a thread may call `defineClass`? **Because another thread can define the same name right after the check.**
2. Why can `synchronized` around `defineClass` alone still be wrong? **Without rechecking under the lock, the second thread will still make a duplicate definition when its turn arrives.**
3. Which API provides the lock for a given name? **`getClassLoadingLock(name)`.**
4. When not parallel capable, what is that lock? **The ClassLoader object itself**, according to the API.
5. When parallel capable, can two differently named classes load concurrently? **Yes**, via per-name locks, though complete absence of waiting is not guaranteed due to dependencies.
6. Should you override all of `loadClass` if you only need to read custom bytes? **Usually no; override `findClass`**.
7. Does `registerAsParallelCapable` automatically add synchronization to a broken override? **No**.
8. When two threads define the same binary name in one loader, what error is typically seen? **`LinkageError`** due to duplicate definition.
9. When two different loaders intentionally define the same binary name for plugin isolation, is it always an error? **No**, because runtime identity differs; problems arise if the type must be shared across the boundary.
10. Does `resolveClass` execute `static{}`? **No**, it links rather than initializes.
11. Why must `ClassNotFoundException` and `LinkageError` be handled differently? **One can be a lookup miss, while the other is usually a verification/binary identity/linking error.**
12. Is closing a `URLClassLoader` while workers are loading classes safe by default? **No**, shutdown must be coordinated.
13. How does a test with a barrier forcing both threads to see null help? **It reproduces TOCTOU instead of relying on scheduler probability.**

## 14. Authoritative references

- [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `findLoadedClass`, `defineClass`, `getClassLoadingLock`, `registerAsParallelCapable`; the default implementation synchronizes on the class-loading lock.
- [ClassLoader — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): the parallel loading and locking contract maintained in recent JDK releases.
- [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): defining/initiating loader, runtime type identity, loading constraints.
- [JVMS §5.4 — Linking](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.4): verification, preparation, resolution.
- [JLS §12.4 — Initialization of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.4): initialization is coordinated across threads, distinct from duplicate class definition.
- [CyclicBarrier — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CyclicBarrier.html) and [CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): tools for forcing interleavings in concurrency tests.

**Conclusion:** `findLoadedClass` only **observes state**, while `defineClass` **mutates state**. Both steps must be inside the same **locking + recheck** mechanism per class name. The safest approach is usually keeping the default `loadClass` and overriding only `findClass`; if overriding manually is unavoidable, use `getClassLoadingLock(name)` for **all** of check/delegation/define/resolve and verify `registerAsParallelCapable` under the proper conditions.
