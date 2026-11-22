# 11.2 Constant pool structure, invocation name, method descriptor, and `BootstrapMethods`

Java's `invokedynamic` bytecode instruction does not point directly to a method belonging to a fixed class like `invokestatic` or `invokevirtual`. Instead, it points to a **dynamic call site descriptor** in the class file's `constant_pool`. That descriptor specifies the **invocation name**, the **call type** (method descriptor), and the **entry in the `BootstrapMethods` table** that the JVM must use to link the call to a `CallSite`.

Four pieces to distinguish:

1. **The `invokedynamic` bytecode:** a call instruction whose operand points to an entry in the constant pool.
2. **`CONSTANT_InvokeDynamic_info`:** a constant pool entry containing a bootstrap-method record index and a `NameAndType` index.
3. **`CONSTANT_NameAndType_info`:** the place that stores the **symbolic invocation name** and the **JVM method descriptor**.
4. **`BootstrapMethods` attribute:** a **class file** table containing a method handle to the bootstrap method and its list of static arguments.

During linkage, the JVM passes information about the caller, the invocation name and type, and the static arguments to the bootstrap method. The bootstrap method returns a `java.lang.invoke.CallSite`; the target of the call site determines the code executed at that call site. Understanding this structure helps you read `javap -v`, explain lambdas/method references and string concatenation optimizations, as well as debug dynamic linkage without confusing **site name**, **bootstrap method name**, and **target method name**.

> **Version:** Java examples are compiled with `javac --release 17` and run on JDK 17+. How many `invokedynamic` call sites the compiler generates and the `#n` indices in `javap` are build/toolchain details; the examples have been tested, but **indices are not a stable interface** to hard-code. Structural content is based on the JVMS and the `java.lang.invoke` API of Java SE 21.

## 1. Where does `invokedynamic` differ from regular bytecode calls?

With regular calls such as `invokestatic`, the operand points to a symbolic method reference, carrying the owning class/interface name, method name, and descriptor. The JVM resolves this reference according to method linkage rules.

With `invokedynamic`:

```text
Bytecode in a method:
    ... push argument values onto operand stack ...
    invokedynamic #7, 0
    ... use result ...

#7 = CONSTANT_InvokeDynamic
        |
        +-- bootstrap_method_attr_index --> BootstrapMethods[0]
        |                                     |
        |                                     +-- bootstrap method handle
        |                                     +-- static arguments [...]
        |
        +-- name_and_type_index -----------> CONSTANT_NameAndType
                                              |
                                              +-- name: "makeConcatWithConstants"
                                              +-- descriptor: (String,int)String

When linkage succeeds:
    bootstrap(...) -> CallSite -> target MethodHandle
    invokedynamic  -> invokes target according to linked descriptor
```

The diagram above is a **conceptual illustration**, with type names/descriptions shortened for readability; actual constant-pool indices and bootstrap indices must be taken from your actual class file.

Key differences:

- `CONSTANT_InvokeDynamic` **does not have a field pointing to the class owning the target method** like `CONSTANT_Methodref`. The bootstrap method determines the call behavior.
- `NameAndType` is the name/descriptor **of the call site**, not necessarily the name of a Java method existing in the source class.
- The JVM still **enforces type safety**: the `CallSite` returned by the bootstrap must have a type matching the method descriptor declared at the dynamic call site.
- After linkage, each **specific `invokedynamic` instruction** is bound to its own linkage result. One constant-pool entry can be shared by multiple instructions, but the JVMS still handles linkage per instruction site.
- `invokedynamic` does not mean **running the bootstrap on every call**. The bootstrap serves linkage; afterward, calls are executed through the call site's target.

## 2. Constant pool in the class file: relevant entry types

`constant_pool` is a table of tagged structures in `ClassFile`, indexed starting from **1**. Many entries only store **indices to other entries**, so reading an entry often requires following a chain of references. When `javap -v` displays `#7`, that is a **constant pool index**; whereas `#0` in the comment of `InvokeDynamic #0:#8` is usually the **bootstrap_methods array index**, not constant pool index 0.

| Entry | Tag | Role in the `invokedynamic` structure |
| --- | --- | --- |
| `CONSTANT_Utf8_info` | 1 | Stores name strings, descriptors, attribute names, recipes, or related component names |
| `CONSTANT_Class_info` | 7 | Describes a class/interface by name; can be used in bootstrap arguments |
| `CONSTANT_String_info` | 8 | References a `String` constant, e.g., a recipe for string concatenation |
| `CONSTANT_NameAndType_info` | 12 | Pair of **name** and **descriptor** of the call site |
| `CONSTANT_MethodHandle_info` | 15 | Reference to a method/field with a reference kind; used to represent the **bootstrap method handle** or impl handle |
| `CONSTANT_MethodType_info` | 16 | Descriptor of a method type; often used as a static argument for lambda metafactory |
| `CONSTANT_Dynamic_info` | 17 | **Dynamic constant** (`condy`), not a dynamic call |
| `CONSTANT_InvokeDynamic_info` | 18 | Describes a **dynamic call site** and links to `BootstrapMethods` + `NameAndType` |

Entries of type `Methodref`/`InterfaceMethodref` (tag 10/11) can also appear **indirectly** through a `CONSTANT_MethodHandle` to a bootstrap or implementation method. It is not that `InvokeDynamic` itself has a `class_index` like `Methodref`.

### 2.1. Binary structure of `CONSTANT_InvokeDynamic_info`

According to the JVMS, the data layout is:

```text
CONSTANT_InvokeDynamic_info {
    u1 tag;                         // 18
    u2 bootstrap_method_attr_index; // index into BootstrapMethods.bootstrap_methods[]
    u2 name_and_type_index;         // CONSTANT_NameAndType_info index
}
```

This is a **class file structure description**, not Java code to compile. `u1` is an unsigned one-byte integer; `u2` is an unsigned two-byte integer.

- `tag = 18` identifies a `CONSTANT_InvokeDynamic`.
- `bootstrap_method_attr_index` is a **0-based index** into the `bootstrap_methods` array of the `BootstrapMethods` attribute in the same class file.
- `name_and_type_index` is a **valid 1-based constant pool index**, pointing to a `CONSTANT_NameAndType_info` with a method descriptor.

The `bootstrap_method_attr_index` field does **not** point directly to a `CONSTANT_MethodHandle` entry. It points to **a record in the attribute**, and that record contains `bootstrap_method_ref` pointing to `CONSTANT_MethodHandle`.

### 2.2. `CONSTANT_NameAndType_info`

`NameAndType` has the structure:

```text
CONSTANT_NameAndType_info {
    u1 tag;             // 12
    u2 name_index;      // CONSTANT_Utf8_info of the name
    u2 descriptor_index;// CONSTANT_Utf8_info of the descriptor
}
```

In `invokedynamic`, the descriptor must be a **method descriptor**; in `CONSTANT_Dynamic` (dynamic constant), the descriptor is a **field descriptor**. This is a very quick way to avoid confusing `condy` with a dynamic call site.

Example:

```text
NameAndType
  name       = "apply"
  descriptor = (Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;
```

The name `apply` here **does not automatically point to** the `apply` method on the `Transformer` interface. It is information passed to `LambdaMetafactory` to create the required behavior; the JVM does not automatically look up `Transformer.apply` like an `invokeinterface` instruction just because the name is `apply`.

### 2.3. `CONSTANT_MethodHandle_info` and `CONSTANT_MethodType_info`

A bootstrap method is represented by a **MethodHandle constant**. In `javap -v`, you often see:

```text
MethodHandle 6:#...  // REF_invokeStatic ...metafactory:(...)CallSite
```

The number `6` here is `reference_kind` indicating `REF_invokeStatic`, which is different from a bootstrap index or CP tag. It indicates how the method handle references a method that the JVM can invoke.

A `MethodType` constant contains **a method descriptor**, not executable code. In `LambdaMetafactory.metafactory`, `MethodType`s typically describe the SAM method type and the instantiated method type; the `MethodHandle` static argument points to the implementation method. It is necessary to distinguish **method descriptors at multiple levels**: the bootstrap method type, the call site type, and the type of the method implemented by the lambda.

## 3. Where does `BootstrapMethods` live and what does it contain?

`BootstrapMethods` is a **`ClassFile`-level attribute**, not a `CONSTANT_InvokeDynamic` entry and not regular method bytecode. A class file has at most one `BootstrapMethods` attribute; when the constant pool contains `CONSTANT_InvokeDynamic` or `CONSTANT_Dynamic`, the class file must provide this attribute in the corresponding format.

Abbreviated structure:

```text
BootstrapMethods_attribute {
    u2 attribute_name_index;
    u4 attribute_length;
    u2 num_bootstrap_methods;
    {
        u2 bootstrap_method_ref;
        u2 num_bootstrap_arguments;
        u2 bootstrap_arguments[num_bootstrap_arguments];
    } bootstrap_methods[num_bootstrap_methods];
}
```

This is a file structure according to the JVMS, **not** a Java class. Key components:

- `attribute_name_index`: constant-pool index of the UTF-8 string `"BootstrapMethods"`.
- `num_bootstrap_methods`: number of records in the bootstrap table.
- `bootstrap_method_ref`: CP index to `CONSTANT_MethodHandle_info` for the bootstrap method.
- `bootstrap_arguments[]`: array of **constant-pool indices** for additional static arguments; not the runtime arguments of the dynamic call.
- A `CONSTANT_InvokeDynamic` selects **one record** via `bootstrap_method_attr_index`; records can share the same bootstrap method handle but have different static arguments.

Static arguments are represented by valid loadable constants/types in the constant pool such as `String`, numbers, `Class`, `MethodType`, `MethodHandle`, and `CONSTANT_Dynamic` when valid. The JVM **resolves** them into values and passes them to the bootstrap. The `bootstrap_arguments[]` array is not an arbitrary string carrying Java parameter names.

### 3.1. Distinguishing three index levels in `javap`

Suppose you see the abbreviated output:

```text
#7 = InvokeDynamic  #0:#8
#8 = NameAndType     #9:#10
...
BootstrapMethods:
  0: #66 REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants:...
```

Here:

- `#7` is the **CP entry containing `InvokeDynamic`**; the bytecode `invokedynamic #7, 0` points to it.
- `#0` (in `#0:#8`) is **bootstrap record index 0**, matching the line `BootstrapMethods: 0: ...`.
- `#8` is the **CP entry of `NameAndType`**, from which `name_index` and `descriptor_index` lead to two `Utf8` entries.
- `#66` is the CP entry of the **bootstrap method handle**; not record index `0`.
- Static arguments (if any) appear **below** the bootstrap record, typically under the `Method arguments:` heading.

Looking only at the `#7 = InvokeDynamic` line without following `NameAndType` and `BootstrapMethods` misses an important part of the structure.

## 4. What does the invocation name (`invokedName`) mean?

A call site has a **symbolic invocation name** located in `NameAndType`. Java typically represents it as a `String` sent to the bootstrap method.

In common compilation examples:

| Java source mechanism | Common call site name | Commonly used bootstrap method |
| --- | --- | --- |
| String concatenation `"x=" + x` with modern javac | `makeConcatWithConstants` (or `makeConcat` depending on strategy) | `StringConcatFactory.makeConcatWithConstants` or `makeConcat` |
| Lambda `x -> ...` | SAM method name such as `apply`/`run`, depending on functional interface | `LambdaMetafactory.metafactory` |
| Method reference `Type::method` | SAM method name such as `applyAsInt` | `LambdaMetafactory.metafactory` |
| Custom `invokedynamic` bytecode | Name chosen by the bytecode producer and valid per JVMS | Framework/language bootstrap method |

**Three names that should not be equated:**

1. `invokedName`: from `CONSTANT_NameAndType`, e.g., `"apply"`.
2. **Bootstrap method name**: e.g., `"metafactory"`; taken from the target of `bootstrap_method_ref`.
3. **Implementation method name**: e.g., `"lambda$withSuffix$0"` or `"square"`; may be a `MethodHandle` static argument.

The JVM passes `invokedName` to the bootstrap; the bootstrap uses it according to its own contract. **The invocation name does not force the JVM to look up a Java method with that exact name** before the bootstrap runs.

### 4.1. With capturing lambdas, `invokedName` does not indicate the number of captured variables

If `withSuffix(String suffix)` returns a lambda, the bytecode creates an instance of the functional interface using `invokedynamic`. The site name may be `apply`, but the **descriptor of the site** has a `String` parameter carrying the captured `suffix` value. Therefore, you must look at **both the name and the descriptor**, rather than inferring the number of captures from the name `apply`.

Do not rely on `lambda$...` names or the order of generated synthetic methods: those are compiler details, not a protocol for application code.

## 5. JVM method descriptor: syntax and how to read it

A **method descriptor** has the form:

```text
( ParameterDescriptor* ) ReturnDescriptor
```

It records the types of **values placed on the operand stack to enter the call site** and the result type; it does not record parameter names, annotations, generic type arguments, or method names.

Some notations:

| Java type | JVM descriptor |
| --- | --- |
| `void` (return type only) | `V` |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |
| nested `IndyConstantPoolDemo.Transformer` | `LIndyConstantPoolDemo$Transformer;` |

Examples:

```text
(Ljava/lang/String;I)Ljava/lang/String;
       |
       +-- takes String, int; returns String

()Ljava/util/function/IntUnaryOperator;
       |
       +-- no arguments; returns IntUnaryOperator

(Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;
       |
       +-- takes one String; returns Transformer
```

At a call site generated by a lambda factory, **the return type can be a functional interface**, while the method implemented by the lambda has a completely different return type. For a non-capturing method reference, the descriptor of the **functional interface object creation site** is usually `()L...Interface;`, even though the SAM method takes parameters and returns a value.

**Important:** the descriptor in `CONSTANT_InvokeDynamic` is **the type of the call issued by the `invokedynamic` instruction**. It is not the descriptor of the bootstrap method. A bootstrap method typically has metadata parameters `(Lookup, String, MethodType, static arguments...)` and returns `CallSite`, whereas the site to be executed may take `(String,int)` and return `String`.

### 5.1. Java `MethodType` and method descriptor

The Java `MethodType` API directly represents the resolved structure of parameter/return types:

```java
// Java 17+ fragment, assuming java.lang.invoke.MethodType is imported.
MethodType mt = MethodType.methodType(
        String.class, String.class, int.class);
String descriptor = mt.toMethodDescriptorString();
// "(Ljava/lang/String;I)Ljava/lang/String;"
```

This is a **fragment**, not a standalone program. `MethodType.fromMethodDescriptorString(...)` can parse a descriptor with an appropriate class loader. Note that parsing does not automatically create a `CallSite` or emit an `invokedynamic` instruction; it only handles **types**.

### 5.2. Distinguishing method descriptor from generic signature

`(Ljava/util/List;)Ljava/lang/Object;` does not contain `List<String>` or `List<Integer>`. Generic information, if present, is recorded in a separate `Signature` attribute. `CONSTANT_InvokeDynamic` binds behavior according to **JVM erased/runtime types**, not directly according to Java generic syntax.

## 6. From `invokedynamic` to bootstrap: linkage flow

Consider a bytecode instruction `invokedynamic #7, 0`; the conceptual steps are:

1. The JVM reads CP index `#7` from the instruction's operand and finds `CONSTANT_InvokeDynamic_info`.
2. From `name_and_type_index`, the JVM retrieves the **name** and **method descriptor** of the site and resolves the parameter/return types into a `MethodType`.
3. From `bootstrap_method_attr_index`, the JVM finds the record in `BootstrapMethods` and resolves the `CONSTANT_MethodHandle` of the bootstrap method.
4. The JVM resolves the **static arguments** in the record in order to obtain the objects/values used at linkage.
5. The JVM invokes the bootstrap method with arguments corresponding to `Lookup` for the **caller class**, `String invokedName`, `MethodType invokedType`, and the list of static arguments.
6. The result must be a **non-null** `CallSite` whose type matches `invokedType`. The JVM binds this result to the **specific instruction**; when executed, the instruction will use the call site's target.
7. Subsequent executions of **the same linked instruction site** do not repeat the bootstrap to re-resolve the site. With `MutableCallSite` or `VolatileCallSite`, the target can be changed according to the contract of that call site type.

```text
ClassFile constant_pool + BootstrapMethods
             |
             v
  resolve bootstrap handle
  resolve static arguments
  resolve name + descriptor
             |
             v
bootstrap(callerLookup, invokedName, invokedType, ...staticArgs)
             |
             v
    CallSite, type == invokedType ?
        |                   |
       yes                  no
        |                   |
        v                   v
  link this instruction   linkage failure
        |
        v
  invoke CallSite target
```

### 6.1. Does BSM run every time or once?

After an instruction is successfully linked, re-resolving **the same bytecode location** does not invoke the BSM again. However, do not design a bootstrap method relying on the premise that "the body of the BSM is guaranteed to run exactly once":

- Two threads can simultaneously trigger resolution of an unlinked site; per the JVMS, the bootstrap **may be executed concurrently**. The JVM selects one result to use, and the remaining results are discarded.
- Two `invokedynamic` instruction locations can point to the same constant-pool entry yet be **linked separately per instruction location**.
- A bootstrap should have controlled side effects and be safe when multiple threads race to link.
- `ConstantCallSite` has a fixed target; `MutableCallSite` and `VolatileCallSite` serve mechanisms that change the target without modifying site bytecode.

### 6.2. Type conditions and linkage errors

If the bootstrap returns `null`, does not return a `CallSite`, or `CallSite.type()` is not equivalent to the site's method descriptor, linkage fails with `BootstrapMethodError`. Normal exceptions thrown from the bootstrap can be wrapped by the JVM into `BootstrapMethodError` (while `Error` and certain linkage errors have their own propagation rules per the JVMS). You should not assume every linkage error is `BootstrapMethodError`: some method handle resolution, class loader, or bytecode verification errors belong to other linkage categories.

A **bootstrap signature** typically has the form:

```java
static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String invokedName,
        MethodType invokedType,
        /* 0 or more static arguments */ ...) throws Throwable
```

This is an **API schema**, not standalone compilable Java code. The bootstrap handle is invoked with `MethodHandle.invokeWithArguments`-style adaptation; so the actual declaration can be more flexible than a fixed prototype, especially with varargs. What matters is that **the arguments can be adapted** and **the result must satisfy the CallSite contract**.

## 7. Practice 1 — Real Java generating `CONSTANT_InvokeDynamic` entries

Create the file **`IndyConstantPoolDemo.java`**:

```java
public final class IndyConstantPoolDemo {
    @FunctionalInterface
    interface Transformer {
        String apply(String value);
    }

    static String label(String name, int count) {
        return "name=" + name + "; count=" + count;
    }

    static Transformer withSuffix(String suffix) {
        return value -> value + suffix;
    }

    public static void main(String[] args) {
        System.out.println(label("Java", 3));
        Transformer exclaim = withSuffix("!");
        System.out.println(exclaim.apply("ready"));
    }
}
```

Compile/run:

```bash
javac --release 17 IndyConstantPoolDemo.java
java IndyConstantPoolDemo
```

**Exact stdout:**

```text
name=Java; count=3
ready!
```

This program contains situations that generate `invokedynamic` with modern `javac`:

- In `label`: string concatenation with two runtime values `name` and `count`.
- In `withSuffix`: creating a lambda capturing the variable `suffix` to implement the functional interface `Transformer`.
- In the implementation method generated by the compiler for the lambda: `value + suffix` is also string concatenation.

It is not that the call `exclaim.apply("ready")` is automatically an `invokedynamic` opcode; the interface call can be compiled into `invokeinterface`. The `invokedynamic` opcode here is used to **create the lambda object/functional value** and perform **string concatenation**.

### 7.1. Viewing the constant pool and bytecode with `javap`

Run:

```bash
javap -v -p IndyConstantPoolDemo
javap -c -p IndyConstantPoolDemo
```

- `-v` (verbose) prints the constant pool, code, and `BootstrapMethods`.
- `-p` displays private/generated implementation methods, useful when inspecting `lambda$...`.
- `-c` prints bytecode instructions and operand refs.

In one compilation with `javac --release 17`, representative lines are:

```text
#7  = InvokeDynamic #0:#8
       // #0:makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
#8  = NameAndType   #9:#10
       // makeConcatWithConstants:(Ljava/lang/String;I)Ljava/lang/String;
#11 = InvokeDynamic #1:#12
       // #1:apply:(Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;
...
BootstrapMethods:
  0: #66 REF_invokeStatic java/lang/invoke/StringConcatFactory.makeConcatWithConstants:...
  1: #72 REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:...
```

This is an **abbreviated excerpt** from a verified compilation. Lines with `...` are omitted parts; indices `#7`, `#8`, `#11`, `#66`, `#72` **must not be assumed invariant** across JDKs/compilers, or when modifying source code.

Important cue: `#7 = InvokeDynamic #0:#8` links the site in `label` to bootstrap record **0**; `#11 = InvokeDynamic #1:#12` links the lambda creation site in `withSuffix` to record **1**. This compilation also has bootstrap record **2** using `StringConcatFactory` for string concatenation inside the lambda body. The same bootstrap method factory can appear in multiple bootstrap records because of **different static arguments**.

### 7.2. Tracing the string concatenation entry yourself

For `label("Java",3)`:

```text
Source:
  "name=" + name + "; count=" + count

Call-site name:
  makeConcatWithConstants

Call-site descriptor:
  (Ljava/lang/String;I)Ljava/lang/String;

Bootstrap record:
  StringConcatFactory.makeConcatWithConstants
  Static arguments: recipe / constants used for concatenation

Runtime inputs:
  name = "Java", count = 3

Result:
  "name=Java; count=3"
```

A *recipe* can encode literal parts `"name="`, `"; count="` and insertion positions for dynamic values using control characters according to `StringConcatFactory`'s contract. The recipe is a **static argument passed to the bootstrap**, whereas `"Java"` and `3` are **runtime operands** at each call to the site.

Do not confuse `"makeConcatWithConstants"` (the site name) with `StringConcatFactory.makeConcatWithConstants` (the bootstrap method pointed to by `MethodHandle`). They may share the same name, but they belong to **two different pieces of metadata**.

### 7.3. Tracing the capturing lambda entry yourself

For `withSuffix(String suffix)`:

```text
Source:
  return value -> value + suffix;

Call-site name:
  apply

Call-site descriptor:
  (Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;

Bootstrap record:
  LambdaMetafactory.metafactory
  Typical static arguments:
    SAM MethodType
    implementation MethodHandle
    instantiated MethodType

Runtime operand at lambda creation site:
  suffix: String

Result of invokedynamic:
  an object implementing Transformer

When calling the functional interface later:
  transformer.apply(value: String) -> String
```

Note that the site signature `(String)Transformer` is completely different from the SAM signature `(String)String`. The `String` parameter of the site is the **captured variable**; the `Transformer` return type is the **created functional interface object**. The implementation method's signature might take `(suffix, value)` with a compiler-generated name, but that is **not** the type of the site used to create the lambda.

`LambdaMetafactory` receives metadata about the SAM, implementation method handle, and instantiated type to generate an adapter matching the contract. You can read these static arguments under `BootstrapMethods: 1:` in `javap -v`.

## 8. Practice 2 — Non-capturing method reference

Create the file **`NonCapturingIndyDemo.java`**:

```java
import java.util.function.IntUnaryOperator;

public final class NonCapturingIndyDemo {
    static int square(int value) {
        return value * value;
    }

    static IntUnaryOperator operation() {
        return NonCapturingIndyDemo::square;
    }

    public static void main(String[] args) {
        IntUnaryOperator op = operation();
        System.out.println("square: " + op.applyAsInt(6));
    }
}
```

```bash
javac --release 17 NonCapturingIndyDemo.java
java NonCapturingIndyDemo
javap -v -p NonCapturingIndyDemo
```

**Stdout of the Java program (excluding `javap` command output):**

```text
square: 36
```

In the `operation()` method, `javap -v` has an `InvokeDynamic` entry with the site form:

```text
applyAsInt:()Ljava/util/function/IntUnaryOperator;
```

There are no captured parameters, so the part inside the descriptor's parentheses is empty. Meanwhile, the **SAM method** `IntUnaryOperator.applyAsInt(int)` takes an `int` and returns an `int`; the implementation method `square(int)` also takes/returns `int`.

Do not interpret `()IntUnaryOperator` as "`square` takes no parameters". This is the **signature at the functional object creation site**, not the signature of the operation when using that object. Nor should you conclude that all method references have a `()Interface` descriptor: method references **with receiver capture** or other contexts can have site parameters.

In this example, `System.out.println("square: " + ...)` can also cause the compiler to emit an additional `StringConcatFactory` site. When counting `InvokeDynamic` in a class file, distinguish between **lambda/method-reference sites** and **string-concat sites**.

## 9. Distinguishing bootstrap static arguments from runtime arguments

This is where many people reading `javap` get confused.

### 9.1. Static arguments are available from the class file

Static arguments are encoded as constant-pool references from `BootstrapMethods.bootstrap_arguments[]`. For example:

- `StringConcatFactory.makeConcatWithConstants` receives a recipe and optionally additional constants such as string/class tokens;
- `LambdaMetafactory.metafactory` receives the SAM `MethodType`, implementation `MethodHandle`, and instantiated `MethodType`.

This data helps the bootstrap decide **how to create the target**. They are not values passed by the caller of `label("Java",3)` or `withSuffix("!")` at runtime.

### 9.2. Runtime arguments are placed on the operand stack

After linkage, an execution of `invokedynamic` takes **n arguments according to the descriptor** from the operand stack. For example:

```text
call site: (String,int)String
runtime stack arguments: "Java", 3
bootstrap static recipe: "name=...; count=..."
                         ^ not an argument passed by the caller at runtime
```

For a capturing lambda:

```text
call site: (String)Transformer
runtime argument: suffix = "!"
bootstrap static args: SAM type, impl handle, instantiated type
```

Both groups can contain objects of type `String` or `MethodType`, but where they are used differs. To debug "which values change on each call", start from the descriptor and the instructions preparing the operand stack; to debug "how the call site is constructed", look at `BootstrapMethods`.

## 10. Bootstrap method prototype and `CallSite` contract

A typical bootstrap method has three initial metadata arguments:

| Parameter | Value provided by JVM | Purpose |
| --- | --- | --- |
| `MethodHandles.Lookup caller` | Lookup with the context of the class containing `invokedynamic` | Resolve components with the caller's appropriate access rights |
| `String invokedName` | Name from `CONSTANT_NameAndType` | Symbol for the bootstrap to interpret |
| `MethodType invokedType` | Type resolved from the method descriptor | Type contract the target must satisfy |
| `... staticArgs` | Static arguments from `BootstrapMethods` | Hints, recipe, implementation handles, constants |

The bootstrap returns a `CallSite`, such as:

- `ConstantCallSite`: target is fixed after configuration; suitable for string concatenation/lambdas where the target must not change.
- `MutableCallSite`: target can change, with its own synchronization/visibility rules.
- `VolatileCallSite`: changes target with volatile-equivalent semantics.

From the outside, `CallSite.type()` is the target type that the JVM expects at **that exact call site**. Any candidate target must have a type compatible with the site; if the implementation logic takes a different type, the bootstrap can use `MethodHandle.asType` adapters or combinators according to permitted conversions.

### 10.1. Example of a bootstrap method *invoked manually* to understand the contract

Create the file **`BootstrapContractDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class BootstrapContractDemo {
    private static String prepend(String prefix, String value) {
        return prefix + value;
    }

    public static CallSite bootstrap(MethodHandles.Lookup caller,
                                     String invokedName,
                                     MethodType invokedType,
                                     String prefix) throws Throwable {
        if (!invokedName.equals("decorate")) {
            throw new IllegalArgumentException("Unexpected call-site name");
        }
        MethodHandle original = caller.findStatic(
                BootstrapContractDemo.class, "prepend",
                MethodType.methodType(String.class, String.class, String.class));
        MethodHandle target = MethodHandles.insertArguments(original, 0, prefix);
        if (!target.type().equals(invokedType)) {
            throw new IllegalArgumentException("Incompatible target type");
        }
        return new ConstantCallSite(target);
    }

    public static void main(String[] args) throws Throwable {
        MethodType descriptor = MethodType.methodType(
                String.class, String.class);
        CallSite site = bootstrap(MethodHandles.lookup(),
                "decorate", descriptor, "ID:");
        System.out.println("descriptor: " + descriptor.toMethodDescriptorString());
        System.out.println("target type: " + site.getTarget().type());
        System.out.println("call: " + (String) site.dynamicInvoker().invokeExact("A7"));
    }
}
```

```bash
javac --release 17 BootstrapContractDemo.java
java BootstrapContractDemo
```

**Exact stdout:**

```text
descriptor: (Ljava/lang/String;)Ljava/lang/String;
target type: (String)String
call: ID:A7
```

**Point to understand correctly:** The program above **calls `bootstrap(...)` directly in Java code** to verify the parameter set `(Lookup, name, type, static argument)` and the `CallSite` result. It does **not** cause the compiler to generate an `invokedynamic` pointing to the `BootstrapContractDemo.bootstrap` method. The string concatenation code inside `prepend` itself can still be emitted by the compiler as an `invokedynamic` using `StringConcatFactory`, but that is **a different site**.

In a custom class file with an actual `invokedynamic` using this bootstrap, `BootstrapMethods.bootstrap_method_ref` needs to point to `BootstrapContractDemo.bootstrap` with static argument `"ID:"`; the site can have the name `"decorate"` and descriptor `(Ljava/lang/String;)Ljava/lang/String;`. The JVM will perform the linkage process in place of the manual call in `main`.

### 10.2. Reading the manual bootstrap example

- `invokedName == "decorate"` illustrates that the bootstrap **can interpret** the site name; the JVM does not automatically invoke a method named `decorate`.
- `invokedType` is `(String)String`; `findStatic` looks up the method `prepend(String,String)String`.
- `insertArguments(original, 0, "ID:")` binds the prefix, making the new target have type `(String)String`.
- `new ConstantCallSite(target)` provides a callable matching the site's type.
- `site.dynamicInvoker().invokeExact("A7")` invokes the target and returns `"ID:A7"`.
- In the example, the author explicitly throws `IllegalArgumentException` when metadata is invalid; if a real bootstrap is invoked by the JVM and fails to meet the linkage contract, the JVM enforces the linkage error rules stated in section 6.2.

This example is sufficient to verify **the types and data components of a bootstrap**, but to see real `invokedynamic` bytecode, rely on examples 7–8 or dedicated, controlled class-file/bytecode generation tools.

## 11. Comparing three frequently confused descriptors

A class with a lambda can contain **three or more** method descriptors. Each descriptor serves a different abstraction layer:

| Descriptor | Where is it located? | Meaning |
| --- | --- | --- |
| `(Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;` | `NameAndType` of `CONSTANT_InvokeDynamic` at `withSuffix` | One `String suffix` in; returns a `Transformer` |
| `(Ljava/lang/String;)Ljava/lang/String;` | `CONSTANT_MethodType` static args of `LambdaMetafactory` | SAM/instantiated signature `apply(String):String` |
| `(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;` | MethodHandle impl target / generated method | Implementation method may take `suffix` and `value` |
| `(Lookup,String,MethodType,MethodType,MethodHandle,MethodType)CallSite` | Descriptor of the `LambdaMetafactory.metafactory` bootstrap method (abbreviated types) | Linkage API, not the runtime signature of the lambda |

Do not use the bootstrap method descriptor to determine the actual number of arguments of `Transformer.apply(...)`. Do not use the descriptor of the generated implementation method to replace the `invokedynamic` site descriptor. Each layer has its own inputs/outputs.

### 11.1. String concatenation also has two signatures

`StringConcatFactory.makeConcatWithConstants` typically takes metadata and a recipe; it is the **bootstrap**. The call-site descriptor of `label` is **`(String,int)String`**. If you put the bootstrap descriptor into the site's `NameAndType`, the JVM would expect the caller to pass `Lookup`, `String`, `MethodType`, recipe... on every run, which is completely wrong.

### 11.2. A `MethodType` static argument is not the runtime "class" of a lambda

`CONSTANT_MethodType` is used as a static argument to pass a **signature**, not the address of the lambda implementation class. The JVM/runtime may generate a hidden class or another implementation mechanism depending on the compiler/runtime; do not build tools that depend on lambda implementation class names or assume a stable `.class` file corresponds to each lambda.

## 12. Distinguishing `CONSTANT_Dynamic` (condy) and `CONSTANT_InvokeDynamic`

The two tags have a similar information shape: bootstrap index + name-and-type index. However, their nature differs:

| Property | `CONSTANT_InvokeDynamic` (tag 18) | `CONSTANT_Dynamic` (tag 17) |
| --- | --- | --- |
| Used for | **Dynamic call site** | **Dynamically computed constant** |
| Descriptor in `NameAndType` | **Method descriptor**: `(args)Result` | **Field descriptor**: a type `Result` |
| Bytecode typically referencing | `invokedynamic` | `ldc` / `ldc_w` / `ldc2_w` when valid |
| Third metadata for bootstrap | `MethodType` | `Class` of the constant to create |
| Bootstrap result | `CallSite` with matching type | A value with matching type |
| At point of use | Invoke target method handle | Load resolved constant |

Both can reference the same `BootstrapMethods` attribute of the class file, but they are **not the same runtime mechanism**. Some `bootstrap_arguments[]` can even lead to a `CONSTANT_Dynamic` constant being resolved before the call site's bootstrap receives it.

Do not call every line containing the word `Dynamic` in `javap` an `invokedynamic` site. Read the exact tag and descriptor.

## 13. Debugging scenario with `javap -v`

When you need to explain an unusual dynamic call in a `.class` file:

1. **Find the opcode** `invokedynamic #n, 0` in the method's code section; note the class and method containing the instruction.
2. **Find constant pool entry `#n`** to identify the `InvokeDynamic` tag, bootstrap index, and `NameAndType` index.
3. **Follow `NameAndType`** to record the invocation name and descriptor; read each parameter from left to right, and read the return type after `)`.
4. **Follow `BootstrapMethods[index]`** to find the `REF_...` method-handle of the bootstrap and the count/list of static arguments. Do not misread the bootstrap index as a CP index.
5. **Distinguish static arguments and runtime operands**: static from `BootstrapMethods`; runtime from the bytecode preparing the stack before `invokedynamic`.
6. **For lambdas**, inspect `LambdaMetafactory` along with the SAM MethodType, implementation MethodHandle, and instantiated MethodType; do not use the site descriptor to describe the SAM.
7. **For string concat**, inspect `StringConcatFactory` and the recipe (if present); do not assume literal strings and runtime arguments are in the same table.
8. **When linkage errors are reported**, read the exception/cause, class loader, module boundaries, method type, and the possibility of concurrent BSM invocation.
9. **When comparing two builds**, do not mechanically diff by CP index. Match opcode, name, descriptor, bootstrap target, static args, and call-site semantics.
10. **When verification is needed**, run the class with the same JDK/classpath/module path you are analyzing, rather than relying solely on assumptions about the compiler.

### 13.1. Example of reading a lambda call site along the reference chain

```text
Code in withSuffix:
   invokedynamic #11, 0

constant_pool[#11]:
   InvokeDynamic bootstrap=1, name_and_type=#12

constant_pool[#12]:
   NameAndType "apply":
       (Ljava/lang/String;)LIndyConstantPoolDemo$Transformer;

BootstrapMethods[1]:
   bootstrap = LambdaMetafactory.metafactory
   static args = [SAM MethodType, impl MethodHandle, instantiated MethodType]

Runtime call-site arguments:
   suffix:String

Runtime call-site result:
   Transformer
```

**On the diagram:** The numbers `#11`, `#12`, and `1` are examples from a verified build, not ABI-stable. The purpose is how to **follow the linkage chain**.

### 13.2. Why is Reflection not enough to find `invokedynamic`?

`Class.getDeclaredMethods()` reports declared/compiler-generated methods on the runtime class, but **does not list individual `invokedynamic` instructions** inside a method's `Code` attribute. To inspect opcodes, the constant-pool graph, and the `BootstrapMethods` attribute, use `javap -v -p` or a bytecode/class-file analysis tool. A bootstrap method can be a normal Java method and appear in Reflection, but that does not create a Reflection API automatically mapping to every site that uses it.

## 14. Common misconceptions

1. **Thinking `CONSTANT_InvokeDynamic` holds a `class_index` to the target method** — wrong; it holds a bootstrap index and a `NameAndType` index.
2. **Confusing `#0` in `InvokeDynamic #0:#8` with constant pool entry `#0`** — wrong; `#0` is the bootstrap array index, CP indices start at 1.
3. **Thinking the site name `"apply"` is a method name the JVM looks up automatically** — wrong; it is a symbolic name passed to the bootstrap.
4. **Thinking the site name, bootstrap name, and implementation name are always the same** — wrong; a lambda can use `apply`, `metafactory`, and `lambda$withSuffix$0`.
5. **Thinking the site descriptor is the SAM descriptor** — wrong when a lambda captures; `(String)Transformer` differs from `(String)String`.
6. **Thinking `BootstrapMethods` is an entry in the constant pool** — wrong; it is a class-level attribute, though it contains indices to CP MethodHandles and static arguments.
7. **Thinking `BootstrapMethods.bootstrap_arguments[]` holds the runtime values `"Java"` and `3` of each call** — wrong; these are static arguments prepared at linkage.
8. **Thinking every execution of `invokedynamic` calls the BSM again** — wrong after successful linkage of the same bytecode location; however, the BSM can still run concurrently during initial linkage.
9. **Thinking two sites using the same CP entry definitely share one linkage** — incorrect; the JVMS binds the result per `invokedynamic` instruction location.
10. **Thinking `CallSite` can return a target with any method type** — wrong; the site's type must be equivalent to the declared descriptor.
11. **Thinking that because source has a lambda, every method call to the lambda is an `invokedynamic` opcode** — incorrect; `invokedynamic` is usually used to create the functional object, and then the SAM call can be `invokeinterface`.
12. **Thinking `CONSTANT_Dynamic` also always returns `CallSite`** — wrong; condy creates a constant, and the bootstrap receives the `Class` of the constant.
13. **Looking at `#n` indices from another machine and hard-coding them** — compiler, JDK, optimizations, and source edits can change indices; re-read `javap`.
14. **Treating a manually invoked BSM prototype as having created a distinct `invokedynamic` bytecode** — no; you need the actual instruction + CP entry + `BootstrapMethods` in the class file.
15. **Ignoring class loaders and Lookup permissions** — resolving static argument classes, impl method handles, and bootstrap targets can fail even if the name/descriptor look right.
16. **Assuming `MutableCallSite` causes the bootstrap to re-run on every target change** — wrong; target mutation is different from re-linking.
17. **Assuming every `javac` build emits string concatenation with the same factory/recipe** — not guaranteed across compilers, compiler flags, or toolchain versions.
18. **Mistaking `javap` output for Java source** — `#7 = InvokeDynamic` and `BootstrapMethods` are bytecode/class-file descriptions, not Java declarations that can be copied into a method body.

## 15. Self-check

**Question 1.** In `CONSTANT_InvokeDynamic_info`, what are the two `u2` fields after `tag`? What do they respectively point to?

**Question 2.** In `#7 = InvokeDynamic #0:#8`, which index spaces do the three numbers 7, 0, and 8 belong to?

**Question 3.** Is `BootstrapMethods` a CP entry or a class-level attribute? What does one of its records contain?

**Question 4.** Why do the site name `apply` and descriptor `(String)Transformer` not prove that the lambda implementation has the signature `apply(String):Transformer`?

**Question 5.** For `withSuffix("!")`, is the `"!"` argument a runtime operand or a static bootstrap argument?

**Question 6.** In `StringConcatFactory.makeConcatWithConstants`, where is the recipe located, and where are the `name/count` values located?

**Question 7.** What three metadata parameters does a typical bootstrap receive before static arguments? What result type must it return for `invokedynamic`?

**Question 8.** A bootstrap returns a `CallSite` with target type `(int)String`, while the site descriptor is `(String)String`. Is the result valid?

**Question 9.** If two `invokedynamic` instructions point to the same CP entry, is there necessarily only one shared resolution for both instruction locations?

**Question 10.** How does `CONSTANT_Dynamic` differ from `CONSTANT_InvokeDynamic` in descriptor and bootstrap result type?

**Question 11.** Can `Class.getDeclaredMethods()` be used to get a list of all `invokedynamic` instructions in a method body? What tool should be used?

**Question 12.** Can a bootstrap be executed concurrently by multiple threads? Which result is used by the JVM?

### Suggested answers

1. `bootstrap_method_attr_index` points to a `BootstrapMethods` record; `name_and_type_index` points to a CP `NameAndType`.
2. `7` is the CP index of `InvokeDynamic`; `0` is the bootstrap record index; `8` is the CP index of `NameAndType`.
3. Class-level attribute; a record has `bootstrap_method_ref` and a list of `bootstrap_arguments`.
4. Because the site creates a **functional interface object** from the captured `String`; the SAM and impl have separate descriptors in static args.
5. A runtime operand passed when the site creates the functional object; not in the static args table.
6. The recipe is a static bootstrap argument; `name/count` are runtime operands of the `(String,int)String` site.
7. `Lookup caller`, `String name`, `MethodType type`; the result is a `CallSite` whose type matches the descriptor.
8. No; the types do not match, so the JVM rejects linkage (usually `BootstrapMethodError`).
9. No; according to the JVMS, linkage is applied per `invokedynamic` instruction location.
10. `Dynamic` holds a field descriptor, and its bootstrap receives the `Class` of the constant and produces a value; `InvokeDynamic` holds a method descriptor and produces a `CallSite`.
11. No; use `javap -v -p`, `javap -c -p`, or a bytecode analyzer.
12. Yes, during initial resolution; the JVM chooses one result and discards the losing results.

## 16. Standard reference documentation

- [JVMS Java SE 21 — `4.4 The Constant Pool` and `4.4.10 CONSTANT_Dynamic / CONSTANT_InvokeDynamic`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4.10): tag 17/18 structure, bootstrap index, and NameAndType index.
- [JVMS Java SE 21 — `4.7.23 BootstrapMethods`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.23): class-level attribute, bootstrap method handle, and static arguments.
- [JVMS Java SE 21 — `4.3.3 Method Descriptors`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3.3): `(parameters)return` syntax.
- [JVMS Java SE 21 — `5.4.3.6 Dynamic Constant and Call Site Resolution`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.6): preparing bootstrap args, resolution, checking `CallSite`, concurrent linkage.
- [JVMS Java SE 21 — `6.5 invokedynamic`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokedynamic): instruction operand and binding to the site.
- [Java SE 21 API — `java.lang.invoke` package](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/package-summary.html): bootstrap contracts, method handles, call sites, and dynamic constants.
- [Java SE 21 API — `CallSite`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/CallSite.html), [`MethodType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html), [`StringConcatFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/StringConcatFactory.html), [`LambdaMetafactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): target types and actual bootstrap factories.

**Remember:** Read `invokedynamic` in the order **opcode → `CONSTANT_InvokeDynamic` → `NameAndType` (name + descriptor) and `BootstrapMethods` (bootstrap handle + static arguments) → `CallSite`**. Properly distinguishing the three layers—**site name**, **call-site descriptor**, and **bootstrap method/arguments**—is the key to understanding why lambdas, method references, and string concatenation share the same bytecode mechanism yet have very different runtime behaviors.