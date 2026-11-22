# A Non-sealed Subtype Breaks the Closedness of a Sealed Hierarchy

> **Module:** Java Core Pattern Matching → Sealed hierarchy. The focus is on the effect of the **`non-sealed`** keyword on hierarchy extensibility and proving `switch` exhaustiveness. Sealed/non-sealed inheritance uses Java 17+ rules (JEP 409); pattern matching examples in `switch` use **Java 21+** (JEP 441) so no preview flags are needed.

## Objectives

After completing this lesson, you will be able to:

- Distinguish between **`sealed`**, **`final`**, and **`non-sealed`** on classes/interfaces that are permitted to directly inherit from a sealed type.
- Point out precisely **which part of the inheritance tree remains closed** and **which branch is reopened**; avoid confusing "sealed parent" with "all descendants are fixed".
- Explain why a `non-sealed` subtype can introduce new descendants without modifying the `permits` clause of the sealed root.
- Write an **exhaustive pattern switch** on a sealed root **even when it has a non-sealed branch**, by covering **the entire type of the open branch** instead of only listing a few known subclasses.
- Identify compile-time errors when an open branch is missing, dominance errors when placing a general branch before a specific branch, and risks of depending on the current list of descendants.
- Establish criteria for designing a sealed hierarchy for a closed domain or an extension/plugin point.

## 1. What Does a Sealed Hierarchy Close?

A **sealed class** or **sealed interface** restricts **which types are allowed to directly extend or implement** it. Java 17 allows declaring them explicitly in the `permits` clause:

~~~java
sealed interface Notice permits TextNotice, Extension {
}

record TextNotice(String text) implements Notice {
}

non-sealed class Extension implements Notice {
}
~~~

The snippets above **illustrate type declarations within an appropriate package/module**, not a standalone program. Assume they are in the same file or project structure that satisfies Java's package/module rules.

Explanation:

- `Notice` is the **sealed root**.
- `TextNotice` and `Extension` are the **two direct permitted subtypes** of `Notice`.
- `record TextNotice` is **implicitly final**, so it cannot be subclassed.
- `Extension` is **non-sealed**, allowing other classes to freely `extends Extension` if normal access rules permit.
- A new class **cannot arbitrarily `implements Notice` directly** if it is not listed in `Notice permits ...`.

The following example **intentionally fails to compile**:

~~~java
final class OtherNotice implements Notice {
    // ERROR: OtherNotice is not a direct permitted subtype of Notice.
}
~~~

**What "closed" means:** the compiler can know **the list of direct types** that `Notice` permits, rather than automatically having a complete list of every class at every depth in the inheritance tree.

## 2. Three Ways to Continue a Permitted Branch

A direct permitted subtype of a sealed type must specify the extensibility of its branch:

| Declaration form | Descendants of the branch | Meaning |
| --- | --- | --- |
| `final class End implements Root` | Cannot be subclassed | Closed here |
| `record End(...) implements Root` | Records are implicitly final | Closed here |
| `sealed class Branch extends Root permits Child` | Only direct subtypes permitted by `Branch` | Continues to be closed by level |
| `non-sealed class Extension extends Root` | Other classes can subclass `Extension` according to Java access rules | **Reopens the branch** |
| `non-sealed interface Extension extends Root` | Interfaces can extend and classes can implement `Extension` according to access rules | **Reopens the interface branch** |

Example hierarchy tree:

~~~text
sealed Notice
├── final TextNotice                 (closed leaf)
└── non-sealed Extension            (open branch)
    ├── PartnerExtension            (already exists)
    ├── FutureExtension             (newly added)
    └── ...                          (more can appear)
~~~

`Notice` still only allows **TextNotice** and **Extension** as direct subtypes. `PartnerExtension` and `FutureExtension` **are not direct permitted subtypes of Notice**; they inherit `Notice` indirectly through `Extension`.

**Key takeaway:** A sealed root still has a **closed set of direct branches**, but when a branch is declared `non-sealed`, the sealed root **no longer controls all deeper subclasses** of that branch.

### Why is it named `non-sealed` instead of just omitting `sealed`?

A class that directly inherits from a sealed class/interface must explicitly state how the branch continues to be controlled. If it is a regular class, you must use exactly one of the three modifiers `final`, `sealed`, or `non-sealed`; records are inherently final by language design.

The following snippet **intentionally fails to compile**:

~~~java
sealed interface Root permits Open {
}

// ERROR: Open is a direct permitted subtype but is not final/sealed/non-sealed.
class Open implements Root {
}
~~~

Fix if you want an open branch:

~~~java
non-sealed class Open implements Root {
}
~~~

Once `Open` is `non-sealed`, a **normal subclass** of it does not need to repeat the `non-sealed` keyword:

~~~java
class PlugIn extends Open {
}
~~~

In fact, using `non-sealed` on a class that **only** inherits from a `non-sealed` class (without any sealed direct superclass/interface) is a compile error:

~~~java
non-sealed class PlugIn extends Open { // ERROR: no sealed direct supertype.
}
~~~

Do not think of `non-sealed` as an annotation that must be written on every descendant; it is a modifier at **the boundary between the sealed region and the open region**.

## 3. `permits` Manages **Direct** Relationships, Not Every Grandchild Class

Consider:

~~~java
sealed interface Notice permits TextNotice, Extension {
}

record TextNotice(String text) implements Notice {
}

non-sealed class Extension implements Notice {
}

final class PartnerExtension extends Extension {
}

final class FutureExtension extends Extension {
}
~~~

Valid relationships:

- `TextNotice implements Notice`: direct and permitted.
- `Extension implements Notice`: direct and permitted.
- `PartnerExtension extends Extension`: indirectly becomes a `Notice`, no need to add its name to `Notice permits`.
- `FutureExtension extends Extension`: also valid, even when added later.

Invalid relationships:

- `OtherNotice implements Notice` without being in `permits`.
- `OtherNotice extends TextNotice`: record/final types cannot be subclassed.
- `non-sealed class Foo extends Extension` if `Foo` has no sealed direct supertype: invalid modifier.

If a sealed class has another `sealed` subtype, it can continue using `permits` to control the next level. Openness/closedness is decided **per branch**, not only at the root.

### Module and Package Restrictions

Direct permitted subtypes of a sealed type must satisfy Java's co-location rules:

- If the sealed type is in a **named module**, its direct permitted subtypes must be in the **same module**.
- If using the **unnamed module**, they must be in the **same package**.

This is a constraint on **direct permitted subtypes**. It does not automatically turn all descendants of `non-sealed Extension` into elements of `permits`. Subclassing a `non-sealed` class in another module/package still depends on `public`, constructor accessibility, module exports, and normal Java access rules.

## 4. "Breaking Closedness" Does Not Mean the Root Loses `sealed`

Two statements must be distinguished:

**True:** `Notice` is still `sealed`, and only the two types listed in `permits` have the right to directly implement it.

**Also true:** after permitting a `non-sealed` subtype, the total number of **concrete types at all levels** that can implement `Notice` is **not predetermined**.

For example, the library initially has:

~~~text
Notice
  TextNotice
  Extension
    PartnerExtension
~~~

After an upgrade, without changing `Notice` or `Extension`:

~~~text
Notice
  TextNotice
  Extension
    PartnerExtension
    FutureExtension
    ThirdPartyExtension
~~~

When a new class extends `Extension`, it **is still a `Notice`** through inheritance. The root has no authority to reject the new class individually based on the root's `permits` clause, because the new class does not directly implement the root.

This is precisely what **"a non-sealed subtype breaks closedness"** means: it does not break the root's sealed rule, but rather **reopens a descendant branch**, making it impossible for the system to definitively list all *leaf/concrete subclasses* at design time.

### Can a sub-branch be "re-closed" after `non-sealed`?

Yes. A descendant class of `Extension` can itself be declared `final` or `sealed` under valid Java rules. However, a self-closed sub-branch **does not make `Extension` itself sealed again**; others can still declare *another* subclass of `Extension` if accessibility permits.

In short: **`sealed` on an optional descendant does not restore closedness to the entire `non-sealed` branch above it**.

## 5. Impact on Pattern Matching for `switch` (Java 21)

Java 21 allows `switch` on a sealed type to use **type patterns** and can be proven **exhaustive** by the compiler without needing `default`, provided the set of cases **covers all permitted subtypes**.

Example:

~~~java
static String kind(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case Extension ext -> "extension";
    };
}
~~~

**This is an exhaustive switch expression in Java 21**, even when `Extension` is `non-sealed`.

**Why?**

1. Every non-null `Notice` belongs to one of the two direct branches permitted by `Notice`: `TextNotice` or `Extension` (or their descendants).
2. `case TextNotice text` matches every instance of the `TextNotice` branch (final record).
3. `case Extension ext` matches **`Extension` itself and every subclass**, including future subclasses whose names the sealed root does not know.
4. Therefore, **no `default` is needed** to cover non-null `Notice` values.

**Strictly distinguish these two statements:**

- "A `non-sealed` branch can have **infinitely many subtypes**": true regarding extensibility; there is no fixed list of subtypes.
- "A switch on a sealed root **cannot be exhaustive** if it has a `non-sealed` branch": **false**. A type pattern for **the open branch itself** can cover all of its subclasses.

The correct understanding of exhaustiveness here is **type coverage**, not "having to list the name of every currently existing concrete class".

## 6. Mistake: Listing Only Currently Known Descendants of the Open Branch

Suppose `PartnerExtension extends Extension` already exists. The following code **intentionally fails to compile**:

~~~java
static String broken(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case PartnerExtension partner -> "partner";
        // ERROR: does not cover Extension and its other subclasses.
    };
}
~~~

The compiler cannot rely on the list of currently known `PartnerExtension` classes to conclude that **all** `Extension` instances have been handled. `Extension` can be instantiated directly (if not abstract), and other classes can extend it. Even if `Extension` is `abstract non-sealed`, the possibility of new subclasses appearing means listing a few concrete subclasses is **not** enough to prove exhaustiveness.

**The right fix when you want to handle partner specially:**

~~~java
static String corrected(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case PartnerExtension partner -> "partner";
        case Extension ext -> "another extension";
    };
}
~~~

- `case PartnerExtension` handles a specific known subtype.
- `case Extension` **catches the rest of the entire open branch**, including `Extension` and any unlisted subtypes.
- The compiler knows the two root branches `TextNotice`/`Extension` are covered, so the switch expression is exhaustive **without needing `default`**.

### Why Does Case Order Matter?

If you write:

~~~java
case Extension ext -> "extension";
case PartnerExtension partner -> "partner"; // ERROR: dominated.
~~~

then every `PartnerExtension` is already caught by the preceding `case Extension`. Java 21 reports the second label as **dominated**. Put **specific subtypes first**, and the **general non-sealed branch after**.

This connects directly to the **Sealed hierarchy** topic: when an open branch is used in a pattern switch, do not write cases based solely on currently existing concrete classes, and do not place a pattern covering the whole branch too early if you still want to classify special subtypes.

### Should You Use `default` to "Fix" a Missing Branch Error?

You can add `default -> ...` to make a switch exhaustive. But consider what it means:

~~~java
static String permissive(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case PartnerExtension partner -> "partner";
        default -> "other";
    };
}
~~~

Here `default` covers unmatched non-null objects, but the `default` label **does not bind a variable of type `Extension`**. If all remaining values *by domain contract* are indeed `Extension`, using `case Extension ext` is usually clearer in intent, gives a precise static type, and clearly reflects the structure of the sealed hierarchy.

However, `default` is a valid choice when a generic fallback is the intended business behavior. What to avoid is assuming that having `default` means you have **understood and individually handled** every future subclass.

## 7. The Downside of an Exhaustive Switch When an Open Branch Can Grow

Suppose today:

~~~java
return switch (notice) {
    case TextNotice t -> "text";
    case PartnerExtension p -> "partner";
    case Extension e -> "unknown extension";
};
~~~

Tomorrow a library adds:

~~~java
final class FutureExtension extends Extension {
}
~~~

The switch still **compiles** when the client is recompiled, because `case Extension e` already covers all descendants of `Extension`. When receiving `FutureExtension`, the program returns `"unknown extension"`.

This is both an **advantage** and a **risk**:

- **Advantage:** The API has an extension point that does not require updating every consumer whenever a new plugin/subclass is added.
- **Risk:** A new subclass with different business semantics can silently fall into the general branch. The compiler **cannot force you to write a separate branch** for each future descendant of a `non-sealed` type.

If the domain requires **every variant to be handled separately**, you should design all branches as `final` or `sealed` continuing with `permits` — i.e., a hierarchy **closed all the way down to the leaves that need to be distinguished**.

If the domain is **plugin/extensibility**, a `non-sealed` branch and a general case are intentional design. In that case, handling unknown plugins requires a sufficiently clear **interface/abstract method contract**, rather than relying solely on a compile-time class list.

### Design Comparison

| Design | What can appear later? | How is an exhaustive switch usually written? |
| --- | --- | --- |
| `sealed Root permits A,B`; both `A`/`B` are `final` | No further subclasses of `A`/`B` | `case A`, `case B` |
| `sealed Root permits A,B`; `B` is also `sealed`, only permitting `C,D` | Only permitted descendants at each level | Can cover `A,C,D` or use an appropriate general pattern |
| `sealed Root permits A,B`; `B` is `non-sealed` | New subclasses of `B` can appear | `case A` and `case B` (covers all subclasses of `B`) |
| Only `case A` and a few known subclasses of `B` | `B` or other subclasses can still exist | **Not** exhaustive without a branch covering `B`/default |

**Good design is not always "close everything"**. The crux is whether the business domain contract allows others to define new variants.

## 8. Java 17: Checking sealed/non-sealed; Java 21: Checking Exhaustive Switch

`sealed` and `non-sealed` became standard in **Java 17**. You can use `instanceof` in Java 17 to branch by type pattern; it enforces which subtypes can directly implement the sealed root.

~~~java
static String classify17(Notice notice) {
    if (notice instanceof TextNotice text) {
        return "text";
    }
    if (notice instanceof Extension extension) {
        return "extension";
    }
    throw new IllegalStateException("Unexpected Notice");
}
~~~

This is an **illustrative method** inside a class with the appropriately declared types, and it differs from Java 21 pattern `switch`:

- `instanceof` checks each condition at runtime.
- The Java 17 compiler **does not check exhaustiveness** of an `if` chain the way a Java 21 pattern switch expression does.
- The final `throw` is the code author's decision, not proof that the compiler has accounted for every subtype.

**Java 21** is what provides the standard syntax:

~~~java
return switch (notice) {
    case TextNotice text -> "text";
    case Extension extension -> "extension";
};
~~~

The Java 21 compiler can prove exhaustiveness based on the sealed root structure and type coverage without needing `default`.

**Version note:** Pattern matching for `switch` in JDKs 17–20 was a preview feature with rules/syntax changing across preview iterations. Do not assume a regular Java 17 compile command is sufficient for Java 21 pattern switch examples.

## 9. Complete Runnable Program (Java 21)

Save the file **`OpenBranchDemo.java`**:

~~~java
public class OpenBranchDemo {

    sealed interface Notice permits TextNotice, Extension {
    }

    // Record is implicitly final; this is a closed branch.
    record TextNotice(String text) implements Notice {
    }

    // Open branch: other classes can extend Extension.
    static non-sealed class Extension implements Notice {
        private final String source;

        Extension(String source) {
            this.source = source;
        }

        String source() {
            return source;
        }
    }

    static final class PartnerExtension extends Extension {
        PartnerExtension(String source) {
            super(source);
        }
    }

    static final class FutureExtension extends Extension {
        FutureExtension(String source) {
            super(source);
        }
    }

    // Exhaustive without default:
    // case Extension covers both current and future subtypes.
    static String classify(Notice notice) {
        return switch (notice) {
            case TextNotice text -> "text:" + text.text();
            case PartnerExtension partner ->
                    "partner:" + partner.source();
            case Extension extension ->
                    "extension:" + extension.source();
        };
    }

    static String broad(Notice notice) {
        return switch (notice) {
            case TextNotice text -> "text";
            case Extension extension -> "any extension";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new TextNotice("hello")));
        System.out.println(classify(new PartnerExtension("Acme")));
        System.out.println(classify(new Extension("legacy")));
        System.out.println(classify(new FutureExtension("future")));
        System.out.println(broad(new FutureExtension("future")));

        try {
            classify(null);
        } catch (NullPointerException ex) {
            System.out.println("null:NPE");
        }
    }
}
~~~

Compile and run with **JDK 21 or later**:

~~~bash
javac --release 21 OpenBranchDemo.java
java OpenBranchDemo
~~~

**Exact stdout:**

~~~text
text:hello
partner:Acme
extension:legacy
extension:future
any extension
null:NPE
~~~

Explanation:

1. `TextNotice("hello")` matches the direct permitted record branch ⇒ `text:hello`.
2. `PartnerExtension` matches the specific case placed before the general case ⇒ `partner:Acme`.
3. An `Extension` instance itself matches `case Extension` ⇒ `extension:legacy`.
4. `FutureExtension` is not named in the root's `permits` and has no dedicated case, yet **still matches `case Extension`** ⇒ `extension:future`.
5. `broad` has exactly two cases corresponding to the two direct permitted branches, so it is exhaustive. A subclass of `Extension` returns `any extension`.
6. `null` does not match the `TextNotice`/`Extension` type patterns; without `case null`, the switch throws `NullPointerException`. The `catch` block in `main` simply converts the exception into the stdout line shown.

**Highlight:** The root has only **two direct permitted subtypes**, yet the application can have more than two **concrete subtypes**; every subtype under the non-sealed branch is handled in `case Extension`.

## 10. Programs Rejected by the Compiler — and the Exact Reasons

### Error A. Failing to Cover the Non-sealed Branch

The following snippet **intentionally fails to compile**, placed in a class that declares `Notice`, `TextNotice`, and `PartnerExtension`:

~~~java
static String broken(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case PartnerExtension partner -> "partner";
        // ERROR: Extension and other subclasses remain uncovered.
    };
}
~~~

Java 21's error message typically looks like:

~~~text
the switch expression does not cover all possible input values
~~~

**Fix:** add `case Extension extension -> ...` (after `case PartnerExtension`) or an intentional `default`.

### Error B. General Branch Hiding a Specific Branch

~~~java
static String badOrder(Notice notice) {
    return switch (notice) {
        case TextNotice text -> "text";
        case Extension extension -> "all extensions";
        case PartnerExtension partner -> "partner"; // ERROR: dominated.
    };
}
~~~

Every `PartnerExtension` is an `Extension`. The compiler rejects the latter branch because it is completely dominated.

### Error C. Class Directly Implementing the Root Without Being Permitted

~~~java
final class Unauthorized implements Notice {
    // ERROR: not directly permitted by Notice.
}
~~~

**Fix:** if you truly want to add a direct variant, the owner of `Notice` must update `permits` and check related exhaustive switches. If the goal is a plugin, extend `Extension` instead of implementing the sealed root directly.

### Error D. Missing Modifier on a Direct Permitted Subtype

~~~java
sealed interface Root permits Open { }

class Open implements Root { // ERROR.
}
~~~

**Fix:** `final class Open`, `sealed class Open permits ...`, or `non-sealed class Open` depending on the design intent.

### Error E. Using `non-sealed` Where There Is No Sealed Direct Supertype

~~~java
non-sealed class Child extends Extension { // ERROR if Extension is a direct non-sealed superclass.
}
~~~

**Fix:** usually you only need `class Child extends Extension` or `final class Child extends Extension`. If you want `Child` to establish a new closed hierarchy, consider declaring `Child` as `sealed` with `permits` according to Java rules.

### Error F. Assuming `default` or Null Is a Valid Constant of the Sealed Root

~~~java
return switch (notice) {
    case TextNotice text -> "text";
    case Extension extension -> "extension";
};
~~~

The code above is exhaustive for **non-null values**. `null` can still throw `NullPointerException`. If the contract needs to handle null, you can write:

~~~java
return switch (notice) {
    case null -> "missing";
    case TextNotice text -> "text";
    case Extension extension -> "extension";
};
~~~

`case null` is a special label, not a new subtype in `permits`.

## 11. Reflection Cannot List All Descendants of an Open Branch

Java provides introspection for sealed types:

~~~java
System.out.println(Notice.class.isSealed()); // true

Class<?>[] directTypes = Notice.class.getPermittedSubclasses();
System.out.println(directTypes.length);       // 2
~~~

This is an illustrative snippet in the context of `OpenBranchDemo` having two direct permitted types of `Notice`. `getPermittedSubclasses()` reflects the **direct permitted subclasses/subinterfaces of the sealed type**; it does not automatically find all indirect subclasses.

With `Extension` being `non-sealed`:

~~~java
System.out.println(Extension.class.isSealed()); // false
System.out.println(
        Extension.class.getPermittedSubclasses() == null
); // true — type is not sealed.
~~~

Do not use `Notice.class.getPermittedSubclasses()` as a guaranteed "registry" listing every plugin/concrete leaf: `PartnerExtension` and `FutureExtension` are not direct permitted subtypes of the root, so they are not in the direct list.

If a plugin system needs to discover all actually available implementations, use a registration/discovery mechanism suited to your architecture (such as `ServiceLoader` in appropriate scenarios) rather than inferring solely from `permits`. That is a plugin management problem, **separate** from Java's sealed rules.

## 12. Common Misconceptions

| Statement | True/False | Explanation |
| --- | --- | --- |
| "If the root is `sealed`, no subclasses can be added at any level." | **False** | A `non-sealed` branch allows adding indirect subclasses |
| "`non-sealed` disables the root's `permits`." | **False** | The root still restricts direct subtypes |
| "A subclass of `non-sealed` must be added to the root's `permits`." | **False** | It does not directly extend/implement the root |
| "Whenever there is a `non-sealed` branch, `switch` cannot be exhaustive." | **False** | `case Extension` covers the entire open branch |
| "Listing all currently visible concrete subclasses is enough." | **False** | The branch remains open for future subclasses and may be instantiable |
| "`case PartnerExtension` placed after `case Extension` is fine." | **False** | Dominance error because the subtype is already caught by the parent branch |
| "An exhaustive switch means the compiler will remind you to handle every future plugin." | **False** | The open branch pattern can accept new plugins without needing a separate case |
| "`non-sealed` must be written on every descendant class." | **False** | This modifier is only valid if there is a corresponding sealed direct supertype |
| "Every direct subtype of a sealed type must be `final`." | **False** | It can be `sealed` or `non-sealed`; records are implicitly final |
| "Reflection `getPermittedSubclasses` lists grandchildren of a non-sealed type too." | **False** | It only returns the list of direct permitted types |
| "`default` automatically handles `null` in a pattern switch." | **False** | Java 21 requires `case null` if you want to handle null directly |

### A Sound Mental Model

Separate **two questions**:

1. "Which types are permitted **directly** under the root?" — `permits` answers this.
2. "Which runtime objects can belong to **the entire subtree** of each branch?" — `final`, `sealed`, and `non-sealed` determine this.

If a branch is `non-sealed`, the second answer is **open**, even though the first answer remains fixed. A type pattern for **the permitted root branch** can still cover that entire subtree.

## 13. Practice Exercises

**Question 1.** Suppose:

~~~java
sealed interface Shape permits Circle, Polygon { }
record Circle(double radius) implements Shape { }
non-sealed class Polygon implements Shape { }
final class Triangle extends Polygon { }
~~~

What are the direct permitted subtypes of `Shape`? Does `Triangle` need to be in `permits`?

**Question 2.** Can you add `final class Rectangle extends Polygon` without modifying `Shape`? Why?

**Question 3.** Consider `switch (shape)` on a selector of static type `Shape`:

~~~java
return switch (shape) {
    case Circle c -> "circle";
    case Triangle t -> "triangle";
};
~~~

Does Java 21 consider this switch expression exhaustive? Which branch should be added?

**Question 4.** If you add `case Polygon p -> "polygon";` **before** `case Triangle t`, will the compiler accept it? How do you fix it?

**Question 5.** With:

~~~java
return switch (shape) {
    case Circle c -> "circle";
    case Triangle t -> "triangle";
    case Polygon p -> "polygon";
};
~~~

After adding `Rectangle extends Polygon`, do you need to modify the switch for Java 21 to consider it exhaustive? Which branch does `Rectangle` enter?

**Question 6.** Write two ways to address the risk of missing a new subtype: one for a **closed** domain, and one for **plugin/open extension**.

**Question 7.** Why is `final class Extra implements Shape` invalid if `Shape` only permits `Circle` and `Polygon`, whereas `final class Extra extends Polygon` is valid?

**Question 8.** A class is directly permitted but has none of the modifiers `final`, `sealed`, or `non-sealed` (and is not a record). What will the compiler do?

**Question 9.** Once `Polygon` is `non-sealed`, can you declare `non-sealed class Triangle extends Polygon` if `Triangle` has no other sealed direct supertype?

**Question 10.** What does `Shape.class.getPermittedSubclasses()` return? Is it sufficient to list all subclasses/plugins of `Polygon`?

**Question 11.** Does `case Polygon p` match `null`? If you want to return `"missing"` for null, what do you add?

**Question 12.** Why is the statement "compiler exhaustiveness means every concrete subtype at every level is handled individually" false in a sealed tree containing a `non-sealed` branch?

### Reference Answers

1. **`Circle` and `Polygon`**. `Triangle` does not need to be in `permits` because it inherits `Shape` indirectly through `Polygon`.
2. **Yes**, if normal visibility/constructor/module rules permit. `Polygon` is `non-sealed`.
3. **No**. `Polygon` and other subclasses remain. Add `case Polygon p -> ...` after the `Triangle` branch, or an intentional `default`.
4. **No**: `Triangle` is dominated by `Polygon`. Place `Triangle` before `Polygon`.
5. **Still exhaustive**. `Rectangle` will enter `case Polygon p`.
6. Closed domain: use `final` or `sealed` branches continuing with `permits` so the compiler has a finite type tree. Plugin domain: intentionally use `non-sealed`, define a common API, and handle `case Polygon p`/fallback with a clear contract.
7. `Extra implements Shape` is an unpermitted direct subtype ⇒ error. `Extra extends Polygon` goes through the open branch ⇒ valid.
8. **Compile error**: a direct permitted subtype must explicitly specify its inheritance continuation strategy, except for cases like implicitly final records.
9. **No**: the `non-sealed` modifier requires a sealed direct supertype, not merely a more distant sealed ancestor.
10. The list of **direct permitted types** of `Shape`; it does not list all descendants of `Polygon`.
11. **No**. Add `case null -> "missing"` when null is an accepted input value.
12. Because `case Polygon p` matches every current and future subtype of `Polygon`, making the switch exhaustive in terms of **type coverage**, without individually classifying each concrete subtype.

## Official References

- [Oracle Java 21 — Sealed Classes](https://docs.oracle.com/en/java/javase/21/language/sealed-classes-and-interfaces.html): `permits`, `final`/`sealed`/`non-sealed` rules, module/package placement.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): design goals of sealed classes/interfaces, opening branches with `non-sealed`.
- [JLS 21 — `8.1.1.2 Sealed, Non-sealed, and Final Classes`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): declaration conditions and inheritance relationships.
- [JLS 21 — `9.1.1.4 Sealed and Non-sealed Interfaces`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4): opening/closing interface branches.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): type coverage, dominance, and exhaustive switch with sealed selectors.
- [JLS 21 — `14.11.1.1 Exhaustive Switch Blocks`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.1): compiler rules for proving exhaustiveness.
- [JLS 21 — `15.28 Switch Expressions`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expressions and runtime handling.
- [Java SE 21 API — Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `isSealed()` and `getPermittedSubclasses()`.
