# Getting `jmethodID` and `jfieldID` by Exact Name and Signature in JNI

## 1. Purpose: Native Code Calling Java Methods and Accessing Java Fields

When Java calls into C/C++ via the Java Native Interface (JNI), native code may need to **call back into a Java method** or **read/write a field of a Java object**. JNI does not accept a single name like `"add"` or `"balance"` and automatically pick the right member: native code must provide the **class, member name, and type signature (descriptor)** and choose the right lookup function for **instance or static**.

JNI solves this through two types of IDs:

- **`jmethodID`:** identifies *a method or constructor*; used with `Call<Type>Method`, `CallStatic<Type>Method`, or `NewObject` functions.
- **`jfieldID`:** identifies *a field*; used with `Get<Type>Field`, `Set<Type>Field`, `GetStatic<Type>Field`, and `SetStatic<Type>Field` functions.

Both are **opaque IDs issued by the JVM**, not `jobject` and not ordinary C field addresses. Do not dereference them, do not cast them to memory offsets, and **do not call `DeleteLocalRef` on `jmethodID`/`jfieldID`**. They are part of the ABI/JVM contract, issued after lookup.

Common sequence of operations:

```text
Java object / class
         │
         ▼
GetObjectClass / FindClass → jclass
         │
         ├── GetMethodID(class, "add", "(I)I") ────→ jmethodID
         │                                           │
         │                                           ▼
         │                                    CallIntMethod(obj, ...)
         │
         └── GetFieldID(class, "count", "I") ────→ jfieldID
                                                     │
                                                     ▼
                                              GetIntField(obj, ...)
                                              SetIntField(obj, ...)
```

**Distinguish two easily confused names:** `GetMethodID` *finds the identifier* of a method, whereas `CallIntMethod` *executes* the found method; `GetFieldID` *finds the identifier* of a field, whereas `GetIntField` *reads the value* from an object.

## 2. Four Main Lookup APIs

| Java member to look up | JNI function (C) | Result | Example |
| --- | --- | --- | --- |
| **Instance** method | `GetMethodID(env, cls, name, signature)` | `jmethodID` | `add(int): int` → `"(I)I"` |
| **Static** method | `GetStaticMethodID(env, cls, name, signature)` | `jmethodID` | `describe(int,int): String` → `"(II)Ljava/lang/String;"` |
| **Instance** field | `GetFieldID(env, cls, name, signature)` | `jfieldID` | `int count` → `"I"` |
| **Static** field | `GetStaticFieldID(env, cls, name, signature)` | `jfieldID` | `static int scale` → `"I"` |

The name and signature must match the **actual declaration in bytecode**, including `private` fields. A correct signature with the wrong static/instance family is still an error. `GetMethodID` cannot replace `GetStaticMethodID`; `GetFieldID` cannot replace `GetStaticFieldID`.

Basic C call examples:

```c
jfieldID countId =
    (*env)->GetFieldID(env, cls, "count", "I");
jfieldID scaleId =
    (*env)->GetStaticFieldID(env, cls, "scale", "I");

jmethodID addId =
    (*env)->GetMethodID(env, cls, "add", "(I)I");
jmethodID describeId =
    (*env)->GetStaticMethodID(
        env, cls, "describe", "(II)Ljava/lang/String;");
```

This snippet **illustrates how to perform lookups**, assuming `env` and `cls` are already valid; section 5 has a complete program with error checking, compilation, and execution.

Meaning of the arguments:

- `env`: `JNIEnv *` of the **current thread**.
- `cls`: `jclass` for the class/interface to look up, not a class name string.
- `name`: **exact name**, case-sensitive, for example `"add"` is different from `"Add"`.
- `signature`: **exact JVM descriptor**, passed as a NUL-terminated C string; for Unicode names, the JNI interface uses modified UTF-8. Examples in this article use ASCII names only.
- Return value: a valid ID or `NULL` if lookup fails; on failure there is usually a **pending Java exception** such as `NoSuchMethodError` or `NoSuchFieldError`.

A lookup can trigger **class initialization** if the class has not been initialized yet. Therefore `ExceptionInInitializerError` or `OutOfMemoryError` must also be accounted for—do not assume every `NULL` is only due to a typo in the name.

## 3. How to Write Field and Method Descriptors

JNI uses **JVM descriptors**, not Java source syntax such as `int`, `String`, `List<String>`. This is the most common source of errors when looking up IDs.

### 3.1. Primitive Types

| Java | Descriptor | Common JNI type |
| --- | --- | --- |
| `boolean` | `Z` | `jboolean` |
| `byte` | `B` | `jbyte` |
| `char` | `C` | `jchar` |
| `short` | `S` | `jshort` |
| `int` | `I` | `jint` |
| `long` | `J` | `jlong` |
| `float` | `F` | `jfloat` |
| `double` | `D` | `jdouble` |
| `void` | `V` | Only used as a **method return type**, not a field type |

Do not confuse `C` (`char`) with `L...;` (class reference). `J` is `long`, not `L`.

### 3.2. Object Types, Arrays, and Nested Classes

- `java.lang.String` → `Ljava/lang/String;`.
- `java.lang.Object` → `Ljava/lang/Object;`.
- `java.util.List` → `Ljava/util/List;`.
- `int[]` → `[I`; `int[][]` → `[[I`.
- `String[]` → `[Ljava/lang/String;`.
- `demo.model.User` → `Ldemo/model/User;`.
- `Outer.Inner` is a member class → use the **binary name** with `$`: for example `Ldemo/model/Outer$Inner;`.

In descriptors, package/class names use **`/`**, placed between `L` and **`;`**. Writing `Ljava.lang.String;` (with dots), omitting the semicolon, or writing `LString;` instead of the fully qualified class name can all cause the lookup to fail.

**Generics do not appear verbatim in descriptors**: a field `List<String> names` has the descriptor `Ljava/util/List;` after type erasure, not `Ljava/util/List<Ljava/lang/String;>;`. Varargs `String... args` in bytecode is the array `[Ljava/lang/String;`.

### 3.3. Method Descriptors

Formula:

```text
(<parameter 1 descriptor><parameter 2 descriptor>...)<return descriptor>
```

Parameters are concatenated directly, **with no commas, spaces, or parameter names**. The return type is placed **outside** the parentheses. Examples:

| Java declaration | JNI descriptor |
| --- | --- |
| `int add(int x, int y)` | `(II)I` |
| `void log()` | `()V` |
| `String format(int n)` | `(I)Ljava/lang/String;` |
| `boolean contains(String text, int[] values)` | `(Ljava/lang/String;[I)Z` |
| `long count(byte[] data, String prefix)` | `([BLjava/lang/String;)J` |
| `String[] split(String s)` | `(Ljava/lang/String;)[Ljava/lang/String;` |
| `void accept(String... args)` | `([Ljava/lang/String;)V` |

A method with no parameters uses `()`; do not omit the parentheses. **The return type is a mandatory part of the descriptor**: `(I)I` differs from `(I)V`. When multiple overloaded methods share the same name, the descriptor identifies the exact version, for example `foo(int)` is `(I)V` and `foo(long)` is `(J)V` if both return `void`.

### 3.4. Field Descriptors Differ from Method Descriptors

The field `int count` has signature **`"I"`**, not `"()I"`. The method `int getCount()` has signature **`"()I"`**, not `"I"`. The two strings are not interchangeable. There is also no field of type `void`.

For a constructor with parameters `(int, String)`, `GetMethodID` uses the special name **`"<init>"`** and descriptor `"(ILjava/lang/String;)V"`, and then `NewObject` uses this ID to create an instance. `<init>` is not the name of an ordinary Java method; do not look up the static initializer `<clinit>` this way.

## 4. From IDs to Type-Appropriate Operations

Lookup is only step one. To **read, write, or invoke**, choose the function matching **static/instance** and the **actual type** of the member.

| Member | Get ID | Correct access |
| --- | --- | --- |
| `int count` instance | `GetFieldID(...,"count","I")` | `GetIntField(env,obj,id)` / `SetIntField(env,obj,id,value)` |
| `static int scale` | `GetStaticFieldID(...,"scale","I")` | `GetStaticIntField(env,cls,id)` / `SetStaticIntField(env,cls,id,value)` |
| `String name` instance | `GetFieldID(...,"name","Ljava/lang/String;")` | `GetObjectField(env,obj,id)` / `SetObjectField(...)` |
| `int add(int)` instance | `GetMethodID(...,"add","(I)I")` | `CallIntMethod(env,obj,id,arg)` |
| `static String describe(int,int)` | `GetStaticMethodID(...,"describe","(II)Ljava/lang/String;")` | `CallStaticObjectMethod(env,cls,id,arg1,arg2)` |
| `void done()` instance | `GetMethodID(...,"done","()V")` | `CallVoidMethod(env,obj,id)` |

`GetObjectField` returns a **JNI local reference** to the object value (which may be `NULL`); this reference value is **different** from `jfieldID`. `CallObjectMethod` returns a reference to the result object (or `NULL`); it is **different** from `jmethodID`. Other call families include `CallLongMethod`, `CallBooleanMethod`, and `CallStaticVoidMethod`.

The `Call<Type>MethodA` functions take a `jvalue` array; `Call<Type>MethodV` takes a `va_list`, suitable when packing arguments dynamically. You still need the correct descriptor and ID. `CallNonvirtual<Type>Method` is for special dispatch behavior, not a default replacement for `Call<Type>Method`.

## 5. Complete Java 17+ Example: Getting Both IDs, Calling Methods, and Reading/Writing Fields

This example demonstrates **all four lookup APIs**, with no external library dependencies. Java has an instance field, a static field, an instance method, and a static method. C retrieves the IDs by name/descriptor, reads the state, calls Java to compute, updates the field, and then calls Java to produce the result string.

### 5.1. Project Structure

```text
jni-id-lookup/
├── src/
│   └── demo/
│       └── jni/
│           └── IdLookupDemo.java
├── native/
│   └── idlookup.c
└── build/                   # generated during the build process
```

The commands below are for **Linux + JDK 17+ + GCC**. On Windows/macOS, the shared library filename and JNI include paths differ; the Java source and descriptors remain the same.

### 5.2. Create `src/demo/jni/IdLookupDemo.java`

```java
package demo.jni;

public final class IdLookupDemo {
    static {
        System.loadLibrary("idlookup");
    }

    private int count = 7;            // instance field: I
    private static int scale = 3;     // static field: I

    private int add(int delta) {      // instance method: (I)I
        return count + delta;
    }

    private static String describe(int before, int after) {
        // static method: (II)Ljava/lang/String;
        return "count " + before + " -> " + after;
    }

    private native String inspectAndUpdate();

    public static void main(String[] args) {
        IdLookupDemo demo = new IdLookupDemo();
        System.out.println("Before: " + demo.count);
        System.out.println("Native: " + demo.inspectAndUpdate());
        System.out.println("After: " + demo.count);
    }
}
```

The members are intentionally `private` to show that JNI lookup is not restricted by Java access modifiers. With untrusted native code, this is an important reason to manage the JNI boundary carefully: native code can interact deeply with state inside the JVM.

Expected ID table:

| Member | Lookup function | Name | Signature |
| --- | --- | --- | --- |
| `count` | `GetFieldID` | `"count"` | `"I"` |
| `scale` | `GetStaticFieldID` | `"scale"` | `"I"` |
| `add(int)` | `GetMethodID` | `"add"` | `"(I)I"` |
| `describe(int,int)` | `GetStaticMethodID` | `"describe"` | `"(II)Ljava/lang/String;"` |

### 5.3. Generate the JNI Header from Java

From the `jni-id-lookup` directory:

```bash
mkdir -p build/classes build/headers build/lib

javac -encoding UTF-8 \
  -h build/headers \
  -d build/classes \
  src/demo/jni/IdLookupDemo.java
```

The compiler creates `build/classes/demo/jni/IdLookupDemo.class` and `build/headers/demo_jni_IdLookupDemo.h`. The header is for the **native entry point** `inspectAndUpdate`; it does not automatically list all fields/methods that C will look up later.

The relevant part of the header is equivalent to:

```c
#include <jni.h>

/* Class: demo_jni_IdLookupDemo
 * Method: inspectAndUpdate
 * Signature: ()Ljava/lang/String;
 */
JNIEXPORT jstring JNICALL Java_demo_jni_IdLookupDemo_inspectAndUpdate
  (JNIEnv *, jobject);
```

This is an illustrative excerpt; the actual header also has include guards and a C++ block. C must include **the header actually generated by the compiler**, rather than manually editing the entry point signature.

### 5.4. Implement `native/idlookup.c`

```c
#include <jni.h>
#include "demo_jni_IdLookupDemo.h"

JNIEXPORT jstring JNICALL Java_demo_jni_IdLookupDemo_inspectAndUpdate(
        JNIEnv *env, jobject self) {

    // Because this is an instance native method, self is the calling object.
    jclass cls = (*env)->GetObjectClass(env, self);
    if (cls == NULL) {
        return NULL;  // Preserve the exception set by the JVM (if any).
    }

    jstring report = NULL;

    // 1) Instance field: int count  -> I
    jfieldID countId = (*env)->GetFieldID(env, cls, "count", "I");
    if (countId == NULL) {
        goto cleanup;
    }

    // 2) Static field: static int scale -> I
    jfieldID scaleId =
            (*env)->GetStaticFieldID(env, cls, "scale", "I");
    if (scaleId == NULL) {
        goto cleanup;
    }

    // 3) Instance method: int add(int) -> (I)I
    jmethodID addId =
            (*env)->GetMethodID(env, cls, "add", "(I)I");
    if (addId == NULL) {
        goto cleanup;
    }

    // 4) Static method: String describe(int,int)
    //    -> (II)Ljava/lang/String;
    jmethodID describeId = (*env)->GetStaticMethodID(
            env, cls, "describe", "(II)Ljava/lang/String;");
    if (describeId == NULL) {
        goto cleanup;
    }

    jint before = (*env)->GetIntField(env, self, countId); // 7
    jint factor = (*env)->GetStaticIntField(env, cls, scaleId); // 3

    // JNI calls back into the Java instance method.
    jint sum = (*env)->CallIntMethod(env, self, addId, (jint)5); // 12
    if ((*env)->ExceptionCheck(env)) {
        goto cleanup;
    }

    // Use only small values in the example to avoid C overflow.
    jint after = sum * factor; // 36
    (*env)->SetIntField(env, self, countId, after);

    // JNI calls back into the Java static method.
    report = (jstring)(*env)->CallStaticObjectMethod(
            env, cls, describeId, before, after);

    if ((*env)->ExceptionCheck(env)) {
        report = NULL; // The Java exception will be propagated to the caller by the JVM.
    }

cleanup:
    // cls is a local reference, whereas the IDs are not JNI references.
    (*env)->DeleteLocalRef(env, cls);
    return report;
}
```

Key points to observe:

1. `GetObjectClass(env, self)` retrieves the `jclass` matching the **runtime class** of the object, avoiding manual class name string construction for this example.
2. Both `Get...FieldID` calls take the signature `"I"`, without `()`. Both `Get...MethodID` calls take signatures with parameter parentheses and return type.
3. `GetIntField` needs **`self`**, `GetStaticIntField` needs **`cls`**; `CallIntMethod` needs `self`, `CallStaticObjectMethod` needs `cls`.
4. `CallIntMethod` executes Java `add(5)` so it gets `7 + 5 = 12`. C multiplies `12 * 3 = 36` and then `SetIntField` updates `count` on the **same object**.
5. `CallStaticObjectMethod` calls Java `describe(7, 36)` to return the string `"count 7 -> 36"`. `report` is a local reference to the Java string, which can be **returned** to the native call in Java; do not delete `report` before returning.
6. If a lookup returns `NULL`, JNI may already have left a pending exception. `goto cleanup` only cleans up the **local reference** and returns to the JVM so the exception is thrown; do not continue using the invalid ID. If the Java method throws an exception, `ExceptionCheck` detects it and avoids continuing calculations with an invalid return value.

`DeleteLocalRef` is one of the JNI operations permitted while an exception is pending, so the cleanup section remains valid. In a real program you need to decide the policy for catching/logging/propagating exceptions to the caller; the example preserves the exception for Java.

### 5.5. Compile C and Run

Configure `JAVA_HOME` to point to a **JDK** (containing `include/jni.h` and `include/linux/jni_md.h`), then run:

```bash
gcc -std=c11 -Wall -Wextra -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  -o build/lib/libidlookup.so \
  native/idlookup.c

java -Xcheck:jni \
  -Djava.library.path=build/lib \
  -cp build/classes \
  demo.jni.IdLookupDemo
```

The paths:

- `-Ibuild/headers` lets the C compiler find `demo_jni_IdLookupDemo.h`.
- `libidlookup.so` corresponds to the logical name `"idlookup"` in `System.loadLibrary`.
- `-Djava.library.path=build/lib` helps the JVM find the library in the location just created.
- `-Xcheck:jni` enables extra JNI checks to make it easier to detect wrong IDs/references/threads during learning and debugging.

**Exact expected stdout** with the data in the example:

```text
Before: 7
Native: count 7 -> 36
After: 36
```

In the run, `Before` is printed before entering JNI; `Native` is printed when `inspectAndUpdate()` returns the string; `After` reads the `count` field that C updated via `SetIntField`. The output proves that both method lookup and field lookup pointed to the right members.

## 6. Self-Verify Signatures with `javap -s -p`

Instead of guessing descriptors, compile the Java code and inspect the **bytecode** with `javap`:

```bash
javap -s -p -classpath build/classes demo.jni.IdLookupDemo
```

In the relevant section, the tool will display declarations equivalent to:

```text
private int count;
  descriptor: I
private static int scale;
  descriptor: I
private int add(int);
  descriptor: (I)I
private static java.lang.String describe(int, int);
  descriptor: (II)Ljava/lang/String;
private native java.lang.String inspectAndUpdate();
  descriptor: ()Ljava/lang/String;
```

Actual output also includes other members such as the constructor, static initializer, and `main` method. Simply compare each `descriptor:` line against the string passed to `GetFieldID`/`GetMethodID`; do not convert it back to Java syntax manually. For overloaded methods, check the **exact overloaded line** by parameters and descriptor.

`javac -h` and `javap -s` solve two different tasks:

- `javac -h` generates C headers for **Java → C native entry points**.
- `javap -s -p` helps inspect descriptors of **Java members that C will look up/call back into**, including private members.

Precisely because C calls regular Java methods that have bodies, the JNI header generated from `native` **cannot replace** the step of looking up descriptors for members accessed at runtime.

## 7. Complex Cases: Overloading, Inheritance, Constructors, Generics

### 7.1. Overloads Must Match Each Signature

Suppose Java has:

```java
int convert(int x) { return x; }
long convert(long x) { return x; }
String convert(String x) { return x; }
```

The descriptors are `(I)I`, `(J)J`, and `(Ljava/lang/String;)Ljava/lang/String;` respectively. Passing only `"convert"` is not enough; passing `"(I)J"` also does not match the first method because the return type differs from `I`.

Java does not allow overloading solely by return type in source code, but **JNI descriptors always include the return type**. Do not omit it when constructing an ID lookup.

### 7.2. Inheritance and Field Hiding

`GetMethodID` can find an instance method declared in a superclass/interface and inherited. For overridden instance methods, normal `Call<Type>Method` calls use dispatch appropriate to the Java object. `CallNonvirtual<Type>Method` has its own semantics and should not be used arbitrarily as a replacement.

Fields can be **hidden** when a subclass and superclass declare the same field name. When you need the field declared at a specific level, use the `jclass` of the **exact declaring class**; do not assume the runtime class of `self` will pick the desired level. `jfieldID` identifies a field, not a generic name to re-query according to native code's intent.

### 7.3. Constructors

To get the constructor `new Widget(int)`:

```c
jmethodID ctor =
    (*env)->GetMethodID(env, widgetClass, "<init>", "(I)V");
if (ctor == NULL) {
    return NULL;  // Illustrative snippet: must handle exceptions and cleanup.
}

jobject obj = (*env)->NewObject(env, widgetClass, ctor, (jint)5);
```

This is a **local illustrative snippet**, assuming `env`/`widgetClass` are valid and the enclosing function returns `jobject`. A constructor always has the descriptor return type `V`. `GetStaticMethodID` is not for constructors.

### 7.4. Type Erasure and Arrays

The following Java examples (illustrative, not part of the runnable program in section 5):

```java
java.util.List<String> names;
int[][] matrix;
String[] labels;
void submit(java.util.List<Integer> values) { }
```

The corresponding signatures are `Ljava/util/List;`, `[[I`, `[Ljava/lang/String;`, and `(Ljava/util/List;)V`. Generic type arguments undergo **erasure** in descriptors. When an API has compiler-generated bridge methods, check `javap -s -p` instead of assuming every signature matches the source verbatim.

### 7.5. Cannot Get `array.length` with `GetFieldID`

`GetFieldID` does not retrieve the "`length` field" of a Java array. For a `jarray array`, use `GetArrayLength(env, array)`. Similarly, to get the class of an instance, use `GetObjectClass`; do not treat VM-internal concepts as fields that can be looked up arbitrarily.

## 8. Handling Lookup Errors and Pending Exceptions

The APIs `GetMethodID`, `GetStaticMethodID`, `GetFieldID`, and `GetStaticFieldID` return an ID or `NULL`. A failed lookup by specification can cause:

- `NoSuchMethodError` if the method name/signature/kind is not found.
- `NoSuchFieldError` if a field with the matching name/signature/kind does not exist.
- `ExceptionInInitializerError` if class initialization throws an exception.
- `OutOfMemoryError` when the JVM runs out of memory.

Therefore, the safe workflow is:

1. Call the right `Get...ID`.
2. Check whether the ID is non-`NULL` **before** using it.
3. If `NULL`, clean up permitted local references/native resources and return to Java with the pending exception, **or** explicitly handle the exception according to the designed contract.
4. Do not call `Call...Method`, `Get...Field`, or `Set...Field` with a `NULL` ID. Do not continue calling arbitrary JNI APIs while an exception is pending.

Example of a lookup error due to a mistyped signature:

```c
jmethodID bad = (*env)->GetMethodID(
    env, cls, "add", "(J)I");  // Wrong: add takes int, not long.
if (bad == NULL) {
    // The JVM may have already set NoSuchMethodError.
    // Perform valid cleanup and return to Java so the exception propagates.
}
```

This is an **intentional error illustration snippet** to recognize the issue; do not insert it into the working `idlookup.c` from section 5.

If the error is a situation that must be handled in native code, you can inspect the details with `ExceptionOccurred` (it returns a local reference to the throwable), decide whether to convert it to an error code or a new exception, and call `ExceptionClear` **only when you genuinely need to discard the old exception**. Do not automatically clear every exception after a bad lookup: doing so hides JNI programming bugs and creates hard-to-debug states.

A practical note: `-Xcheck:jni` helps detect many cases of using wrong IDs, wrong reference types, or calling JNI while an exception is pending, but it does not prove native code is memory-safe. Some JNI bugs crash the JVM directly and do not necessarily surface as an easily catchable Java exception.

## 9. Lifecycle and Proper Caching of `jmethodID`/`jfieldID`

Lookups have a cost, so some libraries keep IDs for reuse. However, an ID **remains valid only as long as the class that defined it stays loaded by the JVM**. According to the JNI Specification, an ID by itself **does not keep a class from being unloaded**. If the class is unloaded, the old ID must not be reused; you must keep a live reference to the class or look it up again.

Distinguish three concepts:

| JNI value | What kind is it? | How to manage |
| --- | --- | --- |
| `jclass cls` from `GetObjectClass` / `FindClass` | **Local reference** to a Java class | Valid within the local frame/thread; `DeleteLocalRef` when done |
| `jmethodID`, `jfieldID` | **Opaque member IDs** | Do not call `DeleteLocalRef`, do not keep the class alive; only use while the class is loaded |
| `jclass globalCls` from `NewGlobalRef(env, cls)` | **Global reference** to a class | Can be stored across JNI calls and multiple threads when valid; requires `DeleteGlobalRef` on cleanup |

When designing a long-lived cache, a sound pattern in principle is to obtain the `jclass` from the right class loader, create a **global reference** to keep the class alive, retrieve/store member IDs alongside that class, and on shutdown stop active callbacks/lookups before deleting the global reference. Initialization/destruction of the cache and threads using it must be synchronized. A cache keyed only by class name while ignoring the **class loader** may look up the wrong class with the same name.

**Do not cache `JNIEnv *` for use from another thread.** `JNIEnv` is bound to a thread; a self-created native thread must attach to the JVM via the Invocation API and obtain that thread's own `JNIEnv *`. IDs can be reused across appropriate threads while the class remains alive, but objects/references, callback ordering, and accessed data still require proper synchronization.

For small examples, looking up IDs on each call is easier to understand and safer for lifecycle management. Only optimize with caching after actually measuring lookup cost and defining clear ownership.

## 10. Quick Diagnosis of Name/Signature Errors

| Symptom | Common cause | How to verify/fix |
| --- | --- | --- |
| `GetMethodID` returns `NULL`, `NoSuchMethodError` | Wrong name, parameters, **return type**, static/instance | Compare with `javap -s -p`; use the right `GetMethodID` or `GetStaticMethodID` |
| `GetFieldID` returns `NULL`, `NoSuchFieldError` | Wrong name, descriptor, or the field is static | Check field descriptor in `javap`; switch to `GetStaticFieldID` if needed |
| `GetObjectField` used for `int` | Wrong getter family for the type | Use `GetIntField` with a field ID of type `I` |
| `String` reference lookup fails | Used `Ljava.lang.String;` or missing `;` | Use `Ljava/lang/String;` |
| Generic field not found | Used type argument instead of type-erased descriptor | Use `Ljava/util/List;` for `List<String>` |
| Wrong overloaded method called | Only checked method name | Check exact descriptor including parameters and return type |
| Cached ID later crashes JVM | Class was unloaded or ID belongs to another class loader | Hold a global class reference or re-lookup ID on the right class |
| Native thread JNI call fails | Used another thread's `JNIEnv *` | Attach/get a separate `JNIEnv *` on the current thread |
| Lookup succeeds but Java does not run as expected | Wrong `Call<Type>Method` or wrong object/class | Match return type, static/instance, and Java dispatch |
| `UnsatisfiedLinkError` on `inspectAndUpdate` | Native entry point/library not found | Generate header with `javac -h`, check `libidlookup.so` and `java.library.path` |

Do not "fix" issues by casting `jmethodID` to `jfieldID` or using a dummy `jobject`. If the descriptor string or access method is wrong, fix the **Java ↔ JNI contract** at the source and rebuild.

## 11. Reinforcement Exercises

1. For Java `private long id;` and `private static String label;`, write the two correct `GetFieldID`/`GetStaticFieldID` calls (including descriptors) and their corresponding getters.
2. For `boolean contains(String text, int[] values)`, what is the method descriptor? Which `Call<Type>Method` function must be used to receive the `boolean` result?
3. Why is `GetMethodID(env, cls, "add", "(I)V")` wrong for the method `int add(int)`? Why is `GetFieldID(..., "count", "()I")` also wrong?
4. If `describe(int,int)` is changed from `static` to an instance method while C keeps `GetStaticMethodID`, what can the outcome be? How must the subsequent calls be replaced?
5. In the runnable example, trace all four IDs to explain why stdout is `Before: 7`, `Native: count 7 -> 36`, `After: 36`.
6. A library stores a `jmethodID` in a global variable and the class gets unloaded. Why is the ID no longer usable? What kind of reference must be held and how should it be cleaned up?
7. Use `javap -s -p` to determine the descriptor of a method with `String[]` and `List<Long>`; explain why generic type arguments do not appear in JNI descriptors.

**Remember:** To get `jmethodID`/`jfieldID` accurately, you must know the **right class, right name, right descriptor, and right static/instance**. After lookup, check `NULL` and exceptions; then choose the right `Call...Method` or `Get/Set...Field`. IDs are not Java references and do not keep a class from unloading.

### Official Documentation

- JNI Specification — [Types and Data Structures / Type Signatures](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/types.html).
- JNI Specification — [Functions: `GetMethodID`, `GetFieldID`, static counterparts](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/functions.html).
- JNI Specification — [Design Overview: Accessing Fields and Methods; ID lifetime](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html).
- JDK `javap` tool (JDK 21): https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html.
