# Dynamic dispatch when a superclass `Method` is invoked on a subclass

A very easily misunderstood scenario in Java Reflection: you look up a `Method` by inspecting the **superclass**, yet pass a **subclass object** into `Method.invoke()`. If the subclass overrides that instance method, **Java still executes the subclass's override**.

```java
Method method = Parent.class.getMethod("speak");
Object result = method.invoke(new Child());
```

Assuming `Child extends Parent` and overrides `speak()`, `result` is the result of `Child.speak()`. The `Method` object still reflects the declaration looked up from `Parent`; choosing which implementation to execute happens **at invocation time**, based on the runtime type of the receiver. This is *dynamic method dispatch*, not a special mechanism invented by Reflection.

This lesson belongs to the **Method** group in Java Core Reflection; the focus is distinguishing three pieces of information: **the looked-up method signature**, **the declaring class on the `Method` object**, and **the implementation actually invoked**.

## 1. Recap: overriding and runtime type

In Java, a call to an overridable instance method is selected according to the **actual type of the object**:

```java
class Parent {
    String speak() {
        return "Parent";
    }
}

class Child extends Parent {
    @Override
    String speak() {
        return "Child";
    }
}

Parent object = new Child();
System.out.println(object.speak()); // Child
```

The variable `object` has **declared type** `Parent` yet references an object with **runtime type** `Child`. The compiler checks that calling `speak()` is valid on `Parent`, while the JVM chooses the override implementation matching the actual receiver. If the subclass does not override it, the corresponding inherited implementation runs.

Overriding follows Java's rules: the subclass method must be compatible in name, signature, and return type; must not reduce the access level of the overridden method; and cannot override `final`, `static`, or `private` methods. With `static`, there is **method hiding**, not overriding.

When moving the call to Reflection, this essence remains unchanged for overridable instance methods.

## 2. `Method` represents the declaration; `invoke()` takes a runtime receiver

`java.lang.reflect.Method` provides metadata such as:

| API | What does it tell? | What to avoid inferring |
| --- | --- | --- |
| `method.getDeclaringClass()` | Class/interface containing the declaration that `Method` represents | Not necessarily the class whose body will execute when the receiver is a subclass |
| `method.getName()` | Declared name | Does not uniquely identify overloads if parameters are missing |
| `method.getParameterTypes()` | Parameter types per the reflected signature | Cannot be substituted by the runtime types of individual arguments |
| `method.getReturnType()` | Return type in the corresponding declaration | Not a mechanism to re-lookup a method by runtime return value |
| `method.getModifiers()` | Modifiers of the declaration | Does not confirm in advance which override will be chosen |
| `method.invoke(receiver, args...)` | Requests invoking the method on the receiver with passed arguments | For an overridable instance method, the implementation is chosen dynamically |

Specifically:

```java
Method fromParent = Parent.class.getDeclaredMethod("speak");
System.out.println(fromParent.getDeclaringClass() == Parent.class); // true

Parent childAsParent = new Child();
Object result = fromParent.invoke(childAsParent);
// If Child overrides speak(), result receives the output of Child.speak()
```

`getDeclaringClass()` **does not turn into `Child.class` after `invoke()`**. The class owning the `Method`'s declaration and the class owning the implementation selected at invocation are two different perspectives.

For an instance method, the receiver passed to `invoke` must be an instance of the declaring class or a valid subtype. Therefore a `Method` obtained from `Parent` can be invoked on `new Child()`; an unrelated object will be rejected.

## 3. Three phases to distinguish

**Phase 1 — Lookup.** We select a method to reflect by class, name, and parameter type list:

```java
Method method = Parent.class.getDeclaredMethod("speak", String.class);
```

`getDeclaredMethod` only searches for methods **declared directly** in `Parent` with the requested signature. `getMethod` searches for `public` methods within the API's supported scope, including inherited ones. Choosing `Parent.class` at lookup does not lock the receiver of all future calls to the superclass.

**Phase 2 — Access/arguments.** `Method.invoke` validates the receiver, enforces access rights under reflection/module rules, and checks/converts arguments. A method can be found yet the call still fail due to access checks or an invalid receiver.

**Phase 3 — Dispatch.** For an overridable instance method, the JVM chooses the implementation matching the runtime class of the receiver. If `Child` overrides it, `Child` runs; if a `GrandChild extends Child` overrides it further, `GrandChild`'s version can run.

General flow:

```text
Parent.class.getMethod("speak")
                |
                v
      Method (Parent declaration)
                |
                v
    invoke(receiver = new Child())
                |
                v
        Runtime type: Child
                |
                v
    Does Child override speak()?
           /           \
         Yes            No
          |              |
          v              v
     Child.speak()   Inherited method
```

That is why **you cannot deduce the exact body that will execute solely from `getDeclaringClass()`** for an overridden virtual method.

## 4. Complete, standalone Java 17+ example

Save the program to `DynamicDispatchDemo.java`:

```java
import java.lang.reflect.Method;

public class DynamicDispatchDemo {
    public static class Parent {
        public String speak(String name) {
            return "Parent:" + name;
        }

        public static String kind() {
            return "Parent-static";
        }

        private String secret() {
            return "Parent-private";
        }

        public final String stable() {
            return "Parent-final";
        }
    }

    public static class Child extends Parent {
        @Override
        public String speak(String name) {
            return "Child:" + name;
        }

        // Overload: different parameter type, does not override speak(String).
        public String speak(Object name) {
            return "Child-overload:" + name;
        }

        // Hiding Parent's static method.
        public static String kind() {
            return "Child-static";
        }

        // Does not override Parent.secret() because Parent.secret() is private.
        public String secret() {
            return "Child-public";
        }
    }

    public static void main(String[] args) throws Exception {
        Method fromParent =
                Parent.class.getDeclaredMethod("speak", String.class);
        Parent receiver = new Child();

        System.out.println("Method owner: "
                + fromParent.getDeclaringClass().getSimpleName());
        System.out.println("Receiver type: "
                + receiver.getClass().getSimpleName());

        System.out.println("Parent instance: "
                + fromParent.invoke(new Parent(), "Java"));
        System.out.println("Child instance: "
                + fromParent.invoke(receiver, "Java"));

        Method fromChild =
                Child.class.getMethod("speak", String.class);
        System.out.println("Child method owner: "
                + fromChild.getDeclaringClass().getSimpleName());

        System.out.println("Parent static: "
                + Parent.class.getDeclaredMethod("kind").invoke(null));

        Method parentPrivate =
                Parent.class.getDeclaredMethod("secret");
        parentPrivate.setAccessible(true);
        System.out.println("Parent private: "
                + parentPrivate.invoke(receiver));

        System.out.println("Child public secret: "
                + Child.class.getMethod("secret").invoke(receiver));

        System.out.println("Parent final: "
                + Parent.class.getDeclaredMethod("stable").invoke(receiver));

        // Method was looked up with signature speak(String), does not switch
        // to overload speak(Object) on Child.
        System.out.println("Parent chosen overload: "
                + fromParent.invoke(receiver, new Object[] {"Java"}));

        try {
            fromParent.invoke(new Object(), "Java");
        } catch (IllegalArgumentException ex) {
            System.out.println(
                    "Unrelated receiver: IllegalArgumentException");
        }
    }
}
```

Compile and run:

```bash
javac DynamicDispatchDemo.java
java DynamicDispatchDemo
```

Output:

```text
Method owner: Parent
Receiver type: Child
Parent instance: Parent:Java
Child instance: Child:Java
Child method owner: Child
Parent static: Parent-static
Parent private: Parent-private
Child public secret: Child-public
Parent final: Parent-final
Parent chosen overload: Child:Java
Unrelated receiver: IllegalArgumentException
```

**Explanation by result group:**

1. `Method owner: Parent` because `fromParent` was created from `Parent.speak(String)`'s declaration. This **does not change** when the receiver is `Child`.
2. `Parent instance: Parent:Java` and `Child instance: Child:Java` use **the same `Method`**. Only the receiver differs, so for an overridable method, the implementation is chosen dynamically.
3. `Child method owner: Child` is the result of **a different lookup**, this time using `Child.class.getMethod("speak", String.class)`. The API returns `Child`'s override declaration; it does not come from the parent `Method` mutating itself.
4. `Parent static: Parent-static` because `static` is *hidden* rather than overridden. The `Method` obtained from `Parent` retains `Parent`'s static behavior.
5. `Parent private: Parent-private` because `Parent`'s `private` method is not overridden. `Child.secret()` is a different method and prints `Child-public`. The example code uses `setAccessible(true)` within the same application environment; opening private access across named modules can be blocked by JPMS.
6. `Parent final: Parent-final` because `final` prevents subclasses from overriding.
7. `Parent chosen overload: Child:Java`: lookup selected the `speak(String)` signature and the call dispatches to the corresponding override; even though `Child` adds `speak(Object)`, the JVM does not automatically switch to that overload.
8. Receiver `new Object()` is not an instance of `Parent`, so `invoke` throws `IllegalArgumentException` before the target method can be called.

The output above reflects Java 17+ and does not depend on reflection array traversal order, because all lookups specify explicit names and signatures.

## 5. Why does `getDeclaringClass()` differ from the runtime implementation?

With the snippet:

```java
Method m = Parent.class.getMethod("speak", String.class);
Object value = m.invoke(new Child(), "A");
```

There are two separate questions:

- Is `m.getDeclaringClass() == Parent.class`? **Yes** in this example: object `m` represents `Parent`'s declaration.
- Which body executes for receiver `Child`? **`Child.speak(String)`**, because it is an overridable instance method and `Child` overrides it.

This also applies to multi-level subclasses:

```java
class GrandChild extends Child {
    @Override
    public String speak(String name) {
        return "GrandChild:" + name;
    }
}
```

This is an **additional illustrative snippet** to be declared in the same scope as `Parent` and `Child` in the example. When `fromParent.invoke(new GrandChild(), "Java")` runs, the expected output is `GrandChild:Java`. The parent's `Method` is the **looked-up entry point**, not a command to "force running the parent's body".

For libraries/frameworks, this point matters: a proxy subclass or a framework-generated subclass can override a method. When calling a superclass method via Reflection, the override code on the proxy/subclass can still participate in execution.

## 6. When is there no override-style dynamic dispatch?

Java methods are not always overridable virtual calls. Distinguish:

| Method kind | Can Child override the same method? | When using a `Method` obtained from `Parent` with a `Child` receiver |
| --- | --- | --- |
| Validly overridable `public`/`protected`/package-private instance | Yes, if Java access and inheritance rules allow | Executes the closest matching override on the runtime class |
| `static` | No; can **hide** the static method | Calls the static method declared on `Parent`; receiver does not govern dispatch |
| `private` | No; method is not inherited as an overridable method | Calls `Parent`'s private body directly if reflection access is permitted |
| `final` instance | No | Calls the body from `Parent`'s declaration because no valid override exists |
| Constructor | Not a `Method`, cannot be overridden | Uses `Constructor.newInstance`, no virtual dispatch like instance methods |

### `static` is hiding, not overriding

```java
class Base {
    static String label() { return "Base"; }
}
class Derived extends Base {
    static String label() { return "Derived"; }
}

// Method obtained from Base -> still calls Base.label().
Method m = Base.class.getDeclaredMethod("label");
System.out.println(m.invoke(null)); // Base
```

This is an **illustrative snippet requiring `import java.lang.reflect.Method`**. For `static` methods, pass `null` as the receiver argument of `Method.invoke` because the target object is not used.

### `private` does not override

If both `Parent` and `Child` have a method named `secret()`, yet the method in `Parent` is `private`, then the two methods **have no overriding relationship**. Reflection obtaining the `Method` from `Parent` can call `Parent`'s private body once access is granted. Do not infer that "having the same name" creates dynamic dispatch.

### `final` restricts overriding

A `final` instance method is still an instance method, yet subclasses cannot declare an override. Because there is no valid override in the subclass, e.g. `Parent.finalMethod` on a `Child` receiver still executes that implementation. Here `final` prevents replacement of the body by subclasses.

## 7. Overriding vs. overloading: Reflection does not pick the best overload

**Overriding**: A subclass provides a replacement implementation for an inherited instance method under Java rules, e.g. `speak(String)` in `Parent` and `Child`.

**Overloading**: Multiple methods share the same name with different parameter lists, e.g. `speak(String)` and `speak(Object)`.

`getMethod("speak", String.class)` and `getMethod("speak", Object.class)` can return **two distinct `Method` objects**, representing two signatures. Once the `Method` for `speak(String)` is selected, `invoke(receiver, value)` **does not re-run the Java compiler's overload resolution algorithm from scratch** based on the runtime value. It only checks/converts the argument for the selected signature and then dispatches the corresponding override if one exists.

For example, when `Child` additionally declares `speak(Object)`, calling `Parent.speak(String)` via reflection on a `Child` receiver still reaches `Child.speak(String)` rather than `Child.speak(Object)`.

If writing a method-name router framework, you must determine the exact signature: `getParameterTypes()`, parameter count, boxing/unboxing, widening, varargs, and an overload-selection policy. **Dynamic dispatch does not solve overload selection for you.**

## 8. What is the difference between looking up on the superclass vs. the subclass?

Common APIs:

| How `Method` is obtained | Search behavior | Suitability |
| --- | --- | --- |
| `Parent.class.getDeclaredMethod("m", types...)` | Only methods declared directly in `Parent`, including non-public | Need the parent's exact declaration |
| `Parent.class.getMethod("m", types...)` | `public` methods per `getMethod` lookup rules | Need the public contract on the parent |
| `Child.class.getDeclaredMethod("m", types...)` | Only methods declared directly in `Child` | Need to know whether the subclass declares a method with that signature |
| `Child.class.getMethod("m", types...)` | `public` methods findable on `Child`, including inherited ones | Need to work through Child's public API |

For example, `Child.class.getDeclaredMethod("stable")` will fail if `stable()` is only declared by `Parent`, even though `Child` **inherits and can call** `stable()`. Meanwhile `Child.class.getMethod("stable")` can succeed, returning the inherited public method with `getDeclaringClass() == Parent.class`.

For override `Child.speak(String)`, `Child.class.getMethod("speak", String.class)` finds `Child`'s declaration; whereas `Parent.class.getMethod("speak", String.class)` gives `Parent`'s method. Yet both can execute the same `Child` implementation when the receiver is a `Child` instance and that signature is overridden.

**Choose lookup based on metadata intent**, do not use lookup on `Parent` as a "trick" to bypass overriding.

## 9. Receiver requirements and important exceptions

`Method.invoke(Object receiver, Object... arguments)` distinguishes instance and static methods:

- **Instance method:** receiver must be non-`null` and compatible with the class/interface declaring the method. `new Child()` is valid when `Child extends Parent`; `new Object()` is invalid for a method declared in `Parent`.
- **Static method:** receiver is ignored; passing `null` keeps code clear.
- **Parameters:** argument count and types must be compatible with the signature represented by `Method`. Reflection can apply appropriate unboxing and primitive widening, but does not automatically choose another overload.
- **Access rights:** before invoking, reflection still obeys Java access checks and module restrictions unless checks have been suppressed. Finding a method does not mean the caller is allowed to invoke it.

| Exception | Typical context | Meaning |
| --- | --- | --- |
| `NoSuchMethodException` | `getDeclaredMethod`/`getMethod` | Name or parameter type list does not match the search scope |
| `IllegalAccessException` | `Method.invoke` | Cannot access the method under current access checks |
| `IllegalArgumentException` | `Method.invoke` | Incompatible receiver, wrong argument count/types |
| `NullPointerException` | `Method.invoke` on an instance method with `null` receiver | No object available to invoke the instance method |
| `InvocationTargetException` | `Method.invoke` when the target method throws an exception | The method body threw an error; inspect `getCause()` |
| `InaccessibleObjectException` | `setAccessible(true)` | Cannot suppress access checks, usually because a named module's package is not open |

Important: `InvocationTargetException` does not mean the dispatch algorithm failed. It typically tells you that **the target method was selected and ran**, and then threw an exception itself.

`Method.invoke` cannot be used as a special mechanism to "pierce through" module encapsulation. For example, `setAccessible(true)` can be rejected by JPMS even though a `Method` was found via `getDeclaredMethod`.

## 10. Interface methods, abstract methods, and default methods

Virtual dispatch is not limited to concrete superclasses. Suppose an interface declares `String name()`, and different implementations execute based on the receiver:

```java
interface Named {
    String name();
}

class First implements Named {
    public String name() { return "First"; }
}

class Second implements Named {
    public String name() { return "Second"; }
}

Method method = Named.class.getMethod("name");
System.out.println(method.invoke(new First()));  // First
System.out.println(method.invoke(new Second())); // Second
```

This is an **illustrative snippet requiring `import java.lang.reflect.Method`**. Across both calls, `Method.getDeclaringClass()` remains `Named.class`, while the implementation is chosen according to the receiver's class.

Similarly, `Method` can represent an `abstract` method of an abstract superclass or interface and be invoked on an instance of a concrete subclass implementing it. If an interface has a **default method**, an implementing class may inherit the default implementation or override it; `Method.invoke` still follows the appropriate dispatch mechanism.

Do not confuse this with a `super.m()` call specially bound in Java code. A `Method` reflecting a superclass method and called via `invoke(child)` **is not equivalent** to a `super.m()` call inside the subclass. To deliberately invoke an overridden superclass implementation, look into method handles/special invocation and their associated access rights; regular `Method.invoke` has no "bypass override" option.

## 11. Bridge methods, generics, and proxies: real-world scenarios

With generics, the compiler sometimes generates a **bridge method** to maintain polymorphism after type erasure. Conceptual example:

```java
class Box<T> {
    T normalize(T value) { return value; }
}

class TextBox extends Box<String> {
    @Override
    String normalize(String value) {
        return value.trim();
    }
}
```

Due to type erasure, the erased signature on `Box<T>` uses `Object`. The compiler can generate a bridge in `TextBox` to forward `normalize(Object)` calls to the `normalize(String)` implementation and preserve overriding. A framework reflecting methods from `TextBox`'s `getDeclaredMethods()` can see both the source method and the bridge/synthetic method; check `method.isBridge()` and `method.isSynthetic()` before deciding which method to pick.

With **proxy subclasses** generated by ORM, mocking frameworks, or AOP, the runtime class can override public/protected methods to add interceptors. When invoking a `Method` obtained from a superclass with a proxy subclass receiver, dispatch can still reach the override on the proxy. That is JVM behavior consistent with dynamic dispatch, not `Method.invoke` always preferring the looked-up class's body.

However, proxies using **interface-based delegation** differ from subclass proxies; you cannot assume every kind of proxy is a subclass of the target class. Verify the actual hierarchy/runtime class before drawing conclusions.

## 12. Common misconceptions

**Misconception 1 — "Getting `Method` from `Parent.class` always runs `Parent`'s code".** False for overridable instance methods. `invoke(new Child())` still calls `Child`'s override if present.

**Misconception 2 — "`getDeclaringClass()` tells which implementation ran".** Not necessarily. It only reports the class/interface containing the declaration that the `Method` object reflects. With a polymorphic receiver, you must inspect the runtime class and overriding relationships.

**Misconception 3 — "Same name always means override".** False. `static` creates hiding, `private` is not overridden, differing parameter signatures are overloads; `final` methods cannot be overridden.

**Misconception 4 — "Reflection will choose the best overload by the runtime class of arguments".** False. The signature is fixed at the `getMethod(name, parameterTypes)` or `getDeclaredMethod(...)` step. `invoke` converts arguments for the already-selected method and dispatches overrides if applicable.

**Misconception 5 — "`setAccessible(true)` forces the parent's method to run".** False. `setAccessible` only requests suppressing Java language access checks when permitted; it does not disable virtual dispatch and does not replace the call with `super.m()`.

**Misconception 6 — "A Method obtained from a superclass can always be called with any Object".** False. The receiver of an instance method must belong to the declaring class or an appropriate subtype; otherwise `invoke` throws `IllegalArgumentException`.

**Misconception 7 — "Wrong override execution is Reflection's fault".** Inspect the override code, proxies/interceptors, exceptions thrown by the target, and inheritance relationships. Reflection follows normal Java dispatch rules for overridable instance methods.

## 13. Checklist when building a framework using `Method`

When a library stores a `Method` of an interface/superclass and invokes it on runtime objects:

1. **Lock down the contract:** choose the right method and signature in `getMethod`/`getDeclaredMethod`; do not assume overloads.
2. **Validate the receiver:** check `receiver.getClass()` for the runtime type, while verifying receiver compatibility with the declaring class. A `null` receiver is only appropriate for static methods.
3. **Check modifiers:** `Modifier.isStatic(method.getModifiers())`, `Modifier.isPrivate(...)`, or `Modifier.isFinal(...)` to know whether overriding is possible.
4. **Anticipate dynamic dispatch:** for overridable instance methods, overrides on the receiver, subclass, or proxy can execute even when `Method` comes from a superclass/interface.
5. **Handle access/modules:** do not treat metadata lookup as permission to call; only call `setAccessible`/`trySetAccessible` when needed and with JPMS awareness.
6. **Handle errors at the right layer:** separate lookup, receiver/argument, access, and target-thrown exception errors (`InvocationTargetException.getCause()`).
7. **Handle compiler-generated methods:** if building a method scanner and encountering generics/bridge methods, use `isBridge()`, `isSynthetic()`, and deliberate method-selection rules.

### Self-check

**Question 1.** `Parent.class.getMethod("speak", String.class)` returns a method with `getDeclaringClass() == Parent.class`. With `new Child()` overriding `speak(String)`, which implementation runs?  
**Answer:** `Child.speak(String)`, because dynamic dispatch relies on the runtime receiver.

**Question 2.** If `Parent.speak(String)` is `static` and `Child` declares a `static` method with the same signature, which method does the `Method` obtained from `Parent` call?  
**Answer:** `Parent.speak(String)`; static hiding is not overriding.

**Question 3.** Why can `Child.class.getDeclaredMethod("stable")` throw `NoSuchMethodException` even though `Child` can call `stable()`?  
**Answer:** Because `getDeclaredMethod` only searches direct declarations; `stable()` is declared in `Parent` and inherited.

**Question 4.** Can `fromParent.setAccessible(true)` force `fromParent.invoke(new Child())` to run the body of `Parent.speak(String)`?  
**Answer:** No. Accessibility and virtual dispatch are two separate mechanisms.

## Conclusion

In Java Reflection, **the class used to look up `Method` determines the selected declaration**, while **the actual receiver determines the implementation of an overridable instance method at invocation time**. Hence:

```text
Method obtained from Parent
       +
runtime receiver Child
       +
valid Child override
       =
runs Child implementation
```

Only by understanding the boundary between **lookup → access/argument check → dynamic dispatch** can you interpret `Method.invoke()` accurately, especially with inheritance, interfaces, generic bridges, and subclass proxies.
