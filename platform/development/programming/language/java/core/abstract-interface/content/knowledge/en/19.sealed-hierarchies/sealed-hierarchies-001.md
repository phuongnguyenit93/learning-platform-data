# Sealed hierarchy in Java 17: controlling direct subtypes

## 1. The problem sealed solves

In object-oriented design, polymorphism allows a variable of a parent type to reference multiple subtypes. However, there are domain models in which the set of valid subtypes needs to be clearly restricted. For example, an expression may only be a number or an addition; a payment may only belong to certain types recognized by the system.

If a regular class or interface is used, any code that satisfies access and inheritance conditions can declare additional subtypes. That sometimes makes the model difficult to control: processing code may encounter an unexpected type, business rules become scattered, or a public API unintentionally allows extensions that the author did not intend to support.

Java 17 standardizes **sealed classes and sealed interfaces** to restrict the set of types allowed to directly extend or implement a type. The `sealed` keyword indicates that the parent type has a list of permitted direct subtypes. That list is declared with `permits`, or inferred by the compiler in valid cases.

Sealed does not eliminate polymorphism. It allows continuing to use a common parent type while establishing clear boundaries for the inheritance tree. Each branch can then be closed completely, further restricted with sealed, or freely extended with non-sealed.

## 2. Basic syntax

~~~java
public sealed class Shape
        permits Circle, Rectangle {
    // Shared state and behavior of Shape
}

public final class Circle extends Shape {
    // This branch does not allow further inheritance
}

public non-sealed class Rectangle extends Shape {
    // This branch allows other types to inherit further
}
~~~

This is an example illustrating syntax, and the public types must be placed in their corresponding files if used as written. A sealed class can be abstract or concrete. When declared abstract, you can still restrict the types permitted to extend it, but cannot instantiate the parent type directly.

The keywords have different meanings:

- `sealed`: this type restricts which types are permitted to directly extend or implement it.
- `permits`: lists the permitted direct subtypes.
- `final`: this subtype cannot have further subclasses.
- `non-sealed`: reopens the inheritance branch at this subtype; other types can extend or implement it according to the normal rules.
- `sealed` on a subtype: continues to place restrictions on the next generation of subtypes.

A permitted direct subtype of a sealed class must be `final`, `sealed`, or `non-sealed`. A record is already implicitly a final type, so a record can directly implement a sealed interface without writing the `final` keyword.

## 3. Controlling direct subtypes, not all descendants

The core effect of sealed is to control **direct subtypes**. A multi-level inheritance tree can still exist; the rules of each branch determine how that tree continues to expand.

~~~java
sealed class Message permits EmailMessage, SystemMessage {
}

final class EmailMessage extends Message {
}

non-sealed class SystemMessage extends Message {
}

class AlertMessage extends SystemMessage {
}
~~~

In this example:

- `Message` only permits `EmailMessage` and `SystemMessage` to extend it directly.
- `EmailMessage` is final, so it cannot have subclasses.
- `SystemMessage` is non-sealed, so this branch is reopened. `AlertMessage` can extend `SystemMessage`, but that does not make it a listed direct subtype of `Message`.

If `SystemMessage` is replaced with a sealed subtype, that subtype must have a list of types permitted to extend it. Thus, sealed allows restricting the inheritance tree across multiple levels, while non-sealed opens a specific branch. The same class cannot be declared final, sealed, and non-sealed at the same time; they are mutually exclusive choices for that type's inheritance capability.

## 4. Sealed interfaces also restrict the set of implementing types

Sealed applies to both classes and interfaces. With a sealed interface, the `permits` list can contain directly implementing classes or direct subinterfaces. Permitted types must follow the corresponding rules: a directly implementing class needs to be final, sealed, or non-sealed; a subinterface needs to be sealed or non-sealed because an interface cannot be final.

~~~java
sealed interface Result permits Success, Failure {
}

record Success(String value) implements Result {
}

record Failure(String reason) implements Result {
}
~~~

Both records above are implicitly final. Therefore, they are closed leaves of the `Result` hierarchy: external code cannot create another record that extends Success or Failure, and cannot add an arbitrary direct implementation for Result.

A sealed interface is useful when an API needs to represent a known set of cases. For example, a processing result may be success or failure; a command may belong to a defined set of types; a domain event may fall within a managed set of types. Calling code can still receive values through the common interface, while the API author controls which types are allowed to appear directly in the hierarchy.

## 5. Runnable Java 17 example

The program below uses a sealed interface to represent two payment types. The records are permitted direct subtypes and provide immutable data for each case.

~~~java
import java.math.BigDecimal;

sealed interface Payment permits CardPayment, CashPayment {
}

record CardPayment(String lastFour) implements Payment {
}

record CashPayment(BigDecimal amount) implements Payment {
}

public class PaymentDemo {
    public static void main(String[] args) {
        Payment card = new CardPayment("4242");
        Payment cash = new CashPayment(new BigDecimal("12.50"));

        printPayment(card);
        printPayment(cash);
    }

    private static void printPayment(Payment payment) {
        if (payment instanceof CardPayment card) {
            System.out.println("Card ending in " + card.lastFour());
        } else if (payment instanceof CashPayment cash) {
            System.out.println("Cash amount: " + cash.amount().toPlainString());
        } else {
            throw new IllegalStateException(
                    "Unexpected payment type: " + payment.getClass().getName());
        }
    }
}
~~~

Save the entire program to the file `PaymentDemo.java`, then compile and run it with JDK 17 or later:

~~~text
javac PaymentDemo.java
java PaymentDemo
~~~

Stdout output:

~~~text
Card ending in 4242
Cash amount: 12.50
~~~

Here, the `payment` variable has declared type Payment but can reference CardPayment or CashPayment. The `printPayment` method uses pattern matching for `instanceof`, a feature finalized since Java 16. The final branch still guards against unexpected types at runtime; sealed lets the compiler know the valid set of direct subtypes, but an `if/else` chain is not automatically verified by the compiler as exhaustive.

Pattern matching for `switch` is still a preview feature in Java 17. You should not use type-pattern switch syntax as if it were already standard Java 17 syntax without preview flags. The example above uses only standard Java 17 syntax and does not require enabling preview.

## 6. Rules for permits and declaration placement

Typically, write the list of direct subtypes explicitly:

~~~java
sealed interface Command permits StartCommand, StopCommand {
}
~~~

The names in `permits` must identify the permitted direct subtypes. Declaring the list does not automatically create those types; they must actually exist and properly extend or implement the parent type. The compiler checks these relationships.

In cases where all direct subtypes are declared in the same compilation unit, `permits` can be omitted so that the compiler infers the list. Conceptual example:

~~~java
sealed interface Command {
}

final class StartCommand implements Command {
}

final class StopCommand implements Command {
}
~~~

When using the inferred form, keep the direct subtype declarations in the same source file as the sealed type so the compiler can infer the permitted set. If the types are in different files, declare `permits` explicitly.

Permitted subtypes must also obey Java's module/package boundaries:

- In a named module, the sealed type and its permitted subtypes must belong to the same module; they may reside in different packages within that module.
- When running in an unnamed module, the sealed type and its permitted subtypes must belong to the same package.

These rules make it possible to check the set of permitted subtypes at compile time and help prevent a type in an inappropriate module or package from arbitrarily extending the hierarchy.

## 7. Comparing final, sealed, and non-sealed

| Modifier | Inheritance capability | When to use |
|---|---|---|
| `final` | Does not allow subtypes to inherit further. | A leaf type that is complete and needs no extension. |
| `sealed` | Only permitted types may directly extend or implement it. | When a controlled set of subtypes is needed. |
| `non-sealed` | Reopens inheritance capability at this branch. | When wanting to restrict the parent's direct branches while allowing one branch to be extended freely. |

Choose the modifier according to the contract the API wants to expose. Use final when a type needs to be completely closed. Use sealed when the valid subtypes have been determined and should be controlled. Use non-sealed when an intentional extension point is needed inside a sealed hierarchy.

Sealed does not replace access modifiers such as public, protected, or private. Access permissions determine which code can see or use a type; sealed determines which types are permitted to become direct subtypes. The two sets of rules solve different problems and can both apply to an API.

## 8. Benefits and limitations in design

**The main benefit** is clarifying the boundaries of the domain model. When the set of direct subtypes is controlled, API readers know which cases are supported by the author. Adding a new case to the hierarchy also becomes an intentional change, rather than an arbitrary implementation type being able to appear from external code.

Sealed also supports exhaustiveness analysis in language features that understand sealed hierarchies, such as pattern matching for switch in Java versions that support that feature. However, this benefit should not be confused with every conditional construct being proven exhaustive by the compiler. An if/else chain like the example above may still need a fallback branch.

**A limitation to consider** is that sealed creates an extensibility constraint. If a library design inherently needs to allow third parties to freely add implementations, closing the subtype list may not be appropriate. In a published library, changing the list of permitted subtypes can also affect users' source code or binaries depending on how the hierarchy is used. Therefore, decide the extension boundaries right when designing the API and clearly document which branches are open and which are closed.

Do not use sealed just because you can. It is valuable when restricting subtypes reflects a real business rule or API contract. For an abstraction that needs to be extended arbitrarily, a regular class or interface may be a more suitable choice.

## 9. Common mistakes

- **Forgetting to declare how a direct subtype handles inheritance.** A permitted class needs to be final, sealed, or non-sealed. A record is implicitly final; a subinterface cannot be declared final.
- **Confusing permits with a list of all descendants.** permits only lists direct subtypes. Subsequent generations are controlled by the modifier on each branch.
- **Placing a subtype outside the permitted module/package.** Check the named module or unnamed module rules when the compiler reports an error about subtype placement.
- **Using non-sealed while expecting that branch to stay closed.** non-sealed intentionally reopens inheritance at the marked branch.
- **Assuming sealed automatically makes all switch handling exhaustive in Java 17.** Pattern matching for switch in Java 17 is still a preview feature; use the appropriate version and compiler options if actively trying preview features.
- **Assuming sealed is an access authorization mechanism.** It restricts valid subtypes; it does not replace access control, authentication, or authorization at the application layer.

## 10. Key takeaways

Java 17 sealed classes/interfaces restrict which types can directly extend or implement a parent type. That list is stated using `permits` or inferred when the direct subtypes are in the same compilation unit. Each direct branch further determines extensibility: final closes the branch, sealed continues to restrict it, and non-sealed reopens the branch. This mechanism preserves polymorphism while making the boundaries of the type hierarchy clear and checkable at compile time.
