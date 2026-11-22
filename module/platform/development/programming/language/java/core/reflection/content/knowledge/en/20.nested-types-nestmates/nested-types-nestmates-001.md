# How `getClasses()` Differs from `getDeclaredClasses()` in Java Reflection

## 1. What do the two methods return?

When using Reflection, each `Class<?>` object describes a Java type. Both of the following methods return `Class<?>[]` representing the **nested member types** (member class/member interface) of the type under inspection:

- `clazz.getClasses()`: retrieves **the `public` member types** declared in that type itself **and the `public` member types inherited from superclasses**.
- `clazz.getDeclaredClasses()`: retrieves **all member types declared directly** in that type, regardless of whether they are `public`, `protected`, package-private, or `private`; **it does not retrieve inherited member types**.

The method names are significant: `getClasses()` focuses on *public members* viewed from the current class; `getDeclaredClasses()` focuses on *declarations* directly in the current class. Both return **member types** (nested types), not every class the program uses, every type in the package, or all classes loaded by the JVM.

| Criterion | `getClasses()` | `getDeclaredClasses()` |
| --- | --- | --- |
| Access condition | Only `public` members | All access levels |
| Directly declared members | Yes, if `public` | Yes, regardless of access level |
| Members from superclass | Yes, if inherited `public` member | No |
| Local class inside a method | No | No |
| Anonymous class created inside a method | No | No |
| Type nested inside another member type | Does not recurse automatically | Does not recurse automatically |
| Return type | `Class<?>[]` | `Class<?>[]` |

A **member type** is a type declared directly in the body of a class or interface. This group can include nested classes, nested interfaces, enums, records, and annotation interfaces. A nested class can be `static` or a non-`static` inner class; the difference between the two methods here is based on **access level and where it is declared**, not on whether the nested class is `static` or not.

## 2. Runnable example on Java 17+

Save the entire program as **`NestedReflectionDemo.java`**:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class NestedReflectionDemo {
    public static class Base {
        public static class BasePublic {}
        protected static class BaseProtected {}
        private static class BasePrivate {}
    }

    public static class Derived extends Base {
        public static class OwnPublic {}
        protected static class OwnProtected {}
        static class OwnPackage {}
        private static class OwnPrivate {}
        public interface Marker {}
        public enum State { READY }
        public record Key(int id) {}

        public void sample() {
            class Local {}
            Object anonymous = new Object() {};
        }
    }

    private static void show(String label, Class<?>[] types) {
        String names = Arrays.stream(types)
                .map(Class::getSimpleName)
                .sorted()
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " -> " + names);
    }

    public static void main(String[] args) {
        show("getClasses()", Derived.class.getClasses());
        show("getDeclaredClasses()", Derived.class.getDeclaredClasses());
        show("Base.getDeclaredClasses()", Base.class.getDeclaredClasses());
    }
}
```

Compile and run:

```bash
javac NestedReflectionDemo.java
java NestedReflectionDemo
```

Output:

```text
getClasses() -> [BasePublic, Key, Marker, OwnPublic, State]
getDeclaredClasses() -> [Key, Marker, OwnPackage, OwnPrivate, OwnProtected, OwnPublic, State]
Base.getDeclaredClasses() -> [BasePrivate, BaseProtected, BasePublic]
```

The program intentionally uses `sorted()` before printing because **the API does not guarantee the order of elements** in the returned arrays. The output has been verified by compiling and running; the names are printed in alphabetical order.

### Explaining the output

1. `Derived.class.getClasses()` includes `OwnPublic`, `Marker`, `State`, and `Key` because they are `public` member types declared in `Derived`. It also includes `BasePublic` because this type is a `public` member inherited from `Base`.
2. `Derived.class.getClasses()` **does not include** `OwnProtected`, `OwnPackage`, `OwnPrivate`, `BaseProtected`, or `BasePrivate`: those types are not `public` members to be returned.
3. `Derived.class.getDeclaredClasses()` includes all seven member types declared directly in `Derived`, from `public` to `private`; it **does not include** `BasePublic` because `BasePublic` is declared in `Base`.
4. `Base.class.getDeclaredClasses()` shows all three types declared directly in `Base`. Being `private` or `protected` does not cause a type to be excluded from the result of `getDeclaredClasses()`.
5. `Local` and the anonymous class in `sample()` do not appear in either result: they are inside a method, not member types declared directly in the body of `Derived`.

**Common pitfall:** `getDeclaredClasses()` allows *seeing metadata* of a `private` type, but this does not automatically grant access to non-public constructors, fields, or methods of that type. Access rights when operating further with Reflection are still subject to Java's access rules and module boundaries.

## 3. Declaration scope and inheritance scope

Consider the structure:

```text
Base
├── public BasePublic
├── protected BaseProtected
└── private BasePrivate
     ↑
   Derived extends Base
   ├── public OwnPublic
   ├── protected OwnProtected
   ├── package-private OwnPackage
   ├── private OwnPrivate
   ├── public Marker (interface)
   ├── public State (enum)
   └── public Key (record)
```

- To find out which nested types `Derived` **declares itself**, use `Derived.class.getDeclaredClasses()`.
- To find the **`public` member types of `Derived`**, including those inherited from a superclass, use `Derived.class.getClasses()`.
- To inspect **every nested type declared in each class of the inheritance chain**, you must traverse each class and call `getDeclaredClasses()` individually. Such an inspection result **is not equivalent** to the members that can actually be inherited/accessed in the subclass; for example, a `private` member of the superclass still appears when inspecting the superclass directly.

Example illustrating how to traverse superclasses (the snippet below is a fragment placed inside a method that already has the variable `Class<?> target`):

```java
for (Class<?> current = target;
     current != null;
     current = current.getSuperclass()) {
    for (Class<?> nested : current.getDeclaredClasses()) {
        System.out.println(current.getName() + " declares " + nested.getName());
    }
}
```

This loop only walks the **superclass chain** and prints the direct declarations of each class; it does not automatically traverse superinterfaces or multi-level nested types. When you need to handle interfaces or nested types recursively, you must clearly define the search criteria and add the corresponding traversal.

## 4. Do not confuse with related APIs

- `getDeclaringClass()`: given a member type, finds the type that **directly declares** it. For example, `Derived.OwnPublic.class.getDeclaringClass()` returns `Derived.class`.
- `getEnclosingClass()`: finds the enclosing class in terms of declaration; also useful for some cases of local/anonymous classes. This is a different question from listing member types.
- `getNestHost()` and `getNestMembers()`: deal with JVM **nestmates**, related to private access rules between classes in the same nest. A nestmate list is not equivalent to the result of `getDeclaredClasses()` or `getClasses()`.
- `getDeclaredMethods()`, `getDeclaredFields()`, and `getDeclaredConstructors()`: list other kinds of members, not a substitute for finding nested classes/interfaces.

Both main methods only inspect **one level of member types**. If `Outer` declares `Inner` and `Inner` in turn declares `Deep`, then `Outer.class.getDeclaredClasses()` can contain `Inner`, but **does not directly contain `Deep`**. To find `Deep`, continue inspecting `Inner.class.getDeclaredClasses()`.

## 5. Choosing a method in practice

| Need | Choice and reason |
| --- | --- |
| Display `public` nested types that a class exposes to API users, including inherited ones | `getClasses()` |
| Write a tool to analyze the declared structure of a class, including `private` nested types | `getDeclaredClasses()` |
| Find all nested type declarations across multiple classes in an inheritance chain | Traverse superclasses and call `getDeclaredClasses()` on each class |
| Find local classes, anonymous classes, or every loaded class | Neither method solves this directly |
| Find members of nested types deeper than one level | Traverse recursively from the discovered member types |

When building a metadata scanner, you may need to handle types with the same simple name across multiple classes. To identify them reliably, use `Class.getName()` or compare `Class<?>` objects directly, rather than relying only on `getSimpleName()`. You should also not rely on element positions in the array because order is not guaranteed.

## 6. Common misconceptions

1. **“`getDeclaredClasses()` gets superclass types too because it gets all access levels.”** False. “Declared” restricts it to member types **declared directly on the target type**.
2. **“`getClasses()` gets all nested classes of the current class.”** False. It only returns **public member types**; `protected`, package-private, and `private` are excluded.
3. **“The two APIs only recognize `static nested class`.”** False. A non-`static` inner member class is also a member type and follows the same rules regarding declaration location and access level.
4. **“`getDeclaredClasses()` returns local and anonymous classes.”** False. They are not member classes declared directly in the body of the type under inspection.
5. **“The first element is always the first declared type.”** False. There is no ordering contract; sort first when stable output is needed.
6. **“Seeing a `private nested class` in the result means you can call its private constructor.”** False. Listing metadata and having access permission to instantiate objects or invoke members are two separate issues.

## 7. Self-check

**Question:** If `Parent` has `public static class Shared` and `private static class Secret`, and `Child extends Parent` has `private static class Internal`, then:

- Which of the three types are in `Child.class.getClasses()`?
- Which of the three types are in `Child.class.getDeclaredClasses()`?
- How can `Secret` be found using Reflection?

**Answer:** `Child`'s `getClasses()` contains `Shared`; `Child`'s `getDeclaredClasses()` contains `Internal`; to list `Secret`'s metadata, call `Parent.class.getDeclaredClasses()`. This is a classic example of how **`public` + inherited** differs from **directly declared + all access levels**.

## References

- [Java SE 21 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): contract of `getClasses()`, `getDeclaredClasses()`, and related methods.
- [Java Language Specification, `8.5 — Member Class and Interface Declarations`](https://docs.oracle.com/en/java/javase/specs/jls/se21/html/jls-8.html#jls-8.5): definition of member classes and member interfaces.
