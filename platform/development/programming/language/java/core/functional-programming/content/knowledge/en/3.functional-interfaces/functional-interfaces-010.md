# Why Cannot a `sealed interface` Be a Target Type for a Lambda in Java?

## 1. The Exact Conclusion According to the Java Language

In Java 17 and later, for an interface to be a **functional interface**, it must satisfy **both** of these conditions simultaneously:

1. The interface **must not be declared `sealed`**.
2. After accounting for inherited methods, overriding, and excluding declarations matching `public` methods of `Object`, it has **a single abstract method contract** (*single abstract method*, SAM).

Therefore, **a `sealed interface` with exactly one abstract method is still not a functional interface**, and cannot be the direct *target type* of a lambda expression or method reference.

This is a rule of the **Java Language Specification (JLS) `9.8**, not a limitation imposed by a specific IDE or library. JLS `15.27.3 also requires the target type of a lambda to be a functional interface type. The `@FunctionalInterface` annotation cannot alter those rules.

> **Key distinction:** Not being able to use `() -> ...` to directly create a value with target type `sealed interface` **does not mean** you cannot create objects implementing that interface, call its methods, or store a lambda-created object in a variable of the sealed type through a valid subtype.

## 2. Two Different Properties: SAM and `sealed`

### 2.1. SAM Is About Behavioral Contracts

Example of a regular interface:

~~~java
@FunctionalInterface
interface Action {
    void execute();
}
~~~

`Action` has one abstract method, `execute()`. It is not `sealed`, so `Action a = () -> System.out.println("run");` is valid.

An interface can add `default`, `static`, and `private` methods with bodies and still have one SAM. `equals(Object)`, `hashCode()`, and `toString()` with signatures matching `public` methods of `Object` do not increase the SAM count either.

### 2.2. `sealed` Restricts **Direct** Subtypes

The `sealed` declaration has been officially supported in Java since **Java 17**. It is used to restrict which classes/interfaces are allowed to **directly** `implements` or `extends` the sealed type.

~~~java
sealed interface Task permits BuiltInTask {
    void execute();
}

final class BuiltInTask implements Task {
    @Override
    public void execute() {
        System.out.println("built-in");
    }
}
~~~

This is a valid declaration snippet. `Task` has only one abstract method, yet because it is a `sealed interface`, it is not a functional interface.

`permits BuiltInTask` is the set of permitted direct subtypes. `BuiltInTask` is `final`, obeying the rule that a class directly extending a sealed type must explicitly state how inheritance continues or stops (typically `final`, `sealed`, or `non-sealed` depending on context). An interface permitted to directly extend a sealed interface must be declared `sealed` or `non-sealed`.

The `permits` syntax is **not a list of objects that can be created**. It is a list of **direct types** permitted to inherit. Once a `non-sealed` branch exists, deeper subtypes may be allowed to extend through that branch.

### 2.3. Why Do These Two Properties Conflict When Using a Lambda Directly?

A lambda is an expression that requires a **functional interface type** as its target type. When a lambda is evaluated at runtime, the result is a reference to an object implementing the target interface; details of how the runtime creates or reuses the object are left flexible by the JLS.

By contrast, a sealed interface explicitly specifies the set of permitted direct subtypes. Java therefore **excludes interfaces declared `sealed` from the definition of a functional interface** rather than allowing a lambda to act as a way of declaring a new direct subtype.

This rule is stricter than the intuition “an interface with one abstract method can take a lambda”: **one SAM is a necessary condition, not a sufficient one**. Matching lambda parameter counts or return types cannot override the `sealed` condition either.

You do not need to rely on synthetic class names that a compiler/runtime might use to prove the rule; the exact foundation is the JLS requirement on **target types**.

## 3. Non-Compiling Example: A `sealed interface` with One SAM

The following snippet is an **intentionally invalid example**, placed in `InvalidSealedTarget.java` to observe the error (do not run the program):

~~~java
sealed interface ClosedAction permits DefaultAction {
    String apply(String input);
}

final class DefaultAction implements ClosedAction {
    @Override
    public String apply(String input) {
        return "default:" + input;
    }
}

public class InvalidSealedTarget {
    public static void main(String[] args) {
        ClosedAction action = input -> "lambda:" + input; // Compile error.
        System.out.println(action.apply("Java"));
    }
}
~~~

Try compiling with JDK 17+:

~~~bash
javac InvalidSealedTarget.java
~~~

Result: **compilation fails** at the lambda expression assigned to `ClosedAction`. Exact `javac` messages vary by version, but the cause is that `ClosedAction` is not a functional interface because it is declared `sealed`. There is no stdout from `java InvalidSealedTarget` because no program was compiled successfully.

Keeping one abstract method and having class `DefaultAction` listed in `permits` **does not make** `ClosedAction` a valid lambda target type. The compiler must check the validity of the **target type** before checking whether a lambda body matches the contract.

### Does Adding `@FunctionalInterface` Fix It?

No. If you add `@FunctionalInterface` to `ClosedAction`, the interface declaration itself is also rejected because the annotation requires the interface to satisfy the functional interface definition, whereas `sealed` is excluded from that definition. The annotation is a compile-time checking tool; it does not alter type rules.

### Does Switching to a Method Reference Fix It?

No. `ClosedAction action = String::trim;` is also invalid because a method reference requires a functional interface type. The signature `String::trim` may be compatible with `String apply(String)` in parameters and return type, yet `ClosedAction` is still not a functional interface.

## 4. First Valid Approach: Use a `non-sealed` Subtype as the Target Type

You can keep a `sealed` root interface to control **direct branches**, and expose a `non-sealed` branch with a single SAM for lambdas.

Save as `SealedWithLambdaDemo.java`:

~~~java
import java.util.Locale;

sealed interface Job permits BuiltInJob, OpenJob {
    String execute(String input);
}

final class BuiltInJob implements Job {
    @Override
    public String execute(String input) {
        return "builtin:" + input;
    }
}

@FunctionalInterface
non-sealed interface OpenJob extends Job {
    // Inherits the SAM execute(String) from Job.
}

public class SealedWithLambdaDemo {
    public static void main(String[] args) {
        Job builtIn = new BuiltInJob();

        OpenJob lambdaJob =
                input -> "lambda:" + input.toUpperCase(Locale.ROOT);

        // Upcast: the lambda object implements OpenJob, and OpenJob extends Job.
        Job asJob = lambdaJob;

        System.out.println(builtIn.execute("one"));
        System.out.println(lambdaJob.execute("java"));
        System.out.println(asJob.execute("ok"));
    }
}
~~~

Compile and run:

~~~bash
javac SealedWithLambdaDemo.java
java SealedWithLambdaDemo
~~~

Exact stdout:

~~~text
builtin:one
lambda:JAVA
lambda:OK
~~~

**Mechanism explanation:**

1. `Job` is a sealed interface declaring one abstract method `execute(String)`. `Job` is not a functional interface.
2. `BuiltInJob` is a valid direct subtype, listed in `permits` and declared `final`.
3. `OpenJob` is also a permitted **direct** subtype; it is declared `non-sealed`, meaning this branch allows further subtypes under normal Java rules.
4. `OpenJob` declares no extra abstract methods itself, so it inherits exactly one SAM `execute(String)`. It is **not sealed**; `@FunctionalInterface` is valid and lambdas can target `OpenJob`.
5. `Job asJob = lambdaJob;` is a normal upcast assignment from subtype to supertype. We are **not** creating a lambda with target type `Job`; the target type when creating the lambda is `OpenJob`.

This is the key point: **an object originating from a lambda can be referenced through a variable of a sealed type** if it was created using a permitted **non-sealed functional subinterface**. The restriction applies at the step of using a lambda target type, rather than forbidding any sealed-type value from ever being related to a lambda.

### Why Can't `OpenJob` Be Replaced by Any Arbitrary Interface?

If you write `interface OtherJob extends Job` when `OtherJob` is not in `Job`'s `permits` set, the direct inheritance declaration is invalid. If it were permitted, `OtherJob` would also have to be declared `sealed` or `non-sealed` because it directly extends a sealed interface. A regular interface unrelated by inheritance to `Job` cannot automatically be assigned to a `Job` variable just because it has a method with the same name and signature: Java's type system uses **nominal typing**, requiring an explicit type relationship.

## 5. Second Valid Approach: Use Lambdas Inside a `permits`-Listed Class

Not every design wants to open a `non-sealed` branch. If you need to keep the set of direct implementing types **closed**, you can create a `final` class permitted to implement the sealed interface, and pass a lambda typed by an independent functional interface into that class.

Save as `SealedAdapterDemo.java`:

~~~java
import java.util.Objects;
import java.util.function.IntUnaryOperator;

sealed interface Calculation permits ConfigurableCalculation {
    int compute(int input);
}

final class ConfigurableCalculation implements Calculation {
    private final IntUnaryOperator rule;

    ConfigurableCalculation(IntUnaryOperator rule) {
        this.rule = Objects.requireNonNull(rule);
    }

    @Override
    public int compute(int input) {
        return rule.applyAsInt(input);
    }
}

public class SealedAdapterDemo {
    public static void main(String[] args) {
        Calculation doubledPlusOne =
                new ConfigurableCalculation(x -> x * 2 + 1);
        Calculation squared =
                new ConfigurableCalculation(x -> x * x);

        System.out.println(doubledPlusOne.compute(5));
        System.out.println(squared.compute(5));
    }
}
~~~

Compile and run:

~~~bash
javac SealedAdapterDemo.java
java SealedAdapterDemo
~~~

Stdout:

~~~text
11
25
~~~

**Type-by-type analysis:**

- `Calculation` is a sealed interface, not a functional interface; it is still a valid type for the two variables `doubledPlusOne` and `squared`.
- `ConfigurableCalculation` is a `final` class in the `permits` list, so its instances are valid in the sealed hierarchy.
- `IntUnaryOperator` is a standard functional interface with SAM `int applyAsInt(int operand)`, so the two lambdas `x -> x * 2 + 1` and `x -> x * x` are valid at the constructor argument position.
- Storing `rule` in a `final` field in the constructor does not change the lambda's target type; the target type remains `IntUnaryOperator`.
- The `compute` method simply delegates to `rule`. Each calculation is supplied by a lambda, while the set of classes directly implementing `Calculation` remains controlled by `permits`.

This pattern is often called **adapter/delegation**: the sealed hierarchy manages the catalog of object kinds; the functional interface expresses configurable behavior. Note that if a lambda captures mutable state, merely storing it in a `final` field does not guarantee pure logic or thread safety.

## 6. Comparing Three Easily Confused Cases

| Declaration / target type | Direct lambda allowed? | Explanation |
|---|---|---|
| `interface A { void run(); }` | Yes | Not sealed, has one SAM |
| `sealed interface A permits Impl { void run(); }` | No | Sealed, so ineligible under JLS `9.8 despite having one SAM |
| `non-sealed interface B extends A { }` where `A` is sealed and `B` is permitted | Yes if it has one SAM | `B` is not sealed and inherits the SAM |
| `interface A { void run(); void stop(); }` | No | Has two independent abstract methods |
| `interface A { void run(); default void reset() {} }` | Yes | `reset` is not counted |
| `Runnable r = () -> ...` | Yes | Target type is `Runnable`, not sealed |
| `A a = r;` where `A` is sealed and `r` is `Runnable` with no subtype relationship | No | Java does not cast/convert based on two interfaces sharing a signature |
| `A a = permittedSubtypeLambda;`, where subtype is a non-sealed functional interface extending A | Yes at upcast | Lambda is created under the subtype target type, then assigned to the supertype |

The case `non-sealed interface B extends A` is only valid when `A` is a sealed direct superinterface and `B` is permitted to extend it. You cannot add the `non-sealed` keyword to an arbitrary interface that has no sealed direct superinterface.

## 7. Why Doesn't Java Automatically Turn a Lambda into a Permitted Subtype?

A common misconception is: “If the compiler already knows `permits`, why doesn't it just instantiate one of the permitted subtypes?”

A lambda expression **is not a constructor call for a permitted class**. It uses a functional interface type as its target type and the runtime provides an object implementing that contract; implementation details may vary across JDKs and should not become an API contract.

For a `sealed interface`, the language wants **direct** inheritance branches to be explicitly named and controlled by `permits`. If you want to use lambda behavior in a sealed hierarchy, the author must **explicitly specify a valid path**:

- Expose a permitted `non-sealed` subinterface with a SAM so callers can use lambdas as values of that subtype; or
- Expose a constructor/factory of a permitted class and have that class accept a functional interface as a behavioral strategy.

Thus, we do not equate “adding another calculation” with “adding another direct subtype”. For domain models that need tight control over object kinds (such as command or result types), the second approach often makes hierarchy invariants easier to enforce.

**Do not overgeneralize:** A sealed interface can perfectly well declare abstract methods, default methods, and generic parameters, and be implemented by concrete classes. It is only ineligible to be a functional interface **when the sealed interface itself is used as the target type for a lambda/method reference**.

## 8. Common Mistakes and How to Check Them

### Mistake 1: Counting One SAM and Concluding a Lambda Can Be Used

~~~java
// Intentionally invalid illustration when adding the annotation.
@FunctionalInterface
sealed interface SealedOp permits ConcreteOp {
    void run();
}

final class ConcreteOp implements SealedOp {
    public void run() {}
}
~~~

Even though `run()` is the single SAM, the annotation is rejected: a sealed interface is not a functional interface. The fix depends on the design goal: if direct lambdas are needed, use a non-sealed interface; if sealed is needed, provide a permitted class or a permitted non-sealed subinterface.

### Mistake 2: Casting a Lambda to a Sealed Interface

~~~java
// Invalid illustration; not a standalone runnable program.
// ClosedAction a = (ClosedAction) (text -> text);
~~~

Casting does not bypass the target-type condition. If the cast type is the sealed `ClosedAction`, it is still not a functional interface. Conversely, casting a lambda to a **non-sealed functional subinterface** can be valid, and the result can then be assigned to a variable of the sealed superinterface type.

### Mistake 3: Thinking Not Being Able to Use Lambdas Means Instances Cannot Be Created

~~~java
// Valid illustration in the scope of InvalidSealedTarget,
// after removing the failing lambda assignment line:
ClosedAction action = new DefaultAction();
System.out.println(action.apply("Java"));
~~~

This snippet calls the permitted class and prints `default:Java`. The issue lies solely in creating a value via a lambda with an invalid target type, not in the ability to have instances of a sealed interface.

### Mistake 4: Thinking `permits` Blocks All Indirect Subtypes

If a sealed interface permits `non-sealed interface Extension` to directly inherit from it, classes implementing `Extension` can become **indirect** subtypes of the sealed interface. That is exactly the mechanism in `OpenJob`. Conversely, if all permitted branches are closed with `final` or remain `sealed`, that same open extensibility does not exist.

### Mistake 5: Thinking Method References Follow Different Rules from Lambdas

`String::trim` or `System.out::println` also requires a functional interface type at the usage site. Switching from lambda syntax to method reference syntax will not turn a sealed interface into a valid target type.

### Mistake 6: Attributing the Annotation's Role to the `sealed` Keyword

`@FunctionalInterface` is an annotation that checks the SAM contract; `sealed` is a modifier restricting direct subtypes. They are two distinct language mechanisms; one does not “override” or disable the other. For a sealed interface, the `@FunctionalInterface` condition is simply not met.

### Mistake 7: Assuming Java 8 Supports `sealed` Examples

`sealed`, `non-sealed`, and `permits` became standard features in Java 17. The runnable programs in this lesson are designed for JDK 17+; if using JDK 8 or 11, syntax errors stem from the language version, not just lambda rules.

## 9. When Should You Choose Each Design?

**Choose a regular functional interface** when the primary job is passing behavior/callbacks and you want callers to supply lambdas easily. You can add `@FunctionalInterface` to have the compiler protect the contract.

**Choose a sealed hierarchy** when the domain needs to control the *direct object kinds* in the hierarchy and organize logic around known branches. Implementing classes along the hierarchy are required; a lambda targeting the sealed root directly does not fit.

**Choose a sealed root + permitted `non-sealed` functional subinterface** when the domain allows one open extension branch while the root's direct branches must still be declared. This allows direct lambdas for the open branch.

**Choose a sealed root + permitted concrete adapter** when you want to keep the list of direct types closed while customizing processing logic via `Function`, `Predicate`, `IntUnaryOperator`, or a custom functional interface. This combines type-hierarchy control with behavior configuration without conflating the two contracts.

Before choosing, answer two separate questions: “Which **subtypes** do I want to restrict?” and “Which **behaviors** do I want callers to pass?”. If only behavior is needed, `sealed` may be an unnecessary constraint. If the domain requires a finite set of object kinds, explicit classes/factories usually make invariants easier to verify.

## 10. Self-Check Exercises

1. A `sealed interface` has only `void run();` and no other methods. Can `() -> {}` be assigned directly to that type? Which condition is missing?
2. Why can `@FunctionalInterface` not make a `sealed interface` declaration into a valid target type?
3. Given `sealed interface Root permits Extension` and `non-sealed interface Extension extends Root` inheriting one SAM, is `Extension e = () -> {}; Root r = e;` valid? Identify the target type when the lambda is created.
4. If `Root` permits only a single `final` class, how can callers configure behavior with lambdas while keeping the root sealed?
5. Why does replacing `() -> ...` with `SomeType::method` not solve the sealed target-type issue?
6. If `sealed` is removed from the root while keeping two distinct abstract methods, is the lambda valid?

**Suggested answers:** (1) No: `sealed` excludes that type from the functional interface definition. (2) The annotation only checks; it does not change the definition. (3) Yes, if `Extension` has one SAM; the lambda has target type `Extension` and is then upcast to `Root`. (4) Use a permitted class with a constructor/factory that accepts a functional interface as a strategy. (5) Method references also require a functional interface type. (6) No: the single-SAM condition is still missing.

## 11. Specification References

- [JLS Java SE 17, `9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): definition of a functional interface including the non-`sealed` requirement.
- [JLS Java SE 17, `15.27.3 — Type of a Lambda Expression](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27.3): compatibility conditions between a lambda and a target functional interface type.
- [JLS Java SE 17, `9.1.1.4 — sealed and non-sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): rules for direct inheritance branches of a sealed interface.

**Takeaway:** “Exactly one SAM” is not enough. **A sealed interface is never a functional interface**, so it cannot serve as the direct target type of a lambda or method reference. Java still allows using lambdas within a sealed design via a **permitted non-sealed functional subinterface** or a **functional interface passed into a permitted class**.