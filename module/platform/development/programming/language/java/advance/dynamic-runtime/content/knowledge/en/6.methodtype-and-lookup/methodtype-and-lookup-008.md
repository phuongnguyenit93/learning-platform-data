# 6.8 Switching Context with `Lookup.in`, `dropLookupMode`, and `privateLookupIn`

**Context:** Java Advance → dynamic-runtime → 6. MethodType and Lookup.

In `java.lang.invoke`, `MethodHandles.Lookup` determines which members a program is allowed to **create a `MethodHandle` to**. When building frameworks, plugins, dependency injection, serializers, or runtime adapters, we often need to switch the lookup context from one class to another or grant a subset of lookup privileges to other code. The three key APIs are:

- `lookup.in(Target.class)`: changes the **lookup class**, and may simultaneously reduce privileges across nest/package/module boundaries.
- `lookup.dropLookupMode(MODE)`: actively **removes a privilege** from a lookup.
- `MethodHandles.privateLookupIn(Target.class, callerLookup)`: requests a lookup with **private access on the target**, but only if the original privileges and module rules allow it.

The three APIs are not synonymous. **`in` does not elevate privileges**, **`dropLookupMode` only reduces privileges**, whereas **`privateLookupIn` can create private access in the target context after validating eligibility**. All examples here use Java 17+ and clearly separate standalone code from snippets.

## 1. Why Must `Lookup` Be Understood as a Capability?

`MethodHandles.lookup()` returns an object carrying the context and lookup privileges bound to **the class that calls that method**. This is a **caller-sensitive** API: calling it in class `A` produces a different result from calling it in class `B`. It should not be thought of as a stateless utility object or a JVM-wide finder.

A `Lookup` stores the following main elements:

- `lookupClass()`: the class acting as the **subject** of the lookup; permission checks are based on this class.
- `lookupModes()`: a bit mask restricting the privilege levels that the lookup can use.
- `previousLookupClass()`: the previous lookup class in **another module** when the lookup has crossed a module boundary; may be `null`.
- `hasFullPrivilegeAccess()`: indicates whether the lookup has both `PRIVATE` and `MODULE`; this is an essential condition when using `privateLookupIn`.

For example, a lookup created directly inside `demo.a.LookupDemo` typically has strong privileges for members that `LookupDemo` is allowed to access according to Java, including private members of the class itself or its nestmates. If that entire lookup is handed over to untrusted code, the recipient can use that same capability to obtain handles to sensitive members within the granted privilege scope.

**Difference from Core Reflection:** With `MethodHandles.Lookup.findStatic`, `findVirtual`, `findGetter`, etc., access rights are checked primarily at the time of **creating the direct method handle**. Once the handle is validly created, calling `invokeExact` does not re-run the same caller-based access check like `java.lang.reflect.Method.invoke`. Therefore, privilege restrictions must be placed **before issuing the `Lookup` or `MethodHandle`**, not just checked at invocation time.

### Lookup modes in Java 17

| Bit | Name | General meaning |
| --- | --- | --- |
| `PUBLIC` | Public mode | Allows public lookups according to visibility, module readability, and appropriate exports |
| `PRIVATE` | Private mode | Ability to access private members of the lookup class/nestmates and corresponding privileged operations |
| `PROTECTED` | Protected mode | Protected access appropriate to inheritance context, with receiver constraints |
| `PACKAGE` | Package mode | Package-private access within the appropriate runtime package |
| `MODULE` | Module mode | Authenticates the original module context; supports finding public types in the same module and is a condition for deep lookup |
| `ORIGINAL` | Original mode | Marks a lookup created by the original caller (`lookup()`) or bootstrap provided by the JVM; special privileges, such as caller-sensitive |
| `UNCONDITIONAL` | Unconditional mode | Characteristic of `publicLookup()`; accesses public members of public types in **unconditionally** exported packages, without requiring module readability like a regular lookup |

`PRIVATE` and `MODULE` are **two different privileges**. A lookup that has `PRIVATE` but has lost `MODULE` can still create handles to private members in certain already-granted contexts, but **cannot use that same lookup to request a deep lookup into another class via `privateLookupIn`**.

`ORIGINAL` is not "a higher public level"; it confirms the caller's origin. `MethodHandles.publicLookup()` has `UNCONDITIONAL`, **and does not have the `PUBLIC` bit** according to `lookupModes()`, even though it can still look up many public methods in unconditionally exported packages. Therefore, do not check "whether public calls are allowed" solely with the expression `(lookup.lookupModes() & PUBLIC) != 0` when `publicLookup()` is involved.

## 2. `Lookup.in(Target.class)`: Switching the Lookup Class, Not Elevating Privileges

Signature:

```java
MethodHandles.Lookup changed = original.in(Target.class);
```

`changed.lookupClass()` is `Target.class`, but `changed` **cannot have more capabilities than `original`**. The JVM adjusts the access modes based on the relationship between the old lookup class and the target:

| Relationship when switching via `in` | Consequence to remember |
| --- | --- |
| Calling `in` on the current lookup class itself | Does not change the class; the API may return the original lookup itself |
| Switching to another class **in the same nest** | Can retain `PRIVATE`; `ORIGINAL` is lost when it is no longer the original class |
| Switching to a class in the same runtime package but **a different nest** | Loses `PRIVATE`; may retain `PACKAGE`, `MODULE`, and public access |
| Switching to a class in a different package but the same module | Loses `PRIVATE` and `PACKAGE`; `MODULE` may remain; public accessibility is still checked |
| Switching to a class in a different module | Loses `MODULE`; records `previousLookupClass`; public access is checked against both modules |
| Switching to a target class that the lookup is not allowed to access | Access modes can drop to **0**, including public access |

The table describes typical cases starting from a full original lookup; modes that were previously dropped do not reappear on their own. In particular, switching to a subclass in another package **does not automatically grant the new lookup private access to the subclass**.

### Nestmates, same package but different nest

Java 11+ defines nests: classes belonging to the same nest have access to each other's private members. A nested class declared inside an outer class is typically a nestmate of the outer class. In the example in section 5, `LookupDemo` and `LookupDemo.NestedTarget` are in the same nest, so `root.in(NestedTarget.class)` **still has `PRIVATE`**. Conversely, `Peer` is a separate top-level class in the same package: `root.in(Peer.class)` **loses `PRIVATE`** while still retaining `PACKAGE`.

Nestmates must be distinguished from two classes that merely share the same package name; **the same runtime package is not the same nest**. If code needs private access to a class in the same package but a different nest, evaluate `privateLookupIn` according to the conditions in section 4.

### Cross-module movement and `previousLookupClass()`

Suppose `Client` belongs to module `beta` and `Gateway` belongs to module `alpha`. When calling `lookup.in(Gateway.class)`:

- The new lookup class is `Gateway`.
- `MODULE` is removed.
- `previousLookupClass()` records `Client`, the class originating from module `beta`.
- `PUBLIC` access (if remaining) is subject to the condition that both the `alpha` side and the `beta` side can publicly access the corresponding type.

If a lookup has already switched between two modules and then switches to **a third module** not belonging to the previous pair, Java 17 may drop **all access modes**. Calling `in` repeatedly is **not** a chain to accumulate more privileges or bypass module conditions. `Lookup.in` with `int.class`, `void.class`, or an array class throws `IllegalArgumentException`; passing `null` throws `NullPointerException`.

## 3. `dropLookupMode(MODE)`: Controlled Privilege Reduction

Signature:

```java
MethodHandles.Lookup restricted =
        original.dropLookupMode(MethodHandles.Lookup.PRIVATE);
```

This method keeps `lookupClass()` unchanged and returns a lookup that can only have **fewer privileges**. It does not interfere with the privileges of the original lookup, does not modify class or member modifiers, and does not revoke previously issued `MethodHandle`s.

**Modes are not completely independent when dropped.** In Java 17, for a normal lookup (not `publicLookup()`), dropping one bit can entail dropping other bits. In addition to the requested bit, `PROTECTED` and `ORIGINAL` **are always removed** in the result of `dropLookupMode`:

| Request | Typical remaining bits from a full lookup |
| --- | --- |
| `dropLookupMode(PROTECTED)` | `PRIVATE + PACKAGE + MODULE + PUBLIC` |
| `dropLookupMode(PRIVATE)` | `PACKAGE + MODULE + PUBLIC` |
| `dropLookupMode(PACKAGE)` | `MODULE + PUBLIC` |
| `dropLookupMode(MODULE)` | `PUBLIC` |
| `dropLookupMode(PUBLIC)` | No access modes remaining |
| `dropLookupMode(ORIGINAL)` | `PRIVATE + PACKAGE + MODULE + PUBLIC` |

These are the typical states when **starting from a full lookup**; if the lookup is already degraded, no transformation "restores" a lost bit. Special case: `publicLookup()` only has `UNCONDITIONAL`; `dropLookupMode(UNCONDITIONAL)` from that lookup produces a lookup with no lookup privileges left.

Why does `dropLookupMode(PACKAGE)` also remove `PRIVATE`? Retaining private access in a context that has lost package access could leak unintended capabilities. Similarly, dropping `MODULE` must remove modes carrying module/package/private privileges. This is **grouped privilege downgrading** guaranteed by the API, not a bitwise bug.

### Safe example when granting privileges to a component

```java
MethodHandles.Lookup full = MethodHandles.lookup();
MethodHandles.Lookup publicOnly =
        full.dropLookupMode(MethodHandles.Lookup.MODULE);
```

In the snippet above, `publicOnly` retains the caller's `lookupClass` but loses `PRIVATE`, `PACKAGE`, `MODULE`, `PROTECTED`, and `ORIGINAL`. It is useful when a subsystem should only look up appropriate public members. If you only want other code to look up **unconditionally** exported public APIs without carrying the caller's module context, consider `MethodHandles.publicLookup()`.

**Note:** Dropping bits does not revoke **already created** method handles. If `full.findStatic(Secret.class, "hidden", ...)` previously returned a valid `MethodHandle`, that handle can still be invoked after another lookup has been downgraded. Both shared **handles** and shared **lookups** need to be controlled.

## 4. `MethodHandles.privateLookupIn(Target.class, callerLookup)`

Signature:

```java
MethodHandles.Lookup deep =
        MethodHandles.privateLookupIn(Target.class, callerLookup);
```

This API grants a lookup whose `lookupClass()` is `Target` and which has `PRIVATE` on the target, **after** checking the conditions. In Java 17, the caller lookup must have both `PRIVATE` and `MODULE` (full privilege access), and the target must be a valid class/interface, **not** a primitive, void, or array.

### Within the same module

If the caller lookup has full privilege and the target is in the **same module**, `privateLookupIn` can return a lookup with private capability on the target, even if the target is in another package or another nest. No `opens` to another module is needed in this case. The result can have `PRIVATE`, `PACKAGE`, `MODULE`, `PUBLIC`, and `PROTECTED`, but not `ORIGINAL`.

In the example in section 5, `root.in(Peer.class)` loses `PRIVATE`, whereas `MethodHandles.privateLookupIn(Peer.class, root)` receives **a lookup granted private access specifically on `Peer`**, because `root` is a full lookup and both classes are in the unnamed module.

### Across modules

When the target is in another module, all of the following are required simultaneously:

1. The caller lookup has `PRIVATE` **and** `MODULE`.
2. The caller's module **reads** the target's module.
3. The target's module **opens** the package containing the target to the caller's module (not just `exports` public API).
4. The target is a valid class/interface; when a SecurityManager environment applies, security checks must permit it.

When granted across modules, the resulting lookup has `PRIVATE` on the target and records `previousLookupClass()` as the source class, but **loses `MODULE`**. Therefore, `privateLookupIn` cannot be called again from that resulting lookup to transfer privileges to another target: `MODULE` is missing. This is a boundary against uncontrolled deep privilege forwarding.

`privateLookupIn` throws `IllegalAccessException` when privilege/module conditions are not met. Passing a primitive, void, or array as target causes `IllegalArgumentException`; passing `null` can cause `NullPointerException`. Calling `privateLookupIn` with `MethodHandles.publicLookup()` will fail due to lacking `PRIVATE` and `MODULE`.

### `exports` and `opens` are not equivalent

- `exports p`: allows other modules to compile against/access the **public API** of package `p` (with appropriate module readability).
- `opens p to m`: allows module `m` deep reflective access to package `p` according to API rules; it does not turn every private member into a public Java API.
- `--add-opens alpha/alpha.internal=beta`: a launch option that can open a package of module `alpha` to module `beta` for diagnostics or integration. Real projects should prefer purposefully designed `opens ... to ...`.
- `exports` alone is **not sufficient** for `privateLookupIn` to a public class in another module when the package is not open. The experiment in section 6 demonstrates this case.

## 5. Standalone Java 17 Demo: Switching Class, Dropping Privileges, and Granting Privileges in the Same Module

**Objective:** compare same nest vs. same package different nest; check `PRIVATE`, `PACKAGE`, `MODULE`, `PUBLIC`, `ORIGINAL`; confirm that a dropped lookup cannot grant private access; verify that a handle created before dropping can still be invoked.

Create three files:

```text
lookup-demo/
└── demo/
    ├── a/
    │   ├── LookupDemo.java
    │   └── Peer.java
    └── b/
        └── PublicPeer.java
```

All three classes are on the **classpath** (unnamed module). Specifically, `NestedTarget` is a static nested class of `LookupDemo`, while `Peer` is a separate top-level class in `demo.a`.

### File `demo/a/LookupDemo.java`

```java
package demo.a;

import demo.b.PublicPeer;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandles.Lookup;

import static java.lang.invoke.MethodHandles.Lookup.*;

public class LookupDemo {
    public static class NestedTarget {
        private static String hidden() { return "nested-secret"; }
        static String packageValue() { return "nested-package"; }
        public static String shown() { return "nested-public"; }
    }

    private static boolean has(Lookup l, int bit) {
        return (l.lookupModes() & bit) != 0;
    }

    private static void show(String label, Lookup l) {
        System.out.println(label + " class=" + l.lookupClass().getSimpleName()
            + " PRI=" + has(l, PRIVATE)
            + " PAC=" + has(l, PACKAGE)
            + " MOD=" + has(l, MODULE)
            + " PUB=" + has(l, PUBLIC)
            + " ORI=" + has(l, ORIGINAL));
    }

    private static void probe(String label, Lookup l, Class<?> owner, String name) {
        try {
            MethodHandle m = l.findStatic(owner, name, MethodType.methodType(String.class));
            System.out.println(label + "=" + (String) m.invokeExact());
        } catch (IllegalAccessException ex) {
            System.out.println(label + "=IllegalAccessException");
        } catch (NoSuchMethodException ex) {
            System.out.println(label + "=NoSuchMethodException");
        } catch (Throwable ex) {
            throw new RuntimeException(ex);
        }
    }

    public static void main(String[] args) throws Throwable {
        Lookup root = MethodHandles.lookup();
        Lookup sameNest = root.in(NestedTarget.class);
        Lookup samePackage = root.in(Peer.class);
        Lookup otherPackage = root.in(PublicPeer.class);
        Lookup hiddenTarget = root.in(PublicPeer.hiddenClass());
        Lookup noPrivate = root.dropLookupMode(PRIVATE);
        Lookup noPackage = root.dropLookupMode(PACKAGE);
        Lookup noModule = root.dropLookupMode(MODULE);
        Lookup noPublic = root.dropLookupMode(PUBLIC);

        show("root", root);
        show("same-nest", sameNest);
        show("same-package", samePackage);
        show("other-package", otherPackage);
        show("in-inaccessible", hiddenTarget);
        show("drop-private", noPrivate);
        show("drop-package", noPackage);
        show("drop-module", noModule);
        show("drop-public", noPublic);

        MethodType str = MethodType.methodType(String.class);
        MethodHandle acquiredBeforeDrop = root.findStatic(NestedTarget.class, "hidden", str);
        probe("same-nest private", sameNest, NestedTarget.class, "hidden");
        probe("same-package peer-private", samePackage, Peer.class, "hidden");
        probe("same-package peer-package", samePackage, Peer.class, "packageValue");
        probe("other-package public", otherPackage, PublicPeer.class, "shown");
        probe("other-package peer-package", otherPackage, PublicPeer.class, "packageValue");
        probe("dropped-private secret", noPrivate, NestedTarget.class, "hidden");
        System.out.println("existing-handle=" + (String) acquiredBeforeDrop.invokeExact());

        Lookup delegated = MethodHandles.privateLookupIn(Peer.class, root);
        show("privateLookupIn-peer", delegated);
        probe("privateLookupIn peer-private", delegated, Peer.class, "hidden");
        try {
            MethodHandles.privateLookupIn(Peer.class, noPrivate);
        } catch (IllegalAccessException ex) {
            System.out.println("privateLookupIn after drop-private=IllegalAccessException");
        }
        try {
            MethodHandles.privateLookupIn(Peer.class, noModule);
        } catch (IllegalAccessException ex) {
            System.out.println("privateLookupIn after drop-module=IllegalAccessException");
        }
        try {
            root.in(int.class);
        } catch (IllegalArgumentException ex) {
            System.out.println("in-primitive=IllegalArgumentException");
        }

        Lookup publicLookup = MethodHandles.publicLookup();
        System.out.println("publicLookup UNCOND=" + has(publicLookup, UNCONDITIONAL)
            + " PUB=" + has(publicLookup, PUBLIC));
        probe("publicLookup nested", publicLookup, NestedTarget.class, "shown");
        probe("publicLookup peer-package", publicLookup, Peer.class, "packageValue");
    }
}
```

### File `demo/a/Peer.java`

```java
package demo.a;

public class Peer {
    private static String hidden() { return "peer-secret"; }
    static String packageValue() { return "peer-package"; }
}
```

### File `demo/b/PublicPeer.java`

```java
package demo.b;

class HiddenClass {
    public static String shown() { return "hidden-public"; }
}

public class PublicPeer {
    public static String shown() { return "other-public"; }
    static String packageValue() { return "other-package"; }
    public static Class<?> hiddenClass() { return HiddenClass.class; }
}
```

**Compile and run** from the `lookup-demo/` directory. Use explicit file paths so the commands are also easy to run in Windows PowerShell:

```bash
javac --release 17 -encoding UTF-8 -d out demo/a/LookupDemo.java demo/a/Peer.java demo/b/PublicPeer.java
java -cp out demo.a.LookupDemo
```

**Exact stdout:**

```text
root class=LookupDemo PRI=true PAC=true MOD=true PUB=true ORI=true
same-nest class=NestedTarget PRI=true PAC=true MOD=true PUB=true ORI=false
same-package class=Peer PRI=false PAC=true MOD=true PUB=true ORI=false
other-package class=PublicPeer PRI=false PAC=false MOD=true PUB=true ORI=false
in-inaccessible class=HiddenClass PRI=false PAC=false MOD=false PUB=false ORI=false
drop-private class=LookupDemo PRI=false PAC=true MOD=true PUB=true ORI=false
drop-package class=LookupDemo PRI=false PAC=false MOD=true PUB=true ORI=false
drop-module class=LookupDemo PRI=false PAC=false MOD=false PUB=true ORI=false
drop-public class=LookupDemo PRI=false PAC=false MOD=false PUB=false ORI=false
same-nest private=nested-secret
same-package peer-private=IllegalAccessException
same-package peer-package=peer-package
other-package public=other-public
other-package peer-package=IllegalAccessException
dropped-private secret=IllegalAccessException
existing-handle=nested-secret
privateLookupIn-peer class=Peer PRI=true PAC=true MOD=true PUB=true ORI=false
privateLookupIn peer-private=peer-secret
privateLookupIn after drop-private=IllegalAccessException
privateLookupIn after drop-module=IllegalAccessException
in-primitive=IllegalArgumentException
publicLookup UNCOND=true PUB=false
publicLookup nested=nested-public
publicLookup peer-package=IllegalAccessException
```

**Mechanism-based explanation of the results:**

1. `root` is created with `MethodHandles.lookup()` directly inside `LookupDemo`. It has full `PRI`/`PAC`/`MOD`/`PUB`/`ORI`, in addition to the `PROTECTED` bit not printed in the table.
2. `sameNest` switches to `NestedTarget`, which is a nestmate of `LookupDemo`. It retains `PRIVATE` and successfully accesses `NestedTarget.hidden()`; because the lookup class changed, `ORIGINAL=false`.
3. `samePackage` switches to `Peer`: not in the same nest so `PRI=false`, but in the same runtime package so `PAC=true`. `Peer.hidden()` gets `IllegalAccessException`; `Peer.packageValue()` is invoked.
4. `otherPackage` is in the same unnamed module but a different package, so `PAC=false` and `MOD=true`. It can find the public `PublicPeer.shown()`, but cannot find the package-private method.
5. `in-inaccessible` is a lookup directed at the package-private `HiddenClass` in another package. The target is not accessible from that lookup context, so all modes become `false`. `in` does not throw `IllegalAccessException` here; it returns a restricted lookup.
6. `drop-private`, `drop-package`, `drop-module`, and `drop-public` show the bit cascade when downgrading privileges. After dropping `PRIVATE`, the lookup cannot find `NestedTarget.hidden()` even though the original root could.
7. `existing-handle=nested-secret`: `acquiredBeforeDrop` was created using root **before** the downgrade step. Creating a new downgraded lookup does not revoke the old handle.
8. `privateLookupIn-peer` obtains `PRI=true` on `Peer` because root has `PRIVATE` and `MODULE`, and the target is in the same module. Conversely, using `noPrivate` or `noModule` to call `privateLookupIn` fails.
9. `in-primitive=IllegalArgumentException`: the API does not accept primitives as a lookup class.
10. `publicLookup UNCOND=true PUB=false` is not a contradiction: `UNCONDITIONAL` grants public access in unconditionally exported public packages according to its own rules.

## 6. Standalone Java 17 Demo: `privateLookupIn` Across Named Module Boundaries

The second demo simulates a framework in module `beta` wanting to access a private method in module `alpha`. `alpha` only exports the public API `alpha.api`, while the private target resides in the unopened package `alpha.internal`.

Create five files:

```text
modules-demo/
└── src/
    ├── alpha/
    │   ├── module-info.java
    │   └── alpha/
    │       ├── api/Gateway.java
    │       └── internal/Hidden.java
    └── beta/
        ├── module-info.java
        └── beta/Client.java
```

### File `src/alpha/module-info.java`

```java
module alpha {
    exports alpha.api;
}
```

### File `src/alpha/alpha/api/Gateway.java`

```java
package alpha.api;

public class Gateway {
    public static String hello() { return "api-public"; }
    public static Class<?> hiddenClass() { return alpha.internal.Hidden.class; }
}
```

### File `src/alpha/alpha/internal/Hidden.java`

```java
package alpha.internal;

public class Hidden {
    private static String secret() { return "deep-secret"; }
}
```

### File `src/beta/module-info.java`

```java
module beta {
    requires alpha;
}
```

### File `src/beta/beta/Client.java`

```java
package beta;

import alpha.api.Gateway;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MethodHandles.Lookup;

import static java.lang.invoke.MethodHandles.Lookup.*;

public class Client {
    private static boolean has(Lookup l, int bit) {
        return (l.lookupModes() & bit) != 0;
    }

    public static void main(String[] args) throws Throwable {
        Lookup base = MethodHandles.lookup();
        MethodType str = MethodType.methodType(String.class);
        MethodHandle publicApi = base.findStatic(Gateway.class, "hello", str);
        System.out.println("public-api=" + (String) publicApi.invokeExact());

        Lookup moved = base.in(Gateway.class);
        System.out.println("in-exported PUB=" + has(moved, PUBLIC)
                + " MOD=" + has(moved, MODULE)
                + " previous=" + moved.previousLookupClass().getSimpleName());

        Lookup blind = base.in(Gateway.hiddenClass());
        System.out.println("in-unexported modes=" + blind.lookupModes());

        try {
            MethodHandles.privateLookupIn(Gateway.class, base);
            System.out.println("privateLookupIn-exported=success");
        } catch (IllegalAccessException expected) {
            System.out.println("privateLookupIn-exported=IllegalAccessException");
        }

        try {
            Lookup deep = MethodHandles.privateLookupIn(Gateway.hiddenClass(), base);
            System.out.println("privateLookupIn-hidden PRI=" + has(deep, PRIVATE)
                    + " MOD=" + has(deep, MODULE)
                    + " previous=" + deep.previousLookupClass().getSimpleName());
            MethodHandle secret = deep.findStatic(Gateway.hiddenClass(), "secret", str);
            System.out.println("secret=" + (String) secret.invokeExact());
        } catch (IllegalAccessException expected) {
            System.out.println("privateLookupIn-hidden=IllegalAccessException");
        }

        try {
            MethodHandles.privateLookupIn(Gateway.hiddenClass(), moved);
            System.out.println("reteleport=success");
        } catch (IllegalAccessException expected) {
            System.out.println("reteleport=IllegalAccessException");
        }
    }
}
```

**Compile** from the `modules-demo/` directory with Java 17:

```bash
javac --release 17 --module-source-path src -d out src/alpha/module-info.java src/alpha/alpha/api/Gateway.java src/alpha/alpha/internal/Hidden.java src/beta/module-info.java src/beta/beta/Client.java
```

**First run**, without opening the package:

```bash
java --module-path out -m beta/beta.Client
```

Result:

```text
public-api=api-public
in-exported PUB=true MOD=false previous=Client
in-unexported modes=0
privateLookupIn-exported=IllegalAccessException
privateLookupIn-hidden=IllegalAccessException
reteleport=IllegalAccessException
```

**Second run**, opening only the internal package `alpha.internal` to `beta`:

```bash
java --module-path out --add-opens alpha/alpha.internal=beta -m beta/beta.Client
```

Result:

```text
public-api=api-public
in-exported PUB=true MOD=false previous=Client
in-unexported modes=1
privateLookupIn-exported=IllegalAccessException
privateLookupIn-hidden PRI=true MOD=false previous=Client
secret=deep-secret
reteleport=IllegalAccessException
```

**Key observations:**

1. `beta` declares `requires alpha` and `alpha` has `exports alpha.api`, so it can obtain a MethodHandle for `Gateway.hello()` using a normal lookup.
2. `base.in(Gateway.class)` switches the lookup class to module `alpha`. The result only retains public access and loses `MODULE`; `previousLookupClass` is `Client` in module `beta`.
3. When `alpha.internal` is not open, `base.in(Hidden.class)` returns a lookup with mode 0. After `--add-opens`, the same `in` operation on **public `Hidden`** can retain `PUBLIC` (numeric mode 1), but **does not have `PRIVATE`**. Thus `in` still cannot replace `privateLookupIn`.
4. `privateLookupIn(Gateway.class, base)` **still fails** after opening `alpha.internal`, because package `alpha.api` is a different package that is only `exports` and not `opens`. Having a `public class` and `exports` does not equate to granting deep private access.
5. `privateLookupIn(Hidden.class, base)` fails when the package is closed, but succeeds after opening `alpha.internal` specifically. The new lookup has `PRI=true`, `MOD=false`, and `previousLookupClass=Client`; the handle for the private method `Hidden.secret()` returns `deep-secret`.
6. `privateLookupIn(Hidden.class, moved)` always fails in the demo: `moved` has lost `MODULE` due to `Lookup.in` switching from `beta` to `alpha`. Even when the package is open, a downgraded lookup does not regain full privilege on its own.

**Application design:** If a framework module needs controlled private access, the target module can declare `opens alpha.internal to beta;` in `module-info.java` when appropriate for the project structure, instead of adding a JVM flag. When doing so, compile the full module graph and only open the exact packages needed. Do not automatically open the entire module or use private lookup when the public API already meets the need.

## 7. Quick Comparison Table of the Three APIs

| Scenario | `Lookup.in` | `dropLookupMode` | `privateLookupIn` |
| --- | --- | --- | --- |
| Switches lookup class to target | **Yes** | No | **Yes** |
| Keeps lookup class unchanged | When target is the current class itself | **Yes** | When target is the current class itself |
| Can lose `PRIVATE`/`PACKAGE`/`MODULE` | **Yes**, across boundaries | **Yes**, by bit and cascade | Can lose `MODULE` when crossing to another module |
| Can grant `PRIVATE` on another target class | Does not elevate privileges | No | **Yes**, after checking input privileges and module rules |
| Requires original `PRIVATE + MODULE` lookup | No | No | **Yes** |
| Requires `opens` for deep lookup across named modules | Does not request deep access | No | **Yes**, if target module is different |
| Can produce non-`null` `previousLookupClass` | Yes, when crossing modules | Preserves previous context | Yes, when crossing modules |
| Common failure mode | Returns lookup with few or no modes; primitive target throws `IllegalArgumentException` | Downgrades privileges by cascade; invalid mode throws `IllegalArgumentException` | `IllegalAccessException` if privileges/reads/opens are insufficient |

**Distinction from `MethodHandles.publicLookup()`:** this is a factory creating a minimal public-privilege lookup (`UNCONDITIONAL`) following the rules for unconditionally exported packages. It is useful for public APIs, but **cannot be elevated to private** using `in` or `privateLookupIn` because it itself lacks `PRIVATE` and `MODULE`.

## 8. Safe Design and Debugging

### 8.1 Applying the principle of least privilege capability

A full lookup allows creating handles to private members and other access according to the caller context. When integrating plugins or template engines:

- Determine the **target** and **member** needed for integration in advance, and grant a specific `MethodHandle` if that is the only contract that needs to be shared.
- If a lookup must be granted to a recipient, actively use `dropLookupMode` to restrict privileges; make sure to also check **what members the lookup class can find**.
- Avoid leaking full `MethodHandles.lookup()` through public APIs, shared registries, or untrusted plugin hooks. A Lookup is a **capability**, not just metadata.
- Do not assume `dropLookupMode` revokes already-issued method handles; if usage rights need to change at runtime, design an additional API layer controlling invocation/application authorization.
- Do not automatically add broad `--add-opens` or widespread `opens p;`. Only open packages intentionally to modules that genuinely need deep reflection.
- If a public API is sufficient, use the normal exported API; deep private lookup should be an exception with a clear justification.

### 8.2 When `findStatic` / `findVirtual` or `privateLookupIn` fails

Investigate in order:

1. **What is the current lookup class?** Print `lookup.lookupClass()`. Code placed in a helper method may have a different caller from the application code calling that helper.
2. **What modes remain?** Print `lookup.lookupModes()` as a mask/bit flags. Check `PRIVATE`, `PACKAGE`, `MODULE`, and `UNCONDITIONAL` according to context.
3. **Is there a previous lookup class?** Print `lookup.previousLookupClass()`. If it has moved across modules, public access must also satisfy the conditions of multiple modules.
4. **Is the target class accessible from the lookup?** `lookup.in(Target.class)` can return mode 0 when the target is inaccessible. Check public visibility, loader, package/module, `requires`/readability, `exports`, and `opens`.
5. **Did the lookup lose privileges earlier?** `dropLookupMode(PRIVATE)` or `in(otherPackage.class)` cannot be reversed by calling `in` again.
6. **If using `privateLookupIn`**, the caller must have both `PRIVATE` and `MODULE`; across modules, reads + opens of the exact target package are required.
7. **Is the member/signature correct?** For `findStatic` and `findVirtual`, `MethodType` must accurately describe the return type and parameter types; a wrong signature can cause `NoSuchMethodException` instead of an access error.
8. **Is the invoke type correct?** `invokeExact` requires the call-site type to match the method handle exactly; otherwise it will cause `WrongMethodTypeException`. This is **different** from `IllegalAccessException` at handle creation time.

The following observation helper is a **snippet**, added where a `Lookup lookup` variable is present (not a standalone program):

```java
System.out.println("lookup class: " + lookup.lookupClass().getName());
System.out.println("previous class: " + lookup.previousLookupClass());
System.out.println("modes mask: " + lookup.lookupModes());
System.out.println("has PRIVATE: " +
        ((lookup.lookupModes() & MethodHandles.Lookup.PRIVATE) != 0));
System.out.println("has MODULE: " +
        ((lookup.lookupModes() & MethodHandles.Lookup.MODULE) != 0));
System.out.println("has full privilege: " + lookup.hasFullPrivilegeAccess());
```

The snippet requires `import java.lang.invoke.MethodHandles;` and a validly created `Lookup`. When logging in real environments, note that `lookupClass()`/`previousLookupClass()` may expose implementation names; avoid printing detailed information on public channels.

### 8.3 Identifying the right exception type

| Exception | Example |
| --- | --- |
| `IllegalAccessException` | `findStatic` blocked by access checks; or `privateLookupIn` lacks `PRIVATE/MODULE` or the module is not `opens` |
| `NoSuchMethodException` | `findStatic` looks up the wrong name or wrong `MethodType`, looks up an instance method as static or vice versa |
| `IllegalArgumentException` | `lookup.in(int.class)`; `dropLookupMode` receives an unsupported mode; `privateLookupIn` receives a primitive/array |
| `NullPointerException` | Passing `null` to `Lookup.in` or to target/caller of `privateLookupIn` |
| `WrongMethodTypeException` | Calling `MethodHandle.invokeExact` with an incorrect signature |
| Exception thrown by target | When a valid handle is executed, exceptions are usually thrown directly from the target; there is **no** automatic `InvocationTargetException` wrapper like `Method.invoke` |

Without distinguishing **lookup/access** from **invoke/type** and **exceptions inside the target**, it is very easy to mistakenly "fix" it by saying "use privateLookupIn" when the real issue is a wrong `MethodType`.

## 9. Self-Check Exercises

**Question 1.** A full `Lookup` is created in class `A`. `A` and `A.Nested` are nestmates. `A` calls `lookup.in(A.Nested.class)`. Can the new lookup retain the `PRIVATE` privilege?

**Answer:** Yes. Being in the same nest allows retaining private access, although `ORIGINAL` no longer remains when the lookup class changes.

**Question 2.** Class `A` and class `B` are in the same runtime package, but in different nests. Does `lookupFromA.in(B.class)` automatically create private access to `B`?

**Answer:** No. `PRIVATE` is dropped when switching to a different nest; `PACKAGE` may remain. With a full lookup in the same module, `privateLookupIn(B.class, lookupFromA)` is the appropriate way to request a private lookup after access checks.

**Question 3.** After `dropLookupMode(PACKAGE)`, can `PRIVATE` be retained in Java 17?

**Answer:** No. Dropping `PACKAGE` also removes `PRIVATE`, `PROTECTED`, and `ORIGINAL`. Starting from a full lookup, `MODULE` and `PUBLIC` remain.

**Question 4.** After `dropLookupMode(MODULE)`, can the resulting lookup be used to call `privateLookupIn` to another class in the same module?

**Answer:** No. It no longer has `MODULE` (and also lost `PRIVATE`).

**Question 5.** Module `beta` reads module `alpha`, and `alpha` exports package `api` without opening it. Does `privateLookupIn(Api.class, lookupFromBeta)` always succeed when `Api` is `public`?

**Answer:** No. For deep lookup between two named modules, the package containing the target must be opened to the caller module. `exports` alone does not satisfy the `opens` condition.

**Question 6.** With `--add-opens alpha/alpha.internal=beta`, a private lookup from `beta` into a target class in `alpha.internal` succeeds. Can the resulting lookup continue requesting a private lookup into a third module?

**Answer:** No. A lookup that has teleported across modules loses `MODULE`; `privateLookupIn` requires the caller to have both `PRIVATE` and `MODULE`.

**Question 7.** A lookup has already created a handle for a private method, and then `dropLookupMode(PRIVATE)` is called on the lookup to create a downgraded version. Is the old method handle revoked?

**Answer:** No. Permissions were checked when the handle was created, and downgrading a new lookup does not revoke the old capability.

**Question 8.** Why does `MethodHandles.publicLookup().lookupModes()` not necessarily contain the `PUBLIC` bit, yet it can still find public members?

**Answer:** `publicLookup()` operates under the separate `UNCONDITIONAL` mode, reaching only public members of public types in unconditionally exported packages. The `UNCONDITIONAL` state is not an arbitrary combination with the `PUBLIC` bit.

**Question 9.** Does a `WrongMethodTypeException` error when you already have a valid handle indicate an issue with `opens`/`PRIVATE`?

**Answer:** No. Usually the `invokeExact` call-site has a signature that does not match the handle's `MethodType`; access checks already occurred when creating the handle.

**Question 10.** Should you call `MethodHandles.lookup()` inside a helper and assume it represents the code calling the helper?

**Answer:** No. `lookup()` is caller-sensitive, taking the exact class that directly calls it as the lookup class. If you want to pass capability from a valid caller to a helper, you must pass the appropriate lookup and control the delegated privileges.

## 10. Key Takeaways

- `Lookup` carries the **lookup class**, **lookup modes**, and sometimes the **previous lookup class**; it is a capability that must be managed carefully.
- `Lookup.in` **switches the class but does not elevate privileges**. Same nest can keep private, same package different nest loses private, different package loses package, cross-module loses module.
- `dropLookupMode` **downgrades privileges one-way** and has a **cascade**; bits cannot be restored with `in`.
- `privateLookupIn` requires a caller with **`PRIVATE + MODULE`**. Crossing to another named module also requires appropriate **reads + opens**.
- A lookup obtained via cross-module `privateLookupIn` still has private access at the target, but **does not have MODULE** to forward deep lookups further.
- A validly created `MethodHandle` **does not lose privileges** because another lookup is dropped; control both handles and lookups when delegating.
- `exports` supports public APIs; `opens` allows deep reflection within the granted scope.
- Check privileges when **creating the handle**, check exact types when calling **`invokeExact`**, and clearly distinguish exceptions from the two phases.

### Official References (Java SE 17)

- [`MethodHandles.Lookup` — Access checking, Cross-module lookups, Access modes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [`MethodHandles.Lookup.in(Class)`, `dropLookupMode(int)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#in(java.lang.Class))
- [`MethodHandles.privateLookupIn(Class, Lookup)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html#privateLookupIn(java.lang.Class,java.lang.invoke.MethodHandles.Lookup))
- [`MethodHandle.invokeExact`, `WrongMethodTypeException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [JLS 17 — Module declarations (`exports`, `opens`)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.7)