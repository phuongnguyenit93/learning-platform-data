# `sealed` and `non-sealed` Subinterfaces in Java

Starting in Java 17, sealed classes and sealed interfaces are an official feature for restricting which types are permitted to directly extend or implement a supertype. With an interface, this mechanism helps model a known set of branches while allowing intentional extension on branches that require flexibility.

Key distinction: `sealed` restricts direct subtypes; `non-sealed` opens a branch of the hierarchy so that other types can continue to implement or extend that branch.

## 1. Why Can't a Subinterface Be `final`?

A sealed interface can permit both classes that directly implement it and subinterfaces that directly extend it. A permitted **class** must have a `final`, `sealed`, or `non-sealed` policy (a record is implicitly final). A **subinterface** can only choose `sealed` or `non-sealed`: Java does not allow declaring a `final interface`.

A child `sealed interface` closes the list of direct branches at the new level; a child `non-sealed interface` is an open contract for subsequent classes or interfaces. Therefore, using `non-sealed` on a subinterface is a decision about API extensibility, not merely a way to avoid a compilation error.

## 2. How to Declare a `sealed interface`

Use the `permits` clause to list the direct subtypes:

~~~java
sealed interface PaymentMethod
        permits CardPayment, CashPayment, FlexiblePaymentMethod {
    String description();
}
~~~

In the example, only `CardPayment`, `CashPayment`, and `FlexiblePaymentMethod` are permitted to directly implement or extend `PaymentMethod`. This list does not enumerate every type located deeper in the hierarchy.

Each listed type must actually be a direct subtype of the sealed type. If `CardPayment` is a `sealed` class, it must have its own `permits` list. If `FlexiblePaymentMethod` is `non-sealed`, types such as `GiftCardPayment` can implement that interface without needing to appear in `PaymentMethod`'s list.

If the `permits` clause is omitted, the permitted direct subtypes must be declared in the same compilation unit as the sealed type. An explicit declaration is usually easier to read when you need to clearly show the permitted scope.

## 3. Java Rules

- Sealed classes and sealed interfaces were finalized in Java 17. When compiling, use a compatible source level, such as `javac --release 17`.
- The types named in `permits` must be direct subtypes of that sealed class/interface.
- In a named module, the sealed type and its permitted direct subtypes must belong to the same module. In an unnamed module, they must belong to the same package.
- Each direct subtype must define its branch with `final`, `sealed`, or `non-sealed`; records and enums are implicitly final according to the rules of the language.
- `non-sealed` is only valid when that type directly extends or implements a sealed type. Write the hyphen correctly: `non-sealed`.
- The sealed rules govern direct inheritance relationships. A deeper type does not have to appear in the root interface's `permits` clause, as long as it goes through a branch opened with `non-sealed`.

## 4. Complete Runnable Example on Java 17

Save the following content to a file named `SealedInterfaceDemo.java`. All types are in the same file and the same unnamed package to keep the example simple and directly compilable.

~~~java
public class SealedInterfaceDemo {
    public static void main(String[] args) {
        PaymentMethod[] methods = {
            new CashPayment(),
            new CardPayment("4242"),
            new InternationalCardPayment("7777", "VN"),
            new GiftCardPayment("GC-01")
        };

        for (PaymentMethod method : methods) {
            System.out.println(method.description());
        }
    }
}

sealed interface PaymentMethod
        permits CardPayment, CashPayment, FlexiblePaymentMethod {
    String description();
}

sealed class CardPayment implements PaymentMethod
        permits InternationalCardPayment {
    private final String lastFour;

    CardPayment(String lastFour) {
        this.lastFour = lastFour;
    }

    @Override
    public String description() {
        return "Card ****" + lastFour;
    }
}

final class InternationalCardPayment extends CardPayment {
    private final String country;

    InternationalCardPayment(String lastFour, String country) {
        super(lastFour);
        this.country = country;
    }

    @Override
    public String description() {
        return "International " + super.description() + " (" + country + ")";
    }
}

record CashPayment() implements PaymentMethod {
    @Override
    public String description() {
        return "Cash";
    }
}

non-sealed interface FlexiblePaymentMethod extends PaymentMethod {
}

final class GiftCardPayment implements FlexiblePaymentMethod {
    private final String code;

    GiftCardPayment(String code) {
        this.code = code;
    }

    @Override
    public String description() {
        return "Gift card " + code;
    }
}
~~~

Compile and run:

~~~shell
javac --release 17 SealedInterfaceDemo.java
java SealedInterfaceDemo
~~~

Exact stdout output:

~~~text
Cash
Card ****4242
International Card ****7777 (VN)
Gift card GC-01
~~~

## 5. Reading the Example Branch by Branch

- `PaymentMethod` is the root sealed interface. The `permits` clause allows exactly three direct subtypes.
- `CardPayment` is a sealed class, so it creates another level of restriction. It only allows `InternationalCardPayment` to extend it directly.
- `InternationalCardPayment` is declared `final`, so the international card branch stops at this class.
- `CashPayment` is a record. A record is automatically final and satisfies the requirement of a direct subtype.
- `FlexiblePaymentMethod` is declared `non-sealed`. It still must be in `PaymentMethod`'s `permits` list, but its branch is opened. `GiftCardPayment` only needs to implement `FlexiblePaymentMethod`; it does not need to be added to `PaymentMethod`'s `permits`.
- The loop calls the same `description()` method through the `PaymentMethod` reference type. Polymorphism continues to work as usual; sealed does not replace or remove Java's polymorphism mechanism.

The hierarchy can be visualized as follows:

~~~text
PaymentMethod (sealed)
├── CardPayment (sealed)
│   └── InternationalCardPayment (final)
├── CashPayment (record, implicitly final)
└── FlexiblePaymentMethod (non-sealed)
    └── GiftCardPayment (final in the example)
~~~

The diagram shows that `permits` governs the direct edges from a sealed type. `PaymentMethod` does not need to list `InternationalCardPayment` or `GiftCardPayment`, because they do not directly extend or implement `PaymentMethod`.

## 6. When to Use `sealed` and `non-sealed`?

Use `sealed` when the domain has well-defined variants, such as transaction states, result types, or message types in a library. The list of direct subtypes helps readers and the compiler understand the valid branches.

Use `non-sealed` when you want to keep a branch open for extension, for example allowing an application to add multiple custom payment method types. Open only the branch that needs to be opened; if every branch is `non-sealed`, the restriction benefit of a sealed type decreases significantly.

Use `final` on a subclass when you want to lock the branch at that point. If you need another level of control, use `sealed` and declare the list of subtypes for that level. These choices express the extension policy directly in the source code, making the API clearer.

## 7. Relationship with Pattern Matching and `switch`

A sealed hierarchy informs the compiler of the direct branches that can occur. This can support exhaustiveness checking when using pattern matching in `switch`. For example, in Java 21 or later, you can handle the branches of `PaymentMethod` with type patterns corresponding to `CardPayment`, `CashPayment`, and `FlexiblePaymentMethod`; the `CardPayment` pattern also covers its subtypes.

Pattern matching for `switch` was finalized in Java 21. In Java 17, this feature was still in preview and required the corresponding preview options. The runnable example above does not use pattern matching for `switch`, so it only requires standard Java 17.

Being sealed does not automatically make an `if/else` chain exhaustive, nor does it automatically guarantee that every business branch has been handled. The exhaustiveness-checking benefit depends on the expression structure and the Java version in use.

## 8. Common Mistakes

**Forgetting the modifier on a direct subtype.** A regular class implementing a sealed interface without declaring `final`, `sealed`, or `non-sealed` will fail to compile. Choose an explicit extension policy.

**Using `final` on an interface.** Interfaces do not use the `final` modifier; choose `sealed` if you want to continue restricting subinterfaces, or `non-sealed` if you want to open the branch.

**Mistakenly listing an indirect subtype in `permits`.** `permits` only contains directly extending/implementing types. Add the intermediate type to the list and manage deeper branches at that intermediate type.

**Opening a branch while still expecting the entire tree to be restricted.** A `non-sealed` type intentionally allows extension beneath it. If you need to control all subtypes in that branch, consider `sealed` instead of `non-sealed`.

**Placing direct subtypes in the wrong package/module.** Check package boundaries when using an unnamed module, or module boundaries when using a named module.

**Compiling with an older Java version.** Sealed types require Java 17 to be used as an official feature. Check the project's JDK and `--release` option.

## 9. Design Checklist

- Clearly identify which types are permitted to directly extend/implement the root interface.
- For each direct subtype, choose `final`, `sealed`, or `non-sealed` according to the desired extension policy.
- If choosing `sealed` at an intermediate level, declare `permits` for that level.
- Only open a branch with `non-sealed` when you genuinely need to allow external extension.
- Keep direct subtypes in the same module or package according to Java's rules.
- Compile the example with the exact target Java version and check both compilation errors and execution results.

Good design typically uses sealed types to describe valid variants at the API boundary, and then opens only the branches that have a real need for extension. This approach balances hierarchy control with application flexibility.
