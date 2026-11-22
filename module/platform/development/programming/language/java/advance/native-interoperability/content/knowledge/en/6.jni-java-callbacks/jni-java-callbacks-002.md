# Creating Java Objects via Constructors in JNI and Distinguishing from AllocObject

## Objectives

When C/C++ code running in JNI needs to **create a Java object**, there are two easily confused APIs:

- `NewObject` (or `NewObjectA`, `NewObjectV`): **creates the object and invokes the selected Java constructor**.
- `AllocObject`: **allocates the Java object without invoking any constructor** of that object.

Both return a `jobject` managed by the JVM; they are **not equivalent in initialization state**. Misinterpreting the difference easily produces objects with fields holding default values, breaking class invariants and causing Java methods to fail when used.

After this lesson, you will be able to identify a constructor with `GetMethodID` using the name `<init>`, understand the `(I)V` descriptor, create objects with `NewObject`, accurately interpret the effect of `AllocObject`, compile a Java 17 + JNI C example, handle exceptions, and manage local references safely.

## 1. Two Operations That Are Not the Same

| Criterion | `NewObject` | `AllocObject` |
|---|---|---|
| Purpose | Create and **initialize via constructor** | Only **allocate an instance** |
| Needs `jclass`? | Yes | Yes |
| Needs `jmethodID` of `<init>`? | Yes | No |
| Invokes the class constructor? | **Yes** | **No** |
| Runs the superclass constructor chain? | According to the semantics of the invoked Java constructor | **Does not** invoke any constructor of the object |
| Runs instance initializers? | Yes, following normal Java initialization flow | Does not run instance field initializers / instance initializer blocks |
| Fields after operation | Set by the constructor and initializers | JVM default values: `0`, `false`, `null`… |
| Side effects in constructor | Occur, or the constructor throws an exception | Do not occur |
| Safety for application objects | The standard choice | Easily creates an invalid state; use only intentionally |
| JNI return value | `jobject` or `NULL` if creation fails | `jobject` or `NULL` if allocation fails |

Key point: **`AllocObject` is not a "slightly faster" version of `NewObject`**. It changes initialization semantics. An object that exists on the heap without a constructor may not satisfy any assumptions made by the class's Java methods.

It is also necessary to distinguish **class initialization** (usually involving `<clinit>` and `static` fields) from **instance initialization** (running the `<init>` constructor). Finding a class or calling `GetMethodID` can lead to class initialization according to JNI/JVM rules; that **does not mean** `AllocObject` runs the instance constructor. The two processes are separate.

## 2. How Is a Java Object Normally Created?

In Java:

~~~java
final class UserProfile {
    private final int id;
    private String status = "initial";
    private static int constructed;

    UserProfile(int id) {
        this.id = id;
        this.status = "ready";
        constructed++;
    }

    String getStatus() {
        return status;
    }
}
~~~

The Java expression `new UserProfile(42)` performs allocation and initialization according to the language rules. In the constructor, the appropriate `this(...)`/`super(...)` call chain is executed; the class's instance initializers are run at the position specified by the language; the constructor body assigns `id`, updates `status`, and increments `constructed`. Upon returning normally, the object satisfies the invariants promised by the constructor.

In JNI, an equivalent call in intent is:

~~~c
jmethodID ctor = (*env)->GetMethodID(env, cls, "<init>", "(I)V");
jobject user = (*env)->NewObject(env, cls, ctor, (jint)42);
~~~

By contrast:

~~~c
jobject raw = (*env)->AllocObject(env, cls);
~~~

allocates the object with `id == 0` and `status == NULL` (`null` on the Java side). The value `"initial"` **has not been assigned either**: instance field initializers in Java source are executed through the constructor, not automatically run by the JVM after `AllocObject`. `constructed` does not increment due to `AllocObject`.

In this example, `status.equals("ready")` on an object just created with `AllocObject` can throw `NullPointerException`. Classes containing resource handles, locks, collections, `final` fields, or parameter checks in the constructor are even more likely to suffer severe consequences.

## 3. Three Mandatory Components to Invoke a Constructor from JNI

### 3.1. `JNIEnv*` Is the Function Table of the Calling Thread

In C, JNI functions are accessed via:

~~~c
(*env)->FindClass(env, "example/UserProfile");
(*env)->GetMethodID(env, cls, "<init>", "(I)V");
(*env)->NewObject(env, cls, ctor, (jint)42);
~~~

`env` is the JNI interface pointer for the current thread. Do not pass `JNIEnv*` to another native thread; a native thread wanting to call the JVM must have a valid JNI environment for **that thread itself** through the appropriate attach mechanism.

### 3.2. `jclass` Identifies the Exact Class to Create

Example:

~~~c
jclass cls = (*env)->FindClass(env, "example/UserProfile");
if (cls == NULL) {
    return NULL; // Preserve the pending JNI error so Java receives it.
}
~~~

Class names in `FindClass` use `/` for packages: `example/UserProfile`, **not** `example.UserProfile`. For nested classes, use the binary name, for example `"JniConstructorDemo$Sample"` in the complete runnable program below.

`jclass` is a JNI reference to the `java.lang.Class` object. It is not the native address of a Java object structure; no C cast turns it into an internal JVM field layout.

### 3.3. `GetMethodID` Uniquely Identifies the Constructor

~~~c
jmethodID ctor = (*env)->GetMethodID(
        env, cls, "<init>", "(I)V");
if (ctor == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return NULL;
}
~~~

- The special name `<init>` is the JVM name for an **instance constructor**, not the class name or the string `"UserProfile"`.
- The descriptor `(I)V` means "takes one `int`, returns `void`". A constructor always has the return descriptor `V`.
- `()V` corresponds to a no-argument constructor; `(Ljava/lang/String;I)V` corresponds to `(String, int)`; `([I)V` corresponds to a single `int[]` parameter.
- `GetMethodID` is used for instance methods/constructors; `GetStaticMethodID` is not used for `<init>`.
- You must match the **exact** parameter list when overloaded constructors exist. `GetMethodID` returns `NULL` when not found and may produce `NoSuchMethodError`; it can also trigger class initialization and throw initializer-related exceptions.
- `jmethodID` is a native method ID, **not a local reference**: do not call `DeleteLocalRef` on this ID.

If `FindClass` or `GetMethodID` encounters an error, do not continue using a `NULL` class/ID. The proper approach is usually to return and let the pending JNI exception propagate back to Java.

## 4. Calling `NewObject` and Its Three Argument-Passing Variants

Basic syntax:

~~~c
jobject NewObject(JNIEnv *env, jclass clazz, jmethodID ctor, ...);
jobject NewObjectA(JNIEnv *env, jclass clazz, jmethodID ctor,
                   const jvalue *args);
jobject NewObjectV(JNIEnv *env, jclass clazz, jmethodID ctor,
                   va_list args);
~~~

All three forms initialize an object using the selected constructor. The difference is **how arguments are represented**:

- `NewObject`: passes arguments directly after `ctor`, suitable for simple calls.
- `NewObjectA`: passes a `jvalue` array, useful when the number/types of arguments are prepared structurally.
- `NewObjectV`: passes a `va_list` from a variadic C wrapper function.

Example for constructor `(I)V`:

~~~c
// Pass directly; ctor obtained from GetMethodID(..., "<init>", "(I)V").
jobject a = (*env)->NewObject(env, cls, ctor, (jint)42);

// Equivalent in intent: jvalue array form.
jvalue params[1];
params[0].i = (jint)42;
jobject b = (*env)->NewObjectA(env, cls, ctor, params);
~~~

This is an **illustrative JNI snippet**, assuming `env`, `cls`, and `ctor` are valid and there is no pending exception. If you want to use both `a` and `b`, you must handle the results and local references properly. Do not apply `NewObjectA` to a constructor by guessing the signature: the `jvalue` array must match the descriptor and parameter order exactly.

`NewObject` returns a reference to the **new instance**; the constructor chain is run, and an exception in the constructor (if any) causes object creation to fail according to the JNI contract. Do not use the result before checking for errors.

## 5. Complete Java 17 + JNI C Example: Seeing the Difference Clearly

The example creates the same Java class using two native functions. The output shows that the constructor and instance field initializers run in the `NewObject` branch, but are skipped in the `AllocObject` branch. We use a nested `static` class to eliminate the implicit outer instance parameter.

### 5.1. Java File: `JniConstructorDemo.java`

~~~java
public final class JniConstructorDemo {
    static {
        System.loadLibrary("jniconstructdemo");
    }

    private static native Sample newByConstructor(int id);
    private static native Sample newByAllocObject();

    public static final class Sample {
        private static int constructorCalls;
        private final int id;
        private int marker = 7;
        private String phase = "field-initializer";

        public Sample(int id) {
            if (id < 0) {
                throw new IllegalArgumentException("id must be non-negative");
            }
            this.id = id;
            this.phase = "ready";
            constructorCalls++;
        }

        String describe() {
            return "id=" + id
                    + ", marker=" + marker
                    + ", phase=" + phase;
        }

        static int constructorCalls() {
            return constructorCalls;
        }
    }

    public static void main(String[] args) {
        Sample constructed = newByConstructor(42);
        Sample allocatedOnly = newByAllocObject();

        System.out.println("NewObject: " + constructed.describe());
        System.out.println("AllocObject: " + allocatedOnly.describe());
        System.out.println(
                "constructorCalls=" + Sample.constructorCalls());
    }
}
~~~

Intentional details in `Sample`:

- `id` is `final` and is only assigned in the constructor.
- `marker = 7` and `phase = "field-initializer"` are **instance field initializers**, executed on the normal initialization path.
- The constructor changes `phase` to `"ready"` and increments the `static constructorCalls` counter.
- `describe()` intentionally only concatenates strings so `null` can be observed; a real method might dereference `phase` and fail on an uninitialized object.
- `Sample` is declared `static`, so the `(I)V` constructor has only the `int` parameter; a **non-static** inner class can have an additional constructor parameter for the enclosing instance at the bytecode level.

### 5.2. Generating the JNI Header from Java Source

In the directory containing the Java file, run with JDK 17 or higher:

~~~bash
javac -h . JniConstructorDemo.java
~~~

The command above compiles `JniConstructorDemo.class`, `JniConstructorDemo$Sample.class` and generates `JniConstructorDemo.h`. The name/parameters of the JNI exported function are generated from the **actual native method declaration**, avoiding having to guess name mangling rules. If the package is changed, the JNI name and `FindClass` must be changed accordingly.

### 5.3. C File: `jniconstructdemo.c`

~~~c
#include "JniConstructorDemo.h"

JNIEXPORT jobject JNICALL
Java_JniConstructorDemo_newByConstructor(
        JNIEnv *env, jclass declaringClass, jint id) {
    (void)declaringClass;

    jclass sampleClass = (*env)->FindClass(
            env, "JniConstructorDemo$Sample");
    if (sampleClass == NULL) {
        return NULL; // Do not use jclass when FindClass fails.
    }

    jmethodID ctor = (*env)->GetMethodID(
            env, sampleClass, "<init>", "(I)V");
    if (ctor == NULL) {
        (*env)->DeleteLocalRef(env, sampleClass);
        return NULL; // Preserve the exception reported by JNI.
    }

    jobject result = (*env)->NewObject(
            env, sampleClass, ctor, id);

    // Delete the local reference to the Class; result is still returned to Java.
    (*env)->DeleteLocalRef(env, sampleClass);
    return result;
}

JNIEXPORT jobject JNICALL
Java_JniConstructorDemo_newByAllocObject(
        JNIEnv *env, jclass declaringClass) {
    (void)declaringClass;

    jclass sampleClass = (*env)->FindClass(
            env, "JniConstructorDemo$Sample");
    if (sampleClass == NULL) {
        return NULL;
    }

    // Do not look up <init>, do not pass arguments, do not run constructor.
    jobject result = (*env)->AllocObject(env, sampleClass);

    (*env)->DeleteLocalRef(env, sampleClass);
    return result;
}
~~~

Explanation:

1. Both native functions are called **from Java into C**, then **C creates a Java object** via JNI and returns the same Java type `Sample`. This is a concrete case of "calling Java from JNI".
2. For a static native method, the second JNI parameter has type `jclass` (the class declaring the native method). If the native method is an instance method, that parameter is the `jobject` of the receiver.
3. `FindClass("JniConstructorDemo$Sample")` uses the binary name of the nested class in the default package. For a `demo` package, the corresponding string would be `"demo/JniConstructorDemo$Sample"`.
4. `NewObject` invokes the exact `Sample(int)` constructor. `AllocObject` neither looks up nor executes `<init>`.
5. Upon success, `FindClass` creates a local reference. Deleting `sampleClass` with `DeleteLocalRef` in the appropriate branches is safe. `result` is returned to Java as a valid local reference; do not release this reference right before returning.
6. If the constructor throws an exception, `NewObject` can return `NULL` with the Java exception pending. `DeleteLocalRef` is among the reference cleanup operations allowed when an exception is pending. Avoid calling further JNI APIs arbitrarily before handling the exception.
7. A JNI object reference is **not a `malloc` pointer** and cannot be directly dereferenced to read `Sample.id` using a C struct. The JVM manages objects and garbage collection.

### 5.4. Compiling the Native Library

Set `JAVA_HOME` to point to a **JDK 17+ of the matching architecture** of the running process. The commands below assume you are in the directory containing `JniConstructorDemo.java`, `JniConstructorDemo.h`, and `jniconstructdemo.c`.

**Linux with GCC:**

~~~bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/linux" \
    jniconstructdemo.c -o libjniconstructdemo.so

java -Djava.library.path=. JniConstructorDemo
~~~

**macOS with Clang:**

~~~bash
clang -dynamiclib -Wall -Wextra \
    -I"$JAVA_HOME/include" -I"$JAVA_HOME/include/darwin" \
    jniconstructdemo.c -o libjniconstructdemo.dylib

java -Djava.library.path=. JniConstructorDemo
~~~

**Windows with MSVC Developer Command Prompt:**

~~~bat
cl /LD /I "%JAVA_HOME%\include" /I "%JAVA_HOME%\include\win32" jniconstructdemo.c /Fe:jniconstructdemo.dll
java -Djava.library.path=. JniConstructorDemo
~~~

These are three **OS-specific build options**, only run the corresponding branch. The native filename satisfies `System.loadLibrary("jniconstructdemo")` on that platform. For Linux/macOS, use a shell supporting `$JAVA_HOME` and line continuation with `\`; for Windows, use a Command Prompt with the MSVC toolchain and `%JAVA_HOME%`. The library must be built for the **exact architecture/ABI of the JVM** and have all dependencies available so the loader can open it.

### 5.5. Expected Output

When built and loaded successfully on a compatible JVM:

~~~text
NewObject: id=42, marker=7, phase=ready
AllocObject: id=0, marker=0, phase=null
constructorCalls=1
~~~

**Why?**

- `NewObject(…, 42)` creates `Sample`, runs instance initializers (`marker = 7`, `phase = "field-initializer"`), executes the constructor, changes `phase = "ready"`, and increments the counter to 1.
- `AllocObject` still creates a `Sample` instance that can be returned to Java, but **does not run instance initializers or constructors**. Therefore `id` and `marker` are at their default value `0`, and `phase` is `null`.
- The `static` counter only increments in the constructor, so the final result is `1`. This is an observation for this specific example; do not use such a counter in place of an object state verification mechanism in real software.

**`GetMethodID` is not needed with `AllocObject`.** If you confuse `AllocObject` with `NewObject`, the program may still compile and load the library successfully, but return objects that break the invariants the constructor is supposed to guarantee.

## 6. Constructors, Field Initializers, and Class Initializers: Distinguishing Correctly

In Java, source code may contain:

~~~java
final class Example {
    static int classState = initializeClass();

    private final int identifier;
    private int instanceState = 10;

    {
        instanceState += 5;  // instance initializer block
    }

    Example(int identifier) {
        this.identifier = identifier;
    }

    private static int initializeClass() {
        return 20;
    }
}
~~~

This is an **illustrative Java structure snippet**, not a self-contained runnable program. Meaning:

- `classState` is **static class state**; class initialization steps follow the JVM/JLS lifecycle, not by default "once per created object".
- `instanceState = 10` and the block adding 5 are **instance initialization**; on the normal initialization path, they are executed through the constructor (while following `super`/`this` ordering).
- `identifier` is `final` per instance; the Java compiler checks its assignment when the constructor completes normally.

**`GetMethodID` can cause initialization of an uninitialized class**, so when testing `AllocObject` you must not say that "none of the class's initializers run". The accurate thing to remember is: `AllocObject` **does not invoke the object's constructor**, so it does not run the *instance* initialization encoded in those constructors. In the example program, the static counter exists and has value 0 by default initialization rules even though the instance allocated with `AllocObject` is uninitialized.

With `NewObject`, if the constructor has a `super(...)` call, the superclass constructor chain is executed according to Java semantics. With `AllocObject`, there is no such constructor chain. An instance may carry the full runtime type yet **not be set up like an object created with Java `new`**.

### `final` Does Not Make `AllocObject` Automatically Assign Fields

`private final int id` helps the compiler enforce variable assignment in normal Java source. But when `AllocObject` bypasses the constructor, the new object's `id` value remains the default `0`. Do not infer that "a final field has definitely received a valid value". If a class relies on a `final String token` that is never null in normal initialization flow, `AllocObject` can create a `token == null` state. Assumptions regarding immutable objects, publication, and the Java Memory Model may also no longer hold as the application expects.

Using `Set<Field>` via JNI to patch fields after `AllocObject`, especially `final` fields, does not automatically restore invariants, parameter validation, resource lifetimes, constructor chains, and safety guarantees of a properly constructed object. **Prefer calling the constructor via `NewObject`** when a usable object is needed.

## 7. Exceptions: Do Not Treat `NULL` as Success

### When `FindClass` Fails

An incorrect binary class name, the class not being visible to the class loader, or a loading error can cause `FindClass` to return `NULL` with a pending exception, such as `NoClassDefFoundError`. Do not call `GetMethodID` with `cls == NULL`.

### When `GetMethodID` Fails

A nonexistent `(I)V` constructor or wrong signature can produce `NoSuchMethodError`. `GetMethodID` can also cause `ExceptionInInitializerError` if the class initializer fails. Check the result before using `ctor`.

### When `NewObject` Fails

If the constructor throws `IllegalArgumentException`, `IOException`, or another Java exception (depending on the constructor), the error is reflected back to Java. `NewObject` can also fail with `InstantiationException` for classes that cannot be instantiated by contract and `OutOfMemoryError`. Do not continue accessing the object after observing a JNI exception.

In the complete runnable example, if you deliberately call `newByConstructor(-1)`, the `Sample(int)` constructor throws `IllegalArgumentException("id must be non-negative")`. JNI does not need to turn that exception into `NULL` and hide it; returning `NULL` while the exception is pending will let Java receive the exact exception.

### When `AllocObject` Fails

`AllocObject` does not take a constructor, so it **cannot throw an exception originating from the constructor body** of that object. However, the API can still return `NULL`; notably `InstantiationException` if `clazz` points to an interface or abstract class, and `OutOfMemoryError` if memory is exhausted. `clazz` must not be an array class. Do not use `AllocObject` to create arrays; there are dedicated JNI array creation APIs such as `NewObjectArray`.

### Post-JNI-Call Handling Pattern

~~~c
jobject object = (*env)->NewObject(env, cls, ctor, (jint)42);

if ((*env)->ExceptionCheck(env)) {
    // Pending exception; clean up allowed local refs and return.
    (*env)->DeleteLocalRef(env, cls);
    return NULL;
}
if (object == NULL) {
    // Check/report error according to the application's contract.
    // Do not assume a NULL jobject is an initialized object.
}
~~~

This is an **illustrative code snippet** inserted inside a JNI function that already has valid `env`, `cls`, and `ctor` variables. Some JNI functions can return `NULL` due to an error without throwing an exception; if `object == NULL` yet there is no pending exception, the native method should turn the failure into an explicit exception/error path rather than silently returning "success".

According to JNI, when an exception is pending you may only use JNI operations permitted in that state (such as cleaning up local references); do not arbitrarily call `GetFieldID`, `CallObjectMethod`, or `NewObject` next. `ExceptionClear` should only be used when you actually intend to handle and replace the error, not to clear an exception just to let the program continue.

## 8. Managing `jobject`, `jclass`, and JNI Reference Lifetimes

Both `NewObject` and `AllocObject` return a **JNI object reference**, not a C pointer to field locations on the Java heap.

- `jobject` is a reference to a Java object; the JVM/GC may move the object while managing the heap. Do not cast `jobject` to `struct Sample*`.
- `jclass` is a reference to a Class object. `FindClass` normally returns a local reference; when no longer needed, call `DeleteLocalRef`.
- `jmethodID` is an identifier, not an object reference; **do not** call `DeleteLocalRef` on it.
- Local references created during a native call are scoped to the native frame; when returning a `jobject` from a JNI native method, the JVM handles the returned reference so Java receives the object. Avoid calling `DeleteLocalRef` on `result` itself before returning.
- When creating many objects in a long JNI loop, clean up local references on each iteration or use `PushLocalFrame`/`PopLocalFrame`. Do not let the local-ref table overflow.
- If you need to keep a reference across native calls, use `NewGlobalRef`/`DeleteGlobalRef` with a clear lifecycle; do not cache a local `jclass` or `jobject` across calls.
- `JNIEnv*` is bound to a thread; do not cache it and use it from another thread.

### Class Loaders and `FindClass`

In the example, `FindClass("JniConstructorDemo$Sample")` is inside a native method called from Java, so it has the appropriate class loader context of the class declaring the native method. For C code running from a native thread that just called `AttachCurrentThread` or when using a custom class loader, class lookup rules may differ. If lookup is unreliable, pass `Class<?>` from Java or manage the class loader/global reference appropriately; **do not assume every class can be found by `FindClass` via the system loader**.

Therefore, the example must not copy the exact `FindClass` call into a native thread with no Java caller frame and assume it still resolves the same application class.

## 9. When Does `AllocObject` Actually Have a Reason to Exist?

`AllocObject` is an intentional API for special runtime mechanisms, such as controlled object state restorers, certain serialization/VM integration frameworks, or native algorithms with a specific contract to allocate first and finalize the object later. The validity of these cases depends heavily on the target class, JVM version, and framework guarantees.

It is **not** the default choice when:

- Creating domain objects that require constructor validation, non-null fields, immutable state, or resource initialization.
- Wanting to avoid constructor overhead while still expecting the object to behave as if it went through `new`.
- Wanting to bypass permission checks or business constraints in the constructor.
- Lacking a proven plan for `final` fields, inheritance, lifecycle, exception cleanup, and cross-thread publication.

Even if you use `AllocObject` and then try to invoke a private constructor via JNI, that is an advanced initialization flow prone to errors. When you simply need to "create and initialize via constructor", `NewObject` already performs both steps in one API and is usually the shortest, clearest path.

### Better Options for Classes with Complex Constructors

If a constructor does a lot of work or its signature changes frequently, you can move the complex initialization into a **Java static factory method** with a clear contract, then have JNI use `GetStaticMethodID` + `CallStaticObjectMethod` to call the factory. That approach still executes Java logic as designed and can return subtypes, cached instances, or reusable objects depending on the factory contract. Do not automatically replace a factory with `AllocObject`.

Java example:

~~~java
public static UserProfile createValidated(int id) {
    if (id <= 0) {
        throw new IllegalArgumentException("id must be positive");
    }
    return new UserProfile(id);
}
~~~

This is an **illustrative Java snippet** inside an appropriate class; it is not a standalone program. When JNI calls the factory, it must use the exact return descriptor, for example `(I)Lexample/UserProfile;` for a class in the `example` package. `GetStaticMethodID` is not used for the `<init>` constructor; it is used for the `createValidated` factory method.

## 10. Common Errors and How to Find the Cause

| Symptom | Likely Cause | How to Check |
|---|---|---|
| `GetMethodID` returns `NULL` | Wrong `<init>` or descriptor; class not loaded/initializer failed | Inspect bytecode with `javap -s -p` and pending exception |
| `NewObject` returns `NULL` | Constructor threw an exception or allocation failed | Check `ExceptionCheck`, preserve original stack trace |
| `AllocObject` returns object but fields "lose values" | Instance field initializers/constructor did not run | Compare with `NewObject`, inspect zero/null defaults |
| `final` field observed as 0/null | Constructor bypassed via `AllocObject` | Do not treat `final` as proof of initialization |
| `NullPointerException` when calling method after `AllocObject` | Method relies on non-null invariants | Initialize via constructor/factory |
| `NoClassDefFoundError` despite correct source class name | Wrong binary name `$`/`/` or class loader | Check `javap` and loader context |
| `UnsatisfiedLinkError` before seeing output | Wrong library name, missing file, mismatched ABI/dependency | Check `System.loadLibrary`, `java.library.path`, and binary |
| Native crash/VM abort after failed lookup | Continued using `NULL` or made invalid JNI calls while exception pending | Check every return value and exception state |
| Local reference table overflow in loop | Retained too many local `jobject`/`jclass` | `DeleteLocalRef` or JNI local frame |
| Class lookup fails from native thread | `FindClass` lacks the expected application loader | Pass Class/loader or store a valid global reference |

To inspect what descriptor a constructor actually has:

~~~bash
javap -s -p 'JniConstructorDemo$Sample'
~~~

This command reads the compiled bytecode in the same directory and typically displays the constructor like:

~~~text
public JniConstructorDemo$Sample(int);
  descriptor: (I)V
~~~

This is a **relevant excerpt** from `javap` output (the full output also lists other fields and methods). On Windows Command Prompt, you can use double quotes to avoid shell syntax differences; on POSIX shells, single quotes preserve the `$` character.

## 11. Code Review Checklist for JNI Object Creation

When encountering a native method that creates a Java object, ask in order:

1. **Which class?** Does `jclass` have the right binary name and class loader? Is it a concrete class, not an interface/abstract/array?
2. **Is a constructor needed?** For normal domain objects, the answer is **yes**; use `GetMethodID("<init>", descriptor)` + `NewObject`, or a Java factory with a clear contract.
3. **Is the descriptor right?** Verify with `javap -s -p`, do not guess from class name or overloads; match primitive/reference/array types and `V` for constructors.
4. **Are the arguments right?** Use JNI types (`jint`, `jlong`, `jobject`...) and order matching the descriptor; with `NewObjectA`, match each position in the `jvalue` array.
5. **Is error checking present?** `FindClass`, `GetMethodID`, and `NewObject` can fail. Do not proceed as if the object exists, and do not clear pending exceptions arbitrarily.
6. **Do references have the right lifetime?** Clean up unneeded local refs; do not delete the returned reference, and do not store local references across native calls.
7. **Is class initialization confused with instance initialization?** Seeing a static initializer run does not mean the constructor ran; check fields and constructor side effects.
8. **Is there real execution evidence?** Build with the matching JDK/native compiler, load the library for the right target, compare `NewObject`/`AllocObject` output; add tests for constructors throwing exceptions and abstract classes if the application actually needs to support these cases.

## 12. Practice Exercises

**Exercise 1 — Predict the output.** With `Sample` in the full program, if you call `newByConstructor(10)` then `newByAllocObject()` and finally print `Sample.constructorCalls()`, explain why the second object has `phase == null` even though the source declares `phase = "field-initializer"`. Answer: instance initializers belong to the constructor path; `AllocObject` only allocates an object with default field values.

**Exercise 2 — Descriptor.** Write the constructor:

~~~java
public Sample(int id, String phase) {
    this.id = id;
    this.phase = phase;
}
~~~

Assuming you replace the old constructor with this constructor in the same class, the new descriptor is `(ILjava/lang/String;)V`. In JNI, use `GetMethodID(env, cls, "<init>", "(ILjava/lang/String;)V")` and pass the corresponding `jint` and `jstring` to `NewObject`. If you do not update the descriptor, `GetMethodID` for `(I)V` will fail. **The Java snippet is only an exercise variant**, and cannot be placed side-by-side in the `Sample` program above without adjusting the field assignment rules accordingly.

**Exercise 3 — Constructor error.** Call `newByConstructor(-1)` and catch `IllegalArgumentException` in Java. Confirm that the exception from the constructor propagates back through JNI; when switching to `newByAllocObject()`, no `id` argument or `id < 0` check is performed. Conclude that `AllocObject` is not a safe "fast object creation" shortcut if the constructor validates data.

**Exercise 4 — Code review.** A JNI function uses `AllocObject` to create a `Session` object whose `final String token` is assigned in the constructor, then returns it to Java. Later, `token.length()` throws `NullPointerException`. Fix it using the appropriate constructor/factory and test the error path as well; do not fix it by assuming `final` fields are automatically initialized.

## Official Documentation

- [JNI Functions — AllocObject, NewObject, GetMethodID, and reference management (Oracle JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html)
- [JNI Types and Data Structures — method signatures, native types, and references (Oracle JDK 17)](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/types.html)
- [Java Language Specification, chapter on object creation and class/instance initialization (JLS 17)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html)

## Key Takeaways

**`NewObject` = allocate + invoke Java constructor**, requiring the right `jclass`, `GetMethodID("<init>", descriptor)`, and arguments. **`AllocObject` = allocate an instance while skipping all constructors**; instance field initializers do not run either, so the object carries default field values that can violate invariants.

Class initializers and instance constructors are two different concepts. `jobject` remains a JVM-managed reference, not a C memory pointer. When creating usable application objects, prefer **constructors/factories**, check for exceptions, and release local references according to their proper lifecycle.
