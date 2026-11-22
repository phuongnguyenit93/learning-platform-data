# 6.9. When Access Checks Occur and Responsibilities When Sharing a `Lookup` or Private Method Handle

`java.lang.invoke.MethodHandles.Lookup` and `java.lang.invoke.MethodHandle` are two object types that carry **access capabilities**, but they grant authority at two very different levels:

- **`Lookup`** can be used to **create additional** method handles/field handles/constructor handles for members permitted by that lookup's privileges.
- A **`MethodHandle`** that has already been created is a **capability to invoke a specific target** according to a defined `MethodType`. The recipient of the handle can invoke that target even if they themselves do not have sufficient privileges to create a similar handle.
- With factories such as `Lookup.findStatic`, `findVirtual`, `findGetter`, **access checking occurs when creating the handle**, based on the lookup class and the privileges of the `Lookup`. When using `invoke` or `invokeExact` on a valid handle, Java **does not re-check private/public access against each caller's class**.
- A handle's privileges **do not include exemption from type checks, business logic checks inside the target, or any other security checks**. The handle still has a `MethodType`, invocation can still throw exceptions, and the target code still runs as normal.

Therefore, when sharing a full-privilege `Lookup` with an untrusted component, you may inadvertently grant permission to **find many more private members**. When sharing a private method handle, you are allowing the recipient to **invoke the exact granted target** (including invoking it multiple times or at unintended times). Both are trust-boundary design decisions, not simply passing a Java object.

This lesson uses Java 17+ and a two-named-module experiment to demonstrate each point, then provides guidance on privilege separation and handling common pitfalls.

## 1. Whose Identity Does `MethodHandles.lookup()` Record?

The call:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
```

is an **illustrative code snippet**, requiring `import java.lang.invoke.MethodHandles;` in an appropriate class. `MethodHandles.lookup()` is a **caller-sensitive** method: the result is bound to **the class that actually calls it**, not whichever class later holds the `lookup` variable.

Each `Lookup` stores at least the following important concepts:

| Component | Meaning |
| --- | --- |
| `lookupClass()` | The class against which the lookup's access privileges are determined |
| `lookupModes()` | A bit mask of privilege levels, e.g. `PUBLIC`, `PACKAGE`, `PRIVATE`, `MODULE`, `PROTECTED`, `UNCONDITIONAL` |
| `previousLookupClass()` | The previous lookup class context when lookup privileges have crossed a module boundary; usually `null` for a direct `lookup()` |
| `hasFullPrivilegeAccess()` | Indicates whether the lookup has full privileges per the API contract to perform certain high-privilege operations |

A `MethodHandles.lookup()` created inside the caller's own class usually has full-privilege access for that class. This does **not** mean it automatically has access to every other class: when accessing another class/package/module, Java visibility rules, module readability, exports, and opens are still evaluated.

Important: a `Lookup` remains bound to **the privileges of the recorded lookup class**, even if you pass the `Lookup` reference to another object, another thread, another module, or store it in a cache. Passing the object does not automatically turn the lookup class into the recipient's class.

### Two Separate Points in Time

```text
Privileged Caller                       Other Consumer
      |                                     |
      | MethodHandles.lookup()              |
      v                                     |
  Lookup (records caller)                   |
      |                                     |
      | findStatic / findVirtual / ...      |
      | -- ACCESS CHECK HAPPENS HERE -->    |
      v                                     |
  MethodHandle created successfully         |
      |                                     |
      + ------------ pass handle ---------->|
                                            |
                                       invokeExact()
                                            |
                                    runs target method
                           (NO re-check of Consumer's
                            class access on invoke)
```

If the factory lacks sufficient privileges, it typically throws `IllegalAccessException` **before** returning a handle. If the factory returns a handle, subsequent invocations are subject to type rules and execution behavior, without requiring the caller to have direct access to the original private member.

## 2. Access Checks at Handle Creation, Type Checks at Invocation

A lookup wanting to create a handle to a member must check **multiple dimensions**:

1. Can a class and member with the right name/signature/operation kind be found?
2. Are that class and member accessible to the lookup class under Java access rules?
3. Which access modes does the lookup hold? Are `PRIVATE`, `PACKAGE`, `MODULE`, ... still valid?
4. If crossing a JPMS module boundary, are the appropriate `reads`, `exports`, or `opens` relationships established? Some special lookup modes have different rules, for example `publicLookup()` has `UNCONDITIONAL`.
5. For special APIs, are additional conditions met, such as `privateLookupIn` requiring a full-privilege lookup and appropriate openness?

Typical factories: `findStatic`, `findVirtual`, `findSpecial`, `findConstructor`, `findGetter`, `findSetter`, `findStaticGetter`, `findStaticSetter`, and the `unreflect*` variants. Variants can differ in how checks are performed; in particular, do not automatically infer `unreflect` rules from `findStatic`.

The standalone example in section 5 uses:

```java
MethodHandles.lookup().findStatic(
        VaultApi.class, "token", MethodType.methodType(String.class));
```

This is a **call snippet located inside the `VaultApi` class in the main example**, not runnable on its own. It looks up the **private static** method `String token()` with a `MethodType` taking no parameters and returning `String`.

After creating the `MethodHandle`, the consumer calls:

```java
String result = (String) handle.invokeExact();
```

which is also a **snippet using an existing `handle` variable**. `invokeExact` requires the call-site type to match the handle's `MethodType` exactly. Casting the result to `String` in the expression above is an important part of the call-site signature. A `WrongMethodTypeException` can occur if the call site is declared incorrectly, even when the caller has been granted a valid handle.

**Do not conflate two questions:**

- **Can the handle be created?** → Decided by the `Lookup`'s access check at creation time.
- **Will invoking the handle succeed?** → Depends on the call-site method type, receiver/arguments if any, the target method, runtime state, and exceptions thrown by the target.

A public wrapper containing an authorization check inside still performs that check every time the wrapper is invoked, even if a handle pointing to the wrapper was created earlier. A handle only skips re-checking **the Java language access of the handle itself**; it does not erase the target's business logic.

## 3. Comparison with Core Reflection

`java.lang.reflect.Method` and `MethodHandle` have different models:

| Comparison Point | Core Reflection (`Method`) | Method Handle |
| --- | --- | --- |
| Obtaining the representative object | `getMethod`, `getDeclaredMethod`, ... | `Lookup.find*`, `Lookup.unreflect*`, ... |
| Usual time of access check | `Method.invoke` checks against the caller at invocation time, unless access checks are suppressed | Checked at handle creation time using the lookup context |
| How deep access is granted | `setAccessible`/`trySetAccessible` when JPMS and access rules permit | `privateLookupIn` or a lookup with appropriate privileges |
| When passing the object to another caller | The caller of `Method.invoke` is still checked if not suppressed; if the accessible flag was validly enabled, the reflected object can also carry deep access | An already-created handle can be invoked by the recipient even if they cannot look up the original member themselves |
| Call typing | Typically via `Object`/boxing and errors at invocation | `MethodType`, `invokeExact`, or `invoke` with adaptation |
| Scope of privilege when shared | Depends on the reflected object and accessible flag | Only the granted handle or the entire handle-minting power of `Lookup` |

`Method.invoke` is not incapable of creating a capability: a `Method` whose accessible flag has been validly enabled must also be shared with care. This lesson simply emphasizes **the difference in where the access check occurs** and the scope of privilege when handing out a `Lookup`/handle.

When code already has a `Method` and calls `lookup.unreflect(method)`, keep its specific rules in mind: the accessible flag can affect how `unreflect` performs access checks. For directly testing when privileges are granted, `findStatic`/`findVirtual` should be used to reduce ambiguity.

## 4. Why Both `Lookup` and Private Handles Are Dangerous Capabilities If Distributed Indiscriminately

### 4.1. Handing Out a `Lookup` Is Equivalent to Handing Out a Tool to Mint More Privileges

Suppose a class has two private methods:

```java
private static String token() { return "TOKEN-42"; }
private static String internal() { return "INTERNAL"; }
```

These are just **two example declarations inside `VaultApi`**, not a complete standalone program.

If that class returns `MethodHandles.lookup()` to a client, the client receives a lookup object whose **lookup class is still the class with private privileges**. The client can use it to look up `token`, `internal`, and other members within the lookup's privilege scope. The lookup's privileges are not downgraded just because it crossed a public method or module boundary as a return value.

A full-privilege lookup can also be used for APIs that carry greater power than accessing private methods, depending on conditions such as `defineClass`, `defineHiddenClass`, `findSpecial`, ... Such an object should not be exported across a trust boundary just to let outsiders call one specific method.

### 4.2. Handing Out a `MethodHandle` Narrows the Scope but Still Grants Execution Authority

A handle pointing to `token()` only invokes that target; it does not itself provide an API to look up `internal()`. However, if the target mutates data, reads secrets, manipulates resources, or sends requests, the holder of the handle can cause **those exact side effects**.

Treat a handle as a **ticket to call a function**, not harmless metadata. The recipient can:

- Invoke it repeatedly, store it in a cache, or pass it along elsewhere.
- Change the timing and frequency of calls if you lack additional runtime checks.
- Use API-permitted combinators/adaptations to wrap or transform a granted handle, though this does not by itself let them find another private method.
- Receive data and exceptions that the target allows to escape, even though the target is private.

**The level of privilege granted must always be evaluated based on the effects of the target**, not merely the `private` modifier or the number of handles.

### 4.3. No Automatic Revocation Mechanism

`Lookup.dropLookupMode(...)` creates a **new Lookup** with reduced privileges. It **does not modify the original Lookup**, does not revoke already-issued MethodHandles, and does not cause references held elsewhere to automatically lose their privileges.

Even after a factory stops issuing new handles, private handles that were already distributed can still be used by their recipients. If an application needs to revoke privileges by account, time, or session, a state-checking layer must be designed **along the granted execution path**, rather than expecting to clear a Java variable or drop a lookup mode.

## 5. Java 17+ Practice: Proving When Access Is Checked

We create two **named modules**:

- `m.vault` contains private methods and decides privilege grants.
- `m.app` is the client, which `requires m.vault`, but is **not** granted deep reflection into package `demo.vault`.

Exact file structure:

```text
src/
├── m.vault/
│   ├── module-info.java
│   └── demo/vault/VaultApi.java
└── m.app/
    ├── module-info.java
    └── demo/app/Main.java
```

This example uses **four Java files**, with no external library dependencies. The `module-info.java` files are also compiled along with the rest of the source code.

**File `src/m.vault/module-info.java`:**

```java
module m.vault {
    exports demo.vault;
}
```

The package is exported so consumers can use the public `VaultApi`. It is **not** `opens` to the client, so the consumer does not automatically have deep reflection access to private methods.

**File `src/m.vault/demo/vault/VaultApi.java`:**

```java
package demo.vault;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class VaultApi {
    private static String token() {
        return "TOKEN-42";
    }

    private static String internal() {
        return "INTERNAL";
    }

    public static MethodHandle grantTokenCall()
            throws NoSuchMethodException, IllegalAccessException {
        return MethodHandles.lookup().findStatic(
                VaultApi.class, "token", MethodType.methodType(String.class));
    }

    // ANTI-PATTERN: do not export a full-privilege Lookup in production.
    public static MethodHandles.Lookup dangerousLookup() {
        return MethodHandles.lookup();
    }

    // New Lookup with PRIVATE dropped; does not affect already-issued handles.
    public static MethodHandles.Lookup reducedLookup() {
        return MethodHandles.lookup()
                .dropLookupMode(MethodHandles.Lookup.PRIVATE);
    }
}
```

`grantTokenCall` is called from outside, but **`MethodHandles.lookup()` is inside the body of `VaultApi`**, so the lookup class is `VaultApi`, which has permission to create a handle to its own private `token()`.

`dangerousLookup` is included to **demonstrate the capability-sharing flaw**; it is strictly not an API to copy into a real system.

**File `src/m.app/module-info.java`:**

```java
module m.app {
    requires m.vault;
}
```

The client reads the library module and uses the public API, but `requires` does not automatically grant permission to call private methods.

**File `src/m.app/demo/app/Main.java`:**

```java
package demo.app;

import demo.vault.VaultApi;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class Main {
    public static void main(String[] args) throws Throwable {
        var granted = VaultApi.grantTokenCall();
        System.out.println("handle=" + (String) granted.invokeExact());

        // A Lookup created in Main does not have VaultApi's private access.
        try {
            MethodHandles.lookup().findStatic(
                    VaultApi.class, "token",
                    MethodType.methodType(String.class));
            System.out.println("ownLookup=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("ownLookup=denied");
        }

        // Demonstrates the flaw: even an unintended private method can be looked up.
        var leaked = VaultApi.dangerousLookup();
        var other = leaked.findStatic(
                VaultApi.class, "internal",
                MethodType.methodType(String.class));
        System.out.println("sharedLookup=" + (String) other.invokeExact());

        // The new reduced Lookup cannot mint a handle to internal().
        var narrowed = VaultApi.reducedLookup();
        try {
            narrowed.findStatic(
                    VaultApi.class, "internal",
                    MethodType.methodType(String.class));
            System.out.println("reducedLookup=unexpected");
        } catch (IllegalAccessException expected) {
            System.out.println("reducedLookup=denied");
        }

        // The already-granted handle can still be invoked.
        System.out.println("oldHandle=" + (String) granted.invokeExact());
    }
}
```

### 5.1. Compile and Run

From the parent directory containing `src`, using JDK 17 or later:

```bash
javac --release 17 -d mods --module-source-path src src/m.vault/module-info.java src/m.vault/demo/vault/VaultApi.java src/m.app/module-info.java src/m.app/demo/app/Main.java
java --module-path mods -m m.app/demo.app.Main
```

Verified output by compiling with `--release 17` and running the two named modules:

```text
handle=TOKEN-42
ownLookup=denied
sharedLookup=INTERNAL
reducedLookup=denied
oldHandle=TOKEN-42
```

### 5.2. Interpreting the Five Lines of Output

1. **`handle=TOKEN-42`:** `VaultApi` created a handle to private `token()` using a privileged lookup; `m.app` received the reference and invoked it successfully without needing the package opened or being granted direct access to `token()`.
2. **`ownLookup=denied`:** the lookup created in `Main` only carries the privileges of `demo.app.Main`. Even though `m.app` `requires m.vault`, `exports demo.vault` only grants access to the public API, not private access. `findStatic` throws `IllegalAccessException`.
3. **`sharedLookup=INTERNAL`:** `Main` received **`VaultApi`'s entire `Lookup`** through a public method. With that lookup, it was able to create a handle to **another private method (`internal`)** that was never intended to be granted. This is why you must not leak a full-privilege lookup.
4. **`reducedLookup=denied`:** `dropLookupMode(PRIVATE)` returns a downgraded lookup so it cannot create a handle to a new private method. You should not assume that returning a reduced lookup is definitely safe for every API; you must evaluate the remaining modes and public/package/module privileges.
5. **`oldHandle=TOKEN-42`:** the already-granted handle remains valid. Creating a downgraded lookup does not revoke the old handle, even when the code hands the new lookup to the consumer.

Note: this is an **experiment on Java access control and capability sharing**, not a secure business authorization model. The public `grantTokenCall` in the example hands out the handle to **any caller** allowed to call the public API; a real application must have a policy controlling who is allowed to receive it.

## 6. Detailed Access-Checking Mechanisms in `Lookup`

### 6.1. Lookup Class and Lookup Modes Are Two Independent Constraints

To evaluate a Lookup:

```java
Class<?> owner = lookup.lookupClass();
int modes = lookup.lookupModes();
boolean full = lookup.hasFullPrivilegeAccess();
```

This is an illustrative snippet using an existing `lookup` variable, not a standalone program. `lookupClass()` is the identity used in access checks; `lookupModes()` describes the types of privileges still held; `hasFullPrivilegeAccess()` is a general query per the API contract.

A `Lookup` can retain a privileged lookup class while having reduced modes. For example, `VaultApi.reducedLookup()` is still bound to `VaultApi` but cannot create handles to private members. Conversely, a full-privilege lookup of `Main` does not automatically access private members of `VaultApi` because it is bound to **a different class**.

**Do not hardcode `lookupModes` as a fixed integer** across Java versions. Use constant names and APIs to check; `dropLookupMode` also has rules for removing dependent modes.

### 6.2. `dropLookupMode` Creates a Lower-Privilege Object

`lookup.dropLookupMode(MethodHandles.Lookup.PRIVATE)` returns a **new Lookup**. Any references still holding the original `lookup` retain the original object's privileges.

Practical privilege-reduction guidelines:

- Only retain the access levels needed for the assigned task.
- Do not return a full lookup from a public API just to help a client call a public member; the client can use `MethodHandles.publicLookup()` when in scope, or a restricted wrapper/factory.
- If providing a lookup to a trusted framework, consider `dropLookupMode`, `Lookup.in(...)`, and module boundaries, and verify which APIs the new lookup **can actually** use.
- If exactly one action is needed, returning **a specific handle or small interface** is usually easier to control than handing out a tool to look up more members.

`Lookup.in(SomeClass.class)` can also reduce privileges when switching the lookup class. It does **not** automatically escalate privileges; when crossing modules, `previousLookupClass` and related restrictions are also taken into account.

### 6.3. `privateLookupIn` Differs from Exporting the Original Lookup

`MethodHandles.privateLookupIn(target, callerLookup)` can create a lookup on the target class when conditions are met. Across two different named modules on Java 17+, the caller's module must **read** the target module, the target's package must be **opened** (`opens`) to the caller module, and the caller lookup must have appropriate `PRIVATE` and `MODULE` modes.

It is not a "trick" for an unprivileged consumer to obtain a private lookup of another module on its own. In the example, `m.vault` only `exports demo.vault`; it **does not `opens` the package**, so `m.app` cannot use `privateLookupIn` by itself to read `VaultApi`'s private methods.

If the target's owner **voluntarily returns a full-privilege `Lookup`** through a public method, they have directly **delegated that capability**, regardless of whether the package is `opens`. This is the exact danger: module openness protects the process of **self-acquiring privileges** through the API, but it does not revoke a capability that the owner intentionally or accidentally gave away.

### 6.4. `publicLookup()` and the `UNCONDITIONAL` Exception

`MethodHandles.publicLookup()` has the `UNCONDITIONAL` mode, which assumes module readability but only creates handles for public members of public classes in packages that are **unconditionally exported**.

Because it does not grant `PRIVATE`, it cannot look up `VaultApi.token()` in the example. It can be suitable for creating shared public handles when the target is genuinely a public API, though qualified exports and caller-sensitive members require separate consideration.

Do not treat `publicLookup` as an automatic drop-in replacement for every lookup: it has a narrow scope and does not have full privileges.

## 7. Responsibilities of the Creator and the Recipient of Privileges

### The Side That **Creates/Grants** the Capability

The owner of a private member must decide explicitly:

1. **Who is allowed to receive it?** An exported module does not mean all code is entitled to manipulate confidential content; a public factory needs an authorization mechanism if the target holds privileged data or actions.
2. **What should be granted?** If only one operation is needed, grant a handle to a **narrowly scoped wrapper** or an interface-style API; avoid returning a full-privilege `MethodHandles.lookup()`.
3. **Is a per-call check needed?** If permission depends on session, role, quota, feature flag, or changing state, place the check on the actual invocation path. Checking only when issuing the handle is not enough to protect future calls.
4. **Which resources can be affected?** A private method handle can mutate state, perform I/O, allocate memory, or call external systems. Constrain side effects and inputs according to the application's contract.
5. **Can it be forwarded or stored?** Java does not automatically forbid the recipient from keeping a reference or passing the handle to someone else. Design under the assumption that the handle may outlive the initial request, unless the application layer controls its usage.
6. **Resilience to refactoring:** a handle already bound to the original method does not automatically morph into a new target if code changes or hot reload happens later. Do not treat a handle as a name string that re-resolves on every invocation.

### The Side That **Receives/Uses** the Capability

- Only invoke within the scope of the granted work; do not assume that having a Java object means every usage is permitted by business rules.
- Do not publish a `Lookup`, a private `MethodHandle`, or an object containing them into a global registry, plugin registry, shared cache, event bus, or logs if that crosses a trust boundary.
- Check `handle.type()` and use the matching signature; avoid confusing a `WrongMethodTypeException` with an access-privilege error.
- Do not pass a private capability onward to an untrusted library just because the library needs "a callback". Consider a wrapper that only exposes permitted results/operations.
- Do not confuse a handle that fails to invoke due to a wrong `MethodType` with a revoked handle. Type mismatch is different from authorization.

### Least Privilege: Quick Selection Table

| Actual Need | Object to Provide | Level of Authority Granted |
| --- | --- | --- |
| External code calls a normal public method | Public method/interface | No private capability needed |
| A trusted framework must look up certain members per contract | Restricted `Lookup`, when truly needed; inspect `lookupModes` | Must audit the scope of handles it can create |
| Consumer only needs to call one specific private operation | An intentionally granted `MethodHandle` or wrapper | Grants authority to invoke the chosen target |
| Per-call permission may change by policy | Wrapper/service checking policy on every execution | Continuous control at runtime |
| Multiple internal secret operations are needed | Keep the full lookup inside the owner's module; create handles internally | Avoids exporting a privilege-minting tool across boundaries |
| Plugin only needs to receive events | Public callback interface and minimal DTOs | Does not expose a private lookup or handle |

The principle of least privilege applies to both the **lookup** level (authority to create more handles) and the **handle** level (authority to execute one target). Evaluating both levels together prevents confusion.

## 8. Revoking Privileges and Per-Call Checking

A very common misconception is:

> "I stopped handing out `Lookup`, so the private method handles issued earlier will stop working."

Incorrect. A handle that has already been created is a usable reference; it does not automatically expire because the factory stops operating. `dropLookupMode` downgrades **a new Lookup**; it does not know who holds old handles to revoke them. Changing exports/opens or the issuance policy after creation time should also not be assumed to invalidate existing handles.

If the application requires revocation, you can implement a **wrapper that checks policy on every call**. The following pseudocode illustrates the business logic, **not a standalone Java program**:

```java
String guardedOperation(Request request) {
    if (!policy.isAllowed(request.actor(), request.operation())) {
        throw new SecurityException("Operation denied");
    }
    return internalOperation(request);
}
```

If the handle points to `guardedOperation`, the policy code runs when the target executes. But if external code still holds a handle directly to `internalOperation`, it can bypass the wrapper. Therefore, **do not issue an unguarded handle** and hope another guard will protect it.

Mechanisms that can be used depending on architecture: interface facade, authorization service, capability object with liveness state, quota, deadline, or proxy checked on each invocation. For true revocation, there must be a point through which **every granted invocation path** is forced to pass for checking. If sensitive data has already been returned before revocation, Java cannot take back that copy of the data.

`MethodHandle` is not a security-specific primitive: it is an invocation tool whose language access is checked at creation time. The application itself is responsible for authentication, authorization, auditing, and capability lifecycle.

## 9. Related Issues to Distinguish

### 9.1. `invoke` and `invokeExact` Do Not Re-Check Private Access, but Still Check Types

`invokeExact` requires the exact method type at the call site. `invoke` allows some type adaptation per `MethodHandle` rules, but that does not mean any string or any object is automatically converted to the right type.

Exceptions such as `WrongMethodTypeException`, `ClassCastException`, `NullPointerException`, or exceptions thrown by the target are different errors from `IllegalAccessException` when **creating** the handle. Where the exception originates is very important when debugging.

### 9.2. Instance Handles Still Require an Appropriate Receiver

A private instance method handle may require a receiver that is an object of the right class or a compatible subtype (depending on the handle and how adapters were created). Granting the handle does not automatically grant a receiver object; however, if the consumer has an appropriate receiver or the handle has been `bindTo` a receiver, they can trigger the granted operation.

`bindTo`, `insertArguments`, `asType`, `filterArguments`, and other combinators can reshape the call site or fix arguments. They do not by themselves give the consumer permission to look up a second private method, but they can alter how the granted handle is used. Therefore, handle-granting design must consider both the data and the objects the handle can act upon.

### 9.3. `VarHandle` Also Carries Capability Semantics

`Lookup.findVarHandle` and `findStaticVarHandle` create a `VarHandle` for a field when the lookup has permission. When granting a `VarHandle` to a private field, the recipient can perform the access modes permitted by the VarHandle, field type, modifiers, and runtime. Do not assume it is merely readable metadata.

For example, a final field does not automatically become writable just because a `VarHandle` is returned. For a mutable field, the recipient may gain additional concurrency/memory-access operations; think carefully before exposing this capability.

### 9.4. Caller-Sensitive Methods Require Extra Caution

Some Java APIs are **caller-sensitive**, meaning their behavior depends on the caller identified by runtime rules. When creating a method handle to such APIs, `Lookup` has specific rules regarding caller context; `publicLookup()` cannot always be used to create such a handle.

Therefore, you should not assume a handle to every public API behaves identically to Java code calling it directly from any client. For frameworks that provide reusable method handles, explicitly check whether the API has caller-sensitive behavior.

### 9.5. Granting a `Lookup` Does Not Mean the Recipient's Privileges Are Arbitrarily Combined

A Lookup is a capability with **recorded privileges**. A client receiving `VaultApi`'s full Lookup can use the privileges of that lookup class, but it does not automatically merge with the client's full privileges to form "super-privileges" of both modules. `Lookup.in`, `privateLookupIn`, and module conditions still precisely determine the boundaries of any derived lookups.

Even so, the inherent privileges of the original lookup are already dangerous enough if they allow looking up additional private members that the provider did not intend to grant.

## 10. How to Debug and Audit When a Private Handle Runs Where There Is "No Access"

When a private method is successfully invoked from a class that could not compile a direct call, determine:

1. **Where was the handle created?** Look for factories like `findStatic`, `findVirtual`, `unreflect`, or adapters; do not only look at the `invokeExact` site.
2. **Where did the `Lookup` originate?** Was it `MethodHandles.lookup()` in a class with private access, `privateLookupIn`, or a lookup object passed from another module?
3. **What are the lookup class and modes?** Inspect `lookupClass()`, `lookupModes()`, `previousLookupClass()` where appropriate; avoid logging unnecessary information about internal systems.
4. **Which object was shared?** A full `Lookup`, a reduced `Lookup`, or a specific handle? A full lookup can create more private handles later.
5. **Was there a prior successful access check?** If so, invoking from a less-privileged class **does not prove** a JVM bug; that is the capability semantics designed by Java.
6. **Does the target check policy itself?** If the target does not check privileges on every call, the initial handle-granting decision is the primary control point.
7. **Are references leaking?** Check caches, registries, plugin hooks, lambda captures, and APIs returning these objects.
8. **Is the error truly an access error?** Distinguish `IllegalAccessException` at handle creation from `WrongMethodTypeException`/target exceptions at invocation.
9. **Where should the fix go?** Narrow the factory and granting contract, wrap the target with a policy check, restrict receivers/arguments, or keep all privileged handles inside a trusted module.

Do not try to solve this by adding `--add-opens` or calling `setAccessible(true)` before identifying where the privilege was granted. Those flags address module access issues in specific scenarios, but they **do not** fix a provider actively leaking a `Lookup` or handle.

## 11. Common Conceptual Pitfalls

| Wrong Conclusion | Fact to Remember |
| --- | --- |
| "The caller cannot see the private method, so it cannot invoke the handle." | Once it has received a valid handle, the caller can invoke it without re-looking up the private member itself |
| "Putting `Lookup` in a public API is just like giving out a `MethodHandle`." | A Lookup can create additional handles for other members within its privilege scope |
| "`MethodHandles.lookup()` returns the recipient's privileges after being passed through a method." | Lookup records the class that called `lookup()` at creation time |
| "`dropLookupMode` mutates the old Lookup in place." | It returns a new Lookup with reduced privileges |
| "Downgrading a Lookup invalidates already-issued handles." | Already-created handles are not automatically revoked |
| "Handing out a private handle is completely safe because it only calls one method." | The target may contain sensitive logic or side effects; the consumer can invoke it multiple times and forward the handle |
| "MethodHandle bypasses all Java checks." | Only language access was handled at creation; method type and target logic still apply |
| "Reflection and MethodHandle always check at the same time." | `Method.invoke` usually checks the caller's access at invocation time; MethodHandle factories check at creation time |
| "Just exporting the public API lets the client obtain a private Lookup on its own." | `exports` does not mean `opens` or private access |
| "If `invokeExact` fails, it must be missing access." | A call-site type error can happen after a valid handle has already been created |

## 12. End-of-Lesson Self-Check

1. `VaultApi.grantTokenCall()` is called from `Main`. What is the lookup class of `MethodHandles.lookup()` in that method? **`VaultApi`**, because the call site of `lookup()` is inside `VaultApi`.
2. Why can `Main` call `granted.invokeExact()` but cannot call `findStatic` on private `token()` itself? **The handle was validly granted by the provider; looking up the method again is a new access check using `Main`'s lookup.**
3. Why is `VaultApi.dangerousLookup()` more dangerous than `grantTokenCall()`? **It gives the client the ability to create other handles, for example to `internal()`.**
4. Does `dropLookupMode(PRIVATE)` on a lookup revoke handles already granted by the original lookup? **No.**
5. `m.app` has `requires m.vault` and the package is `exports`; does that automatically grant private access? **No.**
6. If you want to prevent a user whose session has expired from continuing to invoke a handle, where should the policy be placed? **In the execution path that every granted call goes through, such as a wrapper checked on every invocation, while not exposing a raw bypass handle.**
7. Does `invokeExact()` throwing `WrongMethodTypeException` prove that private access was denied? **No; this error relates to the call-site type.**
8. When sharing a `Lookup`, can you assume the privileges automatically transfer to the receiving class? **No; the lookup class and modes remain bound to the created object.**
9. When a library only needs public methods, why is `publicLookup()` or a public interface usually more suitable than a full lookup? **They narrow privileges to the public API, avoiding granting the capability to create private handles.**
10. Is a private method handle "safe" just because its `MethodType` has no parameters? **No; a zero-parameter method can still read sensitive data or cause side effects.**

## 13. Official Documentation

- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): Access checking section and invocation capability from a caller receiving a handle.
- [Java SE 17 — `MethodHandles`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `lookup()`, `publicLookup()`, `privateLookupIn`, and caller-sensitive behavior.
- [Java SE 17 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): lookup class, access modes, timing of factory access checks, `dropLookupMode`, `in`, `find*`.
- [Java SE 17 — `MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): parameter/return-type signature of a method handle.
- [Java SE 17 — `AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): access checks and `setAccessible`/`trySetAccessible` of Core Reflection.

**Practical Rule:** Treat **creating `Lookup` → using `Lookup` to mint a handle → sharing the handle → executing the handle** as distinct authorization steps. Access to a private member is evaluated primarily **when minting the handle**; afterward, the handle is an already-granted execution authority. To protect the system, control **who receives it, the capability's scope, its lifecycle, and per-use checking policies**.