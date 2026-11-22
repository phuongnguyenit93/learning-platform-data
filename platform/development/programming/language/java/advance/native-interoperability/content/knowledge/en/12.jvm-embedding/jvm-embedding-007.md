# DestroyJavaVM, Non-Daemon Threads, and VM Termination Conditions

## 1. Why Can't a JVM-Embedded Application "Shut Down the VM Immediately"?

With the **JNI Invocation API**, a C or C++ program can create and control a JVM directly inside a native process. Unlike an application launched with the `java` command, here the **native host** owns the timing of VM creation, entering Java, and requesting VM termination.

Basic flow:

~~~text
Native process (C/C++)
       |
       | JNI_CreateJavaVM(...)
       v
JVM initialized, calling thread attached
       |
       | FindClass / CallStaticVoidMethod / ...
       v
Java may create Java threads
       |
       | host requests work to stop
       v
DestroyJavaVM()
       |
       | waits for eligible non-daemon threads to finish/detach
       | executes JVM shutdown sequence
       v
DestroyJavaVM returns JNI_OK or an error code
       |
       v
Native host continues working outside the JVM or exits process
~~~

**`DestroyJavaVM` does not "immediately kill all Java threads."** This call may **block** while the JVM still has active **non-daemon** threads. Those threads include:

- **Java threads** marked as non-daemon (by default, many threads created by the application).
- **Native OS threads attached to the JVM** in non-daemon mode, such as via `AttachCurrentThread`.

The host must design a way to ask threads to terminate and release their resources. You cannot expect the JVM to automatically close files, sockets, database transactions, mutexes, or business work held by native/Java threads.

After this lesson, you will be able to:

1. Describe the conditions under which `DestroyJavaVM` is allowed to complete.
2. Distinguish between non-daemon threads, daemon threads, and **unattached** native OS threads.
3. Understand the difference between `AttachCurrentThread` and `AttachCurrentThreadAsDaemon`.
4. Write a **Java 17+ + C11** program where the host creates the JVM, runs a non-daemon Java worker, requests it to stop, and then calls `DestroyJavaVM`.
5. Identify deadlocks when the host calls Destroy **before** sending the signal that the worker is waiting on.
6. Handle return codes, shutdown hooks, cleanup, and the limitations of recreating a JVM in the same process.

## 2. API: Signature, Call Site, and Return Value

C (from `jni.h`):

~~~c
jint DestroyJavaVM(JavaVM *vm);
~~~

With the `JavaVM *vm` pointer obtained from `JNI_CreateJavaVM`, call in C:

~~~c
jint rc = (*vm)->DestroyJavaVM(vm);
if (rc == JNI_OK) {
    /* Shutdown sequence succeeded. */
} else {
    /* Handle error; do not continue using the JVM as if it were still valid. */
}
~~~

In C++:

~~~cpp
jint rc = vm->DestroyJavaVM();
~~~

These are **illustrative snippets**, not standalone source files.

**Return value:** `JNI_OK` indicates success; appropriate JNI error codes are **negative numbers** (for example `JNI_ERR`). `JNI_VERSION_1_6` is a **JNI interface version constant**, not a success return code of `DestroyJavaVM`.

**Call site:** `DestroyJavaVM` belongs to the **`JavaVM` Invocation API**, typically called from the C/C++ host that owns the JVM. It is not a Java method on `Thread` and cannot be replaced with `System.gc()` or `System.exit(0)` without changing the semantics.

**Argument:** `vm` must be a valid VM pointer, typically received when `JNI_CreateJavaVM` returns `JNI_OK`. Do not pass `NULL` and do not reuse the VM pointer for JNI calls after the VM has terminated successfully.

### 2.1. Conditions on the Calling Thread

Modern JNI versions allow requesting Destroy from a native thread that is not necessarily the original thread that created the JVM.

- If the calling thread is **already attached**, it participates in the VM termination process; **it does not have to wait for itself to terminate** before returning.
- If the calling thread is **not attached**, the VM may automatically attach that thread to carry out the shutdown request.
- If the calling thread currently has **Java methods on the call stack**, you should not call `DestroyJavaVM` from that context. Modern JNI specifications treat this as an error when the thread is attached; from a design standpoint, the host should call it after returning from Java callbacks/native methods.

**Architecturally unsafe** example:

~~~text
Java main()
   |
   v
native closeEverything()
   |
   +--> DestroyJavaVM()   // Java methods still on the call stack
~~~

Have Java signal "stopped" to the host, **return from the Java/JNI call**, and then have the host call `DestroyJavaVM` from the native lifecycle management layer outside the Java call stack.

## 3. Non-Daemon Is the Deciding Condition

### 3.1. Non-Daemon Java Thread

In Java, a thread has a daemon property. For a thread created with `new Thread(...)`, the daemon status may be **inherited from the thread that created it**. Therefore, when building an embedded application, it is best to set the status explicitly so it does not depend on context:

~~~java
Thread worker = new Thread(() -> {
    // Background work that must complete before shutdown.
}, "important-worker");

worker.setDaemon(false);  // Non-daemon: affects VM shutdown wait condition.
worker.start();
~~~

This snippet is illustrative inside a Java method. `setDaemon` must be called **before `start()`**; changing the daemon status of a running thread is invalid.

When `DestroyJavaVM` is requested, a **non-daemon worker that is still alive** can make the host wait. The VM cannot know on its own when your worker finishes its business logic. You yourself must provide:

- A stop-request mechanism (`CountDownLatch`, atomic flag, appropriate interrupt, closing queues/sockets, etc.).
- A way for the worker to exit its loop and release resources.
- A wait policy with a timeout or error reporting at the application layer, especially for services that may hang.
- A rule against creating new non-daemon tasks during shutdown.

### 3.2. Daemon Java Thread

~~~java
Thread background = new Thread(() -> {
    // Work that only needs to run while the JVM is still active.
}, "best-effort-worker");

background.setDaemon(true);
background.start();
~~~

**Daemon threads do not keep the JVM alive** under termination conditions the way non-daemon threads do. When the VM completes shutdown, a daemon thread still executing Java code **is not guaranteed to finish its remaining Java code**, including `finally` blocks or incomplete file writes.

Daemon is **not** a "safely auto-cleaned" mode. Use it only for work that is genuinely allowed to stop when the JVM terminates. If the work needs to flush data, commit/roll back transactions, or close connections, you must perform an explicit stop/join step before shutdown.

### 3.3. Attached Native Thread

An operating system native thread that is **not attached** to the JVM is an independent OS thread: it has no valid `JNIEnv *` and **is not automatically counted** as a Java non-daemon thread. However, once it attaches successfully, its status changes.

| Native thread type | Attach API | Impact on `DestroyJavaVM` |
| --- | --- | --- |
| Not attached to JVM | No attach call | Not counted as a Java non-daemon thread, but the host must still manage the OS thread's resources |
| Attached **non-daemon** | `AttachCurrentThread` | May cause Destroy to wait until it detaches or terminates properly |
| Attached **daemon** | `AttachCurrentThreadAsDaemon` | Does not itself block shutdown due to daemon status, but its Java code may be halted when the VM shuts down |
| Thread created by `JNI_CreateJavaVM` | Attached by VM as main thread | The thread calling Destroy does not have to terminate itself before its own call completes |

Calling `AttachCurrentThreadAsDaemon` **does not convert** an already-attached non-daemon thread into a daemon thread: once attached, a subsequent attach call usually just returns the current `JNIEnv *` and **does not change the daemon status**. To choose the status, decide while the thread is still unattached.

Example in **an independent OS worker thread**, after receiving `JavaVM *vm` from the host (illustrative, not standalone source):

~~~c
JNIEnv *env = NULL;
jint rc = (*vm)->AttachCurrentThread(
        vm, (void **)&env, NULL);

if (rc == JNI_OK) {
    /* Use env ONLY on this thread. */
    /* Finish JNI work, close owned resources... */
    (*vm)->DetachCurrentThread(vm);
}
~~~

Same idea, but as a daemon:

~~~c
JNIEnv *env = NULL;
jint rc = (*vm)->AttachCurrentThreadAsDaemon(
        vm, (void **)&env, NULL);

if (rc == JNI_OK) {
    /* Daemon work, does not depend on the JVM staying alive forever. */
    (*vm)->DetachCurrentThread(vm);
}
~~~

In real code, you must check the return code of `DetachCurrentThread`, check for pending exceptions, and ensure no Java frames remain on the stack. Do not reuse a `JNIEnv *` from one thread on another thread. `JavaVM *` may be passed to threads that need to attach while the VM is active and under host control.

## 4. Who Does the VM Wait For and Until When?

The JNI specifications describe `DestroyJavaVM` as waiting for **remaining non-daemon threads** to terminate; **the current thread, if it is non-daemon**, is excluded from the wait condition (because it is executing the Destroy call).

Practical mental model:

~~~text
Native host (thread A, attached to JVM)
    |
    | DestroyJavaVM()
    v
  +-----------------+--------------------+
  | Java worker B   | attached OS worker C |
  | non-daemon      | non-daemon            |
  | still active    | not yet Detached      |
  +-----------------+--------------------+
    |                                     |
    +----------- B finishes, C detaches --+
                      |
                      v
          VM begins shutdown sequence
                      |
          shutdown hooks complete
                      |
                      v
             DestroyJavaVM returns
~~~

**The wait condition is not counting all OS threads in the process.** An unattached native OS thread is not in the set of Java non-daemon threads, but if it holds a mutex/handle that a Java thread needs in order to finish, it can still **indirectly** cause `DestroyJavaVM` to hang.

Similarly, a daemon Java thread might hold a lock that a non-daemon worker is waiting on; therefore, even though a daemon thread does not directly block VM shutdown, resource dependencies between threads can still prevent a non-daemon thread from exiting.

Do not assume a fixed wait duration: the API has no timeout parameter. If a non-daemon thread never terminates, `DestroyJavaVM` may **wait indefinitely**. Timeouts must be designed **before calling Destroy**, at the host or Java lifecycle layer.

### 4.1. "All Non-Daemons Are Done" Does Not Mean the VM Shuts Down Immediately

Once the non-daemon condition is satisfied, the VM still runs Java's **shutdown sequence**. Related tasks may include:

- Starting **shutdown hooks** registered via `Runtime.getRuntime().addShutdownHook`.
- Waiting for shutdown hooks to finish.
- Stopping remaining Java code execution and reclaiming VM resources to the extent supported by the implementation.

A shutdown hook can also hang if it deadlocks, waits on I/O, or waits on a thread/resource that no longer exists. Therefore:

**The non-daemon condition and the shutdown hooks completion condition are two separate stages.** Both affect when `DestroyJavaVM` can return.

According to modern JNI specifications, the JVM terminates with a **best-effort** approach to resource reclamation; there is no guarantee that all memory mappings, native libraries, or application handles are restored to their state prior to the JVM's existence.

## 5. Practical Java 17+ and C11 Example: Coordinated Shutdown

This example creates a JVM from C, starts a **non-daemon Java worker**, tells the worker to stop using a `CountDownLatch`, and then calls `DestroyJavaVM`.

The important goal is the ordering:

1. The native host creates the JVM.
2. Native code calls `EmbeddedLifecycle.startWorker()`.
3. The non-daemon Java worker runs, signals that it is ready, and waits for the stop signal.
4. The native host prints the shutdown message, then calls `requestStop()` from Java.
5. The worker exits and prints that it has finished.
6. The native host calls `DestroyJavaVM` and prints the final line only after it returns `JNI_OK`.

Thanks to the two `CountDownLatch` instances, the **stdout order in the success case** is deterministic. The program does not measure or guarantee a millisecond wait duration; the point is that the host **does not block itself from sending the stop signal** to the worker.

### 5.1. `EmbeddedLifecycle.java` File

~~~java
import java.util.concurrent.CountDownLatch;

public final class EmbeddedLifecycle {
    private static final CountDownLatch READY = new CountDownLatch(1);
    private static final CountDownLatch STOP = new CountDownLatch(1);

    private EmbeddedLifecycle() {
    }

    public static void startWorker() throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println("Java: worker started");
            READY.countDown();

            try {
                STOP.await();
                System.out.println("Java: worker finished");
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        }, "example-non-daemon");

        worker.setDaemon(false);
        worker.start();

        // Host does not proceed until the worker has actually started.
        READY.await();
    }

    public static void requestStop() {
        STOP.countDown();
    }
}
~~~

**Points to note:**

- `worker.setDaemon(false)` explicitly sets **non-daemon** before `start`.
- `READY.countDown()` notifies the host that the worker has printed its first line and is ready to wait on `STOP`.
- `STOP.await()` is an **intentional blocking** operation by the worker; without `requestStop`, the worker cannot complete its normal work.
- `requestStop` opens the latch via `STOP.countDown()`. Opening the latch does not destroy the JVM by itself; the worker actually needs to exit.
- `InterruptedException` is handled in idiomatic Java fashion: restoring the interrupt flag. In the normal execution path of this example, no thread interrupts the worker.
- The Java program does not need a `main` method. It is called by the C host via JNI `FindClass` and `CallStaticVoidMethod`.

This is **complete Java source** compatible with JDK 17 and later.

### 5.2. Compiling Java

Create a working directory `embed-jvm-lifecycle` with two source files:

~~~text
embed-jvm-lifecycle/
├── EmbeddedLifecycle.java
└── embed_host.c
~~~

Run from this directory:

~~~bash
javac EmbeddedLifecycle.java
~~~

After this command, `EmbeddedLifecycle.class` will be produced (along with any additional class files generated by `javac` if needed). **Do not use `java EmbeddedLifecycle` to run it** because this class has no `main`; the **native executable** is the entry point.

### 5.3. Complete C File: `embed_host.c`

~~~c
#include <jni.h>
#include <stdio.h>
#include <stdlib.h>

/* Use outside Java callbacks and before VM shutdown.
 * In debug mode, print JNI exception and clear pending exception.
 */
static void report_java_exception(JNIEnv *env) {
    if ((*env)->ExceptionCheck(env)) {
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }
}

int main(void) {
    JavaVM *vm = NULL;
    JNIEnv *env = NULL;
    jclass cls = NULL;
    jmethodID start = NULL;
    jmethodID stop = NULL;
    int worker_started = 0;
    int ok = 0;

    JavaVMOption options[1];
    options[0].optionString = "-Djava.class.path=.";
    options[0].extraInfo = NULL;

    JavaVMInitArgs args = {0};
    args.version = JNI_VERSION_1_6;
    args.nOptions = 1;
    args.options = options;
    args.ignoreUnrecognized = JNI_FALSE;

    jint create_rc = JNI_CreateJavaVM(
            &vm, (void **)&env, &args);

    if (create_rc != JNI_OK || vm == NULL || env == NULL) {
        fprintf(stderr, "Cannot create JVM: %d\n", (int)create_rc);
        return EXIT_FAILURE;
    }

    cls = (*env)->FindClass(env, "EmbeddedLifecycle");
    if (cls == NULL) {
        report_java_exception(env);
        goto shutdown;
    }

    start = (*env)->GetStaticMethodID(
            env, cls, "startWorker", "()V");
    if (start == NULL) {
        report_java_exception(env);
        goto shutdown;
    }

    stop = (*env)->GetStaticMethodID(
            env, cls, "requestStop", "()V");
    if (stop == NULL) {
        report_java_exception(env);
        goto shutdown;
    }

    worker_started = 1;
    (*env)->CallStaticVoidMethod(env, cls, start);
    if ((*env)->ExceptionCheck(env)) {
        report_java_exception(env);
        goto shutdown;
    }

    puts("Native: requesting VM shutdown");
    fflush(stdout);

    /* Send STOP signal before calling DestroyJavaVM. */
    (*env)->CallStaticVoidMethod(env, cls, stop);
    if ((*env)->ExceptionCheck(env)) {
        report_java_exception(env);
        goto shutdown;
    }

    ok = 1;

shutdown:
    /* Error path: attempt to wake a worker that was already started.
     * Do not call Java if the corresponding class/method was not obtained.
     */
    if (!ok && worker_started && cls != NULL && stop != NULL) {
        (*env)->CallStaticVoidMethod(env, cls, stop);
        report_java_exception(env);
    }

    if (cls != NULL) {
        (*env)->DeleteLocalRef(env, cls);
    }

    /* After this call, do not use env/vm as a live VM. */
    jint destroy_rc = (*vm)->DestroyJavaVM(vm);
    if (destroy_rc != JNI_OK) {
        fprintf(stderr, "DestroyJavaVM failed: %d\n",
                (int)destroy_rc);
        return EXIT_FAILURE;
    }

    if (ok) {
        puts("Native: DestroyJavaVM returned JNI_OK");
        return EXIT_SUCCESS;
    }

    return EXIT_FAILURE;
}
~~~

**This is a standalone C11 program**, not an exported JNI method. `JNI_CreateJavaVM` is linked by the host against the JDK's corresponding `libjvm`/`jvm.dll` runtime library. It returns `JavaVM *` and `JNIEnv *` for the thread that created the VM; this thread continues to control the VM lifecycle.

Because the example **has no Java methods on the host's stack when calling Destroy**, calling `DestroyJavaVM` here is in a more appropriate context than calling it inside a Java → native callback.

Explanation of choices in C:

- `JNI_VERSION_1_6` is an **Invocation/JNI API version** level supported by JDK 17; it does not mean the program is running JDK 6.
- `JNI_CreateJavaVM`/`DestroyJavaVM` return **status codes**, where success is `JNI_OK`.
- `FindClass` uses the internal class name `"EmbeddedLifecycle"`; since the class has no package, no `/` is needed.
- `GetStaticMethodID` uses the descriptor `"()V"` because both `startWorker` and `requestStop` take no parameters and return `void`; `throws InterruptedException` does not change the descriptor.
- `report_java_exception` is for the error path, using `ExceptionDescribe` when a pending exception exists. `ExceptionClear` is an explicit decision on the diagnostic path to allow cleanup; do not clear unconditionally in normal execution flow.
- `worker_started` allows the error path to emit `requestStop` before calling Destroy if starting the worker encounters an exception after the thread has already started.
- `DeleteLocalRef` frees the local handle before shutdown. There are no global references or native workers that need cleanup in this example.
- After `DestroyJavaVM` returns success, **do not use `env` or `vm` to make any further JNI calls**.

### 5.4. Compiling the Native Host on Linux

Set `JAVA_HOME` to the root directory of JDK 17+; verify that `$JAVA_HOME/include/jni.h` and `$JAVA_HOME/lib/server/libjvm.so` exist.

~~~bash
cc -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host
~~~

`-L` helps the **linker** find `libjvm.so` at build time. `-Wl,-rpath,...` adds the shared library search path for the program at runtime. If your OS/toolchain has a different policy, configure the dynamic loader accordingly; the library and executable must share the **same CPU architecture**.

Run:

~~~bash
./embed_host
~~~

### 5.5. Compiling on macOS

~~~bash
cc -std=c11 -Wall -Wextra \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host
~~~

Run:

~~~bash
./embed_host
~~~

On macOS, actual paths and code signing/sandbox policies can affect JVM loading. Check `JAVA_HOME`, ARM64/x86-64 architecture, and the location of `libjvm.dylib` in your installed JDK.

### 5.6. Compiling on Windows x64

Open **x64 Native Tools Command Prompt for Visual Studio** and use an x64 JDK:

~~~bat
cl /nologo /W4 /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" embed_host.c /link /LIBPATH:"%JAVA_HOME%\lib" jvm.lib /OUT:embed_host.exe
~~~

Before running, so the Windows loader can find `jvm.dll`:

~~~bat
set "PATH=%JAVA_HOME%\bin\server;%JAVA_HOME%\bin;%PATH%"
embed_host.exe
~~~

Only run the steps for your operating system. Linker warnings or missing DLLs are usually JDK path/ABI/runtime dependency issues, **not** `DestroyJavaVM` logic bugs.

### 5.7. Successful Stdout

When using the exact source and classpath above, the expected output is:

~~~text
Java: worker started
Native: requesting VM shutdown
Java: worker finished
Native: DestroyJavaVM returned JNI_OK
~~~

Ordering explanation:

1. The Java worker prints the first line and then calls `READY.countDown`; the host only leaves `startWorker` once the latch is opened.
2. The host prints "requesting VM shutdown" **before** calling `requestStop`.
3. The Java worker can only print "worker finished" **after** `STOP.countDown` has been executed.
4. The final line is printed only **after `DestroyJavaVM` returns `JNI_OK`**.

This example demonstrates **properly ordered shutdown coordination**. It does not attempt to prove how many milliseconds `DestroyJavaVM` waited, because after the host sends the stop signal, the worker may finish very quickly. The general point is that if the worker **is still alive** when Destroy begins, the VM cannot complete shutdown until the non-daemon condition is resolved.

## 6. Anti-Pattern: Calling Destroy Before Signaling the Worker to Stop

This is a classic deadlock scenario:

~~~text
Native host thread                        Java worker (non-daemon)
         |                                           |
         | startWorker()                             | STOP.await()
         |                                           |
         | DestroyJavaVM()                           | (waiting for signal)
         |  -> waits for non-daemon worker to finish |
         |                                           |
         | requestStop()  <-- NEVER REACHED          |
         |                                           |
         +-------------------- wait cycle -----------+
~~~

C snippet with **wrong conceptual ordering** (not standalone source):

~~~c
(*env)->CallStaticVoidMethod(env, cls, start);

/* WRONG: worker is still waiting on STOP, but host enters Destroy first. */
(*vm)->DestroyJavaVM(vm);

/* This line will not run if Destroy is still waiting on the worker. */
(*env)->CallStaticVoidMethod(env, cls, stop);
~~~

Besides the hang risk, the last line is also wrong because **you must not use `JNIEnv *` after Destroy completes**.

Correct approach:

~~~c
(*env)->CallStaticVoidMethod(env, cls, start);

/* The stop signal must be sent while VM and env are still valid. */
(*env)->CallStaticVoidMethod(env, cls, stop);

/* Only Destroy after a valid shutdown has been initiated. */
jint rc = (*vm)->DestroyJavaVM(vm);
~~~

Both snippets above illustrate ordering; in real usage you must check JNI exceptions, worker state, and clean up references as shown in the complete example in Section 5.

### 6.1. Worker Stuck in Java Without a Timeout

Example of an infinite-loop Java worker:

~~~java
Thread worker = new Thread(() -> {
    while (true) {
        // No exit condition and no valid cancellation mechanism.
    }
}, "stuck-worker");
worker.setDaemon(false);
worker.start();
~~~

If this thread remains non-daemon, `DestroyJavaVM` may never be unblocked. **Do not use `Thread.stop`** as a cleanup mechanism; it is unsafe and has been removed from modern Java practice.

Instead, build a loop with a `volatile`/atomic stop flag, interrupt-aware wait, closeable queue, or a shutdown protocol; place a timeout **before** the `DestroyJavaVM` call if you need to detect workers that refuse to exit. Timeouts like `Future.get(timeout)` or `Thread.join(timeout)` belong to the orchestration layer; **they do not turn `DestroyJavaVM` into a timeout-capable API**.

### 6.2. Attached Native Worker Forgetting to Detach

A native thread attached as non-daemon like this:

~~~c
/* Algorithmic example inside a self-created OS thread. */
JNIEnv *worker_env = NULL;
if ((*vm)->AttachCurrentThread(
        vm, (void **)&worker_env, NULL) == JNI_OK) {
    /* Worker runs JNI work... */
    /* WRONG: reaches end of code path without DetachCurrentThread. */
}
~~~

A valid design must ensure the attached thread is managed until `DetachCurrentThread` is called in an appropriate state, before the worker OS thread terminates. An attached non-daemon thread waiting forever on I/O, a lock, or a signal can keep Destroy blocked.

Using `AttachCurrentThreadAsDaemon` **is not a cleanup fix**: a daemon native thread still holds OS resources and may be executing native code when the VM terminates; it must not call back into a terminated JVM. Thread lifecycles must be controlled by the host.

## 7. Shutdown Hooks and Additional Conditions

Java can register a shutdown hook:

~~~java
Runtime.getRuntime().addShutdownHook(
        new Thread(() -> System.out.println("Java: shutdown hook")));
~~~

This is an **illustrative pattern**, not added to the hands-on code in Section 5, so **it does not appear in the stdout** shown earlier.

When the JVM begins its **shutdown sequence**, registered hooks are run. Hooks are typically started in an unspecified order and may run concurrently. The JVM waits for hooks to finish; a hook that hangs on network/locks or waits on a resource with the wrong lifecycle will prolong shutdown.

Design points:

- Hooks should be **short and finite**, avoiding dependencies on threads or services that have already been stopped.
- Do not rely on hooks being called in every kind of process termination, such as native crashes, uncatchable kills, power loss, or `Runtime.halt`.
- Do not create a wait cycle between a hook and the native host. If a hook waits for a task that the host only performs after `DestroyJavaVM`, a deadlock easily occurs.
- Distinguish **terminating Java threads** from **cleaning up resources owned by the native host**; the host remains responsible for closing its own file descriptors, mutexes, and libraries.

### 7.1. Comparing `DestroyJavaVM`, `System.exit`, and `Runtime.halt`

| Mechanism | Typical caller | Notable semantics |
| --- | --- | --- |
| `DestroyJavaVM` | C/C++ host via Invocation API | Requests termination of embedded VM; waits for non-daemon condition and shutdown sequence; returns status code to host |
| `System.exit(status)` | Java code | Initiates VM/JVM process shutdown via `Runtime.exit`; not a normal return-to-host call like `DestroyJavaVM` |
| `Runtime.halt(status)` | Java code | Forces VM/process termination **without** guaranteeing shutdown hooks run; reserved for special situations |
| `Thread.interrupt` | Managing thread | Stop-request/cooperative cancellation signal for a single thread; **does not destroy the VM itself** |
| `Thread.setDaemon(true)` before start | Thread creator | Controls whether the thread **keeps the VM alive**; does not provide a cleanup protocol |

A serious embedded application needs agreement on **who owns shutdown authority**. Do not let Java code, signal handlers, and multiple native threads race to terminate the VM while another component is still making JNI calls.

## 8. Why Must the Native Host Manage Each Thread?

### 8.1. Difference Between `JavaVM *` and `JNIEnv *`

- `JavaVM *` is the Invocation API-level interface to the JVM, used to attach/detach threads and Destroy the VM.
- `JNIEnv *` is the JNI interface bound to the **current thread**; it cannot be shared directly with another thread.
- The thread that creates the VM receives `JNIEnv *` from `JNI_CreateJavaVM`; native workers created by the host must call `AttachCurrentThread` or `AttachCurrentThreadAsDaemon` before calling JNI.
- An attached native thread must detach at the right time; **do not** call `DetachCurrentThread` while Java methods are still on the call stack.

After Destroy succeeds, do not reuse `JNIEnv *`, `jobject`, `jclass`, method IDs, or `JavaVM *` as if they still pointed to an active JVM. Pure C/C++ resources have their own lifecycles and must be freed with their corresponding APIs.

### 8.2. A Non-Daemon Native Thread Can Block Shutdown Without "Running Java"

Example of a native thread:

1. Calls `AttachCurrentThread` successfully.
2. Calls a Java method and returns to C.
3. Waits on `pthread_cond_wait`/socket or mutex **without detaching**.
4. Host calls `DestroyJavaVM`.

That thread is still considered **attached non-daemon** inside the JVM, even though it is currently running/waiting in native code. Therefore, Destroy cannot assume the thread is finished just because its current Java stack is empty. The host should ask the worker to stop, wake it up, wait for it to detach or terminate, and only then call Destroy.

### 8.3. Attached Daemons Do Not Guarantee Work Completion

With `AttachCurrentThreadAsDaemon`, the thread does not itself prevent VM shutdown. However, if the VM terminates while the worker still wants to call Java:

- Native code may continue running for some time depending on the runtime and thread state.
- You cannot trust that subsequent JNI calls will succeed once shutdown has started/finished.
- Running Java code may be halted when the VM terminates.
- The worker's C/C++ resources still need a host-level cleanup protocol.

If the work needs guaranteed data writes, choose **explicit stop + join/detach** even for daemon threads, rather than treating daemon mode as a complete shutdown solution.

## 9. Optimizing the Shutdown Flow in Real Applications

Before calling `DestroyJavaVM`, implement a clear state sequence:

~~~text
RUNNING
   |
   | host stops accepting new requests
   v
QUIESCING
   |
   | signal stop, close input queues, cancel blocking IO safely
   v
DRAINING
   |
   | wait for Java workers to finish
   | wait for native-attached non-daemon workers to detach
   | block new JNI callbacks
   v
READY_TO_DESTROY
   |
   | no host Java frames remain on stack
   | VM-owning host calls DestroyJavaVM exactly once
   v
DESTROYING
   |
   | VM waits for remaining non-daemons + shutdown hooks
   v
TERMINATED
   |
   | JNI interfaces/references are no longer valid
   v
Native process continues cleanup outside VM or exits
~~~

Note: this is an **application-level recommended protocol**, not enum states provided by the JNI Specification.

In practice:

- Have a single **owner** responsible for the VM lifecycle.
- Stop the source of new requests before asking workers to terminate.
- Send the stop signal **before** waiting for results or calling Destroy.
- Java workers can be joined with `Thread.join(timeout)` or `ExecutorService.shutdown()`/`awaitTermination`; native OS threads can be joined using OS APIs.
- Do not hold a mutex that a worker needs in order to exit while the owner is waiting on that worker.
- For an attached native worker, typically perform **JNI cleanup → DetachCurrentThread → thread termination**.
- Once Destroy begins, do not start a new round of attaches or new Java callbacks.
- Log timestamps and thread names to diagnose waits; write logs somewhere that will not block/deadlock the shutdown flow itself.

### 9.1. Timeout Before Destroy, Not "Timeout Destroy"

`DestroyJavaVM` **does not accept a timeout**. If a system requirement says "must shut down within 5 seconds," the application must be designed to:

1. Send the stop request and stop creating new work.
2. Use a timeout mechanism at the Java/native worker level to verify that it has stopped.
3. If a worker does not stop, log the reason clearly and trigger an escalation policy in the **host supervisor**, such as isolating work in a separate process.
4. Call `DestroyJavaVM` only when critical dependencies are known to be resolved or when the JVM's wait condition is acceptable.

Do not arbitrarily kill OS threads attached to the JVM, or manually `free` VM memory, as doing so can corrupt the entire process. When a reliable "JVM restart" is needed, isolating the JVM in a **child process** is usually safer than trying to tear down the JVM inside a long-lived process.

## 10. Return Codes and Error Handling for `DestroyJavaVM`

In C:

~~~c
jint status = (*vm)->DestroyJavaVM(vm);
if (status == JNI_OK) {
    puts("VM shutdown completed");
} else {
    fprintf(stderr, "VM shutdown failed: %d\n", (int)status);
}
~~~

This is an illustrative snippet, assuming `vm` is valid and called at the right time.

Points to check:

| Status | Meaning | Action |
| --- | --- | --- |
| `JNI_OK` | VM completed its termination sequence per implementation | Do not use JNI VM/references afterward; continue native host cleanup |
| Negative JNI error code | VM could not complete the request properly | Log the code, avoid proceeding as if the VM exited cleanly; check JNI spec/JVM logs |
| Call does not return | Usually an unfinished or stuck non-daemon thread/hook | Diagnose waiting threads and resource relationships; no built-in timeout |
| Host crash | May be caused by invalid pointer, JNI lifetime/ABI, or native memory | Check native crash logs, toolchain, ownership; do not blame Destroy for every crash |

**Important:** `DestroyJavaVM` returning success does **not** mean all native OS threads in the process have been joined, all file descriptors have been closed, or all native libraries have been unloaded from the process. Resources owned by the C/C++ host must be managed separately.

### 10.1. Destroying a JVM Does Not Mean "Recreating a JVM"

With common JDK/HotSpot implementations, **there is no contract supporting creating multiple JVMs in one process**. The JDK 17 JNI Specification explicitly states the limitation: creating multiple VMs in a single process is not supported; historical documentation also notes that VM unloading is not fully supported.

Therefore:

- Do not design a `CreateJavaVM → DestroyJavaVM → CreateJavaVM` loop and assume it will work.
- Do not rely on `DestroyJavaVM` as a promise that all VM state has been completely wiped and `libjvm` can be safely unloaded/reloaded.
- If the product requires starting/stopping the JVM multiple times, consider **one separate process per run**; a native supervisor can manage that process.

The hands-on example in Section 5 creates **a single VM**, destroys it, and exits the program; it does not attempt to initialize a second VM.

## 11. Common Errors

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `DestroyJavaVM` waits indefinitely | Java non-daemon worker hasn't exited; native-attached non-daemon thread hasn't detached; shutdown hook stuck | Send stop before Destroy; inspect thread dumps and shutdown logs |
| Host waits in Destroy while worker needs host to open a latch | Wait cycle in stop protocol | Reverse the order: open latch/cancel task first, then Destroy |
| Used `AttachCurrentThreadAsDaemon` but still see leaked resources | Daemon only affects shutdown condition, doesn't auto-close sockets/handles | Explicit cleanup + detach/join by owner |
| `AttachCurrentThreadAsDaemon` doesn't turn current thread into daemon | Thread was previously attached as non-daemon | Choose daemon status on the very first attach |
| Java worker finished but Destroy still waits | Another non-daemon attached native thread, shutdown hook, or another Java thread exists | Check **all** sources of non-daemon threads, not just one worker |
| Cannot call JNI after Destroy | `JNIEnv *`/VM references expired | Forbid callbacks and JNI usage after TERMINATED state |
| Error in `JNI_CreateJavaVM` | Wrong JDK path/ABI, JNI version, or options | Check return code, libjvm, JDK architecture, and option strings |
| Java callback still on stack during Destroy | Host calls shutdown inside a native method invoked by Java | Exit the callback first, then have the host Destroy |
| `System.exit` prevents native host from running desired cleanup | Two shutdown mechanisms with different ownership | Define owner in the host; do not use `System.exit` to replace Destroy |
| Attempting to create a second JVM fails | Multi-VM/re-init in the same process is unsupported | Run the JVM in a child process when restart is needed |

### 11.1. How to Diagnose Threads That Refuse to Exit

- Log the exact names of running **Java non-daemon** workers, their tasks, and whether the stop signal has been sent.
- Check whether native-attached threads execute `DetachCurrentThread` on every exit branch.
- Check whether locks needed by shutdown hooks/workers are still held by the host when calling Destroy.
- Depending on the JVM, use a thread dump (e.g., `jcmd <pid> Thread.print` or an appropriate signal) **while the VM is still running** to inspect Java stacks and locks. Do not expect this tool to work after VM shutdown completes.
- If you only see that one Java thread has exited, do **not** rush to conclude that all VM termination conditions are met: you must also check attached native threads and shutdown hooks.
- Use timeouts at the work-management layer to gather reasons, rather than hanging indefinitely inside `DestroyJavaVM` and losing the ability to send stop signals.

## 12. Contrasting Commonly Confused Concepts

| Concept | Should not be misunderstood as |
| --- | --- |
| `DestroyJavaVM` | "Equivalent to immediately killing the process" |
| Non-daemon | "Thread is automatically terminated by the JVM when the host wants to exit" |
| Daemon | "Everything will be flushed/cleaned up automatically" |
| `AttachCurrentThread` | "Only registers JNI, does not affect shutdown" |
| `AttachCurrentThreadAsDaemon` | "Can convert a thread already attached as non-daemon into a daemon" |
| `DetachCurrentThread` | "Can be called while Java call frames are still present" |
| `JNI_OK` | "Can continue using JNIEnv after Destroy" |
| Unattached native thread | "The JVM will automatically join/close all its resources" |
| Shutdown hooks | "Always called even on crash or Runtime.halt" |
| Successful Destroy | "Guaranteed to be able to create a new JVM in the same process" |

## 13. Review Questions and Real-World Scenarios

**Question 1.** A JVM has been created by a C host. Java has a non-daemon thread waiting on `CountDownLatch.await()`. The host calls `DestroyJavaVM` without anyone opening the latch. What happens?

**Answer:** The call may wait indefinitely because the non-daemon thread does not terminate. You must design an exit path for the worker and send the signal before the host waits for shutdown.

**Question 2.** A native OS thread calls `AttachCurrentThread` and then waits on a socket without detaching. All Java threads have exited. Is `DestroyJavaVM` guaranteed to return?

**Answer:** No. A **non-daemon attached** native thread is also part of the wait condition and must finish/detach.

**Question 3.** Does calling `AttachCurrentThreadAsDaemon` on a thread already attached with `AttachCurrentThread` turn it into a daemon?

**Answer:** No. Once a thread is attached, subsequent attach calls do not change its daemon status.

**Question 4.** Must `DestroyJavaVM` be called from the exact same thread that called `JNI_CreateJavaVM`?

**Answer:** No, according to the modern Invocation API. However, the call must have a valid context and proper lifecycle design; do not invoke it while Java methods are still on the calling thread's call stack.

**Question 5.** After `DestroyJavaVM` returns `JNI_OK`, should you use `env->FindClass` and initialize a new JVM in the same process?

**Answer:** No. Old JNI interfaces are no longer valid; recreating or running multiple VMs in a single process is not a reliably supported scenario.

**Question 6.** If a Java daemon thread is still writing logs, will the JVM wait for it to finish like a non-daemon thread?

**Answer:** No. Daemon threads do not block VM shutdown; to ensure logs are flushed, you must have an explicit stop/wait mechanism.

**Question 7.** `DestroyJavaVM` waits until no other non-daemon threads remain. What else might it wait for?

**Answer:** The shutdown sequence, which includes shutdown hooks; hung hooks can also prevent the VM from terminating.

**Question 8.** Why should the native host own shutdown instead of letting a Java callback call `DestroyJavaVM`?

**Answer:** The host can wait for the Java call stack to return, prevent new callbacks, issue stop signals, and control all Java/native threads. Calling Destroy directly inside a Java → native callback has an inappropriate stack context and easily causes deadlocks.

## 14. Technical References

- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `JNI_CreateJavaVM`, `DestroyJavaVM`, `AttachCurrentThread`, `AttachCurrentThreadAsDaemon`, `DetachCurrentThread`, return codes, and multiple-VM limitations.
- [Oracle Java SE 21 — JNI Invocation API](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html): more detailed explanation of the Destroy calling thread context, non-daemon threads, shutdown sequence, and native threads still running when the VM terminates.
- [Java SE 17 — Runtime API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): `exit`, `halt`, and shutdown hooks.
- [Java SE 17 — Thread API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): daemon status, `join`, and `interrupt`.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): synchronizing readiness signaling and sending the stop signal.
- [Java Virtual Machine Specification — JVM Termination](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.7): VM termination conditions and differences between daemon/non-daemon threads.

**Rule to remember:** Manage threads in the order **stop accepting work → signal stop → wait for Java non-daemon and native-attached workers to finish/detach → exit the Java call stack → call `DestroyJavaVM` → check `JNI_OK`**. `DestroyJavaVM` is the final step of a shutdown protocol, not a tool to fix a hung shutdown protocol.
