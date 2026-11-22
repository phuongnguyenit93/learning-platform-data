# 1.2. Distinguishing Static Typing, OOP Dynamic Dispatch, and Runtime-Resolved Calls

In Java, **the type of an expression is checked at compile time**, while **the implementation of an instance method can be selected at runtime**. These two things coexist and do not contradict each other. It is also necessary to distinguish ordinary polymorphism from mechanisms that actively look up or link calls at runtime, such as Reflection, Method Handles, and the `invokedynamic` bytecode.

After this lesson, you will be able to determine: which type the compiler sees; which overload is selected; which overridden method runs; when runtime method lookup is needed; and why `invokevirtual` is not synonymous with `invokedynamic`.

## 1. Three easily confused concepts

Consider the expression:

```java
Animal pet = new Dog();
```

- **Static (declared) type** of the variable `pet` is `Animal`. `javac` uses this type to check accessible members, call signatures, assignments, and casts. Java is a statically typed language.
- **Actual type (runtime class)** of the object currently referenced by `pet` is `Dog`. This is the runtime information used when dispatching calls to overridable instance methods.
- **Dynamic dispatch** is the step of selecting an **implementation** for an already-determined method signature, based on the actual type of the receiver. It does not mean the runtime automatically searches for an arbitrary overload based on the actual types of all arguments.

A variable can sequentially reference objects of different subclasses, as long as the assignment is valid. The class name on the left side of the assignment does not change just because the object on the right side has a specific subclass. The value `null` has no target object; if an instance method is called on a `null` receiver, the call will throw a `NullPointerException`.

| Question | Where is it primarily decided? | Example |
| --- | --- | --- |
| Which methods can `pet` call, and with which signatures? | At compile time, from the static type and access permissions | `Animal` must declare/inherit a matching method |
| When there are multiple overloads with the same name, which signature is selected? | At compile time, based on argument expression types and overload rules | `feed(Object)` or `feed(String)` |
| For an overridable instance signature, which method body runs? | At runtime, based on the actual class of the receiver | `Dog.speak()` instead of `Animal.speak()` |
| How are method/class names known only at runtime found? | Runtime lookup or specialized runtime linkage | Reflection, Method Handle, `invokedynamic` |

Terminology note: **static type** is not **static method**. `static` in `Animal pet` refers to type checking; `static` in `static void f()` refers to a class member, which does not participate in instance overriding.

## 2. Two-step process: overload first, override second

When encountering `receiver.method(argument)`, separate two tasks:

1. **Compile time:** `javac` determines the static types of the receiver and arguments; finds available methods; and applies overload resolution rules to select **one signature**. Return type, access scope, type conversion compatibility, varargs, and generics can affect the validity of the call. The selected signature must be valid regardless of which subclass the runtime object later belongs to.
2. **Runtime:** if the call is an overridable instance method (`invokevirtual`/`invokeinterface`), the JVM selects the implementation corresponding to **that exact selected signature** on the actual class of the receiver. It does not go back to selecting an overload based on the actual class of the argument.

For static methods, constructors, `super` calls, and private methods, there is no ordinary instance overriding mechanism. Fields also do not have dynamic dispatch like instance methods.

### Standalone compilable and runnable Java 17+ example

Save the following file with the exact name `DispatchDemo.java`:

```java
public class DispatchDemo {
    static class Animal {
        String role = "animal";

        String speak() {
            return "Animal.speak";
        }

        String feed(Object food) {
            return "Animal.feed(Object): " + food;
        }

        static String kind() {
            return "Animal.kind";
        }
    }

    static class Dog extends Animal {
        String role = "dog";

        @Override
        String speak() {
            return "Dog.speak";
        }

        @Override
        String feed(Object food) {
            return "Dog.feed(Object): " + food;
        }

        String feed(String food) {
            return "Dog.feed(String): " + food;
        }

        static String kind() {
            return "Dog.kind";
        }
    }

    interface Greeter {
        String greet();
    }

    static class FriendlyDog extends Dog implements Greeter {
        @Override
        public String greet() {
            return "FriendlyDog.greet";
        }
    }

    public static void main(String[] args) {
        Animal pet = new Dog();

        System.out.println("speak: " + pet.speak());
        System.out.println("feed via Animal: " + pet.feed("bone"));
        System.out.println("feed via Dog: " + ((Dog) pet).feed("bone"));
        System.out.println("field via Animal: " + pet.role);
        System.out.println("static Animal: " + Animal.kind());
        System.out.println("static Dog: " + Dog.kind());

        Greeter greeter = new FriendlyDog();
        System.out.println("interface: " + greeter.greet());
    }
}
```

Compile/run using JDK 17 or higher:

```bash
javac -encoding UTF-8 DispatchDemo.java
java DispatchDemo
```

Output:

```text
speak: Dog.speak
feed via Animal: Dog.feed(Object): bone
feed via Dog: Dog.feed(String): bone
field via Animal: animal
static Animal: Animal.kind
static Dog: Dog.kind
interface: FriendlyDog.greet
```

**Analysis of each key point:**

- `pet.speak()`: the static type `Animal` allows calling `speak()`; the actual object `Dog` has overridden that exact signature, so `Dog.speak()` runs.
- `pet.feed("bone")`: even though `"bone"` is a `String`, at the call site `pet` only has the static type `Animal`, where the available overload is `feed(Object)`. `javac` selects `Animal.feed(Object)`. At runtime, `Dog.feed(Object)` **overrides that exact signature**, so the result is `Dog.feed(Object): bone`; the runtime **does not switch** to `Dog.feed(String)`.
- `((Dog) pet).feed("bone")`: after casting, the receiver in the expression has the static type `Dog`; the overload `feed(String)` can now be selected because it is more specific than `feed(Object)`. The cast is also checked by the JVM at runtime; casting an `Animal` that is not actually a `Dog` will cause a `ClassCastException`.
- `pet.role`: fields are selected by the **static type** `Animal`, so the value is `animal` even though the object has the field `Dog.role`. This is **field hiding**, not method overriding.
- `Animal.kind()` and `Dog.kind()`: two static methods with the same signature are **method hiding**. Use the class name for clarity; static methods are not dispatched based on the runtime class of the receiver.
- `greeter.greet()`: the variable has interface type `Greeter`; the `FriendlyDog` object provides the implementation. This is also runtime polymorphism, typically corresponding to the `invokeinterface` bytecode.

`@Override` does not create the dynamic dispatch mechanism; it asks the compiler to verify that the method actually overrides/implements a valid method. Thanks to this, signature mistakes are easily caught. If you omit `@Override` and accidentally write `feed(String)` when intending to override `feed(Object)`, you have created a new overload rather than overriding the old method.

## 3. What can and cannot be re-decided at runtime

**Implementation can change:** the same call `pet.speak()` can run different method bodies if `Animal`, `Dog`, or another subclass with an override is passed in turn. This is the core extension point of OOP: the caller depends on the superclass/interface contract instead of manually selecting each subclass.

**New members cannot magically appear through a superclass-typed variable:** if `Dog` has its own method `wagTail()` that `Animal` does not declare or inherit, the expression `pet.wagTail()` is invalid at compile time even though the runtime object might be `Dog`. To call it directly, a static type that declares that method is required (for example, a checked cast or a suitable interface). Another way is runtime lookup such as Reflection, but that is a different mechanism.

**Overloads cannot change after compilation:** suppose there are `print(Object)` and `print(String)`. With `Object value = "hi";`, the call `print(value)` will select the `print(Object)` overload at compile time, even though the runtime object is a `String`. If the selected overload has an override in a subclass, the override step still happens afterward; the two steps are not merged into one.

**Not every call is virtual:** `static`, `private`, `super.method()`, constructors, and field accesses have different binding rules. A `final` method cannot be overridden, even though the opcode emitted by the compiler may still be `invokevirtual`; **opcode** and overridability are not identical concepts.

## 4. Looking into bytecode: what is actually "dynamic"?

After compiling the example above, try:

```bash
javap -c -p DispatchDemo
```

Look for the calls (constant-pool numbers may vary between JDK versions):

| JVM Opcode | Typical meaning | Key point to remember |
| --- | --- | --- |
| `invokevirtual` | Calls an instance method via a class | Can perform dynamic dispatch to find an override based on the actual class |
| `invokeinterface` | Calls a method via an interface | Finds the corresponding implementation on the actual object |
| `invokestatic` | Calls a static method | Not a virtual override |
| `invokespecial` | Constructors, private methods, `super` calls, and certain special cases | Does not dispatch overrides in the manner of ordinary virtual calls |
| `invokedynamic` | Runtime linkage via a bootstrap method and `CallSite` | A different call-site linking mechanism, **not** the default opcode for all polymorphic calls |

In the bytecode of `pet.feed("bone")`, the method reference is still bound to the **signature** `Animal.feed(Object)`, not `Dog.feed(String)`. When the receiver is `Dog`, the JVM finds the override `Dog.feed(Object)`. This is proof that overloading and overriding occur at two different times.

`invokedynamic` is designed to flexibly link a call site at runtime. A bootstrap method provides a `CallSite` whose target is a `MethodHandle`; depending on the type of `CallSite`, the target may be fixed or may change according to its contract. In modern Java, the compiler often uses `invokedynamic` to implement lambdas and string concatenation; the exact bytecode emitted depends on the JDK/compiler. Therefore, you **may** see `invokedynamic` for string concatenation in `System.out.println("speak: " + pet.speak())`, but that does not mean `pet.speak()` has become a Reflection call or an overload re-selected at runtime.

The JVM can inline/devirtualize a call when the JIT proves the target type is suitable, and then deoptimize if the assumption no longer holds. This performance optimization must preserve the polymorphism semantics specified by Java; "dynamic dispatch" does not mean every execution is forced to scan a method table from scratch.

## 5. Runtime lookup: when even the call target is only known at runtime

Ordinary polymorphism requires the compiler to know the **method contract** in advance. If an application reads a class name, method name, or plugin from configuration, it may need **Reflection** or **Method Handles** to find the target at runtime.

Standalone Reflection example, saved as `ReflectiveCallDemo.java`:

```java
import java.lang.reflect.Method;

public class ReflectiveCallDemo {
    public static class Hello {
        public String say(String name) {
            return "Xin chào, " + name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        String className = "ReflectiveCallDemo$Hello";

        Class<?> type = Class.forName(className);
        Object instance = type.getDeclaredConstructor().newInstance();
        Method method = type.getMethod("say", String.class);

        Object result = method.invoke(instance, "Lan");
        System.out.println(result);
    }
}
```

```bash
javac -encoding UTF-8 ReflectiveCallDemo.java
java ReflectiveCallDemo
```

```text
Xin chào, Lan
```

Here `Class.forName` finds the class by its **binary name** at runtime (the `$` sign denotes a nested class); `getMethod("say", String.class)` finds a public method by name and parameter types; `Method.invoke` invokes the method on the actual object. The compiler does not verify whether the string `"say"` is actually an existing method. Changing the name or signature can lead to `ClassNotFoundException`, `NoSuchMethodException`, `IllegalAccessException`, and other runtime errors. If the body of the method invoked by Reflection throws an exception, `Method.invoke` wraps the cause in an `InvocationTargetException`.

Related but distinct mechanisms:

- **OOP Dynamic dispatch:** the caller already has the `speak()` signature via the `Animal`/interface type; the runtime only selects the appropriate implementation. This is the default choice for polymorphism and extensibility via interfaces.
- **Reflection (`Class`, `Method`, `Constructor`):** allows metadata lookup and execution when the name/signature is provided at runtime; in return, type checking is deferred to runtime, and access and exceptions must be handled.
- **Method Handle (`java.lang.invoke`):** represents a call target with a method type (`MethodType`); it can be looked up/composed at runtime and then invoked with `invoke` or `invokeExact`. It is related to the `invokedynamic` infrastructure, but using `MethodHandle` **does not automatically make** a call into an `invokedynamic` opcode.
- **Dynamic Proxy:** a proxy object implements interfaces and forwards calls to an `InvocationHandler`; useful for cross-cutting concerns, interceptors, and RPC. It is still subject to interface contracts and does not turn Java into a dynamically typed language.
- **`invokedynamic`:** bytecode with a bootstrap that links the call site at runtime; this is a JVM-level mechanism. Do not use the opcode name as a generic term for `invokevirtual`, Reflection, or proxies.

What they have in common is that a decision is deferred to runtime; **the difference** is whether that decision involves the implementation of a known signature, finding a method via metadata, or linking an entire call site.

## 6. When designing an application, what should you choose?

| Scenario | Usually appropriate choice | Reason |
| --- | --- | --- |
| Multiple ways to handle the same contract, e.g. `PaymentProcessor.process()` | Interface + override | Type-checked at compile time, natural implementation extensibility |
| Two functions with the same name serving different parameter types | Intentional overloading | Caller selects signature from static type; avoid expecting runtime selection by argument class |
| Need to call a plugin whose class name is supplied by configuration at runtime | Plugin mechanism / `ServiceLoader`; Reflection when truly needed | Can discover providers at runtime while still enforcing a clear contract |
| Need an adapter/interceptor by interface | Dynamic Proxy or concrete implementation/decorator | Clearly expresses the boundary for intercepted calls |
| Writing a runtime linkage framework, lambda factory, or JVM tool | Method Handle / `invokedynamic` when technically justified | Controls call-site linkage, accepting higher complexity |

Before using Reflection just to choose among known subclasses, consider interfaces, factories, or dependency injection: they are usually easier to type-check, easier to refactor, and easier to test. Although runtime dispatch can have overhead, do not assume it is slow by default: the JVM optimizes common calls quite well. Measure actual performance before changing the design.

## 7. Conceptual pitfalls and self-check

1. **"Java is statically typed, so it cannot do dynamic calls."** False: static type checking and dynamic method dispatch operate at two different layers.
2. **"The object is `Dog`, so the overload `Dog.feed(String)` will definitely run."** False when the receiver has static type `Animal`: the overload is selected first based on `Animal`, and only then is the override of that same signature dispatched.
3. **"`static` methods are a form of overriding."** False: they are hidden (hiding); they should be called by class name. Fields are also hidden, not virtually dispatched.
4. **"Every dynamic call in the JVM uses `invokedynamic`."** False: `invokevirtual` and `invokeinterface` already support ordinary runtime polymorphism.
5. **"Casting changes an object into another class."** False: a cast checks/provides a new expression type; the object remains the same object. An invalid cast throws `ClassCastException`.
6. **"When using Reflection, you don't need to care about signatures/accessibility."** False: checking is shifted to runtime; errors can appear late and be harder to detect.
7. **"Runtime dispatch always hinders optimization."** Inaccurate: the JIT can inline based on valid observations/assumptions while preserving correct semantics when the target class changes.

**Quick self-check (based on `DispatchDemo`):**

- What does `Animal x = new Dog(); x.speak()` return? → `Dog.speak`, because the override is dispatched by runtime class.
- What does `Animal x = new Dog(); x.feed(42)` return? → `Dog.feed(Object): 42`, because the compiler selects `feed(Object)` and `Dog` overrides that signature.
- What does `Animal x = new Dog(); x.role` return? → `animal`, because field access depends on the static type.
- Which overload does `((Dog) x).feed("bone")` select? → `Dog.feed(String)`, because the static type of the receiver after the cast is `Dog`.
- If `x` actually points to `new Animal()`, does the cast `(Dog) x` create a `Dog`? → No; the cast will throw `ClassCastException`.
- Is seeing `invokedynamic` in `javap` enough to conclude the program is using Reflection? → No; it could just be a lambda or string concatenation.

**Rule for reading a Java call:** identify **the static types of the receiver and arguments → the signature/overload selected by the compiler → the kind of call (virtual, interface, static, special, or dynamic linkage) → the actual class of the receiver if dispatch is needed → the executing implementation or call-site target**. Separating these steps properly will help predict behavior, read bytecode, and debug runtime mechanisms accurately.