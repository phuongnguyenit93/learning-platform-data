# Risks of Mutable `static` State and Interdependent Tests in Java

In Java, a field with the `static` keyword belongs to the **class at runtime**, not individually to each object. If that field is **mutable**, all code using that corresponding runtime class can affect the same shared state. This is a useful tool, but it easily creates hard-to-detect bugs: a test passes when run in isolation but fails when running the entire test suite; changing test order alters the result; two requests interfere with each other; or a long-running program retains stale data and does not release resources.

Example:

~~~java
class Discount {
    static int percent = 0;

    static int priceAfterDiscount(int price) {
        return price - price * percent / 100;
    }
}
~~~

One test runs `Discount.percent = 20`. Another test expects the default value `0` yet runs **in the same JVM and on the same runtime class**. Without isolation, the second test's result depends on the first test. The concern does not lie in the discount calculation, but in the **hidden dependency through the static field**.

This lesson focuses on the **Static Members** topic of Java Core — Class & Object: how shared mutable static state works, why it causes test-order dependence, isolation failure, and thread-safety and memory-retention problems, along with handling strategies ranging from simple fixes to well-testable designs. The standalone programs use **Java 17+**, with compile/run commands and stdout for comparison.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain why two different objects can read/write **the same static field**.
2. Distinguish between a static **constant**, a static **mutable primitive**, and a static **reference to a mutable object**.
3. Point out **hidden shared state** when code does not pass parameters yet its behavior still changes.
4. Explain why test results depend on **order, prior tests, running in the same JVM, and how state is reset**.
5. Create a demo reproducing a test that can PASS when run individually but FAIL when run after another test.
6. Distinguish **isolation between tests** from **thread safety**; a single solution may solve only one issue.
7. Know the limitations of `@BeforeEach`, `@AfterEach`, `@BeforeAll`, reset helpers, and test frameworks.
8. Consider alternatives: **instance-owned state**, dependency injection, pure functions, immutable configuration, and controlled lifecycle.
9. Understand that `static final` does not guarantee the referenced object is immutable.
10. Recognize that global caches, singletons, mutable registries, static clocks/random generators, and `ThreadLocal` can cause state leakage.
11. Use `AtomicInteger`, synchronization, or concurrent collections in the right situations.
12. Write tests based on **public behavior**, without depending on leftover environment state from other tests.
13. Consider module/class-loader boundaries when saying "one static copy across the entire JVM".
14. Have a process for investigating and fixing a test that fails intermittently depending on suite order.

## 2. Why Does `static` Create Shared State?

Consider two fields:

~~~java
class VisitTracker {
    int localVisits;
    static int totalVisits;

    void visit() {
        localVisits++;
        totalVisits++;
    }
}
~~~

Two independent objects:

~~~java
VisitTracker a = new VisitTracker();
VisitTracker b = new VisitTracker();
a.visit();
b.visit();
~~~

State diagram:

~~~text
Class VisitTracker
  static totalVisits = 2
          ^       ^
          |       |
      a object   b object
      local=1    local=1
~~~

`a.localVisits` and `b.localVisits` are **instance fields**: each object has its own value. `VisitTracker.totalVisits` is a **static field**: the same value is updated by two different calls.

Therefore, the right question is not "does object A affect object B?", but rather **"do both objects read/write the same static field or a mutable object referenced by a static field?"**.

### What Not to Over-Infer

- A static field is not copied separately for each new instance.
- `VisitTracker alias = a;` only creates a reference alias; it does not call a constructor and does not create a new static copy.
- A static field is also **not always strictly unique across every class with the same name in the JVM**. Different runtime classes defined by different class loaders can hold separate static states.
- Static does not automatically guarantee atomicity, visibility, security, isolation, or immutability.

In console learning programs using a standard single class loader, the model of "one shared static field per class" is sufficient to understand the examples.

## 3. What Kinds of Static Mutable State Exist?

It is not only fields without `final` that are dangerous.

| Declaration | What can change? | Risk when shared |
| --- | --- | --- |
| `static int count;` | The int value of the field | Another test increments/decrements the value |
| `static String mode;` | The reference field can be reassigned | One test changes another test's configuration |
| `static final int LIMIT = 10;` | The field cannot be reassigned, primitive value is fixed | Usually low mutable-state risk |
| `static final String PREFIX = "ID-";` | String is immutable; field is final | Suitable as a constant if it fits the contract |
| `static final List<String> EVENTS = new ArrayList<>();` | Contents of the List object can still be modified | Tests can add/remove each other's events |
| `static final AtomicInteger COUNT = new AtomicInteger();` | Value inside the AtomicInteger changes | Thread-safe per atomic operation, still shared across tests |
| `static final Map<K,V> CACHE = new ConcurrentHashMap<>();` | Map contents change | Thread-safe at a certain API level, **does not automatically isolate tests** |
| `static final Clock CLOCK = Clock.systemUTC();` | Reference is fixed; clock output changes over time | Tests depend on wall-clock and environment |
| `static final Random RNG = new Random();` | PRNG state advances when drawing numbers | Call order alters the sequence in tests |

**Key takeaway:** `final` on a reference only restricts **reassigning the field's reference**. It does not freeze the entire object graph inside.

## 4. Runnable Example: How Does Test-Order Dependence Appear?

Create the file **`StaticTestOrderDemo.java`**:

~~~java
public class StaticTestOrderDemo {
    static final class Discount {
        static int percent = 0;

        static int finalPrice(int base) {
            return base - base * percent / 100;
        }
    }

    static void expect(String label, int expected, int actual) {
        String result = expected == actual ? "PASS" : "FAIL";
        System.out.println(label + ": " + result
                + " (expected=" + expected + ", actual=" + actual + ")");
    }

    static void testDefaultPrice() {
        expect("default", 100, Discount.finalPrice(100));
    }

    static void testWithDiscount() {
        Discount.percent = 20;
        expect("discount", 80, Discount.finalPrice(100));
    }

    public static void main(String[] args) {
        System.out.println("Order A");
        testDefaultPrice();
        testWithDiscount();

        System.out.println("Order B");
        testDefaultPrice();
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticTestOrderDemo.java
java StaticTestOrderDemo
~~~

Stdout:

~~~text
Order A
default: PASS (expected=100, actual=100)
discount: PASS (expected=80, actual=80)
Order B
default: FAIL (expected=100, actual=80)
~~~

### Step-by-Step Analysis

1. When class `Discount` is initialized, `percent` has the value `0`.
2. The first time `testDefaultPrice` is called, the result is 100 → PASS.
3. `testWithDiscount` **writes 20 to the static field**, computing 80 → PASS.
4. No statement restores the field back to 0.
5. `testDefaultPrice` runs again in the **same JVM and the same runtime class**, so it receives `percent = 20` and returns 80 → FAIL.

This is a **simulated test double-runner**, without using JUnit. The goal is to illustrate a real bug: the method name and expected result do not change; only the **state outside the method** was modified by another test.

### What Happens If You Run `java StaticTestOrderDemo` Twice?

Each standard `java` command launches a new JVM process and initializes new runtime classes. Static state from the previous process does not automatically transfer to the new process. However, **a test suite running multiple test cases in the same JVM** can retain class state across invocations. Test runners typically do not guarantee creating a new JVM for each test method.

Therefore, you should not conclude "it passes when I run it alone, so the test is correct." It must be verified **when running within the same suite**.

## 5. Static State Creates Hidden Dependencies Between Tests

A good test should clearly state:

- What inputs it needs.
- What conditions the initial state must satisfy.
- The behavior being executed.
- The expected result.
- How side effects must be cleaned up.

With static fields, state can be changed by parts of the system **that do not appear in the method calls of the current test**:

~~~text
Test A:
  set Discount.percent = 20
       |
       v
  Shared static field
       |
       v
Test B:
  calls Discount.finalPrice(100)
  observes 80, expected 100
~~~

This is **hidden coupling**: Test B does not call Test A, does not receive any parameters from Test A, and does not know it depends on Test A. Yet its behavior changes depending on the execution result of Test A.

### Common Symptoms

- A test passes when run alone from the IDE, but fails when running the whole suite.
- Re-running a test multiple times in the same process produces changing results.
- Changing the test order changes which test fails.
- Running tests in parallel introduces failures that happen only occasionally.
- `@BeforeEach` is placed in one test class, yet another test class still modifies global state.
- A static cache causes a test to read stale data that does not belong to the current scenario.
- Mock/static configuration is not restored after a test finishes.

These are **signals to investigate**, not proof that every flaky failure is caused by static state: it could also be the clock, network, randomness, I/O, database, a race condition, or improper test setup.

## 6. When Is a Test Truly "Independent"?

A well-designed test should be able to run:

- Individually.
- Together with other tests.
- In various orders.
- Multiple times.
- On workers/processes matching the test configuration.
- In parallel if the suite claims to support parallelism.

Not every suite has to run in parallel. However, if a test needs another test to run first to prepare a static field, that is an **unwanted dependency** unless the test system intentionally designs an integration flow with an explicitly managed lifecycle.

Two principles:

**Independence**: A test's result does not depend on what other tests have called.

**Isolation**: Tests do not inadvertently share mutable state or resources that they do not control.

Isolation is one way to achieve independence, but tests can also become environment-dependent through files, databases, networks, timezones, or system properties. Therefore, fixing a static field only resolves part of the picture.

## 7. Why Is `static` Risky, Yet Not Always Wrong?

A **static immutable constant** is usually easy to use and reliable:

~~~java
public final class Limits {
    public static final int MAX_ITEMS = 100;

    private Limits() {
    }
}
~~~

There is no way to modify `MAX_ITEMS` in normal Java code. Tests using this constant typically do not affect the state of other tests.

By contrast, a mutable registry:

~~~java
class Registry {
    static final java.util.List<String> entries =
            new java.util.ArrayList<>();
}
~~~

allows any code with appropriate access permissions to call `entries.add(...)` and change the shared contents.

**The problem is not the `static` keyword itself, but the combination of:**

1. **Mutable** state.
2. **Broad** sharing scope.
3. Multiple callers having permission to make changes.
4. No mechanism defining **owner and lifecycle**.
5. Tests not reconstructing their own initial state.
6. Concurrent operations not being properly protected.

A **pure** static method that relies solely on its arguments can still be very easy to test, such as `Math.max(a, b)`. You should not forbid all static members when the goal is only to avoid mutable global state.

## 8. Fix 1: Reset at Test Boundaries

A quick measure to salvage legacy code is to reset static state to a **known state** before each test.

Example:

~~~java
class Discount {
    private static int percent;

    static void configure(int value) {
        if (value < 0 || value > 100) {
            throw new IllegalArgumentException("invalid discount");
        }
        percent = value;
    }

    static void resetForTests() {
        percent = 0;
    }

    static int finalPrice(int base) {
        return base - base * percent / 100;
    }
}
~~~

This is an **illustrative class**, not a recommended API to publicly expose reset across all systems. Depending on the architecture, `resetForTests` should only have access appropriate for tests, or reset via a controlled fixture.

A test can call:

~~~java
Discount.resetForTests();
Discount.configure(20);
// Assert Discount.finalPrice(100) == 80.
~~~

Resetting helps each test start under clear conditions. However, it has **important limitations**:

- If two tests run **in parallel** and use the same static field, test A's reset can clear the state that test B is using.
- If there is another related static cache, listener, thread, or resource that has not been reset, assigning `percent=0` does not complete cleanup.
- A test may stop due to an exception mid-execution, preventing end-of-test cleanup from running if organized improperly.
- If multiple test classes act on the static field, a consistent reset convention across classes is needed.
- If tests constantly have to call global reset, that may be a sign that you should **change the design**.

Resetting is suitable to **temporarily mitigate impact** for legacy code or controlled shared fixtures. Resetting should not be viewed as a general solution superior to dependency injection.

## 9. Runnable Example: Resetting Makes Sequential Tests More Independent

Create the file **`StaticResetDemo.java`**:

~~~java
public class StaticResetDemo {
    static final class FeatureFlags {
        private static boolean newCheckout;

        static void enableNewCheckout() {
            newCheckout = true;
        }

        static boolean isNewCheckoutEnabled() {
            return newCheckout;
        }

        static void reset() {
            newCheckout = false;
        }
    }

    static void testDefault() {
        FeatureFlags.reset();
        System.out.println("default=" +
                FeatureFlags.isNewCheckoutEnabled());
    }

    static void testEnabled() {
        FeatureFlags.reset();
        FeatureFlags.enableNewCheckout();
        System.out.println("enabled=" +
                FeatureFlags.isNewCheckoutEnabled());
    }

    public static void main(String[] args) {
        testEnabled();
        testDefault();
        testDefault();
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticResetDemo.java
java StaticResetDemo
~~~

Stdout:

~~~text
enabled=true
default=false
default=false
~~~

Each test method proactively restores the field to its initial state. In the **sequential execution of the demo**, the result is stable.

### Why Do Both Resetting at the Start and Cleaning Up at the End Play a Role?

- Resetting at the start of a test establishes a clear **precondition**, even if a previous test left state behind.
- Cleaning up at the end of a test reduces impact on other parts, especially resources that need to be closed.
- If cleanup must always run even when an exception occurs, use `try/finally` or the test framework's lifecycle hooks.
- For state shared between tests running in parallel, **both resetting at the start and cleaning up at the end can still race**.

Why not just call reset once in `@BeforeAll`? Because subsequent tests can still modify shared state. A single reset at the start of the class **does not create isolation between test methods**.

## 10. JUnit 5: Using Lifecycle Hooks Deliberately

With JUnit Jupiter, `@BeforeEach` is commonly used to prepare the fixture before each test method, while `@AfterEach` cleans up after each test method.

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DiscountTest {
    @BeforeEach
    void setUp() {
        Discount.resetForTests();
    }

    @AfterEach
    void tearDown() {
        Discount.resetForTests();
    }

    @Test
    void noDiscount() {
        assertEquals(100, Discount.finalPrice(100));
    }

    @Test
    void twentyPercent() {
        Discount.configure(20);
        assertEquals(80, Discount.finalPrice(100));
    }
}
~~~

**This is JUnit 5 illustrative code**, requiring the appropriate `org.junit.jupiter:junit-jupiter` dependency declaration and a configured test runner; it is not a program that only needs plain JDK `javac`. Use your project's Maven/Gradle build system and configured JUnit version.

The hooks above help control state when tests execute **sequentially and no other component modifies the same static field while the test is running**. They do not guarantee thread safety or cross-class isolation when other tests run in parallel on the same state.

### Be Careful with `@TestInstance`

JUnit may create a separate test class instance for each test method under its default lifecycle, but that **does not create a separate copy of static fields in production classes**. Changing the test instance lifecycle does not clear global static state.

**Do not confuse them:** resetting the **test object instance** and resetting **class-level production state** are two different things.

## 11. Fix 2: Move Data from Static to Instance

If a value inherently belongs to a **test, a session, a customer, or an object**, turning it into an instance field usually solves the problem more thoroughly than resetting global state.

Instead of:

~~~java
class SharedCart {
    static int itemCount;
}
~~~

consider:

~~~java
class Cart {
    private int itemCount;

    void addOne() {
        itemCount++;
    }

    int itemCount() {
        return itemCount;
    }
}
~~~

Each `new Cart()` creates new instance state. Tests can create their own Cart without resetting global state.

### Runnable Program Verifying Isolation

Create the file **`InstanceIsolationDemo.java`**:

~~~java
public class InstanceIsolationDemo {
    static final class Cart {
        private int itemCount;

        void addOne() {
            itemCount++;
        }

        int itemCount() {
            return itemCount;
        }
    }

    static void scenarioA() {
        Cart cart = new Cart();
        cart.addOne();
        cart.addOne();
        System.out.println("scenarioA=" + cart.itemCount());
    }

    static void scenarioB() {
        Cart cart = new Cart();
        System.out.println("scenarioB=" + cart.itemCount());
    }

    public static void main(String[] args) {
        scenarioA();
        scenarioB();
        scenarioA();
        scenarioB();
    }
}
~~~

~~~bash
javac -encoding UTF-8 InstanceIsolationDemo.java
java InstanceIsolationDemo
~~~

Stdout:

~~~text
scenarioA=2
scenarioB=0
scenarioA=2
scenarioB=0
~~~

Each scenario owns a new Cart object. There is no static mutable counter in Cart; therefore, the runs are independent regarding Cart's internal state.

**Limitation:** If different Cart instances receive a reference to the same mutable service/cache/database, tests can still share state through that dependency. Instance fields help **narrow the sharing scope**; they do not automatically guarantee that every dependency is isolated.

## 12. Fix 3: Dependency Injection with Scoped State

In a real application, multiple objects may **need to share data**, but sharing does not have to happen through a global static field.

For example, a service that updates statistics:

~~~java
interface Counter {
    void increment();
    int value();
}

final class InMemoryCounter implements Counter {
    private int count;

    @Override
    public void increment() {
        count++;
    }

    @Override
    public int value() {
        return count;
    }
}

final class EventService {
    private final Counter counter;

    EventService(Counter counter) {
        this.counter = java.util.Objects.requireNonNull(counter);
    }

    void processEvent() {
        counter.increment();
    }

    int processedEvents() {
        return counter.value();
    }
}
~~~

The classes above are illustrative code without `main`. Each `EventService` receives **a Counter dependency**:

- Two services using **the same Counter object** will share the count.
- Two services using **two separate Counter objects** will be independent.
- In tests, create a new Counter for each test; there is no need to modify static production state.
- The sharing scope is **determined by where dependencies are created/wired** rather than being hard-coded inside the class via static.

This is the useful essence of dependency injection: controlling the **ownership and lifecycle** of dependencies.

### You Do Not Need a Framework to Use DI

You can use constructors directly:

~~~java
Counter counter = new InMemoryCounter();
EventService service = new EventService(counter);
~~~

Spring, CDI, or other frameworks can manage object graphs in large projects, yet **dependency injection is a design principle**, and using a framework is not mandatory.

## 13. Runnable Example: Tests Are Given a Fresh Dependency

Create the file **`DependencyIsolationDemo.java`**:

~~~java
public class DependencyIsolationDemo {
    interface Counter {
        void add(int amount);
        int value();
    }

    static final class InMemoryCounter implements Counter {
        private int value;

        @Override
        public void add(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }
            value += amount;
        }

        @Override
        public int value() {
            return value;
        }
    }

    static final class EventService {
        private final Counter counter;

        EventService(Counter counter) {
            this.counter = java.util.Objects.requireNonNull(counter);
        }

        void onEvent() {
            counter.add(1);
        }

        int total() {
            return counter.value();
        }
    }

    static void scenarioA() {
        EventService service = new EventService(new InMemoryCounter());
        service.onEvent();
        service.onEvent();
        System.out.println("A=" + service.total());
    }

    static void scenarioB() {
        EventService service = new EventService(new InMemoryCounter());
        System.out.println("B=" + service.total());
    }

    public static void main(String[] args) {
        scenarioB();
        scenarioA();
        scenarioA();
        scenarioB();
    }
}
~~~

~~~bash
javac -encoding UTF-8 DependencyIsolationDemo.java
java DependencyIsolationDemo
~~~

Stdout:

~~~text
B=0
A=2
A=2
B=0
~~~

Each test-like scenario creates its own `InMemoryCounter`. There is no dependence on execution order and no need for any `resetStaticState()` method.

This is instance state and is **not automatically thread-safe** if multiple threads share a single Counter. To support concurrent updates, you can swap in an atomic/synchronized Counter implementation **without changing the EventService API**. That is an additional benefit of separating the interface from how state is stored.

## 14. Fix 4: Pure Functions and Immutable Input

If the logic does not need to remember state across calls, you can use a pure function:

~~~java
static long discountedPrice(long base, int percent) {
    if (base < 0 || percent < 0 || percent > 100) {
        throw new IllegalArgumentException("invalid input");
    }
    return base - Math.multiplyExact(base, percent) / 100;
}
~~~

The method is **explicitly passed all of its inputs**, without reading the static mutable `Discount.percent`. The same valid `base` and `percent` will produce the same result, independent of test order and previous calls.

Notes:

- `Math.multiplyExact` can throw an `ArithmeticException` if the product overflows; the rounding here uses integer division.
- Real-world rounding/tax/currency policies may differ; this example aims to illustrate **independence from a shared mutable field**.

A static method **can be pure and easy to test**, so there is no need to turn every method into an instance method just to avoid the `static` keyword.

### Comparing Two APIs

| API | What do the inputs depend on? | Easy to test independently? |
| --- | --- | --- |
| `Discount.finalPrice(100)` reading static `percent` | Hidden class-level state | Poor if the field is mutable |
| `discountedPrice(100, 20)` | Explicit `base` and `percent` | Better |
| `calculator.finalPrice(100)` with immutable calculator config | Constructor-injected instance config | Good when multiple calls share the same policy |
| `service.finalPrice(100)` using DB/request/clock | External dependencies | Requires faking/fixturing the dependencies |

"Pure" must be taken in its strict sense: the method has no observable side effects and does not depend on mutable external state. A static method reading `System.currentTimeMillis()` is not pure simply because it takes no parameters.

## 15. Runnable Example: Immutable Configuration Passed via Constructor

Create the file **`ImmutablePricingPolicyDemo.java`**:

~~~java
public class ImmutablePricingPolicyDemo {
    record PricingPolicy(int discountPercent) {
        PricingPolicy {
            if (discountPercent < 0 || discountPercent > 100) {
                throw new IllegalArgumentException("invalid discount");
            }
        }
    }

    static final class PriceCalculator {
        private final PricingPolicy policy;

        PriceCalculator(PricingPolicy policy) {
            this.policy = java.util.Objects.requireNonNull(policy);
        }

        int finalPrice(int base) {
            if (base < 0) {
                throw new IllegalArgumentException("negative price");
            }
            return base - base * policy.discountPercent() / 100;
        }
    }

    public static void main(String[] args) {
        PriceCalculator normal = new PriceCalculator(new PricingPolicy(0));
        PriceCalculator sale = new PriceCalculator(new PricingPolicy(20));

        System.out.println("normal=" + normal.finalPrice(100));
        System.out.println("sale=" + sale.finalPrice(100));
        System.out.println("normal again=" + normal.finalPrice(100));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ImmutablePricingPolicyDemo.java
java ImmutablePricingPolicyDemo
~~~

Stdout:

~~~text
normal=100
sale=80
normal again=100
~~~

The two calculators hold two separate `PricingPolicy` instances with immutable data. They do not need to write `static Discount.percent` before each calculation, so calculator A's result is not altered by calculator B.

The example uses small `int` values to keep output simple; for large prices or monetary requirements, overflow, currency units, and rounding policies must be handled appropriately.

## 16. Which Solution Addresses Which Risk?

| Measure | Test-order isolation | Thread-safety | Scope of application |
| --- | --- | --- | --- |
| Reset static field before test | Possible, if tests run sequentially and reset thoroughly | No | Legacy fixtures |
| Reset after test with `finally`/`@AfterEach` | Reduces state leak if cleanup runs properly | No | Temporary global modifications |
| Each test has a new object instance | Good for the object's own state | Not automatically guaranteed | Domain/service local state |
| Constructor DI with a new dependency per test | Good if dependencies are truly separated | Not automatically guaranteed | Services, repositories, clocks |
| Immutable object/configuration | Reduces mutable state | Usually favorable for sharing | Value objects, policies |
| Pure function taking arguments | Good if there is no external hidden state | Favorable because there is no shared mutation | Calculation/validation |
| Static `AtomicInteger` | No: value is still shared | Atomic for certain appropriate operations | Concurrent counters |
| `synchronized` on static method | No: tests still share the field | Can protect critical sections | Shared operations |
| `ThreadLocal` | Does not guarantee per-test isolation | Separated per thread, carries lifecycle risks | Certain per-thread contexts |
| Separate JVM processes | Good for static state across processes | Does not solve races within one process | Integration suites/tooling |
| Separate class loaders | Can create separate runtime classes under suitable conditions | Not automatically guaranteed | Specialized plugin/test runtimes |

Choose a solution based on the **source of the dependency**, not just the tool's name. Replacing `int count` with `AtomicInteger` fixes certain race conditions but **does not fix test B reading state left behind by test A**.

## 17. Parallel Tests: Resetting Is No Longer Enough

Two tests running concurrently:

~~~text
Thread/Test A                       Thread/Test B
--------------------------------    --------------------------------
reset Discount.percent = 0
set Discount.percent = 20
                                    reset Discount.percent = 0
assert price == 80  -> FAIL!
                                    assert price == 100 -> PASS
~~~

Even if every test **resets at the beginning**, they still write to the same static field. Any interleaving order can occur under concurrency. Tests may PASS/FAIL inconsistently depending on timing.

### Approaches in the Right Direction

1. **Eliminate shared mutable state**: pass the policy via a constructor/parameter.
2. If tests are forced to modify a global resource, **do not run those tests in parallel** by using appropriate resource locks/isolation mechanisms from the test runner.
3. Isolate tests into separate processes when integration scenarios require it and the cost allows.
4. For mandatory production shared state, use synchronization/atomic/concurrent data structures and test invariants under concurrency, while still maintaining isolation between test scenarios.
5. Use scoped fixtures instead of global ones whenever possible; ensure all test classes follow the same lifecycle.

You should not simply add `Thread.sleep(100)` hoping tests will race less. Sleeping only changes timing; it does not establish a required invariant or happens-before relationship.

## 18. Race Condition Risk on a Static Counter

Code:

~~~java
class Counter {
    static int hits;

    static void hit() {
        hits++;
    }
}
~~~

`hits++` is a read–modify–write operation, not an operation guaranteed to be atomic across multiple threads. If two threads both read the old value 10, both compute 11, and both write 11, one increment is lost.

### Can `volatile` Handle This?

~~~java
static volatile int hits;
~~~

`volatile` supports visibility and ordering under the Java Memory Model, yet **does not make `hits++` atomic**. Therefore, a volatile int can still suffer from lost updates.

### Using `AtomicInteger` Within the Right Scope

~~~java
private static final java.util.concurrent.atomic.AtomicInteger HITS =
        new java.util.concurrent.atomic.AtomicInteger();

static void hit() {
    HITS.incrementAndGet();
}
~~~

Each `incrementAndGet()` call has an atomicity guarantee per the API. However, `HITS` is still a static object **shared across tests**. If test A increments it once, test B can observe that value unless tests are isolated or the state object is explicitly reset/managed.

## 19. Runnable Example: Atomicity Does Not Equal Test Isolation

Create the file **`AtomicButSharedDemo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicButSharedDemo {
    static final class Metrics {
        private static final AtomicInteger EVENTS = new AtomicInteger();

        static void addEvent() {
            EVENTS.incrementAndGet();
        }

        static int count() {
            return EVENTS.get();
        }

        static void clearForDemo() {
            EVENTS.set(0);
        }
    }

    static void runParallelWork() throws InterruptedException {
        Thread a = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                Metrics.addEvent();
            }
        });

        Thread b = new Thread(() -> {
            for (int i = 0; i < 1_000; i++) {
                Metrics.addEvent();
            }
        });

        a.start();
        b.start();
        a.join();
        b.join();
    }

    public static void main(String[] args)
            throws InterruptedException {
        Metrics.clearForDemo();
        runParallelWork();
        System.out.println("after parallel=" + Metrics.count());

        Metrics.addEvent();
        System.out.println("next scenario=" + Metrics.count());
    }
}
~~~

~~~bash
javac -encoding UTF-8 AtomicButSharedDemo.java
java AtomicButSharedDemo
~~~

Stdout:

~~~text
after parallel=2000
next scenario=2001
~~~

`AtomicInteger` helps the two threads accurately update the call count. `Thread.join()` ensures main waits for the threads to finish before reading. However, `next scenario` still starts from the value **already present** after the previous scenario, so it is 2001 instead of 1.

If you want each scenario to have its own counter, use a **passed-in Counter instance** or a dependency with a clear lifecycle. Atomics only solve the problem of **concurrent updates**; they do not fix the problem of **leftover state**.

## 20. Not Just Static Primitives: Shared Mutable Collections

Example:

~~~java
class EventBus {
    static final java.util.List<String> EVENTS =
            new java.util.ArrayList<>();
}
~~~

Tests can add:

~~~java
EventBus.EVENTS.add("ORDER_CREATED");
~~~

Another test may then see the leftover event even though it never called add.

Furthermore, `ArrayList` does not guarantee safe concurrent mutation. If multiple threads call `add` concurrently, lost updates or other issues may occur depending on execution scheduling.

### If a Class-Level Registry Is Truly Needed

You should consider:

- Hiding the field with `private`.
- Public methods that control `add`, `remove`, and invariants.
- Choosing appropriate synchronization/concurrent collections.
- Not returning a mutable internal reference directly.
- Having a lifecycle/clear/eviction strategy.
- Setting a capacity limit or time-to-live when data is long-lived.
- Providing a way to create a **separate registry for tests** instead of forcing use of the default global one.

A static registry for a product does not automatically become a reliable event bus architecture; there are also requirements for ordering, durability, error handling, asynchronous delivery, and thread safety.

## 21. Runnable Example: Returning a Snapshot Is Safer Than Returning a Raw List

Create the file **`StaticRegistrySnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class StaticRegistrySnapshotDemo {
    static final class Registry {
        private static final List<String> EVENTS = new ArrayList<>();

        static synchronized void record(String event) {
            if (event == null || event.isBlank()) {
                throw new IllegalArgumentException("event required");
            }
            EVENTS.add(event);
        }

        static synchronized List<String> snapshot() {
            return List.copyOf(EVENTS);
        }

        static synchronized void resetForDemo() {
            EVENTS.clear();
        }
    }

    public static void main(String[] args) {
        Registry.resetForDemo();
        Registry.record("A");
        Registry.record("B");

        List<String> view = Registry.snapshot();
        System.out.println("snapshot=" + view);

        Registry.record("C");
        System.out.println("old snapshot=" + view);
        System.out.println("new snapshot=" + Registry.snapshot());

        try {
            view.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot immutable structure");
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 StaticRegistrySnapshotDemo.java
java StaticRegistrySnapshotDemo
~~~

Stdout:

~~~text
snapshot=[A, B]
old snapshot=[A, B]
new snapshot=[A, B, C]
snapshot immutable structure
~~~

Here, the methods `record`, `snapshot`, and `resetForDemo` are all `static synchronized`, so they share the monitor of class `Registry` during those method calls. `List.copyOf` creates/obtains a list that disallows structural modification through normal APIs; the old snapshot does not change after `record("C")`.

However, **test isolation still must be handled**: static `EVENTS` still retains contents from previous record calls. `synchronized` controls consistency across Registry's synchronized methods; it does not automatically clear state between tests. When the list contains mutable elements, a structural snapshot also does not automatically deep-copy the elements.

## 22. A Static Cache Easily Causes Tests to Use Stale Data

A shared cache:

~~~java
static final java.util.Map<String, Customer> CACHE =
        new java.util.HashMap<>();
~~~

can retain a Customer from a previous test. If test B creates a Customer with the same ID and different data, yet the production code prioritizes the cache, test B reads stale data and fails.

In production, there are also risks:

- Missing cache invalidation when source data changes.
- User/tenant data getting mixed up if the cache key does not include the scope.
- Unbounded cache growth, causing memory retention.
- Races between threads if the `HashMap` is modified concurrently without synchronization.
- The cache is global, making it hard to replace/fake in tests.
- The test suite may depend on when the cache was warmed.

### Caches Are Not Always Bad

A cache with a clear contract, bounded size, eviction, concurrency control, and appropriate owner/lifecycle can improve performance. You need to test **hit, miss, invalidation, stale data**, as well as isolation. The key question is: does the cache truly need **global static scope**, or should it belong to a service/repository instance?

## 23. A Static Clock Makes Tests Time-Dependent

A hard-to-test example:

~~~java
class DeadlineService {
    static boolean isLate(java.time.Instant deadline) {
        return java.time.Instant.now().isAfter(deadline);
    }
}
~~~

The method does not read a dedicated static mutable field, but it queries **system time**. The result can vary depending on when the test runs. A test with a deadline close to the current moment can PASS/FAIL due to timing.

Instead of hard-coding the clock, inject `java.time.Clock`. For example:

~~~java
final class DeadlineService {
    private final java.time.Clock clock;

    DeadlineService(java.time.Clock clock) {
        this.clock = java.util.Objects.requireNonNull(clock);
    }

    boolean isLate(java.time.Instant deadline) {
        return java.time.Instant.now(clock).isAfter(deadline);
    }
}
~~~

Now tests control time using `Clock.fixed(...)`. This approach does not require mutable static state to test, helping reduce sources of flakiness.

## 24. Runnable Example: Injecting Clock Gives Tests Deterministic Results

Create the file **`InjectedClockDemo.java`**:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

public class InjectedClockDemo {
    static final class DeadlineService {
        private final Clock clock;

        DeadlineService(Clock clock) {
            this.clock = clock;
        }

        boolean isLate(Instant deadline) {
            return Instant.now(clock).isAfter(deadline);
        }
    }

    public static void main(String[] args) {
        Instant deadline = Instant.parse("2026-01-01T12:00:00Z");

        DeadlineService before = new DeadlineService(
                Clock.fixed(
                        Instant.parse("2026-01-01T11:00:00Z"),
                        ZoneOffset.UTC));

        DeadlineService after = new DeadlineService(
                Clock.fixed(
                        Instant.parse("2026-01-01T13:00:00Z"),
                        ZoneOffset.UTC));

        System.out.println("before late=" + before.isLate(deadline));
        System.out.println("after late=" + after.isLate(deadline));
    }
}
~~~

~~~bash
javac -encoding UTF-8 InjectedClockDemo.java
java InjectedClockDemo
~~~

Stdout:

~~~text
before late=false
after late=true
~~~

There is no dependence on the actual date/time when the program runs. The two `DeadlineService` objects own separate clock dependencies and can produce different results as required by tests.

### A Similar Pitfall: Static Random Generators

If multiple tests share a mutable `Random` object, the call order affects subsequent random numbers. Setting a shared seed in `@BeforeAll` does not guarantee test independence when they share the same generator. You can:

- Inject the generator per instance.
- Create a separate generator with a deterministic seed for each test.
- Mock/fake outcomes at the appropriate boundary.
- Assert properties instead of hardcoding the entire random sequence when the test goal does not depend on a specific sequence.

In security-sensitive production code, do not confuse a deterministic `java.util.Random` with a `SecureRandom` suitable for cryptographic requirements.

## 25. Static Mutable Configuration and Tests Modifying System Properties

Not only fields of classes you write yourself constitute global mutable state. Some environments have shared process-level configuration such as:

~~~java
System.setProperty("feature.mode", "new");
~~~

Another test calling `System.getProperty("feature.mode")` may observe the leftover value.

If a test needs to change a system property:

1. Record the exact **previous value and whether the property existed**.
2. Modify it within a controlled scope.
3. Restore it in `finally`/cleanup.
4. Do not allow other tests relying on the same property to run in parallel, unless appropriate isolation/locking is in place.
5. Even better, pass configuration as an argument/dependency if the API allows.

Do not call `System.clearProperty("feature.mode")` unconditionally at the end of a test if the property already held a useful environment value before the test. **Restore the original state**, do not clear by default.

## 26. Runnable Example: Restoring a Process-Level Property with `finally`

Create the file **`SystemPropertyRestoreDemo.java`**:

~~~java
public class SystemPropertyRestoreDemo {
    public static void main(String[] args) {
        String key = "learning.example.feature";
        String original = System.getProperty(key);

        try {
            System.setProperty(key, "enabled");
            System.out.println("inside=" + System.getProperty(key));
        } finally {
            if (original == null) {
                System.clearProperty(key);
            } else {
                System.setProperty(key, original);
            }
        }

        System.out.println("restored=" +
                java.util.Objects.equals(
                        original, System.getProperty(key)));
    }
}
~~~

~~~bash
javac -encoding UTF-8 SystemPropertyRestoreDemo.java
java SystemPropertyRestoreDemo
~~~

Stdout:

~~~text
inside=enabled
restored=true
~~~

Whether the property initially existed or not, the code attempts to restore the previous value. However, `finally` **does not eliminate races with other code concurrently modifying the same system property**. Restoring requires a test-execution isolation mechanism if multiple tests operate on the same key.

## 27. Test Order, Parallelism, and Types of Isolation

Distinguish scopes to choose a solution:

| Scope | Example shared state | How should it be isolated? |
| --- | --- | --- |
| Within the same test method | Local variable, dedicated object | Create its own fixture |
| Between test methods in the same class | Static field or `@TestInstance(PER_CLASS)` state | Per-test setup/instance |
| Between test classes in the same JVM | Production static cache, system property | Scoped dependencies, cleanup, resource lock |
| Between threads in the same JVM | Static mutable counter/list | Atomic/synchronization/ownership |
| Between processes | DB, filesystem, network service | Unique test namespace, transactions, cleanup |
| Between JVM class loaders | May have separate static states; external resources are still shared | Understand loader identity and external dependencies |
| Between builds/runs | Leftover DB data, files, environment | Controlled test environments |

**A test using a new object instance does not isolate the database**, and **separating JVMs does not isolate a shared database**. Do not use the wrong tool: trace back to the **actual shared resource**.

### Does a New Test Class Reset Static State?

No. Creating a new instance of the test class does not create a new copy of a production static field. A runtime class typically retains static state across test methods and classes within the same class-loading environment.

## 28. Why Is `ThreadLocal` Not the Solution for Every Static State?

`ThreadLocal<T>` can provide per-thread values, even though the `ThreadLocal` variable itself is usually held in a static final field.

~~~java
private static final ThreadLocal<String> USER =
        new ThreadLocal<>();
~~~

This prevents different threads from directly sharing **a single USER value** under the ThreadLocal mechanism, yet it carries risks:

- Thread pools reuse worker threads for different requests.
- If you forget `remove()` at the end of a request/test, the next request on **the same thread** may see the old value.
- Context is not automatically propagated properly to async tasks or other threads.
- Objects held by a thread-local can stay alive for a long time alongside the thread pool.
- In tests running sequentially on the same thread, state can still leak between tests.

Do not replace every `static String currentUser` with `static ThreadLocal<String> currentUser` and conclude that context isolation is completely solved. You must define scope and cleanup clearly.

### Sample Cleanup

~~~java
USER.set("Mai");
try {
    // Process within the proper scope of the context.
} finally {
    USER.remove();
}
~~~

This is an illustrative code snippet in the context of a class with a valid USER field. If any code uses an asynchronous boundary, intentional context propagation must be designed.

## 29. Singletons and Static Fields Can Still Make Tests Interdependent

A singleton held via a static field:

~~~java
class Registry {
    private static final Registry INSTANCE = new Registry();
    private final java.util.List<String> entries =
            new java.util.ArrayList<>();

    static Registry getInstance() {
        return INSTANCE;
    }
}
~~~

A single Registry instance is shared through `getInstance()`. Even though `entries` is an **instance field** (not static), it still creates **shared mutable state** because every caller uses **the same singleton object**.

Here is an important point:

> Dangerous shared state does not necessarily reside directly in a `static mutable field`. A `static final` reference to a **mutable singleton object** can also carry all the risks of test-order dependence.

If the goal is test isolation, sometimes you must replace the **singleton dependency** with an injectable instance, rather than merely changing the `entries` field from static to instance inside the same singleton.

## 30. Lifecycle of Static Caches, Registries, and Listeners

A static field can keep objects reachable longer than their business lifecycle:

~~~java
class GlobalListeners {
    static final java.util.List<Runnable> LISTENERS =
            new java.util.ArrayList<>();
}
~~~

Any component that registers a listener without removing it upon finishing leaves the static collection holding a reference to the callback, and potentially holding onto all objects that the callback references.

Consequences may include:

- Increased memory retention in long-running applications.
- Callbacks from old screens/requests being invoked again.
- New tests observing callbacks created by older tests.
- A plugin's class loader may not be released because it is still referenced by state outside the plugin.
- Sensitive data may persist longer than expected in the object graph.

### Designing Intentional Cleanup

Consider having the registration method return a handle:

~~~java
AutoCloseable subscription = bus.subscribe(listener);
try {
    // Use the subscription.
} finally {
    subscription.close();
}
~~~

This is **illustrative API code**, without assuming a pre-existing `bus` class. `close()` must actually remove the listener or close the resource according to the contract.

In tests, you can create **a new bus instance** for each test instead of a shared static registry. This lets you manage the lifecycle by test scope without needing a global `clearAllListeners()`.

## 31. Static Initialization Can Cause Unwanted Side Effects

A static field initialized with I/O or a method with side effects:

~~~java
class Config {
    static final String MODE = loadFromEnvironment();

    static String loadFromEnvironment() {
        return System.getProperty("mode", "default");
    }
}
~~~

`MODE` is computed when **the class is initialized**, not necessarily re-reading the property each time. If test A uses Config first and then test B changes the system property, test B may still see the old MODE.

This causes **timing dependence**:

- Which test touches the class first?
- Under which environment settings was Config initialized?
- Does a test expect the static initializer to run again?

Normally, **class initialization does not run again for each test method** on the same runtime class. To vary configuration flexibly, use an instance configuration/service with an explicit lifecycle; do not rely on changing the environment to "re-trigger" a static final initializer.

### Do Not Force Class Initialization to Fail

A static initializer throwing an unchecked exception can cause an `ExceptionInInitializerError` on the first initialization attempt; the runtime class may then remain in an erroneous initialization state and trigger `NoClassDefFoundError` on subsequent uses. Therefore, a test that pushes a static initializer into an error state can severely affect later tests in the same runtime. Separate processes or design explicit initialization when failure isolation needs to be controlled.

## 32. What Is the Harm in Optimizing Tests by Using Static Global State as a "Place for Fakes"?

An easy-to-write tactic:

~~~java
static FakeDatabase database = new FakeDatabase();
~~~

Test A populates data, and test B reuses it. This may make tests run fast at first, but:

- Tests no longer set up the data they need themselves.
- Any test running beforehand can alter the result.
- When test A fails, cleanup may not run.
- Tests running in parallel can trample over each other's data.
- A growing number of fixtures makes tests hard to understand.
- Test runner sharding/reordering breaks the assumption that "A always runs before B".

Better:

~~~java
FakeDatabase database = new FakeDatabase();
Service service = new Service(database);
~~~

Create the appropriate dependency for **each test** or **each scenario that has an explicit lifecycle**. If creating a real database is too expensive, you can consider a container/process fixture with its own namespace, database transaction rollbacks, or isolated schemas, without forcing tests to depend on each other's state.

## 33. Method for Investigating a Flaky Test Suspected to Be Caused by Static State

### Step 1 — Record the Symptoms

Which test passes alone but fails when running the suite? Does it change with order, speed, or parallel execution?

### Step 2 — List Shared State

Look for mutable `static` fields, `static final` fields referencing mutable collections/singletons, process system properties, environment wrappers, caches, random generators, clocks, and global registries. Also check databases/files if applicable.

### Step 3 — Identify Where It Is Written and Read

For each piece of state, record:

| State | Who writes? | Who reads? | Scope | Cleanup? |
| --- | --- | --- | --- | --- |
| `Discount.percent` | Discount test | Calculator/default test | JVM class runtime | Not yet |
| `Registry.EVENTS` | Subscriber/test | Event assertion | Static singleton | Possibly missing |
| `System.property` | Test setup | Config loader | Process | Possibly missing |
| Clock | Runtime | Deadline logic | External clock | Needs injection |

### Step 4 — Minimal Reproduction

Run the failing test **individually**, then run it after a suspected test in the same process. If changing the order changes the outcome, trace the writes to shared state.

### Step 5 — Add Invariants and Fixtures

Clearly define the test's initial state without relying on whatever ran before it. Only use temporary resets when refactoring is not yet possible.

### Step 6 — Choose to Fix the Root Code

Prefer passing dependencies/parameters, creating separate objects, using immutable configs, or clarifying the lifecycle. For unavoidable shared state, protect concurrency and establish an isolation strategy.

### Step 7 — Run Regression

Try multiple orders, run the suite, and run in parallel to the extent the project supports. Ensure the test does not affect other tests and does not merely flip from FAIL to PASS in one specific order.

## 34. Misconceptions to Avoid

| Misconception | Why is it wrong? | Correct mindset |
| --- | --- | --- |
| "Static data lives inside each object." | It belongs to the runtime class. | Draw class-level state separately. |
| "`static final List` is immutable." | The reference is final, while the List is still mutable. | Distinguish final from deep immutability. |
| "`private static` cannot be modified by another test." | Public methods can still modify the field. | Inspect all update paths. |
| "Putting reset in `@BeforeAll` is enough." | Subsequent test methods still write to the shared state. | Per-test isolation. |
| "`@BeforeEach` makes parallel tests safe." | Two resets can interleave. | Avoid shared mutable state or lock/isolate. |
| "Using `AtomicInteger` prevents tests from leaking into each other." | Atomics only solve concurrent updates. | Separate instances/scopes. |
| "`volatile++` is atomic." | `++` is still read–modify–write. | Use an atomic operation/lock. |
| "Synchronized is equivalent to reset." | A lock does not restore state to its initial value. | Isolation is a different problem. |
| "A new test method instance means fresh production static state." | Static belongs to the production runtime class. | Understand test lifecycle vs. class lifecycle. |
| "A new JVM resets the database too." | DB and external resources are not part of JVM state. | Clean up/namespace external state. |
| "Changing a system property re-runs static final Config." | Static initialization typically runs once per runtime class. | Inject config explicitly. |
| "A singleton without static mutable fields is clean." | The singleton object still has mutable instance fields. | Inspect the object graph. |
| "ThreadLocal gives every request a new object." | Thread pools reuse threads. | Cleanup and context propagation. |
| "One class with a given name has only one static state across the JVM." | Class loaders can define multiple runtime classes. | Consider class identity. |
| "The test only fails on CI, so CI is broken." | Order, timezone, CPU, and parallelism can expose hidden dependencies. | Reproduce and trace shared state. |
| "Adding `Thread.sleep` fixes flaky tests." | Timing does not establish proper synchronization. | Fix invariants/coordination. |
| "Static cache is always good because it reuses objects." | It brings stale data, memory retention, and hidden coupling. | Manage scope/lifecycle/eviction. |
| "Never use static methods in testable code." | Static pure methods are still easy to test. | Avoid shared mutation, do not ban syntax. |

## 35. Exercise 1 — Find the Dependent Test

Given:

~~~java
class Flags {
    static boolean enabled;
}

static void testA() {
    Flags.enabled = true;
}

static void testB() {
    if (Flags.enabled) {
        throw new AssertionError("expected disabled");
    }
}
~~~

**Question:** Running `testB` alone can pass; why can running it after `testA` fail?

**Answer:** `Flags.enabled` is a static mutable field. `testA` sets its value to true and does not reset it, so `testB` reads true when sharing the same runtime class. Suggestion: move flags into a separate instance configuration for each scenario, or reset at boundaries if legacy tests run sequentially.

This is an **illustrative code snippet**; the static methods need to be placed inside a valid class.

## 36. Exercise 2 — Is `static final` Really a Constant?

~~~java
class Store {
    static final java.util.List<String> ITEMS =
            new java.util.ArrayList<>();
}
~~~

One test executes `Store.ITEMS.add("A")`. Another test calls `Store.ITEMS.size()`.

**Answer:** It can read 1 even though the field has `final`. `final` only prevents `ITEMS` from having its reference reassigned; it does not prevent ArrayList mutation. You can move the state into an injected Store instance, or use a snapshot API with a clear lifecycle/isolation.

## 37. Exercise 3 — Does Atomic Solve Everything?

~~~java
class Metrics {
    static final java.util.concurrent.atomic.AtomicInteger HITS =
            new java.util.concurrent.atomic.AtomicInteger();
}
~~~

Two sequential tests: test A increments by 10, and test B increments by 1 and asserts `HITS.get() == 1`.

**Answer:** Test B may observe 11. `AtomicInteger` guarantees atomic updates, not automatic resets between tests. If you want to count within each scenario, use a dedicated Metrics instance (which can own its own AtomicInteger) rather than a global static.

## 38. Exercise 4 — Change the API to Eliminate Static Discount Dependence

Initially:

~~~java
class Pricing {
    static int discountPercent;

    static int calculate(int amount) {
        return amount - amount * discountPercent / 100;
    }
}
~~~

Choose one of the two designs:

**A. Pure function**: `calculate(int amount, int discountPercent)` with validation.

**B. Instance calculator**: `new PriceCalculator(new PricingPolicy(20))` and `finalPrice(amount)`.

Testing requirements:

- Price 100, 0% discount → 100.
- Price 100, 20% discount → 80.
- Changing the policy of the second calculator does not alter the first calculator's result.
- Negative input data or a percent outside `0..100` is rejected according to the contract.

## 39. Exercise 5 — Find the Missing Cleanup

A test runs:

~~~java
System.setProperty("mode", "new");
assertSomething();
~~~

If the assertion throws an exception, a cleanup statement placed **after** the assertion may not run. Save the previous value and use `try/finally` to restore the property regardless of whether the assertion succeeds or fails. Explain why this measure is still insufficient if other tests run in parallel using the same key.

## 40. Exercise 6 — Choosing Static State in Design

Decide between static/instance/injected state for the following scenarios:

| Scenario | Preferred approach |
| --- | --- |
| An immutable constant `MAX_RETRIES` | `public static final` if it is an appropriate API constant |
| Number of items in a Cart | Instance field of Cart |
| Dedicated counter per test scenario | Separate Counter object |
| Process-level, multi-threaded metrics counter | Shared service/counter with atomic or lock and explicit lifecycle |
| User name for each request | Request-scoped context/dependency, not global static |
| Cache keyed by tenant with expiration | Managed cache service with proper keys and lifecycle |
| Time source for deadline testing | Inject `Clock` |
| Shared immutable lookup table | Static immutable collection if appropriate |
| Event listeners per screen/test | Event bus instance or managed registry with cleanup |
| Mutable global singleton session | Usually needs scope and ownership redesign |

## 41. Self-Assessment Checklist

- [ ] I know that a static field is tied to the runtime class and is not recreated for each instance.
- [ ] I distinguish a static constant from a static mutable field and a static final mutable reference.
- [ ] I understand hidden coupling through global state.
- [ ] I can reproduce test-order dependence in `StaticTestOrderDemo`.
- [ ] I know why a test that passes alone can fail in a suite.
- [ ] I know that resetting at the start/end of a test is only a conditional measure.
- [ ] I do not assume `@BeforeEach` automatically makes parallel tests safe with the same static field.
- [ ] I know that the test object instance lifecycle does not determine the production static state lifecycle.
- [ ] I know that `AtomicInteger` handles atomic updates but does not create test isolation.
- [ ] I know that `volatile` does not make `++` atomic.
- [ ] I know that a static mutable List/Map/cache still carries risks of races and state leakage.
- [ ] I understand that a singleton instance can hold shared mutable instance fields.
- [ ] I know how to choose instance-owned state or constructor DI to isolate tests easily.
- [ ] I know how to use pure functions or immutable policies when appropriate.
- [ ] I know how to inject `Clock` to avoid depending on real time in tests.
- [ ] I know how to preserve and restore system properties properly in `finally`.
- [ ] I know the limitations of `ThreadLocal` in thread pools.
- [ ] I can explain memory retention caused by static references.
- [ ] I know that class loaders can create separate static states for classes with the same name.
- [ ] I can identify writers, readers, scope, and cleanup for a shared resource.
- [ ] I know to re-test across multiple orders and parallel mode to verify a solution.
- [ ] I distinguish test-order dependence errors from external issues such as DB/network/clock.
- [ ] I can run the Java 17+ examples and explain the stdout of each example.

**Conclusion:** `static` is not bad, and static pure methods/constants remain useful. The major risk lies in **mutable static state shared across multiple components or multiple tests**, which makes testing dependent on execution order, timing, and hard-to-see side effects. Constrain mutable state to its proper owner and lifecycle, prefer explicit dependencies and dedicated fixtures, use synchronization when concurrency is required, and treat resetting/cleaning up global state as a limited measure. A reliable test must **set up its own required conditions, verify behavior, and leave no state behind that affects other tests**.
