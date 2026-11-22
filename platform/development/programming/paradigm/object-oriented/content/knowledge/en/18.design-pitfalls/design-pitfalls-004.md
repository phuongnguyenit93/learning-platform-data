# Inheritance solely to reuse a few methods: an OOP design pitfall

> **Lesson:** Do not create an `extends` relationship between two classes merely because a subclass wants to reuse a few superclass methods. Evaluate the type relationship, behavioral contract, and APIs inherited unintentionally; when an object merely **uses** a capability, composition/delegation usually expresses that relationship better.

## 1. Why is this choice so tempting?

When learning Java, we see that `extends` lets a class inherit accessible `public` or `protected` methods from its superclass:

~~~java
class TextFormatter {
    public String format(String value) {
        return value.trim();
    }
}

class RegistrationService extends TextFormatter {
    public String register(String username) {
        return format(username);
    }
}
~~~

This code compiles, but `RegistrationService` becomes a subtype of `TextFormatter` even though a registration service merely **needs to use** formatting. External code can treat the registration service as a formatter:

~~~java
TextFormatter formatter = new RegistrationService();
System.out.println(formatter.format("  An  "));
~~~

The statement is type-correct, but the domain relationship is strange. If `TextFormatter` changes to cache data, support `close()`, or use a different algorithm, `RegistrationService` may be affected just because it reused a convenience method.

A small initial saving in code creates a **long-term dependency**.

This is **implementation inheritance for convenience**: using inheritance as a shortcut for code reuse even though the child object does not actually represent a case of the parent abstraction.

## 2. Inheritance means more than "can call a method"

In OOP, `B extends A` represents a type relationship. If Java allows a `B` to be treated as an `A`, code expecting an `A` can rely on the guarantees published by `A`.

For example, `EmailNotificationSender` may genuinely fulfill the entire `NotificationSender` contract, so callers need only know the shared contract. But if `InventoryService extends HashMap<String, Integer>` merely to call `put()` and `get()`, we are claiming an inventory service can be used as **any ordinary HashMap**.

Ask these design questions before using `extends`:

- **Is there a real "is-a" relationship?** Is every `B` truly an `A` under the domain and its defined contract?
- **Can callers substitute it?** Can any caller expecting `A` use `B` without violating published expectations?
- **Is the inherited API appropriate?** Does `A` expose methods that `B` should not allow?
- **Are we reusing an implementation instead of an abstraction?** If we need only a small capability, would owning a collaborator be clearer?
- **How far will changes propagate?** Could superclass changes to structure, constructors, or methods unexpectedly affect subclasses?

The **Liskov Substitution Principle (LSP)** is closely related: a subtype must preserve the behavioral guarantees clients can expect from the supertype. Compiling successfully does not prove LSP compliance.

Importantly, implementation inheritance is **not inherently wrong**. A base abstraction designed for extension, with a stable contract and genuine subtypes, can share code effectively. The problem is choosing `extends` **solely because a few methods are available**, without considering the full contract.

## 3. A dangerous case: Inventory inherits from HashMap

Suppose we manage inventory quantities while preserving these invariants:

1. SKUs must be nonblank.
2. The quantity of each SKU must be nonnegative.
3. Stock can increase only through `restock` and decrease only through `reserve` after validation.
4. When `reserve` is rejected, inventory remains unchanged.

A flawed solution inherits a mutable collection just to get its access methods:

~~~java
import java.util.HashMap;

class UnsafeInventory extends HashMap<String, Integer> {
    public void restock(String sku, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity phải dương");
        }
        merge(sku, quantity, Integer::sum);
    }
}
~~~

This call can break an invariant without changing `restock()`:

~~~java
UnsafeInventory inventory = new UnsafeInventory();
inventory.restock("BOOK", 5);

// Các API được kế thừa công khai từ HashMap:
inventory.put("BOOK", -100);
inventory.put(null, null);
inventory.clear();

System.out.println(inventory.get("BOOK")); // null
~~~

`UnsafeInventory` inherits not only `get` and `put` but also mutation capabilities including `remove`, `replace`, `compute`, `merge`, `putAll`, and `clear`, along with mutable collection views. API clients can bypass validation and business rules.

Failure diagram:

~~~mermaid
flowchart TD
    Client["Client"] -->|restock hợp lệ| Inventory["UnsafeInventory extends HashMap"]
    Client -->|put / clear / compute| MapMethods["API mutable của HashMap"]
    MapMethods --> Inventory
    Inventory --> Broken["Bất biến tồn kho có thể bị phá"]
~~~

The problem is the **boundary controlling state mutation**. Even overriding `put()` to validate would require examining every other mutation path, including inherited behavior and APIs added in the future. That is a steep cost for reusing a few collection methods.

## 4. Fixing it with composition: Inventory owns a Map

An inventory object **has a storage structure**; it does not need to **be a HashMap**. Keep the Map in a `private` field and expose meaningful domain operations.

The following **InheritanceReuseDemo.java** file runs independently on Java 17 or later:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class InheritanceReuseDemo {

    // Inventory không extends HashMap.
    public static final class Inventory {
        private final Map<String, Integer> quantities = new HashMap<>();

        public void restock(String sku, int added) {
            sku = validSku(sku);
            if (added <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng bổ sung phải dương");
            }

            // Từ chối overflow thay vì cho phép số âm do tràn int.
            quantities.merge(sku, added, Math::addExact);
        }

        public boolean reserve(String sku, int requested) {
            sku = validSku(sku);
            if (requested <= 0) {
                throw new IllegalArgumentException(
                        "Số lượng đặt giữ phải dương");
            }

            int available = quantities.getOrDefault(sku, 0);
            if (requested > available) {
                return false; // Không thay đổi state.
            }

            quantities.put(sku, available - requested);
            return true;
        }

        public int available(String sku) {
            return quantities.getOrDefault(validSku(sku), 0);
        }

        // Cho phép đọc một snapshot, không trả Map mutable nội bộ.
        public Map<String, Integer> snapshot() {
            return Map.copyOf(quantities);
        }

        private static String validSku(String sku) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException(
                        "SKU không được rỗng");
            }
            return sku.trim();
        }
    }

    public static final class CheckoutService {
        private final Inventory inventory;

        public CheckoutService(Inventory inventory) {
            this.inventory =
                    Objects.requireNonNull(inventory, "inventory");
        }

        public String placeOrder(String sku, int quantity) {
            if (inventory.reserve(sku, quantity)) {
                return "RESERVED " + sku + " x" + quantity;
            }
            return "REJECTED: insufficient stock";
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory();
        inventory.restock("BOOK", 5);

        CheckoutService checkout = new CheckoutService(inventory);
        System.out.println(checkout.placeOrder("BOOK", 3));
        System.out.println(inventory.available("BOOK"));
        System.out.println(checkout.placeOrder("BOOK", 3));
        System.out.println(inventory.available("BOOK"));

        // Không thể gọi:
        // inventory.put("BOOK", -100);
        // inventory.clear();
    }
}
~~~

Compile and run:

~~~bash
javac InheritanceReuseDemo.java
java InheritanceReuseDemo
~~~

Output:

~~~text
RESERVED BOOK x3
2
REJECTED: insufficient stock
2
~~~

**Protective mechanisms:**

- `Inventory` holds its `Map` as `private final`; clients cannot call `put()`, `clear()`, or `compute()` on an Inventory object.
- Public methods express domain intent: `restock`, `reserve`, and `available`.
- `reserve` validates before subtracting quantities. On insufficient stock, it returns `false` without updating state.
- `Math.addExact` detects integer overflow while adding stock and prevents unintended negative results.
- `snapshot()` returns a Map that cannot be mutated through its returned reference. Because the example's keys and values are `String` and `Integer`, no mutable elements remain inside.
- `CheckoutService` **uses** `Inventory` through a constructor-injected dependency; it does not become a subtype of Inventory or Map.

The example runs in **one thread** to illustrate boundaries and invariants. `HashMap` and the check/update operations shown are not thread-safe under concurrent writes. Real database-backed data needs transactions, locking, or conditional updates to prevent races. Composition fixes the type relationship and API control, not synchronization automatically.

### Design diagram after the fix

~~~mermaid
classDiagram
    class CheckoutService {
        -inventory: Inventory
        +placeOrder(sku, quantity) String
    }
    class Inventory {
        -quantities: Map~String, Integer~
        +restock(sku, added) void
        +reserve(sku, requested) boolean
        +available(sku) int
        +snapshot() Map
    }
    class Map {
        <<interface>>
        +get(key)
        +put(key, value)
        +clear()
    }
    CheckoutService --> Inventory : sử dụng
    Inventory *-- Map : sở hữu nội bộ
~~~

In the diagram's pseudocode, CheckoutService references Inventory, and Inventory internally owns a Map. **The Map interface does not become Inventory's public domain API**.

## 5. Hidden costs of inheritance used only for code reuse

| Risk | Concrete consequence | Warning sign |
| --- | --- | --- |
| **Inflated API** | A subclass exposes methods it does not actually want to provide | Domain class inherits `clear()` and `putAll()` from a collection |
| **Broken invariants** | Callers change state through unvalidated paths | `put("BOOK", -1)` bypasses `restock()` |
| **Incorrect is-a relationship / LSP** | A service is treated like a general-purpose utility or container | `SomeService extends Formatter` solely for `format()` |
| **Tight coupling to the superclass** | Changes to names, return types, constructors, or `protected` details can break subclasses | A small base-class change propagates widely |
| **Fragile base class** | Adding a method or changing internal dispatch can alter subclass behavior | Overrides depend on implementation call order |
| **Hard-to-replace implementation** | Switching `HashMap` to a cache/database forces a change in the type relationship | Business code is tied to a concrete collection |
| **Hierarchy explosion** | Combining capabilities creates many subclass variants | `CachedLoggedValidatedService`… |
| **Difficult isolated tests** | Subtype tests must set up irrelevant parent state/configuration | Subclass needs two functions but depends on parent resources |
| **Misunderstood access** | `protected` is misused as an API for all subclasses | Subclasses can arbitrarily modify internal fields |

These are **risks**, not inevitable consequences of every inheritance relationship. But if the only benefit is "avoiding 5 lines of delegation," it rarely justifies the extra commitments.

### A subtler bug: the base class calls an overridable method

For example:

~~~java
class BaseProcessor {
    public BaseProcessor() {
        initialize(); // Gọi phương thức có thể override.
    }

    protected void initialize() {
        // Mặc định.
    }
}

class CsvProcessor extends BaseProcessor {
    private final String delimiter = ";";

    @Override
    protected void initialize() {
        // Có thể chạy khi field delimiter còn null.
        System.out.println(delimiter.length());
    }
}
~~~

When constructing `new CsvProcessor()`, the base-class constructor runs **before the subclass's field initializers finish**. A call to `initialize()` uses virtual dispatch and may invoke the subclass override; at that moment `delimiter` is still `null`, causing a `NullPointerException`.

This is why overridable methods should not be called from superclass constructors. When using inheritance, understand the object's lifecycle and the subclass contract; `final` methods, factories, or explicit initialization steps are often safer than invoking hooks prematurely.

## 6. How do composition and delegation differ?

- **Composition:** an object manages or uses component objects to fulfill its responsibility. Here, `Inventory` owns the data structure.
- **Delegation:** an object passes part of its work to a collaborator. `CheckoutService` calls `inventory.reserve(...)` rather than modifying stock itself.

The two concepts often work together, but they are not synonyms. An object may contain a dependency without forwarding every call unchanged; it can coordinate several collaborators and enforce business conditions.

A small example: a service needs to normalize identifiers:

~~~java
final class SkuNormalizer {
    String normalize(String sku) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU rỗng");
        }
        return sku.trim().toUpperCase(java.util.Locale.ROOT);
    }
}

final class ImportService {
    private final SkuNormalizer normalizer;

    ImportService(SkuNormalizer normalizer) {
        this.normalizer = java.util.Objects.requireNonNull(normalizer);
    }

    String importSku(String rawSku) {
        String sku = normalizer.normalize(rawSku);
        // Tiếp tục nghiệp vụ import...
        return sku;
    }
}
~~~

`ImportService` **needs** normalized identifiers; it does not need to `extends SkuNormalizer`. With composition, `SkuNormalizer` can be reused in multiple locations without forcing clients to become subtypes of the normalizer.

Still, do not create a helper class for every trivial line of code. For a short algorithm belonging to one class, a `private static method` or private method is sufficient. Extract collaborators for shared responsibility, independent algorithms, testing/replacement needs, or clear boundaries.

## 7. When is inheritance still a good choice?

Inheritance can be appropriate when both **subtype semantics** and **contracts** fit. For example, a framework may provide a base class with well-defined extension points, or the model may have genuine specialized subtypes.

Example of contract-oriented inheritance:

~~~java
abstract class Shape {
    abstract double area();
}

final class Circle extends Shape {
    private final double radius;

    Circle(double radius) {
        if (!Double.isFinite(radius) || radius < 0.0) {
            throw new IllegalArgumentException("Bán kính không hợp lệ");
        }
        this.radius = radius;
    }

    @Override
    double area() {
        return Math.PI * radius * radius;
    }
}

static double areaOf(Shape shape) {
    return shape.area();
}
~~~

Here, `Circle` truly is a `Shape` under the abstraction in use; a caller given a `Shape` can obtain a `Circle`'s area without knowing its concrete shape type. The `areaOf` snippet illustrates a static method that could live in a utility class; putting all snippets into one Java file to experiment requires an enclosing class for that method.

You may choose an **interface** instead of an abstract class when only a capability must be defined:

~~~java
interface Drawable {
    void draw();
}

final class SvgCircle implements Drawable {
    @Override
    public void draw() {
        System.out.println("<circle />");
    }
}
~~~

A class can implement multiple interfaces, but Java supports direct inheritance from only one class. An interface `default method` can sometimes share a default behavior tightly tied to its contract, but **must not become a dumping ground for unrelated utilities**.

### When reusing an implementation through inheritance is valid

Some abstractions are intentionally built for extension:

- A base class has fully documented invariants and lifecycle.
- Subclasses fulfill all public behavior of the base class.
- `protected` extension points and override rules are designed for stability.
- Contract tests for important subtypes guard superclass implementation changes.
- The class hierarchy simplifies the model compared with many additional wrappers.

The JDK's `AbstractList<E>` is a *skeletal implementation* specifically designed for implementing Lists that fulfill its contract. This differs from making `Inventory` inherit `HashMap` just for `get/put`. If a subtype intentionally fulfills every Map/List semantic guarantee, an appropriate collection superclass may be reasonable.

## 8. Comparing reuse options

| Option | When to choose it | Important consideration |
| --- | --- | --- |
| `private method` | Small logic used within a single class | Avoid premature abstraction |
| `static utility method` | Pure algorithm with no state | Keep a clearly named API; avoid "God Utils" |
| **Composition** | An object **has/uses** a collaborator | Define ownership and lifecycle clearly |
| **Delegation** | Transfer a specific task to a collaborator | Do not expose its entire internal API |
| **Interface + implementation** | Multiple implementations fulfill one contract and form a clear dependency boundary | Every implementation must honor the contract |
| **Abstract class** | Genuine subtype family sharing an invariant or extension template | Consider `protected`, constructors, overrides, and LSP |
| **Decorator** | Layer behavior around a contract | Consider wrapper order and side effects |
| **Inheritance from a concrete class** | Only when the superclass is designed for extension and the subtype honors its contract | Risk of coupling to implementation details |

**Composition over inheritance** is a conditional preference, not a ban on inheritance. Choose the form that correctly expresses the domain and reduces long-term coupling.

## 9. Refactoring inheritance into composition

Suppose the codebase currently contains:

~~~java
class PricingService extends SharedStringUtil {
    // Gọi formatCurrency(...) của SharedStringUtil.
}
~~~

Do not build an elaborate interface/factory system if a small helper is all that is needed. A safe refactoring sequence:

1. **Read the entire public superclass API** and every use of the subtype. In particular, find places where `PricingService` is passed as `SharedStringUtil`.
2. **Identify the methods actually needed** and their contracts. Use a helper for small logic; use a collaborator for an independently owned responsibility.
3. **Inject the dependency through a constructor** or retain a suitable private component. Replace `super.someMethod()` with `collaborator.someMethod()` where needed.
4. **Remove `extends`** only after callers stop depending on the old type relationship. For a public API, this can break compatibility and requires a migration plan.
5. **Preserve behavior tests** for business rules and add tests for invariants or previously unsafe access paths.
6. **Remove redundant methods** that merely impersonate a subtype, leaving a small, meaningful API.

Before and after:

~~~mermaid
flowchart LR
    subgraph Before["Trước: is-a giả tạo"]
        A["PricingService"] -->|extends| B["SharedStringUtil"]
    end
    subgraph After["Sau: sử dụng collaborator"]
        C["PricingService"] -->|has-a / delegates| D["CurrencyFormatter"]
    end
~~~

**Do not refactor mechanically** when the base class contains lifecycle hooks, template methods, protected state, or callers strongly depend on polymorphism. Such cases require redesigning boundaries, not just turning `extends` into a field.

## 10. Testing that the design change is beneficial

For the `InheritanceReuseDemo.java` example above, JUnit 5 can verify precisely the invariants that inheriting from HashMap makes harder to enforce:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class InheritanceReuseDemoTest {

    @Test
    void thieuHangKhongLamKhoThayDoi() {
        var inventory = new InheritanceReuseDemo.Inventory();
        inventory.restock("BOOK", 2);

        assertFalse(inventory.reserve("BOOK", 3));
        assertEquals(2, inventory.available("BOOK"));
    }

    @Test
    void giuHangThanhCongKhongDeTonKhoAm() {
        var inventory = new InheritanceReuseDemo.Inventory();
        inventory.restock("BOOK", 5);

        assertTrue(inventory.reserve("BOOK", 3));
        assertEquals(2, inventory.available("BOOK"));
    }

    @Test
    void chanSoLuongAmVaTranhOverflow() {
        var inventory = new InheritanceReuseDemo.Inventory();

        assertThrows(IllegalArgumentException.class,
                () -> inventory.restock("BOOK", -1));

        inventory.restock("BOOK", Integer.MAX_VALUE);
        assertThrows(ArithmeticException.class,
                () -> inventory.restock("BOOK", 1));
        assertEquals(Integer.MAX_VALUE, inventory.available("BOOK"));
    }

    @Test
    void snapshotKhongChoSuaKhoQuaReferenceTraVe() {
        var inventory = new InheritanceReuseDemo.Inventory();
        inventory.restock("BOOK", 2);

        var snapshot = inventory.snapshot();

        assertThrows(UnsupportedOperationException.class,
                () -> snapshot.put("BOOK", -10));
        assertEquals(2, inventory.available("BOOK"));
    }
}
~~~

These tests need JUnit Jupiter on the classpath. `InheritanceReuseDemo.java` itself requires no JUnit and runs directly on JDK 17.

More important than testing each individual function is **the Inventory contract**: after every valid operation, stock quantities are nonnegative; invalid inputs do not corrupt state; clients cannot mutate data while bypassing domain methods. If logic moves to a DB, integration tests must check concurrent contention and transactions.

## 11. Common misconceptions

**"Whenever code looks similar, move it into a superclass."** Two code fragments may temporarily look alike but have different reasons to change. Forcing them into a shared parent can couple changes across modules. Share *truly common knowledge and responsibilities*, not just syntactically similar lines.

**"Using `protected` means encapsulation."** `protected` exposes an extension surface to subclasses, creating a commitment that is hard to change in an inheritance hierarchy. A mutable `protected` field may let subclasses violate invariants the superclass intended to enforce.

**"Composition always requires an interface."** No. With one concrete collaborator and no reason to swap it, a `private final SomeHelper` field is enough. Defining an interface that mirrors a class solely for DI adds boilerplate.

**"Switching inheritance to composition fixes everything."** Dependency structure is only part of the problem. A collaborator with improperly shared mutable state can still break invariants or cause races. Design ownership, data, and transaction handling separately.

**"Every is-a relationship requires class inheritance."** No. Many contracts fit an interface, `sealed interface`, or other data types. Shared capabilities can be expressed with `implements` without requiring shared implementation.

**"Inheritance must never be used."** That is also too extreme. Inheritance is useful for genuine subtype relationships where contracts can be upheld and extension points are intentional.

## 12. Checklist before writing `extends`

Answer these questions during code review:

| Question | If the answer is "no" |
| --- | --- |
| Can you say "every B is an A" in terms of contract, not just names? | Reconsider composition or interfaces |
| Does B need **all** public behavior inherited from A? | Avoid bloated APIs and unintended state mutations |
| Can B be passed to a caller that only knows A while preserving postconditions? | Risk of violating LSP |
| Was A designed or documented for subclass extension? | Beware fragile base classes and lifecycle pitfalls |
| Are there contract tests for major subtypes? | Changes that break polymorphism may go unnoticed |
| If A's implementation changes, does B remain correct? | Coupling to `protected`/override details |
| Is a simpler private helper or collaborator possible? | Prefer the clearer model with fewer commitments |

A strong warning sign is **a subclass that uses only one or two superclass methods while the rest are meaningless to it**. In that situation, first try expressing **"B uses A"** rather than **"B is an A"**.

## 13. Exercise: faulty reuse in a discount system

A developer writes:

~~~java
class DiscountRule extends java.util.ArrayList<Integer> {
    int totalDiscount() {
        int sum = 0;
        for (int item : this) {
            sum += item;
        }
        return sum;
    }
}
~~~

The business requirement is that each discount must be nonnegative, total discounts cannot exceed the order amount, and only authorized application services may add or remove discounts.

Complete these tasks:

1. List at least **three inherited API paths** that can create invalid data without validation.
2. Refactor `DiscountRule` into a class owning a private `List<Integer>` and exposing meaningful domain methods (such as `addDiscount` and `totalDiscount`) with limit checks.
3. Distinguish rules belonging to one discount (nonnegative amount) from rules requiring order data (total discounts cannot exceed the order amount) so validation occurs in the correct place.
4. Write unit tests proving external code cannot modify the list and that overflow is detected.
5. If multiple independent discount algorithms are needed, consider a `DiscountPolicy` interface; explain why that represents a meaningful contract unlike `DiscountRule extends ArrayList`.

**Self-assessment:** Can the refactored class still accidentally be used as a `List<Integer>`? Are there public methods that bypass invariants? Would clients need to change if the underlying storage moved from a list to another structure?

**Remember:** `extends` creates **a type and behavioral commitment**, not just a way to "borrow code." If all you need is a few methods from another object, consider helpers, composition, and delegation. Use inheritance when the subtype can truly substitute for the supertype and the entire inherited contract makes sense.
