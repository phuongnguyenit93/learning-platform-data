# The Parent Relationship Is an Object Relationship, Not Java Class Inheritance

When learning the delegation mechanism of **Java ClassLoader**, a very common confusion is viewing a *parent class loader* as a parent class in Java. These two concepts are completely different:

- **The parent of a class loader** is **another `ClassLoader` object** referenced to serve the class/resource lookup delegation mechanism. It can be inspected via `loader.getParent()`.
- **The superclass of a Java class** is **a Java type** that the class declares inheritance from via `extends` (or implicit inheritance), inspected via `SomeLoader.class.getSuperclass()`.

An object of class `PluginLoader` can perfectly well take **an object** of class `HostLoader` as its parent, **even though `PluginLoader` does not inherit from `HostLoader`**. Conversely, `ChildLoader extends BaseLoader` does not automatically make every instance of `BaseLoader` the parent of a `ChildLoader` instance.

This lesson consistently uses the terms **parent relationship of loader instances** and **inheritance relationship between Java classes**, explains how they affect `loadClass`, and provides runnable Java 17+ programs for verification.

## 1. Two Different Diagrams

### 1.1. Java Type Tree (inheritance / type hierarchy)

```text
java.lang.Object
      │
      └── java.lang.ClassLoader
                 ├── HostLoader
                 └── PluginLoader
```

For example: `HostLoader extends ClassLoader` and `PluginLoader extends ClassLoader`. Both classes inherit from `ClassLoader`; there is **no** `PluginLoader extends HostLoader` relationship.

The diagram above describes:

- `PluginLoader` can inherit APIs from `ClassLoader` such as `loadClass`, `getParent`, and related `protected` methods.
- A `PluginLoader` instance has type `PluginLoader`, and is also a `ClassLoader` and an `Object`.
- The validity of assignment/casting in Java depends on this type hierarchy.
- Changing a loader's `parent` reference **cannot change the superclass** of the Java class being defined.

### 1.2. Chain of Class Loader Objects (delegation / object graph)

```text
pluginLoader (instance of PluginLoader)
      │ getParent()
      ▼
hostLoader   (instance of HostLoader)
      │ getParent()
      ▼
platformLoader (instance of built-in platform class loader)
      │ getParent()
      ▼
bootstrap loader (usually represented as null in Java)
```

This diagram describes **objects existing at runtime**. The connection `pluginLoader.getParent() == hostLoader` is established by the `ClassLoader` constructor, not by the `extends` keyword.

The two diagrams can coexist while answering **two different questions**:

| Question | Asks about | API/expression |
| --- | --- | --- |
| "Which class does `PluginLoader` inherit from?" | Java type, when writing/compiling the program | `PluginLoader.class.getSuperclass()` |
| "Which loader does the `pluginLoader` object delegate to?" | Relationship between instances, at runtime | `pluginLoader.getParent()` |
| "What type does the `pluginLoader` object belong to?" | Runtime class of the loader object itself | `pluginLoader.getClass()` |
| "Which loader defined the `Class<?>` of `demo.Item`?" | Runtime identity of the **loaded class** | `itemClass.getClassLoader()` |
| "Can a loader find this class?" | Class lookup/delegation | `loader.loadClass("demo.Item")` |

**Specifically avoid this confusion:** `ClassLoader.getParent()` is called on a **loader object**, whereas `Class.getSuperclass()` is called on a **Class object**. Sharing the word "parent" in casual explanations does not make them the same relationship.

## 2. `extends` Determines the Superclass, While the Constructor Determines the Parent Object

Let's compare the three code snippets:

```java
class HostLoader extends ClassLoader {
    HostLoader(ClassLoader parent) {
        super(parent);
    }
}

class PluginLoader extends ClassLoader {
    PluginLoader(ClassLoader parent) {
        super(parent);
    }
}
```

These are **illustrative declarations**; to run standalone, see the complete example in Section 4. They have two forms of relationships:

1. `extends ClassLoader` determines the **superclass of the types** `HostLoader` and `PluginLoader`. This decision is in the class declaration, is written by the compiler into the class file, and is part of the Java type structure.
2. `super(parent)` calls the **`ClassLoader` constructor** and passes **a reference to a loader instance** as the parent for the instance being created. It is not "choosing a superclass" via a parameter.

Example of creating instances:

```java
ClassLoader platform = ClassLoader.getPlatformClassLoader();
HostLoader host = new HostLoader(platform);
PluginLoader plugin = new PluginLoader(host);
```

Resulting relationships:

```text
host.getParent()   == platform     → true
plugin.getParent() == host         → true

host.getClass().getSuperclass()    → ClassLoader.class
plugin.getClass().getSuperclass()  → ClassLoader.class
```

`plugin` does not have type `HostLoader`. **`HostLoader.class.isInstance(plugin)` returns `false`**, even though the `host` object is the parent of `plugin`.

A constructor taking a `ClassLoader parent` parameter allows the parent to be **any suitable `ClassLoader` subclass** — typically a built-in system/platform loader or a custom loader. Java checks the `ClassLoader` parameter type; it does not require "the parent instance's class to be the superclass of the child class".

## 3. The Three `ClassLoader` Constructors and the Meaning of the Parent Parameter

In Java 17+, `java.lang.ClassLoader` has commonly used `protected` constructors:

| Constructor | Selected parent | When to use |
| --- | --- | --- |
| `ClassLoader()` | `ClassLoader.getSystemClassLoader()` | A custom loader using the system loader as its default parent. |
| `ClassLoader(ClassLoader parent)` | The exact `parent` object passed in | When explicit control over the delegation chain is needed. |
| `ClassLoader(String name, ClassLoader parent)` | The passed-in parent; also sets the **loader name** | When you want to assign a name to aid diagnostics in Java 9+. |

**`parent == null`** usually represents the **bootstrap loader** as the parent in the standard `ClassLoader` mechanism, rather than meaning selecting a Java parent class of `null`. From Java 9 onward, not all platform classes are guaranteed to be visible through the bootstrap loader; if broader Java platform APIs are needed, consider `ClassLoader.getPlatformClassLoader()`.

Several details to keep in mind:

- `ClassLoader.getParent()` is a **`final`** method in the JDK API: subclasses cannot override this method to spoof the returned parent.
- There is no public `setParent(...)` API to arbitrarily change the parent after creating a loader. Design the relationship when constructing the instance.
- `ClassLoader` remains a **class that can be extended**: a program writes a subclass and overrides `findClass` to support its own source of class bytes.
- `ClassLoader(String name, ClassLoader parent)` sets the **name of the loader instance**; this name is not a Java class name and is not the binary name of the class it loads.
- Some JVMs have security-manager checks in loader creation/inspection APIs; this does not alter the distinction between the two relationships.

### `super(parent)` Does Not Mean the Parent Is a Superclass

In the constructor:

```java
PluginLoader(ClassLoader parent) {
    super(parent);
}
```

`super(...)` in terms of the **Java language** always calls a constructor of the **superclass** `ClassLoader`, so the word `super` here is inheritance syntax. However, the **`parent` argument** is the **loader object** that `ClassLoader` retains for delegation. Because both concepts appear on the same line, it is very easy to confuse them.

The right way to read this statement is: "Call the constructor of the Java superclass `ClassLoader`, passing in the parent loader reference that we want the new instance to use." Not: "turn the passed-in object into the superclass of `PluginLoader`."

## 4. Practice A — Two Loader Classes That Do Not Inherit From Each Other Still Form a Parent Relationship

Create a single Java file:

```text
parent-object-lab/
└── src/
    └── demo/
        └── ParentVsInheritance.java
```

**`src/demo/ParentVsInheritance.java`:**

```java
package demo;

public class ParentVsInheritance {

    static final class HostLoader extends ClassLoader {
        HostLoader(ClassLoader parent) {
            super(parent);
        }
    }

    static final class PluginLoader extends ClassLoader {
        PluginLoader(ClassLoader parent) {
            super(parent);
        }
    }

    public static void main(String[] args) {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();
        HostLoader host = new HostLoader(platform);
        PluginLoader plugin = new PluginLoader(host);

        System.out.println("plugin parent is host: " +
                (plugin.getParent() == host));
        System.out.println("host parent is platform: " +
                (host.getParent() == platform));
        System.out.println("plugin is HostLoader: " +
                HostLoader.class.isInstance(plugin));
        System.out.println("same Java superclass: " +
                (host.getClass().getSuperclass()
                        == plugin.getClass().getSuperclass()));
        System.out.println("superclass is ClassLoader: " +
                (PluginLoader.class.getSuperclass() == ClassLoader.class));
    }
}
```

Using JDK 17+ from the `parent-object-lab` directory:

```sh
javac --release 17 -d out src/demo/ParentVsInheritance.java
java -cp out demo.ParentVsInheritance
```

**Exact stdout:**

```text
plugin parent is host: true
host parent is platform: true
plugin is HostLoader: false
same Java superclass: true
superclass is ClassLoader: true
```

**Why is the third line `false`?** `plugin` is an instance of `PluginLoader`, which only `extends ClassLoader`. The `plugin.getParent() == host` relationship does not create an additional `PluginLoader extends HostLoader` relationship.

**Why is the fourth line `true`?** Both Java classes directly inherit from `ClassLoader`. Comparing `getSuperclass()` compares the `Class<?>` objects representing the **parent type**, not the loader parents.

**Why use `HostLoader.class.isInstance(plugin)`?** It demonstrates a safe runtime type check for two sibling classes. There is no need to write an illegal cast from `PluginLoader` to `HostLoader`.

**Note:** Neither subclass overrides `findClass` yet, so they only help illustrate the *parent object* and do not load custom bytecode on their own yet. Their built-in delegation capability is inherited from `ClassLoader`.

## 5. Practice B — Two Objects of the Same Java Class Can Still Be Parent and Child

The opposite misconception is thinking that you must have **two different Java subclasses** to have a parent/child relationship. That is unnecessary: you only need **two instances** with an appropriate link.

Create `src/demo/SameTypeChain.java`:

```java
package demo;

public class SameTypeChain {

    static final class NamedLoader extends ClassLoader {
        NamedLoader(String name, ClassLoader parent) {
            super(name, parent);
        }
    }

    public static void main(String[] args) {
        ClassLoader platform = ClassLoader.getPlatformClassLoader();

        NamedLoader first = new NamedLoader("first", platform);
        NamedLoader second = new NamedLoader("second", first);

        System.out.println("same class: " +
                (first.getClass() == second.getClass()));
        System.out.println("different objects: " + (first != second));
        System.out.println("second parent is first: " +
                (second.getParent() == first));
        System.out.println("first parent is platform: " +
                (first.getParent() == platform));
        System.out.println("names: " +
                first.getName() + ", " + second.getName());
    }
}
```

From the practice directory containing `src`:

```sh
javac --release 17 -d out src/demo/SameTypeChain.java
java -cp out demo.SameTypeChain
```

**Exact stdout:**

```text
same class: true
different objects: true
second parent is first: true
first parent is platform: true
names: first, second
```

`first` and `second` both have the Java class `NamedLoader`; **there is no concept of "`second` extends `first`"**, because `extends` applies to types, not to two objects.

Two objects of the same class can also be **two sibling loaders** if both use platform as their parent. The parent object relationship is chosen **per instance**, rather than being automatically derived from the class name or how the class is declared.

This difference is essential when an application creates one loader instance for **each plugin/version/tenant**. A single loader subclass can create multiple independent namespaces because each instance defines different classes.

## 6. How Is the Parent Used in the Class Loading Delegation Mechanism?

For subclasses using the default implementation of `ClassLoader.loadClass(String, boolean)`, the general behavior consists of three steps:

1. Check `findLoadedClass(name)` to see whether a class with that name has already been recorded as loaded by the loader previously.
2. If not, try `parent.loadClass(name)`; when the parent is `null`, the VM mechanism is used to look it up via bootstrap.
3. If the parent cannot find it, call `findClass(name)` on the loader itself. If found and the `resolve` parameter is `true`, request linking using `resolveClass`.

Example of a typical flow:

```text
plugin.loadClass("demo.Feature")
          │
          ├── findLoadedClass("demo.Feature") ?
          │       └── yes → return known Class<?>
          │
          └── plugin.getParent() is host
                     │
                     └── host.loadClass("demo.Feature")
                               ├── found by host/ancestor → return
                               └── not found → try
                                   plugin.findClass("demo.Feature")
                                               │
                                       define itself or
                                       ClassNotFoundException
```

**Core point:** Finding the **parent to call `loadClass`** relies on **a reference field of the loader object**, not on using `getSuperclass()` to find the parent's Java class. The inherited `loadClass` implementation code in `ClassLoader` can still call a `HostLoader` **object** as the parent of a `PluginLoader` instance.

The `extends` relationship only determines **which Java code is inherited/overridden**. For example, the `PluginLoader` subclass can override `findClass` to read bytecode from a plugin JAR, while the `host` parent object can be a completely different subclass using its own lookup mechanism.

**Do not equate:** "parent did not find it" is simply a lookup outcome suitable for falling back to `findClass`. A `LinkageError`, `SecurityException`, or invalid bytecode error is not always a `ClassNotFoundException` that may be ignored and unconditionally retried.

### Parent-First Is the Default Behavior, Not the Definition of `extends`

The default implementation of `ClassLoader` is **parent-first delegation**. Subclasses can override `loadClass` to implement a different strategy, but must manage concurrency, type identity, package/module constraints, protected JDK classes, and consistency with resource loading. The Javadoc recommends that subclasses normally **override `findClass`** rather than rewriting all of `loadClass`.

In JDK 9+, built-in loaders also have mechanisms for interacting with **JPMS**; in certain cases involving upgraded modules, class lookup does not match a strictly linear parent chain diagram. The examples in this lesson aim to explain **the parent object relationship of a custom `ClassLoader` using the default mechanism**, without assuming that every class loader in the Java world follows the exact same algorithm.

## 7. Practice C — Observing Parent-First and `findClass` with Controlled Logging

Create `src/demo/DelegationTrace.java`:

```java
package demo;

public class DelegationTrace {

    static final class TracingLoader extends ClassLoader {
        TracingLoader(ClassLoader parent) {
            super(parent);
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            System.out.println("findClass called: " + name);
            throw new ClassNotFoundException(name);
        }
    }

    public static void main(String[] args)
            throws ClassNotFoundException {
        TracingLoader child =
                new TracingLoader(ClassLoader.getPlatformClassLoader());

        Class<?> stringClass = child.loadClass("java.lang.String");
        System.out.println("String reused: " +
                (stringClass == String.class));

        try {
            child.loadClass("demo.MissingForLesson");
        } catch (ClassNotFoundException expected) {
            System.out.println("missing class: " +
                    expected.getClass().getSimpleName());
        }
    }
}
```

From the practice directory:

```sh
javac --release 17 -d out src/demo/DelegationTrace.java
java -cp out demo.DelegationTrace
```

**Exact stdout on a typical Java 17+ runtime:**

```text
String reused: true
findClass called: demo.MissingForLesson
missing class: ClassNotFoundException
```

Why did `findClass` **not print** when loading `java.lang.String`?

- `TracingLoader` uses the default implementation of `loadClass`.
- The passed-in parent is the platform loader, which sees `java.lang.String` via bootstrap.
- The parent returns the `String` class. The child loader **does not need** to call `findClass` for this name.
- `String.class.getClassLoader()` is typically `null`, defined by bootstrap; there is no self-defined copy of `String` in `TracingLoader`.

Why **did** `findClass` print for `demo.MissingForLesson`?

- There is no class with that name on the platform/ancestor in this practice setup.
- Asking the parent does not find it, so the default `loadClass` calls `child.findClass(name)`.
- `findClass` only prints the message and then throws `ClassNotFoundException`. Therefore, this is a **fallback-observation** demo, not a complete custom bytecode loader.

**At which step was the content loaded by the JVM?** You cannot infer which loader defined a class solely from a "`findClass called`" log: `findClass` can fail. When a `Class<?>` is actually returned, check `result.getClassLoader()` to see the **defining loader**.

## 8. Three "Parent/Child" Relationships Easily Confused in an Application

When reading framework code, there are usually at least three distinct relationships:

### 8.1. Java Class Inheritance

```java
class BaseLoader extends ClassLoader { }

class SpecializedLoader extends BaseLoader { }
```

These are **two illustrative class declarations**, not a standalone program. The type relationship is:

```text
SpecializedLoader.class.getSuperclass() == BaseLoader.class
```

Inheritance allows `SpecializedLoader` to reuse or override the behavior of `BaseLoader`. **It does not automatically create a `BaseLoader` object as a parent** when creating `SpecializedLoader`. If the constructor does not call `super(parent)` according to a custom design and ends up using `ClassLoader`'s no-argument constructor, the parent may be the default system loader.

### 8.2. Parent Delegation Between Loader Instances

```java
ClassLoader root = ClassLoader.getPlatformClassLoader();
ClassLoader child = new ClassLoader(root) { };
```

This is valid code that can be placed in `main`. `child.getParent() == root`, even though the runtime type of `child` is an anonymous `ClassLoader` subclass. The parent object is the connection specified in the constructor, not the superclass.

### 8.3. The Loaded Java Object and Its Java Superclass

Suppose we have domain classes:

```java
class Animal { }
class Dog extends Animal { }
```

The fact that `Dog.class.getSuperclass() == Animal.class` speaks to **the inheritance of the `Dog`/`Animal` domain classes**. It does not tell you what `Dog.class.getClassLoader().getParent()` is.

In other words:

- `Dog.class.getSuperclass()` returns `Class<Animal>`.
- `Dog.class.getClassLoader()` returns **the loader that defined `Dog`**, or `null` if bootstrap.
- `Dog.class.getClassLoader().getParent()` (when the loader is non-`null`) returns **the parent of the defining loader**, not necessarily the loader that defined `Animal`.

Two classes with an `extends` relationship can perfectly well be defined by **the same class loader**, or defined by different loaders while still satisfying type-safety rules and loader constraints. Do not infer that "the superclass of `Dog`" must be defined by "the parent loader of the loader that loaded `Dog`".

## 9. Runtime Class Identity Also Depends on the Loader Instance, Not the Subclass Name

The JVM considers a runtime class/interface to be identified by **(binary name, defining loader)**. This connects directly to this lesson:

- Two **loader instances of the same Java class** can still define **two different runtime classes** with the same binary name.
- Two loader instances of **different Java subclasses** can still access **the same runtime class** if they delegate and receive the same `Class<?>` defined by a parent.
- Comparing only `loaderA.getClass() == loaderB.getClass()` is **not enough** to determine that two loader instances represent the same namespace.
- Comparing only `classA.getName().equals(classB.getName())` is **not enough** to determine that two runtime types are the same; compare `classA == classB` or use `isAssignableFrom` appropriately.

Illustrative diagram example:

```text
NamedLoader #1                   NamedLoader #2
(same Java class)                (same Java class)
    │ define "plugin.Task"           │ define "plugin.Task"
    ▼                                ▼
Class<?> task1                   Class<?> task2

task1.getName() == task2.getName()    → same name
task1 == task2                        → false (if both define it themselves)
```

This is a **conceptual model**: the two loaders in Example B did not perform `defineClass` themselves. Demonstrating real isolation requires implementing `findClass`/`defineClass` or using loaders capable of reading JARs, handling dependencies, package constraints, and lifecycles. Do not treat the diagram as stdout from Example B.

**Terminology warning:** the *initiating loader* is the loader used to request loading; the *defining loader* is the loader that defined the class. If `child.loadClass("java.lang.String")` returns `String.class` through the parent, the defining loader may still be bootstrap. `child` being the API call point does not automatically make it the defining loader.

## 10. Practical Implications When Designing Plugins and Application Servers

### 10.1. Choosing the Parent Based on the API to Share

In a plugin system, suppose the host defines the interface `com.example.spi.Plugin`. A plugin implementation needs to be recognized as a subtype of the interface **that the host is using**.

If the plugin uses a loader whose parent is the application/system loader (or another shared-API loader), both the host and the plugin can see the same `Class<?>` for the SPI interface. If the plugin defines its own copy of the interface with the same name, casting to the host's interface may fail.

What matters is choosing the **parent object and class lookup policy** to maintain **the same runtime interface identity**. Creating a loader subclass named `PluginClassLoader` or `HostClassLoader` does not handle that on its own.

### 10.2. Why Not Base the Parent Relationship on the Java Superclass?

Suppose you write:

```java
class PluginLoader extends HostLoader { }
```

Then `PluginLoader` inherits the code of `HostLoader`. This **does not automatically guarantee** that it queries a **separate `HostLoader` instance** before searching for a class. To establish that relationship, you must pass/set the right parent object via the constructor.

Conversely, if you want the plugin to behave differently from the host, `extends HostLoader` can pull in unwanted code and state. Another option is:

```java
class PluginLoader extends ClassLoader {
    PluginLoader(ClassLoader hostLoader) {
        super(hostLoader);
    }
}
```

This is a choice about **API design and composition**, while the delegation mechanism is governed by the parent object and `loadClass` behavior. The class snippet here only illustrates the constructor and does not contain full plugin-loading code.

### 10.3. Choosing Platform, System, or a Custom Loader as Parent?

| Parent object | Typical effect | Limitations to remember |
| --- | --- | --- |
| `ClassLoader.getPlatformClassLoader()` | Can see platform classes, with fewer application dependencies | Does not by default see all classes on the application classpath, especially shared SPIs. |
| `ClassLoader.getSystemClassLoader()` | Usually sees the application and platform classpath | May prioritize host dependencies instead of plugin versions that need isolation. |
| A custom shared-API loader | Shares intentionally selected communication types | Must carefully design which loader loads which API. |
| `null` in the loader constructor | Uses bootstrap for default delegation | Since Java 9, visibility of all platform APIs is not guaranteed. |

There is no single absolute choice for every plugin. You must first determine which classes **must share a runtime identity** and which classes are allowed to be isolated.

### 10.4. Do Not Change the Parent Dynamically

`getParent()` is `final`, and the parent is set during loader creation. A design that unexpectedly changes the parent can violate assumptions used to resolve classes, resource lookup consistency, and loading constraints. If new dependency classes or a new plugin lifecycle are needed, consider creating a new loader instance according to the architecture and managing references/lifecycles carefully.

Creating a new loader instance **does not mean the loader's Java class is redefined**. `PluginLoader.class` can remain a single `Class<?>`, while dozens of its instances are loading different sets of plugins.

## 11. Distinguishing Parent Loader From Superclass Loader and Context Loader When Debugging

A useful inspection snippet in a program that already has `loader` and `loadedType`:

```java
System.out.println(loader.getClass().getName());
System.out.println(loader.getClass().getSuperclass());
System.out.println(loader.getParent());
System.out.println(loadedType.getClassLoader());
System.out.println(Thread.currentThread().getContextClassLoader());
```

This is an **illustrative snippet** that compiles only after declaring `ClassLoader loader` and `Class<?> loadedType`. The lines query, in order:

1. The **concrete Java type** of the loader object.
2. The **Java superclass** of the loader type.
3. The **parent object** for delegation.
4. The **defining loader of a loaded class** (not necessarily equal to the `loader` attempting the load).
5. The **Thread Context Class Loader (TCCL)** of the current thread — a loader reference serving many discovery APIs, not necessarily the parent of `loader`.

The TCCL can be changed per thread by frameworks; for example, some overloads of `ServiceLoader.load(...)` use the context loader to locate providers. It **does not automatically change `getParent()`** of any loader instance.

**Do not confuse `getClassLoader()` with `getClass().getClassLoader()`:**

- For a loader object `myLoader`, `myLoader.getClass().getClassLoader()` returns **the loader that defined the Java class `MyLoader`**.
- For a domain class `MyFeature.class`, `MyFeature.class.getClassLoader()` returns the loader that defined **`MyFeature`**.
- `myLoader.getParent()` returns the parent object used for **delegation from `myLoader`**.

They all use the word "loader" yet refer to **three different objects/relationships**.

## 12. Common Programming Mistakes

| Mistake | Why it is wrong | Correct way to think about it |
| --- | --- | --- |
| "`PluginLoader extends ClassLoader`, so its parent is `ClassLoader.class`" | A parent is an **object**, whereas `ClassLoader.class` is an object describing a type | The parent is chosen by the constructor and inspected via `getParent()`. |
| "`PluginLoader extends HostLoader`, so the parent of a plugin instance is a host instance" | Inheritance only determines the superclass and inherited methods | You must pass the host object if you want delegation through it. |
| "`loader.getParent()` returns `null`, so the loader cannot load JDK classes" | `null` usually represents bootstrap lookup | However, platform-defined classes may be missing on modern JDKs. |
| "Two loaders of the same Java class therefore share the same loaded classes" | Each instance has its own class-loading state/namespace | Compare the actual `Class<?>` and defining loader. |
| "Loader `L` returned `Foo.class`, so `L` defined `Foo`" | The parent may have defined and returned it | Check `Foo.class.getClassLoader()`. |
| "Parent-first looks up the loader's Java superclass and calls `loadClass`" | Lookup does not follow the type hierarchy | It finds the **parent loader object** and calls the method on that object. |
| "`getParent() == null` means the root of the entire JVM with nowhere else to search" | Bootstrap is a built-in VM mechanism, and built-in/module loaders have their own rules | Consult the loader specification and JDK version. |
| "You can modify `parent` anytime to swap JARs at runtime" | There is no public setter, and runtime linkage/type identity have already been created | Design a separate loader/module layer lifecycle. |
| "Just override `loadClass` to change the order" | It is easy to break synchronization, caching, delegation, and package/JDK class rules | Usually override `findClass` and use the default `loadClass`, unless explicitly required. |
| "`Thread.currentThread().getContextClassLoader()` is `getParent()`" | TCCL and parent serve different purposes | Inspect both separately when debugging. |

### Errors Easily Misinterpreted When Reading Stack Traces

- `ClassNotFoundException`: a loader could not find the class with the requested name. Check **the loader instance actually being queried** and its parent chain; a class existing in the application's JAR does not mean the platform parent can see it.
- `NoClassDefFoundError`: the JVM needs the class but cannot define/use it; this may be due to a dependency or an earlier initialization error, so read `Caused by`.
- `ClassCastException` between two classes **with the same name**: this may be because two different defining loader instances created two runtime types. Do not fix this by changing the loader's `extends`.
- `LinkageError`: may stem from loading constraints, binary API mismatch, or other linking errors. Check loader identity, classpath/module path, and descriptors before guessing the cause.

Correctly identifying **the kind of relationship** usually shortens debugging more than just looking at the class loader name printed in logs.

## 13. A Summary Diagram Applied to a Plugin System

Suppose there are two objects of two different Java classes:

```text
                    JAVA TYPE HIERARCHY
                              Object
                                 │
                            ClassLoader
                              /     \
                     HostLoader   PluginLoader

                    RUNTIME OBJECT GRAPH
              platformLoader
                    ▲
                 parent
                    │
              hostInstance : HostLoader
                    ▲
                 parent
                    │
              pluginInstance : PluginLoader

                    LOADING EXAMPLE
pluginInstance.loadClass("java.lang.String")
       → hostInstance
       → platformLoader
       → bootstrap finds/defines String
       → returns the same String.class
```

In the diagram:

- The connection between `HostLoader` and `PluginLoader` in the type hierarchy goes through **`ClassLoader`**: they are two sibling Java subclasses.
- The arrows in the object graph are the result of **the parent reference passed to the constructor**.
- Calling `loadClass` on `pluginInstance` does not cause `String` to be defined by `PluginLoader`.
- In another lookup, if the parent cannot find a plugin class, only a `PluginLoader.findClass` with a real implementation can define that class itself.
- If a custom loader wants to use a different parent, simply choose a different parent object per the API contract; there is no need to change `extends`.

## 14. Self-Check Questions with Answers

**1. Can you create a `PluginLoader` whose parent is a `HostLoader` even though the two classes do not inherit from each other?** Yes. They both only need to be valid `ClassLoader`s; pass a `HostLoader` instance to the `PluginLoader(ClassLoader parent)` constructor.

**2. Can two instances of **the same Java class** `NamedLoader` form a parent chain?** Yes. For example, `new NamedLoader("second", first)` creates the relationship `second.getParent() == first`.

**3. Does `PluginLoader.class.getSuperclass()` change when a different parent is passed?** No. The superclass is determined by the `extends` declaration.

**4. If `PluginLoader extends HostLoader` but calls the no-argument constructor of `ClassLoader` across levels, is the parent automatically a `HostLoader` object?** No. The no-argument constructor of `ClassLoader` sets the system loader as the parent according to the API.

**5. Does `plugin.loadClass("java.lang.String")` returning `String.class` prove that `plugin` defined `String`?** No. The parent/bootstrap may have defined `String` and returned it.

**6. What do you call to find out the defining loader of `Foo.class`?** `Foo.class.getClassLoader()`; a `null` value typically represents bootstrap.

**7. What do you call to find out the superclass of the Java class containing the loader implementation?** `loader.getClass().getSuperclass()`; not `loader.getParent()`.

**8. Why is overriding `findClass` usually safer than overriding `loadClass` to add bytecode-reading capability?** It preserves the loaded-class check, parent-first delegation, and synchronization of the default `loadClass` implementation.

**9. Is the parent loader the superclass of the domain class that the loader is loading?** No. A loader parent is a relationship between **loader objects**; a domain class's superclass is a relationship between **Java types**.

**10. Can two loaders of the same subclass but different instances create two incompatible `plugin.Task` types?** Yes, if each loader defines its own runtime `plugin.Task` class; class identity depends on the binary name and the defining loader.

## 15. Authoritative Sources and Key Takeaways

- [Java SE 17 `ClassLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): constructors, `getParent()`, `loadClass`, `findClass`, and built-in loaders. The Javadoc explicitly states "**Each instance of ClassLoader has an associated parent class loader**".
- [Java SE 17 `Class` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getSuperclass()`, `getClassLoader()`, `isInstance()`.
- [Java Virtual Machine Specification 17, Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loader roles, type identity, initiating/defining loaders, and linkage.
- [JDK 17 `ServiceLoader` Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html): an example of an API that can use the thread context class loader, distinguished from parent delegation.

**The most reliable way to remember:**

> **`extends` connects *Java types*; `getParent()` connects *class loader objects*.** The constructor determines the parent object; the type declaration determines the superclass. The lookup delegation mechanism uses the object relationship, while Java inheritance determines the behavior a loader subclass receives from its superclass.

When encountering a classloading bug, always ask three separate questions: **"Which loader instance is being used?", "What is its parent *object*?", "Which loader defined the returned `Class<?>`?"** Only after answering those should you use the Java inheritance hierarchy to explain why a loader has specific methods or lookup behavior.
