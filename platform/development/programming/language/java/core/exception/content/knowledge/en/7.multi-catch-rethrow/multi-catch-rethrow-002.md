# When Can Multiple Exception Types Share a Single Handler in Java?

In Java, not every exception type needs its own separate `catch` block. If multiple error types lead to the **same handling decision**, Java allows grouping them in a *multi-catch* branch: `catch (IOException | SQLException ex)`. However, being able to combine them **syntactically** does not mean shared handling is always **business-wise** correct.

For example, an application reads data from a file or a database. If both errors allow using a safe cached copy of the data, a shared handling branch can make sense. Conversely, if an I/O error requires a retry, an SQL error requires rolling back a transaction, or `InterruptedException` must preserve the cancellation signal, merging them into a single branch can hide critical decisions.

This lesson focuses on the criteria for deciding **when to share a handling strategy**, how to write `multi-catch`, interactions with inheritance, `rethrow`, exception handling across multiple layers, and how not to lose the root cause.

## 1. What Problem Does Multi-Catch Solve?

Before Java 7, when two exceptions required the same action, code often had to duplicate the handling logic:

```java
try {
    loadData();
} catch (IOException ex) {
    reportFailure(ex);
} catch (SQLException ex) {
    reportFailure(ex);
}
```

This is an illustrative snippet inside a method, assuming `loadData()` can throw `IOException` or `SQLException`, and `reportFailure(Exception)` is already defined. The two branches differ in **exception type** but call the same function with the same policy.

It can be written more clearly using multi-catch:

```java
try {
    loadData();
} catch (IOException | SQLException ex) {
    reportFailure(ex);
}
```

Both types are listed with the `|` operator in **one** parameter of **one** `catch` branch. If `try` throws one of the two compatible types, the shared block runs exactly once. The code is still subject to the usual checked exception rules and `catch` reachability rules.

The main goal is to **eliminate duplication of the same decision**, rather than merely grouping exceptions with similar names or origins.

## 2. Key Criterion: Can the Errors Truly Share the Same Policy?

Answer all five questions before merging:

1. **Is the desired outcome the same?** For example, both errors lead to "unable to load data, use verified cache", or "abort the operation and throw a business exception with a cause".
2. **Do they have the same impact level and recoverability?** Continuing with a fallback result must be safe for both cases; do not share a fallback for an error that could leave data inconsistent.
3. **Are specialized actions needed?** For example, a DB error might require a rollback or marking a connection as unusable; a network error might require a retry; an interrupt signal requires a cancellation policy. If the actions differ, split the branches.
4. **Do different results need to be provided to the caller?** If one error maps to "data not found" while the other maps to "system temporarily unavailable", merging loses a useful distinction.
5. **Is enough information preserved for investigation?** A shared branch still needs to retain the actual error type, `message`, `cause`, and `suppressed` exceptions when needed, rather than turning everything into an anonymous string.

**Only merge when the same handling policy is right for every error type in the branch.** When exception types have different strategies, two separate `catch` blocks are usually clearer and more accurate.

| Scenario | Should they share a `catch`? | Reason |
| --- | --- | --- |
| File read error and data query error; both have a valid cache allowed for use | Possibly | Same fallback decision, but ensure the cache meets data requirements |
| File read error and DB error are both translated into `DataLoadException` with cause | Possibly | Same service-layer error contract while preserving the cause |
| `FileNotFoundException` needs to show a "missing configuration" message, `AccessDeniedException` needs a permission error | Should split | Different meaning, remediation, and message |
| `SocketTimeoutException` can be retried, `SQLException` may need rollback/marking the transaction failed | Usually split | Handling action depends on error source and system state |
| `InterruptedException` and `IOException` | Usually split | InterruptedException means cancellation/propagating interrupt state, not simply an I/O error |
| `IOException` and `OutOfMemoryError` | Should not group to "handle all errors" | Serious JVM errors do not guarantee recoverability like normal I/O |

The suggestions in the table depend on context. There is no rule that an SQL error must always be rolled back manually or a timeout error can always be retried: the decision depends on transactions, idempotency, and the actual API contract.

## 3. Syntax and Type Constraints of Multi-Catch

Multi-catch uses `|` to list the **selected exception types** and a shared handler body:

```java
try {
    loadData();
} catch (IOException | SQLException ex) {
    reportFailure(ex);
}
```

This illustrative snippet requires `loadData()` and `reportFailure(...)` to be defined. `IOException` and `SQLException` have no parent–child relationship, so they can appear together when the `try` block can actually throw both checked exceptions.

Key constraints: do not combine a class with its own subtype (such as `IOException | FileNotFoundException`); `ex` is implicitly `final`; the compiler only allows calling members present on the **common static type** of the alternatives; and checked exceptions must match what can be thrown from `try`. These constraints determine **valid syntax**, while the main question of this lesson is whether both errors share the **same business policy**.

## 4. Java 17+ Program: Sharing a Fallback When Both Errors Have the Same Consequence

Suppose both the file source and DB are only supplemental sources; the service is **allowed** to return verified cached data when fresh data cannot be loaded. This is the business policy for the example, not advice to use a cache regardless of how critical the data is.

Save as `SharedFallbackDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class SharedFallbackDemo {
    static String loadFresh(int mode) throws IOException, SQLException {
        if (mode == 1) {
            throw new IOException("file unavailable");
        }
        if (mode == 2) {
            throw new SQLException("database unavailable");
        }
        return "fresh-data";
    }

    static String loadWithFallback(int mode) {
        try {
            return loadFresh(mode);
        } catch (IOException | SQLException ex) {
            System.out.println("fallback after "
                    + ex.getClass().getSimpleName());
            return "verified-cache";
        }
    }

    public static void main(String[] args) {
        System.out.println("result=" + loadWithFallback(0));
        System.out.println("result=" + loadWithFallback(1));
        System.out.println("result=" + loadWithFallback(2));
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 SharedFallbackDemo.java
java SharedFallbackDemo
```

Output:

```text
result=fresh-data
fallback after IOException
result=verified-cache
fallback after SQLException
result=verified-cache
```

Main execution paths:

1. `mode = 0`: `loadFresh` completes normally, `catch` does not run, returns `fresh-data`.
2. `mode = 1`: throws `IOException`, enters the **same multi-catch branch**, prints the error type, and returns the cache.
3. `mode = 2`: throws `SQLException`, still enters the shared branch and returns the same fallback.
4. The `loadWithFallback` method does not need `throws IOException, SQLException`, because both checked exceptions are handled and do not escape the method.

The benefit lies in having **the fallback decision be a unified rule**. If in real business logic an SQL error could indicate that data was partially written and the cache is no longer trustworthy, this policy is no longer valid: the handling flow must be split or the operation contract fixed.

## 5. When the Shared Handling Is Translating into a Business Exception

A storage layer may throw multiple infrastructure checked exception types, while the service layer wants to provide a single "unable to load information" contract. If both errors have the same meaning at that boundary, they can be **wrapped together**, preserving the actual cause:

```java
catch (IOException | SQLException ex) {
    throw new DataLoadException("Cannot load data", ex);
}
```

This snippet is inside a method appropriately declared with `throws DataLoadException`; `DataLoadException` must be an exception class with a constructor accepting `cause`. Wrapping creates a **new exception object**, unlike rethrowing the same object.

Save as `SharedTranslationDemo.java`:

```java
import java.io.IOException;
import java.sql.SQLException;

public class SharedTranslationDemo {
    static class DataLoadException extends Exception {
        DataLoadException(String message, Throwable cause) {
            super(message, cause);
        }
    }

    static String repository(int source) throws IOException, SQLException {
        if (source == 1) {
            throw new IOException("disk read failed");
        }
        if (source == 2) {
            throw new SQLException("query failed");
        }
        return "OK";
    }

    static String service(int source) throws DataLoadException {
        try {
            return repository(source);
        } catch (IOException | SQLException ex) {
            throw new DataLoadException("Cannot load data", ex);
        }
    }

    public static void main(String[] args) {
        for (int source = 0; source < 3; source++) {
            try {
                System.out.println("value=" + service(source));
            } catch (DataLoadException ex) {
                Throwable cause = ex.getCause();
                System.out.println("service=" + ex.getMessage());
                System.out.println("cause="
                        + cause.getClass().getSimpleName()
                        + ":" + cause.getMessage());
            }
        }
    }
}
```

```bash
javac -encoding UTF-8 SharedTranslationDemo.java
java SharedTranslationDemo
```

Output:

```text
value=OK
service=Cannot load data
cause=IOException:disk read failed
service=Cannot load data
cause=SQLException:query failed
```

Both underlying error types are **translated into a single service-layer checked exception**. `service()` declares `throws DataLoadException`, and `main()` catches that exact contract. Because `DataLoadException` receives `ex` as its cause, investigators can still distinguish `IOException` from `SQLException` and inspect the original stack trace.

Do not replace this with `throw new DataLoadException(ex.getMessage(), null)` or create a new exception with only a message: doing so can lose the cause link. When logging, pass the entire throwable object to the logging API rather than printing only the text message.

## 6. When Should `catch` Branches Be Split?

Multi-catch is a good choice when the action is the same. When there are **different rules**, two independent branches directly reflect the design:

```java
try {
    processRequest();
} catch (java.net.SocketTimeoutException ex) {
    scheduleBoundedRetry(ex);
} catch (java.sql.SQLException ex) {
    markOperationFailed(ex);
    throw ex;
}
```

This is an **illustrative snippet inside a method**, assuming `processRequest()` declares the relevant checked exceptions, the two helper methods are defined, and the enclosing method declares `throws SQLException`. It cannot be treated as a standalone program.

The timeout branch chooses a bounded retry; the SQL branch marks the operation as failed and lets the exception continue propagating upward. Because the policies differ, it is not worth merging them just to reduce line count.

Signs that branches should be split:

- **Different urgency levels:** a missing input parameter error can respond immediately, while an infrastructure error needs to mark a system failure.
- **Different retryability:** retrying only makes sense if the operation is idempotent or has safeguards against repeated side effects.
- **Different resources and transactions:** one error needs to close a connection, while another needs a rollback or must not be allowed to continue.
- **Thread state preservation requirements:** `InterruptedException` is a cooperative cancellation signal; it should usually be propagated or have the interrupt flag restored and the operation terminated, rather than being grouped with a regular infrastructure error.
- **Different user-facing responses:** permission errors and temporary unavailability errors should not automatically receive the same message.
- **Different monitoring needs:** even if both ultimately fail, alert/metric classification needs may require keeping explicit types at the recording boundary.

**Do not merge branches and then write a big `if (ex instanceof A) ... else ...` chain just to reconstruct the merged branches.** If policies genuinely differ, separate `catch` blocks are usually more readable and less error-prone. Using `instanceof` can still make sense if a small step needs extra classification inside a shared policy, though you should question why merging was needed.

## 7. Distinguishing "Shared Action" from "Shared Information"

Merely calling `logger.error("failed", ex)` is not enough to conclude that two exceptions should be handled together. Logging is only **a side effect**; what matters is the **consequence for the system and the upper layer's contract**.

Suppose both errors are logged:

```java
catch (IOException ex) {
    recordFailure(ex);
    return cachedValue();
} catch (SQLException ex) {
    recordFailure(ex);
    throw ex;
}
```

Both branches share `recordFailure(ex)`, but one recovers while the other propagates the error. This is **not the same overall handling**; do not merge them into one `catch` and arbitrarily return the cache in all cases.

If you want to reduce duplicate code, extract the recording logic into a shared helper method as shown. Keep different decisions in their appropriate branches.

Another case: when a boundary layer always maps multiple exceptions to the same failure result code and the same termination policy, multi-catch can be appropriate even if the causes differ, **as long as the cause is still preserved** for analysis. Returning the same user-facing message does not necessarily mean losing the distinction in logs and metrics.

## 8. Multi-Catch and Rethrow: Propagating the Exact Object Upward

When the current layer cannot recover yet, a shared handler can still record context and then **rethrow the exact error object**:

```java
static void forward() throws IOException, SQLException {
    try {
        loadData();
    } catch (IOException | SQLException ex) {
        System.out.println("forward=" + ex.getClass().getSimpleName());
        throw ex;
    }
}
```

This is an illustrative method; `loadData()` must have the contract `throws IOException, SQLException`. `throw ex;` **does not** turn a failure into a success and does not create a new wrapper; the caller remains responsible for handling it. `IOException` and `SQLException` remain the two checked exceptions in the signature.

If the current layer wants to express a general business error, instead of rethrowing it can wrap with a new exception **keeping `ex` as `cause`**. Deciding whether to translate or rethrow is a decision about layer responsibility, not a reason to automatically group error types with different policies. The rule that infers narrower checked exceptions when rethrowing is called *precise rethrow* and has specific conditions in the JLS.

## 9. Multi-Catch Does Not Allow Reassigning the Parameter Variable

In `catch (IOException | SQLException ex)`, the variable `ex` is **implicitly `final`**: assigning `ex = new IOException("other")` is a compile-time error. This does not forbid **rethrowing** `throw ex;`, reading the stack/cause, or creating a new wrapper whose `cause` is `ex`. Do not confuse the parameter being non-reassignable with the `Throwable` object being immutable; suppressed exceptions or stack traces can have their own state. When you want to add context, create a new exception with a cause rather than trying to mutate the handler's reference.

## 10. Validity of `catch` with Checked Exceptions

The Java compiler checks whether the `try` block **can** throw the checked exception type caught by a `catch` branch. Arbitrarily listing multiple checked types without a corresponding exception source can cause a compile-time error.

**Intentionally invalid:**

```java
import java.io.IOException;
import java.sql.SQLException;

class InvalidUnusedAlternative {
    static void run() {
        try {
            throw new IOException("disk");
        } catch (IOException | SQLException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

In this `try`, there is no path that throws the checked `SQLException`; `javac` may report `exception SQLException is never thrown in body of corresponding try statement`. To make it valid, catch only `IOException`, or ensure the operations in `try` actually have a contract that can throw `SQLException`.

**Do not put `throws SQLException` on the enclosing method to legitimize a `catch (SQLException)` branch that `try` itself cannot throw.** Catchability of a checked exception is determined by the contents/operations of `try`, not by arbitrarily declaring that error type on the enclosing method's signature.

For unchecked `RuntimeException`, Java allows broader catching even if there is no explicit throw statement inside `try`. The checked exception rule is part of static checking and must be considered separately from runtime `catch` branch selection.

## 11. Do Not Use Multi-Catch to Hide Interrupt Semantics

A common mistake is treating `InterruptedException` like a transient error that can be logged and ignored to continue:

```java
try {
    Thread.sleep(100);
    readData();
} catch (InterruptedException | IOException ex) {
    System.out.println("failed: " + ex.getMessage());
    // Continue work immediately: may lose the cancellation request.
}
```

This is an illustrative snippet inside a method, assuming `readData() throws IOException`. The multi-catch syntax is valid, but the **handling policy is problematic**: when `Thread.sleep` throws `InterruptedException`, the interrupt status is typically cleared according to that method's contract. If you only log and continue, the program can inadvertently ignore a stop request.

If the current layer needs separate handling, split explicitly:

```java
try {
    Thread.sleep(100);
    readData();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (IOException ex) {
    handleIoFailure(ex);
}
```

This snippet assumes it is inside a `void` method with `readData() throws IOException`, `handleIoFailure(IOException)` exists, and it is not a standalone program. The interrupt branch preserves the cancellation signal, while the I/O branch handles its error according to its own policy. If a method can declare `throws InterruptedException`, letting it propagate is also a reasonable option depending on the contract.

The key takeaway is that **two errors being able to occur in the same `try` is not enough to merge them**. They must share the same final decision when either occurs.

## 12. Parent/Child Relationships Affect How Exceptions Are Grouped

If errors have an inheritance relationship, you **cannot** write a union like `catch (FileNotFoundException | IOException ex)` because `FileNotFoundException extends IOException`. There are two options depending on policy:

```java
catch (IOException ex) {
    handleAllIoFailures(ex); // Only when all I/O errors need the same policy.
}
```

or two separate handlers, **subclass before superclass**:

```java
catch (FileNotFoundException ex) {
    reportMissingFile(ex);
} catch (IOException ex) {
    reportOtherIoFailure(ex);
}
```

These are illustrative branches inside an appropriate `try`, requiring the application's imports and handler functions. Catching `IOException` covers its subclasses, but that **does not mean** every I/O error should be retried or use a fallback. Type coverage and policy suitability are two different questions.

## 13. Difference Between Separate `catch` Blocks with Duplicate Logic and Multi-Catch

If the handling code is duplicated but may need to evolve separately later, two approaches are commonly valid:

**Approach A — one shared branch:**

```java
catch (IOException | SQLException ex) {
    throw new DataLoadException("Data loading failed", ex);
}
```

**Approach B — two separate branches calling one function:**

```java
catch (IOException ex) {
    throw translate(ex);
} catch (SQLException ex) {
    throw translate(ex);
}
```

Both snippets **illustrate the `catch` part of a `try`**, assuming `DataLoadException` and `translate(Exception)` are defined with suitable signatures. Both approaches can have equivalent effects when the policy is truly identical.

Multi-catch makes sense when **both the decision and the effect** are the same and likely to remain stable. Two separate `catch` blocks are useful if you want to report different metrics, attach specific contextual data, or might need different handling policies. There is no need to force a single syntax for every situation.

A practical rule of thumb: if a multi-catch body consists mainly of `instanceof` branches distinguishing types, that is a sign to consider splitting into corresponding `catch` blocks, unless the shared part is still the primary handling logic.

## 14. Grouping at a Centralized Handling Layer Still Requires Preserving Error Meaning

Some applications have a common handling boundary such as a command-line entry point, worker task boundary, or global API error handler. There, many errors can lead to a common action: marking the request failed, returning a consistent response, ending the work, and recording status.

Even so, distinguish between:

- **Grouping how errors are output:** the same response format, the same logging style, the same control over leaking information to users.
- **Grouping error meaning:** treating two errors as identical regarding retryability, data loss, integrity, and recovery strategy.

You can group how errors are output while still preserving the error type information in internal data. If one error should prompt the user to re-enter parameters while the other is a system outage, returning the same error code or remediation guidance can be misleading.

When a boundary uses a broad `catch (Exception ex)`, it can also catch many unchecked exceptions such as `NullPointerException` or `IllegalStateException`. Therefore, `catch (Exception)` has a significantly broader intent than `catch (IOException | SQLException)`. It also **does not catch `Error` branches**. Broad catching should only be used where a clear centralized error policy exists, not as a way to hide all errors and continue as if things succeeded.

## 15. `finally`, Resources, and Multi-Catch

If an error is thrown inside `try` and selects a multi-catch branch, the associated `finally` still runs according to Java rules before the construct finishes transferring control. `finally` does not turn multiple `catch` branches into multiple handler executions.

With `try-with-resources`, automatic resource closing happens before reaching the `catch` of that construct. If the `try` body throws an error and `close()` also throws an error, the close error is typically stored in `getSuppressed()` of the primary exception. **`catch` selection is based on the primary exception thrown**, not by running branches sequentially for each suppressed exception.

Therefore, a multi-catch used for wrapping errors should keep the original `ex` object as the cause. The `suppressed` list attached to the cause object will remain traceable. Copying only the message discards a lot of useful information during incident analysis.

If the `catch` or `finally` block itself throws a new error, distinguish between the error **initially selected to be caught** and the error **escaping outward**. Adjacent `catch` branches do not catch a new exception thrown inside a `catch` branch itself.

## 16. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Grouping all errors because "they all log". | Different recovery policies get mixed together. | Compare final outcome, retry, rollback, fallback, and cancellation before merging. |
| Writing `catch (Exception ex)` instead of the specific types to handle. | May accidentally swallow unrelated `RuntimeException`s. | Use multi-catch listing the exact types if they share a policy. |
| Listing both a superclass and a subclass in multi-catch. | Compile-time error. | Catch the superclass if handling is truly shared; or split subclass before superclass. |
| Reassigning the multi-catch parameter. | Compile-time error because the parameter is implicitly final. | Keep `ex` intact; create another variable if needed. |
| Wrapping an error using only `ex.getMessage()`. | Loses `cause`, making stack and suppressed exceptions hard to trace. | Pass `ex` into a constructor accepting `Throwable cause`. |
| Rethrowing `ex` while assuming the current layer has finished handling it. | The error continues propagating; upper layers remain responsible. | Declare `throws` appropriately or catch at a boundary layer. |
| Merging `InterruptedException` with I/O errors and continuing. | May lose the thread cancellation signal. | Split and propagate interrupt or restore flag and terminate the task. |
| Trying to catch a checked exception that cannot be thrown from `try`. | Compiler may report "never thrown". | Base it on the actual signatures and exception sources inside `try`. |
| Grouping `Throwable` or `Error` into a normal business handling branch. | May mask critical failures and make wrong recovery assumptions. | Restrict caught types to exceptions with a clear strategy. |
| Using a fallback regardless of whether data is safe. | System may return wrong or inconsistent results. | Only use a fallback when there is a valid contract and verification conditions. |

## 17. Decision Checklist Before Writing Multi-Catch

When considering `catch (A | B ex)`, check in order:

1. **Are A and B type-independent?** If one type inherits from the other, multi-catch syntax is invalid.
2. **Can the `try` block throw both A and B under compile-time rules?** Especially important for checked exceptions.
3. **Do both share the same handling from start to finish?** Check fallback, retry, rollback, messaging, and final state.
4. **Is the shared handling decision truly safe?** Do not apply a "looks reasonable" policy to an error that could violate invariants.
5. **Is the original error preserved?** When rethrowing, use `throw ex;`; when translating, use a constructor accepting `cause`.
6. **What does the caller know?** If recovered, return a valid result; if not, declare any checked exceptions that can still escape.
7. **Are there special interrupt or cleanup requirements?** If so, consider a separate branch or explicit resource management logic.

If all answers support the same action, multi-catch keeps code shorter and the policy consistent. If there are important differences, separate `catch` blocks accurately express how the system should react.

## 18. Self-Check

**Question 1.** Both `IOException` and `SQLException` must be translated into `DataLoadException` with the same message and preserving the cause. Does a shared multi-catch make sense?  
**It can make sense.** The two classes have no parent/child relationship and share the same translation policy at the layer boundary. Verify that `try` can throw both checked types.

**Question 2.** Both `FileNotFoundException` and `IOException` use the same action. Can you write `catch (FileNotFoundException | IOException ex)`?  
**No.** Multi-catch forbids an alternative type from being a subclass of another alternative type. You can use `catch (IOException ex)` if all `IOException`s fall under the shared handling scope, or use separate branches.

**Question 3.** Two `catch` blocks both call a logging function, but one returns a fallback while the other rethrows. Should they be merged?  
**Usually no.** Their final policies differ; extracting a shared logging function while keeping two handling branches is clearer.

**Question 4.** Does a multi-catch run twice when both types are declared?  
**No.** One primary exception is selected and handled in a single branch at that time.

**Question 5.** Can you write `ex = replacement;` inside `catch (IOException | SQLException ex)`?  
**No.** The multi-catch parameter is implicitly final.

**Question 6.** Are `throw ex;` and `throw new DataLoadException("failed", ex);` the same?  
**No.** The first rethrows the same object; the second creates a new exception belonging to a different contract and links the cause via `cause`.

**Question 7.** Should you group `InterruptedException` with `IOException`, print the message, and let the worker continue?  
**No**, because the waiting operation may have cleared the interrupt flag, causing the cancellation request to be ignored. A proper interrupt policy is required.

**Question 8.** If `try` can only throw checked `IOException`, is it always allowed to add `SQLException` to multi-catch?  
**No.** Java checks which checked exceptions can be thrown from `try`; a type that cannot be thrown may be rejected.

## References

- [Java Language Specification, Java SE 17 — §14.20 The `try` Statement, multi-catch](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20).
- [JLS 17 — §14.20.1 Execution of `try-catch`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.20.1).
- [JLS 17 — §11.2.2 Exception Analysis of Statements (precise rethrow)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.2).
- [JLS 17 — §11.2.3 Exception Checking](https://docs.oracle.com/javase/specs/jls/se17/html/jls-11.html#jls-11.2.3).
- [JLS 17 — §4.10.4 Least Upper Bound (common type of multi-catch)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.4).

**Remember:** Multiple exceptions can share a single handler when **they all lead to the same correct and safe decision**. Use multi-catch for a shared policy, split branches when the meaning or recovery differs, and always preserve cause information when translating or rethrowing errors.
