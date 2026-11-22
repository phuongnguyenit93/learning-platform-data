# Hidden Classes and Name-Based Discovery Limits in Java

## 1. The problem: creating a class at runtime, yet unable to look it up by name?

Some Java libraries need to **create classes dynamically** to execute compiled code, implement lambdas, proxies, data converters, or a short-lived piece of logic. These classes do not necessarily need to be **published by name** to all other code in the JVM. If every generated class is registered in the normal class-loading namespace, reloading multiple versions with the same name, retaining metadata, or managing memory can become difficult.

Since **Java 15**, the Java platform has provided the **hidden class** mechanism (JEP 371). The primary API is:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup().defineHiddenClass(classBytes, false);
Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

**A hidden class is still a real class created and linked by the JVM, but it cannot be found again by name-based class lookup APIs such as `Class.forName(String)` or `ClassLoader.loadClass(String)`.** Therefore, "hidden" in its name does not mean you cannot obtain `Class<?>` or invoke its methods; it means the class **does not participate in the ordinary binary-name discovery mechanism**.

This is what distinguishes the **Dynamic Class Definition** topic:

- An ordinary class normally has a **binary name** that loader lookup can use to find it again.
- A hidden class has a **runtime name carrying an identifying suffix**, but has **no binary name** usable as a nominal reference in another class's constant pool.
- The JVM can place a hidden class in the **same loader, runtime package, and protection domain** as the lookup class, while still **not registering that name as an ordinary class that can be found with `loadClass`**.
- With a hidden class, the creating code should keep `MethodHandles.Lookup`, `Class<?>`, or a `MethodHandle`/instance for use instead of storing the name string and trying to look it up again.
- A hidden class is created and **linked immediately**, whereas whether it is **initialized** depends on the `initialize` flag or a subsequent active use.
- By default, a hidden class has a "weak" relationship with its defining loader so it can be unloaded independently when no required references remain; `STRONG` changes this class-retention rule.

### Lesson Objectives

You will understand the concept, the `defineHiddenClass` API, why `getName()` does not help look up the class again, the differences between a hidden class and an ordinary dynamic class, how to define a hidden class from Java 17 bytecode, how to use method handles, the `NESTMATE`/`STRONG` options, lifecycle, safety, and diagnostic limitations.

## 2. Two ways to define dynamic classes: ordinary and hidden

### 2.1. Ordinary class via ClassLoader

A custom loader can create an ordinary class from bytes using the protected API:

~~~java
protected final Class<?> defineClass(
        String name, byte[] bytes, int offset, int length);
~~~

The actual call must be **inside a subclass of `ClassLoader`** with valid bytecode, the proper namespace, and the required JVM conditions. For an ordinary class:

- The class is defined with a **binary name**, for example `demo.dynamic.Task`.
- Loading via `ClassLoader.loadClass("demo.dynamic.Task")` can return the class already defined by this loader or its parent, depending on the loader policy.
- A loader cannot **re-define** another class with the same name already recorded for that loader: attempting a duplicate definition can cause a `LinkageError`.
- An ordinary class has a strong lifetime relationship with its defining loader: the class can be unloaded when JVM conditions are met and the loader is no longer reachable.

### 2.2. Hidden class via MethodHandles.Lookup

The method:

~~~java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException;
~~~

Differences:

- The call accepts a class-file representation and does **not** call the ordinary `ClassLoader.defineClass`.
- The hidden class has the **same defining loader**, **runtime package**, and **protection domain** as the **lookup class**.
- The lookup must have **full privilege access**, and the bytecode class must belong to the **same package** as the lookup class. Do not use an arbitrary lookup to inject a class into an arbitrary package.
- The class is **created and linked**; the `initialize=true` flag requests initialization immediately afterward, whereas `false` does not require the initializer to run immediately.
- The method returns the **`Lookup` of the hidden class itself**, not `Class<?>` directly. To obtain the class object, use `hiddenLookup.lookupClass()`.
- The result is not declared as a class carrying a binary name discoverable via `loadClass`/`Class.forName`.
- When calling `defineHiddenClass` multiple times with the same bytes, you can obtain **multiple distinct hidden classes**; the same kind of duplicate definition by binary name as with an ordinary class does not occur.

Comparison table:

| Criterion | Ordinary dynamic class | Hidden class |
|---|---|---|
| Typical API | `ClassLoader.defineClass` / `Lookup.defineClass` | `Lookup.defineHiddenClass` |
| Has a binary name for symbolic lookup | **Yes** | **No** |
| Has a `Class<?>` object | Yes | **Yes** |
| `Class.isHidden()` | `false` | `true` |
| Calling `Class.forName(name)` to find the exact class | Possible, if the loader sees the ordinary class | **Cannot** find a hidden class by name |
| `ClassLoader.loadClass(name)` | Can return the matching ordinary class | Does not find hidden classes |
| Assigned a defining loader | Yes | Yes, based on the lookup class |
| Can instantiate objects / invoke methods | Yes | Yes, via appropriate handles / `Class<?>` |
| Can create multiple classes from the same bytes in the same loader | Duplicate names are normally forbidden | Can create multiple independent hidden classes |
| Unloading | Tied to the lifetime of the defining loader | By default can be unloaded independently; `STRONG` changes this |
| Used as a type referenced from another class's constant pool | Possible when accessible | Cannot reference a hidden class by a nominal type name |

**Do not confuse "hidden" with "private".** `private` is a Java access modifier, whereas a `hidden class` is a special kind of class regarding **how it is defined and whether it can be referenced by name**. A hidden class does not turn all of its methods into private ones, nor does it automatically grant the caller access to read arbitrary private members.

## 3. A hidden class has a name, but no binary name

### 3.1. Why does `getName()` still return a String?

A hidden class can be created from bytecode that originally has the name `demo.HiddenTask`. The JVM appends a unique suffix to the runtime name, for example in **illustrative form**:

~~~text
demo.HiddenTask/0x00007fxxxxxxxxxx
~~~

The actual suffix varies across JVM versions and runs. Do not hardcode it, serialize it, and treat it as a name that can be looked up again.

Related APIs:

~~~java
Class<?> hidden = hiddenLookup.lookupClass();

System.out.println(hidden.isHidden());          // true
System.out.println(hidden.getName());           // contains runtime suffix
System.out.println(hidden.descriptorString());  // has a special form for hidden types
System.out.println(hidden.describeConstable()); // Optional.empty()
~~~

**Common misconception:** `Class.getName()` returns a **string describing the runtime class**, not a promise that every returned string is a **valid binary name** usable with `Class.forName`. For a hidden class, the `getName()` string contains a `/` separating the original name and the suffix, so it is not an ordinary binary name.

`Class.descriptorString()` of a hidden class also has a special form containing the suffix, **not a nominal field descriptor** that can be recorded in another class's constant pool. `Class.describeConstable()` returns `Optional.empty()` because a hidden class has no nominal description to be resolved by name in a constant pool.

### 3.2. Name-based lookup APIs do not find hidden classes

According to the Javadoc of `Lookup.defineHiddenClass`, a hidden class is not discoverable by:

- `Class.forName(String)`, as well as `Class.forName(String, boolean, ClassLoader)`.
- `ClassLoader.loadClass(String)` / `loadClass(String, boolean)`.
- `MethodHandles.Lookup.findClass(String)`.

The reason is **not** that the loader lacks a reference to the hidden class, or that the class is not yet initialized. The JVM intentionally **does not place the hidden class in the lookup table for ordinary classes by binary name**.

Diagram:

~~~text
bytes from demo/HiddenTask.class
   |
   v
hostLookup.defineHiddenClass(bytes, false)
   |
   +--> hiddenLookup.lookupClass() -> Class<?> (isHidden=true)
   |         |
   |         +--> findStatic / findVirtual / findConstructor
   |         +--> reflection when Class<?> and appropriate permissions are available
   |
   +--> Class.forName(hidden.getName()) -----------> NOT FOUND
   +--> hostLoader.loadClass(hidden.getName()) ----> NOT FOUND
~~~

**Do not use `ClassNotFoundException` as evidence that a hidden class never existed.** The class may have already been created, linked, and successfully invoked by a `MethodHandle` — there is simply no lookup path from its name.

### 3.3. Also not a superclass/type in another class's nominal signature

Because a hidden class has no binary name that can be recorded in a constant pool, another class **cannot directly refer to a hidden class** via a symbolic reference as a superclass, field type, parameter type, or return type. This is an intentional limitation of hidden classes, not a bug in Java reflection.

Code having an `Object obj` pointing to an instance of a hidden class is still valid. Code can also use an **interface/ordinary type** as a contract, provided bytecode and access rules permit it. What is restricted is **nominal reference to the hidden type**, not every way of exchanging objects.

### 3.4. Do not confuse with anonymous classes, local classes, and lambdas

| Kind | Can it be a hidden class? | Name-based discovery |
|---|---|---|
| Ordinarily compiled nested class `Outer$Inner` | Not merely because it is nested | Ordinary binary name typically uses `$` |
| Anonymous/local class generated by `javac` | Usually an ordinary class in bytecode | Has a binary name following compiler rules; the name should not be treated as a stable API |
| Lambda implementation | The JVM/compiler may use hidden classes as an implementation detail | Should not depend on the names or number of generated classes |
| Hidden class created by `defineHiddenClass` | **Yes**, by definition | Cannot be looked up again via `Class.forName`/`loadClass` |

Do not treat the way a particular JDK release implements lambdas as a contract guaranteeing that every Java runtime/version uses the exact same names or class shape. `Hidden class` is a JVM/API mechanism, not a synonym meaning all nested/anonymous types are hidden.

## 4. Conditions for creating a hidden class properly

### 4.1. Using a Lookup with sufficient privileges

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandles.Lookup generated =
        lookup.defineHiddenClass(bytes, false);
~~~

If `MethodHandles.lookup()` is called from a method of a normal class, the result typically has full privilege access with respect to that lookup class itself. However, a `publicLookup()` does not have all the corresponding privileges to use `defineHiddenClass`.

If the `Lookup` lacks full privilege access, the method can throw **`IllegalAccessException`**. Attempting to use `privateLookupIn` across module boundaries is also subject to `opens`/access checks and does not automatically grant unauthorized privileges.

### 4.2. The bytecode must belong to the same package as the lookup class

If the lookup class is `demo.HiddenHost`, the input class bytes must declare the class in package `demo` (for example `demo.HiddenTask`). Do not pass a classfile named `other.pkg.Task` and expect `defineHiddenClass` to create a hidden class in a different package: the API will reject it under the package condition.

The hidden class receives:

- The **defining ClassLoader** of the lookup class.
- The **runtime package** matching the lookup class.
- The **ProtectionDomain** of the lookup class.
- The corresponding runtime **module**; it does not automatically create a new named module.

All of this must still obey class-file format, package/access/module checks, and verification/linking rules.

### 4.3. Real class bytes, not a name or path

`defineHiddenClass` accepts a **`byte[]` representing a class file**, and does not accept:

~~~text
"demo.HiddenTask"
"src/demo/HiddenTask.java"
"demo/HiddenTask.class"
~~~

The strings above are names/paths, not classfile contents. You can read from a compiled file or generate bytes using an appropriate bytecode generator. When generating bytecode yourself, you must ensure a valid **classfile version**, format, and constant pool entries.

### 4.4. Linking and initialization occur at two different times

The two calls:

~~~java
lookup.defineHiddenClass(bytes, false);
lookup.defineHiddenClass(bytes, true);
~~~

both **create and link** hidden classes (two separate definitions if called twice). The boolean flag:

- `false`: does not require running `<clinit>` immediately. The hidden class will initialize upon subsequent active use.
- `true`: the JVM initializes the hidden class after linking, per the method contract.

Distinguish this from `Class.forName(Module, String)`, which has the rule of **not automatically linking or initializing** in its module overload. Do not extrapolate from one API to every way of defining dynamic classes.

## 5. Standalone Java 17+ example: definition succeeds, yet lookup by name fails

This exercise is designed to **completely exclude the template class from the runtime application classpath**. `HiddenHost` will read the bytes of `HiddenTask.class` as data, call `defineHiddenClass`, retain the result, and invoke a method using `MethodHandle`.

### 5.1. Directory tree

~~~text
demo/
  src/
    template/
      demo/
        HiddenTask.java
    app/
      demo/
        HiddenHost.java
  build/
    template/
      demo/
        HiddenTask.class
    app/
      demo/
        HiddenHost.class
~~~

**Rule for an accurate demo:** the `java` command uses only `-cp build/app`. Do not add `build/template` to the classpath; if you do, `Class.forName("demo.HiddenTask")` can find the **ordinary template class**, creating the false impression that it found the hidden class.

### 5.2. File `src/template/demo/HiddenTask.java`

~~~java
package demo;

class HiddenTask {
    static {
        System.out.println("TASK_INITIALIZED");
    }

    static String message() {
        return "HELLO_HIDDEN";
    }
}
~~~

The template class is package-private. `static {}` helps observe the timing of initialization; `message()` returns an easily verifiable result.

Even though the source resides in a different tree, the package is still `demo` to satisfy the same-package requirement with the lookup class of `HiddenHost`.

### 5.3. File `src/app/demo/HiddenHost.java`

~~~java
package demo;

import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.nio.file.Files;
import java.nio.file.Path;

public final class HiddenHost {
    public static void main(String[] args) throws Throwable {
        byte[] bytes = Files.readAllBytes(
                Path.of("build/template/demo/HiddenTask.class"));
        MethodHandles.Lookup hostLookup = MethodHandles.lookup();

        MethodHandles.Lookup hiddenLookup =
                hostLookup.defineHiddenClass(bytes, false);
        Class<?> hidden = hiddenLookup.lookupClass();

        System.out.println("hidden=" + hidden.isHidden());
        System.out.println("sameLoader="
                + (hidden.getClassLoader()
                    == HiddenHost.class.getClassLoader()));
        System.out.println("samePackage="
                + hidden.getPackageName().equals(
                    HiddenHost.class.getPackageName()));
        System.out.println("nameHasSlash="
                + hidden.getName().contains("/"));
        System.out.println("descriptorHasSlash="
                + hidden.descriptorString().contains("/"));
        System.out.println("noNominalDescriptor="
                + hidden.describeConstable().isEmpty());

        try {
            Class.forName(hidden.getName());
            System.out.println("forNameFound=true");
        } catch (ClassNotFoundException expected) {
            System.out.println("forNameFound=false");
        }

        try {
            HiddenHost.class.getClassLoader().loadClass(hidden.getName());
            System.out.println("loadClassFound=true");
        } catch (ClassNotFoundException expected) {
            System.out.println("loadClassFound=false");
        }

        Class<?> another =
                hostLookup.defineHiddenClass(bytes, false).lookupClass();
        System.out.println("twoDefinitionsDistinct="
                + (another != hidden));

        MethodHandle mh = hiddenLookup.findStatic(
                hidden, "message", MethodType.methodType(String.class));

        System.out.println("beforeInvoke");
        String value = (String) mh.invokeExact();
        System.out.println("result=" + value);
    }
}
~~~

**Why is `throws Throwable` present?** `MethodHandle.invokeExact` can throw `Throwable` per its signature. Declaring it on `main` is meant to keep the demo clear, not a recommendation that every production application entry point should declare `throws Throwable`.

### 5.4. Compiling/running on Linux and macOS

From the `demo` directory:

~~~sh
mkdir -p build/template build/app

javac --release 17 -d build/template \
    src/template/demo/HiddenTask.java

javac --release 17 -d build/app \
    src/app/demo/HiddenHost.java

java -cp build/app demo.HiddenHost
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/template, build/app | Out-Null
javac --release 17 -d build/template src/template/demo/HiddenTask.java
javac --release 17 -d build/app src/app/demo/HiddenHost.java
java -cp build/app demo.HiddenHost
~~~

Do not use the same output folder for template and app: two separate compilation trees help prove that **the ordinary class does not appear on the runtime classpath**.

### 5.5. Exact verified stdout

~~~text
hidden=true
sameLoader=true
samePackage=true
nameHasSlash=true
descriptorHasSlash=true
noNominalDescriptor=true
forNameFound=false
loadClassFound=false
twoDefinitionsDistinct=true
beforeInvoke
TASK_INITIALIZED
result=HELLO_HIDDEN
~~~

This is the stdout of the program compiled with `javac --release 17` and executed on a JDK supporting Java 17.

### 5.6. Meaning of each output

| Output | Interpretation |
|---|---|
| `hidden=true` | `Class.isHidden()` identifies a class created by `defineHiddenClass` |
| `sameLoader=true` | The hidden class is associated with the defining loader of `HiddenHost` |
| `samePackage=true` | The hidden class belongs to package `demo` of the lookup class |
| `nameHasSlash=true` | `getName()` has a runtime suffix, **not a binary name** |
| `descriptorHasSlash=true` | The hidden class's descriptor has a special separator and cannot be used as a nominal descriptor |
| `noNominalDescriptor=true` | `describeConstable()` is empty, with no nominal constant description |
| `forNameFound=false` | The hidden class cannot be found again via `Class.forName(hidden.getName())` |
| `loadClassFound=false` | `ClassLoader.loadClass(hidden.getName())` also cannot find it |
| `twoDefinitionsDistinct=true` | The same byte array creates two hidden classes with **different identities** |
| `beforeInvoke` | Point in time after create/link with `initialize=false` |
| `TASK_INITIALIZED` | Invoking the static method via the method handle created an active use, triggering initialization |
| `result=HELLO_HIDDEN` | The hidden class still executes code normally when an appropriate handle is available |

**What should not be inferred:** `forNameFound=false` does not mean the `HiddenTask.class` bytes were not read or the class was not linked. We already obtained the `Class<?>`, found a method handle, and ran the method.

### 5.7. Why can `Class.forName("demo.HiddenTask")` be misleading?

If you accidentally leave `build/template` on the application classpath:

~~~sh
java -cp "build/app:build/template" demo.HiddenHost
~~~

on Linux/macOS (Windows uses `;`), the JVM can load the **ordinary class** `demo.HiddenTask` by name. However, that ordinary class is **different** from the hidden class created by `defineHiddenClass` from the same bytes. Do not use a `Class.forName("demo.HiddenTask")` test to claim that a hidden class has become discoverable.

The most accurate test is to use `hidden.getName()` itself and show that ordinary name-based lookup APIs still fail; or directly compare `ordinaryClass != hiddenClass` if both exist.

### 5.8. Variations for self-verification

**Variation A — `initialize=true`:** replace the first `defineHiddenClass(bytes, false)` with `defineHiddenClass(bytes, true)`. The `TASK_INITIALIZED` line appears during the define call, **before** the `hidden=true` output sequence; afterward, the invocation does not re-initialize the class.

**Variation B — Not invoking the method handle:** remove the `mh.invokeExact()` line. With `initialize=false`, if there is no other active use, `TASK_INITIALIZED` does not appear in the demo.

**Variation C — Additional define calls:** create more hidden classes from the same bytes and compare `Class<?>` identities. They are independent even when sharing the same lookup class, original classfile name, and defining loader.

**Variation D — Wrong package:** compile the template under `foreign.HiddenTask` while keeping `HiddenHost` in `demo`. `defineHiddenClass` will reject input not in the same package; do not use dynamic names to bypass access conditions.

**Variation E — Without a full-privilege lookup:** try `MethodHandles.publicLookup().defineHiddenClass(bytes, false)`. This is an example of a lookup lacking privileges, expected to fail with `IllegalAccessException` per the API contract.

## 6. ClassOption options: NESTMATE and STRONG

The API accepts varargs of the `MethodHandles.Lookup.ClassOption` enum:

~~~java
import static java.lang.invoke.MethodHandles.Lookup.ClassOption.NESTMATE;
import static java.lang.invoke.MethodHandles.Lookup.ClassOption.STRONG;

MethodHandles.Lookup hiddenNestmate =
        MethodHandles.lookup().defineHiddenClass(bytes, false, NESTMATE);
MethodHandles.Lookup hiddenStrong =
        MethodHandles.lookup().defineHiddenClass(bytes, false, STRONG);
~~~

This is an **illustrative snippet inside an appropriate class/method**, requiring `bytes` to be available and valid access/package conditions. The two define calls create two separate hidden classes, rather than turning the first class into a nestmate/strong class after creation.

### 6.1. `NESTMATE`: placed into the lookup class's nest

Java nestmates are classes/interfaces in the same **nest** that are permitted to access private members according to JVM rules.

If `NESTMATE` is passed, the hidden class is added to the lookup class's nest. Therefore, the hidden class can access private members of classes/interfaces in the same nest **according to nestmate access rules**.

If `NESTMATE` is **not** selected, the hidden class defaults to having its own nest even when sharing the same package/loader. Thus:

~~~text
Same package + same defining loader
    ≠ automatically granted access to private members of HiddenHost.

NESTMATE
    => the hidden class joins the appropriate nest so nestmate private access applies.
~~~

Do not misunderstand `NESTMATE` as allowing arbitrary access to private members of other modules/classes. Nest membership and lookup privileges are still checked.

### 6.2. `STRONG`: strong lifecycle relationship with the defining loader

Normally, an ordinary class maintains a strong relationship with its defining loader; the class is unloaded only when the loader can be collected according to JVM conditions.

A **default** hidden class can be unloaded even while its defining loader remains reachable, **if no references remain keeping that hidden class alive**. The reason: frameworks may create many temporary classes inside a long-lived loader.

If `STRONG` is selected:

- The hidden class is given a strong relationship with its defining loader **just like an ordinary class**.
- It is normally not unloaded independently while the loader remains reachable.
- This is useful for a hidden class that needs the same lifecycle as the host class/loader, but can cause higher **metadata retention** if very many definitions are created.
- It is chosen at define time; the mode cannot be changed after the class has been created.

**There is no guarantee that the GC will unload a hidden class immediately when you drop the `Class<?>` reference.** The class unloading mechanism depends on reachability, handles, instances, threads, the JVM, and other references. `STRONG` adjusts unloadability rather than acting as a direct command to trigger GC.

### 6.3. Combining options

~~~java
MethodHandles.Lookup lk = MethodHandles.lookup().defineHiddenClass(
        bytes, false, NESTMATE, STRONG);
~~~

They can be combined so that the hidden class both joins the lookup class's nest and has a strong relationship with the loader. Only use this when you need those exact two properties; do not enable them by default just to "avoid not-found-by-name errors" — `STRONG` and `NESTMATE` do **not** turn a hidden class into a discoverable ordinary class.

## 7. Using a hidden class without a name

### 7.1. Keeping the `Lookup` returned by the API

This is usually the clearest path:

~~~java
MethodHandles.Lookup hiddenLookup =
        hostLookup.defineHiddenClass(bytes, false);
Class<?> hiddenClass = hiddenLookup.lookupClass();

MethodHandle run = hiddenLookup.findStatic(
        hiddenClass, "message", MethodType.methodType(String.class));
String value = (String) run.invokeExact();
~~~

This is a snippet that needs to be inside a method with appropriate handling of checked exceptions and `Throwable`. `hiddenLookup` is a lookup on the hidden class itself, so it is capable of performing `find...` operations according to that lookup's privileges.

Do not build a "registry using `getName()` followed by `Class.forName`" to retrieve a hidden class. If a framework needs a registry, store **references to the class/lookup/method handle or object** with a managed lifecycle. Note that retaining strong references also prevents the class from being unloaded as expected.

### 7.2. Passing objects via an ordinary interface

A hidden class can implement an ordinary interface known to the host. The host receives and uses the object through that interface **without needing to know the hidden class's name**.

~~~java
public interface Operation {
    String run(String input);
}
~~~

The snippet above is an illustrative interface declaration. To implement it with a hidden class, there must be bytecode satisfying the contract, appropriate lookup/module/package/access conditions, and instance creation logic. This is a suitable approach for generated adapters or lambda-like runtime objects.

When crossing module/classloader boundaries, the interface contract must still preserve the exact runtime type identity; hidden classes do not eliminate the JVM's type-identity rules.

### 7.3. Reflection can still be used if you have the Class object

`Class.isHidden() == true` does not mean Java reflection is completely forbidden. If code is holding `Class<?> hidden`, it can call:

~~~java
java.lang.reflect.Method method = hidden.getDeclaredMethod("message");
~~~

and use reflection when Java/JPMS access checks permit it. However, `getDeclaredMethod` retrieving metadata differs from the ability to call setAccessible/invoke. What is unsupported is trying to find `hidden` from a string name via `Class.forName`.

In short: **a hidden class is non-discoverable by name, not invisible to all reflection**.

### 7.4. Class data when class-specific state is needed

Java also provides:

~~~java
MethodHandles.Lookup defineHiddenClassWithClassData(
        byte[] bytes, Object classData, boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
~~~

This API creates a hidden class together with class data, useful for frameworks that need to pass metadata/state for generated bytecode to access via the method handles/class data mechanism. It differs from attaching a name/JAR path to a class, and does not turn a hidden class into an ordinary class. You should read the contract of `MethodHandles.classData`/`classDataAt` before designing with it, especially when state is mutable.

The main scope of this lesson is **name-based discovery**, so the class data API is mentioned as an extension capability rather than replacing the basic example.

## 8. Lifecycle, memory, and framework organization

### 8.1. Why did the JVM design hidden classes with independent unloading capability?

Frameworks can generate very many tiny implementations: adapters for individual call site types, schema-based serializers/deserializers, proxies, or lambda implementations. If every class had to stay alive until the long-lived application ClassLoader was collected, metaspace could retain many classes that are no longer used.

With a default hidden class, the JVM is allowed to unload it when no required references remain even while the loader is still alive. This is an advantage in large-scale dynamic class-loading environments. However, if a framework caches every `Lookup`/`Class<?>` in a permanent static map, that advantage is largely lost.

### 8.2. References that keep the class alive

A hidden class can remain reachable through:

- A `Class<?>` object or `MethodHandles.Lookup` holding a reference.
- `MethodHandle`, `MethodType`, `CallSite`, and related structures.
- Instances of the hidden class.
- Callbacks/caches/static registries in the framework.
- Threads executing code or holding related objects.
- Internal references still maintained by the JVM during runtime operation.

**Do not try to predict unloading timing based solely on calling `System.gc()`**. There is no reliable fixed output for testing unloading with GC in a small program.

### 8.3. Hidden classes do not replace custom ClassLoaders in every problem

Hidden classes fit **internal** implementations that need to retain handles and do not need external symbolic discoverability. If you want:

- Plugin classes loaded from JARs by binary name.
- A framework finding classes from the classpath/service descriptors.
- Classes exported and referenced in other classes' bytecode as ordinary types.
- Management of multiple module/plugin boundaries with full classpath/module path.

then ordinary classes, URLClassLoader, ServiceLoader, or module layers may be more suitable. Hidden classes do not replace a standard SPI/plugin architecture simply by changing the define API.

### 8.4. Security and untrusted code

`defineHiddenClass` requires a sufficiently privileged `Lookup` and package/module constraints. However, "hidden" **does not mean a sandbox** for untrusted bytecode. The code can still run in the process with the application's privileges, cause side effects upon initialization or invocation, consume CPU/memory, and call permitted APIs.

If bytecode comes from an external source, you must validate/protect inputs, restrict artifact provenance, and consider process isolation; do not hand over arbitrary privileged lookups to untrusted plugins.

## 9. Troubleshooting common errors

| Symptom | Common cause | How to check |
|---|---|---|
| `Class.forName(hidden.getName())` throws `ClassNotFoundException` | **True nature of hidden classes**: not discoverable by name | Retain `Lookup`/`Class<?>`/MethodHandle; do not try to look it up again |
| `ClassLoader.loadClass(hidden.getName())` fails | A hidden class has no binary name for loader lookup | Do not assume having the same loader is enough |
| `defineHiddenClass` throws `IllegalAccessException` | The lookup lacks full privilege access | Check `lookupModes`, the origin of the `Lookup`, and JPMS permissions |
| `defineHiddenClass` throws `IllegalArgumentException` | The bytecode class is not in the same package, or an argument/option is invalid | Check the internal classfile name and the lookup package |
| `ClassFormatError` or `VerifyError` | Invalid classfile bytecode or verification rule violation | Inspect the bytes, constant pool, classfile version, and generator |
| `UnsupportedClassVersionError` | Bytes were compiled for a newer JVM than the runtime | `java -version`, `javac --release` |
| `LinkageError` during linking | Dependency/loading constraints/verification linkage | Log the cause; do not assume it is due to a "duplicate hidden name" |
| `ExceptionInInitializerError` when `initialize=true` or on active use | `<clinit>` executed and failed | Check the static initializer and root stack trace |
| Method handle lookup gets `NoSuchMethodException` | Method name/signature mismatch | Check `MethodType` and the declared method |
| Method handle access gets `IllegalAccessException` | The lookup does not have the corresponding access rights | Use a valid lookup; do not forcibly open access |
| `ClassCastException` when passing across boundaries | Mismatched interface identity/loader or cast logic | Compare the `Class<?>` of the shared API |
| Increasing metaspace/class retention | Unbounded caches, inappropriate `STRONG`, or objects retaining the class | Review references, handles, and lifecycle |
| Reflection sees the class, yet `Class.forName` still fails | Reflection already has `Class<?>`; name lookup cannot find hidden classes | These are two different mechanisms |
| Code depending on the `/0x...` suffix breaks when changing JDKs | The runtime suffix is not a standard persistence format | Do not use the suffix as a stable identifier |

### 9.1. Distinguishing three layers of failure

~~~text
(1) File/bytes:
    source .java -> compiled .class byte[]
    possible IOException / ClassFormatError / UnsupportedClassVersionError

(2) Define/link:
    MethodHandles.Lookup.defineHiddenClass(...)
    possible IllegalAccessException / IllegalArgumentException / LinkageError

(3) Usage:
    Lookup/Class<?>/MethodHandle/instance
    possible NoSuchMethodException / IllegalAccessException
    or errors during initialize/invoke
~~~

**Do not add a required `Class.forName` step between (2) and (3).** The hidden class is returned directly via lookup — name-based lookup is not the way to obtain the reference.

### 9.2. Appropriate logging

You can log:

~~~java
System.out.println("hidden=" + type.isHidden());
System.out.println("runtimeName=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
~~~

This is an illustrative snippet requiring `type` to be available. Logging the runtime name is useful for diagnostics, but it is not a durable identifier. When you need to prove compatibility or runtime identity, compare the `Class<?>` reference, defining loader, module, and trusted bytecode source information.

## 10. Misconceptions to avoid

1. **"A hidden class has no `Class<?>` object."** False: `hiddenLookup.lookupClass()` returns the class.
2. **"Because it has `getName()`, you can call `Class.forName`."** False: a runtime name is not a binary name.
3. **"Just adding the classfile to the classpath lets `Class.forName(hidden.getName())` find the hidden class."** False: if an ordinary template class is present, it is a different class.
4. **"Hidden classes cannot be initialized or execute code."** False: they can be initialized and invoked normally.
5. **"`initialize=false` means the class is not linked."** False: defineHiddenClass creates and links it; it only defers initialization.
6. **"A hidden class can be used directly as a superclass referenced by name from another class."** False: there is no binary name for a nominal symbolic reference.
7. **"Same defining loader means same class identity."** False: hidden classes defined separately from the same bytes are still distinct `Class<?>` objects.
8. **"Even without selecting NESTMATE, a hidden class can still automatically access the host's private fields."** False: being in the same package does not grant private access.
9. **"Selecting STRONG makes `Class.forName` find the hidden class."** False: STRONG affects lifecycle, not discoverability.
10. **"A hidden class is always unloaded immediately when code exits the method."** False: references and GC determine this.
11. **"Hidden classes can be used instead of all plugin classes by name."** False: plugin discovery/SPI has its own contract.
12. **"`isHidden()` returns true for every anonymous/local/nested class."** False: those classes are usually ordinary types; you must look at the JVM API that created the class.
13. **"Hidden classes are a security measure for untrusted code."** False: lookup privileges and name hiding do not create a security sandbox.
14. **"Reading a unique suffix string is a way to store identity long-term."** False: the runtime name has no stable persistence semantics.
15. **"Reflection can never inspect a hidden class at all."** False if the code holds the `Class<?>` and has sufficient permissions.
16. **"`Class.forName(Module, name)` can find a hidden class because the right module was passed."** False: named-module lookup does not bypass a hidden class's non-discoverable-by-name restriction.

## 11. Self-check questions and exercises

1. In which Java version was `Lookup.defineHiddenClass` introduced? Does it return `Lookup` or `Class<?>`?
2. Why does `Class.getName()` on a hidden class return a value, yet `Class.forName` still cannot find it?
3. What is the difference between a **runtime name** and a **binary name** in the case of a hidden class?
4. What does `Class.isHidden()` return for an ordinary class and for a hidden class?
5. Why is `Class.describeConstable()` on a hidden class `Optional.empty()`?
6. Can `Class.descriptorString()` of a hidden class be used as a nominal descriptor recorded in another class's constant pool?
7. Does a hidden class have a defining ClassLoader? Where does it get its loader and runtime package from?
8. Why must the bytecode passed to `defineHiddenClass` declare the same package as the lookup class?
9. Does `MethodHandles.publicLookup()` have sufficient privileges to define a hidden class?
10. Does `defineHiddenClass(bytes, false)` link the class automatically? Does it run `<clinit>` immediately?
11. Why does the `TASK_INITIALIZED` line in the demo appear after `beforeInvoke`?
12. Why can `Class.forName("demo.HiddenTask")` sometimes still succeed if the template is accidentally left on the app classpath, yet this does not prove the hidden class was found?
13. Do two defineHiddenClass calls with the same bytes create the same `Class<?>` object?
14. What does `NESTMATE` change regarding private access rights?
15. Does `STRONG` affect discoverability or class lifecycle?
16. Why can a default hidden class be unloaded while its defining loader is still alive?
17. How can you invoke a static method of a hidden class if you cannot look the class up again by a string name?
18. Distinguish between using `MethodHandle` and using Java reflection once you already have the `Class<?>` of a hidden class.
19. When designing generated adapters, why should you keep a shared API interface instead of trying to expose the hidden type across the system?
20. A plugin loader needs to look up classes by binary name to load extensions from a JAR: is a hidden class an appropriate default choice? Why or why not?
21. If `defineHiddenClass` throws `IllegalAccessException`, does the issue usually lie in lookup privileges or in the class name not existing on the classpath?
22. Why does a `ClassNotFoundException` from `loadClass(hidden.getName())` not prove that the hidden class never ran?
23. How can keeping every `MethodHandle` in a permanent static cache affect unloading?
24. What should be done if bytecode is supplied by an untrusted third party?

**Completion criteria:** run the Java 17 example successfully and explain all 12 lines of stdout; thoroughly understand the name-based lookup limitation and know how to retain `Lookup`/`Class<?>`/`MethodHandle`; distinguish ordinary vs. hidden classes, initialize vs. link, NESTMATE/STRONG, and class lifecycle.

## 12. Official documentation

- [Java SE 21 — `MethodHandles.Lookup#defineHiddenClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineHiddenClass(byte%5B%5D,boolean,java.lang.invoke.MethodHandles.Lookup.ClassOption...)): authoritative reference on defining hidden classes, name lookup, initialization, access, and unloading.
- [Java SE 21 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): `NESTMATE` and `STRONG`.
- [Java SE 21 — `Class.isHidden()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#isHidden()): detecting hidden classes.
- [Java SE 21 — `Class.descriptorString()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#descriptorString()): descriptor string for a runtime type.
- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): design motivation and limitations of non-discoverable classes.
- [JVMS Java SE 21 — Chapter 5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html): creation, loading, linking, initialization, and runtime identity.

**Conclusion:** a hidden class does not vanish from the JVM, nor is it synonymous with a "private class". It is a dynamic class **without a binary name for name-based discovery**. Keep a handle/reference to use it, design an appropriate lifetime, and use an ordinary class when the system genuinely needs to load or reference a class by its binary name.
