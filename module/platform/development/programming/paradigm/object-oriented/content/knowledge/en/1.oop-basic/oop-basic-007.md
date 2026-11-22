# Class-Based vs. Prototype-Based OOP

When people hear “object-oriented programming,” many first picture a **class** containing fields and methods, followed by `new` creating **objects**. That is the **class-based OOP** model familiar to Java learners. However, organizing software around objects **does not require classes**: another model lets an object use an existing object directly as its **prototype** to find and reuse behavior.

The distinction becomes clear when we ask: *When an object is asked to execute a method that it does not declare directly, where does the program look for that method?*

- In Java, we look at the object's **class type** and methods inherited or overridden through class relationships.
- In JavaScript's prototype model, we look at **the object itself** and follow its **prototype chain** until we find the relevant property or method.

Both models can represent state, behavior, object collaboration, and polymorphism. Their difference lies in **how behavior is organized and reused**, not in whether one is “more truly object-oriented.”

## 1. Two Ways to Build Objects: Blueprints and Prototypes

The **class-based model** treats a class as the definition of a kind of object. The class describes the data instances can hold, constructors establish initial state, and methods express behavior. Two instances of the same class have their own state, while their behavior follows the class definition and related parent classes.

The **prototype-based model** allows one object to be created and another object linked to it. When a property or method is absent from the current object, the program can search its prototype. The prototype is also **an existing object**, not necessarily a “class” or an immutable copy.

| Question | Class-based: Java | Prototype-based: JavaScript |
| --- | --- | --- |
| Source of behavior | Classes and type hierarchies; interfaces define behavioral contracts. | Properties/methods on the current object or objects in its prototype chain. |
| Common object creation | `new SomeClass(...)`; factories are also available. | Object literals `{}`, `Object.create(proto)`, factories, constructors, and `class`/`new` syntax. |
| Behavior reuse | Class methods, inheritance via `extends`, interfaces, and composition. | Delegated property lookup through the prototype chain; composition is also available. |
| Changing where methods are found | Superclass relationships are defined by class types; a running Java object cannot switch its superclass. | Properties on prototype objects can change, and an object's prototype link can be reconfigured (changing links at runtime should be limited). |
| Type system | Java checks most type relationships at compile time. | JavaScript is dynamically typed; object and prototype lookup happens at runtime. |
| Polymorphism | Dynamic dispatch for overridden instance methods; polymorphism through interfaces as well. | Different objects can respond to the same call while resolving functions through their properties and prototype chains. |

**A caution about this comparison:** “class-based” does not mean “statically typed,” and “prototype-based” does not mean “dynamically typed.” These are separate conceptual dimensions. The table uses Java and JavaScript as representative examples, not because dynamically typed languages must use prototypes.

## 2. Class-Based OOP: Reading Java Structure Before Execution

Suppose a delivery application offers two services:

- **Standard**: a base fee of 20.000 VND plus 5.000 VND per kilogram.
- **Express**: a base fee of 40.000 VND plus 12.000 VND per kilogram.

Both receive a weight, both must reject invalid weights, but they calculate fees differently. In Java, we can model them with an **abstract parent class** and **subclasses**.

### Standalone Runnable Java Example

Save as `Main.java` and run using Java 17 or later (the example uses features also available in many older Java versions):

~~~java
import java.util.List;

// Class cha định nghĩa một loại phương thức giao hàng.
abstract class DeliveryMethod {
    private final String name;
    private final long baseFee;

    protected DeliveryMethod(String name, long baseFee) {
        if (name == null || name.isBlank() || baseFee < 0) {
            throw new IllegalArgumentException("Invalid delivery method");
        }
        this.name = name;
        this.baseFee = baseFee;
    }

    public final String name() {
        return name;
    }

    // Template method: phần quy tắc chung không để lớp con bỏ qua.
    public final long quote(int kilograms) {
        if (kilograms <= 0) {
            throw new IllegalArgumentException("Weight must be positive");
        }
        return Math.addExact(baseFee, variableFee(kilograms));
    }

    protected abstract long variableFee(int kilograms);
}

final class StandardDelivery extends DeliveryMethod {
    StandardDelivery() {
        super("Standard", 20_000);
    }

    @Override
    protected long variableFee(int kilograms) {
        return Math.multiplyExact(5_000L, kilograms);
    }
}

final class ExpressDelivery extends DeliveryMethod {
    ExpressDelivery() {
        super("Express", 40_000);
    }

    @Override
    protected long variableFee(int kilograms) {
        return Math.multiplyExact(12_000L, kilograms);
    }
}

public class Main {
    public static void main(String[] args) {
        List<DeliveryMethod> methods = List.of(
            new StandardDelivery(),
            new ExpressDelivery()
        );

        for (DeliveryMethod method : methods) {
            System.out.println(method.name() + ": " + method.quote(2));
        }

        try {
            methods.get(0).quote(0);
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected invalid weight");
        }
    }
}
~~~

Run:

~~~bash
javac Main.java
java Main
~~~

Output:

~~~text
Standard: 30000
Express: 64000
Rejected invalid weight
~~~

### How Are Objects Created and Methods Selected?

Given `DeliveryMethod method = new ExpressDelivery();`:

1. **`ExpressDelivery` is a class** defined with an `extends DeliveryMethod` relationship.
2. **`new ExpressDelivery()` creates an instance** of `ExpressDelivery`. The instance has its own state, including `name = "Express"` and `baseFee = 40000`, initialized by the parent constructor.
3. Variable `method` has the **declared type** `DeliveryMethod`, while the actual object has the **runtime type** `ExpressDelivery`.
4. Calling `method.quote(2)` uses the shared `quote()` method in the parent class, which validates the weight.
5. The `variableFee(2)` call within `quote()` is **dynamically dispatched** to the override in `ExpressDelivery`: `12000 × 2 = 24000`.
6. The final fee is `40000 + 24000 = 64000`.

With `StandardDelivery`, the shared logic remains unchanged; Java selects the corresponding override and returns `20000 + 5000 × 2 = 30000`.

~~~mermaid
classDiagram
    class DeliveryMethod {
      -String name
      -long baseFee
      +name() String
      +quote(int kilograms) long
      #variableFee(int kilograms) long
    }
    class StandardDelivery {
      #variableFee(int kilograms) long
    }
    class ExpressDelivery {
      #variableFee(int kilograms) long
    }
    DeliveryMethod <|-- StandardDelivery
    DeliveryMethod <|-- ExpressDelivery
~~~

In the diagram, the arrow pointing toward `DeliveryMethod` represents **class inheritance**. We define class relationships **in source code**. A Java instance can change values designed to be mutable, but it cannot start inheriting from another superclass while running.

This is only *one way* to design class-based OOP. We could instead use `interface DeliveryMethod` with two implementing classes or composition with a fee-calculation object. Class-based OOP does not require a deep inheritance tree.

## 3. Prototype-Based OOP: Finding Behavior Through Other Objects

JavaScript lets us observe prototype mechanics directly with `Object.create(proto)`. This operation **creates a new object and sets its prototype to `proto`**; it **does not copy all of `proto`'s properties and methods into the new object's own properties**.

We will reuse the delivery problem for comparison with Java.

### JavaScript Example: Creating an Object from an Existing Prototype

Save as `delivery.js` and run with a modern version of Node.js:

~~~javascript
"use strict";

// Một object chứa hành vi được chia sẻ.
const deliveryBehavior = {
  quote(kilograms) {
    if (!Number.isInteger(kilograms) || kilograms <= 0) {
      throw new Error("Weight must be a positive integer");
    }
    return this.baseFee + this.feePerKg * kilograms;
  }
};

// Standard có các thuộc tính riêng và ủy quyền tìm method cho deliveryBehavior.
const standard = Object.create(deliveryBehavior);
standard.name = "Standard";
standard.baseFee = 20_000;
standard.feePerKg = 5_000;

// Express dùng chính standard làm prototype, nhưng đặt lại giá trị riêng.
const express = Object.create(standard);
express.name = "Express";
express.baseFee = 40_000;
express.feePerKg = 12_000;

console.log(standard.quote(2));  // 30000
console.log(express.quote(2));   // 64000

console.log(Object.hasOwn(express, "quote")); // false
console.log(Object.hasOwn(express, "baseFee")); // true
console.log(Object.getPrototypeOf(express) === standard); // true
console.log(Object.getPrototypeOf(standard) === deliveryBehavior); // true

// Economy nhận name và baseFee riêng nhưng kế thừa feePerKg từ standard.
const economy = Object.create(standard);
economy.name = "Economy";
economy.baseFee = 15_000;

console.log(economy.quote(2)); // 25000

// Sửa thuộc tính trên prototype mà economy đang thừa hưởng.
standard.feePerKg = 6_000;

console.log(economy.quote(2));  // 27000
console.log(express.quote(2));  // 64000: express có feePerKg riêng

// Input không hợp lệ vẫn được từ chối bởi cùng method dùng chung.
try {
  economy.quote(0);
} catch (error) {
  console.log("Rejected invalid weight");
}
~~~

Output:

~~~text
30000
64000
false
true
true
true
25000
27000
64000
Rejected invalid weight
~~~

The crucial detail is that object `express` **does not have its own `quote` property**. Yet `express.quote(2)` works because JavaScript searches the objects along the prototype chain in order.

~~~mermaid
flowchart TD
    E["express: own name, baseFee, feePerKg"]
    S["standard: own name, baseFee, feePerKg"]
    B["deliveryBehavior: own quote()"]
    O["Object.prototype"]
    N["null: kết thúc chuỗi"]
    E -->|"[[Prototype]]"| S
    S -->|"[[Prototype]]"| B
    B -->|"[[Prototype]]"| O
    O -->|"[[Prototype]]"| N
~~~

Follow the chain upward from `express`:

1. JavaScript looks for `quote` on `express` itself: **it is absent**.
2. It follows the prototype link to `standard`: **that object also has no own `quote`**.
3. It continues to `deliveryBehavior`: **that object has `quote`**, so JavaScript uses the function.
4. When called as `express.quote(2)`, `this` inside the method is **`express`**. Thus, `this.baseFee` reads `40000` and `this.feePerKg` reads `12000` from `express` itself.

This is a particularly common misunderstanding: **finding a method on a prototype does not mean `this` points to that prototype**. With an ordinary method call `receiver.method()`, `this` depends on the object acting as the call's *receiver* (subject to separate rules for arrow functions, binding, and so on).

### Same Method, but Data Is Looked Up from the Receiving Object

| Expression | Where `quote` is found | `this` during execution | Fee for 2 kg |
| --- | --- | --- | --- |
| `standard.quote(2)` | `deliveryBehavior` | `standard` | 30.000 |
| `express.quote(2)` | `deliveryBehavior` via `standard` | `express` | 64.000 |
| `economy.quote(2)` initially | `deliveryBehavior` via `standard` | `economy` | 25.000 |
| `economy.quote(2)` after changing `standard.feePerKg` | Still `deliveryBehavior` | `economy` | 27.000 |

`economy` has no own `feePerKg`, so it reads the value from `standard`. When `standard.feePerKg` changes from 5.000 to 6.000, `economy`'s result changes too. Meanwhile, `express` has its own `feePerKg` property, which **shadows** the value on `standard` for `express`.

This **delegation** is characteristic of prototype-based models: an object can look to other objects for behavior and data it does not own.

## 4. A “Prototype” Is a Linked Object, Not Automatically a Copy

The term *prototype* can suggest a physical model, leading learners to assume a new object receives copies of all the model's data. With `Object.create(proto)`, that assumption is **incorrect**.

Consider this short example:

~~~javascript
const prototypeUser = { role: "viewer" };
const alice = Object.create(prototypeUser);
const bob = Object.create(prototypeUser);

console.log(alice.role); // "viewer": tìm thấy trên prototype

alice.role = "admin";     // Tạo own property trên alice.
console.log(alice.role); // "admin"
console.log(bob.role);   // "viewer"

prototypeUser.role = "editor";
console.log(bob.role);   // "editor": bob đọc từ prototype.
console.log(alice.role); // "admin": own property che khuất prototype.

delete alice.role;       // Xóa own property.
console.log(alice.role); // "editor": lookup lại tiếp tục đi tới prototype.
~~~

What actually happens:

- `Object.create(prototypeUser)` establishes **a prototype link**; it does not make a deep copy of `prototypeUser`.
- Reading `alice.role` can reach the prototype's value if `alice` has no own property.
- Assigning `alice.role = "admin"` ordinarily creates an **own property** rather than changing `prototypeUser.role`. Getters/setters, read-only descriptors, and proxies follow their own rules.
- `delete alice.role` deletes only the own property (if deletion is permitted), not the property on the prototype.

If the goal is **to copy data into another object**, consider `Object.assign`, spread syntax, or another suitable copying technique. Shallow versus deep copying is a separate choice from setting a prototype.

## 5. Per-Object State and the Risk of Shared State Through Prototypes

Sharing methods is often desirable. But placing **mutable arrays or objects** on a prototype can cause multiple instances to share the same data accidentally.

~~~javascript
const userBehavior = {
  tags: [], // Một mảng nằm trên chính prototype.

  addTag(tag) {
    this.tags.push(tag);
  }
};

const alice = Object.create(userBehavior);
const bob = Object.create(userBehavior);

alice.addTag("vip");
console.log(bob.tags); // ["vip"] — ngoài mong đợi!
~~~

Why? `alice` has no own `tags`, so `this.tags` finds **the same array** on `userBehavior`. Calling `push()` modifies *the referenced array's contents*; it does not create a new own property on `alice`.

The fix is to **initialize mutable state separately for each object**:

~~~javascript
function createUser() {
  const user = Object.create(userBehavior);
  user.tags = []; // Mỗi user có một mảng riêng.
  return user;
}

const user1 = createUser();
const user2 = createUser();

user1.addTag("vip");
console.log(user1.tags); // ["vip"]
console.log(user2.tags); // []
~~~

The design lesson: with prototypes, distinguish **shareable behavior** (methods) from **state each object must own** (arrays, mutable objects, business data). A similar distinction matters in class-based OOP when comparing **instance fields** with **static fields** or shared referenced objects.

## 6. How Does Overriding Work in the Two Models?

In Java, a subclass can **override an instance method** of its parent. Selecting the actual implementation through a parent type uses **dynamic method dispatch**. For example, `ExpressDelivery` overrides `variableFee()` from `DeliveryMethod`. In ordinary Java syntax, an object cannot simply assign a new function to `object.variableFee` to replace the method implementation for that particular instance.

In JavaScript, an object can **shadow** a prototype method with an **own property** of the same name containing a function:

~~~javascript
const formatter = {
  format(value) {
    return String(value);
  }
};

const simple = Object.create(formatter);
const upper = Object.create(formatter);

upper.format = function (value) {
  return String(value).toUpperCase();
};

console.log(simple.format("hello")); // "hello"
console.log(upper.format("hello"));  // "HELLO"
console.log(Object.hasOwn(upper, "format")); // true
~~~

Both `simple` and `upper` share prototype `formatter`, but `upper` has its own `format`, so property lookup **stops at `upper`**.

Describing this behavior as **“overriding a method”** is reasonable at a behavioral level, but mechanically, prototype-based OOP is **using an own property to shadow an inherited property**. This differs from Java class overriding rules involving signatures, accessibility, and type relationships.

In particular, remember that **JavaScript arrow functions do not have their own `this`**. Writing `upper.format = (value) => this...` while expecting `this` to be `upper` can fail because an arrow function captures `this` lexically. Use an ordinary method or function when `this` should be the receiver.

## 7. If JavaScript Has `class`, Is It Still Prototype-Based?

**Yes.** Modern JavaScript supports `class`/`extends`/`new` syntax to declare constructors, methods, and inheritance relationships more clearly. Nevertheless, instance-method lookup still involves **the prototype chain**.

For example:

~~~javascript
class StandardDelivery {
  constructor() {
    this.baseFee = 20_000;
    this.feePerKg = 5_000;
  }

  quote(kilograms) {
    return this.baseFee + this.feePerKg * kilograms;
  }
}

const standard = new StandardDelivery();

console.log(standard.quote(2)); // 30000
console.log(
  Object.getPrototypeOf(standard) === StandardDelivery.prototype
); // true
console.log(
  Object.hasOwn(standard, "quote")
); // false
console.log(
  Object.hasOwn(StandardDelivery.prototype, "quote")
); // true
~~~

The `quote` method defined in the class body above lives on **`StandardDelivery.prototype`**, while `baseFee` and `feePerKg` are created on each instance by the constructor. When `standard.quote(2)` runs, JavaScript can find the method through the prototype.

Three names are easy to confuse:

| Syntax/concept | Role |
| --- | --- |
| `Object.getPrototypeOf(standard)` | Returns the object that is the **internal `[[Prototype]]`** of instance `standard`. |
| `StandardDelivery.prototype` | The `prototype` property of the constructor function/class; typically the object used as `[[Prototype]]` for instances created with `new`. |
| `Object.create(proto)` | Creates a new object whose `[[Prototype]]` is explicitly set to `proto`. |

**`[[Prototype]]` and the property named `prototype` are not the same thing.** Most objects have an internal prototype link (possibly `null`), whereas not every object has its own property named `prototype`. The `Object.getPrototypeOf()` method is generally clearer than legacy `__proto__` access.

A subtle point: saying “`class` is just syntactic sugar” helps recall the underlying prototype mechanism, but does **not mean that every `class` feature is exactly interchangeable with old constructor syntax**. Classes also have distinct semantics, including requiring `new`, rules for `super`, private fields such as `#field`, and other features.

## 8. Side-by-Side Diagrams to Distinguish the Relationships

### Java: Instances Have Classes; Classes Have Inheritance Relationships

~~~mermaid
flowchart TD
    J1["standard : StandardDelivery"] -. "instance of" .-> J2["class StandardDelivery"]
    J3["express : ExpressDelivery"] -. "instance of" .-> J4["class ExpressDelivery"]
    J2 -->|"extends"| J5["abstract class DeliveryMethod"]
    J4 -->|"extends"| J5
~~~

The class determines which methods are available; an override can be selected according to the object's runtime class.

### JavaScript: Objects Look Up Properties Along the Prototype Chain

~~~mermaid
flowchart TD
    P1["express (object)"] -->|"[[Prototype]]"| P2["standard (object)"]
    P2 -->|"[[Prototype]]"| P3["deliveryBehavior (object)"]
    P3 -->|"[[Prototype]]"| P4["Object.prototype"]
    P4 -->|"[[Prototype]]"| P5["null"]
~~~

The `express`, `standard`, and `deliveryBehavior` nodes are all **concrete objects**. With `Object.create`, links between them can be specified without declaring a new class.

The diagrams illustrate **characteristic mechanisms of each model**; they do not mean Java cannot delegate to other objects or JavaScript lacks class syntax.

## 9. Both Support Polymorphism, but Method Lookup Differs

Polymorphism lets a program work with multiple objects through a consistent kind of request.

In Java:

~~~java
DeliveryMethod method = new ExpressDelivery();
long fee = method.quote(2);
~~~

The compiler verifies that `quote(int)` is available on declared type `DeliveryMethod`. When a method is overridden or invokes an overridden hook, the runtime selects the implementation appropriate for the actual object.

In JavaScript:

~~~javascript
function printFee(method, kilograms) {
  console.log(method.quote(kilograms));
}

printFee(standard, 2);
printFee(express, 2);
~~~

The `printFee` function simply invokes the received object's `quote` property. The object may have its own method or find one through the prototype chain. JavaScript commonly describes this style as **duck typing** at the interaction level: an object is usable if it provides the expected behavior. If its `quote` property is not a callable function, the call fails at runtime.

Therefore, **the difference between class-based and prototype-based OOP is not that only one supports polymorphism**. Both can support it; they differ in how behavior is represented, located, and checked.

## 10. Strengths, Limitations, and Choosing an Approach

| Aspect | Class-based OOP | Prototype-based OOP |
| --- | --- | --- |
| **Representing the business model** | Classes/interfaces explicitly express types, contracts, and inheritance relationships. | You can start with concrete objects and shareable behaviors, with less need to define types up front. |
| **Checking before execution** | In Java, the compiler detects many type and method-signature errors. | In plain JavaScript, many invalid property accesses/calls are detected at runtime; TypeScript can add static checking. |
| **Per-object flexibility** | Behavior is generally organized through classes, interfaces, or strategy objects. | Each object can have its own methods/properties and prototype chain. |
| **Predictability** | Type relationships are relatively explicit; too many classes or extends relationships can still be complex. | Dynamic lookup is flexible but may be surprising when prototypes change or mutable state is shared. |
| **Reuse** | Inheritance, composition, and interfaces. | Delegation via prototypes, composition, functions, and factories. |
| **Maintenance** | Deep inheritance trees can create tight coupling and hard-to-follow overrides. | Deep prototype chains, runtime prototype changes, and multi-level shadowing can be confusing. |

**In Java/Spring Boot projects**, you generally define types using classes and interfaces, then establish each type's responsibilities. Not all reuse needs to go through `extends`: composition, strategies, dependency injection, and small interfaces often suit systems with changing requirements better.

**In JavaScript/Node.js projects**, prototypes remain the foundation of JavaScript's object system even when you use `class` syntax. You can use object literals/factories for small objects or classes when you need explicit structure, initialization, private fields, and readable hierarchies. There is no universal rule that “JavaScript must avoid classes” or that “raw prototypes are always better than classes.”

A sound choice depends on **model clarity, invariants to protect, expected changes, and team experience**, rather than the paradigm's name alone.

## 11. Do Not Confuse Prototype-Based OOP with the Prototype Design Pattern

The term **Prototype** also appears among the GoF *creational design patterns*. The two ideas share terminology but **are not the same concept**:

- **Prototype-based OOP** is an *object model*: an object can delegate property/behavior lookup through another prototype object.
- The **Prototype Design Pattern** is a *creational design pattern* that often creates new objects by **copying an existing object**; it can be used in class-based languages such as Java.

Java example:

~~~java
final class ReportConfig {
    private final String format;

    ReportConfig(String format) {
        this.format = format;
    }

    ReportConfig copy() {
        return new ReportConfig(this.format);
    }
}
~~~

`copy()` illustrates creating a new configuration from an existing one. It **does not make Java a prototype-based language**, because instances still belong to class `ReportConfig` and do not perform property lookup through a prototype object as with JavaScript's `Object.create`.

When objects contain collections or mutable references, copy design must also decide between **shallow and deep copying**, which is entirely separate from prototype chains.

## 12. Check Your Understanding with Concrete Scenarios

**Scenario 1.** Are two Java objects constructed with `new StandardDelivery()` the same instance?

**Answer:** No. They are separate instances of the same class. Their class-defined structure and behavior may match, but their object identities differ.

**Scenario 2.** After `const child = Object.create(parent)`, does `child` automatically own copies of all of `parent`'s properties?

**Answer:** No. `child` is linked to `parent` as its prototype. It can *read* properties from `parent` through lookup without owning those properties.

**Scenario 3.** Given `const x = Object.create(proto)` and `proto.say = function() { return this.name; }`, when `x.say()` is called, what does `this` refer to?

**Answer:** `this` is `x` in an ordinary method call. Where the method is found does not determine its receiver.

**Scenario 4.** Why does `economy.quote(2)` change from 25.000 to 27.000 when `standard.feePerKg` changes?

**Answer:** Because `economy` has no own `feePerKg`, lookup reaches `standard`. This demonstrates **reading an inherited value through the prototype**.

**Scenario 5.** Why does `express.quote(2)` remain 64.000 in the same situation?

**Answer:** Because `express` has its own `feePerKg = 12000` property, which shadows the corresponding property on `standard`.

**Scenario 6.** JavaScript has `class` and `extends` syntax. Does that mean it is no longer prototype-based?

**Answer:** No. Instance methods declared with class syntax are generally placed on `Constructor.prototype`, and lookup still uses the prototype chain.

**Scenario 7.** Each object needs its own `tags` list. Is it safe to place `tags: []` on the prototype and call `this.tags.push(...)`?

**Answer:** No. Multiple objects can mutate the same inherited array. Initialize a separate array for each object or use an appropriate immutable structure.

**Scenario 8.** Java uses the Prototype Design Pattern to copy a configuration; is that the same mechanism as `Object.create(proto)`?

**Answer:** No. Copying an object is a creation technique, whereas `Object.create(proto)` primarily establishes *a prototype link* without copying all properties.

## 13. Explaining the Concepts Without Memorizing Definitions

Use a practical question: “Why can two objects both call `quote(2)` but produce different results?”

In **Java**, trace: *Which class created the instance → what type relationships does that class have → which shared method and runtime override are selected → how does the instance's own state contribute to the result?*

In **JavaScript**, trace: *Does the current object have its own `quote` property → if not, which prototypes are visited → where is the method found → which object is receiver `this` → where are the `baseFee` and `feePerKg` values looked up?*

If you can explain that process and predict results before and after modifying a prototype property, you understand **the essential difference between class-based and prototype-based OOP**.
