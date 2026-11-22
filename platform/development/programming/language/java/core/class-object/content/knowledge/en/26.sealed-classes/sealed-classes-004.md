# `final`, `sealed`, and `non-sealed` Subclasses in Sealed Hierarchies — Java 17

## 1. Lesson Objectives

Java 17 introduces **sealed classes** and **sealed interfaces** into the language as a standard feature. With a class or interface declared as `sealed`, the designer can specify **which types are permitted to directly extend or implement** it. This is a way to control the *set of direct branches* of a type hierarchy, rather than allowing any accessible class to arbitrarily `extends`/`implements` it.

The most important point to study thoroughly is not just the `permits` syntax on the parent class, but also the **obligation of the permitted direct subclass**:

> In Java 17, a class that directly extends a sealed superclass or directly implements a sealed interface must explicitly specify its subsequent inheritance policy: `final`, `sealed`, or `non-sealed`. For a record, `final` is applied implicitly.

The three options are not equivalent:

- **`final`**: terminates the branch at that class itself; does not allow other classes to `extends` it.
- **`sealed`**: allows further branching, but restricts **the permitted direct subclasses/subinterfaces**; the next level is in turn subject to the corresponding rules.
- **`non-sealed`**: opens that branch to subsequent extending/implementing types under standard Java access and inheritance rules, even though its ancestor remains `sealed`.

This guide covers everything from fundamentals to implementation: Java SE 17 JLS rules, multi-level inheritance, records, interfaces, module/package and visibility constraints, the difference between direct and indirect subtyping, common compile-time errors, API extensibility, Java 17 pattern matching, testing, domain design, standalone runnable examples with stdout, exercises with solutions, and a code review checklist.

**Version:** The examples use Java 17 (`javac --release 17`). They do not rely on preview `switch` pattern matching or newer Java syntax.

## 2. Starting with a Simple Hierarchy

```java
sealed interface PaymentResult
        permits PaymentSuccess, PaymentFailure {
}

final class PaymentSuccess implements PaymentResult {
}

final class PaymentFailure implements PaymentResult {
}
```

These three declarations are valid if they are in the appropriate module/package scope and compiled together.

Reading them in order:

1. `PaymentResult` is a sealed interface.
2. `permits PaymentSuccess, PaymentFailure` specifies **two direct permitted subtypes**.
3. `PaymentSuccess` and `PaymentFailure` directly `implements PaymentResult`.
4. Each subclass specifies `final`, so no class is allowed to further `extends PaymentSuccess` or `extends PaymentFailure`.
5. Any other class not in the permits list cannot directly `implements PaymentResult` on its own.

**Common misconception:** the `permits` list is not a list of object instances, nor is it a list of enum constants. It lists **the types (classes/interfaces)** permitted to be **direct subtypes**.

### Visual Illustration

```text
sealed PaymentResult
├── final PaymentSuccess       (terminates branch)
└── final PaymentFailure       (terminates branch)
```

If the domain intent is a closed set of results with no need for extension at any level, using final direct implementations like this is very natural.

## 3. Runnable: Two Final Subclasses

Save the file **`FinalBranchesDemo.java`**:

```java
sealed interface Result permits Success, Failure {
    String description();
}

final class Success implements Result {
    private final int value;

    Success(int value) {
        this.value = value;
    }

    @Override
    public String description() {
        return "success:" + value;
    }
}

final class Failure implements Result {
    private final String reason;

    Failure(String reason) {
        this.reason = reason;
    }

    @Override
    public String description() {
        return "failure:" + reason;
    }
}

public class FinalBranchesDemo {
    public static void main(String[] args) {
        Result first = new Success(42);
        Result second = new Failure("invalid");

        System.out.println(first.description());
        System.out.println(second.description());
        System.out.println(first instanceof Success);
        System.out.println(second instanceof Failure);
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 FinalBranchesDemo.java
java FinalBranchesDemo
```

**Exact stdout:**

```text
success:42
failure:invalid
true
true
```

`Result` is an interface; the two implementations are final classes. References with static type `Result` still invoke the right method overrides thanks to dynamic dispatch.

## 4. At Which Level Must the Three Modifiers Be Understood?

Consider a sealed parent:

```java
sealed class Parent permits Closed, Restricted, Open {
}

final class Closed extends Parent {
}

sealed class Restricted extends Parent permits RestrictedChild {
}

final class RestrictedChild extends Restricted {
}

non-sealed class Open extends Parent {
}
```

The `final`/`sealed`/`non-sealed` modifiers apply to **the declaration of the direct subclasses** (`Closed`, `Restricted`, `Open`), not to references to them.

| Modifier | Allows other classes to extend it? | Who decides the next subclasses? | Appropriate choice |
| --- | --- | --- | --- |
| `final` | No | No further subclasses | Final variant, closes the branch |
| `sealed` | Yes, but restricted | The sealed class itself via `permits`/inference | For several known lower-level variants |
| `non-sealed` | Yes, if standard rules allow it | No longer a sealed whitelist at that branch | Extension point for third parties |
| None of the three specified on a direct class child | **Error in Java 17** | Cannot be left ambiguous | Must choose a policy |

**Do not confuse `non-sealed` with `non-final`.** `non-final` is not a Java keyword modifier. `non-sealed` is the actual keyword modifier in the context of a sealed hierarchy.

## 5. Why Does Java Force Subclasses to Choose a Policy?

If a sealed parent only restricted its direct children without forcing the children to explicitly state their policy, readers would find it hard to tell whether the system is truly closed at the child level or accidentally left a branch open.

Java 17 requires an explicit choice:
- Choose `final` if the direct child is a **leaf** of the inheritance tree.
- Choose `sealed` if the direct child still has valid branches, but they are controlled.
- Choose `non-sealed` if the direct child is an **intentional extension point**.

This rule helps reviewers evaluate *at each node* whether the hierarchy can still be extended further.

**What the compiler enforces:** which types may **directly** extend/implement the sealed parent and the policy of direct subclasses/direct subinterfaces. The compiler does not prove every business rule or object invariant desired by the application.

## 6. `final`: Stopping the Inheritance Branch

`final class Leaf extends SealedParent` both fulfills the obligation of a direct child and prevents other classes from using `extends Leaf`.

```java
sealed class Vehicle permits Car, Truck {
}

final class Car extends Vehicle {
}

final class Truck extends Vehicle {
}
```

If you try:

```java
// Compile-negative:
class SportsCar extends Car {
}
```

Java rejects it because `Car` is final. Of course, if `SportsCar` also tries to directly `extends Vehicle` without being permitted, it also violates the sealed-parent restriction.

### Does `final` Make an Object Immutable?

No. `final` on a **class** prevents subclassing; it does not automatically make all fields final or thread-safe.

```java
final class Counter {
    int value;

    void increment() {
        value++;
    }
}
```

`Counter` cannot be extended, yet `value` still changes. This is a common misunderstanding when reading a sealed branch with a final leaf.

### Can `final` Be Used on an Interface?

No. A Java interface cannot be declared `final`. If a direct subtype of a sealed interface **is also an interface**, use `sealed` or `non-sealed`; if a direct subtype is a **class** implementing the interface, the class can be `final`, `sealed`, or `non-sealed`.

## 7. Runnable: A Final Leaf Still Has Mutable State

Save **`FinalLeafStateDemo.java`**:

```java
sealed interface Task permits MutableTask {
    int done();
}

final class MutableTask implements Task {
    private int completed;

    void completeOne() {
        completed++;
    }

    @Override
    public int done() {
        return completed;
    }
}

public class FinalLeafStateDemo {
    public static void main(String[] args) {
        MutableTask task = new MutableTask();

        task.completeOne();
        task.completeOne();

        System.out.println(task.done());
        System.out.println(task instanceof Task);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FinalLeafStateDemo.java
java FinalLeafStateDemo
```

Stdout:

```text
2
true
```

The `MutableTask` class is final **with respect to inheritance**. The `completed` state is still mutable. If used concurrently by multiple threads, `completed++` also requires appropriate synchronization.

## 8. `sealed`: Retaining Control at the Next Level

A direct subclass can itself be `sealed` and list its own direct subtypes:

```java
sealed interface Expression permits Literal, Binary {
}

final class Literal implements Expression {
}

sealed abstract class Binary implements Expression
        permits Addition, Multiplication {
}

final class Addition extends Binary {
}

final class Multiplication extends Binary {
}
```

Tree:

```text
sealed Expression
├── final Literal
└── sealed abstract Binary
    ├── final Addition
    └── final Multiplication
```

- `Expression` controls its direct children: `Literal` and `Binary`.
- `Binary` controls its direct subclasses: `Addition` and `Multiplication`.
- `Addition`/`Multiplication` are **indirect descendants** of Expression.
- There is no need to list Addition/Multiplication in `Expression.permits`, because they do **not directly** implement/extend Expression.

### `sealed` and `abstract`

A class can be both `sealed` and `abstract`:
- `sealed` determines **the permitted subclasses**.
- `abstract` determines direct instantiability and abstract methods.

They do not conflict. Conversely, `final abstract class` is a contradictory combination.

## 9. Runnable: Multiple Sealed Levels and Expression Evaluation

Save **`SealedExpressionTreeDemo.java`**:

```java
sealed interface Expr permits Num, BinaryExpr {
    int evaluate();
}

record Num(int value) implements Expr {
    @Override
    public int evaluate() {
        return value;
    }
}

sealed abstract class BinaryExpr implements Expr
        permits AddExpr, MultiplyExpr {
    protected final Expr left;
    protected final Expr right;

    BinaryExpr(Expr left, Expr right) {
        this.left = left;
        this.right = right;
    }
}

final class AddExpr extends BinaryExpr {
    AddExpr(Expr left, Expr right) {
        super(left, right);
    }

    @Override
    public int evaluate() {
        return left.evaluate() + right.evaluate();
    }
}

final class MultiplyExpr extends BinaryExpr {
    MultiplyExpr(Expr left, Expr right) {
        super(left, right);
    }

    @Override
    public int evaluate() {
        return left.evaluate() * right.evaluate();
    }
}

public class SealedExpressionTreeDemo {
    public static void main(String[] args) {
        Expr expression = new MultiplyExpr(
                new AddExpr(new Num(2), new Num(3)),
                new Num(4));

        System.out.println(expression.evaluate());
        System.out.println(expression instanceof BinaryExpr);
        System.out.println(expression instanceof MultiplyExpr);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedExpressionTreeDemo.java
java SealedExpressionTreeDemo
```

Stdout:

```text
20
true
true
```

`Num` is a record and is **implicitly final**, so it can serve as a permitted direct implementation of the sealed interface `Expr` without having to write `final` in the record declaration. `BinaryExpr` is a permitted direct class that uses `sealed`, and in turn restricts which binary operation classes can directly extend it.

## 10. `non-sealed`: Intentionally Opening a Branch

`non-sealed` means that the type **does not continue enforcing its own list of direct permitted subtypes**; subsequent subclasses are subject to normal extends/implements/accessibility rules.

```java
sealed class Notification permits EmailNotification,
        ExtensibleNotification {
}

final class EmailNotification extends Notification {
}

non-sealed class ExtensibleNotification
        extends Notification {
}

class SmsNotification extends ExtensibleNotification {
}

class PushNotification extends ExtensibleNotification {
}
```

`Notification` **only directly permits** EmailNotification and ExtensibleNotification. It does not need to list SmsNotification or PushNotification because these two classes inherit **indirectly** via ExtensibleNotification.

### What `non-sealed` Does *Not* Do

- Does not automatically make a private constructor accessible.
- Does not bypass Java module/package access rules.
- Does not guarantee that every third party can create a subclass in all circumstances.
- Does not turn an abstract class into a concrete class.
- Does not make a public API automatically support every extension.
- Cannot use `non-sealed` arbitrarily on a class that has no direct sealed superclass/superinterface.

It only **removes the sealed restriction mechanism on this branch**, not all other constraints.

## 11. Runnable: non-sealed and Grandchildren Not Needing the Grandparent's permits

Save **`NonSealedExtensionDemo.java`**:

```java
sealed interface Message permits SystemMessage, CustomMessage {
    String text();
}

final class SystemMessage implements Message {
    @Override
    public String text() {
        return "system";
    }
}

non-sealed abstract class CustomMessage implements Message {
}

final class EmailMessage extends CustomMessage {
    @Override
    public String text() {
        return "email";
    }
}

class SmsMessage extends CustomMessage {
    @Override
    public String text() {
        return "sms";
    }
}

public class NonSealedExtensionDemo {
    public static void main(String[] args) {
        Message one = new SystemMessage();
        Message two = new EmailMessage();
        Message three = new SmsMessage();

        System.out.println(one.text());
        System.out.println(two.text());
        System.out.println(three.text());
        System.out.println(two instanceof CustomMessage);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NonSealedExtensionDemo.java
java NonSealedExtensionDemo
```

Stdout:

```text
system
email
sms
true
```

`EmailMessage` and `SmsMessage` are descendants of `Message` but **do not directly implement the sealed Message**. They do not need to appear in `Message.permits`.

`CustomMessage` is a `non-sealed abstract class` — a valid combination: abstract forces subclasses to implement methods, while non-sealed allows the set of subclasses to be extended.

## 12. Distinguishing Direct and Indirect Subclasses

Given:

```java
sealed class Root permits Branch {
}

non-sealed class Branch extends Root {
}

class Leaf extends Branch {
}
```

- `Branch` is a **direct subclass** of `Root`.
- `Leaf` is a **direct subclass** of `Branch`, but only an **indirect subclass** of `Root`.
- `Root.permits Branch` is sufficient to allow the relationship above.
- `Leaf` must not be included in `Root.permits` if Leaf does not directly extend Root.
- `Leaf` **does not have to declare final/sealed/non-sealed** merely because Root is sealed, because Leaf's **direct superclass** is the non-sealed Branch.

### Why Does This Matter for an API?

If the designer chooses `non-sealed Branch`, they have intentionally ceded extension rights on the Branch branch. Root must not be described as "completely closed at all levels" in that case. Only the direct children are controlled by Root; the non-sealed branch can be extended according to the design.

## 13. Non-sealed Does Not Propagate the Modifier to Grandchildren

```java
sealed class A permits B {
}

non-sealed class B extends A {
}

class C extends B {
}

final class D extends C {
}
```

This code is valid: `C` is an ordinary class and does not need to specify non-sealed itself. `D` is final according to D's own design.

**There is no rule that all descendants must carry one of the three modifiers.** The specific requirement applies when a declaration is a **direct subtype of a sealed type**. A class C extending non-sealed B does not directly extend sealed A.

### Can a Branch Be Re-sealed?

You can place a new sealed boundary beneath an already opened branch:

```java
sealed class Root permits Open {
}

non-sealed class Open extends Root {
}

sealed class Controlled extends Open permits End {
}

final class End extends Controlled {
}
```

`Controlled` is not a direct permitted subclass of Root; it chooses `sealed` on its own to control its own direct descendants. `non-sealed` on Open allows a subclass like Controlled to be declared without having to be listed in Root.permits.

## 14. Runnable: Opening a Branch and Resealing It

Save **`ResealBranchDemo.java`**:

```java
sealed interface Event permits ExtensionPoint {
    String kind();
}

non-sealed abstract class ExtensionPoint implements Event {
}

sealed class ControlledEvent extends ExtensionPoint
        permits SuccessEvent, FailureEvent {
    @Override
    public String kind() {
        return "controlled";
    }
}

final class SuccessEvent extends ControlledEvent {
}

final class FailureEvent extends ControlledEvent {
}

public class ResealBranchDemo {
    public static void main(String[] args) {
        Event first = new SuccessEvent();
        Event second = new FailureEvent();

        System.out.println(first.kind());
        System.out.println(second instanceof ControlledEvent);
        System.out.println(first instanceof ExtensionPoint);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ResealBranchDemo.java
java ResealBranchDemo
```

Stdout:

```text
controlled
true
true
```

Some developers mistakenly think that "once non-sealed, it cannot be sealed again." That is wrong: a lower-level type can seal **its own direct branch** with a new declaration, as long as it follows Java rules.

## 15. `non-sealed` Is Only Valid with an Appropriate Direct Sealed Parent

Invalid:

```java
// Compile-negative:
non-sealed class Plain {
}
```

If `Plain` does not directly extend a sealed class or directly implement a sealed interface, the `non-sealed` modifier has no valid context and is rejected by Java.

Similarly invalid:

```java
class Ordinary {
}

// Compile-negative:
non-sealed class Child extends Ordinary {
}
```

`Ordinary` is not a sealed class and Child has no direct sealed superinterface; therefore `non-sealed` cannot be used.

### Note When Having Both a Superclass and Interfaces

A class can extend a non-sealed superclass while **directly implementing a sealed interface**. In that case, it is still a direct subtype of the sealed interface, and `non-sealed` can be valid if permitted by the interface:

```java
sealed interface Role permits CustomRole {
}

class BaseRole {
}

non-sealed class CustomRole extends BaseRole
        implements Role {
}
```

It is the presence of `sealed` among the **direct supertypes** that determines the requirement/eligibility to declare `non-sealed`.

## 16. Sealed Interface: There Is No `final interface`

A sealed interface can permit:
- **A class** to implement it directly, and the class chooses `final`/`sealed`/`non-sealed` (a record is implicitly final).
- **An interface** to extend it directly, and the interface chooses **`sealed` or `non-sealed`**.

Example:

```java
sealed interface Protocol permits InternalProtocol, OpenProtocol {
}

sealed interface InternalProtocol extends Protocol
        permits InternalProtocolImpl {
}

final class InternalProtocolImpl
        implements InternalProtocol {
}

non-sealed interface OpenProtocol extends Protocol {
}

class PluginProtocolImpl implements OpenProtocol {
}
```

`InternalProtocol` is a sealed direct subinterface. `OpenProtocol` is a non-sealed direct subinterface. `PluginProtocolImpl` does not directly implement the sealed Protocol; it implements the interface that was opened.

**Do not write `final interface InternalProtocol`**. Java does not allow `final` interfaces; an interface always retains the ability to be implemented by classes, whereas a sealed interface controls *direct subtypes* by restricting the list.

## 17. Runnable: Closed/Open Interface Branching

Save **`SealedInterfacesDemo.java`**:

```java
sealed interface Service permits CoreService, PluginService {
    String id();
}

sealed interface CoreService extends Service
        permits BuiltInService {
}

final class BuiltInService implements CoreService {
    @Override
    public String id() {
        return "core";
    }
}

non-sealed interface PluginService extends Service {
}

final class ThirdPartyService implements PluginService {
    @Override
    public String id() {
        return "third-party";
    }
}

public class SealedInterfacesDemo {
    public static void main(String[] args) {
        Service first = new BuiltInService();
        Service second = new ThirdPartyService();

        System.out.println(first.id());
        System.out.println(second.id());
        System.out.println(second instanceof PluginService);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedInterfacesDemo.java
java SealedInterfacesDemo
```

Stdout:

```text
core
third-party
true
```

The `PluginService` interface opens the way for implementations underneath it, while `CoreService` still requires its own whitelist.

## 18. Complete Class/Interface Comparison Table

| Direct subtype of a sealed parent | Valid modifier | Additional requirements |
| --- | --- | --- |
| Concrete class leaf | `final` | Implement all required abstract methods |
| Abstract class wanting to keep a controlled branch | `abstract sealed` | Have direct permitted children |
| Concrete class wanting to restrict its branch | `sealed` | List/infer direct permitted children |
| Concrete class wanting to allow free extension | `non-sealed` | Follow standard access/constructor rules |
| Abstract class wanting an extension point | `abstract non-sealed` | Callers can write valid subclasses |
| Direct subinterface with its own whitelist | `sealed interface` | Have permitted direct subtypes |
| Direct subinterface wanting extension | `non-sealed interface` | Does not have its own permits whitelist |
| Direct subinterface written with `final` | **Invalid** | `final` does not apply to interfaces |
| Direct class child without specifying a modifier | **Invalid** | Choose final/sealed/non-sealed |
| Direct record implementing a sealed interface | **Valid, implicitly final** | The record must be in permits or inferred |
| Indirect class descendant of a non-sealed parent | Modifier from the trio not required | Only normal class rules needed if direct supertypes are not sealed |

**Modifier-mixing trap:** `final sealed class`, `final non-sealed class`, and `sealed non-sealed class` do not represent valid simultaneous policies. A class must choose a single consistent inheritance policy.

## 19. Record: Direct Permitted Class Implicitly Final

A Java record is treated as final by the language; there are no subclasses of a record. Therefore, a record is a convenient choice for **data-carrying leaf variants** of a sealed interface:

```java
sealed interface ApiResult permits Ok, ErrorResult {
}

record Ok(String value) implements ApiResult {
}

record ErrorResult(String message) implements ApiResult {
}
```

You do not need `final record Ok(...)` to show that the obligation of a direct permitted child is satisfied; `record` already provides final semantics. A record is still a class, so `implements ApiResult` is a direct relationship.

### What a Record Does *Not* Do

- A record cannot extend an arbitrary class other than `java.lang.Record`.
- A record cannot be a sealed class acting as a parent for other subclasses.
- A record is not automatically deeply immutable if a component holds mutable objects/arrays.
- A record does not automatically provide exhaustiveness for the Java 17 `switch` API over a sealed interface without using the appropriate mechanisms.

## 20. Runnable: Sealed Interface and Record Leaves

Save **`SealedRecordVariantsDemo.java`**:

```java
sealed interface SearchResult permits Found, Missing {
}

record Found(String value) implements SearchResult {
}

record Missing(String reason) implements SearchResult {
}

public class SealedRecordVariantsDemo {
    static String describe(SearchResult result) {
        if (result instanceof Found found) {
            return "found:" + found.value();
        }
        if (result instanceof Missing missing) {
            return "missing:" + missing.reason();
        }
        throw new IllegalStateException("unhandled");
    }

    public static void main(String[] args) {
        System.out.println(describe(new Found("Java")));
        System.out.println(describe(new Missing("not indexed")));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedRecordVariantsDemo.java
java SealedRecordVariantsDemo
```

Stdout:

```text
found:Java
missing:not indexed
```

`instanceof` pattern matching for the `found`/`missing` variables is a **standard feature in Java 17**, requiring no preview flag. The final `throw` handling is still written explicitly; sealed metadata does not automatically turn an `if/instanceof` chain into a `switch` exhaustiveness proof.

## 21. `permits` Only Affects Direct Subtypes

Suppose:

```java
sealed interface Animal permits Mammal, Bird {
}

non-sealed abstract class Mammal implements Animal {
}

final class Bird implements Animal {
}

class Dog extends Mammal {
}

class Cat extends Mammal {
}
```

In the diagram:

```text
sealed Animal
├── non-sealed Mammal
│   ├── Dog
│   └── Cat
└── final Bird
```

`Animal.permits Mammal, Bird` is sufficient. `Dog` and `Cat` are indirect implementations of Animal through Mammal.

If you change Dog to:

```java
// Compile-negative if Dog is not permitted:
class Dog implements Animal {
    // ...
}
```

then Dog now **directly** implements Animal, which is a completely different relationship from before. Java rejects it if Dog is not in the permitted set.

### Design Consideration

When adding a subtype, determine **which type it directly extends/implements**. Do not rely only on checking `instanceof Animal` or the statement "it is also an Animal" because `instanceof` also matches indirect descendants.

## 22. Conditions on `permits` and Module/Package

`final`/`sealed`/`non-sealed` determines **the extension policy of the branch**; the placement of permitted direct children is still subject to its own restrictions:

- **Named module:** must be in the same named module; may be in a different package if type visibility is valid.
- **Unnamed module:** must be in the same package.
- Every child still needs to directly extend/implement the parent and have valid constructor/access.

For example, in a file `Payment.java` belonging to package `demo`:

~~~java
package demo;
public sealed interface Payment permits Cash, Card {}
final class Cash implements Payment {}
final class Card implements Payment {}
~~~

Classes in other packages cannot add themselves directly to a root in an unnamed module. If you want plugins outside the boundary, allow an appropriate `non-sealed` branch. The lesson **Same-Module or Same-Package Constraints** presents multi-file examples, named modules, and source layouts; this section only reviews the constraints in combination with branch modifiers.

## 23. Permits Can Be Inferred When Direct Children Are in the Same Compilation Unit

When the sealed parent and direct children are in the same **compilation unit**, the explicit `permits` clause can be omitted:

~~~java
sealed interface Shape {}
record Circle(double radius) implements Shape {}
record Square(double side) implements Shape {}
~~~

The compiler infers permitted direct children from declarations in the same source file, and does **not** automatically search for all classes in the package when split across files. This does not change the requirement that each child must choose the proper extension policy. The lesson **Conditions for Inferring the Subclass List When Omitting permits** explains canonical names, local/anonymous types, and compilation-unit conditions in depth; the main focus here is choosing `final`/`sealed`/`non-sealed` once direct children have been determined.

## 24. Runnable: permits Inference in a Single File

Save **`InferredPermitsDemo.java`**:

```java
sealed interface Shape {
    int area();
}

record Square(int side) implements Shape {
    @Override
    public int area() {
        return side * side;
    }
}

record Rectangle(int width, int height) implements Shape {
    @Override
    public int area() {
        return width * height;
    }
}

public class InferredPermitsDemo {
    public static void main(String[] args) {
        Shape first = new Square(3);
        Shape second = new Rectangle(3, 4);

        System.out.println(first.area());
        System.out.println(second.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 InferredPermitsDemo.java
java InferredPermitsDemo
```

Stdout:

```text
9
12
```

`Shape` remains sealed even without writing an explicit `permits` clause. The compiler infers the direct permitted types from the declarations in the same compilation unit. `Square` and `Rectangle` are records, which are implicitly final.

## 25. Case Where a Direct Child Forgets the Modifier

Code **intentionally designed not to compile**:

```java
sealed class Base permits Child {
}

class Child extends Base {
}
```

The error is that `Child` does not declare a `final`, `sealed`, or `non-sealed` policy as a direct permitted subclass of the sealed Base.

Different ways to fix it:

```java
// Close the branch:
final class Child extends Base { }
```

```java
// Open the branch:
non-sealed class Child extends Base { }
```

```java
// Control one more level:
sealed class Child extends Base permits Grandchild { }
final class Grandchild extends Child { }
```

Each snippet is **a separate option**; do not put all three identically named declarations into the same source file.

## 26. Why Is `abstract class Child` Not Enough?

`abstract` answers the question "can this class be directly instantiated?", not the question "who is allowed to extend this class?".

Invalid code:

```java
sealed class Root permits AbstractChild {
}

abstract class AbstractChild extends Root {
}
```

`AbstractChild` is still missing final/sealed/non-sealed. Two valid ways:

```java
abstract non-sealed class AbstractChild extends Root {
}
```

or:

```java
abstract sealed class AbstractChild extends Root
        permits ConcreteChild {
}

final class ConcreteChild extends AbstractChild {
}
```

**Do not write `abstract final class`**, because abstract requires a concrete subclass to instantiate while final prevents subclassing.

## 27. A Direct Subinterface Must Be sealed or non-sealed

Invalid:

```java
sealed interface Root permits Branch {
}

interface Branch extends Root {
}
```

`Branch` directly extends the sealed Root without a modifier.

Fix it to:

```java
non-sealed interface Branch extends Root {
}
```

Or:

```java
sealed interface Branch extends Root permits Leaf {
}

final class Leaf implements Branch {
}
```

It cannot be fixed with `final interface Branch` — Java forbids final interfaces.

### What About an Ordinary Subinterface of a non-sealed Interface?

Valid:

```java
sealed interface Root permits Open {
}

non-sealed interface Open extends Root {
}

interface Further extends Open {
}

class Impl implements Further {
}
```

`Further` is not a direct subinterface of the sealed Root; Further's direct superinterface is Open (non-sealed), so Further is not forced to specify sealed/non-sealed.

## 28. Forbidding `permits` on a non-sealed Type

A `non-sealed` type cannot simultaneously declare its own permits whitelist:

```java
// Compile-negative:
sealed interface Root permits Open {
}

non-sealed interface Open extends Root permits Only {
}
```

`permits` applies when the declaration is a sealed type, not a non-sealed extension point.

If you want to restrict it, declare `sealed interface Open extends Root permits Only`; if you want to open it, write `non-sealed interface Open extends Root` without permits.

**A branch cannot simultaneously declare itself "open" and specify a closed list of direct children in the same declaration.**

## 29. A Class Implementing Two Sealed Interfaces

A class can directly implement multiple interfaces, including multiple sealed interfaces, but in that case **each sealed interface must permit that class**, and the class must satisfy the modifier requirement:

```java
sealed interface Readable permits SharedResource {
}

sealed interface Writable permits SharedResource {
}

final class SharedResource implements Readable, Writable {
}
```

Valid if the other package/module/access conditions are all satisfied.

If `Writable` only permits another class, SharedResource cannot directly implement Writable, even if Readable permits it.

### Design Lesson

Permission does not propagate automatically from one interface to another. Each **direct sealed parent** independently controls its list of permitted direct subtypes.

## 30. Runnable: Implementing Two Sealed Contracts Simultaneously

Save **`MultipleSealedParentsDemo.java`**:

```java
sealed interface Left permits Dual {
    String left();
}

sealed interface Right permits Dual {
    String right();
}

final class Dual implements Left, Right {
    @Override
    public String left() {
        return "L";
    }

    @Override
    public String right() {
        return "R";
    }
}

public class MultipleSealedParentsDemo {
    public static void main(String[] args) {
        Dual value = new Dual();

        System.out.println(value.left() + value.right());
        System.out.println(value instanceof Left);
        System.out.println(value instanceof Right);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 MultipleSealedParentsDemo.java
java MultipleSealedParentsDemo
```

Stdout:

```text
LR
true
true
```

The `Dual` class directly implements both `Left` and `Right`; both include Dual's name in permits. `final` on Dual resolves the child branch for both contracts.

## 31. Record as a Subclass: Conditions to Remember

For a sealed **interface**, a record can implement it directly:

```java
sealed interface Outcome permits Ok, Err {
}

record Ok(int value) implements Outcome {
}

record Err(String message) implements Outcome {
}
```

Why not write a record that extends a sealed **class**?

A `record` cannot extend an arbitrary class: a Java record already implicitly extends `java.lang.Record` and is final. Therefore:

```java
// Compile-negative:
sealed class Base permits SomeRecord {
}
record SomeRecord(int n) extends Base {
}
```

is invalid because a record declaration cannot specify `extends Base` like a normal class. If you want records to serve as leaf variants, prefer a sealed interface.

### Enums Also Have Their Own Mechanism

Enum classes have implicit final/sealed rules depending on constant-specific class bodies, and cannot extend a class other than `java.lang.Enum`. They can participate in a hierarchy through interfaces when declarations satisfy permits requirements and JLS rules; you should not mechanically apply the ordinary class rule `final class Child` to enum syntax.

## 32. `non-sealed` Is Still Subject to Constructor and Visibility Restrictions

An example that looks "open":

```java
sealed class Root permits Open {
}

non-sealed class Open extends Root {
    private Open() {
    }
}
```

If a class outside the private/nest access scope tries to `extends Open`, the compiler may have no accessible way to invoke the superclass constructor, so that subclass is invalid even though Open is non-sealed.

To make an extension point genuinely usable:
- Provide an appropriate accessible constructor, typically protected/public depending on the contract.
- Design stable invariants for subclasses.
- Ensure the supertype/constructor is accessible across module/package boundaries.
- Expose the methods that extensions need to override.
- Check security, thread-safety, and lifecycle if third parties write subclasses.

**The `non-sealed` keyword does not grant extra access permissions.** It only removes the *sealed direct-subtype whitelist* at that type.

## 33. Runnable: Extension Point with a Protected Constructor

Save **`OpenExtensionConstructorDemo.java`**:

```java
sealed abstract class Renderer permits RendererExtension {
    abstract String render();
}

abstract non-sealed class RendererExtension extends Renderer {
    protected final String prefix;

    protected RendererExtension(String prefix) {
        this.prefix = prefix;
    }
}

final class HtmlRenderer extends RendererExtension {
    HtmlRenderer() {
        super("<html>");
    }

    @Override
    String render() {
        return prefix + "content</html>";
    }
}

public class OpenExtensionConstructorDemo {
    public static void main(String[] args) {
        Renderer renderer = new HtmlRenderer();

        System.out.println(renderer.render());
        System.out.println(renderer instanceof RendererExtension);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 OpenExtensionConstructorDemo.java
java OpenExtensionConstructorDemo
```

Stdout:

```text
<html>content</html>
true
```

`Renderer` remains sealed, but `RendererExtension` is a non-sealed extension point. `HtmlRenderer` is not in Renderer.permits; it directly extends RendererExtension and indirectly inherits from Renderer.

## 34. The Purpose of `final` in Domain Modeling

A sealed hierarchy typically represents a **set of variants of the same concept**:

```java
sealed interface PaymentMethod
        permits CardPayment, BankTransfer, CustomPayment {
}

record CardPayment(String lastFour)
        implements PaymentMethod {
}

record BankTransfer(String iban)
        implements PaymentMethod {
}

non-sealed interface CustomPayment
        extends PaymentMethod {
}
```

The two record leaves represent **the variants controlled by the core system**. `CustomPayment` is an intentional extension point.

If the Card payment type must not allow arbitrary subclasses beyond `CardPayment`, a record/final class locks down the branch's representation. If CustomPayment is used for plugins, the API must define the validation and security responsibilities of custom implementations.

### Is Sealed Always Better Than Enum?

Not necessarily. An enum is suitable when the variants are a **known set of singleton constants** with little or no per-instance payload. A sealed interface + final record leaves is suitable when each variant can have **multiple instances carrying different payloads**.

For example, `Success("A")` and `Success("B")` are two record objects with different state; that differs from `enum Status.SUCCESS`, which is just a single enum constant.

## 35. When Should You Choose `sealed` at an Intermediate Level?

Choose `sealed` for an intermediate class/interface when:
- The domain already knows the list of subgroups at that level.
- You do not want plugins to create arbitrary subtypes within a sensitive group.
- Shared invariants or behaviors are needed at the intermediate level.
- You want future additions to that group to require review via modifying permits.
- There are several final/record leaf variants at the final level.

Example structure:

```text
sealed Request
├── final Ping
├── sealed AuthRequest
│   ├── final PasswordRequest
│   └── final TokenRequest
└── non-sealed ExtensionRequest
    └── [plugin-defined classes...]
```

The `AuthRequest` branch is locked down because it involves security. The `ExtensionRequest` branch is opened according to the plugin contract. This expresses intent much more clearly than an ordinary parent class that permits any subclass.

### Do Not Increase Depth Unnecessarily

Too many sealed levels (A permits B; B permits C; C permits D) can make a hierarchy hard to read. Only use an intermediate sealed type when it represents a necessary business grouping or policy.

## 36. Switch and Sealed Hierarchies in Java 17

In Java 17:
- `instanceof` pattern matching is a stable feature and can be used to distinguish variants.
- `switch` expressions with enums are a stable feature.
- **Pattern matching for switch over sealed types is not yet a standard non-preview feature in Java 17**. Do not write a `switch (shape) { case Circle c -> ... }` as a regular `javac --release 17` example.
- Do not assume the Java 17 compiler proves exhaustiveness of an `if/else` chain solely from sealed permits.

A way to handle this without preview:

```java
static String describe(Shape shape) {
    if (shape instanceof Circle circle) {
        return "circle:" + circle.radius();
    }
    if (shape instanceof Square square) {
        return "square:" + square.side();
    }
    throw new IllegalStateException("unsupported");
}
```

This is a **snippet** assuming `Shape` is a sealed interface and `Circle`/`Square` are records. The final error handling should be designed to suit the API. If another permitted subtype is added later, the handling must be updated manually.

### Can Safety Be Increased with a Visitor?

A visitor or polymorphic method declared in the sealed parent can make the compiler require each concrete leaf to provide behavior, reducing omissions when a new variant is added. However, which API is better depends on the goal: transformation, extensibility, or separation of concerns.

## 37. Runnable: Polymorphism Instead of Preview Switch

Save **`SealedPolymorphismDemo.java`**:

```java
sealed interface Shape permits Circle, Rect {
    int area();
}

record Circle(int radius) implements Shape {
    @Override
    public int area() {
        return 3 * radius * radius;
    }
}

record Rect(int width, int height) implements Shape {
    @Override
    public int area() {
        return width * height;
    }
}

public class SealedPolymorphismDemo {
    public static void main(String[] args) {
        Shape a = new Circle(2);
        Shape b = new Rect(4, 5);

        System.out.println(a.area());
        System.out.println(b.area());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedPolymorphismDemo.java
java SealedPolymorphismDemo
```

Stdout:

```text
12
20
```

`Circle` and `Rect` are record leaves. The sealed interface controls direct variants; a polymorphic method lets each variant provide its own implementation without switching on the runtime type.

**Note:** the example formula uses 3 instead of π to get deterministic int output; if calculating the actual area of a circle, use double/Math.PI and round according to the appropriate contract.

## 38. Can an Anonymous Subclass of a Sealed Class Be Created?

Syntax:

```java
// Compile-negative if Base is sealed and only permits the
// listed named types:
Base obj = new Base() {
};
```

An anonymous subclass is also a **direct subclass** of Base. However, a sealed parent only accepts permitted direct subclasses determined according to source/module rules; an anonymous subclass at a call site cannot arbitrarily bypass the whitelist.

Conversely, if the object is created from an accessible **non-sealed branch**:

```java
sealed class Base permits Open {
}

non-sealed class Open extends Base {
}

Open instance = new Open() {
    @Override
    public String toString() {
        return "anonymous extension";
    }
};
```

can be valid because the anonymous class directly extends **Open**, rather than directly extending the sealed Base. Constructor/access rules still apply as usual.

### Conclusion

`sealed` controls **direct subclass declarations**, whether named or anonymous. `non-sealed` opens a point downward to allow normal subclassing capabilities again.

## 39. Binary/Class Loading and the Meaning of Sealed

In Java 17, sealed relationships are not merely a comment convention:
- The compiler checks permits and direct subtype modifiers at the source level.
- The `PermittedSubclasses` class-file metadata represents direct inheritance permission according to JVM/class-file rules.
- When class loading/linking encounters an unpermitted direct subtype, the JVM can reject the class with an appropriate linkage error.
- `Class.isSealed()` and `Class.getPermittedSubclasses()` provide a Reflection API for inspecting sealed types.

Do not treat Reflection metadata as a list of all runtime instances or the entire *transitive closure* of descendants. The permitted subclasses API refers to **direct permitted types**.

**Note:** this rule does not by itself prove that every object creation site is safe; methods, state, and business logic still need validation.

## 40. Runnable: Reflection with Direct Permitted Types

Save **`SealedReflectionDemo.java`**:

```java
import java.util.Arrays;

sealed interface Root permits Alpha, Beta {
}

final class Alpha implements Root {
}

non-sealed class Beta implements Root {
}

public class SealedReflectionDemo {
    public static void main(String[] args) {
        System.out.println(Root.class.isSealed());
        System.out.println(Alpha.class.isSealed());
        System.out.println(Beta.class.isSealed());

        Class<?>[] permitted =
                Root.class.getPermittedSubclasses();

        String[] names = Arrays.stream(permitted)
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println(Arrays.toString(names));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
```

Stdout:

```text
true
false
false
[Alpha, Beta]
```

Final `Alpha` and non-sealed `Beta` are both **not sealed themselves**. Root isSealed is true. Sort the names before printing so as not to rely on assumptions about the order of the Reflection array.

## 41. Mistake: A Sealed Parent Permitting an Indirect Descendant Directly?

Suppose:

```java
sealed class Root permits Intermediate {
}

non-sealed class Intermediate extends Root {
}

class Leaf extends Intermediate {
}
```

`Leaf` is an **indirect descendant** of Root, but is **not a direct permitted subtype** of Root.

The following code cannot be made valid merely because Root "has Leaf in the tree":

```java
// Compile-negative because Leaf does not directly extend Root:
sealed class Root permits Intermediate, Leaf {
}
```

**The permits list includes direct subtypes only**. If Leaf directly extends Intermediate, it should not be in Root.permits. If the goal is for Root to directly permit Leaf, the subtype relationship structure must be changed so that Leaf directly extends/implements Root and satisfies all constraints.

## 42. Mistake: `sealed class X` with No Permitted Child

A `sealed` declaration is not meant to represent a branch **with no subclasses at all**.

```java
// Compile-negative if there is no valid direct permitted
// subclass to be inferred:
sealed class Lonely {
}
```

If you truly do not want any subtypes, consider `final class Lonely`. If you want a sealed model, you need valid permitted direct subtypes.

**Do not use `sealed` as a synonym for `final`**:
- `final`: forbids all subclasses.
- `sealed`: allows **a set** of properly declared subclasses.

## 43. Mistake: Mismatched Modifier on a Direct Child

**Invalid — direct class child omits the modifier:**

```java
sealed class Root permits Child {
}

class Child extends Root {
}
```

**Invalid — direct interface child tries to use final:**

```java
sealed interface Root permits Branch {
}

final interface Branch extends Root {
}
```

**Invalid — direct child is `non-sealed` and `sealed` at the same time:**

```java
sealed class Root permits Branch {
}

sealed non-sealed class Branch extends Root {
}
```

**Invalid — direct subclass is not permitted:**

```java
sealed class Root permits Allowed {
}

final class Allowed extends Root {
}

final class Unlisted extends Root {
}
```

These snippets are **intentionally non-compiling**. Do not put them together into one runnable file with identically named declarations.

## 44. When Does `non-sealed` Pose a Design Risk?

`non-sealed` is very useful for extension points, but opening up also creates responsibilities:

- Subclasses may appear that the core team did not know about at release time.
- Subclasses can override non-final methods and change behavior.
- An `instanceof` algorithm checking a few known classes may miss new descendants.
- Serialization/integration frameworks may require subtype registration.
- Invariants are only preserved if the constructor/method design is sound.
- Security-sensitive domains need to control inputs and extension boundaries.
- Public method contracts must be clearly documented (thread safety, exceptions, lifecycle).

If you want an **exhaustive closed union** domain, you should not have a non-sealed branch that is easily extensible. Use final leaves or sealed intermediate groups with final leaves at the end.

## 45. Closed Hierarchy and Open Extension Point

Two illustrative architectures:

**Closed tree:**

```text
sealed Token
├── final Identifier
├── final NumberToken
└── final EndOfInput
```

Advantage: the set of variants is completely controlled. Suitable for a parser/compiler AST, fixed protocol messages, or strictly defined states.

**Hybrid tree:**

```text
sealed Handler
├── final BuiltInHandler
└── non-sealed PluginHandler
    ├── SomePluginHandler
    └── OtherPluginHandler
```

Advantage: controls core categories while still exposing an extension mechanism.

**Where to place non-sealed is a major API decision**, not merely a measure to "eliminate compiler errors."

## 46. Nested Permitted Types

A sealed type can contain nested permitted classes/interfaces, and the permits list can use simple names within valid scope:

```java
public sealed interface QueryResult
        permits QueryResult.Success, QueryResult.Failure {

    record Success(String data) implements QueryResult {
    }

    record Failure(String message) implements QueryResult {
    }
}
```

The two nested records are implicitly static and final; they directly implement QueryResult.

This organization helps:
- Group variants under a single namespace.
- Keep the contract intuitive.
- Avoid creating too many top-level types when the API is small.
- Let the compiler clearly check the subtype policy.

### Visibility Note

Nested types inside an interface are handled according to the modifier rules of interface members; do not assume a nested type is automatically private. If you need to hide details, choose a class-based container, factory, and appropriate visibility.

## 47. Runnable: Nested Record Leaves

Save **`NestedSealedVariantsDemo.java`**:

```java
sealed interface Reply permits Reply.Ok, Reply.Error {
    record Ok(int value) implements Reply {
    }

    record Error(String message) implements Reply {
    }
}

public class NestedSealedVariantsDemo {
    public static void main(String[] args) {
        Reply first = new Reply.Ok(7);
        Reply second = new Reply.Error("bad");

        System.out.println(first);
        System.out.println(second);

        if (first instanceof Reply.Ok ok) {
            System.out.println(ok.value());
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NestedSealedVariantsDemo.java
java NestedSealedVariantsDemo
```

Stdout:

```text
Ok[value=7]
Error[message=bad]
7
```

`Reply.Ok`/`Reply.Error` are direct permitted record classes of the sealed interface Reply, and are implicitly final. Do not use `final interface`.

## 48. Combining `sealed`, `final`, and `non-sealed` Across Levels

A mixed model:

```text
sealed Root
├── final LeafA
├── sealed GroupB
│   ├── final LeafB1
│   └── non-sealed ExtensibleB2
│       ├── PluginB2a
│       └── PluginB2b
└── non-sealed ExtensionC
    └── ThirdPartyC
```

Root has three direct permitted children. GroupB has two direct permitted children. ExtensibleB2 and ExtensionC open two subtrees.

### Relationships to Remember

- `PluginB2a` does not need to be listed by Root.permits or GroupB.permits because it does not directly extend those two sealed types.
- `LeafA` blocks subclassing.
- `GroupB` does not allow arbitrary direct subclasses.
- `ExtensibleB2` permits ordinary descendants.
- `ExtensionC` is similar.

To evaluate whether a new type D can be added, walk each **direct edge** in the class/interface hierarchy rather than vaguely asking "is Root sealed?".

## 49. Implications for Public Library API Design

A library's sealed hierarchy is part of its **public API contract**, not merely documentation: client modules are not allowed to create direct children outside permits; a `non-sealed` branch must have appropriate access/constructors if it is meant to be an extension point.

Changes such as adding a direct variant, removing a leaf, changing non-sealed to sealed/final, or changing constructor visibility can affect source/binary compatibility and consumer behavior. In code reviews, determine **who owns changes to the type tree** and **which branches are allowed to be open**. The lesson **Comparing Closed Hierarchies with Openly Extensible Classes** analyzes versioning, OCP, compatibility, and migration for public APIs in detail.

## 50. An API Pitfall: Blocking Out-of-Module Plugins

Library:

```java
public sealed interface Plugin permits BuiltInPlugin {
}

final class BuiltInPlugin implements Plugin {
}
```

Consuming application wants:

```java
// Compile-negative if not permitted:
public final class MyPlugin implements Plugin {
}
```

You cannot just change `MyPlugin` to `non-sealed` and be done; **Plugin does not permit MyPlugin**, and package/module constraints still apply.

A more sensible extensible design:

```java
public sealed interface Plugin
        permits BuiltInPlugin, ExternalPlugin {
}

final class BuiltInPlugin implements Plugin {
}

public non-sealed interface ExternalPlugin extends Plugin {
}
```

This is an **API design snippet**; in Java, each public top-level type requires its own source file, and named-module visibility/accessibility must be properly declared. Clients in another module can implement `ExternalPlugin` if the type is exported and accessible, rather than directly implementing the sealed Plugin.

## 51. Choosing `final`, `sealed`, or `non-sealed`: Decision Tree

For a **direct subtype of a sealed parent**:

1. **Are any subclasses/implementations needed beneath this type?**
   - No → if it is a class, choose **`final`** (or an implicitly final record).
   - Yes → continue.
2. **Can the valid set of direct subtypes of this type be enumerated and maintained?**
   - Yes → choose **`sealed`**, and define `permits`/inference.
   - No, you want an extension point → choose **`non-sealed`**.
3. **Is this type an interface?**
   - If it is an interface, **there is no final option**.
   - Choose sealed or non-sealed.
4. **Does this type need abstract behavior?**
   - You can combine `abstract sealed` or `abstract non-sealed` for classes.
5. **Does the public API allow third-party extensions?**
   - If yes, check visibility/constructors/modules; non-sealed is necessary but not sufficient.

Do not choose non-sealed merely out of reluctance to write a permits list if the domain actually requires a completely closed tree.

## 52. What Happens When Adding a New Subtype?

Adding a direct child to `State permits Active, Failed` means declaring the child (for example, `Paused`) and then updating the root `permits` if explicit; the child must carry a valid extension policy. Beyond the source declaration, you also need to review business dispatch, serialization, tests, and versioning.

If `Paused` is a child of a **non-sealed intermediate** already permitted by the root, there is no need to add it to the root whitelist. If it is a child of a **sealed intermediate**, update `permits` on that intermediate level itself. This rule is a direct consequence of **direct vs indirect inheritance**, not an automatic descendant-discovery mechanism.

## 53. `instanceof` Risks When a non-sealed Branch Exists

Example:

```java
sealed interface Action permits BuiltIn, Custom {
}

record BuiltIn() implements Action {
}

non-sealed interface Custom extends Action {
}
```

Consumer handling:

```java
if (action instanceof BuiltIn) {
    // ...
} else if (action instanceof Custom) {
    // ...
}
```

The two branches represent the current direct categories, yet additional Custom implementations may arise. The consumer must not assume only a single known `CustomImpl` class exists. Write behavior based on the interface contract of `Custom` instead of checking every concrete class.

### If the Code Truly Needs Exhaustive Cases

Avoid non-sealed along this path or define a clear fallback/extension contract. Java 17 pattern matching with instanceof keeps syntax concise, but **does not prove that a non-sealed branch has only a finite number of concrete classes**.

## 54. Combining Sealed and Visibility

Independent concerns:
- **Sealed restriction**: which types may directly extend/implement?
- **Access control**: can code at the usage site see the class/constructor/member?
- **Final restriction**: does the class allow any subclasses?
- **Abstract restriction**: can it be directly instantiated?
- **Module encapsulation**: is the package/type exported/accessible?

A permitted subclass can be package-private. A public sealed interface can list permitted types that callers cannot reference directly by name from another package. These do not conflict.

**In practice when designing APIs:** if callers only need to handle values through the sealed parent, you can hide concrete implementations and provide factories. If callers need to construct certain variants themselves, you must expose appropriate constructors/factories.

## 55. Wrong-Level Inheritance Errors

Checklist:

| Intent | What to verify |
| --- | --- |
| Add direct child D of sealed S | D is in S.permits/inference; in the same module/package per JLS; D has an appropriate modifier |
| Add child of sealed intermediate T | T.permits/inference is updated; T directly extends/implements S according to rules |
| Add child of non-sealed branch U | No root permits needed for indirect descendant; check access/constructors |
| Close a branch with final | No legal subclasses remain |
| Keep a branch controlled with sealed | The permitted direct children list of the new branch is valid |
| Allow third-party extends/implements | Non-sealed branch has corresponding visibility/module/API |
| Direct subinterface of a sealed interface | Do not use final; sealed/non-sealed |
| Direct record implementation | Record is implicitly final; cannot extend a sealed class |
| A class implementing two sealed interfaces | Both interfaces permit that class if direct |
| Use an anonymous subclass | Cannot directly bypass sealed permits |

## 56. Exercise 1 — Direct Child Without a Modifier

```java
sealed class A permits B {
}

class B extends A {
}
```

**Answer:** Does not compile in Java 17. `B` is a direct permitted subclass, but it must choose `final`/`sealed`/`non-sealed`.

## 57. Exercise 2 — Changing to final

```java
sealed class A permits B {
}

final class B extends A {
}
```

**Answer:** Valid if scope/module/package is appropriate. B prevents further subclassing.

## 58. Exercise 3 — Adding a Grandchild of final

```java
sealed class A permits B {
}

final class B extends A {
}

class C extends B {
}
```

**Answer:** Invalid because B is final, regardless of whether A is sealed.

## 59. Exercise 4 — Non-sealed Branch

```java
sealed class A permits B {
}

non-sealed class B extends A {
}

class C extends B {
}
```

**Answer:** Valid if constructors/access rules are satisfied; C does not need to be listed in A.permits.

## 60. Exercise 5 — Sealed Intermediate

```java
sealed class A permits B {
}

sealed class B extends A permits C {
}

final class C extends B {
}
```

**Answer:** Valid. B is a direct child of A and is also the sealed parent of C. C is an indirect descendant of A.

## 61. Exercise 6 — Sealed Intermediate Missing Children

`sealed class B extends A` with no permits and no child to infer.

**Answer:** Invalid as a sealed declaration if there is no valid permitted direct subtype. If no subclasses are needed, choose `final class B`.

## 62. Exercise 7 — `abstract sealed`

An abstract class B directly extends sealed A. Can you write `abstract sealed class B extends A permits C`?

**Answer:** Yes. Abstract does not conflict with sealed. C must be permitted to directly extend B and have an appropriate modifier.

## 63. Exercise 8 — `abstract non-sealed`

Is `abstract non-sealed class B extends A` valid when A is sealed and permits B?

**Answer:** Yes. B is both non-concrete and open to subclasses.

## 64. Exercise 9 — `abstract final`

Is `abstract final class B extends A` valid as a direct child?

**Answer:** No. Abstract and final conflict regarding subclassability.

## 65. Exercise 10 — `final interface`

A sealed interface A permits B, where B is an interface. Can B be declared `final interface B extends A`?

**Answer:** No. Interfaces cannot be final; use sealed/non-sealed.

## 66. Exercise 11 — Non-sealed Interface

`sealed interface A permits B`, `non-sealed interface B extends A`.

**Answer:** Valid; B is an extension point. A class implementing B indirectly implements A without needing to be permitted by A.

## 67. Exercise 12 — Direct Record

`sealed interface S permits R`, `record R(int x) implements S`.

**Answer:** Valid with appropriate scope. R is implicitly final, so an explicit final modifier is not needed.

## 68. Exercise 13 — Record Extends Sealed Class

`sealed class Base permits R`, `record R(int x) extends Base`.

**Answer:** Invalid because a record cannot extend an application-chosen superclass.

## 69. Exercise 14 — Two Sealed Parents

Sealed interfaces A and B, with class C directly implementing A,B. A permits C, but B does not.

**Answer:** C is invalid because it lacks direct permission from B. Every sealed direct superinterface must permit C.

## 70. Exercise 15 — Permitting an Indirect Grandchild

A permits B; B is non-sealed; C extends B. Should C be added to A.permits for "completeness"?

**Answer:** No. C is not a direct subtype of A, so it does not belong in A's list of direct permitted subtypes.

## 71. Exercise 16 — Non-sealed on an Ordinary Class

Is `non-sealed class Plain { }` valid?

**Answer:** No. Non-sealed only has valid context when the type directly extends/implements an appropriate sealed type.

## 72. Exercise 17 — Re-seal

A is sealed and permits B; B is non-sealed; C is sealed, extends B, and permits D; D is final and extends C.

**Answer:** Valid. C establishes a new sealed boundary on its own within the open branch.

## 73. Exercise 18 — Not Open Across All Modules

A public sealed interface in module M only permits types in M; can code in module N directly implement it on its own?

**Answer:** No. To allow extensions, you need a permitted non-sealed branch with an exported/accessible API that follows module rules.

## 74. Exercise 19 — Unnamed Module

In the classpath/unnamed module, can direct permitted subclasses reside in any package?

**Answer:** No; in an unnamed module, they must be in the **same package** as the sealed parent.

## 75. Exercise 20 — Named Module

In a named module, must direct permitted subclasses be in the same package or the same module?

**Answer:** They must be in the **same named module**. They may be in a different package if Java visibility/import/module access rules allow it.

## 76. Exercise 21 — Permits Inference

A sealed parent and all direct subclasses are declared in the same compilation unit, without explicit permits. Can this be valid?

**Answer:** Yes, if JLS inference requirements are met and the child modifiers are valid.

## 77. Exercise 22 — Inference Does Not Open Completely

If permits are inferred in one file, can a new class in another file freely extend the sealed parent?

**Answer:** No. Inference does not remove the restriction; it must belong to the permitted set under Java rules.

## 78. Exercise 23 — Mutable Final Class

Can `final class Counter extends SealedParent` have a mutable `int count`?

**Answer:** Yes, if the code allows it. Final locks down subclassing; it does not turn all fields into final.

## 79. Exercise 24 — Non-sealed with Private Constructor

A non-sealed class only has private constructors; can a third-party class without private access directly extend it right away?

**Answer:** Not necessarily. A valid accessible constructor is still needed even though non-sealed opened the branch.

## 80. Exercise 25 — `instanceof` in Java 17

Does `if (value instanceof Ok ok) { ... }` on a sealed Result require preview?

**Answer:** No. Instanceof pattern matching is standard in Java 17.

## 81. Exercise 26 — Pattern Switch in Java 17

Does `switch (result) { case Ok ok -> ... }` compile by default with `javac --release 17`?

**Answer:** Not in non-preview Java 17 mode; pattern matching for switch was a preview feature then. Use instanceof/polymorphism or choose a Java version/preview flag intentionally.

## 82. Exercise 27 — Reflection

`Root.class.isSealed()` returns true; what does `NonSealedChild.class.isSealed()` return?

**Answer:** False, because a non-sealed child is not a sealed type. Root's `getPermittedSubclasses()` describes the direct permitted types.

## 83. Exercise 28 — Anonymous Subclass

Creating `new Root(){...}` when Root is sealed, though an anonymous child cannot be validly listed in permits. Is that allowed?

**Answer:** You cannot bypass the sealed direct subclass restriction on your own using anonymous class syntax.

## 84. Exercise 29 — Hybrid Library Extension

A library wants three fixed built-in variants while supporting third-party extensions. How should it be designed?

**Answer:** A sealed root permits the built-in final classes/records and a properly exported/accessible `non-sealed` extension interface/abstract class; plugins extend through the extension point instead of directly implementing the sealed root.

## 85. Exercise 30 — Reading a Multi-Level Tree

```text
sealed Root
├── sealed BranchA
│   ├── final Leaf1
│   └── non-sealed ExtensionA
└── final BranchB
```

A class X extends ExtensionA, a class Y extends Leaf1, and a class Z extends Root without being permitted.

**Answer:** X can be valid depending on access/constructor rules; Y is invalid because Leaf1 is final; Z is invalid because Root does not directly permit Z.

## 86. Exercise 31 — Which Modifier Is Appropriate?

A direct class child needs to allow **exactly two** subclasses controlled by the team.

**Answer:** Choose `sealed` and permit the two direct children; do not choose non-sealed or final.

## 87. Exercise 32 — Which Modifier Is Appropriate?

A direct class child represents a terminal data variant that must not be subclassed.

**Answer:** `final class`, or `record` when the data fits record semantics. For an interface child, there is no final.

## 88. Exercise 33 — Which Modifier Is Appropriate?

A direct subinterface needs third parties to implement it without a whitelist restriction on that branch.

**Answer:** `non-sealed interface`, with appropriate public API/module exports and method contracts.

## 89. Exercise 34 — Changing from non-sealed to sealed

Changing a public `non-sealed class Extension` to sealed with a few permitted subclasses. Can this break the API?

**Answer:** Yes. Existing subclasses on the client side may no longer compile/load validly; a versioning and migration plan is needed.

## 90. Exercise 35 — An Interface Extending Two Sealed Parents

Interface C directly extends sealed interfaces A and B. Must both A and B permit C?

**Answer:** Yes. C must also declare `sealed` or `non-sealed` (an interface cannot be final).

## 91. Exercise 36 — Comprehensive True/False Questions

Evaluate the statements:

1. `final` allows the class to be extended if the parent already permits it.
2. `sealed` is used to list a set of direct permitted subtypes.
3. `non-sealed` opens the branch, but does not automatically open private constructors.
4. Every indirect descendant of a sealed parent must be included in the root permits.
5. A record can directly implement a sealed interface if permitted.
6. An interface can use `final` to lock a branch.
7. A sealed intermediate can have final leaves.
8. A non-sealed branch can be sealed again at a descendant.
9. A non-sealed child of a sealed parent can be abstract.
10. Java 17 supports instanceof pattern matching without preview.

**Answer:** 1 false; 2 true; 3 true; 4 false; 5 true; 6 false; 7 true; 8 true; 9 true; 10 true.

## 92. Common Errors and Quick Fixes

| Incorrect assumption/code | Why it is wrong | How to fix |
| --- | --- | --- |
| Direct class child omits modifier | Sealed parent forces child to choose an inheritance policy | `final`/`sealed`/`non-sealed` |
| Direct interface child writes final | Interfaces cannot be final | Choose `sealed` or `non-sealed` |
| `abstract` is enough for a direct child | Abstract does not determine subclass openness | Add sealed or non-sealed |
| `final sealed class Child` | Two conflicting policies | Choose one |
| `sealed non-sealed class Child` | Two conflicting policies | Choose one |
| `non-sealed class Plain` without a direct sealed parent | Modifier is invalid in this position | Use an ordinary class or change the hierarchy |
| Non-sealed child has `permits` | Permits is for sealed declarations | Use sealed or remove permits |
| Root indirectly permits Grandchild | Permits only lists direct subtypes | Only permit direct children |
| Subclass is not in permits | Violates the sealed direct subtype restriction | Add it validly or extend a non-sealed branch |
| Changing `final` to `non-sealed` to "fix" compilation | May unintentionally open the API | Choose according to the domain contract |
| Record uses `extends SealedClass` | Records cannot extend arbitrary classes | Design a sealed interface |
| No permitted children | Sealed requires a valid direct subtype | Use final if no child is wanted |
| Sealed parent class in unnamed module, child in another package | Violates the same-package restriction | Move the child to the right package or use module design |
| Named-module child in a different module | Violates the same-module restriction | Change module ownership or use an extension point |
| `public sealed` means any client can implement it directly | Public visibility differs from permitted list | Non-sealed extension point |
| Final class is automatically immutable/thread-safe | Final only prevents subclassing | Manage state/thread safety separately |
| Reflection returns "all descendants" | Permits API returns direct subtypes | Traverse the hierarchy intentionally |
| Java 17 pattern switch runs by default | Switch pattern is not yet stable in Java 17 | Use instanceof/polymorphism |
| Non-sealed opens the branch so every subclass is valid | Constructors/access/modules still constrain it | Design an accessible extension contract |

## 93. Code Review Checklist for Sealed Subclasses

- [ ] Does the parent properly have `sealed class` or `sealed interface`?
- [ ] Do the direct subtypes actually directly extend/implement it?
- [ ] Does explicit `permits` or inference accurately reflect the direct children?
- [ ] Does each direct **class** child have `final`, `sealed`, or `non-sealed`?
- [ ] Do direct **interface** children have `sealed` or `non-sealed`, not final?
- [ ] Is a record leaf understood to be implicitly final?
- [ ] If the root is a sealed class, is there no attempt to have a record extend the root?
- [ ] If there are multiple direct sealed parents, do all of them permit the child?
- [ ] Are indirect grandchildren kept out of the root permits?
- [ ] Are no direct permitted children missed when moving files?
- [ ] Are named-module children in the same module?
- [ ] Are unnamed-module children in the same package?
- [ ] Are accessibility and imports of supertypes/constructors valid?
- [ ] Are conflicting combinations of final/sealed/non-sealed avoided?
- [ ] Does an abstract child choose sealed/non-sealed appropriately?
- [ ] Does a sealed intermediate have valid children and no cycles?
- [ ] Is a non-sealed branch opened intentionally?
- [ ] Does a third-party extension point have appropriate API, constructors, and module exports?
- [ ] Have the consequences of opening a branch for input validation/security been evaluated?
- [ ] Have class names/visibility that accidentally make the API hard to use been avoided?
- [ ] Are there cases where resealing is needed beneath a non-sealed branch?
- [ ] Is a final leaf used when a subtype should not be extended?
- [ ] If an immutable value variant is desired, are record components designed and validated appropriately?
- [ ] Is `final` not mistaken for immutable/thread-safe?
- [ ] Do API consumers handle indirect variants of a non-sealed branch?
- [ ] If type-based dispatch is used, have fallback and subclass openness been accounted for?
- [ ] Does the Java 17 code avoid depending on preview switch patterns?
- [ ] Is the code run using the exact Java 17 JDK/source release?
- [ ] Do public class names match file names in each example?
- [ ] Are all compile-negative snippets separated from runnable programs?
- [ ] Do tests cover adding/removing subtypes according to the domain contract?
- [ ] Are there regression tests when changing non-sealed/final/sealed policy?
- [ ] If it is a library, have source/binary compatibility and module boundaries been reviewed?
- [ ] Is the "closed or open" policy documented at each important branch?
- [ ] Is the distinction between direct vs indirect subtypes maintained during code review?

## 94. Summary: Three Paths for a Direct Subclass

**`final`** answers: "This branch stops here."  
**`sealed`** answers: "This branch can still be extended, but only according to the list of children I control."  
**`non-sealed`** answers: "From this branch downward, I do not apply a sealed whitelist; standard Java inheritance/access rules decide."

This rule applies at **every node that is a direct subtype of a sealed parent**. A sealed parent only governs its *direct* children; it does not automatically close all descendants if a branch chooses non-sealed. Sealed interfaces can have sealed/non-sealed direct subinterfaces; class leaves can be final; record leaves are implicitly final.

When designing a domain:
- Use **final leaves** for terminal variants.
- Use a **sealed intermediate** when a subgroup needs to remain closed.
- Use a **non-sealed extension point** when intentionally allowing external parties to continue extending.
- Combine these choices to preserve important invariants while opening up exactly where extension is needed.

**How to remember:** Look at *each direct edge* in the inheritance tree. A sealed ancestor does not forbid indirect descendants of a non-sealed branch; it only controls who gets to cross the first edge.

## Official Java SE 17 Documentation

- **Java Language Specification `8.1.1.2 — `sealed`, `non-sealed`, `final` class modifiers**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2
- **JLS `8.1.4 — Superclasses and Subclasses**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.4
- **JLS `9.1.1.4 — Sealed Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4
- **JLS `13.4 — Evolution of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.4
- **Java SE 17 `Class.isSealed()`/`getPermittedSubclasses()` API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
