# 11.1 Purpose of `invokedynamic` and Differences from `invokevirtual` or `invokeinterface`

In JVM bytecode, `invokevirtual` and `invokeinterface` represent calls following a **class/interface method contract**: the bytecode references a specific method in the constant pool, and at runtime the JVM selects the implementation corresponding to the receiver according to dispatch rules. `invokedynamic` solves a different problem: **linking a call site with an invocation behavior determined via a bootstrap method**, instead of forcing the bytecode from the start to reference a method of a class/interface under traditional dispatch.

`invokedynamic` was introduced to the JVM in Java 7 (JSR 292). It allows a compiler or runtime to determine how a call site behaves **at linking time**, through `MethodHandle` and `CallSite`. As a result, the JVM better supports dynamic invocation styles, languages running on the JVM, lambdas, and Java compiler optimization strategies, while still preserving strict rules on the call site's **parameter and result signatures**.

This lesson directly answers: what `invokedynamic` exists for, how it differs from `invokevirtual`/`invokeinterface`, what happens at the bootstrap step, and how to observe them in Java 17+.

**After this lesson, you will be able to:**

- Explain why both `invokevirtual` and `invokeinterface` support polymorphism yet still differ from `invokedynamic`.
- Read an `InvokeDynamic` entry in the constant pool and a `BootstrapMethods` entry via `javap -v`.
- Distinguish **linkage** from **execution**: the bootstrap creates/returns a `CallSite`; subsequent calls use the call site's target.
- Understand the roles of `MethodHandles.Lookup`, call-site name, `MethodType`, bootstrap arguments, `CallSite`, and `MethodHandle`.
- Recognize where the Java compiler may emit `invokedynamic`: lambdas, method references, and string concatenation.
- Understand why `ConstantCallSite` differs from `MutableCallSite` or `VolatileCallSite`, along with the limits of changing the target.
- Diagnose linkage errors such as `BootstrapMethodError` without confusing them with errors thrown by the target method.

## 1. Three bytecode instructions solving three invocation mechanisms

A Java source statement such as `receiver.doWork()` does not by itself tell which bytecode is emitted: it also depends on the static type of the receiver, method kind, and compiler. The three instructions within the scope of this lesson are:

| Instruction | Reference in bytecode/constant pool | What the JVM does on call | Typical cases |
| --- | --- | --- | --- |
| `invokevirtual` | Symbolic method reference tied to a class and method name/signature | Dispatches to the appropriate implementation based on the receiver's actual class, following method selection rules | Instance method of a class; overriding between superclass/subclass |
| `invokeinterface` | Symbolic interface-method reference tied to an interface and method name/signature | Dispatches through the interface contract and the receiver's actual class, considering implementation/default method rules | Calling a method on a variable of an interface type |
| `invokedynamic` | **Call-site specifier**: name/signature of the dynamic invocation and bootstrap information | Resolves the bootstrap to obtain a `CallSite`; after linking, invokes the call site's target `MethodHandle` | Lambda factory, string concatenation, certain dynamic languages, and bytecode-generated code |

The first two instructions can both invoke different behaviors at runtime thanks to **overriding or the receiver's implementation**. Therefore, it would be **wrong** to explain that `invokevirtual`/`invokeinterface` are "static" and only `invokedynamic` is "dynamic".

**The key difference:** with `invokevirtual`/`invokeinterface`, the instruction itself represents a **method reference under the class/interface model**. With `invokedynamic`, the instruction represents a **call site linked by a bootstrap method**, allowing the bootstrap to decide what the target is—potentially building adapters, creating factories, caching, or choosing an appropriate runtime strategy.

### 1.1. Intuitive example of `invokevirtual`

```java
class Animal {
    String sound() { return "generic"; }
}

class Dog extends Animal {
    @Override
    String sound() { return "woof"; }
}

// Illustrative snippet:
Animal animal = new Dog();
String value = animal.sound(); // "woof"
```

Even though the variable `animal` has static type `Animal`, the actual receiver is `Dog`, so the virtual call goes to the override `Dog.sound()`. The JVM does not need a custom bootstrap method for that: polymorphic dispatch is already built into `invokevirtual`.

### 1.2. Intuitive example of `invokeinterface`

```java
interface Formatter {
    String format(String text);
}

class PlainFormatter implements Formatter {
    @Override
    public String format(String text) {
        return "[" + text + "]";
    }
}

// Illustrative snippet:
Formatter formatter = new PlainFormatter();
String value = formatter.format("A"); // "[A]"
```

Calling `formatter.format("A")` on an interface type normally produces `invokeinterface`. The fact that the concrete implementation can vary by object is **interface polymorphism**, not `invokedynamic`.

Both snippets above only illustrate class/interface structure; a complete, compilable program with bytecode verification is in section 4.

## 2. Why is `invokedynamic` needed if the JVM already has dynamic dispatch?

`invokevirtual` and `invokeinterface` work well when a call can be expressed as "call method named X/signature Y via class/interface Z". However, languages or runtimes may need to:

1. **Select behavior at the call site according to language rules**, not necessarily according to a method name of a known Java class/interface.
2. **Construct a target from a set of operations**: a method handle to an actual method, method adapters, type checks, argument conversions, composed operations, or an optimization strategy.
3. **Pass additional information to the bootstrap** from the compiler, such as a recipe for string concatenation or a method handle to a lambda body.
4. **Link once and reuse** the linked call site, instead of requiring the compiler to hand-write a dispatch chain with reflection or a fixed wrapper class for every variant.
5. With an appropriate model, **change the target of a call site with a stable type** when the dispatch strategy changes. This requires `MutableCallSite`/`VolatileCallSite` or a corresponding runtime mechanism; it does not mean every `invokedynamic` automatically changes its target.

Two practical **Java** examples:

- **Lambdas and method references:** the compiler may emit `invokedynamic` to link a *factory* that creates a functional interface object, commonly using `LambdaMetafactory`. After the object is created, calling the functional interface's method can still be **`invokeinterface`**.
- **String concatenation:** for modern Java bytecode targets, the compiler may emit `invokedynamic` and use `StringConcatFactory` to organize string concatenation, instead of always emitting a `new StringBuilder` + `append` sequence.

**You should not say** that every lambda/method reference or every string concatenation will always have an `invokedynamic` in every compiler/JDK/optimization mode. This is a bytecode strategy chosen by the compiler. Inspecting the actual `.class` file with `javap` is the evidence for a specific build.

## 3. Structure of a dynamic call site

At the JVM level, an `invokedynamic` instruction references a `CONSTANT_InvokeDynamic_info` entry in the constant pool. That entry connects to:

- **`bootstrap_method_attr_index`**: the position in the class-file `BootstrapMethods` attribute containing a handle to the bootstrap method and static bootstrap arguments.
- **`name_and_type_index`**: the name and *method descriptor* of the dynamic call site, for example `format:()LMyFormatter;` or `makeConcatWithConstants:(I)Ljava/lang/String;`.

You should not read the name `format` or `makeConcatWithConstants` in the `invokedynamic` line as "this is the instance method that the JVM will call". That is the **name used when linking the call site**; the bootstrap has the right to interpret the name according to its own contract. `CONSTANT_InvokeDynamic_info` is not a `CONSTANT_Methodref` pointing directly to an owner class and method implementation.

Model:

```text
              Class file
        +---------------------+
        | invokedynamic #N    |
        +----------+----------+
                   |
                   v
        CONSTANT_InvokeDynamic
        +---------------------+
        | bootstrap index     |----> BootstrapMethods
        | NameAndType         |       - bootstrap MethodHandle
        +----------+----------+       - static bootstrap arguments
                   |
                   v
            Call-site type
           (arguments)result
                   |
          JVM resolve/link site
                   |
                   v
          invoke bootstrap method
           (Lookup, name, MethodType,
            optional static arguments)
                   |
                   v
                CallSite
                   |
                   v
             target MethodHandle
                   |
                   v
            execute target with
            dynamic arguments
```

The diagram only shows the **logical sequence**; it does not imply that the class file pre-stores a `CallSite` object. The call-site object is created/obtained during linking at runtime.

### 3.1. What does a bootstrap method typically receive?

A common form:

```java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType invokedType) throws Throwable {
    // Find/adapt the target MethodHandle, check the contract, and return a CallSite.
}
```

This is **illustrative skeleton code**, without a complete body. The three core arguments:

1. `caller` (`MethodHandles.Lookup`): the lookup context of the class containing the dynamic instruction, along with its corresponding privileges. It is not "granted private access to every class".
2. `name` (`String`): the call-site name recorded by the compiler/bytecode. The bootstrap decides its meaning.
3. `invokedType` (`MethodType`): the required signature of the dynamic instruction: **the types of all arguments and the return type**.

In addition to the three core parts, the compiler can configure **static bootstrap arguments**. The JVM passes them to the bootstrap in the recorded order. For example, a lambda metafactory typically receives the SAM type, the implementation method handle, and the instantiated method type; a string concat factory may receive a recipe and constants.

**Distinguishing static bootstrap arguments from dynamic arguments:**

- Static bootstrap args are metadata/constants supplied when **linking the call site**.
- Dynamic arguments are values on the operand stack passed in **each time** the linked instruction is executed.

If a string concatenation site receives an `int` as a dynamic argument, that `int` can change on each call; the bootstrap recipe is not reprocessed for each value because of that.

### 3.2. When is the bootstrap executed?

The JVM resolves the call-site specifier when it needs to link the dynamic instruction. The exact timing may relate to how the runtime decides to resolve, but the important point is: **after successful linking, the instruction is bound to the chosen `CallSite` object**. Subsequent executions do not automatically re-invoke the bootstrap just because argument values change.

A nuance from the JVMS: if multiple threads concurrently resolve the same site, the bootstrap **may be invoked on multiple threads**; the JVM chooses one `CallSite` to install, and the other results are discarded. Therefore, "the bootstrap is guaranteed to be called exactly once across the entire program" is too strong a claim. A bootstrap with side effects must ensure thread safety itself.

Call-site binding and target binding are also different:

- A linked **dynamic instruction** is bound to the chosen `CallSite` object.
- `CallSite` has a `target` which is a `MethodHandle`. For call-site types that allow changing the target, the same call-site object can be **relinked** to a new target while keeping the same **MethodType**.
- `ConstantCallSite` does not allow changing the target after creation. `MutableCallSite` or `VolatileCallSite` can change the target according to their respective semantics.

## 4. Complete Java 17+ program: seeing all three instructions

Create the file **`InvokeDynamicContrastDemo.java`**:

```java
import java.util.Locale;

public class InvokeDynamicContrastDemo {
    static class Animal {
        String sound() { return "generic"; }
    }

    static class Dog extends Animal {
        @Override
        String sound() { return "woof"; }
    }

    interface Formatter {
        String format(String text);
    }

    static class PlainFormatter implements Formatter {
        @Override
        public String format(String text) { return "[" + text + "]"; }
    }

    static String display(Formatter formatter, String value) {
        return formatter.format(value);
    }

    static String message(int number) {
        return "id=" + number;
    }

    public static void main(String[] args) {
        Animal animal = new Dog();
        System.out.println("virtual: " + animal.sound());

        Formatter formatter = new PlainFormatter();
        System.out.println("interface: " + display(formatter, "A"));

        Formatter lambda = value -> value.toUpperCase(Locale.ROOT);
        System.out.println("lambda: " + display(lambda, "hello"));

        System.out.println("concat: " + message(12));
    }
}
```

Compile and run:

```bash
javac --release 17 InvokeDynamicContrastDemo.java
java InvokeDynamicContrastDemo
```

**Stdout verified with the real program:**

```text
virtual: woof
interface: [A]
lambda: HELLO
concat: id=12
```

Reading the source:

- `Animal animal = new Dog()` then calling `animal.sound()`: the receiver has runtime type `Dog`, the JVM selects the override `Dog.sound()`, printing `woof`.
- `display` takes a variable of type `Formatter` and calls `formatter.format(value)`: a polymorphic operation via an interface.
- `Formatter lambda = value -> ...` is an expression that the compiler can represent with a dynamic factory call site; the factory returns a `Formatter` object, and then `display` **still calls** `Formatter.format` via the interface.
- `message(int)` concatenates a string with `number`, which is a runtime value, sufficient to observe a string-concat call site in the built class file.

At the same time, `System.out.println(...)` is another instance method call, so the bytecode may contain **multiple** `invokevirtual` instructions; you should not infer that each source line corresponds to exactly one invoke instruction.

### 4.1. Viewing bytecode with `javap`

After compiling, run:

```bash
javap -c -p InvokeDynamicContrastDemo
javap -v InvokeDynamicContrastDemo
```

In the `javap -c -p` output, you will see lines **of the form** (index/offset numbers omitted because they depend on the compiler and build):

```text
invokevirtual      // Method InvokeDynamicContrastDemo$Animal.sound:()Ljava/lang/String;
invokeinterface    // InterfaceMethod InvokeDynamicContrastDemo$Formatter.format:(Ljava/lang/String;)Ljava/lang/String;
invokedynamic      // InvokeDynamic ...:format:()LInvokeDynamicContrastDemo$Formatter;
invokedynamic      // InvokeDynamic ...:makeConcatWithConstants:(I)Ljava/lang/String;
```

The `javap -v` command will show the `BootstrapMethods` section with method handles referencing factories, such as:

```text
java/lang/invoke/LambdaMetafactory.metafactory
java/lang/invoke/StringConcatFactory.makeConcatWithConstants
```

In the experiment, `javac --release 17` generated these exact instruction types and `javap` confirmed `invokevirtual`, `invokeinterface`, `invokedynamic`, and the two bootstrap factories. **Do not** treat offsets/constant-pool indices or the order of bootstrap entries as a stable API: they can differ across compilers/JDKs, flags, and edited source code.

### 4.2. Why does an interface call still exist when using a lambda?

The lambda line has two distinct parts:

```java
Formatter lambda = value -> value.toUpperCase(Locale.ROOT);
String result = lambda.format("hello");
```

1. **Creating/obtaining the functional interface object:** may use `invokedynamic` with `LambdaMetafactory` as the bootstrap. The call site can act as a **factory** returning an instance compatible with `Formatter`. For a **non-capturing** lambda like this example, the factory needs no capture arguments.
2. **Calling the SAM method on the object:** `lambda.format(...)` is a regular interface invocation. The bytecode can be `invokeinterface`.

It is not that `invokedynamic` "replaces `invokeinterface`". They can appear in **the same execution flow** for two different tasks. A capturing lambda (for example, capturing an effectively final local variable) can generate a factory call site **with dynamic arguments** representing the captured values.

### 4.3. Looking at `StringConcatFactory`

With:

```java
static String message(int number) {
    return "id=" + number;
}
```

A modern compiler can choose a call site that returns `String` and takes `int`: `(I)Ljava/lang/String;` (in JVM method descriptor form). The bootstrap `StringConcatFactory.makeConcatWithConstants` can receive a **recipe** containing the literal `"id="` along with a placeholder for the dynamic argument.

To avoid confusion:

- `makeConcatWithConstants` is the **bootstrap method** in metadata; it does not mean every call to `message(n)` re-runs the bootstrap.
- `number` is a **dynamic argument** at execution time.
- The output is a `String`, produced by the appropriately linked target method handle.
- The compiler may constant-fold all-literal concatenations; not every `"a" + "b"` produces `invokedynamic`.

## 5. `invokevirtual` and `invokeinterface`: polymorphism with built-in rules

When calling a regular instance method, the JVM performs two groups of tasks:

- **Resolution:** the symbolic reference identifies the referenced method, the associated class/interface, and access/lookup rules.
- **Method selection/dispatch:** based on the receiver and overriding/implementation rules to select the method body to run.

This is **dispatch fixed by JVM semantics**. The JVM does not ask the application for a bootstrap callback to make an arbitrary choice. If `Animal a = new Dog()`, `invokevirtual Animal.sound` can select `Dog.sound` due to overriding. If `Formatter f` holds an instance of a concrete implementing class, `invokeinterface Formatter.format` finds the valid implementation according to interface invocation rules.

### 5.1. The difference is not early binding versus late binding

A common mistaken comparison:

```text
invokevirtual   = static
invokeinterface = static
invokedynamic   = dynamic
```

This comparison misleads readers into thinking the first two instructions have no runtime polymorphism. In reality:

- Both `invokevirtual` and `invokeinterface` **can select different implementations at runtime** when the receiver differs.
- `invokedynamic` adds **the ability to program how a call site's target is linked**. The bootstrap can produce a stable target or a changeable target, depending on the `CallSite`.
- Depending on the target, `invokedynamic` can also invoke a method handle representing a **virtual invocation**. It does not eliminate the dispatch rules underneath a chosen target.

**In summary:** polymorphism on the receiver and bootstrap-defined call-site linkage are two different concepts, not two simple "dynamic/static" levels.

### 5.2. `invokeinterface` does not have only one fixed method body

An interface can have many implementors, and since Java 8, default methods. `invokeinterface` performs method selection according to JVM rules, and can select an implementation in a class or an appropriate default method. Cases with no valid implementation or with conflicts lead to the appropriate resolution/invocation errors. You should not present `invokeinterface` as a "simulated" function call completely outside the JVM.

### 5.3. Other invoke instructions have their own roles

To see the full picture:

- `invokestatic`: static method call; no receiver dispatch like virtual invocation.
- `invokespecial`: used for instance initialization (`<init>`), private method invocation, and special call cases such as `super`.
- `invokevirtual`, `invokeinterface`: the instance invocation forms compared in this lesson.
- `invokedynamic`: linked via call-site specifier + bootstrap.

All are JVM instructions, not a Java API you can call directly by writing `invokedynamic(...)` in standard Java source.

## 6. Linking and execution: the bootstrap is not the target method

The linking and invocation process can be illustrated with pseudocode:

```text
When the call site needs to be resolved:
    bootstrap = resolveBootstrapMethod(...)
    type = resolveCallSiteMethodType(...)
    staticArgs = resolveBootstrapArguments(...)
    callSite = bootstrap(callerLookup, callSiteName, type, staticArgs...)
    verify(callSite != null)
    verify(callSite.type() == type)
    bindDynamicInstructionTo(callSite)

Each time the linked instruction is executed:
    arguments = valuesFromOperandStack()
    target = callSite.getTarget()
    result = invokeTargetWithExactDescriptor(target, arguments)
```

**This is pseudocode**, not Java/JVM implementation code. The JVM is not required to execute each step as functions with those names; the specification defines the observable behavior.

Important conditions:

1. The bootstrap method must supply a valid `CallSite`.
2. `CallSite.type()` must **match the method descriptor** of the dynamic instruction in both parameter and return types.
3. After successful linking, the target is invoked as if via `MethodHandle.invokeExact` according to the dynamic site's descriptor. This is the **instruction's semantics**, not a requirement that Java source must write `invokeExact` for every `invokedynamic`.
4. With `ConstantCallSite`, the target does not change; with `MutableCallSite`/`VolatileCallSite`, the target is updated according to the corresponding rules, but **the type must not change**.
5. If the target method throws a `RuntimeException` or `Error` during execution after linkage, that is a **target error**, and does not automatically turn into a bootstrap error.

### 6.1. `CallSite` and `MethodHandle` are different

`MethodHandle` describes an invokable operation and a `MethodType` signature. `CallSite` holds a **target MethodHandle** with a stable `MethodType`, and can provide `dynamicInvoker()` to invoke the current target.

Visualization:

```text
invokedynamic instruction  -->  CallSite object
                                    |
                                    +-- current target: MethodHandle
                                    |             |
                                    |             +-- target code / adapters
                                    |
                                    +-- type: (arguments)result
```

You should not treat a `MethodHandle` object created manually with `findStatic` as an `invokedynamic` instruction. It is only a potential target. The connection to a bytecode instruction arises when the JVM resolves a real `CONSTANT_InvokeDynamic_info`.

## 7. Complete example: building a bootstrap/`ConstantCallSite` with the Java API

In regular Java source, we can write a **bootstrap method** and call it ourselves to observe the `CallSite` mechanism. This example **simulates the linking construct**; it **does not emit a custom `invokedynamic` instruction**. To create `invokedynamic` with a custom bootstrap in a class file, you need an appropriate compiler/code generator/bytecode tooling.

Create the file **`BootstrapModelDemo.java`**:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.ConstantCallSite;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Locale;

public class BootstrapModelDemo {
    private static String upper(String text) {
        return text.toUpperCase(Locale.ROOT);
    }

    public static CallSite bootstrap(
            MethodHandles.Lookup caller,
            String name,
            MethodType type) throws ReflectiveOperationException {
        if (!name.equals("transform")) {
            throw new IllegalArgumentException("Unknown operation: " + name);
        }

        MethodHandle target = caller.findStatic(
                BootstrapModelDemo.class, "upper",
                MethodType.methodType(String.class, String.class));
        if (!target.type().equals(type)) {
            throw new IllegalArgumentException("Mismatched target type");
        }
        return new ConstantCallSite(target);
    }

    public static void main(String[] args) throws Throwable {
        MethodType descriptor =
                MethodType.methodType(String.class, String.class);
        CallSite site = bootstrap(
                MethodHandles.lookup(), "transform", descriptor);
        MethodHandle invoker = site.dynamicInvoker();

        String result1 = (String) invoker.invokeExact("abc");
        String result2 = (String) invoker.invokeExact("java");
        System.out.println("call-site type: " + site.type());
        System.out.println("first: " + result1);
        System.out.println("second: " + result2);
    }
}
```

Compile and run:

```bash
javac --release 17 BootstrapModelDemo.java
java BootstrapModelDemo
```

Verified stdout:

```text
call-site type: (String)String
first: ABC
second: JAVA
```

**Component-by-component explanation:**

- `MethodType.methodType(String.class, String.class)` requires taking one `String` and returning `String`: `(String)String`.
- `name` is `"transform"` passed by the caller. It does not need to match the Java method name `upper`, because the bootstrap actively interprets the name.
- `caller.findStatic(...)` returns a `MethodHandle` to `upper`. The caller has appropriate privileges in the example because it is in the same class.
- `new ConstantCallSite(target)` holds a target that cannot be replaced with another target after creation.
- `site.dynamicInvoker()` is a `MethodHandle` linked to the site's target. The two calls with `"abc"` and `"java"` run the same logic using different data.
- `(String) invoker.invokeExact(...)` explicitly specifies the return type `String`, matching the target signature.

**Boundary of the example:** the `bootstrap(...)` line is called as a **regular Java method**; the JVM does not perform `CONSTANT_InvokeDynamic_info` resolution for that line. Therefore it does not prove that `invokedynamic` is emitted from a custom bootstrap; the example helps understand **the kind of object** a real bootstrap needs to return.

### 7.1. Why is there a `Lookup` parameter?

`MethodHandles.Lookup` encapsulates the caller's access privileges and lookup context. A bootstrap does not automatically have "unlimited" privileges to obtain private methods of any module. When creating a `MethodHandle` from another class or package, visibility and JPMS must be respected. If `findStatic` cannot find the signature, a `NoSuchMethodException` may occur; if not permitted, an `IllegalAccessException` may occur.

A bootstrap method invoked by the JVM for a dynamic site typically receives a `Lookup` bound to the instruction's caller, but it must still adhere to the contract and validate inputs if used to route to application-provided implementations.

## 8. `ConstantCallSite`, `MutableCallSite`, `VolatileCallSite`

Common call-site types:

| Type | Can target be changed after creation? | Key characteristics | When appropriate |
| --- | --- | --- | --- |
| `ConstantCallSite` | **No** | Stable target; the JVM can optimize aggressively based on this immutability | Lambda/string-concat factory or fixed links when appropriate |
| `MutableCallSite` | **Yes** | Target can change, but propagation across threads must follow semantics/`syncAll` | Dynamic language runtime, inline cache, or active relinking |
| `VolatileCallSite` | **Yes** | Reads/writes target with volatile semantics so target changes are observed per the class contract | Need update visibility across threads without using a `syncAll`-style mechanism |

**Invariant rule:** Once a `CallSite` exists, **the new target's type must equal the old target's type**. You can swap the method/adapter being called, but **cannot** change a `(String)String` site into `(int)int` just with `setTarget`.

### 8.1. Complete example: changing the target of a `MutableCallSite`

Create **`MutableCallSiteDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;

public class MutableCallSiteDemo {
    private static String oldVersion(String text) {
        return "old:" + text;
    }

    private static String newVersion(String text) {
        return "new:" + text;
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType type =
                MethodType.methodType(String.class, String.class);
        MethodHandle oldTarget = lookup.findStatic(
                MutableCallSiteDemo.class, "oldVersion", type);
        MethodHandle newTarget = lookup.findStatic(
                MutableCallSiteDemo.class, "newVersion", type);

        MutableCallSite site = new MutableCallSite(oldTarget);
        MethodHandle invoker = site.dynamicInvoker();

        String before = (String) invoker.invokeExact("Ada");
        System.out.println("before: " + before);

        site.setTarget(newTarget);
        MutableCallSite.syncAll(new MutableCallSite[] {site});

        String after = (String) invoker.invokeExact("Ada");
        System.out.println("after: " + after);
        System.out.println("site type: " + site.type());
    }
}
```

Run:

```bash
javac --release 17 MutableCallSiteDemo.java
java MutableCallSiteDemo
```

Verified stdout:

```text
before: old:Ada
after: new:Ada
site type: (String)String
```

Explanation:

1. `oldTarget` and `newTarget` both have `MethodType (String)String`.
2. `site.dynamicInvoker()` lets the call point to the site's **current target**.
3. On the first call with `"Ada"`, the old target returns `"old:Ada"`.
4. `site.setTarget(newTarget)` changes the target. `MutableCallSite.syncAll(...)` is used to synchronize publication of this change per the class contract in multi-threaded scenarios.
5. The subsequent call returns `"new:Ada"`, while `site.type()` **does not change**.

**Similar to the previous example:** this program uses `MutableCallSite` directly via the Java API, **not generating `invokedynamic` bytecode itself**. When a real `invokedynamic` instruction is linked to a `MutableCallSite`, changing the target affects subsequent executions according to that call site's semantics.

### 8.2. What does `MutableCallSite.syncAll` mean?

`MutableCallSite` does not guarantee that every thread sees a target change immediately in a volatile manner. `syncAll` is the API used to provide synchronization effects appropriate for target updates that have been performed. `VolatileCallSite` has a different visibility contract (volatile semantics). If building a multi-threaded dynamic language runtime, lacking publication rules can cause a thread to continue seeing the old target.

Do not use `MutableCallSite` just to "swap methods arbitrarily" while ignoring synchronization semantics; also do not switch targets across different `MethodType`s.

## 9. Lambdas and method references: an `invokedynamic` example distinct from dynamic invocation

Java 8 introduced lambdas. How the compiler creates classes/objects for lambdas is an implementation detail. The JVM provides the `invokedynamic` mechanism, which `LambdaMetafactory` can use to link a **factory call site**.

Example:

```java
@FunctionalInterface
interface Formatter {
    String format(String s);
}

static String upper(String s) {
    return s.toUpperCase(java.util.Locale.ROOT);
}

// Illustrative snippet inside the corresponding class/method:
Formatter a = s -> upper(s);
Formatter b = Example::upper;
String value = a.format("java");
```

This is an **illustrative snippet**: `Example` is the name of the class containing the `upper` method. If placed in a complete program, `Formatter` and the class must be declared with the appropriate syntax.

Here two kinds of calls can occur:

- When creating `Formatter a` or `Formatter b`, the compiler may emit `invokedynamic` to create/obtain the functional interface object. The bootstrap `LambdaMetafactory.metafactory` receives metadata about the SAM method type, implementation method handle, and instantiated type.
- When calling `a.format("java")`, the source accesses the method on the `Formatter` type, which can emit `invokeinterface`. The lambda's execution code eventually calls `upper`.

You should not equate the **lambda-creating factory** with **each lambda invocation**. The lambda factory's dynamic call site and the interface invocation on the lambda object serve different roles, even though they may be in the same program.

### 9.1. Captured and non-captured lambdas

With `s -> s.toUpperCase(...)`, the lambda uses no outer local values; the factory site may need no dynamic capture arguments. With:

```java
String prefix = "Hi ";
Formatter f = s -> prefix + s;
```

the value `prefix` is captured; the lambda-creating call site can receive that value as a **dynamic argument**. The bootstrap method additionally receives **static metadata** about the shape of the functional interface, while the actual `prefix` of each lambda creation does not have to be a bootstrap constant.

Separating these two kinds of data is the key to understanding how `invokedynamic` can combine **behavior linkage** with **runtime data**.

## 10. String concatenation: a call site that is not a fixed-name method call

In Java 9+, the JDK provides `StringConcatFactory`. An expression like:

```java
static String label(int id) {
    return "item-" + id;
}
```

can be emitted by the compiler as a dynamic call site with a descriptor like `(I)Ljava/lang/String;`. The name in the constant pool may be `makeConcatWithConstants`, and the `BootstrapMethods` attribute indicates a bootstrap method handle to `java.lang.invoke.StringConcatFactory`.

Why is this useful?

- The compiler can present the **shape of the concatenation** and static constants to the bootstrap, instead of having to know a single optimal sequence of append instructions at compile time.
- The runtime can choose an optimal implementation for the target JDK, argument types, and recipe.
- When concatenating multiple times with different data, the already-linked call site can still handle many dynamic values.
- This is an implementation detail **subject to change** by the compiler/runtime; applications should not rely on the factory name or how the `String` is constructed to interpret the business semantics of the `+` operator.

### 10.1. Do not take `StringConcatFactory` as proof of dynamic language dispatch

Although `invokedynamic` is broadly designed for many languages running on the JVM, string concat is a Java feature with very clear semantics under the JLS. In this case the bootstrap does not "look up a method by name from the user"; it creates a target for a string concatenation operation whose signature and constants are supplied by the compiler.

The takeaway is **the generality of call-site linkage**, not an assumption that `invokedynamic` always selects a method by name on every call.

## 11. `invokedynamic` vs calling `MethodHandle.invokeExact`

Two related concepts that do not overlap:

| Aspect | `MethodHandle.invokeExact(...)` in Java source | JVM instruction `invokedynamic` |
| --- | --- | --- |
| Starting point | Java source calls a special method on a `MethodHandle` object | Bytecode contains a dynamic call-site specifier |
| How target is known | Caller already holds a `MethodHandle` object and uses that type | JVM resolves the bootstrap to a `CallSite` and obtains the target |
| When target is chosen | Program created/obtained the handle before the call | Bootstrap decides the target during call-site linking |
| Signature check | Call-site descriptor of `invokeExact` must equal `handle.type()` | `CallSite.type()` must equal the descriptor of `invokedynamic` |
| Needs `BootstrapMethods`? | No, if only calling a handle directly | Has bootstrap information for the corresponding call-site specifier |
| Can perform target invocation? | Yes, it is a way to invoke a `MethodHandle` | Invocation semantics of the dynamic instruction use the target `MethodHandle` per the linked type |

A snippet:

```java
MethodHandle h = MethodHandles.lookup().findStatic(
        SomeClass.class, "work",
        MethodType.methodType(int.class, int.class));
int x = (int) h.invokeExact(7);
```

is an **illustrative snippet** and requires `SomeClass.work(int)`, imports, and checked exception handling. It shows the caller holding a handle and invoking with the exact type. There is **no** basis to say the compiler must emit an `invokedynamic` at the line `h.invokeExact(7)`. This is a special signature of `MethodHandle`, whereas `invokedynamic` is a different opcode.

In regular Java source there is also **no** syntax `invokedynamic methodName(...)` to force the compiler to emit a dynamic instruction with an arbitrary bootstrap. To test a **real** custom bootstrap, you need a compiler/bytecode generation tool that supports creating constant-pool `InvokeDynamic` and `BootstrapMethods` entries.

## 12. Error handling: wrong linkage differs from target execution error

When reading a stack trace, you must know whether the error occurred **during linking** or **after linking when invoking the target**.

| Error / symptom | Typical phase | Meaning / what to check |
| --- | --- | --- |
| `BootstrapMethodError` | Linkage/resolution | The bootstrap or its arguments could not be resolved; the bootstrap did not return a valid `CallSite`; the target type did not match the call-site descriptor; or a bootstrap failure per JVMS |
| `NoSuchMethodException` at `Lookup.findStatic` | Inside bootstrap code | Could not find a method with the exact name/kind/type requested by the bootstrap; if the bootstrap throws a checked exception when the JVM resolves the site, it is typically wrapped into an appropriate linkage error |
| `IllegalAccessException` at `Lookup.findVirtual/findStatic` | Inside bootstrap code | The lookup context lacks permission to access the target method/class; fix permissions/module or target |
| `WrongMethodTypeException` from a manual `MethodHandle.invokeExact` call | When Java code calls MH | The descriptor at the caller differs from `handle.type()`; **not automatically** an error of an `invokedynamic` |
| `ClassCastException` or `IllegalArgumentException` from target | During target execution | Target/adapter code received invalid data; not by default caused by the bootstrap |
| `NullPointerException` when `invokevirtual`/`invokeinterface` receiver is null | During normal call | Receiver object does not exist; no direct connection to bootstrap |
| `NoSuchMethodError`/`AbstractMethodError`/`IncompatibleClassChangeError` | JVM method resolution/selection/invocation | May relate to binary incompatibility or an invalid method contract; not all such errors are `BootstrapMethodError` |

**Diagnosing `BootstrapMethodError`:** determine whether the error occurred when resolving the bootstrap method handle/static arguments, inside the bootstrap body, or when the JVM checked that the resulting `CallSite` has the right `MethodType`. According to the JVMS, bootstrap-related linkage errors have specific `Error` propagation/wrapping rules; you should not claim that every exception from a bootstrap is wrapped identically. Inspect `getCause()`, the stack trace, and the specific JVM version.

### 12.1. Example of a type mismatch in bootstrap

Suppose the instruction is declared with the descriptor:

```text
(java.lang.String)java.lang.String
```

The bootstrap returns a `ConstantCallSite` whose target `MethodHandle` has type:

```text
(int)int
```

This is a **linkage error description**, not a standalone Java program. `CallSite.type()` does not match the dynamic instruction's descriptor; the JVM cannot link that site and may throw `BootstrapMethodError`.

Note: Java code directly calling `new ConstantCallSite(target)` with a target of a different type does **not** by itself generate `BootstrapMethodError`. This error is tied to **JVM resolution of a dynamic call site/dynamic constant**, not to any manually constructed `CallSite` object.

### 12.2. Target throws an error after linking

If the bootstrap has returned a valid call site but the target method throws `IllegalStateException` when given bad input, that exception is a **target runtime error**. The JVM does not automatically re-invoke the bootstrap or turn every target runtime error into `BootstrapMethodError`.

Similarly, replacing a `MutableCallSite` with a new target of the same signature does not mean eliminating all target bugs. The linking contract guarantees **type shape**, not that the target will always succeed in business logic.

## 13. Performance and optimization: there is no absolute "faster"

An important purpose of `invokedynamic` is to give the runtime/compiler a flexible mechanism to build and link targets at each site, **not** to guarantee it is faster than `invokevirtual`/`invokeinterface` in every workload.

A `ConstantCallSite` with a stable target gives the JVM/JIT opportunities to optimize. A `MutableCallSite` that changes its target frequently can invalidate optimization assumptions and incur synchronization/re-optimization costs. Conversely, `invokevirtual`/`invokeinterface` are optimized very well by the JIT with type profile information, devirtualization, and inlining when appropriate.

When evaluating:

- Measure **linkage/bootstrap** cost separately from the cost of **linked executions**. An expensive bootstrap does not mean every execution is equally expensive.
- Check whether the site has a stable type/target; the number of receiver types and target volatility affect optimization capability.
- Use a standard benchmark such as JMH when there are performance questions; avoid drawing conclusions from a single `System.nanoTime()` without warm-up and controlled JVM flags.
- Do not add `invokedynamic` via bytecode tooling just because the opcode name sounds "dynamic" and you think it will automatically optimize better.

**Correct semantics first, benchmark second.** Most Java applications should write clear Java source and let the compiler/JVM choose the appropriate techniques.

## 14. Security and module boundaries

`invokedynamic` does not open unlimited access:

1. The bootstrap method handle must be resolvable under JVM rules. If the name, type, access, or static args are invalid, the site cannot link properly.
2. The `Lookup` passed to the bootstrap has context/privileges associated with the **caller of the dynamic instruction**, but it does not allow arbitrary access to every private member from another module.
3. When the bootstrap uses `findStatic`, `findVirtual`, `privateLookupIn`, those APIs are still subject to language access and JPMS.
4. A validly created `MethodHandle` is a **capability**: if the runtime exposes a handle to untrusted code, you must consider what privileges the target can exercise.
5. A compiler/bytecode generator receiving untrusted input could produce bootstrap arguments or call-site names that cause errors, unexpected class initialization, or dangerous calls. You must restrict allowed link targets and validate inputs.

For example, a dynamic language building its own method-call cache can choose a bootstrap based on the receiver's class on the **first call** and build an appropriate adapter; however, that design must have an invalidation/relink strategy and protect access rights. The `invokedynamic` opcode **does not automatically cache by receiver** unless the bootstrap programs that behavior.

## 15. Practical `invokedynamic` debugging workflow

When a program has a complex stack trace or a lambda/string concat unexpectedly fails when upgrading to a new JDK:

### Step 1 — Identify the actual class file

Obtain the `.class` file built with the exact JDK/compiler/flags of the failing environment. If running from a JAR, use that exact artifact; do not rely on newer undeployed source.

### Step 2 — Inspect instructions and constant pool

```bash
javap -c -p InvokeDynamicContrastDemo
javap -v InvokeDynamicContrastDemo
```

Read:

- Is there `invokevirtual`, `invokeinterface`, or `invokedynamic` in the method under inspection?
- Which constant-pool index does `invokedynamic` reference, and what is its **NameAndType**?
- Which bootstrap method handle does `BootstrapMethods` at that index point to?
- What static bootstrap arguments are there? For example, method type, implementation handle, recipe.

Do not guess solely from the method name shown after `#` in the disassembly. You must trace **instruction → constant pool → BootstrapMethods**.

### Step 3 — Check the type contract

- What parameter and return types does the dynamic site descriptor have?
- Does the bootstrap return a `CallSite.type()` equivalent to that descriptor?
- If the bootstrap builds a `MethodHandle` from lookup and then applies `asType`/adapters, what is the final type before wrapping in `CallSite`?
- For `MutableCallSite`, does the new target have the **same type** as the old target?

### Step 4 — Distinguish linkage error from target logic

If it is a `BootstrapMethodError`, read the cause chain and bootstrap location. If the error occurs after linkage from target code, investigate the target method and runtime data.

For `invokevirtual`/`invokeinterface`, check the actual receiver, method overriding/default implementations, class loader mismatch, and binary compatibility. Do not look for `BootstrapMethods` for a regular call that does not use `invokedynamic`.

### Step 5 — Check runtime target changes

If the site is mutable/volatile, verify the `setTarget` path, `syncAll` when using `MutableCallSite`, and whether threads observe the target according to contract. For `ConstantCallSite`, the target does not change; look for another cause instead of assuming "the bootstrap is re-invoked every time".

### Step 6 — Diagnose compatibility when upgrading the JVM

Check the target classfile version, JDK runtime, bytecode generation tools, JPMS permissions, and compatibility of frameworks/lambda metafactory/custom bootstraps. A `BootstrapMethodError` after an upgrade may come from a bytecode generator or invalid signatures, rather than something to fix by default with `--add-opens`.

## 16. Misconceptions to avoid

**Misconception 1 — "`invokevirtual` and `invokeinterface` are static dispatch."**

Wrong. Both have runtime method selection based on the receiver, which is the foundation of JVM polymorphism.

**Misconception 2 — "`invokedynamic` calls the method name written in the opcode just like `invokevirtual`."**

Wrong. It references a call-site specifier with a bootstrap; the call-site name is interpreted by the bootstrap, and the target method handle is decided through linking.

**Misconception 3 — "The bootstrap is called on every dynamic invocation."**

Wrong after the site has been successfully linked. The JVM uses the linked `CallSite`; the target can change for sites that allow relinking. However, do not claim that the bootstrap body always executes exactly once in every concurrent resolution scenario.

**Misconception 4 — "Every `invokedynamic` has a mutable target."**

Wrong. `ConstantCallSite` does not allow changing the target; only mutable/volatile sites have target-changing semantics.

**Misconception 5 — "Lambdas use `invokedynamic`, so calling `lambda.apply(...)` must also be `invokedynamic`."**

Wrong. The lambda-creating factory may use `invokedynamic`, but invocation of the functional interface method is typically `invokeinterface`.

**Misconception 6 — "`MethodHandle.invokeExact` and `invokedynamic` are the same opcode."**

Wrong. One is a signature-polymorphic API invoking an existing handle; the other is a bytecode instruction linking a call site via a bootstrap.

**Misconception 7 — "Calling a bootstrap in regular Java proves custom `invokedynamic` works."**

Wrong. Simulating `CallSite` creation only tests bootstrap/handle code; a real instruction requires creating the proper class-file entry and call-site specifier.

**Misconception 8 — "`StringConcatFactory` only runs for string concatenation in dynamic languages."**

Wrong. The Java compiler uses it for string concatenation in Java, depending on compiler strategy and target runtime.

**Misconception 9 — "A bootstrap has a `Lookup` so it can bypass all private/module restrictions."**

Wrong. `Lookup` has scope and access privileges under JVM/JPMS rules; private access to another named module can be restricted.

**Misconception 10 — "Changing `MutableCallSite` to a different signature will make the JVM adapt automatically."**

Wrong. `CallSite.type()` is immutable. The new target must have the same `MethodType`; if conversion is needed, a **compatible** adapter must be built before setting it.

**Misconception 11 — "Any exception from an indy target is a `BootstrapMethodError`."**

Wrong. Bootstrap errors belong to linkage; target business-logic errors after linkage do not automatically become bootstrap errors.

**Misconception 12 — "`invokedynamic` is always faster than virtual dispatch."**

Wrong. The JIT optimizes virtual/interface calls very well; indy performance depends on call-site stability, target shape, linking cost, and workload.

## 17. Self-check exercises and answers

**Question 1.** Why is `Animal a = new Dog(); a.sound();` still considered a dynamic call if the bytecode is `invokevirtual`?

**Answer:** Because the implementation is selected based on the receiver's actual class (`Dog`) at runtime, according to virtual dispatch rules. "Dynamic" here is **receiver-based dispatch**, different from the bootstrap-defined call-site linkage mechanism of `invokedynamic`.

**Question 2.** `Formatter f = s -> s.toUpperCase(); f.format("hi");`: where might `invokedynamic` and `invokeinterface` appear?

**Answer:** When creating the lambda object, the compiler may use `invokedynamic` with `LambdaMetafactory`. When calling `f.format("hi")` via the `Formatter` type, the bytecode may use `invokeinterface`. The two instructions solve two different tasks.

**Question 3.** An `InvokeDynamic` entry has a bootstrap index and a NameAndType. Does it point directly to the implementation method?

**Answer:** No. It describes the **call site** and how to find the bootstrap, while the bootstrap decides which `CallSite`/target `MethodHandle` to link.

**Question 4.** What three standard arguments does a bootstrap receive, and what is the role of `MethodType`?

**Answer:** `MethodHandles.Lookup caller`, `String name`, `MethodType type`; optional static bootstrap args may follow. `MethodType` is the parameter and return types contract that the `CallSite`'s target must match.

**Question 5.** How do `ConstantCallSite` and `MutableCallSite` differ when you want to change the implementation?

**Answer:** A Constant target does not change; a Mutable target can be updated via `setTarget` to switch to another `MethodHandle` of the **same type**, and `syncAll` must be considered when coordinating across multiple threads.

**Question 6.** A bytecode site `(String)String` receives a `CallSite` with target `(int)int`. What is wrong?

**Answer:** `CallSite.type()` does not equal the descriptor of the `invokedynamic` site, so linkage fails (typically `BootstrapMethodError`), rather than normal runtime polymorphic dispatch.

**Question 7.** Why can `"id=" + number` use `invokedynamic`?

**Answer:** The compiler can use `StringConcatFactory` as the bootstrap to create a string concatenation target according to a recipe, with `number` as a dynamic argument on each execution. Concatenating two literals may undergo constant folding and thus not necessarily have indy.

**Question 8.** A bootstrap method has a side effect that increments a counter. Can you assert it increments exactly once per dynamic instruction?

**Answer:** Not in all cases. Concurrent resolution can trigger the bootstrap multiple times and the JVM chooses only one call-site result. Do not rely on unsynchronized side effects in a bootstrap.

**Question 9.** Does `MethodHandle h = lookup.findStatic(...); h.invokeExact(...);` automatically create a `BootstrapMethods` entry?

**Answer:** Not merely from calling `invokeExact`. That is a direct `MethodHandle` invocation. For a custom `invokedynamic` instruction, the bytecode must contain the corresponding call-site specifier and bootstrap metadata.

**Question 10.** After a site links successfully, the target method throws `IllegalStateException`. Is this a `BootstrapMethodError`?

**Answer:** Not by default. This is an exception from the target during execution. You need to read the stack trace and actual cause rather than concluding it is a linkage error.

**Question 11.** Why is `invokeinterface` not a "simpler" `invokedynamic`?

**Answer:** `invokeinterface` applies dispatch based on an interface method reference and receiver according to fixed JVM semantics. `invokedynamic` links its target through a bootstrap-defined call-site mechanism; the difference is **the target selection mechanism**.

**Question 12.** In `javap -v`, what pieces of information need to be combined to understand an `invokedynamic`?

**Answer:** Instruction offset and constant-pool index, the `CONSTANT_InvokeDynamic_info` entry with name/descriptor, the bootstrap method index in `BootstrapMethods`, the bootstrap method handle, and static arguments. Looking only at the name after `InvokeDynamic` is not enough.

## 18. Authoritative references

- **Java Virtual Machine Specification 17, §6.5 — `invokedynamic`, `invokevirtual`, `invokeinterface`:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html — opcode semantics, dispatch, and target invocation mechanisms.
- **JVMS 17, §5.4.3.6 — Dynamically-Computed Constant and Call Site Resolution:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3.6 — bootstrap resolution, `CallSite` linking, concurrent resolution, and errors.
- **JVMS 17, §4.4.10 / §4.7.23:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html — `CONSTANT_InvokeDynamic_info` and the `BootstrapMethods` attribute.
- **Java SE 17, `CallSite` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html — target `MethodHandle` and the three `CallSite` types.
- **Java SE 17, `ConstantCallSite` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/ConstantCallSite.html — immutable target.
- **Java SE 17, `MutableCallSite` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html — relinking and `syncAll`.
- **Java SE 17, `VolatileCallSite` API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html — visibility under volatile semantics.
- **Java SE 17, `MethodHandle` and `MethodType`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html ; https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html .
- **Java SE 17, `LambdaMetafactory`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html — linkage of lambdas/metafactory.
- **Java SE 17, `StringConcatFactory`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/StringConcatFactory.html — bootstrap for string concatenation.
- **JEP 292 and JSR 292:** https://openjdk.org/jeps/292 ; https://jcp.org/en/jsr/detail?id=292 — Method Handles and `invokedynamic` in JVM evolution.

**Conclusion:** `invokevirtual` and `invokeinterface` are already mechanisms for **dynamic method dispatch via the receiver**. `invokedynamic` adds the ability to **define how a call site is linked via a bootstrap**; after linking, the call site executes a target `MethodHandle` with an exact signature. Treat the instruction, call-site specifier, bootstrap metadata, and target type as **four related but distinct layers of information**, rather than treating every instruction with the word "dynamic" as the same mechanism.
