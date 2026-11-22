# Duck Typing and Capability-Based Polymorphism in Java OOP

> **Core idea:** Instead of asking "Which class family does this object belong to?", many real problems only require asking "What **can this object do**?" A real duck, a robot duck, and a squeaky duck toy may be built very differently but can all **make a sound**. We want one operation that asks each to make its sound without checking every concrete type.

This perspective relates to **duck typing** and **capability-based polymorphism** (*capability-based polymorphism*). The concepts share a behavior-oriented viewpoint, but their language **typing mechanisms differ**: Python can invoke a matching method on an object at runtime; Java generally needs an **explicitly declared interface or parent type**, or an adapter that converts the object to the required contract.

This lesson explains that distinction, uses runnable Java examples, and shows when to choose interfaces, capability checks, or adapters.

## 1. What Is Duck Typing?

A common phrase illustrating duck typing is: *"If something walks like a duck and quacks like a duck, treat it as a duck."*

In programming, the point is not that an object **has a class named `Duck`**, but that it **provides the required behavior**.

A conceptual Python example:

~~~python
class RealDuck:
    def quack(self):
        print("Cạp cạp")

class ToyDuck:
    def quack(self):
        print("Chíp chíp")

def make_sound(thing):
    thing.quack()

make_sound(RealDuck())
make_sound(ToyDuck())
~~~

`make_sound` does not need to know whether the class of `thing` inherits from `Duck`. At runtime, Python looks up the `quack` method on that object. If it is missing or the call is incompatible, an error can arise **at runtime** (such as `AttributeError`).

This is a common form of **dynamic duck typing**: using objects according to what they can do in the current context, without requiring an explicit inheritance relationship beforehand.

**Do not confuse duck typing with structural typing:** a **structural** type system can check the shape of members at compile time, whereas dynamic duck typing often tries the behavior at runtime. Both care about "what an object offers", but differ in when and how that is checked.

## 2. Java Does Not Automatically Treat Two Classes with `quack()` as Compatible

In Java, ordinary subtype relationships between classes and interfaces are **nominal**: they must be established by `extends`, `implements`, or a valid subtype relationship already present in the hierarchy.

Consider two classes:

~~~java
class RealDuck {
    public void quack() {
        System.out.println("Cạp cạp");
    }
}

class ToyDuck {
    public void quack() {
        System.out.println("Chíp chíp");
    }
}
~~~

Although both classes declare `public void quack()`, you **cannot** write a Java method accepting `RealDuck` and pass it a `ToyDuck` merely because they have the same method:

~~~java
static void makeSound(RealDuck duck) {
    duck.quack();
}

// makeSound(new ToyDuck()); // LỖI BIÊN DỊCH
~~~

Simply declaring an interface with the same signature is not enough either:

~~~java
interface Quackable {
    void quack();
}

// Quackable q = new ToyDuck(); // Vẫn lỗi nếu ToyDuck không implements.
~~~

Therefore, saying "Java has duck typing just like Python" is **incorrect**. Java is very capable of **capability-oriented** designs, but the usual approach is to **represent capabilities as interfaces** and have classes explicitly implement those contracts.

| Question | Dynamic duck typing, as in Python | Java using interfaces |
| --- | --- | --- |
| Must the object have a particular class name? | No | No |
| Must an `implements` relationship be declared? | Not in this example | Yes, directly or through a valid subtype relationship |
| Is a matching method name/signature enough? | Can be used when suitable behavior exists at runtime | **Not enough** to establish an interface subtype |
| When are missing methods detected? | Usually when the call executes | Usually when compiling interface-typed code |
| Can callers be decoupled from concrete classes? | Yes | Yes |
| Who ensures the behavioral meaning is upheld? | Whoever writes/selects the object | Implementers and contract tests |

**Remember:** *Java can achieve the same design goal of "request a capability" without using the same mechanism as dynamic duck typing.*

## 3. Capability-Based Polymorphism: Each Interface Is a Role

We do not need to force every object into a `Duck` inheritance tree. Instead, model independent capabilities:

~~~java
interface Quackable {
    void quack();
}

interface Swimmable {
    void swim(int meters);
}

interface Rechargeable {
    void recharge(int units);
}
~~~

A **real duck** can both quack and swim; a **robot duck** can quack and recharge; a **squeaky toy** can quack but neither swim nor recharge.

Accordingly:

- `WildDuck implements Quackable, Swimmable`
- `RobotDuck implements Quackable, Rechargeable`
- An independent `SqueakyToy` has a `quack()` method; if it does not implement `Quackable`, it must be adapted to that Java contract.

The sound-recording program only needs `Quackable`. The swimming pool only needs `Swimmable`. The charging station only needs `Rechargeable`. None needs to know the complete "duck type" of an object.

~~~mermaid
classDiagram
    class Quackable {
        <<interface>>
        +quack() void
    }
    class Swimmable {
        <<interface>>
        +swim(int) void
    }
    class Rechargeable {
        <<interface>>
        +recharge(int) void
    }
    class WildDuck {
        -distanceMeters int
        +quack() void
        +swim(int) void
    }
    class RobotDuck {
        -battery int
        +quack() void
        +recharge(int) void
    }
    Quackable <|.. WildDuck
    Swimmable <|.. WildDuck
    Quackable <|.. RobotDuck
    Rechargeable <|.. RobotDuck
~~~

The diagram describes **type relationships**, not two "object halves". A `WildDuck` instance can be viewed through both interfaces while remaining **one object** with the same internal state.

## 4. Complete Java Example: Request Only the Required Capability

Save as **`DuckTypingCapabilitiesDemo.java`**. Run on Java 11 or later with no external libraries.

~~~java
import java.util.List;

public class DuckTypingCapabilitiesDemo {

    interface Quackable {
        void quack();
    }

    interface Swimmable {
        void swim(int meters);
    }

    interface Rechargeable {
        void recharge(int units);
    }

    static final class WildDuck implements Quackable, Swimmable {
        private int totalDistanceMeters;

        @Override
        public void quack() {
            System.out.println("Vịt thật: cạp cạp");
        }

        @Override
        public void swim(int meters) {
            if (meters <= 0) {
                throw new IllegalArgumentException(
                        "Quãng đường phải dương");
            }
            totalDistanceMeters = Math.addExact(
                    totalDistanceMeters, meters);
            System.out.println(
                    "Vịt thật bơi thêm " + meters
                    + " m (tổng " + totalDistanceMeters + " m)");
        }
    }

    static final class RobotDuck implements Quackable, Rechargeable {
        private int battery = 1;

        @Override
        public void quack() {
            if (battery == 0) {
                throw new IllegalStateException("Robot hết pin");
            }
            battery--;
            System.out.println(
                    "Vịt robot: quack điện tử (pin " + battery + ")");
        }

        @Override
        public void recharge(int units) {
            if (units <= 0) {
                throw new IllegalArgumentException(
                        "Năng lượng sạc phải dương");
            }
            battery = Math.addExact(battery, units);
            System.out.println(
                    "Vịt robot sạc thêm " + units
                    + " (pin " + battery + ")");
        }
    }

    // Một lớp có phương thức quack nhưng KHÔNG implements Quackable.
    static final class SqueakyToy {
        public void quack() {
            System.out.println("Đồ chơi: chíp chíp");
        }
    }

    // Chỉ yêu cầu khả năng phát tiếng.
    static void askToQuack(Quackable participant) {
        participant.quack();
    }

    // Tình huống này chọn sử dụng các khả năng tùy chọn.
    static void runActivity(Quackable participant) {
        askToQuack(participant);

        if (participant instanceof Swimmable) {
            Swimmable swimmer = (Swimmable) participant;
            swimmer.swim(10);
        }

        if (participant instanceof Rechargeable) {
            Rechargeable robot = (Rechargeable) participant;
            robot.recharge(2);
        }
    }

    public static void main(String[] args) {
        WildDuck wildDuck = new WildDuck();
        RobotDuck robotDuck = new RobotDuck();
        SqueakyToy toy = new SqueakyToy();

        // Method reference cung cấp một Quackable adapter.
        Quackable toyAsQuackable = toy::quack;

        List<Quackable> participants = List.of(
                wildDuck, robotDuck, toyAsQuackable);

        for (Quackable participant : participants) {
            runActivity(participant);
        }

        // Không hợp lệ:
        // Quackable directToy = toy;
    }
}
~~~

Compile and run:

~~~bash
javac DuckTypingCapabilitiesDemo.java
java DuckTypingCapabilitiesDemo
~~~

Output:

~~~text
Vịt thật: cạp cạp
Vịt thật bơi thêm 10 m (tổng 10 m)
Vịt robot: quack điện tử (pin 0)
Vịt robot sạc thêm 2 (pin 2)
Đồ chơi: chíp chíp
~~~

### Why Does It Produce These Results?

| Element in `participants` | Actual object or adapter | `quack()` | Additional capability detected |
| --- | --- | --- | --- |
| Element 1 | `WildDuck` | "Quack, quack" | `Swimmable` → swims 10 m |
| Element 2 | `RobotDuck` | "Electronic quack" | `Rechargeable` → recharges 2 units |
| Element 3 | Adapter from `toy::quack` | "Squeak, squeak" | Neither `Swimmable` nor `Rechargeable` is required |

When `runActivity(participant)` is invoked, `participant` has the **static type** `Quackable`, so it can always call `quack()`. For `WildDuck` and `RobotDuck`, polymorphism selects their respective implementations. For the third entry, `Quackable` is implemented by a **functional object created or represented by a method reference**, which delegates to `SqueakyToy.quack()`.

Thus `SqueakyToy` does **not suddenly become a subtype** of `Quackable`. We have created a **different value** satisfying the interface to invoke the toy's existing behavior.

The `totalDistanceMeters` and `battery` counters show that each implementation owns its own state. Sharing an interface **does not imply** identical field layouts or algorithms.

## 5. Distinguishing "Check the Type" from "Request a Capability"

These two ways of structuring code have different extensibility characteristics.

### Approach Coupled to Concrete Classes

~~~java
// Ví dụ minh họa, KHÔNG phải API khuyến nghị:
void makeNoise(Object value) {
    if (value instanceof WildDuck) {
        ((WildDuck) value).quack();
    } else if (value instanceof RobotDuck) {
        ((RobotDuck) value).quack();
    }
}
~~~

Every time a new class capable of making a sound is added, the function needs another branch and may still overlook the toy.

### Capability-Contract Approach

~~~java
void makeNoise(Quackable value) {
    value.quack();
}
~~~

The function needs no changes for a new implementation, provided the supplied object has a valid `Quackable` reference.

This is the benefit of polymorphism: **callers request behavior through a contract; receivers choose how to perform it**.

There is no need to use `instanceof` everywhere just to replace calls already supported by polymorphism. When the behavior is `quack()`, **call `participant.quack()` directly** instead of checking whether it is a `WildDuck` or `RobotDuck`.

However, `instanceof` in `runActivity` serves a different purpose: the program discovers **optional roles** (`Swimmable` or `Rechargeable`) beyond the minimum `Quackable` contract. This is reasonable when capabilities are truly optional, though not necessarily the best API design for every situation.

## 6. When Should Parameters Use an Interface Instead of `instanceof` Checks?

If an operation **requires** an object capable of swimming, declare that capability directly in the parameter type:

~~~java
static void swimmingLesson(Swimmable swimmer) {
    swimmer.swim(100);
}
~~~

The compiler then helps detect invalid calls:

~~~java
WildDuck wild = new WildDuck();
swimmingLesson(wild); // Hợp lệ.

// swimmingLesson(new RobotDuck()); // Lỗi: không có Swimmable.
~~~

Similarly:

~~~java
static void chargingStation(Rechargeable device) {
    device.recharge(5);
}
~~~

This is usually better than an API accepting `Object` and probing it with a long sequence of `instanceof` checks.

If an operation **requires two capabilities simultaneously**, define a composite interface:

~~~java
interface AmphibiousVoice extends Quackable, Swimmable {
}
~~~

A class declaring `implements AmphibiousVoice` promises both capabilities. **Note:** Java's nominal typing does not automatically treat `WildDuck implements Quackable, Swimmable` as a subtype of `AmphibiousVoice` merely because it has all the methods. If you genuinely need a composite contract type, the class must implement it (directly or indirectly), or you must use an adapter.

Comparing the options:

| Requirement | Generally Suitable Design |
| --- | --- |
| Every supplied object must quack | `Quackable` parameter |
| Every supplied object must swim | `Swimmable` parameter |
| Swimming is only an optional addition | Check `instanceof Swimmable` at an appropriate boundary |
| An object must promise several capabilities together | Composite interface or another abstraction with an explicit contract |
| A legacy library has matching methods but does not implement the contract | Adapter or suitable method reference/lambda |
| Data/behaviors belong to the same use case | Composition may be better than forcing an inheritance tree |

**Design perspective:** let parameter types express **the capabilities actually required**, not necessarily every detail about an object.

## 7. Method References: A Small Bridge, Not Automatic Duck Typing

A useful Java feature is adapting a compatible method to a **functional interface**.

~~~java
@FunctionalInterface
interface Quackable {
    void quack();
}

class SqueakyToy {
    public void quack() {
        System.out.println("Chíp chíp");
    }
}
~~~

~~~java
SqueakyToy toy = new SqueakyToy();

// Sai: SqueakyToy không khai báo implements Quackable.
// Quackable a = toy;

// Đúng: biểu thức method reference có target type Quackable.
Quackable b = toy::quack;
b.quack();
~~~

`Quackable` is a **functional interface** because it has one functional abstract method. The compiler checks whether `toy::quack` can implement the functional method `void quack()`.

An equivalent lambda in terms of behavior:

~~~java
Quackable c = () -> toy.quack();
~~~

For a contract requiring several methods, one method reference cannot "automatically implement the entire interface". Instead, write an **adapter class**:

~~~java
interface SoundEmitter {
    void emit();
    String category();
}

final class ToySoundAdapter implements SoundEmitter {
    private final SqueakyToy toy;

    ToySoundAdapter(SqueakyToy toy) {
        this.toy = java.util.Objects.requireNonNull(toy);
    }

    @Override
    public void emit() {
        toy.quack();
    }

    @Override
    public String category() {
        return "TOY";
    }
}
~~~

An adapter can bridge APIs with different method names, transform data, validate input, and translate errors. Its drawback is an additional bridging class/object. Choose the simplest approach that satisfies the contract.

**Do not confuse the mechanisms:** a method reference does not make **the source object's class** an interface subtype. It creates **a new functional object** typed as the target interface.

## 8. Can Java "Duck Type" Through Reflection?

Reflection can **find and invoke methods at runtime** even when objects do not implement a shared interface:

~~~java
import java.lang.reflect.Method;

static void invokeQuackDynamically(Object target)
        throws ReflectiveOperationException {
    Method method = target.getClass().getMethod("quack");
    method.invoke(target);
}
~~~

For example:

~~~java
invokeQuackDynamically(new SqueakyToy());
~~~

This partially imitates "try invoking a suitably named method", but keep these limitations in mind:

- `getMethod("quack")` searches for an appropriate **public** method (with no parameters here); access also depends on Java class and module rules.
- A missing method can cause `NoSuchMethodException` at runtime.
- If the invoked method throws, reflection often wraps the cause in `InvocationTargetException`.
- Parameter mismatches, access control, performance, and maintenance are more complex than with direct calls.
- The compiler does not validate this invocation against the `Quackable` contract as it does for interface-typed code.

Reflection **does not turn Java's entire type system into structural typing**. It is a runtime tool useful for some frameworks, serialization mechanisms, plugins, and specialized integrations. For ordinary application code with a known contract, interfaces and adapters are clearer and safer.

## 9. Think in Capabilities, Not Noun-Based Inheritance Trees

Suppose we define:

~~~java
abstract class Duck {
    abstract void quack();
    abstract void swim(int meters);
}
~~~

and require `RobotDuck extends Duck`. This makes everything named Duck capable of swimming, but a toy robot that quacks may **not** swim. If `swim` overrides `throw new UnsupportedOperationException(...)` by throwing `Duck`, callers accepting `Duck` may unexpectedly fail when performing an operation implied by the contract.

Separate the roles:

~~~java
interface Quackable {
    void quack();
}

interface Swimmable {
    void swim(int meters);
}
~~~

which lets us choose the right capability set:

- `WildDuck` implements both.
- `RobotDuck` implements only `Quackable` (and perhaps `Rechargeable`).
- A `SwimmingRobot` need not be named Duck to implement `Swimmable`.

This applies the **Interface Segregation Principle**: do not force classes or clients to depend on behaviors they neither support nor need.

Do not mechanically split every interface, however. Contracts must be cohesive and meaningful for real clients. If two behaviors always belong together under business rules, combining them may be more appropriate.

## 10. "Matching Method Names" Do Not Guarantee "Matching Contracts"

Imagine two objects both offering:

~~~java
void send(String target, String message)
~~~

One object sends an email while another may write audit data. Identical signatures do not guarantee that:

- `target` means the same thing.
- The same input-validation rules apply.
- Errors and timeouts are handled consistently.
- Side effects, idempotency, and safety guarantees match.
- The objects are substitutable in the same business situation.

Whether using duck typing or Java interfaces, **contract semantics** must be specified and tested.

In the sound example, `Quackable.quack()` implicitly means producing a valid sound. If `RobotDuck.quack()` secretly deletes data or always rejects the operation in a state considered valid by the contract, substitution is unsafe. This is a concern of the **Liskov Substitution Principle (LSP)** and behavior-oriented API design.

## 11. Test Implementations Against the Same Capability

An interface lets us write **one common contract test suite** for multiple implementations.

Example **JUnit 5** test (requires JUnit Jupiter and a suitable test runner; the main program in section 4 uses only the JDK):

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;
import org.junit.jupiter.api.Test;

class QuackableContractTest {

    @Test
    void implementationsCanPerformCommonOperation() {
        List<DuckTypingCapabilitiesDemo.Quackable> actors =
                List.of(
                        new DuckTypingCapabilitiesDemo.WildDuck(),
                        new DuckTypingCapabilitiesDemo.RobotDuck());

        for (DuckTypingCapabilitiesDemo.Quackable actor : actors) {
            assertDoesNotThrow(actor::quack);
        }
    }

    @Test
    void invalidSwimDistanceIsRejected() {
        DuckTypingCapabilitiesDemo.Swimmable swimmer =
                new DuckTypingCapabilitiesDemo.WildDuck();

        assertThrows(IllegalArgumentException.class,
                () -> swimmer.swim(0));
    }

    @Test
    void adapterCallsAnExistingMethod() {
        DuckTypingCapabilitiesDemo.SqueakyToy toy =
                new DuckTypingCapabilitiesDemo.SqueakyToy();
        DuckTypingCapabilitiesDemo.Quackable adapter = toy::quack;

        assertDoesNotThrow(adapter::quack);
    }
}
~~~

The first test minimally verifies that instances implementing `Quackable` can be invoked successfully in the example's initial state. Real contract tests must also cover **results, state, errors, preconditions, and postconditions**, not merely "does not throw".

Other valuable cases include depleted robot batteries, swimming distances of 0 or less, large values causing overflow, adapters to methods with differing signatures, and objects lacking optional capabilities.

## 12. Common Misconceptions

| Claim | Assessment | Explanation |
| --- | --- | --- |
| "Java automatically treats every class with `quack()` as `Quackable`" | **False** | An interface relationship must be declared or adapted through an adapter value |
| "Duck typing requires the object to be class `Duck`" | **False** | The focus is the capability used, not the class name |
| "Two objects implementing the same interface must have identical fields" | **False** | Each implementation has its own data representation and algorithms |
| "One object can implement several interfaces" | **True** | A class may implement multiple contracts |
| "`instanceof` detects a method just because its name matches" | **False** | `instanceof` checks runtime type compatibility, not dynamically discovering signatures |
| "A method reference automatically makes the source class implement an interface" | **False** | It provides a functional object/value of the target type |
| "Reflection is identical to Python duck typing" | **No** | Only some dynamic calls can be imitated, with different constraints |
| "An interface eliminates the need to test business semantics" | **False** | The compiler checks types, not business correctness |
| "Every optional capability requires `instanceof` everywhere" | **False** | Design clients to accept the required interface or use composition |

## 13. Quick Practice

**Question 1.** A `ToyDuck` class declares only `public void quack()` without `implements Quackable`. Can it be assigned to `Quackable q = new ToyDuck();`?

**Answer:** Not in Java, despite the matching signature. Declare the interface relationship or provide an appropriate adapter/method reference.

**Question 2.** Why can `WildDuck` and `RobotDuck` use `Quackable` without a common custom base class?

**Answer:** Both declare `implements Quackable`, so each instance is a subtype of the `Quackable` contract. A function accepting `Quackable` need not know concrete class names.

**Question 3.** Why can `runActivity` invoke `participant.quack()` without `instanceof Quackable` in the main example?

**Answer:** The parameter already has type `Quackable`, so the compiler guarantees the method is available. `instanceof` is only needed when checking **a different capability** that may not be supported.

**Question 4.** A function always requires a swimmer. Should it accept `void exercise(Object obj)` and cast, or declare `void exercise(Swimmable swimmer)`?

**Answer:** Prefer `Swimmable` because it expresses the mandatory capability directly and lets the compiler validate call sites.

**Question 5.** Does `WildDuck implements Quackable, Swimmable` automatically become a subtype of `interface AmphibiousVoice extends Quackable, Swimmable`?

**Answer:** No. Java relies on declared type relationships; structurally satisfying two interfaces does not automatically create a new nominal relationship with their composite interface.

**Question 6.** What is the difference between `Quackable q = toy::quack;` and `Quackable q = toy;`?

**Answer:** The first adapts a method reference to a functional interface, creating a value that invokes `toy.quack()`; the second requires the `toy` object itself to be a subtype of `Quackable`, which is false unless its class implements the interface.

**Question 7.** When should we avoid modeling "every Duck can swim"?

**Answer:** When some duck-sounding objects cannot swim. Forcing them to override `swim` just to throw an exception breaks caller expectations. Split `Quackable` and `Swimmable` into their actual capabilities.

## Key Takeaways

**Duck typing** emphasizes "what an object **can do**" instead of "what its **type is named**". Java does not infer subtype relationships from method shapes as dynamic duck typing does. For **capability-based polymorphism** in Java, model capabilities with interfaces, let classes implement the capabilities they actually support, and adapt existing objects through adapters or method references.

When designing an API, ask **"What minimum capability must an object provide for this task to work correctly?"** Declaring parameter types by that capability usually produces clear contracts, extensible code, and fewer class-name-based branches.
