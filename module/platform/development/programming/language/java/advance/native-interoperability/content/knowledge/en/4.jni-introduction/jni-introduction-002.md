# Declaring Native Methods for Instances and Static Methods

## 1. Objective: Correctly declaring the first two types of JNI methods

In Java, the `native` keyword marks a method **declared in a Java class whose body is implemented in native code** (such as C/C++). When using JNI (Java Native Interface), the JVM connects the Java call to the corresponding native function. The two common forms are:

- **Instance native method:** does not have `static`; called on a specific object, and can read the state of that object via JNI.
- **Static native method (class-level native method):** has `static`; called through the class name, without an implicit `this` receiver object. The native code receives a reference to the class and can access static state if needed.

This lesson focuses on **how to declare and map both types of methods**, understanding JNI signatures, generating headers with the JDK, compiling the library, running tests, and handling common errors. Library loading concepts are only mentioned to the extent needed to run the examples.

After this lesson, you will be able to look at:

~~~java
public native int addWithOffset(int left, int right);
public static native int multiply(int left, int right);
~~~

and explain why the first C function receives `jobject`, while the second receives `jclass`.

## 2. Syntax and meaning of `native` in Java

Examples of two valid declarations:

~~~java
public class NativeDeclaration {
    private native int increment(int value);       // Instance native
    public static native int doubleValue(int value); // Static native
}
~~~

This is only an **illustrative declaration**, not a standalone runnable program: to call them, a native library and the corresponding JNI functions are required.

Important characteristics:

1. **No Java body:** a `native` method ends with a `;`, without writing a `{ ... }` block. Writing both `native` and a Java body will not compile.
2. **`static` is an independent property:** `native` does not automatically make a method static. Without `static`, the method receives a `this` object according to Java rules.
3. **Access modifiers still apply:** `public`, `protected`, `private` control accessibility on the Java side. A `private native` method can still be called by Java code in that class and can still have a corresponding native function.
4. **Parameter/return types must be mapped correctly:** Java `int` corresponds to `jint`, Java `long` corresponds to `jlong`, `String` corresponds to `jstring`; objects/arrays have their own JNI representations.
5. **`native` and `abstract` cannot be declared together on the same method:** `abstract` requires a subclass to implement a Java method, whereas `native` declares a native implementation.
6. **`native` does not load the library:** the library must be loaded into the Java process, typically using `System.loadLibrary(...)` or `System.load(...)`. Compiling the declaration successfully does not prove that the C/C++ function is linked.

Comparing invocations:

~~~java
NativeDeclaration obj = new NativeDeclaration();
obj.increment(4);                 // Instance: requires an object
NativeDeclaration.doubleValue(4); // Static: called via class
~~~

The code above also only illustrates how to call them. If the JNI library has not been built/loaded, execution may throw `UnsatisfiedLinkError`. Although Java allows syntax for calling a static method through an object variable, you should **use the class name** to clearly express that it is a static method.

## 3. The JVM maps instance and static methods to two different C signatures

With the **JNI C API**, each native implementation function typically receives hidden arguments at the start of its signature: `JNIEnv *` and a reference appropriate for the method type.

| Characteristic | Instance `native` | `static native` |
|---|---|---|
| Java syntax | `public native int calculate(int x);` | `public static native int calculate(int x);` |
| Java call | `object.calculate(5)` | `SomeClass.calculate(5)` |
| Implicit receiver object in Java | Has `this` | Does not have `this` |
| First JNI argument | `JNIEnv *env` | `JNIEnv *env` |
| Second JNI argument | `jobject self`: reference to the receiver object | `jclass clazz`: reference to the class declaring the method |
| Subsequent explicit argument | `jint x` | `jint x` |
| Can read object fields? | Yes, via `self` and JNI API | No pre-existing receiver object; must be passed a `jobject` if you want to read instance fields |
| Can read static fields? | Yes, if the right `jclass` is obtained | Yes, using `clazz` and `GetStatic...` APIs |

Two conceptual C signatures (different class/method names for easy comparison):

~~~c
JNIEXPORT jint JNICALL Java_SomeClass_instanceCall(
    JNIEnv *env, jobject self, jint x
);

JNIEXPORT jint JNICALL Java_SomeClass_staticCall(
    JNIEnv *env, jclass clazz, jint x
);
~~~

**`JNIEnv *`** is the interface for calling JVM capabilities from native code on the **current thread**: reading fields, manipulating objects, creating strings, throwing exceptions, etc. Do not share a `JNIEnv *` pointer directly across threads.

**`jobject`** represents a JNI reference to the Java object receiving the instance call; it is **not** a C pointer pointing into the layout structure of the Java object. To read `this.offset`, C code uses JNI functions, not casting `jobject` to a `struct *`.

**`jclass`** is a JNI reference to the `java.lang.Class` object of the class declaring the static method. It is not an instance of the business class; nor should it be cast to a C struct pointer. APIs such as `GetStaticFieldID`, `GetStaticIntField`, `GetStaticMethodID`, etc. are used when accessing static members.

**`JNIEXPORT`** ensures symbols are exported properly; **`JNICALL`** uses the JNI calling convention appropriate for the platform. You should use these macros intact instead of guessing from `int`/compiler calling conventions.

> Quick rule of thumb: *instance* receives `JNIEnv *` + `jobject` + parameters declared in Java; *static* receives `JNIEnv *` + `jclass` + parameters declared in Java.

## 4. Complete example: one class containing both instance and static native methods

We will create a `NativeKinds` class with per-object state:

- `addWithOffset(left, right)` is an **instance native** method, returning `left + right + offset`; two objects with different `offset` values will produce different results.
- `multiply(left, right)` is a **static native** method, returning the product of the two arguments; it does not use the `offset` of any object.

Working structure:

~~~text
jni-example/
├── NativeKinds.java       # Java declaration and runner
├── nativekinds.c           # JNI implementation in C
└── NativeKinds.h           # Auto-generated with javac -h .
~~~

The `.class` file and the native library file are generated during the build process, not written by hand.

### 4.1. Writing `NativeKinds.java`

~~~java
public final class NativeKinds {
    static {
        System.loadLibrary("nativekinds");
    }

    private final int offset;

    public NativeKinds(int offset) {
        this.offset = offset;
    }

    public native int addWithOffset(int left, int right);

    public static native int multiply(int left, int right);

    public static void main(String[] args) {
        NativeKinds first = new NativeKinds(10);
        NativeKinds second = new NativeKinds(20);

        System.out.println("instance A: " + first.addWithOffset(2, 3));
        System.out.println("instance B: " + second.addWithOffset(2, 3));
        System.out.println("static: " + NativeKinds.multiply(2, 3));
    }
}
~~~

Read these three points carefully:

1. `addWithOffset` **does not have `static`**, so each call has its own receiver object: `first` or `second`.
2. `multiply` **has `static`**, so it is called with `NativeKinds.multiply(...)`. In the Java signature of this method there is no `this`, and it cannot directly use `offset` as an instance variable.
3. The `static` block loads the library by its logical name `nativekinds` when the class is initialized. The actual file name depends on the operating system: `nativekinds.dll`, `libnativekinds.so`, or `libnativekinds.dylib`. Do not include the file extension in `loadLibrary`.

Do not run `java NativeKinds` at this point, because the C implementation has not been built yet. The `javac` command can succeed even if the native library does not exist yet.

### 4.2. Generating the header with the JDK, without guessing function names

From the directory containing `NativeKinds.java`, use **JDK 17 or newer**:

~~~bash
javac -h . NativeKinds.java
~~~

The command generates `NativeKinds.class` and `NativeKinds.h`. The header is the contract between Java and C. The core function declarations in the header take the form:

~~~c
JNIEXPORT jint JNICALL Java_NativeKinds_addWithOffset
  (JNIEnv *, jobject, jint, jint);

JNIEXPORT jint JNICALL Java_NativeKinds_multiply
  (JNIEnv *, jclass, jint, jint);
~~~

This is an **excerpt** of the header, not the entire auto-generated file (the real header also has include guards, `#include <jni.h>`, and comments describing the signatures). Note that **`jobject` and `jclass` are the only important difference in the two implicit arguments**; the remaining `jint` arguments correspond to the two `int` parameters declared in Java.

Related basic JNI types:

| Java declaration | Common type in JNI C | JVM descriptor |
|---|---|---|
| `boolean` | `jboolean` | `Z` |
| `byte` | `jbyte` | `B` |
| `char` | `jchar` | `C` |
| `short` | `jshort` | `S` |
| `int` | `jint` | `I` |
| `long` | `jlong` | `J` |
| `float` | `jfloat` | `F` |
| `double` | `jdouble` | `D` |
| `void` | `void` (return type) | `V` |
| `String` | `jstring` | `Ljava/lang/String;` |
| `int[]` | `jintArray` | `[I` |

The JVM signature for both Java methods in the example is `(II)I`: taking two `int`s, returning an `int`. The descriptor **does not list** `JNIEnv *`, `jobject`, or `jclass`, because those are implicit parameters of the C function, not parameters declared in the Java method.

### 4.3. Implementing the two functions in `nativekinds.c`

~~~c
#include "NativeKinds.h"

JNIEXPORT jint JNICALL Java_NativeKinds_addWithOffset(
    JNIEnv *env, jobject self, jint left, jint right
) {
    /* Find the class of the current object. */
    jclass clazz = (*env)->GetObjectClass(env, self);
    if (clazz == NULL) {
        return 0; /* A Java exception is already pending. */
    }

    /* "I" is the descriptor for an int field. */
    jfieldID offsetField = (*env)->GetFieldID(
        env, clazz, "offset", "I"
    );
    if (offsetField == NULL) {
        (*env)->DeleteLocalRef(env, clazz);
        return 0; /* GetFieldID reports errors via a Java exception. */
    }

    jint offset = (*env)->GetIntField(env, self, offsetField);
    (*env)->DeleteLocalRef(env, clazz);

    return left + right + offset;
}

JNIEXPORT jint JNICALL Java_NativeKinds_multiply(
    JNIEnv *env, jclass clazz, jint left, jint right
) {
    (void) env;   /* This example does not need to call JNI functions. */
    (void) clazz; /* Static method receives the class, not this. */
    return left * right;
}
~~~

**Explanation of the instance part:**

- The `self` parameter is the `first` or `second` object depending on the call.
- `GetObjectClass(env, self)` obtains the class reference; `GetFieldID(..., "offset", "I")` finds the `offset` field of type `int`.
- `GetIntField(env, self, offsetField)` reads the exact value from **the calling object**. Therefore `first` uses 10, while `second` uses 20.
- `DeleteLocalRef` releases the local reference to `clazz` when it is no longer needed. `offsetField` is an ID, not a `jobject` local reference to be deleted this way.
- If `GetObjectClass` or `GetFieldID` fails, they may leave a **pending Java exception**. The `0` value in the error branch is only a return value from C while handling the exception; if an exception is pending, the Java side will receive the exception instead of using `0` as a valid result.

**Explanation of the static part:**

- The second parameter is `jclass clazz`, **not `jobject self`**.
- The function only uses `left` and `right`, so it casts to void so the compiler does not warn about two unused JNI parameters.
- If you want to access a `static int factor` variable in the class, C code must use `GetStaticFieldID` and `GetStaticIntField` with `clazz`. Do not use `GetIntField` for a static field.

To keep the lesson easy to run and the output deterministic, the example uses small numbers: signed integer overflow in C is not examined. When computing with large values, you need to actively define how to handle overflow because signed integer semantics differ between C and Java.

### 4.4. Compiling the library by operating system

Run **one** of the following three approaches depending on the machine running the JVM. The machine needs a JDK with JNI headers and an appropriate C compiler; the `JAVA_HOME` variable points to that JDK. Execute from the directory containing `NativeKinds.java`, `NativeKinds.h`, and `nativekinds.c`.

**Linux (GCC):**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  nativekinds.c -o libnativekinds.so

java -Djava.library.path=. NativeKinds
~~~

**macOS (Clang):**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  nativekinds.c -o libnativekinds.dylib

java -Djava.library.path=. NativeKinds
~~~

**Windows (MSVC in Developer Command Prompt, `cmd.exe` syntax):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" nativekinds.c /Fe:nativekinds.dll

java -Djava.library.path=. NativeKinds
~~~

If you use `javac` and `java` from different JDKs, or if the compiler builds for an architecture that does not match the JVM (for example, a 32-bit DLL with a 64-bit JVM), loading may fail. You must build for the **operating system + CPU/bitness + ABI compatible with the JVM process**.

When built, loaded, and called successfully, the exact stdout is:

~~~text
instance A: 15
instance B: 25
static: 6
~~~

Explanation: `first.addWithOffset(2,3) = 2 + 3 + 10 = 15`; `second.addWithOffset(2,3) = 2 + 3 + 20 = 25`; `multiply(2,3) = 6`. Both instances use the same C function code but carry different Java state data; static native has no state of an implicit `this`.

## 5. Tracing the Java → JNI → C call

~~~text
Java thread executes main()
    |
    +--> first.addWithOffset(2, 3)
    |      +--> JVM dispatches to the instance JNI function
    |      +--> (JNIEnv*, jobject first, jint 2, jint 3)
    |      +--> GetIntField(first, offset) = 10
    |      +--> returns 15 to Java
    |
    +--> second.addWithOffset(2, 3)
    |      +--> (JNIEnv*, jobject second, jint 2, jint 3)
    |      +--> GetIntField(second, offset) = 20
    |      +--> returns 25 to Java
    |
    +--> NativeKinds.multiply(2, 3)
           +--> JVM dispatches to the static JNI function
           +--> (JNIEnv*, jclass NativeKinds, jint 2, jint 3)
           +--> returns 6 to Java
~~~

In all three calls, **the C code runs inside the active JVM process**. `native` does not automatically spawn child processes, does not automatically use networking/IPC, and does not convert Java objects into C structs. The JVM maintains the transition between Java and native according to the JNI contract.

An object can have multiple instance native methods; each call will receive the appropriate receiver. A static native method can still be called through the class even when no instance of that class exists.

## 6. Deeper points to understand about `jobject` and `jclass`

### 6.1. Why does an instance function receive `jobject` but cannot read `self->offset`?

The JVM manages object layout, GC, and references. Therefore, `jobject` is a **JNI reference**, not a public definition of the object's address/layout. Use `GetFieldID` and `GetIntField` instead of dereferencing a pointer like a C struct.

The `jobject` in the example is a *local reference* valid for the duration of the current JNI call; do not store this raw reference into a C global variable for arbitrary use after the function returns. If you must keep a reference across multiple calls, use the **global reference** mechanism (`NewGlobalRef`/`DeleteGlobalRef`) and manage its lifecycle carefully.

### 6.2. What can `jclass` access?

`jclass` represents the class declaring the static method. To read static state of the class from C, the idea is:

~~~c
/* Illustrative snippet; only valid when the class has static int factor. */
jfieldID factorField = (*env)->GetStaticFieldID(
    env, clazz, "factor", "I"
);
if (factorField == NULL) {
    return 0; /* Java exception is pending. */
}
jint factor = (*env)->GetStaticIntField(
    env, clazz, factorField
);
~~~

This is an **excerpt**, not an addition to be inserted into `nativekinds.c` of the complete runnable example. To use it for real, there must be a Java field `static int factor` with the same name/type and a native function with a matching signature.

If a static native method needs to work with a **specific object**, the Java method can **accept that object as an explicit parameter**; in that case, the C function receives an additional `jobject` corresponding to the declared parameter. The static call itself still has no implicit `this`.

### 6.3. Differences between instance fields and static fields in JNI

| Task | Instance field | Static field |
|---|---|---|
| Get field ID | `GetFieldID` | `GetStaticFieldID` |
| Read `int` field | `GetIntField(env, object, fieldID)` | `GetStaticIntField(env, clazz, fieldID)` |
| Write `int` field | `SetIntField(env, object, fieldID, value)` | `SetStaticIntField(env, clazz, fieldID, value)` |
| Required target | A receiver `jobject` | A `jclass` |
| State | Each object has its own value | One value associated with the class (per corresponding loader) |

The field name and JVM descriptor must match the actual declaration. `GetFieldID` looks up an instance field, `GetStaticFieldID` looks up a static field; using the wrong API or wrong descriptor can lead to field lookup failure and a pending exception.

### 6.4. Inheritance, polymorphism, and static

- **Instance native method** is a normal Java instance method in terms of calling and overriding rules: if overridable, a subclass can override it with a Java method or an appropriate native implementation. In the example, the class is marked `final` to focus on the difference between the receiver and the class.
- **Static native method** follows Java static rules: the method is selected by class/type at compile time, with no dynamic dispatch based on the receiver object's type. A static method can *hide* a static method of the same name in a superclass, not override an instance method.
- The selected JNI C function must match the native method that the JVM is resolving. Do not assume that because a subclass has a different object, `static native` receives that object.

## 7. JNI function names and overloaded methods

When using JNI via **name-based lookup**, the exported function typically has the form:

~~~text
Java_<encoded_package_and_class>_<encoded_method>
~~~

Example without a package, without overloading:

~~~text
Java_NativeKinds_addWithOffset
Java_NativeKinds_multiply
~~~

For a class in a package, the exported name includes the package components encoded according to JNI rules. The `_` character has a special meaning in the encoding rules: you cannot always take the fully qualified class name, replace every dot with an underscore, and call it done. **Use `javac -h`** to avoid wrong names, wrong signatures, or mangling marks.

If you **overload** multiple `native` methods with the same name but different parameter types, the long name includes a description of the **parameter types**. Example declaration (this is a separate example, not inserted into `NativeKinds.java` above):

~~~java
public static native int sum(int a, int b);
public static native long sum(long a, long b);
~~~

With a hypothetical class named `Overloads` in the default package, the header may contain the names:

~~~text
Java_Overloads_sum__II
Java_Overloads_sum__JJ
~~~

The `__II` part represents two `int` parameters; `__JJ` represents two `long`s. Overloads are distinguished based on parameter types according to JNI descriptors; **the return type is not used** to distinguish Java overloads. It is still best to generate the header from the real code to get the exact names.

Another path is **`RegisterNatives`**, where the library actively registers the mapping between the Java name, descriptor, and C function pointer. In that case, it is not necessary to rely on exported symbols following the `Java_...` pattern. This practice lesson chooses name-based lookup to directly show the difference between `jobject` and `jclass`.

## 8. What `static native` and instance `native` do not do automatically

**Do not automatically transfer ownership of data.** `jobject` is a reference managed through JNI; native data allocated with `malloc` or native allocators is not automatically reclaimed by the Java GC. If native resources are allocated, a corresponding release mechanism is required.

**Do not automatically guarantee thread safety.** Multiple Java threads can call native methods; C code must protect shared state as required. `JNIEnv *` is tied to the current thread and **must not be reused from another thread**. C `static`/global variables differ from Java `static` fields even though both can be shared state.

**Do not automatically guarantee type safety at native runtime.** The Java compiler checks Java calls, while the C compiler checks the C signature of the function. Wrong mapping, wrong JNI API usage, keeping expired references, or invalid memory access can crash the JVM.

**Do not guarantee that the method is linked just because the class compiled successfully.** The right native library, right symbol or native method registration, right CPU/ABI, and dependent libraries are all required. The JVM may throw `UnsatisfiedLinkError` when loading the library or when resolving the method.

**Do not bypass class initialization rules.** A static native call is still subject to Java's class initialization rules. In the example, the `static` block containing `System.loadLibrary` runs during class initialization. If loading fails, the native call cannot be executed.

## 9. Common errors when writing your first JNI code

| Error or symptom | Common cause | How to verify and fix |
|---|---|---|
| `'native' method cannot have a body` or similar compile error | Writing `native ... { ... }` | Declare with `;`; put the implementation in C/C++. |
| Calling `obj.method()` when the method is instance without creating obj | Missing receiver or `null` object | Create a real object and call the instance method, or change the design to static if no state is needed. |
| `UnsatisfiedLinkError: no nativekinds in java.library.path` | Library not found by logical name | Check the name and the `-Djava.library.path=.` argument before the class. |
| File found but still `UnsatisfiedLinkError` | Missing dependency, wrong architecture, wrong format, or wrong export | Check binary OS/CPU/bitness, dependencies, and symbol names. |
| Native method not found error after changing signature | C still built against old header or name/descriptor changed | Re-run `javac -h`, update C, rebuild the library. |
| C receives `jclass` instead of `jobject` for instance (or vice versa) | Manually wrote wrong signature | Read the newly generated header; argument 2 differs depending on `static`. |
| `GetFieldID` cannot find field | Wrong name, descriptor, or actual field is static | Check the Java field, use the right `GetFieldID`/`GetStaticFieldID` and `I` for `int`. |
| Crash/`hs_err_pid...log` | Invalid JNI reference access, corrupted pointer/ABI, or native memory error | Use JNI APIs properly, enable JNI checks when debugging; inspect crash log and native stack. |
| C/C++ reports confusing symbol linkage | C++ mangling or missing macro/declaration | Include the header from `javac -h`, use C linkage properly according to the JNI header. |

**Useful verification commands:**

~~~bash
java -version
java -Xcheck:jni -Djava.library.path=. NativeKinds
~~~

`-Xcheck:jni` is a HotSpot JNI usage checking option that can help detect some invalid JNI calls during debugging; it does not prove all C/C++ code is safe and does not prevent every crash. The normal correct output of the program is still the three lines `instance A: 15`, `instance B: 25`, and `static: 6`; depending on the JVM/configuration, check mode may print additional warnings when JNI errors are found.

For build errors, look at the **first error** reported by the compiler/linker. For runtime errors, determine whether the failure occurs when **loading the library** or when **calling the native method**, because those are two different stages. Check the binary and dependencies by operating system if needed:

~~~text
Linux:   file / readelf / ldd
macOS:   file / lipo / otool -L
Windows: dumpbin /HEADERS /DEPENDENTS
~~~

The lines above list **tool names**, not complete shell commands; each tool needs to be passed the correct library path when run.

## 10. Self-check exercises

1. In `NativeKinds.java`, why do two objects have different `offset` values while the JNI function `Java_NativeKinds_addWithOffset` is still **one** C function?
2. Why does `Java_NativeKinds_multiply` receive `jclass` even though the Java declaration has no `Class` type parameter?
3. If `addWithOffset` is changed to `static native` without changing C, is the signature still correct? What happens to reading `offset`?
4. How do `GetFieldID` and `GetStaticFieldID` differ? For the Java field `private final int offset`, which API must be used?
5. When adding an overload `multiply(long, long)` alongside `multiply(int, int)`, what should be done to avoid writing the wrong native function name?
6. Why is compiling `NativeKinds.java` successfully not enough to prove that `java NativeKinds` will run successfully?

**Conclusion:** In JNI, **an instance native method receives `JNIEnv *` and `jobject` (representing `this`)**; **a static native method receives `JNIEnv *` and `jclass` (representing the declaring class)**. Java parameters appear after these two hidden parameters. Declaring correctly, generating headers with `javac -h`, implementing the proper JNI API, and testing with a runnable example will help you clearly distinguish both calling forms right from your first JNI lesson.