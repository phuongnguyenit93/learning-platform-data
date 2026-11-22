# Field hiding and multiple same-named fields in a Java class hierarchy

## 1. What is field hiding?

In Java, a subclass can **declare a field with the same name** as a field in its parent class. The subclass's field *hides* the parent class's same-named field when looked up using normal Java syntax. This is **field hiding**, not *overriding* as with instance methods.

```java
class Parent {
    public int count = 10;
}
class Child extends Parent {
    public String count = "ten";
}
```

Both fields `Parent.count` and `Child.count` coexist, even though they have **the same name but different types**. This declaration syntax is valid because they reside in **two different classes**. Conversely, declaring two fields with the same name within *a single class* is a compile-time error. A field in a subclass can have the same or a different type; hiding also does not depend on whether the field is `static` or an instance field.

With an object `Child child = new Child()`:

- `child.count` is resolved by the static type `Child`, so it refers to `Child.count` (value `"ten"`).
- `((Parent) child).count` refers to `Parent.count` (value `10`).
- Casting **does not create a new object**, rather it causes the compiler to select the field according to the type of the access expression.
- Inside a method of `Child`, `super.count` can be used to access the parent's field.

Therefore, a child object can contain **multiple distinct field storage slots with the same name** along the inheritance chain. Field hiding does not delete the parent field, does not merge the two fields, and does not create a dynamic dispatch mechanism based on the runtime class.

## 2. What scope does Reflection search for fields?

| API | Finds inherited fields? | Includes non-`public` fields? | When names collide |
| --- | --- | --- | --- |
| `type.getDeclaredField(name)` | No | Yes, if the field is declared directly in `type` | Returns `type`'s exact field; if that class does not declare it, throws `NoSuchFieldException` |
| `type.getDeclaredFields()` | No | Yes, from `public` to `private` | Returns all directly declared fields, with no guaranteed order |
| `type.getField(name)` | Yes, `public` member fields only | No | Selects **one** field according to `Class`'s public search algorithm |
| `type.getFields()` | Yes, including `public` fields from parent classes and interfaces | No | May contain **multiple fields with the same name**, including hidden fields; order not guaranteed |

**Key point:** `getFields()` returns an array of `Field`s, not a unique `name -> Field` mapping. You must not assume that names are unique keys or that the first element is the desired field.

### The `Class.getField("name")` algorithm

For type `C`, according to the Java SE 17 `Class` documentation:

1. If `C` **directly declares a `public` field** with that name, return that field.
2. If not yet found, recursively check each **direct superinterface** of `C`, in the order the interfaces were declared.
3. If still not found, recursively check the **superclass** of `C`; if no candidate remains, throw `NoSuchFieldException`.

Therefore, when a subclass has a `private` field named `marker` while the parent class has a `public` field also named `marker`, `Child.class.getField("marker")` can **return the parent's `public` field**: the first step skips the non-`public` child field and continues searching. Do not interpret `getField` naively as always choosing the field closest to the subclass regardless of modifier.

In particular, when **both an interface and a superclass provide a public field with the same name**, searching superinterfaces happens **before** the superclass when the current class does not directly declare a matching `public` field.

## 3. Runnable Java 17+ example: three `value` fields on one object

Save the entire program as **`FieldHidingDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class FieldHidingDemo {
    public static class Root {
        public int value = 10;
        public String marker = "root";
    }

    public static class Mid extends Root {
        public String value = "mid";
        private String marker = "mid-private";
    }

    public static class Leaf extends Mid {
        public long value = 30L;
    }

    public interface First {
        int LIMIT = 100;
    }

    public interface Second {
        int LIMIT = 200;
    }

    public static class Settings implements First, Second {
    }

    public static void main(String[] args) throws Exception {
        Leaf leaf = new Leaf();

        System.out.println("Leaf expression: " + leaf.value);
        System.out.println("Mid expression: " + ((Mid) leaf).value);
        System.out.println("Root expression: " + ((Root) leaf).value);

        Field selected = Leaf.class.getField("value");
        System.out.println("getField(value): "
                + selected.getDeclaringClass().getSimpleName());

        for (Class<?> c = Leaf.class; c != Object.class; c = c.getSuperclass()) {
            Field f = c.getDeclaredField("value");
            System.out.println(c.getSimpleName() + ".value = " + f.get(leaf)
                    + " (" + f.getType().getSimpleName() + ")");
        }

        String[] valueOwners = Arrays.stream(Leaf.class.getFields())
                .filter(f -> f.getName().equals("value"))
                .map(f -> f.getDeclaringClass().getSimpleName())
                .sorted()
                .toArray(String[]::new);
        System.out.println("getFields(value) owners: "
                + String.join(", ", valueOwners));

        Field marker = Leaf.class.getField("marker");
        System.out.println("getField(marker): "
                + marker.getDeclaringClass().getSimpleName()
                + "=" + marker.get(leaf));

        System.out.println("Mid marker private: " + Modifier.isPrivate(
                Mid.class.getDeclaredField("marker").getModifiers()));

        String[] limitOwners = Arrays.stream(Settings.class.getFields())
                .filter(f -> f.getName().equals("LIMIT"))
                .map(f -> f.getDeclaringClass().getSimpleName())
                .sorted()
                .toArray(String[]::new);
        System.out.println("getFields(LIMIT) owners: "
                + String.join(", ", limitOwners));
        System.out.println("getField(LIMIT): "
                + Settings.class.getField("LIMIT")
                        .getDeclaringClass().getSimpleName());
        System.out.println("First.LIMIT via reflection: "
                + First.class.getField("LIMIT").getInt(null));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac FieldHidingDemo.java
java FieldHidingDemo
```

Stdout (line order and values verified on Java):

```text
Leaf expression: 30
Mid expression: mid
Root expression: 10
getField(value): Leaf
Leaf.value = 30 (long)
Mid.value = mid (String)
Root.value = 10 (int)
getFields(value) owners: Leaf, Mid, Root
getField(marker): Root=root
Mid marker private: true
getFields(LIMIT) owners: First, Second
getField(LIMIT): First
First.LIMIT via reflection: 100
```

Results to distinguish:

1. **Java syntax resolves by static type:** `leaf.value`, `((Mid) leaf).value`, and `((Root) leaf).value` all access the same object, yet reach **three independent fields**.
2. **`getField("value")` returns a single `Field`:** `Leaf.value` is a `public` field declared directly on the queried class, so it is chosen first.
3. **`getDeclaredField("value")` per class:** Calling it separately on `Leaf.class`, `Mid.class`, and `Root.class` retrieves all three exact fields. `Field.get(leaf)` uses the field of the selected **declaring class**; it does not automatically switch to `Leaf`'s field.
4. **`getFields()` has multiple `value` entries:** the array contains all three public fields despite hiding. The code intentionally uses `sorted()` by class name for stable stdout; the API promises no return order.
5. **`getField("marker")` still finds `Root`:** `Mid.marker` is `private` and is found via `Mid.class.getDeclaredField("marker")`; meanwhile, `getField` finds `Root`'s inherited `public` field.
6. **Two interfaces declare `LIMIT`:** `Settings.class.getFields()` contains both `First.LIMIT` and `Second.LIMIT`. `getField("LIMIT")` selects `First` because `First` is the first superinterface in the `implements First, Second` declaration. To retrieve a specific constant, access `First.class.getField("LIMIT")` or `Second.class.getField("LIMIT")`.

`Root`, `Mid`, and `Leaf` in the example are all `public static` classes nested inside `FieldHidingDemo` so it can run standalone from a single file and avoid unrelated class access details.

## 4. Why does `Field.get()` not automatically read the subclass's field?

A `Field` object represents **one specific declaration**. Three particularly useful pieces of information are:

- `field.getName()`: the simple name of the field, e.g., `"value"`.
- `field.getDeclaringClass()`: the class/interface **actually declaring it**, e.g., `Root.class`.
- `field.getType()`: the declared type, e.g., `int.class`, `String.class`, `long.class`.

For example, `Root.class.getDeclaredField("value").get(leaf)` reads the `Root.value` slot of the `leaf` object, returning an `Integer` with value `10` (`Field.get` boxes primitive values in the `Object` result). `Leaf.class.getDeclaredField("value").get(leaf)` reads the `Leaf.value` slot, returning a `Long` with value `30`.

The object passed to `Field.get(receiver)` for an instance field must belong to the declaring class or a compatible subclass. For a `static` field, passing `null` is valid. `Field` does not perform **virtual dispatch** like an overridden instance method call.

Therefore, to identify a field in Reflection data, **do not store only `name`**. Keep at least `declaringClass` and `name`; also check `type` and `modifiers` when processing schemas or data mapping.

## 5. How to collect *all* same-named fields in the inheritance chain

When you want fields at **all class levels**, including `private` and `protected`, iterate through `getSuperclass()` and call `getDeclaredField(name)` at each level:

```java
// Method snippet for use inside a Java class; not a standalone program.
static java.util.List<java.lang.reflect.Field> findAllInClassHierarchy(
        Class<?> start, String name) {
    java.util.List<java.lang.reflect.Field> result =
            new java.util.ArrayList<>();

    for (Class<?> c = start; c != null; c = c.getSuperclass()) {
        try {
            result.add(c.getDeclaredField(name));
        } catch (NoSuchFieldException ignored) {
            // This class level does not declare the field; continue traversing superclasses.
        }
    }
    return result; // From the inspected class up through superclasses.
}
```

For example, calling `findAllInClassHierarchy(Leaf.class, "value")` returns the three `Field`s declared in `Leaf`, `Mid`, and `Root`, in that order. This method **only traverses classes and superclasses**, without recursing into interfaces; if all constants/fields from interfaces are needed, inspect `getInterfaces()` separately (including parent interfaces if necessary) or choose `getFields()` when only `public` fields matter.

Some implementation notes:

- Do not call `getDeclaredFields()` on a subclass and expect parent class fields.
- If you need to display a list, sort by **class level** or `declaringClass + name` yourself because the order in `getFields()`/`getDeclaredFields()` arrays is not guaranteed.
- Do not use `Map<String, Field>` if you need to keep all same-named fields: a later field can overwrite an earlier one. Use `List<Field>` or a key that includes `declaringClass`.
- When mapping serialization/ORM/custom injection, define clear rules: pick the nearest declared field, pick a field in a specific class, or report an error if multiple fields share a name. Do not treat whichever field the array happens to return first as an API contract.
- For non-public fields, **metadata lookup** is different from **read/write permission**: `getDeclaredField` may succeed, but `Field.get`/`set` must still obey access checks; `trySetAccessible()` is also subject to module `opens` restrictions.

## 6. Field hiding differs from method overriding

| Criterion | Same-named field in parent/child | Overridden instance method |
| --- | --- | --- |
| Relationship | Hiding between field declarations | Overriding if signature rules are met |
| Selection via Java syntax | By the static type of the expression containing the field | Dynamic dispatch by the object's runtime class |
| Casting to parent | Selects the field declared/present on the parent type | Still calls the child's override if the method is actually overridden |
| Reflection | `Field` points to one declaration; `Field.get` reads that declaration | `Method.invoke` on an instance method can execute the corresponding override |
| Different type / `static` | Child field can have a different type, and hiding does not distinguish static/instance | Methods have override conditions and separate static hiding rules |

```java
// Illustrative code snippet; place inside an appropriate Java program.
class A {
    int number = 1;
    String describe() { return "A"; }
}
class B extends A {
    int number = 2;
    @Override String describe() { return "B"; }
}
// A ref = new B();
// ref.number     -> 1 (field of A)
// ref.describe() -> "B" (method overridden in B)
```

Do not infer from method dispatch that a `Field` obtained from a parent will automatically refer to a same-named field in a child.

## 7. Easily confused cases

### 7.1. `private` field in subclass and `public` field in parent class

A subclass can declare a `private` field with the same name as a `public` field in the parent class. `getDeclaredField` on the subclass finds the `private` field; `getField` on the subclass can continue to the `public` field in the parent, as in the `marker` example. Finding a public field via `getField` **does not mean** the subclass has no other field with the same name.

### 7.2. Two interfaces with same-named constants

Fields declared in an interface are implicitly `public static final`. If a class implements `First` and `Second` which both have `LIMIT`, an unqualified expression like `Settings.LIMIT` can be **ambiguous at compile time**. Reflection `Settings.class.getField("LIMIT")`, on the other hand, is defined by `Class`'s lookup algorithm and in the example chooses `First`. These are two different rules; it is best to qualify explicitly as `First.LIMIT` or `Second.LIMIT`.

### 7.3. Same-named fields with different types

`int value`, `String value`, and `long value` at three class levels are three independent declarations. Within **a single class**, Java does not allow field overloading by type like method overloading. When reading via Reflection, use `getType()` before casting the value returned by `Field.get()`.

### 7.4. Static and instance fields

Field hiding does not require both fields to be `static` or both to be instance fields. A subclass can declare a field with the same name as a parent's `static` field. Access a `static` field via Reflection with `get(null)`; for an instance field, pass an appropriate object. Having the same name does not make a field polymorphic.

### 7.5. Having metadata but unable to read the value

`getDeclaredField` can find a `private` field, yet `get(receiver)` cannot be accessed from a caller outside valid scope and throws `IllegalAccessException`. In named modules, deep reflection is further restricted by `opens`; `setAccessible(true)` can throw `InaccessibleObjectException`, while `trySetAccessible()` can return `false`. Do not use permission-opening operations as a default requirement when you only need to list metadata.

## 8. Common errors and how to handle them

| Symptom | Cause | Solution |
| --- | --- | --- |
| `Leaf.class.getDeclaredField("marker")` throws `NoSuchFieldException` | `marker` is only declared in `Mid` and `Root`; `getDeclaredField` does not search parent classes | Traverse `getSuperclass()` and call `getDeclaredField` at each level |
| `getFields()` shows multiple `value` entries | Hidden `public` fields still exist | Use `getDeclaringClass()` to distinguish them |
| `getField("marker")` returns `Root.marker` instead of `Mid.marker` | `Mid.marker` is `private`; `getField` only gets `public` fields | Use `Mid.class.getDeclaredField("marker")` when the exact declared field is needed |
| Reading `Root.value` from a `Leaf` object returns `10` instead of `30` | `Field` is bound to `Root`'s declaration, without dynamic dispatch | Choose `Leaf.class.getDeclaredField("value")` if the child field is needed |
| Losing a field when putting the list into a `Map<String, Field>` | Keys collide and get overwritten | Use a list or a key that includes declaring class |
| `getField("LIMIT")` picks an unexpected interface | The algorithm checks direct interfaces in declaration order | Use `First.class.getField("LIMIT")` / `Second.class.getField("LIMIT")` |
| Getting `IllegalAccessException` on `Field.get` | Metadata exists, but the caller is not yet permitted to use it | Check modifiers, receiver, module, and access permissions |
| Relying on `getFields()` order | The API does not guarantee ordering | Sort or explicitly specify the declaring class |

## 9. Self-check

1. `class Base { public int x; }` and `class Derived extends Base { public String x; }`: how many fields named `x` can `Derived.class.getFields()` contain? **Two**: `Derived.x` and `Base.x`.
2. Which field does `Derived.class.getDeclaredField("x")` return? **`Derived.x`**, because the API only inspects directly declared fields.
3. Which field does `Base.class.getDeclaredField("x").get(derived)` read? **`Base.x`** on the same `derived` object.
4. If `Derived` does not declare `public x`, while `Base` declares `public x`, which field can `Derived.class.getField("x")` return? **`Base.x`**, after searching components according to the `getField` algorithm.
5. Why is `Map<String, Field>` insufficient to represent fields in a hierarchy? Because multiple different declarations share the same name and can overwrite each other in the map.

**Remember:** Field hiding changes how **a field name is resolved**, without removing the parent's field. When Reflection encounters multiple fields with the same name, inspect `getDeclaringClass()` and use the right API for the target scope. `Field` identifies one specific declaration, so `Field.get()` reads that exact declaration.

References: [Java Language Specification §8.3 (Field Declarations)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3), [Java SE 17 Class API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [Dev.java — Reading and Writing Fields](https://dev.java/learn/api/reflection-method-handles/reflection/fields/).