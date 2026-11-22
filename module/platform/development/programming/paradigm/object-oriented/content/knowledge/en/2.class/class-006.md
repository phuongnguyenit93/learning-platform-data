# Read-only and mutable members in Java classes

When designing a class, not all object data should be modifiable after initialization. A product's identifier usually needs to remain unchanged, while its display name or selling price may change according to business rules. Java supports both categories of attributes through **encapsulation**, the `final` keyword, read methods (getters), and update methods (setters or domain-specific methods).

> **Key idea:** "Read-only" may mean *callers can only view a value* or *the value cannot be reassigned after initialization*. These ideas are related but not identical. Be clear about whether you are protecting **a reference**, **an object's state**, or **the right to update it externally**.

## 1. Distinguishing member types

In Java, "class members" include fields, methods, nested classes, and more. When discussing "read-only/mutable" members, we usually mean **attributes/state** and the APIs that expose them.

| Declaration or exposed API | Readable externally? | Directly modifiable externally? | Changeable inside the class? |
| --- | --- | --- | --- |
| `private final String id` + `getId()` | Yes | No | Cannot reassign `id` after initialization |
| `private String name` + `getName()`, `setName()` | Yes | Through the setter | Yes, subject to setter validation |
| `private int stock` + `getStock()`, `reserve()` | Yes | Only through the `reserve()` operation | Yes, according to business rules |
| `public String name` | Yes | Yes, by direct assignment | Yes, hard to control |
| `private final List<String> tags` + `getTags()` | Yes | Depends on how the list is returned | The reference cannot be reassigned, but elements may still be changed if the list is mutable |

**Encapsulation** usually starts by declaring fields `private`, then exposing only the methods that are genuinely necessary. Getters and setters are design choices, not a rule requiring both for every attribute.

## 2. Practical example: a product with read-only and updatable attributes

Suppose a product management system requires:

- **SKU**: product code, which must not change after creation.
- **createdAt**: creation timestamp, which must not change.
- **name**: display name, which may be edited but must not be blank.
- **price**: selling price, which may be edited but must not be negative.

`Product.java` (Java 11+):

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;

public class Product {
    // Chỉ được gán trong quá trình khởi tạo đối tượng.
    private final String sku;
    private final Instant createdAt;

    // Có thể được gán lại thông qua các phương thức được kiểm soát.
    private String name;
    private BigDecimal price;

    public Product(String sku, String name, BigDecimal price) {
        this.sku = Objects.requireNonNull(sku, "sku").trim();
        if (this.sku.isEmpty()) {
            throw new IllegalArgumentException("SKU không được rỗng");
        }

        this.createdAt = Instant.now();
        setName(name);
        setPrice(price);
    }

    // API chỉ đọc.
    public String getSku() {
        return sku;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    // API đọc/ghi có kiểm soát.
    public String getName() {
        return name;
    }

    public void setName(String name) {
        String value = Objects.requireNonNull(name, "name").trim();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Tên không được rỗng");
        }
        this.name = value;
    }

    public BigDecimal getPrice() {
        return price;
    }

    public void setPrice(BigDecimal price) {
        Objects.requireNonNull(price, "price");
        if (price.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
        this.price = price;
    }
}
~~~

Usage:

~~~java
import java.math.BigDecimal;

public class Main {
    public static void main(String[] args) {
        Product product = new Product(
                "BOOK-001", "Java căn bản", new BigDecimal("150000")
        );

        System.out.println(product.getSku());       // BOOK-001
        System.out.println(product.getCreatedAt()); // Thời điểm tạo
        System.out.println(product.getPrice());     // 150000

        product.setName("Java nâng cao"); // Hợp lệ
        product.setPrice(new BigDecimal("180000")); // Hợp lệ

        // product.setSku("BOOK-002"); // Lỗi biên dịch: không có setSku
        // product.sku = "BOOK-002";  // Lỗi biên dịch: sku là private

        // Ném IllegalArgumentException:
        // product.setPrice(new BigDecimal("-1000"));
    }
}
~~~

The key point is that **the class decides who may modify an attribute**. Callers of `Product` can read `sku` but have no public way to update it; they can change `price` only through a method that validates the new price. This design helps prevent objects from entering invalid business states.

## 3. What does `final` protect?

A `final` field may be **assigned exactly once** during initialization: at its declaration, in an initializer block, or in an appropriate constructor. After assignment, that field cannot be reassigned.

~~~java
public class Customer {
    private final long id;
    private String email;

    public Customer(long id, String email) {
        this.id = id;
        this.email = email;
    }

    public long getId() { return id; }
    public String getEmail() { return email; }

    public void changeEmail(String email) {
        this.email = email;
    }

    // public void changeId(long newId) {
    //     this.id = newId; // LỖI: không thể gán lại final field
    // }
}
~~~

However, **`final` on a reference variable does not make the referenced object immutable**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class Basket {
    private final List<String> items = new ArrayList<>();

    public void add(String item) {
        items.add(item); // Hợp lệ: thay đổi nội dung List
    }

    public List<String> getItems() {
        return items; // Nguy hiểm: làm lộ List mutable
    }
}
~~~

The following code can modify internal data without going through `add`:

~~~java
Basket basket = new Basket();
basket.add("Sách");
basket.getItems().clear(); // Xóa dữ liệu nội bộ!
~~~

`items` cannot point to another list because it is `final`, but the existing list can still change. Likewise, a getter without a setter is **not enough** to guarantee that an object is immutable.

## 4. Creating safe read-only APIs for collections

If the desired state is a read-only list, you can create an **unmodifiable copy** during initialization:

~~~java
import java.util.List;
import java.util.Objects;

public class Course {
    private final String code;
    private final List<String> topics;

    public Course(String code, List<String> topics) {
        this.code = Objects.requireNonNull(code, "code");
        this.topics = List.copyOf(
                Objects.requireNonNull(topics, "topics")
        );
    }

    public String getCode() {
        return code;
    }

    public List<String> getTopics() {
        return topics;
    }
}
~~~

Verification:

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> input = new ArrayList<>(List.of("OOP", "Exception"));
Course course = new Course("JAVA-01", input);

input.add("Thread"); // Không ảnh hưởng topics của course

System.out.println(course.getTopics()); // [OOP, Exception]

// Ném UnsupportedOperationException:
course.getTopics().add("Spring");
~~~

`List.copyOf` (Java 10+) creates an unmodifiable list that does not reflect later changes to the input list. Note that this provides **shallow immutability**. If its elements are mutable objects, those objects can still be modified through other references; the example above is safe because `String` is immutable. `List.copyOf` also disallows `null` elements.

Quick comparison:

| Return approach | Characteristics |
| --- | --- |
| `return internalList;` | Callers can modify it directly if it is a mutable List |
| `return Collections.unmodifiableList(internalList);` | Callers cannot modify it through the view, but the view still reflects changes to the underlying list |
| `return List.copyOf(internalList);` | The returned list is unmodifiable; it creates a logical snapshot of the elements |
| `return new ArrayList<>(internalList);` | Callers can modify the copy without affecting the internal list (provided elements do not share mutable state) |

If a class **must continue managing a mutable list internally**, its getter can return `List.copyOf(items)` to provide a read-only snapshot on each call, while domain methods perform internal updates.

## 5. Read-only from outside, but mutable inside

Sometimes a value is allowed to change but **should not have a public setter**. For example, inventory should decrease only for a valid order; exposing `setStock(int)` would let callers bypass the ordering process.

~~~java
public class Inventory {
    private int available;

    public Inventory(int initialQuantity) {
        if (initialQuantity < 0) {
            throw new IllegalArgumentException("Tồn kho không được âm");
        }
        this.available = initialQuantity;
    }

    public int getAvailable() {
        return available; // Người ngoài chỉ đọc được con số
    }

    public void reserve(int quantity) {
        if (quantity <= 0 || quantity > available) {
            throw new IllegalArgumentException("Số lượng đặt không hợp lệ");
        }
        available -= quantity;
    }

    public void restock(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng nhập phải dương");
        }
        available = Math.addExact(available, quantity);
    }
}
~~~

~~~java
Inventory inventory = new Inventory(10);
inventory.reserve(3);
System.out.println(inventory.getAvailable()); // 7

// inventory.setAvailable(999); // Không có API này
~~~

Here, `available` is **not a final field** because its value changes after transactions. But external callers still have **read-only access through the getter**; every change must go through `reserve` or `restock`.

The flow of responsibility can be visualized as follows:

~~~mermaid
flowchart TD
    A["Code sử dụng Inventory"] --> B["getAvailable(): đọc tồn kho"]
    A --> C["reserve(quantity): yêu cầu đặt"]
    C --> D{"Số lượng hợp lệ?"}
    D -->|Có| E["Cập nhật available"]
    D -->|Không| F["Ném ngoại lệ"]
~~~

**Concurrency note:** The `Inventory` example illustrates encapsulation in a single-threaded environment. If multiple threads or requests place orders concurrently, stock validation and decrementing must be protected by appropriate synchronization, transactions, or locking; `private`, getters, and `final` do not prevent race conditions on their own.

## 6. Are read-only attributes, constants, and immutable objects the same?

| Concept | Main meaning | Example |
| --- | --- | --- |
| Read-only API | External code can observe state but cannot assign arbitrary values | `getAvailable()` without `setAvailable()` |
| Final field | A field cannot be reassigned after initialization | `private final String sku` |
| Constant | A value often shared across the class, commonly using `static final` | `public static final int MAX_ITEMS = 100;` |
| Immutable object | All observable state remains unchanged after creation | `String`, `BigDecimal`, a properly designed value object class |
| Mutable object | Some state can change over time | `Product` with `setPrice()` |

Constant example:

~~~java
public final class CartRules {
    private CartRules() {
        // Không cho tạo instance của lớp tiện ích.
    }

    public static final int MAX_ITEMS = 100;
}

// Dùng: CartRules.MAX_ITEMS
~~~

A `static final` reference to a mutable object still **does not automatically make that object immutable**. Constants of primitive types or `String` are more straightforward and safer examples.

Java 16+ also provides **records**, which simplify representing read-only data:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

public record ProductSummary(String sku, BigDecimal price) {
    public ProductSummary {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(price, "price");
        if (price.signum() < 0) {
            throw new IllegalArgumentException("Giá không được âm");
        }
    }
}
~~~

~~~java
ProductSummary summary =
        new ProductSummary("BOOK-001", new BigDecimal("200000"));

System.out.println(summary.sku());
System.out.println(summary.price());

// summary.price = ...; // Không thể gán: component thuộc record là final
// summary.setPrice(...); // Record không tự tạo setter
~~~

Because `String` and `BigDecimal` are both immutable, `ProductSummary` is an immutable value object with these components. **Records provide only shallow immutability**: if a component is a `List` or another mutable object, defensive copying, controlled accessors, or suitably immutable component design is needed.

## 7. Choosing a design based on business requirements

Before declaring a field, identify **who may change it**, **when it may change**, and **which values are valid**:

| Attribute | Commonly suitable design | Reason |
| --- | --- | --- |
| Invoice or product code | `private final` + getter | Identity remains stable after initialization |
| Display name | `private` + getter + validated setter | Updates are allowed but must be valid |
| Account balance | `private` + getter + `deposit()/withdraw()` | Avoids arbitrary setters that bypass rules |
| Creation date | `private final Instant` + getter | A historical timestamp that need not change |
| List of roles | Unmodifiable copy or controlled update API | Prevents direct caller interference |
| Total calculated from line items | Calculated getter; omit the field if unnecessary | Prevents derived data from going out of sync |

**Common beginner mistakes:**

1. Automatically generating setters for every field, including identifiers or important business state.
2. Assuming `private` means immutable. In fact, `private` only restricts direct access.
3. Assuming `final List<T>` makes the entire list and its elements unmodifiable.
4. Returning internal arrays, collections, or mutable `Date` objects without copying them when necessary.
5. Validating values only in the constructor while allowing setters to assign invalid values.
6. Using generic getters/setters for operations with clear business meaning, instead of names such as `reserve`, `cancel`, or `activate`.

## 8. Check your understanding

**Question 1.** In what sense is a `private final String id` field with a getter but no setter read-only?

The `id` field cannot be reassigned after initialization; external code can only view its value through the getter. `String` is also immutable, so there is no risk of modifying the string's internal state.

**Question 2.** Is a `private int stock` field with a getter and `reserve(int)`, but no setter, "read-only"?

It is read-only **through the API exposed to external callers**; the actual state remains mutable and is updated through `reserve`. This is often preferred when operations must follow business rules.

**Question 3.** Why can a getter returning a `List` undermine read-only behavior even when the field is `final`?

Because `final` prevents **reassigning the reference**, not **modifying the object's contents**. If the getter exposes a mutable list, callers can change it directly. Use an immutable collection, a defensive copy, or a controlled access API.

**Question 4.** When should you choose a fully immutable object?

When data represents a value or snapshot that should stay stable (for example, summary information transferred between components), individual fields rarely need updating, and a new object can be created when values change. For objects with lifecycles and business state transitions, controlled mutability may be more appropriate.

**Remember:** Read/write permissions should follow an object's rules. `final` prevents reassignment; `private` and getters/setters help control the API; defensive copies protect referenced data; immutable objects keep state unchanged. Combining these tools appropriately creates a class that is easy to use and hard to update incorrectly.
