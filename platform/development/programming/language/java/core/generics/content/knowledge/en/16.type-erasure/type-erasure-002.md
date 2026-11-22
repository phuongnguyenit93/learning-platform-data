# Erasing Unbounded Generic Type Parameters to `Object` in Java

## Learning objectives

This lesson focuses on **type erasure** for an **unbounded** generic type parameter such as `<T>`. After studying it, you can:

- Explain why `T` without `extends ...` is erased to `java.lang.Object` in the bytecode form of fields, method parameters, and return types that directly use `T`.
- Distinguish **compile-time** type checking from types in a **JVM method descriptor**.
- Find evidence with `javap` and reflection, including why reflection can still read the symbol `T` from metadata.
- Explain where the compiler inserts casts when retrieving a generic value; recognize the risk of `ClassCastException` when type safety is broken.
- Identify typical limitations caused by type erasure and avoid misconceptions about `List<String>` versus `List<Integer>`.

## 1. From generics in source code to the running program

Consider a generic class:

```java
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` is a **type parameter** declared by the `Box` class. In `Box<T>`, `T` has no explicit bound: there is no `T extends Number`, `T extends Comparable<T>`, or similar interface.

In source code, a user can declare:

```java
Box<String> name = new Box<>("Lan");
String value = name.get();
```

The compiler confirms that `name.get()` has expression type `String` and forbids, for instance, `name` from accepting an `Integer` object via a `set(T)` method if such a method is declared.

However, the `String` information of `Box<String>` does not create a separate JVM class named `Box<String>`. Java generics use **type erasure**: the compiler represents positions using type parameters with types that can exist in a JVM descriptor, while inserting necessary checks/casts to preserve semantics on the caller side.

The core rule of this lesson:

> When erasing an unbounded type parameter such as `T`, the replacement type used is **`Object`**.

This describes **how type declarations/references are compiled**, not an action that converts a `String` object into a new `Object` instance. The string `"Lan"` is still genuinely a `String` object at runtime.

## 2. `<T>` and `<T extends Object>`

The two forms below have the same effective upper bound for `T`:

```java
class Unbounded<T> {
    T value;
}

class ExplicitObject<T extends Object> {
    T value;
}
```

By the type erasure rules:

| Position using `T` | Source code | Erased type in descriptor |
| --- | --- | --- |
| Field | `T value` | `java.lang.Object value` |
| Parameter | `void set(T value)` | `void set(Object value)` |
| Return value | `T get()` | `Object get()` |
| Generic method | `static <T> T echo(T x)` | `Object echo(Object x)` |
| Value inside `List<T>` | `List<T> items` | The parameter itself is `java.util.List` (type argument `T` is erased) |

Notice the last case: the entire `List<T>` parameter becomes the descriptor for **`List`**, not an `Object` descriptor; `T` in the type argument position itself is erased from the descriptor. When `T` appears directly as a parameter or return type, that position is replaced with `Object`.

For rule-level comparison: if you declare `<T extends Number>`, the erasure of `T` is `Number`, no longer `Object`. With multiple bounds such as `<T extends Runnable & AutoCloseable>`, the erasure of `T` is based on the **first bound**, `Runnable`. This lesson focuses on the unbounded `<T>` case.

## 3. A runnable Java 17 example with reflection evidence

Create the exact file `ErasureDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.List;

public final class ErasureDemo {
    static final class Box<T> {
        private T value;

        Box(T value) { this.value = value; }

        T get() { return value; }

        void set(T value) { this.value = value; }
    }

    static <T> T echo(T value) {
        return value;
    }

    static <T> T first(List<T> items) {
        return items.get(0);
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Box<String> textBox = new Box<>("Java");
        String text = textBox.get();
        System.out.println("value: " + text.toUpperCase());
        System.out.println("echo: " + echo(123));
        System.out.println("first: " + first(List.of("A", "B")));

        Field field = Box.class.getDeclaredField("value");
        Method method = ErasureDemo.class
                .getDeclaredMethod("echo", Object.class);
        System.out.println("field type: " + field.getType().getTypeName());
        System.out.println("field generic type: "
                + field.getGenericType().getTypeName());
        System.out.println("echo parameter: "
                + method.getParameterTypes()[0].getTypeName());
        System.out.println("echo return: "
                + method.getReturnType().getTypeName());
        System.out.println("echo generic return: "
                + method.getGenericReturnType().getTypeName());
        System.out.println("same class: "
                + textBox.getClass().equals(new Box<>(7).getClass()));
    }
}
```

Compile and run using Java 17 or later, from the directory containing the file:

```bash
javac ErasureDemo.java
java ErasureDemo
```

**Actual verified output:**

```text
value: JAVA
echo: 123
first: A
field type: java.lang.Object
field generic type: T
echo parameter: java.lang.Object
echo return: java.lang.Object
echo generic return: T
same class: true
```

Reading each point:

1. `Box<String>` allows assigning `textBox.get()` to `String` in source code. The JVM knows `Box.get()` returns `Object`; the compiler inserts a `checkcast String` on the caller side.
2. `echo(123)` uses autoboxing from `int` to `Integer`. `T` is validly inferred at compile time, yet the method descriptor of `echo` still uses `Object`.
3. `first(List<T>)` illustrates that the erased parameter type is `List`, while the result `T` is erased to `Object`. Wherever the result is used as a string, a corresponding cast can appear.
4. `field.getType()` and `method.getReturnType()` report the **erased declared type** in the runtime descriptor: `Object`.
5. `getGenericType()` and `getGenericReturnType()` can report **`T`** because the class file still contains generic declaration metadata for reflection.
6. The two expressions `new Box<>("Java")` and `new Box<>(7)` create objects of the **same runtime class `Box`**, so the last line prints `true`.

Note: `Box.class` and `ErasureDemo.class` are valid class literals. There is no separate class literal for `Box<String>` or `Box<Integer>`.

## 4. Verifying with `javap`: inspecting real descriptors

After compiling the file above, run the following commands. Quoting syntax around nested class names depends on your shell: in Bash, use single quotes to prevent `$` from being expanded; in PowerShell, the syntax below is also valid.

```bash
javap -s -p 'ErasureDemo$Box'
javap -s -p ErasureDemo
```

Excerpt **verified with `javap`** (only the relevant members):

```text
final class ErasureDemo$Box<T> {
  private T value;
    descriptor: Ljava/lang/Object;

  ErasureDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V

  T get();
    descriptor: ()Ljava/lang/Object;

  void set(T);
    descriptor: (Ljava/lang/Object;)V
}
```

For `ErasureDemo`:

```text
static <T> T echo(T);
  descriptor: (Ljava/lang/Object;)Ljava/lang/Object;

static <T> T first(java.util.List<T>);
  descriptor: (Ljava/util/List;)Ljava/lang/Object;
```

**How to read descriptors:** `Ljava/lang/Object;` is the reference type `java.lang.Object`; `Ljava/util/List;` is `java.util.List`; `V` is `void`. In a method descriptor, the part between `(` and `)` is the parameter type list; the part after `)` is the return type.

`javap` still prints `T` in the displayed signature in some modes because the declaration's **generic signature** information can be recorded alongside the class file. What governs calls at the JVM level is the erased `descriptor`. Do not confuse the displayed signature `T get()` with the descriptor `()Ljava/lang/Object;`.

To see the compiler-inserted cast, run:

```bash
javap -c -p ErasureDemo
```

In the bytecode of the `main` method, the call to `textBox.get()` has an instruction sequence similar to:

```text
invokevirtual ... Box.get:()Ljava/lang/Object;
checkcast     ... class java/lang/String
astore_2
```

Constant pool indices, bytecode offsets, and class names abbreviated by `javap` may vary by compiler/program structure, but `get` returning `Object` followed by `checkcast String` is the key point to check. This illustrative excerpt comes from the compiled program above.

## 5. Why are developers still protected by type safety?

In Java, generics move type checking into **compile time**. For example:

```java
Box<String> box = new Box<>("OK");
box.set("Java");  // Valid.
// box.set(42);   // Compile-time error: Integer is not compatible with String.
String s = box.get();
```

The `set(T)` signature of `Box<String>` is understood by the compiler as requiring `String` at the call site. Down in bytecode, `set` accepts `Object`, yet correctness is ensured by type-checked Java call sites. Similarly, `get` returns `Object` in its descriptor, while the compiler inserts a cast when the receiving side requires `String`.

An approximate visualization (only **illustrating the compilation model**, not code that the compiler must regenerate as Java source):

```java
final class BoxErased {
    private Object value;

    BoxErased(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }

    void set(Object value) {
        this.value = value;
    }
}

// Simulated at the call site:
// BoxErased box = new BoxErased("Java");
// String s = (String) box.get();
```

In a real program, the compiler does not necessarily create a `BoxErased` class; the example simply makes clear where `T` is replaced with `Object`. The original `Box` class itself is compiled directly with the corresponding descriptors.

Erasing type parameters helps generic APIs interoperate with earlier Java classes and code. However, it is not a guarantee that every data path at runtime is completely safe: a cast can still fail if a call bypasses type checking via raw types or other unsafe operations.

## 6. When raw types break the compiler's assumptions

Here is an **intentionally unsafe** example to observe the limits of erasure:

```java
import java.util.ArrayList;
import java.util.List;

public class UnsafeRawDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List raw = words;              // Raw type: loses the String type argument.
        raw.add(42);                  // Compiler unchecked warning.

        try {
            String first = words.get(0); // Cast to String on read.
            System.out.println(first);
        } catch (ClassCastException ex) {
            System.out.println("Runtime failure: " + ex.getClass().getSimpleName());
        }
    }
}
```

Run with:

```bash
javac -Xlint:unchecked UnsafeRawDemo.java
java UnsafeRawDemo
```

Expected stdout:

```text
Runtime failure: ClassCastException
```

The `javac -Xlint:unchecked` command also emits a compile-time warning for `raw.add(42)`; the exact warning text varies by JDK and is not part of the application's stdout.

What happens: `raw` and `words` reference **the same** `ArrayList`; due to the raw type, the call `add(42)` slips through with a warning. When reading back through `List<String>`, the compiler expects a `String` and emits a cast; the actual object is an `Integer`, so `ClassCastException` is thrown. This error does not prove generics are ineffective: it shows that **ignoring warnings and breaking typing** undermines compile-time guarantees.

In typical projects, avoid raw types, arbitrary unchecked casts, and mixing generic data with unsafe APIs. Do not use `@SuppressWarnings("unchecked")` to hide an issue without proof of safety.

## 7. Direct limitations resulting from erasing `T`

### 7.1. Cannot distinguish type arguments with `instanceof`

Invalid:

```java
// if (value instanceof List<String>) { } // Does not compile.
```

Because the `String` type argument of `List<String>` is not reified into a separate runtime subtype. You can check the portion of the type that still exists:

```java
if (value instanceof List<?>) {
    // Only knows it is a List; cannot guarantee yet
    // that all elements are String.
}
```

The illustrative snippet above assumes `value` is an already declared reference variable, such as `Object value`.

### 7.2. No `T.class` or `new T()`

The following snippet is invalid:

```java
class Factory<T> {
    // Class<T> type = T.class;        // Error.
    // T value = new T();              // Error.
    // T[] items = new T[10];          // Error.
}
```

Since `T` is not reified into a concrete `Class` in the JVM, `T` cannot be used in expressions that require a concrete runtime class as shown above.

If you need to create objects, pass a `Supplier<? extends T>`; if you need a `Class<T>`, pass an explicit token:

```java
static <T> T make(java.util.function.Supplier<? extends T> supplier) {
    return supplier.get();
}

// Example call in a context where the make method exists:
// StringBuilder builder = make(StringBuilder::new);
```

This is an illustrative snippet that needs to be placed inside a class with an appropriate call site.

### 7.3. Cannot overload solely by differing generic arguments

The following two methods cause a **name clash**, because after erasure both have the same parameter form `List`:

```java
// Cannot be declared together in the same class:
void show(List<String> strings) { /* ... */ }
void show(List<Integer> integers) { /* ... */ }
```

Similarly, within the same class, `void receive(Object x)` and `<T> void receive(T x)` have the same erased parameter list `(Object)`, so they cannot be used as two separate overloads.

How to handle this: choose intent-revealing method names (`showStrings`, `showIntegers`), design **one** generic method with appropriate behavior, or pass an explicit strategy/metadata parameter.

### 7.4. Cannot infer concrete `T` from a `Box<T>` instance itself

```java
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(10);
// a.getClass().equals(b.getClass()) == true
```

A `Box<String>` object does not carry a runtime tag recording that it was instantiated with `String` the way a distinct runtime class would. Reflection can read the `Box<T>` **declaration** and generic metadata on fields/methods, but inspecting `a.getClass()` is not enough to infer the concrete type argument `String` at the instantiation site of `a`.

Do not confuse this with `a.get()`: the returned value is still an actual `String` object, and calling `a.get().getClass()` tells you the class of the **currently held value**. That result does not prove the `Box` class preserves the concrete type argument `T` in all cases; a box might be empty or contain `null`.

## 8. Generic signatures do not contradict type erasure

A field declared `T value` in an unbounded `Box<T>` has two valid views:

- **JVM descriptor**: the field has type `Object` (descriptor `Ljava/lang/Object;`).
- **Generic `Signature` metadata**: can still store the type variable name `T` and the class's generic declaration.

Therefore, `Field.getType()` can return `Object.class`, while `Field.getGenericType()` can be a `TypeVariable`. These are not two separate runtime classes for `Box<String>` and `Box<Integer>`, nor do they guarantee knowing the type argument of an arbitrary instance. The final lesson in this chapter explains the `Signature` mechanism in detail; here, what needs to be established is that **the erasure of unbounded `T` is still `Object`**.

## 9. Before/after type erasure comparison: getting the scope right

| Question | Before erasure in source code | After erasure / at runtime |
| --- | --- | --- |
| Can you call `box.set(42)` on `Box<String>`? | Compiler reports an error | JVM only sees descriptor `set(Object)`, but valid programs were checked at compile time |
| What does unbounded `T get()` become? | `T` | Descriptor returns `Object` |
| What does `<T> T echo(T)` become? | Generic method | Descriptor `(Object)Object` |
| `<T> T first(List<T>)`? | Accepts `List<T>`, returns `T` | Descriptor `(List)Object` |
| Is there a separate `Box<String>.class`? | Such class literal syntax is invalid | One shared `Box.class` |
| Is a `String` converted to `Object` when stored in `Box`? | No | No; the object remains a `String` |
| Can you know the declared parameter name is `T`? | Yes | Possible via generic signature / reflection |
| Casting to obtain `String` when `get()` returns erased `Object`? | Compiler treats expression type as `String` | Compiler can insert `checkcast String` |

Do not imagine type erasure as replacing every occurrence of `String` in the program with `Object`. The rule here affects **generic type parameters and positions using generic type parameters**. A variable directly declared `String s` still has descriptor `String` where appropriate; the actual object keeps its real class.

## 10. Self-practice: reading, predicting, and fixing errors

**Exercise 1 — Predicting descriptors.** Given:

```java
static <T> T choose(T x, T y) {
    return x;
}
```

Question: what are the parameters and return type in the descriptor? **Answer:** `(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;`.

**Exercise 2 — Parameter containing `T`.** Given:

```java
static <T> T tail(java.util.List<T> items) {
    return items.get(items.size() - 1);
}
```

Question: what is the descriptor of `tail`? **Answer:** `(Ljava/util/List;)Ljava/lang/Object;`. `List` preserves the container type, while the generic argument `T` is erased from the descriptor.

**Exercise 3 — Does the concrete type disappear from the object?** Given `Box<String> x = new Box<>("Hello");`. What does `x.get().getClass().getName()` tell you? **Answer:** `java.lang.String`, because the actual value is still a string; the result does not indicate a separate runtime class for `Box<String>`.

**Exercise 4 — Reflection.** For an unbounded field `T value`, why does `getType()` report `Object` while `getGenericType()` can report `T`? **Answer:** the erased descriptor and the generic signature metadata reflect two different layers of information.

**Exercise 5 — API design.** You want a generic class to create a new `T`, but `new T()` is invalid. Write a method accepting `Supplier<? extends T>` and calling `get()`. Check why this makes the object-creation decision explicit.

**Exercise 6 — Predicting errors.** Explain why two overloads `show(List<String>)` and `show(List<Integer>)` in the same class are rejected. **Answer:** the same parameter type list `List` after erasure; overloads cannot be distinguished by generic arguments that get erased.

## Key takeaways

**An unbounded generic type parameter `<T>` erases to `Object`.** This appears directly in the bytecode descriptors of fields, parameters, and return values using `T`; for `List<T>`, the descriptor keeps `List` and erases the type argument. Java still checks type compatibility at compile time, can insert casts at usage sites, and preserves generic signatures so reflection can read declarations back. Even though there is no separate `Box<String>` runtime class, objects such as `String` stored inside remain genuine `String` instances.