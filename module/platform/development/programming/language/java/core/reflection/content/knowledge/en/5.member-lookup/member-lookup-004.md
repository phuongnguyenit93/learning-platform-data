# Inherited Public Members Differ from Members Declared on the Class Itself

## 1. Two Different Questions When Looking Up a Member

In Java Reflection, **public** describes accessibility according to the access modifier, whereas **declared** describes **where the member is declared**. These are two different criteria. For a subclass, there may be `public` members inherited from a superclass that do not appear in the set of members declared directly on the subclass.

For example, `Parent` declares the method `public void read()` and `Child extends Parent` does not override `read()`. When viewed from `Child.class`:

- `getMethod("read")` finds the `read` method because it is an inherited public method.
- `getDeclaredMethod("read")` throws `NoSuchMethodException` because `Child` does not declare that method.
- `getMethod("read").getDeclaringClass()` returns `Parent.class`, indicating the class that actually declares the method.

**Core rule:** APIs without the word `Declared` perform a public lookup that considers inherited members (for methods/fields); APIs with `Declared` consider only members declared on the `Class` under inspection, regardless of public/protected/package-private/private. This rule must be applied **according to the member kind**, because constructors are a special case that is not inherited.

## 2. Choosing the Lookup Matching the Declaration Site

- **Need public methods/fields visible through a subclass:** `getMethod`/`getMethods` or `getField`/`getFields`, which may include members inherited from superclasses or interfaces.
- **Need only the declarations of the subclass itself, including private:** `getDeclaredMethod`/`getDeclaredMethods` or `getDeclaredField`/`getDeclaredFields`; the result does not add declarations from superclasses.
- **Need constructors:** `getConstructor`/`getConstructors` retrieve only `public` constructors of the class itself; the `getDeclaredConstructor`/`getDeclaredConstructors` family retrieves all access levels of the class itself. Constructors are not inherited.

For methods, look up by name and the **exact parameter type** list, without passing the return type. Single-member lookup APIs throw `NoSuchMethodException` or `NoSuchFieldException` if not found. When `getMethods()` includes methods from `Object` or `getDeclaredMethods()` contains bridge/synthetic methods, inspect `getDeclaringClass()` and metadata flags before concluding the declaration source. Resulting arrays have no guaranteed order.

## 3. Compilable and Runnable Java 17+ Example

Create the file `MemberLookupDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;

public class MemberLookupDemo {
    public static class Parent {
        public String inheritedField = "from parent";
        public void inheritedMethod() {}
        public void overridden() {}
        protected void protectedMethod() {}
        private void hiddenMethod() {}
    }

    public static class Child extends Parent {
        public int localField = 42;
        private String secret = "child secret";
        public void localMethod() {}
        @Override public void overridden() {}
        private void internalMethod() {}
    }

    private static boolean containsMethod(Method[] methods, String name) {
        return Arrays.stream(methods).anyMatch(m -> m.getName().equals(name));
    }

    private static boolean containsField(Field[] fields, String name) {
        return Arrays.stream(fields).anyMatch(f -> f.getName().equals(name));
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;
        System.out.println("getMethod inherited: "
                + type.getMethod("inheritedMethod").getDeclaringClass().getSimpleName());
        System.out.println("getDeclaredMethod overridden: "
                + type.getDeclaredMethod("overridden").getDeclaringClass().getSimpleName());
        System.out.println("getMethods inherited: "
                + containsMethod(type.getMethods(), "inheritedMethod"));
        System.out.println("getDeclaredMethods inherited: "
                + containsMethod(type.getDeclaredMethods(), "inheritedMethod"));
        System.out.println("getDeclaredMethods private: "
                + containsMethod(type.getDeclaredMethods(), "internalMethod"));
        System.out.println("getField inherited: "
                + type.getField("inheritedField").getDeclaringClass().getSimpleName());
        System.out.println("getDeclaredFields inherited: "
                + containsField(type.getDeclaredFields(), "inheritedField"));
        System.out.println("getDeclaredFields private: "
                + containsField(type.getDeclaredFields(), "secret"));
        System.out.println("getMethods protected: "
                + containsMethod(type.getMethods(), "protectedMethod"));
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac --release 17 MemberLookupDemo.java
java MemberLookupDemo
~~~

Expected output (verified with Java 21 and Java 17 compilation mode):

~~~text
getMethod inherited: Parent
getDeclaredMethod overridden: Child
getMethods inherited: true
getDeclaredMethods inherited: false
getDeclaredMethods private: true
getField inherited: Parent
getDeclaredFields inherited: false
getDeclaredFields private: true
getMethods protected: false
~~~

**Explanation of each group of results:**

1. `inheritedMethod` is declared in `Parent` and has the `public` modifier. `Child` inherits it, so `getMethod` and `getMethods` find it; `Child`'s `getDeclaredMethods` does not include it.
2. `overridden` originates in `Parent`, but `Child` overrides it with its own method. Therefore `Child.class.getDeclaredMethod("overridden")` succeeds and `getDeclaringClass()` is `Child`. A method can be **both public and declared**.
3. `internalMethod` is `private` and declared in `Child`. `getDeclaredMethods` sees its metadata, whereas `getMethods` does not include it in the public set.
4. `inheritedField` is a public field declared in `Parent`, so `getField` from `Child` finds it while `Child`'s `getDeclaredFields` does not contain it. The `secret` field is private but still present in `getDeclaredFields`.
5. `protectedMethod` is not public so it does not appear in `getMethods()`; it can be inspected via `Parent.class.getDeclaredMethod("protectedMethod")`.

Reflection arrays do not guarantee a fixed member order. The example above checks **existence by name**, independent of element position; in production code, if ordered presentation is needed, sort explicitly.

## 4. Distinguishing "Inherited", "Declared", and "Accessible"

- **Inherited:** a member of a superclass or interface inherited according to Java language rules. Public methods/fields of a parent are the most obvious case. Constructors are **never inherited**.
- **Declared:** a member whose declaration lies directly in the type being reflected. An overridden method in `Child` is declared in `Child`, even with the same signature as the parent method.
- **Accessible:** the ability of current code to read, write, or invoke a member. That Reflection **can list** a private member via `getDeclared...` does not mean code is permitted to use that member.

Therefore, do not infer from `getDeclaredMethods()` that "this is the list of public methods", and do not infer from `getMethods()` that "all of these methods were written in the class under inspection".

### How Do Overriding and Hiding Change the Result?

- **Instance method overriding:** if `Child` declares a method overriding a public method of `Parent`, `Child`'s method is in `getDeclaredMethods()`; using `getMethod(...)` typically gives the method applicable on `Child`. Inspect `getDeclaringClass()` to identify the declaration source.
- **Field hiding:** if `Child` declares a field with the same name as a field of `Parent`, those are **two distinct fields**, not field overriding. Each class's `getDeclaredFields()` shows its own field; when processing same-named fields you must inspect `getDeclaringClass()` and not assume field names are unique across the hierarchy.
- **Static method hiding:** static methods can also be hidden under Java rules; static methods do not participate in polymorphic overriding like instance methods.
- **Interfaces:** public methods (including eligible default methods) can participate in the public method set of an implementing class, but do not thereby become members "declared" directly in the class.

This distinction is especially important for JSON libraries, mappers, dependency injection, annotation scanning frameworks, or documentation generators: the choice of lookup API determines whether members from superclasses/interfaces are visible.

## 5. When All Members Across Multiple Inheritance Levels Are Needed

`getDeclaredMethods()` does not automatically traverse superclasses. If an application needs to inventory **every declaration of each class** (e.g., private methods in superclasses), walk `getSuperclass()` step by step and call `getDeclaredMethods()` on each class:

~~~java
for (Class<?> current = Child.class;
     current != null;
     current = current.getSuperclass()) {
    for (Method method : current.getDeclaredMethods()) {
        System.out.println(current.getSimpleName() + ": " + method.getName());
    }
}
~~~

This is an **illustrative code snippet using the `Child`/`Parent` classes from the example above**, not a standalone program. It traverses the superclass chain; if declarations belonging to interfaces are also needed, you must additionally traverse `getInterfaces()` and handle duplicate inheritance paths. If only the type's public methods are needed, `getMethods()` is usually more suitable and shorter.

When reading metadata and filtering members, you can use `Modifier.isPublic(member.getModifiers())` to check modifiers, `member.getDeclaringClass()` to find the owning type, along with `Method.isBridge()`/`isSynthetic()` or `Field.isSynthetic()` to handle compiler-generated artifacts. Inspect each case rather than guessing by name or element count.

## 6. Notes on Invocation and Module Encapsulation

`getDeclaredMethod("internalMethod")` can return a `Method` object representing `Child`'s private method. However, the `invoke(...)` operation must still comply with access checks. `setAccessible(true)` is not a guaranteed shortcut: the Java Platform Module System can block deep reflection on packages that are not `opens`, leading to `InaccessibleObjectException`. Prefer valid public APIs, and only open access when design and module permissions allow it.

Do not confuse "not found by `getMethod`" with "method does not exist": a protected/private method may exist in `getDeclaredMethods` of the exact declaring class, while an inherited public method may exist in `getMethods` but not in `getDeclaredMethods` of the subclass.

## 7. Common Mistakes and How to Choose the API

| Situation | API / Handling Choice |
| --- | --- |
| Need a public method that an instance of `Child` can provide, including from parent | `Child.class.getMethod(name, parameterTypes...)` or `getMethods()` |
| Need the exact method declared on `Child`, even if private | `getDeclaredMethod(...)` or `getDeclaredMethods()` |
| Need a public field inherited from parent | `getField(name)` or `getFields()` |
| Need a private field of `Parent` | `Parent.class.getDeclaredField(name)`, with permission check if reading/writing |
| Need all declarations per class in the hierarchy | Traverse `getSuperclass()`, calling `getDeclaredFields()/getDeclaredMethods()` on each class; handle interfaces if needed |
| Need an inherited constructor of parent | None: constructors are not inherited; look up constructor on the exact class to instantiate |
| Need to call a private method after finding it via Reflection | Check access checks and module restrictions; do not assume `setAccessible(true)` will succeed |

**Self-check:** `Child.class.getMethod("inheritedMethod")` succeeds, whereas `Child.class.getDeclaredMethod("inheritedMethod")` throws `NoSuchMethodException`; conversely `Child.class.getDeclaredMethod("internalMethod")` finds the private method metadata whereas `Child.class.getMethod("internalMethod")` does not. Both differences stem from choosing **public lookup** versus **declared-only lookup**, not a contradiction in Reflection.