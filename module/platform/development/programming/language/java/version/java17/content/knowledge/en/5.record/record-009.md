# Local Records, Nested Records, and the `static` Context in Java 17

In Java 17, a `record` is a form of class declaration suitable for representing a group of values with a clear structure. Alongside a `record` at the top level of a source file (*top-level record*), you can declare a **local record** directly inside a statement block and a **nested record** (*nested/member record*) inside a class or interface.

The key point to understand clearly is: **local records and member records are implicitly `static`**. Therefore, they differ from ordinary inner classes (*inner classes*) in how they access local variables, the state of the enclosing object, and generic type parameters.

This lesson uses stable **Java 17** syntax and explains scope, accessibility, common compilation errors, and how to choose where to place a record declaration when designing source code.

## 1. Recap: What Does a `record` Provide?

Example:

```java
public record Point(int x, int y) {
}
```

This declaration has **two record components**: `x` and `y`. Java automatically provides the basic members:

- Corresponding member fields, which are `private final`.
- A canonical constructor accepting values for the components.
- Two read methods `x()` and `y()`, called **accessors**.
- `equals(Object)`, `hashCode()`, and `toString()` methods based on the state of the components.

Example:

```java
Point point = new Point(3, 7);
System.out.println(point.x());            // 3
System.out.println(point.y());            // 7
System.out.println(point);                // Point[x=3, y=7]
System.out.println(point.equals(new Point(3, 7))); // true
```

`record` was standardized in Java 16 (JEP 395) and can be used directly in Java 17 without enabling preview.

A record is a **class** with language-enforced constraints: it is implicitly `final`, extends `java.lang.Record`, and cannot extend another arbitrary class. A record can implement interfaces, declare additional methods, valid auxiliary constructors, and `static` members.

A record is not synonymous with a "deeply immutable object": if a component holds a mutable object, such as a `List` whose elements can be modified, the record does not automatically copy or lock that list. The designer needs to protect the data using appropriate measures like `List.copyOf(...)` when needed.

## 2. Three Places to Declare a Record in Java 17

| Location | Syntax Example | Name Visibility Scope | Notable Characteristics |
| --- | --- | --- | --- |
| **Top-level record** | `record Point(int x, int y) {}` at the outermost level | Follows package and type access modifiers | Can be used as an independent data type. |
| **Member/nested record** | `class Geometry { record Point(int x, int y) {} }` | Follows scope and access modifiers of enclosing type/member | **Implicitly `static`**, not tied to each `Geometry` instance. |
| **Local record** | `void run() { record Point(int x, int y) {} }` | Within the block where declared, after its declaration | **Implicitly `static`**, does not capture variables from enclosing method or instance. |

Visualizing the structure:

```text
Point.java
└── record Point(...)              ← top-level

Geometry.java
└── class Geometry
    ├── record Point(...)          ← nested/member record
    └── void inspect()
        └── record LocalPoint(...) ← local record
```

The `static` property here refers to **the relationship with the enclosing declaration context**. It **does not mean** the record itself has only a single instance, that all components are static variables, or that instances share values.

Each call to `new Point(1, 2)` still creates a record instance with its own component values.

## 3. Local Records: Declaring a Type Inside a Statement Block

A **local record** is a record declared inside a code block, such as a method body. That record type serves a specific computation and does not need to appear in the enclosing class's API.

### 3.1. Complete Example: Keeping Intermediate Data Locally Scoped

Create **`LocalRecordDemo.java`**:

```java
import java.util.List;

public class LocalRecordDemo {
    static void printMeasurements() {
        // This type has its name and usage scope limited to this method.
        record Measurement(String sensor, int value) {
            Measurement {
                if (sensor == null || sensor.isBlank()) {
                    throw new IllegalArgumentException("sensor must not be blank");
                }
            }

            boolean isAbove(int threshold) {
                return value > threshold;
            }
        }

        List<Measurement> values = List.of(
                new Measurement("A", 17),
                new Measurement("B", 25));

        for (Measurement measurement : values) {
            System.out.println(measurement.sensor() + ": "
                    + measurement.isAbove(20));
        }
    }

    public static void main(String[] args) {
        printMeasurements();
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 LocalRecordDemo.java
java LocalRecordDemo
```

Output:

```text
A: false
B: true
```

In the example:

1. `Measurement` is only needed to represent each measurement inside `printMeasurements()`.
2. The compiler generates accessors `sensor()`, `value()`, along with `equals`, `hashCode`, and `toString` for `Measurement`.
3. The concise constructor `Measurement { ... }` is a **compact canonical constructor**, used to validate data conditions before the record finishes initialization.
4. The method `isAbove(int threshold)` is an **instance behavior of the record itself**, not a static function; it uses the `value` component of the current instance.
5. Outside the block containing the declaration, `Measurement` cannot be referenced by name from other methods as a shared type.

Placing the record near where it is used clarifies that it is an **intermediate data structure**, not part of the system-wide public contract.

### 3.2. Scope of a Local Record Name

Example:

```java
public class ScopeDemo {
    static void first() {
        record Pair(int left, int right) {}

        Pair pair = new Pair(2, 5);
        System.out.println(pair.left() + pair.right());
    }

    static void second() {
        // Pair pair = new Pair(4, 6); // DOES NOT COMPILE:
        // Pair is local to first(), not visible here.
    }
}
```

A local record declaration is in scope within its enclosing block starting from the declaration; it does not appear as a member type visible to all methods of the class.

Therefore, **do not use a local record if multiple methods need the same data type**. In that case, a nested record or top-level record is usually clearer.

### 3.3. In Which Contexts Can a Local Record Be Declared?

A local record can appear in the statement block of:

- An instance method or `static` method.
- A constructor.
- A valid class initializer block.
- A nested block inside a method, such as the body of an `if` branch or loop.

Being inside an **instance method** does not turn a local record into an inner class tied to `this`. The implicit `static` nature of the local record still holds.

## 4. Why Do Local Records Not Capture Local Variables?

This is an important difference between an **ordinary local class** and a **local record**.

An ordinary local class can use outer variables if they are `final` or *effectively final*:

```java
public class CaptureDemo {
    static void run() {
        int threshold = 10; // effectively final

        class Checker {
            boolean passes(int value) {
                return value >= threshold; // Valid for a local class.
            }
        }

        System.out.println(new Checker().passes(12));
    }
}
```

By contrast, **a local record cannot capture variables from the enclosing method or block**:

```java
public class InvalidLocalRecord {
    static void run() {
        int threshold = 10;

        record Score(int value) {
            boolean passes() {
                return value >= threshold; // COMPILE ERROR.
            }
        }
    }
}
```

Even when `threshold` is `final` or effectively final, the local record still cannot use it that way. Reason: local records are **implicitly `static`**, so they have no mechanism to carry an enclosing local variable environment like a local inner class.

### 4.1. The Right Way: Pass Needed Data into the Record

You can turn the dependent variable into a **record component**:

```java
public class LocalRecordFixed {
    static void run() {
        int threshold = 10;

        record Score(int value, int limit) {
            boolean passes() {
                return value >= limit;
            }
        }

        Score score = new Score(12, threshold);
        System.out.println(score.passes()); // true
    }

    public static void main(String[] args) {
        run();
    }
}
```

Or pass a parameter to the method instead of storing the threshold in every record:

```java
static void process(int threshold) {
    record Score(int value) {
        boolean passes(int limit) {
            return value >= limit;
        }
    }

    Score score = new Score(12);
    System.out.println(score.passes(threshold));
}
```

The two approaches express two different meanings:

- `limit` is **part of the result's data**: put it in a component of `Score`.
- `limit` is **an evaluation parameter at call time**: pass it to `passes(limit)`.

Do not add a component merely to work around a compile error if that value is not actually part of the object's data.

## 5. Local Records and Instance State of the Enclosing Class

A local record declared inside an instance method **has no implicit enclosing instance reference (`Outer.this`)**.

Invalid example:

```java
public class InstanceCaptureDemo {
    private final String prefix = "MEASURE-";

    void report() {
        record Result(int value) {
            String label() {
                return prefix + value; // ERROR: accesses enclosing instance field.
            }
        }
    }
}
```

To use `prefix`, you can:

**Approach 1 — Pass the value into a component if it belongs to the record's state:**

```java
public class InstanceValueDemo {
    private final String prefix = "MEASURE-";

    void report() {
        record Result(String prefix, int value) {
            String label() {
                return prefix + value;
            }
        }

        Result result = new Result(prefix, 42);
        System.out.println(result.label()); // MEASURE-42
    }
}
```

**Approach 2 — Keep formatting in the enclosing method if the record only needs to carry data:**

```java
public class InstanceFormatterDemo {
    private final String prefix = "MEASURE-";

    void report() {
        record Result(int value) {}

        Result result = new Result(42);
        System.out.println(prefix + result.value()); // MEASURE-42
    }
}
```

The second approach usually fits better if `prefix` is configuration of the presentation service, while `Result` only needs to hold the result value.

### 5.1. Can Access `static` Members of the Enclosing Type

Not capturing an instance **does not mean forbidding all outer members**. A local record can reference accessible `static` members according to normal rules.

```java
public class StaticMemberAccess {
    private static final int MINIMUM = 18;

    static void evaluate() {
        record Applicant(int age) {
            boolean eligible() {
                return age >= MINIMUM;
            }
        }

        System.out.println(new Applicant(20).eligible()); // true
    }
}
```

`MINIMUM` is a `static` member of the enclosing class. This is a dependency on an accessible static value, **different from capturing a `final` local variable of a method**.

## 6. Nested Records: Records as Members of a Class or Interface

A **nested/member record** is declared in the body of a class or interface. That record exists as a **named member type** and can be used from multiple methods wherever access rules permit.

Example file **`OrderReport.java`**:

```java
import java.util.List;

public class OrderReport {
    private static final String CURRENCY = "VND";

    public record Line(String productCode, int quantity, long unitPrice) {
        public Line {
            if (productCode == null || productCode.isBlank()) {
                throw new IllegalArgumentException("productCode is required");
            }
            if (quantity <= 0 || unitPrice < 0) {
                throw new IllegalArgumentException("invalid quantity or price");
            }
        }

        public long lineTotal() {
            return Math.multiplyExact(quantity, unitPrice);
        }

        public String displayTotal() {
            return lineTotal() + " " + CURRENCY;
        }
    }

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new OrderReport.Line("P-17", 2, 50_000),
                new OrderReport.Line("P-21", 1, 30_000));

        for (Line line : lines) {
            System.out.println(line.productCode() + ": " + line.displayTotal());
        }
    }
}
```

Run:

```bash
javac --release 17 OrderReport.java
java OrderReport
```

Output:

```text
P-17: 100000 VND
P-21: 30000 VND
```

Notable points:

1. `Line` is declared **inside `OrderReport`**, so its qualified name when referenced from elsewhere is `OrderReport.Line`.
2. `Line` is **implicitly `static`**. Creating `new OrderReport.Line(...)` does not require creating an `OrderReport` instance with `new OrderReport()`.
3. `Line` can access `CURRENCY`, which is a `static` member of `OrderReport`.
4. `Line` has a constructor validating data and can add instance methods like `lineTotal()`.
5. `public` lets `Line` be accessed anywhere the enclosing class is accessible; you can use `private` or other visibility depending on design goals.

It is **not required** to write the `static` keyword before a member record: member records are already static by default.

## 7. Nested Records Are Not Bound to an Enclosing Class Instance

Compare two declarations inside the same class:

```java
public class Container {
    private final int offset;

    public Container(int offset) {
        this.offset = offset;
    }

    public class InnerCounter {
        public int add(int value) {
            return offset + value;
        }
    }

    public record Snapshot(int value) {
    }
}
```

Instantiation:

```java
Container container = new Container(10);

Container.InnerCounter counter = container.new InnerCounter();
System.out.println(counter.add(5)); // 15

Container.Snapshot snapshot = new Container.Snapshot(5);
System.out.println(snapshot.value()); // 5
```

**`InnerCounter`** is a *non-static inner class*, so its instance is bound to a `Container` and can access `offset`.

**`Snapshot`** is a member record, implicitly static, **with no enclosing `Container` instance**. Therefore, the following code is invalid:

```java
public class InvalidOuterAccess {
    private int offset = 10;

    record Snapshot(int value) {
        int total() {
            return value + offset; // COMPILE ERROR.
        }
    }
}
```

If the total truly needs an offset, pass it as a component or method parameter:

```java
public class ValidOuterAccess {
    private int offset = 10;

    record Snapshot(int value) {
        int totalWith(int offset) {
            return value + offset;
        }
    }

    void show() {
        Snapshot snapshot = new Snapshot(5);
        System.out.println(snapshot.totalWith(offset)); // 15
    }
}
```

This rule applies to **both local records and member records**: nesting a type inside a class does not automatically create a link to that class's instance state.

## 8. Nested Records in Interfaces and Inside Inner Classes

### 8.1. Records Nested Inside an Interface

An interface can declare member records. This is useful for grouping result variants or messages under a shared meaningful namespace.

```java
public sealed interface OperationResult
        permits OperationResult.Success, OperationResult.Failure {

    record Success(String message) implements OperationResult {
    }

    record Failure(int code, String reason) implements OperationResult {
    }
}
```

Usage:

```java
OperationResult result = new OperationResult.Success("Saved");
System.out.println(result);
```

Both member records inside the interface are **implicitly `public static`** per interface member type rules. You can refer to `OperationResult.Success` without an `OperationResult` instance.

This also combines cleanly with `sealed interface`: only permitted types may directly implement the interface.

### 8.2. Records Nested Inside a Non-Static Inner Class Are Valid in Java 17

Example:

```java
public class Dashboard {
    public class Panel {
        public record Coordinate(int x, int y) {
        }
    }
}
```

This is valid syntax in Java 17: `Coordinate` is a **member record, implicitly static**, even though `Panel` is a non-static inner class.

A difference that often confuses learners is that in very old Java versions, declaring static members inside inner classes faced different restrictions. By Java 17, those restrictions were relaxed to allow static member types such as nested records. Do not mechanically apply outdated rules when learning Java 17.

You do not need a `Dashboard` or `Panel` instance for the `Coordinate` type to exist. Even though the name `Dashboard.Panel.Coordinate` has multiple levels, the long name **does not** imply a chain of nested instance references.

## 9. Static Context and Generic Type Parameters

A similar issue as with instance variables occurs with **generic type parameters of an enclosing class or method**.

### 9.1. Nested Records Cannot Use the Enclosing Class's Type Parameter

Example that **does not compile**:

```java
public class GenericBox<T> {
    record Item(T value) {  // ERROR: T of GenericBox belongs to the enclosing instance context.
    }
}
```

`Item` is implicitly static, so it cannot directly reference the type parameter `T` belonging to a generic `GenericBox<T>` instance.

The solution is giving the record **its own type parameter**:

```java
public class GenericBox<T> {
    record Item<U>(U value) {
    }

    void show(T value) {
        Item<T> item = new Item<>(value);
        System.out.println(item.value());
    }
}
```

`U` belongs to the declaration of `Item<U>` and is completely valid. `T` is passed through the usage `Item<T>` inside `show`, rather than being captured by the record's member definition.

### 9.2. Local Records Cannot Capture the Enclosing Method's Type Parameter

The following example is also invalid:

```java
public class LocalGenericDemo {
    static <T> void print(T value) {
        record Holder(T item) { // ERROR: local records cannot capture T.
        }
    }
}
```

Fix it by declaring the record's own type parameter:

```java
public class LocalGenericDemo {
    static <T> void print(T value) {
        record Holder<U>(U item) {
        }

        Holder<T> holder = new Holder<>(value);
        System.out.println(holder.item());
    }

    public static void main(String[] args) {
        print("Java 17");
        print(17);
    }
}
```

Thus, a **`record` can be generic**, but local/member records cannot arbitrarily reference type parameters of an enclosing context like a context-bound inner class can.

## 10. What Does `static` Mean for Record Components and Methods?

Do not confuse **a record being implicitly static with respect to its enclosing class** with all members inside the record being static.

Consider:

```java
public class RecordMembersDemo {
    record Reading(int value) {
        private static final String UNIT = "ms";

        String display() {
            return value + " " + UNIT;
        }

        static Reading zero() {
            return new Reading(0);
        }
    }

    public static void main(String[] args) {
        Reading first = new Reading(12);
        Reading second = Reading.zero();

        System.out.println(first.display());  // 12 ms
        System.out.println(second.display()); // 0 ms
    }
}
```

Here:

- `Reading` is an **implicitly static member record**.
- `value` is **per-instance** state, read via `first.value()` or `second.value()`.
- `display()` is an **instance method**, operating on the current object's value.
- `UNIT` is a shared **`static` field**, valid because it is a `static` field.
- `zero()` is a **`static` factory method**, able to create and return a `Reading` instance.

A record **cannot manually declare additional instance fields** beyond those corresponding to record components:

```java
record InvalidReading(int value) {
    // private int extra; // ERROR: extra instance fields are not allowed.
}
```

If `extra` truly belongs to data state, make it a record component. If it is a shared instance-independent value, consider a `static final` constant.

## 11. Comparison Table: Local Class, Local Record, and Member Record

| Characteristic | Regular Local Class | Local Record | Member/Nested Record |
| --- | --- | --- | --- |
| Declared inside method/block | Yes | Yes | No, declared at member level of enclosing type |
| Implicitly static | No | **Yes** | **Yes** |
| Captures final/effectively final local variables | **Yes** | **No** | No local variable scope to capture |
| Accesses enclosing instance via inner-class relation | Yes in appropriate context | **No** | **No** |
| Accesses enclosing static members | Yes, if accessible | Yes, if accessible | Yes, if accessible |
| Built-in component-based accessors, `equals`, `hashCode`, `toString` | Not automatic | Yes | Yes |
| Reusable as a type name in other methods | Not directly | Not directly | Yes, per access modifiers |
| Used for data structures serving a single algorithm | Possible | **Well-suited** | Possible, though wider scope |
| Used as a shared data type across methods | Unsuitable | Unsuitable | **Well-suited** |

The crux is **the lifetime scope of the type name** and **its relationship to the enclosing context**, not whether you have to write the `static` keyword when declaring it.

## 12. Practical Example: Local Record for Calculation Steps, Nested Record for Output Data

Suppose a feature needs to sum product quantities in an order. Input and output data may be used in multiple places, so place them as **member records**. A helper structure normalizing each line only serves the algorithm, so declare it as a **local record**.

Create **`OrderSummaryDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class OrderSummaryDemo {
    public record Order(String id, List<Integer> quantities) {
        public Order {
            Objects.requireNonNull(id, "id");
            quantities = List.copyOf(quantities);
        }
    }

    public record Summary(
            String orderId,
            int lineCount,
            int totalUnits) {
    }

    public static Summary summarize(Order order) {
        Objects.requireNonNull(order, "order");

        // Used solely during line-by-line iteration.
        record IndexedQuantity(int index, int quantity) {
            IndexedQuantity {
                if (quantity <= 0) {
                    throw new IllegalArgumentException(
                            "Invalid quantity at line " + index);
                }
            }
        }

        int total = 0;
        for (int i = 0; i < order.quantities().size(); i++) {
            IndexedQuantity line =
                    new IndexedQuantity(i, order.quantities().get(i));
            total = Math.addExact(total, line.quantity());
        }

        return new Summary(order.id(), order.quantities().size(), total);
    }

    public static void main(String[] args) {
        Order order = new Order("OD-17", List.of(2, 3, 1));
        Summary summary = summarize(order);

        System.out.println(summary);
    }
}
```

Run:

```bash
javac --release 17 OrderSummaryDemo.java
java OrderSummaryDemo
```

Output:

```text
Summary[orderId=OD-17, lineCount=3, totalUnits=6]
```

Analyzing the roles:

1. **`Order`** is reusable input data, so it is a member record. The canonical constructor copies the list with `List.copyOf` to avoid external mutation via the passed-in list.
2. **`Summary`** is the result type callers can use to read `totalUnits()` or `lineCount()`, so it is also a member record.
3. **`IndexedQuantity`** only validates and names per-line data inside `summarize`, without needing to become a public type.
4. The local record **explicitly receives** `index` and `quantity` through its constructor; it does not capture the method's `i` or `order` variables.
5. `Math.addExact` detects integer overflow instead of silently returning a wrapped wrong total; this illustrates checking arithmetic bounds.

Later, if `IndexedQuantity` becomes needed in multiple methods, you can promote it to a **member record** with suitable visibility without changing the core meaning of its components.

## 13. How to Choose Where to Place a Record?

| Design Question | Usually Suitable Placement | Reason |
| --- | --- | --- |
| Structure only helps processing inside one method? | **Local record** | Limits scope, avoids polluting broader APIs. |
| Multiple methods of one class need a helper data type? | **`private` member record** | Shared within the class while keeping implementation details hidden. |
| Type is part of the class/module's API? | **Member record with appropriate visibility** or top-level record | Lets callers name and use the data type clearly. |
| Type represents domain data used broadly across package/module? | **Top-level record** | Avoids coupling to an enclosing class name when no real ownership exists. |
| Data needs configuration values from an enclosing service? | **Pass values explicitly or keep logic in the service** | Do not assume a record captures `this`. |
| Type needs an extra generic parameter? | **Declare the record's own type parameter** | Local/member records cannot capture enclosing type parameters. |
| Need an object with mutable identity and multiple reassignable fields? | **Regular class** | Records fit representing fixed state defined by components. |

Nesting a record inside a class just because you "want it in the same file" is not a sufficient design reason. Ask whether that type truly belongs to the enclosing class's scope.

Conversely, using top-level records for every temporary structure fragments the namespace and obscures which records are mere processing details.

## 14. Common Mistakes in Java 17

### 14.1. Confusing a Local Record with a Local Inner Class

Wrong:

```java
void calculate() {
    int extra = 5;
    record Value(int amount) {
        int total() {
            return amount + extra; // Cannot capture extra.
        }
    }
}
```

Fix: turn `extra` into a component or a parameter of `total(...)`.

### 14.2. Confusing a Member Record with an Inner Class Requiring an Enclosing Instance

Wrong:

```java
class Outer {
    record Data(int id) {}
}

// Outer outer = new Outer();
// Outer.Data value = outer.new Data(1); // Invalid instantiation syntax.
```

Right:

```java
Outer.Data value = new Outer.Data(1);
```

### 14.3. Thinking `static` Makes Components Shared Variables

Two instances `new Outer.Data(1)` and `new Outer.Data(2)` have distinct `id` values. Being implicitly static only describes **how the type is nested**, not turning `id` into a static field.

### 14.4. Referencing an Enclosing Class's Generic Type Parameter

Wrong:

```java
class Container<T> {
    record Entry(T data) {} // Invalid.
}
```

Right:

```java
class Container<T> {
    record Entry<U>(U data) {}
}
```

### 14.5. Trying to Reference a Local Record from Another Method

A local record cannot be used as a parameter or return type in another method declaration outside its scope. If you need a contract like `Summary summarize(Order input)` callable elsewhere, declare `Summary` as a member record or top-level record.

### 14.6. Adding Access Modifiers to a Local Record

A local declaration is not a member declaration; you cannot add `private`, `protected`, or `public` to adjust a local record's visibility.

Invalid:

```java
void run() {
    // private record Pair(int x, int y) {} // ERROR.
}
```

If you need class-level access control, promote the type to a member record and choose the appropriate modifier.

### 14.7. Assuming Records Are Deeply Immutable

```java
record Tags(List<String> names) {}
```

The `names` reference field is `final`, yet the passed-in list could be a mutable `ArrayList`. If an unmodifiable snapshot is required, copy on construction:

```java
record Tags(List<String> names) {
    Tags {
        names = List.copyOf(names);
    }
}
```

`List.copyOf` creates a list disallowing standard mutation operations. For components holding objects with mutable internal state, also consider deeper protection as needed.

## 15. Self-Check Questions

**1. Why can't a `record` declared inside an instance method access an enclosing instance field?**  
Because local records are implicitly static and have no `Outer.this` reference. If data is needed, pass it explicitly via constructor or method parameters.

**2. Does a local record capture `final` local variables like a local class?**  
No. Local records do not capture variables in enclosing blocks, even when those variables are `final` or effectively final.

**3. Does a member record inside a class need the `static` keyword to be instantiated with `new Outer.Record(...)`?**  
No. Member records are inherently implicitly static.

**4. Can a record be declared inside an interface?**  
Yes. A member record inside an interface is implicitly `public static`.

**5. Can a record be placed inside a non-static inner class in Java 17?**  
Yes. The member record remains implicitly static and is not tied to any instance of its enclosing inner class.

**6. Why is `class Box<T> { record Item(T value) {} }` invalid?**  
Because a static member record cannot directly use an instance-level type parameter of `Box<T>`. It can be fixed as `record Item<U>(U value) {}`.

**7. When should a local record be promoted to a nested record?**  
When multiple methods or an API contract need to refer to that type by name and share its data structure.

**8. Can a local record have instance methods using its components?**  
Yes. For example, `record Pair(int a, int b) { int sum() { return a + b; } }` is completely valid; being implicitly static relative to the enclosing type does not turn all of the record's methods into static methods.

## References

- [JEP 395 — Records](https://openjdk.org/jeps/395): records in Java, including local records and member records being implicitly static.
- [Java Language Specification — Java SE 17, `8.10 Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record components, constructors, member/local records, and constraints.
- [Java Language Specification — Java SE 17, `8.1.3 Inner Classes and Enclosing Instances](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): enclosing instance relationships and differences between inner classes and nested static classes.
- [Java Language Specification — Java SE 17, `14.3 Local Class and Interface Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.3): scope and rules for local type declarations.
- [Java SE 17 API — `java.lang.Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): base class of records.
