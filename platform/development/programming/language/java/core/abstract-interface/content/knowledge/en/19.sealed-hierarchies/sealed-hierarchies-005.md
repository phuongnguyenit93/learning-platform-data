# `final`, `sealed`, and `non-sealed` Modifiers of Direct Subclasses

In Java, a type declared with `sealed` controls which classes or interfaces are permitted to directly extend or implement it. Every direct subtype must specify its subsequent inheritance policy using `final`, `sealed`, or `non-sealed` (except for types that are already implicitly `final`, such as records).

These three modifiers answer three different questions: does the inheritance branch end here, does it continue while still remaining restricted, or is it opened for external code to extend freely?

## 1. Context: Sealed Types and Inheritance Branches

Sealed classes and sealed interfaces became an official feature in Java 17. They are useful when a domain model has a controlled set of subtypes, such as result types, geometric shapes, messages, or payment methods.

For example, a `Payment` interface might permit exactly three direct subtypes: `CardPayment`, `CashPayment`, and `CustomPayment`. Java requires each of these branches to declare how it can be extended further.

- `final`: the branch ends at this type.
- `sealed`: the branch continues, but only permitted types can directly subtype this type.
- `non-sealed`: the branch is reopened; other classes can extend this type without needing to be listed in the `permits` list of the sealed ancestor.

These modifiers apply to class or interface declarations. They are not method modifiers, and they do not by themselves determine whether an object is immutable.

## 2. How Do the Three Modifiers Differ?

| Modifier on direct subtype | Meaning | Further inheritance |
| --- | --- | --- |
| `final` | This type is a leaf of the inheritance branch. | No class may extend this class; a `final` interface is invalid. |
| `sealed` | This type continues to restrict its own direct subtypes. | Subsequent direct subtypes must be declared in `permits`, or inferred by the compiler when eligible. |
| `non-sealed` | This type explicitly removes the sealed restriction for its branch. | Classes can extend this type without needing to be in the `permits` list of the original sealed type. |

### `final`: Closing the Inheritance Branch

When a class directly extends a sealed class or directly implements a sealed interface and is declared `final`, no subclasses can be created from it.

```java
sealed interface Payment permits CardPayment {}

final class CardPayment implements Payment {}
```

In this example, `CardPayment` is a permitted type of `Payment`, and the `CardPayment` branch ends here. A declaration such as `class PremiumCardPayment extends CardPayment {}` will not compile because `CardPayment` is `final`.

Use `final` when the subtype represents a specific case that the design does not allow to be extended further.

### `sealed`: Continuing to Restrict a Branch

A subtype can itself be sealed. When it is, it becomes a new sealed type with its own list of direct subtypes.

```java
sealed interface Payment permits CashPayment {}

sealed class CashPayment implements Payment
        permits ExactCashPayment {}

final class ExactCashPayment extends CashPayment {}
```

`CashPayment` is a type permitted by `Payment`, while also restricting which classes can extend it. In the example, only `ExactCashPayment` is permitted to directly extend `CashPayment`. Another class that declares `extends CashPayment` without being listed will be rejected at compile time.

Use `sealed` when you want a multi-level hierarchy where each level must still follow a controlled list of subtypes.

### `non-sealed`: Reopening a Branch

`non-sealed` allows a direct subtype of a sealed type to become a normal extension point.

```java
sealed interface Payment permits CustomPayment {}

non-sealed class CustomPayment implements Payment {}

class BrandedPayment extends CustomPayment {}
class PartnerPayment extends CustomPayment {}
```

`CustomPayment` must still be listed in `Payment`'s `permits` list, because it is a direct implementing type. Then, `BrandedPayment` and `PartnerPayment` can extend `CustomPayment` without needing to be added to `Payment`'s `permits` list.

Use `non-sealed` when you want to control the direct subtypes of an abstraction, while still allowing libraries, plugins, or application code to extend a specific branch.

Note that `non-sealed` does not mean that type can be added arbitrarily to the sealed type's direct list. The `non-sealed` type itself must still be a permitted direct subtype.

## 3. A Compilable and Runnable Java 17+ Example

Save the following content to the file `SealedHierarchyDemo.java`. All types are in the same compilation unit and the default package so that the example stays focused on the modifiers.

```java
public class SealedHierarchyDemo {
    public static void main(String[] args) {
        Payment[] payments = {
            new CardPayment(),
            new ExactCashPayment(),
            new CustomPayment(),
            new BrandedPayment()
        };

        for (Payment payment : payments) {
            System.out.println(payment.label());
        }
    }
}

sealed interface Payment
        permits CardPayment, CashPayment, CustomPayment {
    String label();
}

final class CardPayment implements Payment {
    @Override
    public String label() {
        return "card";
    }
}

sealed class CashPayment implements Payment
        permits ExactCashPayment {
    @Override
    public String label() {
        return "cash";
    }
}

final class ExactCashPayment extends CashPayment {}

non-sealed class CustomPayment implements Payment {
    @Override
    public String label() {
        return "custom";
    }
}

final class BrandedPayment extends CustomPayment {
    @Override
    public String label() {
        return "branded";
    }
}
```

Compile and run using JDK 17 or later:

```text
javac --release 17 SealedHierarchyDemo.java
java SealedHierarchyDemo
```

Standard output (stdout):

```text
card
cash
custom
branded
```

The example shows that the modifiers do not replace polymorphism. The array has element type `Payment`, yet each object still executes the `label()` implementation of its actual class. The modifiers control the inheritance structure at compile time.

## 4. Reading the Hierarchy Structure in the Example

```text
Payment (sealed)
├── CardPayment (final)
├── CashPayment (sealed)
│   └── ExactCashPayment (final)
└── CustomPayment (non-sealed)
    └── BrandedPayment (final)
```

- `CardPayment` closes its branch with `final`.
- `CashPayment` creates an additional controlled level with `sealed`; the permitted list for this level contains only `ExactCashPayment`.
- `CustomPayment` is an open branch. Therefore, `BrandedPayment` can extend it even though it does not appear in `Payment`'s `permits` list.
- `BrandedPayment` is in turn declared `final`, so this branch ends at that class.

The modifiers are evaluated based on direct inheritance relationships. A class deeper inside a `non-sealed` branch does not need to declare `final`, `sealed`, or `non-sealed` just because a distant ancestor is sealed. These rules apply when a class directly extends or implements a sealed type.

## 5. Reading `permits` Branch by Branch

In the main example, `Payment` lists the direct implementing types `CardPayment`, `CashPayment`, and `CustomPayment`; `CashPayment` itself permits `ExactCashPayment`. `BrandedPayment` only extends `CustomPayment`, so it does not appear in `Payment`'s `permits` list. To add a direct variant, you must explicitly modify the list at the right level.

The `permits` clause can be omitted if all direct subtypes of a sealed type are declared in the same compilation unit so the compiler can infer them automatically; it does not look for types in other files. A permitted subtype must be in the same named module as the sealed type, or in the same package if in an unnamed module. At the same time, the `extends` / `implements` relationship must be valid; a name appearing in `permits` does not by itself create an inheritance relationship.

## 6. Common Compilation Errors

The snippets below are intentionally written incorrectly to illustrate the rules; do not add them to the working sample program.

**Extending a `final` class:**

```java
class AnotherCardPayment extends CardPayment {}
```

Error: cannot extend `CardPayment` because this class is `final`.

**Extending a sealed class without being permitted:**

```java
class OtherCashPayment extends CashPayment {}
```

Error: `CashPayment` only permits `ExactCashPayment` as a direct subtype. To have a new direct subtype, you must change the authoritative sealed declaration for that branch.

**Implementing a sealed interface without being in the permitted list:**

```java
class UnknownPayment implements Payment {}
```

Error: `UnknownPayment` is not listed in `Payment`'s `permits` list. Declaring `implements Payment` does not automatically register a new type.

**Using `non-sealed` when the direct supertype is not sealed:**

```java
non-sealed class OrdinaryExtension {}
```

Error: `non-sealed` is only valid for a direct subclass of a sealed class or a direct implementing type of a sealed interface. It is not a general declaration for an ordinary open class.

**Confusing `sealed` with `final`:**

A type cannot be both `sealed` and `final` at the same time: `sealed` permits a set of subtypes, whereas `final` forbids all subclasses. Similarly, `final` and `abstract` cannot be applied together to a class because their meanings conflict.

**Forgetting the policy of a sealed subclass:**

If a direct subtype does not close itself with `final`, it must either continue controlling the hierarchy with `sealed` or explicitly open it with `non-sealed`. A sealed subclass also needs its own list of permitted subtypes, unless that list can be validly inferred from the same compilation unit.

## 7. Special Cases to Remember

- **An abstract class can still be sealed.** For example, `abstract sealed class Node permits Leaf, Branch {}` can model a branch where `Node` itself cannot be instantiated directly. The subtypes must still follow the rules of a sealed type.
- **Records are inherently final.** A record can be a permitted type implementing a sealed interface without adding the `final` modifier, because a record cannot be extended like a normal class.
- **Interfaces can also be sealed.** The direct types listed can be implementing classes or subinterfaces. A sealed subinterface can restrict the branch further; a `non-sealed` subinterface opens the branch for other interfaces to extend.
- **`non-sealed` does not erase the ancestor's policy.** It only opens extension from the type declared `non-sealed` downward. The set of direct subtypes of the original sealed type remains the set declared in `permits`.
- **Sealing does not make an object immutable.** Mutable state, member access permissions, method overriding capability, and initialization rules still follow the corresponding Java rules.
- **Sealed types are useful for exhaustiveness checking.** Newer Java versions can use a sealed hierarchy together with pattern matching in `switch` to check that the cases have been handled. Pattern switch syntax has its own version and language requirements; it is not needed to compile the Java 17 example above.

## 8. How to Choose a Modifier

Choose the modifier according to the policy that the API wants to expose:

1. Use `final` when the type represents a specific case and must not be extended.
2. Use `sealed` when the branch has known variants, yet still needs another controlled level of classification.
3. Use `non-sealed` when you want to keep an extension point for API consumers or for code in another module, while the direct subtypes of the root abstraction remain controlled.

For example, a library can permit core payment types such as `CardPayment` and `CashPayment`, while also providing `CustomPayment` as an extension point. In doing so, the library maintains a clear boundary between the core cases and consumer-provided implementations.

Do not choose `non-sealed` just to make a compilation error disappear. Determine whether arbitrary extension is part of the API contract. Opening a branch affects which types applications can define later and the ability to perform exhaustive case analysis in code that uses the hierarchy.

## 9. Quick Troubleshooting Table

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| A class cannot extend a subtype | The parent type is `final`. | Extend a branch designed for extension; only change the modifier if the design policy allows it. |
| A new class cannot directly implement a sealed interface | The class is not yet listed in `permits`. | Add it to the controlled list if this is an intentional API change. |
| A sealed subclass reports an error about its subtypes | The `permits` list for that level is missing or invalid. | Check the direct relationships and declare the permitted list on the sealed subclass itself. |
| `non-sealed` is rejected | The direct supertype is not a sealed type. | Use `non-sealed` only on a direct branch of a sealed class/interface. |
| A type is permitted but still fails to compile | Incorrect `extends`/`implements` relationship, a module/package mismatch under the rules, or an invalid modifier declaration. | Thoroughly check the inheritance relationship, package/module placement, and the subtype's modifier. |

## 10. Checklist When Reading or Designing a Hierarchy

- Identify the root sealed class or sealed interface.
- Read `permits` to find the permitted direct subtypes; if absent, check whether they can be inferred from the same compilation unit.
- For each direct subtype, determine whether it is `final`, `sealed`, or `non-sealed` (or an implicitly `final` type such as a record).
- If the subtype is sealed, continue reading its own `permits` list.
- If the subtype is `non-sealed`, treat it as the boundary where the branch begins to extend freely.
- Check the package/module rules and run the compiler to confirm the actual declarations.
- Keep examples minimal, with accurate file names, clear compilation commands, and verifiable output.

When reading a sealed hierarchy, follow each direct edge of the inheritance tree. `final` ends the branch, `sealed` creates another controlled level, and `non-sealed` opens that branch for new subtypes.
