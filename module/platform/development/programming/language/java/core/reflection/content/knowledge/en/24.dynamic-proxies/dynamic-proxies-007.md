# `equals`, `hashCode`, and `toString` in Java Dynamic Proxies: Contracts to Define

## 1. Why must these three methods be handled explicitly?

A JDK dynamic proxy is an object created at runtime using `java.lang.reflect.Proxy` implementing one or more **interfaces**. When code calls an interface method, the proxy routes the call to `InvocationHandler.invoke(proxy, method, args)` so the handler decides the behavior.

There is an easily overlooked detail: **`equals(Object)`, `hashCode()`, and `toString()` are also routed by the proxy to `InvocationHandler`**, even though they are declared in `java.lang.Object` and are not listed in the business interface. Therefore, the handler must deliberately determine what a proxy object is considered equal to, what its hash code is, and what its string representation looks like. If you only handle business methods and assume the remaining methods belong to a target object, the program can fail at runtime or produce inconsistent behavior in `HashMap`, `HashSet`, logs, and tests.

Distinguish the three objects that may be involved:

- **Proxy**: the object held by the caller, on which `proxy.equals(...)`, `proxy.hashCode()`, and `proxy.toString()` are called.
- **Handler**: the object implementing `InvocationHandler`; receives calls from the proxy. The handler itself has its own `equals`/`hashCode`/`toString`, but those do **not automatically** become the proxy's contract.
- **Target/delegate** (if any): the real object to which the handler forwards business logic. The target's contract does not automatically become the proxy's contract.

Not every dynamic proxy has a target: a handler can compute results itself, send RPC calls, perform logging, or access external resources.

## 2. How does the JVM route the three Object calls to the handler?

For a proxy from `Proxy.newProxyInstance(...)`:

| Caller invocation | `method.getDeclaringClass()` in handler | `args` | Return type to provide |
| --- | --- | --- | --- |
| `proxy.equals(other)` | `Object.class` | One element: `other`, may be `null` | `Boolean` so proxy returns `boolean` |
| `proxy.hashCode()` | `Object.class` | `null` because there are no parameters | `Integer` so proxy returns `int` |
| `proxy.toString()` | `Object.class` | `null` because there are no parameters | `String` |

This remains true even if an interface redeclares a matching signature for any of those three methods: the `Method` passed into the handler still has `Object.class` as its declaring class. Thus, checking `method.getDeclaringClass() == Object.class` and branching by name is a clear way to separate these three calls from business methods. An overload such as `equals(String)` **does not** replace `equals(Object)` and must be identified by its own signature if the interface actually declares it.

A proxy also inherits several other `Object` methods. `final` methods such as `getClass()`, `wait()`, and `notify()` are not intercepted by the handler in this way; you should not assume *every* `Object` method call goes through `invoke`.

**The return type must match.** `InvocationHandler.invoke` has return type `Object`, but the proxy checks/casts the result to the return type of the invoked method. Returning `null` for `equals` or `hashCode` (primitive types) causes `NullPointerException` upon unboxing; returning the wrong type can cause `ClassCastException`. `toString` can technically return `null`, though a meaningful string value is usually much more helpful. If the handler throws a checked exception not declared in the signature, the proxy may wrap it in `UndeclaredThrowableException`.

## 3. Contract of each method

### `equals(Object)` — defining when two proxies are equal

The basic contract of `Object.equals` is:

1. **Reflexive:** `x.equals(x)` is `true`.
2. **Symmetric:** `x.equals(y)` and `y.equals(x)` yield the same result.
3. **Transitive:** if both `x.equals(y)` and `y.equals(z)` are true, `x.equals(z)` must be true.
4. **Consistent:** if the information used for comparison does not change, repeated calls return the same result.
5. **For `null`:** `x.equals(null)` is `false`.

Two common strategies:

- **Proxy identity equality (identity semantics):** only `proxy == other` is equal. Two distinct proxies are considered unequal, even if both forward calls to the same target. This is a simple and safe policy when each proxy is an independent wrapper object.
- **Logical identity equality (logical/value semantics):** two proxies representing the same business entity/resource may be equal if they carry the same stable logical key. You must clearly define the set of comparable objects (for example, same handler type and same service kind), avoiding reliance on just an ID string that unrelated types might also use.

There is no single `equals` policy suitable for all proxies. You must choose based on the proxy's role and document it clearly, especially if an API returns multiple proxies wrapping the same object.

### `hashCode()` — consistent with `equals`

Mandatory condition: if `a.equals(b)` is `true`, then `a.hashCode() == b.hashCode()`. The converse is not required: two unequal objects are allowed to share a hash code.

- When using **identity semantics**, `System.identityHashCode(proxy)` is the right choice to compute a hash code directly from object identity without re-invoking `proxy.hashCode()`.
- When using **logical/value semantics**, the hash code should be computed from **the exact same stable keys used in `equals`**, such as `Objects.hash(serviceType, resourceId)` or `key.hashCode()` if `key` already includes all identifying components.
- Properties used in `equals`/`hashCode` should not mutate while the proxy is a key in a `HashMap` or an element in a `HashSet`; if they mutate, lookups can fail even though the element remains in the data structure.

`System.identityHashCode(proxy)` is **not** suitable when two distinct proxies are considered equal by a logical key: they could receive different hash codes and violate the contract. Do not call `proxy.hashCode()` inside the `hashCode` branch because that re-enters the same handler.

### `toString()` — useful and safe representation

`toString` should return a short, recognizable description for logs/debugging, such as `GreeterProxy[label=A]` or the interface name and an appropriate resource ID. There is no mandatory rule that two equal objects must have the same string, though a consistent description helps testing and operations.

There is no need to dump all internal state, and especially do not print tokens, passwords, or sensitive data. Avoid writing `return proxy.toString()` or `String.valueOf(proxy)` inside the `toString` branch: they trigger `InvocationHandler.invoke` again and lead to recursion.

## 4. Java 17+ example: three contracts using proxy identity

Create the file `ProxyObjectMethodsDemo.java`:

```java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.HashSet;
import java.util.Set;

public class ProxyObjectMethodsDemo {
    public interface Greeter {
        String greet(String name);
    }

    static Greeter createGreeter(String label) {
        InvocationHandler handler = (proxy, method, args) -> {
            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "equals" -> proxy == args[0];
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "toString" -> "GreeterProxy[label=" + label + "]";
                    default -> throw new UnsupportedOperationException(
                            method.toString());
                };
            }

            if (method.getDeclaringClass() == Greeter.class
                    && method.getName().equals("greet")) {
                return "Hello, " + args[0];
            }

            throw new UnsupportedOperationException(method.toString());
        };

        return (Greeter) Proxy.newProxyInstance(
                Greeter.class.getClassLoader(),
                new Class<?>[] { Greeter.class },
                handler);
    }

    public static void main(String[] args) {
        Greeter a = createGreeter("A");
        Greeter b = createGreeter("B");

        System.out.println(a.greet("An"));
        System.out.println(a.equals(a));
        System.out.println(a.equals(b));
        System.out.println(a.equals(null));
        System.out.println(
                a.hashCode() == System.identityHashCode(a));
        System.out.println(a.toString());

        Set<Greeter> set = new HashSet<>();
        set.add(a);
        set.add(b);
        set.add(a);
        System.out.println(set.size());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 ProxyObjectMethodsDemo.java
java ProxyObjectMethodsDemo
```

Expected output:

```text
Hello, An
true
false
false
true
GreeterProxy[label=A]
2
```

Analysis:

1. `a.greet("An")` is a business method, for which the handler returns the greeting string.
2. `a.equals(a)` is `true`, whereas `a.equals(b)` is `false` even though both `a` and `b` implement `Greeter`. The two proxy objects were created by two separate factory calls and thus have distinct identities.
3. `a.equals(null)` is `false` because a proxy is not equal to `null`.
4. `a.hashCode() == System.identityHashCode(a)` is `true` according to the implemented policy; the exact hash code value can vary across runs, so the example only verifies consistency rather than printing an arbitrary number.
5. `a.toString()` builds a readable string directly from the `label` held by the handler, without calling back into proxy methods.
6. The `HashSet` holds only two distinct proxies even though `a` is inserted twice. `HashSet` relies on both `hashCode` and `equals`, making this a practical check of the contract.

In the code above, `args[0]` is only read in the `equals` or `greet` branches, which are the two methods with one parameter. When receiving `hashCode` or `toString`, `args` is `null` and the code does not access it.

## 5. When a proxy wraps a target: do not blindly forward the three methods

Suppose the handler forwards business calls to a `target` object via reflection:

```java
// Illustrative inside InvocationHandler, not a standalone program:
Object result = method.invoke(target, args);
```

This is only appropriate when `method` is genuinely a method meant to be called on `target` and accessibility/object type requirements are met. Specifically, `equals`, `hashCode`, and `toString` must have explicit decisions.

For example, a handler writing `return target.equals(args[0]);` for `proxy.equals(other)` can cause `proxy.equals(target)` to return `true` while `target.equals(proxy)` returns `false`. That **violates symmetry**. Conversely, calling `method.invoke(proxy, args)` to "return default" re-triggers the same proxy and creates a recursive call chain.

If you want **a proxy to equal its target** or **two proxies wrapping the same target to be equal**, you must verify comparison in both directions, accepted types, and corresponding hash codes. In many systems, choosing identity semantics for proxies and exposing business IDs via the interface is far more predictable.

Another option is using an **immutable logical key** when creating the handler. For example, the handler holds `record ServiceKey(String tenant, String serviceId) {}` and compares two valid proxies by their `ServiceKey` values. Then:

- `equals` must verify that the other object belongs to a compatible proxy group and its handler carries a matching key; you can use `Proxy.isProxyClass(other.getClass())` and then `Proxy.getInvocationHandler(other)` after checking `other != null`.
- `hashCode` must be computed from the same key; **not** from proxy identity.
- `toString` can display the service type and a safe portion of the ID to aid diagnostics.

Getting a handler from `Proxy.getInvocationHandler(other)` only confirms the object is a JDK dynamic proxy (or may throw under API conditions); it does not by itself prove it belongs to the same business type. Check the handler/contract type before accessing the key. Two proxies considered equal must share comparison and hashing rules in both directions; if a target from another framework also has a custom `equals`, cross-comparison between proxy and target is usually much more complex.

## 6. Common mistakes and how to avoid them

| Implementation mistake | Consequence | Fix |
| --- | --- | --- |
| Handling only business method names, forgetting `equals`/`hashCode`/`toString` | Logging or adding the proxy to a `HashSet` may throw errors | Create a dedicated branch for `Object.class` |
| Using `proxy.equals(other)` in the `equals` branch | Recursion through `invoke` | Use `proxy == other` for identity semantics; or compare immutable keys |
| Using `proxy.hashCode()` in the `hashCode` branch | Recursion through `invoke` | Use `System.identityHashCode(proxy)` when choosing identity semantics |
| Using `proxy.toString()` in the `toString` branch | Recursion through `invoke` | Build the string from safe handler data |
| `equals` compares logical key while `hashCode` uses identity | May violate contract, breaking lookups in `HashMap`/`HashSet` | Use the same key fields for both |
| Blindly delegating `target.equals(other)` | Can be asymmetric between target and proxy | Choose an explicit policy and test both directions |
| Returning `null` for `equals`/`hashCode` | `NullPointerException` upon unboxing | Return properly typed `Boolean`/`Integer` |
| Mutating the key after inserting the proxy into a hash collection | Element can no longer be found by old key | Use immutable keys throughout the proxy lifecycle |
| Printing target/credentials in `toString` | Sensitive data can leak into logs | Display only safe, necessary metadata |

**Do not check only the method name.** If an interface has an overload `equals(String)`, that is not `Object.equals(Object)`. Combine declaring class and signature; checking `method.getDeclaringClass() == Object.class` handles the exact three special `Object` methods routed by JDK proxies to the handler.

## 7. How should the contract be tested?

For each proxy type, at a minimum test:

- **`equals`:** `x.equals(x)`, `x.equals(null)`, two proxies with same/different keys, and symmetry against another proxy and against the target if the API permits it.
- **`hashCode`:** equal pairs have equal hash codes; value remains stable while identifying state does not change; insert and look up again in `HashSet`/`HashMap`.
- **`toString`:** invokes without error, does not recurse, contains no sensitive data, and yields a string useful in logs.
- **Handler routing:** the three `Object` methods are distinguished from interface methods; also test an interface redeclaring `toString()` or overloading `equals(String)` if the API has such cases.
- **Error paths:** the handler does not return `null` for primitive-returning methods and does not swallow business exceptions into fake success strings.

If a framework creates nested proxies (a proxy wrapping a proxy), clarify whether `equals` compares the outer wrapper, inner wrapper, or business ID; relying purely on the auto-generated proxy class or its name often makes the contract fragile when interfaces or class loaders change.

## 8. Self-check

**Q1.** Must two objects created separately with `Proxy.newProxyInstance` pointing to the same target be `equals` to each other?

**Answer:** No. That depends on the `equals` policy in the handler. With identity semantics they are unequal; with logical semantics they can be equal if the contract is designed consistently.

**Q2.** Why is `return proxy.hashCode()` inside the `hashCode` branch wrong?

**Answer:** The call loops back to the same proxy and handler, causing recursion. With identity semantics, use `System.identityHashCode(proxy)` to avoid reflective dispatch.

**Q3.** Can `System.identityHashCode(proxy)` be used when two different proxies are considered equal by `resourceId`?

**Answer:** You should not: identity hash values can differ between two equal proxies. The hash must be computed from the same stable identifying data used in `equals`.

**Q4.** Does a proxy's `getClass()` enter `InvocationHandler.invoke` like `toString()`?

**Answer:** No. `getClass()` is a `final` method on `Object`; the three methods `equals`, `hashCode`, and `toString` are handled specially by JDK dynamic proxies.

**Takeaway:** JDK dynamic proxies do not automatically provide a meaningful equality policy for an application. The handler must define `equals`, `hashCode`, and `toString` consistently with how the proxy represents an object/resource, and test them through everyday operations such as comparisons, collection storage, and logging.