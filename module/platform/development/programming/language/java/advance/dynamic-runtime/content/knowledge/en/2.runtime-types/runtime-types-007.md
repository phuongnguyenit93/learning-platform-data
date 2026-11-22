# 2.7 Discovering superclasses, interfaces, nestmates, and permitted subclasses of sealed types

When holding a `Class<?>` object at runtime, Java Reflection allows inspecting type relationships recorded in the class metadata: the direct superclass, directly declared interfaces, classes in the same *nest*, and types permitted to extend/implement a `sealed` type. These four relationships have different meanings; you should not use the result of one API to infer the result of another.

This lesson uses **Java 17+** to cover both nestmates (available since Java 11) and sealed classes/interfaces (standardized in Java 17).

## 1. Map of APIs to know

| To discover | API on `Class<?>` | Result and meaning |
| --- | --- | --- |
| Direct superclass | `getSuperclass()` | A `Class<?>`, or `null` if there is no superclass according to the API |
| Superclass with generic information | `getGenericSuperclass()` | A `Type`; may be a `ParameterizedType` |
| Directly declared interfaces | `getInterfaces()` | `Class<?>[]` array; does not automatically collect all indirectly inherited interfaces |
| Direct interfaces with generics | `getGenericInterfaces()` | `Type[]` array |
| Nest host class | `getNestHost()` | `Class<?>` of the nest host; may be the class being inspected itself |
| Members in the same nest | `getNestMembers()` | `Class<?>[]` array including the nest host and recorded nestmates |
| Are two types in the same nest? | `isNestmateOf(Class<?> other)` | `boolean` |
| Is it a sealed type? | `isSealed()` | `boolean` |
| Directly permitted subclasses/subinterfaces | `getPermittedSubclasses()` | `Class<?>[]` array if sealed, otherwise `null` |

All of the operations above reflect JVM type information. They do **not** instantiate objects, and they do not mean scanning the entire classpath to find every subclass.

## 2. Discovering the superclass: `getSuperclass()`

For `class Child extends Parent`, `Child.class.getSuperclass()` returns `Parent.class`. This is **one direct parent level**. To traverse the entire superclass chain, repeat on the result until `null` is returned.

Easily confused cases:

- `Object.class.getSuperclass() == null` because `Object` is the root of the class hierarchy.
- `SomeInterface.class.getSuperclass() == null`, even though an object implementing an interface still inherits methods from `Object` through its class.
- `int.class`, `void.class` also return `null`.
- For an array class such as `String[].class`, the superclass is `Object.class`; arrays also implement `Cloneable` and `java.io.Serializable`.
- A `record` directly extends `java.lang.Record`; an enum has a superclass related to `java.lang.Enum`.

Backtracking example (this is a **supplementary method snippet**, placed inside any class):

~~~java
static void printSuperclassChain(Class<?> type) {
    for (Class<?> current = type;
         current != null;
         current = current.getSuperclass()) {
        System.out.println(current.getName());
    }
}
~~~

Use `getSuperclass()` when only the actual class relationship is needed. If the declaration is `class StringBox extends Box<String>` and you need to know the type argument `String`, use `getGenericSuperclass()` and then process `Type`/`ParameterizedType`. `getSuperclass()` only returns the `Class` of `Box`, without preserving generic arguments in the return type.

## 3. Discovering interfaces: `getInterfaces()`

`getInterfaces()` returns the interfaces **directly** declared in a class's `implements` clause, or the interfaces in an interface's `extends` clause:

~~~java
interface Audible {}
interface Trainable extends Audible {}
class Parent implements Audible {}
class Child extends Parent implements Trainable {}
~~~

Results:

- `Child.class.getInterfaces()` contains only `Trainable`, not `Audible`.
- `Parent.class.getInterfaces()` contains `Audible`.
- `Trainable.class.getInterfaces()` contains `Audible`.

Even though `Audible` does not appear in `Child`'s direct interface array, `Audible.class.isAssignableFrom(Child.class)` is still `true`. Assignability is computed across both superclasses and superinterfaces.

To collect **all related interfaces**, you must traverse both superinterfaces and superclasses while deduplicating. The helper snippet below uses `java.util.Set` and is **not a standalone program**:

~~~java
static void collectAllInterfaces(Class<?> type, java.util.Set<Class<?>> found) {
    if (type == null) return;

    for (Class<?> direct : type.getInterfaces()) {
        if (found.add(direct)) {
            collectAllInterfaces(direct, found);
        }
    }
    collectAllInterfaces(type.getSuperclass(), found);
}
~~~

You can call `collectAllInterfaces(Child.class, new java.util.LinkedHashSet<>())` to obtain both `Trainable` and `Audible`. `Set` avoids loops or reprocessing the same interface in a diamond hierarchy. For generics, `getGenericInterfaces()` returns `Type[]` to preserve declarations such as `Supplier<String>` instead of only getting `Supplier.class`. When checking assignability at runtime, prefer `isAssignableFrom` rather than inferring from interface names.

## 4. Nestmates: same-nest relationship, not inheritance

Since Java 11, the JVM supports **nests**: a group of classes/interfaces in the same runtime package identified by the class file as sharing a *nest host*. These members are **nestmates** and have access to each other's `private` members according to JVM access rules.

For example, the Java compiler typically makes the outermost class `House` the nest host and the nested class `House.Room` a nestmate. In that case:

- `House.Room.class.getNestHost()` returns `House.class`.
- `House.class.getNestMembers()` contains `House` and `House.Room`.
- `House.Room.class.isNestmateOf(House.class)` returns `true`.
- `House.Room` can read a `private` field of `House` without having to use `setAccessible(true)`.

A class that does not participate in a multi-member nest is usually its own nest host. This relationship comes from class file metadata (`NestHost`/`NestMembers`), and is **not** determined by `extends` or `implements`. Two classes with the same superclass are not necessarily nestmates; two classes in the same nest also do not necessarily have an inheritance relationship.

Do not confuse the APIs:

| API | Question answered |
| --- | --- |
| `getDeclaringClass()` | Which class/interface *declares* a member class? (May be `null` for top-level/local classes.) |
| `getEnclosingClass()` | Within the scope of which class is a class declared? |
| `getNestHost()` | Who is the host of the *nest* according to the JVM? |
| `getNestMembers()` | Which types are recorded in the same nest? |

`getNestMembers()` does not guarantee the order of elements other than the nest host and may contain duplicate entries; do not rely on order when comparing or displaying. *Hidden classes* dynamically added to a nest also do not necessarily appear in this array.

## 5. Sealed types and `getPermittedSubclasses()`

`sealed` restricts **which types are directly permitted** to extend a sealed class or extend/implement a sealed interface. In Java 17:

~~~java
sealed interface Shape permits Circle, Square {}
final class Circle implements Shape {}
non-sealed class Square implements Shape {}
~~~

`Shape.class.isSealed()` returns `true`. `Shape.class.getPermittedSubclasses()` returns `Class` objects representing `Circle` and `Square`. This list is about **permission to become a direct subtype**, not a list of all existing objects or all subtypes at every level.

A type that directly extends/implements a sealed type must declare an appropriate modifier: `final` (prevents further inheritance), `sealed` (continues restricting sub-branches), or `non-sealed` (reopens inheritance; only valid on a direct branch of a sealed type). For example, `Square` is `non-sealed`, so further subtypes can appear; `Shape.getPermittedSubclasses()` still only lists `Square` at the direct level.

Distinguish two results:

- `getPermittedSubclasses() == null`: the type being inspected **is not sealed** (including `final`, regular interfaces, arrays, and primitive types).
- `getPermittedSubclasses().length == 0`: the type being inspected **is sealed**, but the returned subtype array is empty; the API may not be able to return certain permitted subtypes that cannot be loaded/verified.

The order of results is not guaranteed. If you need to inspect multiple sealed levels, continue traversing those permitted subtypes for which `isSealed()` is `true`. A `non-sealed` branch does not have a closed list of all subclasses through this API.

## 6. Complete runnable Java 17 example

Save **all** of the following code into a file named `TypeDiscoveryDemo.java`. The non-`public` classes/interfaces at the bottom of the file belong to the same default package and are valid in Java.

~~~java
import java.util.Arrays;
import java.util.stream.Collectors;

public class TypeDiscoveryDemo {
    private static String names(Class<?>[] types) {
        if (types == null) return "null";
        return Arrays.stream(types)
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
    }

    public static void main(String[] args) {
        System.out.println("Child.superclass = " + Child.class.getSuperclass().getSimpleName());
        System.out.println("Child.interfaces = " + names(Child.class.getInterfaces()));
        System.out.println("Parent.interfaces = " + names(Parent.class.getInterfaces()));
        System.out.println("Trainable.superinterfaces = " + names(Trainable.class.getInterfaces()));
        System.out.println("Object.superclass = " + Object.class.getSuperclass());

        System.out.println("Room.nestHost = " + House.Room.class.getNestHost().getSimpleName());
        System.out.println("House.nestMembers = " + names(House.class.getNestMembers()));
        System.out.println("Room.isNestmateOf(House) = " + House.Room.class.isNestmateOf(House.class));
        System.out.println("Room.readPrivate = " + new House.Room().readPrivate(new House()));

        System.out.println("Shape.isSealed = " + Shape.class.isSealed());
        System.out.println("Shape.permits = " + names(Shape.class.getPermittedSubclasses()));
        System.out.println("Square.isSealed = " + Square.class.isSealed());
        System.out.println("Square.permits = " + names(Square.class.getPermittedSubclasses()));
    }
}

interface Audible {}
interface Trainable extends Audible {}
class Parent implements Audible {}
class Child extends Parent implements Trainable {}

class House {
    private final String secret = "private-ok";

    static class Room {
        String readPrivate(House h) {
            return h.secret;
        }
    }
}

sealed interface Shape permits Circle, Square {}
final class Circle implements Shape {}
non-sealed class Square implements Shape {}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 TypeDiscoveryDemo.java
java TypeDiscoveryDemo
~~~

Stdout:

~~~text
Child.superclass = Parent
Child.interfaces = [Trainable]
Parent.interfaces = [Audible]
Trainable.superinterfaces = [Audible]
Object.superclass = null
Room.nestHost = House
House.nestMembers = [House, Room]
Room.isNestmateOf(House) = true
Room.readPrivate = private-ok
Shape.isSealed = true
Shape.permits = [Circle, Square]
Square.isSealed = false
Square.permits = null
~~~

The `names` function simply formats simple names, sorts them so the output is easy to inspect, and handles `null`. In real tools, use `getName()`/`getTypeName()` when full names are needed: two classes in two different packages can have the same `getSimpleName()`. Also remember that the same binary name loaded by different class loaders can represent different `Class` objects.

Reading the key lines:

1. `Child.superclass` is `Parent`, while `Child.interfaces` is only `Trainable` because the API does not automatically fetch interfaces from the superclass.
2. `House.nestMembers` includes the host; `Room.readPrivate` demonstrates that nestmates allow valid private access handled by the compiler/JVM.
3. `Shape.permits` has exactly the **directly permitted children**; `Square.permits = null` because `Square` is `non-sealed`.

## 7. How to choose APIs in practice

- **Checking whether a class inherits from a base class:** use `Base.class.isAssignableFrom(candidate)` for a cross-level relationship check. Use `getSuperclass()` when you need to draw or analyze each link in the superclass chain.
- **Checking an interface/plugin contract:** use `SomeContract.class.isAssignableFrom(candidate)` to evaluate implementation relationships; use `getInterfaces()` and traverse recursively when you need to present which interfaces are declared at each level.
- **Analyzing nested classes and private access:** use `getNestHost()`, `getNestMembers()`, and `isNestmateOf()`; do not use `getDeclaredClasses()` as a substitute because it describes member class declarations, which is not equivalent to nest metadata.
- **Analyzing closed domain models:** for a sealed class/interface, call `isSealed()` first; then use `getPermittedSubclasses()` to determine the list of directly valid sub-branches. When checking an actual object, you must still check the object's runtime type and the corresponding assignability relationship.

## 8. Common mistakes and how to avoid them

| Misconception | Correct understanding |
| --- | --- |
| `getSuperclass() == null` means unrelated to any type | Interfaces, `Object`, primitives, and `void` can all return `null` per the API rules |
| `getInterfaces()` lists every interface, including via the superclass | It only lists the **direct** interfaces of the type being inspected; to get all of them, you must traverse further |
| Nested class and nestmate are synonyms | Nested class is a declaration relationship; nestmate is an access relationship based on JVM metadata |
| Two types with the same parent can access each other's `private` members | `private` access between nestmates depends on the nest, not on sharing a superclass |
| `getPermittedSubclasses() == null` means there are no subclasses | `null` only states that the type **is not sealed**; you cannot infer whether subclasses exist |
| The `permits` list is every possible subtype at every level | It only contains the **directly permitted subtypes**; a `non-sealed` branch can still be extended |
| Reflection array order is always fixed | Do not rely on the order of `getNestMembers()` or `getPermittedSubclasses()`; sort if stable display is needed |
| `getSimpleName()` is sufficient as a unique identifier | You need to consider the full name, module/package, and class loader in dynamic systems |

**Self-check:** For a `class B extends A implements I`, predict `B.class.getSuperclass()` and `B.class.getInterfaces()`. If `A` also implements `J`, does `J` automatically appear in `B.getInterfaces()`? For a sealed interface with a `non-sealed` branch, why does `getPermittedSubclasses()` only see the direct branch and cannot list all descendants?

Official reference: [Java SE 17 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).