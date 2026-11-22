# Predicate.and(), or(), negate(), and Short-Circuit Evaluation in Java

## 1. Why compose Predicates?

In Java, **java.util.function.Predicate<T>** is a functional interface representing a condition on a value of type T. Its single abstract method (SAM) is **boolean test(T value)**. Because it has one SAM, we can construct a Predicate using a lambda or method reference.

A business rule often has more than one condition. For example, an order qualifies for free shipping when it is **paid**, **domestic**, and **meets the amount threshold**. If written all in one expression, the logic can become long and hard to test. We can separate each condition into an independent Predicate and compose them:

~~~java
Predicate<Order> paid = Order::paid;
Predicate<Order> domestic = Order::domestic;
Predicate<Order> minimum = order -> order.totalCents() >= 100_000L;

Predicate<Order> eligible = paid.and(domestic).and(minimum);
~~~

This is an **illustrative snippet**, assuming the Order type has the corresponding methods and java.util.function.Predicate has been imported. When using **eligible.test(order)**, Java evaluates the Predicates in order and applies logical AND.

The three methods **and()**, **or()**, and **negate()** are Predicate composition operations provided by Java as **default methods**:

- **p.and(q)** creates a Predicate meaning **p(x) && q(x)**.
- **p.or(q)** creates a Predicate meaning **p(x) || q(x)**.
- **p.negate()** creates a Predicate meaning **!p(x)**.

These operations return **a new Predicate** representing the composition. Creating a composed Predicate **does not call test()**, does not filter data immediately, and does not require an input value at creation time. The boolean result only appears when **test(value)** is executed or when an API like Stream.filter needs to evaluate the condition.

## 2. Understanding the contract of the three methods

Usage pattern:

~~~java
Predicate<T> combinedAnd = p.and(q);
Predicate<T> combinedOr = p.or(q);
Predicate<T> opposite = p.negate();
~~~

The variables p and q here are already-initialized Predicate<T> instances; the snippet above only illustrates the API, not a standalone program.

| Composition | Condition for returning true | Condition for returning false | Call order |
| --- | --- | --- | --- |
| **p.and(q)** | Both p(x) and q(x) are true | Either one is false | Calls p first; only calls q if p is true |
| **p.or(q)** | At least one of the two is true | Both are false | Calls p first; only calls q if p is false |
| **p.negate()** | p(x) is false | p(x) is true | Calls p once then negates the boolean |

**and() and or() use short-circuit evaluation**, just like Java's **&&** and **||** operators. That affects not only the boolean result, but also null checks, computation cost, exceptions, and side effects.

**negate() has no right-hand side to skip**: it calls the original Predicate and negates the result. When the original Predicate throws an exception, negate does not turn the exception into false/true; the exception still propagates outward.

### 2.1. Truth table

| p(x) | q(x) | p.and(q) | p.or(q) | p.negate() |
| --- | --- | --- | --- | --- |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

The table shows pure logical results. **It does not say that q is always called.** In the row p=false for AND, q is not evaluated at all; in the row p=true for OR, q is also not evaluated.

## 3. Short-circuit evaluation of and(): stopping when the first condition is false

Suppose we want to check that a string is non-null, non-blank, and starts with the letter J:

~~~java
Predicate<String> notNull = text -> text != null;
Predicate<String> notBlank = text -> !text.isBlank();
Predicate<String> startsWithJ = text -> text.startsWith("J");

Predicate<String> valid = notNull.and(notBlank).and(startsWithJ);
~~~

This is an illustrative snippet requiring Predicate to be imported. If we run **valid.test(null)**:

1. **notNull.test(null)** returns false.
2. Because the left result of **and** is false, Java **does not call notBlank**.
3. The outer composition also receives false and **does not call startsWithJ**.
4. The final result is false, with no NullPointerException from isBlank() or startsWith().

**Order matters very much.** If we write **notBlank.and(notNull)** and pass null, **notBlank.test(null)** will call **null.isBlank()** and throw NullPointerException *before* reaching the null check. Therefore, cheap and critical preconditions like **x != null** should usually be placed at the start of an AND chain.

In general logic:

~~~text
p.and(q).test(x)

evaluate p(x)
  ├─ false → return false immediately; do not call q(x)
  └─ true  → evaluate q(x), return result of q(x)
~~~

This avoids unnecessary work. For example, basic state can be checked before performing an expensive lookup. However, placing a rule with side effects in a position where it can be skipped must be weighed against the business contract.

## 4. Short-circuit evaluation of or(): stopping when the first condition is true

Given a condition where a customer gets priority if they belong to the VIP group **or** hold a voucher:

~~~java
Predicate<Customer> vip = Customer::vip;
Predicate<Customer> hasVoucher = Customer::hasVoucher;

Predicate<Customer> priority = vip.or(hasVoucher);
~~~

This is an illustrative snippet assuming a Customer type and corresponding accessors exist.

If **vip.test(customer)** returns true, the entire **priority.test(customer)** returns true and **hasVoucher.test(customer)** is not called. Only if vip is false does Java check the voucher condition.

~~~text
p.or(q).test(x)

evaluate p(x)
  ├─ true  → return true immediately; do not call q(x)
  └─ false → evaluate q(x), return result of q(x)
~~~

When both rules only read data and have no side effects, short-circuiting usually brings performance benefits. But if the second rule must always run to write an audit log, update state, or throw a mandatory error, **or() is not the right tool**: the second rule might not run.

**Note on distinction:** The binary operators **|** and **&** on booleans in Java can evaluate both sides, whereas **||** and **&&** are short-circuiting. Predicate.or() and Predicate.and() follow short-circuit semantics; there is no corresponding Predicate method to force both rules to always run.

## 5. negate(): negating a rule

**p.negate()** is used to express "does not satisfy p":

~~~java
Predicate<String> blank = String::isBlank;
Predicate<String> notBlank = blank.negate();
~~~

Illustrative snippet requiring Predicate imported; **notBlank.test("Java")** returns true, while **notBlank.test("   ")** returns false.

However, **blank.test(null)** calls the instance method **isBlank()** on null and throws NullPointerException. Consequently, **notBlank.test(null)** also throws an error. **negate() only flips the boolean result when test() returns normally; it does not turn an exception into true.**

To handle null proactively, we must clarify the semantics:

~~~java
Predicate<String> present = text ->
        text != null && !text.isBlank();

Predicate<String> absent = present.negate();
~~~

Now **present.test(null)** returns false and **absent.test(null)** returns true. This is **a business choice**: null is treated as "absent". If null is invalid data that must be rejected, explicitly check and throw an exception instead of silently treating null as false.

### 5.1. Predicate.not(...) since Java 11

Java also provides the static method **Predicate.not(Predicate<T>)**, making it convenient to write negation where a Predicate needs to be passed into an API accepting a callback:

~~~java
List<String> result = List.of("A", "", "B")
        .stream()
        .filter(Predicate.not(String::isBlank))
        .toList();
~~~

This is an illustrative snippet requiring **java.util.List** and **java.util.function.Predicate** to be imported. The result is **["A", "B"]** in encounter order. **Predicate.not(...)** and **p.negate()** both express negation, but the syntax differs: one is a static factory taking a Predicate, the other is a default method on an existing Predicate.

**Predicate.not(null)** will throw NullPointerException per the non-null parameter requirement, rather than creating an "always true" Predicate. For a null input entering the lambda **String::isBlank**, an evaluation error can still occur if there is no prior rule filtering out null.

## 6. Complete Java 17 example: combining string filters

Create **PredicateBasicsDemo.java**:

~~~java
import java.util.function.Predicate;

public class PredicateBasicsDemo {
    public static void main(String[] args) {
        Predicate<String> notBlank =
                text -> text != null && !text.isBlank();

        Predicate<String> startsWithJ =
                text -> text != null && text.startsWith("J");

        Predicate<String> atMostFiveChars =
                text -> text != null && text.length() <= 5;

        Predicate<String> accepted =
                notBlank.and(startsWithJ).and(atMostFiveChars);

        Predicate<String> exciting =
                startsWithJ.or(text ->
                        text != null && text.endsWith("!"));

        Predicate<String> notStartingWithJ =
                startsWithJ.negate();

        System.out.println("Java: " + accepted.test("Java"));
        System.out.println("JavaScript: "
                + accepted.test("JavaScript"));
        System.out.println("Kotlin: " + accepted.test("Kotlin"));
        System.out.println("null: " + accepted.test(null));
        System.out.println("Exciting: " + exciting.test("Hi!"));
        System.out.println("Not J: "
                + notStartingWithJ.test("Kotlin"));
        System.out.println("Not J null: "
                + notStartingWithJ.test(null));
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 PredicateBasicsDemo.java
java PredicateBasicsDemo
~~~

Stdout:

~~~text
Java: true
JavaScript: false
Kotlin: false
null: false
Exciting: true
Not J: true
Not J null: true
~~~

**Analysis:**

- **Java** is not blank, starts with J, and has four characters, so it is accepted.
- **JavaScript** satisfies the first two conditions but exceeds five characters.
- **Kotlin** is stopped at **startsWithJ**, so length does not need to be checked.
- **null** is stopped immediately at notBlank; the Predicate was written null-safe so it does not throw an error.
- **Hi!** does not start with J but ends with **!**, so the OR returns true.
- **notStartingWithJ** is the negation of a Predicate designed to return false on null; therefore it returns true on null. This result is **not a "valid string" contract** — it is only accurate to the logical meaning of negation.

The example emphasizes that **negating a condition is not synonymous with input validity**. If the application needs "does not start with J but still non-null", use **notBlank.and(startsWithJ.negate())** or a Predicate with the corresponding contract.

## 7. Observing exact call order and skipped branches

An effective way to learn short-circuiting is to attach logging to Predicates to observe. This technique is only for **demos or diagnostics**; in production code, using pure Predicates (without side effects) is safer and easier to test.

Create **PredicateShortCircuitDemo.java**:

~~~java
import java.util.function.Predicate;

public class PredicateShortCircuitDemo {
    public static void main(String[] args) {
        Predicate<String> longEnough = text -> {
            System.out.println("length: " + text);
            return text.length() > 3;
        };

        Predicate<String> startsWithJ = text -> {
            System.out.println("starts: " + text);
            return text.startsWith("J");
        };

        Predicate<String> endsWithA = text -> {
            System.out.println("ends: " + text);
            return text.endsWith("a");
        };

        Predicate<String> all =
                longEnough.and(startsWithJ).and(endsWithA);

        System.out.println("AND Java:");
        System.out.println("result: " + all.test("Java"));

        System.out.println("AND Jo:");
        System.out.println("result: " + all.test("Jo"));

        Predicate<String> either =
                startsWithJ.or(endsWithA);

        System.out.println("OR Java:");
        System.out.println("result: " + either.test("Java"));

        System.out.println("OR Luna:");
        System.out.println("result: " + either.test("Luna"));

        System.out.println("NEGATE Jo:");
        System.out.println("result: "
                + longEnough.negate().test("Jo"));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 PredicateShortCircuitDemo.java
java PredicateShortCircuitDemo
~~~

Exact stdout:

~~~text
AND Java:
length: Java
starts: Java
ends: Java
result: true
AND Jo:
length: Jo
result: false
OR Java:
starts: Java
result: true
OR Luna:
starts: Luna
ends: Luna
result: true
NEGATE Jo:
length: Jo
result: true
~~~

Observations:

1. For **all.test("Java")**, all three Predicates run in order and all return true.
2. For **all.test("Jo")**, the length condition returns false, so **startsWithJ** and **endsWithA** do not run.
3. For **either.test("Java")**, the first condition is true so **endsWithA** is not called.
4. For **either.test("Luna")**, the first condition is false so the second condition runs and returns true.
5. For **longEnough.negate().test("Jo")**, only longEnough runs once; its false result is negated to true.

In this program null is not passed because **longEnough**, **startsWithJ**, and **endsWithA** intentionally have no null guard. To support null, place a null-checking Predicate at the start of the AND or write each Predicate to be null-safe; do not rely on logs to guarantee safety.

## 8. Composition order, grouping expressions, and precedence

Like booleans in Java, parenthesization affects meaning.

~~~java
Predicate<T> rule1 = p.and(q.or(r));
Predicate<T> rule2 = p.and(q).or(r);
~~~

These are **illustrative expressions**, with p, q, r being valid Predicate<T> instances.

The two corresponding rules:

~~~text
rule1(x) = p(x) && (q(x) || r(x))
rule2(x) = (p(x) && q(x)) || r(x)
~~~

They are **not equivalent**. If p is false and r is true, rule1 is false, while rule2 is true. When translating a business expression with multiple AND/ORs, make the grouping intent explicit rather than just chaining methods for the shortest code.

**Dot-chained calls associate according to method syntax.** The expression **p.and(q).or(r)** is parsed as **(p.and(q)).or(r)**; do not apply **&&** and **||** operator precedence rules to reinterpret it differently.

### 8.1. De Morgan's Laws

If Predicates are viewed as pure boolean conditions:

~~~text
!(p && q) = (!p || !q)
!(p || q) = (!p && !q)
~~~

In Java, this can be expressed as:

~~~java
Predicate<T> notBoth = p.and(q).negate();
Predicate<T> eitherNot = p.negate().or(q.negate());

Predicate<T> neither = p.or(q).negate();
Predicate<T> bothNot = p.negate().and(q.negate());
~~~

This is an illustrative snippet with p and q of type Predicate<T>. The four Predicates describe two pairs of logically equivalent boolean values when tests return normally.

**Caution:** Equivalence in boolean results does not always guarantee the same cost, logs, or outcomes in systems **with side effects, mutable state, or time dependence**. Even if rewriting preserves logic, do not freely reorder Predicates that perform I/O, write data, or depend on the clock.

### 8.2. Can p and q be swapped?

In pure boolean logic, **p && q = q && p**, **p || q = q || p**. But the call order in Java changes:

- **p.and(q)** calls p first; **q.and(p)** calls q first.
- **p.or(q)** calls p first; **q.or(p)** calls q first.

If p checks for null while q dereferences the parameter, swapping them can turn a false return into a NullPointerException. If p is cheap and q is expensive, order also affects performance. If a Predicate has side effects, changing the order can change behavior beyond the boolean result.

**Practical rule:** place preconditions and cheap, pure conditions that can filter out data in sensible positions; more importantly, preserve the **business contract and intentional ordering**.

## 9. Combining Predicate with Stream.filter()

**Stream.filter(Predicate<? super T>)** takes a Predicate and keeps elements whose test returns true. Composition lets you name a rule once and reuse it across multiple pipelines.

Create **OrderRuleDemo.java**:

~~~java
import java.util.List;
import java.util.function.Predicate;

record Order(String id, long totalCents,
             boolean paid, boolean domestic) {}

public class OrderRuleDemo {
    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 150_000L, true, true),
                new Order("B", 160_000L, false, true),
                new Order("C", 90_000L, true, true),
                new Order("D", 120_000L, true, false),
                new Order("E", 200_000L, true, true)
        );

        Predicate<Order> paid = Order::paid;
        Predicate<Order> domestic = Order::domestic;
        Predicate<Order> minimum =
                o -> o.totalCents() >= 100_000L;

        Predicate<Order> freeShipping =
                paid.and(domestic).and(minimum);

        Predicate<Order> manualReview =
                paid.negate().or(domestic.negate());

        List<String> eligibleIds = orders.stream()
                .filter(freeShipping)
                .map(Order::id)
                .toList();

        List<String> reviewIds = orders.stream()
                .filter(manualReview)
                .map(Order::id)
                .toList();

        System.out.println("Eligible: " + eligibleIds);
        System.out.println("Review: " + reviewIds);
        System.out.println("Count: " + eligibleIds.size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 OrderRuleDemo.java
java OrderRuleDemo
~~~

Stdout:

~~~text
Eligible: [A, E]
Review: [B, D]
Count: 2
~~~

**Explanation:**

- **A** and **E** are both paid, domestic, and meet the amount threshold, so they qualify.
- **B** is unpaid; **C** does not meet the threshold; **D** is not domestic.
- **manualReview** in the example means **unpaid or non-domestic**. Therefore B and D belong to the Review list; C is not put into Review per the defined rule. This is an illustrative classification, not an assertion of actual shipping policy.
- **Record Order** keeps sample data concise and provides accessors with the same component names, so **Order::paid**, **Order::domestic**, and **Order::id** have matching signatures.

### 9.1. Two different layers of "laziness"

**Predicate composition** happens when writing **paid.and(domestic)**, but the tests have not run yet. When calling **orders.stream().filter(freeShipping)**, the Stream only builds a **pipeline**; the filter operation is still an *intermediate operation* and has not traversed the data.

Only when a **terminal operation** (such as **toList**, **count**, **anyMatch**, **findFirst**) is called are elements processed to produce a result. When processing each element, the composed Predicate inside applies and/or short-circuiting.

Two mechanisms to distinguish:

1. **Stream laziness:** the pipeline does not execute before a terminal operation; some terminal operations also short-circuit across the entire stream.
2. **Predicate short-circuit:** for **a single element being tested**, the right-hand side of AND or OR may be skipped.

For example, **stream().filter(rule).findFirst()** may not need to traverse elements after the first element satisfying rule. Even for the element under test, **rule = p.and(q)** may not call q if p is false. However, do not rely on the count/schedule of side effects in a Stream pipeline as a contract, especially when using parallel streams or modifying the pipeline.

### 9.2. Multiple filters are not always operationally equivalent

The following two forms usually give the **same result set** if the Predicates are pure and stable:

~~~java
stream.filter(p).filter(q)
stream.filter(p.and(q))
~~~

These are **illustrative pipeline expressions**, assuming stream, p, and q have compatible types. In a typical sequential chain, both keep only elements satisfying both conditions, and elements rejected by p do not need q evaluated.

However, merging them is **no reason** to assume all side effects, exception timing, evaluation counts, or parallel behavior have identical guarantees across all pipelines. For business rules, aim for **pure, stateless, order-independent Predicates**.

## 10. Exceptions, null, and expensive conditions

### 10.1. Exceptions in skipped branches

If p is false in **p.and(q)**, q does not run, so an exception that would have been thrown by q does not occur during that test. Similarly, if p is true in **p.or(q)**, q does not run.

Example:

~~~java
Predicate<String> safe = s -> s != null;
Predicate<String> needsText = s -> s.length() > 3;

System.out.println(safe.and(needsText).test(null)); // false
~~~

This is an illustrative snippet requiring Predicate imported. If changed to **needsText.and(safe)**, evaluating null throws NullPointerException. Short-circuiting helps build guards, but only when written in the right order.

### 10.2. Null as the argument to and/or

The **other** argument of **p.and(other)** and **p.or(other)** must be a valid Predicate, not null. Per the API contract, passing **null** as other causes **NullPointerException immediately when calling and/or to create the composed Predicate**, without waiting for **test()**:

~~~java
Predicate<String> p = s -> s.length() > 2;
// p.and(null)  → throws NullPointerException.
// p.or(null)   → throws NullPointerException.
~~~

This is an illustrative snippet and two comment lines indicating behavior; do not put these two failing calls into normal code. Additionally, calling **p.negate()** also requires the variable p itself to be a valid Predicate object; you cannot call a method on p=null.

Clearly distinguish **null as other** (error during composition) and **null as input to test** (behavior decided by the Predicate).

### 10.3. Side effects should not be the main purpose of a Predicate

A Predicate can technically query a database, send logs, or mutate objects. But **and/or can skip a branch**, and Streams can execute lazily or in parallel. If every operation must run, separate the **action** part from the **decision** part:

- Use Predicate to check conditions and return a boolean.
- Use Consumer or a service method for tasks with mandatory side effects.
- If mandatory auditing is needed, design it at the application boundary and clearly define when it executes.

A pure Predicate is generally easier to unit test, easier to reuse, easier to compose, and safer to put into a Stream.

### 10.4. Mutable state and multithreading

If a Predicate reads mutable fields or depends on concurrently updated data, results can differ between test calls. **p.negate().negate()** represents double negation logically, but if p is unstable due to external state, do not assume two separate evaluations will always observe the same data.

A lambda capturing a local variable must follow the final/effectively final rule, but **the object** that variable points to can still be mutable. Using a Predicate in a parallel stream does not make reading/writing shared state automatically safe; avoid shared mutable state or apply proper synchronization.

## 11. Testing both logic and evaluation counts

When testing a composition, separate two questions:

1. **Is the boolean right?** Check the truth table and business boundaries.
2. **Are only the expected branches executed?** Check short-circuiting when it is part of the contract, especially with null-guard conditions or avoiding expensive computations.

Example of testing with a counter, inside a method with Predicate and AtomicInteger imported:

~~~java
AtomicInteger rightCalls = new AtomicInteger();

Predicate<String> leftFalse = text -> false;
Predicate<String> right = text -> {
    rightCalls.incrementAndGet();
    return true;
};

boolean result = leftFalse.and(right).test("value");

System.out.println(result);           // false
System.out.println(rightCalls.get()); // 0
~~~

This is a **non-standalone illustrative snippet**. It shows that q is not called when p is false in AND. To test OR, replace **leftFalse** with a Predicate that always returns true and use **leftTrue.or(right)**; the call count for right must also be 0.

In real unit tests, you can assert the result and counter directly, while also separating tests for **null**, **exceptions**, **boundary thresholds**, and **one branch true/false**. Do not make all logic depend on logs to distinguish rules; logging here is only an observation technique.

### 11.1. Case table for business conditions

For the free shipping example:

| Paid | Domestic | Meets threshold | freeShipping |
| --- | --- | --- | --- |
| true | true | true | true |
| false | true | true | false |
| true | false | true | false |
| true | true | false | false |
| false | false | false | false |

Beyond the logic table, test **exactly at the threshold**, **one unit below the threshold**, **null** (if the model allows it), and invalid data. In particular, a boolean Predicate does not describe why a condition failed; if the business needs rejection reasons, design a rich result or run a structured validation process instead of relying solely on and/or.

## 12. Common mistakes when composing Predicates

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| Assuming and/or calls both branches | Wrong call count, missing audit/side effect | Remember short-circuit rules, separate mandatory side effects |
| Using p.and(q) but putting the null guard in q | p can throw before the guard | Put the null guard first or write null-safe rules |
| Thinking negate() turns an exception into true | Exception still propagates; no boolean to negate | Handle errors per contract, do not use negate to hide errors |
| Confusing p.and(q).or(r) with p.and(q.or(r)) | Business condition changes | Write explicit groupings, add combination tests |
| Swapping p and q thinking it has no effect | Can change NPEs, side effects, cost | Keep intentional order and use pure rules |
| Passing null to and(null)/or(null) | NPE immediately upon composition | Validate rules before composing |
| Assuming filter runs immediately when declaring a Stream | No terminal operation yet | Distinguish pipeline creation and pipeline execution |
| Assuming negating p means valid input | If p is false on null, p.negate may be true on null | Combine with a validity guard |
| Using a Predicate that reads/writes shared mutable state in a parallel stream | Unstable results and data races | Use immutable/snapshot state or proper synchronization |
| Trying to compress every complex policy into a boolean | Loses reason info and priority levels | Use a structured business result if needed |

## 13. Checklist for real programs

Before using **Predicate.and()**, **or()**, **negate()**:

1. Identify what each Predicate means when returning true; name them like **isPaid**, **hasValidAddress**, **isEligible** instead of vague names.
2. Decide **whether null is accepted or not** and place guards in the right order.
3. Group AND/OR according to policy; do not rely on intuition about dots to misread parentheses.
4. Confirm which conditions may be skipped: in AND, q is skipped if p is false; in OR, q is skipped if p is true.
5. If there are high-cost checks, consider condition order without sacrificing business meaning.
6. Control exceptions and side effects: a Predicate should describe a decision, not implicitly take on mandatory actions.
7. With Streams, distinguish **pipeline initialization** and **terminal operation execution**; avoid treating logs/side effects as API guarantees.
8. Test truth tables, boundary data, null, exceptions, and cases requiring short-circuiting.

## 14. Practice exercises

### Exercise 1: Predict which branches are called

Suppose p returns false and q logs before returning true. For **p.and(q)** and **p.or(q)**, does q run? What is the boolean result of each expression?

**Answer:** With AND, q does not run and the result is false. With OR, q runs and the result is true.

### Exercise 2: Negating a null-safe rule

Given **nonBlank = s -> s != null && !s.isBlank()**. What does **nonBlank.negate().test(null)** return? If you want "valid string that is blank", how should the rule be redesigned?

**Hint:** Negating nonBlank returns true for null. If null must be rejected, add a non-null checking Predicate to the target rule.

### Exercise 3: Find the logic bug in grouping order

Compare:

~~~java
Predicate<Order> first = paid.and(domestic.or(priority));
Predicate<Order> second = paid.and(domestic).or(priority);
~~~

This is an illustrative snippet with previously defined Predicates. If an order is unpaid but priority=true, do first and second give the same result? Write the truth table for the three conditions.

**Answer:** No. first is false because paid is false; second is true because of the priority branch of OR.

### Exercise 4: Testing Stream laziness and short-circuiting

Create a List containing 5 strings, use **filter(notBlank.and(startsWithJ))** then **findFirst()**. Attach counters to each Predicate to observe which data items are checked and which branches are skipped. Then replace findFirst() with toList() and compare evaluation counts in the sequential pipeline.

### Exercise 5: Business design requiring rejection reasons

Suppose an application can be rejected for missing documents, being past the deadline, or invalid data. Explain when **Predicate.and()** is sufficient to represent a boolean condition, and when a result type like **Decision(boolean accepted, List<String> reasons)** or another suitable structure should be used to store reasons.

## 15. Takeaways

**Predicate.and()** is short-circuiting AND, **Predicate.or()** is short-circuiting OR, and **Predicate.negate()** negates the result of the original Predicate. Compositions produce a **new Predicate**; they do not run tests when declared.

Correct logical results are a necessary condition, but writing reliable Java also requires understanding **evaluation order, skipped branches, null contracts, exceptions, side effects, grouping, and Stream laziness**. Keeping each rule small, clear in meaning, side-effect-free, and independently tested makes composed logic easier to read and maintain.
