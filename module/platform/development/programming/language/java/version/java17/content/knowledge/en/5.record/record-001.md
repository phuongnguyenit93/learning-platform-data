# Purpose of `record` and Its Relationship to Data-Carrying Classes in Java 17

## 1. Why Does Java Have `record`?

In many programs, we need a type solely to **carry a group of data with clear names and types**. For example, a coordinate consisting of `x` and `y`; an invoice line consisting of a product code, quantity, and unit price; or a statistical result consisting of a total count and an average value. Objects of this kind are typically created with a constructor, read through methods, compared by content, and printed for inspection.

Before `record`, a data-carrying Java class often required a lot of boilerplate code:

- Data fields, usually `private final`.
- A constructor to accept and assign the data.
- Methods to read each field.
- `equals(Object)` and `hashCode()` to compare by content and use as keys in collections.
- `toString()` for a readable representation of the object.

If a class truly only represents a group of data, the volume of this code can outweigh the part that describes the meaning of the data. Using an IDE to generate code reduces typing, but still leaves many methods to maintain when adding, renaming, or removing fields.

**`record`** is designed to directly describe a data-carrying type: the author declares the **data components** (*record components*) right in the declaration header; the compiler generates the corresponding standard members. It makes the code shorter and clearly expresses the type's contract: "which data components characterize this object?".

`record` is a special form of **class in Java**, not a primitive type or a data structure outside the object model. Records were standardized in Java 16 (JEP 395), so **Java 17 uses records as a stable feature, without needing to enable preview**.

## 2. From a Regular Data-Carrying Class to `record`

Consider a value representing a two-dimensional coordinate. Written as a regular class:

```java
import java.util.Objects;

public final class Point {
    private final int x;
    private final int y;

    public Point(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() {
        return x;
    }

    public int y() {
        return y;
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) return true;
        if (!(obj instanceof Point other)) return false;
        return x == other.x && y == other.y;
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y);
    }

    @Override
    public String toString() {
        return "Point[x=" + x + ", y=" + y + "]";
    }
}
```

With a record, the corresponding idea is declared concisely:

```java
public record Point(int x, int y) {}
```

The two snippets are **two ways of building a data-carrying type with a similar contract**, not two declarations used simultaneously in the same project. In the record version, `x` and `y` are **record components**. From them, Java provides:

- Corresponding storage fields, which are `private final`.
- A canonical constructor accepting the components in the order `(int x, int y)`.
- Accessor methods `x()` and `y()`.
- `equals(Object)`, `hashCode()`, and `toString()` based on the declared components.

Usage example:

```java
Point a = new Point(3, 5);
Point b = new Point(3, 5);

System.out.println(a.x());       // 3
System.out.println(a.y());       // 5
System.out.println(a.equals(b));  // true
System.out.println(a == b);       // false
System.out.println(a);            // Point[x=3, y=5]
```

What matters is not just fewer lines of code: the declaration `record Point(int x, int y)` already makes clear the **two components that define the data** of `Point`.

### Quick Comparison

| Aspect | Regular Data-Carrying Class | Record |
|---|---|---|
| Data declaration | Manually declare fields and API | Record header declares components |
| Constructor | Written manually | Has a canonical constructor, customizable |
| Data access | Defined manually, often `getX()` or `x()` | Default accessor has the same name as component: `x()` |
| Content comparison | Manually write `equals()`, `hashCode()` if needed | Provided by default based on components |
| String representation | Manually write `toString()` if needed | Has a default `toString()` |
| Mutating fields after creation | Decided by author; can be mutable | Component fields cannot be reassigned |
| Inheriting another class | Can `extends` a suitable class | Cannot `extends` an arbitrary class; implicitly inherits `java.lang.Record` |
| Allowing subclasses | Depends on `final` and other design choices | A record itself is `final` |
| Responsibilities and behavior | Flexible, can hold multiple internal states | Used for data models exposed via components; can still declare business methods |

**Not every class with little code should become a record.** Choosing a record is a data modeling and API contract decision, not merely a syntactic shortcut.

## 3. A Record Is a Class with a Clear Data Contract

The declaration:

```java
record Book(String isbn, String title, int pages) {}
```

specifies three components in order: `isbn`, `title`, `pages`. The components are a public part of the record's shape. Renaming, reordering, or changing the type of a component can affect the constructor, accessors, object representation, and calling code elsewhere.

### 3.1. Record Components and Accessors

Each component generates a read method with the **exact component name**, without a `get` prefix:

```java
Book book = new Book("978-1", "Learning Java", 320);
String id = book.isbn();
int length = book.pages();
```

This is an important difference to know when migrating from standard JavaBeans to records. Libraries, serialization tools, or frameworks may rely on `getIsbn()`-style getters, setters, or a no-arg constructor; record support depends on the specific version and integration mechanism. You should not assume every data-carrying class used in a framework can be turned into a record without impacting the API.

### 3.2. Constructor, `equals`, `hashCode`, `toString`

For a record without special body declarations, the compiler provides a canonical constructor taking all components. Java also provides `equals`/`hashCode` based on component contents and a `toString` format reflecting the type name, component names, and values.

```java
Book a = new Book("A-1", "Java", 200);
Book b = new Book("A-1", "Java", 200);

System.out.println(a.equals(b));              // true
System.out.println(a.hashCode() == b.hashCode()); // true
System.out.println(a); // Example: Book[isbn=A-1, title=Java, pages=200]
```

Two records `a` and `b` can be **two distinct objects** yet equal in content. Therefore:

- `equals()` expresses equivalence based on components.
- `hashCode()` is consistent with `equals()`; two equal records must have equal hash codes.
- `==` on two variables referencing records still checks whether they refer to the **same object**.

A record is still an object, still has object identity, and can be used in collections or passed to methods like any other class. It **does not turn Java into a pass-by-value object language**, nor does it guarantee memory layout different from a regular class.

### 3.3. Records Can Have Behavior

A record is not merely a "data bag" with no methods. It can implement logic directly tied to its data and implement interfaces:

```java
public record Rectangle(double width, double height) {
    public Rectangle {
        if (!Double.isFinite(width) || !Double.isFinite(height)
                || width < 0 || height < 0) {
            throw new IllegalArgumentException("Invalid dimensions");
        }
    }

    public double area() {
        return width * height;
    }

    public boolean isSquare() {
        return Double.compare(width, height) == 0;
    }
}
```

`area()` and `isSquare()` are **behaviors derived from the components themselves**. Placing such operations on the record is usually better than storing the result as state that could go out of sync.

## 4. "Immutability" of a Record: How Far Does It Go?

A record's component storage fields are `private final`, so **component references or primitive values cannot be reassigned after the object is created**. However, this is **shallow immutability**, not a guarantee that every object held inside the record is immutable.

### 4.1. Components That Are Primitives or Immutable Objects

```java
record Temperature(String city, int celsius) {}

Temperature t = new Temperature("Ha Noi", 28);
// t.celsius = 30; // Error: no public field to assign.
// t.celsius(30);   // Error: accessor is not a setter.
```

`String` is an immutable type; `int` is a primitive. With this kind of data, records provide a simple, easy-to-reason-about value model.

If you need to "update" a record, you typically create a new record:

```java
Temperature next = new Temperature(t.city(), 30);
```

### 4.2. Components Referencing Mutable Objects

The following example is **not truly deeply immutable**:

```java
import java.util.List;

record Team(String name, List<String> members) {}

List<String> names = new java.util.ArrayList<>();
names.add("An");
Team team = new Team("Core", names);
names.add("Binh");

System.out.println(team.members()); // [An, Binh]
```

The list can be modified via the `names` variable; the record only holds a `final` reference to that list.

When you want immutability at the list level, make a copy in the constructor:

```java
import java.util.List;
import java.util.Objects;

public record Team(String name, List<String> members) {
    public Team {
        name = Objects.requireNonNull(name, "name").strip();
        if (name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        members = List.copyOf(Objects.requireNonNull(members, "members"));
    }
}
```

`List.copyOf` creates a list that cannot be modified through its methods and is detached from subsequent changes to the source list. However, if the **elements inside** are mutable objects, copying the list still does not automatically make those elements immutable. Appropriate defensive copying should be considered for each kind of data.

### 4.3. Arrays Are an Easy-to-Misunderstand Case

```java
record Bytes(byte[] data) {}
```

With this record, callers can still mutate `data` through the array returned by the accessor, and the default comparison of an array component is based on **array reference equality**, not byte-by-byte equality. Two different arrays with identical contents will not necessarily make two `Bytes` records equal.

In an API that needs immutability and array content comparison, you can use defensive copies in both the constructor and accessor, and design `equals`/`hashCode` appropriate to the contents, or choose another representative data type with a clear equivalence contract.

This example shows that **records do not automatically solve every problem of deep immutability and deep equality**. You must examine the characteristics of each component.

## 5. Validating Data at Record Creation

In real systems, a data-carrying type still needs to **protect business invariants** (*invariants*): non-negative quantities, non-empty codes, non-negative money amounts, end date not before start date, and so on.

Records support a **compact canonical constructor**: syntax with just the record name and body, without rewriting the full parameter list. You validate or normalize parameters in the constructor body, and then Java automatically assigns the final parameter values to the corresponding fields.

```java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
    public OrderLine {
        sku = Objects.requireNonNull(sku, "sku").strip();
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isEmpty()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must be non-negative");
        }
    }

    public BigDecimal total() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

Here:

1. `OrderLine` declares three components `sku`, `quantity`, `unitPrice`.
2. `public OrderLine { ... }` validates and normalizes inputs. Reassigning the **parameter** `sku` before the constructor finishes is valid; this is not mutating a record field after creation.
3. Java completes assigning the parameters to the component fields at the end of the compact constructor.
4. `total()` returns a result derived from the data, without keeping an extra copy of the total amount.
5. `BigDecimal` is used instead of binary floating-point numbers for monetary values requiring exact decimal arithmetic per domain rules.

Example:

```java
OrderLine line = new OrderLine("  P-10  ", 3, new BigDecimal("12.50"));
System.out.println(line.sku());   // P-10
System.out.println(line.total()); // 37.50
```

Besides compact constructors, records also allow declaring an explicit canonical constructor with the full parameter list. Additional constructors (accepting different parameter sets) must delegate to another constructor of the same record via `this(...)`, so object creation ultimately goes through the canonical constructor and keeps data consistent.

```java
record Size(int width, int height) {
    Size(int side) {
        this(side, side);
    }
}
```

## 6. What Can and Cannot a Record Declare?

| Characteristic | Java 17 Rule | Design Implication |
|---|---|---|
| Record is a class | Implicitly extends `java.lang.Record` | Usable as a regular object and Java type |
| Inheritance | Record is implicitly `final`, cannot `extends` another class | Not for class hierarchies needing extension via inheritance |
| Interfaces | Can `implements` one or more interfaces | Well-suited for data models participating in shared contracts |
| Instance fields | Cannot declare additional instance fields beyond component fields | All instance state resides in the record header |
| `static` fields | Can declare suitable `static` fields | Used for constants or class-level data when justified |
| Methods | Can declare instance/static methods, override valid methods | Place rules tightly coupled to components on the record |
| Constructors | Can have canonical/compact constructors and valid auxiliary constructors | Validate and normalize data upon creation |
| Component fields | Are `private final`; no setters are generated | Data cannot be reassigned after creation |
| Nested records | Nested records are implicitly `static` | Do not hold an implicit reference to the enclosing class instance |
| Generics | Can declare type parameters like `record Pair<A,B>(A first, B second)` | Used for strongly typed results |

Example of a record implementing an interface:

```java
interface Priced {
    long priceInCents();
}

record Item(String code, long priceInCents) implements Priced {
    Item {
        if (priceInCents < 0) {
            throw new IllegalArgumentException("price must be non-negative");
        }
    }
}
```

The `priceInCents()` accessor generated by the record directly satisfies the interface method contract. There is no need to manually rewrite the method just to return the component.

A record can also be a direct subtype of a **sealed interface** when the record type is permitted. Since a record is implicitly `final`, that branch is closed. This is a useful combination when modeling a fixed set of results, though you do not need to learn sealed types first to understand the basic purpose of records.

## 7. When Is `record` the Right Choice?

### 7.1. Typically Suitable Cases

**Data exchanged between layers or application tiers (DTOs):**

```java
record SearchResult(String title, String url, int score) {}
```

A search result represented by a clear set of components is very convenient to return from functions or pass between layers. Using records for DTOs also depends on the serialization tools and API contracts in use.

**Domain-tied values:**

```java
record DateRange(java.time.LocalDate from, java.time.LocalDate to) {
    DateRange {
        if (from == null || to == null || to.isBefore(from)) {
            throw new IllegalArgumentException("Invalid date range");
        }
    }
}
```

The components are validated upfront, preventing the creation of an invalid date range.

**Multi-part return values:**

```java
record CountAndTotal(long count, long total) {}
```

Instead of using an array with hard-to-guess meanings at index 0 and 1, the result has transparent component names.

**Input data for an operation:**

```java
record CreateUserCommand(String email, String displayName) {}
```

The record carries the data of a clear request, which the business layer then processes and returns a result for. Using a record does not eliminate the need for validation or authorization at the appropriate layer.

### 7.2. Cases Where a Regular Class Often Makes More Sense

**Objects with a lifecycle and mutable state:** an account with a continuously changing balance, a shopping cart adding/removing items, or a process whose state changes through actions. A class encapsulating state and state transitions often communicates the design better.

**Objects with identity independent of all attributes:** two entities with the same name and birth date are not necessarily the same user; two orders with the same displayed fields are not necessarily the same order. When equality by ID or identity is core, you should not mechanically apply `equals()` based on all record components.

**Frameworks requiring a different class shape:** some ORM/entity mechanisms, proxies, lazy loading, or binding tools may require an extensible class, special constructors, or mutable fields. For example, JPA entities typically have a lifecycle, identifier, and framework requirements incompatible with a record's `final`/constructor/component constraints. Records may fit projections or DTOs better, depending on the framework and version.

**Models needing inheritance from another class or holding extra hidden state:** records cannot extend an arbitrary class and cannot have instance fields beyond components. If a type must hold a per-instance cache, undisclosed internal state, or participate in a specific class hierarchy, a regular class may be more appropriate.

A useful design rule: if callers care more about **the published bundle of data** than **the identity and lifecycle of an object**, consider a record. If an object needs to maintain state across a sequence of actions, a class is usually the more natural choice.

## 8. Records vs. Other Ways of Carrying Data

| Representation | Pros | Limitations or Considerations |
|---|---|---|
| `record UserId(long value)` | Expresses a value with a clear type name; has component-based comparison | Needs validation when the value has business constraints |
| `final class UserId` with manual fields and API | Full control over state, equality, and API | Must write/maintain boilerplate code if only carrying data |
| `Map<String, Object>` | Flexible for dynamic structures | Easy to mistype keys, loses compile-time type checking, hard to document contract |
| `Object[]` or positional arrays | Simple syntax for very short data | Positional meanings are ambiguous; casting and error detection are harder |
| `enum` | Represents a finite set of constants with related logic | Does not create an open set of arbitrary data-carrying values like a record |

Identification example:

```java
record UserId(long value) {
    UserId {
        if (value <= 0) throw new IllegalArgumentException("Invalid user ID");
    }
}
```

`UserId` provides a meaningful data type instead of passing an ambiguous `long` throughout the program. However, having a record **does not automatically guarantee good domain design**; the author must still specify valid values, null handling, and equality semantics.

## 9. Migrating an Existing Class to a Record: What to Check?

Suppose a project has the class:

```java
public final class CustomerData {
    private final String name;
    private final int tier;

    public CustomerData(String name, int tier) {
        this.name = name;
        this.tier = tier;
    }

    public String getName() {
        return name;
    }

    public int getTier() {
        return tier;
    }
}
```

Concise form using a record:

```java
public record CustomerData(String name, int tier) {}
```

However, a direct replacement can change contractual behavior:

1. **Accessor names:** `getName()`/`getTier()` in the class become `name()`/`tier()` by default. If API compatibility must be preserved, the record can declare extra compatibility methods, or you can keep the old class.
2. **Equality:** the class above defaults to identity-based `Object.equals()`; the new record compares by components. This can affect `HashSet`, `HashMap`, tests, and business logic.
3. **String display:** a record's `toString()` differs from `Object.toString()` or any custom format defined in the class.
4. **Constructor shape and reflection:** the canonical constructor and record components are part of the record's structure. Frameworks relying on a no-arg constructor, setters, or JavaBean properties may need adjustment.
5. **State requirements:** if the class has fields that do not appear in the record header, the new record can no longer hold the same state.
6. **Long-term API compatibility:** adding, renaming, or reordering record components can affect constructor calls and how external callers read data. Treat the record header as a public contract.

Therefore, convert to a record when **the type's semantics** truly fit, and after identifying which APIs must remain unchanged.

## 10. Integrated Example Running on Java 17

The following example maintains a small product list and uses a record to represent product data. Data is normalized and validated in the constructor; when changing stock, the program creates a new record.

Save as `Main.java`:

```java
import java.util.List;
import java.util.Objects;

public class Main {
    record Product(String sku, int stock) {
        Product {
            sku = Objects.requireNonNull(sku, "sku").strip();
            if (sku.isEmpty()) {
                throw new IllegalArgumentException("sku must not be blank");
            }
            if (stock < 0) {
                throw new IllegalArgumentException("stock must be non-negative");
            }
        }

        boolean inStock() {
            return stock > 0;
        }

        Product withStock(int newStock) {
            return new Product(sku, newStock);
        }
    }

    public static void main(String[] args) {
        Product first = new Product("  SKU-01  ", 5);
        Product same = new Product("SKU-01", 5);
        Product updated = first.withStock(3);

        System.out.println(first.sku());
        System.out.println(first.equals(same));
        System.out.println(first);
        System.out.println(updated);

        List<Product> products = List.of(first, new Product("SKU-02", 0));
        long available = products.stream()
                .filter(Product::inStock)
                .count();
        System.out.println("Available: " + available);
    }
}
```

Compile/run with JDK 17:

```bash
javac --release 17 -encoding UTF-8 Main.java
java Main
```

Illustrative output:

```text
SKU-01
true
Product[sku=SKU-01, stock=5]
Product[sku=SKU-01, stock=3]
Available: 1
```

The example demonstrates the key ideas:

- `Product` is a **nested record** inside `Main`, so there is no need to create a separate `Product.java` file for the example.
- `sku` is normalized in the compact constructor, and invalid values are rejected.
- `first.equals(same)` returns `true` because both records have the same components, even though they are two distinct objects.
- `withStock` creates a new `Product`; it does not mutate `first`.
- `Product::inStock` uses the record's business method to filter a `List<Product>`.

For multi-class projects, `Product` can be extracted into a top-level record `public record Product(...)` in `Product.java` in the appropriate package.

## 11. Misconceptions to Avoid

### "A record is just shorthand for a class; there is no design difference"

A record makes an **explicit commitment to published data** through components and generated methods, while imposing restrictions on state and inheritance. It signals that the object's meaning lies in its set of data components. A regular class can hide implementation details and change state in many other ways.

### "Records are always deeply immutable"

Component fields are `final`, but `List`s, arrays, and mutable objects inside can still be modified. If deep immutability is needed, you must design and copy defensively accordingly.

### "Records cannot have methods or constructors"

Records can declare methods, static members, compact/canonical constructors, and valid auxiliary constructors. What is restricted is the **instance state model** and **class inheritance relationship**, not the ability to write logic.

### "A record's `equals` deeply compares every kind of data"

Records compare components according to each type's rules. For array components, default equality is array reference equality; mutable objects inside can also cause hash/equality results to change over time. Choose components with stable equality semantics.

### "Records are the best default entity in every project"

Entities often need identity, mutable state, and persistence framework requirements. Records are usually convenient for **DTOs, computation results, clear domain values, or snapshots**; the specific choice depends on architecture and tooling.

### "Records are a preview feature in Java 17"

Incorrect. Records became a stable feature in Java 16 and are standard in Java 17. All examples in this lesson use only stable Java 17 features.

## 12. Practice Exercises

### Exercise 1: Choosing Class or Record

Read these four requirements:

1. Data representing coordinates `(latitude, longitude)`, created and passed across multiple methods.
2. A shopping cart object that can add/remove items and recalculate promotions on each event.
3. A statistical result `(count, average)` returned from a function.
4. A user object with an ID and many mutable profile attributes; identity determines the same user.

**Hint:** (1) and (3) usually suit records; (2) and (4) usually make more sense as classes with a clear lifecycle/identity model. When choosing, explain why the data is a **value** or a **lifecycle entity**.

### Exercise 2: Protecting Shallow Immutability

Design `record Course(String code, List<String> tags)` such that:

- `code` cannot be null or whitespace-only.
- `tags` cannot be null and after creation cannot be mutated through the original list or accessor.
- There is a method `hasTag(String tag)` checking whether a tag exists.

Hint: use a compact constructor, `Objects.requireNonNull`, `String.strip()`, and `List.copyOf`. Explain in your own words why tags here should be `String` (an immutable type) if you want to avoid state changes via elements.

### Exercise 3: Predicting Equality

```java
record Id(long value) {}
record Bag(int[] values) {}

Id a = new Id(10);
Id b = new Id(10);
Bag x = new Bag(new int[] {1, 2});
Bag y = new Bag(new int[] {1, 2});
```

Determine the results of `a.equals(b)`, `a == b`, `x.equals(y)`; explain using **record components**, **object identity**, and **array equality** behavior.

Answer: `true`, `false`, `false`. Both `Id` instances have the same primitive component; `a` and `b` are references to two different objects; the two `Bag` instances hold two arrays with different references.

### Exercise 4: Adding a Rule to a Record

Create `record Money(String currency, long minorUnits)`, validating that currency is non-blank and minorUnits is non-negative; add a method `add(Money other)` returning a new record if the currencies match. If the currencies differ, throw `IllegalArgumentException`. Write test cases for zero amounts, currency mismatch errors, and addition that could overflow `long` (hint: `Math.addExact`).

This exercise practices **data contracts**, validation, business behavior, and creating new values without setters.

## 13. Mastery Criteria

Learners understand the role of records when they can:

1. Explain why Java provides records for data-carrying types and why a record is still a class.
2. Write a record with multiple components, instantiate it using the canonical constructor, call accessors, and explain the default `equals`/`hashCode`/`toString`.
3. Convert a simple data class to a record and list differences that can affect the API.
4. Write a compact constructor to validate and normalize data before the object is created.
5. Distinguish **final component fields** from **deep immutability**, and handle mutable collection/array examples.
6. Choose records for suitable DTOs/values and choose classes when lifecycle, identity, or hidden state is needed.
7. Write and run examples with JDK 17 without enabling preview.

### Official References

- [Java Language Specification, Java SE 17 — Record Classes (JLS §8.10)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record syntax and rules.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): common superclass of records.
- [OpenJDK JEP 395 — Records](https://openjdk.org/jeps/395): design goals and standardized status of the feature.

Records help the Java language express a fixed group of data clearly. Choose a record when **the published data itself is the type's contract**; choose a regular class when the system needs an object model with state, identity, or inheritance that does not fit a record's constraints.
