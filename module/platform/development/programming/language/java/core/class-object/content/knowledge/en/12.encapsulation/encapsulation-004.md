# Data Validation at Creation and Update Points in Java

**Encapsulation** is not merely about declaring `private` fields and creating getters/setters. The more important goal is to **control every path that can change an object's state**, so that the object always complies with the validity rules (*invariants*) defined by the class. Therefore, data validation must take place at **creation points** — typically constructors or static factories — and at **update points** — methods that modify state.

For example, an item may require a non-empty item code, a positive selling price, and a non-negative stock quantity. The constructor needs to reject invalid data upon creation; methods for receiving stock, selling items, and changing prices must also reject operations that would make an already valid object become invalid.

This lesson explains how to define invariants, distinguish parameter validation from resulting-state validation, apply the **validate first — update later** sequence, handle multiple interdependent fields, avoid exposing mutable data, as well as the boundaries of `final`, errors, and testing. The standalone programs compile and run with **Java 17 or later**.

## 1. Why Validate at Both Creation and Update?

Consider a class with these fields:

~~~java
class Item {
    private String name;
    private int quantity;

    Item(String name, int quantity) {
        this.name = name;
        this.quantity = quantity;
    }

    void setQuantity(int quantity) {
        this.quantity = quantity;
    }
}
~~~

This is a **valid illustrative class**, yet it still lacks validation. A caller can create `new Item("", -3)`; or create `new Item("Bút", 10)` and then call `setQuantity(-99)`. Using `private` alone does not prevent invalid values from slipping through **accessible methods**.

If the business rules are:

~~~text
name != null
name does not consist only of whitespace
quantity >= 0
~~~

then a correct class must preserve them **after every successful creation or update**. That is the meaning of an invariant.

| Control point | Question to answer | Example |
| --- | --- | --- |
| Constructor | Is it allowed to create an object with this input data? | Name must be valid, initial stock non-negative |
| Static factory | Can the input be validated and normalized before returning the object? | `Item.of("  Bút  ", 5)` |
| State-changing method | Is the result after the action still valid? | Receiving stock without numeric overflow |
| Multi-parameter method | Do the **combined** fields satisfy the constraints? | `start <= end` |
| Mutable input | Can the data be modified through a reference held externally? | Copy arrays/lists when receiving and returning |
| Multithreading | Can check-then-update be interleaved? | Locks or atomic mechanisms for shared state |

**Do not validate only in the UI or controller.** Other code in the program, tests, background tasks, or another API can still call the constructor/method directly. A class should protect the invariants that are its own responsibility.

## 2. Distinguishing Precondition, Postcondition, and Invariant

Three concepts are related but not identical:

- **Precondition:** the condition the caller must satisfy before the method executes successfully. For example, `receive(amount)` requires `amount > 0`.
- **Postcondition:** what holds true after the method completes normally. For example, `receive(3)` increases the stock quantity by exactly 3.
- **Invariant:** what must hold true at valid observation points of the object. For example, `quantity >= 0` after the constructor and after public operations complete.

Example:

~~~text
Before calling sell(4):
  quantity = 10                   (invariant: quantity >= 0)
  amount = 4                      (precondition: amount > 0)

After sell(4) succeeds:
  quantity = 6                    (postcondition: decreases by exactly 4)
  quantity >= 0                   (invariant still holds)

If calling sell(99):
  amount > 0 but insufficient stock
  -> reject and keep quantity = 10
~~~

A rule such as "cannot sell more than the quantity on hand" cannot be checked with `amount > 0` alone. It depends on **both the parameter and the current state**.

**Good encapsulation** means keeping the authority to modify data in methods that have enough information to protect invariants, rather than mechanically exposing setters for every field.

## 3. Defining Invariants Before Writing the Constructor

Before writing code, make a table for each field:

| Field | Data type | Proposed invariant | Can it be changed? |
| --- | --- | --- | --- |
| `sku` | `String` | Non-null and non-blank | No, the item code is stable |
| `name` | `String` | Non-null and non-blank | Yes, via updating details |
| `quantity` | `int` | Non-negative | Yes, via receiving/selling |
| `priceCents` | `long` | Greater than 0 | Yes, via updating details |

These are **illustrative rules**, not mandatory rules for every sales system. Depending on the problem, a price of 0 might be valid for free items, or negative inventory might be represented when managing pre-orders. What matters is choosing rules that are **clear and consistent**.

Use `private` to prevent callers from assigning fields directly; use `final` when a field must not be reassigned after initialization; and provide methods that **express behavior** such as `receive`, `sell`, and `updateDetails` instead of making every operation just `setX`.

In Java, a constructor allows an object to be created in a valid initial state. An update method must continue to maintain a valid state and must not assume "it was already checked in the constructor, so it is no longer needed afterward".

## 4. Complete Program: Protecting an Item's Invariants

Create a file named **`EncapsulationValidationDemo.java`** containing an encapsulated `InventoryItem` class and a `public` class holding `main`.

~~~java
final class InventoryItem {
    private final String sku;
    private String name;
    private int quantity;
    private long priceCents;

    InventoryItem(String sku, String name, int quantity, long priceCents) {
        this.sku = checkedText(sku, "sku");
        this.name = checkedText(name, "name");
        this.quantity = checkedQuantity(quantity);
        this.priceCents = checkedPrice(priceCents);
    }

    private static String checkedText(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(field + " không hợp lệ");
        }
        return value.strip();
    }

    private static int checkedQuantity(int value) {
        if (value < 0) {
            throw new IllegalArgumentException("quantity không được âm");
        }
        return value;
    }

    private static long checkedPrice(long value) {
        if (value <= 0) {
            throw new IllegalArgumentException("priceCents phải dương");
        }
        return value;
    }

    void receive(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }
        int nextQuantity = Math.addExact(quantity, amount);
        quantity = nextQuantity;
    }

    void sell(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount phải dương");
        }
        if (amount > quantity) {
            throw new IllegalArgumentException("không đủ hàng");
        }
        quantity -= amount;
    }

    void updateDetails(String newName, long newPriceCents) {
        String checkedName = checkedText(newName, "name");
        long checkedPrice = checkedPrice(newPriceCents);

        name = checkedName;
        priceCents = checkedPrice;
    }

    String summary() {
        return sku + " | " + name
                + " | q=" + quantity
                + " | price=" + priceCents;
    }
}

public class EncapsulationValidationDemo {
    public static void main(String[] args) {
        InventoryItem item = new InventoryItem(
                "SKU-01", "  Bút  ", 10, 5000);

        System.out.println("created=" + item.summary());

        item.receive(5);
        item.sell(3);
        System.out.println("updated=" + item.summary());

        try {
            item.receive(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject receive=" + ex.getMessage());
        }

        try {
            item.updateDetails("Vở", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject details=" + ex.getMessage());
        }
        System.out.println("after errors=" + item.summary());

        item.updateDetails("Vở", 7000);
        System.out.println("valid change=" + item.summary());

        try {
            item.sell(99);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject sell=" + ex.getMessage());
        }

        try {
            item.receive(Integer.MAX_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("reject overflow");
        }

        try {
            new InventoryItem("X", "Sai", -1, 100);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject create=" + ex.getMessage());
        }
        System.out.println("final=" + item.summary());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 EncapsulationValidationDemo.java
java EncapsulationValidationDemo
~~~

**Exact stdout:**

~~~text
created=SKU-01 | Bút | q=10 | price=5000
updated=SKU-01 | Bút | q=12 | price=5000
reject receive=amount phải dương
reject details=priceCents phải dương
after errors=SKU-01 | Bút | q=12 | price=5000
valid change=SKU-01 | Vở | q=12 | price=7000
reject sell=không đủ hàng
reject overflow
reject create=quantity không được âm
final=SKU-01 | Vở | q=12 | price=7000
~~~

### Analyzing the Validation Points

**In the constructor:** `sku` and `name` are checked to be non-null/non-blank, then `strip()` removes leading/trailing whitespace; `quantity` must be non-negative and `priceCents` must be positive. As a result, `"  Bút  "` becomes `"Bút"`. The `sku` field is `final`, meaning this field reference cannot be reassigned after initialization.

**In `receive`:** check `amount > 0`, and compute `nextQuantity` via `Math.addExact` to detect `int` overflow. Only after the calculation completes normally is `quantity = nextQuantity` executed. When trying to add `Integer.MAX_VALUE` to 12, the calculation throws `ArithmeticException`, while `quantity` stays 12.

**In `sell`:** the amount sold must be positive and not greater than the stock on hand. Because both conditions have been checked, the subtraction keeps quantity non-negative.

**In `updateDetails`:** validate **both new values before assigning any field**. The call `updateDetails("Vở", 0)` is rejected and keeps both the name `Bút` and the price 5000 unchanged. When both are valid, both fields are updated together.

**When the constructor fails:** `new InventoryItem("X", "Sai", -1, 100)` is rejected. The object creation expression does not complete normally and does not return a valid object reference to the caller.

Thanks to `final class InventoryItem`, the example also prevents subclasses from altering the update rules or overriding behavior. A class that allows inheritance will need to design and test its own inheritance contract.

## 5. Validation at Creation Points: Constructor and Factory

A constructor is a critical boundary because it determines whether an object can be created successfully with an initial state.

A constructor needs to:

1. Determine the required parameters and which fields have default values.
2. Reject values that do not satisfy invariants.
3. Normalize input data if the contract requires it, such as `strip()` for names.
4. Properly initialize all fields and the relationships between fields.
5. Do not publish `this` prematurely to a listener/thread while state is still incomplete.

A static factory can also take on validation before returning an object, yet **an internal constructor should not become a way to bypass invariants** if other code within the class can still call that constructor.

For example, when you want a factory name to express intent:

~~~java
final class Percent {
    private final int value;

    private Percent(int value) {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("percent ngoài 0..100");
        }
        this.value = value;
    }

    static Percent of(int value) {
        return new Percent(value);
    }

    int value() {
        return value;
    }
}
~~~

This is a valid illustrative class; callers can use `Percent.of(75)`, while `Percent.of(150)` is rejected by the constructor. The factory provides an expressive way to call it, and the constructor continues to act as the **final gatekeeper**.

If there are multiple overloaded constructors, validation logic should be consolidated into a core constructor or shared validation functions to avoid each creation path applying a different set of rules. **Do not call an overridable instance method from a constructor** if it could observe a subclass that is not yet fully initialized.

## 6. Validation at Update Points: Valid Parameters Do Not Guarantee a Valid Resulting State

A simple setter can validate a value domain:

~~~java
void setPriceCents(long priceCents) {
    if (priceCents <= 0) {
        throw new IllegalArgumentException("giá phải dương");
    }
    this.priceCents = priceCents;
}
~~~

This is an **illustrative method** in a class with a `priceCents` field. It properly validates the intrinsic condition of the price.

However, behavioral updates often also require the **previous state**. For example:

~~~java
void sell(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount phải dương");
    }
    if (amount > quantity) {
        throw new IllegalArgumentException("không đủ hàng");
    }
    quantity -= amount;
}
~~~

A request to sell 20 units may be valid when stock is 50, but **invalid** when stock is 5. Therefore, validation at the update point cannot be replaced solely with "`amount` must be a positive integer".

**The right condition must be checked on the resulting state**, such as `nextQuantity >= 0`. For integer addition, compute it with `Math.addExact` to eliminate the risk of overflow unexpectedly turning `nextQuantity` negative.

## 7. Validate First — Update Later to Avoid Partially Updated State

Suppose a method needs to modify **two fields**. The dangerous approach:

~~~java
void updateDetails(String newName, long newPrice) {
    name = checkedText(newName, "name");
    priceCents = checkedPrice(newPrice);
}
~~~

This is an example that **compiles but has poor design** when the requirement is "preserve the existing state on failure". If the name is valid while the price is invalid, the method has already modified `name` before the price check throws an exception.

A more appropriate approach:

~~~java
void updateDetails(String newName, long newPrice) {
    String checkedName = checkedText(newName, "name");
    long checkedPrice = checkedPrice(newPrice);
    name = checkedName;
    priceCents = checkedPrice;
}
~~~

The snippets above only illustrate two **alternative versions** of the same method, not two overloads that may be declared simultaneously. In the second version, validation and normalization happen first; if a check fails, **no field has been reassigned yet**.

Model:

~~~text
Receive new values
        |
        v
Validate each parameter
        |
        v
Validate relationships between values
        |
        v
Compute resulting state (may fail/overflow)
        |
        +-- error --> throw exception, preserve old state
        |
        v
Assign fields as planned
        |
        v
Return successful result
~~~

**Important limitation:** two consecutive assignments do not become an atomic transaction across **multiple threads** just because validation was performed beforehand. This pattern helps avoid a partially updated state caused by synchronous errors within the same call; if the object is shared concurrently, a separate synchronization mechanism is required.

## 8. Cross-Field Constraints: Must Validate Relationships, Not Just Individual Values

An object representing an integer range has the invariant `0 <= start <= end`. Two fields can be individually non-negative yet still **invalid in combination**, for example `start=9`, `end=3`.

Create a file named **`RangeValidationDemo.java`**:

~~~java
final class Range {
    private int start;
    private int end;

    Range(int start, int end) {
        validate(start, end);
        this.start = start;
        this.end = end;
    }

    void moveTo(int newStart, int newEnd) {
        validate(newStart, newEnd);
        this.start = newStart;
        this.end = newEnd;
    }

    private static void validate(int start, int end) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("range không hợp lệ");
        }
    }

    String describe() {
        return "[" + start + "," + end + "]";
    }
}

public class RangeValidationDemo {
    public static void main(String[] args) {
        Range range = new Range(2, 5);
        System.out.println("original=" + range.describe());

        try {
            range.moveTo(9, 3);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("after reject=" + range.describe());

        range.moveTo(6, 8);
        System.out.println("updated=" + range.describe());

        try {
            new Range(-1, 4);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject create=" + ex.getMessage());
        }
    }
}
~~~

Compile and run:

~~~bash
javac RangeValidationDemo.java
java RangeValidationDemo
~~~

**Stdout:**

~~~text
original=[2,5]
reject=range không hợp lệ
after reject=[2,5]
updated=[6,8]
reject create=range không hợp lệ
~~~

Lessons from the example:

- `validate` is shared at both the **constructor and the update point**.
- `moveTo` accepts **two proposed values** and validates the relationship between them as well before changing the fields.
- Calling `range.moveTo(9,3)` is rejected and keeps `[2,5]`.
- The `Range` type is declared `final` so no subclass can override the initialization/update logic; a class with inheritance requires a different appropriate design.

If you provide two independent setters `setStart` and `setEnd`, it is very easy to produce an intermediate state that violates `start <= end`, even when the final desired result is valid. When an invariant involves multiple fields, a **grouped update method** such as `moveTo(start,end)` is usually clearer and safer.

## 9. Choosing Exception Types Consistently

Java does not enforce a single exception type for all validation. Common choices:

| Situation | Potentially suitable exception |
| --- | --- |
| Parameter is outside the allowed domain | `IllegalArgumentException` |
| Required parameter must not be null | `NullPointerException` from `Objects.requireNonNull`, or `IllegalArgumentException` per contract |
| Calling an operation in an object state that does not yet allow it | `IllegalStateException` |
| Array/list index out of bounds | `IndexOutOfBoundsException` or an exception thrown by the collection |
| Integer addition/multiplication with overflow checking | `ArithmeticException` from `Math.addExact`/`multiplyExact` |
| Invalid size/string content | `IllegalArgumentException` or an exception type published by the API |

In `InventoryItem`, the program deliberately chooses `IllegalArgumentException` for both null and whitespace-only strings. This is a **convention applied consistently within the class**, not a rule forcing all APIs to use the same exception.

Error messages should identify the **invalid condition** without leaking sensitive data. For example, `quantity không được âm` is more helpful than a generic message `invalid`.

### Validation Is Not Abusing `try/catch`

An update method should **reject by throwing an exception** if its contract specifies so. The caller can catch the error at the UI boundary to display a friendly message; you should not automatically catch every exception inside a setter and silently ignore it, leading the caller to believe the update succeeded.

Another option is for the API to return a result carrying a success/failure status. Use that approach when input errors are a normal business case, while still protecting invariants in the implementation.

## 10. Data Normalization and Validation: Distinguish the Order Clearly

"Validation" and "normalization" are not entirely the same:

- **Validation:** determines whether to accept a value or not.
- **Normalization:** transforms a valid input into a uniform representation, for example `"  Bút  "` into `"Bút"`.

In `checkedText`:

~~~java
private static String checkedText(String value, String field) {
    if (value == null || value.isBlank()) {
        throw new IllegalArgumentException(field + " không hợp lệ");
    }
    return value.strip();
}
~~~

The check avoids `NullPointerException` before calling the `isBlank()` method. Use `String.strip()` (Java 11+) to remove whitespace according to the Unicode definition supported by the method. The normalized result is written to the field without modifying the original `String` because `String` is immutable.

Depending on requirements, an application may need to normalize **before checking length**. For example, the string `"  A  "` has length 5, yet after `strip()` its length is only 1. You must clearly choose whether to measure before or after, avoiding inconsistent rules between the constructor and setter.

**Do not normalize all data arbitrarily.** SKU codes, passwords, identifier keys, legal names, or strings containing meaningful whitespace may need to be preserved as-is. A method named `normalize` must clearly express what gets changed.

## 11. Controlling Mutable Inputs: Constructors Must Consider Defensive Copying

If a constructor accepts an `int[]`, `List`, `Date`, or another mutable object and **stores the reference directly**, the caller can keep an alias and modify the data after the object is created. In that case, invariants can be broken **without going through any setter**.

Example to avoid when independent data ownership is needed:

~~~java
class WeakGradeBook {
    private final int[] grades;

    WeakGradeBook(int[] grades) {
        this.grades = grades;
    }
}
~~~

This is a valid illustrative class. `private final int[] grades` only prevents reassigning the **field reference** after the constructor; it does not make the **array elements** immutable.

If the caller passes `int[] scores = {80,90}` and the constructor stores `scores` directly, the caller can later modify `scores[0] = -10`; the object holding the **same array** will see the invalid value.

The typical protection is to:

1. Check that the array parameter is non-null.
2. **Copy the data into a separate array** before storing it in the object's state.
3. Validate each element of the copy.
4. Assign the field only after all data is valid.
5. When returning the array externally, **return a copy** instead of exposing the internal array.

## 12. Complete Program: Copying and Validating an Array in Both Directions

Create a file named **`GradeBookValidationDemo.java`**:

~~~java
import java.util.Arrays;

final class GradeBook {
    private int[] grades;

    GradeBook(int[] input) {
        grades = checkedCopy(input);
    }

    void replaceGrades(int[] input) {
        int[] replacement = checkedCopy(input);
        grades = replacement;
    }

    int[] grades() {
        return grades.clone();
    }

    String summary() {
        return Arrays.toString(grades);
    }

    private static int[] checkedCopy(int[] input) {
        if (input == null) {
            throw new IllegalArgumentException("grades null");
        }
        int[] copy = input.clone();
        for (int grade : copy) {
            if (grade < 0 || grade > 100) {
                throw new IllegalArgumentException("grade ngoài 0..100");
            }
        }
        return copy;
    }
}

public class GradeBookValidationDemo {
    public static void main(String[] args) {
        int[] source = {80, 90};
        GradeBook book = new GradeBook(source);
        System.out.println("created=" + book.summary());

        source[0] = -10;
        System.out.println("after external edit=" + book.summary());

        int[] exported = book.grades();
        exported[1] = -10;
        System.out.println("after getter edit=" + book.summary());

        try {
            book.replaceGrades(new int[] {90, 101});
        } catch (IllegalArgumentException ex) {
            System.out.println("reject replace=" + ex.getMessage());
        }
        System.out.println("after reject=" + book.summary());

        int[] newSource = {100, 95};
        book.replaceGrades(newSource);
        newSource[1] = -1;
        System.out.println("after valid replace=" + book.summary());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 GradeBookValidationDemo.java
java GradeBookValidationDemo
~~~

**Stdout:**

~~~text
created=[80, 90]
after external edit=[80, 90]
after getter edit=[80, 90]
reject replace=grade ngoài 0..100
after reject=[80, 90]
after valid replace=[100, 95]
~~~

Three protective measures:

- **Constructor copy:** `source[0] = -10` cannot modify `GradeBook.grades`.
- **Getter copy:** receiving `exported` and modifying that array does not modify the internal array.
- **Update copy + validation:** `replaceGrades` creates a copy and iterates to validate **before assigning the field**. If any grade is outside `0..100`, the old state is preserved. After a valid update, modifying `newSource` also does not affect the object.

For a primitive `int[]` array, `clone()` copies the numeric elements, which suffices for this requirement. For a `List<MutableStudent>` or an array of mutable objects, copying the collection/array only copies **element references**: to prevent external modification, you also need to design immutable elements or perform an appropriate deep copy.

## 13. Getters Should Not Expose a Way to Break Invariants

Making a field `private` while providing a getter that directly returns a mutable object can open a **backdoor**:

~~~java
class LeakySettings {
    private final java.util.List<String> tags =
            new java.util.ArrayList<>();

    java.util.List<String> tags() {
        return tags;
    }
}
~~~

This is a valid illustrative class. A caller can call `settings.tags().add(null)` if it holds the `settings` object, even though the class wants to forbid null tags.

Ways to improve depend on the contract:

- Return a **copy**: `return new ArrayList<>(tags);` so the caller modifies the copy.
- Return an **unmodifiable snapshot**: `return List.copyOf(tags);` when elements are permitted under `List.copyOf`'s rules (containing no nulls).
- Use dedicated query APIs such as `containsTag` and `tagCount` when there is no need to expose the collection.
- For mutable child objects, continue to consider how to control ownership of each element.

Simply writing `Collections.unmodifiableList(tags)` provides a **view that disallows modification through the view**, yet if someone still holds the original list and modifies it, the view still reflects the changes. **An unmodifiable view is not necessarily an independent snapshot**.

Similarly, `final` on a field reference does not guarantee that the entire object graph becomes immutable.

## 14. Generic Setters or Meaningful Behavioral Methods?

A class can have:

~~~java
void setQuantity(int quantity) {
    if (quantity < 0) {
        throw new IllegalArgumentException("quantity âm");
    }
    this.quantity = quantity;
}
~~~

This is an illustrative method. It may be reasonable if the business domain genuinely allows **resetting the stock quantity to an absolute value**, such as through a controlled inventory audit process.

However, if the actual business domain only allows **receiving or selling stock**, using `receive(amount)` and `sell(amount)` helps:

- Express the action and preconditions clearly.
- Validate the received/sold amount, numeric overflow, and available stock before updating.
- Restrict the allowed state transitions.
- Log events or apply business permissions if needed, at a clear point.

For an account, `deposit(amount)` and `withdraw(amount)` are usually more appropriate than a public `setBalance(anyValue)`. For reservations, `reserveSeats(count)` is better suited than replacing every field with an independent setter that does not enforce limits.

**There is no absolute rule forbidding setters.** Use one when "setting a value" is genuinely a permitted behavior and all invariants can be fully protected. Do not auto-generate getters/setters for every `private field` just because a tool supports it.

## 15. Validation Can Depend on Lifecycle State

In addition to static field invariants, many objects have a **lifecycle state**: `NEW`, `ACTIVE`, `CLOSED`; or an order with `DRAFT`, `PAID`, `CANCELLED`.

A parameter may be valid on its own, yet the operation may be invalid in the current state:

~~~java
final class DocumentState {
    private boolean closed;

    void close() {
        closed = true;
    }

    void edit() {
        if (closed) {
            throw new IllegalStateException("tài liệu đã đóng");
        }
    }

    boolean isClosed() {
        return closed;
    }
}
~~~

This is a valid illustrative class. `edit()` does nothing beyond checking the state in order to focus on the lifecycle rule; a real document API would combine this check **before the document-editing behavior** within the same method.

**`IllegalArgumentException` and `IllegalStateException` differ in cause:** the former usually indicates a bad parameter; the latter indicates that **the object is in a state that does not permit the operation**. A method may have to check both.

Do not use exceptions to mask an avoidable lifecycle design flaw, such as continuing to let external code call every setter on an already closed object.

## 16. Classes Allowing Inheritance: Avoid Bypassing Validation via Overriding

If a class is not `final` and has overridable methods, a subclass can alter the semantics of updates. A superclass method that validates data properly yet gets overridden by code that does not preserve invariants can introduce risk.

Strategies depending on the design:

- Declare the class `final` if inheritance is not intentionally supported.
- Declare essential operations as `final` when you do not want subclasses to change the contract.
- Centralize validation in private methods or members that subclasses cannot override.
- If designing for inheritance, explicitly document the invariants that subclasses must preserve and test subtypes accordingly.
- Avoid calling **overridable** methods from a constructor: a subclass override may run before the subclass fields have been initialized.

In the `InventoryItem` example, the class is `final`, all fields are `private`, and all changes can be made strictly through the defined behaviors. This is a simple design suitable for this lesson; it does not mean every system must forbid inheritance.

## 17. Validation Across Multiple System Layers: Avoid Confusing Responsibilities

An application can have validation at multiple layers:

| Layer | Typical responsibility |
| --- | --- |
| UI/form | Fast feedback for input; supporting user experience |
| API/controller | Validating request format, caller permissions, request limits |
| Domain class | Maintaining an object's invariants across all creation/update paths |
| Service/use case | Checking rules that require multiple objects or transactions |
| Database | Persistent existence constraints, consistency, unique/check/foreign keys |

Multiple layers may check the same condition, yet **for different purposes**. The form checks `quantity >= 0` to display an error immediately; the domain object must still protect its invariant when a service is called without going through the form.

A domain object alone cannot guarantee **cross-object and persistent** rules such as "the SKU is unique across the entire database" solely through constructor validation. That usually requires a service/repository and appropriate transaction constraints.

**Do not put all business logic into setters** or rely solely on UI annotations to conclude that an object's state is safe. Distinguish between what is an internal invariant and what is a rule involving the repository/system.

## 18. No Update on Failure Is a Commitment That Must Be Actively Designed

A well-designed API usually aims for **the object's state to remain unchanged** when an operation is rejected. For example, both `InventoryItem.updateDetails` and `Range.moveTo` are designed that way.

However, **an exception does not automatically roll back** everything. Consider:

~~~java
void unsafeRename(String newName) {
    this.name = newName;
    if (newName == null || newName.isBlank()) {
        throw new IllegalArgumentException("name sai");
    }
}
~~~

This is an illustrative method **with a logic bug**. It assigns an invalid value to the field before throwing the exception, so the invariant can be broken even though the caller receives a failure notification.

If a method writes to a file, emits an event, or updates another object before validation completes, throwing an exception also **does not automatically undo those side effects**.

For a stronger guarantee:

1. Normalize and validate all necessary data first.
2. Precompute values that might overflow or fail.
3. Update state only once steps that can fail have finished.
4. Avoid publishing intermediate state to listeners/other threads.
5. If multiple external resources must change together, use an appropriate transaction/compensation mechanism instead of merely hoping an exception will undo them.

For a class with an invariant spanning multiple fields and shared across multiple threads, the two steps "validate then assign" must be properly protected with synchronization so that no other thread modifies the state between them.

## 19. Concurrency: Correct Validation Is Not Enough If Operations Are Not Atomic

Suppose two threads simultaneously call `sell(7)` on an item with a stock quantity of 10. If the method is not synchronized, both can **read the same value 10**, both pass the "sufficient stock" check, and then overwrite each other's updates. The result is not guaranteed to accurately reflect the total quantity sold.

In the Java Memory Model, `private` does not provide *thread safety*. Making a field private only restricts access from source code; multiple threads can still invoke public instance methods concurrently on the **same object**.

Design approaches depending on the situation:

- Protect **the entire read–check–write sequence** with a consistent lock or `synchronized`.
- For suitable state, use atomic updates or CAS that rechecks the condition.
- Restrict ownership so that a mutable object is modified by only one thread.
- Place business operations requiring durable consistency inside a **storage-layer transaction** when needed.

For example, for an object managing only `quantity` in memory, a `synchronized void sell(int amount)` method covering both validation and updating provides mutual exclusion for calls using the **same monitor**. However, the system must apply synchronization to **every related read/write path**; making a single method `synchronized` alone does not automatically make the entire program thread-safe.

**Do not conflate the two concepts:** an object's invariant under sequential execution and atomicity/visibility under multiple threads are two requirements that must both be considered.

## 20. Immutable Design to Reduce Update Points

Another option is to create an **immutable value object**: an object with no state-mutating operations, where every change is represented by a new value.

Java 17 example:

~~~java
record Temperature(int celsius) {
    Temperature {
        if (celsius < -273) {
            throw new IllegalArgumentException("dưới giới hạn");
        }
    }

    Temperature warmerBy(int delta) {
        int next = Math.addExact(celsius, delta);
        return new Temperature(next);
    }
}
~~~

This is a valid illustrative record. The compact constructor validates the state on every creation. `warmerBy` computes the new value with overflow checking and calls the constructor to re-validate the invariant; the old object is not modified.

A caller wishing to keep the new value must reassign it:

~~~java
Temperature current = new Temperature(20);
current = current.warmerBy(5);
// current.celsius() equals 25.
~~~

For a record containing only primitive types such as `int`, keeping the state immutable is fairly straightforward. For a record containing `List<MutableItem>`, the record itself does not automatically deep-copy mutable components; defensive copying must still be considered.

Immutable objects reduce the number of update points to manage, but do not automatically replace synchronization if multiple threads **reassign a shared reference** in a read–compute–write pattern.

## 21. Testing Validation with a Matrix of Success, Failure, and State Preservation

A useful test needs to verify **three things**: valid cases work correctly; invalid inputs are rejected; and after a failure the object still preserves its invariants.

Matrix for `InventoryItem`:

| Action | Result to verify |
| --- | --- |
| Create with valid SKU, name `"  Bút  "`, stock 10, price 5000 | Creation succeeds; name normalized to `"Bút"` |
| Create with `null` or blank name | `IllegalArgumentException` |
| Create with stock -1 | `IllegalArgumentException` |
| Create with price 0 | `IllegalArgumentException` |
| `receive(5)` from stock 10 | Stock becomes 15 |
| `receive(0)` or `receive(-1)` | Rejected and old stock is preserved |
| `receive(Integer.MAX_VALUE)` with positive stock | `ArithmeticException`, old stock unchanged |
| `sell(3)` when stock is 15 | Stock becomes 12 |
| `sell(99)` when stock is 12 | Rejected, stock remains 12 |
| `updateDetails("Vở",0)` | Rejected and **both old name and old price** remain unchanged |
| `updateDetails("Vở",7000)` | Name and price change as requested |
| Modify mutable data via input reference or getter | Does not corrupt the object if the contract specifies defensive copying |

For `Range`, check `start<0`, `end<start`, two equal values, and boundaries like `Integer.MAX_VALUE` when calculations occur.

### Some Direct Java Checks

No testing library is needed to understand the principle, for instance:

~~~java
Range range = new Range(2, 5);
if (!"[2,5]".equals(range.describe())) {
    throw new AssertionError("trạng thái ban đầu sai");
}
try {
    range.moveTo(9, 3);
    throw new AssertionError("phải từ chối khoảng sai");
} catch (IllegalArgumentException expected) {
    if (!"[2,5]".equals(range.describe())) {
        throw new AssertionError("thất bại nhưng trạng thái đổi");
    }
}
~~~

This is a runnable illustrative snippet when placed in a method alongside the `Range` definition from section 8. It verifies both the **expected exception** and the state after the exception. In a real project, you can use JUnit's `assertThrows`, `assertEquals`, and boundary tests, yet the essence of what needs to be verified does not change.

**Do not merely check that the constructor/setter does not throw an error.** A buggy method such as `quantity = quantity;` can execute normally without updating the field; therefore, you must **read back the resulting state**.

## 22. Common Mistakes

| Mistake | Consequence | How to improve |
| --- | --- | --- |
| Validating only in the constructor while setters assign directly | An object starts valid and later becomes invalid | Share the same rules across all update paths |
| Validating only in the UI | Calls from other APIs/tasks can bypass it | Domain objects protect their own invariants |
| Assuming `private` automatically rejects invalid values | Fields can still receive invalid values through unvalidated methods | Validate in public behaviors |
| Assigning fields first and validating afterward | Fails yet leaves the object modified | Validate/compute first, then assign |
| Updating two fields via two setters when a cross-field invariant exists | Intermediate state may become invalid | Provide a grouped update operation |
| Not checking for overflow | The new value may overflow and fall out of range | Use `Math.addExact`/`multiplyExact` when appropriate |
| Directly exposing an internal array/list via a getter | Callers can mutate it without going through methods | Defensive copy or query API |
| Storing a caller-supplied list/array directly | Caller mutates it after the constructor and breaks invariants | Copy on receipt; validate elements |
| Believing `final List` means an immutable list | Final only locks the field reference | Protect mutable child objects |
| Catching exceptions and silently ignoring them | Callers assume the update succeeded | Define a clear error contract |
| Allowing subclasses to override update logic arbitrarily | Superclass invariants may be broken | Design for inheritance or use `final` |
| Calling an overridable method from a constructor | Subclass is not yet fully initialized | Avoid dynamic dispatch in constructors |
| Assuming a two-line check-and-write is atomic across threads | Execution may interleave or lose updates | Appropriate locking/atomic updates |
| Handling every error in setters | Some rules span multiple objects/transactions | Place them in the appropriate business/storage layer |
| Testing only that an error occurs without checking post-error state | Fails to detect partial updates | Verify invariants and state preservation |

## 23. Practice Exercises

**Question 1 — Invariant.** A `BankAccount` class has `private long balance` and requires `balance >= 0`. Which paths need validation if it has a constructor, `deposit`, `withdraw`, and `setBalance`?

**Question 2 — Creation.** The constructor `Product(String name,int stock)` writes `this.name=name; this.stock=stock;` without validation. Add the rules for a non-blank name and non-negative stock, and explain where validation must be called.

**Question 3 — Post-update state.** Stock is 5. `sell(7)` has a positive parameter. Why must it still be rejected? After the failure, what must the stock quantity be if the API guarantees no state change on error?

**Question 4 — Overflow.** When `quantity=20`, what can adding `Integer.MAX_VALUE` using `quantity += amount` cause? Why is using `Math.addExact` before assigning the field safer?

**Question 5 — Multi-field update.** Given `start=2,end=5`, you want to change it to `start=7,end=9`. Why might `setStart(7)` be temporarily rejected even though the final target is valid? Suggest a new design.

**Question 6 — Defensive copying.** The `Scores` class directly keeps the `int[] scores` passed into its constructor. The caller later modifies `scores[0]=-1`. Why does `private final int[]` not prevent this?

**Question 7 — Getter.** What modification path can `List<String> getTags() { return tags; }` expose? When is `List.copyOf(tags)` useful, and what are its limitations?

**Question 8 — Exception types.** When receiving the parameter `amount=-3` and when an object is already `CLOSED` yet the caller invokes `edit`, which error types do these two cases usually belong to?

**Question 9 — Inheritance.** Why must a class that allows subclasses to override validation/update methods establish a stricter contract than a `final` class?

**Question 10 — Concurrency.** Two threads sell items concurrently on the same object. Why does both of them passing `if (amount <= quantity)` not prove that the total quantity sold is valid?

**Question 11 — Immutable object.** Given `record Temperature(int celsius)` with an invariant, why should `warmerBy` create a new value through the validated constructor? How does the caller retain the result?

**Question 12 — Layering.** Can "the item code is unique in the database" be guaranteed solely by using the constructor? Where should the constraint be placed?

### Reference Answers

1. The constructor and **every update operation** must protect `balance>=0`; `deposit` checks for positive amount/overflow, `withdraw` checks for sufficient balance, and `setBalance`, if it exists, must require non-negative values.
2. Check `name != null`, `!name.isBlank()`, and `stock>=0` before accepting the state; reapply them along every corresponding modification path.
3. Because `sell` depends on both the parameter and the current stock quantity; it must reject the call and keep stock at 5.
4. `int` addition can overflow and produce an incorrect value; `Math.addExact` detects overflow before assigning to the field.
5. Calling `setStart(7)` alone makes `start > end` while `end` is still 5; use `moveTo(7,9)` to validate the pair and then update.
6. The field holds a reference to the **same array**; `final` does not lock elements. Use clone/copy, and copy on return if needed.
7. The caller can `add`/`clear` the internal list without going through validation; `List.copyOf` creates an unmodifiable list, though it does not deep-copy mutable elements.
8. An invalid parameter is usually `IllegalArgumentException`; an operation invalid for the object's state is usually `IllegalStateException`.
9. Because a subclass can alter the implementation and break invariants; a clear override contract is needed, or `final` on operations that must not be changed.
10. The read–check–write sequence is not automatically atomic across threads; appropriate locking or atomic updates are required.
11. The constructor re-validates the invariant for every new value; a caller wishing to apply it assigns `current=current.warmerBy(delta)`, while the old object remains unmodified.
12. No. Validation in the business layer and appropriate unique constraints/transactions in the persistent data store are needed.

## 24. References

- [Java Language Specification 17, §8.3 — Field Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): instance fields, `private`, `final`, and declaration rules.
- [Java Language Specification 17, §8.8 — Constructor Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.8): constructors and object initialization.
- [Java Language Specification 17, §15.9 — Class Instance Creation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9): instance creation semantics.
- [Java SE 17 API — Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(int,int)): overflow detection for integer addition.
- [Java SE 17 API — String.isBlank](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#isBlank()): determining whether a string is empty or contains only whitespace.
- [Java SE 17 API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable lists and copy semantics.
- [Java Language Specification 17, §17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): the memory model and synchronization requirements when sharing mutable state.

**Key takeaway:** effective encapsulation protects invariants at **two mandatory points**: **initialization** and **every update**. Keep fields private, validate both parameters and the **resulting state**, validate everything before assigning, protect mutable data accessed via references, and test that failed operations **do not corrupt the object**. If multiple threads or multi-object transactions are involved, appropriate consistency mechanisms must be added; validation inside a single method alone is not enough.
