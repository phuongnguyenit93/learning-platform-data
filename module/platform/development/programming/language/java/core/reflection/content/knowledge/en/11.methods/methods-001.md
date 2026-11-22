# Method metadata: name, declaring class, and return type in Java Reflection

A `java.lang.reflect.Method` object describes **a method** of a class or interface. When writing code analysis tools, frameworks, mappers, documentation generators, or testing tools, the three pieces of information most often needed first are:

- **Method name**: `method.getName()`.
- **Class or interface that declares the method**: `method.getDeclaringClass()`.
- **Declared return type**: `method.getReturnType()`.

These three properties are **metadata about the method**, not the result of running the method. They do not require calling `Method.invoke()` to obtain a value. However, it is very easy to confuse the "declaring class" with the "class being queried" or the "class of the receiver object", and to confuse the "return type" with the "runtime type of the returned value". This lesson clarifies those boundaries.

## 1. What is Method and where do we get a Method?

`Method` belongs to the `java.lang.reflect` package and represents information about a method loaded by the JVM. It is usually obtained from a `Class<?>` object:

```java
Method publicMethod = Example.class.getMethod("run");
Method declaredMethod = Example.class.getDeclaredMethod("run");
```

This is an illustrative snippet in a context where an `Example` class with a matching method already exists and `Method` is imported; both calls can throw `NoSuchMethodException`.

The two lookup APIs are not synonymous:

| `Class` API | Search scope |
| --- | --- |
| `getMethod(name, parameterTypes...)` | **Public** methods of the type, which may include methods inherited from a superclass/superinterface |
| `getDeclaredMethod(name, parameterTypes...)` | Methods **declared directly on the type itself**, regardless of `public`, `protected`, package-private, or `private`; does not search superclasses |
| `getMethods()` | Array of public methods of the type and inherited methods according to the API contract |
| `getDeclaredMethods()` | Array of methods declared directly on the type, excluding inherited methods |

The order of elements in `getMethods()` and `getDeclaredMethods()` is **not guaranteed to be the declaration order in source code**. For a specific method that must be identified accurately, look it up by name and parameter type list; for multiple methods that need a stable presentation, sort them yourself by an appropriate key.

Obtaining metadata of a `private` method via `getDeclaredMethod` does **not** automatically grant permission to call that method. Access control checks during `invoke` are a separate concern.

## 2. Three core metadata APIs

### 2.1. getName(): simple name of the method

`String name = method.getName();` returns the **method name**, for example `"save"`, `"count"`, `"toString"`.

The value is only the name:

- It does not contain the package name or declaring class.
- It does not include parentheses, parameter list, or return type.
- It does not guarantee the method is unique: overloads `parse(String)` and `parse(int)` both return `"parse"`.

To identify an overload, combine `getName()` with `getParameterTypes()` (parameter order is important). When additional metadata is needed for documentation, you can use `getModifiers()`, `getGenericParameterTypes()`, `getAnnotations()`, etc. depending on the purpose, but **the simple name alone does not form a complete signature**.

### 2.2. getDeclaringClass(): the type that actually declares the method

`Class<?> owner = method.getDeclaringClass();` returns the `Class` object of the **class or interface that declares** the method represented by that `Method`.

Example:

```java
class Parent {
    public void work() {}
}
class Child extends Parent {}
```

This is illustrative code; assume the two classes are in a valid access context.

If you look up `Child.class.getMethod("work")`, you get metadata for the `work` method **declared in `Parent`**. Therefore:

```java
Method m = Child.class.getMethod("work");
System.out.println(m.getDeclaringClass() == Parent.class); // true
```

Even though the lookup starts with `Child.class`, the result is still `Parent.class`, because `Child` **inherits** the method rather than declaring a new one.

Three concepts must be distinguished:

| Concept | How to obtain | In the example where Child inherits Parent.work() |
| --- | --- | --- |
| Type used to start the query | `Class` object calling `getMethod` | `Child.class` |
| Type declaring the reflected method | `Method.getDeclaringClass()` | `Parent.class` |
| Runtime type of the receiver when used | `receiver.getClass()` | Could be `Child.class` or another subtype |

**Do not confuse** `Method.getDeclaringClass()` with `Class.getDeclaringClass()`: they share the same name but are called on two different kinds of objects. `Class.getDeclaringClass()` refers to *the enclosing class that declares a member class*, not the owner of a method.

For a method declared in an interface, `getDeclaringClass()` can return that **interface** itself. For an overridden method, a `Method` belonging to the subclass returns the subclass. If a `Method` is obtained directly from the superclass, its metadata still has the superclass as owner even when executed on a subclass receiver using dynamic dispatch.

### 2.3. getReturnType(): formal return type

`Class<?> returnType = method.getReturnType();` returns a `Class` object representing the **declared return type** of that method.

Examples:

| Declaration | `getReturnType()` |
| --- | --- |
| `int count()` | `int.class` |
| `String name()` | `String.class` |
| `void reset()` | `void.class` |
| `String[] labels()` | `String[].class` |
| `List<String> tags()` | `List.class` |

**Important point:** `void` is represented by `void.class` (or `Void.TYPE`), **not** `null` and not `Void.class`. `Void.class` is a special wrapper class, different from the `void` type of a method declaration.

When a method declares a reference type `Number` but at runtime returns an `Integer` object, `getReturnType()` still returns `Number.class`: metadata describes the **declaration**, without observing or running the method to infer the value's type. For a generic method such as `List<String> tags()`, `getReturnType()` returns `List.class` after **type erasure**, without storing the `String` type argument inside that `Class` object itself.

## 3. Complete, standalone Java 17+ example

The following example intentionally includes an inherited method, an overridden method, a generic return type, `void`, a primitive return type, and overloads. It queries each method by name/signature, so the output does not depend on Reflection array ordering.

Create the file `MethodMetadataDemo.java`:

```java
import java.lang.reflect.Method;
import java.util.List;

public class MethodMetadataDemo {
    static class Parent {
        public String inherited() {
            return "parent";
        }

        public String status() {
            return "base";
        }
    }

    static class Child extends Parent {
        @Override
        public String status() {
            return "child";
        }

        public List<String> tags() {
            return List.of("java");
        }

        public int count() {
            return 2;
        }

        public void refresh() {}

        public String parse(String text) {
            return text;
        }

        public String parse(int code) {
            return Integer.toString(code);
        }
    }

    private static void show(Method method) {
        System.out.printf(
                "%s | owner=%s | return=%s%n",
                method.getName(),
                method.getDeclaringClass().getSimpleName(),
                method.getReturnType().getTypeName()
        );
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        show(Child.class.getMethod("inherited"));
        show(Child.class.getMethod("status"));
        show(Child.class.getDeclaredMethod("tags"));
        show(Child.class.getDeclaredMethod("count"));
        show(Child.class.getDeclaredMethod("refresh"));

        Method tags = Child.class.getDeclaredMethod("tags");
        System.out.println(
                "tags generic=" + tags.getGenericReturnType().getTypeName()
        );

        Method overload =
                Child.class.getDeclaredMethod("parse", String.class);
        System.out.println(
                "overload=" + overload.getName()
                + "(" + overload.getParameterTypes()[0].getSimpleName() + ")"
        );

        Method parentStatus = Parent.class.getDeclaredMethod("status");
        System.out.println(
                "parentStatus owner="
                + parentStatus.getDeclaringClass().getSimpleName()
        );
        System.out.println(
                "parentStatus invoked=" + parentStatus.invoke(new Child())
        );
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac MethodMetadataDemo.java
java MethodMetadataDemo
```

Output:

```text
inherited | owner=Parent | return=java.lang.String
status | owner=Child | return=java.lang.String
tags | owner=Child | return=java.util.List
count | owner=Child | return=int
refresh | owner=Child | return=void
tags generic=java.util.List<java.lang.String>
overload=parse(String)
parentStatus owner=Parent
parentStatus invoked=child
```

Explanation of notable lines:

1. `Child.class.getMethod("inherited")` finds the `public inherited()` method declared by **Parent**. Therefore `getDeclaringClass().getSimpleName()` is `Parent`, not `Child`.
2. `Child.class.getMethod("status")` finds the **overriding method declared by Child**, so the owner is `Child`.
3. For `tags()`, `getReturnType().getTypeName()` is `java.util.List`; using `getGenericReturnType()` reveals the `java.util.List<java.lang.String>` information.
4. `count()` returns the primitive type `int`; `refresh()` has return type `void`. Both have a valid `Class` representing that type.
5. `getDeclaredMethod("parse", String.class)` selects the overload with the `String` parameter, whereas the `parse(int)` overload has the same name but a different signature.
6. `parentStatus` is a `Method` object obtained directly from `Parent`, so its owner remains `Parent`; however, `parentStatus.invoke(new Child())` invokes the overridden implementation of `Child` and returns `"child"`. **The declaring class of the metadata** and **the implementation dispatched at runtime** can differ.

The example is arranged so that each piece of information is printed from a specific method. If you replace these calls with a loop over `getDeclaredMethods()`, sort them first if you require a deterministic output order.

## 4. How do getReturnType() and getGenericReturnType() differ?

Both APIs describe the **declared return type**, but with different levels of detail:

- `getReturnType()` has Java type `Class<?>`. It represents the **erased/raw type** after applying erasure rules for generics.
- `getGenericReturnType()` has Java type `java.lang.reflect.Type`. It preserves generic signature information when present, such as `ParameterizedType`, `TypeVariable`, `GenericArrayType`, or `Class`.

Example:

```java
public List<String> tags() {
    return List.of("java");
}
```

In the context of the runnable example in section 3, `tags.getReturnType()` is `List.class`, while `tags.getGenericReturnType().getTypeName()` prints `java.util.List<java.lang.String>`.

Another generic example:

```java
class Box<T> {
    public T read() {
        return null;
    }
}
```

This is a non-standalone illustrative snippet. For the `Method` representing `Box.read()`, `getReturnType()` is `Object.class` because `T` has no explicit upper bound, while `getGenericReturnType()` represents the **type variable** `T`.

If `SpecialBox extends Box<String>`, do not assume `SpecialBox.class.getMethod("read").getGenericReturnType()` automatically turns `T` into `String`: that method can still be the metadata declared on `Box`. To infer the concrete `T` from a subclass, a generic analysis tool must **resolve the type variable mapping** through the superclass/interface type hierarchy.

When handling `Type`, distinguish `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType`, etc. according to each case instead of casting every `Type` to `Class`. Using `getTypeName()` helps display information; do not treat this string format as a stable storage/signature protocol invented by the application.

If you only need to branch on the erased runtime type, `getReturnType()` is usually sufficient. If you want to build API documentation, perform generic analysis, or create mappers that distinguish `List<String>` from `List<Integer>`, you must inspect `getGenericReturnType()` and the broader context.

## 5. Inheritance, overriding, and dynamic dispatch

The following three concepts should not be conflated:

**One: the queried type.** Code may start with `Child.class.getMethod("inherited")`, but querying through the subclass does not mean every `Method` found is declared in the subclass.

**Two: the declaring type.** `method.getDeclaringClass()` is the class/interface **containing the corresponding declaration** that the `Method` represents. For an inherited non-overridden method, this is usually the superclass; for an overridden method declared in the child, it is the child.

**Three: the executed implementation.** For an instance method using virtual dispatch, a `Method` pointing to a declaration in the superclass can still execute the subclass's overridden implementation when given a subclass object. That is why in the example `parentStatus.getDeclaringClass() == Parent.class`, yet `parentStatus.invoke(new Child())` returns `"child"`.

Do not explain `getDeclaringClass()` as "the class that defines the implementation that actually ran". Before invocation, the API only provides metadata; runtime dispatch also depends on the kind of method (`static`, instance, private, etc.) and the receiver.

For interfaces, `getDeclaringClass()` can return the interface that defines the method. For example, a method declared in interface `Task` has owner `Task.class`, even when a concrete class implements `Task`.

## 6. Overloading, overriding, bridge, and synthetic methods

**Overloading**: multiple methods with the same name but different parameter type lists. Both `parse(String)` and `parse(int)` produce the same `getName() == "parse"` result. To find a specific one, pass `Class<?>...` to `getMethod` or `getDeclaredMethod`:

```java
Method byText = Child.class.getDeclaredMethod("parse", String.class);
Method byCode = Child.class.getDeclaredMethod("parse", int.class);
```

The snippet above is in the context of the `Child` class in the full example, with `Method` imported and `NoSuchMethodException` handled by the caller. If you omit parameter types when looking up `parse`, Java looks for a **no-argument** `parse()`, rather than picking an arbitrary overload.

**Overriding**: a method in a subclass redefines a method from a superclass. Each declaration can be represented by its own `Method`, with the corresponding `getDeclaringClass()`. Overriding can use a **covariant return type** (for example, the superclass declares `Number measure()` and the subclass overrides with `Integer measure()`): when reflecting each declaration accurately, `getReturnType()` also reflects the corresponding declared type.

**Bridge/synthetic**: the compiler sometimes generates extra methods in bytecode to preserve polymorphism when using generics or covariant returns. As a result, `getDeclaredMethods()` can show more methods than the list a reader sees in source code. When analyzing methods to generate documentation or register handlers, you may need to check `method.isBridge()` and `method.isSynthetic()`, combining `getParameterTypes()` and `getReturnType()`; you should not treat the name as a unique key.

Some class files can contain multiple methods with the same name and parameter types but different return types (for example, bridge methods). Per the `Class.getDeclaredMethod` contract, when there are multiple candidates and one has a more specific return type than the others, the API prefers that candidate; in other cases it may select one of the candidates. Do not design bytecode analysis code based on the assumption that name + params alone always distinguishes every method at the JVM level.

**Constructors are not Methods**: constructors are reflected using `Constructor<?>`; there is no method named `"<init>"` returned by `getDeclaredMethod`. Reading `Method.getReturnType()` does not apply directly to `Constructor` because constructors do not have a regular method return type.

## 7. Practical application: building an ordered metadata list

Suppose you need to list endpoints, handlers, or commands from methods. Avoid two mistakes: using `getName()` as a unique ID when overloads exist, and relying on the return order of `getDeclaredMethods()`.

Illustrative code example (not a standalone program; assumes `Arrays`, `Comparator`, and `Method` are imported and `SomeClass` exists):

```java
Method[] methods = SomeClass.class.getDeclaredMethods();

Arrays.sort(
        methods,
        Comparator.comparing(Method::getName)
                  .thenComparing(m -> Arrays.toString(m.getParameterTypes()))
                  .thenComparing(m -> m.getReturnType().getTypeName())
);

for (Method method : methods) {
    System.out.printf(
            "%s declaredIn=%s returns=%s%n",
            method.getName(),
            method.getDeclaringClass().getName(),
            method.getReturnType().getTypeName()
    );
}
```

The example above orders by name, parameter type list (as an illustrative string), and return type; it **does not restore declaration order in source code**. If a long-lived identifier key is needed, define a consistent signature encoding that accounts for declaring type, method name, ordered parameter types, and when appropriate, return type/bridge information. For simple display purposes, the comparator above suffices to illustrate the principle.

When building a framework, you should also explicitly decide whether to include:

- Methods inherited from superclasses/interfaces or only methods declared on the inspected class;
- `public` methods only or non-public methods as well;
- Compiler-generated bridge/synthetic methods;
- Overridden methods and the annotations present on each declaration.

Those decisions are business rules of your tool, **not the inherent meaning of `getName`, `getDeclaringClass`, or `getReturnType`**.

## 8. Common mistakes and how to avoid them

| Misconception | Reality |
| --- | --- |
| `Child.class.getMethod("x")` always has `getDeclaringClass() == Child.class` | The method may be declared in a parent/interface and inherited |
| `getName()` gives the full method signature | It only gives the **simple name**, excluding parameters |
| `getReturnType()` returns the runtime class of the returned value | It returns the **declared type**, without invoking the method |
| `getReturnType()` of `void` is `null` | It is `void.class` |
| `getReturnType()` of `List<String>` preserves `String` | Only `List.class` remains after erasure; use `getGenericReturnType()` when generic metadata is needed |
| `getDeclaringClass()` tells which implementation will run | Declaration metadata and virtual dispatch are two separate matters |
| `getDeclaredMethods()` includes inherited methods | No; it only includes methods declared in the type itself |
| Obtaining a `private Method` means you can call it | Metadata discovery does not automatically bypass access checks |
| One method name corresponds to exactly one Method | Overloading and compiler bridge/synthetic methods can repeat names |
| The order of `getDeclaredMethods()` is the order written in the Java file | The API does not guarantee that order |

When calling `getMethod` or `getDeclaredMethod` with a name/signature that is not found, `NoSuchMethodException` can be thrown. This is an exception of the **lookup step**, not a consequence of calling `getName()`, `getDeclaringClass()`, or `getReturnType()` after obtaining a valid `Method` object.

Calls to `Method.invoke` may also be subject to access checks, throwing `IllegalAccessException`, `InvocationTargetException`, and other errors. Metadata does not automatically grant execution permission or guarantee that the method will run successfully.

## 9. Checklist and self-check questions

Before using Method metadata in a program, you can check in order:

1. Do I need *directly declared methods* or also *inherited methods*? Choose `getDeclaredMethod(s)` or `getMethod(s)` accordingly.
2. Do I need to distinguish overloads? Use the name together with ordered parameter types, not `getName()` alone.
3. Am I asking for the *declaring class* or the *runtime type of the receiver*? Choose the right metadata source.
4. Do I need the *erased return type* or the *generic return signature*? Use `getReturnType()` or `getGenericReturnType()`.
5. Do I need to run the method? If not, stop at metadata; if so, handle access permissions, receiver, and exceptions separately.
6. Am I relying on listing order or overlooking bridge/synthetic methods? Choose an explicit filter/sort.

### Questions

1. What is `Method.getName()` for `parse(String)`? **`"parse"`**; it does not contain `String`.
2. Calling `Child.class.getMethod("inherited")` for a method declared only in `Parent`, what is `getDeclaringClass()`? **`Parent.class`**.
3. Does `void refresh()` have `getReturnType()` equal to `null`? **No.** The result is `void.class`.
4. Does `List<String> tags()` have `getReturnType()` equal to `List<String>.class`? **No such class literal exists**; the result is `List.class`, and generic information resides in `getGenericReturnType()`.
5. A `Method` representing `Parent.status()` is invoked with a `Child` receiver that overrides it; does the Method's owner change? **No.** The owner remains `Parent`, even though virtual dispatch may execute `Child.status()`.
6. To find `parse(int)` without confusing it with `parse(String)`, what should you use? **`getDeclaredMethod("parse", int.class)`** on the declaring class.
7. Does obtaining method metadata via `getDeclaredMethod` automatically grant permission to call a `private` method? **No.** Execution access permissions are checked separately.

## 10. Official references

- [Oracle Java SE 21 — `java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): defines `getName()`, `getDeclaringClass()`, `getReturnType()`, `getGenericReturnType()`, bridge/synthetic, and invocation.
- [Oracle Java SE 21 — `java.lang.Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): distinguishes `getMethod`, `getDeclaredMethod`, `getMethods`, `getDeclaredMethods`, and lookup rules.
- [Java Language Specification SE 21 — §8.4 Method Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4): foundation of overloading, overriding, and return types.

**Takeaway:** `getName()` returns the *name*, `getDeclaringClass()` returns the *type that declares the method*, and `getReturnType()` returns the *formal return type after erasure*. When generic metadata is needed, also use `getGenericReturnType()`; when you need to know which implementation will run, you must consider dynamic dispatch and the receiver rather than inferring from the declaring class.