# Binary names, slashes, and JNI function naming rules

## 1. Why does a Java class have multiple ways to write its name?

When working with the Java Native Interface (JNI), the same class can appear in several representations:

- **Java type name in source code**: `edu.demo.jni.NativeNames`.
- **Binary name** of the class: `edu.demo.jni.NativeNames`; for member classes, the binary name usually contains `$`.
- **Internal form** in the JVM: `edu/demo/jni/NativeNames`, using forward slashes `/` instead of dots separating packages.
- **Descriptor (type descriptor)**: `Ledu/demo/jni/NativeNames;`; a method descriptor also includes the parameter list and return type.
- **Exported C function name following JNI rules**: for example, `Java_edu_demo_jni_NativeNames_sum_1value`; this is a mangled *symbol*, not a class name or a path.
- **Native library name**: such as `libnative_names.so`, `native_names.dll`, or `libnative_names.dylib`; this filename belongs to the operating system's library loading mechanism.

These representations are related, but **cannot be interchanged arbitrarily**. The `/` in `edu/demo/jni/NativeNames` is a JVM internal name convention, not a requirement to choose Linux or macOS. JNI function names use `_` according to an **exact escape table**, so you cannot simply replace every dot with an underscore.

Goal of this lesson: distinguish binary/internal names, understand `/` in descriptors and JNI APIs, derive short/long JNI names yourself, explain the `_1`/`_2`/`_3`/`_0xxxx` rules, and verify with `javac -h` on Java 17+.

## 2. Source code name, binary name, and internal form

### 2.1. Top-level class with a package

Given the declaration:

~~~java
package edu.demo.jni;

public class NativeNames {
}
~~~

we have:

| Context | Name string | Meaning |
|---|---|---|
| Java code / `Class.getName()` | `edu.demo.jni.NativeNames` | Binary name of a regular class, with dots separating packages. |
| JVM internal form | `edu/demo/jni/NativeNames` | `/` separates package/class components in the class file structure. |
| Field descriptor of an object type | `Ledu/demo/jni/NativeNames;` | `L` begins a class/interface reference type; `;` ends it. |
| Source filename in a common layout | `src/edu/demo/jni/NativeNames.java` | Filesystem path, subject to shell and OS syntax. |
| Class file in a common layout | `build/classes/edu/demo/jni/NativeNames.class` | Build file; on Windows the filesystem separator can be `\`. |

Note: packages in Java are written with dots. When converting to internal form, the dots **separating packages** are replaced with `/`. This is a JVM/JNI rule, **not** a platform-dependent filesystem separator conversion. In Java literals, write `"edu/demo/jni/NativeNames"` when a JNI API requires an internal name, even when running on Windows.

A binary name is the name of a **class**; “binary” here does not mean `.dll` or `.so`. Do not confuse it with *binary filename* or with the native library name.

### 2.2. Member classes, nested classes, and the `$` character

Consider the following code (illustrating names, not yet involving native methods):

~~~java
package edu.demo.jni;

public class Outer {
    public static class Inner {
    }
}
~~~

Name of `Inner`:

| Representation | Value |
|---|---|
| Written in Java source | `edu.demo.jni.Outer.Inner` |
| Binary name / `Outer.Inner.class.getName()` | `edu.demo.jni.Outer$Inner` |
| Internal form | `edu/demo/jni/Outer$Inner` |
| Descriptor | `Ledu/demo/jni/Outer$Inner;` |
| Class part after JNI escaping | `edu_demo_jni_Outer_00024Inner` |

Common pitfall: Java source uses `Outer.Inner`, but the **binary name of a member class** has `Outer$Inner`. When mangling a JNI function name, the `$` character (U+0024) cannot be kept as-is like ASCII letters/digits, so it becomes `_00024`. Do not manually replace `$` with `_`. For local/anonymous classes, the binary name may contain numbered parts; you should always obtain the name from the actual class rather than guessing from source.

### 2.3. Array names are not like regular classes

The JVM describes arrays with a leading `[`:

| Java type | JVM type descriptor |
|---|---|
| `int[]` | `[I` |
| `long[][]` | `[[J` |
| `String[]` | `[Ljava/lang/String;` |
| `edu.demo.jni.NativeNames[][]` | `[[Ledu/demo/jni/NativeNames;` |

There is a small but important difference: `String[].class.getName()` returns the binary-name-style string `[Ljava.lang.String;` with **dots** in the class name part; the JVM descriptor and the `FindClass` argument for object arrays use **slashes**, such as `[Ljava/lang/String;`. Do not confuse the output of `Class.getName()` for an array with the bytecode descriptor that must be written for JNI.

## 3. The `/` in JVM signatures and JNI calls

### 3.1. Field descriptor rules

Basic JVM type descriptor characters:

| Java type | Descriptor | Corresponding JNI C type (when used as parameter/value) |
|---|---|---|
| `boolean` | `Z` | `jboolean` |
| `byte` | `B` | `jbyte` |
| `char` | `C` | `jchar` |
| `short` | `S` | `jshort` |
| `int` | `I` | `jint` |
| `long` | `J` | `jlong` |
| `float` | `F` | `jfloat` |
| `double` | `D` | `jdouble` |
| `void` | `V` | `void` (method return type position only) |
| `java.lang.String` | `Ljava/lang/String;` | `jstring` |
| `int[]` | `[I` | `jintArray` |
| `String[]` | `[Ljava/lang/String;` | `jobjectArray` |

Descriptor formation rule: a class/interface has the form `L<internal-name>;`; each array dimension prepends one `[` before the element's descriptor. For example, Java `String[][]` has descriptor `[[Ljava/lang/String;`. The slash `/` is part of the internal name; `L`, `;`, and `[` are descriptor syntax, not decorative characters.

### 3.2. Method descriptors contain both inputs and output

Example declaration:

~~~java
static native long calculate(int count, String[] names);
~~~

The method descriptor is:

~~~text
(I[Ljava/lang/String;)J
~~~

Breakdown:

- `(` and `)` enclose the **parameter descriptors in order**.
- `I` is `int count`.
- `[Ljava/lang/String;` is `String[] names`.
- `J` after `)` is the return type `long`.

**Separate two concepts:** the full JVM descriptor **includes the return type**, whereas the suffix of a *long JNI name* only takes the **parameter descriptors**, omitting `(`, `)`, and the return type. Therefore, the example above uses the parameter string `I[Ljava/lang/String;` to encode the JNI suffix, not the entire string `(I[Ljava/lang/String;)J`.

Generics mostly undergo **type erasure** in regular JVM descriptors: for example, a `java.util.List<String>` parameter has the object descriptor `Ljava/util/List;`, without embedding `<String>` in the JNI method descriptor.

### 3.3. Which JNI APIs use internal form?

On the C side (the snippet below is **an illustration inside a JNI function**; a valid `JNIEnv *env` is required):

~~~c
jclass cls = (*env)->FindClass(env, "edu/demo/jni/NativeNames");
~~~

`FindClass` takes the class name in internal form (or the corresponding array descriptor), so it uses `/`. For a `String[]` array, the form is:

~~~c
jclass arrayCls = (*env)->FindClass(env, "[Ljava/lang/String;");
~~~

Both examples must check for a `NULL` result and any pending Java exception before continuing. `FindClass` is also subject to the class loader context; a correct name does not guarantee the class is always visible in every loader.

When looking up a method/field via JNI, **the Java name and the descriptor are two separate arguments**:

~~~c
/* Illustration: only call after having a valid jclass cls. */
jmethodID id = (*env)->GetStaticMethodID(
    env, cls, "size", "([I)I"
);
~~~

`"size"` is the **original** method name, not the C name `Java_...`; `"([I)I"` is the exact descriptor for `static int size(int[])`. `GetStaticMethodID` looks up a static method; for an instance method, use `GetMethodID`. When lookup fails, JNI may leave a Java exception that needs to be handled.

## 4. How to form C function names following JNI rules (name mangling)

### 4.1. Formula

For **name-based JNI linking**, the rule has the form:

~~~text
Short name:
Java_<escaped-internal-class-name>_<escaped-method-name>

Long name:
Java_<escaped-internal-class-name>_<escaped-method-name>__<escaped-parameter-descriptor>
~~~

Steps:

1. Take the **binary name** of the class that actually **declares the native method**.
2. Convert it to **internal form** (package-separating `.` → `/`, keeping `$` of nested classes as-is).
3. **Escape** the internal class name according to the JNI table.
4. Escape the Java method name (do not arbitrarily alter `_`).
5. If it is necessary to distinguish overloaded native methods: append exactly **two underscores** `__`, then escape the descriptor string **of the parameters** (without parentheses or return type).

A long name is not how a normal method descriptor is written, but rather a C symbol name containing an **encoded** version of the parameter descriptors.

### 4.2. Official escape table

| Original character | Part written in JNI C name | Example |
|---|---|---|
| ASCII letters/digits `A–Z`, `a–z`, `0–9` | Kept as-is | `size` → `size` |
| Slash `/` | `_` | `java/lang` → `java_lang` |
| Underscore `_` | `_1` | `sum_value` → `sum_1value` |
| Semicolon `;` | `_2` | `Ljava/lang/String;` → `Ljava_lang_String_2` |
| Opening square bracket `[` | `_3` | `[I` → `_3I` |
| Other UTF-16 characters | `_0xxxx`, four lowercase hex digits | `$` (U+0024) → `_00024`; `é` (U+00E9) → `_000e9` |

The notation `_0xxxx` here means `_`, the digit `0`, followed by **four hexadecimal digits** representing one *UTF-16 code unit*. For characters outside the Basic Multilingual Plane (having a surrogate pair), each surrogate unit is encoded separately; they are not combined into a single code point with more than four digits. Certain additional JVM rules ensure valid mapping for class names allowed in class files; the most reliable approach is to let `javac -h` generate the header.

**Why must `_` become `_1`?** If kept as-is, an `_` in a method name could be confused with a package/class/method separator or the start of an overload suffix. For example, `sum_value` must become `sum_1value`; writing `sum_value` in the C name could point to a different Java name.

**Why do two underscores `__` sometimes become three `___`?** The long name suffix begins with `__`, while an array descriptor `[I` when escaped begins with `_3I`. Concatenated directly: `__` + `_3I` = `___3I`. This is the correct result, not an accidental extra underscore.

### 4.3. Short name and long name when overloading

When resolving a `native` method by symbol name, the JVM looks for the **short name first**, and if not found, then looks for the **long name** (per the JNI specification). Therefore:

- A native method that is not overloaded by another native method can usually use the **short name**.
- Two or more **native** methods in the same class with the same name but different parameter types need **distinct long names**, so each method points to the right C code.
- If it only shares a name with a **non-native Java** method, the native method does not necessarily have to use a long name, because that Java method does not need a symbol in the native library.
- You should not export a “shared” short symbol for multiple native overloads with different C signatures; since the short name is tried first, it can lead to unintended binding and dangerous ABI errors.

Although knowing the rules is essential, you should **generate the header with `javac -h` whenever you declare or change a native method**, and include that header in your C/C++ file.

## 5. Examples of deriving JNI names from a class and overloads

Suppose a class in package `edu.demo.jni`:

~~~java
package edu.demo.jni;

public final class NativeNames {
    public static native int sum_value(int a, int b);
    public static native int size(int[] values);
    public static native int size(String text);
}
~~~

This is a **declaration snippet for analysis**; a complete runnable program will have `static` library loading and `main` in the hands-on section below.

Internal class name: `edu/demo/jni/NativeNames`. After escaping: `edu_demo_jni_NativeNames`.

| Java method | JVM descriptor | **Parameter** descriptor | JNI C function name |
|---|---|---|---|
| `sum_value(int,int)` | `(II)I` | `II` | `Java_edu_demo_jni_NativeNames_sum_1value` |
| `size(int[])` | `([I)I` | `[I` | `Java_edu_demo_jni_NativeNames_size___3I` |
| `size(String)` | `(Ljava/lang/String;)I` | `Ljava/lang/String;` | `Java_edu_demo_jni_NativeNames_size__Ljava_lang_String_2` |

Explanation of the results:

- `sum_value` is not overloaded: the short name suffices, and the `_` in the method name must be escaped to `_1`.
- `size(int[])` needs an overload-disambiguating suffix: `__` + escaped `[I` (`_3I`), producing `size___3I`.
- `size(String)` uses the suffix `__Ljava_lang_String_2` because `/` turns into `_`, and `;` turns into `_2`.

Do not append the `I` of the **return type** to the long name suffix: both `size` methods return `int`, but the JVM distinguishes them by their **parameters**.

### 5.1. JVM names with `$` and Unicode

If a member class has binary name `edu.demo.jni.Outer$Inner`, the class name part in the JNI symbol has the form:

~~~text
edu_demo_jni_Outer_00024Inner
~~~

If a method is declared with the name `tínhToán` or a class contains Unicode, the C name may contain additional `_0xxxx` escapes. Do not transliterate, strip accents, or arbitrarily convert to ASCII: being off by even one UTF-16 code unit will differ from the symbol the JVM expects. The header generated by the JDK is the reliable reference.

## 6. Complete hands-on Java 17+ → JNI header → C → JVM

This example runs using **one Java class that has one native method containing an underscore and two native overloads**, thereby testing `_1`, `_3`, `_2`, and `__` simultaneously.

Directory structure after creating the files:

~~~text
jni-names/
├── src/
│   └── edu/demo/jni/
│       └── NativeNames.java
├── native_names.c
└── build/               (created by compilation commands)
    ├── classes/
    └── headers/
~~~

### 6.1. Java: `src/edu/demo/jni/NativeNames.java`

~~~java
package edu.demo.jni;

public final class NativeNames {
    static {
        System.loadLibrary("native_names");
    }

    private NativeNames() {
    }

    public static native int sum_value(int a, int b);

    public static native int size(int[] values);

    public static native int size(String text);

    public static void main(String[] args) {
        System.out.println("sum_value(2, 3) = " + sum_value(2, 3));
        System.out.println("size(int[]) = " + size(new int[] {2, 4, 6}));
        System.out.println("size(String) = " + size("JNI"));
    }
}
~~~

This is **complete and compilable** Java code on Java 17+. The `static` block loads the library by its **logical name** `native_names`; the actual native filename will be mapped by the system/JVM according to the platform. `System.loadLibrary("native_names")` does not use the Java class name or a `Java_...` symbol name.

### 6.2. Generating bytecode and header

In the `jni-names` directory, run on Linux/macOS:

~~~bash
mkdir -p build/classes build/headers
javac -h build/headers -d build/classes src/edu/demo/jni/NativeNames.java
~~~

On Windows Command Prompt:

~~~bat
if not exist build\classes mkdir build\classes
if not exist build\headers mkdir build\headers
javac -h build\headers -d build\classes src\edu\demo\jni\NativeNames.java
~~~

The output includes `build/classes/edu/demo/jni/NativeNames.class` and the header **`build/headers/edu_demo_jni_NativeNames.h`**. In the header, the core function declarations look like (this is an **excerpt**; the actual header has include guards, `#include <jni.h>`, and signature information):

~~~c
JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_sum_1value
  (JNIEnv *, jclass, jint, jint);

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_size___3I
  (JNIEnv *, jclass, jintArray);

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_size__Ljava_lang_String_2
  (JNIEnv *, jclass, jstring);
~~~

All three methods are declared `static native`, so the second hidden argument of the JNI function is **`jclass`** (class reference). If an instance native method is declared, this position is `jobject` (receiver/`this`). `JNIEnv *` always comes first in standard C JNI.

You can also read the descriptors from bytecode:

~~~bash
javap -s -p -classpath build/classes edu.demo.jni.NativeNames
~~~

Look for the lines `descriptor: (II)I`, `descriptor: ([I)I`, and `descriptor: (Ljava/lang/String;)I`. These lines are how you inspect **JVM descriptors**; distinguish them from the escaped descriptor part in the C name.

### 6.3. C: `native_names.c`

~~~c
#include "edu_demo_jni_NativeNames.h"

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_sum_1value(
    JNIEnv *env, jclass cls, jint a, jint b
) {
    (void) env;
    (void) cls;
    return a + b;
}

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_size___3I(
    JNIEnv *env, jclass cls, jintArray values
) {
    (void) cls;
    return (*env)->GetArrayLength(env, values);
}

JNIEXPORT jint JNICALL Java_edu_demo_jni_NativeNames_size__Ljava_lang_String_2(
    JNIEnv *env, jclass cls, jstring text
) {
    (void) cls;
    return (*env)->GetStringLength(env, text);
}
~~~

This is the **complete C file** for the example. It includes the header generated by `javac -h`, so the compiler can check the JNI declaration types. `JNIEXPORT` ensures symbol export; `JNICALL` selects the platform-appropriate JNI calling convention. Do not remove these macros.

`GetArrayLength` returns the **number of array elements** (here `{2,4,6}` has 3 elements). `GetStringLength` returns the length of a Java string in **UTF-16 code units** (the string `"JNI"` has 3 units). The example only passes **non-null** arguments; this learning code does not define a policy for null inputs. The addition/length operations in the example do not need other JNI APIs; for real `int` arithmetic, integer overflow must be considered when using large operands.

### 6.4. Compiling the native library and running

Run only the **set of commands matching the JVM's operating system**. You need a JDK with `jni.h`, a C compiler matching the JVM's architecture, and `JAVA_HOME` pointing to the JDK. The commands below assume you just ran the `javac -h` step successfully.

**Linux (GCC):**

~~~bash
gcc -fPIC -shared \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/linux" \
  -Ibuild/headers \
  native_names.c -o libnative_names.so

java -Djava.library.path=. -cp build/classes edu.demo.jni.NativeNames
~~~

**macOS (Clang):**

~~~bash
cc -dynamiclib -fPIC \
  -I"$JAVA_HOME/include" \
  -I"$JAVA_HOME/include/darwin" \
  -Ibuild/headers \
  native_names.c -o libnative_names.dylib

java -Djava.library.path=. -cp build/classes edu.demo.jni.NativeNames
~~~

**Windows (MSVC Developer Command Prompt):**

~~~bat
cl /LD /I"%JAVA_HOME%\include" /I"%JAVA_HOME%\include\win32" /I"build\headers" native_names.c /Fe:native_names.dll

java -Djava.library.path=. -cp build\classes edu.demo.jni.NativeNames
~~~

When built and loaded successfully, the **exact stdout** is:

~~~text
sum_value(2, 3) = 5
size(int[]) = 3
size(String) = 3
~~~

Explanation of the output: the method containing an underscore is linked by the JVM to the `sum_1value` symbol; the `size(int[])` overload is linked to the symbol containing `___3I`; the `size(String)` overload is linked to the symbol containing `__Ljava_lang_String_2`. The equal numeric output of the two `size` calls does not mean they are the same C function: they take different parameter types, have different long JNI names, and use different JNI APIs.

## 7. From class file to symbol: sequence to remember

~~~text
Java source
  package edu.demo.jni;
  class NativeNames { native int size(int[] v); }
           |
           v javac
Class binary name: edu.demo.jni.NativeNames
           |
           v Internal form
edu/demo/jni/NativeNames
           |
           v Escape class name + method name
Java_edu_demo_jni_NativeNames_size
           |
           v Overload: take parameter descriptor "[I"
           v Escape "[I" -> "_3I"
           v Prepend "__" before suffix
Java_edu_demo_jni_NativeNames_size___3I
           |
           v Export from native library + JVM lookup
Java call -> JNI C function -> Java return value
~~~

The diagram only describes the **name mapping rules**; it cannot replace properly building the binary, loading the library, and checking the class loader/ABI. The library name `native_names` and the symbol name `Java_...` are two independent mechanisms: a library can contain multiple symbols for multiple Java classes.

## 8. Special note: forward slash is not a Windows file separator

Do not mix four kinds of separators:

| Context | Correct example | Rule |
|---|---|---|
| Java package / binary name | `edu.demo.jni.NativeNames` | Dot `.` |
| JVM internal name | `edu/demo/jni/NativeNames` | Slash `/`, does not change by OS |
| Windows filesystem path | `src\edu\demo\jni\NativeNames.java` | Backslash `\` in cmd (paths); Java APIs may accept slash depending on context |
| JNI mangled C symbol | `Java_edu_demo_jni_NativeNames_size___3I` | Underscore and rule-based escaping |

Even on Windows, `FindClass(env, "edu/demo/jni/NativeNames")` still uses the standard JVM slash. Writing `"edu\demo\jni\NativeNames"` in a Java string will cause character escaping issues, and using a backslash instead of a slash in a JNI internal class name violates the API contract.

In `System.load("/absolute/path/libnative_names.so")`, you are passing a native **file path**, not an internal name. `System.loadLibrary("native_names")` takes a **logical name**, not slashes or `.so`/`.dll`/`.dylib` extensions. Do not force APIs with different purposes under the same rule.

## 9. If using `RegisterNatives`, are `Java_...` names still needed?

In addition to automatic name-based symbol lookup, JNI allows manual registration via `RegisterNatives`, mapping each Java method to a native function pointer. When registering, you use the **original Java name** and the **full JVM descriptor**, for example:

~~~text
method name:  "size"
signature:    "([I)I"
native impl:  (C function pointer with matching JNI signature)
~~~

Because the mapping is explicitly registered, the C function name **does not have to be in the `Java_...` form**. However, it must still match the JNI ABI, `JNIEnv *`, `jclass`/`jobject`, parameter types, return type, and manage registration for the right class loader. `RegisterNatives` is a different mechanism, not a way to “ignore” signatures.

Beginners should use `javac -h` and exported names first because the correspondence is easy to see. Once comfortable with the rules, you can proceed to read libraries that implement JNI through method registration.

## 10. Naming mistakes that easily break JNI linking

| Mistake | Symptom/consequence | How to fix |
|---|---|---|
| Using dots in the C function name | Expected JVM symbol does not exist | Take the internal form then apply JNI escape rules, regenerate the header. |
| Using raw `_` in a Java name that has an underscore | Wrongly exports `Java_..._sum_value` instead of `..._sum_1value` | Escape `_` to `_1`. |
| Forgetting `__` when there are two native overloads | No distinguishing long name or wrong binding | Compare against the header generated by `javac -h`, use the exact parameter suffix. |
| Using raw `[I` in the C symbol | The `[` character is not a valid escaped name | `[` must become `_3`. |
| Changing `/` to `_` but forgetting `;` | String overload is missing `_2` | Escape the full descriptor according to the table. |
| Adding the return type to the long name suffix | Symbol does not match the name the JVM expects | Use only the **parameter** descriptors in the suffix. |
| Writing a nested class as `Outer.Inner` instead of binary name `Outer$Inner` | Wrong class/symbol | Use the binary name with `$`, escaped to `_00024`. |
| Putting `java.lang.String` into a field/method descriptor | Invalid descriptor | Write `Ljava/lang/String;`. |
| Passing a file path to `FindClass` | JVM cannot find the class | Pass internal name `pkg/Class` or an array descriptor. |
| Changing the Java signature without rebuilding C/header | `UnsatisfiedLinkError` or mismatch | Re-run `javac -h`, update C, and rebuild the native library. |

For a **native method not found** error, separate three checkpoints: (1) has the JVM **loaded the library** yet, (2) has the library **exported the right JNI symbol** or called `RegisterNatives` properly, and (3) does the **descriptor/ABI** match the current Java declaration. An `UnsatisfiedLinkError` can originate from different stages.

Suggested tools:

~~~text
Java:    javac -h ; javap -s -p
Linux:   nm -D ; readelf -Ws
macOS:   nm -g
Windows: dumpbin /EXPORTS
~~~

This is a **list of suggested tool names and options**, not a complete shell command. When using them, pass the proper class name, library filename, and arguments for your current tool. Not all compilers/linkers export symbols identically under different configurations, so the header and the symbol table of the newly built binary are the evidence to compare against.

## 11. Self-check before moving to the next JNI lesson

1. For `org.demo.Fast_Parser`, what is the internal class name, and how does the escaped class part in the JNI name change at `_`?
2. In what contexts do `Outer.Inner` and `Outer$Inner` differ? Why can `_00024` appear in a JNI name?
3. What are the descriptors for `int[][]`, `String[]`, and `long calculate(int, String[])`, respectively?
4. Why does `size(int[])` produce `size___3I` with **three consecutive underscores**?
5. For `static native int f(String s)`, why does the long name suffix (if needed) contain `Ljava_lang_String_2` but not the return type `I`?
6. In JNI C, when calling `FindClass` with `"java/lang/String"`, does the `/` depend on the operating system?
7. If you move a class from `edu.demo.jni.NativeNames` to another package and forget to recompile C, can the JVM link to the old symbol name?
8. In what case can a short name be used for a native method that shares a name with a regular Java method, and why should you not export a shared short name for multiple **native overloads**?

**Key takeaway:** First get the right **binary name**, convert to **internal name using `/`**, determine the JVM descriptor, and only then **escape according to the JNI table** to form the `Java_...` symbol. A short name has no parameter suffix; a long name adds `__` and the **escaped parameter descriptors**. `javac -h` is the most reliable way to verify the actual names and signatures.

### Standard references

- [Java Native Interface Specification — Resolving Native Method Names](https://docs.oracle.com/en/java/javase/21/docs/specs/jni/design.html): rules for forming short/long names and the character escape table.
- [The Java Virtual Machine Specification — Names and Descriptors](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): binary names, internal form, field/method descriptors.
- [The javac Command — -h option](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): how to generate JNI headers from Java declarations.