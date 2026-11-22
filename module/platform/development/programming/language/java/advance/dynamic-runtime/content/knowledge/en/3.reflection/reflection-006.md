# 3.6 Overridden Method Dispatch When Invoking a Superclass `Method` on a Subclass Object

In Java Reflection, obtaining a `java.lang.reflect.Method` object from a **superclass** does not mean the invocation will execute the **superclass method body**. If the method is an **overridable instance method** and the actual target object is a subclass, `Method.invoke(...)` performs **dynamic method lookup**: the JVM selects the appropriate implementation based on the **runtime type of the target object**. This is a core point when writing frameworks, dynamic method invokers, testing tools, mappers, or plugin systems.

This lesson focuses on the scenario where you already have a `Method` representing the superclass declaration, and then use it to invoke on a subclass instance. We will go from the dispatch mechanism to runnable examples, exceptions such as `static`/`private`/`final`, how to actually invoke `super`, and how to diagnose errors.

## 1. Two Different Questions: Which `Method` to Find, and Which Implementation to Execute?

Suppose:

~~~java
class Parent {
    public String say() { return "parent"; }
}
class Child extends Parent {
    @Override
    public String say() { return "child"; }
}
~~~

The statements:

~~~java
Method method = Parent.class.getMethod("say");
Object result = method.invoke(new Child());
~~~

have **two phases**:

1. **Metadata lookup:** `Parent.class.getMethod("say")` finds the public method named `say` with no parameters, as viewed from `Parent`. `method.getDeclaringClass()` is `Parent.class`.
2. **Execution on the receiver:** `method.invoke(new Child())` receives an object with runtime type `Child`. Because `Child.say()` overrides `Parent.say()`, Java dispatches to `Child.say()` and returns `"child"`.

Therefore, it is necessary to distinguish:

| Information | Result in Example | What Does It Tell Us? |
| --- | --- | --- |
| `method.getDeclaringClass()` | `Parent.class` | Where the method selected for reflection is declared |
| `method.getName()` | `"say"` | The method name of the metadata |
| `method.getParameterTypes()` | Empty array | The parameter type list of the declaration |
| `receiver.getClass()` | `Child.class` | The actual runtime type of the object receiving the invocation |
| `method.invoke(receiver)` | `"child"` | The result of the implementation dispatched at invocation time |

**Rule:** `Method` reflects **the declaration that was found**, whereas a virtual call reflects **the implementation chosen at runtime**. Do not use `getDeclaringClass()` to conclude which method body ran.

The Java SE 17 API documentation for `Method.invoke` states explicitly: for an instance method, dynamic method lookup can select an overriding method based on the runtime type of the target (per JLS `15.12.4.4`). That is behavior specified by Java, not a coincidental HotSpot quirk.

## 2. Standard Example: The Same Superclass `Method` Invokes Multiple Implementations

Save the complete program as **`ReflectionDispatchDemo.java`**:

~~~java
import java.lang.reflect.Method;

public class ReflectionDispatchDemo {
    static class Parent {
        public String name() { return "Parent.name"; }
        public String role(String prefix) { return prefix + ":Parent.role"; }
    }

    static class Child extends Parent {
        @Override public String name() { return "Child.name"; }
        @Override public String role(String prefix) {
            return prefix + ":Child.role";
        }
    }

    static class GrandChild extends Child {
        @Override public String name() { return "GrandChild.name"; }
    }

    public static void main(String[] args) throws Exception {
        Parent target = new Child();
        Method nameFromParent = Parent.class.getMethod("name");
        Method roleFromParent = Parent.class.getMethod("role", String.class);

        System.out.println(nameFromParent.getDeclaringClass().getSimpleName());
        System.out.println(target.getClass().getSimpleName());
        System.out.println(nameFromParent.invoke(target));
        System.out.println(nameFromParent.invoke(new Parent()));
        System.out.println(nameFromParent.invoke(new GrandChild()));
        System.out.println(roleFromParent.invoke(target, "Hello"));
        System.out.println(((Parent) target).name());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~sh
javac ReflectionDispatchDemo.java
java ReflectionDispatchDemo
~~~

**Exact stdout:**

~~~text
Parent
Child
Child.name
Parent.name
GrandChild.name
Hello:Child.role
Child.name
~~~

Explanation of each result:

- `getDeclaringClass().getSimpleName()` prints `Parent`: `nameFromParent` is indeed metadata obtained from the superclass; it is not replaced with `Child.class.getMethod(...)`.
- `target.getClass().getSimpleName()` prints `Child`: the variable `target` is declared with type `Parent` but references an actual `Child` object.
- `nameFromParent.invoke(target)` prints `Child.name`: the reflection call dispatches the override.
- With the same `Method` object, when the receiver is `new Parent()`, it runs `Parent.name`; when the receiver is `new GrandChild()`, it runs `GrandChild.name`. There is no need to re-fetch `Method` for each subclass.
- `roleFromParent.invoke(target, "Hello")` prints `Hello:Child.role`: dynamic dispatch still applies to methods with parameters if the signature is actually overridden.
- Casting `((Parent) target)` does not change the runtime type, so `((Parent) target).name()` still prints `Child.name`.

You can visualize the process as:

~~~text
Parent.class.getMethod("name")  ->  Method declared by Parent
                                            |
                                            v
                                 Method.invoke(receiver)
                                            |
                         +------------------+------------------+
                         |                  |                  |
                  receiver: Parent   receiver: Child   receiver: GrandChild
                         |                  |                  |
                         v                  v                  v
                   Parent.name()      Child.name()      GrandChild.name()
~~~

Here each branch depends on the **actual receiver**, not on which class the `getMethod` statement was called on.

## 3. Why Does the JVM Dispatch This Way?

For a validly overridden instance method, a normal Java call like `parentRef.name()` uses the virtual dispatch mechanism. Reflection does not intentionally "lock" `Method` to the declaring class's body. `Method.invoke` uses a dynamic lookup mechanism corresponding to the Java specification.

Three mental steps are enough to explain most practical cases:

1. **Select the method signature:** the name and parameter types are determined when obtaining the `Method`, for example `getMethod("role", String.class)`. Reflection does not automatically pick a new overload based on the runtime class of the arguments.
2. **Verify the target and access rights:** an instance method requires a non-`null` receiver belonging to the class/interface declaring the method or a corresponding subtype/implementing type; access rights must also be valid.
3. **Dispatch the override:** if the runtime receiver has an implementation that overrides that exact instance method, invoke the most specific matching implementation. If there is no override, invoke the inherited implementation.

For example, if `Child` does not override `role(String)`, then calling `Parent.class.getMethod("role", String.class).invoke(new Child(), "...")` will use the `Parent.role` body. Conversely, as long as there is a valid override, the runtime selects the new body.

This does not require the method to appear directly on a variable of the subclass type. Whether the receiver is stored in an `Object`, `Parent`, or interface variable, the runtime type remains unchanged. The JVM must also respect multi-level overriding (e.g., `GrandChild`) and the corresponding inheritance/interface relationships.

### `abstract` Superclasses and Interfaces Also Participate in Dispatch

When a `Method` represents an abstract method of a superclass or an interface, it can invoke the implementation of a concrete object. Complete program **`InterfaceDispatchDemo.java`**:

~~~java
import java.lang.reflect.Method;

public class InterfaceDispatchDemo {
    interface Reporter { String report(); }

    static class ReporterImpl implements Reporter {
        @Override public String report() { return "implementation"; }
    }

    abstract static class BaseTask {
        public abstract String execute();
    }

    static class Work extends BaseTask {
        @Override public String execute() { return "concrete"; }
    }

    public static void main(String[] args) throws Exception {
        Method viaInterface = Reporter.class.getMethod("report");
        Method viaAbstractBase = BaseTask.class.getMethod("execute");
        System.out.println(viaInterface.invoke(new ReporterImpl()));
        System.out.println(viaAbstractBase.invoke(new Work()));
    }
}
~~~

~~~sh
javac InterfaceDispatchDemo.java
java InterfaceDispatchDemo
~~~

~~~text
implementation
concrete
~~~

In both `invoke` calls, the declaring type has no concrete body to run; the receiver provides the concrete implementation. The same principle also applies when an interface has a default method: an overriding implementation in a class, if present, will be selected according to dispatch rules. Do not assume that reflection always runs the interface's default body.

## 4. Important Exceptions: `static`, `private`, `final`, and Overloads

Not every method with the same name in a superclass and subclass has an **override** relationship. There are cases where the names are identical, yet Java **does not perform virtual override dispatch**.

| Case | Is It an Override? | When Invoking a Superclass `Method` on a Subclass Instance |
| --- | --- | --- |
| Public/protected instance method validly overridden by subclass | Yes | Runs the subclass implementation |
| Inherited instance method, not overridden by subclass | No new override | Runs the implementation inherited from the superclass |
| `abstract` method of superclass, with implementation in subclass | Has a concrete implementation | Runs the subclass implementation |
| Interface method, object implements/overrides | According to interface dispatch rules | Runs the implementation applicable to the object |
| `static` method with the same name in superclass/subclass | **No**: this is method hiding | Runs the static method represented by `Method`; receiver is ignored |
| `private` method in superclass, method with the same name in subclass | **No**: superclass private is not overridden | With valid access rights, runs the superclass's private method |
| `final` instance method in superclass | Cannot be validly overridden | Runs the superclass body |
| Superclass has `render(Object)`, subclass only adds `render(String)` | **No**: this is an overload | The `Method` for `render(Object)` still invokes the `render(Object)` implementation |

To verify all of these cases in a standalone program, save **`ReflectionRulesDemo.java`**:

~~~java
import java.lang.reflect.Method;

public class ReflectionRulesDemo {
    static class Base {
        public static String kind() { return "Base.static"; }
        private String secret() { return "Base.private"; }
        public final String id() { return "Base.final"; }
        public String render(Object value) { return "Base(Object)"; }
    }

    static class Derived extends Base {
        public static String kind() { return "Derived.static"; }
        public String secret() { return "Derived.public"; }
        public String render(String value) { return "Derived(String)"; }
    }

    public static void main(String[] args) throws Exception {
        Derived target = new Derived();

        System.out.println(Base.class.getMethod("kind").invoke(target));
        System.out.println(Derived.class.getMethod("kind").invoke(null));

        Method privateOfBase = Base.class.getDeclaredMethod("secret");
        System.out.println(privateOfBase.invoke(target));
        System.out.println(Derived.class.getMethod("secret").invoke(target));

        System.out.println(Base.class.getMethod("id").invoke(target));
        System.out.println(
            Base.class.getMethod("render", Object.class).invoke(target, "A")
        );
        System.out.println(
            Derived.class.getMethod("render", String.class).invoke(target, "A")
        );
    }
}
~~~

~~~sh
javac ReflectionRulesDemo.java
java ReflectionRulesDemo
~~~

~~~text
Base.static
Derived.static
Base.private
Derived.public
Base.final
Base(Object)
Derived(String)
~~~

**Clear explanation of each exception:**

- **`static`:** `Base.kind()` and `Derived.kind()` are two static methods with a *hiding* relationship, not overriding. With `Base.class.getMethod("kind")`, the result is always `Base.static`. The receiver argument in `invoke` is ignored; here `target` is passed only to emphasize that fact. Calling `Derived.class.getMethod("kind").invoke(null)` is what yields `Derived.static`.
- **`private`:** `Base.secret()` is not inherited by the subclass for overriding. `Derived.secret()` is a separate method. `Base.class.getDeclaredMethod("secret").invoke(target)` executes the `Base.private` body. The sample program can access the private method because the nested classes belong to the same **nest** as the enclosing class in Java 17; another caller may receive `IllegalAccessException`, while using `setAccessible` is subject to module restrictions.
- **`final`:** `Base.id()` cannot be overridden, so invoking it on `Derived` still produces `Base.final`. If you try to declare `@Override public String id()` in `Derived`, the program will not compile.
- **Overload:** `Base.render(Object)` and `Derived.render(String)` have different parameter types, and therefore **do not override**. Even though `"A"` is passed as a `String`, the `Method` selected via `getMethod("render", Object.class)` will run `Base.render(Object)`. Reflection does not switch to the `String` overload just because the runtime argument matches it better.

In real reflection code, confusing an **overload with an override** is especially common when designing dispatchers. You must check both the name and the `Class<?>` list of parameter types, not just look at the method name.

### Overriding with Generics and Covariant Return Types

At the Java source level, a method can override with a **covariant** (more specific) return type, and generic type erasure can cause the compiler to generate a **bridge method** to preserve correct polymorphic behavior in the JVM. When iterating over `getDeclaredMethods()`, you sometimes see extra methods that were not written directly in source.

- `Method.isBridge()` tells you whether a method is a bridge method; `isSynthetic()` is another piece of metadata that may appear.
- The presence of bridge methods **does not break** the dynamic dispatch contract of `Method.invoke` on instance methods.
- When building API-listing tools, consider intentionally filtering or handling bridge methods; do not rely on the number of visible methods to infer the number of overloads in source.
- Only the signature (including parameters and Java's overriding rules) determines an override relationship; do not use the method name string alone.

## 5. How Do `getMethod`, `getDeclaredMethod`, and `getDeclaringClass` Affect This?

Metadata lookup APIs do not change the nature of dispatch when calling `invoke` on a receiver:

| How `Method` Is Obtained | Lookup Scope | Implications to Note |
| --- | --- | --- |
| `Parent.class.getMethod("name")` | `public` methods visible from `Parent`, including inherited public methods | For a public instance method, still dispatches to the override on `Child` |
| `Parent.class.getDeclaredMethod("name")` | Only methods declared **directly** in `Parent`, regardless of access modifier | Obtains the superclass's own metadata, but does not force runtime to run the superclass body |
| `Child.class.getMethod("name")` | Public methods visible from `Child` | If `Child` overrides a public method, the metadata is normally declared by `Child` |
| `Child.class.getDeclaredMethod("name")` | Only methods declared in `Child` | Throws `NoSuchMethodException` if `Child` only inherits the method without redeclaring it |
| `method.getDeclaringClass()` | The class/interface that actually declares that metadata | Indicates the declaration source of the `Method`, not which body runs on every receiver |

Example when the subclass has an override:

~~~java
Method parentMethod = Parent.class.getMethod("name");
Method childMethod = Child.class.getMethod("name");

System.out.println(parentMethod.getDeclaringClass() == Parent.class); // true
System.out.println(childMethod.getDeclaringClass() == Child.class);   // true
~~~

This snippet **illustrates** the context of the two nested types `Parent`/`Child` in `ReflectionDispatchDemo`, not a standalone program.

**Access checks are not dispatch.** If a method is non-public, reflection may refuse to invoke it with `IllegalAccessException` even if the receiver matches. `trySetAccessible()`/`setAccessible(true)` can alter access checking within what the Java module system allows, but it **does not turn a virtual call into a `super` call**. From Java 9+, strong encapsulation can block reflective access to members of modules that are not appropriately opened; you should not treat `setAccessible(true)` as a guaranteed way to bypass all barriers.

## 6. What If You Want to Run the Superclass Body Directly?

Suppose `Child.say()` overrides `Parent.say()`. The result of:

~~~java
Method fromParent = Parent.class.getMethod("say");
fromParent.invoke(new Child());
~~~

is still `Child.say()`. **`Method.invoke` has no "bypass override" option**. Even if you obtain the method with `getDeclaredMethod`, cast the receiver to `Parent`, or call `setAccessible(true)`, that still will not force dispatch back to the superclass body.

In subclass code, the natural way to call the superclass implementation is **`super.say()`**. If you are working at the runtime level with method handles, Java supports special invocation semantics via `MethodHandles.Lookup.findSpecial(...)` with a lookup that has appropriate access rights. This is a **different** mechanism from `Method.invoke`.

Standalone example **`SuperInvocationDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class SuperInvocationDemo {
    static class Parent {
        public String say() { return "parent"; }
    }

    static class Child extends Parent {
        @Override public String say() { return "child"; }

        public String callSuper() { return super.say(); }

        public String callParentHandle() throws Throwable {
            MethodHandle handle = MethodHandles.lookup().findSpecial(
                Parent.class, "say", MethodType.methodType(String.class),
                Child.class
            );
            return (String) handle.invokeExact(this);
        }
    }

    public static void main(String[] args) throws Throwable {
        Child child = new Child();
        Method fromParent = Parent.class.getMethod("say");

        System.out.println(fromParent.invoke(child));
        System.out.println(child.callSuper());
        System.out.println(child.callParentHandle());
    }
}
~~~

~~~sh
javac SuperInvocationDemo.java
java SuperInvocationDemo
~~~

~~~text
child
parent
parent
~~~

In `Child.callParentHandle()`, `MethodHandles.lookup()` is created **right inside the subclass context**, with appropriate privileges for `findSpecial(Parent.class, ..., Child.class)`. The method handle models a special invocation from `Child`, so it can run `Parent.say()` despite the override in `Child`. You cannot arbitrarily copy that `findSpecial` snippet into any external class: `Lookup`, `specialCaller`, and access checks still apply, and may throw `IllegalAccessException`.

Quick comparison:

| Call | Which Method Runs? |
| --- | --- |
| `new Child().say()` | `Child.say()` |
| `((Parent) new Child()).say()` | `Child.say()` |
| `Parent.class.getMethod("say").invoke(new Child())` | `Child.say()` |
| `super.say()` inside `Child` | `Parent.say()` |
| `findSpecial(...)` with an appropriate lookup as in the example | `Parent.say()` |

For interface `default` methods, the syntax `InterfaceName.super.method()` or an appropriate special invocation mechanism also has its own access rules; do not assume that getting the interface's `Method` and calling `invoke` will bypass an override.

## 7. Errors During Reflective Method Invocation and How to Distinguish Them

`Method.invoke(Object obj, Object... args)` has a contract regarding receivers, arguments, access, and exceptions. These errors are often confused with dispatch issues:

- **`IllegalArgumentException`:** the receiver is not an instance of the declaring class/interface or a compatible subtype, the number of arguments is wrong, or an argument type cannot be converted appropriately; reflection does not "guess" another overload.
- **`NullPointerException`:** `null` receiver when invoking an instance method. For `static`, the receiver can be `null`.
- **`IllegalAccessException`:** the caller lacks sufficient privileges to access the method when reflective access checks are enforced.
- **`InvocationTargetException`:** code inside the invoked method threw an exception; call **`getCause()`** to get the original cause from the invoked method.
- **`NoSuchMethodException`:** error at the `getMethod` or `getDeclaredMethod` step if no matching method exists, before reaching the dispatch step.
- **`ExceptionInInitializerError`:** class initialization triggered at invocation time may fail, especially with static methods.

Standalone example **`InvocationFailureDemo.java`**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class InvocationFailureDemo {
    static class Parent {
        public String speak() { return "ok"; }
        public void explode() { throw new IllegalStateException("broken"); }
    }

    static class Child extends Parent {}

    public static void main(String[] args) throws Exception {
        Method speak = Parent.class.getMethod("speak");

        try {
            speak.invoke(new Object());
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }

        try {
            speak.invoke(null);
        } catch (NullPointerException ex) {
            System.out.println(ex.getClass().getSimpleName());
        }

        Method explode = Parent.class.getMethod("explode");
        try {
            explode.invoke(new Child());
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println(
                cause.getClass().getSimpleName() + ": " + cause.getMessage()
            );
        }
    }
}
~~~

~~~sh
javac InvocationFailureDemo.java
java InvocationFailureDemo
~~~

~~~text
IllegalArgumentException
NullPointerException
IllegalStateException: broken
~~~

In the final part, `explode` is an instance method inherited from `Parent`; its body runs and throws `IllegalStateException`. Reflection wraps it in `InvocationTargetException`. If the method is overridden to throw a different error, you should still investigate the cause via `getCause()` and the original exception's stack trace.

### Note on the Return Value

`invoke(...)` returns `Object`: primitive values are boxed (for example `int` to `Integer`), while a `void` method returns `null`. For overloads or callers requiring a specific type, you need to cast/check the result value appropriately. Do not confuse the return type of `Method.invoke` in the API (always `Object`) with the actual return type of the reflected method (`method.getReturnType()`).

## 8. Common Misconceptions That Easily Break Reflection Programs

**Misconception 1: "Getting the `Method` from the superclass guarantees running the superclass's code."** False for overridden instance methods: dispatch is based on the runtime receiver.

**Misconception 2: "`getDeclaredMethod` helps invoke the superclass implementation."** False. It only restricts where metadata is searched, and does not turn virtual dispatch into a special call.

**Misconception 3: "Casting the object to the superclass will force the superclass method to run."** False. `((Parent) child).say()` still calls the override if the method is virtual; casting does not change the runtime class.

**Misconception 4: "A method with the same name in the subclass is an override."** False. You must check parameter types, override rules, `static`, `private`, and `final`. `render(String)` does not override `render(Object)`.

**Misconception 5: "`Method.invoke` automatically picks the best overload from the argument values."** False. You select the method via `name + parameterTypes` metadata beforehand; `invoke` performs compatibility checks/conversions against the already-selected method.

**Misconception 6: "`Method.getDeclaringClass()` indicates which class executed the method just invoked."** False. It indicates the declaring class of the metadata; the executing class may be a subclass.

**Misconception 7: "`setAccessible(true)` can bypass overriding."** False. It relates to access checks and has module limits; it does not control dispatch.

**Misconception 8: "A superclass's static method will be overridden by a subclass's static method."** False. That is hiding; `Method.invoke` for static methods ignores the receiver.

**Misconception 9: "If `invoke` throws `InvocationTargetException`, the bug is in the Reflection API."** Not necessarily. Usually you need to inspect `getCause()` because the invoked method's code threw an exception.

**Misconception 10: "You can freely call `findSpecial` from anywhere to run the superclass."** False. `Lookup` and `specialCaller` have strict constraints, different from ordinary reflection privileges.

## 9. How to Inspect a Dispatch Case in Practice

When you encounter the symptom "got the superclass's `Method` but invoking it produces subclass behavior", record the following information:

1. **Selected metadata:** `method.getDeclaringClass()`, `method.getName()`, `method.getParameterTypes()`, `method.getReturnType()`, and `method.getModifiers()`.
2. **Target object:** `target.getClass()` (after checking `target != null` for instance methods). Do not rely on the declared type of the variable holding the receiver.
3. **Override relationship:** for the selected method signature, find the matching implementation on the runtime class; distinguish a true `@Override` from an overload, hiding, or a separate private method.
4. **Reflection scope:** `getMethod` only retrieves visible public methods, `getDeclaredMethod` only retrieves directly declared methods; evaluate access/modules separately.
5. **Bridge or generics:** if the `getDeclaredMethods()` list looks unusual, check `isBridge()` and `isSynthetic()`.
6. **Result and errors:** compare runtime output; if `InvocationTargetException` is thrown, follow `getCause()` and the stack trace of the invoked code.
7. **If you truly want the superclass implementation:** use `super.method()` in an appropriate Java location or `MethodHandles.Lookup.findSpecial` with exact access privileges.

You can use the metadata inspection snippet below within a program that already has `method`/`target` objects (this is an **illustrative snippet**, not standalone):

~~~java
System.out.println("declaring = " + method.getDeclaringClass().getName());
System.out.println("receiver  = " + target.getClass().getName());
System.out.println("name      = " + method.getName());
System.out.println("parameters= " +
    java.util.Arrays.toString(method.getParameterTypes()));
System.out.println("static    = " +
    java.lang.reflect.Modifier.isStatic(method.getModifiers()));
System.out.println("bridge    = " + method.isBridge());
~~~

These log lines identify the **selected method** and **which override the target can dispatch to**. They are not a direct measurement of the entire call graph; if there are multiple layers of delegation, continue using a debugger/stack trace or instrumentation to confirm the body's behavior.

## 10. Self-Practice

**Exercise 1.** `Base.run()` is a public instance method; `Sub.run()` overrides it. `Method m = Base.class.getMethod("run"); m.invoke(new Sub());` runs which method?

**Answer:** `Sub.run()`, due to dynamic dispatch on the `Sub` receiver. `m.getDeclaringClass()` is still `Base.class`.

**Exercise 2.** `Sub` does not override `Base.run()` and only adds `run(String)`. What does `Base.class.getMethod("run").invoke(new Sub())` run?

**Answer:** `Base.run()` because the `run(String)` method is an overload with a different signature.

**Exercise 3.** `Base.version()` and `Sub.version()` are both `static`. Does getting `Base.class.getMethod("version")` and calling `invoke(new Sub())` invoke `Sub.version()`?

**Answer:** No; static methods do not override. The runtime ignores the receiver argument and uses the static method that `Method` represents in `Base`.

**Exercise 4.** Why is calling `Parent.class.getDeclaredMethod("say").invoke(child)` not equivalent to `super.say()`?

**Answer:** `getDeclaredMethod` only finds the declaration in `Parent`; `invoke` still uses dynamic dispatch for overridable instance methods. `super.say()` is a special invocation from the subclass context.

**Exercise 5.** `Method m` represents an `abstract` method in the superclass. Can `m.invoke(instanceLopCon)` run?

**Answer:** Yes, if the valid receiver has a concrete implementation and satisfies access checks. Reflection invokes the matching implementation at runtime.

**Exercise 6.** Why can a `Method.invoke` call throw `InvocationTargetException` while the application method actually throws `IllegalStateException`?

**Answer:** Reflection wraps exceptions thrown inside the target method; inspect `InvocationTargetException.getCause()` to get the original error.

## 11. References

- Java SE 17, `java.lang.reflect.Method.invoke` — description of dynamic method lookup, override dispatch by runtime type, parameters, and exceptions: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...)
- Java SE 17, `Class.getMethod` / `Class.getDeclaredMethod`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java Language Specification 17, `15.12.4.4` — Locate Method to Invoke: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.4
- Java SE 17, `MethodHandles.Lookup.findSpecial` — special invocation and access checks: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#findSpecial(java.lang.Class,java.lang.String,java.lang.invoke.MethodType,java.lang.Class)
- Java SE 17, `Method.isBridge`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#isBridge()

**Academic Conclusion:** In `Method.invoke`, **the declaration of `Method`** determines the method/signature being called; for an overridden instance method, **the runtime type of the receiver** determines the executed body. To invoke the superclass body despite an override requires a properly privileged special invocation, typically `super.method()` or `Lookup.findSpecial(...)`.