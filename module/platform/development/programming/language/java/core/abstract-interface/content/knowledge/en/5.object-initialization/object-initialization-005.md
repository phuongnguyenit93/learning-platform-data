# Risks of Calling Overridable Methods in Java Constructors

## 1. The Core Problem

In Java, a constructor is responsible for bringing an object into a valid state before external code begins using it. However, **if a superclass constructor calls an overridable instance method**, Java still performs **dynamic dispatch** to the overridden method in the subclass, even though the subclass constructor **has not finished yet**, and even before the subclass's field initializers **have run**.

A common consequence: the overriding method reads subclass fields while they still hold their **default values** (`null`, `0`, `false`). The result can be invalid state, incorrect logs, a `NullPointerException`, violation of object invariants, or hard-to-reproduce behavior.

The most important practical rule:

> **Do not call overridable methods on `this` while a constructor is running, including indirect calls through another method.** Complete initialization first, and only then execute polymorphic extension steps.

This issue is especially common with **abstract classes**, because an abstract class's constructor still runs when a subclass object is created; an `abstract` method declared in the superclass can be called directly from that constructor and execute in the subclass while the subclass has not yet finished initializing.

## 2. Why Can This Happen? Initialization Order Combined with Polymorphism

When executing `new Derived()` where `Derived extends Base`, the JVM creates a single object whose actual runtime type is `Derived`, rather than first creating an independent `Base` object and replacing it later. Memory for the instance fields of the **entire** object is allocated up front and initialized to default values.

In the standard inheritance case, without complex `this(...)` calls:

1. **Memory allocation** for the `Derived` object and assignment of default values to instance fields across the entire inheritance hierarchy: `null` for references, `0` for numeric types, and `false` for `boolean`.
2. **Follow the constructor chain** from the subclass up to `super(...)`; the constructor of the highest class runs first. For each class, after the superclass constructor completes, that class's instance field initializers and instance initializer blocks run in the order they appear in code, and then that class's constructor body executes.
3. While inside the **`Base` constructor**, the fields of `Derived` have not yet run `Derived`'s initializers or `Derived`'s constructor body.
4. However, if `Base` calls an overridable instance method, Java uses the **actual runtime type of the object** to select the override, so execution can jump straight into `Derived.method()`.
5. Only after the `Base` constructor returns do `Derived`'s field initialization and constructor body continue.

This does not contradict the rule that `super(...)` runs first: **constructor order** and **override selection mechanism** are two separate rules. Calling `super(...)` determines how the superclass part is initialized; it does not disable virtual dispatch.

Default values can be observed inside an override even when a subclass field declares an initializer at its point of definition, such as `private String name = "Đã sẵn sàng";`. That assignment is executed **after** the superclass constructor finishes.

Note: static initialization is a separate class-level mechanism and does not alter the hazard rule for instance fields in this example. A constructor that calls `this(...)` delegates to another constructor in the same class; despite ordering variations, the key invariant remains unchanged: **do not assume the subclass portion has finished initializing while superclass code is running**.

## 3. Java 17+ Example Reproducing the Bug and the Fix

The following example places both the unsafe case and the safe design into **a single `Main.java` file**. First, the superclass constructor calls an `abstract` method and the override observes `null`. Then, the safe approach checks only the portion of state initialized by the superclass itself, and runs the subclass hook after all constructors have completed.

```java
import java.util.Objects;

// UNSAFE APPROACH: constructor calls an overridable method.
abstract class HazardBase {
    protected HazardBase() {
        System.out.println("1. HazardBase(): đang khởi tạo");
        printStatus(); // Dynamic dispatch happens right here.
    }

    protected abstract void printStatus();
}

final class HazardChild extends HazardBase {
    // This initializer has NOT run yet when HazardBase() calls printStatus().
    private String status = "ready";

    @Override
    protected void printStatus() {
        System.out.println("2. Override: status = " + status);
    }

    String getStatus() {
        return status;
    }
}

// SAFE APPROACH: constructor only handles the superclass's own state.
abstract class SafeBase {
    private final String category;

    protected SafeBase(String category) {
        this.category = Objects.requireNonNull(category, "category");
        verifyBaseState(); // private, cannot be overridden.
    }

    private void verifyBaseState() {
        System.out.println("4. SafeBase(): category = " + category);
    }

    // Call the polymorphic method after the object has been fully created.
    public final void start() {
        System.out.println("6. start(): category = " + category);
        perform();
    }

    protected abstract void perform();
}

final class SafeChild extends SafeBase {
    private final String status;

    SafeChild() {
        super("TASK");
        status = "ready";
        System.out.println("5. SafeChild(): status = " + status);
    }

    @Override
    protected void perform() {
        System.out.println("7. perform(): status = " + status);
    }
}

public class Main {
    public static void main(String[] args) {
        HazardChild hazard = new HazardChild();
        System.out.println("3. Sau new: status = " + hazard.getStatus());

        SafeChild safe = new SafeChild();
        safe.start();
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 Main.java
java Main
```

Exact output:

```text
1. HazardBase(): đang khởi tạo
2. Override: status = null
3. Sau new: status = ready
4. SafeBase(): category = TASK
5. SafeChild(): status = ready
6. start(): category = TASK
7. perform(): status = ready
```

**Analysis of lines 1–3:**

- In `new HazardChild()`, the `HazardBase()` constructor runs first; it prints line 1 and then calls `printStatus()`.
- `printStatus()` is an abstract method in the superclass that is implemented by `HazardChild`. The call selects `HazardChild.printStatus()` based on the actual runtime type of the object.
- When the override reads `status` on line 2, the `"ready"` assignment in the subclass initializer has not been executed yet. The `String` field is currently `null`.
- After the superclass constructor returns, `HazardChild`'s initializer runs and assigns `status = "ready"`. Line 3 therefore prints `ready`.
- The `final` keyword on the `HazardChild` class does not prevent the issue, because overriding already occurred **between `HazardChild` and `HazardBase`**.

**Analysis of lines 4–7:**

- `SafeBase()` only assigns its own field and calls `verifyBaseState()`, which is `private`, so this method cannot be overridden by subclasses.
- `SafeChild()` proceeds to initialize `status` and finishes. In `main`, only **after `new SafeChild()` returns** does the program call `safe.start()`.
- `start()` is `final`, keeping the execution order fixed; it calls the polymorphic `perform()` hook once `status` is already `"ready"`. At this point, extending behavior through the subclass is appropriate.
- `final` only prevents direct overriding of the `start()` method; it **does not by itself make every call inside `start()` safe in a constructor**. Safety here comes from calling `start()` after initialization.

The example uses `System.out.println` to observe the exact order, so it does not depend on thread scheduling or non-deterministic factors.

## 4. Real-World Bugs Can Be Worse Than a `null` Value

### 4.1. `NullPointerException`

An overriding method might assume that a subclass field has already been assigned:

```java
// Illustrative snippet inside a subclass:
private String configuration = "production";

@Override
protected void printStatus() {
    System.out.println(configuration.length());
}
```

If the superclass constructor calls `printStatus()` too early, `configuration` is still `null`. Calling `configuration.length()` throws a `NullPointerException` and object creation fails. Because this is only an illustrative snippet inside a hypothetical subclass, it is not a standalone Java file; the `Main.java` example above is the directly runnable program.

### 4.2. Default Values That Look Valid

For integer or boolean fields, the bug sometimes **does not throw an exception**, and instead silently computes the wrong result:

```java
// Illustrative snippet inside a subclass:
private int retryLimit = 3;
private boolean enabled = true;

@Override
protected void printStatus() {
    System.out.println("retryLimit=" + retryLimit
            + ", enabled=" + enabled);
}
```

If called too early, the override will see `retryLimit=0, enabled=false`. Because `0` and `false` are type-valid values, the bug can slip into business decisions or be recorded as corrupted data without raising an immediate error.

### 4.3. When an Early Call Also Lets `this` Escape

If an override is called from a constructor and then registers `this` with a listener or registry, or schedules a task holding a reference to the object, other code can use the object before initialization finishes. However, **early dispatch does not automatically mean the reference has been published**. Two separate mechanisms must be checked: which method runs too early, and whether the object escapes from the constructor.

The article “Avoiding letting this escape before object initialization completes” focuses specifically on callbacks, threads, safe publication, and happens-before relationships.

## 5. Indirect Calls That Are Often Overlooked

Simply searching for an `overridableMethod();` statement inside a constructor is not enough. You must inspect the **entire call chain originating from the constructor**.

| Code Pattern in Constructor | Why It Needs Checking |
| --- | --- |
| `initialize();`, where `initialize()` in turn calls `hook()` | The constructor does not call `hook()` directly, yet it still reaches the override. |
| `setValue(x);` with a non-`final` setter | A subclass can override the setter and read incomplete state. |
| `System.out.println(this);` or `"obj=" + this` | Converting the object to a string can invoke an overridden `toString()`. |
| `Objects.toString(this)`, logging objects, debugger display | Operations that seem purely observational can invoke `toString()`. |
| `registerListener(this)` | The object may be called back via a callback while the constructor is still running. |
| `executor.execute(() -> useFields())` or creating a thread that uses `this` | The asynchronous task may run early and read uninitialized state. |

Several details need to be distinguished:

- Calling `super.method()` from a subclass selects the superclass implementation for **that specific call**, but the superclass method can still go on to call another virtual hook. `super` does not guarantee that the entire call chain is free of dynamic dispatch.
- `private` methods cannot be overridden; `final` instance methods cannot be overridden; `static` methods do not dispatch like instance methods (reusing the same name may be *hiding*). However, **a `private` or `final` method can still call an overridable method**, so the calls inside it must be inspected.
- `getClass()` and the actual runtime type of `this` are already the subclass type while executing inside the superclass constructor. You should not infer that the object “is currently the superclass” during that phase.
- A method called from a constructor can also access subclass state **via a method reference, lambda, callback, or listener**. The hazard comes from the timing of execution and object access, not merely from the syntactic form.

## 6. Safer Design Approaches

### Approach A — Let the Constructor Complete Only Its Own Class's Data

A superclass constructor should perform work that can be determined entirely from its parameters and the superclass's own initialized fields: validating arguments, assigning fields, establishing invariants, or calling carefully controlled `private`/`final` helpers.

Example:

```java
// Illustrative snippet of a constructor that only handles internal state.
abstract class ConnectionBase {
    private final String endpoint;

    protected ConnectionBase(String endpoint) {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("endpoint bắt buộc");
        }
        this.endpoint = endpoint;
    }

    protected final String endpoint() {
        return endpoint;
    }
}
```

There is no need to ask the subclass whether `endpoint` is valid through an overridable hook. If the data is a constructor parameter, validating it directly where the data is received is usually simpler and safer.

### Approach B — Move Extension Points to a Method Called After `new`

The Template Method pattern can maintain a clear extension workflow, provided the template method is called after the subclass constructor has finished running:

```java
// Illustrative snippet; concrete classes will provide executeStep().
abstract class Job {
    public final void run() {
        checkInputs();
        executeStep();
    }

    private void checkInputs() {
        System.out.println("Đã kiểm tra");
    }

    protected abstract void executeStep();
}
```

The proper usage flow is to finish constructing a concrete `Job` **and then** call `run()`. Do not call `run()` inside `Job`'s constructor, because it still leads to the polymorphic `executeStep()`. Even when there are multiple levels of indirect calls, a public post-construction entry point remains an easier design boundary to control.

### Approach C — Mandatory Startup Step Required: Use a Factory with Explicit Post-Initialization

When the application requires starting the object immediately upon creation, you can place a factory method in control of the ordering: construct the object completely first, and only then invoke the startup step.

```java
// Standalone illustrative snippet of the factory pattern, independent of the Main example.
final class Session {
    private final String user;
    private boolean started;

    private Session(String user) {
        this.user = java.util.Objects.requireNonNull(user);
    }

    public static Session open(String user) {
        Session session = new Session(user);
        session.startInternal();
        return session;
    }

    private void startInternal() {
        started = true;
    }

    public String status() {
        return user + ":" + (started ? "started" : "new");
    }
}
```

For classes designed for inheritance, a factory can also finish creating a concrete instance and then call the required hook after the constructor returns. Reference publication and construction paths must still be controlled: if the object is exposed to other code **before** the post-initialization step, the factory has not fully solved the problem. If startup can fail, clearly define whether the failed object may be returned or must be cleaned up.

### Approach D — Use Composition If Polymorphism During Initialization Is Unnecessary

Instead of having the superclass constructor rely on an overridden subclass method, pass an already-ready dependency into the constructor or move the varying logic into a collaborator object. When dependencies can be validated and supplied from the outside, initialization code does not need to dispatch on an incomplete `this`.

Note: a passed-in dependency could still invoke a callback back to `this` if the constructor supplies that reference. Composition narrows the design risk, but does not automatically eliminate every bug if `this` is still allowed to escape prematurely.

## 7. Common Misconceptions to Avoid

**“Constructors cannot be overridden, so an override cannot be called inside one.”** It is true that constructors do not participate in overriding, but **instance methods called by a constructor** can still be virtual methods and be dynamically dispatched.

**“The subclass declared an initializer, so the field is guaranteed to have a value.”** False. Subclass field initializers only run during the subclass initialization phase, after the superclass constructor returns.

**“Making the field `final` is enough.”** False. `final` on a field prevents reassignment after it has been initialized (according to Java's assignment rules); it does not make the subclass field assignment run any earlier. An override called from the superclass constructor can still observe the default value.

**“Making the constructor `private` or making the template method `final` solves it.”** You must examine where dispatch actually occurs: a `private` helper cannot be overridden, but that helper might call a virtual hook. `final` on a template method only prevents overriding the template method itself; if the template method calls another overridable method, the hazard remains.

**“This bug only happens with abstract methods.”** No. Any **overridable instance method** called from a constructor (including concrete methods in the base class or `toString()`) can resolve to a subclass override.

**“Seeing `null` proves Java has not allocated the subclass object yet.”** False. The entire object has already been allocated with default values; only the subclass-specific initialization has not yet executed.

**“I should add `super.printStatus()` inside the override to fix it.”** Unreliable. The issue is **when the call happens**; calling the superclass method as well does not guarantee that subclass state is ready. You must change the execution point or redesign the initialization relationship.

## 8. Code Review and Testing Checklist

When reviewing an abstract class or any class open to inheritance:

1. **Read the constructors and the `this(...)`/`super(...)` chains**. Record every instance method called, including calls through helpers.
2. **Classify each called method:** `private`, `final`, `static`, or overridable? For `private`/`final` helpers, inspect inside them to see if they call any hooks or publish `this`.
3. **Inspect subclass overrides:** which fields do they read, and when are those fields assigned? Distinguish default values from values assigned by field initializers or constructors.
4. **Look for escape paths for `this`:** callbacks, listeners, registry registrations, executors, lambdas, or starting threads.
5. **Move polymorphic work to a post-initialization phase**, or fold it into constructor input data and helpers that only operate on already-initialized state.
6. **Test states that expose the bug:** `null` reference fields, numeric fields equal to `0`, `false` booleans, and constructors with multiple inheritance levels. Also verify cases where no exception is thrown but the output is wrong.
7. **Verify ordering with a small program** like the `Main.java` example; distinguish logs from the superclass constructor, subclass initializers, and post-`new` logic.

If you use static code analysis tools, a warning equivalent to “constructor invokes overridable method” is a signal to inspect. Not every such call causes an immediately visible bug, yet as subclasses and overrides are added in the future, the risk remains; public extensible APIs in particular should avoid this design.

## 9. Self-Check Exercises

**Exercise 1.** Suppose `Base()` calls `getCount()` and the subclass overrides `getCount()` to return `count`, while `count` is declared as `private int count = 10;`. While `Base()` is running, what can the call return? **Answer: `0`**, because the subclass initializer has not run yet; only after `new` finishes does the value become `10`.

**Exercise 2.** Is replacing `getCount()` with a `private int getCount()` helper in the superclass itself enough to eliminate dispatch to a subclass override? **Yes, for that helper call itself**, because a `private` method cannot be overridden. However, you must still check whether the helper calls an overridable method or exposes `this`.

**Exercise 3.** If the superclass has a `public final void initialize()` method that calls `configure()`, which is `protected abstract`, is it safe to call `initialize()` in the superclass constructor? **No.** Although `initialize()` is `final`, it still executes `configure()` polymorphically. Move the `initialize()` call to after `new` completes.

**Exercise 4.** Should all instance methods be prohibited in constructors? **Not necessary.** A constructor can call non-overridable helpers that work with already-initialized state and do not expose `this`. The rule is to avoid calling logic that could access unready subclass state or give external code an opportunity to observe an incomplete object.

## 10. Key Takeaways

- A superclass constructor executes before subclass-specific initialization, yet **dynamic dispatch already operates based on the object's actual runtime type** as soon as the superclass constructor runs.
- Uninitialized subclass fields can be observed through an override: **`null`, `0`, `false`** instead of the values the developer expects.
- Calling an overridable method **directly or indirectly** from a constructor can be dangerous; `abstract` methods, `toString()`, setters, and hooks inside a `final` method all need to be checked.
- Keep constructors focused on the state they directly control; move polymorphic hooks to methods called **after the entire `new` process completes**. Do not publish `this` prematurely.
