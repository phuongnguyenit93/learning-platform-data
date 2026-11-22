# Permitted Extension Branches and Limitations of Anonymous Classes and Lambdas

## Objectives

In Java, `sealed` allows a class or interface to control which types can extend or implement it directly. Both anonymous classes and lambdas help create behavior inline, but they cannot bypass the rules of a `sealed` hierarchy.

After this lesson, you will be able to distinguish:
- direct subtypes declared in `permits` from indirect subtypes;
- the limitations of anonymous classes when extending a `sealed` type;
- why a lambda cannot directly implement a sealed interface;
- how to intentionally open an extension branch using `non-sealed`.

## 1. Direct vs. Indirect Determines Extensibility

~~~java
sealed interface Payment permits CardPayment, ExternalPayment {}

final class CardPayment implements Payment {}

non-sealed class ExternalPayment implements Payment {}
~~~

`Payment` permits only two named direct implementing types. `CardPayment` closes its branch, while `ExternalPayment` opens its branch. A class under `ExternalPayment` is an **indirect** descendant of `Payment` and does not need to be listed again in `permits`. An anonymous class can extend `ExternalPayment`; conversely, it cannot create a new direct subtype of `Payment` on its own. A lambda also respects the boundaries of the target type, but it has its own rule regarding functional interfaces, explained below.

## 2. Limitations of Anonymous Classes

An anonymous class is an unnamed class declared right at an object creation expression. A typical example:

~~~java
Runnable task = new Runnable() {
    @Override
    public void run() {
        System.out.println("running");
    }
};
~~~

This is valid because `Runnable` is an interface that is not sealed. However, an anonymous class cannot become a direct subtype of a `sealed` class or interface. A direct subtype must be a named type permitted in the hierarchy; an anonymous class cannot be listed as a specific type in the `permits` clause.

The following example is **invalid**:

~~~java
sealed interface Command permits StartCommand {
}

final class StartCommand implements Command {
}

class Main {
    public static void main(String[] args) {
        Command command = new Command() {
            // Anonymous class trying to implement Command directly.
        };
    }
}
~~~

The compiler rejects the anonymous class because the newly created type is not a permitted direct subtype. Adding an object to the `permits` list does not solve the problem either: `permits` lists types, not objects, and an anonymous class has no source name to declare there.

An anonymous class can still extend or implement a type that is **not sealed**, even when that type is an extension branch of a sealed hierarchy. This is an intentional form of extension rather than breaking the defined boundaries.

## 3. Why Do Lambdas Have Different Limitations?

A lambda expression is not syntax for creating an arbitrary subclass. A lambda provides an implementation for a **functional interface** — an interface with a single abstract method suitable as a functional contract.

Example:

~~~java
@FunctionalInterface
interface Handler {
    void handle();
}

class Main {
    public static void main(String[] args) {
        Handler handler = () -> System.out.println("handled");
        handler.handle();
    }
}
~~~

Here, the lambda implements the `handle()` contract of `Handler`. A lambda does not extend a class, nor does it provide a subtype name to list in `permits`.

A sealed interface cannot serve as a target functional interface for a lambda: Java's definition of a functional interface excludes `sealed` interfaces. Therefore, a lambda cannot be used to create a direct implementing type for a sealed interface. If you try to assign a lambda to a sealed interface, the program will not compile.

This does not mean that lambdas are completely forbidden in a sealed hierarchy. A lambda can target a `non-sealed` functional interface located in a permitted branch. In that case, the direct type beneath the sealed interface is the named `non-sealed` interface; the lambda merely supplies behavior for that extensible interface.

## 4. Opening a Valid Branch for Anonymous Classes and Lambdas

The following complete example illustrates that design. Save all the code in `Main.java`:

~~~java
sealed interface Job permits BuiltInJob, ExtensibleJob {
}

record BuiltInJob(String name) implements Job {
}

@FunctionalInterface
non-sealed interface ExtensibleJob extends Job {
    void execute();
}

public class Main {
    public static void main(String[] args) {
        ExtensibleJob lambdaJob =
                () -> System.out.println("lambda job");

        ExtensibleJob anonymousJob = new ExtensibleJob() {
            @Override
            public void execute() {
                System.out.println("anonymous job");
            }
        };

        lambdaJob.execute();
        anonymousJob.execute();

        Job builtIn = new BuiltInJob("report");
        System.out.println(builtIn instanceof BuiltInJob);
    }
}
~~~

Compile and run with JDK 17 or later:

~~~text
javac Main.java
java Main
~~~

Exact standard output:

~~~text
lambda job
anonymous job
true
~~~

Analysis of the example:

1. `Job` is a sealed interface. The two permitted direct subtypes are `BuiltInJob` and `ExtensibleJob`.
2. `BuiltInJob` is a record, so it is automatically `final`; it does not extend the hierarchy any further.
3. `ExtensibleJob` is declared `non-sealed`, so other types can implement this interface. It has exactly one abstract method, `execute()`, so it can be used as a target for a lambda.
4. `lambdaJob` provides the method body with a lambda. `anonymousJob` uses an anonymous class to implement the same extensible interface. Both objects are `Job` instances through an indirect type relationship via `ExtensibleJob`.
5. The expression `builtIn instanceof BuiltInJob` prints `true`, because the created object is a `BuiltInJob`.

This design maintains a clear boundary: the sealed interface permits only two named direct branches, but a `non-sealed` branch can allow flexible implementations such as lambdas and anonymous classes.

## 5. Quick Comparison

| Case | Valid? | Reason |
|---|---|---|
| Anonymous class directly implementing a sealed interface | No | An anonymous class cannot be declared as a permitted direct subtype |
| Anonymous class implementing a `non-sealed` interface in the hierarchy | Yes | The direct supertype of the anonymous class is a permitted open branch |
| Lambda targeting a sealed interface | No | A sealed interface cannot be a target functional interface |
| Lambda targeting a `non-sealed` functional interface in the hierarchy | Yes | An open functional interface can accept an implementation from a lambda |
| A `final` type declared in `permits` | Yes | A named direct subtype that closes the inheritance branch |
| A `non-sealed` type declared in `permits` | Yes | A named direct subtype that opens further sub-branches |

## 6. Common Mistakes and How to Handle Them

**Trying to put an anonymous class into `permits`.** This clause declares direct subtypes by type name; it does not accept object creation expressions. Declare a named class or interface as a direct branch if another branch is needed.

**Assuming a lambda can implement any interface.** Lambdas are only compatible with functional interfaces. A sealed interface cannot act as a target functional interface; determine whether the branch genuinely needs to be closed or needs to be opened.

**Marking a direct branch as `final` and expecting an anonymous class to extend it.** `final` forbids all subtypes. If the design needs to allow custom implementations, consider a `non-sealed` direct subtype with a clear name.

**Using `non-sealed` without considering the consequences.** Once a branch is opened, other code can add subtypes that the sealed parent does not list directly. Only open a branch when this is an intended extension of the API.

**Confusing sealed with forbidding all subtypes.** Sealed does not eliminate inheritance; it controls direct subtypes. Branches marked `non-sealed` can be extended further, while `final` closes a branch and `sealed` continues to control it.

## 7. Decision Process

1. Identify which type is the sealed parent and read the `permits` list.
2. For each direct subtype, verify that it is named and declared `final`, `sealed`, or `non-sealed` according to the design.
3. If a lambda is needed, check whether the target type is a functional interface and is not sealed.
4. If an anonymous class is needed, check whether the type that the anonymous class directly extends or implements is an open branch.
5. When you need to extend a sealed hierarchy, create a named direct branch and intentionally mark it `non-sealed`.
6. Compile with JDK 17+ to detect sealed rule violations; then run the program and compare stdout.

## Key Takeaways

Anonymous classes and lambdas cannot bypass the boundaries of a sealed hierarchy. An anonymous class cannot be a direct subtype of a sealed type; a lambda cannot target a sealed interface because a sealed interface is not a functional interface. The valid way to extend is to declare a named direct subtype, allow it to be `non-sealed` when you genuinely want to support additional implementations, and then use an anonymous class or a lambda with that open branch.
