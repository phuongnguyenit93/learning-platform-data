# The “is-a” relationship and substitutability in Java OOP

When we see `Dog extends Animal` or `ExpressShipping implements ShippingPolicy`, we often say the subtype has an **“is-a” relationship (*is-a*)** with the supertype. In programming, this has two levels of meaning:

- **Subtyping:** Java permits a subtype expression wherever a compatible supertype or interface is expected.
- **Behavioral substitutability:** Replacing an object with another implementation still lets code written against the common contract behave correctly according to its promises.

The compiler largely checks the first level. The second requires designers to define and implement **behavioral contracts**: input conditions, output guarantees, invariants, failures, side effects, and promises that clients rely on.

**Core idea:** Using `extends` or `implements` does not by itself ensure a well-designed “is-a” relationship. A subtype must genuinely fulfill the supertype's role.

## 1. Understanding “is-a” in Java

Example:

~~~java
class Animal {
    public String describe() {
        return "Một động vật";
    }
}

class Dog extends Animal {
    @Override
    public String describe() {
        return "Một con chó";
    }

    public void bark() {
        System.out.println("Gâu!");
    }
}
~~~

A `Dog` object can also be used as an `Animal`:

~~~java
Dog dog = new Dog();
Animal animal = dog; // Upcasting: hợp lệ, không cần ép kiểu tường minh.

System.out.println(animal.describe()); // Một con chó
// animal.bark(); // Không biên dịch: Animal không có bark().
~~~

In this code:

1. The **runtime object** is a `Dog`; the assignment `animal = dog` does not create a new `Animal`.
2. The **declared type of the variable** `animal` is `Animal`, so the compiler permits only members accessible through that type.
3. **Overridden instance methods** are dispatched at runtime based on the actual object: `Dog.describe()`.
4. `bark()` is declared only on `Dog` and is not part of the `Animal` contract, so it cannot be called directly through an `Animal` reference.

This is the foundation of **runtime polymorphism**.

~~~mermaid
classDiagram
    class Animal {
        +describe() String
    }
    class Dog {
        +describe() String
        +bark() void
    }
    Animal <|-- Dog
~~~

In Java, `extends` on a class is a mechanism for **class inheritance**. Besides being usable as the supertype, subclasses participate in implementation inheritance, constructor chaining, and Java override rules. A class may directly `extends` only one class, but may `implements` several interfaces.

For example, `Printer implements Printable` means **Printer can fulfill the Printable role**, even if `Printer` does not belong to the same class hierarchy of machines as other implementations.

## 2. Type relationships and behavioral substitutability are not identical

| Question | Java type substitutability | Behavioral substitutability |
|---|---|---|
| Where is it primarily checked? | Compiler and runtime type system | Contract design, testing, and observed behavior |
| Basic requirement | `Dog` is a subtype of `Animal` | `Dog` fulfills the public promises of `Animal` |
| Are different algorithms allowed? | Yes | Yes |
| Must outputs be identical? | No | No, unless the contract requires it |
| Can the compiler miss problems? | Yes, such as invalid casts | Yes, such as strengthened preconditions or semantically incorrect results |
| Evaluation basis | `extends`, `implements`, method signatures, and type rules | Preconditions, postconditions, invariants, exceptions/side effects |

For instance, a `ShippingPolicy` may quote different fees for standard and express services. **Different fees** do not prevent substitutability if the contract allows each policy to use its own pricing. But an implementation that unexpectedly returns a negative fee when the contract requires nonnegative fees violates substitutability.

This is captured by the **Liskov Substitution Principle (LSP)**: subtype objects should be usable wherever supertype objects are expected **without invalidating the program correctness properties promised by the contract**.

## 3. Complete Java example: two policies, one contract

A sales application needs to calculate shipping fees. Its checkout layer only needs a policy that can **quote a valid parcel**; it does not need to know how the fee is calculated.

In this example, the contract specifies:

- The input must be a valid `Parcel`, not `null`.
- `quote(parcel)` returns a `ShippingQuote` other than `null`, with a nonnegative fee in VND.
- The implementation must not modify `Parcel`.
- For `null` input, the implementation throws `NullPointerException`.
- If a calculation exceeds the `long` range, the implementation may throw `ArithmeticException`; it must not silently overflow and report an incorrect fee.

Create **`Demo.java`**; this code runs with Java 17 or later:

~~~java
import java.util.Objects;

public class Demo {
    public static void main(String[] args) {
        Parcel parcel = new Parcel(1_500, 10);

        CheckoutService standard = new CheckoutService(
                new StandardShipping()
        );
        CheckoutService express = new CheckoutService(
                new ExpressShipping()
        );

        print(standard.calculate(parcel));
        print(express.calculate(parcel));
    }

    private static void print(ShippingQuote quote) {
        System.out.println(quote.method() + ": "
                + quote.feeVnd() + " VND");
    }
}

// Giá trị đầu vào hợp lệ ngay sau khi được tạo.
record Parcel(long weightGrams, int distanceKm) {
    Parcel {
        if (weightGrams <= 0) {
            throw new IllegalArgumentException(
                    "Trọng lượng phải dương");
        }
        if (distanceKm < 0) {
            throw new IllegalArgumentException(
                    "Khoảng cách không được âm");
        }
    }
}

record ShippingQuote(String method, long feeVnd) {
    ShippingQuote {
        Objects.requireNonNull(method, "method");
        if (method.isBlank() || feeVnd < 0) {
            throw new IllegalArgumentException(
                    "Báo giá không hợp lệ");
        }
    }
}

/**
 * Hợp đồng chung cho mọi chính sách vận chuyển.
 *
 * Với Parcel hợp lệ và khác null:
 * - Trả ShippingQuote khác null, feeVnd >= 0.
 * - Số tiền có đơn vị VND.
 * - Không sửa Parcel và không thực hiện ghi dữ liệu.
 *
 * @throws NullPointerException nếu parcel == null
 * @throws ArithmeticException nếu phép tính tràn long
 */
interface ShippingPolicy {
    ShippingQuote quote(Parcel parcel);
}

// Mô phỏng chính sách tiêu chuẩn.
final class StandardShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        Objects.requireNonNull(parcel, "parcel");

        long kilograms = ceilKilograms(parcel.weightGrams());
        long weightFee = Math.multiplyExact(kilograms, 5_000L);
        long distanceFee =
                Math.multiplyExact(parcel.distanceKm(), 2_000L);

        long total = Math.addExact(
                10_000L,
                Math.addExact(weightFee, distanceFee)
        );

        return new ShippingQuote("STANDARD", total);
    }

    private long ceilKilograms(long grams) {
        // grams > 0; tránh overflow của (grams + 999).
        return 1L + (grams - 1L) / 1_000L;
    }
}

// Mô phỏng chính sách hỏa tốc.
final class ExpressShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        Objects.requireNonNull(parcel, "parcel");

        long kilograms = 1L + (parcel.weightGrams() - 1L) / 1_000L;
        long weightFee = Math.multiplyExact(kilograms, 8_000L);
        long distanceFee =
                Math.multiplyExact(parcel.distanceKm(), 3_000L);

        long total = Math.addExact(
                20_000L,
                Math.addExact(weightFee, distanceFee)
        );

        return new ShippingQuote("EXPRESS", total);
    }
}

// Client chỉ cần khả năng báo giá, không cần biết class cụ thể.
final class CheckoutService {
    private final ShippingPolicy policy;

    CheckoutService(ShippingPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    ShippingQuote calculate(Parcel parcel) {
        return policy.quote(parcel);
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
STANDARD: 40000 VND
EXPRESS: 66000 VND
~~~

Fee calculations for a parcel weighing 1.500 grams and traveling 10 km:

| Policy | Base fee | Weight rounded to 2 kg | Distance of 10 km | Total |
|---|---:|---:|---:|---:|
| Standard | 10.000 | 2 × 5.000 | 10 × 2.000 | **40.000 VND** |
| Express | 20.000 | 2 × 8.000 | 10 × 3.000 | **66.000 VND** |

Different fees are **variations allowed by the contract**. The implementations remain substitutable because `CheckoutService` relies only on one shared operation: accept a valid parcel and return a nonnegative quote in VND.

~~~mermaid
classDiagram
    class ShippingPolicy {
        <<interface>>
        +quote(Parcel) ShippingQuote
    }
    class StandardShipping {
        +quote(Parcel) ShippingQuote
    }
    class ExpressShipping {
        +quote(Parcel) ShippingQuote
    }
    class CheckoutService {
        -ShippingPolicy policy
        +calculate(Parcel) ShippingQuote
    }
    ShippingPolicy <|.. StandardShipping
    ShippingPolicy <|.. ExpressShipping
    CheckoutService --> ShippingPolicy : phụ thuộc
~~~

Here, the subtype represents the **role** `ShippingPolicy`. `StandardShipping` and `ExpressShipping` need not represent the same kind of physical object; they are strategies implementing one capability.

## 4. Upcasting: passing a subtype object where a supertype is expected

In Java, assigning or passing a reference from a subtype to a compatible supertype is a **widening reference conversion**, often simply called *upcasting*:

~~~java
ShippingPolicy policy = new ExpressShipping();
CheckoutService service = new CheckoutService(policy);

ShippingQuote result = service.calculate(new Parcel(800, 4));
~~~

This conversion does not create a new object, copy data, or “slice off” part of the implementation. The object remains an `ExpressShipping`; the `policy` variable only exposes the public operations declared by `ShippingPolicy`.

A Java example to verify this:

~~~java
interface SoundMaker {
    String sound();
}

class Cat implements SoundMaker {
    @Override
    public String sound() {
        return "Meo";
    }

    public void scratch() {
        System.out.println("Cào");
    }
}

Cat cat = new Cat();
SoundMaker maker = cat;

System.out.println(maker.sound()); // Meo
System.out.println(maker == cat);  // true
// maker.scratch(); // Lỗi biên dịch: không thuộc SoundMaker.
~~~

Place the example statements inside a suitable Java method. The reference's declared type determines **which methods can be called**, while the object's runtime type determines **the implementation of an overridden instance method**.

Do not confuse this with static methods and field hiding:

~~~java
class Parent {
    public String kind = "Parent";

    public String describe() {
        return "Parent";
    }
}

class Child extends Parent {
    public String kind = "Child";

    @Override
    public String describe() {
        return "Child";
    }
}

Parent ref = new Child();
System.out.println(ref.kind);       // Parent: field theo kiểu tham chiếu.
System.out.println(ref.describe()); // Child: method theo kiểu runtime.
~~~

The output shows that **fields are not overridden like instance methods**. Polymorphic design should therefore rely on methods and contracts, not public fields that happen to share names.

## 5. Preconditions, postconditions, and invariants in LSP

For an implementation to substitute for a supertype, it must preserve the promises that clients rely on.

### Do not strengthen preconditions

If `ShippingPolicy` promises to handle every valid `Parcel`, a new implementation **cannot arbitrarily** require `distanceKm <= 5` and reject all longer routes unless the shared contract explicitly allows that rejection.

The following implementation is questionable:

~~~java
final class VeryLocalShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        Objects.requireNonNull(parcel, "parcel");

        if (parcel.distanceKm() > 5) {
            throw new IllegalArgumentException(
                    "Chỉ giao trong bán kính 5 km");
        }
        return new ShippingQuote("LOCAL", 5_000L);
    }
}
~~~

It **compiles**, but violates the example contract, which requires quoting every valid `Parcel` except in arithmetic overflow cases. A client can supply a 10-km parcel—valid under the common contract—but this implementation imposes a new input restriction.

If a shipping business serves only certain destinations, redesign the contract to represent **unsupported routes** as an allowed result or separate route-availability checking into its own capability. Do not hide new limits in a subtype and surprise callers.

### Do not weaken postconditions

If the contract promises nonnegative fees, returning `null` or a negative number is incorrect. For example:

~~~java
final class NullShipping implements ShippingPolicy {
    @Override
    public ShippingQuote quote(Parcel parcel) {
        return null; // Biên dịch nhưng vi phạm hợp đồng non-null.
    }
}
~~~

Clients are entitled to rely on published postconditions:

~~~java
ShippingQuote quote = policy.quote(parcel);
// Nếu hợp đồng được thực hiện đúng, quote != null.
System.out.println(quote.feeVnd());
~~~

In production code, if a provider can reject a request or become unavailable, represent **rejection status** using a result type or exception agreed upon by the contract. Do not disguise an error as a fee of 0 when `0` means “free shipping.”

### Preserve supertype invariants

If an `Account` promises `balance >= 0`, a subclass must not make `balance` negative through its own new methods. Additional public subtype behavior must preserve the valid state promised by the supertype.

Invariants are typically protected by constructors, checks before mutation, and restrictions on subclasses directly modifying fields. An interface does not enforce invariants automatically through the compiler; the implementation must be designed and tested correctly.

### Preserve observable failure behavior and side effects

A subtype should not turn an operation promised to be purely computational into one that silently deletes data. If the contract specifies “no I/O,” a new implementation must not unexpectedly send an HTTP request or write to a database.

Conversely, **not every difference in exceptions or performance violates LSP**. What matters is the actual contract. In the example `ShippingPolicy`, an `ArithmeticException` on arithmetic overflow is already documented.

## 6. A correct domain label does not guarantee a suitable contract

In geometry, a square is a kind of rectangle. But consider a **mutable** `Rectangle` exposing two independent setters:

~~~java
// Hợp đồng Rectangle: setWidth chỉ đổi width;
// setHeight chỉ đổi height.
rectangle.setWidth(5);
rectangle.setHeight(3);
System.out.println(rectangle.area()); // 15
~~~

If `Square extends Rectangle` overrides each setter to preserve `width == height`, after those two calls both sides equal `3` and the area becomes `9`. The subtype has **weakened the postcondition** that “the other dimension remains unchanged.” If it throws instead when the dimensions differ, it **strengthens the precondition**: an input valid for `Rectangle` is rejected by `Square`.

This illustrates the boundary between *is-a by name* and substitutability under an API. A suitable solution is to put `area()` in a shared `Shape` abstraction or separate the resizing capabilities of rectangles and squares into appropriate contracts. The final lesson builds two runnable programs and contract tests to verify each case.

**The focus of this lesson:** evaluate `ShippingPolicy` by the same standard: every implementation must quote valid parcels defined by the contract; different fees are acceptable, but arbitrarily rejecting an allowed route is not.

## 7. “Is-a” and “has-a”: when to prefer composition?

A sound inheritance relationship should make sense both in the business domain and under the behavioral contract.

Useful questions:

1. Is the child object **genuinely a kind of** parent object in the way this system uses it?
2. Are all operations that clients may call on the parent valid and meaningful for the child?
3. Do subclass invariants conflict with the state changes the parent permits?
4. Do we need **substitutability under a contract**, or merely **a little code reuse**?

For example, `Car extends Engine` is semantically wrong: a car **has an engine** (*has-a*); it is not **an engine** (*is-a*). Use composition:

~~~java
final class Engine {
    public void start() {
        System.out.println("Động cơ hoạt động");
    }
}

final class Car {
    private final Engine engine;

    Car(Engine engine) {
        this.engine = java.util.Objects.requireNonNull(engine);
    }

    public void start() {
        engine.start();
    }
}
~~~

Usage:

~~~java
Car car = new Car(new Engine());
car.start();
~~~

`Car` keeps an `Engine` collaborator and delegates behavior to it. Composition is typically appropriate for **has/contains/uses** relationships or when the implementation must change without forcing a class into an invalid subtype relationship.

An `extends` relationship chosen only for code reuse may force a subclass to expose superclass operations it cannot correctly fulfill.

## 8. Java override rules preserve part of the contract

The Java compiler enforces some restrictions to reduce risks when subclasses substitute for superclasses.

| Override rule | Example/meaning |
|---|---|
| Cannot reduce accessibility | A `public` parent method cannot be overridden as `protected` |
| Covariant return types are allowed | A child method may return a compatible subtype of a reference return type |
| Cannot improperly widen checked exceptions | An overriding method cannot declare checked exceptions broader than the parent's rules |
| Cannot override a `final` instance method | `final` prevents overriding |
| Static methods do not override instance methods | Static hiding differs from dynamic dispatch |
| Parent `private` methods are not overridden | A subclass may declare an unrelated method with the same name |
| The compiler checks `@Override` | Helps catch signature mistakes or confusion about overrides |

Example of a covariant return type:

~~~java
class Animal {
    public Animal copy() {
        return new Animal();
    }
}

class Dog extends Animal {
    @Override
    public Dog copy() {
        return new Dog(); // Dog là subtype của Animal.
    }
}
~~~

A client holding an `Animal` reference can still invoke `copy()` and receives an `Animal` according to the declared type. A client holding a `Dog` reference can rely on the method returning `Dog`.

Example with checked exceptions:

~~~java
import java.io.IOException;

class Source {
    public String read() throws IOException {
        return "data";
    }
}

class CachedSource extends Source {
    @Override
    public String read() {
        return "cached"; // Không cần ném checked exception.
    }
}

// Không thể override read() thành:
// public String read() throws Exception { ... }
// vì Exception rộng hơn IOException.
~~~

Java permits overrides to **narrow** checked exceptions here, but not add checked exceptions incompatible with the original method. Language rules help with declared-type substitutability, but are **insufficient** to establish correct business behavior.

Note: a subtype can still throw unchecked exceptions at runtime. Thus, “no compilation error” does not establish that all preconditions/postconditions are preserved.

## 9. Downcasting: why can casting to a subtype reduce flexibility?

Upcasting from a subtype to a supertype is usually automatic:

~~~java
ShippingPolicy policy = new StandardShipping();
~~~

But casting from a supertype to a particular subtype requires checking, since a supertype variable could refer to a different implementation:

~~~java
ShippingPolicy policy = new ExpressShipping();

// StandardShipping standard = (StandardShipping) policy;
// Nếu chạy: ClassCastException.
~~~

Java 17 supports pattern matching with `instanceof` for safe checks:

~~~java
if (policy instanceof StandardShipping standard) {
    System.out.println("Đang dùng gói tiêu chuẩn");
}
~~~

This usage is syntactically valid, but if a client repeatedly writes:

~~~java
if (policy instanceof StandardShipping) {
    // Một nhánh nghiệp vụ riêng.
} else if (policy instanceof ExpressShipping) {
    // Một nhánh khác.
}
~~~

it starts depending on concrete implementations. Adding a new subtype then requires changing the client, undermining polymorphism.

Look for an appropriate shared operation in the interface, or move the choice of implementation into a factory/configuration. `instanceof` still has valid uses when the actual type matters, such as backward-compatible adapters or distinguishing a closed set of types.

**Do not overuse casts** merely to access methods outside the contract. If only some implementations offer a capability, consider a separate role interface so clients can declare precisely which capability they require.

## 10. A subtype relationship between objects does not imply one between collections

A Java generics pitfall:

~~~java
class Animal {}
class Dog extends Animal {}

java.util.List<Dog> dogs = new java.util.ArrayList<>();

// java.util.List<Animal> animals = dogs; // Lỗi biên dịch.
~~~

Although `Dog` is a subtype of `Animal`, `List<Dog>` is **not** a subtype of `List<Animal>`. Java generics are **invariant** by default.

If that assignment were allowed, a `Cat` could be added to an underlying list of `Dog` objects, violating type safety.

To read elements through the parent role:

~~~java
java.util.List<Dog> dogs = java.util.List.of(new Dog());
java.util.List<? extends Animal> animals = dogs;

Animal first = animals.get(0);

// animals.add(new Animal()); // Không hợp lệ về type safety.
~~~

The wildcard `? extends Animal` allows elements to be read as `Animal`, but not arbitrary additions of a specific `Animal`, because the list might actually contain `Dog` or another subtype.

For a consumer that adds `Dog` elements:

~~~java
static void addDogs(java.util.List<? super Dog> destination) {
    destination.add(new Dog());
}
~~~

A common practical guideline is **PECS**: *Producer Extends, Consumer Super*. It is about variance in Java generics and should not be confused with upcasting between **individual objects**.

### Arrays differ from generics

Java arrays are **covariant**:

~~~java
Animal[] animals = new Dog[1];
// animals[0] = new Animal(); // ArrayStoreException lúc chạy.
~~~

Although the array assignment compiles, the JVM must check element types at runtime. Invariant generics prevent many similar errors at compile time.

## 11. Designing contracts that make subtypes usefully substitutable

In the shipping example, `ShippingPolicy` focuses on one small capability. If a new policy serves only short routes, two designs are possible depending on the business:

**Option A — Change the contract to allow unsupported-service results.**

~~~java
sealed interface QuoteResult
        permits QuoteSuccess, UnsupportedRoute {}

record QuoteSuccess(ShippingQuote quote) implements QuoteResult {}
record UnsupportedRoute(String reason) implements QuoteResult {}
~~~

A different contract could define `QuoteResult quote(Parcel parcel)`, with all implementations agreeing when to return `UnsupportedRoute`. Clients must handle that state.

**Option B — Separate capabilities by role.** For example, `RouteSupport` provides only `boolean supports(Parcel)`, while `ShippingPolicy` provides quotes after valid selection. However, conditions/data may change between `supports()` and `quote()`, so the API must define appropriate consistency guarantees.

You cannot force every provider to handle input outside its actual capabilities while preserving the old contract unchanged. Design **result terminology or responsibility boundaries** that reflect the business accurately.

### LSP does not mean “all subtypes must be identical”

A `Comparator<String>` may sort A to Z or Z to A; a `PaymentMethod` may pay by card or wallet; and a `ShippingPolicy` may calculate different fees.

Such differences are valid when clients rely only on shared guarantees. LSP does not require the same algorithm, internal data, or output values regardless of context.

### Can a subtype add methods?

Yes. `Dog` may have `bark()` even though `Animal` does not. An additional capability does not necessarily violate LSP, provided the object still fulfills every `Animal` promise when used as an `Animal`. A client that needs `bark()` must depend on an appropriate type/role rather than assume every `Animal` barks.

## 12. Test substitutability using the same scenarios

A practical approach is to test **a shared contract** against every implementation, followed by tests specific to each algorithm.

For the classes in `Demo.java`, add the following static method to `Demo` to try this:

~~~java
private static void verifyContract(ShippingPolicy policy) {
    Parcel input = new Parcel(1_200, 8);
    ShippingQuote result = policy.quote(input);

    if (result == null || result.feeVnd() < 0) {
        throw new AssertionError("Báo giá không hợp lệ");
    }

    if (input.weightGrams() != 1_200 || input.distanceKm() != 8) {
        throw new AssertionError("Đầu vào bị thay đổi");
    }

    try {
        policy.quote(null);
        throw new AssertionError("Đáng lẽ phải từ chối null");
    } catch (NullPointerException expected) {
        // Hợp đồng yêu cầu lỗi này cho null.
    }
}
~~~

Call it from `main`:

~~~java
verifyContract(new StandardShipping());
verifyContract(new ExpressShipping());
System.out.println("Hai implementation vượt qua kiểm tra cơ bản");
~~~

This is only a minimal set of checks. It **does not prove** that every fee calculation is correct, establish thread safety, or cover all boundary cases. Real systems need tests for weights/distances, arithmetic limits, rounding rules, provider failures, and business compatibility.

The key point is to test **shared promises** with one test suite and verify **implementation-specific behavior** with separate provider tests.

## 13. Warning signs that an “is-a” relationship needs review

| Warning sign | Risk | Improvement |
|---|---|---|
| Subclass throws `UnsupportedOperationException` for many parent methods | Subtype cannot fulfill its promised role | Split into smaller interfaces or change the hierarchy |
| Child class adds unexpected preconditions | Valid clients are rejected | Redesign the contract or separate roles |
| Child class weakens postconditions | Clients receive incorrect results | Restore guarantees and expand the valid result type |
| Subclass frequently checks/casts to a concrete type | Client code depends on implementation | Find a suitable abstraction and inject the required role |
| Inheritance is used only to obtain utility methods | Domain relationship is incorrect | Composition or utility class |
| Parent exposes field changes incompatible with a stricter child invariant | State rules conflict | Reduce setters; favor behaviors or immutable values |
| Client uses `instanceof` for every variant | Adding a subtype requires client changes | Use polymorphism or a factory/strategy where appropriate |
| Parent contract tests pass but child tests fail | Substitutability is violated | Fix the implementation or redefine the abstraction |

A useful design question is: **“If I only know the parent type, can I use the child object without inspecting its actual class name or adding special exceptions?”** If the answer is often “no,” reconsider the subtype relationship.

## 14. Self-assessment exercises

**Exercise 1: same object or two objects?**

~~~java
Dog dog = new Dog();
Animal animal = dog;
~~~

Suppose `Dog extends Animal`. How many objects are created by the code, and what does `animal instanceof Dog` return?

**Answer:** one `Dog` object; `animal instanceof Dog` is `true`. Upcasting does not create a new object.

**Exercise 2: overriding and runtime dispatch**

~~~java
class A {
    String name() { return "A"; }
}
class B extends A {
    @Override String name() { return "B"; }
}
A item = new B();
System.out.println(item.name());
~~~

**Answer:** `B`, because `name()` is an overridden instance method. Variable declarations and output statements must be placed in an appropriate method.

**Exercise 3: a subtype rejects every input above 5 kg even though the parent contract accepts every positive weight. Is that valid?**

**Answer:** This strengthens the subtype's preconditions. If the parent truly promises to handle all positive weights, the subtype violates substitutability. Put the limit into the shared contract or model an unsupported-result state.

**Exercise 4: is `Square extends Rectangle` always wrong?**

**Answer:** The class names alone are insufficient. If mutable `Rectangle` exposes independent `setWidth()` and `setHeight()` methods, `Square` struggles to fulfill both the parent contract and the invariant of equal sides. With a `Shape` that only exposes `area()`, both can implement the contract legitimately.

**Exercise 5: can `List<Dog>` be passed to a method accepting `List<Animal>`?**

**Answer:** Not directly, because Java generics are invariant. For a read-only use case, consider `List<? extends Animal>` or a suitable generic design.

**Exercise 6: when is `implements` preferable to `extends`?**

**Hint:** When describing a **shared role/capability** but implementations have no natural state/implementation inheritance relationship. For example, shipping strategies can each `implements ShippingPolicy` while retaining separate pricing formulas.

**Exercise 7: a subclass retains method signatures but silently modifies input objects. Is it substitutable?**

**Answer:** No, if the supertype promises not to modify input. Compatible signatures alone are insufficient; side effects are observable parts of a contract.

## Applying these ideas when building a type hierarchy

Define **the contract clients will use first**, then examine each subtype:

1. **Business-level is-a:** is the subtype truly a kind of or a role of the supertype, or does it merely “have” a component of the parent type?
2. **Valid calls:** does the subtype accept every input permitted by the supertype contract?
3. **Results and failures:** does the subtype preserve guarantees about types, meaning, invariants, success conditions, and errors?
4. **Polymorphism:** can client code use the supertype without repeatedly depending on implementation names?
5. **Verification:** can the same contract tests run against all implementations?

An `extends`/`implements` relationship is useful when it allows **one object to replace another in the same role while preserving shared promises**. If special cases or subtype-specific client changes keep accumulating, consider a smaller abstraction, composition, or a different type model that more accurately reflects the business.
