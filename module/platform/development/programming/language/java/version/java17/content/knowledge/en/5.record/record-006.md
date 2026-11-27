# Records in Java 17: Auto-Generated `equals()`, `hashCode()`, and `toString()`

In Java 17, a **record** is a kind of class for objects whose **state is described by a set of data components (record components)**. When declaring a record, Java automatically provides methods for working with values, including **`equals(Object)`**, **`hashCode()`**, and **`toString()`**. These three methods are critical when comparing objects, using objects as keys in `HashMap` / elements in `HashSet`, or inspecting data while running a program.

This lesson explains **how those methods are generated, what they compare, where their limits lie, and when you should override them**. All examples use standard Java 17 syntax, without needing preview features enabled.

## 1. Why Does a Record Auto-Generate These Three Methods?

With a regular class, programmers often have to write a constructor, getters, `equals`, `hashCode`, and `toString` manually to represent a group of data:

```java
public final class PointClass {
    private final int x;
    private final int y;

    public PointClass(int x, int y) {
        this.x = x;
        this.y = y;
    }

    public int x() { return x; }
    public int y() { return y; }

    // To compare by value, you also have to write equals and hashCode.
    // To print data clearly, you also have to write toString.
}
```

Without overriding `equals()` in the class above, `PointClass` inherits `Object`'s default comparison: two references are equal only when pointing to the exact same object. Meanwhile, many problems require **two points with the same coordinates to be considered equal even if they are two separately created objects**.

With a record, the declaration becomes concise:

```java
record Point(int x, int y) {
}
```

From the **record header** `(int x, int y)`, Java provides the corresponding members:

| Member | Built-in Behavior |
| --- | --- |
| `Point(int x, int y)` | **Canonical constructor** initializing the data components, if you do not declare a matching constructor yourself. |
| `x()`, `y()` | Component accessor methods with names matching the components; different from `getX()`-style getters. |
| `equals(Object)` | Compares **same record type** and the value of **each component**. |
| `hashCode()` | Produces a hash code based on the components, consistent with `equals`. |
| `toString()` | Creates a descriptive string of the record, containing the record name and the components with their values. |

Components correspond to `private final` instance fields. A record is also an **implicitly `final`** class and **extends `java.lang.Record`**. Thus, a record cannot be subclassed with `extends`; this is not a mechanism for creating "inheritable data classes."

> **Key point:** Saying the three methods are "auto-generated" means the record author does not have to declare them to get default behavior. A record **can still define** one or more of these methods itself when there is a clear reason.

## 2. First Example: How Do the Three Methods Work?

Create `RecordMethodsDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

record Point(int x, int y) {
}

record OtherPoint(int x, int y) {
}

public class RecordMethodsDemo {
    public static void main(String[] args) {
        Point a = new Point(2, 5);
        Point b = new Point(2, 5);
        Point c = new Point(2, 6);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.equals(new OtherPoint(2, 5)));

        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a);

        Set<Point> points = new HashSet<>();
        points.add(a);
        System.out.println(points.contains(b));
    }
}
```

Compile and run with JDK 17:

```bash
javac RecordMethodsDemo.java
java RecordMethodsDemo
```

Typical output:

```text
false
true
false
false
true
Point[x=2, y=5]
true
```

Explanation:

- `a == b` is `false`: `a` and `b` are **two separate objects**, so they do not share the same reference.
- `a.equals(b)` is `true`: both are `Point` instances with `x = 2` and `y = 5`.
- `a.equals(c)` is `false`: component `y` differs.
- `a.equals(new OtherPoint(2, 5))` is `false`: same shape and values, yet **different record types**.
- Two equal `Point` instances have the same `hashCode()`.
- `System.out.println(a)` calls `a.toString()` to display the components.
- `HashSet` recognizes another `Point` equal to `a` by value, so `contains(b)` is `true`.

**Do not memorize a specific hash number** for `Point(2, 5)`. The important contract is that **equal records have the same hash code**, not a fixed numerical formula across all JDK versions.

## 3. `equals(Object)`: Comparing by Components, Not Object Identity

Declaration:

```java
record Student(String name, int age, boolean active) {
}
```

When not overridden, `Student` gets an `equals(Object)` meaning:

1. The compared object must be the **same record type `Student`**.
2. Corresponding components (`name`, `age`, `active`) must be equal.
3. If any component differs, the two records are not equal.

In this example:

```java
Student s1 = new Student("Lan", 20, true);
Student s2 = new Student("Lan", 20, true);
Student s3 = new Student("lan", 20, true);

System.out.println(s1.equals(s2)); // true
System.out.println(s1.equals(s3)); // false: String.equals is case-sensitive
System.out.println(s1.equals(null)); // false
```

For reference types like `String`, comparison follows **`equals` of that component's value type**, handling `null`. For primitive components, Java uses value comparison appropriate to the primitive type; note the special cases for `float` and `double` below.

### 3.1. Comparing Primitive and Reference Components

| Component Type | Important Behavior of Auto-Generated `equals()` |
| --- | --- |
| `int`, `long`, `short`, `byte`, `char`, `boolean` | Compares the corresponding primitive values. |
| `float`, `double` | Compares using `Float.compare`/`Double.compare` semantics, distinguishing signed zeros and handling `NaN`. |
| `String` | Compares using `String.equals`, case-sensitive. |
| `BigDecimal` | Uses `BigDecimal.equals`: `1.0` and `1.00` are **not** equal under `equals` due to different scales. |
| `List<T>` | Uses `List.equals`: typically compares elements in order according to their `equals` contract. |
| Arrays `int[]`, `String[]`, ... | Uses array reference comparison; **does not compare elements automatically**. |

For `double`, two cases can be surprising:

```java
record Measure(double value) {
}

System.out.println(
        new Measure(+0.0).equals(new Measure(-0.0))
); // false

System.out.println(
        new Measure(Double.NaN).equals(new Measure(Double.NaN))
); // true
```

This differs from primitive `==` on `double`: `+0.0 == -0.0` is `true`, whereas `Double.NaN == Double.NaN` is `false`. The record's rules support a consistent contract between `equals` and `hashCode`.

### 3.2. Arrays Need Special Attention

```java
import java.util.Arrays;

record Scores(int[] values) {
}

int[] first = {8, 9, 10};
int[] second = {8, 9, 10};

Scores a = new Scores(first);
Scores b = new Scores(second);
Scores c = new Scores(first);

System.out.println(Arrays.equals(first, second)); // true
System.out.println(a.equals(b)); // false
System.out.println(a.equals(c)); // true
```

**Why?** `Arrays.equals(first, second)` compares the contents of the two arrays. However, a record's default `equals` uses reference comparison for array components: two variables pointing to **two different arrays**, even with identical elements inside, are not considered equal components.

When a record holds an array, choose one of two paths:

- You genuinely want **array identity**: keep default behavior and understand its limitation.
- You want **element value equality**: switch to a collection type with content-based `equals`, or explicitly design `equals`/`hashCode` for the array component.

Do not assume the `record` keyword automatically performs deep equality (`deep equality`) for nested data structures.

### 3.3. Two Different Record Types Are Not Equal Just Because Their Components Match

```java
record UserId(long value) {
}

record OrderId(long value) {
}

System.out.println(new UserId(100).equals(new OrderId(100))); // false
```

This is a helpful property: values belonging to two different domain concepts keep **type boundaries** even when both wrap a `long` internally.

## 4. `hashCode()`: Hash Code Based on Components

When `hashCode` is not defined manually, Java generates a hash code matching the record's component comparison. For two records of the same type that are equal according to `equals`, their hash codes must match:

```java
record Book(String isbn, int edition) {
}

Book book1 = new Book("978-0-00-000000-0", 2);
Book book2 = new Book("978-0-00-000000-0", 2);

System.out.println(book1.equals(book2)); // true
System.out.println(book1.hashCode() == book2.hashCode()); // true
```

Rules to remember:

1. **If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must be `true`.**
2. **Equal hash codes do not prove two objects are equal**; hash collisions can occur.
3. A hash code is not a unique ID, cryptographic checksum, or value to persist externally as a permanent key.
4. Do not depend on a specific **numeric value or formula** of `hashCode()` generated by the JDK; the compatibility contract lies in the relationship between `equals` and `hashCode`.

### Why Does This Matter for `HashSet` and `HashMap`?

```java
import java.util.HashMap;
import java.util.Map;

record ProductKey(String sku, int warehouseId) {
}

Map<ProductKey, Integer> stock = new HashMap<>();
stock.put(new ProductKey("P100", 3), 12);

int available = stock.get(new ProductKey("P100", 3));
System.out.println(available); // 12
```

The program creates **two distinct `ProductKey` objects** with the same components. `HashMap` still finds the right entry because the record has value-compatible `equals` and `hashCode`. This is a common reason to use records for **composite keys**.

However, if a component references an object whose state mutates after the record is used as a key, lookup results can become unreliable. Immutability of a **reference** does not mean deep immutability of the data inside it.

## 5. `toString()`: Clearly Displaying Record Name and Components

Given the record:

```java
record Address(String city, String country) {
}

Address address = new Address("Hanoi", "Vietnam");
System.out.println(address.toString());
System.out.println(address);
```

On common JDK 17 implementations, both lines typically display:

```text
Address[city=Hanoi, country=Vietnam]
Address[city=Hanoi, country=Vietnam]
```

This is useful when inspecting data during development without manually concatenating strings. `println(Object)` uses `String.valueOf`, which calls `toString()` when the object is non-`null`.

**Do not treat the exact string format as a long-term data contract.** The specification requires the string to include the record name and component information, though exact formatting details can depend on the implementation. Do not parse `toString()` output to exchange data with other systems; use an appropriate interchange format such as JSON with a proper serializer.

### 5.1. Reference Fields and `null`

```java
record Profile(String nickname, Integer level) {
}

System.out.println(new Profile(null, 3));
// Example: Profile[nickname=null, level=3]
```

Records **do not forbid `null` automatically**. To disallow it, validate in the constructor. For nested data, a record's `toString()` uses the string representations of its component values, so readability also depends on the component types.

### 5.2. `toString()` Does Not Protect Sensitive Data

```java
record AccessToken(String account, String token) {
    @Override
    public String toString() {
        return "AccessToken[account=" + account + ", token=***]";
    }
}
```

With the default `toString`, the token string could appear in logs when printing the record. Overriding `toString()` as above helps avoid **accidentally logging secrets through this method**. Even so, it **does not hide the data from the `token()` accessor** and does not replace proper secrets management.

## 6. `final` on Components Does Not Mean "Deep Immutability"

The fields corresponding to record components are `private final`, meaning **the field's reference cannot be reassigned after initialization**. However, if the component object itself is mutable, its contents can still be modified:

```java
import java.util.ArrayList;
import java.util.List;

record Basket(List<String> items) {
}

List<String> list = new ArrayList<>();
list.add("Pen");

Basket basket = new Basket(list);
System.out.println(basket); // Basket[items=[Pen]]

list.add("Notebook");
System.out.println(basket); // Basket[items=[Pen, Notebook]]
```

The value observed via `toString()` **changes**, and `hashCode()` can also change along with the `List`'s contents. If `basket` was already inserted into a `HashSet` or used as a `HashMap` key before mutating the list, lookups may no longer behave as expected.

### 6.1. Copying Data in the Constructor

A safer design for collection data is creating a copy that disallows mutation through standard operations:

```java
import java.util.List;
import java.util.Objects;

record ImmutableBasket(List<String> items) {
    ImmutableBasket {
        Objects.requireNonNull(items, "items");
        items = List.copyOf(items);
    }
}
```

In a **compact constructor**, the `items` parameter can be normalized before Java assigns it to the corresponding field; you do not write `this.items = items`. `List.copyOf` returns a list whose structure and elements cannot be changed via list operations, and which disallows `null` elements. Since the example uses immutable `String` elements, this structure fits well as a value object.

```java
List<String> source = new ArrayList<>();
source.add("Pen");

ImmutableBasket safe = new ImmutableBasket(source);
source.add("Notebook");

System.out.println(safe); // ImmutableBasket[items=[Pen]]
```

**Limitation:** `List.copyOf` copies at the collection level; if individual elements are still mutable objects, those element objects can continue to be modified through other references. Deep immutability requires examining the entire object graph, not only the `record` shell.

### 6.2. For Arrays, Defensive Copying Alone Does Not Change `equals`

Even if you clone an array in the constructor and when returning from the accessor, the record's default `equals` still treats array components as **references**, without comparing elements automatically. If content-based value semantics are needed, you must also implement `equals()` and `hashCode()` appropriately, or choose a different data type.

## 7. When Should You Override These Methods Yourself?

Records favor **value semantics across all components**. Therefore, keeping the default methods is usually best when the components truly define the value object's identity and have stable `equals`.

Overriding can make sense when:

- You need to mask a sensitive component or format the string specially → **override only `toString()`**.
- You need array content comparison instead of reference comparison → **override both `equals()` and `hashCode()`** and take care with defensive copying.
- You need to change what defines value equality → **redesign `equals()` together with `hashCode()`**; consider whether a record still fits the model.
- You need to normalize data before comparison → usually **normalize in the constructor** to keep the default methods, rather than rewriting all three methods.

### 7.1. Prefer Normalizing Components When Possible

For example, wanting emails to be case-insensitive **per application policy**:

```java
import java.util.Locale;
import java.util.Objects;

record NormalizedEmail(String value) {
    NormalizedEmail {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toLowerCase(Locale.ROOT);
    }
}
```

```java
NormalizedEmail a = new NormalizedEmail(" User@Example.COM ");
NormalizedEmail b = new NormalizedEmail("user@example.com");

System.out.println(a.equals(b)); // true
System.out.println(a.hashCode() == b.hashCode()); // true
```

Because both objects **store the identically normalized component**, the default `equals`, `hashCode`, and `toString` are already consistent. This illustrates an application-chosen normalization rule; do not blindly apply the same lowercasing to every identifier or internationalized text.

### 7.2. Example Overriding Both `equals` and `hashCode` for an Array

Create `IntVectorDemo.java`:

```java
import java.util.Arrays;

record IntVector(int[] elements) {
    IntVector {
        elements = elements.clone();
    }

    @Override
    public int[] elements() {
        return elements.clone();
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof IntVector vector
                && Arrays.equals(elements, vector.elements);
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(elements);
    }

    @Override
    public String toString() {
        return "IntVector[elements=" + Arrays.toString(elements) + "]";
    }
}

public class IntVectorDemo {
    public static void main(String[] args) {
        int[] source = {1, 2, 3};
        IntVector first = new IntVector(source);
        IntVector second = new IntVector(new int[] {1, 2, 3});

        source[0] = 99;
        first.elements()[1] = 88;

        System.out.println(first.equals(second));
        System.out.println(first.hashCode() == second.hashCode());
        System.out.println(first);
    }
}
```

Run:

```bash
javac IntVectorDemo.java
java IntVectorDemo
```

Output:

```text
true
true
IntVector[elements=[1, 2, 3]]
```

This example combines **three design decisions**:

1. The constructor clones the array so external code cannot mutate internal data via the input array.
2. The `elements()` accessor also clones the array so external code cannot mutate internal data via the returned value.
3. `equals` and `hashCode` both use `Arrays` utilities, while `toString` explicitly prints the element list.

`Arrays.equals` and `Arrays.hashCode` fit one-dimensional arrays of `int`. For **nested arrays**, consider `Arrays.deepEquals` and `Arrays.deepHashCode`, and handle deep copying if inner data also must be immutable. Do not assume `Arrays.equals` performs deep comparison across all levels by default.

### 7.3. If Only One Component Determines Equality

By default, a record compares **all** components. You can override to use a different subset of components, though doing so changes the type's meaning:

```java
import java.util.Objects;

record Employee(String id, String displayName) {
    Employee {
        Objects.requireNonNull(id, "id");
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Employee employee
                && id.equals(employee.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Two `Employee` records with the same `id` but different `displayName` values will be equal under this new definition. This may be chosen in certain models, yet can also surprise readers because the record header lists **both** components. If an entity has an identifier and mutable lifecycle, a regular class may express the model better. When overriding manually, ensure all `equals` and `hashCode` contracts still hold.

## 8. Contract of `equals` and `hashCode` When Overriding

These rules apply to every Java class, including records:

| Rule | Meaning |
| --- | --- |
| Reflexive | `a.equals(a)` must be `true` for any non-`null` object. |
| Symmetric | `a.equals(b)` and `b.equals(a)` must return the same result. |
| Transitive | If `a.equals(b)` and `b.equals(c)`, then `a.equals(c)`. |
| Consistent | As long as the data used for comparison does not change, `equals` results must remain consistent. |
| Comparison with `null` | `a.equals(null)` must be `false`. |
| Hash relation | If `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()` must hold. |

**A record's default methods** already obey the required contracts when components behave compatibly. When overriding `equals`, never assume the auto-generated `hashCode` still fits the new comparison rule.

Design bug example:

```java
// Bug illustration: DO NOT use in an application.
record BadKey(String code, String label) {
    @Override
    public boolean equals(Object other) {
        return other instanceof BadKey key && code.equals(key.code);
    }

    // hashCode is still generated from all record components.
    // Two BadKey instances with the same code but different labels are equal,
    // yet their default hashCodes can differ => contract violation.
}
```

If equality depends only on `code`, you must define `hashCode` correspondingly using `code`, or pick a design that does not need to alter the default equality semantics.

## 9. Things Records Do Not Do Automatically

The three auto-generated methods are very helpful, yet **not every data modeling need is solved automatically**:

| Common Misconception | Actual Behavior |
| --- | --- |
| "Records deeply compare all data." | For arrays, default `equals` still compares references; for other objects, it uses their `equals` contract. |
| "Everything inside a record is immutable." | Fields are `final`, but referenced objects may be mutable. |
| "A record's hash code is a standardized constant." | Only consistency with `equals` is guaranteed; do not rely on specific hash numbers. |
| "`toString()` is always safe to log." | It may contain sensitive data from components. |
| "Two records with the same component names/values are equal." | They must be the same record type; identical structure does not imply equality. |
| "Record constructors automatically validate data." | To forbid `null`, negative numbers, or invalid values, validate or normalize explicitly. |
| "`toString()` can serve as a stable storage format." | Formatting details should not be treated as a data interchange protocol. |

## 10. When to Use Records for Value Objects?

Records fit well when an object is **a group of values defined primarily by its components**. Examples:

- **Coordinates:** `record Point(int x, int y)`.
- **Date ranges:** `record DateRange(LocalDate start, LocalDate end)`; validate `start` is not after `end`.
- **Composite data keys:** `record OrderKey(String orderId, int lineNumber)`.
- **Computation results:** `record Result(int total, boolean successful)`.
- **Data passed between layers:** `record SearchResult(String title, int score)` when components define the value's meaning.

If you need **objects with distinct identity, continuously mutating state**, or expect most attributes not to participate in equality, a regular class may be more suitable. Do not force every Java object into a record just to reduce line count.

## 11. Self-Practice Exercises

### Exercise 1: Predict the Three Methods

```java
record Size(int width, int height) {
}

Size s1 = new Size(10, 20);
Size s2 = new Size(10, 20);
Size s3 = new Size(20, 10);
```

Predict:

1. What is `s1 == s2`?
2. What are `s1.equals(s2)` and `s1.equals(s3)`?
3. Is `s1.hashCode() == s2.hashCode()` guaranteed to be true?
4. What information can `System.out.println(s1)` display?

**Hint:** Answer respectively `false`, `true`/`false`, `true`, and a string with the record name plus `width`, `height` names and values (typically `Size[width=10, height=20]`).

### Exercise 2: Do Arrays Compare by Content?

```java
record Pixels(int[] rgb) {
}

Pixels p1 = new Pixels(new int[] {255, 0, 0});
Pixels p2 = new Pixels(new int[] {255, 0, 0});
```

Explain why `p1.equals(p2)` does not return `true` by element values. Fix the design using **`Arrays.equals` and `Arrays.hashCode`**, and consider defensive copying of the array in the constructor and accessor.

### Exercise 3: Avoiding Hash Mutation as a Map Key

```java
record FilterKey(java.util.List<String> tags) {
}
```

Write a constructor using `List.copyOf(tags)`, then put a `FilterKey` into a `HashMap`. Try mutating the source list; explain why an unmodifiable copy keeps `equals` and `hashCode` results stable when the component is a `List<String>`.

### Exercise 4: Designing Safe Display Output

Design `record LoginSession(String userId, String sessionToken)` and override **only** `toString()` so the raw token is not printed in logs. Verify that `equals` and `hashCode` are still generated by Java from both components if you do not override them.

## 12. Takeaways to Apply

A record's default **`equals()`** expresses equality based on **same record type and each component's value**. Auto-generated **`hashCode()`** is consistent with that comparison, making it especially useful for `HashSet` and `HashMap`. **`toString()`** helps inspect the record name and components without manual string concatenation. When components are mutable, arrays, contain secrets, or when "equality" differs from comparing all components, proactively design the constructor, accessors, and overridden methods accordingly.

### References

- [JEP 395: Records](https://openjdk.org/jeps/395) — records becoming a standard Java feature.
- [Java Language Specification, Java SE 17 — §8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10) — specification of records, constructors, components, and default methods.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html) — base class of all records and value contracts.
- [Java SE 17 API — `java.util.Arrays`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html) — comparison, hashing, and string formatting methods for arrays.
- [Java SE 17 API — `java.util.List`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)) — `List.copyOf` for creating unmodifiable collections.
