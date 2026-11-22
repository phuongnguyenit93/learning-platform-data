# Conditions for `public`, `non-public`, `hidden`, and `sealed` Interfaces in Java Dynamic Proxies

## 1. Objective and decision rules

`java.lang.reflect.Proxy` generates a class at runtime to implement **one or more interfaces**, then dispatches method calls on the proxy to `InvocationHandler.invoke`. Having `isInterface() == true` on a `Class<?>` value is **not enough** for it to work with `Proxy.newProxyInstance`.

In Java 17+, the input interface set must simultaneously satisfy constraints on **interface kind**, **class loader**, **type visibility**, **package/module**, and **method signatures**. Two special cases rejected by design are **hidden interfaces** and **sealed interfaces**.

| Input interface | Usable with `Proxy.newProxyInstance`? | Main conditions |
| --- | --- | --- |
| `public`, non-`hidden`, non-`sealed` | **Yes**, if valid | The interface and types in public signatures must be visible through the supplied loader; module encapsulation affects proxy class placement and accessibility. |
| `non-public` (e.g., package-private), non-`hidden`, non-`sealed` | **Conditionally** | All non-public interfaces in the same creation call must be in the **same package and same module**, defined by the supplied loader; their module must have access to the interfaces to implement. |
| `hidden interface` | **No** | The `Proxy` API requires interfaces to be **non-hidden**; violation throws `IllegalArgumentException`. |
| `sealed interface` | **No** | The `Proxy` API requires interfaces to be **non-sealed**; violation throws `IllegalArgumentException` even if the interface is `public`. |

Key point to remember: **`non-public` does not mean unproxiable**. Conversely, `public` does not automatically guarantee success if the class loader, module, or signatures are invalid.

## 2. Three concepts often confused

### 2.1. Java access level of an interface

- `public interface Api` has the `public` modifier: `Modifier.isPublic(Api.class.getModifiers())` is `true`.
- A package-level `interface InternalApi`, or a member interface declared without `public`, may be `non-public`: `Modifier.isPublic(...)` is `false`.
- Whether calling Java code can see a type and whether the JVM can generate a valid proxy are **two separate questions**. Holding a `Class<?>` reference to an interface does not automatically remove package/module restrictions.

A **public interface inside an unexported package** of a named module still has the `public` modifier. It **does not turn into a non-public interface** merely because the module does not export that package.

### 2.2. Package, runtime module, and class loader

The same package name does not guarantee the same runtime package/module in the JVM. When multiple non-public interfaces participate together, the JDK requires them to share the same package **and the same module**, and the module/loader must satisfy proxy class definition rules.

For every interface `i`, the class loader `loader` passed to `Proxy.newProxyInstance` must see the exact **same `Class` object** under the check:

```java
Class.forName(i.getName(), false, loader) == i
```

This is an **illustrative Javadoc condition expression**, not standalone code and not a recommendation to call `Class.forName` on a hidden interface. A loader that sees a type with **the same name but a different `Class` identity** still fails the requirement. Beyond the interfaces themselves, types appearing in the signatures of all `public` methods (including methods inherited from superinterfaces) must also be visible by name through this loader.

### 2.3. Regular, hidden, and sealed interfaces

- A **regular interface** has a binary name looked up by a loader; `public` vs. `non-public` is an orthogonal classification dimension.
- A **hidden interface** is defined, for example, via `MethodHandles.Lookup#defineHiddenClass`. `Class.isHidden()` returns `true`; it has no binary name that can be looked up in the normal way. `Proxy` rejects this kind.
- A **sealed interface** restricts permitted implementations via `permits`; `Class.isSealed()` returns `true`. JDK `Proxy` does not accept sealed interfaces as input, even if another design could comply with `permits`.

`hidden` and `sealed` are **two different properties**. A `non-sealed` interface in a hierarchy with a sealed superinterface must be evaluated by **the exact `Class<?>` object placed in the interfaces array**; do not assume it is rejected merely because of a sealed ancestor. However, loader, module, and signature conditions must still hold.

## 3. How is the proxy class's package/module chosen?

The JDK chooses the accessibility of the **generated proxy class** based on the interface set:

| Interface set | Proxy class rule |
| --- | --- |
| All interfaces are `public`, and all are in exported or open packages | Proxy class is `public` in an unconditionally exported but **non-open** package; exact package/module name is not guaranteed. |
| All interfaces are `public`, but at least one interface is in a package that is neither exported **nor** open | Proxy class is `public` in a non-exported, non-open package of a **dynamic module**; code outside the module does not automatically get direct access to the proxy class. |
| At least one interface is `non-public` | Proxy class is **non-public**, in the **same package and module** as the non-public interfaces. All non-public interfaces must share the same package/module; if they differ, that proxy cannot be created. |

**Usability of a proxy instance differs from direct access to the proxy class.** Callers typically only need:

```java
Object instance = Proxy.newProxyInstance(loader, interfaces, handler);
```

Then cast to an interface that the calling code is permitted to access. Do not rely on class names formatted like `$Proxy...` or manually invoke the proxy class's constructor via Reflection. For a proxy in a closed dynamic module, invoking the constructor directly via Reflection can fail with `IllegalAccessException`. `Proxy.getProxyClass` has also been marked deprecated; prefer `newProxyInstance`.

If there are both public and non-public interfaces, the proxy class's accessibility follows the **most restrictive interface**; adding a public interface does not make a non-public proxy class public.

## 4. Complete runnable example on Java 17+

This example demonstrates **four cases** in one program: valid public, valid non-public, rejected sealed, and rejected hidden. The program also verifies mixing public and non-public.

Save as **`ProxyInterfaceRulesDemo.java`** (without adding a `package` declaration so it runs directly from the same directory):

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Modifier;
import java.lang.reflect.Proxy;

public class ProxyInterfaceRulesDemo {
    public interface PublicApi {
        String message();
    }

    interface InternalApi {
        String internal();
    }

    public sealed interface SealedApi permits Approved {
        String execute();
    }

    public static final class Approved implements SealedApi {
        public String execute() { return "approved"; }
    }

    interface HiddenSeed {
        String hidden();
    }

    public static void main(String[] args) throws Throwable {
        ClassLoader loader = ProxyInterfaceRulesDemo.class.getClassLoader();
        InvocationHandler handler = (proxy, method, parameters) ->
                switch (method.getName()) {
                    case "message" -> "public-ok";
                    case "internal" -> "internal-ok";
                    default -> throw new UnsupportedOperationException(method.getName());
                };

        PublicApi publicProxy = (PublicApi) Proxy.newProxyInstance(
                loader, new Class<?>[]{PublicApi.class}, handler);
        System.out.println("public: " + publicProxy.message()
                + ", proxyPublic=" + Modifier.isPublic(publicProxy.getClass().getModifiers()));

        InternalApi internalProxy = (InternalApi) Proxy.newProxyInstance(
                loader, new Class<?>[]{InternalApi.class}, handler);
        System.out.println("non-public: " + internalProxy.internal()
                + ", proxyPublic=" + Modifier.isPublic(internalProxy.getClass().getModifiers()));

        Object mixed = Proxy.newProxyInstance(
                loader, new Class<?>[]{PublicApi.class, InternalApi.class}, handler);
        System.out.println("mixed: " + ((PublicApi) mixed).message()
                + ", proxyPublic=" + Modifier.isPublic(mixed.getClass().getModifiers()));

        System.out.println("sealed flag: " + SealedApi.class.isSealed());
        try {
            Proxy.newProxyInstance(loader, new Class<?>[]{SealedApi.class}, handler);
            System.out.println("sealed: unexpected success");
        } catch (IllegalArgumentException expected) {
            System.out.println("sealed rejected: " + expected.getClass().getSimpleName());
        }

        String resource = "/" + HiddenSeed.class.getName().replace('.', '/') + ".class";
        try (InputStream stream = HiddenSeed.class.getResourceAsStream(resource)) {
            if (stream == null) throw new IllegalStateException("Class bytes not found");
            byte[] bytes = stream.readAllBytes();
            Class<?> hidden = MethodHandles.lookup()
                    .defineHiddenClass(bytes, false).lookupClass();
            System.out.println("hidden flags: interface=" + hidden.isInterface()
                    + ", hidden=" + hidden.isHidden());
            try {
                Proxy.newProxyInstance(loader, new Class<?>[]{hidden}, handler);
                System.out.println("hidden: unexpected success");
            } catch (IllegalArgumentException expected) {
                System.out.println("hidden rejected: " + expected.getClass().getSimpleName());
            }
        }
    }
}
```

Compile and run in the directory containing the source file with JDK 17 or later:

```bash
javac --release 17 ProxyInterfaceRulesDemo.java
java ProxyInterfaceRulesDemo
```

Output:

```text
public: public-ok, proxyPublic=true
non-public: internal-ok, proxyPublic=false
mixed: public-ok, proxyPublic=false
sealed flag: true
sealed rejected: IllegalArgumentException
hidden flags: interface=true, hidden=true
hidden rejected: IllegalArgumentException
```

**Output explanation:**

1. `PublicApi` is a member interface with `public`; the generated proxy class is `public`, and the handler returns `"public-ok"`.
2. `InternalApi` is a member interface declared without `public`, so it is non-public. Because it is created alone and satisfies package/module/loader rules, the proxy is created successfully, but the proxy class is not `public`.
3. When both `PublicApi` and `InternalApi` are passed in the array, the proxy is still valid, but the proxy class is non-public according to the more restrictive interface. You can still call `PublicApi.message()` through the public interface type.
4. `SealedApi.class.isSealed()` is `true`; the JDK immediately rejects the request to proxy that interface with `IllegalArgumentException`. Having a class `Approved` listed in `permits` does not allow JDK Proxy to append its own subclass.
5. `HiddenSeed` starts out as a **regular** interface with a `.class` file produced by `javac`. `defineHiddenClass` defines a **new hidden interface** from that bytecode, then returns a `Class<?>` with `isInterface() == true` and `isHidden() == true`. That is the kind JDK Proxy rejects. Do not conflate the original `HiddenSeed.class` with the new `Class<?> hidden` object.
6. The proxy class name and hidden interface name can vary across runs or JDK versions; the example only prints properties guaranteed by the API. The `InvocationHandler` in the example handles the two business methods being called; a real application needs to define how to handle `equals`, `hashCode`, `toString`, and other methods if invoked.

The example was verified with `javac --release 17` and executed on JDK 24. It uses only APIs available since Java 17, including `Class.isHidden()`, `Class.isSealed()`, and `Lookup.defineHiddenClass`. Reading the `.class` bytes requires the `javac`-compiled files to be on the classpath at runtime; the commands above satisfy that.

## 5. Why cannot hidden and sealed interfaces be proxied?

### 5.1. Hidden interface

`MethodHandles.Lookup#defineHiddenClass(byte[], ...)` creates a hidden class or hidden interface from bytecode. A hidden type has no binary name for a normal loader to look up again by name; you cannot assume `Class.forName(hidden.getName(), false, loader)` will find itself.

The `Proxy.newProxyInstance` Javadoc explicitly specifies that elements in the `interfaces` array must be **non-hidden** interfaces. Even when you already hold a `Class<?>` reference to the hidden interface in hand, passing it to this API is rejected. This is a **limitation of the JDK dynamic proxy mechanism**, not a statement that all bytecode generation techniques or adapter frameworks cannot interact with hidden types in other ways.

### 5.2. Sealed interface

Valid declaration example:

```java
sealed interface Operation permits ReadOperation {}

final class ReadOperation implements Operation {}
```

The two declarations above are a **package-scoped illustrative fragment**, needing to be placed in a valid source file. `Operation.class.isSealed()` is `true`. When calling `Proxy.newProxyInstance(..., new Class<?>[]{Operation.class}, ...)`, the JDK rejects `Operation` because of the API's `non-sealed` policy. This cannot be fixed by adding the dynamically generated proxy to the `permits` list in source code as you would with a known implementation class.

**Distinguishing `non-sealed` in Java from "not sealed":** the `non-sealed` keyword is used on an interface/class that directly reopens implementation in a sealed hierarchy. Its `Class.isSealed()` is `false`. If the input interface itself is non-hidden, non-sealed, and satisfies all other conditions, merely having inherited from a sealed superinterface is not a reason to reject it.

## 6. Other checks still required for public/non-public interfaces

Even when every interface has `isInterface() == true`, `isHidden() == false`, and `isSealed() == false`, `Proxy.newProxyInstance` can still throw `IllegalArgumentException`:

1. **Duplicate interface:** the same `Class<?>` object appears twice in the `interfaces` array.
2. **Wrong class loader:** an interface is not visible by name through the specified loader, or the loader resolves a different `Class` with the same name; types mentioned in `public` signatures must also be visible.
3. **Non-public in different packages/modules:** two non-public interfaces from two different packages cannot be implemented together by one proxy class. Even if package names match, differing modules are still invalid under JDK rules.
4. **Loader does not define the non-public interface:** a loader merely *seeing* it via delegation is insufficient if it fails the defining-loader requirement in the Javadoc.
5. **Module of the non-public interface lacks accessibility:** when mixing non-public with other interfaces, the module containing the proxy must have access to the implemented interfaces.
6. **Matching signatures with incompatible return types:** methods with the same name and parameter list whose primitive/`void` return types differ will conflict; for reference return types, one return type must be an appropriate subtype of the others.
7. **JVM limits:** the number of interfaces or class file limits may prevent proxy generation.

If `interfaces` or any element of it is `null`, or `handler` is `null`, the API may throw `NullPointerException` per its contract; do not lump every failure under `IllegalArgumentException`.

**Module access differs from export/open conditions:** a public interface in a closed package can be proxied under the JDK's **dynamic module** rules. Successful proxy creation does not turn that package into public API for all other Java code. Distinguish between creating a proxy, valid casting from the caller's location, and directly accessing the generated proxy class.

## 7. Quick diagnosis before creating a proxy

The method snippet below is for **preliminary filtering** (placed in a class with `import java.lang.reflect.Modifier;`). It only checks the **interface kind**; a `"candidate"` result does not mean all other requirements pass.

```java
static String precheck(Class<?> type) {
    if (type == null) return "null";
    if (!type.isInterface()) return "not an interface";
    if (type.isHidden()) return "hidden interface: unsupported";
    if (type.isSealed()) return "sealed interface: unsupported";
    return Modifier.isPublic(type.getModifiers())
            ? "candidate: public"
            : "candidate: non-public; check package, module and loader";
}
```

When investigating a failure, record the following (without depending on JDK-generated proxy names):

- `type.getName()`, `type.isInterface()`, `type.isHidden()`, `type.isSealed()`, `Modifier.isPublic(type.getModifiers())`.
- `type.getPackageName()`, `type.getModule()`, `type.getClassLoader()`, and the loader actually passed to `Proxy.newProxyInstance`.
- All interfaces in the array, their order, and types appearing in `public` signatures, including inherited interfaces.
- Exception type and cause; avoid relying on exact exception message strings because messages may vary across JDK versions.

**Invalid** duplicate interface example:

```java
Proxy.newProxyInstance(
        PublicApi.class.getClassLoader(),
        new Class<?>[]{PublicApi.class, PublicApi.class},
        handler);
```

This is an **illustrative fragment** using `PublicApi` and `handler` declared in the previous program, not a standalone program. This error is `IllegalArgumentException` even though `PublicApi` is completely public, non-hidden, and non-sealed.

## 8. Clearing up common misconceptions

| Misconception or wrong fix | Correct handling |
| --- | --- |
| "Only `public interface` works with JDK Proxy." | Non-public is valid if package/module/loader constraints are strictly met. |
| "A non-public interface means an unexported package." | Interface modifiers and package export/open status are two distinct concepts. |
| "Holding a hidden interface's `Class<?>` means you can still proxy it." | `isHidden() == true` is rejected by JDK Proxy even when you already have the `Class` object. |
| "A public sealed interface is allowed." | `isSealed() == true` is rejected independently of the `public` modifier. |
| "Switching the loader to `Thread.currentThread().getContextClassLoader()` definitely fixes the error." | You must prove the specified loader sees the exact identity of every interface and every type in signatures, plus non-public rules. |
| "Once a proxy is created successfully, you can call the `$Proxy...` class constructor." | Access to the proxy class may be closed by modules; use `Proxy.newProxyInstance`. |
| "`newProxyInstance` only checks `isInterface()`." | The Javadoc also enforces sealed/hidden, duplicates, loader, signatures, package/module, and VM limits. |
| "If each interface can be proxied separately, combining them always works." | The combined interface set may conflict on non-public package/module or method return types. |

## 9. Exercises and self-check questions

1. Can two **package-private** interfaces in the same package and same module, defined by the exact same class loader, be passed together to `newProxyInstance`? Explain the remaining conditions that still must be checked.
2. Is a `public interface` inside a **non-exported, non-open** package of a named module rejected merely because the package is closed? Where will the proxy class reside according to JDK rules?
3. In the example, why could `InternalApi` be proxied even though `Modifier.isPublic(InternalApi.class.getModifiers()) == false`?
4. Why is the freshly compiled `HiddenSeed.class` different from the `Class<?> hidden` returned by `defineHiddenClass`?
5. If an interface has `isSealed() == true` and is also `public`, which condition determines the outcome of `newProxyInstance`?
6. If two interfaces are both `public` and non-hidden/non-sealed, yet declare the same `value()` method with two different primitive return types, why can the proxy request fail?

**Self-check before designing a library:** First classify `isInterface / isHidden / isSealed`; then check the loader, interface set, signatures, package/module, and accessibility from proxy-consuming code. Use **`Proxy.newProxyInstance`** as the instance creation API, then work through the interfaces that calling code is actually permitted to access.

## 10. Official Documentation

- [Oracle Java 17 — `java.lang.reflect.Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html): Restrictions, Package and Module Membership of Proxy Class, Dynamic Modules, and exceptions of `newProxyInstance`.
- [Oracle Java 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isInterface`, `isHidden`, `isSealed`, `getModifiers`, `getModule`, and `getClassLoader`.
- [Oracle Java 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass` and how hidden classes/interfaces are created.
- [Java Language Specification 17 — Sealed Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4): semantics of `sealed`, `permits`, `non-sealed`.