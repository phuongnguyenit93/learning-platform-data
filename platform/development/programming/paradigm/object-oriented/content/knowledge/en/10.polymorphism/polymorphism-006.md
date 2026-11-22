# Distinguishing Member Hiding from Overriding in Java

When a subclass declares a member with **the same name** as its parent, Java does not always perform **overriding**. Whether that member is a **field**, a **`static` method**, or an **instance method** determines which rule applies:

- **Field hiding (*field hiding*):** A subclass field shares a name with a superclass field. Access to `ref.field` primarily depends on **the reference expression's compile-time type**, not the object's runtime class.
- **Static method hiding (*static method hiding*):** A subclass declares a static method with a signature corresponding to a superclass static method. The call resolves by **the type known at compile time**, without the dynamic polymorphism of instance methods.
- **Method overriding (*method overriding*):** A subclass supplies a new implementation of an eligible **instance method** from its parent. For a call with a receiver object, Java selects an implementation at **runtime** based on the actual object type.

This distinction is especially important when reading:

~~~java
Parent ref = new Child();
~~~

`ref` has the declared type `Parent` but refers to a `Child` object. Fields, static methods, and instance methods **do not necessarily resolve using the same type**.

## 1. Quick Comparison

| Feature | Field Hiding | Static Method Hiding | Instance Method Overriding |
|---|---|---|---|
| Typical condition | Subclass declares a same-named field | Subclass declares a valid same-signature static method | Subclass declares a valid overriding instance method |
| Member selection | Reference expression's compile-time type | Call/class type selected at compile time | Actual receiver object type at runtime |
| Dynamic polymorphism? | **No** | **No** | **Yes** |
| Use `@Override`? | No | No; compiler error | Recommended |
| Is `super` useful? | `super.field` accesses the parent field | `super.method()` for static methods follows separate rules; prefer `Parent.method()` | `super.method()` invokes the superclass implementation |
| Do separate members exist? | Two same-named fields can coexist in superclass and subclass state | Two static methods are declared across the classes | Different implementations of the same method contract can exist |
| Recommendation | Avoid field hiding to prevent confusion | Call static methods using **class names** | Use it for contracted polymorphic behavior |

**Rule of thumb:** *fields and static methods depend on compile-time reference/class types; overridden instance methods depend on the runtime object.*

This is the core rule, but the compiler's call resolution also considers overloads, accessibility, and argument types. The following sections separate these mechanisms.

## 2. Complete Java Example: One Object, Three Member-Resolution Rules

Save everything to **`Demo.java`** and compile/run with Java 17 or later:

~~~java
public class Demo {
    public static void main(String[] args) {
        Parent parentView = new Child();
        Child childView = (Child) parentView;

        System.out.println("=== Field ===");
        System.out.println(parentView.label);
        System.out.println(childView.label);
        System.out.println(((Parent) childView).label);

        System.out.println("=== Static method ===");
        System.out.println(Parent.kind());
        System.out.println(Child.kind());

        // Hợp lệ về cú pháp, nhưng không nên gọi static qua instance:
        System.out.println(parentView.kind());
        System.out.println(childView.kind());

        System.out.println("=== Instance method ===");
        System.out.println(parentView.describe());
        System.out.println(childView.describe());

        System.out.println("=== Kết hợp với super ===");
        childView.inspect();
        System.out.println(parentView.report());
    }
}

class Parent {
    public String label = "Field của Parent";

    public static String kind() {
        return "Static của Parent";
    }

    public String describe() {
        return "Method của Parent";
    }

    public String report() {
        // describe() là instance method: dispatch theo object.
        return "Report: " + describe();
    }
}

class Child extends Parent {
    public String label = "Field của Child"; // Field hiding.

    public static String kind() {            // Static method hiding.
        return "Static của Child";
    }

    @Override
    public String describe() {               // Method overriding.
        return "Method của Child";
    }

    public void inspect() {
        System.out.println(this.label);
        System.out.println(super.label);
        System.out.println(this.describe());
        System.out.println(super.describe());
    }
}
~~~

Run:

~~~bash
javac Demo.java
java Demo
~~~

Output:

~~~text
=== Field ===
Field của Parent
Field của Child
Field của Parent
=== Static method ===
Static của Parent
Static của Child
Static của Parent
Static của Child
=== Instance method ===
Method của Child
Method của Child
=== Kết hợp với super ===
Field của Child
Field của Parent
Method của Child
Method của Parent
Report: Method của Child
~~~

### Analyzing Each Mechanism

**Field hiding:**

~~~java
Parent parentView = new Child();

System.out.println(parentView.label);          // Field của Parent
System.out.println(((Child) parentView).label); // Field của Child
~~~

Both expressions refer to **one `Child` object**, yet the field is selected by **the reference type** of each expression:

- `parentView` is declared `Parent` → reads `Parent.label`.
- `(Child) parentView` has type `Child` → reads `Child.label`.

In this case, casting **does not create another object or move field values**; it changes how the compiler views the expression.

**Static method hiding:**

~~~java
System.out.println(parentView.kind()); // Static của Parent
System.out.println(childView.kind());  // Static của Child
~~~

Both calls are permitted but misleadingly resemble polymorphic static calls. **Prefer writing `Parent.kind()` and `Child.kind()`** to show that the static methods belong to classes.

**Instance method overriding:**

~~~java
System.out.println(parentView.describe()); // Method của Child
~~~

The compiler confirms that `Parent` declares `describe()`, while the JVM chooses the actual object's `Child.describe()` implementation.

Notably, `Parent.report()` can also invoke `Child.describe()` when executed on a `Child` object: the parent-class method calls an **overridable instance method**, and dispatch still occurs at runtime.

## 3. Field Hiding: Same Name, Distinct Fields

When a subclass redeclares the same field name, think of a subclass object as holding state from both superclass and subclass:

~~~mermaid
flowchart TD
    R["parentView: Parent"] --> O["Object thực tế: Child"]
    S["childView: Child"] --> O
    O --> P["Phần Parent: label = Field của Parent"]
    O --> C["Phần Child: label = Field của Child"]
    R -.->|"parentView.label"| P
    S -.->|"childView.label"| C
~~~

This is a **logical** diagram, not a guarantee of physical memory layout or JVM optimization.

A modification example demonstrates **two independent fields**:

~~~java
class CounterBase {
    public int count = 1;
}

class CounterChild extends CounterBase {
    public int count = 10;
}

CounterChild obj = new CounterChild();
obj.count = 20;
((CounterBase) obj).count = 2;

System.out.println(obj.count);               // 20
System.out.println(((CounterBase) obj).count); // 2
~~~

The usage statements at the end belong inside an appropriate Java method. Assigning `obj.count = 20` **does not modify** `CounterBase.count`; assigning through a cast to `CounterBase` also leaves `CounterChild.count` unchanged.

This can cause bugs when parent-class invariants depend on its field while a child redeclares that name, causing different code to read inconsistent state.

### Do Not Use Public Fields for Polymorphism

A misleading design:

~~~java
class Configuration {
    public String environment = "default";
}

class ProductionConfiguration extends Configuration {
    public String environment = "production";
}
~~~

Consuming code:

~~~java
Configuration config = new ProductionConfiguration();
System.out.println(config.environment); // default
~~~

For results depending on the runtime object, use an **instance method**:

~~~java
class Configuration {
    public String environment() {
        return "default";
    }
}

class ProductionConfiguration extends Configuration {
    @Override
    public String environment() {
        return "production";
    }
}

Configuration config = new ProductionConfiguration();
System.out.println(config.environment()); // production
~~~

For important data, keep fields `private` and expose getters or intention-revealing operations. Overridden getters can provide contract-based polymorphism while classes maintain their invariants.

## 4. Static Method Hiding: Same Signature, No Dynamic Dispatch

In Java, static methods belong to **classes**, not to the per-instance state. A subclass may declare a matching static method to **hide** its superclass method under Java's rules.

~~~java
class Formatter {
    public static String format() {
        return "BASE";
    }
}

class JsonFormatter extends Formatter {
    public static String format() {
        return "JSON";
    }
}
~~~

Usage:

~~~java
Formatter base = new JsonFormatter();

System.out.println(Formatter.format());      // BASE
System.out.println(JsonFormatter.format());  // JSON
System.out.println(base.format());           // BASE
~~~

The final line **is allowed** but discouraged: `base.format()` looks like an object-method call, but the compiler selects `Formatter`'s static method from the expression type.

**`@Override` is invalid on `JsonFormatter.format()`**, because static methods hide rather than override.

### A Static Method Cannot Be Turned into an Instance Override

Java rejects the following:

~~~java
class Parent {
    public static void process() {}
}

class Child extends Parent {
    // public void process() {} // Lỗi biên dịch:
    // instance method không thể override/hide static method tương ứng.
}
~~~

The opposite direction is invalid too:

~~~java
class Parent {
    public void process() {}
}

class Child extends Parent {
    // public static void process() {} // Lỗi biên dịch:
    // static method không thể hide instance method tương ứng.
}
~~~

Same-signature methods in an inheritance relationship cannot freely switch between static and instance declarations.

### Interface Static Methods Are Different

Java interfaces can declare static methods:

~~~java
interface TextRules {
    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}

class TextService implements TextRules {}

System.out.println(TextRules.hasText("Java")); // true

// TextService.hasText("Java");  // Không hợp lệ.
// new TextService().hasText("Java"); // Không hợp lệ.
~~~

Static methods declared in an interface **are not inherited by implementing classes** as instance/default methods are. Do not mechanically apply class static-hiding rules to interface static methods.

## 5. Overriding Instance Methods Differs from Hiding

~~~java
class Notification {
    String send() { return "Gửi thông báo"; }
}
class EmailNotification extends Notification {
    @Override String send() { return "Gửi email"; }
}
Notification item = new EmailNotification();
System.out.println(item.send()); // Gửi email
~~~

`send()` is an **overridable instance method**, so Java dispatches it based on the `EmailNotification` object, unlike `item.field` field access or a hidden static call. `@Override` lets the compiler check the signature; valid overrides must also return compatible types, preserve accessibility, obey checked-exception rules, and honor behavioral contracts.

For overriding syntax, covariant returns, `final`, `super`, and constructor-hook behavior, see *Method Overriding and Runtime Method Selection*.

## 6. Can Private Methods Be Overridden?

No. Private instance methods of superclasses **are not inherited for overriding** by subclasses.

~~~java
class SecureBase {
    private String secretLabel() {
        return "Base private";
    }

    public String audit() {
        return secretLabel();
    }
}

class SecureChild extends SecureBase {
    // Phương thức riêng, không phải override private method của Base.
    public String secretLabel() {
        return "Child public";
    }
}
~~~

Usage:

~~~java
SecureBase ref = new SecureChild();
System.out.println(ref.audit()); // Base private

SecureChild child = new SecureChild();
System.out.println(child.secretLabel()); // Child public
~~~

`SecureBase.audit()` invokes its own `private secretLabel()` method declared by `SecureBase`; `SecureChild` declares a same-named method but does not replace it.

This is very different from overridable `public`/`protected` instance methods.

Note that nested classes (*nestmates*) can have special private access under Java's rules, but that does not turn a superclass private method into an overridable method.

### Subclasses Cannot Access Private Fields Through `super`

~~~java
class Parent {
    private int balance = 100;

    public int getBalance() {
        return balance;
    }
}

class Child extends Parent {
    public int readBalance() {
        // return super.balance; // Lỗi: private không được truy cập.
        return getBalance();     // Hợp lệ: gọi public method.
    }
}
~~~

`super` does not bypass `private` access restrictions; it only identifies the superclass context for accessible members.

## 7. Field Hiding and Overriding Can Coexist and Cause Inconsistent State

Consider:

~~~java
class Profile {
    protected String displayName = "Base";

    public String summary() {
        return "Tên: " + displayName;
    }
}

class PremiumProfile extends Profile {
    protected String displayName = "Premium";

    @Override
    public String summary() {
        return "Tên cao cấp: " + displayName;
    }
}
~~~

~~~java
Profile profile = new PremiumProfile();
System.out.println(profile.displayName); // Base
System.out.println(profile.summary());   // Tên cao cấp: Premium
~~~

Although both expressions reference the same object, field access and method calls produce results using **two different rules**.

That is why **external code should not depend on same-named protected/public fields** across an inheritance hierarchy. Prefer overriding methods for variable behavior. When state is shared, the parent should keep a private field and expose validated operations.

## 8. Overloading Asks a Different Question: Which Signature?

~~~java
class Printer {
    void print(Object value) { System.out.println("Object"); }
    void print(String value) { System.out.println("String"); }
}
Object text = "hello";
Printer printer = new Printer();
printer.print(text);      // Object
printer.print("hello");   // String
~~~

`print(Object)` and `print(String)` are **two overloads**; the compiler selects one from the argument's static type, not the runtime object referenced by `text`. After choosing the signature, it can dispatch an overridden instance method at runtime.

| Mechanism | Selected By |
|---|---|
| Field hiding | Static type of the expression |
| Static hiding | Static type or class name |
| Overloading | Static receiver and argument types plus overload-resolution rules |
| Instance overriding | Receiver runtime class after the signature is fixed |

Combined overloading/overriding examples, `null`, boxing, and varargs are covered separately in *Distinguishing Overriding from Overloading*.

## 9. How `super` Affects These Cases

`super` is used in an instance context to identify superclass operations and avoid ambiguity when both classes declare same-named members.

~~~java
class Vehicle {
    protected String label = "Vehicle";

    public String move() {
        return "Vehicle moves";
    }
}

class Car extends Vehicle {
    protected String label = "Car";

    @Override
    public String move() {
        return "Car moves; " + super.move();
    }

    public void inspect() {
        System.out.println(this.label);  // Car
        System.out.println(super.label); // Vehicle
        System.out.println(this.move()); // Car moves; Vehicle moves
    }
}
~~~

- `super.label` selects the superclass's `label` field.
- `super.move()` invokes the superclass implementation (without dynamically redispatching this particular `Car.move()` call to `super`).
- `this.move()` is an ordinary instance-method call on the current object, so it uses the `Car` override.

`super` does not refer to another object: we are still working on the superclass part of **the same `Car` object**.

If a superclass method calls an overridable instance method internally, that inner call can still dispatch to a subclass. Thus a path such as `super.doWork()` → parent method → `this.hook()` → subclass hook implementation is possible.

### Beware of Overridable Methods Called from Constructors

A design error related to polymorphism:

~~~java
class Base {
    Base() {
        initialize(); // Có thể gọi implementation trong subclass.
    }

    void initialize() {}
}

class Derived extends Base {
    private String configuration = "ready";

    @Override
    void initialize() {
        System.out.println(configuration);
    }
}
~~~

~~~java
new Derived();
~~~

It may print `null` because, when the `Base` constructor calls `initialize()`, the ordinary initialization of fields in `Derived` **has not completed yet**. This is not field hiding; it results from **dynamic dispatch during object construction**. Avoid calling overridable methods from constructors when subclass implementations may depend on uninitialized state.

## 10. Same-Named Interface Members Can Cause Ambiguity

Besides class inheritance, Java supports implementing multiple interfaces:

~~~java
interface Left {
    int VERSION = 1;
}

interface Right {
    int VERSION = 2;
}

class Combined implements Left, Right {
    void printVersions() {
        // System.out.println(VERSION); // Mơ hồ, không biên dịch.
        System.out.println(Left.VERSION);
        System.out.println(Right.VERSION);
    }
}
~~~

Interface fields are implicitly `public static final`. If two interfaces declare fields with the same name, qualify the source, such as `Left.VERSION`.

When two interfaces expose **default instance methods** with the same signature, the implementing class may have to override the method to resolve the conflict:

~~~java
interface LeftAction {
    default String action() {
        return "left";
    }
}

interface RightAction {
    default String action() {
        return "right";
    }
}

class CombinedAction implements LeftAction, RightAction {
    @Override
    public String action() {
        return LeftAction.super.action()
                + " + " + RightAction.super.action();
    }
}
~~~

These are two default methods supplied by interfaces, not static hiding. Default-method conflict rules belong to Java's interface-inheritance and instance-method selection mechanisms; distinguish them from compile-time field lookup.

## 11. `final` and Access Levels

### `final` on Methods Prevents the Relevant Override or Hiding

~~~java
class Service {
    public final void start() {
        System.out.println("Started");
    }
}

class SpecialService extends Service {
    // public void start() {} // Lỗi: final method không thể override.
}
~~~

A `final` static method also cannot be hidden by a matching static method of a subclass in a valid inheritance context.

### `final` on Fields Does Not Prevent Field Hiding

~~~java
class Parent {
    public final int code = 100;
}

class Child extends Parent {
    public final int code = 200;
}
~~~

This declaration is valid: `final` prevents **reassignment of that field**, not a subclass declaring a **different** same-named field.

~~~java
Parent view = new Child();
System.out.println(view.code);          // 100
System.out.println(((Child) view).code); // 200
~~~

This can be especially confusing when a field acts as a type tag. Avoid designs that use same-named fields for polymorphic behavior.

### Overrides Must Not Reduce Access

~~~java
class Parent {
    public String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    public String describe() {
        return "Child";
    }
}
~~~

Changing `Child.describe()` to `protected` causes a compilation error: an overriding method cannot narrow the access that callers had through `Parent`.

A subclass may override a superclass `protected` method as `public`, **widening** access where appropriate.

## 12. When to Use and Avoid These Mechanisms

| Need | Prefer | Avoid |
|---|---|---|
| Behavior that varies with the actual object | Instance methods plus `@Override` | Using same-named fields to "override" |
| Utility independent of instances | Call `static` methods by class name | Static calls through objects that suggest dispatch |
| State belonging to each instance | `private` fields and controlled behavior | Same-named public fields across inheritance levels |
| Extending parent behavior | Override and `super.method()` where appropriate | Treating `super` as a way to bypass access control |
| Multiple input forms with different types | Overloads with clear contracts | Confusing overloading with runtime overriding |
| New subtypes without modifying clients | Design abstractions with instance methods/interfaces | Class-based `if` chains or type/name fields driving algorithms |

The practical reason to **avoid field hiding** is maintainability: changing a variable's declared type or adding a cast may change which field is read even when the runtime object stays the same. Properly designed polymorphic methods select an implementation by the actual object, matching OOP needs more closely.

## 13. Mistakes When Reasoning from Member Names

- **"Same names always mean overriding."** Same-named fields are field hiding; same-signature static methods are static hiding; methods with different parameters are usually overloads.
- **"`new Child()` means every access uses Child."** With `Parent ref = new Child()`, only eligible overridden instance methods dispatch dynamically; fields and static methods have separate rules.
- **"`@Override` works on static methods or when only the return type differs."** No. Static methods do not override; changing only a return type does not create an overload.
- **"A getter is the same as a field."** A getter is an instance-method call and may be overridden; field lookup does not dispatch.
- **"`super` calls another parent object or bypasses `private`."** No. `super` selects accessible superclass members on the same object.
- **"A subclass method sharing the parent's private name overrides it."** No. A superclass private method is not an inherited override hook.

When debugging, first identify **what kind of member** is involved, then determine compile-time selection and runtime dispatch. The exercises below demonstrate these differences.

## 14. Exercises

### Exercise 1 — Predict Field and Method Results

~~~java
class A {
    int value = 1;
    String who() { return "A"; }
}

class B extends A {
    int value = 2;
    @Override String who() { return "B"; }
}

A obj = new B();
System.out.println(obj.value);
System.out.println(obj.who());
~~~

**Answer:** `1`, followed by `B`. Fields use the `A` reference type; overridden instance methods use the `B` object.

### Exercise 2 — Predict a Static Method Result

~~~java
class A {
    static String id() { return "A"; }
}

class B extends A {
    static String id() { return "B"; }
}

A x = new B();
System.out.println(x.id());
~~~

**Answer:** `A`. Although legal, invoking a static method through `x` is discouraged; use `A.id()` for clarity.

### Exercise 3 — Override or Overload?

~~~java
class A {
    void draw(Object value) {}
}

class B extends A {
    void draw(String value) {}
}
~~~

**Answer:** `B.draw(String)` is an **overload**, not an override of `A.draw(Object)`, because the parameters differ. `@Override` on `B.draw(String)` produces an error.

### Exercise 4 — Can Private Methods Be Overridden?

~~~java
class A {
    private void save() {}
}

class B extends A {
    public void save() {}
}
~~~

**Answer:** No override occurs. `B.save()` is a separate method; it does not replace the private implementation `A.save()`.

### Exercise 5 — Which Implementation Does `super` Select?

~~~java
class A {
    String message() { return "A"; }
}

class B extends A {
    @Override String message() {
        return super.message() + "B";
    }
}
~~~

**Answer:** `new B().message()` returns `"AB"`. `super.message()` calls the `A` implementation, then `B` appends `"B"`.

### Exercise 6 — Why Can Parent's `report()` Call Child's `describe()`?

**Answer:** `Parent.report()` runs on a receiver that is a `Child` object. Its internal `describe()` instance call within `report()` still uses dynamic dispatch, selecting `Child.describe()`.

### Exercise 7 — Improve the Design

A system uses:

~~~java
class Payment {
    public String type = "generic";
}
class CardPayment extends Payment {
    public String type = "card";
}
~~~

But `Payment p = new CardPayment();` prints `p.type == "generic"`. How would you change the design?

**Hint:** Make `type` a query behavior:

~~~java
class Payment {
    public String type() { return "generic"; }
}
class CardPayment extends Payment {
    @Override public String type() { return "card"; }
}
~~~

Now `Payment p = new CardPayment(); p.type()` returns `"card"` through overriding.

## 15. How to Read a Call in an Inheritance Hierarchy

When you see `ref.member`, check the following in order:

1. **Is `member` a field or method?** Field access does not use dynamic overriding.
2. **If it is a method, is it static?** Static methods do not use runtime dispatch.
3. **If it is an instance method, which signature does the compiler select?** Does overloading depend on argument types?
4. **Does the actual object type validly override that signature?** If so, runtime selects that implementation.
5. **Does any modifier prevent overriding?** `private`, `final`, static declarations, or access rules may alter the relationship.
6. **Is there an explicit `super` or cast?** These can affect field selection, parent methods, or expression types.
7. **Does behavior satisfy the contract?** Even when Java selects the correct implementation, overrides must still honor the supertype's requirements.

~~~mermaid
flowchart TD
    A["Gặp ref.member"] --> B{"Member là field?"}
    B -->|Có| C["Chọn field theo kiểu biểu thức<br/>Field hiding, không dynamic dispatch"]
    B -->|Không| D{"Method là static?"}
    D -->|Có| E["Chọn static method theo compile-time type<br/>Static hiding"]
    D -->|Không| F["Compiler chọn chữ ký overload phù hợp"]
    F --> G["Runtime chọn override theo object thực tế"]
~~~

**Conclusion:** In Java, **member hiding** and **overriding** differ in both OOP meaning and call resolution. Field hiding and static method hiding are determined mainly at compile time; overriding instance methods provides **dynamic polymorphism**. To vary behavior by object type, design contracted instance methods, prefer `@Override`, encapsulate state, and avoid same-named fields in inheritance hierarchies.
