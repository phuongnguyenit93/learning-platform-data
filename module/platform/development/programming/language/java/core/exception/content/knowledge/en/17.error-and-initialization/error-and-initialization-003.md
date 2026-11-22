# Do Not Use `assert` for Public Input Validation in Java

In Java, `assert` is a diagnostic tool for assumptions that a program **should always guarantee to be true through internal logic**. It is **not** a mechanism for validating user data, parameters of `public` methods, public constructors, or data from files, networks, and databases. The most important reason: **assertions can be disabled at runtime**, rendering the entire `assert` statement ineffective and **evaluating neither the condition expression nor the detail message**.

Incorrect example:

~~~java
public void setAge(int age) {
    assert age >= 0 : "age must be non-negative";
    this.age = age;
}
~~~

This is an **illustrative snippet in a class with an `age` field**. If the program runs without assertions enabled, a negative value can still be assigned to the field. If assertions are enabled, the error thrown is `AssertionError` under the `Error` hierarchy, rather than a standard invalid-argument exception that API callers can expect.

Appropriate approach for a public API:

~~~java
public void setAge(int age) {
    if (age < 0) {
        throw new IllegalArgumentException("age must be non-negative");
    }
    this.age = age;
}
~~~

Validation using `if` **always executes** when the method is called, regardless of whether assertions are enabled or disabled. This is the foundation of an API contract: invalid input must be rejected consistently across all deployment environments.

This lesson covers the rules in JLS §14.10, how to run `-ea`/`-da`, distinguishing `AssertionError` from `IllegalArgumentException`/`NullPointerException`, validating public constructors, records, collection indices, and state-mutating methods; when `assert` remains useful for **internal invariants**; why you should not put side effects in assertions; and Java 17+ examples with clear stdout.

## 1. What does `assert` in Java actually do?

Java has two forms:

~~~java
assert condition;
assert condition : detailExpression;
~~~

These are two **illustrative syntax patterns**, where `condition` is an expression of type `boolean` or `Boolean` and `detailExpression` is an expression suitable as a detail message.

According to JLS §14.10:

1. If assertions are **disabled**, the entire statement completes normally; **neither** the condition nor the expression after the colon is evaluated.
2. If assertions are **enabled**, Java evaluates the condition.
3. If the condition returns `true`, the statement completes normally; the detail expression after the colon **is not evaluated**.
4. If the condition returns `false`, Java evaluates the detail expression if present, constructs an `AssertionError` object, and throws it.
5. If evaluating the condition or the detail expression itself throws an error or exception, the statement can complete abruptly with that throwable before creating `AssertionError` through the normal path.

Therefore, `assert` is an **assertion that can be disabled via runtime configuration**, not a mandatory `if` condition.

| Construct | When condition is true | When condition is false | Can be skipped by the JVM based on assertion status? |
| --- | --- | --- | --- |
| `assert x > 0;` | Continues | `AssertionError` if enabled | **Yes** |
| `if (x <= 0) throw new IllegalArgumentException(...);` | Continues | `IllegalArgumentException` | **No** |
| `Objects.requireNonNull(value);` | Returns the non-`null` reference itself | `NullPointerException` | **No** |
| `Objects.checkIndex(index, length);` | Returns the valid index | `IndexOutOfBoundsException` | **No** |

A validly compiled `assert` does not mean it will be executed in an actual run. Conversely, an `if` condition or a call to `Objects.requireNonNull` is normal executable code that does not depend on the assertion-enabling flag.

## 2. Enabling and disabling assertions with `java -ea` and `java -da`

In a typical JVM, assertions in application classes are **disabled by default**, unless configured via the launcher, class loader, or related APIs. Common commands:

~~~bash
javac -encoding UTF-8 MyProgram.java
java -da MyProgram
java -ea MyProgram
~~~

Meaning:

- `-ea` or `-enableassertions`: enables assertions for the specified scope; the form without a suffix serves as the default for applicable application classes.
- `-da` or `-disableassertions`: disables assertions in the corresponding scope.
- The JVM can configure assertions **per class or package**; not all classes necessarily have the same status. In addition to launcher flags, class loaders provide APIs to set the desired status for classes yet to be initialized.
- Assertion configuration is typically determined when a class is initialized. Do not design business logic around toggling assertions on/off between two calls to the same class.

**JVM flags must be placed before the class name**: `java -ea MyProgram`, not `java MyProgram -ea`. In the second command, `-ea` is merely an element of `String[] args` passed to the program, not a JVM option.

When testing, running in both modes helps catch bugs like "with assertions enabled it rejects bad data, while with assertions disabled it silently accepts it." However, tests should emphasize **the same input contract in both modes**, rather than treating `-ea` as a mandatory production requirement to prevent errors.

## 3. Example 1: buggy code allows invalid data when assertions are disabled

Save as `BadPublicAssertDemo.java`:

~~~java
public class BadPublicAssertDemo {
    static String acceptAmount(int amount) {
        assert amount > 0 : "amount must be positive";
        return "accepted:" + amount;
    }

    public static void main(String[] args) {
        try {
            System.out.println(acceptAmount(-4));
        } catch (AssertionError ex) {
            System.out.println("error=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run twice:

~~~bash
javac -encoding UTF-8 BadPublicAssertDemo.java
java -da BadPublicAssertDemo
java -ea BadPublicAssertDemo
~~~

Output of the **`-da` run**:

~~~text
accepted:-4
~~~

Output of the **`-ea` run**:

~~~text
error=AssertionError
~~~

Same source code and same argument `-4`, yet two different outcomes:

1. When assertions are disabled, the check is skipped and the program produces **accepted:-4**, violating the expected precondition.
2. When assertions are enabled, the false condition produces `AssertionError`. The program intentionally catches this type to demonstrate the output; **catching AssertionError for normal input handling is not recommended**.
3. If `acceptAmount` is a public API, callers should not have to know whether their program is running with `-ea` enabled to predict whether the API will reject negative values.

This is why `assert` must not be used for parameters of a `public` method or public constructor, especially when inputs come from another caller, module, library, or service.

## 4. Public preconditions must be checked with mandatory execution flow

A public method has **preconditions**: for example, `quantity > 0`, `name != null`, `index >= 0`. Preconditions are part of the contract known to the caller. If violated, the method must fulfill its published policy, such as throwing `IllegalArgumentException`.

How to write it:

~~~java
public static int calculateCharge(int quantity) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive");
    }
    return quantity * 10;
}
~~~

This is an illustrative method placed in a Java class; the arithmetic is only meant to demonstrate the condition. If the product `quantity * 10` could overflow in a real application, additional checks are needed, such as `Math.multiplyExact`.

**The check does not depend on `-ea`** and executes before the method returns a result. You can use a helper for reuse, but the helper must be normal code, not hidden inside an assert expression.

### Example 2: public guard stable in all modes

Save as `PublicGuardDemo.java`:

~~~java
import java.util.Objects;

public class PublicGuardDemo {
    static String register(String name, int age) {
        Objects.requireNonNull(name, "name");

        if (name.isBlank()) {
            throw new IllegalArgumentException("name blank");
        }
        if (age < 0 || age > 150) {
            throw new IllegalArgumentException("age out of range");
        }
        return "registered:" + name + ":" + age;
    }

    static void show(String name, int age) {
        try {
            System.out.println(register(name, age));
        } catch (RuntimeException ex) {
            System.out.println("error="
                    + ex.getClass().getSimpleName()
                    + ":" + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        show("Ada", 36);
        show("", 36);
        show("Ada", -1);
        show(null, 20);
    }
}
~~~

~~~bash
javac -encoding UTF-8 PublicGuardDemo.java
java -da PublicGuardDemo
java -ea PublicGuardDemo
~~~

**Both runs print the exact same output**:

~~~text
registered:Ada:36
error=IllegalArgumentException:name blank
error=IllegalArgumentException:age out of range
error=NullPointerException:name
~~~

Here:

- `Objects.requireNonNull(name, "name")` is used to enforce that **a required reference must not be null**.
- `name.isBlank()` checks that the string is not empty or whitespace-only; that is distinct from a null check.
- `age` is validated against the business domain.
- `RuntimeException` is caught in **the demo to print the exception type name**, not as a recommendation to catch broadly in a real service.
- Whether assertions are enabled or disabled, the validation result does not change because the guard code is normal control flow.

This is the kind of stable behavior a public API must provide.

## 5. `AssertionError` is not `IllegalArgumentException`

Both are descendants of `Throwable`, but they belong to **different branches**:

~~~text
Throwable
 ├── Error
 │    └── AssertionError
 └── Exception
      └── RuntimeException
           ├── IllegalArgumentException
           ├── IllegalStateException
           ├── NullPointerException
           └── IndexOutOfBoundsException
~~~

Intended usage:

| Type | Appropriate context |
| --- | --- |
| `AssertionError` | A broken internal assumption, usually reflecting a bug that requires a code fix |
| `IllegalArgumentException` | The caller passed an invalid parameter value |
| `NullPointerException` | A reference is not allowed to be null; `Objects.requireNonNull` explicitly supports this |
| `IllegalStateException` | The object is in a state that does not permit the operation |
| `IndexOutOfBoundsException` | Invalid index or index range |
| Custom domain exception | When the API needs a domain-specific error, error code/attributes, or an explicit checked/unchecked policy |

**AssertionError extends Error**, not Exception. Therefore, `catch (Exception ex)` does not catch `AssertionError`. While one could write `catch (Throwable ex)` or `catch (AssertionError ex)`, catching broadly like that to mask assertion failures in operations usually misses the point: internal bugs should be fixed rather than pretending invalid input was handled.

You should not manually throw `AssertionError` when detecting user errors. If a user enters a negative quantity, that is data violating the contract, not necessarily a bug in the program's implementation.

## 6. Warning: `assert` can skip expressions with side effects

According to JLS §14.10, a disabled assertion **does not evaluate** its condition expression. If the expression calls a method with side effects, the program state can differ between the two run modes.

### Example 3: side effect lost when assertions are disabled

Save as `AssertSideEffectDemo.java`:

~~~java
public class AssertSideEffectDemo {
    static int calls = 0;

    static boolean incrementAndReportTrue() {
        calls++;
        return true;
    }

    public static void main(String[] args) {
        assert incrementAndReportTrue();
        System.out.println("calls=" + calls);
    }
}
~~~

~~~bash
javac -encoding UTF-8 AssertSideEffectDemo.java
java -da AssertSideEffectDemo
java -ea AssertSideEffectDemo
~~~

Output with `-da`:

~~~text
calls=0
~~~

Output with `-ea`:

~~~text
calls=1
~~~

Neither case throws `AssertionError` because the method returns `true`, yet the `calls` state differs. Placing logging, variable assignment, file reading, or API calls with side effects inside an `assert` condition can cause test and production environments to follow different control paths.

**Rule:** the `assert` condition and the expression after the colon should **have no meaningful side effects on the program**. If an operation needs to run, execute it as a normal statement first, and then use `assert` to check assumptions about the result.

Better example:

~~~java
int updated = updateState();
assert updated >= 0 : "internal invariant";
~~~

This is an illustrative snippet inside a method where `updateState()` is appropriate. `updateState()` always runs; the `assert` statement only observes the resulting value. However, if `updated >= 0` is a mandatory requirement for public data, you must still use a non-disableable check, not just an assert.

## 7. The detail expression after the colon is also conditionally evaluated

The form `assert condition : detailExpression;` does not evaluate `detailExpression` every time:

- Assertions **disabled**: neither expression is evaluated.
- Assertions **enabled and condition is true**: only `condition` is evaluated; `detailExpression` is not evaluated.
- Assertions **enabled and condition is false**: both are evaluated, and then an `AssertionError` is normally created with the detail message.

This is useful when constructing the diagnostic message is expensive: detailed information is only computed when the invariant fails. Still, the detail expression should be safe, without mutating state or compounding the error.

### Example 4: lazy detail evaluation

Save as `LazyAssertDetailDemo.java`:

~~~java
public class LazyAssertDetailDemo {
    static int descriptions = 0;

    static String describe(int value) {
        descriptions++;
        return "internal value=" + value;
    }

    public static void main(String[] args) {
        int x = -2;

        try {
            assert x >= 0 : describe(x);
            System.out.println("accepted=" + x);
        } catch (AssertionError ex) {
            System.out.println("error=" + ex.getMessage());
        }

        System.out.println("descriptions=" + descriptions);
    }
}
~~~

~~~bash
javac -encoding UTF-8 LazyAssertDetailDemo.java
java -da LazyAssertDetailDemo
java -ea LazyAssertDetailDemo
~~~

Output with `-da`:

~~~text
accepted=-2
descriptions=0
~~~

Output with `-ea`:

~~~text
error=internal value=-2
descriptions=1
~~~

The example increments a counter solely to **observe the exact evaluation behavior**. In production code, avoid designing `describe` to mutate state; it should be a function that only builds a safe description for diagnostics.

Do not use the expression after the colon to modify data, commit transactions, release resources, or emit business signals. Any mandatory operation must run independently of whether assertions are enabled or disabled.

## 8. Public constructors are also input boundaries

A constructor can receive untrusted input from another module. If you only write:

~~~java
public Account(String id) {
    assert id != null;
    this.id = id;
}
~~~

This is an illustrative snippet in an `Account` class with an `id` field. When assertions are disabled, an object can still be created with `id == null`, causing other methods to hit a delayed `NullPointerException` at a hard-to-diagnose location.

The safe approach is to validate immediately upon construction:

~~~java
public Account(String id) {
    this.id = java.util.Objects.requireNonNull(id, "id");
}
~~~

If there are additional conditions such as non-blank, no spaces, or matching a specific ID format, add `if` checks. Ensure the constructor **never returns an object in an invalid state** according to its contract.

### Example 5: validation in a constructor

Save as `ConstructorGuardDemo.java`:

~~~java
import java.util.Objects;

public class ConstructorGuardDemo {
    static final class Account {
        private final String id;

        Account(String id) {
            Objects.requireNonNull(id, "id");
            if (id.isBlank()) {
                throw new IllegalArgumentException("id blank");
            }
            this.id = id;
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) {
        System.out.println("ok=" + new Account("U-7").id());

        try {
            new Account(null);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getClass().getSimpleName());
        }

        try {
            new Account("   ");
        } catch (IllegalArgumentException ex) {
            System.out.println("blank=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ConstructorGuardDemo.java
java -da ConstructorGuardDemo
java -ea ConstructorGuardDemo
~~~

Output is **identical in both modes**:

~~~text
ok=U-7
null=NullPointerException
blank=IllegalArgumentException
~~~

The constructor rejects unsuitable input right at object creation, rather than accepting an object that violates its invariant and letting errors surface later. This is the difference between **enforcing an invariant with mandatory validation** and merely **asserting that an invariant already holds**.

When using inheritance, Java 17 constructors require an explicit `super(...)` or `this(...)` call to be placed first in the constructor per language rules. If you need to validate arguments before passing them to the superclass constructor, you can use a helper expression inside the arguments of `super(...)`, such as `super(Objects.requireNonNull(value, "value"))`, instead of trying to place an `if` statement before an explicit `super(...)` in Java 17.

## 9. Records and immutable objects must also validate before storing

Java 17 supports `record` for carrying immutable data at the component level. However, the `record` keyword **does not automatically validate** `null`, negative numbers, empty strings, or out-of-range values. Validation must be performed in the constructor when required by the contract.

### Example 6: compact constructor of a record

Save as `RecordGuardDemo.java`:

~~~java
import java.util.Objects;

public class RecordGuardDemo {
    record OrderLine(String sku, int quantity) {
        OrderLine {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("sku blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
        }
    }

    public static void main(String[] args) {
        OrderLine valid = new OrderLine("SKU-1", 3);
        System.out.println("valid="
                + valid.sku() + ":" + valid.quantity());

        try {
            new OrderLine("SKU-2", 0);
        } catch (IllegalArgumentException ex) {
            System.out.println("quantity="
                    + ex.getClass().getSimpleName());
        }

        try {
            new OrderLine(null, 2);
        } catch (NullPointerException ex) {
            System.out.println("sku="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 RecordGuardDemo.java
java -da RecordGuardDemo
java -ea RecordGuardDemo
~~~

Output in both modes:

~~~text
valid=SKU-1:3
quantity=IllegalArgumentException
sku=NullPointerException
~~~

The compact constructor validates parameters before the record stores its components. Just because data is immutable does not mean validation can be skipped; once an invalid value is stored, it is **hard to fix after the object is created**.

If a record holds a mutable collection, you should also consider defensive copying (such as `List.copyOf`) and a null-element policy; `assert` cannot replace these data-protection steps either.

## 10. Choosing the right exception for each type of public condition

Not every input error should throw the same exception. Choose according to the API's **contract** and usage context:

| Condition | Typically appropriate type | Example |
| --- | --- | --- |
| Numeric parameter out of domain | `IllegalArgumentException` | amount <= 0 |
| Required reference parameter must not be null | `NullPointerException` via `Objects.requireNonNull` | customerId == null |
| Index outside list bounds | `IndexOutOfBoundsException` | index < 0 or index >= size |
| Operation disallowed in current object state | `IllegalStateException` | calling mutate after close |
| Numeric text cannot be parsed as int | `NumberFormatException` | parseInt("foo") |
| Date-formatted input cannot be parsed | `DateTimeParseException` | LocalDate.parse("bad") |
| Business validation failure requiring field/code feedback | Custom exception or validation result | INVALID_QUANTITY |
| Internal assumption broken despite validated public input | `AssertionError` when assertions are enabled | postcondition that should always hold |

This table reflects **common design conventions**, not an exhaustive list. An API may choose a custom exception or a `Result<T>` type carrying error details. Most importantly, behavior on invalid public input must be **enforced consistently**, meaningful to callers, and documented.

Do not automatically use `AssertionError` just because a condition "should not happen." If the condition can be **triggered by a caller via public arguments**, use validation. If the condition represents an **implementation bug** that internal logic was supposed to prevent, an assertion can serve as an auxiliary diagnostic tool.

## 11. Validating collection indices: do not use `assert index >= 0`

For public methods accessing a list, checking only `index >= 0` is insufficient: the index must also be less than the size. If you use `assert`, when assertions are disabled, an invalid index can be accessed and fail deeper in the call stack—or even execute unintended logic before failing.

The JDK provides helpers:

- `Objects.checkIndex(index, length)` validates a single index.
- `Objects.checkFromToIndex(from, to, length)` validates a half-open range [from, to).
- `Objects.checkFromIndexSize(from, size, length)` validates a range by start index and size.

These APIs throw `IndexOutOfBoundsException` when arguments are invalid; they do not depend on `-ea`.

### Example 7: index-checking helper

Save as `IndexGuardDemo.java`:

~~~java
import java.util.List;
import java.util.Objects;

public class IndexGuardDemo {
    static String read(List<String> items, int index) {
        Objects.requireNonNull(items, "items");
        int checked = Objects.checkIndex(index, items.size());
        return items.get(checked);
    }

    public static void main(String[] args) {
        List<String> data = List.of("A", "B");

        System.out.println("ok=" + read(data, 1));

        try {
            read(data, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("index="
                    + ex.getClass().getSimpleName());
        }

        try {
            read(null, 0);
        } catch (NullPointerException ex) {
            System.out.println("list="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 IndexGuardDemo.java
java -da IndexGuardDemo
java -ea IndexGuardDemo
~~~

Output in both modes:

~~~text
ok=B
index=IndexOutOfBoundsException
list=NullPointerException
~~~

The benefit of validating near the boundary: callers receive an error for the **violated contract condition**, rather than waiting for a deeper operation to accidentally throw a less contextual error.

## 12. Invalid input vs. invalid state

A method can have both **parameter preconditions** and **object-state preconditions**. Both must be checked with normal executable code if violations can occur in expected API usage scenarios.

Consider an account:

- `withdraw(amount)` with `amount <= 0`: invalid parameter → `IllegalArgumentException`.
- Closed account: object is not in a state that permits withdrawal → `IllegalStateException`.
- After validation and update, `balance >= 0` can serve as an **internal invariant** checked with `assert` during debugging. However, the logic must **guarantee** the invariant even when assertions are disabled.

### Example 8: validation and supplementary invariant

Save as `StateContractDemo.java`:

~~~java
public class StateContractDemo {
    static final class Account {
        private int balance;
        private boolean closed;

        Account(int initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException(
                        "initial balance negative");
            }
            balance = initialBalance;
        }

        void withdraw(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }
            if (closed) {
                throw new IllegalStateException("account closed");
            }
            if (amount > balance) {
                throw new IllegalStateException("insufficient balance");
            }

            balance -= amount;
            assert balance >= 0 : "internal negative balance";
        }

        void close() {
            closed = true;
        }

        int balance() {
            return balance;
        }
    }

    public static void main(String[] args) {
        Account account = new Account(10);
        account.withdraw(4);
        System.out.println("balance=" + account.balance());

        try {
            account.withdraw(-2);
        } catch (IllegalArgumentException ex) {
            System.out.println("argument="
                    + ex.getClass().getSimpleName());
        }

        account.close();
        try {
            account.withdraw(1);
        } catch (IllegalStateException ex) {
            System.out.println("state="
                    + ex.getClass().getSimpleName());
        }

        System.out.println("final=" + account.balance());
    }
}
~~~

~~~bash
javac -encoding UTF-8 StateContractDemo.java
java -da StateContractDemo
java -ea StateContractDemo
~~~

Output is identical in both modes:

~~~text
balance=6
argument=IllegalArgumentException
state=IllegalStateException
final=6
~~~

Here, `assert balance >= 0` is merely a **supplementary diagnostic check** after the algorithm has already verified `amount` and the balance to prevent negative values. Even with assertions disabled, the object cannot be overdrawn through valid API paths in this example. That aligns with checking an internal invariant: **never use assert as the sole line of defense**.

Note that in multithreaded systems, synchronization or transactional state must be considered if multiple threads modify `balance` concurrently. An `assert` does not provide atomicity or thread safety.

## 13. The right place for `assert`: invariants controlled by internal code

An appropriate assertion typically expresses something **guaranteed by the implementation**, rather than something the caller must guarantee. For example, after a sorting algorithm or an internal enum dispatch branch, you can assert a property that cannot be false unless the code has a bug.

Pattern inside a method:

~~~java
Result result = algorithm(validatedInput);
assert result != null : "algorithm violated its postcondition";
return result;
~~~

This is **non-standalone illustrative code**: it assumes `Result`, `algorithm`, and `validatedInput` are defined. If `result != null` is an essential condition for correct behavior, production logic must still handle or be designed so that it does not produce an invalid state when assertions are disabled.

Places where internal assertions may be appropriate:

- Checking a mathematical relationship that an algorithm must always preserve.
- Checking an unreachable private branch when a switch/dispatch has handled all cases.
- Checking data-structure consistency after an operation whose public API inputs were already validated.
- Attaching contextual debug messages when an invariant is violated.

**However, "private" does not automatically turn every precondition into an invariant.** A private method receiving raw strings from the network or unvalidated data should also not rely on `assert` for mandatory checks. The criterion is **who guarantees the condition and whether it can be violated by valid system input**.

## 14. Do not use `assert` as a guard before dangerous side effects

A risky pattern:

~~~java
public void transfer(int amount) {
    assert amount > 0;
    debit(amount);
    credit(amount);
}
~~~

This is a non-standalone illustrative example assuming `debit` and `credit` exist. If assertions are disabled, the code may proceed with an invalid operation before detecting the problem, or fail halfway through. For money, inventory, access permissions, or resources, **validating inputs before side effects** is an essential part of design.

Better pattern:

~~~java
public void transfer(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException(
                "amount must be positive");
    }
    debit(amount);
    credit(amount);
}
~~~

These two snippets are only for comparing validation; a real money transfer requires additional checks such as authorization, balance verification, atomicity/transactions, and system error handling. The `if` here is a necessary condition, not a claim that the illustrative code is a complete financial implementation.

When receiving data from a request, parse and validate at the **trust boundary** before performing side effects. Assertions used for debugging internal steps cannot replace these barriers.

## 15. Input parsing errors should not be "checked with assert"

Some values come from strings: quantities in URLs, IDs, dates from CSVs. For example:

~~~java
int amount = Integer.parseInt(rawAmount);
assert amount > 0;
~~~

This is an illustrative snippet. There are two distinct failure modes:

1. If `rawAmount` cannot represent an `int`, `Integer.parseInt` throws **NumberFormatException**.
2. If `rawAmount` parses successfully but the value is non-positive, `assert` might **not run**, letting the data slip past the precondition.

A better approach is to express both steps explicitly:

### Example 9: parsing and validation with cause

Save as `InputBoundaryDemo.java`:

~~~java
import java.util.Objects;

public class InputBoundaryDemo {
    static int parseQuantity(String raw) {
        Objects.requireNonNull(raw, "quantity");

        final int quantity;
        try {
            quantity = Integer.parseInt(raw);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "quantity must be an integer", ex);
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
        return quantity;
    }

    static void show(String raw) {
        try {
            System.out.println("quantity=" + parseQuantity(raw));
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
            System.out.println("causeIsNFE="
                    + (ex.getCause() instanceof NumberFormatException));
        }
    }

    public static void main(String[] args) {
        show("3");
        show("abc");
        show("-5");
    }
}
~~~

~~~bash
javac -encoding UTF-8 InputBoundaryDemo.java
java -da InputBoundaryDemo
java -ea InputBoundaryDemo
~~~

Output in both modes:

~~~text
quantity=3
invalid=quantity must be an integer
causeIsNFE=true
invalid=quantity must be positive
causeIsNFE=false
~~~

`InputBoundaryDemo` **does not rely on assert**; empty/invalid data can be clearly classified. For parse errors, the wrapper preserves the original `NumberFormatException` object as its cause; for negative numbers, the independent business error needs no artificial cause.

Note: `show` does not test `null` because this demo only catches `IllegalArgumentException`, whereas `parseQuantity(null)` uses `Objects.requireNonNull` and throws `NullPointerException`. If an API wants to translate all invalid inputs into a unified error response, build an explicit mapping layer rather than assuming `IllegalArgumentException` always covers NPE.

## 16. How to write tests for a public API contract

A unit test can use a testing library to verify that a public method consistently throws a specified exception type when called with invalid data. That is different from placing `assert` in the implementation. In plain Java without a framework, you can write a simple helper to prove the contract.

### Example 10: verifying exceptions in both `-da` and `-ea`

Save as `GuardContractTestDemo.java`:

~~~java
public class GuardContractTestDemo {
    static int requirePositive(int value) {
        if (value <= 0) {
            throw new IllegalArgumentException("value not positive");
        }
        return value;
    }

    static boolean rejects(int value) {
        try {
            requirePositive(value);
            return false;
        } catch (IllegalArgumentException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        System.out.println("positive=" + requirePositive(5));
        System.out.println("rejectZero=" + rejects(0));
        System.out.println("rejectNegative=" + rejects(-1));

        if (!rejects(0) || !rejects(-1)) {
            throw new AssertionError("broken public contract");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 GuardContractTestDemo.java
java -da GuardContractTestDemo
java -ea GuardContractTestDemo
~~~

Identical output:

~~~text
positive=5
rejectZero=true
rejectNegative=true
~~~

**In tests**, `throw new AssertionError(...)` is written explicitly using normal execution flow, unlike the `assert` keyword which can be skipped. Many unit-testing frameworks also use `AssertionError` to report test failures; that is the role of **testing**, not a reason to use `assert` for public preconditions in application code.

When using JUnit, you can apply `assertThrows(IllegalArgumentException.class, ...)` to specify the expected exception type. Do not rely solely on `assert condition;` in tests and forget to enable `-ea` if the test itself depends on the Java `assert` keyword; framework assertion methods are APIs distinct from the language's `assert` keyword.

## 17. `Objects.requireNonNull`, `checkIndex`, and custom helpers: choosing properly

Helpers in `java.util.Objects` are often convenient for public parameters:

~~~java
String validName =
        java.util.Objects.requireNonNull(name, "name");
int validIndex =
        java.util.Objects.checkIndex(index, count);
~~~

This is an illustrative snippet inside a method where `name`, `index`, and `count` are already defined. Both operations always run, even if assertions are disabled.

Distinctions:

- `requireNonNull` only checks for null; it **does not automatically check** for empty strings, whitespace, patterns, or business rules.
- `checkIndex` checks the index domain [0, length), not replacing access-permission checks or element semantics.
- Custom helpers such as `requirePositive` should throw a meaningful exception and keep validation **impossible to disable**.
- For user-supplied values, a system might want to return a **ValidationResult** instead of throwing an exception because invalid input is a frequent case; that is an API design choice, but never use `assert` as a substitute.

Example of a reusable helper:

~~~java
static int requirePositive(int value, String parameter) {
    if (value <= 0) {
        throw new IllegalArgumentException(
                parameter + " must be positive");
    }
    return value;
}
~~~

This is a valid method when placed in a class. It can be used in constructors or methods to reduce code duplication. Avoid putting sensitive data into exception messages; the parameter name and rule are usually sufficient.

## 18. Cases where you should not rely on `assert` alone

| Context | Why assert is unsuitable | Alternative |
| --- | --- | --- |
| Public method receiving a negative quantity | With `-da`, invalid data is accepted | `if` + IllegalArgumentException |
| Constructor receiving null | An invalid object can be created | Objects.requireNonNull |
| Record with invalid component values | Immutability is left unchecked | Compact constructor validation |
| REST API receiving a malformed date | User input can routinely be invalid | Parse + map validation error |
| CSV file containing a malformed row | Expected input error | Return per-row error, appropriate exception/result |
| Collection index access | Invalid index violates the contract | Objects.checkIndex or checked API |
| Transaction with out-of-bounds input | State must not change on invalid input | Validate before side effects |
| Closed object state | Operation is disallowed by the API | IllegalStateException |
| Access-control rules | Protection must be mandatory in all modes | Non-disableable authorization check |
| Null check to avoid deep dereference | With assert disabled, delayed NPE occurs | Objects.requireNonNull |
| Assert calling a state-mutating function | Enabling/disabling changes program behavior | Extract the call into a normal statement |
| Expected error-recovery flow | AssertionError is an Error, not a normal contract | Exception/domain error or result type |

**Distinguishing the degree of "do not":** The JLS does not forbid the syntax `assert x > 0` at the top of a public method, but doing so **does not enforce the contract** if assertions are disabled. Therefore, it is a **design anti-pattern**, not a Java syntax error.

## 19. When should `assert` still be used in production code?

Assertions can appear in production code to aid diagnostics of an internal invariant when intentionally enabled. For example, inside an algorithm whose inputs have already been validated by the public API and all control paths guarantee a property:

~~~java
int result = carefullyComputedValue();
assert result >= 0 : "internal algorithm invariant";
return result;
~~~

This is an illustrative snippet assuming `carefullyComputedValue()` exists and the program logic already guarantees a non-negative result. When assertions are disabled, the algorithm must still remain valid and uphold its critical contracts.

Areas requiring careful consideration:

- **Security checks:** never replace with assert, as enabling/disabling alters the level of protection.
- **Input validation:** do not use assert because callers are allowed to pass invalid data and need consistent feedback.
- **Resource management:** do not place close/commit/rollback inside an assert expression.
- **Concurrency:** assert provides no locking, visibility, atomicity, or synchronization.
- **Debug-only invariants:** assert can be used to detect violations of assumptions that the implementation is supposed to guarantee.
- **Expensive invariant checks:** assert can be used if the condition has no side effects, the extra execution is solely for debugging, and disabling it has no mandatory consequences.

An invariant violation surfaced by `AssertionError` usually requires investigating and fixing the logic, not returning an "invalid parameter" message to end users.

## 20. Common misconceptions about enabling/disabling assertions

**Misconception 1 — "Java automatically enables assert when debugging in an IDE."**  
There is no such guarantee. An IDE or test runner may or may not add `-ea`. Always check the actual JVM configuration. A program compiled with `javac` does not enable assertions on its own.

**Misconception 2 — "Running `java MyProgram -ea` enables assert."**  
No. JVM options go before the main class name: use `java -ea MyProgram`.

**Misconception 3 — "Disabling assert only disables the `throw`, while the condition still runs."**  
False. When assertions are disabled, expressions inside `assert` **are not evaluated**.

**Misconception 4 — "Running `-ea` in dev means production is protected too."**  
False. Another environment can disable assertions, especially when launcher or configuration settings change.

**Misconception 5 — "A `catch(Exception)` handles AssertionError."**  
False. AssertionError extends `Error`, which is not in the Exception hierarchy.

**Misconception 6 — "Everything `assert` checks is public data."**  
No. Assert is best suited for checking an invariant **controlled by the implementation**, meaning a deviation indicates a bug rather than bad user input.

**Misconception 7 — "Objects.requireNonNull checks all kinds of invalid Strings."**  
No. The string `""` is still non-null; you must additionally check `isBlank`, format, and domain rules.

**Misconception 8 — "JUnit assertEquals is the same as the Java keyword assert."**  
No. Framework assertions are library methods and are not skipped by the JVM via `-da` like the language's `assert` statement.

**Misconception 9 — "Putting `assert balance >= 0` after subtraction is enough."**  
No. When assertions are disabled, the condition is not checked. Normal logic must prevent overdrawing the balance before updating it.

**Misconception 10 — "Assert always throws AssertionError when an expression fails."**  
Not necessarily. If the condition or detail expression itself throws an exception/error during evaluation, the statement can terminate with that throwable; the JLS describes this behavior explicitly.

## 21. Review checklist for a public method or constructor

Review in order:

1. **Where does the input come from?** An external module caller, HTTP, file, CLI, configuration, or an already-validated internal step?
2. **Which parameters are required?** Are null, blank, range, index, format, enum, and capacity constraints clearly defined?
3. **Is `assert` used as the sole barrier?** If so, replace it with `if`, `Objects` helpers, or a validation result.
4. **Does the code have side effects before checking?** Validate before writing to a DB, sending messages, mutating state, or allocating expensive resources.
5. **Is the exception type semantically right?** NullPointerException, IllegalArgumentException, IndexOutOfBoundsException, IllegalStateException, or a custom domain failure?
6. **Is the message safe?** Does it avoid leaking tokens, passwords, sensitive data, or entire large inputs?
7. **Can the constructor create an invalid object?** Validate before storing components/fields.
8. **Where is the invariant guaranteed?** Validation and algorithms must guarantee it; assert only supplements diagnostics.
9. **Are there side-effecting expressions in assert?** If so, extract them out of assert into statements that always run.
10. **Tested in both modes?** Run with both `java -da` and `java -ea` to ensure the public contract does not change.
11. **Tested failure paths?** Verify the exact exception type, message or error code, and state after rejection.
12. **API documentation:** document parameter domains and error types instead of expecting callers to read assert code.

This checklist is especially useful when promoting code from a script or debug utility into a public library: assumptions that only held for test data must be converted into contract checks before facing real-world inputs.

## 22. Self-check questions

**Question 1.** Why shouldn't `assert amount > 0` be used as the sole check in a public method?  
Because assertions can be disabled, in which case `amount > 0` is not evaluated and invalid input can pass through.

**Question 2.** How does running `java -ea Program` differ from `java -da Program`?  
The first flag enables assertions in the applicable scope, while the second disables them; validations written with `if`/`Objects` execute identically in both.

**Question 3.** When `assert false : "bad";` is enabled, what error is normally thrown?  
**AssertionError**, which belongs to the Error branch.

**Question 4.** Does `catch(Exception ex)` catch AssertionError?  
**No**, because AssertionError does not extend Exception.

**Question 5.** If `assert checkAndModify();` has a side effect, does the side effect happen under `-da`?  
**No**, the condition expression is not invoked.

**Question 6.** How should a constructor handle receiving `null` for a required parameter?  
It can use **Objects.requireNonNull**, throwing NullPointerException per a clear contract.

**Question 7.** Is a negative quantity passed by a caller a broken internal invariant?  
Usually **no**; it is an argument violating the public contract and should be rejected via validation.

**Question 8.** When an object is closed and a caller invokes a mutating method, what exception type is typically appropriate?  
**IllegalStateException** by standard API design convention.

**Question 9.** Should you use `assert index >= 0` to ensure valid list access?  
**No**. You must also check the upper bound with mandatory code, such as Objects.checkIndex.

**Question 10.** Can `assert` be used to check an internal invariant after thorough validation?  
**Yes**, provided the application still upholds its contract when assertions are disabled and the condition has no side effects.

**Question 11.** Does a record's compact constructor automatically reject a quantity of 0?  
**Not automatically**. You must check it with `if` if that is a precondition.

**Question 12.** Why should tests be run with both `-ea` and `-da`?  
To detect faulty code that depends on assertions being enabled; a public API must maintain consistent validation behavior.

**Question 13.** Does `assert condition : detailExpression` always evaluate `detailExpression`?  
**No**. It is only evaluated when assertions are enabled and the condition is false (unless the condition itself completes abruptly).

**Question 14.** Are the `assert` keyword and the `assertThrows` method in a testing framework the same thing?  
**No**. `assertThrows` is a testing method; the `assert` keyword can be disabled by the JVM.

## Authoritative references

- [JLS Java SE 21 — §14.10: The assert Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.10) — enable/disable rules, expression evaluation, AssertionError, and the recommendation against using assertions for public argument checking.
- [Oracle — Programming With Assertions](https://docs.oracle.com/javase/8/docs/technotes/guides/language/assert.html) — appropriate/inappropriate uses of assert and side effects.
- [Java SE 21 — java.lang.AssertionError](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/AssertionError.html).
- [Java SE 21 — java.util.Objects: requireNonNull, checkIndex](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html).
- [Java SE 21 — IllegalArgumentException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IllegalArgumentException.html).
- [Java SE 21 — IllegalStateException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IllegalStateException.html).
- [Java SE 21 — IndexOutOfBoundsException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/IndexOutOfBoundsException.html).
- [Java launcher — enableassertions / disableassertions](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).

**Key takeaway:** `assert` is for internal assumptions that the program **already guarantees to be true**, helping detect bugs when diagnostics are enabled. **Public methods, constructors, records, APIs receiving external data, and operations with side effects must validate preconditions using code that always runs**, regardless of `-ea`/`-da`. Choose meaningful contract exceptions, preserve causes when translating errors, write tests for invalid data, and never let correctness or security depend on assertion status.
