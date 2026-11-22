# `toString()` to Represent Objects When Observing a Program in Java

In Java, every object can be **represented as text** so programmers can easily observe its state when running a program, printing to the console, inspecting in a debugger, logging, or including it in a diagnostic message. The foundational method for this is **`toString()`**, declared in the `java.lang.Object` class and typically **overridden** in your own class to produce a meaningful string.

For example, instead of observing:

```text
Student@5acf9800
```

we usually want:

```text
Student{id=12, name='An', active=true}
```

The second string helps you understand the object without needing to expand each field. However, the `Student@5acf9800` example is only an **illustrative form**, not a guaranteed suffix value across every run, every JVM, or every object.

A common way to override it:

```java
@Override
public String toString() {
    return "Student{id=" + id
            + ", name='" + name + "'"
            + ", active=" + active + "}";
}
```

**Keep in mind from the start:**

- `toString()` creates a **`String` representation** of an object; it does not change the object's type.
- `Object.toString()` has a default implementation, but most domain classes should consider a more readable representation.
- `System.out.println(object)` and string concatenation with an object commonly lead to calling `toString()` through the string-conversion mechanism.
- The correct override is **`public String toString()`, with no parameters**, and should use `@Override`.
- `toString()` does not replace `equals()`, `hashCode()`, serialization, or a public API format.
- A good `toString()` is usually **short, consistent, safe, with minimal side effects, and without leaking secrets**.

This lesson belongs to the **`Object` class** section in Java Core, using **Java 17+**, moving from the basic contract to practical printing/logging scenarios: inheritance, arrays, collections, records, enums, `null`, reference cycles, security, performance, and runnable examples with **deterministic stdout**.

## 1. Where is `toString()` declared?

Every regular class in Java has an inheritance relationship to `java.lang.Object` (directly or indirectly). Therefore, an object can use methods from `Object`, including:

```java
public String toString()
```

This is an **instance method**. A class that does not override it still **inherits an implementation** appropriate for it.

For example:

```java
class User {
    private final int id;

    User(int id) {
        this.id = id;
    }
}
```

`User` does not declare `toString()`, so calling `new User(7).toString()` uses the implementation inherited from `Object`.

**This does not mean every object displays the same content.** The runtime class, `hashCode()`, overrides in library classes, and how string-conversion APIs are called can all affect the observed representation.

### Why can `toString()` be called without an explicit extends clause?

```java
class User {
}
```

in terms of the normal superclass relationship, is equivalent to:

```java
class User extends Object {
}
```

If a class extends another superclass, `toString()` can be inherited from that superclass or from `Object` further up in the hierarchy, depending on where the method is overridden.

**Do not mistake `toString()` for a function that only exists on `String`.** It is a method belonging to the `Object` contract, and very many classes provide their own overrides.

## 2. Default representation of `Object.toString()`

The implementation of `Object.toString()` returns a string equivalent to:

```java
getClass().getName() + "@"
        + Integer.toHexString(hashCode())
```

Where:

- `getClass().getName()` is the runtime class name according to the `Class` API, typically the fully qualified name or an appropriate binary name.
- `"@"` is the separator character.
- `Integer.toHexString(hashCode())` converts the `int` value from the `hashCode()` method into an unsigned hexadecimal representation.

Example of the observed form for a `Student` class in the default package:

```text
Student@2f92e0f4
```

**The `2f92e0f4` part is only an example.** Do not write tests asserting this exact string when calling `Object.toString()`. The suffix varies by object, JVM, and `hashCode()` implementation.

### Is the hexadecimal suffix a memory address?

**You should not infer that.** Java does not specify that the suffix is a memory address. It is the **hexadecimal representation of the `hashCode()` value** used by the default implementation of `Object.toString()`.

If a class overrides `hashCode()`, calling `super.toString()` may use the hash value returned by that override. All the more reason the suffix cannot be treated as a reliable memory address.

### Is `Object.toString()` a global identifier key?

No. Two objects can have the same hash code; `hashCode` does not guarantee a unique ID. Do not use the default `Class@hex` string as a database key, request ID, or long-term immutable identifier.

If you need to distinguish objects by business logic, create a **stable ID** or an appropriate value object. If you need identity diagnostics, you can consider `System.identityHashCode` in diagnostic tools, though it also **does not guarantee absolute uniqueness**.

## 3. First program: comparing the default and an override

Save as **`ToStringFirstDemo.java`**:

```java
class PlainStudent {
    private final int id;

    PlainStudent(int id) {
        this.id = id;
    }
}

class Student {
    private final int id;
    private final String name;

    Student(int id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public String toString() {
        return "Student{id=" + id
                + ", name='" + name + "'}";
    }
}

public class ToStringFirstDemo {
    public static void main(String[] args) {
        PlainStudent plain = new PlainStudent(12);
        Student student = new Student(12, "An");

        System.out.println(
                plain.toString().startsWith("PlainStudent@"));
        System.out.println(student.toString());
        System.out.println(student);
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac -encoding UTF-8 ToStringFirstDemo.java
java ToStringFirstDemo
```

**Deterministic stdout:**

```text
true
Student{id=12, name='An'}
Student{id=12, name='An'}
```

Explanation:

1. `PlainStudent` does not override it, so it uses `Object.toString()`; checking `startsWith` avoids depending on the hexadecimal suffix.
2. `Student` overrides `toString()` and returns the designed string.
3. `System.out.println(student)` can display the object's representation without explicitly writing `student.toString()`.
4. The `id` of both objects only appears in the string when the `toString()` logic actually includes it; the default `Object.toString()` **does not automatically traverse fields**.

## 4. Correct override syntax

A standard override:

```java
@Override
public String toString() {
    return "Some readable representation";
}
```

Components:

| Component | Meaning |
| --- | --- |
| `@Override` | Has the compiler check that this is a valid method override |
| `public` | Preserves the public access level of `Object.toString()` |
| `String` | Return type of the method |
| `toString` | Method name with exact spelling and case |
| `()` | Takes no parameters |
| `return ...` | Returns a string representing the object |

**Two common mistakes:**

```java
class Wrong {
    // String toString() { return "Wrong"; }
    // WRONG: reduces visibility from public of Object.toString().
}
```

```java
class OverloadInstead {
    public String toString(String prefix) {
        return prefix + "data";
    }
    // This is a new overload, NOT an override of Object.toString().
}
```

Using `@Override` helps catch mistakes like writing `toString(String)` or `tostring()` if the author thought they were overriding it.

### Is `throws` needed?

`Object.toString()` does not declare checked exceptions. An override must not broaden the list of checked exceptions in violation of overriding rules. Normal string construction does not need to declare `throws Exception`.

## 5. `toString()` is an instance method with dynamic dispatch

`toString()` is not a static method. If a subclass overrides it, Java uses the **implementation matching the runtime class of the receiver**.

```java
Object object = new Student(12, "An");
System.out.println(object.toString());
```

Even though the variable `object` has the declared type `Object`, the runtime object is a `Student`, so the `Student.toString()` override is called.

### Example across three reference types

Save **`ToStringDispatchDemo.java`**:

```java
class Asset {
    private final String code;

    Asset(String code) {
        this.code = code;
    }

    protected String code() {
        return code;
    }

    @Override
    public String toString() {
        return "Asset[" + code + "]";
    }
}

class Vehicle extends Asset {
    Vehicle(String code) {
        super(code);
    }

    @Override
    public String toString() {
        return "Vehicle[" + code() + "]";
    }
}

public class ToStringDispatchDemo {
    public static void main(String[] args) {
        Asset base = new Asset("A");
        Asset vehicle = new Vehicle("V");
        Object view = vehicle;

        System.out.println(base);
        System.out.println(vehicle);
        System.out.println(view);
    }
}
```

```bash
javac -encoding UTF-8 ToStringDispatchDemo.java
java ToStringDispatchDemo
```

Stdout:

```text
Asset[A]
Vehicle[V]
Vehicle[V]
```

The two variables `vehicle` and `view` have different static types, but both reference the runtime `Vehicle` object. Therefore, the `Vehicle.toString()` override is selected when printing both.

### What if a subclass does not override?

When a subclass does not override it, it inherits the nearest appropriate superclass implementation. For example, `class Truck extends Vehicle { ... }` without declaring `toString()` calls the method inherited from `Vehicle`. This is usually reasonable if the superclass representation is still accurate for the subclass; if the subclass adds important information, consider overriding it intentionally.

## 6. How does `System.out.println(object)` work?

`PrintStream.println` has multiple overloads:

```java
println(String value)
println(Object value)
println(int value)
println(char[] value)
...
```

If the argument has a static type of a domain object such as `Student`, the `println(Object)` overload can be selected. It converts the object to a string according to the API's semantics, typically via `String.valueOf(object)`, and then writes the content followed by a newline.

Therefore:

```java
Student student = new Student(12, "An");

System.out.println(student);
System.out.println(student.toString());
```

usually produce the same representation when the receiver is non-null and `toString()` returns a valid String, though **not every overload of `println` behaves the same**. The `char[]` case is a notable counterexample that will be explained later.

### How `print` differs from `println`

`System.out.print(student)` converts the object to text **without automatically adding a newline** after the content.

`System.out.println(student)` converts the object to text and **appends a line terminator** according to PrintStream.

If you write:

```java
System.out.print("Object: ");
System.out.println(student);
```

in the same output stream, the single-line result is `Object: Student{...}`.

## 7. String concatenation: Java converts objects to text

When one operand of the `+` operator is a `String`, Java performs string concatenation and converts the other operand to text according to the **string conversion** rules.

```java
Student student = new Student(12, "An");

String message = "Đang xử lý: " + student;
System.out.println(message);
```

Assuming `Student.toString()` is overridden as in the first example, message will contain the student's representation.

**Note:** the compiler/runtime may implement string concatenation using an appropriate optimization mechanism (Java 17 typically uses invokedynamic for string concatenation). You should not infer that source code `"x" + object` is required to create and use exactly one `StringBuilder` at the bytecode level.

### Runnable: direct, string concatenation, and `String.valueOf`

Save **`ToStringConversionDemo.java`**:

```java
record Point(int x, int y) {
}

public class ToStringConversionDemo {
    public static void main(String[] args) {
        Point point = new Point(2, 3);

        System.out.println(point);
        System.out.println("Point = " + point);
        System.out.println(String.valueOf(point));
    }
}
```

```bash
javac -encoding UTF-8 ToStringConversionDemo.java
java ToStringConversionDemo
```

Stdout:

```text
Point[x=2, y=3]
Point = Point[x=2, y=3]
Point[x=2, y=3]
```

The record here has a compiler-provided `toString()`, so all three ways of observing it use the same deterministic representation.

## 8. `String.valueOf(Object)` and `Objects.toString(Object)`

When an object might be null, calling directly:

```java
value.toString();
```

can cause a `NullPointerException` if `value == null`.

`String.valueOf(Object)` provides a mechanism to convert an **object reference** into a string:

- If the reference is null → returns the text string `"null"`.
- If not null → uses the representation from `toString()`.

`Objects.toString(Object)` also supports null in a common way:

```java
String left = String.valueOf((Object) null);
String right = java.util.Objects.toString(null);
```

Both `left` and `right` are the string `"null"`.

There is a useful overload:

```java
String label =
        java.util.Objects.toString(maybeNull, "<missing>");
```

If `maybeNull` is null, you get `"<missing>"`; if it is non-null, `maybeNull.toString()` is used.

### Java 17 example

Save **`NullSafeToStringDemo.java`**:

```java
import java.util.Objects;

public class NullSafeToStringDemo {
    public static void main(String[] args) {
        Object absent = null;
        Object present = "Java";

        System.out.println(String.valueOf(absent));
        System.out.println(Objects.toString(absent));
        System.out.println(Objects.toString(absent, "(missing)"));
        System.out.println(Objects.toString(present, "(missing)"));
    }
}
```

```bash
javac -encoding UTF-8 NullSafeToStringDemo.java
java NullSafeToStringDemo
```

Stdout:

```text
null
null
(missing)
Java
```

**Do not confuse the string `"null"` with the `null` reference value.** The four-character string is valid data; a null reference does not point to any String object.

## 9. Be careful with overloads of `String.valueOf` and `println`

Java has many overloads, so calls that look similar may be handled differently.

For example, a character array:

```java
char[] chars = {'J', 'a', 'v', 'a'};
System.out.println(chars);
```

`println(char[])` prints **the characters**, rather than using the default array `Object.toString()`.

`String.valueOf(chars)` selects the `String.valueOf(char[])` overload and produces `"Java"`.

Conversely, if you cast:

```java
Object value = chars;
System.out.println(value);
```

the `println(Object)` overload is selected; arrays do not override `Object.toString()` to print their elements automatically, so you typically observe a representation like `[C@...` with a non-fixed suffix.

### Example independent of the suffix

Save **`CharArrayOverloadDemo.java`**:

```java
public class CharArrayOverloadDemo {
    public static void main(String[] args) {
        char[] chars = {'J', 'a', 'v', 'a'};
        Object asObject = chars;

        System.out.println(chars);
        System.out.println(String.valueOf(chars));
        System.out.println(
                asObject.toString().startsWith("[C@"));
    }
}
```

```bash
javac -encoding UTF-8 CharArrayOverloadDemo.java
java CharArrayOverloadDemo
```

Stdout:

```text
Java
Java
true
```

Key takeaway: **overload resolution uses the static type of the expression**, whereas the runtime object's instance `toString()` may produce a different representation. Do not guess the outcome solely from the method name.

## 10. Why should you override `toString()` for domain objects?

An `Order` object might contain an order code, a status, and a line count. The default `Order@hex` representation does not help someone debugging know which order encountered an error.

An appropriate method:

```java
@Override
public String toString() {
    return "Order{id='" + id + "', status=" + status
            + ", lineCount=" + lines.size() + "}";
}
```

helps:
- Identify the object when printing to the console.
- Find related objects in logs.
- Quickly observe state through a debugger or error message.
- Write useful descriptions for diagnostics.
- Reduce repeating multiple `println(field)` statements elsewhere.

**However,** a good representation does not mean putting **every field** into the string. Some fields may be large, have reference cycles, be expensive to access, be unstable, or carry sensitive data.

### Practical goal

A good `toString()` usually answers:

> “What is this object, and what information is sufficient for the reader to understand/trace it, at an acceptable cost and risk?”

It does not necessarily have to answer:

> “What is all the data inside the object, without omitting a single byte?”

## 11. An informative yet balanced `toString()`

Domain example:

```java
final class Task {
    private final long id;
    private final String name;
    private final boolean completed;

    Task(long id, String name, boolean completed) {
        this.id = id;
        this.name = name;
        this.completed = completed;
    }

    @Override
    public String toString() {
        return "Task{id=" + id
                + ", name='" + name + "'"
                + ", completed=" + completed + "}";
    }
}
```

Representation:
- Includes the type name `Task`.
- Contains a useful ID for locating it.
- Includes the `completed` status.
- Does not reveal unnecessary data.

### Runnable

Save **`ReadableObjectDemo.java`**:

```java
final class Task {
    private final long id;
    private final String name;
    private final boolean completed;

    Task(long id, String name, boolean completed) {
        this.id = id;
        this.name = name;
        this.completed = completed;
    }

    @Override
    public String toString() {
        return "Task{id=" + id
                + ", name='" + name + "'"
                + ", completed=" + completed + "}";
    }
}

public class ReadableObjectDemo {
    public static void main(String[] args) {
        Task first = new Task(101, "Java Core", false);
        Task second = new Task(102, "OOP", true);

        System.out.println(first);
        System.out.println("Kiểm tra: " + second);
    }
}
```

```bash
javac -encoding UTF-8 ReadableObjectDemo.java
java ReadableObjectDemo
```

Stdout:

```text
Task{id=101, name='Java Core', completed=false}
Kiểm tra: Task{id=102, name='OOP', completed=true}
```

**Format design has no single mandatory standard for every class.** Braces, commas, and single quotes are simply conventions chosen by the author. What matters is that the representation is clear, fits the domain, and is maintained consistently.

## 12. When an object contains another object

For example:

```java
class Address {
    private final String city;
}

class Customer {
    private final String name;
    private final Address address;
}
```

`Customer.toString()` can call `address.toString()` to represent the nested object. However, you need to consider:
- Can `address` be null?
- Is `Address.toString()` safe and concise?
- Is there a circular back-reference `address.customer`?
- Does printing the entire address expose personal information?

If a full nested representation is not needed, sometimes printing only `address.city()` or an ID is enough.

### Example of safe composition with a nested immutable object

Save **`NestedToStringDemo.java`**:

```java
import java.util.Objects;

record City(String name) {
    City {
        Objects.requireNonNull(name);
    }

    @Override
    public String toString() {
        return name;
    }
}

final class Store {
    private final String code;
    private final City city;

    Store(String code, City city) {
        this.code = Objects.requireNonNull(code);
        this.city = Objects.requireNonNull(city);
    }

    @Override
    public String toString() {
        return "Store{code='" + code + "', city=" + city + "}";
    }
}

public class NestedToStringDemo {
    public static void main(String[] args) {
        Store store = new Store("S01", new City("Hà Nội"));

        System.out.println(store);
    }
}
```

```bash
javac -encoding UTF-8 NestedToStringDemo.java
java NestedToStringDemo
```

Stdout:

```text
Store{code='S01', city=Hà Nội}
```

`Store.toString()` indirectly uses `City.toString()`. The `City` record in the example **provides its own override** to display only the city name; it does not use the default record format.

## 13. Records automatically have `toString()`

Java 17 supports **records**:

```java
record Point(int x, int y) {
}
```

The compiler provides a `toString()` for a record if the record does not declare its own implementation. With two primitive components, the representation takes the form:

```text
Point[x=2, y=3]
```

A record automatically declares its component fields and corresponding methods, and also has implementations for `equals()`, `hashCode()`, and `toString()` conforming to record semantics.

### Runnable record program

Save **`RecordToStringDemo.java`**:

```java
record Point(int x, int y) {
}

record Course(String title, int lessons) {
}

public class RecordToStringDemo {
    public static void main(String[] args) {
        System.out.println(new Point(2, 3));
        System.out.println(new Course("Java", 12));
    }
}
```

```bash
javac -encoding UTF-8 RecordToStringDemo.java
java RecordToStringDemo
```

Stdout:

```text
Point[x=2, y=3]
Course[title=Java, lessons=12]
```

**There is no need to manually override every record just to print component names.** The default representation can be sufficient for diagnostics.

### Can you override `toString()` in a record?

Yes:

```java
record Product(String sku, int price) {
    @Override
    public String toString() {
        return sku + " (" + price + ")";
    }
}
```

However, if the custom format serves an **external API**, consider a separate method such as `toDisplayText()` instead of making the system's entire contract depend on `toString()`.

## 14. A record containing a mutable reference is not automatically deeply immutable

For example:

```java
record Snapshot(int[] values) {
}
```

The `Snapshot` record is a final type and the fields for its components are final, but `int[]` is still mutable. Moreover, the default representation may invoke the array's string conversion and display something like `[I@...` instead of the elements.

### One way to customize the display

```java
import java.util.Arrays;

record Snapshot(int[] values) {
    @Override
    public String toString() {
        return "Snapshot{values="
                + Arrays.toString(values) + "}";
    }
}
```

The example above assumes `values` is non-null or already validated; `Arrays.toString((int[]) null)` still has a null representation according to the API.

**However, customizing `toString()` does not make the array immutable.** If an immutable snapshot is needed, you must control mutable input/output, for example through defensive copying in the constructor/accessor or by using an immutable representation.

## 15. Arrays usually do not print their contents automatically via `Object.toString()`

An array in Java is an object, but array types do not override `toString()` to render each element the way you usually want.

For example:

```java
int[] values = {1, 2, 3};
System.out.println(values);
```

Typically, this produces a string like:

```text
[I@... 
```

where `[I` is the descriptor for a one-dimensional `int` array and the suffix is not predetermined. The ellipsis here merely stands in for the hash suffix, **not characters that the program is guaranteed to print**.

To print the contents:

```java
System.out.println(java.util.Arrays.toString(values));
```

result:

```text
[1, 2, 3]
```

**You should not write a fixed expected stdout for direct array `toString()`**, because the hash code suffix can differ.

## 16. `Arrays.toString`, `Arrays.deepToString`, and multidimensional arrays

`java.util.Arrays` provides methods for displaying arrays:

- `Arrays.toString(int[])`, `Arrays.toString(long[])`, ... for one-dimensional primitive arrays.
- `Arrays.toString(Object[])` for one-dimensional reference arrays, representing each element (which can call the elements' `toString()`).
- `Arrays.deepToString(Object[])` for nested object arrays, useful for multidimensional arrays such as `int[][]`.
- A multidimensional primitive array such as `int[][]` is an **array of `int[]`**, so `Arrays.toString(matrix)` does not deeply print the int elements.

### Java 17 program

Save **`ArrayToStringDemo.java`**:

```java
import java.util.Arrays;

public class ArrayToStringDemo {
    public static void main(String[] args) {
        int[] numbers = {1, 2, 3};
        String[] names = {"An", "Bình"};
        int[][] matrix = {{1, 2}, {3, 4}};

        System.out.println(Arrays.toString(numbers));
        System.out.println(Arrays.toString(names));
        System.out.println(Arrays.deepToString(matrix));
        System.out.println(
                numbers.toString().startsWith("[I@"));
    }
}
```

```bash
javac -encoding UTF-8 ArrayToStringDemo.java
java ArrayToStringDemo
```

**Stdout:**

```text
[1, 2, 3]
[An, Bình]
[[1, 2], [3, 4]]
true
```

**Important:** `Arrays.deepToString` handles nested reference arrays. It has a mechanism for appropriate reference-cycle cases, but the output for a complex graph can still be large and should not be used as a standard serializer.

## 17. Collections usually have a readable representation

Classes such as `ArrayList` and many implementations of `Collection`/`Map` provide a useful `toString()`:

```java
List<String> names = List.of("An", "Bình");
System.out.println(names);
```

Example output:

```text
[An, Bình]
```

However, a collection's representation typically **relies on the representations of its elements**. If the element class does not override `toString()`, you may see:

```text
[Student@..., Student@...]
```

instead of the desired name/id information.

### Do not rely on unguaranteed order

A `HashSet` or `HashMap` does not make the same iteration-order guarantee as a `List` or `LinkedHashMap` under their respective contracts. Because a collection's `toString()` typically traverses its elements/entries, the output order can change.

**Avoid writing unit tests that expect `HashMap.toString()` to have a specific order** if the contract does not guarantee ordering. When stable output is needed, use a structure with an ordering contract or sort the data before representing it.

## 18. Collection + record example for stable stdout

Save **`CollectionToStringDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

record Item(String code, int quantity) {
}

public class CollectionToStringDemo {
    public static void main(String[] args) {
        List<Item> items = List.of(
                new Item("A", 2),
                new Item("B", 1));

        Map<String, Integer> quantities = new LinkedHashMap<>();
        quantities.put("A", 2);
        quantities.put("B", 1);

        System.out.println(items);
        System.out.println(quantities);
    }
}
```

```bash
javac -encoding UTF-8 CollectionToStringDemo.java
java CollectionToStringDemo
```

Stdout:

```text
[Item[code=A, quantity=2], Item[code=B, quantity=1]]
{A=2, B=1}
```

`List.of` preserves the element order according to the passed-in list; `LinkedHashMap` in the example maintains insertion order under its default configuration.

If `Item.toString()` is overridden to return a different format, the representation of `items` changes accordingly. Therefore, changing an element class's `toString()` can affect diagnostic output in a great many places.

## 19. String, StringBuilder, and other library types

`String` represents itself using its own string content:

```java
String text = "Java";
System.out.println(text.toString()); // Java
```

`StringBuilder` can modify its content, and `toString()` returns a string representing the character state at the time of the call:

```java
StringBuilder builder = new StringBuilder("Java");
builder.append(" 17");
System.out.println(builder.toString()); // Java 17
```

This is a reminder that `toString()` **does not have one mandatory format for every class**. Depending on the object type, an appropriate representation may be:
- Only the text value (String).
- The accumulated characters (StringBuilder).
- Record components (record).
- A collection of elements (List/Map).
- Business ID/state (domain object).
- API-specific diagnostic text (exceptions or certain framework objects).

Do not rely on the default `Object.toString()` to guess the format of **every JDK class**; each class may have overridden it.

## 20. Enum: how `name()` differs from `toString()`

An enum constant has its **declared name** provided by `name()`, while `toString()` can be overridden to display friendly text.

```java
enum Status {
    NEW,
    DONE
}
```

By default, `Status.NEW.toString()` typically returns `"NEW"` according to `Enum.toString()` behavior. However, the enum author can override `toString()` with a different representation.

### Runnable example

Save **`EnumToStringDemo.java`**:

```java
enum Status {
    NEW("Chưa xử lý"),
    DONE("Hoàn thành");

    private final String label;

    Status(String label) {
        this.label = label;
    }

    @Override
    public String toString() {
        return label;
    }
}

public class EnumToStringDemo {
    public static void main(String[] args) {
        Status status = Status.DONE;

        System.out.println(status.name());
        System.out.println(status.toString());
        System.out.println(status);
    }
}
```

```bash
javac -encoding UTF-8 EnumToStringDemo.java
java EnumToStringDemo
```

Stdout:

```text
DONE
Hoàn thành
Hoàn thành
```

**When to use `name()`?** If you need the official declared name of the enum constant and accept the constraint when renaming in source code, `name()` expresses that intent more clearly. However, **you should not use `name()` as a permanent storage format without designing versioning** if enum names might change in the future.

**When to use `toString()`?** When you need a readable representation. However, if the text depends on the user's language, a separate method such as `displayName(Locale)` is usually more appropriate than a parameterless `toString()`.

## 21. Distinguishing `toString()` from serialization

A common architectural mistake is to use:

```java
String json = object.toString();
```

and assume the `json` variable already contains valid JSON.

**Not true.** `toString()` is not a standard serialization protocol. An author-defined string might:
- Not escape quotes, newlines, or control characters.
- Be missing fields or include extra fields.
- Contain information that changes based on timing/logging policy.
- Not be reliably parseable back.
- Have no schema version.

A representation:

```text
Customer{id=7, name='An'}
```

is not JSON because it lacks standard double quotes for keys/strings and proper JSON syntax.

If you need JSON/XML/CSV or a protocol message:
- Use an appropriate serializer library with a clear contract.
- Define a DTO/schema, escaping, and versioning.
- Choose the timezone/locale/date format explicitly.
- Do not use `toString()` as contract data that other systems must parse.

### Display text also differs from debug text

An invoice for a customer requires exact language, currency, layout, and figures. A `toString()` meant for debugging might only print `Invoice{id=..., total=...}`. The two needs should use **separate APIs** if the format carries business meaning.

## 22. `toString()`, `equals()`, and `hashCode()` are three different contracts

`Object` provides all three:

```java
public boolean equals(Object obj)
public int hashCode()
public String toString()
```

Do not confuse them:

- `equals` defines the **logical equality** relationship according to its contract.
- `hashCode` produces a hash value for structures like HashMap/HashSet, and must be consistent with `equals`.
- `toString` produces a **textual description** for humans to observe.

Two objects with the same `toString()` are **not required** to be considered equal by `equals`. Two objects for which `equals` is true are also **not required by Java** to always have the same `toString()`, even though designing for consistency can be useful.

### Do not use `toString()` as an identifier in equality

Conceptually wrong:

```java
@Override
public boolean equals(Object other) {
    return other != null
            && this.toString().equals(other.toString());
}
```

This approach depends on the display format, can get the type wrong, miss state, expose dependencies on unrelated fields, and easily cause recursion. Implement equality according to **business identity/value semantics**.

**Similarly:** you should not implement `hashCode` as `toString().hashCode()` just to avoid thinking about fields; the two contracts have different responsibilities.

## 23. Example: same representation, different identity

Save **`ToStringIdentityDemo.java`**:

```java
final class Label {
    private final String value;

    Label(String value) {
        this.value = value;
    }

    @Override
    public String toString() {
        return "Label[" + value + "]";
    }
}

public class ToStringIdentityDemo {
    public static void main(String[] args) {
        Label first = new Label("A");
        Label second = new Label("A");

        System.out.println(first.toString());
        System.out.println(second.toString());
        System.out.println(first == second);
        System.out.println(first.equals(second));
    }
}
```

```bash
javac -encoding UTF-8 ToStringIdentityDemo.java
java ToStringIdentityDemo
```

Stdout:

```text
Label[A]
Label[A]
false
false
```

`Label` **does not override `equals()`**, so it uses `Object`'s identity-based equality. The two instances are different, yet their `toString()` values are the same because they have the same `value`.

**Do not take a text presentation as proof that two references refer to the same object.**

## 24. Inheritance: using `super.toString()` when it makes sense

If the superclass has overridden `toString()` to display common properties, a subclass can reuse that representation:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "Person{name='" + name + "'}";
    }
}

class Employee extends Person {
    private final int level;

    Employee(String name, int level) {
        super(name);
        this.level = level;
    }

    @Override
    public String toString() {
        return "Employee{base=" + super.toString()
                + ", level=" + level + "}";
    }
}
```

`super.toString()` **deliberately invokes the superclass implementation**, rather than using a cast to try to disable virtual dispatch.

### Runnable

Save **`SuperToStringDemo.java`**:

```java
class Person {
    private final String name;

    Person(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "Person{name='" + name + "'}";
    }
}

class Employee extends Person {
    private final int level;

    Employee(String name, int level) {
        super(name);
        this.level = level;
    }

    @Override
    public String toString() {
        return "Employee{base=" + super.toString()
                + ", level=" + level + "}";
    }
}

public class SuperToStringDemo {
    public static void main(String[] args) {
        Person person = new Person("An");
        Person employee = new Employee("Bình", 3);

        System.out.println(person);
        System.out.println(employee);
    }
}
```

```bash
javac -encoding UTF-8 SuperToStringDemo.java
java SuperToStringDemo
```

Stdout:

```text
Person{name='An'}
Employee{base=Person{name='Bình'}, level=3}
```

If `Person` has not overridden it, `super.toString()` may return the default `Class@hex` based on the runtime receiver (the runtime class name), rather than the fixed `Person` type name. That is not necessarily what the subclass wants.

### Design risk

If the superclass changes its `toString()` format, the format of subclasses that depend on `super.toString()` changes as well. When a stable format is needed, consider building the representation from getters or a helper API with a clear contract instead of parsing or directly embedding unstable text.

## 25. Do not call `toString()` from a constructor when the subclass is incomplete

`toString()` is an **overridable instance method** if it is not `final`. Calling it inside a superclass constructor can dispatch to a subclass override **before subclass fields are explicitly initialized**.

Design flaw example:

```java
class Base {
    Base() {
        System.out.println(this);
    }
}

class Child extends Base {
    private String state = "READY";

    @Override
    public String toString() {
        return "Child{state=" + state + "}";
    }
}
```

`new Child()` can print `Child{state=null}` because the `Base` constructor runs before Child's instance field initializer `state = "READY"`.

### Deterministic Java 17 example

Save **`ConstructorToStringPitfallDemo.java`**:

```java
class Base {
    Base() {
        System.out.println("Base sees: " + this);
    }
}

class Child extends Base {
    private String state = "READY";

    @Override
    public String toString() {
        return "Child{state=" + state + "}";
    }
}

public class ConstructorToStringPitfallDemo {
    public static void main(String[] args) {
        Child child = new Child();
        System.out.println("After: " + child);
    }
}
```

```bash
javac -encoding UTF-8 ConstructorToStringPitfallDemo.java
java ConstructorToStringPitfallDemo
```

**Stdout:**

```text
Base sees: Child{state=null}
After: Child{state=READY}
```

**Recommendation:** do not leak `this` prematurely and do not call overridable methods from a constructor if they might depend on subclass state. `toString()` is a specific case of this, not an exception to initialization rules.

## 26. Infinite recursion if `toString()` prints `this` itself

This is a dangerous trap:

```java
class Bad {
    @Override
    public String toString() {
        return "Bad: " + this;
    }
}
```

Reason:
1. There is a call to `object.toString()`.
2. Inside `toString()`, the expression `"Bad: " + this` must convert `this` to a string.
3. To convert it to a string, `this.toString()` is called again.
4. The loop has no stopping point.

The result is typically a **`StackOverflowError`**, not a valid representation.

Similarly:

```java
@Override
public String toString() {
    System.out.println(this);
    return "Bad";
}
```

also triggers `toString()` on itself when printing `this`, leading to recursion.

### How to fix

Print **the fields or values actually needed**, rather than printing all of `this` from `toString()` itself:

```java
@Override
public String toString() {
    return "Good{id=" + id + "}";
}
```

You can use `getClass().getSimpleName()` to represent the type name, though doing this is not a fix for recursion cycles between objects that reference each other.

## 27. Reference cycles between two objects

A bidirectional association:

```text
Department ----> Employee
      ^              |
      |--------------|
```

If:
- `Department.toString()` prints the entire list of Employees.
- `Employee.toString()` prints Department.
- Department contains an Employee pointing back to the same Department.

then the call chain can be:

```text
Department.toString()
 -> Employee.toString()
     -> Department.toString()
         -> Employee.toString()
             -> ...
```

This is an **object graph cycle**. Java's GC can collect unreachable reference cycles, but **it does not make a recursive `toString()` stop on its own**.

### How to design safely

1. In `Department.toString()`, print only `departmentId` and `employeeCount`.
2. In `Employee.toString()`, print `employeeId` and `departmentId`, without printing the full Department object.
3. If rendering the graph is genuinely needed, use a dedicated utility with an **identity-based visited set**, limiting depth and element count.
4. Do not put complex graph-traversal logic into the default `toString()` of every entity.
5. With entities/JPA, avoid accidentally triggering lazy associations just to render logs.

## 28. Safe program with a bidirectional association

Save **`CyclicReferenceSafeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

final class Department {
    private final String code;
    private final List<Employee> employees = new ArrayList<>();

    Department(String code) {
        this.code = code;
    }

    void add(Employee employee) {
        employees.add(employee);
    }

    String code() {
        return code;
    }

    @Override
    public String toString() {
        return "Department{code='" + code
                + "', employeeCount=" + employees.size() + "}";
    }
}

final class Employee {
    private final String name;
    private final Department department;

    Employee(String name, Department department) {
        this.name = name;
        this.department = department;
    }

    @Override
    public String toString() {
        return "Employee{name='" + name
                + "', departmentCode='" + department.code() + "'}";
    }
}

public class CyclicReferenceSafeDemo {
    public static void main(String[] args) {
        Department dev = new Department("DEV");
        Employee an = new Employee("An", dev);
        dev.add(an);

        System.out.println(dev);
        System.out.println(an);
    }
}
```

```bash
javac -encoding UTF-8 CyclicReferenceSafeDemo.java
java CyclicReferenceSafeDemo
```

Stdout:

```text
Department{code='DEV', employeeCount=1}
Employee{name='An', departmentCode='DEV'}
```

Each method prints only **short metadata** about the relation without trying to expand the entire object graph. This design avoids recursion in `toString()` even though the references form a cycle.

## 29. Security: do not expose passwords, tokens, and personal data

`toString()` is often called indirectly in logging, exception messages, debug printouts, and error monitoring. If it prints fields such as:

- Passwords, password hashes, recovery codes.
- Access tokens, refresh tokens, API keys.
- Secret connection strings, private keys.
- Unnecessary personal information.
- Payment data or confidential content.

then a single `logger.info("{}", user)` (depending on the framework) or `System.out.println(user)` call can leak data into logs.

**Rule:** by default, do not put secrets in `toString()`. Use a redacted representation.

For example:

```java
@Override
public String toString() {
    return "Credentials{username='" + username
            + "', password=<redacted>}";
}
```

Here, password is not read and converted into a string; only the literal `<redacted>` is printed.

### What if personal data is the ID itself?

You also need to consider log access permissions, observation purpose, and data policies. Not every ID or email is safe to print everywhere. You might print only a stable pseudonymous ID, a masked portion of the information, or a correlation ID.

**You should not rely on `toString()` as the sole place to handle log security**; controlling log levels, retention, access permissions, and redaction in the logging pipeline is still necessary.

## 30. Runnable: `toString()` that masks sensitive information

Save **`SafeToStringDemo.java`**:

```java
final class Credentials {
    private final String username;
    private final String password;

    Credentials(String username, String password) {
        this.username = username;
        this.password = password;
    }

    @Override
    public String toString() {
        return "Credentials{username='" + username
                + "', password=<redacted>}";
    }
}

public class SafeToStringDemo {
    public static void main(String[] args) {
        Credentials credentials =
                new Credentials("an", "secret-123");

        System.out.println(credentials);
    }
}
```

```bash
javac -encoding UTF-8 SafeToStringDemo.java
java SafeToStringDemo
```

Stdout:

```text
Credentials{username='an', password=<redacted>}
```

Note: the `password` variable in the example program still exists in the object; **redaction in `toString()` does not erase data from memory**. It only prevents the representation from revealing that value along that particular printing path.

## 31. `toString()` should avoid side effects

A `toString()` used to observe state should **not modify business state itself**.

Dangerous design:

```java
@Override
public String toString() {
    counter++; // Unwanted side effect.
    return "Counter=" + counter;
}
```

When a debugger or logger requests the representation, the object gets mutated. The result can differ solely because of **how many times it was observed**.

Operations that should generally be avoided inside `toString()`:
- Writing to a database or sending an HTTP request.
- Creating a transaction or changing business state.
- Expensive file/network reads.
- Accessing a lazy-loaded association that triggers an unintended query.
- Removing from or modifying a collection.
- Throwing an unchecked exception because a field is temporarily null without a proper policy.
- Using the current time or random values unless there is a clear display reason.

**The goal is usually a lightweight, fast, and unsurprising observation operation.** Java does not forbid toString from having side effects, though from a design standpoint that is usually a poor choice.

## 32. Performance cost when rendering objects

A `toString()` called on a hot path can become expensive if it:
- Iterates over thousands of elements in a collection.
- Builds a very large string.
- Traverses a deep relation graph.
- Formats dates/currency every time.
- Queries external data via a getter.
- Causes significant allocations.

For large collections, the representation should limit the number of elements and show the count:

```java
@Override
public String toString() {
    return "Batch{count=" + items.size() + "}";
}
```

If a full dump is needed, give the operation a clear name such as `toDebugDump()` and control callers/log levels.

### Logging can defer formatting

Many logging libraries provide **parameterized logging** or supplier/lazy message mechanisms to avoid constructing strings when a log level is disabled. However, details depend on the API/framework; do not claim that all logging frameworks always avoid calling `toString()` in every case.

For comparison:
- `logger.debug("Object: " + object)` builds the message string in the Java expression before the logger decides whether to use it, unless the compiler/framework has a special mechanism that does not alter argument-evaluation semantics.
- APIs that support lazy suppliers or placeholders can defer formatting work according to their own contracts.

In this Java Core lesson, `System.out.println` actually observes the object right when the line executes, with no log-level filtering mechanism.

## 33. Thread-safety: a representation can observe changing state

If an object has mutable fields and multiple threads modify it concurrently, `toString()` can read **an inconsistent combination of values** if there is no synchronization/visibility contract.

Conceptual example:

```java
class Pair {
    int left;
    int right;

    @Override
    public String toString() {
        return "Pair{" + left + ", " + right + "}";
    }
}
```

If one thread updates `left` and `right` without synchronization while another thread calls `toString()`, the representation may capture an intermediate state. Simply adding `final` to the **method** or to the **reference to Pair** does not make the object thread-safe.

Options depending on the contract:
- Design an immutable value object.
- Synchronize reads/writes using the same lock.
- Read from a safely published immutable snapshot.
- Use an appropriate concurrent structure.
- Do not promise that logs are an atomic snapshot if there is no guarantee.

Do not call multiple getters with different side effects and combine them into a representation treated as an atomic snapshot when no mechanism actually guarantees it.

## 34. Null fields inside an object

The receiver of `toString()` itself must be non-null to invoke the instance method directly. However, **fields inside the object can be null**.

```java
class User {
    private String nickname;

    @Override
    public String toString() {
        return "User{nickname=" + nickname + "}";
    }
}
```

String concatenation with `nickname == null` can produce the text `null` in a syntactically safe way. However:

```java
return nickname.toUpperCase();
```

will throw a `NullPointerException` if nickname is null.

Considerations:
- If null is a valid state, print `(unknown)` or `null` clearly.
- If null is invalid, validate it in the constructor/operation instead of letting `toString()` be where it is caught late.
- If the data contains secrets, avoid printing it even when it is non-null.
- Do not create misleading strings like “nickname='null'” when a reader might interpret it as an actual name.

### Using `Objects.toString` for fallback text

```java
return "User{nickname="
        + java.util.Objects.toString(nickname, "(unset)")
        + "}";
```

This approach clearly represents a nullable field.

## 35. Runnable: nullable field

Save **`NullableFieldToStringDemo.java`**:

```java
import java.util.Objects;

final class User {
    private final int id;
    private final String nickname;

    User(int id, String nickname) {
        this.id = id;
        this.nickname = nickname;
    }

    @Override
    public String toString() {
        return "User{id=" + id + ", nickname="
                + Objects.toString(nickname, "(unset)")
                + "}";
    }
}

public class NullableFieldToStringDemo {
    public static void main(String[] args) {
        System.out.println(new User(1, "An"));
        System.out.println(new User(2, null));
    }
}
```

```bash
javac -encoding UTF-8 NullableFieldToStringDemo.java
java NullableFieldToStringDemo
```

Stdout:

```text
User{id=1, nickname=An}
User{id=2, nickname=(unset)}
```

## 36. Formatting time and numbers: separating Locale/timezone concerns

If the representation contains numbers, dates, currency, or decimals:
- `Double.toString(value)` uses a different format from locale-based display.
- `LocalDate` has a clear ISO-like representation.
- `Instant` represents a point on the UTC timeline.
- `ZonedDateTime` and `OffsetDateTime` carry timezone/offset data according to their own semantics.

If the API needs stable output for tests/diagnostics, **choose an explicit format**, such as `Locale.ROOT` with `String.format` when controlling decimal numbers.

**Do not call an object's `toString()` and treat it as a permanent protocol across every Java/JDK/library version.** Library-specific formats can change if the API does not promise stability.

### Decimal example with Locale.ROOT

Save **`LocaleToStringDemo.java`**:

```java
import java.util.Locale;

record Measurement(double value, String unit) {
    @Override
    public String toString() {
        return String.format(Locale.ROOT,
                "Measurement{value=%.2f, unit=%s}",
                value, unit);
    }
}

public class LocaleToStringDemo {
    public static void main(String[] args) {
        Measurement measurement =
                new Measurement(12.5, "kg");

        System.out.println(measurement);
    }
}
```

```bash
javac -encoding UTF-8 LocaleToStringDemo.java
java LocaleToStringDemo
```

Stdout:

```text
Measurement{value=12.50, unit=kg}
```

Including `Locale.ROOT` ensures the decimal number uses a dot in the example representation, without depending on the environment's default locale.

## 37. Does `String.format("%s", object)` always call `toString()`?

For an ordinary object that does not implement a custom formatting mechanism, the `%s` conversion typically represents the object using `toString()`; if the object is null, it displays `null`.

However, the `java.util.Formatter` API has a special path: if the argument implements **`java.util.Formattable`**, the `%s` conversion may call **`formatTo(...)`** instead of simply calling `toString()`.

Therefore:

```java
String text = String.format("Value=%s", object);
```

should not be treated as an absolute equivalent to `"Value=" + object` for **every kind of object**.

In addition, `String.format` has rules for `Locale`, format flags, width, and precision, and can throw formatting exceptions if the format string is invalid. Use `toString()` for ordinary debug representations; use a formatter when intentional formatting is required.

### Example with a record

```java
record Point(int x, int y) {
}

System.out.printf("Point: %s%n", new Point(1, 2));
```

With JDK 17 and this record, the result:

```text
Point: Point[x=1, y=2]
```

The `%n` specifier is a platform-dependent newline; when recording stdout line by line in documentation, the content of each line remains as shown above.

## 38. Do not use `toString()` to test full state

A unit test such as:

```java
assertEquals("Order{id=7, status=NEW}", order.toString());
```

may be appropriate **if the `toString()` format itself is the behavior you need to verify**.

However, if the test is meant to verify business logic, comparing the representation can cause **false failures** when only the debug format changes:
- Changing whitespace.
- Adding a diagnostic field.
- Reordering fields.
- Renaming the class/record.
- Changing the locale or escaping.

Good tests for domain behavior should call **business accessors/methods** or compare value objects according to the appropriate contract. Test `toString` separately to ensure the representation is readable and does not leak secrets.

### Flexible checks when values are unstable

If the default implementation contains a hash suffix:

```java
String text = new Object().toString();
System.out.println(text.startsWith("java.lang.Object@"));
```

This line produces `true` on a standard `Object.toString` implementation; do not check the entire `hex`.

For a custom object, if the representation is not guaranteed to be completely stable, you can assert meaningful parts such as `contains("id=7")` and the absence of secrets, while still avoiding too many tests tightly coupled to internal formatting.

## 39. Debugger tools may display an object differently from `toString()`

In an IDE/debugger, an object is often presented in several ways:
- A tree of fields and properties.
- Class name + identity.
- A custom object renderer.
- The result of `toString()` if the configuration and environment permit.

**Do not assume an IDE always calls `toString()`** or never calls it. Some debuggers may execute the method to generate display text, carrying risks of side effects and cost. Each IDE's configuration may differ.

That is why `toString()` should not:
- Cause changes to business state.
- Perform unnecessary blocking I/O.
- Access remote resources.
- Create many objects or traverse a huge graph.
- Throw an error due to an uninitialized field.

If an object is heavy, you can design a short summary, while a detailed dump can be a separate API whose invocation can be controlled.

## 40. Distinguishing `toString()` from a stable identifier

An object may need multiple ways of being presented:

```java
record UserId(long value) {
}
```

- **ID:** `value()` → the number used to locate the user in the domain.
- **Debug representation:** `toString()` → for example, `UserId[value=12]`.
- **Display label:** `displayName()` or profile data → for example, a UI-friendly name.
- **Serialization:** JSON/protobuf/DTO fields → a separate contract with other systems.

Do not use `user.toString()` as a foreign key, long-lived cache key, or URL path segment unless you **intentionally define** a stable, escaped, and versioned format—and even then, a dedicated method is usually easier to maintain.

A mutable object can also change its representation along with its state:

```java
class Counter {
    int count;

    @Override
    public String toString() {
        return "Counter=" + count;
    }
}
```

Because the text changes when `count` changes, it is unsuitable as an immutable identifier key.

## 41. Quick comparison of ways to observe objects

| Usage | Purpose | Key points to remember |
| --- | --- | --- |
| `obj.toString()` | Get the object's representation | Null receiver → error |
| `System.out.println(obj)` | Print the object to the console | Selects overload by static type; for domain objects, typically uses object conversion |
| `"obj=" + obj` | Concatenate representation into a string | May invoke conversion right when evaluating the expression |
| `String.valueOf(obj)` | Convert an object/null to text | `null` → `"null"` with the Object overload |
| `Objects.toString(obj, fallback)` | Null-safe text with fallback | Selects fallback when obj is null |
| `Arrays.toString(array)` | Print elements of a one-dimensional array | Differs from the default array toString |
| `Arrays.deepToString(objectArray)` | Print nested object arrays | Useful for `int[][]` and nested arrays |
| `record.toString()` | Print record components | Auto-generated unless custom-overridden |
| `enum.name()` | Enum constant name | Differs from display `toString()` if the enum overrides it |
| `String.format("%s", obj)` | Formatter-based text | `Formattable` can intervene in the conversion |
| `serializer.write(obj)` | Data protocol formatting | Not equivalent to `toString()` |
| IDE object inspector | Observe fields/runtime state | May or may not use `toString()` |

## 42. Common mistakes table

| Symptom | Cause | Fix |
| --- | --- | --- |
| Printing an object outputs `Class@hex` | The class uses inherited `Object.toString()` | Override with an appropriate representation |
| Test depends on hex suffix | Hash suffix is unstable | Check a pattern or stable custom text |
| Assuming `@hex` is a memory address | Default format uses `hashCode()` | Do not use as an address/ID |
| Writing non-public `String toString()` | Reduces access from Object's public method | Use `public String toString()` |
| Writing `toString(String prefix)` | Overload, not an override | Use `@Override` and the correct signature |
| Returning `"X" + this` directly inside `toString()` | Calls the method itself recursively | Print specific fields |
| Bidirectional nested objects print infinitely | Object graph cycle | Print only IDs/count or use a dedicated graph renderer |
| Array prints `[I@...` | Arrays use the inherited Object representation | `Arrays.toString` |
| 2D array does not print individual numbers | `Arrays.toString` does not deep-render | `Arrays.deepToString` |
| Direct `char[]` print differs from `Object` view | `println(char[])` overload | Check the static type / called overload |
| List elements print `Class@hex` | Element class does not override `toString()` | Override on the element or map to a label |
| HashMap text order varies | Collection does not guarantee iteration order | Use an ordered structure / sort first |
| Logs accidentally expose password/token | `toString()` prints sensitive field | Redact/omit and configure logging securely |
| Logging an object triggers database loads | `toString()` touches lazy association/getter | Print only local summary and ID |
| Debugger mutates the object | Side effect inside `toString()` | Pure-ish representation |
| `null.toString()` throws an error | No receiver object | `String.valueOf`/`Objects.toString` or validate |
| `Record[array=...@hex]` | Component is a mutable array | Custom `Arrays.toString`, consider copying |
| Using `toString` as JSON | Does not guarantee escaping/schema | Dedicated serializer/DTO |
| Using `toString` as `equals` | Text is not an equality contract | Compare fields/IDs logically |
| Printing object in superclass constructor sees null field | Virtual dispatch runs before subclass initializer | Avoid calling overridable methods during construction |
| ToString returns overly long output | Unbounded collection/graph traversal | Summary, bounded elements/depth |
| Output varies by Locale | Formatting relies on default Locale | Choose explicit Locale/formatter |
| Assuming `%s` always behaves like `+` | Formatter has a `Formattable` path | Know the formatting API in use |

## 43. Exercise 1 — Result of `Object.toString()`

```java
class A {
}

A value = new A();
System.out.println(value);
```

**Question:** can you know the exact stdout line?

**Answer:** You cannot portably deduce the entire hexadecimal suffix. Under the default representation, it usually has the form `A@...`. That is no reason to make up a specific hash string.

## 44. Exercise 2 — Overriding with the right signature

```java
class A {
    public String toString(int detail) {
        return "A:" + detail;
    }
}
```

**Question:** does `System.out.println(new A())` use `toString(int)`?

**Answer:** No. This is only an overload with a different parameter. `println` does not automatically call `toString(1)`; it uses the object's representation via the no-argument `toString()`. To customize it, you must declare `@Override public String toString()`.

## 45. Exercise 3 — Dynamic dispatch

```java
class Parent {
    @Override
    public String toString() {
        return "P";
    }
}

class Child extends Parent {
    @Override
    public String toString() {
        return "C";
    }
}

Parent value = new Child();
System.out.println(value);
```

**Answer:** `C`. The runtime object is a Child, and the method is overridden, so dispatch goes to the Child implementation.

## 46. Exercise 4 — Null-safe string conversion

```java
Object value = null;
System.out.println(String.valueOf(value));
System.out.println(java.util.Objects.toString(value, "none"));
```

**Stdout:**

```text
null
none
```

`String.valueOf(Object)` returns the literal `"null"` for null; the `Objects.toString` overload with a fallback returns `"none"`.

## 47. Exercise 5 — Primitive array

```java
int[] data = {4, 5};
System.out.println(java.util.Arrays.toString(data));
```

**Answer:**

```text
[4, 5]
```

Direct `System.out.println(data)` does not guarantee this string, because the overload receiving this array is Object, and arrays do not render their elements automatically like `Arrays.toString`.

## 48. Exercise 6 — Character array

```java
char[] text = {'O', 'K'};
System.out.println(text);
```

**Answer:**

```text
OK
```

Java selects `println(char[])`. If you want to observe the value as an object, distinguish `Object asObject = text` and call accordingly; do not infer that all arrays print the same way.

## 49. Exercise 7 — Record

```java
record Point(int x, int y) {
}

System.out.println(new Point(1, 2));
```

**Answer:**

```text
Point[x=1, y=2]
```

A record generates a `toString()` representation of its components when there is no custom override.

## 50. Exercise 8 — Enum

```java
enum Level {
    HIGH;

    @Override
    public String toString() {
        return "high-priority";
    }
}

System.out.println(Level.HIGH.name());
System.out.println(Level.HIGH.toString());
```

**Stdout:**

```text
HIGH
high-priority
```

`name()` still returns the enum constant's name, while `toString()` can be customized for display.

## 51. Exercise 9 — Printing inside a superclass constructor

```java
class Parent {
    Parent() {
        System.out.println(this);
    }
}

class Child extends Parent {
    String value = "ready";

    @Override
    public String toString() {
        return String.valueOf(value);
    }
}

new Child();
```

**Answer:** `null`. The `Parent` constructor calls the overridden `toString()` in Child before the field initializer `value = "ready"` runs.

## 52. Exercise 10 — The string `"X" + this`

```java
class Bad {
    @Override
    public String toString() {
        return "Bad" + this;
    }
}
```

**Answer:** The method calls itself recursively via string conversion, typically causing a `StackOverflowError`. Fix it by representing specific fields, for example `"Bad{id=" + id + "}"`.

## 53. Exercise 11 — Collection with stable ordering

```java
java.util.List<String> names =
        java.util.List.of("An", "Bình");
System.out.println(names);
```

**Answer:**

```text
[An, Bình]
```

The `List` iteration order in the example is deterministic, and the `String` elements display their own text.

## 54. Exercise 12 — Do two identical strings mean the objects are equal?

```java
class User {
    @Override
    public String toString() {
        return "User";
    }
}

User a = new User();
User b = new User();

System.out.println(a.toString().equals(b.toString()));
System.out.println(a.equals(b));
```

**Stdout:**

```text
true
false
```

The two representations are equal, but `equals` still follows `Object` identity because the class does not override `equals`.

## 55. Exercise 13 — What should be printed from an Order with thousands of OrderLines?

**Prompt:** An Order has 50,000 lines and many bidirectional links. Should you write `return "Order{" + lines + "}"`?

**Answer:** Usually not. It can generate very large text, be expensive, cause recursion if lines point back to Order, and expose unnecessary data. Instead, print a summary such as `Order{id=..., lineCount=50000, status=...}`; create a separate dump with depth/element limits if truly needed.

## 56. Exercise 14 — Information security

**Prompt:** `Credentials` has fields username, password, and accessToken. Which `toString()` design is appropriate?

**Answer:** Print minimal non-sensitive information such as username if policy permits; represent password/token with `<redacted>` or omit them altogether. Do not use `getPassword()`/`getToken()` to put secrets into the string. Protecting the log pipeline is still necessary outside of `toString()`.

## 57. Exercise 15 — Superclass representation

```java
class Base {
    @Override
    public String toString() {
        return "Base";
    }
}

class Child extends Base {
    @Override
    public String toString() {
        return "Child(" + super.toString() + ")";
    }
}

System.out.println(new Child());
```

**Answer:**

```text
Child(Base)
```

`super.toString()` calls the superclass implementation in a special way; if replaced with `((Base) this).toString()`, dynamic dispatch still goes to Child and risks recursion.

## 58. Exercise 16 — Use for JSON?

**Prompt:** `record Customer(String name, int age)` prints `Customer[name=An, age=20]`. Can you send `toString()` directly as a JSON API response?

**Answer:** No. This is a debug representation, not a JSON schema. Use a valid JSON serializer/DTO, escaping, and a versioning contract.

## 59. Exercise 17 — `toString()` and a mutable field

```java
class Counter {
    int value;

    @Override
    public String toString() {
        return "Counter=" + value;
    }
}

Counter counter = new Counter();
System.out.println(counter);
counter.value = 3;
System.out.println(counter);
```

**Stdout:**

```text
Counter=0
Counter=3
```

`toString()` returns text reflecting the **object's state at the time of the call**. It does not capture a permanently immutable snapshot right when the object is created.

## 60. Exercise 18 — Null field and fallback

```java
String nickname = null;
System.out.println(
        java.util.Objects.toString(nickname, "unknown"));
```

**Answer:** `unknown`. When the reference is null, the overload with a fallback returns the replacement string instead of throwing a `NullPointerException`.

## 61. Checklist for implementing `toString()`

1. Is it declared properly as **`@Override public String toString()`**?
2. Does the result help identify the **object type and useful state**?
3. Is it using the default `Object.toString()` with a hash suffix that readers do not need?
4. Are you accidentally treating the hash suffix as a **memory address / unique ID**?
5. Are there any **password, token, secret, or PII** fields that need to be omitted or redacted?
6. Is the representation short and readable even when the object contains large collections?
7. Does it print the entire object graph or lazy-loaded relations that cause side effects or recursion?
8. Does it accidentally concatenate **`this` inside `toString()` itself**?
9. If the class has bidirectional associations, have recursive references been limited?
10. Does the method perform I/O, database queries, mutable state modifications, or blocking operations?
11. If the object is used across multiple threads, can the representation observe an intermediate state?
12. Are there nullable fields that need `Objects.toString`/a fallback?
13. Is there an array that needs `Arrays.toString` or `Arrays.deepToString`?
14. Is a record's auto-generated representation sufficient, or is an override genuinely needed?
15. For enums, is `name()` distinguished from `toString()`?
16. Does it depend on the unguaranteed iteration order of `HashMap`/`HashSet`?
17. When concatenating strings or calling `println`, have special overloads such as `char[]` been distinguished?
18. When using `String.format`, have Locale/`Formattable` been considered where needed?
19. With inheritance, does `super.toString()` provide a stable and useful representation?
20. Is `toString()` called from a superclass constructor before the subclass finishes initializing?
21. Is `toString()` being used unintentionally as JSON, a storage key, an equality check, or a UI display contract?
22. If end-user output is needed, should there be a **separate formatter/display method**?
23. Do tests verify the **actual required behavior** rather than depending on an unstable diagnostic string?
24. Is there a runnable Java 17 program with matching public class/file name and stable stdout?

## Things to remember

- **`toString()` of `java.lang.Object`** is the foundation for having a textual representation of an object; a class can **override** it to print meaningful fields.
- **The default `Object.toString()`** has the form class name + `@` + hex of `hashCode()`; the suffix is neither a memory address nor a reliable unique identifier.
- **`System.out.println(object)`, string concatenation, and `String.valueOf(Object)`** commonly use the `toString()` representation; be mindful of special overloads such as `char[]`.
- **Arrays use `Arrays.toString` / `Arrays.deepToString`** if you want to display their elements; records have a `toString()` generated from their components; enums can override their display representation.
- **`toString()` is an instance method with polymorphic dispatch**, so a variable declared with type `Object` can still invoke the runtime subclass's override.
- **`toString()` is not serialization, equality, or a stable identifier**. Those contracts require separate APIs.
- Avoid **self-calling recursion with `this`**, reference cycles between objects, heavy I/O, mutation inside the method, and printing sensitive data.
- When debugging/logging, prefer a representation that is **concise, includes appropriate ID/state, is safe, and has predictable cost**.
