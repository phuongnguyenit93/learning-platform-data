# 18.1 Role of `jdk.dynalink` in Dynamic Language Runtimes on the JVM

## 1. What problem does Dynalink solve?

When a dynamically typed language runs on the JVM, a source expression such as:

~~~text
user.name
~~~

can appear at a location where **the compiler does not yet know what type of object `user` will be**. On the first execution, `user` might be a Java bean with a `name` field; on the second, a Java bean with a `getName()` getter; on the third, an object of a custom-built language that stores properties in a dictionary. The same *property read* expression has a concrete access mechanism that depends on the **actual receiver at runtime**.

With static Java, the compiler usually knows the target early enough to emit `getfield` or `invokevirtual`. With a dynamic language, a good design needs to:

- Express the **abstract intent** of the expression: `GET PROPERTY "name"`, `SET ELEMENT`, `CALL`, `NEW`...
- **Select the right method handle** to perform the operation after seeing the runtime object.
- Attach the target to a **relinkable call site**.
- Automatically check the validity condition of the old target using a **guard**; when the object changes type or assumptions become invalid, request relinking.
- Optimize the case of repeatedly encountering the same object shape, avoiding reflection and type branching on every call.
- Allow multiple **object models** and **type conversion rules** to coexist, especially when interoperating between a dynamic language and Java.

The **`jdk.dynalink`** module is a library in the JDK, available since Java 9, that supports these exact high-level linking tasks. It is built on top of `java.lang.invoke` and typically works in conjunction with the `invokedynamic` bytecode.

**Short definition:** Dynalink is a **library for dynamically linking high-level operations on objects**, not a scripting language, a complete interpreter, a Java source compiler, a bytecode generator, or a mechanism to replace JVM method dispatch. It provides a *linker architecture* so that a dynamic language runtime can define operations itself and learn how to perform them for runtime receivers.

## 2. Where does Dynalink sit in JVM dynamic invocation?

Distinguish three layers:

| Layer | Provides | Role |
| --- | --- | --- |
| **JVM/`invokedynamic`** | Instruction, bootstrap method protocol, `CallSite` | When resolving a call site for the first time, the JVM invokes the bootstrap method; subsequent invocations use the target provided by the call site |
| **`java.lang.invoke`** | `MethodHandle`, `MethodType`, `CallSite`, `MethodHandles.Lookup`, combinators | Represent, combine, convert types, and execute target method handles |
| **`jdk.dynalink`** | `Operation`, `DynamicLinkerFactory`, `DynamicLinker`, `GuardingDynamicLinker`, `GuardedInvocation`, `RelinkableCallSite` | Understand high-level operations and select, guard, cache, and relink targets appropriate for runtime objects |

Common diagram of a dynamic language compiler:

~~~text
Language source:
    user.name
         |
         v
Language compiler defines operation:
    GET:PROPERTY:name
         |
         v
Emits invokedynamic site: (Object)Object
         |
         v
JVM calls the language runtime's bootstrap method
         |
         v
DynamicLinker.link(RelinkableCallSite)
         |
         v
Site initially holds a relink-and-invoke fallback
         |
         v
Actual execution: receiver = Person("Ada")
         |
         v
GuardingDynamicLinkers inspect LinkRequest
         |
         v
BeansLinker/custom linker returns GuardedInvocation
         |
         v
Install target + guard + fallback into the call site
         |
         v
Read property, return "Ada"
         |
         +-- Receiver matches guard? -> fast-path call to linked target
         |
         +-- Guard mismatch? -> request relink with new receiver
~~~

**Important:** `jdk.dynalink` **does not automatically turn every Java expression into `invokedynamic`**. The compiler or interpreter of **the language being built** must create `CallSiteDescriptor`/`Operation` and choose when to call Dynalink. If the compiler generates a Java class file with the `invokedynamic` opcode, the bootstrap method can call `DynamicLinker.link(...)`; if building an interpreter, one can also create call sites from Java source to serve an AST interpreter without generating new instructions.

## 3. Modules, packages, and core components

Java 17 places the Dynalink API in the **named JDK module `jdk.dynalink`**. Important packages:

| Package | Components | When do you use it? |
| --- | --- | --- |
| `jdk.dynalink` | `DynamicLinkerFactory`, `DynamicLinker`, `CallSiteDescriptor`, `Operation`, `StandardOperation`, `StandardNamespace`, `NamedOperation`, `NamespaceOperation`, `RelinkableCallSite` | Designing operations, building and linking dynamic sites |
| `jdk.dynalink.support` | `SimpleRelinkableCallSite`, `ChainedCallSite` | Choosing the caching strategy at the site |
| `jdk.dynalink.linker` | `GuardingDynamicLinker`, `TypeBasedGuardingDynamicLinker`, `LinkRequest`, `LinkerServices`, `GuardedInvocation`, `GuardingDynamicLinkerExporter` | Creating linkers for custom language object models, normalizing targets/guards, cross-language interoperability |
| `jdk.dynalink.beans` | `BeansLinker`, `StaticClass` | Java interop: fields, getters/setters, methods, arrays, List, Map, constructors |

If the program is placed on the **class path** with a full JDK, the examples below use the above imports and have been run in a test environment. If the code resides in a **named module**, module-info needs to declare the dependency:

~~~java
module my.dynamic.runtime {
    requires jdk.dynalink;
}
~~~

This is a **module-info snippet**, not a standalone runnable program. `requires` makes your module able to read the module API, **it does not automatically open all packages of the application to reflection/BeansLinker**. Java access control and JPMS still apply.

Official JavaDoc API: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html

### Roles of the main objects

- **`DynamicLinkerFactory`:** configures prioritized linkers, fallback linkers, the class loader used to discover exporters, and relink/sync policies; then calls `createLinker()`.
- **`DynamicLinker`:** coordinates linkers and attaches the **relink-and-invoke** mechanism to a call site via `link(...)`.
- **`CallSiteDescriptor`:** stores the `Lookup`, `Operation`, and `MethodType` of the site so linkers know “who is asking, what they want to do, and what the type contract is”.
- **`RelinkableCallSite`:** contract for a site that can receive relinked targets. Two built-in classes are `SimpleRelinkableCallSite` and `ChainedCallSite`.
- **`GuardingDynamicLinker`:** a handler that knows how to link operations for certain receiver types/language logic.
- **`GuardedInvocation`:** a target MethodHandle accompanied by a guard condition and optional invalidation mechanisms such as `SwitchPoint`.
- **`LinkRequest`:** information for a specific link request, containing the descriptor and current arguments.
- **`LinkerServices`:** type conversion services and linking utilities provided by Dynalink.
- **`BeansLinker`:** linker for Java objects following common public Java behavior, serving as the foundation for interop.

## 4. Representing high-level operations with `Operation`

A language compiler should not encode all logic into Java method names. Dynalink allows representing an **operation** as a value:

~~~java
Operation op = StandardOperation.GET
    .withNamespace(StandardNamespace.PROPERTY)
    .named("name");
~~~

This is a **snippet**, requiring `jdk.dynalink.*` imports. `StandardOperation.GET` means “read”; `PROPERTY` states we are reading the **property namespace**; `named("name")` fixes the property name.

### Standard operations

| Operation | Meaning | Common high-level signature |
| --- | --- | --- |
| `GET` | Get property/element/method value by namespace | `(receiver, name) -> value`, or `(receiver) -> value` if name is `named(...)` |
| `SET` | Write property/element | `(receiver, name, value) -> void`, or `(receiver, value) -> void` if name is fixed |
| `REMOVE` | Remove element/entry by namespace | `(receiver, name) -> void` or `(receiver) -> void` if name is fixed |
| `CALL` | Invoke callable/dynamic method | `(callable, receiver, args...) -> result` |
| `NEW` | Invoke constructor-like object | `(constructor, args...) -> newObject` |

Note that `GET` and `SET` **must have a namespace** according to the Dynalink contract. Do not specify bare `StandardOperation.GET` and assume it means a Java bean getter; at least `PROPERTY` or the appropriate `ELEMENT`/`METHOD` is required.

### Namespaces describe the access space

| Namespace | Example meaning |
| --- | --- |
| `StandardNamespace.PROPERTY` | `obj.color`, Java bean getter/field, or language object property |
| `StandardNamespace.ELEMENT` | `array[i]`, `list[i]`, `map[key]` |
| `StandardNamespace.METHOD` | Retrieve a callable representing a method, which can later be invoked via `CALL` |

A language might allow `obj["name"]` to try property first and then element. In that case, use `withNamespaces(PROPERTY,ELEMENT)` to express **multiple namespaces in order**, instead of writing repetitive `if` logic in the interpreter. A specific linker decides which namespaces it supports and how to handle missing members.

### `NamedOperation` differs from a runtime-passed name

Two ways of representing it:

~~~text
GET PROPERTY with fixed name:
    operation = GET.withNamespace(PROPERTY).named("name")
    site type = (Object)Object

GET PROPERTY with runtime-supplied name:
    operation = GET.withNamespace(PROPERTY)
    site type = (Object,Object)Object
                   ^    ^
                receiver key
~~~

`NamedOperation` **removes the name parameter from the signature at the site** for GET/SET. This can optimize repeated operations with the same property name. However, **the compiler must ensure the right name and the right site descriptor**, not blindly replace a site taking a runtime key with a named site while still passing an extra argument.

For `CALL` and `NEW`, naming via `NamedOperation` mainly aids diagnostics and **does not automatically remove parameters from the signature**; check the exact contract of each operation.

### Operation names in bytecode do not have a built-in parser

A bootstrap method can receive the String `"GET:PROPERTY:name"` and parse it into an operation itself, but `jdk.dynalink` **does not enforce a single name encoding syntax**. Each language runtime is responsible for defining and validating how metadata/names are converted into `Operation`.

Example from JavaDoc:
`StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("color")`.

## 5. Connecting a site: `DynamicLinkerFactory`, `DynamicLinker`, `CallSiteDescriptor`

Basic procedure:

~~~java
DynamicLinker linker = new DynamicLinkerFactory().createLinker();

CallSiteDescriptor descriptor = new CallSiteDescriptor(
    MethodHandles.lookup(),
    StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("name"),
    MethodType.methodType(Object.class, Object.class)
);

CallSite site = linker.link(
    new SimpleRelinkableCallSite(descriptor)
);
~~~

This is a **snippet**; to compile, it needs imports `java.lang.invoke.*`, `jdk.dynalink.*`, `jdk.dynalink.support.SimpleRelinkableCallSite`. A complete program is in section 6.

**Three pieces of information in a descriptor:**

1. **`Lookup`:** caller context for performing member lookups; not a license to bypass Java access checks.
2. **`Operation`:** name/namespace of the language operation.
3. **`MethodType`:** signature of the call site; for example `(Object)Object` takes one Object receiver and returns an Object.

`DynamicLinker.link(...)` takes a `RelinkableCallSite`. It **installs an initial target so that on execution it attempts to link according to the actual arguments**. Do not interpret calling `link(...)` as always knowing the receiver type in advance; the receiver might not even exist until the first invocation.

**A distinction in the Java type system:** `RelinkableCallSite` is a **separate interface**, not a subclass of `java.lang.invoke.CallSite`. Built-in implementations like `SimpleRelinkableCallSite` and `ChainedCallSite` are also subclasses of `CallSite`, so to call `dynamicInvoker()`, use a variable with static type `CallSite` or the concrete class. Incorrect snippet:

~~~java
RelinkableCallSite site = new SimpleRelinkableCallSite(descriptor);
// site.dynamicInvoker(); // DOES NOT COMPILE: the interface does not have this method
~~~

This is a snippet illustrating a compiler error, **not standalone runnable code**. It can be fixed as `CallSite site = linker.link(new SimpleRelinkableCallSite(...))` or by keeping the concrete type; the `dynamicInvoker()` method belongs to `CallSite`.

## 6. Example 1 — Java objects: field, getter, and Map element

`DynamicLinkerFactory` by default creates a linker with **`BeansLinker`** as a fallback, allowing operations on many ordinary Java objects without having to write your own `GuardingDynamicLinker`.

Save **`DynalinkBeansDemo.java`**:

~~~java
import java.lang.invoke.*;
import java.util.*;
import jdk.dynalink.*;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkBeansDemo {
    public static class Person {
        public String name;

        public Person(String name) {
            this.name = name;
        }
    }

    public static class Contact {
        private final String name;

        public Contact(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinker linker = new DynamicLinkerFactory().createLinker();

        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("name");

        CallSiteDescriptor d = new CallSiteDescriptor(
                MethodHandles.lookup(), op,
                MethodType.methodType(Object.class, Object.class));

        CallSite site = linker.link(
                new SimpleRelinkableCallSite(d));
        MethodHandle getter = site.dynamicInvoker();

        System.out.println("siteType=" + site.type());

        System.out.println("field=" + (Object)
                getter.invokeExact((Object) new Person("Ada")));

        System.out.println("getter=" + (Object)
                getter.invokeExact((Object) new Contact("Lin")));

        System.out.println("fieldAgain=" + (Object)
                getter.invokeExact((Object) new Person("Binh")));

        Operation elementOp = StandardOperation.GET
                .withNamespace(StandardNamespace.ELEMENT)
                .named("language");

        CallSite mapSite = linker.link(
                new SimpleRelinkableCallSite(
                    new CallSiteDescriptor(
                        MethodHandles.lookup(),
                        elementOp,
                        MethodType.methodType(
                            Object.class, Object.class))));

        Object map = Map.of("language", "Java");
        System.out.println("map=" + (Object)
                mapSite.dynamicInvoker().invokeExact(map));
    }
}
~~~

Run on JDK 17+:

~~~sh
javac --release 17 DynalinkBeansDemo.java
java DynalinkBeansDemo
~~~

**Verified stdout:**

~~~text
siteType=(Object)Object
field=Ada
getter=Lin
fieldAgain=Binh
map=Java
~~~

**Explanation:**

- `Person.name` is a `public field`, whereas `Contact.name` is a `private field` with a public getter `getName()`. `BeansLinker` can satisfy **the same GET PROPERTY name** through two different public access paths.
- `site.type()` is always `(Object)Object`, even though the runtime receiver type changes between `Person` and `Contact`.
- `SimpleRelinkableCallSite` maintains a **monomorphic** cache; when the receiver no longer satisfies the previous target's guard, it relinks. There is no need to manually branch `if (user instanceof Person)` in Java source on every call.
- `Map` uses the **ELEMENT namespace**: `Map.of("language","Java")` has the key `"language"`, so `GET ELEMENT language` returns `"Java"`.
- `getter.invokeExact((Object) value)` statically casts the argument to Object and casts the return to Object; this is **important for `MethodHandle.invokeExact`**. Calling exact with a String return cast or a Person static argument type when the site is `(Object)Object` can result in `WrongMethodTypeException`.
- The example uses the site on a single thread after linking succeeds; do not infer the exact number of linker callbacks the JVM invokes solely from stdout, as that is a cache detail. The example checking the link count of a custom linker is in section 7.

`BeansLinker` also supports Java arrays, `List`, `Map`, public getters/setters, public methods, and `StaticClass` for calling static members/constructors according to the API rules. Do not assume all private members can be read via BeansLinker.

## 7. Why is a custom `GuardingDynamicLinker` needed?

A dynamic language may have its own object model: objects as maps of field values, prototype chains, proxies, shape tables, or property tables that do not correspond to Java beans. When encountering such objects, `BeansLinker` cannot know on its own what `obj.name` means.

The solution is to create a **language-specific linker**:

~~~text
LinkRequest(op=GET PROPERTY "name", receiver=DynRecord)
                     |
                     v
Language's GuardingDynamicLinker:
    - Check if receiver belongs to its object model?
    - Check if operation is supported?
    - Create corresponding target MethodHandle
    - Create guard checking assumption
                     |
          +----------+----------+
          |                     |
      Has handler          Does not handle
          |                     |
          v                     v
    GuardedInvocation        return null
          |                     |
          v                     v
     Dynalink cache       Next linker / BeansLinker
~~~

`GuardingDynamicLinker.getGuardedInvocation(LinkRequest,LinkerServices)` returns:

- A `GuardedInvocation` when it understands the operation and can create a target.
- **`null`** when the linker **does not handle** this receiver/operation, yielding to the next linker.
- An exception when linking encounters an unrecoverable error according to the contract.

`GuardedInvocation` can contain a **guard**, a target, a `SwitchPoint` for invalidation, or exception types that signal relinking according to the API. In the example below, only an `instanceof DynRecord` guard is used to focus on the core idea.

### Example 2 — Custom object model + monomorphic/polymorphic cache

Save **`DynalinkCustomDemo.java`**:

~~~java
import java.lang.invoke.*;
import java.util.*;
import jdk.dynalink.*;
import jdk.dynalink.linker.*;
import jdk.dynalink.support.*;

public class DynalinkCustomDemo {
    public static class DynRecord {
        final Map<String, Object> values;

        DynRecord(Map<String, Object> values) {
            this.values = values;
        }
    }

    public static class JavaBean {
        private final String name;

        public JavaBean(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public static Object get(DynRecord r, String key) {
        return r.values.get(key);
    }

    public static boolean isDynRecord(Object obj) {
        return obj instanceof DynRecord;
    }

    static class RecordLinker implements GuardingDynamicLinker {
        int customLinks;

        @Override
        public GuardedInvocation getGuardedInvocation(
                LinkRequest request,
                LinkerServices services) throws Exception {

            if (!(request.getReceiver() instanceof DynRecord)) {
                return null;
            }

            Operation operation =
                    request.getCallSiteDescriptor().getOperation();
            Object key = NamedOperation.getName(operation);
            Operation unwrapped =
                    NamedOperation.getBaseOperation(operation);

            if (!(key instanceof String) ||
                !NamespaceOperation.contains(
                    unwrapped, StandardOperation.GET,
                    StandardNamespace.PROPERTY)) {
                return null;
            }

            customLinks++;

            MethodHandles.Lookup lookup = MethodHandles.lookup();
            MethodHandle mh = lookup.findStatic(
                    DynalinkCustomDemo.class, "get",
                    MethodType.methodType(
                        Object.class, DynRecord.class, String.class));

            MethodHandle target = MethodHandles.insertArguments(
                    mh, 1, (String) key)
                    .asType(request.getCallSiteDescriptor().getMethodType());

            MethodHandle guard = lookup.findStatic(
                    DynalinkCustomDemo.class, "isDynRecord",
                    MethodType.methodType(boolean.class, Object.class));

            return new GuardedInvocation(target, guard);
        }
    }

    static void run(boolean chain) throws Throwable {
        RecordLinker custom = new RecordLinker();

        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setPrioritizedLinker(custom);
        DynamicLinker linker = factory.createLinker();

        Operation operation = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("name");

        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                MethodHandles.lookup(), operation,
                MethodType.methodType(Object.class, Object.class));

        CallSite site = chain
                ? new ChainedCallSite(descriptor)
                : new SimpleRelinkableCallSite(descriptor);

        linker.link((RelinkableCallSite) site);
        MethodHandle mh = site.dynamicInvoker();

        Object one = mh.invokeExact(
                (Object) new DynRecord(Map.of("name", "neo")));
        Object two = mh.invokeExact(
                (Object) new JavaBean("Ada"));
        Object three = mh.invokeExact(
                (Object) new DynRecord(Map.of("name", "trinity")));

        System.out.println((chain ? "chain" : "simple") +
                "=" + one + "," + two + "," + three);
        System.out.println((chain ? "chainLinks" : "simpleLinks") +
                "=" + custom.customLinks);
    }

    public static void main(String[] args) throws Throwable {
        run(false);
        run(true);
    }
}
~~~

~~~sh
javac --release 17 DynalinkCustomDemo.java
java DynalinkCustomDemo
~~~

**Stdout of this sequential program:**

~~~text
simple=neo,Ada,trinity
simpleLinks=2
chain=neo,Ada,trinity
chainLinks=1
~~~

**How to read the program:**

1. The runtime defines `DynRecord` with a `Map<String,Object>` dictionary. This is a minimal object model, different from JavaBeans; to read `name`, it calls `get(DynRecord,String)`.
2. `RecordLinker` is placed in the **prioritized list** via `setPrioritizedLinker`. When the receiver is `DynRecord`, it handles it; for `JavaBean`, it returns null so the default `BeansLinker` handles it next.
3. `request.getCallSiteDescriptor().getOperation()` describes `GET PROPERTY name`. Because the operation was `named(...)`, it is a **`NamedOperation` wrapping a `NamespaceOperation`**. `NamedOperation.getName(...)` extracts the key and `NamedOperation.getBaseOperation(...)` **unwraps the NamedOperation layer** before calling `NamespaceOperation.contains(...)`. If `NamespaceOperation.contains` were called directly on the outer NamedOperation, this condition would not match and the custom linker could skip the right operation.
4. The initial method handle `get(DynRecord,String):Object` has the key `"name"` bound via `insertArguments` to become `(DynRecord)Object`; `asType((Object)Object)` adapts the receiver for the site's descriptor.
5. The guard `isDynRecord(Object):boolean` ensures the above target is only used when the receiver belongs to the DynRecord object model. When the guard does not match, the relink callback gets a chance to select another linker.
6. `SimpleRelinkableCallSite` holds only **one guarded invocation**: the first DynRecord encounter links once; encountering JavaBean replaces the target; encountering DynRecord again has to call the custom linker again ⇒ `simpleLinks=2`.
7. `ChainedCallSite` holds **a chain of guarded invocations** (default maximum of 8). After encountering DynRecord and JavaBean, the third DynRecord can hit the old target in the chain ⇒ `chainLinks=1` for this sequence.

**Note:** the counts above are the number of times **the custom linker created a GuardedInvocation**, not the number of times the JVM called the `get` method. Do not use this example to prove `ChainedCallSite` is always faster. If there are too many shapes, long guard chains, invalidations, contention, or memory pressure, the best strategy may differ.

### Limitations of the guard in the example

`instanceof DynRecord` is sufficient **only because** all `DynRecord` instances in the example read fields from the map using the same `get` method. If a runtime has multiple **shapes/versions/prototypes** with different layouts, a class-only guard may not be enough. You need to additionally guard the shape's identity/version or use `SwitchPoint` to invalidate the target when assumptions change. Caching with incorrect guard conditions leads to returning wrong data, a logic bug harder to detect than an exception.

## 8. Bootstrap method: where `invokedynamic` hands off work to Dynalink

In a class file generated by a language compiler, an instruction can carry a custom name:

~~~text
invokedynamic "GET:PROPERTY:name" (Object)Object
~~~

When resolving the site, the JVM provides `MethodHandles.Lookup caller`, `String name`, and `MethodType type` to the BSM. The BSM **parses name itself** into an `Operation`, creates a `CallSiteDescriptor`, and delegates to `DynamicLinker.link(...)`.

Here is a simple BSM pattern:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType type) {
    Operation op = parseOperation(name);
    return LINKER.link(new SimpleRelinkableCallSite(
            new CallSiteDescriptor(caller, op, type)));
}
~~~

**This is a snippet, not standalone runnable**, because `LINKER` and `parseOperation` are not yet declared. The complete example below defines them.

### Example 3 — Calling a BSM-shaped method directly to observe the contract

Save **`DynalinkBootstrapDemo.java`**:

~~~java
import java.lang.invoke.*;
import jdk.dynalink.*;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkBootstrapDemo {
    public static class Item {
        private final String name;

        public Item(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    private static final DynamicLinker LINKER =
            new DynamicLinkerFactory().createLinker();

    public static CallSite bootstrap(
            MethodHandles.Lookup caller,
            String name,
            MethodType type) {
        if (!name.equals("GET:PROPERTY:name")) {
            throw new IllegalArgumentException("Unsupported: " + name);
        }

        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("name");

        return LINKER.link(new SimpleRelinkableCallSite(
                new CallSiteDescriptor(caller, op, type)));
    }

    public static void main(String[] args) throws Throwable {
        CallSite site = bootstrap(
                MethodHandles.lookup(),
                "GET:PROPERTY:name",
                MethodType.methodType(Object.class, Object.class));

        System.out.println("type=" + site.type());
        System.out.println("value=" + (Object)
                site.dynamicInvoker().invokeExact(
                    (Object) new Item("demo")));

        try {
            bootstrap(MethodHandles.lookup(),
                "GET:PROPERTY:unknown",
                MethodType.methodType(Object.class, Object.class));
        } catch (IllegalArgumentException ex) {
            System.out.println("unsupported=" +
                    ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~sh
javac --release 17 DynalinkBootstrapDemo.java
java DynalinkBootstrapDemo
~~~

**Stdout:**

~~~text
type=(Object)Object
value=demo
unsupported=IllegalArgumentException
~~~

**Distinguishing the demo from actual bytecode:** this program **calls `bootstrap(...)` via regular Java source** to test the wiring between BSM, descriptor, and Dynalink. It **does not itself emit an `invokedynamic` instruction**. In a real system, the bytecode generator must emit `CONSTANT_InvokeDynamic` and `BootstrapMethods` pointing to the BSM; the JVM is what calls the BSM at linking time. Calling the BSM directly is useful for unit testing a compiler/runtime, but does not replace testing `invokedynamic` bytecode.

### `DynamicLinker.link` is not the same as `MethodHandle.invokeExact`

- `link(...)` **sets up the call site to know how to link/relink**.
- `site.dynamicInvoker()` is a MethodHandle representing a call through the site.
- `invokeExact(...)` **executes** through the site with the exact descriptor, at which point the target may link for the first time or relink.

At an `(Object)Object` site, the static types of both the argument and the result of `invokeExact` must be `Object`. That is why the example writes `(Object) new Item(...)` and casts the return `(Object)`; if the return were cast to `String`, `WrongMethodTypeException` could occur **even before the target is called**.

## 9. When nobody can link: diagnosing errors

Dynalink may receive an invalid receiver for the described operation. If no linker can produce a matching `GuardedInvocation`, the site will throw **`NoSuchDynamicMethodException`** on invocation. This is a failure of **dynamic operation resolution**, unlike Java Reflection's `NoSuchMethodException`.

### Example 4 — Wrong return type and no matching linker

Save **`DynalinkErrorsDemo.java`**:

~~~java
import java.lang.invoke.*;
import jdk.dynalink.*;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkErrorsDemo {
    public static class Bean {
        public String color = "blue";
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinker linker =
                new DynamicLinkerFactory().createLinker();

        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("color");

        CallSite site = linker.link(
                new SimpleRelinkableCallSite(
                    new CallSiteDescriptor(
                        MethodHandles.lookup(), op,
                        MethodType.methodType(
                            Object.class, Object.class))));

        MethodHandle getter = site.dynamicInvoker();
        Object bean = new Bean();

        System.out.println("exists=" +
                (Object) getter.invokeExact(bean));

        try {
            String unused = (String) getter.invokeExact(bean);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongReturn=" +
                    ex.getClass().getSimpleName());
        }

        try {
            Object unknown = new Object();
            Object unused = getter.invokeExact(unknown);
            System.out.println("unknown=" + unused);
        } catch (NoSuchDynamicMethodException ex) {
            System.out.println("unknown=" +
                    ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~sh
javac --release 17 DynalinkErrorsDemo.java
java DynalinkErrorsDemo
~~~

**Stdout:**

~~~text
exists=blue
wrongReturn=WrongMethodTypeException
unknown=NoSuchDynamicMethodException
~~~

Two independent issues:

1. `WrongMethodTypeException` is a mismatch with **`MethodHandle.invokeExact`**: the site returns Object while the source asks for String. Fix the call site/cast or use `invoke` with appropriate adaptation; this error **does not prove** Dynalink failed to find `Bean.color`.
2. `NoSuchDynamicMethodException` occurs when the site receives `new Object()` which has no `color` property and no linker can handle it. The site still exists; the runtime can define its own policy for missing properties (return null, create a sentinel object, throw a specific exception...), but without an appropriate fallback, the Dynalink exception is the expected result.

**Do not wrap every operation in `try/catch(NoSuchDynamicMethodException)` and silently return null** if the language distinguishes between a non-existent member and a member with a null value. This is a language semantic decision that needs to be consistently differentiated in the linker/fallback.

## 10. Guard, relink, and inline cache mechanisms

A `GuardedInvocation` wraps:

~~~text
target: (Object)Object  // method handle performing the operation
guard:  (Object)boolean // condition that target is still valid
fallback: relink-and-invoke managed by DynamicLinker
~~~

On each call:

~~~text
New receiver passes through site
            |
            v
      Guard matches?
        /       \
      Yes        No
      |           |
      v           v
  Call target   Relink callback
                  |
                  v
           GuardingDynamicLinker(s)
                  |
                  v
        New GuardedInvocation
                  |
                  v
         Site updates target
                  |
                  v
        Attempt to perform operation
~~~

**This is a conceptual diagram, not a guarantee of specific instruction ordering**. The JVM/JIT may inline/optimize method handles. The goal is to keep **guard conditions + fallback** correct.

### Monomorphic and polymorphic caches

- **`SimpleRelinkableCallSite`:** one guarded invocation at a time. Receiver no longer matches ⇒ replace the current linkage. Suitable for sites that mostly see a single shape/type.
- **`ChainedCallSite`:** stores a chain of guarded invocations, **up to eight** by default, newest first. A previously seen receiver can hit a guard in the chain without creating a new linkage. In return, longer chains incur guard check costs.
- **`RelinkableCallSite` interface:** defines how to receive `relink(...)` and `resetAndRelink(...)`; you can implement your own custom caching strategy when the two built-in classes do not fit.
- **`DynamicLinkerFactory.setUnstableRelinkThreshold(...)`:** helps mark a site as unstable after a number of relinks so linkers can choose an appropriate policy, such as a generic target.
- **`DynamicLinkerFactory.setSyncOnRelink(...)`:** controls calling `MutableCallSite.syncAll(...)` when updating a site, affecting visibility across threads.

Do not choose “PIC is always better” or “monomorphic is always better” based solely on the number of classes in the entire program. What matters is the **distribution of types at each site**, frequency of change, speed of guard checks, shape mutations, and memory pressure. For megamorphic sites (very many types), a generic strategy or profile-optimized cache is needed.

### Invalidation via `SwitchPoint`

For runtimes with mutable object shapes/prototypes, a guard checking only `instanceof` is usually too weak. Dynalink supports `GuardedInvocation` with `SwitchPoint` or exception types as invalidation signals so the relink callback can regenerate the target after outdated assumptions.

For example, prototype data is modified: the old target used to return a field at slot 2, but the new shape moves the field to slot 4. If the guard remains true without invalidation, the program can **silently return wrong results**. Therefore, design *guard validity* before optimizing for speed.

## 11. Configuring the linker pipeline and multi-language interoperability

`DynamicLinkerFactory` allows configuring three groups of linkers:

~~~text
1. Prioritized linkers installed by the runtime
          |
          v
2. Autodiscovered linkers from other language runtimes
          |
          v
3. Fallback linkers (defaults to including BeansLinker)
          |
          v
     Nobody handles => error / fallback policy
~~~

In section 7, `RecordLinker` was added using `setPrioritizedLinker(custom)` so it receives `DynRecord` first. When it does not recognize the receiver, it returns null; `BeansLinker` resolves the Java bean. **A factory does not have only one linker**; it is precisely the coordination of multiple linkers that makes Dynalink useful for mixed languages.

### Cross-language interop

`GuardingDynamicLinkerExporter` is the API for a language runtime to export its guarding linkers for other runtimes to autodiscover via the service mechanism. `DynamicLinkerFactory.setClassLoader(...)` affects discovering exporters, typically via the runtime/context's class loader. A multi-scripting-language system can configure each runtime with the appropriate class loader so linkers from other languages are included in the pipeline.

**Do not claim that simply importing `jdk.dynalink` makes all languages automatically understand each other's objects**. Each language runtime needs to:

- Write an exporter/linker for its object model.
- Package and publish service providers in the right class loader/module.
- Define how values and types are converted for interop.
- Agree on operation namespaces and semantics.
- Arbitrate prioritized/fallback linkers to avoid one linker mistakenly claiming another language's object.

### `LinkerServices`

Besides `MethodHandle.asType`, Dynalink provides `LinkerServices` for linkers to request **type adaptations** in the context of converters supported by the runtime, as well as other services. Do not assume converting from a custom language object to a Java type is always like standard primitive boxing/reference casting; custom language runtimes may define different conversions.

A custom linker should produce a `GuardedInvocation` whose type is compatible with the descriptor and use `LinkerServices` when it wants to respect a unified conversion policy. In the learning example, `asType((Object)Object)` suffices because it only adapts the reference receiver.

## 12. JPMS and Java access still apply with `BeansLinker`

Having `requires jdk.dynalink` allows **calling the Dynalink API** from a named module. However, a `GET PROPERTY` operation on a public bean in a **non-exported** package may fail to link due to Java module encapsulation. Dynalink is not a privilege to break visibility.

### Minimal named module example

Structure:

~~~text
src/
  dyn.demo/
    module-info.java
    app/Main.java
~~~

File **`src/dyn.demo/module-info.java`**:

~~~java
module dyn.demo {
    requires jdk.dynalink;
    exports app;
}
~~~

File **`src/dyn.demo/app/Main.java`**:

~~~java
package app;

import java.lang.invoke.*;
import jdk.dynalink.*;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class Main {
    public static class Bean {
        public String name = "module-ok";
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinker linker = new DynamicLinkerFactory().createLinker();
        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("name");

        CallSite site = linker.link(
                new SimpleRelinkableCallSite(
                    new CallSiteDescriptor(
                        MethodHandles.lookup(), op,
                        MethodType.methodType(
                            Object.class, Object.class))));

        System.out.println("module=" +
                Main.class.getModule().getName());
        System.out.println("property=" + (Object)
                site.dynamicInvoker().invokeExact((Object) new Bean()));
    }
}
~~~

From the directory containing `src`:

~~~sh
javac --release 17 --module-source-path src -d mods -m dyn.demo
java --module-path mods -m dyn.demo/app.Main
~~~

**Stdout when package `app` is exported:**

~~~text
module=dyn.demo
property=module-ok
~~~

In the verified configuration, if `exports app;` is removed while keeping only `requires jdk.dynalink;`, reading the property via `BeansLinker` **fails to link** and the site throws `NoSuchDynamicMethodException`. `requires` only establishes module readability; it does not automatically open the package for access from the linker library. The main point of the example is to demonstrate that **reading the Dynalink API is different from permission to see bean members**.

**Design choice:** do not indiscriminately export entire internal packages just for scripting convenience. If the runtime needs to access non-public resources, provide a well-designed public API/DTO or a custom linker that respects `Lookup`/JPMS; do not put `--add-opens` into deployment as a default “bypass” without evaluating security boundaries.

## 13. What Dynalink does not do for a language runtime

Dynalink **solves linkage**, it does not replace the entire language implementation.

| Responsibility | Who handles it? | Notes |
| --- | --- | --- |
| Parse tokens, grammar, build AST | Language compiler/parser | Dynalink does not parse scripts |
| Check language semantics, scope, closures | Compiler/interpreter | Decides operation names, object models, and results |
| Emit Java `invokedynamic` bytecode | Bytecode generator/language | Dynalink is not a class file emitter |
| Define object representation | Language runtime | Object shapes, dynamic properties, prototypes |
| Link operations to MethodHandles | **Dynalink with custom/Beans linkers** | Core value of the library |
| Cache/guard/relink at site | **Dynalink + RelinkableCallSite implementation** | Has monomorphic/polymorphic strategies |
| Language-specific type conversions | Runtime + `LinkerServices`/linkers | Needs clear semantics |
| Run native JVM bytecode and JIT | JVM | Dynalink relies on Java method handles |
| Run scripts safely in a sandbox | **Outside Dynalink's scope** | Needs isolation, resource limits, and trust policies |
| Grant access to private/JDK internals | Java/JPMS/access control | Dynalink does not bypass permissions |

Therefore, putting `jdk.dynalink` on the classpath does not immediately create a dynamic language. First, you must design **operation semantics**: if reading a property with a missing key, does it return `null`, `undefined`, or throw an error? Does Number + String coerce? How do setters work on immutable objects? When calling an overloaded method, what rules does overload resolution follow? Those choices belong to the language runtime.

## 14. Designing a dynamic language runtime: step by step

Suppose you want to support expressions `obj.color` and `obj["color"]` in a DSL. A minimal workflow:

1. **Define semantics:** Do `GET PROPERTY` and `GET ELEMENT` have the same meaning or different? If a lookup does not exist, use a sentinel or an exception?
2. **Standardize operations:** use `StandardOperation.GET.withNamespace(PROPERTY).named("color")` for sites with a statically known name; use `GET.withNamespace(ELEMENT)` taking a runtime key for subscripts.
3. **Define site descriptors:** operation name, `Lookup`, type `(Object)Object` or `(Object,Object)Object` depending on runtime inputs. Be careful with the return type of `MethodHandle.invokeExact`.
4. **Choose object model:** use Java beans/Map if they match language semantics; if you have `DynRecord`/prototypes/shapes, a custom `GuardingDynamicLinker` is needed.
5. **Create linker:** add custom linkers via `setPrioritizedLinker`; keep `BeansLinker` fallback if Java interop is desired; consider custom type conversions.
6. **Choose call site strategy:** `SimpleRelinkableCallSite` if the site is stable on one shape; `ChainedCallSite` if the site sees a few shapes; benchmark to decide.
7. **Integrate interpreter/bytecode:** the interpreter stores a `CallSite` in each AST node, or the bytecode generator emits `invokedynamic` with a BSM calling Dynalink.
8. **Guard every important assumption:** not just class, also shape/version/prototype, visibility, and invalidate when changed.
9. **Decide error policy:** if a field/method is missing, create a fallback returning/throwing according to semantics; avoid catching all errors into null.
10. **Design isolation/security:** do not let scripts automatically access Java internals/reflective APIs disallowed by language policy; control exposed class loaders, modules, and libraries.
11. **Measure behavior:** relink count/site, guard hit/miss, shapes/site, latency, allocation, and memory/cache size. Do not benchmark only a single receiver type.
12. **Test multi-type/multi-threaded:** receiver changing types, property values changing, object model invalidation, concurrent relinking, and startup; verify correctness before performance.

### Controlled development scenario

Start with a `GET PROPERTY name` site for two Java bean types as in example 1. Then add custom `DynRecord` (example 2). Finally, add a compiler emitting `invokedynamic` (example 3 explains bootstrap wiring). Going from simple to complex helps distinguish three classes of bugs: wrong operation semantics, wrong linkers/guards, and wrong bytecode/bootstrap descriptors.

## 15. Diagnosing errors: site, operation, linker, guard, or target?

When an error occurs in the runtime:

| Symptom | Common cause | Where to look |
| --- | --- | --- |
| `NoSuchDynamicMethodException` | No linker claims the receiver/operation, or namespace/member does not match | `LinkRequest`, operation, receiver class, fallback order, access |
| `WrongMethodTypeException` | Site signature differs from static type of `invokeExact` or MH target/guard is incompatible | `CallSiteDescriptor.getMethodType()`, `MethodHandle.type()`, return cast |
| `ClassCastException` | Target or adapter casts receiver/value to an incompatible type | Guard, `asType`, converter, and runtime class |
| `IllegalAccessException` | Lookup lacks permission to find method/field | `lookup.lookupClass()`, modes, module exports/opens |
| `BootstrapMethodError` when running indy | Bootstrap failed/wrong CallSite type during JVM link | BSM code, cause, `BootstrapMethods` bytecode |
| Many unexpected relinks | Receiver shapes fluctuate or guard is too specific | Cache strategy, site profile, type distributions |
| Stale results after object shape change | Guard/invalidation missing conditions | `SwitchPoint`, shape version, prototype invalidation |
| Public Java bean not seen by Dynalink | Class/package not public/exported per module rules or wrong operation namespace | JPMS exports, bean accessors, `PROPERTY` vs `ELEMENT` |
| Custom linker not called/always returns null | Not set as prioritized, wrong receiver check, NamedOperation wrapper not unwrapped | `setPrioritizedLinker`, `NamedOperation.getBaseOperation` |
| Site returns inconsistent language errors | Missing-member fallback policy lacks design | Custom fallback linker, language semantics |

**Error logging principle:** log at minimum `operation`, `descriptor.getMethodType()`, runtime receiver class (when present), which linker handled it, guard result, and relink count; avoid logging entire objects/user data unnecessarily. For code engines running external data, limit log size and mask secrets.

### Small debug pattern (non-standalone snippet)

~~~java
CallSiteDescriptor desc = request.getCallSiteDescriptor();
Object receiver = request.getReceiver();

System.out.println("operation=" + desc.getOperation());
System.out.println("siteType=" + desc.getMethodType());
System.out.println("receiverType=" +
    (receiver == null ? "null" : receiver.getClass().getName()));
~~~

This snippet assumes the variable `LinkRequest request` exists inside `GuardingDynamicLinker.getGuardedInvocation(...)`. Do not take `request.getReceiver()` as proof that the compiler knew the receiver type at compile time: this is the **runtime object** of a single link request.

## 16. Common misconceptions

- “`invokedynamic` and Dynalink are the same thing.” — No. The opcode/protocol belongs to the JVM; Dynalink is a library that helps link operations.
- “Dynalink parses the language and runs scripts itself.” — No. It has no grammar, parser, or complete evaluator.
- “Only JavaBeans can use Dynalink.” — No. A custom `GuardingDynamicLinker` can understand another language's object model.
- “Using normal Java field access will also be cached by Dynalink.” — No. The compiler must create/configure sites using Dynalink.
- “`DynamicLinker.link` already finds targets for all receivers at setup time.” — No. Actual targets are typically linked when the site receives runtime arguments.
- “The property name of a `NamedOperation` still has to be passed via a separate runtime parameter.” — No. For GET/SET, the name is fixed and no longer appears in the site signature.
- “You can call `NamespaceOperation.contains` directly on an outer NamedOperation.” — Not according to that contract; unwrap it first with `NamedOperation.getBaseOperation`.
- “The `RelinkableCallSite` interface has `dynamicInvoker()`.” — No. This method belongs to the `CallSite` class; built-in concrete implementations extend CallSite.
- “A guard only needs to check the class in every object model.” — No. If shapes/prototypes change, a class-only guard can be too weak.
- “`ChainedCallSite` is always faster than `SimpleRelinkableCallSite`.” — No, it depends on polymorphism at the site and guard cost.
- “`setPrioritizedLinker` makes the JavaBeans fallback disappear.” — Not by default; the built-in BeansLinker can still handle objects when the custom linker returns null.
- “`requires jdk.dynalink` allows reading every Java member in private packages.” — No. Java visibility/JPMS still applies.
- “Failing to link a member must always return null.” — No, the language runtime must decide missing-member semantics.
- “`MethodHandle.invokeExact` automatically widens/casts every argument.” — No; the call-site descriptor must match exact types.
- “Dynalink automatically sandboxes dynamic code.” — No. It does not block CPU, I/O, reflection, network, or class loading of code that the engine allows to execute.
- “A site for receiver type A will be permanently bound to A.” — No. Relinking/guards allow handling types B, C... at the same site.

## 17. Self-check exercises

**Question 1.** A DSL has the expression `obj.color` where the runtime receiver can be `Person` or `Map`. What role does Dynalink play?

**Answer:** Represents the property/element read operation, selects a guarding linker based on the receiver, and relinks the target when the receiver no longer satisfies the guard. The DSL must still clearly define whether Map uses the `PROPERTY` or `ELEMENT` namespace.

**Question 2.** Why does a `GET PROPERTY name` site with `NamedOperation` have type `(Object)Object` instead of `(Object,String)Object`?

**Answer:** The property name `name` has been fixed in the operation metadata. Only the receiver is a dynamic argument at invocation; the return is Object.

**Question 3.** Which default linker does `DynamicLinkerFactory` have to assist with Java interoperability?

**Answer:** `BeansLinker` in the fallback configuration, allowing linking of common operations on JavaBeans, Java arrays/List/Map, and many Java public members.

**Question 4.** Does a custom linker returning null in `getGuardedInvocation` indicate it successfully linked with a null target?

**Answer:** No. Null means that linker **does not handle** the operation and allows trying subsequent linkers. If nobody handles it, the site may throw `NoSuchDynamicMethodException` at invocation.

**Question 5.** How do `SimpleRelinkableCallSite` and `ChainedCallSite` differ?

**Answer:** Simple holds one guarded invocation; Chained holds a chain of guarded invocations (default maximum of 8). Chained can reuse targets for previously seen types, but cost/performance depends on the workload.

**Question 6.** Why does `DynalinkCustomDemo` have `simpleLinks=2` and `chainLinks=1`?

**Answer:** The receiver sequence is DynRecord→JavaBean→DynRecord. Simple replaces the target when switching to JavaBean, so returning to DynRecord requires relinking. Chained kept the guard for the earlier DynRecord so it does not need a new custom link on the third call.

**Question 7.** With `MethodHandle.invokeExact` on an `(Object)Object` site, can you assign the result directly under `String`?

**Answer:** If cast at the call site to `String`, the return descriptor does not match `Object`, causing `WrongMethodTypeException`. Receive `Object` first or use a controlled conversion API.

**Question 8.** Does `requires jdk.dynalink` in a named module automatically allow the default BeansLinker to read a public bean in a non-exported package?

**Answer:** No. Readability of the module API and export/visibility of the bean package are two separate checks. Appropriate exposure must be designed.

**Question 9.** If an object can change its prototype/shape after the site is linked, what should be added?

**Answer:** A guard checking shape/version or invalidating `SwitchPoint`/target when assumptions change; a class-only guard may no longer be valid.

**Question 10.** Can Dynalink be used in an interpreter without `invokedynamic` bytecode?

**Answer:** Yes. The interpreter can attach a `CallSite` per AST operation and call `dynamicInvoker()`. However, that is using Dynalink via Java APIs, not proof that the interpreter emitted the indy opcode.

**Question 11.** To use `BeansLinker` for a custom-defined object model without corresponding Java fields/getters, is merely making the class public sufficient?

**Answer:** No. You must define a custom linker or appropriate adapter mapping, and put it into `DynamicLinkerFactory`'s pipeline.

**Question 12.** Does Dynalink guarantee that a site running on different receivers will never have cache misses?

**Answer:** No. Guards can fail, sites relink, cache chains have limits, and assumptions can be invalidated. That is why configuring and measuring the call site strategy is necessary.

## 18. Official Java SE 17 documentation

- Module `jdk.dynalink` — goals, example architecture, language-specific linkers, BeansLinker, and interoperability: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html
- `DynamicLinker` — `link(RelinkableCallSite)` and relink mechanism: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html
- `DynamicLinkerFactory` — prioritized/fallback linkers, class loader discovery, relink policy: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html
- `CallSiteDescriptor`, `Operation`, `StandardOperation`, `StandardNamespace`, `NamedOperation`, `NamespaceOperation`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/package-summary.html
- `SimpleRelinkableCallSite` — monomorphic inline cache: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html
- `ChainedCallSite` — polymorphic inline cache, default maximum 8 entries: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/ChainedCallSite.html
- `GuardingDynamicLinker`, `LinkRequest`, `GuardedInvocation`, `LinkerServices`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/package-summary.html
- `BeansLinker` — Java properties, methods, arrays/List/Map, and public access: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/beans/BeansLinker.html
- `java.lang.invoke` — MethodHandles, MethodType, CallSite, and invokedynamic: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html

**Remember:** `invokedynamic` is the linking mechanism at the JVM level; `java.lang.invoke` represents MethodHandles/CallSites; and `jdk.dynalink` is the layer that **interprets high-level operations, selects guarding linkers, and manages relinking/caching** so a dynamic language runtime can handle multiple receiver types and interoperate with Java objects. To use it properly, you must design **operation semantics, guard validity, access rights, cache policy, and error behavior**; Dynalink does not decide those on behalf of your language.