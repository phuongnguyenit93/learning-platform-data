# Reading or Writing Instance Fields and Static Fields Using Type-Safe Functions in JNI

## Learning Objectives

When C/C++ code calls back into the Java world through the Java Native Interface (JNI), it cannot read or modify Java fields by treating a Java object as a C struct and accessing memory directly. After this lesson, you will:

1. Distinguish between **instance** fields (belonging to each object) and **static** fields (belonging to the class) when accessing them from JNI.
2. Identify the correct **jclass**, **jobject**, **jfieldID**, and **field descriptor** before reading/writing.
3. Choose the exact **Get<Type>Field / Set<Type>Field** or **GetStatic<Type>Field / SetStatic<Type>Field** function pair corresponding to the Java type.
4. Understand how to read/write primitives, String, objects, and arrays; manage local references returned by JNI.
5. Handle cases of wrong name lookup, wrong signature, wrong static/instance, failed class initialization, or a pending exception.
6. Run a complete Java 17+ and C/JNI example to see Java data modified from native code, then apply a safety checklist for production.

The scope focuses on **accessing Java fields from JNI**. Broader topics such as calling Java methods, managing native arrays, pinning, or designing the entire JNI lifecycle are only mentioned when they directly affect field operations.

## 1. Why Does JNI Need Field Accessor Functions?

Suppose Java defines:

~~~java
final class SampleState {
    private int count = 7;
    private String name = "initial";

    private static long total = 100L;
    private static String mode = "idle";
}
~~~

We have two types of fields with different lifecycles:

| Java Field | Logical Owner | Required to Access from JNI |
| --- | --- | --- |
| **count**, type int | Each SampleState object | A **jobject**, field ID of type **I**, functions **GetIntField / SetIntField** |
| **name**, type String | Each SampleState object | A **jobject**, field ID of type **Ljava/lang/String;**, functions **GetObjectField / SetObjectField** |
| **total**, type static long | SampleState class | A **jclass**, static field ID of type **J**, functions **GetStaticLongField / SetStaticLongField** |
| **mode**, type static String | SampleState class | A **jclass**, static field ID of type **Ljava/lang/String;**, functions **GetStaticObjectField / SetStaticObjectField** |

In pure Java, the compiler and JVM know the type, class, field offset, and access rules. JNI provides a **semantically stable interface**, so native code uses explicitly named operations instead of guessing Java object layouts. The actual layout can vary across JVMs, garbage collectors, JIT, and runtime configurations.

JNI operates through **Java references** managed by the JVM. A **jobject is not a direct C pointer to a struct** of the Java object; never cast it and use pointer arithmetic to find a field.

### Four Foundational Components

- **JNIEnv \***: the JNI function table used in the current thread; do not share this pointer across different native threads.
- **jobject**: a reference to a specific Java object; used with instance fields.
- **jclass**: a reference to a Class object managed by the JVM; used to look up field IDs and access static fields.
- **jfieldID**: a field identifier issued by the JVM; it is not a jobject, not a Java reference, and must not be passed to DeleteLocalRef.

A field ID is looked up by **field name + type descriptor + instance/static kind + associated class**. Once looked up successfully, get/set operations do not need to search for the field name again on each access.

## 2. Standard Workflow: Find Class → Find Field ID → Access with the Right Function Family

For an object already received from Java into a native method:

~~~c
// Illustrative example inside a native method with valid env and obj.
jclass cls = (*env)->GetObjectClass(env, obj);
if (cls == NULL) {
    return; // A corresponding exception is already pending, e.g. allocation error.
}

jfieldID countId = (*env)->GetFieldID(env, cls, "count", "I");
if (countId == NULL) {
    (*env)->DeleteLocalRef(env, cls);
    return; // Do not continue when lookup fails.
}

jint oldCount = (*env)->GetIntField(env, obj, countId);
(*env)->SetIntField(env, obj, countId, oldCount + 1);

(*env)->DeleteLocalRef(env, cls);
~~~

**This snippet is only an excerpt**, not a complete C file: it assumes `env`, `obj`, a Java class with an `int` field `count`, and a suitable native method are already available. A standalone runnable example appears in section 7.

This workflow has three steps:

1. **GetObjectClass(env, obj)** obtains a **local jclass reference** pointing to the runtime class of the object.
2. **GetFieldID(env, cls, "count", "I")** looks up the **instance field** named `count` with descriptor **I**, returning a `jfieldID`.
3. **GetIntField / SetIntField** performs the access with **jobject obj** and the found field ID.

For **static fields**, two things change: use **GetStaticFieldID** to look up the ID, then use **GetStaticIntField / SetStaticIntField** (or the corresponding function family) with **jclass**, not passing `jobject` in that position.

### Comparison Table: Instance vs. Static

| Operation | Instance field | Static field |
| --- | --- | --- |
| Look up ID | **GetFieldID(env, cls, name, sig)** | **GetStaticFieldID(env, cls, name, sig)** |
| Read int | **GetIntField(env, obj, id)** | **GetStaticIntField(env, cls, id)** |
| Write int | **SetIntField(env, obj, id, value)** | **SetStaticIntField(env, cls, id, value)** |
| Read String or object | **GetObjectField(env, obj, id)** | **GetStaticObjectField(env, cls, id)** |
| Write String or object | **SetObjectField(env, obj, id, ref)** | **SetStaticObjectField(env, cls, id, ref)** |
| Argument holding data | **jobject** holding per-instance values | **jclass** representing the class declaring/accessing static |

The word **Static** in the function name is a mandatory marker. Do not obtain the ID of a static field with `GetFieldID`, do not use `SetIntField` to write a static `int`, and do not mix a static `jfieldID` with the instance family or vice versa.

## 3. Field Descriptor: Describes Type, Not Method

A **descriptor** is a type notation string used by the JVM/JNI. Field lookup requires a descriptor matching the **declared type of the field**, not the value type you want to cast to or the C type of the receiving variable.

| Java Declared Type | Field Descriptor | JNI Type / Accessor Family |
| --- | --- | --- |
| boolean | **Z** | **jboolean**, Boolean |
| byte | **B** | **jbyte**, Byte |
| char | **C** | **jchar**, Char |
| short | **S** | **jshort**, Short |
| int | **I** | **jint**, Int |
| long | **J** | **jlong**, Long |
| float | **F** | **jfloat**, Float |
| double | **D** | **jdouble**, Double |
| java.lang.String | **Ljava/lang/String;** | **jobject/jstring**, Object |
| java.util.List | **Ljava/util/List;** | **jobject**, Object |
| int[] | **[I** | **jobject/jintArray**, Object |
| String[] | **[Ljava/lang/String;** | **jobject/jobjectArray**, Object |
| int[][] | **[[I** | **jobject** (can use the appropriate array reference type), Object |

For reference types, the descriptor starts with **L**, uses class names with **/** instead of **.**, and ends with **;**. Arrays use one **[** for each dimension. Field types do not have parentheses; strings like **(I)V** are **method descriptors** and cannot be used to look up an `int` field.

Lookup examples:

~~~c
jfieldID pointsId =
    (*env)->GetFieldID(env, cls, "points", "I");

jfieldID titleId =
    (*env)->GetFieldID(env, cls, "title", "Ljava/lang/String;");

jfieldID valuesId =
    (*env)->GetFieldID(env, cls, "values", "[I");

jfieldID objectsId =
    (*env)->GetStaticFieldID(env, cls, "objects", "[Ljava/lang/Object;");
~~~

This is a standalone illustration of **descriptor strings**; it requires the corresponding fields to actually exist in the class. Lookup calls must be **checked for errors before using the ID**, as shown in the complete example.

### How to Avoid Guessing Descriptors Wrong

For compiled classes, the command **javap -s -private ClassName** displays field names and descriptors:

~~~bash
javac SampleState.java
javap -s -private SampleState
~~~

The **-private** flag makes private fields visible as well; **-s** displays descriptors. You can use **javap -s** as direct evidence when Java source changes or when descriptors of nested types are complex. Do not guess uppercase/lowercase letters: **I differs from J**, **L differs from [**, and **Ljava/lang/String;** must have a trailing semicolon.

## 4. Reading/Writing Primitives with Type-Safe Functions

JNI has specific function families for each primitive. The notation **<Type>** in documentation represents one of the suffixes below; in real C code, the **full function name** must be used.

| Java type | Read instance | Write instance | Read static | Write static |
| --- | --- | --- | --- | --- |
| boolean | GetBooleanField | SetBooleanField | GetStaticBooleanField | SetStaticBooleanField |
| byte | GetByteField | SetByteField | GetStaticByteField | SetStaticByteField |
| char | GetCharField | SetCharField | GetStaticCharField | SetStaticCharField |
| short | GetShortField | SetShortField | GetStaticShortField | SetStaticShortField |
| int | GetIntField | SetIntField | GetStaticIntField | SetStaticIntField |
| long | GetLongField | SetLongField | GetStaticLongField | SetStaticLongField |
| float | GetFloatField | SetFloatField | GetStaticFloatField | SetStaticFloatField |
| double | GetDoubleField | SetDoubleField | GetStaticDoubleField | SetStaticDoubleField |

For example, if Java has **private boolean enabled** and **private static double factor**:

~~~c
jfieldID enabledId =
    (*env)->GetFieldID(env, cls, "enabled", "Z");
if (enabledId == NULL) {
    return;
}

jboolean enabled = (*env)->GetBooleanField(env, obj, enabledId);
(*env)->SetBooleanField(
    env, obj, enabledId, enabled == JNI_TRUE ? JNI_FALSE : JNI_TRUE
);

jfieldID factorId =
    (*env)->GetStaticFieldID(env, cls, "factor", "D");
if (factorId == NULL) {
    return;
}

jdouble factor = (*env)->GetStaticDoubleField(env, cls, factorId);
(*env)->SetStaticDoubleField(env, cls, factorId, factor * 2.0);
~~~

This is an **illustrative snippet**, assuming `env`, `obj`, `cls` are valid and the fields exist; production code must clean up local references and handle exceptions according to context. In this code:

- **enabled** has descriptor **Z**, so it uses **GetBooleanField / SetBooleanField** and type **jboolean**.
- **factor** has descriptor **D**, is a **static double** field, so it uses **GetStaticDoubleField / SetStaticDoubleField** and type **jdouble**.
- JNI boolean values should use **JNI_TRUE** and **JNI_FALSE** instead of inferring from how the C compiler represents booleans.
- **jchar** is a 16-bit UTF-16 code unit; it is not identical to C's 8-bit **char**.
- **jlong** is the JNI type for 64-bit Java `long`; do not assume that **long** in C is always 64 bits long (Windows has a different ABI model from many Unix systems).
- Do not read an **int** field with **GetLongField** expecting JNI to widen the type automatically. For field descriptor **I**, you must use **GetIntField**; if a `long` is needed, perform an intentional type conversion in C after receiving **jint**.

### Serious Mistake Example

~~~c
jfieldID id = (*env)->GetFieldID(env, cls, "score", "I");

// Wrong: score is declared as int, yet a double getter is used.
jdouble wrong = (*env)->GetDoubleField(env, obj, id);
~~~

This code is intentionally wrong and **must not be run in a real application**. JNI has contract conditions on field ID types and accessor types; violating them can cause severe errors, crashes, or unpredictable behavior. When **-Xcheck:jni** is enabled on a supported JVM, many misuses are detected early, but check mode does not replace proper design.

## 5. Reading/Writing String, Objects, and Arrays: Use the Object Family

Fields of **reference** type do not use a separate getter named String/Array/List. Instead, JNI provides:

- **GetObjectField(env, obj, id)** and **SetObjectField(env, obj, id, value)** for instance reference fields.
- **GetStaticObjectField(env, cls, id)** and **SetStaticObjectField(env, cls, id, value)** for static reference fields.

In C code, the read result has type **jobject**. With the correct declared type, it can be cast to **jstring**, **jintArray**, or a corresponding JNI reference type to use specialized APIs. A C cast **does not change the actual type of the Java object**, so you must adhere to the descriptor and field contract.

Java example:

~~~java
final class ReferenceHolder {
    private String title = "old";
    private int[] scores = {3, 4};
    private static String status = "idle";
}
~~~

Corresponding JNI calls:

~~~c
// Illustrative snippet: assumes env, obj, cls are valid;
// all lookups must be checked for success before use.
jfieldID titleId =
    (*env)->GetFieldID(env, cls, "title", "Ljava/lang/String;");
jfieldID scoresId =
    (*env)->GetFieldID(env, cls, "scores", "[I");
jfieldID statusId =
    (*env)->GetStaticFieldID(env, cls, "status", "Ljava/lang/String;");

jstring title = (jstring)(*env)->GetObjectField(env, obj, titleId);
jintArray scores = (jintArray)(*env)->GetObjectField(env, obj, scoresId);
jstring status = (jstring)(*env)->GetStaticObjectField(env, cls, statusId);

// When no longer needed:
if (title != NULL) (*env)->DeleteLocalRef(env, title);
if (scores != NULL) (*env)->DeleteLocalRef(env, scores);
if (status != NULL) (*env)->DeleteLocalRef(env, status);
~~~

**Note:** the snippet above is shortened to illustrate the right getter types; you must check **titleId/scoresId/statusId != NULL** before each getter call, and do not call additional regular JNI APIs when there is a pending exception. The complete example in section 7 demonstrates this control flow.

### Local References Differ from the Field's Value

**GetObjectField** and **GetStaticObjectField** return a JNI **local reference** to the Java object currently stored in the field (or `NULL` if the Java field is `null`). Local references returned by JNI are typically only valid within the current native call, and long native calls/loops that create many references need **DeleteLocalRef** or local frames to avoid accumulation.

Conversely, when creating a new string:

~~~c
jstring text = (*env)->NewStringUTF(env, "updated");
if (text == NULL) {
    return; // OutOfMemoryError may be pending.
}
(*env)->SetObjectField(env, obj, titleId, text);
(*env)->DeleteLocalRef(env, text);
~~~

Calling **DeleteLocalRef(text)** only drops the **JNI local reference**. After a successful assignment, the Java field still holds its reference to the String; the object does not disappear just because the local reference was deleted. Never use **free(text)** because **jstring is not a malloc pointer**.

**NewStringUTF** takes modified UTF-8 according to the JNI contract; if the source data is an arbitrary UTF-8 string from I/O (especially with null bytes or invalid encoding sequences), it must be converted according to proper rules rather than assuming every byte buffer is modified UTF-8. The example in section 7 uses only ASCII text so this difference does not arise.

### Arrays Are Object Fields, but Length Is Not a Lookable Field

If Java declares **int[] scores**, use **GetObjectField** with descriptor **[I** to obtain the array reference. Then you can call **GetArrayLength(env, scores)** to get the length; do not use **GetFieldID(..., "length", "I")** on array types. Reading elements requires JNI array APIs (such as `GetIntArrayRegion`), which are outside the field-access scope of this lesson.

## 6. What Are the Important Differences for Static Fields?

Each runtime class has its own static state per class/class loader identity. When reading/writing a static field from JNI:

1. Obtain the **jclass** representing the relevant class.
2. Call **GetStaticFieldID** with the correct name and descriptor.
3. Use **GetStatic<Type>Field / SetStatic<Type>Field** with the **jclass** and corresponding ID.
4. Clean up the **jclass local reference** if no longer needed.

Example for Java **static int nextId = 20**:

~~~c
jfieldID id =
    (*env)->GetStaticFieldID(env, cls, "nextId", "I");
if (id == NULL) {
    return; // NoSuchFieldError may be pending.
}

jint current = (*env)->GetStaticIntField(env, cls, id);
(*env)->SetStaticIntField(env, cls, id, current + 1);
~~~

There is no **jobject** argument in the two static functions here. Also, do not use **GetFieldID** because `nextId` is static.

### Field ID Lookup Can Trigger Class Initialization

According to the JNI Specification, both **GetFieldID** and **GetStaticFieldID** can trigger **class initialization** if the class has not been initialized yet. This can execute Java static blocks, leading to library loading, I/O, or initialization exceptions.

If lookup fails, you may encounter **NoSuchFieldError** (the right field could not be found) or **ExceptionInInitializerError** if class initialization throws a corresponding exception, along with certain resource errors. Do not assume `GetFieldID`/`GetStaticFieldID` merely look up metadata and have no side effects at all.

In the hands-on example, the native method is called **after the Java class has already been initialized**, so the field lookup does not cause an additional initialization cycle.

### Warning About static final

Do not use JNI to modify the value of a **final field**, especially a **static final constant**, as a configuration mechanism. Current JNI documentation warns that although it is possible to pass a final field's ID to a setter, the result can cause unexpected exceptions or crashes. The Java compiler/JIT can also optimize or inline constant values, causing readers to observe inconsistent values.

Good rule: treat **final** as immutable by contract; put mutable configuration in a Java API with a controlled setter, an intentionally replaced immutable data structure, or an appropriate state management mechanism.

## 7. Complete Practice: Java 17+ Combined with C/JNI

The example below reads and writes **four fields** of the same class:

- **count**: instance int → GetIntField / SetIntField.
- **label**: instance String → GetObjectField / SetObjectField.
- **total**: static long → GetStaticLongField / SetStaticLongField.
- **mode**: static String → GetStaticObjectField / SetStaticObjectField.

The Java code prints before/after values; the C code accesses the fields through the right IDs and the right accessor families.

### Step 1 — Create FieldAccessDemo.java

~~~java
public final class FieldAccessDemo {
    private int count = 7;
    private String label = "initial";

    private static long total = 100L;
    private static String mode = "idle";

    static {
        System.loadLibrary("fieldaccessdemo");
    }

    private native void mutate();

    public static void main(String[] args) {
        FieldAccessDemo data = new FieldAccessDemo();

        System.out.printf(
            "before: count=%d, label=%s, total=%d, mode=%s%n",
            data.count, data.label, total, mode
        );

        data.mutate();

        System.out.printf(
            "after: count=%d, label=%s, total=%d, mode=%s%n",
            data.count, data.label, total, mode
        );
    }
}
~~~

This is a **complete Java program**, but it requires the native library compiled from C in the next step to run successfully. **mutate** is an instance native method, so the JNI entry point receives **JNIEnv \*** and **jobject self**. In `main`, the first active use of the class triggers the static initializer, calling `System.loadLibrary`; if the library is not found, the application reports `UnsatisfiedLinkError` and does not proceed to field operations.

### Step 2 — Compile Java and Generate the JNI Header

In the directory containing the Java file:

~~~bash
javac -h . FieldAccessDemo.java
~~~

The command produces at least **FieldAccessDemo.class** and **FieldAccessDemo.h**. Use the header generated by **javac -h**; do not guess how JNI mangles function names. For a class not in a package and a native method as above, the corresponding declaration is named **Java_FieldAccessDemo_mutate**.

### Step 3 — Create field_access_demo.c

~~~c
#include "FieldAccessDemo.h"

/*
 * Generated header defines the JNI name and signature.
 * self is the jobject of the instance calling mutate().
 */
JNIEXPORT void JNICALL
Java_FieldAccessDemo_mutate(JNIEnv *env, jobject self) {
    jclass cls = NULL;
    jfieldID countId = NULL;
    jfieldID labelId = NULL;
    jfieldID totalId = NULL;
    jfieldID modeId = NULL;

    jobject oldLabel = NULL;
    jobject oldMode = NULL;
    jstring nextLabel = NULL;
    jstring nextMode = NULL;

    jint oldCount = 0;
    jlong oldTotal = 0;

    /* Get the runtime class of self (FieldAccessDemo is final). */
    cls = (*env)->GetObjectClass(env, self);
    if (cls == NULL) {
        return; /* JVM has already thrown the corresponding exception. */
    }

    /* Look up IDs: instance fields use GetFieldID. */
    countId = (*env)->GetFieldID(env, cls, "count", "I");
    if (countId == NULL) goto cleanup;

    labelId = (*env)->GetFieldID(
        env, cls, "label", "Ljava/lang/String;"
    );
    if (labelId == NULL) goto cleanup;

    /* Look up IDs: static fields use GetStaticFieldID. */
    totalId = (*env)->GetStaticFieldID(env, cls, "total", "J");
    if (totalId == NULL) goto cleanup;

    modeId = (*env)->GetStaticFieldID(
        env, cls, "mode", "Ljava/lang/String;"
    );
    if (modeId == NULL) goto cleanup;

    /* Read primitives using the right type family and field kind. */
    oldCount = (*env)->GetIntField(env, self, countId);
    oldTotal = (*env)->GetStaticLongField(env, cls, totalId);

    /* Read reference fields: result is a local reference or NULL. */
    oldLabel = (*env)->GetObjectField(env, self, labelId);
    if ((*env)->ExceptionCheck(env)) goto cleanup;

    oldMode = (*env)->GetStaticObjectField(env, cls, modeId);
    if ((*env)->ExceptionCheck(env)) goto cleanup;

    /* Prepare all objects to write before modifying state. */
    nextLabel = (*env)->NewStringUTF(env, "from JNI");
    if (nextLabel == NULL) goto cleanup;

    nextMode = (*env)->NewStringUTF(env, "native");
    if (nextMode == NULL) goto cleanup;

    /* Write primitives and references using the right accessors. */
    (*env)->SetIntField(env, self, countId, oldCount + 5);
    (*env)->SetObjectField(env, self, labelId, nextLabel);

    (*env)->SetStaticLongField(env, cls, totalId, oldTotal + 25);
    (*env)->SetStaticObjectField(env, cls, modeId, nextMode);

cleanup:
    /*
     * DeleteLocalRef is a local reference cleanup operation,
     * which can be used while a Java exception is pending.
     * If field lookup / string creation fails, the original exception
     * continues propagating to Java when the native method returns.
     */
    if (nextMode != NULL) (*env)->DeleteLocalRef(env, nextMode);
    if (nextLabel != NULL) (*env)->DeleteLocalRef(env, nextLabel);
    if (oldMode != NULL) (*env)->DeleteLocalRef(env, oldMode);
    if (oldLabel != NULL) (*env)->DeleteLocalRef(env, oldLabel);
    (*env)->DeleteLocalRef(env, cls);
}
~~~

### Why Is the C Code Structured This Way?

1. **GetObjectClass(self)** creates a local `jclass` reference. Because the Java class is `final`, the class of `self` is `FieldAccessDemo`; there is no ambiguity from subclasses.
2. Two **GetFieldID** calls locate instance fields `count` and `label`; two **GetStaticFieldID** calls locate `total` and `mode`. Descriptors **I/J/Ljava/lang/String;** match the Java declarations.
3. Every lookup is checked for **NULL**. When a lookup fails, JNI usually has already set a pending exception (such as `NoSuchFieldError`). The **cleanup** branch cleans up references and returns to Java, without executing further getters/setters on an invalid ID.
4. **GetIntField** returns **jint**; **GetStaticLongField** returns **jlong**. Do not use C's `long` type to assume Java `long` width.
5. **GetObjectField** and **GetStaticObjectField** return local references. The code does not need to use the old string contents, yet intentionally performs both read operations to demonstrate the API and reference lifecycle.
6. Two **NewStringUTF** calls prepare the new values before updating fields. If memory is insufficient, JNI can set `OutOfMemoryError`; the code does not execute write operations after string creation fails.
7. The four setters choose the right types: **SetIntField**, **SetObjectField**, **SetStaticLongField**, **SetStaticObjectField**. **SetObjectField** takes a valid **jstring**, which is a Java reference compatible with a `String` field.
8. **DeleteLocalRef** does not delete the value stored in the Java field. The new reference remains held by the object/class field after the native method ends.

**Transaction limitation:** the example illustrates sequential operations, not a transaction. If multi-field updates require atomicity across threads or rollback on failure, design a synchronized Java API, create an immutable state object and replace it, or use an appropriate transaction mechanism. Four independent setter calls do not mean changing all four is atomic.

### Step 4 — Build the Native Library

Install a JDK with **JAVA_HOME** pointing to the JDK directory containing **include/jni.h**, along with a C compiler suitable for the running platform. Use the same CPU architecture/ABI as the JVM.

**Linux (GCC):**

~~~bash
gcc -std=c11 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  field_access_demo.c -o libfieldaccessdemo.so
~~~

**macOS (Clang):**

~~~bash
clang -std=c11 -fPIC -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  field_access_demo.c -o libfieldaccessdemo.dylib
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" field_access_demo.c /link /OUT:fieldaccessdemo.dll
~~~

The output names match how **System.loadLibrary("fieldaccessdemo")** maps the logical name on common platforms. The Windows command assumes the MSVC environment is already initialized; the Linux/macOS commands assume GCC/Clang and corresponding headers are ready.

### Step 5 — Run the Example

From the directory containing **FieldAccessDemo.class** and the built library:

~~~bash
java -Djava.library.path=. FieldAccessDemo
~~~

**Exact stdout on a successful configuration:**

~~~text
before: count=7, label=initial, total=100, mode=idle
after: count=12, label=from JNI, total=125, mode=native
~~~

If using a JDK with native access restrictions, running on the classpath may require enabling the unnamed module:

~~~bash
java --enable-native-access=ALL-UNNAMED -Djava.library.path=. FieldAccessDemo
~~~

Depending on the JDK, calling `System.loadLibrary` without declared permission may emit a warning to **stderr** or be denied by policy. Any stderr warning is not part of the sample stdout above. When running on the module path, prefer granting permission to the **specific module** rather than `ALL-UNNAMED`.

**If the program reports UnsatisfiedLinkError**, check the library name, build artifact, `JAVA_HOME`, JVM architecture, native dependencies, and `java.library.path`. This is a library loading/linking error, not proof that field descriptors are wrong. When the library loads successfully but uses a wrong field lookup, you may receive **NoSuchFieldError**.

### Using -Xcheck:jni to Detect Contract Violations Early

On a supported HotSpot/JVM:

~~~bash
java -Xcheck:jni -Djava.library.path=. FieldAccessDemo
~~~

Depending on the JDK's native access policy, combine with the native access enablement option if needed. **-Xcheck:jni** helps detect many invalid JNI usages such as passing a field ID of the wrong kind or an invalidated reference. It is a diagnostic and testing tool; it does not guarantee that JNI or C/C++ libraries are completely memory-safe.

## 8. Error Handling for Field Lookup and Pending Exceptions

The **GetFieldID / GetStaticFieldID** functions return **NULL** when lookup fails. Common causes include:

| Cause | Example | Common Consequence |
| --- | --- | --- |
| Wrong name | Java declares **count**, but C looks up **counts** | **NoSuchFieldError** |
| Wrong descriptor | Java declares **long total**, but C uses **"I"** | **NoSuchFieldError** |
| Wrong instance/static | Java declares **static int level**, C calls GetFieldID | **NoSuchFieldError** |
| Class initialization failed | The class's static initializer throws an error | **ExceptionInInitializerError** or another initialization error may occur |
| Out of memory | The JVM cannot complete the related operation | **OutOfMemoryError** may occur |
| Invalidated ID | Reusing a field ID after the defining class has been unloaded | JNI contract violation, may cause severe errors |

Check for **NULL** immediately after lookup:

~~~c
jfieldID id = (*env)->GetFieldID(env, cls, "count", "I");
if (id == NULL) {
    // An exception is pending; clean up necessary local references,
    // then return so Java handles the original error.
    return;
}
~~~

If you need to check an API that can set an exception without signaling error via `NULL`, use **ExceptionCheck**:

~~~c
if ((*env)->ExceptionCheck(env)) {
    // Only call JNI APIs allowed while an exception is pending,
    // such as DeleteLocalRef to clean up resources.
    return;
}
~~~

**Do not continue calling a series of regular JNI APIs when there is a pending exception.** According to JNI, after an error you must handle the exception or return control to Java; only a small set of APIs is allowed while an exception remains pending. Cleaning up local references is one of the allowed operations.

### ExceptionClear Is Not a "Fix"

**ExceptionClear** discards the pending exception state. Only call it when there is a clearly designed reason: translating to another exception, a valid fallback, or the error has been completely handled. If you clear **NoSuchFieldError** and continue accessing with a `NULL` `jfieldID`, you have not solved the root cause and may cause a crash.

### Do Not Bypass Java Invariants

JNI can access private fields via field IDs, but that does not make **bypassing setters/validation** safe. If a field has business constraints such as "non-negative balance" or "state change must emit an event", writing directly from C can violate invariants that Java setters normally protect. When business behavior matters, consider calling a public Java method via JNI instead of writing directly to the field.

## 9. Lifecycle of jfieldID, jclass, and jobject

Three kinds of values are easily confused:

| Value | Is it a Java reference? | Use DeleteLocalRef? | Can it be cached long-term? |
| --- | --- | --- | --- |
| Local **jobject** | Yes | Yes, when no longer needed | **No**, must create a global reference if needed after the native call |
| Local **jclass** | Yes | Yes | **No** as a local reference; use NewGlobalRef if needed to retain |
| **jfieldID** | **No** | **No** | Can be cached **while the class remains alive**; ID becomes invalid if the class is unloaded |

In a short native method, looking up the ID and using it directly is usually clear enough. If a field is accessed repeatedly and lookup is a significant cost, caching **jfieldID** is reasonable, but you must manage the **class loader lifecycle**.

A long-lived cache must avoid two problems:

1. **Class unloading:** a field ID can become invalid when the defining class is unloaded; the cache must not be used after that point. You can hold a global `jclass` reference to keep the class alive when the application genuinely requires it.
2. **Class loader leaks:** holding a global `jclass` reference permanently can prevent releasing a class loader in plugin/hot-reload environments. When a module is unloaded, global references and caches must be cleaned up according to the lifecycle.

Do not treat **jfieldID** as a field offset address that can be added or subtracted. It is an opaque token, only for use with the appropriate JNI functions.

## 10. Thread Safety and Data Consistency

**Type-safe JNI reading/writing** only satisfies the **type and instance/static contract**; it is not sufficient to guarantee correctness in a multithreaded environment.

C example:

~~~c
jint oldValue = (*env)->GetIntField(env, obj, countId);
(*env)->SetIntField(env, obj, countId, oldValue + 1);
~~~

This is a **two-step read-modify-write** operation, not an atomic increment. If two threads execute it concurrently, both may read the same old value and write the same new value, leading to a **lost update**.

To design properly:

- Clearly identify which fields are shared, including when both Java and native code access them.
- Use synchronization compatible with the Java Memory Model, or delegate complex operations to a Java method that already has locks/atomic classes.
- For state spanning multiple fields, avoid letting other threads observe partially updated state.
- Do not assume "calling a JNI setter is thread-safe" or "primitive fields make all related operations atomic".
- If a native library spawns its own thread and wants to interact with the JVM, that thread must be attached to the JVM and use **its own JNIEnv**; do not pass a `JNIEnv` from another thread.
- Do not retain a **local jobject reference** across native methods or pass it to another thread. When long-term retention is needed, consider a global reference and release it according to the lifecycle.

Distinguish **type correctness** from **synchronization correctness** and **business contract correctness**. All three must be satisfied if native code modifies state observed by Java.

## 11. Typical Mistakes to Avoid

| Mistake | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| Using **GetFieldID** for a static field | Looks up the wrong field kind | Use **GetStaticFieldID**, followed by an accessor containing `Static` |
| Using **GetStaticIntField** for a long field | Wrong type family, different descriptor | **GetStaticLongField**, descriptor **J** |
| Reading an int with **GetDoubleField** | JNI does not auto-cast across accessors | Use **GetIntField** then convert the `jint` if needed |
| Passing **jobject** instead of **jclass** to a static accessor | Wrong JNI API parameter | Obtain/store the appropriate `jclass` reference |
| Passing **jclass** instead of **jobject** to an instance accessor | Class is not the instance holding the field | Pass the specific Java object |
| Passing descriptor **"java.lang.String"** | Not a JVM field descriptor | **"Ljava/lang/String;"** |
| Forgetting **;** or using **.** in a reference descriptor | Lookup cannot find the field | Use JVM name with **/** and **;** |
| Continuing get/set when field ID is NULL | Pending exception, invalid ID | Check for error, clean up references, return |
| Calling **free(jstring)** | `jstring` is a Java reference | Use **DeleteLocalRef** for local references when appropriate |
| Closing a local reference immediately and continuing to use the handle | Handle is no longer valid | Use before deleting; hold a global ref if needed long-term |
| Using **SetObjectField** with a reference of a different field type | Violates Java type contract | Match the descriptor and actual object |
| Trying to modify **static final** via JNI | Violates immutability design, JIT risks | Do not modify `final`; use an API designed for updates |
| Keeping **jfieldID** after class unload | ID is no longer valid | Tie the cache to the class/class loader lifecycle |
| Writing a private field directly to bypass validation | Breaks business invariants | Call the appropriate Java method if state needs protection |
| Using GetFieldID to look up **array.length** | Array `length` cannot be looked up by ID | Use **GetArrayLength** |
| Treating a Get/Set pair as an atomic increment | Read-modify-write is not atomic | Use appropriate synchronization/atomic operations |

## 12. Checklist When Reviewing JNI Field-Access Code

- [ ] Determine whether the field is **instance** or **static** according to the Java declaration.
- [ ] Obtain a valid **jobject** or **jclass**; do not confuse classes from two different class loaders.
- [ ] Look up the field using the exact **name**, **descriptor**, and **GetFieldID / GetStaticFieldID**.
- [ ] Check that every lookup returns a **non-NULL jfieldID**, and do not continue with a pending exception.
- [ ] Choose the exact **Get<Type>Field / Set<Type>Field** or **Static** variant.
- [ ] Use the correct JNI types (**jint**, **jlong**, **jboolean**, **jobject**...), without assuming equivalent C type sizes.
- [ ] For object/reference fields, manage local/global references; do not `free` JNI pointers or retain local references beyond their lifecycle.
- [ ] Do not write directly to **final fields**, and do not bypass business invariants/validation.
- [ ] If multiple threads access the field, have a clear strategy for visibility, synchronization, and atomicity.
- [ ] If caching **jfieldID/jclass**, handle class loader unloading and global reference cleanup.
- [ ] Have tests for matching field types, wrong name/descriptor, initialization errors, pending exceptions, and concurrency.
- [ ] Run **-Xcheck:jni** in appropriate tests; smoke-test with the exact binary, JVM, and ABI that will be used in deployment.

## 13. Self-Check Questions

**Question 1.** Java has **static long total**. How must it be looked up and written from JNI?

**Answer:** Use **GetStaticFieldID(env, cls, "total", "J")**; if the ID is non-NULL, use **SetStaticLongField(env, cls, id, jlongValue)**. Do not use the instance `GetFieldID` or `SetLongField`.

**Question 2.** Java declares **private String label**. Why use GetObjectField instead of GetStringField?

**Answer:** `String` is a reference type. JNI uses the **ObjectField** family for all reference fields; there is no dedicated `GetStringField` family for `String` fields. The descriptor of `label` is **Ljava/lang/String;**.

**Question 3.** After reading an **int[] data** field with GetObjectField, you want to know its length. Can you use GetFieldID with the name **length**?

**Answer:** No. A Java array is retrieved using `GetObjectField` with descriptor **[I**; use **GetArrayLength** on a valid array reference to get the size.

**Question 4.** Why can't a **jfieldID** be passed to DeleteLocalRef?

**Answer:** `jfieldID` is a metadata identifier, not a Java object reference. `DeleteLocalRef` is only for JNI local references such as `jobject`/`jclass`/`jstring`.

**Question 5.** Two threads concurrently call GetIntField then SetIntField(value + 1). Will it always increment by two?

**Answer:** No. This is a multi-step read-modify-write, which can suffer lost updates. Synchronization or an appropriate atomic increment mechanism is required.

**Question 6.** In the example, why can **DeleteLocalRef(nextLabel)** be called after **SetObjectField(label, nextLabel)**?

**Answer:** The setter has already stored the Java reference into the field. `DeleteLocalRef` only deletes the temporary JNI reference; it does not delete the `String` object that the Java field holds.

**Question 7.** If GetFieldID fails to find a field, should you use ExceptionClear and continue with GetIntField?

**Answer:** No. The lookup returns `NULL` and a `NoSuchFieldError` is usually pending; you must handle the error or return to Java, not continue with an invalid ID. `ExceptionClear` is only meaningful when there is a genuinely valid recovery mechanism.

**Question 8.** Do you need to use a method descriptor like **(I)V** to look up the field **int count**?

**Answer:** No. The field descriptor for `int` is **I**. Parentheses belong in method descriptors, not for looking up fields.

## References

- [Oracle Java Native Interface Specification — JNI Functions: Accessing Fields of Objects / Accessing Static Fields](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/functions.html).
- [Oracle JNI Design Overview — Accessing Fields and Methods, Local/Global References, JNIEnv](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/design.html).
- [Oracle JNI Types and Data Structures](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/types.html).
- [Oracle javac — -h option for generating JNI headers](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html).
- [Oracle JNI Invocation API — attaching native threads to the JVM](https://docs.oracle.com/en/java/javase/25/docs/specs/jni/invocation.html).

**Key takeaway:** In JNI, reading/writing Java fields correctly always starts with the **right field kind (instance/static), right class, and right descriptor**. Then use the **right type-specific Get/Set accessor** with the appropriate **jobject or jclass** argument; check field ID errors, manage Java references, and ensure synchronization/business invariants. Calling the wrong function family can cause data corruption or severe JVM errors even when the C source still compiles.
