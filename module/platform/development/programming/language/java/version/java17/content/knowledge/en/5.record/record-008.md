# Generic Records and Implementing Interfaces in Java 17

**Topic:** Java 17 → Record  
**Contents:** Declaring records with generic type parameters (*generic records*), using type bounds (*type bounds*), and having records implement one or more interfaces, including generic interfaces.

In Java 17, a **record** is a form of class declaration for objects primarily meant to carry data. A record can have **type parameters** such as `<T>` or `<K, V>`, just like a regular Java class, and can **`implements` interfaces** to participate in shared processing contracts. Records have been a standard feature since Java 16, so all examples in this lesson use **stable Java 17 syntax**, without needing `--enable-preview` or external libraries beyond the JDK.

## 1. Quick Review: What Does a Record Generate?

Consider a simple record:

~~~java
record Book(String title, int pages) {
}
~~~

This declaration defines two **record components**: `title` and `pages`. The compiler provides the corresponding members:

- Storage fields matching the components, with `private final` modifiers.
- A primary constructor (*canonical constructor*) taking component values in declaration order.
- Accessor methods `title()` and `pages()`. Records do not auto-generate `getTitle()`-style getters.
- `equals(Object)`, `hashCode()`, and `toString()` methods following record data semantics, unless validly redeclared.

Example:

~~~java
Book book = new Book("Java 17", 320);
System.out.println(book.title()); // Java 17
System.out.println(book.pages()); // 320
System.out.println(book);         // Book[title=Java 17, pages=320]
~~~

A record **cannot be subclassed by another class** because records are implicitly `final`. A record itself always inherits `java.lang.Record`, so it cannot `extends` another superclass. Even so, a record **is allowed to implement interfaces** and can declare methods, constructors, `static` fields, or `static` methods per Java rules.

## 2. Generic Record Syntax: `record Name<T>(...)`

A generic record places its type parameter list **immediately after the record name**:

~~~java
record Box<T>(T value) {
}

record Pair<K, V>(K key, V value) {
}
~~~

Where:

| Element | Role |
| --- | --- |
| `record` | Declares a record. |
| `Box<T>` | `T` is a type parameter; the concrete type is specified at usage time. |
| `T value` | Component `value` of type `T`. |
| `Pair<K, V>` | A record with two independent type parameters, often used for key–value pairs. |
| `key()`, `value()` | Record-generated accessors returning the declared component types using compile-time type info. |

### 2.1. Runnable Example: One Record for Multiple Data Types

Create **`GenericRecordDemo.java`**:

~~~java
import java.util.Objects;

public class GenericRecordDemo {
    record Box<T>(T value) {
        Box {
            Objects.requireNonNull(value, "value");
        }
    }

    record Pair<K, V>(K key, V value) {
    }

    public static void main(String[] args) {
        Box<String> title = new Box<>("Java 17");
        Box<Integer> count = new Box<>(17);
        Pair<String, Integer> course = new Pair<>("Lessons", 8);

        String text = title.value();
        int number = count.value();

        System.out.println(text);
        System.out.println(number);
        System.out.println(course.key() + ": " + course.value());
    }
}
~~~

Compile and run with **JDK 17**:

~~~shell
javac --release 17 GenericRecordDemo.java
java GenericRecordDemo
~~~

Output:

~~~text
Java 17
17
Lessons: 8
~~~

**Explanation:**

1. `Box<String>` holds `String`; `title.value()` has compile-time type `String`.
2. `Box<Integer>` holds `Integer`; `int number = count.value()` works via **unboxing** from `Integer` to `int`.
3. `new Box<>(...)` uses the diamond operator `<>` so Java infers type arguments from the context and constructor arguments.
4. `Pair<String, Integer>` has two components with two independent types.
5. The block `Box { ... }` is a **compact canonical constructor**; it validates the `value` parameter before Java automatically assigns it to the corresponding component field.

You cannot use primitive types as type arguments; for example, `Box<int>` is invalid syntax. Use wrapper types like `Integer`, `Long`, or `Double`.

### 2.2. Declaring Generic Methods in a Record

A generic record can also provide utility methods for creating instances:

~~~java
record Box<T>(T value) {
    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

Usage:

~~~java
Box<String> a = Box.of("Hello");
Box<Integer> b = Box.of(42);
~~~

`T` is a type parameter of **the record itself**; `U` is an independent type parameter of the **static method** `of`. A static method cannot directly use an instance's `T` because no instance is attached to a static call.

## 3. Type Bounds on Record Type Parameters

Just like generic classes, generic records can restrict which types are allowed:

~~~java
record Measurement<T extends Number>(T amount, String unit) {
}
~~~

`T extends Number` states that `T` must be `Number` or a valid subtype of `Number`, such as `Integer`, `Long`, `Double`, or `BigDecimal`.

~~~java
Measurement<Integer> steps = new Measurement<>(1200, "steps");
Measurement<Double> distance = new Measurement<>(2.5, "km");

double total = steps.amount().doubleValue();
System.out.println(total); // 1200.0
~~~

Conversely, `Measurement<String>` is invalid because `String` is not a subtype of `Number`. This check occurs **at compile time**.

A more general bound is commonly used for comparable data:

~~~java
record Ranked<T extends Comparable<? super T>>(T value) {
    int compareTo(Ranked<T> other) {
        return value.compareTo(other.value());
    }
}
~~~

The syntax `Comparable<? super T>` allows `T` to be compared by a `Comparable` accepting `T` or a supertype of `T`. This is often more flexible than plain `Comparable<T>`. Type bounds ensure calling `compareTo` is type-safe at compile time.

### 3.1. Generics Preserve Type Checking

The following declarations have **distinct generic types**:

~~~java
Box<Integer> integerBox = new Box<>(10);
Box<Number> numberBox = new Box<>(10);
~~~

Even though `Integer` is a subtype of `Number`, **`Box<Integer>` is not a subtype of `Box<Number>`**. Java generics are **invariant in their type arguments** (*invariance*).

Therefore, the following statement is invalid:

~~~java
// Invalid: Box<Integer> cannot be assigned to Box<Number>.
// Box<Number> other = integerBox;
~~~

If a method only needs to **read** a number from a Box, you can use a wildcard:

~~~java
static double readNumber(Box<? extends Number> box) {
    return box.value().doubleValue();
}
~~~

The method accepts `Box<Integer>`, `Box<Double>`, and any Box whose type argument extends `Number`.

## 4. How Do Records Implement Interfaces?

A record can write `implements InterfaceName` after its component list:

~~~java
interface Named {
    String name();
}

record User(String name, int age) implements Named {
}
~~~

Even though `User` does not explicitly declare a `name()` method in its body, **the `name()` accessor generated from component `String name` already satisfies the `Named.name()` contract**. Because the signature and return type match, there is no need to rewrite the method just to return the component.

A `User` object can be used through the interface type:

~~~java
Named named = new User("Lan", 25);
System.out.println(named.name()); // Lan
~~~

This is **polymorphism**: consumer code cares that the object fulfills `Named`, without needing to know it is a `User` record.

### 4.1. Complete Example: Generic Record Implementing a Generic Interface

Create **`GenericInterfaceDemo.java`**:

~~~java
import java.util.Objects;

public class GenericInterfaceDemo {
    interface Identifiable<ID> {
        ID id();
    }

    record Entity<ID, T>(ID id, T payload)
            implements Identifiable<ID> {

        Entity {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(payload, "payload");
        }
    }

    static <ID> void printId(Identifiable<ID> item) {
        System.out.println("ID: " + item.id());
    }

    public static void main(String[] args) {
        Entity<Long, String> first = new Entity<>(1001L, "Java Course");
        Entity<String, Integer> second = new Entity<>("LESSON-1", 25);

        printId(first);
        printId(second);

        System.out.println(first.payload());
        System.out.println(second.payload());
    }
}
~~~

Run:

~~~shell
javac --release 17 GenericInterfaceDemo.java
java GenericInterfaceDemo
~~~

Output:

~~~text
ID: 1001
ID: LESSON-1
Java Course
25
~~~

**Breaking down the declaration:**

~~~java
record Entity<ID, T>(ID id, T payload) implements Identifiable<ID>
~~~

- `ID`: type of the identifier, e.g., `Long` or `String`.
- `T`: type of the payload, independent of the identifier type.
- `implements Identifiable<ID>`: commits the record to providing method `ID id()`.
- Component `ID id` causes the compiler to generate a matching `id()` accessor; no manual implementation needed.
- Method `printId` accepts any object implementing `Identifiable<ID>`, including records.

For generic interfaces, type arguments must be compatible. For example, `Entity<Long, String>` implements `Identifiable<Long>`, not `Identifiable<String>`.

## 5. When an Accessor Does Not Match an Interface Method Name

Records only generate accessors matching **exact component names**. If an interface requires a different method name, the record must implement it explicitly:

~~~java
interface DisplayName {
    String getDisplayName();
}

record Person(String name) implements DisplayName {
    @Override
    public String getDisplayName() {
        return name();
    }
}
~~~

Here, component `name` generates `name()`; it **does not automatically generate** `getDisplayName()`. Therefore, overriding `getDisplayName()` is required.

If an interface requires `String name()`, `record Person(String name)` can satisfy it directly. Conversely, if the component is `Object name`, the accessor returns `Object` and cannot satisfy a method requiring return type `String`.

| Interface Requirement | Record Component | Result |
| --- | --- | --- |
| `String name()` | `String name` | Auto-generated accessor matches. |
| `Number amount()` | `Integer amount` | Covariant return type `Integer` can satisfy `Number`. |
| `String getName()` | `String name` | Must manually write `getName()`. |
| `String name()` | `Object name` | Auto-generated accessor does not have a compatible return type. |

Interface methods can be `default`, `static`, or `private` according to Java interface rules. When a record implements an interface, it can inherit suitable `default` methods or override behavior itself. Override rules remain the same as for other Java classes.

## 6. Records Can Implement Multiple Interfaces

A record cannot extend an arbitrary superclass, but it can implement **multiple interfaces**:

~~~java
interface HasValue<T> {
    T value();
}

interface Describable {
    String description();
}

record Product<T>(String code, T value)
        implements HasValue<T>, Describable {

    @Override
    public String description() {
        return code() + " = " + value();
    }
}
~~~

Usage:

~~~java
Product<Integer> product = new Product<>("SKU-15", 150);

HasValue<Integer> valueView = product;
Describable descriptionView = product;

System.out.println(valueView.value());          // 150
System.out.println(descriptionView.description()); // SKU-15 = 150
~~~

**What is auto-generated vs. what must be written manually?**

| Member | Provided by Record? | Notes |
| --- | --- | --- |
| `code()` and `value()` | Yes | Accessors for the two components. |
| `HasValue<T>.value()` | Satisfied by `value()` | No second `value` method needed. |
| `Describable.description()` | No | Must write manually unless the interface supplies a default implementation. |
| `equals`, `hashCode`, `toString` | Yes | Generated from components. |
| `setValue(...)` | No | Records do not provide setters and forbid reassigning component fields. |

This design is useful when passing the same object through multiple APIs: a value-reading API only needs `HasValue<T>`, while a display API only needs `Describable`.

## 7. Adding Behavior and Data Constraints to Generic Records

A record is not just a one-line declaration. It can contain validation logic and business methods, as long as it follows record rules.

Example **`ValidatedRecordDemo.java`**:

~~~java
import java.util.Objects;

public class ValidatedRecordDemo {
    interface HasCode {
        String code();
    }

    record CatalogItem<T>(String code, T details)
            implements HasCode {

        CatalogItem {
            Objects.requireNonNull(code, "code");
            Objects.requireNonNull(details, "details");

            code = code.trim();
            if (code.isEmpty()) {
                throw new IllegalArgumentException("Code must not be blank");
            }
        }

        String display() {
            return code() + ": " + details();
        }
    }

    public static void main(String[] args) {
        CatalogItem<Integer> item =
            new CatalogItem<>("  ITEM-9  ", 120);

        HasCode contract = item;
        System.out.println(contract.code());
        System.out.println(item.display());
    }
}
~~~

~~~shell
javac --release 17 ValidatedRecordDemo.java
java ValidatedRecordDemo
~~~

Output:

~~~text
ITEM-9
ITEM-9: 120
~~~

In the compact constructor `CatalogItem { ... }`, you can validate and **reassign the parameter** `code` to normalize data before the component field is implicitly initialized. You must not assign directly to the component field as `this.code = ...` inside a compact constructor. In a full canonical constructor, field assignment follows that constructor's own rules.

`HasCode.code()` is satisfied by the record's generated `code()` accessor. The author-declared `display()` method adds display behavior without interfering with using the record through the interface.

## 8. Generic Records, Collections, and Shallow Immutability

A common misconception is: "a record has `final` fields, so all of its contents are immutable." In reality, a record guarantees **component references cannot be reassigned after creation**, yet **referenced objects can still be modified**.

Consider:

~~~java
import java.util.List;

record Group<T>(List<T> members) {
}
~~~

If a mutable `ArrayList` is passed into `Group`, other code can mutate that list; `Group.members()` also returns the same reference. This is **shallow immutability**, not deep immutability.

When designing a record holding a collection and wanting to prevent structural mutations through external references, copy defensively:

~~~java
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

record Batch<T>(List<T> items) implements Iterable<T> {
    Batch {
        items = List.copyOf(Objects.requireNonNull(items, "items"));
    }

    @Override
    public Iterator<T> iterator() {
        return items.iterator();
    }
}
~~~

Usage:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> source = new ArrayList<>(List.of("A", "B"));
Batch<String> batch = new Batch<>(source);

source.add("C");
System.out.println(batch.items()); // [A, B]

for (String value : batch) {
    System.out.println(value);
}

// batch.items().add("D"); // Throws UnsupportedOperationException.
~~~

Explaining the two cooperating mechanisms:

1. `List.copyOf(...)` produces a list that cannot be modified directly, taking a snapshot of elements at copy time (or reusing an existing unmodifiable list).
2. `Iterable<T>` allows `Batch<T>` to be used in `for-each` loops; the record must write `iterator()` explicitly because that name is not a component accessor.

`List.copyOf` rejects `null` elements. Define your data policy upfront if inputs can contain `null`.

**Limitation:** `List.copyOf` does not deep-copy each `T` object. If `T` is a mutable type, inner contents of elements can still be mutated. Achieving deep immutability also requires appropriate rules for the element type.

## 9. Generic Records and Type Erasure

Java generics use **type erasure**. At runtime, there is not one class for `Box<String>` and another class for `Box<Integer>`; both use the same `Box` class.

Example:

~~~java
Box<String> text = new Box<>("Java");
Box<Integer> number = new Box<>(17);

System.out.println(text.getClass() == number.getClass()); // true
~~~

Therefore, you cannot check the concrete type argument `String` using an `instanceof Box<String>` expression:

~~~java
Object value = new Box<>("Java");

// Invalid: cannot check concrete type argument String this way.
// if (value instanceof Box<String> box) { ... }
~~~

However, you can match the record type using a wildcard:

~~~java
if (value instanceof Box<?> box) {
    System.out.println(box.value());
}
~~~

This is **pattern matching for `instanceof`**, which is standard and available in Java 17. Matching checks that the object is a `Box`; it cannot recover the concrete type argument erased at runtime.

**Design impact:** Do not treat `T` as if runtime always knows its concrete class. If type metadata is needed at runtime, design it explicitly, such as passing a `Class<T>` or an adapter capable of handling the corresponding type.

## 10. Combining Generic Records with Sealed Interfaces

An application can use a generic interface to represent a result with data of type `T`, while directly restricting variants with `sealed`. Both **records** and **sealed interfaces** are standard features in Java 17.

Create **`ResultRecordDemo.java`**:

~~~java
public class ResultRecordDemo {
    sealed interface Result<T> permits Success, Failure {
    }

    record Success<T>(T value) implements Result<T> {
    }

    record Failure<T>(String reason) implements Result<T> {
    }

    static <T> String describe(Result<T> result) {
        if (result instanceof Success<?> success) {
            return "Success: " + success.value();
        }
        if (result instanceof Failure<?> failure) {
            return "Failure: " + failure.reason();
        }
        throw new IllegalStateException("Unsupported result type");
    }

    public static void main(String[] args) {
        Result<String> first = new Success<>("Saved");
        Result<String> second = new Failure<>("Access denied");

        System.out.println(describe(first));
        System.out.println(describe(second));
    }
}
~~~

~~~shell
javac --release 17 ResultRecordDemo.java
java ResultRecordDemo
~~~

Output:

~~~text
Success: Saved
Failure: Access denied
~~~

In the example:

- `Result<T>` is a generic sealed interface permitting only two **direct** subtypes: `Success` and `Failure`.
- `Success<T>` and `Failure<T>` are generic records directly implementing `Result<T>`; records are implicitly `final`, satisfying sealed hierarchy rules.
- `Failure<T>` still declares type parameter `T` so a failure result can be used through the same `Result<T>` contract, even though component `reason` does not need type `T`.
- In `instanceof`, `Success<?>` and `Failure<?>` are used because Java cannot check the concrete type argument `T` at runtime.

**Pattern matching in `switch`** is not used here: that feature was still in preview in Java 17. The `if`/`instanceof` chains in the example use standard syntax.

This pattern fits well when you want to model a controlled set of outcomes while allowing the success payload to take many types.

## 11. Common Mistakes and How to Avoid Them

### 11.1. Forgetting Type Arguments or Using Raw Types

~~~java
record Box<T>(T value) {
}

// Raw type: compiles in some contexts,
// but loses type-checking benefits and may emit warnings.
Box raw = new Box("text");

Box<String> typed = new Box<>("text"); // Recommended.
~~~

In new code, declare concrete type arguments or use `var` when the type is clearly inferred from the expression. Avoid raw types because they can lead to unsafe casts.

### 11.2. Confusing Accessors with JavaBeans-Convention Getters

~~~java
record Customer(String name) {
}

Customer customer = new Customer("Minh");
System.out.println(customer.name()); // Valid

// customer.getName(); // Invalid: records do not auto-generate getName().
~~~

If an interface or framework API requires `getName()`, declare that method or configure an appropriate adapter.

### 11.3. Trying to Subclass a Record or Have a Record Extend a Regular Class

~~~java
record Point(int x, int y) {
}

// Invalid: records are final, cannot extends Point.
// class ColoredPoint extends Point {}

// Invalid: records already inherit java.lang.Record.
// record SpecialPoint(int x, int y) extends Point {}
~~~

To share behavior or contracts across multiple records, use **interfaces**. If a class hierarchy with inherited state and logic is needed, consider regular classes.

### 11.4. Having a Record Implement an Interface Without Satisfying Its Methods

~~~java
interface Printable {
    String print();
}

// Invalid: component named value only generates value(), not print().
// record Note(String value) implements Printable {}

record Note(String value) implements Printable {
    @Override
    public String print() {
        return value();
    }
}
~~~

A record is a concrete class, so it must satisfy all abstract methods of its interfaces via compatible accessors, manually written methods, or inherited default implementations per Java rules.

### 11.5. Believing `final` Means Deeply Immutable Data

~~~java
import java.util.List;

record Tasks(List<String> values) {
}
~~~

The list can still be modified if the record holds a reference to a mutable list. Use defensive copying and decide how mutable elements are handled when designing data types.

### 11.6. Treating Type Erasure as Runtime Generic Type Checking

`new Box<>(42)` and `new Box<>("text")` both create objects of class `Box`. Java generics support compile-time type checking; do not rely on `instanceof Box<String>` to distinguish payloads. Use wildcards, inspect concrete values when needed, or design a model with explicit type metadata.

## 12. When Should You Combine Generic Records and Interfaces?

| Need | Design Suggestion | Benefit |
| --- | --- | --- |
| Wrapping a value of arbitrary type | `record Box<T>(T value)` | Preserves concrete types, reduces manual casts. |
| Representing a multi-typed pair of values | `record Pair<K, V>(K key, V value)` | Compact, clear accessors. |
| Multiple object types all have identifiers | `interface Identifiable<ID>`; record `implements Identifiable<ID>` | Consumers work via the identifier contract. |
| Multiple data types can be described or displayed | Record `implements Describable` | Attaches clear behavior to data objects. |
| Item list exposed via an interface | `record Batch<T>(List<T> items) implements Iterable<T>` | Usable with `for-each`, while defining collection protection policy. |
| Processing result with multiple variants and diverse payloads | `sealed interface Result<T>` and implementing generic records | Bounds the outcome set while preserving payload type checking. |

A generic record fits well when the data structure has stable semantics and most of the object's behavior comes from its components. If an object needs a continuously changing lifecycle, private internal state, complex class inheritance logic, or setter-based update flows, a regular class may fit better.

## 13. Applied Practice Exercise

**Requirement:** Build a `Response<T>` type carrying data `T` and an HTTP status code; this type must implement `HasStatus` so external code can read the status. Upon creation, the status code must be between 100 and 599; the payload must not be `null`.

**Suggested Solution:**

~~~java
import java.util.Objects;

public class ResponseDemo {
    interface HasStatus {
        int status();
    }

    record Response<T>(int status, T body) implements HasStatus {
        Response {
            if (status < 100 || status > 599) {
                throw new IllegalArgumentException("Invalid HTTP status");
            }
            Objects.requireNonNull(body, "body");
        }
    }

    static void showStatus(HasStatus value) {
        System.out.println("HTTP " + value.status());
    }

    public static void main(String[] args) {
        Response<String> text = new Response<>(200, "OK");
        Response<Integer> number = new Response<>(201, 123);

        showStatus(text);
        showStatus(number);
        System.out.println(text.body());
    }
}
~~~

~~~shell
javac --release 17 ResponseDemo.java
java ResponseDemo
~~~

Output:

~~~text
HTTP 200
HTTP 201
OK
~~~

**Explain to yourself:** Why is there no need to rewrite `status()`? Why can both `Response<String>` and `Response<Integer>` be passed to `showStatus(HasStatus)`? What happens if you create `new Response<>(700, "invalid")` or pass `null` as `body`?

The answers lie in the three rules covered: the record's `status()` accessor satisfies the interface, both objects implement `HasStatus`, and the compact constructor rejects invalid data.

## 14. Takeaways and References

- **Generic records** use `record Name<T>(T component)`, supporting multiple type parameters and type bounds just like generic classes.
- Records can **`implements` one or more interfaces** (including generic interfaces), but cannot `extends` arbitrary classes because they always inherit `java.lang.Record` and are `final`.
- Component-generated accessors can **directly satisfy** an interface method if the name and return type are compatible; other methods must be supplied per the interface contract.
- `record` provides data semantics and `final` component fields, yet **does not guarantee deep immutability** for referenced collections or mutable objects.
- Java generics have **type erasure**. Type arguments are checked at compile time; `instanceof Box<?>` is valid while `instanceof Box<String>` is not a valid runtime check.
- All examples use standard **Java 17** features and require no preview/incubator flags.

**Official Sources:**

1. [JEP 395 — Records](https://openjdk.org/jeps/395): specification direction and finalization of records.
2. [Java Language Specification 17 — Record Classes (§8.10)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): structure, components, constructors, generic records, and record constraints.
3. [Java Language Specification 17 — Type Parameters (§4.4)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): type parameters and type bounds.
4. [Java Language Specification 17 — Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): method contracts and interface implementation rules.
5. [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): base superclass of all records.

When combining generic records and interfaces, design **the data the record carries**, **the bounded type parameters**, and **the contracts the record commits to fulfilling** as three clear decisions. That keeps Java 17 code concise, type-safe, and easy to extend through interfaces without relying on class inheritance.
