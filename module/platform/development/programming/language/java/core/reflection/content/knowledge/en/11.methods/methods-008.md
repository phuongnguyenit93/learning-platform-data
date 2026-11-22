# Distinguishing virtual calls from intending to invoke only a super implementation in Java Reflection

## 1. Problem: already obtained the superclass Method, why does subclass code still run?

A Reflection user might obtain a `Method` object declared on a superclass and then invoke it on an instance of a subclass:

~~~java
Method method = Parent.class.getDeclaredMethod("message");
Object result = method.invoke(new Child());
~~~

If `Child` **overrides** `message()`, the result comes from `Child`'s implementation, **not** the implementation in `Parent`. This is the expected behavior of `Method.invoke` for instance methods using virtual dispatch.

What must be distinguished:

- **Where was the Method found?** `Parent.class.getDeclaredMethod(...)` returns metadata for the method declared in `Parent`.
- **On which object is the Method invoked?** The object passed to `invoke(receiver)` has runtime type `Child`.
- **Which method body does the JVM choose?** For an overridable instance method, `Method.invoke` uses **dynamic method lookup**; the subclass override is selected.
- **How to intentionally call the `super` implementation?** A `super.message()` statement inside subclass code, or `MethodHandles.Lookup.findSpecial(...)` / `unreflectSpecial(...)` in a caller context with sufficient privileges, expresses intent analogous to `invokespecial`.

This lesson belongs to the **Method group in Java Reflection**, focusing on dispatch and how to invoke the right method body rather than just retrieving method names or annotations.

## 2. Foundational model: compile-time type vs. runtime type

Example:

~~~java
class Parent {
    public String message() {
        return "Parent.message";
    }
}

class Child extends Parent {
    @Override
    public String message() {
        return "Child.message";
    }

    public String callSuper() {
        return super.message();
    }
}
~~~

With:

~~~java
Parent p = new Child();
System.out.println(p.message());       // Child.message
System.out.println(((Parent) p).message()); // Child.message
System.out.println(((Child) p).callSuper()); // Parent.message
~~~

**Why?** A declared type `Parent` on an expression and the `(Parent)` cast only govern compile-time checking/call resolution; the actual object is still `Child`. For a virtual call, the JVM selects the appropriate override according to the actual class of the receiver. Casting does not turn the object into a new `Parent` instance.

Conversely, `super.message()` is a special call appearing inside **subclass code**. Java uses superclass member-call semantics in that context, bypassing any override present in the subclass. `super` is not an object value that can be passed to `Method.invoke`; you cannot write `method.invoke(super)` in ordinary code because `super` is not a standalone variable expression like `this`.

### Path illustration

~~~text
Parent p = new Child()
        |
        +-- p.message()
        |       |
        |       +-- virtual dispatch by actual receiver: Child.message()
        |
        +-- Parent.class.getMethod("message").invoke(p)
        |       |
        |       +-- Method describes Parent.message
        |       +-- Method.invoke still dispatches: Child.message()
        |
        +-- ((Child) p).callSuper()
                |
                +-- code inside Child calls super.message(): Parent.message()
~~~

An important note on the word "virtual": in Java, overridable instance methods normally use dynamic dispatch. Do not apply that rule mechanically to all methods such as `static`, `private`, constructors, or non-overridable methods.

## 3. Method lookup APIs do NOT decide which body runs

| How Method is obtained | What method metadata may represent | When `invoke(child)` with a valid override |
| --- | --- | --- |
| `Parent.class.getMethod("message")` | Public method of `Parent` | Runs `Child.message` |
| `Parent.class.getDeclaredMethod("message")` | Method declared directly in `Parent` | Runs `Child.message` |
| `Child.class.getMethod("message")` | Public method visible when looking up from `Child` | Runs `Child.message` |
| `Child.class.getDeclaredMethod("message")` | Method declared directly in `Child` if present | Runs `Child.message` |
| `Parent.class.getSuperclass()` | Returns `Parent`'s superclass, not a method call | Has no effect on dispatch |

Technical points:

1. `getMethod` looks up `public` methods according to `Class` rules, which may include inherited methods.
2. `getDeclaredMethod` searches for declarations on the **queried class/interface itself**, regardless of `public`, `protected`, package-private, or `private`; it does not automatically look in superclasses.
3. `Method.getDeclaringClass()` tells **which class declared the Method**, not which override will be selected at runtime.
4. Pass the exact `Class<?>` list of parameters to `getMethod/getDeclaredMethod` when the method has parameters or overloads.
5. Using `setAccessible(true)` or `trySetAccessible()` (when allowed) changes **access control checks**, not virtual dispatch. Opening access for a Method declared in Parent does not force the JVM to select Parent's body.

The Java SE 17 documentation for `Method.invoke` confirms that, for instance methods, the JVM uses dynamic method lookup; overriding based on the runtime type of the target object still takes place.

### Two different goals

- **Goal A — invoke polymorphic behavior on the current receiver:** use `Method.invoke(receiver, args...)` or a method handle with virtual semantics.
- **Goal B — invoke the superclass implementation specifically:** requires a call site with privileges to perform `super`/`invokespecial`; that cannot be achieved merely by changing the `Method` object or casting the receiver.

## 4. Standalone Java 17+ example: seeing all outcomes in one run

Place all the following code in **`VirtualDispatchDemo.java`**. The program uses nested classes for easy compilation, while performing `findSpecial` from **inside `Child`**, where the lookup is created with appropriate access privileges.

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;

public class VirtualDispatchDemo {
    public static class Parent {
        public String message() { return "Parent.message"; }
        public static String category() { return "Parent.category"; }
        public final String fixed() { return "Parent.fixed"; }
    }

    public static class Child extends Parent {
        @Override
        public String message() { return "Child.message"; }

        public static String category() { return "Child.category"; }

        public String directSuper() { return super.message(); }

        public String specialSuper() throws Throwable {
            MethodHandle handle = MethodHandles.lookup().findSpecial(
                    Parent.class, "message",
                    MethodType.methodType(String.class),
                    Child.class);
            return (String) handle.invoke(this);
        }
    }

    public static void main(String[] args) throws Throwable {
        Child child = new Child();
        Parent parentRef = child;
        Method fromParent = Parent.class.getMethod("message");
        Method fromChild = Child.class.getDeclaredMethod("message");
        Method staticParent = Parent.class.getMethod("category");
        Method finalParent = Parent.class.getMethod("fixed");

        System.out.println("normal: " + parentRef.message());
        System.out.println("declared by: "
                + fromParent.getDeclaringClass().getSimpleName());
        System.out.println("parent Method.invoke: "
                + fromParent.invoke(child));
        System.out.println("child Method.invoke: "
                + fromChild.invoke(child));
        System.out.println("super in Child: " + child.directSuper());
        System.out.println("findSpecial from Child: "
                + child.specialSuper());

        MethodHandle virtual = MethodHandles.lookup().findVirtual(
                Parent.class, "message",
                MethodType.methodType(String.class));
        System.out.println("findVirtual: " + (String) virtual.invoke(child));
        System.out.println("static Parent method: "
                + staticParent.invoke(null));
        System.out.println("final Parent method: "
                + finalParent.invoke(child));
    }
}
~~~

Compile and run in the file's directory with JDK 17 or later:

~~~bash
javac --release 17 VirtualDispatchDemo.java
java VirtualDispatchDemo
~~~

**Exact stdout of the example compiled and run with OpenJDK 21 using `--release 17`:**

~~~text
normal: Child.message
declared by: Parent
parent Method.invoke: Child.message
child Method.invoke: Child.message
super in Child: Parent.message
findSpecial from Child: Parent.message
findVirtual: Child.message
static Parent method: Parent.category
final Parent method: Parent.fixed
~~~

### Analysis of each result

- `normal`: variable `parentRef` has declared type `Parent` yet points to `Child`; virtual invocation picks `Child.message`.
- `declared by`: the `Method` object itself belongs to `Parent`, confirming lookup on the superclass, yet it **does not lock** dispatch to Parent.
- `parent Method.invoke` and `child Method.invoke`: both execute `Child.message`; this separates Method metadata from runtime implementation selection.
- `super in Child`: `directSuper` inside Child uses the `super` keyword directly and thus executes `Parent.message`.
- `findSpecial from Child`: creates a method handle with special-invocation semantics from Child's privileged lookup, bypassing the override and running `Parent.message`.
- `findVirtual`: a method handle created with `findVirtual` still uses virtual dispatch when receiving Child, so it runs `Child.message`.
- `static Parent method`: `static` uses method hiding rather than overriding; Reflection calls the static method described on Parent; the receiver can be `null`.
- `final Parent method`: `final` cannot be overridden by Child; invoking on Child still uses `Parent.fixed`'s body.

The example runs on the classpath without special JVM options. If modified to split into **named modules** with restricted access, method handle creation behavior also depends on JPMS and lookup privileges.

## 5. Limitations of `Method.invoke` for calling super

In section 4's example, `fromParent.getDeclaringClass()` remains `Parent.class`, yet `fromParent.invoke(child)` calls `Child.message()`. This is **virtual dispatch**, just like a normal instance call. Replacing `getMethod` with `getDeclaredMethod`, casting `child` to `Parent`, or enabling `setAccessible(true)` all **do not** change the override selection mechanism.

`Method.invoke` takes a receiver and arguments; this API **has no option to "invoke only the super body"**. If polymorphic behavior is what you want, keep using `invoke`; when you truly need to call the superclass implementation, you need a special-invocation mechanism with suitable privileges, described below.

## 6. When can a super implementation be invoked using MethodHandles?

Java provides `java.lang.invoke.MethodHandle` and `MethodHandles.Lookup`. A method handle can represent invocation styles analogous to certain JVM bytecode instructions, including:

| API | Emphasized invocation kind | When receiver is Child overriding Parent |
| --- | --- | --- |
| `Method.invoke` on Parent's instance method | Dynamic lookup by receiver | Child override |
| `Lookup.findVirtual(Parent.class, "message", type)` | Virtual call similar to `invokevirtual` | Child override |
| `Lookup.findSpecial(Parent.class, "message", type, Child.class)` from Child's privileged lookup | Special call similar to `invokespecial` | Parent implementation, per `invokespecial` rules |
| `Lookup.unreflectSpecial(parentMethod, Child.class)` from Child's privileged lookup | Creates a special-invocation handle from Method metadata | Can call Parent implementation |
| `super.message()` in Child code | Language syntax for superclass call | Parent implementation |

### 6.1. `findSpecial` and its parameters

In the example:

~~~java
MethodHandle handle = MethodHandles.lookup().findSpecial(
        Parent.class,
        "message",
        MethodType.methodType(String.class),
        Child.class);
String result = (String) handle.invoke(this);
~~~

- `Parent.class`: the class where the special method is looked up.
- `"message"`: the name of the method to call.
- `MethodType.methodType(String.class)`: the return type and parameter types of the method; does not include the receiver.
- `Child.class`: the **special caller**, i.e., the class authorized to perform an `invokespecial`-style call in this context.
- `MethodHandles.lookup()`: created inside a method of `Child`, so the lookup class is indeed `Child` and holds access privileges to validate this call.
- `this`: the receiver the handle needs to execute. For an instance method, the handle's type includes a receiver parameter before the method parameters.

`findSpecial` is not merely another way of writing `findVirtual`. It carries **semantics that bypass ordinary overriding** and can only be created when the lookup has corresponding privileges. Per the API, if `specialCaller` does not match the lookup class or the lookup lacks required private access, the operation can fail with `IllegalAccessException`.

An invalid expectation example: placing `MethodHandles.lookup().findSpecial(Parent.class, ..., Child.class)` in arbitrary code outside Child and assuming any caller is allowed to invoke `super` on Child. `super` semantics are tied to an **authorized call site/class**, not just a declared class literal.

### 6.2. `unreflectSpecial` when you already have a Method

If you already obtained a `Method` via Reflection, from inside `Child` you can use:

~~~java
Method parent = Parent.class.getDeclaredMethod("message");
MethodHandle special = MethodHandles.lookup()
        .unreflectSpecial(parent, Child.class);
String result = (String) special.invoke(this);
~~~

This is a code snippet **to be placed inside an instance method of `Child`**, with `Parent`/`Child` as in section 4; appropriate checked exceptions and `Throwable` must be declared/propagated. `unreflectSpecial` reuses `Method` metadata to create a method handle with special-invocation semantics. It **does not** turn `parent.invoke(child)` itself into a super call.

Being able to read a `Method` via Reflection does not automatically authorize `unreflectSpecial`. The API still checks lookup privileges and access limits. `privateLookupIn` is also not an arbitrary "break-in" mechanism: switching to a lookup with private privileges is constrained by caller privileges and module package openness.

### 6.3. Why prefer direct `super` when controlling subclass code

When you write `Child` yourself, the simplest, clearest, and most stable way is:

~~~java
@Override
public String message() {
    return "Child wrapper -> " + super.message();
}
~~~

This directly performs the superclass call in a Java-authorized context, without creating Reflection or method handles. If a library wants external clients to call the parent's logic, it can expose an **explicit method** on `Child` (for example `callParentMessage()`) rather than forcing clients to obtain special access privileges.

`findSpecial` is useful when writing frameworks, dynamic invocation engines, or integrations needing dispatch control, yet it is more complex than `super` and has strict privilege boundaries.

## 7. Cases that do not follow the normal override model

| Method kind | Overridden like a normal instance method? | Behavior to remember |
| --- | --- | --- |
| Overridable instance method | Yes | `Method.invoke` selects the override matching the runtime receiver |
| `static` | No; same name/signature is **hiding** | Reflection calls the exact static Method found; receiver is ignored |
| `private` | Not overridden | Parent's private method is a private member; declaring the same signature in child does not override it |
| `final` instance | Cannot be overridden | Subclass receiver still only gets the inherited final implementation |
| Constructor | Not a Method, not inherited/overridden | Use `Constructor.newInstance`; no virtual dispatch like `Method.invoke` |
| `abstract` method on parent or interface | Can be implemented in child | `Method.invoke` with a concrete receiver reaches the valid implementation, if any |
| Interface default method | Can be overridden | `Method.invoke` on an overriding receiver normally reaches the override; calling only the default requires valid special invocation semantics |

Especially for private methods, do not see two methods with the same name and conclude "Child overrides Parent's private method". Java does not allow overriding a private member that way. If Reflection invokes Parent's private method on a Child instance with access permission, Parent's body runs because it has no corresponding dynamic override — **that is not a technique for calling `super` on an overridable public/protected method**.

Similarly, when a method is `static`, calling `Parent.class.getMethod("category").invoke(null)` runs `Parent.category`; `Child` can declare `category` with the same name yet only hides Parent's static method. Do not take that result as proof that normal instance methods can call super via `Method.invoke`.

### Interface default methods

Conceptual example:

~~~java
interface Greeting {
    default String hello() { return "Greeting.hello"; }
}

class Friendly implements Greeting {
    @Override
    public String hello() { return "Friendly.hello"; }

    String interfaceDefault() {
        return Greeting.super.hello();
    }
}
~~~

If you obtain `Greeting.class.getMethod("hello")` and call `invoke(new Friendly())`, the result reflects the override `Friendly.hello`. To call the default directly from `Friendly`, `Greeting.super.hello()` expresses the intent clearly. With method handles, the default case also involves special lookup yet must obey appropriate special-caller/interface rules; do not use an arbitrary `findSpecial` from outside the class and assume it is valid. This is an illustrative code snippet, not a standalone Java program with `main`.

## 8. Access rights and modules are separate from dispatch

Three questions must be evaluated separately:

1. **Can metadata be found?** `getMethod` only looks up matching public Methods; `getDeclaredMethod` searches direct declarations, including private ones.
2. **Do you have permission to invoke or create a special handle?** Check Java access control, lookup privileges, and JPMS boundaries when using named modules.
3. **Which method body is chosen once validly invoked?** With `Method.invoke` for overridable instance methods, it is still virtual dispatch; with a valid handle created via `findSpecial`, it follows special-invocation rules.

Therefore, `method.setAccessible(true)` (if permitted by the runtime) **only addresses access checks**. It does not change the receiver object, does not remove overrides, and does not force Parent to run. For named modules, a package not properly `opens`-ed can cause attempts to suppress access checks to fail with `InaccessibleObjectException` or `trySetAccessible() == false`.

Distinguishing errors:

| Symptom | Most likely issue |
| --- | --- |
| `NoSuchMethodException` | Wrong name/signature, choosing `getMethod` instead of `getDeclaredMethod`, or lookup class does not declare the method |
| `IllegalArgumentException` from `Method.invoke` | Receiver incompatible with Method's declaring class or invalid argument list/types |
| `NullPointerException` with instance `Method.invoke(null)` | Missing receiver instance |
| `IllegalAccessException` from `Method.invoke` | Caller lacks access permission for the method |
| `InvocationTargetException` | Target method body itself threw an exception; read `getCause()` |
| `IllegalAccessException` during `findSpecial` / `unreflectSpecial` | Lookup or special caller lacks privileges for special-invocation semantics |
| `WrongMethodTypeException` when calling `MethodHandle.invokeExact` | Call-site type does not match the method handle's type exactly |
| Runs successfully yet produces `Child.message` instead of `Parent.message` | **Not a Reflection bug**; this is virtual dispatch |

`MethodHandle.invoke`/`invokeExact` have different type checking/adaptation rules than `Method.invoke`. Specifically, `invokeExact` requires an exact call-site type; `invoke` performs certain type adaptations per the API. Avoid confusing method handle type errors with permission resolution or dispatch errors.

## 9. Common wrong attempts

### Mistake 1 — Casting the receiver to Parent

~~~java
Child child = new Child();
Method m = Parent.class.getMethod("message");
System.out.println(m.invoke((Parent) child)); // still Child.message
~~~

Casting only gives the same object a different compile-time view; it does not create a Parent object and does not disable overriding.

### Mistake 2 — Using getDeclaredMethod to "lock" the declaration in the superclass

~~~java
Method m = Parent.class.getDeclaredMethod("message");
System.out.println(m.invoke(new Child())); // still Child.message
~~~

`Declared` means metadata declared at Parent; it does not mean "run the exact body declared in Parent".

### Mistake 3 — Calling setAccessible(true) to avoid overriding

~~~java
Method m = Parent.class.getDeclaredMethod("message");
m.setAccessible(true);
System.out.println(m.invoke(new Child())); // still Child.message
~~~

This snippet may run for classes in a classpath example, yet in named modules deep access may not be granted. Even when enabled successfully, virtual dispatch remains intact.

### Mistake 4 — Creating a Lookup anywhere while specifying specialCaller as Child

~~~java
// Illustrating a wrong expectation when placed in a calling class without matching privileges:
MethodHandles.lookup().findSpecial(
        Parent.class, "message",
        MethodType.methodType(String.class), Child.class);
~~~

Merely typing `Child.class` in the parameter does not turn the calling class's lookup into a lookup with Child's privileges. The context creating the lookup and the special checks are what determine validity. Place the call inside Child as in section 4's example or design a legitimate delegating method.

### Mistake 5 — Calling super in a framework to skip all subclass logic

A framework that intentionally skips overrides can break invariants maintained by Child (input validation, synchronization, transactions, logging, security, or caching). Only call the superclass directly when the API contract genuinely permits it. In many situations, polymorphic invocation is the right and safer behavior.

## 10. Workflow for choosing in a real-world scenario

Suppose you are writing an annotation-based command runner:

1. **Want to run the actual object's behavior:** find a valid `Method` and `invoke(receiver)`; keep polymorphism if the method is overridable.
2. **Want to read annotations or signatures on the superclass:** use `Parent.class.getDeclaredMethod(...)` and inspect metadata; do not infer from that that Parent's body will be called.
3. **Want to wrap Parent's logic for Child to call intentionally:** write a `super.foo()` call inside Child or an explicit forwarding method.
4. **Need dynamic invocation with super semantics and Child's privileges:** consider `Lookup.findSpecial` or `unreflectSpecial` from a valid lookup, testing privileges in a real module environment.
5. **Do not control Child or lack lookup privileges:** do not rely on switching to `getDeclaredMethod`, casting, or `setAccessible` to bypass dispatch. Revisit the design and provide an API permitted by the class owner.

If the goal is to diagnose an unexpected result, log both **`method.getDeclaringClass()`** and **`receiver.getClass()`**, the method name, signature, and invocation type (`invoke`, `findVirtual`, or `findSpecial`). Both class types are important evidence, provided you understand their distinct roles.

## 11. Self-check exercises (with answers)

**Exercise 1.** `Parent p = new Child();`, `Method m = Parent.class.getMethod("message");`. What does `m.invoke(p)` run?

**Answer:** `Child.message` because the actual receiver is Child and the method has a valid override.

**Exercise 2.** Switch `getMethod` to `getDeclaredMethod` while keeping the Child receiver. Does the result change?

**Answer:** No; changing the Method metadata lookup mechanism does not change virtual dispatch.

**Exercise 3.** Can you write `((Parent) child).message()` to execute `Parent.message`?

**Answer:** No. Casting the reference does not change the object's runtime class, so the virtual call still picks `Child.message`.

**Exercise 4.** `setAccessible(true)` on `Parent.message` succeeded. Does that force Reflection to call Parent's body?

**Answer:** No. Access permissions and dispatch are two separate mechanisms.

**Exercise 5.** Inside `Child`, what is the simplest way to call `Parent`'s implementation?

**Answer:** `super.message()` inside an instance method of Child with calling access. When a dynamic call must be constructed, `findSpecial` from a privileged lookup is appropriate.

**Exercise 6.** `Parent.category` and `Child.category` are both `static`. Which method does `Parent.class.getMethod("category").invoke(null)` run?

**Answer:** `Parent.category`, because static methods do not have instance-style overriding; this is hiding.

**Exercise 7.** Parent's method is `final`. Can you write an override with the same signature in Child so Reflection picks Child?

**Answer:** No. Java forbids overriding final methods; calling the valid method on Child uses the inherited final implementation.

**Exercise 8.** A tool in another module creates `findSpecial(Parent.class, "message", ..., Child.class)` yet receives `IllegalAccessException`. Should you call `setAccessible(true)` on an arbitrary `Method` to fix it?

**Answer:** No. You must examine the lookup context, `specialCaller` privileges, and module boundaries; `setAccessible` on a `Method` does not grant privileges to create a special handle or alter dispatch semantics.

## 12. Takeaway and reference sources

**Core rule:** `Method.invoke` on an overridable instance method still uses **virtual dispatch**; a `Method` declared on Parent does not guarantee running Parent's body on a Child receiver. To intentionally invoke a superclass implementation, use `super` in authorized code, or a **special** method handle created with a valid lookup. `getDeclaredMethod`, casting the receiver, and `setAccessible` are not ways to change dispatch.

Official Java SE 17 documentation:

- [`java.lang.reflect.Method` — `invoke` section](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): dynamic method lookup by runtime type and exceptions during Reflection invocation.
- [`MethodHandles.Lookup` — `findVirtual`, `findSpecial`, `unreflectSpecial`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): handle kinds, lookup privileges, and special callers.
- [JLS `15.12.4.4 — Locate Method to Invoke](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.4): rules for locating the target method on invocation.
- [JVMS `6.5 — `invokevirtual` and `invokespecial`](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html): semantics of invocation instructions in the JVM.