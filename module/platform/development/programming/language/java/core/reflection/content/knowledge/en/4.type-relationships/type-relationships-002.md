# Class.getInterfaces() — Returns Only Direct Interfaces

## 1. Meaning and the Word "Direct"

In Java Reflection, `Class<?>[] getInterfaces()` is a method of `java.lang.Class` that tells you the **interfaces directly declared** by the type under inspection. The method returns an **array of `Class<?>` objects** representing interfaces; it does not return instances implementing the interfaces, does not return names as `String`, and does not automatically traverse the entire inheritance tree.

- For a **class**, these are the interfaces appearing directly in the `implements` clause of the class itself.
- For an **interface**, these are the superinterfaces appearing directly in the `extends` clause of the interface itself.
- Interfaces obtained **indirectly** via a superclass or via another superinterface do not automatically appear in the result for the type under inspection.
- The result is an empty array `Class<?>[0]` if there are no direct interfaces, not `null`. Elements in the array follow the declaration order in `implements` or `extends`.

Quick example:

~~~java
interface A {}
interface B extends A {}
class Parent implements A {}
class Child extends Parent implements B {}
~~~

Here:

| Expression | Directly returned interfaces | Important note |
| --- | --- | --- |
| `A.class.getInterfaces()` | `[]` | `A` does not `extends` any interface. |
| `B.class.getInterfaces()` | `[A]` | `B extends A` directly. |
| `Parent.class.getInterfaces()` | `[A]` | `Parent implements A` directly. |
| `Child.class.getInterfaces()` | `[B]` | `Child` only declares `implements B`; `A` is still a valid type relationship, but it is not in the direct array of `Child`. |

Separate two questions: **"Which interfaces does this type directly declare?"** uses `getInterfaces()`; **"Can this type be treated as a specific interface?"** uses a type-relationship check like `SomeInterface.class.isAssignableFrom(Target.class)`.

## 2. Runnable Example with Java 17+

Save the entire following program as `DirectInterfacesDemo.java`:

~~~java
import java.io.Serializable;
import java.util.Arrays;
import java.util.function.Supplier;
import java.util.stream.Collectors;

interface Root {}
interface Middle extends Root {}
interface Marker {}

class Parent implements Serializable {}
class Child extends Parent implements Middle, Marker {}

class GenericSample implements Supplier<String> {
    @Override
    public String get() {
        return "ok";
    }
}

public class DirectInterfacesDemo {
    private static String directNames(Class<?> type) {
        return Arrays.stream(type.getInterfaces())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Child: " + directNames(Child.class));
        System.out.println("Parent: " + directNames(Parent.class));
        System.out.println("Middle: " + directNames(Middle.class));
        System.out.println("Root: " + directNames(Root.class));
        System.out.println("String[]: " + directNames(String[].class));
        System.out.println("int: " + directNames(int.class));

        System.out.println("Root assignable from Child: "
                + Root.class.isAssignableFrom(Child.class));
        System.out.println("Serializable assignable from Child: "
                + Serializable.class.isAssignableFrom(Child.class));

        System.out.println("Generic direct: "
                + GenericSample.class.getInterfaces()[0].getTypeName());
        System.out.println("Generic signature: "
                + GenericSample.class.getGenericInterfaces()[0].getTypeName());
    }
}
~~~

Compile and run:

~~~bash
javac DirectInterfacesDemo.java
java DirectInterfacesDemo
~~~

Expected output:

~~~text
Child: [Middle, Marker]
Parent: [Serializable]
Middle: [Root]
Root: []
String[]: [Cloneable, Serializable]
int: []
Root assignable from Child: true
Serializable assignable from Child: true
Generic direct: java.util.function.Supplier
Generic signature: java.util.function.Supplier<java.lang.String>
~~~

Point-by-point analysis:

1. `Child` **directly** `implements Middle, Marker`, so `getInterfaces()` returns `Middle` before `Marker`, matching the declaration order. `Root` is not in this array even though `Middle extends Root`.
2. `Serializable` belongs to the `implements` clause of `Parent`, so `Parent.class.getInterfaces()` contains `Serializable` while `Child.class.getInterfaces()` does not. However, a `Child` is also `Serializable` by inheriting from `Parent`.
3. `Middle` is an **interface**, so the result `[Root]` comes from `extends Root`. `Root` does not extend any interface, so the result is empty.
4. Array types and primitive types have their own rules; see the next section.
5. `isAssignableFrom` returns `true` even for indirect relationships via superinterfaces or superclasses; thus it serves a different purpose from `getInterfaces()`.
6. `Supplier<String>` is returned as the raw `Class` `Supplier` when calling `getInterfaces()`; the `<String>` information is only visible via `getGenericInterfaces()`.

## 3. Special Cases

| Kind of `Class` | Result of `getInterfaces()` |
| --- | --- |
| Class declaring `implements I, J` | `[I, J]` in declaration order. |
| Class without `implements` | Empty array, even if its superclass implements interfaces. |
| Interface declaring `extends I, J` | `[I, J]` in declaration order. |
| Interface without `extends` | Empty array. |
| Array type, such as `String[]` or `int[]` | `[Cloneable, java.io.Serializable]`, in this exact order, even without `implements` in source code. |
| Primitives such as `int`, `boolean`, or `void.class` | Empty array. |

In particular, `String[].class.getInterfaces()` does not look up interfaces implemented by `String`; it reflects the interfaces of the **array type itself**. Similarly, `int.class.getInterfaces()` is empty, but `int[].class.getInterfaces()` has two elements.

## 4. Distinguishing from Related APIs

| API | Question the API answers |
| --- | --- |
| `type.getInterfaces()` | Which interfaces are directly implemented by the class or directly extended by the interface? |
| `type.getGenericInterfaces()` | With which generic type parameters, if any, are those direct interfaces declared? Returns `Type[]`, not `Class<?>[]`. |
| `type.getSuperclass()` | What is the direct superclass of the class? Not used to list interfaces. |
| `I.class.isAssignableFrom(type)` | Can a variable of type `I` accept an object of `type`, considering both indirect inheritance and implementation? |
| `I.class.isInstance(object)` | Is the actual object compatible with interface `I`? |

The two methods `isAssignableFrom` and `isInstance` are better suited when you want to **check type assignability**. For example, `Root.class.isAssignableFrom(Child.class)` is `true` even though `Root` is not in `Child.class.getInterfaces()`. With `isInstance`, you pass an object; with `isAssignableFrom`, you pass a `Class<?>` object.

`getGenericInterfaces()` still lists only **direct** interfaces, but preserves generic descriptions: in the example, the result contains `java.util.function.Supplier<java.lang.String>`. Do not cast every element of `Type[]` to `ParameterizedType` because an interface can appear as a raw `Class`; check `instanceof` before casting.

## 5. When You Need to Know All Ancestor Interfaces

If you need to list interfaces obtained across multiple levels, `getInterfaces()` is only the starting step. For `Child` in the example, the algorithm must read the direct interfaces of `Child`, continue through `getInterfaces()` of each discovered interface, also examine `Parent` via `getSuperclass()`, and record each `Class<?>` exactly once in a `Set<Class<?>>` to avoid duplicates when multiple branches converge.

For example, `Child` has two direct interfaces `[Middle, Marker]`, `Middle extends Root`, and `Parent implements Serializable`. If you traverse each interface branch depth-first before moving to the next branch and finally walk up to the superclass, the resulting order is `[Middle, Root, Marker, Serializable]`. This is an order **chosen by the algorithm**, not a list that a single call to `Child.class.getInterfaces()` returns.

When you only need a true/false answer for one interface, `Root.class.isAssignableFrom(Child.class)` is clearer and simpler. You only need to traverse the graph yourself when you must collect all interfaces; in that case, use `Class<?>` identity as the deduplication key, clearly define the traversal order, and decide whether to include the input interface itself or only ancestors. Algorithm choices and diamond graph scenarios are covered in detail in the article "Traversing the interface graph and avoiding duplicates".

## 6. Common Mistakes and How to Self-Check

- **Confusing direct with the entire inheritance tree:** `Child.class.getInterfaces().length == 0` does not prove `Child` implements no interfaces; a superclass may have already implemented them.
- **Missing superinterfaces:** a class `implements Middle` does not cause `Root` to appear directly in the class's array, even though `Middle extends Root`.
- **Applying general assumptions mechanically to arrays:** every array type returns `Cloneable` and `Serializable` in the specified order.
- **Expecting generic information from `Class<?>[]`:** use `getGenericInterfaces()` when you must read `Supplier<String>` or `Comparable<T>` from direct declarations.
- **Accessing `getInterfaces()[0]` without checking:** the array may be empty; check `length` first to avoid `ArrayIndexOutOfBoundsException`.
- **Confusing the result with instances:** `getInterfaces()` returns metadata about the *type*; it does not create an instance or invoke interface methods.

Self-check with `class D extends Parent {}` in the example: `D.class.getInterfaces()` must be `[]`, whereas `Serializable.class.isAssignableFrom(D.class)` must be `true`. Being able to explain both results means you have properly grasped the meaning of **"direct"**.

**Reference:** [Java SE 17 API — java.lang.Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), sections `getInterfaces()`, `getGenericInterfaces()`, and `isAssignableFrom()`.
