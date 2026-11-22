# Relationship Between Exceptions, Method Contracts, and Program State — Java Core Exception

> **Context:** Java Core → Exception → Overview. An exception is not just a message saying “an error occurred”. It is also an **abrupt way for a method to complete**, directly affecting what the method commits to the caller and the state of data that was modified before the error appeared. Understanding these three elements together helps design easy-to-use APIs, avoid corrupting data, and write testable error-handling code.

## 1. Three Questions to Answer Together

When calling a method that can fail, identify:

1. **Method contract:** What conditions must the caller provide? If it succeeds, what value/result will be received? What failure types are reported?
2. **Exception:** If it does not complete normally, what does the method throw, where, does it propagate outward, and at what layer can the caller handle it?
3. **Program state:** At the moment the exception exits the method, to what extent have objects, collections, files, resources, or external systems changed?

For example, a `transfer(from, to, amount)` method might commit to:

- Preconditions: valid, distinct accounts, `amount > 0`, sufficient balance, and the addition result does not overflow.
- Upon normal return: the source balance decreases by exactly `amount`, the destination increases by exactly `amount`; the sum of both balances is preserved.
- If it throws an exception due to invalid data, insufficient balance, or overflow: both balances **remain unchanged**.
- Invariant: balances are non-negative and do not exceed the representable range of the data type.

The commitment “on failure, do not change balances” is an important part of the API even though the Java signature does not express it. Merely adding `throws SomeException` **does not automatically create** this commitment.

### 1.1. Normal and Abrupt Are Two Completion Paths

A Java method call can:

- **Complete normally:** run to the end or `return`. The caller receives the return value if the method has a return type other than `void`.
- **Complete abruptly due to an exception:** a `throw` or a nested call raises an unhandled exception. The current method does not return a normal result; the runtime searches for an appropriate handler. Normal statements after the point where the exception occurs are skipped.

A method may have already performed some state changes **before** the exception occurs. Therefore, you cannot deduce “once it throws, all previous operations are undone”. Java does not automatically roll back assignments, collection modifications, file writes, or network requests.

```text
Caller calls method()
       │
       ▼
 Check input conditions
       │
       ▼
 Perform work ─────────────────────┐
       │                           │
       ▼                           ▼
 return / finish            exception occurs
       │                           │
       ▼                           ▼
 caller uses result       find matching catch, stack unwinding
                                   │
                                   ▼
                           state may have changed
```

On the exception path, `finally` and corresponding resource-closing operations may execute as the stack unwinds. This helps with cleanup, but it does not mean that previous business changes are undone.

## 2. What Is a Method Contract?

A **method contract** describes the caller's obligations and the method's guarantees. It is usually expressed through the name, parameters, return type, Javadoc, validation, exceptions, and tests. There are four parts to consider:

| Component | Question | Example with `withdraw(amount)` |
| --- | --- | --- |
| **Precondition** | What must the caller ensure or accept that the method checks? | `amount > 0`; the account object exists. |
| **Postcondition (on success)** | After the method returns normally, what is guaranteed to be true? | The balance decreases by the exact withdrawal amount and is non-negative. |
| **Invariant** | What properties of the object must remain true at valid observation points? | The balance is non-negative; internal data satisfies the class's rules. |
| **Exceptional guarantee** | When the method throws an exception, is the state still safe to use, and is it preserved? | The balance remains unchanged for the errors stated in the contract. |

The Java compiler checks data types, accessibility, syntax, and some checked exception rules. The compiler **cannot prove** all preconditions, postconditions, invariants, or the degree of state rollback. Developers must implement, document, and test them themselves.

### 2.1. Distinguishing Preconditions from Internal Checks

An API may require the caller not to pass negative values; when the caller violates this, the method may actively throw `IllegalArgumentException` to report a contract violation. Another API might treat “insufficient balance” as a normal business situation that should yield `false` or a dedicated exception type. **Both approaches can be reasonable** if the contract is consistent and the caller knows how to handle it.

A precondition is not necessarily something the compiler checks. `int amount` only guarantees it is a Java integer, not that `amount > 0`. The type `String path` likewise does not guarantee the path exists.

### 2.2. Postconditions Apply Only on Success, Unless the Contract States Otherwise

Suppose `saveOrder(order)` promises to return an order ID after saving successfully. If it throws `IOException`, the caller must not assume the order was definitely not written. The exception may occur **after** part or all of the data was sent/written, before the caller received confirmation.

Therefore, you need to write a separate commitment for the failure path: “nothing changed”, “may have been partially saved”, “state is still valid but result is undetermined”, or “must reload from the data source”. Do not use the phrase “rolls back on failure” if no rollback mechanism actually exists.

### 2.3. Object Invariants and Valid State

An invariant is a property that must always hold at points where the API allows observation. For example, a balance-managing class does not allow negative numbers, a collection only holds positive quantities, or a pair of fields satisfies `start <= end`. If a method updates the first field and then throws before updating the second field, the invariant can be broken.

In sequential code that is not observed between steps, intermediate state may temporarily change; the key requirement is that state at **public boundaries** remains consistent with the contract. In multithreaded programs, intermediate changes may be visible to other threads if synchronization is lacking; the exception mechanism itself does not provide atomicity or thread safety.

## 3. Exceptions as Signals of Contract Failure

Distinguish three commonly confused concepts:

- **`throw`**: a statement that creates an abrupt completion path by throwing a `Throwable` object.
- **`throws`**: a part of the method declaration for checked exceptions that may escape. Unchecked exceptions can also be declared for documentation, though the compiler does not require it.
- **`catch`**: a place to handle an exception of a compatible type; it can recover, translate, add context, or rethrow.

Conceptual example:

```java
int parsePositive(String text) {
    int result = Integer.parseInt(text); // May throw NumberFormatException.
    if (result <= 0) {
        throw new IllegalArgumentException("Giá trị phải dương");
    }
    return result;
}
```

This is a **method illustration snippet**, not a standalone program. The caller has two failure types of interest: `NumberFormatException` when the string is not a valid integer, and `IllegalArgumentException` when it parses but the value is not positive. Both are unchecked; `throws` does not need to be declared. `NumberFormatException` inherits from `IllegalArgumentException`, so if the caller uses two `catch` blocks, the `NumberFormatException` block must be placed first.

### 3.1. How Do Checked and Unchecked Exceptions Relate to Contracts?

| Category | Compiler mechanism | Example | Meaning for API design |
| --- | --- | --- | --- |
| **Checked exception** | Must be caught or declared when it can escape the method, unless language rules permit otherwise | `IOException` | When signing the API contract, the caller is forced to consider the error path at the syntax level. |
| **Unchecked exception** | Not required to be caught or declared | `IllegalArgumentException`, `IllegalStateException` | Can be used for contract violations, inappropriate state, or many other situations; still needs documentation and tests. |
| **`Error`** and subclasses | Not required to be caught or declared | `OutOfMemoryError` | Usually represents severe failures; normal applications do not promise to recover from every `Error`. |

Exact technical rule: checked exceptions are subclasses of `Throwable` that are **not** in the `RuntimeException` or `Error` branches. In practice, Java APIs usually use subclasses of `Exception` outside the `RuntimeException` branch.

**Do not infer severity from checked/unchecked.** An I/O error from a missing file can be checked and recoverable; an unchecked error from invalid data can also be handled at the input layer. Choose the exception type based on the contract's meaning and how the caller is expected to use the API.

### 3.2. The Promise of `throws` Has Limits

The signature:

```java
void loadConfig() throws java.io.IOException
```

tells the caller that `IOException` may escape the method. It **does not** say that:

- the exception will definitely occur;
- the method can only throw this exact type;
- the method has not modified data before throwing;
- I/O operations are automatically undone;
- catching the exception is enough for the caller to guarantee valid state;
- the JVM will handle every possible error.

Unchecked exceptions and `Error` can still occur even if they do not appear in `throws`. State behavior on failure must be specified through separate documentation, design, and testing.

### 3.3. Inheritance and Overriding Contracts

When overriding, a subclass method **must not widen the checked exception list** in a way incompatible with the superclass/interface declaration. It can declare a narrower set of checked exceptions, declare none, or throw unchecked exceptions. This rule ensures code using an object via its supertype still compiles against the supertype's declared contract.

However, substitutability also requires a **behavioral** contract: a subclass should not arbitrarily impose stricter preconditions or weaken guarantees promised by the interface. The compiler cannot detect all violations of state and business semantics.

For example: the interface `Account.withdraw(positiveAmount)` promises to preserve the balance on failure. An implementation that throws the same exception type but deducts money before throwing still violates the contract, even though the code compiles normally.

## 4. State Guarantees When an Exception Occurs

There is no single uniform guarantee level for all Java methods. You must read the documentation or explicitly establish your API's own commitment.

| Guarantee level | State after exception | Practical example |
| --- | --- | --- |
| **No guarantee** | May have broken invariants; the object should not be used further until recovered or replaced. | A custom method updates multiple fields but aborts halfway with no recovery. |
| **Basic guarantee** | The object still satisfies invariants and does not leak resources managed by the API, though values may have partially changed. | Processed the first three elements in a list and stopped at the erroneous element; the list remains valid. |
| **Strong guarantee** | For the committed failure set, the operation has the observable effect as if it had never been performed: related state remains unchanged. | Parse all input into a copy; assign the new snapshot only after all validation steps succeed. |
| **No-throw guarantee** | Within the promised range of conditions, the method does not let an exception escape. | A properly designed close/cleanup operation with a contract not to throw under predefined conditions. |

These guarantee names are commonly encountered when discussing **exception safety**; Java does not enforce them automatically. “No-throw” cannot be interpreted as a promise against all environmental disasters such as JVM termination, power loss, or extreme out-of-memory conditions.

Three things are not equivalent:

1. **Object invariant preserved:** data remains valid, even if values differ from before.
2. **Strong exception safety:** for the considered failure types, the observable effect is as if the operation were not performed.
3. **Atomicity/transactionality:** the operation is observed as a single unit under concurrency or transaction mechanisms; usually requires synchronization, a database transaction, or a specialized protocol.

A method with strong exception safety in sequential execution is not necessarily atomic to another thread. And rolling back data in RAM does not automatically roll back files or network requests already sent.

## 5. Java 17 Program: Validate First, Then Mutate State

The following example uses two accounts with non-negative integer balances. The transfer method checks all expected failure cases **before the two assignments**, to preserve both balances if there is an input error, insufficient funds, or overflow.

Create the file `TransferContractDemo.java`:

```java
import java.util.Objects;

public class TransferContractDemo {
    static final class Account {
        final String id;
        private int balance;

        Account(String id, int initialBalance) {
            this.id = Objects.requireNonNull(id, "id");
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Số dư âm");
            }
            this.balance = initialBalance;
        }

        int balance() {
            return balance;
        }
    }

    static void transfer(Account from, Account to, int amount) {
        Objects.requireNonNull(from, "from");
        Objects.requireNonNull(to, "to");

        if (from == to) {
            throw new IllegalArgumentException("Trùng tài khoản");
        }
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        if (from.balance < amount) {
            throw new IllegalStateException("Không đủ số dư");
        }

        // Check for overflow before modifying any account.
        int newToBalance = Math.addExact(to.balance, amount);
        int newFromBalance = from.balance - amount;

        // These two steps have no remaining checks/parsing that can fail.
        from.balance = newFromBalance;
        to.balance = newToBalance;
    }

    public static void main(String[] args) {
        Account a = new Account("A", 100);
        Account b = new Account("B", 40);

        System.out.println("Ban đầu: A=" + a.balance() + ", B=" + b.balance());
        transfer(a, b, 30);
        System.out.println("Sau chuyển: A=" + a.balance() + ", B=" + b.balance());

        try {
            transfer(a, b, 90);
        } catch (IllegalStateException e) {
            System.out.println("Từ chối: " + e.getMessage());
        }
        System.out.println("Sau thiếu tiền: A=" + a.balance()
                + ", B=" + b.balance());

        try {
            transfer(a, b, 0);
        } catch (IllegalArgumentException e) {
            System.out.println("Tham số sai: " + e.getMessage());
        }

        Account full = new Account("FULL", Integer.MAX_VALUE);
        try {
            transfer(a, full, 1);
        } catch (ArithmeticException e) {
            System.out.println("Không chuyển vì: "
                    + e.getClass().getSimpleName());
        }
        System.out.println("Cuối cùng: A=" + a.balance()
                + ", B=" + b.balance()
                + ", FULL=" + full.balance());
    }
}
```

Compile and run with Java 17+:

```bash
javac -encoding UTF-8 TransferContractDemo.java
java TransferContractDemo
```

Expected stdout, matching the code above:

```text
Ban đầu: A=100, B=40
Sau chuyển: A=70, B=70
Từ chối: Không đủ số dư
Sau thiếu tiền: A=70, B=70
Tham số sai: Số tiền phải dương
Không chuyển vì: ArithmeticException
Cuối cùng: A=70, B=70, FULL=2147483647
```

### 5.1. Practical Contract of `transfer`

**Preconditions and violation handling:**

- Both accounts must be non-`null`; `Objects.requireNonNull` throws `NullPointerException` if violated.
- Cannot transfer from an account to itself; violation throws `IllegalArgumentException`.
- `amount` must be positive; otherwise throws `IllegalArgumentException`.
- The source account must have sufficient funds; if insufficient, throws `IllegalStateException` per the illustrative API choice.
- The destination balance after addition must fit within `int` range; `Math.addExact` throws `ArithmeticException` on overflow.

**Postconditions on normal completion:**

- `from.balance` equals its old value minus `amount`.
- `to.balance` equals its old value plus `amount`.
- Both balances remain non-negative; the total balance of the account pair is preserved in mathematical arithmetic.

**Exceptional guarantee:** for the checked errors above, both balances remain unchanged. Because the program calls `Math.addExact` before updating, even overflow does not lose money from the source account.

**Example limitations:** this is an **in-memory sequential** model. It has no locks and is not safe for concurrent calls on the same accounts. It is not a database transaction or distributed transaction, does not handle process crashes mid-operation, cannot represent real currency with `int` in production systems, and does not guarantee atomicity for multithreaded observation. The goal here is to demonstrate an exception-path design technique, not to build a real bank.

### 5.2. Why Statement Order Determines the Guarantee Level

Suppose it were written incorrectly:

```java
// Counterexample illustration inside a method; not a standalone program.
from.balance -= amount;
to.balance = Math.addExact(to.balance, amount);
```

If `Math.addExact` throws `ArithmeticException` after deducting money from the source, the method exits and **does not automatically undo** the subtraction. At that point, one side's state has changed while the other has not.

Fix this by checking and computing the new values first, then writing to state as in the full example. In general:

```text
Wrong: mutate A → operation that may fail → mutate B
Right: validate → prepare new data → commit changes
```

The “validate then commit” recipe is useful when all expected errors can be checked upfront and the commit phase is short and reliable. If the commit itself still has operations that can fail (writing a file, calling an API, allocating memory, callbacks, or third-party collections), you need a transaction mechanism, rollback/compensation, or to accept a weaker guarantee and document it clearly.

## 6. Partially Modified State: Distinguishing Basic from Strong Guarantee

A very common example: adding parsed elements one by one into an existing list.

```java
// Illustration inside a method with variables numbers and inputs.
for (String value : inputs) {
    numbers.add(Integer.parseInt(value));
}
```

If `inputs = ["10", "20", "sai", "30"]`, the first two elements may have already been added to `numbers` before `Integer.parseInt("sai")` throws `NumberFormatException`. With a regular `ArrayList`, the list may still be valid but partially modified: that outcome fits the **basic guarantee**, not the strong guarantee. The compiler will not warn about this.

The solution when the contract requires “replace all or keep unchanged” is to build a complete version before publishing the new state.

### 6.1. Java 17 Program: Snapshot Replaced Only When Preparation Succeeds

Create the file `SnapshotContractDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SnapshotContractDemo {
    static final class NumberStore {
        private List<Integer> values = List.of();

        void replaceAll(List<String> texts) {
            Objects.requireNonNull(texts, "texts");

            List<Integer> candidate = new ArrayList<>();
            for (String text : texts) {
                int parsed = Integer.parseInt(text);
                if (parsed <= 0) {
                    throw new IllegalArgumentException("Số phải dương");
                }
                candidate.add(parsed);
            }

            // Prepare the immutable snapshot before changing state.
            List<Integer> ready = List.copyOf(candidate);
            values = ready;
        }

        List<Integer> snapshot() {
            return values;
        }
    }

    public static void main(String[] args) {
        NumberStore store = new NumberStore();

        store.replaceAll(List.of("1", "2"));
        System.out.println("Ban đầu: " + store.snapshot());

        try {
            store.replaceAll(List.of("3", "sai", "4"));
        } catch (NumberFormatException e) {
            System.out.println("Lỗi: " + e.getClass().getSimpleName());
        }
        System.out.println("Sau lỗi parse: " + store.snapshot());

        try {
            store.replaceAll(List.of("5", "0"));
        } catch (IllegalArgumentException e) {
            System.out.println("Lỗi: " + e.getMessage());
        }
        System.out.println("Sau lỗi điều kiện: " + store.snapshot());

        store.replaceAll(List.of("7", "8", "9"));
        System.out.println("Sau cập nhật đúng: " + store.snapshot());
    }
}
```

Run:

```bash
javac -encoding UTF-8 SnapshotContractDemo.java
java SnapshotContractDemo
```

Stdout:

```text
Ban đầu: [1, 2]
Lỗi: NumberFormatException
Sau lỗi parse: [1, 2]
Lỗi: Số phải dương
Sau lỗi điều kiện: [1, 2]
Sau cập nhật đúng: [7, 8, 9]
```

Here, `candidate` is local data. All parsing, validation, and immutable snapshot creation happen before `values = ready`. If any of those steps fail, the `values` field keeps its old reference. When all steps succeed, a single reference assignment puts the new snapshot into use. `List.copyOf` creates an unmodifiable list; a caller receiving the list from `snapshot()` cannot use `add` or `remove` to alter the store's state.

**Commitment to state accurately:** keeping the `values` field unchanged when an error occurs during preparation is a strong guarantee **for the described internal state**. The example does not yet satisfy thread-safety requirements: to publish a snapshot across threads, you need to consider `volatile`, synchronization, or appropriate concurrency utilities. And creating a snapshot costs memory; whether this trade-off is acceptable depends on the situation.

### 6.2. Copy-on-Write, Validate-Before-Mutate, and Rollback

Three common approaches:

| Approach | When to use | What to watch out for |
| --- | --- | --- |
| **Validate-before-mutate** | All preconditions can be checked upfront and the write operation is short, unlikely to raise expected errors. | Must also check overflow, `null` references, caller-side mutations, and race conditions. |
| **Copy/prepare then publish** | Replacing an entire data structure and wanting to preserve the old snapshot if parsing/validation fails. | Costs memory/work; publication across threads needs consistent visibility mechanisms. |
| **Rollback/compensation** | Multiple state sources have already been modified and not everything can be checked upfront. | Rollback itself can fail; especially difficult with I/O, network, and external side effects already emitted. |

You cannot “catch `Exception` and roll back everything” if the API/design lacks a sufficiently reliable recovery mechanism. You must clearly define the scope of state under your control.

## 7. Exceptions Propagating Across Layers: Who Is Responsible for What?

Suppose an application has the flow:

```text
UI / CLI
    ↓ calls
OrderService.placeOrder()
    ↓ calls
InventoryRepository.reserve()
    ↓ calls
Database / file / external API
```

Each layer has a different responsibility:

- **Infrastructure layer:** reports technical causes such as `IOException`, timeouts, data access errors; if an API can return ambiguous results, it must clearly state its limits.
- **Business layer:** enforces rules such as positive quantities, not exceeding inventory; decides whether an operation is considered successful.
- **Presentation/interface layer:** translates failures into messages/results for the user or caller, decides when to re-enter input or retry.

If a lower layer throws an exception, the upper layer needs to read **both the error type and the remaining state**. For example, when processing an order, a response error from a payment gateway after the request was sent does not prove that money was not deducted. Uncontrolled retries can create duplicate operations; in integrated systems, an idempotency key, confirmation status, or reconciliation mechanism is often needed.

This is a direct consequence of the relationship between exceptions and state; `catch` itself cannot deduce the outcome of an external operation solely from the fact that it threw an error.

### 7.1. Catch Where a Sensible Action Can Be Taken

A useful principle: **catch an exception where there is enough information to handle it, translate it at the right layer, or clean up**. There is no need to catch every exception right where it occurs.

For example, a pure computation method can let `IllegalArgumentException` propagate to the caller. The CLI layer catches it and prompts the user to re-enter input. Conversely, if a service catches the exception and silently returns `null`, the caller may confuse “no data” with “failed mid-way”, leading to incorrect business state.

Distinguish clearly:

- **Actual handling:** choosing a recovery strategy, returning a structured error status, fixing input, stopping safely, or deciding to retry.
- **Contextual translation:** wrapping a low-level exception into a higher-level exception, preserving `cause`.
- **Cleanup:** releasing resources with try-with-resources; cleanup is not necessarily business error handling.
- **Logging only:** can help observability, but if the error is then swallowed without an appropriate contract, the caller's state will be misunderstood.

### 7.2. Wrap Exceptions While Preserving the Cause

The following snippet is an **illustration inside a method**, not a standalone program:

```java
try {
    repository.load();
} catch (java.io.IOException e) {
    throw new IllegalStateException("Không thể nạp cấu hình", e);
}
```

`e` becomes the **cause** of the new `IllegalStateException`. When reading the stack trace, developers can find the root cause. You should use a constructor that accepts a cause or `initCause` per the appropriate API rather than only taking `e.getMessage()` and discarding the original object.

Do not translate all errors into an overly generic exception if the caller genuinely needs to distinguish “not found”, “unauthorized”, “invalid data”, and “service unavailable”. At the same time, do not expose sensitive information (private paths, accounts, tokens, secret SQL queries) in messages returned to users.

## 8. `finally` and Try-with-Resources Guarantee Cleanup, Not Business Rollback

Consider:

```java
try {
    balance -= 10;
    doSomethingThatMayThrow();
} finally {
    System.out.println("Dọn dẹp");
}
```

This is an illustrative snippet inside a method. If `doSomethingThatMayThrow()` throws an exception, `finally` normally still runs, **but `balance` has already been reduced by 10**. A `finally` block does not automatically undo assignments, reinitialize objects, or determine whether a business transaction succeeded.

In particular, avoid `return` or throwing a new exception inside `finally` if doing so masks the original error. `finally` is also not guaranteed to run when the JVM/process terminates abruptly.

### 8.1. Resource Closing Failure: Primary and Suppressed Exceptions

Try-with-resources is the preferred way to manage `AutoCloseable` objects. There are situations where the main operation fails **and** `close()` also fails. Java keeps the exception from the try block body as the primary exception and places the error raised during closing into the **suppressed** list.

Create the file `SuppressedContractDemo.java`:

```java
import java.io.IOException;

public class SuppressedContractDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("lỗi đóng");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("lỗi xử lý");
        } catch (IOException e) {
            System.out.println("Chính: " + e.getMessage());
            System.out.println("Số lỗi suppressed: "
                    + e.getSuppressed().length);
            System.out.println("Suppressed đầu: "
                    + e.getSuppressed()[0].getMessage());
        }
    }
}
```

Run:

```bash
javac -encoding UTF-8 SuppressedContractDemo.java
java SuppressedContractDemo
```

Stdout:

```text
Chính: lỗi xử lý
Số lỗi suppressed: 1
Suppressed đầu: lỗi đóng
```

The `close()` method is called when leaving the block. The closing error does not replace the primary error in this case; instead, it is attached to `getSuppressed()`. If the block body does not throw an error but `close()` throws, the closing exception can become the exception escaping outward. With multiple resources, Java closes them in reverse order of declaration.

Resource cleanup and business rollback are two different responsibilities: closing a connection does not automatically cancel already-committed changes; transaction rollback only exists if the corresponding transaction mechanism is used properly.

## 9. Deciding Exception Types Based on Contract and Recoverability

When writing an API, answer first: **what action can the caller take on failure?** Only then choose the result/exception type.

| Situation | A suitable design | What must be documented |
| --- | --- | --- |
| Invalid parameters (negative quantity, invalid `null` object) | `IllegalArgumentException` / `NullPointerException` per API semantics | Valid conditions; when violated, whether state changes. |
| Current state does not allow the operation | `IllegalStateException` or a dedicated business exception | State rules, outcome on failure. |
| File cannot be read | `IOException` (checked) | Caller catches/declares; whether target content was affected or not. |
| Data not found is a normal case | `Optional<T>` / structured result, or an exception if the API specifies so | How “not found” differs from “query failed”. |
| User input fails to parse | Catch `NumberFormatException` at the input boundary or convert to a validation result | How the user can re-enter input; do not use uncontracted dummy values. |
| Network request receives no response | Appropriate connection/timeout exception; result state may be undetermined | Retry policy, deduplication, and how to confirm the outcome. |

Custom exceptions should only exist when the caller needs to classify/react differently or the API wants to convey meaningful semantics. There is no need to create `MyIllegalArgumentException` just to rename a standard error that already expresses the issue well.

### 9.1. When Should You Return a Result Instead of Throwing an Exception?

If a situation is an expected outcome branch that occurs frequently (a search finding no element, a user testing validity), the API can use `boolean`, `Optional`, or a clear status result type instead of using exceptions for routine control flow.

Conversely, “wrapping everything in `boolean`” can also lose the error cause, leaving the caller unaware of whether the operation partially modified state. Choose the representation based on nature: invalid input data, technical failure, or normal business result are concepts that need to be distinguished.

### 9.2. Retry Policies Must Depend on State, Not Just Exception Type

Retrying is usually reasonable when the operation is **idempotent** (repeating it produces no unintended extra effects) or has a deduplication mechanism. If the caller does not know whether the operation succeeded on the server side, unconditional retrying can duplicate money transfers, emails, or orders.

An exception only indicates that the call did not complete normally from the current perspective. The actual state of an out-of-process system may need to be verified using a status-lookup API or a dedicated protocol.

## 10. Documenting Clear Contracts in Javadoc

The following example illustrates **how to document the contract** for `transfer` in Section 5; the signature is repeated only to introduce Javadoc and does not form a standalone file:

```java
/**
 * Transfers amount from from to to when conditions are met.
 *
 * <p>Preconditions: both accounts are non-null, distinct,
 * amount is positive, source has sufficient funds, and destination does not overflow int.</p>
 *
 * <p>Upon normal return: from's balance decreases by amount,
 * to's balance increases by amount.</p>
 *
 * <p>If any of the checks below fail,
 * the balances of both accounts remain unchanged.</p>
 *
 * <p>Not safe for concurrent calls on the same accounts.</p>
 *
 * @throws NullPointerException if from or to is null
 * @throws IllegalArgumentException if accounts are the same or amount <= 0
 * @throws IllegalStateException if source has insufficient balance
 * @throws ArithmeticException if destination balance overflows int
 */
static void transfer(Account from, Account to, int amount) {
    // Method body is in the full example in Section 5.
}
```

In real Javadoc, do not use the stub body above to replace the implementation. The takeaway is: `@throws` states **when and why** an error is raised, while the prose description states **the impact on state**. A good API usually needs both.

There is no need to document every unchecked exception that might arise from the VM or libraries; prioritize cases that are foreseeable and affect how the caller uses the API. The commitment must not be stronger than what the actual implementation can uphold.

## 11. Testing Contracts: Always Verify the Failure Path and Remaining State

A test that only checks `assertThrows(...)` is insufficient if the contract promises to preserve data. Tests should observe both the **exception** and the **state**.

The following JUnit 5 example is an **illustrative test snippet** using `TransferContractDemo` from Section 5, requiring a project with the corresponding JUnit Jupiter dependency to compile; it is not a standalone `javac` program:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class TransferContractDemoTest {
    @Test
    void insufficientFundsDoesNotChangeBalances() {
        var from = new TransferContractDemo.Account("A", 20);
        var to = new TransferContractDemo.Account("B", 8);

        assertThrows(IllegalStateException.class,
                () -> TransferContractDemo.transfer(from, to, 25));

        assertEquals(20, from.balance());
        assertEquals(8, to.balance());
    }

    @Test
    void overflowDoesNotDebitSource() {
        var from = new TransferContractDemo.Account("A", 10);
        var to = new TransferContractDemo.Account(
                "B", Integer.MAX_VALUE);

        assertThrows(ArithmeticException.class,
                () -> TransferContractDemo.transfer(from, to, 1));

        assertEquals(10, from.balance());
        assertEquals(Integer.MAX_VALUE, to.balance());
    }

    @Test
    void successfulTransferUpdatesBothBalances() {
        var from = new TransferContractDemo.Account("A", 20);
        var to = new TransferContractDemo.Account("B", 8);

        TransferContractDemo.transfer(from, to, 5);

        assertEquals(15, from.balance());
        assertEquals(13, to.balance());
    }
}
```

Because the two classes above do not declare a `package` and `Account` as well as `transfer` have package-private access, the test file must also be placed in the same package (in the example, the default package). In real projects, choose an appropriate package, access level, and test location.

A minimal test matrix:

| Case | Expected exception/result | State to verify |
| --- | --- | --- |
| Valid input | Method returns normally | Postconditions hold, invariants hold. |
| Invalid parameter | Documented exception type | State remains unchanged if the contract promises a strong guarantee. |
| Insufficient data / disallowed state | Exception or result per contract | No undocumented changes appear. |
| Overflow / parse error | Specific exception | Does not corrupt balances, lists, or internal data. |
| Failure after some side effects | Appropriate exception | Clearly determine progress made, rollback/compensation, or undetermined state. |
| Resource cleanup also fails | Correct primary/suppressed exceptions | Resource is handled per contract; original error is not lost. |

**Testing tip:** save a copy/snapshot before the call; after `assertThrows`, compare each relevant field, data structure, dependency call count, or observable effect. For external side effects, use a fake/mock or an appropriate integration environment, but do not treat verifying “the mock was called” as proof that the real system has transactions.

## 12. Common Mistakes

### 12.1. “Throwing an exception means nothing changed”

False. If `list.add`, a file write, or an HTTP send was already called before the error was thrown, the prior effect may still exist. You must identify the commit point and failure guarantee level; do not rely on intuition.

### 12.2. “Catching an exception restores the state”

False. `catch` provides a place to handle the error; it does not create a snapshot or undo log. If you want rollback, you must have a corresponding state-recovery mechanism. In particular, side effects outside the JVM often have no simple “undo” operation.

### 12.3. “`finally` always rolls back”

False. `finally` is used to run cleanup logic according to Java's rules; it does not automatically save old values or undo changes. `try-with-resources` helps close resources; a closed connection does not mean all external transactions were rolled back.

### 12.4. “Having `throws IOException` means the caller knows the entire contract”

False. The caller only knows part of the error path at the checked exception type level. They also need to know data integrity, resources, progress already made, retryability, and expected unchecked exceptions.

### 12.5. “Converting checked to unchecked solves the error”

False. Wrapping `IOException` in `RuntimeException` only changes how the compiler forces the caller to handle it. It does not fix the cause, restore state, or make anything safer. Only translate exception types at the right abstraction boundary and preserve the cause.

### 12.6. “Always catch `Exception` or `Throwable`”

Catching very broadly and then ignoring it often hides programming bugs, allowing corrupted state to spread silently. `Error` should generally not be caught as a normal business issue. At a centralized control boundary (for example, a worker loop), a broad handler may be appropriate, but it needs a clear policy for recovery, logging, stopping, or isolating work.

### 12.7. “Strong exception safety means thread-safe”

Incorrect. Replacing a reference after preparation can preserve the old state on the exception path in a single thread, but other threads still need proper visibility and synchronization rules. Two assignments updating two objects also do not automatically become an atomic transaction for concurrent observation.

### 12.8. “The exception message is the only contract to test”

Messages can change by locale, version, or messaging policy. If code needs to classify errors, prefer the exception type or documented error codes; compare exact text only when the message is genuinely part of the contract.

### 12.9. “Only the happy path needs step-by-step handling”

Serious bugs often appear on the failure path **after a change has already occurred**. Write failure tests at every boundary with a side effect: before updating, mid-update, after updating but before confirmation, during close, and on retry.

## 13. Self-Practice Exercises

**Exercise 1 — Identify the violated contract.** Given a hypothetical method:

```java
// Illustration snippet, assuming data is List<Integer> and input is List<String>.
void replace(List<String> input) {
    data.clear();
    for (String text : input) {
        data.add(Integer.parseInt(text));
    }
}
```

Method specification: “Replace the list if all strings are valid numbers; if there is an error, keep the old list.” Explain why `data.clear()` breaks the contract before parsing completes. Fix it by preparing a new list and then **replacing the field reference** once, if the design permits, as in Section 6. Do not just change it to `try/catch` and manually re-add old elements without considering the case where rollback also fails.

**Exercise 2 — Choose your own error-reporting approach.** Write `reserve(int quantity)` with a non-negative inventory invariant. For `quantity <= 0`, choose `IllegalArgumentException`; for a quantity exceeding inventory, clearly choose one of `IllegalStateException`, a business exception, or a structured result. Write Javadoc explaining the choice, postconditions, and failure guarantee; test both success and insufficient inventory.

**Exercise 3 — Predict exception and state.** In the transfer example, try replacing `Math.addExact` with `to.balance + amount`. What can happen near `Integer.MAX_VALUE`? Explain how Java integer overflow differs from an automatic exception. Then restore `Math.addExact` and verify the overflow test.

**Exercise 4 — Cause and suppressed.** Write a method wrapping `IOException` with a cause, then run `SuppressedContractDemo`. Point out the two different relationships: `getCause()` describes the error that led to the new exception, whereas `getSuppressed()` stores secondary errors raised while the primary error was being handled/cleaned up.

**Exercise 5 — Reason about retries.** A call to `placeOrder()` sends a request and then times out before receiving a response. List at least three possibilities for the server-side state: the request never arrived, arrived but did not complete, or completed but the response was lost. Propose a confirmation/idempotency method before automatically resending.

## 14. Checklist for Designing APIs with Exceptions

Before publishing an important method, answer each item in turn:

- [ ] Are preconditions clear and checked before significant side effects?
- [ ] Can postconditions after `return` be verified by tests?
- [ ] Are the invariants of every involved object preserved when an error occurs?
- [ ] For each foreseeable exception, is data unchanged, partially modified, or undetermined?
- [ ] Do `throws` and `@throws` accurately reflect checked exceptions and main failure cases?
- [ ] Does the API throw appropriate exceptions without hiding programming bugs or using overly broad types?
- [ ] If translating exceptions, are `cause` and necessary context preserved?
- [ ] Are resources closed with try-with-resources, and are suppressed errors preserved when diagnostically valuable?
- [ ] Is there a clear boundary between in-memory operations and external side effects?
- [ ] Does the caller have enough information to decide on handling, rollback, state confirmation, or safe retry?
- [ ] If multiple threads can call concurrently, are atomicity/visibility guaranteed beyond exception safety?
- [ ] Do tests check both the exception type **and the state after failure**, not just the error message?

**Conclusion:** the contract states what must be true when a method succeeds and when it fails; the exception is the signal of the abrupt completion path; the state shows what effects actually occurred. To design a reliable API, you must specify and test all three elements from the moment you write the method, especially at the boundaries before and after each side effect.
