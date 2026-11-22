# `findVirtual`, `findStatic`, `findConstructor`, and `findSpecial` in Java MethodHandle

## 1. Four Ways to Look Up Invocations and the Mental Model

`java.lang.invoke.MethodHandle` is an object representing an operation that can be invoked in Java: calling an instance method, calling a static method, creating an object, or invoking a method with special semantics. You do not invoke a method name directly through `MethodHandle`; first you use `MethodHandles.Lookup` to **look up** a valid operation, then you invoke the handle.

A `MethodHandle` has a runtime type described by `MethodType`: an ordered list of parameter types and a return type. This type must be understood accurately, because the type of the handle after lookup **can differ** from the Java method's declared signature. In particular, an instance-method handle has an extra **receiver** (the target object receiving the call) in the first parameter slot; a constructor handle takes constructor parameters and returns a new object, even though you must specify return type `void` during lookup.

All four lookup methods covered here live on `MethodHandles.Lookup`:

| API | Operation Found | `MethodType` Passed In | Resulting Handle Type | Distinguishing Point |
| --- | --- | --- | --- | --- |
| `findVirtual(refc, name, type)` | Instance method | Return type and parameters **excluding receiver** | `(Receiver, params...)ReturnType` | Uses appropriate instance dispatch when invoked |
| `findStatic(refc, name, type)` | `static` method | Exact declared return type and parameters | `(params...)ReturnType` | No receiver |
| `findConstructor(refc, type)` | Constructor | **`void`** and constructor parameters | `(params...)refc` | Creates and returns a new instance |
| `findSpecial(refc, name, type, specialCaller)` | Instance call with `invokespecial` semantics | Return type and parameters **excluding receiver** | `(specialCaller, params...)ReturnType`, per access rules | Can invoke a superclass version bypassing override, if lookup has sufficient permissions |

In the table, `refc` is the class or interface used to resolve the member; `name` is the method name; `type` is a `MethodType`. `specialCaller` is the special calling class context allowed to perform `invokespecial`, not an arbitrary name string. Java checks access permissions when looking up the handle; those permissions are not automatically elevated just because you use a dynamic API.

## 2. `MethodType` and `Lookup`: Preparing Correctly Before Lookup

`MethodType.methodType(returnType, parameterTypes...)` describes the type of the method **being looked up**. For example:

```java
MethodType.methodType(String.class, int.class)          // (int)String
MethodType.methodType(void.class, String.class)          // (String)void
MethodType.methodType(boolean.class)                     // ()boolean
```

- `MethodHandles.lookup()` provides a lookup bound to **its calling class** and that class's current access rights. Inside a class with appropriate permissions, the lookup can also see non-public members.
- `MethodHandles.publicLookup()` is only for public accesses allowed to the public lookup; it cannot be used to freely invoke private or package-private members.
- `MethodHandles.privateLookupIn(Target.class, lookup)` can create a lookup carrying private access to `Target` **when** the input lookup, modules, and package-opening rules permit it. It is not a way to bypass all `private`/module barriers.
- Both the method signature and receiver type must be exact. `MethodHandle.type()` lets you inspect the handle type **after** lookup, which is very helpful when diagnosing `WrongMethodTypeException`.

Method names are case-sensitive; overloads are distinguished by parameter lists and appropriate return types. For constructors, there is no method name because the API only accepts `refc` and `type`.

## 3. `findVirtual` — Looking Up an Instance Method

Signature:

```java
MethodHandle handle = lookup.findVirtual(
    SomeClass.class,
    "methodName",
    MethodType.methodType(ReturnType.class, ParamType.class)
);
```

For the Java method `String greet(String prefix)` on `Person`:

- The **lookup** type is `(String)String`.
- The **handle** type is `(Person,String)String`, because `Person` is the receiver.
- When invoking, pass the `Person` instance before the `prefix` string.

For overridable instance methods, dispatch still depends on the object receiving the call: a handle looked up through a superclass can execute a subclass override. Do not treat "virtual" as a promise that every method can be overridden: `final` methods cannot be overridden; private methods have their own invocation rules.

`findVirtual` must not be used to look up constructors or `static` methods. Mixing up the member kind causes the lookup to fail rather than automatically falling back to `findStatic`.

## 4. `findStatic` — Looking Up a Class-Level Method

Signature:

```java
MethodHandle handle = lookup.findStatic(
    Utility.class,
    "parse",
    MethodType.methodType(int.class, String.class)
);
```

A `static int parse(String text)` method has both lookup type and handle type `(String)int`. **Do not pass a `Utility` object** when invoking the handle. The class in `refc` serves member resolution and does not become a runtime parameter.

Do not confuse `static` with calling an instance method through a class reference variable: only methods genuinely declared `static` fit `findStatic`. The same access checks apply as with `findVirtual`.

## 5. `findConstructor` — Type-Checked Object Creation

Signature:

```java
MethodHandle ctor = lookup.findConstructor(
    Person.class,
    MethodType.methodType(void.class, String.class)
);
```

Suppose `Person(String name)` is a constructor. The `MethodType` during **lookup** has type `(String)void`, because constructors in bytecode do not declare a return type. However, `ctor.type()` has type `(String)Person`, and invoking it returns a new `Person` instance.

Points to remember:

- Do not pass `MethodType.methodType(Person.class, String.class)` into `findConstructor`: the `type` parameter must specify return type `void`.
- There is no receiver object when creating an object; the constructor handle returns the new instance.
- If the class cannot be instantiated or the constructor does not exist/is inaccessible under the applicable rules, lookup or invocation will fail. For example, an abstract class cannot be instantiated using this handle.

## 6. `findSpecial` — Invoking a "Special" Version Under the Caller's Rights

Signature:

```java
MethodHandle handle = lookup.findSpecial(
    Parent.class,
    "methodName",
    MethodType.methodType(String.class),
    Child.class
);
```

`findSpecial` reflects how the JVM performs certain `invokespecial` calls, such as a valid `super.method()` call in a subclass context. It is **not** simply a variant of `findVirtual` with one extra parameter.

Suppose `Child extends Parent` and overrides `label()`:

- A normal call `child.label()` runs `Child.label()`.
- If code inside the `Child` context has special-caller lookup permissions for `Parent.class` with `specialCaller = Child.class`, the corresponding handle can run `Parent.label()` on that `Child` without dispatching to the override.
- The first argument when invoking this handle is a receiver of type `Child`; `specialCaller` affects **semantics and access control**, not an optional parameter at invocation time.
- Creating a lookup from a class without appropriate special-caller access typically results in `IllegalAccessException`; you cannot arbitrarily pick any class as `specialCaller`.

`findSpecial` also appears in scenarios invoking private or default interface methods with special semantics, though access details depend on the class, interface, and module. For ordinary instance calls, use `findVirtual`; only use `findSpecial` when you need and are allowed to preserve explicit call semantics from a specific class.

## 7. Complete Runnable Example on Java 17+

Save the following code into `LookupDemo.java` as UTF-8. The program uses all four APIs, including a genuine `super` call resolved via `findSpecial` right inside the `Child` class.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class LookupDemo {
    static class Person {
        private final String name;

        Person(String name) {
            this.name = name;
        }

        String greet(String prefix) {
            return prefix + ", " + name;
        }

        static String badge(int id) {
            return "ID-" + id;
        }
    }

    static class Base {
        String label() {
            return "Base";
        }
    }

    static class Child extends Base {
        @Override
        String label() {
            return "Child";
        }

        String callBase() throws Throwable {
            // Lookup created inside Child: valid special-caller context.
            MethodHandle parent = MethodHandles.lookup().findSpecial(
                Base.class,
                "label",
                MethodType.methodType(String.class),
                Child.class
            );
            return (String) parent.invokeExact((Child) this);
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Constructor: look up (String)void, get handle (String)Person.
        MethodHandle constructor = lookup.findConstructor(
            Person.class,
            MethodType.methodType(void.class, String.class)
        );

        // Virtual: look up (String)String, get (Person,String)String.
        MethodHandle virtual = lookup.findVirtual(
            Person.class,
            "greet",
            MethodType.methodType(String.class, String.class)
        );

        // Static: look up and get (int)String.
        MethodHandle fixed = lookup.findStatic(
            Person.class,
            "badge",
            MethodType.methodType(String.class, int.class)
        );

        Person person = (Person) constructor.invokeExact("Lan");
        System.out.println((String) virtual.invokeExact(person, "Hello"));
        System.out.println((String) fixed.invokeExact(7));

        Child child = new Child();
        System.out.println(child.label());
        System.out.println(child.callBase());
    }
}
```

Compile and run in the directory containing the source file:

```bash
javac -encoding UTF-8 LookupDemo.java
java LookupDemo
```

Output:

```text
Hello, Lan
ID-7
Child
Base
```

Step-by-step explanation:

1. `constructor.invokeExact("Lan")` creates a `Person`, requiring the Java compiler to see an exact return type of `Person`.
2. `virtual.invokeExact(person, "Hello")` passes the receiver before the parameter. The result is a greeting using the object's name.
3. `fixed.invokeExact(7)` takes only `int` because `badge` is a static method.
4. `child.label()` yields `Child` via normal dispatch, whereas `child.callBase()` creates a handle in the proper `Child` context to invoke `Base.label()` and yields `Base`.

The example places `Person`, `Base`, and `Child` inside the same enclosing class so access rights are straightforward. If you move them into different packages/modules, you must re-check class/method modifiers and `Lookup` permissions instead of assuming every lookup remains valid.

## 8. `invokeExact`, `invoke`, and Changing Types

Succeeding at lookup is only step one; invoking the handle must satisfy its type.

- `invokeExact` requires parameter types **and the return type seen at the call site** to match `handle.type()` exactly. For calls returning a value, an explicit cast like `(String)` or `(Person)` in the example helps the compiler establish the expected return type. If the signatures do not match, `WrongMethodTypeException` is thrown at runtime.
- `invoke` allows certain type adaptations equivalent to `asType` (such as boxing/unboxing or valid reference casts); this does not mean every type can be converted.
- `handle.asType(targetType)` produces an adapted handle according to permitted conversion rules; it can throw `WrongMethodTypeException` if adaptation is not possible.
- `invokeWithArguments` is useful for dynamic argument lists and can perform boxing/conversions; on the other hand, it does not replace designing exact signatures when performance and type safety are priorities.

Example of handling the `virtual` invocation in the program above:

```java
// virtual.type() is (LookupDemo.Person,String)String
String result = (String) virtual.invokeExact(person, "Hello");

// With invokeExact, you cannot arbitrarily omit the receiver:
// virtual.invokeExact("Hello"); // Wrong signature at the call site.
```

This snippet is **only illustrative when placed inside `main` of the full example**, where the `virtual` and `person` variables already exist; it is not a standalone Java file.

## 9. Common Errors, Causes, and Fixes

| Symptom | Typical Cause | How to Check/Fix |
| --- | --- | --- |
| `NoSuchMethodException` during `find*` | Wrong name, overload, parameter/return types; confusing static with instance | Cross-check the actual declaration and `MethodType`; pick the right API |
| `IllegalAccessException` during lookup | Lookup lacks permission for the class/member or lacks special-caller access | Check where `lookup()` is created, modifiers, package, and module; only use `privateLookupIn` when authorized |
| `WrongMethodTypeException` during invocation | Call-site signature in `invokeExact` differs from `handle.type()`, including return type | Print `handle.type()`; check receiver, `int`/`Integer`, return type, and casts |
| `ClassCastException`/conversion error during invoke | Runtime argument does not match the requested conversion | Check runtime types, `asType`, and the actual conversion path |
| Calls override instead of superclass | Used `findVirtual` while expecting `super` behavior | Use `findSpecial` inside a valid special-caller context |
| Constructor lookup fails | Put the class instead of `void` as the return type, or wrong parameter list | Look up constructors with `MethodType.methodType(void.class, ...)` |
| Missing/extra arguments in call | Forgot receiver for virtual/special or added receiver for static/constructor | Compare `handle.type()` with the table in section 1 |

The lookup APIs above declare `NoSuchMethodException` and `IllegalAccessException`. `MethodHandle.invokeExact`/`invoke` can throw `Throwable`, so the example uses `throws Throwable` for ease of observation; in real applications, choose an appropriate exception-handling strategy.

## 10. Access, Inheritance, and Java Modules

`Lookup` is an **access-checked capability**. A reference to a `Class<?>` or a method name does not grant permissions by itself. A few practical rules:

1. Create `MethodHandles.lookup()` in the exact class/context where the lookup belongs. Moving the code into another helper changes the lookup-owning class, which can change member accessibility.
2. A public method on a public class may not be enough when the class resides in a package not exported by its module to the caller. Cross-module private access also involves package `opens` and the conditions of `privateLookupIn`.
3. For overridden methods, `findVirtual` is usually the choice that reflects polymorphism. For intentional `super` calls, `findSpecial` should be verified with a concrete case in the class hierarchy being used.
4. Do not treat Reflection's `setAccessible(true)` as implying that a MethodHandle lookup automatically gains the same permissions. These are two distinct access mechanisms.
5. When a lookup fails, diagnose the modifier, module, and signature accurately before changing JVM flags; do not open module permissions broadly just to avoid understanding the cause.

## 11. Choosing an API by Scenario

- Calling `user.getName()` across many instances: look up `findVirtual(User.class, "getName", methodType(String.class))`; pass each `User` as the handle's first argument.
- Calling utility `Math.max(int,int)`: look up `findStatic(Math.class, "max", methodType(int.class, int.class, int.class))`; pass the two integers directly.
- Creating `new ArrayList<>(initialCapacity)`: look up `findConstructor(ArrayList.class, methodType(void.class, int.class))`; the handle's result is an `ArrayList`.
- Calling the superclass version even though a subclass overrides it: consider `findSpecial` **inside the valid permitted subclass context**; do not use it as a shortcut to invoke arbitrary members from external code.

An effective problem-solving sequence: **identify member kind -> write declared signature -> pick `find*` -> print `handle.type()` -> check lookup permissions -> pass proper receiver and return type -> verify output**. Once you grasp the difference between lookup type and handle type, most real-world errors become much easier to pinpoint.

## 12. Self-Check

1. Why does `findVirtual` take a `MethodType` without the receiver, while the resulting handle includes the receiver?
2. Why does `findConstructor` require return type `void` while the handle returns an object?
3. When a subclass overrides `label()`, how do you distinguish a virtual call from a special call to the superclass version?
4. Can `WrongMethodTypeException` occur because the return type at the `invokeExact` call site differs from the handle?
5. When the same lookup works inside `Child` but fails after being moved to a helper in another module, which permissions must be checked?

**Learning outcome:** distinguish all four lookup forms, write the right `MethodType`, read `MethodHandle.type()`, execute calls, and explain signature as well as access errors.