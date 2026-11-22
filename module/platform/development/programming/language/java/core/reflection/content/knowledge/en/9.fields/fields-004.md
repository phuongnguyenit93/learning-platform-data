# Reading instance fields with a properly typed object in Java Reflection

## 1. The problem: a `Field` needs an object to read its value

Reflection lets you obtain a field's metadata even before having a concrete object:

```java
Field field = Person.class.getDeclaredField("name");
```

However, **an instance field belongs to each object's state**. To read its value, you must pass a compatible **receiver object** to `Field.get(Object obj)`:

```java
Person person = new Person("Lan");
Object value = field.get(person);
```

In this illustrative example, `Person` must be a class with a `name` field, a constructor accepting `String`, and access permissions must be valid. This is a code snippet explaining syntax, not a standalone program.

There are two separate conditions: **(1) the receiver must have a type compatible with the class declaring the field; (2) the calling code must have permission to access that field**. If the receiver has the wrong type, Java Reflection cannot retrieve the field value for the selected metadata, even if the field has the `public` modifier.

Core question of this lesson: what type does `field.get(obj)` require `obj` to have, and what are the differences between the field's declaring class, the object's runtime class, inherited fields, and same-named fields?

## 2. Exact rules of `Field.get(Object)`

API signature:

```java
public Object get(Object obj)
        throws IllegalArgumentException, IllegalAccessException
```

When `field` represents an **instance field**:

- `obj` must be **non-`null`**.
- `obj` must be an instance of **the class or interface declaring the field**, or a compatible subclass/implementing class. For a field declared in `Parent`, receivers `new Parent()` and `new Child()` when `Child extends Parent` are both type-valid.
- `Field.getDeclaringClass()` indicates **the type declaring the field**. This is the reference point to check against the receiver, not the class that happened to be used to look up the field.
- When the receiver has the wrong type: `IllegalArgumentException`. When the receiver is `null` for an instance field: `NullPointerException`.
- When the receiver has the right type but the caller lacks permission to read the field under current access checks: `IllegalAccessException`.
- When reading a primitive field like `int`, `get` returns a wrapper object, e.g., `Integer`. When a reference-type field holds `null`, the result of `get` can also be `null`: do not confuse a **null field value** with a **null receiver**.

**Difference with static fields:** if a field has the `static` modifier, Java ignores the receiver passed to `Field.get` (`null` can be passed), because the value belongs to the class, not a specific object. This lesson focuses on **instance fields**.

You can predict a properly typed receiver with the expression:

```java
Class<?> owner = field.getDeclaringClass();
boolean compatible = owner.isInstance(obj);
```

`Class.isInstance(null)` returns `false`, so the expression safely checks even when the receiver may be null. It only verifies **type compatibility**; it does not grant access permission for a `private` field or a restricted class/package.

## 3. Standalone runnable Java 17+ example: valid type, wrong type, and `null`

Create file **`InstanceFieldReadDemo.java`**:

```java
import java.lang.reflect.Field;

public class InstanceFieldReadDemo {
    public static class Parent {
        public String label = "parent";
    }

    public static final class Child extends Parent {
        public String label = "child";
        public int count = 7;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Parent parent = new Parent();
        Child child = new Child();

        Field parentLabel = Parent.class.getDeclaredField("label");
        Field childLabel = Child.class.getDeclaredField("label");
        Field count = Child.class.getDeclaredField("count");

        System.out.println("Parent.label from Parent: " + parentLabel.get(parent));
        System.out.println("Parent.label from Child: " + parentLabel.get(child));
        System.out.println("Child.label from Child: " + childLabel.get(child));

        System.out.println("Parent field accepts Child: "
                + parentLabel.getDeclaringClass().isInstance(child));
        System.out.println("Child field accepts Parent: "
                + childLabel.getDeclaringClass().isInstance(parent));

        Object countValue = count.get(child);
        System.out.println("Child.count: " + countValue);
        System.out.println("Count declared type: " + count.getType().getName());
        System.out.println("Count returned type: "
                + countValue.getClass().getSimpleName());

        try {
            childLabel.get(parent);
        } catch (IllegalArgumentException e) {
            System.out.println("Wrong receiver: IllegalArgumentException");
        }

        try {
            childLabel.get(null);
        } catch (NullPointerException e) {
            System.out.println("Null receiver: NullPointerException");
        }
    }
}
```

Compile and run from the directory containing the file:

```bash
javac --release 17 InstanceFieldReadDemo.java
java InstanceFieldReadDemo
```

Stdout result:

```text
Parent.label from Parent: parent
Parent.label from Child: parent
Child.label from Child: child
Parent field accepts Child: true
Child field accepts Parent: false
Child.count: 7
Count declared type: int
Count returned type: Integer
Wrong receiver: IllegalArgumentException
Null receiver: NullPointerException
```

**Why does the program produce the output above?**

1. `parentLabel` is declared in `Parent`, so it can be read from a `Parent` or a `Child`. A `Child` object **still contains the instance state of the inherited `Parent` part**.
2. `Child` declares its own `label` with the same name: that is **field hiding**. The two `Field` objects represent **two different declarations**. `parentLabel.get(child)` still reads `Parent.label` and returns `parent`; `childLabel.get(child)` reads `Child.label` and returns `child`.
3. `childLabel` is declared in `Child`, so the `parent` receiver is invalid: a `Parent` instance is not necessarily a `Child`. Java throws `IllegalArgumentException`.
4. `childLabel.get(null)` has no object holding instance state, so it throws `NullPointerException`.
5. `count` is declared as `int`; `Field.get` returns `Integer` after boxing. `count.getType()` remains `int.class`, while the runtime type of the result is `Integer.class`.

The example deliberately uses `public` fields in `public` nested classes to highlight **receiver type checking** without mixing in access permission errors.

## 4. Correctly understanding declaring class vs. runtime type

Suppose:

```java
class Animal {
    public int age = 3;
}

class Dog extends Animal {
    public String breed = "Shiba";
}
```

This is a **standalone snippet of type declarations**; to run it, place the two classes in files matching Java file naming rules, or use them inside a program with `main`.

With:

```java
Field ageField = Animal.class.getDeclaredField("age");
Field breedField = Dog.class.getDeclaredField("breed");

Dog dog = new Dog();
Animal animal = new Animal();

Object a = ageField.get(dog);     // Valid: Dog is an Animal
Object b = ageField.get(animal);  // Valid: Animal is an Animal
Object c = breedField.get(dog);   // Valid: Dog has field breed
// breedField.get(animal);        // IllegalArgumentException
```

These statements reside in a method declaring `throws ReflectiveOperationException` or handling the appropriate exceptions.

Do not reverse the relationship:

- **Field declared in superclass + subclass object:** type-valid.
- **Field declared in subclass + superclass object:** invalid, unless the passed object is actually an instance of the subclass.
- **Field declared in class A + unrelated object B:** invalid.
- **Field declared in A + reference variable with static type `Object` holding an instance of A:** still valid, because `Field.get` checks the **runtime object**, not limited by the declared type of the Java variable.

Example:

```java
Object receiver = new Dog();
Object value = Animal.class.getDeclaredField("age").get(receiver);
```

The receiver is valid because the runtime object is `Dog`. Having the variable `receiver` with static type `Object` does not cause `Field.get` to throw `IllegalArgumentException`.

You can remember this with the expression:

```java
field.getDeclaringClass().isInstance(receiver)
```

However, this expression does not check whether the field is `static` and does not replace access permission verification. To avoid ambiguity, handle those two conditions separately.

## 5. Reading the right field with inheritance and duplicate names

### 5.1. `getDeclaredField` fixes the declaring class

`Parent.class.getDeclaredField("label")` returns the field declared **directly inside `Parent`**. Similarly, `Child.class.getDeclaredField("label")` returns the field declared **directly inside `Child`**; the two fields share the same name but have different declaring classes.

This is why **the `Field` object determines which data slot is read**, while the receiver determines **which instance that data slot is read on**. A `Field` does not automatically switch to the declaration closest to the subclass just because a subclass instance is passed to `get`.

### 5.2. `getField` can find inherited public fields

`Child.class.getField("name")` can find a `public` field inherited from a superclass if `Child` does not declare a hiding public field with the same name according to Reflection rules. However, when handling field hiding, you should fetch by the exact target class using `getDeclaredField` and inspect `getDeclaringClass()`.

To find a field with a given name along the **superclass chain**, you can traverse classes from child up to parent and take the first declaration found:

```java
static Field findNearestDeclaredField(Class<?> start, String fieldName)
        throws NoSuchFieldException {
    for (Class<?> current = start;
         current != null;
         current = current.getSuperclass()) {
        try {
            return current.getDeclaredField(fieldName);
        } catch (NoSuchFieldException ignored) {
            // This class does not declare that field; try the parent class.
        }
    }
    throw new NoSuchFieldException(fieldName);
}
```

This is an **illustrative method** (place in a utility class and import `java.lang.reflect.Field`), not a complete file. It finds **the declaration closest to the subclass**, does not automatically check whether it is an instance or static field, and does not guarantee the field is readable by access rules. If a specific superclass field is needed, choose `Parent.class.getDeclaredField("...")` right from the start.

### 5.3. Field hiding differs from method overriding

Methods can be overridden and perform dynamic dispatch. For fields, Java **does not have field overriding** in the sense of dynamic dispatch like methods. When two classes have a field with the same name, access via `Field` is determined by **the declaration that the `Field` represents**, even if the receiver's runtime type is a subclass.

Therefore, do not apply the intuition "the object is a Child, so any field named `label` must come from Child" to Reflection. Always check `Field.getDeclaringClass()`.

## 6. A safer helper method for reading instance fields

If writing a mapper or diagnostic tool, you can create a helper that enforces receiver compatibility upfront, avoiding accidentally calling a static field or reading from an incompatible object type.

Place the following method in a class that imports `java.lang.reflect.Field`, `java.lang.reflect.Modifier`, and `java.util.Objects`:

```java
static Object readInstanceField(Field field, Object receiver)
        throws IllegalAccessException {
    Objects.requireNonNull(field, "field");

    if (Modifier.isStatic(field.getModifiers())) {
        throw new IllegalArgumentException("Expected an instance field");
    }

    Class<?> owner = field.getDeclaringClass();
    if (!owner.isInstance(receiver)) {
        throw new IllegalArgumentException(
                "Receiver must be an instance of " + owner.getName()
        );
    }

    return field.get(receiver);
}
```

Meaning:

- `Objects.requireNonNull(field)` detects missing field metadata early.
- `Modifier.isStatic(...)` verifies that the `Field` object represents an **instance field** within the helper's scope.
- `owner.isInstance(receiver)` accepts instances of `owner` as well as compatible subclasses; for `null` it returns `false`.
- When the receiver is valid, `field.get(receiver)` can still throw `IllegalAccessException` if the field is not accessible. The helper **does not bypass access control on its own**, and this is intentional by design.

The helper deliberately converts both a null receiver and a wrong type into its own `IllegalArgumentException` message. That is a **helper-defined contract**; if you call the raw `Field.get(null)` API on an instance field, Java throws `NullPointerException` per the official contract.

If using the helper in a system receiving external data, clearly define the exception and access-permission policy instead of automatically opening all fields.

## 7. Valid receiver type can still fail with `IllegalAccessException`

Example:

```java
public class Account {
    private String token = "secret";
}
```

The illustration must be placed in an appropriate context to compile (top-level public class in `Account.java`). Code outside the class can look up the metadata:

```java
Field tokenField = Account.class.getDeclaredField("token");
Account account = new Account();
Object value = tokenField.get(account); // May throw IllegalAccessException
```

Here `account` has the right type, but `token` is `private`. If the Reflection caller does not have permission to access private members, `get` is blocked with `IllegalAccessException`. The cause is **completely different** from `IllegalArgumentException` when the receiver has the wrong type.

The preferred approach is to use **a public getter or an API provided by the class** if you control the source code. Only use deep reflection when the problem truly requires it and access rules allow. `trySetAccessible()` can return `false`; `setAccessible(true)` can be blocked, especially when the class resides in a package of a named module that is not appropriately `opens`-ed. Do not assume every private field is readable simply because you found the `Field`.

Distinguish:

| Case | Receiver right type? | Access permission? | Result |
| --- | --- | --- | --- |
| `public` field of a public class, valid access | Yes | Yes | Returns value |
| `public` field of `Parent`, receiver `Child extends Parent` | Yes | Yes | Returns the `Parent` state portion on the `Child` object |
| Field of `Child`, receiver is only `Parent` | No | Cannot determine success | `IllegalArgumentException` |
| Instance field, receiver is `null` | No | Cannot determine success | `NullPointerException` |
| Private field, receiver right type but caller lacks permission | Yes | No | `IllegalAccessException` |
| Static field | Receiver is ignored | Still must be valid | Can pass `null` |

In cases combining multiple errors, you need to analyze the API conditions and access control; the table focuses on prominent isolated causes.

## 8. Reading primitive and reference fields

`Field.get(Object)` always returns `Object`, so primitive values are automatically **boxed**:

```java
Field countField = Child.class.getDeclaredField("count");
Object boxed = countField.get(child);   // Integer(7)
int count = (Integer) boxed;            // Unboxing
```

This snippet references `Child` and the `child` variable from the program in section 3.

When the field type is known exactly, the API also provides primitive-typed read methods, such as `getInt(receiver)`, `getLong(receiver)`, and `getBoolean(receiver)`. They avoid returning a wrapper in the call signature and apply appropriate primitive widening conversions. **Do not call `getInt` on an `Integer` reference field expecting automatic unboxing**, as these specialized methods are not arbitrary type conversion tools.

For reference-type fields:

```java
String text = (String) field.get(receiver);
```

casting to `String` is only valid when the value is actually a `String` or `null`; if the value belongs to a different class, the cast can throw `ClassCastException`. You can check `field.getType()` to know **the field's declared type**, though generic type parameters require `getGenericType()` as well if generic signature analysis is needed. Do not call `getClass()` directly on the result without checking for `null`.

## 9. Common mistakes when reading instance fields

| Mistake | Symptom | Fix |
| --- | --- | --- |
| `field.get(null)` on an instance field | `NullPointerException` | Pass a real, non-`null` instance |
| Passing an object not belonging to the declaring class or a subclass | `IllegalArgumentException` | Check `field.getDeclaringClass().isInstance(receiver)` |
| Using a `Field` from `Child` to read on a plain `Parent` | `IllegalArgumentException` | Obtain the `Field` from the appropriate class or pass a `Child` receiver |
| Assuming a superclass field automatically switches to a same-named subclass field | Reads the wrong value during field hiding | Check `getDeclaringClass()`; pick the right declaration |
| Right receiver but private field is not accessible | `IllegalAccessException` | Prefer public APIs; check module and access permissions |
| Calling `getDeclaredField` on a subclass for a field only declared in a superclass | `NoSuchFieldException` | Look up on the declaring class or traverse superclasses |
| Casting `Object` from an `int` field directly to `String` | `ClassCastException` | Use the corresponding wrapper, `getInt`, or type check |
| Using `field.getType().isInstance(receiver)` to validate the receiver | Wrong target check because `getType()` is the field's **value type** | Use `getDeclaringClass().isInstance(receiver)` |
| Forgetting to distinguish `static` and instance fields | Passing unnecessary receiver or misusing a helper | Check `Modifier.isStatic(field.getModifiers())` |

### Distinguishing three types in the same operation

Read the expression:

```java
Field field = Parent.class.getDeclaredField("label");
Object receiver = new Child();
Object value = field.get(receiver);
```

- `field.getDeclaringClass() == Parent.class`: **the field's declaring type**.
- `receiver.getClass() == Child.class`: **the runtime type of the object holding the value**.
- `field.getType() == String.class`: **the declared type of the field's value**.

To validate the object passed to `get`, compare **the declaring class with the runtime receiver**, not `field.getType()` with the receiver. `getType()` is useful when checking or converting **the returned value**, not when identifying the field's owner.

## 10. Self-check questions

1. Given `Base` and `Derived extends Base`, if `age` is declared in `Base`, is `Base.class.getDeclaredField("age").get(new Derived())` type-valid?
2. If `Derived` has an additional field `score`, what happens when calling `Derived.class.getDeclaredField("score").get(new Base())`?
3. How does `field.getDeclaringClass()` differ from `field.getType()`?
4. What exception does `field.get(null)` throw for an instance field? If the field is `static`, how is the receiver handled?
5. Why can reading a private field fail even when `owner.isInstance(receiver)` returns `true`?
6. Both parent and child classes declare a field named `label`: which field will a `Field` object obtained from the parent class read when the receiver is a child object?

**Short answers:** (1) valid; (2) `IllegalArgumentException`; (3) one is the class declaring the field, the other is the field's value type; (4) `NullPointerException` for instance fields, receiver is ignored for static fields; (5) because access permission is also checked; (6) the parent class's `label` declaration.

## 11. Takeaways when applying

For **instance fields**, the proper read pattern is:

```java
if (field.getDeclaringClass().isInstance(receiver)) {
    Object value = field.get(receiver);
    // Use value according to the appropriate declared type.
}
```

This is a snippet placed inside a method that handles `IllegalAccessException`, applicable specifically to instance fields. It accurately reflects the receiver compatibility rule, though real-world programs must also handle invalid receivers, access permissions, and `null` values.

Three questions to answer before any Reflection read call: **where is the field declared? what type of object is the receiver actually? does the caller have access permission?** Answering these three questions accurately helps clearly distinguish type errors, `null` errors, and access errors, while avoiding reading the wrong field under inheritance or field hiding.

API reference: [Java SE `Field.get(Object)`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#get(java.lang.Object)).