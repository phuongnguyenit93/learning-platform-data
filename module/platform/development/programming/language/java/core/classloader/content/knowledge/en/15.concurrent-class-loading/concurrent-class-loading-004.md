# registerAsParallelCapable and Registration Conditions

## 1. Problem: Multiple Threads Concurrently Requesting Class Loading

In Java applications with plugins, application servers, proxy frameworks, or multiple background tasks, two threads can simultaneously request a `ClassLoader` to load two different classes. If every load holds **the same loader-wide lock**, independent requests must also wait for each other. This can reduce throughput and, in a non-tree delegation ClassLoader topology, also increase the risk of deadlock.

Java allows the author of a `ClassLoader` subclass to declare that the loader type can support **parallel class loading** using the method:

~~~java
protected static boolean ClassLoader.registerAsParallelCapable()
~~~

The line above describes the API signature, **not Java syntax for calling the method**. In a class extending `ClassLoader`, the typical approach is to call `registerAsParallelCapable()` directly inside the **static initializer**, before any instance of that class is created.

~~~java
public final class MyLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "Cannot register MyLoader as parallel capable");
        }
    }

    public MyLoader(ClassLoader parent) {
        super(parent);
    }
}
~~~

This is a compilable class example when saved as `MyLoader.java`, but it **does not implement its own bytecode source yet**; if you want the loader to actually load plugin classes, you need to add `findClass` or use a standard loader such as `URLClassLoader`. This pattern illustrates **the timing of registration and handling the result**, not a complete plugin loader.

**Key takeaway:** `registerAsParallelCapable()` declares the concurrent loading coordination capability of a **class loader type**, rather than being called on an instance to toggle a per-loader runtime option.

## 2. Two Registration Conditions According to the Java 17 Javadoc

The `ClassLoader.registerAsParallelCapable()` Javadoc specifies that registration succeeds **if and only if both conditions** hold:

1. **No instance of the class loader calling the registration method has been created yet.**
2. **Every superclass of that class loader, except `Object`, has already been registered as parallel capable.**

The method returns:

- `true` if registration succeeds;
- `false` if the registration conditions are not met.

Once a loader type has registered as parallel capable, it **cannot unregister to switch back to non-parallel capable**.

Java's `ClassLoader` **is registered as parallel capable by default**, yet **each subclass that wants to participate must still register itself**. Do not infer that “because the parent class `ClassLoader` is registered, the subclass is also automatically registered”.

| Scenario | Typical Result |
|---|---|
| `MyLoader extends ClassLoader` and calls registration in a `static` block before any instance is created | `true` |
| `ChildLoader extends MyLoader`; `MyLoader` is already registered and `ChildLoader` registers itself early | `true` |
| `ChildLoader` forgets to register itself even though its parent is registered | `ChildLoader` remains non-parallel capable |
| `ChildLoader` registers, but has a superclass loader that is **not** registered | `false` |
| Calling registration for the first time after an instance of the caller class itself has already been created | `false` |
| Registering successfully and then creating multiple instances of the same loader class | Those instances belong to a registered loader type |
| Wanting to “turn off” registration later | No API to revert |

Note that the term **caller** here refers to **the class loader subclass that actually calls the registration method**, not an object passed as a parameter. The method is `protected static`, not a `public` instance setter.

## 3. Why Must It Be Called in a `static initializer`?

The static initializer runs during the **class initialization** phase, before the constructor creating the first instance can complete. Placing registration there matches the “no instance yet” condition precisely:

~~~java
class ParallelDirectoryLoader extends ClassLoader {
    static {
        boolean ok = registerAsParallelCapable();
        if (!ok) {
            throw new ExceptionInInitializerError(
                    "Parent hierarchy is not parallel capable");
        }
    }

    ParallelDirectoryLoader(ClassLoader parent) {
        super(parent);
    }
}
~~~

If registration fails and you **continue running** as if nothing happened, the loader type can still operate using coarse-grained locking. However, if your design **strictly depends** on parallel capability, you should fail fast as in the example.

Do not call `registerAsParallelCapable()` inside a constructor to “register this instance”, or from a button/runtime config to switch modes after the loader has already been used. Registration belongs to the **class lifecycle**, not the object lifecycle.

A fundamental Java point: a superclass's static initializer runs before the subclass's initializer according to initialization rules. Thanks to that, if the parent registers in its static initializer and no parent instance was created beforehand, the subclass can call registration in its static initializer after the parent has been initialized. However, **the parent class must still actually succeed in registering**; merely extending a parent that “intends to register” is not enough.

## 4. Inheritance Relationship: Registration Must Span the Superclass Chain

Consider two trees:

~~~text
Valid tree                              Failing tree

ClassLoader [registered]                ClassLoader [registered]
       │                                        │
       ▼                                        ▼
BaseLoader [registered]                 LegacyLoader [NOT registered]
       │                                        │
       ▼                                        ▼
ChildLoader [registered]                ChildLoader [attempts registration]
                                                │
                                                ▼
                                           returns false
~~~

In the first tree:

- `ClassLoader` is pre-registered by the JDK.
- `BaseLoader` calls registration early and receives `true`.
- `ChildLoader` also calls registration early, sees all superclass loaders are registered → `true`.

In the second tree:

- `LegacyLoader` does not register.
- Even though `ChildLoader` calls `registerAsParallelCapable()` in its static initializer before any instance is created, **the superclass condition is still false**.
- The result is `false`; registering in a subclass cannot “skip over” an unregistered superclass.

This matters when you extend a ClassLoader library written by someone else. If the base class was not designed and registered as parallel capable, your subclass cannot fix that merely by calling registration itself.

### 4.1. Distinguishing Parent Loader from Superclass

Two Java concepts that are very easy to confuse:

**Superclass** is the inheritance relationship *between classes in source code*: `MyLoader extends BaseLoader`. This is the factor in the **registerAsParallelCapable condition**.

**Parent ClassLoader** is **the object reference used for delegation** when a loader loads a class: `new MyLoader(parent)`. This is a **per-instance** configuration.

~~~java
// Illustrative code:
MyLoader loader = new MyLoader(ClassLoader.getPlatformClassLoader());
~~~

Passing the platform loader as the parent **does not make an unregistered superclass registered**. Conversely, having all superclasses registered **does not prove** that the parent loader instance has any custom configuration you expect.

| Question | What to Check |
|---|---|
| “Is MyLoader eligible for registerAsParallelCapable?” | **MyLoader's superclass chain** and the timing of instance creation |
| “Which loader does Loader A query before loading?” | **Instance** A's `getParent()` and delegation logic |
| “Can two requests on the same loader obtain two separate locks?” | The **loader class** registration state, `getClassLoadingLock(name)` |
| “Do two plugin loaders see the same interface?” | Parent/delegation and the defining loader of the shared API |

## 5. How Does Registration Change Locking?
For the default `loadClass`, `getClassLoadingLock(name)` returns **`this`** if the subclass is not registered; when registered, it returns **a stable lock per binary name**. Therefore, different names A/B can be loaded concurrently, whereas two requests for A must still use the same lock and check `findLoadedClass` before `defineClass`.
Registration does not guarantee higher performance or make `findClass` thread-safe. The experiment in §6 checks locks by identity and distinguishes successful registration, an unregistered superclass, and a late registration case.

## 6. Java 17+ Program to Verify the Two Registration Conditions

This is a **standalone** file illustrating four cases:

1. A class directly extending `ClassLoader` registers early: succeeds.
2. A subclass of an already-registered loader also registers: succeeds.
3. A subclass of an unregistered loader attempts to register: fails.
4. A ClassLoader attempts to register only after an instance has already been created: fails.

The program also checks the locks for the same name and for different names, so you can observe the effect of registration without relying on multithreaded races or unstable timing measurements.

Create the file **`ParallelRegistrationDemo.java`**:

~~~java
public final class ParallelRegistrationDemo {
    private ParallelRegistrationDemo() {
    }

    static class RegisteredParent extends ClassLoader {
        static final boolean REGISTERED = registerAsParallelCapable();

        RegisteredParent() {
            super(ClassLoader.getSystemClassLoader());
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    static final class RegisteredChild extends RegisteredParent {
        static final boolean REGISTERED = registerAsParallelCapable();

        RegisteredChild() {
            super();
        }
    }

    static class LegacyParent extends ClassLoader {
        // Does not call registerAsParallelCapable.
        LegacyParent() {
            super(ClassLoader.getSystemClassLoader());
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    static final class BlockedChild extends LegacyParent {
        static final boolean REGISTERED = registerAsParallelCapable();

        BlockedChild() {
            super();
        }
    }

    static final class LateAttempt extends ClassLoader {
        // Intentionally does not register in the static initializer.
        LateAttempt() {
            super(ClassLoader.getSystemClassLoader());
        }

        static boolean registerTooLate() {
            return registerAsParallelCapable();
        }
    }

    public static void main(String[] args) {
        RegisteredParent parent = new RegisteredParent();
        RegisteredChild child = new RegisteredChild();
        LegacyParent legacy = new LegacyParent();
        BlockedChild blocked = new BlockedChild();
        LateAttempt late = new LateAttempt();

        System.out.println("RegisteredParent registration: "
                + RegisteredParent.REGISTERED);
        System.out.println("RegisteredChild registration: "
                + RegisteredChild.REGISTERED);
        System.out.println("LegacyParent registered: "
                + legacy.isRegisteredAsParallelCapable());
        System.out.println("BlockedChild registration: "
                + BlockedChild.REGISTERED);
        System.out.println("BlockedChild registered: "
                + blocked.isRegisteredAsParallelCapable());

        System.out.println("RegisteredChild registered: "
                + child.isRegisteredAsParallelCapable());
        System.out.println("Same name uses same lock: "
                + (child.lock("demo.A") == child.lock("demo.A")));
        System.out.println("Different names use different locks: "
                + (child.lock("demo.A") != child.lock("demo.B")));

        System.out.println("Legacy lock is loader: "
                + (legacy.lock("demo.A") == legacy));
        System.out.println("Blocked lock is loader: "
                + (blocked.lock("demo.B") == blocked));

        System.out.println("Late initially registered: "
                + late.isRegisteredAsParallelCapable());
        System.out.println("Late registration after instance: "
                + LateAttempt.registerTooLate());
        System.out.println("Late finally registered: "
                + late.isRegisteredAsParallelCapable());

        // Use the parent variable to check the state of the base instance:
        System.out.println("RegisteredParent instance registered: "
                + parent.isRegisteredAsParallelCapable());
    }
}
~~~

### 6.1. Compile and Run

Use JDK **17 or later** and run in the directory containing `ParallelRegistrationDemo.java`:

~~~bash
javac -encoding UTF-8 ParallelRegistrationDemo.java
java ParallelRegistrationDemo
~~~

Both commands work in Bash, PowerShell, and Command Prompt when the JDK is in `PATH`; the source uses no dependencies outside the JDK and requires no `--module-path`.

### 6.2. Exact Stdout

~~~text
RegisteredParent registration: true
RegisteredChild registration: true
LegacyParent registered: false
BlockedChild registration: false
BlockedChild registered: false
RegisteredChild registered: true
Same name uses same lock: true
Different names use different locks: true
Legacy lock is loader: true
Blocked lock is loader: true
Late initially registered: false
Late registration after instance: false
Late finally registered: false
RegisteredParent instance registered: true
~~~

**Detailed explanation:**

- `RegisteredParent.REGISTERED`: `ClassLoader` is pre-registered, and there is no `RegisteredParent` instance before the static initializer registers → `true`.
- `RegisteredChild.REGISTERED`: superclass `RegisteredParent` is already registered, and the subclass also calls it early → `true`.
- `LegacyParent`: does not call registration, so by default it is **not** registered even though it extends `ClassLoader`.
- `BlockedChild.REGISTERED`: there is no `BlockedChild` instance before the static initializer runs, but its superclass `LegacyParent` is not registered → `false`.
- `child.lock("demo.A")` called twice returns the same dedicated lock; `child.lock("demo.B")` returns a different lock, matching the default `getClassLoadingLock` for a registered loader.
- `legacy.lock(...) == legacy` and `blocked.lock(...) == blocked` demonstrate the default lock on the loader object for non-parallel capable types.
- `LateAttempt` is instantiated via `new LateAttempt()` before calling `registerTooLate()`. The “no instance yet” condition has been violated → `false`, and the loader type remains non-parallel capable.

This example does **not** perform a benchmark: it observes the registration/lock identity contract and does not run two contending threads. You should not infer from these results what percentage throughput improvement would occur on a real machine.

## 7. A Subtlety About the `static` Method and the Caller

`registerAsParallelCapable()` is not an instance method like:

~~~java
// WRONG API semantics; not a way to toggle it on/off for an object:
loader.registerAsParallelCapable();
~~~

It is `protected static` and must be called from the appropriate subclass scope. The recommended registration approach is to **call it directly in the static initializer of the loader type itself**:

~~~java
class AppPluginLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "AppPluginLoader registration failed");
        }
    }
}
~~~

If you call a **static helper defined by a superclass**, do not assume that helper is registering the subclass based on the object's dynamic class name. Java `static` methods do not have dynamic dispatch like instance methods; the registration caller must be understood in terms of the class that defines the call.

That is why every subclass that wants to be parallel capable should have its **own** registration step, rather than treating a base class's constructor or shared helper as sufficient for the entire inheritance tree.

## 8. Registration Must Be Paired with a Truly Thread-Safe Implementation

The name “parallel capable” is **the loader author's promise** of concurrent class-loading capability, not an automatic transformation that makes all code thread-safe.

For example, if `findClass` uses an unprotected shared instance buffer:

~~~java
// Dangerous illustrative code, not a standalone program.
private byte[] sharedBuffer;

@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    sharedBuffer = readBytes(name); // another thread can overwrite this
    return defineClass(name, sharedBuffer, 0, sharedBuffer.length);
}
~~~

When two threads load two different names at the same time, the `sharedBuffer` data can be overwritten; class A could receive bytecode B, leading to `ClassFormatError`, `NoClassDefFoundError`, or intermittent errors.

A better design:

~~~java
// Illustrative code; readBytes(...) is implemented by the loader and has
// thread-safe access to the data source when called concurrently.
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    byte[] bytes = readBytes(name); // local variable per invocation
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

Beyond byte arrays, you must check:

- Maps from class names to bytes/URLs that are cached and updated concurrently.
- Shared `JarFile`, ZIP readers, network clients, or database connections.
- Package-definition state, code sources, security domains, signers/sealing, and metadata.
- Callback queues and event logs if `findClass` emits events.
- Resource loading paths and open streams during plugin shutdown.
- `close()` or loader reloading occurring concurrently with class loading.
- Lock ordering when custom loaders call into each other or use multiple locks.

**Do not register just to be “faster” if the current implementation is not thread-safe.** Switching from a global loader lock to per-name locks can expose races that were previously hidden by accidental serialization.

## 9. If Overriding `loadClass`, You Must Still Lock Properly
`registerAsParallelCapable()` enables the **default** implementation to use per-name locks; it does not inject locking into any override. If you must write a child-first loader, place the entire **`findLoadedClass` → delegation/`findClass` → `resolveClass` (when needed)** sequence inside `synchronized(getClassLoadingLock(name))`. Handle a `null` parent, shared APIs, and `ClassNotFoundException` properly; do not swallow `LinkageError`. Avoid `public synchronized loadClass` because locking the entire instance forfeits the benefit of per-name locks.
When your goal is simply to add a bytecode source, you should override only `findClass` and let the standard `loadClass` manage locking/delegation.

## 10. Why Must Two Threads Loading the Same Name Still Be Serialized?

A loader must not freely define the same binary name twice:

~~~text
Thread A: child.loadClass("plugin.Widget")
Thread B: child.loadClass("plugin.Widget")
             │
             ▼
   Same lock for name Widget
             │
             ▼
     Check findLoadedClass
             │
             ▼
Only one valid Class<?> definition
~~~

If both call `defineClass` without proper checking and coordination, `LinkageError: duplicate class definition` can occur. `registerAsParallelCapable` **does not allow** creating multiple runtime types with the same name in **the same defining loader**.

Two different loader instances can each define a class with the same binary name and create **two different runtime types**. That is a matter of class identity by `(binary name, defining loader)`, not the purpose of parallel-capable registration.

## 11. When Delegation Is Non-Hierarchical
In a loader graph with cross-calls, T1 holding lock A while waiting for B and T2 holding lock B while waiting for A can deadlock. Parallel-capable reduces contention when names differ, but it does not cure an actual wait cycle. The article **Deadlock When Multiple Loaders Cross-Delegate** focuses on how to reproduce and diagnose this; the registration rule remains: choose an eligible loader hierarchy **and** make all shared state safe.

## 12. Observable State via `isRegisteredAsParallelCapable()`

Java 9+ provides:

~~~java
public final boolean isRegisteredAsParallelCapable()
~~~

This method is an **instance API** that returns `true` when **the class of the loader object** has been registered as parallel capable. This is an easy way to inspect the state:

~~~java
// Illustrative snippet; requires a customLoader object:
System.out.println(customLoader.isRegisteredAsParallelCapable());
~~~

Do not confuse it with `registerAsParallelCapable()`, which is **protected static** for registering the class. The differences:

| API | Static or Instance? | Purpose |
|---|---|---|
| `registerAsParallelCapable()` | `protected static` | Registers the **loader type**; typically in a static initializer |
| `isRegisteredAsParallelCapable()` | `public final` instance method | Reads the registration state of the **loader object/type** |
| `getClassLoadingLock(name)` | `protected` instance method | Obtains the lock that the default `loadClass` will use |
| `loadClass(name)` | Instance method | Requests class loading with delegation and locking |

The `ParallelRegistrationDemo` example uses both kinds of APIs to check status and lock identity without needing reflection into JDK internals.

## 13. Common Mistakes

| Mistake | Consequence | Correct Approach |
|---|---|---|
| “`ClassLoader` is registered, so every subclass is automatically registered” | The subclass remains non-parallel capable unless it registers itself | Register in each loader subclass that needs parallel capability |
| Only calling register in the subclass while ignoring an unregistered base loader | `registerAsParallelCapable()` returns `false` | Register the entire superclass chain first |
| Calling registration after an instance has already been created | The timing condition no longer holds | Register in the static initializer before any instance is created |
| Treating `getParent()` as the superclass | Misinterprets the registration conditions | Distinguish type inheritance from instance delegation |
| Ignoring the boolean return value of registration | Assuming it is parallel while it actually uses a loader-wide lock | Check for `true` and fail fast if required |
| Assuming registration automatically makes all fields thread-safe | Races when `findClass` uses shared state | Audit mutable state and concurrency |
| `synchronized loadClass(...)` on the whole object | Serializes all class names even when registered | Use the default `loadClass`/`getClassLoadingLock(name)` |
| Two threads load the same class name and define it twice | `LinkageError` due to duplicate definition | Synchronize by name and call `findLoadedClass` properly |
| Treating parallel capability as a deadlock guarantee | Lock inversion may still occur in parents/dependencies | Inspect delegation topology and lock ordering |
| Confusing parallel loading with parallel class initialization | Confuses class lifecycle phases | Separate loading, linking, and initialization |
| Seeing no speedup in a benchmark and assuming the API is useless | Bottlenecked by I/O, parent locks, or workload | Observe contention and profile the actual loader |

## 14. When Should You Register and When Is It Unnecessary?

**Consider registering** when:

- Writing a custom loader that genuinely needs to load multiple classes from multiple threads.
- The loader may be used by a plugin host, application server, or framework with complex delegation paths.
- `findClass` is designed to be thread-safe, using properly synchronized state/storage.
- The entire superclass chain is registered and you control the static initialization lifecycle.

**You do not necessarily need to register** when:

- Simply using a standard loader that already supports what you need; for example, `URLClassLoader` has the JDK's design/registration, so there is no need to create a subclass just to “enable parallel”.
- Writing a regular Java application that does not subclass `ClassLoader`.
- Thread safety has not been verified yet, especially if the loader uses shared byte buffers, resource handles, or mutable caches.
- A superclass in a legacy library is not registered and you cannot change that class; calling registration in the subclass will still fail.

If you simply need to load plugin JARs, prefer `URLClassLoader` or an appropriate module/plugin mechanism before designing your own ClassLoader with concurrency.

## 15. Concurrency Testing Advice

Before putting a parallel-capable custom loader into production:

1. Confirm that `registerAsParallelCapable()` **returns `true`** in every required loader subclass.
2. Confirm that instances return `isRegisteredAsParallelCapable() == true`.
3. Test loading **two different class names** concurrently, as well as **the same class name** from multiple threads.
4. Verify there is no `LinkageError` from defining the same name and no class data mixed across requests.
5. Test cross-loader dependencies that could form a wait cycle, using timeouts and thread dumps when needed.
6. Audit `findClass`, `findResource(s)`, caches, filesystem/JAR/network reads, and the close/shutdown lifecycle.
7. Do not use millisecond timings from a single run to conclude thread safety or performance gains.
8. If a failure occurs, distinguish among **deadlock**, slow contention, class initialization locks, I/O locks, and circular class dependencies.
9. Avoid measuring by unintentionally overriding synchronization in a way that alters the property being verified.

**Monitoring:** thread dumps, Java Flight Recorder, class-loading logs, and contention measurements can help identify bottlenecks; there is no need to guess from a single console log.

## 16. Self-Check Questions

**1. What conditions must hold for `registerAsParallelCapable()` to succeed?**

**Answer:** No instance of the caller loader class has been created yet, and every superclass loader of that class (except `Object`) has already registered as parallel capable.

**2. `ClassLoader` is already registered. Why does the subclass `MyLoader` still need to register?**

**Answer:** Registration is not automatically inherited. Each subclass intending to be parallel capable must register itself and satisfy the hierarchy condition.

**3. `Child extends LegacyParent`, where LegacyParent is not registered. Child calls registration in its static initializer; what is the result?**

**Answer:** `false` even though Child has no instance yet, because its superclass is not registered.

**4. A registered loader loads `A` and `B`. Is the default lock the same for both names?**

**Answer:** No. The default `getClassLoadingLock` returns a separate lock per class name; two calls with the same name are coordinated using the same lock.

**5. Does `registerAsParallelCapable()` make `findClass` code that shares a mutable byte buffer thread-safe?**

**Answer:** No. The loader author must independently ensure that shared state is accessed safely. Registration only affects `ClassLoader`'s loading lock mechanism.

**6. Can you enable parallel capability for an already existing loader object by calling an instance method?**

**Answer:** No. Registration is static per loader type and must occur before any instance exists; `isRegisteredAsParallelCapable()` is only for checking state.

**7. If the parent ClassLoader instance is the platform loader, is an unregistered superclass bypassed?**

**Answer:** No. The registration condition examines **the superclass of the loader class**, not the parent object passed to the constructor.

## 17. References

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): overview of parallel-capable loaders, `registerAsParallelCapable`, `isRegisteredAsParallelCapable`, `getClassLoadingLock`, and `loadClass`.
- [Java SE 17 — registerAsParallelCapable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#registerAsParallelCapable()): the “no instance yet” and “all superclasses registered” conditions.
- [Java SE 17 — getClassLoadingLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getClassLoadingLock(java.lang.String)): loader-wide lock vs. per-name lock.
- [Java SE 17 — isRegisteredAsParallelCapable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#isRegisteredAsParallelCapable()): checking state at runtime.
- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, loading, and linking.

**Remember:** `registerAsParallelCapable()` must be called **early in the static initializer of each loader subclass**; it succeeds only when no instance of the caller exists yet and **all superclass loaders are already registered**. It lets the default `loadClass` use **per-class-name locks** instead of a single loader-wide lock, but it **does not automatically make a custom loader thread-safe** and does not guarantee that all class loading will run in parallel or be deadlock-free.
