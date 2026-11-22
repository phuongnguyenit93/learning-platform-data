# Calling Instance, Static, and Nonvirtual Methods from JNI

> **Context:** Java Advance → Native Interoperability → Calling Java from JNI. This article explains how C/C++ code uses the Java Native Interface (JNI) to call Java **instance methods**, **static methods**, and **nonvirtual instance methods**, where the most important difference is how the method to be executed is selected.

## 1. The Problem and Three Call Types

JNI allows native code running inside the JVM to access Java objects/classes and invoke Java methods through the `JNIEnv` function table. In C code, the three important API families are:

- `Call<Type>Method`: calls an **instance method** through a `jobject`. For overridable instance methods, the JVM applies **dynamic dispatch** based on the actual runtime type of the object.
- `CallStatic<Type>Method`: calls a **`static` method** through a `jclass`. There is no `jobject` receiver and no dynamic dispatch. A subclass `static` method can **hide**, but not override, a superclass `static` method of the same name.
- `CallNonvirtual<Type>Method`: calls an **instance method according to an explicitly specified class** using a `jclass` and a `jmethodID` obtained from that class; bypassing the subclass override selection mechanism. This is useful when intentionally invoking a superclass implementation on a subclass object.

`<Type>` in the API name is the **Java return type**: `Object`, `Void`, `Boolean`, `Byte`, `Char`, `Short`, `Int`, `Long`, `Float`, or `Double`. For example, a method returning `String` uses `CallObjectMethod` and receives a JNI `jobject` result (which can be cast to `jstring`); a method returning `int` uses `CallIntMethod` and receives `jint`; a method returning `void` uses `CallVoidMethod`.

**From C into Java** is different from **Java calling a native C function**: Java must declare `native` and load the library to enter C; whereas inside that native function, C can call back into Java methods using the three JNI API families above.

## 2. Method Selection Comparison Table

| Factor | `CallObjectMethod` / `Call<Type>Method` | `CallStaticObjectMethod` / `CallStatic<Type>Method` | `CallNonvirtualObjectMethod` / `CallNonvirtual<Type>Method` |
|---|---|---|---|
| Java Method | Instance, non-`static` | `static` | Instance, non-`static` |
| JNI Receiver | `jobject obj` | `jclass clazz` | `jobject obj` **and** `jclass clazz` |
| ID Lookup | `GetMethodID` | `GetStaticMethodID` | `GetMethodID` on the exact `clazz` to be selected |
| Implementation Selection Rule | Dispatches by the object's actual class when the method is overridable | Selects the `static` method by class/method ID | Selects the implementation by the specified `clazz`, bypassing subclass overrides |
| Corresponding Example | `receiver.greet("Lan")` | `Parent.kind()` | Close to the intent of calling `Parent`'s implementation on `Child`; in regular Java this can be seen when calling `super.greet(...)` |
| When Suitable | Callbacks into Java objects, polymorphism | Calling utility/factory/static configuration methods | Intentionally calling a superclass implementation; certain default interface method scenarios |

Imagine an actual object belonging to `Child extends Parent`, where `Child` overrides `greet` and both classes declare `static kind`:

```text
                 receiver = new Child()
                           |
          +----------------+-------------------+
          |                |                   |
 CallObjectMethod   CallNonvirtualObjectMethod CallStaticObjectMethod
 (receiver, id)     (receiver, Parent, id)      (Parent, staticId)
          |                |                   |
 Child.greet()      Parent.greet()             Parent.kind()
                                           
 CallStaticObjectMethod(Child, childStaticId) -> Child.kind()
```

**Important:** `CallNonvirtual` still requires an **actual object** as the receiver. It does not create a new object and does not turn the method into `static`. The `clazz` parameter determines which instance implementation is called.

## 3. Lookup: `jclass`, `jmethodID`, and JNI Descriptors

You must find the right **class** and **method ID** before calling:

```c
jclass parentClass = (*env)->FindClass(env, "JniCallsDemo$Parent");

jmethodID instanceId = (*env)->GetMethodID(
    env, parentClass, "greet",
    "(Ljava/lang/String;)Ljava/lang/String;");

jmethodID staticId = (*env)->GetStaticMethodID(
    env, parentClass, "kind",
    "()Ljava/lang/String;");
```

This is an **illustrative snippet**, assuming `env` and the Java classes exist and all steps succeed; full runnable code with error checking is in section 5.

- `jclass` is a reference to a Java `Class` object, not synonymous with an instance object. `FindClass` takes a **JNI binary name**: packages use `/` (e.g., `com/example/Parent`), and nested classes use `$` (e.g., `JniCallsDemo$Parent`).
- `jmethodID` is a method identifier in the JVM. It is **not** a `jobject` and must not be freed with `DeleteLocalRef`. `GetMethodID` finds **instance** methods; `GetStaticMethodID` finds **static** methods.
- Lookup must match both **name and descriptor**; a class with overloaded `greet(String)` and `greet(int)` has two different methods.
- `GetMethodID` and `GetStaticMethodID` may trigger **class initialization** if not yet initialized. A failed lookup returns `NULL` and usually sets a pending Java exception (such as `NoSuchMethodError`, `ExceptionInInitializerError`).

### How to Read Descriptors

The descriptor `(Ljava/lang/String;)Ljava/lang/String;` means: the parameter is `java.lang.String`, and the result is `java.lang.String`. The part before `)` is the parameter list, and the part after is the return type.

| Java Type | Descriptor |
|---|---|
| `boolean`, `byte`, `char`, `short` | `Z`, `B`, `C`, `S` |
| `int`, `long`, `float`, `double` | `I`, `J`, `F`, `D` |
| `void` (return type only) | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

For example: `int sum(int a, int b)` has descriptor `(II)I`; `void log(String s, boolean enabled)` is `(Ljava/lang/String;Z)V`; `String kind()` is `()Ljava/lang/String;`. In the terminal after `javac`, run `javap -p -s JniCallsDemo` or inspect the nested class to see the descriptors emitted by the compiler. When Java declares a native method, use `javac -h .` to generate the **JNI header with the exact C function name**; do not manually guess name mangling when packages, underscores, or overloads are involved.

## 4. C and C++ Syntax: Similar-Looking but Different Receiver

The examples use the **JNI C API**, where `JNIEnv *env` is a pointer to the function table and calls look like:

```c
(*env)->CallObjectMethod(env, receiver, instanceId, argument);
(*env)->CallStaticObjectMethod(env, parentClass, staticId);
(*env)->CallNonvirtualObjectMethod(
    env, receiver, parentClass, instanceId, argument);
```

If written in the **C++ JNI API**, the corresponding syntax is:

```cpp
env->CallObjectMethod(receiver, instanceId, argument);
env->CallStaticObjectMethod(parentClass, staticId);
env->CallNonvirtualObjectMethod(
    receiver, parentClass, instanceId, argument);
```

The difference above is the C/C++ JNI wrapper syntax; **the dynamic/static/nonvirtual dispatch rules remain the same**. Do not mix C-style `(*env)->...` with C++-style `env->...` in the same file.

In a **`static`** native method, the second JNI parameter is the `jclass` of the class declaring the native method; for an **instance** native method, the second parameter is `jobject thiz`. Java parameters are forwarded after the first two JNI parameters. `JNIEnv *` is only valid for the thread that owns it; do not share it across other threads.

## 5. Complete Runnable Example: All Three Call Types on the Same Object

The example has `Parent` and `Child`. `Child.greet(String)` **overrides** `Parent.greet(String)`, while `Child.kind()` **hides** `Parent.kind()`. A native JNI function `inspect` invokes four cases and returns a `String[]` array for Java to print the results.

**Requirements:** JDK 17+ and a C compiler that builds a shared library for the appropriate OS/CPU. The build commands below are for **Linux with GCC**; `JAVA_HOME` must point to the JDK directory.

### 5.1. Java File: `JniCallsDemo.java`

```java
public class JniCallsDemo {
    static {
        System.loadLibrary("jni_calls");
    }

    public static class Parent {
        public String greet(String name) {
            return "Parent hello " + name;
        }

        public static String kind() {
            return "Parent static";
        }
    }

    public static class Child extends Parent {
        @Override
        public String greet(String name) {
            return "Child hello " + name;
        }

        public static String kind() {
            return "Child static";
        }
    }

    private static native String[] inspect(Parent receiver, String name);

    public static void main(String[] args) {
        String[] output = inspect(new Child(), "Lan");

        System.out.println("virtual = " + output[0]);
        System.out.println("nonvirtual = " + output[1]);
        System.out.println("static Parent = " + output[2]);
        System.out.println("static Child = " + output[3]);
    }
}
```

Even though the `receiver` parameter is declared with type `Parent`, at runtime it points to **`new Child()`**. That is the key point to observe when comparing virtual and nonvirtual.

### 5.2. Generate the JNI Header

```bash
javac -encoding UTF-8 -h . JniCallsDemo.java
```

This command creates `JniCallsDemo.class`, the two nested classes, and `JniCallsDemo.h`. For the `static` native method on the `JniCallsDemo` class, the header describes the corresponding C function with the first parameter as `JNIEnv *`, the second parameter as `jclass`, followed by `jobject` (the `Parent`/`Child` object) and `jstring` (the name `Lan`).

### 5.3. C File: `JniCallsDemo.c`

```c
#include <jni.h>
#include "JniCallsDemo.h"

JNIEXPORT jobjectArray JNICALL Java_JniCallsDemo_inspect(
        JNIEnv *env, jclass owner, jobject receiver, jstring name) {
    (void) owner;

    // Binary name of a nested class uses '$'.
    jclass parentClass = (*env)->FindClass(env, "JniCallsDemo$Parent");
    if (parentClass == NULL) return NULL;

    jclass childClass = (*env)->FindClass(env, "JniCallsDemo$Child");
    if (childClass == NULL) return NULL;

    jclass stringClass = (*env)->FindClass(env, "java/lang/String");
    if (stringClass == NULL) return NULL;

    // Instance method: String greet(String).
    jmethodID greetId = (*env)->GetMethodID(
            env, parentClass, "greet",
            "(Ljava/lang/String;)Ljava/lang/String;");
    if (greetId == NULL) return NULL;

    // Two static methods with the same name belonging to two different classes.
    jmethodID parentKindId = (*env)->GetStaticMethodID(
            env, parentClass, "kind", "()Ljava/lang/String;");
    if (parentKindId == NULL) return NULL;

    jmethodID childKindId = (*env)->GetStaticMethodID(
            env, childClass, "kind", "()Ljava/lang/String;");
    if (childKindId == NULL) return NULL;

    // 1) Virtual: receiver is Child -> Child.greet is selected.
    jstring virtualResult = (jstring)(*env)->CallObjectMethod(
            env, receiver, greetId, name);
    if ((*env)->ExceptionCheck(env)) return NULL;

    // 2) Nonvirtual: Parent specified -> Parent.greet is selected.
    jstring nonvirtualResult = (jstring)(*env)->CallNonvirtualObjectMethod(
            env, receiver, parentClass, greetId, name);
    if ((*env)->ExceptionCheck(env)) return NULL;

    // 3) Static: no receiver needed; uses jclass and static method ID.
    jstring parentStaticResult = (jstring)(*env)->CallStaticObjectMethod(
            env, parentClass, parentKindId);
    if ((*env)->ExceptionCheck(env)) return NULL;

    jstring childStaticResult = (jstring)(*env)->CallStaticObjectMethod(
            env, childClass, childKindId);
    if ((*env)->ExceptionCheck(env)) return NULL;

    // Collect the four results into a Java String[].
    jobjectArray output = (*env)->NewObjectArray(
            env, 4, stringClass, NULL);
    if (output == NULL) return NULL;

    (*env)->SetObjectArrayElement(env, output, 0, virtualResult);
    if ((*env)->ExceptionCheck(env)) return NULL;

    (*env)->SetObjectArrayElement(env, output, 1, nonvirtualResult);
    if ((*env)->ExceptionCheck(env)) return NULL;

    (*env)->SetObjectArrayElement(env, output, 2, parentStaticResult);
    if ((*env)->ExceptionCheck(env)) return NULL;

    (*env)->SetObjectArrayElement(env, output, 3, childStaticResult);
    if ((*env)->ExceptionCheck(env)) return NULL;

    // Local JNI references are automatically freed when the native method returns.
    return output;
}
```

This is a **complete** JNI function for this example. If `FindClass`, `GetMethodID`, `GetStaticMethodID`, `NewObjectArray`, or a Java method throws an exception, JNI leaves the exception in a **pending** state and the C function returns, allowing the JVM to propagate the exception back to Java. You should not continue calling arbitrary JNI APIs while an exception is pending.

In this short example, the local references (three `jclass`, four `jstring`, the result array) are cleaned up when the native call finishes. When writing a **long native loop**, you need `DeleteLocalRef` or local frame management to avoid accumulating local references.

### 5.4. Compile the Native Library and Run

```bash
gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -o libjni_calls.so JniCallsDemo.c

java -Djava.library.path=. JniCallsDemo
```

On **JDK 24+**, you should explicitly grant native access to the application running on the classpath to avoid restricted native access warnings:

```bash
java --enable-native-access=ALL-UNNAMED \
  -Djava.library.path=. JniCallsDemo
```

**Expected stdout:**

```text
virtual = Child hello Lan
nonvirtual = Parent hello Lan
static Parent = Parent static
static Child = Child static
```

These lines prove three rules:

1. `CallObjectMethod` receives `greetId` looked up from `Parent` but **calls `Child.greet`** because the actual receiver is `Child`.
2. `CallNonvirtualObjectMethod` receives the **same** receiver and `greetId`, plus `parentClass`, so it **calls `Parent.greet`**.
3. The two `CallStaticObjectMethod` calls use two separate `jclass` + `jmethodID` pairs, calling `Parent.kind` and `Child.kind` respectively; there is no overriding for `static` methods.

On macOS and Windows, you need to build a `.dylib`/`.dll` using the corresponding toolchain and JNI header path (macOS: `include/darwin`; Windows: `include/win32`). The logical library name in Java remains `jni_calls`; the JVM maps this name to the OS-specific filename.

## 6. Dispatch Mechanism: Why Does One Method ID Yield Two Results?

Suppose the equivalent Java code is:

```java
JniCallsDemo.Parent p = new JniCallsDemo.Child();
System.out.println(p.greet("Lan"));                  // Child hello Lan
System.out.println(JniCallsDemo.Parent.kind());       // Parent static
System.out.println(JniCallsDemo.Child.kind());        // Child static
```

This is an **illustrative snippet**, not a standalone program. For a normal instance call, Java selects the implementation based on the actual class when the method is overridden. For `static`, the class name is determined by the compiled reference/method ID, whereas a nonvirtual call in JNI requires **implementation selection via the `jclass` parameter**.

Direct comparison:

```c
// Receiver has runtime class Child.
(*env)->CallObjectMethod(env, receiver, greetId, name);
// => Child.greet("Lan"), even though greetId was obtained from Parent.

// Bypass Child override, select Parent implementation.
(*env)->CallNonvirtualObjectMethod(
    env, receiver, parentClass, greetId, name);
// => Parent.greet("Lan").
```

**Do not replace `parentClass` with `GetObjectClass(receiver)` when the goal is to call the superclass.** `GetObjectClass(receiver)` returns the runtime class `Child`. With `CallNonvirtual...`, the class passed in must be the exact class you want to select, and the method ID must be obtained via `GetMethodID` on that class. Using a mismatched `jclass` and ID or an incompatible receiver is a serious bug in a native program.

`CallNonvirtual...` also supports special cases of **default methods on interfaces** according to JNI rules. However, it should not be understood merely as a mechanical translation of every `super` call in Java: the JVM has its own rules for `invokespecial`, private/constructor/interface calls. This article illustrates the easiest-to-verify case: selecting `Parent.greet` which has been overridden by `Child`.

## 7. Changing Return Types and Passing Arguments

All three API families have variants corresponding to the return type. Choose the right function according to the **actual return type of the Java method**:

| Java method | Instance | Static | Nonvirtual |
|---|---|---|---|
| `int size()` | `CallIntMethod` → `jint` | `CallStaticIntMethod` → `jint` | `CallNonvirtualIntMethod` → `jint` |
| `boolean ready()` | `CallBooleanMethod` → `jboolean` | `CallStaticBooleanMethod` → `jboolean` | `CallNonvirtualBooleanMethod` → `jboolean` |
| `String greet(String)` | `CallObjectMethod` → `jobject` | `CallStaticObjectMethod` → `jobject` | `CallNonvirtualObjectMethod` → `jobject` |
| `void reset()` | `CallVoidMethod` | `CallStaticVoidMethod` | `CallNonvirtualVoidMethod` |

Note: `jstring` is a JNI reference type compatible with `jobject`; cast appropriately when you know the method actually returns `String`. For a method returning `int`, use `CallIntMethod` instead of `CallObjectMethod`; mixing up return types leads to serious ABI/JNI errors.

Three ways to pass arguments:

- Standard form: `CallObjectMethod(env, receiver, greetId, name)` passes arguments directly after the ID.
- Suffix `A`: `CallObjectMethodA` takes a `jvalue[]` array. Suitable when building argument lists dynamically from a descriptor.
- Suffix `V`: `CallObjectMethodV` takes a C `va_list` (`V` does not mean `void`).

Equivalent example with one object parameter:

```c
// Snippet inside a JNI function, assuming variables are initialized.
jvalue args[1];
args[0].l = name;

jobject result = (*env)->CallObjectMethodA(
        env, receiver, greetId, args);
if ((*env)->ExceptionCheck(env)) {
    // Handle/propagate exception to Java; do not use result.
}
```

When passing primitive types, populate the corresponding member of the `jvalue` union, such as `.i` for `jint`, `.j` for `jlong`, `.z` for `jboolean`, `.d` for `jdouble`, etc. With `CallNonvirtual<Type>MethodA`, the order is still `env, obj, clazz, methodID, args`; with the static `A` form, it is `env, clazz, methodID, args`.

## 8. Exceptions, Reference Memory, and Lifecycle

### 8.1. Pending Java Exceptions

A `CallObjectMethod` call can cause Java code to throw a `RuntimeException`, `Error`, or another exception. JNI usually **does not automatically turn** that exception into a C exception. Native code must:

```c
jobject value = (*env)->CallObjectMethod(
        env, receiver, greetId, name);
if ((*env)->ExceptionCheck(env)) {
    // Do not use value; return from the native method so Java sees the exception.
    return NULL; // Only suitable for native methods returning a reference.
}
```

If the native method returns `jint`, the C return statement must return a valid `jint` (for example `0` when an exception is pending, with the Java caller above receiving the exception instead of the value). If the application genuinely wants to **translate an exception** into another error, you must understand which JNI APIs are allowed to be called while an exception is pending; typically you need to read/save the exception, intentionally clear it, and then rethrow/throw a new one. Do not use `ExceptionClear` just to ignore errors.

### 8.2. Local References, Global References, and `jmethodID`

- `jobject`, `jclass`, and `jstring` returned from JNI are normally **local references**: valid in the current native frame/thread and automatically cleaned up when the frame ends. In a long loop, creating many references without deleting them will exhaust the local reference table.
- To keep a class/object across multiple native calls or use it on another thread, consider `NewGlobalRef`, followed by `DeleteGlobalRef` at the appropriate time; Java references are not arbitrary C pointers.
- `jmethodID` is not a Java reference and **does not keep a class alive**. It can be cached for the lifetime of the class; when the class is unloaded, the ID becomes invalid. If caching long-term, you must manage the corresponding class/class loader lifecycle.
- `JNIEnv*` belongs to a thread; for a self-created native thread, you must attach via `JavaVM` properly and detach when finished. Do not retain `JNIEnv*` for use on another thread.

### 8.3. Do Not Confuse Class Lookup with Arbitrary Class Loaders

`FindClass(env, "JniCallsDemo$Parent")` inside a native method of `JniCallsDemo` can find the class through the class loader associated with the currently executing native method. However, `FindClass` when called from a self-attached native thread with no Java caller has different loader rules; classes belonging to a custom loader may not be found. When designing broad bindings, you can pass the class/class loader from Java, or store `jclass` as a global reference with a well-defined lifecycle.

Class names use slash `/` for packages and dollar `$` for nested classes; do not substitute Java dots in the `FindClass` string.

## 9. Common Errors and How to Diagnose Them

| Symptom / Mistake | Common Cause | Check / Fix |
|---|---|---|
| `NoSuchMethodError` on `GetMethodID` | Wrong descriptor, wrong case, using instance ID lookup for a static method | Check `javap -p -s`; distinguish `GetMethodID` and `GetStaticMethodID` |
| `ClassNotFound` / `NoClassDefFoundError` around `FindClass` | Wrong binary name `/` and `$`; class loader cannot find the class | Check binary name, class loader, and native thread context |
| `UnsatisfiedLinkError` | Missing `.so/.dll/.dylib` load, wrong architecture, missing dependent library, wrong JNI symbol name | Check `-Djava.library.path`, OS loader, `javac -h` header file, and exported symbols |
| Calling `Child.greet` when `Parent.greet` was expected | Used `CallObjectMethod` (virtual dispatch) | Use `CallNonvirtualObjectMethod` with the right `parentClass`/`greetId` |
| Calling `Parent.kind` when `Child.kind` was expected | Static methods do not override | Look up the static ID on `Child` and pass `childClass` |
| JVM crash or garbage result | Wrong object/class/method ID/return type/descriptor, using stale ref or ID | Verify signature and receiver, enable JNI checking |
| Java exception not seen in the right place | Continuing JNI calls while an exception is pending, or clearing and forgetting to throw | `ExceptionCheck` after lookup/invoke that may throw; propagate or translate intentionally |
| Local reference table overflow | Creating many refs in a long native loop | `DeleteLocalRef` or `PushLocalFrame`/`PopLocalFrame` |
| Callback fails on a native thread | Using `JNIEnv*` from another thread / not attached to JVM | `AttachCurrentThread`, get the thread's `JNIEnv*`, detach |
| Cached method ID fails after reload | Class/class loader was unloaded; local class reference went out of scope | Tie cache to loader/class lifecycle, manage global refs |

**Useful diagnostics in development:** run with `java -Xcheck:jni -Djava.library.path=. JniCallsDemo`. Several JNI mistakes can be detected early and reported in detail; depending on the JDK version, `--enable-native-access=ALL-UNNAMED` may also be needed. `-Xcheck:jni` does not guarantee catching all native memory bugs, but it is very useful before optimizing.

## 10. Workflow for Calling Java Methods Safely with JNI

1. **Define the Java contract:** owning class, static or instance, visibility, parameter/return types, whether it is overridden. Do not distinguish static from nonstatic by name alone.
2. **Generate the header:** use `javac -h` for the Java → JNI entrypoint; use `javap -p -s` to verify the descriptor of the Java method to be called from C.
3. **Find the class and ID:** `FindClass`/class ref, `GetMethodID` or `GetStaticMethodID`. If lookup fails or there is a pending exception, stop and propagate the error.
4. **Choose the right Call family for the purpose:** instance dynamic dispatch → `Call<Type>Method`; static → `CallStatic<Type>Method`; instance by explicit class → `CallNonvirtual<Type>Method`.
5. **Pass arguments properly:** Java primitives mapped to JNI primitives, Java objects to references, `jvalue[]` argument array if using `A`. Do not pass arbitrary pointers instead of `jobject`.
6. **Check after the call:** use `ExceptionCheck`/consistent exception handling before using the result. Ensure the returned reference is not freed prematurely.
7. **Manage lifetimes:** clean up local refs in many iterations; cache `jmethodID` per class lifecycle; global class refs when needed; `JNIEnv*` per thread.
8. **Test polymorphism behavior:** run the same `Child` receiver with both virtual and nonvirtual to verify the exact implementation called; test static hiding separately.
9. **Verify native deployment:** OS/CPU, symbols, dependent libraries, native access permissions on newer JDKs; use `-Xcheck:jni` during development.

Do not call nonvirtual just to be "faster." It changes the **semantics** of method dispatch and easily bypasses validation/invariants overridden in a subclass. Only use it when there is a clear, tested behavioral reason.

## 11. Comprehension Exercises

**Exercise 1 — predict the output.** Given `Child extends Parent`, both having `greet` overridden as in the demo. Native code obtains `greetId` from `Parent` and the receiver is `new Child()`. Does `CallObjectMethod` or `CallNonvirtualObjectMethod(env, receiver, parentClass, greetId, ...)` call `Parent.greet`? **Answer:** only nonvirtual with `parentClass`; virtual calls `Child.greet`.

**Exercise 2 — distinguish static hiding.** Add `public static String kind()` to both classes. If JNI uses `GetStaticMethodID(parentClass, "kind", "()Ljava/lang/String;")` and `CallStaticObjectMethod(parentClass, id)`, what does it return? **Answer:** `Parent static`; the receiver's runtime class is irrelevant.

**Exercise 3 — fix the descriptor.** Java has `public int score(String s, long threshold)`. Choose the JNI descriptor. **Answer:** `(Ljava/lang/String;J)I`. Choose `CallIntMethod` or `CallNonvirtualIntMethod` (if needing to specify a superclass implementation); for `static score`, use `GetStaticMethodID` + `CallStaticIntMethod`.

**Exercise 4 — check exceptions.** Modify `Child.greet` to throw `IllegalStateException` when the name is empty; call JNI with `""`. What must the C code do after `CallObjectMethod`? **Answer:** see that `ExceptionCheck` is non-zero, stop using the result, return from the native method or intentionally handle/translate the exception; the Java caller receives the Java exception if it is left pending.

**Exercise 5 — find the bug.** Native code obtains `jclass` via `GetObjectClass(receiver)` (where `receiver` is `Child`), then tries to use it to "call the superclass method." **Answer:** that is the `Child` runtime class; to call `Parent`, you need the `Parent` class reference and the `jmethodID` obtained on `Parent`.

## 12. Official References

- [Java Native Interface Specification — JNI Functions: Calling Instance, Static, Nonvirtual Methods](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html)
- [JNI Specification — Design Overview: Accessing Fields and Methods](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html)
- [JNI Specification — Types and Field/Method Descriptors](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html)
- [JDK Tool Specification — javac and the `-h` option](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [JDK Tool Specification — javap and the `-s` option](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javap.html)
- [JEP 472 — Prepare to Restrict the Use of JNI](https://openjdk.org/jeps/472)

When choosing an API, remember: **`Call<Type>Method` selects the implementation based on the runtime receiver; `CallStatic<Type>Method` selects a static method by class/ID; `CallNonvirtual<Type>Method` selects an instance implementation by an explicit `clazz`**. Looking up the right method ID, descriptor, receiver type, and handling exceptions are the minimum requirements for reliable JNI calls.
