# 15.7. Accessing Hidden Class Members Using the Returned Lookup and MethodHandle

## Objectives

This lesson belongs to Java Advance – dynamic-runtime, section **15. Class Definition**. After completing it, you will be able to:

- Accurately state the characteristics of a hidden class and explain why a hidden class cannot be retrieved by concatenating a name and calling `Class.forName`.
- Use `MethodHandles.Lookup.defineHiddenClass` from valid class-file bytes and retain the **returned Lookup** instead of merely storing a name string.
- Use `lookupClass()`, `findConstructor`, `findVirtual`, `findStatic`, `findGetter`, and `findSetter` to work with **private** constructors, fields, and methods of a hidden class.
- Convert a `MethodHandle` whose receiver is a runtime class that cannot be named directly in source code into a handle with an `Object` or interface signature via `asType`.
- Distinguish the private access that the returned Lookup has to the hidden class itself from the private access to the **host class** with/without `ClassOption.NESTMATE`.
- Distinguish class definition, class initialization (`initialize` / `ensureInitialized`), class identity, and lifetime choice with `ClassOption.STRONG`.
- Diagnose lookup errors, classfile errors, package/module errors, `WrongMethodTypeException`, cast errors, and `IllegalAccessError` inside target bytecode.
- Design caching and control access-right scope, without treating hidden classes as a sandbox for untrusted bytecode.

Examples are written for **Java 17+**, with clear compilation commands and stdout. Snippets labeled *fragment* only illustrate the API and do not run standalone; the two complete programs use self-contained Java source without requiring ASM/Byte Buddy.

## 1. What problem do hidden classes solve?

A runtime framework may want to generate a dedicated implementation for a call or a data shape. That implementation needs a real `Class<?>` and may have constructors, fields, and instance/static methods. However, the framework does not want the implementation's name to become a binary-name linkage point for `Class.forName`, loaders, or external code.

Java has **hidden classes**: classes defined at runtime that cannot be looked up by name via normal class lookup mechanisms, yet **are still real classes** and still execute Java bytecode with access checks.

~~~text
Trusted class-file bytes
        |
        v
Lookup of code with defining privilege
        |
        | defineHiddenClass(bytes, initialize, options)
        v
Returned Lookup (lookupClass = new hidden class)
        |
        +--> lookupClass() --------> Class<?> hiddenType
        |
        +--> findConstructor() ----> MethodHandle to create an instance
        |
        +--> findVirtual() --------> MethodHandle for an instance method
        |
        +--> findStatic() ---------> MethodHandle for a static method
        |
        +--> findGetter/Setter() --> MethodHandle for a field
~~~

Key point: **`defineHiddenClass` returns `MethodHandles.Lookup`, not a `Class<?>` directly**. The returned Lookup is the "key" for most of the operations needed in this lesson.

### 1.1. A hidden class does not mean a non-interactable class

A hidden class:

- Has a `Class<?>` object retrieved via `returnedLookup.lookupClass()`.
- Can be instantiated, have its methods invoked, and have its fields read/written if the proper `MethodHandle` and sufficient permissions are used.
- Can implement an interface known to the application in advance; in that case, instances can be interacted with through that interface.
- Can contain `private`, `public`, `static`, or instance members like an ordinary class, within the bounds of a valid classfile.
- Can be defined multiple times from **the same byte array**, creating **different runtime classes**.
- Does not allow code to retrieve the class via `Class.forName(hiddenType.getName())`. A runtime name with a special suffix is not a binary name used for normal loading.

A hidden class is not "another version of a private nested class". An ordinary private nested class still has a binary name and its own classfile; `private` determines **access rights**, whereas `hidden` is a characteristic of **how the class is defined and looked up in the JVM**.

### 1.2. Not a sandbox

Loading and running a hidden class means running JVM bytecode. The "not discoverable by name" property **does not automatically restrict** I/O, network, CPU, resource access, or code side effects. Only define trusted bytecode or have independent safety control mechanisms. Do not build an API that lets users submit arbitrary bytes and assume the word "hidden" has isolated malicious code.

## 2. The `defineHiddenClass` API and the returned Lookup

Central signature:

~~~java
// Abbreviated API signature for reference, not a standalone program:
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException;
~~~

| Component | Meaning | What to verify |
| --- | --- | --- |
| `bytes` | Contents of **class-file bytes**, not Java source | Valid class file, correct package/context, JVM compatible |
| `initialize` | Whether to request class initialization immediately during definition | Distinguish defining from running the static initializer |
| `options` | `NESTMATE`, `STRONG` options | Nest and lifetime options; not arbitrary privileges |
| Returned `Lookup` | Has `lookupClass()` as the new hidden class | Keep needed privileges or obtain handles before discarding the lookup |

**Important privilege requirement:** The `Lookup` calling `defineHiddenClass` requires **full privilege access**. The bytecode used for definition must have a class belonging to **the appropriate same package as the lookup class**, per the API contract. Do not take `MethodHandles.publicLookup()` and use it to define a private class in an arbitrary package/module.

An illustrative flow:

~~~java
// Fragment: classBytes are trusted, valid class-file bytes in the correct package.
MethodHandles.Lookup defining = MethodHandles.lookup();
MethodHandles.Lookup hiddenLookup =
        defining.defineHiddenClass(classBytes, false);
Class<?> hiddenType = hiddenLookup.lookupClass();
~~~

The three variables serve different functions:

1. `defining` represents the privilege context **of the calling class**.
2. `hiddenLookup` is the **new** Lookup, whose lookup class is the newly created hidden class itself; it has private access to the hidden class per the API.
3. `hiddenType` is the actual runtime Class object of the hidden class; it is **not** a name that can be saved and used with `Class.forName`.

`lookupClass()` allows passing the Class object itself into `findConstructor`/`findVirtual`. From there, we can use MethodHandle to invoke members that Java source cannot invoke by the hidden class's name.

### 2.1. Why do we need to keep the returned Lookup?

Suppose you create a hidden class and only save `hiddenType.getName()`. Other code tries to do:

~~~java
// WRONG fragment for finding a hidden class:
Class<?> type = Class.forName(hiddenType.getName());
~~~

A hidden class cannot be found by name like that. Conversely, keeping `hiddenLookup` or at least keeping `hiddenType` and the created MethodHandles retains the necessary runtime reference. The `Lookup` API also determines **permissions** when finding private members, rather than merely providing a class name.

### 2.2. The returned Lookup is a capability

`Lookup` is not just metadata; it allows the code holding it to find members within the scope of its corresponding access modes. The returned Lookup from `defineHiddenClass` carries privileges for **private members of the hidden class**. If you pass this Lookup to external code, you may unintentionally expose implementation details that should not be public.

You should separate:

~~~text
Trusted runtime component:
    defineHiddenClass -> hidden Lookup
    -> findConstructor/findVirtual/findStatic...
    -> create the required interface or adapted MethodHandle

Client code:
    receives an interface / a MethodHandle with a designed signature
    does not receive a full-privilege Lookup by default
~~~

Even a published MethodHandle is a callable capability: the underlying method may have side effects. Do not publish a handle to a private method if external code is not permitted to perform that operation.

## 3. Producing bytes for practice without external libraries

To focus on `Lookup` and `MethodHandle`, we will compile **one Java file containing two top-level classes**:

~~~text
HiddenMembersDemo.java --javac--> HiddenMembersDemo.class
                                  SecretBlueprint.class
~~~

`SecretBlueprint` is an ordinary template, having:

- A private constructor taking `int`.
- A private field `int code`.
- A private instance method `String describe(String)`.
- A private static method `String label()`.

The program will read the bytes of `SecretBlueprint.class` using `getResourceAsStream` and then use `defineHiddenClass` so the JVM defines **a new hidden class**. This class is distinct from the ordinary `SecretBlueprint.class`, even though it originates from the same classfile bytes.

This approach keeps the example self-contained; in a real system, bytes might come from a **trusted** code generator. Do not read Java source text and pass it directly into `defineHiddenClass`; the API takes **compiled class-file bytes**.

## 4. Complete example 1: accessing private constructor, field, and method

Save the file **HiddenMembersDemo.java**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public class HiddenMembersDemo {
    private static byte[] bytesOf(String resource) throws Exception {
        try (InputStream stream = HiddenMembersDemo.class.getResourceAsStream(resource)) {
            return Objects.requireNonNull(stream, resource).readAllBytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup owner = MethodHandles.lookup();
        byte[] classBytes = bytesOf("SecretBlueprint.class");
        MethodHandles.Lookup hiddenLookup = owner.defineHiddenClass(classBytes, false);
        Class<?> hiddenType = hiddenLookup.lookupClass();

        System.out.println("hidden=" + hiddenType.isHidden());
        System.out.println("nameHasSlash=" + hiddenType.getName().contains("/"));
        System.out.println("differentFromOrdinary=" + (hiddenType != SecretBlueprint.class));
        System.out.println("lookupClassMatches=" + (hiddenLookup.lookupClass() == hiddenType));
        System.out.println("fullPrivilege=" + hiddenLookup.hasFullPrivilegeAccess());
        try {
            Class.forName(hiddenType.getName());
        } catch (ClassNotFoundException ex) {
            System.out.println("classForName=" + ex.getClass().getSimpleName());
        }

        MethodHandle constructor = hiddenLookup.findConstructor(
                hiddenType, MethodType.methodType(void.class, int.class));
        MethodHandle createAsObject = constructor.asType(
                MethodType.methodType(Object.class, int.class));
        Object instance = (Object) createAsObject.invokeExact(41);
        System.out.println("instanceType=" + (instance.getClass() == hiddenType));

        MethodHandle getCode = hiddenLookup.findGetter(
                hiddenType, "code", int.class).asType(
                MethodType.methodType(int.class, Object.class));
        MethodHandle setCode = hiddenLookup.findSetter(
                hiddenType, "code", int.class).asType(
                MethodType.methodType(void.class, Object.class, int.class));
        MethodHandle describe = hiddenLookup.findVirtual(
                hiddenType, "describe",
                MethodType.methodType(String.class, String.class)).asType(
                MethodType.methodType(String.class, Object.class, String.class));
        MethodHandle label = hiddenLookup.findStatic(
                hiddenType, "label", MethodType.methodType(String.class));

        System.out.println("initialCode=" + (int) getCode.invokeExact(instance));
        System.out.println("initialText=" + (String) describe.invokeExact(instance, "!"));
        setCode.invokeExact(instance, 73);
        System.out.println("updatedCode=" + (int) getCode.invokeExact(instance));
        System.out.println("updatedText=" + (String) describe.invokeExact(instance, "?"));
        System.out.println("staticLabel=" + (String) label.invokeExact());

        try {
            owner.findVirtual(hiddenType, "describe",
                    MethodType.methodType(String.class, String.class));
        } catch (IllegalAccessException ex) {
            System.out.println("otherLookupPrivate=" + ex.getClass().getSimpleName());
        }
    }
}

final class SecretBlueprint {
    private int code;

    private SecretBlueprint(int code) {
        this.code = code;
    }

    private String describe(String suffix) {
        return "code=" + code + suffix;
    }

    private static String label() {
        return "hidden-private";
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 HiddenMembersDemo.java
java HiddenMembersDemo
~~~

**Exact stdout**:

~~~text
hidden=true
nameHasSlash=true
differentFromOrdinary=true
lookupClassMatches=true
fullPrivilege=true
classForName=ClassNotFoundException
instanceType=true
initialCode=41
initialText=code=41!
updatedCode=73
updatedText=code=73?
staticLabel=hidden-private
otherLookupPrivate=IllegalAccessException
~~~

### 4.1. The hidden class is genuinely different from the template class

`hiddenType.isHidden()` is true. `hiddenType != SecretBlueprint.class` is also true. Each call to `defineHiddenClass` creates a **new runtime class**, not an alias to an ordinary class with the same bytes. The result `lookupClassMatches=true` proves that the returned Lookup points to the exact Class object of the newly defined hidden class.

`hiddenType.getName().contains("/")` in the test is true because a hidden class has a runtime name with a special suffix. **Do not depend on the exact suffix string or address in the name**; it may vary across JVMs/runs. `Class.forName(hiddenType.getName())` throws `ClassNotFoundException`: that is a key property of hidden classes.

### 4.2. Creating an instance using the private constructor

Template method:

~~~java
// Fragment from SecretBlueprint:
private SecretBlueprint(int code) {
    this.code = code;
}
~~~

We look up the constructor:

~~~java
// Fragment, hiddenLookup/hiddenType already obtained:
MethodHandle constructor = hiddenLookup.findConstructor(
        hiddenType, MethodType.methodType(void.class, int.class));
~~~

**Note the two kinds of MethodType**:

| What is being done | Signature |
| --- | --- |
| `MethodType` passed to `findConstructor` | `(int)void` |
| Returned MethodHandle after finding the constructor | `(int)HiddenType` |
| MethodHandle after `asType(Object,int)` | `(int)Object` |

This is because a constructor in Java is described with return type `void` in the lookup request, whereas **invoking the constructor handle** returns a new instance. Looking up a constructor with return type `HiddenType` directly in the request is a common mistake.

We cannot write a Java type literal like `SecretBlueprint/0x...` in source code. Instead:

~~~java
// Fragment:
MethodHandle createAsObject = constructor.asType(
        MethodType.methodType(Object.class, int.class));
Object instance = (Object) createAsObject.invokeExact(41);
~~~

The object is still an instance of **hiddenType**, not converted into a different Java class. `asType` only adjusts the signature and conversions of the handle. Therefore `instance.getClass() == hiddenType` is true.

### 4.3. Reading/writing a private field using Getter/Setter MethodHandles

Template field:

~~~java
// Fragment:
private int code;
~~~

Two lookups:

~~~java
// Fragment:
MethodHandle getter = hiddenLookup.findGetter(hiddenType, "code", int.class);
MethodHandle setter = hiddenLookup.findSetter(hiddenType, "code", int.class);
~~~

Original handle signatures:

~~~text
getter: (HiddenType)int
setter: (HiddenType,int)void
~~~

In the complete code, we adapt the receiver to `Object`:

~~~java
// Fragment:
MethodHandle getCode = getter.asType(
        MethodType.methodType(int.class, Object.class));
MethodHandle setCode = setter.asType(
        MethodType.methodType(void.class, Object.class, int.class));
~~~

The `invokeExact` call takes a compile-time `Object`, so it matches the signature, while the adapter checks at runtime whether the receiver is actually an instance of the hidden class. `setCode.invokeExact(instance,73)` modifies the private field, and then `getCode` returns 73.

**Do not confuse `findGetter` with `findStaticGetter`.** If the field is static, use the corresponding static API without passing a receiver. If the field is `final`, do not assume Lookup has permission to set it like a mutable field; field access and handle creation rules still apply.

### 4.4. Calling a private instance method using findVirtual

Template method:

~~~java
// Fragment:
private String describe(String suffix) {
    return "code=" + code + suffix;
}
~~~

Find the handle:

~~~java
// Fragment:
MethodHandle raw = hiddenLookup.findVirtual(
        hiddenType, "describe",
        MethodType.methodType(String.class, String.class));
~~~

The `MethodType` passed to `findVirtual` describes the type **of the declared method**, excluding the receiver. The returned handle is what includes the receiver:

~~~text
findVirtual request:  (String)String
MethodHandle result:  (HiddenType,String)String
~~~

We adapt the receiver so source code can invoke it:

~~~java
// Fragment:
MethodHandle adapted = raw.asType(
        MethodType.methodType(String.class, Object.class, String.class));
String result = (String) adapted.invokeExact(instance, "!");
~~~

The result is `code=41!`. After the field changes to 73, `describe(instance,"?")` yields `code=73?`. The handle is not an immutable snapshot of the field; it invokes the code of the actual instance.

### 4.5. Calling a private static method using findStatic

A static method does not need a receiver:

~~~java
// Fragment:
MethodHandle label = hiddenLookup.findStatic(
        hiddenType, "label", MethodType.methodType(String.class));
String text = (String) label.invokeExact(); // "hidden-private"
~~~

When both the return type and parameters can be written in Java source, no adapter is needed just to hide a receiver. The returned Lookup has private access to the hidden class, so finding this method succeeds.

### 4.6. One private method, but two Lookups yield different results

For example, calling:

~~~java
// Fragment, owner is the original Lookup of HiddenMembersDemo:
owner.findVirtual(hiddenType, "describe",
        MethodType.methodType(String.class, String.class));
~~~

receives `IllegalAccessException`. The reason: the first hidden class was defined **without `NESTMATE`**, so the host's Lookup is not permitted to access private members of that class. The returned Lookup succeeds because its lookupClass **is the hidden class itself**.

**Conclusion:** finding a private member is a matter of **Lookup access rights**, not merely holding a `Class<?>` to be able to call any member. Do not use `setAccessible` to paper over a privilege design gap when the returned Lookup already provides the official path.

## 5. asType, invokeExact, and receivers without a source name

### 5.1. MethodHandle still retains the exact runtime type

In the program, the original types of the handles still reference **the actual hiddenType**:

| Handle | Original signature |
| --- | --- |
| Constructor | `(int)HiddenType` |
| Getter `code` | `(HiddenType)int` |
| Setter `code` | `(HiddenType,int)void` |
| Instance method `describe` | `(HiddenType,String)String` |
| Static method `label` | `()String` |

`HiddenType` is an illustrative notation, not a class name that can be typed into Java source. The actual MethodHandle signature contains the runtime `Class<?>` of the hidden class in `MethodType`.

If the source only has `Object instance`, calling `raw.invokeExact(instance,"!")` directly with static signature `(Object,String)String` will **not match** the original handle `(HiddenType,String)String`. `invokeExact` requires matching the call-site signature, including the return type.

### 5.2. An adapter is a type bridge, not a privilege bypass

`MethodHandle.asType` can create a new handle accepting `Object`, and then **cast the reference at runtime** to the hidden class when invoked. Thus:

~~~java
// Fragment:
MethodHandle adapted = raw.asType(
        MethodType.methodType(String.class, Object.class, String.class));
String answer = (String) adapted.invokeExact((Object) instance, "!");
~~~

The snippet above works when `instance` is genuinely an instance of the hidden class. If you pass a `new Object()` or an instance of **another hidden class created from the same bytes**, the adapter may throw `ClassCastException`. `asType` does not turn an object into an instance of another class and does not change the access rights of the raw handle.

### 5.3. So can invokeWithArguments be used?

Yes, when you cannot determine the signature to call at compile time:

~~~java
// Fragment: raw is an instance method handle of the hidden class.
Object created = constructor.invokeWithArguments(41);
Object result = raw.invokeWithArguments(created, "!");
~~~

`invokeWithArguments` accepts multiple `Object` arguments and performs the necessary conversions/runtime adaptation; it may introduce boxing and overhead on a frequent call path. For code generation or a "hot path" dispatcher, you should **create and cache the adapter once** and try `invokeExact` with a clear signature, measuring with a real benchmark (e.g., JMH) rather than asserting it is always faster.

### 5.4. Signature errors to recognize

- `WrongMethodTypeException`: the call-site descriptor does not match `MethodHandle.type()` or cannot be adapted according to the requested conversion. Even the return type must match.
- `ClassCastException`: the reference cast to the hidden class is incompatible in the adapter/call path.
- `NullPointerException`: may occur when calling an instance method on a null receiver or when target code itself throws the error.
- `NoSuchMethodException`: `findConstructor`/`findVirtual`/`findStatic` cannot find the requested signature.
- `IllegalAccessException`: the Lookup being used does not have the appropriate member access rights.
- Exceptions thrown by the hidden method's code: different from lookup errors. Do not catch everything as "class not found".

A short debug sequence:

~~~text
1. Check hiddenLookup.lookupClass().isHidden().
2. Print hiddenType + method parameter/return types (do not hardcode the runtime name).
3. Check the actual member and the requested signature.
4. Print rawHandle.type() before invoking.
5. Print adaptedHandle.type() after asType.
6. Compare the signature at the invokeExact site (including return type).
7. Verify the receiver was created by that exact generation of the hidden class.
8. Distinguish findXxx errors from errors running bytecode in the target.
~~~

## 6. NESTMATE: two different directions of private access

The easiest mistake is to treat the returned Lookup and `ClassOption.NESTMATE` as doing the same thing. In reality, they handle **two different boundaries**.

| Relationship | Mechanism | Example |
| --- | --- | --- |
| Host code looks up private member **of the hidden class** | Returned Lookup has private access to the new class | `hiddenLookup.findVirtual(hiddenType, "describe", ...)` |
| Bytecode **of the hidden class** wants to access private member **of the host class** | Requires a valid nest/access relationship; `ClassOption.NESTMATE` may be used | Hidden method reads host's `private static String token` |
| Less-trusted client wants to call a specific member | Publish only the chosen MethodHandle/interface | Do not distribute the returned Lookup indiscriminately |

`ClassOption.NESTMATE` places the new hidden class into **the nest of the lookup class** according to API rules. Then Java private access within the same nest can work appropriately. Without this option, being in the same package is usually **not enough** for private fields/methods of the host.

Nor should `NESTMATE` be understood as "allowed to access any package/module". `defineHiddenClass` still requires a sufficiently privileged Lookup, valid bytes, matching package, and related conditions.

## 7. Complete example 2: NESTMATE and initialization

The program below creates a hidden class from the bytecode of a nested class `HiddenNestDemo.Template`. The private method `readOwnerToken()` inside it accesses the private field `HiddenNestDemo.token`. We intentionally declare the field **non-final** so the read is not constant-folded by javac.

Save the file **HiddenNestDemo.java**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public class HiddenNestDemo {
    private static String token = "nest-secret";
    private static int initEvents;

    public static void recordInit() {
        initEvents++;
    }

    private static byte[] templateBytes() throws Exception {
        try (InputStream stream = HiddenNestDemo.class.getResourceAsStream(
                "HiddenNestDemo$Template.class")) {
            return Objects.requireNonNull(stream).readAllBytes();
        }
    }

    static final class Template {
        static {
            HiddenNestDemo.recordInit();
        }

        private static String readOwnerToken() {
            return token;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup hostLookup = MethodHandles.lookup();
        byte[] bytes = templateBytes();

        MethodHandles.Lookup deferred = hostLookup.defineHiddenClass(
                bytes, false, MethodHandles.Lookup.ClassOption.NESTMATE);
        Class<?> hiddenClass = deferred.lookupClass();
        System.out.println("isHidden=" + hiddenClass.isHidden());
        System.out.println("nestmate=" + hiddenClass.isNestmateOf(HiddenNestDemo.class));
        System.out.println("initBefore=" + initEvents);
        deferred.ensureInitialized(hiddenClass);
        System.out.println("initAfterEnsure=" + initEvents);

        MethodHandle read = deferred.findStatic(hiddenClass, "readOwnerToken",
                MethodType.methodType(String.class));
        System.out.println("ownerPrivate=" + (String) read.invokeExact());

        MethodHandles.Lookup immediate = hostLookup.defineHiddenClass(
                bytes, true, MethodHandles.Lookup.ClassOption.NESTMATE);
        System.out.println("distinctHiddenClass="
                + (immediate.lookupClass() != hiddenClass));
        System.out.println("initAfterImmediate=" + initEvents);

        MethodHandles.Lookup noNest = hostLookup.defineHiddenClass(bytes, false);
        System.out.println("noNestmate="
                + !noNest.lookupClass().isNestmateOf(HiddenNestDemo.class));
        try {
            MethodHandle readNoNest = noNest.findStatic(
                    noNest.lookupClass(), "readOwnerToken",
                    MethodType.methodType(String.class));
            System.out.println((String) readNoNest.invokeExact());
        } catch (IllegalAccessError ex) {
            System.out.println("accessWithoutNest=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 -encoding UTF-8 HiddenNestDemo.java
java HiddenNestDemo
~~~

**Exact stdout**:

~~~text
isHidden=true
nestmate=true
initBefore=0
initAfterEnsure=1
ownerPrivate=nest-secret
distinctHiddenClass=true
initAfterImmediate=2
noNestmate=true
accessWithoutNest=IllegalAccessError
~~~

### 7.1. Why does the NESTMATE version work?

The hidden class defined with `ClassOption.NESTMATE` is in the same nest as `HiddenNestDemo`; `isNestmateOf` returns true. The returned Lookup can access the private method **belonging to the hidden class**. When this method runs and reads `token` (a private field of the host), the appropriate nest relationship allows the read to succeed, returning `nest-secret`.

Do not think `readOwnerToken` and `token` are in the same class. They belong to **two different classes** but can access private members thanks to the nest membership created by the option. If a runtime generator design needs to access host private members for optimization, it must be clearly justified why that privilege is appropriate for trusted code.

### 7.2. Why does the version without NESTMATE fail?

The end of the code defines a third hidden class:

~~~java
// Fragment:
MethodHandles.Lookup noNest = hostLookup.defineHiddenClass(bytes, false);
~~~

With this returned Lookup, `findStatic(hiddenClass, "readOwnerToken",...)` **can still succeed**, because the method being looked up is a private member of **the hidden class itself**. However, when invoking the method, the method's bytecode attempts to access `private static String token` in the host, at which point nest permission is missing and **`IllegalAccessError`** is thrown.

This is a very useful distinction:

- `IllegalAccessException` typically occurs when **Lookup finds a member** and permissions are insufficient.
- `IllegalAccessError` in the example occurs when **bytecode executes an illegal member access**.

The experiment catches `IllegalAccessError` to illustrate accurately; normal business code should not swallow linkage/access errors and try to continue as if nothing happened.

### 7.3. Why can't token be a compile-time constant in the experiment?

If declared as:

~~~java
// Fragment NOT suitable when wanting to measure getstatic permission:
private static final String TOKEN = "nest-secret";
~~~

then `TOKEN` is a **compile-time constant**. Javac may replace the field access with a literal in the template's method. The result "without NESTMATE it still prints nest-secret" may simply reflect **there was no getstatic operation to the private field at all**. That is not evidence that access controls were bypassed.

The example uses a non-final `private static String token`, so the bytecode genuinely needs to access the host's member. When verifying cross-class permissions, use a field that is not constant-folded or inspect `javap -c` output to confirm the actual access instruction.

## 8. initialize=false, ensureInitialized, initialize=true

Class definition and class initialization are **two phases**.

In example 2, `Template` has a static initializer calling `HiddenNestDemo.recordInit()`:

~~~java
// Fragment from Template:
static {
    HiddenNestDemo.recordInit();
}
~~~

The program creates the first hidden class with `initialize=false`:

~~~java
// Fragment:
MethodHandles.Lookup deferred =
        hostLookup.defineHiddenClass(bytes, false,
                MethodHandles.Lookup.ClassOption.NESTMATE);
~~~

Right after defining, `initEvents=0`. Then:

~~~java
// Fragment:
deferred.ensureInitialized(deferred.lookupClass());
~~~

forces initialization of that hidden class; the static initializer runs once, `initEvents=1`.

Next, the code calls `defineHiddenClass(bytes,true,NESTMATE)` a second time. Because that is **a new class**, the second class's static initializer runs separately right during definition, making `initEvents=2`.

**Do not interpret `initialize=false` as "never initialize".** Subsequent active use such as calling a static method, creating an instance, or `ensureInitialized` can trigger class initialization according to JVM rules. Nor should reading the `Template.class` file via `getResourceAsStream` be confused with initializing the ordinary template class.

### 8.1. Why is the static state of two hidden classes independent?

When calling with the same bytes multiple times:

~~~text
defineHiddenClass(bytes, false, NESTMATE) -> HiddenA
defineHiddenClass(bytes, true,  NESTMATE) -> HiddenB

HiddenA != HiddenB

Each class has its own class initialization and static storage.
~~~

These separate `Class<?>` objects are not aliases, despite sharing the same logical template. In the example, both static initializers call **a host method** that increments a shared counter, which is why we observe two initializations.

If you need a singleton logical implementation, you must design your own cache/canonicalization; `defineHiddenClass` does not automatically merge identical bytes into a single class.

## 9. Hidden class identity and MethodHandle identity

A major concern when doing runtime class generation is **never mixing instances/handles across class generations**.

Suppose:

~~~java
// Fragment: defining and bytes have been prepared.
MethodHandles.Lookup a = defining.defineHiddenClass(bytes, false);
MethodHandles.Lookup b = defining.defineHiddenClass(bytes, false);
boolean same = a.lookupClass() == b.lookupClass(); // false
~~~

Same classfile bytes, but **different runtime identities**:

- The constructor handle of HiddenA creates an instance of HiddenA.
- The instance method handle of HiddenA expects a HiddenA receiver.
- An instance of HiddenB is not automatically an instance of HiddenA.
- An adapter using an `Object` receiver still casts to the **exact** hidden type embedded in the original handle.
- `Class.isInstance` and `Class.cast` only work if the object has the right runtime type relationship.

Therefore, you should cache the `Class<?>`, MethodHandles, and corresponding metadata together **in the same entry**. Do not take a raw handle from one version and apply it to an instance of another version just because they share the same original classfile name.

### 9.1. Do not store the runtime name as a durable key

`Class.getName()` of a hidden class usually has a JVM-generated suffix, for example containing `/0x...`. This is not a stable identifier. Do not serialize the name for a later `Class.forName`, do not parse the suffix yourself, and do not expose that name as a contract to users.

If a runtime registry is needed, use an **application-defined logical key**:

~~~text
Plugin ID + implementation version
         |
         v
Cache entry
  - returned Lookup (if further lookup is still needed)
  - Class<?> hiddenType
  - constructor MethodHandle
  - private business MethodHandles
  - lifecycle / validation metadata
~~~

Use the logical key to look up the entry, not the generated runtime name. When the code version changes, create a new entry and switch routing in a controlled manner.

### 9.2. STRONG and the unloading issue

`ClassOption.STRONG` affects the lifetime of a hidden class:

| Mode | General characteristics |
| --- | --- |
| Without `STRONG` | A hidden class can typically be unloaded independently of its defining class loader when no suitable reachable references remain |
| With `STRONG` | Lifetime is more strongly tied to the defining class loader; do not expect independent unloading like a weak hidden class |

There is no guarantee that GC will unload immediately after a local variable goes out of scope. A live `Lookup`, `MethodHandle`, `Class<?>`, `MethodType`, instance, or cache can keep the related objects alive. A static cache holding thousands of entries will increase pressure on metadata/metaspace even without `STRONG`.

**Right decision:** choose lifecycle/caching according to runtime requirements, and check actual memory usage. Do not use `STRONG` just to be "safer" if there is no specific lifetime requirement.

## 10. Package, module, privileges, and bytecode trustworthiness

### 10.1. Correct package does not mean access to every private member

`defineHiddenClass` requires the bytecode to belong to the appropriate package of the lookup class; this does not open all private members in the same package. Java private still requires private access to the class itself or a valid nest/access relationship.

- The returned Lookup is created to access the new hidden class.
- `NESTMATE` can allow hidden class bytecode to participate in the host's nest.
- Without `NESTMATE`, hidden code can still read public/package-private members according to access rules, but does not by default read host private members.
- Module boundaries are not bypassed just because a class is hidden.

### 10.2. Do not use publicLookup() as a bypass tool

`MethodHandles.publicLookup()` has public access scope; it does not provide the full privilege needed to define a hidden class. Even `privateLookupIn` has module openness and caller privilege conditions; it is not a master key.

Determine which code component owns the class bytes, which package is allowed to generate runtime code, and which Lookup has the appropriate privileges. Avoid passing high-privilege Lookups through abstraction layers that only need a specific MethodHandle.

### 10.3. When bytecode is invalid

Main error categories:

| Phase | Possible error types | What to check |
| --- | --- | --- |
| Read resource | `NullPointerException` from requireNonNull | Was the `.class` file built/packaged properly? |
| Define | `IllegalAccessException` | Full privilege Lookup, module/context |
| Define | `IllegalArgumentException` | Mismatched bytes package name or input/options violating API conditions |
| Verify/link | `ClassFormatError`, `VerifyError`, `LinkageError` or related errors | Classfile bytes, target version, constant pool, dependencies |
| Find member | `NoSuchMethodException` / `NoSuchFieldException` | Name, return/parameter types, static vs instance |
| Find member | `IllegalAccessException` | Lookup access rights |
| Invoke | `WrongMethodTypeException` / `ClassCastException` | Descriptor, adapter, receiver runtime identity |
| Invoke hidden code | `IllegalAccessError` | Target bytecode itself accessing a member outside its privileges |
| Initialize | Error from static initializer | Side effects, dependencies, exceptions during init |

Do not lump every error into "class not found". Separate **resource**, **define**, **lookup**, **invoke**, and **business exceptions** so diagnosis and handling are meaningful.

### 10.4. Is creating a hidden class from user input safe?

**Not by default.** Hidden classes do not provide a sandbox. If bytecode is untrusted, it can execute operations permitted by the runtime context and cause external effects. A system running arbitrary plugins needs higher-level protections: verification policies, isolation, execution permissions, and resource management. Hiding the class name is not enough to replace those mechanisms.

## 11. Caching, concurrency, and performance

### 11.1. Defining a class is not a cheap per-request operation

`defineHiddenClass` creates a new class identity. If every request re-defines from the same bytes, the framework may waste class metadata, JIT warmup, and lifecycle management effort. A typically reasonable path:

~~~text
1. Determine the logical implementation key.
2. Look up an existing and still valid cache entry.
3. If missing, obtain trusted classfile bytes.
4. defineHiddenClass once for the key/version.
5. Obtain returned Lookup + Class<?>.
6. find private members and asType adapters once.
7. Cache the entry with appropriate privileges/lifecycle.
8. Subsequent requests invoke the cached MethodHandle.
9. Evict when no longer used, avoiding holding references indefinitely.
~~~

If multiple threads want to define the key simultaneously, a mechanism to avoid races is needed: if the same bytes are defined in parallel, the JVM still creates different class identities. The cache must manage initialization/failures according to actual needs, rather than just calling `computeIfAbsent` and ignoring initialization errors.

### 11.2. Getter/Setter MethodHandles do not make a field volatile

In example 1, `code` is an ordinary mutable `int`. Using `findGetter/findSetter` does not automatically provide thread-safety or stronger Java Memory Model guarantees than the corresponding field operation. When sharing a hidden instance across threads, you must use synchronization, appropriate volatile/VarHandle, or an immutable data design.

Similarly, `initialize=true` controls when class initialization happens, not turning all internal object state thread-safe.

### 11.3. Do not claim performance without measuring

A cached and adapted MethodHandle can help avoid repeated Reflection overhead in many cases, but the cost still depends on signature, dispatch, JIT, dynamic types, adapter chains, boxing, and runtime. To know whether an approach is beneficial:

- Avoid measuring `defineHiddenClass` inside a loop if the application defines once.
- Measure define/lookup time and invoke time separately.
- Use JMH with warmup, representative data, and avoid dead-code elimination.
- Compare with the same semantics against reflection and interface calls, rather than just comparing a microbenchmark with no side effects.
- Look at memory/metaspace and lifecycle, not just throughput.

## 12. Implementation checklist

Before putting runtime hidden classes code into production:

1. **Byte source**: generated/read from a trusted source, compatible classfile version, valid package.
2. **Input Lookup**: right class, module, and full privilege, not arbitrarily grabbing `publicLookup`.
3. **Returned Lookup**: kept secure, use `lookupClass()`; do not guess the runtime name.
4. **Member API**: constructors use `MethodType` returning `void`; `findVirtual` uses a signature without the receiver in the request; static differs from instance.
5. **Private member access**: use the returned Lookup, publish only the necessary capabilities.
6. **NESTMATE**: enable only when hidden code has a legitimate need for host private members, not as a mindless default step.
7. **Adapter**: check `raw.type()` and `adapted.type()`; actual receiver matches the hidden runtime class.
8. **Initialization**: understand `initialize`, actively test static initializers and init errors.
9. **Identity**: each define creates a new runtime type, do not mix handles/instances from different versions.
10. **Lifetime**: choose `STRONG` with justification and bound the cache.
11. **Concurrency**: define/cache once per key, handle races, synchronize mutable state.
12. **Observability**: log the logical implementation key/version and errors by phase, do not use the runtime hidden name as a durable ID.

## 13. Self-check questions

**1.** What type does `defineHiddenClass` return?

**Answer:** `MethodHandles.Lookup`, not `Class<?>` directly. Retrieve the Class object via `returnedLookup.lookupClass()`.

**2.** Can we call `Class.forName(hiddenType.getName())` to look up a hidden class again?

**Answer:** No. Hidden classes are not looked up by name via normal class lookup mechanisms. You must retain the Class object/Lookup/handles already obtained.

**3.** To call a private constructor taking `int`, what return type does the signature passed to `findConstructor` have?

**Answer:** `void`. The lookup request is `MethodType.methodType(void.class,int.class)`; the returned constructor MethodHandle is what returns an instance of the hidden class.

**4.** To find `private String describe(String)`, does the MethodType of `findVirtual` need to include the receiver?

**Answer:** No. The request uses `(String)String`; the handle after lookup carries `(HiddenType,String)String`.

**5.** Why does `asType(Object,... )` work without breaking private access?

**Answer:** Private access was already checked when using the returned Lookup to find the member; `asType` creates an adapter that converts the reference and checks the runtime cast, without adding privileges on its own.

**6.** Do two hidden classes defined from the same bytes have the same identity?

**Answer:** No. Each `defineHiddenClass` creates a separate runtime class. An instance of class A is not automatically compatible with a handle expecting a receiver of class B.

**7.** The returned Lookup lets you call a private method of the hidden class. Can that method's bytecode automatically access host private members?

**Answer:** Not by default. Accessing host private members requires a valid privilege/nest relation, typically choosing `ClassOption.NESTMATE` when appropriate for the purpose.

**8.** Why did the noNest version succeed with `findStatic` yet throw `IllegalAccessError` when invoked?

**Answer:** The Lookup has privileges for **the private method of the hidden class itself**; the error occurred when bytecode inside the method tried to read **a private field of the host** without nest access.

**9.** Why not use `private static final String TOKEN = "x"` to verify private field permission in the demo?

**Answer:** This constant can be inlined by javac; not throwing an error could be because **there is no getstatic instruction accessing the field**.

**10.** Does `initialize=false` mean the class is never initialized?

**Answer:** No. It only does not request initialization immediately at define time; `ensureInitialized` or active use will cause the class to initialize according to JVM rules.

**11.** What does `STRONG` do?

**Answer:** Ties the hidden class's lifetime more strongly to the defining class loader. Without `STRONG`, a weak hidden class can be unloaded independently when no suitable references remain; there is no guarantee of immediate unloading.

**12.** Can a hidden class be used as a sandbox for untrusted bytecode?

**Answer:** No. Hidden only affects the class definition/lookup mechanism and relates to lifetime/access; it does not automatically prevent I/O or malicious code execution.

## Summary

- `defineHiddenClass` returns a **Lookup pointing to the new hidden class**. Keep the Lookup or the necessary Class/MethodHandles, do not rely on the runtime name.
- Use the returned Lookup to invoke **private constructors, methods, and fields** of the hidden class: `findConstructor`, `findVirtual`, `findStatic`, `findGetter`, `findSetter`.
- Constructor lookup uses **return type void**; instance method lookup **does not** include the receiver in the requested MethodType, whereas the MethodHandle takes the receiver.
- `asType` helps represent the receiver/return type as `Object` or a known interface; `invokeExact` requires an exact signature at the call site.
- **Private access of the returned Lookup** differs from **NESTMATE** for hidden bytecode accessing host private members.
- `initialize` controls initialization; `STRONG` affects lifetime; each define creates **a new runtime class identity**.
- Cache the right Class/handles by version, control the Lookup as a capability, and test **actually invoking the members**, not just checking that `findXxx` succeeds.

## References

- Java SE 17, **MethodHandles.Lookup** — defineHiddenClass, lookupClass, findConstructor/findVirtual/findStatic/findGetter/findSetter, ensureInitialized: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html
- Java SE 17, **Lookup.ClassOption** — NESTMATE and STRONG: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html
- Java SE 17, **MethodHandle** — asType, invokeExact, invokeWithArguments: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html
- Java SE 17, **Class** — isHidden, isNestmateOf, getName: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- OpenJDK, **JEP 371 – Hidden Classes**: https://openjdk.org/jeps/371
- Java Virtual Machine Specification SE 17, **Class Loading, Linking, Initialization and Access Control**: https://docs.oracle.com/javase/specs/jvms/se17/html/index.html
