# Attaching cleanup actions to the right scope, avoiding double-free

## Lesson Objectives

When Java interacts with C/C++ using the **Foreign Function & Memory API (FFM)**, data can be allocated by **Java's Arena** or by **a native library** through malloc, create, open, retain, or custom resource initialization functions. The hard part is not just obtaining the address: the application must know **who owns the resource, when it becomes invalid, and which exact operation must free it**.

A particularly dangerous bug is **double-free**: calling the deallocation function twice for the same allocation without an intervening new allocation. This bug can corrupt C's heap management structures, corrupt memory, hang the process, or cause a JVM crash. In addition, attaching cleanup to the wrong scope can create **use-after-free** or **memory leak** even when double-free does not occur.

After this lesson, you will:

1. Distinguish between **Java-owned**, **C-owned/borrowed**, **transferred ownership**, and **reference-counted** resources.
2. Understand **Arena.ofConfined, Arena.ofShared, Arena.ofAuto, Arena.global** and when to close a scope explicitly.
3. Know how to use **MemorySegment.reinterpret(long, Arena, Consumer<MemorySegment>)** to attach **one cleanup action** to the appropriate scope for a pointer allocated by C and **truly owned by Java**.
4. Not confuse **reinterpret**, **asSlice**, **MemorySegment**, and **Arena.close** with C's own free operation.
5. Keep **SymbolLookup/library and the deallocator** alive longer than the resources that need to be freed.
6. Analyze failure paths, single release, thread affinity, asynchronous callbacks, cleanup errors, and shutdown order.
7. Run a **complete Java 22+ and C11** example, verifying that C's release function is called exactly **once** when the owning arena closes.
8. Apply a review and test checklist to prevent double-free, leaks, and use-after-free in native interop projects.

**Baseline:** This lesson uses the stable **java.lang.foreign** API from **JDK 22** per JEP 454. These syntaxes **do not run as-is on JDK 17** because FFM had different APIs/incubator/preview features at that time.

---

## 1. Distinguishing a resource from views and addresses

Suppose C allocates a 4-byte region:

~~~c
int32_t *p = malloc(sizeof(int32_t));
~~~

The address **p** represents a single allocation managed by the C runtime. Java can receive that address as a **MemorySegment**; from there, it can create additional **slice** or **reinterpret** views. However, having multiple MemorySegment objects **does not mean** native code allocated multiple allocations.

~~~text
        C malloc: 1 real allocation
                   |
                address P
                   |
       +-----------+------------+
       |           |            |
   raw pointer   managed      asSlice
   view          view         view
       |           |            |
       +-----------+------------+
             SAME backing bytes

    Only ONE owner may call the right deallocator
    ONCE when the allocation's lifecycle ends.
~~~

Concepts that must be kept separate:

| Concept | Nature | Does it automatically free the C resource? |
| --- | --- | --- |
| **Native address** | Address number returned from C | No |
| **MemorySegment** | View with address, byte bounds, scope | Does not own a C allocation by default |
| **MemorySegment.asSlice** | Sub-view sharing backing memory and scope with the original view | No |
| **MemorySegment.reinterpret** | Creates an alias with re-declared size/scope; restricted API | **No**, unless a cleanup that actually performs release is attached |
| **Arena** | Scope managing memory regions/segments attached to the arena | Closing the arena frees regions allocated by the arena; custom cleanup can manage other C resources |
| **C destroy/free/release function** | Native operation that frees or decrements reference count per contract | Yes, if right function, right allocator, right ownership |

**Ownership rule:** An allocation may have many **borrowers/views**, but there must be one **single party responsible for freeing** according to the contract. If two cleanup actions both call free on one address, or if you both call it manually and register an automatic cleanup for the same allocation, that is a double-free risk.

## 2. What FFM knows and what it cannot know on its own

FFM knows that a MemorySegment has a byte range and a scope. When Java performs get/set, FFM can check bounds, thread access, and whether the scope is still alive. However, FFM **cannot prove on its own** whether a native pointer:

- Was allocated by whom: Java Arena, C malloc, C++ library new, a custom pool, or the stack?
- Is **owned** (caller must free) or **borrowed** (must not be freed)?
- Can be NULL? Does NULL mean an error or an empty value?
- Has how many bytes in length, according to which API?
- Needs **free**, **destroy**, **close**, **release**, or a specialized deallocator?
- Is still retained by C after return or callback?
- Needs to be freed on the same thread, in the same event loop, or before unloading the library?
- Uses reference counting or a shared ownership mechanism?
- Can be freed while a native worker is still running?

C documentation/headers and testing of the **actual binary** are what provide this semantic information. **FunctionDescriptor** only helps the linker call the function according to the ABI described by the programmer; it does not turn a C pointer into a smart pointer with automatic ownership.

## 3. Four ownership patterns to read from the C contract

### 3.1. Java-owned: allocated by Arena

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment buffer = arena.allocate(256);
    buffer.set(ValueLayout.JAVA_INT, 0, 42);
} // Arena frees the backing memory of buffer.
~~~

This is a Java 22+ snippet inside a method with `import java.lang.foreign`. The native region allocated by Arena already has an owner: **Arena**. Do not attach an extra callback calling libc's **free(buffer)** to "make sure it cleans up": doing so can cause **double-free** or break the allocator contract.

**Summary:** Arena.allocate → Arena is the owner → only close Arena properly once when there are no more consumers.

### 3.2. Borrowed: C remains the owner

A C header might declare:

~~~c
/* p is only a borrowed pointer, do not free in caller. */
const unsigned char *device_get_view(
    struct Device *device,
    size_t *length
);
~~~

If the library retains ownership, Java may only read within the specified validity window (for example, until the next call or until Device is closed). **Do not register a deallocator** for a borrowed pointer. Reinterpreting onto a Java scope only restricts access paths through the view; it **does not extend** the actual lifetime of the memory managed by C.

### 3.3. Ownership transferred: Java must call destroy

A C header might declare:

~~~c
/* Returns an allocation owned by the caller; destroy with blob_destroy. */
struct Blob *blob_create(void);
void blob_destroy(struct Blob *blob);
~~~

When the creation function succeeds and the contract says the caller owns it, Java needs to choose **one single mechanism**:

- **Automatic by scope:** register a cleanup action that calls `blob_destroy` when the owning Arena closes.
- **Manual with an AutoCloseable owner:** a Java wrapper calls `blob_destroy` on close, with state so it does not release repeatedly. When choosing this approach, **do not simultaneously** attach a second `blob_destroy` cleanup to the Arena for the same pointer.

Both mechanisms can be valid, but **they must not be combined so that each considers itself the owner of the same allocation**.

### 3.4. Reference-counted or shared native object

An API might provide:

~~~c
void object_retain(struct Object *obj);
void object_release(struct Object *obj);
~~~

This contract is different from malloc/free. Each successful **retain** creates an ownership share that needs a corresponding **release**; two wrappers may only release independently if **each wrapper truly owns a retained reference**, not because they happen to see the same address. If only one ref was granted, creating two wrappers that both release on their own is wrong.

**Must read the specific contract:** do not infer from the word release that it is equivalent to free; in some APIs release only decrements a counter and the object is destroyed when the refcount reaches 0.

### Ownership Matrix

| Data source | Who frees? | Correct cleanup | Common mistake |
| --- | --- | --- | --- |
| **Arena.allocate** | Java Arena | Close Arena once | Calling libc free on a segment owned by Arena |
| C returns **borrowed pointer** | C-side owner | Do not free from Java | Registering a custom free for a borrowed address |
| C **malloc/create** transfers ownership to caller | New Java owner | Right C deallocator once | Both manual free and arena cleanup |
| **Reference-counted** C object | Owner of each ref | release matching actual retain/ownership | Multiple aliases releasing the same ref |
| Pointer to **stack/native callback** region | Owning C thread/callback | Do not free; do not use after deadline | Keeping Java view and using after callback |
| Pointer to **mapped file** | Mapping owner | Unmap/close per mapping contract | Calling free on the mapping address |

## 4. Choosing the right scope: when does cleanup run?

In Java 22, **Arena** determines the **temporal bounds** of segments associated with it:

| Arena | Lifecycle | Suitable for native cleanup |
| --- | --- | --- |
| **Arena.ofConfined()** | Explicitly closed on the thread that created the arena | Usually a good default for a single native request/transaction on one thread |
| **Arena.ofShared()** | Explicitly closed; usable from multiple threads | Resources shared by multiple workers, when stopping has been coordinated before close |
| **Arena.ofAuto()** | Reclaimed by reachability/GC, non-deterministic timing | Only when the resource allows non-deterministic cleanup timing and has no strict thread-affinity |
| **Arena.global()** | Lives as long as the JVM, not explicitly closed | Not suitable if deterministic release timing is needed |

### Confined Arena

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(32);
    // Use in the thread owning the arena.
}
// arena.close() runs when exiting try-with-resources.
~~~

When close completes normally, the scope becomes invalid. Java access through segments associated with that scope will be blocked. Only the owner thread may close a confined arena.

### Shared Arena

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment block = arena.allocate(32);
    // Multiple Java workers can use the same scope,
    // but must wait for all workers to finish before close.
}
~~~

A shared arena **does not automatically make data thread-safe** and **does not automatically interrupt a native worker** holding a raw pointer. There must be a stop/unregister/join mechanism or acknowledgment that all consumers have finished. If a downcall is still accessing a segment of the arena, close may also fail due to concurrent access constraints.

### Auto Arena

Cleanup associated with an auto arena may be executed when the runtime determines the region is no longer reachable, **not at a time actively chosen by code**. Do not rely on `Arena.ofAuto()` to close device connections on time, free scarce sockets, or send an important protocol message immediately when the user clicks close.

If the cleanup action holds a strong reference to the arena or to something that keeps the arena reachable, the automatic collector may **never become eligible to trigger**. Therefore, when cleanup has important side effects, prefer a scope that closes explicitly.

### Global Arena

`Arena.global` cannot be closed explicitly; tying a resource that requires early release to the entire JVM lifetime is usually a **memory/resource leak at the application lifecycle level**. Global scope is not an ownership protection solution.

## 5. The right scope is the scope of actual ownership

Just because "two operations are in the same Java method" does not mean cleanup should be attached to the same arena. Choose the scope based on **when the last consumer finishes**:

~~~text
Java request starts
    |
    +-- create native resource (Java becomes owner)
    |
    +-- pass to native library / worker
    |                     |
    |                 still in use?
    |                     |
    +-- Java method returns (resource not necessarily free yet)
                          |
                    worker finishes
                          |
                unregister / drain / join
                          |
                    owner.close()
                          |
              right native deallocator ONCE
~~~

If C retains the pointer after a downcall, **closing a request-local Arena right when the Java method returns is too early**. Conversely, attaching a small request to `Arena.global` prevents the resource from being freed on time.

A quick checklist for choosing a scope: Who requests the resource? Who is allowed to read/write? Is there a background thread/callback? Is there an ownership handoff? Is there a clear point confirming all consumers have finished? If not, do not close the resource.

## 6. Attaching a cleanup action with MemorySegment.reinterpret

FFM in JDK 22 has a restricted overload:

~~~java
MemorySegment managed =
    rawPointer.reinterpret(byteSize, ownerArena, cleanupAction);
~~~

Components:

- **rawPointer**: MemorySegment representing the native address you want to manage.
- **byteSize**: number of bytes actually valid according to the native contract.
- **ownerArena**: arena whose lifetime reflects **the duration Java owns the resource**.
- **cleanupAction**: **Consumer<MemorySegment>** executed when the arena's scope becomes invalid, for example during closing of `Arena.ofConfined`/`ofShared`.

**Especially important:** **reinterpret by itself does not allocate more memory and does not free memory**. Freeing happens **only if the cleanup action actually calls the right native deallocator**. If cleanup is null, the alias only gets its scope/size re-attached, with no mechanism to return the C allocation to C's allocator.

### C-returned pointers usually have byteSize equal to 0

Suppose a C function returns **int32_t\***. FFM represents the returned pointer as a **zero-length MemorySegment**, usually with an always-alive scope. You cannot call `get(JAVA_INT, 0)` directly on a 0-byte view.

~~~java
MemorySegment raw = (MemorySegment) create.invokeExact(42);
// raw.byteSize() is usually 0 for pointer return.
~~~

This is a snippet, assuming MethodHandle **create** has signature **(int) -> MemorySegment**. To read safely, only after verifying that C actually allocated at least **sizeof(int32_t)** bytes should you attach the size and scope:

~~~java
MemorySegment managed = raw.reinterpret(
    ValueLayout.JAVA_INT.byteSize(),
    ownerArena,
    cleanupAction
);
~~~

**Warning:** reinterpret is a restricted method because you can declare the wrong size/lifetime. FFM cannot prove the pointer is still alive, has enough bytes, or has proper alignment. An already-freed pointer can still be reinterpreted and later cause a crash when dereferenced.

### The cleanup action receives a different segment from managed

According to the JDK 22 API, the cleanup Consumer is passed a **new** segment with the same native address, with global scope and the corresponding byte count. It is provided so that the **address** can be passed to the free function right when the original scope becomes invalid.

~~~java
java.util.function.Consumer<MemorySegment> cleanup = ptr -> {
    try {
        destroyHandle.invokeExact(ptr);
    } catch (Throwable failure) {
        throw new IllegalStateException(
                "Native destroy failed", failure
        );
    }
};
~~~

This is a snippet, assuming **destroyHandle** has MethodType **(MemorySegment)void**. Use the cleanup pointer **only to complete deallocation**, do not store it in a global/list or send it outside. Because the cleanup pointer has global scope, letting it escape can lead to dereference-after-free that FFM cannot block.

Do not call **managed.get(...)** inside cleanup thinking managed is still alive; cleanup time is when the scope is becoming invalid. Cleanup should be short, purpose-specific, and avoid callbacks that trigger unnecessary native operations.

## 7. Avoiding double-free: register exactly once per ownership

### 7.1. One owner, multiple non-owning aliases

~~~text
         Native allocation P
                  |
         owner Arena R
                  |
     reinterpret(P, R, destroy)    <-- EXACTLY ONE registration
                  |
              managed
            /    |     \
        asSlice viewA viewB
                  |
     R.close() -> destroy(P) ONCE
~~~

Aliases, views, or slices **do not receive separate cleanups**. They share the backing memory and are invalidated when the owner Arena closes.

### 7.2. Wrong: two cleanup registrations freeing the same pointer

~~~java
// INTENTIONALLY WRONG: two independent cleanups pointing to the same allocation.
MemorySegment a = raw.reinterpret(size, arenaA, freeAction);
MemorySegment b = raw.reinterpret(size, arenaB, freeAction);
// arenaA.close() -> free(P)
// arenaB.close() -> free(P) the second time: double-free!
~~~

This is only **warning code that must not be run**. Even though the two Java views have separate scopes, the C heap still has only **one allocation**. FFM has no mechanism to automatically detect "this pointer was already registered in another arena".

### 7.3. Wrong: both manual free and attaching arena cleanup

~~~java
// INTENTIONALLY WRONG: resource has both auto cleanup and manual free.
MemorySegment managed = raw.reinterpret(size, arena, freeAction);
freeHandle.invokeExact(raw); // Free immediately.
// ...
arena.close();               // Callback will free again.
~~~

This is **Java/FFM pseudocode of an anti-pattern**, not a standalone program. Do not run a free once to "check" with a debugger on real data: double-free can corrupt the heap before you even see a stack trace.

### 7.4. Wrong: freeing an alias instead of the owner

A slice does not own its own allocation. Calling free with the address of a slice in the **middle** of an allocation can also cause an invalid free. Even if a slice starts at the exact base address, it still **has no right to free** if another owner already registered cleanup.

**Rule:** Free through the **owner record** that knows the exact allocator/deallocator; do not free merely because you have a `MemorySegment.address()`.

### 7.5. Arena.close is not idempotent

According to JDK 22 documentation, **Arena.close() is not idempotent**: attempting to close an already-closed Arena throws **IllegalStateException**. This is a lifecycle error signal. Calling close a second time should not be understood as a valid way to "ensure extra cleanup".

However, distinguish carefully:

- **Calling close twice on the same Arena**: the normal API throws an exception the second time. That is **different** from having certainly called C free twice.
- **Registering two cleanup callbacks for the same C pointer, or manual free plus callback**: can actually lead to **double-free**.
- **Two owners with different addresses**: they can free separately if each owner owns its own allocation per the C contract.

Close throwing an exception does not mean a cleanup action in a complex system completely succeeded; always have a clear error/monitoring path for the native deallocator.

## 8. Complete Java 22+ with C11 example: cleanup exactly once

The example creates an **int32_t** in C with malloc and hands ownership to Java. Java attaches a cleanup action using **reinterpret(size, ownerArena, cleanup)**. When the owner Arena closes, cleanup calls **the right release function of the C library**. The library has a counter to prove there was **one release**, after which Java verifies that the managed view has been invalidated.

The program creates **two Arenas** with different responsibilities:

- **libraryArena**: keeps the shared library and downcall MethodHandles alive so cleanup can still call the release function.
- **ownerArena**: manages **one C allocation transferred to Java**; closed before libraryArena.

No manual free is called, and no separate cleanup is created for the slice.

### Step 1 — Create scope_cleanup.c

~~~c
#include <stdint.h>
#include <stdlib.h>

#if defined(_WIN32)
#  define API __declspec(dllexport)
#else
#  define API __attribute__((visibility("default")))
#endif

/*
 * Demo runs single-threaded; counter is not designed to be thread-safe.
 * One successful make -> caller must release exactly once.
 */
static int32_t release_counter = 0;

/* Returns NULL when malloc fails. */
API int32_t *demo_make_int(int32_t value) {
    int32_t *p = (int32_t *)malloc(sizeof(*p));
    if (p != NULL) {
        *p = value;
    }
    return p;
}

/*
 * Contract: p is an unreleased pointer allocated by
 * demo_make_int with ownership belonging to the caller.
 */
API void demo_release_int(int32_t *p) {
    if (p != NULL) {
        free(p);
        release_counter++;
    }
}

API int32_t demo_release_count(void) {
    return release_counter;
}
~~~

**C contract that cannot be ignored:** `demo_release_int` may only be called on a pointer successfully returned by `demo_make_int`, not yet released, and whose ownership has not been transferred further. If an unknown address is passed or it is called twice, the precondition no longer holds; this C function itself **is not a double-free detector**. The `release_counter` metric proves the demo's success path; it does not mean calling again after free will be safe.

This is a simple C11 example on common OS/ABIs that have **int32_t**. The static counter is read/written sequentially from the same Java thread; if used across multiple threads in production, appropriate synchronization/atomics must be added.

### Step 2 — Compile the native library

**Linux (GCC or Clang):**

~~~bash
cc -std=c11 -O2 -fPIC -shared \
  scope_cleanup.c -o libscopecleanup.so
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -O2 -fPIC -dynamiclib \
  scope_cleanup.c -o libscopecleanup.dylib
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /nologo /W4 /LD scope_cleanup.c /link /OUT:scopecleanup.dll
~~~

Run only **the one command matching your operating system**. The output uses the library name corresponding to **System.mapLibraryName("scopecleanup")**. Compile for the same architecture/ABI as the JDK; ensure the C runtime and binary dependencies can be loaded.

### Step 3 — Create ScopeCleanupDemo.java

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.MethodHandle;
import java.nio.file.Path;

public final class ScopeCleanupDemo {
    private ScopeCleanupDemo() {
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        /*
         * libraryArena has a LONGER lifetime than the resource owner.
         * Owner's cleanup must still be able to call demo_release_int.
         */
        try (Arena libraryArena = Arena.ofConfined()) {
            Path path = Path.of(
                    System.mapLibraryName("scopecleanup")
            ).toAbsolutePath();

            SymbolLookup symbols =
                    SymbolLookup.libraryLookup(path, libraryArena);

            // C: int32_t *demo_make_int(int32_t value)
            MethodHandle make = linker.downcallHandle(
                    symbols.find("demo_make_int").orElseThrow(),
                    FunctionDescriptor.of(
                            ValueLayout.ADDRESS,
                            ValueLayout.JAVA_INT
                    )
            );

            // C: void demo_release_int(int32_t *p)
            MethodHandle release = linker.downcallHandle(
                    symbols.find("demo_release_int").orElseThrow(),
                    FunctionDescriptor.ofVoid(ValueLayout.ADDRESS)
            );

            // C: int32_t demo_release_count(void)
            MethodHandle releaseCount = linker.downcallHandle(
                    symbols.find("demo_release_count").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT)
            );

            System.out.println(
                    "releasedBefore=" + (int) releaseCount.invokeExact()
            );

            MemorySegment managed;

            /*
             * Owner scope: one C allocation, one cleanup.
             * Java will close owner BEFORE libraryArena.
             */
            try (Arena ownerArena = Arena.ofConfined()) {
                MemorySegment raw =
                        (MemorySegment) make.invokeExact(42);

                if (raw.address() == 0L) {
                    throw new OutOfMemoryError(
                            "demo_make_int returned NULL"
                    );
                }

                /*
                 * C allocated at least sizeof(int32_t) bytes.
                 * reinterpret does NOT own automatically; Consumer
                 * is what calls the deallocator when owner closes.
                 */
                managed = raw.reinterpret(
                        ValueLayout.JAVA_INT.byteSize(),
                        ownerArena,
                        cleanupPointer -> {
                            try {
                                release.invokeExact(cleanupPointer);
                            } catch (Throwable failure) {
                                throw new IllegalStateException(
                                        "Native release failed", failure
                                );
                            }
                        }
                );

                // Slice is only a view, do NOT register a new cleanup.
                MemorySegment alias = managed.asSlice(
                        0, ValueLayout.JAVA_INT.byteSize()
                );
                System.out.println(
                        "value=" + alias.get(ValueLayout.JAVA_INT, 0)
                );

                /*
                 * Do not call release.invokeExact(raw) here.
                 * The right to release already resides in ownerArena.
                 */
            } // ownerArena.close() -> demo_release_int exactly once.

            System.out.println(
                    "releasedAfter=" + (int) releaseCount.invokeExact()
            );

            try {
                managed.get(ValueLayout.JAVA_INT, 0);
                System.out.println("accessAfterClose=unexpected");
            } catch (IllegalStateException expected) {
                System.out.println("accessAfterClose=blocked");
            }
        } // Only here is libraryArena closed.
    }
}
~~~

### Step 4 — Compile and run

Place the Java file and the built native library **in the current working directory**. Use **JDK 22 or newer**:

~~~bash
javac ScopeCleanupDemo.java
java --enable-native-access=ALL-UNNAMED ScopeCleanupDemo
~~~

**Exact stdout when build/library load and native calls succeed:**

~~~text
releasedBefore=0
value=42
releasedAfter=1
accessAfterClose=blocked
~~~

Meaning of each line:

- **releasedBefore=0:** C release has not been called yet.
- **value=42:** the `int32_t` data was allocated by C and read by Java through the managed alias after attaching the right size/scope.
- **releasedAfter=1:** `ownerArena` just closed; custom cleanup called **demo_release_int** once.
- **accessAfterClose=blocked:** the managed segment's `ownerArena` scope has become invalid; FFM rejects Java dereference after close.

**Result scope:** The output is derived from the code and FFM/C contracts in a successful build environment; no actual run is claimed here. If the library is missing or the JDK/native access is unsuitable, the program may fail before printing all lines.

### Step 5 — What the example did right

1. **C provides the matching deallocator:** the pointer from `demo_make_int` is freed by **demo_release_int** from the same library.
2. **Ownership is clear:** Java receives the right to free exactly one allocation after create succeeds.
3. **Appropriate resource scope:** confined `ownerArena` lives only for the code block needing the pointer.
4. **Only one cleanup registration:** one `reinterpret` call with one Consumer. The slice alias does not register release.
5. **Library scope lives longer:** `libraryArena` closes **after** `ownerArena`. Cleanup does not call an already-unloaded function pointer.
6. **No manual free:** the code has no second free path for the raw pointer.
7. **Do not read raw after close:** raw may carry a global scope, but it still points to a freed allocation. The managed alias is the interface used by the code.
8. **Java access is blocked after close:** that is temporal safety of the view bound to the owner scope; it is not proof that C cannot violate memory safety.
9. **No background worker:** the demo does not need a shared arena or complex synchronization. Production must add them if there are concurrent consumers.

### Intentional limitations of the demo

The code is kept short to focus on **single-time cleanup**. Production may need to handle errors when creating a wrapper before registration completes, guard against API calls while the resource is closing, track native status on destroy, and adapt ABIs for multiple platforms. A deallocator returning **void** can also fail silently depending on the C library; a Java-side callback exception does not mean C memory was definitely freed.

If **reinterpret** fails before the ownership transfer is established, the newly created C pointer risks **leaking**, because no owner cleanup has been attached yet. Production systems should design a helper that manages atomic ownership transfer at the application level, with a release branch when setup fails, and test error paths; avoid registering early and then accidentally freeing again in a catch branch.

## 9. Failure paths: when must who clean up?

Creating a native resource does not always succeed:

~~~text
C create() ---> NULL -----------------> No successful allocation
        |
        +--> pointer P
                 |
          setup wrapper / metadata
                 |
        +--------+-----------+
        |                    |
   setup succeeds        setup fails
        |                    |
  owner receives P     creator/caller still
  (cleanup registered) must release P if owning
        |                    |
  owner.close()       call deallocator exactly once
        |
  release P exactly once
~~~

Three moments must be distinguished:

- **Before receiving ownership:** If the API only lends a pointer, Java must never free on error.
- **Received ownership but not yet handed over to wrapper:** If the Java initialization step fails, there must be a cleanup branch for the unregistered pointer.
- **After wrapper/arena ownership succeeds:** All Java error branches go through **owner.close()**; **do not add manual free** in catch/finally.

### An owner record with clear state

A useful state machine:

~~~text
    NOT_ALLOCATED
          |
      create OK
          v
       OWNED_RAW
          |
     bind to scope
          v
     OWNED_SCOPED
          |
    close / release
          v
        CLOSED
~~~

Transitions must be clearly designed. Do not allow two independent paths to both transition from `OWNED_SCOPED` to free. If there is concurrent close, manage state with a synchronization/atomic mechanism at the **ownership layer**, do not rely solely on an unsynchronized boolean field.

### Why just adding an AtomicBoolean is not enough

A Java wrapper can use **AtomicBoolean.compareAndSet(false, true)** to prevent two threads from calling the deallocator through the wrapper at the same time. However, it **does not** know whether the C library or another cleanup action has already freed the pointer. Also, if native destroy has complex failure behavior, marking CLOSED before calling destroy can leave a leak, while marking after destroy can create a risk of wrong retry. You must determine the **deallocator's failure model**, conditions under which retry is allowed, and actual ownership from the contract.

If you choose an AutoCloseable wrapper with idempotent close by application design, **do not simultaneously register an arena cleanup with the same deallocator**. Only one final ownership mechanism.

## 10. Do not confuse closing twice with double-free

A common Java mistake:

~~~java
// INTENTIONALLY WRONG: try-with-resources already closes automatically.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(32);
    arena.close();
} // Java tries to close the arena one more time.
~~~

This is an **illustrative anti-pattern** and should not be run as a real workflow. **Arena.close** is not idempotent in JDK 22; the second close may throw `IllegalStateException`. But that is **not** proof that C free executed twice.

Conversely, if there are **two cleanup registrations** on two different arenas for the same C pointer, each arena can close validly, and C is actually asked to free the same allocation **twice**. That is the dangerous double-free.

### Choose one of two clear strategies

**Strategy A — Scope owns resource:**

~~~text
create P -> reinterpret(P, ownerArena, destroy)
         -> process P
         -> ownerArena.close() -> destroy(P)
~~~

**Strategy B — Manual wrapper owns resource:**

~~~text
create P -> NativeHandle(P)
         -> process P
         -> NativeHandle.close() -> destroy(P)
~~~

Do not build a system where **NativeHandle.close** calls `destroy(P)` and then **Arena.close** also runs custom `destroy(P)`, unless they are **distinct reference counts that were validly retained**. "Having multiple Java objects pointing to the same P" does not create additional ownership shares on its own.

## 11. Library lifetime and cleanup order

A mistake that is not directly double-free but can cause a crash:

~~~text
1. libraryLookup("libnative.so", libraryArena)
2. obtain destroy MethodHandle from library
3. create P, register custom cleanup in resourceArena
4. CLOSE libraryArena first
5. resourceArena.close() -> calls destroy in an already-unloaded library!
~~~

**SymbolLookup.libraryLookup(path, arena)** binds the lifetime of the library lookup to the passed arena. When the corresponding scope becomes invalid, the library may be unloaded per the API contract. Therefore, **you must keep the library/symbols/deallocator alive longer than the resource owner**.

Correct nested try pattern:

~~~java
try (Arena libraryArena = Arena.ofConfined()) {
    // Load library, look up create/destroy functions.
    try (Arena resourceArena = Arena.ofConfined()) {
        // Create C resource, register cleanup in resourceArena.
    } // Calls destroy while the library is still loaded.
} // Close library arena last.
~~~

This snippet is a **skeleton**, missing the Java parts that create handles and resources; the complete example in section 8 demonstrates the exact order.

If the application has multiple native resources, a shared `libraryArena` can live until module shutdown, while each resource or batch has its own `ownerArena`. However, if the same arena attaches cleanups for multiple resources and they have dependencies on one another, **do not assume cleanup callbacks run in registration order**, unless the API documentation specifically guarantees it. To control order (for example, destroying child before parent), design explicit **nested scopes/owner graphs**.

## 12. Parent–child ownership and resource graph

A C library might have:

~~~c
Database *db_open(void);
Statement *db_prepare(Database *db, const char *sql);
void statement_destroy(Statement *s);
void db_close(Database *db);
~~~

Suppose the contract requires **Statement to be valid only while Database is still open**. If Java registers cleanup for both Database and Statement in the same arena and relies on an unguaranteed order, it could close DB before Statement.

Correct owner model:

~~~text
   Database owner arena
         |
       db handle
         |
   Statement owner arena
         |
      stmt handle

Close statement scope FIRST.
Close database scope AFTER.
~~~

Skeleton example:

~~~java
try (Arena databaseScope = Arena.ofConfined()) {
    // dbCreate, dbDestroy; attach database cleanup.
    try (Arena statementScope = Arena.ofConfined()) {
        // stmtCreate from db; attach statement cleanup.
        // Use statement.
    } // statement cleanup runs first.
} // database cleanup runs after.
~~~

Do not free **each MemorySegment.asSlice** of Statement as a separate object. If the C API says **db_close automatically destroys all statements**, Java must not simultaneously destroy those statements again on its own. Contracts can change how ownership is divided; nested scopes are just one pattern after you already know the library's exact rules.

### Transferring ownership into C

Sometimes a C function **takes ownership**:

~~~c
/* Assumed contract: on success, C receives buffer ownership. */
int pipeline_take_buffer(void *buffer);
~~~

If the call succeeds and C has taken over the right to free, the Java cleanup attached earlier must **no longer have the right to free**. You should not try to "remove the callback" by keeping the arena alive indefinitely or having the callback guess. Use a wrapper API with a **clear ownership transfer mechanism**, synchronized state transitions, and cleanup attached to the right phase; in many cases, using a **manual owner** is more suitable than a fixed scope cleanup.

If the C API can transfer ownership **only on success**, you must record the exact return code and state on failure: if it fails then Java still owns it, if it succeeds then the native library owns it. Do not free on both sides.

## 13. Thread issues and asynchronous callbacks

### 13.1. Confined arena is only for the owner thread

If the Java owner uses **Arena.ofConfined**, do not pass the managed segment to another Java thread and perform get/set from that thread. Scope checks may throw **WrongThreadException**. Also do not assume a native deallocator is safe when called from an arbitrary callback/thread: some APIs require freeing on the exact thread that initialized the resource.

Closing a confined arena must be performed from the owner thread. If a resource is used by a worker and needs to be cleaned up on the worker, design an owner loop that receives close commands on the right thread.

### 13.2. Shared arena allows multi-threaded access, does not grant automatic synchronization

**Arena.ofShared** is useful when multiple Java threads need shared memory. However:

- Java writes to the same bytes still need memory-order/synchronization per the data contract.
- Do not close the arena while a worker is still reading/writing or a downcall is still active.
- If native C holds onto the raw address on its own, FFM cannot track every native read/write to protect lifetime automatically.
- `IllegalStateException` may occur if close conflicts with an ongoing access.
- A worker canceled mid-way may still have native work not yet confirmed complete.

You need **stop accepting new work → cancel/drain → join/await completion → owner.close**.

### 13.3. Callbacks and upcall stubs have their own lifetime

A C API may hold a function pointer from **Linker.upcallStub**. The stub is created with an Arena and becomes invalid according to that Arena's scope. If C still holds and calls the pointer after the arena closes, that can be a **use-after-free at the function pointer level**.

Proper cleanup does not just free the data pointer; it must also:

1. Unregister the callback on the C side.
2. Wait for any currently running callback to finish.
3. Close data resources in dependency order.
4. Close the arena containing the upcall stub.
5. Finally unload the library if appropriate.

Do not treat the callback pointer, context data, and resource handle as the same allocation; each kind has its own owner and deallocator/arena.

### 13.4. Arena.ofAuto and thread-affine cleanup

Because an auto arena is cleaned up when the runtime determines it is unreachable, code cannot reliably control the thread or timing of cleanup. If a native API specifies that destroy must run on the UI thread, event loop, or the thread that opened the resource, **do not choose GC-timed cleanup** as the primary mechanism. Use an owner thread + explicit close/dispatch or a native resource manager that knows thread affinity.

## 14. What if a cleanup action fails?

Not every release function returns void and "never fails". A C API may return an error code, require status logging, have a timeout, or disallow retry if state has already changed.

For example:

~~~c
/* Illustrative header, no implementation. */
int remote_resource_close(struct RemoteResource *r);
~~~

When attaching cleanup:

- If the close function can fail, determine **when ownership is considered released**.
- Record errors with an observable mechanism; do not swallow them silently.
- Do not retry blindly: the first call may have already freed native memory but returned an error due to a secondary step, and retrying could double-free.
- If retry is needed, the contract must truly support retry or idempotency.
- If close depends on network/async protocols, a cleanup callback running during `Arena.close` may be unsuitable; consider an explicit close abstraction that returns a result.

According to JDK 22, if a custom cleanup action throws an exception, **Arena.close may throw RuntimeException**. Do not assume a failed close means the resource is definitely still alive. Also do not rely solely on an `isAlive()` boolean to prove the C deallocator finished: Java scope status and native resource state are two different concepts.

### An often-overlooked bug: cleanup keeps the arena itself alive

With **Arena.ofAuto()**, if the cleanup lambda captures an object that strongly references back to its own arena/segment, the arena may never become unreachable, preventing the callback from running. Conceptual wrong example:

~~~text
autoArena -> resource -> cleanupAction -> autoArena
           ^                         |
           +-------------------------+
~~~

The reference graph must be examined for actual reachability; in particular, **do not capture autoArena inside the cleanup action and expect it to be reclaimed on time**. Explicitly closed scopes are usually easier to audit for important resources.

## 15. Protecting against pointer aliases and reused addresses

After `free(P)`, the C allocator may reuse **address P** for a new allocation. Therefore:

- Do not use an address (long address) as a **permanent unique ID** for a resource.
- Do not infer "the address is still the same, so the resource is still the old resource".
- A global-scoped raw MemorySegment may still hold address number P after P has been freed. It **is not automatically invalidated** by an `ownerArena` that you created on a different alias.
- If code stores raw pointers in multiple places, protecting a managed view with a scope does not prevent other places from dereferencing unmanaged raw/alias views.

**Good design:** hide the raw pointer inside an owner abstraction, expose only APIs with state checks, and do not let modules arbitrarily reinterpret/free the same address. When passing a pointer to C, only lend it within a call with a confirmed lifetime or build an explicit borrow-tracking/concurrent-owner mechanism.

### Distinguishing double-free from use-after-free

| Condition | Example | Consequence |
| --- | --- | --- |
| **Double-free** | `free(P)`, then `free(P)` again | Heap corruption/crash; undefined behavior |
| **Use-after-free** | `free(P)`, then get data at P | Reading garbage, corrupting heap on write, crash |
| **Memory leak** | `malloc(P)` but never free | Growing native RSS/resource exhaustion |
| **Invalid free** | `free(P + 4)` or `free(borrowed P)` | Undefined behavior |
| **Premature free** | Closing Arena before C worker finishes using P | Native use-after-free |
| **Wrong deallocator** | C uses custom allocator but Java calls libc free | Heap corruption/allocator violation |
| **Double-close of Arena** | Closing the same Arena twice | Second time usually throws IllegalStateException; not synonymous with freeing P twice |

If you encounter a heap-related native crash, you should simultaneously check **ownership, lifetime, aliasing, and error paths** instead of only grepping for free calls that appear next to each other.

## 16. Clear owner design strategies

### Strategy A: one Arena per request

Suitable when a C API returns **one or more owned pointers** whose lifetime equals a single request, with no native consumer outliving the request.

~~~text
request start
   |
   ownerArena = ofConfined()
   |
   create owned handles
   |
   attach cleanup for each handle (no duplicates)
   |
   synchronous processing
   |
   all consumers finish
   |
   ownerArena.close()
   |
request end
~~~

If resources have dependencies, use **nested arenas** or actively manage cleanup order instead of relying on the execution order of multiple callbacks in the same arena.

### Strategy B: one Arena per session

Suitable when a session opens a C object, processes multiple requests, and closes when the session ends. Do not put the session object into a request-local scope. The session owner must have a coordinated close function; after close, all new requests are rejected.

If multiple threads share a session, a **reference/borrow counting** mechanism or lock is needed to ensure it does not close while an active request remains.

### Strategy C: owner wrapper instead of auto cleanup

Suitable when a resource has **transferred ownership**, has a close returning status, needs valid retry, or needs to close on a specific thread/event loop. An `AutoCloseable` wrapper can hold the pointer, custom deallocator, and transition state.

**Condition:** when the wrapper is the owner, do not also register **reinterpret(..., cleanup)** calling the same deallocator. The wrapper holds sole responsibility. A MemorySegment carrying an appropriate scope can still be used for access checks, but there must not be a second release path.

### Strategy D: batch arena with per-handle custom cleanup

If resources live for the same batch and are independent, you can attach cleanups for multiple **different addresses** to the same arena. Do not misunderstand "one arena having multiple actions" as wrong: what is wrong is **one allocation being released multiple times** or **unprotected dependency order**.

When the batch finishes, ensure no C callback or thread still holds any address. Then close once; all valid cleanups execute per the runtime contract, though complex dependencies require separate ordering.

## 17. Testing to detect double-free and leaks

You should have the following tests with a **real native binary**:

| Test | How to perform | Result to verify |
| --- | --- | --- |
| **Happy path** | create → use → owner.close | exactly one destroy, data valid before close |
| **Null allocation** | native create returns NULL | no wrong cleanup registered, clear error |
| **Setup failure** | pointer creation succeeds, wrapper creation fails | exactly one cleanup via appropriate ownership branch |
| **Java exception during use** | throw exception inside try | try-with-resources still closes owner properly |
| **Borrowed pointer** | C returns non-owned view | Java does not call free |
| **Multiple aliases** | create multiple asSlice/views | only the single owner cleans up |
| **Duplicate close** | attempt to close same Arena twice in controlled test | Java reports IllegalStateException; not used as a second free |
| **Concurrent use** | worker holds segment, owner wants to close | does not close before last consumer |
| **Native callback** | unregister then close | no callback after stub/data becomes invalid |
| **Library unload** | close resource before closing library arena | cleanup can call deallocator |
| **Different allocator** | C custom allocator + matching destroy | does not call wrong libc free |
| **Refcount** | retain/release per ownership shares | release count balances retain/ownership count |
| **Long-lived sessions** | open/close thousands of sessions | native RSS/handle count stays stable |

### Native diagnostics

- On Linux/macOS with an appropriate toolchain, build the C test library with **AddressSanitizer (ASan)** to detect double-free/use-after-free in native code.
- Use **UndefinedBehaviorSanitizer**, Valgrind, or OS-appropriate heap diagnostic tools when suitable.
- If JNI/FFM crashes, save the JVM crash log/core dump and native stack symbols.
- Do not treat every **IllegalStateException** as proof that the program is memory-safe: C can corrupt memory outside FFM-checked accesses.
- For untrusted third-party native code, run integration tests in a **separate process** so a crash does not kill the entire test runner.

A release counter like in the demo is useful for smoke tests but does not replace ASan. If code truly double-frees, the process may crash before the counter increments to 2.

## 18. Common mistakes and how to fix them

| Mistake | Why it is wrong | Right approach |
| --- | --- | --- |
| Attaching **free** to a segment allocated by `Arena.allocate` | Arena already owns the allocation | Only close the Arena |
| Attaching cleanup to a borrowed pointer | Java has no right to free | Let the C owner free; Java only borrows for the valid lifetime |
| Attaching two cleanups to the same address | Two owners think they own one allocation | Only one owner; slices are non-owning |
| Manual free and also waiting for arena cleanup | Deallocator is called twice | Choose manual **or** scope cleanup |
| Thinking reinterpret automatically frees memory | reinterpret does not allocate/free on its own | Must use the right cleanup action if Java owns the C allocation |
| Arbitrary reinterpret size | FFM does not know the real allocation | Get byteSize from C contract, validate |
| Using libc free for a pointer needing `custom_destroy` | Wrong allocator/contract | Use the matching deallocator |
| Closing library lookup before resource owner | Cleanup calls into already-unloaded native code | Library arena lives longer than owner arena |
| Closing arena while worker is not finished | C still uses a dangling address | Drain/join then close |
| Using `Arena.ofAuto` to close a resource by a deadline | GC has no fixed schedule | Use explicit close and an owner loop |
| Using `Arena.global` for request resources | Does not release at the right time | Confined/shared arena matching lifetime |
| Closing the same Arena twice | `Arena.close` is not idempotent | One owner closes once via try-with-resources |
| Calling free from each `asSlice` | Slice does not own its own allocation | Single cleanup at the base owner |
| Keeping a global raw pointer after free | Raw scope does not reflect native free | Hide raw handle and only use managed view |
| Thinking `AtomicBoolean` fixes all double-free bugs | Does not control native side/other wrappers | Ownership architecture, state, native contract |
| Implicitly depending on cleanup order in the same arena | Parent may be destroyed before child | Nested scopes or explicit teardown ordering |
| Cleanup lambda capturing auto arena | Can prevent arena from becoming unreachable | Avoid reference cycles through cleanup |
| Retrying blindly after cleanup failure | May have already freed, retry leads to double-free | Clear error contract, no unconditional retry |
| Comparing only addresses to identify resources | Addresses can be reused | Resource IDs/generation and owner state |
| Not checking `create()` returning NULL | Reinterpreting NULL and dereferencing | Check pointer before managing/using |

## 19. Pre-implementation review checklist

- [ ] Accurately identify whether the resource is **allocated by Java Arena, native-allocated with transferred ownership, borrowed, or reference-counted**.
- [ ] Have **exactly one owner** for each allocation/reference ownership share.
- [ ] Deallocator matches the library, type, ABI, and allocator.
- [ ] Do not attach cleanup to borrowed pointers or call free on slices.
- [ ] If using **reinterpret(size, arena, cleanup)**, clearly know size, lifetime, ownership, and restricted API risks.
- [ ] Have a branch handling **NULL** and failures before ownership is registered.
- [ ] Choose **Arena scope** based on the last consumer, not mechanically by Java syntactic scope.
- [ ] Library lookup/`MethodHandle` destroy remain valid **when cleanup runs**.
- [ ] Do not simultaneously use manual free and custom arena cleanup for the same address.
- [ ] `try-with-resources` does not have an extra manual `arena.close` causing duplicate close.
- [ ] Cleanup does not store the **global-scoped cleanup pointer** for use after native free.
- [ ] Do not allow native workers/callbacks to use the pointer after arena closes; have unregister/drain/join.
- [ ] Confined/shared arena and deallocator thread-affinity match the actual design.
- [ ] Parent/child resources have explicitly managed cleanup order.
- [ ] If ownership transfers to C, Java does not continue freeing the same resource.
- [ ] Do not retry a deallocator without knowing the native state after failure.
- [ ] Have tests for aliases, double close, setup error, native error, GC/auto arena, and concurrent shutdown.
- [ ] Have ASan/heap diagnostics or an appropriate integration harness to detect native heap corruption.

## 20. Self-check questions

**1. Does calling MemorySegment.reinterpret(size, arena, null) automatically free the C pointer when arena.close runs?**

**Answer:** No. reinterpret only creates an alias with a new size/scope. If the pointer is allocated by C and owned by Java, there must be a cleanup action calling the right deallocator or another manual release mechanism.

**2. A MemorySegment from Arena.allocate is already managed by the arena. Should you add a callback calling libc free?**

**Answer:** No. Arena already owns the backing region, and manual free can lead to double-free or wrong allocator usage.

**3. Do two asSlice views of an owned segment need two cleanup callbacks?**

**Answer:** No. They are views of the same allocation; only the owner registers cleanup. Each slice does not have an independent allocation.

**4. A C API returns a borrowed const char\*. May Java attach free when the scope ends?**

**Answer:** No, unless the contract actually transfers ownership (which cannot be inferred from const alone). Borrowed pointers are managed by the C owner.

**5. Why should a libraryArena live longer than resourceArena if cleanup calls a destroy MethodHandle?**

**Answer:** Because library lookup can cause the library to be unloaded when its arena closes. If unloaded first, cleanup calls a function pointer that is no longer valid.

**6. Does calling Arena.close twice definitely mean a native double-free?**

**Answer:** No. JDK 22 `Arena.close` is not idempotent; the second time throws `IllegalStateException`. An actual double-free occurs when a native allocation has its deallocator called more times than ownership permits.

**7. A C function retains a pointer after returning, while Java attaches cleanup to a request Arena that closes right after return. What is wrong?**

**Answer:** The Java scope is shorter than the C consumer's lifetime, which can cause use-after-free. You must keep the resource alive until native work finishes and only then close.

**8. If a native object uses retain/release, can two Java wrappers always release independently?**

**Answer:** Only when each wrapper truly owns a reference share that was retained/transferred per contract. Two aliases of the same ref must not release independently.

**9. Why should you not use Arena.ofAuto for a resource that must close on the UI thread at an exact time?**

**Answer:** Cleanup timing and thread through GC are not controlled by the application. You need an owner thread and explicit close/dispatch.

**10. After ownerArena.close, managed.get throws IllegalStateException; is rawPointer still safe?**

**Answer:** No. The raw pointer may still have global scope, but it already points to C-freed memory. FFM does not automatically invalidate every alias detached outside the owner scope.

**11. If custom cleanup throws an exception, should you immediately call native free again?**

**Answer:** Not if you do not know whether the native deallocator already freed the memory. You must follow the error/retry contract to avoid calling free twice.

**12. When are nested arenas more valuable than a single shared arena?**

**Answer:** When resources have lifetime dependencies such as a statement belonging to a database or a native library that must outlive a resource. Nested scopes create a clearer close order.

## Official References

- [JEP 454 — Foreign Function & Memory API finalized in JDK 22](https://openjdk.org/jeps/454).
- [Java SE 22 — Arena: scopes, confined/shared/auto/global, non-idempotent close, and cleanup errors](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- [Java SE 22 — MemorySegment: reinterpret with Arena and cleanup Consumer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- [Oracle Java 22 Guide — Foreign Functions That Return Pointers: malloc/free via reinterpret cleanup](https://docs.oracle.com/en/java/javase/22/core/foreign-functions-that-return-pointers.html).
- [Java SE 22 — SymbolLookup: library lifetime bound to Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html).
- [Java SE 22 — Linker and FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html).

**Conclusion:** To avoid double-free in FFM, you must understand **ownership of the native allocation**, choose a **scope that ends right when the last consumer finishes**, attach **exactly one cleanup action** or one manual owner (not both), call the **right matching deallocator**, and keep the **library/native code alive longer than cleanup**. `MemorySegment`, `asSlice`, and `reinterpret` only manage views/scopes; they **cannot prove C pointer ownership on their own**. Clear ownership design is the most important safeguard against double-free, leaks, and use-after-free.
