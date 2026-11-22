# Usage Contracts and Implementation Details in Java OOP

An object may change its algorithm, data storage, or external provider without requiring consumers to **change how they call it**. This is safe only when we clearly distinguish two things:

- **Usage contract (*contract*):** which behavior callers may request, which inputs are valid, which types of results they receive, and which errors or side effects can occur.
- **Implementation details (*implementation*):** the algorithms, data structures, libraries, or external connections the object uses to fulfill those promises.

In Java, `interface`, `abstract class`, and public APIs can all express parts of a contract. But **a method signature is not the entire behavioral contract**. An implementation can compile successfully yet return results with the wrong meaning.

This lesson uses a **leave-request evaluation policy** to examine contract definition, two different rule implementations, provider substitution, testing, and change management. It is a standalone example that does not require Spring Boot.

## 1. The Caller's Perspective: What Do They Actually Need to Know?

An HR service needs to perform an initial evaluation of a leave request. The illustrative policy needs an employee ID, the number of leave days requested, and the remaining leave balance at the time of evaluation. There are two policies:

- **Standard policy:** returns an eligible decision if the requested days do not exceed the remaining leave balance.
- **Probationary policy:** in addition to the balance requirement, each request can cover at most two days.

These implementations can return **different results for the same input** while honoring the same contract. Callers need only invoke `evaluate(request)` and receive a reasoned decision; they need not know whether the probation rule is implemented with an `if`, a rule table, or an HR system.

| What the contract must expose | Example |
| --- | --- |
| Capability | Evaluate whether a leave request can be accepted |
| Input data | `LeaveRequest` with an employee ID, `requestedDays`, and `remainingDays` |
| Value domain | Nonblank ID, requested days > 0, remaining days >= 0 |
| Result | `LeaveDecision` with a decision code and explanation |
| Shared rule | Do not approve when requested days exceed the remaining balance |
| Errors | `null` is rejected; invalid data is rejected when creating the request |
| Side effects | **Evaluation only**; do not deduct leave days or write to the database |
| Limitation | Decision uses a snapshot; it does not mean the request has been approved or persisted |

**The clearer the contract, the less room each implementation has to interpret it differently.** For example, if one class returns `null` for a rejected request while another returns an object with a rejection code, callers must branch by provider.

## 2. Standalone Java Example: Two Implementations, One Contract

Save as `LeaveContractDemo.java` and compile with **JDK 17 or later**. `record` types are compact value types with constructors that validate data. Here, records contain only `String`, integers, and enums, so they do not expose mutable references.

~~~java
import java.util.Objects;

public class LeaveContractDemo {

    record LeaveRequest(
            String employeeId, int requestedDays, int remainingDays) {
        LeaveRequest {
            if (employeeId == null || employeeId.isBlank()) {
                throw new IllegalArgumentException("Employee ID is required");
            }
            if (requestedDays <= 0 || remainingDays < 0) {
                throw new IllegalArgumentException("Invalid day count");
            }
        }
    }

    enum DecisionCode {
        APPROVED, INSUFFICIENT_BALANCE,
        EXCEEDS_TRIAL_LIMIT, REJECTED_BY_POLICY
    }

    record LeaveDecision(DecisionCode code, String explanation) {
        LeaveDecision {
            Objects.requireNonNull(code, "code");
            if (explanation == null || explanation.isBlank()) {
                throw new IllegalArgumentException("Explanation is required");
            }
        }

        boolean approved() {
            return code == DecisionCode.APPROVED;
        }
    }

    /**
     * Đánh giá một request hợp lệ, khác null.
     * Trả LeaveDecision khác null.
     * Không APPROVED khi requestedDays > remainingDays.
     * Không sửa request hay số dư; không lưu/phê duyệt đơn thật.
     * Null input -> NullPointerException.
     */
    interface LeavePolicy {
        LeaveDecision evaluate(LeaveRequest request);
    }

    static final class StandardLeavePolicy implements LeavePolicy {
        @Override
        public LeaveDecision evaluate(LeaveRequest request) {
            Objects.requireNonNull(request, "request");
            if (request.requestedDays() > request.remainingDays()) {
                return new LeaveDecision(
                        DecisionCode.INSUFFICIENT_BALANCE,
                        "Số ngày phép còn lại không đủ");
            }
            return new LeaveDecision(
                    DecisionCode.APPROVED, "Đủ ngày phép");
        }
    }

    static final class TrialLeavePolicy implements LeavePolicy {
        @Override
        public LeaveDecision evaluate(LeaveRequest request) {
            Objects.requireNonNull(request, "request");
            if (request.requestedDays() > request.remainingDays()) {
                return new LeaveDecision(
                        DecisionCode.INSUFFICIENT_BALANCE,
                        "Số ngày phép còn lại không đủ");
            }
            if (request.requestedDays() > 2) {
                return new LeaveDecision(
                        DecisionCode.EXCEEDS_TRIAL_LIMIT,
                        "Giới hạn thử việc là 2 ngày");
            }
            return new LeaveDecision(
                    DecisionCode.APPROVED, "Đạt quy tắc thử việc");
        }
    }

    static final class LeaveReviewService {
        private final LeavePolicy policy;

        LeaveReviewService(LeavePolicy policy) {
            this.policy = Objects.requireNonNull(policy, "policy");
        }

        LeaveDecision review(LeaveRequest request) {
            return policy.evaluate(request);
        }
    }

    static void print(
            String name, LeavePolicy policy, LeaveRequest request) {
        LeaveDecision result =
                new LeaveReviewService(policy).review(request);
        System.out.println(name + ": " + result.code()
                + " - " + result.explanation());
    }

    public static void main(String[] args) {
        LeaveRequest request = new LeaveRequest("NV-01", 3, 5);
        print("Thông thường", new StandardLeavePolicy(), request);
        print("Thử việc", new TrialLeavePolicy(), request);

        LeaveRequest insufficient = new LeaveRequest("NV-02", 6, 5);
        print("Thiếu phép", new StandardLeavePolicy(), insufficient);
    }
}
~~~

Run:

~~~bash
javac LeaveContractDemo.java
java LeaveContractDemo
~~~

Output:

~~~text
Thông thường: APPROVED - Đủ ngày phép
Thử việc: EXCEEDS_TRIAL_LIMIT - Giới hạn thử việc là 2 ngày
Thiếu phép: INSUFFICIENT_BALANCE - Số ngày phép còn lại không đủ
~~~

**Step-by-step explanation:**

1. The first request asks for 3 days with 5 remaining; this is valid input.
2. `StandardLeavePolicy` checks that requested days do not exceed the balance and returns `APPROVED`.
3. `TrialLeavePolicy` is also called through `LeavePolicy.evaluate`, but applies the additional 2-day limit and therefore returns `EXCEEDS_TRIAL_LIMIT`.
4. The second request asks for 6 days with 5 remaining, so the standard policy returns `INSUFFICIENT_BALANCE`.
5. No operation deducts the balance. `remainingDays` is an **input snapshot**, and `APPROVED` here means only "passed policy evaluation", not final approval of a leave transaction.

Different results do not imply a contract violation. Individual policies are intentionally allowed to apply additional criteria, but every implementation must preserve the **shared rule: never approve a request exceeding the remaining balance**.

## 3. Dependency Map and Responsibilities

~~~mermaid
classDiagram
    class LeavePolicy {
        <<interface>>
        +evaluate(LeaveRequest) LeaveDecision
    }
    class StandardLeavePolicy {
        +evaluate(LeaveRequest) LeaveDecision
    }
    class TrialLeavePolicy {
        +evaluate(LeaveRequest) LeaveDecision
    }
    class LeaveReviewService {
        -LeavePolicy policy
        +review(LeaveRequest) LeaveDecision
    }
    LeavePolicy <|.. StandardLeavePolicy
    LeavePolicy <|.. TrialLeavePolicy
    LeaveReviewService --> LeavePolicy
~~~

**`LeaveReviewService` is the client:** it knows only the `LeavePolicy` type and `LeaveDecision` result. Object construction or configuration decides which policy is passed to the constructor. The interface **does not choose** the appropriate policy for an employee on its own.

**`LeavePolicy` is the contract:** it exposes the evaluation capability, input/output types, and behavioral promises. It does not specify the algorithm.

**`StandardLeavePolicy` and `TrialLeavePolicy` are implementations:** each class is responsible for satisfying the contract, including rejecting `null` and refusing approval when requested days exceed the balance.

Constructor injection in this example passes a dependency from outside. No DI container is required. When a different valid implementation is provided, `LeaveReviewService.review` still need not know the new class's name.

## 4. Distinguishing Method Signatures from Behavioral Contracts

The Java signature:

~~~java
LeaveDecision evaluate(LeaveRequest request);
~~~

tells the compiler a method's name, parameter types, and return type. It **does not itself enforce** every promise, such as "never return null", "do not write to the database", or "do not approve leave beyond the balance".

| Item | Can the Java compiler check it? | What else must be verified |
| --- | --- | --- |
| Has method `evaluate(LeaveRequest)` | Yes | Business meaning |
| Returns `LeaveDecision` | Yes | Whether `null` can be returned when prohibited |
| Request created through a valid constructor | Constructor validates at runtime | Other creation paths and source-data rules |
| Do not approve when the balance is insufficient | Not through the signature | Test requested days > remaining days |
| No side effects | Not through the signature | Code review, tests, and documentation |
| Decision code has the correct meaning | Not through the signature | Scenario tests and shared conventions |

For example, this implementation is wrong even though it compiles:

~~~java
static final class BrokenLeavePolicy implements LeavePolicy {
    @Override
    public LeaveDecision evaluate(LeaveRequest request) {
        return null; // Vi phạm cam kết kết quả khác null.
    }
}
~~~

You can place this snippet as a nested class in `LeaveContractDemo` to observe it. `@Override` only helps the compiler verify that a method correctly overrides a signature; it does not prove correct behavior.

### Things Callers Must Know and Must Not Be Mistakenly Hidden

A real contract may need to specify when leave balances are read, how stale data is handled, approval permissions, persistence state, network errors, and concurrency conditions. If an implementation switches from in-memory evaluation to calling an HR API, timeouts and stale data **may become observable**. Do not promise "identical behavior in every respect" merely because the method name is unchanged.

In this example, `evaluate` deliberately evaluates only the supplied data. Updating leave balances belongs in **a separate use case or transaction** with concurrency control. If two employees or requests use the same balance snapshot, two `APPROVED` decisions do not guarantee that sufficient leave exists to fulfill both requests simultaneously.

## 5. Substitutability Depends on the Contract, Not Just an Interface

The Liskov Substitution Principle (LSP) here means that one implementation can replace another without breaking the **shared promises** clients are entitled to rely on.

Do not assume the two policies must return the same decision. The problem explicitly allows the probationary policy to impose a stricter leave limit, but neither policy may return `APPROVED` when `requestedDays > remainingDays`.

| Implementation behavior | Complies with the example contract? | Why |
| --- | --- | --- |
| Standard policy approves 3/5 days | Yes | The standard rule permits it |
| Probationary policy rejects 3/5 days | Yes | This policy imposes a 2-day limit |
| An implementation returns `APPROVED` for 6/5 days | No | Violates the shared balance guarantee |
| An implementation returns `null` for an invalid request | No | The contract requires a non-null result for a valid request |
| An implementation deducts leave days during evaluation | No | Violates the no-side-effects guarantee |
| Uses a different data structure or algorithm | Yes | Implementation details may change |
| Changes the explanation while preserving the correct code | Usually yes | Unless the exact explanation text is part of the promised API |

Another practical rule: an implementation must not **strengthen shared preconditions** so that contract-valid calls unexpectedly fail, nor **weaken shared postconditions**. Here, policies may *return a valid rejection result*, which differs from *throwing a new error not described by the contract*.

LSP does not require every policy to accept the same requests; the **meaning of different outcomes** must remain consistent.

## 6. Contract Tests and Client Tests Serve Different Purposes

### A. Shared Tests for Implementations

You can add the following method to `LeaveContractDemo`:

~~~java
static void verifyContract(LeavePolicy policy) {
    LeaveRequest insufficient = new LeaveRequest("NV-X", 6, 5);
    LeaveDecision rejected = policy.evaluate(insufficient);

    if (rejected == null || rejected.approved()) {
        throw new AssertionError("Policy approved excessive leave");
    }
    if (policy.evaluate(new LeaveRequest("NV-Y", 1, 3)) == null) {
        throw new AssertionError("Policy returned null");
    }

    try {
        policy.evaluate(null);
        throw new AssertionError("Null must be rejected");
    } catch (NullPointerException expected) {
        // Đúng hợp đồng về null.
    }
}
~~~

Call `verifyContract(new StandardLeavePolicy())` and `verifyContract(new TrialLeavePolicy())` to check the **shared guarantees**. Do not write a shared test asserting "every policy always approves 3 days", because the probationary limit explicitly allows rejection.

This is only a sample test; it does not prove correctness for every input. Real applications should add edge cases such as a balance of 0, update timing, provider failures, and integration tests.

### B. Testing the Client with a Fake Implementation

To test only whether `LeaveReviewService` **passes the correct request and receives the correct result**, we do not need the actual policy:

~~~java
static final class FixedRejectPolicy implements LeavePolicy {
    @Override
    public LeaveDecision evaluate(LeaveRequest request) {
        Objects.requireNonNull(request, "request");
        return new LeaveDecision(
                DecisionCode.REJECTED_BY_POLICY, "Kết quả giả lập");
    }
}
~~~

This is a contract-compliant *test double*: rejection is a valid result, the input is still checked, and there are no side effects. It allows testing the client independently of the real policy algorithm.

**A test double does not replace the provider's contract tests.** A client that works with a fake does not establish that its database or HTTP implementation preserves the same semantics.

## 7. Interface, Abstract Class, or Public Method: How Much Is Enough?

Abstraction is a design decision; it does not require an `interface`. A concrete class that clearly exposes `evaluate` and hides its calculation can also offer a good API.

| When needed | Suggestion |
| --- | --- |
| One simple, stable policy | A concrete class with a clearly specified public method |
| Multiple policies share behavior; the client must replace them independently | A small interface such as `LeavePolicy` |
| A genuine class family shares instance state, constructors, and most of the workflow | Consider an `abstract class` |
| Only a validation rule or algorithm must be reused | Helper function or composition; inheritance may be unnecessary |
| Several interfaces simply forward the same call | Consider removing layers with no responsibility |

An `interface` has no constructors or instance fields; an `abstract class` can hold state and shared implementation, but Java permits only one direct superclass. Detailed syntax for `abstract` belongs to the dedicated abstract classes/methods lesson; here, the main criterion is **which contract clients need to depend on**.

The Dependency Inversion Principle (DIP) suggests that orchestration modules depend on stable contracts instead of hardcoding concrete providers. It **does not** require every small class to have its own interface.

## 8. When Implementations Depend on External Systems

A real policy might query an HR service through a REST API or SDK. `LeaveReviewService` need not know the provider's URL, JSON fields, HTTP headers, or error codes.

The responsibilities can be organized at these boundaries:

~~~mermaid
flowchart LR
    A["LeaveReviewService"] --> C["LeavePolicy<br/>Hợp đồng ứng dụng"]
    P["RemoteHrPolicyAdapter"] -. "implements" .-> C
    P --> H["SDK / HTTP HR"]
    H --> P
    P --> R["LeaveDecision"]
~~~

An adapter maps `LeaveRequest` to provider data, invokes the service, converts its response into `LeaveDecision`, and represents errors using the application's contract. Distinguish **a policy rejection** from **an inability to evaluate because the system failed**.

Example of an error boundary (illustrative code, not a complete file):

~~~java
try {
    // Gọi provider và chuyển phản hồi thành LeaveDecision.
} catch (java.io.IOException ex) {
    throw new HrPolicyUnavailableException(
            "Không thể đánh giá lúc này", ex);
}
~~~

`HrPolicyUnavailableException` is an application exception type that must be declared and given handling rules. This is only a descriptive pattern; mapping every failure to the same exception is not necessarily appropriate. Real systems must specify timeouts, retries, idempotency, stale-data handling, and which failures affect callers.

**In particular, never convert a network error into `APPROVED` or `INSUFFICIENT_BALANCE`** simply to always produce a result. That misrepresents the outcome and falsely suggests the policy check succeeded.

## 9. Contract Changes Can Affect Clients

Keeping the name `evaluate` does not guarantee the contract remains compatible.

| Change | Assessment |
| --- | --- |
| Optimize a private helper without changing semantics | Usually invisible to callers |
| Change a policy's algorithm within its advertised bounds | Callers need not change their calls, but business tests are needed |
| Rename `evaluate` or change the return type | Usually causes compilation errors for callers/implementations |
| Add an abstract method to `LeavePolicy` | Existing implementations must implement it |
| Add a default method | May improve compatibility, but conflicts and semantics must be considered |
| Change `remainingDays` from days to hours without renaming the field | Breaks semantics/units even if the type remains `int` |
| Automatically deduct leave in `evaluate` | Breaks the no-side-effects guarantee |
| Return `null` instead of a rejection decision | Breaks the non-null result promise |
| Throw a new exception for previously rejected but valid input | May break caller logic |
| Switch from local computation to a network call | Consider timeouts, transient errors, and snapshot validity |

If a contract must change, assess source, binary, and behavioral compatibility within the application; version the API if needed, update callers and implementations, and retain contract tests.

**Difference from internal refactoring:** adjusting a private formula may leave the API unchanged; changing a parameter's meaning, commitment timing, or error type can be a **breaking change** even if the Java signature looks identical.

## 10. When Is a Contract Too Broad or Leaking Implementation Details?

Both of these designs can confuse consumers:

~~~java
// Quá mơ hồ: caller phải đoán ngữ nghĩa và ép kiểu.
interface GenericOperation {
    Object execute(Object input);
}

// Rò rỉ hạ tầng: nghiệp vụ bị ép hiểu cách truy xuất cụ thể.
interface RawHrConnector {
    java.sql.ResultSet queryVacationBalance(String employeeId)
            throws java.sql.SQLException;
}
~~~

The `LeavePolicy.evaluate(LeaveRequest)` contract is clearer because it exposes the required behavior and data types. However, if the application deliberately provides a low-level JDBC query library, `ResultSet` may itself be the appropriate contract. Whether something "leaks" depends on **who consumes the API and what they need to know**.

When an API expands to dozens of unrelated methods, some implementations may throw `UnsupportedOperationException` for unsupported operations. That suggests splitting the contract into meaningful capabilities rather than requiring every provider to pretend it supports everything.

A good API does not hide **observable properties callers need to know**. Inputs, results, errors, data freshness, commitment timing, and side effects can all be essential. Details worth hiding are implementation choices *unnecessary for using the contract correctly*.

## 11. Practice: Test Your Ability to Read Contracts

**Question 1.** `LeaveReviewService` declares a `LeavePolicy` field rather than `TrialLeavePolicy`. What is the benefit?

**Hint:** The client depends only on the evaluation capability, so the policy can change at configuration time without editing the `review` method.

**Question 2.** A `LeavePolicy` returns `null` when a request exceeds the leave balance. The code still compiles. Does it satisfy the contract?

**Hint:** No. A valid request must return a non-null `LeaveDecision`; insufficient balance is a rejection decision, not an absence of a result.

**Question 3.** Why may `StandardLeavePolicy` and `TrialLeavePolicy` return different decisions for the same request?

**Hint:** The contract allows specific policies to apply their own rules. They must still respect the shared rules, especially never approving beyond the balance or modifying the input.

**Question 4.** The provider switches to HTTP but still returns `LeaveDecision`. Should the contract be reconsidered?

**Hint:** Possibly: timeouts, transient errors, data freshness, and timing-dependent behavior affect callers. A signature does not itself guarantee these properties.

**Question 5.** Does `@Override` prove that the leave balance was checked correctly?

**Hint:** No. It only confirms the override relationship at compile time; promised postconditions and semantics require testing.

**Question 6.** Should every class get an `ILeaveReviewService` to "meet OOP standards"?

**Hint:** No such rule exists. Introduce a contract layer only when there is a dependency boundary, a need for substitution, or a genuinely independent set of behaviors.

**Question 7.** May the same `LeavePolicy` both evaluate a request and deduct the leave quota?

**Hint:** Not under the stated contract. Granting leave and recording its balance require a separate use case, a transaction, and concurrency checks. Do not silently change the responsibility of `evaluate`.

## Checklist for Designing Durable Contracts

Before finalizing an API, ask: **Who calls it?**; **Are inputs/outputs and units clear?**; **Which preconditions/postconditions may callers rely on?**; **What errors, side effects, timing, and concurrency guarantees are promised?**; **Can two implementations substitute for each other legitimately?**; **Are there shared contract tests?**; **Are unnecessary infrastructure details exposed?**

A contract is a **trust boundary** between consuming code and its implementation. Good abstraction allows controlled internal changes without making external consumers guess what each implementation means.
