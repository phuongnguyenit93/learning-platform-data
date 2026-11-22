# Caching JNI method/field IDs according to the corresponding class lifecycle

When C/C++ code calls back into a Java method or accesses a Java field via JNI, it usually has to obtain `jmethodID` using `GetMethodID`/`GetStaticMethodID` and `jfieldID` using `GetFieldID`/`GetStaticFieldID`. Repeatedly looking up names and signatures on every call can create unnecessary overhead. **Caching IDs helps reuse lookup results, but an ID is only valid while the class defining that member is still loaded by the JVM.** Class unloading, multiple `ClassLoader`s, and `jclass` management are issues that must be solved together.

This article focuses on how to tie the cache to **the right class identity and the right lifecycle** when Java calls JNI and then JNI calls back into Java. After studying, you should be able to distinguish IDs from object references, choose how to keep a class alive or recreate IDs, design safe initialization/cleanup, and run a Java 17 + C11 example that caches `jmethodID`, `jfieldID`, and class references.

## 1. Why cache and what to cache?

The sequence for calling a Java instance method from JNI normally looks like:

~~~c
jclass cls = (*env)->GetObjectClass(env, object);
if (cls == NULL) return;  /* error or exception */

jmethodID mid = (*env)->GetMethodID(env, cls, "run", "()V");
if (mid == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return;                 /* JNI may have a pending exception */
}

(*env)->CallVoidMethod(env, object, mid);
(*env)->DeleteLocalRef(env, cls);
~~~

This is only an **illustrative snippet**: it assumes `object` is non-null, `env` is the current thread's environment, the caller checks for exceptions after calling, and the method is actually an instance `void run()`. If repeated many times for the same class, `GetMethodID` with the strings `"run"` and `"()V"` can be avoided by storing `mid`.

A proper cache must also answer: **which specific Class object** the ID was obtained from, whether that Class object is still alive, whether threads use the cache concurrently, and who is responsible for destroying the cached data. IDs do not carry ownership of the class by themselves.

| JNI Entity | Role | Is it a JNI object reference? | Lifetime/cleanup |
| --- | --- | --- | --- |
| `jmethodID` | Identifies a method by name + descriptor, used with `Call<Type>Method`/`CallStatic<Type>Method`... | **No** | Valid while the class defining the method has not been unloaded; do not call `DeleteGlobalRef` on an ID |
| `jfieldID` | Identifies a field used with `Get<Type>Field`/`Set<Type>Field`... | **No** | Similar to method ID; there is no `DeleteFieldID` function |
| `jclass` | JNI reference to a `java.lang.Class` object | **Yes** | Local ref is only used within the scope of a JNI call/thread; global ref needs `DeleteGlobalRef`; weak global needs `DeleteWeakGlobalRef` |
| `jobject` | JNI reference to a Java object | **Yes** | Local/global/weak depending on ref type, not a native pointer into object layout |
| `JNIEnv *` | JNI interface of the calling thread | Not an ID or reference to be cached | Only use with the corresponding thread, do not retain across threads |
| `JavaVM *` | JVM-level handle | Not a Java member ID | Can be stored per the JVM contract, used to attach and obtain `JNIEnv *` on an appropriate thread |

**Important rule:** `jmethodID`/`jfieldID` do not keep a class alive; `NewGlobalRef` on a `jclass` can keep `Class<?>` and the associated class loader alive. An ID obtained in the past may still be a non-`NULL` value but **is no longer valid** after class unload.

## 2. Class identity: same name does not necessarily mean same class

In Java, class identity is determined by both **binary name and defining class loader**. Two independent loaders can define two classes with the same name `com.example.Plugin` yet create two different `Class<?>` objects, with different field/method IDs. A cache using only the string `"com/example/Plugin"` as the key is not safe enough.

~~~text
ClassLoader A --> com.example.Plugin (Class A)
                       | GetMethodID("execute", "()I")
                       v
                   methodID A

ClassLoader B --> com.example.Plugin (Class B)
                       | GetMethodID("execute", "()I")
                       v
                   methodID B

Same class name ≠ same Class object / same class lifecycle
~~~

A class is unloaded when the JVM determines that unloading conditions are met. This timing depends on reachability, GC, loader, and VM; **do not assume** a class is unloaded immediately when clearing a Java variable, or that it always stays alive until the process ends.

If a plugin is unloaded and then reloaded, the new `Class<?>` object may bear the old name but is a **different definition**. Never reuse `jmethodID`/`jfieldID` from an unloaded class for a reloaded class. The JNI specification explicitly states that IDs become invalid after the defining class is unloaded.

To avoid confusion between two JNI references pointing to the same class, use `IsSameObject(env, classA, classB)` when comparing identity; do not compare raw C handles with `==` and infer they are different classes, because JNI handles can differ even for the same referent.

### 2.1. Methods and fields also require exact signatures

`GetMethodID(env, clazz, "read", "()I")` finds the **instance** method `int read()`; `GetStaticMethodID` finds a **static** method. `GetFieldID(env, clazz, "count", "I")` finds the instance field `int count`; `GetStaticFieldID` finds a static field.

| Java declaration | JNI descriptor |
| --- | --- |
| `int count` | `I` |
| `long id` | `J` |
| `String name` | `Ljava/lang/String;` |
| `int[] values` | `[I` |
| `void tick()` | `()V` |
| `int add(int a, int b)` | `(II)I` |
| `String describe(long id)` | `(J)Ljava/lang/String;` |

The signature includes both parameter types and **return type**, using the internal name form with `/`, not `.`. `GetMethodID` does not find a static method, and `GetStaticMethodID` is not a "faster" version of instance lookup. When lookup fails, JNI usually returns `NULL` and may raise `NoSuchMethodError` or `NoSuchFieldError`; do not cache a `NULL` ID as if it were successfully initialized.

`GetMethodID`/`GetFieldID` may initialize an uninitialized class, thereby running `<clinit>` and raising initialization errors. Therefore, the cache creation point must be designed to avoid class initialization cycles or calling into an unready state.

## 3. Three lifetime management strategies

### 3.1. Strategy A: cache with strong global `jclass` and explicit release

Keep a struct containing a strong global reference to `Class<?>` along with the IDs:

~~~c
typedef struct {
    jclass class_ref;      /* global reference */
    jfieldID value_field;  /* ID, not jobject */
    jmethodID method;      /* ID, not jobject */
} ClassCache;
~~~

On creation, take the class provided by the caller, resolve the IDs, then create `NewGlobalRef(env, clazz)` and store it in the cache. As long as the global reference is alive, the class is kept reachable, so IDs do not become invalid due to class unloading. When no clients use it anymore: block all calls using the cache, call `DeleteGlobalRef` **exactly once**, then `free` the C struct. After that, never use the IDs or the cache pointer.

Pros: simple and suitable for native handles with a clear lifecycle. Cons: keeps the class/loader alive longer than desired if closed is forgotten; especially dangerous in servers with hot deployment or plugin loaders. Therefore, the lifecycle must **have an owner** (for example `AutoCloseable` and `try-with-resources`) instead of relying on GC.

A common design mistake: storing a global `jclass` in a C static variable and only intending to delete it in `JNI_OnUnload`. A strong global ref can prevent the class loader from becoming collectible, causing `JNI_OnUnload` not to occur as expected. If you want the class/loader to unload, an independent, explicit release mechanism is needed before unloading conditions are met.

### 3.2. Strategy B: weak global `jclass` and re-lookup when the class is no longer alive

`NewWeakGlobalRef` creates a weak global reference that does not keep the object/class alive. Before each use of IDs belonging to that class, try to **promote** the weak ref to a strong local ref using `NewLocalRef`:

~~~c
/* Illustrative snippet: cache->weak_class is a jweak created from the right Class<?>. */
jclass temporary = (jclass)(*env)->NewLocalRef(
    env, (jobject) cache->weak_class);

if (temporary == NULL) {
    /* The class may have been GC'd, or out of memory:
       check for a pending exception, discard old IDs and look up again when
       a valid new Class<?> is available; do not continue calling with old IDs. */
} else {
    /* While temporary is alive, the class is kept alive for this call.
       Only use IDs looked up from this exact class identity.
       Lock/synchronize the cache if there are concurrent invalidation operations. */
    (*env)->DeleteLocalRef(env, temporary);
}
~~~

This snippet **cannot run standalone** and describes the lifetime protocol, not a complete cache implementation. Synchronization, how to re-acquire the class, error checking, and `DeleteWeakGlobalRef` when destroying the registry must be added. The key point is **do not just call `IsSameObject(weakRef, NULL)` and then use the weak ref directly**, because GC can reclaim the referent **between the check and use**. `NewLocalRef` creates a strong reference during the usage window when it succeeds.

A weak cache is appropriate where unloading is a real requirement; in return, the code is more complex and must distinguish "class is no longer alive" from "failed to allocate local ref". Do not transfer an ID from an old class to a new class just because the name/descriptor is the same.

### 3.3. Strategy C: reinitialize IDs per `<clinit>` of each class

A familiar pattern is a `nativeInit` method called in the initializer of a Java class:

~~~java
final class NativeReady {
    static {
        System.loadLibrary("native_ready");
        nativeInit();
    }

    private static native void nativeInit();
}
~~~

This is an **illustrative snippet** and cannot run without the `native_ready` library. `<clinit>` runs for each class definition after it is loaded; if the class unloads and is redefined, the new class's initializer will run again. This pattern can tie the time of ID lookup to the initialization of the **calling class**.

However, **putting all IDs in a single global C static variable** does not automatically create a separate cache per class identity. You must prove that the library and the class have only one corresponding lifecycle, or create a registry keyed by Class object / loader identity, avoiding overwrites and concurrent access. If `jclass` needs to be kept after the initializer call, local/global/weak references must still be managed according to the rules.

## 4. Complete example: Java 17 + JNI, caching by the lifecycle of a native handle

We build `IdCache`. Each Java instance creates **one** native cache for the passed-in `Class<?>`, storing one `jfieldID` for the instance field `value` and one `jmethodID` for the instance method `twice()`. JNI uses the cached IDs to get the field and call back the Java method. `IdCache.close()` properly releases the global reference and native allocation.

This is a pattern that can be built and run on Linux/macOS/Windows with an appropriate compiler, assuming the target platform provides `intptr_t` and a native pointer can be represented in `jlong` (true for common 32/64-bit JDK 17 environments). For exotic architectures or APIs that need to prevent handle spoofing, use a controlled opaque handle table instead of casting pointers to integers.

Directory structure:

~~~text
id-cache-demo/
├── src/
│   └── demo/
│       └── IdCache.java
├── native/
│   └── idcache.c
└── build/
    ├── classes/
    ├── include/
    └── lib/
~~~

### 4.1. Java: owning the cache with `AutoCloseable`

Create the full file `src/demo/IdCache.java`:

~~~java
package demo;

import java.util.Objects;

public final class IdCache implements AutoCloseable {
    static {
        System.loadLibrary("idcache");
    }

    // 0 means not yet created or already closed.
    private long nativeHandle;

    public IdCache(Class<?> targetClass) {
        Objects.requireNonNull(targetClass, "targetClass");
        long opened = nativeOpen(targetClass);
        if (opened == 0L) {
            throw new IllegalStateException("native cache creation failed");
        }
        nativeHandle = opened;
    }

    public synchronized long calculate(Object object) {
        if (nativeHandle == 0L) {
            throw new IllegalStateException("cache is closed");
        }
        Objects.requireNonNull(object, "object");
        return nativeCalculate(nativeHandle, object);
    }

    @Override
    public synchronized void close() {
        long opened = nativeHandle;
        if (opened != 0L) {
            nativeHandle = 0L;
            nativeClose(opened);
        }
    }

    private static native long nativeOpen(Class<?> targetClass);
    private static native long nativeCalculate(long handle, Object object);
    private static native void nativeClose(long handle);

    public static final class Sample {
        private final int value;

        public Sample(int value) {
            this.value = value;
        }

        private int twice() {
            return Math.multiplyExact(value, 2);
        }
    }

    public static void main(String[] args) {
        IdCache cache = new IdCache(Sample.class);
        try (cache) {
            System.out.println(cache.calculate(new Sample(7)));
            System.out.println(cache.calculate(new Sample(11)));
        }

        cache.close(); // closing again is safe
        try {
            cache.calculate(new Sample(1));
        } catch (IllegalStateException expected) {
            System.out.println("closed");
        }
    }
}
~~~

**Lifecycle meaning:** the constructor receives an **actual Class object** (not looking it up by name string), calls `nativeOpen`, and stores the handle; `calculate` and `close` are synchronized on the same instance so it is impossible to use and destroy the same handle concurrently through this public API. `close` sets the handle to 0 and calls cleanup once; calls after close throw `IllegalStateException` before entering JNI. Using `try (cache)` is Java 9+ syntax, valid in Java 17.

`Sample` is a `static final` nested class. JNI can read the `private int value` field and obtain the ID of `private int twice()` (JNI does not perform the same Java source access checks). The class is `final`, avoiding complicating the first lesson with virtual overrides. Java `Math.multiplyExact` throws `ArithmeticException` if multiplication overflows `int`; JNI must respect that pending exception.

**Real-world production:** casting a native pointer to `long` is only a compact handle mechanism for the example. Native code must always control the source of handles, not allow callers to pass arbitrary fake integers, and must have a synchronization/ownership model on every JNI call path. The public Java API here uses synchronized to ensure `close` and `calculate` are sequential **for a single instance**; if developing a public native API for multiple threads/native callbacks, reference-count state or locks on the native side must be added.

### 4.2. C: storing the global class ref and two resolved IDs

First generate the header from Java (full build commands in section 5). The header `build/include/demo_IdCache.h` contains the JNI names verified by the compiler. Create the full file `native/idcache.c`:

~~~c
#include "demo_IdCache.h"
#include <stdint.h>
#include <stdlib.h>

_Static_assert(sizeof(void *) <= sizeof(jlong),
               "This demo needs native pointers to fit in jlong");

typedef struct {
    jclass class_ref;         /* Strong JNI global reference */
    jfieldID value_field;     /* Not a jobject */
    jmethodID twice_method;   /* Not a jobject */
} IdEntry;

static void throw_java(JNIEnv *env, const char *name,
                       const char *message) {
    jclass exception_type = (*env)->FindClass(env, name);
    if (exception_type != NULL) {
        (*env)->ThrowNew(env, exception_type, message);
        (*env)->DeleteLocalRef(env, exception_type);
    }
}

JNIEXPORT jlong JNICALL
Java_demo_IdCache_nativeOpen(JNIEnv *env, jclass owner,
                             jclass target_class) {
    (void) owner;

    if (target_class == NULL) {
        throw_java(env, "java/lang/NullPointerException",
                   "targetClass");
        return 0;
    }

    /* 1. Resolve IDs from the right Class object. */
    jfieldID value_field =
        (*env)->GetFieldID(env, target_class, "value", "I");
    if (value_field == NULL) {
        return 0; /* Usually already has a pending NoSuchFieldError */
    }

    jmethodID twice_method =
        (*env)->GetMethodID(env, target_class, "twice", "()I");
    if (twice_method == NULL) {
        return 0; /* Usually already has a pending NoSuchMethodError */
    }

    /* 2. Class stays alive at least until the cache is closed. */
    jclass keep_class =
        (jclass)(*env)->NewGlobalRef(env, target_class);
    if (keep_class == NULL) {
        if (!(*env)->ExceptionCheck(env)) {
            throw_java(env, "java/lang/OutOfMemoryError",
                       "NewGlobalRef failed");
        }
        return 0;
    }

    /* 3. Only publish the cache when all components are valid. */
    IdEntry *entry = malloc(sizeof *entry);
    if (entry == NULL) {
        (*env)->DeleteGlobalRef(env, keep_class);
        throw_java(env, "java/lang/OutOfMemoryError",
                   "native cache allocation failed");
        return 0;
    }

    entry->class_ref = keep_class;
    entry->value_field = value_field;
    entry->twice_method = twice_method;
    return (jlong)(intptr_t)entry;
}

JNIEXPORT jlong JNICALL
Java_demo_IdCache_nativeCalculate(JNIEnv *env, jclass owner,
                                  jlong handle, jobject object) {
    (void) owner;

    if (handle == 0) {
        throw_java(env, "java/lang/IllegalStateException",
                   "cache is closed");
        return 0;
    }
    if (object == NULL) {
        throw_java(env, "java/lang/NullPointerException",
                   "object");
        return 0;
    }

    IdEntry *entry = (IdEntry *)(intptr_t)handle;
    if ((*env)->IsInstanceOf(env, object, entry->class_ref)
            != JNI_TRUE) {
        throw_java(env, "java/lang/IllegalArgumentException",
                   "object has an incompatible class");
        return 0;
    }

    /* ID obtained once in nativeOpen, reused here. */
    jint value =
        (*env)->GetIntField(env, object, entry->value_field);
    if ((*env)->ExceptionCheck(env)) {
        return 0;
    }

    jint doubled =
        (*env)->CallIntMethod(env, object, entry->twice_method);
    if ((*env)->ExceptionCheck(env)) {
        return 0; /* Preserve the pending Java exception. */
    }

    return (jlong)value + (jlong)doubled;
}

JNIEXPORT void JNICALL
Java_demo_IdCache_nativeClose(JNIEnv *env, jclass owner,
                              jlong handle) {
    (void) owner;
    if (handle == 0) {
        return;
    }

    IdEntry *entry = (IdEntry *)(intptr_t)handle;
    (*env)->DeleteGlobalRef(env, entry->class_ref);
    free(entry);
}
~~~

This is **one complete C file** for the JNI example. The library has no `main`; the JVM calls the three exported JNI functions. Check the header generated by `javac -h` and do not rename Java classes/methods without recompiling C.

Notable decisions:

1. **Lookup before publishing:** if `GetFieldID`/`GetMethodID` fails, do not store a half-built cache. `NULL` is an error signal, not an ID to retry on call.
2. **Global class ref:** `NewGlobalRef` promotes this call's class reference to a strong global; the cache keeps it for the entire time the two IDs are allowed to be used. After `DeleteGlobalRef`, there is no longer permission to use the IDs through that cache.
3. **Do not ref-count IDs:** IDs are managed by the JVM; do not `free`, do not `NewGlobalRef`, and do not `DeleteLocalRef` directly on `jmethodID`/`jfieldID`.
4. **Object type check:** `IsInstanceOf` uses the **cached Class object**, not looking it up again by name. Check `object == NULL` first, because according to JNI a null reference can be cast to any class (so `IsInstanceOf` alone is not enough to catch null).
5. **Pending exception:** `CallIntMethod` can run Java code that throws an exception. After encountering an exception, return early so Java sees the original exception; do not replace it with a `0` value as a successful result.
6. **Do not cache `JNIEnv *`:** each native call receives the env of the right thread; the struct only contains the global class and two IDs.
7. **Native lifecycle:** `free(entry)` is placed after `DeleteGlobalRef`, exactly once; Java synchronized methods protect against close while calculation is running via the public API.

Regarding the handle type: `intptr_t` represents a pointer as an integer on common targets; combining the cast `(jlong)(intptr_t)` is a demo pattern bounded by `_Static_assert`. The handle value **is not** a Java object reference and is not automatically freed by GC. On platforms that do not support `intptr_t`, it must be replaced with another handle mechanism and ABI compatibility must be checked.

## 5. Building and running in practice

Set `JAVA_HOME` to point to an appropriate JDK and use a compiler matching the JVM architecture. Run the commands from the `id-cache-demo` directory.

### 5.1. Linux (GCC/Clang, C11)

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/IdCache.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  native/idcache.c -o build/lib/libidcache.so

java -Djava.library.path=build/lib \
  -cp build/classes demo.IdCache
~~~

### 5.2. macOS (Clang)

~~~sh
mkdir -p build/classes build/include build/lib
javac -h build/include -d build/classes src/demo/IdCache.java

cc -std=c11 -O2 -Wall -Wextra -Wpedantic -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  native/idcache.c -o build/lib/libidcache.dylib

java -Djava.library.path=build/lib \
  -cp build/classes demo.IdCache
~~~

### 5.3. Windows x64 (MSVC Developer Command Prompt)

~~~bat
mkdir build\classes
mkdir build\include
mkdir build\lib
javac -h build\include -d build\classes src\demo\IdCache.java

cl /nologo /W4 /O2 /LD ^
  /I"%JAVA_HOME%\include" ^
  /I"%JAVA_HOME%\include\win32" ^
  /I"build\include" ^
  native\idcache.c ^
  /link /OUT:build\lib\idcache.dll

java -Djava.library.path=build\lib -cp build\classes demo.IdCache
~~~

The Windows commands above are for **Command Prompt**, with `^` as line continuation; use `cl` from the Visual Studio Developer Command Prompt and a JDK of the matching architecture. Depending on the compiler, warnings from system headers vary; what matters most is compiling/linking successfully and running the JNI functions properly. If `JAVA_HOME` is not set, configure the environment before building.

With Java 17+, the pure Java code and the two computing native functions behave as follows:

~~~text
21
33
closed
~~~

On the first call, `value = 7`, `twice() = 14`, JNI returns `7 + 14 = 21`. On the second call, `11 + 22 = 33`. After `try (cache)`, Java automatically calls `close()`; calling `close()` again does not double-free, and then `calculate` throws `IllegalStateException` and prints `closed`. The stdout above does not include build/compiler messages on stderr.

### 5.4. Checking symbols and signatures

~~~sh
javap -s -classpath build/classes demo.IdCache
nm -D --defined-only build/lib/libidcache.so
~~~

On Linux, the dynamic symbols table should contain three names:

~~~text
Java_demo_IdCache_nativeOpen
Java_demo_IdCache_nativeCalculate
Java_demo_IdCache_nativeClose
~~~

On macOS, you can check with `nm -gU build/lib/libidcache.dylib` (the tool may prepend `_` before symbol names). On Windows, check with `dumpbin /exports build\lib\idcache.dll`. If the method name or Java package changes, regenerate the header and rebuild the library; do not manually edit the generated header.

## 6. Why does this example keep IDs valid for the right lifecycle?

Lifecycle of one instance:

~~~text
new IdCache(Sample.class)
    |
    | GetFieldID / GetMethodID -> IDs for the current Sample.class
    | NewGlobalRef(Sample.class) -> class is kept alive
    | malloc(IdEntry) -> store strong ref + 2 IDs
    v
cache OPEN
    |
    | calculate(...): retrieve IDs from the same IdEntry
    | IsInstanceOf(..., class_ref)
    | GetIntField + CallIntMethod
    v
close()
    |
    | synchronized so there is no concurrent calculate on the same instance
    | nativeHandle = 0
    | DeleteGlobalRef(class_ref)
    | free(IdEntry)
    v
cache CLOSED -> do not call with old IDs
~~~

During `OPEN`, the strong global ref guarantees the class is not unloaded merely because there are no other Java references. IDs are therefore valid when the methods are called. During `CLOSED`, Java forbids using the handle; the native entry has been freed. The class can become eligible for unloading when all other references are gone (with no promise that it will unload immediately).

The example intentionally **does not keep the cache alive until `JNI_OnUnload`**: calling `close` independently allows the strong global reference to disappear before the classloader needs to be GC'd. When using this pattern in a server, clean up each instance, especially before unloading a plugin or stopping a module.

It is also important to distinguish: the JVM may update a method's internal representation via JIT optimizations, but that does not cause an ID cached for the right class to spontaneously become invalid while the class is still alive. The class lifetime condition is the normal JNI contract; special operations such as instrumentation/redefinition require adhering to additional relevant tool contracts.

## 7. Subtle details that easily cause bugs

### 7.1. Local `jclass` must not be used after the native method returns

~~~c
/* WRONG: cls is a local reference, invalidated after the current call. */
static jclass cached_class;

JNIEXPORT void JNICALL Java_demo_Example_save(JNIEnv *env,
                                              jclass owner) {
    (void) env;
    cached_class = owner;
}
~~~

This snippet only illustrates a bug; it is not code to run. `owner` is a local ref given by the JVM for the static native call. Assigning it to a C static only copies the handle, **not converting** it to global. After the JNI call ends, reusing the handle is wrong even if the class has not unloaded. If you really must keep a class across multiple calls, use `NewGlobalRef` and destroy it with `DeleteGlobalRef` when no longer used.

### 7.2. IDs are different from references and cannot be freed with the JNI ref API

~~~c
jmethodID id = (*env)->GetMethodID(env, clazz, "twice", "()I");
/* Do not do the following:
   (*env)->NewGlobalRef(env, (jobject) id);
   (*env)->DeleteGlobalRef(env, (jobject) id);
*/
~~~

`jmethodID`/`jfieldID` are opaque IDs whose representation is decided by the JVM. Do not cast them to `jobject` to "keep alive", do not `free` them, and do not manipulate them as pointers to JVM structures. Only pass them as arguments to JNI APIs that accept the corresponding ID while the defining class is still valid.

### 7.3. Do not cache solely by class name string

If a C registry stores `"com.example.Plugin" -> jmethodID`, a new plugin loader might receive an ID belonging to an old class loader. The registry should tie the ID to a specific **Class object identity** and lifetime token/handle; using `IsSameObject` to compare classes avoids depending on local reference addresses.

With a weak cache, if the weak Class ref has been reclaimed, you must discard the old ID and recreate the cache for the new Class, not just update the `jclass` slot. With a strong cache, there must be explicit cleanup so the old class loader is not pinned forever. These patterns are different design choices; do not mix them and hope GC handles it automatically.

### 7.4. `FindClass` may pick an unintended loader

`FindClass(env, "com/example/Plugin")` depends on the class loader context of the native frame, and rules differ when called from `JNI_OnLoad` or an attached native thread. In a plugin/server environment, looking up a class by name may return the wrong class or `ClassNotFoundException` even though the class is in another loader.

An easily verifiable approach is for **Java to pass the actual `Class<?>`** down to native during cache creation, like `IdCache(Sample.class)`; when looking up a class by name is necessary, specify the right loader and use an appropriate Java `ClassLoader.loadClass` mechanism. This is especially important if a C thread attaches itself to the JVM and calls back into classes defined by a custom loader.

### 7.5. Do not use the cache after close, not even a single instruction

A `jmethodID` is not automatically "zeroed out" when the class reference is destroyed. After `DeleteGlobalRef` and `free`, the old C pointer may still contain old bytes; dereference/use-after-free is a severe native bug. `nativeHandle = 0` in Java prevents subsequent calls through this wrapper, but **if you have distributed the handle elsewhere**, it is not enough to prevent races. When adding asynchronous callbacks or native worker threads, you must design the order to stop work, wait for in-flight calls to complete, and only then free; you can use mutexes, reference counting, or generation-based handles.

### 7.6. Thread safety of the cache and `JNIEnv *`

IDs and strong global refs can be used across multiple threads when the lifetime is right, but **`JNIEnv *` belongs only to the thread on which it was obtained**. If calling back on a native worker thread, attach via the Invocation API and obtain that thread's own env; do not retain a `JNIEnv *` received from an earlier Java call.

In the example, `synchronized` on the Java instance protects the read/close sequence of the same cache. `GetFieldID` and `GetMethodID` are performed once in the constructor, and the struct is only published after both the IDs and the global class ref are valid. Do not concurrently mutate fields of the cache struct that other threads read without synchronization. JNI APIs do not automatically resolve data races in your C structures.

### 7.7. Class initialization and lookup exceptions

`GetFieldID`/`GetMethodID` may trigger class initialization. If `<clinit>` throws an exception, native code must abort cache creation and let the exception return to Java. Do not continue running `Call<Type>Method` or `NewGlobalRef` arbitrarily when JNI has a pending exception.

In the example, `nativeOpen` only publishes `IdEntry` after lookups succeed and the global reference is created. If `malloc` fails after `NewGlobalRef`, the code deletes the global ref right before throwing the error. There is no path that intentionally keeps a half-initialized cache.

## 8. When to choose which strategy?

| Context | Reasonable approach | Issues to manage |
| --- | --- | --- |
| Simple application, one class exists for nearly the entire JVM lifetime | `<clinit>` calls native init, caches IDs per corresponding class | Avoid shared static C cache across wrong loaders, verify cleanup |
| Native resource with clear `open/close`, caller actively owns it | Struct containing strong global `jclass` + IDs, `AutoCloseable` | Must close; class is kept alive while cache is open |
| Module/plugin requiring frequent hot unloading | Class-keyed registry without holding long-term strong refs, possibly weak refs | Revalidate and rebuild IDs, synchronize with GC/unload |
| Native callbacks invoked across multiple threads | Cache immutable IDs per class + global/strong local ref with proper lifetime | Do not cache `JNIEnv *`; attach/detach and lock on shutdown |
| Multiple defining loaders with the same class name | Cache keyed by Class identity/loader context | Do not use class name as unique key; avoid stale IDs |

**Choose a strong cache when you have an reliably enforced close point.** Choose weak/recompute when unloading is a functional requirement and you are ready to handle extra synchronization and races with GC. For systems using `JNI_OnLoad`/`JNI_OnUnload`, carefully analyze whether global class references pin the loader, avoiding circular dependency designs where unloading never happens.

## 9. Sequential verification exercises

1. **Check cache and output.** Run the example above, confirm stdout has three lines `21`, `33`, `closed`. Confirm `javac -h` generates `demo_IdCache.h` and the native library exports all three functions.
2. **Check wrong object type.** In Java, call `cache.calculate("hello")` while the cache is open. Native `IsInstanceOf` rejects it and reports `IllegalArgumentException`; the class/IDs remain valid for continued use if the caller catches the error.
3. **Check field name error.** In C change `"value"` to `"missing"`, rebuild; `GetFieldID` returns `NULL` and Java will receive the corresponding error. Do not let the constructor create a cache with an invalid ID.
4. **Check method signature.** In C change `"()I"` to `"()J"` while keeping the Java method returning `int`, rebuild; the lookup will mismatch. Restore the right descriptor before finishing.
5. **Check close.** Place a `cache.calculate(...)` call after `close`; it must receive `IllegalStateException` in Java, not fall into the native function using a freed pointer.
6. **Try two caches.** Open two `IdCache(Sample.class)` instances and close them one by one. Each instance has its own native global reference; closing one cache does not invalidate the still-open cache. When all are closed, no global refs owned by these two caches remain.
7. **Observe loader identity.** With two custom `ClassLoader`s actually defining two classes with the same name, try designing a cache for each separate `Class<?>`. Do not transfer handles/IDs between the two classes; compare identity with `IsSameObject` or on the Java side with `==` on `Class<?>`.

During debugging, use `java -Xcheck:jni -Djava.library.path=build/lib -cp build/classes demo.IdCache` (some JNI checks are enabled by the JVM). This tool **does not** fully detect all C memory lifetime bugs and does not turn an invalidated ID into a valid one. For complex native code, use a C debugger and sanitizers supported on the target compiler.

## 10. Checklist before caching JNI in production

- **Class identity:** Which specific `Class<?>` does the cache belong to? Are there multiple `ClassLoader`s or hot reload? Is the key the class object or just the name?
- **Member metadata:** Do the method/field name, descriptor, static/instance, and `Call<Type>...` or `Get<Type>...` type match strictly?
- **Lifetime:** Is the defining class kept alive by a clearly scoped strong ref, or is there a weak ref + method to re-lookup IDs? Is the ID still valid at call time?
- **Reference category:** Which `jclass` local/global/weak is it? Are `NewGlobalRef`/`DeleteGlobalRef` or `NewLocalRef`/`DeleteLocalRef` properly paired? Are IDs not treated as `jobject`?
- **Initialization:** Is the cache published only after all lookups succeed? Are pending exceptions, `NULL`, `malloc` failures, or possible class initialization failures handled?
- **Cleanup:** Is there a `close`/destroy mechanism independent of `JNI_OnUnload`? Who stops callback/worker threads and waits for active calls before freeing? Is double-close safe?
- **Threading:** Is the right `JNIEnv *` used on each thread, are there no races between lookup/invalidation/use/free, and are local refs not held past their lifetime?
- **Verification:** Are null, wrong class, missing field/method, close-after-use, multi-instance, custom ClassLoader, and class unload/reload tested when the environment supports it?

A proper JNI cache must maintain the invariant:

> **No `jmethodID` or `jfieldID` may be used without guaranteeing that the ID's defining class is still alive, and no JNI object reference may be retained beyond the scope of its reference type.**

If you cannot prove this invariant with your current caching approach, merely optimizing lookups will create a class unloading bug that is far harder to reproduce than the original lookup cost.

### Standard reference documentation

- Oracle, [JNI Specification — Design Overview](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html): `Accessing Fields and Methods`, noting that IDs do not prevent class unloading, and local/global references.
- Oracle, [JNI Specification — Functions](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html): `GetMethodID`, `GetFieldID`, `NewGlobalRef`, `DeleteGlobalRef`, `NewWeakGlobalRef`, `NewLocalRef`, `IsInstanceOf`, and `ExceptionCheck`.
- Android Developers, [JNI tips](https://developer.android.com/ndk/guides/jni-tips): examples on caching IDs, class initialization, global refs, and class loaders (JNI principles should be placed in platform context).
