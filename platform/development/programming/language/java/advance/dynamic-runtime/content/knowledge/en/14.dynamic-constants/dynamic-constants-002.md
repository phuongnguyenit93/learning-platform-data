# 14.2. Dynamic Constant Bootstrap Contract: `Lookup`, Name, and Value `Class<?>`

## 1. Why Is a Dynamic Constant's Bootstrap a Separate Contract?

A **dynamic constant (dynamically-computed constant, often called *condy*)** is a value in the *runtime constant pool* resolved by the JVM by invoking a **bootstrap method**. In a class file, it is represented by `CONSTANT_Dynamic_info` (constant-pool tag **17**), introduced in class-file version **55.0 (Java 11)**.

The typical contract of a constant bootstrap is:

```java
public static Object bootstrap(
        MethodHandles.Lookup caller,
        String name,
        Class<?> type) throws Throwable {
    // Compute or look up a value compatible with type and return it.
    throw new UnsupportedOperationException("Illustration only");
}
```

This is **only an API signature template**, not a standalone runnable example. When executing an `ldc`/`ldc_w` instruction referencing `CONSTANT_Dynamic`, the JVM resolves the constant-pool entry, prepares the arguments, and invokes the bootstrap. The JVM checks the return value and then stores the resolution result so subsequent uses of the same symbolic reference do not have to recompute it.

Key difference from **`invokedynamic` bootstrap**:

```text
CONSTANT_Dynamic:
    bootstrap(Lookup, String, Class<?>, [static args...]) -> VALUE

CONSTANT_InvokeDynamic:
    bootstrap(Lookup, String, MethodType, [static args...]) -> CallSite
```

A dynamic constant has a **field descriptor** and produces a **value**; `invokedynamic` has a **method descriptor** and links a **call site**. In a constant bootstrap, the third parameter has the **`Class<?>` of the value**, **not `MethodType`**. Confusing the two protocols commonly causes linkage errors.

This article explains the exact meaning of each parameter, the data flowing from the class file to the bootstrap, type checking and failures, and provides verified Java 17+ examples including **direct method call**, **a real dynamic constant emitted in a class file**, and **standard JDK bootstraps**.

## 2. Data Available in `CONSTANT_Dynamic`

A dynamic constant in the constant pool has the logical structure:

```text
CONSTANT_Dynamic_info {
    tag = 17;
    bootstrap_method_attr_index;
    name_and_type_index;
}
```

`name_and_type_index` points to `CONSTANT_NameAndType_info` consisting of:

- The **unqualified name** of the constant, for example `GREETING` or `NUMBER`.
- The **field descriptor**, for example `Ljava/lang/String;` for `String`, `I` for `int`, `[I` for `int[]`.

`bootstrap_method_attr_index` points to an entry in the **`BootstrapMethods`** attribute of the same class file containing that constant pool. The entry specifies:

- Which **bootstrap method handle** the JVM needs to resolve and invoke.
- Which **zero or more static bootstrap arguments** will accompany the three default parameters.

There is no rule that `GREETING` must be a Java field named `GREETING`. Here the name is metadata of the **constant-pool entry**, used for the bootstrap. A `CONSTANT_Dynamic` does not have to correspond to any `static final` field in the source.

Logical example:

```text
Constant pool:
  #19 = Dynamic #0:GREETING:Ljava/lang/String;

BootstrapMethods:
  0: REF_invokeStatic CondyBootstrap.text:(Lookup,String,Class,String)Object
     Method arguments:
       "Hi, "

Code:
  0: ldc #19      // Dynamic #0:GREETING:Ljava/lang/String;
```

This is an **abbreviated version to explain the structure**. Full descriptors/indices and actual bytecode are in the `javap` example in section 8. `#19` is the **constant pool** index, `#0` is the **BootstrapMethods entry** index; do not confuse the two kinds of indices.

## 3. First Implicit Parameter: `MethodHandles.Lookup caller`

For a real dynamic constant, the JVM provides a `Lookup` whose lookup class is **the class whose runtime constant pool contains the symbolic reference being resolved**. In the following example, that class is `CondyClient`, because `CondyClient.class` contains `CONSTANT_Dynamic` and the `ldc` instruction using it.

The bootstrap can query:

```java
Class<?> requestingClass = caller.lookupClass();
```

This snippet **only illustrates inside the bootstrap body**, where the `caller` variable already exists.

Some main uses:

1. **Context identification**: knowing which class contains the dynamic constant. `caller.lookupClass().getName()` can be used for contract checks or diagnostics.
2. **Access control**: `Lookup` carries the caller's access privileges according to Java/JPMS rules. The bootstrap can use `caller.findStatic`, `findGetter`, `findConstructor`, ... to find accessible members.
3. **Does not automatically grant all permissions**: `Lookup` is not a mechanism to bypass `private`, module readability, `exports`, and `opens` system-wide.
4. **Not the most recent object calling `ldc` on the stack**: the lookup's privileges are tied to **the class referencing the dynamic constant**, and do not turn into the privileges of every method or library that further calls that class.

**Deep constraint in JVMS 17:** for a `CONSTANT_Dynamic`, the **first parameter in the descriptor of the bootstrap method handle must be `java.lang.invoke.MethodHandles.Lookup`**, otherwise linkage fails with `BootstrapMethodError`. That is a special constraint of condy; one should not assume that every other parameter must match each type rigidly, because the bootstrap is invoked using an adaptation mechanism equivalent to `MethodHandle.invokeWithArguments`.

For new designs, use the explicit signature `(Lookup, String, Class<?>)` for readability and to avoid ambiguous adaptations.

### Why is calling the bootstrap directly in Java not completely equivalent?

If code in `CondyBootstrap.main` calls directly:

```java
text(MethodHandles.lookup(), "GREETING", String.class, "Hi, ");
```

then `Lookup.lookupClass()` is **`CondyBootstrap`**, because that is the class actually calling `MethodHandles.lookup()`. By contrast, when the JVM resolves the constant in `CondyClient.class`, `Lookup.lookupClass()` will be **`CondyClient`**. The same Java bootstrap method can receive different lookup contexts depending on the path.

A direct call can also be executed multiple times as Java code wishes; it **does not automatically create `CONSTANT_Dynamic` or `BootstrapMethods` in the class file**.

## 4. Second Parameter: `String name`

`name` is the **unqualified name** taken from the `NameAndType` part of `CONSTANT_Dynamic`, for example `GREETING` or `NUMBER`.

It is **not required** to be:

- The name of the class containing the constant.
- A Java field name.
- The bootstrap method name.
- A parameter name in source.
- A name generated from the stack trace at runtime.

The bootstrap can **use** this name to decide the value:

```java
return prefix + name;
```

This is an **illustrative expression** when `prefix` and `name` are already available. There are also bootstraps that intentionally ignore `name`, for example `ConstantBootstraps.nullConstant` does not use this parameter.

Because the name is recorded in the class file, it is usually stable for the entry being resolved, but it is **not data authenticated by a user identity system**. You should not use `name` as proof that the caller is authorized to access secret data. When the name is generated by an untrusted toolchain/plugin, the bootstrap needs to validate that the name belongs to an allowed set and check `Lookup`/policy appropriately.

### Name, descriptor, and bootstrap owner are three different pieces of data

In disassembly:

```text
Dynamic #0:GREETING:Ljava/lang/String;
```

- `#0` → **bootstrap specifier index**.
- `GREETING` → **name** passed into the bootstrap.
- `Ljava/lang/String;` → **field descriptor**, which determines `Class<?> type` as `String.class`.

Meanwhile, `CondyBootstrap.text` appears in `BootstrapMethods` because that is the **bootstrap method handle**; having `GREETING` does not make the JVM look for a Java method named `GREETING`.

## 5. Third Parameter: `Class<?> type` of the **Value to Produce**

This is the core of the article. With `CONSTANT_Dynamic`, the JVM converts the field descriptor into the corresponding `Class<?>` and passes it to the bootstrap.

| Field descriptor | `Class<?> type` received | Example valid values |
| --- | --- | --- |
| `Ljava/lang/String;` | `String.class` | `"Hello"` |
| `Ljava/lang/Object;` | `Object.class` | Any reference, including `null` |
| `I` | `int.class` | Primitive `int` value; bootstrap can return `Integer` for the JVM to unbox |
| `J` | `long.class` | `long` value, e.g., bootstrap returns `Long` |
| `Z` | `boolean.class` | Primitive boolean, e.g., returning `Boolean.TRUE` |
| `[I` | `int[].class` | `int[]` array |
| `Ljava/time/DayOfWeek;` | `DayOfWeek.class` | `DayOfWeek.MONDAY` |

**Do not use `type.getClass()` to determine the kind of value.** `type` is already an instance of `java.lang.Class`: `type.getClass()` normally returns `Class.class`. To know the described type, use `type == String.class`, `type == int.class`, `type.getName()`, `type.isPrimitive()`, `type.isArray()`.

Validator example in a bootstrap:

```java
if (type != String.class) {
    throw new IllegalArgumentException("Expected String constant");
}
return "configured";
```

This is a **code snippet used inside the bootstrap body**, not a complete class. For a constant with descriptor `I`, `type` is `int.class`, **not** `Integer.class`. A bootstrap with return type `Object` can still return `Integer.valueOf(42)` and the JVM converts the result to primitive `int` according to the linkage contract.

### Result compatibility check

A dynamic constant bootstrap **returns a value** (which can declare Java return type `Object`), and then the JVM converts that value to type T of the field descriptor:

- If T is reference type `String`, the value must be a compatible `String` or `null`.
- If T is primitive `int`, an appropriate `Integer` can be unboxed to `int`; `null` cannot be unboxed.
- If the result is a reference of the wrong type (`String` when T is `int`, or `Integer` when T is `String`), conversion may cause `ClassCastException`; when condy validation fails with `ClassCastException`/`NullPointerException`, the JVM reports **`BootstrapMethodError`**.
- The bootstrap **does not need** to declare its Java return type as the exact type T. For example, `public static Object number(...) { return 42; }` is valid for a dynamic constant with descriptor `I`, because it autoboxes to `Integer` and then the JVM unboxes it.
- A dynamic constant's descriptor is a **field descriptor**, so it **cannot be `V`/`void`** like a method's return type.

The JVM handles the result according to the specification's conversion rules. When designing a bootstrap, you should **explicitly validate the target type and return a clear result**, rather than relying on an accidental conversion succeeding.

## 6. The Three Fixed Parameters and Static Bootstrap Arguments

The JVM builds the argument list in order:

```text
0. Lookup caller
1. String name
2. Class<?> type          (for condy)
3. staticArgument0        (if any)
4. staticArgument1        (if any)
...
```

They are used to invoke the **bootstrap method handle** with behavior equivalent to `invokeWithArguments`. Therefore, the most common bootstrap signature is:

```java
public static Object bootstrap(
        MethodHandles.Lookup caller,
        String name,
        Class<?> type,
        String prefix) {
    return prefix + name;
}
```

This is a sample method with **one static bootstrap argument** `String prefix`. In the hands-on example, the class generator attaches the string `"Hi, "` to the `BootstrapMethods` entry, so the JVM passes four arguments to the bootstrap when resolving `GREETING`.

**Static bootstrap arguments are not parameters passed when calling `ldc`.** They are metadata recorded in the class file and resolved by the JVM before invoking the bootstrap. They can represent kinds of constant-pool values permitted by the JVMS, including strings, numeric constants, class/method type/method handle references, and even nested dynamic constants.

For example, a bootstrap that additionally receives `Class<?> owner` or `MethodHandle factory` can use that metadata to look up data; however, the class generator must create the exact bootstrap specifier and arguments in the order accepted by the method handle. If the count/types are unsuitable, resolution fails. Varargs bootstraps are allowed, though they must also follow method-handle invocation rules.

**Point not to overstate:** the bootstrap invocation contract does not require the Java method to have the exact declared form `(Lookup,String,Class<?>)Object` for every position's type. The JVMS requires the first parameter of the **condy bootstrap method handle** to be `Lookup`; subsequent parameters are passed using the adaptation mechanism. In application code, keeping the standard signature is the most readable and least error-prone practice.

### Nested condy and cycles

A static argument can itself be another dynamic constant. The JVM resolves this argument before invoking the outer constant's bootstrap. However, **there must not be a dependency cycle**, for example constant A needing A, or A needing B while B needs A. JVMS 17 specifies that such resolution fails with `StackOverflowError` at the point where the pending constant must be resolved again.

Therefore, do not create bootstrap metadata with cycles, and do not design a bootstrap that executes code circling back to the very constant being resolved without a termination mechanism.

## 7. Java 17+ Hands-On — Part A: Defining the Bootstrap

We will use three files:

```text
CondyBootstrap.java       // Valid Java bootstrap methods
EmitCondyClient.java      // Experimental tool emitting a class file with a real CONSTANT_Dynamic
RunCondyClient.java       // Client that runs and observes linkage
```

The second file uses **`jdk.internal.org.objectweb.asm` built into the JDK** so the experiment is self-contained without downloading external dependencies. This is an **internal API, not supported for production**; `--add-exports` must be added when compiling and running the emitter tool. In real applications, you should use the **official ASM** library (`org.objectweb.asm`) or a supported bytecode library/framework instead of depending on `jdk.internal.*` packages. The experiment was tested on a JDK supporting Java 17; internal APIs may change in other JDK versions.

### File `CondyBootstrap.java`

```java
import java.lang.invoke.MethodHandles;

public final class CondyBootstrap {
    public static Object text(MethodHandles.Lookup caller,
                              String name, Class<?> type, String prefix) {
        System.out.println("bsmText:caller=" + caller.lookupClass().getSimpleName()
                + ",name=" + name + ",type=" + type.getSimpleName()
                + ",prefix=" + prefix);
        return prefix + name;
    }

    public static Object number(MethodHandles.Lookup caller,
                                String name, Class<?> type) {
        System.out.println("bsmNumber:caller=" + caller.lookupClass().getSimpleName()
                + ",name=" + name + ",type=" + type.getSimpleName());
        return 42;
    }

    public static Object wrong(MethodHandles.Lookup caller,
                               String name, Class<?> type) {
        System.out.println("bsmWrong:type=" + type.getSimpleName());
        return "not-an-int";
    }

    public static void main(String[] args) {
        Object answer = text(MethodHandles.lookup(), "GREETING",
                             String.class, "Hi, ");
        System.out.println("manual=" + answer);
    }
}
```

The methods do three important things:

- `text`: has the fixed parameters `(Lookup, name, type)` plus **one static argument `prefix`**; it returns a `String` inside `Object`.
- `number`: returns `42`, boxed into `Integer`; when the dynamic constant has descriptor `I`, the JVM converts it to primitive `int` successfully.
- `wrong`: intentionally returns `"not-an-int"` for a dynamic constant with descriptor `I`, leading to **`BootstrapMethodError`** when the JVM validates the result type.

`main` lets us run a **direct call** to `text`. That is a normal Java method check, not the real condy linkage path.

### Observing the direct call

Run separately:

```bash
javac --release 17 CondyBootstrap.java
java CondyBootstrap
```

Exact output:

```text
bsmText:caller=CondyBootstrap,name=GREETING,type=String,prefix=Hi, 
manual=Hi, GREETING
```

In the first line there is **a space after `Hi,`**: that is the trailing part of the static argument `"Hi, "` in the log, not an extra character from a formatting bug. The direct call creates `Lookup` inside `CondyBootstrap` itself, so `caller=CondyBootstrap`.

## 8. Java 17+ Hands-On — Part B: A Class File with a Real `CONSTANT_Dynamic`

Regular Java source does not have syntax to “write an arbitrary `CONSTANT_Dynamic`” and ask `javac` to emit that constant-pool entry. We use a bytecode emitter **only in this hands-on exercise** to generate class `CondyClient` with three static methods:

```text
CondyClient.readText()    -> ldc Dynamic GREETING:Ljava/lang/String;
CondyClient.readNumber()  -> ldc Dynamic NUMBER:I
CondyClient.readBad()     -> ldc Dynamic BAD:I
```

All methods are generated directly as bytecode, without a `CondyClient.java` source file. This helps **strictly distinguish** between manually calling a Java bootstrap and having the JVM resolve a real dynamic constant.

### File `EmitCondyClient.java` (internal JDK experimental tool)

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import jdk.internal.org.objectweb.asm.ClassWriter;
import jdk.internal.org.objectweb.asm.ConstantDynamic;
import jdk.internal.org.objectweb.asm.Handle;
import jdk.internal.org.objectweb.asm.MethodVisitor;
import jdk.internal.org.objectweb.asm.Opcodes;

public final class EmitCondyClient implements Opcodes {
    public static void main(String[] args) throws IOException {
        ClassWriter cw = new ClassWriter(0);
        cw.visit(V17, ACC_PUBLIC | ACC_SUPER, "CondyClient",
                 null, "java/lang/Object", null);

        Handle textBsm = new Handle(H_INVOKESTATIC, "CondyBootstrap", "text",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
                        + "Ljava/lang/Class;Ljava/lang/String;)Ljava/lang/Object;",
                false);
        Handle intBsm = new Handle(H_INVOKESTATIC, "CondyBootstrap", "number",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
                        + "Ljava/lang/Class;)Ljava/lang/Object;",
                false);
        Handle wrongBsm = new Handle(H_INVOKESTATIC, "CondyBootstrap", "wrong",
                "(Ljava/lang/invoke/MethodHandles$Lookup;Ljava/lang/String;"
                        + "Ljava/lang/Class;)Ljava/lang/Object;",
                false);

        addLdcMethod(cw, "readText", "()Ljava/lang/String;",
                new ConstantDynamic("GREETING", "Ljava/lang/String;",
                                    textBsm, "Hi, "), ARETURN);
        addLdcMethod(cw, "readNumber", "()I",
                new ConstantDynamic("NUMBER", "I", intBsm), IRETURN);
        addLdcMethod(cw, "readBad", "()I",
                new ConstantDynamic("BAD", "I", wrongBsm), IRETURN);

        cw.visitEnd();
        Files.write(Path.of("CondyClient.class"), cw.toByteArray());
    }

    private static void addLdcMethod(ClassWriter cw, String name,
                                     String descriptor, ConstantDynamic constant,
                                     int returnOpcode) {
        MethodVisitor mv = cw.visitMethod(
                ACC_PUBLIC | ACC_STATIC, name, descriptor, null, null);
        mv.visitCode();
        mv.visitLdcInsn(constant);
        mv.visitInsn(returnOpcode);
        mv.visitMaxs(1, 0);
        mv.visitEnd();
    }
}
```

**Note on practical limitations:** the example uses the JDK's internal ASM package only to generate a class file in a learning environment, with two `--add-exports` flags. This is **not production deployment advice**. If using official ASM, the equivalent types reside in `org.objectweb.asm` and require declaring the dependency and choosing a version compatible with the class-file version.

Explanation of the key lines:

1. `cw.visit(V17,...)` creates class-file version **61**, which supports condy (requires at least version 55).
2. `new Handle(H_INVOKESTATIC, "CondyBootstrap", "text", ... )` creates a **bootstrap method handle** to the Java static method. The descriptor specifies **`Lookup, String, Class, String -> Object`**.
3. `new ConstantDynamic("GREETING", "Ljava/lang/String;", textBsm, "Hi, ")` creates a symbolic dynamic constant: **name**, **field descriptor**, **bootstrap method**, and **one static bootstrap argument**.
4. `mv.visitLdcInsn(constant)` emits an `ldc` instruction referencing the dynamic constant-pool entry.
5. `ARETURN` is the opcode returning an object reference for `readText`; `IRETURN` returns primitive `int` for `readNumber` and `readBad`.
6. `Files.write(...)` outputs `CondyClient.class`; the tool does not need to create `CondyClient.java`.
7. For `long` or `double` condy types, the appropriate load opcode is `ldc2_w`, not a single-slot `ldc` like `String`/`int`. The emitter must choose the right kind/stack size; this example only uses `String` and `int`.

A `ConstantDynamic` represented by ASM is **metadata used to emit a class file**; this ASM object itself is **not** the runtime value the JVM returns for `ldc`.

### File `RunCondyClient.java`

```java
public final class RunCondyClient {
    public static void main(String[] args) {
        System.out.println("first=" + CondyClient.readText());
        System.out.println("second=" + CondyClient.readText());
        System.out.println("number=" + CondyClient.readNumber());

        for (int i = 0; i < 2; i++) {
            try {
                System.out.println("bad=" + CondyClient.readBad());
            } catch (BootstrapMethodError failure) {
                System.out.println("badFailure="
                        + failure.getClass().getSimpleName());
            }
        }
    }
}
```

`RunCondyClient` is a standalone Java source file **but depends on the `CondyClient.class` just generated by the emitter**. Create all files and run them in the exact order in the next section; do not compile `RunCondyClient.java` before running the emitter.

## 9. Sequential Run Commands and Verified Output

Place the three source files in the same directory and use JDK 17 or later. The following commands do not require Maven/Gradle:

```bash
javac --release 17 CondyBootstrap.java

javac --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED EmitCondyClient.java
java --add-exports java.base/jdk.internal.org.objectweb.asm=ALL-UNNAMED EmitCondyClient

javac --release 17 RunCondyClient.java

java CondyBootstrap
java RunCondyClient
```

Explanation:

- `CondyBootstrap.java` and `RunCondyClient.java` use public Java APIs so they compile with `--release 17`.
- `EmitCondyClient.java` must use `--add-exports` for both **compiling and running** because it uses an internal package. Do not combine `--release 17` with `--add-exports` for internal APIs in the emitter compilation command.
- The generated file is named `CondyClient.class` with class-file version **61** due to `V17`; when compiling `RunCondyClient`, `javac` finds that class file on the current classpath.
- `java RunCondyClient` does not need `--add-exports`: **the runtime class and bootstrap do not depend on ASM**. The emitter finished its job before execution.

### 9.1. `java CondyBootstrap`: direct call

```text
bsmText:caller=CondyBootstrap,name=GREETING,type=String,prefix=Hi, 
manual=Hi, GREETING
```

### 9.2. `java RunCondyClient`: resolving a real dynamic constant

```text
bsmText:caller=CondyClient,name=GREETING,type=String,prefix=Hi, 
first=Hi, GREETING
second=Hi, GREETING
bsmNumber:caller=CondyClient,name=NUMBER,type=int
number=42
bsmWrong:type=int
badFailure=BootstrapMethodError
badFailure=BootstrapMethodError
```

The above results have been verified with a Java 17 program and the class file generated by the emitter.

### Analysis of each phenomenon

**`caller=CondyClient`**: the bootstrap is not called from `CondyBootstrap.main`; instead, the JVM is resolving a symbolic reference in the runtime constant pool of class `CondyClient`. `Lookup` is created according to that context.

**`name=GREETING`, `type=String`**: the JVM takes the name from `CONSTANT_NameAndType` and turns the field descriptor `Ljava/lang/String;` into `String.class`, rather than sending `MethodType` or `String.class.getClass()`.

**`prefix=Hi, `**: this is the static bootstrap argument recorded in the class file. `RunCondyClient` **does not** pass `prefix` to `readText()`; that method has no parameters.

**`second=...` without a second `bsmText`**: the same symbolic reference was already resolved successfully and the result is reused. In this sequential experiment, the bootstrap runs only once for the `GREETING` entry.

**`bsmNumber:...type=int`**: field descriptor `I` makes `type == int.class`; the `number` bootstrap returns `Integer` from boxing `42`, and the JVM unboxes it to primitive `int`, so `number=42`.

**`bsmWrong` appears once**: the bootstrap returns `String` for descriptor `I`; result validation fails and the JVM throws `BootstrapMethodError`. The next use of the same reference still fails; the bootstrap is not run again in this sequential experiment.

**Two `badFailure=BootstrapMethodError` lines** prove the failure is recorded during dynamic constant resolution, rather than a Java `ClassCastException` accidentally occurring in `RunCondyClient`.

## 10. Inspecting the Class File with `javap -c -v -p`

Run:

```bash
javap -p -c -v CondyClient
```

In the output of the verified class, there are representative lines:

```text
major version: 61

#19 = Dynamic #0:#18        // #0:GREETING:Ljava/lang/String;
#30 = Dynamic #1:#29        // #1:NUMBER:I
#38 = Dynamic #2:#37        // #2:BAD:I

0: ldc #19                  // Dynamic #0:GREETING:Ljava/lang/String;
0: ldc #30                  // Dynamic #1:NUMBER:I
0: ldc #38                  // Dynamic #2:BAD:I

BootstrapMethods:
  0: REF_invokeStatic CondyBootstrap.text:...
  1: REF_invokeStatic CondyBootstrap.number:...
  2: REF_invokeStatic CondyBootstrap.wrong:...
```

Here the display is **intentionally abbreviated**: `...` replaces full JVM descriptors and constant pool identifier constants; this is **not a complete `javap` snippet to copy and run**. The numbers `#19`, `#30`, `#38` are from one specific test run and may vary by toolchain. Each `0: ldc ...` line belongs to **a different method**, so all three have bytecode offset `0`.

Points to check in a real disassembly:

1. There is `Dynamic` (tag 17), **not `InvokeDynamic` (tag 18)**, at the constant-pool entries containing `GREETING`, `NUMBER`, `BAD`.
2. Each `Dynamic` records a **field descriptor** (`Ljava/lang/String;`, `I`).
3. `Code` contains **`ldc`** referencing the `Dynamic` entries.
4. There is a **`BootstrapMethods` attribute** containing **three entries** with method handles pointing to `CondyBootstrap.text`, `CondyBootstrap.number`, `CondyBootstrap.wrong`.
5. The `text` entry also has a static argument: `"Hi, "`.
6. The class has major version `61`, corresponding to Java 17.

**The `invokedynamic` opcode is not needed to use a dynamic constant.** This is a bytecode reading trap: `CONSTANT_Dynamic` is normally loaded via `ldc`, whereas `CONSTANT_InvokeDynamic` is used by the `invokedynamic` instruction. Both share the bootstrap metadata mechanism but produce **different kinds of results**.

## 11. Resolution Timing, Caching, and Multithreading

For an unresolved `CONSTANT_Dynamic`, the JVM can compute the value when executing an instruction that needs the constant for the first time. After successful resolution:

- The result is stored for the **symbolic reference in the runtime constant pool**.
- Subsequent uses of the same symbolic reference receive the resolved result, **without running the bootstrap repeatedly**.
- If the value is a reference to a mutable object, being “constant” **does not** make that object immutable. Any code holding the reference can still mutate the object's contents if the object's class/API allows it.
- If resolution fails, subsequent uses of the same reference continue to receive the error per JVMS rules; do not treat the next call as an opportunity to automatically retry the bootstrap.
- Do not confuse the storage scope of a runtime constant-pool entry with a “JVM-wide cache by constant name”. Two different classes/constant-pool entries may use the same name/type but are different symbolic references.

**Concurrency point to note:** if multiple threads simultaneously try to resolve the same unresolved reference, the JVMS allows the bootstrap method handle to be **invoked concurrently**. The JVM selects one result and installs it publicly for all threads; other bootstrap results may be discarded. Therefore, one should not rely on the absolute statement “a Java bootstrap method will only execute strictly once even under a race”.

Bootstraps with side effects should be designed to be thread-safe, or idempotent when needed. In the example in section 9, the calls are executed **sequentially**, so observing a single bootstrap execution is expected and reproducible.

### 11.1. A dynamic constant can be `null`

A reference-type condy can validly resolve to **`null`**. This is not a bootstrap error if the field descriptor is a reference. Conversely, for a primitive descriptor like `I`, `null` cannot be unboxed and causes resolution to fail.

The specification does not require a new `String`/class object to be created on every `ldc`: within the same symbolic reference, a resolved value is reused; `null` is also a value that can be reused for a reference type.

## 12. Built-in Standard Constant Bootstraps: `ConstantBootstraps`

Java 11+ provides `java.lang.invoke.ConstantBootstraps` in the `java.base` module. It collects standard bootstrap methods; several can be referenced by bytecode generators instead of writing bootstraps from scratch.

Typical examples:

| Standard API | Meaning | Related parameters |
| --- | --- | --- |
| `nullConstant` | Returns `null` for a reference type | `type` must be a reference type |
| `primitiveClass` | Returns the `Class<?>` of a primitive based on the descriptor in `name` | `name` like `"I"`; `type` must be `Class.class` |
| `enumConstant` | Returns an enum constant based on name and enum type | `name` like `"MONDAY"`; `type` like `DayOfWeek.class` |
| `getStaticFinal` | Retrieves the value of a valid static-final field | `name`, `type`, sometimes declaring class |
| `fieldVarHandle`, `staticFieldVarHandle`, `arrayVarHandle` | Creates the appropriate `VarHandle` | `Lookup` and metadata about field/array |
| `explicitCast` | Converts a value to the requested type | `Class<?> dstType` and static argument |
| `invoke` | Invokes a `MethodHandle` with static arguments | `type`, method handle, and args |

Some APIs **intentionally ignore** `lookup`/`name`, while some APIs **use them** to look up metadata or check permissions. Do not assume all standard bootstraps interpret `name` in the same way.

### Second Java 17+ example — using standard APIs directly

Save file **`ConstantBootstraps17Demo.java`**:

```java
import java.lang.invoke.ConstantBootstraps;
import java.lang.invoke.MethodHandles;
import java.time.DayOfWeek;

public final class ConstantBootstraps17Demo {
    public static void main(String[] args) {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        Object blank = ConstantBootstraps.nullConstant(
                lookup, "IGNORED", String.class);
        System.out.println("null=" + (blank == null));

        DayOfWeek day = ConstantBootstraps.enumConstant(
                lookup, "MONDAY", DayOfWeek.class);
        System.out.println("enum=" + day);

        Class<?> ptype = ConstantBootstraps.primitiveClass(
                lookup, "I", Class.class);
        System.out.println("primitive=" + ptype);

        try {
            ConstantBootstraps.nullConstant(lookup, "WRONG", int.class);
            System.out.println("primitiveNull=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("primitiveNull=rejected");
        }
    }
}
```

Compile/run:

```bash
javac --release 17 ConstantBootstraps17Demo.java
java ConstantBootstraps17Demo
```

Verified output:

```text
null=true
enum=MONDAY
primitive=int
primitiveNull=rejected
```

**Important:** this code **calls the standard bootstraps directly in Java**, so it is an example testing API behavior, **not** proof that this class contains a real `CONSTANT_Dynamic`. To have the JVM use these APIs to link condy, a bytecode generator/compiler must reference them in `BootstrapMethods`.

In particular, `primitiveClass(lookup, "I", Class.class)` clearly shows that **`name` can carry a primitive's descriptor** per that standard bootstrap's contract, while the constant's requested result has type **`Class.class`**. `Class<?> type` is not a primitive type in this case, even though the returned value is `int.class`.

## 13. What Happens If a Bootstrap Violates the Contract?

Commonly confused errors:

### 13.1. Wrong third parameter: using `MethodType` instead of `Class<?>`

If bytecode describes a condy, the JVM prepares a `Class<?>` taken from the **field descriptor**. A bootstrap written as if receiving `invokedynamic`'s `MethodType` may fail to receive a compatible argument, causing an error **when invoking the bootstrap method handle**. The result is a linkage failure, usually surfacing as `BootstrapMethodError` if the invocation error is not directly an `Error`.

Prevention: write the standard `(Lookup,String,Class<?>)` signature for condy. Only use `MethodType` in the **call site** bootstrap protocol or when it is a custom static argument you designed.

### 13.2. Bootstrap returns `CallSite` instead of a value

`CONSTANT_Dynamic` expects a **value convertible to type T**, not a `CallSite`. If `type == String.class` and the bootstrap returns a `ConstantCallSite`, the result is incompatible with `String`, so validation fails.

Special case: if the field descriptor is `Ljava/lang/Object;`, a `CallSite` object is also an `Object` that can be valid **as a value**; however, that **does not turn** the constant into `invokedynamic`. The JVM will simply treat that `CallSite` as an object loaded via `ldc`.

### 13.3. Bootstrap returns `String` for descriptor `I`

The `wrong` example in sections 7–9 proved this:

```text
bsmWrong:type=int
badFailure=BootstrapMethodError
```

The error is not in the name `BAD`, but in **the incompatibility of the result type**. The JVM knows the type from descriptor `I`, and does not infer the type from the runtime object returned by the bootstrap.

### 13.4. Primitive constant but returning `null`

`null` is valid for reference descriptors like `Ljava/lang/String;`; invalid when the target type is primitive. Validation will fail due to unboxing `null`, usually reported as `BootstrapMethodError`.

### 13.5. Bootstrap method handle cannot be invoked or `Lookup` lacks permissions

To resolve the constant, the JVM must resolve the bootstrap method handle and static arguments according to class-file access rules. When the bootstrap itself looks up private fields/methods, `Lookup` cannot bypass JPMS and Java visibility. Errors occurring when resolving or invoking the method handle can manifest as various linkage/error types per the specification; not always `ClassCastException`.

Check the **bootstrap owner**, descriptors, class loader/module graph, and permissions of `caller.lookupClass()` before concluding the `bootstrap` method was written wrong.

### 13.6. Bootstrap throws an exception

According to JVMS 17 §5.4.3.6, if bootstrap invocation throws an **`Error`**, resolution fails with that error. If it throws an exception **not in the `Error` hierarchy**, the JVM creates a `BootstrapMethodError` and preserves the original exception as the cause. If an error occurs during the return type check step, `ClassCastException`/`NullPointerException` also causes resolution to report `BootstrapMethodError`.

This differs from **calling a Java bootstrap manually**: a direct call still follows the exception thrown by the Java method itself and does not automatically perform the `CONSTANT_Dynamic` JVM validation step.

## 14. Comparison Table: `CONSTANT_Dynamic` vs. `CONSTANT_InvokeDynamic`

| Property | Dynamic constant — condy | Dynamic call — indy |
| --- | --- | --- |
| Constant-pool tag | **17 — `CONSTANT_Dynamic`** | **18 — `CONSTANT_InvokeDynamic`** |
| NameAndType descriptor | **Field descriptor** (`I`, `Ljava/lang/String;`, ...) | **Method descriptor** (`(I)Ljava/lang/String;`, ...) |
| First bootstrap parameter is usually | `MethodHandles.Lookup` of the class containing the reference; for condy bootstrap BMH, the first parameter must be Lookup | `MethodHandles.Lookup` of the caller per common protocol |
| Second parameter | `String name` | `String name` |
| Third parameter | **`Class<?> type`** | **`MethodType type`** |
| Required result | Value compatible with the field descriptor | `CallSite` whose target type matches the method descriptor |
| Typical opcode | **`ldc` / `ldc_w`**, `ldc2_w` for two-slot types | **`invokedynamic`** |
| BootstrapMethods attribute | Present when the constant pool uses `CONSTANT_Dynamic` | Present when the constant pool uses `CONSTANT_InvokeDynamic` |
| Successful linkage caching | Per symbolic reference in the runtime constant pool | Per resolved instruction |
| From regular Java source | No direct syntax for custom `CONSTANT_Dynamic` | Java compiler can auto-emit via lambda/method reference/string concat |
| Notable errors | Wrong result type, missing permissions, static args cycle, bootstrap failure | Wrong/null `CallSite`/target type mismatch, bootstrap failure |

`BootstrapMethods` can serve **both** kinds of constant-pool entries, so merely seeing this attribute does not tell you whether the class uses condy or indy. To verify, you must read the **constant-pool tag**, **NameAndType descriptor**, the using instruction, and the corresponding bootstrap entry.

## 15. Misconceptions to Eliminate

1. **“A bootstrap named `bootstrap` is automatically found by the JVM by name.”** False: class-file metadata selects a specific bootstrap method handle; the Java method name is up to the author.
2. **“`name` is the name of a static field.”** Not required. It is the unqualified name of the condy entry.
3. **“The third parameter is always `MethodType`.”** False for condy: the JVM provides the `Class<?>` of the value.
4. **“`type == Integer.class` if the descriptor is `I`.”** False: it is `int.class`.
5. **“A bootstrap with `Object` return type is invalid for an `int` constant.”** False: the JVM can convert a compatible wrapper to primitive, as in the `42` demo.
6. **“`ConstantCallSite` is required for condy.”** False: condy needs a **value**; `CallSite` is the result needed for invokedynamic.
7. **“Because we called `CondyBootstrap.text` in Java, the class has condy.”** False: a direct method call does not emit `CONSTANT_Dynamic`.
8. **“Every `ldc` invokes the bootstrap again.”** False after the same symbolic reference has been resolved successfully.
9. **“The bootstrap is guaranteed to run strictly once in every race.”** Not absolute; multiple threads can invoke the bootstrap concurrently before the JVM chooses the resolution result.
10. **“A dynamic constant guarantees the returned object is immutable.”** False: the result can be a mutable object; constant resolution only guarantees the mechanism of storing the value for the symbolic reference.
11. **“Having `BootstrapMethods` means the class uses `invokedynamic`.”** False: the attribute also holds bootstrap specifiers for `CONSTANT_Dynamic`.
12. **“`null` is always a bootstrap failure.”** False if the target type is a reference; true that `null` cannot be unboxed to a primitive.
13. **“You can set `void.class` as the type of a condy.”** No: a field descriptor cannot represent `void`.
14. **“To check condy you just need to look at stdout.”** No: stdout proves the method ran, but does not prove the JVM resolved `CONSTANT_Dynamic`; `javap -v` is needed.
15. **“Being given `Lookup` means you can read any private field.”** False: lookup permissions are tied to caller/JPMS and Java access rules.

## 16. Checklist for Debugging a Dynamic Constant Bootstrap

When an application reports `BootstrapMethodError` or a dynamic constant has the wrong value:

1. **Pick the exact class file being executed** and use `javap -p -c -v` to get the actual bytecode.
2. **Look for constant-pool tag `Dynamic`**, do not confuse with `InvokeDynamic`.
3. **Read the name and field descriptor**; convert the descriptor to the expected `Class<?>` (`I` → `int.class`, `Ljava/lang/String;` → `String.class`).
4. **Find the bootstrap entry** via `bootstrap_method_attr_index`; confirm the owner/name/descriptor of the bootstrap method handle.
5. **Check the first parameter** of the bootstrap method handle is `MethodHandles.Lookup` per the JVMS constraint for condy.
6. **Check the order of static args** after `Lookup, String, Class<?>`: are any missing, wrong type, or swapped in order?
7. **Verify bootstrap accessibility**: class loader, Java visibility, and JPMS module permissions.
8. **Check code using `caller`**: is `caller.lookupClass()` the right class containing the condy? Direct Java calls and JVM condy resolution can differ.
9. **Check the actual result type**: reference cast, primitive boxing/unboxing, and is `null` valid for the descriptor?
10. **If the error involves a cycle**, check static arguments referencing other condy entries in a cycle or the bootstrap calling back into the constant being resolved.
11. **Distinguish first-time failure from memoized failure**: failure when resolving the same symbolic reference is not automatically reset by the next call.
12. **Check concurrency** if the bootstrap uses a cache, counter, logging, or external resources.
13. **Read the cause of `BootstrapMethodError`** and the stack trace of the method handle/bootstrap; do not discard the original information.
14. **Do not conclude from a single log line**: only disassembly tells whether this is a direct Java call or runtime dynamic-constant resolution.

## 17. Self-Check Questions (with Answers)

1. **What are the first three parameters of a condy bootstrap?** `MethodHandles.Lookup`, `String name`, `Class<?> type`.
2. **Which pair of information determines `name` and `type`?** `NameAndType` of `CONSTANT_Dynamic`: unqualified name + field descriptor.
3. **If the descriptor is `I`, what `type` does the JVM pass?** `int.class`.
4. **What if the descriptor is `Ljava/lang/String;`?** `String.class`.
5. **Can bootstrap `Object number(...) { return 42; }` serve an `I` condy?** Yes, via `Integer` boxing and valid JVM unboxing.
6. **What if bootstrap `Object wrong(...) { return "x"; }` serves an `I` condy?** Type validation fails, which can become `BootstrapMethodError`; verified.
7. **Where does `caller.lookupClass()` come from when resolving a real condy?** The class containing the runtime constant-pool symbolic reference being resolved.
8. **Must `name` match any Java field?** No.
9. **Where do static bootstrap arguments reside?** In the `BootstrapMethods` entry specified by class-file metadata.
10. **Are static args passed after the three JVM-generated parameters?** Yes, in the order recorded in the bootstrap specifier.
11. **Must the result of a condy bootstrap be a `CallSite`?** Not required and not the contract; it is a **value** compatible with the field descriptor.
12. **For invokedynamic, what is the third parameter usually?** `MethodType`, because a call site has a method descriptor.
13. **To verify a real condy, which opcode do you look for?** Usually `ldc`/`ldc_w` (and `ldc2_w` for two-slot types), along with `CONSTANT_Dynamic` and `BootstrapMethods`.
14. **Can `BootstrapMethods` exist even without an `invokedynamic` opcode?** Yes, it also serves condy.
15. **Is using `ConstantBootstraps.nullConstant(..., String.class)` returning `null` valid?** Yes, because `String` is a reference type.
16. **What about using `nullConstant(..., int.class)`?** The standard API rejects it because `int` is primitive.
17. **If the same condy symbolic reference is used twice in a row, does the bootstrap run again?** Not after successful resolution; in the sequential demo there is only one bootstrap log.
18. **Under a race, can there be multiple bootstrap invocations?** Yes; the JVM selects the resolution result, so the bootstrap needs to handle concurrency when it has side effects.
19. **Why does the article have an emitter file?** Regular Java source cannot specify a custom `CONSTANT_Dynamic`; bytecode must be generated or a supporting compiler tool must be used.
20. **What is the biggest mistake when writing a condy bootstrap by copying invokedynamic code?** Using `MethodType` and returning `CallSite` instead of receiving `Class<?>` and returning a value of the right type.

## 18. Official Java SE 17 / JVMS 17 References

- [JVMS 17 — §4.4.10 `CONSTANT_Dynamic_info`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.4.10): constant-pool structure, field descriptor, and bootstrap index.
- [JVMS 17 — §4.7.23 `BootstrapMethods`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.23): bootstrap method handles and static arguments.
- [JVMS 17 — §5.4.3.6](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6): resolution process, passing `Lookup/name/Class`, result checking, errors, and concurrency.
- [JVMS 17 — §6.5 `ldc` / `ldc_w` / `ldc2_w`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html#jvms-6.5.ldc): loading values from the runtime constant pool.
- [Java SE 17 — `ConstantBootstraps`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantBootstraps.html): standard bootstrap methods for dynamically-computed constants.
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup class, access privileges, handle creation methods.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): reading class files at the instruction, constant pool, and attribute levels.

**Conclusion:** For **`CONSTANT_Dynamic`**, the JVM invokes the bootstrap with the context **`Lookup caller`**, **`String name`**, and **`Class<?> type` of the field descriptor**, plus static bootstrap arguments if any; the bootstrap must produce **a value compatible** with type. Mastering these three parameters will help you distinguish condy from `invokedynamic`, design bootstraps that follow the contract, understand caching, and trace errors through real bytecode.