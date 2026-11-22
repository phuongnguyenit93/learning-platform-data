# Passing the Correct Name, Offset, and Length to defineClass

When writing a custom `ClassLoader` to read bytecode from a file, JAR, network, memory, or a custom container, the decisive step is calling the **`defineClass(String name, byte[] b, int off, int len)`** method correctly. The three values **`name`, `off`, `len`** must accurately describe the **class definition** carried by the byte region: the binary name of the class inside the ClassFile and the starting position/length of the valid ClassFile portion in the array.

A small mistake can produce a `ClassFormatError`, a `NoClassDefFoundError`, or an error that only appears when class-loading code runs in production. Having a byte array that is large enough or contains a valid ClassFile segment is **not sufficient** if we slice at the wrong boundaries, pass the wrong buffer size, or declare a mismatched class name.

**Key rule:**

~~~java
Class<?> type = defineClass(binaryName, bytes, offset, classFileLength);
~~~

This is a **fragment** that must run from a subclass of `ClassLoader` or a context permitted to call that `protected` method; it is not a public call from any arbitrary class.

- `binaryName`: the JVM/Java binary name of the **exact class inside the ClassFile**, for example `com.example.Widget`, not the path `com/example/Widget.class`.
- `bytes`: the array containing the ClassFile data.
- `offset`: the **starting byte index** of the ClassFile in the `bytes` array, counted from **0**.
- `classFileLength`: the **number of bytes of the ClassFile starting at offset**, not the end index of the array.

If the entire array is exactly one ClassFile (with no extra header/footer), the most typical call is:

~~~java
defineClass("com.example.Widget", classBytes, 0, classBytes.length);
~~~

## 1. The Role of defineClass in a Custom Class Loader

`ClassLoader` is responsible for locating a class's data and coordinating with the JVM to define the class. For a traditional subclass, the steps are typically:

~~~text
Request to load "com.example.Widget"
       |
       v
loadClass(...) checks already loaded / delegates to parent
       |
       v
findClass(...) reads or obtains ClassFile byte[]
       |
       v
determine binary name + valid byte segment
       |
       v
defineClass(name, bytes, offset, length)
       |
       v
JVM creates Class<?> definition
       |
       v
resolve / initialize at the appropriate time
~~~

`defineClass` is the step that **defines a class from its ClassFile representation**. It does not mean the static initializer is always executed right at the call site. Linking, resolution, and initialization are separate JVM operations. `resolveClass(type)` is usually called by code in `loadClass` when resolution is requested; initialization only occurs according to Java/JVM conditions.

A simple subclass typically overrides **`findClass(String name)`** to fetch the bytes while keeping the default parent-first `loadClass` mechanism. Do not override `loadClass` yourself unless you need child-first loading or a special policy, because it is very easy to break delegation, create two types with the same name via different loaders, or block platform classes.

### Key Parameter Specifications

| Parameter | Meaning | Common Mistakes |
| --- | --- | --- |
| `name` | The binary name corresponding to the class in the ClassFile; the API also supports `null` in some overloads, though normally you should pass the exact name. | Using the path `pkg/MyClass.class` or a name different from `this_class` inside the bytecode. |
| `b` | The byte array containing the ClassFile. | Passing an incompletely populated buffer, a modified buffer, or compressed/encrypted data that has not been decoded. |
| `off` | The first byte to read, zero-based index. | Mistakenly reading a container header or passing offset 0 despite a prefix. |
| `len` | The number of ClassFile bytes in the array starting from `off`. | Passing `b.length` instead of the payload length, confusing `endIndex` with `length`, or forgetting to subtract the prefix. |

**The `name` is not a file name:** If we read `plugins/lab/generated/Echo.class` from disk, the type's binary name is `lab.generated.Echo`, not `plugins.lab.generated.Echo`, `lab/generated/Echo`, or a string ending with `.class`.

## 2. The Binary Name Must Match the Name Declared in the Bytecode

Inside a ClassFile, the `this_class` structure references metadata identifying the type. For Java:

~~~java
package lab.generated;
public class Echo { }
~~~

The ClassFile describes the corresponding internal name `lab/generated/Echo`, whereas the `name` parameter of `ClassLoader.defineClass` is provided as a **binary name**:

~~~text
Must pass:    lab.generated.Echo
Do not pass:  lab/generated/Echo
Do not pass:  lab/generated/Echo.class
Do not pass:  Echo
Do not pass:  lab.generated.Other
~~~

Nested class names also use `$` in the binary name, for example `lab.generated.Outer$Inner` for a normally compiled member class. A file name may contain `$`, but it must be derived from the **actual name inside the ClassFile**, not constructed arbitrarily by replacing slashes based on a container path.

If you provide a `name` **different** from the name declared by the ClassFile, the JVM may throw **`NoClassDefFoundError`** (often with *wrong name* details). There is no mechanism to rename a type merely by changing the `name` parameter: to give a class a different name, you must transform the ClassFile validly along with all related metadata and references according to JVM rules.

**Is passing `null` allowed?** Some `defineClass` overloads allow `name == null` and let the JVM infer it from the ClassFile, but the API documentation warns of limited checks associated with the name/package; therefore, **you should pass a non-null, validated binary name** in custom loaders. In particular, the `java.*` package has protection constraints, and the bytecode name/module kind can affect security checks.

## 3. off and len Represent the Byte Range [off, off + len)

The byte sequence of a standard ClassFile begins with **`CA FE BA BE`**. A custom storage format's header/footer may appear outside the actual payload:

~~~text
byte[] container:

Index:  0   1   2   3   4   5   6   7   8   9  ...      N
        +-------------------+------------------------+----------+
Data:   | 5-byte HEADER     | CA FE BA BE ... .class | TRAILER  |
        +-------------------+------------------------+----------+
                            ^
                            off = 5
                             <---- len bytes ---->
~~~

In this example, the ClassFile occupies the region **from `off` (inclusive) to `off + len` (exclusive)**. Therefore:

- `off = 5`, `len = payload.length` is correct if `payload` contains all the ClassFile bytes.
- `off = 0`, `len = payload.length` will pass the header as well and truncate the end of the ClassFile.
- `off = 5`, `len = container.length` easily exceeds the array bounds; even if it does not, passing the trailer as well is semantically wrong.
- `off = 5`, `len = payload.length - 1` cuts off the last byte of the ClassFile, typically leading to a `ClassFormatError`.
- `off = 5`, `len = off + payload.length` confuses the **end index** with the **length**.

You need to distinguish four quantities:

~~~text
offset                 starting position of the payload in the array
endExclusive           position after the last byte = offset + length
length                 number of payload bytes = endExclusive - offset
container.length       length of the entire array, which may be larger than the payload
~~~

A common mistake when working with streams, buffer pools, and custom containers is using the **capacity** instead of the number of bytes actually received or the number of decoded payload bytes. A buffer with a capacity of 65,536 does not mean all 65,536 bytes belong to the ClassFile.

### Range Checking Before defineClass

A safety condition before using an untrusted array is:

~~~java
if (offset < 0 || length < 0 || length > data.length
        || offset > data.length - length) {
    throw new IndexOutOfBoundsException("Invalid ClassFile byte range");
}
~~~

This is a **fragment**, assuming `data` is a non-`null` array and `offset`/`length` are integers. The condition using `offset > data.length - length` avoids overflow of the addition expression `offset + length`. The library/JVM still validates parameters and bytecode format, but boundary validation provides clearer input error reporting.

**Do not treat length validation as ClassFile validation.** Checking that the offset/length are valid only says the range lies within the array; the bytes may still have the wrong magic, an invalid constant pool, the wrong version, or be corrupted.

## 4. Java 17 Example: Same File, Buffer with Prefix/Suffix

This example uses the JDK compiler to generate a single `lab.generated.Echo` ClassFile at runtime, then places the payload into a larger array with a **5-byte prefix and a 7-byte suffix**. A `ClassLoader` subclass calls `defineClass` directly to test both valid and invalid cases.

Create a standalone file **`DefineClassRangeDemo.java`**:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class DefineClassRangeDemo {
    private static final String NAME = "lab.generated.Echo";
    private static final int PREFIX = 5;
    private static final int SUFFIX = 7;

    static class ByteArrayLoader extends ClassLoader {
        ByteArrayLoader() {
            super(ClassLoader.getSystemClassLoader());
        }

        Class<?> define(String binaryName, byte[] container,
                        int offset, int length) {
            return defineClass(binaryName, container, offset, length);
        }
    }

    public static void main(String[] args) throws Exception {
        Path root = Files.createTempDirectory("defineclass-range-");
        Path source = root.resolve("src/lab/generated/Echo.java");
        Path classes = root.resolve("classes");

        Files.createDirectories(source.getParent());
        Files.createDirectories(classes);

        Files.writeString(source,
                "package lab.generated;\n"
                + "public class Echo {\n"
                + "  public static String message() { return \"OK\"; }\n"
                + "}\n",
                StandardCharsets.UTF_8);

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run with a full JDK");
        }

        int result = compiler.run(null, null, null,
                "--release", "17",
                "-d", classes.toString(), source.toString());

        if (result != 0) {
            throw new IllegalStateException("Compilation failed");
        }

        byte[] payload = Files.readAllBytes(
                classes.resolve("lab/generated/Echo.class"));

        byte[] container = new byte[PREFIX + payload.length + SUFFIX];
        Arrays.fill(container, (byte) 0x11);
        System.arraycopy(payload, 0, container, PREFIX, payload.length);

        Class<?> type = new ByteArrayLoader().define(
                NAME, container, PREFIX, payload.length);

        System.out.println("Loaded: " + type.getName());
        System.out.println("Message: "
                + type.getMethod("message").invoke(null));
        System.out.println("Container larger: "
                + (container.length > payload.length));

        try {
            new ByteArrayLoader().define(NAME, container, 0, payload.length);
        } catch (ClassFormatError e) {
            System.out.println("Wrong offset: ClassFormatError");
        }

        try {
            new ByteArrayLoader().define(
                    NAME, container, PREFIX, payload.length - 1);
        } catch (ClassFormatError e) {
            System.out.println("Short length: ClassFormatError");
        }

        try {
            new ByteArrayLoader().define(
                    "lab.generated.Other", container, PREFIX, payload.length);
        } catch (NoClassDefFoundError e) {
            System.out.println("Wrong name: NoClassDefFoundError");
        }

        try {
            new ByteArrayLoader().define(
                    NAME, container, container.length - 2, 8);
        } catch (IndexOutOfBoundsException e) {
            System.out.println("Invalid range: IndexOutOfBoundsException");
        }
    }
}
~~~

Using **JDK 17 or newer**, run in the directory containing the file:

~~~bash
javac --release 17 DefineClassRangeDemo.java
java DefineClassRangeDemo
~~~

With a standard JDK that includes `jdk.compiler`, the program prints:

~~~text
Loaded: lab.generated.Echo
Message: OK
Container larger: true
Wrong offset: ClassFormatError
Short length: ClassFormatError
Wrong name: NoClassDefFoundError
Invalid range: IndexOutOfBoundsException
~~~

**Explanation:**

1. `JavaCompiler` compiles the generated source file into the ClassFile of `lab.generated.Echo` targeting Java 17. The bytecode is read **exactly** from `classes/lab/generated/Echo.class`.
2. `Arrays.fill` creates surrounding bytes that do not belong to the ClassFile. `System.arraycopy` places the entire payload at index `PREFIX = 5`.
3. The call `define(NAME, container, PREFIX, payload.length)` passes the exact byte region and exact binary name to the JVM, creating a valid class.
4. Reflectively calling `message()` proves that the class has been defined and used. The result is the string `OK`.
5. When passing `off = 0`, the data starts with 0x11 instead of the `CAFEBABE` magic. The JVM rejects the format with `ClassFormatError`.
6. When cutting `len` one byte shorter than the payload, the ClassFile is missing its end and is rejected with `ClassFormatError`.
7. When passing `name = lab.generated.Other` while the bytecode itself declares `lab.generated.Echo`, the error is `NoClassDefFoundError` due to the name mismatch.
8. With an offset near the end of the buffer and `len = 8` exceeding the array, the JVM detects an invalid range and throws `IndexOutOfBoundsException`.
9. Each failure test uses **a fresh `ByteArrayLoader`**. If we tried defining the same name again in a loader that had already defined it successfully, we would also have to account for duplicate-definition errors rather than just observing the input bytes.

The example creates a temporary directory to hold dynamically generated source/class files; you can clean it up after running. It requires no network connection or libraries outside the JDK. `Class.forName` or `resolveClass` is not needed for this demo because we call protected `defineClass` directly and then use reflection. In a real application, you also need a parent delegation policy, bytecode source verification, package protection, and lifecycle management.

### Why Not Use container.length?

In the example, `container.length` is `5 + payload.length + 7`. If you use `len = container.length` starting at offset 5, the range goes past the end of the array. If you take offset 0 and length container.length, you pass both the prefix/trailer; the JVM cannot interpret that as a ClassFile starting at byte 0.

When a container holds **multiple ClassFiles**, do not pass the entire container to `defineClass`; you must extract the exact single ClassFile to load and its corresponding name. Finding ClassFile boundaries in a container format is the responsibility of the container's parser/decoder, not `defineClass`.

## 5. Example of a Properly Implemented findClass

This is a **condensed fragment** of a `ClassLoader` subclass where `byte[] data` is the entire ClassFile read from a trusted source:

~~~java
@Override
protected Class<?> findClass(String binaryName)
        throws ClassNotFoundException {
    byte[] data = readClassFileBytes(binaryName);
    if (data == null) {
        throw new ClassNotFoundException(binaryName);
    }
    return defineClass(binaryName, data, 0, data.length);
}
~~~

`readClassFileBytes(...)` in the fragment is an **undefined** method illustrating a loader that reads from a file/JAR/resource/memory; this is **not standalone compilable code**. Points to keep in mind:

- Convert the binary name to a path in a controlled manner, for example `binaryName.replace('.', '/') + ".class"` when reading from a JAR or custom classpath. This path is the **entry name/path**, not the `name` parameter for `defineClass`.
- If the bytecode is not found, throw `ClassNotFoundException` with the binary name and preserve the I/O cause if any, rather than swallowing the error and returning `null`.
- If `byte[] data` is the entire payload, `off = 0` and `len = data.length`.
- Do not use `InputStream.available()` as the total ClassFile length; it only reflects the number of bytes that can be read without blocking per the stream contract, and **does not guarantee content size**. With Java 17, `readAllBytes()` is suitable for files of controlled size with a reasonable limit policy.
- Do not use the length of a string obtained by decoding bytecode as text. A ClassFile is **binary**, not a UTF-8 string containing Java source.
- For container data with a prefix/suffix, pass the exact region or create `Arrays.copyOfRange(container, off, off + len)` and then call `defineClass(name, slice, 0, slice.length)`. Copying makes it easier to avoid offset mistakes at the cost of extra memory; start/end indices must be validated before copying.

**Note on duplicate classes:** `findClass` should only define a class when no definition exists yet under the `loadClass` policy. If you bypass `findLoadedClass` and redefine the same binary name within one loader, the JVM can throw `LinkageError`. Do not try to use `defineClass` to overwrite an already-loaded class.

## 6. Errors and Exceptions to Distinguish

| Symptom | Typical Cause | How to Check |
| --- | --- | --- |
| `IndexOutOfBoundsException` | Negative `off`/`len` or range exceeding the array. | Inspect `off`, `len`, `b.length`; verify calculations do not overflow. |
| `ClassFormatError` | Byte sequence does not form a valid ClassFile: wrong magic, corrupted constant pool, truncated data, or garbage data. | Recheck the first 4 bytes `CAFEBABE` and exact payload boundaries. |
| `NoClassDefFoundError` with *wrong name* | Requested `name` differs from `this_class` in the ClassFile. | Compare the requested binary name with the actual name in bytecode using `javap -v`. |
| `UnsupportedClassVersionError` | Bytecode targets an unsupported JVM version. | Check `major_version` in the ClassFile and the running Java version. |
| `SecurityException` | Possible violation of forbidden package definition rules or certificate/package constraints. | Check the package, signing, ProtectionDomain, and code source design. |
| `LinkageError` | For example, duplicate definition in the same loader or linkage conflict between type definitions. | Check `findLoadedClass`, loader synchronization, namespace, and delegation. |
| `ClassNotFoundException` | `findClass` could not find the required data; usually in the class lookup path rather than ClassFile parsing. | Check binary-name-to-path conversion, byte source, and I/O cause. |

Some errors such as `UnsupportedClassVersionError` and `NoClassDefFoundError` also belong to the `LinkageError` hierarchy, but carry more specific diagnostic meaning. Do not assume every `NoClassDefFoundError` is due to a wrong name: it can also be caused by a missing dependency or a class left in a failed initialization state from earlier. Read the **full message and cause**.

### Quick Header Check

A valid ClassFile has the first four bytes `CA FE BA BE`:

~~~java
boolean plausibleMagic = length >= 4
        && (data[offset] & 0xFF) == 0xCA
        && (data[offset + 1] & 0xFF) == 0xFE
        && (data[offset + 2] & 0xFF) == 0xBA
        && (data[offset + 3] & 0xFF) == 0xBE;
~~~

This is a **fragment**, assuming offset/length have already been validated within data. `plausibleMagic` is only a **sanity check**; it does not replace the JVM verifier and does not guarantee that the rest of the ClassFile is valid or trustworthy.

For missing or version-mismatched bytecode, you can use:

~~~bash
javap -v lab.generated.Echo
~~~

when `lab.generated.Echo` has been compiled onto the right classpath with no name conflicts. `javap -v` displays the major version, this_class, constant pool, and structure to help cross-check the name/version. For a custom container, you can extract the exact ClassFile to a file before inspecting it.

## 7. Does the ByteBuffer Overload Solve Offset Errors?

In addition to the `byte[]` overloads, `ClassLoader` also has the method `defineClass(String, ByteBuffer, ProtectionDomain)` and related overloads. With `ByteBuffer`, you must accurately understand the data region used to define the class in terms of the buffer's **position/limit/remaining** and the API contract rather than guessing from `capacity`.

If data is received from network/NIO, the typical pattern is to prepare a buffer containing only the payload or create a **slice** with the right position/limit, and then call the appropriate overload. However, using ByteBuffer **does not automatically fix** a wrong binary name, corrupted data, wrong boundaries, or ProtectionDomain inconsistencies.

For `byte[]`, what matters remains computing:

~~~text
0 <= off
0 <= len
off + len <= b.length  (check in a way that avoids overflow)
payload = b[off ... off+len)
~~~

For untrusted input, you should enforce a payload size limit, ensure the byte source has been fully decompressed/verified, and avoid using shared mutable data that another thread could modify while the class is being defined. You can copy into a privately owned array before calling `defineClass` if the bytecode source might be modified concurrently.

## 8. Name, Package, and Class Definition Permissions

`defineClass` does not merely check the syntax of four parameters. The JVM and ClassLoader also enforce rules regarding:

- **Package:** a class belongs to a package according to its actual binary name. Certain packages such as `java.*` cannot normally be defined by custom class loaders.
- **ProtectionDomain:** the simple overload uses the default protection domain associated with the loader per the API contract; when loading code with different origins/permissions, an overload with an explicit `ProtectionDomain` may be required.
- **Certificate/signing consistency:** classes in the same package of a defining loader may have to satisfy certificate consistency requirements per the `ClassLoader` API.
- **Type identity:** the same binary name with different defining loaders constitutes two distinct JVM types. Do not call `defineClass` twice in two loaders to pretend to create a second copy of a shared API interface.
- **Class initialization:** `defineClass` does not mean running the static initializer of the newly defined type. Initialization timing follows JLS/JVMS rules.

If you need to build a plugin system with child-first loading, you should distinguish shared API packages (delegated to the parent) from private implementation packages (owned by the plugin loader). Passing the right name/byte range is a necessary condition, but **not sufficient** to make a custom loader safe and compatible with all dependencies.

## 9. Common Anti-Patterns

**Using `buffer.length` as `len` despite a prefix:**

~~~java
// Wrong if there is a header/trailer outside the ClassFile:
defineClass(name, container, prefixSize, container.length);
~~~

`container.length` includes bytes that do not belong to the payload, easily exceeding array bounds or misinterpreting the ClassFile. Use the exact `payloadLength`.

**Using the end index as the length:**

~~~java
// Wrong if endExclusive is the ending index:
defineClass(name, container, start, endExclusive);
~~~

The correct value is `endExclusive - start` when the ending index is exclusive.

**Using the right offset with the wrong name:**

~~~java
// Wrong if the ClassFile declares pkg.Widget, not pkg.Other:
defineClass("pkg.Other", bytes, 0, bytes.length);
~~~

You cannot rename a class by editing the `name` string.

**Reading a binary file into a String and converting back to byte[]:**

~~~java
// Wrong idea: a ClassFile is not UTF-8 text of source code.
String source = new String(classBytes, java.nio.charset.StandardCharsets.UTF_8);
byte[] converted = source.getBytes(java.nio.charset.StandardCharsets.UTF_8);
~~~

Doing so can corrupt bytes that are invalid in UTF-8, altering the contents and causing `ClassFormatError`. Keep binary data intact.

**Concatenating multiple ClassFiles into one array and defining the whole array:** The JVM expects only **one valid ClassFile** per `defineClass` call. You must extract the exact entry before calling it.

**Assuming defineClass always returns a usable class:** A ClassFile may be defined successfully, while linking/resolution/dependency or initialization errors only arise later upon use. Distinguish errors by phase and log the cause.

## 10. Checklist Before Calling defineClass

1. **Binary name:** does it match `pkg.Type` according to the name inside the ClassFile? No `.class` suffix or `/` characters from an internal name.
2. **Input data:** does the byte array contain **one complete** ClassFile that has not been altered, compressed, or truncated?
3. **Boundaries:** `off` is the starting index; `len` is the number of payload bytes; `off + len` does not exceed `b.length`.
4. **Header:** if debugging is needed, are the first four bytes of the payload region `CA FE BA BE`?
5. **Version:** is the ClassFile target supported by the current JVM?
6. **Class loader:** has the same binary name already been defined in this loader? Are parent delegation and the `findLoadedClass` policy appropriate?
7. **Package/ProtectionDomain:** are any package/certificate/security rules violated?
8. **Concurrency:** could the bytes be modified by another thread during definition? If so, copy them into a private buffer.
9. **Error observation:** distinguish `ClassFormatError`, `NoClassDefFoundError`, `IndexOutOfBoundsException`, `UnsupportedClassVersionError`, and linking/initialization issues.

## 11. Knowledge Self-Check

**Question 1.** An array is 1024 bytes long, and the ClassFile starts at offset 32 and is 800 bytes long. How must it be called?

**Answer:** `defineClass(name, b, 32, 800)`. The byte range read is `[32, 832)`, not `[32, 800)`.

**Question 2.** If you pass `len = 832` instead of 800, is that valid because 832 is `endExclusive`?

**Answer:** No. `len` is the **length**, not the ending index. Starting from off 32, that slice would be 832 bytes long and end at 864.

**Question 3.** The bytecode itself declares `com.demo.Service`; is calling `defineClass("com/demo/Service", bytes, 0, bytes.length)` standard?

**Answer:** No. The `name` parameter requires the **binary name** `com.demo.Service`, not the internal name `com/demo/Service`.

**Question 4.** The ClassFile is completely valid, but the loader declares a different name. What is the usual error?

**Answer:** `NoClassDefFoundError` with a *wrong name* message, because the requested name does not match the name inside the bytecode.

**Question 5.** `byte[]` has the exact four magic bytes, but `len` is missing the last byte. Is that enough for a successful definition?

**Answer:** No. The magic number is only a preliminary check, whereas the ClassFile format requires complete content. The JVM can throw `ClassFormatError`.

**Question 6.** Each loader defines a `com.example.Api` from identical bytecode. Do the two types automatically merge into one?

**Answer:** No. Type identity includes the defining loader; a shared API contract must be loaded through an appropriate common loader if the two sides want to cast directly.

## Key Takeaways

`defineClass(name, b, off, len)` requires the **exact binary name** and the **exact byte region of a single ClassFile**. `off` is the starting byte (zero-based), and `len` is the number of bytes to read, not the ending offset or capacity. For an array containing only one ClassFile, use `off=0` and `len=b.length`; for a buffer with a prefix/suffix, you must use the actual payload boundaries. Beyond that, you also need to pay attention to package, version, ProtectionDomain, parent delegation, and the class loader lifecycle.

**Official documentation:**

- Java SE 17 API, `ClassLoader#defineClass`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java Virtual Machine Specification, Java SE 17, §4.1 — *The ClassFile Structure*: https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.1
- Java Virtual Machine Specification, Java SE 17, §5.3 — *Creation of Classes and Interfaces*: https://docs.oracle.com/en/java/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- Java SE 17 API, `JavaCompiler`: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
