# 10.3 Conditions on public, non-public, sealed interfaces and type visibility

**Module:** Java Advance - dynamic-runtime  
**Parent topic:** 10. Dynamic proxies  
**Demonstrated version:** Java 17 and above; main APIs: `java.lang.reflect.Proxy` and `InvocationHandler`.

## Objectives

`Proxy.newProxyInstance(loader, interfaces, handler)` does not accept every set of interfaces. The JVM needs to generate a class that can actually implement each interface; the generated class must also obey **Java accessibility rules, type identity by class loader, the Java Platform Module System (JPMS), and sealed hierarchies**.

After this lesson, you will be able to:

1. Explain why JDK dynamic proxies **only implement interfaces**, and why an interface must be **non-hidden, non-sealed**, with no duplicate `Class<?>`.
2. Distinguish between `public` interfaces and **non-public** interfaces (e.g., package-private): when they can be used together and why non-public interfaces must reside in the **same package, same module, and appropriate defining loader**.
3. Understand the difference between **type visibility by name through a class loader** and **type accessibility under Java/JPMS semantics**.
4. Know the rules for checking types that appear in **public method signatures**, including inherited methods; and the constraints on return types when multiple interfaces declare the same signature.
5. Read the rules for selecting the **package/module** of the proxy class when the interface package is exported/opened or closed.
6. Try practical, executed Java 17 examples: succeeding with `public`/package-private, failing with `sealed`/duplicate/invisible loader/different packages/invalid return types, and the case of a named module with a `public` interface whose **package is not exported**.
7. Design a stable public SPI without depending on the name or access rights of the generated proxy class.

## 1. What does a JDK dynamic proxy actually create?

Typical API:

~~~java
Object proxy = Proxy.newProxyInstance(
        loader,
        new Class<?>[]{SomeInterface.class},
        handler);
~~~

This is an **illustrative snippet** that requires `loader`/`handler` variables and an actual interface. `Proxy` creates a **new class at runtime** that extends `java.lang.reflect.Proxy` while implementing the provided list of interfaces. Each instance is bound to an `InvocationHandler`; when an interface method is called on the proxy, the JVM forwards the call to `handler.invoke(proxy, method, args)`.

Unlike bytecode subclassing libraries, **JDK dynamic proxies are not used to extend an arbitrary business class**. Passing `String.class`, `ArrayList.class`, or an implementation class instead of an interface is an error.

Diagram:

~~~text
Caller
  |
  | call Greeting.greet("An")
  v
Proxy instance: implements Greeting
  |
  | forward to InvocationHandler.invoke(proxy, Method, Object[])
  v
Handler
  | execute logic / forward / log / cache
  v
Return value to caller, or exception
~~~

The proxy class is **not** `Greeting` implemented beforehand in source code, yet it can still be cast to `Greeting` when one of the proxy interfaces is `Greeting`. The generated class name, package, and module can vary depending on the environment and JDK rules. Do not program against names like `$Proxy0` or specific dynamic module names.

**Two independent questions:** (1) are the input interfaces **valid for generating a proxy class**? (2) does the caller code have **permission to import, cast, reflect on, or invoke methods** on the involved types? Just because a proxy can be created does not mean every caller can see all of its types.

## 2. Checklist of conditions that `Proxy.newProxyInstance` must satisfy

Java 17 specifies the following constraints; violations typically throw `IllegalArgumentException` at the time the proxy is requested:

| Condition | Why is it needed? | Example causing an error |
| --- | --- | --- |
| Every element in `interfaces` is an **interface**, **non-hidden**, and **non-sealed** | The generated class must be allowed to directly implement the interface | `String.class`, a `sealed` interface |
| No duplicate `Class<?>` object in the array | Each proxy interface may appear only once | `{Greeting.class, Greeting.class}` |
| Every interface is **visible by name** through the chosen `loader` | The proxy must reference the exact runtime identity of the interface | An isolated loader that cannot load `Greeting` |
| All types appearing in **public method signatures**, including inherited methods, are visible through `loader` | The proxy bytecode needs to describe those parameter/return types | A method taking a class only visible through another loader |
| **Non-public** interfaces must be in the **same package and module**, defined by the given loader; that module must be able to access the relevant interface types | A non-public proxy class has only one valid package/module location | Two package-private interfaces in two different packages |
| Methods with the same name and parameter type list must have compatible return types | A proxy method cannot be valid with two conflicting return types | `Number result()` and `String result()` |
| Does not exceed classfile/JVM limits | The generated class needs a valid structure | Exceeding the JVM limit on the number of interfaces |

In addition to the table, if `interfaces` or an element in the array is `null`, or `handler` is `null`, a `NullPointerException` is thrown. Security rules may involve `SecurityManager` in environments that still use this mechanism, but it does not replace the fundamental conditions.

**Duplicate signature return types:** if multiple interfaces declare a method with the same name and parameter signature:
- When the return is primitive or `void`, the corresponding methods must have the **exact same return type**.
- When the return is a reference type, there must be **one return type assignable to all the remaining return types** (covariant return). `String` and `CharSequence` are compatible; `String` and `Number` are incompatible.
- Checking return type assignability alone is not enough to guarantee correct handler logic; when methods overlap, **interface order** affects which `Method` is passed to the handler.

Requesting a proxy with a different set or order of interfaces can result in a different proxy class; the interface array should not be treated as an unordered set.

## 3. `public` interfaces, package-private interfaces, and access boundaries

### 3.1. All interfaces are public

Example:

~~~java
public interface Greeting {
    String greet(String name);
}
~~~

If `Greeting.class` is visible through the loader, is not sealed/hidden, the types in public method signatures are also visible, and all other conditions are met, `Proxy.newProxyInstance` can create a public proxy class.

However, **`public` is only one condition**:

- On the Java classpath / unnamed module, packages are governed by the class loader model and traditional Java visibility.
- With **named modules**, a `public` interface can still reside in a package that is **not `exports`-ed**. Code in another module cannot directly `import` that interface simply because it has the `public` modifier.
- A proxy may be created under special JPMS mechanisms even when the caller has no compile-time permission to import the interface. Yet the caller must still have an **allowed** way to work with the value, such as an exported public contract; one cannot infer from the ability to create a proxy that all internal members can be invoked.

### 3.2. Having non-public interfaces

A top-level **package-private** interface:

~~~java
package lab.proxy;

interface LocalInternal {
    String identity();
}
~~~

This illustrative snippet compiles when saved in the proper package; in the program in section 6, it resides in the same file as the public class. This interface **does not have the `public` modifier**; code outside the corresponding runtime package cannot import or use the type directly as a public API.

If a proxy array contains `LocalInternal.class`, the proxy class will have **non-public** access. With multiple non-public interfaces, all of them must:

1. Be in the **same package**.
2. Be in the **same module**.
3. Be defined according to the class loader rules required by `Proxy`.
4. Have access to the relevant types so the proxy class can actually implement those interfaces.

**It is possible to combine** a public interface with a package-private interface in the same call. The access level of the generated proxy class will follow the **least public** interface, meaning **non-public**. Callers can still invoke through a public interface they can see, but cannot by default access the proxy class by name or use its constructor via Reflection from anywhere.

Non-public interfaces **in two different packages** cannot be placed together in a single JDK proxy class, even if Java source code can obtain both `Class<?>` objects via Reflection. The reason is not that `Proxy` dislikes mixing packages syntactically, but that a generated class **belongs to only one package and module**, so it cannot simultaneously satisfy all access rules for two non-public interfaces in different packages.

### 3.3. `public interface` vs. `public proxy class`

There are two layers of access rights to distinguish:

- **Rights on the interface:** whether the caller can reference the type name, import, cast, and call methods according to Java/module rules.
- **Rights on the generated proxy class:** the package/module chosen by `Proxy` determines whether the caller is allowed to access the class itself, its public constructor, or reflect on it.

Even when the generated class is `public`, its package may **not be exported** to the caller in JPMS. `Modifier.isPublic(proxy.getClass().getModifiers())` is **not sufficient** to conclude that a caller can call `Constructor.newInstance` or `Class.forName` and use it directly. The named module lab will prove this.

## 4. `sealed` and `non-sealed`: the boundary of dynamic proxies

Since Java 17, `sealed interface` allows an author to **directly restrict which types are permitted to extend/implement** it via a `permits` list. A JDK proxy class generated at runtime cannot arbitrarily be added to the list of permitted implementations. Therefore the `Proxy` condition is very clear: **an interface passed directly in the `interfaces` array must be non-sealed**.

Example:

~~~java
public sealed interface Restricted permits AllowedRestricted {
    String run();
}
public static final class AllowedRestricted implements Restricted {
    public String run() { return "direct"; }
}
~~~

This is an illustrative snippet **inside an enclosing class** (as in section 6), not a standalone file. For the `Restricted` interface, the equivalent call:

~~~java
Proxy.newProxyInstance(
        Restricted.class.getClassLoader(),
        new Class<?>[]{Restricted.class},
        handler);
~~~

will throw `IllegalArgumentException`. Providing a valid `InvocationHandler` does not bypass the sealed restriction.

**Important distinction:** "Cannot pass a sealed interface directly into proxy interfaces" **does not mean** "cannot have a proxy that satisfies `instanceof` for a sealed superinterface." Consider this valid hierarchy:

~~~text
sealed Parent
    |
    +-- permitted non-sealed Child
                         |
                         +-- generated proxy implements Child
~~~

If `Child` is a **non-sealed interface** permitted by `Parent` to extend it, a proxy class can **directly implement Child**, and thereby **indirectly** implement `Parent`. This is a normal consequence of sealed hierarchy rules: what is controlled are the **direct subclasses/subinterfaces** of `Parent`. The standalone runnable example in section 7 confirms this behavior.

`final`, `sealed`, and `non-sealed` classes/interfaces each have distinct meanings:
- A `final class` cannot be subclassed; it is **not an interface**, so it cannot be passed into `interfaces`.
- A `sealed interface` is an interface, but is rejected by the `Proxy` API when specified directly.
- A `non-sealed interface` can serve as a proxy interface if the remaining conditions are satisfied.
- A normal interface without a sealed declaration (i.e., non-sealed in the sense of being unrestricted) is also valid; the `non-sealed` keyword syntax only applies when reopening an appropriate sealed relationship.

## 5. "Type visibility" through a class loader does not mean "accessible"

### 5.1. Runtime Class identity check

For each interface `i` and class loader `cl` passed to `Proxy`, Java 17 requires:

~~~java
Class.forName(i.getName(), false, cl) == i
~~~

This is a **check expression**, not a standalone runnable file. The comparison uses **`==` on `Class<?>` objects**, not just comparing the string `i.getName()`.

Why?

- The runtime identity of a class/interface type depends on both its **binary name** and its **defining class loader**; two different loaders can define two types with the same name that are **not assignable to each other**.
- The loader given to the proxy must **find the exact type that was passed**. It can use **parent delegation**; it does **not require** `i.getClassLoader() == cl`, because a child loader can see an interface defined by a parent loader.
- `Class.forName(..., false, loader)` uses `false` so as **not to actively initialize the class** during name lookup; this differs from instantiating objects or executing the handler.
- Having a `Class<?>` obtained from a plugin loader **does not guarantee** that the app loader sees that same Class object.

For example, `new ClassLoader(null) {}` in the lab creates a loader with no application parent. It cannot find `lab.proxy.ProxyVisibilityDemo$Greeting`; `Proxy.newProxyInstance` rejects it due to the visibility condition, even though `Greeting.class` is already available in the calling code.

### 5.2. Must see **all types in public method signatures**

Not just the interface itself. Example:

~~~java
public interface ShippingApi {
    Receipt ship(Order request);
}
~~~

This is **signature pseudocode** because `Receipt`/`Order` are not declared. If `Order` or `Receipt` is defined by a loader such that the loader chosen for the proxy cannot find the **exact Class object by name**, the proxy may fail to be created.

The rule covers **public method signatures of the interface and its inherited superinterfaces**, not only methods written directly in the current file.

- First, pay attention to the **erased** types in the runtime descriptor (for example, generic `List<Order>` has a raw descriptor type of `List`; other generic information is a separate metadata layer).
- **Parameter** and **return types** in public signatures must be visible by name. Do not just check `interface.getName()` and assume the entire API can be proxied.
- With JPMS, a type may be **visible by name in the loader** while its **package is not exported** to the caller. Proxy's module rules can arrange the necessary permissions for the **dynamic proxy module**, which does not mean the external application can automatically import that type.
- When a plugin uses its own class loader, carrying a "name copy" of an interface is not enough to cast to the host interface. SPI designs typically place contracts in a deliberately shared module/loader.

### 5.3. Do not use class loaders as a substitute for authorization

Loaders solve **class lookup/identity** and help establish module/class boundaries; they are not inherently a sandbox. Proxies/handlers run **inside the application process** and can execute logic with the process's privileges. When plugins are untrusted, you need capability control, data validation, resource management, and process isolation when necessary.

## 6. Java 17 Demo: public, package-private, and rejected cases

The demo consists of two files in two packages. The first file contains a public interface, a package-private interface, a sealed interface, and conflicting return signature cases. The second file is used to prove that **two non-public interfaces in two different packages cannot be proxied together**.

**Directory structure** (from an empty project directory):

~~~text
src/
  lab/
    proxy/
      ProxyVisibilityDemo.java
    other/
      ForeignInternal.java
~~~

### 6.1. `src/lab/proxy/ProxyVisibilityDemo.java`

~~~java
package lab.proxy;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

interface LocalInternal {
    String identity();
}

public final class ProxyVisibilityDemo {
    public interface Greeting {
        String greet(String name);
    }

    public sealed interface Restricted permits AllowedRestricted {
        String run();
    }

    public static final class AllowedRestricted implements Restricted {
        public String run() { return "direct"; }
    }

    public interface NumberResult { Number result(); }
    public interface StringResult { String result(); }

    private static final InvocationHandler HANDLER = (proxy, method, args) -> {
        return switch (method.getName()) {
            case "greet" -> "Hello " + args[0];
            case "identity" -> "internal";
            case "toString" -> "proxy-object";
            default -> throw new UnsupportedOperationException(method.getName());
        };
    };

    private static Object create(ClassLoader loader, Class<?>... interfaces) {
        return Proxy.newProxyInstance(loader, interfaces, HANDLER);
    }

    private static void rejected(String label, Runnable attempt) {
        try {
            attempt.run();
            System.out.println(label + "=unexpected-success");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader appLoader = ProxyVisibilityDemo.class.getClassLoader();

        Greeting publicProxy = (Greeting) create(appLoader, Greeting.class);
        System.out.println("publicCall=" + publicProxy.greet("An"));
        System.out.println("publicProxy="
                + Modifier.isPublic(publicProxy.getClass().getModifiers()));
        System.out.println("isProxy=" + Proxy.isProxyClass(publicProxy.getClass()));

        Object mixed = create(appLoader, Greeting.class, LocalInternal.class);
        System.out.println("mixedGreeting=" + ((Greeting) mixed).greet("Binh"));
        System.out.println("mixedInternal=" + ((LocalInternal) mixed).identity());
        System.out.println("mixedProxyPublic="
                + Modifier.isPublic(mixed.getClass().getModifiers()));
        System.out.println("samePackage=" + mixed.getClass().getPackageName()
                .equals(LocalInternal.class.getPackageName()));
        System.out.println("sameModule=" + (mixed.getClass().getModule()
                == LocalInternal.class.getModule()));

        rejected("sealed", () -> create(appLoader, Restricted.class));
        rejected("duplicate",
                () -> create(appLoader, Greeting.class, Greeting.class));
        rejected("notInterface", () -> create(appLoader, String.class));
        rejected("hiddenByLoader",
                () -> create(new ClassLoader(null) {}, Greeting.class));

        Class<?> foreign = Class.forName("lab.other.ForeignInternal");
        rejected("differentPackages",
                () -> create(appLoader, LocalInternal.class, foreign));
        rejected("conflictingReturns",
                () -> create(appLoader, NumberResult.class, StringResult.class));
    }
}
~~~

### 6.2. `src/lab/other/ForeignInternal.java`

~~~java
package lab.other;

interface ForeignInternal {
    void ping();
}
~~~

### 6.3. Compile and run

From the directory containing `src/`:

~~~bash
javac --release 17 -d out src/lab/proxy/ProxyVisibilityDemo.java src/lab/other/ForeignInternal.java
java -cp out lab.proxy.ProxyVisibilityDemo
~~~

The commands above work in a terminal with JDK 17+ on Windows, Linux, and macOS when no extra shell syntax is inserted. `javac` can create the `out` directory if it does not already exist.

**Exact stdout** of the compiled/executed demo:

~~~text
publicCall=Hello An
publicProxy=true
isProxy=true
mixedGreeting=Hello Binh
mixedInternal=internal
mixedProxyPublic=false
samePackage=true
sameModule=true
sealed=IllegalArgumentException
duplicate=IllegalArgumentException
notInterface=IllegalArgumentException
hiddenByLoader=IllegalArgumentException
differentPackages=IllegalArgumentException
conflictingReturns=IllegalArgumentException
~~~

**Explanation:**

- `Greeting` is `public`, non-sealed, and visible through the app loader; `publicCall` succeeds.
- `Proxy.isProxyClass(...) == true` confirms this is genuinely a JDK proxy class. Do not replace it with checking whether the name contains `$Proxy`.
- `Greeting + LocalInternal` in the same package produces a non-public proxy class; that class resides in the package and module of the non-public interface; `Greeting.greet` and `LocalInternal.identity` can still be called from code with access.
- `Restricted` is a sealed interface, so it is rejected. This is a restriction checked by the API, not a `ClassCastException` from casting after creating an instance.
- Duplicate interfaces, a non-interface class, a loader that cannot see the name, and two non-public interfaces in two different packages each violate independent conditions.
- `NumberResult.result()` returns `Number` and `StringResult.result()` returns `String`; neither reference return type is assignable to the other, so the combination is rejected.
- In `rejected`, we only print the **error type** rather than hardcoding `Exception.getMessage()` because messages can differ across JDKs; the lines above are stable for the example.

To see the actual cause during experimentation, temporarily log `expected.getMessage()` or the stack trace, but do not rely on message content as an API contract to drive application logic.

## 7. Java 17 Demo: sealed parent and non-sealed child

A sealed parent can permit a **non-sealed subinterface** to extend it. A proxy created from the **non-sealed subinterface** is valid and also satisfies `instanceof` for the sealed parent because the extends relationship is permitted.

**Standalone runnable file:** `SealedParentCheck.java`

~~~java
import java.lang.reflect.Proxy;

public class SealedParentCheck {
    public sealed interface Parent permits Child {
        String value();
    }

    public non-sealed interface Child extends Parent { }

    public static void main(String[] args) {
        Object instance = Proxy.newProxyInstance(
                Child.class.getClassLoader(),
                new Class<?>[]{Child.class},
                (p, m, a) -> "ok");

        System.out.println("childResult=" + ((Child) instance).value());
        System.out.println("parentInstance=" + (instance instanceof Parent));
    }
}
~~~

Compile and run (in the directory containing the file):

~~~bash
javac --release 17 SealedParentCheck.java
java SealedParentCheck
~~~

Verified stdout:

~~~text
childResult=ok
parentInstance=true
~~~

Distinguish the two arrays passed to `Proxy`:

~~~java
new Class<?>[]{Parent.class} // Rejected: Parent is sealed.
new Class<?>[]{Child.class}  // Valid: Child is non-sealed.
~~~

These are **two illustrative expressions**, not complete variable declarations. Even the valid case can still be rejected if other conditions (loader visibility, conflicting return types, etc.) are violated.

## 8. Named modules (JPMS): public interface in an unexported package

Since Java 9, the publicness of an interface is **not enough** to determine the accessibility of its package from another module. The package/module selection rules for a generated proxy, according to Java 17, are:

| Interface set | Packages containing the interfaces | Package/module of the generated proxy |
| --- | --- | --- |
| All interfaces are `public` | All packages are **unconditionally exported or opened** | **Public** proxy class in an **unconditionally exported, non-open** package; the package and module names are not guaranteed |
| At least one **non-public** interface | All packages are unconditionally exported/opened | **Non-public** proxy class in the exact package/module of the non-public interfaces; all non-public interfaces must be in the same package/module |
| All interfaces are `public` | At least one package is **neither unconditionally exported nor opened** | **Public** proxy class in a **non-exported, non-open** package belonging to a **dynamic named module**; the package/module names are not guaranteed |
| At least one **non-public** interface | Has a package not unconditionally exported/opened | **Non-public** proxy class in the package/module of the non-public interfaces, if all general conditions are valid |

**Reading the table properly:**

- The words "exported/open" in this section mean **unqualified exports/opens**, i.e., open to all modules. `exports p to friend;` or `opens p to mapper;` are **qualified**, and do not count as an unqualified export/open.
- A package that is `opens` but not `exports` allows runtime Reflection access under module rules, **not** direct compile-time API import from another module.
- A **`public` proxy class** in a dynamic module with a **non-exported** package still does not grant arbitrary callers permission to use its public constructor. The JDK recommends **`Proxy.newProxyInstance`** to create instances.
- Generated module names like `jdk.proxy1` and proxy class names are not contracts. Do not make the application depend on those names.
- A dynamic module has mechanisms to read the modules containing the interfaces and types in public signatures, and can be granted appropriate exports so the generated proxy can use those types. This does not export the entire package to the host or the entire application.

### 8.1. Hands-on with two named modules

Create the tree:

~~~text
module-src/
  demo.hidden/
    module-info.java
    demo/hidden/api/HiddenService.java
  demo.host/
    module-info.java
    demo/host/Main.java
~~~

**`module-src/demo.hidden/module-info.java`**

~~~java
module demo.hidden { }
~~~

**`module-src/demo.hidden/demo/hidden/api/HiddenService.java`**

~~~java
package demo.hidden.api;

public interface HiddenService {
    String value();
}
~~~

The `HiddenService` interface is public, but the package `demo.hidden.api` is **not exported** in `module-info.java`.

**`module-src/demo.host/module-info.java`**

~~~java
module demo.host { }
~~~

The host does not `requires demo.hidden` because the example only looks up the class by name via Reflection; use `--add-modules demo.hidden` at runtime to ensure this module is in the module graph.

**`module-src/demo.host/demo/host/Main.java`**

~~~java
package demo.host;

import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

public final class Main {
    public static void main(String[] args) throws Exception {
        ClassLoader loader = Main.class.getClassLoader();
        Class<?> contract = Class.forName(
                "demo.hidden.api.HiddenService", false, loader);

        Object proxy = Proxy.newProxyInstance(
                loader,
                new Class<?>[]{contract},
                (instance, method, values) -> "ok");
        Class<?> generated = proxy.getClass();

        System.out.println("interfacePublic="
                + Modifier.isPublic(contract.getModifiers()));
        System.out.println("interfaceExported="
                + contract.getModule().isExported(
                        contract.getPackageName(), Main.class.getModule()));
        System.out.println("proxyPublic="
                + Modifier.isPublic(generated.getModifiers()));
        System.out.println("proxyNamedModule="
                + generated.getModule().isNamed());
        System.out.println("proxyExported="
                + generated.getModule().isExported(
                        generated.getPackageName(), Main.class.getModule()));

        Constructor<?> ctor = generated.getConstructor(InvocationHandler.class);
        try {
            ctor.newInstance((InvocationHandler) (p, m, a) -> "no");
            System.out.println("directConstructor=allowed");
        } catch (IllegalAccessException expected) {
            System.out.println("directConstructor=blocked");
        }
    }
}
~~~

**Bash (Linux/macOS)** — from the directory containing `module-src/`:

~~~bash
javac --release 17 --module-source-path module-src -d modules $(find module-src -name '*.java')
java --module-path modules --add-modules demo.hidden --module demo.host/demo.host.Main
~~~

**PowerShell (Windows)** — equivalent, using a source collection instead of `find`:

~~~powershell
$files = Get-ChildItem module-src -Recurse -Filter '*.java' |
    Select-Object -ExpandProperty FullName
javac --release 17 --module-source-path module-src -d modules $files
java --module-path modules --add-modules demo.hidden --module demo.host/demo.host.Main
~~~

**Verified stdout when running the exact two modules above:**

~~~text
interfacePublic=true
interfaceExported=false
proxyPublic=true
proxyNamedModule=true
proxyExported=false
directConstructor=blocked
~~~

**Explanation of results:**

1. `interfacePublic=true` because `HiddenService` is a public interface. However, `interfaceExported=false` for module `demo.host`: host code **cannot directly import/call** the interface in normal Java source.
2. `Class.forName(...)` still retrieves the `Class<?>` object once the module is resolved and the loader sees the name. **Ability to load by name does not equal ability to access members**.
3. `Proxy.newProxyInstance` can create an instance from a public interface in an unexported package, but the generated class is placed in a **dynamic named module** in an unexported package, so `proxyPublic=true` **does not contradict** `proxyExported=false`.
4. `generated.getConstructor(InvocationHandler.class)` can find the public constructor; **invoking the constructor via Reflection** from the host is still blocked because the package containing the generated class is not exported to the host.
5. `Proxy.newProxyInstance` returned the proxy object successfully. This is the official way to create proxies instead of trying to call the generated proxy class's constructor.

**Do not infer that the host will have permission to call `HiddenService.value()` just because the instance was created.** This lesson illustrates proxy creation/placement, not a public API permitted for use across a module boundary. If consumers need to call typed methods, the library should export an appropriate SPI contract.

## 9. How to inspect a set of interfaces before requesting a proxy

For a plugin manager or framework, it is good practice to have an intentional inspection step to report clear errors. You do not necessarily need to reimplement all of `Proxy`'s logic, but you should log what is valuable for developers.

### 9.1. Information to inspect

For each `Class<?> itf`:

~~~java
System.out.println("name=" + itf.getName());
System.out.println("interface=" + itf.isInterface());
System.out.println("sealed=" + itf.isSealed());
System.out.println("hidden=" + itf.isHidden());
System.out.println("public=" + java.lang.reflect.Modifier.isPublic(itf.getModifiers()));
System.out.println("package=" + itf.getPackageName());
System.out.println("module=" + itf.getModule());
System.out.println("loader=" + itf.getClassLoader());
~~~

This is an **illustrative snippet in a scope that has `itf`**, not a standalone file. Avoid printing full system paths or sensitive data into production logs.

Further checks:

- Are there duplicate interfaces **by `Class<?>` object**? `Set<Class<?>>` is useful, but do not accidentally reorder the interfaces when order matters.
- Can the chosen loader resolve **the interface itself** and all **types in public method signatures**?
- If there are non-public interfaces, do they share the same package/module/loader and required access conditions?
- Do methods with the same name and parameter signature have compatible return types?
- With named modules, how are the packages exported/opened, and which case will the generated proxy module fall into?
- Does the consumer actually need Reflection on the generated proxy class, or does it only need an instance typed to a public interface?

### 9.2. Loader visibility check code (illustrative snippet)

~~~java
static boolean visibleByName(ClassLoader loader, Class<?> type) {
    try {
        return Class.forName(type.getName(), false, loader) == type;
    } catch (ClassNotFoundException e) {
        return false;
    }
}
~~~

This method needs to be placed **inside a Java class**. It illustrates one of the important conditions, **not a complete validator**: you still need to check sealed/hidden, duplicates, non-public package/module, types in signatures, compatible returns, and JVM limits. Do not replace all of `Proxy`'s checks with a custom helper that does not cover module cases.

### 9.3. Solution selection flow

~~~text
Need to create a proxy for a concrete class?
  -> JDK dynamic proxy does not subclass business classes; choose an interface/adapter
      |
      v
Is the interface non-hidden and non-sealed?
  -> No: remove that interface from the proxy list or design another contract
      |
      v
Does the loader see the interfaces and types in public signatures?
  -> No: fix the module/loader topology, share the SPI, or eliminate version mismatches
      |
      v
Are there non-public interfaces?
  -> Yes: verify valid same package/module/loader
      |
      v
Are return types of duplicate methods compatible?
  -> No: split the proxy or adjust the contract
      |
      v
Proxy.newProxyInstance(...)
  -> Return via a valid public interface; do not rely on the proxy class name
~~~

## 10. Common pitfalls and how to handle them

| Symptom | Common cause | Diagnostic direction |
| --- | --- | --- |
| `IllegalArgumentException` with a sealed interface | The directly passed interface has `isSealed() == true` | Use a valid non-sealed contract, or write an explicit adapter/implementation |
| `IllegalArgumentException` with a regular class | `interfaces` contains a `Class<?>` that does not represent an interface | Check `isInterface()` first |
| `IllegalArgumentException` when using a custom loader | The loader cannot resolve the interface's exact `Class<?>` object | Check `Class.forName(..., false, loader) == itf` |
| Interface resolves, yet proxy still fails | A type in public method signatures is not visible through the loader | Check public methods including inherited ones and their parameter/return types |
| Two package-private interfaces cannot be combined | They belong to different packages or modules | Split the proxy or publish an appropriate public SPI |
| A proxy from multiple interfaces with same-named methods is rejected | Incompatible return types | Compare return assignability; split contracts if needed |
| `proxy instanceof API` is true, but caller cannot cast to internal interface | The internal interface is not accessible to the caller | Return/call via a public exported interface; do not force use of internal ones |
| Proxy class is `public`, yet constructor Reflection is blocked | The generated class is in a non-exported package of a dynamic module | Use `Proxy.newProxyInstance`; do not try to open the constructor |
| `Class.forName` finds the interface, yet direct import fails | Visibility by name differs from Java/JPMS accessibility | Check `module-info.java` and package exports |
| `ClassCastException` when casting proxy to an interface "with the same name" | Two loaders defined two different `Class<?>` objects | Unify where the SPI/interface is defined; check identity |
| `UndeclaredThrowableException` when handler throws a checked exception | The checked exception is not permitted by the interface method | Choose an exception policy matching the signature |
| Proxy method returning primitive throws `NullPointerException` | Handler returned `null` for a primitive method | Handler must return the corresponding non-null wrapper |

Not all `IllegalArgumentException`s from `Proxy` are the same. Log the **list of interfaces in exact order**, module, loader, sealed/hidden/public status, and method signatures to find the exact rule. Do not rely on substrings of `getMessage()` because error text is not a compatibility guarantee.

### 10.1. Default methods, `Object` methods, and the handler

These points do not change the conditions for **creating** a proxy, but you need to know them to avoid mistakes when **invoking**:

- `equals`, `hashCode`, and `toString` on the proxy are dispatched to the handler; the corresponding `Method` may have `java.lang.Object` as its declaring class.
- The handler receives `Object[] args`; for methods with no parameters, `args` may be `null`. Primitive arguments are boxed.
- `InvocationHandler.invokeDefault` (Java 16+) can invoke a default method of a proxy interface when valid; a default method is not automatically invoked if the handler does not dispatch it.
- The handler must return a value compatible with the return type; `null` for a primitive return causes `NullPointerException`. Checked exceptions not appropriately declared may be wrapped in `UndeclaredThrowableException`.
- These are **invocation rules after the proxy has been successfully created**, not a way to "fix" sealed, loader visibility, or module access errors.

## 11. Designing dynamic libraries that are safe and easy to upgrade

1. **Separate contract from implementation.** Place public SPIs/interfaces in a module/loader where both host and plugin see the **exact same `Class<?>` object**. Do not require the host to compile directly against internal implementation packages.
2. **Export APIs intentionally** in JPMS if consumers need to import/call typed methods. Do not use `opens` on an entire module to solve class loader or sealed errors: those two errors have different causes.
3. **Only use sealed hierarchies when you want to close the list of direct implementors.** If the system needs free runtime plugins, a dedicated non-sealed interface for extension is a more natural choice than trying to proxy a sealed interface directly.
4. **Prefer stable public interfaces.** Every non-public interface included in a proxy narrows where the proxy class can be placed and its availability. When internal methods also need to be wrapped, create an adapter/factory in the same privileged package/module and expose the result via a valid public interface.
5. **Control class loader topology.** Loading multiple independent copies of an SPI leads to the same binary name without the same runtime type; always verify class identity when using plugin class loaders or custom module layers.
6. **Do not rely on generated class names or constructors.** `Proxy.getProxyClass` is deprecated in JDK 17; use `Proxy.newProxyInstance`. Do not call `setAccessible(true)`/`--add-opens` to bypass encapsulation just to instantiate a generated proxy manually.
7. **Do not treat proxies as a sandbox.** Handlers are code running in-process; module/loader boundaries do not replace authorization, OS sandboxing, isolation, timeouts, or auditing.
8. **Test interface combinations when releasing APIs.** Adding a method with a conflicting return type, sealing an interface, moving packages, changing module exports, or changing class loaders can prevent previously working plugins from creating proxies.

## 12. Self-check exercises

1. **Public scope:** Using the example in section 6, keep `Greeting` but remove `LocalInternal` from the proxy array. How will `publicProxy` and `mixedProxyPublic` change? Why?
2. **Different package:** Move `ForeignInternal` into the `lab.proxy` package and recompile. Predict the result when combining it with `LocalInternal`; is having the same package name alone with a different defining loader enough?
3. **Sealed:** Compare `Proxy.newProxyInstance` with `Parent.class` and `Child.class` in section 7. Distinguish between "directly implementing a sealed interface" and "inheriting a sealed relationship through a permitted non-sealed subinterface."
4. **Class loader:** Replace the loader creating the public proxy in section 6 with a child loader whose parent is the app loader. Predict whether `Class.forName(..., false, childLoader) == Greeting.class`. Why should you not check solely via `type.getClassLoader() == childLoader`?
5. **Signature visibility:** Create a public interface with a method taking a type from a separate plugin loader. Design a loader for the proxy that cannot resolve this type; explain why being able to load the interface is not enough.
6. **JPMS:** In section 8, try unconditionally exporting `demo.hidden.api`, then recompile/rerun. Predict the module/package selection for the proxy. Should you check using the **specific name** of the generated class?
7. **Return collisions:** Change `NumberResult` to return `CharSequence` while `StringResult` still returns `String`. Predict whether the proxy is created, and why interface order still matters for methods with the same name?
8. **API design:** Given a plugin system currently passing both package-private `InternalHook` interfaces from two different packages into `Proxy`. Propose a stable public SPI without widening the visibility of all implementations.

## Conclusion

A JDK dynamic proxy is successfully created when the **interface list, class loader, and accessibility relationships** are all valid. Interfaces must be **non-hidden, non-sealed, with no duplicates**; the loader must see the **exact type object** of each interface and the types in public method signatures; **non-public** interfaces must share a valid **same package/module**; return types on methods with matching signatures must be compatible. An interface being `public` does not mean its JPMS package is exported, and a generated proxy being `public` does not mean the class is open for Reflection from every module.

Dynamic library design should have the host depend on **exported public contracts shared through the right loader**, let the proxy class be generated where the JDK chooses, and avoid using `sealed` directly for extension points that require runtime implementations.

## Official references

- [Java SE 17 — `java.lang.reflect.Proxy`: restrictions, package and module membership, dynamic modules](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html)
- [Java SE 17 — `InvocationHandler`: dispatch, checked exceptions, return types](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html)
- [Java SE 17 — `java.lang.Class`: `isInterface`, `isSealed`, `isHidden`, `getModule`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java Language Specification 17 — `8.1.1.2`: sealed, non-sealed classes; `9.1.1.4`: sealed interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4)
- [Java Language Specification 17 — `7.7`: module declarations, `exports`, `opens`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)
