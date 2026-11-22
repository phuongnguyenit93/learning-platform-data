# Passing Explicit Type Arguments to Clarify an Invocation

## Objectives

In most generic method calls in Java, the compiler automatically infers types from the passed arguments and from the context where the result is used. However, there are times when you want to **explicitly specify the type argument** to express intent, control the result type, or make a complex call easier to understand.

Example:

```java
Number value = ExplicitTypeArgumentsDemo.<Number>chooseFirst(10, 2.5);
List<String> empty = Collections.<String>emptyList();
```

These two statements are **illustrative**: the `chooseFirst` method is defined by us in the standalone runnable example below; `Collections.emptyList()` is a standard API in `java.util.Collections`.

After this lesson, you will be able to distinguish a **type parameter in a declaration** from a **type argument in an invocation**, write the exact syntax for passing explicit type arguments to static/instance methods, explain the relationship with **type inference** and **target typing**, and recognize when explicit syntax is genuinely helpful versus when it only makes code longer.

## 1. Type parameters in declarations differ from type arguments in invocations

Consider the generic method:

```java
static <T> T chooseFirst(T first, T second) {
    return first;
}
```

This is an **illustrative** method placed inside a class. In `static <T> T chooseFirst(...)`:

- `<T>` before the return type is the **type variable declaration** (*type parameter*) of the method.
- The two parameters `first` and `second` are checked against type `T`.
- The method returns a value with static type `T`.

The caller can let the compiler infer:

```java
Number result = chooseFirst(10, 2.5);
```

Or explicitly specify the type argument:

```java
Number result = ExplicitTypeArgumentsDemo.<Number>chooseFirst(10, 2.5);
```

In the second call, **`<Number>` is an explicit type argument**. It substitutes `Number` for `T` in that call: `Integer` obtained from literal `10` via boxing and `Double` obtained from literal `2.5` are both compatible with `Number`. The compile-time return type is `Number`.

Type arguments **do not replace method parameter values**. The expressions `10` and `2.5` remain the actual data arguments. Specifying `T = Number` also **does not convert the `Integer` object into a new `Number`**; in the example, the returned object is the original `first` element.

Two pairs of concepts must be kept distinct:

| Position | Syntax pattern | Effect |
| --- | --- | --- |
| Method declaration | `static <T> T chooseFirst(T a, T b)` | Defines the type variable `T` |
| Call with explicit type | `Demo.<Number>chooseFirst(1, 2.5)` | Selects `Number` as `T` for the call |
| Implicit call | `Demo.chooseFirst(1, 2.5)` | Compiler infers a suitable type |
| Data arguments | `1, 2.5` | Supplies the values for `a` and `b` |

A class can be generic while also having its own generic methods. A method's type parameter `T` is not automatically the class's type parameter and is only in scope within that method's declaration.

## 2. Syntax for passing explicit type arguments

### 2.1. Calling a static method

For a static generic method in class `Demo`, the explicit syntax is:

```java
Demo.<String>identity("hello");
Demo.<Number>chooseFirst(10, 2.5);
```

The two calls above illustrate the syntax; to compile, class `Demo` needs to declare suitable `identity`/`chooseFirst` methods. The dot sits **before** `<String>`, followed by the **method name**. Writing `Demo.<String>identity(...)` indicates this is a type argument of the *invoked method*.

With `java.util.Collections`, actual code looks like:

```java
List<String> values = Collections.<String>emptyList();
```

`Collections.emptyList()` is declared in the form:

```java
public static <T> List<T> emptyList()
```

This is an abbreviated signature of the standard API, not a method you need to define yourself. Calling `Collections.<String>emptyList()` specifies `T = String`, so the result has type `List<String>`.

### 2.2. Calling an instance method

An explicit type argument can also be placed after the *receiver* expression of an instance method:

```java
String description = printer.<String>describe("generic");
```

This is an illustrative snippet, where `printer` is an object with a generic method `<T> String describe(T value)`. The complete runnable example later uses the expression `new Printer().<String>describe("generic")`.

You do not need to pass the class's type parameter as a type argument to every instance method. Check **whether the specific method declares `<T>`**. A regular method on `List<String>` such as `add(String)` does not magically become a generic method just because its enclosing class/interface has a type parameter.

### 2.3. Multiple type parameters and type bounds

If a method declares multiple type parameters:

```java
static <K, V> String describePair(K key, V value) {
    return key + "=" + value;
}
```

the caller can pass type arguments **in the exact order**:

```java
String pair = Demo.<String, Integer>describePair("age", 20);
```

These are illustrative examples (assuming the method is placed inside class `Demo`). The number of type arguments passed must match the number of type parameters of the method. Type arguments must obey bounds and type constraints.

For example, with:

```java
static <T extends Number> double asDouble(T number) {
    return number.doubleValue();
}
```

`Demo.<Integer>asDouble(7)` is valid, whereas `Demo.<String>asDouble("7")` **does not compile**: `String` does not satisfy the `T extends Number` bound.

An explicit type argument must be a **reference type** such as `Integer`, `String`, or `Number`, not a primitive `int` or `double`. When passing primitive literal `7` to a parameter of type `Integer`, Java can use autoboxing.

## 3. How do type inference and target typing work?

**Type inference** is the process by which the compiler finds suitable type arguments from information at the call site. In Java 17, that information can include:

- Static types of the actual arguments passed to the method.
- Constraints on type parameters such as `<T extends Number>`.
- Expected type of the context, such as an assignment, an enclosing call's parameter, or an appropriate return context.
- Relationships between type parameters and wildcards in the method declaration.

Example:

```java
List<String> first = Collections.emptyList();
List<Integer> second = Collections.emptyList();
```

In these two assignments, the compiler has enough **target type** information from the left-hand side to infer `T = String` and `T = Integer` without writing `Collections.<String>emptyList()` or `Collections.<Integer>emptyList()`.

Therefore, when the call is already short and the desired type is clear, explicit syntax is usually **unnecessary**. Adding `<T>` is only helpful when it highlights a notable type decision.

Conversely, if `var` is used, the variable's type comes from the static type of the initializer expression; there is no declared type on the left like `List<String>` to guide inference:

```java
var inferred = Collections.emptyList();          // List<Object>
var explicit = Collections.<String>emptyList(); // List<String>
```

The lines above are illustrative examples inside a Java 17 method. With an `emptyList()` call having no data arguments, the compiler typically infers `Object` when there is no specific target type. An explicit type argument is a way to express the `List<String>` intent right in the initializer expression.

However, `emptyList()` returning `List<String>` **does not make the list mutable**. The empty list returned by `Collections.emptyList()` does not allow adding elements. If you need a modifiable list, create a new `ArrayList` from it.

## 4. Standalone runnable Java 17+ example

Create the file **`ExplicitTypeArgumentsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class ExplicitTypeArgumentsDemo {
    static <T> T chooseFirst(T first, T second) {
        return first;
    }

    static <T> List<T> copy(List<? extends T> source) {
        return new ArrayList<>(source);
    }

    static <T extends Number> double asDouble(T value) {
        return value.doubleValue();
    }

    static final class Printer {
        <T> String describe(T value) {
            return "value=" + value;
        }
    }

    public static void main(String[] args) {
        Number chosen = ExplicitTypeArgumentsDemo.<Number>chooseFirst(10, 2.5);
        System.out.println("chosen: " + chosen);

        List<Integer> integers = List.of(1, 2);
        List<Number> copied = ExplicitTypeArgumentsDemo.<Number>copy(integers);
        System.out.println("copied: " + copied);

        List<String> empty = Collections.<String>emptyList();
        System.out.println("empty size: " + empty.size());

        var texts = new ArrayList<>(Collections.<String>emptyList());
        texts.add("Java");
        System.out.println("texts: " + texts);

        String info = new Printer().<String>describe("generic");
        System.out.println("instance: " + info);

        System.out.println("as double: "
                + ExplicitTypeArgumentsDemo.<Integer>asDouble(7));

        List<Number> inferred = ExplicitTypeArgumentsDemo.copy(List.of(3, 4.5));
        System.out.println("inferred: " + inferred);
    }
}
```

Run from the directory containing the file:

```bash
javac ExplicitTypeArgumentsDemo.java
java ExplicitTypeArgumentsDemo
```

**Exact stdout:**

```text
chosen: 10
copied: [1, 2]
empty size: 0
texts: [Java]
instance: value=generic
as double: 7.0
inferred: [3, 4.5]
```

### Explaining the output

1. `<Number>chooseFirst(10, 2.5)` explicitly states `T = Number`. The first element is the integer `10`, so `System.out.println` prints `10`, even though the static type of variable `chosen` is `Number`.
2. `<Number>copy(integers)` creates a new `List<Number>` from `List<Integer>`. The signature `List<? extends T>` allows reading `Integer` as `Number`. This is **copying the list structure** (a shallow copy with respect to element references), not making the original list have type `List<Number>`.
3. `Collections.<String>emptyList()` explicitly specifies the element type of the result, while `size()` is 0 because the list is empty.
4. `new ArrayList<>(Collections.<String>emptyList())` creates a new modifiable list while preserving the `String` type. `texts.add("Java")` turns the list into `[Java]`.
5. `new Printer().<String>describe("generic")` illustrates placing a type argument on an **instance method call**.
6. `<Integer>asDouble(7)` satisfies `T extends Number` and calls `doubleValue()` on the `Integer` object, printing `7.0`.
7. `copy(List.of(3, 4.5))` has no explicit type argument; the compiler infers a type compatible with `List<Number> inferred`. This is a case where you should **prefer letting Java infer**, since the desired result is already clear from the receiving variable's type.

The example uses Java 17 and needs no libraries outside the JDK. `Integer`, `Number`, and `String` belong to `java.lang`, so they need no import.

## 5. When do explicit type arguments actually help?

### 5.1. No type information from data arguments

`Collections.emptyList()` takes no data arguments; when the context provides no expected type, an explicit type argument is the clearest way to state intent:

```java
var names = Collections.<String>emptyList();
```

The compiler obtains `List<String>` directly from the expression, instead of inferring a list of a more general type. This is an illustrative example inside a Java 17 method; `names` points to an unmodifiable empty list.

### 5.2. Wanting to see the result type right at the call site

Suppose we have the method:

```java
static <T> List<T> copy(List<? extends T> source) {
    return new ArrayList<>(source);
}
```

The source argument might be `List<Integer>`, yet you want the result declared as `List<Number>`:

```java
List<Integer> source = List.of(1, 2);
List<Number> numbers = ExplicitTypeArgumentsDemo.<Number>copy(source);
```

The `<Number>` syntax tells readers that you **want to widen the copy's element type to `Number`**. The variable `numbers` can accept a `Double` later because `copy` returns an `ArrayList<Number>`, if adding fits the application logic:

```java
numbers.add(2.5);
System.out.println(numbers); // [1, 2, 2.5]
```

The snippet above is an additional example inside a method. **The source `source` remains `List<Integer>`** and does not contain `Double`. The explicit type helps select an appropriate return type; it does not perform an unsafe cast on the source.

### 5.3. Wanting to constrain a notable type choice

When a generic method has multiple arguments of different subtypes:

```java
Number chosen = ExplicitTypeArgumentsDemo.<Number>chooseFirst(1, 2.5);
```

`<Number>` expresses that the caller wants to handle both values within the `Number` framework. This is a useful choice for **clarity**, especially when the default inferred type might be complex. Even so, `<Number>` itself does not perform numeric conversion from `Integer` to `Double` or vice versa.

### 5.4. When a chained API obscures the target type

In nested expressions or fluent chains, readers may have to trace inference across several calls. A well-placed explicit type argument clarifies the type right at the data creation source:

```java
var mutableNames =
        new ArrayList<>(Collections.<String>emptyList());
mutableNames.add("Lan");
```

This syntax is clear about `String` without adding a full type declaration on the left-hand side. Do not sprinkle type arguments on every call in a chain; only place them at the step where they genuinely express intent or resolve an inference error.

## 6. Explicit type arguments cannot force an invalid call to become valid

**Rule:** writing `<T>` specifies the type parameter; Java still checks the types of **all value arguments**, the return type, generic bounds, and overload applicability.

Annotated compile-error examples:

```java
// Cannot assign List<Integer> to List<Number>:
List<Integer> integers = List.of(1, 2);
// List<Number> invalid = integers;

// T = Number does not allow a String list as source:
// List<Number> invalidCopy =
//         ExplicitTypeArgumentsDemo.<Number>copy(List.of("a"));

// T = String violates the T extends Number bound:
// double invalidNumber =
//         ExplicitTypeArgumentsDemo.<String>asDouble("7");

// T = Integer makes the result List<Integer>, not List<Number>:
// List<Number> invalidResult =
//         ExplicitTypeArgumentsDemo.<Integer>copy(integers);
```

Each error line must be understood through the generic signature and the invariance of `List<T>`. There is no "magic type witness" that turns a `List<Integer>` into `List<Number>` via direct assignment.

### A type argument is not a cast

- `(Number) expression` is the syntax to **cast** an expression to a target type.
- `Demo.<Number>method(...)` is the syntax to **pass a type argument to a generic method**; the compiler checks the signature with `T = Number`.
- `new ArrayList<Number>(source)` is **creating a new list object** with type argument `Number` on the constructor/class, distinct from a generic method call.

A type argument can affect the call's type constraints, but it does not create extra objects, perform data conversion on its own, or eliminate runtime errors inside the method body.

### Without a type parameter, there is nothing to specify

You cannot put an arbitrary `<String>` on a **non-generic** method and expect it to adopt a new type. Inspect the method's declared signature: only type parameters provided by a generic method are meaningful in a corresponding type-witness call.

If a class is `Box<String>` but its `get()` method does not declare its own type parameter, the `String` type of the result comes from the **class parameter**, which does not mean you should write `box.<String>get()`.

## 7. Relationship with method overloading

A class can declare multiple methods with the same name but different parameter lists. Overload selection also depends on **the types and count of arguments**, signature applicability, boxing, varargs, and Java's "more specific" rules.

An explicit type argument can affect whether a **generic candidate** is applicable, but it **is not a syntax to pick any arbitrary overload at will**. To understand which call is selected, read all signatures with the same name and apply overload resolution rules.

In particular, do not try to use `<T>` as a workaround for an ambiguous overload without understanding why it is ambiguous. In some cases, you must **change the type of an argument expression**, use an API with a clearer name, or supply another kind of type information. Do not equate specifying a type parameter with performing a cast.

## 8. Connection to wildcards and generic methods

A generic method often combines a type parameter with wildcards:

```java
static <T> List<T> copy(List<? extends T> source) {
    return new ArrayList<>(source);
}
```

Here:

- `<T>` declares a type parameter of the **method**.
- `? extends T` states that source elements belong to some (unspecified) subtype of `T`.
- `List<T>` is the return type, so the caller may want to decide `T` explicitly.

The call:

```java
List<Integer> input = List.of(1, 2);
List<Number> result = ExplicitTypeArgumentsDemo.<Number>copy(input);
```

is valid because `Integer extends Number`. Conversely:

```java
// List<String> invalid =
//         ExplicitTypeArgumentsDemo.<String>copy(input);
```

is invalid: `Integer` is not a subtype of `String`.

This is a good example showing that an explicit type argument helps express the goal, while the wildcard helps **maintain type safety between the producer and the result type**. However, when a sufficiently clear target type exists, `List<Number> result = ExplicitTypeArgumentsDemo.copy(input);` can also be inferred successfully by the compiler. The difference is mainly whether you want `Number` to be decided explicitly at the call site.

## 9. Common mistakes

**Confusing declaration syntax with invocation syntax.** `static <T> T f(T x)` is a declaration; `ClassName.<String>f("a")` is an invocation. Do not arbitrarily write `<String>` before the entire class name.

**Specifying primitive types.** `<int>` and `<double>` are not valid generic type arguments. Use `Integer` and `Double` when needed.

**Assuming an explicit type argument makes invariant generics covariant.** `List<Integer>` is still not `List<Number>`. If you need to create a new list typed as `Number`, you must use an appropriate mechanism such as the generic `copy` in the example; do not use direct assignment.

**Believing `<T>` can bypass bounds.** `<String>asDouble(...)` is invalid if the method declares `T extends Number`.

**Repeating unnecessary type arguments.** `List<String> x = Collections.<String>emptyList()` is valid, yet `List<String> x = Collections.emptyList()` is just as clear and usually cleaner thanks to target typing.

**Confusing collection kind.** `Collections.<String>emptyList()` has type `List<String>` but elements cannot be added to it; type safety does not imply mutability.

**Confusing type arguments with runtime type tokens.** `<String>` does not make Java retain `Class<String>` for reflection or runtime specialization. Java Generics is primarily implemented via type erasure; if a method needs `Class<T>` information at runtime, the API must declare a `Class<T>` parameter or an equivalent mechanism.

**Using type witnesses to mask a confusing API design.** If you have to insert type arguments too often, consider adjusting signatures, intermediate types, method names, or expression structure for readability.

## 10. Self-check

**Question 1.** How do the two calls `Collections.emptyList()` and `Collections.<String>emptyList()` differ?

The second call explicitly specifies `T = String`. If a context such as `List<String> x = ...` already suffices for inference, both can yield the same compile-time result type.

**Question 2.** What type does `var items = Collections.<Integer>emptyList();` give `items`?

The compiler infers `List<Integer>` for the initializer expression, so `items` has static type `List<Integer>`. That list is still unmodifiable.

**Question 3.** Why is `<Number>copy(List<Integer>)` valid?

Because `source` requires `List<? extends Number>` after choosing `T = Number`, and `Integer` is a subtype of `Number`. The method returns a new `List<Number>`.

**Question 4.** Can you write `SomeClass.<int>genericMethod(1)`?

No. Generics require reference types as type arguments, such as `Integer`. The literal `1` can be autoboxed to `Integer` if the signature requires it.

**Question 5.** Will `Demo.<String>asDouble("7")` pass the compiler if the method declares `<T extends Number>`?

No, because `String` does not satisfy the `Number` type bound.

**Question 6.** When should automatic inference be preferred?

When the compiler infers correctly, the expected types are already clear from arguments and target types, and adding `<T>` provides no important readability benefit.

## Remember

The syntax `Receiver.<TypeArg>genericMethod(args)` allows **specifying the type arguments of a generic method at the call site**. It clarifies the intended type `T`, especially when there is no target type or when intentionally choosing a broader result type. The compiler still enforces all type constraints, generic bounds, and overload resolution rules. When default inference is already clear, let Java infer automatically; write explicit type arguments only when doing so clarifies meaning or resolves a specific inference situation.
