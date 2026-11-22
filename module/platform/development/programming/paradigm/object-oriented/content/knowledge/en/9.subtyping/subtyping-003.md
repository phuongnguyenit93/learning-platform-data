# Nominal and structural type compatibility in Java OOP

When a method accepts a parameter of type `MessageSender`, which objects can be passed to it? Is having a method named `send(...)` with the right parameters sufficient, or must the object's class **declare a relationship** with `MessageSender`?

This is the difference between **nominal typing** (compatibility based on type identity and declared relationships) and **structural typing** (compatibility based on structure). Java uses **nominal subtyping** for relationships among classes and interfaces: for one type to be considered a subtype of another interface/class, it must have a declared implementation or inheritance relationship in the type hierarchy. Two classes that happen to offer the same methods are **not automatically** compatible.

## 1. Two ways to determine type compatibility

**Nominal typing:** Java examines **type identity and declared inheritance/implementation relationships**. For example, `EmailSender implements MessageSender`, so `EmailSender` is a subtype of `MessageSender`.

**Structural typing:** in a type system that supports it, a value can be accepted if it provides **the required set of members**, even without explicitly declaring `implements`. Structural checks depend on the language, including parameter types, return types, accessibility, and other rules.

| Criterion | Nominal | Structural |
| --- | --- | --- |
| Based on | Type identity and declared subtype relationships | The shape/members offered by the type |
| Two classes sharing the same methods | Not necessarily compatible | Potentially compatible if the structural contract is met |
| Relationship to contracts | Often explicit via `implements` or `extends` | May be determined implicitly during type checking |
| Language examples | Java class/interface relationships | TypeScript's mostly structural type system; interfaces in Go are implemented implicitly |
| Advantage | Explicit public contracts and intentional type declarations | Flexible use of existing types with suitable structure |
| Trade-off | Requires declarations/type coupling or adapters | Similar structure may hide different semantics |

**Note:** “type compatibility” broadly includes other rules, such as primitive conversions, boxing/unboxing, and generics. This lesson focuses on **subtype compatibility between classes and interfaces**; not every legal Java assignment results from inheritance.

## 2. Java does not accept matching method signatures alone

Consider this Java code:

~~~java
interface MessageSender {
    void send(String receiver, String content);
}

class EmailSender implements MessageSender {
    @Override
    public void send(String receiver, String content) {
        System.out.println("Email đến " + receiver + ": " + content);
    }
}

// Cùng public method, cùng tham số/kiểu trả về, nhưng KHÔNG implements.
class LegacySmsSdk {
    public void send(String receiver, String content) {
        System.out.println("SMS đến " + receiver + ": " + content);
    }
}
~~~

Both `EmailSender` and `LegacySmsSdk` have `public void send(String, String)`, but only `EmailSender` is recognized as **a subtype of `MessageSender`**:

~~~java
MessageSender sender = new EmailSender();  // Hợp lệ.

// LỖI BIÊN DỊCH:
// MessageSender sender2 = new LegacySmsSdk();
~~~

The reason is that `LegacySmsSdk` has no `implements MessageSender` relationship, either directly or inherited from a suitable supertype. Java does not compare the shapes of classes to infer implementation of an interface merely because similar methods exist.

~~~mermaid
classDiagram
    class MessageSender {
        <<interface>>
        +send(String,String) void
    }
    class EmailSender {
        +send(String,String) void
    }
    class LegacySmsSdk {
        +send(String,String) void
    }
    MessageSender <|.. EmailSender
~~~

The dashed line with a triangle represents `EmailSender implements MessageSender`. `LegacySmsSdk` stands alone despite having the same method signature. This visually distinguishes **“similar structure”** from **“an established subtype relationship.”**

## 3. Complete example: an adapter connecting classes from different type hierarchies

In real projects, a third-party SDK may already exist, and we cannot modify it to add `implements MessageSender`. Instead, write an **adapter** that implements the application's interface and delegates to the SDK.

Save the following as `NominalTypingDemo.java` and run it with **Java 11+**:

~~~java
import java.util.List;
import java.util.Objects;

public class NominalTypingDemo {

    interface MessageSender {
        void send(String receiver, String content);
    }

    static final class EmailSender implements MessageSender {
        @Override
        public void send(String receiver, String content) {
            System.out.println("EMAIL -> " + receiver + ": " + content);
        }
    }

    // Giả lập thư viện ngoài có method phù hợp, nhưng không implements.
    static final class LegacySmsSdk {
        public void send(String receiver, String content) {
            System.out.println("SMS -> " + receiver + ": " + content);
        }
    }

    // Cầu nối: công bố hợp đồng của ứng dụng, dùng lại SDK sẵn có.
    static final class SmsSenderAdapter implements MessageSender {
        private final LegacySmsSdk sdk;

        SmsSenderAdapter(LegacySmsSdk sdk) {
            this.sdk = Objects.requireNonNull(sdk, "sdk");
        }

        @Override
        public void send(String receiver, String content) {
            sdk.send(receiver, content);
        }
    }

    static final class NotificationService {
        void notifyCustomer(MessageSender sender,
                            String receiver, String content) {
            Objects.requireNonNull(sender, "sender");
            if (receiver == null || receiver.isBlank()
                    || content == null || content.isBlank()) {
                throw new IllegalArgumentException(
                        "Người nhận/nội dung phải hợp lệ");
            }
            sender.send(receiver, content);
        }
    }

    public static void main(String[] args) {
        MessageSender email = new EmailSender();
        LegacySmsSdk externalSdk = new LegacySmsSdk();
        MessageSender sms = new SmsSenderAdapter(externalSdk);

        NotificationService service = new NotificationService();

        service.notifyCustomer(email, "KH-01", "Đơn đã xác nhận");
        service.notifyCustomer(sms, "KH-02", "Đơn đang giao");

        List<MessageSender> channels = List.of(email, sms);
        for (MessageSender channel : channels) {
            channel.send("KH-03", "Khuyến mãi");
        }

        // KHÔNG BIÊN DỊCH, dù LegacySmsSdk có đúng method send:
        // MessageSender incompatible = externalSdk;
    }
}
~~~

Run:

~~~bash
javac NominalTypingDemo.java
java NominalTypingDemo
~~~

Output:

~~~text
EMAIL -> KH-01: Đơn đã xác nhận
SMS -> KH-02: Đơn đang giao
EMAIL -> KH-03: Khuyến mãi
SMS -> KH-03: Khuyến mãi
~~~

In this example:

1. `NotificationService` requires a **`MessageSender`** parameter, an application-defined contract.
2. `EmailSender` directly implements that contract.
3. `LegacySmsSdk` offers similar functionality but **is not a `MessageSender`** in Java's type system.
4. `SmsSenderAdapter` is an actual subtype of `MessageSender` and invokes `sdk.send(...)` to perform the operation.
5. Although `NotificationService` does not know the concrete receiving class, `send(...)` dispatches to the corresponding runtime implementation (**polymorphism**).

~~~mermaid
classDiagram
    class MessageSender {
        <<interface>>
        +send(String,String) void
    }
    class EmailSender
    class SmsSenderAdapter {
        -sdk LegacySmsSdk
        +send(String,String) void
    }
    class LegacySmsSdk {
        +send(String,String) void
    }
    class NotificationService {
        +notifyCustomer(MessageSender,String,String) void
    }

    MessageSender <|.. EmailSender
    MessageSender <|.. SmsSenderAdapter
    SmsSenderAdapter --> LegacySmsSdk : delegates
    NotificationService --> MessageSender : depends on
~~~

**The adapter does not turn `LegacySmsSdk` into a subtype.** It creates **an adapter object** with a valid subtype relationship and a reference to the SDK object. This avoids modifying an external library and keeps control over the meaning of the `MessageSender` contract at the application boundary.

## 4. How would structural typing treat this situation differently?

For comparison, here is an example in **TypeScript (not Java)**:

~~~typescript
type Sender = {
    send(receiver: string, content: string): void;
};

class LegacySmsSdk {
    send(receiver: string, content: string): void {
        console.log(receiver, content);
    }
}

const sender: Sender = new LegacySmsSdk(); // Hợp lệ theo cấu trúc
sender.send("KH-01", "Xin chào");
~~~

`LegacySmsSdk` does not need to declare `implements Sender` here because its instance type has the shape that TypeScript checks for `Sender`.

The corresponding Java code **would not** compile without a declared subtype relationship. This is a difference in **type-system rules**, not merely the absence of a decorative `implements` keyword.

### Similar structure does not guarantee similar meaning

Two classes can both have `void send(String, String)` while one method sends a notification and the other sends data to an audit system. Matching signatures **do not guarantee** identical semantics, failure contracts, security, parameter order, or side effects.

Nominal typing requires a class to intentionally accept a role through a declared relationship. Structural typing offers flexible integration but **still requires a clear semantic contract**. Neither type system can prove correct business behavior from method names and signatures alone.

## 5. How are Java subtypes determined?

Core cases:

~~~java
class Animal {
    void eat() {}
}

class Dog extends Animal {
    void bark() {}
}

interface RunnableTask {
    void run();
}

class ReportTask implements RunnableTask {
    @Override
    public void run() {}
}
~~~

| Assignment | Result | Reason |
| --- | --- | --- |
| `Animal animal = new Dog();` | Valid | `Dog extends Animal` |
| `RunnableTask task = new ReportTask();` | Valid | `ReportTask implements RunnableTask` |
| `Object obj = new Dog();` | Valid | Java classes inherit directly/indirectly from `Object` |
| `Dog dog = new Animal();` | Invalid | Not every `Animal` is a `Dog` |
| `RunnableTask task = new Dog();` | Invalid | `Dog` is not declared a subtype of `RunnableTask` |
| `Animal a = new ReportTask();` | Invalid | There is no subtype relationship between these classes |

**Subtyping is directional:** given `Dog extends Animal`, a `Dog` can widen to `Animal` (*upcast*) without an explicit cast. The reverse conversion is not automatically valid.

Relationships are transitive across levels:

~~~java
interface Identifiable {
    String id();
}

interface Named extends Identifiable {
    String name();
}

class Customer implements Named {
    @Override
    public String id() { return "C01"; }

    @Override
    public String name() { return "An"; }
}
~~~

~~~java
Named a = new Customer();
Identifiable b = new Customer(); // Hợp lệ qua Named extends Identifiable
~~~

`Customer` need not explicitly write `implements Identifiable` because it already declares `implements Named`, and `Named` extends `Identifiable`. **Nominal compatibility does not mean checking only for the exact text `implements X` in the current class declaration**; Java follows valid subtype relationships along class and interface hierarchies.

An implementation may also be inherited from a superclass when the subclass declares `implements`:

~~~java
interface Greeter {
    String greet();
}

class BaseGreeter {
    public String greet() {
        return "Xin chào";
    }
}

class GreeterAdapter extends BaseGreeter implements Greeter {
    // Không cần viết lại greet() vì đã kế thừa implementation public.
}
~~~

`GreeterAdapter` is a `Greeter` because it **declares `implements`**, even though it does not override `greet()` again.

## 6. Two interfaces with identical methods are still distinct types

~~~java
interface Storable {
    void save(String value);
}

interface Auditable {
    void save(String value);
}

class FileStore implements Storable {
    @Override
    public void save(String value) {
        System.out.println("Lưu: " + value);
    }
}
~~~

~~~java
Storable s = new FileStore(); // Đúng.

// Auditable a = new FileStore(); // Sai: không implements Auditable.
~~~

Although `Storable` and `Auditable` declare the same method, Java still treats them as **two independent type identities**. If a class genuinely fulfills both:

~~~java
class DualStore implements Storable, Auditable {
    @Override
    public void save(String value) {
        System.out.println(value);
    }
}
~~~

A single `save(String)` implementation can satisfy both interfaces because the signatures match, but relationships with **both interfaces are declared explicitly**.

The lesson is: **matching structure does not create a subtype relationship; once subtype relationships exist, one implementation may satisfy contracts with compatible signatures**.

## 7. Does Java have “structural typing” through lambdas and method references?

Java supports **functional interfaces**: interfaces with a single abstract method (SAM). Lambdas and method references can be converted to values of a **target functional interface type** when signatures and other rules match.

~~~java
@FunctionalInterface
interface TextFormatter {
    String format(String raw);
}

class PrefixFormatter {
    String prefix(String raw) {
        return "[INFO] " + raw;
    }
}
~~~

~~~java
PrefixFormatter legacy = new PrefixFormatter();

// LỖI: PrefixFormatter không implements TextFormatter.
// TextFormatter a = legacy;

// Hợp lệ: method reference được chuyển theo target type TextFormatter.
TextFormatter b = legacy::prefix;

System.out.println(b.format("Đã lưu")); // [INFO] Đã lưu
~~~

This resembles “having a method with the required shape,” but it **does not** make `PrefixFormatter` automatically a subtype of `TextFormatter`. Instead, Java creates/represents a value of the **target functional interface** whose behavior invokes the referenced method.

A lambda also requires a **target type**:

~~~java
TextFormatter upper = text -> text.toUpperCase();

System.out.println(upper.format("java")); // JAVA
~~~

A Java lambda does not have an independently assignable concrete class type in the way a `PrefixFormatter` instance does under structural typing. The compiler needs a matching target functional interface, such as when assigning a variable or passing an argument.

**Correct conclusion:** method references and lambdas use **compatible functional signatures** at conversion sites, while ordinary Java class/interface subtyping remains primarily **nominal**.

## 8. Distinguish subtyping from “being castable”

An explicit cast **does not create** a missing subtype relationship.

~~~java
interface MessageSender {
    void send(String receiver, String content);
}

class LegacySmsSdk {
    public void send(String receiver, String content) { }
}
~~~

The next line may be syntactically accepted by the compiler when casting through `Object`, but it fails at runtime:

~~~java
LegacySmsSdk legacy = new LegacySmsSdk();

// Biên dịch được vì ép qua Object, nhưng ném ClassCastException:
MessageSender sender = (MessageSender) (Object) legacy;
~~~

Do not use casts to bypass Java's nominal contract. An **adapter** is the proper solution when an existing class has a similar API that must be exposed through an application interface.

Conversely, a supertype reference actually holding a subclass object can be safely downcast after checking:

~~~java
Animal animal = new Dog();

if (animal instanceof Dog) {
    Dog dog = (Dog) animal;
    dog.bark();
}
~~~

`instanceof` tests **the object's actual type compatibility**, not whether it coincidentally offers a collection of method names.

## 9. Generics: element subtyping does not guarantee collection assignability

If `EmailSender implements MessageSender`, then:

~~~java
EmailSender email = new EmailSender();
MessageSender sender = email; // Đúng.
~~~

But this **does not imply**:

~~~java
List<EmailSender> emails = List.of(new EmailSender());

// LỖI: generic List<T> trong Java bất biến (invariant).
// List<MessageSender> senders = emails;
~~~

If that assignment were allowed, callers might think they can add `SmsSenderAdapter` to a `List<EmailSender>`, breaking type safety.

When a method **only reads a list of elements that are subtypes of `MessageSender`**, use a wildcard:

~~~java
static void announce(
        List<? extends MessageSender> senders, String message) {
    for (MessageSender sender : senders) {
        sender.send("KH-01", message);
    }
}
~~~

~~~java
List<EmailSender> emails = List.of(new EmailSender());
announce(emails, "Thông báo");
~~~

`? extends MessageSender` allows elements to be **read** as `MessageSender` but does not allow adding an arbitrary `MessageSender` (except `null` under Java's rules). This is how variance works in generics, **distinct from** nominal/structural relationships between `EmailSender` and `MessageSender` themselves.

To use `List` in the separate snippets of this section, include `import java.util.List;` and define the sample classes/interfaces in an appropriate scope.

## 10. Identical data shapes do not make two records the same type

In Java **17+**, two `record` declarations with identical component names/types remain **different nominal types**:

~~~java
record Point(int x, int y) {}
record Position(int x, int y) {}

Point point = new Point(3, 5);
Position position = new Position(3, 5);

// LỖI BIÊN DỊCH:
// Position p = point;

System.out.println(point.equals(position)); // false
~~~

`Point` and `Position` are different classes without an applicable subtype relationship. Although their data has the same structure, they may have **different domain meanings**, such as geometric coordinates versus map locations.

You can convert them **explicitly** when appropriate:

~~~java
Position p = new Position(point.x(), point.y());
~~~

That **creates a different object by mapping data**, rather than assigning a reference through subtyping. Make this conversion deliberately instead of automatically equating concepts that share fields.

## 11. Designing APIs around nominal contracts

A Java API is generally clearer when a parameter type expresses **the capability it requires** instead of demanding one concrete class or using reflection to inspect similarly named methods.

For example:

~~~java
interface Exporter {
    void export(String fileName);
}

class ReportService {
    private final Exporter exporter;

    ReportService(Exporter exporter) {
        this.exporter = exporter;
    }

    void createReport() {
        // Tạo dữ liệu báo cáo...
        exporter.export("report.csv");
    }
}
~~~

`ReportService` only needs to know that the supplied object **fulfills the `Exporter` contract**. An implementation may write CSV, export PDF, or call another service, provided its behavior matches. The nominal contract supports dependency injection and polymorphism.

If an external library has a similar method but does not implement `Exporter`, integration options include an **adapter** or a **method reference** (if the contract is a functional interface and the signature matches):

~~~java
// Ví dụ minh họa khi có một object legacy với phương thức
// void save(String fileName):
Exporter exporter = legacy::save;
~~~

`legacy` itself **does not become a subtype of `Exporter`**. The method-reference expression supplies a value implementing the target functional interface.

Avoid overusing reflection to invoke methods solely by their names/arguments where a known Java contract exists. Reflection can be useful for specialized frameworks or plugins, but bypasses many static checks, adds complexity, and increases the risk of runtime failures.

## 12. Common misconceptions

| Statement | True or false? | Explanation |
| --- | --- | --- |
| “Classes with identical public methods are assignable to each other” | **False** in ordinary Java | No nominal subtype relationship |
| “A class must directly declare `implements I` to be a subtype of I” | **False** | The relationship can be inherited through a parent class/interface |
| “A subclass can inherit an implementation that satisfies an interface” | **True** | When it declares/inherits a valid interface relationship and the inherited method qualifies |
| “A class implementing two interfaces with the same method must duplicate the method” | **False** | One compatible implementation can satisfy both |
| “Lambdas make all structurally similar objects into Java subtypes” | **False** | Lambdas/method references are converted to target functional interface types |
| “Casting turns a class without an interface implementation into that interface” | **False** | Runtime type checking still applies and may throw `ClassCastException` |
| “`List<Sub>` is a `List<Super>` when Sub extends Super” | **False** | Java generics are invariant by default |
| “Two records with the same fields are always the same type” | **False** | Records retain distinct nominal type identities |
| “Nominal compatibility merely requires class names with identical spelling” | **False** | It depends on type identity and relationships, not simple string comparisons |

## 13. Practice questions with answers

**Question 1.** What happens?

~~~java
interface Readable {
    String read();
}

class FileSource {
    public String read() {
        return "Dữ liệu";
    }
}

// Readable input = new FileSource();
~~~

**Answer:** The assignment fails to compile. `FileSource` has a method with the same signature but is not declared a subtype of `Readable`. You can use an adapter that `implements Readable` or the method reference `Readable input = new FileSource()::read;`, since `Readable` is a functional interface.

**Question 2.** If `class SecureFileSource extends FileSource implements Readable { }`, must it override `read()`?

**Answer:** No. `SecureFileSource` fulfills the nominal relationship through `implements Readable` and inherits a compatible `public read()` implementation from `FileSource`.

**Question 3.** Why is `MessageSender sender = new SmsSenderAdapter(sdk)` valid even though `sdk` does not implement `MessageSender`?

**Answer:** The **assigned object** is an instance of `SmsSenderAdapter`, whose class does `implements MessageSender`. The adapter holds `sdk` and delegates to it; it does not change `sdk`'s type identity.

**Question 4.** Given `interface A { void go(); }`, `interface B { void go(); }`, and `class X implements A { public void go(){} }`, can you assign `B b = new X();`?

**Answer:** No. The interfaces have identical shapes, but `X` has no subtype relationship to `B`. If `X` implements both, that relationship must be declared directly or through a suitable hierarchy.

**Question 5.** Why can you assign `Base x = new Derived();` but not `List<Base> list = new ArrayList<Derived>();`?

**Answer:** The first statement uses subclass-to-superclass assignability. The second is rejected because `List<Base>` and `List<Derived>` are not related through subtyping under Java's invariant generics. Use a wildcard suited to reading subtype elements.

**Question 6.** In TypeScript, an object with a compatible `send(receiver, content)` can be used as `Sender` without declaring `implements Sender`. What form of compatibility is this?

**Answer:** Structural (*structural*) compatibility, based on the provided members fulfilling a contract. This reasoning does not apply to ordinary Java classes/interfaces.

**Question 7.** If two systems use different `Customer` classes that both contain `id` and `name`, should they be directly cast/assigned for reuse?

**Answer:** No. The types may have different domain meanings and constraints. Map the data explicitly, use an adapter, or define a shared contract at the integration boundary as appropriate.

## Main ideas to remember

In Java, **subtype compatibility** depends on **type identity and valid `extends`/`implements` relationships**, not merely on two classes having the same methods or fields. Structural type systems can accept a value based on its members' shape without an explicit declared relationship; this is a different language design choice.

When encountering an *incompatible types* error, ask: **(1)** What is the expression's declared type? **(2)** Is there a nominal subtype relationship to the target type? **(3)** Is this a special Java conversion or an invariant generic type? **(4)** If the systems lack a common contract, should you create an adapter/conversion instead of casting? These answers often reveal the precise reason for the error and a clearer design.
