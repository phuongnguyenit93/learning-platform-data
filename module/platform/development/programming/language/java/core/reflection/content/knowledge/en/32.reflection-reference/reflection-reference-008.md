# Looking Up Javadoc and Language Rules by Java Reflection Operation

## 1. Why Look Up by *Specific Operation*?

Reflection is not a single API with one simple rule set. In Java 17+, **finding a class**, **listing members**, **finding a method signature**, **checking access permissions**, **invoking a method**, **reading generics/annotations**, or **creating a dynamic proxy** each have their own rules and error types. When results contradict intuition, identify the exact operation being performed, then read the corresponding documentation.

Reference sources have distinct roles:

- **API Javadoc (Java SE 17):** the contract of a specific API such as `Class.getDeclaredMethod`, `Method.invoke`, or `AccessibleObject.trySetAccessible`: parameters, return values, conditions, exceptions, and differences from similarly named APIs.
- **Java Language Specification (JLS):** rules of *the Java language*: member access, method overloading/overriding, invocation conversions, generics/type erasure, annotations, and class initialization.
- **Java Virtual Machine Specification (JVMS):** definitions of *runtime/bytecode*: class loading, linking, initialization, resolution, field/method descriptors, generic `Signature` attributes, and JVM-level dispatch.
- **Minimal Java test code on the target JDK:** confirms a reproducible hypothesis. Experimental results verify that specific case, **and do not replace the official contract**.

A classic case: `getMethod("process", Integer.class)` throws `NoSuchMethodException` even though the class declares `process(int)`. Intuition about **autoboxing in normal Java calls** cannot substitute for the Javadoc of **reflection lookup**. Similarly, calling `Method.invoke` on a found `Method` has its own argument conversion rules.

## 2. Official Links Worth Bookmarking

All links below point to **Java SE / JDK 17** documentation so you read against the same version baseline when checking the article's examples.

| Need | Official Documentation | Sections to Read |
| --- | --- | --- |
| Discover classes, fields, methods, constructors | [`java.lang.Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html) | `forName`, `getMethod`, `getDeclaredMethod`, `getMethods`, `getDeclaredMethods`, `getField`, `getDeclaredField` |
| Get/set fields | [`java.lang.reflect.Field`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html) | `get`, `set`, `getType`, `getGenericType` |
| Invoke methods/read signatures | [`java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html) | `invoke`, `getReturnType`, `getGenericReturnType`, `getParameterTypes` |
| Invoke constructors | [`java.lang.reflect.Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html) | `newInstance` and exceptions when a constructor throws |
| Control reflection access | [`AccessibleObject`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html) | `canAccess`, `trySetAccessible`, `setAccessible` |
| Generic metadata | [`java.lang.reflect.Type`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Type.html) | `ParameterizedType`, `TypeVariable`, `WildcardType` |
| Runtime annotations | [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html) | `getAnnotation`, `getDeclaredAnnotation`, `getAnnotationsByType` |
| Create dynamic proxies | [`Proxy`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Proxy.html) and [`InvocationHandler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationHandler.html) | `newProxyInstance`, `invoke`, `Object` methods |
| Check overload/override | [JLS `15.12` — Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12) and [JLS `8.4` — Method Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4) | Steps for selecting a method when writing Java code, overriding, signature |
| Language access scope | [JLS `6.6` — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6) | `public`, `protected`, package-private, `private` |
| Type erasure | [JLS `4.6` — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6) | Erasure of `T`, `List<String>`, bounds |
| Class loading/linking/init | [JVMS Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html) | `5.3` loading, `5.4` linking, `5.5` initialization |
| Generic `Signature` in class files | [JVMS `4.7.9` — The Signature Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.9) | Bytecode descriptors vs. generic metadata |

When using a different JDK version, switch **Javadoc, JLS/JVMS, and the runtime JDK together** to that same version if newer behavior matters. Do not pick the latest docs arbitrarily while running an older program without checking `@since`, `@Deprecated`, module restrictions, or API changes.

## 3. How to Read a Javadoc Page in Order

For the API you are looking up, follow this sequence of questions:

1. **Right kind/operation?** For example, `Class.getMethod` versus `Class.getDeclaredMethod`, `Method.invoke` versus `Constructor.newInstance`.
2. **Right version and signature?** Check the full declaration form, generic parameters, varargs, static/instance, and overloads of the JDK API itself.
3. **What do the inputs mean?** For `getMethod`, the `Class<?>... parameterTypes` array represents **declared parameter types**; for `Method.invoke`, `args` are **values passed at invocation time**.
4. **What is the result scope?** `public` or declared, inherited or not; `getDeclaredMethods()` can include synthetic/bridge methods; `getDeclaredFields()` does not return inherited fields.
5. **Are access permissions checked?** Finding metadata does not mean permission to call a private method or read a private field; `trySetAccessible` is subject to module constraints.
6. **What are the failure paths?** `NoSuchMethodException` differs from `IllegalAccessException`, `IllegalArgumentException`, and `InvocationTargetException`. Under `Throws`, read the exact conditions *for that operation*.
7. **Does the Javadoc link to the JLS/JVMS?** Open the corresponding spec section when your question concerns the compiler/JVM rather than the library contract.

Read the **Method Detail** (descriptions and conditions), not just the name in the Method Summary; `Since`, `See Also`, `Throws` notes, and special behavior warnings are usually in the detail section.

## 4. Lookup Table: Which Document to Open First for Which Situation?

| Operation You Are Performing | Priority API | Question to Verify | Common Misconception |
| --- | --- | --- | --- |
| Know name `"pkg.Foo"`, want `Class<?>` | `Class.forName`/`ClassLoader.loadClass` | Which loader? Is initialization required? | Assuming every loader searches the same scope; thinking `Class.forName("int")` returns `int.class` |
| Have an object, ask runtime class | `obj.getClass()`, `Class.isInstance` | Which class is the runtime type? | Expecting `List<String>` to exist as a distinct runtime class |
| List public methods | `Class.getMethods()` | Are inherited public methods included? | Thinking it includes only directly declared methods |
| List directly declared methods | `Class.getDeclaredMethods()` | Are there private/bridge/synthetic methods? | Expecting return order to match source order and automatically include inherited methods |
| Find an exact method | `getMethod`/`getDeclaredMethod` | What are the name + **exact parameter type** list? | Expecting reflection to pick an overload or auto-box types passed to `getMethod` |
| Find a field or constructor | `getDeclaredField`, `getDeclaredConstructor` | Direct or public field/constructor; exact parameter types? | Using `getMethods` to find constructors; believing constructors are inherited |
| Read a private field | `Field.get`, `canAccess`, `trySetAccessible` | Does the caller have access and is the package opened by its module? | Assuming `getDeclaredField` means permission to read |
| Invoke a method via reflection | `Method.invoke` | Receiver, actual args, boxing/widening, target exceptions? | Thinking `invoke` re-runs overload resolution from scratch |
| Read annotations at runtime | `AnnotatedElement`/`Retention` | Does the annotation have `RUNTIME`, and is it direct/inherited? | Expecting `RetentionPolicy.CLASS` to appear via `getAnnotation` |
| Read `List<String>` in a signature | `getGeneric...`, `Type`, classfile `Signature` | Is generic metadata stored in the classfile? | Thinking every instance retains its own type arguments |
| Generate an interface proxy | `Proxy`, `InvocationHandler` | How does the handler process methods and `equals`/`hashCode`/`toString`? | Thinking a proxy automatically delegates/handles equality to a target |
| Missing class or static init failure | `Class.forName`, JVMS Ch. 5 | Lookup failure or class linkage/initialization failure? | Equating `ClassNotFoundException` with `NoClassDefFoundError` |

**Scope of `Class<?>`:** Having `SomeClass.class` is enough to introspect that type itself; it does not allow automatically listing every class in a package. Classpath scanning is a separate class/resource-source problem, not `Class.getDeclaredClasses()`.

## 5. Sample Problem: "`getMethod` Fails Even Though Direct Calling Works"

Consider a class with two overloads:

```java
// Illustration inside a class body, not a standalone runnable program.
public String choose(int n) { return "primitive"; }
public String choose(Integer n) { return "wrapper"; }
```

Once you know the exact question, the lookup path is:

1. Open the Javadoc for `Class.getMethod(String, Class<?>...)` and `getDeclaredMethod`.
2. Read that the trailing parameters represent **the parameter types of the method to find**; pick `int.class` for `choose(int)` and `Integer.class` for `choose(Integer)`.
3. To understand how the compiler picks source calls `choose(1)` and `choose(Integer.valueOf(1))`, open **JLS `15.12.2`**; that is **language overload resolution**, not an overload resolver provided by `getMethod`.
4. After finding `Method chooseInt` and calling `chooseInt.invoke(receiver, Integer.valueOf(1))`, open the **`Method.invoke`** Javadoc to see unboxing/primitive widening for actual arguments.
5. If `getMethod("choose", Long.class)` fails despite an overload `choose(Number)`, that matches signature lookup: `Long.class` is not `Number.class`.

**Distinguish the two stages:** during *lookup*, `Class<?>` must match the declared parameter type; during *invoke*, the actual argument object is checked and can be converted under reflection rules, without choosing a different method.

JLS `15.12` also defines strict/loose/varargs and most-specific phases for method invocation expressions in source code. Do not project those phases onto the semantics of `getMethod`.

## 6. Sample Problem: "`getDeclaredMethod` Finds the Method, but `invoke` Errors"

Suppose a `private` method is found:

```java
// Illustration, not standalone.
Method m = SomeType.class.getDeclaredMethod("secret");
Object result = m.invoke(instance);
```

`getDeclaredMethod` returns metadata of a directly declared method regardless of public/private when the signature matches. Yet `m.invoke` still checks access permissions. Read **`AccessibleObject`**:

- `m.canAccess(instance)` checks the caller's current permission on the reflected member, with an appropriate receiver.
- `m.trySetAccessible()` returns `true` when access check suppression can be enabled under JDK conditions; it does not promise success across every module/package.
- `m.setAccessible(true)` can fail with `InaccessibleObjectException` if the module does not allow opening access.
- `IllegalAccessException` from `Method.invoke` usually indicates the caller lacks permission; unlike `InvocationTargetException`, which wraps **exceptions thrown by the target method itself**.

To learn why Java source code can or cannot access a member, consult JLS `6.6`. To learn when reflective access can be suppressed, read the `AccessibleObject` Javadoc and the `exports`/`opens` requirements of the Java Platform Module System. **Reading metadata is not proof of permission to access the member.**

Fields behave similarly: `getDeclaredField` can retrieve a `Field` for a private field, yet `Field.get(instance)` still checks access. In production tools, prefer public APIs/clear module contracts, and only open private access across authorized boundaries.

## 7. Sample Problem: Generic Erasure and Classfile Metadata

When a method is declared `List<String> find()`:

- `getReturnType()` returns `List.class` because the erased/runtime return type is `List`.
- `getGenericReturnType()` can return a `ParameterizedType` representing `java.util.List<java.lang.String>` if the classfile retains valid `Signature` metadata.
- The fact that a method describes `List<String>` does not mean individual list objects carry full generic type arguments at runtime.

Read **JLS `4.6`** to understand erasure; read **JVMS `4.7.9`** to understand classfile `Signature`; read the `Method.getGenericReturnType` Javadoc to see the APIs representing metadata as `Type` and the exceptions that can occur when signatures are malformed or missing types.

For a parameter declared `List<String>`, calling `getMethod("accept", ...)` requires passing `List.class`, **not `ArrayList.class`**, even though passing an `ArrayList<String>` instance to `Method.invoke` can be valid.

Do not confuse a type description string `"java.util.List<java.lang.String>"` with a class name passable to `Class.forName`. Java does not generate a separate runtime `List<String>` class per type argument.

## 8. Sample Problem: Annotation Exists in Source, Not Visible via Reflection

Annotations meant to be read at runtime must consider **`@Retention`**:

- `RetentionPolicy.SOURCE`: for source processing only; not kept as a runtime annotation in the classfile.
- `RetentionPolicy.CLASS`: can exist in the classfile, but is not visible through standard runtime reflection APIs.
- `RetentionPolicy.RUNTIME`: the annotation is retained so reflection APIs like `getAnnotation`/`isAnnotationPresent` can read it.

`@Target` only specifies which element kinds an annotation applies to (field/method/class...), **and does not automatically enforce a validation rule**. `@Inherited` has specific semantics for annotations on classes; it does not make superclass fields/methods automatically become directly declared fields/methods of a subclass.

So when `field.getAnnotation(MyAnnotation.class)` returns `null`, first check whether the annotation definition has `@Retention(RUNTIME)`, whether the field was obtained from **the right class and right loader**, and whether the annotation is attached directly on the queried element. Only after that should you investigate classfile transformation, build versions, or same-named annotation packages in another loader.

Sources: **`AnnotatedElement`**, `Retention` Javadocs, and annotation rules in JLS `9.6`.

## 9. Sample Problem: Class Loading/Initialization and Introspection Errors

`Class.forName("pkg.Plugin")` does not merely ask to find a binary name: the one-argument form also requires the class to be initialized upon success. If you only want to obtain `Class<?>` without requiring initialization yet, the three-argument form `Class.forName(name, false, loader)` is an option, though it still does not guarantee zero loading/linking errors.

Distinguish:

- **`ClassNotFoundException`:** a class-name lookup API (like `Class.forName`) could not find the class via the requested loader.
- **`NoClassDefFoundError`:** the JVM could not obtain a usable class definition while resolving/linking a dependency, or the class is in an erroneous state after failed initialization; sometimes the cause contains `ClassNotFoundException`.
- **`ExceptionInInitializerError`:** static initialization threw a normal exception during initialization; subsequent use of the failed class can lead to `NoClassDefFoundError`.
- **`InaccessibleObjectException` or `IllegalAccessException`:** reflective access permission issue, not proof that the class does not exist.
- **`NoSuchMethodException`:** method signature not found; completely different from a class loader failing to find a class.

When a stack trace has multiple `Caused by` layers, do not stop at the outer error layer. Use the operation being called and **the root cause** to open the exact Javadoc and cross-check **JVMS Ch. 5** on loading/linking/initialization. Successfully obtaining a `Class<?>` does not guarantee dependent types in method signatures will always resolve during deep introspection.

## 10. Runnable Java 17+ Example: Looking Up and Comparing Each Operation

The program below uses the APIs mentioned and prints deterministic output. It does not scan the classpath and requires no external libraries.

Create `JavadocLookupDemo.java` in an empty directory, without a `package` declaration:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.List;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Action {}

class LibraryBase {
    public String inherited() {
        return "base";
    }
}

class LibrarySample extends LibraryBase {
    private final String secret;

    public LibrarySample(String secret) {
        this.secret = secret;
    }

    public String choose(int value) {
        return "primitive:" + value;
    }

    public String choose(Integer value) {
        return "wrapper:" + value;
    }

    @Action
    public List<String> labels() {
        return List.of("a", "b");
    }

    public void fail() {
        throw new IllegalStateException("boom");
    }
}

public class JavadocLookupDemo {
    public static void main(String[] args) throws Exception {
        Class<LibrarySample> type = LibrarySample.class;
        Constructor<LibrarySample> ctor =
                type.getConstructor(String.class);
        LibrarySample sample = ctor.newInstance("key");

        System.out.println("Created: "
                + sample.getClass().getSimpleName());

        Method inherited = type.getMethod("inherited");
        System.out.println("Inherited declaring class: "
                + inherited.getDeclaringClass().getSimpleName());

        boolean inheritedDeclaredHere = true;
        try {
            type.getDeclaredMethod("inherited");
        } catch (NoSuchMethodException expected) {
            inheritedDeclaredHere = false;
        }
        System.out.println("Declared inherited method: "
                + inheritedDeclaredHere);

        Method primitive = type.getMethod("choose", int.class);
        Method wrapper = type.getMethod("choose", Integer.class);
        System.out.println("Primitive lookup: "
                + primitive.getParameterTypes()[0].getTypeName());
        System.out.println("Wrapper lookup: "
                + wrapper.getParameterTypes()[0].getTypeName());
        System.out.println("Primitive invocation: "
                + primitive.invoke(sample, Integer.valueOf(7)));
        System.out.println("Wrapper invocation: "
                + wrapper.invoke(sample, Integer.valueOf(7)));

        boolean missingLong = false;
        try {
            type.getMethod("choose", Long.class);
        } catch (NoSuchMethodException expected) {
            missingLong = true;
        }
        System.out.println("Long lookup missing: " + missingLong);

        Field field = type.getDeclaredField("secret");
        System.out.println("Private field accessible before: "
                + field.canAccess(sample));
        System.out.println("Private access enabled: "
                + field.trySetAccessible());
        System.out.println("Private field value: " + field.get(sample));

        Method labels = type.getMethod("labels");
        System.out.println("Erased return: "
                + labels.getReturnType().getTypeName());
        System.out.println("Generic return: "
                + labels.getGenericReturnType().getTypeName());
        System.out.println("Runtime annotation: "
                + labels.isAnnotationPresent(Action.class));

        try {
            type.getMethod("fail").invoke(sample);
        } catch (InvocationTargetException e) {
            System.out.println("Target exception: "
                    + e.getCause().getClass().getSimpleName());
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 JavadocLookupDemo.java
java JavadocLookupDemo
```

Output in a standard classpath environment, running from the same directory:

```text
Created: LibrarySample
Inherited declaring class: LibraryBase
Declared inherited method: false
Primitive lookup: int
Wrapper lookup: java.lang.Integer
Primitive invocation: primitive:7
Wrapper invocation: wrapper:7
Long lookup missing: true
Private field accessible before: false
Private access enabled: true
Private field value: key
Erased return: java.util.List
Generic return: java.util.List<java.lang.String>
Runtime annotation: true
Target exception: IllegalStateException
```

**Key analysis according to the Javadoc:**

1. `getConstructor(String.class)` finds a public constructor with the specific signature; `newInstance` creates the object. Constructors are not inherited methods.
2. `getMethod("inherited")` finds the public method inherited from `LibraryBase`, whereas `getDeclaredMethod("inherited")` does not find it because `LibrarySample` does not declare it itself.
3. `choose(int)` and `choose(Integer)` are two overloads; passing `int.class` and `Integer.class` to `getMethod` produces two different results. `invoke` on the primitive method accepts a boxed `Integer`.
4. Looking up `Long.class` does not automatically pick the `Integer` or `int` overload; there is no matching signature, so `NoSuchMethodException` occurs.
5. Class `LibrarySample` is declared at top-level scope and is not a nestmate of `JavadocLookupDemo`, so the private field is not directly accessible yet. `trySetAccessible` in the illustrative classpath environment can enable it and allow `Field.get`; **this is not a guarantee for every named module**.
6. `getReturnType()` only sees the erased type `List`, whereas `getGenericReturnType()` reads the generic Signature metadata retained by the compiler for the `List<String>` declaration.
7. Annotation `@Action` has `RUNTIME` retention, so it is found.
8. `fail()` throws `IllegalStateException`, yet through `Method.invoke` the exception is wrapped in `InvocationTargetException`; reading `getCause()` reveals the original error.

## 11. 7-Step Workflow When Facing a Real Reflection Issue

**Step 1 — Pinpoint the running API and line of code.** Record the exact call such as `type.getDeclaredMethod(...)` or `method.invoke(...)`, rather than generically saying "reflection failed."

**Step 2 — Separate the input data.** For lookup: method name, parameter `Class<?>` list, class/loader. For invocation: receiver, actual arguments, static/instance method, access permissions.

**Step 3 — Read the Javadoc matching the runtime version.** Check `Parameters`, `Returns`, `Throws`, descriptions of "public"/"declared"/"inherited", and special conditions in method detail.

**Step 4 — Open the specification at the right layer.** If comparing how the compiler picks overloads/overrides, use JLS `15.12`/`8.4`. If investigating class initialization and linkage, use JVMS Ch. 5. If generic Signature is missing, use JLS `4.6` and JVMS `4.7.9`.

**Step 5 — Write a minimal reproduction program.** One file, a few clearly named classes, deterministic inputs; print method name, `getParameterTypes()`, `getDeclaringClass()`, and class loader if relevant. Do not rely on `getDeclaredMethods()` order.

**Step 6 — Test both success and failure paths.** For instance, `getMethod(..., int.class)` succeeding and `getMethod(..., Long.class)` failing; reading a private field before and after permission is granted; invoking a method that throws an exception to confirm `InvocationTargetException`.

**Step 7 — Document the conclusion with version and conditions.** For example: "on Java 17, with classes in the unnamed module and methods declared as in the example, `getDeclaredMethod` does not find inherited methods." Do not turn module/compiler/class-loader-dependent behavior into unconditional claims.

## 12. Common Documentation Research Mistakes

| Lookup Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Searching whole blog posts instead of the Javadoc of the called API | Mixing rules of different operations | Read the method detail of the corresponding API first |
| Reading newer Java docs while running an older JDK | Conflicts in `@since` and module behavior | Use documentation matching the JDK version |
| Reading `getMethod` but applying `Method.invoke` rules to infer signatures | Finds the wrong overload | Lookup and invocation are two separate stages |
| Thinking finding a `Field` means you can read private values | `IllegalAccessException`/`InaccessibleObjectException` | Read `AccessibleObject` and module boundaries |
| Thinking `getDeclared...` automatically includes inherited members | Misses superclasses | Choose the right API, traverse superclasses when needed |
| Relying on method/field array ordering | Flaky tests | Filter by name/signature and sort when printing |
| Confusing generic metadata with an instance's type | Framework infers wrong runtime types | Distinguish erasure from `Signature` |
| Ignoring `Caused by` in exceptions | Fixes the wrong error layer | Record the exact lookup/invocation/target/linkage exception |
| Thinking `Class.forName` and `ClassLoader.loadClass` are identical | Misunderstands initialization timing | Read the Javadoc of each overload and JVMS Ch. 5 |
| Using `setAccessible` as a cure-all for every error | Does not solve metadata or linkage; may be blocked by modules | Only open access when valid; fix the true root cause |

## 13. Self-Check Exercises

**Question 1.** `getMethod("parse", Integer.class)` does not find `parse(int)`. Open Javadoc or JLS first?

**Answer:** Open the `Class.getMethod` Javadoc first because you are performing a signature lookup. Use JLS `15.12` when you want to know which overload the compiler chooses for a call in source code.

**Question 2.** `getDeclaredMethod` finds a private method, yet `invoke` fails. Which docs should you read?

**Answer:** Javadoc of `Method.invoke` and `AccessibleObject`, then JLS `6.6` if you need to understand language access rules; check `trySetAccessible` along with module/package settings.

**Question 3.** `getGenericReturnType()` sees `List<String>` while `getReturnType()` is only `List`. Do the two APIs contradict each other?

**Answer:** No. One API returns the erased runtime type, while the other reads declared generic metadata stored in the class file if present. Check JLS `4.6` and JVMS `4.7.9`.

**Question 4.** With `getDeclaredMethods()`, can you assume the first method returned is the earliest declared method in source?

**Answer:** No. Return order is not guaranteed, and the compiler may add bridge/synthetic methods. Check `Method.isBridge()`/`isSynthetic()` when relevant.

**Question 5.** `Class.forName` throws `ExceptionInInitializerError` instead of `ClassNotFoundException`. Is the Javadoc wrong?

**Answer:** No. The class may have been found, yet static initialization failed. Check the `Class.forName` overload and JVM initialization rules; distinguish lookup errors from initialization errors.

**Question 6.** An annotation has `@Retention(CLASS)` yet `getAnnotation` returns `null`. Which documentation answers this?

**Answer:** `AnnotatedElement`/`Retention` Javadocs along with JLS rules specifying retention. An annotation stored in the classfile is not automatically visible through runtime reflection.

**Question 7.** The API documentation allows accessing a method in Java 17, yet a named-module project blocks it. Do you also need to check the module specification?

**Answer:** Yes. `AccessibleObject` explains access-suppression conditions; JPMS `exports`/`opens` determine access scope. Having a method or class name does not automatically grant private reflection rights.

**Takeaway:** With Reflection, follow the order **identify the operation → read the Javadoc for the exact method/version → check JLS/JVMS when needed → write a reproduction test → conclude with conditions**. This prevents substituting compiler, JVM, and Reflection API rules for one another.
