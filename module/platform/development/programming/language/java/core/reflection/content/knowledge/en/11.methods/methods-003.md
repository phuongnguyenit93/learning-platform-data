# How getMethods() differs from getDeclaredMethods() in Java Reflection

`Class.getMethods()` and `Class.getDeclaredMethods()` both return `Method[]` for discovering methods of a Java type, yet they address **two different needs**. Confusing these two APIs causes Reflection tools to miss inherited methods, miss private methods, pick the wrong method to invoke, or accidentally depend on implementation details.

- **`getMethods()`:** retrieves the **public** methods of the inspected type, including directly declared public methods and public methods inherited under Java rules.
- **`getDeclaredMethods()`:** retrieves **the methods declared directly** on the inspected class/interface itself, across **all access levels**: public, protected, package-private, and private; **excluding** inherited methods.

The word `declared` in the API name means **declared directly on the `Class` being inspected**, not the declared type of a reference variable. To use them properly, you must choose both the right `Class<?>` object and the appropriate lookup API family.

## 1. Direct comparison of the two APIs

The two API signatures belong to `java.lang.Class`:

```java
public Method[] getMethods()
public Method[] getDeclaredMethods()
```

Both return `java.lang.reflect.Method`, but differ in **lookup scope** and **visibility rules**.

| Method kind | `getMethods()` | `getDeclaredMethods()` |
| --- | --- | --- |
| Public, declared directly in the class | Yes | Yes |
| Protected, declared directly in the class | No | Yes |
| Package-private, declared directly in the class | No | Yes |
| Private, declared directly in the class | No | Yes |
| Public, inherited from superclass | Yes | No |
| Public instance/default, inherited from interface | Yes | No |
| Private/protected declared in superclass | No | No |
| Public from `Object` on a normal class | Yes, according to the most-specific method rule | No, unless inspecting `Object.class` itself |
| Bridge/synthetic method declared by compiler in class file | May be present if public and selected in result | May be present, at any access level |
| Constructor | No | No |
| Class initializer `<clinit>` | No | No |

Do not infer that `getMethods()` is equivalent to concatenating all `getDeclaredMethods()` arrays of superclasses/subclasses: Java applies rules for method membership, overriding/hiding, most-specific method selection, and interface inheritance. Neither array guarantees ordering; if a deterministic result is needed, **sort it yourself**.

A class may contain a `private` method that `getMethods()` still does not see. Conversely, a class that declares no methods at all can still return many elements from `getMethods()` by inheriting public methods from `Object`.

## 2. Choose the right Class before choosing the API

Consider this illustrative snippet:

```java
Parent ref = new Child();

Class<?> staticType = Parent.class;
Class<?> runtimeType = ref.getClass(); // Child.class
```

The declared type of `ref` is `Parent`. The actual type of the referenced object is `Child`. Both APIs operate on **the type on which you invoke them**, so:

- `Parent.class.getDeclaredMethods()`: only methods declared on `Parent`.
- `Parent.class.getMethods()`: public methods of `Parent`, including inherited public methods.
- `Child.class.getDeclaredMethods()`: only methods declared on `Child`, including private methods.
- `Child.class.getMethods()`: public methods of `Child` and applicable inherited public methods.

A Reflection `Method` object also has `getDeclaringClass()` to tell **which class/interface actually declares that method**. The declaring class may differ from the `Class<?>` used to start the search.

## 3. Complete Java 17+ program

Create the file `MethodDiscoveryDemo.java`:

```java
import java.lang.reflect.Method;

public class MethodDiscoveryDemo {
    interface Named {
        default String label() {
            return "from-interface";
        }
    }

    static class Parent {
        public String parentOnly() {
            return "parent";
        }

        public String describe() {
            return "Parent";
        }

        protected void protectedParent() {
        }

        private void privateParent() {
        }
    }

    static final class Child extends Parent implements Named {
        @Override
        public String describe() {
            return "Child";
        }

        public String childOnly() {
            return "child";
        }

        protected void protectedChild() {
        }

        private void privateChild() {
        }
    }

    static boolean contains(Method[] methods, String name) {
        for (Method method : methods) {
            if (method.getName().equals(name)) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {

        Class<?> type = Child.class;
        Method[] publicMethods = type.getMethods();
        Method[] declaredMethods = type.getDeclaredMethods();

        System.out.println("public parentOnly: "
                + contains(publicMethods, "parentOnly"));
        System.out.println("declared parentOnly: "
                + contains(declaredMethods, "parentOnly"));
        System.out.println("public childOnly: "
                + contains(publicMethods, "childOnly"));
        System.out.println("declared childOnly: "
                + contains(declaredMethods, "childOnly"));
        System.out.println("public label: "
                + contains(publicMethods, "label"));
        System.out.println("declared label: "
                + contains(declaredMethods, "label"));
        System.out.println("public privateChild: "
                + contains(publicMethods, "privateChild"));
        System.out.println("declared privateChild: "
                + contains(declaredMethods, "privateChild"));
        System.out.println("public protectedChild: "
                + contains(publicMethods, "protectedChild"));
        System.out.println("declared protectedChild: "
                + contains(declaredMethods, "protectedChild"));
        System.out.println("public toString: "
                + contains(publicMethods, "toString"));
        System.out.println("declared toString: "
                + contains(declaredMethods, "toString"));

        Method inherited = type.getMethod("parentOnly");
        System.out.println("parentOnly declared in: "
                + inherited.getDeclaringClass().getSimpleName());

        Method overridden = type.getMethod("describe");
        System.out.println("describe declared in: "
                + overridden.getDeclaringClass().getSimpleName());

        Method fromParent = Parent.class.getMethod("describe");
        System.out.println("invoke Parent.describe on Child: "
                + fromParent.invoke(new Child()));

        try {
            type.getDeclaredMethod("parentOnly");
        } catch (NoSuchMethodException e) {
            System.out.println("declared parentOnly lookup: missing");
        }

        try {
            type.getMethod("privateChild");
        } catch (NoSuchMethodException e) {
            System.out.println("public privateChild lookup: missing");
        }
    }
}
```

Run with JDK 17 or later:

```bash
javac MethodDiscoveryDemo.java
java MethodDiscoveryDemo
```

Stdout result:

```text
public parentOnly: true
declared parentOnly: false
public childOnly: true
declared childOnly: true
public label: true
declared label: false
public privateChild: false
declared privateChild: true
public protectedChild: false
declared protectedChild: true
public toString: true
declared toString: false
parentOnly declared in: Parent
describe declared in: Child
invoke Parent.describe on Child: Child
declared parentOnly lookup: missing
public privateChild lookup: missing
```

The program checks **whether a method exists by name**, so the output is deterministic even if the order of elements returned by Reflection changes. In real applications, method names may be overloaded; you need to check parameters too, not just use this `contains` function.

Meaning of each result group:

1. `parentOnly()` is a public method **inherited** from `Parent`. `Child`'s `getMethods()` sees it; `getDeclaredMethods()` does not.
2. `childOnly()` is a public method **declared directly** in `Child`, so it appears in both sets.
3. `label()` is a public default method of interface `Named`. `Child` inherits it without declaring it itself; hence it only appears in the combined public set.
4. `privateChild()` and `protectedChild()` are declared in `Child`. They appear in the declared set; because they are not public, they do not appear in the `getMethods()` set.
5. `toString()` comes from `Object`. Normal classes inherit this public method, whereas `Child` does not declare it directly.
6. `getDeclaringClass()` of `parentOnly` is `Parent`. Meanwhile `describe` is overridden in `Child`, so the public method selected on `Child` has declaring class `Child`.
7. `Parent.class.getMethod("describe").invoke(new Child())` returns `"Child"` due to **dynamic dispatch** of instance methods. Selecting metadata from the superclass does not force the JVM to execute the superclass body.
8. `getDeclaredMethod("parentOnly")` on `Child` and `getMethod("privateChild")` both fail, but for **two different reasons**: the former is not a direct declaration; the latter is not public.

## 4. Interfaces, Object, and special cases

### Public default methods of an interface

```java
interface HasName {
    default String name() {
        return "unknown";
    }
}

class Person implements HasName {
}
```

In this illustrative snippet:

- `Person.class.getMethods()` sees `name()` because it is a public instance method inherited from the interface.
- `Person.class.getDeclaredMethods()` does not see `name()` because the class does not declare that method.
- `HasName.class.getDeclaredMethods()` sees `name()` because the interface declares it directly.

Conversely, a **static method declared on an interface is not inherited by an implementing class** in the same way as a default instance method. A private method of an interface is also not a public member method of an implementing class. Always distinguish static/default/private when handling interfaces.

### Object methods on classes and interfaces

For regular classes, `getMethods()` includes applicable public methods from `Object`, unless a more specific override replaces that method in the result. For **interfaces**, the `getMethods()` array **does not implicitly include methods from `Object`**. Therefore:

```java
interface Empty {
}
```

`Empty.class.getMethods()` is an empty array; it does not automatically add `toString()` or `hashCode()`. This differs from `new Object().getClass().getMethods()`.

For **array classes**, `getMethods()` returns public methods inherited from `Object`, but does not return `clone()`. Meanwhile `getDeclaredMethods()` on an array type, primitive type, or `void` returns an empty array.

### Overridden methods and hidden methods

When a subclass overrides a public instance method of a superclass, `getMethods()` applies appropriate selection rules and prefers the more specific declaration. For static methods, a subclass declaring a method with the same signature is **hiding**, not dynamic overriding. Therefore, do not compare names alone to infer which method will execute upon invocation.

## 5. Retrieving a Method by name and signature

Two APIs correspond to fetching a specific method:

```java
Class<?> type = Example.class;

Method first = type.getMethod("run", String.class);
Method second = type.getDeclaredMethod("run", String.class);
```

This is an illustrative snippet; `Example` must exist and have a matching method; handle `NoSuchMethodException` when lookup fails.

| API | Scope |
| --- | --- |
| `getMethod(name, parameterTypes...)` | Searches for a **public member method**, including inherited ones |
| `getDeclaredMethod(name, parameterTypes...)` | Searches for a **directly declared** method, regardless of access |

The parameters of both methods accept `Class<?>` values representing **formal parameter types**, in exact order, **not the return type**. With overloads:

```java
class Printer {
    public void print(String text) {
    }

    public void print(int number) {
    }
}
```

Correct lookup calls:

```java
Method textMethod = Printer.class.getMethod("print", String.class);
Method numberMethod = Printer.class.getMethod("print", int.class);
```

This is illustrative code; declaring `Method` requires `import java.lang.reflect.Method;` and the calls can throw `NoSuchMethodException`.

`getMethod("print", Object.class)` does not apply source-code overload resolution via `Object`/`String` conversions: you must use the exact declared parameter type list. For varargs, the metadata of the last parameter is an **array** type, such as `String[].class`; use `Method.isVarArgs()` to check the varargs characteristic.

`getMethod` and `getDeclaredMethod` do not return constructors. To look up a constructor, use `getConstructor(...)` or `getDeclaredConstructor(...)`.

## 6. Having Method metadata does not mean you can invoke it

`getDeclaredMethods()` lists private methods too, but metadata visibility **does not automatically grant permission** to call that method.

```java
Method method = type.getDeclaredMethod("privateAction");
Object result = method.invoke(target);
```

This is an illustrative snippet, runnable only when `type`, `target`, signature, and access permissions match. `invoke` can throw `IllegalAccessException` if the method is not accessible; an invoked method can throw a business exception wrapped in `InvocationTargetException`.

Some code uses `method.setAccessible(true)` or `trySetAccessible()` to request deep access. However, on Java 17+, **JPMS strong encapsulation** may refuse it because the named module's package is not open to the caller. `setAccessible(true)` may throw `InaccessibleObjectException`; `trySetAccessible()` may return `false`. This is independent of whether the method is returned by `getDeclaredMethods()`.

For application APIs, prefer public methods or clear interfaces/factories. Use deep Reflection for non-public members only when genuinely justified and properly permitted.

## 7. Bridge and synthetic methods make the array differ from source code

`getDeclaredMethods()` does not promise that every element corresponds to a method written by the programmer. The compiler can generate extra **bridge** or **synthetic methods**, typically when generic erasure or covariant return types affect an overridden method.

```java
class Holder<T> {
    public T value() {
        return null;
    }
}

class TextHolder extends Holder<String> {
    @Override
    public String value() {
        return "text";
    }
}
```

This illustrative snippet is typically compiled by `javac` into a `String value()` method and a JVM-signature-compatible bridge method with return type `Object`. Thus `TextHolder.class.getDeclaredMethods()` may contain more than one method named `value`.

Inspecting metadata:

```java
for (java.lang.reflect.Method method
        : TextHolder.class.getDeclaredMethods()) {
    System.out.println(method.getName()
            + ", bridge=" + method.isBridge()
            + ", synthetic=" + method.isSynthetic());
}
```

The snippet requires `TextHolder` declared above and is not a standalone program. Line order is not guaranteed. `getMethods()` may also return public bridge methods in its matching result set.

Filter `isBridge()` or `isSynthetic()` **according to purpose**: a scanner for "developer-declared APIs" often needs to filter them out; a bytecode/compatibility analysis tool should keep them to reflect the actual class file.

In theory, a class file can contain multiple methods with the same **name and parameter types** but different return types, even though Java source code forbids declaring overloads differing only in return type. Therefore, single-lookup methods `getMethod`/`getDeclaredMethod` have selection rules when multiple candidates share the same name and parameters; do not assume the `getDeclaredMethods()` array always has at most one element per name/parameter pair.

## 8. Traversing the hierarchy when you also need structurally inherited non-public methods

No single `getDeclaredMethods()` call on `Child.class` automatically retrieves private/protected methods declared in all superclasses. If you are writing an inspector that needs to view **every declaration across the entire class hierarchy**, traverse it:

```java
Class<?> current = Child.class;

while (current != null) {
    for (java.lang.reflect.Method method
            : current.getDeclaredMethods()) {
        System.out.println(current.getSimpleName()
                + "." + method.getName());
    }
    current = current.getSuperclass();
}
```

This is an illustrative snippet using `Child` from the example in section 3. Notes:

- The loop only traverses the **superclass chain**, not superinterfaces. To analyze interfaces, you must also process `getInterfaces()` and their hierarchies.
- An overridden method in the subclass and a method with the same signature in the superclass may appear as **two separate declarations**; do not deduplicate them blindly if you need to know the origin of each method.
- The order of `getDeclaredMethods()` is not guaranteed; sorting is needed if producing a stable report.
- A private method of a superclass may have its metadata listed, but that does not make it an inherited public method of the subclass.

If the goal is solely the public API callable from outside, `getMethods()` is usually more concise and accurate without manually walking the entire hierarchy.

## 9. Sorting and filtering Methods for stable tools

When printing Reflection lists to documentation, UI, or test outputs, do not depend on the order returned by the JVM. For example:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

class MethodPrinter {
    static void printPublic(Class<?> type) {
        Method[] methods = type.getMethods();

        Arrays.sort(methods,
                Comparator.comparing(Method::getName)
                        .thenComparing(Method::toGenericString));

        for (Method method : methods) {
            System.out.println(method.getName() + " -> "
                    + method.getDeclaringClass().getName());
        }
    }
}
```

This snippet is an illustrative utility class with no `main` method. The comparator makes the order consistent **for the same metadata set**. The set of public methods can still change when the type or JDK version changes.

Some useful filters:

- `Modifier.isPublic(method.getModifiers())` to check the public flag when analyzing `getDeclaredMethods()`.
- `method.getDeclaringClass() == type` to find methods whose declaring class is the inspected type itself.
- `method.isBridge()` / `method.isSynthetic()` to handle compiler-generated methods.
- `method.getParameterTypes()`, `method.getReturnType()`, `method.isVarArgs()` when distinguishing methods by signature.
- `method.getAnnotation(YourAnnotation.class)` when needing a specific annotation; you must define a policy for finding annotations on direct declarations, overrides, or interfaces rather than assuming method annotations are automatically inherited.

Do not filter `getMethods()` by `getDeclaringClass()==type` and assume the result equals `getDeclaredMethods()`: that approach still **misses non-public methods**.

## 10. Which API should you choose?

| Need | Recommendation |
| --- | --- |
| List public API of a class/interface along with inherited public methods | `getMethods()` |
| Look up a public member method by name + parameter type list | `getMethod(...)` |
| Inventory methods declared directly on a class, including private/protected | `getDeclaredMethods()` |
| Look up a single direct method regardless of access | `getDeclaredMethod(...)` |
| Scan annotations across all declarations in a class hierarchy | Traverse each class and use `getDeclaredMethods()`, adding interfaces when needed |
| Retrieve only methods belonging to a specific class | Check `getDeclaringClass()`, while choosing the input set matching access requirements |
| Output results in a consistent order | Sort `Method[]` using a comparator |
| Invoke a non-public method | Verify necessity, Java/JPMS access rights, and receiver before invoking |

A note on proxies/frameworks: `obj.getClass()` may return a **runtime proxy class**, not the class declaring the business contract. If you want to inspect the exact API consumers are allowed to use, start with `YourInterface.class` or the configured contract class. If the goal is debugging the implementation, use the runtime class with an appropriate filtering policy.

## 11. Common mistakes

1. **Confusing declared with variable type:** `object.getClass().getDeclaredMethods()` discovers direct methods of the **runtime class**, not the static type of the variable.
2. **Thinking `getMethods()` only returns self-written methods:** it also returns public methods from superclasses, interfaces, and normally from `Object`.
3. **Thinking `getDeclaredMethods()` includes private methods in superclasses:** it only includes private methods declared **on the inspected type itself**.
4. **Seeing a `Method` and immediately calling `invoke`:** access rights, receiver object, parameter types, JPMS, and checked exceptions still need handling.
5. **Filtering by name while forgetting overloads:** you must inspect parameter types, and sometimes return types and bridge methods.
6. **Comparing the direct method count to Java source declarations:** the compiler may add bridge/synthetic methods.
7. **Trusting Reflection ordering:** neither array is guaranteed by the API to be sorted.
8. **Assuming `Object` methods are added to interfaces:** `getMethods()` of an interface does not contain implicit methods from `Object`.
9. **Using `getMethods()` to find constructors:** constructors have their own APIs.
10. **Inferring dynamic dispatch from declaring class:** a method may be looked up from a superclass yet invoking it on a subclass instance still runs the override.

## 12. Self-check

With `MethodDiscoveryDemo` in section 3:

1. Does `Child.class.getDeclaredMethods()` contain `parentOnly()`? **No**, because the method is declared in `Parent`.
2. Does `Child.class.getMethods()` contain `parentOnly()`? **Yes**, because it is an inherited public method.
3. Does `Child.class.getDeclaredMethods()` contain `privateChild()`? **Yes**, because the method is declared directly, even though it is private.
4. Does `Child.class.getMethods()` contain `privateChild()`? **No**, because this set only searches for public member methods.
5. Does `Child.class.getMethods()` contain `Named.label()`? **Yes**, because it is an inherited public default instance method.
6. What does `Method parentMethod = Parent.class.getMethod("describe"); parentMethod.invoke(new Child())` return? **`"Child"`**, due to dispatch of the overridden instance method.
7. If you need to list private methods from each superclass and subclass, is a single `getDeclaredMethods()` call on `Child` enough? **No**; you must traverse the class hierarchy.

**Takeaway:** `getMethods()` answers the question **"what public methods does this type have under inheritance rules?"**; `getDeclaredMethods()` answers the question **"what methods does this type itself declare, across all access levels?"**. Always combine the starting `Class<?>` object, `Method.getDeclaringClass()`, and access checks to interpret results accurately.

### Official documentation

- [Java SE 17 — java.lang.Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — java.lang.reflect.Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [dev.java — Invoking Methods](https://dev.java/learn/api/reflection-method-handles/reflection/methods/)