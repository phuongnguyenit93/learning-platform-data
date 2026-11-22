# Passing a Function Pointer to a C Library and Reading Parameter Data with an FFM Upcall

## 1. When Java Not Only Calls C, but C Must Also Call Back into Java

In the Java Foreign Function & Memory API (FFM), a **downcall** is a **Java → native function** call, while an **upcall** is the reverse direction: **native C code → Java callback**. A C library may require the user to pass in a **function pointer** so that it can call it whenever new data arrives, a value needs to be computed, records need to be filtered, or an event needs to be dispatched.

Example C contract:

```c
#include <stdint.h>

typedef struct {
    int32_t id;
    int32_t x;
    int32_t y;
} Event;

typedef int32_t (*event_callback)(
        const Event *event,
        int32_t event_bytes,
        void *user_data);

int32_t run_events(event_callback callback, void *user_data);
```

When calling `run_events`, the Java program needs to provide an address that can be **treated by C as a function pointer**. If C executes `callback(&event, sizeof(Event), user_data)`, the Java callback must receive the **address of the struct**, the **byte count of the struct**, and the **address of the context data**; then decode the `id`, `x`, and `y` fields, and return an `int32_t` to C.

This is done using **`Linker.upcallStub`**: turning a `MethodHandle` pointing to a Java method into an **upcall stub** located at a native address that can be passed into C.

### 1.1. Objectives of This Lesson

After studying this lesson, you will be able to:

1. Read **callback function pointer** signatures in C headers.
2. Build an **ABI-compatible** `FunctionDescriptor` and `MethodHandle`.
3. Create a callback pointer using `Linker.upcallStub` and pass it as an `ADDRESS` parameter to a downcall.
4. Read **primitive parameters** and **pointed-to** data from a Java callback, including structs, byte arrays, and `void *user_data`.
5. Handle `NULL`, buffer sizes, alignment, scope, and the fact that pointers are only temporarily valid.
6. Keep the callback stub and context alive long enough; avoid dangling callbacks across an `Arena` close.
7. Handle exceptions **inside the callback**, because an exception escaping an upcall target can cause the JVM to terminate abruptly.
8. Compile and run a complete Java and C example on Linux, macOS, and Windows x64.

### 1.2. Java Version

The code uses the **stable API from JDK 22** (`java.lang.foreign`, JEP 454). Java 17 **does not have** the standard FFM API with these signatures; earlier preview/incubator releases had differences. Use JDK 22+ for the programs in this lesson.

Calls such as `Linker.upcallStub`, `Linker.downcallHandle`, `SymbolLookup.libraryLookup`, and `MemorySegment.reinterpret` are **restricted operations**. When running a Java application on the classpath, grant native access to the unnamed module:

```bash
java --enable-native-access=ALL-UNNAMED FfmCallbackDemo
```

Configuring native access **does not fix the ABI, does not validate C pointers**, and does not automatically extend pointer lifetimes. Grant permission to named modules by module name instead of `ALL-UNNAMED` when deploying a modular application.

## 2. Visualizing the Call Flow with a Function Pointer

```text
Java main()
   |
   | Linker.nativeLinker()
   | SymbolLookup.libraryLookup("...so/.dylib/.dll", arena)
   | downcallHandle(run_events, C signature)
   |
   | MethodHandles.lookup().findStatic(JavaCallback, "onEvent", ...)
   | Linker.upcallStub(methodHandle, callbackSignature, arena)
   |                     |
   |             MemorySegment callbackStub
   |               (native function pointer)
   |                     |
   | call run_events(callbackStub, contextAddress)
   v                     v
C: run_events(event_callback cb, void *ctx)
   |
   | Event event = ...
   | cb(&event, sizeof(Event), ctx)
   v
JVM upcall stub
   |
   | Dispatch to Java MethodHandle
   v
Java: onEvent(MemorySegment eventPtr,
              int eventBytes,
              MemorySegment contextPtr)
   |
   | validate pointer/size
   | reinterpret to read valid data region
   | read id, x, y and factor from context
   | return int
   v
C receives int32_t callback result
   |
   | continue loop/accumulate result
   v
Return total to Java via downcall
```

**There are two independent function signatures:**

- **C API called by Java (downcall)**: `int32_t run_events(event_callback, void*)`.
- **Callback called by C (upcall)**: `int32_t callback(const Event*, int32_t, void*)`.

The two descriptors are **not the same**. Although both contain `ADDRESS`, the callback has three parameters, whereas `run_events` has two parameters.

## 3. Reading C Function Pointer Typedefs Correctly

### 3.1. Translating C Types to Java Carriers

| C ABI | Common FFM layout | Java carrier in `MethodHandle` |
| --- | --- | --- |
| `int32_t` | `ValueLayout.JAVA_INT` | `int` |
| `uint8_t`/`char` | `JAVA_BYTE` | `byte` |
| `int64_t` | `JAVA_LONG` | `long` |
| `double` | `ValueLayout.JAVA_DOUBLE` | `double` |
| `const Event *` | `ValueLayout.ADDRESS` | `MemorySegment` |
| `void *user_data` | `ValueLayout.ADDRESS` | `MemorySegment` |
| Function pointer `event_callback` | `ValueLayout.ADDRESS` | `MemorySegment` |
| C `void` return | `FunctionDescriptor.ofVoid(...)` | `void` |

For this example, C uses **`int32_t`**, not C `long` or `size_t`, to avoid width differences between Linux and Windows 64-bit. `Event` has three `int32_t` fields; on the demo's target compiler/ABI, the expected layout is 12 bytes with offsets 0, 4, and 8 respectively.

If using a complex real-world struct, you must check **`sizeof`, `alignof`, `offsetof`** against the exact target compiler; do not infer the layout solely from field names or the byte counts in the example.

### 3.2. Callback Descriptor

C:

```c
typedef int32_t (*event_callback)(
    const Event *event,
    int32_t event_bytes,
    void *user_data
);
```

FFM:

```java
FunctionDescriptor callbackSignature =
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT, // C returns int32_t
                ValueLayout.ADDRESS,  // const Event*
                ValueLayout.JAVA_INT, // int32_t event_bytes
                ValueLayout.ADDRESS   // void*
        );
```

This is a **snippet inside Java code with appropriate imports**, not a standalone runnable program. The order of `FunctionDescriptor.of(...)` is the **return layout first**, followed by the list of parameter layouts in the **exact C order**.

The Java target must have the signature:

```java
private static int onEvent(
        MemorySegment eventPtr, int eventBytes,
        MemorySegment userDataPtr) {
    // Process and return int.
    return 0;
}
```

It is necessary to distinguish `int eventBytes`, which is a **value passed by value**, from `MemorySegment eventPtr`, which is an **address**. Java does not receive `Event` as a Java object automatically; it must read the data from the native region according to the layout itself.

### 3.3. Descriptor for the C Function Receiving the Callback

C:

```c
int32_t run_events(event_callback callback, void *user_data);
```

FFM:

```java
FunctionDescriptor runSignature =
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT, // return int32_t
                ValueLayout.ADDRESS,  // function pointer
                ValueLayout.ADDRESS   // void* user_data
        );
```

A `downcallHandle` created from this descriptor has the equivalent **Java MethodType**:

```text
(MemorySegment callbackFunctionPointer,
 MemorySegment userDataAddress) -> int
```

The `FunctionDescriptor` snippets above describe the **two call directions**, not the command that executes the callback. The JVM only knows the address to call when you pass the C function symbol to `downcallHandle` or create a stub with `upcallStub`.

## 4. Creating a Java MethodHandle Pointing to the Callback

You can use `MethodHandles.lookup().findStatic(...)` to obtain a handle to a Java static method:

```java
MethodHandle target = MethodHandles.lookup().findStatic(
        FfmCallbackDemo.class,
        "onEvent",
        MethodType.methodType(
                int.class,
                MemorySegment.class,
                int.class,
                MemorySegment.class
        )
);
```

This is a snippet inside the `FfmCallbackDemo` class with a static method `onEvent` of the matching signature; the complete example is in section 8. `findStatic` can access a private static method if the lookup is performed from that same class.

**Why not use a Java method object or an arbitrary lambda?**

- `Linker.upcallStub` accepts a **`MethodHandle`**, not an arbitrary lambda interface directly.
- The `MethodType` must be compatible with the FFM descriptor in **count**, **order**, and **carrier types**.
- You can adapt a lambda/method reference via a static adapter or a bound `MethodHandle`, but you must still produce a handle with the exact signature at the point passed to `upcallStub`.

### 4.1. Creating the Upcall Stub

```java
Linker linker = Linker.nativeLinker();

MemorySegment functionPointer =
        linker.upcallStub(target, callbackSignature, arena);
```

Here `arena` is a live `Arena` and the caller has native access permission. `functionPointer` is **a segment representing the address of the code stub**, **not** a Java `Runnable` or the address of a Java object. C can receive it as a **function pointer** via an `ADDRESS` argument.

According to the JDK 22 Javadoc, the stub is tied to the `Arena`: closing the arena will **free the stub**. Therefore, the callback function pointer **is no longer valid** after the arena is closed.

### 4.2. Passing via Downcall

```java
MethodHandle run = linker.downcallHandle(
        nativeFunctionAddress,
        runSignature
);

int sum = (int) run.invokeExact(
        functionPointer, userDataSegment
);
```

`run.invokeExact` performs the Java→C step. Inside the body of `run_events`, C invokes the function pointer; the C→Java step goes through the stub created by `upcallStub`. When the Java callback returns `int`, C receives an `int32_t` according to the ABI and continues.

`invokeExact` uses **exact** type checking. If the descriptor is `(ADDRESS, ADDRESS) -> JAVA_INT`, you must pass two `MemorySegment` arguments and cast/receive the result as `int`. A wrong carrier can cause a `WrongMethodTypeException`; a wrong native descriptor can cause a crash/corruption because FFM cannot verify signature metadata directly from the C binary.

## 5. Reading Pointer Parameters: Why Does the Received `MemorySegment` Have Length 0?

This is the most important part regarding callback safety.

C calls:

```c
callback(&event, (int32_t) sizeof(Event), user_data);
```

The JVM creates the Java argument for `const Event *` as a **`MemorySegment` representing a native pointer**. When the corresponding layout is `ValueLayout.ADDRESS` without specifying a target layout, this segment **typically has `byteSize() == 0`**. It holds the **address**, not the size information, because the JVM cannot know how many bytes the C pointer actually points to.

Therefore, the following code is **incorrect**:

```java
// WRONG: eventPtr does not yet have bounds for the struct data.
int id = eventPtr.get(ValueLayout.JAVA_INT, 0L);
```

`get` requires at least four bytes within the segment's bounds, so with a zero-length segment it will throw `IndexOutOfBoundsException`.

### 5.1. Checking the Contract Before Expanding Bounds

For a C `Event` known to be 12 bytes in size:

```java
if (eventPtr.address() == 0L) {
    // NULL pointer, must not dereference.
    return -1;
}
if (eventBytes != EVENT_LAYOUT.byteSize()) {
    // Data size mismatch.
    return -1;
}

MemorySegment event = eventPtr.reinterpret(eventBytes);
```

This is a **snippet inside a callback returning `int`** with `EVENT_LAYOUT` defined as in section 6. Calling `reinterpret(long)` **assigns new bounds as requested**, without verifying on its own whether the C pointer actually points to a valid region of that length.

**Safety points that cannot be ignored:**

- `reinterpret` is a **restricted, unsafe operation**. If `eventPtr` has an invalid address or the native region has already been freed, reading can **crash** the JVM.
- Only use it when you trust the ABI/library and have checked the length, `NULL`, and lifecycle according to the **native contract**.
- Do not use `reinterpret(Long.MAX_VALUE)` "just to be safe"; artificially large bounds do not make memory valid.
- Do not store `event`/`eventPtr` for processing after C has left the callback, unless the native API **explicitly transfers ownership and guarantees the lifetime**.
- `const Event *` is a C promise that the callback does not modify the struct; the Java segment itself **does not automatically understand C `const`**. Only read the data and do not call `set` on this borrowed region.

### 5.2. Reading Fields by Offset/Layout

Java describes it as:

```java
StructLayout EVENT_LAYOUT = MemoryLayout.structLayout(
        ValueLayout.JAVA_INT.withName("id"),
        ValueLayout.JAVA_INT.withName("x"),
        ValueLayout.JAVA_INT.withName("y")
);

long ID_OFFSET = EVENT_LAYOUT.byteOffset(
        MemoryLayout.PathElement.groupElement("id")
);
long X_OFFSET = EVENT_LAYOUT.byteOffset(
        MemoryLayout.PathElement.groupElement("x")
);
long Y_OFFSET = EVENT_LAYOUT.byteOffset(
        MemoryLayout.PathElement.groupElement("y")
);
```

This snippet belongs to the class using FFM. With the sample ABI, `ID_OFFSET=0`, `X_OFFSET=4`, `Y_OFFSET=8`. The callback reads:

```java
int id = event.get(ValueLayout.JAVA_INT, ID_OFFSET);
int x  = event.get(ValueLayout.JAVA_INT, X_OFFSET);
int y  = event.get(ValueLayout.JAVA_INT, Y_OFFSET);
```

Offsets are measured **in bytes**. Using `MemoryLayout`/`PathElement` makes the code express the structure and reduces byte-addition errors when a struct has many fields or padding.

### 5.3. Why Are `sizeof` and `offsetof` Needed on the C Side?

FFM knows the layout **you declare**; it does not read C headers or check the ABI at runtime. If the actual C struct has different padding, the Java layout can read the wrong field. In the example in section 8, the C library also exports:

```c
int32_t ffm_event_size_2026(void) {
    return (int32_t) sizeof(Event);
}
int32_t ffm_event_y_offset_2026(void) {
    return (int32_t) offsetof(Event, y);
}
```

Java downcalls these two functions and checks that the size is **12 bytes** and the offset is `y=8` before sending the callback pointer. For real APIs, you should also validate the ABI, alignment, struct version, endianness, and any `#pragma pack` compiler flags if relevant.

## 6. `void *user_data`: Passing Callback State Without Global Mutable State

A C callback often takes an additional `void *user_data` (or `void *ctx`). Its purpose is to pass the caller's context:

```c
int32_t run_events(event_callback callback, void *user_data);
```

On the Java side, we can allocate a native region for an `int32_t` factor:

```java
MemorySegment context = arena.allocate(ValueLayout.JAVA_INT);
context.set(ValueLayout.JAVA_INT, 0L, 2);
```

Then pass `context` to C as the second argument of the downcall. C preserves the address and passes it back as the third parameter of the callback. When the Java callback receives `MemorySegment contextPtr`, it is also typically a **zero-length pointer segment**. Therefore:

```java
if (contextPtr.address() == 0L) {
    return -1;
}

MemorySegment contextView =
        contextPtr.reinterpret(ValueLayout.JAVA_INT.byteSize());
int factor = contextView.get(ValueLayout.JAVA_INT, 0L);
```

This is a **snippet inside the callback**; you should not read the context after the owner closes the arena or if C retains the pointer past its lifetime. In the demo, factor is always 2.

**Benefit of `user_data`:** multiple callbacks can use the same Java method/`FunctionDescriptor` while keeping separate contexts without needing static fields that are constantly mutated.

**Important distinction:** `user_data` is a C pointer to native memory, **not a normal Java object reference**. Do not cast a Java object address to `void*` by guesswork. If you need to associate a Java object with a callback, you can use an ID/handle in the native context and a lifecycle-managed Java registry table, rather than creating raw pointers to Java objects on the heap.

## 7. Reading a Byte Array When C Passes `(pointer, length)`

Besides structs, callback APIs often receive a pair of `const uint8_t *data` and `int32_t length`. That is a **contiguous byte region**, not a C string by default:

```c
typedef int32_t (*bytes_callback)(
        const uint8_t *bytes,
        int32_t byte_count,
        void *user_data);
```

The Java target can have the **same `MethodType`** as the callback receiving a struct pointer:

```text
(MemorySegment, int, MemorySegment) -> int
```

but the **semantics of the first argument differ**: in the bytes callback, `byte_count` is the number of bytes in the array, rather than the fixed size of `Event`.

### 7.1. Safe Reading Pattern Within Callback Scope

```java
if (bytesPtr.address() == 0L
        || byteCount < 0
        || byteCount > MAX_INPUT_BYTES) {
    return -1;
}
MemorySegment view = bytesPtr.reinterpret(byteCount);
byte[] copy = view.toArray(ValueLayout.JAVA_BYTE);
```

This is a snippet inside a callback returning `int`; `MAX_INPUT_BYTES` is an application-defined limit, and the trusted native caller must guarantee the pointer has at least `byteCount` bytes. You can use `view.get(ValueLayout.JAVA_BYTE, i)` to process directly if you do not want to copy.

**Why is `toArray` useful?** It creates an **independent `byte[]`** in Java. In a synchronous callback, C may pass a pointer to a local array on the stack — after the callback returns, that address is no longer guaranteed to be valid. If Java needs to keep the data, **copy the contents before returning**, rather than caching `bytesPtr` or `view`.

If receiving UTF-8 bytes:

- You must know clearly whether `length` includes the terminating `\0` byte.
- If it is **length-delimited data**, decode with `StandardCharsets.UTF_8` on the copied bytes without scanning for `\0`.
- If C passes a **null-terminated C string**, cap the maximum byte count and enforce the NUL contract rather than scanning unboundedly on a zero-length pointer.

### 7.2. Element Count Is Not Byte Count

For `int32_t data[4]`, `count=4` means **4 elements**, which equals **16 bytes**; `reinterpret(4)` is wrong if you want to read the entire array. The formula needs an overflow check:

```java
long byteCount = Math.multiplyExact(
        (long) elementCount,
        ValueLayout.JAVA_INT.byteSize()
);
MemorySegment view = ptr.reinterpret(byteCount);
```

The snippet assumes `elementCount` is valid and `ptr` is still alive. The unit of measurement for `MemorySegment.reinterpret` and `MemorySegment.get` offsets is **bytes**; do not confuse it with an array index.

## 8. Complete Example: C Calls Java Callbacks to Process a Struct, Buffer, and Context

The hands-on example creates a C shared library exporting three entry points (and ABI helpers):

- `ffm_event_size_2026()` and `ffm_event_y_offset_2026()`: verify the struct ABI.
- `ffm_run_events_2026(callback, user_data)`: creates three `Event`s, calls the Java callback for each event, and sums the results.
- `ffm_run_bytes_2026(callback, user_data)`: passes a byte array and its length to the Java callback.

Both C and Java use `int32_t` for values and `ADDRESS` for all pointers. C **calls the callbacks synchronously before returning** and does not store the function pointers in global state. Therefore, using **`Arena.ofConfined()`** in Java is appropriate.

### 8.1. File `FfmCallbackDemo.c`

```c
#include <stdint.h>
#include <stddef.h>

#if defined(_WIN32)
#  define FFM_EXPORT __declspec(dllexport)
#else
#  define FFM_EXPORT __attribute__((visibility("default")))
#endif

typedef struct {
    int32_t id;
    int32_t x;
    int32_t y;
} Event;

typedef int32_t (*event_callback)(
        const Event *event,
        int32_t event_bytes,
        void *user_data);

typedef int32_t (*bytes_callback)(
        const uint8_t *bytes,
        int32_t byte_count,
        void *user_data);

FFM_EXPORT int32_t ffm_event_size_2026(void) {
    return (int32_t) sizeof(Event);
}

FFM_EXPORT int32_t ffm_event_y_offset_2026(void) {
    return (int32_t) offsetof(Event, y);
}

FFM_EXPORT int32_t ffm_run_events_2026(
        event_callback callback,
        void *user_data) {

    if (callback == NULL || user_data == NULL) {
        return -1;
    }

    const Event events[] = {
        {1, 10, 20},
        {2, 30, 40},
        {3, -4, 7}
    };

    int32_t total = 0;
    const size_t count = sizeof(events) / sizeof(events[0]);

    for (size_t i = 0; i < count; ++i) {
        // events[i] remains alive for the duration of this call.
        const int32_t answer = callback(
                &events[i],
                (int32_t) sizeof(Event),
                user_data);

        // -1 is an application-chosen error code.
        if (answer < 0) {
            return -1;
        }
        total += answer;
    }
    return total;
}

FFM_EXPORT int32_t ffm_run_bytes_2026(
        bytes_callback callback,
        void *user_data) {

    if (callback == NULL || user_data == NULL) {
        return -1;
    }

    const uint8_t bytes[] = {2, 4, 6, 8};

    // The bytes array is on the stack, valid only while the callback runs.
    return callback(
            bytes,
            (int32_t) sizeof(bytes),
            user_data);
}
```

**Characteristics of the C code:**

- Includes a symbol export macro that works on Linux/macOS/Windows. On Windows you should build x64; 32-bit platforms may require additional handling for calling conventions and symbol decoration.
- `Event` has three `int32_t` fields. Java must declare the exact matching layout and must not assume incorrect padding.
- `event_callback` and `bytes_callback` are **function pointers**; C has no knowledge of `MethodHandle` or Java objects.
- `events[]` and `bytes[]` are **local variables**. C only passes their addresses to synchronous callbacks; Java must not retain raw pointers for use after C returns.
- Error code `-1` is an **example convention**, not a built-in FFM/JNI error code.
- C does not throw Java exceptions. It receives `int32_t` from the callback and handles it as a C value.

### 8.2. File `FfmCallbackDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.Linker;
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.StructLayout;
import java.lang.foreign.SymbolLookup;
import java.lang.foreign.ValueLayout;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Path;
import java.util.Arrays;

import static java.lang.foreign.MemoryLayout.PathElement.groupElement;

public final class FfmCallbackDemo {

    private static final StructLayout EVENT_LAYOUT =
            MemoryLayout.structLayout(
                    ValueLayout.JAVA_INT.withName("id"),
                    ValueLayout.JAVA_INT.withName("x"),
                    ValueLayout.JAVA_INT.withName("y")
            );

    private static final long ID_OFFSET =
            EVENT_LAYOUT.byteOffset(groupElement("id"));

    private static final long X_OFFSET =
            EVENT_LAYOUT.byteOffset(groupElement("x"));

    private static final long Y_OFFSET =
            EVENT_LAYOUT.byteOffset(groupElement("y"));

    // C callback: int32_t cb(const pointer*, int32_t length, void* ctx)
    private static final FunctionDescriptor CALLBACK_DESC =
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS
            );

    // C driver: int32_t run(callback_function_ptr, void* ctx)
    private static final FunctionDescriptor RUN_DESC =
            FunctionDescriptor.of(
                    ValueLayout.JAVA_INT,
                    ValueLayout.ADDRESS,
                    ValueLayout.ADDRESS
            );

    private FfmCallbackDemo() {
    }

    private static int factor(MemorySegment contextAddress) {
        if (contextAddress.address() == 0L) {
            throw new IllegalArgumentException("NULL user_data");
        }
        MemorySegment context = contextAddress.reinterpret(
                ValueLayout.JAVA_INT.byteSize());
        return context.get(ValueLayout.JAVA_INT, 0L);
    }

    // MethodType: (MemorySegment, int, MemorySegment) -> int
    private static int onEvent(MemorySegment eventAddress,
                               int eventBytes,
                               MemorySegment contextAddress) {
        try {
            if (eventAddress.address() == 0L
                    || eventBytes != EVENT_LAYOUT.byteSize()) {
                return -1;
            }

            // The pointer passed by native has size 0.
            // C guarantees a valid Event during this callback.
            MemorySegment event = eventAddress.reinterpret(eventBytes);

            int id = event.get(ValueLayout.JAVA_INT, ID_OFFSET);
            int x = event.get(ValueLayout.JAVA_INT, X_OFFSET);
            int y = event.get(ValueLayout.JAVA_INT, Y_OFFSET);
            int multiplier = factor(contextAddress);

            int answer = Math.multiplyExact(
                    Math.addExact(x, y), multiplier);

            System.out.println("event id=" + id
                    + " x=" + x
                    + " y=" + y
                    + " factor=" + multiplier
                    + " result=" + answer);
            return answer;
        } catch (Throwable unexpected) {
            // Never let a Throwable escape across the upcall boundary.
            // Return the error sentinel per the C contract.
            return -1;
        }
    }

    private static int onBytes(MemorySegment bytesAddress,
                               int byteCount,
                               MemorySegment contextAddress) {
        try {
            if (bytesAddress.address() == 0L
                    || byteCount < 0
                    || byteCount > 1024) {
                return -1;
            }

            MemorySegment view =
                    bytesAddress.reinterpret(byteCount);

            // Independent Java snapshot before the native stack disappears.
            byte[] copied = view.toArray(ValueLayout.JAVA_BYTE);

            int sum = 0;
            for (byte value : copied) {
                sum = Math.addExact(
                        sum, Byte.toUnsignedInt(value));
            }

            int multiplier = factor(contextAddress);
            int answer = Math.multiplyExact(sum, multiplier);

            System.out.println("bytes=" + Arrays.toString(copied)
                    + " sum=" + sum
                    + " factor=" + multiplier
                    + " result=" + answer);

            return answer;
        } catch (Throwable unexpected) {
            return -1;
        }
    }

    public static void main(String[] args) throws Throwable {
        Linker linker = Linker.nativeLinker();

        Path path = Path.of(
                System.mapLibraryName("ffmcallbackdemo")
        ).toAbsolutePath().normalize();

        try (Arena arena = Arena.ofConfined()) {
            SymbolLookup library =
                    SymbolLookup.libraryLookup(path, arena);

            MethodHandle eventSize = linker.downcallHandle(
                    library.find("ffm_event_size_2026").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT)
            );

            MethodHandle eventYOffset = linker.downcallHandle(
                    library.find("ffm_event_y_offset_2026").orElseThrow(),
                    FunctionDescriptor.of(ValueLayout.JAVA_INT)
            );

            int nativeEventSize = (int) eventSize.invokeExact();
            int nativeYOffset = (int) eventYOffset.invokeExact();

            if (nativeEventSize != EVENT_LAYOUT.byteSize()
                    || nativeYOffset != Y_OFFSET) {
                throw new IllegalStateException(
                        "C Event ABI does not match Java layout");
            }

            System.out.println("eventBytes=" + nativeEventSize
                    + " yOffset=" + nativeYOffset);

            MethodHandle runEvents = linker.downcallHandle(
                    library.find("ffm_run_events_2026").orElseThrow(),
                    RUN_DESC
            );

            MethodHandle runBytes = linker.downcallHandle(
                    library.find("ffm_run_bytes_2026").orElseThrow(),
                    RUN_DESC
            );

            MethodType callbackType = MethodType.methodType(
                    int.class,
                    MemorySegment.class,
                    int.class,
                    MemorySegment.class
            );

            MethodHandle eventTarget =
                    MethodHandles.lookup().findStatic(
                            FfmCallbackDemo.class,
                            "onEvent",
                            callbackType
                    );

            MethodHandle bytesTarget =
                    MethodHandles.lookup().findStatic(
                            FfmCallbackDemo.class,
                            "onBytes",
                            callbackType
                    );

            MemorySegment eventStub = linker.upcallStub(
                    eventTarget, CALLBACK_DESC, arena);
            MemorySegment bytesStub = linker.upcallStub(
                    bytesTarget, CALLBACK_DESC, arena);

            MemorySegment context =
                    arena.allocate(ValueLayout.JAVA_INT);
            context.set(ValueLayout.JAVA_INT, 0L, 2);

            // Java -> C -> Java, synchronous on the same thread.
            int eventTotal = (int) runEvents.invokeExact(
                    eventStub, context);

            if (eventTotal < 0) {
                throw new IllegalStateException(
                        "Event callback failed");
            }
            System.out.println("events total=" + eventTotal);

            int bytesTotal = (int) runBytes.invokeExact(
                    bytesStub, context);

            if (bytesTotal < 0) {
                throw new IllegalStateException(
                        "Bytes callback failed");
            }
            System.out.println("bytes total=" + bytesTotal);

            // C has returned: do not retain Event or bytes pointers.
        }
        // Arena closed: function pointers, context, and
        // the library tied to lookup must not be used further.
    }
}
```

### 8.3. Step-by-Step Explanation of the Java Code

1. **`EVENT_LAYOUT` and offsets**: describes the 3 fields `id`/`x`/`y` matching C; uses `byteOffset(groupElement(...))` to avoid hard-coding offsets in the callback.
2. **`CALLBACK_DESC`**: declares the callback target `int(MemorySegment,int,MemorySegment)`; when C invokes the function pointer, the JVM converts these 3 ABI parameters to Java according to the descriptor.
3. **`RUN_DESC`**: declares the C driver `int(void*,void*)`. C does not actually treat the first parameter as a data pointer, but as a **function pointer**, though both Java carriers are `ADDRESS`.
4. **`libraryLookup(Path,Arena)`**: opens the shared library we compiled. No Java `native` method, `javac -h`, or `JNI_OnLoad` is needed.
5. **ABI validation**: Java calls `ffm_event_size_2026` and `ffm_event_y_offset_2026` before receiving data; if the layout is wrong, it rejects instead of silently reading the wrong fields.
6. **`findStatic`**: creates `MethodHandle`s pointing to `onEvent` and `onBytes`; both use the same parameter shape but have different data-decoding logic.
7. **`upcallStub`**: creates two function pointers. C receives them in `runEvents`/`runBytes`, rather than receiving a Java `MethodHandle` as an arbitrary JVM pointer.
8. **`context`**: allocates 4 native bytes containing `int=2`, passed via `void *user_data`. C simply passes that address back to the Java callback.
9. **`onEvent`**: receives the raw pointer and length, validates `NULL`/size, expands bounds with `reinterpret`, and reads the 3 numbers. The sum `(x+y)*2` is returned to C.
10. **`onBytes`**: validates the length and upper bound 1024, copies the array into a `byte[]` with `toArray`, sums the unsigned bytes, and multiplies by the factor.
11. **`catch(Throwable)`**: the callback always returns an `int` error code if Java throws an unexpected error; it does not let `Throwable` cross the upcall boundary.
12. **Arena/Scope**: keeps `library`, `eventStub`, `bytesStub`, and `context` alive **until after both C calls return**. Only at the end of `try` is the arena closed.

This is a **synchronous callback** example. If the C library stores the pointer to call from another thread later, this model is **not sufficient**; see section 11.

### 8.4. Compiling/Running on Linux

Prerequisites: JDK 22+ and GCC/Clang matching the ABI/JVM, run in the directory containing both source files.

```bash
gcc -std=c11 -O2 -shared -fPIC \
    FfmCallbackDemo.c -o libffmcallbackdemo.so

javac FfmCallbackDemo.java

java --enable-native-access=ALL-UNNAMED FfmCallbackDemo
```

`SymbolLookup.libraryLookup(Path,Arena)` takes an absolute path built from `System.mapLibraryName`, so **`-Djava.library.path=.` is not needed** in this lesson.

If `gcc` and `javac` target different architectures, Java will not be able to load the shared library. For example, an x86_64 JVM needs a `libffmcallbackdemo.so` with an x86_64-compatible ABI/architecture.

### 8.5. Compiling/Running on macOS

Use Clang and JDK 22+ appropriate for Apple Silicon or Intel:

```bash
clang -std=c11 -O2 -dynamiclib \
    FfmCallbackDemo.c -o libffmcallbackdemo.dylib

javac FfmCallbackDemo.java

java --enable-native-access=ALL-UNNAMED FfmCallbackDemo
```

On macOS, the filename from `System.mapLibraryName("ffmcallbackdemo")` is typically `libffmcallbackdemo.dylib`. Ensure the toolchain, binary, and JDK use the same CPU architecture; the example code does not depend on JNI headers.

### 8.6. Compiling/Running on Windows x64

Open Visual Studio's **x64 Native Tools Command Prompt**, set JDK 22+ x64 in `PATH`, then run in the directory containing both source files:

```bat
cl /nologo /O2 /LD FfmCallbackDemo.c /link /OUT:ffmcallbackdemo.dll

javac FfmCallbackDemo.java

java --enable-native-access=ALL-UNNAMED FfmCallbackDemo
```

`FFM_EXPORT` on Windows uses `__declspec(dllexport)` so that the `ffm_*` names can be looked up. You should use x64 to avoid Windows x86 calling convention and export-name decoration differences. The program's native library path will be `ffmcallbackdemo.dll` in the working directory.

### 8.7. Exact Stdout on a Successful Run

```text
eventBytes=12 yOffset=8
event id=1 x=10 y=20 factor=2 result=60
event id=2 x=30 y=40 factor=2 result=140
event id=3 x=-4 y=7 factor=2 result=6
events total=206
bytes=[2, 4, 6, 8] sum=20 factor=2 result=40
bytes total=40
```

**Explanation of the calculations:**

- `sizeof(Event)=12`, `offsetof(Event,y)=8` match Java `EVENT_LAYOUT` and `Y_OFFSET`.
- Event 1: `(10+20)*2=60`.
- Event 2: `(30+40)*2=140`.
- Event 3: `(-4+7)*2=6`.
- C sums the three results: `60+140+6=206`.
- The byte buffer contains `2,4,6,8`; Java copies it to a new array, computes the unsigned byte sum `20`, and multiplies by factor 2 to get `40`.
- Each `runEvents/runBytes` invokes the callback immediately before returning, so the log lines appear in this order on the **success path**.
- There is no `System.out` in C; all stdout displayed is printed by Java.

If the program reports an ABI mismatch error on another target, **do not remove validation just to make it run**: you must change `StructLayout` to match the real C ABI or fix the C build target to match.

## 9. Key Points When Reading C Parameters from Java

### 9.1. Primitive Values vs. Pointers

C callback:

```c
int32_t cb(const Event *event, int32_t event_bytes, void *ctx);
```

corresponds to:

```java
static int cb(MemorySegment eventPtr,
              int eventBytes,
              MemorySegment ctxPtr) { ... }
```

`eventBytes` is already a **Java `int`**: no `reinterpret` is needed to read it. By contrast, `eventPtr` and `ctxPtr` are addresses; you must know how many bytes the backing region has before dereferencing.

**Wrong:** calling `eventPtr.get(JAVA_INT,0)` when the segment has size 0, and blaming the JDK. That is the intentional consequence of bounds checking.

### 9.2. Passed-In Pointers Do Not Carry Real Lifetime

According to the FFM Javadoc, a pointer passed into an upcall can be represented by a zero-length segment associated with the **global scope**. That global scope **does not assert that the C memory region will exist forever**. The scope of the Java wrapper and the real lifetime of the C allocation **are two different things**.

In the example, C passes the address of `Event events[]`/`uint8_t bytes[]` living on the native stack. You may only read it during the synchronous callback itself; if you need to process it later, **copy the bytes or convert them into a Java DTO** while C still guarantees the memory region is valid.

### 9.3. Byte Order and Alignment

`ValueLayout.JAVA_INT` accesses a 4-byte `int` with the platform's layout byte order. If the C struct is compiled on the same native ABI and does not change format, this is reasonable. When reading a buffer from the network or a file with a different byte order, use `withOrder(ByteOrder.BIG_ENDIAN/LITTLE_ENDIAN)` accordingly.

`MemorySegment.reinterpret(length)` does not automatically fix alignment. For unaligned C fields or packed structs, use a layout with the appropriate alignment (for example `JAVA_INT_UNALIGNED`) **only when** the C ABI actually specifies packed data. Do not choose unaligned layouts to mask struct-layout mistakes.

### 9.4. `const` in C Is Not Automatically Enforced by Java

`const Event *` specifies how the C caller/callee may use the pointer; a Java `MemorySegment` does not automatically become read-only just from `ADDRESS` metadata. Therefore, the Java callback must **respect the native contract**: if the C parameter is `const`, only read.

If you want to guard against accidental writes in Java code, you can create a read-only view:

```java
MemorySegment event = eventPtr
        .reinterpret(eventBytes)
        .asReadOnly();
```

This is a snippet inside the callback after validating the pointer/size. `asReadOnly` prevents write operations through this view; it does not validate the C pointer or freeze the data if another C thread modifies the same region.

## 10. Advanced Option: `AddressLayout.withTargetLayout`

Besides calling `reinterpret` inside the callback, you can create an **`AddressLayout` with a target layout**. The idea:

```java
var eventAddressLayout =
        ValueLayout.ADDRESS.withTargetLayout(EVENT_LAYOUT);

FunctionDescriptor describedCallback =
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT,
                eventAddressLayout,
                ValueLayout.JAVA_INT,
                ValueLayout.ADDRESS
        );
```

This is a **snippet** assuming `EVENT_LAYOUT` is already declared. According to the `Linker.upcallStub` Javadoc, if a callback argument has an `AddressLayout` with target layout `T`, the segment passed to the Java target can be represented with size `T.byteSize()` instead of 0.

**This does not mean absolute safety.** `withTargetLayout` is restricted/unsafe; you are asserting that the pointer actually points to a valid object of the matching size and alignment. The Java runtime cannot verify a native pointer on its own, and when C passes a dynamically sized buffer, you **cannot** apply an arbitrary fixed target layout.

For C APIs with dynamic `pointer + length` parameters like a bytes callback, using `ADDRESS` plus checking `length` and then calling `reinterpret(length)` can be clearer.

### 10.1. When to Use a Target Layout?

- The parameter always points to a fixed struct and the ABI is validated.
- You want to reduce `reinterpret(EVENT_LAYOUT.byteSize())` boilerplate.
- You can check `sizeof` and offsets on the native side beforehand.
- Do not use it if the pointer is optional/`NULL` or points to a region whose shape varies without verification.

### 10.2. `MemoryLayout` Is Not an Automatic C Serializer

Declaring a `StructLayout` in Java only describes the **shape of bytes**. It does not invoke C constructors, does not manage the lifetime of C allocations, does not turn pointers into a Java object graph, and does not check the `ABI version` in the shared library. To model a complex struct in Java, you must design the schema properly or create a Java DTO after reading.

## 11. If the C Library Stores the Callback to Call Later: Changing the Lifecycle Model

The example in section 8 **does not store the callback**. This is critical because `Arena.ofConfined()` and C stack addresses only live for the synchronous scope of the downcall.

Suppose a C API looks like:

```c
void register_callback(event_callback callback, void *user_data);
void unregister_callback(void);
```

This is an **illustrative C pattern**, with no implementation in the runnable demo. The library may invoke the callback from an arbitrary native worker/thread **after `register_callback` has returned**. In that case, you must never use the `try(Arena.ofConfined()) { register(...); }` pattern and close the arena before callbacks finish.

### 11.1. Lifecycle Model for Asynchronous Callbacks

```text
Java owner initializes
    |
    | create Arena.ofShared()
    | allocate long-lived native context
    | create upcallStub using the shared arena
    | register_callback(stub, context)
    v
ACTIVE
    |
    | C may emit callbacks from native threads
    | Java callback must not throw, must be thread-safe
    | C data must remain alive during each callback
    v
STOPPING
    |
    | ask C to stop generating new callbacks
    | unregister_callback / stop_native_threads
    | wait for all in-flight callbacks to complete
    v
SAFE_TO_CLOSE
    |
    | close arena (frees stub/context)
    v
CLOSED
```

This is an **application model**, not a built-in lifecycle API of Java FFM. `Arena.ofShared()` allows multi-threaded access within its scope, but **does not automatically provide a stop/unregister/join mechanism**. If C retains the function pointer after the arena closes, a C call to the freed address can crash the JVM.

### 11.2. A Callback May Run on a Different Native Thread

Some C libraries invoke callbacks synchronously on the Java thread used for the downcall; others use their own thread pool. You must study the library's threading contract:

- Can multiple callback instances run concurrently?
- Is the callback allowed to be reentrant (callback calling back into the C API)?
- How long is the callback allowed to block?
- Can the native thread terminate while the Java callback is still processing?
- Who stops the worker and waits for all callbacks before closing the arena?
- Does the Java callback rely on `ThreadLocal`, security context, class loader, virtual thread assumptions, or a UI thread?

Do not assume the callback always runs on Java `main`. Shared Java state should be synchronized (`AtomicInteger`, queues, locks...); avoid holding locks across callbacks if a callback can call back into native code and create a lock-ordering cycle.

### 11.3. Do Not Mix `std::thread::detach` with FFM Callback Lifetime

A C++ library may spawn background threads and detach them from the `std::thread` object using `detach()`. That only removes the ability to `join` via that object; it **does not** guarantee that callbacks have stopped and **does not** extend the FFM upcall stub. For asynchronous callbacks, there should be **unregister + stop + quiescence acknowledgment** or an equivalent shutdown contract.

### 11.4. Long-Lived User Data

If C retains `void *user_data` after `register_callback`, the context must also live until C confirms it will no longer use it. Do not pass the address of a C stack variable that goes out of scope or a Java native arena that closes early. If you want to use a Java object as context, use a stable ID/registry mechanism and clean up at the right time; do not pass a raw Java object pointer into C.

## 12. Java Exceptions in Upcalls Are a Dangerous Situation

Unlike normal Java callbacks, **the `Linker.upcallStub` Javadoc warns that the target `MethodHandle` must not throw exceptions out**. If an exception escapes from an upcall target, **the JVM may terminate abruptly**; there is no normal way for C to `try/catch` a Java exception like Java code does.

That is why the example's callback code does:

```java
private static int onEvent(/* parameters */) {
    try {
        // validate and read data
        // ...
        return computedResult;
    } catch (Throwable unexpected) {
        return -1;
    }
}
```

This is a **conceptual pattern**, not a standalone Java method because the parameter list is abbreviated. The purpose of `catch(Throwable)` inside the callback is to **prevent a Java `Throwable` from crossing the ABI boundary**; you should not copy the habit of "catching all `Throwable`s" into regular Java code. In production applications, report errors to a fault-tolerant logging/telemetry channel, return a clear error code to C, and inspect that result in the Java caller. Avoid logging that itself throws and escapes the callback.

### 12.1. Agree on Error Codes Between Java and C

The example chooses `-1` as the error:

- The Java callback returns `-1` if the pointer/size is invalid or an exception occurs.
- C `ffm_run_events_2026` checks the callback result, stops if negative, and returns `-1`.
- Java sees the negative total after the downcall and throws `IllegalStateException` **on the Java side calling the downcall**, where normal exceptions are allowed to be handled.

If a real C API allows the callback to return negative numbers as valid results, you cannot arbitrarily choose `-1` as a sentinel. You must follow the C API's design: there may be an `error_code*` parameter, a boolean success flag, a `void` callback with a result buffer, or state inside `user_data`.

### 12.2. Do Not Call Heavy Java Logic Inside a Callback Without Understanding the Contract

A callback running on a native thread may occur while C holds a mutex or is handling a signal. Calling heavy Java code, blocking I/O, synchronized methods, or calling back into the C library itself can cause **deadlock/reentrancy problems**.

Prefer short callbacks that validate quickly and push data to a Java queue/worker when the C API permits. If you need to keep the payload after the callback, **copy it into Java-owned data** before returning. In low-latency environments, measure the Java↔C↔Java transition cost instead of assuming upcalls are free.

## 13. Issues with Callback Pointers and `Arena`

### 13.1. The Arena Owns the Stub

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment stub =
            linker.upcallStub(callbackHandle, descriptor, arena);
    // C may only use stub while arena is alive.
}
// Outside, never pass stub to C for further calls.
```

This is a snippet with valid `linker`/`callbackHandle`/`descriptor`. A `MemorySegment` representing a function pointer is **not** an immortal reference. When the arena closes, the stub code region is deallocated. Keeping the Java `stub` variable around does not make that address valid again.

### 13.2. Keep the Native Library Alive Too

If Java creates downcalls from `SymbolLookup.libraryLookup(path, arena)`, the library lookup also has a lifecycle tied to the arena. Not only the stub/context, but **C function addresses** and downcall `MethodHandle`s also require the library to remain loaded.

Therefore, use an owner that manages:

- The native library's arena.
- The upcall stub and native context allocations.
- The downcall handles.
- The `RUNNING/STOPPING/CLOSED` state.
- Unregistering and waiting for in-flight callbacks if the API is asynchronous.

Do not close the arena before the C API is truly inactive; do not issue downcalls after the owner has closed.

### 13.3. `Arena.ofAuto` Is Not Suitable for Leaving Long-Term Callbacks Unmanaged

If a callback is stored in C and Java no longer holds an explicit reference, an automatic arena may be reclaimed by GC at an uncontrolled time. For callback registrations requiring explicit lifetimes, use an arena with an owner and a concrete close step; `Arena.ofShared()` is the choice if other native threads need access. Parameters from C located on the stack still follow C's own lifetime and are not "extended" merely by a shared arena.

## 14. Distinguishing Passing a Pointer, Passing a Struct by Value, and Passing a Pointer to a Pointer

Not every C header uses the same ABI.

### 14.1. Pointer to Struct

```c
void notify(const Event *event);
```

The Java callback receives a `MemorySegment` representing the **address of the struct**, then reads each field after verifying bounds. For the descriptor: `ofVoid(ADDRESS)`.

### 14.2. Struct by Value

```c
void notify(Event event);
```

This is **passing a struct by value**, not a pointer. The ABI may split the struct across registers/stack depending on the architecture. FFM uses a **`GroupLayout`** in the descriptor, and the corresponding carrier may differ—for example, a `MemorySegment` containing a copy/struct data according to linker rules. **Do not** replace a by-value struct with `ADDRESS` just because both contain bytes.

### 14.3. Pointer to Pointer

```c
void notify(Event **event_ptr);
```

The parameter is the **address of a memory slot containing an `Event` address**, not the address of `Event` directly. Java must have an appropriate layout/scope to read an `ADDRESS` at that address, and then follow the pointer that was read. If you treat it as `Event*`, you will interpret the bytes of a pointer as `id`/`x`/`y` and cause errors.

### 14.4. Arrays and `char*`

`const uint8_t *bytes, int32_t length` is a **byte array with an explicit length**. `const char *text` may be a **NUL-terminated C string**, but not every `char*` is a string. Do not use `getString(0)` or read unboundedly unless the data contract, NUL termination, and bounds have been proven valid.

## 15. Passing Java State Without `void *ctx`

Some C APIs only accept:

```c
typedef int32_t (*simple_callback)(int32_t value);
void register_simple(simple_callback cb);
```

There is no `void *user_data`. Java can still create a **bound `MethodHandle`** to attach a Java object/state to the callback target:

```java
// Conceptual example: the state object must be kept alive
// by the owner of the callback registration.
MethodHandle bound = MethodHandles.insertArguments(
        instanceMethodHandle, 0, stateObject);

MemorySegment stub = linker.upcallStub(
        bound,
        FunctionDescriptor.of(
                ValueLayout.JAVA_INT, ValueLayout.JAVA_INT),
        arena);
```

This is an **illustrative snippet**, requiring `instanceMethodHandle` to have its first parameter match `stateObject` and the post-bind method type to be `(int)int`. `MethodHandles.insertArguments` does not give C a Java object pointer; `upcallStub` bridges through the bound `MethodHandle`.

Comparison:

| Approach | Does the C API need `void *user_data`? | Does C hold the Java object directly? | Lifecycle considerations |
| --- | --- | --- | --- |
| Native context `Arena.allocate` | Yes | No | Keep context memory alive until callbacks stop |
| Java bound `MethodHandle` | No | No | Owner must keep stub/state alive |
| ID registry in Java | Usually yes | No | C holds ID, Java looks up ID with synchronization and cleanup |
| Raw Java object address manually cast | Not recommended | Wrong model | GC can move objects, unsafe |

## 16. Debugging Upcalls When Errors Occur

### 16.1. C Symbol Not Found

If `library.find("ffm_run_events_2026")` returns empty:

- Check that the `.so`/`.dll`/`.dylib` file has the right name.
- Check exported symbols with `nm -D` (Linux), `nm -gU` (macOS), `dumpbin /EXPORTS` (Windows).
- Check C++ name mangling and visibility; the lesson's C example uses the `FFM_EXPORT` macro.
- Make sure you built the exact binary being loaded by Java; do not just look at the C header.

### 16.2. FFM Reports `WrongMethodTypeException`

Usually caused by a `MethodHandle` not matching the `FunctionDescriptor`, `invokeExact` having wrong types, or confusing the callback signature with the driver signature. In the example:

```text
C callback: int32_t (*)(Event*, int32_t, void*)
Upcall:      (MemorySegment, int, MemorySegment) -> int

C driver:   int32_t (*)(callback_ptr, void*)
Downcall:    (MemorySegment, MemorySegment) -> int
```

Do not create a callback target `(MemorySegment,long,MemorySegment)->int` when `event_bytes` is `int32_t`.

### 16.3. Callback Receives Pointer but Reading Throws `IndexOutOfBoundsException`

Common causes: a size-0 pointer segment, not calling `reinterpret`, or an `AddressLayout` without a target layout. Before reading, you must have a valid size and lifetime contract. Do not fix it by inventing a huge size.

### 16.4. JVM Crash After Callback Has Finished

Possible causes:

- C kept a function pointer to the upcall stub after the `Arena` closed.
- Java kept a pointer to C stack data and read it after the callback returned.
- Wrong ABI (confusing struct by value with struct pointer, wrong numeric types/parameter widths, mismatched calling convention).
- A Java exception escaped the upcall target.
- Native C code wrote out of bounds, or returned a freed pointer.

When the JVM crashes, do not assume it is a normal Java bug. Check the C ABI, scope ownership, and crash logs/HotSpot error files; use ASan/UBSan or native debuggers when the environment permits.

### 16.5. Native Access Errors

`java.lang.IllegalCallerException` can occur when the caller does not have permission to use a restricted API. For classpath applications on JDK 22+, run with `--enable-native-access=ALL-UNNAMED`. For named modules, grant permission to the exact module calling restricted methods. **Do not** treat this flag as a way to skip pointer/size checks.

### 16.6. Callback Runs Multiple Times or on Multiple Threads

If C allows concurrent callbacks, the Java target must be thread-safe. Shared mutable `static` variables need synchronization. If the C callback is invoked from another thread and the arena is confined, review the scope contract; a **shared arena** is commonly required for cross-thread asynchronous callbacks. Avoid closing the shared arena while callbacks are still running.

## 17. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Passing a `MethodHandle` directly to C | Not a native function pointer | Use `Linker.upcallStub` and pass the stub `MemorySegment` |
| Using the same `FunctionDescriptor` for C driver and callback when signatures differ | Wrong ABI | Describe the two signatures separately |
| Returning `long` from Java target when C callback returns `int32_t` | `MethodType` mismatch | Use `JAVA_INT` and `int` |
| Ignoring zero-length pointers | `IndexOutOfBoundsException` | Check size/`NULL`, then `reinterpret` per contract |
| Using `reinterpret` with an arbitrary byte count | Crash/memory corruption | Trust the native provider, verify size/lifetime |
| Reading `Event*` as a Java object | No automatic marshaling | Use `StructLayout`/offsets to read bytes |
| Forgetting `void *user_data` | Callback has no context | Allocate native context and pass it to C |
| Passing a fake Java heap object address as a native pointer | Violates GC/lifetime | Use native context or a Java registry |
| Keeping a pointer to a C stack buffer after return | Use-after-free | Copy data inside the callback |
| Closing the `Arena` right after registering an async callback | C calls a freed stub | Unregister, wait for in-flight callbacks, then close |
| Callback throws a Java exception out | JVM may terminate abruptly | Catch errors in target and return a valid C status |
| Skipping `sizeof/offsetof` checks | Reading wrong fields | Verify struct layout against the C ABI |
| Calling `getString` on `uint8_t *` without knowing NUL | Out-of-bounds read | Process by pointer + length and charset |
| Assuming `const` means read-only Java memory | May mutate C memory against contract | Read only, consider `asReadOnly` |
| Using a confined `Arena` with callbacks from other C workers | Thread access error | Shared arena and lifecycle synchronization |
| C/Java using different compilers/architectures | Load/ABI failure | Build for the same architecture/matching JDK |
| Treating FFM upcalls like JNI `Java_Class_method` | Confusing two mechanisms | FFM uses `MethodHandle` and function pointers |
| Forgetting to grant native access | Restricted operation rejected | Configure `--enable-native-access` for the right module |

## 18. Extended Practice Exercises

**Exercise 1 — Reading an additional `timestamp` field:** Add `int64_t timestamp` to C's `Event` and `JAVA_LONG` to Java's `StructLayout`. Recalculate padding/alignment and use `offsetof` in C to verify before dereferencing. Compare Windows/Linux ABIs.

**Exercise 2 — Payload containing negative numbers:** Change `bytes[]` to bytes such as `{0x80, 0xFF}`. Java `byte` is signed; use `Byte.toUnsignedInt` to compute 128 and 255 instead of -128 and -1. Print output clearly showing the logical unsigned values.

**Exercise 3 — Callback returning an error:** Change C to pass `event_bytes=0` once. The Java callback should return `-1`, C stops, and the Java caller detects `IllegalStateException` after the downcall. Do not let an exception escape across the upcall boundary.

**Exercise 4 — Two callbacks sharing context:** Keep `factor=2`, then change it to 3 before calling `ffm_run_bytes_2026`. The event result remains 206, but the bytes result becomes `60`; explain why, since C only passes back the context address without copying the value.

**Exercise 5 — Asynchronous callback:** Design C `register_callback` + `unregister_callback` + `join_native_thread`. In Java, use `Arena.ofShared()`, a lifecycle owner, and a stop barrier, without closing the arena until C confirms no callbacks remain. This is a **design** exercise, not changing a few lines in the synchronous demo.

**Exercise 6 — Converting `Event` to a Java record:** Define `record EventDto(int id, int x, int y) {}`, read the fields inside the callback, and copy them into the Java DTO. Do not retain the raw `Event*`; allow processing the DTO after the callback returns.

## 19. Checklist Before Shipping a Production FFM Callback

1. Confirm **JDK 22+** (or adjust the API for the target JDK), and grant native access to the right module.
2. Extract the callback signature from the **C header**: return type, parameters, pointer/value, calling convention, and enum/struct widths.
3. Create accurate `FunctionDescriptor`s for both the **upcall callback** and the **downcall C driver**.
4. Ensure the Java target `MethodHandle` matches the exact carrier types and never lets exceptions escape.
5. Create the stub via `Linker.upcallStub` with a clearly owned `Arena`.
6. Pass the stub `MemorySegment` via C's `ADDRESS` parameter, not a Java object or raw JVM pointer.
7. For pointer data, verify `NULL`, byte length, overflow, alignment, struct layout, and native lifetime before calling `reinterpret`/reading.
8. For `void* user_data`, identify the memory/context owner, keep it alive throughout callbacks, and avoid unsynchronized global mutable state.
9. If C passes stack data, **copy it inside the callback** before returning; never leak raw pointers.
10. If C retains the callback long-term, have register/unregister/stop/join/quiescence before closing the arena.
11. If the callback runs across multiple threads, use an appropriate shared arena and ensure callback logic is thread-safe.
12. Check C return values/error codes after downcalls, logging, crash diagnostics, and test with invalid native inputs.
13. Compile the C shared library with exported symbols, use the right OS/architecture, and verify the actual ABI.
14. Do not confuse FFM upcalls with JNI `AttachCurrentThread`, Java `native` declarations, or `JNI_OnLoad`.
15. Run integration tests covering success, `NULL` pointers, wrong lengths, callback errors, and the shutdown path.

## Official References

- [Oracle Java SE 22 — Linker](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Linker.html): `nativeLinker`, `downcallHandle`, `upcallStub`, ABI rules, scope, and notes on exceptions in upcall targets.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): zero-length segments when passing pointers to upcalls, restricted `reinterpret`, `toArray`, `get`, and scope.
- [Oracle Java SE 22 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): describing return/argument layouts.
- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): confined/shared scopes, context allocation, and freeing upcall stubs.
- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): struct layouts, group paths, and byte offsets.
- [Oracle Java SE 22 — SymbolLookup](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SymbolLookup.html): looking up symbols from shared libraries.
- [OpenJDK — JEP 454](https://openjdk.org/jeps/454): FFM API finalized in JDK 22.
