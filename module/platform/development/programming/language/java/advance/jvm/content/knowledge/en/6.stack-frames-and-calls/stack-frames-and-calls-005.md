# invokedynamic, BootstrapMethods, and Dynamic Call Site Linking in the JVM

## Objectives

Common method invocation instructions in Java bytecode such as `invokestatic`, `invokevirtual`, `invokeinterface`, and `invokespecial` have linking rules based on class/method references and invocation kinds. **`invokedynamic`** adds an important mechanism: the compiler provides a **call site descriptor** along with a **bootstrap method** so that the JVM determines *how to link the call* when the call site is used. This is the foundation of many modern JVM features, especially lambdas and the string concatenation approach used by modern `javac`.

After this lesson, you will be able to:
- Explain `invokedynamic` at the instruction, operand stack, and method descriptor levels.
- Trace `CONSTANT_InvokeDynamic` → `BootstrapMethods` → `MethodHandle` → `CallSite`.
- Distinguish **static bootstrap arguments** in the class file from **dynamic arguments** pushed onto the operand stack when the call executes.
- Describe the lifecycle of a call site: unlinked → bootstrap/link → invocation of the target, including bootstrap errors and race cases.
- Distinguish `ConstantCallSite`, `MutableCallSite`, and `VolatileCallSite`; recognize visibility limitations when changing the target.
- Use Java 17+ to compile lambdas/string concatenation, inspect `javap -v -p`, and understand why constant pool indices are not fixed.
- Distinguish `CONSTANT_InvokeDynamic` from `CONSTANT_Dynamic` (condy) and avoid misconceptions such as “`invokedynamic` calls the bootstrap every time”.

## 1. Why does the JVM need a dynamic invocation mechanism?

A familiar example:

~~~java
object.toString();
~~~

For a normal instance method call, the bytecode can carry `invokevirtual` with a reference to the method identified by the owner class, name, and method descriptor in the constant pool. The JVM has its own rules to resolve the method and select the implementation at execution time (for example, virtual dispatch).

The mechanism above is not convenient for all compiler/runtime requirements: a call site may need to be **configured with custom rules** that the compiler only describes via metadata. That is where `invokedynamic` is useful. Instead of the bytecode fixing an owner method according to the normal invocation model, it points to a **call site specifier**; the JVM uses a **bootstrap method** specified by the class file to obtain a `CallSite` and its corresponding method handle.

Diagram:

~~~text
Caller's bytecode
    |
    | invokedynamic #N
    v
CONSTANT_InvokeDynamic #N
    |
    +-- name_and_type_index --> call site name + METHOD descriptor
    |
    +-- bootstrap_method_attr_index (0-based)
            |
            v
        BootstrapMethods attribute
            |
            +-- bootstrap_method_ref --> CONSTANT_MethodHandle
            +-- bootstrap_arguments[] --> constant pool entries
            |
            v
        Bootstrap Method invoked by the JVM to link
            |
            v
        CallSite whose target is a MethodHandle
            |
            v
        target is invoked with dynamic args on the operand stack
~~~

This diagram describes logical relationships, **not a fixed memory layout**. The `#N` entries are specific class file indices; the ordering, index numbers, and some names are decided by the compiler. `invokedynamic` does not mean that on every execution it will slowly look up the method again by resolving its name.

### At which stage is it “Dynamic”?

There are two separate stages:
1. **Call site linking (*linkage*)**: the bootstrap is triggered according to the resolution rules for an unlinked `invokedynamic` instruction, preparing a valid `CallSite`.
2. **Call execution (*invocation*)**: each time the instruction is executed, runtime arguments are taken from the operand stack to invoke the current target of the call site.

The linking mechanism can choose a target once or provide a `CallSite` with a mutable target, depending on the call site kind and the program. This is different from running the bootstrap again before every invocation.

## 2. The `invokedynamic` instruction and the operand stack

`invokedynamic` has decimal opcode **186**, hexadecimal **`0xBA`**. Format in the class file:

~~~text
invokedynamic indexbyte1 indexbyte2 0 0

index = (indexbyte1 << 8) | indexbyte2
~~~

The two index bytes form an unsigned 16-bit operand pointing to a **`CONSTANT_InvokeDynamic`** in the current class's run-time constant pool; **the following two bytes must be 0** according to the JVM format. When viewing with `javap -c`, you often see:

~~~text
invokedynamic #N,  0  // InvokeDynamic #k:applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
~~~

This is only a **display illustration**: the name, descriptor, and indices depend on the compiled class. `#N` after the opcode and `#k` in the comment have different meanings: `#N` is the constant pool index, while `#k` usually represents the bootstrap method table index formatted by `javap`.

The **method descriptor** in `NameAndType` specifies the parameter types and return type of the *call at that exact site*. For example:

~~~text
(II)I                         // two ints -> int
(Ljava/lang/String;)V         // String -> void
(I)Ljava/lang/String;        // int -> String
()Ljava/lang/Runnable;       // no parameters -> Runnable
(I)Ljava/util/function/IntUnaryOperator; // int -> IntUnaryOperator
~~~

With descriptor `(II)I`, before the instruction the operand stack has two `int`s:

~~~text
Stack before:  ..., int1, int2
invokedynamic: pops both arguments, invokes the matching target
Stack after:   ..., intResult
~~~

If the descriptor returns `V` (void), no return value is pushed. With `long`/`double`, the JVM uses category-2 values on the stack. The parameters already pushed onto the stack are the **dynamic arguments**; they are **different** from the bootstrap static arguments in the attribute.

Unlike instance calls such as `invokevirtual`, the `invokedynamic` instruction does not have an implicit `objectref` operand. If you want to pass a receiver to the call target, that receiver can be an **explicit parameter in the descriptor**, i.e., a normal dynamic argument.

## 3. Class file: `CONSTANT_InvokeDynamic`

According to the JVMS, the entry has tag **18**:

~~~text
CONSTANT_InvokeDynamic_info {
    u1 tag;                            // 18
    u2 bootstrap_method_attr_index;
    u2 name_and_type_index;
}
~~~

Where:
- **`bootstrap_method_attr_index`** points to **an element in the `bootstrap_methods[]` table** of the class file's `BootstrapMethods` attribute. This index is **0-based**, not a constant pool index.
- **`name_and_type_index`** points to `CONSTANT_NameAndType`; from here, the **unqualified name** and **method descriptor** of the call site can be read. This is a *method descriptor*, not a field descriptor.
- `CONSTANT_InvokeDynamic` **does not have a `class_index`** like `CONSTANT_Methodref`. Choosing the target method handle is the result of bootstrapping, not a fixed resolution directly by the caller's owner/method.
- Class files using this entry type must conform to version requirements, constant pool specifications, and bootstrap attributes. `invokedynamic`/`CONSTANT_InvokeDynamic` has existed since Java 7, corresponding to class file major version 51 or higher.

Do not assume the call site name is a Java method guaranteed to exist. The name is passed to the bootstrap as metadata for the bootstrap to interpret; **there does not necessarily have to be a method with that same name declared in some owner class**.

### How to recognize the `NameAndType` form

Suppose `javap -v` outputs these illustrative entries:

~~~text
#20 = InvokeDynamic      #0:#21    // #0:applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
#21 = NameAndType        #22:#23   // applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
#22 = Utf8               applyAsInt
#23 = Utf8               (I)Ljava/util/function/IntUnaryOperator;
~~~

This is a **mock snippet for explanation**, not output that can be predicted identically across every compiler version. Read along the chain:
1. Entry `#20` has the InvokeDynamic tag.
2. The number `#0` in the bootstrap portion refers to element **0** of the `BootstrapMethods` attribute.
3. `#21` is `NameAndType` in the constant pool; from there, the name and descriptor are read.
4. To know the actual bootstrap method, look at the **`BootstrapMethods` attribute**, do not treat `#0` as `constant_pool[0]`.

## 4. What does the `BootstrapMethods` attribute contain?

The `BootstrapMethods` attribute is at the **class level** in `ClassFile`. If the constant pool contains one or more `CONSTANT_InvokeDynamic` or `CONSTANT_Dynamic` entries, the class file must have **exactly one** `BootstrapMethods` attribute according to the format rules.

Abbreviated layout:

~~~text
BootstrapMethods_attribute {
    u2 attribute_name_index; // Utf8 "BootstrapMethods"
    u4 attribute_length;
    u2 num_bootstrap_methods;
    {
        u2 bootstrap_method_ref;
        u2 num_bootstrap_arguments;
        u2 bootstrap_arguments[num_bootstrap_arguments];
    } bootstrap_methods[num_bootstrap_methods];
}
~~~

Each element of the bootstrap table consists of:
- **`bootstrap_method_ref`**: a constant pool index to a **`CONSTANT_MethodHandle`**, describing the bootstrap method.
- **`bootstrap_arguments[]`**: an array of constant pool indices for the allowed **static bootstrap arguments**. Each argument is resolved/interpreted according to its constant kind.
- The table is indexed **from 0**; whereas the constant pool in the class file is indexed **from 1** (index 0 is unused). This is a very common class file reading mistake.

A `javap -v` output may display:

~~~text
BootstrapMethods:
  0: #40 REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:...
    Method arguments:
      #47 (I)I
      #48 REF_invokeStatic Example.lambda$main$0:(II)I
      #47 (I)I
~~~

The indices/names above are only to **illustrate the bootstrap relationship**; synthetic method names and types may differ. The important point is that the **method handle for the bootstrap** is in the same table as **additional constants** such as `MethodType` or `MethodHandle`. These arguments help the bootstrap produce a target matching the call site's descriptor.

### Two groups of arguments not to be confused

| Group | Source | When present? | Examples |
| --- | --- | --- | --- |
| **Bootstrap static arguments** | `bootstrap_arguments[]` pointing into the constant pool | When the bootstrap/link point is processed | MethodType of the SAM, MethodHandle of the lambda body, string concatenation recipe |
| **Bootstrap JVM-supplied arguments** | Supplied by the JVM when calling the bootstrap | During call site resolution | `MethodHandles.Lookup`, call site name, `MethodType` of the call |
| **Dynamic invocation arguments** | Operand stack at `invokedynamic` | **Every time** the instruction is executed | Values captured from scope, numbers for string concatenation, receiver according to descriptor |

Bootstrap arguments **do not automatically appear on the caller program's operand stack**. Conversely, dynamic arguments **are not metadata in BootstrapMethods**: they vary between executions of the instruction.

## 5. Linking (*linkage*) lifecycle of a call site

General flow when the JVM first executes an unlinked `invokedynamic` instruction:

1. **Read the symbolic reference** `CONSTANT_InvokeDynamic` of the instruction, including the name/descriptor and bootstrap table index.
2. **Resolve the necessary constants** such as the bootstrap's `MethodHandle` and static arguments, and determine the `MethodType` of the call site.
3. **Prepare arguments for the bootstrap**. In the typical bootstrap case, the first three arguments consist of `MethodHandles.Lookup` with the caller's privileges, the call site name of type `String`, and the `MethodType` of the call site; followed by the defined static arguments. The actual signature must be compatible with the bootstrap invocation rules.
4. **Invoke the bootstrap method** specified by the method handle. The bootstrap decides how to create the target and returns an appropriate **`CallSite`** object.
5. **Validate the result**: non-null, is a `CallSite`, and **the CallSite's type is compatible with the specified method descriptor**. If not satisfied, resolution fails.
6. **Bind the result to that instruction call site**. Subsequent executions of **that same instruction** use the linked result to invoke the corresponding target (which may change if it is a CallSite type that allows it).

~~~text
First time the indy instruction runs
   |
   v
Check if call site is linked?
   |
   +-- NO  --> resolve bootstrap metadata
   |                |
   |                v
   |          invoke bootstrap method
   |                |
   |                v
   |          validate CallSite + type
   |                |
   |                v
   |          bind result to instruction
   |
   +-- YES ------+
                 |
                 v
       read CallSite target per site kind semantics
                 |
                 v
       pass dynamic args -> invoke MethodHandle
                 |
                 v
       return result to operand stack if non-void
~~~

**Do not claim that the bootstrap always runs physically exactly once.** The JVMS allows different threads to simultaneously attempt to resolve an unlinked site; the bootstrap may be triggered by more than one thread in a race, but **only one result is chosen as the official linkage**. Therefore, a bootstrap should avoid non-idempotent side effects or be able to handle concurrent invocations. Once the site is successfully linked, subsequent executions of *that instruction* do not re-link it as a new site.

### Which call site is cached?

It is necessary to distinguish **a constant pool entry** and **an occurrence of an `invokedynamic` instruction**. The resolution rules of indy attach linkage to **the instruction occurrence itself**; two different `invokedynamic` instructions can reference the same symbolic entry and still have separate resolution results. Thus, one cannot infer “same `#N` means two bytecode locations must use the same `CallSite`”.

Similarly, calling a Java method containing an `invokedynamic` instruction multiple times **does not create a new call site per method call**. The call site belongs to the instruction location in the current class, not to each active stack frame.

### Frames and method invocation

Linking a call site is a JVM runtime operation, but when the target is invoked, the **method handle invocation** must still obey parameter/return types and invocation rules. There is no persistent “BootstrapMethods frame” for every call: the bootstrap is called during the link phase, whereas the target is called during instruction execution. The JVM/JIT may optimize the actual implementation, but the observable semantics must match the linkage and the current target of the `CallSite`.

## 6. `CallSite` and `MethodHandle`

**`MethodHandle`** is a runtime value with a `MethodType`, representing the ability to invoke a target according to a defined mechanism. **`CallSite`** is an object holding a **target MethodHandle** of a dynamic call site.

Three common CallSite groups:

| Kind | Target after creation | Things to note |
| --- | --- | --- |
| **`ConstantCallSite`** | Immutable after valid initialization | Suitable when the call site's target is fixed; easy to optimize. |
| **`MutableCallSite`** | Can be changed via `setTarget` | Observing the new target in other threads has its own visibility rules; `MutableCallSite.syncAll` is the tool for synchronizing changes. |
| **`VolatileCallSite`** | Can be changed; reading/writing the target has volatile-like semantics | Useful when stronger visibility is needed without manually managing synchronization of a mutable site. |

**`MethodHandle` is not automatically synonymous with `Methodref` in the constant pool.** `CONSTANT_MethodHandle` is a *binary description* to create/resolve a method handle; `java.lang.invoke.MethodHandle` is a *runtime object*. The bootstrap can combine/adapt handles to build the target, and the `CallSite` holds the target that will be invoked.

**The target's type matters:** the bootstrap must return a `CallSite` whose `type()` matches the call site descriptor. If it does not match, you cannot take a target with arbitrary parameters/return type and leave it for the JVM to “guess”; the bootstrap must use combinators such as `asType`, `bindTo`, `insertArguments`, or construct a handle of the right type when needed.

### Changing the target and visibility across threads

With `MutableCallSite`, `setTarget` changes the target, but multiple threads executing concurrently may continue to see the old target if proper visibility is not established. `syncAll` helps synchronize changes according to the `MutableCallSite` contract, but it is not an application-wide transaction mechanism. With `VolatileCallSite`, the target has semantics similar to volatile operations for reading/writing the target; costs and synchronization needs vary by case.

**CallSite does not mean a Java method body is “overwritten” or “edited” at runtime.** It selects the *target method handle* for the call site, which can switch from behavior A to B, while the class/method bytecode is not necessarily modified.

## 7. Runnable Java 17+ example: lambdas and string concatenation

Programmers do not have Java source syntax directly equivalent to the `invokedynamic` instruction. Instead, the **compiler** emits the instruction when needed. Two common examples from modern `javac` are **lambda expressions** and **string concatenation**.

Create the file **`InvokeDynamicDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class InvokeDynamicDemo {
    private static String message(int value) {
        return "value=" + value;
    }

    public static void main(String[] args) {
        int offset = 3;
        IntUnaryOperator addOffset = n -> n + offset;

        System.out.println("lambda=" + addOffset.applyAsInt(7));
        System.out.println("concat=" + message(42));
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --release 17 InvokeDynamicDemo.java
java InvokeDynamicDemo
~~~

**Exact stdout:**

~~~text
lambda=10
concat=value=42
~~~

Analysis:
- The variable `offset = 3` is captured by the lambda. The lambda `n -> n + offset`, after being converted into an implementation of `IntUnaryOperator`, adds `n` and 3; `applyAsInt(7)` returns 10.
- The string concatenation expression `"value=" + value` returns `"value=42"`.
- `System.out.println` is a normal Java API call; it is not the word `println` itself that is an indy opcode.

Inspect the bytecode:

~~~bash
javap -c -p InvokeDynamicDemo
javap -v -p InvokeDynamicDemo
~~~

In **typical `javac --release 17`**:
- `main` has an `invokedynamic` related to creating a functional interface instance for the lambda; the bootstrap usually references `java/lang/invoke/LambdaMetafactory.metafactory`.
- `message` may have an `invokedynamic` for string concatenation; the bootstrap usually references `java/lang/invoke/StringConcatFactory.makeConcatWithConstants`.
- You may see a synthetic method like `lambda$main$0` generated by the compiler to hold the lambda body. **Do not rely on the exact synthetic method name/numbering**, order, or index `#N`.
- Other string concatenation expressions in `main` may also produce indy call sites. Constant pool indices/recipes vary depending on how the compiler generates code.

Example of a **shortened disassembly form, for recognition only**:

~~~text
invokedynamic #N, 0  // InvokeDynamic #k:applyAsInt:(I)Ljava/util/function/IntUnaryOperator;
...
invokeinterface #M   // InterfaceMethod IntUnaryOperator.applyAsInt:(I)I
...
invokedynamic #P, 0  // InvokeDynamic #j:makeConcatWithConstants:(I)Ljava/lang/String;
~~~

**Distinguish the two invocations!** `invokedynamic` in the lambda case usually **creates the functional interface object at the call site**; calling `addOffset.applyAsInt(7)` afterward may use `invokeinterface`, not every lambda call executes the same indy opcode. The bootstrap is responsible for creating the linkage/behavior factory; the call site for *creating the lambda object* is a separate layer of meaning from the method invocation on that object.

## 8. Deep dive into LambdaMetafactory

For lambdas or method references, `javac` typically uses `LambdaMetafactory` to create a factory for the functional interface implementation. The typical set of information includes:

1. **Lookup:** the access context of the caller class.
2. **Invoked name:** usually related to the name of the functional interface's abstract method, e.g., `applyAsInt`.
3. **Invoked type:** the descriptor at the call site, returning the functional interface; parameters may be captured values, e.g., `(I)Ljava/util/function/IntUnaryOperator;`.
4. **SAM method type:** the abstract method signature required by the functional interface, e.g., `(I)I`.
5. **Implementation method handle:** a reference to the synthetic/static/instance lambda body method or a matching method reference.
6. **Instantiated method type:** the method type after applying generic adaptation/instantiation of the lambda.

From there, the bootstrap can produce a `ConstantCallSite` whose target is a **factory method handle**, responsible for creating an object compatible with the functional interface. When Java runs `n -> n + offset`, the captured value is typically passed as a **dynamic argument** to the call site's factory. When `applyAsInt` is called on the resulting instance, the generated implementation forwards to the lambda body logic.

### Capturing and “stateless”

If a lambda **does not capture** any variables, the invoked type can have a no-argument descriptor and may be implemented by reusing a single instance. However, **do not rely on the identity** (`==`) of two lambda objects from different evaluations: the language specification does not promise a new object every time or a stable singleton.

If a lambda captures a value, the invoked type can carry the captured values as parameters, e.g., `(I)Ljava/util/function/IntUnaryOperator;`. This does not mean the lambda body runs at factory creation time; creating the lambda instance and calling the instance's method are **two different actions**.

### Method references are not a separate dynamic invocation API

Source expressions `String::length` or `MyClass::staticMethod` may also be implemented by the compiler via `LambdaMetafactory`. However, this is a **compiler choice depending on version/strategy**, not a promise that every `::` expression emits exactly one indy instruction. Inspect actual bytecode instead of hardcoding opcode counts.

## 9. String concatenation via StringConcatFactory

Since Java 9, `javac` typically implements the `+` string concatenation operator via `invokedynamic` with a `StringConcatFactory` bootstrap, rather than always building a `new StringBuilder().append(...).toString()` chain directly at each call site as in older bytecode.

Example:

~~~java
static String describe(String name, int age) {
    return "name=" + name + ", age=" + age;
}
~~~

This is an **illustrative method** to be placed inside a class; it can be compiled in a full example program if desired. Targeting Java 17, the compiler typically uses a call site with an invoked type corresponding to the dynamic variables, such as:

~~~text
(Ljava/lang/String;I)Ljava/lang/String;
~~~

The `StringConcatFactory.makeConcatWithConstants` bootstrap can be supplied with a **recipe string** in the static arguments, in which certain characters mark the positions of dynamic arguments or static constants. **The recipe is bootstrap metadata**, not dynamic input passed from the stack on each call.

When the runtime executes the expression with `name="An"`, `age=20`, the values `"An"` and `20` are the dynamic arguments placed on the stack and passed through the call site to produce the resulting string. The same call site can run again with `name="Binh"`, `age=21` **without needing to bootstrap again to know which method will be used**.

### Is the resulting String also a CallSite?

No. The **CallSite** is the linked object for the instruction. The **String** is the result of the target processing the arguments at runtime. Mixing up these two concepts easily leads to false reasoning such as “every string concatenation creates a CallSite” or “BootstrapMethods contains every resulting string”.

## 10. Standalone Java API example: changing the target of a MutableCallSite

To better understand CallSite, we can manipulate `java.lang.invoke` directly using standard Java. **The example below does not emit a custom `invokedynamic` opcode by itself.** It uses the public API to show that the target of a `CallSite` can be changed. Because Java source code has no operator to emit `invokedynamic` directly, you need a compiler or a class file/bytecode generator when you want to define a custom call site in bytecode.

Create the file **`MutableSiteDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;

public class MutableSiteDemo {
    private static String first(String name) {
        return "A:" + name;
    }

    private static String second(String name) {
        return "B:" + name;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type = MethodType.methodType(String.class, String.class);

        MethodHandle initial = lookup.findStatic(
                MutableSiteDemo.class, "first", type);

        MutableCallSite site = new MutableCallSite(initial);
        MethodHandle invoker = site.dynamicInvoker();

        String before = (String) invoker.invokeExact("x");
        System.out.println("before=" + before);

        MethodHandle replacement = lookup.findStatic(
                MutableSiteDemo.class, "second", type);

        site.setTarget(replacement);
        MutableCallSite.syncAll(new MutableCallSite[] { site });

        String after = (String) invoker.invokeExact("x");
        System.out.println("after=" + after);
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 MutableSiteDemo.java
java MutableSiteDemo
~~~

**Exact stdout:**

~~~text
before=A:x
after=B:x
~~~

Explanation:
- `MethodType.methodType(String.class, String.class)` describes a target that takes a `String` and returns a `String`.
- `findStatic` obtains the method handle of `first`. `MutableCallSite` holds that target.
- `dynamicInvoker()` returns a handle whose behavior follows the site's current target.
- `setTarget(replacement)` changes the target; `syncAll` demonstrates how to signal synchronization when multiple threads observe the site. In this single-thread example, the before/after results are deterministic as printed.
- `invokeExact("x")` requires exact parameter and return types matching the `MethodType`; the `(String)` cast at the call site helps the compiler emit the matching return signature for the invocation.

**Do not confuse `CallSite` with `invokedynamic`:** This Java API demonstrates the site object and method handles. The `MethodHandle.invokeExact` call in the class file has special signature-polymorphic `invokevirtual` rules; it is not a way to prove that a custom `invokedynamic` instruction was emitted. With the lambda example above, you observe a case where the compiler actually emits indy.

## 11. Distinguishing invokedynamic and dynamic constant (condy)

Both `CONSTANT_InvokeDynamic` and `CONSTANT_Dynamic` use the bootstrap table, but their purposes differ.

| Criterion | `CONSTANT_InvokeDynamic` | `CONSTANT_Dynamic` |
| --- | --- | --- |
| Constant pool tag | **18** | **17** |
| Used to | Describe a **call site** to be linked | Describe a **constant value** to be computed upon resolution |
| `NameAndType` descriptor | **Method descriptor** such as `(I)Ljava/lang/String;` | **Field descriptor** such as `Ljava/lang/String;` or `J` |
| How it is used | Opcode **`invokedynamic`** | One of the constant-loading instructions `ldc`/`ldc_w`/`ldc2_w` according to type and rules |
| Bootstrap result | A **`CallSite`** compatible with the descriptor | A **value** compatible with the described constant type |
| Available since | Class file major **51** (Java 7) | Class file major **55** (Java 11) |

**BootstrapMethods** can contain entries serving both kinds. That does **not** make the two kinds the same: indy is an invocation mechanism; condy is a constant-computation mechanism. If you see `Dynamic` in `javap -v`, do not automatically conclude that the class contains an `invokedynamic` instruction.

### Related reference kinds also differ

| Constant pool kind | Purpose |
| --- | --- |
| `CONSTANT_Methodref` | Symbolic reference for a class method under normal resolution rules |
| `CONSTANT_InterfaceMethodref` | Symbolic reference for an interface method |
| `CONSTANT_MethodHandle` | Describes a method handle, consisting of a reference kind and an index to the appropriate reference |
| `CONSTANT_MethodType` | Describes a method type via a descriptor |
| `CONSTANT_InvokeDynamic` | Describes a dynamic call site, pointing to a bootstrap index and `NameAndType` |
| `CONSTANT_Dynamic` | Describes a dynamic constant, pointing to a bootstrap index and `NameAndType` |

Although many entry names start with `CONSTANT_`, **the constant pool does not only contain literal values**. It also contains metadata that helps the JVM link code at runtime.

## 12. Errors in dynamic call site linking

When the bootstrap cannot run or cannot produce a valid result, the JVM typically reports **`BootstrapMethodError`**, a form of linkage error. Cases to consider:

- The bootstrap method handle cannot be resolved due to a wrong class/entry, access error, or binary incompatibility.
- The bootstrap throws an exception, dependency initialization fails, or it executes buggy logic.
- The bootstrap returns **null** or an object that is not a `CallSite` in the indy case.
- The bootstrap returns a `CallSite` whose type does not match the call site's method descriptor.
- `BootstrapMethods`/constant pool contains an invalid index or tag, or the class file fails format/verification constraints — some situations may manifest as **`ClassFormatError`, `VerifyError`, or another linkage error**, not necessarily wrapped in `BootstrapMethodError`.

**Do not diagnose every `BootstrapMethodError` as “missing lambda class”.** Inspect the root cause, call site name/type, bootstrap method handle, static arguments, class loading, and related dependency versions.

### What happens when a bootstrap fails?

Once the JVM determines that resolution of an indy instruction **has failed**, subsequent attempts on **the same instruction** do not automatically re-invoke the bootstrap to “try its luck” on every invocation. Resolution failure is persisted according to specification semantics. This is important: the bootstrap is not a retry mechanism for temporarily failing network, IO, or registry calls. If you want runtime logic that can change, you should successfully link to a `CallSite` with an appropriate target so that the target itself handles retry/fallback by design.

### Concurrency issues in bootstrapping

If two threads reach an unlinked call site at the same time, the JVM may allow the bootstrap to run multiple times in a race. Although only one result is accepted to link the instruction, **side effects occurring in the non-selected bootstrap executions can still be observed**. Therefore, bootstraps should have pure/minimal side effects, or be designed to be idempotent and thread-safe when updating caches/registries.

### Changing to an incompatible target type

For an already-linked `CallSite`, `setTarget` on a mutable kind must still respect the corresponding type; an incompatible target will cause an error at the API level. You cannot change from an `(int)int` handle to `(String)String` for the same call site simply by assigning arbitrarily.

## 13. How to read javap step by step

With `InvokeDynamicDemo.class`, follow these steps:

1. Run `javap -c -p InvokeDynamicDemo` to identify which methods contain `invokedynamic` instructions and what the operand index `#N` is.
2. Run `javap -v -p InvokeDynamicDemo`. In the **Constant pool** section, find `#N = InvokeDynamic #k:#m`.
3. Follow `#m` to `NameAndType`, then inspect the **call site name** and **method descriptor**. The descriptor tells you which dynamic arguments must be on the operand stack.
4. Follow **`#k` in the comment/table** to the **BootstrapMethods** section at the end of the output. Note that the bootstrap index is 0-based.
5. In the bootstrap entry, read `REF_invokeStatic ...LambdaMetafactory.metafactory` or `...StringConcatFactory.makeConcatWithConstants` if using `javac` as in the example setup.
6. Follow the **Method arguments** as static bootstrap arguments such as method handle, method type, recipe; do not treat them as runtime data passed every time.
7. Cross-check the bytecode preparing the stack right before the `invokedynamic` instruction: `iload`, `aload`, or other opcodes pushing dynamic arguments matching the descriptor.
8. Inspect the instruction **after** indy: what does the call site return? If it returns a functional interface, there will be subsequent code storing/executing that instance, often via `invokeinterface`.
9. Record the compiler, target class file, and results in your notes; **do not hardcode `#N` indices** across compilations.

### Map form in javap

~~~text
Code:
  ...
  invokedynamic #N, 0      // InvokeDynamic #k:someName:(I)Ljava/lang/Runnable;
  ...

Constant pool:
  #N = InvokeDynamic #k:#m  // #k:someName:(I)Ljava/lang/Runnable;
  #m = NameAndType   #a:#b
  #a = Utf8          someName
  #b = Utf8          (I)Ljava/lang/Runnable;
  ...

BootstrapMethods:
  k: #handle REF_invokeStatic some/bootstrap/Owner.bootstrap:...
    Method arguments:
      #arg1 ...
      #arg2 ...
~~~

This is a **generalized representation pattern**, not the exact output of a specific class or an assertion that the bootstrap is always in a class named `some.bootstrap.Owner`. In a dump, `javap` may print multiple levels of interpreted comments to make it easier to read.

## 14. Practical scenarios and common misconceptions

| Claim / scenario | Correct analysis |
| --- | --- |
| “`invokedynamic` calls a method whose name is stored in the constant pool, like `invokevirtual`.” | Indy links via the specified bootstrap; the call site name/type is metadata, and the target is obtained from `CallSite`. |
| “The bootstrap runs before every time a lambda is called.” | The bootstrap serves site linking; a lambda object can be created via the linked site, and then the SAM method is invoked by another mechanism. |
| “One `InvokeDynamic` entry must have one shared target for every instruction referencing it.” | Call site linkage is attached per **instruction occurrence**. |
| “The bootstrap always runs physically only once.” | Racing threads may perform multiple bootstrap executions; only one result is chosen. |
| “BootstrapMethod index `#0` is constant pool entry number 0.” | The bootstrap table is 0-indexed; the constant pool starts at 1. |
| “Dynamic arguments are the Method arguments listed in `BootstrapMethods`.” | Method arguments in the attribute are **static bootstrap arguments**; dynamic invocation arguments are on the operand stack. |
| “`CallSite` is the String result of string concatenation.” | CallSite describes the linked target; String is the result of each invocation. |
| “`MutableCallSite.setTarget` makes all threads immediately see the new target.” | Visibility rules apply; use `syncAll` or `VolatileCallSite` when appropriate. |
| “Seeing `invokedynamic` means the JVM must use reflection.” | The core mechanism is based on MethodHandle/CallSite, not synonymous with `java.lang.reflect.Method.invoke`. |
| “`invokedynamic` is always slow because of the bootstrap.” | Bootstrapping is a site-linking cost; afterward the JIT can optimize, though performance depends on target, site kind, and workload. |
| “Lambdas always generate a separate class file before runtime.” | The compiler/runtime can generate implementations flexibly; do not infer file structure based on one implementation strategy. |
| “Any method handle can be a bootstrap.” | It must satisfy parameter/return type rules and CallSite/type requirements. |
| “Having `Dynamic` in the constant pool means there is an indy call site.” | `CONSTANT_Dynamic` is a dynamic constant (condy); it is different from `CONSTANT_InvokeDynamic`. |
| “All synthetic lambda names will always follow one format.” | Generated method names/counts are compiler details. |
| “A failed bootstrap can be retried freely on the next call.” | Failed resolution has error-caching rules; it does not automatically repeat the bootstrap per invocation. |

## 15. When does a developer need to know this mechanism?

You will usually **not need to create indy call sites yourself** in everyday Java business code. This knowledge is useful when:

- **Reading bytecode**: understanding why `javap -c` shows `invokedynamic` even when the Java source only has lambdas or string concatenation.
- **Diagnosing linking errors**: when seeing `BootstrapMethodError`/`LambdaConversionException` or errors when running classes generated by bytecode tooling.
- **Developing compilers/JVM languages or bytecode tooling**: generating bootstraps, call site descriptors, dynamic constants, method handles, and proper information in `BootstrapMethods`.
- **Understanding performance/JIT**: distinguishing one-time linking cost from continuous invocation; evaluating stable targets versus mutable targets.
- **Designing systems that change behavior at runtime**: using the MethodHandle/CallSite API when dynamic linking is genuinely needed, while controlling thread safety, type safety, and observable behavior.

If you only want to call normal Java methods, you should not choose invokedynamic as a default “optimization trick”. Each `invoke*` opcode has its own semantics, and how the compiler uses them should be based on program requirements.

## 16. Self-check

**Question 1.** Does `invokedynamic` require the target method's owner class to be stored in `CONSTANT_InvokeDynamic`?

**Answer:** No. The entry contains **bootstrap_method_attr_index** and **name_and_type_index**. The bootstrap determines the target by returning a CallSite, rather than specifying only an owner/method reference like `Methodref`.

**Question 2.** Is index 0 in `BootstrapMethods` the same as `constant_pool[0]`?

**Answer:** No. The `bootstrap_methods[]` list starts at 0, while the constant pool starts at 1. Inside the bootstrap entry, `bootstrap_method_ref` points back into the constant pool.

**Question 3.** What does a call site `(I)Ljava/lang/String;` take and return?

**Answer:** Each invocation takes one dynamic argument of type int from the operand stack and returns a reference to a String on the stack. It says nothing about the number of static bootstrap arguments.

**Question 4.** Why does `LambdaMetafactory` need an implementation method handle?

**Answer:** The bootstrap needs to know which method logic the functional interface implementation will invoke. The method handle describes the implementation, while the SAM method type and instantiated method type describe the type contract.

**Question 5.** Does calling a lambda `op.applyAsInt(5)` always execute `invokedynamic` again?

**Answer:** No. `invokedynamic` is usually used to create the lambda factory/object; calling the method on the object afterward can use `invokeinterface` or another appropriate invocation mechanism.

**Question 6.** Two indy instructions at different bytecode locations reference the same constant pool entry. Is there guaranteed to be only one CallSite?

**Answer:** No. Successful linkage is established per **instruction occurrence**, even when the symbolic constant pool entry is the same.

**Question 7.** What happens if the bootstrap returns `null` or a CallSite with the wrong type?

**Answer:** Call site resolution fails, typically causing `BootstrapMethodError` according to JVMS rules.

**Question 8.** Why should a bootstrap avoid non-idempotent side effects?

**Answer:** Because threads can race to resolve the same unlinked site, causing multiple bootstrap executions, while only one result is chosen.

**Question 9.** How does `MutableCallSite` differ from `ConstantCallSite`?

**Answer:** The target of a MutableCallSite can be changed via `setTarget` and requires attention to visibility, whereas ConstantCallSite keeps its target immutable after proper initialization.

**Question 10.** Does `CONSTANT_Dynamic` carry a method descriptor for calling a method?

**Answer:** No. `CONSTANT_Dynamic` describes a **dynamic constant** with a **field descriptor**; method descriptors are for `CONSTANT_InvokeDynamic`.

**Question 11.** If you encounter `BootstrapMethodError` on the first call, should you retry the same instruction so the bootstrap runs again automatically?

**Answer:** No. The JVM preserves the resolution error state according to the specification. Identify and fix the bootstrap, type, class loading, or dependency issue.

**Question 12.** If you change the target of a `MutableCallSite` in one thread, will all other threads see it immediately?

**Answer:** Not automatically guaranteed like volatile in all cases. You need to use `syncAll` or an appropriate design such as `VolatileCallSite` depending on visibility requirements.

## 17. Memory map

~~~text
ClassFile
  |
  +-- constant_pool
  |     +-- CONSTANT_InvokeDynamic (tag 18)
  |             +-- NameAndType  -> name + METHOD descriptor
  |             +-- bootstrap_method_attr_index -> BootstrapMethods[k]
  |
  +-- BootstrapMethods attribute
        +-- bootstrap_method_ref  -> CONSTANT_MethodHandle
        +-- bootstrap_arguments[] -> supported CONSTANT_*
Runtime:
  opcode invokedynamic #N, 0
             |
             v
      [site unlinked?]
             |
             +-- yes -> resolve metadata -> invoke bootstrap
             |                            -> validate CallSite / type
             |                            -> bind result to instruction
             |
             v
         target MethodHandle
             |
             +-- ConstantCallSite: stable target
             +-- MutableCallSite : mutable target, mind sync
             +-- VolatileCallSite: mutable target, volatile semantics
             |
             v
       dynamic args from operand stack
             |
             v
       execute target -> push return if non-void
~~~

**Key takeaway:** `invokedynamic` provides a **call site with custom linking via a bootstrap**; `BootstrapMethods` carries the method and constants for linking; `CallSite` is the linkage result holding the target MethodHandle; and **dynamic arguments** are only passed when actually invoking. Clearly separating these four concepts is the key to understanding lambdas, string concatenation, and call-site linking in the JVM.

## Official references

- [JVMS Java SE 21 — `4.4.10` CONSTANT_InvokeDynamic and CONSTANT_Dynamic](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.4.10).
- [JVMS Java SE 21 — `4.7.23` BootstrapMethods attribute](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.23).
- [JVMS Java SE 21 — `5.4.3.6` Dynamic constant and call site resolution](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4.3.6).
- [JVMS Java SE 21 — `6.5` invokedynamic](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html#jvms-6.5.invokedynamic).
- [Java SE 17 API — CallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html).
- [Java SE 17 API — LambdaMetafactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html).
- [Java SE 17 API — StringConcatFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html).
- [JDK 17 javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
