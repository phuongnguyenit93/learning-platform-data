# Component Declarations and Auto-Generated Members of a Java Record

## 1. What Is a Record and What Does This Lesson Focus On?

Since Java 16, `record` has been a form of class declaration specialized in modeling **a data value described by a fixed list of components** (*record components*). Java 17 already supports records as an official and stable feature.

Example:

```java
record Student(String name, int age) {
}
```

This is the declaration of a **record class** named `Student` with exactly **two record components**:

- `String name`: a component of type String named `name`.
- `int age`: a component of type int named `age`.

From this short declaration, the compiler generates observable members such as:

- Two corresponding **instance fields**: `private final String name` and `private final int age`.
- Two **public accessor methods**: `String name()` and `int age()`.
- A **canonical constructor** accepting arguments in header order: `Student(String name, int age)`.
- Implementations for `equals(Object)`, `hashCode()`, and `toString()`, unless you declare the permitted replacement methods yourself.

A record is still a **class**; it can have methods, static fields, static methods, and implement interfaces according to its rules. However, it cannot be used as an arbitrary mutable class: component fields are `final`, declaring additional instance fields is not allowed, and extending a class of your choice is not allowed.

> **Key takeaway:** The record header is not just a constructor parameter list. It is the **description of the core data state of the record**, serving as the foundation for fields, accessors, the canonical constructor, and value-oriented methods.

This lesson focuses specifically on **record component declarations and auto-generated members**, how to view/redefine them, cases with mutable components, and common mistakes. The examples prioritize Java 17+ and clearly specify the file, compilation command, and output when they are complete programs.

## 2. Running the First Record Program

Create the file **`RecordBasicsDemo.java`**:

```java
record Student(String name, int age) {
}

public class RecordBasicsDemo {
    public static void main(String[] args) {
        Student student = new Student("An", 20);

        System.out.println(student.name());
        System.out.println(student.age());
        System.out.println(student);
    }
}
```

Compile and run:

```bash
javac RecordBasicsDemo.java
java RecordBasicsDemo
```

**Standard output:**

```text
An
20
Student[name=An, age=20]
```

### Reading the Output

1. `new Student("An", 20)` calls the canonical constructor whose signature matches the record header.
2. `student.name()` calls the component accessor `name()`. This is **not** a compiler-generated `getName()`.
3. `student.age()` calls the component accessor `age()`.
4. `System.out.println(student)` calls the `toString()` provided by the record, displaying the record name and the component names/values.

**What the compiler does not auto-generate:** JavaBean-style `getName()`, `getAge()`, `setName(...)`, or `setAge(...)`. If you need JavaBean naming for a specific library, that is a separate integration requirement; default record accessors always have the **same name as the component**.

## 3. Reading the Record Declaration Syntax

A general declaration has the form:

```java
record RecordName(TypeA first, TypeB second) {
    // Permitted members of the record.
}
```

This is an **illustrative template**; `TypeA` and `TypeB` represent valid types that must be defined when used.

Structure:

| Syntax | Meaning |
| --- | --- |
| `record` | Keyword to declare a record class |
| `RecordName` | Type name |
| `(...)` immediately after the name | Record header |
| `TypeA first` | First record component |
| `TypeB second` | Second record component |
| `{ ... }` | Record class body for adding valid members |
| `;` after declaration | Not required for a class/record declaration |

The components have a defined **order**, name, and type. This order is used for the parameters of the canonical constructor and for APIs that observe the record structure.

### A Record Can Have Zero Components

```java
record Empty() {
}
```

This is a valid declaration. It describes a record with no component state; the canonical constructor takes no parameters, and component accessors do not exist because there are no components.

**However, choose according to the domain:** If you only need a data-free constant, a singleton/enum may be clearer. An empty record makes sense when a **value of a specific type** needs to participate in an API without carrying component data.

## 4. From Header to Fields: `private final` Is the Core Point

Consider:

```java
record Point(int x, int y) {
}
```

The compiler generates fields corresponding to the two components that are, in essence:

```java
private final int x;
private final int y;
```

This is an **illustrative snippet**, not a requirement to rewrite the two fields in the record body. In a record declaration, **declaring additional instance fields is not allowed**.

### Meaning of the Two Modifiers

- `private`: external code does not access `point.x` directly via the usual field access mechanism; instead, it uses `point.x()`.
- `final`: each component field is assigned during object construction and **cannot be reassigned after initialization**.

Create **`RecordFinalFieldsDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordFinalFieldsDemo {
    public static void main(String[] args) {
        Point first = new Point(2, 3);
        Point second = new Point(5, 8);

        System.out.println(first.x() + "," + first.y());
        System.out.println(second.x() + "," + second.y());

        // first.x = 10; // Invalid: private final field.
        // first.x(10);  // No setter x(int).
    }
}
```

```bash
javac RecordFinalFieldsDemo.java
java RecordFinalFieldsDemo
```

```text
2,3
5,8
```

Both instances have their own state. You cannot modify component `x` on an already created Point via assignment. If you want a new value, create a **new record instance** from the new values.

**Do not confuse:** `final` on a reference field only fixes the reference; it does not necessarily make the referenced object inside immutable. A later section has an array/list example.

## 5. Accessors: Same Name as the Component, Without the `get` Prefix

Each record component `foo` has an accessor method `foo()`. For example:

```java
record User(String username, boolean active) {
}
```

The compiler provides:

```java
public String username();
public boolean active();
```

The two lines are **illustrative method signatures**, not declarations to copy into the body.

Not auto-generated:

```java
// public String getUsername();
// public boolean isActive();
// public void setActive(boolean value);
```

### Callable Example

Create **`RecordAccessorNamesDemo.java`**:

```java
record User(String username, boolean active) {
}

public class RecordAccessorNamesDemo {
    public static void main(String[] args) {
        User user = new User("an", true);

        System.out.println(user.username());
        System.out.println(user.active());

        // user.getUsername(); // Not generated.
        // user.isActive();    // Not generated.
    }
}
```

```bash
javac RecordAccessorNamesDemo.java
java RecordAccessorNamesDemo
```

```text
an
true
```

**Why is this important?** Some older frameworks recognize properties through JavaBeans getters. Records have their own API, so you must check whether the framework supports record/component introspection or requires an adapter/custom mapping.

## 6. Canonical Constructor Generated According to the Record Header

Record:

```java
record Rectangle(int width, int height) {
}
```

has a canonical constructor corresponding to the components:

```java
Rectangle(int width, int height)
```

This is a **conceptual signature**; the access level is determined by the canonical constructor rules and the record declaration.

The canonical constructor is used to set the state for each component, in the exact order of the header. For example:

```java
new Rectangle(4, 6);
```

passes `width=4`, `height=6`.

Create **`RecordConstructorDemo.java`**:

```java
record Rectangle(int width, int height) {
}

public class RecordConstructorDemo {
    public static void main(String[] args) {
        Rectangle r = new Rectangle(4, 6);

        System.out.println(r.width());
        System.out.println(r.height());
        System.out.println(r.width() * r.height());
    }
}
```

```bash
javac RecordConstructorDemo.java
java RecordConstructorDemo
```

```text
4
6
24
```

**If no constructor is declared**, the compiler generates a canonical constructor matching the header. If you explicitly declare a canonical or compact constructor yourself, you are responsible for ensuring invariants, while the component field initialization rules are still enforced by Java.

## 7. Generated `equals(Object)`: Comparing Component Values

A record is designed to carry data values. When you do not declare `equals`, the compiler provides a comparison based on all components of the record type.

Create **`RecordEqualityDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordEqualityDemo {
    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point c = new Point(2, 4);

        System.out.println(a == b);
        System.out.println(a.equals(b));
        System.out.println(a.equals(c));
        System.out.println(a.equals(null));
    }
}
```

```bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
```

```text
false
true
false
false
```

**Explanation:**

- `a == b` is false because they are created with two separate `new` calls and are two separate object references.
- `a.equals(b)` is true because they have the same record class and both components x,y are equal.
- `a.equals(c)` is false because y is different.
- `a.equals(null)` is false.

This is **equality by component state**, which does not mean that record fields are deep-copied. Nor is it the case that equal record instances must be the same object.

### Be Careful About Comparing Reference Components

For a component that is an object, how it is compared depends on the component's value kind; for example, String has content equality, whereas an array uses reference identity when no custom logic is written. Do not conclude that generated equals will recursively compare every object graph according to business expectations.

## 8. `hashCode()` Generated Consistently with `equals()`

The compiler provides `hashCode()` based on the components, following the contract: two equal record instances must have the same hashCode.

Create **`RecordHashCodeDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordHashCodeDemo {
    public static void main(String[] args) {
        Point a = new Point(2, 3);
        Point b = new Point(2, 3);
        Point c = new Point(2, 4);

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());
        System.out.println(a.equals(c));
    }
}
```

```bash
javac RecordHashCodeDemo.java
java RecordHashCodeDemo
```

```text
true
true
false
```

**Do not print a specific hash number and treat it as standard output.** A hash code is not a business ID key or a storage code that remains stable across all versions/implementations. Two unequal objects can still have a hash collision.

### Record as a HashMap Key

A record with appropriate components that are immutable in logical value is often a good candidate for a map key. However, if a component references a mutable object that affects equals/hashCode, mutating that object after using the record as a key can make lookup behavior unpredictable.

**Practical rule:** Components that contribute to equality/hashCode should have **stable value semantics** when the record is used as a key.

## 9. `toString()` Generated to Display in a Component-Named Format

A record has a `toString()` of the form:

```text
RecordName[component1=value1, component2=value2]
```

This is an **output pattern**; the specific values are determined by the instance.

Create **`RecordToStringDemo.java`**:

```java
record Book(String title, int pages, boolean published) {
}

public class RecordToStringDemo {
    public static void main(String[] args) {
        Book book = new Book("Java", 300, true);

        System.out.println(book);
    }
}
```

```bash
javac RecordToStringDemo.java
java RecordToStringDemo
```

```text
Book[title=Java, pages=300, published=true]
```

`toString()` is convenient for debugging, but it is not **JSON** by default, does not have an escaping/serialization contract suitable for all cases, and can expose sensitive components if logged without control.

**An important point:** For an array component, `toString()` may use the default object array representation rather than necessarily printing formatted contents like `[1, 2]`. If you want adjusted output, implement toString yourself according to the application contract.

## 10. Relationship Among the Three Auto-Generated Methods

| Method | Role | Default Source of Semantics |
| --- | --- | --- |
| `equals(Object)` | Compare values by record components | Components and types |
| `hashCode()` | Hash consistent with equals | Components |
| `toString()` | Display the record/component names | Components and display values |

These three methods serve **different purposes**. A record can override them individually, but if you override equals/hashCode you must preserve the general contracts of Object.

**Do not infer** that identical toString outputs mean two records are equal, or that identical hashCode values mean they are equal. Display content and hash collisions are not sufficient evidence.

## 11. Summary of Generated Members on a Record

Create **`RecordGeneratedSummaryDemo.java`**:

```java
record Employee(String id, int grade) {
}

public class RecordGeneratedSummaryDemo {
    public static void main(String[] args) {
        Employee first = new Employee("E-1", 3);
        Employee duplicate = new Employee("E-1", 3);

        System.out.println(first.id());
        System.out.println(first.grade());

        System.out.println(first.equals(duplicate));
        System.out.println(
                first.hashCode() == duplicate.hashCode());
        System.out.println(first.toString());
    }
}
```

```bash
javac RecordGeneratedSummaryDemo.java
java RecordGeneratedSummaryDemo
```

```text
E-1
3
true
true
Employee[id=E-1, grade=3]
```

There are no hand-written method bodies in Employee, yet it already has a constructor, accessors, and Object-related implementations ready to use.

**The savings are not just fewer lines:** Because all the methods are derived from the **same record header**, a new component becomes part of the canonical constructor, equality, hash, and display according to the record rules. This reduces the risk of a developer forgetting to add a field to equals/hashCode compared to a hand-written mutable data class.

## 12. A Record Component Differs from a Local Variable or a Simple Getter

Consider:

```java
record Score(int points) {
    int doubled() {
        return points * 2;
    }
}
```

`points` is a **record component**; the compiler creates a corresponding field and an accessor `points()`. The method `doubled()` is an **additional instance method** that you declare, not a record component.

Therefore:

- `Score.points()` is not a static method.
- `score.points()` returns the component state.
- `score.doubled()` computes a derived value.
- `doubled` is not automatically added to `equals/hashCode/toString` as a new component.

**Boundary:** Only declarations in the record header constitute record components. Methods in the body do not become components even when they return important data.

## 13. Additional Instance Methods Are Valid

A record is not just “inert data”. You can write methods that compute derived values without storing additional state.

Create **`RecordDerivedMethodDemo.java`**:

```java
record Rectangle(int width, int height) {
    int area() {
        return Math.multiplyExact(width, height);
    }

    boolean isSquare() {
        return width == height;
    }
}

public class RecordDerivedMethodDemo {
    public static void main(String[] args) {
        Rectangle a = new Rectangle(3, 4);
        Rectangle b = new Rectangle(5, 5);

        System.out.println(a.area());
        System.out.println(a.isSquare());
        System.out.println(b.area());
        System.out.println(b.isSquare());
    }
}
```

```bash
javac RecordDerivedMethodDemo.java
java RecordDerivedMethodDemo
```

```text
12
false
25
true
```

The `area` and `isSquare` methods operate on the stored components. There is no need for a new field like `private int areaCache`; records prohibit adding instance fields outside the components.

`Math.multiplyExact` throws `ArithmeticException` when integer multiplication overflows, avoiding silently returning an incorrect value if the area exceeds `int`.

## 14. Records Do Not Automatically Validate Data Just Because They Are Records

The generated canonical constructor **receives and stores arguments**, but it does not automatically know what your business logic requires.

Example:

```java
record Age(int value) {
}
```

You can still call `new Age(-5)` if there is no validation.

A clear approach is to declare a **compact canonical constructor** to add checks.

Create **`RecordValidationDemo.java`**:

```java
record Age(int value) {
    Age {
        if (value < 0 || value > 150) {
            throw new IllegalArgumentException(
                    "age out of range");
        }
    }
}

public class RecordValidationDemo {
    public static void main(String[] args) {
        Age valid = new Age(20);
        System.out.println(valid.value());

        try {
            new Age(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid age");
        }
    }
}
```

```bash
javac RecordValidationDemo.java
java RecordValidationDemo
```

```text
20
invalid age
```

The **compact constructor** `Age { ... }` does not redeclare the parameter list; Java takes the canonical parameters from the header. After the body, the compiler takes care of assigning the component fields with the parameter values (which may have been normalized in the body).

Do not equate a record with a full bean validation system: domain invariants still have to be programmed or configured using an appropriate solution.

## 15. A Compact Constructor Can Normalize Parameters

A compact constructor can **reassign a parameter** before Java stores it into the final component field, such as trimming a String.

Create **`RecordNormalizationDemo.java`**:

```java
import java.util.Objects;

record Username(String value) {
    Username {
        value = Objects.requireNonNull(value).trim();

        if (value.isEmpty()) {
            throw new IllegalArgumentException(
                    "username is blank");
        }
    }
}

public class RecordNormalizationDemo {
    public static void main(String[] args) {
        Username username = new Username("  An  ");

        System.out.println(username.value());
        System.out.println(username);
    }
}
```

```bash
javac RecordNormalizationDemo.java
java RecordNormalizationDemo
```

```text
An
Username[value=An]
```

In the constructor body, `value` is the **parameter** of the canonical constructor and can be normalized. When the compact constructor body completes normally, Java assigns the final parameter value to the corresponding final field.

**Do not write `this.value = value` inside a compact constructor body**. Java prohibits direct assignment to a component field inside a compact constructor because the assignment mechanism is performed by the compiler. If you need explicit assignment control, see the explicit canonical constructor.

## 16. Explicit Canonical Constructor and the Requirement to Assign All Components

You can also write a full constructor yourself with the exact types, names, and order of parameters from the header.

Create **`ExplicitCanonicalRecordDemo.java`**:

```java
import java.util.Objects;

record Product(String sku, int quantity) {
    Product(String sku, int quantity) {
        this.sku = Objects.requireNonNull(sku).trim();

        if (quantity < 0) {
            throw new IllegalArgumentException(
                    "negative quantity");
        }
        this.quantity = quantity;
    }
}

public class ExplicitCanonicalRecordDemo {
    public static void main(String[] args) {
        Product product = new Product(" A-1 ", 4);

        System.out.println(product.sku());
        System.out.println(product.quantity());
        System.out.println(product);
    }
}
```

```bash
javac ExplicitCanonicalRecordDemo.java
java ExplicitCanonicalRecordDemo
```

```text
A-1
4
Product[sku=A-1, quantity=4]
```

**Unlike a compact constructor:**

- `Product(String sku, int quantity)` declares the full canonical parameters.
- You are responsible for assigning each component field exactly once according to definite-assignment rules.
- `this.sku` and `this.quantity` are permitted to be assigned in an **explicit canonical constructor**.
- This approach is more verbose and is useful when detailed initialization logic must be controlled.
- A compact constructor is usually more concise when only validating/normalizing parameters.

**Visibility:** The canonical constructor must have an access level consistent with the record declaration; you cannot deliberately restrict its access in a way that violates record rules. For a public record, use a public canonical constructor.

## 17. Comparing the Two Forms of Canonical Constructor

| Characteristic | Compact constructor | Explicit canonical constructor |
| --- | --- | --- |
| Syntax | `RecordName { ... }` | `RecordName(Type a, Type b) { ... }` |
| Parameter list | Taken from the header | Written in full matching the header |
| How component fields are stored | Compiler assigns after the body | Body must assign fields explicitly |
| Can parameters be normalized? | Yes, before implicit assignment | Yes, via explicit logic |
| Is `this.field = ...` allowed? | No, for component fields | Yes, if definite-assignment rules are satisfied |
| Best suited for | Short validation/normalization | More explicit initialization logic |

Do not declare **both a compact canonical constructor and an explicit canonical constructor at the same time** for the same record, because they represent the same canonical constructor.

## 18. Non-Canonical Constructors Must Delegate via `this(...)`

A record can have **overloaded constructors**, but a non-canonical constructor must delegate to another constructor of the same record, ultimately reaching the canonical constructor.

Create **`RecordOverloadedConstructorDemo.java`**:

```java
record Point(int x, int y) {
    Point(int both) {
        this(both, both);
    }

    Point {
        if (x < 0 || y < 0) {
            throw new IllegalArgumentException(
                    "negative coordinate");
        }
    }
}

public class RecordOverloadedConstructorDemo {
    public static void main(String[] args) {
        Point a = new Point(4);
        Point b = new Point(2, 3);

        System.out.println(a);
        System.out.println(b);
    }
}
```

```bash
javac RecordOverloadedConstructorDemo.java
java RecordOverloadedConstructorDemo
```

```text
Point[x=4, y=4]
Point[x=2, y=3]
```

`Point(int both)` calls `this(both,both)`, after which the canonical/compact constructor ensures that the components are initialized and validated.

**Overloaded constructors are not allowed to arbitrarily reassign component fields like a regular mutable class.** Every path to creating a record instance must go through canonical initialization according to the record rules.

## 19. Overriding an Accessor: Possible, but Must Preserve the Contract

By default, Java generates `public Type componentName()`. If you declare an accessor explicitly, it must have the **same component name, a matching return type, and no parameters**, with a valid access/public contract.

A valid example: using an accessor to return a snapshot of a mutable array.

Create **`RecordCustomAccessorDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record Samples(int[] values) {
    Samples {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }
}

public class RecordCustomAccessorDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};

        Samples samples = new Samples(source);
        source[0] = 9;

        int[] returned = samples.values();
        returned[1] = 8;

        System.out.println(
                Arrays.toString(samples.values()));
        System.out.println(
                Arrays.toString(source));
    }
}
```

```bash
javac RecordCustomAccessorDemo.java
java RecordCustomAccessorDemo
```

```text
[1, 2]
[9, 2]
```

- The compact constructor **clones the input array**, not keeping the source reference.
- The overridden accessor **clones the output array**, not exposing the internal array.
- The actual component field is still `private final int[] values`, but the mutable array contents are protected by defensive copying at both boundaries.
- `@Override` on the accessor indicates that the explicit method replaces the implicit accessor; if the compiler rejects the override due to a signature mismatch, the method declaration needs to be fixed.

**Essential warning:** Generated equals/hashCode for an array component is still based on array reference identity semantics, not automatic deep comparison of contents. A later section analyzes this separately.

## 20. Records Are Only *Shallowly Immutable* by Default

Record components are final fields, but if a component type is a mutable object, that object itself can still be modified.

Create **`RecordMutableArrayDemo.java`**:

```java
import java.util.Arrays;

record Numbers(int[] values) {
}

public class RecordMutableArrayDemo {
    public static void main(String[] args) {
        int[] source = {1, 2};

        Numbers n = new Numbers(source);
        source[0] = 9;

        System.out.println(
                Arrays.toString(n.values()));

        n.values()[1] = 8;

        System.out.println(
                Arrays.toString(source));
    }
}
```

```bash
javac RecordMutableArrayDemo.java
java RecordMutableArrayDemo
```

```text
[9, 2]
[9, 8]
```

**Why?**

- The final field `values` cannot be reassigned to another array after construction.
- However, the generated constructor **does not clone the array**; it holds the reference to `source`.
- The generated accessor `values()` returns the exact internal array reference without creating a copy.
- Modifying `source[0]` or `n.values()[1]` mutates **the same array object**.

Therefore, the statement “a record is immutable” is only accurate if **the component values are truly immutable or defensively guarded and no mutable state is exposed**. Do not assume that every object graph reachable from a record is immutable.

## 21. Records with `List`: Structure and Elements Must Be Checked Separately

Create **`RecordListAliasDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
}

public class RecordListAliasDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Team team = new Team(input);
        input.add("Binh");

        System.out.println(team.members());

        team.members().add("Chi");
        System.out.println(input);
    }
}
```

```bash
javac RecordListAliasDemo.java
java RecordListAliasDemo
```

```text
[An, Binh]
[An, Binh, Chi]
```

The generated constructor and accessor do not deep-copy the List.

### How to Handle When Containing Only Immutable Elements

Create **`RecordImmutableListDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}

public class RecordImmutableListDemo {
    public static void main(String[] args) {
        List<String> input = new ArrayList<>();
        input.add("An");

        Team team = new Team(input);
        input.add("Binh");

        System.out.println(team.members());

        try {
            team.members().add("Chi");
        } catch (UnsupportedOperationException ex) {
            System.out.println("immutable list view");
        }
    }
}
```

```bash
javac RecordImmutableListDemo.java
java RecordImmutableListDemo
```

```text
[An]
immutable list view
```

`List.copyOf` creates an unmodifiable snapshot of the mutable input list structure. Because the elements are immutable `String` values, this design has appropriate immutable semantics for the member list in the example.

**Do not overgeneralize:** If `members` is `List<StringBuilder>`, `List.copyOf` does not clone each StringBuilder. It is still possible to mutate the elements through other references. You must determine the **depth of the immutable contract** according to the types of components.

## 22. Generated `equals` with Array Components: Limitations of the Generated Member

The methods generated by a record are based on **record components**, but for a reference to an array, equality is not an element-by-element comparison. Two arrays with identical contents that are two distinct objects are still not equal according to the array's `Object.equals`:

~~~java
record Numbers(int[] values) {}

Numbers a = new Numbers(new int[]{1, 2});
Numbers b = new Numbers(new int[]{1, 2});
// a.equals(b) is false; java.util.Arrays.equals(a.values(), b.values()) is true.
~~~

The instantiations/calls above are a **fragment placed inside a method**, not a standalone Java file. If both records hold the exact **same array reference**, generated equality can be true, even though the array state remains mutable.

This is an exception you need to know so you do not misunderstand the word **generated**. The lesson **“equals(), hashCode(), toString() and the Impact of Array Components”** is where all these cases are verified (new arrays, shared references, hash contracts, two-dimensional arrays, and Map/Set). `Arrays.equals` only returns a boolean value and does **not** automatically change the behavior of `record.equals`; if you want content-based value semantics, you must explicitly design overrides for both `equals` and `hashCode` or choose another immutable representation.

## 23. Record Example with Custom Content Equality for Arrays

Create **`RecordArrayContentValueDemo.java`**:

```java
import java.util.Arrays;
import java.util.Objects;

record IntVector(int[] values) {
    IntVector {
        values = Objects.requireNonNull(values).clone();
    }

    @Override
    public int[] values() {
        return values.clone();
    }

    @Override
    public boolean equals(Object other) {
        return this == other
                || (other instanceof IntVector vector
                    && Arrays.equals(values, vector.values));
    }

    @Override
    public int hashCode() {
        return Arrays.hashCode(values);
    }

    @Override
    public String toString() {
        return "IntVector" + Arrays.toString(values);
    }
}

public class RecordArrayContentValueDemo {
    public static void main(String[] args) {
        int[] input = {1, 2};
        IntVector a = new IntVector(input);
        IntVector b = new IntVector(new int[] {1, 2});

        System.out.println(a.equals(b));
        System.out.println(a.hashCode() == b.hashCode());

        input[0] = 9;
        System.out.println(a);
        System.out.println(b);
    }
}
```

```bash
javac RecordArrayContentValueDemo.java
java RecordArrayContentValueDemo
```

```text
true
true
IntVector[1, 2]
IntVector[1, 2]
```

**Design points:**

- The compact constructor clones the input to break aliasing.
- The accessor clones the output so as not to expose mutable internal state.
- `equals` and `hashCode` compare by contents.
- `toString` displays the contents according to the application policy.

This is a case where you **deliberately rewrite** the generated methods because the representation requires logical value semantics that differ from array reference equality.

**Limitation:** If the array has nested mutable elements or other mutable values, appropriate deep copy/deep equals must be considered. This example is only an `int[]` array.

## 24. You Can Write `equals`, `hashCode`, and `toString` Yourself, but They Must Be Consistent

A record allows you to declare overrides of the three special methods. However, consider the following:

- Why is the default not suitable?
- Are you defining equality based on **all core data**, or do you want a different business identity?
- If two records are equal, are their hashCode values guaranteed to be equal?
- Is there any mutable value that causes hashCode to change after being used as a map key?
- Does `toString()` accidentally leak credentials, tokens, or sensitive data?
- Do frameworks/serializers expect the semantics of header components?

**An alternative approach** is not to use a record when a class truly has its own **identity and lifecycle**. Records lean toward transparent data carriers; if equality is based solely on a database ID while other fields are mutable, a regular entity class may express this more accurately.

## 25. A Record Can Implement Interfaces

A record cannot extend a user-defined class, but it can implement interfaces.

Create **`RecordInterfaceDemo.java`**:

```java
interface Named {
    String name();
}

record Person(String name, int age) implements Named {
}

public class RecordInterfaceDemo {
    static String display(Named value) {
        return "name=" + value.name();
    }

    public static void main(String[] args) {
        Person person = new Person("Lan", 25);

        System.out.println(display(person));
        System.out.println(person instanceof Named);
    }
}
```

```bash
javac RecordInterfaceDemo.java
java RecordInterfaceDemo
```

```text
name=Lan
true
```

The generated accessor `public String name()` of Person has a signature compatible with the interface `Named.name()`. Therefore, the record can satisfy the interface contract **directly from the auto-generated accessor**, without manual override code.

This is useful when APIs need shared read-only views, while each record still retains its own set of components.

## 26. A Record Is an Implicitly `final` Class and Extends `java.lang.Record`

A record class is considered final; you cannot write another class that `extends Person` if Person is a record. It extends `java.lang.Record` by language mechanism, not `Object` directly like a regular class.

An **intentionally invalid** snippet:

```java
record Person(String name) {
}

// class Employee extends Person { } // Invalid.
```

A record also cannot choose to `extends OtherBaseClass`. This is intentional: a record has a fixed and transparent set of state components; a subclass extending it with additional instance state could obscure that semantics.

**Polymorphism can be used via interfaces:** Multiple records `implements SharedInterface` without extending one another.

## 27. What Is Permitted in a Record Body?

| Member Kind | Can Be Declared? | Notes |
| --- | --- | --- |
| Instance method | Yes | Can compute derived values |
| Explicit accessor | Yes | Must conform to the component accessor contract |
| Compact canonical constructor | Yes | Validation/normalization |
| Explicit canonical constructor | Yes | Matches header/assigns components |
| Overloaded constructor | Yes | Must delegate via `this(...)` |
| Static field | Yes | E.g., constant/config; be cautious with mutable state |
| Static method | Yes | Factory/helper methods |
| Static initializer | Yes | According to the corresponding rules |
| Nested class/interface/enum | Yes | According to member declaration rules |
| Instance field outside the header | **No** | Component fields are the only instance fields |
| Instance initializer block | **No** | Records restrict instance initialization |
| Explicitly extending another class | **No** | Superclass is `java.lang.Record` |
| Letting a class extend a record | **No** | Records are final |
| Abstract record | **No** | Records cannot be declared abstract |

### Example Combining Instance and Static Methods

Create **`RecordFactoryDemo.java`**:

```java
record Temperature(int celsius) {
    static Temperature freezing() {
        return new Temperature(0);
    }

    int fahrenheit() {
        return celsius * 9 / 5 + 32;
    }
}

public class RecordFactoryDemo {
    public static void main(String[] args) {
        Temperature a = Temperature.freezing();
        Temperature b = new Temperature(20);

        System.out.println(a.fahrenheit());
        System.out.println(b.fahrenheit());
    }
}
```

```bash
javac RecordFactoryDemo.java
java RecordFactoryDemo
```

```text
32
68
```

`freezing()` is a **static factory** declared by the author, not a generated member. `fahrenheit()` is an additional instance method. Component `celsius` remains final.

## 28. Do Not Declare Instance Fields or Instance Initializers

This is **invalid code with comments**:

```java
record Bad(int x) {
    // int counter; // Invalid: instance field outside components.

    // { System.out.println("init"); }
    // Invalid: instance initializer block.
}
```

If you need derived state `doubleX`, there are these approaches:

- Compute it from `x` in a method: `int doubleX() { return 2 * x; }`.
- Add a new component to the header if the data is truly **part of the transparent state**. However, you must consider equality/hash/constructor because all of them are affected.
- Use an ordinary class if you need multiple instance fields, mutable caching, and a dedicated lifecycle.

**Do not use a static field as a workaround for the restriction:** Static state is shared across the entire type, not per-record-object state.

## 29. A Record Component Can Be a Primitive, Reference, or Generic Type

Example:

```java
record Coordinate(double latitude, double longitude) {
}

record Pair<A, B>(A first, B second) {
}

record Response<T>(int status, T body) {
}
```

These are **illustrative valid declarations**.

- Primitive components like int/double are stored directly as component values.
- Reference components like String/List can be null unless validated by the constructor.
- Generic type parameters allow a record to model a pair/response with flexible types.
- Generated methods are still based on **the declared components**, without generating a new kind of member field for generic arguments.

### Runnable Generic Record Example

Create **`GenericRecordDemo.java`**:

```java
record Pair<A, B>(A first, B second) {
}

public class GenericRecordDemo {
    public static void main(String[] args) {
        Pair<String, Integer> pair =
                new Pair<>("item", 5);

        System.out.println(pair.first());
        System.out.println(pair.second());
        System.out.println(pair);
    }
}
```

```bash
javac GenericRecordDemo.java
java GenericRecordDemo
```

```text
item
5
Pair[first=item, second=5]
```

Generic type safety works according to Java generics; it is not an automatic deep-copy or validation mechanism for reference components.

## 30. A Record Can Be a Nested Type or Local Record

A record can be declared nested inside a class or inside a block (Java 17). Nested/member records and local records are **implicitly static**, so they do not implicitly hold an enclosing instance or capture local variables like a non-static inner class.

Create **`NestedAndLocalRecordDemo.java`**:

```java
public class NestedAndLocalRecordDemo {
    record Pair(int left, int right) {
    }

    static int sum(int base) {
        record Delta(int amount) {
        }

        Delta delta = new Delta(3);
        return base + delta.amount();
    }

    public static void main(String[] args) {
        Pair pair = new Pair(2, 4);

        System.out.println(pair.left() + pair.right());
        System.out.println(sum(10));
    }
}
```

```bash
javac NestedAndLocalRecordDemo.java
java NestedAndLocalRecordDemo
```

```text
6
13
```

`Delta` is a local record that only has a name within the `sum` block. It does not capture `base` into implicit fields; the code explicitly passes `3` into the `amount` component. `base` is used by the enclosing method in the addition outside the local record.

**Note:** Do not confuse a local record with a non-static local class that can capture effectively-final local variables; the two kinds have different rules.

## 31. Record Components and Declaration Order Matter

The header order is part of the constructor API and how record components are observed.

```java
record Pair(int first, int second) {
}
```

`new Pair(1,2)` assigns first=1, second=2. If you change the order or names of the components, the source-level API and serialized schemas/tooling may be affected.

### Regarding Generated equality/toString

- Equality compares components according to record semantics.
- The string representation displays according to component names and order.
- The canonical constructor accepts parameters in record header order.
- `Class.getRecordComponents()` reflects the declaration order of components.

**Do not treat renaming/reordering components as a completely harmless refactor**, especially when external systems use JSON/database mapping or reflect record metadata.

## 32. Observing Components via Reflection Instead of Inferring from Fields

Java provides the `Class.getRecordComponents()` and `Class.isRecord()` APIs to determine whether a type is a record and to inspect its components.

Create **`RecordReflectionDemo.java`**:

```java
import java.lang.reflect.RecordComponent;

record Point(int x, int y) {
}

public class RecordReflectionDemo {
    public static void main(String[] args) {
        Class<Point> type = Point.class;

        System.out.println(type.isRecord());

        for (RecordComponent component :
                type.getRecordComponents()) {
            System.out.println(component.getName() + ":"
                    + component.getType().getSimpleName());
        }
    }
}
```

```bash
javac RecordReflectionDemo.java
java RecordReflectionDemo
```

```text
true
x:int
y:int
```

**Why use this API?** Frameworks and tools can recognize record structure in a standard way instead of guessing that a class has private final fields or JavaBean getters. An ordinary class can also have private final fields, yet **does not become a record** because of that.

`getRecordComponents()` returns record component information in declaration order. For a class that is not a record, this API returns null, so generic code needs to check `isRecord()` or handle null accordingly.

## 33. Generated Accessors Can Be Inspected via Reflection

A record component describes its name, type, and corresponding accessor method. The `RecordComponent.getAccessor()` method allows frameworks to find the accessor conforming to the contract.

Create **`RecordAccessorReflectionDemo.java`**:

```java
import java.lang.reflect.RecordComponent;

record User(String name, int age) {
}

public class RecordAccessorReflectionDemo {
    public static void main(String[] args) {
        for (RecordComponent component :
                User.class.getRecordComponents()) {
            System.out.println(component.getAccessor().getName());
        }
    }
}
```

```bash
javac RecordAccessorReflectionDemo.java
java RecordAccessorReflectionDemo
```

```text
name
age
```

**Key point:** The accessor names are `name` and `age`, not `getName` or `getAge`. Reflection metadata is a standard way to identify record components.

**Do not use reflection as the default approach for everyday application code** when the static type is already known; calling `user.name()` directly is clearer and more type-safe.

## 34. Do Not Confuse a Record with an Arbitrary `java.lang.Record` Object

Every record class extends `java.lang.Record`, but you cannot write an arbitrary ordinary class that `extends Record` to make it a record.

**Concepts:**

- `record Person(...)` is dedicated language syntax for a record class.
- `java.lang.Record` is the special superclass of record types.
- The `Class.isRecord()` API distinguishes an actual record class.
- Generated members depend on the **record declaration**, not just on the superclass name.

You should not use `java.lang.Record` as a general domain data type if a clearer interface expresses the requirement better.

## 35. A Record Can Override `toString()` to Avoid Exposing Data

A record storing sensitive information may need a cautious display policy. Generated toString normally prints component values, so not every record should be logged directly.

Create **`RecordSafeDisplayDemo.java`**:

```java
record ApiCredential(String user, String token) {
    @Override
    public String toString() {
        return "ApiCredential[user=" + user
                + ", token=REDACTED]";
    }
}

public class RecordSafeDisplayDemo {
    public static void main(String[] args) {
        ApiCredential credential =
                new ApiCredential("service", "secret-value");

        System.out.println(credential);
        System.out.println(credential.user());
    }
}
```

```bash
javac RecordSafeDisplayDemo.java
java RecordSafeDisplayDemo
```

```text
ApiCredential[user=service, token=REDACTED]
service
```

**Important limitation:** Overriding toString **does not protect data from code that has access to the accessor**: `credential.token()` still returns the token. If data is truly sensitive, design access control, storage, and logging at the system level; do not use a toString override as the sole security measure.

## 36. Null Components: Records Do Not Automatically Prohibit Null

Create **`RecordNullComponentDemo.java`**:

```java
record OptionalNote(String text) {
}

public class RecordNullComponentDemo {
    public static void main(String[] args) {
        OptionalNote note = new OptionalNote(null);

        System.out.println(note.text() == null);
        System.out.println(note);
    }
}
```

```bash
javac RecordNullComponentDemo.java
java RecordNullComponentDemo
```

```text
true
OptionalNote[text=null]
```

A record does not prohibit reference components from being null just because the fields are final. If the domain requires non-null, use `Objects.requireNonNull` in the canonical/compact constructor.

**Do not mechanically replace every nullable component with Optional**. Java Optional was designed primarily for return values; for components/serialization, you need to consider tool compatibility and domain semantics.

## 37. When Adding a New Component, What Changes Automatically?

Suppose initially:

```java
record Customer(String name) {
}
```

Then it is changed to:

```java
record Customer(String name, int loyaltyPoints) {
}
```

These are **two illustrative versions replacing each other**, not declared simultaneously.

When adding a component:

- The canonical constructor changes its signature.
- The generated accessor `loyaltyPoints()` appears.
- Generated equals/hashCode/toString take the new component into account.
- Old call sites `new Customer(name)` may fail to compile unless a compatible overloaded constructor is added.
- Serializers, mappers, persisted schemas, and tests may need updating.
- A change in the header can be an **API/schema change**, not merely adding an internal field.

### Keeping the Old Constructor as an Overload

```java
record Customer(String name, int loyaltyPoints) {
    Customer(String name) {
        this(name, 0);
    }
}
```

This is a valid declaration. The old overloaded constructor delegates via `this(name,0)` to the canonical constructor.

**Migration note:** Preserving Java source call sites is not necessarily enough for compatibility with old serialized data or binary compatibility. You need to verify the application's actual integration contract.

## 38. Combining Records with Pattern Matching in Java 17

Java 17 supports pattern matching for `instanceof`, which is useful when code receives a supertype and then checks for a record type.

Create **`RecordInstanceofDemo.java`**:

```java
record Point(int x, int y) {
}

public class RecordInstanceofDemo {
    static String describe(Object object) {
        if (object instanceof Point point) {
            return point.x() + "," + point.y();
        }
        return "not a point";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe("text"));
    }
}
```

```bash
javac RecordInstanceofDemo.java
java RecordInstanceofDemo
```

```text
2,3
not a point
```

In Java 17, this is a **type pattern for instanceof**, not a record deconstruction pattern.

**Version distinction to note:** Record patterns like `case Point(int x,int y)` are not a finalized feature of Java 17; they appear in newer Java versions. When documentation targets Java 17+, use only patterns that compile on Java 17, or clearly state the version when introducing newer features.

## 39. Record Components Are Not All Members of the Class

A record can contain:

- Components (header): generate fields/accessors and participate in value methods.
- Additional instance methods: computation logic.
- Static fields/methods: logic/type-wide data.
- Constructors: initialization/validation.
- Nested types: helpers.

Computed **instance methods** are not automatically included in equals/hashCode/toString. **Static fields** also do not belong to component state and do not determine equality of a record object in generated methods.

Example:

```java
record Invoice(int amount) {
    static final int TAX_PERCENT = 10;

    int total() {
        return amount + amount * TAX_PERCENT / 100;
    }
}
```

This is an **illustrative declaration**.

`amount` is a component; `TAX_PERCENT` is a static constant; `total()` is a derived method. Generated equals compares records by amount, not by a `total` field because that field does not exist.

## 40. When to Choose a Record Instead of a Regular Class?

A record is suitable if:

- The object is primarily a **data value**, not an entity with complex identity/lifecycle.
- The core set of data can be clearly declared in the header.
- Component state does not change after construction.
- Value-like equals/hashCode/toString fit the domain or can be cleanly overridden.
- Mutable components can be guarded if deep immutability is desired.
- You do not need to extend a class, add extra instance fields, or use an instance initializer.
- The API expects accessors named after the components.

An ordinary class is usually more suitable if:

- The object has a **mutable lifecycle** with setters/state transitions.
- Additional instance fields/caches beyond the exposed dataset are needed.
- Inheritance from a specific class is required.
- Equality is based on a business ID and involves complex entity semantics.
- Current frameworks require no-arg constructors/proxy/subclass behaviors incompatible with records.
- You want to encapsulate internal state in a way completely different from a transparent component API.

**Not every DTO has to be a record**, and records do not automatically guarantee deep immutability or validation.

## 41. Comparison Table: Record vs. Hand-Written Class

| Characteristic | Record | Ordinary class |
| --- | --- | --- |
| Declaring data components | In the header | Fields/constructors as designed |
| Corresponding instance fields | Auto-generated `private final` | Declared manually |
| Getter/accessor | Auto-generated `componentName()` | Optional `get...` |
| Canonical constructor | Auto-generated if not defined | No header-based canonical mechanism |
| `equals/hashCode/toString` | Auto-generated from components | Inherited from Object if not overridden |
| Mutating setters | Not generated | Can be written |
| Additional instance fields | No | Yes |
| Extends user-defined class | No | Yes, if the class permits |
| Implement interfaces | Yes | Yes |
| Instance initialization block | No | Yes |
| Static members | Yes | Yes |
| Mutable component references | Possible | Possible |
| Automatic deep immutability | No | No |

Both are Java reference types when creating objects, and both require clear design of invariants, null policy, resource ownership, and thread safety if the domain requires them.

## 42. Common Mistakes

| Mistake | Why It Is Wrong | Correct Approach |
| --- | --- | --- |
| “Records auto-generate `getName()`” | The accessor has the same name as the component | Call `name()` |
| “Records auto-generate setters” | Components are final | Create a new record instance |
| “Components are public fields” | Generated fields are private final | Use the accessor |
| “Having final fields means deep immutability” | A reference may point to a mutable object | Defensive copies/immutable components |
| “Constructors automatically check null/range” | The generated canonical constructor only stores values | Validate explicitly |
| “A compact constructor must assign `this.x`” | Assignment is added by the compiler after the body | Validate/normalize the parameter |
| “You can add instance fields to a record” | Prohibited by Java | Put them in the header or switch to an ordinary class |
| “Records can have instance initializers” | Prohibited by Java | Use the canonical constructor |
| “Adding a component does not change equals” | Generated equals considers all components | Review value semantics |
| “Generated equals deeply compares arrays” | Array equality is identity-based | Custom Arrays equals/hash or change representation |
| “Equal hashes mean equal objects” | Hash collisions can occur | Use equals |
| “`toString` can serve as stable JSON” | It is not a serialization format | Use a dedicated serializer |
| “Records cannot have methods” | Instance/static methods are permitted | Declare methods according to the rules |
| “Records can extend any class” | The superclass is java.lang.Record | Use interfaces/composition |
| “Local records capture outer method variables” | Local records are implicitly static | Pass data through components |
| “Non-canonical record constructors assign fields directly” | Non-canonical constructors must delegate via `this(...)` | Delegate to another constructor |
| “Overriding equals while forgetting hashCode” | Breaks the general contract | Override the matching pair |
| “Record toString is always safe to log” | May expose component values | Apply a safe display/log policy |
| “Records are immutable so they are thread-safe” | Mutable nested objects can still race | Design ownership/synchronization |
| “Generated accessors always clone arrays” | Returns the internal reference by default | Override with a defensive accessor |
| “Reflecting fields is the standard way to inspect components” | Ordinary fields are not record metadata | `getRecordComponents()` |
| “Java 17 supports finalized record deconstruction patterns” | Not finalized in Java 17 | Use accessors/instanceof type patterns |
| “Records fit every DB entity” | Entity identity/proxies/lifecycle may differ | Choose a class if needed |

## 43. A Self-Test Suite Checking Default Members

Create **`RecordGeneratedSelfTest.java`**:

```java
record Item(String code, int count) {
}

public class RecordGeneratedSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Item first = new Item("A", 2);
        Item same = new Item("A", 2);
        Item other = new Item("A", 3);

        check(first.code().equals("A"), "accessor code");
        check(first.count() == 2, "accessor count");

        check(first != same, "different instances");
        check(first.equals(same), "value equals");
        check(!first.equals(other), "unequal value");

        check(first.hashCode() == same.hashCode(),
                "hash contract");
        check(first.toString().equals(
                "Item[code=A, count=2]"), "toString");

        check(Item.class.isRecord(), "isRecord");
        check(Item.class.getRecordComponents().length == 2,
                "component count");

        System.out.println("record generated members PASS");
    }
}
```

```bash
javac RecordGeneratedSelfTest.java
java RecordGeneratedSelfTest
```

```text
record generated members PASS
```

The checks actively throw `AssertionError` on failure without needing to enable JVM `-ea`.

**Test limitation:** It does not measure performance and does not prove that every kind of component has perfect value semantics. When records contain arrays, lists, or custom reference objects, additional tests for copying, equality, and null/invariant contracts are needed.

## 44. Practice: Designing a Record with Validation and a Derived Method

**Requirement:** Create `Product(String code, int price)`, disallow an empty code and a negative price, normalize code with `trim()`, and allow computing the price after a fixed discount of 10 units without becoming negative.

### Reference Solution

Create **`RecordProductExercise.java`**:

```java
import java.util.Objects;

record Product(String code, int price) {
    Product {
        code = Objects.requireNonNull(code).trim();
        if (code.isEmpty()) {
            throw new IllegalArgumentException("empty code");
        }
        if (price < 0) {
            throw new IllegalArgumentException("negative price");
        }
    }

    int discountedPrice() {
        return Math.max(0, price - 10);
    }
}

public class RecordProductExercise {
    public static void main(String[] args) {
        Product product = new Product(" A1 ", 35);

        System.out.println(product);
        System.out.println(product.discountedPrice());

        try {
            new Product("", 10);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid product");
        }
    }
}
```

```bash
javac RecordProductExercise.java
java RecordProductExercise
```

```text
Product[code=A1, price=35]
25
invalid product
```

**Remarks:** The canonical constructor protects invariants; record components store state; the derived method computes the result without storing a new field. This is a concise value-carrier design aligned with the purpose of records.

## 45. Practice: Finding Errors in a Declaration and Fixing Them

The following snippet is **intentionally invalid** and does not compile:

```java
record InvalidPerson(String name, int age) {
    private int counter; // Invalid: adding an instance field.

    InvalidPerson {
        this.name = name.trim(); // Invalid in a compact constructor.
    }

    void setAge(int age) {
        this.age = age; // Invalid: final component field.
    }
}
```

**Distinct errors:**

1. `counter` is an instance field outside the record components, which is prohibited.
2. Inside a compact constructor, you cannot directly assign the component field `this.name`.
3. `age` is a private final field and cannot be modified in a setter after construction.

### Valid Fix

```java
record Person(String name, int age) {
    Person {
        name = name.trim();

        if (age < 0) {
            throw new IllegalArgumentException("negative age");
        }
    }

    Person withAge(int newAge) {
        return new Person(name, newAge);
    }
}
```

This is an **illustrative record declaration**.

`withAge` does not mutate the current object; instead, it creates a new Person instance. Although the syntax is longer than a setter, the value-like semantics of the record remain clear.

## 46. Review Questions and Answers

**Question 1.** How many components does `record Point(int x, int y)` declare?

*Answer:* Two: `x` of type int and `y` of type int.

**Question 2.** With what modifiers does the compiler generate fields?

*Answer:* The corresponding component fields have `private final`.

**Question 3.** Does the compiler generate `getX()` or `x()`?

*Answer:* `x()`, an accessor with the same name as the component.

**Question 4.** In what order does the generated canonical constructor have its parameters?

*Answer:* Exactly matching the record header order.

**Question 5.** Can `new Point(2,3)` be called when no constructor is explicitly declared?

*Answer:* Yes; the canonical constructor is auto-generated.

**Question 6.** Can `point.x = 5` be assigned after construction?

*Answer:* No; the field is private final.

**Question 7.** Why can two `new Point(1,2)` records evaluate equals as true while `==` is false?

*Answer:* Two instances have different identities but share the same component values.

**Question 8.** Must generated hashCode be equal for equal records?

*Answer:* Yes, according to the equals/hashCode contract.

**Question 9.** Does having equal hashCode prove that records are equal?

*Answer:* No; collisions are valid.

**Question 10.** What does generated `toString()` typically display?

*Answer:* The record name and the name/value of each component.

**Question 11.** Is a record with an `int[]` component automatically deeply immutable?

*Answer:* No. A final field can still point to a mutable array.

**Question 12.** Does a generated array accessor clone the contents?

*Answer:* Not by default; it returns the component reference.

**Question 13.** What does `List.copyOf` in a compact constructor help with?

*Answer:* It takes an unmodifiable snapshot of the list structure when the input is mutable, but it does not deep-copy mutable elements.

**Question 14.** Does generated equals for an array component compare with `Arrays.equals`?

*Answer:* No; default array equals has identity semantics.

**Question 15.** When customizing equals for an array by contents, what else is needed?

*Answer:* A corresponding custom hashCode, and mutable state should be guarded.

**Question 16.** Does a compact constructor have to assign `this.component` manually?

*Answer:* No; the compiler assigns the fields when the body completes.

**Question 17.** How does an explicit canonical constructor differ from a compact constructor?

*Answer:* It writes out the full parameters and manually assigns the final component fields according to the rules.

**Question 18.** What must an overloaded constructor do?

*Answer:* Delegate with `this(...)` to another constructor, ultimately reaching the canonical constructor.

**Question 19.** Can a record add an instance field that is not in the header?

*Answer:* No.

**Question 20.** Can a record declare a static method?

*Answer:* Yes.

**Question 21.** Can a record extend a user-defined class?

*Answer:* No; a record extends `java.lang.Record` by language mechanism and is final.

**Question 22.** Can a record implement interfaces?

*Answer:* Yes.

**Question 23.** Does a local record automatically capture local variables of the enclosing method?

*Answer:* No, a local record is implicitly static; pass values into components.

**Question 24.** Which API tells whether a Class is a record?

*Answer:* `Class.isRecord()`.

**Question 25.** Which API retrieves the list of record components?

*Answer:* `Class.getRecordComponents()`.

**Question 26.** Can a record component be a generic type parameter?

*Answer:* Yes, for example `record Box<T>(T value)`.

**Question 27.** When adding a new component, which generated members change?

*Answer:* The canonical constructor, the new accessor/field, equals/hashCode/toString, and related metadata.

**Question 28.** Does Java 17 have finalized record deconstruction patterns?

*Answer:* No; use component accessors and instanceof type patterns.

**Question 29.** Does a record guarantee that `null` cannot appear in a reference component?

*Answer:* No; validate explicitly if the domain prohibits null.

**Question 30.** In what cases should you choose an ordinary class instead of a record?

*Answer:* When you need a mutable lifecycle, additional instance fields, inheritance, or entity identity semantics that do not fit a transparent value carrier.

## 47. Checklist for Reviewing Record Declarations and Generated Members

- [ ] Does the record header accurately describe the **core components**?
- [ ] Do the component names and order reflect the intended API?
- [ ] Is it understood that component fields are `private final`?
- [ ] Are you avoiding adding instance fields/instance initializers to the record?
- [ ] Are you calling `componentName()` accessors rather than assuming JavaBean getters?
- [ ] Is validation present for null, blank, range, and invariants when needed?
- [ ] If using a compact constructor, do you only normalize parameters and let the compiler assign the component fields?
- [ ] If using an explicit canonical constructor, are all fields assigned exactly once?
- [ ] Do overloaded constructors validly delegate via `this(...)`?
- [ ] Is generated equals/hashCode/toString based on components understood?
- [ ] If customizing equals, does the custom hashCode preserve the contract?
- [ ] Are there array or mutable List/Map components that require defensive copying?
- [ ] If overriding an accessor for a mutable component, are both input and output protected?
- [ ] Are there tests for equality/aliasing on reference components?
- [ ] Could `toString()` expose sensitive information?
- [ ] Are you avoiding using hashCode/toString as a business ID/default serializer?
- [ ] Are derived methods implemented without needing extra instance state?
- [ ] Are static factory/helper methods used when they make the API clearer?
- [ ] If implementing an interface, does the accessor have a valid signature?
- [ ] Are you avoiding expecting to extend a record or having a record extend an ordinary class?
- [ ] Are local/nested records used properly under the implicitly static rule?
- [ ] If using reflection, do you rely on `isRecord/getRecordComponents`?
- [ ] If changing a record header, have callers/serialization/mapping/tests been reviewed?
- [ ] Does code targeting Java 17 avoid record patterns not yet finalized in this version?
- [ ] Does each runnable example have the matching file/public class name, `javac`/`java` commands, and stdout?

---

**Final takeaway:** From a short declaration `record Person(String name, int age) { }`, Java automatically provides **private final component fields**, **public accessors `name()`/`age()`**, a **canonical constructor**, and `equals`, `hashCode`, and `toString` implementations based on the components. This is a mechanism for creating a **transparent data carrier** with value-like semantics, not merely shorthand for a JavaBean. When validation or normalization is needed, use a **compact/explicit canonical constructor**; when derived values are needed, add methods. When components contain arrays, lists, or mutable objects, **do not assume that the record is deeply immutable or that generated equals performs a deep content comparison**: you must define defensive-copy and equality contracts for the domain. Use a record when the core data has a clear, stable set of components and does not require a mutable entity lifecycle; use an ordinary class when the constraints of a record do not fit.
