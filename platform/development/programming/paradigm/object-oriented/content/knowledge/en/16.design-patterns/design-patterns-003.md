# Builder and Creating Complex Objects in Java

**Topic:** Design Patterns — Builder.  
**Goal:** Understand why Builder helps when objects have many components and constraints, implement a fluent Builder in Java, ensure that constructed objects are valid, and recognize when a simpler form of object creation is preferable.

## 1. Why Can Object Initialization Become Difficult to Control?

When an object has only two required fields, a direct constructor is usually clear enough:

~~~java
record Point(int x, int y) {}

Point point = new Point(10, 20);
~~~

Now imagine creating an **order** with the following information:

| Element | Required? | Constraint |
| --- | --- | --- |
| Customer ID | Yes | Must not be empty or whitespace only |
| Shipping address | Yes | Must not be empty |
| Item list | At least one item | Each item has an SKU, positive quantity, and nonnegative unit price |
| Shipping method | No | Defaults to **STANDARD**, optionally **EXPRESS** |
| Coupon code | No | Must not be blank if provided |
| Gift wrapping | No | Defaults to **false** |
| Delivery note | No | Defaults to the empty string |

If everything becomes a constructor argument:

~~~java
// Khó nhận ra ý nghĩa của các giá trị ở giữa.
new Order("C01", "12 Nguyễn Huệ", items,
          ShippingMode.EXPRESS, "WELCOME",
          true, "Gọi trước khi giao");
~~~

Clients must remember parameter order, optional-field representations, and valid combinations of values. Parameters that all use **String** are especially easy to swap without a compiler error. Adding many overloaded constructors (*telescoping constructors*) to fix this can make the number of variants grow rapidly. Alternatively, using an empty constructor followed by setters can leave an object temporarily invalid while it is configured:

~~~java
MutableOrder order = new MutableOrder();
order.setCustomerId("C01");
// Nếu bị sử dụng tại đây, order có thể chưa có địa chỉ và mặt hàng.
order.setShippingAddress("12 Nguyễn Huệ");
~~~

**Builder** provides an organized object-construction process: collect configuration choices in a builder, give each operation a clear name, validate before completion, and create the resulting object.

## 2. What Is Builder?

Builder is a *creational pattern*. Its core idea is to **separate construction steps from the final object**. In Java, a common variant is the **fluent Builder**: each configuration method returns the builder itself to allow method chaining.

~~~java
Order order = Order.builder("C01", "12 Nguyễn Huệ")
        .addItem("BOOK-01", 2, new BigDecimal("125000"))
        .addItem("PEN-05", 1, new BigDecimal("35000"))
        .shippingMode(ShippingMode.EXPRESS)
        .couponCode("WELCOME")
        .giftWrap(true)
        .build();
~~~

Read the code as a sequence: create an order for a customer, add items, choose shipping, enter a coupon, request gift wrapping, and complete construction. Method signatures make the meaning of each value clear.

Builder does not require a fluent chain, a nested class, or fixed method names. The classic GoF Builder may include **Builder**, **ConcreteBuilder**, **Director**, and **Product**; a Java fluent Builder may need only **Product** and **Builder**, without a Director. The pattern name helps organize construction; it does not mandate implementing every role for every problem.

~~~mermaid
flowchart LR
    A["Client"] -->|"builder(required fields)"| B["Order.Builder"]
    B -->|"addItem / shippingMode / couponCode"| B
    B -->|"build(): kiểm tra bất biến"| C["Order (bất biến)"]
    C --> D["Client sử dụng Order hoàn chỉnh"]
~~~

### Benefits to Recognize Accurately

- **Readability:** configuration steps are named, reducing mistakes in parameter order.
- **Centralized validation:** the Builder/Product constructor can validate constraints spanning multiple fields before returning the object.
- **Options and defaults:** clients provide only choices that differ from the defaults.
- **Immutable final object:** public setters are unnecessary when values are complete at **build()**.
- **Reusable construction process:** a builder can support additional steps or business-specific variants.

**Not automatic benefits:** Builder does not inherently guarantee immutability, business correctness, thread safety, or the elimination of complexity. Those properties depend on the actual code.

## 3. Java 17+ Example: Creating an Order with Explicit Constraints

Save the following code as **BuilderDemo.java** and run it with JDK 17 or later. The example uses a **record** for immutable line items, **BigDecimal** for precise unit prices, **List.copyOf** to snapshot the item list when creating an order, and a builder entry point that requires the mandatory parameters.

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class BuilderDemo {

    enum ShippingMode {
        STANDARD, EXPRESS
    }

    // Value object: record tự sinh accessor, equals/hashCode và toString.
    // Các thành phần của record này đều là giá trị bất biến.
    public record LineItem(String sku, int quantity, BigDecimal unitPriceVnd) {
        public LineItem {
            sku = requiredText(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng phải lớn hơn 0");
            }
            Objects.requireNonNull(unitPriceVnd, "unitPriceVnd");
            if (unitPriceVnd.signum() < 0) {
                throw new IllegalArgumentException(
                        "Đơn giá không được âm");
            }
        }

        public BigDecimal lineTotalVnd() {
            return unitPriceVnd.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static final class Order {
        private final String customerId;
        private final String shippingAddress;
        private final List<LineItem> items;
        private final ShippingMode shippingMode;
        private final String couponCode;
        private final boolean giftWrap;
        private final String note;

        private Order(Builder builder) {
            // Một lần nữa xác nhận bất biến tại ranh giới tạo đối tượng.
            this.customerId =
                    requiredText(builder.customerId, "customerId");
            this.shippingAddress =
                    requiredText(builder.shippingAddress, "shippingAddress");

            // Bản sao độc lập; không giữ danh sách mutable của Builder.
            this.items = List.copyOf(builder.items);
            if (items.isEmpty()) {
                throw new IllegalStateException(
                        "Đơn hàng cần ít nhất một mặt hàng");
            }

            this.shippingMode =
                    Objects.requireNonNull(builder.shippingMode);
            this.couponCode = builder.couponCode;
            this.giftWrap = builder.giftWrap;
            this.note = builder.note;
        }

        // Bắt buộc có khách hàng và địa chỉ ngay khi khởi tạo builder.
        public static Builder builder(
                String customerId, String shippingAddress) {
            return new Builder(customerId, shippingAddress);
        }

        public String customerId() {
            return customerId;
        }

        public String shippingAddress() {
            return shippingAddress;
        }

        public List<LineItem> items() {
            return items;
        }

        public ShippingMode shippingMode() {
            return shippingMode;
        }

        public String couponCode() {
            return couponCode;
        }

        public boolean giftWrap() {
            return giftWrap;
        }

        public String note() {
            return note;
        }

        public BigDecimal goodsTotalVnd() {
            return items.stream()
                    .map(LineItem::lineTotalVnd)
                    .reduce(BigDecimal.ZERO, BigDecimal::add);
        }

        public static final class Builder {
            private final String customerId;
            private final String shippingAddress;
            private final List<LineItem> items = new ArrayList<>();
            private ShippingMode shippingMode = ShippingMode.STANDARD;
            private String couponCode;
            private boolean giftWrap;
            private String note = "";

            private Builder(String customerId, String shippingAddress) {
                this.customerId = requiredText(customerId, "customerId");
                this.shippingAddress =
                        requiredText(shippingAddress, "shippingAddress");
            }

            public Builder addItem(
                    String sku, int quantity, BigDecimal unitPriceVnd) {
                items.add(new LineItem(sku, quantity, unitPriceVnd));
                return this;
            }

            public Builder shippingMode(ShippingMode mode) {
                this.shippingMode =
                        Objects.requireNonNull(mode, "shippingMode");
                return this;
            }

            public Builder couponCode(String code) {
                this.couponCode = requiredText(code, "couponCode");
                return this;
            }

            public Builder giftWrap(boolean enabled) {
                this.giftWrap = enabled;
                return this;
            }

            public Builder note(String value) {
                this.note = Objects.requireNonNull(value, "note");
                return this;
            }

            public Order build() {
                return new Order(this);
            }
        }
    }

    private static String requiredText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " không được rỗng");
        }
        return value.trim();
    }

    public static void main(String[] args) {
        Order order = Order.builder("C01", "12 Nguyễn Huệ")
                .addItem("BOOK-01", 2, new BigDecimal("125000"))
                .addItem("PEN-05", 1, new BigDecimal("35000"))
                .shippingMode(ShippingMode.EXPRESS)
                .couponCode("WELCOME")
                .giftWrap(true)
                .note("Gọi trước khi giao")
                .build();

        System.out.println(
                order.customerId() + " | " +
                order.shippingMode() + " | " +
                order.goodsTotalVnd().toPlainString() + " VND");
        System.out.println("Số dòng mặt hàng: " + order.items().size());
    }
}
~~~

Run:

~~~bash
javac BuilderDemo.java
java BuilderDemo
~~~

Output:

~~~text
C01 | EXPRESS | 285000 VND
Số dòng mặt hàng: 2
~~~

**Explanation of the design choices:**

1. **The Order constructor is private.** Clients cannot create an **Order** while bypassing the validation boundary.
2. **Order.builder(customerId, shippingAddress)** requires two minimum pieces of information. The compiler enforces that arguments are supplied; null/blank validation occurs at runtime.
3. **addItem(...)** creates a valid **LineItem** when it is added to the builder; **build()** validates the whole-order constraint: at least one line item is required.
4. **shippingMode** has a default. **couponCode == null** means no coupon, **giftWrap == false** means no gift wrapping, and **note == ""** means no note. These meanings must be explicit in the API.
5. **Order** has only **private final** fields and accessors. There are no setters to change its state after construction.
6. **List.copyOf** produces a list that cannot be modified through its accessor and separates the order's list from the builder's internal list. Because **LineItem** uses **String**, **int**, and **BigDecimal** (all immutable in this example), individual elements cannot be altered through mutable references either.
7. **goodsTotalVnd()** is the merchandise total before shipping charges and discounts. The Builder does not automatically apply coupons; discount rules belong in separate business processing.

The code uses **BigDecimal** instead of **double** for money to avoid binary floating-point errors. In real projects, standardize rounding rules, currencies, and taxes, and do not treat the presence of a coupon string as proof that a discount has been applied.

## 4. Two Validation Points: Configuration and Completion

Do not mechanically postpone every check until **build()**, and do not assume that individually valid setters guarantee a valid final combination.

| When | What to validate | Example |
| --- | --- | --- |
| When initializing the builder | Independent required values | Nonblank customer ID/address |
| When invoking configuration methods | Validity of individual choices | Quantity > 0, nonnegative unit price, non-null shipping mode |
| When invoking **build()** | Invariants involving multiple components | At least one item; delivery date after order date if business rules require it |
| In the business service | Rules requiring dynamic data or infrastructure | Inventory, coupon validity, ordering permissions, carrier rates |

For example, an optional rule may require an **EXPRESS** order to include a contact phone number. You can add **contactPhone** to the builder and validate the combination at **build()**:

~~~java
// Minh họa đoạn điều kiện đặt trong constructor của Product:
if (builder.shippingMode == ShippingMode.EXPRESS
        && (builder.contactPhone == null
            || builder.contactPhone.isBlank())) {
    throw new IllegalStateException(
            "Giao EXPRESS yêu cầu số điện thoại liên hệ");
}
~~~

This is an **illustrative extension**, not a snippet that can be pasted unchanged into **BuilderDemo.java**, because the complete example above does not yet declare **contactPhone**. To implement it, add a field and method to the builder, an immutable field to Order, an accessor, and tests for the constraint.

Important: inventory checks or external shipping-rate calculations should not automatically make network calls inside a value object's **build()** if that makes construction unpredictable, difficult to test, or side-effectful. Let a service coordinate appropriate dependencies before creating or confirming the order.

## 5. Understanding Immutability and Builder Reuse

**Builders are usually mutable**, while **Products may be immutable**. These properties do not conflict.

A builder can be reused to create multiple object snapshots:

~~~java
var builder = BuilderDemo.Order
        .builder("C02", "45 Lê Lợi")
        .addItem("BOOK-01", 1, new java.math.BigDecimal("100000"));

var first = builder.build();           // 1 dòng
builder.addItem("PEN-05", 2,
        new java.math.BigDecimal("10000"));
var second = builder.build();          // 2 dòng

System.out.println(first.items().size());   // 1
System.out.println(second.items().size());  // 2
~~~

This works because every **build()** copies the list. If the Product constructor retains **builder.items** directly, modifying the builder after building will also change the previously created product, violating the expectation of immutability.

However, **List.copyOf only makes a shallow copy of the elements**. If the list contains mutable objects such as **MutableAddress**, a nested **ArrayList**, or objects with setters, anyone holding references to those elements may still change their contents. For deeper immutability, use immutable value objects, defensively copy each element, or avoid exposing mutable references.

**A mutable Builder is not inherently thread-safe.** Do not share a builder under modification across threads without suitable synchronization/concurrency controls. The simplest option is to give each thread/task its own builder.

Common mistakes:

- Public setters on **Order** undermine the idea of “complete at build time”.
- **build()** returns the builder itself or a product that retains mutable references owned by the builder.
- The Builder permits creating a product with missing required fields without reporting an error.
- Defaults silently change over time, unexpectedly altering existing behavior.
- Validation occurs in one setter, but combinations of configuration steps can bypass invariants.
- Exceptions are used for valid but frequently failing business outcomes without a clear contract; larger applications may use a specialized validation-result type.

## 6. Testing Builder with JUnit 5

Put the following tests in **BuilderDemoTest.java** (with JUnit Jupiter on the project's classpath). The goal is to verify the correctness of the **constructed** object, defaults, invariants, and input errors.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class BuilderDemoTest {

    @Test
    void taoDonHangVoiMacDinh() {
        var order = BuilderDemo.Order.builder("C01", "12 Nguyễn Huệ")
                .addItem("BOOK-01", 2, new BigDecimal("125000"))
                .build();

        assertEquals(BuilderDemo.ShippingMode.STANDARD,
                order.shippingMode());
        assertFalse(order.giftWrap());
        assertNull(order.couponCode());
        assertEquals("", order.note());
        assertEquals(new BigDecimal("250000"), order.goodsTotalVnd());
    }

    @Test
    void khongChoTaoDonRong() {
        var builder = BuilderDemo.Order.builder("C01", "12 Nguyễn Huệ");

        assertThrows(IllegalStateException.class, builder::build);
    }

    @Test
    void chanSoLuongKhongHopLe() {
        var builder = BuilderDemo.Order.builder("C01", "12 Nguyễn Huệ");

        assertThrows(IllegalArgumentException.class, () ->
                builder.addItem("BOOK-01", 0,
                        new BigDecimal("125000")));
    }

    @Test
    void danhSachCuaOrderKhongTheSuaVaKhongBiAnhHuongKhiTaiSuDungBuilder() {
        var builder = BuilderDemo.Order.builder("C01", "12 Nguyễn Huệ")
                .addItem("BOOK-01", 1, new BigDecimal("100000"));
        var first = builder.build();

        assertThrows(UnsupportedOperationException.class, () ->
                first.items().clear());

        builder.addItem("PEN-05", 1, new BigDecimal("10000"));
        var second = builder.build();

        assertEquals(1, first.items().size());
        assertEquals(2, second.items().size());
    }

    @Test
    void batBuocCoMaKhachHangHopLe() {
        assertThrows(IllegalArgumentException.class, () ->
                BuilderDemo.Order.builder("   ", "12 Nguyễn Huệ"));
    }
}
~~~

A more complete test suite should cover boundaries: extremely large quantities, negative unit prices, nulls, blank strings, cross-field rules, defaults, and repeated builder configuration. Match the testing effort to business risk; there is no need to test that every setter returns the builder if end-to-end results already cover the behavior.

## 7. Comparing Object-Creation Approaches in Java

| Approach | Appropriate when | Trade-off |
| --- | --- | --- |
| Ordinary constructor | Few fields, all clear and required | Can become hard to read with many same-type parameters |
| **record** | Small value object with clear components and value-based equality | Does not inherently solve many options or multistep construction |
| Static factory | Clear business naming, implementation selection, or controlled instantiation is needed | Numerous options may cause factory overloads to proliferate |
| Setters on a mutable object | The object truly needs to change continuously after creation | May expose invalid intermediate states |
| **Builder** | Many optional fields, multistep creation, and a need for valid/immutable products | Extra code, intermediate state, and API learning cost |
| Factory + Builder | Select an object family/implementation, then configure many parameters | Consider overall complexity; the patterns serve different purposes |

**A Factory mainly answers “what type of object to create, and through which mechanism?”; Builder answers “what information and steps are needed to create that object?”.** Combine them when the problem requires both, not merely to increase the pattern count.

In particular, Java **record** suits small data values such as **LineItem**. Builder offers more obvious value for an **Order** aggregate with many options, a list, and cross-field constraints.

## 8. Fluent Builder, Staged Builder, and Director

### Ordinary Fluent Builder

The **Order.Builder** example above lets callers invoke optional steps in flexible order. Some mandatory inputs are enforced through **builder(customerId, shippingAddress)**, while the “at least one item” requirement is checked at runtime by **build()**.

### Staged Builder / Step Builder

If a complex workflow must enforce the order of calls at *compile time*, split the API into stage-specific interfaces:

~~~java
interface CustomerStep {
    AddressStep customer(String customerId);
}

interface AddressStep {
    BuildStep address(String shippingAddress);
}

interface BuildStep {
    BuildStep giftWrap(boolean enabled);
    Order build();
}
~~~

Clients only see methods valid for the current stage. This can reduce missing mandatory fields, but it introduces more interfaces, generics, or complex types. It is rarely worthwhile for ordinary configuration objects. The snippet above only illustrates the **stage interfaces**; a matching implementation and a real **Order** type are required before use.

### Director in GoF Builder

A **Director** knows a standard construction sequence. It invokes a builder to create variants such as “gift order,” “detailed report,” or “default test-environment configuration”:

~~~java
static BuilderDemo.Order createGiftOrder(
        String customerId, String address) {
    return BuilderDemo.Order.builder(customerId, address)
            .addItem("GIFT-01", 1, new java.math.BigDecimal("200000"))
            .giftWrap(true)
            .build();
}
~~~

Here a static factory is enough to express the “recipe” without a separate **Director** class. An independent Director may help when multiple builder types produce different products through the same construction process.

## 9. Builder with Lombok, Spring, or Other Libraries

In codebases using Lombok, **@Builder** can generate a builder API and reduce boilerplate:

~~~java
// Ví dụ ý tưởng, cần dependency Lombok và cấu hình annotation processing:
@lombok.Builder
record ExportOptions(
        String format,
        boolean includeImages,
        int maxRows
) {}
~~~

This is not a direct substitute for the validation in the **Order** example. The annotation generates a builder and construction mechanism, but business invariants, defensive copies of mutable data, default choices, and cross-field constraints still need to be designed and verified. Reviews should also consider interactions among **@Builder**, records/constructors, **@Builder.Default** (where supported), and generated code.

With Spring Boot, a configuration class can be bound from YAML/properties through constructors/records with framework-provided validation. Do not add Builder to every **@ConfigurationProperties** when constructor binding or a record is clear enough; Builder better suits cases where client code genuinely constructs objects step by step or sets many optional code-defined choices.

**Performance note:** a builder introduces another short-lived object and method calls. Usually prioritize correctness, clarity, and maintainability. Optimize allocations only when profiling demonstrates a real bottleneck.

## 10. Designing Builder APIs for Usability and Maintenance

Small decisions can have substantial effects:

| Decision | Suggestion | Rationale |
| --- | --- | --- |
| Required fields | Include them in the static **builder(required...)** factory or use staged steps when needed | Reduces omissions and clarifies the entry point |
| Default values | Define them transparently and consistently in the builder | Clients need not resupply common values |
| Lists/maps | Accumulate in the builder and make defensive copies at build time | Prevents exposing mutable state through the product |
| Typed values | Prefer **enum** and value objects over uncontrolled strings | Reduces invalid states |
| Similar field names | Use method names from the business domain | Avoids ambiguity such as **setFlag(true)** |
| Exceptions | Report the affected field or violated invariant | Helps callers correct input |
| Multiple builds | Specify whether they are supported; if so, return independent objects | Prevents accidental mutation |
| Concurrency | Scope builders to one task/thread unless synchronization is explicitly designed | Limits data races |
| Copying/variants | Consider **toBuilder()** only when necessary | Avoids copying through setters on an immutable product |

A common implementation places the **Builder inside the Product class**, but this is not a limitation of the pattern. An external Builder works when the Product source is unavailable, several construction strategies are needed, or the Product API should remain compact.

## 11. When Should You Avoid Builder?

Builder has implementation and maintenance costs. Keep object creation simple when:

- An object has 2–3 clear parameters, with few options or intermediate states.
- Data is mainly a small immutable record; a **record** or constructor suffices.
- The object is an ORM-managed entity with lifecycle/proxy requirements unlike those of a value object. Examine the framework's requirements instead of applying Builder mechanically.
- Every change is a valid state transition throughout the object's lifetime; controlled mutation APIs, commands, or aggregate methods may be more appropriate.
- A builder is introduced only because “the project must use Design Patterns,” while readers now need another layer to understand an assignment.

A practical principle: **choose Builder when it clarifies a complex construction process, protects invariants, or makes the calling API substantially clearer than a constructor/factory**. Do not measure design quality by the number of classes or patterns.

## 12. Practical Exercise

Design **ReportConfig** for exporting revenue reports:

- **reportName**, **fromDate**, and **toDate** are required.
- **format** defaults to **CSV**, with **PDF** as an option.
- **includeCharts** defaults to false; PDF reports may contain charts, but CSV reports may not.
- The list of departments to filter by may be empty (meaning all departments) but must not contain null/blank department codes.
- The start date must not be after the end date.

Implement **ReportConfig.builder(reportName, fromDate, toDate)**, and add **format(...)**, **includeCharts(...)**, **addDepartment(...)**, and **build()**. Use **LocalDate**, **enum Format**, **List.copyOf**, and **final** fields where appropriate. At a minimum, test that CSV is the default, reversed date ranges are rejected, CSV with charts is rejected, the department list on the Product cannot be modified, and reusing a builder does not alter previously created ReportConfig instances.

Self-assess with three questions: (1) can readers understand each option at the call site; (2) is it possible to create a ReportConfig that violates an invariant; (3) when adding a new option, must every constructor call site in the system change?

**Conclusion:** Builder is most valuable when it turns object creation with many parameters into meaningful steps, centralizes validation, and produces a complete product. Ensure the boundary between a mutable Builder and an immutable Product is implemented correctly, and accept the pattern's complexity only when maintenance benefits are clear.
