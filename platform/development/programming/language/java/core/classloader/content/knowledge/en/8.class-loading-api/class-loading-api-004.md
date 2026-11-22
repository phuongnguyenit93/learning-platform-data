# defineClass: Creating a Class from byte[] or ByteBuffer

> **Scope:** Java Core → ClassLoader → Class Loading API. This article explains how `ClassLoader.defineClass` uses compiled bytecode to **define a new class** at runtime, how to use the two data forms `byte[]` and `ByteBuffer`, binary names, protection domains, common errors, and how to integrate with `findClass`/`loadClass`. Examples compile on Java 17+.

## 1. The Problem: Turning Bytecode into a Class<?> in the JVM

Normally, `javac` turns the source `demo.Gadget` into the file `demo/Gadget.class`; the application class loader reads the class file from the classpath when needed. However, in plugin systems, bytecode generators, loaders that read JARs from custom locations, or frameworks that load dynamically generated code, you can **own your own `ClassLoader`** and let it receive bytes at runtime.

`ClassLoader.defineClass` is the core operation:

```text
Source .java
    |
    | javac / bytecode generator
    v
Valid JVM class-file bytes       <- byte[] / ByteBuffer
    |
    | ClassLoader.defineClass(...)
    v
Class<?> defined by this loader
    |
    | linking / initialization according to their own rules
    v
Can create instances, invoke methods, and read fields via Java/Reflection
```

Points that must be distinguished:

1. `defineClass` **does not compile Java source**. The input must be valid class-file data according to the JVM format, typically starting with the magic bytes `CA FE BA BE`.
2. It **defines a class within the scope of a specific loader** and returns the corresponding `Class<?>`.
3. `defineClass` does not mean the class has been initialized, a `static` initializer has been called, or a constructor has been executed.
4. Loading (`loading`), linking (`linking`), resolution (`resolution`), and initialization (`initialization`) are distinct phases. According to the API, before using a defined class, the class needs to be linked; `loadClass(name, true)` or `resolveClass` plays a role related to linking.
5. `defineClass` must not be called a second time with the same binary name on **the same defining loader**, because the JVM does not allow the same loader to redefine a class with that name.

## 2. Key Overloads of ClassLoader.defineClass

`ClassLoader` declares **`protected final`** overloads; application Java code outside a subclass cannot call them directly at will. Custom loader authors typically create a subclass and call the method from within it.

| Short Signature | Bytecode Source | Meaning |
| --- | --- | --- |
| `defineClass(String name, byte[] b, int off, int len)` | Region of a byte array | Creates a class with the default protection domain. |
| `defineClass(String name, byte[] b, int off, int len, ProtectionDomain pd)` | Region of a byte array | Creates a class with the specified protection domain, or the default one when `pd == null`. |
| `defineClass(String name, ByteBuffer b, ProtectionDomain pd)` | Remaining portion of a buffer | Creates a class from the `position()` to `limit()` region, with the same name/package/protection domain rules. |
| `defineClass(byte[] b, int off, int len)` | Array without an explicit name | **Deprecated**; avoid using it, and pass the expected binary name instead. |

Examples of the actual API signatures (placed here as **declaration illustrations**, cannot be copied into a standalone class):

```java
protected final Class<?> defineClass(
        String name, byte[] b, int off, int len);

protected final Class<?> defineClass(
        String name, byte[] b, int off, int len,
        java.security.ProtectionDomain protectionDomain);

protected final Class<?> defineClass(
        String name, java.nio.ByteBuffer b,
        java.security.ProtectionDomain protectionDomain);
```

The return value is the `Class<?>` object of **the newly created type**, not an instance `new Gadget()`. To create an instance, code can invoke an appropriate constructor once the class is ready.

### Why protected final?

- **`protected`:** only code granted access under Java's access rules (for example, a subclass in an appropriate context) can call this method. It does not turn `defineClass` into an arbitrary public API for all callers.
- **`final`:** subclasses cannot override the JVM's class-definition mechanism; a subclass can **override `findClass`** to decide how to locate the bytes, and then call `defineClass`.
- If an application needs a public API on a custom loader, expose a clearly named wrapper method that controls the byte source and lifetime. Do not attempt to bypass JDK encapsulation using reflection on `ClassLoader#defineClass`.

## 3. byte[] Data: offset and length Represent a Specific Segment

For the overload using `byte[]`:

```java
defineClass("demo.Gadget", bytes, offset, length)
```

- `name`: **the expected binary name** of the class, for example `demo.Gadget`; for a member class, for example `demo.Outer$Inner`.
- `bytes`: the array containing the bytecode of **one complete class file**.
- `offset`: the starting index in the array.
- `length`: the number of class-file bytes to read, **not the ending index**.

Basic conditions:

```text
offset >= 0
length >= 0
offset + length <= bytes.length
```

For an array containing only the class file, pass `0` and `bytes.length`. If the bytes are placed inside a buffer/array that has a header or preceding/trailing data, pass the exact segment containing the class file; never define the custom header as well as if it were a class file.

Example:

```java
byte[] classBytes = ...;         // contains complete JVM bytecode
byte[] envelope = new byte[classBytes.length + 4];
System.arraycopy(classBytes, 0, envelope, 2, classBytes.length);

// Skip the 2-byte prefix and 2-byte suffix:
Class<?> type = defineClass(
        "demo.Gadget", envelope, 2, classBytes.length);
```

This is a **snippet inside a subclass of `ClassLoader`**; the `classBytes` variable must be supplied by the code that loads the class file. Another overload accepts a `ProtectionDomain` when you need to attach an appropriate code source/certificates/policy.

If `off` or `len` is negative, or extends out of bounds of the array, the API throws `IndexOutOfBoundsException`. If the byte segment does not represent a valid class file, it may throw `ClassFormatError`. A file with a `CAFEBABE` header can still be structurally invalid elsewhere, so checking only the first four bytes is not sufficient.

## 4. ByteBuffer: Using Exactly the Range from position to limit

The overload:

```java
defineClass("demo.Gadget", byteBuffer, protectionDomain)
```

uses the bytecode in the **remaining region** of the buffer, determined by `position()` and `limit()`. It supports heap buffers, direct buffers, buffer slices, and read-only buffers (as long as the data is valid).

With the configuration:

```text
capacity = 1200
position = 5
limit = 1105

Byte range used for defineClass: [5, 1105)
Number of bytes used: remaining() = 1100
```

Do not use `capacity()` or the entire backing array to infer the class-file data. If the buffer was just written to with `put` calls, you need to switch it to reading mode, typically with `flip()`; if there is a prefix, you must advance `position` accurately and set `limit` right after the last byte.

Example reading bytes containing a prefix/suffix:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(classBytes.length + 2);
buffer.put((byte) 1);
buffer.put(classBytes);
buffer.put((byte) 2);
buffer.flip();
buffer.position(1);
buffer.limit(1 + classBytes.length);

// ClassLoader subclass:
Class<?> clazz = defineClass("demo.Gadget", buffer, null);
```

`ByteBuffer` only describes the **byte source**; it does not let the JVM interpret "a Java file" or "multiple class files" concatenated together. The passed region must still contain exactly one class file in the JVMS format.

**Be careful with the buffer position after the call:** the `ClassLoader#defineClass(String, ByteBuffer, ProtectionDomain)` documentation describes the result as equivalent to taking the `remaining()` bytes and calling the `byte[]` overload. You should not build logic that depends on **whether `position()` on the input buffer object is guaranteed to be modified or not** across implementations or execution paths. On OpenJDK 21 in the example in Section 6, the input buffer's position remained unchanged. If the caller needs to use the buffer afterward, create a `duplicate()` or `slice()`, set the bounds explicitly, and manage the position yourself.

**Do not assume "a direct ByteBuffer is always zero-copy and faster":** the API defines the class-loading outcome; it does not promise to avoid copying the bytecode or to be superior in every case. Choose `byte[]` or `ByteBuffer` based on the available data source, clarity, and actual measurements.

## 5. Class Name: The Binary Name Must Match the Bytecode

A class file contains the internal name of the class it defines. The `name` value in `defineClass` is the **expected binary name** and, when non-null, must match the actual name in the class file.

```text
Source type:       demo.Gadget
Binary name:       demo.Gadget
JVM internal name: demo/Gadget
Resource path:     demo/Gadget.class
```

Correct:

```java
defineClass("demo.Gadget", bytes, 0, bytes.length);
```

Incorrect:

```java
defineClass("demo.Other", bytes, 0, bytes.length);   // the bytes are actually demo.Gadget
defineClass("demo/Gadget", bytes, 0, bytes.length);  // internal name
defineClass("demo/Gadget.class", bytes, 0, bytes.length); // resource path
```

In cases where the name does not match the class file, the API may throw **`NoClassDefFoundError`**. A `NoClassDefFoundError` in this situation **does not mean the class file is missing**: the file can be read, but the binary name passed in is wrong compared to the metadata in the bytecode.

`name == null` is permitted by some overloads, but **you should provide the expected name** to support consistency checking and enforce package/certificate rules properly. Do not use a null name to evade security constraints or loader structure.

## 6. Complete Hands-On Example on Java 17+: byte[] and ByteBuffer

This example creates **two runtime classes with the same binary name** using two separate loaders, using the exact bytes of `demo.Gadget`. It also observes initialization, reloading, and three error forms. No libraries outside the JDK are required.

Structure:

```text
src/demo/Gadget.java
src/app/DefineDemo.java
model/              (javac output for Gadget)
app/                (javac output for DefineDemo)
```

### File src/demo/Gadget.java

```java
package demo;

public class Gadget {
    static {
        System.out.println("Gadget initialized");
    }

    public String ping() {
        return "pong";
    }
}
```

### File src/app/DefineDemo.java

```java
import java.nio.ByteBuffer;
import java.nio.file.Files;
import java.nio.file.Path;

public class DefineDemo {
    static class BytesLoader extends ClassLoader {
        BytesLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }

        Class<?> fromArray(String name, byte[] bytes, int offset, int length) {
            return defineClass(name, bytes, offset, length);
        }

        Class<?> fromBuffer(String name, ByteBuffer bytes) {
            return defineClass(name, bytes, null);
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] image = Files.readAllBytes(
                Path.of("model/demo/Gadget.class"));

        byte[] padded = new byte[image.length + 4];
        System.arraycopy(image, 0, padded, 2, image.length);

        BytesLoader arrayLoader = new BytesLoader();
        Class<?> first = arrayLoader.fromArray(
                "demo.Gadget", padded, 2, image.length);

        System.out.println("array defined: " + first.getName());
        System.out.println("array loader owned: "
                + (first.getClassLoader() == arrayLoader));
        System.out.println("loadClass returns same: "
                + (arrayLoader.loadClass("demo.Gadget") == first));
        System.out.println("initialize next:");
        Object gadget = first.getDeclaredConstructor().newInstance();
        System.out.println("method: "
                + first.getMethod("ping").invoke(gadget));

        ByteBuffer direct = ByteBuffer.allocateDirect(image.length + 2);
        direct.put((byte) 1).put(image).put((byte) 2).flip();
        direct.position(1);
        direct.limit(1 + image.length);

        BytesLoader bufferLoader = new BytesLoader();
        Class<?> second = bufferLoader.fromBuffer("demo.Gadget", direct);
        System.out.println("buffer defined: " + second.getName());
        System.out.println("buffer remaining preserved: "
                + (direct.position() == 1));
        System.out.println("same binary name: "
                + first.getName().equals(second.getName()));
        System.out.println("same runtime type: " + (first == second));

        try {
            arrayLoader.fromArray("demo.Gadget", image, 0, image.length);
        } catch (LinkageError expected) {
            System.out.println("duplicate define: LinkageError");
        }

        try {
            new BytesLoader().fromArray(
                    "demo.Other", image, 0, image.length);
        } catch (NoClassDefFoundError expected) {
            System.out.println("wrong expected name: NoClassDefFoundError");
        }

        try {
            new BytesLoader().fromArray(
                    "demo.Bad", new byte[]{1, 2, 3}, 0, 3);
        } catch (ClassFormatError expected) {
            System.out.println("invalid bytes: ClassFormatError");
        }
    }
}
```

**Compile/run from the parent directory** containing `src` (do not put `model` on the application classpath):

```bash
javac -d model src/demo/Gadget.java
javac -d app src/app/DefineDemo.java
java -cp app DefineDemo
```

**Verified output on OpenJDK 21:**

```text
array defined: demo.Gadget
array loader owned: true
loadClass returns same: true
initialize next:
Gadget initialized
method: pong
buffer defined: demo.Gadget
buffer remaining preserved: true
same binary name: true
same runtime type: false
duplicate define: LinkageError
wrong expected name: NoClassDefFoundError
invalid bytes: ClassFormatError
```

### Why Is the Result Like This?

- `arrayLoader` defines `demo.Gadget` from the **segment** `padded[2 ... 2+image.length)`; `bufferLoader` defines a class with the same name from the `position..limit` range in a **direct ByteBuffer**.
- The two `Class<?>` objects have the same `getName()` but **do not share the same identity**, because their defining loaders differ. The JVM identifies an ordinary class/interface by the pair `(binary name, defining loader)`.
- After `defineClass` returns, `first.getName()` and `loadClass("demo.Gadget")` do not run the static initializer. The `getDeclaredConstructor().newInstance()` call that creates the instance causes `Gadget initialized` to appear.
- The base class's `loadClass` overload checks whether the class has already been loaded, so loading it again through **the same loader** returns the same `Class<?>`.
- Calling `defineClass` again directly for a class with the same binary name on `arrayLoader` violates identity rules and causes `LinkageError`. Real code should not catch this error and try to define the class again.
- Passing `demo.Other` for the actual bytecode of `demo.Gadget` causes `NoClassDefFoundError` due to **wrong name**, not "file not found".
- The bytes `{1,2,3}` are not a class file, so they cause `ClassFormatError`.
- `buffer remaining preserved: true` is **an observation from the tested runtime environment**, not a universal guarantee that the input `ByteBuffer` object will keep its position unchanged across all implementations.

The example intentionally calls `defineClass` directly through a wrapper to make the behavior clear; in a real loader, it should be combined with `findClass` and the `loadClass` path to manage caching, delegation, and concurrent loading.

## 7. Proper Integration into findClass and loadClass

Normally, application code requests:

```java
Class<?> type = customLoader.loadClass("demo.Gadget");
```

The default `ClassLoader.loadClass(String, boolean)` (when not overridden by a subclass) executes the following flow:

```text
loadClass(binaryName)
    |
    | synchronized(getClassLoadingLock(binaryName))
    v
findLoadedClass(binaryName)
    |
    +-- already recorded -> return Class<?>
    |
    +-- not yet recorded -> try parent.loadClass(binaryName)
                                |
                                +-- parent found it -> return parent's Class<?>
                                |
                                '-- parent did not find it -> findClass(binaryName)
                                                               |
                                                               '-- read class bytes
                                                                   defineClass(...)
```

If the `resolve` parameter of the protected overload is `true`, the standard path also calls `resolveClass` after obtaining the matching `Class<?>`.

**Design point:** custom loader authors typically override **`findClass`**, because the default `loadClass` already manages `findLoadedClass`, parent delegation, and synchronization. You usually do not need to override `loadClass` yourself just to handle reading bytes from a new source.

The following skeleton illustrates the integration (it is not a standalone program because `readBytesFor` must be supplied by the application):

```java
public final class RepositoryClassLoader extends ClassLoader {
    public RepositoryClassLoader(ClassLoader parent) {
        super(parent);
    }

    @Override
    protected Class<?> findClass(String binaryName)
            throws ClassNotFoundException {
        byte[] bytes = readBytesFor(binaryName);
        if (bytes == null) {
            throw new ClassNotFoundException(binaryName);
        }
        return defineClass(binaryName, bytes, 0, bytes.length);
    }

    private byte[] readBytesFor(String binaryName) {
        // Real application example: read from an archive, database, or bytecode generator.
        throw new UnsupportedOperationException("implement source lookup");
    }
}
```

The `readBytesFor` method is intentionally unimplemented; this is an **architectural pattern**, not an immediately runnable example. In a real production system, you need to handle I/O, size limits, checksums/signatures, package metadata, and ownership of the bytes.

If you override `loadClass` to intentionally apply child-first loading, you must preserve the rules for reusing already-loaded types, class-loading locks, lookup/delegation order, resolve decisions, and loading constraints. Calling `defineClass` multiple times for the same name on the same loader does not create a new version of the class; it causes an error.

### Multiple Threads Requesting the Same Name

Two threads can concurrently call `loadClass("demo.Gadget")`. The default path uses `getClassLoadingLock(name)` to avoid a *double define* race.

For custom loaders that want to support loading multiple names in parallel, Java provides `registerAsParallelCapable()` with registration rules when the class loader subclass is initialized. Do not enable parallelism and replace synchronization with an unsafe boolean variable. Class types defined by the JVM must be managed consistently when multiple threads look them up concurrently.

## 8. ProtectionDomain, Package, and Code Source

The overloads with `ProtectionDomain` allow associating protection domain information with a runtime class:

```java
defineClass(binaryName, bytes, 0, bytes.length, protectionDomain);
defineClass(binaryName, byteBuffer, protectionDomain);
```

`protectionDomain == null` means using the default protection domain of the corresponding overload. `ProtectionDomain` can carry a `CodeSource`, certificates, and related access/policy information. This is platform metadata and protection machinery; it is not a simple "trusted bytes" flag or a safety tool for running malicious bytecode inside the same JVM.

Package relationships:

- `defineClass` can define a `Package` in the loader if the corresponding package has not yet been defined in that loader.
- A **runtime package** is identified by the package name combined with the defining loader; two loaders defining the same package name string still result in two different runtime packages.
- When using overloads with a domain/certificate, **the first class in the package determines the set of certificates** that subsequent classes in the same package/loader must match. A violation can cause `SecurityException`.
- Package sealing and version information taken from the manifest are the responsibility of an appropriate loader/packaging system. `URLClassLoader` handles many of these details for standard JARs; a loader that simply calls `defineClass` from raw bytes does not automatically emulate all JAR manifest rules.
- A loader cannot arbitrarily define classes whose binary name starts with `java.` as application classes; the API enforces security restrictions and may throw `SecurityException`.

Do not use `defineClass(null, ...)` to bypass checks on the binary name, certificates, or namespace. When the class name is known, always supply the correct name.

## 9. Errors and How to Diagnose Them

| Symptom / Error | Common Cause | How to Handle |
| --- | --- | --- |
| `ClassFormatError` | Bytes are not a valid class file, are truncated, or have a corrupted structure. | Check the magic bytes, class file length, compiler/generator source, and JVM structure. |
| `UnsupportedClassVersionError` | The class file was compiled for a newer JVM version than the runtime supports. | Compare `javac --release`, the bytecode major version, and the runtime JDK. This is a subclass of `ClassFormatError`. |
| `NoClassDefFoundError: wrong name` | The `name` passed to `defineClass` does not match the binary name in the class file. | Use dots for packages and `$` for member classes, and inspect with `javap -v`. |
| `IndexOutOfBoundsException` | `offset`/`length` fall outside the `byte[]` bounds. | Check the bounds and avoid confusing length with end index. |
| `LinkageError` on duplicate define | The same defining loader already has a class with the same binary name. | Go through `loadClass`/`findLoadedClass` and do not attempt to redefine it. |
| `SecurityException` | Violation of the `java.` namespace or inconsistent certificate sets within the package. | Choose a valid name and handle the code source and package metadata properly. |
| `ClassNotFoundException` | `findClass` could not locate the bytecode source and the loader chain does not have that class. | Check the source lookup, binary name, and parent delegation. |
| `NoClassDefFoundError` on subsequent use | A dependent class may be missing or a previous initialization failed. | Inspect the message and `Caused by`, distinguishing wrong name from missing dependencies. |
| `VerifyError` | The bytecode violates verification constraints. | Check the generator, stack map frames, typing, and compiler target. |
| `ClassCastException` between two classes with the same name | Two separate defining loaders produced two different runtime types. | Share the API via a parent loader and inspect `clazz.getClassLoader()`. |

Some linkage errors may only manifest when the class is **linked or used**, not necessarily immediately inside `defineClass`. Do not treat the success of `defineClass` as proof verifying all dependencies, access permissions, logical correctness, or application readiness.

### Distinguishing Class Names and Class Sources

- `binary name`: `demo.Gadget` → parameter of `defineClass`.
- `internal name`: `demo/Gadget` → inside the class-file constant pool.
- `resource path`: `demo/Gadget.class` → path used to locate the bytes.
- `Class.getName()` returns the appropriate name for observing ordinary classes; `Class.getClassLoader()` indicates the defining loader of that class.

Do not pass a resource path to `defineClass`, and do not take the filename on disk as proof that the class file contains the same binary name.

## 10. When Should You Use or Avoid defineClass?

**Appropriate when** you are implementing a custom class loader that loads bytecode from a repository, database, network, generator, plugin archive, or another well-defined byte source; you control the identity, parent, package, source, and timing of class loading.

**Not needed when** the class is already on the classpath/module path: `Class.forName`, `ClassLoader.loadClass`, or reflection is usually sufficient. If you only want to add a JAR/directory to a separate namespace, `URLClassLoader` with the appropriate URLs and parent already handles the bytecode source for you.

**Do not use it to "overwrite an existing class"**: the same binary name on the same defining loader cannot be defined a second time. Hot-reload needs typically create a new loader, clear references to the old loader, or use the instrumentation API within its own limits. Bytecode from untrusted sources can affect JVM/application safety; appropriate source controls and execution boundaries must be applied, without assuming `ProtectionDomain` guarantees a sandbox in all modern Java versions.

A practical implementation checklist:

1. Validate the source and length of the class bytes; accept only properly formatted class files.
2. Determine the **binary name** before defining, and verify that the name matches the class bytes.
3. Choose an appropriate parent loader to avoid API duplication and incorrect class identity.
4. Use `findClass` and the `loadClass` path to prevent duplicate definition/races.
5. Attach package/protection domain/certificate/code source information when required by the use case.
6. Distinguish bytecode reading errors from linkage, verification, and initialization errors; preserve the `cause` when wrapping `IOException` into `ClassNotFoundException`.
7. For dynamic plugin sources, manage loader lifecycle, caching, references, and unload/upgrade strategies; do not assume `close()` or discarding bytes causes the JVM to immediately reclaim the class.

## 11. Self-Check Questions

1. **Does `defineClass` accept Java source from a string?**  
   No. It accepts valid JVM class-file bytes; compiling source code requires a compiler or a separate bytecode generation tool.
2. **What is the difference between `off=2,len=100` and `off=2,len=102`?**  
   The `len` value is the number of bytes starting from `off`. If the class file inside the envelope is 100 bytes long, use `2,100`; passing `102` will read extra bytes or go out of bounds depending on the array length.
3. **If a `ByteBuffer` has a 200-byte capacity but `position=10,limit=110`, how many bytes are used?**  
   100 bytes, in the range `[10,110)`.
4. **Can the same `demo.Gadget` be defined by two different loaders?**  
   Yes. They are two separate runtime types because their `(binary name, defining loader)` pairs differ.
5. **Does defining the same name twice in the same loader create a newly updated version?**  
   No. It violates the class identity rule and typically throws `LinkageError`.
6. **When passing `name="demo.Other"` while the bytes contain `demo.Gadget`, which error is expected?**  
   `NoClassDefFoundError`, because the expected name does not match the bytes.
7. **Does simply calling `defineClass` run `static { ... }` in the class?**  
   It does not automatically perform initialization; an active use (such as calling a constructor) is what typically triggers initialization under JVM rules.
8. **Should you override `loadClass` to load bytes from a file?**  
   Usually you only need to override `findClass`; the default `loadClass` already handles checking recorded loaded classes, parent delegation, and synchronization.
9. **What is the benefit of the `ByteBuffer` overload?**  
   It directly passes a data source already represented by a buffer; the read region is determined by `position/limit`. There is no general performance or zero-copy guarantee.
10. **Does ProtectionDomain turn unfamiliar bytecode into completely safe code?**  
    No. It attaches protection metadata and has package/certificate rules; designing a security boundary requires other appropriate mechanisms.

## 12. Official References

- [Java SE 21 API — ClassLoader.defineClass](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): `byte[]`, `ByteBuffer`, and `ProtectionDomain` overloads, names, and exceptions.
- [Java SE 21 API — SecureClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/SecureClassLoader.html): overloads using `CodeSource`.
- [Java SE 21 API — ByteBuffer](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): `position`, `limit`, `remaining`, `flip`, `slice`, `duplicate`.
- [JVMS 4 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html): class-file structure and version.
- [JVMS 5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3): class identity by binary name and defining loader.
- [JLS 12 — Execution](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html): loading, linking, and initializing classes.
