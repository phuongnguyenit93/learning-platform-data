# Receiver Evaluation Timing and Null Risks in Method References

## Objectives

In Java, a **method reference** expression `receiver::instanceMethod` may look like the lambda `() -> receiver.instanceMethod()`, but the two forms are **not completely equivalent in execution timing**. The object before `::` is evaluated when the method reference is created, and a bound method reference requires the receiver to be non-`null` right at that moment. With a lambda, evaluating the receiver sits inside the lambda body and may only happen when the functional method is called.

After this lesson, you will be able to:

- Distinguish **bound instance method references** (`object::method`), **unbound instance method references** (`Type::method`), static method references, and lambdas.
- Determine when a receiver expression with side effects is evaluated and when the method is actually called.
- Explain why `nullable::method` can throw `NullPointerException` **immediately upon creation**, whereas `() -> nullable.method()` usually throws **when calling the lambda**.
- Know **which object** the receiver is bound to, and understand that the object can still change state after the reference is created.
- Choose the appropriate form when registering callbacks, deferring object creation, working with `Optional`, and building APIs that accept functional interfaces.
- Run the Java 17 example and accurately predict both stdout order and where errors occur.

## 1. A method reference is not an immediate method call

A method reference is an expression using `::` syntax to provide an implementation for a **functional interface**. It requires a **target type** with a single abstract method (*SAM*).

Example:

```java
String name = "Java";
java.util.function.Supplier<Integer> length = name::length;
```

`Supplier<Integer>` has the descriptor `() -> Integer`. `name::length` creates behavior such that calling `length.get()` invokes `length()` on the string bound to the method reference. Creating the reference **is not the same** as calling `name.length()`.

```java
int value = length.get(); // 4
```

Because `String.length()` returns `int`, the result is boxed into `Integer` according to the target type. Without a target type like `Supplier<Integer>`, Java generally cannot infer intent from `name::length` alone; `var x = name::length` is invalid because it lacks a functional interface target type.

However, there are **two distinct points in time** to distinguish:

1. **Method reference creation time:** evaluate the receiver part to the left of `::` (if it is a bound reference's receiver expression), check that the receiver is non-`null`, and bind to the object.
2. **Functional method invocation time:** execute the referenced method on the bound receiver.

In most situations, bugs stem from thinking only about the second point in time and overlooking receiver evaluation at the first.

## 2. Four method reference forms and the receiver

| Form | Example | Where does the receiver come from? | Related `null` risk |
| --- | --- | --- | --- |
| **Bound instance**: `expression::instanceMethod` | `profile::greet` | The `profile` expression is evaluated at reference creation and the instance is bound to the reference | A `null` receiver causes NPE immediately at creation |
| **Unbound instance**: `Type::instanceMethod` | `Profile::greet` | The receiver is the argument of the functional method when called | A `null` receiver argument causes NPE when called |
| **Static**: `Type::staticMethod` | `Integer::parseInt` | No object receiver for a static call | No bound-instance receiver check; a `null` argument can still fail inside the static method |
| **Constructor**: `Type::new` | `StringBuilder::new` | Creates an object when the functional method is called | No pre-existing receiver object; the constructor can still throw exceptions |

Bound form:

```java
Profile profile = new Profile("Lan");
java.util.function.Supplier<String> bound = profile::greet;
System.out.println(bound.get()); // Hello Lan
```

Unbound form:

```java
java.util.function.Function<Profile, String> unbound =
        Profile::greet;
System.out.println(unbound.apply(profile)); // Hello Lan
```

These two snippets are **illustrative in the context** of the `Profile` class defined in the full program below. They differ in their descriptors:

- `profile::greet` matches `() -> String` because the receiver is already bound.
- `Profile::greet` matches `(Profile) -> String` because the receiver must be **passed as the first parameter** of the call.

Do not assume that having `::` always implies a bound receiver. Only method references of the **instance expression with an evaluated receiver** form perform early `null` checking like `profile::greet`.

## 3. Receiver evaluation timing order

### 3.1. The expression before :: is evaluated immediately

```java
java.util.function.Supplier<String> greeting =
        loadProfile()::greet;
```

If `loadProfile()` has side effects (logging, incrementing a counter, querying a database), those side effects happen **when constructing `greeting`**, without waiting for `greeting.get()`. If `loadProfile()` returns `null`, creating the bound reference throws `NullPointerException` right at the reference creation expression. `greet()` has not been called yet.

You can picture the logical sequence as:

```text
1. Evaluate loadProfile()
2. Check whether the result is null
3. Bind the valid receiver to the method reference
4. [Later] Someone calls greeting.get()
5. Execute greet() on the bound receiver
```

This is a semantic diagram, **not Java code or a description of a mandatory JVM mechanism**. Compilers/JVMs may use various strategies to implement lambdas and method references; programs should only rely on language-guaranteed semantics.

### 3.2. A lambda can defer obtaining the receiver altogether

```java
java.util.function.Supplier<String> greeting =
        () -> loadProfile().greet();
```

Here, the body `loadProfile().greet()` only runs when `greeting.get()` is called. If no one calls `get()`, `loadProfile()` is never executed because the lambda body does not run. If `get()` is called multiple times, `loadProfile()` may also be called multiple times, producing different receivers.

Comparison:

| Operation | `loadProfile()::greet` | `() -> loadProfile().greet()` |
| --- | --- | --- |
| When creating the function object | Calls `loadProfile()` once and checks for null | Does not call `loadProfile()` yet |
| When calling the functional method the first time | Calls `greet()` on the bound instance | Calls `loadProfile()` then `greet()` |
| On subsequent functional method calls | Still calls `greet()` on the previously bound instance | Continues calling `loadProfile()` then `greet()` |
| When the factory returns `null` | NPE when creating the reference | NPE when executing the body |
| When the factory performs I/O | I/O happens when creating the reference | I/O happens on each body execution, if reached |

If the goal is to **defer obtaining or creating the receiver as well**, a lambda is the natural choice. If you want to **select the receiver once and reuse it**, a bound reference expresses that intent accurately. Yet both can have side effects/exceptions; the decision must rest on the call contract.

### 3.3. The receiver is bound once, not state-frozen

```java
StringBuilder builder = new StringBuilder("A");
java.util.function.Supplier<String> text = builder::toString;

builder.append("B");
System.out.println(text.get()); // AB
```

When `text` is created, the `builder` instance is bound. When `text.get()` is called, `toString()` runs on **that exact instance**, when its content has become `"AB"`. A method reference is not a snapshot of the method's result. It binds the object; it does not automatically cache the method call's return value.

That the receiver does not change in **identity** does not mean its state is immutable. Distinguish a **bound receiver** from **memoization** or **eager method invocation**.

## 4. Complete Java 17 program

The program tests all four key cases: a valid bound receiver; a receiver created via a side-effecting method; a null receiver in a bound reference vs. a lambda; and an unbound reference with a receiver passed later.

Save the following to **`MethodReferenceReceiverDemo.java`**:

```java
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import java.util.function.Supplier;

public class MethodReferenceReceiverDemo {
    record Profile(String name) {
        String greet() {
            return "Hello " + name;
        }
    }

    static Profile load(AtomicInteger calls) {
        System.out.println("load #" + calls.incrementAndGet());
        return new Profile("An");
    }

    public static void main(String[] args) {
        Profile profile = new Profile("Lan");
        Supplier<String> bound = profile::greet;
        Supplier<String> lambda = () -> profile.greet();

        System.out.println("created");
        System.out.println("bound: " + bound.get());
        System.out.println("lambda: " + lambda.get());

        AtomicInteger calls = new AtomicInteger();
        Supplier<String> fromCall = load(calls)::greet;
        System.out.println("after reference: " + calls.get());

        Supplier<String> delayed = () -> load(calls).greet();
        System.out.println("after lambda: " + calls.get());

        System.out.println("fromCall: " + fromCall.get());
        System.out.println("delayed: " + delayed.get());

        Profile absent = null;

        try {
            Supplier<String> rejected = absent::greet;
            System.out.println(rejected.get());
        } catch (NullPointerException e) {
            System.out.println("bound null: NPE at creation");
        }

        Supplier<String> later = () -> absent.greet();
        System.out.println("lambda with null created");
        try {
            later.get();
        } catch (NullPointerException e) {
            System.out.println("lambda null: NPE at get");
        }

        Function<Profile, String> unbound = Profile::greet;
        System.out.println("unbound: " + unbound.apply(profile));
        try {
            unbound.apply(null);
        } catch (NullPointerException e) {
            System.out.println("unbound null: NPE at apply");
        }
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac MethodReferenceReceiverDemo.java
java MethodReferenceReceiverDemo
```

**Exact stdout:**

```text
created
bound: Hello Lan
lambda: Hello Lan
load #1
after reference: 1
after lambda: 1
fromCall: Hello An
load #2
delayed: Hello An
bound null: NPE at creation
lambda with null created
lambda null: NPE at get
unbound: Hello Lan
unbound null: NPE at apply
```

**Explanation of output order:**

1. `profile::greet` and `() -> profile.greet()` are created, without calling `greet()` yet. Thus the first line is `created`.
2. `bound.get()` and `lambda.get()` both call `greet()` on `profile` and return `Hello Lan`. For this lambda, `profile` is captured as an *effectively final* local reference.
3. When creating `fromCall = load(calls)::greet`, `load(calls)` runs immediately, printing `load #1` and creating the `Profile("An")` instance. Hence `after reference: 1`.
4. When creating `delayed = () -> load(calls).greet()`, `load` does not run yet; `after lambda: 1` proves this.
5. `fromCall.get()` only calls `greet()` on the bound instance without incrementing `calls`; it returns `Hello An`.
6. `delayed.get()` calls `load(calls)`, printing `load #2` before `System.out.println("delayed: " + ...)` prints `delayed: Hello An`. This is Java's expression evaluation order.
7. `absent::greet` throws `NullPointerException` right at creation because the receiver is `null`; control jumps to `catch`, so the print statement in the `try` block does not run.
8. The lambda `() -> absent.greet()` is created successfully even though `absent` is `null`. The NPE occurs when `later.get()` executes the body.
9. `Profile::greet` does not bind an instance at creation time. `unbound.apply(profile)` succeeds, while `unbound.apply(null)` throws NPE at call time because the passed receiver is `null`.

The exceptions in the example are explicitly caught, allowing the program to print deterministic output and continue to the end.

## 5. Why do nullable::method and () -> nullable.method() differ?

Suppose we have a variable:

```java
Profile nullable = null;
```

The following **throws NPE immediately when the method reference expression is evaluated**:

```java
Supplier<String> a = nullable::greet;
```

Even without calling `a.get()`, the bound reference cannot be created successfully with a `null` receiver.

Meanwhile:

```java
Supplier<String> b = () -> nullable.greet();
// The assignment above succeeds.
// Only the line below throws NPE:
b.get();
```

Both can cause an NPE, but at different **times**. This affects:

- **Control flow:** the error is thrown in a constructor, field initializer, or callback registration instead of when the callback runs.
- **Try/catch:** to catch an NPE from a null bound receiver, the `try` block must wrap **reference creation**; to catch an NPE from a lambda, the `try` block must wrap **the invocation**.
- **Logging and stack traces:** the observed error location differs, which can make diagnosis confusing if readers assume both are identical.
- **Lazy initialization:** a bound reference may force immediate data access, defeating the intent to defer.
- **Input validation policy:** catching `null` early is sometimes good, but in other cases you want conditional execution so it never dereferences.

Example with method registration:

```java
// Illustrative; Action is a class with a void runAction() method.
Action action = null;

Runnable callback = action::runAction; // NPE at the registration step
```

Written as a lambda:

```java
Runnable callback = () -> action.runAction();
// Only when callback.run() is called does it attempt to dereference action.
```

These are **two separate illustrative snippets**; do not put them in the same scope due to the duplicate variable name. If the callback is never invoked, the lambda does not raise an NPE from its body; the bound reference already failed at registration time. Do not use a change in error timing to hide missing data that should have been present.

## 6. Evaluating a receiver with side effects or potential exceptions

The part before `::` can be a method call, a field access, or a complex expression. It does not have to be just a variable name.

```java
Supplier<String> first = repository.loadCurrent()::name;
```

This is an illustrative snippet: `repository.loadCurrent()` returns an object with a no-arg `name()` method. If `loadCurrent()` queries a database, the database is accessed **immediately when creating `first`**. If it returns `null`, NPE occurs immediately. If `loadCurrent()` itself throws an exception, that exception occurs during receiver evaluation, before the method reference is even created.

Equivalent in the "fetch receiver once" sense:

```java
// Also illustrative, only usable when Repo and Data types are defined.
Data current = repository.loadCurrent();
Supplier<String> first = current::name;
```

In the explicit form, the repository read step is easier to spot. Note: if `current` is `null`, the line creating the method reference still throws NPE. Using `Objects.requireNonNull(current, "current")` makes the non-null check explicit before creating the callback.

If business logic actually requires fetching fresh data on **each call**, use a lambda:

```java
Supplier<String> fresh = () -> repository.loadCurrent().name();
```

In this case, the repository operation is deferred and re-run every time `fresh.get()` is called. If there is I/O or failure, the caller must know this contract. Note: `Supplier.get()` does not declare checked exceptions, so if `loadCurrent()` throws a checked exception (e.g. `IOException`), the lambda must handle or translate it per policy, or use a custom functional interface declaring `throws`. You cannot assume any I/O operation placed in a `Supplier` will compile.

### Evaluating the receiver once is not equivalent to caching the result

```java
Supplier<String> bound = load(calls)::greet;
```

In the complete example, `load(calls)` runs once, yet **`greet()` still runs every time `bound.get()` is called**. If the receiver is a mutable object and `greet()` reads mutable fields, the result can differ on each call. Only the **receiver** is bound early; the method's result is not automatically memoized.

Conversely:

```java
String saved = load(calls).greet();
Supplier<String> cachedValue = () -> saved;
```

Here both `load` and `greet` run **right before creating the Supplier**, and subsequent `cachedValue.get()` calls return the `saved` value. Only this form represents computing the result once and retaining it, unlike a method reference.

## 7. Unbound instance method reference: null comes from the call-time argument

A method reference like `Profile::greet` does not need a concrete `Profile` when created:

```java
Function<Profile, String> f = Profile::greet;
```

With the target `Function<Profile,String>`, when `f.apply(profile)` is called, the first parameter `profile` acts as the receiver of `greet()`. Passing `null` to `f.apply(null)` can throw NPE at execution time; the `Profile::greet` expression itself was created earlier without checking a specific receiver.

Equivalent in intent:

```java
Function<Profile, String> f = person -> person.greet();
```

This is also a function taking a `Profile`. When `person == null`, the error occurs when the body executes. The two lines above are **two separate declaration options**; do not place them together in one scope with the same name `f`.

When you want to apply one method to many different objects, an unbound reference is usually appropriate:

```java
// Illustrative snippet using Profile from the main program.
java.util.List<Profile> profiles =
        java.util.List.of(new Profile("Lan"), new Profile("An"));

java.util.List<String> greetings = profiles.stream()
        .map(Profile::greet)
        .toList(); // [Hello Lan, Hello An]
```

`Stream.map` accepts a mapper called with each element at stream execution time. For non-`null` elements, the method reference works normally. `List.of` does not allow creating a list containing `null`; for a Stream from a source that can contain `null`, `Profile::greet` will not filter out null elements on its own.

If nulls are allowed in the input and should be skipped, you can write:

```java
java.util.List<String> safeNames = profiles.stream()
        .filter(java.util.Objects::nonNull)
        .map(Profile::greet)
        .toList();
```

This structure filters out null elements before calling `greet`. However, you must decide as a business rule: is null data to be skipped, replaced, or treated as an immediate data error?

## 8. Using Optional and checking null at the right boundary

You cannot use `Optional` to "rescue" a bound method reference after it has already been evaluated with a null receiver:

```java
// If profile is null, the line below fails before a valid Supplier exists.
Supplier<String> greet = profile::greet;
```

If a receiver may be absent, choose clear semantics.

**Case 1 — missing receiver is an error:** check early and provide a message:

```java
Profile checked = java.util.Objects.requireNonNull(
        profile, "profile is required");
Supplier<String> greet = checked::greet;
```

An NPE still occurs when `profile` is missing, but the location and error message express the contract. These are two illustrative statements that must be in a scope where `profile` is declared.

**Case 2 — missing receiver yields a fallback value:**

```java
String greeting = java.util.Optional.ofNullable(profile)
        .map(Profile::greet)
        .orElse("Hello Guest");
```

When `profile` is absent, the mapper does not run and the result is `Hello Guest`. `Optional.map` takes a `Function<Profile,String>`, so `Profile::greet` is a suitable **unbound reference** that does not bind a null receiver at creation time.

**Case 3 — invoke callback only when receiver is present:**

```java
java.util.Optional.ofNullable(profile).ifPresent(
        p -> System.out.println(p.greet())
);
```

The lambda is only executed when the `Optional` has a value. Note that `Optional.ofNullable(profile)` reads `profile` at **the time `ofNullable` is called**; it does not track future changes to a field.

Do not wrap an unexpected null bug in `Optional` if doing so silently ignores a required invariant. Choose between fail-fast, default value, and skipping based on business requirements.

## 9. Lambda capture, identity, and receiver mutation

A local variable captured by a lambda must be `final` or *effectively final*:

```java
Profile profile = new Profile("Lan");
Supplier<String> later = () -> profile.greet();
```

This snippet is valid if `profile` is not reassigned after initialization. If code assigns `profile = new Profile("An")` later in the same method, the compiler will not allow the lambda to capture this variable.

If a **mutable** object is captured, its contents can still change:

```java
StringBuilder builder = new StringBuilder("A");
Supplier<String> byReference = builder::toString;
Supplier<String> byLambda = () -> builder.toString();

builder.append("B");
System.out.println(byReference.get()); // AB
System.out.println(byLambda.get());    // AB
```

Both are using the same `builder` instance. For references to such a stable object, the behavior can be identical. **Prominent differences** appear when the receiver expression must be evaluated, the receiver may be null, or obtaining the object has side effects. Seeing `::` does not automatically mean newer or safer behavior than a lambda.

If the receiver is a field that can be reassigned, the difference becomes even clearer:

```java
// Illustrating semantics when field holder.current can change:
Supplier<String> fixed = holder.current::greet;
Supplier<String> dynamic = () -> holder.current.greet();
```

`fixed` keeps the instance of `holder.current` at creation time. `dynamic` reads `holder.current` every time the body executes and may see a different instance or `null`. This is only an illustrative snippet with an application-defined `holder`; not a standalone program. Use synchronization or proper state design if the field can change from another thread; method references/lambdas do not provide thread safety on their own.

## 10. Practical applications: callbacks, listeners, and lazy computation

An API often accepts `Runnable`, `Supplier<T>`, `Consumer<T>`, or `Function<T,R>`. Receiver behavior must be understood **before registering**:

```java
// Illustrative: notifier has a void notifyUser() method.
Runnable readyCallback = notifier::notifyUser;
Runnable deferredCallback = () -> notifier.notifyUser();
```

With a non-null `notifier` variable, both callbacks may produce equivalent results when run. But if `notifier` is null at registration time, the bound version fails immediately, while the lambda only fails if called. If `notifier` is a mutable field that changes after registration, how the receiver is bound can change which object executes the callback.

When calling registration:

```java
// Illustrative, callbackRegistry accepts Runnable:
callbackRegistry.register(notifier::notifyUser);
```

The right reasoning is that the argument expression `notifier::notifyUser` must finish being created before `register` is called. If `notifier` is null, NPE occurs before registration succeeds. A `try/catch` wrapping `register(...)` can still catch the error if the whole call is inside `try`, but you should not assume the error happens when the registry *runs* the callback.

When the receiver is expensive to create or only needed if the callback actually runs, write:

```java
callbackRegistry.register(() -> createNotifier().notifyUser());
```

`createNotifier()` is deferred. However, if the callback is called multiple times, the factory may also run multiple times; decide whether the goal is "create every time", "create once at registration", or "create once on first call and cache". A lambda does not provide thread-safe lazy caching by itself.

## 11. Common errors and misconceptions

1. **Thinking `receiver::method` executes the method immediately.** Wrong: it evaluates and binds the receiver immediately, while executing the method when the functional method is called.
2. **Thinking `receiver::method` is completely identical to `() -> receiver.method()`.** Wrong if the receiver is an expression with side effects, nullable, or changes at different times.
3. **Thinking null only causes errors when calling `get()`.** Wrong for bound references: the non-null receiver check happens when creating the reference.
4. **Thinking `Type::instanceMethod` checks a receiver at declaration time.** The unbound form has no concrete receiver yet; null is checked when receiving the argument and executing the call.
5. **Thinking a bound reference holds the method result.** It binds the **object**, not automatically caching the return value; the method can read updated state.
6. **Thinking a lambda defers everything around it.** Only expressions **inside the body** are deferred; if you compute the receiver or a value before creating the lambda, that computation is still eager.
7. **Ignoring factory side effects:** `find()::process` can query or fail immediately; `() -> find().process()` changes the timing and number of queries.
8. **Using `Optional` just to hide required-data bugs:** distinguish valid nullability from a violated business invariant.
9. **Assuming references and lambdas are automatically concurrency-safe:** they do not protect mutable receivers or I/O on their own; proper synchronization and lifecycle contracts are needed.
10. **Relying on lambda object identity:** do not assume each evaluation of a lambda/method reference allocates a new object or the same object; Java is free to choose its implementation strategy.

## 12. Self-check exercises

1. Given `String text = null; Supplier<Integer> s = text::length;`, does the error occur before or after calling `s.get()`?
2. Given `String text = null; Supplier<Integer> s = () -> text.length();`, when does the NPE appear?
3. Suppose `getService()` increments a counter and returns a valid service. Compare the number of `getService()` calls when creating and invoking `getService()::execute` twice vs. `() -> getService().execute()`.
4. Given `Function<String,Integer> f = String::length;`, when does `null` become the receiver, and why can the method reference expression still be created?
5. A `StringBuilder` is used in `builder::toString`. If characters are appended after creating the reference but before calling it, does the result reflect the old or new content?
6. Suppose `repository.load()` can return null. Choose the appropriate handling for (a) missing is an error; (b) missing returns a default value; (c) query only when the callback is invoked.
7. Compare `Service service = factory(); Supplier<String> s = service::status;` with `Supplier<String> s = () -> factory().status();` regarding factory execution timing and ability to swap services.
8. When receiving a `Stream<Profile>` that may contain null, why can `.map(Profile::greet)` hit an NPE? Fix it according to a policy of discarding nulls.

**Suggested answers:**

- (1) NPE occurs when creating the bound reference `text::length`, before `s` is even assigned.
- (2) Lambda creation succeeds; NPE occurs at `s.get()`.
- (3) Bound calls the factory once at creation; lambda calls the factory each time the body runs (twice under the assumption).
- (4) `String::length` is unbound and receives the receiver in `f.apply(...)`; `f.apply(null)` causes NPE when called.
- (5) New content, because `toString()` only runs when the functional method is called.
- (6) Fail-fast with a non-null check; `Optional.ofNullable(...).map(...).orElse(...)` or equivalent; move the factory into the lambda body to defer.
- (7) The first fetches the service once and binds the receiver; the second fetches the service again each time `get()` runs.
- (8) The unbound form takes each element as the receiver; use `filter(Objects::nonNull)` before `map` if business rules allow dropping nulls.

## Conclusion

The most important takeaway for `receiver::method` is **evaluating the receiver and checking non-null when creating the bound method reference, while only calling the method when the functional method is executed**. The lambda `() -> receiver.method()` can defer receiver evaluation and thus change when side effects or exceptions occur. Meanwhile, `Type::instanceMethod` receives its receiver as an argument at call time.

Understanding these three cases accurately helps you read execution flow, decide when to fail-fast vs. defer work, and avoid hard-to-spot null bugs when registering callbacks or processing data with functional APIs.