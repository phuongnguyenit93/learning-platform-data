# Overloading Native Methods in JNI: When to Use Short Symbol Names and When to Use Full Names?

## 1. Lesson Objectives and Problem Statement

In Java, **method overloading** allows multiple methods to share the same name, as long as their parameter type lists are different. This rule still applies to methods marked `native`. However, when the method body resides in a C/C++ library, the JVM must know which **native symbol (exported symbol)** executes the exact version that was selected.

For example:

```java
package demo.jni;

public final class NativeNames {
    private static native int scale(int n);
    private static native long scale(long n);
}
```

Both methods are named `scale` but accept different types, `int` and `long`. The fact that C can define a function named `scale` is not enough for the JVM to distinguish between the two overloads. JNI uses a name-encoding rule, generating a **short name** and, when needed, a **long name containing the parameter types**.

We need to accurately answer five questions:

1. Which overload does Java select when calling `scale(7)` or `scale(7L)`?
2. In what order does the JVM search for **short** and **long** symbol names?
3. Where does the `__I` or `__J` suffix come from?
4. If a `native` method has the same name as a regular Java method, is it mandatory to use the long name?
5. How do we use `javac -h` to avoid guessing JNI names and signatures manually?

**Distinguish two phases:** selecting the overload is a rule of the **Java language and bytecode**; finding the C/C++ function that implements that overload is **JNI linking**. They are related, but they are not the same operation.

## 2. Overloading in Java and JVM Descriptors

With the two declarations:

```java
static native int scale(int n);
static native long scale(long n);
```

- `scale(7)` selects the overload accepting `int` because the literal `7` has type `int`.
- `scale(7L)` selects the overload accepting `long` because the `L` suffix makes the literal have type `long`.
- `scale((long) 7)` also selects the overload accepting `long`.
- Java resolves overloads at **compile time** according to applicability rules, type conversion precedence, varargs, generics, etc. The bytecode of the call references a method with a specific name and *descriptor*; JNI does not guess the overload by inspecting values at runtime.

A **method descriptor** in JVM format has the form:

```text
(parameter_type_1 parameter_type_2 ...)return_type
```

There are no commas or spaces between type codes. Some basic codes:

| Java Type | JVM Code |
| --- | --- |
| `byte` | `B` |
| `char` | `C` |
| `double` | `D` |
| `float` | `F` |
| `int` | `I` |
| `long` | `J` |
| `short` | `S` |
| `boolean` | `Z` |
| `void` (return type only) | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

For the two `scale` methods above:

| Declaration | Full JVM method descriptor | **Parameter** descriptor part |
| --- | --- | --- |
| `int scale(int n)` | `(I)I` | `I` |
| `long scale(long n)` | `(J)J` | `J` |

**Key point:** the JNI long name only encodes the **parameter list** (the part inside the parentheses), **not the return type**. Even though the full method descriptor includes the return type, the return type is not included in the JNI function name suffix. This aligns with Java: you cannot create two overloads that differ **only by return type**.

## 3. How Does JNI Generate Short and Long Names?

When using **name-based JNI linking**, the common name forms are:

```text
Short name:
Java_<escaped_class_name>_<escaped_method_name>

Long name:
Java_<escaped_class_name>_<escaped_method_name>__<escaped_parameters>
                                              ^^
                                       two underscores
```

For `demo.jni.NativeNames`, the internal class name is `demo/jni/NativeNames`. The slash character `/` becomes an underscore `_` when JNI-encoded, so the prefix is:

```text
Java_demo_jni_NativeNames_
```

The corresponding symbols:

| Java Method | Short name (without parameters) | Long name (with parameters) |
| --- | --- | --- |
| `int scale(int)` | `Java_demo_jni_NativeNames_scale` | `Java_demo_jni_NativeNames_scale__I` |
| `long scale(long)` | `Java_demo_jni_NativeNames_scale` | `Java_demo_jni_NativeNames_scale__J` |
| `int sum(int,int)` | `Java_demo_jni_NativeNames_sum` | `Java_demo_jni_NativeNames_sum__II` |
| `int parse(String)` | `Java_demo_jni_NativeNames_parse` | `Java_demo_jni_NativeNames_parse__Ljava_lang_String_2` |

**The short names of both `scale` methods are identical.** If both are `native` methods, we need two distinct long-name symbols to implement both properly.

In the long-name symbol, the string `__I` is parsed as `__` (the long-name separator) + `I` (Java `int` parameter); similarly, `__J` is the overload with a `long` parameter. `__II` means **two `int` parameters**, completely unrelated to the return type.

### JVM Symbol Lookup Order

The JNI Specification clearly states the name lookup order when the JVM links a native call:

1. Try looking up the **short name**, without a signature suffix.
2. Only if the short name is not found, try the **long name** containing the parameter signature.

```text
Java calls scale(7)
       │ selected overload: scale(int)
       ▼
JVM tries Java_demo_jni_NativeNames_scale
       │ if not found
       ▼
JVM tries Java_demo_jni_NativeNames_scale__I
       │ if found
       ▼
Calls the right C function taking jint
```

Because the **short name is tried first**, do not export a shared short-name symbol for `native` overloads that have different ABIs. For example, if you accidentally export `Java_demo_jni_NativeNames_scale` for both, the JVM might link one overload to a C function that does not accept the right parameter type: unreliable behavior, ranging from wrong results to native errors/crashes. When there are multiple `native` methods with the same name, generate a **separate long name for each overload** using the auto-generated header.

It is also necessary to separate: the library file name in `System.loadLibrary("native_names")` is the **name of the library containing the functions**, whereas `Java_demo_jni_NativeNames_scale__I` is the **exported function name inside the library**. These two names solve two different problems.

## 4. Special Case: Overloading with Only One Native Method

Consider a class with:

```java
private static native int size(int n);
private static int size(String text) {
    return text.length();
}
```

At the Java level, these are still **two overloads of `size`**. However, only one overload has a C body; `size(String)` is implemented entirely in Java.

In this case, the short name `Java_demo_jni_NativeNames_size` is **sufficient to link the native method**. It is not mandatory to use `Java_demo_jni_NativeNames_size__I`. According to the JNI specification, the long name is required when **two or more `native` methods in the same class have the same name**; a regular Java overload does not produce a JNI function to cause ambiguity.

Comparison:

| Declaration group | Recommended native symbol |
| --- | --- |
| Only `native void ping()` | `Java_demo_jni_NativeNames_ping` |
| `native int size(int)` + Java `int size(String)` | `Java_demo_jni_NativeNames_size` |
| `native int scale(int)` + `native long scale(long)` | `Java_demo_jni_NativeNames_scale__I` and `Java_demo_jni_NativeNames_scale__J` |

**Practical rule:** if you want to know exactly what the compiler expects, use `javac -h` and take the name/prototype from the header; there is no need to guess manually.

## 5. Escaping/Mangling Rules When Names or Parameters Have Special Characters

JNI does not directly concatenate Java names containing dots, underscores, or object types into C symbols. In the JNI Specification:

| Original character in internal name / descriptor | JNI escape result |
| --- | --- |
| ASCII characters `A–Z`, `a–z`, `0–9` | Kept as-is |
| `/` (package separator in internal name) | `_` |
| `_` (literal underscore in Java name) | `_1` |
| `;` (end of object type in descriptor) | `_2` |
| `[` (start of array type) | `_3` |
| Other UTF-16 code units | `_0xxxx`, four lowercase hex digits |

Illustrative examples:

- Class `com.example.My_Class` has internal name `com/example/My_Class`: the class part in the symbol is `com_example_My_1Class`, because the original underscore must be escaped as `_1`.
- Java method `run_task()`: the method name part is `run_1task`.
- Type `String`: descriptor `Ljava/lang/String;` → escaped string `Ljava_lang_String_2`.
- Type `int[]`: descriptor `[I` → `_3I`.
- Type `String[]`: descriptor `[Ljava/lang/String;` → `_3Ljava_lang_String_2`.

From that, if class `demo.jni.NativeNames` has two methods `native void process(int[])` and `native void process(String[])`, the long names will be respectively:

```text
Java_demo_jni_NativeNames_process___3I
Java_demo_jni_NativeNames_process___3Ljava_lang_String_2
```

In `process___3I`, there are **three consecutive underscores** after the method name: `__` for the long-name form, then `_3` to represent the array opening bracket `[`. This is not a typo.

The `void` return type in the example does not add a `V` at the end of the symbol. However, the full descriptors for Java/JVM to identify the methods are still `([I)V` and `([Ljava/lang/String;)V`, respectively.

For Unicode characters, JNI encodes by **UTF-16 code unit**; characters outside the BMP using a surrogate pair are escaped into two parts. Therefore, it is even more advisable not to type long symbols manually when there are packages, nested classes, Unicode names, or complex array types. `javac -h` eliminates most manual naming errors.

## 6. Complete Buildable JNI Example Using Java 17+ and C

The example below simultaneously demonstrates:

- Two `native` overloads of `scale` must have **two separate long names**.
- A `native size(int)` method overloaded by `size(String)` **written in Java** can use the **short name**.
- Java selects the overload from the argument type; JNI finds the right C implementation function by symbol name.
- The `.h` file generated by `javac -h` is the authoritative source for prototypes.

### Step 1 — Create `src/demo/jni/NativeNames.java`

```java
package demo.jni;

public final class NativeNames {
    static {
        System.loadLibrary("native_names");
    }

    private static native int scale(int n);
    private static native long scale(long n);

    private static native int size(int n);

    private static int size(String text) {
        return text.length();
    }

    public static void main(String[] args) {
        System.out.println("int: " + scale(7));
        System.out.println("long: " + scale(7L));
        System.out.println("native size: " + size(5));
        System.out.println("java size: " + size("abc"));
    }
}
```

Because `7` is `int` and `7L` is `long`, the compiler binds the two calls to two different descriptors. Because the argument `"abc"` is `String`, the call `size("abc")` **does not cross into native code**.

### Step 2 — Compile Java and Generate the JNI Header

From the project root directory, create the output directories (e.g., Linux/macOS shell):

```bash
mkdir -p build/classes build/include build/native

javac -h build/include \
  -d build/classes \
  src/demo/jni/NativeNames.java
```

- `-d build/classes` is where the class file (`demo/jni/NativeNames.class`) is stored.
- `-h build/include` instructs `javac` to generate the JNI header for `native` methods.
- The header is named `build/include/demo_jni_NativeNames.h` (this is the naming convention for non-modular classes in the example).
- `javac` does not create a C library or native executable yet; it generates bytecode and a C header.

In the header, the meaningful prototype section looks like this (omitting auto-generated comments/header guards):

```c
#include <jni.h>

JNIEXPORT jint JNICALL Java_demo_jni_NativeNames_scale__I
  (JNIEnv *, jclass, jint);

JNIEXPORT jlong JNICALL Java_demo_jni_NativeNames_scale__J
  (JNIEnv *, jclass, jlong);

JNIEXPORT jint JNICALL Java_demo_jni_NativeNames_size
  (JNIEnv *, jclass, jint);
```

Important observation: `scale(int)` carries the `__I` suffix, `scale(long)` carries the `__J` suffix, while `size(int)` only has the **short** symbol. There is no JNI prototype for `size(String)` because it is implemented in Java.

**Verified this rule with `javac -h` on JDK 24:** the header generated the exact three prototypes above. On JDK 17+ with the same declarations, run `javac -h` to verify against your actual JDK version.

### Step 3 — C Implementation in `NativeNames.c`

```c
#include <jni.h>
#include "demo_jni_NativeNames.h"

JNIEXPORT jint JNICALL Java_demo_jni_NativeNames_scale__I(
        JNIEnv *env, jclass clazz, jint n) {
    (void) env;
    (void) clazz;
    return n * 2;
}

JNIEXPORT jlong JNICALL Java_demo_jni_NativeNames_scale__J(
        JNIEnv *env, jclass clazz, jlong n) {
    (void) env;
    (void) clazz;
    return n * 3;
}

JNIEXPORT jint JNICALL Java_demo_jni_NativeNames_size(
        JNIEnv *env, jclass clazz, jint n) {
    (void) env;
    (void) clazz;
    return n + 1;
}
```

Two points to cross-check against the header:

1. `JNIEXPORT` marks the function to be exported from the library in a compiler/platform-appropriate way; `JNICALL` uses the calling convention required by JNI. Keep these macros intact, especially when switching platforms.
2. The first two parameters are `JNIEnv *env` and `jclass clazz` because all three Java methods are `static native`. For **instance native** methods (without `static`), the second parameter is `jobject obj` corresponding to the `this` object. After that come the Java parameters converted to JNI types (`int → jint`, `long → jlong`).

If writing the native part in **C++**, you must ensure the JNI functions have C linkage (typically using `extern "C"`); if you let the C++ compiler mangle symbols using C++ rules, the JVM may fail to find the `Java_...` symbol even if the function name in source looks right. The header generated by `javac -h` already wraps the prototypes in an `extern "C"` block when compiled as C++.

### Step 4 — Build the Library on Linux

Requirements: JDK 17+ and GCC, with the `JAVA_HOME` environment variable pointing to the JDK directory containing `include/jni.h`.

```bash
gcc -O2 -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/include \
  -o build/native/libnative_names.so \
  NativeNames.c
```

Load and run the Java program:

```bash
java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.NativeNames
```

**Exact stdout when compilation, loading, and linking succeed:**

```text
int: 14
long: 21
native size: 6
java size: 3
```

Explanation:

- `scale(7)` goes to `Java_demo_jni_NativeNames_scale__I` and computes `7 * 2 = 14`.
- `scale(7L)` goes to `Java_demo_jni_NativeNames_scale__J` and computes `7 * 3 = 21`.
- `size(5)` uses the short symbol `Java_demo_jni_NativeNames_size`, returning `5 + 1 = 6`.
- `size("abc")` executes the Java body, returning `3` without calling JNI.

### Compiling on macOS or Windows

The Java/C code above does not depend on Linux; only the library build command and file names differ.

**macOS** (JDK and Apple Clang; after creating `build/classes`, `build/include`, `build/native` and running `javac -h` as above):

```bash
clang -O2 -dynamiclib \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/include \
  -o build/native/libnative_names.dylib \
  NativeNames.c

java -Djava.library.path=build/native \
  -cp build/classes \
  demo.jni.NativeNames
```

**Windows** (JDK, Visual Studio C compiler; run from *Developer Command Prompt* with `cl` and `JAVA_HOME` configured):

```bat
mkdir build\classes
mkdir build\include
mkdir build\native

javac -h build\include -d build\classes src\demo\jni\NativeNames.java

cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\include" NativeNames.c /Febuild\native\native_names.dll

java -Djava.library.path=build\native -cp build\classes demo.jni.NativeNames
```

The `mkdir` commands may report that the directory already exists when re-run; this does not affect the source contents. On all three platforms, you must use a JDK and native compiler with **matching architectures** (e.g., x64 with x64). `System.loadLibrary("native_names")` automatically maps the logical name to the platform-specific library filename.

Note the distinction between **stdout** and **stderr**: newer JDKs may print native access policy warnings on stderr. If the runtime requires enabling native access for a program on the classpath, use the option appropriate for your JDK version, such as `--enable-native-access=ALL-UNNAMED` when running on a supported JDK; warnings are not part of the four stdout lines above.

## 7. Long Names with Object and Array Parameters

In real projects, overloads often involve `String`, classes in packages, or arrays. Take a standalone example of symbol names (not a complete program):

```java
package demo.jni;

public class ReferenceOverloads {
    public native int find(int id, String text);
    public native int find(int id, Object value);
    public native void accept(int[] items);
    public native void accept(String[] items);
}
```

Breakdown of descriptors and symbol names:

| Declaration | Full descriptor | Parameters only for encoding | Long symbol name |
| --- | --- | --- | --- |
| `find(int, String)` | `(ILjava/lang/String;)I` | `ILjava/lang/String;` | `Java_demo_jni_ReferenceOverloads_find__ILjava_lang_String_2` |
| `find(int, Object)` | `(ILjava/lang/Object;)I` | `ILjava/lang/Object;` | `Java_demo_jni_ReferenceOverloads_find__ILjava_lang_Object_2` |
| `accept(int[])` | `([I)V` | `[I` | `Java_demo_jni_ReferenceOverloads_accept___3I` |
| `accept(String[])` | `([Ljava/lang/String;)V` | `[Ljava/lang/String;` | `Java_demo_jni_ReferenceOverloads_accept___3Ljava_lang_String_2` |

All four methods in the table are *instance native*, so the C prototype takes `jobject` as the second parameter (unlike `jclass` in the `static` example).

Do not confuse the **JNI symbol suffix** with the **full JVM descriptor**:

- The JNI symbol `...find__ILjava_lang_String_2` uses **escaped parameters**, without parentheses `()` and without the return type `I`.
- JNI APIs such as `GetMethodID` or `RegisterNatives` take the **full descriptor**, for example `"(ILjava/lang/String;)I"`, including parentheses and return type.
- Type strings like `Ljava/lang/String;` use **slashes `/`**, not dots as in Java source names.

## 8. Alternative: Registering Mappings with RegisterNatives

JNI also provides the `RegisterNatives` API. Instead of having the JVM look up C symbols starting with `Java_...`, native code can **explicitly register** each Java method by **name and full descriptor**, and bind it to the corresponding C function pointer.

Illustrating a partial registration setup (this is only an excerpt, not a standalone runnable program; you need to declare the C functions, obtain `jclass`, call registration at the appropriate time, and handle errors):

```c
static JNINativeMethod methods[] = {
    {"scale", "(I)I", (void *) nativeScaleInt},
    {"scale", "(J)J", (void *) nativeScaleLong}
};

/* env: JNIEnv*, targetClass: already-located jclass */
jint result = (*env)->RegisterNatives(
    env, targetClass, methods, 2);
```

Here:

- `"scale"` is the **Java method name**, not the C symbol `Java_demo_jni_NativeNames_scale__I`.
- `"(I)I"` and `"(J)J"` are **full descriptors**, including the return type, which helps register the exact overload.
- `nativeScaleInt` and `nativeScaleLong` can have any C names you choose, as long as the pointers point to functions with the **correct JNI ABI/signature**.
- You must check the return value and exceptions. Registering wrong types/pointers can also cause errors or crashes. `RegisterNatives` is a different mechanism, not evidence that the short/long symbol rules have changed.

Using `javac -h` and name-based linking suits simple examples; explicit registration is useful when a framework/native runtime wants to manage the method mapping table. With standard Java 17+, both are JNI techniques that require careful maintenance.

## 9. Diagnosing Native Method Overloading Errors

### 9.1. Library Not Loaded ≠ Symbol Mismatch

`System.loadLibrary("native_names")` can fail because the **main native library or its dependency cannot be found** (for example `libnative_names.so`, `native_names.dll`), in which case the error occurs at the library-loading step.

Conversely, if the library loads successfully but the JVM **cannot find the corresponding JNI function** when calling `scale(int)`, Java may throw:

```text
java.lang.UnsatisfiedLinkError: 'int demo.jni.NativeNames.scale(int)'
```

The actual message depends on the JDK and runtime; the sample above describes the missing **method binding**, not the entire stack trace. Use the class name + method name + descriptor to identify the exact overload that failed.

### 9.2. Checking with `javac -h` and Symbol Inspection Tools

1. Regenerate the header from the current Java source version: `javac -h build/include -d build/classes ...`.
2. Cross-check the `Java_...` name and the entire C prototype against the header, including `JNIEXPORT`, `JNICALL`, `JNIEnv*`, `jclass/jobject`, and JNI types.
3. Inspect the actual exported symbols from the library:

```bash
# Linux (ELF): view exported symbols, verify full names
nm -D --defined-only build/native/libnative_names.so | grep Java_demo_jni_NativeNames

# Linux: readelf can also be used
readelf -Ws build/native/libnative_names.so | grep Java_demo_jni_NativeNames
```

```bash
# macOS (Mach-O): symbols may display a leading '_'
nm -gU build/native/libnative_names.dylib | grep Java_demo_jni_NativeNames
```

```bat
rem Windows: in Visual Studio Developer Command Prompt
dumpbin /EXPORTS build\native\native_names.dll
```

4. If you see `Java_demo_jni_NativeNames_scale` without `...scale__I` and `...scale__J`, do not treat that as a valid implementation for **two native overloads**.
5. If the library is written in C++, check whether it exports **C linkage**. If you change the package, class name, method name, or parameter types, **regenerate the header and rebuild the library**.

### 9.3. Errors and Troubleshooting Guide

| Symptom | Possible Cause | Check/Fix |
| --- | --- | --- |
| `no native_names in java.library.path` | JVM could not find the main library | Logical name, `.so`/`.dll`/`.dylib` file, `java.library.path` |
| `scale(int)` fails but `scale(long)` works | Missing or wrong `__I` symbol | Compare header and exported symbols; rebuild the function for `int` |
| `scale(long)` fails but `scale(int)` works | Missing or wrong `__J` symbol | Compare header and exported symbols; rebuild the function for `long` |
| Symbol exists but wrong parameter types or call crashes | Wrong C function prototype/ABI, or shared short symbol | Use JNI prototypes from header, remove ambiguous short name |
| Symbol has strange long name like `___3I` | Array is escaped as `_3I` | Read method descriptor `([I)...` and escaping rules |
| Renamed package/method and call fails | C symbol still has old class/method name | Generate new header, update C code, and recompile |
| C++ exports `_Z...` style names | C++ compiler mangling instead of JNI C linkage | Declare with `extern "C"` and JNI macros |
| Symbol name is right but loading still fails | Missing dependent library, wrong OS/architecture, or native access permission | Check loader, platform, and JDK policy |

**Specifically:** do not try to fix a `scale(int)` error by renaming the Java method to eliminate overloading if overloading is the required API. The long-name rule was designed to solve this exact case.

## 10. Self-Check Exercises

**Exercise 1.** Given two methods `native int combine(int, int)` and `native int combine(int, long)` in class `demo.jni.NativeNames`, state their long names.

Answer: the parameters have descriptors `II` and `IJ` respectively, so the symbols are:

```text
Java_demo_jni_NativeNames_combine__II
Java_demo_jni_NativeNames_combine__IJ
```

**Exercise 2.** A class has `native int count(int[])` and `native int count(String[])`. Why are there three underscores right before `3`?

Answer: `__` separates the long-name part, and `_3` is how the `[` character is escaped. The corresponding long names are `...count___3I` and `...count___3Ljava_lang_String_2`.

**Exercise 3.** A class has `native double calc(double)` and `int calc(String)` (implemented in Java). Is it mandatory to export `Java_..._calc__D`?

Answer: **No**. Only one overload is `native`, so the short name `Java_..._calc` is sufficient; the C type/prototype just needs to match `calc(double)`.

**Exercise 4.** A library exports both `Java_demo_jni_NativeNames_scale` (short name) and `Java_demo_jni_NativeNames_scale__I`/`__J` (long names). Can you guarantee the JVM will always pick the right long name?

Answer: **No**. According to the JNI Specification, the JVM **tries the short name first**, so accidentally exporting the short name is risky. When there are multiple `native` methods with the same name, only export the overload-specific long names.

**Exercise 5.** Does `RegisterNatives` distinguish overloads by the strings `"__I"` and `"__J"` or by the full descriptor?

Answer: By the **method name together with the full descriptor**, for example `"scale" + "(I)I"` and `"scale" + "(J)J"`. The `Java_...__I` symbol-generation rule does not need to be used when functions are explicitly registered.

## 11. Key Takeaways to Apply

- Overloading is selected by the **Java compiler** based on parameter types; the **JNI linker** needs to find the C/C++ function for the selected overload.
- **Short name**: `Java_<class>_<method>`; **long name**: append `__<escaped parameter descriptor>`.
- The JVM tries the **short name first**, and only then the **long name** when looking up symbols by JNI rules.
- If **two or more overloads are `native`**, generate **separate long names**; if only one overload is `native`, the short name is sufficient even if regular Java overloads exist.
- The return type is **not included in the JNI suffix**, but it is included in the full descriptor for `GetMethodID`/`RegisterNatives`.
- `_`, `/`, `;`, `[`, and Unicode characters have specific escaping rules; **`javac -h` is the safest way** to get exact function names and prototypes.
- Failure to find the **library** and failure to find the **JNI method** must be diagnosed separately.

## Official References

- [JNI Specification (Java 17), Design Overview: Resolving Native Method Names](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/design.html#resolving-native-method-names)
- [JNI Specification (Java 24), Design Overview: short/long symbol resolution, escaping and native access](https://docs.oracle.com/en/java/javase/24/docs/specs/jni/design.html)
- [Java Virtual Machine Specification, Method Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3.3)
- [`javac`, `-h` option for generating native headers](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [JNI Functions: RegisterNatives](https://docs.oracle.com/en/java/javase/17/docs/specs/jni/functions.html#registering-native-methods)
