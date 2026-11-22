# Renaming to Clarify Intent (Rename for Intent) in Java OOP

## How Can a Name Make Code Hard to Understand?

Consider a call in a sales application:

~~~java
long total = Calc.f(items, true);
~~~

The reader cannot tell what `f` does, which condition `true` enables, or which amounts `total` includes. To modify the code, they must inspect the implementation, trace variables, and infer the business rules.

Renaming to clarify intent is a **refactoring**: changing a class, method, field, variable, or constant name to express its actual purpose while **preserving the program's observable behavior**.

The same idea with clearer names:

~~~java
long payableAmountVnd =
        orderPriceCalculator.calculatePayableAmountVnd(
                orderLines, includeDeliveryFee);
~~~

The names now answer three questions: the value is **the payable amount**, the unit is **VND**, and the boolean controls **whether a delivery fee is included**.

> A good name reveals intent rather than just a data type. `orderLines` is more useful than `list`, `remainingStock` more useful than `number`, and `isPaymentApproved` more useful than `flag`.

## Names Worth Improving

| OOP element | Unclear name | Intention-revealing name | Why it helps |
|---|---|---|---|
| Class | `DataManager` | `OrderRepository` | Identifies responsibility for storing/retrieving orders |
| Method | `process()` | `confirmOrder()` | Names the business operation |
| Calculation method | `getTotal()` | `calculatePayableAmountVnd()` | Clarifies the calculation and its result |
| Field | `n` | `quantity` | Explains what the number represents |
| Collection | `data` | `unpaidInvoices` | Identifies the items and selection criterion |
| Boolean | `flag` | `includeDeliveryFee` | Explains what `true` means |
| Boolean state | `status` | `isOrderCancelled` | Reads naturally as a true/false condition |
| Constant | `LIMIT` | `MAX_LOGIN_ATTEMPTS` | Identifies the business limit |
| Unit | `timeout` | `connectionTimeoutMillis` | Avoids confusing milliseconds with seconds |
| Time point | `time` | `paymentExpiresAt` | Distinguishes a timestamp from a duration |

These examples are conditional: **the correct name must follow actual behavior**. Do not rename `DataManager` to `OrderRepository` if it manages many data types. Nor should `getTotal()` become `calculatePayableAmountVnd()` if it returns a product count rather than money.

## Runnable Refactoring Example: Before and After Renaming

The following program calculates line-item totals with an optional fixed delivery fee of 30.000 VND. The `Before` and `After` implementations coexist **only to demonstrate verification in this lesson**; in real code, keep one implementation after refactoring and remove old names when no API-compatibility requirement remains.

Save the following code as **RenameForIntentDemo.java** (Java 11 or later):

~~~java
import java.util.List;

public final class RenameForIntentDemo {
    private static final long DELIVERY_FEE_VND = 30_000L;

    static final class OrderLine {
        private final long unitPriceVnd;
        private final int quantity;

        OrderLine(long unitPriceVnd, int quantity) {
            if (unitPriceVnd < 0 || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
            this.unitPriceVnd = unitPriceVnd;
            this.quantity = quantity;
        }

        long calculateLineAmountVnd() {
            return Math.multiplyExact(unitPriceVnd, (long) quantity);
        }
    }

    // BEFORE: phải đọc phần thân mới đoán được tên và biến có ý nghĩa gì.
    static final class Before {
        static long f(List<OrderLine> x, boolean y) {
            long z = 0L;
            for (OrderLine i : x) {
                z = Math.addExact(z, i.calculateLineAmountVnd());
            }
            if (y) {
                z = Math.addExact(z, DELIVERY_FEE_VND);
            }
            return z;
        }
    }

    // AFTER: chỉ đổi các định danh; điều kiện, phép tính và thứ tự giữ nguyên.
    static final class After {
        static long calculatePayableAmountVnd(
                List<OrderLine> orderLines,
                boolean includeDeliveryFee) {

            long payableAmountVnd = 0L;
            for (OrderLine orderLine : orderLines) {
                payableAmountVnd = Math.addExact(
                        payableAmountVnd,
                        orderLine.calculateLineAmountVnd());
            }
            if (includeDeliveryFee) {
                payableAmountVnd = Math.addExact(
                        payableAmountVnd, DELIVERY_FEE_VND);
            }
            return payableAmountVnd;
        }
    }

    private static void assertEquals(long expected, long actual) {
        if (expected != actual) {
            throw new AssertionError(
                    "Expected " + expected + ", actual " + actual);
        }
    }

    public static void main(String[] args) {
        List<OrderLine> orderLines = List.of(
                new OrderLine(20_000L, 2),
                new OrderLine(55_000L, 1)
        );
        // Tiền hàng: 20.000 * 2 + 55.000 = 95.000 VND.

        long oldWithoutDelivery = Before.f(orderLines, false);
        long newWithoutDelivery =
                After.calculatePayableAmountVnd(orderLines, false);

        long oldWithDelivery = Before.f(orderLines, true);
        long newWithDelivery =
                After.calculatePayableAmountVnd(orderLines, true);

        assertEquals(95_000L, oldWithoutDelivery);
        assertEquals(oldWithoutDelivery, newWithoutDelivery);

        assertEquals(125_000L, oldWithDelivery);
        assertEquals(oldWithDelivery, newWithDelivery);

        // Kiểm tra một trường hợp biên: không có dòng hàng.
        assertEquals(Before.f(List.of(), false),
                After.calculatePayableAmountVnd(List.of(), false));

        System.out.println("Rename preserves behavior: PASS");
    }
}
~~~

Run:

~~~bash
javac RenameForIntentDemo.java
java RenameForIntentDemo
~~~

Output:

~~~text
Rename preserves behavior: PASS
~~~

The main changes within the method:

| Before | After | Purpose |
|---|---|---|
| `f` | `calculatePayableAmountVnd` | Calculates the amount due |
| `x` | `orderLines` | Collection of order lines |
| `y` | `includeDeliveryFee` | Whether to add the delivery fee |
| `z` | `payableAmountVnd` | Accumulated amount and result |
| `i` | `orderLine` | Current element in the iteration |

Both `Before` and `After` use the same delivery-fee constant, `Math.addExact`, and `Math.multiplyExact`. Therefore, the change under examination is **naming**, not calculations or overflow handling. The example checks a few specific cases; real projects should run the full suite, including important boundary cases.

## How Can Names Accurately Express Intent?

### 1. Method Names Should Express Actions or Questions

~~~java
// Mơ hồ: tên không thể hiện kết quả.
void handle(Order order);

// Rõ hơn nếu nghiệp vụ thực sự là xác nhận đơn.
void confirmOrder(Order order);

// Boolean method có thể đọc như một câu hỏi.
boolean isEligibleForFreeShipping(Order order);
~~~

A method named `validateOrder` needs a clear contract: does it return a `boolean`, a list of errors, or throw an exception? If it **throws on invalid input**, `requireValidOrder` may communicate that behavior more accurately; if it returns a `boolean`, `isOrderValid` may be clearer. Choose according to the actual contract.

For JavaBeans, JPA, serialization libraries, or getter-based frameworks, prefixes such as `get`, `is`, and `set` may be part of technical conventions. Renaming must respect those contracts and framework rules.

### 2. Data Names Should Convey Business Meaning and Units

~~~java
long delay = 5_000;                 // 5.000 giây hay mili giây?
long retryDelayMillis = 5_000;      // Mili giây.

int count = 3;                      // Đếm cái gì?
int failedLoginAttempts = 3;        // Số lần đăng nhập thất bại.
~~~

In new code, a domain type can reduce ambiguity further, for example `Duration.ofSeconds(5)`. However, **changing from `long` to `Duration` changes the data type**, not just the name; it should be a separate refactoring step with suitable tests.

### 3. Boolean Names Must Avoid Ambiguity

~~~java
boolean active;              // Ai đang hoạt động?
boolean userAccountActive;   // Tài khoản người dùng đang hoạt động.

boolean send;                // Gửi thứ gì, lúc nào?
boolean sendConfirmationEmail;
~~~

Avoid double negatives such as `isNotDisabled` when `isEnabled` expresses the intent directly. However, **reversing a flag's meaning** (changing `disabled` to `enabled` and inverting its value) is not a simple rename because `true` now means something different; all usage logic must be updated and thoroughly tested.

### 4. Balance Concision with Sufficient Context

`customerId` is better than `c`, but `customerIdOfTheCustomerCurrentlyBeingProcessed` is excessively long. In a short loop, `index` or `item` may be enough; in a method handling `orders`, `invoices`, and `receipts`, `currentOrder` is clearer than `item`.

The broader the scope (public classes, public APIs, long-lived fields), the more self-explanatory names should be. A short but contextually clear name is fine in a very local expression.

## A Safe Renaming Process in Java Projects

~~~mermaid
flowchart TD
    A["Hiểu mục đích và hợp đồng hiện tại"] --> B["Chọn tên diễn đạt nghiệp vụ đúng"]
    B --> C["Dùng IDE Rename Symbol để cập nhật tham chiếu"]
    C --> D["Xem diff: chỉ các định danh mong muốn thay đổi?"]
    D --> E["Compile và chạy unit tests"]
    E --> F{"Có API / dữ liệu / cấu hình phụ thuộc tên?"}
    F -- "Có" --> G["Kiểm tra consumer, reflection, serialization, migration"]
    F -- "Không" --> H["Hoàn tất refactor"]
    G --> H
~~~

1. **Read the method/class being renamed:** Understand its meaning, conditions, results, and side effects. Do not guess from its old name.
2. **Choose the new name:** Express the actual action, object, unit, or state and follow the project's domain vocabulary.
3. **Use the IDE's Rename refactoring:** IntelliJ IDEA commonly uses **Shift+F6**, and VS Code with Java tooling often uses **F2**. Symbol-aware reference updates are safer than global string replacement.
4. **Inspect the diff and call sites:** Review constructors, method references, overrides/implementations, tests, annotations, configuration, and documentation. Check multiple modules when the symbol crosses module boundaries.
5. **Compile and test:** Compare behavior before and after. For public APIs and persistence, verify consumers and real data contracts.
6. **Keep changes small:** Separating naming refactors from business-logic edits makes commits easier to review, debug, and revert (commit only when the project's workflow requires it).

IDE-assisted local-variable renaming is usually low risk. Renaming public methods, properties, or externally referenced classes may require a compatibility/migration plan.

## Important Boundary: Source Names May Differ from Runtime Names

| Scenario | What can break | Mitigation |
|---|---|---|
| Rename a method in a public interface | Other projects may fail to compile; binary clients may fail at linkage | Update consumers, version the API, or maintain adapters/deprecated methods as policy requires |
| Rename a field in a JSON payload | The API contract changes and clients expecting the old field fail | Preserve the wire name with annotations (such as `@JsonProperty`) or use versioned migration |
| Rename a JPA entity property | Mapping, property-based queries, or convention-driven schema names may change | Check `@Column`, derived queries, JPQL, migrations, and integration tests |
| Rename `@Bean`, `@Qualifier`, or a component | Name-based dependency injection may fail to resolve the right bean | Check bean configuration and context-startup tests |
| Rename a method/field referenced through reflection | Old string literals are not necessarily updated by Rename Symbol | Find reflection calls and names in config/tests; update and execute them |
| Rename a public file/class/package | Builds, imports, resources/configuration, or callers may break | Use IDE refactoring and inspect tests, build scripts, and external references |

Example of renaming a Java field while preserving a public JSON contract (in a project using Jackson):

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public final class PaymentResponse {
    private long payableAmountVnd;

    @JsonProperty("total")
    public long getPayableAmountVnd() {
        return payableAmountVnd;
    }
}
~~~

Here, the JSON name `"total"` is applied **to the getter** to preserve the serialized field name. The snippet only illustrates output serialization; deserialization also requires an appropriate constructor/setter or creator configuration. This is merely a mapping example: when a real application uses different setters, constructors, records, serialization strategies, or visibility rules, verify actual JSON input/output in tests. This Jackson import belongs in a project with the corresponding dependency and is **not part of the standalone Java file above**.

In Java, renaming an `@Override` method must remain consistent with the interface/superclass contract; when the interface comes from an external library, its signature cannot be changed arbitrarily while preserving correct implementation.

## When Is a Better Name Insufficient?

Sometimes the problem goes beyond naming. For example:

~~~java
void processOrder(Order order);
~~~

If a method checks inventory, charges a payment, updates an order, and sends email, renaming it `processValidatedOrderAndChargeAndSendEmail` still does not create clear responsibilities. Consider **Extract Method**, **Extract Class**, or responsibility-based collaborators with separately named steps. These are different refactorings and should be assessed and tested separately.

Likewise, `calculatePayableAmountVnd(orderLines, true)` still forces a reader at the **call site** to remember what `true` means. Good parameter names improve declarations, but Java lacks named arguments. For more complex cases, consider an explicit method or an enum representing the business choice. Changing a signature or introducing an enum is a separate API change, not merely a rename.

## Self-Check Exercises

**Exercise 1 — Name the intent:** After checking actual behavior, propose meaningful names for the following snippets:

~~~java
boolean a = invoice.getDueDate().isBefore(today) && !invoice.isPaid();
int n = cart.getItems().size();
long t = priceCents * quantity;
~~~

Suggested names: `isInvoiceOverdue` (if the business rule requires both overdue and unpaid), `cartItemCount`, and `lineAmountCents`.

**Exercise 2 — Preserve behavior:** In `RenameForIntentDemo.java`, rename `After.calculatePayableAmountVnd` to `calculateOrderPayableAmountVnd` using Rename Symbol, verify that the call in `main` changes, and rerun the program. The console must still print `PASS`.

**Exercise 3 — Identify risks:** An API returns JSON with the field `"total"`. Propose a way to rename the Java field to `payableAmountVnd` while existing clients still receive `"total"`; write a serialization test if the project uses Jackson.

**Self-assessment:** Explain why changing `flag` to `includeDeliveryFee` is renaming, whereas replacing `boolean includeDeliveryFee` with `ShippingMethod shippingMethod` redesigns the contract. Identify tests proving that totals remain unchanged.

A successful rename lets readers understand **what an object does, what its data means, and what a condition represents** right where the name is used; code retains its expected behavior, and contracts beyond source code have been considered.
