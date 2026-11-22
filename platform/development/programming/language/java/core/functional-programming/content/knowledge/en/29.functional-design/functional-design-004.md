# Passing Behavior Instead of Creating Many Classes Differing by One Operation in Java

## 1. The Problem: Same Workflow, Only One Step Varies

In object-oriented programming, a common way to vary an algorithm is to define an interface and write multiple implementing classes. This makes sense when each handler has its own state, configuration, lifecycle, and multiple responsibilities. However, when many classes **differ only by a single short calculation or condition**, the number of classes can grow rapidly without adding much value.

For example, a total-payment calculation feature has fixed steps:

1. Receive the order.
2. Validate the input data.
3. Calculate the shipping fee according to the active policy.
4. Add the item price and the fee.
5. Return the result.

Across these five steps, only **step 3** varies. We could create `FlatFeePolicy`, `PriorityFeePolicy`, `FreeFromThresholdPolicy`, `HolidayPolicy`, and so on, but if each class only has a one-line method, creating a file for each variant can bloat the codebase, hurt readability, and increase maintenance cost.

The solution is **passing behavior as a value**: the method handling the shared workflow takes an extra parameter carrying the behavior of the varying step. In Java, this behavior is typically represented by a **functional interface**, lambda, or method reference.

```text
Before:  Class A handles flow + rule 1
         Class B handles flow + rule 2
         Class C handles flow + rule 3

After:   One shared flow
                  |
           Policy parameter
               /    |    \
          lambda A lambda B method reference C
```

**The goal is not to eliminate all classes.** The goal is to keep the shared workflow in one place, isolate the varying part into a small contract, and let the caller choose the appropriate behavior at the call site.

## 2. From the Strategy Pattern to Passing Functions

This idea is closely related to the **Strategy Pattern**: encapsulate an interchangeable algorithm, then pass that algorithm to where it is used.

### Traditional Implementing Classes

Suppose we define:

```java
@FunctionalInterface
interface FeePolicy {
    int fee(Order order);
}
```

This is a **type-definition snippet**; an `Order` type is needed in the same context. We can write:

```java
final class FlatFee implements FeePolicy {
    @Override
    public int fee(Order order) {
        return 20;
    }
}

final class PriorityFee implements FeePolicy {
    @Override
    public int fee(Order order) {
        return order.priority() ? 50 : 20;
    }
}
```

Two classes make sense when we want named strategies registered in a dependency injection system, or when they have state or multiple configurations. However, if they are just two tiny calculations like above, the caller can supply lambdas without **being forced to create two separate classes**.

### Replacing with Lambdas

```java
FeePolicy flat = order -> 20;
FeePolicy priority = order -> order.priority() ? 50 : 20;
```

These two lines are illustrative inside a method where `FeePolicy` and `Order` are defined. The lambda implements the single abstract method of the functional interface: `fee(Order)`.

`FeePolicy` is still an **interface type**—only the way of providing the implementation object changes. Do not mistake “passing a function” for Java dropping its type system or allowing arbitrary code blocks to be passed without a target type.

## 3. Conditions for Behavior to Be Passed as a Lambda

A functional interface has **exactly one abstract method** under Java rules (excluding methods matching public methods of `Object`); it may also have `default` or `static` methods.

Example:

```java
@FunctionalInterface
interface FeePolicy {
    int fee(Order order);
}
```

The `@FunctionalInterface` annotation is not required to use lambdas, but it lets the compiler check intent and report an error if the interface accidentally loses its functional nature.

When writing:

```java
FeePolicy rule = order -> 20;
```

Java uses the target type `FeePolicy` to infer that `order` has type `Order` and the body returns `int`. For method references, the compiler also needs a target type:

```java
FeePolicy rule = BehaviorInjectionDemo::flatFee;
```

This is a snippet from the full runnable program in Section 8, where `flatFee(Order)` is a `static` method.

Choose interface names that express **domain meaning** when worthwhile: `FeePolicy`, `RetryDecision`, `EligibilityRule` are clearer than `Function<Order,Integer>` in an API with many similar behaviors. Conversely, there is no need to define a new interface when `Predicate<T>`, `Function<T,R>`, or `Comparator<T>` already describes it clearly enough.

## 4. Designing Functions That Accept Behavior: Fix the Skeleton, Open One Variation Point

Example `QuoteService` accepting `FeePolicy` instead of deciding the fee itself:

```java
static final class QuoteService {
    int total(Order order, FeePolicy policy) {
        Objects.requireNonNull(order);
        Objects.requireNonNull(policy);
        if (order.amount() < 0) {
            throw new IllegalArgumentException("amount");
        }
        int fee = policy.fee(order);
        if (fee < 0) {
            throw new IllegalArgumentException("fee");
        }
        return Math.addExact(order.amount(), fee);
    }
}
```

This is a snippet from the full program; it requires `import java.util.Objects`, as well as `Order` and `FeePolicy` declarations.

The shared part stays intact:

- **Input validation** before applying the policy.
- **Calling the exact variation point** via `policy.fee(order)`.
- **Checking the behavior result's contract** (non-negative fee).
- **Overflow-checked addition** using `Math.addExact` in this small-integer example.

Now callers can swap policies without modifying `QuoteService`:

```java
FeePolicy flat = order -> 20;
FeePolicy priority = order -> order.priority() ? 50 : 20;

int normal = service.total(order, flat);
int rush = service.total(order, priority);
```

These statements are **illustrative only** with appropriate `service` and `order` variables. Each call selects an implementation of the same interface.

Passing behavior as an argument is often called **behavioral parameterization** or **strategy injection**. This applies the principle of extending functionality via parameters, rather than duplicating orchestration just because one rule changes.

## 5. Comparing “Before” and “After” Refactoring

| Perspective | Multiple Classes for Small Variants | One Shared Function Accepting Behavior |
| --- | --- | --- |
| Where shared flow lives | Risk of duplication across classes or subclasses | Centralized in one service/function |
| Adding a new policy | May require creating a new class and wiring/config | Pass a lambda, reference, or class when truly needed |
| Testing the shared flow | Easy to duplicate tests per class | Use a fake/stub policy in service tests |
| Readability at call site | `new FlatFee()`, `new PriorityFee()` | `order -> ...`, method reference, named policy |
| Complex state/config | Dedicated class is often clearer and easier to manage lifecycle | Lambda captures can become hard to follow if overly complex |
| Extending multiple methods | Interface/class may be appropriate | A lambda only represents one SAM |
| Ordering and side effects | Depends on implementation | Still depends on implementation; lambdas do not make behavior pure automatically |

**Do not eliminate a class just because it is short** if the class name carries important domain meaning or needs independent configuration/observability. Refactoring is worthwhile when it reduces **unnecessary variant duplication** and clarifies the shared part.

One sign of “class explosion”: a bunch of classes all implementing the same interface, having no significant fields, overriding one method with a few lines, and instantiated on the spot to pass into a service. In that case, consider lambdas, method references, or factories returning functional interfaces.

## 6. Common Behavior Types Built into Java

Before creating a new interface, check `java.util.function` and `java.util.Comparator`:

| Interface | SAM | Common Meaning | Example |
| --- | --- | --- | --- |
| `Predicate<T>` | `boolean test(T)` | Condition / selection rule | `order -> order.amount() > 0` |
| `Function<T,R>` | `R apply(T)` | Data transformation | `Candidate::name` |
| `Consumer<T>` | `void accept(T)` | Action receiving data | `log::add` |
| `Supplier<T>` | `T get()` | Supplies or creates a value when called | `() -> new ArrayList<>()` |
| `UnaryOperator<T>` | `T apply(T)` | Same-type transformation | `String::trim` |
| `BiFunction<T,U,R>` | `R apply(T,U)` | Two-argument function | `(a,b) -> a+b` |
| `Comparator<T>` | `int compare(T,T)` | Comparison / sorting rule | `Comparator.comparing(Candidate::name)` |
| `Runnable` | `void run()` | Action with no input/output | `() -> refresh()` |

The examples in the table are **illustrative expressions**; some require corresponding variable/type declarations (`log`, `Candidate`, `refresh`). `Comparator` is in `java.util`; the other interfaces are mainly in `java.util.function`, and `Runnable` is in `java.lang`.

Do not use `Consumer<T>` just because a method is short if the logic actually needs to **return a value**. When the contract requires a result, use `Function<T,R>` or an interface with an appropriate return type. When only checking a condition, `Predicate<T>` communicates intent more accurately than `Function<T,Boolean>`.

In high-frequency code operating on primitives, specialized interfaces like `IntPredicate`, `IntUnaryOperator`, and `ToIntFunction<T>` can avoid boxing; optimize only after understanding semantics and measuring when needed.

## 7. Key Point: Behavior Parameters Are Part of the API Contract

If a method accepts multiple behavior parameters, each parameter must have a **clear role**:

```java
static List<String> select(
        List<Candidate> source,
        Predicate<? super Candidate> rule,
        Function<? super Candidate, String> format,
        Comparator<? super String> order) {
    return source.stream()
            .filter(rule)
            .map(format)
            .sorted(order)
            .toList();
}
```

This is a **method inside the class** of the full program in Section 9, not a standalone file. Each argument has a job:

1. `source`: source data.
2. `rule`: decides which elements are kept.
3. `format`: converts an element to a string.
4. `order`: rule for comparing result strings.

The result is **one shared workflow**, yet callers can swap the condition, representation, and sorting without creating `ActiveCandidateSelector`, `ExcellentCandidateSelector`, `ReverseCandidateSelector` classes for each combination.

`? super Candidate` allows predicates/functions to accept `Candidate` or an appropriate supertype; `Comparator<? super String>` allows comparators to accept `String` or an appropriate supertype. This is generic flexibility of Java APIs, not unsafe casting.

**Do not pass too many lambdas when they make the function hard to read**: if there are 7–10 hard-to-distinguish policies, group them into a named configuration object, a clear domain service, or a few specialized policy types. Parameterization is only helpful when the interface remains easy to understand.

## 8. Standalone Java 17 Program: Strategy Classes and Lambdas Sharing One Service

Create file `BehaviorInjectionDemo.java`:

```java
import java.util.List;
import java.util.Objects;

public class BehaviorInjectionDemo {
    record Order(String code, int amount, boolean priority) {}

    @FunctionalInterface
    interface FeePolicy {
        int fee(Order order);
    }

    static final class FlatFee implements FeePolicy {
        @Override
        public int fee(Order order) {
            return 20;
        }
    }

    static final class PriorityFee implements FeePolicy {
        @Override
        public int fee(Order order) {
            return order.priority() ? 50 : 20;
        }
    }

    static final class QuoteService {
        int total(Order order, FeePolicy policy) {
            Objects.requireNonNull(order);
            Objects.requireNonNull(policy);
            if (order.amount() < 0) throw new IllegalArgumentException("amount");
            int fee = policy.fee(order);
            if (fee < 0) throw new IllegalArgumentException("fee");
            return Math.addExact(order.amount(), fee);
        }
    }

    static int flatFee(Order order) {
        return 20;
    }

    static FeePolicy freeFrom(int threshold, FeePolicy original) {
        Objects.requireNonNull(original);
        return order -> order.amount() >= threshold ? 0 : original.fee(order);
    }

    public static void main(String[] args) {
        QuoteService service = new QuoteService();
        List<Order> orders = List.of(
                new Order("O-1", 80, false),
                new Order("O-2", 120, true));

        for (Order order : orders) {
            System.out.println(order.code() + "/classic-flat=" +
                    service.total(order, new FlatFee()));
            System.out.println(order.code() + "/classic-priority=" +
                    service.total(order, new PriorityFee()));
        }

        FeePolicy flat = BehaviorInjectionDemo::flatFee;
        FeePolicy priority = order -> order.priority() ? 50 : 20;
        FeePolicy freeShipping = freeFrom(100, flat);

        for (Order order : orders) {
            System.out.println(order.code() + "/reference=" + service.total(order, flat));
            System.out.println(order.code() + "/lambda=" + service.total(order, priority));
            System.out.println(order.code() + "/free-from-100=" +
                    service.total(order, freeShipping));
        }

        FeePolicy testPolicy = order -> 0;
        System.out.println("test=" + service.total(orders.get(0), testPolicy));

        try {
            service.total(orders.get(0), order -> -5);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 BehaviorInjectionDemo.java
java BehaviorInjectionDemo
```

Output **verified in practice with Java 17**:

```text
O-1/classic-flat=100
O-1/classic-priority=100
O-2/classic-flat=140
O-2/classic-priority=170
O-1/reference=100
O-1/lambda=100
O-1/free-from-100=100
O-2/reference=140
O-2/lambda=170
O-2/free-from-100=120
test=80
invalid=fee
```

### How to Read the Program

- Record `Order(code, amount, priority)` uses the example's immutable data (a record with the declared components).
- `FeePolicy` has one SAM, suitable for lambdas or method references.
- `FlatFee` and `PriorityFee` show **the traditional way of writing Strategy classes**. They are still valid implementations, just not mandatory for small rules.
- `QuoteService.total` has no `if (policyType == ...)` to pick a policy; callers pass the appropriate `FeePolicy`.
- `BehaviorInjectionDemo::flatFee` illustrates a method reference: an existing static method used as a behavior object.
- `order -> order.priority() ? 50 : 20` illustrates an inline lambda with short logic.
- `freeFrom(100, flat)` **returns another `FeePolicy`**: orders of 100 or more get free shipping, while others delegate to the original policy. Behavior can be wrapped/composed.
- `testPolicy = order -> 0` lets you test `QuoteService` logic without building a `FreeFeeForTests` class.
- `invalid=fee` proves the service still **validates the contract** of the passed-in policy.

The example represents money with `int` to focus on passing behavior, and uses `Math.addExact` to detect overflow. For real monetary systems, choose `BigDecimal` or integers representing the smallest unit along with appropriate rounding rules and safe ranges.

## 9. Standalone Java 17 Program: Passing Multiple Behaviors to a Workflow

Create file `FunctionalWorkflowDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class FunctionalWorkflowDemo {
    record Candidate(String name, int score, boolean active) {}

    static List<String> select(
            List<Candidate> source,
            Predicate<? super Candidate> rule,
            Function<? super Candidate, String> format,
            Comparator<? super String> order) {
        return source.stream()
                .filter(rule)
                .map(format)
                .sorted(order)
                .toList();
    }

    static void deliver(List<String> values, Consumer<? super String> sink) {
        values.forEach(sink);
    }

    public static void main(String[] args) {
        List<Candidate> data = List.of(
                new Candidate("An", 85, true),
                new Candidate("Binh", 72, false),
                new Candidate("Chi", 95, true),
                new Candidate("Dung", 82, true));

        Predicate<Candidate> eligible = c -> c.active() && c.score() >= 80;
        List<String> names = select(
                data, eligible, Candidate::name, Comparator.naturalOrder());
        System.out.println("eligible=" + names);

        Predicate<Candidate> excellent = c -> c.active() && c.score() >= 90;
        System.out.println("excellent=" +
                select(data, excellent, Candidate::name, Comparator.naturalOrder()));

        Function<Candidate, String> label = Candidate::name;
        Function<Candidate, String> uppercase = label.andThen(String::toUpperCase);
        System.out.println("upper=" +
                select(data, eligible, uppercase, Comparator.naturalOrder()));

        List<String> reverse = select(data, eligible,
                c -> c.name() + ":" + c.score(), Comparator.reverseOrder());
        System.out.println("reverse=" + reverse);

        List<String> fakeMessages = new ArrayList<>();
        deliver(names, fakeMessages::add);
        System.out.println("delivered=" + fakeMessages);
        System.out.println("sourceSize=" + data.size());
    }
}
```

Run commands:

```bash
javac --release 17 -encoding UTF-8 FunctionalWorkflowDemo.java
java FunctionalWorkflowDemo
```

Exact output:

```text
eligible=[An, Chi, Dung]
excellent=[Chi]
upper=[AN, CHI, DUNG]
reverse=[Dung:82, Chi:95, An:85]
delivered=[An, Chi, Dung]
sourceSize=4
```

Explanation:

- `eligible`: caller uses `Predicate<Candidate>` “active and score at least 80” to select people.
- `excellent`: swaps only the predicate “at least 90”, **without writing another class or copying the `select` function**.
- `upper`: uses `Candidate::name` and `andThen(String::toUpperCase)` to change the formatting step.
- `reverse`: keeps the predicate, swaps formatter and comparator to display `name:score` in reverse string order.
- `deliver`: accepts `Consumer<String>` to decide where to send results; in the example, `fakeMessages::add` is an in-memory fake sink instead of a real delivery service.
- `sourceSize=4`: the original source is not mutated by the workflow; this pattern has strong testability and reusability.

Note: `select` produces data via `filter`, `map`, `sorted`, `toList`. Actions that **must execute** are placed into `deliver` separately; do not hide notification sending inside `map` or `peek`.

## 10. Method References When a Suitable Method Already Exists

When a method already exists that does exactly what is needed, a method reference is often concise:

```java
FeePolicy p = BehaviorInjectionDemo::flatFee;
Function<Candidate, String> name = Candidate::name;
Consumer<String> print = System.out::println;
```

These are illustrative statements inside a class with the appropriate types. They correspond in behavior to:

```java
FeePolicy p = order -> BehaviorInjectionDemo.flatFee(order);
Function<Candidate, String> name = candidate -> candidate.name();
Consumer<String> print = value -> System.out.println(value);
```

Note: the two groups above **cannot be copied together into the same block scope** because they declare duplicate names `p`, `name`, `print`; they are shown for syntax comparison.

Java supports common forms `ClassName::staticMethod`, `instance::instanceMethod`, `ClassName::instanceMethod` (the receiver is the parameter of the functional interface), and `ClassName::new`. Method references are resolved via **target type** and overload resolution; not every method name can have its type inferred in isolation.

Prefer method references when they make the code **more readable**; if you need extra validation, chaining multiple steps, or conditions, a lambda can be clearer.

## 11. Passing Behavior at Call Sites and Creating Behavior Factories

One advantage is the ability to **return behavior** from a method:

```java
static FeePolicy freeFrom(int threshold, FeePolicy original) {
    Objects.requireNonNull(original);
    return order -> order.amount() >= threshold
            ? 0
            : original.fee(order);
}
```

This is the method from the full example in Section 8. `threshold` and `original` are **captured** by the lambda for later use.

Example:

```java
FeePolicy base = order -> 20;
FeePolicy freeShipping = freeFrom(100, base);
```

When calling `freeShipping.fee(order)`, if the order's amount is at least 100 it returns 0; otherwise, it calls `base.fee(order)`. This creates **variants by composing rules**, without needing a separate `FreeShippingOver100Policy` class.

Regarding lambda capture, local variables referenced from a lambda must be **final or effectively final** per Java rules; a lambda cannot directly mutate captured external local variables. Do not “work around” this rule with a mutable array just to manage shared state, as it easily leads to side effects and race conditions.

If the wrapping logic is large, has multi-step state, or needs standalone documentation, creating a separate policy class can still be a better choice.

## 12. Comparing Conditional Configuration vs. Passing Behavior

A design that often leads to many branches:

```text
int calculate(Order order, String type) {
    if (type.equals("FLAT")) { ... }
    else if (type.equals("PRIORITY")) { ... }
    else if (type.equals("FREE_100")) { ... }
    else { ... }
}
```

This is **pseudocode**, not standalone Java, since the branch bodies are omitted. Problem: every time a strategy is added, you must edit the service directly, extend the `if/else` chain, and risk breaking existing logic.

With a behavior parameter:

```java
int total(Order order, FeePolicy policy) {
    int fee = policy.fee(order);
    return Math.addExact(order.amount(), fee);
}
```

This is a **shortened version purely for structural comparison**; the full version in Section 8 also checks null, amount, and fee.

If the application receives a config string like `"PRIORITY"` from HTTP/CLI, there can still be a **strategy selection step at the boundary**:

```text
String mode from request
      |
  choose appropriate FeePolicy
      |
QuoteService.total(order, policy)
```

Selecting at the boundary **differs from** embedding piles of selection branches into the core computation logic. The caller is responsible for choosing the policy; the service only works with the `FeePolicy` contract.

Nor should you turn very simple logic into overly abstract structures. If there is only one fixed calculation with no need to vary, adding a functional parameter can just make the API harder to understand.

## 13. Testability: Replacing Real Dependencies with Fake Functions

Behavioral parameterization is a form of **simple dependency injection**. In tests, you can pass a fake policy without building a class hierarchy or complex mocks:

```java
FeePolicy zeroFee = order -> 0;
int total = service.total(new Order("T-1", 80, false), zeroFee);
if (total != 80) {
    throw new AssertionError("expected 80, got " + total);
}
```

This illustrative snippet is in a context with `QuoteService`, `FeePolicy`, `Order`, and a `service` variable. Because the fee policy is a pure function returning 0, the test can focus on the service's **validation and addition**.

Additional cases can be tested:

- Policy returns a negative fee → service throws `IllegalArgumentException`.
- `order.amount()` is negative → service rejects the data.
- Policy is `null` → `Objects.requireNonNull` throws an error.
- Sum exceeds `int` range → `Math.addExact` throws `ArithmeticException`.
- Policy calculates fee based on priority → results match each order type.

If a test needs to observe how many times a callback was invoked, you can use a stateful fake **in a sequential test**. Do not write tests that depend on callback order when the API allows parallel execution or optimizations.

### Behavioral Testing and Integration Testing Are Two Different Layers

A fake lambda can prove the service **calls the contract correctly**, but it does not prove a real email-sending or DB-writing service works. You still need integration tests for external system boundaries, retries, and persistence according to real architecture.

## 14. Distinguishing Pure Behavior from Behavior with Side Effects

A **pure function** (*pure function*) typically uses only its inputs and returns an output without modifying external state. A `FeePolicy` that takes an `Order` and calculates a fee is a good candidate for a pure function.

**Behavior with side effects** such as writing files, sending notifications, updating a DB, or counting events can be passed via `Consumer` or a custom interface, but passing a lambda **does not automatically guarantee**:

- That the action runs only once across the whole system.
- Transactions or rollbacks when an error occurs.
- All actions complete if processing is cancelled.
- Thread safety when multiple threads invoke the lambda concurrently.
- Processing order when using parallel streams.

The example `deliver(names, fakeMessages::add)` uses a fake List in the main program, and must not be taken to mean “an email-sending system has succeeded”.

If an action must execute on every record, invoke it in an **explicit processing step** (`for`, properly managed terminal `forEach`, or a service), rather than hiding it in `Stream.peek` or `map` and assuming the framework will run side effects. Also clearly define who is responsible for catching/rethrowing checked exceptions, recording status, and retrying.

## 15. Checked Exceptions and Functional Interfaces

Standard interfaces like `Function<T,R>.apply` or `Consumer<T>.accept` do not declare checked exceptions. Therefore, lambdas passed to them **cannot directly throw** an unhandled checked exception such as `IOException`.

For example, a method with `throws IOException` cannot be called directly from a `Function<String,String>` lambda without catching the error, converting the exception, or switching to an appropriate target interface.

When domain behavior has checked errors that callers must handle, you can define:

```java
@FunctionalInterface
interface CheckedOperation<T> {
    void execute(T value) throws java.io.IOException;
}
```

This is a standalone interface declaration that can be placed in an appropriate class/file. It makes the **`throws` contract** explicit instead of silently wrapping every error in `RuntimeException`.

Do not define a custom interface just to “avoid try/catch” if the external API still requires `Consumer<T>`. When connecting with the Stream API, you still need an error conversion or handling policy at the appropriate boundary.

## 16. When a Separate Class Is Still Better Than a Lambda

**Keep or create a class** when the behavior has:

1. **Multiple cooperating methods** or a protocol beyond a single SAM.
2. **Real state and lifecycle**: connections, caches, mutable configuration, resource management.
3. **Multiple dependencies** that need explicit injection and management by a DI container.
4. **Identity / plugin registration / configuration**: policies toggled on/off, named, and observed independently.
5. **Complex enough behavior** to warrant its own documentation, unit tests, and logging.
6. **Controlled extensibility requirements** with subclasses/sealed hierarchies or specific domain types.
7. **Widespread reuse**, where a named class/object is clearer than repeated lambdas.

For example, a fee policy based on price tables, regions, exchange rates, time, and a rule engine may deserve its own service or class. `FeePolicy` remains the contract passed to `QuoteService`; just because callers are allowed to use lambdas **does not mean** every implementation must be a lambda.

Similarly, a one-line function with important business meaning can be written as a **named method reference**, keeping call sites short while making it easy to search for and test.

## 17. Common Design Mistakes When Passing Behavior

| Mistake | Why It Is a Problem | How to Fix |
| --- | --- | --- |
| Creating a new class for every one-line lambda | Lots of boilerplate without adding meaning | Pass a lambda or method reference |
| Duplicating shared logic in every strategy | Copy/pasted validation and orchestration | Keep shared pipeline in one place, pass varying step |
| Writing `if/else` to choose policy inside core service | Core must be edited for every new variant | Choose policy at boundary, pass into core |
| Passing `Function<Object,Object>` for “flexibility” | Loses type safety and domain meaning | Use proper generics or domain-named interfaces |
| Using `Consumer<T>` when a result is needed | Consumer's SAM returns `void` | `Function<T,R>` or interface with return type |
| Overly long lambdas full of business logic | Hard to read, test, and debug | Extract clearly named methods/classes |
| Lambda captures shared mutable objects | Results depend on state, prone to race conditions | Prefer immutability, pure functions |
| Method reference is harder to read than lambda | Readers must trace across multiple classes | Choose whichever form is most readable |
| Service trusts every callback to return valid values | Can receive negative/null/out-of-range values | Validate contract right at the boundary |
| Using `peek` for mandatory actions | Intermediate stage may not execute | Move action into an explicit terminal step |
| Turning every behavior into 10 lambda parameters | Cluttered API, easy to swap arguments | Create named config/policy objects |
| Writing custom functional interfaces for every `map` | Unnecessarily duplicates standard APIs | Prefer `java.util.function` when expressive enough |
| Assuming lambdas are automatically thread-safe | Lambdas can capture shared mutable state | Design concurrency separately |
| Assuming functional interfaces can throw any checked exception | SAM has a specific `throws` contract | Catch/convert errors or define an appropriate SAM |

## 18. Practice Exercises (with Answers)

**Exercise 1 — Identify the Variation Point.** A filter has three versions: filter by age, by score, by status. All three run `source.stream().filter(...).toList()`. Which part should be passed as a parameter?

Answer: pass `Predicate<T>` for the condition; keep `stream().filter(rule).toList()` as the shared pipeline.

**Exercise 2 — Write a Fee Lambda.** Given `FeePolicy` as in the lesson, write a policy with a fee of 30 for priority orders and 10 for regular orders.

Answer:

```java
FeePolicy policy = order -> order.priority() ? 30 : 10;
```

This is an illustrative statement inside a method with appropriate `Order` and `FeePolicy` types.

**Exercise 3 — Method Reference.** Given `static int flatFee(Order order)`, how do you represent it as a `FeePolicy` using a method reference?

Answer: `FeePolicy rule = BehaviorInjectionDemo::flatFee;` when in a class or context with access to that method.

**Exercise 4 — Testing.** Why is passing `order -> 0` to `QuoteService` more convenient than writing a `ZeroFeeTestPolicy` class for a simple test?

Answer: the fake is short, visible right at the test site, needs no separate class/file, and is still type-checked as `FeePolicy`. If the fake must simulate complex state, a separate class can be clearer.

**Exercise 5 — Comparing Standard Interfaces.** A step takes `Candidate` and returns `String`. Should you use `Consumer<Candidate>` or `Function<Candidate,String>`?

Answer: use `Function<Candidate,String>` because a `String` result is needed. `Consumer` has `void accept(...)`.

**Exercise 6 — Refactoring if/else.** A core service takes `String feeMode` and uses `if/else` to pick among three fee rules. Where should policy selection move?

Answer: to the **caller / system edge** (where request/config is read). The core takes `FeePolicy` and does not need to know which mode was selected.

**Exercise 7 — Passing Multiple Behaviors.** In `select(source,rule,format,order)`, if you swap `rule` while keeping `format` and `order`, do you have to rewrite `select`?

Answer: no. The caller passes a different `Predicate`. That is the benefit of a shared workflow accepting behavior parameters.

**Exercise 8 — State.** Why can `int[] count={0}; Consumer<String> action=s -> count[0]++;` be hard to use safely in a parallel stream?

Answer: the mutable array is captured, and multiple threads can increment without synchronization, causing races. The effectively final rule only protects **the local variable reference**, not making the captured object's contents immutable or thread-safe.

**Exercise 9 — When to Use a Class.** A policy needs database access, has a cache, per-customer configuration, and its own lifecycle. Should you insist on writing a long lambda just to reduce class count?

Answer: no. You can use a separate class/service implementing the same interface, since it is an independent abstraction with real state and responsibilities.

**Exercise 10 — Choosing Policy and Computing Total.** Given an order with `amount=120`, `priority=true`, priority policy `50`, and policy `freeFrom(100, priority)`, what total is returned when using the wrapped policy?

Answer: `120`. Because the amount meets the threshold, the fee is 0; `QuoteService` adds 120 + 0. This is behavior change via a function object, without editing the service.

## 19. Checklist Before Refactoring from Many Classes to Behavior Parameters

1. **Have you identified the true variation point?** Do the classes only differ by one step, or do they also have different data/responsibilities?
2. **Can the shared part be placed in one function/service?** Avoid duplicating validation, logging, and error handling.
3. **Is the behavior contract clear enough?** Parameter types, return type, validity conditions, checked exceptions.
4. **Is there a suitable functional interface?** Prefer standard ones; create domain-named interfaces when they add meaning.
5. **Have you named complex behaviors?** Short inline lambdas, method references for named code, classes for multi-responsibility logic.
6. **Is the behavior pure?** If it has side effects, define lifecycle, concurrency, transactions, and errors.
7. **Does the caller pick the right policy?** Do not scatter confusing `if/else` chains from the core to many other places without structure.
8. **Do tests cover both core and policies?** Use fake policies for the core; test real policies independently, and add integration tests if external systems are involved.
9. **Does the refactoring actually improve readability?** Reduce boilerplate without making the API harder to call or search.
10. **Is there a risk of capturing mutable state?** Avoid uncontrolled state dependencies, especially under parallel execution.

## 20. Key Takeaways

- When **many classes differ only by one short operation**, you can keep one shared workflow and **pass behavior** via a functional interface parameter.
- **Lambdas** and **method references** provide implementations of a functional interface without writing a dedicated class for every variant.
- **The Strategy Pattern does not disappear**: instead of always creating Strategy classes, you can implement Strategy with a lambda when simple.
- Choose standard interfaces (`Predicate`, `Function`, `Consumer`, `Supplier`, `Comparator`) when expressive enough; use domain-named interfaces when an explicit contract is needed.
- **The core service** owns the shared workflow and validation; **the caller** decides the behavior; tests pass fakes to verify the shared part.
- Functional parameterization extends processing without adding piles of classes, but **does not replace** classes/services when there is state, configuration, lifecycle, or complex business logic.
- Lambdas do not automatically guarantee side effects, checked exceptions, thread safety, or exactly-once execution. Those concerns still require dedicated design.

Official references: [Java SE 17 — java.util.function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/package-summary.html), [Function](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Function.html), [Predicate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/function/Predicate.html), [Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html), [JLS 9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8), [JLS 15.27 — Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27).
