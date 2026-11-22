# Detaching Native-Attached Threads and Cleaning Up References Before Exit

When Java calls a **native** method, the JVM already has a thread and provides a **JNIEnv*** to that method. Conversely, a thread created by C/C++ code using **pthread_create**, **std::thread**, or a native library must call **AttachCurrentThread** (or **AttachCurrentThreadAsDaemon**) itself before using JNI. After finishing its work, if that same thread performed the attach, it must call **DetachCurrentThread** before exiting.

**Detaching does not replace cleanup.** While attached, the worker may create local references, global references, borrow String/array pointers, hold Java monitors, or allocate native buffers. Resources must be reclaimed according to proper ownership and order, and errors must be handled before detaching the thread. Never pass a **JNIEnv*** between threads or use it after detaching.

Learning objectives: explain *who is responsible for detaching*, *which references to clean up and with which APIs*, *when a Java callback is considered finished*, *how to handle errors*, and practice on a real Java 17+ native worker.

## 1. Two Java–Native Paths

~~~text
Java creates thread
  Java Thread.run()
    -> calls native method via JNI
       -> native receives existing JNIEnv*
       -> frees needed native resources and local refs
    <- native method returns
  Java continues managing thread

Native creates thread
  pthread_create / std::thread
    -> thread not attached to JVM: no JNIEnv*
    -> AttachCurrentThread -> receives this thread's JNIEnv*
    -> creates and uses JNI references
    -> Call...Method -> Java callback -> returns to native
    -> releases borrowed buffers, references, locks
    -> DetachCurrentThread
    -> native thread exits
~~~

In the first case, the native method usually **must not detach the Java thread itself**: while the native method is executing, there are still Java frames on the stack. In the second case, created and attached by native code, the native worker is responsible for detaching after all Java methods on the call stack have returned. The JNI specification explicitly states that **a thread cannot detach while Java methods remain on the call stack**.

**AttachCurrentThread** attaches as a non-daemon Java thread. **AttachCurrentThreadAsDaemon** attaches as a daemon. Calling attach when the thread is already attached returns the existing interface, *without changing the daemon status*. Daemon status only affects the condition for keeping the JVM alive during shutdown; **it does not remove the obligation to clean up or detach**.

## 2. JavaVM*, JNIEnv*, and Ownership

| Component | Scope | Rule |
| --- | --- | --- |
| **JavaVM*** | Represents the JVM; can be passed to workers while the JVM is alive | Used for **GetEnv**, **AttachCurrentThread**, **DetachCurrentThread** |
| **JNIEnv*** | Only valid on the thread that received it | Never obtain env on thread A and use it on B |
| **jobject/jclass local ref** | Local reference only valid within its thread and corresponding local frame | Do not send local refs across threads |
| **NewGlobalRef** | Creates a reference usable across attached threads | Must call **DeleteGlobalRef** according to owner lifecycle |
| **NewWeakGlobalRef** | Weak reference, does not guarantee the object still exists | Must call **DeleteWeakGlobalRef** when no longer needed |
| **jmethodID/jfieldID** | Opaque ID, not a jobject reference | Do not call **DeleteLocalRef/GlobalRef** on an ID |

A helper might be called from both Java threads and native threads. To avoid accidentally detaching an attachment it did not create, check the status before attaching:

~~~c
/*
 * Fragment running in a C function returning void.
 * vm is a valid JavaVM*; cleanup must be added at the exit point.
 */
JNIEnv *env = NULL;
int attached_here = 0;
jint status = (*vm)->GetEnv(vm, (void **)&env, JNI_VERSION_1_6);

if (status == JNI_EDETACHED) {
    status = (*vm)->AttachCurrentThread(vm, (void **)&env, NULL);
    if (status != JNI_OK) {
        return; /* No valid JNIEnv*. */
    }
    attached_here = 1;
} else if (status != JNI_OK) {
    return; /* For example, JNI_EVERSION. */
}

/* Call JNI here; all error paths must go through cleanup. */

if (attached_here) {
    status = (*vm)->DetachCurrentThread(vm);
    /* A real application must report/handle status != JNI_OK. */
}
~~~

**GetEnv** returns **JNI_OK** if the thread is already attached, **JNI_EDETACHED** if not attached, and **JNI_EVERSION** if the JNI version is not supported. If a helper calls **AttachCurrentThread** when the thread was already attached, the helper does not automatically become the owner of the attachment. Save **attached_here** for the cleanup procedure.

**DetachCurrentThread operates on the current thread.** The original Java thread cannot call this function to detach another pthread remotely; the worker detaches itself when finished.

## 3. Resources That Must Be Cleaned Up Before Exiting

| Resource | Created with | Cleaned up with |
| --- | --- | --- |
| Local reference to **jstring**, **jclass**, **jobject**, **jarray** | **FindClass**, **NewStringUTF**, **CallObjectMethod**, etc. | **DeleteLocalRef** or **PopLocalFrame** |
| Global reference | **NewGlobalRef** | **DeleteGlobalRef** |
| Weak global reference | **NewWeakGlobalRef** | **DeleteWeakGlobalRef** |
| Temporary pointer from Java string | **GetStringUTFChars**, **GetStringChars** | Corresponding **ReleaseStringUTFChars**, **ReleaseStringChars** |
| Primitive array elements | **GetIntArrayElements** and variants | **ReleaseIntArrayElements** and the exact matching variant |
| Critical pointer | **GetPrimitiveArrayCritical**, **GetStringCritical** | Corresponding Release Critical, keep critical region very short |
| Java monitor held by native | **MonitorEnter** | **MonitorExit** |
| Native-managed memory/OS resources | **malloc**, **new**, file/socket/lock | **free**, **delete**, close/unlock per the corresponding native API |

### 3.1. Local References and Long-Lived Attached Threads

In a native method called from Java, local references are normally reclaimed when the **native method returns**. A native-attached worker can run for a very long time without a native invocation returning to Java, so local refs it creates will easily **accumulate until detach**. On common runtimes, a detached thread has its remaining refs reclaimed by the JVM, but waiting until then can still cause out-of-memory errors or exhaustion of reference slots.

Example fix when processing many items:

~~~c
/* Fragment: env is valid on an attached native worker. */
for (int i = 0; i < 100000; i++) {
    jstring item = (*env)->NewStringUTF(env, "value");
    if (item == NULL) {
        /* Report error, handle pending exception before exiting. */
        break;
    }

    /* Use item in the current iteration. */

    (*env)->DeleteLocalRef(env, item);
}
~~~

If an iteration creates multiple references, using **PushLocalFrame(env, capacity)** and **PopLocalFrame(env, NULL)** can simplify cleanup. Every successful **PushLocalFrame** must have a matching **PopLocalFrame** on every exit path; do not use a local ref from a popped frame. **EnsureLocalCapacity** only prepares capacity; it does not delete already-created references.

**DeleteLocalRef** does not mean immediately freeing the Java object; it only removes one JNI reference, allowing GC to reclaim the object when no other strong references remain.

### 3.2. Global References Are Not Automatically Deleted on Detach

**NewGlobalRef** creates a strong reference keeping a Java object alive that can be used across other attached threads. It persists until **DeleteGlobalRef** is called, even if the thread that created the ref has died. Do not delete it prematurely while a worker still needs the object, and do not keep it indefinitely when the callback/job finishes.

A clear ownership model:

~~~text
Java thread calls native
  -> NewGlobalRef(callbackClass)
  -> hands over reference ownership to job
  -> native worker attaches
  -> uses callbackClass to call Java
  -> DeleteGlobalRef(callbackClass)
  -> DetachCurrentThread
  -> job finishes
~~~

If the worker **fails to attach**, the worker does not have a valid env to delete the ref. The thread that created the global ref must have a **fallback cleanup** path after knowing the worker has finished. It must guarantee **exactly one deletion**, no double-delete, and no deletion while another worker is still using the reference.

**Weak global references** do not keep an object alive like strong global refs, but **DeleteWeakGlobalRef** must still be called to free management resources. To use an object via a weak ref, create a strong **NewLocalRef** and check that the result != NULL; merely checking **IsSameObject(weak, NULL)** and then continuing to use the weak ref does not guarantee GC has not made the object disappear between the two operations.

### 3.3. Borrowed Pointers and Monitors Have Separate Lifecycles

Do not confuse a **jstring local ref** with the pointer returned from **GetStringUTFChars**:

~~~c
/* Fragment: str is a valid local ref. */
const char *chars = (*env)->GetStringUTFChars(env, str, NULL);
if (chars != NULL) {
    /* Use chars... */
    (*env)->ReleaseStringUTFChars(env, str, chars);
}
(*env)->DeleteLocalRef(env, str);
~~~

**chars** must be released with the corresponding function **before deleting the local ref str**. Likewise, **DeleteLocalRef** on a **jintArray** does not replace **ReleaseIntArrayElements**. After the final Release, pointers obtained via JNI are no longer permitted to be used.

If native code called **MonitorEnter**, call **MonitorExit** properly before detaching. The JNI spec notes that DetachCurrentThread may release held Java monitors, but a correct program does not rely on this side effect to fix a forgotten unlock, because doing so can break the application's synchronization invariants.

## 4. Runnable Java 17+ and C/POSIX Example

The program creates a pthread from a native method. The worker itself calls **GetEnv**, **AttachCurrentThread**, calls back into a static Java method three times, releases the **jstring** local refs and UTF buffers, deletes a **jclass global ref**, and then detaches. Finally **GetEnv** confirms the thread is detached; the Java thread waits using **pthread_join**.

The example runs on **Linux/JDK 17+** and requires a C compiler with pthread. It illustrates ownership/cleanup, not a thread pool framework.

### 4.1. AttachedCleanupDemo.java

~~~java
public final class AttachedCleanupDemo {
    static {
        System.loadLibrary("attached_cleanup");
    }

    private AttachedCleanupDemo() {}

    private static native void runWorker();

    private static String label(int index) {
        return "job-" + index;
    }

    public static void main(String[] args) {
        System.out.println("Java: start");
        runWorker();
        System.out.println("Java: end");
    }
}
~~~

### 4.2. attached_cleanup.c

~~~c
#include <jni.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>

struct Task {
    JavaVM *vm;
    jclass owner; /* Global ref, owned by task */
    int error;    /* 0 if successful */
};

static void throw_state(JNIEnv *env, const char *message) {
    jclass type = (*env)->FindClass(
            env, "java/lang/IllegalStateException");
    if (type != NULL) {
        (*env)->ThrowNew(env, type, message);
        (*env)->DeleteLocalRef(env, type);
    }
}

static void *worker_main(void *opaque) {
    struct Task *task = (struct Task *)opaque;
    JNIEnv *env = NULL;

    jint before = (*task->vm)->GetEnv(
            task->vm, (void **)&env, JNI_VERSION_1_6);
    if (before != JNI_EDETACHED) {
        task->error = 1;
        return NULL; /* Original thread will delete the global ref. */
    }

    puts("Native: before attach = detached");
    fflush(stdout);

    jint attached = (*task->vm)->AttachCurrentThread(
            task->vm, (void **)&env, NULL);
    if (attached != JNI_OK || env == NULL) {
        task->error = 2;
        return NULL;
    }

    jmethodID label = (*env)->GetStaticMethodID(
            env, task->owner, "label", "(I)Ljava/lang/String;");
    if (label == NULL) {
        task->error = 3;
        goto cleanup_attached;
    }

    for (jint i = 0; i < 3; ++i) {
        jstring value = (jstring)(*env)->CallStaticObjectMethod(
                env, task->owner, label, i);
        if ((*env)->ExceptionCheck(env)) {
            task->error = 4;
            goto cleanup_attached;
        }
        if (value == NULL) {
            task->error = 5;
            goto cleanup_attached;
        }

        const char *chars = (*env)->GetStringUTFChars(
                env, value, NULL);
        if (chars == NULL) {
            task->error = 6;
            (*env)->DeleteLocalRef(env, value);
            goto cleanup_attached;
        }

        printf("Native: %s\n", chars);
        fflush(stdout);
        (*env)->ReleaseStringUTFChars(env, value, chars);
        (*env)->DeleteLocalRef(env, value);
    }

cleanup_attached:
    if ((*env)->ExceptionCheck(env)) {
        /* Demo logs Java exception; production has its own mechanism. */
        (*env)->ExceptionDescribe(env);
        (*env)->ExceptionClear(env);
    }

    (*env)->DeleteGlobalRef(env, task->owner);
    task->owner = NULL;

    jint detached = (*task->vm)->DetachCurrentThread(task->vm);
    if (detached != JNI_OK) {
        task->error = 7;
        return NULL;
    }

    /* Do not use env after detaching. */
    JNIEnv *check_env = NULL;
    jint after = (*task->vm)->GetEnv(
            task->vm, (void **)&check_env, JNI_VERSION_1_6);
    if (after == JNI_EDETACHED) {
        puts("Native: after detach = detached");
        fflush(stdout);
    } else {
        task->error = 8;
    }
    return NULL;
}

JNIEXPORT void JNICALL
Java_AttachedCleanupDemo_runWorker(JNIEnv *env, jclass owner) {
    JavaVM *vm = NULL;
    if ((*env)->GetJavaVM(env, &vm) != JNI_OK) {
        throw_state(env, "GetJavaVM failed");
        return;
    }

    jclass global_owner = (jclass)(*env)->NewGlobalRef(env, owner);
    if (global_owner == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            throw_state(env, "NewGlobalRef failed");
        }
        return;
    }

    struct Task task = {vm, global_owner, 0};
    pthread_t thread;
    int created = pthread_create(&thread, NULL, worker_main, &task);
    if (created != 0) {
        (*env)->DeleteGlobalRef(env, global_owner);
        throw_state(env, "pthread_create failed");
        return;
    }

    /*
     * Because task is a stack variable, wait until worker stops using it.
     * In the demo, a pthread_join error is an infrastructure failure where
     * it is unsafe to continue with task residing on the stack.
     */
    if (pthread_join(thread, NULL) != 0) {
        fputs("pthread_join failed\n", stderr);
        abort();
    }

    /* Fallback if worker did not attach/delete global ref. */
    if (task.owner != NULL) {
        (*env)->DeleteGlobalRef(env, task.owner);
        task.owner = NULL;
    }

    if (task.error != 0) {
        throw_state(env, "attached worker failed");
    }
}
~~~

**Why does the example preserve the correct lifecycle?**

- **runWorker** runs on the original Java thread, receives **JNIEnv*** from the JVM, and only uses it on this thread.
- **GetJavaVM** obtains **JavaVM***; **NewGlobalRef** converts the local **owner** into a global reference so the pthread can use it validly.
- The pthread calls **AttachCurrentThread** and gets its own **JNIEnv***. The native callback via **CallStaticObjectMethod** has already returned before detaching.
- **GetStringUTFChars** is released with **ReleaseStringUTFChars**; **jstring value** is deleted with **DeleteLocalRef** in each iteration.
- The worker calls **DeleteGlobalRef** before detaching. If it does not attach successfully, the Java-entry thread deletes the global ref after joining, avoiding leaks/double-deletes.
- The worker reports errors via **task.error**; the Java-entry native method turns it into an exception for the Java caller. Pending exceptions on the worker are handled before cleaning up references.
- After detaching, the worker does not use **JNIEnv*** anymore; status checking only uses **JavaVM* -> GetEnv**.

**Note on pthread_join:** the demo uses a stack-allocated task and joins a joinable pthread. If pthread_join unexpectedly fails, it aborts the process to avoid returning while the worker might still be accessing the stack address. Production code should use a heap-allocated task, proper event/lifecycle management, a cancellation policy, and graceful shutdown.

### 4.3. Compiling on Linux

Save both files **AttachedCleanupDemo.java** and **attached_cleanup.c** in the same directory, and set **JAVA_HOME** to a JDK 17+ matching the compiler architecture:

~~~bash
javac -h . AttachedCleanupDemo.java

cc -std=c17 -Wall -Wextra -Wpedantic -fPIC -shared -pthread \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  attached_cleanup.c -o libattached_cleanup.so

java -Xcheck:jni -Djava.library.path=. AttachedCleanupDemo
~~~

**javac -h .** generates the header to verify the JNI export name **Java_AttachedCleanupDemo_runWorker** and function signature. **System.loadLibrary("attached_cleanup")** on Linux searches for a shared library following conventions such as **libattached_cleanup.so**. Compile for the target ABI/JDK; on Windows, replace the thread API and DLL build method.

**Exact stdout on the success path:**

~~~text
Java: start
Native: before attach = detached
Native: job-0
Native: job-1
Native: job-2
Native: after detach = detached
Java: end
~~~

The order is deterministic due to **pthread_join** and **fflush(stdout)**. On error paths, stderr/Java exceptions or fewer stdout lines may appear; the output above is only for the case where creation/attach/callback/detach all succeed.

## 5. Controlling Error Paths and Exceptions

Functions such as **GetStaticMethodID**, **Call...Method**, **NewStringUTF**, and **NewGlobalRef** can fail or create a pending Java exception. Do not use a returned object on error and do not continue calling arbitrary JNI functions while an exception is pending.

Flow for a native-attached worker:

~~~text
AttachCurrentThread succeeds
       |
       v
JNI call and check return / ExceptionCheck
       |
       +--- success --- process data
       |
       +--- failure --- log/package error
       |                deliberately handle pending exception
       v
Release borrowed pointers / DeleteLocalRef
       |
DeleteGlobalRef / DeleteWeakGlobalRef according to ownership
       |
Release monitors / native locks / buffers
       |
DetachCurrentThread
       |
Report status to job owner, exit native thread
~~~

**ExceptionCheck** is a way to check for a pending exception without creating a local ref. **ExceptionOccurred** creates a local reference to the Throwable, so if kept for inspection, the reference must be cleaned up appropriately. **ExceptionClear** clears the exception state; only do this once you have decided to log/propagate the error, do not swallow errors silently. **ExceptionDescribe** is useful for demos/diagnostics, but does not replace an error propagation mechanism in production.

Because a JNI-attached native thread has no Java caller waiting directly to receive an exception, leaving an exception pending and detaching **does not automatically throw the exception into another Java thread**. The JNI specification allows the VM to report the existence of a pending exception upon detach. Pass an error code/message or perform a controlled error callback while the attachment is still valid.

Conversely, a native method called by Java can return with a pending exception so the Java caller receives the error per contract; **do not detach** the Java caller thread in this situation.

## 6. PushLocalFrame/PopLocalFrame in Long-Running Workers

A native worker may process hundreds of thousands of objects. If each iteration creates local refs and waits until the final detach to release them, the JVM may spend significant resources keeping references or objects alive.

~~~c
/* Fragment on an attached worker, processing local refs in batches. */
for (int i = 0; i < 100000; ++i) {
    if ((*env)->PushLocalFrame(env, 8) != JNI_OK) {
        /* Possible resource exhaustion or pending exception. */
        break;
    }

    jstring value = (*env)->NewStringUTF(env, "temporary");
    if (value != NULL) {
        /* Use value within the scope of this local frame. */
    }

    (*env)->PopLocalFrame(env, NULL);

    if ((*env)->ExceptionCheck(env)) {
        break; /* Branch to error/cleanup in a real worker. */
    }
}
~~~

**PushLocalFrame** with a positive capacity creates a new frame; **PopLocalFrame** discards all local refs belonging to that frame. On error paths, you must still pop if push succeeded; do not use a popped ref. To keep one local ref when popping, use the **PopLocalFrame(env, result)** variant, receive the new ref belonging to the parent frame, and manage it. **EnsureLocalCapacity** does not perform ref cleanup.

In the main example, each callback only creates one **jstring**, so **DeleteLocalRef** immediately after use is clearer.

## 7. Daemon Attachment, Shutdown, and Native Cancellation

### Daemon Does Not Exempt Cleanup

**AttachCurrentThread** creates a non-daemon thread and can keep the JVM waiting for shutdown until the worker finishes. **AttachCurrentThreadAsDaemon** does not by itself keep the JVM alive, but the native worker must still detach and avoid JNI calls once the VM has terminated.

When shutting down a native thread pool, stop accepting work, signal stop, wait for running Java callbacks to return, clean up each worker's resources, detach each worker, and then release the pool's global registrations or native library resources.

### Native Cancellation Can Bypass Cleanup

**pthread_cancel**, process termination, or an uncaught C++ exception can cause a thread to take a path that does not invoke normal cleanup. In C, centralize error paths at a **cleanup** label; in C++, RAII guards can be used to release JNI resources and detach when appropriate.

If an application needs to cancel a worker, prefer cooperative stopping and ensure cleanup handlers are called on the right thread and while the JVM is still available. Do not treat destructors, TLS destructors, or **JNI_OnUnload** as magic fixes for every abnormal termination case. Do not allow a native library to be unloaded while a worker could still execute code from the library or call back into Java.

### Do Not Rely on DetachCurrentThread to Unlock

The spec describes that held Java monitors may be released on detach, but a correct program must call **MonitorExit** according to lock ownership before detaching. Native mutexes, file handles, and malloc buffers are not the JVM's responsibility; they must be released with the proper native APIs.

## 8. Common Mistakes

| Mistake | Why it is wrong | Good practice |
| --- | --- | --- |
| Native pthread exits without detaching | Violates JNI thread lifecycle rules | Detach on that pthread itself before exit |
| Carrying **JNIEnv*** from a Java thread to a pthread | Interface is thread-dependent | Attach/GetEnv on each thread |
| Helper detaches whenever AttachCurrentThread returns JNI_OK | Thread might already have been attached | Call GetEnv first and track **attached_here** |
| Detaching while a Java callback is still on the stack | Spec forbids detaching with active Java methods | Wait for callback to return to native |
| Deleting **jclass local ref** and then using it on a worker | Local reference cannot be used across threads | Create **NewGlobalRef**, delete when all workers are done |
| Waiting until detach to clean up all local refs | Long-running worker accumulates refs | DeleteLocalRef/PopLocalFrame in each iteration |
| Thinking detach deletes global/weak global refs | Global refs have a separate lifecycle | DeleteGlobalRef/DeleteWeakGlobalRef by the proper owner |
| DeleteLocalRef on String instead of ReleaseStringUTFChars | Borrowed pointer needs separate release | Release chars before deleting String ref |
| Using old env after detach | Interface is no longer valid | Do not call JNI, re-attach if needed |
| Clearing all pending exceptions without reporting errors | Loses failure cause | Propagate/log error before cleanup |
| Daemon worker does not need to detach | Daemon only changes shutdown policy | Clean up and detach as usual |
| Forgetting native mutex/free/socket | JNI does not own OS resources | Clean up via native APIs |
| Deleting global ref while another worker is still using it | Dangling reference, may crash | Synchronize owner/handoff and delete at end of life |

## 9. Application Scenarios

**Native SDK callback on its own thread.** The SDK creates a pthread, and each event needs to notify Java. Attach the worker once when it starts using JNI, store the proper **JavaVM*** and global callback ref, delete local refs in each event, handle exceptions, and detach before the SDK worker exits. If the SDK can invoke callbacks after shutdown, register stop and halt callbacks before freeing global refs.

**Media library running a worker for hours.** Each frame may create jbyteArray, jstring, or jobject local refs. Do not wait until the end of the session to detach and clean up; use **DeleteLocalRef/PopLocalFrame** per frame. Borrowed primitive arrays must be released separately and critical regions must be short.

**Plugin creates a thread pool and then the JVM shuts down.** Non-daemon attached threads can make the JVM wait; daemon threads do not guarantee remaining work will finish. Design stop/join/cleanup before VM teardown, and do not leave global refs pointing to a class loader that is no longer needed.

**Native helper used in both Java and C callbacks.** Always call **GetEnv** to know whether it is already attached. Only the party that actually attached detaches; on a Java caller thread, only clean up resources belonging to the invocation and return.

## 10. Self-Check Questions

**1.** A Java Thread is calling a native method. Should the native method call **DetachCurrentThread** before returning?

**Answer:** No. The thread is managed by the JVM and still has Java frames on the stack. Release resources belonging to the native method and return to Java.

**2.** A pthread calls **AttachCurrentThread**, calls Java, and then the native thread exits. Is it enough to just let the OS destroy the thread?

**Answer:** No. The JNI spec requires a native-attached thread to call **DetachCurrentThread** before exiting.

**3.** After **NewGlobalRef**, the native worker detached. Is the Java object held by the global ref automatically unreferenced?

**Answer:** No. A global reference must have **DeleteGlobalRef** called at the right time by its owner; detaching does not automatically delete global refs.

**4.** Why should a local **jstring** created in a 100,000-iteration loop be deleted immediately?

**Answer:** A long-running attached native worker may retain local refs until detach, leading to consumption of reference slots, keeping objects from GC, and memory risks.

**5.** A helper runs on a thread where **GetEnv** returned **JNI_OK**. May it detach when finished?

**Answer:** Usually no; the attachment belongs to whoever attached the thread earlier. The helper should only detach if it attached itself after **JNI_EDETACHED**.

**6.** Can **DetachCurrentThread** be called while a **CallStaticObjectMethod** is still executing Java code?

**Answer:** No, you must wait for the Java callback to return to native so there are no Java method frames left on the stack.

**7.** A native worker obtained a **const char*** from **GetStringUTFChars** and then deleted the jstring's local ref. Is the buffer considered returned?

**Answer:** No. You must call the matching **ReleaseStringUTFChars** while the jstring is still valid, and only then call **DeleteLocalRef**.

**8.** After detaching, can the old **JNIEnv*** be reused to create a local ref?

**Answer:** No. Only use JNIEnv* while the thread is attached and it is that thread's own interface; if you must continue using JNI, re-attach validly.

## References

- [JNI Specification Java SE 21 — Invocation API](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html): AttachCurrentThread, AttachCurrentThreadAsDaemon, GetEnv, DetachCurrentThread, shutdown.
- [JNI Specification Java SE 21 — Global and Local References](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#global-and-local-references): NewGlobalRef/DeleteGlobalRef, DeleteLocalRef, PushLocalFrame, PopLocalFrame.
- [JNI Specification Java SE 21 — Weak Global References](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#weak-global-references): NewWeakGlobalRef, NewLocalRef, DeleteWeakGlobalRef.
- [JNI Specification Java SE 21 — Exceptions](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html#exceptions): ExceptionCheck, ExceptionOccurred, ExceptionClear, ExceptionDescribe.
- [Android NDK — JNI tips](https://developer.android.com/ndk/guides/jni-tips): experience with holding references and cleanup on attached native workers; Android-specific rules should be distinguished from the Java SE standard.

**Remember:** *whichever thread attaches itself must detach itself when finished*, while each JNI reference and borrowed pointer has its own owner/cleanup. Clean up resources when they are no longer needed, handle pending exceptions deliberately, wait for Java callbacks to complete, and never use JNIEnv* after detaching.