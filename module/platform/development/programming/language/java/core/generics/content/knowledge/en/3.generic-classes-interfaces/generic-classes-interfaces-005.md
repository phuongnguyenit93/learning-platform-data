# Implementing Interfaces with Concrete Type Arguments in Java Generics

A **generic interface** defines a behavioral contract using type parameters, such as `Processor<T>`, `Converter<I, O>`, or `Repository<E>`. When a class writes `implements Processor<String>`, that class chooses the **concrete type argument** `String` to fulfill the contract: the positions that originally used `T` in the interface's methods are interpreted as `String` in the source-level API.

This technique allows one interface to serve many data types while each implementing class retains clear signatures checked by the compiler. The lesson explains the `implements Interface<ConcreteType>` syntax, how to write `@Override` properly, multi-type-parameter cases, differences from keeping the implementing class generic, and limitations related to inheritance, type invariance, and *type erasure*.

## 1. Reading `implements Interface<ConcreteType>` Correctly

Suppose we want a contract that converts data into a string:

```java
interface Renderer<T> {
    String render(T value);
}
```

`T` is the **type parameter** declared on the interface. `Renderer<T>` itself does not yet require a concrete data type. A class handling strings can choose `String`:

```java
final class UppercaseRenderer implements Renderer<String> {
    @Override
    public String render(String value) {
        return value.toUpperCase();
    }
}
```

Analysis:

- `implements Renderer<String>`: the `UppercaseRenderer` class commits to implementing the `Renderer` interface with **type argument** `String`.
- `String render(String value)`: the method in the implementing class matches the contract after substituting `String` for type parameter `T`.
- `@Override`: asks the compiler to verify that the method actually overrides or implements an overridable method of the supertype; very helpful for catching signature mismatches.
- `UppercaseRenderer` is a normal class, **not a generic class**, because it does not declare `<T>` after the class name. It always implements `Renderer<String>` and does not take new type arguments at instantiation sites.

Importantly: `implements Renderer<String>` does not turn the letter `T` in the interface definition into a global variable; it **binds the type role** in the contract that this class is implementing. Another class can independently write `implements Renderer<Integer>` and provide `render(Integer value)`.

## 2. Complete Java 17 Program: One Interface, Multiple Specialized Classes

Save as the file **`ConcreteInterfaceDemo.java`**:

```java
public class ConcreteInterfaceDemo {
    interface Renderer<T> {
        String render(T value);
    }

    static final class UppercaseRenderer implements Renderer<String> {
        @Override
        public String render(String value) {
            return value.toUpperCase();
        }
    }

    static final class IntegerRenderer implements Renderer<Integer> {
        @Override
        public String render(Integer value) {
            return "Số: " + value;
        }
    }

    public static void main(String[] args) {
        Renderer<String> text = new UppercaseRenderer();
        Renderer<Integer> number = new IntegerRenderer();

        System.out.println(text.render("java"));
        System.out.println(number.render(25));
    }
}
```

Compile and run using JDK 17 or later:

```bash
javac -encoding UTF-8 ConcreteInterfaceDemo.java
java ConcreteInterfaceDemo
```

Exact result (`stdout`):

```text
JAVA
Số: 25
```

On the `text` variable, the compiler understands `render(...)` accepts `String`; on the `number` variable, the method accepts `Integer`. The `int` value `25` is boxed (`autoboxing`) to `Integer` by Java upon the call.

If you add the following statement to `main`:

```java
// text.render(25); // Compile error: Renderer<String> requires String
```

the compiler will reject the call. **There is no need to use `instanceof` or manual casting** at the call site because the type of the input value is already expressed in the interface.

Distinguish between the type of the **variable** and the type of the **object**:

```java
Renderer<String> renderer = new UppercaseRenderer();
```

The variable has the interface type `Renderer<String>`; the actual object has class `UppercaseRenderer`. Callers depend only on the interface contract, so it can be swapped with another class implementing `Renderer<String>` without changing every call site.

## 3. Method Signatures Must Match the Chosen Type Arguments

In `Renderer<T>`, the method is:

```java
String render(T value);
```

Once a class chooses `Renderer<String>`, the **matching implementation signature** is:

```java
@Override
public String render(String value) {
    return value.toUpperCase();
}
```

The snippet above is **an illustrative method**, which must reside inside a class that `implements Renderer<String>`. You cannot just replace the type parameter with `Object` and treat it as an equivalent implementation:

```java
// Intentionally invalid example; do not use as a runnable program:
final class WrongRenderer implements Renderer<String> {
    @Override
    public String render(Object value) {
        return value.toString();
    }
}
```

`render(Object)` does not override the `render(String)` method required by the `Renderer<String>` contract. Thus there is a compile error: `WrongRenderer` fails to implement the required abstract method and `@Override` also does not match. Even if `@Override` is removed, a method taking `Object` still does not become a method satisfying `Renderer<String>`.

**Practical rule:** open the interface declaration, substitute each type parameter with the type argument chosen in `implements`, and write the exact method to implement. For an interface with multiple methods, implement all remaining abstract methods or declare the class `abstract`.

Regarding visibility, methods declared in an interface are normally `public` under Java semantics. Therefore when implementing the `render` method, specify `public`; you cannot reduce access to `protected` or package-private.

## 4. Implementing Interfaces with Multiple Type Parameters

An interface can express both an input type and an output type:

```java
interface Converter<I, O> {
    O convert(I input);
}
```

`I` is the input type parameter, and `O` is the output type parameter. The implementing class specifies both arguments in exact order:

```java
final class TextLengthConverter implements Converter<String, Integer> {
    @Override
    public Integer convert(String input) {
        return input.length();
    }
}
```

Type parameter `I` corresponds to `String`; `O` corresponds to `Integer`. Therefore the method takes `String` and returns `Integer`.

### Runnable Example

Save the file **`MultiTypeInterfaceDemo.java`**:

```java
public class MultiTypeInterfaceDemo {
    interface Converter<I, O> {
        O convert(I input);
    }

    static final class TextLengthConverter
            implements Converter<String, Integer> {
        @Override
        public Integer convert(String input) {
            return input.length();
        }
    }

    static final class NumberLabelConverter
            implements Converter<Integer, String> {
        @Override
        public String convert(Integer input) {
            return "ID-" + input;
        }
    }

    public static void main(String[] args) {
        Converter<String, Integer> length = new TextLengthConverter();
        Converter<Integer, String> label = new NumberLabelConverter();

        Integer size = length.convert("Generics");
        String code = label.convert(42);

        System.out.println(size);
        System.out.println(code);
    }
}
```

Run commands:

```bash
javac -encoding UTF-8 MultiTypeInterfaceDemo.java
java MultiTypeInterfaceDemo
```

`stdout`:

```text
8
ID-42
```

Both classes use **the same interface** yet choose two different sets of type arguments. Swapping `<String, Integer>` to `<Integer, String>` changes the meaning and required signatures, not merely code presentation.

| Interface Type | Parameter Type of `convert` | Return Type of `convert` |
|---|---|---|
| `Converter<String, Integer>` | `String` | `Integer` |
| `Converter<Integer, String>` | `Integer` | `String` |
| `Converter<String, String>` | `String` | `String` |

Note that `int` is a primitive type and cannot be used directly as a generic argument; we use the wrapper class `Integer`. The expression `input.length()` returns `int` and is boxed into `Integer` upon returning from the method.

## 5. Comparing a Concrete-Typed Implementing Class and a Still-Generic Implementing Class

The two forms serve different purposes.

**Class implementing with a fixed type:**

```java
final class StringEcho implements Echo<String> {
    @Override
    public String echo(String value) {
        return value;
    }
}
```

**Class forwarding the type parameter:**

```java
final class GenericEcho<T> implements Echo<T> {
    @Override
    public T echo(T value) {
        return value;
    }
}
```

Both snippets above assume the interface:

```java
interface Echo<T> {
    T echo(T value);
}
```

`StringEcho` has locked in `String`; usage sites write `new StringEcho()` and **cannot** write `new StringEcho<Integer>()` because the class declares no type parameter.

`GenericEcho<T>` still carries the type parameter `T`; usage sites can write `new GenericEcho<String>()` or `new GenericEcho<Integer>()`. The `implements Echo<T>` syntax forwards the type relationship from the class to the interface.

### Complete Comparison Example

Save the file **`ConcreteVsGenericDemo.java`**:

```java
public class ConcreteVsGenericDemo {
    interface Echo<T> {
        T echo(T value);
    }

    static final class StringEcho implements Echo<String> {
        @Override
        public String echo(String value) {
            return value.toUpperCase();
        }
    }

    static final class GenericEcho<T> implements Echo<T> {
        @Override
        public T echo(T value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Echo<String> stringOnly = new StringEcho();
        Echo<String> genericString = new GenericEcho<>();
        Echo<Integer> genericNumber = new GenericEcho<>();

        System.out.println(stringOnly.echo("java"));
        System.out.println(genericString.echo("Java"));
        System.out.println(genericNumber.echo(17));
    }
}
```

Run:

```bash
javac -encoding UTF-8 ConcreteVsGenericDemo.java
java ConcreteVsGenericDemo
```

`stdout`:

```text
JAVA
Java
17
```

Which approach should you choose?

- Use `implements Echo<String>` if the class performs domain logic specific to **one fixed type**, such as string processing or a `Customer` entity.
- Use `class GenericEcho<T> implements Echo<T>` if the algorithm can operate identically across many types and the class itself does not need to know what `T` is.
- You can combine them: `class Child<U> implements Converter<String, U>` fixes the input type to `String` while allowing the output type `U` to vary. Only use this when business logic genuinely needs that flexibility.

This is a decision about **the generality level of the class**, not about runtime object types being duplicated per `T`.

## 6. Generic Interfaces Still Allow Multiple Methods and Default Methods

An interface is not limited to one method. When declaring `implements Repository<String>`, every occurrence of `T` in the contract must be understood consistently as `String`.

Example:

```java
interface Repository<T> {
    void save(T item);
    T latest();

    default String describe(T item) {
        return "Value: " + item;
    }
}
```

A class choosing `String` will have to implement `save(String)` and `String latest()`; `describe(String)` is a `default` method that already has a body, so the class can inherit the implementation without overriding. If overridden, the signature must still match the chosen type.

Save the file **`RepositoryDemo.java`**:

```java
public class RepositoryDemo {
    interface Repository<T> {
        void save(T item);
        T latest();

        default String describe(T item) {
            return "Value: " + item;
        }
    }

    static final class LastTextRepository implements Repository<String> {
        private String latest;

        @Override
        public void save(String item) {
            latest = item;
        }

        @Override
        public String latest() {
            return latest;
        }
    }

    public static void main(String[] args) {
        Repository<String> repository = new LastTextRepository();
        repository.save("Generics");

        System.out.println(repository.latest());
        System.out.println(repository.describe("Java"));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 RepositoryDemo.java
java RepositoryDemo
```

`stdout`:

```text
Generics
Value: Java
```

In the example, `Repository<String>` does not automatically persist data or add database access mechanisms. `LastTextRepository` merely holds one value in memory to illustrate type relationships; the name `Repository` here describes a learning contract, not a durable storage engine.

In particular, the implementation must uphold the method's meaning; generics only verifies the **type** of data, not business requirements such as whether data exists, is valid, or requires synchronization across threads.

## 7. Practical Example: `Comparable<Product>`

A common use of implementing a generic interface with a concrete type argument is `Comparable<T>`. A class can write `implements Comparable<Product>` to describe how to compare two `Product` objects.

Save the file **`ProductSortDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ProductSortDemo {
    record Product(String code, int price) implements Comparable<Product> {
        @Override
        public int compareTo(Product other) {
            int byPrice = Integer.compare(price, other.price());
            return byPrice != 0 ? byPrice : code.compareTo(other.code());
        }
    }

    public static void main(String[] args) {
        List<Product> products = new ArrayList<>(List.of(
            new Product("B", 20),
            new Product("A", 10),
            new Product("C", 20)
        ));

        products.sort(null);

        for (Product product : products) {
            System.out.println(product.code() + ":" + product.price());
        }
    }
}
```

Run on Java 17+:

```bash
javac -encoding UTF-8 ProductSortDemo.java
java ProductSortDemo
```

`stdout`:

```text
A:10
B:20
C:20
```

With `Comparable<Product>`, the required method is `int compareTo(Product other)`. If the price is lower, the method returns a negative value; if higher, a positive value; if equal in price, it also compares `code` for a deterministic ordering. `List.sort(null)` uses the natural ordering provided by the elements' `Comparable`.

The `record` example above is a Java data type supported since before Java 17; the syntax `record Product(...) implements Comparable<Product>` is completely valid. We need to distinguish `Comparable<T>`: the object defines its own natural ordering; whereas `Comparator<T>` is another interface for describing comparison rules external to the object.

The `Product` argument in `Comparable<Product>` lets the compiler prevent passing the wrong object type to `compareTo` through a type-checked API.

## 8. Inheritance and Multiple Interfaces: Limits to Remember

### 8.1. A Class Can Implement Multiple Different Generic Interfaces

Example:

```java
interface Named {
    String name();
}

interface Identifiable<T> {
    T id();
}

final class Account implements Named, Identifiable<Long> {
    @Override
    public String name() {
        return "Primary";
    }

    @Override
    public Long id() {
        return 100L;
    }
}
```

This is an **illustrative group of declarations**, which can be placed in a single file in the same package. `Account` implements `Named` and `Identifiable<Long>`. An interface without type parameters and an interface with type parameters can be combined normally, provided the contracts do not conflict.

### 8.2. Cannot Inherit the Same Generic Interface with Two Different Type Arguments

Consider:

```java
interface Handler<T> {
    void handle(T value);
}

interface TextHandler extends Handler<String> { }
interface NumberHandler extends Handler<Integer> { }

// Invalid:
// final class Both implements TextHandler, NumberHandler { ... }
```

Even though one might think writing `handle(String)` and `handle(Integer)` would suffice, Java does not allow one type to inherit two different parameterizations of **the same generic interface** such as `Handler<String>` and `Handler<Integer>`. After *type erasure*, these type relationships also have conflict issues; language rules reject that inheritance right at compile time.

If the application genuinely needs to handle two types, you can declare two methods with **different names** in independent interfaces, or use one interface taking a broader type with clear dispatch logic. Do not drop generics and use raw types to mask this design flaw.

### 8.3. A Class Can Extend a Base Class and Implement Interfaces

In Java, a class can only `extends` one superclass, yet can `implements` multiple interfaces:

```java
abstract class Base {
    String prefix() {
        return "ID:";
    }
}

interface Formatter<T> {
    String format(T value);
}

final class IntegerFormatter extends Base implements Formatter<Integer> {
    @Override
    public String format(Integer value) {
        return prefix() + value;
    }
}
```

The declarations above are **standalone illustrative code**. The proper order is `extends Base implements Formatter<Integer>`. The generic interface is still implemented with a concrete type argument `Integer`.

## 9. Type Invariance (`invariance`) Still Applies to Generic Interfaces

A common mistake is thinking that because `String extends Object`, `Renderer<String>` can be passed where `Renderer<Object>` is expected. In Java, this relationship **does not exist by default**:

```java
Renderer<String> strings = new UppercaseRenderer();

// Renderer<Object> allObjects = strings; // Invalid: incompatible types
```

`Renderer<String>` and `Renderer<Object>` are two different parameterizations of `Renderer`; Java generics are invariant by default. Allowing the assignment above would let callers pass `Object`s that are not `String` into the implementing class, breaking its contract.

For an interface that only **consumes** values of type `T` such as `Renderer<T>`, the wildcard `? super String` can be useful in API signatures accepting renderers that can handle `String`; for an interface that only **provides** values of type `T`, the wildcard `? extends T` is usually more appropriate. This is an extension direction when designing APIs that consume or produce data; you do not yet need to apply wildcards to `UppercaseRenderer` for it to properly implement `Renderer<String>`.

## 10. What Happens at Runtime: Type Erasure and Bridge Methods

Java generics primarily generates type checks **at compile time**. After *type erasure*, the JVM does not have a separate runtime copy of the interface for each argument like `Renderer<String>` and `Renderer<Integer>`.

Consider a compact example:

```java
interface Source<T> {
    T get();
}

final class StringSource implements Source<String> {
    @Override
    public String get() {
        return "Java";
    }
}
```

At the source-code level, `Source<String>.get()` returns `String`. After erasure, the interface signature essentially becomes `Object get()`. To preserve polymorphism of the overridden method, the Java compiler can generate a synthetic **bridge method** in the implementing class, typically having signature `Object get()` and forwarding to `String get()`.

Bridge methods are an automatic mechanism to keep override behavior working when erasure changes JVM signatures, **not** methods programmers must write manually. You can observe this by saving the two declarations above in `StringSource.java` (without `public`), then running:

```bash
javac -encoding UTF-8 StringSource.java
javap -p -c StringSource
```

The `javap` output includes bytecode and compiled methods; in this case you will see a `get()` method returning `java.lang.String` and a bridge `get()` method returning `java.lang.Object`. Depending on display options, use `javap -v StringSource` to view the `ACC_BRIDGE` and `ACC_SYNTHETIC` flags.

From an API usage perspective, the key point remains: declaring `implements Source<String>` lets the compiler check `String` at call sites. However, when legacy code uses raw types or performs unchecked casts, `ClassCastException` can still occur. Therefore avoid raw types and inspect `unchecked` warnings.

## 11. Common Mistakes When Implementing Concrete Type Arguments

| Error | Cause | How to Fix |
|---|---|---|
| `implements Renderer<String>` yet writing `render(Object)` | Wrong signature to implement: `render(String)`. | Override `public String render(String value)` and add `@Override`. |
| `implements Converter<String, Integer>` yet returning `String` | Return type does not match the second argument `Integer`. | Return `Integer` or adjust the contract's type arguments. |
| Writing `class X implements Renderer<T>` when the class does not declare `T` | `T` does not automatically exist in the class scope. | Use `class X<T> implements Renderer<T>` or fix `Renderer<String>`. |
| Writing `implements Renderer<int>` | Generics only accept reference types as arguments. | Use `Renderer<Integer>`. |
| Writing `new UppercaseRenderer<String>()` | `UppercaseRenderer` is not a generic class. | Use `new UppercaseRenderer()`. |
| Giving the implementing method package-private visibility | Cannot reduce visibility of a public interface method. | Declare the method `public`. |
| Thinking `Renderer<String>` can be assigned to `Renderer<Object>` | Java generics are invariant. | Keep the exact contract or design wildcards at consumption sites if truly needed. |
| Implementing both `Handler<String>` and `Handler<Integer>` through inheritance branches | Cannot inherit the same generic interface with two different type arguments. | Design independent interfaces or change the processing model. |
| Omitting type arguments: `implements Renderer` | Raw types lose type-checking benefits and can produce warnings. | Specify `Renderer<String>` or a validly declared type parameter. |
| Assuming `implements Interface<String>` lets runtime check all generic parameters | Type erasure removes most type info, disallowing `instanceof Interface<String>`. | Maintain compile-time safety, and validate data at untrusted boundaries. |

If a class fails to override all abstract methods under the proper contract, the compiler requires the class to be `abstract` or to supply the missing methods. Do not suppress warnings, use unchecked casts, or remove `@Override` to hide errors.

## 12. Process for Implementing a Generic Interface Properly

When faced with the requirement "write a class implementing `SomeInterface<ConcreteType>`," follow these steps in order:

1. **Read the interface declaration**: identify the number of type parameters, their order, bounds such as `T extends Number`, and the list of abstract/default methods.
2. **Choose meaningful business type arguments**: for example `String`, `Order`, `Integer`, `Converter<Request, Response>`. Must use reference types and satisfy all bounds.
3. **Write `implements` with full type arguments**: `class TextHandler implements Handler<String>`.
4. **Substitute types in the contract**: every `T` in methods is interpreted as `String`; for `<I,O>`, substitute according to the exact order of the two arguments.
5. **Implement the required methods**: specify `public`, `@Override`, exact signature, and business logic inside.
6. **Use through the interface type** on the caller side if appropriate: `Handler<String> handler = new TextHandler();`.
7. **Compile and check warnings**: `javac -Xlint:rawtypes,unchecked ...`; watch out for signature errors, raw types, bounds, and unsafe casts.
8. **Test both valid and wrong-typed values at compile time**: wrong types must be rejected at call sites of the type-bound API; runtime still needs to enforce `null` checks and domain-specific business rules.

### Self-Check Exercises

**Question 1.** Given `interface Mapper<I, O> { O map(I input); }`, which method must exist in a class that `implements Mapper<String, Long>`?

**Question 2.** Why can `class TextMapper implements Mapper<String, Long>` not simply declare `Object map(Object x)`?

**Question 3.** Is `class CommonMapper<T> implements Mapper<T, String>` a generic class? Can callers declare `CommonMapper<Integer>`?

**Question 4.** Why does Java reject a class being both `Handler<String>` and `Handler<Integer>` via two inherited interfaces?

**Question 5.** Does `StringSource` in the *type erasure* section have to write `Object get()` manually to be used via `Source<String>`?

**Guided answers:** (1) `public Long map(String input)`. (2) The signature after binding types requires a `String` parameter and a `Long` result; `Object` does not satisfy that contract. (3) Yes; `T` remains a type parameter of the class, while the output is fixed to `String`. (4) The same generic interface cannot be inherited with two different type arguments. (5) No; the compiler handles the necessary bridge method during compilation.

**Remember:** `implements Interface<ConcreteType>` is how to **specialize a generic interface's contract at an implementing class**. Replace type parameters with the chosen type arguments in method signatures, use `public` and `@Override`, and then use the object through the parameterized interface type so the compiler protects type relationships right as you write code.
