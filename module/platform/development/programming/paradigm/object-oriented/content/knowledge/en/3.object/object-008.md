# Null Values and Objects That Do Not Exist in Java

In Java, a **reference variable** can either point to an object or hold `null`. When its value is `null`, **there is no object accessible through that reference**. This differs from an existing object containing empty data and from a local variable that has not yet been assigned.

For example, in a sales application:

- A customer exists but has not supplied a `phoneNumber`: the field may be represented by `null` if the model permits it.
- A customer exists with `phoneNumber = ""`: there is a `String` object containing an empty string, not `null`.
- A customer-ID lookup finds no result: no entity matches the search; an API may represent this using `Optional.empty()` or `null`.
- Declaring `Customer customer;` inside a method without assigning it: this is **an uninitialized local variable** that cannot be read.
- Assigning `customer = null` after using it: this changes only the reference variable; the old object may still exist because other code may retain references.

The goal of this lesson is to understand **absence**, **object lifecycles**, and **how to write code that avoids invalid `null` access**.

## 1. What Exactly Is `null`?

`null` is the special value of Java's **null type** and can be assigned to compatible reference types, such as objects, arrays, interfaces, and wrapper classes. `null` is not an instance created using `new`.

~~~java
String title = null;
Customer customer = null;
int[] scores = null;
Runnable task = null;
~~~

These declarations are type-correct. None creates a `String`, `Customer`, array, or `Runnable` object through assignment of `null`.

By contrast, primitive types such as `int`, `long`, `double`, `boolean`, and `char` cannot hold `null`:

~~~java
int quantity = 0;        // Hợp lệ: số nguyên có giá trị 0.
// int count = null;     // Lỗi biên dịch.
Integer optionalCount = null; // Hợp lệ: Integer là kiểu tham chiếu.
~~~

**Key point:** `null` is a **reference value**, not an “empty” object on which methods can be called. With `customer.getName()`, Java must obtain the object through `customer`; if `customer == null`, invoking this instance method throws `NullPointerException`.

## 2. Four Commonly Confused Situations

| Situation | Example | Is an object created? | What it means |
|---|---|---|---|
| Unassigned local variable | `Customer c;` | None created by this declaration | `c` cannot be read until it is properly assigned on every required path |
| Reference variable holding `null` | `Customer c = null;` | None created by this assignment | `c` currently refers to no object |
| Reference pointing to an object | `Customer c = new Customer("Lan");` | Yes, if construction succeeds | An instance exists and `c` refers to it |
| Object with empty data | `String s = "";` or `new ArrayList<>()` | Yes, an appropriate object exists | The object exists; its contents happen to be empty |

Consider this example:

~~~java
String a = null;
String b = "";
String c = " ";

System.out.println(a == null);     // true
System.out.println(b == null);     // false
System.out.println(b.isEmpty());   // true
System.out.println(c.isEmpty());   // false
System.out.println(c.isBlank());   // true (Java 11+)
~~~

- `null`: there is no reference to a `String` object.
- `""`: a string exists with length zero.
- `" "`: a string contains a space; it is not empty under `isEmpty()` but is blank under `isBlank()`.

Similarly, for collections, `List<String> names = null` means no list is currently accessible through that variable, while `List<String> names = List.of()` means **a list exists with size zero**. These situations have different meanings and should not be substituted arbitrarily.

## 3. How Does an Uninitialized Local Variable Differ from `null`?

A method's local variable must be **definitely assigned** before use. Java checks this at compile time:

~~~java
void demo() {
    String name;
    // System.out.println(name); // Lỗi: variable name might not have
    //                           // been initialized.
    name = "Lan";
    System.out.println(name);    // Hợp lệ.
}
~~~

If we assign `name = null;`, the variable **has been assigned according to the language rules**, but its reference value is `null`:

~~~java
void demo() {
    String name = null;
    System.out.println(name == null); // true
}
~~~

For object fields, static fields, and array elements, Java supplies **default values** unless other assignments are made:

| Data type | Default value of a field/array element |
|---|---|
| `byte`, `short`, `int`, `long` | Corresponding numeric zero |
| `float`, `double` | Corresponding 0.0 value |
| `boolean` | `false` |
| `char` | Character `'\u005Cu0000'` (U+0000) |
| Reference types such as `String`, `Customer`, and arrays | `null` |

For example:

~~~java
class Profile {
    String email; // Mặc định null nếu không được gán.
    int points;   // Mặc định 0.
}

Profile profile = new Profile();
System.out.println(profile.email == null); // true
System.out.println(profile.points);        // 0

String[] labels = new String[2];
System.out.println(labels[0] == null);     // true
~~~

Default values **do not apply to ordinary local variables**. Prefer intentional field initialization through constructors rather than relying on defaults, especially when `null` is not a valid object state.

## 4. Distinguishing a Reference Variable from the Object Itself

Think of a reference variable as a “path” to an object. Multiple paths can reach the same object; removing one path does not automatically delete it.

~~~java
class Box {
    int value;
}

Box first = new Box();
first.value = 42;

Box alias = first;
first = null;

System.out.println(first == null); // true
System.out.println(alias.value);   // 42
~~~

`new Box()` creates one object, initially referenced by both `first` and `alias`. After `first = null`, `alias` still refers to that object.

~~~mermaid
flowchart TD
    A["Biến first"] --> N["null<br/>Không trỏ đến object"]
    B["Biến alias"] --> O["Đối tượng Box<br/>value = 42"]
~~~

The diagram depicts the situation **after assigning `first = null`**; it does not represent actual memory addresses.

This clarifies three commonly confused statements:

1. **“The variable is null”** only describes the reference variable's current value.
2. **“The object has been deleted”** cannot be inferred from assigning `null`. Java has no `delete object` operation like some languages use for resource management.
3. **“The object is no longer reachable”** means there is no reference path from GC roots to the object. It *may then become eligible* for garbage collection, but the collection time is not guaranteed.

An object may also remain in memory while no reference accessible to program code can reach it. Thus, distinguish **reachability** from **physical presence in memory at a particular moment**.

## 5. Complete Java Example: A Customer May or May Not Be Found

The following program runs with **Java 17+**. The repository stores one customer; looking up an existing ID returns an `Optional<Customer>` containing that customer, while a missing ID returns `Optional.empty()`.

Save it as **`Demo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class Demo {
    public static void main(String[] args) {
        CustomerRepository repository = new CustomerRepository();

        Optional<Customer> found = repository.findById("C01");
        Optional<Customer> missing = repository.findById("C99");

        System.out.println("Có C01: " + found.isPresent());
        System.out.println("Có C99: " + missing.isPresent());

        String name = found
                .map(Customer::getName)
                .orElse("Không tìm thấy");

        String absentName = missing
                .map(Customer::getName)
                .orElse("Không tìm thấy");

        System.out.println("Tên C01: " + name);
        System.out.println("Tên C99: " + absentName);

        Customer one = found.orElseThrow();
        Customer alias = one;

        System.out.println("Cùng object: " + (one == alias));
        System.out.println("Địa chỉ giao hàng: "
                + one.getShippingAddress()
                     .orElse("Chưa cung cấp"));

        try {
            repository.findById("C99")
                    .orElseThrow(() -> new IllegalArgumentException(
                            "Không có khách hàng C99"));
        } catch (IllegalArgumentException exception) {
            System.out.println(exception.getMessage());
        }

        // Objects.equals xử lý an toàn khi một hoặc cả hai vế null.
        String inputName = null;
        System.out.println("Tên khớp: "
                + Objects.equals(inputName, one.getName()));
    }

    static final class Customer {
        private final String id;
        private final String name;
        private String shippingAddress;

        Customer(String id, String name) {
            this.id = Objects.requireNonNull(id, "id không được null");
            this.name = Objects.requireNonNull(name, "name không được null");
            if (id.isBlank() || name.isBlank()) {
                throw new IllegalArgumentException(
                        "id và name không được rỗng");
            }
        }

        String getName() {
            return name;
        }

        Optional<String> getShippingAddress() {
            return Optional.ofNullable(shippingAddress);
        }

        void setShippingAddress(String address) {
            if (address != null && address.isBlank()) {
                throw new IllegalArgumentException(
                        "Địa chỉ không được chỉ chứa khoảng trắng");
            }
            this.shippingAddress = address;
        }
    }

    static final class CustomerRepository {
        private final Map<String, Customer> customers =
                Map.of("C01", new Customer("C01", "Lan"));

        Optional<Customer> findById(String id) {
            Objects.requireNonNull(id, "id không được null");
            return Optional.ofNullable(customers.get(id));
        }
    }
}
~~~

Run in a terminal:

~~~bash
javac Demo.java
java Demo
~~~

Output:

~~~text
Có C01: true
Có C99: false
Tên C01: Lan
Tên C99: Không tìm thấy
Cùng object: true
Địa chỉ giao hàng: Chưa cung cấp
Không có khách hàng C99
Tên khớp: false
~~~

### Explaining Each Situation

**Case 1 — The customer exists:** the repository holds a `Customer("C01", "Lan")` object, and `findById("C01")` returns an `Optional` containing a reference to that object. `one` and `alias` are obtained from the same reference, so `one == alias` is `true`.

**Case 2 — The customer is not found:** `Map.get("C99")` returns `null` because the map lacks that key. `Optional.ofNullable(...)` converts it to `Optional.empty()`. There is **no matching query result**; this alone says nothing about whether another object with the same information exists elsewhere in the system.

**Case 3 — The customer exists but has no address:** the `Customer` object exists, but its `shippingAddress` field may contain `null`. The getter exposes possible absence through `Optional<String>`. “Address not provided” does not mean “customer does not exist.”

**Case 4 — Required data must not be null:** the constructor calls `Objects.requireNonNull` to reject an `id` or `name` whose value is `null`. The `isBlank()` check also rejects empty or whitespace-only strings. Thus, an object constructed successfully cannot have invalid values in those two required fields.

In a real application, the repository might query a database instead of a `Map`; the same principles for representing absent data apply.

## 6. Why Does `NullPointerException` Occur?

`NullPointerException` (NPE) is a common runtime error that occurs when code attempts to use a `null` reference as though it pointed to a valid object.

For example:

~~~java
String title = null;
// System.out.println(title.length()); // NPE nếu bỏ comment.

Customer customer = null;
// customer.getName();                  // NPE nếu gọi.

int[] numbers = null;
// System.out.println(numbers.length);  // NPE nếu truy cập độ dài mảng.
~~~

Here, the variable **has a valid type** but there is no object to access. In ordinary Java, the compiler generally cannot prevent these calls; the error occurs when execution reaches the statement.

Distinguish it from other errors:

| Situation | Result |
|---|---|
| Reading an unassigned local variable | Compile-time error |
| Calling an instance method on `null` | `NullPointerException` |
| Accessing an instance field through `null` | `NullPointerException` |
| Reading an array element when the array reference is `null` | `NullPointerException` |
| Accessing an existing array with an out-of-range index | `ArrayIndexOutOfBoundsException` |
| Calling `Optional.empty().get()` | `NoSuchElementException` |
| Explicitly using `Objects.requireNonNull(null)` | Intentional `NullPointerException` to report missing required data |

An NPE does not mean “the garbage collector deleted the object halfway through an operation.” It means the current operation attempted to use a `null` reference incorrectly.

### Automatic Unboxing Can Also Cause an NPE

The `Integer` wrapper can be `null`. When Java converts an `Integer` to `int` (auto-unboxing), it must obtain a value from the object:

~~~java
Integer quantity = null;
// int total = quantity + 1; // NPE do unboxing quantity.
~~~

If a quantity **must always be present**, a primitive `int` with separate validation rules is often suitable. If the data may be absent, represent that absence explicitly and handle it before calculating.

## 7. Appropriate Strategies for Avoiding `null` Errors

No single approach fits every problem. First determine: **is missing data permitted, or is its absence an error?**

### Approach 1 — Explicitly Check for `null`

~~~java
String middleName = getMiddleName();

if (middleName != null) {
    System.out.println(middleName.toUpperCase());
} else {
    System.out.println("(không có tên đệm)");
}
~~~

This is appropriate when the API defines `null` as a valid value. Place the check near the dereference and apply it to the variable actually being used.

If you only want to invoke behavior when an object exists:

~~~java
if (customer != null) {
    customer.sendWelcomeMessage();
}
~~~

The `customer.sendWelcomeMessage()` snippet illustrates a `Customer` class with that method; the `Customer` defined in `Demo.java` above does not provide it.

### Approach 2 — Use `Objects.requireNonNull` for Required Data

~~~java
import java.util.Objects;

class Product {
    private final String sku;

    Product(String sku) {
        this.sku = Objects.requireNonNull(sku, "SKU bắt buộc");
    }
}
~~~

If `sku == null`, the constructor immediately throws an NPE with a clear message at the point of contract violation. This check **does not** reject `""` or whitespace-only strings; add a separate content rule if required.

You may use `IllegalArgumentException` when application conventions classify invalid inputs that way. What matters is consistent input contracts and preventing missing required state from spreading deeper into the system.

### Approach 3 — Use `Optional<T>` for Potentially Absent Results

~~~java
Optional<Customer> result = repository.findById("C01");

result.ifPresent(c -> System.out.println(c.getName()));

String displayName = result.map(Customer::getName)
                           .orElse("Khách chưa xác định");

Customer required = result.orElseThrow(
        () -> new IllegalStateException("Khách hàng không tồn tại"));
~~~

`Optional<T>` is a wrapper object representing either **a present value** or **an absent value**:

| API | Meaning |
|---|---|
| `Optional.of(value)` | Requires `value` to be non-`null`; otherwise throws an NPE |
| `Optional.ofNullable(value)` | May produce `Optional.empty()` if the value is null |
| `Optional.empty()` | Represents no value |
| `map(fn)` | Transforms a present value; a mapper returning null produces an empty result |
| `orElse(defaultValue)` | Returns the value or a default |
| `orElseGet(supplier)` | Creates the default only when empty |
| `orElseThrow(...)` | Reports an error when no value exists |
| `ifPresent(action)` | Performs an action when a value exists |

**Pitfall:** `orElse(expensiveCall())` evaluates `expensiveCall()` as an argument **even when the Optional has a value**. To call it only when absent, use `orElseGet(() -> expensiveCall())`.

Avoid using `Optional.get()` without checking presence: `Optional.empty().get()` throws `NoSuchElementException`. Usually prefer `orElse`, `orElseThrow`, `map`, or `ifPresent`.

**Practice:** `Optional` is particularly useful as a **return type** for methods whose result may be missing. There is no need to replace every field, parameter, collection, or object with `Optional`. Avoid methods that sometimes return `Optional.empty()` but at other times return **`null` instead of an Optional**, forcing callers to handle yet another level of absence.

### Approach 4 — Return an Empty Collection When the Contract Allows “Zero or More Elements”

~~~java
import java.util.List;

List<String> findTagsForProduct(String productId) {
    return List.of(); // Không có tag; vẫn là List hợp lệ.
}
~~~

Returning `List.of()` instead of `null` allows callers to handle results uniformly:

~~~java
for (String tag : findTagsForProduct("P01")) {
    System.out.println(tag);
}
~~~

For APIs that retrieve multiple elements, an empty list is often more natural than `null`: the search simply has **zero results**. However, if “not yet loaded,” “load failed,” and “loaded successfully but empty” are distinct business states, model them explicitly rather than collapsing them all into an empty list.

### Approach 5 — Compare Strings and Objects Safely

~~~java
import java.util.Objects;

String status = null;

System.out.println("ACTIVE".equals(status)); // false
System.out.println(Objects.equals(status, "ACTIVE")); // false
System.out.println(Objects.equals(null, null)); // true
~~~

`status.equals("ACTIVE")` throws an NPE if status is null. To compare object contents, use `equals()` according to the type's contract; `==` between references checks **whether they point to the same object**, not ordinary content equality.

## 8. Detecting `null` with Java Syntax and Safe Conditions

### Comparing with `== null` / `!= null`

~~~java
if (customer == null) {
    System.out.println("Chưa có khách hàng");
} else {
    System.out.println(customer.getName());
}
~~~

Comparing with `null` using `==` is correct. Do not write `customer.equals(null)`: it can throw an NPE when the customer reference is null and also expresses the wrong intent for reference checking.

### Short-Circuit Logical Operators

Java evaluates `&&` from left to right and stops when the left condition is `false`:

~~~java
if (customer != null && customer.isActive()) {
    System.out.println("Có khách hàng đang hoạt động");
}
~~~

`customer.isActive()` is called only when `customer != null`. This illustrates a class with an `isActive()` method.

Reversing the condition can cause an error:

~~~java
// Sai: customer có thể bị dereference trước khi kiểm tra null.
// if (customer.isActive() && customer != null) { ... }
~~~

Similarly, the `||` operator stops when its left operand is true, so `customer == null || customer.isActive()` can avoid null dereferences under single-threaded conditions when the reference is not concurrently changed. Nevertheless, write readable conditions and avoid evaluation side effects.

### `instanceof` with a Null Variable

~~~java
Object value = null;

System.out.println(value instanceof String); // false
~~~

`instanceof` with a `null` operand evaluates to `false` without throwing an NPE. This does not make `null` a `String` object.

### Java Does Not Have the `?.` Operator Found in Some Other Languages

The syntax `customer?.getName()` **is not valid safe-access syntax in Java 17**. Check for `null`, use Optional, or design an API that explicitly models absent data. Do not confuse Kotlin, C#, or JavaScript syntax with Java.

## 9. When Does an Object “Not Yet Exist”?

That phrase has several different meanings:

| Context | Example | Correct interpretation |
|---|---|---|
| In Java code | `User u = null;` | No `User` object is accessible through `u`; a User may still exist elsewhere |
| In a query result | `findById("C99")` returns empty | No matching record was found at query time |
| In a business workflow | No order exists for a cart | An order may not yet have been created or persisted; business rules determine what that means |
| In JVM memory | An object is no longer reachable | It may be reclaimed by GC later; the precise moment cannot be inferred |
| In control flow | A constructor has not been called | The current code path has not created an instance that way |

For example:

~~~java
Order order = null;

// Sau thao tác hợp lệ nào đó:
order = new Order(); // Tạo một instance nếu constructor thành công.
~~~

You cannot infer from `order == null` that “no Order exists anywhere in the program.” You can only say **the `order` variable currently points to no Order**.

Conversely, if an entity has no database record, creating `new Order()` in memory **does not automatically** create a database record. A Java object and the existence of a persisted entity belong to different layers.

### An Existing Object Whose State Contains a Null Field

~~~java
class Employee {
    final String name;
    String managerName; // null nếu chưa có người quản lý.

    Employee(String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}

Employee employee = new Employee("Mai");
System.out.println(employee == null);             // false
System.out.println(employee.managerName == null); // true
~~~

This is a realistic scenario: **the employee object exists**, but direct-manager information is missing. A `null` field does not make the entire object null.

## 10. Choosing How to Represent Absence in OOP Design

Before choosing `null`, ask **what absence means in the business domain**.

~~~mermaid
flowchart TD
    A["Cần biểu diễn dữ liệu có thể vắng mặt"] --> B{"Dữ liệu có bắt buộc không?"}
    B -->|Có| C["Kiểm tra ngay ở constructor / ranh giới API"]
    B -->|Không| D{"Kết quả có nhiều phần tử?"}
    D -->|Có| E["Thường trả collection rỗng khi 0 kết quả"]
    D -->|Không| F{"Là kết quả truy vấn đơn có thể không tìm thấy?"}
    F -->|Có| G["Cân nhắc Optional&lt;T&gt; làm kiểu trả về"]
    F -->|Không| H["Mô hình hóa nullable field hoặc trạng thái nghiệp vụ tường minh"]
~~~

The diagram suggests design choices rather than absolute rules. For example, if `null` means “not yet loaded” and `List.of()` means “loaded but empty,” replacing `null` with an empty list loses information. With multiple business states, consider a dedicated type:

~~~java
sealed interface LoadResult<T>
        permits Loaded, NotFound, LoadFailed {}

record Loaded<T>(T value) implements LoadResult<T> {}
record NotFound<T>() implements LoadResult<T> {}
record LoadFailed<T>(String reason) implements LoadResult<T> {}
~~~

The records illustrate that **“not found” differs from “loading failed.”** Java 17 fully supports sealed interfaces and records. If immutable state is required, validate mandatory values in the corresponding record constructors.

### Distinguishing Errors from Normal Cases

- **ID not found** can be an ordinary result: use `Optional.empty()` or an explicit result type.
- **Null ID when the contract requires an ID** is generally a caller error: validate immediately and provide a suitable message.
- **Database connection failure** is not equivalent to “no customer exists”: report the failure instead of returning `Optional.empty()` and misleading callers.
- **A search with zero matches** is commonly represented by an empty collection.
- **An optional attribute not yet supplied** may permit null internally, but the API should make its validity and usage contract clear.

In larger systems, API documentation and tests help callers understand when they must handle absent data.

## 11. Common Mistakes to Avoid

| Mistake | Problem | Fix |
|---|---|---|
| Calling `obj.method()` when `obj` may be null | Runtime NPE | Check for null or design a safe return type |
| Treating `""` as `null` | Incorrect data rules | Distinguish missing, empty, and blank |
| Using a nullable `Integer` in arithmetic | Auto-unboxing may throw an NPE | Validate or provide a business-appropriate default before calculation |
| Returning `null` instead of a list with no elements | Callers must branch in many places | Consider returning an empty collection |
| Returning `null` instead of `Optional<T>` | Violates the contract and undermines `Optional` | Return `Optional.empty()` when no result exists |
| Calling `Optional.get()` without checking | May throw `NoSuchElementException` | Use `orElseThrow`, `orElse`, `map`, etc. |
| Catching every NPE and silently ignoring it | Hides programming or data errors | Fix where null values originate or are read; fail fast when needed |
| Using `null` for every unclear state | Conflates “not entered,” “not present,” and “query failed” | Model business states explicitly |
| Assigning `x = null` and assuming the object was destroyed | Other aliases may remain or GC may not have run | Understand reachability; manage resources appropriately |
| Using `null` as a reason to skip closing files/connections | Leaks external resources outside the heap | Use try-with-resources for `AutoCloseable` resources |

**Note:** the garbage collector manages Java object memory according to the JVM model; it does not guarantee timely closure of files, sockets, or database connections. Do not treat assigning `null` as releasing every kind of resource.

## 12. Practice and Self-Assessment

### Exercise 1 — Predict the Output

~~~java
String first = null;
String second = "";
System.out.println(first == null);
System.out.println(second == null);
System.out.println(second.length());
~~~

**Answer:**

~~~text
true
false
0
~~~

`second` refers to an empty string, so `length()` is valid and returns 0.

### Exercise 2 — Two References to One Object

~~~java
class Note {
    String text = "Ban đầu";
}

Note one = new Note();
Note two = one;
one = null;
System.out.println(two.text);
~~~

**Answer:** Prints `Ban đầu`. Assigning `one = null` does not delete the object referenced by `two`.

### Exercise 3 — At Which Stage Does the Error Occur?

~~~java
String value;
// System.out.println(value);
~~~

**Answer:** Uncommenting the statement that reads `value` causes a **compile-time error** because the local variable has not been assigned. This is not an NPE.

### Exercise 4 — Wrappers and Unboxing

~~~java
Integer score = null;
// int doubled = score * 2;
~~~

**Answer:** Uncommenting the calculation can throw an NPE when Java automatically unboxes `score` to `int`.

### Exercise 5 — Search APIs

A `findUserById(id)` method must distinguish “not found” from “database server failure.” Should it return `Optional.empty()` for both?

**Answer:** No. `Optional.empty()` can represent “not found.” Database access failures must be reported according to the API contract (for example, through an exception or explicit error result) so they are not mistaken for normal absence.

### Exercise 6 — Write a Safe Method

Requirement: accept `String name`, return `"(chưa có tên)"` when `name` is null or consists only of whitespace, and otherwise return the `trim()`-processed string.

Suggested solution:

~~~java
static String displayName(String name) {
    if (name == null || name.isBlank()) {
        return "(chưa có tên)";
    }
    return name.trim();
}
~~~

The `name.isBlank()` expression is evaluated only if `name != null`, because of `||` short-circuiting, so it causes no NPE.

## Remember

In Java, `null` means **the current reference value does not refer to any object**; it is not an empty object. An unassigned local variable is an *initialization* issue checked by the compiler. Empty strings and lists are still **real objects**. Assigning `null` does not mean an object has been destroyed, and a missing query result does not always prove the entity never existed.

When designing classes and APIs, distinguish **required data**, **legitimately absent data**, **not-found results**, and **errors**. Then choose `requireNonNull`, `null` checks, `Optional`, empty collections, or suitable domain result types. This reduces `NullPointerException` errors and keeps object semantics clear in OOP designs.
