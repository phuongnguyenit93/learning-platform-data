# Why Do `Box<String>` and `Box<Integer>` Share the Same Class at Runtime?

## Learning objectives

When learning Java generics, we often see two variables with two different types:

```java
Box<String> words = new Box<>("Java");
Box<Integer> numbers = new Box<>(42);
```

In **source code**, `Box<String>` and `Box<Integer>` are two distinct parameterized types, checked by the compiler under different constraints. However, if both objects are created directly from the `Box` class, the expression `words.getClass() == numbers.getClass()` evaluates to `true`.

This lesson helps you:

- Explain the reason via **type erasure** and the JVM's class-loading mechanism.
- Distinguish **compile-time parameterized types**, the **runtime class of the `Box` object**, the **runtime class of the value inside `Box`**, and **generic metadata**.
- Observe a real runnable Java 17 program, inspect `javap`, and check `java.lang.reflect`.
- Understand why a single runtime class can still prevent `Box<String>` from accepting an `Integer` at compile time.
- Recognize confusing edge cases: subclasses of `Box<String>`, multiple class loaders, `null` values, raw types, and explicitly passed type tokens.

## 1. Framing the problem: one declared class, many parameterized uses

We declare a generic class:

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
```

`T` is a **type parameter** declared in the class definition. `Box<String>` and `Box<Integer>` are two ways of **parameterizing the type** `Box<T>` with different type arguments; they are not two separate Java classes written or generated as `class BoxString` and `class BoxInteger`.

Examples of assignments checked by the compiler:

```java
Box<String> words = new Box<>("Java");
words.set("Generics");       // Valid: String matches T = String.
// words.set(123);          // Compile-time error: int/Integer is not String.

Box<Integer> numbers = new Box<>(42);
numbers.set(100);           // Valid: Integer.
// numbers.set("wrong");    // Compile-time error.
```

Even though type arguments are checked at compile time, Java does not create a separate runtime class for each concrete `T`. This is a key characteristic of how Java implements generics, differing from specializing a class per type parameter in some other languages or models.

Note the distinctions:

| Component | Example | Nature |
| --- | --- | --- |
| Declared generic class | `Box<T>` | One class definition |
| Parameterized type in source code | `Box<String>` | The compiler knows the element of `Box` is `String` |
| Another parameterized type | `Box<Integer>` | The compiler knows the element of `Box` is `Integer` |
| Runtime class of both objects created directly via `new Box<>(...)` | `Box.class` | The same `Class` object within the same class loader context |
| Contained value | `"Java"` and `42` (boxed as `Integer`) | Two objects whose actual types are `String` and `Integer` respectively |

**Sharing the same runtime class does not mean the two variables reference the same object.** `words` and `numbers` still point to two separately allocated `Box` instances, each with its own state.

## 2. The reason: Java generics use type erasure

For an unbounded `class Box<T>`, positions using `T` typically have JVM descriptors of type `Object`, rather than generating `Box$String` or `Box$Integer`:

```java
static class Box<T> {
    private T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}
```

| Member of `Box<T>` | Erased JVM descriptor |
| --- | --- |
| `T value` | `Ljava/lang/Object;` |
| `Box(T)` | `(Ljava/lang/Object;)V` |
| `T get()` | `()Ljava/lang/Object;` |

This is the **mechanism explaining the shared runtime class**. When using `Box<String>` and `Box<Integer>`, the compiler still checks call types and can insert casts on the caller side. Do not think of `Box<String>` as `Box<Object>` in the **source-level type system**. The next section verifies class identity directly with `getClass()`/`Box.class` and `javap`.

## 3. Java 17 program: proving the shared runtime class

Create the file `SameRuntimeClassDemo.java` (all of the following compiles standalone on Java 17+):

```java
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;

public final class SameRuntimeClassDemo {
    static class Box<T> {
        private T value;

        Box(T value) { this.value = value; }
        T get() { return value; }
        void set(T value) { this.value = value; }
    }

    static final class StringBox extends Box<String> {
        StringBox(String value) { super(value); }
    }

    public static void main(String[] args) {
        Box<String> words = new Box<>("Java");
        Box<Integer> numbers = new Box<>(42);

        System.out.println("same class: " + (words.getClass() == numbers.getClass()));
        System.out.println("class equals Box.class: " + (words.getClass() == Box.class));
        System.out.println("runtime name: " + words.getClass().getName());
        System.out.println("actual values: " + words.get().getClass().getSimpleName()
                + ", " + numbers.get().getClass().getSimpleName());
        System.out.println("values: " + words.get().toUpperCase()
                + " / " + (numbers.get() + 1));

        Class<?> clazz = words.getClass();
        TypeVariable<?> parameter = clazz.getTypeParameters()[0];
        System.out.println("declared parameter: " + parameter.getName());
        System.out.println("declared bound: "
                + Arrays.toString(parameter.getBounds()));

        Type superclass = StringBox.class.getGenericSuperclass();
        System.out.println("subclass generic parent: " + superclass.getTypeName());
        System.out.println("subclass shares Box.class: "
                + (new StringBox("X").getClass() == words.getClass()));
    }
}
```

Run from the directory containing the file:

```bash
javac SameRuntimeClassDemo.java
java SameRuntimeClassDemo
```

**Stdout verified with `javac` and `java`:**

```text
same class: true
class equals Box.class: true
runtime name: SameRuntimeClassDemo$Box
actual values: String, Integer
values: JAVA / 43
declared parameter: T
declared bound: [class java.lang.Object]
subclass generic parent: SameRuntimeClassDemo$Box<java.lang.String>
subclass shares Box.class: false
```

Reading and explaining:

1. **`same class: true`**: both objects are direct instances of the runtime class `SameRuntimeClassDemo$Box`. The `==` operator compares two `Class` references; `true` proves both calls obtain the exact same object representing the runtime class.
2. **`class equals Box.class: true`**: `Box.class` is the class literal for the declared class `Box`. There is no `Box<String>.class` dedicated to the `String` type argument.
3. **`runtime name: SameRuntimeClassDemo$Box`**: a static nested class has a binary name containing `$`. The name does not include `<String>` or `<Integer>`.
4. **`actual values: String, Integer`**: sharing the box class does not change the type of object held inside each instance. One box holds `String`, the other holds `Integer`.
5. **`values: JAVA / 43`**: the compiler still enables calling `String.toUpperCase()` and arithmetic on `Integer` according to the types declared via generics.
6. **`declared parameter: T`**: reflection gets the **type parameter name declared on the class**, not the `Box<String>` parameterization of the `words` variable.
7. **`declared bound: [class java.lang.Object]`**: `T` declares no bound, so the corresponding bound is `Object`.
8. **`subclass generic parent: ...Box<java.lang.String>`**: the `StringBox` subclass declares a fixed inheritance relationship `extends Box<String>`, so the subclass's own metadata can describe `String`. This is information **on the subclass declaration**, not evidence that every `Box<String>` instantiation spawns a new runtime class.
9. **`subclass shares Box.class: false`**: `StringBox` is a **genuinely distinct subclass** of `Box`; `StringBox.class != Box.class` is the expected result and does not contradict type erasure rules.

The example leaves `Box` non-`final` solely to allow declaring `StringBox`; that very detail highlights the difference between **parameterization** and **inheritance**.

## 4. Inspecting the class file with `javap`

In the example above, `Box` is a static nested class, so `javac` produces a corresponding file with binary name `SameRuntimeClassDemo$Box`. After compiling, run:

```bash
javap -s -p 'SameRuntimeClassDemo$Box'
```

Wrap the class name in single quotes in Bash or PowerShell to prevent the shell from expanding `$`. Key excerpt **verified with `javap`**:

```text
class SameRuntimeClassDemo$Box<T> {
  private T value;
    descriptor: Ljava/lang/Object;

  SameRuntimeClassDemo$Box(T);
    descriptor: (Ljava/lang/Object;)V

  T get();
    descriptor: ()Ljava/lang/Object;

  void set(T);
    descriptor: (Ljava/lang/Object;)V
}
```

On the left, `javap` can display generic signatures such as `T get()`. On the right, the descriptor the JVM uses for that method is `()Ljava/lang/Object;`. The class file can store **generic `Signature` metadata** alongside the descriptor; this metadata helps tools/reflection display the `T` declaration, yet **does not create a separate runtime variant for each type argument**.

How to read the key parts:

- `Ljava/lang/Object;` represents the reference type `java.lang.Object`.
- `(Ljava/lang/Object;)V` takes one `Object` parameter and returns `void`.
- `()Ljava/lang/Object;` takes no parameters and returns `Object`.

You can also run:

```bash
javap -c -p SameRuntimeClassDemo
```

When `main` calls `words.get()` in a context requiring `String`, the bytecode can include:

```text
invokevirtual ... Box.get:()Ljava/lang/Object;
checkcast     ... class java/lang/String
```

Constant pool indices, offsets, and class name formatting depend on the `javac`/`javap` version; the notable part is that **`get` returns `Object` in its descriptor**, after which the compiler inserts **`checkcast String`** when the concrete type needed is `String`.

Why can a single `Box.class` run for multiple types? Because the JVM does not resolve every type parameter into a new class; it runs `Box`'s erased bytecode, while the compiler is responsible for enforcing generic constraints at call sites.

## 5. Same runtime class, yet still type-safe

If the JVM only sees `set(Object)`, why is `words.set(123)` rejected in source code?

Because the compiler knows the variable `words` is declared as `Box<String>`. Consequently, in the compiler's view, normal operations on that variable correspond to:

- `set(String)` at the source level after substituting `T = String`;
- `String get()` at the source level;
- an `Integer` argument passed to `set` violates the type constraint at **compile time**.

Once bytecode is generated, the JVM executes the erased calls. For example, when assigning the result of `get()` to a `String` variable, the compiler inserts a corresponding cast. Provided the program does not use unsafe data paths, the compile-time guarantee ensures that cast succeeds.

**Incorrect claim:** "since the JVM sees `Object`, the compiler also allows `words.set(new Object())`." Java has two distinct levels: source-level generic type checking and erased types in bytecode.

### Type erasure does not turn `Box<String>` into `Box<Object>`

The following assignment is **invalid**:

```java
Box<String> strings = new Box<>("one");
// Box<Object> objects = strings; // Compile-time error.
```

Java generics are **invariant**: `String` being a subtype of `Object` does not make `Box<String>` a subtype of `Box<Object>`. If that assignment were allowed, callers could insert a non-string `Object` into a box promised to hold only `String`.

When you need a reference to read data from multiple kinds of `Box` without depending on a specific `T`, `Box<?>` can fit:

```java
Box<?> unknown = new Box<>("hello");
Object value = unknown.get();
// unknown.set("another"); // Does not compile: concrete T is unknown.
// unknown.set(null);      // Type-valid; null handling depends on the API.
```

`Box<?>` allows reading values as `Object`, yet the compiler cannot allow writing a non-`null` object when the real type parameter is unknown. This rule still holds even though `Box` variants share the same runtime class.

## 6. What can reflection read — and what can it not read?

Two reflection methods that are easily confused:

```java
Class<?> clazz = words.getClass();
System.out.println(clazz.getTypeParameters()[0].getName()); // T
```

`getTypeParameters()` describes the **type parameters declared in the class definition**. The symbol `T` appears in `class Box<T>` and can be stored in metadata; reflection does not deduce for an individual `words` object that it received `String` at its variable declaration site.

Conversely:

```java
System.out.println(StringBox.class.getGenericSuperclass().getTypeName());
```

can return `SameRuntimeClassDemo$Box<java.lang.String>` because the `StringBox` class itself was compiled from `extends Box<String>`. Metadata of the **inheritance declaration** carries that information.

Three distinct questions:

| Question | Commonly used API | What you get |
| --- | --- | --- |
| Which runtime class is this object an instance of? | `obj.getClass()` | `Class<?>` of the actual runtime class |
| Which type parameter names does the generic class declare? | `Box.class.getTypeParameters()` | `T`, its bounds |
| Which generic superclass does the subclass declare? | `StringBox.class.getGenericSuperclass()` | Can see `Box<String>` from subclass metadata |

**You cannot rely solely on `new Box<String>("X").getClass()` to recover `String` as a runtime argument attached to `Box`'s `Class`.** For `Box<Integer>`, that method returns the exact same `Box.class` within the same class-loading context.

Nor should you try inferring type `T` via `box.get().getClass()`. That only tells you the **type of the object currently inside the box**, which may be absent if the value is `null`, and is not general proof of the `Box<T>` declaration.

## 7. When you genuinely need type information at runtime: pass `Class<T>`

Type erasure does not prevent an application from storing metadata **explicitly**. If an API needs to verify that an externally supplied object has the expected type, accept a **type token** `Class<T>` and store it per instance.

The following `TypeTokenDemo.java` example compiles and runs standalone on Java 17+:

```java
import java.util.Objects;

public final class TypeTokenDemo {
    static final class Box<T> {
        private final Class<T> type;
        private T value;

        Box(Class<T> type, T value) {
            this.type = Objects.requireNonNull(type);
            this.value = type.cast(value);
        }

        Class<T> type() { return type; }
        T get() { return value; }

        void setFromObject(Object candidate) {
            value = type.cast(candidate);
        }
    }

    public static void main(String[] args) {
        Box<String> text = new Box<>(String.class, "Hi");
        Box<Integer> number = new Box<>(Integer.class, 7);

        System.out.println("same Box class: "
                + (text.getClass() == number.getClass()));
        System.out.println("saved tokens: " + text.type().getSimpleName()
                + ", " + number.type().getSimpleName());

        try {
            text.setFromObject(8);
        } catch (ClassCastException ex) {
            System.out.println("rejected: " + ex.getClass().getSimpleName());
        }
    }
}
```

Commands:

```bash
javac TypeTokenDemo.java
java TypeTokenDemo
```

Verified stdout:

```text
same Box class: true
saved tokens: String, Integer
rejected: ClassCastException
```

What changed compared to the first example:

- Instances still belong to the **same class `TypeTokenDemo$Box`**.
- Each object holds a **`type` data field**, passed from `String.class` or `Integer.class`. The difference in tokens belongs to **per-instance state**, not to the JVM reconstructing `Box<T>`'s generic argument on its own.
- `Class.cast` checks the incoming object against the token; when `Box<String>` receives an `Integer` via `setFromObject`, it throws `ClassCastException`.
- `Class<T>` works conveniently for runtime types that have a `Class` token such as `String` or `Integer`. It cannot capture nested arguments of a type like `List<String>` using `List.class` alone; if complex generic types are needed, other type metadata is required (such as an appropriate `Type`/`ParameterizedType`).

You can choose a design that disallows mutating values via `Object` when an application only needs a compile-time type-checked generic API. Type tokens are useful when receiving dynamic data, reflecting, deserializing, or interacting with APIs that do not carry sufficient generic parameters.

## 8. Common consequences

Using `Box<String>` and `Box<Integer>` with the same runtime class leads to several limitations, yet they do not eliminate compile-time type checking:

| Situation | Result on Java 17 | Why |
| --- | --- | --- |
| `obj instanceof Box<?>` | Valid | Only checks the runtime class `Box` |
| `obj instanceof Box<String>` with `obj: Object` | Rejected | Runtime does not know the generic argument `String` |
| `new Box<String>[2]` | Rejected | Component type is not reifiable |
| Two overloads `f(Box<String>)` and `f(Box<Integer>)` | Rejected | Identical erasure |
| Assigning `Box<Integer>` to `Box<String>` | Rejected | Generic type invariance |
| Raw alias / unchecked cast | Warning or runtime risk | Bypasses source-level type guarantees |

`Box<String>` and `Box<Integer>` can still hold **actual value objects of different classes**; `getClass()` of the value inside the box does not make the box's class specialized. If runtime validation is needed, pass a `Class<T>` token as in the second program, while remembering a token does not automatically verify deeply nested type arguments like `List<String>`.

## 9. Three important misconceptions to clear up

**Misconception A — "Same `Box.class` means same object."**

False. Two `new Box<>(...)` calls create two distinct `Box` objects even though they share the same class. Compare:

```java
Box<String> x = new Box<>("A");
Box<String> y = new Box<>("A");
System.out.println(x == y);                    // false
System.out.println(x.getClass() == y.getClass()); // true
```

`==` on `x` and `y` checks **instance identity**. `==` on `getClass()` results checks **Class identity**.

**Misconception B — "Erasing `T` to `Object` means `String` loses its real class."**

False. The `String` object still belongs to `String.class`. The compiler/JVM can use `Object` in the box's erased signatures because every `String` object is also an `Object`. It is the **box's generic argument** information that is omitted from runtime descriptors, not the real class of each referenced object.

**Misconception C — "If reflection prints `Box<String>`, the JVM must have a separate `Box<String>` class."**

False. Reflection reads generic information of a **declaration** (for example, a subclass that literally wrote `extends Box<String>`) because the class file can store `Signature` metadata. It does not assert that there is a specialized runtime class for every `new Box<String>(...)` usage.

**An advanced caveat about class loaders:** the statement "two `Box` objects share the same `Class`" implicitly assumes they were created from the same class definition resolved by the same class-loading context. In the JVM, two different class loaders can define two classes with the same binary name that are two distinct runtime classes. That is a rule about **class identity and class loading**, independent of which generic argument `Box<String>` or `Box<Integer>` chose.

## 10. Practice questions

**Question 1.** Given two variables both created directly with `new Box<>(...)`:

```java
Box<String> a = new Box<>("Hello");
Box<Integer> b = new Box<>(10);
```

Predict `a == b` and `a.getClass() == b.getClass()`.

**Explanation:** in the example, the two variables have directly incompatible source types, so writing `a == b` may be flagged by the compiler as incomparable types. To check instance identity validly in this exercise, cast both sides to `Object` or store them in `Object` first. Then the two instances are distinct so the result is `false`; meanwhile both `getClass()` calls return the same `Box.class`, so `true`.

**Question 2.** Why can `Box<T>.get()` have descriptor `()Ljava/lang/Object;`, while `String text = box.get();` is valid when `box` is `Box<String>`?

**Answer:** type erasure causes the method descriptor to return `Object`; the compiler checks source types and inserts a cast to `String` at the usage site when needed.

**Question 3.** What do `Box<String>` and `Box<Integer>` have in common, and how do they differ?

**Answer:** if both are created directly from the `Box` class, they share the same runtime class; they differ in the parameterized type checked by the compiler and may differ in values, state, and tokens passed to each instance.

**Question 4.** If you declare `class StringBox extends Box<String>` and call `new StringBox("A").getClass()`, does the result equal `new Box<>("A").getClass()`?

**Answer:** no. `StringBox` is a separate subclass with its own runtime class, not a variant auto-generated by passing `String` as a generic argument.

**Question 5.** Why does `Box.class.getTypeParameters()` not return `String` for a variable declared as `Box<String>`?

**Answer:** that API reads the list of type parameters **of the `Box<T>` class declaration**, not the type argument chosen in a specific variable declaration.

**Question 6.** Design `Box<T>` so that the program rejects putting an object of the wrong type into the box when data comes from an `Object` source.

**Hint:** pass an explicit `Class<T>` into the constructor, store it in a field, and use `type.cast(candidate)` at the data-entry boundary. Distinguish the **instance**'s token field from `Box`'s own `Class` object.

## Summarize for yourself with an accurate mental model

- **Source code:** `Box<String>` and `Box<Integer>` are two distinct parameterized types; the compiler protects normal operations on `T` according to the provided type argument.
- **Bytecode:** positions using the unbounded parameter `T` in `Box<T>` have erased type `Object`; the JVM uses the shared `Box` class definition.
- **Objects:** each `new` still allocates a separate instance; the value inside still has its real runtime class such as `String` or `Integer`.
- **Reflection:** you can inspect the runtime class and read declared generic metadata, but `Box.class` does not automatically supply `String` or `Integer` for arbitrary instances.
- **API design:** if runtime logic genuinely needs to know the concrete type, pass a proper token/metadata; do not rely on the box's `getClass()` to infer generic arguments.

Key takeaway: `Box<String>` and `Box<Integer>` **share the same runtime class because Java uses type erasure**, while generic type safety is primarily enforced at compile time.