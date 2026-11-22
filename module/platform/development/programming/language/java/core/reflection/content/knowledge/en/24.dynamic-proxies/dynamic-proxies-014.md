# Interface-Based Dynamic Proxy vs. Bytecode-Generated Subclass Proxy in Java

In Java Reflection, two techniques are both commonly called **proxy** because each places an intermediary layer in front of real behavior for logging, authorization, timing, transactions, or remote calls. However, **JDK dynamic proxies** and **subclass-based proxies (subclass proxies)** have completely different type structures, interception mechanisms, and limitations.

Most common point of confusion: **JDK dynamic proxies also generate bytecode/classes at runtime**. The key difference is not "one generates bytecode and the other does not," but whether **the generated proxy class implements interfaces** or **extends a concrete class and overrides overridable methods**.

## 1. Two mechanisms at the type and call level

### JDK dynamic proxy: standing in front of interfaces

Given an interface `Greeting` and an implementation `GreetingImpl`:

```text
Client holds a Greeting reference
          |
          v
Proxy object (JVM-generated class, extends java.lang.reflect.Proxy)
          | implements Greeting
          v
Interface method on proxy
          |
          v
InvocationHandler.invoke(proxy, method, args)
          |
          +--> calls real GreetingImpl, or performs other behavior
```

When `greeting.say("An")` is called, execution enters the method generated on the proxy class and dispatches to `InvocationHandler`. The handler **may** delegate to a target, return a simulated result, call over the network, or throw an exception. JDK Proxy does not mandate having a target instance.

Initialization example:

```java
Greeting proxy = (Greeting) Proxy.newProxyInstance(
        Greeting.class.getClassLoader(),
        new Class<?>[] {Greeting.class},
        handler);
```

This is an **illustrative snippet**: assume `Greeting` and `handler` are already defined. The returned object satisfies `proxy instanceof Greeting`, yet normally it is **not** an instance of `GreetingImpl` even when the handler forwards calls to `GreetingImpl`. The proxy class extends `java.lang.reflect.Proxy`, not the implementation `GreetingImpl`. One JDK proxy class can implement multiple valid interfaces.

### Subclass proxy: standing in front of a concrete class

Given a class `Service` with an overridable method `work()`:

```text
Client holds a Service reference
          |
          v
Object of a library-generated subclass
          | extends Service
          v
Overridden work() method in the subclass
          |
          +--> interceptor before call
          +--> calls super.work() / forwards to target (depends on mechanism)
          +--> interceptor after call
```

Libraries such as **Byte Buddy** or **CGLIB** can generate bytecode and define a subclass at runtime, overriding eligible methods to insert intermediary logic. This object can be used just like the base class itself: `subclassProxy instanceof Service` is `true`. `Service` does not need to declare an interface.

**Note:** a bytecode-generation library may support multiple ways of creating classes; here "subclass proxy" specifically refers to generating a class that `extends Service` and overrides methods. How targets are called, state is stored, and instances are created depends on the framework and configuration.

## 2. How does JDK Proxy route calls through InvocationHandler?

The core APIs reside in `java.lang.reflect.Proxy` and `java.lang.reflect.InvocationHandler`:

- `Proxy.newProxyInstance(loader, interfaces, handler)`: creates an instance of a proxy class supporting the requested interfaces. Interfaces must satisfy JVM visibility, class loader, and module constraints.
- `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`: receives the proxy being invoked, `Method` metadata, and arguments. For parameterless methods, `args` may be `null`.
- `method.invoke(target, args)`: an **optional** way to delegate to an implementation; when the real method throws an exception, Reflection may wrap it in `InvocationTargetException`, whose cause must be handled.
- `Proxy.isProxyClass(type)` and `Proxy.getInvocationHandler(proxy)`: check for a JDK proxy class and retrieve its handler when appropriate.

Not every Java call on a proxy object enters the handler. Interface instance methods are routed through the handler; `equals(Object)`, `hashCode()`, and `toString()` declared on `Object` are also routed to the handler. Conversely, `getClass()` is a `final` method on `Object` and is not intercepted by the handler. Interface `static` methods are not invoked via instance proxy dispatch.

**Interface default methods:** calls through a proxy still route to the handler; the handler must decide how to handle them, such as delegating to a target implementation or using `InvocationHandler.invokeDefault(...)` (Java 16+) where appropriate. Do not assume default methods automatically run without passing through the handler.

**Proxy type:** callers should hold the proxy in an interface variable. Trying to cast a JDK proxy to a concrete implementation class can throw `ClassCastException`. Methods present only on the implementation and **not on the implemented proxy interfaces** also cannot be called through that interface API.

## 3. How does a subclass proxy intercept calls via overriding?

A subclass proxy can be pictured via the hand-written source code below; a real library generates an equivalent structure in bytecode instead of requiring you to write this class manually:

```java
class Service {
    String work() {
        return "done";
    }
}

class ServiceProxyLike extends Service {
    @Override
    String work() {
        System.out.println("before");
        String result = super.work();
        System.out.println("after");
        return result;
    }
}
```

This is a **structural illustration**, not proof that every library calls `super.work()`. Some proxies invoke the original method on the subclass instance itself, while proxies from other frameworks may forward to a separate target instance or use an interceptor chain. Actual bytecode structure and call paths must be checked against the framework in use.

Core limitations stem from Java's inheritance and overriding rules:

- A **`final class`** cannot be subclassed. Records are implicitly `final`; sealed classes also restrict the list of permitted subclasses.
- A **`final` instance method** cannot be overridden. A pure subclass proxy cannot insert an interceptor by overriding that method.
- A **`private` method** cannot be overridden; a **`static` method** resolves by class and does not participate in virtual dispatch/overriding. Constructors are not overridden methods either.
- `public`/`protected` methods and package-private methods can be overridden **when access and package rules permit**. Module encapsulation, class loaders, and class definition mechanisms can impose further restrictions.
- Instantiation requires a valid strategy: a constructor may be invoked, or a framework may use specialized instantiation techniques. Therefore **you must not deduce** from the phrase "subclass proxy" that the target constructor runs exactly once in one fixed manner.

A `final` method can still be **called** on a subclass instance if inherited and accessible; what is missing is an override point to insert logic. Actual outcomes also depend on how the framework manages state and targets.

## 4. Direct comparison

| Criterion | JDK dynamic proxy | Bytecode-generated subclass proxy |
|---|---|---|
| Proxy type | Generated class extends `Proxy`, implements interfaces | Generated class extends target class |
| Main prerequisite | Needs one or more valid interfaces | Needs an inheritable target class and overridable methods |
| `instanceof` | True for interfaces implemented by the proxy | True for the base class |
| Interception point | Methods on proxy class forward to `InvocationHandler.invoke` | Overridden methods pass through interceptor/logic in subclass |
| Methods only on concrete class | Do not become proxy API unless present on an interface | Can be intercepted if inherited and validly overridden |
| `final` methods on concrete class | Not applicable to interface method selection; cannot proxy concrete class | Cannot be intercepted by overriding |
| `private`/`static` methods on target | Not invoked via interface instance dispatch | Cannot be overridden/intercepted via override |
| Multiple interfaces | Can implement multiple interfaces | Subclass has only one superclass, though it can implement interfaces |
| Real target instance | Optional; decided by handler | Depends on framework: may call `super` or a separate target |
| Proxy creation | Built-in JDK API | Typically uses libraries like Byte Buddy/CGLIB |
| Ideal usage | Interface-based contracts | When concrete class type must be preserved or class lacks interfaces |

Both are governed by JVM rules for type identity, class loaders, modules, and visibility. Both also carry some runtime overhead; you should not claim one mechanism is **always** faster without benchmarking with real workloads and frameworks.

## 5. Java 17+ program demonstrating both paths

The following example runs using only the JDK. The JDK Proxy part uses a real proxy; the subclass part is **hand-written to accurately simulate the override concept**, avoiding requiring extra Byte Buddy/CGLIB dependencies. The example does not pretend the hand-written class is library-generated bytecode.

Save as **`ProxyVsSubclassDemo.java`**:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class ProxyVsSubclassDemo {
    interface Greeting {
        String say(String name);
    }

    static class GreetingImpl implements Greeting {
        @Override
        public String say(String name) {
            return "Hello, " + name;
        }

        public String extra() {
            return "Only available on concrete class";
        }
    }

    static class Service {
        String work() {
            return "work done";
        }

        final String fixed() {
            return "fixed";
        }
    }

    // Illustrates the class structure a bytecode-generation library can produce.
    static class ServiceSubclassDemo extends Service {
        @Override
        String work() {
            System.out.println("[subclass] before");
            String result = super.work();
            System.out.println("[subclass] after");
            return result;
        }
    }

    public static void main(String[] args) {
        GreetingImpl target = new GreetingImpl();

        Greeting interfaceProxy = (Greeting) Proxy.newProxyInstance(
                Greeting.class.getClassLoader(),
                new Class<?>[] {Greeting.class},
                (proxy, method, arguments) -> {
                    System.out.println("[interface] " + method.getName());
                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException e) {
                        throw e.getCause();
                    }
                });

        System.out.println(interfaceProxy.say("An"));
        System.out.println("proxy instanceof Greeting = "
                + (interfaceProxy instanceof Greeting));
        System.out.println("proxy instanceof GreetingImpl = "
                + (interfaceProxy instanceof GreetingImpl));
        System.out.println("proxy superclass is Proxy = "
                + (interfaceProxy.getClass().getSuperclass() == Proxy.class));

        Service subclassProxy = new ServiceSubclassDemo();
        System.out.println(subclassProxy.work());
        System.out.println(subclassProxy.fixed());
        System.out.println("subclass instanceof Service = "
                + (subclassProxy instanceof Service));
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 ProxyVsSubclassDemo.java
java ProxyVsSubclassDemo
```

**Stdout:**

```text
[interface] say
Hello, An
proxy instanceof Greeting = true
proxy instanceof GreetingImpl = false
proxy superclass is Proxy = true
[subclass] before
[subclass] after
work done
fixed
subclass instanceof Service = true
```

**Output explanation:**

1. When calling `interfaceProxy.say("An")`, the JDK proxy class method calls the handler. The handler prints `[interface] say`, then uses Reflection to invoke `GreetingImpl.say`.
2. The proxy implements `Greeting` but does not extend `GreetingImpl`; therefore the two `instanceof` lines are `true` and `false` respectively. Its direct superclass is `Proxy`.
3. `ServiceSubclassDemo` is a subclass of `Service`. `work()` is overridden, prints before/after logs, and calls `super.work()`; this is the **override mechanism** that subclass-generating libraries can produce automatically.
4. `fixed()` is `final` and is not overridden in `ServiceSubclassDemo`. It still returns `fixed`, bypassing the `[subclass]` logs.
5. `subclassProxy` is still a `Service` per `instanceof` and can be passed wherever a `Service` is expected, unlike a JDK interface proxy when code requires the concrete type `GreetingImpl`.

Note: inside the handler, `method.invoke(target, arguments)` can throw `InvocationTargetException`; the example unwraps the cause to preserve the method's real exception. If you replace `target` with `proxy` itself and call the same method again, the handler can recurse infinitely.

## 6. Differences that matter when using frameworks

### No interface, or callers require the concrete type

If an API accepts `Service` as a concrete class and needs to swap the object for a proxy that is still a `Service`, a JDK proxy implementing only `ServiceInterface` (if one exists) generally cannot be cast to `Service`. A subclass proxy can fit **if** `Service` allows inheritance and the methods to intercept are overridable.

Conversely, if the API is already standardized around interfaces, JDK proxy provides a clean contract and uses Java's standard API directly. An implementation with extra methods outside the interface will not automatically be added to the proxy contract.

### Self-invocation cannot be deduced from the word "proxy" alone

Distinguish **Java virtual dispatch** from **how a framework invokes the target**:

- If an instance of the subclass directly invokes an overridden method via `this.work()`, Java can dispatch to the subclass override.
- If a framework places a proxy around a **separate target instance**, an internal `this.work()` call on the target can go straight to the target and **bypass the proxy**.
- Therefore, with Spring AOP or similar frameworks, inspect **the proxy design, interceptor chain, and which object executes the call**, rather than assuming a subclass proxy intercepts every self-invocation.

### Common errors and limitations

| Symptom | Explanation or what to check |
|---|---|
| `ClassCastException` when casting JDK proxy to implementation | Proxy takes identity only from implemented interfaces, does not extend implementation |
| Cannot intercept `final` method | Subclass cannot override; consider an interface proxy, changing the API/method, or another instrumentation technique if designed for it |
| Cannot generate subclass | Check `final`/record/sealed class, suitable constructors, access rights, package, and module |
| JDK proxy encounters a method with checked exceptions | If the handler throws a checked exception outside the interface method's `throws` list, callers may receive `UndeclaredThrowableException` |
| Handler runs unexpectedly when logging proxy | `toString()` and the `Object` methods mentioned above can enter the handler; watch out for recursive loops |
| Concrete-only methods invisible through JDK proxy | Add behavior to the interface if it truly belongs to the public contract |
| Proxy class name or behavior differs across environments | Do not depend on generated class names; check JVM/library versions, class loaders, and module configuration |

Do not use `$Proxy...` names or generator-produced subclass names as stable identifiers. They are implementation details. Use interface/class contracts and appropriate metadata APIs for identification.

## 7. Which mechanism to choose?

- **Prefer JDK dynamic proxy** when the target class already has suitable interfaces, the application programs to interfaces, and you want an intermediary layer for logging, access control, metrics, or remote invocation using standard library APIs.
- **Consider subclass proxy** when callers require the exact concrete class type or the target class has no interfaces, while the methods to intercept are overridable, the class is inheritable, and the environment permits defining classes.
- **Inspect the actual framework** when working with Spring AOP, Hibernate, or mocking libraries: a framework can choose its proxy strategy by configuration and use case; using Byte Buddy/CGLIB does not by itself prove every method is intercepted or every constructor runs the same way.

Ask these questions before choosing: **Are callers using an interface or a class? Are the methods to intercept overridable? Does the proxy wrap a separate target or is it the executing instance itself?** Those three answers usually point to the right direction.

## 8. Self-check

**Q1.** Does JDK dynamic proxy generate bytecode?

**Yes.** It generates a proxy class at runtime; the difference is that this class extends `Proxy` and implements interfaces, rather than extending a concrete implementation.

**Q2.** Can you cast a JDK proxy of `Greeting` to `GreetingImpl` merely because the handler forwards to `GreetingImpl`?

**No.** Having the handler call a target does not alter the proxy object's inheritance hierarchy.

**Q3.** If `Service` is a `final class`, can a library use a standard subclass proxy mechanism?

**No.** Java forbids extending final classes. You may need an interface-based design or a technique other than subclassing.

**Q4.** Can a `final` method run on a subclass instance? Can it be intercepted via overriding?

**It can run if inherited and accessible**, yet **it cannot be intercepted by overriding** in the subclass.

**Q5.** Why does calling `this.someMethod()` sometimes bypass interceptors even when a framework uses class-based proxies?

Because the framework may execute methods on a **separate target instance** or have specific interception rules; you must analyze where dispatch happens rather than guessing from the proxy class shape.

## Standard References

- Java SE 17 API: [`java.lang.reflect.Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html).
- Java SE 17 API: [`java.lang.reflect.InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html).
- Java Language Specification §8.4.8 (overriding), §8.1.1.2 (final classes), §15.12 (method invocation).
- Byte Buddy and CGLIB documentation for the exact version in use when verifying class generation, interceptor, and instantiation strategies.

**Takeaway:** JDK Proxy uses a class implementing interfaces to route calls to `InvocationHandler`; subclass proxy uses a class extending a concrete class, typically intercepting behavior via overriding. Both can generate bytecode at runtime, yet **their type shapes and interception points differ**, so casting rules, method scope, and `final` constraints differ as well.