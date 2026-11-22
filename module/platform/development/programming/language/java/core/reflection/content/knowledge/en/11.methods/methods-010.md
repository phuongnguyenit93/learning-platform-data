# Abstract, default, and interface methods in Java Reflection

In Java Reflection, a `java.lang.reflect.Method` object describes a method declared in a **class or interface**. Not every `Method` has a body that executes directly: `abstract` methods define a contract, `default` methods in interfaces provide a default implementation, `static` methods belong to the interface, and `private` interface methods only serve internal logic. How Reflection **discovers** a method and how `Method.invoke(...)` **executes** it are two separate concerns to keep distinct.

This lesson shows how to identify method kinds using `Modifier.isAbstract(...)`, `Method.isDefault()`, and `Modifier.isStatic(...)`; distinguish the scope of `getDeclaredMethod(s)` vs. `getMethod(s)`; invoke interface methods via Reflection; understand inheritance, overriding, and default method conflicts; and avoid confusing a *default method* with an annotation's *default value*.

## 1. Accurately identifying method kinds

Example of an interface declaring four kinds of methods:

~~~java
interface Named {
    String name(); // implicitly public abstract

    default String greeting() {
        return decorate("Hi " + name());
    }

    static String source() {
        return "interface-static";
    }

    private String decorate(String text) {
        return "[" + text + "]";
    }
}
~~~

This is an **illustrative snippet**, not a standalone program. Java 8 introduced `default` and `static` methods in interfaces; since Java 9, interfaces can have `private` methods (instance or static) to share internal logic. A `private` interface method has a body, yet is not a default method and is not inherited as a public API.

| Declaration on interface | Has a body? | Reflection modifiers/methods to observe | `Method.isDefault()` |
| --- | --- | --- | --- |
| `String name();` | No | `Modifier.isAbstract(method.getModifiers()) == true` | `false` |
| `default String greeting() {...}` | Yes | Public, non-abstract, non-static; `method.isDefault() == true` | `true` |
| `static String source() {...}` | Yes | `Modifier.isStatic(...) == true` | `false` |
| `private String decorate(...) {...}` | Yes | `Modifier.isPrivate(...) == true` | `false` |

A regular class method with a body does **not** become a default method either. `isDefault()` is reserved for **public instance methods that have an implementation and are declared in an interface**, rather than simply meaning "has code". There is no `Modifier.isDefault(...)`; call `Method.isDefault()`.

### Which `Method` API carries which information?

`Method` lets you read:

- `getName()`: method name.
- `getDeclaringClass()`: class/interface **that actually declares** the method.
- `getModifiers()`: flags such as `public`, `private`, `abstract`, `static`, `final`. Check with `java.lang.reflect.Modifier`.
- `isDefault()`: accurately identifies interface default methods.
- `getParameterTypes()`, `getReturnType()`: runtime signature; `getGenericParameterTypes()` and `getGenericReturnType()` serve generic metadata.
- `isBridge()`, `isSynthetic()`: detects certain compiler-generated methods, very useful when scanning full method lists.
- `invoke(receiver, args...)`: executes when compatible receiver, arguments, and access permissions are provided.

`getDeclaringClass().isInterface()` tells you a method **is declared on an interface**, yet is **not sufficient** to conclude it is abstract or default. Interfaces can also have static and private methods.

## 2. Abstract methods: identifying with `Modifier.isAbstract`

An interface can declare an abstract instance method:

~~~java
interface Shape {
    double area(); // public abstract
}
~~~

With `Method m = Shape.class.getDeclaredMethod("area")`:

~~~java
boolean abstractMethod = Modifier.isAbstract(m.getModifiers());
boolean defaultMethod = m.isDefault();
~~~

The two results are `true` and `false` respectively. These are illustrative snippets; import `java.lang.reflect.Method` and `java.lang.reflect.Modifier` when placing them in a standalone program.

An `abstract` class can also declare abstract methods, such as `abstract class Base { abstract void work(); }`. `Modifier.isAbstract` remains the right API to detect it; `isDefault()` continues returning `false` because it is not an interface default method.

**Important:** a `Method` reflecting an abstract method **can still be invoked** using `Method.invoke(...)` if the receiver is an object of a concrete implementing class and dispatch resolves an implementation. `Method.invoke` on an instance method uses dynamic lookup based on the **runtime type of the receiver**. It does not mean the JVM tries to run the body of an abstract method that does not exist.

For example, if `Named` declares `String name()` and `BasicNamed` implements `name()` returning `"An"`, the following call returns `"An"`:

~~~java
Method method = Named.class.getDeclaredMethod("name");
Object result = method.invoke(new BasicNamed());
~~~

The snippet above assumes `Named` and `BasicNamed` are declared as in the full example in the next section. The receiver must be compatible with the interface declaring the method; passing an incompatible object causes `invoke` to throw `IllegalArgumentException`.

## 3. Default methods: detecting with `Method.isDefault()`

Since Java 8, interfaces may declare instance methods with a body using the `default` keyword:

~~~java
interface Loggable {
    default String label() {
        return "item";
    }
}
~~~

`Loggable.class.getDeclaredMethod("label").isDefault()` is `true`. This method is `public`, non-`abstract`, and non-`static`. Implementing classes can **inherit the default implementation**, or **override** it with their own method.

An override written in an implementing class is a **class method**, so `isDefault()` on the `Method` object reflecting that override is `false` even though it replaces the behavior of an interface default method.

Therefore, distinguish:

1. **Where the method is declared:** `method.getDeclaringClass()`.
2. **Whether it is truly a default method:** `method.isDefault()`.
3. **Which implementation an actual call runs:** depends on the receiver and dynamic dispatch of `Method.invoke(...)`.

`isDefault()` describes the **`Method` object**, and does not answer "is this object currently using the default implementation or an override?" with a single boolean.

## 4. Full Java 17+ example: abstract, default, static, and private interface methods

Create the file **`InterfaceMethodReflectionDemo.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

interface Named {
    String name();

    default String greeting() {
        return decorate("Hi " + name());
    }

    private String decorate(String text) {
        return "[" + text + "]";
    }

    static String source() {
        return "interface-static";
    }
}

class BasicNamed implements Named {
    @Override
    public String name() {
        return "An";
    }
}

class CustomNamed implements Named {
    @Override
    public String name() {
        return "Binh";
    }

    @Override
    public String greeting() {
        return "overridden";
    }
}

public class InterfaceMethodReflectionDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Class<?> iface = Named.class;

        Method requirement = iface.getDeclaredMethod("name");
        Method fallback = iface.getDeclaredMethod("greeting");
        Method staticMethod = iface.getDeclaredMethod("source");
        Method helper = iface.getDeclaredMethod("decorate", String.class);

        System.out.println("abstract = "
                + Modifier.isAbstract(requirement.getModifiers())
                + ", default = " + requirement.isDefault());
        System.out.println("default = "
                + fallback.isDefault()
                + ", abstract = " + Modifier.isAbstract(fallback.getModifiers()));
        System.out.println("static = "
                + Modifier.isStatic(staticMethod.getModifiers())
                + ", default = " + staticMethod.isDefault());
        System.out.println("private = "
                + Modifier.isPrivate(helper.getModifiers())
                + ", default = " + helper.isDefault());

        System.out.println("inherited declaring type = "
                + BasicNamed.class.getMethod("greeting")
                        .getDeclaringClass().getSimpleName());

        try {
            BasicNamed.class.getDeclaredMethod("greeting");
        } catch (NoSuchMethodException expected) {
            System.out.println("basic declared default = missing");
        }

        System.out.println("default invoke = "
                + fallback.invoke(new BasicNamed()));
        System.out.println("overridden invoke = "
                + fallback.invoke(new CustomNamed()));
        System.out.println("abstract invoke = "
                + requirement.invoke(new BasicNamed()));
        System.out.println("static invoke = " + staticMethod.invoke(null));

        BasicNamed target = new BasicNamed();
        System.out.println("private accessible before = "
                + helper.canAccess(target));
        System.out.println("private open = " + helper.trySetAccessible());
        System.out.println("private invoke = "
                + helper.invoke(target, "OK"));
    }
}
~~~

Run with Java 17+:

~~~bash
javac --release 17 InterfaceMethodReflectionDemo.java
java InterfaceMethodReflectionDemo
~~~

**Stdout:**

~~~text
abstract = true, default = false
default = true, abstract = false
static = true, default = false
private = true, default = false
inherited declaring type = Named
basic declared default = missing
default invoke = [Hi An]
overridden invoke = overridden
abstract invoke = An
static invoke = interface-static
private accessible before = false
private open = true
private invoke = [OK]
~~~

### Part-by-part analysis

- `name()` is implicitly `public abstract` on the interface. `Modifier.isAbstract(...)` returns `true`; `isDefault()` returns `false`.
- `greeting()` is `default`, so `isDefault()` returns `true`. It calls `decorate(...)`, an internal private helper of the interface.
- `source()` is `static`. It has a body yet is not default; invoke via Reflection with a `null` receiver.
- `decorate(String)` is a `private` instance method of the interface. It has a body, yet is neither public nor default.
- `BasicNamed.class.getMethod("greeting")` finds the public method inherited from interface `Named`; `getDeclaringClass()` is `Named.class`.
- `BasicNamed.class.getDeclaredMethod("greeting")` throws `NoSuchMethodException` because `BasicNamed` does not **declare** this method itself.
- `fallback.invoke(new BasicNamed())` runs the default implementation, combining name `An` into `[Hi An]`.
- `fallback.invoke(new CustomNamed())` runs `CustomNamed`'s **override** and returns `overridden` even though variable `fallback` still represents the interface's original method. This demonstrates dynamic dispatch.
- `requirement.invoke(new BasicNamed())` calls the implementation of the abstract interface method and returns `An`.
- `helper.trySetAccessible()` succeeds in this example because the classes run in the unnamed module on the same class loader. Deep reflection permissions may differ when the Reflection library runs in another module.

**Do not misunderstand:** `getDeclaredMethod(...)` can locate a private interface method, yet finding metadata does not mean it can be invoked immediately. `Method.invoke(...)` still checks access permissions; if `trySetAccessible()` returns `false` in another environment, do not assume subsequent invocation will succeed.

## 5. `getMethod(s)` and `getDeclaredMethod(s)`: similar names, different scopes

| API on `Class<?>` | Search scope | With `BasicNamed.class` and `Named#greeting` |
| --- | --- | --- |
| `getDeclaredMethod(name, types...)` | Methods **declared directly** on that class/interface, regardless of access level | Does not find `greeting()` because `BasicNamed` does not declare it |
| `getMethod(name, types...)` | **Public** methods available on the class/interface, including inherited public methods | Can find `greeting()` with declaring class `Named` |
| `getDeclaredMethods()` | Array of directly declared methods, including private, static, default, and abstract | Does not contain default methods that are only inherited |
| `getMethods()` | Array of public methods of the type, including inherited public methods | Can include available interface default/abstract methods |

Never assume the array order of `getMethods()` or `getDeclaredMethods()` matches the order in source files. Metadata scanners should filter by name, parameter types, declaring class, modifiers, `isBridge()`, or `isSynthetic()` as needed.

### `static` methods on an interface are **not inherited**

`Named.source()` is a valid call via the interface name, whereas `BasicNamed.source()` is invalid in Java source. With Reflection, look up `Named.class.getDeclaredMethod("source")` or `Named.class.getMethod("source")`. Do not expect `BasicNamed.class.getMethod("source")` to find it, because interface static methods are not inherited by implementing classes.

Conversely, a `public` default method can be inherited, so `BasicNamed.class.getMethod("greeting")` is a valid case.

### When inspecting multiple superinterfaces

A subinterface can inherit methods from parent interfaces; `getDeclaredMethods()` on the subinterface still only shows methods it **declares directly**. `getMethods()` helps inspect inherited public methods and the precedence of methods sharing the same signature per API rules. If you need to know the **origin**, use `method.getDeclaringClass()` rather than inferring from the `Class<?>` on which you called `getMethod`.

## 6. Differences between `Method` kinds and `invoke(...)` behavior

`Method.invoke(Object receiver, Object... args)` has two primary scenarios:

1. For **instance methods** (abstract, default, or class implementations), pass a compatible receiver. The JVM performs **dynamic method lookup** on the runtime type of the receiver; an override can be selected.
2. For **static methods**, there is no receiver instance; pass `null`. The call goes to the reflected static method, with no instance-method override mechanism.

This leads to an easy trap:

~~~java
Method m = Named.class.getDeclaredMethod("greeting");
System.out.println(m.isDefault()); // true: method declared on Named
System.out.println(m.invoke(new CustomNamed())); // overridden
~~~

`m.isDefault()` remains `true` because it describes `Named#greeting`; yet calling it on `CustomNamed` runs `CustomNamed`'s override. Do not use `Method.invoke` on an interface's default method to try forcing the JVM to skip an override.

If you genuinely need to call **the interface's default implementation body itself** like `SomeInterface.super.m()`, that is a *special invocation* problem. It differs from the normal dispatch mechanism of `Method.invoke` and is typically performed using the `java.lang.invoke.MethodHandles` API with appropriate `Lookup` privileges. Do not try to work around it by renaming methods or calling `setAccessible(true)` hoping to disable overriding.

### When invoking an abstract method

A `Method` representing an abstract declaration can still be used with a receiver that has a concrete implementation:

~~~java
Method abstractMethod = Named.class.getDeclaredMethod("name");
Object result = abstractMethod.invoke(new BasicNamed()); // "An"
~~~

However, you cannot instantiate an interface or abstract class directly just to call a method. If bytecode/runtime cannot find a valid implementation, execution can hit linking/method-resolution errors; ordinarily compiled consistent Java programs ensure an appropriate implementation exists.

### When invoking a private interface method

Private interface methods are defined to help methods **inside the interface** share logic, not to create a public API. `getDeclaredMethod` can still reflect them. Calling via `invoke` from code outside the interface may require `trySetAccessible()`, and Java module/package openness can restrict enabling access. In normal programs, prefer calling the interface's public/default API rather than relying on private helpers.

## 7. When multiple default methods share the same signature

Java has conflict detection if two interfaces provide default implementations with the same signature and a class has no unambiguous inheritance resolution. For instance, if a class implements `Left` and `Right`, both having `default String choose()`, the class must resolve the conflict, usually by overriding.

Create the file **`DefaultConflictDemo.java`**:

~~~java
import java.lang.reflect.Method;

interface Left {
    default String choose() {
        return "L";
    }
}

interface Right {
    default String choose() {
        return "R";
    }
}

class Choice implements Left, Right {
    @Override
    public String choose() {
        return Left.super.choose() + "+" + Right.super.choose();
    }
}

public class DefaultConflictDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        Method leftMethod = Left.class.getDeclaredMethod("choose");
        Method implementation = Choice.class.getDeclaredMethod("choose");

        System.out.println("Interface method default: "
                + leftMethod.isDefault());
        System.out.println("Class override default: "
                + implementation.isDefault());
        System.out.println("Interface Method.invoke: "
                + leftMethod.invoke(new Choice()));
    }
}
~~~

~~~bash
javac --release 17 DefaultConflictDemo.java
java DefaultConflictDemo
~~~

**Stdout:**

~~~text
Interface method default: true
Class override default: false
Interface Method.invoke: L+R
~~~

Here `Left.super.choose()` and `Right.super.choose()` are **special calls written directly in `Choice`'s source code**. By contrast, `leftMethod.invoke(new Choice())` does not force running `Left#choose`'s body alone: it performs dynamic dispatch to `Choice#choose` and yields `L+R`.

If the override in `Choice` is removed, the source program will not compile due to the default method conflict. Reflection cannot "arbitrarily pick" one implementation to fix this design error after compilation.

## 8. Abstract methods in interfaces, abstract classes, and inheritance

Distinguish the levels:

- **Interface abstract method:** normally implicitly `public abstract`. Concrete implementing classes must provide an implementation if no valid inherited implementation exists.
- **Abstract method in an abstract class:** can have `protected` or package-private access per Java rules; `Modifier.isAbstract(...)` is `true`, and `Method.isDefault()` is always `false`.
- **Concrete method in an abstract class:** even though its enclosing class is `abstract`, the method itself can be non-`abstract` and is not a default method.
- **Default method in an interface:** a public method with a body, recognized by `isDefault()`; implementing classes can inherit or override it.
- **Public concrete method in a class:** is not an interface default method even if the class provides an implementation for a signature declared in an interface.

A superclass method can satisfy a subclass's interface abstract declaration. Therefore, do not infer that "every method declared in an interface must have a corresponding method declared by the implementing class itself". Use `getDeclaringClass()` and the lookup scope of `getMethod/getDeclaredMethod` to answer the question accurately.

In normal Java source, a class's method implementation must meet the interface method's visibility requirement; for example, an implementation for a `public` abstract interface method cannot reduce visibility to `private`.

## 9. Distinguishing `Method.isDefault()` and `Method.getDefaultValue()`

Two easily confused API names with **completely different purposes**.

| API | Purpose | When to use |
| --- | --- | --- |
| `Method.isDefault()` | Checks whether the method is an **interface default method** | Analyzing interface behavior, finding methods with default implementations |
| `Method.getDefaultValue()` | Retrieves the **default value of an annotation element** if declared | Reading `@interface` metadata; can return `null` |

Example of an annotation with a default value:

~~~java
@interface Role {
    String level() default "viewer";
}
~~~

`Role.class.getDeclaredMethod("level").isDefault()` is `false`. This is an annotation element method (abstract under the annotation type contract), **not** an interface default method with a body. `getDefaultValue()` on that `Method` returns `"viewer"`.

Do not infer that `getDefaultValue() != null` implies `isDefault() == true`. For a defaulted annotation element, the opposite is normally **true**: it has a default value in annotation metadata, yet the method has no Java interface default implementation body.

## 10. Parameter types, generics, and varargs when looking up interface methods

Signature rules for `getDeclaredMethod` or `getMethod` do not change just because a method is in an interface:

~~~java
interface Processor {
    void consume(String... values);
    void register(java.util.List<String> values);
}
~~~

Exact lookup (illustrative snippet):

~~~java
Method consume = Processor.class.getDeclaredMethod(
        "consume", String[].class);
Method register = Processor.class.getDeclaredMethod(
        "register", java.util.List.class);
~~~

- `String...` is represented by `String[]` in bytecode/runtime signatures; `consume.isVarArgs()` indicates the declaration is varargs.
- `List<String>` undergoes type erasure to `List.class` during method lookup. Generic metadata can be read via `getGenericParameterTypes()`.
- `int.class` differs from `Integer.class`; lookup does not apply autoboxing or widening to search for an approximate method.
- Compiler-generated methods such as bridge methods may appear in `getDeclaredMethods()`. To analyze source-level declarations, filter and check `isBridge()`/`isSynthetic()` rather than treating every `Method` as a handwritten declaration.

## 11. Access control, Java modules, and common mistakes

Getting a `Method` via Reflection does not guarantee `invoke(...)` can be called. When analyzing:

1. Find the right `Class<?>` declaring the method or look up inherited public methods if that is the goal.
2. Match the name and **runtime signature**; `NoSuchMethodException` means the method was not found within the inspected API's scope.
3. Read `getModifiers()`, `isDefault()`, and `getDeclaringClass()` to classify it.
4. For `invoke(...)`, prepare the receiver instance or `null` for static methods.
5. Check access permissions; `trySetAccessible()` may be needed for private methods. The Java Platform Module System may deny deep access to packages not open to a caller in another module.
6. When the method executes and throws an exception, `Method.invoke` wraps that exception in `InvocationTargetException`; inspect `getCause()` for the root cause from the original method.

| Misconception | Correction |
| --- | --- |
| Seeing a method with code means `default` | Only public non-abstract interface instance methods have `Method.isDefault() == true` |
| Using `Modifier.isAbstract` for every interface method | Interfaces can have abstract, default, static, and private methods |
| `getDeclaredMethods()` on an implementing class must contain inherited default methods | No; that is the class's direct scope—use `getMethods()` for inherited public methods |
| Interface static methods are inherited like default methods | No; look them up on the declaring interface itself |
| `Method.invoke` with a default method always forces running the interface body | No; instance methods follow dynamic dispatch and can run overrides |
| Must call `trySetAccessible()` for all interface methods | No; public methods can be called normally when access requirements are met; use deep access only when needed |
| An annotation element with `default "x"` is a Java interface default method | No; use `getDefaultValue()` for annotation metadata |
| The order of `getDeclaredMethods()` matches source-code order | Not guaranteed; actively filter/sort if stable display order is wanted |

### Note on dynamic proxies

Java dynamic proxies have their own mechanism: calls to interface methods on a proxy are routed to `InvocationHandler#invoke`. Since Java 16, the `InvocationHandler.invokeDefault(proxy, method, args...)` API can directly invoke a proxy interface's default method under suitable conditions; it differs from regular `Method.invoke(...)`. Only use this proxy mechanism when actually building a `Proxy`, not as a general way to invoke default methods on arbitrary objects.

## 12. Self-check questions

**Question 1.** `interface I { void run(); }`. Does `I.class.getDeclaredMethod("run").isDefault()` return `true`?

**Answer:** No. `run()` is an abstract instance method, `Modifier.isAbstract(...) == true` and `isDefault() == false`.

**Question 2.** `interface I { default void run() {} }`, class `C implements I` without overriding. Does `C.class.getDeclaredMethod("run")` find the method?

**Answer:** No. `run()` is declared by `I`. `C.class.getMethod("run")` is what finds the inherited public method.

**Question 3.** `I.class.getDeclaredMethod("run")` for a default method; the receiver is an object of class `C` overriding `run()`. Which one does `Method.invoke(...)` execute?

**Answer:** `C`'s override via dynamic dispatch. `Method.isDefault()` on the method reflected from `I` remains `true`.

**Question 4.** Why can't static method `I.make()` be found via `C.class.getMethod("make")`, even though `C implements I`?

**Answer:** Static methods of an interface are not inherited by implementing classes. Look it up on `I.class` and use a `null` receiver on `invoke`.

**Question 5.** An interface has `private String helper()`. What is `helper.isDefault()`?

**Answer:** `false`. A private method can have a body yet is not a public interface default method; accessing it from another caller may require enabling valid Reflection access.

**Question 6.** `@interface Role { String level() default "viewer"; }`. Why do `isDefault()` and `getDefaultValue()` differ?

**Answer:** `isDefault()` tests for an **interface default method with a body**; `getDefaultValue()` returns the `"viewer"` metadata of an annotation element. They are two different "default" concepts.

**Question 7.** How do you tell whether a method obtained from `Class#getMethods()` is declared on an interface?

**Answer:** Check `method.getDeclaringClass().isInterface()`. Then inspect `isDefault()`, `Modifier.isAbstract(...)`, `Modifier.isStatic(...)`; being declared on an interface alone does not determine the method kind.

## Standard documentation to verify against

- [JDK 21 — java.lang.reflect.Method](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): `isDefault()`, `invoke(...)`, `getDefaultValue()`, and metadata.
- [JDK 21 — java.lang.Class](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getMethod(s)`, `getDeclaredMethod(s)`, and inheritance scope.
- [JDK 21 — InvocationHandler](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html): `invokeDefault(...)` for dynamic proxies.

**Takeaway:** `Modifier.isAbstract(method.getModifiers())` checks whether a method is abstract; `method.isDefault()` checks whether a method is a **public default instance method of an interface**. `getDeclaringClass()` tells where a method is declared; `getMethod` and `getDeclaredMethod` have different scopes. Finally, `Method.invoke` on instance methods obeys dynamic dispatch, so a Method reflected from an interface **does not guarantee** running the interface's default body when the receiver overrides that method.