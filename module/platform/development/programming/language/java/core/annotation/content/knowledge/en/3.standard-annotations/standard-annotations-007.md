# @Native: Marking Constants for Native Code in Java Core

`@Native` is a standard Java annotation declared at `java.lang.annotation.Native` since Java 8. It marks **a field that defines a constant value that may be referenced from native code** (such as C/C++ via JNI). Native header generation tools, especially the `javac -h` command, can use this marker to include Java constant values in the header for the native side.

Key point to understand: `@Native` is **metadata for compiler/header-generation tools**. It does not turn a Java field into a native method, does not automatically load C/C++ libraries, and does not cause the JVM to convert data or synchronize values at runtime.

## 1. Lesson Objectives

After this lesson, you will be able to:

- Accurately state the purpose of `@Native` and the scenarios where it is useful.
- Identify its target (`FIELD`), lifecycle (`SOURCE`), and the fact that the annotation has no configuration elements.
- Write a Java 17+ class containing constants annotated with `@Native`, using `javac -h` to generate a native header.
- Read the constant macros in the generated `.h` file and explain how C/C++ code uses them.
- Distinguish `@Native` from the `native` keyword, JNI, `System.loadLibrary(...)`, and runtime annotations.
- Avoid ineligible constant cases, stale headers, and false assumptions about Reflection.

## 2. Why Mark Constants for Native Code?

Suppose a Java application communicates with a C/C++ library that uses status codes. In Java, you have:

~~~java
public static final int STATUS_OK = 0;
public static final int STATUS_BUSY = 42;
~~~

The C side may also need the two numbers `0` and `42`. If developers manually copy the numbers into a C header file, every time Java changes a constant, that copy must be updated manually. Missing an update on one side will cause the two sides to interpret the same status code differently.

`@Native` helps make the intent explicit: *this constant may be referenced from native code*. Combined with `javac -h`, the information is exported into the header, allowing native code to use the generated macro names instead of repeating literals.

Example:

~~~java
import java.lang.annotation.Native;

public final class NativeCodes {
    @Native
    public static final int STATUS_OK = 0;

    @Native
    public static final int STATUS_BUSY = 42;
}
~~~

In this context, `@Native` does not change the values of `STATUS_OK` or `STATUS_BUSY`, nor does it make them "native" in terms of data type. They remain ordinary Java constants. The annotation is primarily a signal for header-generation tools.

## 3. Technical Specifications of `java.lang.annotation.Native`

Java SE defines `@Native` with the following meta-annotations:

~~~java
@Documented
@Target(ElementType.FIELD)
@Retention(RetentionPolicy.SOURCE)
public @interface Native {
}
~~~

The snippet above illustrates the JDK API definition; you do **not** need to, and should not, redeclare an annotation with the same name `java.lang.annotation.Native` yourself.

| Characteristic | Meaning |
| --- | --- |
| Package | `java.lang.annotation` — requires importing `java.lang.annotation.Native` |
| Available since | Java 8 |
| `@Target(FIELD)` | Applied only directly to field declarations, not to classes or methods |
| `@Retention(SOURCE)` | Processed by the compiler during the source phase; the annotation is not retained in `.class` files |
| `@Documented` | The annotation can appear in the Javadoc documentation for the associated element |
| Element | No elements to pass; the usage syntax is `@Native` |
| Typical usage | Marking constant fields that native header generation tools need to recognize |

From `@Retention(SOURCE)`, it follows that **runtime Reflection does not see `@Native`** on a field, even when that field can be looked up via Reflection. This is a reasonable choice because header-generation tools use this information at compile time.

`@Target(FIELD)` only controls syntactically valid placement. It does not by itself guarantee that a field is a constant; for the header to emit a stable value, you should use `static final`, an appropriate primitive type (for example `int`, `long`), and an initializer expression that is a compile-time constant.

## 4. Complete Java 17+ Example: Generating a Header from Constants

Create **a single file** named `NativeCodes.java`, without a `package` declaration so the header file name is easy to observe:

~~~java
import java.lang.annotation.Native;

public final class NativeCodes {
    @Native
    public static final int STATUS_OK = 0;

    @Native
    public static final int STATUS_BUSY = 42;

    @Native
    public static final long MAX_BUFFER_BYTES = 4096L;

    private NativeCodes() {
        // Utility class: do not instantiate.
    }

    public static void main(String[] args) throws NoSuchFieldException {
        System.out.println("STATUS_OK=" + STATUS_OK);
        System.out.println("STATUS_BUSY=" + STATUS_BUSY);
        System.out.println("MAX_BUFFER_BYTES=" + MAX_BUFFER_BYTES);
        System.out.println("RUNTIME_VISIBLE=" +
                NativeCodes.class.getField("STATUS_OK")
                        .isAnnotationPresent(Native.class));
    }
}
~~~

In the directory containing `NativeCodes.java`, run using JDK 17 or later:

~~~bash
javac -encoding UTF-8 -h headers NativeCodes.java
java NativeCodes
~~~

`javac -h headers` compiles the Java file normally and requests generating the JNI/native headers in the `headers` directory. The compiler can create the necessary output directory. For a class without a package like this example, you will see the file `headers/NativeCodes.h`.

Stdout of the `java NativeCodes` command:

~~~text
STATUS_OK=0
STATUS_BUSY=42
MAX_BUFFER_BYTES=4096
RUNTIME_VISIBLE=false
~~~

Line-by-line explanation:

1. The first three lines come from **the values of the Java fields**, not from executing a native library.
2. `NativeCodes.class.getField("STATUS_OK")` retrieves the Reflection object for the public field.
3. `isAnnotationPresent(Native.class)` returns `false` because `@Native` has `SOURCE` retention: this metadata is no longer present in the class when the program runs.
4. Even though Reflection returns `false`, `javac -h` can still use the annotation during the compilation phase to generate the header.

### What Is in the Generated Header?

In the file `headers/NativeCodes.h`, the constant-related declarations have the form:

~~~c
#undef NativeCodes_STATUS_OK
#define NativeCodes_STATUS_OK 0L
#undef NativeCodes_STATUS_BUSY
#define NativeCodes_STATUS_BUSY 42L
#undef NativeCodes_MAX_BUFFER_BYTES
#define NativeCodes_MAX_BUFFER_BYTES 4096LL
~~~

These are the macro lines verified from the example with JDK 21. The actual header also contains include guards, comments, and includes generated by `javac`; the excerpt above shows only **the key lines for the constants**. For `int` values, the header generates C-style literals with an `L` suffix; for Java `long`, the macro literal may use an `LL` suffix.

The macro name combines the class name and the field name, for example `NativeCodes_STATUS_BUSY`. When a class belongs to a package, the header file name and macro prefix reflect the fully qualified Java name, with character conversion according to JNI rules. Therefore, inspect the actually generated `.h` file rather than guessing macro names.

The native side can reference the header in C code as follows (this snippet **illustrates the C side**, not a complete C program):

~~~c
#include "NativeCodes.h"

int is_busy_code(int status) {
    return status == NativeCodes_STATUS_BUSY;
}
~~~

When compiling C code, you need to properly configure the include paths to the generated header directory and the JDK's JNI headers (because the generated native header may include `jni.h`). Simply including the `.h` file in C source does not automatically create a native library, and the Java example above does not require running C code to produce the stdout shown.

## 5. How It Works from Java Code to Header

~~~text
NativeCodes.java
   |
   |  @Native on static final int/long
   v
javac -h headers NativeCodes.java
   |
   +--> NativeCodes.class
   |       bytecode uses constants normally;
   |       @Native with SOURCE retention is not retained
   |
   +--> headers/NativeCodes.h
           macros corresponding to the exported constants
                      |
                      v
           C/C++ code includes the header
           and uses the macro names during the native build
~~~

It is important to clearly distinguish **two artifacts**: `.class` for the JVM and `.h` for the native toolchain. The annotation provides a hint during header generation. It does not create a Java ↔ C/C++ function-call bridge, does not perform data marshaling, and does not provide an automatic native invocation mechanism.

Java code and C/C++ code only share the same definitions when the project's build process actually **regenerates the header and recompiles the native code when constants change**. If a stale header is used, the numbers in the C/C++ code can still diverge from Java. Java compile-time constants can also be inlined into the bytecode of calling code; changing a constant's value may require recompiling dependent code.

## 6. How Does `@Native` Differ from the `native` Keyword and JNI?

The following two constructs target different things:

~~~java
import java.lang.annotation.Native;

class NativeExample {
    @Native
    public static final int OPERATION_READ = 1;

    public native int readValue();
}
~~~

**`@Native`** is placed on a field, hinting to header-generation tools that the constant may be referenced from native code. **`native`** is a method modifier; it declares a method implemented in native code, so it has no Java method body. The illustrative code above consists only of declarations, not a standalone runnable program: calling `readValue()` requires a matching native implementation and loading the necessary library.

| Aspect | `@Native` on a field | `native` on a method |
| --- | --- | --- |
| Purpose | Export constant metadata for native headers | Declare a method implemented outside Java |
| Placement | Field | Method |
| Does it call C/C++ by itself? | No | Does not call on its own without an invocation/implementation |
| Can it cause `javac -h` to generate a header? | Yes, when the field is an eligible constant | Yes, when the class contains a native method |
| Does it load a library? | No | No; library loading is a separate step when an application uses JNI |

**JNI (Java Native Interface)** is a set of conventions/APIs that enable Java and native code to work together. `@Native` can participate in the JNI header-generation workflow, but by itself it is **not a JNI bridge**. The call `System.loadLibrary("...")` is the mechanism for loading a native library when needed; it is not directly related to whether `@Native` is present on a field.

`@Native` is also not a tool for creating a GraalVM Native Image, does not automatically compile Java into native machine code, and does not replace `javac -h`.

## 7. When Should and Shouldn't You Use It?

Use `@Native` when a project actually has a C/C++ component that depends on a set of Java constant values, and the native build consumes the tool-generated header. Suitable scenarios include status codes, bitmask flags, operation codes, or size limits that are stable and need to be used on both sides.

Example of bitmask flag constants:

~~~java
import java.lang.annotation.Native;

class FileFlags {
    @Native public static final int READ  = 1 << 0;
    @Native public static final int WRITE = 1 << 1;
}
~~~

`1 << 0` and `1 << 1` are **compile-time constant expressions**; the two fields have values `1` and `2`, respectively. This is a reasonable case for exporting constants via a header.

You do not need `@Native` for every `static final`. A constant used only internally within Java has no reason to be included in a native header. Nor should `@Native` be treated as a tool for validation, persistence, security, or dependency injection: it does not provide those capabilities.

It is necessary to distinguish a *constant variable* from a field that merely has the `final` modifier. The following example is not suitable for exporting a constant macro:

~~~java
import java.lang.annotation.Native;

class BadConstantExample {
    @Native
    static final int VALUE = Integer.parseInt("42");
}
~~~

Although the field is declared `static final`, the call `Integer.parseInt("42")` is not a Java **constant expression**; you cannot expect it to be exported as a constant macro like `42`. `@Native` does not turn a runtime computation into a constant expression.

## 8. Common Mistakes and How to Check

**Mistake 1 — Wrong package:** Writing `import java.lang.Native;` is incorrect. The full name is `java.lang.annotation.Native`.

**Mistake 2 — Placing on the wrong declaration kind:** `@Native` has target `FIELD`. Placing it on a method or class will cause a compilation error. Place it on a field that declares a constant value needed by native code.

**Mistake 3 — Expecting Reflection to read the annotation:** `@Native` has `SOURCE` retention, so it cannot be read via `Field.getAnnotation(Native.class)` at runtime. Use `javac -h` to observe its actual role.

**Mistake 4 — Running only `javac NativeCodes.java`:** That command compiles the Java code but does not request native header generation. When you want to generate headers, use the `-h <thu_muc>` option, for example `javac -h headers NativeCodes.java`.

**Mistake 5 — Annotating a field whose value is not a compile-time constant:** `final` only prevents reassignment after initialization; it does not mean "able to export a literal at compile time". Choose primitive types and constant expressions according to Java rules; inspect the actual generated `.h` file.

**Mistake 6 — Assuming the header exports every field:** `javac -h` does not mean every field of the class becomes a macro. In this annotation scenario, specifically mark the constant fields that native code needs and inspect the output contents.

**Mistake 7 — Editing `.h` manually:** Header files generated by `javac` may be overwritten on the next build. Edit the source value in `.java`, regenerate the header, and then recompile the dependent native code.

**Mistake 8 — Confusing a header with a library:** Having a `.h` file does not mean having a `.dll`/`.so` file, a native implementation, linking, or library loading. Those are separate steps if the application actually calls native methods.

## 9. Practice Exercises

1. Create `NativeCodes.java` as in the example. Predict the stdout, then run `javac -h headers NativeCodes.java` and `java NativeCodes`. Verify all three values and `RUNTIME_VISIBLE=false`.
2. Open `headers/NativeCodes.h` and find the macros for `STATUS_OK`, `STATUS_BUSY`, and `MAX_BUFFER_BYTES`. Explain why using the generated names helps avoid manually copying numbers.
3. Add `@Native public static final int FLAG_COMBINED = (1 << 0) | (1 << 2);` to the class. Predict what value the macro exports, regenerate the header, and verify it (the numeric result is `5`).
4. Remove `@Native` from `STATUS_BUSY` and regenerate the header into a clean output directory. Check which macro no longer appears and explain why.
5. Add a method `public native void ping();` but **do not call it**. Use `javac -h` to observe how JNI method declarations differ from constant macros.
6. Explain in your own words why `getAnnotation(Native.class)` does not return the annotation, even though `javac -h` still generates the header.

## 10. Key Takeaways

- `@Native` is a built-in annotation available since Java 8, with the full name `java.lang.annotation.Native`.
- It applies only to fields (`@Target(FIELD)`), has `SOURCE` retention, and is used to mark constants that may be referenced by native code.
- `javac -h` can generate native headers and macros for those constants, even when the class declares no native methods.
- A field annotated with `@Native` remains an ordinary Java field; native code does not run automatically, and runtime Reflection does not see the annotation.
- The build process needs to regenerate the header and rebuild dependent components when constants change.

### References

- Oracle Java SE 17 — [`java.lang.annotation.Native`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Native.html).
- Oracle Java SE 17 — [`javac` documentation, `-h` option](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
