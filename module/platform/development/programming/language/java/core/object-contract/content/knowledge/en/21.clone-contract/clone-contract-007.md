# Clone convention: distinct reference, same class, and usually equal values in Java

When we say an object is **cloned** in Java, we usually expect a **new object** of the same runtime type, carrying initial data matching the original object. The `Object.clone()` contract describes three prominent conventions:

~~~java
x.clone() != x
x.clone().getClass() == x.getClass()
x.clone().equals(x)
~~~

The three lines above are **expressions illustrating conventions**, which can only be called directly if the `clone()` method has been provided by the class with an appropriate access scope. They are **not three absolute guarantees of every method named `clone`**. The JavaDoc of `Object.clone()` states these are things that should hold *by convention*, and there can be exceptions, especially the third expression.

Therefore, distinguish: **copying an object** is different from **copying the entire referenced object graph**, and **having the same data** does not always mean `equals() == true`.

## 1. What do the three conventions mean?

| Convention | Meaning | Limitation to remember |
|---|---|---|
| `clone != original` | Clone is usually a **new instance**, with a different reference from the original object | A custom-written clone method can violate the convention if it returns `this` |
| `clone.getClass() == original.getClass()` | The copy usually has **the exact same runtime class** | True for the standard copying path via `super.clone()`; a custom override can return another class |
| `clone.equals(original)` | The copy usually equals the original **by the class's equality definition** | Not guaranteed if the class does not override `equals()` or if clone intentionally changes a compared field |

For example, if class `Customer` has `id = 7`, the clone also has `id = 7`, and the class defines `equals()` by `id`, then `customer.clone().equals(customer)` is usually `true`. If that same class inherits `Object.equals()` by **identity**, two distinct instances will yield `false` despite having identical fields.

Do not call the three expressions above **mandatory verification laws** for all Java classes. They are **design conventions and useful testing criteria** when an API promises to provide a copy in the standard sense.

## 2. How do `Object.clone()` and `Cloneable` work?

`Object` declares the method **`protected Object clone() throws CloneNotSupportedException`**. Because it is `protected`, external code cannot arbitrarily write `someObject.clone()` if the class does not expose an appropriate method publicly.

`java.lang.Cloneable` is a **marker interface**: it **does not declare a `clone()` method**. When invoking the `Object.clone()` mechanism on an instance of a class not implementing `Cloneable` (and not an array), the default mechanism throws `CloneNotSupportedException`. Writing `implements Cloneable` alone **does not automatically create a `public clone()` method** for external callers.

Common implementation pattern:

~~~java
final class Item implements Cloneable {
    private final int id;

    Item(int id) {
        this.id = id;
    }

    @Override
    public Item clone() {
        try {
            return (Item) super.clone();
        } catch (CloneNotSupportedException e) {
            throw new AssertionError(e);
        }
    }
}
~~~

This is a compilable class declaration without `main`. Because `Item` is `final` and implements `Cloneable`, the `super.clone()` call under this design does not raise `CloneNotSupportedException`; wrapping the error into `AssertionError` is an option expressing that invariant. The class uses a **covariant return type** (`Item` instead of `Object`), while widening access level to `public`.

The `super.clone()` mechanism creates a new object with fields copied from the current object; it **does not call the constructor of the cloned class** the way `new Item(...)` normally does. However, calling `super.clone()` also **does not automatically deep-copy** objects held in reference fields.

## 3. Distinct reference: the clone is a new object

With a convention-compliant implementation, two variables can contain identical information without pointing to the same instance:

~~~java
Item original = new Item(7);
Item copied = original.clone();

System.out.println(original == copied); // false
System.out.println(original != copied); // true
System.out.println(original.getClass() == copied.getClass()); // true
~~~

This is a snippet using the `Item` class above and can be placed inside `main`. `==` on references checks **identity**, not data. If two variables point to the same instance, modifying state through one variable affects the same object seen by the other. If they are different instances, reassigning a direct field of one copy does not automatically change the direct field of the other.

However, distinguish **two different original/clone objects** from **child objects referenced by them**: both the original and the clone can still hold references to the same `List`, array, or mutable object. That is a *shallow copy*, analyzed below.

An erroneous override could write `return this;` and cause `clone != original` to fail. The Java compiler does not block that kind of implementation automatically; the responsibility to uphold the contract belongs to the API author.

## 4. Same runtime class: `getClass()`, not variable type name

With standard `Object.clone()`, the created object has **the same runtime class** as the object receiving the call. If a variable is declared with a superclass type yet points to a subclass instance, cloning through an inherited method can return an object with the runtime class **of the subclass**.

~~~java
Object a = new Item(9);
Item b = ((Item) a).clone();

System.out.println(a.getClass() == b.getClass()); // true
~~~

In this example variable `a` is declared `Object`, while the actual instance is `Item`. The same-class convention checks `getClass()` of the **runtime object**, not the declared type name of the variable, nor merely `instanceof`: `instanceof` accepts subclasses as well, whereas comparing `getClass() == getClass()` requires the exact runtime class.

When a class uses inheritance, `super.clone()` usually preserves the runtime type because clone creates a new object of the receiver's actual type. However, subclass implementations must be careful to copy mutable fields added by them; relying solely on `super.clone()` can leave shared references behind.

A custom-written method named `clone` that constructs `new Base(...)` when the receiver is `Child` can violate the same-class convention. This is one reason not to assume every override adheres to the contract solely from the method name.

## 5. Usually equal values: why can `equals()` still be false?

Separate **copied state** from **`equals()` rules**:

- If a class defines `equals()` by value fields and clone preserves corresponding fields, `clone.equals(original)` is usually `true`.
- If a class **does not override `equals()`**, the default of `Object.equals()` is identity. Since the clone is a new instance, `clone.equals(original)` is `false`.
- If `equals()` depends on data that clone intentionally changes (for example, resetting an identifier), `equals()` can be `false` even when the copy is valid for business logic.
- If a class defines `equals()` violating symmetry/transitivity or has mutable state changing during comparison, results are also unreliable. This is an equality design problem, not solely a clone problem.

Example of a class that has clone yet still uses identity equality:

~~~java
final class IdentityItem implements Cloneable {
    int value;

    IdentityItem(int value) {
        this.value = value;
    }

    @Override
    public IdentityItem clone() {
        try {
            return (IdentityItem) super.clone();
        } catch (CloneNotSupportedException e) {
            throw new AssertionError(e);
        }
    }
}
~~~

With two variables `IdentityItem a = new IdentityItem(5);` and `IdentityItem b = a.clone();`, we have `a != b` is `true`, `a.value == b.value` is `true`, yet `a.equals(b)` is `false`. This class **does not violate mandatory rules of `equals()`**; it only misses the "usually equals" clone convention because default equality is identity.

If you want a **value object**, define `equals()` alongside `hashCode()` over stable value fields; when used as keys in `HashSet`/`HashMap`, avoid changing fields participating in equality/hash after insertion.

## 6. Shallow copy and deep copy: practical meaning of "a copy"

`super.clone()` performs field-by-field copying by the default mechanism (*field-by-field copy*). For primitive fields like `int`, the value is copied. For reference fields like `int[] scores`, the **reference value** is copied: the original object and the clone may point to the same array.

~~~text
Before clone:
Original ----> scores [10, 20]

After super.clone() (shallow):
Original ----> scores [10, 20]
Clone    -----^

After additionally copying scores.clone() (separate array):
Original ----> scores [10, 20]
Clone    ----> scores [10, 20]
~~~

This is a diagram illustrating references; the two `[10, 20]` lines in the final diagram represent **two different arrays**, not the same array.

If the clone should be able to modify the array independently, the array field needs to be copied (for example, `copy.scores = scores.clone()`). For complex structures containing nested arrays, lists, maps, or mutable objects, copying an outer array/list **is not enough**: inner referenced elements may still be shared, requiring consideration of appropriate depth.

What constitutes a "deep copy" also depends on the business contract: immutable objects like `String` can be shared safely, whereas mutable data usually needs to be copied or replaced with an immutable model. Do not copy the entire object graph unconditionally, especially when there are reference cycles, system resources, or intentionally shared identities.

## 7. Runnable Java 17 program with deterministic output

The following program directly checks the three conventions, compares shallow/deep copies, verifies the constructor is not called during cloning, and tests a class missing `Cloneable`.

Save file **`CloneContractDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class CloneContractDemo {
    static final class Document implements Cloneable {
        static int constructorCalls = 0;

        String title;
        int[] pages;

        Document(String title, int[] pages) {
            constructorCalls++;
            this.title = title;
            this.pages = pages;
        }

        @Override
        public Document clone() {
            try {
                return (Document) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }

        Document deepCopy() {
            Document result = clone();
            result.pages = pages.clone();
            return result;
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) return true;
            if (!(other instanceof Document d)) return false;
            return Objects.equals(title, d.title)
                    && Arrays.equals(pages, d.pages);
        }

        @Override
        public int hashCode() {
            return 31 * Objects.hashCode(title)
                    + Arrays.hashCode(pages);
        }
    }

    static final class IdentityItem implements Cloneable {
        final int value;

        IdentityItem(int value) {
            this.value = value;
        }

        @Override
        public IdentityItem clone() {
            try {
                return (IdentityItem) super.clone();
            } catch (CloneNotSupportedException e) {
                throw new AssertionError(e);
            }
        }
        // Does not override equals(): uses Object's identity.
    }

    static final class MissingMarker {
        Object attemptClone() throws CloneNotSupportedException {
            return super.clone();
        }
    }

    public static void main(String[] args) {
        Document original = new Document("Guide", new int[]{10, 20});
        Document shallow = original.clone();
        Document deep = original.deepCopy();

        System.out.println("clone different reference: "
                + (shallow != original));
        System.out.println("clone same class: "
                + (shallow.getClass() == original.getClass()));
        System.out.println("clone equals original: "
                + shallow.equals(original));
        System.out.println("shallow shares array: "
                + (shallow.pages == original.pages));
        System.out.println("deep different reference: "
                + (deep != original));
        System.out.println("deep same class: "
                + (deep.getClass() == original.getClass()));
        System.out.println("deep equals original: "
                + deep.equals(original));
        System.out.println("deep separate array: "
                + (deep.pages != original.pages));
        System.out.println("constructor calls: "
                + Document.constructorCalls);

        original.pages[0] = 99;
        System.out.println("original pages: "
                + Arrays.toString(original.pages));
        System.out.println("shallow pages: "
                + Arrays.toString(shallow.pages));
        System.out.println("deep pages: "
                + Arrays.toString(deep.pages));
        System.out.println("shallow still equals: "
                + original.equals(shallow));
        System.out.println("deep now equals original: "
                + original.equals(deep));

        IdentityItem identity = new IdentityItem(7);
        IdentityItem identityCopy = identity.clone();
        System.out.println("identity copy different: "
                + (identity != identityCopy));
        System.out.println("identity same field: "
                + (identity.value == identityCopy.value));
        System.out.println("identity equals: "
                + identity.equals(identityCopy));

        int[] array = {1, 2};
        int[] arrayCopy = array.clone();
        System.out.println("array clone different: "
                + (array != arrayCopy));
        System.out.println("array clone same class: "
                + (array.getClass() == arrayCopy.getClass()));
        System.out.println("array content equal: "
                + Arrays.equals(array, arrayCopy));

        try {
            new MissingMarker().attemptClone();
            System.out.println("missing marker: unexpected success");
        } catch (CloneNotSupportedException expected) {
            System.out.println("missing marker: CloneNotSupportedException");
        }
    }
}
~~~

Compile and run using **JDK 17 or later**:

~~~bash
javac CloneContractDemo.java
java CloneContractDemo
~~~

Output:

~~~text
clone different reference: true
clone same class: true
clone equals original: true
shallow shares array: true
deep different reference: true
deep same class: true
deep equals original: true
deep separate array: true
constructor calls: 1
original pages: [99, 20]
shallow pages: [99, 20]
deep pages: [10, 20]
shallow still equals: true
deep now equals original: false
identity copy different: true
identity same field: true
identity equals: false
array clone different: true
array clone same class: true
array content equal: true
missing marker: CloneNotSupportedException
~~~

**Result analysis:**

1. `Document.clone()` creates a new instance (`!=`) of the same runtime class (`getClass() ==`). Before data changes, the clone equals the original because `Document.equals()` is defined by `title` and array contents.
2. `shallow.pages == original.pages` is `true`: two different Documents yet **referencing the same array**. Modifying an element in the original's array makes the shallow copy observe the same change.
3. `deepCopy()` clones first and then separates `pages` via `pages.clone()`; the two arrays are distinct, initially having identical contents. After modifying the original's array, the deep copy keeps the old data and `equals` compared to the original becomes `false`.
4. The constructor counter is 1 even though two additional Documents were created via clone/deepCopy: `Object.clone()` does not call the `Document` constructor.
5. `IdentityItem` proves **identical fields do not mean `equals == true`** when using the default `Object.equals()` implementation.
6. Arrays have their own `clone()`, resulting in a distinct reference of the same runtime array class; for primitive arrays, primitive elements are copied independently.
7. `MissingMarker` shows `Object.clone()` throws `CloneNotSupportedException` when the class does not implement `Cloneable`; the exception is checked rather than letting the program crash.

**Example limitation:** `deepCopy()` only deep-copies one level of primitive array, because the `Document` model here only has `String` (immutable) and `int[]`. With nested mutable objects, an explicit strategy is needed for each component; calling `clone()` once does not automatically produce a general deep copy.

## 8. Inheritance and Cloneable: why is it easy to design wrongly?

A superclass with `public Parent clone()` using `super.clone()` allows subclasses to inherit that method. When the actual receiver is `Child`, the copy created by `Object.clone()` can still be **runtime `Child`**, even though the declared return type is `Parent`.

However, inheritance introduces two risks:

- **Subclass adds mutable reference fields:** `super.clone()` only copies reference values; if the subclass wants independence, it must override and copy the added mutable parts.
- **Different equality contracts across classes:** the clone may have the same runtime class, yet the parent/child class's `equals()` has bugs or lacks value equality. Hence the `clone.equals(original)` convention must not be taken as proof that equality was designed properly.

If a superclass was not built to support cloning, attempting to override it arbitrarily in a subclass can cause issues with internal state and constructor invariants. In particular, check whether the class has `final` fields pointing to mutable objects: shallow cloning keeps shared references, while a deep-copy design with `final` fields cannot simply reassign them arbitrarily inside clone.

**`Cloneable` is a marker**, not an interface defining `public clone()`; generic code accepting `Cloneable` cannot automatically call `clone()` on a reference typed only as `Cloneable`. This is an important limitation of the legacy clone mechanism.

## 9. Arrays, records, and other copying options

**Arrays** can be cloned directly with `clone()`. For `int[]`, primitive elements are copied; for `Person[]`, the copy is a new array yet each initial element still points to **the same Person**. Do not confuse `array.clone()` with a deep copy of object elements.

**Records** are declared `final` by Java, automatically have `equals()`/`hashCode()` based on components, but do not have an auto-generated `public clone()` method for copying records. For suitable immutable records, cloning is usually unnecessary: you can use the exact same value directly or create a new record from components if a distinct instance is needed.

Many modern designs prefer a **copy constructor** or **static factory** because they explicitly state the copying policy:

~~~java
final class Settings {
    private final String name;
    private final int[] flags;

    Settings(String name, int[] flags) {
        this.name = name;
        this.flags = flags.clone();
    }

    Settings(Settings other) {
        this(other.name, other.flags);
    }
}
~~~

This is an illustrative class without `main`. The constructor accepting `Settings` creates a new object and creates a new array. In this design, the primary constructor also performs a **defensive copy** to prevent callers from keeping references to mutable `flags`. If a getter returning the array is provided, returning a copy should also be considered to protect immutability.

Options like copy constructors/factories fit when an API needs an explicit contract: shallow or deep copy, whether IDs are kept or regenerated, which mutable fields are separated, and whether copying is allowed through inheritance.

## 10. Common mistakes

| Mistake or assumption | Why it is wrong | How to handle |
|---|---|---|
| `implements Cloneable` automatically gives `public clone()` | The marker interface declares no methods | Write a public clone method if the API needs it |
| Calling `super.clone()` on a non-`Cloneable` object | The Object mechanism throws `CloneNotSupportedException` | Only use with classes designed to support clone, or use a copy constructor |
| Clone has the same fields so `equals == true` is guaranteed | `Object.equals` defaults to identity | Read/define equality with proper semantics |
| `clone != original` means no shared mutable state | Shallow copy preserves references in fields | Additionally copy mutable parts needing independence |
| `clone.getClass() == original.getClass()` is always enforced by the JVM | Custom overrides can return a different type | Maintain the contract and test runtime class |
| Adding mutable fields in a subclass and merely inheriting parent's clone | New mutable objects may still be shared | Review and override clone in the subclass if needed |
| Thinking clone calls the constructor | `Object.clone()` copies fields without calling that class's constructor | Protect invariants; consider a copy constructor |
| Using clone as the sole mechanism for complex deep copies | Nested references/reference cycles need special handling | Specify depth, use a factory or controlled copying |
| Misusing `equals` or mismatched `hashCode` | Breaks hash collections if objects are used as keys | Preserve equality/hash contract, avoid mutable keys |

## 11. How to test the clone contract

For `x` as an object expected to be cloneable, do not check only surface contents. Test the following relationship layers:

1. **Instance:** does `clone != original` hold per the published contract?
2. **Runtime type:** does `clone.getClass() == original.getClass()` hold? If the design intentionally returns another type, is it documented?
3. **Initial values:** are primitive fields, immutable references, and mutable parts whose contents must be preserved copied accurately?
4. **Equality:** does `clone.equals(original)` behave according to **the class's own equals definition**? If not, is that intentional or a bug?
5. **State sharing:** after modifying a mutable array/list on the original, is the copy altered? Does that match the shallow/deep contract?
6. **Inheritance:** clone a runtime object belonging to a subclass and verify the actual type and fields added by the subclass.
7. **Exception/access:** does the class permit cloning, is calling permission `public` or `protected`, and must `CloneNotSupportedException` be handled?
8. **Invariants and hashing:** do cloning or post-clone mutations break invariants, equality, or hash collection structures?

Do not use the three conventions as a magic spell in place of behavioral testing. For a copying API with another goal (for instance, creating a new order with a new ID), name and document it clearly instead of letting users mistakenly assume full value cloning.

## 12. Self-check questions

**1.** What does `x.clone() != x` aim to ensure?  
**Answer:** The copy is a new instance, not merely an alias of the original object. This is a design convention, not an absolute law for every override.

**2.** If a clone has the same runtime class yet `equals()` uses default `Object.equals()`, what is `clone.equals(original)` usually?  
**Answer:** `false`, because two instances differ in identity. "Same data" does not automatically mean value equality.

**3.** Does `super.clone()` automatically clone every object referenced in fields?  
**Answer:** No. It creates a shallow copy; mutable reference fields can share child objects.

**4.** Why is `Cloneable` not enough to call `x.clone()` from external code?  
**Answer:** `Cloneable` does not declare `public clone`; `Object.clone` is `protected`. The class must provide a copy API with appropriate access level.

**5.** Can `int[] copy = source.clone()` be used to get a new independent array?  
**Answer:** Yes. The new array has a different reference and primitive element values are copied. For `Object[]`, references to element objects remain shared unless copied further.

**6.** When should a copy constructor be chosen instead of clone?  
**Answer:** When you need to explicitly express copying rules, control mutable fields/invariants, or handle models with complex inheritance.

**Remember:** The three clone characteristics **distinct reference, same runtime class, and usually equal values** are **expected conventions**. To make a copy genuinely useful, you must understand the class's `equals()` and the level of **independence of mutable state**, rather than merely trusting `super.clone()`.