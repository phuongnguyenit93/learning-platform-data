# Passing Application State via the user data Parameter Under the C Contract

## 1. Goal and Problem to Solve

In the **Foreign Function & Memory API (FFM)**, Java can pass a **function pointer** to C so that C calls back into Java code (**upcall**). Many C APIs use a callback signature consisting of business arguments and a **void *user_data** pointer:

~~~c
typedef void (*event_callback)(int32_t value, void *user_data);
int32_t emit_twice(int32_t first, event_callback callback,
                   void *user_data);
~~~

**user_data** is also called *client data*, *context*, *cookie*, or *opaque pointer*. The caller passes a context value when registering/invoking the callback; the C library returns that exact value each time the callback occurs. This allows Java to determine **which request, session, or business object the event belongs to** without letting C understand the Java object model.

After this lesson, you will know how to:

1. Read the C contract regarding **void\***, callback invocation count, pointer retention, threading, and ownership.
2. Map **void\*** to **ValueLayout.ADDRESS**/**MemorySegment** and declare **FunctionDescriptor** for callbacks/C call sites.
3. Create **Linker.upcallStub** pointing to a Java MethodHandle with the right ABI.
4. Pass application state using an **opaque token + Java registry**, without faking Java object addresses.
5. Distinguish how to use a **native struct** as user_data if C actually needs to read data.
6. Manage the lifetime of the **token**, **upcall stub**, **Java State**, and **native library**, especially with asynchronous callbacks.
7. Prevent Java exceptions from escaping through an upcall, avoiding races, dangling pointers, ABA, and resource leaks.
8. Run a complete **Java 22+ and C11** example with deterministic and testable stdout.

**Baseline:** The **java.lang.foreign** package has been finalized since JDK 22 per JEP 454. The examples use **Java 22+**; it is not claimed to run verbatim on Java 17 because FFM had a different API at that stage.

## 2. Diagram of a Java Application Sending State Through C

~~~text
Java State A       Java State B
     |                  |
     v                  v
Token A             Token B
     |                  |
     +--------+---------+
              |
      C API receives callback pointer
        and void *user_data
              |
        C emits event
              |
 C calls callback(value, user_data)
              |
       FFM upcall stub
              |
     Java callback receives address
              |
   Registry maps address -> State
              |
    Updates the right State A or B
~~~

There are **three objects with independent lifecycles**:

| Object | Purpose | Ownership Rule |
| --- | --- | --- |
| **Upcall stub** | Function pointer callable by C, created by **Linker.upcallStub** | The Arena containing the stub must stay alive while C can invoke the callback |
| **user_data** | C pointer that C stores/echoes or reads per contract | The owner of the token/struct must keep the memory region valid and only free it at the right time |
| **Java State** | Session, Counter, Handler, Context on the Java heap | Must have a strong reference until the final callback has finished |

**Do not equate** the function pointer, native token, and Java object: a MemorySegment returned from FFM does not automatically keep all related Java objects alive. A **void\*** pointer also does not automatically grant C the right to free the data.

## 3. The C Contract Matters More Than the Name user_data

C APIs may use the same parameter name but have different behaviors:

| What to Verify | Key Question |
| --- | --- |
| **Synchronous/Asynchronous** | Does the callback run during the downcall, or does C retain the pointer to call later? |
| **Opaque/Readable** | Does C only echo the pointer as-is, or actually read a struct at that address? |
| **Nullability** | Are user_data or callback allowed to be NULL? |
| **Ownership** | Does the Java caller only lend the pointer to C, or transfer freeing responsibility to C? |
| **Lifetime** | Must the pointer live until the function returns, unsubscribe, or end of session? |
| **Thread** | Is the callback invoked on the Java thread making the downcall or a native worker? |
| **Concurrency** | Can C invoke multiple callbacks concurrently or reentrantly? |
| **Unregister** | Does unregister wait for in-flight callbacks to complete? |
| **Error model** | Does the callback return an error code? If the callback fails, what will C do? |
| **ABI** | Are the actual arguments int32_t, long, size_t, pointer, or struct? |

Without this information, **FFM cannot automatically infer the contract of void\*** from a FunctionDescriptor. Successfully creating a MethodHandle does not confirm that C will not retain the pointer.

### Two Typical Contract Forms

**Synchronous, does not retain pointer:**

~~~c
/* Contract: cb and ctx are only borrowed during this call. */
int32_t emit(int32_t value, event_callback cb, void *ctx);
~~~

Java can allocate the token/stub in **Arena.ofConfined()**, call C, and close the arena **after** the downcall completes.

**Asynchronous, retains pointer:**

~~~c
/* Contract: C retains cb/ctx until unregister + drain. */
int register_cb(event_callback cb, void *ctx);
void unregister_cb(void);
void wait_callbacks_finished(void);
~~~

This is an **illustrative header**, not a runnable C implementation. Java must keep the token/stub and State alive until after **unregister + drain**. Do not use a request-local arena and close it immediately when **register_cb** returns.

## 4. ABI of the Callback and void* Pointer

With:

~~~c
typedef void (*event_callback)(int32_t value, void *user_data);
~~~

The path from Java to C is described by:

~~~java
FunctionDescriptor callbackDescriptor =
    FunctionDescriptor.ofVoid(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS
    );
~~~

The Java callback target needs the type:

~~~java
private static void onEvent(int value, MemorySegment userData) {
    // value corresponds to int32_t; userData corresponds to void*.
}
~~~

**ValueLayout.ADDRESS** has carrier **MemorySegment**, not int or Java object. **ValueLayout.JAVA_INT** matches int32_t on common ABIs supported by the example. If the header uses **C long** or **size_t**, you must choose the layout according to the native ABI, not blindly cast to Java long across OSes.

### A Zero-Length Pointer Is Not an Actually Empty Buffer

An address passed by C into an upcall usually appears as a **zero-sized MemorySegment**, carrying the real address and global scope. This is how FFM avoids fabricating a valid byte count:

~~~java
long tokenAddress = userData.address(); // Can be used as an opaque key.
// DO NOT call userData.get(JAVA_INT, 0) without knowing the bounds.
~~~

A zero-length MemorySegment **does not mean C allocated 0 bytes**, it means Java **does not know the length**. If you use **reinterpret(size)** or **AddressLayout.withTargetLayout(...)** to read, you must prove size/alignment/lifetime per the C contract; these APIs are restricted and cannot prevent forged or freed pointers on their own.

### Do Not Pass a Java Object Directly as a Pointer

Do not use **System.identityHashCode(state)** as a pointer: it is only an integer hash, can collide, and is not a valid native address. Do not cast a Java reference to **void\*** and let C dereference it: the Java heap is subject to GC and does not provide a stable pointer under the FFM contract.

The two clear approaches are a **native token with a real address to look up a Java registry**, or a **native struct with a verified ABI/layout**.

## 5. Approach A: Opaque Token and Java Registry

When C **only holds/echoes the pointer without reading its contents**, you can allocate a 1-byte token in an Arena:

~~~java
MemorySegment token = arena.allocate(1);
long key = token.address();
~~~

Then:

1. Create Java-owned State, such as Counter or RequestContext.
2. Put **key → State** into **ConcurrentHashMap<Long, State>**, holding State via a strong reference.
3. Pass the token along with the upcall stub to C.
4. When C invokes the callback, Java receives MemorySegment userData, gets **address()**, and looks it up in the map.
5. Update State; do not let exceptions escape through the callback.
6. Wait for confirmation that C has stopped using the token; **remove** the entry, then close the Arena.

The 1-byte token **does not contain State**; its small size merely provides a valid native pointer. C must not dereference it if the contract says opaque.

### Why Is This Approach Suitable?

Java State can be a complex object containing services, queues, collections, metadata, and business invariants. C does not need to understand or copy those fields; C only returns a native address. The registry resolves from native identity to Java State.

### Important Limitations

- The registry is not a security authentication mechanism: a native library could pass an unregistered address. Check for missing keys.
- If you forget **remove**, the registry keeps State alive indefinitely → Java heap leak.
- If you remove before the final callback finishes, the callback may fail to find State.
- The native allocator may reuse the **same address** for a new token after the old token is freed. A late callback could mistake it for the new State (**ABA**); late callbacks must be blocked by a teardown barrier, possibly adding a generation/session ID if the API supports it.
- ConcurrentHashMap protects map operations, **not automatically** making State, native workers, or Arena teardown safe.

## 6. Approach B: Passing a Native Struct

If C actually **reads the context**, a struct with a concrete layout is more appropriate:

~~~c
#include <stdint.h>

typedef struct AppContext {
    int32_t request_id;
    int32_t multiplier;
} AppContext;
~~~

Java describes the native region (on a matching ABI):

~~~java
MemoryLayout contextLayout = MemoryLayout.structLayout(
    ValueLayout.JAVA_INT.withName("request_id"),
    ValueLayout.JAVA_INT.withName("multiplier")
);

try (Arena arena = Arena.ofConfined()) {
    MemorySegment context = arena.allocate(contextLayout);
    context.set(ValueLayout.JAVA_INT, 0, 101);
    context.set(ValueLayout.JAVA_INT, 4, 3);
    // Pass context as void* while callback/C API uses it in scope.
}
~~~

This is a snippet without a downcall yet. C can point to the struct and read the fields **if** the contract agrees. The Java callback needs to know the exact layout when it wants to read the echoed pointer. **sizeof, alignof, offsetof** must be verified against the actual native binary if the struct is complex, packed, or uses ABI-dependent typedefs.

One way to declare a target layout:

~~~java
AddressLayout contextPointer =
    ValueLayout.ADDRESS.withTargetLayout(contextLayout);

FunctionDescriptor desc = FunctionDescriptor.ofVoid(
    ValueLayout.JAVA_INT,
    contextPointer
);
~~~

This is a Java 22+ snippet assuming AddressLayout is imported and contextLayout is created. **withTargetLayout** is a restricted API: it tells FFM the expected size of the pointee, **not proving** that C actually allocated that region or that the pointer is still alive. Do not use this style when the C contract only says user_data is an opaque cookie not to be dereferenced.

**When to choose which?** Use the **registry** if Java state is complex and C only echoes the pointer. Use a **native struct** if C needs to read/write simple data fields with a verified ABI/lifetime.

## 7. Upcall Stub and Exception Policy

Creating a function pointer from a Java MethodHandle:

~~~java
Linker linker = Linker.nativeLinker();

MethodHandle target = MethodHandles.lookup().findStatic(
    UserDataCallbackDemo.class,
    "onEvent",
    MethodType.methodType(
        void.class, int.class, MemorySegment.class
    )
);

MemorySegment callback = linker.upcallStub(
    target,
    FunctionDescriptor.ofVoid(
        ValueLayout.JAVA_INT,
        ValueLayout.ADDRESS
    ),
    arena
);
~~~

This is a snippet, assuming the class has onEvent and arena is alive. C can call the stub address as an ABI-compliant **event_callback**.

**Important warning:** Per JDK 22 Linker, a Java callback MethodHandle **must not throw an exception across an upcall**; an escaping exception can cause the JVM to terminate abruptly. Therefore, the callback must **catch at the FFM boundary** and record the error in request State, an AtomicReference, or return an error code per the C signature.

~~~java
private static void onEvent(int value, MemorySegment userData) {
    try {
        // Look up context and process safely.
    } catch (Throwable failure) {
        // Report error via separate state/queue, DO NOT rethrow across C ABI.
    }
}
~~~

This is a snippet illustrating the principle; production code must not silently swallow errors and needs an observability channel. If the C callback returns an int status, it can return an error code after catching. If the C callback runs on a latency-sensitive thread, keep processing brief and send the event to a queue with backpressure.

## 8. Complete Example: C11 Invokes a Java Callback Twice

This example enforces a **synchronous contract**: C does not retain the function pointer or user_data after returning. Java can use **Arena.ofConfined()**, because the callback runs immediately during the C call on the thread performing the downcall.

Expected result: C calls Java with values **10 and 11**, both callbacks receive the same token and update the same State.

### Step 1 — Create userdata_callback.c

~~~c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
#  define API __declspec(dllexport)
#else
#  define API __attribute__((visibility("default")))
#endif

typedef void (*event_callback)(
    int32_t value, void *user_data
);

/*
 * CONTRACT:
 * - callback and user_data are non-NULL;
 * - user_data is opaque, not dereferenced/not freed;
 * - only borrows both pointers during this call;
 * - two synchronous callbacks, on the caller thread;
 * - does not retain callback/user_data after returning;
 * - returns 2 if called twice; -1/-2 on invalid input.
 */
API int32_t emit_twice(
    int32_t first,
    event_callback callback,
    void *user_data
) {
    if (callback == NULL || user_data == NULL) {
        return -1;
    }
    if (first == INT32_MAX) {
        return -2;
    }

    callback(first, user_data);
    callback(first + 1, user_data);
    return 2;
}
~~~

The decisive point is not the 2 callbacks, but **C's commitment not to retain the pointers**. If you change the implementation to a native worker calling after return, the Java code below must change its scope/lifecycle to match the session, not just flip a flag.

### Step 2 — Compile the Shared Library

**Linux:**

~~~bash
cc -std=c11 -O2 -fPIC -shared \
  userdata_callback.c -o libuserdatacallback.so
~~~

**macOS:**

~~~bash
clang -std=c11 -O2 -fPIC -dynamiclib \
  userdata_callback.c -o libuserdatacallback.dylib
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /nologo /W4 /LD userdata_callback.c /link /OUT:userdatacallback.dll
~~~

The three commands are **OS-specific alternatives**, do not run all three. The binary must match the JVM's OS/CPU/ABI. Place the library in the working directory used for the Java step.

### Step 3 — Create UserDataCallbackDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Path;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public final class UserDataCallbackDemo {
    private static final ConcurrentHashMap<Long, State> REGISTRY =
            new ConcurrentHashMap<>();

    // Demo runs a single request; production should
    // store failures per session/context.
    private static final AtomicReference<Throwable> CALLBACK_FAILURE =
            new AtomicReference<>();

    private static final class State {
        final AtomicInteger calls = new AtomicInteger();
        final AtomicInteger sum = new AtomicInteger();
        final AtomicInteger last = new AtomicInteger();
    }

    private UserDataCallbackDemo() {
    }

    // C signature: void callback(int32_t, void*).
    private static void onEvent(int value, MemorySegment userData) {
        try {
            State state = REGISTRY.get(userData.address());

            if (state == null) {
                CALLBACK_FAILURE.compareAndSet(
                        null,
                        new IllegalStateException("Unknown user_data")
                );
                return;
            }

            state.calls.incrementAndGet();
            state.sum.addAndGet(value);
            state.last.set(value);
        } catch (Throwable failure) {
            // Do not let Throwable escape across the C upcall boundary.
            CALLBACK_FAILURE.compareAndSet(null, failure);
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        // Library scope must outlive native call duration.
        try (Arena libraryArena = Arena.ofConfined()) {
            Path library = Path.of(
                    System.mapLibraryName("userdatacallback")
            ).toAbsolutePath();

            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(library, libraryArena);

            // C: int32_t emit_twice(int32_t,
            //                       event_callback, void*);
            MethodHandle emit = linker.downcallHandle(
                    symbols.find("emit_twice").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.JAVA_INT,
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS,
                            ValueLayout.ADDRESS
                    )
            );

            MethodHandle target =
                    MethodHandles.lookup().findStatic(
                            UserDataCallbackDemo.class,
                            "onEvent",
                            MethodType.methodType(
                                    void.class,
                                    int.class,
                                    MemorySegment.class
                            )
                    );

            FunctionDescriptor callbackDescriptor =
                    FunctionDescriptor.ofVoid(
                            ValueLayout.JAVA_INT,
                            ValueLayout.ADDRESS
                    );

            // Sync contract: stub/token only need to live until
            // emit_twice returns.
            try (Arena callArena = Arena.ofConfined()) {
                MemorySegment token = callArena.allocate(1);
                long key = token.address();
                State state = new State();

                if (REGISTRY.putIfAbsent(key, state) != null) {
                    throw new IllegalStateException(
                            "Token already registered"
                    );
                }

                try {
                    MemorySegment callback = linker.upcallStub(
                            target, callbackDescriptor, callArena
                    );

                    CALLBACK_FAILURE.set(null);
                    int delivered = (int) emit.invokeExact(
                            10, callback, token
                    );

                    Throwable failure = CALLBACK_FAILURE.get();
                    if (failure != null) {
                        throw new IllegalStateException(
                                "Callback failed", failure
                        );
                    }
                    if (delivered != 2) {
                        throw new IllegalStateException(
                                "C returned: " + delivered
                        );
                    }

                    System.out.println("delivered=" + delivered);
                    System.out.println(
                            "events=" + state.calls.get()
                    );
                    System.out.println(
                            "sum=" + state.sum.get()
                    );
                    System.out.println(
                            "last=" + state.last.get()
                    );
                } finally {
                    // C has returned and promised not to retain pointers.
                    REGISTRY.remove(key, state);
                }
            } // Arena closes: token and upcall stub become invalid.

            System.out.println(
                    "registryEmpty=" + REGISTRY.isEmpty()
            );
        } // Close the library arena last.
    }
}
~~~

### Step 4 — Run Java 22+

~~~bash
javac UserDataCallbackDemo.java
java --enable-native-access=ALL-UNNAMED UserDataCallbackDemo
~~~

Classpath applications need native access permission for **SymbolLookup.libraryLookup**, **Linker.downcallHandle**, and **Linker.upcallStub**. For modularized applications, grant permission to the specific required module.

**Exact stdout if build/load and native call succeed:**

~~~text
delivered=2
events=2
sum=21
last=11
registryEmpty=true
~~~

Explanation: C calls twice with **10 and 11**; the Java callback looks up the token address in REGISTRY, adds **10+11=21**, updates last=11 and count=2. After C returns, the entry is removed, so registryEmpty=true. C never dereferences or frees the token.

**Demo limitations:** The code is a complete Java 22+/C11 sample following the described C contract. The output is the expected result if built and executed successfully; integration testing on the target toolchain/JDK is required before deployment. The static registry and error slot only serve a single request; multi-request production code should have **per-context** error tracking.

## 9. Async Callbacks and Proper Teardown Order

For APIs with **register(callback, user_data)** that invoke callbacks later, the lifetime scope is no longer a short downcall. A session owner must keep:

- **Library lookup** and function pointers still loaded.
- **Upcall stub** valid for the entire duration C holds the callback.
- **user_data token/struct** valid until the final callback.
- **Java State strong reference** in the map until no callback uses it anymore.
- **Stop/unregister and drain/join mechanism** per the C contract.

Safe closing sequence:

~~~text
Session start
  1. Create an owner Arena that lives for the session
  2. Create token, State, registry entry, callback stub
  3. C register succeeds
  4. C may invoke callbacks from a native worker
Session close
  5. Reject new requests / set closing state
  6. C unregister
  7. Wait for C to guarantee no in-flight callbacks remain
  8. Remove token->State registry entry
  9. Close Arena containing token and stub
 10. Unload library when no users remain
~~~

**Unregister does not automatically mean callbacks are drained.** If C may still be running callbacks, there must be an additional wait API/contract. Closing the Arena first leaves the native pointer pointing to a freed function stub, which can crash the JVM. Removing from the registry first causes callbacks to fail to find State. For C APIs lacking a clear shutdown barrier, no simple try-with-resources can guarantee safety on its own.

### Thread Confinement and Synchronization

- **Arena.ofConfined()** is suitable for synchronous callbacks on the thread that created the Arena, as in the example.
- **Arena.ofShared()** is appropriate for multi-threaded lifetimes when needed, but **does not automatically synchronize application data**.
- **ConcurrentHashMap** only protects the mapping, not the lifecycle of all native consumers.
- **AtomicInteger** makes each individual update in the example safe, without creating an atomic snapshot across multiple fields.
- If native callbacks run concurrently/reentrantly, session state and closing mechanisms need synchronization/active callback counters.
- Avoid holding long locks across downcalls that may upcall simultaneously; there is a risk of reentrancy deadlock.

**FFM upcalls are not synonymous with JNI JNIEnv callbacks.** Do not pass a Java thread's JNIEnv to a native worker; if JNI is also used, JNI thread rules still apply separately.

## 10. Pointer Lifetime, ABA, and Ownership

### 10.1. ABA on Address Reuse

Suppose an old token at address P is freed. The native allocator may reallocate the exact same address P for a new session; a late callback from the old session will look up the registry and get the new State. This is the **ABA problem**.

The primary prevention is ensuring no late callbacks arrive **before freeing the token**. When the API allows, use a generation/unique handle to reduce the risk of identity confusion; however, do not use generation to justify dereferencing a freed pointer.

### 10.2. Borrowed or Transferred Ownership?

If the C API only borrows user_data, a **Java Arena** can own the token and free it on close. If C receives **ownership transfer**, there must be a new owner/deallocator and Java must ensure it does not free the same allocation. Do not call libc free on Arena-managed memory just because it was passed as void*.

### 10.3. NULL Pointer and Invalid Context

Do not assume NULL means "default state"; an API may allow NULL as no context, or forbid it completely. Read the contract, check statuses, and reject callbacks with non-existent keys. A token from genuinely allocated memory **is not a security token**: a malicious or buggy native library can still pass a different address.

### 10.4. When Not to Use a 1-Byte Token?

If C **dereferences user_data** as a struct, a 1-byte token is not enough. You must allocate a native struct with the right size/alignment, data initialized per the ABI, and a lifetime covering all C accesses. Do not arbitrarily reinterpret a pointer into a large struct and assume FFM allocated enough memory.

## 11. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Casting Java object/hash to void* | Invalid/unstable address | Native token + registry or C struct |
| C callback receives zero-length pointer then calls get() | Out-of-bounds | Use opaque address() or a proven layout |
| Wrong FunctionDescriptor | ABI mismatch/crash | Cross-check C typedef and platform |
| Java callback throws across upcall | JVM may terminate | Catch and record error/return code |
| Closing Arena after async register | Dangling stub/user_data | Session lifetime + unregister/drain |
| Forgetting to remove mapping | Java heap leak | Remove when C no longer has callback rights |
| Removing mapping too early | Missing state/race | Wait for in-flight callbacks to finish |
| Using address forever as identity | ABA | Quiescence + generation when appropriate |
| C frees token allocated by Java Arena | Invalid/double-free | Single owner, matching allocator |
| Treating ConcurrentHashMap as full synchronization | State/teardown race | Lock/atomic/in-flight tracking |
| C retains pointer then Java reuses prefix buffer | Data overwritten | Separate buffer or await completion |
| Unloading library while callbacks are alive | Calling invalid code | Longer library lifetime |
| Callback runs long, blocks, or reenters improperly | Deadlock/latency | Short callback, clear queue contract |
| C reads native struct but Java passes 1B token | Invalid memory access | Allocate struct with right ABI and lifetime |

## 12. Pre-Production Checklist

- [ ] Have the exact version of the C header and accurate callback prototype.
- [ ] Determine whether C **echoes** or **dereferences** user_data.
- [ ] Have contracts for NULL, ownership, byte bounds, and deallocator.
- [ ] Upcall MethodHandle matches FunctionDescriptor, does not throw across ABI.
- [ ] Do not use Java heap hashes/object addresses as C pointers.
- [ ] Registry keeps State alive long enough and has a removal path.
- [ ] Stub Arena and token Arena live until after the final native callback.
- [ ] For async, unregister/drain guarantees no in-flight callbacks remain.
- [ ] Do not reuse a token address while old callbacks may still arrive.
- [ ] Thread affinity, concurrency, and reentrancy have real tests.
- [ ] Library lookup outlives callbacks and cleanup.
- [ ] Have tests for multiple sessions, missing token, callback error, registration failure, close race, and shutdown.
- [ ] For native structs, have sizeof/alignment/offsetof tests per OS/ABI.
- [ ] Use native diagnostics if an invalid callback pointer causes a crash.

## 13. Self-Check Questions

**1. Is void *user_data a Java object reference?**

**Answer:** No. It is a C pointer. Java State must be held via an explicit registry/handle or the necessary data must be transferred into a native struct.

**2. Why is a 1-byte native token enough for the example?**

**Answer:** C only echoes the address and reads no bytes. A one-byte allocation provides a valid pointer within the synchronous lifetime.

**3. Does a callback receiving a MemorySegment with byteSize=0 mean C allocated 0 bytes?**

**Answer:** No; Java does not know the bounds yet. You can use address as an opaque key, and must not dereference it arbitrarily.

**4. When can callArena be closed immediately after a downcall?**

**Answer:** Only when the C contract guarantees it does not retain the callback/token and all callbacks have completed before the downcall returns.

**5. Why not let a callback throw a RuntimeException?**

**Answer:** The C ABI does not propagate Java Throwables normally; FFM warns that an exception escaping an upcall can cause the JVM to terminate abruptly.

**6. Can ConcurrentHashMap prevent a late callback after arena.close?**

**Answer:** No. You must unregister/drain per the contract before removing from the map and closing.

**7. What does Java need to do when C actually reads AppContext*?**

**Answer:** Allocate a native struct with the right layout, size/alignment, initialize fields, protect lifetime and synchronization; do not pass a 1-byte token.

**8. Why not use System.identityHashCode as a user_data pointer?**

**Answer:** A hash is not a native address, can collide, and does not protect the Java object from GC.

**9. With two callback values 10 and 11, what is the output sum=?**

**Answer:** **21**, because the Java callback finds the same State from user_data and sums both events.

**10. Which should be closed first: the Arena containing the callback or the native library?**

**Answer:** After unregister/drain, close the Arena containing the stub/token; only unload the library when no callbacks and native calls need it anymore.

## Official References

- [JEP 454 — Foreign Function & Memory API finalized in JDK 22](https://openjdk.org/jeps/454).
- [JDK 22 — Linker: downcall/upcall, function pointers, callback exception](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).
- [JDK 22 — MemorySegment: zero-length address, scope, reinterpret](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [JDK 22 — Arena: confined/shared and cleanup lifetime](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [JDK 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html).
- [JDK 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).

**Conclusion:** **user_data is a C contract about context and lifetime**, not a Java object or a memory region automatically managed by FFM. For C APIs that only echo the pointer, use a native token + Java registry to select the right State; when C needs data, use a native struct with a verified layout. Always keep the stub/token/State alive long enough, handle callback exceptions, and wait for the final callback to complete **before** closing the Arena.
