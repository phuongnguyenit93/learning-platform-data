# Member Lookup Using `getField`, `getMethod`, and `getConstructor` in Java Reflection

In Java Reflection, a `Class<?>` object allows looking up **fields**, **methods**, and **constructors** from type information at runtime. The three APIs `getField`, `getMethod`, and `getConstructor` are commonly used when a member name or constructor signature is only determined while the program is running, such as in serializers, dependency injection frameworks, API validators, or plugin mechanisms.

An important commonality: all three APIs search for **`public` members**. However, **fields and methods can be inherited**, whereas **constructors are not inherited**. If you need `private`, `protected`, or package-private members, or need to know the exact members **declared directly on the class**, use the corresponding `getDeclaredField`, `getDeclaredMethod`, or `getDeclaredConstructor` APIs.

## 1. The Big Picture

| `Class` API | Return Value | Lookup Criteria | Considers Inherited Members? | Access Scope During Lookup |
|---|---|---|---|---|
| `getField(String name)` | `Field` | Field name | Yes, from superclass or interface per field lookup rules | `public` only |
| `getMethod(String name, Class<?>... parameterTypes)` | `Method` | Method name and parameter type sequence | Yes, including methods inherited from superclass/interface | `public` only |
| `getConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Constructor parameter type sequence | **No**; constructors belong only to the declaring class | `public` only |
| `getDeclaredField(String name)` | `Field` | Directly declared field name | No | All access levels |
| `getDeclaredMethod(String name, Class<?>... parameterTypes)` | `Method` | Directly declared method name and parameter types | No | All access levels |
| `getDeclaredConstructor(Class<?>... parameterTypes)` | `Constructor<T>` | Directly declared constructor parameter types | No | All access levels |

The three `get...` APIs return **one** member. To list multiple members, use `getFields()`, `getMethods()`, `getConstructors()`, or the plural `getDeclared...` versions. The order of elements returned by the listing APIs is **not guaranteed**; do not rely on array position to select a member.

A successful lookup only proves that Reflection **found the metadata**. It does not mean the member can be read, written, invoked, or instantiated from every caller: at usage time, Java still applies access rules and module restrictions.

## 2. `getField(String name)`: Finding a `public` Field

Signature:

```java
Field field = SomeType.class.getField("fieldName");
```

`getField` finds a `public` field with the exact requested name. That field may be **declared directly** on the target class or **inherited** from a superclass/interface. It returns `java.lang.reflect.Field`, providing metadata such as `getName()`, `getType()`, `getModifiers()`, `getDeclaringClass()`.

Hypothetical example:

```java
class Base {
    public int count;
}

class Derived extends Base {
    private String secret;
}
```

- `Derived.class.getField("count")` **succeeds**: `count` is a `public` field inherited from `Base`.
- `Derived.class.getField("secret")` throws `NoSuchFieldException`: `secret` is not `public`.
- `Derived.class.getDeclaredField("secret")` **succeeds**: this field is declared directly on `Derived`, even though it is `private`.
- `Derived.class.getDeclaredField("count")` throws `NoSuchFieldException`: `count` is declared in `Base`, not `Derived`.

Do not confuse **discovering a `Field`** with **reading a field value**:

```java
Field field = Derived.class.getField("count");
Derived object = new Derived();
int value = field.getInt(object);
field.setInt(object, 42);
```

This is an independent illustrative snippet about `Field` operations, using the two classes declared above. `field.getInt(object)` reads the `int` field value of the instance; `setInt` assigns a new value. For `static` fields, the receiver for `Field.get(null)` can be `null`. Access rules and restrictions on writing `final` fields still apply.

**Field hiding:** if a subclass declares a new field **with the same name** as a field in the superclass, the two fields remain two separate members; this is not an overriding mechanism like methods. When you need to select the exact original field, look up on `Base.class` or use `getDeclaredField` on the class that actually declares the field. When interfaces provide multiple `public` fields with the same name, do not rely on an ambiguous lookup; choose the specific declaring interface.

## 3. `getMethod(String name, Class<?>... parameterTypes)`: Finding a `public` Method

Signature:

```java
Method method = SomeType.class.getMethod("methodName", String.class, int.class);
```

The lookup uses the **method name** and the **parameter type sequence in exact order**. A `public` method may belong to the current class or be inherited from a superclass/interface. `getMethod("save", String.class)` differs from `getMethod("save", Object.class)` and differs from `getMethod("save")`.

Example:

```java
class Service {
    public void run() { }
    public void run(String text) { }
    public void run(String text, int count) { }
    private void reset() { }
}
```

```java
Method m0 = Service.class.getMethod("run");
Method m1 = Service.class.getMethod("run", String.class);
Method m2 = Service.class.getMethod("run", String.class, int.class);
Method hidden = Service.class.getDeclaredMethod("reset");
```

The statements above are **illustrative snippets**, not a program with `main`. `m0`, `m1`, `m2` correspond to the three overloads. `getMethod("reset")` does not find `reset` because it is `private`; `getDeclaredMethod("reset")` finds the metadata.

### Parameter Types Must Match the Declared Signature

- `int.class` **differs from** `Integer.class`; lookup does not automatically box/unbox to find another signature.
- `String.class` **differs from** `Object.class`; lookup does not choose an overload simply because a runtime argument is assignable to that parameter type.
- Varargs `String... values` is declared as an array in bytecode; look it up with `String[].class`.
- For `List<String>`, the regular runtime signature uses the **erased** type: `List.class`; there is no `List<String>.class`.
- Parameter order matters: `(String, int)` differs from `(int, String)`.
- Do not pass the return type into `getMethod`; Java does not overload methods solely by return type at the regular source-code level.

Illustrative example for two special signatures:

```java
// Suppose Example declares:
// public void accept(int value) { }
// public void collect(String... values) { }

Method accept = Example.class.getMethod("accept", int.class);
Method collect = Example.class.getMethod("collect", String[].class);
```

`Integer.class` cannot replace `int.class` in the `accept` lookup. For generic methods, bridge/synthetic methods may appear in metadata; when inspecting a set of methods, `isBridge()` and `isSynthetic()` can be used depending on the purpose.

### Lookup Differs from Execution

`getMethod` only retrieves metadata. When execution is needed:

```java
Method method = Service.class.getMethod("run", String.class);
Service service = new Service();
method.invoke(service, "hello");
```

`Method.invoke` is what runs the method's logic. For `static` methods, a `null` receiver can be used. An exception thrown by the invoked method is usually wrapped in `InvocationTargetException`; inspect `getCause()` to find the root error. The parameter types of the arguments passed to `invoke` must still be compatible; a valid lookup does not guarantee a call with valid arguments.

**Method overriding:** when a subclass overrides a `public` method, `getMethod` usually returns the method corresponding to the specific overridden version. When a class only inherits a method and does not override it, `getDeclaringClass()` points to the declaring class in the superclass/interface. In bytecode there may be bridge methods or methods with the same name and parameters but different return types; Reflection has its own selection rules, so in compiler-generated bridge cases inspect actual metadata rather than inferring from a simple Java source signature.

## 4. `getConstructor(Class<?>... parameterTypes)`: Finding a `public` Constructor

Signature:

```java
Constructor<User> constructor = User.class.getConstructor(String.class);
```

A constructor has no separate method name during lookup; pass only the **parameter type sequence**. If the constructor takes no parameters, call `getConstructor()`. This API only finds **`public` constructors declared by the target class itself**. Superclass constructors are not inherited.

```java
class Account {
    public Account() { }
    public Account(String id) { }
    private Account(int internalCode) { }
}
```

```java
Constructor<Account> a = Account.class.getConstructor();
Constructor<Account> b = Account.class.getConstructor(String.class);
Constructor<Account> internal = Account.class.getDeclaredConstructor(int.class);
```

This is an illustrative snippet. `Account.class.getConstructor(int.class)` fails because that constructor is `private`; `getDeclaredConstructor(int.class)` returns metadata but does not automatically grant permission to call it.

Creating an object with `Constructor.newInstance`:

```java
Constructor<Account> ctor = Account.class.getConstructor(String.class);
Account instance = ctor.newInstance("A-001");
```

The constructor actually runs at the `newInstance` step. If the class has not been initialized yet, the JVM initializes the class before creating the instance. A class not declaring any constructor in **source code** may result in a compiler-generated default constructor, but **the access level of the default constructor depends on the access level of the class**. Do not assume `getConstructor()` always yields a result: for some classes, no `public` no-arg constructor exists.

For interfaces, abstract classes, arrays, and primitive types, one cannot assume there is a constructor capable of instantiating an object this way. `getConstructor(...)` may report that no matching constructor was found; even if a constructor of an abstract class is found, `newInstance` still cannot instantiate an abstract class.

## 5. Complete Java 17+ Example: Public, Inheritance, Overload, Constructor

Create the file **`MemberLookupDemo.java`**. The nested classes are declared `static` so the example can run from a standalone file:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class MemberLookupDemo {
    public interface Tagged {
        String TAG = "interface-tag";
    }

    public static class Parent {
        public int inherited = 10;

        public String origin() {
            return "Parent.origin";
        }
    }

    public static class Child extends Parent implements Tagged {
        public int own = 20;
        private String secret = "hidden";

        public Child() {
        }

        public Child(String text) {
            own = text.length();
        }

        private Child(int value) {
            own = value;
        }

        public String echo() {
            return "echo:empty";
        }

        public String echo(String text) {
            return "echo:" + text;
        }

        private void hidden() {
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Child> type = Child.class;

        Field inherited = type.getField("inherited");
        Field fromInterface = type.getField("TAG");
        Field own = type.getField("own");

        System.out.println(inherited.getDeclaringClass().getSimpleName());
        System.out.println(fromInterface.getDeclaringClass().getSimpleName());
        System.out.println(own.getDeclaringClass().getSimpleName());

        Method origin = type.getMethod("origin");
        Method echoString = type.getMethod("echo", String.class);
        System.out.println(origin.getDeclaringClass().getSimpleName());
        System.out.println(echoString.getDeclaringClass().getSimpleName());
        System.out.println(type.getMethod("echo").getParameterCount());

        Constructor<Child> empty = type.getConstructor();
        Constructor<Child> withText = type.getConstructor(String.class);
        System.out.println(empty.getParameterCount());

        Child child = withText.newInstance("Java");
        System.out.println(child.own);
        System.out.println(inherited.getInt(child));
        System.out.println(origin.invoke(child));
        System.out.println(echoString.invoke(child, "Reflection"));

        try {
            type.getField("secret");
        } catch (NoSuchFieldException e) {
            System.out.println("secret: not public");
        }
        System.out.println(type.getDeclaredField("secret").getName());

        try {
            type.getConstructor(int.class);
        } catch (NoSuchMethodException e) {
            System.out.println("int constructor: not public");
        }
        System.out.println(type.getDeclaredConstructor(int.class).getParameterCount());

        try {
            type.getMethod("hidden");
        } catch (NoSuchMethodException e) {
            System.out.println("hidden: not public");
        }
        System.out.println(type.getDeclaredMethod("hidden").getName());
    }
}
```

Run in the directory containing the file:

```bash
javac MemberLookupDemo.java
java MemberLookupDemo
```

Stdout:

```text
Parent
Tagged
Child
Parent
Child
0
0
4
10
Parent.origin
echo:Reflection
secret: not public
secret
int constructor: not public
1
hidden: not public
hidden
```

Matching the output:

1. `getField("inherited")` returns the `Field` declared in `Parent`; `getField("TAG")` finds the `public static final` field of interface `Tagged`; `getField("own")` belongs to `Child`. `getDeclaringClass()` helps determine the **actual declaring location**, not necessarily the `Class` used for lookup.
2. `getMethod("origin")` gets the method from `Parent`; `getMethod("echo", String.class)` gets the method of `Child`. The `echo()` overload has `0` parameters.
3. `getConstructor()` succeeds because `Child` has a `public` no-arg constructor. The constructor taking `String` is invoked with `"Java"`, length 4, so `own` becomes `4`.
4. `Field.getInt(child)` reads the inherited field `inherited = 10`; `Method.invoke` actually invokes the two methods and receives `Parent.origin` along with `echo:Reflection`.
5. The operations `getField("secret")`, `getConstructor(int.class)`, and `getMethod("hidden")` all fail because those members are `private`. The three corresponding `getDeclared...` operations **can look up the metadata**, even though the members are not `public`.
6. The example **does not invoke** private members. Finding via `getDeclared...` and being allowed to use via Reflection are two separate issues.

## 6. When to Use `getDeclared...`?

There are two different questions:

- **"Which public members can a caller see through this type?"** → `getField`, `getMethod`, `getConstructor`.
- **"Which members has this class itself declared, including private ones?"** → `getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor`.

For example, a property mapping framework may need to find `private` fields declared in a class; an API contract checker may only care about `public` methods, including inherited ones.

Do not assume a `private` member obtained with `getDeclaredField` can be read immediately:

```java
// Illustrative snippet: type is a Class<?> already determined.
Field privateField = type.getDeclaredField("secret");
boolean accessible = privateField.trySetAccessible();
if (!accessible) {
    throw new IllegalStateException("Private field is not reflectively accessible");
}
```

`trySetAccessible()` requests bypassing certain Java Reflection access checks if the platform and module relationships permit it; it can return `false`. With named modules, having `private` metadata **does not remove** the encapsulation mechanism of the Java Platform Module System. In real applications, prefer public APIs, constructors/factories, or intentional module `opens` when deep reflective access is needed. Avoid automatically enabling access for every member.

**Note on searching in superclasses:** `getDeclaredField("x")` does not automatically walk up the inheritance tree. If an application must find non-public fields across multiple levels, it must actively traverse `getSuperclass()` and look up `getDeclaredField` at each level, with clear rules when names are hidden. This is a different operation from `getField`.

## 7. Handling Failures and Distinguishing Errors

| Case | Exception or Symptom | How to Handle |
|---|---|---|
| No `public` field with exact name | `NoSuchFieldException` from `getField` | Check name, declaring location, access level; consider `getDeclaredField` if non-public metadata is needed. |
| No `public` method with exact name + parameter types | `NoSuchMethodException` from `getMethod` | Check overloads, `int.class` vs `Integer.class`, array type for varargs, and generic erasure. |
| No `public` constructor with exact type sequence | `NoSuchMethodException` from `getConstructor` | Check constructors declared on the class itself and access levels. |
| Method found but caller is not permitted to invoke | `IllegalAccessException` from `Method.invoke` | Inspect visibility and module exports/opens; use public API or appropriate permissions. |
| Invoked method/constructor throws an exception | `InvocationTargetException` | Inspect `getCause()` to see the original exception from the executed code. |
| Constructor cannot instantiate an abstract class | `InstantiationException` on `newInstance` | Use a concrete implementation with a suitable constructor. |
| Arguments to `invoke`/`newInstance` are incompatible | `IllegalArgumentException` may occur | Compare argument count, types, and actual receiver with parameter types. |
| Attempting to bypass module reflective access limits | `InaccessibleObjectException` may occur with `setAccessible(true)` | Review module boundaries; do not assume every member can be opened for access. |

At **lookup** time, most "does not exist with exact signature" errors are checked exceptions `NoSuchFieldException`/`NoSuchMethodException`. At the time of **using** `Field`, `Method`, or `Constructor`, exceptions related to access permissions, parameters, and executed code become important.

Example of handling a required method (snippet has `Class<?> type` already defined):

```java
try {
    Method method = type.getMethod("execute", String.class);
    // Next steps can check modifiers and access permissions
    // before invoking the method with an appropriate receiver/argument.
} catch (NoSuchMethodException e) {
    throw new IllegalArgumentException(
            "Expected public execute(String) method on " + type.getName(), e);
}
```

Do not use `catch (Exception)` to swallow all lookup errors and assume the class does not support a feature. You must distinguish **member not found** from **found, but invocation failed** to diagnose accurately.

## 8. Common Conceptual Mistakes

1. **"`getDeclaredMethod` includes inherited methods."** False: `declared` includes only methods declared directly in this class/interface.
2. **"`getConstructor` automatically finds superclass constructors."** False: constructors are not inherited.
3. **"`getMethod` automatically picks an overload from the arguments to be passed later."** False: you must supply the exact `Class<?>...` of parameter types **right at lookup time**.
4. **"`getField` only finds fields of the current class itself."** False: it can find `public` fields from superclasses/interfaces.
5. **"Finding a private member means being able to call the private member."** False: metadata retrieval and reflective access are two separate steps.
6. **"Passing `Integer.class` will find a method declared with `int`."** False: types in a reflective signature are exact, with no boxing during lookup.
7. **"`getMethod("work")` means invoking the `work` method."** False: it only returns a `Method`; invoke it with `invoke` or normal Java.
8. **"`getMethods()[0]` is always the first method in source code."** False: the API does not guarantee listing order.
9. **"A field has a getter so `getField("name")` finds that property."** False: getter `getName()` is a method; basic Java Reflection does not automatically turn a JavaBean property into a field of the same name.
10. **"Looking up a no-arg constructor must be written as `getConstructor(null)`."** Avoid this: use **`getConstructor()`** to pass an empty parameter type sequence, which is clear and safe with varargs.

## 9. Self-Check Exercises

**Question 1.** `Child extends Parent`, `Parent` declares `public void show()`, `Child` does not override it. Which lookup finds `show` from `Child.class`?

**Answer:** `Child.class.getMethod("show")` finds it; `Child.class.getDeclaredMethod("show")` throws `NoSuchMethodException`.

**Question 2.** `Service` declares `public void process(int n)`. What type must be passed to `getMethod`?

**Answer:** `Service.class.getMethod("process", int.class)`. `Integer.class` is a different signature.

**Question 3.** A `Customer` has `private Customer(String id)`. Do `Customer.class.getConstructor(String.class)` and `Customer.class.getDeclaredConstructor(String.class)` yield the same result?

**Answer:** No. The version without `Declared` does not find the `private` constructor; the `Declared` version returns metadata, though permission to invoke the constructor still depends on access.

**Question 4.** Why should you call `getDeclaringClass()` on a found `Field`/`Method`?

**Answer:** To know which class/interface actually declares the member, especially when looking up via a subclass and there is inheritance or field hiding.

**Question 5.** Can an object be created just by calling `getConstructor()`?

**Answer:** `getConstructor()` only returns metadata for a `public` no-arg constructor **if one exists**. You must call `Constructor.newInstance()` to request object creation, and the class must be instantiable.

## Standard Reference Documentation

- Java SE API, `java.lang.Class`: `getField`, `getMethod`, `getConstructor`; `getDeclaredField`, `getDeclaredMethod`, `getDeclaredConstructor`.
- Java SE API, `java.lang.reflect.Field`: `get`, `getInt`, `set`, `getDeclaringClass`.
- Java SE API, `java.lang.reflect.Method`: `invoke`, `getParameterTypes`, `isBridge`, `isSynthetic`.
- Java SE API, `java.lang.reflect.Constructor`: `newInstance`, `getParameterTypes`.
- Java Language Specification, sections on inheritance, access control, method signatures, and constructor declarations.

**Takeaway:** `getField` looks up a **`public` field by name**; `getMethod` looks up a **`public` method by name and parameters**; `getConstructor` looks up a **`public` constructor of the class itself by parameters**. Add `Declared` when you want metadata of directly declared members regardless of access level, and always separate **lookup** from **access/execution**.