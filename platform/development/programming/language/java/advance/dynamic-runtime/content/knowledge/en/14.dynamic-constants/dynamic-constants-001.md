# 14.1 CONSTANT_Dynamic and Differences from the invokedynamic Call Site

**Context:** Java Advance → dynamic-runtime → 14. Dynamic Constants.

The Java Virtual Machine (JVM) has two runtime linking mechanisms that are easily confused because both use a **bootstrap method** and both appear in the constant pool:

- **`CONSTANT_Dynamic` (condy, constant pool tag 17)** is a *dynamically-computed constant*: the JVM executes a bootstrap to **compute a value of a specific type**, then caches the resolved value.
- **`CONSTANT_InvokeDynamic` (tag 18)** is a *dynamically-computed call site*: the JVM executes a bootstrap to **link an `invokedynamic` call site to a `CallSite` object**, then executes the call site's target each time the instruction runs.

They share the **bootstrap resolution mechanism**, but have completely different outcomes: a **value** for condy and a **call site with behavior** for indy. This lesson covers the class file structure, type notations, bootstrap signatures, cache semantics, when to use each mechanism, common pitfalls, and a **Java 17 program that actually generates both entries to verify with `javap -v`**.

## 1. Visualizing the Difference with a Diagram

### Condy: loading a resolved constant

```text
                    CONSTANT_Dynamic (tag 17)
                    name = "configValue"
                    descriptor = Ljava/lang/String;
                    bootstrap = bootstrapConstant
                                |
                                v
                          instruction ldc
                                |
                         JVM resolve symbol
                                |
                         bootstrap(Lookup,
                          "configValue",
                          String.class)
                                |
                           "value-1"
                                |
                   cache resolution result
                                |
     subsequent ldc with same reference: "value-1"
```

What is "dynamic" is that **the value is computed at resolution**, not "calling the bootstrap on every read". If the bootstrap creates a mutable object, the JVM caches the **reference to the object**, not freezing the object's internal state.

### Indy: creating a call site and dispatching multiple times

```text
                   CONSTANT_InvokeDynamic (tag 18)
                   name = "call"
                   descriptor = (String)String
                   bootstrap = bootstrapInvocation
                                |
                         instruction invokedynamic
                                |
                          JVM link instruction
                                |
                bootstrap(Lookup, "call", MethodType)
                                |
                  VolatileCallSite(target=first)
                                |
                    first("A") -> "first:A"
                                |
                   setTarget(second)   [later]
                                |
                    second("C") -> "second:C"
```

Here, the bootstrap returns a **`CallSite`**, not `"first:A"`. The business invocation is performed by the call site's target. Because `VolatileCallSite` can change its target, the result of a later call can differ, **even though the bootstrap does not run again**. If the bootstrap returns a `ConstantCallSite`, the target cannot be changed; indy's nature is still a **call site**, not condy.

## 2. Constant-Pool Structure and Type Notations

JVMS 4.4.10 specifies:

```text
CONSTANT_Dynamic_info {
    u1 tag;                          // 17
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}

CONSTANT_InvokeDynamic_info {
    u1 tag;                          // 18
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
```

The two structures are nearly identical in bytes, but `name_and_type_index` points to **two different kinds of descriptors**:

| Property | Condy | Indy |
| --- | --- | --- |
| Tag | `CONSTANT_Dynamic = 17` | `CONSTANT_InvokeDynamic = 18` |
| `NameAndType` | Name and **field descriptor** | Name and **method descriptor** |
| Example | `configValue:Ljava/lang/String;` | `call:(Ljava/lang/String;)Ljava/lang/String;` |
| Type meaning | A value type, e.g., `String` | Call signature: parameter types and return type |
| Opcode used | `ldc`/`ldc_w`; `ldc2_w` for category 2 types `long`/`double` | `invokedynamic` |
| Typical bootstrap type argument | `Class<?>` | `MethodType` |
| Bootstrap returns | Value converted to the field descriptor type | `CallSite` whose `type()` equals the method descriptor |
| Reuse after linkage | Reuse the resolved value | Reuse the instruction's linkage; each time still executes the target |

**Field descriptor** differs from **method descriptor**:

- `Ljava/lang/String;` is a field descriptor: it represents the reference type `java.lang.String`.
- `I` is the primitive type `int`; `J` is `long`.
- `(Ljava/lang/String;)Ljava/lang/String;` is a method descriptor: takes a `String` and returns a `String`.
- `()V` is the method descriptor of a method with no parameters returning `void`; condy **cannot** have a "`void` value" because it must resolve to a value.

The `bootstrap_method_attr_index` field is **not a direct index of a Java method**. It is an index into the array of bootstrap specs in the **`BootstrapMethods` class-file attribute**. Each bootstrap spec contains a reference to a `CONSTANT_MethodHandle` and a list of static bootstrap arguments.

```text
constant_pool:
  #26 = CONSTANT_Dynamic,       bootstrap spec 0
  #29 = CONSTANT_InvokeDynamic, bootstrap spec 1

BootstrapMethods attribute:
  [0] -> MethodHandle of bootstrapConstant, 0 static args
  [1] -> MethodHandle of bootstrapInvocation, 0 static args

bytecode:
  readConstant():  ldc #26; areturn
  dynamicCall(s):  aload_0; invokedynamic #29; areturn
```

The indexes above are **the indices from the Section 7 example**, not a fixed format for every class. `BootstrapMethods` also supports various static bootstrap arguments such as strings, method handles, method types, classes, or compatible resolved condy entries; the two entries in the demo only use the three required parameters.

### JVM Versions

- `invokedynamic`/`CONSTANT_InvokeDynamic` has existed since **Java 7 (class-file major version 51)**.
- `CONSTANT_Dynamic` has existed since **Java 11 (major 55; JEP 309)**.
- The demo below generates a file with **major version 61 (Java 17)**, running on JDK 17+.
- Java source has no direct keyword to create an arbitrary `CONSTANT_Dynamic`. Writing `static final` does not mean generating condy. Therefore, to see a real `Dynamic` entry, we need to generate bytecode or use a bytecode library.
- Some constructs are compiled by `javac` using `invokedynamic` (for example, lambdas or string concatenation in appropriate Java versions), but **not every Java call** uses this opcode.

## 3. Condy Bootstrap: Returning a Value, Not a Target Call

Common signature pattern:

```java
public static String bootstrapConstant(
        MethodHandles.Lookup lookup, String name, Class<?> type) {
    return "computed-value";
}
```

This is a **snippet**, not a standalone program. When resolving condy, the JVM provides:

1. `Lookup` with the context of the class containing the symbolic reference.
2. The symbol name `name` from `NameAndType`.
3. The `Class<?>` object corresponding to **the value type requested** by the field descriptor.
4. Additional static arguments if the `BootstrapMethods` entry declares them.

In the real example, `name` is `"configValue"` and `type` is `String.class`; the bootstrap returns the string `"value-1"`. The JVM validates/converts the result to the declared type `T`. If incompatible (for example, an object cannot be cast to `String`, or `null` for a primitive), resolution raises an error, typically `BootstrapMethodError`.

**Condy is not restricted to returning only String.** It can return an object reference, `Class`, `MethodHandle`, `VarHandle`, or a primitive value matching the field descriptor. The `java.lang.invoke.ConstantBootstraps` library provides built-in bootstraps such as `nullConstant`, `enumConstant`, `primitiveClass`, `getStaticFinal`, `fieldVarHandle`, `staticFieldVarHandle`, `arrayVarHandle`, and `invoke`.

### Why is `Lookup` needed?

A BSM may need to read fields, create method handles, access classes, or reference linked resources. `Lookup` reflects the access context of the class containing the entry: **a bootstrap is not allowed to bypass all `private` or JPMS barriers**. In a modular application, access checks when looking up a target/field still apply.

Although many Java examples use the exact signature `(Lookup, String, Class) -> Object/String`, **the JVMS allows bootstrap method handles with parameter types compatible via `invokeWithArguments`**. For condy specifically, there is an important constraint: the first parameter of the BSM handle must have type `MethodHandles.Lookup`. The sample form above is easy to read and suitable for basic examples.

### Is a condy value always immutable?

No. A bootstrap returning a mutable `ArrayList` produces **one cached reference**. Subsequent `ldc` instructions on the same entry can retrieve that exact same object, but the object's internals can still be modified. If you want an immutable value, use an immutable object or proper concurrency conventions. "Constant" means the JVM does not **re-resolve that value** after successful resolution, not that it turns a mutable object into an immutable one.

### Cache scope of the value

Each class created by a defining class loader has a corresponding run-time constant pool. A condy result is reused per **resolved symbolic reference in the run-time constant pool**, not a JVM-wide cache by the name `configValue`. Two different classes using the same name/descriptor can still have different results and bootstrap invocation counts.

You should not attach non-idempotent operations (such as charging money) to a condy BSM merely expecting it to run "always once": when multiple threads race on initial resolution, **the JVM may invoke the bootstrap concurrently multiple times and then pick one result**. This point will be explained in Section 9.

## 4. Indy Bootstrap: Returning a `CallSite` and a `MethodType`

Simple form:

```java
public static CallSite bootstrapInvocation(
        MethodHandles.Lookup lookup, String name, MethodType type)
        throws ReflectiveOperationException {

    MethodHandle target = MethodHandles.lookup().findStatic(
            SomePublicClass.class, "implementation", type);
    return new ConstantCallSite(target);
}
```

This is also an **illustrative snippet**; `SomePublicClass`/`implementation` must be replaced with a real method in another program. The JVM typically provides:

1. `Lookup` corresponding to the class containing the indy instruction.
2. The dynamic call site name such as `"call"`.
3. `MethodType` corresponding to the **method descriptor** including parameters and return type.
4. Optional static bootstrap arguments.

**The result must be a non-null `CallSite`**, whose `type()` equals the signature required by the indy instruction. You cannot directly return a `MethodHandle` or `String` and expect the JVM to create a call site automatically. If using `ConstantCallSite`, the target is fixed; if using `MutableCallSite` or `VolatileCallSite`, other code can update the target according to the corresponding memory visibility rules.

### Special linkage scope of `invokedynamic`

According to JVMS 5.4.3, when resolution of an indy instruction succeeds, the JVM remembers the **`CallSite` for that specific instruction**. Subsequent executions at **the same instruction location** reuse the linked call site. However, if **two different indy instructions point to the same constant-pool entry**, they are still allowed/required to link separately per instruction; one should not say "one indy CP entry always means a single call site".

Compare with condy: when a `CONSTANT_Dynamic` symbolic reference resolves to a value, other `ldc` instructions with that same reference reuse the resolved constant. This is an important difference even though both structures have a bootstrap index and `NameAndType`.

### Do not confuse linkage with each invocation

```text
First time at instruction N:
    BSM -> CallSite(target=first)
    first("A") -> "first:A"

Second time, same instruction N:
    [no BSM needed anymore]
    first("B") -> "first:B"

Update:
    site.setTarget(second)

Third time, same instruction N:
    [still the same CallSite]
    second("C") -> "second:C"
```

The `invokedynamic` call site operates through the stored linkage, but **the target is executed on every call**. Condy, on the other hand, pushes a resolved value onto the operand stack without an implicit "target method invocation" on each load.

## 5. When Does the JVM Actually Resolve?

A convenient pedagogical model is "first use invokes the bootstrap" because JVMs typically lazy-resolve symbolic references when needed. However, for condy, applications **should not rely on a fixed wall-clock moment** for BSM side effects: the specification has rules on when resolution is permitted, and the JVM may have the right to perform valid eager resolution. What is guaranteed is: **successful resolution is remembered** and does not automatically re-execute the BSM on subsequent uses of the same reference.

For indy, linking is tied to executing **a specific indy instruction**; code that merely loads a class or looks up a `Method` has not yet run the target. The example run below shows before/linkage output matching a tested Java 17 JVM, but is not a general scheduling guarantee for all executions.

### An example of cache and version

```text
condy resolution:
    configValue => "value-1"
    10 ldc calls on same resolved ref -> same "value-1"

indy resolution:
    instruction N => CallSite S
    10 invocations of N -> 10 executions of S's current target
    setTarget(H2) -> subsequent calls can use H2

Cannot:
    call "condy.setTarget(H2)"  // no such API
```

If condy **happens to return a `CallSite` object as its value**, `ldc` only returns **that object**. It does not execute the `invokedynamic` opcode or invoke the target automatically. A consumer wanting to invoke it must write the corresponding code. A result of type `CallSite` does not turn a constant pool entry from tag 17 into tag 18.

## 6. Concise Comparison Table

| Criterion | `CONSTANT_Dynamic` | `CONSTANT_InvokeDynamic` |
| --- | --- | --- |
| Tag | 17 | 18 |
| Purpose | Resolve value | Resolve call site |
| Descriptor | Field descriptor | Method descriptor |
| Opcode | `ldc`/`ldc_w`/`ldc2_w` | `invokedynamic` |
| Bootstrap type arg | `Class<?>` | `MethodType` |
| Bootstrap result | Typed constant value | `CallSite` |
| After successful linkage | Reuse value | Invoke target each time |
| Can change result via `setTarget`? | No API to replace resolved value | Yes, on mutable/volatile call site |
| Primary cache unit | Symbolic reference in run-time constant pool | Each linked indy instruction |
| Minimum | Java 11 / major 55 | Java 7 / major 51 |
| Bootstrap error | Typically `BootstrapMethodError` | Typically `BootstrapMethodError` |
| Usage | Runtime-computed metadata/value/handle | Runtime dispatch/language linkage |

## 7. Java 17 Demo: Generating a Class File Containing **Both Real Entries**

To ensure `javap -v` displays both constant pool types properly, this example uses the **pure JDK `DataOutputStream`** API to create a minimal Java 17 classfile. No ASM, no external dependencies, and **no flags to access internal JDK APIs** are needed.

The program has two classes:

- `ConstantBridgeDemo`: the Java source you compile; contains bootstrap methods, two business methods, and bytecode generation code.
- `GeneratedLinkageDemo`: a class generated from `byte[]`, containing `readConstant()` with `ldc #26` and `dynamicCall(String)` with `invokedynamic #29`. There is no separate Java source file for it.

In production, you should not hard-code constant pool indices as in the demo; use a bytecode library that supports the classfile version or an appropriate compiler mechanism. The example is solely intended to help learners **read a real class file**.

### 7.1 Single Source File: `ConstantBridgeDemo.java`

Save **all** of the code below into `ConstantBridgeDemo.java` in your experiment directory:

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.CallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VolatileCallSite;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;

public class ConstantBridgeDemo {
    private static int constantLinks;
    private static int invocationLinks;
    private static VolatileCallSite callSite;

    public static String bootstrapConstant(MethodHandles.Lookup lookup,
                                           String name, Class<?> type) {
        constantLinks++;
        System.out.println("condy.bootstrap:" + name + ":" + type.getSimpleName());
        return "value-" + constantLinks;
    }

    public static CallSite bootstrapInvocation(MethodHandles.Lookup lookup,
                                               String name, MethodType type)
            throws ReflectiveOperationException {
        invocationLinks++;
        System.out.println("indy.bootstrap:" + name + ":" + type);
        MethodHandle target = MethodHandles.lookup()
                .findStatic(ConstantBridgeDemo.class, "first", type);
        callSite = new VolatileCallSite(target);
        return callSite;
    }

    public static String first(String input) {
        return "first:" + input;
    }

    public static String second(String input) {
        return "second:" + input;
    }

    static final class Loader extends ClassLoader {
        Loader(ClassLoader parent) { super(parent); }
        Class<?> defineGenerated(byte[] binary) {
            return defineClass("GeneratedLinkageDemo", binary, 0, binary.length);
        }
    }

    private static void utf(DataOutputStream out, String value) throws IOException {
        out.writeByte(1);
        out.writeUTF(value);
    }

    private static void clazz(DataOutputStream out, int name) throws IOException {
        out.writeByte(7);
        out.writeShort(name);
    }

    private static void nameAndType(DataOutputStream out, int name, int desc)
            throws IOException {
        out.writeByte(12);
        out.writeShort(name);
        out.writeShort(desc);
    }

    private static void methodRef(DataOutputStream out, int owner, int signature)
            throws IOException {
        out.writeByte(10);
        out.writeShort(owner);
        out.writeShort(signature);
    }

    private static void staticHandle(DataOutputStream out, int reference)
            throws IOException {
        out.writeByte(15);
        out.writeByte(6); // REF_invokeStatic
        out.writeShort(reference);
    }

    private static void codeMethod(DataOutputStream out, int name, int descriptor,
                                   int maxStack, int locals, byte[] code)
            throws IOException {
        out.writeShort(0x0009); // public static
        out.writeShort(name);
        out.writeShort(descriptor);
        out.writeShort(1); // Code attribute
        out.writeShort(7); // #7 = "Code"
        out.writeInt(12 + code.length);
        out.writeShort(maxStack);
        out.writeShort(locals);
        out.writeInt(code.length);
        out.write(code);
        out.writeShort(0); // no exception handlers
        out.writeShort(0); // no nested Code attributes
    }

    static byte[] buildClass() throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(buffer);
        out.writeInt(0xCAFEBABE);
        out.writeShort(0);   // minor
        out.writeShort(61);  // Java 17 class-file version
        out.writeShort(30);  // constant_pool_count: 29 entries

        utf(out, "GeneratedLinkageDemo");                            // #1
        clazz(out, 1);                                                // #2
        utf(out, "java/lang/Object");                                 // #3
        clazz(out, 3);                                                // #4
        utf(out, "readConstant");                                     // #5
        utf(out, "()Ljava/lang/String;");                            // #6
        utf(out, "Code");                                             // #7
        utf(out, "dynamicCall");                                      // #8
        utf(out, "(Ljava/lang/String;)Ljava/lang/String;");          // #9
        utf(out, "BootstrapMethods");                                 // #10
        utf(out, "ConstantBridgeDemo");                               // #11
        clazz(out, 11);                                               // #12
        utf(out, "bootstrapConstant");                                // #13
        utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/Class;)Ljava/lang/String;"); // #14
        nameAndType(out, 13, 14);                                     // #15
        methodRef(out, 12, 15);                                       // #16
        staticHandle(out, 16);                                        // #17
        utf(out, "bootstrapInvocation");                              // #18
        utf(out, "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;Ljava/lang/invoke/MethodType;)Ljava/lang/invoke/CallSite;"); // #19
        nameAndType(out, 18, 19);                                     // #20
        methodRef(out, 12, 20);                                       // #21
        staticHandle(out, 21);                                        // #22
        utf(out, "configValue");                                      // #23
        utf(out, "Ljava/lang/String;");                              // #24
        nameAndType(out, 23, 24);                                     // #25
        out.writeByte(17); out.writeShort(0); out.writeShort(25);     // #26 CONSTANT_Dynamic
        utf(out, "call");                                             // #27
        nameAndType(out, 27, 9);                                      // #28
        out.writeByte(18); out.writeShort(1); out.writeShort(28);     // #29 CONSTANT_InvokeDynamic

        out.writeShort(0x0021); // public, super
        out.writeShort(2);      // this class
        out.writeShort(4);      // java/lang/Object
        out.writeShort(0);      // interfaces_count
        out.writeShort(0);      // fields_count
        out.writeShort(2);      // methods_count

        codeMethod(out, 5, 6, 1, 0, new byte[]{
            0x12, 0x1a,             // ldc #26 (CONSTANT_Dynamic)
            (byte) 0xb0            // areturn
        });
        codeMethod(out, 8, 9, 1, 1, new byte[]{
            0x2a,                  // aload_0
            (byte) 0xba, 0, 29, 0, 0,  // invokedynamic #29
            (byte) 0xb0            // areturn
        });

        out.writeShort(1);   // class attributes_count
        out.writeShort(10);  // "BootstrapMethods"
        out.writeInt(10);    // attribute_length
        out.writeShort(2);   // two bootstrap specs
        out.writeShort(17); out.writeShort(0); // condy BSM handle, no static args
        out.writeShort(22); out.writeShort(0); // indy BSM handle, no static args
        out.flush();
        return buffer.toByteArray();
    }

    public static void main(String[] args) throws Throwable {
        byte[] binary = buildClass();
        Files.write(Path.of("GeneratedLinkageDemo.class"), binary);
        Class<?> generated = new Loader(ConstantBridgeDemo.class.getClassLoader())
                .defineGenerated(binary);
        Method read = generated.getMethod("readConstant");
        Method call = generated.getMethod("dynamicCall", String.class);

        System.out.println("before:condy=" + constantLinks + ",indy=" + invocationLinks);
        System.out.println("condy.1=" + read.invoke(null));
        System.out.println("condy.2=" + read.invoke(null));
        System.out.println("indy.1=" + call.invoke(null, "A"));
        System.out.println("indy.2=" + call.invoke(null, "B"));
        MethodHandle next = MethodHandles.lookup()
                .findStatic(ConstantBridgeDemo.class, "second",
                            MethodType.methodType(String.class, String.class));
        callSite.setTarget(next);
        System.out.println("indy.3=" + call.invoke(null, "C"));
        System.out.println("after:condy=" + constantLinks + ",indy=" + invocationLinks);
    }
}
```

### 7.2 Compile and Run

From the directory containing the Java file:

```bash
javac --release 17 -encoding UTF-8 ConstantBridgeDemo.java
java ConstantBridgeDemo
javap -v GeneratedLinkageDemo
```

`java ConstantBridgeDemo` also generates `GeneratedLinkageDemo.class` in the current directory. `javap -v` reads the generated class file, making it easy to see the two constant-pool entries that Java source cannot directly express.

**Actual output from `java ConstantBridgeDemo` (single-threaded):**

```text
before:condy=0,indy=0
condy.bootstrap:configValue:String
condy.1=value-1
condy.2=value-1
indy.bootstrap:call:(String)String
indy.1=first:A
indy.2=first:B
indy.3=second:C
after:condy=1,indy=1
```

Explanation:

1. After the driver creates `GeneratedLinkageDemo` and obtains the `Method` objects via Reflection, in the tested run, neither bootstrap has run yet: `before:condy=0,indy=0`.
2. `read.invoke(null)` causes the `readConstant` method to execute **`ldc #26`**. The BSM `bootstrapConstant` receives the name `configValue` and `String.class`, returning `"value-1"`.
3. Calling `readConstant` a second time still uses the resolved `"value-1"`; `constantLinks` does not increment.
4. `call.invoke(null,"A")` causes the `dynamicCall` method to execute **`invokedynamic #29`**. The BSM `bootstrapInvocation` creates a `VolatileCallSite` with target `first`. That is why `indy.bootstrap:call:(String)String` appears, followed by `indy.1=first:A`.
5. Calling `dynamicCall` a second time at **the same instruction** uses the linked site, yet still invokes the target with input `B`: `indy.2=first:B`. The BSM does not run again.
6. The code `callSite.setTarget(next)` switches the target from `first` to `second` without **modifying the CP entry or re-resolving the indy instruction**. The subsequent call returns `indy.3=second:C`.
7. `after:condy=1,indy=1` confirms that in the **tested single-threaded scenario** each bootstrap runs once; this result should not be generalized into a callback-count guarantee under multi-threaded resolution races.

**Distinguishing Reflection from the bytecode being studied:** `Method.invoke` appears in the **driver** to invoke the generated methods. It is not the `invokedynamic` opcode itself. The `ldc` and `invokedynamic` opcodes reside **in the bytecode of `GeneratedLinkageDemo`** and can be inspected with `javap -v`.

### 7.3 Evidence from `javap -v`

In the long output of `javap -v GeneratedLinkageDemo`, the notable parts are (relevant lines excerpted, not the full verbatim output):

```text
major version: 61
#26 = Dynamic            #0:#25     // #0:configValue:Ljava/lang/String;
#29 = InvokeDynamic      #1:#28     // #1:call:(Ljava/lang/String;)Ljava/lang/String;

public static java.lang.String readConstant();
    ...
    0: ldc           #26          // Dynamic #0:configValue:Ljava/lang/String;
    2: areturn

public static java.lang.String dynamicCall(java.lang.String);
    ...
    0: aload_0
    1: invokedynamic #29,  0      // InvokeDynamic #1:call:(Ljava/lang/String;)Ljava/lang/String;
    6: areturn

BootstrapMethods:
  0: #17 REF_invokeStatic ConstantBridgeDemo.bootstrapConstant:(...)
  1: #22 REF_invokeStatic ConstantBridgeDemo.bootstrapInvocation:(...)
```

The `...` in this excerpt represent **long metadata/descriptors omitted** for readability, not `javap` syntax. When you run it, you will see the full descriptors of the BSMs and related constant-pool entries.

Notice the three connections:

- `#26` has tag **17**, bootstrap spec index `0`, descriptor **`Ljava/lang/String;`**, and is loaded by **`ldc`**.
- `#29` has tag **18**, bootstrap spec index `1`, descriptor **`(Ljava/lang/String;)Ljava/lang/String;`**, and is used by **`invokedynamic`**.
- `BootstrapMethods[0]` contains `#17` method handle for `bootstrapConstant`; `BootstrapMethods[1]` contains `#22` for `bootstrapInvocation`.

### 7.4 Why is this small class generator valid?

In `buildClass()`:

- `0xCAFEBABE` marks the class file; major **61** indicates Java 17.
- `constant_pool_count = 30`, but there are only 29 actual entries from `#1` to `#29` (index `0` is unused).
- `staticHandle(...)` writes constant-pool tag **15** for MethodHandle and reference kind **6 = REF_invokeStatic**.
- `out.writeByte(17)` emits a **CONSTANT_Dynamic** entry (with bootstrap index 0).
- `out.writeByte(18)` emits a **CONSTANT_InvokeDynamic** entry (with bootstrap index 1).
- The two generated methods contain just enough bytecodes for `ldc/areturn` and `aload_0/invokedynamic/areturn`.
- The `BootstrapMethods` class attribute contains 2 bootstrap specs, each with 0 static args.

The `GeneratedLinkageDemo` class **has no constructor** because the demo only calls two static methods; no instance needs to be created. The `Code` attribute has no branches or exception handlers, so the minimal structure is sufficient for the Java verifier. Manually writing each constant pool index here is **for learning purposes only**; production codegen needs a reliable library to handle descriptors, stack maps, class loaders, and more opcode types.

## 8. Differences Easily Overlooked

### Condy caches the *value*, indy caches the *linkage*

Suppose a condy BSM takes a timestamp and returns `Instant.now()`. After successful resolution, `ldc` instructions on the same entry return **the same resolved reference**, without calling `Instant.now()` each time. Conversely, an indy target can contain code that calls `Instant.now()` and returns a new timestamp each time the target is invoked. "Dynamic" does not mean "recompute on each use".

### Indy bootstrap does not return the business result

If an indy BSM returns `"ok"` or a `MethodHandle`, that violates the contract; the result must be a `CallSite`. However, the target inside the `CallSite` can return `String`, `int`, `void`, etc., depending on the indy site's `MethodType`. Remember the **two-stage model**: linking (`BSM -> CallSite`) and invoking (`CallSite.target -> business result`).

### Both can appear in the same class file

The demo generates both tag 17 and tag 18 together in `GeneratedLinkageDemo.class`. Moreover, condy can be used as a **static argument** to an indy BSM. In that case, the JVM resolves condy to obtain metadata or a handle prior to/during the indy linking process according to dependency order. However, that does not turn condy into indy; it is simply **data supplied to the call's bootstrap**.

### Condy is not `static final`

A Java `static final` field has rules regarding class initialization and compile-time constant variables. Condy is a **symbolic reference in the run-time constant pool**. A `static final` object can be created in `<clinit>`, not necessarily related to `CONSTANT_Dynamic`. A `CONSTANT_Dynamic` can exist even if there is no Java field with that name.

### Bootstrap errors differ from errors when the target is executed

If an indy BSM runs and links successfully, but the **target** later throws `IllegalArgumentException`, `IOException`, or another exception, that is a target invocation error, not an automatic reason for `BootstrapMethodError`. Only when **resolution/linkage** encounters a problem does it belong to bootstrap/linkage errors. This is helpful when reading stack traces through dynamic language frameworks.

## 9. Linkage Errors, Failure Caching, and Concurrency Nuance

| Case | Outcome |
| --- | --- |
| Condy BSM returns an object of the requested type | Resolution succeeds, value is cached |
| Condy of type `int` but BSM returns `null` | Cannot convert to primitive → `BootstrapMethodError` |
| Condy BSM returns a reference not convertible to declared field type | `BootstrapMethodError` |
| Indy BSM returns `null` | `BootstrapMethodError` |
| Indy BSM returns a bare `String` or `MethodHandle` instead of `CallSite` | `BootstrapMethodError` |
| Indy BSM returns a `CallSite` with wrong `MethodType` | `BootstrapMethodError` |
| BSM throws a runtime/checked exception other than `Error` | JVM wraps the exception from BSM invocation into `BootstrapMethodError` with cause |
| BSM throws a subclass of `Error` | Resolution may fail with that `Error` itself |
| Condy has a static-argument dependency cycle to itself | JVMS specifies failure on re-resolution, possibly `StackOverflowError` |
| Condy reference whose resolution failed | Resolution failure is cached for subsequent uses of that reference; bootstrap does not auto-retry |
| Indy instruction whose linkage failed | Subsequent uses of that same instruction still fail, without automatically re-invoking the BSM |

**Concurrency nuance (important):** The JVMS allows **multiple threads to simultaneously attempt to resolve a symbolic reference**, and the bootstrap method handle **may be invoked concurrently**. The JVM selects the result of one invocation and publishes it to the threads; the others are allowed to complete, but their results are discarded. Therefore, the bootstrap counter incrementing to 1 in the single-threaded demo is observed behavior, **not a promise that every BSM system-wide runs strictly once with absolutely no duplicate side effects**.

If a bootstrap reads/writes shared mutable state, it must be thread-safe or idempotent. Do not perform business actions like charging payments, sending emails, or writing irreversible data inside a BSM under the assumption that it cannot be executed concurrently. Also avoid circular dependencies in condy static arguments: the JVM does not support resolving a condy that has a circular dependency back to the same symbolic reference.

## 10. When to Use Condy, When to Use Indy?

### Choose condy when you need a **value** resolved at runtime

Suitable examples:

- Special metadata values computed from `Lookup`, name, and static arguments.
- A reference to a `MethodHandle`, `VarHandle`, `Class`, or immutable domain descriptor.
- A configuration object not easily represented by a simple constant-pool literal, but only needing to be resolved **once per reference**.
- A literal-like value for a compiler generating bytecode that does not want to recreate an object on every use.

If business requirements demand a value that is always refreshed from an external service **on every read**, condy alone does not solve that problem; the resolved value is cached. You can return an object that manages its own refresh, but refreshing is **the object's behavior**, not re-running the condy BSM.

### Choose indy when you need a **call site**

Suitable when a compiler/runtime needs to:

- Link a call based on lookup context and method signature.
- Support dynamic language dispatch or call adapters.
- Use `ConstantCallSite` for dispatch that is fixed after linking.
- Use `MutableCallSite`/`VolatileCallSite` when needing to change the target at runtime with appropriate memory semantics.

**Do not think indy requires a mutable target.** `invokedynamic` can link to a `ConstantCallSite`; "dynamic" means **linking at runtime**, not that the target must change afterward.

### The two mechanisms can work together

```text
CONSTANT_Dynamic metadata
         |
   resolve once
         |
         v
    static bootstrap argument
         |
         v
 invokedynamic bootstrap
         |
         v
       CallSite
         |
         v
  repeated target invocations
```

This pattern is very useful for compilers/language runtimes wanting to pass resolved metadata into call site creation. However, you still need to respect type constraints, class loaders, packages/modules, and avoid creating cycles in condy dependencies.

## 11. `javap` Reading Checklist for Debugging

1. **Verify the class major version**: condy requires ≥ 55 (Java 11); indy requires ≥ 51.
2. **Distinguish tag 17/18**: `Dynamic` represents a value; `InvokeDynamic` represents a call site.
3. **Check the `NameAndType` descriptor**: condy must be a field descriptor; indy must be a method descriptor.
4. **Find the BootstrapMethods index**, do not confuse the CP index with the bootstrap index.
5. **Check the BSM `MethodHandle`**: reference kind, method name, and descriptor must match the BSM invocation contract.
6. **Check Lookup access and modules** if member resolution encounters `IllegalAccessError` or `BootstrapMethodError`.
7. **Check the BSM return value**: value compatible with condy field type, `CallSite` having the exact type matching the indy descriptor.
8. **Identify the cache scope**: condy symbolic reference vs indy instruction site. Do not assume a JVM-wide cache by name.
9. **Distinguish BSM exceptions from target exceptions**: linking errors can be sticky; target exceptions after linking are not a reason to re-invoke the bootstrap.
10. **Test concurrency** if the bootstrap has side effects: multiple initial invocations can run in parallel.
11. **Do not confuse output from the `Method.invoke` driver** with the opcodes proven by `javap` in the generated class.
12. **Cross-check with JVMS `5.4.3.6`** instead of guessing that every execution of `ldc`/`invokedynamic` re-runs the BSM.

## 12. Self-Check with Answers

**Question 1.** What are the two tags for `CONSTANT_Dynamic` and `CONSTANT_InvokeDynamic`?

**Answer:** 17 and 18. Both are in the CP, but represent **value resolution** and **call-site linkage**, respectively.

**Question 2.** If a condy has descriptor `Ljava/lang/String;`, what `Class<?>` type argument does the JVM typically pass to the BSM?

**Answer:** `String.class`; that is the field type of the constant.

**Question 3.** If an indy has descriptor `(I)Ljava/lang/String;`, does the BSM receive `Class<?>` or `MethodType`?

**Answer:** Typically a `MethodType` describing a method that takes `int` and returns `String`.

**Question 4.** A condy BSM returns `"v1"`. If the same `ldc` entry is executed 100 times, will the BSM be called 100 times?

**Answer:** No. After successful resolution, the JVM reuses the resolved value. The caveat to note is that multiple threads may **race to call the bootstrap during initial resolution**, not once per `ldc`.

**Question 5.** A `CONSTANT_InvokeDynamic` BSM returns a `MethodHandle` without creating a `CallSite`. Is this valid?

**Answer:** No. The BSM must return a non-null `CallSite` whose `MethodType` matches the indy entry.

**Question 6.** After indy has linked a `VolatileCallSite`, code calls `setTarget(newHandle)`. Does the BSM need to be called again?

**Answer:** No. The existing call site changes its target; the instruction continues using the same linked site.

**Question 7.** Two indy instructions at two different offsets point to the same tag 18 CP entry. Must they share a single `CallSite`?

**Answer:** No. Indy linkage rules apply **per instruction site**.

**Question 8.** A condy BSM returns a mutable list. Is the list's value automatically frozen?

**Answer:** No. The reference is cached, and the object can be mutated. Concurrency/state must be controlled separately.

**Question 9.** A condy BSM returns `null` for field descriptor `I`. Does the JVM use `0` by default?

**Answer:** No. `null` cannot be converted to primitive `int`; resolution will fail (typically `BootstrapMethodError`).

**Question 10.** Why does `javap -v` in the demo show `ldc #26` differently from `invokedynamic #29`?

**Answer:** `ldc` loads a resolved value from tag 17; `invokedynamic` executes a call site linked by tag 18. The two opcodes have different stack behaviors.

**Question 11.** A bootstrap has a plain static counter, and two threads resolve concurrently. Will the counter always increment by exactly one?

**Answer:** No. The bootstrap may be invoked concurrently multiple times during a resolution race, and an unsynchronized counter has a data race. Only one linkage result is chosen by the JVM.

**Question 12.** Does an exception thrown from indy's target `first(String)` after linkage automatically become a `BootstrapMethodError`?

**Answer:** No. That is an exception from **target invocation**, not a bootstrap resolution error.

**Question 13.** When needing to compute a `Class<?>` value corresponding to an enum field name at runtime resolution, which API should come to mind?

**Answer:** Condy with a bootstrap can fit; `ConstantBootstraps` has methods like `enumConstant` and `primitiveClass` depending on the goal, and you should check the exact Javadoc/signature.

**Question 14.** If a Java method declares `static final String x`, is `javac` guaranteed to generate `CONSTANT_Dynamic`?

**Answer:** No. That is a different Java field mechanism; condy is a distinct kind of constant-pool entry.

**Question 15.** Why is `CONSTANT_Dynamic` not "an invokedynamic that returns a constant"?

**Answer:** They differ in tag, descriptor, opcode, BSM type argument kind, result validation, and cache scope; condy does not create a `CallSite` just because it has a bootstrap.

## 13. Key Takeaways

- **Condy = tag 17 + field descriptor + `ldc` + typed value**, cached by the JVM after resolution.
- **Indy = tag 18 + method descriptor + `invokedynamic` + `CallSite`**, whose target is invoked on each execution of the instruction.
- **Both use `BootstrapMethods` and a `MethodHandle` bootstrap**, but the type argument is typically `Class<?>` and `MethodType`, respectively.
- **Cache scopes differ:** Condy is per symbolic reference in the run-time CP; indy is per `invokedynamic` instruction.
- **An indy target can be relinked without re-running the BSM** when using a mutable/volatile call site; a condy value has no `setTarget`.
- **"Dynamic" does not mean "run bootstrap on every use".** After successful resolution, the JVM reuses the resolved value or linkage accordingly.
- **Bootstraps can be invoked concurrently in a resolution race**, so avoid non-thread-safe side effects.
- **Read `javap -v` for real verification:** constant-pool tags, name/descriptor, BSM indexes, `ldc`/`invokedynamic` bytecode, and JVM stdout.

### Java SE 17 Official Sources

- [JVMS 4.4.10 — `CONSTANT_Dynamic_info` and `CONSTANT_InvokeDynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10)
- [JVMS 4.7.23 — `BootstrapMethods` class-file attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23)
- [JVMS 5.4.3 and `5.4.3.6` — Resolution, bootstrap, caching, and errors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6)
- [JVMS 6.5 — `ldc`, `ldc_w`, `ldc2_w`, and `invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html)
- [Oracle API — `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html)
- [Oracle API — `CallSite`, `MutableCallSite`, `VolatileCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html)
- [OpenJDK JEP 309 — Dynamic Class-File Constants](https://openjdk.org/jeps/309)