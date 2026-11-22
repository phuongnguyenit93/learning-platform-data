# Preconditions, Postconditions, and Side Effects of Methods in Java

A Java method can accept data, perform calculations, return a result, and modify state during execution. To use a method correctly, knowing only its name and data types in the signature is not enough: the caller also needs to know its **preconditions**, **postconditions**, and **side effects**. These three concepts form an important part of a **method contract**.

This lesson uses Java 17 or later and focuses on how to design, implement, use, and test a method's contract. The examples include standalone runnable programs, and the results are explained in execution order.

## 1. What “Contract” Does a Method Have?

Consider the requirement “reserve a quantity of items currently in stock.” We can describe the method in words:

- **Input:** the quantity to reserve is a positive integer that does not exceed the currently available stock.
- **Output on success:** the method returns the remaining quantity available for sale.
- **Side effect:** decreases the quantity available for sale and increases the reserved quantity.
- **When input is invalid:** rejects the operation with an exception and leaves the inventory state unchanged.

The description above adds meaning that the following signature alone cannot fully express:

~~~java
int reserve(int quantity)
~~~

The signature shows that a method named `reserve` takes an `int` and returns an `int`; it **does not by itself specify** whether `quantity` must be positive, whether the inventory count changes, or how errors are handled.

One way to remember this:

| Concept | Question to answer | Example |
| --- | --- | --- |
| Precondition | What must be true at the **start** of the call? | `quantity > 0`, `quantity <= available` |
| Postcondition | What is guaranteed **after normal completion**? | Returns the remaining quantity, non-negative |
| Side effect | Besides the return value, what state or environment is affected? | Both fields `available` and `reserved` change values |
| Behavior on failure | What error occurs, and does the data remain intact? | Throws `IllegalArgumentException`, inventory count unchanged |

**Important:** a postcondition is typically guaranteed only under the cases specified by the contract, such as when the inputs are valid and the method **completes normally**. You must distinguish the state after success from the state after throwing an exception; not every Java method automatically “rolls back” when an error occurs.

## 2. Preconditions

A **precondition** is a requirement that the caller or system must satisfy before the method performs its promised work. For example:

~~~java
double divide(double numerator, double denominator) {
    if (denominator == 0.0) {
        throw new IllegalArgumentException("Mẫu số không được bằng 0");
    }
    return numerator / denominator;
}
~~~

*This is a method snippet inside a class; it is not a standalone program.* The contract in this example requires `denominator != 0.0`. Java allows floating-point division by 0 to produce `Infinity` or `NaN` depending on the case, but **this method itself** chooses to reject inputs with a zero denominator.

Preconditions can relate to:

1. **Value bounds:** positive quantity, non-negative age, index within a valid range.
2. **Nullability:** a reference that must be non-`null`, such as `Objects.requireNonNull(path)`.
3. **Format and semantics:** non-empty item code, string in a matching format, value belonging to an allowed set.
4. **Current object state:** sufficient stock to reserve, object already opened, resource not yet closed.
5. **Relationships between parameters:** `start <= end`, data size compatible with allowed limits.

### Who Is Responsible for Ensuring Preconditions?

The caller is responsible for **providing inputs that satisfy the contract**. The method author should guard important rules with validation checks at appropriate public boundaries, especially when inputs may come from outside.

For example:

~~~java
static int percent(int part, int total) {
    if (total <= 0) {
        throw new IllegalArgumentException("Tổng phải dương");
    }
    if (part < 0 || part > total) {
        throw new IllegalArgumentException("Phần phải nằm trong [0, tổng]");
    }
    return (int) ((100L * part) / total);
}
~~~

*This is an illustrative method snippet without `main`.* The multiplication `100L * part` uses `long` to avoid overflow within the validated non-negative `int` range; integer division rounds toward zero, which here is equivalent to taking the integer part. The contract should clarify this rounding behavior if it matters to the caller.

You should not check preconditions only at an input screen and leave the processing method unguarded: the same method may be called from tests, APIs, batch jobs, or other parts of the program.

### Choosing How to Reject Input

In Java, common choices include:

- `IllegalArgumentException`: an argument value is invalid according to the contract.
- `NullPointerException` or `Objects.requireNonNull(...)`: a required argument must be non-`null`.
- `IllegalStateException`: the **object state** does not permit performing the operation, even though the parameters may be valid.
- A result value such as `boolean`, `Optional<T>`, or a domain result type: when “not found” or “cannot be performed” is a **normal** case designed into the API, rather than a contract-usage error.

There is no rule that every input failing to meet requirements must use the exact same exception type. What matters is that the API has a **clear and consistent contract** so the caller knows how to handle it.

## 3. Postconditions

A **postcondition** describes what the method guarantees **once it has finished along the success path**. It includes both the return value and the observable state if the method is allowed to mutate data.

Example with inventory:

~~~text
Before reserve(4):
    available = 10
    reserved  = 0

After reserve(4) succeeds:
    available = 6
    reserved  = 4
    return    = 6
~~~

Written in shorthand notation, letting `old(x)` denote the value **before the call**:

~~~text
pre:  quantity > 0
      quantity <= old(available)

post: available == old(available) - quantity
      reserved  == old(reserved) + quantity
      result    == available
~~~

These lines are an **illustrative specification**, not Java syntax enforced by the compiler. Java has no `old` keyword in regular source code.

### How Does a Postcondition Differ from a Return Type?

`int reserve(int quantity)` only requires the returned result to have a type compatible with `int`. It does not enforce that the result equals the remaining quantity of items. The promise `return == available` is a **business rule** defined, implemented, tested, and documented by the method author.

If a method returns `void`, it can still have a postcondition:

~~~java
void reset() {
    count = 0;
}
~~~

This is a method snippet inside a class with a `count` field; the contract upon success is `count == 0`, even though **there is no return value**.

A read-only method also has a postcondition without modifying state: for example, `size()` returns the exact number of elements observed at the time of reading. You should avoid promising that a value remains unchanged forever after the method returns if the object can be modified by another thread.

## 4. Side Effects

A **side effect** is an observable change beyond simply returning a value to the caller. In Java, common examples include:

| Behavior | Has side effect? | Explanation |
| --- | --- | --- |
| `return a + b;` with two `int` values | No, if there are no other operations | Only computes and returns a value |
| `this.balance += amount;` | Yes | Changes the state of the receiving object |
| `list.add(value);` | Yes | Modifies a `List` object that the caller may still hold |
| `sharedCount++;` with a `static` field | Yes | Changes shared class-level state |
| `System.out.println(text);` | Yes | Writes to the output stream |
| `Files.writeString(path, text);` | Yes | May alter data on the file system |
| Sending an HTTP request or saving to a database | Possibly | Affects external resources/systems |
| `new StringBuilder("A")` solely for internal computation | Typically no externally observable side effect | Creating a private temporary object does not equate to modifying external state |

Exceptions can alter control flow and are part of the **outcomes** that a method must describe. However, throwing an exception does not necessarily mean data has been modified; if fields or files were written before the exception was thrown, those changes may remain.

### References Allow Side Effects to Reach the Caller

Java passes arguments **by value**. If an argument has a reference type, the copied reference value can point to the **same object** as the caller's variable. Therefore:

~~~java
static void addName(java.util.List<String> names) {
    names.add("An");
}
~~~

*This is an illustrative method snippet without `main`.* The method **cannot** make the `names` variable in the caller automatically change to another reference by reassigning the parameter, but it **can** modify the list object that both sides point to. This is a very common source of side effects.

You need to distinguish between:

- **Changing the local parameter variable:** `names = new ArrayList<>();` only changes the `names` variable inside the method.
- **Modifying the referenced object:** `names.add("An");` modifies the actual list that was passed in, provided the list supports modification.
- **Returning a mutable object:** the caller can modify the object after the method finishes; you should check whether this is internal data suffering from “reference exposure”.

## 5. Complete Example: Checking Contracts When Reserving Inventory

We create a `StockItem` class to manage the quantity available for sale (`available`) and the reserved quantity (`reserved`). One object represents one item code. Valid state requires both quantities to be **non-negative**.

The `reserve(quantity)` method has the following contract:

- **Precondition:** `quantity > 0` and does not exceed the quantity available for sale.
- **Postcondition on success:** the quantity available for sale decreases by `quantity`, the reserved quantity increases by `quantity`, and the returned result is the new `available`.
- **Side effect:** modifies two instance fields of the receiving object.
- **On controlled failure:** throws `IllegalArgumentException` before any updates; both fields remain unchanged.

The `release(quantity)` method performs the reverse operation, but may only release a reserved quantity that actually exists.

Create the file **`MethodContractDemo.java`**:

~~~java
record StockSnapshot(String sku, int available, int reserved) {
}

class StockItem {
    private final String sku;
    private int available;
    private int reserved;

    StockItem(String sku, int initialAvailable) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("Mã hàng không hợp lệ");
        }
        if (initialAvailable < 0) {
            throw new IllegalArgumentException("Số lượng không được âm");
        }
        this.sku = sku;
        this.available = initialAvailable;
        this.reserved = 0;
    }

    boolean canReserve(int quantity) {
        return quantity > 0 && quantity <= available;
    }

    int reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (quantity > available) {
            throw new IllegalArgumentException("Không đủ hàng");
        }

        available -= quantity;
        reserved += quantity;
        return available;
    }

    void release(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Số lượng phải dương");
        }
        if (quantity > reserved) {
            throw new IllegalArgumentException("Chưa giữ đủ hàng");
        }

        reserved -= quantity;
        available += quantity;
    }

    StockSnapshot snapshot() {
        return new StockSnapshot(sku, available, reserved);
    }
}

public class MethodContractDemo {
    public static void main(String[] args) {
        StockItem item = new StockItem("BOOK-01", 10);
        StockSnapshot before = item.snapshot();

        System.out.println("Trước: " + before);
        System.out.println("Có thể giữ 4: " + item.canReserve(4));

        int remaining = item.reserve(4);
        System.out.println("Giá trị trả về: " + remaining);
        System.out.println("Sau giữ: " + item.snapshot());

        try {
            item.reserve(7);
        } catch (IllegalArgumentException ex) {
            System.out.println("Từ chối: " + ex.getMessage());
        }
        System.out.println("Sau lỗi: " + item.snapshot());

        item.release(2);
        System.out.println("Sau giải phóng: " + item.snapshot());
        System.out.println("Ảnh chụp cũ: " + before);
    }
}
~~~

From the directory containing the file, compile and run:

~~~bash
javac -encoding UTF-8 MethodContractDemo.java
java MethodContractDemo
~~~

Exact stdout:

~~~text
Trước: StockSnapshot[sku=BOOK-01, available=10, reserved=0]
Có thể giữ 4: true
Giá trị trả về: 6
Sau giữ: StockSnapshot[sku=BOOK-01, available=6, reserved=4]
Từ chối: Không đủ hàng
Sau lỗi: StockSnapshot[sku=BOOK-01, available=6, reserved=4]
Sau giải phóng: StockSnapshot[sku=BOOK-01, available=8, reserved=2]
Ảnh chụp cũ: StockSnapshot[sku=BOOK-01, available=10, reserved=0]
~~~

### Tracing the State

| Point in time | `available` | `reserved` | Explanation |
| --- | ---: | ---: | --- |
| After constructor | 10 | 0 | Valid initial state |
| After `canReserve(4)` | 10 | 0 | Only computes a `boolean`, does not modify state |
| After `reserve(4)` | 6 | 4 | Succeeds and returns `6` |
| After `reserve(7)` | 6 | 4 | Throws an exception before any update |
| After `release(2)` | 8 | 2 | Moves 2 units from reserved back to available |

In every **successful** `reserve`/`release` operation in this sequential model, the sum `available + reserved` stays constant. The constructor starts with a sum that does not exceed `Integer.MAX_VALUE`; because quantities are transferred between the two groups with boundary checks, addition in these operations cannot overflow when state is only created and updated through the defined API itself.

`StockSnapshot` is a Java 17 **record**. The components in this example consist of an immutable `String` and two `int` values, so the snapshot object is not modified when `StockItem` later changes state. This is why the “Ảnh chụp cũ” line still prints the initial values. If a record contains a mutable `List`, the record does not automatically create a deep copy of that list.

### Why Does the Order of Checks Matter?

In `reserve`, all checks appear **before** the two updates:

~~~java
available -= quantity;
reserved += quantity;
~~~

If the input is invalid, the method throws an exception before touching the state. This is a useful guarantee of the current API. If the order were reversed—subtracting from `available` first and checking inventory afterward—a failure could leave the object in an invalid state.

**Limitation:** the two assignments here are not an atomic transaction in a multithreaded program or database. If two threads modify the same `StockItem` concurrently, additional concurrency protection is needed; if moving to persistent storage, an appropriate transaction design is required.

## 6. How Do Postconditions and Invariants Differ?

A **postcondition** describes the outcome of **a single call**; an **invariant** describes a rule that must be maintained for the valid state of an object.

In `StockItem`:

- **Invariant:** `available >= 0`, `reserved >= 0`.
- **Postcondition of `reserve(q)`:** the new `available` equals the old `available` minus `q`, the new `reserved` equals the old `reserved` plus `q`, and the returned result equals the new `available`.
- **Postcondition of `release(q)`:** the new `reserved` equals the old `reserved` minus `q`, and the new `available` equals the old `available` plus `q`.
- **Postcondition of `canReserve(q)`:** returns `true` precisely when `q > 0` and `q <= available`; does not modify state.

In this lesson, `canReserve` is intentionally designed to accept non-positive numbers as well and return `false` instead of throwing an exception, whereas `reserve` treats a non-positive request as a **contract violation**. The two methods serve different purposes, so their behavior for the same input data does not have to be identical, as long as it is clearly documented.

Do not assume that preconditions relate only to parameters. For example, a `close()` method might require the resource to be open; if the state is already closed, even a method with no parameters may not be permitted to be called again according to the contract.

## 7. Designing Methods Without Side Effects: Pure Functions

A **pure function**, in the common sense, produces the same result for the same inputs and causes no observable side effects. In Java, many useful `static` methods can be written in this style:

~~~java
static int shippingFee(int distanceKm, int feePerKm) {
    if (distanceKm < 0 || feePerKm < 0) {
        throw new IllegalArgumentException("Giá trị không được âm");
    }
    return Math.multiplyExact(distanceKm, feePerKm);
}
~~~

*This is an illustrative method declaration inside a class without `main`.* Given two valid inputs, the method only computes and returns the result; it does not modify fields, parameters, or the external environment. `Math.multiplyExact` throws `ArithmeticException` if the `int` multiplication exceeds the representable range; the “non-negative” precondition **does not guarantee** that the product always fits in an `int`.

Benefits of limiting side effects:

- Easy to reason about the result and test using an input/output table.
- Easy to reuse because it does not depend on hidden state.
- Easy to compose in other calculations without worrying about unintended object mutations.
- In many situations, reduces the portion of state that must be protected during concurrent execution.

However, real-world programs still need operations with side effects, such as updating a shopping cart, writing files, or sending data. The goal is to **clearly define, limit, and control side effects**, not eliminate them at all costs.

A `static` method is **not pure by default**: it can still modify a `static` field, mutate a passed-in list, or write to a file. Conversely, an instance method can simply read fields and return a result without causing any state changes, such as `snapshot()` in the example above (with respect to `StockItem`'s state; it creates a new result object).

## 8. Second Example: Side Effects on a Mutable Parameter

Many real-world bugs happen because a method mutates an object passed in by the caller, even though its signature looks like a utility function.

Create the standalone file **`SideEffectDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class SideEffectDemo {
    static void sortInPlace(List<String> names) {
        Collections.sort(names);
    }

    static List<String> sortedCopy(List<String> names) {
        List<String> copy = new ArrayList<>(names);
        Collections.sort(copy);
        return copy;
    }

    public static void main(String[] args) {
        List<String> original = new ArrayList<>(List.of("Binh", "An"));

        List<String> result = sortedCopy(original);
        System.out.println("Bản gốc: " + original);
        System.out.println("Bản sao: " + result);

        sortInPlace(original);
        System.out.println("Sau sửa tại chỗ: " + original);
    }
}
~~~

~~~bash
javac -encoding UTF-8 SideEffectDemo.java
java SideEffectDemo
~~~

Stdout:

~~~text
Bản gốc: [Binh, An]
Bản sao: [An, Binh]
Sau sửa tại chỗ: [An, Binh]
~~~

**`sortInPlace`** has a side effect: it modifies the order of the very list passed in by the caller. The contract should clearly state that the list must be **mutable** and support `set`/element modifications required for sorting; if an immutable list or one that does not support the operation is passed, the method may fail.

**`sortedCopy`** creates a new list using `new ArrayList<>(names)` and then sorts the copy. It does not change the order of the input list and returns the resulting list. Because the list holds immutable `String` objects, copying the elements does not introduce shared mutable element issues in this example. With `List<MutableObject>`, the copied list is a **shallow copy**: the element objects themselves can still be shared.

### Which API Should You Choose?

If the goal is to **modify the caller's data**, a name like `sortInPlace`, documentation stating “modifies the input list”, and a `void` return type convey the intent fairly clearly. If the goal is to return a new ordering without mutating the input data, `sortedCopy` has a more suitable contract. In both cases, `null` checks and ordering rules should be made explicit in a real-world API.

## 9. Distinguishing Return Values, Output Data, and Side Effects

Not all “output” comes from `return`.

~~~java
static int twice(int value) {
    return value * 2;
}

static void announce(int value) {
    System.out.println(value);
}
~~~

These are two illustrative methods, not a standalone program:

- `twice(3)` **returns** `6`; the caller can write `int result = twice(3);`. Multiplying `int` values can overflow for large inputs; if the contract requires exact calculation, this must be handled.
- `announce(3)` **prints** `3` to stdout but has a `void` return type. The caller cannot write `int result = announce(3);`.

Output can also take the form of a modification to a passed-in object, a file written, an event emitted, or state saved to a database. If an API has such side effects, the documentation must clearly describe: which data is modified, what errors may occur, and whether data is preserved after an error.

A method that returns a `List` is not pure by default; it could both update a database and return a list. Conversely, a method returning `void` does not by itself prove that it has a side effect; an empty method `void noop() {}` does nothing observable.

## 10. Documenting Contracts with Javadoc

Javadoc helps readers understand usage requirements and guarantees after a call. The following example is a **code snippet used inside the `StockItem` class**, replacing the documentation placed before the `reserve` method:

~~~java
/**
 * Reserves stock for a request.
 *
 * @param quantity the quantity must be positive and must not exceed the quantity available for sale
 * @return the quantity available for sale after a successful reservation
 * @throws IllegalArgumentException if quantity is invalid
 *
 * Side effect: available decreases by quantity and reserved increases by quantity.
 * When rejected due to invalid data, the state remains unchanged.
 */
int reserve(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException("Số lượng phải dương");
    }
    if (quantity > available) {
        throw new IllegalArgumentException("Không đủ hàng");
    }
    available -= quantity;
    reserved += quantity;
    return available;
}
~~~

`@param`, `@return`, and `@throws` are standard Javadoc tags. The “Side effect” explanation line here is ordinary documentation text, not a keyword automatically checked by Java.

You can use `@throws` multiple times if you need to document different exception types. If a method returns `void`, `@return` is usually not needed. When the contract is more complex, also describe failure cases, resource state, data ownership, and support for concurrent use.

Javadoc is not a contract-enforcement mechanism. The compiler primarily checks syntax, types, access control, and language rules; conditions like `quantity > 0` must be checked in code or guaranteed through type/API design, and must be tested.

## 11. Verifying Preconditions, Postconditions, and Side Effects

A useful test suite must verify **both the return value and the object state**, not merely check that the method does not throw an exception.

For `StockItem("BOOK-01", 10)`, the main cases are:

| Case | Expected result | Resulting state |
| --- | --- | --- |
| `canReserve(4)` | `true` | Still 10 available, 0 reserved |
| `reserve(4)` | Returns `6` | 6 available, 4 reserved |
| `reserve(0)` immediately after | `IllegalArgumentException` | Still 6 and 4 |
| `reserve(7)` immediately after | `IllegalArgumentException` | Still 6 and 4 |
| `release(2)` afterward | Completes normally | 8 available, 2 reserved |
| `release(3)` afterward | `IllegalArgumentException` | Still 8 and 2 |

When writing JUnit tests, the corresponding checks can use `assertEquals`, `assertThrows`, and **before/after** snapshot comparisons. For simple examples, a `main` program that prints results also helps with learning, but automated tests should assert the promised conditions rather than relying solely on console observation.

It is especially important to test **boundary values**: `0`, `1`, exact current stock, one unit above current stock, `null`, blank strings, and values near `Integer.MAX_VALUE` or `Long.MAX_VALUE` when arithmetic is involved.

### Checking Properties by Comparing Against Previous State

Given a prior state `(a, r)` and `0 < q <= a`, a successful `reserve(q)` call must yield:

~~~text
newAvailable == a - q
newReserved  == r + q
result       == newAvailable
newAvailable >= 0
newReserved  >= 0
~~~

This is a **test specification**, not standalone Java code. A test can capture a snapshot beforehand, call the method, and then capture a snapshot afterward to verify each condition. If an operation fails under a case specified as “state unchanged”, you should compare both fields before and after the exception.

## 12. Note: Exceptions Do Not Roll Back Side Effects by Default

Look at the following method snippet, which is **intentionally flawed by design**:

~~~java
void unsafeReserve(int quantity) {
    available -= quantity;
    if (available < 0) {
        throw new IllegalArgumentException("Không đủ hàng");
    }
    reserved += quantity;
}
~~~

This snippet assumes it is placed inside a class with `available` and `reserved` fields; it **should not be used as a real API**. If `available = 6` and `unsafeReserve(7)` is called, the first statement sets `available = -1`, and then the method throws an exception. The exception **does not automatically reset available back to 6**.

Even when inputs are validated up front, a method performing multiple file writes, API calls, or database saves can still fail **midway between side effects**. Therefore, you should distinguish:

- **Basic guarantee:** invariants are still preserved after an error, though part of the state may have changed.
- **Strong guarantee:** if the operation fails, the observable state is kept as it was before the call.
- **Transactional guarantee:** a group of changes is committed or rolled back according to the corresponding transaction mechanism; in distributed systems, boundaries, consistency, and error handling must also be defined.

These are **implementation-design guarantee** levels, not three modes that Java automatically provides for every method. For `reserve` in our example, the preconditions are checked before assignments, so the stated input errors are handled without modifying state, within a sequential context and without external field mutation.

## 13. Mutable Data, Defensive Copying, and Output Guarantees

If you want a method to only provide **information**, carefully consider whether it returns a reference to internal data. For example, if a class has `private final List<String> names;`, the following method does not make a copy:

~~~java
List<String> names() {
    return names;
}
~~~

This is a snippet inside an illustrative class and cannot compile on its own. If `names` is a modifiable list and the caller has access to the returned reference, they can write `object.names().clear()` to mutate internal data without going through the intended update method.

One option for data meant for reading is:

~~~java
List<String> namesSnapshot() {
    return List.copyOf(names);
}
~~~

`List.copyOf` returns a list that **does not support modification through its API** and does not accept `null` elements. It captures the element references at the time of the call and **does not automatically deep-copy** mutable objects inside. If the contract requires an independent snapshot of mutable child objects, you must consider deep copying or using immutable value types.

The same issue exists on the **input** side: storing a `List` passed by the caller directly into a constructor allows the caller to modify that list later and affect the state of the object holding the list. Reference ownership should be explicitly documented in the contract.

## 14. Multiple Threads Complicate Contracts

In a single-threaded example, `canReserve(4)` returning `true` means `reserve(4)` can subsequently succeed if no other operation intervenes. With multiple threads, **checking beforehand does not guarantee the subsequent operation remains valid** if another thread has modified the stock.

~~~text
Thread A: canReserve(4) -> true
Thread B: reserve(8)    -> success
Thread A: reserve(4)    -> may be rejected because it is out of stock
~~~

The lines above represent a conceptual scenario when the initial state has enough stock for one of the two reservations, not the exact execution result of the current code under unsynchronized access. The `StockItem` class is **not yet thread-safe**: if shared across multiple threads, data race bugs can render checks and updates unreliable. To demonstrate a real concurrent scenario, you must use a version whose concurrent accesses are protected by an appropriate mechanism.

In concurrent design, you must re-specify:

- **At what point in time** are preconditions checked?
- Is the read–check–write sequence executed **as a single atomic step**?
- Which state, and at what point in time, does the return value reflect?
- Do post-success guarantees still hold under concurrent operations?

This is why the contract of a method operating on shared data cannot merely state “read then write”; synchronization and consistency responsibilities must be clearly specified when the application scope requires it.

## 15. Common Mistakes

| Misconception | Consequence | Correct understanding |
| --- | --- | --- |
| “Type `int` means any input is valid” | Passing 0, negative numbers, or exceeding business limits | Preconditions are usually stricter than the Java type |
| “`return` tells the whole story of the output” | Overlooking updates to fields, lists, or files | Also examine side effects and resulting state |
| “A `void` method has no outcome” | Forgetting to describe state changes | `void` methods can still have postconditions |
| “Throwing an exception automatically reverts data to its previous state” | The object ends up partially modified | Validate and prepare before updating, or use an appropriate rollback mechanism |
| “A `static` method is always pure” | Missing modifications to static variables or shared resources | Purity depends on overall behavior, not the `static` keyword |
| “Using `final` on a parameter makes the object immutable” | Mutable lists/objects can still be modified | `final` only prevents reassigning the parameter variable |
| “Returning a `List` only lets the caller read it” | The caller mutates the internal collection | Consider copies, immutable views, and data ownership |
| “Checking conditions once on the outside is enough” | State may change before the operation runs | Check where the rule is enforced and synchronize when needed |
| “Invalid input only needs to be handled with `System.out.println`” | The caller has no structured way to know the operation failed | Design clear exceptions or result values |
| “Not throwing an error means the postcondition holds” | Faulty logic can still return or store wrong results | Test both the return value and the observable state |

## 16. Process for Designing a Method with a Clear Contract

Before writing code for a new method, follow these steps in order:

1. **State the purpose:** for example, “reserve available stock” rather than a generic name like `update`.
2. **Define the inputs:** data types, whether `null` is allowed, value ranges, and conditions tied to current state.
3. **Define success:** the return value and which state must change (or remain unchanged).
4. **Define side effects:** fields, collections, files, console, database, network, or passed-in objects.
5. **Define failure:** error scenarios, exception types/result types, and the level of state preservation.
6. **Write code that validates before mutating:** prepare values that could fail before making hard-to-reverse updates.
7. **Document the contract:** use descriptive names, Javadoc, appropriate data types, and access constraints.
8. **Test boundaries and exceptions:** compare return values, before/after state, and observable side effects.
9. **Consider concurrency:** if multiple threads may operate concurrently, protect the rules with the right mechanism.

A very useful question during code review is: **“If this method is rejected on its last line, what has already changed before that?”** The answer helps uncover the risk of uncontrolled side effects.

## 17. Self-Practice Exercises

**Exercise 1 — Identify the contract.** Given the method:

~~~java
int withdraw(int amount) {
    if (amount <= 0 || amount > balance) {
        throw new IllegalArgumentException("Không thể rút");
    }
    balance -= amount;
    return balance;
}
~~~

Assume this is an instance method in a class with an `int balance` field that is kept non-negative. State the precondition, postcondition on success, side effect, and behavior on failure.

**Exercise 2 — Pure or side-effecting?** Classify `int doubleValue(int x) { return x * 2; }`, `void add(List<String> xs) { xs.add("A"); }`, and `String upper(String x) { return x.toUpperCase(); }` (for non-`null` inputs). Can a method avoid modifying objects yet still be impure if it reads the current time or external state?

**Exercise 3 — Spot the bug.** Given the code:

~~~java
void give(int quantity) {
    reserved -= quantity;
    if (quantity <= 0 || reserved < 0) {
        throw new IllegalArgumentException();
    }
    available += quantity;
}
~~~

Point out what is wrong with the order of checks and the state upon failure. Rewrite it so that `quantity > 0` and `quantity <= reserved` are checked **before** updating.

**Exercise 4 — Passed-in list.** If a method calls `Collections.sort(list)` on a `list` received as a parameter, does the change appear on the caller's side? If instead it creates `new ArrayList<>(list)` and sorts the copy, what is different?

**Exercise 5 — Snapshot.** Why does `StockSnapshot before = item.snapshot()` in the example still hold the old quantities after `item.reserve(4)`? If the snapshot contained a mutable list also held by the item, would the independence guarantee still hold completely?

**Reference hints:**

1. Precondition: `0 < amount <= balance`; after success, `balance` decreases by `amount` and the return value is the new balance; the side effect is modifying the `balance` field; if the input is invalid, an exception is thrown before any update.
2. Doubling an `int` and uppercasing a `String` are computations that cause no side effects in the example; adding to a `List` does. Reading the current time or mutable external state can make results inconsistent even without writing data.
3. Subtracting from `reserved` happens before the check, which can leave a negative value after an error. Check both conditions first, and only then run `reserved -= quantity; available += quantity;`.
4. Sorting in place mutates the same list object; sorting a copy does not change the source list's order, though the element objects themselves may still be shared.
5. A record containing a `String` and primitives is a separate representation of the read data; a record does not deep-copy mutable child objects.

## 18. References

- [Java Language Specification 17, §8.4 — Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4): declarations, return types, parameters, method bodies, and exceptions.
- [Java Language Specification 17, §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): method invocation semantics and argument passing.
- [Oracle Java API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#requireNonNull(T)): checking that a required argument is non-null.
- [Oracle Java API — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): creating a list that does not support modification through its API and related limitations.

**Key takeaway:** a precondition describes what must be true **before** a successful call; a postcondition describes what is guaranteed **after** a successful execution; a side effect tells you **which objects or environment change** beyond the return value. A reliable method should clearly document all three and exhibit failure behavior consistent with its promised contract.
