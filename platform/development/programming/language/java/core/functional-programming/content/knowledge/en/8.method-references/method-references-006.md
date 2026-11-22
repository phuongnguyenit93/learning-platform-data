# Constructor References with Type::new in Java

## 1. What is a constructor reference used for?

In Java, a **constructor reference** is a form of **method reference** that lets you represent object creation using the `Type::new` syntax. Instead of writing a lambda that calls `new Type(...)`, you can pass a constructor reference to an API expecting a matching **functional interface**.

~~~java
Supplier<StringBuilder> first = () -> new StringBuilder();
Supplier<StringBuilder> second = StringBuilder::new;
~~~

The snippet above is **illustrative** inside a method and requires importing `java.util.function.Supplier`. Both expressions express the same behavior: when called, create a new `StringBuilder`. `StringBuilder::new` does not immediately create an object; it represents a factory function for `Supplier.get()` to invoke later.

Most importantly: **`Type::new` is not a standalone data type**. It needs a *target type* — a functional interface with a single abstract method — so the compiler knows how many arguments, which argument types, and which return type are required.

Example:

~~~java
Supplier<StringBuilder> noArg = StringBuilder::new;
Function<Integer, StringBuilder> withCapacity = StringBuilder::new;
~~~

This snippet requires importing `java.util.function.Function`. It uses the same `StringBuilder::new`, yet:
- With `Supplier<StringBuilder>`, the method descriptor is `() -> StringBuilder`, so the compiler chooses the no-arg constructor.
- With `Function<Integer,StringBuilder>`, the descriptor is `(Integer) -> StringBuilder`; the `Integer` value can be unboxed to `int` for the `StringBuilder(int capacity)` constructor.
- `withCapacity.apply(100)` creates a buffer with an **initial capacity** of 100, not a 100-character string.

**A constructor reference is a way to pass object-creation behavior; it is not a way to bypass constructor rules, type checking, accessibility, or error handling.**

## 2. Syntax and constructor selection mechanism

General structure:

~~~text
ReferenceType::new
ArrayType::new
~~~

Here `ReferenceType` is an object type with an accessible constructor, and `ArrayType` is an array type handled by an array constructor reference. For generic types, you can use explicit type arguments, such as `ArrayList<String>::new`, when the context permits.

The essence can be read from this table:

| Illustrative lambda | Constructor reference | Target functional interface |
| --- | --- | --- |
| `() -> new Ticket()` | `Ticket::new` | `Supplier<Ticket>` |
| `code -> new Ticket(code)` | `Ticket::new` | `Function<String,Ticket>` |
| `(code,n) -> new Ticket(code,n)` | `Ticket::new` | `BiFunction<String,Integer,Ticket>` |
| `size -> new String[size]` | `String[]::new` | `IntFunction<String[]>` |
| `size -> new int[size]` | `int[]::new` | `IntFunction<int[]>` |

`Ticket` is an example class that will be declared in the standalone program in section 7. The table states **behavioral equivalence** when target type, overloads, and accessibility are satisfied; it does not claim that both compile to identical bytecode or intermediate objects.

### 2.1. Arguments belong to the functional interface invocation

Consider `Function<String,Ticket> factory = Ticket::new;`:

1. The compiler sees that the target type has the method `Ticket apply(String)`.
2. The compiler looks for a matching `Ticket` constructor taking `String`.
3. The constructor reference is used as the value of `factory`.
4. When `factory.apply("A12")` is called, the argument `"A12"` is used to run the constructor.
5. If the constructor succeeds, the call returns a new `Ticket`.

Thus, parameters do not appear after `new` when writing the reference: the argument list is determined via the **function descriptor** of the functional interface.

### 2.2. A constructor has no method name to call

A constructor in Java is not a regular method named `new`. `Type::new` is **special language syntax** for referencing object creation. Do not write `Type.new()` or `Type::Type`.

Comparison:

| Syntax | Meaning |
| --- | --- |
| `new Ticket("A")` | Creates an object immediately at that expression |
| `Ticket::new` | References `Ticket`-creation behavior, requires a target type |
| `Ticket::someStaticFactory` | References a **static method** (if it exists), not a constructor |
| `someObject::instanceMethod` | References an instance method with an existing receiver |
| `Ticket::instanceMethod` | References an unbound instance method; the target type must supply the receiver via a parameter |

Even though it belongs to the method reference family, a constructor reference has no pre-existing receiver instance: it **creates a new instance** when the corresponding function succeeds.

## 3. Connecting Type::new to standard functional interfaces

The number of arguments and return type of the constructor suggest the appropriate functional interface:

### 3.1. Supplier<T> — no-arg constructor

~~~java
Supplier<ArrayList<String>> createNames = ArrayList::new;
ArrayList<String> names = createNames.get();
~~~

The illustrative snippet above requires importing `java.util.ArrayList` and `java.util.function.Supplier`, inside a method. `ArrayList::new` selects the no-arg constructor overload. The list is created when `get()` is called.

Note the distinction:

~~~java
Supplier<List<String>> supplier = ArrayList::new;
~~~

This is valid because `ArrayList<String>` can be returned where `List<String>` is expected. The instantiated class is still `ArrayList`, even though the declared result type is the `List` interface.

### 3.2. Function<A,T> — one-arg constructor

~~~java
Function<String, Ticket> byCode = Ticket::new;
Ticket ticket = byCode.apply("A12");
~~~

This illustrative snippet assumes `Ticket` has a `Ticket(String)` constructor and requires importing `java.util.function.Function`. `A` is the input parameter type, and `T` is the created object type. Because `Function<A,T>` takes exactly one argument, it cannot be used for a constructor that only has two required parameters.

### 3.3. BiFunction<A,B,T> — two-arg constructor

~~~java
BiFunction<String, Integer, Ticket> bySeats = Ticket::new;
Ticket ticket = bySeats.apply("B20", 3);
~~~

This is an illustrative snippet requiring `java.util.function.BiFunction` import, assuming `Ticket(String,int)` has been declared. Java automatically unboxes `Integer` to `int` in a compatible context. If you want to avoid boxing or have multiple primitive parameters, consider a custom functional interface with the exact signature.

### 3.4. With three or more arguments

The `java.util.function` package does not provide a general `TriFunction<A,B,C,R>` out of the box. If a constructor has three parameters, you can define an explicit functional interface:

~~~java
@FunctionalInterface
interface TriFactory<A, B, C, R> {
    R create(A a, B b, C c);
}

record Shipment(String id, int quantity, boolean express) {}

TriFactory<String, Integer, Boolean, Shipment> factory =
        Shipment::new;
~~~

The two declarations `TriFactory` and `Shipment` are placed **at class level or top level**; the `factory` assignment is placed inside a method or at a valid variable declaration site. This is partial illustrative code, not a complete Java file. `record Shipment` has a canonical constructor taking `String,int,boolean`, so the reference can match a descriptor taking `String,Integer,Boolean` via unboxing.

For public APIs, consider using a parameter object (a record holding configuration) if the parameter list is long and values should be grouped semantically. Do not create a slew of interfaces just to avoid a lambda `(a,b,c) -> new Type(a,b,c)` when using a lambda is clearer.

## 4. Constructor overloads: same Type::new, multiple choices

A class can have multiple overloaded constructors:

~~~java
class Ticket {
    Ticket() { /* ... */ }
    Ticket(String code) { /* ... */ }
    Ticket(String code, int seats) { /* ... */ }
}
~~~

The constructors above are an **illustrative snippet** whose bodies are syntactic placeholders; the real program in section 7 provides a complete implementation. Java resolves the reference according to the **target functional interface**, checking parameter count, parameter types, conversions, and overload rules.

Example:

~~~java
Supplier<Ticket> a = Ticket::new;
Function<String, Ticket> b = Ticket::new;
BiFunction<String, Integer, Ticket> c = Ticket::new;
~~~

- `a.get()` calls the no-arg constructor.
- `b.apply("T7")` calls the single-`String` constructor.
- `c.apply("T7", 2)` calls the `String,int` constructor.

If no matching constructor exists, the compiler reports an error right at the constructor reference. If multiple constructors match and no unique choice can be made under overload rules, the reference can be ambiguous.

**Do not guess the constructor solely from `Type::new`**; always read the functional interface type where it is assigned or passed.

### 4.1. A constructor reference can also be ambiguous due to overloads of the callback-accepting method

Consider two overloads of an API:

~~~java
static void register(Supplier<Ticket> supplier) { /* ... */ }
static void register(Callable<Ticket> callable) { /* ... */ }
~~~

This is an illustrative class-level snippet requiring `Supplier` and `Callable` imports. If `Ticket` has a no-arg constructor, a direct call `register(Ticket::new)` can match both functional interfaces. When neither overload is more specific, the compiler reports an **ambiguous method call**.

Disambiguate with a variable declaration or cast:

~~~java
Supplier<Ticket> chosen = Ticket::new;
register(chosen);

// Or:
register((Supplier<Ticket>) Ticket::new);
~~~

These are illustrative calls assuming the two `register` methods are defined. Avoid designing multiple overloads with different semantics that accept functional interfaces of the same shape; clear API naming saves callers from frequent casting.

### 4.2. Be careful when using var

~~~java
// DOES NOT COMPILE: missing target type.
// var create = Ticket::new;

// VALID when a concrete functional interface is provided:
Supplier<Ticket> create = Ticket::new;
~~~

Like a lambda, a method reference is a poly expression and needs a target type. `var` does not infer an arbitrary functional interface from `Ticket::new` alone.

## 5. Generics: how Java determines the created object's type

Constructor references often appear with generic classes like `ArrayList<E>`:

~~~java
Supplier<List<String>> listFactory = ArrayList::new;
List<String> names = listFactory.get();
~~~

Java infers the appropriate type from the target type context: the result is an `ArrayList<String>` used where `List<String>` is expected. Writing explicit type arguments is also possible:

~~~java
Supplier<ArrayList<String>> factory = ArrayList<String>::new;
~~~

Requires importing `java.util.List`, `java.util.ArrayList`, and `java.util.function.Supplier`. With constructor reference syntax, do not insert constructor parentheses `()` after `new`; this is not an immediate constructor call.

**Note on raw types:** avoid `ArrayList::new` in a context assigning to a raw `Supplier`, as it can lose type checking. A concrete generic target type helps the compiler verify conversions and elements more safely.

### 5.1. Record constructors can also be referenced

Records are used to represent data and have a canonical constructor matching their components:

~~~java
record Label(String value) {}

Function<String, Label> createLabel = Label::new;
Label label = createLabel.apply("VIP");
~~~

This is illustrative code: the record is declared at type level, and the assignment is inside a method. `Label::new` references the constructor taking a `String`. The result of `label.toString()` on Java 17 is `Label[value=VIP]`.

If a record declares additional valid constructors, a constructor reference can select a compatible overload, just like a regular class.

## 6. Array constructor references: a special case

Java allows referencing **array** constructors, such as `String[]::new` or `int[]::new`. This form is very important when working with Streams and APIs that need array allocation.

### 6.1. IntFunction<T[]> — the most natural usage

~~~java
IntFunction<String[]> factory = String[]::new;
String[] values = factory.apply(3);
~~~

Requires importing `java.util.function.IntFunction`. The descriptor `int -> String[]` is a function taking an **array length** and returning a new `String[]` array of that length. Initially, reference elements in the array are `null`.

Equivalent lambda form:

~~~java
IntFunction<String[]> factory = size -> new String[size];
~~~

When the length value is negative, the array allocation throws `NegativeArraySizeException` at function execution time. Java does not "auto-clamp" negative lengths to 0.

### 6.2. Primitive arrays and other target types

~~~java
IntFunction<int[]> intFactory = int[]::new;
Function<Integer, int[]> boxedLengthFactory = int[]::new;
~~~

Requires importing `java.util.function.Function` and `IntFunction`. In the first case, the length argument is primitive `int`. In the second case, the parameter type is `Integer`, which Java can unbox to `int` for allocation. If the API allows it, `IntFunction<T>` expresses a primitive length directly and avoids unnecessary boxing.

### 6.3. Multidimensional arrays: only the outer dimension is allocated

~~~java
IntFunction<String[][]> matrixFactory = String[][]::new;
String[][] matrix = matrixFactory.apply(2);
~~~

Equivalent in meaning to `size -> new String[size][]`: creates an outer array of length 2, **without automatically creating the inner row arrays**. `matrix[0]` and `matrix[1]` are initially `null`. If a full rectangular matrix is needed, you must allocate the remaining dimensions separately as required.

This is why you should not assume `String[][]::new` is equivalent to `(rows,cols) -> new String[rows][cols]`. An array constructor reference has one `int` length parameter in its function descriptor.

### 6.4. Example with Stream.toArray

A common application:

~~~java
List<String> names = List.of("An", "Bình");
String[] array = names.stream().toArray(String[]::new);
~~~

This snippet assumes `java.util.List` is imported and is placed inside a method. `Stream<T>.toArray(IntFunction<A[]>)` accepts an array-allocating function; the implementation supplies the required size when calling it. `String[]::new` is clearer than `size -> new String[size]` in this situation.

Do not confuse it with the no-arg `Stream.toArray()`, which returns `Object[]`. The form with `String[]::new` lets you get `String[]` matching the target element type.

## 7. Complete Java 17 program

Create the file **ConstructorReferenceDemo.java**. The program combines:
- No-arg, one-arg, and two-arg constructors of the `Ticket` class.
- The canonical constructor of the `Label` record.
- Generic constructor `ArrayList::new`.
- Array references `String[]::new`, `int[]::new`, and `String[][]::new`.
- Using a constructor reference directly in `Stream.map`.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Function;
import java.util.function.IntFunction;
import java.util.function.Supplier;

public class ConstructorReferenceDemo {
    static final class Ticket {
        private final String code;
        private final int seats;

        Ticket() { this("DEFAULT", 1); }
        Ticket(String code) { this(code, 1); }
        Ticket(String code, int seats) {
            this.code = code;
            this.seats = seats;
        }

        @Override
        public String toString() {
            return code + ":" + seats;
        }
    }

    record Label(String value) {}

    public static void main(String[] args) {
        Supplier<Ticket> defaultTicket = Ticket::new;
        Function<String, Ticket> ticketByCode = Ticket::new;
        BiFunction<String, Integer, Ticket> ticketBySeats = Ticket::new;
        Function<String, Label> label = Label::new;

        System.out.println(defaultTicket.get());
        System.out.println(ticketByCode.apply("A12"));
        System.out.println(ticketBySeats.apply("B20", 3));
        System.out.println(label.apply("VIP"));

        Supplier<List<String>> emptyList = ArrayList::new;
        Function<Integer, List<String>> listWithCapacity = ArrayList::new;
        System.out.println("list sizes: " + emptyList.get().size()
                + ", " + listWithCapacity.apply(50).size());

        IntFunction<String[]> stringArray = String[]::new;
        Function<Integer, int[]> intArray = int[]::new;
        IntFunction<String[][]> matrix = String[][]::new;

        System.out.println("array length: " + stringArray.apply(3).length);
        System.out.println("int array length: " + intArray.apply(4).length);
        System.out.println("matrix: " + matrix.apply(2).length
                + ", first row null: " + (matrix.apply(2)[0] == null));

        List<String> codes = List.of("X", "Y");
        List<Ticket> tickets = codes.stream().map(Ticket::new).toList();
        System.out.println("mapped: " + tickets);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 ConstructorReferenceDemo.java
java ConstructorReferenceDemo
~~~

**Directly verified stdout:**

~~~text
DEFAULT:1
A12:1
B20:3
Label[value=VIP]
list sizes: 0, 0
array length: 3
int array length: 4
matrix: 2, first row null: true
mapped: [X:1, Y:1]
~~~

Explanation of the results:

1. `defaultTicket.get()` selects the `Ticket()` constructor, which calls `Ticket("DEFAULT", 1)`, so it prints `DEFAULT:1`.
2. `ticketByCode.apply("A12")` selects `Ticket(String)` and assigns 1 seat by default; `ticketBySeats.apply("B20", 3)` selects `Ticket(String,int)`.
3. `Label::new` uses the record's constructor, so its string representation is `Label[value=VIP]`.
4. Both ways of creating `ArrayList` produce `size() == 0`. The argument 50 in the `ArrayList(int initialCapacity)` constructor specifies **initial capacity**, not inserting 50 elements.
5. The `String[]` array has length 3, the `int[]` array has length 4; `String[][]::new` allocates an outer array of length 2 and the first subarray remains null.
6. `codes.stream().map(Ticket::new)` creates a `Ticket(String)` for each code, behaviorally equivalent to `map(code -> new Ticket(code))`; the result preserves the encounter order of `List.of("X","Y")`.

The program above was compiled with `javac --release 17` and executed, with results matching exactly.

## 8. Constructor references and execution timing

An important distinction is **representing behavior** versus **actually allocating an object**.

~~~java
Supplier<StringBuilder> factory = StringBuilder::new; // constructor not called yet
StringBuilder first = factory.get();                    // constructor called
StringBuilder second = factory.get();                   // constructor called again
System.out.println(first == second);                   // false
~~~

This illustrative snippet requires importing `java.util.function.Supplier`. Each `get()` executes a new `StringBuilder` creation and returns a distinct object when the constructor succeeds.

However, an API receiving a callback may invoke it zero times, once, or many times. For example, `Optional.orElseGet(supplier)` only needs to call `supplier.get()` when no value is present; whereas `Stream.map(Type::new)` typically applies the callback when the pipeline has a terminal operation requiring those elements to be processed.

**Do not assume the constructor runs when `factory` is assigned**. If the constructor has side effects (logging, accessing resources, updating a counter), those side effects appear **when the callback is actually invoked**, not when the reference syntax is evaluated.

## 9. Access scope, special classes, and limitations

### 9.1. The constructor must exist and be accessible

A `private` constructor can only be referenced from a location that has access to it. If the constructor is not accessible from where `Type::new` is written, the compiler reports an error. Similarly, you cannot use `AbstractType::new` to directly instantiate an abstract class or interface because there is no callable constructor to create an instance that way.

For an interface, you typically choose a concrete implementing class:

~~~java
Supplier<List<String>> supplier = ArrayList::new;
~~~

Rather than writing `List::new`, because `List` is an interface with no constructor to instantiate directly.

### 9.2. Constructors with checked exceptions

If a constructor declares a checked exception such as `IOException`, the target callback must have a contract that permits that exception or the code must handle it.

Illustrative example assuming a class:

~~~java
class CheckedResource {
    CheckedResource() throws java.io.IOException {
        throw new java.io.IOException("unavailable");
    }
}
~~~

The following code is a **compile-time error example** (kept in comments):

~~~java
// Supplier<CheckedResource> wrong = CheckedResource::new;
// Invalid: Supplier.get() does not declare IOException.
~~~

You can choose a functional interface that allows checked exceptions, for example:

~~~java
java.util.concurrent.Callable<CheckedResource> create =
        CheckedResource::new;
~~~

This is an illustrative snippet placed inside a method that can access `CheckedResource`; `Callable.call()` declares `throws Exception`. Creating the reference above compiles; however, `create.call()` will throw `IOException` from the example constructor, so the caller must handle/declare the exception.

Do not assume that `Type::new` swallows exceptions or turns checked exceptions into unchecked ones.

### 9.3. Non-static inner classes

A non-`static` member inner class is associated with an instance of its enclosing class, unlike a `static` nested class. An inner class constructor is subject to enclosing-instance rules and special syntax; do not mechanically apply the `Outer.Inner::new` pattern as if it were always equivalent to a constructor of a standalone static class.

To teach or use factories with minimal context coupling, prefer top-level classes, `static` nested classes, or factory methods that make the enclosing instance explicit. If you truly need to instantiate an inner class, verify the exact syntax and target type with your JDK's compiler.

### 9.4. Generic inference and raw types

Inferred generic types depend on the target type and type bounds. Do not assume every `Type::new` infers the desired generic type arguments in every context. When the compiler lacks information or overloads compete, declare the callback with an explicit type or use an explicit lambda.

### 9.5. Not every object creation pattern can be referenced with Type::new

Some classes use **static factory methods** like `of(...)` or `valueOf(...)` instead of public constructors. In that case, the appropriate target is usually `Type::of` or `Type::valueOf`, not `Type::new`.

For example, `List.of(...)` is a static factory creating an unmodifiable collection. There is no `List::new` syntax to replace it. An API may also require a dedicated factory because of validation, caching, lifecycle, or immutability; constructor references do not bypass those conventions.

## 10. When to choose Type::new over a lambda or factory method?

| Situation | Which to choose? | Reason |
| --- | --- | --- |
| Forwarding arguments directly to a constructor | `Type::new` | Concise, clearly reveals intent to create an instance |
| Need computation/adjustment before calling the constructor | `arg -> new Type(normalize(arg))` | A lambda allows transforming parameters |
| Need multiple statements, checks, or try/catch | Block lambda or helper factory | Expresses logic and error handling more clearly |
| Need objects with special caching/validation rules | Static factory method provided by the API | A constructor is not synonymous with a business factory |
| Constructor overload is hard to identify | Explicit target type or explicit lambda | Easier to review and diagnose errors |
| Need array allocation in `Stream.toArray` | `String[]::new` | Matches the `IntFunction<String[]>` signature |
| Passing a factory to a library with its own lifecycle | Choose the exact functional interface accepted by the API | The library controls when the callback runs |

**Principle:** prefer the form that expresses intent most clearly. `Type::new` should not be assumed "faster" than a lambda in all cases; optimize for readability first, and measure performance when there is a real requirement.

## 11. Common mistakes

1. **Thinking `Type::new` creates an object immediately:** it only creates a behavioral reference expression; the constructor runs when the corresponding callback is executed.
2. **Writing `Type::new()`:** constructor references do not place call parentheses directly after `new`.
3. **Writing `var factory = Type::new`:** there is no target functional interface for the compiler to determine the descriptor.
4. **Choosing the wrong argument count:** `Supplier<T>` cannot reference a constructor that requires one mandatory parameter.
5. **Confusing capacity with size:** `new ArrayList<>(100)` does not pre-populate 100 elements; `size()` is still 0.
6. **Ignoring checked exceptions on the constructor:** `Supplier.get()` does not declare checked exceptions; use a suitable interface or handle them.
7. **Trying to instantiate an interface or abstract class with `Type::new`:** there is no constructor to invoke directly that way.
8. **Mistaking an array factory for full multidimensional allocation:** `String[][]::new` takes one length for the outer array and does not allocate the rows.
9. **Assuming a constructor reference always picks the same constructor:** different target types can resolve to different overloads.
10. **Using raw generic types unnecessarily:** explicit type inference with `Supplier<List<String>>` is safer and easier to check.
11. **Confusing `Type::new` with a static factory:** `Type::of` references a static method, not a constructor.
12. **Ignoring that the callback may be called multiple times:** a `Supplier<T>` can create multiple objects, so do not treat it like a fixed singleton variable when caching is intended.

## 12. Self-check exercises

**Exercise 1.** Given `Function<String,Ticket> factory = Ticket::new;`, when does the constructor run?

**Answer:** when a call such as `factory.apply("A")` executes, not when `factory` is declared.

**Exercise 2.** Why is `Supplier<ArrayList<String>> list = ArrayList::new;` valid, while `Supplier<List<String>> list = List::new;` is not?

**Answer:** `ArrayList` is a concrete class with a matching constructor; `List` is an interface that cannot be instantiated directly.

**Exercise 3.** Given `IntFunction<int[]> create = int[]::new;`, what does `create.apply(5)` return?

**Answer:** a new `int[]` array of length 5, with all elements initialized to 0.

**Exercise 4.** `IntFunction<String[][]> create = String[][]::new;` and then `create.apply(3)` creates how many rows?

**Answer:** an outer array of length 3, with each row element initially `null`; no inner arrays exist yet.

**Exercise 5.** Why does `Function<Integer,ArrayList<String>> f = ArrayList::new;` not create a list with a number of elements equal to the argument?

**Answer:** the `ArrayList(int)` constructor sets the initial capacity, while the current number of elements is 0.

**Exercise 6.** If a constructor throws a checked exception and the callback is `Supplier<T>`, what should you do?

**Answer:** choose another callback that permits the appropriate exception, design a wrapper/lambda with explicit error handling, or use a factory API with a suitable exception contract; do not assume `Supplier` permits checked exceptions.

**Exercise 7.** Which constructor of `Ticket` does `Stream<String>.map(Ticket::new)` need?

**Answer:** a constructor taking `String` (or a compatible overload selected by the compiler according to the descriptor); `map` needs a matching `Function<String,Ticket>`.

**Exercise 8.** When is writing `x -> new Type(transform(x))` better than `Type::new`?

**Answer:** when you need to transform, validate, or combine arguments before calling the constructor; a direct reference cannot contain that custom logic.

## 13. References

- [Java Language Specification 17, §15.13 — Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13).
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9).
- [Java Language Specification 17, §15.10 — Array Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10).
- [Java SE 17 API, IntFunction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/IntFunction.html).
- [Java SE 17 API, Stream.toArray(IntFunction)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toArray(java.util.function.IntFunction)).

**Takeaway:** `Type::new` connects a **constructor** to a **functional interface**. The target type determines the parameter count/types and result, and the constructor still obeys overloads, accessibility, and checked exceptions. For arrays, `T[]::new` is an allocation function taking an `int` length. Use a reference when you only need to forward arguments directly to a constructor; use a lambda or factory method when you need extra logic or different semantics.