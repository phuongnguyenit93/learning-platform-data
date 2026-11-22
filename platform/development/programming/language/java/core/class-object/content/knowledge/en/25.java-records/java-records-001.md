# Records for Representing a Named Group of Values in Java

## Learning Objectives

After this lesson, you will be able to:

- Understand that a **record** in Java 17 is a kind of class for representing **a group of values defined by named and typed components** (*record components*).
- Explain why `record Point(int x, int y)` conveys meaning better than an anonymous pair of values or an `Object[]`.
- Read and declare a record header, record body, constructors, component accessors, methods, interfaces, and generic records.
- Use Java-generated members: the canonical constructor, private final component fields, public accessors, `equals`, `hashCode`, and `toString`.
- Distinguish between **object identity (`==`)** and **component-based value equality (`equals`)**; know how to use records as keys/values when components are sufficiently stable.
- Ensure invariants using a **compact canonical constructor** or a normal canonical constructor, normalizing data before writing to record components.
- Understand that a record is **shallowly immutable with respect to component references**, not deeply immutable by default: components of array, mutable list, or mutable object types can still be modified after construction.
- Know how to use `List.copyOf`, defensive copies, and immutable domain components when a safe snapshot is needed, while recognizing the limitations of shallow copies.
- Apply records to calculation results, coordinates, time intervals, search keys, parse results, internal DTOs, and version states.
- Distinguish records from normal classes, mutable entities, enums, generic pairs, maps, arrays, and anonymous/local classes to choose the appropriate type.
- Know the constraints: a record is implicitly `final`, extends `java.lang.Record`, cannot declare additional instance fields or instance initializers, but can have instance methods, static members, and implement interfaces.
- Compile/run Java 17+ examples with clear stdout on your own and complete comprehension check exercises.

> **Version:** Records officially became a standard feature in Java 16 (JEP 395); in Java 17, `--enable-preview` is not required to use records. Standalone examples in this document have file/class names matching the `javac`/`java` commands. Code fragments that are not standalone runnable programs will be explicitly noted.

## 1. What Is a Named Group of Values?

When describing a coordinate, we often need two integers:

~~~java
int x = 4;
int y = 7;
~~~

This is easy to understand in a short method, but if you need to **pass both values across an API**, a programmer might think of an array:

~~~java
int[] point = {4, 7};
~~~

Problem: Is `point[0]` x or y? Who guarantees that the array has exactly two elements? If the caller changes `point[0]`, everywhere holding the same array observes the change.

A Java record lets you **name a group of values**:

~~~java
record Point(int x, int y) {
}
~~~

Now you can write:

~~~java
Point p = new Point(4, 7);
int horizontal = p.x();
int vertical = p.y();
~~~

`p.x()` and `p.y()` express meaning more clearly than `point[0]` and `point[1]`. The compiler ensures that when creating `new Point(...)`, an appropriate value must be provided for each component according to the exact type and order.

**Important mindset:** A record is a **data carrier with type identity**, not an array/list of arbitrary length. It expresses that **that group of values belongs to the same concept in the domain**.

## 2. Structure of a Record Declaration

~~~java
record Person(String name, int age) {
}
~~~

Breakdown:

| Syntax | Role |
| --- | --- |
| `record` | Declares a **record class** |
| `Person` | Type name |
| `String name` | Component `name` of type String |
| `int age` | Component `age` of type int |
| `(String name, int age)` | **Record header**, an ordered list of components |
| `{ }` | Record body, which can be empty or contain valid constructors/methods/members |

For an empty record body, Java provides:

- A private final field for each component.
- An accessor `name()` returning String and `age()` returning int (normally both public).
- A canonical constructor with parameters corresponding to the components in the **exact header order**.
- `equals(Object)`, `hashCode()`, and `toString()` based on the record components.

Therefore:

~~~java
Person p = new Person("Lan", 20);
System.out.println(p.name());
System.out.println(p.age());
System.out.println(p);
~~~

will have well-defined meaning without us having to write boilerplate getters, field assignments, and Object methods. This is only a snippet without an enclosing `main`.

### 2.1. A “Component” Is Different from a Manually Declared Field

When declaring `record Person(String name, int age)`, you have already declared the **state description** in the record header. Do not additionally declare:

~~~java
// private String name; // You cannot add this instance field yourself.
~~~

The backing fields generated by the compiler are kept private final. You write additional methods, valid constructors, or static members when needed — rather than redeclaring component fields.

## 3. Opening Program: Point Record with a Name for Each Value

Save **`RecordPointDemo.java`**:

~~~java
public class RecordPointDemo {
    record Point(int x, int y) {
    }

    public static void main(String[] args) {
        Point start = new Point(4, 7);
        Point end = new Point(10, 3);

        System.out.println("start=" + start);
        System.out.println("x=" + start.x());
        System.out.println("y=" + start.y());
        System.out.println("end=" + end);
    }
}
~~~

Compile and run:

~~~bash
javac RecordPointDemo.java
java RecordPointDemo
~~~

**Stdout (JDK 17):**

~~~text
start=Point[x=4, y=7]
x=4
y=7
end=Point[x=10, y=3]
~~~

Remember:

1. `Point` is declared as a **member record** inside the demo class, so `new Point(...)` is used from `main`.
2. The component accessors are named `x()`/`y()`, **not** `getX()`/`getY()` unless you add those methods yourself.
3. The line `start=Point[x=4, y=7]` comes from the record's generated `toString()`.
4. The two Point objects are independent instances, yet they share the same Point type and the same value equality rules.

## 4. Why Is a “Named Group of Values” Better than `Object[]`, `Map`, or a Generic Pair?

Let's compare three models:

~~~java
Object[] request = {"Lan", 20};
java.util.Map<String, Object> data =
        java.util.Map.of("name", "Lan", "age", 20);
record Person(String name, int age) { }
Person person = new Person("Lan", 20);
~~~

This is a valid fragment if placed inside an appropriate method/block.

### 4.1. Array

- With `Object[]`, the compiler does not know that the 0th element represents name.
- Callers can pass too few/too many elements, mix up positions, or use wrong types and only encounter errors late.
- Array elements can be reassigned.
- `Object[]` does not carry the domain name `Person` by itself.

### 4.2. Map

- A Map is useful when **the set of keys changes dynamically**.
- However, for a fixed two-field structure, string keys `"name"`/`"age"` can be misspelled; values of type Object require casting/validation.
- `Map.of` does not allow mutating the map structure, but it does not automatically make all nested objects immutable.
- A Map may not express “this is a Person” as clearly as a dedicated Java type.

### 4.3. Generic Pair

A `Pair<String,Integer>` expresses **two things going together**, but `first()/second()` or `left()/right()` are less meaningful than `name()/age()`. The `Person` record makes the data model more self-explanatory.

**Rule:** When a group of values has **stable business meaning and components known in advance**, use a specifically named record instead of overusing arrays/maps/pairs. A Map is still good for dynamic metadata, and a Pair can be reasonable in local algorithms.

## 5. Program: A Type Name Prevents Passing Two Data Groups by Mistake

Save **`NamedRecordTypesDemo.java`**:

~~~java
public class NamedRecordTypesDemo {
    record Coordinate(int x, int y) {
    }

    record Size(int width, int height) {
    }

    static String describe(Coordinate point, Size size) {
        return "point=" + point.x() + "," + point.y()
                + "; size=" + size.width() + "x" + size.height();
    }

    public static void main(String[] args) {
        Coordinate where = new Coordinate(2, 5);
        Size dimension = new Size(640, 480);

        System.out.println(describe(where, dimension));

        // describe(dimension, where); // Compile-time type mismatch.
    }
}
~~~

Run:

~~~bash
javac NamedRecordTypesDemo.java
java NamedRecordTypesDemo
~~~

Output:

~~~text
point=2,5; size=640x480
~~~

Even though `Coordinate` and `Size` both hold two integers, Java treats them as **two different types**. The compiler can detect a method call where the two data types are swapped, something that `int[]` or a general generic pair can hardly help us make clear.

## 6. The Canonical Constructor Represents the Full Record State

With:

~~~java
record Temperature(String unit, double value) {
}
~~~

Java generates a corresponding canonical constructor `Temperature(String unit, double value)`. The record header **specifies the parameter list and order**.

~~~java
Temperature sample = new Temperature("C", 24.5);
~~~

Arguments cannot be swapped arbitrarily. Java compile-time type checking verifies types, but if two components have the same type (such as `record Period(int start,int end)`), swapping their order can still compile and cause a business bug.

### 6.1. The Generated Constructor Does Not Automatically Check Domain Rules

`new Temperature(null, Double.NaN)` can be valid in terms of types in an empty record body. A record does not automatically conclude which values are “business-valid”. If invariants are needed, declare a constructor to validate and normalize.

### 6.2. Compact Canonical Constructor

~~~java
record Name(String value) {
    Name {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value");
        }
        value = value.strip();
    }
}
~~~

`Name { ... }` is a **compact constructor**: it does not repeat the parameter list and uses the parameter names from the record header. Java assigns the normalized parameter values to the component fields **after the compact constructor body** according to JLS rules.

Example input checks: blank → exception; `" Lan "` → `"Lan"`.

## 7. Program: A Data Group with Invariants

Save **`RecordValidationDemo.java`**:

~~~java
import java.util.Objects;

public class RecordValidationDemo {
    record User(String username, int age) {
        User {
            Objects.requireNonNull(username, "username");
            username = username.strip();

            if (username.isEmpty()) {
                throw new IllegalArgumentException("empty username");
            }
            if (age < 0 || age > 150) {
                throw new IllegalArgumentException("invalid age");
            }
        }
    }

    public static void main(String[] args) {
        User user = new User("  Lan  ", 20);

        System.out.println("user=" + user);
        System.out.println("username=" + user.username());

        try {
            new User("  ", 20);
        } catch (IllegalArgumentException expected) {
            System.out.println("blank username rejected");
        }

        try {
            new User("Minh", -1);
        } catch (IllegalArgumentException expected) {
            System.out.println("invalid age rejected");
        }
    }
}
~~~

Run:

~~~bash
javac RecordValidationDemo.java
java RecordValidationDemo
~~~

Output:

~~~text
user=User[username=Lan, age=20]
username=Lan
blank username rejected
invalid age rejected
~~~

This approach makes the record object valid right after the constructor completes. If the constructor throws an exception, the creation expression **does not return** a complete User instance to the caller.

**Important:** `Objects.requireNonNull` can throw `NullPointerException`; in the example, only the other two `IllegalArgumentException` cases are caught. Do not assume null and blank produce the same exception type unless the API clearly unifies the policy.

## 8. Normal Canonical Constructor and How It Differs from the Compact Form

You can write the full canonical constructor:

~~~java
record Range(int start, int end) {
    Range(int start, int end) {
        if (start > end) {
            throw new IllegalArgumentException("start > end");
        }
        this.start = start;
        this.end = end;
    }
}
~~~

In a **normal canonical constructor**, you explicitly write the parameters and must initialize each component field according to the rules. In a **compact constructor**, Java automatically assigns the fields from the parameters after the body; do not write `this.start = start` inside a compact body.

Do not declare two canonical constructors with the same signature at the same time for one record. Choose the compact form when validation/normalization is concise, and the normal canonical form if special logic is warranted.

### 8.1. Do Not Leave Validation in Getters

If a record accepts `Range(10,5)` and only checks when `length()` is called, an invalid object could already enter collections, logs, and other layers. Placing invariants of **the data group itself** right in the constructor is usually more correct.

## 9. Program: A Record for a Value Range

Save **`RecordRangeDemo.java`**:

~~~java
public class RecordRangeDemo {
    record Range(int start, int end) {
        Range {
            if (start > end) {
                throw new IllegalArgumentException("start > end");
            }
        }

        boolean contains(int value) {
            return value >= start && value <= end;
        }

        long length() {
            return (long) end - start + 1L;
        }
    }

    public static void main(String[] args) {
        Range range = new Range(3, 8);

        System.out.println("range=" + range);
        System.out.println("contains 5=" + range.contains(5));
        System.out.println("contains 10=" + range.contains(10));
        System.out.println("length=" + range.length());

        try {
            new Range(10, 2);
        } catch (IllegalArgumentException expected) {
            System.out.println("reversed range rejected");
        }
    }
}
~~~

Run:

~~~bash
javac RecordRangeDemo.java
java RecordRangeDemo
~~~

Output:

~~~text
range=Range[start=3, end=8]
contains 5=true
contains 10=false
length=6
reversed range rejected
~~~

Casting to `long` **before** subtraction helps avoid intermediate overflow of the two int values. This is an example of domain-specific instance methods based on components, without needing additional instance fields.

## 10. Generated Accessors Differ from JavaBeans Getters

With `record Book(String title, int pages)`:

~~~java
Book book = new Book("Java", 300);
String title = book.title();
int pages = book.pages();
~~~

The compiler generates public methods with the exact **component names**: `title()` and `pages()`. It does not automatically generate `getTitle()`, `getPages()`, or `setTitle()`.

If you need to integrate with a framework that requires JavaBeans getters, check whether the framework supports records or add a separate adapter/accessor method if appropriate. Do not declare a setter to make a final component field mutable.

### 10.1. You Can Declare Custom Methods with Other Names

~~~java
record Book(String title, int pages) {
    boolean longBook() {
        return pages > 500;
    }

    String label() {
        return title + " (" + pages + " pages)";
    }
}
~~~

A record is not restricted to having only field accessors. It can contain **derived methods** that do not modify component values.

## 11. Program: Behavior Computed from Record Components

Save **`RecordDerivedMethodsDemo.java`**:

~~~java
public class RecordDerivedMethodsDemo {
    record Rectangle(int width, int height) {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("negative size");
            }
        }

        long area() {
            return (long) width * height;
        }

        long perimeter() {
            return 2L * (width + (long) height);
        }

        boolean square() {
            return width == height;
        }
    }

    public static void main(String[] args) {
        Rectangle a = new Rectangle(4, 3);
        Rectangle b = new Rectangle(5, 5);

        System.out.println("a area=" + a.area());
        System.out.println("a perimeter=" + a.perimeter());
        System.out.println("a square=" + a.square());
        System.out.println("b square=" + b.square());
    }
}
~~~

Run:

~~~bash
javac RecordDerivedMethodsDemo.java
java RecordDerivedMethodsDemo
~~~

Output:

~~~text
a area=12
a perimeter=14
a square=false
b square=true
~~~

The methods do not store additional `area`/`perimeter` instance fields. Results are computed from the components; this keeps the **record representation exactly as width + height**.

If a computation is expensive and requires a mutable per-instance cache, a normal class may be more suitable, because a record does not allow declaring additional instance fields. An external cache can be used, but you should evaluate lifecycle, equality, and complexity instead of trying to work around record rules.

## 12. Value Equality: `equals` and `==` Are Different

Records are widely used as **value objects**: two separate instances with equal components will be considered equal by `equals` according to record rules.

~~~java
record Point(int x, int y) {
}

Point first = new Point(2, 3);
Point second = new Point(2, 3);
~~~

- `first == second` is normally `false` because `new` creates two different object instances.
- `first.equals(second)` is `true` because they have the same record type and components with equal values.
- `first.hashCode() == second.hashCode()` must be true according to the hashCode contract when equals is true.
- `first.toString()` displays the record name/components in the format of the record API.

**Do not equate equals with a deep structural comparison of every object graph**. If a component is an array, the generated equality uses the semantics of the array reference component, and does not automatically call `Arrays.equals`.

### 12.1. Component Order Is Part of the Record Shape

`record Pair(int left,int right)` has the generated constructor `Pair(int left,int right)`. `new Pair(2,3)` differs in value from `new Pair(3,2)`. Names and order give the code/API meaning. When changing component order, source callers might not be caught by the compiler if the types are the same — API evolution and tests must be managed.

## 13. Program: Identity, Equality, and HashSet

Save **`RecordEqualityDemo.java`**:

~~~java
import java.util.HashSet;
import java.util.Set;

public class RecordEqualityDemo {
    record Key(String code, int revision) {
    }

    public static void main(String[] args) {
        Key first = new Key("A", 1);
        Key sameValue = new Key("A", 1);
        Key other = new Key("A", 2);

        System.out.println("same instance=" +
                (first == sameValue));
        System.out.println("equal values=" +
                first.equals(sameValue));
        System.out.println("different revision=" +
                first.equals(other));
        System.out.println("equal hashes=" +
                (first.hashCode() == sameValue.hashCode()));

        Set<Key> keys = new HashSet<>();
        keys.add(first);
        keys.add(sameValue);
        keys.add(other);

        System.out.println("set size=" + keys.size());
        System.out.println("contains equivalent=" +
                keys.contains(new Key("A", 1)));
    }
}
~~~

Run:

~~~bash
javac RecordEqualityDemo.java
java RecordEqualityDemo
~~~

Output:

~~~text
same instance=false
equal values=true
different revision=false
equal hashes=true
set size=2
contains equivalent=true
~~~

Do not print the raw `HashSet` to avoid depending on unguaranteed iteration order. `Set` eliminates value-duplicates because `equals`/`hashCode` of records are based on components.

**Limitation:** If a mutable component participating in hash/equality can change after being stored in a HashSet/HashMap, that record is no longer a safe key. Only use it as a key when **equality-relevant state is stable**.

## 14. A Record Is Not Automatically Deeply Immutable

Consider:

~~~java
record Picture(int[] pixels) {
}
~~~

`pixels` is a record component; the final backing field only prevents replacing the reference inside the object according to the rules. However:

~~~java
int[] source = {1, 2};
Picture p = new Picture(source);
source[0] = 9;
System.out.println(p.pixels()[0]); // 9
~~~

The exact same array object is referenced by `source` and `p.pixels()`. A record **does not automatically clone the array**.

Similarly:
- `record R(List<MutableItem> items)` can still observe mutations of MutableItem.
- `record R(Date date)`: if using mutable `java.util.Date`, a caller holding an alias can modify the state.
- `record R(StringBuilder text)` holds a mutable StringBuilder.
- `record R(LocalDate date)` shares `LocalDate` safely with respect to mutation because LocalDate is immutable.

**Shallow immutability** differs from **deep immutability**. This is one of the most important notes when using records to represent data.

## 15. Counterexample Program: A Record Holding the Same Mutable Object

Save **`RecordMutableComponentDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordMutableComponentDemo {
    record Basket(List<String> items) {
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket basket = new Basket(source);

        source.add("B");
        basket.items().add("C");

        System.out.println("source=" + source);
        System.out.println("basket=" + basket.items());
        System.out.println("same list=" +
                (source == basket.items()));
    }
}
~~~

Run:

~~~bash
javac RecordMutableComponentDemo.java
java RecordMutableComponentDemo
~~~

Output:

~~~text
source=[A, B, C]
basket=[A, B, C]
same list=true
~~~

Even though the record component `items` has a final backing field, the default accessor returns **a reference to the same list**. Callers can mutate the list. Therefore, `record` does not replace defensive copying when an API promises a snapshot.

## 16. Choosing an Immutable Snapshot for a Named Group of Values

When a record represents a **snapshot**, copy the mutable input structure:

~~~java
record Basket(List<String> items) {
    Basket {
        items = List.copyOf(items);
    }
}
~~~

This is a compact constructor. `List.copyOf` creates an unmodifiable representation of the structure and does not allow null elements. Because String is immutable, a `List<String>` like the example is usually sufficiently stable after copying the structure.

**However**, `List.copyOf` does not deep-copy custom mutable elements; `List<MutableItem>` still keeps the same element references. If a deep snapshot is needed, convert each item into an immutable value record/DTO before copying the list.

### 16.1. Record + Immutable List Snapshot Program

Save **`RecordListSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class RecordListSnapshotDemo {
    record Basket(List<String> items) {
        Basket {
            items = List.copyOf(items);
        }

        int count() {
            return items.size();
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("A"));
        Basket snapshot = new Basket(source);

        source.add("B");

        System.out.println("source=" + source);
        System.out.println("snapshot=" + snapshot.items());
        System.out.println("snapshot count=" + snapshot.count());

        try {
            snapshot.items().add("C");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshot cannot add");
        }
    }
}
~~~

Run:

~~~bash
javac RecordListSnapshotDemo.java
java RecordListSnapshotDemo
~~~

Output:

~~~text
source=[A, B]
snapshot=[A]
snapshot count=1
snapshot cannot add
~~~

The source list remains mutable, but Basket holds a snapshot structure from the time of construction. Because the elements are immutable Strings, mutating the list or String values via an alias does not change the snapshot.

### 16.2. At Which Boundary to Take a Snapshot?

An API receiving mutable input needs to consider whether the caller keeps a reference. If so and the record promises its own snapshot, copy in the constructor. If the accessor returns a sufficiently stable immutable list, it can return the same list; it does not necessarily have to copy on every call. For primitive arrays, copying is usually needed both on input **and** output.

## 17. Array Components: Distinguishing Snapshot and Equality Semantics

A record like `record Bytes(byte[] data) {}` does **not** automatically copy `byte[]`. The default accessor `data()` returns a reference to the array that the component field holds. If snapshot protection is needed, a record can explicitly specify both boundaries:

~~~java
record Bytes(byte[] data) {
    Bytes {
        data = java.util.Objects.requireNonNull(data).clone();
    }

    @Override
    public byte[] data() {
        return data.clone();
    }
}
~~~

This is a valid **record declaration**, not a program with `main`. The compact constructor replaces the parameter with a clone before Java assigns it to the field; the explicit accessor returns a clone so as not to expose state.

**Distinguish two problems:** defensive copying blocks mutation via aliases, but generated `equals/hashCode` still compares array components by **array reference semantics**, rather than automatically comparing contents like `Arrays.equals`. Value equality cases, hash-based collections, and custom equals/hashCode are covered in the dedicated lesson **“equals(), hashCode(), toString(), and the Impact of Array Components”**. The relationship between shallow/deep immutability is covered in the lesson **“Records Only Guarantee Shallow Immutability”**.

## 18. Program: Array Defensive Copy and State Isolation

Save **`RecordArrayDefensiveDemo.java`**:

~~~java
import java.util.Arrays;

public class RecordArrayDefensiveDemo {
    record Payload(int[] values) {
        Payload {
            values = values.clone();
        }

        @Override
        public int[] values() {
            return values.clone();
        }

        int total() {
            return Arrays.stream(values).sum();
        }
    }

    public static void main(String[] args) {
        int[] input = {1, 2, 3};
        Payload payload = new Payload(input);

        input[0] = 9;
        int[] outgoing = payload.values();
        outgoing[1] = 8;

        System.out.println("input=" + Arrays.toString(input));
        System.out.println("outgoing=" + Arrays.toString(outgoing));
        System.out.println("stored total=" + payload.total());
    }
}
~~~

Run:

~~~bash
javac RecordArrayDefensiveDemo.java
java RecordArrayDefensiveDemo
~~~

Output:

~~~text
input=[9, 2, 3]
outgoing=[1, 8, 3]
stored total=6
~~~

The sum 6 proves the internal array was not affected by the two external mutations. **Do not infer** that two Payload objects with equal array contents will automatically evaluate `equals` to true; record-generated equality for array components uses array reference identity semantics.

## 19. Records with Nested Immutable Values

A record can group other records to create structured data:

~~~java
record Point(int x, int y) { }
record Segment(Point from, Point to) { }
~~~

`Point` only contains primitives, so it has stable value semantics and no mutable children. `Segment` only contains Point references, and if the two Points are truly immutable, the Point objects can be **shared** without cloning.

There is no mandatory “deep copy everything” just because nested references exist. The question is **whether the referenced objects can be mutated or not**.

### 19.1. Immutable Record Graph Program

Save **`NestedRecordValuesDemo.java`**:

~~~java
public class NestedRecordValuesDemo {
    record Point(int x, int y) {
        Point translated(int dx, int dy) {
            return new Point(x + dx, y + dy);
        }
    }

    record Segment(Point from, Point to) {
        Segment {
            if (from == null || to == null) {
                throw new IllegalArgumentException("null endpoint");
            }
        }

        int dx() {
            return to.x() - from.x();
        }
    }

    public static void main(String[] args) {
        Point origin = new Point(1, 1);
        Segment first = new Segment(origin, new Point(4, 1));
        Segment second = new Segment(
                origin, origin.translated(0, 3));

        System.out.println("first dx=" + first.dx());
        System.out.println("second dx=" + second.dx());
        System.out.println("shared from=" +
                (first.from() == second.from()));

        Point moved = origin.translated(10, 0);
        System.out.println("old origin=" + origin);
        System.out.println("new point=" + moved);
    }
}
~~~

Run:

~~~bash
javac NestedRecordValuesDemo.java
java NestedRecordValuesDemo
~~~

Output:

~~~text
first dx=3
second dx=0
shared from=true
old origin=Point[x=1, y=1]
new point=Point[x=11, y=1]
~~~

The two Segments both hold the origin Point reference without being altered by updates, because `translated` creates a new value. With primitive ints in the record, there is no mutation setter.

## 20. Generic Records: A Named Data Group That Preserves Type Safety

A record can declare its own type parameters:

~~~java
record Response<T>(T payload, int status) {
}
~~~

Usage:

~~~java
Response<String> text = new Response<>("OK", 200);
Response<Integer> count = new Response<>(42, 200);
~~~

Benefit: one **data group pattern** can be used with many payload types, while component names remain meaningful as `payload`/`status`.

### 20.1. When Is a Generic Record Not Enough?

If `Response<T>` allows any T, a caller can still pass in a mutable T object. A generic record does not automatically copy T or make T immutable. API documentation, type constraints, conversion to immutable values, or defensive copying is needed when the domain requires it.

## 21. Program: Generic Record with a Method

Save **`GenericRecordDemo.java`**:

~~~java
import java.util.Objects;

public class GenericRecordDemo {
    record Box<T>(T value, String label) {
        Box {
            Objects.requireNonNull(value, "value");
            Objects.requireNonNull(label, "label");
        }

        String describe() {
            return label + "=" + value;
        }
    }

    public static void main(String[] args) {
        Box<Integer> one = new Box<>(17, "version");
        Box<String> two = new Box<>("ready", "state");

        System.out.println(one.describe());
        System.out.println(two.describe());
        System.out.println("integer value=" + one.value());
    }
}
~~~

Run:

~~~bash
javac GenericRecordDemo.java
java GenericRecordDemo
~~~

Output:

~~~text
version=17
state=ready
integer value=17
~~~

`Box<Integer>` does not turn Integer into a primitive field (generic erasure/boxing still applies). The record header defines the components, while the `Box<T>` type parameter maintains compile-time type consistency.

## 22. Records Can Implement Interfaces

A record implicitly extends `java.lang.Record`, so it cannot explicitly extend another normal superclass, but it can `implements` interfaces:

~~~java
interface Identified {
    String id();
}

record UserId(String id) implements Identified {
}
~~~

The generated accessor `id()` satisfies the contract of the `Identified` interface if visibility/type/signature match. This is how a record serves as a value object in a polymorphic API.

### 22.1. Complete Program

Save **`RecordInterfaceDemo.java`**:

~~~java
public class RecordInterfaceDemo {
    interface Measurable {
        long area();
    }

    record Rectangle(int width, int height)
            implements Measurable {
        Rectangle {
            if (width < 0 || height < 0) {
                throw new IllegalArgumentException("size");
            }
        }

        @Override
        public long area() {
            return (long) width * height;
        }
    }

    static void report(Measurable measure) {
        System.out.println("area=" + measure.area());
    }

    public static void main(String[] args) {
        Measurable small = new Rectangle(3, 4);
        Measurable large = new Rectangle(5, 6);

        report(small);
        report(large);
    }
}
~~~

Run:

~~~bash
javac RecordInterfaceDemo.java
java RecordInterfaceDemo
~~~

Output:

~~~text
area=12
area=30
~~~

Although the caller views them through `Measurable`, the underlying objects are still record instances. A record is a class, so it integrates with standard Java polymorphism through interfaces.

## 23. Local Records: A Data Group Specific to a Block

If a group of data is only used within a single method, you can declare a **local record** (Java 17):

~~~java
void process() {
    record Entry(String key, int count) {
    }

    Entry entry = new Entry("A", 2);
    System.out.println(entry);
}
~~~

A local record has the lexical scope of the block; it is not a member type accessible via `Outer.Entry` from an outer class. It is **implicitly static**: it does not capture outer locals/instance state like a normal local class.

Incorrect example (commented out):

~~~java
void process(int bonus) {
    // record Entry(int score) {
    //     int total() { return score + bonus; } // Does not capture bonus.
    // }
}
~~~

The right way: pass `bonus` as a component or a method argument, because a record requires **explicit data flow**.

### 23.1. Runnable Program

Save **`LocalRecordDemo.java`**:

~~~java
public class LocalRecordDemo {
    static void summarize(int base, int bonus) {
        record Calculation(int base, int bonus) {
            int total() {
                return base + bonus;
            }
        }

        Calculation result = new Calculation(base, bonus);
        System.out.println("summary=" + result);
        System.out.println("total=" + result.total());
    }

    public static void main(String[] args) {
        summarize(10, 5);
    }
}
~~~

Run:

~~~bash
javac LocalRecordDemo.java
java LocalRecordDemo
~~~

Output:

~~~text
summary=Calculation[base=10, bonus=5]
total=15
~~~

`Calculation` is a local type, yet its object does not necessarily live only within the stack frame; if returned via an interface/Object or if its reference is stored elsewhere, the record instance can outlive the method. “Local” refers to source name scope, not a special allocation/GC rule.

## 24. A Member Record Is an Implicitly Static Nested Type

If a record is declared inside a class:

~~~java
class Container {
    record Item(String name, int count) {
    }
}
~~~

Then `Item` is a **member record**, implicitly static, and does not need an enclosing Container object to be instantiated:

~~~java
Container.Item item = new Container.Item("A", 3);
~~~

Do not write `container.new Item(...)` because a member record is not a non-static inner class. When external code needs to use it, the visibility of Container/Item and the constructor must satisfy Java access control.

### 24.1. Nested Record Program

Save **`MemberRecordDemo.java`**:

~~~java
public class MemberRecordDemo {
    static class Store {
        private final String name;

        Store(String name) {
            this.name = name;
        }

        record Item(String sku, int quantity) {
        }

        Item newItem(String sku, int quantity) {
            return new Item(sku, quantity);
        }

        String name() {
            return name;
        }
    }

    public static void main(String[] args) {
        Store store = new Store("Main");
        Store.Item item = store.newItem("PEN", 3);
        Store.Item another = new Store.Item("BOOK", 2);

        System.out.println("store=" + store.name());
        System.out.println("item=" + item);
        System.out.println("another=" + another);
    }
}
~~~

Run:

~~~bash
javac MemberRecordDemo.java
java MemberRecordDemo
~~~

Output:

~~~text
store=Main
item=Item[sku=PEN, quantity=3]
another=Item[sku=BOOK, quantity=2]
~~~

`Store.Item` is a nested record and can be created directly; `Store.newItem` calling the constructor is merely a convenience method and does not provide an implicit enclosing instance to Item.

## 25. Records Are Not Mutable Entities

An entity typically has a **stable business identity** and mutable state:

- An account with a changing balance.
- An order with states NEW/PAID/SHIPPED.
- A session being refreshed.
- A JPA/ORM object needing specialized lifecycle/instrumentation.

A record is **not** an automatic replacement for every mutable entity. Record component fields are final, the record class is final, and there are no setters to reassign them.

However, records can be very useful as:
- An **immutable snapshot** of an entity at time T.
- Value objects such as Money, Coordinate, and DateRange.
- Response DTOs for APIs and event payloads.
- Validated command parameters.
- Projections when retrieving a subset of data from a query.
- Stable, durable keys for hash collections.

### 25.1. “Updating a Record” by Creating a New Value

Instead of `point.setX(9)`, create a new Point:

~~~java
record Point(int x, int y) {
    Point withX(int nextX) {
        return new Point(nextX, y);
    }
}
~~~

The *value evolution* mindset: the old object keeps the old value, while the new object describes the new state.

## 26. Program: Modifying by Creating a New Instance

Save **`RecordWithMethodDemo.java`**:

~~~java
public class RecordWithMethodDemo {
    record Settings(String theme, int size) {
        Settings {
            if (size <= 0) {
                throw new IllegalArgumentException("size");
            }
        }

        Settings withTheme(String next) {
            return new Settings(next, size);
        }

        Settings withSize(int next) {
            return new Settings(theme, next);
        }
    }

    public static void main(String[] args) {
        Settings oldValue = new Settings("light", 12);
        Settings dark = oldValue.withTheme("dark");
        Settings larger = dark.withSize(16);

        System.out.println("old=" + oldValue);
        System.out.println("dark=" + dark);
        System.out.println("larger=" + larger);
        System.out.println("same object=" + (oldValue == dark));
    }
}
~~~

Run:

~~~bash
javac RecordWithMethodDemo.java
java RecordWithMethodDemo
~~~

Output:

~~~text
old=Settings[theme=light, size=12]
dark=Settings[theme=dark, size=12]
larger=Settings[theme=dark, size=16]
same object=false
~~~

`withTheme`/`withSize` are **not generated record methods**; they are declared by the programmer to make the API expressive. If the next value equals the old value, a method may choose to return `this` when the contract allows, but the demo code creates a new object each time to illustrate the semantics.

## 27. Combining Records with Enums to Represent Named State

A record can hold an enum component to represent a finite set of states:

~~~java
enum Status { NEW, DONE }
record Task(String title, Status status) { }
~~~

Then `Task` holds a group of values carrying business meaning: title and status. Enum constants such as Status.NEW are shared; if the enum only has immutable state, this fits well with record value representation.

### 27.1. Integrated Program

Save **`RecordWithEnumDemo.java`**:

~~~java
import java.util.Objects;

public class RecordWithEnumDemo {
    enum Status {
        NEW, DONE
    }

    record Task(String title, Status status) {
        Task {
            Objects.requireNonNull(title, "title");
            Objects.requireNonNull(status, "status");
        }

        Task completed() {
            return new Task(title, Status.DONE);
        }
    }

    public static void main(String[] args) {
        Task initial = new Task("Study", Status.NEW);
        Task finished = initial.completed();

        System.out.println("initial=" + initial);
        System.out.println("finished=" + finished);
        System.out.println("same title=" +
                initial.title().equals(finished.title()));
    }
}
~~~

Run:

~~~bash
javac RecordWithEnumDemo.java
java RecordWithEnumDemo
~~~

Output:

~~~text
initial=Task[title=Study, status=NEW]
finished=Task[title=Study, status=DONE]
same title=true
~~~

This is an example of a record acting as a **snapshot value**: the initial object is not mutated when the Task is “completed”; the method returns a new Task value. If a domain entity needs state transitions with side effects/transactions, a record can serve as a DTO/snapshot, while lifecycle rules reside in the service/aggregate.

## 28. Collections and Using a Record as a Map Key

When a record has immutable components, the generated `equals/hashCode` makes it very natural to use as a HashMap key:

~~~java
record Coordinate(int x, int y) { }
java.util.Map<Coordinate, String> labels = new java.util.HashMap<>();
labels.put(new Coordinate(1, 2), "A");
String value = labels.get(new Coordinate(1, 2));
~~~

An equal value key will look up the entry. You do not need to keep the exact object key reference that was inserted.

### 28.1. Complete Program

Save **`RecordMapKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class RecordMapKeyDemo {
    record Coordinate(int x, int y) {
    }

    public static void main(String[] args) {
        Map<Coordinate, String> labels = new HashMap<>();
        labels.put(new Coordinate(1, 2), "Home");
        labels.put(new Coordinate(3, 4), "Office");

        System.out.println("lookup=" +
                labels.get(new Coordinate(1, 2)));
        System.out.println("size=" + labels.size());
        System.out.println("missing=" +
                labels.get(new Coordinate(9, 9)));
    }
}
~~~

Run:

~~~bash
javac RecordMapKeyDemo.java
java RecordMapKeyDemo
~~~

Output:

~~~text
lookup=Home
size=2
missing=null
~~~

Do not use mutable List/array references as equality-relevant components if a stable key is needed without protecting the corresponding data. Records do not automatically “freeze” nested objects to keep hashCode stable.

## 29. What Is a Record Allowed and Not Allowed to Declare?

| Capability | Java 17 Record | Notes |
| --- | --- | --- |
| Component header | Yes | Describes named state |
| Compiler-generated component fields | Yes, private final | Do not declare duplicate ones yourself |
| Generated accessors | Yes | `componentName()` |
| Canonical constructor | Yes | Implicit, normal, or compact |
| Other constructors | Yes | Must delegate via `this(...)` per rules |
| Instance methods | Yes | Behavior from components |
| Static fields/methods | Yes | Cannot add arbitrary instance state |
| Implement interfaces | Yes | Including appropriate generic interfaces |
| Generic type parameters | Yes | `record Box<T>(T value)` |
| Member nested/local declarations | Yes | Per rules, member/local records are implicitly static |
| Additional instance fields | **No** | Record state must be described via components |
| Instance initializer block `{...}` | **No** | Use constructors |
| Declaring `extends SomeClass` | **No** | Implicitly extends `java.lang.Record` |
| Inheriting from another record | **No** | Records are implicitly final |
| Abstract record | **No** | Records cannot be subclassed |
| Setters for backing final fields | **No** | Use a new record object |
| Custom `equals/hashCode/toString` | Yes | Must preserve contract and semantics |
| Mutable-type components | Yes | But not automatically deeply immutable |

### 29.1. Invalid Lines (Commented Out)

~~~java
record Invalid(int x) {
    // private int extra; // Compile-time error: additional instance field.
    // { System.out.println("init"); } // Invalid instance initializer.
    // void setX(int n) { this.x = n; } // Final component field.
}

// record Derived(int n) extends Base { } // Records do not have an extends clause.
~~~

The reason is not that “a record is not a class”. A record **is a special class** with a commitment to a transparent data model based on components, so it restricts instance representation outside the header.

## 30. Distinguishing Records from Lombok `@Data` or Handwritten POJOs

A conceptually equivalent normal Java class might need:

~~~java
final class PointClass {
    private final int x;
    private final int y;

    PointClass(int x, int y) {
        this.x = x;
        this.y = y;
    }

    int x() {
        return x;
    }

    int y() {
        return y;
    }

    // equals, hashCode, toString would have to be written manually
    // if component-value semantics are desired.
}
~~~

In the record `record Point(int x,int y) {}`, the Java language/compiler generates most of that boilerplate. Compared to codegen from a library, record semantics are **defined by the Java Language Specification** and run on a supporting JDK.

However, a record differs from a mutable JavaBean:
- No no-arg constructor + step-by-step setters following the usual convention.
- Final fields, which must be initialized through constructors.
- Final class, cannot serve as a superclass for a subclass entity.
- Even with the same component names, a normal class and a record are two different types.
- Frameworks need to support record constructors/accessors instead of assuming bean-style getters/setters.

**Do not replace a POJO/entity with a record just to save lines of code** if record semantics do not fit the business lifecycle.

## 31. Custom Accessors and Normalization: Must Stay Consistent

You can declare a component accessor manually to change the value-returning logic:

~~~java
record Name(String value) {
    Name {
        value = value.strip();
    }

    @Override
    public String value() {
        return value;
    }
}
~~~

Here the override has no clear benefit because the generated accessor already returns the same String. In the array example, overriding the accessor to clone is more worthwhile. However, overriding must preserve the **exact return type**, access level, and record semantics.

### 31.1. Custom Object Methods: Risks Alongside Flexibility

If you manually declare `equals`/`hashCode` for different domain equality, they must:
- Be reflexive, symmetric, transitive, and consistent according to the equals contract.
- Have a compatible hashCode: equal objects must have the same hash.
- Be faithful to the components and the purpose of the record representation.
- Not use mutable state that changes while the object serves as a Map key.

Normally, **prefer the generated methods** unless there is a strong technical reason, because generated semantics are a primary benefit of records.

## 32. Multiple Constructors in a Record: Always Delegate to the Canonical Constructor

A record can declare a convenience constructor with a different signature:

~~~java
record Label(String text, int priority) {
    Label(String text) {
        this(text, 0);
    }
}
~~~

A non-canonical constructor must begin with an explicit `this(...)` invocation to a constructor of the same record. It is not allowed to “assign directly” to the component fields like a normal constructor with a mutable representation.

### 32.1. Runnable Program

Save **`RecordConstructorOverloadDemo.java`**:

~~~java
public class RecordConstructorOverloadDemo {
    record Label(String text, int priority) {
        Label {
            if (text == null || text.isBlank()) {
                throw new IllegalArgumentException("text");
            }
        }

        Label(String text) {
            this(text, 0);
        }
    }

    public static void main(String[] args) {
        Label defaultPriority = new Label("A");
        Label urgent = new Label("B", 10);

        System.out.println("default=" + defaultPriority);
        System.out.println("urgent=" + urgent);
    }
}
~~~

Run:

~~~bash
javac RecordConstructorOverloadDemo.java
java RecordConstructorOverloadDemo
~~~

Output:

~~~text
default=Label[text=A, priority=0]
urgent=Label[text=B, priority=10]
~~~

Thanks to `this(text,0)`, all paths go through the compact canonical constructor and thus apply the same validation rule. If additional convenience constructors are added, invariants must be kept consistent.

## 33. Records and Serialization / JSON / Databases

Records are often suitable as DTOs, but serialization/deserialization depends on the framework:

- JSON libraries need to support record canonical constructors/component names.
- Validation still needs to run at the boundary rather than simply trusting external data to be correct.
- Adding, renaming, or reordering a component can affect schemas and consumers.
- Generated `toString()` is **not a JSON serializer**, and has no guarantee to be used as a stable protocol.
- Java Object Serialization has special handling for serializable records, but this does not mean every record automatically `implements Serializable` or that all JSON representations are the same.
- If the domain needs ORM entity tracking/proxies/mutable lifecycle, a normal entity class is usually more suitable than a record.

### 33.1. Do Not Parse `toString()` as a Data Format

`new Point(1,2).toString()` produces a readable representation like `Point[x=1, y=2]`, but that is a presentation/debug representation and should not be treated as a public wire protocol. Use a dedicated JSON/schema/format when stable data exchange is needed.

## 34. When **Should** You Use a Record to Represent a Group of Values?

Suitable scenarios:

1. A computation result with multiple parts: `record Stats(long min,long max,double average)`.
2. Coordinates/dimensions: `Point(x,y)`, `Size(width,height)`.
3. Value ranges with invariants: `Range(start,end)`.
4. A query key: `Key(countryCode,customerId)` when both are immutable.
5. A message or event: `Event(id,type,timestamp)` when snapshot semantics are appropriate.
6. An API response with clear fields: `Response(status,payload)`.
7. Intermediate values of an algorithm, especially a local record used only within a method.
8. A composite value object composed of multiple other immutable record components.

Scenarios requiring careful consideration:

- Needing to mutate fields in place, with identity independent of current field values.
- Needing a standard class inheritance hierarchy, proxies, or a no-arg mutable construction convention.
- Having to manage resource lifecycles, listeners, transactions, and mutable graph state.
- Components containing mutable data where ownership/snapshot cannot be determined.
- Having many optional/unordered parameters where constructor calls are easy to mix up; consider a builder/named factory and validation.

## 35. Integrated Program: Records Grouping Quote Data

Save **`RecordQuoteIntegrationDemo.java`**:

~~~java
import java.util.List;
import java.util.Objects;

public class RecordQuoteIntegrationDemo {
    record Item(String sku, long unitPrice, int quantity) {
        Item {
            Objects.requireNonNull(sku, "sku");
            if (unitPrice < 0 || quantity <= 0) {
                throw new IllegalArgumentException("item data");
            }
        }

        long amount() {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    record Quote(String id, List<Item> items) {
        Quote {
            Objects.requireNonNull(id, "id");
            items = List.copyOf(items);
        }

        long total() {
            long sum = 0L;
            for (Item item : items) {
                sum = Math.addExact(sum, item.amount());
            }
            return sum;
        }
    }

    public static void main(String[] args) {
        Quote quote = new Quote("Q1", List.of(
                new Item("PEN", 10, 2),
                new Item("BOOK", 50, 1)));

        System.out.println("quote=" + quote.id());
        System.out.println("lines=" + quote.items().size());
        System.out.println("total=" + quote.total());
        System.out.println("first sku=" +
                quote.items().get(0).sku());
    }
}
~~~

Run:

~~~bash
javac RecordQuoteIntegrationDemo.java
java RecordQuoteIntegrationDemo
~~~

Output:

~~~text
quote=Q1
lines=2
total=70
first sku=PEN
~~~

Analysis:

- `Item` groups SKU, unit price, and quantity into **a named type**, instead of `Object[]`.
- `Item.amount()` computes a derived value from components. `Math.multiplyExact` detects overflow in long multiplication according to the Java contract.
- `Quote` holds the id and list of lines. `List.copyOf` keeps the list structure from being modified via the source list.
- Because Item components are only String/long/int, Item is an immutable value object in practice in this example, so sharing Item references inside `Quote` creates no mutable alias risk.
- If unit price involves currency/decimal precision/rounding, production code should have a Money type/domain rules rather than defaulting to an arbitrary long unit.

## 36. Common Mistakes Table

| Misconception / Mistake | Correct Understanding |
| --- | --- |
| “A record is an array with a different name.” | A record is a **class** with a group of typed, named components. |
| “`Point(1,2)` does not need `new` because a record is a value.” | A Java 17 record is created using `new Point(1,2)` like a class instance. |
| “A record only declares fields and has no methods.” | It can have instance/static methods, constructors, and interfaces. |
| “Accessors are named `getX()`.” | The generated accessor is `x()`. |
| “A record generates a setter for each component.” | No; component fields are private final. |
| “Two `new Point(1,2)` calls will be `==` true.” | No; they are normally two separate instances, while `equals` is true. |
| “Generated equals deeply compares everything.” | Array components are compared by reference; nested mutable elements are not deep-copied. |
| “A record is deeply immutable.” | Only component references are final; nested objects can still be mutable. |
| “Elements cannot be added to a final List component.” | If the list is mutable and the accessor exposes it, adding is still possible. |
| “`List.copyOf` deep-clones mutable Items.” | It only snapshots the structure; Item references are shared. |
| “A record is always a safe HashMap key.” | Only when equality/hash-relevant state is stable. |
| “A record can add an arbitrary instance cache field.” | No; instance state must be described by components. |
| “Instance initializer blocks work like in a regular class.” | Records do not allow instance initializer blocks. |
| “A record can extend a normal superclass.” | No; it implicitly extends `java.lang.Record` and is implicitly final. |
| “A record cannot implement interfaces.” | It can implement interfaces. |
| “A member record requires `outer.new Inner()`.” | A member record is implicitly static and created with `new Outer.Record(...)`. |
| “A local record captures method variables.” | No; pass them via constructor/method params. |
| “A compact constructor needs to assign `this.x = x`.” | No; the compiler assigns them automatically after the body. |
| “A non-canonical constructor assigns fields directly.” | It must delegate using `this(...)`. |
| “No need to validate a record because the compiler does it for you.” | The generated constructor only enforces types; domain invariants must be checked yourself. |
| “A record's toString is a JSON format.” | No; it is a presentation/debug representation. |
| “Records replace all mutable ORM entities.” | No; domain identity/lifecycle may require a normal class. |
| “Swapping the order of same-type components will be blocked by the compiler.” | It can still compile and change meaning; tests/API evolution are needed. |

## 37. Checklist When Designing a Record

- [ ] Do the components have names and types that clearly express **a single domain concept**?
- [ ] Are field names more expressive than `first/second` or `data1/data2`?
- [ ] Is the constructor parameter order easy to mix up when two types are the same?
- [ ] Are there invariants that need to be checked in the compact/normal canonical constructor?
- [ ] Is there a policy for null, blank, negative, overflow, and invalid enum value inputs?
- [ ] Which mutable types do the components reference?
- [ ] Is a defensive copy needed at the input boundary to keep a snapshot?
- [ ] Does the generated accessor expose a mutable internal representation?
- [ ] If using `List.copyOf`, are the elements truly immutable?
- [ ] Are you using an array component while expecting deep array equality?
- [ ] Are `equals/hashCode` stable if placed into a `HashMap`/`HashSet`?
- [ ] Is a method derived from components needed instead of a forbidden instance cache field?
- [ ] Should the record implement a meaningful interface?
- [ ] Is the type local/member/top-level matching its intended usage scope?
- [ ] Are there any frameworks/serializers/ORMs requiring specific support for records?
- [ ] Is there a dedicated wire schema rather than relying on the `toString()` debug representation?
- [ ] If updates are needed, is there an easy-to-understand `with...()` method or factory creating a new record?
- [ ] If mutable identity/entity lifecycle is needed, should a normal class be used instead of a record?
- [ ] Have you verified Java 17, compiler/run commands, and exact stdout?

## 38. Review Exercises with Answers

**Question 1.** What does `record Point(int x,int y)` describe?  
**Answer:** A class with two named components, x of type int and y of type int.

**Question 2.** What is the main difference compared to `int[]`?  
**Answer:** The type name and component names carry meaning; constructor/accessors/type checking are clear.

**Question 3.** How is the constructor that creates a Point record called?  
**Answer:** `new Point(2,3)`.

**Question 4.** What is the name of the generated accessor for x?  
**Answer:** `x()`, it does not automatically generate `getX()`.

**Question 5.** Can you declare `record User(String name,int age){}` without declaring a manual constructor?  
**Answer:** Yes; the compiler generates the canonical constructor.

**Question 6.** Is the generated `equals` used to compare identity or component values?  
**Answer:** It compares by record components; it is not like `==`.

**Question 7.** What does `new Point(2,3)==new Point(2,3)` normally evaluate to?  
**Answer:** False, because the two object identities are different.

**Question 8.** What does `new Point(2,3).equals(new Point(2,3))` evaluate to?  
**Answer:** True, because the component values are equal.

**Question 9.** Can a record be used as a Map key?  
**Answer:** Yes, if the equality/hash-relevant data is stable.

**Question 10.** Why is a mutable component dangerous for a record key?  
**Answer:** Hash/equality can change after the key is stored, breaking lookup invariants.

**Question 11.** Does a record automatically deep-copy an array component?  
**Answer:** No.

**Question 12.** Where do you need to handle keeping an array snapshot?  
**Answer:** Defensive copy at construction and typically in the accessor when returning a mutable array.

**Question 13.** Does the generated equality of an array component automatically compare contents like `Arrays.equals`?  
**Answer:** No; it uses array reference equality semantics.

**Question 14.** What does `List.copyOf` help with in a compact constructor?  
**Answer:** It snapshots the structure into an unmodifiable list without deep-copying elements.

**Question 15.** Can you declare an instance method `area()` in a Rectangle record?  
**Answer:** Yes, computed from components.

**Question 16.** Can a record declare an additional mutable instance cache field?  
**Answer:** No; records forbid additional instance fields.

**Question 17.** Can a record have an instance initializer block `{ ... }`?  
**Answer:** No; use a constructor to validate/normalize.

**Question 18.** Can a record extend another user superclass?  
**Answer:** No; a record extends `java.lang.Record` and is implicitly final.

**Question 19.** Can a record implement an interface?  
**Answer:** Yes.

**Question 20.** Is `record Box<T>(T value)` valid?  
**Answer:** Yes, a record can have generic type parameters.

**Question 21.** Can a local record inside a method directly capture `final int base`?  
**Answer:** No; a local record is implicitly static, so pass base via constructor/method param.

**Question 22.** Does a member record need an Outer instance when created?  
**Answer:** No; a member record is implicitly static.

**Question 23.** When does a compact constructor automatically assign fields?  
**Answer:** After the compact body, from the canonical parameters according to the rules.

**Question 24.** What must a non-canonical constructor do?  
**Answer:** Delegate via explicit `this(...)` to a constructor of the record.

**Question 25.** Where should username normalization be done?  
**Answer:** In the compact/normal canonical constructor, before the record completes.

**Question 26.** Is the `toString()` generated by a record standard JSON?  
**Answer:** No; do not use it as a wire protocol.

**Question 27.** Does a record always replace a mutable database entity?  
**Answer:** No; lifecycle/identity/proxy/mutation requirements may not fit.

**Question 28.** How does a `Settings` record “change theme”?  
**Answer:** Create a new instance using `new Settings(nextTheme, old.size())` or a `withTheme` method.

**Question 29.** Can a record hold an enum constant?  
**Answer:** Yes; this forms value composition and shares enum constants.

**Question 30.** Why is record `Coordinate` different from record `Size` even though both have two ints?  
**Answer:** They have **distinct named Java types**, helping avoid mixing up meaning when calling APIs.

**Question 31.** When should you use a Pair instead of a named record?  
**Answer:** When the pairing is truly generic and temporary, and the names have no specific domain meaning.

**Question 32.** If a JSON library requires a no-arg mutable bean, does a record satisfy it automatically?  
**Answer:** No; you need a framework supporting record constructors or an adapter.

**Question 33.** Does the value `record Task(title,status)` automatically freeze a mutable Status object?  
**Answer:** No; only the component reference is final. With an immutable enum status, it fits well.

**Question 34.** What is the biggest thing a record provides out of the box?  
**Answer:** A **type-safe, named, transparent carrier of component values**, along with generated constructor/accessors/equals/hashCode/toString.

## 39. References

- Java Language Specification Java SE 17, [`8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): nature of records, components, and class-level restrictions.
- JLS 17, [`8.10.1 — Record Components](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.1): names/types/list of components.
- JLS 17, [`8.10.2 — Record Body Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.2): valid members and restrictions on instance fields/blocks.
- JLS 17, [`8.10.3 — Record Members](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.3): generated fields, accessors, Object methods.
- JLS 17, [`8.10.4 — Record Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4): canonical/non-canonical constructors.
- JLS 17, [`8.10.4.2 — Compact Canonical Constructors](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4.2): normalization/implicit component assignment.
- Oracle Java 17 Language Guide, [Record Classes](https://docs.oracle.com/en/java/javase/17/language/records.html): introduction to Java 17 records and examples.
- OpenJDK [JEP 395 — Records](https://openjdk.org/jeps/395): feature standardized in Java 16.
- JLS 17, [`14.3 — Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): local records are implicitly static.
- Java API 17, [java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): base class of records.
- Java API 17, [List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable copy/snapshot semantics.
- Java API 17, [Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): input validation.
- Java API 17, [java.util.HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): equality/hash keys.
- JLS 17, [`17.5 — final Field Semantics](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.5): final fields/JMM, not synonymous with deep immutability.

## Conclusion

**A record is a Java 17 tool for expressing a group of values with names, types, and meaning** using a concise Java class. `record Point(int x,int y)` does more than reduce boilerplate: it declares a clear group of components so that the constructor, accessors, and Object methods operate consistently with the described data.

Use records when you need a **stable value representation**, such as coordinates, value ranges, result DTOs, snapshots, keys, or messages. Place domain invariants in the constructor, use methods derived from components, and choose immutable component types when possible. For mutable arrays/lists/objects, a record **does not automatically deep-copy**: you need to determine ownership and defensive-copy appropriately.

Finally, distinguish records from mutable entities: records are implicitly final, with no additional instance fields or setters for components. If complex mutable identity/lifecycle is needed, a normal class may be more appropriate. The best design is to **name the group of values properly**, clearly declare the components, and ensure equality/immutability matches the contract that API consumers expect.
