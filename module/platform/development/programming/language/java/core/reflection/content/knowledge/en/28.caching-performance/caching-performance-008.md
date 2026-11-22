# Never Share Private Access Capabilities Beyond the Necessary Scope

## 1. The Issue in Reflection and Caching

Reflection lets a program look up and invoke a class member through objects such as `Method`, `Field`, or `Constructor`. By default, the API enforces Java's access checks; `private` members are not automatically callable from everywhere.

`java.lang.reflect.AccessibleObject` (the superclass of `Method`, `Field`, and `Constructor`) provides `setAccessible(true)` and `trySetAccessible()` to request **suppressing Java language access checks** for a specific reflective object, within the limits allowed by the Java Platform Module System (JPMS). Once enabled, other code **handed that exact `Method`/`Field` object** can exercise the access capability enabled by its owner.

Therefore, in the **Caching and Performance** module, the practical rule is:

> **Keep and share metadata or invocation capabilities strictly with components that genuinely need them. Never place reflection objects with private access enabled into shared caches or public APIs.**

Example risk: a diagnostics component is permitted to access a plugin's private method for internal inspection. It calls `method.trySetAccessible()` and then stores the `Method` in a `public static Map<String, Method>`. Another component that obtains this reference can call `method.invoke(...)` without having to establish permissions on the same object itself. A cache labeled “performance optimization” thus unintentionally becomes a **distribution channel for broader access than necessary**.

An important distinction: Java/JPMS access checks are not an isolation boundary against malicious code running in the same JVM. Controlling APIs, references, and lookup privileges remains essential to preserve **encapsulation**, prevent misuse, and limit unintended capability exposure.

## 2. Access Control Mechanisms on `AccessibleObject`

| API or Operation | Meaning | Scope-Preservation Note |
| --- | --- | --- |
| `getDeclaredMethod`, `getDeclaredField` | Looks up metadata including non-public members declared directly | Finding metadata does not grant permission to invoke/read |
| `Method.invoke`, `Field.get/set` | Executes the reflective operation | Enforces access checks unless validly suppressed |
| `canAccess(receiver)` | Checks whether access is permitted via this reflection object for the given receiver | Read-only check, does not grant access; `null` for static members/constructors, actual instance for instance members |
| `trySetAccessible()` | Attempts to enable suppressing access checks, returning `true` on success and `false` otherwise | **Mutates the state** of the object on success |
| `setAccessible(true)` | Requests enabling suppression of access checks | Can throw `InaccessibleObjectException` if JPMS forbids it |
| `setAccessible(false)` | Disables suppressing access checks on **this object** | Not a mechanism to revoke already-distributed references/handles |
| `MethodHandles.privateLookupIn` | Creates a `Lookup` with appropriate access rights to the target class when eligible | `Lookup` is also a sensitive capability; do not hand it where unneeded |

A `Method` with `setAccessible(true)` enabled must still satisfy other invocation conditions such as compatible receiver class and argument count/types. Enabling accessibility **does not make the method `public` in bytecode**, does not alter modifiers, and does not grant unlimited access across all packages/modules.

In Java 9+, JPMS restricts deep reflection. If the target module's package is not suitably opened to the calling module, `trySetAccessible()` can return `false`, and `setAccessible(true)` can throw `InaccessibleObjectException`. Do not treat `setAccessible(true)` as a way around all module boundaries.

### Capability Travels with the Handed-Out Object

Consider the following snippet (illustrating behavior to avoid):

```java
// ANTI-PATTERN ILLUSTRATION, NOT STANDALONE RUNNABLE:
// Method created in a trusted component:
Method privateMethod = Target.class.getDeclaredMethod("secret");
privateMethod.setAccessible(true);

// Wrong scope: putting the access-enabled object into a public registry/cache:
sharedRegistry.put("secretMethod", privateMethod);
```

Once the `privateMethod` reference escapes, recipients can exercise the capability attached to **that reference**. Making the cache field `private` is insufficient if a public getter or callback returns the `Method` object directly. Likewise, returning a `MethodHandle` created with a private-privileged lookup also hands out the invocation capability it holds.

## 3. Java 17+ Example: Enabling Access Locally and Closing It Again

This example deliberately puts **two top-level classes** in one file: `Ticket` has a private method; `ScopedPrivateAccessDemo` belongs to a **different nest**, so initially it has no permission to invoke the private method via reflection. Run on the **class path/unnamed module** so opening access in the example is permitted.

Save to `ScopedPrivateAccessDemo.java`:

```java
import java.lang.reflect.Method;

public class ScopedPrivateAccessDemo {
    static final class Diagnostics {
        static boolean suffixMatches(Ticket ticket, String expected)
                throws ReflectiveOperationException {
            // Each call creates its own Method object, without placing it in a shared cache.
            Method method = Ticket.class.getDeclaredMethod("lastFour");

            System.out.println("before=" + method.canAccess(ticket));
            if (!method.trySetAccessible()) {
                throw new IllegalStateException(
                        "Private access is not available");
            }

            try {
                System.out.println("during=" + method.canAccess(ticket));
                String suffix = (String) method.invoke(ticket);

                // Return a minimal business result, not the Method.
                return suffix.equals(expected);
            } finally {
                method.setAccessible(false);
                System.out.println("after=" + method.canAccess(ticket));
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Ticket ticket = new Ticket("DOC-4821");
        System.out.println("label=" + ticket.publicLabel());
        boolean matched = Diagnostics.suffixMatches(ticket, "4821");
        System.out.println("matched=" + matched);
    }
}

final class Ticket {
    private final String identifier;

    Ticket(String identifier) {
        this.identifier = identifier;
    }

    private String lastFour() {
        return identifier.substring(identifier.length() - 4);
    }

    String publicLabel() {
        return "ticket";
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 ScopedPrivateAccessDemo.java
java ScopedPrivateAccessDemo
```

Expected stdout:

```text
label=ticket
before=false
during=true
after=false
matched=true
```

Explanation:

1. `method.canAccess(ticket)` is initially `false` because `Ticket.lastFour()` is private and the calling code belongs to a different nest.
2. `trySetAccessible()` succeeds in this example running on the class path; the local `Method` object has invocation access enabled.
3. `invoke(ticket)` runs the method and returns the string. The utility returns a **boolean** to the caller; it neither returns the internal string nor the `Method`.
4. `finally` disables the accessible flag on **that local `Method` object** before the method returns, even if `invoke` throws an exception.
5. `matched=true` confirms the final output is only the intentionally exposed minimal result, not reflective capability.

**Important limitation:** the example clarifies local lifecycle; it does not claim `setAccessible(false)` is an absolute capability-revocation mechanism. If the object was leaked earlier, another copy/reference or independent handle may still exist. You must also never toggle the accessible flag **on the same `Method` used concurrently by multiple threads**: one thread disabling the flag can cause another thread's call to fail unexpectedly.

In ordinary applications, it is best **not to reflect into private members at all** when an appropriate public/package-private method can express what is needed. `publicLabel()` in the example illustrates a narrower access path for common needs.

## 4. Designing Caches at the Right Scope

Reflection optimization usually aims to reduce the cost of **repeated metadata lookups**. Yet the more widely a cache is shared, the more code can obtain references to sensitive access objects.

Comparing designs:

| Design | Evaluation |
| --- | --- |
| Global cache mapping names → accessible-enabled `Method` accessible by any component | **Avoid**: distributes references granted private capability |
| Caching metadata of public methods for public operations | More suitable when genuinely needed and classloaders are managed |
| Caching private `Method` inside a trusted helper; exposing only a narrow business API | Acceptable when performance is truly needed, provided callers, concurrency, and cache lifecycle are controlled |
| Looking up the private method locally each time and returning checked results | Simple and easy to audit; trades off repeated lookup cost |
| Using a private-privileged `MethodHandle` and exposing the handle externally | Also distributes invocation capability; not automatically safe |

If a method truly must be cached, the scope should be the **component owning the work**, for instance:

- Keep the cache inside an internal class/service, with no getter returning `Method` or `Lookup`.
- Return only bounded values through business methods like `boolean matches(...)` or DTOs without sensitive internals.
- Do not use ambiguous method-name string keys; include declaring `Class<?>`, name, parameter list, static/instance, and module/loader where needed.
- Choose an appropriate eviction/lifecycle policy because caches retaining `Method`/`Class` long-term can retain references to a **plugin's classloader**, preventing plugin versions from unloading.
- Use thread-safe cache structures (`ConcurrentHashMap`, `ClassValue` where appropriate) to avoid concurrent map corruption; **a thread-safe map does not make an element's accessible state thread-safe**.

Do not decide to cache private reflection just because “reflection is slow.” Benchmark the real workload first; lookup, invoke, boxing, and adapter costs depend on the JDK, call shape, and frequency. If the logic can use direct Java calls, that is usually the simplest and most maintainable path.

### Do Not Toggle Access on an Object Shared Across Threads

Suppose `Method cached` is already shared, and one thread executes:

```java
// Thread A — anti-pattern:
cached.setAccessible(true);
try {
    cached.invoke(target);
} finally {
    cached.setAccessible(false);
}
```

Meanwhile, Thread B also uses `cached`. Because the flag is state on the reflection object, Thread B can observe it at unexpected moments. `finally` only ensures Thread A **attempts to close it after the operation**, without creating an atomic access section across threads.

If private access must be used in concurrent code, avoid sharing an object whose flag is toggled; consider creating local objects or designing a component that owns stable privileges without letting capabilities escape, and verify thread safety and business invariants separately. Synchronization locks only work if **every caller** accessing the same state uses the exact same lock—something a leaked reference cannot guarantee.

## 5. `MethodHandles.Lookup` Is Also a Capability

`MethodHandles.Lookup` represents the access context of the code that created it. Sometimes a framework needs `MethodHandles.privateLookupIn(Target.class, callerLookup)` to create a lookup with required access to the target, if module/readability/openness conditions are satisfied. Then:

```java
// Illustrative snippet, requires imports and appropriate permission/module conditions:
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(Target.class,
                MethodHandles.lookup());
MethodHandle privateHandle = privateLookup.findVirtual(
        Target.class,
        "hiddenAction",
        MethodType.methodType(void.class));
```

**Switching from `Method` to `MethodHandle` does not automatically make it safe**:

- A `Lookup` with private privileges should only be passed to trusted code that needs those privileges.
- A `MethodHandle` pointing to a private operation also confers invocation capability; any component receiving the handle can invoke it without re-checking permissions as at creation time.
- Do not cache private lookups/handles in registries shared with untrusted plugins.
- Prefer encapsulating inside a helper that exposes only validated operations and restricted outputs.

Java modules still control which packages are opened for deep reflection. Do not add global `--add-opens` flags merely to silence exceptions; opening a module can grant broad access to other code in the receiving module.

## 6. Alternative API Designs to Avoid Distributing Private Access

Several alternatives are usually better:

**Minimal public API.** If callers only need the answer to “is the code valid?”, provide `boolean isValidCode(String input)` instead of returning the `Field` holding the code.

**Integration interfaces.** Have plugins implement public interfaces for permitted functionality, rather than letting the host look up private members by string name. This gives compile-time contracts and reduces coupling to internal structure.

**Privileged adapter or service.** If a framework must reflect into private members for legacy compatibility, isolate the privilege inside an internal adapter; callers pass validated requests and receive only the necessary data.

**Alternatives using public APIs and metadata caching.** For stable public methods, keep metadata in a private cache without enabling `setAccessible` when needed. Still account for loader lifecycle.

**Minimal module openness.** When a plugin is a named module, open only the required package to the specific diagnostics module (`opens package.to.inspect to module.diagnostics;`) rather than `open module` or `--add-opens ...=ALL-UNNAMED` across the whole application. “Opening a package” is a **package/module-level** permission, not scoped to a single method; that makes controlling the API of the receiving component even more important.

## 7. Testing and Exception Handling

Common issues when building internal capabilities:

| Scenario | Cause / How to Handle |
| --- | --- |
| `getDeclaredMethod` throws `NoSuchMethodException` | Verify exact name and parameter type list (primitives vs. wrappers), overloads, and the loaded class version |
| `trySetAccessible()` returns `false` | JPMS or access rules forbid it; reject the action and fix module configuration according to required privileges |
| `setAccessible(true)` throws `InaccessibleObjectException` | Target does not open the required package; do not retry blindly or open the entire module |
| `Method.invoke` throws `IllegalAccessException` | Access checks still apply or context lacks permission; do not assume access opening succeeded |
| `InvocationTargetException` | Target code actually threw an exception; inspect `getCause()` to diagnose rather than blaming accessibility |
| `IllegalArgumentException` on invoke | Wrong receiver or argument count/types; opening access will not fix this |
| Classloader still retained after plugin unload | Check caches holding plugin-related `Class`, `Method`, `Lookup`, handles, or lambdas |
| Tests pass on class path but fail on module path | Check `opens`, `exports`, caller/target modules, and classloaders |

Never log secrets, tokens, or full private arguments when reflection fails. Log only the exception type, member signature, declaring class, module/loader, and failing step according to your application's data-protection rules.

## 8. Review Checklist for Reflection Caches

Before shipping a reflection cache/helper to production, verify:

1. Is accessing the private member truly necessary? Is there a cleaner public/package-private API?
2. Which callers may invoke the helper? Are business conditions checked before enabling access?
3. Can any sensitive `Method`/`Field`, `Lookup`, or `MethodHandle` escape through getters, callbacks, maps, events, logs, or return objects?
4. Is the cache placed in the component that owns the privilege, or shared across the entire application/plugins?
5. If an accessible object may be used concurrently, does the code rely on contentious flag toggling?
6. Does the cache's lifecycle align with classloader/redeploy/hot-reload lifecycles?
7. Are module permissions truly opening only the necessary packages/modules?
8. Are both allowed and denied access cases, wrong receiver/arguments, and target exceptions tested?
9. Was performance measured before trading cache scope for speed?

## 9. Self-Check Questions

**Question 1.** If `trySetAccessible()` is enabled on a private method, and that `Method` is placed into a public cache, what is the primary risk?

**Answer:** Components that obtain a **reference to that access-enabled `Method`** can exercise that private-access capability; the remedy is keeping it inside a trusted component and exposing only a narrow business API.

**Question 2.** Does calling `setAccessible(false)` on a local `Method` revoke all handles already distributed?

**Answer:** No. It only changes the flag on that specific reflection object; it does not disable other independent capabilities or erase references already handed out.

**Question 3.** Why does using `ConcurrentHashMap` not solve all the risks?

**Answer:** A thread-safe map only protects map operations; the `Method` values inside still have their own accessible flag that can be mutated concurrently.

**Question 4.** Can `MethodHandles.privateLookupIn` replace access-scope management?

**Answer:** No. The resulting `Lookup` and private handles also carry capability; only hand them out within the necessary scope.

**Question 5.** Should you add `--add-opens ...=ALL-UNNAMED` whenever reflection is denied?

**Answer:** No. First identify who needs access, which package must be opened, and whether a public API or adapter can solve the problem.

**Takeaway:** **Cache metadata to save lookup cost, but keep private-access capabilities with the right owner and for the right duration.** In reflection, privilege resides in **how objects are created**, **their accessible state**, and **references you hand to other code**; performance optimization must never widen access scope beyond what is needed.

References: [`AccessibleObject` Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html), [`Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html), [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).