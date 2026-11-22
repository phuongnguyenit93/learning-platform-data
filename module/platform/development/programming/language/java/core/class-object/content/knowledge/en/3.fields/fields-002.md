# Primitive Fields and Reference Fields in Java

A **field** is a variable declared in the body of a class or interface, used to represent the state of an object or state associated with the class. In Java, a field can have a **primitive type** or a **reference type**. The key difference that determines how they behave is: a primitive field holds a **primitive value**, whereas a reference field holds a **reference value to an object** or `null`.

Understanding these two groups of fields correctly helps predict the outcome of assignments, explain why two objects can observe a shared change, handle unset values, and protect internal state when designing classes. The content below uses Java 17+.

## 1. Identifying the Two Groups of Fields

Consider a profile management class:

~~~java
class StudentProfile {
    int age;                 // primitive field: int value
    double averageScore;     // primitive field: double value
    boolean active;          // primitive field: boolean value

    String fullName;         // reference field: String reference or null
    int[] examScores;        // reference field: array reference or null
    Address address;         // reference field: Address reference or null
}

class Address {
    String city;
}
~~~

This is an **illustrative class declaration snippet** and does not yet have a `main` method to run directly.

| Criterion | Primitive field | Reference field |
| --- | --- | --- |
| Examples | `int age`, `boolean active` | `String name`, `Address address`, `int[] scores` |
| Stored value | Value of the primitive type | Reference value or `null` |
| Default value for a field | `0`, `false`, `'\u0000'`… depending on type | `null` |
| Can `null` be assigned directly? | No | Yes, unless constrained by another mechanism |
| Assignment from a field of the same type | Copies the primitive value | Copies the reference value |
| Can two fields point to the same object? | No concept of a pointed-to object | Yes |
| Can an instance method be called via the field value? | Not directly on a primitive | Yes, when the reference is non-`null` and the type allows it |
| Comparison with `==` | Compares primitive values according to operator rules | Compares whether two references point to the same object |

Note: **a reference is also a value that is assigned and copied**. Saying "a reference field holds an address" is only a common analogy; the Java specification does not require a program to know or manipulate a raw memory address. How the JVM represents references is an implementation detail.

## 2. The Eight Primitive Types

Java has exactly **eight primitive types**:

| Type | Category | Size/range according to the language | Example |
| --- | --- | --- | --- |
| `byte` | Integer | Signed, 8-bit, from -128 to 127 | `byte level = 5;` |
| `short` | Integer | Signed, 16-bit, from -32768 to 32767 | `short year = 2026;` |
| `int` | Integer | Signed, 32-bit | `int quantity = 10;` |
| `long` | Integer | Signed, 64-bit | `long distance = 9_000_000_000L;` |
| `float` | Floating-point | 32-bit, IEEE 754 standard | `float ratio = 0.5f;` |
| `double` | Floating-point | 64-bit, IEEE 754 standard | `double price = 19.5;` |
| `char` | Character | Unsigned 16-bit UTF-16 code value (0 to 65535) | `char grade = 'A';` |
| `boolean` | Boolean | `true` or `false`; no fixed physical storage size specified | `boolean enabled = true;` |

`char` represents **a single UTF-16 code unit**, not necessarily a complete Unicode character as perceived by the user; some Unicode characters require two code units (*surrogate pair*). `boolean` does not automatically convert to `0`/`1` as in some other languages.

Primitive types are **not classes**, are not Java objects, and have no object identity. Therefore:

~~~java
class Metrics {
    int count = 3;
    boolean ready = true;
    double total = 7.5;

    // count.length() // invalid: int has no instance methods
}
~~~

The snippet above illustrates field types; the commented line would be an invalid expression if uncommented. The fields can still be used in calculations and comparison expressions appropriate for their respective types.

### 2.1. A Primitive Field Holds Its Own Value

~~~java
class Score {
    int value;
}
~~~

Suppose there are two objects `Score first` and `Score second`: each object carries its own **instance field `value`**. Assigning `first.value = 10` does not automatically change `second.value`. If you write `second.value = first.value`, Java copies the current number; modifying one afterward does not affect the other.

A single `Score` object can be pointed to by multiple different reference variables; in that case, `first` and an alias variable of `first` access **the same instance field**. Therefore, it is necessary to distinguish between **two different objects** and **two variables referencing the same object**.

## 3. Common Reference Types

Reference types include class types, interface types, array types, and related types supported by Java. In field declarations, you commonly encounter:

~~~java
class Order {
    String orderCode;              // String is a class
    Customer customer;             // user-defined class
    java.util.List<String> items;  // List is an interface
    int[] quantities;              // array is an object
    Object extra;                  // reference to a compatible object
}

class Customer {
    String name;
}
~~~

This is a declaration example, not a standalone program. Even though the `int[]` array contains **primitive-type elements**, the **`quantities` field itself** is still a **reference field**, because an array in Java is an object. Conversely, each element `quantities[i]` is an `int` value.

A reference field does not contain the entire object "inside the field" according to the language model. It holds a reference value; the referenced object can have multiple fields of its own and can be pointed to by multiple references simultaneously.

For example:

~~~java
class Department {
    String name;
}

class Employee {
    Department department;
}
~~~

Two independent `Employee` objects can still both hold a reference value to **the same** `Department` object. Changing `department.name` through one employee can be seen through the other employee if both point to the same object.

### 3.1. String Is a Reference Type Even Though It Looks Like a Value

`String` is a **class**; `String name` is a reference field. A `String` object is **immutable**: the content of a created String object cannot be modified.

~~~java
class Greeting {
    String message = "Xin chào";
}
~~~

After `greeting.message = "Tạm biệt"`, the field points to a different String value; the original String object's content is not modified. This differs from a mutable class such as `StringBuilder` or an `Address` that allows updating its fields.

`String` has optimization features such as the string pool, but **do not use `==` to conclude that two strings have the same content**; you should use `equals` when comparing content.

## 4. Default Values: A Consequence of the Two Type Groups

When a field does not have an explicit initializer, Java assigns a **default value based on the type**, not based on business intent: integer types default to `0`, floating-point types to `0.0`, `boolean` to `false`, `char` to code 0; every **reference field** defaults to `null`. This rule applies to both instance fields and static fields.

```java
class Profile {
    int visits;        // 0
    boolean enabled;   // false
    String nickname;   // null, not ""
    int[] points;      // null, no array object yet
}
```

This is an **illustrative declaration**, without `main`. The key distinction to remember in this lesson is that **a primitive receives a primitive value, whereas a reference may point to no object at all**. `nickname.length()` or `points.length` will fail if the reference is still `null`. Local variables, by contrast, must be proven by the compiler to have been assigned before being read (*definite assignment*). Even when type-valid, those defaults may fail to satisfy business invariants; the constructor needs to establish required data.

## 5. Assignment: Copying Primitive Values and Copying References

This is the most important part in practice. Both assignments **copy a value**. The difference is what that value represents.

~~~java
int a = 10;
int b = a;       // b receives a copy of the value 10
b = 99;          // does not change a

Address first = new Address();
Address second = first; // copies the reference, does not create a new Address object
~~~

This snippet illustrates the mechanism. If `first` and `second` both point to a mutable `Address`, modifying the object's state through `second` can be seen through `first`. However, **`second = new Address()` does not cause `first` to automatically point to the new object**.

### 5.1. Complete Example: Two Reference Fields Pointing to the Same Object

Create the file **`FieldKindsDemo.java`**:

~~~java
public class FieldKindsDemo {
    static final class Location {
        String city;

        Location(String city) {
            this.city = city;
        }
    }

    static final class Member {
        int points;              // primitive field
        boolean verified;        // primitive field
        String nickname;         // reference field
        Location location;       // reference field

        Member(int points, Location location) {
            this.points = points;
            this.location = location;
        }
    }

    public static void main(String[] args) {
        Location shared = new Location("Huế");

        Member first = new Member(10, shared);
        Member second = new Member(20, shared);

        int copiedPoints = first.points;
        copiedPoints = 99;

        System.out.println("copiedPoints = " + copiedPoints);
        System.out.println("first.points = " + first.points);

        Location copiedLocation = first.location;
        copiedLocation.city = "Đà Nẵng";

        System.out.println("first.city = " + first.location.city);
        System.out.println("second.city = " + second.location.city);

        copiedLocation = new Location("Hà Nội");

        System.out.println("first.city after reassignment = " + first.location.city);
        System.out.println("default verified = " + first.verified);
        System.out.println("nickname is null = " + (first.nickname == null));
        System.out.println("same location = " + (first.location == second.location));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac -encoding UTF-8 FieldKindsDemo.java
java FieldKindsDemo
~~~

**Exact stdout:**

~~~text
copiedPoints = 99
first.points = 10
first.city = Đà Nẵng
second.city = Đà Nẵng
first.city after reassignment = Đà Nẵng
default verified = false
nickname is null = true
same location = true
~~~

Step-by-step explanation:

1. `shared` references a `Location("Huế")`. The `Member` constructor copies this **reference value** into `first.location` and `second.location`; it does not create two `Location` objects.
2. `copiedPoints = first.points` copies the primitive value `10`. Assigning `copiedPoints = 99` only modifies the local variable; `first.points` remains `10`.
3. `copiedLocation = first.location` creates an alias for the same `Location`. `copiedLocation.city = "Đà Nẵng"` modifies the `city` field **on the shared object**, so both `first.location.city` and `second.location.city` change accordingly.
4. `copiedLocation = new Location("Hà Nội")` only changes the value of the `copiedLocation` variable. The two fields `first.location` and `second.location` still reference the old `Location` in Đà Nẵng.
5. `verified` has not been assigned, so it defaults to `false`; `nickname` has not been assigned, so it defaults to `null`. The two `location` fields currently reference the same object, so `first.location == second.location` is `true`.

A conceptual diagram immediately after the statement `copiedLocation.city = "Đà Nẵng"` and **before** assigning `copiedLocation = new Location(...)`:

~~~text
Member first                       Member second
+------------------+               +------------------+
| points = 10      |               | points = 20      |
| location --------+----+      +---+-------- location |
+------------------+    |      |   +------------------+
                        v      v
                    +-------------------+
                    | Location object   |
                    | city = "Đà Nẵng"  |
                    +-------------------+
                              ^
                              |
                       copiedLocation
~~~

This is a **model of reference relationships**, not a memory address map or a mandatory physical layout of the JVM.

## 6. Reference Assignment Is Not a Deep Copy of an Object

Suppose:

~~~java
class Basket {
    int[] quantities;
}
~~~

If there are two different `Basket` objects that both hold a reference to **the same `int[]` array**, a change to `first.quantities[0]` can be observed through `second.quantities[0]`. The assignment `second.quantities = first.quantities` does not create a copy of the array.

To obtain another array with the primitive elements copied, you can use the array's `clone()` or `Arrays.copyOf(...)`:

~~~java
int[] source = {2, 4, 6};
int[] copied = source.clone();

copied[0] = 99;

System.out.println(source[0]); // 2
System.out.println(copied[0]); // 99
~~~

This snippet is a fragment inside a method (without a standalone `main` class). It illustrates a **primitive array**: each element is an `int` value, so copying the array copies those numbers.

If an array holds **references**, such as `Address[]`, calling `clone()` or `Arrays.copyOf` only creates a new array and copies **the element references**. The two arrays can continue pointing to the same mutable `Address` objects; that is a **shallow copy**, not a deep copy. Making the child objects independent as well requires copying according to the data structure and contract specific to each type.

## 7. Reference Fields Can Be Null; Primitive Fields Cannot

`null` represents **the absence of a reference to an object**. It is not an object itself, has no methods, and cannot be assigned directly to a primitive:

~~~java
class Customer {
    int age;          // cannot assign age = null
    String name;      // can receive null
}
~~~

If you write `customer.name.length()` when `name == null`, Java throws a `NullPointerException` at runtime.

A safe check:

~~~java
if (customer.name != null) {
    System.out.println(customer.name.length());
}
~~~

The snippet above requires that the `customer` variable already references a non-null `Customer`. If `customer == null` itself, even the expression `customer.name` causes a `NullPointerException`. When data is required to be present, you can validate early in the constructor:

~~~java
import java.util.Objects;

class RegisteredCustomer {
    private final String id;

    RegisteredCustomer(String id) {
        this.id = Objects.requireNonNull(id, "id");
    }
}
~~~

This is an illustrative declaration snippet, without `main`. `Objects.requireNonNull` throws `NullPointerException` when `id` is null, helping detect missing data right when the object is created. For other constraints (for example, a non-empty string), additional checks are needed.

### 7.1. Wrapper Classes and Auto-Unboxing

Primitives have corresponding wrapper classes: `Integer` for `int`, `Long` for `long`, `Double` for `double`, `Boolean` for `boolean`, and so on. **Wrapper-type fields are reference fields** and can hold `null`.

~~~java
class Registration {
    int attempts;       // defaults to 0
    Integer maxRetries; // defaults to null
}
~~~

`Integer value = 10;` uses autoboxing in an appropriate context. Meanwhile:

~~~java
Integer boxed = null;
// int unboxed = boxed; // Throws NullPointerException if executed
~~~

The compiler accepts assigning an `Integer` to an `int` via **unboxing**, but it will fail at runtime if the reference is `null`. Therefore, you need to choose correctly between "`0` is a meaningful value" and "no value yet".

Wrappers also have object allocation/representation overhead depending on optimizations and do not share the same semantics as primitives. Avoid using `Integer` just as a replacement for `int` unless nullability is needed or an API requires a reference type.

## 8. The == Operator and equals: Two Field Kinds Lead to Two Different Questions

### 8.1. For Primitives: Comparing Values

~~~java
int left = 42;
int right = 42;
System.out.println(left == right); // true
~~~

`==` on valid numeric/`char`/`boolean` primitives compares values according to Java's rules (which may involve numeric promotion). For floating-point numbers, note that `NaN == NaN` is `false`, and representation inaccuracy makes direct `double` comparison potentially unsuitable when checking approximate calculation results.

### 8.2. For References: == Checks for the Same Object

~~~java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);       // false: two different String objects
System.out.println(a.equals(b));  // true: String.equals compares content
~~~

This is a fragment inside a method. `new String("Java")` intentionally creates two distinct objects to illustrate identity; you do **not** need to construct Strings this way in normal applications. Do not rely on the fact that `"Java" == "Java"` sometimes yields `true` due to string interning to infer that `==` compares String content.

For reference fields, `Objects.equals(a, b)` is useful when one side might be null: it performs null checks and then calls `equals` appropriately. Note that each type's `equals` has its own contract; not every class defines content equality, because `Object.equals` defaults to identity comparison when not overridden.

| Purpose | Typical approach |
| --- | --- |
| Do two `int` values have the same value? | `x == y` |
| Do two references point to the same object? | `left == right` |
| Do two `String` instances have the same content? | `left.equals(right)` if `left` is non-null |
| Do two potentially null references have the same content? | `Objects.equals(left, right)` |
| Check whether a reference does not yet point to an object? | `value == null` |

## 9. final: Prevents Field Reassignment, but Does Not Guarantee Object Immutability

The `final` modifier follows the same fundamental principle across both groups of fields: once assigned during valid initialization, that field **cannot be reassigned**.

~~~java
class Example {
    final int id = 10;
    final String title = "Cơ bản";
    final int[] scores = {1, 2, 3};

    void update() {
        // id = 20;           // invalid: cannot reassign a final field
        // title = "Nâng cao"; // invalid: cannot reassign a final field
        scores[0] = 99;       // valid: modifies the array content
        // scores = new int[3]; // invalid: cannot reassign a final field
    }
}
~~~

This is a declaration snippet, without `main`. `final int id` fixes the primitive value `10` for an object. `final int[] scores` fixes **the field's reference**, while the referenced array remains mutable. For `String`, the final reference does not change and String itself is immutable, so there is no way to modify the content of the referenced String through normal APIs.

Levels to distinguish:

1. **Preventing reference reassignment:** `final` field.
2. **Objects whose state cannot be modified:** determined by class design; `String` is an example.
3. **Deeply immutable object graphs:** every observable component must be controlled; simply adding `final` to a reference is not enough.

Example of a class protecting an array with defensive copies:

~~~java
class GradeBook {
    private final int[] grades;

    GradeBook(int[] grades) {
        this.grades = grades.clone();
    }

    int[] getGrades() {
        return grades.clone();
    }
}
~~~

This is an illustrative declaration snippet, without `main`. Calling `clone()` in the constructor prevents the caller from retaining a reference to **the internal array itself**; calling `clone()` in the getter prevents the caller from modifying the internal array through the returned reference. For an `int[]` array, a single-level copy is sufficient to isolate the primitive values. For strict production code, you should check `grades != null` or use `Objects.requireNonNull` before cloning.

## 10. Primitive/Reference Fields Are Independent of Instance/Static

The two classifications are not mutually exclusive:

- **Primitive / reference** describes **the type of value that the field holds**.
- **Instance / static** describes whether the field belongs to **each object** or to the **class**.

Example:

~~~java
class RuntimeState {
    int currentLevel;                       // instance + primitive
    String currentUser;                     // instance + reference

    static int activeUsers;                 // static + primitive
    static String applicationName = "Demo"; // static + reference
}
~~~

This is an illustrative snippet, without `main`.

| Field | Primitive/reference | Instance/static |
| --- | --- | --- |
| `currentLevel` | Primitive `int` | Instance |
| `currentUser` | Reference `String` | Instance |
| `activeUsers` | Primitive `int` | Static |
| `applicationName` | Reference `String` | Static |

If there are two different `RuntimeState` objects, their `currentLevel` fields are independent. All instances of the same loaded class in a normal context share access to the static field `activeUsers`. If a static reference field points to a shared mutable object, any code with access through it can affect the same object.

**Static is not automatically thread-safe**. The operation `activeUsers++` can lose updates when multiple threads run concurrently; if data is shared across threads, proper synchronization design is required (for example, `AtomicInteger` or `synchronized`). Choosing a primitive does not eliminate the need for concurrency control.

## 11. Constructors, Encapsulation, and Data Protection

You should consider declaring fields as `private` and using constructors to establish valid state. For example, an order consisting of an `int` quantity and a `String` product code:

~~~java
import java.util.Objects;

class OrderLine {
    private final String productCode;
    private final int quantity;

    OrderLine(String productCode, int quantity) {
        Objects.requireNonNull(productCode, "productCode");

        if (productCode.isBlank()) {
            throw new IllegalArgumentException("productCode rỗng");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }

        this.productCode = productCode;
        this.quantity = quantity;
    }

    String getProductCode() {
        return productCode;
    }

    int getQuantity() {
        return quantity;
    }
}
~~~

This is a declaration snippet, without `main`. `productCode` is a `String` reference field; the constructor checks for null and empty content. `quantity` is a primitive field, so it cannot be null; the constructor still needs to validate the `int` value.

For **mutable reference types** such as `Date` or `ArrayList`, keeping them `private final` alone is not enough to protect invariants. If the caller passes in an object and later modifies it, the internal state can be affected. You can:

- Create an appropriate copy when receiving the object; for a collection containing immutable elements, `List.copyOf(source)` can create an unmodifiable list per the API and isolate it from structural mutations to `source`.
- Avoid returning a mutable object directly if the caller should not modify it; use a getter that returns a copy or an unmodifiable view when that meets the requirements.
- For collections containing mutable elements, you must also consider **the elements themselves**. `List.copyOf` does not automatically deep-copy each object inside.

**Unconditional copying is unnecessary:** an immutable object such as `String` can be shared safely with respect to content modification. The decision to copy depends on whether the object is mutable, ownership rules, and performance requirements.

## 12. When Should You Use a Primitive, and When a Reference?

| Need | Typical reasonable choice | Considerations |
| --- | --- | --- |
| Counting products, attempt counts, validated age | `int` or `long` | Is 0 meaningful or must it be validated? |
| Enabling/disabling a capability | `boolean` | Only true/false, no "unknown" state |
| Real-valued measurements | `double` | Binary representation has rounding error; do not use casually for money |
| Single character code as a UTF-16 code unit | `char` | Does not represent every full Unicode character |
| Names, codes, messages | `String` | Can be null; String is immutable |
| Collection of scores | `int[]` or an appropriate collection | The field holds a reference; aliasing must be considered |
| A related domain object | Class/interface type | Objects may be shared; mutability must be considered |
| Integer that may be "not entered yet" | `Integer` when an API requires null | Unboxing null can cause NPE; boxing overhead |
| Attribute with multiple variants or custom logic | Appropriately designed class/record | Enforces invariants instead of adding multiple loose fields |

Some data has specific rules: for currency, you can use `BigDecimal` (a reference type) or represent the smallest unit as a `long` if the problem allows it and overflow is controlled. There is no single field kind that is "right for every case"; the choice depends on the value domain, the possibility of missing data, and the class contract.

## 13. Common Misconceptions

1. **"A String field is primitive because it is assigned using a literal."** False: `String` is always a class/reference type; the `"text"` syntax simply provides a way to write a String literal.
2. **"An `int[]` array is primitive because it contains int values."** False: arrays are objects; an `int[]` field holds a reference to the array, and only each individual element is an `int`.
3. **"Assigning a reference copies the object."** False: it only copies the reference value. To isolate mutable state, you must create an appropriate copy.
4. **"Changing the reference in the second variable changes the first variable too."** False: assigning `b = new X()` only changes `b`; this differs from `b.field = value`, which mutates an object that both variables may be pointing to.
5. **"An unassigned int field is null."** False: instance/static fields of type `int` default to 0. Local variables cannot be read before assignment.
6. **"A reference field creates an empty object by default."** False: it defaults to `null`; a `String name;` field does not automatically create the String `""`, and an `int[] values;` field does not automatically create a length-0 array.
7. **"`final Address` makes every field of Address immutable."** False: `final` prevents reassigning the field's reference; it does not automatically prevent modifying `Address.city`.
8. **"Using `==` on two Strings compares their content."** False: `==` on references asks whether they refer to the same object; comparing content requires `equals` or the class's corresponding rules.
9. **"Java passes objects by reference."** Imprecise phrasing: Java **always passes arguments by value**. For reference types, the copied value is the reference; a method can modify the referenced object, but it cannot change the caller's variable simply by reassigning the parameter.
10. **"Primitives are always on the stack, and references are always on the heap."** False if treated as a language specification rule: instance fields belong to the object's state, static fields belong to the class, while how the JVM/JIT lays out or optimizes memory is an implementation detail.

### 13.1. Argument Passing Is Still by Value

Illustrative example (a fragment inside an appropriate class/method):

~~~java
static void change(int number, StringBuilder text) {
    number = 100;           // only changes the copy of the number
    text.append("!");       // modifies the shared StringBuilder object
    text = new StringBuilder("Khác"); // only reassigns the local parameter
}
~~~

If the caller has `int n = 1` and `StringBuilder s = new StringBuilder("Hi")`, and then calls `change(n, s)`, after the call `n` is still 1, while `s.toString()` is `"Hi!"`. Assigning `text = new ...` does not make `s` point to the new object. There is no concept of "pass-by-reference" for a Java variable in the sense of allowing a method to reassign the caller's variable.

## 14. Self-Check Questions

**Question 1.** `String code;` and `int quantity;` are two instance fields without explicit initialization. What values do they have after the object is created?

**Answer:** `code == null` and `quantity == 0`; these are the default values for reference and `int` fields.

**Question 2.** Is `int[] numbers` a primitive field or a reference field? What kind is the element `numbers[0]` after the array `new int[3]` has been assigned?

**Answer:** `numbers` is a reference field pointing to an array object; `numbers[0]` is a primitive `int` element, initialized to 0 by default.

**Question 3.** `first.address = second.address`. Can changing `first.address.city` affect `second.address.city`?

**Answer:** Yes, if both fields still point to the same mutable `Address` and the modification is permitted. The assignment copied the reference, not a copy of the object.

**Question 4.** `final int[] values = {1, 2};`. Can `values[0] = 7` and `values = new int[]{3, 4}` be executed?

**Answer:** Modifying the element `values[0]` is allowed, but reassigning the `values` field is not allowed because it is `final`.

**Question 5.** Why does `Integer retries = null; int x = retries;` fail at runtime even though it compiles?

**Answer:** The compiler inserts unboxing from `Integer` to `int`; unboxing a null reference causes a `NullPointerException`.

**Question 6.** Two variables `String a` and `String b` have the same text content. Is `a == b` guaranteed to be `true`?

**Answer:** No. `==` checks whether they refer to the same object. If you need to compare content, use `a.equals(b)` when `a` is non-null, or `Objects.equals(a, b)` if either can be null.

To read a class with many fields, answer these questions in order: **does the field hold a primitive value or a reference; is the default value valid; can the reference be null; is the pointed-to object mutable; can two fields alias the same object; is a defensive copy or validation needed**. Being able to answer those questions is the foundation for building Java object state that is easy to understand, safe, and verifiable.
