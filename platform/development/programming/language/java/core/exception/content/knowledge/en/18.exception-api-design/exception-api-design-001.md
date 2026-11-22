# Defining Valid State Before and After Method Failure

A Java API does not only need to return the right result when it **succeeds**. When a call throws an exception partway through, is the object still usable? Which fields are allowed to change? Are resources closed? Can the caller retry? Has an operation that wrote data to a file, database, or external service actually been rolled back?

The topic **"Defining Valid State Before and After Method Failure"** is at the core of predictable API design. It combines **invariants**, **preconditions**, **postconditions**, **exceptional postconditions**, **exception safety guarantees**, resource management, and failure-path testing.

For example, consider calling `wallet.withdraw(200)` from a wallet that only has 100 units:

- Did the caller violate a precondition? If so, what type of exception does the method throw?
- After throwing, is the balance still 100, or has it been changed to a negative value?
- If the method already sent an external payment request before failing, can it assert that the transaction did not happen?
- If a retry is needed, must the caller fix the input, fix the state, or verify side effects first?

A **good contract** clearly states the state **before the call**, the state **after success**, and the state **after failure**. The `throws` syntax or having a `catch` block **does not automatically provide** those guarantees.

The examples focus on Java 17+, are self-contained, and include run commands/stdout when marked as complete programs. Illustrative snippets are clearly noted; not all of them can run on their own.

## 1. Three layers of a contract: before, after success, after failure

Consider a state-mutating method:

```java
account.withdraw(amount);
```

This is an **illustrative call**; variables and classes need to be defined. A contract should separate:

1. **Precondition:** what the caller must satisfy before calling. For example, `amount > 0`.
2. **Normal postcondition:** if the method returns normally, what is true? For example, the balance decreases by exactly `amount`.
3. **Exceptional postcondition:** if the method throws an exception, what is still guaranteed? For example, the balance is unchanged for validation errors; or the object remains in a published `FAILED` state.

In addition, an **invariant** is what must hold at all stable and observable states of the object. For example, `balance >= 0` or `start <= end`.

A minimal specification:

| Aspect | Contract of `withdraw` |
| --- | --- |
| Valid pre-state | `balance >= 0` |
| Valid argument | `amount > 0` |
| Success | `newBalance = oldBalance - amount` |
| Invalid argument | Throws `IllegalArgumentException`; `balance` unchanged |
| Insufficient funds | Throws `IllegalStateException` or a domain failure per design; `balance` unchanged |
| Resource/dependency failure | Separate rule; must not assume external transactions were rolled back |

The key point is that **exceptional postconditions must be specific**—you cannot simply write "throws an exception on error."

## 2. What is an invariant and when must it hold?

An **invariant** is a condition on an object's state that must always hold at points where the system publishes the state as valid.

For example, a numeric range:

```text
lower <= upper
```

A `Range` object might use two fields `lower` and `upper`. If a method updates one field first and then throws an exception before updating the other field, the invariant can be broken.

**Distinguish between intermediate state and observable state:**

- Inside an internal operation, code may compute multiple temporary values.
- Before the method returns or throws, the externally published state must obey the documented guarantees.
- In a multithreaded environment, an intermediate state **must not be exposed** through concurrent calls if the class promises thread safety / consistently observable invariants.
- If the object supports callbacks/reentrancy, even within a single method, a callback can observe an incomplete state if you invoke the callback between update steps.

Therefore, an invariant is not merely an `if` expression; it is tied to **state publication and observation rules**.

## 3. Exception safety guarantee levels

In software design, three *exception safety guarantee* levels are commonly distinguished:

| Level | When the method fails | Example meaning |
| --- | --- | --- |
| **Basic guarantee** | Invariants still hold, resources are managed; state may have changed | Some records were successfully written before stopping |
| **Strong guarantee** | Failure does not change observable state within the promised scope (*commit-or-no-change*) | The old configuration remains intact if the new configuration is invalid |
| **No-throw guarantee** | The operation is designed not to let exceptions escape under conditions covered by the contract | A pure, simple getter with no I/O dependencies |

These are **design** terms, not three mandatory interfaces provided by Java. Java **does not automatically verify** that a class achieves the level you advertise.

Be very careful with scope:

- A strong guarantee on **fields in an object** does not mean **logs, emails, files, databases, or HTTP requests** are rolled back.
- A basic guarantee does **not** allow the object to fall into an invalid state; it only allows some changes to have occurred while **invariants still hold**.
- A no-throw guarantee is a **design promise for valid contexts**, not a guarantee that severe `Error`s like `OutOfMemoryError` or JVM faults can never occur. Do not use `catch (Throwable)` to pretend to provide a no-throw guarantee in all cases.

## 4. "Unchanged state" must be defined by scope

When advertising "on failure, state is unchanged," specify **which objects and effects** are covered by the promise:

- Only fields of one instance?
- Also collections owned by the instance?
- Referenced mutable objects?
- Data written to a file?
- Changes in a database transaction?
- Side effects sent to another system?
- Callbacks/listeners that already received notifications?
- Data already published to other threads?

A class might keep `this.state` unchanged yet have already done:

```java
listener.onChanged(newValue);
throw new IllegalStateException("commit chưa hoàn tất");
```

This is **illustrative code**. Even though internal fields have not changed, **the listener has already observed a side effect**. Claiming this method has a system-wide strong guarantee would be inaccurate.

The contract should state specifically: "If validation fails, the active configuration is unchanged; no listeners are invoked." Or: "If sending fails, some bytes may already have been sent; the caller must reconcile state before retrying."

## 5. Bad example: mutating state before validating

A dangerous implementation of the pair `lower`, `upper`:

```java
void setBounds(int newLower, int newUpper) {
    lower = newLower;
    if (newLower > newUpper) {
        throw new IllegalArgumentException("lower > upper");
    }
    upper = newUpper;
}
```

This is an **illustrative method** in a class with two fields. If the range starts as `[2, 8]` and `setBounds(10, 4)` is called, the method assigns `lower = 10` before throwing the exception, while `upper` remains `8`. The state becomes `[10, 8]`: **the invariant `lower <= upper` is broken**.

This is not only a violation of the strong guarantee, it may also **fail to meet the basic guarantee**. After catching, other methods may misbehave because the object is now invalid.

The simple fix: **check all conditions that can fail before assigning**, provided the final commit cannot fail under normal conditions.

## 6. Java 17 program: contrasting wrong and right updates

Save **`BoundsFailureDemo.java`**:

```java
public class BoundsFailureDemo {
    static class UnsafeRange {
        private int lower = 2;
        private int upper = 8;

        void setBounds(int a, int b) {
            lower = a;
            if (a > b) {
                throw new IllegalArgumentException("lower > upper");
            }
            upper = b;
        }

        String view() {
            return "[" + lower + ", " + upper + "]";
        }
    }

    static class SafeRange {
        private int lower = 2;
        private int upper = 8;

        void setBounds(int a, int b) {
            if (a > b) {
                throw new IllegalArgumentException("lower > upper");
            }
            lower = a;
            upper = b;
        }

        String view() {
            return "[" + lower + ", " + upper + "]";
        }
    }

    public static void main(String[] args) {
        UnsafeRange unsafe = new UnsafeRange();
        SafeRange safe = new SafeRange();

        try {
            unsafe.setBounds(10, 4);
        } catch (IllegalArgumentException e) {
            System.out.println("Unsafe bị từ chối");
        }
        try {
            safe.setBounds(10, 4);
        } catch (IllegalArgumentException e) {
            System.out.println("Safe bị từ chối");
        }

        System.out.println("Unsafe sau lỗi: " + unsafe.view());
        System.out.println("Safe sau lỗi: " + safe.view());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 --release 17 BoundsFailureDemo.java
java BoundsFailureDemo
```

**Exact stdout:**

```text
Unsafe bị từ chối
Safe bị từ chối
Unsafe sau lỗi: [10, 8]
Safe sau lỗi: [2, 8]
```

In `UnsafeRange`, the object retains the new value of `lower` even though the operation was rejected and the invariant is broken. `SafeRange` validates first and assigns afterward, so a validation failure preserves the state.

**Limitation:** `SafeRange` here is a **single-threaded example without callbacks**. Assigning two separate fields does not automatically ensure that other threads always observe a consistent snapshot. Concurrent observation requires separate design.

## 7. Preconditions: errors under the caller's responsibility

A method should advertise which arguments are valid:

```java
/**
 * @param amount positive integer amount
 * @throws IllegalArgumentException if amount is not positive
 */
public void deposit(long amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException(
                "amount phải lớn hơn 0");
    }
    // ...
}
```

This is **illustrative code**; the update logic needs to be implemented. `IllegalArgumentException` describes **an argument passed by the caller that violates a precondition**. Because it is unchecked, Java does not force declaring `throws` in the signature, though JavaDoc `@throws` is still helpful.

If a null argument is not accepted, `Objects.requireNonNull` can be used per the contract. If the object is in a not-opened/closed state, `IllegalStateException` usually reflects **lifecycle/state** more accurately than `IllegalArgumentException`.

Important: **check preconditions as early as possible, before side effects**. When validation fails, the API should have an easy-to-understand exceptional postcondition, typically "no state change."

## 8. Normal postconditions must align with exceptional postconditions

Consider a wallet:

- **Before:** `balance >= 0`.
- **Input:** `amount > 0`.
- **Success:** `newBalance = oldBalance - amount`, still non-negative.
- **Insufficient funds:** deduct nothing; throw an error or return failure per the contract.
- **Invalid validation:** no change.
- **If data belongs to an external transaction:** a separate commitment on persistence is required.

A contract should not vaguely say "on error, the state may be anything." If you cannot promise a strong guarantee, clearly state the **basic level**, what effects may have occurred, and the corresponding recovery actions.

An exception is a control-flow signal about **call failure**, but it does not by itself describe the state's condition. It is the API contract that determines how users can proceed.

## 9. Java 17 example: preserving balance on failed withdrawal

Save **`WalletContractDemo.java`**:

```java
public class WalletContractDemo {
    static class Wallet {
        private long balance;

        Wallet(long initial) {
            if (initial < 0) {
                throw new IllegalArgumentException(
                        "initial phải không âm");
            }
            balance = initial;
        }

        long balance() {
            return balance;
        }

        void withdraw(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount phải dương");
            }
            if (amount > balance) {
                throw new IllegalStateException("Không đủ tiền");
            }
            balance -= amount;
        }
    }

    public static void main(String[] args) {
        Wallet wallet = new Wallet(100);
        try {
            wallet.withdraw(150);
        } catch (IllegalStateException e) {
            System.out.println("Từ chối: " + e.getMessage());
        }
        System.out.println("Sau từ chối: " + wallet.balance());

        wallet.withdraw(30);
        System.out.println("Sau thành công: " + wallet.balance());

        try {
            wallet.withdraw(-5);
        } catch (IllegalArgumentException e) {
            System.out.println("Input sai: " + e.getMessage());
        }
        System.out.println("Cuối: " + wallet.balance());
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 WalletContractDemo.java
java WalletContractDemo
```

**Exact stdout:**

```text
Từ chối: Không đủ tiền
Sau từ chối: 100
Sau thành công: 70
Input sai: amount phải dương
Cuối: 70
```

In this case, **validation happens before subtraction**, and `long` cannot overflow on subtraction because `amount > 0` and `amount <= balance`, with `balance` always non-negative in this simple class. If methods that add to the balance are added later, overflow still needs to be guarded so the invariant holds.

The takeaway is that **failure leaves neither a negative balance nor a partial deduction**. This is not yet a real e-wallet application with multithreading, persistence, or banking transactions.

## 10. Overflow checking is also part of state guarantees

Some Java `int` and `long` arithmetic operations can **overflow without throwing an exception automatically**, producing an invalid state.

For example, depositing into a balance near `Long.MAX_VALUE`:

```java
balance += amount;
```

Addition can wrap around to a negative number, breaking the invariant. A stronger approach is to compute beforehand with `Math.addExact`:

```java
long next = Math.addExact(balance, amount);
if (next < 0) {
    throw new IllegalStateException("Số dư không hợp lệ");
}
balance = next;
```

This is **illustrative code**, assuming `amount > 0` and `balance >= 0` were already checked. `Math.addExact` throws `ArithmeticException` if addition overflows; since no assignment has occurred yet, the old state is preserved.

Do not assume that **all intermediate calculations are safe just because there are no checked exceptions**. Validation can throw unchecked exceptions, and silent arithmetic overflows also need to be controlled.

## 11. Java 17 example: overflowing addition leaves state intact

Save **`OverflowGuaranteeDemo.java`**:

```java
public class OverflowGuaranteeDemo {
    static class Counter {
        private long value;

        Counter(long initial) {
            value = initial;
        }

        void add(long amount) {
            if (amount < 0) {
                throw new IllegalArgumentException(
                        "amount phải không âm");
            }
            long next = Math.addExact(value, amount);
            value = next;
        }

        long value() {
            return value;
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter(Long.MAX_VALUE - 1);
        counter.add(1);
        System.out.println("Đạt max: "
                + (counter.value() == Long.MAX_VALUE));

        try {
            counter.add(1);
        } catch (ArithmeticException e) {
            System.out.println("Bắt overflow");
        }

        System.out.println("Giữ max: "
                + (counter.value() == Long.MAX_VALUE));
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 OverflowGuaranteeDemo.java
java OverflowGuaranteeDemo
```

**Exact stdout:**

```text
Đạt max: true
Bắt overflow
Giữ max: true
```

`Math.addExact` computes and checks **before committing**. If the operation throws `ArithmeticException`, the assignment `value = next` does not run, preserving the old state.

If `value += amount` were used instead, integer overflow could make the state violate the invariant without any exception to catch.

## 12. The "validate → prepare → commit" pattern

To achieve a strong guarantee for internal data, a practical approach is:

1. **Validate:** check preconditions and current state.
2. **Prepare:** build replacement data/values, computing any operations that may fail in local variables or temporary objects.
3. **Commit:** update published state only when all preparation steps have succeeded.

Example:

```java
void replace(List<String> incoming) {
    Objects.requireNonNull(incoming, "incoming");
    List<String> candidate = List.copyOf(incoming);
    this.items = candidate;
}
```

This is an **illustrative method**, requiring imports for `List`, `Objects` and a field `items`. `List.copyOf` can throw if the input is null or contains null elements, or encounter an error while creating the copy. Because `this.items` is only assigned **after `candidate` is complete**, failures before commit keep the old reference intact.

**Do not assume `List.copyOf` always takes an accurate snapshot of a collection being concurrently modified by another thread**; stable input or proper synchronization is required. Also, `List.copyOf` only creates a list structure unmodifiable through its API; if the elements inside are mutable objects, they are not automatically deep-copied.

## 13. Java 17 example: copy-then-swap collection update

Save **`CopyThenSwapDemo.java`**:

```java
import java.util.List;
import java.util.Objects;

public class CopyThenSwapDemo {
    static class Registry {
        private List<String> names = List.of("old");

        List<String> snapshot() {
            return names;
        }

        void replace(List<String> incoming) {
            Objects.requireNonNull(incoming, "incoming");
            List<String> candidate = List.copyOf(incoming);
            names = candidate;
        }
    }

    public static void main(String[] args) {
        Registry registry = new Registry();

        try {
            registry.replace(java.util.Arrays.asList("A", null));
        } catch (NullPointerException e) {
            System.out.println("Bản cập nhật bị từ chối");
        }

        System.out.println("Sau lỗi: " + registry.snapshot());

        registry.replace(List.of("A", "B"));
        System.out.println("Sau thành công: " + registry.snapshot());
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 CopyThenSwapDemo.java
java CopyThenSwapDemo
```

**Exact stdout:**

```text
Bản cập nhật bị từ chối
Sau lỗi: [old]
Sau thành công: [A, B]
```

On the failure path, `List.copyOf` rejects the null element and **no change has been assigned to `names`**. On the success path, a single reference assignment publishes the new list.

This is a strong guarantee for **the name list stored inside one instance in a single-threaded example**; it does not automatically synchronize when multiple threads access the field.

## 14. Do not expose mutable state through getters

A strong guarantee can be broken by **aliasing**, even when setters are implemented very carefully.

Problematic example:

```java
class Store {
    private final List<String> values = new ArrayList<>();

    List<String> getValues() {
        return values;
    }
}
```

This is an **illustrative class** requiring imports for `List` and `ArrayList`. The caller receives the exact reference to the internal list and can then write `store.getValues().clear()` without going through validation.

If the invariant is "the list always contains at least one item," a mutable getter leaves the invariant unprotected.

Options:

- Return an **immutable snapshot** such as `List.copyOf(values)` when the contents are suitable.
- Return an unmodifiable view such as `Collections.unmodifiableList` when you want changes to the source list to be reflected without letting callers mutate through the view.
- Use immutable objects from the start and replace the entire reference on commit.
- Control ownership of all mutable references passed across the API.
- If elements are also mutable, consider deep copying or an appropriate immutable representation.

Exceptional postconditions are not durable if callers have another path to mutate state unchecked.

## 15. Immutable objects simplify exception safety

With an immutable value object, a "mutating" method can create a **new object**. If building the new object fails, the old object naturally remains intact.

Java 17 example:

```java
record PortRange(int min, int max) {
    PortRange {
        if (min < 1 || max > 65535 || min > max) {
            throw new IllegalArgumentException("PortRange sai");
        }
    }

    PortRange withMax(int nextMax) {
        return new PortRange(min, nextMax);
    }
}
```

This is an **illustrative record**, which can be placed in a separate Java file named `PortRange.java`. A `PortRange(1000, 2000)` will not change when `withMax(500)` throws `IllegalArgumentException`.

Benefits:

- No partial mutation of the original object's state.
- A complete new object can be prepared before publishing.
- Easy to use with caches, snapshots, comparisons, and tests.
- Reduces the risk of callbacks observing half-updated state.

Limitation: a record whose components reference mutable objects **does not automatically become deeply immutable**. If it contains `List<MutableItem>`, an appropriate snapshot/deep-copy design is needed.

## 16. Java 17 example: immutable configuration and failure when creating a new version

Save **`ImmutableConfigDemo.java`**:

```java
public class ImmutableConfigDemo {
    record Config(String host, int port) {
        Config {
            if (host == null || host.isBlank()) {
                throw new IllegalArgumentException("host rỗng");
            }
            if (port < 1 || port > 65535) {
                throw new IllegalArgumentException("port sai");
            }
        }

        Config withPort(int newPort) {
            return new Config(host, newPort);
        }
    }

    public static void main(String[] args) {
        Config current = new Config("localhost", 8080);

        try {
            current = current.withPort(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("Tạo cấu hình mới thất bại");
        }

        System.out.println("Cấu hình cũ: " + current);

        current = current.withPort(9090);
        System.out.println("Cấu hình mới: " + current);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 ImmutableConfigDemo.java
java ImmutableConfigDemo
```

**Exact stdout:**

```text
Tạo cấu hình mới thất bại
Cấu hình cũ: Config[host=localhost, port=8080]
Cấu hình mới: Config[host=localhost, port=9090]
```

The assignment `current = current.withPort(-1)` does not occur because the right-hand side throws an exception before producing a result. When creating the new configuration succeeds, the `current` variable is pointed to the new object. This is the natural **prepare then publish** pattern when using immutable data.

## 17. When the commit itself can fail

Not every commit operation is a simple field assignment. If committing must:

- write through the filesystem,
- call a database,
- send a message to a broker,
- update multiple shared objects,
- invoke a listener that may throw an exception,
- allocate additional memory,
- update a cache and then publish an event,

then **the commit can fail partway through**. In that case, the "validate → prepare → commit" pattern needs to be extended.

Some strategies:

1. **Minimize failure points inside commit:** prepare data and allocations beforehand; commit via an atomic update whenever possible.
2. **Transactions** supported by the underlying system, with a clearly defined scope.
3. **Intentional compensation** when true rollback is impossible (noting that compensation can also fail).
4. **State machine** publishing `IN_PROGRESS`, `FAILED`, or `UNKNOWN` states so callers are not misled.
5. **Idempotency keys** and state reconciliation when remote side effects may already have occurred.

Do not write `catch (Exception e) { oldValue = backup; }` and claim a strong guarantee if the rest of the commit already produced irreversible side effects.

## 18. Basic guarantee: partially changed state that remains valid

Not every API needs a strong guarantee. An import processor that allows successfully writing the first rows and stopping on an invalid row can provide a **basic guarantee**:

- Every committed record is valid.
- Uncommitted data is not treated as processed.
- Resource lifecycles are managed.
- After failure, the object continues to obey its invariants and can report partially processed state.
- **Partial success** is clearly advertised to the caller.

Conceptual example:

```java
for (Record record : records) {
    validate(record);
    storeOne(record); // Each record has its own commit.
}
```

This is **illustrative code**, with helper classes/methods undefined. If the 5th item fails, the first 4 items have already been saved; the method may throw an exception, but the system must not claim "nothing changed."

The basic guarantee is by no means bad design if it is **clearly advertised**, preserves invariants, and fits the domain. The mistake is letting callers **implicitly expect all-or-nothing** when the implementation only guarantees partial progress.

## 19. Java 17 example: partial progress still preserves invariants

Save **`PartialImportDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class PartialImportDemo {
    static class Importer {
        private final List<String> accepted = new ArrayList<>();

        void importAll(List<String> input) {
            for (String item : input) {
                if (item.isBlank()) {
                    throw new IllegalArgumentException(
                            "Item không được rỗng");
                }
                accepted.add(item);
            }
        }

        List<String> snapshot() {
            return List.copyOf(accepted);
        }
    }

    public static void main(String[] args) {
        Importer importer = new Importer();

        try {
            importer.importAll(List.of("A", "B", "", "C"));
        } catch (IllegalArgumentException e) {
            System.out.println("Import dừng: " + e.getMessage());
        }

        System.out.println("Đã nhận: " + importer.snapshot());
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 PartialImportDemo.java
java PartialImportDemo
```

**Exact stdout:**

```text
Import dừng: Item không được rỗng
Đã nhận: [A, B]
```

The items `"A"` and `"B"` were added. When the blank string is encountered, the exception is thrown **before adding the invalid item**; the internal list still contains only valid data. The caller must know that `importAll` can **commit item by item** and must not assume failure reverts the list to its initial state.

This pattern is not suitable for an all-or-nothing data import contract unless replaced with staging and a single commit or a transaction.

## 20. Strong guarantee for batches: prepare everything before publishing

If the domain requires **either accept the whole batch or change nothing**, you can prepare a new structure first:

```java
void importAll(List<String> input) {
    List<String> candidate = new ArrayList<>(accepted);
    for (String item : input) {
        if (item.isBlank()) {
            throw new IllegalArgumentException("Item rỗng");
        }
        candidate.add(item);
    }
    accepted = List.copyOf(candidate);
}
```

This is an **illustrative method**, with `accepted` as a reassignable `List<String>` field and imports for `List`, `ArrayList`. If validation or copying fails before `accepted = ...`, the old field is unchanged.

Notes:

- `accepted` must not be declared `final` if you want to swap the reference.
- If items are mutable, copying the list does not automatically deep-copy the items.
- If callbacks are invoked during preparation, those callbacks can produce external side effects.
- If multiple threads can modify `accepted`, synchronization or an atomic update mechanism is needed.
- In persistent systems, in-memory copy-then-swap **does not roll back databases or files**.

The goal is not just "using a temporary list," but **placing all work that can fail before the commit boundary**.

## 21. Java 17 program: failed batch adds no elements

Save **`AtomicImportDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class AtomicImportDemo {
    static class Importer {
        private List<String> accepted = List.of("old");

        void importAll(List<String> input) {
            List<String> candidate = new ArrayList<>(accepted);
            for (String item : input) {
                if (item == null || item.isBlank()) {
                    throw new IllegalArgumentException(
                            "Item không hợp lệ");
                }
                candidate.add(item);
            }
            accepted = List.copyOf(candidate);
        }

        List<String> snapshot() {
            return accepted;
        }
    }

    public static void main(String[] args) {
        Importer importer = new Importer();

        try {
            importer.importAll(List.of("A", "", "C"));
        } catch (IllegalArgumentException e) {
            System.out.println("Batch thất bại");
        }
        System.out.println("Sau lỗi: " + importer.snapshot());

        importer.importAll(List.of("A", "B"));
        System.out.println("Sau thành công: " + importer.snapshot());
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 AtomicImportDemo.java
java AtomicImportDemo
```

**Exact stdout:**

```text
Batch thất bại
Sau lỗi: [old]
Sau thành công: [old, A, B]
```

All changes are built in `candidate`. Only when the list is complete and `List.copyOf` succeeds is the `accepted` field updated. This is a strong guarantee for **managed internal state in a single-threaded example**.

## 22. Exception safety does not mean thread safety

A method with a strong guarantee when called single-threaded is **not automatically safe** when multiple threads run concurrently.

Two-field example:

```java
if (newLower > newUpper) {
    throw new IllegalArgumentException();
}
lower = newLower;
upper = newUpper;
```

This is **illustrative code**. Another thread can read `lower` after it is assigned but before `upper` is assigned, observing an inconsistent intermediate state. If this case violates the contract, synchronization must be added.

Design options:

- Protect both reads and writes with the **same lock** (`synchronized` or `Lock`).
- Bundle state into **an immutable snapshot** and update a single reference with proper publication rules (e.g., `volatile` / `AtomicReference`).
- Use **CAS** if the operation requires checking the current version and updating atomically.
- Confine the object to **a single thread** and document that it is not thread-safe.

**Merely adding `volatile` to individual fields does not turn multiple assignments into a transaction.** Exception guarantees and atomicity/visibility are different, though related, properties.

## 23. Java 17 example: publishing an immutable snapshot via a single reference

Save **`SnapshotStateDemo.java`**:

```java
public class SnapshotStateDemo {
    record Bounds(int lower, int upper) {
        Bounds {
            if (lower > upper) {
                throw new IllegalArgumentException("Khoảng sai");
            }
        }
    }

    static class RangeStore {
        private volatile Bounds bounds = new Bounds(1, 5);

        Bounds snapshot() {
            return bounds;
        }

        void replace(int lower, int upper) {
            Bounds candidate = new Bounds(lower, upper);
            bounds = candidate;
        }
    }

    public static void main(String[] args) {
        RangeStore store = new RangeStore();

        try {
            store.replace(9, 2);
        } catch (IllegalArgumentException e) {
            System.out.println("Từ chối khoảng sai");
        }

        System.out.println("Sau lỗi: " + store.snapshot());

        store.replace(3, 7);
        System.out.println("Sau thành công: " + store.snapshot());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 SnapshotStateDemo.java
java SnapshotStateDemo
```

**Exact stdout:**

```text
Từ chối khoảng sai
Sau lỗi: Bounds[lower=1, upper=5]
Sau thành công: Bounds[lower=3, upper=7]
```

The `Bounds` record validates its invariant upon creation. The `volatile Bounds bounds` field is updated by **a single reference assignment**, so readers obtain a consistent snapshot of the two immutable components. If the update is a **read-modify-write based on an old snapshot** across multiple writers, `volatile` alone does not prevent lost updates: `AtomicReference.compareAndSet` or a lock may be needed.

This is one way to combine a strong guarantee during candidate creation with state-publication rules in a concurrent environment.

## 24. Example: atomic transfer between two balances in one object

When changes to multiple fields must happen together, check all conditions first. The example below uses **a single lock on the instance** so methods of the class itself cannot observe a half-completed transfer.

Save **`AccountTransferDemo.java`**:

```java
public class AccountTransferDemo {
    static class Ledger {
        private long left = 100;
        private long right = 20;

        synchronized void transfer(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount phải dương");
            }
            if (amount > left) {
                throw new IllegalStateException(
                        "Không đủ số dư bên trái");
            }

            long nextRight = Math.addExact(right, amount);
            long nextLeft = left - amount;

            left = nextLeft;
            right = nextRight;
        }

        synchronized String snapshot() {
            return left + "/" + right;
        }
    }

    public static void main(String[] args) {
        Ledger ledger = new Ledger();

        try {
            ledger.transfer(150);
        } catch (IllegalStateException e) {
            System.out.println("Từ chối chuyển");
        }
        System.out.println("Sau lỗi: " + ledger.snapshot());

        ledger.transfer(30);
        System.out.println("Sau chuyển: " + ledger.snapshot());
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 AccountTransferDemo.java
java AccountTransferDemo
```

**Exact stdout:**

```text
Từ chối chuyển
Sau lỗi: 100/20
Sau chuyển: 70/50
```

`Math.addExact` guards against overflow on the receiving balance before assigning. Both `transfer` and `snapshot` use the **same monitor lock**; callers using the designed API never see between the two assignments. Side effects not implemented in this example (database, network, listeners) are not covered by this lock.

**Do not treat this as a real-world multi-account/multi-process money transfer system.** Database transactions, multi-object locking, crash recovery, and idempotency require dedicated design.

## 25. Constraining state before and after lifecycle failure

Some objects cannot return to their previous state after an operation fails, but can still transition to a **valid, well-defined** state.

State machine example:

```text
NEW → OPEN → CLOSED
       │
       └── I/O failure → FAILED
```

Contract:

- `read()` is only valid in `OPEN`.
- If validation fails, the object stays in `OPEN` (strong guarantee for input errors).
- If underlying I/O breaks and cannot continue, the object transitions to `FAILED`.
- After `FAILED`, only advertised operations (e.g., `close`, `state`, or `diagnostics`) are permitted; `read()` is rejected with `IllegalStateException`.
- Even on error, the object is **not** in an ambiguous half-OPEN, half-CLOSED state.

This is a **basic guarantee** for I/O errors: the state transitions to `FAILED`, yet lifecycle invariants still hold.

Some JDK APIs allow retrying reads after a timeout; you should not force every `IOException` into `FAILED` if the contract and protocol allow continuing. The decision must be based on **whether invariants can still be maintained after a specific error**.

## 26. Java 17 program: exceptional postcondition is the FAILED state

Save **`FailureStateDemo.java`**:

```java
import java.io.IOException;

public class FailureStateDemo {
    enum State {
        NEW, OPEN, FAILED, CLOSED
    }

    static class ReaderSession {
        private State state = State.NEW;

        void open() {
            if (state != State.NEW) {
                throw new IllegalStateException("Không còn NEW");
            }
            state = State.OPEN;
        }

        String read(boolean fail) throws IOException {
            if (state != State.OPEN) {
                throw new IllegalStateException(
                        "read cần trạng thái OPEN");
            }
            if (fail) {
                state = State.FAILED;
                throw new IOException("Lỗi đọc");
            }
            return "data";
        }

        State state() {
            return state;
        }

        void close() {
            state = State.CLOSED;
        }
    }

    public static void main(String[] args) {
        ReaderSession session = new ReaderSession();
        session.open();
        System.out.println("Trước: " + session.state());

        try {
            session.read(true);
        } catch (IOException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        System.out.println("Sau lỗi: " + session.state());
        session.close();
        System.out.println("Sau close: " + session.state());
    }
}
```

Run:

```bash
javac -encoding UTF-8 --release 17 FailureStateDemo.java
java FailureStateDemo
```

**Exact stdout:**

```text
Trước: OPEN
Bắt: Lỗi đọc
Sau lỗi: FAILED
Sau close: CLOSED
```

A read failure intentionally transitions the object to `FAILED` before throwing the checked `IOException`. The goal is to **advertise a clear exceptional postcondition**, not to keep everything unchanged in every situation.

For real systems, the `FAILED` state must have proper rules for closing, recreation, or diagnostics; do not use a state flag to hide resource leaks.

## 27. Checking which operations can throw exceptions at any point

In Java, a call often has many sources of failure:

- **Validation**: `IllegalArgumentException`, `NullPointerException`.
- **Lifecycle**: `IllegalStateException`.
- **Arithmetic**: `ArithmeticException` such as `Math.addExact`.
- **Collections**: `IndexOutOfBoundsException`, `ConcurrentModificationException` depending on the API.
- **I/O**: `IOException`, `UncheckedIOException`, or framework errors.
- **Allocation**: severe allocation/JVM errors, usually outside application recovery guarantees.
- **Arbitrary callbacks**: can throw exceptions that the callback-invoking class does not control.
- **Cancellation/interruption**: especially in blocking waits or asynchronous tasks.

Defining post-failure state must consider **all failure sources within the contract the API promises to handle**, not only a single `throw new IllegalArgumentException` statement you wrote yourself.

For example, if you updated the first field and then invoked a callback that can throw `RuntimeException` before updating the second field, a callback failure can break the invariant even though validation was checked earlier.

## 28. Callbacks, observers, and reentrancy risks

Consider a problematic pattern:

```java
state = "UPDATING";
listener.onChange(newValue);
state = "READY";
```

This is **illustrative code**. If `listener.onChange` throws an exception, the object is stuck in `"UPDATING"`. If the listener also calls back into `getState()` before throwing, it observes the intermediate state.

Strategies:

1. Finalize and publish a consistent state **before** emitting notifications; however, if the listener fails, advertise that notification side effects can fail after commit.
2. Prepare the event and new state, and commit in a clearly contracted order.
3. Do not invoke untrusted callbacks between steps that repair invariants.
4. If callbacks run asynchronously, publish separate failure semantics for event delivery.
5. If notification is required together with the state transition, use a transactional/outbox mechanism or compensation rather than just `try/catch`.

A **strong guarantee on internal state** does not imply a strong guarantee for all observers. The contract must state **whether commit happens before or after notification** and what happens when notification fails.

## 29. Resources and exceptional postconditions

State is not just business fields. An API also manages **file handles, sockets, locks, database connections, streams, or threads**.

After a failure, answer:

- Is the resource still open?
- Who owns closing it?
- Can closing throw an error?
- Is a lock still held, or has it been released?
- Can the object be reused, or must a new one be created?
- Is there unflushed data in a buffer?
- Is there an uncommitted/unrolled-back transaction?
- Is the caller allowed to retry on the same resource?

`try-with-resources` helps close resources when exiting scope:

```java
try (InputStream input = openInput()) {
    return parse(input);
}
```

This is **illustrative code**; `openInput` and `parse` need to be defined, and the enclosing method must handle checked exceptions. When `parse` throws, Java still attempts to call `input.close()`. However, **closing a resource** does not automatically guarantee that previously written data was rolled back or that the peer did not receive a request.

**Do not equate "cleanup succeeded" with "transaction rollback succeeded."**

## 30. Java 17 example: try-with-resources still closes after failure

Save **`CleanupAfterFailureDemo.java`**:

```java
public class CleanupAfterFailureDemo {
    static class Resource implements AutoCloseable {
        private boolean closed;

        void work() {
            System.out.println("Đang xử lý");
            throw new IllegalStateException("Thất bại");
        }

        @Override
        public void close() {
            closed = true;
            System.out.println("Đã đóng");
        }

        boolean isClosed() {
            return closed;
        }
    }

    public static void main(String[] args) {
        Resource resource = new Resource();

        try (resource) {
            resource.work();
        } catch (IllegalStateException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        System.out.println("Closed: " + resource.isClosed());
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 CleanupAfterFailureDemo.java
java CleanupAfterFailureDemo
```

**Exact stdout:**

```text
Đang xử lý
Đã đóng
Bắt: Thất bại
Closed: true
```

`try (resource)` has been valid since Java 9 for a **final or effectively final** resource variable. Even when `work()` fails, `close()` is called before the `catch` handler executes.

This is a **resource lifecycle** guarantee in the example, not a guarantee that all business state mutated inside `work()` has been undone.

## 31. What if both the main operation and cleanup fail?

`try-with-resources` uses **suppressed exceptions** so the primary error is not lost when `close()` also throws an exception.

Example:

```java
try (Resource resource = acquire()) {
    perform(resource);  // Throws primary error.
} // close() may throw a secondary error.
```

This is **illustrative code**; `Resource` and helper methods need to be declared. If the `try` body throws an exception and `close()` also throws, the close error is attached to `primary.getSuppressed()` via the standard mechanism.

The state contract must consider: a resource may have **performed partial cleanup** before `close` failed. Suppressed errors are still worth recording when assessing whether resources were actually released.

Do not only extract `primary.getMessage()` and discard cause/suppressed exceptions when diagnosing recovery conditions. In loggers, prefer logging the full `Throwable` object.

## 32. Java 17 example: close exception becomes suppressed

Save **`SuppressedFailureDemo.java`**:

```java
import java.io.IOException;

public class SuppressedFailureDemo {
    static class Resource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close thất bại");
        }
    }

    static void run() throws IOException {
        try (Resource resource = new Resource()) {
            throw new IOException("work thất bại");
        }
    }

    public static void main(String[] args) {
        try {
            run();
        } catch (IOException e) {
            System.out.println("Primary: " + e.getMessage());
            System.out.println("Suppressed count: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 SuppressedFailureDemo.java
java SuppressedFailureDemo
```

**Exact stdout:**

```text
Primary: work thất bại
Suppressed count: 1
Suppressed: close thất bại
```

If code manually writes `finally` and throws a new exception, it can **mask the original error**; using proper resource constructs preserves diagnostic information better.

## 33. File/network writes can complete only partially

An `OutputStream.write` call may **have already output some bytes before `IOException` is thrown**. Therefore, you cannot conclude "the method threw `IOException`, so nothing was written."

Self-contained example simulating **partial I/O** without needing a filesystem:

Save **`PartialWriteDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class PartialWriteDemo {
    static class FailingOutput extends OutputStream {
        private final StringBuilder delivered = new StringBuilder();

        @Override
        public void write(int value) throws IOException {
            if (delivered.length() == 2) {
                throw new IOException("Sink từ chối byte tiếp theo");
            }
            delivered.append((char) (value & 0xff));
        }

        String delivered() {
            return delivered.toString();
        }
    }

    public static void main(String[] args) {
        FailingOutput output = new FailingOutput();

        try {
            output.write("ABC".getBytes(StandardCharsets.US_ASCII));
        } catch (IOException e) {
            System.out.println("Bắt: " + e.getMessage());
        }

        System.out.println("Đã ghi: " + output.delivered());
    }
}
```

Commands:

```bash
javac -encoding UTF-8 --release 17 PartialWriteDemo.java
java PartialWriteDemo
```

**Exact stdout:**

```text
Bắt: Sink từ chối byte tiếp theo
Đã ghi: AB
```

`OutputStream` has a default `write(byte[])` implementation that calls `write(byte[],off,len)`; the default `OutputStream` class calls `write(int)` sequentially for each byte. In the example, two bytes `A` and `B` were accepted, and byte `C` caused the error. `IOException` does not automatically erase the two bytes already written.

**This is an intentional simulation**, not proof that every stream splits writes in the same way. The general lesson is to write contracts about **partial progress** rather than assuming a strong guarantee for I/O by guesswork.

## 34. Database transactions: strong within transaction scope, not the whole world

A database transaction can provide atomicity for a group of operations **on the resources within that transaction's scope**. JDBC skeleton example:

```java
connection.setAutoCommit(false);
try {
    debit(connection, from, amount);
    credit(connection, to, amount);
    connection.commit();
} catch (SQLException e) {
    try {
        connection.rollback();
    } catch (SQLException rollbackError) {
        e.addSuppressed(rollbackError);
    }
    throw e;
}
```

This is **illustrative code**, requiring a connection, helpers, and proper transaction lifecycle handling. In practice, you must restore `autoCommit`/close the connection according to ownership, and account for network errors during or after commit.

Important conditions:

- The same transaction does not cover emails, files, or HTTP calls sent during the transaction.
- `rollback()` can also fail; rollback errors must be preserved.
- A connection error during `commit()` can leave the **commit outcome unknown** to the client.
- You must not assert "an `SQLException` means the database definitely did not change."
- Database isolation and concurrency must be configured appropriately; exception safety in Java does not replace transaction semantics.

The contract may need an **UNKNOWN** state or transaction ID reconciliation when the commit outcome cannot be verified.

## 35. Distributed side effects: "threw an error" does not mean "not executed"

In RPC, HTTP, message brokers, or payment systems, a request can be:

1. Sent by the client.
2. Received and processed by the server.
3. Committed by the server.
4. Response lost.
5. Client times out and throws an exception.

In this case, the client-side call **failed in terms of knowing the outcome**, yet the server-side side effect **may already have happened**.

You cannot fix this with:

```java
catch (IOException e) {
    sendAgain();
}
```

This is an **illustrative counterexample**; `sendAgain` is undefined. Repeating the call can create a second transaction.

Appropriate techniques:

- **Idempotency keys** so the same logical request is not erroneously processed twice.
- **Request/transaction IDs** to query server state.
- **Bounded retries** with backoff and deadlines.
- **Outbox** or event-driven consistency when the system must coordinate writing data and emitting events.
- **Compensation** when cross-service transactions are not possible.
- **Unknown outcome state** clearly advertised to the caller, rather than returning "failed, definitely not committed."

A **system-wide distributed** strong guarantee requires protocol/component support, not a built-in feature of checked exceptions.

## 36. Outcome states: SUCCESS, FAILED, and UNKNOWN

For APIs with remote side effects, a result may need to distinguish:

- **SUCCESS:** the server confirmed the operation succeeded.
- **FAILED:** the server confirmed the operation was not executed or was rejected, and the contract knows the state.
- **UNKNOWN:** the client cannot determine for certain whether the operation committed.

Java 17 result type example:

```java
enum Outcome {
    SUCCESS, FAILED, UNKNOWN
}

record OperationResult(String requestId, Outcome outcome) {
}
```

These are **two illustrative types**, without `main`. A request timeout can lead to `UNKNOWN`, whereas a validation failure before sending can definitely be `FAILED` with no side effects.

Do not return `FAILED` meaning "not executed" when all you know is that **no response was received**. If callers need to retry, distinguishing `UNKNOWN` is critical.

## 37. Checked and unchecked exceptions do not determine state guarantees

A method with `throws IOException` can:

- leave state unchanged on failure,
- partially change valid state,
- put the object into `FAILED`,
- or be unable to verify external side effects.

Similarly, a method throwing `IllegalArgumentException` can **accidentally corrupt state** if validation is performed after mutating fields.

Therefore:

- **Checked vs. unchecked:** compiler catch-or-declare rules and error contract semantics.
- **Basic/strong/no-throw:** level of state guarantee when a method terminates abnormally.
- **Atomicity:** indivisibility of a group of updates within a defined system scope.
- **Thread safety:** guarantees under concurrent access.
- **Idempotency:** repeating the same logical operation does not produce unwanted effects.
- **Durability:** committed effects survive corresponding crashes.

These properties **do not substitute for one another**. A reliable API often needs several of them together.

## 38. Do not assume catch restores invariants

`try/catch` is a control-flow mechanism after an exception:

```java
try {
    updatePartA();
    updatePartB();
} catch (RuntimeException e) {
    log(e);
}
```

This is **illustrative code**. If `updatePartA` already mutated state and then `updatePartB` throws an exception, a handler that only logs **restores nothing**.

Writing `catch` does not mean:

- rolling back fields,
- rolling back the database,
- recalling sent messages,
- closing all resources,
- releasing all locks,
- or keeping object state unchanged.

A proper handler must know the **exceptional postcondition** and work ownership. If it cannot recover, it should propagate or wrap the error with its cause per the contract, rather than returning a fake success.

## 39. Be careful with manual rollback

A common thought:

```java
State old = current;
try {
    updateExternalSystem();
    current = next;
} catch (Exception e) {
    current = old;
    throw e;
}
```

This is **illustrative code**; variables and methods need to be defined. Setting `current = old` cannot undo the side effects of `updateExternalSystem()`. If `current` points to a mutable object modified elsewhere, keeping the old reference does not guarantee the old state is actually intact either.

Manual rollback can fail because:

- the backup is a shallow copy/alias.
- the undo operation itself throws an exception.
- callbacks already observed intermediate data.
- resources/transactions partially committed.
- other threads already read or modified the state.
- an event was already sent to another system.
- an error occurred at a point you did not anticipate.

If you cannot roll back with commensurate reliability, **advertise a basic guarantee or FAILED/UNKNOWN** instead of promising a false strong guarantee.

## 40. Exception safety and methods with observable side effects

A public API can produce side effects even when object fields do not change:

- Writing logs containing data.
- Incrementing metrics/counters.
- Emitting events.
- Sending emails.
- Allocating a new ID.
- Consuming an item from a queue.
- Marking a job as having run.
- Invoking an asynchronous callback.

This means "**state unchanged**" must be defined according to the **observable scope that actually needs to be guaranteed**. Some side effects like logs/metrics are acceptable even when a method fails; not everything needs to be rolled back.

For example, an API might promise "if validation fails, business data is unchanged; the system still records an audit event for the rejected call." This contract can be completely valid, but it should not be written simply as "no state changes."

## 41. Combining exception cause with state condition

The exception should state the **cause**; the contract/documentation should state the **object's condition**. Some APIs choose to represent state alongside a domain exception:

```java
class SubmissionException extends Exception {
    private final boolean mayHaveCommitted;

    SubmissionException(String message,
                        boolean mayHaveCommitted,
                        Throwable cause) {
        super(message, cause);
        this.mayHaveCommitted = mayHaveCommitted;
    }

    boolean mayHaveCommitted() {
        return mayHaveCommitted;
    }
}
```

This is an **illustrative class**, without `main`. It demonstrates how to expose the knowledge a caller needs to decide whether to reconcile or retry.

However, a boolean `mayHaveCommitted` may not be enough for real systems. An enum `NOT_SENT/CONFIRMED/UNKNOWN` or a result object containing a request ID, outcome, and recovery information can express this more clearly.

**Do not infer commit status solely from `IOException`, `TimeoutException`, or `RuntimeException`.** The source of truth must be a verified protocol/state contract.

## 42. Writing JavaDoc with clear exceptional postconditions

API example:

```java
/**
 * Replaces the entire active configuration.
 *
 * @param next new configuration data, non-null
 * @throws NullPointerException if next is null
 * @throws IllegalArgumentException if next is invalid
 *
 * <p>If validation fails, the current configuration
 * is unchanged and listeners have not been invoked.</p>
 *
 * <p>If updating the external source fails, the state
 * may be FAILED; call state() to check before retrying.</p>
 */
public void replace(Config next) {
    // implementation per the contract above
}
```

This is **illustrative code**, with `Config` and the implementation designed separately. When writing real JavaDoc, describe both state conditions and specific exceptions if the method has them.

A useful documentation template:

| Item | Question to answer |
| --- | --- |
| Invariant | What always holds in a valid state? |
| Precondition | What may the caller pass and when may it call? |
| Success | Which fields/resources/side effects change? |
| Failure by validation | Which state remains unchanged? |
| Failure by I/O | Could it have partially written/sent? |
| Failure by cancellation | What happens to resources and interrupt status? |
| Retry | Must input be fixed, object rebuilt, state queried, or an idempotency key used? |
| Ownership | Who closes, rolls back, releases locks, or handles a FAILED object? |

The goal is that **callers do not have to read the entire source** to know what they can do after an exception.

## 43. Designing tests: verify state, not just exception type

A test that only checks:

```java
assertThrows(IllegalArgumentException.class,
        () -> service.update(badInput));
```

is **illustrative code using JUnit**, requiring the appropriate library and variables. It checks that an exception occurred, but **does not verify post-failure state**.

You also need to:

- Snapshot state before calling.
- Inject an intentional error at the desired point.
- Call the method and catch the exact exception type.
- Snapshot state after failure.
- Compare the parts belonging to invariants and strong/basic guarantees.
- If there are external side effects, check what the fake/mock sink received rather than inferring from internal state.
- Verify resources are closed / locks are released.
- Verify cause/suppressed exceptions if wrapping/cleanup is part of the contract.
- Check which methods the caller can invoke after failure.
- Test retries and idempotency per scenario.

**Exception safety tests must proactively exercise multiple failure points**, not just the easiest validation branch.

## 44. Java 17 program: asserting both exception and unchanged state

Save **`FailureInvariantAssertionsDemo.java`**:

```java
public class FailureInvariantAssertionsDemo {
    static class Counter {
        private int value = 5;

        void increase(int delta) {
            if (delta <= 0) {
                throw new IllegalArgumentException(
                        "delta phải dương");
            }
            int candidate = Math.addExact(value, delta);
            value = candidate;
        }

        int value() {
            return value;
        }
    }

    static void assertUnchanged(
            Counter counter, int before, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Thiếu exception");
        } catch (RuntimeException expected) {
            if (counter.value() != before) {
                throw new AssertionError("State đã thay đổi");
            }
            System.out.println("PASS unchanged");
        }
    }

    public static void main(String[] args) {
        Counter counter = new Counter();

        assertUnchanged(counter, 5,
                () -> counter.increase(-1));

        counter.increase(3);
        System.out.println("Success state: " + counter.value());

        Counter nearMax = new Counter();
        nearMax.increase(Integer.MAX_VALUE - 5);

        assertUnchanged(nearMax, Integer.MAX_VALUE,
                () -> nearMax.increase(1));
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 --release 17 FailureInvariantAssertionsDemo.java
java FailureInvariantAssertionsDemo
```

**Exact stdout:**

```text
PASS unchanged
Success state: 8
PASS unchanged
```

Branches tested:

- Negative input throws `IllegalArgumentException`, `value` remains 5.
- Valid increment updates from 5 to 8.
- From an object with `value = Integer.MAX_VALUE`, incrementing further triggers `ArithmeticException` from `Math.addExact`, and the value remains intact.

The test uses `AssertionError` directly so the `-ea` flag is not needed. It does not cover every failure injection yet, but it serves as a pattern for testing **exceptional postconditions**, not only exception types.

## 45. Failure injection: testing errors at every stage

A system has multiple steps:

```text
VALIDATE → PREPARE → WRITE → NOTIFY → COMMIT
```

Test when each step throws:

| Failure point | What to verify |
| --- | --- |
| Validate | No changes made and no side-effecting dependencies called |
| Prepare | Candidate discarded, old state valid |
| Write | Any partial I/O? Any resource leak? |
| Notify | Has commit already happened? Could events be partially sent? |
| Commit | Is outcome clear? Is rollback/compensation guaranteed? |
| Close/cleanup | Are primary and suppressed errors preserved? |

You can use:

- Fake dependencies programmed to throw `IOException` on the Nth call.
- Fake sinks that record the count of received items and then throw.
- In-memory repositories managing simulated transactions with explicit outcomes.
- Latches to reproduce specific concurrency scenarios.
- Property-based tests checking invariants across many inputs.
- Independent integration tests for real databases/filesystems/networks.

Do not rely on "waiting for the network to fail on its own" to test guarantee logic; real infrastructure failures are very hard to reproduce at the exact step.

## 46. Failure paths and guarantee levels by API type

| API/operation | Targetable level | Notes |
| --- | --- | --- |
| Simple setter with full validation | Strong for fields | Watch out for observers and concurrency |
| Immutable snapshot replacement | Strong for snapshot | Old snapshot remains if prepare fails |
| Per-item batch import | Basic | Partially committed, must be advertised |
| In-memory all-or-nothing batch | Strong within memory scope | Prepare all before swapping |
| Writing `OutputStream` | Usually must accept partial progress | `IOException` does not roll back bytes |
| JDBC transaction | Atomic within supported transaction scope | Commit/network errors can leave outcome unknown |
| RPC with side effects | Needs idempotency/state reconciliation | Timeout does not prove uncommitted |
| Resource close | May throw `IOException` | Manage cleanup/suppressed |
| Simple immutable getter | Can be designed no-throw under valid conditions | Does not promise immunity to all JVM `Error`s |

This table is a **contract design** suggestion, not a claim that every implementation of an API category always achieves a fixed guarantee level.

## 47. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Having `catch` automatically rolls back state." | No. Catch only handles control flow. |
| "Checked exceptions definitely preserve state." | No. Checked/unchecked is independent of state guarantees. |
| "Invariants only need to hold on success." | After failure, the advertised guarantee level must still hold. |
| "Basic guarantee means nothing changes." | No. State may change, but invariants must hold. |
| "Strong guarantee means rolling back emails, logs, and databases too." | Only within the promised scope; external side effects need separate mechanisms. |
| "No-throw means catching `Throwable` so nothing ever fails." | No. Do not hide severe/JVM errors. |
| "Validation can go after field mutation because an exception is thrown anyway." | It can corrupt state before throwing. |
| "`List.copyOf` automatically deep-copies all mutable items." | No. It only creates a list structure snapshot per its contract. |
| "Returning an internal list from a getter doesn't affect invariants." | Callers can mutate it directly if the list is mutable. |
| "Assigning two `volatile` fields consecutively is a transaction." | No. Readers can see an intermediate state. |
| "An immutable record containing a mutable field is definitely deep immutable." | No. Component ownership/snapshotting is needed. |
| "`finally`/try-with-resources automatically undoes written data." | No. It primarily manages resource cleanup. |
| "`IOException` on write means zero bytes were written." | No. Partial writes may have occurred. |
| "An RPC timeout proves the server did not commit." | No. The outcome may be `UNKNOWN`. |
| "`rollback()` always succeeds." | No. Rollback can throw its own error. |
| "Throwing `IllegalStateException` means the object must be completely broken." | No. It may just be a wrong lifecycle call, with state still valid. |
| "Transitioning to `FAILED` violates the basic guarantee." | Not if `FAILED` is a valid contracted state. |
| "A single reference assignment solves all writer races." | No. Concurrent read-modify-write needs locks/CAS. |
| "Catching and returning success is resilience." | Only true when genuinely recovered per the contract. |
| "Asserting only the exception type is enough for safety testing." | Post-failure state and side effects must also be verified. |

## 48. Self-check questions

**1. What is an invariant?**  
A condition on state that must hold at points where the object is published as valid.

**2. What is an exceptional postcondition?**  
A commitment about state and side effects when a method terminates by throwing an exception.

**3. How does the basic guarantee differ from the strong guarantee?**  
Basic preserves invariants while allowing partial state changes; strong keeps observable state within the promised scope unchanged on failure.

**4. Does Java automatically guarantee a strong guarantee for every `throws IOException` method?**  
No. It requires design, implementation, and testing.

**5. Why is placing validation after field assignments dangerous?**  
An exception can occur after state has already partially changed, even breaking invariants.

**6. What does the validate–prepare–commit pattern solve?**  
It moves steps that can fail before a small commit, keeping the old state if preparation fails.

**7. Why is `List.copyOf` useful yet not a deep copy?**  
It creates a list unmodifiable through the list API, but mutable element objects may still be shared.

**8. Is an immutable record containing `List<MutableItem>` automatically deep immutable?**  
No. Mutable-referencing components need their own policy.

**9. How does `Math.addExact` help with exceptions?**  
It detects overflow before assignment, avoiding publishing an overflowed value that violates invariants.

**10. Does catching an exception guarantee that an earlier callback did not run?**  
No. The callback may have already produced side effects before throwing.

**11. If 4 items are imported and the 5th fails, what guarantee level might that be?**  
Basic, if the four committed items are valid, invariants still hold, and the contract advertises partial progress.

**12. Why can writing to an `OutputStream` leave partial data after an `IOException`?**  
The implementation may have written earlier bytes before encountering an error on a subsequent byte.

**13. What does `try-with-resources` promise when the `try` body throws?**  
It attempts to close the resource; if `close` also throws, it may attach a suppressed exception to the primary error. It does not automatically roll back side effects.

**14. Why can't database `rollback()` be assumed to always succeed?**  
Rollback can encounter I/O/connection errors or an unclear transaction state, so its error must be handled and logged separately.

**15. Does a timeout after sending a transaction creation command prove the transaction did not commit?**  
No. You may need to use an `UNKNOWN` status and a request ID to reconcile.

**16. Does a `volatile Bounds` snapshot solve lost updates across multiple writers?**  
No. CAS/locks are needed for read-modify-write.

**17. If an object transitions to `FAILED` after an `IOException`, can it still meet the basic guarantee?**  
Yes, if `FAILED` is a valid advertised state and resources are managed.

**18. Why shouldn't you catch `RuntimeException` and return default success data?**  
It can hide bugs and partial side effects, violating the caller's contract.

**19. What else should good exception tests check besides the exception type?**  
Before-and-after state, invariants, side effects, resources, cause/suppressed exceptions, and retry/reuse capabilities.

**20. If a getter gives the caller a reference to an internal mutable collection, are exceptional postconditions easy to control?**  
No. The caller can mutate state outside all API validation.

**21. Does a listener failure after commit mean the earlier commit automatically rolled back?**  
No. Separate contracts are needed for commit and notification.

**22. Should `catch (Throwable)` be used to create an absolute no-throw guarantee?**  
No. Swallowing severe JVM errors usually cannot provide a real safety guarantee.

**23. Why is it necessary to specify the scope of "unchanged state"?**  
Because fields, resources, callbacks, and out-of-process side effects have different guarantee scopes.

**24. When an error can leave the remote outcome unclear, what information does the caller need?**  
Request ID, `UNKNOWN` outcome or state-query capability, and idempotency/retry policy.

## 49. Checklist for designing APIs with clear exceptional postconditions

1. **Write the invariant:** what conditions must a valid object satisfy?
2. **Write the precondition:** what are the caller's arguments, state, and ownership rules?
3. **Write the normal postcondition:** what does success change?
4. **Write the exceptional postcondition:** if it fails, what is preserved and what may change?
5. **Choose the appropriate guarantee level:** basic, strong, or no-throw within a specific scope.
6. **Do not promise a strong guarantee beyond what you can control.**
7. **Validate before mutation** whenever possible.
8. **Prepare data in local/immutable candidates**, committing last.
9. **Check for overflow and other throwing operations** before assigning.
10. **Do not expose mutable internal state** via getters or input aliases.
11. **Account for callbacks/reentrancy** that could observe intermediate state.
12. **If there are multiple writers, add properly scoped locks/CAS** instead of only `volatile` on multiple fields.
13. **If partial progress is allowed, document clearly** which items may have committed.
14. **If resources are involved, define ownership and cleanup**, using try-with-resources where appropriate.
15. **Preserve cause and suppressed exceptions** when both operation and cleanup fail.
16. **Treat file/network writes as potentially partial**; do not infer rollback from `IOException`.
17. **For DB transactions, define isolation, commit, rollback, and unknown states.**
18. **For RPCs with side effects, use idempotency/state reconciliation** before retrying.
19. **Are `FAILED`/`CLOSED`/`UNKNOWN` states clearly defined?**
20. **Do not catch exceptions and return fake success** without genuine recovery.
21. **Test failure paths at every stage**: validation, prepare, write, notification, commit, close.
22. **Assert invariants and before–after snapshots**, not just the exception type.
23. **Verify resources and external side effects**, not just Java fields.
24. **Document retry/reuse policies in JavaDoc** after an exception.
25. **Evaluate API compatibility** if changing exception types or exceptional postconditions.

## 50. Conclusion

**API design does not end with "which exception the method throws."** A reliable contract must define **valid state before calling, state after success, and state after failure**.

On failure, there are three common commitments: the **basic guarantee** preserves invariants despite partial progress; the **strong guarantee** keeps observable state unchanged within the advertised scope; the **no-throw guarantee** is for operations that can genuinely be designed not to let exceptions escape under valid conditions. Java does not automatically verify any of these three promises.

In practice, prefer **validate → prepare → commit**, use immutable snapshots/copy-then-swap where appropriate, check for overflow before assigning, manage resources with clear contracts, and write failure tests at every step. At the same time, remember that **I/O writes can be partial, transaction commits can be unknown, and timeouts from external systems do not prove side effects did not occur**.

The most important question to review every API with is:

> **"If the method stops with an exception right at this step, what can the caller trust about the current state and what is it allowed to do next?"**

Answering that question with concrete invariants, exceptional postconditions, and tests is the foundation of **exception-safe Java APIs**.
