# 15.5. `NESTMATE`, `STRONG`, and the lifecycle relationship of a hidden class with the class loader

## 1. The problem: one hidden class, two independent decisions

Java 15 introduced `MethodHandles.Lookup.defineHiddenClass(...)` to create a **hidden class** directly from bytecode, without registering a binary name that can be looked up via `Class.forName`. Two `MethodHandles.Lookup.ClassOption` options are very easy to confuse:

- **`NESTMATE`**: lets the hidden class **join the nest of the lookup class**, thereby allowing it to access `private` members of other classes in the **same nest**, according to nest-based access control rules.
- **`STRONG`**: gives the hidden class a **strong relationship with the class loader marked as the defining loader**, just like a normal class. A hidden class with `STRONG` *can* only be unloaded if the defining loader is no longer reachable and can be reclaimed by GC.
- **Without `STRONG`**: by default, a hidden class **can be unloaded even while the defining loader is still reachable**, if it is no longer kept alive by related objects/capabilities and the JVM decides to reclaim it.
- **The two options are independent**. `NESTMATE` **does not imply** `STRONG`; `STRONG` **does not grant** `private` access.

Within the scope of this lesson, calling it a “weak hidden class” is a way of referring to the default **ability for class unloading independently of the loader**. That does **not** mean `Class.getClassLoader()` returns `null`, does not mean the class is created by `WeakReference`, and does not guarantee that unloading results can be measured with a single `System.gc()` call.

Learning objectives:

1. Distinguish nest rights from the unloading policy of a hidden class.
2. Understand how `defineHiddenClass` associates the new class with the **same runtime package, module, protection domain, and defining loader** of the lookup class.
3. Read `Class.isHidden()`, `getNestHost()`, `isNestmateOf()`, `getClassLoader()`, and understand the limitation of `getNestMembers()`.
4. Run a Java 17+ example with all **four combinations** of options, observing private calls succeeding/failing.
5. Design lifecycles for code generation, frameworks, lambda-like runtime code, and avoid retaining unnecessary classes in long-lived loaders.

## 2. `defineHiddenClass`: unlike `ClassLoader.defineClass`

Typical API:

```java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);

Class<?> hiddenType = hiddenLookup.lookupClass();
```

**This snippet is illustrative code**, using a provided `byte[] bytes`; requires importing `java.lang.invoke.MethodHandles`.

Important parameters:

| Input | Role |
| --- | --- |
| `bytes` | Valid class file bytes; `this_class` points to a class in the same package as the lookup class |
| `initialize` | `true`: the JVM initializes the hidden class after deriving/linking; `false`: allows deferring initialization until an appropriate first use |
| `options` | `ClassOption` values such as `NESTMATE`, `STRONG`; no options may be passed |
| `hiddenLookup` | Returned `Lookup` whose `lookupClass()` is the new hidden class |
| `hiddenType` | `Class<?>` representing the hidden class, usable with reflection and many APIs accepting `Class<?>` |

The `Lookup` used to create a hidden class requires **full privilege access** under the Java SE 17 contract. Not just any `publicLookup()` or reduced-privilege lookup can create a hidden class.

`defineHiddenClass` does not call `ClassLoader.defineClass` to register a normal binary name. Instead, the JVM **marks the lookup class's loader as the defining loader** of the hidden class and creates a class with its own runtime name. The new class uses:

- **The same defining class loader** as the lookup class.
- **The same module** and **the same runtime package** as the lookup class.
- **The same protection domain** as the lookup class.
- A **distinct class identity**, different from every other definition, even when the source bytes are identical.

Sharing the same loader/package does not mean gaining default access to all `private` members of the lookup class: private access is governed by the **nest relationship**.

Do not confuse `Lookup.defineClass(bytes)` (which creates a **named class**) with `Lookup.defineHiddenClass(bytes, ...)`. A named class is normally looked up by binary name according to loader rules; a hidden class is designed not to have a binary name that can be linked from other classes.

## 3. Comparison table of the four configurations

Same full-privilege lookup, same bytecode, and same loader:

| Configuration | Nest host of the hidden class | Granted nest-based private access to host? | Policy: can be unloaded while loader is still reachable |
| --- | --- | --- | --- |
| No option | The hidden class itself (its own nest) | **No**, not merely by sharing loader/package | **Possible**, if no live references remain |
| `NESTMATE` | Nest host of the lookup class | **Yes**, with members of the same nest | **Possible**, because `STRONG` is not enabled |
| `STRONG` | The hidden class itself (its own nest) | **No**, not merely because of `STRONG` | **No**, while the defining loader is still reachable |
| `NESTMATE, STRONG` | Nest host of the lookup class | **Yes** | **No**, while the defining loader is still reachable |

The unload column describes **the sufficient condition for the class to be eligible for reclamation**, not a promise that the JVM will unload it immediately. The class can still be kept alive by object instances, method handles, lookup references, class literals/references, callback registrations, or currently executing code.

**`NESTMATE` is the access-control axis. `STRONG` is the lifecycle axis.** Combining the two options simply applies both policies simultaneously; the order of options in varargs creates no new feature.

## 4. What are a nest and a nestmate?

Since Java 11, classes/interfaces can belong to the same **nest**. One class acts as the **nest host**, and the other classes are recognized by the JVM as **nestmates** of each other and can access each other's `private` members under nest-based access control.

With Java source:

```java
public final class Owner {
    private static String secret() {
        return "secret";
    }

    static class Helper {
        static String read() {
            return secret();
        }
    }
}
```

This is an **illustrative code fragment**, not the main example. Regular `javac` generates `NestHost`/`NestMembers` metadata in class files so that `Helper` and `Owner` are nestmates. Accessing `private static Owner.secret()` from `Helper` is valid when both are genuinely in the same nest.

When using `defineHiddenClass`, the JVM does not simply preserve the `NestHost` recorded in the class-file bytes:

- **By default**: the hidden class has **its own nest**, with itself as the nest host.
- **With `NESTMATE`**: the JVM sets the hidden class's nest host to the **nest host of the lookup class** used to define it.
- The nest is decided at hidden class creation time, not based on the original `NestHost` attribute of the bytes.
- Joining the nest **does not rewrite the `NestMembers` attribute** of the host class file, and the host class may have been loaded long ago.

Therefore, the same class file compiled by the compiler as a nested class, when **re-defined as hidden** without `NESTMATE`, **does not automatically inherit** private access to the outer host.

### Important queries

```java
Class<?> host = hiddenType.getNestHost();
boolean canAccessAsNestmate = hiddenType.isNestmateOf(Owner.class);
```

This is **illustrative code** using an existing `hiddenType` and `Owner`. `getNestHost()` returns the actual nest host at runtime. `isNestmateOf` compares nest hosts, which is the appropriate query to check a nest relationship.

`Class.getNestMembers()` has a subtle limitation: **the returned array only includes the nest members recorded in the host's `NestMembers` attribute**, without adding hidden classes newly attached to the nest via `Lookup.defineHiddenClass`. Therefore:

```text
hiddenClass.isNestmateOf(hostClass) == true
```

**does not contradict** not seeing `hiddenClass` in `hostClass.getNestMembers()`.

## 5. `NESTMATE` grants private access, but not unlimited access

When a hidden class is a nestmate of the lookup class, it can access `private` methods, fields, and constructors of classes that genuinely belong to the same nest; the JVM still verifies bytecode, class accessibility, and other conditions.

Do not overgeneralize:

- `NESTMATE` does **not** grant access to all private members of **every class in the same package**.
- `NESTMATE` does **not** create readability to any module, open another package, or automatically modify JPMS `exports/opens`.
- `NESTMATE` does **not** turn the hidden class into a subclass of the host; nest and inheritance are **two different relationships**.
- `NESTMATE` does **not** mean the hidden class can be looked up by name with `Class.forName`.
- `NESTMATE` does **not** force the hidden class to stay alive until the loader is reclaimed; that is `STRONG`'s job.

Conversely, a hidden class that is **not a nestmate** still has access to public/package-private members that Java access control actually permits. When a private method of the host is called illegally from the hidden class's bytecode, the JVM may throw **`IllegalAccessError` at call linking/resolution time**. This is **different** from `IllegalAccessException` when a `Lookup.find*` factory cannot create a method handle.

The example in section 8 illustrates this difference using the same `Payload.class` defined as four different classes.

## 6. `STRONG` is a lifecycle relationship with the loader, not a “keep forever” keyword

Under Java SE 17, a normal class has a strong relationship with its **defining class loader**: the class can be unloaded **if and only if** that loader is no longer reachable so GC can reclaim it. `ClassOption.STRONG` requires the hidden class to follow this relationship.

That does not mean:

- `STRONG` makes the class **immortal** until JVM shutdown in every application. The loader can become unreachable, and the class can be unloaded along with the loader.
- `STRONG` itself pins the class loader permanently. Actual reference paths and resources must be considered.
- `STRONG` grants private access or helps nestmate checks.
- `STRONG` is required for all hidden classes.
- `Class.getClassLoader()` returns a different kind of loader between strong and default hidden classes. In the example, all four variants use **the same defining loader**.

**If the defining loader is always reachable** (for example, the app class loader of a running server process), a hidden class using `STRONG` has the same unloading policy as a normal class in that loader. Continuously generating many strong hidden classes can increase metaspace consumption, because they cannot be unloaded independently while the loader is alive.

**If `STRONG` is not selected**, by default a hidden class can be unloaded independently of the loader when it is no longer kept alive; this is an advantage for runtimes that generate many short-lived classes, such as implementations for lambda-like constructs, DSLs, adapters, or generated functions.

### What if `NESTMATE` is set without `STRONG`?

Adding a hidden class to a nest does not force the JVM to keep it alive forever with the nest host. `NESTMATE` determines access control checks. The hidden class still has the **default lifecycle** if `STRONG` is not enabled, so it can be unloaded while the host and loader remain reachable when no other references keep it alive.

### What if `STRONG` is set without `NESTMATE`?

The hidden class has its lifecycle tied to the defining loader, but its nest host remains **the hidden class itself**. It does not gain access to private members of the lookup class merely because it shares the same loader, the same package, or lives longer.

## 7. Which class loader actually “owns” the hidden class?

`Lookup.defineHiddenClass` does not take a `ClassLoader` argument like `Proxy.newProxyInstance`. It uses **the defining class loader of the current lookup class**.

Illustrative example:

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
ClassLoader expected = lookup.lookupClass().getClassLoader();

MethodHandles.Lookup hidden = lookup.defineHiddenClass(
        bytes, false, MethodHandles.Lookup.ClassOption.STRONG);

boolean sameLoader =
        hidden.lookupClass().getClassLoader() == expected;
```

This illustrative code requires valid `bytes` and a full-privilege `Lookup`; it does not run standalone. The result `sameLoader` is `true` per the `defineHiddenClass` contract.

**Be careful with the term “class loader”:**

- **Defining loader**: the loader attached by the JVM to the class.
- **Initiating loader**: a loader that may be recorded when `loadClass` initiates normal class loading.
- For a hidden class, the JVM attaches the lookup class's defining loader but **does not record an initiating loader** the way a normal class discovered by binary name does.

`Thread.currentThread().getContextClassLoader()` **does not automatically determine** the defining loader for a hidden class if you do not use that context to choose the lookup class. Therefore, to make a hidden class live with a plugin that has its own loader, you must **obtain a validly privileged Lookup in the plugin's module/package**, not merely change the thread context class loader.

When a plugin loader is held by a static registry in the app class loader, “disabling” the plugin in the UI is not enough to prove the loader is unreachable. Caches and cross-loader references must be examined; `STRONG` further increases retention of hidden classes sharing that loader.

## 8. Complete Java 17+ program: four options and private access

Save the entire following file with the exact name **`HiddenClassOptionsDemo.java`**. The program needs no ASM or external dependencies; it uses **a nested class compiled by `javac` into `.class`** as template bytes to redefine as hidden classes.

```java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;

import static java.lang.invoke.MethodHandles.Lookup.ClassOption.NESTMATE;
import static java.lang.invoke.MethodHandles.Lookup.ClassOption.STRONG;

public final class HiddenClassOptionsDemo {
    private static String secret() {
        return "private-ok";
    }

    public static class Payload {
        public static String callHostSecret() {
            return HiddenClassOptionsDemo.secret();
        }
    }

    private static String invoke(MethodHandles.Lookup lk) throws Throwable {
        MethodHandle mh = lk.findStatic(
                lk.lookupClass(), "callHostSecret",
                MethodType.methodType(String.class));
        return (String) mh.invokeExact();
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream stream =
                     HiddenClassOptionsDemo.class.getResourceAsStream(
                             "HiddenClassOptionsDemo$Payload.class")) {
            if (stream == null) {
                throw new IllegalStateException("Payload class resource missing");
            }
            bytes = stream.readAllBytes();
        }

        MethodHandles.Lookup host = MethodHandles.lookup();

        MethodHandles.Lookup plain =
                host.defineHiddenClass(bytes, true);
        MethodHandles.Lookup nest =
                host.defineHiddenClass(bytes, true, NESTMATE);
        MethodHandles.Lookup strong =
                host.defineHiddenClass(bytes, true, STRONG);
        MethodHandles.Lookup both =
                host.defineHiddenClass(bytes, true, NESTMATE, STRONG);

        Class<?> p = plain.lookupClass();
        Class<?> n = nest.lookupClass();
        Class<?> s = strong.lookupClass();
        Class<?> b = both.lookupClass();

        System.out.println("hidden=" + p.isHidden());
        System.out.println("sameLoader=" +
                (p.getClassLoader() ==
                        HiddenClassOptionsDemo.class.getClassLoader()));
        System.out.println("sameModule=" +
                (p.getModule() == HiddenClassOptionsDemo.class.getModule()));
        System.out.println("samePackage=" +
                p.getPackageName().equals(
                        HiddenClassOptionsDemo.class.getPackageName()));
        System.out.println("defaultNestSelf=" + (p.getNestHost() == p));
        System.out.println("strongNestSelf=" + (s.getNestHost() == s));
        System.out.println("nestHostIsOwner=" +
                (n.getNestHost() == HiddenClassOptionsDemo.class));
        System.out.println("bothNestHostIsOwner=" +
                (b.getNestHost() == HiddenClassOptionsDemo.class));
        System.out.println("ownerIsNestmate=" +
                HiddenClassOptionsDemo.class.isNestmateOf(n));
        System.out.println("strongOnlyNotNestmate=" +
                !HiddenClassOptionsDemo.class.isNestmateOf(s));

        try {
            System.out.println("plainPrivate=" + invoke(plain));
        } catch (IllegalAccessError expected) {
            System.out.println("plainPrivate=denied");
        }

        System.out.println("nestPrivate=" + invoke(nest));

        try {
            System.out.println("strongPrivate=" + invoke(strong));
        } catch (IllegalAccessError expected) {
            System.out.println("strongPrivate=denied");
        }

        System.out.println("bothPrivate=" + invoke(both));
        System.out.println("distinctClasses=" +
                (p != n && n != s && s != b));

        try {
            Class.forName(n.getName(), false, n.getClassLoader());
            System.out.println("byName=unexpected");
        } catch (ClassNotFoundException expected) {
            System.out.println("byName=unavailable");
        }

        System.out.println("enumeratedNest=" +
                Arrays.asList(HiddenClassOptionsDemo.class.getNestMembers())
                        .contains(n));
    }
}
```

### 8.1. Compile and run

In the directory containing the file, using JDK 17 or later:

```bash
javac --release 17 HiddenClassOptionsDemo.java
java HiddenClassOptionsDemo
```

`javac` produces at least:

```text
HiddenClassOptionsDemo.class
HiddenClassOptionsDemo$Payload.class
```

The code reads the bytes of the second file via `getResourceAsStream` and passes **the same bytes** into four `defineHiddenClass` calls. All four calls create **distinct class identities**, without modifying `Payload.class` on disk.

### 8.2. Verified exact stdout

```text
hidden=true
sameLoader=true
sameModule=true
samePackage=true
defaultNestSelf=true
strongNestSelf=true
nestHostIsOwner=true
bothNestHostIsOwner=true
ownerIsNestmate=true
strongOnlyNotNestmate=true
plainPrivate=denied
nestPrivate=private-ok
strongPrivate=denied
bothPrivate=private-ok
distinctClasses=true
byName=unavailable
enumeratedNest=false
```

This is the verified output when compiled with `javac --release 17` and run on a JDK supporting Java 17. The program intentionally **does not print the full hidden class name**, because the suffix generated by the JVM is not fixed across runs.

## 9. Analyzing the output: how does `NESTMATE` differ from `STRONG`?

### 9.1. Four distinct classes, same loader/module/package

```text
hidden=true
sameLoader=true
sameModule=true
samePackage=true
```

`isHidden()` verifies that `plain` is a hidden class. The subsequent comparisons prove that the JVM attaches it to the lookup class's loading environment as specified by the API. If the host class is in a named module, the hidden class is in that same module; the example runs on the classpath so both are in the unnamed module.

`distinctClasses=true` means **each `defineHiddenClass` call creates a new identity**. Having the same bytes or the same `this_class` name in the original file does not make the four definitions return a single class.

### 9.2. Nest rights are directly observable

```text
defaultNestSelf=true
strongNestSelf=true
nestHostIsOwner=true
bothNestHostIsOwner=true
ownerIsNestmate=true
strongOnlyNotNestmate=true
```

Even though `Payload` is a nested class in the Java source (and the compiler may record `NestHost` in the bytecode), a hidden class created **without `NESTMATE`** becomes its own nest. That happens for both `plain` and `strong`.

Conversely, `nest` and `both` are added to `HiddenClassOptionsDemo`'s nest thanks to the `NESTMATE` option. `getNestHost()` accurately reflects the runtime nest host, without relying on whether the original bytes look like a nested class.

### 9.3. `IllegalAccessError` proves private access is denied

```text
plainPrivate=denied
nestPrivate=private-ok
strongPrivate=denied
bothPrivate=private-ok
```

The `Payload.callHostSecret()` method contains code calling:

```java
HiddenClassOptionsDemo.secret();
```

That is a private static method of the host. For that exact same call:

- **Without `NESTMATE`**: the hidden class is not in the same nest, so the JVM rejects the private call. The program catches `IllegalAccessError` as expected.
- **With `NESTMATE`**: the hidden class is treated as a nestmate, so the private call succeeds and returns `private-ok`.
- **`STRONG` only**: does not change nest rights; still denied.
- **With both**: same private access as `NESTMATE`, while also having `STRONG`'s lifecycle policy.

This is the most important experiment in the lesson: **`STRONG` is not an access-granting mechanism**.

The `invoke(lk)` helper on the host side uses `lk.findStatic(...)` to obtain a handle to **the hidden class's public method `callHostSecret`**. That handle creation succeeds because the lookup returned from `defineHiddenClass` is bound to the hidden class itself. Later, when `invokeExact()` runs the method and the bytecode attempts to call private `secret()` on the host, the JVM detects the nest access failure.

Therefore **the observed error is `IllegalAccessError` inside the hidden class's bytecode**, not `IllegalAccessException` rejected by `findStatic` itself. The two error types occur at two different steps; this distinction matters when debugging.

### 9.4. A hidden name is not a lookup-capable binary name

```text
byName=unavailable
```

A hidden class has a runtime name whose `Class.getName()` typically looks like:

```text
HiddenClassOptionsDemo$Payload/0x0000... 
```

This is only an **illustrative shape**, not a fixed name to copy. The part after `/` is generated by the JVM, can differ between two runs, and that name does not have the properties of a valid binary name for normal class loading.

`Class.forName(hiddenClass.getName(), false, loader)` cannot find the hidden class under the API contract. However, you **can still** hold onto the `Class<?>` obtained from `lookup.lookupClass()`, use reflection on that class, create `MethodHandle`s, or create instances when the bytecode/class is suitable.

**“Hidden” does not mean the class is inaccessible to everyone**, only that it is not linked and discovered by a normal nominal binary name.

### 9.5. Why doesn't `getNestMembers()` list the hidden nestmate?

```text
enumeratedNest=false
```

`HiddenClassOptionsDemo.class.getNestMembers()` reflects the classes recorded in the host's `NestMembers` attribute. A hidden class that joins a nest **dynamically** is not added to the attribute already present in the class file. Hence the `false` output does not falsify `ownerIsNestmate=true`.

Under Java SE 17, **`getNestMembers()` does not include hidden classes added via `defineHiddenClass`**, so to check a specific hidden class, use `hiddenType.getNestHost()` or `hiddenType.isNestmateOf(hostType)`.

## 10. Why does `Payload.class` have `NestHost`, yet the default hidden class is still not in the same nest?

Run the command:

```bash
javap -v -p 'HiddenClassOptionsDemo$Payload'
```

In Bash and PowerShell, single quotes around the class name prevent the shell from expanding the `$` character. `javap` in the experiment confirms:

```text
major version: 61
NestHost: class HiddenClassOptionsDemo
```

This snippet **summarizes the relevant information**, not the entire `javap` output. The template file was compiled by `javac` from a nested class and has `NestHost` recording the host of the **normally named** class.

However, `Lookup.defineHiddenClass(bytes, ..., options)` is a **different** class derivation mechanism. For a hidden class, the JVM **does not use the `NestHost` attribute in the bytes to decide the nest host**. `NESTMATE` is what instructs the JVM to add the new class to the lookup class's nest.

The difference:

```text
Normal named class:
  compiler metadata NestHost -> confirms nest of named Payload

Hidden class redefined from the same bytes:
  without NESTMATE -> the hidden class's own nest
  with NESTMATE    -> the lookup class's nest
```

This is why the experiment is valuable: it can be verified without using an external bytecode emitter. At the same time, it reminds us that **the same class file does not always lead to the same runtime rules** if the way the class is defined differs.

## 11. Reachability, class unloading, and GC relationships

The crux of `STRONG` is not the output of a boolean API like `getNestHost()`, but **the JVM rule determining whether a hidden class can be unloaded while the loader is still reachable**.

### 11.1. Default hidden class — can be unloaded independently

Under the Java SE 17 contract, without `STRONG`, the JVM **can** unload a hidden class even while the defining loader remains reachable. This is especially useful if:

- A framework generates thousands of short-lived handlers/adapters.
- Generated functions are tied to a request, expression tree, or short-lived script snippet.
- A library creates implementation classes for many configurations and discards them when no consumers remain.
- You do not want every hidden class to survive until the application/plugin class loader is reclaimed.

**However, “can be unloaded” is not “guaranteed to be unloaded”.** If there is a strong reference to the hidden class's `Class<?>`, a live instance, a `MethodHandle` bound to one of its methods, or a retained `Lookup`, the JVM may still consider the class reachable. Metadata/call-site caches can also maintain related reference paths.

Using `WeakReference<Class<?>>` to observe a class after GC is an **observation** tool, not something that changes the JVM's default unloading policy. You must not equate a `ref.get() != null` result at one point in time with the conclusion “cannot be unloaded”.

### 11.2. Strong hidden class — same unloading conditions as a normal class

With `STRONG`, the hidden class has a strong relationship with its **defining loader**. If the loader is still reachable, the class is **not eligible** for independent unloading, even if the application has dropped all direct references to the hidden class's `Class<?>` and objects.

If the loader becomes unreachable, a `STRONG` hidden class *can* be unloaded along with the loader, but GC/the JVM decides the actual timing; **immediate unloading is not guaranteed**.

A server application that loads all hidden classes through the app class loader and continuously creates more strong classes can retain a large amount of class metadata until the process exits. This is one reason to choose `STRONG` based on required lifecycle, rather than enabling it by default “to be safer”.

### 11.3. References that often accidentally keep a hidden class alive

Check places that might store the class/capability:

- `Class<?>` placed in a `static final` map/list.
- `MethodHandles.Lookup` whose `lookupClass()` is the hidden class.
- `MethodHandle`/`VarHandle` referencing members of the hidden class.
- Instances of the hidden class or wrappers holding them.
- Callback registrations, global event buses, scheduled tasks, and threads currently executing the hidden class's code.
- Framework caches, static fields of a long-lived class, or object-graph structures crossing class loaders.
- A call site already linked to a target handle of the hidden class while the call site itself is still alive.

These are **possible retention paths**, not a list claiming every JVM builds the exact same internal object graph. You need to measure in the real system using a profiler/heap dump/class unloading events.

In the `STRONG` case, even clearing some of the references above **does not make the class eligible for unloading** if the defining loader is still reachable. In the default case, removing those references **can** clear the way for unloading, though it does not command the JVM to do so immediately.

## 12. Do not measure unloading with a single `System.gc()` and treat it as truth

A common test snippet:

```java
WeakReference<Class<?>> ref = ...;   // after creating the hidden class
System.gc();
System.out.println(ref.get() == null);
```

This is **non-standalone illustrative code**. The result depends on the JVM, GC configuration, actual reachability, timing, JIT, and references still held by the code. `System.gc()` is only a hint, which may be ignored or may not reclaim classes immediately.

**In particular:** code in the middle of a method still holding a local `hiddenLookup`, `hiddenClass`, or handle can keep the hidden class reachable. Even when a developer thinks a variable is “no longer used”, the compiler/JIT may have different liveness/lifetimes than inferred from source.

When you need to study lifecycle:

1. Create the hidden class in a separate scope/factory, avoiding holding `Lookup`/`Class<?>`/instances in long-lived caches.
2. Return a `WeakReference<Class<?>>` along with a `ReferenceQueue<Class<?>>` if tracking is needed.
3. Drop all strong references outside the probe; verify no registry or other target handle retains the class.
4. Observe across multiple GC cycles/memory conditions in a controlled environment.
5. On HotSpot, you can add unified logging, e.g., `-Xlog:class+unload=info`, to view class unloading events (if any).
6. Compare multiple runs, rather than relying on a single measurement.
7. Do not write a unit test requiring “must be GC'd within N milliseconds” as a pass condition.

A **reliable contract test** for `STRONG`/default should verify the option selection and documented rules; it should not use GC nondeterminism as a mandatory assertion.

### Regarding `ReferenceQueue`

`ReferenceQueue` can notify you that a reference has been cleared/enqueued when GC actually reclaims the referent under VM policy. It is not a class-unloading controller. If no event arrives within some period, you cannot conclude that the class became a strong hidden class. With `STRONG`, even Java references to `Class<?>` may be removed from the app object graph while the class is still retained by the VM via its strong relationship with the loader.

## 13. Class loader lifecycle in plugins and hot reload

Suppose an application has:

```text
Application loader (very long-lived)
    |
    +-- Plugin loader #1 -> plugin classes -> hidden classes
    |
    +-- Plugin loader #2 -> plugin classes -> hidden classes
```

It is the **lookup class** that determines the defining loader. If a generator uses a lookup from application-loader code, the hidden class has the application's defining loader, and does **not** automatically switch to the plugin loader just because the plugin called the generator.

When you want hidden classes to belong to a plugin's lifecycle:

- Obtain a validly privileged lookup in a class/module/package of the plugin.
- Verify `hiddenClass.getClassLoader() == pluginClass.getClassLoader()` by design.
- Ensure no registry or callback from the application retains references to the plugin loader/classes/handles after unloading the plugin.
- Use `STRONG` only if the hidden class **needs** the same lifetime coupling with the plugin loader; if you want many generated classes to be reclaimed separately while the plugin runs, omit `STRONG`.
- Distinguish **class unloading** from deleting a JAR file or closing a `URLClassLoader`: `close()` releases some resources, and does **not** guarantee that the loader and classes are unreachable/unloaded.
- Avoid testing by “changing ContextClassLoader and calling `defineHiddenClass`” if the lookup class still belongs to the application loader; the result still binds to the lookup class's defining loader.

If a plugin loader is referenced by an application static map, the plugin still cannot be unloaded even if you make every generated class a weak hidden class. `STRONG` is not the only cause of memory leaks; the entire object graph must be inspected.

## 14. `initialize` is a parameter independent of both `NESTMATE` and `STRONG`

`defineHiddenClass(bytes, boolean initialize, ClassOption... options)` has a separate `initialize` parameter:

- `initialize=true`: the JVM initializes the class after deriving/linking, before the API returns the lookup.
- `initialize=false`: allows deferring initialization, following class initialization rules when a method/field/constructor is used.

It does **not** change:

- Nest host.
- Strong/weak unloading policy.
- Defining loader.
- Ability to look up via `Class.forName`.

Illustrative example in code with a static initializer:

```java
static {
    System.out.println("Hidden class initialized");
}
```

This is only **a declaration snippet in a class template**, not a standalone program. If `initialize=true` is used, the initializer output appears when defining the hidden class. If `false`, calling a static method or accessing an appropriate static field can trigger initialization later.

**Do not use the number of times the initializer prints to infer unloading policy**. An initialized class can still be unloaded if policy and reachability allow; an uninitialized class does not automatically gain private access.

For templates with side effects in `<clinit>`, enabling `initialize=true` requires care because initialization errors can surface immediately in `defineHiddenClass` and leave an erroneous state under JVM rules. The main experiment uses a template without a static initializer to keep output stable.

## 15. Returned `Lookup` and the hidden class's privileges

When `defineHiddenClass` succeeds, the API returns a `MethodHandles.Lookup` whose **lookup class is the new hidden class**, with appropriate privileges per the specification. This object is a **capability**:

```java
MethodHandles.Lookup hidden = hostLookup.defineHiddenClass(bytes, true);
Class<?> c = hidden.lookupClass();
MethodHandle mh = hidden.findStatic(
        c, "run", MethodType.methodType(String.class));
```

This is **illustrative code**; `hostLookup` and `bytes` must already exist, and the hidden class must declare `static String run()`. The granted lookup can look up members of the hidden class itself, including private members within the privilege scope of that lookup.

Design risks:

- If you accidentally share a full-privilege hidden lookup with another plugin, the plugin can look up additional members of the hidden class that the provider did not intend to expose.
- If the hidden class is a `NESTMATE`, sharing an appropriate lookup can also carry **nest access privileges** under Java access checks; this is a sensitive capability.
- A `MethodHandle` to a specific operation is usually a **narrower** capability than a full-privilege Lookup.
- Holding a `Lookup`, `Class<?>`, or `MethodHandle` in a long-lived cache also affects the **reachability** of a default hidden class.

From both a security and resource perspective, you must design **both**: call/access privileges and reference lifecycles. `STRONG` is not a way to grant access, and `NESTMATE` is not a GC policy.

## 16. Hidden class name and how to access it after definition

The Java SE 17 specification states that `Class.getName()` of a hidden class has an appended runtime suffix, for example:

```text
com.example.Generated/0x0000000800123456
```

This is an **example shape**, not a fixed name from executed code. The `/` character and suffix make this name **not a normal binary name** that can be passed to:

```java
Class.forName(hiddenType.getName(), false, hiddenType.getClassLoader());
```

This call will not resolve the hidden class under normal nominal lookup mechanisms. That does **not** mean `hiddenType` is unusable:

- `hiddenType.isHidden()` confirms it is hidden.
- `hiddenType.getNestHost()` and `hiddenType.isNestmateOf(...)` check nest relationships.
- `hiddenType.getClassLoader()` returns the defining loader attached to the class.
- `hiddenType.getDeclaredMethods()` can inspect members.
- `MethodHandles.Lookup`/reflection with appropriate privileges can invoke members.
- An instance has `getClass()` returning the hidden class's `Class<?>`.

Because a hidden class has no binary name, mechanisms that require reconstructing a nominal name, such as default Java serialization, do not always work. Using hidden classes in a framework requires attention to **saving/reconstructing by name**, not just private access.

### `Class.getNestMembers()` is not a registry for hidden nestmates

A framework wanting to “find all classes added to the nest by `NESTMATE`” cannot simply call `getNestMembers()`. This API reflects the `NestMembers` attribute recorded in the class file, not all dynamically added hidden classes. If it needs to manage/clean up generated hidden classes, the framework must manage its own references/metadata, while choosing appropriate **weak tracking** to avoid accidentally preventing unloading.

## 17. Choosing options for real-world scenarios

| Need | What to consider | Why |
| --- | --- | --- |
| Generated helper needs to access host's private members | `NESTMATE` | Joins the same nest to gain private access |
| Generated helper only uses public/package members | No `NESTMATE` needed | Least privilege, limits private access |
| Large batches of short-lived generated classes in a long-lived app loader | **No `STRONG`**, unless explicitly required | Enables independent unloading to reduce metaspace pressure |
| Generated class must stay alive for the lifecycle of a normal class loader | `STRONG` | Gives loader-coupled unloading policy |
| Helper needs both private access and loader-coupled lifetime | `NESTMATE, STRONG` | Two options complementing two different axes |
| Sandbox/untrusted plugin code | Avoid handing out full-privilege Lookup and review the bytes' privileges | `NESTMATE` can open sensitive private access |
| Plugin reload with a short-lived custom loader | Choose the right lookup/loader; `STRONG` can be used if lifetime is tied to the plugin loader | Must ensure the loader is reclaimed and not retained by a static cache |
| Lambda-like runtime creating countless classes | Default hidden class is usually appropriate | Each class can be unloaded if no references remain |
| Need to look up the class by binary name through a classloader | **Do not use a hidden class** for that requirement | Hidden classes do not have a discoverable binary name |

There is no “always best” configuration. Decide based on **private access policy** and **expected loader/generated-code lifecycle**, then measure memory/behavior under real workload.

## 18. Common mistakes

### 18.1. Having `NESTMATE` and believing the hidden class will live as long as the host

False. Nest relationship does not determine unloading policy. Without `STRONG`, the hidden class can still be reclaimed while the loader/host is reachable, when no live references remain and the JVM decides to unload it.

### 18.2. Having `STRONG` and believing the hidden class has permission to read private fields

False. `STRONG` only applies a lifecycle relationship. If the bytes call a private method of the host while the hidden class is not a nestmate, the JVM may throw `IllegalAccessError`, as shown in the experiment.

### 18.3. `NestHost` in the bytes is enough for a hidden class

False. A hidden class does not inherit its nest from the `NestHost` attribute of the bytes. To join the lookup class's nest, `NESTMATE` must be explicitly chosen.

### 18.4. `getNestMembers()` does not list it, so `isNestmateOf` must be false

False. The `getNestMembers()` API does not list newly added hidden classes; `getNestHost()` and `isNestmateOf()` reflect the runtime relationship.

### 18.5. Same loader means two class identities are the same

False. Each `defineHiddenClass` call creates a new class. Equal `getClassLoader()` only indicates the same defining loader, not equal `Class<?>`. Identical source bytes also do not merge identities.

### 18.6. Calling `System.gc()` without seeing unloading means the default hidden class is strong

False. The JVM may not have run a suitable GC, references may still remain, or the observation method may be flawed. The contract only states that default hidden classes **can** be unloaded while the loader is reachable, with no timing SLA.

### 18.7. `STRONG` means keeping objects/instances alive forever

False. Normal instance objects are still GC'd according to their reachability. `STRONG` affects **class unloading**, not turning every instance of the class into a GC root.

### 18.8. Thread context class loader automatically decides where the hidden class is defined

False. `defineHiddenClass` uses the defining loader of the **lookup class**. Check `lookup.lookupClass().getClassLoader()` and `hidden.lookupClass().getClassLoader()`.

### 18.9. A hidden class cannot be used from outside because `Class.forName` fails

False. A holder of a valid `Class<?>`, instance, `Lookup`, or `MethodHandle` can still interact with the hidden class within privilege limits. “Hidden” mainly refers to nominal linking/discovery.

### 18.10. Catching `IllegalAccessException` will handle all private access errors

No. Creating a handle via Lookup can throw `IllegalAccessException`, whereas bytecode inside the hidden class attempting to violate Java access control when executed can throw `IllegalAccessError`. You must determine whether **the error occurs at factory/define time or at the call site in bytecode**.

## 19. Class definition and lifecycle debugging checklist

1. **Which API is being used?** `ClassLoader.defineClass`, `Lookup.defineClass`, or `Lookup.defineHiddenClass`? The three mechanisms are not equivalent.
2. **What is the lookup class?** Print `lookup.lookupClass()` or identify where `MethodHandles.lookup()` is called.
3. **Does the lookup have enough privileges?** `defineHiddenClass` requires a full-privilege lookup; do not use `publicLookup()` as a substitute.
4. **Are the bytes valid?** Supported class file version, `this_class` in the same package, accepted by the bytecode verifier.
5. **Is the defining loader right?** Compare `getClassLoader()`, module, and runtime package of the hidden class with the lookup class.
6. **Do the options match the goal?** `NESTMATE` for private nest access, `STRONG` for loader-coupled unloading policy.
7. **Is the runtime nest right?** Check `getNestHost()` and `isNestmateOf()`; do not rely on `getNestMembers()` as a registry.
8. **Where does the error occur?** When defining/linking/initializing the class, when calling `Lookup.findStatic`, or when hidden code executes `invokestatic` on a private member?
9. **Is any cache lifecycle holding a reference?** Class/Lookup/MethodHandle/instances/registries/call sites.
10. **Is the loader still reachable?** Inspect the entire object graph, not just one local variable or a closed JAR file.
11. **If you want to observe GC**: use heap dumps, class loading/unloading logs, weak references, and repeat across multiple runs; do not treat a single `System.gc()` result as a standard.
12. **If using `STRONG` with a long-lived loader**: account for potential metaspace accumulation when generating many classes.
13. **Is there a need for lookup by name?** If so, a hidden class may not be suitable.
14. **Are there security access-control concerns?** Check whether the loaded bytecode is trustworthy and whether `NESTMATE`/Lookup grants unwanted private access.
15. **Is there self-invocation in the bytes?** Because a hidden class has a special runtime name, class-file references to `this_class` are handled by the JVM under hidden class rules; do not assume it will load another named class with the template name.

## 20. Self-check exercises with answers

1. **Which two questions do the two options solve?** `NESTMATE` solves *nest-based private access*; `STRONG` solves *class unloading tied to the defining loader*.
2. **Is a default hidden class strong with respect to its loader?** No. It can be unloaded while the loader is still reachable.
3. **Does `STRONG` guarantee the class will never unload?** No. The loader can become unreachable and the JVM can unload it.
4. **Does `NESTMATE` mean the class will live as long as the nest host?** No.
5. **Does `NESTMATE` grant private access in every class in the same package?** No; only within the same nest under Java access rules.
6. **Does `STRONG` help a method in a hidden class call a `private` method of the host?** No, if the appropriate nest relationship is missing.
7. **If a nested template class already has `NestHost`, does defining it as hidden with no options keep the old nest?** No; by default a hidden class has its own nest.
8. **How to check the nest host of a hidden class?** `hiddenType.getNestHost()`.
9. **How to determine if a hidden class is a nestmate of the host?** `hiddenType.isNestmateOf(hostType)`.
10. **Why might `host.getNestMembers()` be missing a hidden nestmate?** It only lists nest members recorded in the `NestMembers` attribute, excluding hidden additions.
11. **Can a hidden class be loaded via `Class.forName(hidden.getName())`?** Not via normal nominal class loading.
12. **Does each `defineHiddenClass` call with the same bytes create a distinct class?** Yes.
13. **Where does the defining loader of a hidden class come from?** The defining loader of `lookup.lookupClass()`.
14. **Does changing the thread context class loader automatically change the defining loader?** No.
15. **Does `initialize=true` implicitly enable `STRONG`?** No; initialization is an independent parameter.
16. **If a `Lookup` to the hidden class exists, is the class guaranteed to be unloadable immediately?** No; the lookup reference can keep the class reachable.
17. **Why is `System.gc()` unsuitable as an assertion for unloading?** GC has no guarantees on timing/coverage and code may still hold references.
18. **With a long-lived app loader, what is the risk of using `STRONG` for tens of thousands of generated classes?** Class metadata/metaspace accumulation because classes do not unload independently.
19. **If you want a generated helper to see the host's private members while still being unloadable while the loader is alive, what do you choose?** `NESTMATE` **without** `STRONG`.
20. **If you want both private nest access and loader-coupled unloading, what do you choose?** `NESTMATE, STRONG`.
21. **Why is `plainPrivate=denied` an `IllegalAccessError` rather than a compiler error?** Valid bytes are derived into a hidden class with a new nest; the private access error occurs at runtime when resolving/executing the call in the hidden bytecode.
22. **Should a full-privilege hidden `Lookup` be shared with an untrusted plugin?** No, unless evaluated and intentionally delegating a capability with an appropriate access scope.
23. **Can a hidden class share the same module and protection domain with the host?** Yes; this is the contract when defining from a Lookup.
24. **Is ASM required to run the main hands-on exercise?** No. Only `javac` is needed to produce the nested template `.class`, then read bytes via `getResourceAsStream`.

## 21. Official Java SE 17 references

- [Java SE 17 — `MethodHandles.Lookup.defineHiddenClass`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): lookup privileges, same-package requirement, hidden name, loader, nest, unloading, class verification, and exceptions.
- [Java SE 17 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): official description of `NESTMATE` and `STRONG`.
- [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isHidden`, `getNestHost`, `isNestmateOf`, `getNestMembers`, `getClassLoader`.
- [JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): design motivation and the ability to unload hidden classes that are no longer needed.
- [JVMS Java SE 17 — §5.4.4 Access Control](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.4): nest-based access semantics.
- [JLS Java SE 17 — §12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): class unloading conditions with class loaders.
- [Java SE 17 — `javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): verifying `NestHost`/class file metadata of the template.

**Conclusion:** Choose `NESTMATE` **only when the hidden class genuinely needs private access within the same nest**; choose `STRONG` **only when you want the hidden class's lifecycle tied to the defining class loader**. By default, a hidden class can be unloaded independently of the loader. The two options do not substitute for each other; check `getNestHost()` and `isNestmateOf()` for access rights, while class unloading must be evaluated by reachability and GC policy, not by a single `System.gc()` call.