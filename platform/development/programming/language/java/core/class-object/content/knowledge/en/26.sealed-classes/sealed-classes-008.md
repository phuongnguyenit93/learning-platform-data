# When `sealed` Is Appropriate for Modeling Kinds of Values in Java 17+

## 1. The Design Problem: A Value Can Take One of Several Shapes

Not all data shares the same set of fields. A successful payment result may carry a transaction ID; a failure carries a decline reason; a pending result carries a scheduled time. If you try to put everything into one class with many nullable fields such as `success`, `receiptId`, `error`, `retryAt`, you can easily create invalid states: having both a transaction ID and a failure reason, or `success=true` while the transaction ID is null.

A better way to express this is: **a value belongs to exactly one of the variants with their own structure**.

~~~java
sealed interface PaymentResult permits Approved, Declined {
}

record Approved(String receiptId) implements PaymentResult {
}

record Declined(String reason) implements PaymentResult {
}
~~~

These are three **valid Java 17 declarations**, not a program with `main`. `PaymentResult` is the common type; `Approved` and `Declined` are the **direct permitted implementations**. Each variant has its own data and can be distinguished using `instanceof` or polymorphic behavior.

**`sealed` is appropriate when the set of direct kinds of values is an important part of the domain contract and you want the library/module itself to own that list.** Pay special attention to the word **direct**: a `non-sealed` branch can reopen indirect extension.

This lesson belongs to **Java core – class-object**, group **Sealed classes**, section **When sealed is appropriate for modeling kinds of values**. The content focuses on **design selection criteria**, not just memorizing syntax. All standalone programs below use **Java 17 or later**, without preview features; invalid code is labeled separately.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Explain why a general type with many nullable fields is often less safe than explicit variant types.
2. Identify the signs that indicate when to use **sealed interface + record variants**.
3. Distinguish restricting **direct permitted subtypes** from closing all descendants.
4. Recognize when `enum` is simpler than `sealed`.
5. Choose `sealed abstract class` if you need to share state, constructors, or implementations, instead of forcing a record to extend a class.
6. Choose an open interface or a `non-sealed` branch when plugins/extensions are needed.
7. Model states, results, commands, events, or syntax trees using typed variants.
8. Understand the trade-offs when adding a new variant in a public API.
9. Apply `instanceof` type patterns in Java 17 without confusing them with pattern `switch`, which was standardized in Java 21.
10. Understand that sealed does not automatically guarantee deeply immutable data, non-nullness, security, or exhaustiveness of an `if` chain.
11. Design tests for variants, state transitions, and validation.
12. Choose between a polymorphic method, a visitor, and type-dispatch according to your needs.

## 3. Concise Decision Rules

You can use four sequential questions:

**A. Does the value set have few kinds and is it controlled within the same domain/module?** If yes, this is a sign leaning toward sealed. If external parties all need to create new kinds, an open interface is usually more appropriate.

**B. Do the kinds have different data structures?** If you have `Success(data)`, `Failure(error)`, `Pending(retryAt)`, a sealed interface + records helps keep each payload matched to its kind. If it is just a set of constant names `RED`, `GREEN`, `BLUE`, an enum is usually easier.

**C. Do you want callers to be forced to handle the known variants?** A closed hierarchy can help describe the list of types clearly; however, **Java 17 does not automatically check exhaustiveness of every `if instanceof` chain**, and pattern matching `switch` for this hierarchy is not yet a stable non-preview feature in Java 17.

**D. Is sharing inheritance/state really needed?** If the variants are mainly payload records, choose a sealed interface. If each variant inherits logic and a base class constructor, consider a sealed class. If you only need to share ordinary behavior without closing extension, a regular interface may suffice.

A good sign of the design is that **domain meaning is stated through type names**, rather than inferred from a pair of flags and multiple null fields.

## 4. “One of Multiple Types” Values and Sum Types

Many sources refer to the modeling approach above as something close to an **algebraic data type — sum type**. A `PaymentResult` can be `Approved` **or** `Declined`; each choice has its own fields.

~~~text
PaymentResult
├── Approved(receiptId: String)
└── Declined(reason: String)
~~~

There is no `Approved` variant carrying `reason` instead of `receiptId` unless you intentionally design that type that way. Values with the wrong shape can be blocked right at compile time or during constructor validation.

**Exact boundary:** a `sealed interface` only defines the set of direct subtypes. If a permitted child is `non-sealed`, an unlimited number of indirect descendants can grow beneath it. To model **closing all concrete variants**, choose `final` leaf variants (including records, which are implicitly final) or keep sealing every branch down to the leaves, and do not add a `non-sealed` branch.

## 5. Program 1 — Payment Results with Different Data

File **`PaymentResultDemo.java`**:

~~~java
sealed interface PaymentResult permits Approved, Declined {
}

record Approved(String receiptId) implements PaymentResult {
    Approved {
        if (receiptId == null || receiptId.isBlank()) {
            throw new IllegalArgumentException("receiptId");
        }
    }
}

record Declined(String reason) implements PaymentResult {
    Declined {
        if (reason == null || reason.isBlank()) {
            throw new IllegalArgumentException("reason");
        }
    }
}

public class PaymentResultDemo {
    static String explain(PaymentResult result) {
        if (result instanceof Approved approved) {
            return "OK:" + approved.receiptId();
        }
        if (result instanceof Declined declined) {
            return "NO:" + declined.reason();
        }
        throw new IllegalArgumentException("unknown result");
    }

    public static void main(String[] args) {
        PaymentResult success = new Approved("TX-7");
        PaymentResult failure = new Declined("insufficient funds");
        System.out.println(explain(success));
        System.out.println(explain(failure));
        System.out.println("success type="
                + success.getClass().getSimpleName());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 PaymentResultDemo.java
java PaymentResultDemo
~~~

**Stdout:**

~~~text
OK:TX-7
NO:insufficient funds
success type=Approved
~~~

In the Approved variant, the constructor only checks the transaction ID. In Declined, the constructor only checks the failure reason. They do not have to hold fields that do not apply to them.

`instanceof Approved approved` is **pattern matching for instanceof**, finalized in Java 16 and stable in Java 17. The `throw` branch states the policy if an unexpected value appears, including null. The Java 17 compiler does not prove this if chain exhaustive solely because of `sealed`.

## 6. Comparison with “One Class with Many Nullable Fields”

Less clear design:

~~~java
class PaymentResponse {
    boolean successful;
    String receiptId;
    String error;
}
~~~

This is a valid illustrative class. It allows nonsensical states:

- `successful=true` but `receiptId=null`.
- `successful=false` but `receiptId="TX-7"`.
- `successful=true` while `error="DECLINED"`.

You can add constructor validation and factory methods to reduce errors; **sealed is not the only way**. However, when variants genuinely have **different sets of fields**, separate subtypes express the contract directly without requiring excessive cross-field null/flag relationships.

| Question | One class with flags/null fields | Sealed with records |
| --- | --- | --- |
| Where is the variant represented? | A field/flag | The concrete type |
| Payload for each branch | Many optional fields | Components of each variant |
| Are invalid states easy to create? | Yes if invariants are missing | Greatly reduces wrong-shape errors; validation is still needed |
| Extending variants | Usually add flags and fields | Add permitted type, update consumers |
| API type | One class | Common interface/abstract class |
| Does it support polymorphism? | Can write methods manually | Can be applied naturally |
| Suitable for open plugin systems? | Depends on the API | Fully sealed is usually unsuitable |

Important: `record` automatically provides final fields, but **does not automatically reject null or invalid content**. Validation in each canonical constructor is still needed when the domain requires it.

## 7. When It Is Just a Fixed Set of Named Values: Choose `enum`

If a state only has a few named constants and **does not need a separate payload per variant**, `enum` is usually more concise:

~~~java
enum OrderPhase {
    CREATED, PACKED, SHIPPED, DELIVERED
}
~~~

Enums provide constant instances, `values()`, `valueOf(...)`, and stable `switch` support on enums in Java 17. Compare enum constants using `==`.

A sealed hierarchy with empty records for each of `Created`, `Packed`, `Shipped` can be overengineering if each variant **is just a label** and has no distinct behavior or payload.

Conversely, if `Shipped` always needs `trackingCode` and `Delivered` needs `deliveredAt`, sealed variants can express the structure better, because enum constants do not hold component values **specific to each event occurrence** the way record instances do.

Do not treat enum and sealed as mutually exclusive features: an enum can be **a permitted direct implementor** of a sealed interface when the model requires it.

## 8. Program 2 — Enum for Constants, Sealed for Results with Payloads

File **`EnumOrSealedDemo.java`**:

~~~java
enum JobStage {
    QUEUED, RUNNING, FINISHED
}

sealed interface UploadResult permits Uploaded, UploadFailed {
}

record Uploaded(String fileId, int size)
        implements UploadResult {
}

record UploadFailed(String reason)
        implements UploadResult {
}

public class EnumOrSealedDemo {
    public static void main(String[] args) {
        JobStage stage = JobStage.RUNNING;
        UploadResult result = new Uploaded("file-1", 12);

        System.out.println("stage=" + stage);
        System.out.println("is running="
                + (stage == JobStage.RUNNING));
        System.out.println("result=" + result);
        System.out.println("failed="
                + (result instanceof UploadFailed));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 EnumOrSealedDemo.java
java EnumOrSealedDemo
~~~

**Stdout:**

~~~text
stage=RUNNING
is running=true
result=Uploaded[fileId=file-1, size=12]
failed=false
~~~

`JobStage` represents fixed state names. `Uploaded` is a **distinct object for a specific upload**, carrying a file ID and size. You should not force such data into a global enum instance and mutate fields, because enum constants exist as shared objects.

## 9. Variants with Different Payload Types Are a Strong Signal for Sealed

Many systems have the same “general result kind” but different payloads:

- `Authenticated(userId)` or `Unauthorized(reason)`.
- `Found(value)` or `NotFound(key)`.
- `FileCreated(path, bytes)` or `FileRejected(code)`.
- `Circle(radius)` or `Rectangle(width, height)`.
- `Add(left, right)` or `Literal(value)` in an AST.

Here, having multiple constructors with different parameters **does not automatically create explicit subtypes**. If everything goes into a single class, callers may have to check `kind` before reading fields and deal with fields that do not apply.

Sealed variants make the type of each payload more specific. This is especially useful when values pass through multiple layers: controller → service → processor → renderer.

**However**, if the API only needs a `status` field and every payload shares the same structure, there is no need to force sealed at all costs. Use a regular record or enum for simple cases.

## 10. Program 3 — Notifications with Different Payloads per Channel

File **`NotificationVariantsDemo.java`**:

~~~java
sealed interface Notification permits EmailNotice, SmsNotice {
}

record EmailNotice(String email, String subject)
        implements Notification {
    EmailNotice {
        if (email == null || subject == null) {
            throw new IllegalArgumentException("missing email data");
        }
    }
}

record SmsNotice(String number, String text)
        implements Notification {
    SmsNotice {
        if (number == null || text == null) {
            throw new IllegalArgumentException("missing sms data");
        }
    }
}

public class NotificationVariantsDemo {
    static String route(Notification item) {
        if (item instanceof EmailNotice email) {
            return "email:" + email.email()
                    + ":" + email.subject();
        }
        if (item instanceof SmsNotice sms) {
            return "sms:" + sms.number()
                    + ":" + sms.text();
        }
        throw new IllegalArgumentException("unsupported");
    }

    public static void main(String[] args) {
        Notification a =
                new EmailNotice("a@example.test", "Hello");
        Notification b = new SmsNotice("123", "Ready");
        System.out.println(route(a));
        System.out.println(route(b));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 NotificationVariantsDemo.java
java NotificationVariantsDemo
~~~

**Stdout:**

~~~text
email:a@example.test:Hello
sms:123:Ready
~~~

Each record only has the fields needed for its channel. Validation prevents null in the example, but does not claim that email/phone formats have been validated. Real validation rules are domain-specific.

**Consideration:** if Notification is a plugin framework where third parties must add new channels themselves, sealing everything can become an obstacle. In that case, an open interface or an extension branch is the better choice.

## 11. When the Direct List Needs to Be Owned and Controlled

One of the most important reasons for sealed is **who is allowed to extend the set of variants**.

~~~java
sealed interface DomainEvent permits CreatedEvent, DeletedEvent {
}

record CreatedEvent(String id) implements DomainEvent {
}

record DeletedEvent(String id) implements DomainEvent {
}
~~~

These are valid declarations. This is a contract allowing only two types to **directly** implement DomainEvent. An external module cannot arbitrarily write `implements DomainEvent` to create a new direct subtype outside the list.

This fits well when the list of variants must be reviewed together with **schemas, validation, serialization, and downstream processing**. It does not fit when the goal of DomainEvent is to provide a hook where clients freely define new types.

A sealed hierarchy is a **type-system governance** decision, not merely shorthand syntax. Control over direct types resides where the sealed type and its permitted types are defined, within module/package boundaries.

## 12. “Closing Direct Children” Differs from “Closing All Descendants”

Example:

~~~java
sealed interface Task permits BuiltInTask, PluginTask {
}

record BuiltInTask(String name) implements Task {
}

non-sealed interface PluginTask extends Task {
}
~~~

`BuiltInTask` is an implicitly final record. `PluginTask` is a permitted subinterface, yet it is **non-sealed**, meaning other implementations of PluginTask can be declared according to ordinary Java rules.

If `SpecialTask implements PluginTask`, it is an indirect subtype of Task and **does not need** to appear in `Task permits ...`.

~~~text
          Task (sealed)
           /         \
 BuiltInTask      PluginTask (non-sealed)
    (final)             |
                     SpecialTask
                        |
                     ...open...
~~~

When you want “every Task value to have only two absolute concrete forms,” a `non-sealed` branch will **break that closure**. When you want “two direct Task families, one of which is for plugins,” non-sealed is instead a useful tool.

## 13. Program 4 — Intentionally Both Closed and Open Model

File **`ExtensionPointDemo.java`**:

~~~java
sealed interface ReportItem permits TextItem, ExternalItem {
    String render();
}

record TextItem(String text) implements ReportItem {
    @Override
    public String render() {
        return "text:" + text;
    }
}

non-sealed interface ExternalItem extends ReportItem {
}

final class PluginItem implements ExternalItem {
    @Override
    public String render() {
        return "plugin";
    }
}

public class ExtensionPointDemo {
    public static void main(String[] args) {
        ReportItem first = new TextItem("core");
        ReportItem second = new PluginItem();

        System.out.println(first.render());
        System.out.println(second.render());
        System.out.println("plugin is ReportItem="
                + (second instanceof ReportItem));
        System.out.println("plugin directly implements="
                + PluginItem.class.getInterfaces()[0]
                        .getSimpleName());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 ExtensionPointDemo.java
java ExtensionPointDemo
~~~

**Stdout:**

~~~text
text:core
plugin
plugin is ReportItem=true
plugin directly implements=ExternalItem
~~~

`ReportItem` only permits two direct subtypes: TextItem and ExternalItem. PluginItem does not directly implement ReportItem; instead, it directly implements ExternalItem.

**Use case:** the sealed root still publicly declares that a value is built-in text or belongs to the external extension family. However, you can no longer assume **there are only two concrete runtime classes**.

## 14. When You Have a Tree of Expressions, Commands, or AST Nodes

Sealed is especially well suited to an **abstract syntax tree (AST)** or recursive data structure whose set of node kinds is defined within a small language:

~~~text
Expression (sealed)
├── NumberLiteral(value)
├── Addition(left, right)
└── Multiplication(left, right)
~~~

Each node has different components; all of them are Expressions. Nodes can in turn contain other Expressions, forming a multi-level tree.

The set of direct permitted node types can be relatively stable, controlled by the grammar. The sealed + record form helps parser, evaluator, pretty printer, and unit test code clearly distinguish node kinds.

If the grammar is freely extended by plugin authors, a completely closed sealed root can cause difficulties. In that case, consider an extension AST API or defining an additional non-sealed extension node family.

## 15. Program 5 — AST Using Sealed and Records

File **`ExpressionTreeDemo.java`**:

~~~java
sealed interface Expr permits Num, Add, Multiply {
    int eval();
}

record Num(int value) implements Expr {
    @Override
    public int eval() {
        return value;
    }
}

record Add(Expr left, Expr right) implements Expr {
    @Override
    public int eval() {
        return left.eval() + right.eval();
    }
}

record Multiply(Expr left, Expr right) implements Expr {
    @Override
    public int eval() {
        return left.eval() * right.eval();
    }
}

public class ExpressionTreeDemo {
    public static void main(String[] args) {
        Expr tree = new Multiply(
                new Add(new Num(2), new Num(3)),
                new Num(4));

        System.out.println("value=" + tree.eval());
        System.out.println("is Multiply="
                + (tree instanceof Multiply));
        System.out.println("left is Add="
                + (((Multiply) tree).left() instanceof Add));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ExpressionTreeDemo.java
java ExpressionTreeDemo
~~~

**Stdout:**

~~~text
value=20
is Multiply=true
left is Add=true
~~~

Sealed holds the direct node types, records describe the fields for each node, and `eval()` uses dynamic dispatch. No `switch` on the runtime type is needed for evaluation because the behavior is placed directly in each variant.

Because records have component references `left`/`right`, separate validation is needed if the AST does not accept null. The program assumes the input tree is constructed validly; sealed **does not automatically guard against null children or reference cycles** in a model with mutable references.

## 16. Sealed Interface + Record Is a Well-Suited Pair for Value Variants

**A sealed interface** specifies “which kinds of values are recognized”; **a record** specifies “which components each kind carries.”

Example:

~~~java
sealed interface ValidationResult permits Valid, Invalid {
}

record Valid(String normalizedValue)
        implements ValidationResult {
}

record Invalid(String message)
        implements ValidationResult {
}
~~~

Records are implicitly final, so there is no need to declare `final record` (that syntax is not meant for records either). They cannot extend a custom sealed class, because a record **always extends `java.lang.Record`**. Therefore, pairing with a **sealed interface** is usually the most flexible option.

Records automatically provide a canonical constructor, accessors, equality, hash, and toString based on components. However, you still have to validate null/ranges, and you can use a compact constructor to normalize/copy inputs.

**Do not equate records with deep immutability:** if a record holds `List<MutableItem>`, reachable objects inside can still be mutated unless you design defensive copying.

## 17. Program 6 — Lookup Results with or Without Data

File **`LookupResultDemo.java`**:

~~~java
sealed interface LookupResult permits Found, NotFound, LookupError {
}

record Found(String value) implements LookupResult {
    Found {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value");
        }
    }
}

record NotFound() implements LookupResult {
}

record LookupError(String reason) implements LookupResult {
}

public class LookupResultDemo {
    static String text(LookupResult result) {
        if (result instanceof Found found) {
            return "found:" + found.value();
        }
        if (result instanceof NotFound) {
            return "missing";
        }
        if (result instanceof LookupError error) {
            return "error:" + error.reason();
        }
        throw new IllegalArgumentException("unsupported");
    }

    public static void main(String[] args) {
        System.out.println(text(new Found("Java")));
        System.out.println(text(new NotFound()));
        System.out.println(text(new LookupError("timeout")));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 LookupResultDemo.java
java LookupResultDemo
~~~

**Stdout:**

~~~text
found:Java
missing
error:timeout
~~~

`NotFound()` is a **record with no components**, valid when the type only needs to signal a variant. `LookupError` carries an error reason; `Found` carries the found data. This design avoids having `null` represent both “not found” and “error” at the same time.

If an API returns `Optional<T>` just to describe the presence or absence of a value and there are no separate domain error cases, Optional can be even simpler than a sealed hierarchy.

## 18. When to Use `Optional<T>` Instead of Sealed

`Optional<T>` describes a result that **has a value or has no value**, not a detailed error classification system.

- If looking up a key in a cache and not finding it is a normal situation, `Optional<Value>` may be reasonable.
- If you need to distinguish NotFound, PermissionDenied, TemporarilyUnavailable, and Found(payload), a sealed result hierarchy expresses multiple outcomes more accurately.
- If a method can throw an unexpected exception, it is not necessarily required to put every checked/unchecked exception into sealed results; it also depends on API conventions.
- If existing code uses `null` for a purpose different from “absence,” you need to align the semantics before changing the design.

Choose based on the **number of meaningful outcomes**, not on formal complexity. `Optional` is not a full replacement for every result type, and sealed is not mandatory for a simple lookup.

## 19. When a Variant Needs Shared Logic or State from a Superclass

A sealed interface pairs well with records, but sometimes variants need a **base constructor**, shared fields, protected helpers, or a shared implementation. In that case, a `sealed abstract class` is a viable choice:

~~~java
abstract sealed class Shape permits Square, Rectangle {
    private final String label;

    Shape(String label) {
        this.label = label;
    }

    final String label() {
        return label;
    }

    abstract int areaUnits();
}
~~~

The two subclasses `Square` and `Rectangle` will have to extend Shape and choose `final`/`sealed`/`non-sealed`. By contrast, records **cannot** extend Shape because a record has Record as its fixed superclass.

If shared state is just data that each variant can store separately in record components, a sealed interface may introduce less inheritance coupling. Do not build an abstract superclass just to save two lines of field declarations if doing so complicates the domain.

## 20. Program 7 — Sealed Abstract Class with Shared Constructor

File **`SealedShapeDemo.java`**:

~~~java
abstract sealed class Shape permits Square, Rectangle {
    private final String label;

    Shape(String label) {
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("label");
        }
        this.label = label;
    }

    final String label() {
        return label;
    }

    abstract int areaUnits();
}

final class Square extends Shape {
    private final int side;

    Square(int side) {
        super("square");
        if (side <= 0) {
            throw new IllegalArgumentException("side");
        }
        this.side = side;
    }

    @Override
    int areaUnits() {
        return side * side;
    }
}

final class Rectangle extends Shape {
    private final int width;
    private final int height;

    Rectangle(int width, int height) {
        super("rectangle");
        if (width <= 0 || height <= 0) {
            throw new IllegalArgumentException("dimensions");
        }
        this.width = width;
        this.height = height;
    }

    @Override
    int areaUnits() {
        return width * height;
    }
}

public class SealedShapeDemo {
    public static void main(String[] args) {
        Shape a = new Square(3);
        Shape b = new Rectangle(2, 4);

        System.out.println(a.label() + "=" + a.areaUnits());
        System.out.println(b.label() + "=" + b.areaUnits());
    }
}
~~~

Command:

~~~bash
javac -encoding UTF-8 SealedShapeDemo.java
java SealedShapeDemo
~~~

**Stdout:**

~~~text
square=9
rectangle=8
~~~

The base class holds the invariant for the label; each subclass has its own data and validation. Sealed controls the set of direct subclasses, while `abstract` forbids creating a Shape object that does not belong to a specific variant.

**Note:** a `sealed class` is **not abstract by default**. If the base is concrete and its constructor is accessible, `new Base()` can be valid. Add abstract when you genuinely need to forbid direct instances of the general concept.

## 21. Workflow States: Sealed Works Well When States Carry Their Own Data

A simple job status such as `CREATED`, `RUNNING`, `DONE` may only need an enum. However, if:

- `CartOpen` carries a list of items;
- `AwaitingPayment` carries a request ID and an amount;
- `Completed` carries an invoice ID;
- `Cancelled` carries a reason;

then sealed variants help ensure each state requires its corresponding payload.

One benefit is **no longer “reading the wrong field”**: `Completed` has `receiptId()`, whereas `CartOpen` does not have that method. The Java compiler requires checking or casting when accessing information specific to each variant.

However, sealed **does not manage transitions by itself**. You still have to design appropriate state-transition methods and validate legal transitions. A caller can still construct `Completed` directly if the constructor is exposed; if the domain demands strict lifecycle protection, you must control factories/services, visibility, and authentication separately.

## 22. Program 8 — State Variants with Explicit Transitions

File **`CheckoutStateDemo.java`**:

~~~java
sealed interface CheckoutState
        permits CartOpen, AwaitingPayment, Completed, Cancelled {
}

record CartOpen(int items) implements CheckoutState {
    CartOpen {
        if (items < 0) {
            throw new IllegalArgumentException("items");
        }
    }
}

record AwaitingPayment(String orderId)
        implements CheckoutState {
}

record Completed(String receiptId) implements CheckoutState {
}

record Cancelled(String reason) implements CheckoutState {
}

public class CheckoutStateDemo {
    static CheckoutState requestPayment(CheckoutState current) {
        if (current instanceof CartOpen cart && cart.items() > 0) {
            return new AwaitingPayment("ORD-1");
        }
        throw new IllegalStateException("cannot request payment");
    }

    static CheckoutState confirm(CheckoutState current) {
        if (current instanceof AwaitingPayment) {
            return new Completed("R-1");
        }
        throw new IllegalStateException("cannot confirm");
    }

    public static void main(String[] args) {
        CheckoutState current = new CartOpen(2);
        System.out.println("start=" + current);

        current = requestPayment(current);
        System.out.println("pending=" + current);

        current = confirm(current);
        System.out.println("done=" + current);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CheckoutStateDemo.java
java CheckoutStateDemo
~~~

**Stdout:**

~~~text
start=CartOpen[items=2]
pending=AwaitingPayment[orderId=ORD-1]
done=Completed[receiptId=R-1]
~~~

Transition methods only accept meaningful runtime variants. Sealed makes the kinds of states explicit, but deciding **who is allowed to transition** and **when to transition** still belongs to business logic. In production code, identifiers should not be hardcoded as in the example; transaction data and concurrency must be managed appropriately for the domain.

## 23. `final`, `sealed`, `non-sealed` Determine the Closure Level of the Tree

A direct permitted subtype must specify its extension direction:

| Permitted subtype | Result |
| --- | --- |
| `final class Leaf extends Parent` | Disallows subclasses of Leaf |
| `record Leaf(...) implements Parent` | Record is implicitly final |
| `sealed class Branch extends Parent permits ...` | Continues controlling direct children of Branch |
| `sealed interface Branch extends Parent permits ...` | Continues controlling direct subtypes of Branch |
| `non-sealed class Branch extends Parent` | Reopens subclassing under Branch |
| `non-sealed interface Branch extends Parent` | Reopens extension under Branch |

An ordinary direct permitted child **cannot** simply write `class Child extends SealedParent` and omit all three choices. The compiler requires an explicit extension decision.

`non-sealed` is also **not** a modifier applicable to an arbitrary class; it is only valid in relation to a corresponding sealed direct supertype.

Only when all concrete leaves are final and all intermediate branches remain sealed is the hierarchy truly a **closed collection of concrete variants**. If a non-sealed branch appears, only the parent's list of direct children remains closed, while descendants under that branch can be open.

## 24. Multi-Level Trees and Grouped Variants

A domain may need to be divided into families:

~~~text
Event (sealed)
├── UserEvent (sealed)
│   ├── UserCreated (record)
│   └── UserDeleted (record)
└── SystemEvent (sealed)
    ├── Started (record)
    └── Stopped (record)
~~~

If `Event` directly permits `UserEvent` and `SystemEvent`, it **does not need** to permit each leaf. Each subtype `UserCreated` must directly implement `UserEvent` (and thus indirectly be an Event) as declared in the code.

This is a good way to organize when the grouping reflects real concepts; however, it also increases the number of levels in the model. With three simple variants, a sealed interface directly permitting three records is usually easier to read.

**Principle:** do not build multiple layers just to “lock everything down.” Each layer should serve a useful purpose for the API, behavior, or domain structure.

## 25. Program 9 — Two-Level Hierarchy

File **`EventFamiliesDemo.java`**:

~~~java
sealed interface Event permits UserEvent, SystemEvent {
}

sealed interface UserEvent extends Event
        permits UserCreated, UserDeleted {
}

sealed interface SystemEvent extends Event
        permits Started, Stopped {
}

record UserCreated(String id) implements UserEvent {
}

record UserDeleted(String id) implements UserEvent {
}

record Started() implements SystemEvent {
}

record Stopped() implements SystemEvent {
}

public class EventFamiliesDemo {
    static String family(Event event) {
        if (event instanceof UserEvent) {
            return "user";
        }
        if (event instanceof SystemEvent) {
            return "system";
        }
        throw new IllegalArgumentException("unknown");
    }

    public static void main(String[] args) {
        Event a = new UserCreated("U1");
        Event b = new Started();

        System.out.println("a=" + family(a));
        System.out.println("b=" + family(b));
        System.out.println("a UserEvent="
                + (a instanceof UserEvent));
        System.out.println("b SystemEvent="
                + (b instanceof SystemEvent));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 EventFamiliesDemo.java
java EventFamiliesDemo
~~~

**Stdout:**

~~~text
a=user
b=system
a UserEvent=true
b SystemEvent=true
~~~

`Event` only permits two direct subinterfaces; each subinterface restricts its own leaf records. Java 17 allows `instanceof` against this interface hierarchy without enabling preview features.

A multi-level model is appropriate when consumers frequently need to ask “user-related or system-related” before handling the specific subtype.

## 26. Placement Rules: Named Modules and Unnamed Modules

A sealed hierarchy is constrained by Java's boundaries:

- In a **named module**, all direct permitted subclasses/subinterfaces of a sealed type must reside in the **same named module**. They may be in different packages within the module if Java accessibility and dependencies allow.
- In an **unnamed module**, the permitted direct subtypes must reside in the **same package**.
- If `permits` is omitted, the compiler can only infer permitted direct subtypes from the **same compilation unit** under JLS conditions.
- Declaring `permits` explicitly is usually easier to maintain when the type hierarchy spans multiple files.

All runnable examples here place declarations in a single file with no package to keep `javac` simple. This is not a guideline saying every project must organize a hierarchy in a single file.

Sealed **does not allow a plugin in another module to directly implement the root** merely because the root is public. If the API needs external extension, consider an open interface or a permitted non-sealed extension point.

## 27. API Evolution: Adding a Variant Is a Significant Change

Suppose you initially have `sealed interface Outcome permits Success, Failure`. When you add a `Pending` to permits:

- Callers written under the assumption “only Success or Failure” must be reviewed.
- Serializers/JSON polymorphic mappings may need to understand the new discriminator.
- Policies, metrics, logs, or UIs may need to handle Pending.
- Unit tests and integration tests must be updated.
- If clients use Java 17 and `if instanceof` chains, the compiler does not automatically catch all call sites that omit a branch.
- For an API used across modules/libraries, binary/source compatibility and the rebuild process must be considered.

If the domain genuinely has a centrally governed set of variants, forcing such an explicit change is a **benefit of sealed**. If new variants appear continuously as created by external users, sealed instead imposes unnecessary overhead.

**Do not use `default` or an `else` branch just to “swallow” every unfamiliar variant** if the system must handle each variant accurately. When a new kind is not yet supported, failing fast can be safer than a business-incorrect default result.

## 28. Handling Variants in Java 17: Polymorphism First, Type Tests When Needed

There are two basic styles:

**Polymorphism:** place a common method on the sealed interface and implement it in each variant.

~~~java
sealed interface Message permits PlainText, ImportantText {
    String display();
}
~~~

Each variant has `display()`, and callers simply call `message.display()`. Benefit: if a new permitted type is added, that class must implement the interface's abstract methods in order to compile; this reduces type-dispatch in consumers.

**Type tests:** callers need context-specific logic, for example when the UI and auditing interpret variants differently:

~~~java
if (message instanceof PlainText text) {
    // handle PlainText payload in this context
}
~~~

This is a valid snippet given a variable message of type Message and a matching record PlainText.

You should not force every behavior onto variant types if it depends on application-layer data or services: sometimes a visitor or an external service renderer is better. Conversely, there is no need to write 15 identical instanceof chains if a polymorphic method already expresses the meaning well.

## 29. Program 10 — Polymorphism Eliminates Type-Switching

File **`SealedBehaviorDemo.java`**:

~~~java
sealed interface Message permits PlainText, ImportantText {
    String display();
}

record PlainText(String value) implements Message {
    @Override
    public String display() {
        return value;
    }
}

record ImportantText(String value) implements Message {
    @Override
    public String display() {
        return "IMPORTANT:" + value;
    }
}

public class SealedBehaviorDemo {
    public static void main(String[] args) {
        Message a = new PlainText("hello");
        Message b = new ImportantText("save");

        System.out.println(a.display());
        System.out.println(b.display());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SealedBehaviorDemo.java
java SealedBehaviorDemo
~~~

**Stdout:**

~~~text
hello
IMPORTANT:save
~~~

Both implementations are implicitly final records. The caller does not need to know which runtime variant the Message variable holds; dynamic dispatch selects the appropriate method.

This is a good solution when the method is an **intrinsic behavior of the variant**, with no dependency on external resources.

## 30. Pattern Switch in Java 17: Distinguishing Stable and Preview Features

Java 17 already has **pattern matching for `instanceof`** as a standard feature:

~~~java
if (result instanceof Approved approved) {
    System.out.println(approved.receiptId());
}
~~~

This snippet is valid inside a method with a variable result of type PaymentResult from the example.

However, syntax like:

~~~java
// NOT stable non-preview code in Java 17:
// return switch (result) {
//     case Approved a -> a.receiptId();
//     case Declined d -> d.reason();
// };
~~~

cannot be used as a standard non-preview feature of Java 17. Pattern matching for switch went through preview releases and became an official feature in **Java 21 (JEP 441)**.

**Therefore:**
- When learning/writing default Java 17 code: use `if instanceof`, polymorphism, or a visitor.
- Do not promote `switch` on a sealed interface as standard Java 17 syntax.
- If a project uses a release that supports stable pattern switch, you can leverage exhaustiveness on sealed hierarchies according to that release's rules.
- Do not assume that the Java 17 compiler automatically checks exhaustiveness for any `if instanceof` chain.

Being cautious about versions is part of long-term library design, especially when the build target is still Java 17.

## 31. With Many Independent Operations, Consider a Visitor

If the variants are stable while many new operations keep appearing (rendering, serialization, metrics, validation...), a **visitor** can centralize overloads by variant without placing every business method into the records.

Conceptual interface example:

~~~java
interface OutcomeVisitor<R> {
    R onApproved(Approved value);
    R onDeclined(Declined value);
}
~~~

The Approved/Declined types are assumed to be the records from the first example. An `accept` method implemented by the interface/variants can invoke the right overload, helping avoid duplicate instanceof chains in consumers.

Trade-offs:
- Adding a new **operation** is easy via a new visitor implementation.
- Adding a new **variant** requires updating the visitor interfaces/implementations.
- With 2 variants and a single operation, a visitor can be cumbersome.
- With 20 variants and many separate operations, a visitor can help keep code paths clearly organized.

This is an API design choice, not a requirement of `sealed`.

## 32. Program 11 — Visitor for Sealed Value Variants

File **`SealedVisitorDemo.java`**:

~~~java
interface ResultVisitor<R> {
    R success(Success value);
    R failure(Failure value);
}

sealed interface Result permits Success, Failure {
    <R> R accept(ResultVisitor<R> visitor);
}

record Success(String text) implements Result {
    @Override
    public <R> R accept(ResultVisitor<R> visitor) {
        return visitor.success(this);
    }
}

record Failure(String message) implements Result {
    @Override
    public <R> R accept(ResultVisitor<R> visitor) {
        return visitor.failure(this);
    }
}

public class SealedVisitorDemo {
    public static void main(String[] args) {
        ResultVisitor<String> renderer =
                new ResultVisitor<>() {
                    @Override
                    public String success(Success value) {
                        return "OK:" + value.text();
                    }

                    @Override
                    public String failure(Failure value) {
                        return "NO:" + value.message();
                    }
                };

        Result a = new Success("saved");
        Result b = new Failure("denied");
        System.out.println(a.accept(renderer));
        System.out.println(b.accept(renderer));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 SealedVisitorDemo.java
java SealedVisitorDemo
~~~

**Stdout:**

~~~text
OK:saved
NO:denied
~~~

The visitor defines two separate methods for the two variants; each record calls the corresponding method in `accept`. `Result` is a sealed interface, but **not a functional interface**, so you cannot directly assign a lambda to Result.

Note that the Java generic method `<R> R accept(...)` is valid in an interface and overridden by records; Java 17 needs no preview features.

## 33. Why Can't a Sealed Interface Be Used Directly as a Lambda Target?

A `sealed interface` with one abstract method **is not considered a functional interface** under JLS 17.

~~~java
sealed interface Operation permits NamedOperation {
    void execute();
}

final class NamedOperation implements Operation {
    @Override
    public void execute() {
        System.out.println("named");
    }
}
~~~

These declarations are valid. The snippet below **intentionally does not compile** if placed inside a method:

~~~java
// Operation op = () -> System.out.println("lambda");
~~~

Because Operation is sealed, a `lambda` is not a declared permitted direct implementing class. Java intentionally excludes sealed interfaces from functional interface target types.

If the application needs callbacks that callers can create freely, use a separate non-sealed `@FunctionalInterface` interface, such as `Runnable`, `Consumer<T>`, `Function<T,R>`. Only seal domain value types if the set of variants is genuinely controlled by the owner.

This point is a very practical **“when not to use sealed”** criterion.

## 34. Immutability and Data Contracts: Sealed Is Not Enough

`sealed` does not make variants immutable. Even `record` only guarantees final component fields, not deep freezing of the object graph:

~~~java
sealed interface CatalogResult permits Items, CatalogError {
}

record Items(java.util.List<String> values)
        implements CatalogResult {
}

record CatalogError(String reason)
        implements CatalogResult {
}
~~~

These are valid declarations. If Items receives a mutable `ArrayList<String>`, the caller can still modify the list through the original reference or `items.values()`.

If the API promises a value snapshot, copy it in the compact canonical constructor:

~~~java
record Items(java.util.List<String> values)
        implements CatalogResult {
    Items {
        values = java.util.List.copyOf(values);
    }
}
~~~

This is a **replacement version** for the Items declaration above; do not put both versions into the same compilation unit.

`List.copyOf` creates an unmodifiable structural snapshot, but does not deep-copy mutable elements. Therefore, sealed + record + copyOf only guarantees a level of immutability matching the **element types** and the **designed graph depth**.

## 35. Program 12 — Sealed with Record Snapshot

File **`SealedSnapshotDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

sealed interface CatalogResult permits Items, CatalogError {
}

record Items(List<String> values) implements CatalogResult {
    Items {
        values = List.copyOf(values);
    }
}

record CatalogError(String reason) implements CatalogResult {
}

public class SealedSnapshotDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("A");

        CatalogResult result = new Items(source);
        source.add("B");

        if (result instanceof Items items) {
            System.out.println("stored=" + items.values());
            try {
                items.values().add("C");
            } catch (UnsupportedOperationException ex) {
                System.out.println("unmodifiable=true");
            }
        }

        System.out.println("source=" + source);
    }
}
~~~

Command:

~~~bash
javac -encoding UTF-8 SealedSnapshotDemo.java
java SealedSnapshotDemo
~~~

**Stdout:**

~~~text
stored=[A]
unmodifiable=true
source=[A, B]
~~~

Sealed ensures the direct result kind is valid; record describes the payload; `List.copyOf` ensures a snapshot list structure. These are three **distinct** responsibilities working together and should not be conflated.

In this example, the elements are immutable Strings, so the Items record acts as a stable value snapshot for the graph under consideration.

## 36. Generic Results: Sealed Can Be Used with Type Parameters

An API that wants `Result<User>`, `Result<Order>`, `Result<String>` can use a generic sealed interface:

~~~java
sealed interface Result<T> permits Ok, Err {
}

record Ok<T>(T value) implements Result<T> {
}

record Err<T>(String message) implements Result<T> {
}
~~~

These declarations are valid in the same compilation unit. `Result<T>` preserves the type of the success payload; the error variant still carries a message.

It can be used as:

~~~java
Result<Integer> answer = new Ok<>(42);
Result<Integer> failure = new Err<>("missing");
~~~

This is a valid snippet inside a method. Variants sharing a generic contract help the API avoid returning `Object` and relying on uncontrolled casting.

**However**, a generic sealed hierarchy does not by itself replace exception management, null policy, or validation. You need to decide whether `Ok<>(null)` is allowed, whether the error string has sufficient structure, and how clients should handle it.

## 37. Program 13 — Generic Sealed Result

File **`GenericResultDemo.java`**:

~~~java
sealed interface Result<T> permits Ok, Err {
}

record Ok<T>(T value) implements Result<T> {
}

record Err<T>(String message) implements Result<T> {
}

public class GenericResultDemo {
    static <T> String describe(Result<T> result) {
        if (result instanceof Ok<?> ok) {
            return "ok:" + ok.value();
        }
        if (result instanceof Err<?> err) {
            return "err:" + err.message();
        }
        throw new IllegalArgumentException("unknown");
    }

    public static void main(String[] args) {
        Result<Integer> success = new Ok<>(42);
        Result<Integer> failure = new Err<>("missing");

        System.out.println(describe(success));
        System.out.println(describe(failure));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericResultDemo.java
java GenericResultDemo
~~~

**Stdout:**

~~~text
ok:42
err:missing
~~~

The generic parameter lets callers know that the success payload is of type Integer here. In Java 17, the pattern `instanceof Ok<?> ok` is valid because it does not test a concrete generic type argument that has been lost to type erasure at runtime.

## 38. Reflection: Observes Only Direct Permitted Types

Java 17 provides:

- `Class.isSealed()` to check whether a runtime class/interface is sealed.
- `Class.getPermittedSubclasses()` to read the **direct permitted classes/interfaces**, not all descendants.

For example, with:

~~~text
Result (sealed)
├── Success (final)
└── ExtensionResult (non-sealed)
    └── ThirdPartyResult
~~~

Reflection on Result returns Success and ExtensionResult; it **does not automatically list ThirdPartyResult**.

You should not use reflection to regularly branch business logic in a small model; using interface methods or `instanceof` is clearer. Reflection is more useful for tooling, diagnostics, and inspecting hierarchy structure.

The order returned by reflection should not be treated as business ranking; if printing the list in tests, sort it first so stdout is stable.

## 39. Program 14 — Inspecting the List of Direct Variants

File **`PermittedVariantsDemo.java`**:

~~~java
import java.util.Arrays;

sealed interface Action permits CreateAction, DeleteAction {
}

record CreateAction(String id) implements Action {
}

record DeleteAction(String id) implements Action {
}

public class PermittedVariantsDemo {
    public static void main(String[] args) {
        System.out.println("sealed=" + Action.class.isSealed());

        String[] names = Arrays.stream(
                    Action.class.getPermittedSubclasses())
                .map(Class::getSimpleName)
                .sorted()
                .toArray(String[]::new);

        System.out.println("permitted="
                + Arrays.toString(names));
        System.out.println("record final="
                + java.lang.reflect.Modifier.isFinal(
                        CreateAction.class.getModifiers()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 PermittedVariantsDemo.java
java PermittedVariantsDemo
~~~

**Stdout:**

~~~text
sealed=true
permitted=[CreateAction, DeleteAction]
record final=true
~~~

`CreateAction` and `DeleteAction` are both implicitly final records. Sorting makes the printed output independent of the order returned by the API. The code does not use reflection to classify a runtime Action instance; it only demonstrates metadata of the type hierarchy.

## 40. Sealed Is Neither Security Control Nor Data Validity

Things `sealed` **does not automatically guarantee**:

- That the caller is authorized to create or execute a value.
- That a request has been authenticated/authorized.
- That record components are non-null or have valid formats.
- That external JSON is safe against malicious data.
- That a List/Map/array inside a variant is deeply immutable.
- That methods have no side effects.
- That workflow states are only created through valid transitions.
- That all case handling in a Java 17 `if instanceof` chain is exhaustive.
- That integrated APIs are updated when a new variant is added.

For example, `record DeleteUser(String userId) implements Command` is a valid type, but it **does not prove** that the sender of the command has permission to delete an account. The service must still check permissions, validate data, and perform changes safely.

Do not use type names as a security boundary mechanism. Sealed is a **subtype constraint in the Java language**, not authentication or authorization.

## 41. Cases Where Sealed Should Not Be Applied

**A. Plugin systems:** a `Plugin` interface must be implemented by third parties in separate modules. A completely sealed root does not fit; consider an open interface or a non-sealed extension point.

**B. A single kind of value:** `record Coordinate(int x, int y)` does not need a sealed root if there are no alternatives.

**C. Simple constant sets:** `enum Priority { LOW, MEDIUM, HIGH }` is usually more direct and readable than three empty records.

**D. Only two states, “present or absent”:** `Optional<T>` may be sufficient if there is no error payload or additional policy.

**E. Polymorphic data with an intentionally open contract:** a library interface like `Comparator<T>` or `Runnable` serves caller flexibility. Sealing such callback types defeats the purpose.

**F. Types frequently generated outside the module by a code generator:** `permits` and module boundaries introduce maintenance costs without providing value if there is no genuinely closed set of variants.

**G. Systems that only need to group data by an enum field:** adding a complex sealed hierarchy may not provide any new invariants.

Sealed should be chosen for the **variant-set contract**, not because it is “newer than a regular class.”

## 42. Quick Selection Table

| Situation | Option worth considering | Reason |
| --- | --- | --- |
| Name-only status, no separate payload | Enum | Less boilerplate, works well with switch in Java 17 |
| Value with the same set of fields | Single record | No need for multiple runtime types |
| One of several outcomes, different payloads | Sealed interface + records | Types distinguish each payload accurately |
| AST with different nodes and recursive tree | Sealed interface + records/classes | Closed grammar, clear behavior |
| Shared base state/constructor logic | Abstract sealed class + final children | Shares implementation |
| Simple value presence/absence | `Optional<T>` | Lightweight API |
| External functional callback | Open functional interface | Allows lambdas and arbitrary implementations |
| Third-party plugins | Open interface or non-sealed branch | Intentionally supports extension |
| Domain hierarchy with some open families | Sealed root + non-sealed direct child | Closes direct families, opens one branch |
| Domain value with mutable components | Record + defensive copies/invariants | Sealed does not replace immutability |
| State machine model with complex transitions | Sealed variants + domain service | Explicit state kinds, separately controlled transitions |

The choices above are **design guidelines**, not absolute rules. The major distinction lies in value semantics and extension scope.

## 43. Step-by-Step Refactoring from a Model with `kind` and Many Fields

Suppose an old model exists:

~~~java
class ProcessResult {
    String kind;
    String value;
    String error;
}
~~~

Refactor in controlled steps:

1. **List the truly valid states:** success carries value; error carries error; is there a Pending state or not?
2. **Identify invalid states:** `kind="SUCCESS"` while value is null, or both value and error exist together.
3. **Name the variants:** `Processed`, `Failed`, `Pending` matching the domain, not `Type1`, `Type2`.
4. **Choose the root:** `sealed interface ProcessOutcome permits ...` if the owner controls the variants.
5. **Declare records:** each record has only its own payload and compact constructor validation if needed.
6. **Create an adapter at the old boundary:** parse kind once and convert the input into a typed variant.
7. **Migrate call sites:** use polymorphism or Java 17 instanceof patterns.
8. **Define the null/error policy:** do not use null to represent multiple different meanings.
9. **Maintain external API compatibility:** if the JSON discriminator was previously a string, decide on mapping/versioning.
10. **Test the migration:** all valid legacy states convert into the right variant; invalid states are rejected.
11. **Evaluate how often new kinds are added:** if variants are not closed, adjust the root/extension strategy before stabilizing the public API.

Do not change the entire system just for new syntax. Demonstrate that the refactor **eliminates invalid states and improves ownership boundaries**.

## 44. Practice Exercises

**Question 1.** A `Result` has two outcomes: Success(value) and Failure(reason). Why might a sealed interface + records be better than a class with `boolean success`, `String value`, `String reason`?

**Question 2.** An enum Color only has RED, GREEN, BLUE. Should it be converted by default into three record variants?

**Question 3.** If the SHIPPED state needs a separate tracking code per order, is an enum instance suitable as a place to store a mutable tracking code?

**Question 4.** Does `sealed` control direct children or all descendants?

**Question 5.** If a direct child declares `non-sealed`, does a grandchild class need to appear in the root's `permits`?

**Question 6.** If a model needs to close **all concrete variants**, what risk does a non-sealed branch pose?

**Question 7.** Why does a record usually implement a sealed interface rather than extend a sealed class?

**Question 8.** Must a permitted record explicitly add `final`?

**Question 9.** In what situation is a `sealed abstract class` more suitable than a sealed interface?

**Question 10.** For a plugin API where third parties must directly implement the interface in another module, is a completely sealed root suitable?

**Question 11.** In Java 17, does using `instanceof Success success` require preview features?

**Question 12.** In non-preview Java 17, can you pattern-switch directly over all record variants of a sealed interface like in Java 21?

**Question 13.** Is an `if/else instanceof` chain over sealed value types in Java 17 automatically checked for exhaustiveness by the compiler?

**Question 14.** If a sealed interface has only one abstract method, can a lambda be assigned to it directly?

**Question 15.** When might using a polymorphic method `value.display()` be better than many instanceof branches?

**Question 16.** How does a visitor help organize code when many different operations must be performed on the same set of variants?

**Question 17.** Does an `Items(List<String>)` record automatically make the List deeply immutable?

**Question 18.** Does `List.copyOf` in a compact constructor deep-copy all mutable elements?

**Question 19.** Does sealed automatically validate null components of a record?

**Question 20.** Does sealed automatically guarantee valid transitions from CartOpen to Completed?

**Question 21.** What parts need to be reviewed when adding Pending to an already public sealed Result?

**Question 22.** If variants are in an unnamed module, must direct permitted subtypes be in the same package or just in the same project?

**Question 23.** If in a named module, can a permitted direct subtype be in a different package within the same module?

**Question 24.** If `permits` is omitted, does Java automatically search the entire repository for all subclasses?

**Question 25.** Does `Class.getPermittedSubclasses()` list all indirect descendants under a non-sealed branch?

**Question 26.** If you only need presence/absence of a value, should you consider Optional before a sealed hierarchy?

**Question 27.** Does sealed replace authorization in a DeleteUser method?

**Question 28.** State three questions to answer before adding sealed to a domain model.

### Answers with Explanations

1. Each variant carries only its corresponding payload, reducing invalid state combinations caused by inapplicable fields.
2. No; an enum is more appropriate for a set of constant names that do not need different payloads.
3. No; an enum constant is a shared object, so mutating a single order's data there is bad design. A record variant containing the tracking code can be used instead.
4. Direct permitted subtypes of **that sealed node itself**.
5. No, because the grandchild directly extends/implements the non-sealed child.
6. That branch allows new descendants, so the set of all concrete variants is no longer closed.
7. A record has `java.lang.Record` as its fixed superclass; it can implement an interface.
8. No; records are implicitly final.
9. When variants need to inherit state, constructors, or shared implementation from a superclass.
10. Usually no; choose an open interface or design a non-sealed extension point.
11. No. Pattern matching for instanceof is a standard feature in Java 17.
12. No, pattern matching for switch only became stable in Java 21; Java 17 has a different preview version, not enabled by default.
13. No; tests, a visitor, or an explicit fallback policy are needed.
14. No; a sealed interface is not treated as a functional interface.
15. When an intrinsic behavior of the variant is invoked uniformly and the caller does not need to distinguish types.
16. Visitor methods distinguish variants so a new processing operation can be added without scattering instanceof checks everywhere.
17. No; record fields are final, but a mutable List can still be modified via aliases or the accessor.
18. No; it only snapshots the list structure and references to elements.
19. No; separate constructor validation is required.
20. No; business service, factory, or state-transition logic must still check it.
21. Consumers, serializers, versioning, UI, rules, tests, null/fallback policy, and docs.
22. Same package according to unnamed module rules.
23. Yes, if in the same named module and accessibility is valid.
24. No; they are only inferred from the same compilation unit when the rules are met.
25. No; only direct permitted types of the sealed root.
26. Yes; Optional<T> can be simpler if it only means present/absent.
27. No; authorization must be based on user identity and actual permission policies.
28. Is the set of variants genuinely closed? Do the payloads of each variant differ? Does the API need external extension?

## 45. Design Review Checklist

- [ ] Are the kinds of values genuinely different **domain variants**?
- [ ] Is the set of direct variants known and governed by the same package/module?
- [ ] Does each variant have its own fields/invariants sufficient to justify having a type?
- [ ] If they are only named constants, has an enum been considered?
- [ ] If there is only a single data shape, has a record been considered?
- [ ] If it is only present/absent, has Optional<T> been considered?
- [ ] Is the root a sealed class or sealed interface appropriate for the inheritance needs?
- [ ] Does `permits` contain the exact direct implementing/extending types?
- [ ] Do all permitted children have the appropriate final/sealed/non-sealed status?
- [ ] Is a non-sealed branch avoided if the model must close all concrete variants?
- [ ] If there is a non-sealed branch, is it explicitly exposed as an extension point?
- [ ] Do record variants avoid trying to extend a superclass other than `Record`?
- [ ] Is null/range/format validation present in constructors when the domain requires it?
- [ ] Is defensive copying applied to mutable record components when exposing a value snapshot?
- [ ] Are polymorphism/visitor chosen instead of duplicating instanceof chains where appropriate?
- [ ] In Java 17, is Java 21 pattern switch avoided as non-preview code?
- [ ] Are null, unsupported variants, and fallback behavior tested?
- [ ] Is the set of variants treated as an API contract when adding a new variant?
- [ ] Are Java sealed module/package restrictions checked?
- [ ] Is confusing security/permissions with type hierarchy restrictions avoided?
- [ ] Are clear serialization formats and versioning chosen for external messages?
- [ ] Do test programs have deterministic stdout and behavior?
- [ ] Do variant names accurately describe domain concepts rather than just TypeA/TypeB?
- [ ] Does using sealed reduce invalid states instead of increasing boilerplate?

## 46. Official Java 17 Documentation

- [JLS Java SE 17 §8.1.1.2 — `sealed`, `non-sealed`, and `final`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2): class modifier options.
- [JLS Java SE 17 §8.1.6 — Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6): the `permits` list of a sealed class.
- [JLS Java SE 17 §9.1.1.4 — `sealed` and `non-sealed` interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): options in interface hierarchies.
- [JLS Java SE 17 §9.1.4 — Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4): which types a sealed interface directly controls.
- [JLS Java SE 17 §9.8 — Functional Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.8): a sealed interface is not a functional interface.
- [JLS Java SE 17 §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): records and record components.
- [JLS Java SE 17 §15.20.2 — `instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): type tests and pattern variables.
- [Java SE 17 API — `Class.isSealed`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSealed()): reflection check for sealed.
- [Java SE 17 API — `Class.getPermittedSubclasses`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()): reflection reading of direct types.
- [Java SE 17 API — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): unmodifiable snapshot of list structure.
- [Java SE 17 API — `Optional`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html): cases where a value is present or absent.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): design motivation, closed hierarchies, and subtype control.
- [JEP 395 — Records](https://openjdk.org/jeps/395): record payload variants.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): finalized in Java 21, not stable non-preview syntax in Java 17.

## 47. Summary: Choose Sealed for a Domain Contract That Genuinely Needs Closure

**Sealed is especially suitable when a value can belong to one of several centrally governed kinds, and each kind has its own structure or meaning.** Combining **sealed interface + record** is often effective for results, commands, states, events, and AST nodes: sealed specifies *which kinds are allowed*, while record specifies *what data each kind holds*.

However, `sealed` **does not replace** an enum when there are only named constants, Optional when there is only absent/present, an open interface when plugins are needed, or constructor validation when invariants are needed. `sealed` restricts **direct subtypes**, and does not automatically prevent descendants through a non-sealed branch. It also does not automatically provide exhaustive `if instanceof` in Java 17 and is not a security mechanism.

Before applying it, ask: **(1) is the set of variants genuinely closed and under the module's control; (2) do the payload/behavior of each variant differ enough to warrant a separate type; (3) do we want and have the capacity to maintain the variant contract as the API evolves?** When all three answers fit, sealed helps the type system protect the design, makes code easier to understand, and reduces malformed data states.
