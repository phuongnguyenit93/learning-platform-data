# Referencing Instance Methods on an Existing Object in Java

## 1. When to use `existingObject::instanceMethod`?

In Java, a **method reference** lets you pass a matching method where a **functional interface** is expected, instead of writing a lambda that merely calls that method. This lesson covers **referencing an instance method on an existing object** (*bound instance method reference*):

~~~java
existingObject::instanceMethod
~~~

**`existingObject` is an expression that produces or points to the receiver** — the object that will receive the call. When creating the method reference, Java evaluates the receiver expression and **binds that receiver** to the reference. When the functional interface is invoked later, Java calls the method on the bound receiver, passing the arguments provided by the SAM.

For example, if you already have a `Printer printer`:

~~~java
Consumer<String> output = printer::print;
~~~

then the idea is equivalent to:

~~~java
Consumer<String> output = text -> printer.print(text);
~~~

These two snippets are illustrative only in a context where `Printer.print(String)` is defined and `java.util.function.Consumer` is imported. With a final/effectively final local variable `printer`, the lambda form usually has the same behavior when invoked. However, the two forms are **not equivalent in every situation**, especially when the receiver is an expression with side effects or may return `null`; we will examine this specifically in a later section.

The main benefit is concise syntax with a clear call target:

- `System.out::println` — sends each value to the existing `PrintStream` object.
- `formatter::format` — uses an already-configured formatter.
- `cache::get` — retrieves a value from a cache instance when the signature matches.
- `listener::onEvent` — uses a specific object as a callback.

A method reference **does not call the method immediately at declaration time**. It only creates behavior that can be invoked later. Only **the expression identifying the receiver** is evaluated when creating the method reference, without waiting for the callback invocation.

## 2. The functional interface determines the call signature

A method reference requires a functional interface as its **target type**; the compiler uses the single abstract method (SAM) to determine the expected parameters and return type.

| Target type | SAM | Bound reference example | Condition |
| --- | --- | --- | --- |
| `Runnable` | `void run()` | `service::refresh` | `refresh()` can be called with no arguments |
| `Supplier<String>` | `String get()` | `service::status` | `status()` returns a compatible String |
| `Consumer<String>` | `void accept(String)` | `printer::print` | Receiver has a matching `print(String)` method |
| `Function<String,Integer>` | `Integer apply(String)` | `parser::parse` | `parse(String)` returns a compatible int/Integer |
| `Predicate<Order>` | `boolean test(Order)` | `policy::allows` | `allows(Order)` returns a compatible boolean/Boolean |
| `BiFunction<A,B,R>` | `R apply(A,B)` | `service::combine` | `combine(A,B)` returns a compatible R |

The names `service`, `printer`, `parser`, `policy`, `Order`, `A`, `B`, `R` in the table are **signature illustrations**, not declared variables/classes ready to compile.

The receiver object **does not occupy a parameter** in the SAM of a bound reference: it is already bound. For example, `printer::print` with `print(String)` corresponds to `Consumer<String>`: the callback only needs to pass `String`.

If a method returns a value while the SAM returns `void`, Java can discard the return value when the method reference is compatible with the SAM's contract. Even so, you should choose a target type that expresses the true intent: `Consumer` for an action, `Function` for a transformation with a result, `Supplier` for providing a value.

**Do not write `var callback = printer::print;`** without an additional target type: a method reference is not an expression with an independent type from which `var` can infer. Declare `Consumer<String>` or pass it directly to a method accepting a typed functional interface.

## 3. Complete Java 17 example: binding a configured formatter

Suppose a formatter class has its own configuration: a prefix before the product name and a price threshold considered expensive. We want to pass **the exact same instance** into a data processing pipeline.

Create the file **BoundReferenceBasics.java**:

~~~java
import java.util.List;
import java.util.function.Function;
import java.util.function.Predicate;

record Product(String name, int price) {}

final class ProductFormatter {
    private final String prefix;
    private final int expensiveFrom;

    ProductFormatter(String prefix, int expensiveFrom) {
        this.prefix = prefix;
        this.expensiveFrom = expensiveFrom;
    }

    String format(Product product) {
        return prefix + product.name() + " (" + product.price() + ")";
    }

    boolean isExpensive(Product product) {
        return product.price() >= expensiveFrom;
    }
}

public class BoundReferenceBasics {
    public static void main(String[] args) {
        ProductFormatter formatter =
                new ProductFormatter("Product: ", 100);

        Function<Product, String> describe = formatter::format;
        Predicate<Product> expensive = formatter::isExpensive;

        List<Product> products = List.of(
                new Product("Pen", 25),
                new Product("Book", 120),
                new Product("Backpack", 180)
        );

        List<String> result = products.stream()
                .filter(expensive)
                .map(describe)
                .toList();

        result.forEach(System.out::println);
    }
}
~~~

Compile and run with **JDK 17 or later**:

~~~bash
javac -encoding UTF-8 BoundReferenceBasics.java
java BoundReferenceBasics
~~~

Stdout:

~~~text
Product: Book (120)
Product: Backpack (180)
~~~

**Explanation following the data flow:**

1. `formatter` is **an existing object**, holding `prefix="Product: "` and `expensiveFrom=100`.
2. `formatter::format` creates behavior of the form `Product → String`, assigned to `Function<Product,String>`.
3. `formatter::isExpensive` creates behavior `Product → boolean`, assigned to `Predicate<Product>`.
4. `filter(expensive)` removes the product priced at 25; `map(describe)` produces strings from the remaining two products.
5. `System.out::println` is a method reference bound to the `PrintStream` object obtained from `System.out` when the expression is created. In the `forEach` call, it is a matching `Consumer<String>` callback.

**Why choose a bound method reference?** The formatting rule and price threshold are encapsulated inside the `formatter` instance. The Stream steps do not need to know how to format or read the threshold; they simply invoke the behaviors the object provides. When changing configuration, you create or pass a different formatter instead of duplicating lambdas in multiple places.

This lesson illustrates how to represent callbacks; it does not recommend using `int` prices for real-world payment systems. Monetary systems must define units, numeric limits, and appropriate rounding rules.

## 4. Distinguishing bound, unbound, and static method references

Java has several forms of method references; you need to distinguish **who the receiver is** and **which parameters the SAM provides**.

| Form | Example | Receiver when callback runs |
| --- | --- | --- |
| `expression::instanceMethod` | `text::toUpperCase` | The `text` object already bound beforehand |
| `TypeName::instanceMethod` | `String::toUpperCase` | String object taken from the first SAM parameter |
| `TypeName::staticMethod` | `Integer::parseInt` | No instance receiver |
| `TypeName::new` | `StringBuilder::new` | Creates a new object via constructor |

With `String`, the following three examples show different signatures:

~~~java
String source = "java";

Supplier<String> bound = source::toUpperCase;
Function<String, String> unbound = String::toUpperCase;
Function<String, Integer> staticMethod = Integer::parseInt;
~~~

This is an **illustrative snippet** requiring `Supplier` and `Function` imports. Running it:

~~~text
bound.get()               → "JAVA"
unbound.apply("hello")    → "HELLO"
staticMethod.apply("42")  → 42
~~~

- `bound.get()` takes no parameters because it already has the `source` receiver.
- `unbound.apply("hello")` uses **"hello"** as the receiver when called. No specific String is fixed when writing `String::toUpperCase`.
- `Integer::parseInt` is a reference to a **static** method of `Integer`, so the input is a business parameter `String`, not a receiver.

A very intuitive comparison:

~~~java
String prefix = "ID-";
UnaryOperator<String> withBoundPrefix = prefix::concat;
BiFunction<String, String, String> withUnboundPrefix = String::concat;
~~~

The two lines above require importing `UnaryOperator` and `BiFunction`.

- `withBoundPrefix.apply("7")` returns **"ID-7"**; the `prefix` receiver is already bound.
- `withUnboundPrefix.apply("ID-", "7")` also returns **"ID-7"**, but the receiver is the **first parameter** of `BiFunction`.

**Note:** An expression `TypeName::method` can refer to a static method or an unbound instance method depending on the method kind and the overload compatible with the target type. Therefore, do not classify solely by the `TypeName::...` spelling; check the method definition and the SAM.

## 5. Receiver binding timing: the expression before :: is evaluated once

This is an important difference between a method reference on a **receiver expression** and a lambda that re-evaluates the receiver expression.

Consider:

~~~java
Runnable bound = factory.create()::run;
Runnable lambda = () -> factory.create().run();
~~~

This is an **illustrative snippet**, assuming `factory.create()` produces an object with `run()`.

- With `factory.create()::run`, Java calls **factory.create() immediately when evaluating the method reference** and binds the returned object. When `bound.run()` is called multiple times, the callback keeps using this same object.
- With `() -> factory.create().run()`, Java calls **factory.create() every time the lambda runs**; it may create multiple different objects.

Create the file **ReceiverEvaluationDemo.java** to observe the behavior:

~~~java
public class ReceiverEvaluationDemo {
    static int creations = 0;

    static class Task {
        private final int id;
        private int invocations;

        Task(int id) {
            this.id = id;
        }

        void execute() {
            invocations++;
            System.out.println("task " + id + " call " + invocations);
        }
    }

    static Task createTask() {
        creations++;
        System.out.println("create " + creations);
        return new Task(creations);
    }

    public static void main(String[] args) {
        Runnable bound = createTask()::execute;
        Runnable lambda = () -> createTask().execute();

        System.out.println("run bound:");
        bound.run();
        bound.run();

        System.out.println("run lambda:");
        lambda.run();
        lambda.run();
    }
}
~~~

Run:

~~~bash
javac ReceiverEvaluationDemo.java
java ReceiverEvaluationDemo
~~~

Stdout:

~~~text
create 1
run bound:
task 1 call 1
task 1 call 2
run lambda:
create 2
task 2 call 1
create 3
task 3 call 1
~~~

**Exact interpretation:**

- `createTask()::execute` causes `createTask()` to run **immediately when assigned** to `bound`, printing `create 1`. No call to `Task.execute()` has happened yet at that moment.
- Both calls to `bound.run()` use the same Task with id 1, so the counter increases from 1 to 2.
- `lambda` only stores the behavior to call `createTask()` later. Each `lambda.run()` creates a new Task with id 2 then id 3, and each Task executes only once.

This is why you cannot conclude that every `obj::method` is completely equivalent to `() -> obj.method()`: **where and when the receiver is evaluated** is part of the semantics, especially when the expression has side effects.

### 5.1. If the receiver is an existing local variable

With:

~~~java
Task task = createTask();
Runnable a = task::execute;
Runnable b = () -> task.execute();
~~~

This is an illustrative snippet in a class context having `Task` and `createTask()`. When `task` is a **final or effectively final** local variable, both callbacks invoke the same `task` object; the difference in evaluation timing of a **complex expression** usually no longer matters. However, a bound reference still follows the rule of evaluating the receiver at creation time; meanwhile, a lambda also obeys local variable capture rules.

With a mutable field `this.currentTask`, it is different: `this.currentTask::execute` binds the receiver fetched **once**, whereas `() -> this.currentTask.execute()` reads the field again when the callback runs. If the field changes to another object after creation, the two callbacks may operate on different objects.

## 6. Null receiver: error occurs immediately when creating a bound method reference

An easy-to-miss bug is using a bound method reference on a null receiver.

~~~java
Printer printer = null;
Consumer<String> action = printer::print;
~~~

This is a **snippet intentionally causing a runtime error**, assuming `Printer` has `print(String)` and `Consumer` is imported. Evaluating `printer::print` throws a **NullPointerException immediately when creating the reference**, before `action.accept(...)` has a chance to run.

With a lambda:

~~~java
Printer printer = null;
Consumer<String> action = text -> printer.print(text);
~~~

With an effectively final local `printer`, **creating the lambda** can succeed; the **NullPointerException** occurs when `action.accept(text)` actually tries to call the method on null. The difference is **when the error occurs**.

In real APIs, if the receiver must exist, check it explicitly at the callback creation boundary:

~~~java
Objects.requireNonNull(printer, "printer");
Consumer<String> action = printer::print;
~~~

This illustrative snippet requires importing `java.util.Objects` and `Consumer`. An explicit check makes the message express the input precondition, but it does not mean the method reference handles null automatically.

**Do not confuse a null receiver with a null argument.** A bound receiver can be completely valid, yet `action.accept(null)` can still fail inside the **called method** depending on the contract of `print`, `format`, or `parse`.

## 7. The receiver is bound, but the object's internal state is not necessarily fixed

A method reference holds the receiver object; it **does not take a snapshot** of all fields of the object at creation time. If a field is mutated, subsequent method calls can see the new state.

Create the file **BoundStateDemo.java**:

~~~java
import java.util.function.Function;

final class MutablePrefixer {
    private String prefix;

    MutablePrefixer(String prefix) {
        this.prefix = prefix;
    }

    void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    String addPrefix(String value) {
        return prefix + value;
    }
}

public class BoundStateDemo {
    public static void main(String[] args) {
        MutablePrefixer prefixer = new MutablePrefixer("old-");
        Function<String, String> add = prefixer::addPrefix;

        System.out.println(add.apply("x"));

        prefixer.setPrefix("new-");
        System.out.println(add.apply("x"));

        MutablePrefixer replacement = new MutablePrefixer("other-");
        Function<String, String> other = replacement::addPrefix;
        System.out.println(other.apply("x"));
        System.out.println(add.apply("y"));
    }
}
~~~

Run:

~~~bash
javac BoundStateDemo.java
java BoundStateDemo
~~~

Stdout:

~~~text
old-x
new-x
other-x
new-y
~~~

Takeaways:

- `add` always stays bound to **the same `prefixer` instance**.
- Changing `prefixer.prefix` affects the result of later calls, because `addPrefix` reads the current state of the instance.
- Creating `replacement` does not change the receiver of `add`. `other` is a new callback bound to a different object.
- "Bound receiver" **does not mean the result is always fixed** or a pure function.

When you want a callback to return the same result regardless of configuration changes, you can use an immutable object or capture the needed configuration value and create a lambda based on that value. Decide between a **live state** or **snapshot state** policy based on business requirements.

## 8. Bound references still use virtual dispatch when needed

When the receiver has a superclass type but the actual instance is a subclass overriding the method, a bound method reference to an **instance method** executes according to normal Java dispatch rules.

Create the file **BoundDispatchDemo.java**:

~~~java
import java.util.function.Supplier;

class BaseService {
    String name() {
        return "base";
    }
}

class ChildService extends BaseService {
    @Override
    String name() {
        return "child";
    }
}

public class BoundDispatchDemo {
    public static void main(String[] args) {
        BaseService service = new ChildService();

        Supplier<String> reference = service::name;
        Supplier<String> lambda = () -> service.name();

        System.out.println(reference.get());
        System.out.println(lambda.get());
    }
}
~~~

Run:

~~~bash
javac BoundDispatchDemo.java
java BoundDispatchDemo
~~~

Stdout:

~~~text
child
child
~~~

**Why?** `service` is a variable with static type `BaseService`, while the actual object is `ChildService`. `name()` is an overridden instance method, so Java selects the `ChildService` implementation.

Do not confuse this with `super::name` inside a subclass: the `super::...` syntax has its own semantics for selecting the superclass implementation from a valid inheritance context. The topic of this lesson is **an existing receiver object**, so `service::name` uses regular instance dispatch.

**Note on overloaded methods:** If the receiver has multiple methods with the same name (for example `print(String)`, `print(int)`), Java uses the target type of the functional interface to select the matching overload. You cannot tell which exact overload `printer::print` refers to without knowing the target type.

## 9. Overloads and type inference: the target type decides the method

An object can provide multiple overloads:

~~~java
class Converter {
    String convert(String input) {
        return "str:" + input;
    }

    String convert(int input) {
        return "int:" + input;
    }
}
~~~

This is an **illustrative class definition**. You can write:

~~~java
Converter converter = new Converter();

Function<String, String> stringRule = converter::convert;
IntFunction<String> numberRule = converter::convert;
~~~

The snippet above requires importing `java.util.function.Function` and `java.util.function.IntFunction`. `stringRule.apply("a")` returns **"str:a"**, while `numberRule.apply(3)` returns **"int:3"**.

When Java cannot resolve a single overload from context, a compilation error for ambiguous reference occurs. The fix is to clarify the target type or write a lambda specifying parameter types when needed.

For example:

~~~java
Function<String, String> selected =
        (String input) -> converter.convert(input);
~~~

If the method receiving the callback is overloaded with two functional interfaces having similar signatures, a method reference/lambda may lack enough information to pick an overload at the outer call site. You can assign it beforehand to a typed variable or use an intentional cast, though avoid casting when the API can be designed with clearer method names.

**Generic method references:** Generic methods on a receiver can still be referenced when argument and result types match the SAM. Java performs type inference according to the target type; not every case can be inferred automatically, especially when overloads and generic bounds overlap. Check the specific compiler error rather than guessing.

## 10. Method references in Streams, callbacks, and behavior-accepting APIs

Three common scenarios:

### 10.1. Using configured state in a pipeline

~~~java
List<String> formatted = items.stream()
        .map(formatter::format)
        .toList();
~~~

This is an **illustrative snippet**, assuming `items` contains objects accepted by `formatter.format`. The behavior may have been configured via constructor or dependency injection. `map` only cares about the return value.

If `formatter.format` has side effects like mutating state or making network calls, the Stream can still execute, but it becomes harder to reason about, harder to parallelize, or unstable in performance. Do not assume that method reference syntax automatically makes behavior pure.

### 10.2. Registering a listener for a specific object

~~~java
Consumer<Event> handler = listener::onEvent;
eventBus.register(handler);
~~~

This is an **illustrative snippet**: the types `Event`, `eventBus`, `listener`, and the `register` method must be defined appropriately. An application can register a callback to run on future events; the reference binds the `listener` receiver at creation time.

If the listener needs to be unregistered, you should **keep the same callback object** `handler` and reuse it when calling `unregister(handler)`, according to the event bus contract. Creating a new method reference and assuming it has the same object identity as the old reference is unsafe: Java does not guarantee such stable object identity for lambdas/method references.

### 10.3. Interacting with standard APIs

~~~java
StringBuilder builder = new StringBuilder();
Consumer<String> append = builder::append;

append.accept("A");
append.accept("B");
System.out.println(builder); // AB
~~~

This is an **illustrative snippet** requiring `Consumer` import. `StringBuilder.append(String)` returns the `StringBuilder` itself, but `Consumer.accept` returns `void`, so the call's return value is ignored. The two callback invocations mutate the receiver's state and print **AB**.

This is useful when you want an intentional side-effecting action, but be aware of the discarded return type and the mutable object being updated. `StringBuilder` is not safe when multiple threads write concurrently to the same instance without coordination.

## 11. Capture, object lifecycle, and thread safety

A bound method reference can hold a **strong reference** to that object for as long as the callback is retained. If the callback is stored in a long-lived scheduler, event bus, or registry, the receiver can also remain referenced and not be garbage-collected as expected.

Some principles:

1. **Manage registration lifecycle:** store the created callback, unregister it at the right time, and check the listener mechanism's contract.
2. **Do not create callbacks just to compare with `==`:** the identity of method references is not guaranteed to be equal even when written identically as `obj::method`.
3. **Distinguish receiver from state:** a bound reference binds the object, but the object's field state can still change, as in the `MutablePrefixer` example.
4. **Synchronize access to mutable state:** when multiple threads invoke the same callback on a mutable object, protect the state with synchronization, atomic classes, immutable design, or an appropriate mechanism.
5. **Consider creation timing:** a reference on a receiver expression with side effects executes the expression at creation time; this affects logs, exceptions, resource opening, and expensive computations.
6. **Do not use bound references to hide complex dependencies:** if an API needs retries, transactions, or error control, the callback contract must express that.

A `counter::increment` callback is no safer than `() -> counter.increment()` if `increment` updates shared data without synchronization. The conciseness of a method reference is purely syntactic; side effects, thread safety, and error observability are still determined by the called method.

### 11.1. What if a static field receiver changes?

Suppose `Manager.current` is a static field pointing to an instance. The following two ways can differ:

~~~java
Runnable fixed = Manager.current::refresh;
Runnable dynamic = () -> Manager.current.refresh();
~~~

This is an **illustrative snippet**; the names must be declared appropriately. `fixed` binds the receiver read from `Manager.current` **at creation time**. `dynamic` reads `Manager.current` again **each time it is called**. If `current` changes, the two callbacks may invoke methods on two different instances. If `current` is null at the time `fixed` is created, creating the bound reference will throw a `NullPointerException`.

## 12. Common mistakes

| Mistake/misconception | Consequence | Correct understanding |
| --- | --- | --- |
| "`object::method` calls the method immediately" | Wrong prediction of side effects | Only the receiver is evaluated at creation; the method runs when SAM is called |
| "The receiver is the first parameter of the SAM" | Assigning the wrong target type | For a bound reference, the receiver is already bound; SAM parameters are method arguments |
| Confusing `obj::instanceMethod` with `Type::instanceMethod` | Mixing up bound and unbound, wrong parameter count | `Type::instanceMethod` uses the first SAM parameter as the receiver |
| Confusing `Type::staticMethod` with an unbound instance reference | Wrong receiver analysis | Static methods need no receiver |
| Thinking `factory.create()::run` and `() -> factory.create().run()` are always the same | Object creation timing and factory call count differ | Bound evaluates the receiver once; lambda evaluates it on every run |
| Creating a bound reference on a null receiver | `NullPointerException` at reference creation time | Check the receiver beforehand; distinguish lambda error timing |
| Thinking the receiver's entire state is "frozen" | Callback results change unexpectedly | The object is bound, mutable fields can still change |
| Not declaring a target type | `var f = obj::method` lacks a target type | Assign to a specific functional interface |
| Forgetting overloads | Method reference is ambiguous or selects an unexpected signature | Check the target SAM and overloads |
| Comparing two newly created references by identity | Cannot find the registered listener | Store and reuse a single callback variable |
| Using a method reference and assuming thread safety | Race condition, lost updates | Evaluate the receiver's state and synchronization |
| Keeping callbacks in a registry too long | Receiver may be kept alive longer than expected | Tie registration and unregistration lifecycles properly |

## 13. How to choose between a method reference and a lambda

Use **`object::method`** when:

- You already have the right instance to handle the work and want to pass its method;
- The target functional interface and method have compatible signatures;
- **Binding the receiver immediately at callback creation** matches your intent;
- The method name clearly expresses the action, keeping the code short and readable.

Use a **lambda** when:

- You need extra checks, conversions, error handling, or multiple statements before/after the call;
- You want to **re-read the receiver dynamically** on every execution;
- You need to adjust arguments or combine results from multiple methods;
- Writing a method reference makes it hard for readers to tell which method/receiver is chosen due to overloads.

Do not replace lambdas with method references mechanically. Verify equivalence in **receiver evaluation timing**, **`null`**, **overloads**, **side effects**, **dispatch**, and **callback lifecycle**.

## 14. Exercises and self-check questions

1. Given `String name = "Java"; Supplier<String> f = name::toLowerCase;`, what is the receiver, and what does `f.get()` return? If changed to `String::toLowerCase`, which target type is appropriate?
2. Given `String prefix = "ID-";`, distinguish `prefix::concat` and `String::concat`: how many parameters does the functional interface have in each case?
3. Why does `factory.create()::execute` differ from `() -> factory.create().execute()` if the factory creates a new instance each time?
4. When `printer == null`, when does the error of `printer::print` occur? How can switching to `text -> printer.print(text)` change the error timing?
5. A `formatter::format` was bound earlier, and then `formatter` changes its `prefix` field. Does the method reference use the new value? Explain the difference between binding a receiver and taking a state snapshot.
6. Why does `BaseService service = new ChildService(); Supplier<String> f = service::name;` choose the `ChildService` implementation if the method is overridden?
7. An event bus uses `unregister(callback)`. Why should you store the registered callback variable instead of recreating the same `listener::onEvent` expression?
8. Given an object with two overloads `convert(String)` and `convert(int)`, assign `converter::convert` to `Function<String,String>` and `IntFunction<String>`, then predict the results when called.

## 15. Takeaways

**`existingObject::instanceMethod` is a bound instance method reference**: the expression to the left of `::` is evaluated when creating the reference, the receiver is bound, and the method call happens when the SAM is executed.

Distinguish it from `TypeName::instanceMethod` (unbound, receiver comes from the first parameter), `TypeName::staticMethod` (no receiver needed), and a lambda that evaluates the receiver expression dynamically. Watch out that **a null receiver fails at creation time**, **mutable state of the receiver can still change**, and **the target functional interface determines overload/signature resolution**.

A method reference is a tool for clearly expressing behavior on an existing object; deciding to use it must be based on receiver correctness, API contracts, lifecycle, and side effects, not merely on reducing Java character count.