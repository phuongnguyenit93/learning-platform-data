# Integrated Practice: Observing Type Erasure and Bridge Methods with `javap`

## Lab Objectives

In Java generics, source code sees types like `Store<String>` and `NumberWorker<Integer>`, yet most type-argument information undergoes **type erasure** during compilation. When a subclass overrides a generic method, the specialized method's JVM descriptor can differ from the superclass method's descriptor. The Java compiler then generates a **bridge method** so polymorphic calls keep working.

This lab presents a runnable Java 17 program, then verifies **every claim against `.class` files**, rather than guessing from source code alone. Upon completion, you will be able to:

- Predict the erasure of an unbounded `T` and `T extends Number`.
- Use `javap -p -s` to match JVM descriptors of fields/methods against Java source signatures.
- Use `javap -p -c` to trace bytecode: `checkcast`, `invokevirtual`, `invokespecial`, and `areturn`.
- Use `javap -p -v` to confirm `ACC_BRIDGE` and `ACC_SYNTHETIC` flags on compiler-generated methods.
- Contrast two bridge forms: `set(Object)` casting input and `get():Object` forwarding the return type.
- Distinguish bridges erased to `Object` from bridges using `Number` from an upper bound.
- Use reflection `Method.isBridge()` to verify at runtime and explain when raw types trigger `ClassCastException`.

**Requirements:** Java 17 or later, with `javac`, `java`, and `javap` from the same JDK. No Gradle, Maven, or external libraries needed.

## 1. Predict Before Opening Bytecode

Look at three type relationships in one problem:

```java
class Store<T> {
    public void set(T item) { /* ... */ }
    public T get() { /* ... */ }
}

class StringStore extends Store<String> {
    @Override public void set(String item) { /* ... */ }
    @Override public String get() { /* ... */ }
}

class NumberWorker<T extends Number> {
    public T next(T value) { return value; }
}

class IntegerWorker extends NumberWorker<Integer> {
    @Override public Integer next(Integer value) { return value + 1; }
}
```

This is an **excerpt for signature analysis**; the complete compilable program appears in the next section.

Before running commands, predict:

1. After type erasure, does `Store<T>.set(T)` take `T`, `Object`, or `String`?
2. What type does `Store<T>.get()` return in its JVM descriptor?
3. In `StringStore`, what extra methods must the compiler add to link calls via `Store<String>` to the overriding methods handling `String`?
4. If the `set(Object)` bridge receives an `Integer` at runtime, what happens?
5. For `NumberWorker<T extends Number>`, does the upper bound cause `T`'s erasure to differ from `Object`?

Keep these predictions to compare against `javap` and runtime output. That is the core habit of a lab: **every conclusion must rest on observed evidence**.

## 2. Create a Program Containing All Verification Cases

Create a file named **`ErasureBridgeLab.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

public class ErasureBridgeLab {
    static class Store<T> {
        private T item;

        public void set(T item) {
            this.item = item;
        }

        public T get() {
            return item;
        }
    }

    static final class StringStore extends Store<String> {
        @Override
        public void set(String item) {
            super.set(item.trim());
        }

        @Override
        public String get() {
            return super.get();
        }
    }

    static class NumberWorker<T extends Number> {
        public T next(T value) {
            return value;
        }
    }

    static final class IntegerWorker extends NumberWorker<Integer> {
        @Override
        public Integer next(Integer value) {
            return value + 1;
        }
    }

    static <T> T echo(T item) {
        return item;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Store<String> store = new StringStore();
        store.set("  java  ");
        System.out.println("stored: " + store.get());
        System.out.println("runtime: " + store.getClass().getSimpleName());

        Method concrete = StringStore.class
                .getDeclaredMethod("set", String.class);
        Method bridge = StringStore.class
                .getDeclaredMethod("set", Object.class);
        System.out.println("set(String) bridge: " + concrete.isBridge());
        System.out.println("set(Object) bridge: " + bridge.isBridge());
        System.out.println("set(Object) synthetic: " + bridge.isSynthetic());

        List<String> bridges = Arrays
                .stream(StringStore.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .map(Method::getName)
                .sorted()
                .toList();
        System.out.println("StringStore bridges: " + bridges);

        NumberWorker<Integer> worker = new IntegerWorker();
        System.out.println("bounded: " + worker.next(7));
        System.out.println("echo: " + echo("ok"));

        Store raw = new StringStore();
        try {
            raw.set(123);
        } catch (ClassCastException ex) {
            System.out.println("raw failure: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

The classes `Store`, `StringStore`, `NumberWorker`, and `IntegerWorker` here are **static nested classes**. `javac` emits separate class files for each nested class; binary names have `$` between the enclosing and nested class names. Using a single file lets us reproduce every experiment with one compilation command.

**Intentional design details:**

- `Store<T>` has field `T item`, a method taking `T`, and a method returning `T`: letting us observe erasure in all three positions.
- `StringStore` overrides both `set(String)` and `get():String`: we will observe **two bridges** with distinct behaviors.
- `NumberWorker<T extends Number>` has an upper bound: testing confirms its bridge uses `Number` rather than defaulting to `Object`.
- `echo(T)` is a generic method independent of the generic classes: its descriptor proves type erasure also applies to method-level type parameters.
- The raw `Store` snippet intentionally creates a warning/runtime failure to reveal where compiler type protection is lost.
- Reflection uses `getDeclaredMethod` with exact parameter types, while the bridge list is **sorted by name** so stdout does not depend on `getDeclaredMethods()` order.

## 3. Compile and Run to Verify Runtime Behavior

In the directory containing `ErasureBridgeLab.java`, run:

```bash
javac -Xlint:rawtypes -Xlint:unchecked ErasureBridgeLab.java
java ErasureBridgeLab
```

**Verified stdout on Java 17+**:

```text
stored: java
runtime: StringStore
set(String) bridge: false
set(Object) bridge: true
set(Object) synthetic: true
StringStore bridges: [get, set]
bounded: 8
echo: ok
raw failure: ClassCastException
```

`javac` also emits **two warnings** in this example: one `[rawtypes]` on `Store raw` and one `[unchecked]` on `raw.set(123)`. Those come from the compiler, not from `java ErasureBridgeLab` stdout. The `raw failure` line is printed by the program's `catch` block.

Initial explanation:

- `store` is declared as `Store<String>`, so the compiler only permits calling `set` with `String` through that reference.
- The actual instance was created by `new StringStore()`, so polymorphic dispatch enters the subclass logic and trims whitespace via `trim()`.
- `set(String)` is the author-written method; `set(Object)` is the compiler-generated **bridge**.
- Both `get` and `set` have bridge methods in `StringStore`.
- `IntegerWorker.next(7)` increments `7` to `8`.
- The raw type discards `String` information at the call site; the bridge attempts to cast `Integer` to `String` and throws `ClassCastException`.

**Detail to observe separately:** `runtime: StringStore` reflects the **actual class of the instance**, not the compile-time type `Store<String>`. The same object can be held through a superclass variable.

## 4. Locate the Right Class Files and Run `javap`

After compilation, the generated class files have binary names such as:

```text
ErasureBridgeLab.class
ErasureBridgeLab$Store.class
ErasureBridgeLab$StringStore.class
ErasureBridgeLab$NumberWorker.class
ErasureBridgeLab$IntegerWorker.class
```

Do not just run `javap ErasureBridgeLab` and conclude there are no bridges: generated bridge methods live in the **corresponding subclasses**.

Inspection commands:

```bash
javap -p -s 'ErasureBridgeLab$Store'
javap -p -s 'ErasureBridgeLab$StringStore'
javap -p -s 'ErasureBridgeLab$NumberWorker'
javap -p -s 'ErasureBridgeLab$IntegerWorker'
javap -p -s ErasureBridgeLab
```

Single quotes around class names containing `$` work in both Bash and PowerShell, preventing the shell from expanding `$Store` or `$StringStore` as variables. If running `javap` from another directory, add `-classpath <directory_containing_classes>` and keep the exact binary name.

Three key modes:

| Command | Purpose |
| --- | --- |
| `javap -p -s` | Display all methods/fields and JVM **descriptors** |
| `javap -p -c` | Display bytecode instructions inside method bodies |
| `javap -p -v` | Display access flags, `Signature`, constant pool, and metadata |

`javap -p` includes private members, letting you inspect field `item`. `javap -s` shows exact descriptors; `javap -v` clearly exposes the bridge flags.

## 5. Experiment A — Type Erasure of Unbounded `Store<T>`

Superclass source:

```java
static class Store<T> {
    private T item;
    public void set(T item) { this.item = item; }
    public T get() { return item; }
}
```

This snippet is part of the full program in section 2. `T` has no `extends` clause, so its effective upper bound is `Object`.

Run:

```bash
javap -p -s 'ErasureBridgeLab$Store'
```

**Verified** excerpt:

```text
class ErasureBridgeLab$Store<T> {
  private T item;
    descriptor: Ljava/lang/Object;

  public void set(T);
    descriptor: (Ljava/lang/Object;)V

  public T get();
    descriptor: ()Ljava/lang/Object;
}
```

In JVM descriptors:

- `Ljava/lang/Object;` denotes a reference to `java.lang.Object`.
- The part inside parentheses `(...)` gives the method parameter types.
- `V` is the `void` return type.
- `()Ljava/lang/Object;` means a method taking **no parameters** and returning `Object`.

`javap` still prints `T` on the class/method declaration line because the class file stores **generic `Signature` metadata** for tools and reflection to inspect declared generics. However, the erased descriptor reveals how the JVM represents the method.

Thus, `Store<String>` and `Store<Integer>` do not need separate runtime `Store` classes for `String` or `Integer`. At runtime, instances share the same class, while the Java compiler checks generic type arguments and inserts casts where values are consumed.

**Check question:** `Store<T>.get()` returns `T` in source. When a `Store<String>` variable calls `get()`, the source expression is typed as `String`, yet `get`'s descriptor in the superclass is `()Ljava/lang/Object;`. The compiler inserts `checkcast java/lang/String` where the result is used.

## 6. Experiment B — Observing Two Bridges in `StringStore`

`StringStore` declares:

```java
static final class StringStore extends Store<String> {
    @Override
    public void set(String item) {
        super.set(item.trim());
    }

    @Override
    public String get() {
        return super.get();
    }
}
```

`extends Store<String>` makes the compiler treat the subclass's specialized methods as valid overrides. In bytecode, however, the superclass has `set(Object):void` and `get():Object`, whereas the user-written subclass methods have `set(String):void` and `get():String`.

Run:

```bash
javap -p -s 'ErasureBridgeLab$StringStore'
```

Confirmed descriptors:

```text
public void set(java.lang.String);
  descriptor: (Ljava/lang/String;)V

public java.lang.String get();
  descriptor: ()Ljava/lang/String;

public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;

public void set(java.lang.Object);
  descriptor: (Ljava/lang/Object;)V
```

`set(String)` and `get():String` are the **concrete overrides** written in source. `set(Object)` and `get():Object` are generated by `javac` as bridges so calls targeting the superclass's erased descriptors still dispatch to the concrete overrides.

Comparison table:

| Role | Method in subclass | JVM descriptor |
| --- | --- | --- |
| Override written in source | `set(String)` | `(Ljava/lang/String;)V` |
| **Bridge** | `set(Object)` | `(Ljava/lang/Object;)V` |
| Override written in source | `get():String` | `()Ljava/lang/String;` |
| **Bridge** | `get():Object` | `()Ljava/lang/Object;` |

From a Java source perspective, you cannot declare two methods differing only by return type. In the **class file**, however, the JVM descriptor includes the return type, allowing the compiler to emit bridge `get():Object` alongside `get():String`. Never write bridges by hand; the compiler generates them, and manually writing `set(Object)` alongside `set(String)` in this generic hierarchy usually causes a **name clash**.

## 7. Experiment C — Inspecting Bridge Bodies with `javap -c`

Run:

```bash
javap -p -c 'ErasureBridgeLab$StringStore'
```

Inspect the body of bridge `set(Object)`. Verified bytecode:

```text
public void set(java.lang.Object);
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #8  // class java/lang/String
     5: invokevirtual #25 // Method set:(Ljava/lang/String;)V
     8: return
```

Step-by-step reading:

1. `aload_0` pushes `this` onto the operand stack.
2. `aload_1` pushes the argument received as `Object`.
3. `checkcast String` verifies the argument is a `String` or `null` (for casting); if incompatible, the JVM throws `ClassCastException`.
4. `invokevirtual ... set(String):void` invokes the subclass-written method.
5. `return` exits the bridge.

Pseudocode conveying the idea — **not code to add to the class**:

```java
// Illustrating compiler-generated bridge; do not write manually:
public void set(Object value) {
    set((String) value);
}
```

This exact `checkcast` explains stdout:

```text
raw failure: ClassCastException
```

Raw `Store` calls `set(123)` with an `Integer`; the cast to `String` fails **before entering the body** of `set(String)` to trim the string. With a typed `Store<String>` reference, the compiler rejects `set(123)` directly, catching the mistake far earlier.

### How is the `get():Object` bridge different?

Body from `javap -c`:

```text
public java.lang.Object get();
  Code:
     0: aload_0
     1: invokevirtual #21 // Method get:()Ljava/lang/String;
     4: areturn
```

There is no parameter to cast, so this bridge simply invokes `get():String` and returns the resulting reference as `Object`. A `String` is already an `Object`, requiring no new object allocation.

Notice: the user-written `get():String` **calls** `super.get():Object`; inside the real method's bytecode, the compiler inserts **`checkcast String`** when narrowing the superclass return value to `String`. Do not confuse that `checkcast` inside the real method with the body of bridge `get():Object`.

In the same `javap -c` output, the real method has instructions like:

```text
public java.lang.String get();
  Code:
     0: aload_0
     1: invokespecial #17 // Method ErasureBridgeLab$Store.get:()Ljava/lang/Object;
     4: checkcast     #8  // class java/lang/String
     7: areturn
```

Distinguishing these two is very helpful when reading stack traces or locating cast failures.

## 8. Experiment D — Confirming Bridges via Flags and Reflection

Use verbose mode:

```bash
javap -p -v 'ErasureBridgeLab$StringStore'
```

On the bridge methods, you will see lines matching this verified excerpt:

```text
public java.lang.Object get();
  descriptor: ()Ljava/lang/Object;
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC

public void set(java.lang.Object);
  descriptor: (Ljava/lang/Object;)V
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

The flags:

- **`ACC_BRIDGE`**: the method is a compiler-generated bridge preserving override/type semantics.
- **`ACC_SYNTHETIC`**: the method is compiler-generated rather than an ordinary declaration in user source code.
- **`ACC_PUBLIC`**: in this example, public visibility matching the overridden method.

Not every synthetic method is a bridge. To confirm a method is a bridge, check `ACC_BRIDGE` or the corresponding reflection API.

The Java reflection code in `main` confirms the same thing:

```java
Method concrete = StringStore.class
        .getDeclaredMethod("set", String.class);
Method bridge = StringStore.class
        .getDeclaredMethod("set", Object.class);
System.out.println(concrete.isBridge()); // false
System.out.println(bridge.isBridge());   // true
System.out.println(bridge.isSynthetic()); // true
```

This is an excerpt from `ErasureBridgeLab.java`, not a standalone program. `Class.getDeclaredMethod` matches **parameter types**, so both `set` methods can be looked up individually. Because the `get()` bridge and real `get()` share an empty parameter list and differ only in return type in the class file, iterating `getDeclaredMethods()` and filtering by `Method.isBridge()` is a safer inspection method than assuming `getDeclaredMethod("get")` returns a specific one.

Verified lab output:

```text
set(String) bridge: false
set(Object) bridge: true
set(Object) synthetic: true
StringStore bridges: [get, set]
```

Calling `sorted()` makes the `[get, set]` order deterministic, since Reflection does not guarantee the order returned by `getDeclaredMethods()`.

## 9. Experiment E — A `Number` Bound Changes the Bridge Descriptor

Now inspect the second class pair:

```java
static class NumberWorker<T extends Number> {
    public T next(T value) {
        return value;
    }
}

static final class IntegerWorker extends NumberWorker<Integer> {
    @Override
    public Integer next(Integer value) {
        return value + 1;
    }
}
```

Here `T` has `Number` as its first bound, so `T`'s type erasure is **`Number`**, not `Object`.

Run:

```bash
javap -p -s 'ErasureBridgeLab$NumberWorker'
javap -p -s 'ErasureBridgeLab$IntegerWorker'
```

Key output from `NumberWorker`:

```text
public T next(T);
  descriptor: (Ljava/lang/Number;)Ljava/lang/Number;
```

From `IntegerWorker`:

```text
public java.lang.Integer next(java.lang.Integer);
  descriptor: (Ljava/lang/Integer;)Ljava/lang/Integer;

public java.lang.Number next(java.lang.Number);
  descriptor: (Ljava/lang/Number;)Ljava/lang/Number;
```

`next(Number):Number` is the bridge. Run:

```bash
javap -p -c 'ErasureBridgeLab$IntegerWorker'
```

Verified bridge body:

```text
public java.lang.Number next(java.lang.Number);
  Code:
     0: aload_0
     1: aload_1
     2: checkcast     #8  // class java/lang/Integer
     5: invokevirtual #17 // Method next:(Ljava/lang/Integer;)Ljava/lang/Integer;
     8: areturn
```

Thus, calls through `NumberWorker<Integer>` still target the superclass's erased signature `next(Number):Number`, and the bridge forwards to the subclass's `next(Integer):Integer`. Input `7` is an `Integer`, so the cast succeeds and the method returns `8`.

General rule: for a type variable like `<T extends Number & Comparable<T>>`, `T` erases to its **first bound**, `Number`. Verify each case rather than assuming every generic method erases to `Object`.

## 10. Experiment F — Generic Methods Also Undergo Erasure

The full file also defines:

```java
static <T> T echo(T item) {
    return item;
}
```

This is a **generic method**, not a method depending on a class-level type parameter. Run:

```bash
javap -p -s ErasureBridgeLab
```

Relevant line from verified output:

```text
static <T> T echo(T);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;
```

Because `T` has no explicit upper bound, the JVM descriptor uses `Object` for both input and output. Calling `echo("ok")` is still type-checked and inferred by the Java compiler, producing stdout:

```text
echo: ok
```

This evidence prevents a common misconception: type erasure does not happen only on generic classes like `Store<T>`; it also applies to type parameters declared on methods like `<T> T echo(T)`.

**Distinction:** `echo` does not generate a bridge just because it is generic. Bridges in this lab appear due to **override** relationships whose descriptors must stay connected after erasure.

## 11. Execution Path Diagram of a `set` Call

When writing:

```java
Store<String> store = new StringStore();
store.set("  java  ");
```

The execution flow matching the observed bytecode:

```text
Java source: Store<String>.set("  java  ")
                |
                v
Compiler checks argument is String
                |
                v
JVM call via descriptor Store.set(Object):void
                |
                v
Actual object: StringStore
                |
                v
StringStore.set(Object):void     [BRIDGE]
                |
       checkcast String
                |
                v
StringStore.set(String):void     [SOURCE OVERRIDE]
                |
       String.trim()
                |
                v
Store.set(Object):void          [SUPER IMPLEMENTATION]
                |
                v
Field item stores String object "java"
```

This is a diagram for reading bytecode, not runnable Java syntax. Across compilers and dispatch scenarios, opcodes can vary, yet the lab's evidence establishes two main layers: the bridge method matching the erased descriptor and the specialized override method processing the value.

Similarly, when calling `store.get()`, the JVM targets `Store.get():Object`, dispatches to bridge `StringStore.get():Object`, the bridge invokes `StringStore.get():String`, and the real method invokes `super.get():Object` and casts the result to `String`. Thanks to bridges, source-level polymorphism is not broken by erasure.

## 12. Explaining the Raw Type Case in the Same Lab

Intentional code at the end of `main`:

```java
Store raw = new StringStore();
try {
    raw.set(123);
} catch (ClassCastException ex) {
    System.out.println("raw failure: "
            + ex.getClass().getSimpleName());
}
```

Here `Store` is a **raw type** because it omits `<T>`. In Java source, `raw.set(123)` is permitted with an unchecked warning because the erased signature of `set` takes `Object`. However, the runtime object is still `StringStore`; its `set(Object)` bridge casts the argument to `String`. `Integer` is incompatible, so runtime throws `ClassCastException`.

Two takeaways:

- **Generic type safety** is enforced by the compiler on normal typed calls. Raw types deliberately cross a weakly checked boundary and expose the hazard.
- **A bridge is not an arbitrary type converter.** It only preserves override contracts; its `checkcast` still fails on data violating assumptions.

Do not conclude that "every raw method call throws an exception": if the actual argument is a `String`, the bridge cast succeeds. Whether an error occurs depends on the runtime value passed and the target method's bytecode.

## 13. Quick Command Suite and Self-Verification Table

A reproducible end-to-end sequence:

```bash
# Step 1: Compile with warnings to observe.
javac -Xlint:rawtypes -Xlint:unchecked ErasureBridgeLab.java

# Step 2: Observe output.
java ErasureBridgeLab

# Step 3: Observe erasure on generic class.
javap -p -s 'ErasureBridgeLab$Store'

# Step 4: Count real methods and bridges in subclass.
javap -p -s 'ErasureBridgeLab$StringStore'

# Step 5: Inspect cast and invocation inside bridge.
javap -p -c 'ErasureBridgeLab$StringStore'

# Step 6: Verify bridge/synthetic flags.
javap -p -v 'ErasureBridgeLab$StringStore'

# Step 7: Compare upper bound Number.
javap -p -s 'ErasureBridgeLab$NumberWorker'
javap -p -s 'ErasureBridgeLab$IntegerWorker'

# Step 8: Compare generic method.
javap -p -s ErasureBridgeLab
```

Lines starting with `#` are shell comments in Bash; PowerShell also supports `#` comments. If using Windows `cmd.exe`, run the `javac`/`java`/`javap` commands individually without copying the comment lines into `cmd`.

Claims to verify from the output:

| Claim | Evidence to look for | Expected |
| --- | --- | --- |
| Erasure of `Store<T>` is `Object` | Descriptors of field/set/get | `Object` |
| `StringStore` has a bridge taking `Object` | `javap -s` | `set(Object):void` |
| `StringStore` has a bridge returning `Object` | `javap -s` | `get():Object` |
| Bridge casts parameter on entry | `javap -c` | `checkcast String` |
| Bridges are compiler-generated | `javap -v` | `ACC_BRIDGE, ACC_SYNTHETIC` |
| Reflection detects bridges | `Method.isBridge()` | `true` for `set(Object)` |
| Erasure of `T extends Number` | `NumberWorker.next` | `Number` |
| Subclass bridge with Number bound | `IntegerWorker.next` | `next(Number):Number` |
| Generic method `echo(T)` is erased | Descriptor of `echo` | `(Object)Object` |
| Raw type breaks type safety | `raw.set(123)` | `ClassCastException` |

To mark an item **PASS**, point to the exact descriptor/flag/bytecode line rather than relying solely on the generic signature printed on the top line by `javap`.

## 14. Common Mistakes During the Lab

### Cannot find `ErasureBridgeLab$StringStore`

Common causes are running `javap` in the wrong directory, forgetting to compile first, or the shell expanding `$`. Verify the generated class files, wrap nested class names in single quotes, or pass `-classpath` pointing to the `javac` output directory.

### Running only `javap ErasureBridgeLab` and seeing no bridge methods

Bridges are generated inside the **subclasses** `StringStore` and `IntegerWorker`, not in the enclosing `ErasureBridgeLab` class. Aim `javap` at the specific subclass.

### Thinking `T` in `javap` output means it was not erased

`javap` can read generic `Signature` attributes. Check **`descriptor:`** to see the JVM-level type. For example, `T get()` has descriptor `()Ljava/lang/Object;`.

### Concluding `get():Object` is a regular author-written overload

Bridges are marked `ACC_BRIDGE` and `ACC_SYNTHETIC` and do not appear in source. JVM descriptors include the return type, allowing the compiler to emit bridge `get():Object` alongside `get():String`.

### Assuming every bridge must contain `checkcast`

The `set(Object)` bridge casts its input parameter; the `get():Object` bridge in this example merely delegates to `get():String`. A cast can occur in the **real method** or **call site** rather than in every bridge.

### Confusing `StringStore.get():String` with `StringStore.get():Object`

Both exist in the class file and differ in **return descriptor**. Read the method header at the top of each `javap -c` block before interpreting opcodes.

### Thinking raw types automatically convert `Integer` to `String`

Raw types bypass compile-time checks; the bridge performs a runtime cast check. When types are incompatible, the program throws `ClassCastException` rather than converting values.

### Relying on fixed ordering of `getDeclaredMethods()`

Reflection does not guarantee method order. When comparing output, filter by `isBridge`, normalize names/signatures, and sort deliberately as in the sample program.

### Seeing `Number` and assuming it is wrong because "generics erase to Object"

Erasure replaces a type variable with its **effective upper bound**. For `T extends Number`, descriptors use `Number`; `Object` is the unbounded case (or when the effective upper bound is `Object`).

### Copying bridge pseudocode into Java source

The compiler creates bridges automatically. Manually writing a method with the same erasure as an inherited method causes a name clash. Implement only the typed override and let the compiler handle the bridge.

## 15. Program Modification Exercises and Output Predictions

**Exercise 1 — Remove `@Override` from `StringStore.set(String)`.** Predict whether the bridge disappears when the signature and inheritance remain identical. Then compile and re-inspect with `javap`.

*Guided answer:* `@Override` is a compiler check for override intent. Removing the annotation does not alter the valid override relationship; the required bridges are still generated. Still, keep the annotation to catch signature mistakes early.

**Exercise 2 — Change `NumberWorker<T extends Number>` to `NumberWorker<T>`.** What must change so `IntegerWorker` remains valid? Predict the descriptor of `next(T)` in the superclass and the bridge in the subclass.

*Guided answer:* The new `T` erases to `Object`; if method bodies remain valid, the superclass descriptor becomes `(Object)Object`, and the subclass bridge needs `next(Object):Object`. Run `javap -s` afterward to verify.

**Exercise 3 — Change `StringStore.get()` to return a constant string.** Is the `get():Object` bridge still needed?

*Guided answer:* As long as it still overrides `Store<String>.get()` with return type `String`, the bytecode link with the superclass method returning `Object` remains. Changing the method body does not eliminate the need for a bridge.

**Exercise 4 — List all bridges of `IntegerWorker` via reflection.** Write a snippet like `Arrays.stream(...).filter(Method::isBridge)` and compare with `StringStore`.

*Guided answer:* `IntegerWorker` has one bridge `next(Number):Number` in this example, whereas `StringStore` has bridges `get` and `set`. Count methods on the exact class without mixing inherited methods into `getDeclaredMethods()`.

**Exercise 5 — Classify casts.** In `javap -c`, locate `checkcast` inside `StringStore.get():String` and inside `StringStore.set(Object):void`. Which one is inside a bridge?

*Guided answer:* `set(Object)` is the bridge, casting input from `Object` to `String`. `get():String` is the real method, casting the result from `Store.get():Object` to return `String`.

**Exercise 6 — Test raw type with a compatible value.** Replace `raw.set(123)` with `raw.set("correct")`, compile, and run. How do warnings and exceptions change?

*Guided answer:* The raw/unchecked warnings remain because the reference type is raw; however, the runtime value is `String`, so the bridge's cast succeeds and `ClassCastException` no longer occurs at that call.

**Exercise 7 — Look at generic method `echo`.** Why does `echo("ok")` create no bridge despite having descriptor `(Object)Object`?

*Guided answer:* Generic erasure alone does not make the compiler emit a bridge. Bridges serve override/descriptor relationships that must be linked; here `echo(T)` is a standalone static generic method overriding no superclass generic method.

## 16. Lab Self-Assessment

You have completed the lab when you can:

- Compile `ErasureBridgeLab.java` with `javac`, explain the raw/unchecked warnings, and match the exact stdout.
- Point out `Object` in `Store<T>` descriptors while `javap` still displays generic symbol `T`.
- Prove `StringStore` contains two bridges using **descriptors, bytecode, and flags**, not merely `@Override`.
- Distinguish the `checkcast` in bridge `set(Object)` from the cast inside the real method `get():String`.
- Explain why `IntegerWorker` has a bridge using `Number` instead of `Object`.
- Read `ACC_BRIDGE`, `ACC_SYNTHETIC`, and `Signature` and explain their distinct roles.
- Connect runtime `isBridge()` evidence, raw-type errors, and polymorphic dispatch through the superclass.

**Core outcome:** type erasure turns occurrences of `T` into the appropriate upper bound in JVM descriptors; bridge methods are generated by `javac` to preserve override and polymorphism semantics when a specialized override's descriptor differs from the erased form. `javap -s`, `-c`, `-v`, together with reflection, let you prove both the **bytecode shape** and **runtime behavior** of that mechanism firsthand.