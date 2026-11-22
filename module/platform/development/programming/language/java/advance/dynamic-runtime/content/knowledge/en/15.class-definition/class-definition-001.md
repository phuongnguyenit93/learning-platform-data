# 15.1 The chain of generating valid bytecode, defining a class, initializing, and invoking new code

In Java, it is possible to create **a class that did not exist in the source code when the program started**, load that class definition into the JVM, then instantiate objects and invoke new methods. This chain is commonly found in runtime frameworks, dynamic languages running on the JVM, proxy/code generation, rule engines, and *runtime compilation* systems.

The core point is not just "having a `byte[]` array and calling `defineClass`". That array must represent a **valid classfile** with proper metadata, constant pool, method signatures, and bytecode; the class must be defined in an **appropriate class loader/module/package**; the JVM also performs linking and verification; only after that can you **initialize the class, create an instance, and execute methods**. Each stage has its own errors and success conditions.

This article focuses on the entire path:

~~~text
Class description / source / bytecode builder
                    │
                    ▼
     Generate valid .class content
                    │
                    ▼
       byte[] containing classfile
                    │
       check basic structure
                    │
                    ▼
           Define the class
       Lookup.defineClass(bytes)
            or ClassLoader
                    │
                    ▼
       Class<?> representing class
                    │
         linking / verification
                    │
                    ▼
      Initialize class (<clinit>)
           (when required)
                    │
                    ▼
    Create object (constructor <init>)
                    │
                    ▼
   Invoke new code via Reflection /
      MethodHandle / interface
~~~

The self-contained programs run on **JDK 17+**, without needing external libraries. The first example uses the JDK's `JavaCompiler` to generate valid bytecode in memory, then uses `MethodHandles.Lookup.defineClass`. The second example manually builds a **minimal binary classfile** using `DataOutputStream`, defines it via a custom `ClassLoader`, instantiates an instance, and invokes the new method. Writing bytecode manually is only for learning the structure; production should prefer a compiler or a battle-tested bytecode generation library.

## 1. Where does a new class actually start?

There are three concepts that should not be mixed up:

- **Java source code**: a string with syntax like `public class Greeter { ... }`. A normal JVM **does not load source strings directly** to create a class; there must be a compilation or classfile generation step.
- **Classfile**: a byte sequence following the JVM Class File Format. It starts with the magic `0xCAFEBABE`, contains version information, constant pool, access flags, this/super class, field/method/attribute lists, and `Code` attributes containing bytecode instructions.
- **JVM-defined class**: a runtime entity represented by a `Class<?>`, associated with a **defining class loader** and module/package rules. Two classes having the same apparent name does not prove they are the same type if their loaders differ.

For example, a classfile with the binary name `runtime.GeneratedMultiplier` uses an internal name in the constant pool:

~~~text
binary name (Java API): runtime.GeneratedMultiplier
internal JVM name:     runtime/GeneratedMultiplier
class descriptor:      Lruntime/GeneratedMultiplier;
~~~

A valid `byte[]` array is the **input** to class definition, not an already-created object. Only when `defineClass` returns `Class<?>` successfully does the JVM have the corresponding class definition. Calling a constructor is yet another stage.

### "Generating bytecode" can take multiple paths

| Path to create byte[] | Characteristics | When appropriate |
| --- | --- | --- |
| `javac` or `javax.tools.JavaCompiler` | Compiles valid source into a classfile; the compiler automatically generates the constant pool, stack maps, and bytecode | When the new class can be expressed as Java source |
| Dedicated bytecode libraries like ASM/Byte Buddy | Provides APIs to build/transform classfiles, supporting low-level JVM manipulation | Complex frameworks/code generators |
| Writing a classfile manually with `DataOutputStream` | Directly responsible for every index, length, opcode, and verification constraint | Learning classfile structure or extremely constrained problems |
| Reading a pre-compiled classfile | Does not generate new bytecode; only loads an unloaded definition | Plugins/extensions with pre-existing class bytes |

Not all code generation requires `invokedynamic`. `invokedynamic` relates to a **call site** with bootstrap/linkage; whereas `defineClass` relates to **defining a new type**. The two mechanisms can work together in a framework, but they are not synonymous.

## 2. Minimum conditions for valid bytecode

A classfile is not arbitrary data ending in `.class`. It must comply with the JVM Class File Format and semantic/verifier constraints.

**Header:** the first four bytes are `CA FE BA BE`, followed by two bytes of `minor_version` and two bytes of `major_version`. Java 17 corresponds to major version **61** (decimal). Do not infer the Java version from the byte array length; read the exact header position.

**Constant pool:** a one-based table, with `constant_pool_count` including unused slot 0. Entries such as `CONSTANT_Utf8`, `CONSTANT_Class`, `CONSTANT_NameAndType`, and `CONSTANT_Methodref` reference each other by index. Referencing the wrong constant kind or an out-of-bounds index results in an invalid classfile.

**Class metadata:** `access_flags` indicates class/interface/public/final...; `this_class` and `super_class` must reference valid `CONSTANT_Class` entries. Internal names use forward slashes `/`. Normal classes have a super class (except `java/lang/Object`).

**Method descriptors:** accurately describe input/output types. For example, `()V` is a method with no parameters returning `void`; `(I)I` takes an `int` and returns an `int`. Do not put `(int)int` into the constant pool as a JVM descriptor; that notation is only a convenient way to read it in Java.

**Code attribute:** a method with code must declare `max_stack`, `max_locals`, `code_length`, the bytecode bytes, an exception table, and a list of sub-attributes. The `max_stack` value must be sufficient for the operand stack depth; `max_locals` must hold the receiver at slot 0 for instance methods and the parameters, including cases where `long`/`double` occupy two slots.

**Control flow and verifier:** bytecode must not only be syntactically valid, but must also have consistent stack types, branch targets, value types, and object initialization rules. For newer classfile versions, complex branches usually require an appropriate `StackMapTable`. The manually written classfile example in this article has **straight-line flow with no branches**, so it can use a minimal Code attribute without manually building stack map frames.

**Access rights:** you cannot make a class valid by bypassing package/module, superclass access, or access permissions. These errors can occur during verification, preparation, resolution, initialization, or method invocation depending on the situation.

Common errors are analyzed in a later section; first, we need a way to generate `byte[]` where the compiler guarantees validity.

## 3. Separating loading, linking, initialization, and instantiation

Java defines distinct phases for a class:

| Phase | What happens? | What must not be assumed |
| --- | --- | --- |
| **Loading/definition** | Finds/receives binary representation, brings class into the JVM, produces `Class<?>` | That constructors have run |
| **Verification** | Checks bytecode and type-safety constraints | That the method's business logic is necessarily correct |
| **Preparation** | Allocates/sets default values for static fields per JVM mechanics | That the static initializer in source has run |
| **Resolution** | Converts symbolic references to runtime references when needed | That all dependent links must be completely resolved immediately |
| **Initialization** | Executes the class initializer `<clinit>` if present, per JVM rules | That it is synonymous with creating an instance |
| **Instantiation** | Creates an object, allocates and runs constructor `<init>` | That each class has only one instance |
| **Invocation** | Calls a method on an object or calls a static method | That access rights, parameter types, and exceptions can be ignored at call time |

The exact order and timing of loading/linking/resolution may be performed *lazily* by the JVM according to the specification. `Lookup.defineClass` does not by itself require running the class initializer. To force initialization, you can use `Class.forName(name, true, loader)` or an operation that triggers initialization per Java semantics, such as creating an object via a constructor.

**Class name and object:** `Class<?> generated` is the metadata handle of the type; `Object instance = constructor.newInstance(...)` is an instance of that type. Keeping the two variables separate helps avoid the misconception that "defineClass already created the object".

## 4. Choosing a class-definition API

### A. MethodHandles.Lookup.defineClass(byte[])

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> defined = lookup.defineClass(bytes);
~~~

This is an **illustrative snippet**, requiring `import java.lang.invoke.MethodHandles`, a `bytes` variable holding a valid classfile, and an appropriate context. Available since Java 9, this API allows defining a **named class** from `byte[]` in the same runtime package as the lookup class and under appropriate access permissions. The lookup must have **PACKAGE** access; you cannot use a lookup from an arbitrary package to secretly define a class in another package.

In an example in the **default package**, a lookup obtained from `CompileAndDefineDemo` will define the new class `GeneratedGreeter` also in the default package, with the appropriate class loader/module. If the classfile is named `other.pkg.GeneratedGreeter`, then `lookup.defineClass(bytes)` cannot arbitrarily place that name into another package.

`defineClass` returns `Class<?>`, **without initializing the class merely by the act of defining it**; `static { ... }` code does not necessarily run yet. Initialization can be requested explicitly afterward.

### B. ClassLoader.defineClass(...)

~~~java
static class ByteLoader extends ClassLoader {
    ByteLoader(ClassLoader parent) {
        super(parent);
    }

    Class<?> define(String binaryName, byte[] bytes) {
        return defineClass(binaryName, bytes, 0, bytes.length);
    }
}
~~~

This is an **illustrative class snippet**, which must be placed in a valid class/file and passed the correct `binaryName`. `ClassLoader#defineClass` is a **protected** method, typically used in a custom loader subclass. It can define a class from a byte array by binary name; the JVM checks the name, structure, and related constraints. It is **not** a way to bypass the verifier.

A class is identified by **(binary name, defining loader)**. Two `Class<?>` objects both named `runtime.GeneratedMultiplier` but with different loaders are **two different types** at runtime. Using `instanceof`/casting between two loader worlds is not allowed just because the text names match.

### C. defineHiddenClass, a different goal from this article

`Lookup.defineHiddenClass(...)` can be used for certain kinds of classes supporting runtime code generation with different identity/discoverability from named classes. Hidden classes have different naming/lookup and class-loading rules, and are not a direct replacement when you need a **named class** that can be looked up via `Class.forName("pkg.Name")`. In this article, we intentionally use a **named class** to observe the full chain define → initialize → instantiate → invoke.

### D. Do not choose a loader arbitrarily

If a framework wants to define a class in the same package/module and interact directly with permitted members, `Lookup.defineClass` has the advantage of access rights matching the lookup. If you want to isolate versions/plugins or create a separate namespace, a dedicated `ClassLoader` is more appropriate; in that case you must design delegation, parent loader, visibility, package, module, and lifecycle. Do not apply reflection tricks to call `ClassLoader.defineClass` on an arbitrary loader to bypass JDK encapsulation.

## 5. Complete example 1 — compiling Java source to byte[] in memory

This example uses the **JDK JavaCompiler API**, writing no `GeneratedGreeter.class` file to disk at all. The program:

1. Writes the `GeneratedGreeter` class source code into a `String`.
2. Uses `JavaCompiler` and a `JavaFileManager` that receives bytecode into a `ByteArrayOutputStream`.
3. Checks that the generated file has magic `CAFEBABE`.
4. Uses `MethodHandles.lookup().defineClass(bytes)`.
5. Explicitly triggers `<clinit>` using `Class.forName(..., true, ...)`.
6. Creates an object via the constructor.
7. Invokes `greet` using Reflection and using `MethodHandle`.

**This is a standalone Java 17+ program**, requiring no Maven/Gradle/ASM. Create the file **CompileAndDefineDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.net.URI;
import java.nio.ByteBuffer;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileAndDefineDemo {
    static final class SourceFile extends SimpleJavaFileObject {
        private final String source;

        SourceFile(String binaryName, String source) {
            super(URI.create("string:///" + binaryName
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    static final class ClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output =
                new ByteArrayOutputStream();

        ClassFile(String binaryName, Kind kind) {
            super(URI.create("memory:///" + binaryName + kind.extension),
                    kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return output;
        }

        byte[] bytes() {
            return output.toByteArray();
        }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassFile> compiled = new HashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {
            ClassFile file = new ClassFile(className, kind);
            compiled.put(className, file);
            return file;
        }

        byte[] getBytes(String className) {
            ClassFile file = compiled.get(className);
            if (file == null) {
                throw new IllegalStateException("No class: " + className);
            }
            return file.bytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        String className = "GeneratedGreeter";

        String source = """
                public class GeneratedGreeter {
                    static {
                        System.out.println("generated: initialized");
                    }

                    private final String prefix;

                    public GeneratedGreeter(String prefix) {
                        this.prefix = prefix;
                    }

                    public String greet(String name) {
                        return prefix + name;
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run using a full JDK");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        byte[] bytes;
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, null)) {
            MemoryFileManager files = new MemoryFileManager(standard);
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new SourceFile(className, source)));

            boolean compiled = Boolean.TRUE.equals(task.call());
            if (!compiled) {
                for (Diagnostic<? extends JavaFileObject> diagnostic :
                        diagnostics.getDiagnostics()) {
                    System.err.println(diagnostic);
                }
                throw new IllegalStateException("Compilation failed");
            }
            bytes = files.getBytes(className);
        }

        System.out.println("compiled: " + (bytes.length > 0));
        System.out.printf("magic: %08X%n",
                ByteBuffer.wrap(bytes).getInt());

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Class<?> generated = lookup.defineClass(bytes);
        System.out.println("defined: " + generated.getName());

        System.out.println("request initialization");
        Class.forName(
                generated.getName(), true, generated.getClassLoader());

        Object instance = generated
                .getDeclaredConstructor(String.class)
                .newInstance("Hi ");

        Method greet = generated.getMethod("greet", String.class);
        System.out.println("reflect: " + greet.invoke(instance, "Lan"));

        MethodHandle handle = lookup.findVirtual(
                generated,
                "greet",
                MethodType.methodType(String.class, String.class));
        System.out.println("handle type: " + handle.type());
        System.out.println("handle: " +
                handle.invokeWithArguments(instance, "Minh"));
    }
}
~~~

Save and execute:

~~~bash
javac CompileAndDefineDemo.java
java CompileAndDefineDemo
~~~

Expected stdout on **JDK 17+**:

~~~text
compiled: true
magic: CAFEBABE
defined: GeneratedGreeter
request initialization
generated: initialized
reflect: Hi Lan
handle type: (GeneratedGreeter,String)String
handle: Hi Minh
~~~

### Line-by-line breakdown

- `compiled: true`: JavaCompiler produced a classfile and memory received `byte[]`. Successful compilation shows that the Java source is valid under `--release 17`, but has not yet checked all class-loading policies of the host program.
- `magic: CAFEBABE`: reads the first four bytes with `ByteBuffer` in default big-endian byte order. This is an **identification check**, not a full classfile check.
- `defined: GeneratedGreeter`: `Lookup.defineClass` created a named class definition in the same runtime package as `CompileAndDefineDemo`. No `GeneratedGreeter` object is needed yet.
- `request initialization` appears **before** the line `generated: initialized`. The call `Class.forName(..., true, ...)` requests class initialization and executes the static initializer once for that class in the corresponding class loader.
- `reflect: Hi Lan`: constructor `GeneratedGreeter(String)` creates an object with `prefix="Hi "`; `Method.invoke` calls the instance method on the object.
- `handle type: (GeneratedGreeter,String)String`: `findVirtual` creates a handle whose first parameter is the `GeneratedGreeter` receiver, even though the method source only declares one `String` parameter. If `bindTo(instance)` is used, the new handle will take only `String`.
- `handle: Hi Minh`: `invokeWithArguments` can invoke the handle with the supplied values; it uses the standard argument conversion mechanism of method handles. `invokeExact` requires an exact static call-site signature match, which is not directly suitable when we only hold the receiver as type `Object` without an adapter.

**Why not use `Class.forName("GeneratedGreeter")` from the start?** Before defining the class, a normal loader does not know that name if there is no classfile on the classpath. After `lookup.defineClass(bytes)` succeeds, we can use `generated.getClassLoader()` itself to locate the newly defined class.

**Why does `GeneratedGreeter` have no `package`?** So that the example in the **default package** can use `CompileAndDefineDemo`'s lookup without needing package files/directories. For production code, use a named package and ensure the new class is in the same runtime package as the lookup as required by `Lookup.defineClass`.

### When a single compilation produces multiple classfiles

The example only has one class to load. Java code with nested classes or multiple top-level classes can validly produce **multiple classfiles**. `MemoryFileManager` stores them by binary name; in that case, the framework must manage each class `byte[]` and define the necessary classes in the appropriate loader. Do not assume the compiler always returns a single class file just because the input is a single source string.

## 6. Creating and initializing a class are two different things

Suppose a class has a static initializer:

~~~java
static {
    System.out.println("class initialized");
}
~~~

This is an **illustrative class member snippet**, not a complete class. Distinguish:

~~~text
defineClass(bytes)
    => class is defined
    => does not automatically require running the static initializer

Class.forName(binaryName, true, loader)
    => requests class initialization
    => executes <clinit> if needed

getDeclaredConstructor(...).newInstance(...)
    => creates object, runs constructor
    => class must be initialized before creating an object

method.invoke(object, ...)
    => runs method on an existing instance
~~~

A few subtle points:

- **Loading** and **initialization** are not synonymous. `Class.forName(name, false, loader)` can find/load a class without requesting initialization; `true` requests initialization.
- **Initialization normally happens once per class definition** if successful, not once per object creation. If you create two instances, the constructor runs twice, while the static initializer does not run twice because of that.
- If `<clinit>` fails, the JVM may throw `ExceptionInInitializerError` (or propagate the appropriate `Error`). Subsequent uses may encounter `NoClassDefFoundError` because the class is in an erroneous state, rather than re-running the initializer.
- `Class<?>` does not imply there is a public/no-arg constructor. `getDeclaredConstructor(...)` must find the exact signature; accessing non-public members also involves access/module permissions.
- When `newInstance` invokes a constructor and the constructor throws an exception, Reflection typically provides an `InvocationTargetException`; check `getCause()` to see the real constructor error.

To verify the order, use a class with a static block printing one line and a constructor printing another line. Do not rely on static initializer side effects as a timing gauge for correctness; the order can be affected by other operations triggering initialization in the program.

## 7. Complete example 2 — manually building a well-formed binary classfile

In the second example, we **do not compile source**. We create bytes according to the JVM Class File Format and pass them into a custom `ClassLoader`. The created class has the binary name `runtime.GeneratedMultiplier`:

~~~java
package runtime;

public class GeneratedMultiplier {
    public GeneratedMultiplier() {
        super();
    }

    public int twice(int value) {
        return value * 2;
    }
}
~~~

This is the **behaviorally equivalent source code**, **no separate file needs to be created**. The program below directly generates the classfile containing the constructor and `twice` method at the bytecode level, without using the source above.

Create the file **HandmadeBytecodeDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;

public class HandmadeBytecodeDemo {
    private static final String BINARY_NAME =
            "runtime.GeneratedMultiplier";

    static class ByteLoader extends ClassLoader {
        ByteLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(byte[] classfile) {
            return defineClass(
                    BINARY_NAME, classfile, 0, classfile.length);
        }
    }

    // Constant-pool helpers.
    static void utf8(DataOutputStream out, String value)
            throws IOException {
        out.writeByte(1);     // CONSTANT_Utf8
        out.writeUTF(value);  // modified UTF-8 length + payload
    }

    static void cpClass(DataOutputStream out, int nameIndex)
            throws IOException {
        out.writeByte(7);     // CONSTANT_Class
        out.writeShort(nameIndex);
    }

    static void nameAndType(
            DataOutputStream out, int nameIndex, int typeIndex)
            throws IOException {
        out.writeByte(12);    // CONSTANT_NameAndType
        out.writeShort(nameIndex);
        out.writeShort(typeIndex);
    }

    static void methodRef(
            DataOutputStream out, int ownerIndex, int nameTypeIndex)
            throws IOException {
        out.writeByte(10);    // CONSTANT_Methodref
        out.writeShort(ownerIndex);
        out.writeShort(nameTypeIndex);
    }

    static void writeMethod(
            DataOutputStream out,
            int flags,
            int nameIndex,
            int descriptorIndex,
            byte[] code,
            int maxStack,
            int maxLocals) throws IOException {
        out.writeShort(flags);
        out.writeShort(nameIndex);
        out.writeShort(descriptorIndex);
        out.writeShort(1); // one method attribute: Code

        out.writeShort(9);  // "Code" in constant pool
        out.writeInt(12 + code.length);
        out.writeShort(maxStack);
        out.writeShort(maxLocals);
        out.writeInt(code.length);
        out.write(code);
        out.writeShort(0); // exception_table_length
        out.writeShort(0); // Code.attributes_count
    }

    static byte[] buildClassfile() throws IOException {
        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(memory);

        out.writeInt(0xCAFEBABE);
        out.writeShort(0);   // minor version
        out.writeShort(61);  // major: Java 17
        out.writeShort(12);  // constant_pool_count, indexes 1..11

        // #1 Utf8 runtime/GeneratedMultiplier
        utf8(out, "runtime/GeneratedMultiplier");
        // #2 Class #1
        cpClass(out, 1);
        // #3 Utf8 java/lang/Object
        utf8(out, "java/lang/Object");
        // #4 Class #3
        cpClass(out, 3);
        // #5 Utf8 <init>
        utf8(out, "<init>");
        // #6 Utf8 ()V
        utf8(out, "()V");
        // #7 NameAndType #5:#6
        nameAndType(out, 5, 6);
        // #8 Methodref #4:#7 = Object.<init>:()V
        methodRef(out, 4, 7);
        // #9 Utf8 Code
        utf8(out, "Code");
        // #10 Utf8 twice
        utf8(out, "twice");
        // #11 Utf8 (I)I
        utf8(out, "(I)I");

        out.writeShort(0x0021); // ACC_PUBLIC | ACC_SUPER
        out.writeShort(2);      // this_class = #2
        out.writeShort(4);      // super_class = #4
        out.writeShort(0);      // interfaces_count
        out.writeShort(0);      // fields_count
        out.writeShort(2);      // methods_count

        // public <init>()V:
        //   aload_0; invokespecial #8; return
        byte[] constructor = {
                (byte) 0x2A, (byte) 0xB7, 0x00, 0x08, (byte) 0xB1
        };
        writeMethod(out, 0x0001, 5, 6, constructor, 1, 1);

        // public twice(I)I:
        //   iload_1; iconst_2; imul; ireturn
        byte[] twice = {
                (byte) 0x1B, (byte) 0x05,
                (byte) 0x68, (byte) 0xAC
        };
        writeMethod(out, 0x0001, 10, 11, twice, 2, 2);

        out.writeShort(0); // class attributes_count
        out.flush();
        return memory.toByteArray();
    }

    public static void main(String[] args) throws Throwable {
        byte[] classfile = buildClassfile();

        System.out.printf("magic: %08X%n",
                ByteBuffer.wrap(classfile).getInt());
        System.out.println("major: " +
                Short.toUnsignedInt(
                        ByteBuffer.wrap(classfile, 6, 2).getShort()));

        ByteLoader loader = new ByteLoader(
                HandmadeBytecodeDemo.class.getClassLoader());
        Class<?> generated = loader.define(classfile);

        System.out.println("defined: " + generated.getName());
        System.out.println("custom loader: " +
                (generated.getClassLoader() == loader));

        Object instance = generated.getDeclaredConstructor().newInstance();
        System.out.println("instance: " +
                instance.getClass().getName());

        Method twice = generated.getMethod("twice", int.class);
        System.out.println("reflect: " + twice.invoke(instance, 21));

        MethodHandle handle = MethodHandles.publicLookup().findVirtual(
                generated,
                "twice",
                MethodType.methodType(int.class, int.class));
        System.out.println("handle: " +
                handle.invokeWithArguments(instance, 15));
    }
}
~~~

Compile and run:

~~~bash
javac HandmadeBytecodeDemo.java
java HandmadeBytecodeDemo
~~~

Expected stdout:

~~~text
magic: CAFEBABE
major: 61
defined: runtime.GeneratedMultiplier
custom loader: true
instance: runtime.GeneratedMultiplier
reflect: 42
handle: 30
~~~

### Comparing bytecode with actual behavior

**From byte array to Class:** `buildClassfile()` writes the header, constant pool, and two `method_info` entries. `ByteLoader.define(classfile)` loads those bytes into the new loader, letting the JVM define the named class `runtime.GeneratedMultiplier`. Printing `defined` only proves the class exists; printing `custom loader` confirms the defining loader is the newly created `ByteLoader`.

**Constructor:** `public <init>()V` uses `aload_0` to push the uninitialized receiver onto the operand stack, `invokespecial #8` to call `java/lang/Object.<init>:()V`, then `return`. Without calling the superclass constructor, the classfile of a normal instance class would violate object initialization rules.

**Method `twice`:** descriptor `(I)I` means one `int` in and one `int` out. Because it is an instance method, `max_locals=2` reserves slot 0 for `this` and slot 1 for `value`. `iload_1` pushes `value` onto the stack; `iconst_2` pushes the constant 2; `imul` multiplies; `ireturn` returns the result.

**max_stack:** `twice` needs at most 2 items (`value` and `2` before `imul`). The constructor needs at most 1 receiver reference before `invokespecial`. These values are **stack slot limits**, not the number of bytecode instructions.

**Code attribute length:** the fixed part of the Code attribute in the example is 12 bytes plus `code_length`, because `exception_table_length=0` and there are no nested attributes. Therefore `writeMethod` uses `out.writeInt(12 + code.length)`. If an exception table/attributes are added later, you must **recalculate** the exact length; do not blindly reuse this formula.

**Reflection:** `getDeclaredConstructor().newInstance()` creates an instance; `getMethod("twice", int.class)` finds the public method; `Method.invoke(instance, 21)` returns an `Object` holding the boxed integer value, so it prints `42`.

**MethodHandle:** `findVirtual` creates a handle taking the receiver and an `int`, returning an `int`; `invokeWithArguments` accepts passing the receiver and `15` as Java arguments and converts them upon invocation. The result is boxed into an `Integer` to be returned as `Object` and printed as `30`.

### Why is this example valid even without a StackMapTable?

The code of both methods **runs strictly linearly, with no branches**, no exception handlers, and no merging of control flows. For such a small shape, no additional stack-map frames need to be recorded at other basic blocks. For generated classes with `if`, `switch`, loops, `try/catch`, complex stack types, or uninitialized objects crossing branches, you must understand the corresponding `StackMapTable`/verifier constraints. In production, using a compiler/bytecode library that computes frames appropriately is safer.

### Why choose ClassLoader instead of Lookup.defineClass?

The bytecode above declares package `runtime`, while `HandmadeBytecodeDemo` is in the default package. `Lookup.defineClass(classfile)` with a lookup from `HandmadeBytecodeDemo` would not satisfy the **same runtime package** requirement. A dedicated `ByteLoader` can define a class with binary name `runtime.GeneratedMultiplier` that it manages itself, without needing a same-package lookup. This is a choice based on **class-definition context**, not a difference in "which bytecode is better".

## 8. Minimal classfile structure of the manual example

The parts written can be summarized as follows:

~~~text
ClassFile {
  u4 magic = 0xCAFEBABE
  u2 minor_version = 0
  u2 major_version = 61
  u2 constant_pool_count = 12

  constant_pool[1..11]:
    #1  Utf8 "runtime/GeneratedMultiplier"
    #2  Class #1
    #3  Utf8 "java/lang/Object"
    #4  Class #3
    #5  Utf8 "<init>"
    #6  Utf8 "()V"
    #7  NameAndType #5:#6
    #8  Methodref #4:#7
    #9  Utf8 "Code"
    #10 Utf8 "twice"
    #11 Utf8 "(I)I"

  u2 access_flags = 0x0021
  u2 this_class = #2
  u2 super_class = #4
  u2 interfaces_count = 0
  u2 fields_count = 0
  u2 methods_count = 2

  method #1:
    access = public
    name = #5
    descriptor = #6
    Code:
      max_stack = 1
      max_locals = 1
      aload_0
      invokespecial #8
      return

  method #2:
    access = public
    name = #10
    descriptor = #11
    Code:
      max_stack = 2
      max_locals = 2
      iload_1
      iconst_2
      imul
      ireturn

  class attributes_count = 0
}
~~~

This is a **structural diagram** for reading, not syntax that the JVM accepts as Java source. `DataOutputStream` writes integers in big-endian order, matching many u2/u4 fields of the JVM format. `writeUTF` uses modified UTF-8 with a u2 length prefix, compatible with `CONSTANT_Utf8_info` encoding within the ASCII string scope of the example. When building a general-purpose bytecode generator, you must fully comply with length limits, encodings, and constant pool entry types.

The reason `constant_pool_count=12` rather than `11`: slot `0` is reserved, so 11 entries indexed from 1 to 11 require a count of 12. An off-by-one error here can cause the parser to misread the rest of the classfile.

## 9. How to inspect the newly created classfile with javap?

`javap` needs to read a classfile from a file or classpath. The two demos above intentionally keep the bytecode **in memory**; therefore `javap -v -c GeneratedGreeter` will not necessarily find the newly created classfile just from the program having run.

To inspect the manual version with `javap`, in `main` of `HandmadeBytecodeDemo` you can add the following lines **right after** `byte[] classfile = buildClassfile();`, before the program ends:

~~~java
java.nio.file.Path output = java.nio.file.Path.of(
        "out", "runtime", "GeneratedMultiplier.class");
java.nio.file.Files.createDirectories(output.getParent());
java.nio.file.Files.write(output, classfile);
~~~

This is an **optional snippet**, not present in the original program, and will write a file in the `out` directory when you explicitly add it. Then:

~~~bash
javac HandmadeBytecodeDemo.java
java HandmadeBytecodeDemo
javap -classpath out -p -c -v runtime.GeneratedMultiplier
~~~

Read `major version: 61`, the constant pool entries, the `twice` method section, and the instructions `iload_1`, `iconst_2`, `imul`, `ireturn`. You do not need to match line numbers or spacing of every `javap` version; the semantic content of the new classfile is the evidence.

You can try a stricter verification mode:

~~~bash
java -Xverify:all HandmadeBytecodeDemo
~~~

Depending on the JDK version, the `-Xverify:all` option may emit a deprecation/lifecycle warning, but on JDK 17 it is still accepted. The fact that the class loads and the method runs successfully is also a practical verification of the bytecode in the example; however, a single successful run with small inputs **does not prove all control paths** of a general-purpose generator are correct.

### Notes on file name and class name

The file containing the **generator** code is `HandmadeBytecodeDemo.java`; the generated class has the binary name **`runtime.GeneratedMultiplier`**. You **do not need** `runtime/GeneratedMultiplier.java` to run the generator. If you write the `.class` file to disk to use `javap`, place it under `out/runtime/GeneratedMultiplier.class` and add `out` as the classpath root for `javap`.

For the JavaCompiler example, the generated class `GeneratedGreeter` belongs to the default package, and the code generator `CompileAndDefineDemo` also belongs to the default package. If you place the generator in a named package, you must update the binary name of the generated source to match the package and lookup permissions.

## 10. Defining a class multiple times and class-loader identity

A single loader cannot define the same **binary name** multiple times. If you use the same `ByteLoader` and call `define(classfile)` twice for `runtime.GeneratedMultiplier`, the second call may cause a `LinkageError` due to duplicate definition. Do not "retry" by calling the exact same definition again into the same loader after the class has already been defined.

Conversely, two different loaders can define classes with the same binary name:

~~~text
ByteLoader A → runtime.GeneratedMultiplier [Class A]
ByteLoader B → runtime.GeneratedMultiplier [Class B]

Class A.getName() == Class B.getName()  // true as a string
Class A == Class B                       // false for identity
~~~

The diagram is conceptual. These two different types cannot be cast to each other: an object from a class in loader A is not an instance of the class in loader B just because their display names are the same. Shared parent interfaces loaded by the parent can be used as a **communication contract** between plugin and host, if the delegation design is compatible.

### Loader lifecycle and metaspace

A defined class is not individually deleted by "setting `Class<?> = null`". The JVM can reclaim class metadata when the **defining loader** and dependent objects are no longer reachable and unloading conditions are met. A framework generating thousands of differently named classes in a loader that lives for the entire application lifecycle can create metaspace pressure.

Therefore, when defining classes dynamically:

- Reuse generated classes if semantics and isolation permit.
- Design a clear loader lifecycle for groups of classes/plugins that can be discarded.
- Do not cache `Class<?>`, constructors, method handles, or instances tied to a retired loader indefinitely.
- Monitor metaspace errors and the number of defined classes; avoid a "one new class per request" strategy unless necessary.

That is a **runtime lifecycle** issue, distinct from the validity of a single classfile.

## 11. Reflection and MethodHandle: invoking newly defined code

Because the host program's source code does not know the generated class type at compile time, we usually receive the result as `Class<?>`. Invocation options:

**Reflection:**

~~~java
Class<?> type = /* defined Class<?> */;
Object instance = type.getDeclaredConstructor().newInstance();
Object value = type.getMethod("twice", int.class)
        .invoke(instance, 21);
~~~

This snippet is **illustrative**, requiring a valid `type` variable and handling Reflection's checked exceptions. `getDeclaredConstructor()` finds the no-arg constructor; `newInstance()` invokes the constructor; `Method.invoke` boxes the primitive result into `Integer` to return `Object`.

**MethodHandle:**

~~~java
MethodHandle twice = MethodHandles.publicLookup().findVirtual(
        type,
        "twice",
        MethodType.methodType(int.class, int.class));
Object value = twice.invokeWithArguments(instance, 21);
~~~

This is also an **illustrative snippet**, requiring imports and `type`/`instance` variables. `findVirtual` returns a handle with the receiver as the first parameter, i.e. modeled as `(GeneratedMultiplier,int)int`. `invokeWithArguments` suits dynamic code when the receiver is only known as type `Object`. If a concrete Java type is known at compile time, `invokeExact` can be used to strictly enforce the signature, provided the return type also matches.

**Common interface:** if the generated class implements an existing interface and that interface is loaded in a compatible class loader, the host program can cast the instance to that interface and call the method directly. This is an API design generally preferable to per-call reflection, especially when compile-time type checking is desired.

### Why can Method.invoke throw InvocationTargetException?

If the invoked method **itself throws an exception**, `Method.invoke` wraps the target's exception in `InvocationTargetException`. To find the target cause, use `getCause()`. Errors from looking up the wrong name/signature (`NoSuchMethodException`), missing permissions (`IllegalAccessException`), or wrong args (`IllegalArgumentException`) belong to the **Reflection layer**, not errors from the new method.

`MethodHandle` does not necessarily wrap target exceptions in the same way; handle invocation propagates errors according to the method handle contract. Distinguishing error layers helps accurately diagnose "corrupt classfile", "class load failed", and "code ran but business logic threw an error".

## 12. Errors by stage: reading the stack trace at the right place

| Stage | Example errors | How to handle |
| --- | --- | --- |
| **Generate/compile** | JavaCompiler reports syntax/type error | Read `DiagnosticCollector`; fix source or release/classpath configuration |
| **Parse classfile** | `ClassFormatError`, wrong constant-pool index | Check magic/version/count/attribute lengths/descriptor |
| **Verify bytecode** | `VerifyError`, invalid stack types or stackmap | Check operand stack, locals, control-flow joins, and StackMapTable |
| **Classfile version** | `UnsupportedClassVersionError` | Generate bytecode targeting a compatible JDK runtime, e.g., major 61 for Java 17 |
| **Class name definition** | `NoClassDefFoundError` with name-mismatch message, `LinkageError` duplicate class | Verify binary/internal name and class loader; do not define duplicates in the same loader |
| **Lookup/package** | `IllegalArgumentException` or `IllegalAccessException` in Lookup API context | Check the classfile's package, PACKAGE access, and lookup's module |
| **Superclass/dependency** | `NoClassDefFoundError`, `IllegalAccessError`, or `IncompatibleClassChangeError` | Ensure referenced classes exist and loader/module permits access |
| **Class initialization** | `ExceptionInInitializerError`, or error from initializer | Investigate `<clinit>`; do not treat it as a constructor failure |
| **Constructor lookup/invocation** | `NoSuchMethodException`, `IllegalAccessException`, `InvocationTargetException` | Check constructor signature and root cause |
| **Method lookup/invocation** | `NoSuchMethodException`, `WrongMethodTypeException`, `ClassCastException` | Check method descriptor, receiver, handle shape, and call-site type |
| **Runtime resources** | `OutOfMemoryError: Metaspace` | Reduce unbounded class generation, review defining loader lifecycle |

The situations above are **typical error categories**, not an exhaustive mapping: the JVM is allowed to perform some linking steps lazily, so dependency errors may appear when accessing a member rather than immediately at `defineClass`. A `VerifyError` may still be detected by the VM at what application code sees as the first use of the class.

### Do not catch Throwable and ignore it

Errors in this chain include `Error` subclasses such as `LinkageError`, `VerifyError`, and `OutOfMemoryError`. You should not catch everything, automatically generate different bytes, and retry indefinitely; that can leave the JVM with partially defined classes or confuse ownership/class names.

For a runtime framework, log sufficient **binary name, defining loader, classfile major version, current step, and root cause**. If the bytecode may contain sensitive data (constant pool strings), do not log the entire `byte[]` content to monitoring systems.

## 13. Testing workflow for a generator: from bytes to behavior

A reliable generator cannot just test "byte array is non-empty". Testing should be designed across multiple layers:

1. **Check header and version:** magic `CAFEBABE`, correct major/minor, `byte[]` not truncated.
2. **Check structure:** constant pool indexes/tags, names, descriptors, attribute lengths; when tools are available, dump `javap -v -c` to inspect the code.
3. **Check verifier with a real JVM:** define the class in an isolated loader, test running with full verification when appropriate; test branched paths and exception handlers if the generator supports them.
4. **Check identity and access:** name, package, loader, superclass, interfaces, and accessibility from caller code.
5. **Check initialization:** static initializer runs at the expected time; does not run repeatedly within the same definition.
6. **Check constructor:** correct parameter count/types, created object has expected state; missing constructor cases fail clearly.
7. **Check method:** inputs/outputs and exceptions of the new method, including primitives, references, null, numeric boundaries, and invalid conditions.
8. **Check cleanup:** loader and class metadata lifecycle if the generator creates many classes.
9. **Check version:** run on the lowest supported JDK runtime and use the right target version.

For a simple `twice(I)I` class, test at least `twice(0)==0`, `twice(1)==2`, `twice(-3)==-6`, while also recognizing **`int` overflow** per Java semantics for large inputs. Code with correct types that computes the wrong value is still a generator bug or business-model bug.

### Negative tests to know, but not treat as valid examples

Some intentional corruptions to a classfile to observe JVM checks:

- Change one byte of magic `CAFEBABE` → classfile no longer has a standard header.
- Change `major_version` to a number higher than the runtime supports → `UnsupportedClassVersionError`.
- Increment `constant_pool_count` by one without adding an entry → classfile is parsed out of alignment.
- Point `invokespecial` to a wrong kind of constant pool entry → structural/linking/verifier error.
- Use `ireturn` when the operand stack only has a reference → verification failure.

These cases should only be done in **isolated test processes/loaders** and treated as intentionally invalid inputs. Do not put broken classfiles into production flows and do not treat the exact timing of an error reported by a specific JVM version as the sole contract.

## 14. Design decisions in real applications

### A. Avoid writing entire classfiles manually unless necessary

The manual example only has one class, one constructor, and one multiplication. Just adding branching, generic signatures, annotations, interfaces, exception handlers, stack-map frames, fields, records, or invokedynamic greatly increases the number of states to manage. Use JavaCompiler if you can express the source, or a reliable bytecode generation library when direct bytecode optimization/transformation is needed.

### B. Do not run untrusted code as a "sandbox" just by using a custom loader

Creating a new `ClassLoader` **does not make that code safe**. Once loaded and running in the same JVM, the code can use APIs permitted by the environment; the traditional Security Manager is no longer a sandbox model to rely on in modern Java versions. If running untrusted code, you must design isolation at the process/container/OS level, resource permissions, CPU/memory/time limits, and appropriate input validation.

Bytecode verification ensures type safety and JVM structural correctness; **it does not mean the defined code cannot perform dangerous actions**.

### C. Be careful with packages/modules and library versions

`Lookup.defineClass` is bound by the lookup's package/module constraints. `ClassLoader.defineClass` needs an appropriate loader and can run into class visibility, sealing, package signers, or module boundaries. When a generated class calls host libraries, both sides must see interface types with compatible identity.

If a framework uses multiple plugin loaders, do not pass an object of the "same class name" and assume casting will always work. Check the actual loader chain and interface contract.

### D. Name classes intentionally and cache reasonably

A class with a fixed name should be defined **once in a loader**. If code changes across generations, you can use a new loader or a different versioned name by design. Consider metaspace/caches so the number of classes does not grow without bound. Do not use user-supplied names directly without validation and a namespace policy.

### E. Do not depend on unpredictable side-effect ordering

In the first example, the order is clear because the code calls `Class.forName(..., true, ...)` before the constructor and logs. In a multithreaded environment, class initialization has its own JVM synchronization mechanism; do not recursively initialize the same class endlessly or use static blocks for hard-to-recover side effects. Frameworks should control runtime initialization through explicit APIs/constructors when possible.

## 15. Distinguishing ways to "run new code" after defining

| Approach | Pros | Cons/conditions |
| --- | --- | --- |
| `Constructor.newInstance(...)` then `Method.invoke(...)` | Works when you only have `Class<?>`, easy to read and debug | Runtime lookup by name/signature, boxed results, target exceptions wrapped in InvocationTargetException |
| `MethodHandles.Lookup.findVirtual/findStatic` | Typed handle model, easy to build adapters/call chains | Must match `MethodType` and Lookup permissions; `invokeExact` is strict |
| Cast to a known interface | Good type safety in source, easy-to-use API | Generated class must implement the exact interface with compatible loader identity |
| Static method via Reflection/handle | No instance needed to invoke static code | Class requires initialization per JVM rules before active use; linkage/initializer errors can still occur |
| `MethodHandles.Lookup.findConstructor` | Can represent a constructor as a MethodHandle | Constructor handle signature returns object type; requires managing permissions and type conversions |

**Defining a class** is only the step that informs the JVM of the new type. To execute the new code, the caller must still select the **corresponding constructor/method**, have an object if it is an instance method, satisfy permissions and types, and handle runtime exceptions.

If the interface is known at compile time, a durable strategy is for the compiler/generator to create a class that **implements the interface**, then instantiate the object and cast it to the interface. If the shape is unknown, Reflection/MethodHandles provide flexible manipulation but shift many errors from compile time to runtime.

## 16. Practice questions and answers

**1. Is a `byte[]` with the first four bytes `CAFEBABE` enough for `defineClass` to succeed?**  
No. That is only the magic number; the constant pool, version, metadata, Code attributes, and verifier constraints must all be valid.

**2. Which major classfile version does Java 17 use?**  
Major version `61`. An older runtime that does not support that version will not load a Java 17 classfile.

**3. Does `Lookup.defineClass(bytes)` automatically run the static initializer?**  
Not per the API contract. An operation that triggers initialization is required, such as `Class.forName(name, true, loader)`.

**4. How do `Class<?>` and a generated object differ?**  
`Class<?>` represents the type definition; an object is an instance created via a constructor or an appropriate object-creation mechanism.

**5. Why can't `Lookup.defineClass` arbitrarily load bytecode in a different package from the lookup?**  
The API requires the class to be defined in the same runtime package under appropriate lookup permissions; it is not an entry point for loading classes into arbitrary packages.

**6. Can `ClassLoader#defineClass` bypass the bytecode verifier?**  
No. The JVM still checks structure, permissions, bytecode compatibility, and class linking.

**7. Why does `runtime.GeneratedMultiplier` have `max_locals=2` for `twice(int)`?**  
Because it is an instance method: slot 0 is `this`, slot 1 is the `int` argument.

**8. Why must constructor bytecode call `Object.<init>`?**  
Instance constructors must follow superclass and receiver initialization rules. The example code uses `aload_0; invokespecial Object.<init>; return`.

**9. Why is `constant_pool_count` equal to 12 when there are 11 entries?**  
Constant-pool index 0 is unused, and the entries are numbered 1..11.

**10. How does `Class.forName(name, true, loader)` differ from `Class.forName(name, false, loader)`?**  
`true` requests initialization; `false` does not request immediate initialization from that call alone.

**11. Are two classes with the same binary name in two loaders considered the same type?**  
No. A JVM class's type identity depends on **name and defining loader**; having the same text name is not enough.

**12. Why does `Method.invoke` return `Object` even when the generated method returns `int`?**  
The Reflection API has return type `Object`; primitive values are boxed into the appropriate wrapper.

**13. When a generated constructor throws an error, what can `newInstance` report?**  
`InvocationTargetException` with the root cause in `getCause()`; distinguish this from constructor-lookup errors or missing permissions.

**14. How many parameters does `MethodHandle.findVirtual` for `twice(int)int` take?**  
Two when the handle has not bound a receiver: the generated class receiver and one `int`. Modeled as `(GeneratedMultiplier,int)int`.

**15. When should `javap` be used?**  
To read a classfile/bytecode after writing bytes to a file or having the class on the classpath. `javap` cannot directly read a `Class<?>` just created inside another JVM.

**16. Can a new class loader be used to run malicious bytecode safely?**  
No. A separate loader does not create a security sandbox; real resource/permission isolation is required.

**17. Is catching `Throwable` and immediately retrying define sensible?**  
No. You must classify generator errors, duplicate names, verifier errors, linkage errors, initializer errors, and runtime errors. Wrong retries can corrupt state or increase the number of classes.

**18. What is the problem if every request defines a new class in a long-lived loader?**  
It risks growing metadata/metaspace and making unloading difficult; you should cache generator outputs or design a controlled loader lifecycle.

## 17. Sequential implementation checklist

- [ ] Determine the **binary name**, package, target JDK major version, superclass/interfaces, and method signatures.
- [ ] Choose how to generate bytecode: JavaCompiler, a bytecode library, or a manual builder if there is a genuine reason.
- [ ] Generate a **complete byte[]**, not truncated partway; check magic/version/structure if needed.
- [ ] If building the classfile manually: verify constant pool indexes, descriptors, max_stack/max_locals, Code lengths, and control flow/stack maps.
- [ ] Choose a **defining loader/lookup** matching the package/module/access rights; do not define duplicate names in the same loader.
- [ ] Call `defineClass` and keep the returned `Class<?>`; distinguish it from an object instance.
- [ ] Request initialization at the desired time, monitoring the static initializer and related errors.
- [ ] Find the **constructor with the exact signature**, create the instance, and handle the cause if the constructor throws.
- [ ] Find/invoke the **method with the exact signature** via interface, Reflection, or MethodHandle; ensure receiver/return types match.
- [ ] Test input/output values and exceptions of the new code; do not treat "define succeeded" as proof of correct logic.
- [ ] Monitor classloader lifecycle, class name collisions, caching, and metaspace.
- [ ] Do not treat verification/classloaders as a sandbox for running untrusted code.

## 18. Conclusion

The chain of generating and executing dynamic code in the JVM consists of **four main boundaries**:

1. **Generating valid bytes:** emitting a classfile with the right format, version, and bytecode verification rules.
2. **Defining the class:** choosing `Lookup.defineClass` or `ClassLoader.defineClass` according to package/module/loader; obtaining `Class<?>`.
3. **Initializing the class and object:** distinguishing `<clinit>`, `<init>`, `Class.forName`, and constructors.
4. **Executing the new code:** invoking methods via Reflection, MethodHandle, or an interface with matching types and permissions.

The two Java 17+ programs demonstrated both the **compiler generating classfile** path and the **writing bytecode from scratch** path, both leading to instantiating and invoking a method on the newly defined class. When you understand these boundaries, you can read stack traces at the right stage, avoid confusing a classfile with an object, and design runtime code generation that is both verifiable and lifecycle-managed.
