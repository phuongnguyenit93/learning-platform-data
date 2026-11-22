# Diamond and Type Inference During Object Creation in Java Generics

## 1. What is the diamond `<>`?

When creating an object of a generic class, Java can **infer type arguments** from the context and constructor arguments. The empty angle brackets `<>` are called the **diamond operator**. This syntax was introduced in Java 7; its main purpose is to avoid repeating type arguments when there is already enough information for the compiler to figure them out.

```java
// Explicitly write type arguments on both left and right
List<String> names = new ArrayList<String>();

// Diamond: the compiler infers the type of the new object
List<String> names = new ArrayList<>();
```

The two lines are **equivalent ways of declaring the variable**, so you should pick one when writing an actual program. In the second line, `javac` uses the `List<String>` context to infer that the created object is compatible with `ArrayList<String>`.

Key points to remember:

- The diamond `<>` appears **after the generic class name when creating an object**, such as `new ArrayList<>()`, `new HashMap<>()`, or `new Box<>(value)`.
- `<>` asks the compiler to **infer type arguments**; it does not mean "not using generics", nor does it mean "the element type is always `Object`".
- Diamond **differs from raw types**. `new ArrayList()` omits type arguments and can lose type checking; `new ArrayList<>()` still participates in generic type checking.
- Diamond **differs from the wildcard `<?>`**. `?` describes an unknown type argument in a used type, whereas `<>` requests inference of type arguments to perform object instantiation.

Type arguments are checked primarily at **compile time**. The diamond does not automatically add per-element runtime checks; Java Generics still operates under *type erasure*.

## 2. Relationship between target type and `new` expressions

When an expected type exists at the location containing the `new` expression, the compiler can use that type as the **target type**. Contexts with a target type include assignment, variable initialization, passing arguments to a method, and returning a result from a method.

Most common example:

```java
List<Integer> numbers = new ArrayList<>();
Map<String, Integer> counts = new HashMap<>();
Set<Long> ids = new HashSet<>();
```

These declarations require importing the classes from `java.util`. You can read the first line as follows:

1. The variable on the left requires a `List<Integer>`.
2. The expression on the right creates an `ArrayList<E>` and uses the diamond.
3. The compiler infers `E = Integer` so that the assignment is valid.
4. The caller receives a list to which `Integer` can be added, but an arbitrary `String` cannot.

```java
List<Integer> numbers = new ArrayList<>();
numbers.add(10);
// numbers.add("ten"); // Compile error
```

Diamond reduces syntactic repetition; it does **not** alter the *invariance* rules of Java Generics. Just because `Integer` extends `Number` does not mean `List<Integer>` is a subtype of `List<Number>`.

```java
List<Integer> ints = new ArrayList<>();
// List<Number> nums = ints; // Error: generics are invariant
```

### The target type does not have to be the exact same class as the right-hand side

```java
Collection<String> words = new ArrayList<>();
Iterable<Integer> input = new ArrayList<>();
Map<String, List<Integer>> grouped = new HashMap<>();
```

`ArrayList<E>` implements `Collection<E>` and `Iterable<E>`; `HashMap<K,V>` implements `Map<K,V>`. Diamond uses the expected type information through compatible type relationships, rather than merely copying the exact class name on the left.

## 3. Comparing explicit syntax, diamond, and raw type

| Syntax | Meaning | Type safety |
|---|---|---|
| `new ArrayList<String>()` | Explicitly specifies `E = String` | Yes |
| `new ArrayList<>()` with target `List<String>` | Infers `E = String` from context | Yes |
| `new ArrayList()` | Uses raw `ArrayList`, declaring no type arguments | Skips generic checks on raw operations; may emit `unchecked` warnings |
| `new ArrayList<?>()` | Attempts to use a wildcard as a type argument in object creation | Invalid |
| `new ArrayList` | Missing `()` for the constructor in standard Java | Invalid |

Put these two lines side by side:

```java
List<String> safe = new ArrayList<>();
List<String> unsafe = new ArrayList(); // Unchecked conversion
```

The second line may compile with a warning because the right-hand side is a raw type. With `javac -Xlint:rawtypes,unchecked`, the compiler can point out where type information is lost. An example of raw type risk:

```java
List raw = new ArrayList();
raw.add(42);
List<String> assumedStrings = raw; // Unchecked conversion
// String s = assumedStrings.get(0); // May throw ClassCastException
```

This is **unsafe illustrative code**. With diamond, type parameter inference and checking happen at compile time, so there is no need to open up this risk just to avoid repeating `String`.

## 4. Diamond uses information from the constructor

The compiler does not only look at the target type. It can also use the **arguments passed to the constructor** and the constructor's constraints to infer type arguments.

Example:

```java
ArrayList<String> copy = new ArrayList<>(List.of("Lan", "Minh"));
```

The constructor `ArrayList(Collection<? extends E>)` accepts a collection of elements compatible with `E`. The call `List.of("Lan", "Minh")` provides strings; the target type `ArrayList<String>` also constrains `E` to `String`. This information is consistent.

When the target is a broader type:

```java
List<Number> numbers = new ArrayList<>(List.of(1, 2.5));
```

The compiler solves constraints from **the target type `List<Number>`** and the constructor arguments. The result can be `ArrayList<Number>`, because both `Integer` and `Double` values are assignable to `Number`. That does not make `ArrayList<Integer>` a subtype of `ArrayList<Number>`.

With a custom generic class:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

We can create:

```java
Box<String> a = new Box<>("Java");
Box<Integer> b = new Box<>(21);
```

Here, the constructor accepts `T`, while the target type specifies `T` is `String` or `Integer`. Both constraint sources work together so the compiler selects the appropriate type.

**Note:** The compiler finds a type that satisfies the constraints of the entire expression, rather than simply "reading the text on the left and pasting it into the diamond" in every case. If the constructor, type bounds, or target type conflict, the program may fail to compile.

## 5. When initializing with `var`, the constructor must provide the type information itself

`var` causes the compiler to infer the variable's type from the initializer, so there is no target type like `List<String>` to guide the diamond. The result depends on the constructor signature and arguments:

```java
var mixed = new ArrayList<>();             // ArrayList<Object>.
mixed.add("hello");
mixed.add(123);

var words = new ArrayList<>(List.of("A", "B")); // ArrayList<String>.
// words.add(3); // Error: Integer is not a String.

var fixed = new ArrayList<String>();      // ArrayList<String>.
```

In the first line, the constructor has no arguments constraining E; the default upper bound Object leads to `ArrayList<Object>`. In the second line, the constructor `ArrayList(Collection<? extends E>)` receives a String source, so E is usefully determined even without a left-hand target type. **Subsequent add calls do not cause E to be re-inferred.**

| Declaration | Static type |
| --- | --- |
| `List<String> a = new ArrayList<>()` | `List<String>` |
| `var b = new ArrayList<String>()` | `ArrayList<String>` |
| `var c = new ArrayList<>()` | `ArrayList<Object>` |
| `var d = new ArrayList<>(List.of("x"))` | `ArrayList<String>` |

This is a special branch of **constructor inference with diamond**: look at the constraints right at the `new` expression. If the goal is an empty list of Strings, write `List<String> list = new ArrayList<>()` or `var list = new ArrayList<String>()`.

## 6. Diamond in method invocations

An object creation expression with diamond can appear directly in the **argument position of a method**. When the method requires a specific type, the compiler can use the formal parameter type as the target type.

```java
static void acceptStrings(List<String> input) {
    System.out.println(input.size());
}

static void example() {
    acceptStrings(new ArrayList<>());
}
```

`new ArrayList<>()` is checked in a context requiring `List<String>`; the compiler can infer `E = String`. The fact that the newly created list is empty does not cause the compiler to default to `Object` in this case.

An example with generic parameters:

```java
static <T> void addDefault(List<T> values, T element) {
    values.add(element);
}

static void example() {
    addDefault(new ArrayList<>(), "Java");
}
```

The compiler can infer type `T` so the call is valid, based on information from both the list parameter and the argument `"Java"`. With APIs that have multiple overloads or complex constraints, the inferred type can be less obvious; in such cases, declaring an explicitly typed variable beforehand is easier to read and diagnose.

Do not interpret every `new ArrayList<>()` as `ArrayList<Object>`: it is only inferred that way in **contexts lacking specific constraints**, such as `var list = new ArrayList<>()` with the no-arg constructor.

## 7. Diamond in `return` statements

A method's return type can also provide a target type.

```java
static List<String> emptyNames() {
    return new ArrayList<>();
}
```

The compiler checks `new ArrayList<>()` against the return type `List<String>`. You do not have to write `return new ArrayList<String>();`.

With a generic method:

```java
static <T> List<T> emptyList() {
    return new ArrayList<>();
}
```

Inside the method body, `T` is a named type parameter; the diamond expression is inferred so the result fits `List<T>`. Callers can use:

```java
List<Integer> ints = emptyList();
List<String> texts = emptyList();
```

In the `emptyList` example, inference **at the method call** and inference **at the object creation expression** are two related yet distinct steps:

1. `emptyList()` is a generic method call, which can rely on the target type to determine `T`.
2. `new ArrayList<>()` is inside the method body, checked against the declared return type `List<T>`.

Do not conclude that an `ArrayList` object at runtime retains full information about `T`; generics are still erased.

## 8. Initializing nested generic structures

Diamond is especially helpful when the target type is long and nested:

```java
Map<String, List<Integer>> groups =
        new HashMap<String, List<Integer>>();
```

This can be written concisely:

```java
Map<String, List<Integer>> groups = new HashMap<>();
groups.put("even", new ArrayList<>());
```

In the outer expression, the compiler uses the target type `Map<String, List<Integer>>` to determine `K = String` and `V = List<Integer>`. In the `put` call, the value parameter requires `List<Integer>`, so `new ArrayList<>()` further infers the element type `Integer`.

An example with data:

```java
Map<String, List<Integer>> groups = new HashMap<>();
groups.put("even", new ArrayList<>(List.of(2, 4)));
groups.put("odd", new ArrayList<>(List.of(1, 3)));

// groups.put("wrong", new ArrayList<>(List.of("x"))); // Type mismatch
```

Diamond removes repetitive syntax, yet the compiler still checks **every generic level**. `Map<String, List<Integer>>` does not accept `List<String>` in the value position.

Use clear variable names when many nested generic layers make code hard to read. Diamond reduces boilerplate text; it does not eliminate the need for meaningful type design.

## 9. Complete Java 17 example

Create the file `DiamondInferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DiamondInferenceDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static void printStrings(List<String> input) {
        System.out.println("Argument: " + input);
    }

    static List<String> copyWords(List<String> source) {
        return new ArrayList<>(source);
    }

    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("Lan");
        System.out.println("Names: " + names);

        var scores = new ArrayList<Integer>();
        scores.add(3);
        scores.add(5);
        System.out.println("Scores: " + scores);

        var mixed = new ArrayList<>();
        mixed.add("text");
        mixed.add(42);
        System.out.println("Mixed inference: " + mixed);

        Map<String, List<Integer>> groups = new HashMap<>();
        groups.put("even", new ArrayList<>(List.of(2, 4)));
        System.out.println("Even: " + groups.get("even"));

        Box<String> greeting = new Box<>("Hello");
        var inferredBox = new Box<>("Hi");
        System.out.println("Greeting: " + greeting.get());
        System.out.println("Inferred box: " + inferredBox.get());

        List<String> copied = copyWords(List.of("red", "blue"));
        System.out.println("Copied: " + copied);

        printStrings(new ArrayList<>(List.of("A", "B")));
    }
}
```

Compile with JDK 17 or newer:

```bash
javac DiamondInferenceDemo.java
java DiamondInferenceDemo
```

**Exact stdout:**

```text
Names: [Lan]
Scores: [3, 5]
Mixed inference: [text, 42]
Even: [2, 4]
Greeting: Hello
Inferred box: Hi
Copied: [red, blue]
Argument: [A, B]
```

Reading the program by context:

1. `names` has target type `List<String>`, so `new ArrayList<>()` infers element type `String`.
2. `scores` uses `var`, but `Integer` is already in `new ArrayList<Integer>()`, so the variable has type `ArrayList<Integer>`.
3. `mixed` uses `var` and the no-arg constructor diamond; the compiler has no more specific clue and infers `ArrayList<Object>`. `add("text")` and `add(42)` are both safe for `Object`.
4. `groups` uses two inference levels: `HashMap<>` from the declared type and `ArrayList<>(List.of(2,4))` from the `put` parameter and input values.
5. `greeting` infers `Box<String>` thanks to the target type and constructor. `inferredBox` has no explicit target type, but the constructor receives `String`, so the variable has type `Box<String>`.
6. `copyWords` shows diamond in a `return` expression; `printStrings` shows diamond in a method argument position.

The example intentionally uses mutable `ArrayList` wherever elements are added. `List.of(...)` provides immutable source data, whereas `new ArrayList<>(source)` creates a new modifiable list; the two have different mutation behavior.

## 10. Diamond is not a wildcard

The two syntaxes look similar but serve different purposes:

```java
List<?> unknown;              // Wildcard: unknown element type
List<String> known = new ArrayList<>(); // Diamond: infers String
```

`?` appears in a **type argument of a used generic type**, to represent an unknown type in a contract. `<>` appears during **object creation** to let the compiler infer type arguments. You cannot write:

```java
// List<?> wrong = new ArrayList<?>(); // Invalid
// List<String> wrong2 = new ArrayList<? extends String>(); // Invalid
```

Even when the target uses a wildcard, the right-hand side during object creation still needs a diamond or a concrete type argument:

```java
List<?> view = new ArrayList<String>();
List<?> inferredView = new ArrayList<>();
```

In `inferredView`, the `List<?>` context does not determine a unique element type. The compiler chooses a type matching the constraints; you must not rely on it necessarily being `String`. To create a list guaranteed to hold `String`, write `new ArrayList<String>()` or provide a sufficiently specific context such as `List<String> names = new ArrayList<>()`.

## 11. Diamond and generic constructors are two independent mechanisms

The type arguments of a **class** and the type arguments of a **generic constructor** can be two different things.

Example class `Entry<T>`:

```java
final class Entry<T> {
    private final T value;

    <U> Entry(T value, U marker) {
        this.value = value;
        System.out.println("Marker: " + marker);
    }

    T get() {
        return value;
    }
}
```

With:

```java
Entry<String> item = new Entry<>("Java", 2026);
```

`T` is the type parameter of class `Entry<T>`, constrained to `String`. `U` is the constructor's own type parameter, inferred from `2026` (an `Integer` after boxing). Diamond `<>` represents **the class type arguments to be inferred**; it does not record `<U>` at the constructor's parameter position.

This snippet illustrates class/instantiation declarations and has no `main`, so it is not a standalone program. If you want to call a generic constructor with explicit type arguments in Java, the exact syntax differs from diamond; normally you do not need to do so when inference works well enough.

The takeaway is: the compiler can solve multiple type variables in the same `new` expression, yet each variable has **its own declaration source and constraints**.

## 12. Syntax limits and common errors

### Diamond only applies to generic classes

```java
List<String> xs = new ArrayList<>(); // Valid
String text = new String("Hello");  // Valid, no diamond needed
// String bad = new String<>();     // Invalid: String is not generic
```

You cannot write diamond in place of declaring a new type parameter:

```java
// class Box<> { }                  // Invalid
class GenericBox<T> { }            // Named type parameter declaration

// static <> void method() { }     // Invalid
static <T> T identity(T value) { return value; } // Valid declaration example
```

The two declarations `GenericBox` and `identity` are separate syntax examples; in an actual program, place methods inside an appropriate class.

### Cannot apply diamond to generic arrays

Java does not allow directly creating many forms of arrays of generic types with non-reifiable arguments:

```java
// List<String>[] lists = new ArrayList<>[10]; // Invalid
```

The reason is that arrays track element types at runtime differently from erased generics. For generic collections, consider `List<List<String>>`:

```java
List<List<String>> lists = new ArrayList<>();
```

### Diamond does not guarantee every assignment is type-compatible

```java
List<String> strings = new ArrayList<>();
// List<Integer> integers = strings; // Does not compile
// List<Number> numbers = new ArrayList<String>(); // Does not compile
```

Diamond cannot fix an incompatible generic relationship. The compiler does not automatically convert `List<String>` into `List<Number>` or `List<Integer>` when type constraints conflict.

### Do not write wildcards directly in object creation

```java
// new ArrayList<?>()                  // Invalid
// new ArrayList<? extends Number>()   // Invalid
List<? extends Number> values = new ArrayList<Integer>(); // Valid
```

Wildcards express a contract when **using a type**. A `new` expression must infer a concrete type that satisfies constraints, or explicitly specify an appropriate type argument.

## 13. Diamond with anonymous classes: Java 7 vs. Java 9+

In Java 7–8, diamond could not be used when instantiating an *anonymous class*. Since Java 9, Java allows diamond with anonymous classes **when the inferred type is denotable** (can be validly represented in Java source).

Java 17-compatible example:

```java
List<String> names = new ArrayList<>() {
    @Override
    public boolean add(String item) {
        return super.add(item.trim());
    }
};
names.add("  Lan  ");
System.out.println(names); // [Lan]
```

This is an illustrative snippet; it requires importing `java.util.List` and `java.util.ArrayList` and being placed inside a method. Overriding `add` uses the exact `String` type inferred from `List<String>` on the left.

When using diamond in an anonymous class, Java imposes an extra restriction on newly declared **non-private** methods inside the anonymous class body: they must override/implement a method from a supertype. If you need to define a new non-overriding method, check this rule or use a named class; do not assume every anonymous class with diamond is valid.

The key takeaway for Java 17 is: diamond **can** be used with anonymous classes in suitable cases, but it is not a universal syntactic substitute for every situation.

## 14. How to diagnose diamond inference errors

When the compiler reports `incompatible types`, `cannot infer type arguments`, or `inference variable ... has incompatible bounds`, follow these steps in order:

1. **Identify the target type**: is the `new C<>()` expression being assigned to a `List<String>` variable, passed to a `Collection<Number>` parameter, or placed in a `return` with a concrete return type?
2. **Inspect the selected constructor**: is it the no-arg constructor, the `Collection<? extends E>` constructor, or another overload? Any passed values also contribute constraints.
3. **Write down the type variables to infer**: for example, `ArrayList<E>` needs to find `E`; `HashMap<K,V>` needs to find `K` and `V`.
4. **Look for conflicts**: does the target require `String` while the data or overload requires an incompatible type? Are you confusing `List<Integer>` with `List<Number>`?
5. **If using `var`**, remember there is no explicitly typed target declaration on the left. Check the type of the initializer expression before reasoning about subsequent `add` calls.
6. **Try stating the type argument explicitly on the right** to clarify intent: `new ArrayList<String>()`. If it still errors, the constraints themselves are likely incompatible.
7. **Prefer explicit signatures/types** when expressions have too many generic layers or overloads. Do not use raw types or unchecked casts to "silence the compiler".

A common error example:

```java
List<String> names = new ArrayList<>();
names.add("Lan");
// names.add(10); // Error: int boxes to Integer, cannot be assigned to String
```

The cause is not the diamond; it inferred `String` correctly. The call adding an `Integer` violates the contract of `List<String>`.

Another example:

```java
var values = new ArrayList<>();
values.add(10);
values.add("Lan");
```

This case **has no error** because `values` has type `ArrayList<Object>`. If you want to forbid strings, you must provide a target type or declare the element type explicitly at initialization.

## 15. Self-check exercises

Predict the static type and compilation result:

```java
// A
List<String> a = new ArrayList<>();

// B
var b = new ArrayList<>();

// C
var c = new ArrayList<>(List.of(1, 2, 3));

// D
Map<String, List<Integer>> d = new HashMap<>();
d.put("odd", new ArrayList<>(List.of(1, 3)));

// E
List<Number> e = new ArrayList<>(List.of(1, 2.5));

// F
List<?> f = new ArrayList<String>();
```

Questions:

1. Why is `a.add("x")` valid while `a.add(1)` is invalid?
2. Do `b.add("x")` and `b.add(1)` compile? Is `b` a raw type?
3. What element type is `c` typically inferred to hold? Can a `String` be added to `c`?
4. Why is `d.put("odd", new ArrayList<>(List.of(1,3)))` valid?
5. Why can `e` hold both `Integer` and `Double` elements?
6. Is `f.add("x")` valid? How does `?` in `List<?>` differ from `<>` in an object creation expression?

**Answers:**

1. `a` has type `List<String>`; the target type causes diamond to infer `String`. `Integer` cannot be assigned to `String`.
2. Both compile because `b` is `ArrayList<Object>`. `b` is **not** a raw type.
3. `c` is inferred as `ArrayList<Integer>` from the input collection `List.of(1,2,3)`; a `String` is not compatible.
4. The type of `d` is `Map<String,List<Integer>>`. The `put` method requires a `List<Integer>` value, and the nested constructor creates a list of `Integer` elements.
5. Target type `List<Number>` allows the constructor to create a list parameterized by `Number`; `Integer` and `Double` are both subtypes of `Number`.
6. `f.add("x")` does not compile because the wildcard `?` does not expose the actual element type. `<?>` states "unknown hidden type" in a declaration; `<>` tells the compiler to infer type arguments during object creation.

## 16. Summary of how to apply

Use **diamond `<>`** when creating a generic object where the compiler already has sufficient constraints from the target type, constructor arguments, or method call context. It preserves type safety and makes code less repetitive. With `var`, be aware that the type may be inferred more broadly than intended if initialized with a no-arg `new ArrayList<>()`; provide an explicit type when you want to restrict elements.

When an inference result is hard to understand, trace backwards: **target type → constructor arguments → type parameters to infer → compatible constraints**. Diamond does not replace understanding Generics, invariance, and wildcards; it merely delegates valid type inference to the compiler.
