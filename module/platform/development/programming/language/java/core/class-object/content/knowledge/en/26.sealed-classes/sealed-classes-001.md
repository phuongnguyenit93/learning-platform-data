# Purpose of Controlling the Set of Direct Subclasses with `sealed` in Java 17+

When designing an object-oriented system, a public class or interface can normally be inherited or implemented by many new types. This openness is useful for extension, yet there are also times when **the set of valid variants is part of the domain model**: for example, only two result groups are allowed, a defined set of command types exists, or a syntax tree has clear node categories.

Starting in Java 17, `sealed` is a standard feature that helps **control precisely which classes or interfaces are allowed to directly extend a class, or directly implement/extend an interface**. The key term is **directly**: `sealed` restricts *direct subclasses* or *direct subtypes*, rather than automatically turning all multi-level descendants into a closed list if a branch is declared `non-sealed`.

~~~java
sealed interface PaymentResult permits Paid, Rejected {
}

record Paid(String receipt) implements PaymentResult {
}

record Rejected(String reason) implements PaymentResult {
}
~~~

These are **valid Java 17 declarations**, without `main`. The `PaymentResult` interface permits precisely `Paid` and `Rejected` to **directly implement** it in this hierarchy. Both records are implicitly final, so no subclass can inherit from them. If another class writes `implements PaymentResult` without being permitted, the compiler will reject it.

This lesson belongs to **Java core – class-object**, the **Sealed classes** group, topic **Purpose of controlling the set of direct subclasses**. The focus includes the `sealed` keyword, the `permits` list, the direct/indirect subtypes boundary, the `final`/`sealed`/`non-sealed` choices, package/module rules, its role in data model design, and what `sealed` **does not guarantee**. The standalone programs run on **Java 17+**, without enabling preview features. Snippets with intentional compilation errors are clearly marked.

## 1. Learning Objectives

After this lesson, you should be able to:

1. Explain that `sealed` controls **direct subtypes**, rather than blocking all polymorphism.
2. Correctly write `sealed class X permits A, B` with `A extends X`, `B extends X`.
3. Write `sealed interface I permits A, B` along with a class that `implements I` and an interface that `extends I`.
4. Distinguish `final`, `sealed`, and `non-sealed` at each direct permitted subtype.
5. Analyze multiple inheritance levels, where a branch is closed or reopened.
6. Know when `permits` can be inferred within the same compilation unit.
7. Know the location constraints of permitted subtypes in a **named module** and an **unnamed module**.
8. Explain that a sealed class is **not necessarily abstract** and can be instantiated if its constructor allows it.
9. Distinguish a sealed class from an enum, record, abstract class, and open interface.
10. Understand the impact on `instanceof`, pattern matching, switch, and API evolution in Java 17.
11. Avoid equating a closed hierarchy with a security boundary or access control.
12. Design a minimal, readable sealed hierarchy that aligns with domain invariants.

## 2. Before `sealed`: A Superclass Open to Many Subclasses

Java supports class inheritance:

~~~java
class Message {
}

class EmailMessage extends Message {
}

class SmsMessage extends Message {
}
~~~

The three declarations are valid Java. If `Message` is not `final` and an appropriate constructor is accessible, a fourth class can also write `extends Message` wherever scope allows.

In an extension-oriented framework or library, this flexibility is often **intentional and desirable**. However, in a closed domain, the emergence of unmodeled subtypes can force many pieces of code to rely on `else` or dynamic casts, and it cannot be certain that all variants have been covered.

Switching to:

~~~java
sealed class Message permits EmailMessage, SmsMessage {
}

final class EmailMessage extends Message {
}

final class SmsMessage extends Message {
}
~~~

Now only **EmailMessage** and **SmsMessage** are the two direct permitted subclasses. Other types **cannot** directly extend Message unless the `permits` definition is changed according to Java's rules.

**Do not assume** that every system should close extension: sealed is a domain design decision. If your library intentionally lets users create plugin classes, sealing the superclass can defeat the goal of extensibility.

## 3. The Keywords `sealed`, `permits`, `final`, `non-sealed`

| Keyword | Role |
| --- | --- |
| `sealed` | Restricts the set of direct permitted subtypes |
| `permits` | Lists the permitted direct subtypes |
| `final` | Disallows any class from inheriting from this class |
| `non-sealed` | A permitted direct child chooses to reopen inheritance/implementation like a normal type |
| `abstract` | Prevents directly instantiating the class; does not restrict subtypes on its own |
| `extends` | Declares the direct superclass of a class, or the superinterface of an interface |
| `implements` | Declares the interfaces that a class directly implements |

Example:

~~~java
sealed abstract class Event permits LoginEvent, OtherEvent {
}

final class LoginEvent extends Event {
}

non-sealed class OtherEvent extends Event {
}
~~~

These are three valid declarations. `LoginEvent` is a **completely closed branch** due to final; `OtherEvent` is a **reopened branch** due to non-sealed.

An arbitrary class cannot simply declare `non-sealed` at will: this modifier is reserved for a class/interface that has a **direct sealed supertype** which it is permitted to extend/implement. Without a direct sealed supertype, `non-sealed` has no semantic basis and is rejected.

## 4. Standalone Program 1 — Two Permitted Direct Subclasses

File **`SealedPaymentDemo.java`**:

~~~java
sealed abstract class Payment permits CashPayment, CardPayment {
    abstract String description();
}

final class CashPayment extends Payment {
    @Override
    String description() {
        return "Cash";
    }
}

final class CardPayment extends Payment {
    @Override
    String description() {
        return "Card";
    }
}

public class SealedPaymentDemo {
    public static void main(String[] args) {
        Payment first = new CashPayment();
        Payment second = new CardPayment();

        System.out.println("first=" + first.description());
        System.out.println("second=" + second.description());
        System.out.println("same type="
                + (first.getClass() == second.getClass()));
        System.out.println("cash is Payment="
                + (first instanceof Payment));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SealedPaymentDemo.java
java SealedPaymentDemo
~~~

**Stdout:**

~~~text
first=Cash
second=Card
same type=false
cash is Payment=true
~~~

`Payment` is a sealed abstract class; the compiler permits the two direct subclasses CashPayment and CardPayment because they are in permits. Both subclasses are final, so they do not open the inheritance tree further.

**The purpose of sealed is not to eliminate polymorphism:** a variable of type Payment can still reference two runtime types and invoke `description()` via dynamic dispatch.

## 5. Precisely: What Is a Direct Subclass?

Consider the tree:

~~~text
                 Payment               sealed
                /       \
      CashPayment     CardPayment       direct subclasses
           |               |
       (final)           (final)

Only the two types at the level immediately below Payment need to be permitted directly.
~~~

For a class, a **direct subclass** is a class that has `extends Payment` directly. For an interface, a **direct subtype** in the context of sealed can be either a class that directly `implements I` or an interface that directly `extends I`.

Suppose `Payment` permits `OnlinePayment` as a direct child, and OnlinePayment declares `non-sealed`. Then `NewProviderPayment extends OnlinePayment` is an **indirect descendant** of Payment. NewProviderPayment **does not need** to be listed in `Payment permits ...` because it does not directly extend Payment.

This is the key distinction of this lesson: **permits only controls a single inheritance edge from a sealed parent to a direct child**, not a full whitelist of every class at every depth of the hierarchy.

## 6. Standalone Program 2 — `non-sealed` Reopens a Branch

File **`NonSealedBranchDemo.java`**:

~~~java
sealed abstract class Delivery permits Pickup, Courier {
    abstract String mode();
}

final class Pickup extends Delivery {
    @Override
    String mode() {
        return "pickup";
    }
}

non-sealed class Courier extends Delivery {
    @Override
    String mode() {
        return "courier";
    }
}

final class ExpressCourier extends Courier {
    @Override
    String mode() {
        return "express";
    }
}

public class NonSealedBranchDemo {
    public static void main(String[] args) {
        Delivery a = new Pickup();
        Delivery b = new Courier();
        Delivery c = new ExpressCourier();

        System.out.println(a.mode());
        System.out.println(b.mode());
        System.out.println(c.mode());
        System.out.println("express is Delivery="
                + (c instanceof Delivery));
        System.out.println("express direct parent="
                + c.getClass().getSuperclass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NonSealedBranchDemo.java
java NonSealedBranchDemo
~~~

**Stdout:**

~~~text
pickup
courier
express
express is Delivery=true
express direct parent=Courier
~~~

`Delivery permits Pickup, Courier`, **without** `ExpressCourier`. It still compiles properly because ExpressCourier directly extends **Courier**, a permitted child declared `non-sealed`. Courier can have many other subclasses according to normal Java inheritance rules.

**Conclusion:** a sealed hierarchy with a non-sealed branch **is not a closed set of all concrete classes**. It only closes the list of **direct children** at the sealed node.

## 7. Why Must a Permitted Child Choose One of Three Paths?

A class or interface that directly extends/implements a sealed supertype must explicitly indicate whether extension **stops, continues to be controlled, or is reopened**.

The options:

1. `final class`: no further valid subclasses.
2. `sealed class` / `sealed interface`: continues to allow only the specified direct subtypes.
3. `non-sealed class` / `non-sealed interface`: returns to an open state on that branch.

There is no `final interface` in Java. Therefore, a **permitted subinterface** must choose `sealed` or `non-sealed`; meanwhile, a **permitted record/enum** inherently has its own implicitly final or implicitly sealed rules depending on its form (see later).

A common mistake:

~~~java
sealed class Base permits Child {
}

class Child extends Base {
}
~~~

This is an **intentionally non-compiling snippet**. Child is listed in permits, yet it does not carry an appropriate modifier (`final`, `sealed`, `non-sealed`) to tell the compiler whether subclassing from Child is still permitted or not.

A simple fix if Child does not need subclasses: `final class Child extends Base {}`.

## 8. `sealed` Can Also Repeat Across Multiple Levels

Not every permitted direct child has to be final. A child can be sealed and define its own `permits` list:

~~~text
          sealed Expression
           /            \
   final Literal      sealed Binary
                        /       \
                    final Add  final Multiply
~~~

In this tree:
- Expression only allows Literal and Binary as **direct children**.
- Binary only allows Add and Multiply as **direct children** of Binary.
- Literal/Add/Multiply are final, so they do not allow further inheritance.

The tree can be as deep as the design calls for. Each sealed node **independently closes its own set of direct children**. If any path chooses non-sealed, deeper subclasses along that branch are no longer subject to the root node's whitelist.

Choosing a multi-level structure is useful when the domain has **real conceptual levels**, for example Expression → Binary → Add/Multiply. There is no need to create a new sealed level just to make code “look modern”.

## 9. Standalone Program 3 — Multi-Level Sealed Hierarchy

File **`SealedExpressionDemo.java`**:

~~~java
sealed interface Expr permits Literal, Binary {
    int evaluate();
}

record Literal(int value) implements Expr {
    @Override
    public int evaluate() {
        return value;
    }
}

sealed interface Binary extends Expr permits Sum, Product {
}

record Sum(Expr left, Expr right) implements Binary {
    @Override
    public int evaluate() {
        return left.evaluate() + right.evaluate();
    }
}

record Product(Expr left, Expr right) implements Binary {
    @Override
    public int evaluate() {
        return left.evaluate() * right.evaluate();
    }
}

public class SealedExpressionDemo {
    public static void main(String[] args) {
        Expr two = new Literal(2);
        Expr three = new Literal(3);
        Expr sum = new Sum(two, three);
        Expr product = new Product(sum, new Literal(4));

        System.out.println("sum=" + sum.evaluate());
        System.out.println("product=" + product.evaluate());
        System.out.println("sum implements Binary="
                + (sum instanceof Binary));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SealedExpressionDemo.java
java SealedExpressionDemo
~~~

**Stdout:**

~~~text
sum=5
product=20
sum implements Binary=true
~~~

`Expr` permits precisely Literal and Binary. `Binary` is a **direct subinterface** of Expr and is permitted by Expr, yet it is itself sealed to restrict its direct children to Sum and Product.

The two records Sum/Product are implicitly final: they do not need to write `final` explicitly. This combination of **sealed interface + record** is often useful for representing data structures with a clear set of variants.

## 10. How Do a Sealed Class and a Sealed Interface Differ?

**Sealed class:**
- A direct subclass must use `extends` for that class and be in permits.
- A Java class has **one** direct superclass.
- The parent class can have state, constructors, and shared implementations.
- A sealed class can be abstract or concrete.

**Sealed interface:**
- A direct implementing class or direct extending interface must be valid according to permits.
- A Java class can implement **multiple interfaces** (subject to the sealed rules of each interface).
- An interface does not have instance constructors/instance fields like a class.
- A sealed interface is very well suited for **sum type-like models**: a value can belong to one of several recognized variants.

For both, permits does not grant access to private members. It is a **declaration constraint on the subtype relationship**, and does not replace `public`, `protected`, package-private, or `private`.

## 11. Standalone Program 4 — A Sealed Interface with Two Record Variants

File **`ResultVariantsDemo.java`**:

~~~java
sealed interface ApiResult permits Success, Failure {
}

record Success(String value) implements ApiResult {
}

record Failure(int code, String message) implements ApiResult {
}

public class ResultVariantsDemo {
    static String describe(ApiResult result) {
        if (result instanceof Success success) {
            return "OK:" + success.value();
        }
        if (result instanceof Failure failure) {
            return "ERROR:" + failure.code()
                    + ":" + failure.message();
        }
        throw new IllegalStateException("Unknown variant");
    }

    public static void main(String[] args) {
        ApiResult a = new Success("saved");
        ApiResult b = new Failure(404, "missing");

        System.out.println(describe(a));
        System.out.println(describe(b));
        System.out.println("same variant="
                + (a.getClass() == b.getClass()));
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 ResultVariantsDemo.java
java ResultVariantsDemo
~~~

**Stdout:**

~~~text
OK:saved
ERROR:404:missing
same variant=false
~~~

In **Java 17**, the pattern variable `success` or `failure` in `instanceof` is already a standard feature, with no preview required. The describe method handles the two known variants and has a `throw` path if the assumption about the hierarchy no longer holds.

However, **Java 17 does not have general exhaustiveness checking for if/instanceof chains**. If a permitted variant is added later, you yourself still have to verify the logic of the describe method. Furthermore, sealed does not forbid the `ApiResult result` variable from holding `null`, so `null` will reach `throw` in this example.

## 12. Design Purpose: Making the Set of Variants Meaningful

Why would a domain want to restrict direct subtypes?

**1. Expressing a clear contract.** When an API states that a result is Success or Failure, everyone shares the understanding that the set of **direct variants** has been described, rather than allowing any arbitrary plugin to directly implement ApiResult.

**2. Protecting assumptions in the model.** If the domain has three recognized commands, an unfamiliar subtype created outside the library could cause code to process it incorrectly or require an unwanted fallback.

**3. Supporting compile-time analysis.** Java knows the list of permitted subtypes from the declaration and checks the inheritance/implementation relationships, even when the classes reside in different files within a valid module/package scope.

**4. Assisting readers and tooling.** The compiler, IDEs, and tools that inspect the type hierarchy can recognize the permitted direct variants.

**5. Allowing “selective closing”.** You can still reserve a `non-sealed` branch for extension, instead of having only the two extremes of “completely open” or “all final”.

**6. Organizing the domain API by intent.** An API exposes a few primary variants and keeps details in their corresponding subtypes, rather than scattering “magic string types” across many places.

Sealed should not be interpreted as a sandbox/security technology against malicious code; it **does not control permission to call methods or read data**.

## 13. `non-sealed interface` Also Reopens a Branch

With a sealed interface:

~~~java
sealed interface Message permits TextMessage, ExtensionMessage {
}

record TextMessage(String value) implements Message {
}

non-sealed interface ExtensionMessage extends Message {
}
~~~

The declarations above are valid. `TextMessage` is a final record; `ExtensionMessage` is a permitted direct subinterface, yet it allows valid classes/interfaces in other locations to continue with `implements/extends ExtensionMessage`.

A class `PluginMessage implements ExtensionMessage` will **indirectly** implement Message. It is not listed in `Message permits ...` because the direct superinterface that it implements is ExtensionMessage.

If you choose `non-sealed`, make sure it is an **intentional extension point**; otherwise, the open branch can undermine the benefit of controlling all concrete implementations beneath it.

## 14. Standalone Program 5 — Reopened Interface with a Plugin Subtype

File **`OpenInterfaceBranchDemo.java`**:

~~~java
sealed interface Operation permits ReadOperation, CustomOperation {
    String name();
}

record ReadOperation(String path) implements Operation {
    @Override
    public String name() {
        return "read:" + path;
    }
}

non-sealed interface CustomOperation extends Operation {
}

final class BackupOperation implements CustomOperation {
    @Override
    public String name() {
        return "backup";
    }
}

public class OpenInterfaceBranchDemo {
    public static void main(String[] args) {
        Operation first = new ReadOperation("/data");
        Operation second = new BackupOperation();

        System.out.println(first.name());
        System.out.println(second.name());
        System.out.println("backup is CustomOperation="
                + (second instanceof CustomOperation));
        System.out.println("backup is Operation="
                + (second instanceof Operation));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 OpenInterfaceBranchDemo.java
java OpenInterfaceBranchDemo
~~~

**Stdout:**

~~~text
read:/data
backup
backup is CustomOperation=true
backup is Operation=true
~~~

`Operation` only permits `ReadOperation` and `CustomOperation` directly. `BackupOperation` does not directly implement Operation; it implements a `non-sealed` subinterface.

**This is not a way to “exploit a bug in Java”.** This is precisely the designed effect of non-sealed: allowing the API designer to select a specific extension point.

## 15. `permits` Rules and Direct Inheritance Must Match

Valid example:

~~~java
sealed class Vehicle permits Car, Bicycle {
}

final class Car extends Vehicle {
}

final class Bicycle extends Vehicle {
}
~~~

If `Car` is listed but Car does not actually `extends Vehicle` directly, that permits declaration is invalid. Similarly, if a class `Bus extends Vehicle` directly without being listed (or without belonging to a validly inferred permits list), the compiler will reject it.

Important conditions:

- A permitted direct subtype must have the proper **direct** `extends` or `implements` relationship with the sealed supertype.
- The modifier of a permitted child must choose a valid extension state: final/sealed/non-sealed, or the implicitly final/sealed cases of enum/record.
- Names in permits must refer to valid types that resolve properly.
- Direct subtypes must not be declared in an impermissible module/package according to Java 17 rules.
- `permits` cannot be used to allow a subclass that is prohibited by a **final class**; the base must be properly defined as sealed.
- Accessibility/constructor rules still apply: being named in permits does not automatically grant access to an inaccessible private constructor.

## 16. When Can `permits` Be Omitted?

You can omit `permits` when the sealed type and its direct permitted subtypes are properly declared **in the same compilation unit** (typically the same `.java` file) and satisfy the other JLS conditions:

~~~java
sealed interface Token {}
record NumberToken(int value) implements Token {}
record WordToken(String text) implements Token {}
~~~

The compiler infers the two permitted direct implementations. This **does not automatically search all Java files in the same package/module** and does not open the door to a third-party subtype outside the list. If you plan to move the permitted types to different files, write `permits` explicitly. The lesson **Conditions for inferring the subclass list when omitting permits** analyzes canonical names, local/anonymous types, nested declarations, and compilation units as well.

## 17. Standalone Program 6 — `permits` Inferred Within a Single File

File **`InferredPermitsDemo.java`**:

~~~java
sealed interface Token {
}

record NumberToken(int value) implements Token {
}

record WordToken(String text) implements Token {
}

public class InferredPermitsDemo {
    static String describe(Token token) {
        if (token instanceof NumberToken number) {
            return "number=" + number.value();
        }
        if (token instanceof WordToken word) {
            return "word=" + word.text();
        }
        throw new IllegalArgumentException("not supported");
    }

    public static void main(String[] args) {
        Token first = new NumberToken(7);
        Token second = new WordToken("java");

        System.out.println(describe(first));
        System.out.println(describe(second));
        System.out.println("first Token="
                + (first instanceof Token));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 InferredPermitsDemo.java
java InferredPermitsDemo
~~~

**Stdout:**

~~~text
number=7
word=java
first Token=true
~~~

No `permits` is written on Token, yet the compiler can infer the two direct implementations in the same compilation unit. Both are final records, so the hierarchy in the example does not open additional classes through them.

If you separate the two records into other files without updating the sealed declaration, you will need to review `permits` and the module/package scope accordingly.

## 18. `permits` and Java Modules: Constraints on Where Subtypes Reside

The location of permitted direct subtypes is subject to an additional boundary:

| Where is the sealed parent? | Where must the permitted direct types be? |
| --- | --- |
| **Named module** | **Same named module**, can be in a different package if visibility allows |
| **Unnamed module** (classpath) | **Same package** |

`permits` does not automatically grant type/constructor access or bypass Java module visibility. This rule protects the ownership of the sealed API rather than acting as a runtime plugin registration mechanism. The lesson **Same-module or same-package constraints** includes examples of multi-file compilation, `module-info.java`, exported packages, and classpath/module-path.

## 19. Illustrating Multiple Files in the Same Package in an Unnamed Module

This example assumes the files are placed together in the `example.model` package without using a named module.

**`Outcome.java`**:

~~~java
package example.model;

public sealed interface Outcome permits Good, Bad {
}
~~~

**`Good.java`**:

~~~java
package example.model;

public record Good(String value) implements Outcome {
}
~~~

**`Bad.java`**:

~~~java
package example.model;

public record Bad(String reason) implements Outcome {
}
~~~

These are three **valid files in the same package**, not a program with main. The records are declared `public`, so each record resides in a correspondingly named file.

If `Good` is moved to another package in the **unnamed module**, directly implementing Outcome no longer satisfies the same-package requirement of a sealed hierarchy. If using a **named module**, the permitted subtypes can belong to multiple packages within the same module under Java's rules; visibility and valid dependencies still need to be handled.

The benefit of the multi-file example is clarifying that **`permits` publicly declares the list**, while the type declarations can be organized into independent files.

## 20. A Named Module Does Not Mean Permitted Classes Can Be Anywhere

Even if a sealed interface is `public` and exported from a named module, an external module **cannot add its own direct permitted implementation**. Opening an API for plugins must be an explicit design decision:

- The root can permit a `non-sealed` extension interface/class in the same named module; third parties implement that **open branch**.
- Or use an ordinary open interface/strategy, if extensibility is the primary requirement.
- Access/`exports`/`requires` rules and constructor restrictions must still be valid.

Do not try to “bypass” sealed using a custom class loader or reflection. This is only a conceptual map; the lesson **Same-module or same-package constraints** has a concrete source layout, while the lesson **Comparing closed hierarchies with freely extensible classes** analyzes API trade-offs.

## 21. A Sealed Class Does Not Have to Be `abstract`

A common misconception: “sealed means abstract, so an object cannot be created directly”. This is **false**.

`sealed` only restricts **creating direct subtypes**, and does not inherently prohibit `new` on the sealed class itself. If a sealed class is not abstract and its constructor is accessible, you can still create instances of it.

~~~java
sealed class Animal permits Dog {
    String voice() {
        return "animal";
    }
}

final class Dog extends Animal {
    @Override
    String voice() {
        return "woof";
    }
}
~~~

These are two valid class declarations. Within the same package, you can write both `new Animal()` and `new Dog()`.

If the domain wants the base type to be strictly an abstraction and every object to belong to a specific variant, add **`abstract`** to the sealed class. `abstract` and `sealed` serve two different purposes and can be combined.

## 22. Standalone Program 7 — A Concrete Sealed Superclass Can Still Be Instantiated

File **`ConcreteSealedClassDemo.java`**:

~~~java
sealed class Animal permits Dog {
    String voice() {
        return "animal";
    }
}

final class Dog extends Animal {
    @Override
    String voice() {
        return "woof";
    }
}

public class ConcreteSealedClassDemo {
    public static void main(String[] args) {
        Animal base = new Animal();
        Animal dog = new Dog();

        System.out.println("base=" + base.voice());
        System.out.println("dog=" + dog.voice());
        System.out.println("base is Dog="
                + (base instanceof Dog));
        System.out.println("dog is Animal="
                + (dog instanceof Animal));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ConcreteSealedClassDemo.java
java ConcreteSealedClassDemo
~~~

**Stdout:**

~~~text
base=animal
dog=woof
base is Dog=false
dog is Animal=true
~~~

Animal is not abstract, so it can be instantiated directly. What is controlled by sealed is that **there is no new direct subclass besides Dog** in a valid hierarchy, not the creation of instances of Animal.

## 23. `abstract sealed` to Close the Set of Concrete Variants

When the base type only represents a concept rather than a concrete data variant, this option is usually appropriate:

~~~java
abstract sealed class Document
        permits Invoice, Receipt {
    abstract String kind();
}

final class Invoice extends Document {
    @Override
    String kind() {
        return "invoice";
    }
}

final class Receipt extends Document {
    @Override
    String kind() {
        return "receipt";
    }
}
~~~

These are valid declarations. `new Document()` is invalid because Document is **abstract**; `new Invoice()` and `new Receipt()` are valid.

**If both Invoice and Receipt are final**, and there is no non-sealed branch, every concrete subclass belongs to strictly one of those two direct variants. This is a closed model similar to a list of variant types, yet each variant can still have the logic, state, and behavior of a class.

You should use a sealed abstract class if variants need to share **a constructor, protected state, or implementations**. If you primarily need value variants and multiple interface implementation, sealed interface + records is usually simpler.

## 24. Standalone Program 8 — Abstract Sealed Class Holds the Contract

File **`AbstractSealedDocumentDemo.java`**:

~~~java
abstract sealed class Document
        permits Invoice, Receipt {
    abstract String kind();
}

final class Invoice extends Document {
    @Override
    String kind() {
        return "invoice";
    }
}

final class Receipt extends Document {
    @Override
    String kind() {
        return "receipt";
    }
}

public class AbstractSealedDocumentDemo {
    static String label(Document doc) {
        return "type=" + doc.kind();
    }

    public static void main(String[] args) {
        Document first = new Invoice();
        Document second = new Receipt();

        System.out.println(label(first));
        System.out.println(label(second));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 AbstractSealedDocumentDemo.java
java AbstractSealedDocumentDemo
~~~

**Stdout:**

~~~text
type=invoice
type=receipt
~~~

Both concrete types implement the abstract method `kind()`. Sealed provides the whitelist of direct subclasses, abstract requires implementations and forbids instantiating Document directly; dynamic dispatch still operates just like normal class inheritance.

## 25. `record` Is Often a Direct Variant of a Sealed Interface

A record is an implicitly final class. Therefore, using a record to represent each variant of a sealed interface makes a lot of sense:

~~~java
sealed interface Command permits Create, Delete {
}

record Create(String id) implements Command {
}

record Delete(String id) implements Command {
}
~~~

These declarations are valid. If you want to add `Update` as a direct variant, you must adjust `Command permits ...` and declare `record Update(...)` within the permitted boundary.

You **cannot** have a record `extends` an arbitrary sealed class: a record always extends `java.lang.Record` and cannot extend another class. To use records as variants, choose a **sealed interface** so they directly implement it.

This is also why a sealed interface fits data-oriented request/result/command types: each variant has its own component structure, and the parent type represents “one of these variants”.

## 26. Standalone Program 9 — Closed Command Model with Sealed + Record

File **`SealedCommandDemo.java`**:

~~~java
sealed interface Command permits Create, Delete, Rename {
}

record Create(String id) implements Command {
}

record Delete(String id) implements Command {
}

record Rename(String id, String newName) implements Command {
}

public class SealedCommandDemo {
    static String describe(Command command) {
        if (command instanceof Create c) {
            return "create:" + c.id();
        }
        if (command instanceof Delete d) {
            return "delete:" + d.id();
        }
        if (command instanceof Rename r) {
            return "rename:" + r.id() + "->" + r.newName();
        }
        throw new IllegalArgumentException("invalid command");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Create("A")));
        System.out.println(describe(new Rename("A", "B")));
        System.out.println(describe(new Delete("B")));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SealedCommandDemo.java
java SealedCommandDemo
~~~

**Stdout:**

~~~text
create:A
rename:A->B
delete:B
~~~

The record variants are implicitly final and carry data via record components. In Java 17, `instanceof` type patterns are sufficient to recognize variants without manual casting.

**Note:** the describe method is written with if/else and a `throw` at the end; the Java 17 compiler **does not automatically prove that an if chain handles an exhaustive sealed hierarchy**. Do not remove the final branch just because you assume sealed will turn the method into a complete switch expression.

## 27. Java 17 and `switch`: Avoiding Release Confusion

Some examples on the Internet write:

~~~java
// Illustrates SYNTAX that is NOT a stable sealed-type
// switch in Java 17 without preview enabled:
// return switch (command) {
//     case Create c -> ...;
//     case Delete d -> ...;
// };
~~~

In **Java 17 without preview enabled**, you cannot use general switch pattern matching on a sealed interface as a stable feature the way newer Java releases allow. Traditional `switch` in Java 17 supports selectors such as **enum**, strings, and the specified integral types; it does not automatically allow an arbitrary sealed interface as a selector.

**What you can do in standard Java 17:**

~~~java
if (command instanceof Create create) {
    return "create:" + create.id();
}
~~~

This is a valid snippet inside a method returning String that has the corresponding Command variable.

**Pattern matching for switch** had a preview history and was finalized in Java 21 (JEP 441). When reading newer Java documentation, always check the version and whether `--enable-preview` is required before copying examples. This lesson intentionally does not use preview features.

The fact that sealed helps the compiler/tooling understand the set of permitted direct subtypes **does not mean every hierarchy-analysis syntax is available in every Java release**.

## 28. Comparing `sealed`, `final`, `enum`, `record`

These keywords address **different axes**:

| Mechanism | Constraint |
| --- | --- |
| `final class` | Prohibits other subclasses from inheriting directly |
| `sealed class/interface` | Permits a controlled list of **direct subtypes** |
| `non-sealed` direct child | Reopens a valid branch |
| `abstract class` | Prevents instantiating the base class directly |
| `record` | Data carrier that is an implicitly final class |
| `enum` | A set of enum constants as declared, not an arbitrary set of subclasses |

`sealed interface + record` generally fits variants with differently typed payloads; `enum` is good for a fixed set of named values; `sealed abstract class` can share state/constructors. Records cannot extend an application superclass because they already extend `java.lang.Record`. The lesson **Combining sealed with abstract classes, records, and enums** analyzes these combinations, immutable values, and the case of enums with constant-specific bodies in depth.

## 29. Standalone Program 10 — Enum and Record Together in a Sealed Interface

File **`MixedVariantsDemo.java`**:

~~~java
sealed interface AccessEvent
        permits AccessLevel, TemporaryAccess {
}

enum AccessLevel implements AccessEvent {
    GUEST, MEMBER, ADMIN
}

record TemporaryAccess(int minutes) implements AccessEvent {
}

public class MixedVariantsDemo {
    static String label(AccessEvent event) {
        if (event instanceof AccessLevel level) {
            return "level:" + level.name();
        }
        if (event instanceof TemporaryAccess temporary) {
            return "minutes:" + temporary.minutes();
        }
        throw new IllegalArgumentException("unknown event");
    }

    public static void main(String[] args) {
        AccessEvent permanent = AccessLevel.ADMIN;
        AccessEvent temporary = new TemporaryAccess(15);

        System.out.println(label(permanent));
        System.out.println(label(temporary));
        System.out.println("admin enum="
                + (permanent instanceof AccessLevel));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 MixedVariantsDemo.java
java MixedVariantsDemo
~~~

**Stdout:**

~~~text
level:ADMIN
minutes:15
admin enum=true
~~~

The `AccessLevel` enum (without constant-specific class bodies) is implicitly final and is a permitted direct implementor. The `TemporaryAccess` record is also final. `AccessEvent` has only **two direct permitted implementing types**, even though AccessLevel has **three enum instances**.

This underscores the difference between **the set of subtypes** and **the set of object instances/constants**. Sealed governs the subtype relation; enum governs the named constants.

## 30. Common Error Cases When Declaring `sealed`

The snippets in this section **intentionally do not compile**; each case is viewed independently, without merging identically named declarations into the same file.

**A. A direct subclass that is not permitted:**

~~~java
sealed class Base permits Good {
}

final class Good extends Base {
}

// INTENTIONALLY DOES NOT COMPILE if uncommented:
// final class Surprise extends Base {}
~~~

**B. A permitted direct subclass forgets to specify its continuation state:**

~~~java
sealed class Base permits Good {
}

// INTENTIONALLY DOES NOT COMPILE:
class Good extends Base {
}
~~~

**C. Permitting a type that does not directly extend the superclass:**

~~~java
sealed class Base permits Good {
}

// INTENTIONALLY DOES NOT COMPILE:
final class Good {
}
~~~

**D. Using `non-sealed` when there is no sealed direct supertype:**

~~~java
class Ordinary {
}

// INTENTIONALLY DOES NOT COMPILE:
non-sealed class Child extends Ordinary {
}
~~~

**E. Using `sealed final` simultaneously:**

~~~java
// INTENTIONALLY DOES NOT COMPILE:
sealed final class Impossible {
}
~~~

`sealed` requires allowing valid direct children; `final` prohibits all subclasses. Java does not allow applying both modifiers on the same class.

**F. Attempting to directly implement a sealed interface without being listed:**

~~~java
sealed interface Event permits Known {
}

final class Known implements Event {
}

// INTENTIONALLY DOES NOT COMPILE if uncommented:
// record Unknown(String data) implements Event {}
~~~

**G. A sealed interface used as a lambda target:**

~~~java
sealed interface Task permits NamedTask {
    void run();
}

final class NamedTask implements Task {
    @Override
    public void run() {
    }
}

// INTENTIONALLY DOES NOT COMPILE inside a method:
// Task task = () -> System.out.println("run");
~~~

Even when an interface declares only one abstract method, **a sealed interface is not a functional interface** according to the JLS because a functional interface must not be declared `sealed`. Use a separate non-sealed `@FunctionalInterface` to accept lambdas if the API needs function-style callbacks.

## 31. Some Subtle Design Limitations

**Permits does not automatically grant constructor access.** A permitted child must still invoke an accessible superclass constructor; a private constructor does not become public because of permits.

**Permits does not make instance state immutable.** A sealed class can still have mutable fields and setters. A record variant holding a mutable List also provides only shallow immutability unless explicitly copied.

**Permits does not generate an automatic factory.** Callers still use appropriate constructors/factories. There is no runtime mechanism forcing iteration over all permitted types for instantiation.

**Sealed does not prohibit using other interfaces.** A permitted subtype class can implement additional interfaces, provided it does not violate other Java rules.

**Sealed does not guarantee an exhaustive `if` in Java 17.** You can design a closed list of variants while an if/instanceof method still forgets to handle a branch when code changes.

**Do not overuse `non-sealed`.** With just one open branch, the model of all descendants is no longer closed as readers might imagine.

## 32. Reflection Rules: Observing Permitted Direct Subclasses

Java 17 provides reflection APIs related to sealed types:

- `Class.isSealed()`: whether the class/interface runtime type is declared sealed.
- `Class.getPermittedSubclasses()`: returns an array describing **the direct permitted subclasses/subinterfaces** declared for the sealed type; for a type that is not sealed, the result can be null per the API.

Important: reflection APIs should only be used when metadata is genuinely needed (tooling, frameworks, diagnostics). Business logic should not have to scan reflection on every request just to classify a few known variants.

**Do not assume** that `getPermittedSubclasses()` represents “all concrete objects/descendants”. If there is a non-sealed branch, many new types beneath that branch will not necessarily appear in the sealed ancestor's array.

**Array order** should not be used as business ranking. If an order defined by the domain is needed, represent it separately using a field or an explicit list with a clear policy.

## 33. Standalone Program 11 — Reflection Observes Precisely Direct Permits

File **`SealedReflectionDemo.java`**:

~~~java
import java.util.Arrays;

sealed interface Root permits DirectLeaf, OpenBranch {
}

final class DirectLeaf implements Root {
}

non-sealed class OpenBranch implements Root {
}

final class IndirectLeaf extends OpenBranch {
}

public class SealedReflectionDemo {
    public static void main(String[] args) {
        Class<Root> root = Root.class;

        System.out.println("root sealed=" + root.isSealed());
        System.out.println("open sealed="
                + OpenBranch.class.isSealed());

        String[] names = Arrays.stream(
                root.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println("direct="
                + Arrays.toString(names));
        System.out.println("indirect Root="
                + (new IndirectLeaf() instanceof Root));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

**Stdout:**

~~~text
root sealed=true
open sealed=false
direct=[DirectLeaf, OpenBranch]
indirect Root=true
~~~

`Root.getPermittedSubclasses()` returns the list of **permitted direct subtypes**: DirectLeaf and OpenBranch. IndirectLeaf does **not** appear because it extends OpenBranch rather than directly implementing Root.

The example intentionally sorts by name before printing, so it does not rely on the entry order from reflection. `OpenBranch.class.isSealed()` is false because this branch is declared non-sealed.

## 34. API Changes When Adding a Permitted Child

Adding a permitted direct subtype, such as `Pending` to `Outcome permits Success, Failure`, is an **API contract change**, not merely adding a file. You must check consumers, serialization/schemas, business dispatch, and tests that assume only two variants exist.

In standard Java 17 without preview enabled, an `if/else instanceof` chain is not proven exhaustive by the compiler solely because of sealed; Java 21+ has different pattern switch checking capabilities. Maintain an intentional fallback, test the branches, and use sensible versioning. If the ecosystem needs to create variants independently, consider a `non-sealed` extension point rather than promising the hierarchy is always closed. The lesson **Comparing closed hierarchies with freely extensible classes** delves into OCP, binary/source compatibility, and cost of evolution.

## 35. A Sealed Hierarchy Is Not an Authorization Mechanism

A sealed interface can say “only classes in permits directly implement me”. It **does not** say that:

- The user has been authenticated.
- The request is trustworthy and needs no validation.
- A subtype inherently has permission to access the database.
- An object cannot be mutated.
- Data has been escaped against injection.
- Reflection/deserialization is always safe.
- An API endpoint is protected from unauthorized access.

For example, `record AdminCommand(String userId) implements Command` does not by itself prove that the caller is authorized to execute an admin command. **Authorization** must be checked based on the actual principal, resource, and policy.

Sealed provides a **type-hierarchy constraint**, and does not replace authentication, authorization, validation, or serialization hardening.

## 36. When Does Sealed Make a Design Better?

Sealed is appropriate when **a single owner controls the set of direct variants**, the domain clearly knows the main kinds, and adding a new kind should be treated as an API change. Examples: Success/Failure results with different payloads, AST nodes, and workflow states with their own data.

You should not seal just to “modernize”: an ordinary interface may be better if the primary goal is plugin extension; `enum` is simpler if only constant labels are needed, and composition/strategy is useful when behavior varies while the data shape does not require a tree of variants. `non-sealed` branches mean the root is no longer completely closed with respect to descendants. The lesson **When sealed is suitable for modeling value types** and the lesson **Comparing closed hierarchies with freely extensible classes** provide a decision matrix and concrete domain patterns.

## 37. Dynamic Dispatch Still Works the Same Way

When a caller holds a reference of a sealed base class/interface type, Java still dispatches virtual methods according to the runtime type as usual.

~~~java
sealed interface Formatter permits Plain, Upper {
    String format(String value);
}

final class Plain implements Formatter {
    public String format(String value) {
        return value;
    }
}

final class Upper implements Formatter {
    public String format(String value) {
        return value.toUpperCase(
                java.util.Locale.ROOT);
    }
}
~~~

These declarations are valid. Sealed only determines which types **are allowed** to implement Formatter directly, without changing the rules for calling `formatter.format(...)`.

Therefore, many times you **do not need** if/instanceof: the caller can invoke a method on the base interface and let polymorphism select the implementation. Use type tests only when you genuinely need variant-specific handling rather than shared behavior.

## 38. Standalone Program 12 — Polymorphism in a Sealed Interface

File **`SealedPolymorphismDemo.java`**:

~~~java
import java.util.List;
import java.util.Locale;

sealed interface Formatter permits Plain, Upper {
    String format(String input);
}

final class Plain implements Formatter {
    @Override
    public String format(String input) {
        return input;
    }
}

final class Upper implements Formatter {
    @Override
    public String format(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}

public class SealedPolymorphismDemo {
    public static void main(String[] args) {
        List<Formatter> formatters =
                List.of(new Plain(), new Upper());

        for (Formatter formatter : formatters) {
            System.out.println(formatter.format("Java"));
        }

        System.out.println("formatter count="
                + formatters.size());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SealedPolymorphismDemo.java
java SealedPolymorphismDemo
~~~

**Stdout:**

~~~text
Java
JAVA
formatter count=2
~~~

Sealed does not force callers to write `instanceof` in every method. When a polymorphic API is sufficient, users simply call `format` and the implementation performs the corresponding work.

## 39. Process for Designing a Proper Sealed Hierarchy

Before writing code, follow this sequence:

1. **Identify the conceptual domain:** PaymentResult, Expr, Command, rather than a generic Base.
2. **List the actual direct variants:** each class/interface has its own domain role.
3. **Choose between a sealed class and an interface:** is shared superclass state/constructors needed?
4. **Define the package/module boundary:** are the direct subtypes located where the JLS permits?
5. **Write `permits` explicitly** if the hierarchy spans multiple files or needs a clearly visible public contract.
6. **Choose a modifier for each direct subtype:** final, sealed, or non-sealed; do not omit it.
7. **Design the second level if needed:** each sealed child has its own permits.
8. **Decide whether there is an open branch:** if using non-sealed, document the extension point.
9. **Clearly define shared behavior:** virtual methods or value components.
10. **Design invariants/validation:** sealed does not replace constructor checks.
11. **Handle `null`:** a variable of a sealed interface type can still be null.
12. **Choose variant handling in Java 17:** polymorphism/instanceof patterns, without relying on unfinalized pattern switch syntax.
13. **Consider equality, serialization, and API evolution:** what contracts do the variant records/classes have?
14. **Write negative compile tests or verify with the compiler:** unpermitted subclasses must fail to compile.
15. **Review the hierarchy:** are the direct subclasses meaningful enough, or are too many intermediate levels being overused?

## 40. Misconceptions to Avoid

| Misconception | Reality |
| --- | --- |
| `sealed` prohibits all subclasses at every level | It restricts **direct** subtypes; non-sealed can reopen a branch |
| Having permits means `extends`/`implements` is unnecessary | Direct inheritance must still be declared properly |
| A permitted child does not need any modifier | The child needs final/sealed/non-sealed per the rules |
| `final` and `sealed` are the same | Final forbids subclasses; sealed permits a chosen list |
| `non-sealed` means a class has no sealed parent | On the contrary, it is for a direct subtype of a sealed type |
| A sealed interface can be used as a lambda target | A sealed interface is not considered a functional interface |
| A sealed class is abstract by default | No; it can be instantiated if concrete and accessible |
| Permits also lists grandchildren/great-grandchildren | Permits lists direct children |
| A class in any module can be permitted | A named module requires the same named module |
| In an unnamed module, a class in another package can be permitted | It must be in the same package |
| Standard Java 17 switch supports sealed pattern cases | In Java 17, preview must be distinguished; it is not a standard non-preview feature |
| Java 17 automatically proves every `instanceof` chain exhaustive | No |
| A record automatically extends any permitted sealed class | A record only extends Record; it typically implements a sealed interface |
| Sealed is a security/authorization tool | No; it is only a restriction on subtype declarations |
| Sealed automatically guarantees data immutability | No; mutable state remains mutable |
| Sealed eliminates polymorphism | No; dispatch works normally |
| `getPermittedSubclasses()` returns all descendants | Only direct permitted subtypes |
| A non-sealed branch still guarantees all leaves are closed | No; the branch is open for further extension |
| A new variant can be added without affecting clients | It can affect assumptions/handling/the API contract |

## 41. Self-Practice Exercises

**Question 1.** Does `sealed` control direct children or all descendants of a class?

**Question 2.** Given `sealed class A permits B`, if `B` declares `non-sealed`, must `C extends B` be in `A permits`?

**Question 3.** Which modifiers must a direct permitted subclass choose from?

**Question 4.** Can a direct permitted subinterface be declared `final`?

**Question 5.** How does a `sealed abstract class` differ from a concrete `sealed class`?

**Question 6.** Why can `new Base()` be valid if Base is sealed?

**Question 7.** If a sealed Base only permits Child, will an unlisted `Unknown extends Base` compile?

**Question 8.** Is a permitted class that omits `final`/`sealed`/`non-sealed` valid?

**Question 9.** If you want Child to have its own controlled subclasses, which modifier do you use?

**Question 10.** If you want Child to be an open extension point, which modifier do you use?

**Question 11.** Can a sealed interface permit a direct subinterface?

**Question 12.** Can a sealed interface permit a record to implement it?

**Question 13.** Can a record `extends` an arbitrary sealed class?

**Question 14.** If an enum is permitted by a sealed interface and implements it, does it need to be declared `final enum`?

**Question 15.** In a named module, must permitted direct subtypes be in the same package or the same module?

**Question 16.** In an unnamed module, must permitted direct subtypes be in the same package?

**Question 17.** When can `permits` be omitted while keeping the type sealed?

**Question 18.** Do two direct subtypes in separate files within the same package need an explicit permits clause?

**Question 19.** Does `sealed` prevent a variable reference from holding null?

**Question 20.** Is a sealed interface with only one abstract method a functional interface usable for lambdas?

**Question 21.** In Java 17 without preview, which technique should be used to branch by record variants?

**Question 22.** Is an `instanceof` chain on a sealed hierarchy in Java 17 automatically proven exhaustive by the compiler?

**Question 23.** Does `getPermittedSubclasses()` list a grandchild extending a non-sealed direct child?

**Question 24.** Should a framework that allows plugins to implement an interface directly from another module unconditionally seal that interface?

**Question 25.** Why does sealed not replace authorization?

**Question 26.** Given a sealed interface Formatter, does a caller need `instanceof` to invoke `format()` polymorphically?

**Question 27.** When adding a new direct permitted variant, what places need to be checked?

**Question 28.** In the tree Expression → Binary → Add, does Add need to be listed in Expression permits if Add directly implements Binary?

### Reference Answers

1. Only direct subtypes of the sealed node.
2. No. C directly extends B; C is an indirect descendant of A.
3. `final`, `sealed`, `non-sealed` for classes, along with the implicitly final/sealed cases of record/enum.
4. No; interfaces do not have final, so use sealed or non-sealed.
5. Abstract forbids instantiating the base and can have abstract methods; sealed by itself only restricts direct subtypes.
6. Sealed does not mean abstract; if Base is concrete and its constructor is accessible, it can be instantiated.
7. No. Unknown is not a direct permitted subclass.
8. No, under the normal direct subtype rules.
9. `sealed` with Child's own permits.
10. `non-sealed`.
11. Yes. The subinterface declares `extends` directly on the sealed interface and is permitted.
12. Yes. A record is implicitly final and can implement a sealed interface.
13. No. A record extends `java.lang.Record` and cannot extend another class.
14. No. An enum has implicitly final or implicitly sealed rules depending on constant-specific bodies.
15. Same **named module**; multiple packages are possible if access is valid.
16. Yes, the same package.
17. When the direct permitted subtypes can be validly inferred in the same compilation unit.
18. Yes: if they are in different compilation units, an explicit permits list is required.
19. It can hold null; sealed does not prohibit null.
20. No. A sealed interface is not a functional interface.
21. `instanceof` type patterns, polymorphic methods, or an appropriate visitor.
22. No.
23. No. Reflection returns permitted **direct** subtypes.
24. No, if the API genuinely needs open direct extension; a non-sealed extension branch or an open interface can be used.
25. Type-hierarchy constraints do not check principals/permissions.
26. No. Call the interface method directly and rely on dynamic dispatch.
27. Variant handling paths, tests, APIs, serialization, downstream consumers, and versioning.
28. No, if Add is a direct subtype of Binary rather than directly of Expression.

## 42. Knowledge Check and Code Review Checklist

- [ ] Do I understand that sealed restricts **direct subclasses or subtypes**, not all descendants?
- [ ] Have I properly identified the direct superclass/superinterface in each `extends`/`implements`?
- [ ] Does the `permits` list contain exactly the direct subtypes?
- [ ] Does each permitted direct subtype have the proper final/sealed/non-sealed modifier or implicit state?
- [ ] If using non-sealed, did I intend to open the branch?
- [ ] If the entire hierarchy should be closed, are the leaves final and free of any non-sealed branch?
- [ ] If the base should not be instantiated, have I declared it abstract?
- [ ] If using records, is the parent an appropriate sealed interface?
- [ ] If using an enum, do I distinguish named constants from direct implementation types?
- [ ] Have I verified being in the same named module or the same package in an unnamed module?
- [ ] If permits is omitted, are the direct subtypes validly in the same compilation unit?
- [ ] Do constructors/access still satisfy Java rules, since permits does not automatically grant access?
- [ ] Have I distinguished polymorphism from pattern/type checks?
- [ ] Have I avoided using Java 21 pattern switch as standard Java 17 syntax?
- [ ] Have I checked null handling and fallback in Java 17?
- [ ] Do I treat the set of variants as an API contract when versioning?
- [ ] Have I checked that a `non-sealed` branch will allow new descendants?
- [ ] If using reflection, am I avoiding confusing permitted direct subclasses with all descendants?
- [ ] Have I confirmed that sealed does not by itself guarantee immutable state/security?
- [ ] Does sealing the API genuinely align with extension and plugin integration goals?
- [ ] Have the runnable examples been verified for imports, class names, and Java 17 stdout?

## 43. Official Java 17 Documentation

- [JLS 17 §8.1.1.2 — `sealed`, `non-sealed` and `final` Class Modifiers](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): class modifiers in a sealed hierarchy.
- [JLS 17 §8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6): `permits` for classes and direct subclass rules.
- [JLS 17 §9.1.1.4 — `sealed` and `non-sealed` Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): interface modifiers.
- [JLS 17 §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): sealed interfaces and permitted direct subtypes.
- [JLS 17 §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): sealed interfaces are not functional interfaces.
- [JLS 17 §14.30.1 — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30.1): type patterns used in Java 17.
- [JLS 17 §15.20.2 — Type Comparison Operator `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type tests and pattern variables.
- [Java SE 17 API — `Class.isSealed()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSealed()): identifying a sealed class/interface at runtime.
- [Java SE 17 API — `Class.getPermittedSubclasses()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()): reading the direct permitted types.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): purpose, forms, and limitations of sealed hierarchies standardized in Java 17.
- [JEP 395 — Records](https://openjdk.org/jeps/395): record variants combined with sealed interfaces.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch feature finalized in Java 21, **not standard non-preview Java 17 syntax**.

## 44. Summary

**`sealed` is used to control *which types are permitted to directly extend or implement a parent type***. With `sealed class A permits B, C`, B/C are the direct permitted subclasses. With `sealed interface I permits X, Y`, X/Y can be direct implementing classes or direct extending interfaces. `permits` does not automatically list all multi-level descendants.

Each direct permitted child must indicate whether that branch is **closed (`final`)**, **further controlled (`sealed`)**, or **reopened (`non-sealed`)**. This per-level choice is what helps API design balance a **closed domain hierarchy** with **intentional extension points**.

In Java 17, sealed helps the compiler check subtype relationships, increases clarity in the domain model, and makes variants easy to recognize. It **does not** automatically provide immutability, security, or non-preview exhaustive pattern switch. To use it effectively, clearly design **direct children, module/package boundaries, constructor access, fallback behavior, and the API change process**.
