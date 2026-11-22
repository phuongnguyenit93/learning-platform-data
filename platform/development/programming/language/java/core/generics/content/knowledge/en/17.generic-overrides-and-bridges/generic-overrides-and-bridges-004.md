# Comparing Java Code with Bytecode Using `javap`: Generic Overrides and Bridge Methods

## Learning Objectives

This lesson belongs to the topic **Overriding and Bridge Methods** in Java generics. After completing it, you can:

- Read an `@Override` method in Java source and locate the corresponding method in the `.class` file.
- Explain why the compiler can generate a **bridge method** in addition to the methods declared by the programmer.
- Distinguish `Signature` metadata describing generic information from the **JVM descriptor** used to invoke methods.
- Use `javap -s`, `javap -c`, and `javap -v` to inspect descriptors, bytecode, and the `ACC_BRIDGE` and `ACC_SYNTHETIC` flags.
- Trace method call flows accurately through a parent-type variable and predict where `ClassCastException` arises when raw types are misused.
- Recognize bridges caused by erasure, bridges related to covariant return types, and the effect of non-`Object` upper bounds.

All output below is verified against an actually executed Java 17 example. `javap` excerpts keep only relevant lines; bytecode offsets and constant-pool indices may vary across JDKs.

## 1. The Problem: Java Code Says “Override”, Yet Descriptors Differ

Consider two types:

```java
class Processor<T> {
    public T transform(T value) {
        return value;
    }
}

class UppercaseProcessor extends Processor<String> {
    @Override
    public String transform(String value) {
        return value.toUpperCase();
    }
}
```

Viewed from Java source, `UppercaseProcessor` extends `Processor<String>`. After substituting `T = String` for type checking, `transform(String)` in the subclass **overrides** `transform(T)` in the superclass. The `@Override` annotation is accepted by the compiler.

However, `Processor<T>` declares `T` **with no explicit bound**, so type erasure replaces `T` with `Object`. After compilation:

| Declared in | Viewed from Java source | JVM descriptor |
| --- | --- | --- |
| `Processor<T>` | `T transform(T)` | `(Ljava/lang/Object;)Ljava/lang/Object;` |
| `UppercaseProcessor` | `String transform(String)` | `(Ljava/lang/String;)Ljava/lang/String;` |

If the runtime saw only `transform(String)` on the subclass, a call through `Processor<String>` could still reference the erased signature `transform(Object)`, raising the issue of preserving override semantics. `javac` solves this with a **bridge method** having a descriptor compatible with the superclass method. The bridge receives `Object`, casts it to `String`, and delegates to the real `transform(String)` method.

This bridge method **does not appear in source**. It is generated automatically by the compiler into the `.class` file to guarantee polymorphism after type erasure.

## 2. Runnable and Inspectable Java 17 Program

Create the file **`BridgeInspection.java`** with the following program verbatim:

```java
import java.lang.reflect.Method;

public class BridgeInspection {
    static class Processor<T> {
        public T transform(T value) {
            return value;
        }
    }

    static final class UppercaseProcessor extends Processor<String> {
        @Override
        public String transform(String value) {
            return value.toUpperCase();
        }
    }

    static class Provider<T> {
        public T produce() {
            return null;
        }
    }

    static final class StringProvider extends Provider<String> {
        @Override
        public String produce() {
            return "ready";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Processor<String> processor = new UppercaseProcessor();
        System.out.println("generic call: " + processor.transform("java"));

        Method concrete = UppercaseProcessor.class
                .getDeclaredMethod("transform", String.class);
        Method bridge = UppercaseProcessor.class
                .getDeclaredMethod("transform", Object.class);

        System.out.println("concrete: "
                + concrete.getReturnType().getSimpleName()
                + ", bridge=" + concrete.isBridge()
                + ", synthetic=" + concrete.isSynthetic());
        System.out.println("bridge: "
                + bridge.getReturnType().getSimpleName()
                + ", bridge=" + bridge.isBridge()
                + ", synthetic=" + bridge.isSynthetic());

        Provider<String> provider = new StringProvider();
        System.out.println("provider: " + provider.produce());

        Processor raw = new UppercaseProcessor();
        try {
            raw.transform(100);
        } catch (ClassCastException ex) {
            System.out.println("raw call: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

From the directory containing the file, run:

```bash
javac -Xlint:unchecked BridgeInspection.java
java BridgeInspection
```

**Verified stdout:**

```text
generic call: JAVA
concrete: String, bridge=false, synthetic=false
bridge: Object, bridge=true, synthetic=true
provider: ready
raw call: ClassCastException
```

`javac -Xlint:unchecked` also emits a warning for the call `raw.transform(100)` on raw type `Processor` (the warning is compiler output, not part of the application's stdout). The raw call is kept **intentionally** to observe the risk of bypassing type checks. In normal application code, use `Processor<String>` instead of raw `Processor`.

Why are there three lines to note?

- `generic call: JAVA`: when calling through the parent-type reference `Processor<String>`, the program still executes the overridden body in `UppercaseProcessor`.
- Reflection sees **two** methods in the subclass: the programmer-declared method taking `String`, and the compiler-generated bridge method taking `Object`.
- `raw call: ClassCastException`: the raw type lets the call pass source checking with a warning, but the bridge must cast the `Integer` argument to `String`; that cast fails.

## 3. Useful `javap` Commands and How to Read Them

After `javac` succeeds, the program above creates class files for the outer class and nested classes, for example `BridgeInspection$UppercaseProcessor.class`.

Use three inspection levels, each serving a different goal:

```bash
# 1. View method descriptors, including private ones.
javap -p -s 'BridgeInspection$UppercaseProcessor'

# 2. View bytecode instructions in each method body.
javap -p -s -c 'BridgeInspection$UppercaseProcessor'

# 3. View flags, Signature attribute, and class file details.
javap -p -v 'BridgeInspection$UppercaseProcessor'
```

Single quotes around the nested class name are especially helpful on Bash and PowerShell because `$` has special meaning to the shell. On Windows PowerShell, the commands above can also use single quotes as shown. If you saved the files in another directory, pass `-classpath <class-directory>`, or run directly from that directory.

Meaning of the options:

| Option | Primary data | Use when |
| --- | --- | --- |
| `-p` | Displays all members, including private | Avoiding missing generated methods |
| `-s` | Displays JVM descriptors | Determining erasure of parameter and return types |
| `-c` | Disassembles JVM bytecode instructions of methods | Checking `checkcast`, `invokevirtual`, `areturn` |
| `-v` | Full class file details, access flags, constant pool, attributes | Confirming exact `ACC_BRIDGE`, `ACC_SYNTHETIC`, `Signature` |

Running only `javap BridgeInspection` on the outer class may cause you to miss bridges inside nested classes. Point directly to **the class containing the overriding method**: `BridgeInspection$UppercaseProcessor`.

## 4. Direct Comparison for `UppercaseProcessor`: Two Descriptors

Relevant excerpt from the actual output of:

```bash
javap -p -s -c 'BridgeInspection$UppercaseProcessor'
```

```text
public java.lang.String transform(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  Code:
     0: aload_1
     1: invokevirtual #7  // Method java/lang/String.toUpperCase:()Ljava/lang/String;
     4: areturn

public java.lang.Object transform(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #8  // class java/lang/String
     5: invokevirtual #13 // Method transform:(Ljava/lang/String;)Ljava/lang/String;
     8: areturn
```

Numbers `#7`, `#8`, `#13` are constant-pool indices from the test compilation, not fixed values required across all JDKs. Even if a compiler changes constant-pool ordering, what to observe remains the pairs of **descriptor and bytecode**.

Separated into two methods:

**Actual method written by the programmer:**

```java
public String transform(String value) {
    return value.toUpperCase();
}
```

It has JVM descriptor `(Ljava/lang/String;)Ljava/lang/String;`.

**Bridge method generated by the compiler (roughly equivalent pseudocode):**

```java
// PSEUDOCODE: illustrates the compiler generating a bridge in bytecode.
// Do not manually write this method into UppercaseProcessor.
public Object transform(Object value) {
    return transform((String) value);
}
```

The bridge has JVM descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`, which is the erased form of the method in `Processor<T>`. The pseudocode illustrates the semantics of the generated method, not something to copy into the subclass: manually writing `transform(Object)` alongside the generic override causes an erasure/name clash in Java source.

### Reading the bridge's bytecode step by step

1. `aload_0`: pushes `this` onto the operand stack.
2. `aload_1`: pushes the `Object value` parameter onto the stack.
3. `checkcast java/lang/String`: checks whether the received object can be cast to `String`; for an `Integer`, it throws `ClassCastException`.
4. `invokevirtual ... transform(String):String`: calls the specialized method in the subclass (written by the programmer).
5. `areturn`: returns the resulting reference. `String` is also an `Object`, so no new object needs to be created at the return step.

With `Processor<String> p = new UppercaseProcessor(); p.transform("java")`, the call site bytecode may reference the erased descriptor of the superclass. Dispatch selects the corresponding implementation on the subclass object via the bridge, and the bridge delegates to `transform(String)`. Thus, the override semantics promised by Java source are enforced at runtime.

This is the key point: **bridges preserve polymorphism** when the method descriptor used for calling through a superclass does not directly match the descriptor of the specialized method in the subclass.

## 5. Confirming the `ACC_BRIDGE` and `ACC_SYNTHETIC` Flags

Run:

```bash
javap -p -v 'BridgeInspection$UppercaseProcessor'
```

In the verbose output, look for the method with descriptor `(Ljava/lang/Object;)Ljava/lang/Object;`. Verified excerpt:

```text
public java.lang.String transform(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  flags: (0x0001) ACC_PUBLIC

public java.lang.Object transform(java.lang.Object);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

Meaning:

- `ACC_PUBLIC`: the bridge in this example remains public, matching the public overridden superclass method.
- `ACC_BRIDGE`: the class file marks this method as a compiler-generated **bridge** to maintain override/type relationships.
- `ACC_SYNTHETIC`: compiler-generated member; not an ordinary method declared directly by the programmer in source.

Do not infer that every `synthetic` method is a bridge: `synthetic` is a broader concept. For the method here, both flags appear together.

Compilers may choose different bytecode details when generating bridges; to inspect a specific class file, trust the descriptors and flags of that class file itself rather than memorizing the example's bytecode.

## 6. Reflection Verifies Bytecode from a Java Program

In `main` of the complete program, the two methods are retrieved using:

```java
Method concrete = UppercaseProcessor.class
        .getDeclaredMethod("transform", String.class);
Method bridge = UppercaseProcessor.class
        .getDeclaredMethod("transform", Object.class);
```

This is an excerpt from `BridgeInspection.java`; the `java.lang.reflect.Method` import, classes, and `main` method are already in the runnable program in Section 2.

Output confirms:

```text
concrete: String, bridge=false, synthetic=false
bridge: Object, bridge=true, synthetic=true
```

`Class.getDeclaredMethod(name, parameterTypes...)` looks up by name and parameter types; the bridge has an `Object` parameter so it can be retrieved separately from the real method taking `String`. `Method.isBridge()` and `Method.isSynthetic()` reflect the roles of those methods in the class file.

When building reflection tools, serializers, mappers, or frameworks that discover user APIs, you need to know that bridges can appear in `getDeclaredMethods()`. If the goal is to extract user-declared methods for metadata processing, evaluate `isBridge()`/`isSynthetic()` and override relationships appropriately; do not mechanically count all same-named methods as independent APIs. In some cases a framework still **needs** to resolve a bridge back to the real method to find annotations or generic metadata in the right context.

Avoid assuming any order in the array returned by `getDeclaredMethods()`. In the example, we use `getDeclaredMethod` with explicit parameters so the result does not depend on listing order.

## 7. An Important Variant: Parameters Unchanged, Return Type Changed

Bridges do not pertain only to the `transform(T)` scenario. In the same runnable file from Section 2, there is also:

```java
static class Provider<T> {
    public T produce() {
        return null;
    }
}

static final class StringProvider extends Provider<String> {
    @Override
    public String produce() {
        return "ready";
    }
}
```

From Java source, `StringProvider.produce()` overrides the method in `Provider<String>`. The superclass method returns `Object` after erasure; the subclass method returns `String`. Both parameter lists are empty.

Run:

```bash
javap -p -s -c 'BridgeInspection$StringProvider'
```

Two key methods in the actual output:

```text
public java.lang.String produce();
  descriptor: ()Ljava/lang/String;
  Code:
     0: ldc           #7  // String ready
     2: areturn

public java.lang.Object produce();
  descriptor: ()Ljava/lang/Object;
  Code:
     0: aload_0
     1: invokevirtual #9  // Method produce:()Ljava/lang/String;
     4: areturn
```

**Difference from the `transform(Object)` bridge:** `produce()` has no argument requiring `checkcast`. The bridge simply invokes the `String`-returning version and returns it as `Object`.

Remember that JVM method descriptors **include the return type**. The compiler generating a bridge with the same parameter list but a different return-type descriptor is valid at the class-file level. In Java source, you cannot manually declare two overloads differing only in return type:

```java
// Cannot be manually declared in the same Java source class:
// String produce() { ... }
// Object produce() { ... }
```

Bridges can also arise with *covariant return* overrides even without generics. When inspecting with `javap`, draw conclusions from the actual override relationship and descriptors rather than assuming every bridge comes solely from `<T>`.

## 8. How Do Upper Bounds Affect Bridge Descriptors?

For `Processor<T>`, the upper bound of `T` is `Object` because no `extends` clause is declared. If replaced with `<T extends Number>`, the erasure of `T` is `Number`.

Another standalone example, file **`BoundedBridge.java`**:

```java
public class BoundedBridge {
    static class Receiver<T extends Number> {
        public void accept(T value) {
            System.out.println("base: " + value);
        }
    }

    static final class IntegerReceiver extends Receiver<Integer> {
        @Override
        public void accept(Integer value) {
            System.out.println("integer: " + value);
        }
    }

    public static void main(String[] args) {
        Receiver<Integer> receiver = new IntegerReceiver();
        receiver.accept(7);
    }
}
```

Compile/run/inspect:

```bash
javac BoundedBridge.java
java BoundedBridge
javap -p -s 'BoundedBridge$IntegerReceiver'
```

Verified stdout:

```text
integer: 7
```

Actual descriptor excerpt:

```text
public void accept(java.lang.Integer);
  descriptor: (Ljava/lang/Integer;)V

public void accept(java.lang.Number);
  descriptor: (Ljava/lang/Number;)V
```

The `accept(Number)` method is generated as a bridge for the method in `Receiver<T extends Number>`; erasure uses `Number`, **not** `Object`. The bridge converts the `Number` argument to `Integer` before calling the real method. Hence the claim “every generic bridge has an `Object` parameter” is false.

When a type variable has multiple bounds, erasure is based on the leftmost bound. Type erasure applies to **the actual JVM signature being connected by the bridge**; you should not guess the descriptor solely from the value type passed at one call site.

## 9. Bridge and Overload: Do Not Confuse the Concepts

**Override** is the relationship between a subclass method and a superclass/interface method under language rules, including cases after substituting generic type parameters. `@Override` helps the compiler confirm that intent.

**Overload** is multiple methods with the same name but different parameter lists in a permitted scope. For example, `void print(String)` and `void print(Integer)` are ordinary overloads. The compiler does not turn arbitrary overloads into bridges.

**Bridge** is an additional bytecode method generated by the compiler to preserve override semantics when the concrete descriptor differs from the descriptor used through a parent type. A bridge may look like an overload when viewing only `javap -p`, but it carries `ACC_BRIDGE` and performs delegation.

Common mistake example:

```java
class Parent<T> {
    public void handle(T value) {}
}

class Child extends Parent<String> {
    // Invalid if intended as an override of handle(String):
    // public void handle(Object value) {}
}
```

This case is not a way to write a bridge manually; between `handle(Object)` in the subclass and the parent method after type substitution there is an erasure/name clash, and it cannot validly substitute for `handle(String)`.

Correct way:

```java
class Child extends Parent<String> {
    @Override
    public void handle(String value) {
        System.out.println(value);
    }
}
```

These two snippets illustrate independently of the complete programs above; place each class pair in its own file/scope when experimenting.

**Keep `@Override`** to catch wrong names, wrong parameter types, or accidentally creating an overload instead of the intended override early. Generating bridges is the compiler's responsibility; do not add manual bridges to Java source.

## 10. Distinguishing `descriptor`, `Signature`, and Instructions

When using `javap -v`, three kinds of evidence answer different questions:

| What to check | Question | Observed in the example |
| --- | --- | --- |
| **Descriptor** | What types does the JVM accept/return at the binary level? | `transform(Object):Object` or `transform(String):String` |
| **Signature metadata** | How are the class/method declared generically? | `Processor<T>`, `extends Processor<String>` appear in metadata |
| **Code** | What does the method do at runtime? | Bridge casts `Object` to `String` then calls real method |
| **Access flags** | Is the method compiler-generated as a bridge? | `ACC_BRIDGE, ACC_SYNTHETIC` |
| **Reflection** | Can the program identify the bridge method? | `Method.isBridge() == true` |

A `Signature` entry stating the subclass extends `Processor<String>` **does not** eliminate the `Processor.transform(Object):Object` descriptor. Generic metadata describes declarations for tools, whereas bridge methods ensure proper dispatch at the binary level.

Do not equate `Signature` with “a method called at runtime”, and do not equate `checkcast` with allocating a new instance. `checkcast` only verifies whether a reference can be cast to the target type.

## 11. Common Mistakes and Pitfalls When Reading `javap`

**Looking only at source and ignoring bridges.** If a subclass overrides successfully yet superclass and subclass descriptors differ after erasure, check the subclass's class file before concluding the JVM fails to dispatch properly.

**Confusing `synthetic` and `bridge`.** A `synthetic` method is not necessarily a bridge. Use `ACC_BRIDGE` or `Method.isBridge()` to identify bridges accurately.

**Using the wrong nested class name.** For `static class UppercaseProcessor` inside `BridgeInspection`, the class file's binary name is `BridgeInspection$UppercaseProcessor`. Do not run `javap BridgeInspection` alone and expect to find subclass methods not present in the outer class.

**Treating constant-pool numbers as conclusions.** Indices like `#8` and offset `2` are specific to a particular compilation. When explaining, prioritize method names, descriptors, `checkcast`, and `invokevirtual` opcodes.

**Assuming bridges make all raw calls safe.** The `raw.transform(100)` example proves the opposite: a bridge throws `ClassCastException` if the value does not match the specialized type.

**Assuming every same-named method is an author-written overload.** Some methods may be bridges hidden from source. Use `javap -v`, `isBridge()`, and class relationships.

**Rigidly assuming return types do not affect descriptors.** JVM descriptors include return types; for instance, `StringProvider.produce()` has a bridge returning `Object` to match the erased form of the superclass method.

**Manually stripping bridges from bytecode.** Doing so can break dispatch and binary compatibility of the class. Fix source code to respect the override contract and let the compiler generate needed bridges.

## 12. Quick Comparison Workflow on Real Projects

When encountering a puzzling generic `@Override` method:

1. **Read source:** identify the superclass/interface, `T`, bounds of `T`, what type the subclass substitutes for `T`, and the concrete override signature.
2. **Predict erasure:** if `T` is unbounded, use `Object`; if bounded like `T extends Number`, use `Number`. Distinguish parameter types from return types.
3. **Compile with the right Java version:** use `javac`; check `-Xlint:unchecked` warnings if raw types are used.
4. **Inspect `javap -p -s`:** find the descriptor of the source-written method and the additional method matching the erased form.
5. **Inspect `javap -p -c`:** locate `checkcast`, the target method, and how the value is returned.
6. **Inspect `javap -p -v`:** verify the bridge has `ACC_BRIDGE` and `ACC_SYNTHETIC`.
7. **Test through a parent-type reference:** ensure dispatch reaches the override, and inspect an invalid raw-type scenario when demonstrating the risk.
8. **Cross-check reflection:** if a framework inspects method descriptors, check `isBridge()` and consider resolving to the real method.

This sequence takes you from **intent in Java source** to **evidence in bytecode** and back to **runtime behavior**, helping separate misconceptions about generics from bugs in algorithm logic.

## 13. Exercises with Answers

### Exercise 1. Predicting the bridge for `transform`

Given `Processor<T>` and `UppercaseProcessor extends Processor<String>`, does the compiler generate `transform(Object)` in the subclass? What are its descriptor and role?

**Answer:** Yes. `(Ljava/lang/Object;)Ljava/lang/Object;` matches `Processor<T>`'s method after erasure. It receives `Object`, casts to `String`, invokes `transform(String)`, and returns the result as `Object`.

### Exercise 2. Identifying a runtime error

Variable `Processor raw = new UppercaseProcessor();` is used to call `raw.transform(100)`. What error can occur and where?

**Answer:** The compiler emits an unchecked raw-call warning; at runtime the bridge executes `checkcast String` on `Integer` and throws `ClassCastException`. The error happens before the body of `transform(String)` processes any string.

### Exercise 3. Bridge without arguments

For `Provider<T>.produce()` and `StringProvider.produce()`, is `checkcast` needed inside the bridge?

**Answer:** No, because the bridge takes no parameter; it calls `produce():String` and returns the result as `Object`.

### Exercise 4. Changing upper bound

For `Receiver<T extends Number>` and `IntegerReceiver`, does the bridge descriptor accept `Object` or `Number`?

**Answer:** `(Ljava/lang/Number;)V`, because the erasure of `T` is `Number`. The real method accepts `Integer`.

### Exercise 5. Identifying compiler-generated methods

A class has two `transform` entries in `javap`: one has `ACC_PUBLIC`; the other has `ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC`. Can we conclude both were written manually in source?

**Answer:** No. The method with `ACC_BRIDGE` is a bridge method. In this example, the compiler automatically generated that extra method to maintain the override after erasure.

### Exercise 6. Analyzing `@Override`

Why should `@Override` be kept on `String transform(String)` in `UppercaseProcessor`, even though bytecode adds `transform(Object)`?

**Answer:** `@Override` tells the compiler to verify the override relationship at the Java source level; the compiler is what decides how to generate bridges. The programmer writes and maintains the specialized method, not the compiler-generated bridge.

## Key Conclusion to Remember

`javap` reveals the difference between **Java source code**, **erased types in descriptors**, and **bridge methods added to the class file**. When a generic superclass method is overridden by a subclass with a concrete type, `javac` can generate a method flagged `ACC_BRIDGE, ACC_SYNTHETIC` to preserve polymorphism. Compare `-s` to read descriptors, `-c` to trace casting/delegation, and `-v` to confirm flags. Bridges explain why calls through a parent type still reach the right override after type erasure, while also showing why invalid raw types can cause `ClassCastException`.
