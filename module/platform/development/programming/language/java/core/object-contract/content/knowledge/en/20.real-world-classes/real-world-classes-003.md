# `getClass()` Is `final` and Cannot Be Overridden in Java

## 1. Lesson Objectives

In Java, every object inherits the `getClass()` method from `java.lang.Object`. When calling this method on a **non-`null`** reference, Java returns a `Class<?>` object representing the **actual runtime class** of that object.

This lesson focuses on two closely related facts:

1. `Object.getClass()` is a **`final`** method, so no subclass—including user-defined classes, records, or enums—**may override it**.
2. The result of `getClass()` reflects the **actual type of the object**, which may differ from the reference variable's declared type in source code.

Understanding these facts helps you use type information properly in Java, distinguish exact-type comparison from inheritance-based checks, and avoid designing `equals()` methods incorrectly.

## 2. Declaration of `Object.getClass()`

In `java.lang.Object`, the method signature has the form:

```java
public final native Class<?> getClass();
```

This is an **illustrative signature declaration from the JDK**, not code you can add into your own class to run standalone. Meaning of each part:

- **`public`:** can be called on any object for which you hold a valid reference.
- **`final`:** subclasses cannot override a method with the same signature. This rule is enforced by the Java compiler.
- **`native`:** the implementation is provided via a low-level JVM/runtime mechanism rather than a Java method body in the declaration above.
- **`Class<?>`:** the return type represents metadata of a runtime class/type; it is not a class name string. Reflection APIs such as `getName()`, `getSuperclass()`, `isInterface()`, and `isAssignableFrom()` can be used on it.

For an object existing in the JVM, its actual class is already determined when the object is created. Assigning that object to a variable of a superclass or interface type does not change that actual class, so `getClass()` still returns metadata for the original runtime type.

**Key distinction:** `getClass()` is a **`final`** method, but that does not mean every class containing that method is `final`. For example, `Animal` can be non-`final` and still be subclassed, even though the `getClass()` method inherited from `Object` can never be overridden.

## 3. How Do the Declared Type and the Actual Class Differ?

Example:

```java
class Animal {}
class Dog extends Animal {}

Animal pet = new Dog();
```

`pet` has the **declared type** `Animal`. However, the object created by `new Dog()` has the **runtime class** `Dog`.

Therefore:

```java
pet.getClass() == Dog.class;    // true
pet.getClass() == Animal.class; // false
pet instanceof Animal;          // true
pet instanceof Dog;             // true
```

These are illustrative expressions based on the `pet` variable declared above. Understand the two different checks:

- `pet.getClass() == Dog.class` asks: "Does this object belong to the **exact** `Dog` class at runtime?"
- `pet instanceof Animal` asks: "Is this object compatible with type `Animal`, including subclasses?"

The `getClass()` method is not "hidden" by the `Animal` variable type. Calling it on a parent-type variable still yields metadata for the actual class, even when the subclass does not redefine `getClass()`.

### How Does `SomeType.class` Differ from `obj.getClass()`?

`Dog.class` is a **class literal**: it obtains the `Class` of the type named directly in code; there is no need to instantiate a `Dog`.

`pet.getClass()` is a **runtime query** on the specific object currently referenced. If one day the variable `pet` holds `new Cat()` instead of `new Dog()`, the result can be `Cat.class`.

Both return a `Class` object representing the corresponding type. Within the same type scope loaded by the JVM, multiple instances of the same class share the `Class` object:

```java
new Dog().getClass() == new Dog().getClass(); // true
```

The two `Dog` instances in this expression **are not the same `Dog` object**; they merely share the same actual class. Thus `a.getClass() == b.getClass()` does not imply `a == b` or `a.equals(b)`.

## 4. Why Can't `getClass()` Be Overridden?

If a class could spoof runtime type metadata via overriding, the result of `getClass()` would no longer be a trustworthy source of information about the actual class managed by the JVM. Java therefore locks the method on `Object` with `final`.

An **intentionally invalid example that will not compile**:

```java
class FakeType {
    @Override
    public Class<?> getClass() {
        return String.class;
    }
}
```

The compile error in essence is: `getClass()` cannot override the `final` method in `Object`. Removing `@Override` does not help either: the signature still clashes with the inherited `final` method.

Similarly, you cannot override `getClass()` in:

- A normal subclass, including deeply nested subclasses.
- A record: records inherit `Object` (via `java.lang.Record`) and remain subject to the `final` constraint on `getClass()`.
- An enum: enums inherit `java.lang.Enum` and then `Object`.
- An anonymous class or an enum constant's own class body.

If you only want to provide a **business category label**, define a method with a **different name**, such as `kind()`, `typeCode()`, or `displayType()`; do not try to alter `Object.getClass()`.

## 5. Complete Java 17+ Example

Create the file **`GetClassFinalDemo.java`**:

```java
import java.util.ArrayList;

public class GetClassFinalDemo {

    static class Animal {}

    static class Dog extends Animal {}

    record Point(int x, int y) {}

    enum Mode {
        SIMPLE,
        CUSTOM {
            @Override
            String label() {
                return "custom";
            }
        };

        String label() {
            return "simple";
        }
    }

    static boolean sameRuntimeClass(Object left, Object right) {
        return left != null
                && right != null
                && left.getClass() == right.getClass();
    }

    public static void main(String[] args) {
        Animal animal = new Animal();
        Animal dogAsAnimal = new Dog();
        Object anonymous = new Animal() {};
        Object point = new Point(1, 2);

        System.out.println("declared Animal, runtime Dog: "
                + (dogAsAnimal.getClass() == Dog.class));
        System.out.println("dog instanceof Animal: "
                + (dogAsAnimal instanceof Animal));
        System.out.println("Animal vs Dog same class: "
                + (animal.getClass() == dogAsAnimal.getClass()));
        System.out.println("two Dog instances same Class: "
                + (new Dog().getClass() == dogAsAnimal.getClass()));
        System.out.println("same runtime class Dog vs Animal: "
                + sameRuntimeClass(dogAsAnimal, animal));
        System.out.println("record runtime class: "
                + (point.getClass() == Point.class));

        System.out.println("anonymous exactly Animal: "
                + (anonymous.getClass() == Animal.class));
        System.out.println("anonymous superclass Animal: "
                + (anonymous.getClass().getSuperclass()
                        == Animal.class));
        System.out.println("anonymous canonical name null: "
                + (anonymous.getClass().getCanonicalName() == null));

        System.out.println("enum constant class is Mode: "
                + (Mode.CUSTOM.getClass() == Mode.class));
        System.out.println("enum declaring class is Mode: "
                + (Mode.CUSTOM.getDeclaringClass() == Mode.class));

        Object strings = new ArrayList<String>();
        Object numbers = new ArrayList<Integer>();
        System.out.println("erased generic class same: "
                + (strings.getClass() == numbers.getClass()));

        Object missing = null;
        System.out.println("missing == null: " + (missing == null));
        try {
            missing.getClass();
        } catch (NullPointerException ex) {
            System.out.println("missing.getClass() throws NPE");
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac GetClassFinalDemo.java
java GetClassFinalDemo
```

**Expected output:**

```text
declared Animal, runtime Dog: true
dog instanceof Animal: true
Animal vs Dog same class: false
two Dog instances same Class: true
same runtime class Dog vs Animal: false
record runtime class: true
anonymous exactly Animal: false
anonymous superclass Animal: true
anonymous canonical name null: true
enum constant class is Mode: false
enum declaring class is Mode: true
erased generic class same: true
missing == null: true
missing.getClass() throws NPE
```

**Explanation of output groups:**

1. `dogAsAnimal` has declared type `Animal` but is `new Dog()`, so `getClass() == Dog.class` is `true`. `instanceof Animal` is also `true` due to inheritance.
2. `animal` and `dogAsAnimal` have different runtime classes, so comparing the two `Class` objects yields `false`. Two independent `Dog` instances have the **same class** and share `Class` metadata.
3. `sameRuntimeClass` compares two classes exactly and explicitly checks for `null` on both sides. Two objects instantiated from different classes yield `false`.
4. `Point` is a record, yet a record is still a concrete runtime type. `point.getClass()` returns `Point.class`.
5. `new Animal() {}` creates an **anonymous subclass** of `Animal`. That object is an `Animal` according to `instanceof`, yet its actual class **is not** `Animal.class` itself. `getSuperclass()` shows the direct superclass is `Animal`, and an anonymous class has no canonical name so `getCanonicalName() == null`.
6. `Mode.CUSTOM` has a **constant-specific class body**, so this constant's runtime class can be a subclass of the `Mode` enum, distinct from `Mode.class`. `getDeclaringClass()` on the constant still returns the declaring enum class, namely `Mode.class`.
7. Two `ArrayList` instances with type arguments `String` and `Integer` have the same runtime class `ArrayList` after type erasure. Calling `getClass()` on an instance does not let you recover the full generic type argument.
8. Calling a method on a `null` reference throws `NullPointerException`; checking `missing == null` is allowed and invokes no method.

## 6. `getClass()`, `instanceof`, `Class.isInstance`: Asking the Right Question

| Check | Meaning | Result with `new Dog()` compared to `Animal` |
| --- | --- | --- |
| `obj.getClass() == Animal.class` | Runtime class is **exactly** `Animal` | `false` |
| `obj instanceof Animal` | Object is an `Animal` or subtype | `true` |
| `Animal.class.isInstance(obj)` | Runtime check whether the object can be used as `Animal` | `true` |
| `Animal.class.isAssignableFrom(obj.getClass())` | Checks whether class `Animal` can accept a value of the right-hand runtime class | `true` if `obj` is non-null |
| `obj == other` | Whether two references point to the same object | Cannot be inferred from class name alone |

`instanceof` and `Class.isInstance` are designed for **type compatibility**, such as a handling branch that applies to every class implementing an interface. `getClass() == SomeClass.class` is for cases that require the exact **specific class**, rejecting subtypes.

Example with an interface:

```java
interface Payable {}
final class Invoice implements Payable {}

Object value = new Invoice();

boolean isPayable = value instanceof Payable;          // true
boolean runtimeInvoice = value.getClass() == Invoice.class; // true
```

This snippet illustrates two different questions, not a program with `main`. Most application code leverages **polymorphism** and should therefore handle things via interfaces or `instanceof` instead of branching repeatedly by class name. Choose an exact-class check only when that is genuinely a business or API requirement.

## 7. Connection to `equals()`: Why Do Some People Use `getClass()`?

When writing value equality manually, there are two common strategies for checking the right-hand object:

**Exact-class checking strategy:**

```java
@Override
public boolean equals(Object other) {
    if (this == other) return true;
    if (other == null || getClass() != other.getClass()) return false;
    PointValue that = (PointValue) other;
    return x == that.x && y == that.y;
}
```

This is an **illustrative method body** for a `PointValue` class with two fields `int x` and `int y`; a matching `hashCode()` must be defined to form a complete value class. The condition `getClass() != other.getClass()` excludes all subtypes from the equality relation. In an inheritable type, this is sometimes a deliberate decision to avoid tricky `equals` symmetry/transitivity situations.

**Compatible-type checking strategy:**

```java
if (!(other instanceof PointValue value)) {
    return false;
}
```

Using `instanceof` can accept subtypes. This makes sense when all subtypes are allowed to participate in **the same equality relation** and the rules genuinely preserve the `equals` contract. However, if a subtype adds fields that participate in equality, a careless implementation can break symmetry or transitivity.

**There is no rule saying "always use `getClass` for every class"**. It depends on the data model and equality contract:

- For a `final` value class or record, there are no application subclasses; `instanceof` and exact-class checks are generally equivalent for instances of the considered type.
- For an inheritance hierarchy that extends data, the equality relation must be designed very carefully; you may restrict to the exact class using `getClass()`, or prefer composition/`final` value objects.
- Do not confuse `getClass()` being `final` with `equals()` always comparing exact classes. `Object.equals()` defaults to **identity** comparison; many classes override `equals()` with their own semantics. `getClass()` is not automatically called by every `equals` implementation.

### Proxies or Dynamically Generated Classes

A framework-created proxy/subclass object may have a different runtime class from the domain class the program expects. If you rigidly use `getClass() == Domain.class`, that object may be rejected even though it is still compatible with `Domain` under `instanceof`. In frameworks, read the corresponding proxy and equality contracts; do not assume on your own that a proxy entity and the original entity must be equal.

## 8. Common Special Cases

### 8.1. Anonymous Classes and Nested Classes

`getClass()` does not return the "nearest superclass"; it returns the actual runtime class, even when the class name is compiler-generated. Anonymous classes may have no canonical name; do not rely on `getSimpleName()` or a name containing `$` to determine business types.

`getSuperclass()` is a different API: it returns the direct superclass of a `Class` (or `null` for certain kinds such as interfaces, primitives, or `Object.class`). It does not replace `getClass()`.

### 8.2. Enums with Constant-Specific Class Bodies

If an enum defines per-constant methods via a class body, a constant can have a runtime class different from the declaring enum class. To get the **root enum type**, use `someEnum.getDeclaringClass()`. To check which exact **constant** it is, use `==` with the corresponding constant.

Do not assume that `enumConstant.getClass() == MyEnum.class` is true for every constant when an enum has constant-specific class bodies.

### 8.3. Primitive Types and Arrays

Primitives are not objects on which to call instance methods:

```java
int number = 42;
// number.getClass(); // Wrong: int is a primitive type and has no getClass().
Class<?> primitiveType = int.class;
Class<?> boxedType = Integer.valueOf(number).getClass();
```

The snippet above illustrates variable declarations. `primitiveType` represents the primitive type `int`; `boxedType` represents the `Integer` class. They are not equal.

Arrays are objects, so `new String[0].getClass() == String[].class` is `true`. Do not conclude that the array is `String.class`: the class of `String[]` differs from the class of each `String` element.

### 8.4. Generic Type Erasure

With:

```java
Object first = new java.util.ArrayList<String>();
Object second = new java.util.ArrayList<Integer>();

boolean sameClass = first.getClass() == second.getClass(); // true
```

`getClass()` does not expose the `String` or `Integer` generic type argument of each instantiation when that information has been erased by type erasure. Reflection APIs for generic declarations can read generic structure in **class/field/method declarations** when metadata exists, but they do not turn each `ArrayList<T>` object into a separate runtime class for each `T`.

### 8.5. Classes Loaded by Different Class Loaders

Having the same fully qualified name does not always mean it is **the same runtime type**. Java determines class identity by both the class name and the class loader that defines the class. When the same class name is loaded independently by different loaders, the two `Class` objects can differ. Comparing `Class<?>` with `==` accurately reflects runtime identity; comparing strings from `getName()` may only tell you they have the **same name**, not prove they are the same class.

In ordinary applications this rarely appears; in plugin systems, application servers, hot deployment, or complex modular environments, this is a major cause of type-compatibility errors.

## 9. `getClass()` and Reflection

Once you have a `Class<?>` object, you can inspect structural information without altering the nature of the object:

```java
Object value = "hello";
Class<?> type = value.getClass();

String binaryName = type.getName();       // "java.lang.String"
String simpleName = type.getSimpleName(); // "String"
boolean isString = type == String.class;  // true
```

This is an illustrative Java snippet that can be placed inside `main`. Reflection also has methods to query constructors, fields, methods, or annotations according to Java's access rules. `getClass()` itself **does not** automatically read all data fields, does not change member accessibility, and does not turn an object into an instance of another class.

When you need a type already known at compile time, prefer `SomeClass.class`. When receiving an arbitrary `Object` and needing its runtime type, use `getClass()` after handling the possibility of `null`.

## 10. Common Mistakes and How to Avoid Them

| Claim or Practice | Problem | Correct Approach |
| --- | --- | --- |
| "An `Animal` variable always returns `Animal.class`." | Wrong if it points to a `Dog` or another subclass. | `getClass()` returns the actual class of the object. |
| "Override `getClass()` to display a custom type." | The method on `Object` is `final`; will not compile. | Define `kind()` or a differently named method. |
| "`getClass() == Base.class` checks subclasses too." | It only accepts **the exact `Base` class**. | Use `instanceof Base` if you want to accept subtypes. |
| "Two objects with the same `getClass()` are `equals()`." | Same type does not prove equality of identity or value. | Use the `equals` contract or `==` depending on intent. |
| "You can call `value.getClass()` when `value` is null." | Throws `NullPointerException`. | Check for `null` first or use `instanceof` where appropriate. |
| "Comparing `getClass().getName()` is always enough to identify a class." | Different class loaders can load the same name. | Compare `Class` by identity when exact runtime class is truly needed. |
| "`getClass()` distinguishes `List<String>` from `List<Integer>`." | Generic args are typically erased in the runtime instance type. | Pass type information via API/`Class<T>` or a type token when needed. |
| "Every enum constant has `getClass() == MyEnum.class`." | Constant-specific class bodies have a runtime subclass. | Use `getDeclaringClass()` for the declared enum type. |
| "`final` `getClass()` makes every subclass `final`." | The `final` modifier applies only to that method. | Distinguish a `final` method from a `final` class. |
| "`getClass()` and `getSuperclass()` are equivalent." | One gets the object's runtime class; the other queries the parent class of `Class` metadata. | Choose the API according to the question you need to answer. |

## 11. Quick Selection Checklist

1. **Want to know the exact class of an object?** Check that it is not `null`, then use `obj.getClass()`.
2. **Want to check whether an object is compatible with an interface/superclass?** Use `instanceof` or `Class.isInstance`.
3. **Want metadata for a type known at compile time?** Use `Type.class`; no need to instantiate an object just to call `getClass()`.
4. **Want to compare two exact runtime classes?** Use `a.getClass() == b.getClass()` after handling `null`.
5. **Want to check whether two objects have the same data?** Use the class's defined `equals()` relation; do not infer it from `getClass()`.
6. **Want the declared enum type even when a constant has its own class body?** Use `enumValue.getDeclaringClass()`.
7. **Want a user-defined business type label?** Create an API with a different name; `Object.getClass()` cannot be overridden.

## 12. Self-Check

**Question 1.** `Animal x = new Dog();`. Is `x.getClass() == Animal.class` `true` or `false`?

**Answer:** `false`, because the runtime class is `Dog`. `x instanceof Animal` is still `true`.

**Question 2.** Can you declare `public Class<?> getClass()` in your own class to "replace the result" of `Object.getClass()`?

**Answer:** No. `Object.getClass()` is `final`; a method with the same signature cannot be overridden.

**Question 3.** Do two different `Dog` objects have the same `getClass()`? Are they guaranteed to be `equals()`?

**Answer:** They have the same runtime `Class`. `equals()` still depends on the class's rules; it cannot be inferred from having the same type.

**Question 4.** Why does `new Animal() {}` not have `getClass() == Animal.class`?

**Answer:** It is a genuine anonymous subclass; the runtime class is that subclass.

**Question 5.** Why is `getClass()` the same for `ArrayList<String>` and `ArrayList<Integer>`?

**Answer:** Both are runtime instances of `ArrayList`; generic type argument information does not create separate runtime classes after type erasure.

**Question 6.** When you need to check whether a value belongs to a subtype of `Base`, should you use `obj.getClass() == Base.class` or `obj instanceof Base`?

**Answer:** `obj instanceof Base`. Exact-class comparison excludes subtypes.

**Key Takeaway:** `Object.getClass()` is **`public final native`**, always returning metadata of the **actual runtime class** for a non-null object. No class may override it. Use `getClass()` when you need the exact type, `instanceof` when you need a type relationship, and `equals()` when you need value semantics.