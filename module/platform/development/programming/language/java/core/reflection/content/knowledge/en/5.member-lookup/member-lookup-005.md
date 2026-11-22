# Looking Up One Member and Listing Multiple Members with Java Reflection

## 1. Objectives and Scope

Once you have a `Class<?>` object, Java Reflection allows **looking up a single member by name/signature** or **listing the members** of a type at runtime. "Members" here mainly include:

- **Field**: data field, described by `java.lang.reflect.Field`.
- **Method**: method, described by `java.lang.reflect.Method`.
- **Constructor**: constructor, described by `java.lang.reflect.Constructor`. Constructors are not inherited and are looked up using separate APIs.

This lesson focuses on **finding and reading metadata**, without needing to call `Method.invoke()`, read/write `Field.get()/set()`, or instantiate objects via `Constructor.newInstance()`. Obtaining metadata of a `private` member **does not mean** you are permitted to access or execute that member.

Suppose you have `Class<?> type = SomeClass.class;`. The two most important method families are:

- `getXxx(...)`: finds **`public` members**, in many cases including inherited `public` members.
- `getDeclaredXxx(...)`: finds members **declared directly in the type itself**, regardless of access level (`public`, `protected`, package-private, `private`), but **does not automatically climb to the superclass**.

Note: the inheritance difference for constructors is stated separately below.

## 2. Quick Lookup API Table

| Need | Look Up One Member | List Multiple Members | Scope |
| --- | --- | --- | --- |
| `public` method | `getMethod(name, parameterTypes...)` | `getMethods()` | `public` methods of the type and `public` methods inherited/exposed through the type hierarchy |
| Directly declared method | `getDeclaredMethod(name, parameterTypes...)` | `getDeclaredMethods()` | Declared directly in the type; all access levels |
| `public` field | `getField(name)` | `getFields()` | `public` fields of the type and inherited `public` fields |
| Directly declared field | `getDeclaredField(name)` | `getDeclaredFields()` | Declared directly in the type; all access levels |
| `public` constructor | `getConstructor(parameterTypes...)` | `getConstructors()` | Only `public` constructors of the class itself |
| Directly declared constructor | `getDeclaredConstructor(parameterTypes...)` | `getDeclaredConstructors()` | Constructors of the class itself; all access levels |

The word `Declared` means **declared on the type under inspection**, not "allows private access". With `getMethod()`/`getMethods()`, `public` methods from superclasses, interfaces, or `Object` may appear; `getDeclaredMethods()` does not automatically include them. When listing, you must not assume the first element is the desired member: **the returned order is not guaranteed**.

### 2.1. Why Do Methods Require Parameter Types Too?

Java allows overloading:

```java
void process(String text) {}
void process(int count) {}
```

To look up accurately, you must specify the parameter signature:

```java
Method byText = type.getDeclaredMethod("process", String.class);
Method byCount = type.getDeclaredMethod("process", int.class);
```

The arguments after the method name are the `Class<?>` objects of the **parameter types in exact order**. Do not pass the return type: `getDeclaredMethod`/`getMethod` only accept the name and parameter types. A parameterless method is looked up with `getDeclaredMethod("run")` or `getDeclaredMethod("run", new Class<?>[0])`.

Lookup uses exact types at the reflection level: `int.class` differs from `Integer.class`; no automatic boxing, unboxing, or widening occurs when **searching for a signature**. For `String...`, the runtime signature is `String[]`, so use `String[].class`. For a `List<String>` parameter, due to type erasure, the parameter used for lookup is usually `List.class`; there is no `List<String>.class`.

### 2.2. Where Do Fields and Constructors Differ from Methods?

- `getField("id")` and `getDeclaredField("id")` look up by **field name**, with no parameter type list. A field may hide a field of the same name in a superclass; check `Field.getDeclaringClass()` to know which class the field actually belongs to.
- `getConstructor(String.class)` finds only `public` constructors; `getDeclaredConstructor(String.class)` finds constructors declared directly in the class, including `private`. There are no "inherited constructors", so neither API walks up to the superclass.
- If `Class` represents an interface, primitive, or array, the constructor set may be empty; do not assume every `Class` has a no-arg constructor.

## 3. Complete Example: Finding One Member and Listing Multiple Members

Save the following snippet to the file `MemberLookupDemo.java`. The example intentionally includes inheritance, overloads, a `private` field, and a `private` constructor to compare the two API families.

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.stream.Collectors;

public class MemberLookupDemo {
    static class Parent {
        public int id = 10;
        protected void protectedHook() {}
        public void inheritedAction() {}
    }

    static class Child extends Parent {
        public String label;
        private int counter;

        public Child() {}
        private Child(int counter) { this.counter = counter; }

        public String show(String prefix) { return prefix + label; }
        public String show(int times) { return label + times; }
        private void reset() { counter = 0; }
    }

    static String params(Class<?>[] types) {
        return Arrays.stream(types)
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", "));
    }

    public static void main(String[] args)
            throws NoSuchMethodException, NoSuchFieldException {
        Class<Child> type = Child.class;

        // Look up a single member by exact name/signature.
        Method one = type.getDeclaredMethod("show", String.class);
        Field field = type.getDeclaredField("counter");
        Constructor<Child> constructor = type.getDeclaredConstructor(int.class);

        System.out.println("one method: " + one.getName() + "("
                + params(one.getParameterTypes()) + ") -> "
                + one.getReturnType().getSimpleName());
        System.out.println("one field: " + field.getName()
                + ": " + field.getType().getSimpleName());
        System.out.println("one constructor: "
                + constructor.getDeclaringClass().getSimpleName() + "("
                + params(constructor.getParameterTypes()) + ")");

        // Public members of the superclass are found via getMethod/getField.
        System.out.println("inherited field owner: "
                + type.getField("id").getDeclaringClass().getSimpleName());
        System.out.println("inherited method owner: "
                + type.getMethod("inheritedAction")
                      .getDeclaringClass().getSimpleName());

        // List and sort so the output does not depend on Reflection order.
        System.out.println("declared fields: "
                + Arrays.stream(type.getDeclaredFields())
                        .map(Field::getName).sorted().toList());
        System.out.println("public fields: "
                + Arrays.stream(type.getFields())
                        .map(Field::getName).sorted().toList());
        System.out.println("declared methods: "
                + Arrays.stream(type.getDeclaredMethods())
                        .map(Method::getName).distinct().sorted().toList());
        System.out.println("public constructors: "
                + Arrays.stream(type.getConstructors())
                        .map(c -> c.getDeclaringClass().getSimpleName()
                                + "(" + params(c.getParameterTypes()) + ")")
                        .sorted().toList());
        System.out.println("declared constructors: "
                + Arrays.stream(type.getDeclaredConstructors())
                        .map(c -> c.getDeclaringClass().getSimpleName()
                                + "(" + params(c.getParameterTypes()) + ")")
                        .sorted().toList());

        // Declared does not walk up to the superclass.
        try {
            type.getDeclaredMethod("inheritedAction");
        } catch (NoSuchMethodException ex) {
            System.out.println("declared inheritedAction: not found");
        }
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac MemberLookupDemo.java
java MemberLookupDemo
```

Expected output (verified with JDK 21):

```text
one method: show(String) -> String
one field: counter: int
one constructor: Child(int)
inherited field owner: Parent
inherited method owner: Parent
declared fields: [counter, label]
public fields: [id, label]
declared methods: [reset, show]
public constructors: [Child()]
declared constructors: [Child(), Child(int)]
declared inheritedAction: not found
```

**Output explanation:**

1. `getDeclaredMethod("show", String.class)` selects the exact overload accepting `String`; the overload accepting `int` is a different `Method`. Extracting `getName()` when listing and calling `distinct()` is only for displaying **unique names**; that operation **cannot show both overloaded signatures**.
2. `getDeclaredField("counter")` sees the `private` field in `Child`. `getFields()` only outputs `id` (`public` from `Parent`) and `label` (`public` in `Child`).
3. `getDeclaredConstructor(int.class)` finds the `private` constructor. `getConstructors()` only has `Child()` because that constructor is `public`.
4. `getMethod("inheritedAction")` succeeds because the method is declared `public` in `Parent`; `getDeclaredMethod("inheritedAction")` on `Child.class` throws `NoSuchMethodException` because `Child` does not declare that method.
5. Seeing `reset` via `getDeclaredMethods()` does not grant permission to run the `private` method. The example only inspects metadata. `Parent.protectedHook()` does not appear in `Child.getMethods()` because it is not `public`, nor in `Child.getDeclaredMethods()` because it is declared in the superclass.

## 4. Reading Metadata After Finding a Member

`Field`, `Method`, and `Constructor` objects reveal **name, type, declaring site, modifiers, and signature**:

| Object | APIs to Know | Meaning |
| --- | --- | --- |
| `Field` | `getName()`, `getType()`, `getDeclaringClass()`, `getModifiers()` | Field name, field type, declaring class/interface, access/property flags |
| `Method` | `getName()`, `getParameterTypes()`, `getReturnType()`, `getDeclaringClass()`, `getModifiers()` | Name, parameter type list, return type, declaring site, modifiers |
| `Constructor<?>` | `getParameterTypes()`, `getDeclaringClass()`, `getModifiers()` | Parameter signature, owning class, and constructor modifiers |
| All three | `isSynthetic()` | May be a compiler-generated member; you must understand the listing goal before filtering |

For example, after obtaining `Method one` and `Field field` in the program above:

```java
System.out.println(one.getDeclaringClass().getSimpleName()); // Child
System.out.println(field.getType() == int.class);            // true
System.out.println(java.lang.reflect.Modifier.isPrivate(
        field.getModifiers()));                               // true
```

This short snippet **is inserted into `main` of the previous example**, not a standalone Java program. `getParameterTypes()` returns a `Class<?>[]` array in declaration order; for generic methods, `getGenericParameterTypes()` can additionally be used when generic declaration info is needed (not guaranteed to reflect concrete types after erasure).

To display the **full signature of each overload** when listing, instead of `map(Method::getName).distinct()`, use a representation that includes parameters:

```java
Arrays.stream(type.getDeclaredMethods())
        .filter(m -> m.getName().equals("show"))
        .map(m -> m.getName() + "(" + params(m.getParameterTypes()) + ")")
        .sorted()
        .forEach(System.out::println);
```

This snippet is also placed inside `main` of the previous program; output:

```text
show(String)
show(int)
```

Here `sorted()` is used because reflection does not guarantee method order. For documentation/debugging tools, display `getDeclaringClass()`, parameter types, and modifiers rather than just names.

## 5. Finding Inherited Non-Public Members

When you need to find a `protected`/package-private/`private` field or method located on a superclass, `Child.class.getDeclaredXxx(...)` **does not automatically search the superclass**; `getXxx(...)` does not find non-`public` members either. If business requirements genuinely demand traversing superclasses, perform an explicit loop.

Example utility that finds the **field declared in the closest class** in the superclass chain:

```java
static Field findFieldInHierarchy(Class<?> start, String name)
        throws NoSuchFieldException {
    for (Class<?> current = start; current != null;
         current = current.getSuperclass()) {
        try {
            return current.getDeclaredField(name);
        } catch (NoSuchFieldException ignored) {
            // Not declared in this class: continue up to superclass.
        }
    }
    throw new NoSuchFieldException(name);
}
```

This is a **utility method**, requiring placement inside a Java class and importing `java.lang.reflect.Field`. Calling `findFieldInHierarchy(Child.class, "id")` returns the `Field` declared in `Parent`; calling with `"counter"` selects the field in `Child`. This loop only inspects the **superclass chain** and does not search fields declared in interfaces; that is the intentional scope of the example.

For methods, `getDeclaredMethod(name, parameterTypes)` can similarly be used on each superclass when inspecting specific declarations. However, **interface methods are not in the `getSuperclass()` chain**; to scan interfaces and superinterfaces completely, you need to traverse `getInterfaces()` separately. In that case, you should usually start with `getMethods()` if you only care about the `public` API.

Also distinguish: **finding metadata across the hierarchy** and **deciding which method will run during dynamic dispatch** are two different issues. `getDeclaringClass()` tells where the metadata object is declared; it does not replace understanding overriding, hiding, or access permissions.

## 6. Easily Confused Situations

### 6.1. Not Finding a Member Does Not Necessarily Mean the Member Does Not Exist

- `getMethod("reset")` on `Child.class` fails because `reset` is `private`; `getDeclaredMethod("reset")` finds it.
- `getDeclaredMethod("inheritedAction")` fails on `Child.class` because the method is in the superclass; `getMethod("inheritedAction")` finds it.
- `getConstructor(int.class)` fails on `Child.class` because the constructor taking `int` is `private`; `getDeclaredConstructor(int.class)` finds it.
- `getDeclaredMethod("show", Integer.class)` fails because the corresponding overload takes `int`, not `Integer`.

Single-member lookup methods usually throw `NoSuchMethodException` or `NoSuchFieldException` when not found. If a missing member is a normal case, catch the **appropriately scoped** exception or return an `Optional` from a utility method; avoid broadly catching `Exception` and hiding programming bugs.

### 6.2. `getDeclared*` Does Not Mean Free Use of `private`

Reflection can **discover** non-public members, but reading/writing/calling a member must pass separate access checks. On Java 9+ with the Java Platform Module System, attempting `setAccessible(true)` can be denied (`InaccessibleObjectException`), even when `getDeclaredField()` returned a `Field`. `trySetAccessible()` can also return `false`. Therefore, do not design programs assuming "found means callable"; when building libraries/frameworks, prefer public APIs or intentional `opens` mechanisms.

### 6.3. The Compiler Can Generate Extra Members

In real programs, `getDeclaredMethods()` may encounter **bridge methods** generated by generics/covariant returns, or synthetic methods/fields. `Method.isBridge()` and `Member.isSynthetic()` help distinguish them. If generating developer-facing documentation tables, consider filtering them; if analyzing runtime/bytecode, do not filter arbitrarily.

Do not treat element count, order, or `toString()` representations of `Member` objects as a stable contract for tests. A safer approach is to extract structured information, sort, and compare the exact required fields. A constructor may not exist with the expected signature; **Java does not auto-generate a no-arg constructor** once a class declares another constructor.

### 6.4. Differences Between Declaration and Inheritance

- `getDeclaredFields()` does not include superclass fields; `getFields()` includes only `public` fields visible via type relationships.
- `getDeclaredMethods()` does not automatically include superclass/interface methods; `getMethods()` serves `public` method discovery and may include methods from `Object`.
- Constructors are not inherited, so `getConstructors()` never includes `Parent`'s constructors when called on `Child.class`.
- Method names are not unique when overloaded; when classifying, use **name + parameter types**, adding return type/owner when inspecting bridge cases or complex runtime scenarios.

## 7. Choosing the Right API in Practice

| Situation | Initial Choice | Why |
| --- | --- | --- |
| Framework needs a `public` method with a specific name and signature on an object | `type.getMethod(name, parameterTypes)` | Accepts inherited `public` methods |
| Audit tool needs to see all fields declared in a class | `type.getDeclaredFields()` | Includes non-public fields of that exact class |
| Debugging the list of directly declared methods | `type.getDeclaredMethods()` | Not mixed with all inherited `public` methods |
| Checking a `public` factory constructor | `type.getConstructor(parameterTypes)` | Only `public` constructors |
| Inspecting non-public constructors for metadata analysis | `type.getDeclaredConstructors()` | Does not require permission to invoke them |
| Finding a field declared in a superclass, regardless of modifier | Traverse `getSuperclass()` + `getDeclaredField()` | Needs precise control over traversal scope |

When the type is already known at compile time and you only need a normal method call, direct invocation is usually simpler, more type-safe, and easier to maintain. Reflection is most useful when names/signatures are determined at runtime, such as mappers, serializers, containers, plugin loaders, test/discovery tools, and introspection utilities. For very frequent repeated lookups, `Method`/`Field` can be cached by class and signature; `ClassLoader` lifecycles must be accounted for to avoid retaining classes unnecessarily.

## 8. Self-Check

1. How do `Child.class.getDeclaredField("id")` and `Child.class.getField("id")` differ? **Answer:** the first call throws `NoSuchFieldException` because `id` is declared in `Parent`; the second call returns the inherited `public` field.
2. Why does `Child.class.getDeclaredMethod("show")` fail even though the class has two `show` methods? **Answer:** both take one parameter; the call is requesting a parameterless `show()` method.
3. How do you obtain the `show(int)` overload? **Answer:** `Child.class.getDeclaredMethod("show", int.class)`.
4. Why does `Child.class.getConstructors()` have only one element in the example? **Answer:** only `Child()` is `public`; `Child(int)` is `private`, and `Parent`'s constructors are not inherited.
5. Which API should be used to count methods declared directly in the class, including `private`? **Answer:** `getDeclaredMethods()`; if counting for business logic, account for synthetic/bridge methods and overloads before tallying.

**Takeaway:** Before looking up a member, answer three questions: **(1)** do you need a method, field, or constructor; **(2)** do you need only `public` or all access levels; **(3)** do you need inherited members too or only direct declarations. Those three decisions lead to the right `get...`/`getDeclared...` API pair and help prevent most `NoSuchMethodException`/`NoSuchFieldException` errors.