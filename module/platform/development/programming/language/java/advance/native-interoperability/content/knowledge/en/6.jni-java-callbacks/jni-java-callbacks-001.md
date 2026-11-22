# Finding Classes with `FindClass` and the Impact of Class Loader Context in JNI

## 1. The problem: the class name is correct, yet JNI still cannot find it

When C/C++ needs to call a Java method, read a field, or create an object via JNI, native code usually starts with:

~~~c
jclass clazz = (*env)->FindClass(env, "com/example/Service");
~~~

`FindClass` does not look up a global list of classes for the entire JVM. It uses the **class loader context** associated with where the JNI call originates. Therefore, the `com.example.Service` class may exist in the process, yet `FindClass` still fails to find it because the selected loader cannot see that class definition. Conversely, multiple loaders can define classes with the **same name** but **different type identities**.

This is a critical issue when Java calls native code to interact back with Java, especially in applications with plugins, custom `URLClassLoader`s, OSGi, application servers, Android, and self-created **native worker threads**.

Lesson objectives:

- Use the correct `FindClass` syntax, check `jclass`, and handle exceptions.
- Explain which loader JNI selects when called from a native method, `JNI_OnLoad`, `JNI_OnUnload`, and a self-attached native thread.
- Distinguish the loader declaring a native method from the **thread context class loader (TCCL)**.
- Run a Java 17+ example with a custom loader to demonstrate class lookup results.
- Use `Class<?>`, `GetObjectClass`, `ClassLoader.loadClass`, or a global reference when a specific loader is needed.
- Avoid caching local references with the wrong lifetime and confusing two classes with the same name from two loaders.

## 2. `FindClass` API contract

JNI C declaration:

~~~c
jclass FindClass(JNIEnv *env, const char *name);
~~~

**C** and **C++** calls differ in syntax:

~~~c
// C, inside a JNI function with JNIEnv *env:
jclass cls = (*env)->FindClass(env, "java/lang/String");
~~~

~~~cpp
// C++, inside a JNI function with JNIEnv *env:
jclass cls = env->FindClass("java/lang/String");
~~~

The `name` parameter is a **JNI internal name**, encoded in Modified UTF-8. Class names use `/` instead of `.`; array names use descriptor syntax.

| Type in Java | Name passed to `FindClass` |
| --- | --- |
| `java.lang.String` | `"java/lang/String"` |
| `com.example.Service` | `"com/example/Service"` |
| `com.example.Outer.Inner` (nested class) | `"com/example/Outer$Inner"` |
| `int[]` | `"[I"` |
| `java.lang.String[]` | `"[Ljava/lang/String;"` |
| `java.lang.String[][]` | `"[[Ljava/lang/String;"` |

Do not pass `"com.example.Service"` to `FindClass` for a regular class; that is the dotted name used by Java APIs such as `ClassLoader.loadClass`. Do not use `"int"` to get the `Class` of primitive `int`; you can pass `int.class` from Java if needed.

**On success:** the function returns a `jclass`, which is a JNI reference to a Java object of type `java.lang.Class`. It is a **local reference**, not a C/C++ pointer to an internal class structure.

**On failure:** the function returns `NULL` and usually leaves a pending Java exception/error, such as `NoClassDefFoundError`. The specification also lists `ClassFormatError`, `ClassCircularityError`, and `OutOfMemoryError` in other cases. Do not assume every `NULL` is due to a wrong name; consider the loader, dependencies, and class initialization errors.

Basic handling snippet (placed inside a JNI function returning `void`, not a standalone program):

~~~c
jclass target = (*env)->FindClass(env, "com/example/Target");
if (target == NULL) {
    // Do not use target. If there is a pending exception,
    // let it propagate to Java or handle it intentionally.
    return;
}

/* Use target to look up method/field ... */
(*env)->DeleteLocalRef(env, target);
~~~

If `target == NULL`, do not proceed to call `GetMethodID`/`NewObject` with that reference. Only clear a pending exception with `ExceptionClear` when there is an actual recovery branch; clearing it unconditionally loses the root cause of the error.

## 3. Which loader is used?

The JNI specification defines the **loader by context**, as follows:

| Context calling `FindClass` | Loader selected by JNI | What to remember |
| --- | --- | --- |
| Inside a native method called by Java | Loader of the **class declaring the current native method** | Usually finds classes belonging to the same application/plugin as the class declaring the native method |
| Inside `JNI_OnLoad` or `JNI_OnLoad_L` | Loader of the class loading the native library | Suitable for finding and caching classes before native workers run |
| Inside `JNI_OnUnload` or `JNI_OnUnload_L` | **System class loader** | The loader used during load may no longer exist |
| Self-created native thread, after `AttachCurrentThread`, with no Java native method as context | Invocation Interface rule: **system class loader** | May not see plugin-private classes |
| C/C++ application embedding the JVM via the Invocation Interface | **System class loader** if there is no current native method | Does not search in any custom loader by default |

When called inside a native method, the key point is the **loader of the class declaring the native method itself**, not the loader of an arbitrary object passed to the function. There may be another Java caller outside, but the rule is determined by the current native method.

### 3.1. TCCL does not automatically control `FindClass`

Java supports:

~~~java
Thread.currentThread().setContextClassLoader(pluginLoader);
~~~

Many frameworks actively use the **Thread Context ClassLoader** to find classes or resources. However, JNI `FindClass` does not automatically switch to `pluginLoader` just because TCCL changes. A native method of a class defined by the **system loader** still uses the loader according to that native method's context.

Conversely, a native method of `plugin.Bridge` (defined by a custom loader) can still succeed with `FindClass("plugin/Target")` when TCCL points to the system loader. The following runnable example demonstrates this exact behavior.

## 4. Java 17+ example: proving `FindClass` uses the native method's loader

Set up three classes:

- `Launcher`: only on the application classpath, loaded by the system/application loader.
- `plugin.Bridge`: class containing the native method, loaded by a **separate `URLClassLoader`**.
- `plugin.Target`: class to find, located in the same custom loader as `Bridge`.

C code calls `FindClass("plugin/Target")` inside `Bridge`'s native method and returns `Class<?>` to Java. Java prints the name, identity, and actual loader to verify.

### 4.1. Source layout

~~~text
findclass-lab/
├── Launcher.java
├── plugin-src/
│   └── plugin/
│       ├── Bridge.java
│       └── Target.java
└── native/
    └── bridge.c

After building:
├── host/Launcher.class
├── plugin-classes/plugin/Bridge.class
├── plugin-classes/plugin/Target.class
├── native/plugin_Bridge.h
└── libfindclass_lab.so | libfindclass_lab.dylib | findclass_lab.dll
~~~

Keep `plugin-classes` **outside** `Launcher`'s application classpath. This path separation is a prerequisite of the experiment.

### 4.2. `plugin-src/plugin/Target.java`

~~~java
package plugin;

public final class Target {
    private Target() {
    }
}
~~~

No methods or fields are needed in `Target`. We only look up the `Class` object and the loader that defined this class.

### 4.3. `plugin-src/plugin/Bridge.java`

~~~java
package plugin;

public final class Bridge {
    static {
        System.loadLibrary("findclass_lab");
    }

    private Bridge() {
    }

    public static native Class<?> lookupTarget();
}
~~~

`System.loadLibrary("findclass_lab")` takes the **logical name** of the library and loads the OS-specific file (Linux: `libfindclass_lab.so`; macOS: `libfindclass_lab.dylib`; Windows: `findclass_lab.dll`). `lookupTarget` has a Java return type of `Class<?>`, represented by `jclass` in the generated JNI header.

### 4.4. `Launcher.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class Launcher {
    public static void main(String[] args) throws Exception {
        boolean appCanSeeTarget;
        try {
            Class.forName("plugin.Target");
            appCanSeeTarget = true;
        } catch (ClassNotFoundException ex) {
            appCanSeeTarget = false;
        }

        URL pluginUrl = Path.of("plugin-classes")
                .toAbsolutePath()
                .toUri()
                .toURL();

        try (URLClassLoader pluginLoader = new URLClassLoader(
                new URL[] {pluginUrl},
                ClassLoader.getPlatformClassLoader())) {

            // TCCL is the system loader, not pluginLoader.
            Thread.currentThread().setContextClassLoader(
                    ClassLoader.getSystemClassLoader());

            Class<?> bridge = Class.forName(
                    "plugin.Bridge", true, pluginLoader);

            Class<?> found = (Class<?>) bridge
                    .getMethod("lookupTarget")
                    .invoke(null);

            Class<?> explicitlyLoaded = Class.forName(
                    "plugin.Target", false, pluginLoader);

            System.out.println(
                    "App loader sees plugin.Target: " + appCanSeeTarget);
            System.out.println("FindClass result: " + found.getName());
            System.out.println(
                    "Resolved by plugin loader: "
                            + (found.getClassLoader() == pluginLoader));
            System.out.println(
                    "Matches explicit lookup: "
                            + (found == explicitlyLoaded));
            System.out.println(
                    "TCCL is plugin loader: "
                            + (Thread.currentThread()
                                    .getContextClassLoader() == pluginLoader));
        }
    }
}
~~~

`Launcher` loads `Bridge` via reflection because it has no compile-time dependency on the plugin class. `URLClassLoader` uses the **platform loader as its parent**, so the plugin can see standard Java APIs without automatically picking up classes that are only on the application classpath. `plugin.Target` exists only in `plugin-classes` managed by the URLClassLoader.

`Class.forName("plugin.Target")` without passing a loader in `Launcher` uses the loader associated with `Launcher`; under this layout it will throw `ClassNotFoundException`. The call `Class.forName("plugin.Target", false, pluginLoader)` looks up the class with an **explicit loader**.

### 4.5. Generating the header and writing the C code

Before compiling, create the output directories. On Linux/macOS:

~~~bash
mkdir -p host plugin-classes native
~~~

On Windows CMD, inside the `findclass-lab` directory:

~~~bat
mkdir host
mkdir plugin-classes
mkdir native
~~~

Run with **JDK 17 or higher** (Linux/macOS):

~~~bash
javac -d host Launcher.java
javac -h native -d plugin-classes \
  plugin-src/plugin/Bridge.java \
  plugin-src/plugin/Target.java
~~~

Windows CMD (same effect):

~~~bat
javac -d host Launcher.java
javac -h native -d plugin-classes plugin-src\plugin\Bridge.java plugin-src\plugin\Target.java
~~~

`javac -h native` generates **`native/plugin_Bridge.h`**. The prototype in the header is equivalent to:

~~~c
JNIEXPORT jclass JNICALL Java_plugin_Bridge_lookupTarget(
        JNIEnv *, jclass);
~~~

Create the complete **`native/bridge.c`** file:

~~~c
#include "plugin_Bridge.h"

JNIEXPORT jclass JNICALL Java_plugin_Bridge_lookupTarget(
        JNIEnv *env, jclass declaringClass) {
    (void) declaringClass;

    // Local reference is returned to Java as Class<?>.
    return (*env)->FindClass(env, "plugin/Target");
}
~~~

`JNI_OnLoad` is not needed in this example. `FindClass` runs **inside a native method of `plugin.Bridge`**, so `Bridge`'s loader is used. If the class is not found, the JVM reports the error when the call returns to Java; the demonstration intentionally preserves the original error cause.

### 4.6. Compiling the library

Set `JAVA_HOME` to the **JDK root directory** containing `include/jni.h`, and choose a compiler with the same architecture as the JVM (x64/ARM64...). Run **one** of the three command groups:

**Linux, GCC or Clang:**

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  native/bridge.c -o libfindclass_lab.so
~~~

**macOS, Clang:**

~~~bash
cc -std=c11 -Wall -Wextra -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  native/bridge.c -o libfindclass_lab.dylib
~~~

**Windows x64, x64 Native Tools Command Prompt for Visual Studio:**

~~~bat
cl /nologo /W4 /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" native\bridge.c /link /OUT:findclass_lab.dll
~~~

The library file is created in the `findclass-lab` root directory, where the JVM is run in the next step. Do not use a shared library of a different architecture or OS than the JVM.

### 4.7. Running and exact output

From the `findclass-lab` directory:

~~~bash
java -Djava.library.path=. -cp host Launcher
~~~

Expected stdout with the proper build and classpath:

~~~text
App loader sees plugin.Target: false
FindClass result: plugin.Target
Resolved by plugin loader: true
Matches explicit lookup: true
TCCL is plugin loader: false
~~~

Explanation:

1. **`false`:** `Launcher`'s application loader does not see `plugin.Target` because `-cp` only contains `host`.
2. **`plugin.Target`:** `FindClass` inside the native method finds the `Target` class.
3. **`true`:** `pluginLoader` itself defined the class returned by JNI.
4. **`true`:** Java looks up the class via `pluginLoader` explicitly and receives the **same `Class<?>` object**.
5. **`false`:** TCCL is not the plugin loader, yet `FindClass` still succeeds; this refutes the assumption that JNI always uses TCCL.

If you accidentally add `plugin-classes` to the application's `-cp`, the experiment results will differ because the application loader will also see `Target`. Keeping the classes in the proper directories isolates the two loaders.

### 4.8. Reviewing the JNI flow

~~~text
Launcher.class  (application/system loader)
      |
      | creates a separate URLClassLoader
      v
pluginLoader --> plugin.Bridge + plugin.Target
      |
      | Class.forName("plugin.Bridge", true, pluginLoader)
      v
Bridge.<clinit> --> System.loadLibrary("findclass_lab")
      |
      | Bridge.lookupTarget() via reflection
      v
JVM calls Java_plugin_Bridge_lookupTarget(JNIEnv*, jclass)
      |
      | FindClass("plugin/Target")
      | JNI gets the loader of the class declaring the native method: Bridge
      v
pluginLoader finds Target
      |
      v
JNI returns jclass --> Java receives Class<?> --> getClassLoader() == pluginLoader
~~~

`FindClass` returns a **class object**, not an instance created via `new Target()`. To invoke methods/constructors, native code also needs `GetMethodID`/`GetStaticMethodID` and the appropriate `Call*Method`/`NewObject` calls. `JNIEnv *` and `jclass` in the JNI signature are parameters **added by the JVM**, and do not appear in Java's `lookupTarget()` declaration.

## 5. Self-attached native threads: why can the result differ?

A common failure scenario:

1. Java calls a native library.
2. The C/C++ library creates its own OS thread using a mechanism such as `pthread_create` or an OS thread API.
3. That thread calls `JavaVM->AttachCurrentThread` to use JNI and obtain its own thread-local `JNIEnv *`.
4. The thread calls `FindClass("plugin/Target")` **without a current Java native method as context**.
5. JNI uses the Invocation Interface rule, usually the **system class loader**; this loader may not see classes that only reside in a plugin loader.

Diagram:

~~~text
Java Bridge.startWorker() --> native creates OS thread
                                         |
                                         v
                              AttachCurrentThread
                                         |
                                         v
                                 Separate JNIEnv*
                                         |
                                         v
                         FindClass("plugin/Target")
                                         |
                       no Bridge native method
                                         |
                                         v
                               system class loader
                                         |
                            plugin.Target is absent
                                         |
                                         v
                         NULL / definition lookup error
~~~

**Not every different thread fails.** When a regular **Java thread** calls `Bridge.lookupTarget()` directly, JNI still has `Bridge`'s native method context, so the Bridge loader continues to be used. The failure occurs specifically with a **self-attached** native thread when there is no suitable Java/native method context.

`JNIEnv *` is a **per-thread** interface pointer; do not pass a `JNIEnv *` from thread A to thread B. You can keep `JavaVM *` to attach/detach as needed. A self-attached thread must follow `DetachCurrentThread` before terminating per the Invocation API. Even a successful attach **does not** automatically make an old plugin's loader the default loader.

### 5.1. Three ways to fix it

- **Pass `Class<?>` from Java** into JNI if Java knows the exact type to handle.
- **Pass the right `ClassLoader`** and call `loadClass` via JNI when the class name is only known at runtime.
- **Look up the class in the right context**, such as `JNI_OnLoad` or a plugin native method, and hold the `jclass` with `NewGlobalRef` for use in worker threads.

Do not just change TCCL and assume `FindClass` will pick that loader. TCCL can be used for **Java logic that selects a loader itself**, but JNI `FindClass` has its own rules.

## 6. `JNI_OnLoad` is an important exception

`JNI_OnLoad` is an optional hook called by the JVM when loading a JNI library. According to the specification, `FindClass` running inside this hook uses the **class loader of the class that loaded the library**. If `plugin.Bridge` calls `System.loadLibrary`, then `JNI_OnLoad` typically sees `plugin.Target`.

This is convenient for caching classes for later use. The following snippet **illustrates the caching technique** and does not need to be added to the experiment's `native/bridge.c` if the lifecycle is not yet designed:

~~~c
#include <jni.h>

static jclass g_target_class = NULL;

JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    (void) reserved;

    JNIEnv *env = NULL;
    if ((*vm)->GetEnv(
            vm, (void **) &env, JNI_VERSION_1_6) != JNI_OK) {
        return JNI_ERR;
    }

    jclass local = (*env)->FindClass(env, "plugin/Target");
    if (local == NULL) {
        return JNI_ERR;
    }

    g_target_class = (jclass) (*env)->NewGlobalRef(env, local);
    (*env)->DeleteLocalRef(env, local);

    if (g_target_class == NULL) {
        return JNI_ERR;
    }

    return JNI_VERSION_1_6;
}
~~~

Here:

- `local` is a **local reference** from `FindClass`; do not store it in a global variable for use after the function returns.
- `NewGlobalRef` creates a **global reference** valid across multiple JNI calls and attached threads until it is deleted.
- `DeleteLocalRef` frees the newly created local reference.
- `DeleteGlobalRef` must be called at a **controlled cleanup point** when it is certain no threads are still using it.
- A strong global reference keeps the Java `Class` alive, which can prevent the class loader from being GC'd/unloaded. Therefore, do not blindly expect `JNI_OnUnload` to clean up a reference that is blocking the unload itself.

`JNI_OnUnload` uses a different loader context and may run when the original loader no longer exists. Avoid relying on `FindClass` inside `JNI_OnUnload` still seeing the plugin's classes.

## 7. How to select a class loader explicitly in JNI

### 7.1. Pass `Class<?>` or an object from Java

If Java already knows the target class, let Java pass the class object itself:

~~~java
// Illustrative interface, not a complete program.
public static native void processType(Class<?> type);
public static native void processValue(Object value);

// Call from a place where the right class is visible:
processType(plugin.Target.class);
processValue(targetInstance);
~~~

When JNI receives a Java `Class<?>`, native code can use it as a `jclass` to look up methods/fields of that exact type. If it receives a regular object, `GetObjectClass(env, obj)` returns the runtime `jclass` of that object; there is no need for `FindClass` by name.

**Benefit:** the class reference is determined precisely by the loader that created that object. There is no need to guess names, loaders, or rely on whether the system loader can see it.

### 7.2. Pass `ClassLoader` and call `loadClass`

If runtime needs to look up a class by name but the right loader is only known in Java, pass the `ClassLoader` object into native code and call `ClassLoader.loadClass(String)`. Illustrative C helper (assumes `loader` is non-null, and the caller handles Java exceptions):

~~~c
#include <jni.h>

static jclass load_with_loader(JNIEnv *env, jobject loader) {
    if (loader == NULL) {
        return NULL;
    }

    jclass loader_type = (*env)->GetObjectClass(env, loader);
    if (loader_type == NULL) {
        return NULL;
    }

    jmethodID load_method = (*env)->GetMethodID(
            env,
            loader_type,
            "loadClass",
            "(Ljava/lang/String;)Ljava/lang/Class;");

    (*env)->DeleteLocalRef(env, loader_type);
    if (load_method == NULL) {
        return NULL;
    }

    // ClassLoader.loadClass requires a dotted name.
    jstring name = (*env)->NewStringUTF(env, "plugin.Target");
    if (name == NULL) {
        return NULL;
    }

    jobject result = (*env)->CallObjectMethod(
            env, loader, load_method, name);
    (*env)->DeleteLocalRef(env, name);

    // Returns a local reference; NULL may be accompanied by a Java exception.
    return (jclass) result;
}
~~~

**Name distinction:** `FindClass("plugin/Target")` uses slashes, whereas `ClassLoader.loadClass("plugin.Target")` takes a dotted binary name. The descriptor of the Java method `ClassLoader.loadClass(String)` is `(Ljava/lang/String;)Ljava/lang/Class;`. If the loader cannot find the class, the Java call may throw **`ClassNotFoundException`**; `CallObjectMethod` leaves that exception pending.

`ClassLoader.loadClass` does not initialize the class immediately by default. If explicit initialization is needed, Java code can use `Class.forName(name, true, loader)` with the chosen loader.

### 7.3. Caching global references, method IDs, and lifecycle

The `jclass` returned by `FindClass`/`GetObjectClass` is a **local JNI reference**. After the native method returns, a local reference that has not been converted to global is **no longer valid** for use across other callbacks.

To reuse it multiple times:

1. Obtain `jclass` in the right loader context.
2. Use `NewGlobalRef` if it needs to be stored across calls or threads.
3. Use `GetMethodID`/`GetStaticMethodID` for **that exact class**; method/field IDs are not object references and have lifetimes tied to the class.
4. When native workers have definitely stopped using it, release it with `DeleteGlobalRef`.
5. In hot-reload systems, ensure IDs/references from an old loader are not applied to a new class with the same name.

If you need to allow the class loader to be GC'd, you can design with **weak global references**, but you must check/promote to a strong local reference before each use and handle the case where the class has been unloaded. Do not treat a weak reference as an always-valid handle.

## 8. Class identity consists of name and defining loader

Two classes with the same name that are **actually defined** by two loaders are two distinct types:

~~~text
Loader A -- defines --> plugin.Target --> Class A
Loader B -- defines --> plugin.Target --> Class B

Class A.getName() == Class B.getName()   // true
Class A == Class B                       // false
~~~

You may encounter `ClassCastException`, method lookup errors, or ID mismatches when caching a `jclass` from loader A and using it with an object from loader B. Do not compare only `getName()`; check the **defining loader** and `Class<?>` identity.

Note **parent delegation**: if loaders A and B both delegate to a parent loader to define `plugin.Target`, both may return the **same `Class<?>`**, so merely calling `loader.loadClass(...)` does not prove that loader actually defined the class. The experiment in section 4 uses `getPlatformClassLoader()` as the parent and a separate application classpath to make this clear.

### 8.1. Native libraries also have class loader constraints

According to the JNI Specification, the **same JNI native library** is managed per class loader and cannot be arbitrarily loaded into two different loaders within one JVM. Calling `System.loadLibrary` for the same library from another loader can cause `UnsatisfiedLinkError`. In multi-plugin/hot-reload systems, library and loader lifecycles must be designed together.

An architecture that is often easier to control is to keep the **native bridge in a stable loader** and pass plugin `Class<?>`/`ClassLoader`/objects as explicit parameters, rather than having multiple plugin loaders load the same library or having JNI infer class names on its own.

## 9. Common errors and how to diagnose them

| Symptom | Common cause | How to check/fix |
| --- | --- | --- |
| `FindClass("com.example.Foo")` returns `NULL` | Wrong JNI name syntax | Use `"com/example/Foo"` |
| `FindClass` succeeds from native method, fails in attached native thread | Native thread uses a different loader (usually system loader) | Pass loader/`Class<?>` or cache a global ref from the right context |
| Succeeds in `JNI_OnLoad` but class not seen later | `JNI_OnLoad` has the loader of the class that loaded the library | Look up early, manage global ref; or use an explicit loader |
| Sees class with same name but cannot cast | Two different defining loaders | Check `Class.getClassLoader()` and identity |
| `NoClassDefFoundError` | Class/dependency not found or class previously failed initialization | Inspect the root exception, dependencies, loader, and classpath |
| `ClassNotFoundException` from `ClassLoader.loadClass` | Passed loader cannot load the class | Use correct dotted name; check URL/JAR and loader delegation |
| `UnsatisfiedLinkError ... already loaded in another classloader` | A native library is loaded in another loader | Check the class calling `loadLibrary` and the bridge architecture |
| `UnsatisfiedLinkError` when calling native method | Wrong JNI symbol/prototype, not a Java class lookup error | Regenerate header with `javac -h`, check exports/ABI |
| Crash after caching `jclass` | Using local reference past its lifetime, or native memory/ABI bug | Use global ref properly and stop workers before cleanup |
| `GetMethodID` fails even though class name is right | Wrong name/descriptor or class belongs to a different loader | Verify method descriptor, static/instance, and class identity |

**Do not lump exceptions into one category:** `FindClass` can lead to `NoClassDefFoundError` when a class cannot be resolved, whereas calling `ClassLoader.loadClass` directly via JNI can leave `ClassNotFoundException` pending. `UnsatisfiedLinkError` concerns loading/linking a **native library or native method**, which is a different issue.

### 9.1. Ordered debugging workflow

1. Log the exact `FindClass` string, fixing `/`, `$`, array descriptors, and letter case if wrong.
2. Identify *which class declares the native method*, its class loader, and the thread where `FindClass` is being called.
3. In Java, print `clazz.getClassLoader()`, `clazz.getName()`, and compare `clazz == expectedClazz`; check the plugin's classpath/JAR/module layer.
4. Check for `FindClass` returning `NULL` and pending Java exceptions with `ExceptionCheck`/`ExceptionOccurred`. If not intentionally recovering, let the original exception propagate to Java; do not call `ExceptionClear` unconditionally.
5. Check usage of `NewGlobalRef`/`DeleteGlobalRef`, `DeleteLocalRef`, the correct per-thread `JNIEnv *`, and caches on unload/reload.
6. With HotSpot/OpenJDK, enable JNI validation during debug runs to help catch many JNI usage errors:

~~~bash
java -Xcheck:jni -Djava.library.path=. -cp host Launcher
~~~

`-Xcheck:jni` does not prove all class loader logic is correct and cannot catch every native memory bug; combine it with logs, Java stack traces, and reference type checks. `ExceptionDescribe` can be used when debugging, but it affects exception state; do not treat it as a harmless logging operation.

## 10. Mental pitfalls to avoid

1. **Having the right name is enough:** `FindClass` also depends on the loader and dependency availability.
2. **TCCL is always the loader JNI picks:** `FindClass` has its own rules based on the native method or Invocation Interface.
3. **An attached native thread inherits the previous Java caller's loader:** without a native method context, it does not inherit automatically.
4. **`jclass` is a forever-valid pointer:** usually it is only a local reference.
5. **Global references should be kept until `JNI_OnUnload`:** a strong global reference can prevent the loader itself from unloading; clean up proactively.
6. **`JNIEnv *` can be shared across threads:** each attached thread uses its own interface pointer.
7. **Same class name means same type:** the defining loader must be considered.
8. **`GetObjectClass` and `FindClass` are equivalent:** `GetObjectClass` gets the exact runtime class of an existing object, whereas `FindClass` looks up by name and loader.
9. **`ClassLoader.loadClass` takes slash names like JNI:** this Java API takes dotted names.
10. **On any `NULL`, clear the exception and continue:** only clear when there is a specific recovery strategy.

## 11. Self-check questions

**Q1.** A Java thread calls `plugin.Bridge.lookupTarget()`, while TCCL is the system loader. If `Bridge` is defined by loader P, which loader will `FindClass` use?  
**Answer:** P, the loader of the **class declaring the native method**.

**Q2.** A native library creates its own thread and calls `AttachCurrentThread`. Why might `FindClass("plugin/Target")` fail even though the class exists?  
**Answer:** There is no plugin native method context; the system uses the Invocation Interface's default loader, which usually cannot see plugin-private classes.

**Q3.** Why should you not keep `jclass local = FindClass(...)` in a static variable and use it across multiple callbacks?  
**Answer:** A local reference is only valid within its scope; it must be converted to a global reference if kept long-term, with a mechanism to release it.

**Q4.** Do `FindClass` in `JNI_OnLoad` and in `JNI_OnUnload` use the same loader?  
**Answer:** No. `JNI_OnLoad` uses the loader of the class that loaded the library; `JNI_OnUnload` uses the system class loader.

**Q5.** Java already has `Class<?> pluginType` for the right plugin class. What is the surest way for native code to use that class?  
**Answer:** Pass `pluginType` itself through JNI; if storing it beyond the call, manage the reference lifetime.

**Q6.** Are two `plugin.Target` classes with the same name and bytecode from two different plugin loaders necessarily the same type?  
**Answer:** No, if two different loaders **define** two separate classes; name and defining loader together determine type identity.

## 12. Technical references

- [Oracle Java SE 17 — JNI Specification: FindClass](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#findclass): class names, selected loader, return value, and errors.
- [Oracle Java SE 17 — JNI Invocation API](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html): `AttachCurrentThread`, `JNI_OnLoad`, `JNI_OnUnload`, relationship between native libraries and loaders.
- [Oracle Java SE 17 — JNI Global/Local References](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#global-and-local-references): `NewGlobalRef`, `DeleteGlobalRef`, `DeleteLocalRef`.
- [Oracle Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass` and parent delegation.
- [Android NDK — JNI Tips](https://developer.android.com/ndk/guides/jni-tips): `FindClass` issue from attached native threads and early class lookup/caching solutions.

**Practical rule:** Before calling `FindClass`, identify the **internal class name**, the **executing native method or hook/thread**, the **loader that actually owns the target class**, and the **lifetime of `jclass`**. When the loader context is unclear, pass `Class<?>`/`ClassLoader` from Java for an explicit selection.
