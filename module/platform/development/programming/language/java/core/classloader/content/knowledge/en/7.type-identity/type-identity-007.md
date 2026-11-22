# Loading Constraints Ensure Type Consistency in Signatures

## 1. The problem: the same Java name can refer to two different types

In the JVM, a class or interface at runtime is identified by its **binary name and defining class loader**. If two independent class loaders both define `com.example.Message`, they create **two different runtime types**, even if the class file, package name, and class name are identical.

This matters at the boundary between two loaders. Suppose code belonging to loader `L_A` calls a method on a class defined by loader `L_B`:

```java
Message transfer(Message input);
```

If the `Message` seen by each loader is **two different runtime classes**, the two sides no longer agree on what the signature means: one side thinks the parameter/return value belongs to `L_A`'s `Message`, while the other uses `L_B`'s `Message`. The JVM must protect type safety when resolving such field and method references.

A **loading constraint** is a linking rule imposed by the JVM to ensure that type names referenced in the field/method descriptors of related classes refer to the **same runtime type when linking requires them to be identical**.

Key points:

- Two loaders **are allowed** to define two classes with the same name if no constraint forces them to be treated as one.
- When linking a field/method or an override/implement relationship requires the same type in the signature, the JVM imposes a loading constraint.
- If the loaders have already seen two incompatible definitions, or if a loader later attempts to record a class that violates an existing constraint, the corresponding operation fails with **`LinkageError`**.
- Loading constraints are part of **JVM semantics**; they are not a Java annotation, a loader configuration line, or an API call that an application invokes directly.

The foundational specification is **JVMS `5.3.4` — Loading Constraints**; the points at which constraints are imposed are described in **`5.4.2`** and **`5.4.3`**.

## 2. Recap: defining loader, initiating loader, and runtime type identity

To understand loading constraints, we need to distinguish two roles of a class loader:

| Concept | Meaning |
|---|---|
| **Defining loader** | The loader that actually invokes the class-definition mechanism and owns the runtime class identity. |
| **Initiating loader** | The loader that requested loading the class and is recorded by the JVM as an initiating loader of that class; it may receive a class defined by a parent. |
| **Binary name** | A name in the form `com.example.Message` of the class, without loader identity. |
| **Runtime class identity** | The pair of binary name + defining loader; two classes with the same name but different defining loaders are two different runtime types. |

For example: a custom loader requests `java.lang.String` through parent delegation. It can be an initiating loader for that request, while the bootstrap loader remains the defining loader of `String`. `String.class.getClassLoader() == null` in the Java API represents the bootstrap defining loader on a standard JDK.

The JVMS notation has the form:

```text
N^L1 = N^L2
```

Read this as: **the type name N, when resolved through loaders L1 and L2, must denote the same runtime class or interface**. This is a *loading constraint*, not a string comparison of the name `N`, nor does it require `L1 == L2`.

If both loaders delegate to receive the same class from a parent loader, this constraint is satisfied. If the two loaders each define two different copies of class `N`, the constraint is violated.

An intuitive example:

```text
                      Shared API
                    (loader Parent)
                        |
          +-------------+-------------+
          |                           |
       Loader A                    Loader B
    impl.A.Service              impl.B.Client
          |                           |
          +------ uses api.Message ---+
                        |
                 Class<Message>
                 defined by Parent

Both A and B resolve api.Message -> one runtime class:
constraint is satisfied.
```

Conversely, if A and B each have their own copy of `api.Message` and use their own copy when participating in a shared method that requires compatibility, the JVM can detect the conflict via a loading constraint.

## 3. Which signatures do loading constraints appear in?

The JVM stores a field's type using a **field descriptor** and a method's parameter list and return type using a **method descriptor**.

Examples:

| Java declaration | JVM descriptor |
|---|---|
| `Message message;` | `Lcom/example/Message;` |
| `Message[] messages;` | `[Lcom/example/Message;` |
| `Message transfer(Message input);` | `(Lcom/example/Message;)Lcom/example/Message;` |
| `void accept(Message[][] data);` | `([[Lcom/example/Message;)V` |
| `int count();` | `()I` |

Reference type names such as `com/example/Message` are the components that can be subject to loading constraints when linking requires consistency across loaders.

A few details:

- **Primitives** such as `int`, `long`, `boolean`, etc. do not have a class identity defined by a custom loader, so there is no issue of "same name but different defining loader."
- **Arrays** include `[` characters in the descriptor. For an array of a class/interface, the constraint is evaluated on the corresponding reference element type; you must not conclude "arrays are irrelevant because the name has `[`."
- **`void`** is a special return type and does not produce a loader-defined class reference.
- **Generics** like `List<Message>` normally undergo *erasure* to `Ljava/util/List;` in the method/field descriptor. By itself, the generic argument `Message` **does not automatically generate a loading constraint merely because it appears in generic signature metadata**. Other code that directly uses `Message` may still place that name into its own descriptor or symbolic reference.
- A `throws SomeException` list is not part of the method descriptor; an exception declaration **does not by itself** cause a constraint in the same way as parameter/return types.
- Annotations, parameter names, and nullability information are also not part of field/method descriptors.

**Do not confuse "equal descriptor strings" with "same runtime type."** Two loaders can see the exact same string `Lcom/example/Message;` yet resolve it to two different classes. A loading constraint arises when the JVM must guarantee they are identical for a specific linking operation.

## 4. Where and when does the JVM impose constraints?

The JVMS specifies imposing constraints at certain linking operations. Simply calling `loadClass` does not cause the JVM to impose a constraint across every loader in the world.

### 4.1. When preparing a class with method overriding or inheritance relationships

During **preparation**, if a subclass defines an instance method that can override a method from a superclass/superinterface, the JVM must ensure that the types involved in the method's descriptor are understood consistently between the defining loaders of the two classes.

Consider this conceptual scenario:

```java
// Defined by loader Parent:
package api;

public class Message {}

public class Base {
    public Message echo(Message value) {
        return value;
    }
}
```

```java
// Class Sub belongs to a loader Child:
package plugin;

public class Sub extends api.Base {
    @Override
    public api.Message echo(api.Message value) {
        return value;
    }
}
```

**The two blocks above are source sketches of two components, not two standalone programs placed in a single file.** They illustrate how class `Sub` overrides `Base.echo`.

The method descriptor of both methods is:

```text
(Lapi/Message;)Lapi/Message;
```

The JVM must constrain the resolution of `api.Message` through the relevant defining loaders so that both point to **one runtime class**. If Child delegates `api.Message` to Parent, the condition is met. If Child tries to use a different copy of `api.Message` in this override context, the constraint can be violated during linking.

The specification also covers the case where a class *selects* an inherited method to satisfy a superinterface method; do not oversimplify this to "only methods with the `@Override` keyword have constraints." `@Override` is a compile-time check annotation; the JVM cares about the actual method relationship in the class file.

### 4.2. When resolving a field reference

If a class defined by loader `L_Caller` accesses a field declared in a class defined by loader `L_Owner`, the JVM resolves the symbolic field reference and that field's descriptor. Class/interface names appearing in the **field's descriptor** must satisfy the corresponding loading constraints between the two sides.

Example:

```java
// Illustrates referencing a field across two classes/loaders.
Message value = service.currentMessage;
```

If the field descriptor is `Lapi/Message;`, the JVM must ensure that the caller's and field owner's understanding of `api.Message` does not lead to two different runtime types when resolution imposes the constraint.

Not **every** instance field access causes a conflict. If both sides use the same `api.Message` definition via parent delegation, the constraint is satisfied and no error occurs.

### 4.3. When resolving a method/interface method reference

For the call:

```java
Message output = service.echo(input);
```

the symbolic method reference contains the method name and descriptor, for example:

```text
echo:(Lapi/Message;)Lapi/Message;
```

When method resolution or interface method resolution succeeds in finding the method and checking access permissions, the JVM imposes loading constraints for the parameter and return types between the loader of the class declaring the selected method and the loader of the class containing the symbolic reference, according to the rules in `5.4.3`.

This ensures the caller does not use a different `api.Message` from the meaning of `api.Message` in the target method's descriptor.

### 4.4. Constraints are recorded and checked over time

You should not assume the JVM must load every class named in every descriptor as soon as it reads a `.class` file. The JVM is permitted to perform many resolution steps on demand. Consequences:

1. **A constraint can be imposed before the participating class name has actually been loaded by one or both loaders.** Later, recording an initiating loader for a newly loaded class will check any existing constraints.
2. **If both loaders have already resolved the same name to two different runtime classes**, a new constraint requiring them to be equal fails immediately when imposed.
3. **If a constraint already exists**, a later incompatible class load can fail when the JVM records the initiating loader.
4. When a violation is detected, the JVM throws `LinkageError`; the operation creating the constraint or recording the initiating loader fails, and the offending new constraint/record is rolled back according to the specification.

**The exact timing of the error can vary** depending on the program, the linking path, and whether the JVM chooses eager or lazy resolution. Do not write tests that depend on a single stack trace or a single line location across all JVMs.

## 5. Two loaders with the same name are not always wrong

An important example is that **two different runtime classes with the same binary name can coexist if no constraint forces them to be identical**.

Create a standalone file **`LoaderIdentityDemo.java`**, containing the main class and a package-private class in the same file:

```java
import java.io.IOException;
import java.io.InputStream;

public class LoaderIdentityDemo {
    private static final String TARGET = "Payload";

    static class CopyLoader extends ClassLoader {
        CopyLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> type = findLoadedClass(name);
                if (type == null) {
                    type = findClass(name);
                }
                if (resolve) {
                    resolveClass(type);
                }
                return type;
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                throw new ClassNotFoundException(name);
            }

            String resource = name.replace('.', '/') + ".class";
            try (InputStream in =
                         getParent().getResourceAsStream(resource)) {
                if (in == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = in.readAllBytes();
                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException error) {
                throw new ClassNotFoundException(name, error);
            }
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        ClassLoader app = LoaderIdentityDemo.class.getClassLoader();
        ClassLoader left = new CopyLoader(app);
        ClassLoader right = new CopyLoader(app);

        Class<?> a = left.loadClass(TARGET);
        Class<?> b = right.loadClass(TARGET);

        System.out.println("Same binary name: "
                + a.getName().equals(b.getName()));
        System.out.println("Same runtime type: " + (a == b));
        System.out.println("Left defined by left: "
                + (a.getClassLoader() == left));
        System.out.println("Right defined by right: "
                + (b.getClassLoader() == right));
        System.out.println("Assignable: " + a.isAssignableFrom(b));
    }
}

class Payload {
}
```

Compile and run on **JDK 17+** in the directory containing the file:

```bash
javac LoaderIdentityDemo.java
java LoaderIdentityDemo
```

Stdout:

```text
Same binary name: true
Same runtime type: false
Left defined by left: true
Right defined by right: true
Assignable: false
```

### Why doesn't the example throw LinkageError by itself?

The two `CopyLoader` instances are written to prefer **defining on their own** only the single class named `Payload` from the bytes on the application class path; all other classes still delegate to the parent. Because `left` and `right` are two distinct defining loaders, they create two different classes with the same name `Payload`.

However, the program **does not** establish any cross-loader override/field/method resolution relationship requiring `Payload` on both sides to be the same type. Therefore, loading `Payload` independently does not by itself cause a loading constraint error.

This clarifies an important boundary: **having two classes with the same name** and **violating a loading constraint** are two different things.

> This code is intentionally child-first for `Payload` to demonstrate class identity. It is not a pattern to use for every package: you should not blindly apply child-first loading to system namespaces, shared APIs, or arbitrary dependencies when building plugins.

## 6. Illustrating a constraint violation scenario

Suppose the host defines:

```text
Loader Parent:
  api.Message
  api.Service
    public api.Message transfer(api.Message input)
```

The plugin loader `Child` must override `api.Service`'s `transfer` method or call that method via a symbolic reference. However, the plugin also defines its own `api.Message` with the **same binary name** but a different defining loader.

```text
                 Parent defines:
              api.Message [P]
              api.Service [P]
                       |
                       | method descriptor:
                       | (Lapi/Message;)Lapi/Message;
                       |
                Plugin Child
                defines its own:
              api.Message [C]  != [P]
                       |
                       v
       JVM requires api.Message^Child
                 == api.Message^Parent
                       |
                       v
          Conflict: [C] != [P]
                       |
                       v
                  LinkageError
```

In that situation, if the JVM must impose the loading constraint `api.Message^Child = api.Message^Parent` due to preparation or method resolution, it checks whether the same name resolves to the same runtime class.

If Child has already defined its own copy of `api.Message`, the constraint is violated. If not yet loaded, the established constraint can cause a subsequent attempt by Child to define its own copy to fail.

A message on HotSpot may contain the phrase `loader constraint violation`, the class name, and descriptions of the involved loaders; **do not assume the exact message wording or timing across all JVM versions**.

### The right design

If `api.Message` is a shared DTO or contract:

- Place `api.Message` and `api.Service` in an API module/JAR defined by a shared loader.
- Have the plugin loader **delegate** to the API's defining loader for the `api.*` namespace.
- Use isolated loading strategies only for plugin classes that truly need isolation; avoid packaging/redefining duplicate copies of the API inside plugins when communicating with the host.
- When creating objects and passing them across boundaries, verify that the class used by caller and callee is the **same runtime class**.

In other words, matching package names in JARs do not create a shared type identity; **how loaders resolve classes** is what decides it.

## 7. How do loading constraints differ from ClassCastException?

These errors all appear in multi-classloader systems, but they have different causes and occur at different times.

| Symptom | Characteristics |
|---|---|
| **`LinkageError` due to loading constraint violation** | The JVM detects that a type name must be consistent across loaders during preparation/resolution, but the existing definitions (or a new load) cannot satisfy it; fails during loading/linking. |
| **`ClassCastException`** | At runtime, an object is not an instance of the type required by a cast; two classes with the same name but different defining loaders can cause a cast failure. |
| **`ClassNotFoundException`** | A loader was asked to find a class and could not find it; does not mean there are two conflicting copies. |
| **`NoClassDefFoundError`** | The JVM cannot find or use a required class definition during execution/linking; can also relate to prior initialization failure. Not synonymous by default with a loading constraint violation. |
| **`NoSuchMethodError`** | Resolution cannot find a method with a matching name/descriptor; different from finding the method and having the sides' descriptors cause a constraint conflict. |

An example:

- If an app has `Foo` from loader A and passes an object of `Foo` defined by loader B into a cast to A's `Foo`, you can get a **`ClassCastException`**.
- If the JVM must link a call/override requiring `Foo` of A and B to be the same type in a descriptor and they already differ, you can get a **`LinkageError`** before ever having a chance to execute a cast.

You do not need to trigger both errors to conclude that loaders are configured inconsistently. Pinpoint the exact failure phase: **lookup**, **linking**, **initialization**, or **runtime cast**.

## 8. Loading constraints, method overriding, and JVM descriptors

### Class-file-level overriding

In Java source code, overriding is checked according to language rules. In the JVM, whether an instance method can override another method is determined by name, **method descriptor**, and the corresponding access/inheritance conditions (JVMS `5.4.5`).

Because a method descriptor contains **parameter types and the return type**, two methods having the same descriptor string does not guarantee they use the same runtime types if the classes are defined by two different loaders.

Loading constraints add the consistency requirement for reference names in the descriptor when the JVM prepares a class with an applicable override relationship.

### Generics do not solve class identity

Example:

```java
public java.util.List<api.Message> fetch() {
    return java.util.List.of();
}
```

The JVM descriptor after erasure of the method above is:

```text
()Ljava/util/List;
```

The type argument name `api.Message` typically resides in the generic `Signature` metadata, not in this **method descriptor**. Therefore, you cannot say the JVM automatically creates a loading constraint for `api.Message` **solely because** it appears in `List<api.Message>`.

This does not make type arguments safe across loaders. When code actually accesses, casts, or calls APIs that use `api.Message` in their descriptors, the corresponding linkage and cast rules still apply.

### Arrays of reference types

The method:

```java
api.Message[] copy(api.Message[][] data)
```

has the descriptor:

```text
([[Lapi/Message;)[Lapi/Message;
```

In constraints involving a method descriptor, the element type name `api.Message` must still be resolved consistently. You cannot use a difference in array dimensions to bypass the requirement for the same runtime element type when the JVM imposes a constraint.

### Primitives do not cause same-name loader conflicts

The method `int count(long value)` has the descriptor `(J)I`. `J` and `I` describe primitives predefined by the JVM; there is no custom class loader A defining "int A" and loader B defining "int B."

Of course, a class with primitive methods is still subject to other linking rules; simply using `int`/`long` in a descriptor does not require a loading constraint for a class reference.

## 9. Constraints do not force every same-named class in the JVM to merge

This is a dangerous misconception when designing a plugin architecture.

**Loading constraints are specific equality relationships** imposed by the JVM when needed to ensure type-safe linkage. They do not mean Java globally allows only one `com.example.Widget`.

Consider two completely independent plugins:

```text
Plugin A (loader A): com.example.Widget
Plugin B (loader B): com.example.Widget
```

If there is no API signature/override/field resolution requiring the name `Widget` in A and B to be the same, the JVM can keep both runtime classes. This may be the exact goal of classloader isolation.

However, if the host declares:

```text
shared.PluginApi:
  Widget convert(Widget input)
```

and A/B must execute through this shared API, the `Widget` type in the API signature must be designed so that all sides resolve it consistently. The safe approach is usually to place shared DTOs/interfaces in a **shared API loader**. Do not try to rely on identical names as a way of forcing two loaders to share a type.

Distinguish three levels:

1. **Do the names match?** Compare `Class.getName()`.
2. **Do the runtime classes have the same identity?** Compare two `Class<?>` objects with `==`.
3. **Does linking force them to have the same identity?** Examine field/method descriptors, overrides, interface method selection, and the specific symbolic references of the JVMS.

The first two are state observations; the third concerns the condition the JVM must enforce during linking.

## 10. Parent delegation helps satisfy constraints, but does not replace them

In a typical parent-first model:

```text
App loader
    |
    v
Parent loader (defines api.Message)
    |
    +--> Plugin loader A requests api.Message
    |
    +--> Plugin loader B requests api.Message
```

Two plugins can load many separate implementation classes, but for the `api.Message` namespace, both receive the same definition from Parent. When a loading constraint requires this type to be consistent, the condition is satisfied.

However:

- **Parent-first is not a hard rule for every custom loader.** A loader overriding `loadClass` can choose to self-define certain packages first.
- **Sharing a parent does not guarantee every same-named class shares an identity.** If two loaders override/define the same class name before delegating, they can still create two classes.
- **Constraints are JVM rules**, not an accidental side effect of following parent-first.
- **A `null` parent** typically delegates to bootstrap under the default `ClassLoader.loadClass` implementation. This helps unify core classes, but a `null` parent cannot automatically see APIs in the application loader. If shared DTOs/interfaces are not in bootstrap, you must choose an appropriate loader architecture.

A plugin architecture should have explicit package rules: core/JDK from platform/bootstrap, shared contracts from a shared loader, and private implementations from the plugin loader; carefully consider module boundaries, dependency visibility, and lifecycle.

## 11. Investigating loading constraint errors in real applications

When you see a `LinkageError` with a message involving `loader constraint violation`, do not rush to rename classes or delete all JARs. Analyze along the linking path:

1. **Read the type name in the error**: which class/interface do the two loaders disagree on? Does that name appear in the field type, parameter type, or return type of the linked API?
2. **Identify the two loaders**: who defined the caller/callee, superclass/subclass, or interface/implementation? Compare class loader identity, not just the loader display name.
3. **Inspect the JVM descriptor of the field/method**: use `javap -s -p` to see the actual types after erasure. If override/bridge analysis is needed, use `javap -v -p` to inspect methods, flags, and `Signature`.
4. **Check for dependency duplication**: does the plugin bundle a copy of the shared interface/DTO/JAR inside itself? Is parent delegation overridden for the shared namespace?
5. **Compare `Class<?>` directly when possible**: two types with the same name but different under `==` indicate different loader identities; identify where linking demands identity.
6. **Do not rely on when the error appears**: resolution can be lazy. That the error surfaces on the first method call does not mean the cause was just created at that instruction.
7. **Fix it in the loader/class path architecture**: unify ownership of shared APIs and avoid creating multiple copies of classes acting as shared contracts. After fixing, create a new appropriate loader/runtime; a class already defined in a loader cannot arbitrarily "switch the defining loader" of that runtime class.

### Observation tools

Inspect descriptors:

```bash
javap -s -p api.Service
javap -v -p api.Service
```

Replace `api.Service` with the actual class name on the class path/module path visible to the tool. `javap` reads bytecode and prints metadata; it **does not confirm** which loader's definition the runtime is using.

Observe class loading on HotSpot JDK 17:

```bash
java -Xlog:class+load=info YourMainClass
```

Output can be verbose and formatting varies by VM. Logs can help show where a class came from, but proving runtime identity still requires checking the **defining loader** and resolution path in the running program.

With code that has access:

```java
System.out.println(typeA.getName());
System.out.println(typeA.getClassLoader());
System.out.println(typeA == typeB);
```

This is an **illustrative** snippet: `typeA`/`typeB` must be two `Class<?>` values obtained from the right places. Do not infer from two identical `getName()` strings that they are the same `Class<?>`.

## 12. Common mistakes to avoid

| Misconception | Reality |
|---|---|
| "If two loaders load the same `Foo`, the JVM always throws an error." | A conflict occurs only when a linking constraint requires identity and they cannot satisfy it. |
| "Same binary name and same bytecode means same runtime type." | Different defining loaders create two different runtime class identities. |
| "Constraints are created for every class name as soon as the class file is found." | The JVM imposes them at specified preparation/resolution operations; resolution timing can vary. |
| "Having generic `List<Foo>` in a signature always forces loaders to share `Foo`." | The erased descriptor may contain only `java.util.List`; generic `Signature` has separate rules. |
| "A constraint error is always a `ClassCastException`." | A constraint violation is a linking/loading error of type `LinkageError`; a bad cast happens at runtime. |
| "Using the same class name in two plugins is how to share a DTO." | Shared DTOs must share a runtime definition via an appropriate loader. |
| "Using parent-first means the JVM no longer needs loading constraints." | Constraints are a JVM-level guarantee; delegation is a lookup strategy that helps satisfy many constraints. |
| "Errors can only happen right at `new CustomLoader()`." | Creating a loader object is distinct from class linking; errors can appear during loading, preparation, or resolution. |
| "A method descriptor only includes parameters, not the return type." | A method descriptor contains parameters **and** the return type, e.g., `(LFoo;)LFoo;`. |
| "Every `LinkageError` is a loading constraint violation." | `LinkageError` is a broad category; inspect the subtype/cause/message and context. |

## 13. Self-check exercises

**Question 1.** Loaders A and B both define `com.example.Event`. If the program has no communication requiring `Event` to be unified, does that automatically violate a loading constraint?

**Answer:** No. Two runtime classes with the same name can coexist. Constraints arise only in JVM-specified situations requiring type-safe linkage across loaders.

**Question 2.** Which descriptor represents the method `Event echo(Event input)`? If two loaders participate in linking this method, which name is a candidate for a constraint?

**Answer:** With `Event` in `com.example`, the descriptor is `(Lcom/example/Event;)Lcom/example/Event;`. The reference type name `com.example.Event` is the candidate when the JVM imposes the appropriate constraint.

**Question 3.** Two loaders both call `loadClass("java.lang.String")` via parent delegation and receive the bootstrap `String.class`. Is a constraint requiring both sides to agree on `String` satisfied?

**Answer:** Yes, because the same runtime class is used, even though the initiating loaders differ.

**Question 4.** Why can't you use `clazzA.getName().equals(clazzB.getName())` to prove two classes are the same?

**Answer:** `getName()` only reflects the name, whereas runtime identity also depends on the defining loader. Comparing `clazzA == clazzB` confirms the same `Class` object representing the same runtime type.

**Question 5.** Why doesn't `List<Event> fetch()` necessarily impose a constraint directly on `Event` from the method descriptor alone?

**Answer:** The generic argument `Event` is erased; the JVM descriptor is typically `()Ljava/util/List;`. Handling `Event` in other code can still create separate symbolic references/constraints.

**Question 6.** A class in a plugin overrides a method using `api.Event` defined in the parent loader. What deployment approach avoids conflicts?

**Answer:** Have the plugin loader delegate the shared API namespace (including `api.Event`) to the shared defining loader, so both sides resolve the same class. Avoid defining a copy of `api.Event` inside the plugin.

**Question 7.** A loading constraint was recorded when one loader had not yet loaded `api.Event`. That loader later attempts to define a copy of `api.Event` different from the other side's. What can happen?

**Answer:** When the VM records the new initiating loader/class and checks constraints, if the equality relationship cannot be satisfied, the corresponding load operation fails with `LinkageError`. You should not assume the error must have fired earlier when the constraint was first imposed.

## 14. Core takeaways and references

A loading constraint is a **rule that preserves type safety when linking across class loaders**. The JVM can allow multiple classes with the same binary name to exist, but when methods/fields in a linking relationship must use **the same reference type**, the VM requires that name to resolve to the **same runtime class** across the involved loaders.

Remember four points:

1. **Class identity** = binary name + defining loader.
2. **Loading constraint** notation `N^L1 = N^L2`: the same name `N` must denote the same runtime type when linking requires it.
3. The JVM imposes constraints during **preparation** (e.g., overriding/method selection) and **resolution** (field/method/interface method); violations cause **`LinkageError`** according to JVM rules.
4. **Shared API types** should be defined once in a shared loader so plugins/callers share the same runtime identity through proper delegation.

Standard references:

- [JVMS 17 — `5.3.4` Loading Constraints](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3.4): rationale, notation, when classes are recorded, and checking loading constraints.
- [JVMS 17 — `5.4.2` Preparation](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.2): imposing constraints for overridable methods and methods selected from interfaces.
- [JVMS 17 — `5.4.3` Resolution](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3): rules for symbolic field, method, and interface method references.
- [JVMS 17 — `4.3` Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3): field/method descriptor grammar.
- [Java SE 17 — `ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `loadClass`, and defining classes.
