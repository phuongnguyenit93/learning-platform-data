# Comparing Scope and `this` Between Lambdas and Anonymous Classes in Java

## 1. Context: Same Behavior, Different Scopes

A **lambda** expression and an **anonymous class** can both provide an implementation for a functional interface, such as `Runnable` or `Comparator<T>`. However, they define **name scope** and the meaning of `this` and `super` very differently.

- **A lambda** does not create its own `this` and `super` scope. `this` in a lambda has the same meaning as `this` at the location where the lambda appears: usually the enclosing object executing the method.
- **An anonymous class** declares and creates an object of a new unnamed class. Inside a method of the anonymous class, `this` is that anonymous class object, and `super` points to the superclass of the anonymous class.
- **A lambda** does not allow redeclaring parameter or local variable names already in the enclosing scope by way of creating a separate class. **An anonymous class** has its own member scope (fields, methods) and can shadow names in the outer scope.
- Both can read local variables **captured** from the enclosing region if the variable is `final` or *effectively final*. Both can access and modify object fields if access rules allow.

These differences matter when writing callbacks, listeners, stream processing, asynchronous code, and when refactoring code from anonymous classes to lambdas.

> **Recognition principle:** do not just see `() -> ...` and `new Runnable() { ... }` and assume they are freely interchangeable syntaxes. Check whether the body uses `this`, `super`, colliding field names, `return`, or information about the runtime class.

## 2. Same `Runnable` Contract, Two Implementations

`Runnable` is a functional interface in `java.lang`, with a single abstract method `void run()`. Both approaches below create a value that can be passed where a `Runnable` is expected:

```java
Runnable lambda = () -> System.out.println("Run");

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println("Run");
    }
};

lambda.run();    // Run
anonymous.run(); // Run
```

This is a **code snippet illustrating inside a method**, not a standalone program. For an example that just prints a string, the output is the same. Differences appear when the method body needs to reference an object or a name from the enclosing scope.

A lambda is usually more concise when only performing a small behavior. An anonymous class can declare additional fields, methods, and its own initializer blocks, or extend an inheritable class (not necessarily a functional interface). Lambdas are only used in a **functional interface** context; they are not a general replacement syntax for arbitrary anonymous classes.

## 3. The `this` Rule: The Question "Which Object Are We Talking About?"

Consider code inside an instance method of `Outer`:

```java
class Outer {
    String label = "OUTER";

    void demonstrate() {
        Runnable lambda = () ->
                System.out.println(this.label);

        Runnable anonymous = new Runnable() {
            String label = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println(this.label);
                System.out.println(Outer.this.label);
            }
        };

        lambda.run();    // OUTER
        anonymous.run(); // ANONYMOUS, then OUTER
    }
}
```

- In the lambda, `this.label` is `Outer.this.label` because the lambda has **lexical scoping** for `this`; it has no separate "lambda `this`."
- In the anonymous class, `this.label` is the field of the anonymous class object, so the result is `ANONYMOUS`.
- `Outer.this` is a **qualified `this`**, explicitly indicating the enclosing `Outer` object. This syntax is very useful when an inner class shadows a field of the outer class.

If the `label` field of the anonymous class is removed, how `this.label` resolves changes: the anonymous class object does not have that field and does not automatically have permission to use `this` to refer to `Outer`'s field. From inside the anonymous class, write `Outer.this.label` to explicitly reference the enclosing field.

### When is `this` in a lambda unusable?

`this` is only valid in a context with an appropriate current object. If a lambda is declared directly inside a **static method**, there is no `this` instance of the enclosing class:

```java
class Example {
    static Runnable task() {
        // INVALID: in a static context there is no "this" of Example.
        // return () -> System.out.println(this);
        return () -> System.out.println("static context");
    }
}
```

An anonymous class created in a static method is still an object: inside its `run()`, `this` still points to the **anonymous class object**, not to an instance of the class containing the static method. Static and instance contexts must therefore be clearly distinguished.

## 4. Complete Java 17 Program for Verification

The program below runs entirely on Java 17+, using `Runnable`, `Consumer<String>`, lambdas, and anonymous classes, and intentionally prints output in deterministic order.

Create the file **`LambdaScopeDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Consumer;

public class LambdaScopeDemo {
    private final String label = "OUTER";
    private int counter = 0;

    private void demonstrate() {
        String prefix = "captured";

        Runnable lambda = () -> {
            System.out.println("Lambda this.label: " + this.label);
            System.out.println("Lambda this is outer: "
                    + (this == LambdaScopeDemo.this));
            System.out.println("Lambda local: " + prefix);
            counter++;
        };

        Runnable anonymous = new Runnable() {
            private final String label = "ANONYMOUS";

            @Override
            public void run() {
                System.out.println("Anonymous this.label: " + this.label);
                System.out.println("Anonymous outer.label: "
                        + LambdaScopeDemo.this.label);
                System.out.println("Anonymous this is outer: "
                        + ((Object) this == LambdaScopeDemo.this));
                System.out.println("Anonymous local: " + prefix);
                LambdaScopeDemo.this.counter++;
            }
        };

        lambda.run();
        anonymous.run();
        System.out.println("Counter: " + counter);

        List<String> events = new ArrayList<>();
        Consumer<String> lambdaConsumer = text -> {
            events.add("lambda:" + text);
        };

        Consumer<String> anonymousConsumer = new Consumer<>() {
            private final String prefix = "inner";

            @Override
            public void accept(String text) {
                events.add(prefix + ":" + text);
            }
        };

        lambdaConsumer.accept("A");
        anonymousConsumer.accept("B");
        System.out.println("Events: " + events);

        // Both capture a local variable: no reassignment of prefix.
        Runnable again = () ->
                System.out.println("Again local: " + prefix);
        again.run();
    }

    public static void main(String[] args) {
        new LambdaScopeDemo().demonstrate();
    }
}
```

Compile and run:

```bash
javac --release 17 LambdaScopeDemo.java
java LambdaScopeDemo
```

**Exact expected stdout**:

```text
Lambda this.label: OUTER
Lambda this is outer: true
Lambda local: captured
Anonymous this.label: ANONYMOUS
Anonymous outer.label: OUTER
Anonymous this is outer: false
Anonymous local: captured
Counter: 2
Events: [lambda:A, inner:B]
Again local: captured
```

Comparing part by part:

1. `lambda` runs in the `demonstrate` method of the `LambdaScopeDemo` object. `this.label` points to the `label` field of the enclosing object itself, which is `"OUTER"`.
2. `this == LambdaScopeDemo.this` in the lambda is `true` because the two expressions denote the same instance.
3. The anonymous class has its own field named `label`, so `this.label` becomes `"ANONYMOUS"`. Writing `LambdaScopeDemo.this.label` retrieves the outer field.
4. In the anonymous class, `(Object) this == LambdaScopeDemo.this` evaluates to `false`: they are two different objects. Casting `(Object)` here makes the reference comparison between two different object types type-valid.
5. Both can read `prefix` from their containing method because `prefix` is not reassigned.
6. The two increments of `counter` act on **the same field of the enclosing object**: the lambda uses `counter++`, and the anonymous class explicitly writes `LambdaScopeDemo.this.counter++`. The result is 2.
7. With the lambda's `Consumer`, `events.add(...)` adds `"lambda:A"`. In the anonymous class, its own `prefix` field has the value `"inner"`, so it adds `"inner:B"`. The actions are invoked sequentially, so the list order is deterministic.

> The example intentionally uses `counter++` and `events.add` to demonstrate **scope and state ownership**, not as a recommendation to update shared state from multiple threads. When invoking callbacks concurrently, coordination mechanisms or a design change are needed to avoid data races.

## 5. Local Variable Scope and the *Effectively Final* Rule

A lambda can **read** a local variable in its containing scope when that variable is `final` or *effectively final*: the variable's value is only assigned during initialization (or according to valid definite assignment rules) and is not reassigned afterwards.

```java
String category = "BOOK"; // effectively final
Runnable lambda = () -> System.out.println(category);

Runnable anonymous = new Runnable() {
    @Override
    public void run() {
        System.out.println(category);
    }
};
```

Both are valid. However, the following snippet is invalid for **both lambdas and anonymous classes**:

```java
// INVALID: the local variable is reassigned so it is not effectively final.
String category = "BOOK";
Runnable lambda = () -> System.out.println(category);
category = "PEN";
```

The compiler will report an error that a local variable referenced from a lambda must be final or effectively final. If `lambda` is changed to an anonymous class, the local capture restriction is the same.

**Why does this rule exist?** Local variables belong to the stack frame of a method call; a lambda or anonymous class object can outlive that method's execution. Java allows capturing the value of a qualifying local without providing a shared mutable local variable for callbacks to modify arbitrarily. This is also why you cannot directly use a local counter variable to update inside `forEach`:

```java
// INVALID: cannot modify a captured local variable.
int count = 0;
// list.forEach(item -> count++);
```

Instead of "working around" it with an array `int[] count = {0}`, use `stream().count()` if the goal is counting elements, or `reduce`/`sum` to aggregate.

### *Effectively final* does not mean the object is immutable

```java
List<String> events = new ArrayList<>();
Consumer<String> store = events::add;
store.accept("A");
System.out.println(events); // [A]
```

The variable `events` is not reassigned to another list, so it remains effectively final, even though the **contents** of the list change. Both lambdas and anonymous classes can mutate an object referenced via a captured local; that is precisely why side effects, state ownership, and thread safety must be considered separately.

## 6. Shadowing: A Lambda Does Not Open a Class with Its Own Fields

**Shadowing** occurs when a declaration in a nearer scope uses the same name as a declaration in a farther scope and hides the farther name. This rule makes lambdas differ from anonymous classes.

In a method with `String name = "outer";`, a lambda **cannot** declare a parameter or another local variable with the same name in its body:

```java
void example() {
    String name = "outer";

    // INVALID: lambda parameter name collides with local variable in enclosing scope.
    // Consumer<String> badParam = name -> System.out.println(name);

    // INVALID: local variable declared in lambda block collides with existing name.
    // Runnable badLocal = () -> {
    //     String name = "inner";
    //     System.out.println(name);
    // };
}
```

This is **error-illustrating** code; the invalid lines are commented out so they do not affect a program.

Conversely, an anonymous class creates its own **member scope**, so it can declare a field with the same name as a local in the enclosing method:

```java
void example() {
    String name = "outer";

    Runnable anonymous = new Runnable() {
        private final String name = "inner";

        @Override
        public void run() {
            System.out.println(this.name); // inner
            System.out.println(name);      // inner: field takes precedence
        }
    };

    anonymous.run();
    System.out.println(name); // outer
}
```

This snippet is also a method example, not a standalone class. The `name` field belongs to the anonymous class object; the local `name` in the containing method still exists and its value is unchanged. That does not mean an anonymous class has the right to reassign a captured local variable: it merely declares **a different field** with the same name.

### Lambda parameters also belong to the naming scope of the enclosing context

```java
String item = "BOOK";

// Valid: parameter name differs from enclosing local variable name.
Consumer<String> display = value ->
        System.out.println(item + " -> " + value);
```

A lambda can use a different parameter name (`value`) and read the captured `item`. When designing callbacks, choosing clear parameter names avoids confusion between names in the two scopes and reduces the risk of "variable is already defined" errors.

## 7. `this`, `super`, and Referencing Inherited Members

The difference in `this` entails a difference in `super`:

| Context | What `this` points to | What `super` targets |
| --- | --- | --- |
| Lambda in an instance method of `Child extends Base` | Enclosing `Child` instance | `Base`, like `super` at the location where the lambda is written |
| `run()` method of `new Runnable() { ... }` | Anonymous class instance | Direct superclass of the anonymous class (in the example, `Object`) |
| Anonymous class inside `Child`, using `Child.this` | Enclosing `Child` instance | Requires qualified syntax `Child.super` to target `Child`'s superclass |
| Lambda in a static method | No outer `this` instance | Cannot use `super` of an outer instance |

Example of `super` with dedicated code:

```java
class Base {
    String source() {
        return "base";
    }
}

class Child extends Base {
    @Override
    String source() {
        return "child";
    }

    void compare() {
        Runnable lambda =
                () -> System.out.println(super.source());

        Runnable anonymous = new Runnable() {
            @Override
            public void run() {
                System.out.println(Child.super.source());
            }
        };

        lambda.run();    // base
        anonymous.run(); // base
    }
}
```

`super.source()` in the lambda is interpreted as if written right in the `Child.compare()` method, i.e., calling `Base`'s `source()` method. In the anonymous class, writing `super.source()` **cannot** call `Base.source()`, because the superclass of an anonymous class implementing `Runnable` is `Object`; `Object` does not define a `source()` method. Writing `Child.super.source()` explicitly specifies the superclass of the enclosing object.

**Limitation:** the syntax `QualifiedType.this` and `QualifiedType.super` can only be used in contexts with a valid enclosing instance/class according to language rules; you cannot arbitrarily reference an outer object that is not in the lexical enclosing chain.

## 8. Anonymous Classes Have Their Own Objects; Lambdas Do Not Mean "New Class Every Time"

An anonymous class is an unnamed class declaration used in a class instance creation expression like `new Runnable() { ... }`. It creates its own instance and can have helper fields and methods. Inside an anonymous class, `getClass()` and `this.getClass()` refer to the anonymous class, not the enclosing class.

A lambda has a runtime representation decided by the JVM. You should not rely on `lambda.getClass().getName()`, synthetic class names, object allocation counts, or reference identity `==` for business logic. For non-capturing lambdas, the JVM may reuse instances; for state-capturing lambdas, instance creation/reuse behavior is not a contract for designing application logic.

```java
Runnable lambda = () -> {};
Runnable anonymous = new Runnable() {
    @Override public void run() {}
};

System.out.println(lambda instanceof Runnable);    // true
System.out.println(anonymous instanceof Runnable); // true
```

Both values are `Runnable`. They are not required to have the same class at runtime and should not have their class names or object identities compared to test behavioral equivalence.

## 9. From Anonymous Class to Lambda: What to Check?

A common refactoring:

```java
Runnable oldTask = new Runnable() {
    @Override
    public void run() {
        System.out.println("Ready");
    }
};

Runnable newTask = () -> System.out.println("Ready");
```

Both versions print `Ready` when run. However, the conversion **needs careful review** if the original anonymous class referenced:

1. **`this`** or `getClass()`: previously referenced the anonymous class object; after converting to a lambda, it may reference the outer instance.
2. **`super`**: previously the anonymous class's superclass; in a lambda, it is the superclass of the outer context.
3. **The anonymous class's own fields/methods**: a lambda cannot define new fields like a class; state must be moved to an object with a clear owner or another structure.
4. **Colliding variable/field names**: a lambda does not create an equivalent new shadowing region.
5. **Behaviors depending on instance creation time or identity**: not guaranteed to stay the same if the object model changes.
6. **Functional interface**: lambdas only apply to interfaces with a single abstract method and cannot replace an anonymous subclass of an arbitrary class.

Example of meaning changing:

```java
class Example {
    private String name = "Outer";

    void run() {
        Runnable anonymous = new Runnable() {
            private String name = "Inner";

            @Override public void run() {
                System.out.println(this.name); // Inner
            }
        };

        Runnable lambda = () ->
                System.out.println(this.name); // Outer

        anonymous.run();
        lambda.run();
    }
}
```

You cannot simply delete the `new Runnable() { ... }` syntax and replace it with `() -> ...` expecting `this.name` to keep the same meaning. When refactoring, write out the data source to be read explicitly and verify with tests for the same scenario.

## 10. Distinguishing Outer Object, State, and Thread Safety

A lambda can use a field of the outer object directly:

```java
class Counter {
    private int value;

    Runnable incrementTask() {
        return () -> value++;
    }

    int value() {
        return value;
    }
}
```

This code is valid with respect to scope, but the increment `value++` is not atomic. If two threads call `incrementTask` or multiple tasks capture the same `Counter`, **lost updates** can occur.

An anonymous class does not automatically solve the problem either: `Counter.this.value++` carries the same risk. The difference in `this` **does not determine** whether code is thread-safe. The solution depends on requirements: avoid shared state, return new values via `Function`/`reduce`, or use `AtomicInteger`, `synchronized`/locks, or an appropriate state-sharing design.

Example choosing not to use a shared accumulator:

```java
List<Integer> values = List.of(1, 2, 3, 4);

int sum = values.stream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(sum); // 10
```

`mapToInt` converts each `Integer` to primitive `int`, and `sum` performs the aggregation through the Stream API. There is no need to have a lambda increment a shared local variable/array.

## 11. Frequently Asked Questions and Typical Errors

**"Does a lambda have its own `this`?"** No. In an instance context, `this` inside a lambda is the `this` at the location where the lambda is declared. An anonymous class has its own object, so its `this` has a different meaning.

**"Does a lambda capture the entire outer object?"** It cannot be inferred that simply. If the lambda body uses fields/instance methods via `this`, it may hold a reference to the enclosing instance; if it only uses effectively final local variables, the lambda captures the needed values. Representation details and optimizations are decided by the JVM. Do not design logic depending on a lambda's internal object structure.

**"If a captured variable is `final`, is it immutable?"** `final`/effectively final only prevents **reassigning the local variable**, not modifying the object inside the reference. A `List` or `AtomicInteger` can still be modified.

**"Can an anonymous class read a non-effectively-final local?"** No. Both lambdas and anonymous classes are bound by the appropriate local variable capture rules.

**"Can fields be declared inside a lambda?"** Not like in the class body of an anonymous class. A lambda body is an expression or an executable block, not a field declaration section. You can declare new local variables in the block as long as they do not collide with names in forbidden scopes.

**"Why does `this.toString()` differ?"** In a lambda, it calls `toString()` on the outer object; in an anonymous class, it calls it on the anonymous object, unless qualified outer `this` is written.

**"Does omitting `this` always fetch the outer field?"** No. An unqualified name depends on name resolution and shadowing rules. An anonymous class with a same-named field can shadow the outer member; use `Outer.this.member` for clarity.

**"What is better about using an anonymous class?"** It is suitable if you need to extend a class, declare your own fields/methods, or organize an object with its own state. For a simple callback with exactly one behavior, a lambda is usually shorter and easier to read.

**"Can every anonymous class be replaced by a lambda?"** Only for functional interface cases and after reviewing scope, `this`/`super`, custom members, and callback semantics.

## 12. Self-Check Exercises

1. In `LambdaScopeDemo`, change the outer `label` field to `"PARENT"`. Predict exactly which stdout lines change and why the `Anonymous this.label` line remains `"ANONYMOUS"`.
2. Remove the `label` field from the anonymous class in the program and adjust accesses accordingly. Use `LambdaScopeDemo.this.label` to access the outer field.
3. Set `String prefix = "captured";` and then try `prefix = "changed";` after declaring the lambda. Explain why both the lambda and the anonymous class capturing `prefix` no longer compile.
4. Try declaring a lambda parameter named `prefix` in the same scope as the method's local `prefix`. Note the compiler error and rename it to `value` to fix.
5. In the anonymous `Consumer`, change `private final String prefix = "inner";` to `private final String prefix = "ANON";`. Predict the exact contents of the `events` list, while the `lambdaConsumer` lambda remains unchanged.
6. In the `Child extends Base` example, change `Child.source()` to return `"child-v2"`. Explain why `super.source()` still returns `"base"`.
7. Write an anonymous class `Runnable` that writes `System.out.println(this.getClass().getName())`, then write a lambda with the same expression body. Identify which object `this` refers to and do not rely on runtime class names to compare functionality.
8. Create `Counter` with `incrementTask()` and run multiple tasks concurrently. Explain why the result can miss increments and show how to replace it with `AtomicInteger` or a non-shared-state design.
9. Take an anonymous class callback in a project and tabulate places using `this`, `super`, colliding field names, and captured variables. Only convert to a lambda when the meaning of the references is preserved.

**Core takeaway to remember:** lambdas use `this`/`super` according to the **enclosing lexical scope**; anonymous classes create **their own object and member scope**. Both are subject to the `final` or effectively final local capture rule. When you understand these rules clearly, choosing or refactoring callbacks is much less likely to cause unintended behavior changes.