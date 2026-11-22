# Choosing Declared Type or Actual Type When Discovering Members with Java Reflection

When a variable is declared with a superclass or interface yet is referencing an object of a subclass, Reflection can discover **two different sets of members** depending on which `Class<?>` object is chosen. This decision affects methods, fields, lookup results, and the stability of tools using Reflection.

## 1. Distinguishing Three Concepts of Type

Consider:

```java
Animal animal = new Dog();
```

- **Declared/static type** of the variable `animal` is `Animal`. The compiler checks ordinary calls like `animal.speak()` based on `Animal`'s contract. This type is known from the declaration in source code, or from metadata of a field, parameter, or return type.
- **Actual/runtime type** of the object is `Dog`. The expression `animal.getClass()` returns the `Class` object describing `Dog`, regardless of the variable carrying type `Animal`.
- **Declaring class of a member** is where a `Method` or `Field` is actually declared. Check with `member.getDeclaringClass()`; this class may differ from the `Class` used for the lookup.

The two starting points for Reflection therefore carry different meanings:

```java
Class<?> contractType = Animal.class;       // Discover from the declared type
Class<?> runtimeType = animal.getClass();   // Discover from the actual type: Dog
```

`Animal.class` is an explicit choice by the programmer; Java does not automatically infer the declared type of a variable from an object passed into a method that only accepts `Object`. Meanwhile `getClass()` is always based on the actual object and will throw `NullPointerException` if the reference is `null`.

**Key point:** which `Class<?>` you choose determines **the starting point for discovering metadata**. It does not mean specifying which method implementation executes when invoking an overridable instance method.

## 2. Which Type Choice Leads to Which Member Set?

Suppose `Parent` declares `parentOnly()`, while `Child extends Parent` additionally declares `childOnly()` and overrides `describe()`.

| How `Class<?>` is obtained | Meaning during discovery | Member `childOnly()` |
| --- | --- | --- |
| `Parent.class` | Discover API starting from `Parent` | Does not appear |
| `Child.class` | Discover API starting from `Child` | Can appear |
| `parentRef.getClass()`, when `parentRef = new Child()` | Discover the exact runtime class `Child` | Can appear |
| `method.getDeclaringClass()` | Identify where the method is declared, does not re-discover | Depends on `method` itself |

However, the result also depends on **which Reflection API family** is called on `Class<?>`:

| API | What does it discover? | Includes inherited members? |
| --- | --- | --- |
| `getDeclaredMethods()` / `getDeclaredMethod(name, parameterTypes...)` | Methods declared directly on the inspected type, whether `public`, `protected`, package-private, or `private` | No |
| `getMethods()` / `getMethod(name, parameterTypes...)` | `public` methods of the type and inherited `public` methods; may include methods from interfaces and `Object` | Yes, per inheritance rules |
| `getDeclaredFields()` / `getDeclaredField(name)` | Fields declared directly on the inspected type, at any access level | No |
| `getFields()` / `getField(name)` | `public` fields of the type and inherited `public` fields per Java rules | Yes |
| `getDeclaredConstructors()` / `getDeclaredConstructor(...)` | Constructors declared on the class itself, any access level | No; constructors are not inherited |
| `getConstructors()` / `getConstructor(...)` | `public` constructors of the class itself | No; constructors are not inherited |

Note that the word `declared` in the API name means "**declared directly on the queried type**", **not** "according to the declared type of the variable". For example, `object.getClass().getDeclaredMethods()` still lists methods declared on the runtime class of `object`.

The `getDeclared*` methods can still return metadata for non-public members; **seeing metadata does not mean having permission to access or invoke that member**. Using `setAccessible(true)` can be restricted by the module system (JPMS), access permissions, or the runtime environment.

## 3. Runnable Java 17+ Example: Superclass, Subclass, and Actual Invocation

Create a file named `ReflectionTypeChoiceDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionTypeChoiceDemo {
    static class Parent {
        public String describe() {
            return "Parent";
        }

        public String parentOnly() {
            return "parent-only";
        }

        private String secret = "parent-secret";
    }

    static final class Child extends Parent {
        @Override
        public String describe() {
            return "Child";
        }

        public String childOnly() {
            return "child-only";
        }

        private int childCount = 3;
    }

    private static boolean declaresMethod(Class<?> type, String name) {
        for (Method method : type.getDeclaredMethods()) {
            if (method.getName().equals(name)) {
                return true;
            }
        }
        return false;
    }

    private static boolean declaresField(Class<?> type, String name) {
        for (Field field : type.getDeclaredFields()) {
            if (field.getName().equals(name)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Parent reference = new Child();

        Class<?> declaredType = Parent.class;
        Class<?> runtimeType = reference.getClass();

        System.out.println("Declared type: " + declaredType.getSimpleName());
        System.out.println("Runtime type: " + runtimeType.getSimpleName());

        System.out.println("Parent declares childOnly: "
                + declaresMethod(declaredType, "childOnly"));
        System.out.println("Child declares parentOnly: "
                + declaresMethod(runtimeType, "parentOnly"));

        Method inherited = runtimeType.getMethod("parentOnly");
        System.out.println("parentOnly declared in: "
                + inherited.getDeclaringClass().getSimpleName());

        Method parentMethod = declaredType.getMethod("describe");
        System.out.println("Parent.describe invoked on Child: "
                + parentMethod.invoke(reference));

        Method childMethod = runtimeType.getMethod("childOnly");
        System.out.println("Child.childOnly invoked: "
                + childMethod.invoke(reference));

        System.out.println("Child declares childCount: "
                + declaresField(runtimeType, "childCount"));
        System.out.println("Child declares secret: "
                + declaresField(runtimeType, "secret"));
    }
}
```

Run with JDK 17 or higher:

```bash
javac ReflectionTypeChoiceDemo.java
java ReflectionTypeChoiceDemo
```

Output:

```text
Declared type: Parent
Runtime type: Child
Parent declares childOnly: false
Child declares parentOnly: false
parentOnly declared in: Parent
Parent.describe invoked on Child: Child
Child.childOnly invoked: child-only
Child declares childCount: true
Child declares secret: false
```

Explanation of easily confused points:

1. `declaredType` represents `Parent`; it has no metadata for `childOnly()`. In normal Java code, `reference.childOnly()` does not compile either because the variable `reference` has type `Parent`.
2. `runtimeType.getDeclaredMethods()` only contains methods **directly declared** on `Child`, not containing `parentOnly()`. Yet `runtimeType.getMethod("parentOnly")` finds the inherited `public` method, and `getDeclaringClass()` returns `Parent`.
3. `Parent.class.getMethod("describe")` returns metadata for `Parent.describe()`. When calling `invoke(reference)` on the `Child` object, dynamic dispatch of instance methods leads to the overridden version `Child.describe()`, so it prints `Child`. `static` or `private` methods do not participate in overriding this way.
4. `Child.class.getDeclaredField("childCount")` exists; `Child.class.getDeclaredField("secret")` would throw `NoSuchFieldException` because `secret` is declared in `Parent`. The example uses a loop to check instead of throwing an exception.

The two functions `declaresMethod` and `declaresField` in the example check only the **name**, which works because the names under inspection are not overloaded. When looking up a specific method in a real application, you must also include the parameter type list, e.g., `getMethod("find", String.class, int.class)`.

## 4. Distinguishing Metadata Discovery from How Java Dispatches Calls

There are two independent questions:

- **Is a `Method` found or not?** Depends on the starting `Class<?>` for the lookup and whether `getMethod` or `getDeclaredMethod` is used.
- **When calling `Method.invoke(receiver, args)`, which body runs?** For overridable instance methods, Java applies dynamic dispatch based on the actual class of `receiver`; the receiver object must still be compatible with the declared method and must satisfy access checks.

Therefore:

```java
Parent instance = new Child();
Method method = Parent.class.getMethod("describe");
Object value = method.invoke(instance); // "Child"
```

Do not view `Parent.class` as a way to "force running the body of `Parent.describe()`" when an override exists. If the real requirement is to invoke a specific superclass implementation, that is a different invocation mechanism problem, not solved merely by changing the `Class<?>` passed to `getMethod()`.

Conversely, Reflection on the runtime class can see methods specific to the subclass, even though the variable in Java is only `Parent`. This is useful for diagnostics or frameworks, yet can couple code to implementation details outside the public contract.

## 5. Discovering Inherited Fields: Walking the Class Tree When Needed

Fields **do not have dynamic dispatch like instance methods**. When a subclass hides a field name from a superclass (field hiding), the two declarations remain two separate `Field` objects and `getDeclaringClass()` helps distinguish their origin.

To learn which fields are declared **on each class** from the runtime class up to `Object`, traverse the class tree:

```java
Class<?> type = instance.getClass();

while (type != null) {
    for (java.lang.reflect.Field field : type.getDeclaredFields()) {
        System.out.println(type.getName() + " -> " + field.getName());
    }
    type = type.getSuperclass();
}
```

This is an **illustrative snippet** using an already-existing `instance` variable, not a standalone program. The order of results from `getDeclaredFields()` is not guaranteed by the API; if you need a deterministic order, sort before processing.

The `getSuperclass()` loop only follows the **superclass chain** and does not automatically descend into interfaces. If you need to discover interfaces, examine `getInterfaces()`, the interface hierarchy, and the corresponding member rules. Do not use this loop to bypass access checks by default; listing field names differs from reading field values.

Once you have a `Field` object, inspect `field.getDeclaringClass()` and `field.getType()` to know the field's declaring class and declared type. `field.getType()` also does not turn into the actual type of the value sitting inside the field; if you need to analyze the value, you must read a valid value first and only then consider `value.getClass()` when `value != null`.

## 6. When Should You Choose the Declared Type, and When the Actual Type?

### Choose the Declared Type or Interface When Working Against a Contract

Appropriate when building API callers, checking annotations on a defined contract, verifying methods users are permitted to call, or needing results independent of implementation classes that may change.

```java
Class<?> apiType = Runnable.class;
Method method = apiType.getMethod("run");
```

`Runnable.class` represents the exact `Runnable` contract. Having extra helper methods on the runtime object does not expand the API list your component intends to support. However, if business logic needs annotations declared on the implementation, Reflection on the interface alone may be **insufficient**: you must design a specific annotation-lookup policy and check the appropriate declaration locations.

### Choose the Actual Type When You Need to Know What the Object Actually Has

Appropriate when writing debug tools, serializers with an explicit policy, diagnostic inspectors, or code that uses implementation-specific metadata:

```java
Object value = obtainValue(); // Application-provided function, illustrative only
if (value != null) {
    Class<?> runtimeType = value.getClass();
    for (Method method : runtimeType.getDeclaredMethods()) {
        System.out.println(method.getName());
    }
}
```

This is also an **illustrative snippet**, not yet a standalone runnable program because `obtainValue()` is an application-defined function. `getDeclaredMethods()` here only collects methods directly declared on the implementation. If you need the list of `public` APIs the object can use, consider `getMethods()` instead of `getDeclaredMethods()`.

**Proxy/framework case:** a runtime object may be a proxy or dynamically generated class. `getClass()` then returns the proxy type, not necessarily the domain class you expect. For contract-based code, prefer `interface.class` or an explicitly specified `Class<?>`; for unwrapping a proxy's target type, use the mechanism provided by the actual framework rather than guessing the superclass.

### Wanting to Find Where a Member Is Actually Declared

Use `getDeclaringClass()` after finding a `Method` or `Field`. A method returned from `Child.class.getMethod("parentOnly")` can belong to `Parent`; this is not an error or a duplicate of the method on `Child`.

### Wanting to Handle a Subclass Safely from a Superclass-Typed Variable

If you genuinely need behavior that only `Child` has, first verify that the object has the right type:

```java
if (Child.class.isInstance(reference)) {
    Child child = Child.class.cast(reference);
    System.out.println(child.childOnly());
}
```

This is an illustrative snippet using the classes and variables from the example above. `isInstance` indicates whether the object is compatible with the checked type; `cast` performs a checked cast, helping avoid `ClassCastException`. Do not choose `getClass()` just to bypass API design when the contract can be expressed with an interface or superclass.

## 7. Common Mistakes and How to Check

| Misconception | Why it is wrong | Correct approach |
| --- | --- | --- |
| `reference.getClass()` returns the variable's declared type | It returns the runtime type | Use `DeclaredType.class`, or the declaration's own metadata if analyzing source/field/parameter |
| `getDeclaredMethods()` gets all callable methods, including inherited ones | It only gets direct declarations on the chosen `Class<?>` | Use `getMethods()` if inherited public methods are needed; or traverse the hierarchy per policy |
| `getMethods()` shows private methods too | This API only lists matching public methods | For private declaration metadata, use `getDeclaredMethods()` and handle access permissions |
| `Child.class.getDeclaredField("baseField")` finds a superclass field | Fields declared in the superclass are not in the subclass's `getDeclaredFields()` | Look up on `Parent.class` or traverse `getSuperclass()` |
| A method retrieved from `Parent.class` always runs the `Parent` version | Instance overrides are dynamically dispatched on `invoke` | Distinguish the found method from the executed body |
| Filtering only `Method.getName()` is sufficient in all cases | One name can have multiple overloads; the compiler can generate bridge/synthetic methods | Include parameter types, and check `isBridge()`/`isSynthetic()` when appropriate |
| Relying on the order of `getDeclaredMethods()` or `getDeclaredFields()` | The API does not guarantee a stable order | Sort by explicit criteria if order matters |
| Being able to see a `private Field` means being able to read its value | Metadata does not automatically grant access permission | Respect Java access rules and module restrictions; access only when authorized and justified |

A short selection workflow for Reflection tools:

1. Identify the goal: **inspecting a contract** or **discovering an actual implementation**.
2. Choose the `Class<?>` source: `Contract.class` when following an API, or `obj.getClass()` when following an object and `obj != null`.
3. Choose member scope: `getDeclared*` to view declarations on the class itself; `get*` when needing public members, including inherited ones.
4. Check `getDeclaringClass()` so inherited members are not mistaken for self-declared members. If you must discover private/protected members on superclasses, traverse the hierarchy intentionally.
5. If preparing to call via `invoke`, check the signature, receiver, access permissions, and note dynamic dispatch; do not infer execution solely from the `Class<?>` object used for lookup.

## 8. Self-Check

With `Parent parent = new Child();` in the program from section 3, try answering yourself:

- Is `parent.getClass() == Child.class` true? **True**, because the actual object is `Child`.
- Does `Child.class.getDeclaredMethod("parentOnly")` succeed? **No**, it throws `NoSuchMethodException` because the method is declared in `Parent`.
- What does `Child.class.getMethod("parentOnly").getDeclaringClass()` return? **`Parent.class`**, because this is an inherited public method.
- What does `Parent.class.getMethod("describe").invoke(parent)` return? **`"Child"`**, because dynamic dispatch selects the override on the runtime class.
- If you need to inspect all fields directly declared on each class in the hierarchy, what should you use? **`getDeclaredFields()` on each `Class<?>`**, combined with traversing `getSuperclass()` and an interface-handling policy if needed.

Conclusion for this article: **the declared type answers questions about the contract; the actual type answers questions about the existing object; the member's declaring class answers questions about the origin of metadata**. Choosing the right starting point before deciding between `get*` and `getDeclared*` will help avoid missing inherited members, misunderstanding overridden methods, and accidentally coupling code to implementation details.