# Java Generics: Type-Safe Code Reuse

Generics allow classes, interfaces, and methods to accept **data types as parameters**. As a result, the same algorithm or data structure can work with many object types while the compiler still checks whether values are passed and received with the correct type. This is the foundation of familiar APIs such as `List<String>`, `Set<Long>`, and `Map<String, Integer>`.

After this lesson, you will be able to explain why code using `Object` is prone to casting errors, read and write `<T>` declarations, distinguish between errors caught at compile time and errors that only occur at runtime, and recognize the basic limitations of generics.

## 1. The Problem Before Generics: Reusing Code with `Object`

Suppose an application needs a box that holds a value. If we write separate classes like `StringBox`, `IntegerBox`, `UserBox`, etc., we repeat almost identical structure and logic. The common approach is to store the value as type `Object`, because every reference class in Java inherits from `Object`.

```java
final class LegacyBox {
    private final Object value;

    LegacyBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
```

How to use it:

```java
LegacyBox box = new LegacyBox("Java");
String language = (String) box.get(); // The caller must cast.

LegacyBox another = new LegacyBox(42);
String errorLater = (String) another.get(); // Compiles; fails at runtime.
```

The last line compiles because the compiler only knows that `get()` returns `Object`, and casting to `String` is a syntactically valid reference cast. At runtime, the actual object is an `Integer`, so Java throws a `ClassCastException`.

There are three problems here:

1. **Loss of type information when using the API:** the signature `Object get()` does not tell the caller with certainty what the box actually contains.
2. **Manual casting required:** calling code is longer and error-prone; the compiler does not guarantee that the value inside matches the expected type.
3. **Errors appear late:** putting one type into the box and retrieving it as another type may only fail when that code branch is executed.

`Object` enables *reusing the storage structure*, but it cannot express the constraint “this box only stores strings” directly in the data type's contract.

## 2. What Do Generics Solve?

Replace the fixed type `Object` with a **type parameter**, for example `T`:

```java
final class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    void set(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

In the declaration `class Box<T>`, `T` is a placeholder name for the reference type that will be specified when using the class. `Box<String>` and `Box<Integer>` are two ways of *parameterizing* the same `Box<T>` definition:

```java
Box<String> text = new Box<>("hello");
text.set("Java");
String value = text.get(); // No explicit cast needed.

Box<Integer> number = new Box<>(42);
int result = number.get(); // Integer is automatically unboxed to int.

// text.set(42); // DOES NOT compile: requires String, but received int.
```

**Distinguishing three syntactic positions:**

| Syntax | Meaning |
| --- | --- |
| `class Box<T>` | Generic class declaration; `T` is the type parameter. |
| `Box<String>` | Using the class with `String` as the type argument. |
| `new Box<>(...)` | The diamond operator `<>` asks the compiler to infer the type argument from context. |

The name `T` is only a convention; you can choose another clearer name. Common names include `T` (Type), `E` (Element), `K` (Key), and `V` (Value). They are not Java keywords.

The core point is **the type relationship across the entire API**: the argument passed to the constructor and `set(T)` must match `T`, and `get()` returns that same `T`. The compiler verifies that relationship at method call sites. A single class definition serves multiple types while providing early error feedback.

## 3. Complete Example Running on Java 17+

Create a file named `Main.java` with the following content. The program places the `Object`-based approach alongside `Box<T>` and also uses a generic method.

```java
import java.util.List;

public class Main {
    static final class LegacyBox {
        private final Object value;

        LegacyBox(Object value) {
            this.value = value;
        }

        Object get() {
            return value;
        }
    }

    static final class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        void set(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("Danh sách rỗng");
        }
        return values.get(0);
    }

    public static void main(String[] args) {
        LegacyBox legacy = new LegacyBox("Java");
        String oldText = (String) legacy.get();
        System.out.println("Legacy: " + oldText);

        legacy = new LegacyBox(42);
        // String errorLater = (String) legacy.get(); // ClassCastException at runtime.

        Box<String> text = new Box<>("Java");
        text.set("Generics");
        String word = text.get();
        System.out.println("Box<String>: " + word);

        Box<Integer> number = new Box<>(42);
        System.out.println("Box<Integer>: " + number.get());

        System.out.println("first String: " + first(List.of("A", "B")));
        System.out.println("first Integer: " + first(List.of(10, 20)));
        // text.set(42); // Compile error: Integer is not compatible with String.
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Expected output:

```text
Legacy: Java
Box<String>: Generics
Box<Integer>: 42
first String: A
first Integer: 10
```

The lines with error comments are intentionally commented out. If you remove `//` before `text.set(42)`, the example will **not compile**: that is the early type-mismatch detection mechanism. If you remove `//` before casting `legacy.get()` to `String`, the program can throw `ClassCastException` at that line because `legacy` holds an `Integer`.

## 4. Generic Methods: Reusing Algorithms

Generics do not apply only to classes. Methods can also **declare their own** type parameters:

```java
static <T> T first(List<T> values) {
    if (values.isEmpty()) {
        throw new IllegalArgumentException("Danh sách rỗng");
    }
    return values.get(0);
}
```

`<T>` **appears before the return type** `T`: that is the method's own type parameter declaration. The parameter `List<T>` ensures that the input element type and the return type are linked.

Example:

```java
String name = first(List.of("An", "Bình")); // T is inferred as String.
Integer id = first(List.of(101, 102));     // T is inferred as Integer.
```

A single algorithm for getting the first element works for both strings and integers. The compiler infers `T` from the argument types and the call context; sometimes you can also write the type argument explicitly, such as `Main.<String>first(List.of("An"))`.

Note: generics **do not automatically check for empty data**. The `values.isEmpty()` check above is a business rule of the method to prevent `get(0)` from causing an `IndexOutOfBoundsException`. Type safety and value validity are two different concerns.

## 5. Why Are Type Errors Caught Early?

Compare a list using `Object` with a list that has a specific element type:

```java
List<Object> mixed = new java.util.ArrayList<>();
mixed.add("Java");
mixed.add(100); // Valid: both String and Integer are Object.

List<String> languages = new java.util.ArrayList<>();
languages.add("Java");
// languages.add(100); // Does not compile: element must be String.

String firstLanguage = languages.get(0); // No cast needed.
```

The Java compiler checks operations such as `add`, `set`, and the result of `get` against **the type argument in the expression**. Calls that violate the contract are rejected at compile time, before the program runs. This is very helpful when changing APIs or refactoring code: incompatible call sites usually show up immediately as compile errors.

| Criterion | `Object`-only API | Generic API |
| --- | --- | --- |
| Reusing one structure for multiple types | Yes | Yes |
| Expressing value types in API signatures | Vague: usually just `Object` | Clear: `Box<String>`, `List<Integer>` |
| Reading values as a concrete type | Usually requires casting | Usually no explicit cast needed |
| Preventing passing the wrong type in normal calls | No | Yes, at compile time |
| Completely eliminating `ClassCastException` | No | **No**; raw/unchecked code or legacy code can still cause errors |

Generics also help IDEs provide more accurate method suggestions and refactoring because type information is preserved in the API.

## 6. When to Use Generics

**Data structures:** when a list should only hold user names, use `List<String>` instead of `List<Object>`. For a dictionary mapping product codes to quantities, use `Map<String, Integer>` to clearly describe the key and value types:

```java
java.util.Map<String, Integer> quantities = new java.util.HashMap<>();
quantities.put("SKU-01", 5);
Integer count = quantities.get("SKU-01");
```

**Reusable components:** a single `Box<T>` can hold `String`, `Integer`, or a domain type like `Order` without copying a new box class for each type. If there are two independently related types, a class can declare multiple type parameters, such as `Pair<K, V>`.

**Data processing utilities:** a method such as `first(List<T>)` reuses the operation while preserving the return type for each call site. This is why the Java Collections library uses generics extensively: strong type contracts without duplicating algorithms for each element type.

**When generics are not needed yet:** if a class only handles a single type with specific rules, a concrete declaration such as `UserService` is usually easier to understand. Avoid adding `<T>` just to look “generic”; a type parameter should represent a **real type relationship** among input parameters, results, and state.

## 7. Limitations to Understand from the Start

### 7.1. Generics Are Not Comprehensive Runtime Type Checking

Java implements generics primarily through **type erasure**: the compiler checks type constraints in the source code and then removes most type argument information from the executable bytecode, inserting necessary casts at certain usage points. Therefore, `List<String>` and `List<Integer>` use the same runtime `ArrayList` implementation class; you cannot write `value instanceof List<String>` to check the exact element type.

Compile-time checking is still tremendously useful, but it **does not guarantee that every execution path is safe** if data passes through legacy APIs, unchecked casts, or raw types.

### 7.2. Avoid Raw Types and `unchecked` Warnings

Using `List` without a type argument is a *raw type*, intended mainly for compatibility with older Java code:

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names; // Raw type: type safety guarantee is lost at this variable.
raw.add(123);              // Produces an unchecked warning; can pollute the list.
// String name = names.get(0); // May throw ClassCastException if an Integer is read.
```

The snippet above only illustrates the risk and is **not a recommended usage pattern**. Prefer declarations with full type arguments (`List<String>`) and do not blindly suppress `unchecked` warnings. A `ClassCastException` can still happen when reading an element inserted through `raw`.

### 7.3. Type Arguments Must Be Reference Types

`Box<int>` is **invalid**; use `Box<Integer>`. Java supports automatic boxing/unboxing when converting between `int` and `Integer`. Similarly, `List<double>` is invalid, whereas `List<Double>` is valid.

### 7.4. Generic Types Do Not Automatically Have Inheritance Relationships

Even though `Integer` is a subclass of `Number`, `List<Integer>` is **not** a subclass of `List<Number>`. If such an assignment were allowed, someone could add a `Double` to a list that actually only holds `Integer` values. Generics are invariant by default. Wildcards such as `? extends Number` or `? super Integer` address certain flexibility needs, but they belong to the next step of learning about type bounds and wildcards after mastering the basics.

### 7.5. Generic Types Do Not Automatically Enforce Business Constraints

`Box<String>` can still hold `null`; `List<Integer>` can still contain negative numbers. Generics ensure compatibility **in data type** across checked calls, not “non-empty string”, “positive number”, or “validated”. Those requirements must be handled with separate value checks.

## 8. Common Mistakes and How to Avoid Them

- **Using `Object` even when the type is known:** this forces callers to cast and weakens the API contract. Add a type parameter to the class or method when there is a type relationship to preserve.
- **Declaring raw types** (`List items`): easily leads to `unchecked` warnings and runtime errors. Use `List<Item>` or the required element type.
- **Thinking generics “change an object's type” at runtime:** `T` is a tool for describing and checking types in source code; it is not a mechanism for turning an `Integer` into a `String`.
- **Placing `<T>` in the wrong position on a method:** you must declare `static <T> T first(...)`, not just `static T first(...)` if `T` has not been declared in an enclosing valid scope.
- **Confusing type safety with data validation:** `List<String>` does not prevent empty strings, `null`, or invalid external data.
- **Overusing unchecked casts to bypass the compiler:** only cast when you have clear justification regarding the actual runtime type and can verify data boundaries.

## 9. Self-Check

**Scenario 1:** Do the two calls `new Box<String>("A")` and `new Box<Integer>(1)` require creating two different `Box` class definitions?

**Answer:** No. The same `Box<T>` is reused with two different type arguments; the compiler checks each call site separately according to the chosen type.

**Scenario 2:** Why can `String s = (String) legacy.get()` fail at runtime, while `Box<String> b; b.set(100)` is rejected at compile time?

**Answer:** `LegacyBox.get()` is declared to return `Object`, so the cast can be accepted even if the actual value is not a `String`. With `Box<String>`, the parameter of `set` is fixed as `String`, so passing an integer does not match the parameterized method signature.

**Scenario 3:** Can a `List<Integer>` be assigned to a `List<Number>` variable because `Integer extends Number`?

**Answer:** No. Those two list types do not have a subtype relationship in that way; invariance prevents adding incompatible number types to the list.

## Conclusion

Generics solve a very practical design problem: **writing a structure or algorithm once and reusing it for many types while maintaining a clear type contract**. Syntax such as `Box<T>`, `List<String>`, and `static <T> T first(List<T>)` moves many errors from runtime to compile time, reduces casting, and makes APIs easier to read. Start by using generic types only when there is a type relationship to express, avoid raw types, and always validate value constraints independently of type safety.