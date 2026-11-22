# Choosing a Class Loader That Sees the Right Interfaces When Creating a Java Dynamic Proxy

## 1. The practical problem

In Java Reflection, `java.lang.reflect.Proxy` creates an object implementing one or more **interfaces at runtime**, then routes method calls to an `InvocationHandler`. The primary API is:

~~~java
Object proxy = Proxy.newProxyInstance(
        loader,
        new Class<?>[] {Service.class, Auditable.class},
        handler);
~~~

*This is an illustrative snippet, assuming types and variables have already been declared.*

The `loader` parameter is critical: the JVM uses it to define the generated proxy class, and **that loader must see each interface** the proxy implements. An interface may exist in the program yet not be visible from the chosen loader; two classes/interfaces with identical names can still be **two different types** if defined by two different class loaders.

**Lesson goal:** know how to choose the right loader in regular programs and plugin/module environments; understand `Proxy`'s `Class` identity check; verify before creating a proxy; recognize errors caused by the loader, interface rules, and casting.

## 2. What does "seeing the interface" mean precisely?

For each interface `i` and class loader `cl`, a mandatory condition of `Proxy.newProxyInstance` is:

~~~java
Class.forName(i.getName(), false, cl) == i
~~~

Meaning of each part:

- `i` is **the exact `Class<?>` object** of the interface passed in the `interfaces` array.
- `i.getName()` is the *binary name* of the interface.
- `Class.forName(name, false, cl)` attempts to resolve the type with that name using loader `cl`, with `initialize=false` so the class is not actively initialized.
- `== i` requires returning **the exact same `Class` object**, not merely two types with the same name.

If `Class.forName` cannot find the type, it throws `ClassNotFoundException`. If it finds **another interface with the same name**, the `==` comparison is still false. `Proxy.newProxyInstance` rejects cases violating this visibility rule, typically with `IllegalArgumentException`. Note: the class may be resolved through the loader's **delegation** mechanism; `i.getClassLoader() == cl` is not required.

Here is the key distinction:

| Question | Check | Meaning |
| --- | --- | --- |
| Do two interfaces have the same name? | `a.getName().equals(b.getName())` | Compares names only |
| Are two interfaces the same runtime type? | `a == b` | Compares `Class` identity |
| Does loader `cl` see the exact interface `i`? | `Class.forName(i.getName(), false, cl) == i` | Mandatory condition for dynamic proxy |
| Does an object implement `i`? | `i.isInstance(object)` | Runtime type compatibility check |

Java identifies a reference type by its **binary name together with its defining class loader**, not by name alone. The loader chosen for a proxy must therefore see **the exact `Class`** of every input interface.

## 3. Visualizing class loaders in application and plugin environments

Suppose there is an application class loader `AppLoader` and a plugin loader `PluginLoader` delegating to `AppLoader`:

~~~text
                  Bootstrap / Platform
                           ↑
                        AppLoader
                       (SharedApi)
                           ↑ delegates to parent
                       PluginLoader
                       (PluginOnlyApi)

AppLoader:    typically sees SharedApi; does not automatically see PluginOnlyApi
PluginLoader: can see both SharedApi (via parent) and PluginOnlyApi (loaded by itself)
~~~

In this setup, when a proxy is needed for `SharedApi` **and** `PluginOnlyApi`, the plugin loader can be a reasonable choice **if** `Class.forName(..., false, PluginLoader) == i` holds for *both* interfaces. The application loader typically cannot see interfaces that only exist inside the plugin. Conversely, in a system using custom loaders without standard delegation, a loader might reload `SharedApi` into a **same-named copy that is a different type**; in that case do not use it to implement the application's `SharedApi` interface.

There is no rule that "the child loader is always right." Delegation structure, child-first policies, JPMS, and the actual identity of each `Class<?>` determine compatibility.

## 4. Process for choosing a loader

1. **Collect the exact `Class<?>` objects of the interfaces to implement.** For example `Service.class` from the shared API or `pluginApiClass` received from the plugin loader. Avoid reloading an interface by name alone if you already have a trustworthy `Class<?>`.
2. **Select a candidate based on where the interfaces are defined and the delegation mechanism.** If there is only a single regular interface, `Service.class.getClassLoader()` is a simple starting point. With multiple plugin interfaces, check whether the plugin loader sees all interfaces, including shared APIs.
3. **Verify the identity of all interfaces**, using the comparison in section 2. If any interface fails, change the class loading architecture or choose another loader that can see all required types simultaneously.
4. **Check other dynamic proxy constraints.** The interfaces must be valid, module/package access must be permitted, and types appearing in `public` method signatures must also be visible; the proxy may still be rejected even if step 3 passes.
5. **Create the proxy with the verified loader and interface array**, then use the proxy through an interface shared between the caller and the proxy.

A preliminary check can be written as follows:

~~~java
static boolean seesAllInterfaces(ClassLoader loader, Class<?>... interfaces) {
    for (Class<?> iface : interfaces) {
        if (iface == null || !iface.isInterface()) {
            return false;
        }
        try {
            if (Class.forName(iface.getName(), false, loader) != iface) {
                return false;
            }
        } catch (ClassNotFoundException ex) {
            return false;
        }
    }
    return true;
}
~~~

*This is an illustrative method that must be placed inside a Java class; a complete example is in section 5.*

The method above confirms **each input interface is visible and has the same identity**, but **does not prove a proxy can definitely be created**: rules for parameter/return types, methods with matching signatures, non-public interfaces, modules, and `sealed` or `hidden` interfaces still need to be validated by `Proxy`. Class loading/linking errors other than `ClassNotFoundException` may also occur and should not be masked as a plain `false` result.

## 5. Standalone Java 17+ example: one loader sees all, another sees only one interface

In the program below, both `Greeter` and `Tag` are visible to the application loader. `MaskingLoader` is created to **intentionally refuse loading `Tag`**, simulating the scenario of choosing a loader that does not see all interfaces. This loader is for demonstration purposes; in real applications, errors usually come from boundaries between modules/plugins or different classpaths.

Create the file `ProxyLoaderChoiceDemo.java`:

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Proxy;

public class ProxyLoaderChoiceDemo {
    public interface Greeter {
        String greet(String name);
    }

    public interface Tag {
    }

    static final class MaskingLoader extends ClassLoader {
        MaskingLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (name.equals(Tag.class.getName())) {
                throw new ClassNotFoundException(name);
            }
            return super.loadClass(name, resolve);
        }
    }

    static boolean seesAllInterfaces(ClassLoader loader, Class<?>... types) {
        for (Class<?> type : types) {
            if (type == null || !type.isInterface()) {
                return false;
            }
            try {
                if (Class.forName(type.getName(), false, loader) != type) {
                    return false;
                }
            } catch (ClassNotFoundException ex) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        ClassLoader good = Greeter.class.getClassLoader();
        ClassLoader masked = new MaskingLoader(good);
        Class<?>[] interfaces = {Greeter.class, Tag.class};

        System.out.println("good sees all: "
                + seesAllInterfaces(good, interfaces));
        System.out.println("masked sees Greeter: "
                + seesAllInterfaces(masked, Greeter.class));
        System.out.println("masked sees Tag: "
                + seesAllInterfaces(masked, Tag.class));

        InvocationHandler handler = (proxy, method, values) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "GreeterProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == values[0];
                    default -> throw new UnsupportedOperationException();
                };
            }
            if (method.getName().equals("greet")) {
                return "Hello, " + values[0];
            }
            throw new UnsupportedOperationException(method.toString());
        };

        Object created = Proxy.newProxyInstance(
                good, interfaces, handler);
        Greeter greeter = (Greeter) created;

        System.out.println(greeter.greet("Linh"));
        System.out.println("implements Tag: " + (created instanceof Tag));
        System.out.println("proxy loader == good: "
                + (created.getClass().getClassLoader() == good));

        try {
            Proxy.newProxyInstance(masked, interfaces, handler);
            System.out.println("unexpected success");
        } catch (IllegalArgumentException ex) {
            System.out.println("masked rejected: IllegalArgumentException");
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ProxyLoaderChoiceDemo.java
java ProxyLoaderChoiceDemo
~~~

Output:

~~~text
good sees all: true
masked sees Greeter: true
masked sees Tag: false
Hello, Linh
implements Tag: true
proxy loader == good: true
masked rejected: IllegalArgumentException
~~~

Explanation:

- `good` sees both interfaces, so it can generate a proxy class implementing `Greeter` and `Tag`.
- `masked` still sees `Greeter` by delegating to `good`, but rejects `Tag`. **Just one invisible interface** makes the interface array invalid for that loader.
- The proxy created with `good` can be cast to `Greeter` and checked with `instanceof Tag`.
- `InvocationHandler` receives calls through the proxy; the example also handles `equals`, `hashCode`, and `toString` inherited from `Object` to avoid returning wrong data types. The business logic of `greet` is independent of the loader selection rules.

In real applications, do not modify a loader to "hide" an interface like `MaskingLoader`. Choose a loader that **actually sees every exact type**, or design a shared API across the plugin boundary.

## 6. Choosing `getClassLoader()`, context class loader, or system loader?

| Candidate | When to consider | Limitations |
| --- | --- | --- |
| `MyApi.class.getClassLoader()` | One or more interfaces belong to a shared API, and this loader sees all of them | Does not automatically see interfaces that exist only in plugins |
| `pluginInterface.getClassLoader()` | Interface loaded by a plugin; the plugin loader may delegate to see shared APIs | Must verify every interface, including APIs from the application side |
| `Thread.currentThread().getContextClassLoader()` (TCCL) | A framework/container sets a context loader to discover types for the current request | May be `null`, mutated, or see a wrong copy of an interface |
| `ClassLoader.getSystemClassLoader()` | Simple classpath application where all interfaces can be found by the system loader | Not a universal loader for all plugin/container environments |
| `null` (bootstrap loader) | Interfaces can be resolved through the bootstrap loader and other rules permit it | Not suitable for ordinary application interfaces |

**TCCL is a hint about loading context, not a guarantee of correctness.** For example, a plugin may need TCCL to load implementation classes or resources, but the loader used for `Proxy` must still pass the interface identity check. If a framework temporarily switches TCCL, ensure the previous loader is properly restored when work finishes.

Check snippet when considering TCCL:

~~~java
ClassLoader context = Thread.currentThread().getContextClassLoader();
if (!seesAllInterfaces(context, interfaces)) {
    throw new IllegalArgumentException(
            "Context class loader cannot see the requested interfaces");
}
Object proxy = Proxy.newProxyInstance(context, interfaces, handler);
~~~

*This fragment assumes `seesAllInterfaces`, `interfaces`, and `handler` are already defined; other proxy constraints must still be handled.*

When interface `Class<?>` objects are already available, prefer passing them directly rather than assembling names to load through TCCL and hoping to get the right type.

## 7. Same name, different `ClassLoader`: a hard-to-spot bug in plugin systems

Suppose both the application and a plugin **separately load** the bytecode of `com.example.api.Service`:

~~~text
AppLoader    → Class A: com.example.api.Service
PluginLoader → Class B: com.example.api.Service

A.getName().equals(B.getName()) == true
A == B                             == false
~~~

This **illustrates two distinct runtime types**, not class names from a standalone example program. If `PluginLoader` finds `B` when looking up `Service`, while you pass `A` into `Proxy.newProxyInstance`, the condition `Class.forName(A.getName(), false, PluginLoader) == A` fails. Even if a proxy implementing `B` is created, application code expecting `A` still cannot cast that proxy to `A`: sharing a name does not create a type relationship.

Common organizational approaches:

- Place the shared contract interface in a library/API loaded **once** by a shared loader; the plugin loader delegates to the shared copy rather than bundling its own copy.
- If the plugin has its own interface, pass the actual `Class<?>` that the plugin uses, then choose a loader that resolves both the plugin interface and the shared contract accurately.
- If the required interfaces live in two loader regions that cannot see each other, **there is no magic `loader` parameter** that can create a proxy for both. You need to adjust the loader structure, split proxies, or use a forwarding layer via a shared API.

The `ClassLoader` passed to `Proxy.newProxyInstance` **can differ** from the loader that directly defined some interfaces in the list: delegation can return the parent loader's exact `Class`. The requirement is that **resolved identities match**, not that all `getClassLoader()` values be identical.

## 8. Other constraints often mistaken for class loader errors

According to the Java 17+ `Proxy.newProxyInstance` API:

- Every element of the `interfaces` array must be a **valid interface**, not a class, primitive, or `sealed` or `hidden` interface; duplicate entries of the same `Class<?>` are forbidden.
- **Every reference type used in the signatures of `public` methods** of the interfaces (including inherited methods) must also be visible by name through the chosen loader. Checking only the name of the interface itself is not enough.
- With multiple **non-`public`** interfaces, all must belong to **the same package and module**, be defined by the supplied loader, and satisfy access conditions. A loader merely seeing them is not enough to bypass this restriction.
- Methods from multiple interfaces with the same name and parameter list must have **compatible return types** under proxy rules. Interface order also matters when there are matching method signatures.
- In applications using the **Java Platform Module System (JPMS)**, Java has rules determining the package/module containing the proxy class, sometimes generating the proxy in a *dynamic module*. Avoid assuming you can reflectively access a `public` constructor of the proxy class from an arbitrary module; use `Proxy.newProxyInstance` as the designed API.

Common errors:

| Symptom | Diagnostic direction |
| --- | --- |
| `IllegalArgumentException` from `newProxyInstance` | Check whether interfaces are valid, non-duplicate, identity-visible through the loader, types in signatures, and package/module restrictions |
| `ClassNotFoundException` when testing `Class.forName` | The loader cannot find a type by that name |
| `ClassCastException` after proxy creation | Caller may be using a different `Class`, or the proxy does not implement the expected interface |
| `IllegalAccessException` when trying to instantiate the proxy class manually | May be due to module access rules on the proxy; use `newProxyInstance` |
| `NoClassDefFoundError` or other linkage errors | Check dependencies and loading/linking of referenced types; this is not necessarily an interface identity comparison error |

Do not apply mechanical workarounds like `setAccessible(true)`, reordering interfaces arbitrarily, or unchecked casts. Those actions do not make two distinct `Class` objects become one.

## 9. How to diagnose when a proxy fails to be created

When hitting an error at a framework/plugin boundary, record the following values for **each interface**:

~~~java
for (Class<?> i : interfaces) {
    System.out.println("interface: " + i.getName());
    System.out.println("defined by: " + i.getClassLoader());
    System.out.println("module: " + i.getModule());
    try {
        Class<?> resolved = Class.forName(i.getName(), false, loader);
        System.out.println("same Class: " + (resolved == i));
        System.out.println("resolved by: " + resolved.getClassLoader());
    } catch (ClassNotFoundException ex) {
        System.out.println("not visible by name");
    }
}
~~~

*This fragment uses existing `loader` and `interfaces` variables. The name returned by `getName()` is insufficient to conclude types are identical; the `same Class` result answers the critical question.*

Also inspect the loaders of types appearing in parameters/return types of `public` methods, module relationships, whether interfaces are `public`, and whether multiple copies of the contract library exist in the classpath/plugin. Enable only appropriate logging/diagnostics; do not depend on generated proxy class names as a stable API.

## 10. Knowledge self-check

1. What does `Proxy.newProxyInstance` require for each interface `i` with loader `cl`? **`Class.forName(i.getName(), false, cl) == i`.**
2. If `AppLoader` defines the shared API, and `PluginLoader` delegates to its parent and loads the plugin interface itself, which loader is likely able to create a proxy for both? **`PluginLoader`, provided the identity check and other constraints all pass.**
3. `interfaceA.getName().equals(interfaceB.getName())` is `true`, but `interfaceA == interfaceB` is `false`. Can they be treated as the same type? **No.** Matching names do not guarantee the same loader identity.
4. Is TCCL always the right choice? **No.** You must verify it sees every exact interface.
5. If a loader sees all exact interfaces, is proxy creation guaranteed to succeed? **Not necessarily.** There are still types in public method signatures, `non-public` interface/module constraints, methods with matching signatures, `sealed`/`hidden`, and so on.
6. Why can `ClassCastException` occur after a proxy is successfully created? **The casting code may reference an interface with a different identity or an interface not implemented by the proxy.**

## 11. Conclusion

When creating a dynamic proxy, choose **a class loader that resolves every interface to the exact same `Class` identity**, then verify type, package, and module constraints. In simple programs, the API interface's loader is usually sufficient. In frameworks/plugins, the decision must be based on the actual class loading structure and delegation mechanism. The condition `Class.forName(i.getName(), false, loader) == i` is a reliable starting check to avoid confusing "same name" with "same type".

References:
- [Java SE 21 — `Proxy.newProxyInstance` and interface restrictions](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 21 — `Class.forName` and class identity](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [Java SE 21 — `ClassLoader` and class loading mechanism](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html)
