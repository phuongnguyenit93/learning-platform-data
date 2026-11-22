# Finding Classes, Invoking Java Entry Points, and Managing Exceptions from a Native Host Application

An application written in C/C++ can **embed the Java Virtual Machine (JVM)** to execute Java code directly within that application's own process. This is the *native host → JVM → Java* call direction, which differs from the familiar *Java → JNI native library → C* case. The native host is responsible for initializing the JVM using the **JNI Invocation API**, finding the appropriate class, resolving the method ID with the exact JVM signature, creating JNI arguments, invoking the Java method, and handling any thrown exceptions before continuing or terminating the process.

The three most critical decisions in a native host are:

1. **Finding the right class:** `FindClass` requires the class name in the correct JNI format and a **class loader** that can see it. The JVM's classpath/module path must be configured at VM creation time.
2. **Invoking the right entry point:** `GetStaticMethodID`/`GetMethodID` requires the exact name and **method descriptor**; `CallStatic<Type>Method`/`Call<Type>Method` must match the return type and parameter list.
3. **Controlling errors:** A Java exception can become a **pending exception on the native host's thread**. Because there is not necessarily a Java caller waiting above, the native host must choose to handle, record, convert, or safely terminate; it must not leave an exception pending and continue making arbitrary JNI calls.

This lesson presents this entire flow, an **executable example in Java 17+ and C11 on Linux**, the success path, two known exception types, the unexpected error path, local reference management, JVM shutdown, and practical issues regarding class loaders, multithreading, and security.

## 1. Understanding the Call Direction When Embedding the JVM

In a normal Java application, the command `java com.example.Main` is handled by the Java launcher; the JVM is created before `public static void main(String[] args)` runs. In a native host application, **C is the starting point**, deciding when to create the VM and which Java method to invoke. It is not necessary to call a method named `main`.

Lifecycle diagram:

```text
Native process: C's main()
      |
      | Prepare JavaVMInitArgs, options
      v
JNI_CreateJavaVM(&vm, &env, &args)
      |
      +--> JavaVM *vm: JVM management interface
      +--> JNIEnv *env: JNI interface OF THE current THREAD
      |
      | FindClass("com/example/EntryPoint")
      v
jclass entryClass (local reference)
      |
      | GetStaticMethodID(entryClass, "run", "(Ljava/lang/String;)I")
      v
jmethodID runMethod (ID, not a local reference)
      |
      | NewStringUTF("21") -> jstring arg (local reference)
      | CallStaticIntMethod(entryClass, runMethod, arg)
      v
Java method executes in the JVM
      |
      +--> If successful: returns jint
      |
      +--> If an exception is thrown: pending on the JNI thread
      |    ExceptionCheck/ExceptionOccurred
      |    ExceptionClear if choosing to handle
      |
      v
Clean up local references, native memory, pending state
      |
      v
DestroyJavaVM(vm) -> native main() returns exit code
```

In particular, `JNI_CreateJavaVM` is not a JNI native method called by Java. It belongs to the **Invocation API**, which can be called from a native host program that has linked/loaded the VM library. Conversely, calls such as `(*env)->FindClass(...)` and `(*env)->CallStaticIntMethod(...)` belong to the `JNIEnv` interface after the JVM already exists.

### 1.1. Two Groups of Pointers That Must Not Be Confused

| Value | Provided by | Role | Lifetime rules |
| --- | --- | --- | --- |
| `JavaVM *vm` | `JNI_CreateJavaVM` | Access Invocation API; attach/detach threads, destroy VM | Bound to the created JVM; do not use after shutdown |
| `JNIEnv *env` | `JNI_CreateJavaVM` or `AttachCurrentThread` | Call JNI functions on **one thread** | Only use on the thread that received `env` |
| `jclass` / `jobject` / `jstring` | JNI calls | Opaque references to Java objects | Local/global/weak-global scope per the JNI contract |
| `jmethodID` | `GetStaticMethodID` / `GetMethodID` | Opaque ID identifying a class's method | Not a `jobject`, do not use `DeleteLocalRef`; lifetime is tied to the class |
| `jint` / `jlong` | Java primitive ↔ JNI | Primitive data | No local reference cleanup needed |

Both `JavaVM *` and `JNIEnv *` have different syntax in C compared to C++. In **C**, calls go through a function table like `(*env)->FindClass(env, "java/lang/String")`; in **C++**, it is typically written `env->FindClass("java/lang/String")`. Do not copy C++ signatures into a C11 file.

## 2. Initializing the JVM: `JNI_CreateJavaVM` and `JavaVMInitArgs`

Key types/entry points in `jni.h`:

```c
jint JNI_CreateJavaVM(JavaVM **p_vm,
                      void **p_env,
                      void *vm_args);

typedef struct JavaVMInitArgs {
    jint version;
    jint nOptions;
    JavaVMOption *options;
    jboolean ignoreUnrecognized;
} JavaVMInitArgs;

typedef struct JavaVMOption {
    char *optionString;
    void *extraInfo;
} JavaVMOption;
```

This is an **API description**, not a standalone compilable C file. The `jni.h` header already provides definitions matching the JDK and compiler. Do not redefine these typedefs in your project.

- `version`: **JNI** interface version, for example `JNI_VERSION_1_8`. This is **not** the JDK 8/17/21 version string; JNI 1.8 can still be used on JDK 17+.
- `nOptions`, `options`: VM configuration at startup time, such as `-Djava.class.path=.`, `-Xms...`, `-Xmx...`, module options.
- `ignoreUnrecognized`: if `JNI_FALSE`, certain unrecognized options cause startup to fail instead of being ignored.
- `p_vm`: location where the JVM fills in `JavaVM *`.
- `p_env`: location where the JVM fills in a valid `JNIEnv *` for **the thread that called to create the VM**.
- Return code `JNI_OK` indicates success; other negative codes such as `JNI_ERR`, `JNI_EVERSION`, `JNI_ENOMEM`, etc. indicate situational errors.

Minimal initialization example in C:

```c
#include <jni.h>

JavaVM *vm = NULL;
JNIEnv *env = NULL;

char classpath[] = "-Djava.class.path=.";
JavaVMOption option = { .optionString = classpath, .extraInfo = NULL };
JavaVMInitArgs args = {
    .version = JNI_VERSION_1_8,
    .nOptions = 1,
    .options = &option,
    .ignoreUnrecognized = JNI_FALSE
};

jint result = JNI_CreateJavaVM(&vm, (void **)&env, &args);
if (result != JNI_OK) {
    /* Do not call JNIEnv functions if the JVM has not been created successfully. */
}
```

The snippet above **only illustrates a block inside a C function**; the full runnable program is in section 6. `java.class.path` is set when creating the VM so the system class loader sees `.class` files in the current directory. For JARs, other paths, or multi-module environments, an appropriate class lookup path must be designed.

### 2.1. Why Must the Classpath Be Correct from the Start?

`FindClass` searches for a class through the class loader of the current context. When a native host uses the Invocation API without a Java native method on the call stack, JNI defaults to using the **system class loader**. Therefore, `-Djava.class.path=.` is a clear choice for a sample program where `EmbeddedEntry.class` resides in the working directory.

If the binary is run from a different directory, `.` also points to that different directory. The result can be `FindClass == NULL` and a pending `NoClassDefFoundError`, even though `EmbeddedEntry.class` still exists somewhere on the machine.

Do not rely on the environment `CLASSPATH` when the native app already passes its own system property. With JPMS modules, custom loaders, or a plugin architecture, you must identify **the exact class loader that owns the class**; `FindClass` does not automatically scan all JARs/modules/class loaders.

### 2.2. A Process Must Not Arbitrarily Create Multiple JVMs

The JDK 17 Invocation API specification states that **creating multiple Java VMs in a single process is not supported**. In a product that embeds the JVM, the architecture should have one shared VM management component and threads attached as needed, rather than creating/destroying a VM per request.

Nor should a design rely on expecting to call `DestroyJavaVM` and immediately create a new VM multiple times. The availability of restarting a VM in the same process is not guaranteed. If session isolation or a clean restart is needed, consider a separate **child process**.

## 3. Finding a Class: `FindClass`, Binary Names, and Class Loaders

Function:

```c
jclass FindClass(JNIEnv *env, const char *name);
```

In C:

```c
jclass entry = (*env)->FindClass(env, "EmbeddedEntry");

if (entry == NULL) {
    /* An error occurred, usually accompanied by a pending Java exception. */
    return;
}
```

These two snippets are **prototypes and illustrative structures**, not standalone programs.

The name passed to `FindClass` is in **slash-separated form** for packages, not dot-separated form:

| Java binary name | `FindClass` name |
| --- | --- |
| `EmbeddedEntry` (default package) | `EmbeddedEntry` |
| `com.example.EntryPoint` | `com/example/EntryPoint` |
| `java.lang.String` | `java/lang/String` |
| `java.lang.NumberFormatException` | `java/lang/NumberFormatException` |
| `java.lang.String[]` | `[Ljava/lang/String;` |

Do not confuse **class name** with **method signature**. The argument `FindClass("com/example/EntryPoint")` does not have `L...;` around it; whereas in a method descriptor, an object parameter is written `Lcom/example/EntryPoint;`.

If `FindClass` cannot find or load the class, it usually returns `NULL` with a pending exception such as `NoClassDefFoundError`; other errors such as bytecode verification failures, initialization errors, or missing dependencies can also appear in related steps. After receiving `NULL`, do not call `GetStaticMethodID(env, NULL, ...)`.

### 3.1. Local Reference to `jclass`

`FindClass` returns a `jclass`, which in JNI terms is a **local reference to a Class object** within the invocation/thread. The native host may call `DeleteLocalRef(env, entry)` when finished using it. Deleting the local ref does not mean “destroying the Java class.” Other roots, the class loader, and class unloading rules still govern the class lifecycle.

If you need to keep the class across many long-lived calls, or use it on other native threads, use `NewGlobalRef` and then `DeleteGlobalRef` at the proper release time. Do not store a local `jclass` in a global C variable and use it after the thread detaches or the local frame expires.

### 3.2. Custom Class Loaders and Module Path

In real applications, a class may be loaded by a dedicated plugin loader; in that case, `FindClass` from the native host will not necessarily see the class. A more reliable approach is to receive a valid `jclass` from Java bootstrap code, or obtain the required Java `ClassLoader` and call `loadClass` through JNI in accordance with access permissions and the class-loader contract.

Distinguish between:

- `FindClass("com/example/EntryPoint")`: JNI's `/` form.
- `ClassLoader.loadClass("com.example.EntryPoint")`: Java binary name using `.`.
- `Class.forName("com.example.EntryPoint", true, loader)`: requests class initialization per the Java API, with a specific loader.

When configuring JPMS, options such as `--module-path=...`, `--add-modules=...`, `--add-exports=...` must use the **option=value form** in `JavaVMOption.optionString` per the Invocation API. Adding a module path alone does not automatically guarantee that APIs in the module are accessible from calling code; module readability/exports and reflection constraints (if using reflection) must also be considered.

## 4. Finding a Method: `GetStaticMethodID` and Entry Point Methods

Once you have a `jclass`, the next step is to get the ID of the method to invoke.

```c
jmethodID GetStaticMethodID(JNIEnv *env,
                            jclass clazz,
                            const char *name,
                            const char *sig);
```

C code:

```c
jmethodID method = (*env)->GetStaticMethodID(
    env, entry, "evaluate", "(Ljava/lang/String;)I");

if (method == NULL) {
    /* Matching method not found or an exception occurred. */
    return;
}
```

Explanation of the signature `(Ljava/lang/String;)I`:

- `(` and `)` enclose the list of parameter types.
- `Ljava/lang/String;` is one argument of type `java.lang.String`.
- `I` means the return type is `int`.

Common descriptor table:

| Java type | JNI signature |
| --- | --- |
| `void` | `V` |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `String` | `Ljava/lang/String;` |
| `String[]` | `[Ljava/lang/String;` |
| `int[]` | `[I` |

Examples:

| Java method | Descriptor |
| --- | --- |
| `static int evaluate(String text)` | `(Ljava/lang/String;)I` |
| `static void main(String[] args)` | `([Ljava/lang/String;)V` |
| `static long add(long a, long b)` | `(JJ)J` |
| `static boolean ready()` | `()Z` |
| `int size()` (instance) | `()I` |

Do not guess descriptors from method names. To inspect compiled bytecode, use:

```bash
javap -s -p EmbeddedEntry
```

The command above displays the class's actual descriptors. For generics, descriptors use **type erasure**; there is no generic syntax like `List<String>` at the JNI descriptor level. For overloaded methods, the same name with different descriptors selects different overloads.

**Distinguishing static/instance:**

- `GetStaticMethodID` → `CallStaticIntMethod`, `CallStaticObjectMethod`, `CallStaticVoidMethod`, etc., and the receiver is a `jclass`.
- `GetMethodID` → `CallIntMethod`, `CallObjectMethod`, `CallVoidMethod`, etc., and the receiver is an appropriate `jobject` instance.
- If you need to create an instance yourself, there must be a `<init>` constructor, `GetMethodID(env, clazz, "<init>", "(...)V")` followed by `NewObject`. Do not invoke `<init>` as a static method.

You must check the return value of `GetStaticMethodID`; if the method does not exist, there may be a pending `NoSuchMethodError`. Retrieving a method ID can also **initialize the class** if the class has not yet been initialized, and a Java static initializer can throw an exception. Therefore, do not assume “lookup only, no Java code runs.”

A `jmethodID` is **not a local JNI reference**; do not call `DeleteLocalRef` on it. If caching method IDs over a long lifetime, you must ensure the associated class/class loader remains valid; in an environment with dynamic unloading, reusing the ID of an unloaded class violates the contract.

## 5. Invoking Java: Creating Arguments, Retrieving Results, and Checking Errors

For `evaluate(String) : int`, the C → Java sequence can be written as:

```c
/* Illustrative snippet in a native host that already has env, entry, method. */
jstring arg = (*env)->NewStringUTF(env, "21");
if (arg == NULL) {
    /* There may be a pending OutOfMemoryError. */
    return;
}

jint value = (*env)->CallStaticIntMethod(
    env, entry, method, arg);

/* DeleteLocalRef is allowed even when a Java exception is pending. */
(*env)->DeleteLocalRef(env, arg);

if ((*env)->ExceptionCheck(env)) {
    /* Do not use value. Choose to handle the exception. */
    return;
}

printf("value=%d\n", (int)value);
```

This is an **illustrative structure**, not a standalone file. `NewStringUTF` takes a C string in JNI's **Modified UTF-8**, not full standard UTF-8; the ASCII string `"21"` is compatible. For arbitrary internationalized/Unicode data, you must convert the encoding properly or create the String from UTF-16; do not pass invalid byte sequences to `NewStringUTF`.

A Java method can validly return `0`, so do not use a `jint` value of `0` to infer an exception. **Check for a pending exception after `CallStaticIntMethod`** when the result depends on a Java callback.

If the Java method has a `void` return type, use `CallStaticVoidMethod` and still check for exceptions. If the method returns an object, use `CallStaticObjectMethod`, manage the local `jobject`, and distinguish a valid `NULL` (returning Java null) from a pending exception when necessary.

### 5.1. Each JNI Call Can Fail Differently

| Step | Common errors | Rule |
| --- | --- | --- |
| `JNI_CreateJavaVM` | Invalid option, no suitable JVM, out of memory | Check `JNI_OK` before using `env` |
| `FindClass` | Class not present, wrong class loader, missing dependency | Check `NULL` and pending state |
| `GetStaticMethodID` | Wrong name/descriptor/static, class initialization error | Check `NULL`; do not call with an invalid method ID |
| `NewStringUTF` | Failed to allocate String, invalid encoding | Check `NULL`, do not pass invalid refs |
| `CallStaticIntMethod` | Java callback throws any `Throwable` | Check `ExceptionCheck`, do not use result when pending |
| `ExceptionOccurred` | Returns local throwable when pending | Manage local ref; **does not clear** pending |
| `ExceptionClear` | Explicitly discards pending state | Only call when there is a genuine handling policy |
| `DestroyJavaVM` | May wait for non-daemon threads; may fail | Shut down in order, check status |

## 6. Runnable Program: C Host Creates JVM, Finds Java Class, Handles Exceptions

The demo program shows **C actively calling Java three times**:

- Input `"21"`: Java returns `42`, host prints a normal result.
- Input `"bad"`: Java throws `NumberFormatException`; host retrieves the throwable, clears pending, classifies it, and prints an error label.
- Input `"-1"`: Java throws `IllegalArgumentException`; host handles it similarly but distinguishes the exact class.
- For an exception **not belonging to the two recognized error groups**, the host **does not swallow the error**: it re-sets the throwable as pending, lets the fatal path print diagnostics, and exits with an error code.

The example uses Java 17 and C11, relying only on the Java standard library, JNI from the JDK, and a C compiler on Linux. No native method is needed in Java because Java only acts as **a module called into by the native host**.

### 6.1. File `EmbeddedEntry.java`

```java
public final class EmbeddedEntry {
    private EmbeddedEntry() {
        // Only provides a static API for the native host to call.
    }

    public static int evaluate(String text) {
        int value = Integer.parseInt(text);

        if (value < 0) {
            throw new IllegalArgumentException(
                "negative numbers are not allowed");
        }

        return Math.multiplyExact(value, 2);
    }
}
```

This class intentionally **has no `main`**. The C function acts as the launcher: after initializing the JVM, it finds the `EmbeddedEntry` class and calls `evaluate` with descriptor `(Ljava/lang/String;)I`. We use `Math.multiplyExact` so that a very large input can trigger `ArithmeticException` due to overflow; this is an exception **not treated as a normal parse error** in the sample policy.

### 6.2. File `embed_host.c`

```c
#include <jni.h>
#include <stdio.h>

/*
 * run_once returns 1 if it handled the result or business error
 * according to the defined policy. Returns 0 on an unexpected error.
 *
 * formatType and argumentType are local refs to two Class objects
 * looked up BEFORE the Java callback can throw.
 */
static int run_once(JNIEnv *env,
                    jclass entryClass,
                    jmethodID evaluateMethod,
                    jclass formatType,
                    jclass argumentType,
                    const char *label,
                    const char *inputText) {

    jstring javaText = (*env)->NewStringUTF(env, inputText);
    if (javaText == NULL) {
        return 0;  /* There may be a pending OutOfMemoryError. */
    }

    jint answer = (*env)->CallStaticIntMethod(
        env, entryClass, evaluateMethod, javaText);

    /* Local ref cleanup is allowed even when an exception is pending. */
    (*env)->DeleteLocalRef(env, javaText);

    if ((*env)->ExceptionCheck(env) == JNI_FALSE) {
        printf("%s=%d\n", label, (int)answer);
        return 1;
    }

    /*
     * ExceptionOccurred creates a local ref to the Throwable,
     * but does not change the pending state.
     */
    jthrowable error = (*env)->ExceptionOccurred(env);
    if (error == NULL) {
        return 0;  /* Cannot classify safely. */
    }

    /*
     * Must clear BEFORE calling IsInstanceOf.
     * Otherwise, IsInstanceOf is not allowed to be called
     * while an exception is pending.
     */
    (*env)->ExceptionClear(env);

    jboolean isFormat = (*env)->IsInstanceOf(
        env, error, formatType);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, error);
        return 0;
    }

    if (isFormat == JNI_TRUE) {
        printf("%s=NumberFormatException\n", label);
        (*env)->DeleteLocalRef(env, error);
        return 1;
    }

    jboolean isArgument = (*env)->IsInstanceOf(
        env, error, argumentType);

    if ((*env)->ExceptionCheck(env)) {
        (*env)->DeleteLocalRef(env, error);
        return 0;
    }

    if (isArgument == JNI_TRUE) {
        printf("%s=IllegalArgumentException\n", label);
        (*env)->DeleteLocalRef(env, error);
        return 1;
    }

    /*
     * Unexpected Throwable: rethrow the same object.
     * Main will call ExceptionDescribe and exit with an error.
     */
    (void)(*env)->Throw(env, error);
    (*env)->DeleteLocalRef(env, error);
    return 0;
}

int main(void) {
    JavaVM *vm = NULL;
    JNIEnv *env = NULL;

    /* "." is the working directory when RUNNING the executable. */
    char classpathOption[] = "-Djava.class.path=.";
    JavaVMOption options[1] = {
        { .optionString = classpathOption, .extraInfo = NULL }
    };
    JavaVMInitArgs args = {
        .version = JNI_VERSION_1_8,
        .nOptions = 1,
        .options = options,
        .ignoreUnrecognized = JNI_FALSE
    };

    jint rc = JNI_CreateJavaVM(&vm, (void **)&env, &args);
    if (rc != JNI_OK || vm == NULL || env == NULL) {
        fprintf(stderr, "JNI_CreateJavaVM failed: %d\n", (int)rc);
        return 1;
    }

    int exitCode = 1;
    jclass entryClass = NULL;
    jclass formatType = NULL;
    jclass argumentType = NULL;

    entryClass = (*env)->FindClass(env, "EmbeddedEntry");
    if (entryClass == NULL) {
        goto cleanup;
    }

    /*
     * GetStaticMethodID may initialize the class.
     * If the Java static initializer fails, there will be an exception.
     */
    jmethodID evaluateMethod = (*env)->GetStaticMethodID(
        env, entryClass, "evaluate", "(Ljava/lang/String;)I");
    if (evaluateMethod == NULL) {
        goto cleanup;
    }

    /*
     * Preload classes before CallStaticIntMethod:
     * do not look up new classes while a Java exception is already pending.
     */
    formatType = (*env)->FindClass(
        env, "java/lang/NumberFormatException");
    if (formatType == NULL) {
        goto cleanup;
    }

    argumentType = (*env)->FindClass(
        env, "java/lang/IllegalArgumentException");
    if (argumentType == NULL) {
        goto cleanup;
    }

    if (!run_once(env, entryClass, evaluateMethod,
                  formatType, argumentType, "ok", "21")) {
        goto cleanup;
    }

    if (!run_once(env, entryClass, evaluateMethod,
                  formatType, argumentType, "bad", "bad")) {
        goto cleanup;
    }

    if (!run_once(env, entryClass, evaluateMethod,
                  formatType, argumentType, "negative", "-1")) {
        goto cleanup;
    }

    puts("host=completed");
    exitCode = 0;

cleanup:
    /*
     * There is no Java caller waiting for native main.
     * For unexpected errors, the native host must report the error clearly.
     *
     * ExceptionDescribe prints the stacktrace and CLEARS pending:
     * only use on this fatal path, not to
     * "peek" when wanting to continue propagating.
     */
    if ((*env)->ExceptionCheck(env)) {
        fprintf(stderr, "Unexpected Java exception:\n");
        (*env)->ExceptionDescribe(env);
        exitCode = 1;
    } else if (exitCode != 0) {
        fprintf(stderr, "Host stopped due to a JNI error\n");
    }

    if (argumentType != NULL) {
        (*env)->DeleteLocalRef(env, argumentType);
    }
    if (formatType != NULL) {
        (*env)->DeleteLocalRef(env, formatType);
    }
    if (entryClass != NULL) {
        (*env)->DeleteLocalRef(env, entryClass);
    }

    /*
     * Shut down after handling pending exceptions and refs.
     * DestroyJavaVM may wait for other non-daemon threads.
     */
    rc = (*vm)->DestroyJavaVM(vm);
    if (rc != JNI_OK) {
        fprintf(stderr, "DestroyJavaVM failed: %d\n", (int)rc);
        return 1;
    }

    return exitCode;
}
```

**Notable points in the C code:**

1. C does not have `System.loadLibrary` or `JNIEXPORT Java_...` because **C itself creates the VM and calls Java**, rather than Java looking up a JNI native method exported by C.
2. `JNI_CreateJavaVM` takes the address of `JavaVM *`, the address of `JNIEnv *` cast to `void **` per the Invocation API signature, and `JavaVMInitArgs`.
3. After creating the VM successfully, all JNI calls go through the thread-correct `env`. Do not use `env` if startup fails.
4. `FindClass("EmbeddedEntry")` searches for the class in the default package via the system class loader; `-Djava.class.path=.` helps find `EmbeddedEntry.class` in the working directory.
5. `GetStaticMethodID` uses the exact descriptor `(Ljava/lang/String;)I` and can cause class initialization to occur; there is an error branch if the ID cannot be obtained.
6. The classes used to classify exceptions are looked up **before** calling Java. If the callback throws an error, do not call `FindClass` while an exception is still pending.
7. `NewStringUTF` creates a local `jstring`. `run_once` calls `DeleteLocalRef` before reading the pending state, even if the callback threw. This is permitted JNI cleanup.
8. `ExceptionCheck` does not create a local ref, helping decide between success and error. Only when it is genuinely necessary to know the error type is `ExceptionOccurred` called.
9. `ExceptionOccurred` creates a local `jthrowable`, but the pending exception remains. Since `IsInstanceOf` is not among the JNI functions allowed while pending, the code calls `ExceptionClear` first.
10. `NumberFormatException` extends `IllegalArgumentException`, so **NumberFormatException must be checked first** to classify accurately. If the order is reversed, parse errors would also be printed as `IllegalArgumentException`.
11. Both recognized error types are handled intentionally, and then the local ref `error` is deleted; the native host can continue to the next call.
12. Unexpected errors are re-thrown via `Throw` using the same `Throwable` object; the final cleanup branch sees the pending exception and uses `ExceptionDescribe` to print diagnostics and clear it. An error such as `ArithmeticException` is not silently converted into a valid result.
13. `DestroyJavaVM` runs after errors have been handled and references cleaned up. If the Java application started additional non-daemon threads, the destroy step may wait for them; in a real app there must be a shutdown policy.
14. The `jint` result is only used when `ExceptionCheck == JNI_FALSE`. A number like `0` can be a valid business result, not a JNI error signal.

### 6.3. Compiling on Linux with JDK 17+

Place both `EmbeddedEntry.java` and `embed_host.c` in the **same directory**, then run the commands in that directory. `JAVA_HOME` must be the JDK directory in use, containing `include/jni.h` and `lib/server/libjvm.so`.

```bash
javac EmbeddedEntry.java

cc -std=c11 -Wall -Wextra -Wpedantic \
  -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
  embed_host.c \
  -L"$JAVA_HOME/lib/server" \
  -Wl,-rpath,"$JAVA_HOME/lib/server" \
  -ljvm -o embed_host

./embed_host
```

**Exact stdout when the three sample paths succeed:**

```text
ok=42
bad=NumberFormatException
negative=IllegalArgumentException
host=completed
```

On the normal success path, there is no Java stacktrace on `stderr` because the two business errors were explicitly handled by the native host. If the VM fails to initialize or an unexpected error occurs, the program may print diagnostic messages to `stderr`, return a nonzero exit code, and **not** produce the complete stdout shown above.

**Why not run `java EmbeddedEntry`?** The class has no `main`; it is a library entry point for the C host. The program to launch is the executable `./embed_host`.

**Why not use `javac -h`?** The Java source does not declare any `native` methods, so there is no need to generate a JNI exported header. C only uses the JDK's `jni.h` to create the VM and call Java methods. `javac -h` is primarily useful when Java declares native methods that require an exported C implementation.

**How does the C command link?** `-I` finds JNI headers, `-L` finds `libjvm.so` at link time, `-ljvm` links the Invocation API, and `-Wl,-rpath,...` tells the runtime linker where to find the JVM library. On different Linux distributions, the path to `libjvm.so` may be in a different location; check the actual JDK layout.

**Platform notes:** Windows uses `jvm.dll` and an import library/loader configuration per toolchain (MSVC or appropriate MinGW); macOS uses JDK/macOS library paths and linker options; do not copy `include/linux` and `-Wl,-rpath` verbatim to other platforms. The native host and JVM must have **compatible architecture/ABI** (x64 ↔ x64, ARM64 ↔ ARM64, calling convention, and compiler runtime).

### 6.4. Testing Out-of-Policy Error Generation

To test the fatal path, one scenario is calling `evaluate("2147483647")`. `Integer.parseInt` succeeds, but `Math.multiplyExact(value, 2)` throws `ArithmeticException` due to overflow.

Only change **the input of the test call in a copy used for testing** (not the default stdout of the sample). Because this is neither a parse error nor a negative number, `run_once` calls `Throw(env, error)` and returns 0. The `cleanup` branch sees the pending exception, prints the stacktrace using `ExceptionDescribe`, and returns exit code 1. The stacktrace (line numbers/file names depend on the code version) should not be treated as fixed stdout.

In production, a native host might choose to log the exception via C's logging framework, convert it into an error status of a plugin manager, or actively stop the worker/subprocess. The important thing is **not to continue calling Java as if no error occurred**.

## 7. JNI Exceptions from the Perspective of a C Host Application

### 7.1. How Do a Java-Called Native Method and a Native Host Differ?

In the `Java → native method → Java` path, if JNI code leaves an exception pending and returns, the Java caller above can observe the exception as a `throw`.

In the `native main → embedded JVM → Java method` path, **there is no Java caller at the native main point** to catch it automatically. The pending state remains attached to the JNI thread, but the native host must choose one of the following strategies:

- **Recover:** retrieve the exception, clear it, confirm it is an allowed error type, and return a fallback result or record a status.
- **Report-and-stop:** print diagnostics (e.g. `ExceptionDescribe` on the fatal path), clear it, and terminate the native operation with an appropriate error code.
- **Propagate to a Java layer:** if the host architecture has a corresponding Java callback/handler, design a path to re-emit the exception via `Throw` with proper lifetime, rather than just returning from C `main` and hoping the JVM does it for you.
- **Isolate:** move the Java plugin/job into a separate process; the main host receives status/IPC, protecting availability against unrecoverable errors.

Do not assume `ExceptionClear` means the error has been handled at the business level. Clearing only removes **the pending state**. If the root cause is ignored, the returned data may no longer be valid.

### 7.2. `ExceptionCheck`, `ExceptionOccurred`, and `ExceptionDescribe`

| API | Return/effect | Pending after call | Adds local ref? |
| --- | --- | --- | --- |
| `ExceptionCheck(env)` | `JNI_TRUE` or `JNI_FALSE` | Unchanged | No |
| `ExceptionOccurred(env)` | Local `jthrowable` or `NULL` | Unchanged | Yes if non-`NULL` |
| `ExceptionClear(env)` | Clears pending exception | Cleared | No |
| `ExceptionDescribe(env)` | Prints throwable + stacktrace to system error stream | **Cleared** per specification | No |
| `Throw(env, throwable)` | Sets throwable object as pending | Becomes pending if successful | Does not create a new ref to an existing object |
| `ThrowNew(env, exceptionClass, message)` | Creates/sets a new exception | Pending if successful | Not a harmless way to “print logs” |

For any arbitrary error, the quick check pattern is:

```c
if ((*env)->ExceptionCheck(env)) {
    /* Clean up using allowed JNI calls. */
    /* Then return or handle intentionally. */
}
```

If classification is needed:

```c
jthrowable error = (*env)->ExceptionOccurred(env);
if (error != NULL) {
    (*env)->ExceptionClear(env);

    /* Now normal JNI APIs can be called to inspect the error. */

    (*env)->DeleteLocalRef(env, error);
}
```

The two snippets above are **illustrative structures in a native host**, not standalone files. `ExceptionOccurred` **does not clear** pending, and `DeleteLocalRef(error)` only deletes the local handle, **not the pending Java exception**.

### 7.3. Which JNI Calls Can Be Used While Pending?

When an exception is pending, most normal JNI APIs **must not be called**. Operations permitted by the specification include:

- `ExceptionCheck`, `ExceptionOccurred`, `ExceptionDescribe`, `ExceptionClear`.
- `DeleteLocalRef`, `DeleteGlobalRef`, `DeleteWeakGlobalRef`.
- `ReleaseStringChars`, `ReleaseStringUTFChars`, `ReleaseStringCritical`.
- `Release<Type>ArrayElements`, `ReleasePrimitiveArrayCritical`.
- `MonitorExit`, `PushLocalFrame`, `PopLocalFrame`, `DetachCurrentThread`.

That is why the runnable sample **preloads exception classes before the Java callback** and only calls `IsInstanceOf` after `ExceptionClear`. APIs such as `FindClass`, `GetStaticMethodID`, `NewStringUTF`, or `CallStaticIntMethod` are not in the safe group while pending.

If a JNI callback has raised an exception, **do not use the return value** of `CallStaticIntMethod` for business logic even if it happens to have a bit pattern resembling valid data. Clean up JNI resources first, then handle the exception according to policy.

### 7.4. When Class Initialization Throws an Exception

An often-overlooked case is a class with `static { ... }` that performs I/O or throws errors. `GetStaticMethodID` can trigger initialization if the class has not been initialized yet. If the initializer throws, JNI may encounter `ExceptionInInitializerError` or a related error; subsequent accesses may also encounter `NoClassDefFoundError` because the class is in a failed initialization state.

Do not merely check `FindClass != NULL` and assume every method lookup will succeed. Check each step and decide whether that plugin/module needs to be marked unhealthy or if other components can continue running.

### 7.5. Do Not “Log” with `ExceptionDescribe` Before Intending to Rethrow

`ExceptionDescribe` **clears the pending exception** after printing. If the native host wants to keep the error object and rethrow it later, it must be aware of this behavior; calling `ExceptionDescribe` and then proceeding as if the exception were still pending is wrong.

If you want to log while keeping the throwable, you need a deliberate policy: retrieve `ExceptionOccurred` (local ref), clear it, call Java APIs to get the message/stacktrace while not pending, then `Throw` again if needed. This process introduces an additional source of exceptions during logging that must be handled; on the fatal path, printing and stopping is usually simpler.

## 8. Lifecycle of References, JNIEnv, Threads, and Shutdown

### 8.1. Local References in Long Loops of a C Host

A native host can perform hundreds of thousands of Java calls on **the same attached thread**. Local references created in an Invocation API context should not be allowed to accumulate until thread detach or JVM shutdown.

For each loop iteration:

```c
/* Structural example in a host that already has env and entryClass. */
for (int i = 0; i < count; ++i) {
    jstring value = (*env)->NewStringUTF(env, "x");
    if (value == NULL) {
        break; /* Handle pending exception after cleanup. */
    }

    /* Use value for JNI method call... */
    (*env)->DeleteLocalRef(env, value);
}
```

This is **illustrative code**; not a standalone file. If a single iteration creates many objects, `PushLocalFrame`/`PopLocalFrame` can be used; you must pop on both the success path and valid exception paths. Local refs are only valid in the thread that created them; do not pass a local `jobject` to another pthread.

### 8.2. Multithreaded Native Host: `AttachCurrentThread` and `DetachCurrentThread`

Once the JVM is created, a C worker thread that wants to use JNI must attach:

```c
/*
 * Illustration: vm is valid; this is a C function running on
 * a different OS thread from the thread that created the JVM.
 */
JNIEnv *threadEnv = NULL;
jint status = (*vm)->AttachCurrentThread(
    vm, (void **)&threadEnv, NULL);

if (status == JNI_OK) {
    /* Use threadEnv ONLY in this thread. */

    /* Ensure no Java methods remain on the call stack
       and clean up local/global references per policy. */
    (*vm)->DetachCurrentThread(vm);
}
```

A `JNIEnv *` returned for thread A **cannot** be used on thread B. If multiple host workers need to access the JVM, store `JavaVM *` so each thread can attach itself and obtain its own `JNIEnv *`. A native-created thread must detach before exiting when using `AttachCurrentThread`, per Invocation API rules. Do not detach a thread while it still has Java methods on the stack.

If you need to share a Java object across threads or retain it across multiple tasks, create a **global JNI reference** with `NewGlobalRef` under valid conditions and delete it with `DeleteGlobalRef` when no longer needed. A local `jclass`/`jobject` does not become safe just by copying the pointer value to native heap memory.

### 8.3. Shutting Down an Embedded JVM

`DestroyJavaVM` terminates the JVM per the Invocation API; it may **wait for non-daemon Java threads and other attached native threads to finish**. If the Java application started a non-daemon thread pool/timer/service and does not shut it down, the native host may wait for a long time or indefinitely.

Practical shutdown checklist:

1. Stop accepting new Java calls and transition the host into a stopping state.
2. Wait for or cancel in-flight jobs according to your contract; do not free native allocations still in use by callbacks.
3. Notify the Java layer to shut down executors/sockets/timers if any exist.
4. Clean up unneeded JNI global refs and local refs.
5. Ensure native workers have detached properly per the rules; handle any pending exceptions before exiting.
6. Call `DestroyJavaVM` in a valid thread/scope and check the return code.
7. Do not continue making JNI calls via `env` or `vm` after the VM has been destroyed.

In a large native app, JNI documentation also notes that on some operating systems, initializing the JVM from the **primordial process thread** has caveats regarding stack and thread handling; it may be advisable to create a dedicated thread to initialize/coordinate the VM. The minimal example uses `main` for clarity; production code should review platform-specific guidance.

## 9. When to Call the `main(String[])` Entry Point Instead of a Dedicated API?

If a Java module is designed as a standalone application, the native host can look up:

```c
jmethodID mainMethod = (*env)->GetStaticMethodID(
    env, mainClass, "main", "([Ljava/lang/String;)V");
```

This is **illustrative code**, without `mainClass` or the `String[]` argument. To call it properly, the native host must create a `jobjectArray` of type `String[]` via `NewObjectArray` (usually needing `FindClass("java/lang/String")` first), set the strings with `SetObjectArrayElement`, call `CallStaticVoidMethod`, and then clean up local references.

However, calling a Java application's `main` from a native host can trigger starting background threads, global configuration, and `System.exit()` if the Java code calls it itself. `System.exit()` can terminate the entire **native host process**, which is usually undesirable for a plugin host/server.

A dedicated Java API such as `public static int evaluate(String)` or a service interface with explicit create/start/stop is usually easier to embed, test, and manage shutdown for than calling a general-purpose Java `main`.

If the requirement is truly to use the Java launcher rather than in-process embedding, consider spawning a separate `java -cp ... Main` process and communicating via IPC/HTTP/gRPC. In that case the boundary is a **process**, not a JNI call, and the native host does not have to manage `JNIEnv *`.

## 10. Troubleshooting Common Errors

| Symptom | Possible cause | Check/fix |
| --- | --- | --- |
| `JNI_CreateJavaVM` returns a negative code | Wrong JVM option, architecture, environment/heap | Check JDK, `JAVA_HOME`, options, return code |
| Running `./embed_host` reports `libjvm.so` not found | Dynamic loader cannot find JVM shared library | Check RPATH, `libjvm.so`, and link command |
| `FindClass("EmbeddedEntry") == NULL` | Class not on classpath or wrong working dir | Verify `EmbeddedEntry.class` and `-Djava.class.path=.` |
| `FindClass("com.example.Foo")` fails | Used dots instead of slashes | Use `com/example/Foo` |
| `GetStaticMethodID` returns `NULL` | Wrong descriptor, non-static method, nonexistent method | `javap -s -p`, fix name and descriptor |
| Method lookup throws `ExceptionInInitializerError` | Class static initializer failed | Diagnose root cause, do not use method ID |
| `CallStaticIntMethod` returns a “weird” number | Method has a pending exception; result is invalid | `ExceptionCheck` before using `jint` |
| After a callback error, subsequent `FindClass` crashes or triggers CheckJNI warning | Pending exception exists | Clean up; clear only when there is a recovery policy |
| `ExceptionOccurred` used in a loop without deleting ref | Accumulating JNI local references | `DeleteLocalRef` each handle |
| `NumberFormatException` seen but labeled `IllegalArgumentException` | The two classes have an inheritance relationship | Test specific subclass before superclass |
| After `ExceptionDescribe` no exception remains | This API **clears pending state** | Only use for diagnostics/fatal; rethrow intentionally |
| Native host hangs on `DestroyJavaVM` | Java non-daemon threads have not stopped | Shut down Java executors/workers first |
| Using main's `JNIEnv *` on another worker | `JNIEnv` is thread-local | `AttachCurrentThread` separately and detach when finished |
| Reports `NoClassDefFoundError` even though JAR has the class | Loader/module graph cannot see it, dependency error | Choose the right loader, classpath/module path, and dependencies |
| Storing local `jclass` in a static C variable | Reference expires/wrong thread | `NewGlobalRef` or look up in the right scope |
| Native host and JVM have different architectures | Link/load/JVM startup fails | Same ABI, architecture, and JDK libraries |

For debugging, you can add JVM startup options such as `-verbose:class` or use appropriate JDK logging, but **do not enable noisy logging in examples with deterministic stdout**. For class loading errors, logging the working directory, configured classpath, and exception stacktrace from the fatal path is usually enough to find the root cause.

## 11. Designing a Safe and Operable Native Host

### 11.1. Trust Boundaries

When a C host embeds the JVM in **the same process**, native memory bugs, native crashes, or `abort()` can bring down both the JVM and the host. Conversely, loaded Java code can read resources within the process under the host's OS permissions; JNI is not a sandbox for untrusted code.

Do not let external input arbitrarily dictate the class name, classpath, JVM options, method name, or JNI descriptor without going through an **allowlist** and validation. When untrusted plugins must be run, use process separation with appropriate privileges/cgroups/IPC instead of trusting that `FindClass` or a class loader provides sufficient isolation.

### 11.2. Define the Error Contract Before Coding

A native host typically has its own C API, for example returning:

```c
typedef enum {
    HOST_OK = 0,
    HOST_BAD_INPUT = 1,
    HOST_JAVA_FAILURE = 2,
    HOST_VM_FAILURE = 3
} HostStatus;
```

This is an **example return type for a production API**, not a complete program. The mapping table should clearly state:

- Java `NumberFormatException` → `HOST_BAD_INPUT` or parse error details.
- Java `IllegalArgumentException` → `HOST_BAD_INPUT` if the input is invalid per the contract.
- Java `OutOfMemoryError`/`LinkageError`/other exceptions → `HOST_JAVA_FAILURE`, with logging and a specific recovery policy, not automatically treated as a user error.
- Failure creating the JVM → `HOST_VM_FAILURE`.
- Success path → valid data + `HOST_OK`, without mixing error status into the numeric domain if negative numbers/0 can be valid results.

For a production API, it may be necessary to capture exception type/message/stacktrace as controlled data (without accidentally leaking secrets), instead of calling `ExceptionDescribe` directly to `stderr`.

### 11.3. Class Caching and Garbage Collection Management

Caching `jclass` can help avoid repeated lookups, but a local `jclass` must not outlive JNI threads or detach. If retained long-term, create a global reference; method IDs do not need `DeleteLocalRef` but must be bound to the lifetime of a valid class/class loader.

Java objects are managed by the JVM; the C host **must not `free(jobject)`**. Native buffers from `malloc` must be `free`d with the matching allocator; JNI buffers from `GetStringUTFChars` must be released with `ReleaseStringUTFChars`; different resources have different owners and release functions.

### 11.4. Concurrency and Serviceability

If the host has multiple native worker threads:

- Each thread needs its own `JNIEnv *`; do not share a single `JNIEnv *`.
- The Java entry point must be thread-safe or have synchronization mechanisms; do not assume a Java method is race-free just because it is called from C.
- Choose a concurrency cap and timeout for Java callbacks; a Java method can block, causing both the native worker and the JNI invocation to hold resources.
- Do not destroy the VM while workers are still calling JNI or holding Java refs.
- Create a clear bootstrap layer to manage initialization/shutdown, thread attachment, local/global refs, and reporting; avoid scattering `JNI_CreateJavaVM` throughout the application.

## 12. Testing and Evaluating Correctness

Minimum cases to verify:

1. **JVM creation:** VM startup with the right classpath, `JNI_CreateJavaVM == JNI_OK`, `env != NULL`; startup error path does not use `env`.
2. **Class lookup:** `FindClass("EmbeddedEntry")` succeeds; changing to an invalid class name or running in the wrong working directory must enter the error branch instead of dereferencing `NULL`.
3. **Method descriptor:** `javap -s -p EmbeddedEntry` confirms `evaluate(String) : int` has `(Ljava/lang/String;)I`; method ID is non-`NULL`.
4. **Success:** input `"21"` → `42`, host prints `ok=42`.
5. **Parse exception:** input `"bad"` → `NumberFormatException`, host explicitly clears and classifies it.
6. **Value-policy exception:** input `"-1"` → `IllegalArgumentException`, not confused with `NumberFormatException`.
7. **Unexpected Java exception:** input `"2147483647"` → `ArithmeticException` from `Math.multiplyExact`, fatal path prints error and exits nonzero.
8. **String reference cleanup:** every `jstring` returned by `NewStringUTF` has `DeleteLocalRef` called after use, even when the callback throws an exception.
9. **Throwable cleanup:** local `jthrowable` has `DeleteLocalRef` called after classification/rethrow; not used after deletion.
10. **Class references:** `entryClass` and exception class references are deleted before shutdown; `jmethodID` is not treated as a local ref.
11. **Shutdown:** `DestroyJavaVM` is called exactly once after cleanup; no Java non-daemon workers remain waiting indefinitely.
12. **Thread scope:** if adding a native worker thread, it must attach, obtain a new `JNIEnv *`, and detach; do not use main's JNI env in a worker.
13. **Deployment:** test the exact architecture/ABI on the target Linux system; verify the runtime loader finds `libjvm.so`.
14. **Security:** native host input/classpath/options must be controlled, and untrusted plugins must not be granted native privileges in the same process.

For large applications, add fault injection (lookup failure, invalid JVM option, Java callback throwing unexpected exceptions), native memory leak detection, and JVM/native thread profiling. Do not check only stdout; also check exit code, `stderr`, and that resources are released on time.

## 13. Checklist Before Integrating the JNI Invocation API

- Has the native host decided to use an **in-process embedded JVM** instead of spawning a Java process?
- Is there **exactly one place** responsible for creating/closing the JVM and owning startup options?
- Is the class name in `FindClass` in slash form, and is the classpath/module loader appropriate?
- Does the method ID use the right static/instance API, and has the descriptor been verified via `javap -s`?
- Are `jobject` arguments validly created with the right encoding, and are local refs cleaned up after use?
- After a Java callback, does the code check for a pending exception **before using the return value**?
- If `ExceptionOccurred` is called, is the local `jthrowable` cleaned up and the pending state handled intentionally?
- Are `FindClass`, `IsInstanceOf`, and most JNI functions avoided while an exception is still pending?
- Does the fatal path have clear logging/exit status, without assuming Java will catch the exception for C `main`?
- Is there a shutdown policy for Java executors and native workers so `DestroyJavaVM` does not wait indefinitely?
- Does each native thread have its thread-correct `JNIEnv *` and clear local/global ref lifetimes?
- Is there a deployment plan for the JVM library along with ABI and loader configuration on each operating system?

**Rule of thumb:** in a JVM-embedding application, C is the active party that **creates the VM → finds the class → finds the method → calls Java → handles pending exceptions → cleans up references → shuts down**. Do not treat `FindClass` as searching every class loader, do not guess method descriptors, and do not continue using normal JNI functions right after a Java callback throws an exception. A transparent *error policy* is needed at the native host/Java boundary, because C does not have Java's `try/catch`.

### Official References

- [Oracle Java SE 17 — JNI Invocation API: JNI_CreateJavaVM, AttachCurrentThread, DestroyJavaVM](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/invocation.html)
- [Oracle Java SE 17 — JNI Functions: FindClass, GetStaticMethodID, CallStaticIntMethod, ExceptionCheck, ExceptionOccurred](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [Oracle Java SE 17 — JNI Design Overview: exception handling, references, and garbage collection](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html)
- [Oracle Java SE 17 — javap for inspecting bytecode and descriptors](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html)
