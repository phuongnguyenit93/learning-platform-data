# Composing Validation Rules Using Named `Predicate`s in Java

## 1. Why Name Validation Rules?

In Java applications, many decisions do not rely on a single condition. For example, a candidate is eligible for registration when they are **at least 18 years old, have an active account, are verified, and have a minimally valid email**.

If all that logic is placed inside one lambda, the code can quickly become hard to read:

~~~java
List<Candidate> accepted = candidates.stream()
        .filter(c -> c != null
                && c.age() >= 18
                && c.active()
                && c.verified()
                && c.email() != null
                && !c.email().isBlank())
        .toList();
~~~

In this example, `Candidate` is an application-declared record, fully defined in the standalone runnable program later in the lesson.

An alternative is to **name the small rules**, then compose them:

~~~java
Predicate<Candidate> eligible = IS_NOT_NULL
        .and(IS_ADULT)
        .and(IS_ACTIVE)
        .and(IS_VERIFIED)
        .and(HAS_EMAIL);

List<Candidate> accepted = candidates.stream()
        .filter(eligible)
        .toList();
~~~

When reading the expression, readers clearly see **the business conditions** instead of decoding a long lambda. Each `Predicate` can also be tested, reused, and composed into other policies.

**Lesson goals:** understand `Predicate<T>`, how to declare named rules via variables/constants/method references, composition with `and()`, `or()`, and `negate()`, short-circuiting rules, meaningful naming and `null` handling, rule testing, integration with `Stream.filter`, while avoiding side effects and common logic bugs.

## 2. What Is `Predicate<T>`?

`java.util.function.Predicate<T>` is a functional interface representing a **condition that takes a value of type `T` and returns `boolean`**. Its single abstract method is:

~~~java
boolean test(T value);
~~~

Example:

~~~java
Predicate<String> isLong = s -> s.length() >= 5;

System.out.println(isLong.test("Java"));   // false
System.out.println(isLong.test("Stream")); // true
~~~

It can be written with a lambda or a method reference:

~~~java
Predicate<String> isBlank = String::isBlank;
Predicate<Integer> positive = n -> n > 0;
Predicate<String> nonNull = Objects::nonNull;
~~~

`Predicate` **does not** return error messages or modify its input. It only reports whether a condition is true or false. If the business logic needs to know *why* data is invalid, a validation result with an error list is more suitable; see Section 12.

Key properties:

- Type `T` is the **input** type, not the output type.
- `Predicate<String>` is commonly passed to `Stream<String>.filter(...)`.
- A `Predicate` can be called directly via `test(value)` or passed to APIs accepting a `Predicate`.
- Composition methods `and`, `or`, `negate` create **a new Predicate** without modifying the original Predicate's logic.
- A `Predicate` can contain a lambda closing over external variables (*captured variables*); for ease of reasoning and parallel use, avoid depending on mutable state that changes during evaluation.

## 3. Naming Rules: From Lambdas to Business Expressions

Suppose we have a record:

~~~java
record Candidate(
        String id,
        int age,
        boolean active,
        boolean verified,
        String email) {}
~~~

Declare named rules as `static final` constants:

~~~java
static final Predicate<Candidate> IS_NOT_NULL =
        Objects::nonNull;

static final Predicate<Candidate> IS_ADULT =
        c -> c.age() >= 18;

static final Predicate<Candidate> IS_ACTIVE =
        Candidate::active;

static final Predicate<Candidate> IS_VERIFIED =
        Candidate::verified;

static final Predicate<Candidate> HAS_EMAIL =
        c -> c.email() != null && !c.email().isBlank();
~~~

These names describe **what is being checked**, not how it is implemented:

- `IS_NOT_NULL`: does the `Candidate` object exist?
- `IS_ADULT`: is the candidate at least 18 years old?
- `IS_ACTIVE`: is the account active?
- `IS_VERIFIED`: has verification status been achieved?
- `HAS_EMAIL`: is the email non-null and not just whitespace?

`HAS_EMAIL` in this lesson only checks **non-null/non-blank**; it **does not** verify RFC-compliant email syntax or actual existence. The name should reflect the strength of the check; in a real application it could be renamed to `HAS_NON_BLANK_EMAIL` to avoid over-expectation.

The Predicates `IS_ADULT`, `IS_ACTIVE`, `IS_VERIFIED`, and `HAS_EMAIL` above assume a **non-`null`** input. To compose safely for potentially null data, place `IS_NOT_NULL` at the start of the `and` chain, as shown next.

### 3.1. Parameterized Rules: Factory Methods

Not every threshold should be hard-coded as a constant:

~~~java
static Predicate<Candidate> ageAtLeast(int minimumAge) {
    return c -> c != null && c.age() >= minimumAge;
}
~~~

Rules can be created by context:

~~~java
Predicate<Candidate> adult = ageAtLeast(18);
Predicate<Candidate> seniorProgram = ageAtLeast(21);
~~~

Here `minimumAge` is captured by the lambda; each method call creates/represents a distinct policy. With an immutable primitive parameter, this is easier to test and safer than having the predicate read a threshold variable that multiple threads might update.

## 4. `and()`: All Rules Must Be True

Method:

~~~java
default Predicate<T> and(Predicate<? super T> other);
~~~

The result corresponds to **logical AND**:

\[
(A \land B)(x)=A(x)\ \&\&\ B(x).
\]

Example:

~~~java
Predicate<Integer> positive = n -> n > 0;
Predicate<Integer> even = n -> n % 2 == 0;

Predicate<Integer> positiveEven = positive.and(even);

System.out.println(positiveEven.test(4));  // true
System.out.println(positiveEven.test(-2)); // false
System.out.println(positiveEven.test(3));  // false
~~~

`and()` uses **short-circuit evaluation**: if the left Predicate returns `false`, the right Predicate **is not called**. Therefore, a null check can guard property accesses:

~~~java
Predicate<Candidate> safeAdult =
        IS_NOT_NULL.and(IS_ADULT);

System.out.println(safeAdult.test(null)); // false, does not throw.
~~~

When passing `null`:

1. `IS_NOT_NULL.test(null)` returns `false`.
2. Because the first operand of `and` is false, `IS_ADULT.test(null)` is not called.
3. The composed Predicate's result is `false`.

**Composition order can affect safety:**

~~~java
Predicate<Candidate> safe = IS_NOT_NULL.and(IS_ADULT);

// Not null-safe:
// Predicate<Candidate> unsafe = IS_ADULT.and(IS_NOT_NULL);
~~~

With `unsafe.test(null)`, `IS_ADULT` accesses `c.age()` first and will throw `NullPointerException`. Two rules can be logically equivalent over non-null data yet **have different behavior on null or exceptions**.

When evaluation functions have different costs, order also affects performance: placing cheap checks that filter out many elements before expensive checks can help, as long as semantics are unchanged and there are no side-effect dependencies.

## 5. `or()`: Only One Rule Needs to Be True

Method:

~~~java
default Predicate<T> or(Predicate<? super T> other);
~~~

Corresponds to **logical OR**:

\[
(A \lor B)(x)=A(x)\ ||\ B(x).
\]

Example:

~~~java
Predicate<Integer> isZero = n -> n == 0;
Predicate<Integer> isNegative = n -> n < 0;

Predicate<Integer> nonPositive = isZero.or(isNegative);

System.out.println(nonPositive.test(0)); // true
System.out.println(nonPositive.test(-2)); // true
System.out.println(nonPositive.test(3)); // false
~~~

`or()` also short-circuits: if the left side is `true`, the right side does not need to run. However, do not use OR as a careless null guard:

~~~java
Predicate<Candidate> notNull = Objects::nonNull;
Predicate<Candidate> adult = c -> c.age() >= 18;

// Wrong if expecting safe null rejection:
// Predicate<Candidate> wrong = notNull.or(adult);
~~~

With `null`, `notNull` returns false and OR forces `adult` to be called; this can throw `NullPointerException`.

If you want “allow null or be an adult”, write the corresponding condition explicitly:

~~~java
Predicate<Candidate> nullOrAdult =
        ((Predicate<Candidate>) Objects::isNull).or(IS_ADULT);
~~~

In this code, null yields true because the left side is already true; for non-null, the right side checks age. However, **allowing null** is a different business policy from **accepting only valid Candidates**. Do not use it when null must be rejected.

## 6. `negate()` and `Predicate.not()`

### 6.1. `negate()` Inverts an Existing Rule

~~~java
Predicate<Integer> isEven = n -> n % 2 == 0;
Predicate<Integer> isOdd = isEven.negate();

System.out.println(isOdd.test(3)); // true
System.out.println(isOdd.test(4)); // false
~~~

`negate()` creates a Predicate whose logical result is the negation of the original Predicate. It **does not modify the `isEven` variable**:

~~~java
System.out.println(isEven.test(4)); // true, unchanged.
~~~

For candidates:

~~~java
Predicate<Candidate> isNotActive = IS_ACTIVE.negate();
~~~

Note that `isNotActive.test(null)` is not safe, because to negate the result, the original Predicate still has to run and access `Candidate::active`. It is usually best to combine with a non-null check beforehand:

~~~java
Predicate<Candidate> knownInactive =
        IS_NOT_NULL.and(IS_ACTIVE.negate());
~~~

Here `knownInactive.test(null)` returns false. This also clearly distinguishes between “no Candidate” and “Candidate exists but is inactive”.

### 6.2. `Predicate.not()` Is Convenient with Method References

Since Java 11, there is a static method:

~~~java
static <T> Predicate<T> not(Predicate<? super T> target);
~~~

Use it directly when you want to negate a method reference:

~~~java
List<String> names = List.of("Java", "", "Stream", "   ");

List<String> nonBlank = names.stream()
        .filter(Predicate.not(String::isBlank))
        .toList();

System.out.println(nonBlank); // [Java, Stream]
~~~

Compare:

~~~java
Predicate<String> isBlank = String::isBlank;
List<String> nonBlank = names.stream()
        .filter(isBlank.negate())
        .toList();
~~~

Both approaches are valid. `Predicate.not(String::isBlank)` is often concise when an expression needs to negate a method reference on the spot; for already-named business rules, `IS_ACTIVE.negate()` can be easier to read.

**Be careful:** `Predicate.not` does not handle null or exceptions inside the inner predicate by itself. If the input can be null, `String::isBlank` does not accept null safely; filter `Objects::nonNull` first.

### 6.3. Negating Compound Expressions: De Morgan's Laws

If `eligible = adult.and(active)`, then:

~~~java
Predicate<Candidate> notEligible = eligible.negate();
~~~

logically can be written equivalently using De Morgan's law:

~~~java
Predicate<Candidate> notAdultOrInactive =
        IS_ADULT.negate().or(IS_ACTIVE.negate());
~~~

**But it is only equivalent on an input domain where all predicates are safely defined**, such as non-null Candidates. Do not assume `IS_NOT_NULL.and(IS_ADULT).negate()` is the same as `IS_NOT_NULL.and(IS_ADULT.negate())` on null:

- `IS_NOT_NULL.and(IS_ADULT)` returns false for null.
- Negating the whole expression returns **true** for null.
- `IS_NOT_NULL.and(IS_ADULT.negate())` returns **false** for null.

This is a notable logic bug when creating a “rejected” rule: you may want to exclude null records from a report or treat null as a rejected case. Define your goal clearly before negating an entire expression.

## 7. Combining Multiple Named Rules into a Policy

Suppose the eligibility condition is:

~~~java
static final Predicate<Candidate> ELIGIBLE =
        IS_NOT_NULL
                .and(IS_ADULT)
                .and(IS_ACTIVE)
                .and(IS_VERIFIED)
                .and(HAS_EMAIL);
~~~

This expression means:

\[
\text{eligible}
= \text{notNull}
\land \text{adult}
\land \text{active}
\land \text{verified}
\land \text{hasEmail}.
\]

Naming it `ELIGIBLE` saves call sites from repeating the condition structure:

~~~java
List<Candidate> accepted = candidates.stream()
        .filter(ELIGIBLE)
        .toList();

boolean canRegister = ELIGIBLE.test(candidate);

boolean hasAnyoneEligible = candidates.stream()
        .anyMatch(ELIGIBLE);
~~~

`Predicate` acts as **a policy that can be passed as data**: another API can accept a `Predicate<Candidate> policy` parameter without knowing the details of each individual rule.

### 7.1. Building a “Status Violation” Rule with OR

~~~java
static final Predicate<Candidate> HAS_BAD_STATUS =
        IS_NOT_NULL.and(
                IS_ACTIVE.negate().or(IS_VERIFIED.negate()));
~~~

Meaning: Candidate exists, and **is inactive or unverified**. Because `IS_NOT_NULL` is checked first, the composed Predicate safely rejects null.

Using `IS_ACTIVE.negate().or(IS_VERIFIED.negate())` directly with null can throw an error. Always inspect the whole expression, not just individual parts.

### 7.2. Expressing Rules as Named Methods

Some teams prefer named methods over constants:

~~~java
static boolean isAdult(Candidate c) {
    return c != null && c.age() >= 18;
}

static boolean hasUsableEmail(Candidate c) {
    return c != null && c.email() != null && !c.email().isBlank();
}

Predicate<Candidate> rule =
        ((Predicate<Candidate>) Rules::isAdult)
                .and(Rules::hasUsableEmail);
~~~

This snippet assumes a `Rules` class owning both static methods; it illustrates method references, not a standalone file. When there are only a few conditions, named methods can be easier to test; when flexible passing or composition is needed, keeping named `Predicate<T>`s is especially convenient.

## 8. Integrating with Stream Operations

### 8.1. `filter`: Keeping Elements That Match the Rule

~~~java
List<Candidate> accepted = candidates.stream()
        .filter(ELIGIBLE)
        .toList();
~~~

`filter` requires a `Predicate<? super T>` and keeps elements when `test` returns true. It **does not transform** `Candidate`. Filtering does not mutate the source list.

### 8.2. `anyMatch`, `allMatch`, `noneMatch`

~~~java
boolean anyEligible = candidates.stream().anyMatch(ELIGIBLE);
boolean allEligible = candidates.stream().allMatch(ELIGIBLE);
boolean noneEligible = candidates.stream().noneMatch(ELIGIBLE);
~~~

- `anyMatch`: at least one element matches the rule.
- `allMatch`: every element matches the rule.
- `noneMatch`: no element matches the rule.

These three terminal operations **short-circuit** and can stop early; do not assume the predicate is called on the entire source. On an empty Stream: `anyMatch` returns false, while `allMatch` and `noneMatch` return true per vacuous truth. This matters if business logic needs to distinguish empty data from “all valid”.

### 8.3. `dropWhile`, `takeWhile`, `removeIf`

`takeWhile` and `dropWhile` (Java 9+) also take a Predicate, but behave **differently from `filter`**:

~~~java
List<Integer> values = List.of(2, 4, 7, 8, 10);
Predicate<Integer> isEven = n -> n % 2 == 0;

System.out.println(values.stream()
        .takeWhile(isEven)
        .toList()); // [2, 4]

System.out.println(values.stream()
        .filter(isEven)
        .toList()); // [2, 4, 8, 10]
~~~

For an ordered source, `takeWhile` only takes the **contiguous prefix** satisfying the predicate, stopping at 7; `filter` checks subsequent elements as well when a full result is needed.

`Collection.removeIf` also takes a Predicate, but it **mutates the original mutable collection**, unlike `Stream.filter` which produces a stream of retained elements:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));
numbers.removeIf(n -> n % 2 == 0);
System.out.println(numbers); // [1, 3]
~~~

Do not call `removeIf` on the same collection **from inside a callback traversing a Stream of that collection**, as that violates non-interference.

## 9. Intentional Null Handling

Null is one of the main reasons to design rule names and ordering well.

### 9.1. `Objects::nonNull` as a Guard

~~~java
Predicate<String> isNonBlank =
        ((Predicate<String>) Objects::nonNull)
                .and(s -> !s.isBlank());

System.out.println(isNonBlank.test(null));  // false
System.out.println(isNonBlank.test("   ")); // false
System.out.println(isNonBlank.test("Java")); // true
~~~

`Objects::nonNull` is a convenient method reference for a Predicate. It is not the entire policy: the second `and` operand expresses the non-blank string constraint.

### 9.2. `Predicate.isEqual` Handles Value Equality

`Predicate.isEqual(targetRef)` (Java 8+) creates a Predicate to compare via `equals`, with appropriate null handling:

~~~java
Predicate<String> isAdmin = Predicate.isEqual("admin");

System.out.println(isAdmin.test("admin")); // true
System.out.println(isAdmin.test("guest")); // false
System.out.println(isAdmin.test(null));    // false

Predicate<String> isNull = Predicate.isEqual(null);
System.out.println(isNull.test(null));     // true
~~~

`isEqual` does not mean reference comparison with `==`. For a non-null target, it evaluates equality equivalently to `target.equals(input)`; the result depends on `equals`'s implementation. For a null target, the Predicate checks for null input.

### 9.3. Does “Invalid” Include Null or Not?

Both policies are valid in different contexts:

~~~java
Predicate<Candidate> rejectedIncludingNull =
        ELIGIBLE.negate();

Predicate<Candidate> rejectedNonNullOnly =
        IS_NOT_NULL.and(ELIGIBLE.negate());
~~~

- `rejectedIncludingNull.test(null) == true`: treats null as ineligible.
- `rejectedNonNullOnly.test(null) == false`: only cares about existing Candidates that are ineligible.

Do not confuse the two expressions. When using `Stream.filter` to build a report, your choice decides whether a null element is kept in the “rejected” result.

## 10. When Should You Use Named `Predicate`s?

Named Predicates are especially useful when:

1. **A rule repeats** in multiple places: service validation, list filters, permission checks, or reports.
2. **Business logic needs readability**: `ELIGIBLE` and `HAS_BAD_STATUS` are more meaningful than a long operator chain.
3. **Flexible composition is needed** by context: apply both `HAS_EMAIL` and `IS_VERIFIED` on screen A, but only `IS_ACTIVE` on screen B.
4. **Independent testing is needed** for each rule, then for the composed policy.
5. **You want to swap a rule's implementation** while keeping call sites unchanged.
6. **You need to pass policies as parameters** without creating many `if/else` branches in data-processing APIs.

However, not every one-line condition must become a static constant. If used once and the expression is obvious (`n -> n > 0`), keeping an inline lambda can be shorter and clearer. Naming is valuable when it **explains intent**, not just naming things `P1`, `CHECK1`, or `RULE_A`.

### 10.1. Choose Positive and Consistent Names

Prefer:

~~~java
IS_ACTIVE
IS_VERIFIED
HAS_NON_BLANK_EMAIL
IS_ADULT
ELIGIBLE
~~~

over vague names:

~~~java
VALID
CHECK
FLAG
PRED
TESTER
~~~

If you use a name like `NOT_ACTIVE`, clearly define whether it means “Candidate exists and is inactive” or “no evidence of being active, including null”. Naming must match the policy across the entire valid data domain.

### 10.2. Immutability and Parameterization

If a policy depends on a user-supplied threshold, build a factory method with an immutable parameter:

~~~java
static Predicate<Candidate> minAge(int threshold) {
    return c -> c != null && c.age() >= threshold;
}
~~~

If a policy depends on a set of allowed codes:

~~~java
static Predicate<String> oneOf(Set<String> allowedCodes) {
    Set<String> snapshot = Set.copyOf(allowedCodes);
    return snapshot::contains;
}
~~~

`Set.copyOf` returns an unmodifiable Set and rejects null, preventing `allowedCodes` from being unexpectedly mutated after creating the Predicate. However, it does not deep-copy element state if elements are mutable; for immutable `String` codes, this works well.

### 10.3. Order Checks by Dependency

Place guarding conditions before later operands:

~~~java
Predicate<Candidate> safe = IS_NOT_NULL
        .and(HAS_EMAIL)
        .and(IS_ACTIVE);
~~~

Dropping this order can turn a policy that returns false for null into an exception. For two conditions that are both expensive and side-effect-free, order can be tuned based on cost and actual rejection rate.

## 11. Testability: Unit Tests and Truth Tables

Named rules let each condition be tested individually via `test`:

~~~java
assert IS_ADULT.test(candidateAdult);
assert !IS_ADULT.test(candidateMinor);
assert ELIGIBLE.test(eligibleCandidate);
assert !ELIGIBLE.test(ineligibleCandidate);
~~~

`assert` statements are illustrative only; by default many Java setups do not enable assertions without `-ea`. In real projects, prefer a unit-test framework for consistent CI execution, such as JUnit 5 (an external dependency outside the JDK).

A test table for the `ELIGIBLE` policy:

| Candidate | Age ≥18 | Active | Verified | Non-blank Email | Result |
| --- | --- | --- | --- | --- | --- |
| A | True | True | True | True | true |
| B | False | True | True | True | false |
| C | True | False | True | True | false |
| D | True | True | False | True | false |
| E | True | True | True | False | false |
| F | True | True | True | True | true |
| null | — | — | — | — | false if starting with `IS_NOT_NULL` |

The most important tests are usually at **boundaries**: age 17/18, null/blank email, single failing flag, all conditions true, and null input.

### 11.1. Compactly Testing Composition Laws

For two Predicates that are safe over the data domain under consideration, you can verify:

- `A.and(B)` is true only when both A and B are true.
- `A.or(B)` is true when at least one side is true.
- `A.negate()` inverts A's result.
- `A.and(B)` preserves A's meaning if B is always true.
- `A.or(B)` preserves A's meaning if B is always false.

These properties rely on **pure, non-throwing, side-effect-free functions**. If a Predicate logs, updates counters, throws exceptions, or reads mutable state, short-circuit order can produce different effects even though the logical truth table looks equivalent.

## 12. When `Predicate` Is Not Enough for a Validation System

`Predicate<T>` only returns a boolean; it carries no failure reason.

~~~java
boolean eligible = ELIGIBLE.test(candidate);
~~~

But a registration form may need to report **which rules failed**. An explicit approach is to build a validator returning results with error codes:

~~~java
record Violation(String code, String message) {}

static List<Violation> validateCandidate(Candidate c) {
    if (c == null) {
        return List.of(new Violation("MISSING", "Candidate is required"));
    }

    List<Violation> violations = new ArrayList<>();
    if (!IS_ADULT.test(c)) {
        violations.add(new Violation("AGE", "Age must be at least 18"));
    }
    if (!IS_ACTIVE.test(c)) {
        violations.add(new Violation("ACTIVE", "Account must be active"));
    }
    if (!IS_VERIFIED.test(c)) {
        violations.add(new Violation("VERIFIED", "Account must be verified"));
    }
    if (!HAS_EMAIL.test(c)) {
        violations.add(new Violation("EMAIL", "Email is required"));
    }
    return List.copyOf(violations);
}
~~~

This is a method example, not a standalone class; it needs `Candidate` declared and appropriate imports. `List.copyOf` returns an unmodifiable List per contract and rejects null elements.

Do not use `and`/`or` with side effects just to accumulate all error messages: **short-circuiting** means some rules will not run, so you cannot expect to collect all errors. Separate fast boolean decisions with `Predicate` from a dedicated error-collection flow when business logic requires it.

## 13. Complete Java 17+ Program and Deterministic Stdout

Create file **`NamedPredicateDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;
import java.util.stream.Collectors;

public class NamedPredicateDemo {
    record Candidate(
            String id,
            int age,
            boolean active,
            boolean verified,
            String email) {}

    static final Predicate<Candidate> IS_NOT_NULL =
            Objects::nonNull;

    static final Predicate<Candidate> IS_ADULT =
            candidate -> candidate.age() >= 18;

    static final Predicate<Candidate> IS_ACTIVE =
            Candidate::active;

    static final Predicate<Candidate> IS_VERIFIED =
            Candidate::verified;

    static final Predicate<Candidate> HAS_EMAIL =
            candidate -> candidate.email() != null
                    && !candidate.email().isBlank();

    static final Predicate<Candidate> ELIGIBLE =
            IS_NOT_NULL
                    .and(IS_ADULT)
                    .and(IS_ACTIVE)
                    .and(IS_VERIFIED)
                    .and(HAS_EMAIL);

    static final Predicate<Candidate> BAD_STATUS =
            IS_NOT_NULL
                    .and(IS_ACTIVE.negate().or(IS_VERIFIED.negate()));

    static Predicate<Candidate> ageAtLeast(int age) {
        return candidate ->
                candidate != null && candidate.age() >= age;
    }

    public static void main(String[] args) {
        List<Candidate> candidates = Arrays.asList(
                new Candidate("A", 20, true, true, "a@example.test"),
                new Candidate("B", 17, true, true, "b@example.test"),
                new Candidate("C", 30, false, true, "c@example.test"),
                new Candidate("D", 21, true, false, "d@example.test"),
                new Candidate("E", 22, true, true, " "),
                new Candidate("F", 25, true, true, "f@example.test"),
                null);

        List<String> eligibleIds = candidates.stream()
                .filter(ELIGIBLE)
                .map(Candidate::id)
                .toList();

        List<String> rejectedIds = candidates.stream()
                .filter(IS_NOT_NULL.and(ELIGIBLE.negate()))
                .map(Candidate::id)
                .toList();

        List<String> badStatusIds = candidates.stream()
                .filter(BAD_STATUS)
                .map(Candidate::id)
                .toList();

        List<String> missingEmailIds = candidates.stream()
                .filter(IS_NOT_NULL.and(HAS_EMAIL.negate()))
                .map(Candidate::id)
                .toList();

        List<String> adultAt21 = candidates.stream()
                .filter(ageAtLeast(21))
                .map(Candidate::id)
                .toList();

        long adults = candidates.stream()
                .filter(IS_NOT_NULL.and(IS_ADULT))
                .count();

        List<String> nonBlank = List.of("Java", " ", "Stream", "")
                .stream()
                .filter(Predicate.not(String::isBlank))
                .toList();

        Predicate<String> isAdmin = Predicate.isEqual("admin");

        System.out.println("eligibleIds=" + eligibleIds);
        System.out.println("rejectedIds=" + rejectedIds);
        System.out.println("badStatusIds=" + badStatusIds);
        System.out.println("missingEmailIds=" + missingEmailIds);
        System.out.println("adultAt21=" + adultAt21);
        System.out.println("adultCount=" + adults);
        System.out.println("nullEligible=" + ELIGIBLE.test(null));
        System.out.println("adminMatch=" + isAdmin.test("admin"));
        System.out.println("otherMatch=" + isAdmin.test("guest"));
        System.out.println("nonBlank=" + nonBlank);
        System.out.println("anyEligible=" + candidates.stream()
                .anyMatch(ELIGIBLE));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac NamedPredicateDemo.java
java NamedPredicateDemo
~~~

**Deterministic stdout:**

~~~text
eligibleIds=[A, F]
rejectedIds=[B, C, D, E]
badStatusIds=[C, D]
missingEmailIds=[E]
adultAt21=[C, D, E, F]
adultCount=5
nullEligible=false
adminMatch=true
otherMatch=false
nonBlank=[Java, Stream]
anyEligible=true
~~~

Explanation:

1. `eligibleIds=[A, F]`: only A and F satisfy age, active, verified, and non-blank email.
2. `rejectedIds` excludes null from the report and takes elements failing `ELIGIBLE`; hence B, C, D, E.
3. `badStatusIds=[C, D]`: C is inactive, D is unverified. The null Candidate is excluded by `IS_NOT_NULL`.
4. `missingEmailIds=[E]`: E has an email containing only whitespace, not a non-blank email.
5. `adultAt21=[C, D, E, F]`: factory method creates a predicate for threshold 21, with built-in null guard.
6. `adultCount=5`: only B is under 18; null is excluded.
7. `nullEligible=false` proves `IS_NOT_NULL` at the start of the AND chain makes null evaluation safe.
8. `Predicate.isEqual("admin")` returns true for `"admin"` and false for `"guest"`.
9. `Predicate.not(String::isBlank)` removes empty or whitespace-only strings.
10. `anyEligible=true` because at least A or F matches the policy; `anyMatch` can stop early.

The program uses `Arrays.asList` to represent a list with a null element; unlike `List.of`, which does not accept null elements. All pipelines producing results traverse the source List sequentially, so the order of printed IDs is stable.

## 14. Common Mistakes

| Mistake | Why It Is Dangerous | How to Fix |
| --- | --- | --- |
| Putting all business logic in one overly long lambda | Hard to test and reuse | Split conditions into named Predicates |
| Assuming `and` and `or` always call both sides | They short-circuit | Do not put mandatory side effects on a side that may be skipped |
| Writing `IS_ADULT.and(IS_NOT_NULL)` and passing null | `IS_ADULT` runs first and can throw NPE | Use `IS_NOT_NULL.and(IS_ADULT)` |
| Writing `IS_NOT_NULL.or(IS_ADULT)` to guard null | On null, OR calls the right side and still fails | Use AND or define an explicit “allow null” policy |
| Calling `IS_ACTIVE.negate().test(null)` | `negate` does not add a null guard | Use `IS_NOT_NULL.and(IS_ACTIVE.negate())` |
| Negating all of `ELIGIBLE` and thinking null is excluded | `!false = true` so null can be kept | Combine `IS_NOT_NULL.and(ELIGIBLE.negate())` if selecting only existing records |
| Thinking `Predicate.not` exists in Java 8 | This static method was added in Java 11 | Use Java 11+ or a named predicate with `negate` |
| Thinking `Predicate.isEqual` uses reference comparison | `isEqual` checks equality via `equals` | Understand equals/null semantics |
| Naming `HAS_EMAIL` while expecting full email standard validation | It only checks for content | Name it to reflect the strength of the rule |
| Using `Predicate` to collect all validation errors | Booleans carry no reasons; short-circuit skips checks | Use a validation result with an error list |
| Capturing a mutable `List` and using the Predicate in parallel | State can change between runs, causing races | Snapshot/immutable values or proper synchronization |
| Using `removeIf` inside `stream().filter` on the same source | Interferes with the collection being traversed | Separate mutation phase from the Stream |
| Reusing a Stream after a terminal operation | A Stream can only be consumed once | Create a new pipeline from the source |
| Using a Predicate referencing mutable objects and assuming fixed results | Conditions can change as object state changes | Define ownership, immutability, and evaluation context |

## 15. Self-Check Questions and Answers

**Question 1.** Given `Predicate<Integer> positive = n -> n > 0` and `even = n -> n % 2 == 0`, what is `positive.and(even).test(-2)`?

**Answer:** `false`. `positive` is checked first and returns false, so `even` does not need to run.

**Question 2.** Does `positive.or(even).test(-2)` return true?

**Answer:** Yes. `positive(-2) == false`, but `even(-2) == true`.

**Question 3.** Why is `Objects::nonNull` usually placed at the start of `and` when the remaining rules access properties?

**Answer:** AND short-circuits. If the object is null, the first condition is false, and rules that would dereference the object do not run, avoiding `NullPointerException`.

**Question 4.** How do `ELIGIBLE.negate()` and `IS_NOT_NULL.and(ELIGIBLE.negate())` differ on null?

**Answer:** `ELIGIBLE.test(null)` is false, so negating the whole expression returns true. The second expression returns false because of the non-null check at the start.

**Question 5.** To filter non-blank strings using a method reference, what is the right way in Java 17?

**Answer:** `stream.filter(Predicate.not(String::isBlank))`, if inputs are non-null. If nulls may exist, filter `Objects::nonNull` first.

**Question 6.** When a policy needs an age threshold per campaign, should you declare a constant `IS_ADULT` or create `ageAtLeast(minimumAge)`?

**Answer:** A factory method `ageAtLeast(minimumAge)` allows configuring different thresholds per use; a constant only fits a fixed rule.

**Question 7.** If you only have `Predicate<Candidate>`, can you tell whether a candidate failed due to age or email?

**Answer:** No. A Predicate only returns a boolean; to record each reason, evaluate rules and build a validation result containing error codes/messages.

**Question 8.** What does `allMatch(policy)` return on an empty Stream? Is that enough to conclude “all registered candidates are valid”?

**Answer:** It returns true by vacuous truth. If business logic requires at least one candidate, also check that it is non-empty.

**Question 9.** `Predicate<String> isAdmin = Predicate.isEqual("admin")`; does `isAdmin.test(null)` throw `NullPointerException`?

**Answer:** No. It returns false; `Predicate.isEqual` handles null according to the API contract.

## 16. Key Takeaways

`Predicate<T>` represents a check of type `T -> boolean`. Naming Predicates makes **business rules clear, easy to test, and reusable**.

- Use `and` when **all** conditions must hold, `or` when **at least one** condition is needed, and `negate` or `Predicate.not` when negation is needed.
- `and`/`or` **short-circuit**; composition order affects null safety, exceptions, and side effects.
- Place `Objects::nonNull` before dereferencing predicates in an AND chain if input can be null.
- Think carefully about negation semantics: “invalid” may include null, whereas “existing object that is invalid” does not.
- Pass named predicates as arguments to `filter`, `anyMatch`, `allMatch`, `noneMatch`, and other APIs accepting a `Predicate`.
- Use **factory methods** to create parameterized rules, avoiding shared mutable state if parallel execution is desired.
- `Predicate` returns a boolean and does not replace a multi-error validation model; separate error collection into an explicit mechanism.
- Always test boundary cases, nulls, individual rules, and composed policies.

When a policy has many conditions, an expression like `IS_NOT_NULL.and(IS_ADULT).and(IS_ACTIVE).and(IS_VERIFIED).and(HAS_EMAIL)` is usually much more maintainable than a long lambda, provided each rule is accurately named and adheres to the same data contract.
