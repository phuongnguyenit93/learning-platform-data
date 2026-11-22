# JNIEnv Parameter Along with jobject or jclass at the Beginning of a JNI Function

When calling a Java method declared as **native**, the Java Virtual Machine (JVM) transfers execution control to the corresponding C/C++ function. The native function receives **two parameters implicitly provided by the JVM at the beginning of the list**: **JNIEnv \*env** and **jobject** (instance method) **or jclass** (static method). After those two parameters come the parameters declared in the Java code.

This is the core rule when writing your first JNI function: **env provides the API to interact with the JVM; the second parameter indicates the object or class context; the subsequent parameters are the actual data of the Java call.** The first two parameters do not appear in the Java method declaration and are not explicitly passed by the Java programmer.

## 1. From Java Declaration to C Function Signature

Consider two independent methods:

~~~java
class Example {
    native int addOne(int value);            // instance
    static native int addTwo(int value);     // static
}
~~~

With the standard JNI naming convention, the corresponding C functions have the form:

~~~c
/* Two illustrative prototypes; #include <jni.h> is required for JNI types. */

JNIEXPORT jint JNICALL Java_Example_addOne(
        JNIEnv *env, jobject self, jint value);

JNIEXPORT jint JNICALL Java_Example_addTwo(
        JNIEnv *env, jclass clazz, jint value);
~~~

| Position in C function | Instance native | Static native | Passed by whom? |
| --- | --- | --- | --- |
| 1 | **JNIEnv \*env** | **JNIEnv \*env** | JVM; interface for calling JNI functions |
| 2 | **jobject self** | **jclass clazz** | JVM; receiver or class declaring the native method |
| 3 | **jint value** | **jint value** | The **int value** argument in the Java call |
| Return value | **jint** | **jint** | C function returns to Java |

Variable names like **env**, **self**, **thiz**, **obj**, **clazz**, or **klass** are just names chosen by the C author; **the type, position, calling convention, and signature** are what determine the correct ABI linkage. Java has no declaration like **addOne(JNIEnv env, Object self, int value)**; the JVM automatically passes the first two arguments of the C function.

~~~text
Java:  new Example().addOne(10)
                 |
                 v
JVM:   Java_Example_addOne(env, thisObject, 10)
                                     ^
                                 jobject self

Java:  Example.addTwo(10)
                 |
                 v
JVM:   Java_Example_addTwo(env, Example.class, 10)
                                     ^
                                 jclass clazz
~~~

The examples illustrate the calls logically. The JVM performs the handoff through the native ABI itself; Java code does not directly call the C function as a function pointer.

## 2. What is JNIEnv* and What Is It Used For?

**JNIEnv** is a type provided by **jni.h**, representing the JVM's JNI function interface. It allows native code to access Java validly: finding classes, reading/writing fields, calling methods, creating strings/arrays, checking/throwing exceptions, and managing JNI references.

Common calls:

| Task | JNI Function |
| --- | --- |
| Get the runtime class of an object | **GetObjectClass** |
| Find an instance field | **GetFieldID** |
| Read an int instance field | **GetIntField** |
| Find a static field | **GetStaticFieldID** |
| Read an int static field | **GetStaticIntField** |
| Create a Java string | **NewStringUTF** or **NewString** |
| Find and call a method | **GetMethodID**, **Call<type>Method** |
| Check for a pending exception | **ExceptionCheck** |
| Compare two JNI references by identity | **IsSameObject** |
| Release a local reference no longer needed | **DeleteLocalRef** |

### Why is (*env)->... written in C?

In the JNI declaration for C, **JNIEnv** is a pointer type to a function table, and the parameter is received as **JNIEnv \*env**. Therefore, the C syntax for a call through the function table is:

~~~c
/* Illustrative snippet inside an instance native method that already has env and self. */
jclass type = (*env)->GetObjectClass(env, self);

if (type != NULL) {
    (*env)->DeleteLocalRef(env, type);
}
~~~

The **(*env)->GetObjectClass** part selects the function pointer in the JNI table; **env** in the argument list is the first parameter of that function itself. This is the C syntax published by the JNI header, not a direct dereference of a Java object.

In **C++**, **jni.h** provides a wrapper class/struct with inline member functions, so the syntax is shorter:

~~~cpp
// Illustrative snippet inside a C++ native method.
jclass type = env->GetObjectClass(self);

if (type != nullptr) {
    env->DeleteLocalRef(type);
}
~~~

The two snippets perform the same JNI functionality, but **do not mix C and C++ syntax**: **.c** files use **(*env)->...(..., env, ...)**, while **.cpp** files typically use **env->...(...)**. If writing C++, declare the native entry point with **extern "C"** (or use the exact header generated by **javac -h**) to ensure proper symbol linkage.

### JNIEnv* Is Bound to a Thread

- The JVM passes a valid **JNIEnv \*** for the thread executing the JNI call. Do not store **env** in a global variable and use it from another thread.
- Two calls on the same Java thread are guaranteed by the JVM to receive the same JNI interface pointer; on different threads, the pointer may differ.
- If a thread created by C/C++ itself wants to call into Java, that thread must be attached to the JVM via **JavaVM**/**AttachCurrentThread** to obtain its own **JNIEnv \***; after finishing, it must detach according to the rules. A **JNIEnv \*** obtained from thread A must not be passed to thread B.
- **JNIEnv \*** is the entry point to the Java API, not a Java object, not a reference to **this**, and not a substitute for **JavaVM \***.

## 3. When Is the Second Parameter jobject?

For a **non-static native** method, the JVM passes the object receiving the Java call (**this**) as a **jobject**, commonly named **self**, **thiz**, or **obj**.

~~~java
class Counter {
    private int count = 10;

    native int increase(int delta);  // instance method
}
~~~

The native function has the form:

~~~c
JNIEXPORT jint JNICALL Java_Counter_increase(
        JNIEnv *env, jobject self, jint delta);
~~~

**self** references the exact **Counter** object that received the call, so if there are two different instances, each call receives the reference to its respective instance. Fields like **count** must be accessed through JNI functions, not read like a C struct (**self->count** is wrong). The typical steps are **GetObjectClass(env, self)** → **GetFieldID** → **GetIntField(env, self, ...)**.

**jobject is an opaque JVM reference**, not an object layout address that C can arbitrarily dereference. The JVM is free to use its own representation and the garbage collector may move objects. Do not infer Java object layout or point directly to fields using offset arithmetic on **jobject**.

In a valid Java instance call, the JVM provides the receiver object to the native method; if an instance method is called with a **null** receiver from Java, the call fails before executing the native body. However, other object arguments passed from Java can still be **null** and need to be checked depending on the API.

**jobject** is the general type for an object reference in JNI; subtypes such as **jstring**, **jarray**, **jobjectArray**, and **jclass** are used according to specific roles. Do not recklessly cast references just to bypass type checking; use the appropriate JNI APIs.

## 4. When Is the Second Parameter jclass?

For a **static native** method, the JVM has no **this** receiver; the second parameter is **jclass**, a reference to the **java.lang.Class** object representing **the class that declares the native method**.

~~~java
class Converter {
    private static int factor = 3;

    static native int multiply(int value);
}
~~~

The corresponding native function:

~~~c
JNIEXPORT jint JNICALL Java_Converter_multiply(
        JNIEnv *env, jclass clazz, jint value);
~~~

Native code can use **clazz** immediately with **GetStaticFieldID(env, clazz, "factor", "I")** and then **GetStaticIntField(env, clazz, ...)**. Attempting to use **GetIntField** as if it were an instance field on **clazz** violates the API contract.

**jclass is a JNI reference to a Class object**, not a C-style pointer to the class memory layout, not an instance of **Converter**, and it has no ability to read instance fields when lacking an appropriate instance. For example, **GetObjectClass(env, clazz)** returns the runtime class of the **Class** object itself (typically **java.lang.Class**), not an operation to retrieve **Converter.class**: **clazz** already represents the needed class.

| Question | jobject in instance native | jclass in static native |
| --- | --- | --- |
| Represents | The receiving object, equivalent to **this** | The **Class** object of the class declaring the method |
| Data typically accessed | Instance fields/methods | Static fields/methods |
| Getting the class type to look up an instance field | **GetObjectClass(env, self)** | Already have **clazz** for static members |
| Is it a C address to dereference? | No | No |
| Lifetime when passed into native method by JVM | Local reference for the current call | Local reference for the current call |

## 5. Complete Java 17+ Example Calling Both Instance and Static Native

The practice exercise below uses plain Java and C, without requiring Spring/Gradle. Both methods take an **int** parameter from Java, but the native implementation accesses two different kinds of fields to clearly show the role of the second JNI parameter.

### 5.1. File FirstJni.java

Save the file with the **exact name FirstJni.java**, without declaring a **package** to keep the C names easy to read:

~~~java
public final class FirstJni {
    private final int base;
    private static int factor = 3;

    static {
        System.loadLibrary("firstjni");
    }

    public FirstJni(int base) {
        this.base = base;
    }

    // JVM will pass JNIEnv*, jobject before the value parameter.
    public native int addToBase(int value);

    // JVM will pass JNIEnv*, jclass before the value parameter.
    public static native int scale(int value);

    public static void main(String[] args) {
        FirstJni demo = new FirstJni(10);
        System.out.println("instance=" + demo.addToBase(5));
        System.out.println("static=" + FirstJni.scale(7));
    }
}
~~~

From Java, **addToBase(5)** is called on an instance with **base = 10**; **scale(7)** belongs to the class with static field **factor = 3**. The **System.loadLibrary("firstjni")** call loads the native library according to the operating system's naming convention. The argument to **loadLibrary** is the logical name **firstjni**, without the **lib** prefix or **.so/.dll/.dylib** extension.

### 5.2. Generating the JNI Header from Java Signatures

Open a terminal with JDK 17+ and run in the directory containing the file:

~~~bash
javac -h . FirstJni.java
~~~

**javac** compiles **FirstJni.class** and simultaneously generates **FirstJni.h**. Inside the header, there will be prototypes corresponding to:

~~~c
JNIEXPORT jint JNICALL Java_FirstJni_addToBase
        (JNIEnv *, jobject, jint);

JNIEXPORT jint JNICALL Java_FirstJni_scale
        (JNIEnv *, jclass, jint);
~~~

The first two parameters are added implicitly, so the Java declaration only has one **int value**, whereas C has three arguments. For the same **FirstJni** name, instance and static natives are distinguished by **the type of the second parameter**. Do not change the order or swap **jobject** for **jclass** just because they often have similar pointer representations; their APIs and signature contracts are different.

If there is a **package**, underscores, or overloading, the symbol name has specific escaping/suffix rules. Inspect **the actual header generated by javac -h**; this is much more reliable than writing **Java_...** names by guesswork.

### 5.3. File FirstJni.c

Save the following C file in the same directory as **FirstJni.h**:

~~~c
#include <jni.h>
#include "FirstJni.h"

/*
 * Instance native:
 * - env: JVM's JNI functions
 * - self: FirstJni object receiving the call
 * - value: int parameter passed by Java
 */
JNIEXPORT jint JNICALL Java_FirstJni_addToBase(
        JNIEnv *env, jobject self, jint value) {

    jclass receiverClass = (*env)->GetObjectClass(env, self);
    if (receiverClass == NULL) {
        return 0; /* JVM exception is pending if the operation failed */
    }

    jfieldID baseField =
            (*env)->GetFieldID(env, receiverClass, "base", "I");

    (*env)->DeleteLocalRef(env, receiverClass);

    if (baseField == NULL) {
        return 0; /* For example: NoSuchFieldError is pending */
    }

    jint base = (*env)->GetIntField(env, self, baseField);
    return base + value;
}

/*
 * Static native:
 * - env: JVM's JNI functions
 * - clazz: Class object of FirstJni
 * - value: int parameter passed by Java
 */
JNIEXPORT jint JNICALL Java_FirstJni_scale(
        JNIEnv *env, jclass clazz, jint value) {

    jfieldID factorField =
            (*env)->GetStaticFieldID(env, clazz, "factor", "I");

    if (factorField == NULL) {
        return 0; /* For example: NoSuchFieldError is pending */
    }

    jint factor =
            (*env)->GetStaticIntField(env, clazz, factorField);

    return value * factor;
}
~~~

**Step-by-step explanation of each path:**

1. **Java_FirstJni_addToBase** receives **self**, calls **GetObjectClass** to obtain a reference to the instance's runtime class; **GetFieldID** looks up the **base** field with descriptor **"I"** (Java **int**); **GetIntField** reads **base** from **self** itself. Since **base=10** and **value=5**, the result is **15**.
2. **Java_FirstJni_scale** receives **clazz** directly, so it uses **GetStaticFieldID** to look up the static field **factor** with descriptor **"I"**, then **GetStaticIntField** retrieves **factor=3**. Since **value=7**, the result is **21**.
3. **GetObjectClass** creates a new local reference, so **DeleteLocalRef** releases it after use. **jfieldID** is a field ID, not a **jobject**, and must not be passed to **DeleteLocalRef**.
4. When **GetFieldID/GetStaticFieldID** returns **NULL** due to an error, an appropriate Java exception may be pending. The sample returns **0** to exit the C body, but if an exception is pending, Java receives the exception rather than treating **0** as a successful result. For production programs, design a complete error-handling path and ensure you do not continue calling JNI APIs that are prohibited while an exception is pending.
5. The two small operations in the example do not overflow **jint**. When doing real arithmetic, **jint** corresponds to a 32-bit signed Java **int**; you must check value ranges and overflow rules, especially when combining with C **long**, **size_t**, or pointers.

**Why can private fields be read?** JNI has APIs to look up fields by class, name, and descriptor, and can access **private** fields as in the example. There is no syntax like **self->base** or **clazz->factor** on JNI references.

### 5.4. Compiling the Library on Linux

A C compiler and the **JAVA_HOME** environment variable pointing to a JDK matching the JVM architecture are required. Run in the shell:

~~~bash
javac -h . FirstJni.java

cc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  FirstJni.c -o libfirstjni.so

java -cp . -Djava.library.path=. FirstJni
~~~

### 5.5. Compiling the Library on macOS

Change the JNI platform header directory and the dynamic library type:

~~~bash
javac -h . FirstJni.java

cc -std=c11 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  FirstJni.c -o libfirstjni.dylib

java -cp . -Djava.library.path=. FirstJni
~~~

### 5.6. Compiling the Library on Windows (MSVC)

In **x64 Native Tools Command Prompt for Visual Studio** with **cl** and JDK **JAVA_HOME**:

~~~bat
javac -h . FirstJni.java

cl /nologo /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" FirstJni.c /Fe:firstjni.dll

java -cp . -Djava.library.path=. FirstJni
~~~

Choose the right compiler/linker and the same architecture between the JDK/JVM and the DLL/shared library; a 32-bit library cannot be loaded into a 64-bit JVM process. The commands above illustrate native builds directly on common targets; when cross-compiling, use the appropriate compiler, sysroot, JNI headers, and ABI.

**Stdout of all three builds when successful:**

~~~text
instance=15
static=21
~~~

The syntax is for **.c**, because the code is written using the JNI C API. If switching to C++, you must compile as C++, adjust the API call syntax and linkage according to **jni.h**; do not simply rename the file extension and keep all **(*env)->...** expressions unchanged.

## 6. Exact Breakdown of the Two Calls Through the JVM

~~~text
new FirstJni(10).addToBase(5)
        |
        | Non-static native method
        v
JNIEXPORT jint Java_FirstJni_addToBase(
    JNIEnv *env,      // interface of the current Java thread
    jobject self,     // instance FirstJni(base=10)
    jint value        // 5
)
        |
        v
GetObjectClass(self) -> GetFieldID("base","I")
        -> GetIntField(self) -> 10 + 5 -> 15

FirstJni.scale(7)
        |
        | Static native method
        v
JNIEXPORT jint Java_FirstJni_scale(
    JNIEnv *env,      // interface of the current Java thread
    jclass clazz,     // Class object of FirstJni
    jint value        // 7
)
        |
        v
GetStaticFieldID(clazz,"factor","I")
        -> GetStaticIntField(clazz) -> 7 * 3 -> 21
~~~

The order **env, receiver/class, Java parameters** applies even when the Java native method has no parameters. For example, **native void ping()** still receives **(JNIEnv \*, jobject)**; **static native void pingGlobal()** still receives **(JNIEnv \*, jclass)**. When a method has multiple arguments, they appear next in the exact Java order, with their corresponding JNI types.

## 7. JNI Data Types, Signatures, and Java Reflection

The first two parameters are **not** part of the **Java method descriptor**. For **addToBase(int)** returning **int**, the descriptor is **(I)I**, with no characters describing **JNIEnv \*** or **this**. For **scale(int)**, it is also **(I)I**: static/instance information is a method attribute, not a second argument declared by Java.

Some basic mappings:

| Java | C JNI | Notes |
| --- | --- | --- |
| **boolean** | **jboolean** | Use **JNI_TRUE/JNI_FALSE** for boolean values |
| **byte**, **short**, **char** | **jbyte**, **jshort**, **jchar** | Java **char** is an unsigned 16-bit UTF-16 code unit |
| **int**, **long** | **jint**, **jlong** | Java **int** is 32-bit, **long** is 64-bit; C **long** is not fixed at 64-bit |
| **float**, **double** | **jfloat**, **jdouble** | Width matches Java |
| **String** | **jstring** | Reference to a Java String |
| Any Java object | **jobject** or JNI subtype | Opaque reference, can be null if passed from Java |
| **Class<?>** | **jclass** | Java class object reference |
| **void** | **void** | No return value |

Common field descriptors: **I=int**, **J=long**, **Z=boolean**, **D=double**, **Ljava/lang/String;=String**, **[I=int[]**. In the example, **"I"** is passed to **GetFieldID/GetStaticFieldID** because both **base** and **factor** are Java **int**. The exact descriptor must be used even if two C types have the same size on a platform.

An incorrect native prototype may compile in C if the matching header is not included, but the JVM will call it using a different ABI/calling convention and cause severe errors. Therefore, include the header generated by **javac -h** in the native file and let the compiler verify the declaration/definition. **JNIEXPORT** requests the appropriate exported symbol, **JNICALL** applies the required platform calling convention, and **Java_FirstJni_addToBase** is the export name according to JNI rules (unless using dynamic registration).

## 8. Lifetime of env, jobject, and jclass

These three parameters do **not** share the same lifetime rules:

| Component | Basic safe scope | What NOT to do |
| --- | --- | --- |
| **JNIEnv \*** | The thread executing the JNI call | Cache and call from another thread |
| **jobject self** passed by JVM | Local reference within the current native call | Keep the raw reference in a global variable for use in a later call |
| **jclass clazz** passed by JVM | Local reference within the current native call | Cache the raw **jclass** and assume it lives forever |
| **jfieldID / jmethodID** | ID of a member still belonging to a valid class | Treat as **jobject** or keep across class unloading without managing the class lifecycle |

The JVM tracks **local references** passed into or created during a call; they are valid on that same thread and are usually automatically freed after the native method returns. The new reference obtained from **GetObjectClass** in the example was freed early using **DeleteLocalRef**. Do not call **DeleteLocalRef** on **self**/**clazz** provided by the JVM and then continue using them.

If you need to keep an object or class after the native method ends, consider **NewGlobalRef** to create a **global reference**, check for **NULL** in case allocation fails, and then call **DeleteGlobalRef** when no longer needed. Global references still must be managed to avoid keeping objects/class loaders alive unintentionally. If only a weak reference is needed, JNI provides **weak global references** with different semantics. Do not pass a **local reference** to another native thread.

Two different JNI references can point to the same Java object; **comparing pointer values directly with == is not a portable way to compare identity**. Use **(*env)->IsSameObject(env, a, b)** in C or **env->IsSameObject(a, b)** in C++.

## 9. Static or Instance: Deciding Based on the Java Model

Distinguish **jobject/jclass** based on **the native method declaration**, not on variable names, a specific Java caller, or the C body.

- If the native method needs the state of a specific object (**base**, **id**, instance buffer, native handle attached to the object), choose **instance native** and receive **jobject**.
- If the native method represents a class-level operation, factory, or computation that does not depend on a receiver, you can choose **static native** and receive **jclass**. If you want to access an instance's data in a static native, that instance must be passed as an explicit Java argument.
- A **static native** method can still accept an **Object** passed by the caller; in that case, the C signature is **(JNIEnv \*, jclass, jobject ...)**. **jclass** is still the second implicit parameter, and the passed **jobject** is the actual argument.
- An **instance native** method can accept an additional **Class<?>** from Java; the C signature is then **(JNIEnv \*, jobject, jclass ...)**. Do not confuse the **jclass** passed from Java in a later position with the implicit second parameter.

Contrasting example of parameter kinds (declaration snippet, not a standalone program):

~~~java
class BindingCases {
    static native void inspect(Object suppliedObject);
    native void inspectClass(Class<?> suppliedClass);
}
~~~

~~~c
/* Logical signature form; C names can be set according to the generated header. */
JNIEXPORT void JNICALL Java_BindingCases_inspect(
        JNIEnv *env, jclass declaringClass, jobject suppliedObject);

JNIEXPORT void JNICALL Java_BindingCases_inspectClass(
        JNIEnv *env, jobject receiver, jclass suppliedClass);
~~~

**Position**, not just type name, determines which parameter is implicitly provided by the JVM.

## 10. What Changes When Using C++ or RegisterNatives?

**C++:** always still receives **JNIEnv \*** followed by **jobject/jclass**. The main difference is how the JNI API is called and linkage when exporting. An illustrative C++ native snippet:

~~~cpp
#include <jni.h>
#include "FirstJni.h"

extern "C" JNIEXPORT jint JNICALL Java_FirstJni_scale(
        JNIEnv *env, jclass clazz, jint value) {

    jfieldID field = env->GetStaticFieldID(clazz, "factor", "I");
    if (field == nullptr) {
        return 0;
    }
    return value * env->GetStaticIntField(clazz, field);
}
~~~

This is **an alternative implementation of scale** to illustrate C++ syntax; do not compile it alongside **FirstJni.c** into the same library if both define the same symbol. If using C++ throughout, convert the other native functions to the corresponding syntax and configure the C++ compiler/linker.

**RegisterNatives:** JNI also allows mapping Java native methods to C/C++ function pointers using **RegisterNatives**. When using this approach, the function is not required to have an export name like **Java_Class_method**, but **the call signature still starts with JNIEnv \* and the appropriate jobject or jclass**, followed by the Java arguments. You must register the exact method name and descriptor, ensuring the pointer has an ABI-compatible signature; a type mismatch can cause a crash. When first learning JNI, the **javac -h** approach and traditional symbol linking are simpler for observing the exact signatures.

## 11. Exceptions and Safety Rules When Using JNI Parameters

Whenever calling a JNI API through **env**, check the documentation for return types and errors:

1. **GetObjectClass** creates a **jclass** local reference; if it fails and returns **NULL**, do not pass **NULL** to **GetFieldID**.
2. **GetFieldID** is for **instance fields**; **GetStaticFieldID** is for **static fields**. Both APIs take a **jclass** as the lookup context, but reading the value afterward differs: **GetIntField** takes **jobject**; **GetStaticIntField** takes **jclass**.
3. When a Java exception is pending, many JNI APIs are not allowed to be called; to check, you can use **ExceptionCheck**, and valid cleanup operations such as **DeleteLocalRef** are still permitted. Normally, let the pending exception propagate back to Java rather than clearing the exception just to return a dummy number.
4. Reading/writing Java data must go through the JNI API; do not cast **jobject** to a pointer to a C struct, store a raw **JNIEnv \*** for later use, or assume a field ID is a memory pointer.
5. When a native method is called concurrently by multiple Java threads, each call has its own **env** and implicit references per thread/call, but Java **static** variables or global C state can still be shared across threads; separate synchronization is required if modified concurrently.

There is no instruction that allows C code to dereference **jobject** like a Java object. Use the **-Xcheck:jni** tool in HotSpot when you need to detect many JNI usage errors at runtime (depending on JVM and version):

~~~bash
java -Xcheck:jni -cp . -Djava.library.path=. FirstJni
~~~

The extra checking mode is not guaranteed to catch all C bugs, memory safety issues, races, or ABI mismatches.

## 12. Common Errors When Writing Your First JNI Function

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| **UnsatisfiedLinkError: no firstjni in java.library.path** | Library has wrong name or is not in the search path | Check **System.loadLibrary("firstjni")**, filename **libfirstjni.so / libfirstjni.dylib / firstjni.dll**, **java.library.path** |
| **UnsatisfiedLinkError** when calling method | Native symbol has wrong name/package, library lacks the function, or wrong overload | Run **javac -h .** and match the prototype and export exactly |
| C compilation reports error on **GetObjectClass** | Using C++ syntax **env->...** in a C file | Use **(*env)->GetObjectClass(env, ...)** |
| C++ compilation reports error on JNI call syntax | Keeping C-only syntax | Use **env->GetObjectClass(...)** |
| Instance native method declared with second argument as **jclass** | Confused static/instance; prototype mismatch | Recheck **native** vs **static native** in Java/header |
| Static native method uses **GetIntField** on **clazz** | **clazz** is a Class object, not an instance | Use **GetStaticFieldID/GetStaticIntField**, or accept the instance via an explicit argument |
| **NoSuchFieldError** or **NULL** field ID | Wrong name, descriptor, static/instance field, or class | Check **"base","I"** and **"factor","I"** along with the corresponding API |
| Crash/JVM fatal error when manipulating references | Dereferencing/casting opaque reference, using reference past lifetime, wrong ABI | Use JNI APIs, manage local/global references, check header/architecture |
| Crash or strange behavior from a native thread | Reusing **JNIEnv \*** from another thread | Attach the thread to obtain that thread's env; detach at the right time |
| C++ build has symbol errors | C++ name mangling or missing proper export/linkage | Include header from **javac -h**, ensure **extern "C"** and **JNIEXPORT/JNICALL** |
| JVM reports wrong architecture when loading library | 64-bit JVM but DLL/.so has different bitness or ABI | Build with the same architecture as the JVM and use the target's native compiler/linker |

When debugging, clearly separate the three stages: **load library**, **resolve the right native symbol**, **execute JNI APIs with the right types/thread/lifetime**. Issues at each stage have different causes and must not be solved by arbitrary casting.

## 13. Quick Self-Check

**Question 1.** Java declares **public native long read(int id)**. What type must the C function start with?

**Answer:** **jlong Java_..._read(JNIEnv \*env, jobject self, jint id)** with standard **JNIEXPORT/JNICALL** macros; parameters **env** and **self** are added by the JVM before the **id** argument. The return type **jlong** corresponds to Java **long**, do not default to C **long**.

**Question 2.** Java declares **public static native String format(int id)**. What is the second parameter of the C function?

**Answer:** **jclass clazz**, representing the class declaring the native method; return type **jstring**, Java argument **int id** maps to **jint id**. There is no **this** instance.

**Question 3.** In a static native function, you have **jclass clazz**; is using **GetObjectClass(env, clazz)** to get the class declaring the method right or wrong?

**Answer:** Wrong in purpose. **clazz** is already the Class object representing the class. **GetObjectClass(env, clazz)** queries the runtime class of the **java.lang.Class** object itself, not retrieving the class that **clazz** represents.

**Question 4.** Can you keep **JNIEnv \*env** received from a native callback in a global variable so a C worker thread can call Java the next day?

**Answer:** No. **JNIEnv \*** is only valid on its own thread. A native thread that wants to access the JVM must attach to obtain its own env, and manage references/lifecycle independently; objects that need to be kept beyond the call must be managed with an appropriate JNI global reference.

**Question 5.** Why does the Java method declare only one parameter, yet the C function has three?

**Answer:** The JVM prepends **JNIEnv \*** and **jobject/jclass** in the first two positions; only the third parameter comes from the Java declaration. That is the JNI calling contract, not two hidden Java parameters accessible via Java reflection.

## References

- Oracle Java 21 — JNI Design Overview (JNI interface pointer, native arguments, linking, and references): https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html
- Oracle Java 21 — JNI Functions (GetObjectClass, GetFieldID, GetStaticFieldID, GetIntField, GetStaticIntField, reference APIs): https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html
- Oracle Java 21 — JNI Types and Data Structures: https://docs.oracle.com/en/java/javase/21/docs/specs/jni/types.html
- Oracle Java 21 — JNI Invocation API (AttachCurrentThread, DetachCurrentThread): https://docs.oracle.com/en/java/javase/21/docs/specs/jni/invocation.html

**Key takeaway:** Every native method receives **JNIEnv \*** first. **Instance** methods receive **jobject self** second; **static** methods receive **jclass clazz** second. The actual parameters declared by Java come afterward. Always use the JNI API appropriate for each reference's role, maintain proper thread/lifetime rules, and generate headers from Java to ensure C/C++ signatures match the JVM.