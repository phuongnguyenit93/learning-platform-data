# 18.2. Describing Operation, Namespace, Operation Name, and CallSiteDescriptor

> **Module:** Java Advance – dynamic-runtime, group **18. Dynalink**, Java SE 21. In `jdk.dynalink`, a dynamic expression such as `obj.name`, `obj[key]`, or `obj.method(x)` is described by **operation intent** (`Operation`), **address space** (`Namespace`), **pre-bound name/index if any** (`NamedOperation`), and **call site signature + linking permissions** (`CallSiteDescriptor`). These objects are *metadata*, not executable code. Only when there is a linker and a relinkable call site do they participate in creating and invoking a `MethodHandle`.

## 1. Objectives and Scope

After this lesson, you can:

1. Distinguish `Operation`, `StandardOperation`, `Namespace`, `StandardNamespace`, `NamespaceOperation`, `NamedOperation`, and `CallSiteDescriptor`.
2. Identify the five standard operations `GET`, `SET`, `REMOVE`, `CALL`, `NEW`; know when they require a namespace.
3. Understand `PROPERTY`, `ELEMENT`, `METHOD` and explain why namespace order creates different semantics.
4. Create operations using `withNamespace`, `withNamespaces`, `named`; use `NamedOperation.getName` and helpers to unwrap them.
5. Deduce the argument count and return type of `GET/SET/REMOVE` when the address is dynamic or named, and of `CALL/NEW` when labeled.
6. Create `CallSiteDescriptor(lookup, operation, methodType)`; explain the individual responsibility of each parameter and the two methods `changeOperation`/`changeMethodType`.
7. Distinguish metadata equality from runtime linkability/accessibility.
8. Create and run `DynamicLinker`, `BeansLinker`, and `SimpleRelinkableCallSite` to test a real operation.
9. Identify nesting errors, null errors, wrong `MethodType`, `Lookup` permissions, module dependency, and missing-linker errors.
10. Compile/run five standalone programs using standard Java 21 APIs.

**Prerequisites:** `MethodHandle`, `MethodType`, `MethodHandles.Lookup`, `invokedynamic` at a conceptual level; JavaBeans, Map/List, class loader/module. No new bytecode-generating compiler, ASM, Nashorn, or internal APIs are needed.

## 2. The Big Picture: Metadata First, Then Linking

Dynalink supports languages/DSLs that have expressions whose receiver type is only known at runtime. The descriptor set contains the answers to: "what do we want to do?", "which data domain to access?", "is the key fixed or passed at runtime?", "what types does the call take/return?", and "what permissions does the caller have?".

```text
DSL semantics: obj.title
        |
        v
Operation: GET + PROPERTY + name "title"
        |
        +--> CallSiteDescriptor
        |    ├── Lookup: caller access context
        |    ├── Operation: GET:PROPERTY:title
        |    └── MethodType: (Object)Object
        |
        v
RelinkableCallSite (SimpleRelinkableCallSite)
        |
        v
DynamicLinker (BeansLinker and/or custom linker)
        |
        v
GuardedInvocation / target MethodHandle
        |
        v
dynamicInvoker() and relink when needed
```

`Operation` is not `MethodHandle`. `CallSiteDescriptor` is also not `java.lang.invoke.CallSite`. They do not read properties or invoke Java methods on their own. `DynamicLinker` finds a suitable implementation among `GuardingDynamicLinker`s; `RelinkableCallSite` holds the target so calls pass through it.

A linker can combine guards by receiver class, overload resolution, conversion, and switchpoint invalidation; the same descriptor can link different targets for different receivers. Therefore, **metadata equality does not imply target identity**.

## 3. StandardOperation: Five Standard Operations

`StandardOperation` is an enum implementing `Operation`. Java 21 has exactly five values: `GET`, `SET`, `REMOVE`, `CALL`, `NEW`.

| Operation | Responsibility | Typical Signature Form |
| --- | --- | --- |
| `GET` | Read a value from a namespace of the receiver | `(receiver,name)→value` or named `(receiver)→value` |
| `SET` | Write a value into a namespace | `(receiver,name,value)→void` or named `(receiver,value)→void` |
| `REMOVE` | Remove a value at an address in a namespace | `(receiver,name)→void` or named `(receiver)→void` |
| `CALL` | Invoke a callable object | `(callable,receiver,arguments...)→value` |
| `NEW` | Invoke a constructor object | `(constructor,arguments...)→value` |

According to the Java 21 Javadoc, `GET`, `SET`, and `REMOVE` **must be combined with at least one NamespaceOperation** to have standard semantics. `CALL` and `NEW` operate standalone; they can still be named via `NamedOperation` for diagnostic labeling.

`receiver`, `name`, `value`, `callable` are parameter **roles**, not fixed Java types. The actual `MethodType` may use `Object`, `Map`, `int`, `String`, etc., depending on the frontend and adapter/linker capabilities. The `CALL` signature has **callable before receiver**; do not swap them to receiver first just because a normal Java instance method usually takes the receiver first. For a callable that has no concept of a receiver, the linker may ignore that parameter. `NEW` takes a constructor object and arguments, with no separate receiver.

### 3.1. GET METHOD Is Different from CALL

An expression `obj.run(x)` can be split into `GET:METHOD:run` to obtain the callable, and then `CALL` to invoke it with the receiver and argument `x`. `GET:METHOD` does not mean the method has already been called. This is a modeling decision of the language/runtime: it can be optimized differently, but the semantic contract must be preserved.

### 3.2. Creating Operations Using Factories

```java
// Illustrative snippet in a class that has imported jdk.dynalink.*.
Operation getProperty = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY);
Operation getElement = StandardOperation.GET
        .withNamespace(StandardNamespace.ELEMENT);
Operation setProperty = StandardOperation.SET
        .withNamespace(StandardNamespace.PROPERTY);
Operation removeElement = StandardOperation.REMOVE
        .withNamespace(StandardNamespace.ELEMENT);
Operation call = StandardOperation.CALL;
Operation create = StandardOperation.NEW;
```

The factories return operation descriptions; they do not yet run to look up getters, map entries, or constructors. If the receiver does not support the operation, the linker may fail at the link/invoke stage.

## 4. Namespace: PROPERTY, ELEMENT, METHOD

`Namespace` is an interface describing an **address space**; `StandardNamespace` has `PROPERTY`, `ELEMENT`, and `METHOD`.

| Namespace | According to `BeansLinker` for Java Objects | Example |
| --- | --- | --- |
| `PROPERTY` | Bean-style public getter/setter, record component accessor, public field, some virtual properties | `obj.name` |
| `ELEMENT` | Array/list element, Map entry by index/key | `obj[key]` |
| `METHOD` | Obtain a callable object representing a method, which can then be CALLed | `obj.work` |

These are namespaces **per linker**, not a JVM claim that Java objects always have three physical memory regions. A language-specific linker can have custom namespaces; `BeansLinker` defines semantics for JavaBeans/arrays/lists/maps.

### 4.1. NamespaceOperation Carries Priority Order

```java
Operation propertyFirst = StandardOperation.GET.withNamespaces(
        StandardNamespace.PROPERTY, StandardNamespace.ELEMENT);
Operation elementFirst = StandardOperation.GET.withNamespaces(
        StandardNamespace.ELEMENT, StandardNamespace.PROPERTY);
```

`NamespaceOperation` requires **at least one namespace**, stored **in exact order**. When there are multiple namespaces, they are alternatives **in first-applicable order**, not an unordered set. `getNamespace(0)` is the first priority; `getNamespaceCount()` returns the count; `contains()` checks membership. `getNamespaces()` returns a **defensive copy**.

**First applicable does not mean first non-null.** The linker decides whether a property/key applies to the receiver. If an entry exists but its value is null, one must not arbitrarily infer "try the next namespace" without a specific contract.

### 4.2. Example of a Real Difference

For a Map with key `"empty"` and value `"map-value"`, the Map itself is not empty so `isEmpty()` returns `false`. `BeansLinker` allows reading property `empty` via the Java getter `isEmpty()`, and element `empty` via the Map key.

```text
GET:PROPERTY|ELEMENT:empty  -> false
GET:ELEMENT|PROPERTY:empty  -> "map-value"
```

Lab 5 will use the **same receiver** and the **same MethodType** but swap the namespace order; this is a real semantic difference, not just changing the `toString()` string.

## 5. NamedOperation: Pre-Bound Name/Address

`NamedOperation` combines a base operation and a non-null `Object name`. The address can be a String property name or an Integer index; the API does not restrict name to String.

```java
Operation namedProperty = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY).named("title");
Operation namedIndex = StandardOperation.GET
        .withNamespace(StandardNamespace.ELEMENT).named(2);
Operation namedCall = StandardOperation.CALL.named("service.execute");
```

For `GET/SET/REMOVE`, binding the name/index in metadata **removes one name argument** from the expected call-site signature. For `CALL/NEW`, the name is only a **diagnostic label** and removes no parameter, because CALL/NEW do not have a separate name parameter in the first place.

### 5.1. Wrapper Structure

```text
NamedOperation
├── name: "title"
└── baseOperation: NamespaceOperation
    ├── baseOperation: StandardOperation.GET
    └── namespaces: [PROPERTY, ELEMENT]
```

Use the factories in the order `StandardOperation → withNamespace(s) → named`:

```java
Operation op = StandardOperation.GET
        .withNamespaces(StandardNamespace.PROPERTY, StandardNamespace.ELEMENT)
        .named("title");
```

Do not nest `NamespaceOperation` over a base that is already a `NamedOperation` or `NamespaceOperation`, nor nest `NamedOperation` over another `NamedOperation`: the constructors reject such structures. Metadata may be valid as a Java object yet not conform to standard operation rules (for example, bare `GET` without a namespace); the linker still needs semantic validation.

### 5.2. Unwrapping an Operation in the Right Order

```java
// Within a scope that has Operation op.
Object name = NamedOperation.getName(op);
Operation withoutName = NamedOperation.getBaseOperation(op);
jdk.dynalink.Namespace[] namespaces =
        NamespaceOperation.getNamespaces(withoutName);
Operation root = NamespaceOperation.getBaseOperation(withoutName);
```

`NamedOperation.getName` returns null when the outer object is not a NamedOperation; do not use a `(String)` cast by default because name can be an Integer. `NamedOperation.getBaseOperation` unwraps the outer wrapper if present. `NamespaceOperation.getBaseOperation` only unwraps the namespace wrapper it receives; it **does not automatically traverse through NamedOperation**. Therefore, unwrap name first and then unwrap namespace.

Two operations with the same base/name and namespace ordering compare equal via `equals`. Reversing the namespace order will make them different. Use `equals` for structural comparison; do not rely on object identity of newly created wrappers.

## 6. Lab 1 — Describing, Decomposing, and Comparing Operations

Create the file **`OperationAnatomyLab.java`**:

```java
import jdk.dynalink.NamedOperation;
import jdk.dynalink.NamespaceOperation;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;

public class OperationAnatomyLab {
    public static void main(String[] args) {
        Operation unbound = StandardOperation.GET
                .withNamespaces(StandardNamespace.PROPERTY, StandardNamespace.ELEMENT);
        Operation named = unbound.named("size");
        Operation inner = NamedOperation.getBaseOperation(named);
        Operation root = NamespaceOperation.getBaseOperation(inner);
        System.out.println("unbound=" + unbound);
        System.out.println("named=" + named);
        System.out.println("name=" + NamedOperation.getName(named));
        System.out.println("root=" + root);
        System.out.println("namespaceCount=" + NamespaceOperation.getNamespaces(inner).length);
        System.out.println("firstNamespace=" + NamespaceOperation.getNamespaces(inner)[0]);
        System.out.println("hasProperty=" + NamespaceOperation.contains(
                inner, StandardOperation.GET, StandardNamespace.PROPERTY));
        System.out.println("namedEquals=" + named.equals(
                StandardOperation.GET.withNamespaces(
                        StandardNamespace.PROPERTY, StandardNamespace.ELEMENT).named("size")));
        System.out.println("orderMatters=" + !named.equals(
                StandardOperation.GET.withNamespaces(
                        StandardNamespace.ELEMENT, StandardNamespace.PROPERTY).named("size")));
        System.out.println("indexName=" +
                StandardOperation.GET.withNamespace(StandardNamespace.ELEMENT).named(2));
        System.out.println("callName=" + StandardOperation.CALL.named("compute()"));
        System.out.println("plainName=" + NamedOperation.getName(unbound));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all OperationAnatomyLab.java
java --add-modules jdk.dynalink OperationAnatomyLab
```

**Verified stdout:**

```text
unbound=GET:PROPERTY|ELEMENT
named=GET:PROPERTY|ELEMENT:size
name=size
root=GET
namespaceCount=2
firstNamespace=PROPERTY
hasProperty=true
namedEquals=true
orderMatters=true
indexName=GET:ELEMENT:2
callName=CALL:compute()
plainName=null
```

**Explanation:** `unbound` does not bind a name, so GET may require a runtime key. `named` attaches `"size"` in metadata. After unwrapping the outer named and inner namespace, root is the enum `GET`. `indexName` proves an index can be an Integer. `callName` is a diagnostic label for CALL, not a method that has been invoked. `plainName=null` because `unbound` is not a NamedOperation.

## 7. CallSiteDescriptor Consists of Lookup, Operation, and MethodType

`CallSiteDescriptor` is a description of a dynamic call site, not the call site itself. Java 21 constructor:

```java
// Illustrative code snippet in scope with import jdk.dynalink.* and java.lang.invoke.*.
CallSiteDescriptor descriptor = new CallSiteDescriptor(
        MethodHandles.lookup(),
        StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("name"),
        MethodType.methodType(Object.class, Object.class));
```

Three components:

| Component | API | Question It Answers |
| --- | --- | --- |
| `Lookup` | `getLookup()` | Who is the caller and what access modes does it have? |
| `Operation` | `getOperation()` | What GET/SET/REMOVE/CALL/NEW on which namespace and name is desired? |
| `MethodType` | `getMethodType()` | What are the exact call-site arguments and return type? |

`MethodType.methodType(returnType, parameterTypes...)` takes the return type **first**; `toString()` usually prints `(parameters)returnType`. `(Object)Object` in the example is **one receiver → one result** because `name` is already bound in the operation.

**Do not treat `getMethodType()` as proof that a runtime target already exists.** The descriptor describes the linkage request. One can create a descriptor with a signature unsuitable for the operation and only discover it when the linker processes it or at invocation; compiler/DSL authors must check sanity.

### 7.1. Lookup and Access Permissions

`MethodHandles.Lookup` has `lookupClass()`, `lookupModes()`, and the class loader/module context. If the descriptor is created in an `invokedynamic` bootstrap method, use the **lookup passed in by the JVM** to preserve the caller's permissions. Carelessly replacing it with `publicLookup()` can lose permission to find private/package members or encounter visibility/class-loading restrictions.

Do not turn an operation name into a mechanism to bypass Java access control. `GET:PROPERTY:secret` only tells the linker "try to read"; whether it succeeds depends on Lookup, receiver, module permissions, linker policy, and the actual member.

## 8. Changing Metadata Without Changing the Call Site Itself

`CallSiteDescriptor` has two ways to derive a new descriptor:

- `changeOperation(newOperation)`: **changes only the operation**, keeping lookup and method type.
- `changeMethodType(newType)`: **changes only the method type**, keeping lookup and operation.

```java
// Illustrative code snippet; assume the original descriptor is GET:PROPERTY:name, (Object)Object.
CallSiteDescriptor anotherOp = descriptor.changeOperation(
        StandardOperation.GET.withNamespace(StandardNamespace.ELEMENT).named("name"));
CallSiteDescriptor anotherType = descriptor.changeMethodType(
        MethodType.methodType(String.class, Object.class));
```

These methods **do not** mutate the old descriptor, do not call `DynamicLinker.link`, do not automatically change the target `MethodHandle`, and do not perform any property access. If changing from a named to an unnamed operation, the method type does not automatically insert a name parameter.

```text
Initially:
  Operation  = GET:PROPERTY:name
  MethodType = (Object)Object

Only calling changeOperation(GET:PROPERTY):
  Operation  = GET:PROPERTY
  MethodType = (Object)Object      <-- still missing the name argument

To represent a dynamic-name GET:
  Operation  = GET:PROPERTY
  MethodType = (Object,Object)Object
```

### 8.1. Equality of CallSiteDescriptor

The Javadoc describes equality by **exact descriptor class**, operation, method type, and `Lookup.lookupClass()` + `Lookup.lookupModes()`. Two separately constructed descriptors can still be equal if those attributes match. However, description equality does not prove two receiver objects, target handles, or guards are the same; that is a matter of runtime linking.

## 9. Lab 2 — Building and Changing Operation and MethodType

Create **`DescriptorMetadataLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;

public class DescriptorMetadataLab {
    public static void main(String[] args) {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY).named("name");
        MethodType type = MethodType.methodType(Object.class, Object.class);
        CallSiteDescriptor desc = new CallSiteDescriptor(lookup, op, type);
        CallSiteDescriptor otherType =
                desc.changeMethodType(MethodType.methodType(String.class, Object.class));
        CallSiteDescriptor otherOp = desc.changeOperation(StandardOperation.GET
                .withNamespace(StandardNamespace.ELEMENT).named("name"));
        CallSiteDescriptor reconstructed = new CallSiteDescriptor(lookup, op, type);
        System.out.println("operation=" + desc.getOperation());
        System.out.println("type=" + desc.getMethodType());
        System.out.println("lookupClass=" + desc.getLookup().lookupClass().getSimpleName());
        System.out.println("changedType=" + otherType.getMethodType());
        System.out.println("keepsOp=" + otherType.getOperation().equals(op));
        System.out.println("changedOp=" + otherOp.getOperation());
        System.out.println("keepsType=" + otherOp.getMethodType().equals(type));
        System.out.println("valueEquals=" + desc.equals(reconstructed));
        System.out.println("originalStill=" + desc.getMethodType());
        System.out.println("sameLookupClass=" +
                (otherOp.getLookup().lookupClass() == desc.getLookup().lookupClass()));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all DescriptorMetadataLab.java
java --add-modules jdk.dynalink DescriptorMetadataLab
```

**Stdout:**

```text
operation=GET:PROPERTY:name
type=(Object)Object
lookupClass=DescriptorMetadataLab
changedType=(Object)String
keepsOp=true
changedOp=GET:ELEMENT:name
keepsType=true
valueEquals=true
originalStill=(Object)Object
sameLookupClass=true
```

**Analysis:** `changeMethodType` changes the return type to String while keeping the operation. `changeOperation` changes PROPERTY to ELEMENT while keeping the type. `valueEquals=true` because the two descriptors have the same three components and lookup context. `originalStill` confirms the old descriptor was not modified.

## 10. Deducing Signatures for GET/SET/REMOVE/CALL/NEW

A linker needs a `MethodType` matching the argument roles; in particular, a named operation affects GET/SET/REMOVE differently from CALL/NEW.

| Operation | Illustrative Object-based Signature | Argument Roles |
| --- | --- | --- |
| `GET:PROPERTY` | `(Object,Object)Object` | receiver, runtime name |
| `GET:PROPERTY:title` | `(Object)Object` | receiver; name is bound |
| `SET:PROPERTY` | `(Object,Object,Object)void` | receiver, runtime name, value |
| `SET:PROPERTY:title` | `(Object,Object)void` | receiver, value |
| `REMOVE:ELEMENT` | `(Object,Object)void` | receiver, runtime index/key |
| `REMOVE:ELEMENT:0` | `(Object)void` | receiver; index is bound |
| `CALL` | `(Object,Object,Object)Object` | callable, receiver, 1 arg |
| `CALL:service.execute` | `(Object,Object,Object)Object` | same as CALL; label is diagnostic only |
| `NEW` | `(Object,Object)Object` | constructor, 1 arg |
| `NEW:Widget` | `(Object,Object)Object` | same as NEW; label is diagnostic only |

These are **typical shapes** according to `StandardOperation`. Depending on the linker, parameter/return types may be narrower or primitive. Do not mistake a printed `MethodType` for an indication that the linker actually supports the operation on every receiver.

### 10.1. How to Remember Named vs. Dynamic

`GET:PROPERTY` takes `(receiver,name)`. `GET:PROPERTY:title` takes `(receiver)` because `title` is in the metadata. `SET` adds value after name if name is runtime; when named, only receiver+value remain. `REMOVE` has return type `void`; when named, only receiver remains. `CALL` takes callable and receiver even when named; `NEW` takes constructor object and arguments, with no separate receiver.

Note that `MethodHandle.invokeExact` checks the **return type** of the call site as well. In an actual invocation snippet, an `(Object)` cast and an Object variable are often needed to match the `(Object)Object` descriptor; one cannot arbitrarily change it to `(String)` and hope the JVM adjusts automatically.

## 11. Lab 3 — Printing Signatures for All Five Groups

Create the file **`OperationSignaturesLab.java`**:

```java
import java.lang.invoke.MethodType;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;

public class OperationSignaturesLab {
    private static void display(String label, Operation operation, MethodType type) {
        System.out.println(label + "=" + operation + " " + type);
    }

    public static void main(String[] args) {
        Operation get = StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY);
        Operation set = StandardOperation.SET.withNamespace(StandardNamespace.PROPERTY);
        Operation remove = StandardOperation.REMOVE.withNamespace(StandardNamespace.ELEMENT);
        display("getDynamic", get,
                MethodType.methodType(Object.class, Object.class, Object.class));
        display("getNamed", get.named("title"),
                MethodType.methodType(Object.class, Object.class));
        display("setDynamic", set,
                MethodType.methodType(void.class, Object.class, Object.class, Object.class));
        display("setNamed", set.named("title"),
                MethodType.methodType(void.class, Object.class, Object.class));
        display("removeDynamic", remove,
                MethodType.methodType(void.class, Object.class, Object.class));
        display("removeNamed", remove.named(0),
                MethodType.methodType(void.class, Object.class));
        display("call", StandardOperation.CALL,
                MethodType.methodType(Object.class, Object.class, Object.class, Object.class));
        display("namedCall", StandardOperation.CALL.named("service.execute"),
                MethodType.methodType(Object.class, Object.class, Object.class, Object.class));
        display("new", StandardOperation.NEW,
                MethodType.methodType(Object.class, Object.class, Object.class));
        display("namedNew", StandardOperation.NEW.named("Widget"),
                MethodType.methodType(Object.class, Object.class, Object.class));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all OperationSignaturesLab.java
java --add-modules jdk.dynalink OperationSignaturesLab
```

**Stdout:**

```text
getDynamic=GET:PROPERTY (Object,Object)Object
getNamed=GET:PROPERTY:title (Object)Object
setDynamic=SET:PROPERTY (Object,Object,Object)void
setNamed=SET:PROPERTY:title (Object,Object)void
removeDynamic=REMOVE:ELEMENT (Object,Object)void
removeNamed=REMOVE:ELEMENT:0 (Object)void
call=CALL (Object,Object,Object)Object
namedCall=CALL:service.execute (Object,Object,Object)Object
new=NEW (Object,Object)Object
namedNew=NEW:Widget (Object,Object)Object
```

**Lab limitation:** this code prints Operation and MethodType **manually constructed** by the programmer, not yet linked to real objects. It helps cross-check expected signatures; Lab 5 is what shows a linker applying an operation to a JavaBean/Map at runtime.

## 12. Structural Validity and Nesting Errors

`NamespaceOperation` allows a **base Operation that is not Named/NamespaceOperation** and at least one namespace. `NamedOperation` does not accept a base that is already a NamedOperation; both reject null components per their constructor contracts.

| Input | Expectation |
| --- | --- |
| `new NamespaceOperation(GET, PROPERTY)` | Valid |
| `new NamespaceOperation(GET)` | `IllegalArgumentException` due to missing namespace |
| `new NamespaceOperation(GET.withNamespace(PROPERTY), ELEMENT)` | `IllegalArgumentException` because base is already a NamespaceOperation |
| `new NamedOperation(GET.named("a"),"b")` | `IllegalArgumentException` because base is already named |
| `new NamedOperation(GET,null)` | `NullPointerException` |
| `new NamespaceOperation(GET,(Namespace)null)` | `NullPointerException` |

**Two different validation levels:** `NamedOperation(GET,"x")` may be constructible as a wrapper object, but bare `GET` still lacks a namespace under the semantic contract of `StandardOperation.GET`. Therefore, do not infer construction success = linker supports it.

### 12.1. The Namespace Array Is a Copy

`NamespaceOperation.getNamespaces()` returns a new array. Mutating `copy[0]` does not modify the operation. This allows you to introspect without altering the priority configured when the operation was created. `getNamespace(0)` reads the first namespace. When you need a new priority configuration, construct a new `NamespaceOperation`.

## 13. Lab 4 — Testing Error Structures and Defensive Copies

Create the file **`ValidationLab.java`**:

```java
import jdk.dynalink.NamedOperation;
import jdk.dynalink.Namespace;
import jdk.dynalink.NamespaceOperation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;

public class ValidationLab {
    public static void main(String[] args) {
        try {
            new NamespaceOperation(StandardOperation.GET);
            System.out.println("noNamespaces=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("noNamespaces=IllegalArgumentException");
        }
        try {
            new NamespaceOperation(
                    StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY),
                    StandardNamespace.ELEMENT);
            System.out.println("nestedNamespace=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("nestedNamespace=IllegalArgumentException");
        }
        try {
            new NamedOperation(StandardOperation.GET.named("a"), "b");
            System.out.println("nestedName=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("nestedName=IllegalArgumentException");
        }
        try {
            new NamedOperation(StandardOperation.GET, null);
            System.out.println("nullName=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullName=NullPointerException");
        }
        try {
            new NamespaceOperation(StandardOperation.GET, (Namespace) null);
            System.out.println("nullNamespace=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullNamespace=NullPointerException");
        }
        NamespaceOperation good = new NamespaceOperation(
                StandardOperation.GET,
                StandardNamespace.PROPERTY, StandardNamespace.ELEMENT);
        Namespace[] copy = good.getNamespaces();
        copy[0] = StandardNamespace.METHOD;
        System.out.println("defensiveCopy=" +
                (good.getNamespace(0) == StandardNamespace.PROPERTY));
        System.out.println("containsElement=" + good.contains(StandardNamespace.ELEMENT));
        System.out.println("namespaceEquals=" + good.equals(new NamespaceOperation(
                StandardOperation.GET, StandardNamespace.PROPERTY,
                StandardNamespace.ELEMENT)));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all ValidationLab.java
java --add-modules jdk.dynalink ValidationLab
```

**Stdout:**

```text
noNamespaces=IllegalArgumentException
nestedNamespace=IllegalArgumentException
nestedName=IllegalArgumentException
nullName=NullPointerException
nullNamespace=NullPointerException
defensiveCopy=true
containsElement=true
namespaceEquals=true
```

**Explanation:** the constructors prevent nesting and nulls according to the rules. `defensiveCopy=true` confirms that modifying the returned array does not change the priority inside the operation. `namespaceEquals=true` confirms that two wrappers with the same base and the same ordered namespaces compare equal.

## 14. Connecting CallSiteDescriptor to a Real Linker

A Dynalink application needs a `DynamicLinkerFactory`, `DynamicLinker`, `RelinkableCallSite`, and linkers that handle the actual object model.

- `DynamicLinkerFactory` creates a linker set with priority/fallback. In the lab we use `setFallbackLinkers(new BeansLinker())`.
- `BeansLinker` reads properties, elements, and methods of Java objects; it has specific rules for JavaBean, array, List, Map, and record.
- `SimpleRelinkableCallSite` in **package `jdk.dynalink.support`** is a `RelinkableCallSite` implementation based on `MutableCallSite`, supporting **monomorphic inline caching**.
- `linker.link(site)` initializes the relink-and-invoke target; the first call with actual arguments selects a guarded invocation.
- `site.dynamicInvoker()` provides a `MethodHandle` to invoke according to the site's type.

**Exact name to note:** Java 21 provides `jdk.dynalink.support.SimpleRelinkableCallSite`. There is no API class `jdk.dynalink.MonomorphicCallSite`; "monomorphic" is a description of the caching strategy, not a standard class name. `ChainedCallSite` is the solution that supports a chain of guarded invocations for more diverse receivers.

Do not confuse "printable metadata" with "linked behavior". An Operation like `GET:PROPERTY:name` cannot `invokeExact()` by itself; only a linked site or MethodHandle executes.

## 15. Lab 5 — BeansLinker and PROPERTY/ELEMENT Priority

Create **`BeansLinkLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.HashMap;
import java.util.Map;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.beans.BeansLinker;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class BeansLinkLab {
    public static class Bean {
        public String getName() { return "Ada"; }
    }

    private static MethodHandle invoker(DynamicLinker linker, Operation operation) {
        CallSiteDescriptor desc = new CallSiteDescriptor(
                MethodHandles.lookup(), operation,
                MethodType.methodType(Object.class, Object.class));
        SimpleRelinkableCallSite site = new SimpleRelinkableCallSite(desc);
        linker.link(site);
        return site.dynamicInvoker();
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setFallbackLinkers(new BeansLinker());
        DynamicLinker linker = factory.createLinker();

        MethodHandle beanGetter = invoker(linker,
                StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("name"));
        System.out.println("beanName=" + (Object) beanGetter.invokeExact((Object) new Bean()));

        Map<String, Object> map = new HashMap<>();
        map.put("empty", "map-value");
        MethodHandle propertyFirst = invoker(linker, StandardOperation.GET.withNamespaces(
                StandardNamespace.PROPERTY, StandardNamespace.ELEMENT).named("empty"));
        MethodHandle elementFirst = invoker(linker, StandardOperation.GET.withNamespaces(
                StandardNamespace.ELEMENT, StandardNamespace.PROPERTY).named("empty"));
        System.out.println("propertyFirst=" +
                (Object) propertyFirst.invokeExact((Object) map));
        System.out.println("elementFirst=" +
                (Object) elementFirst.invokeExact((Object) map));
        System.out.println("mapStillHasKey=" + map.containsKey("empty"));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all BeansLinkLab.java
java --add-modules jdk.dynalink BeansLinkLab
```

**Verified stdout:**

```text
beanName=Ada
propertyFirst=false
elementFirst=map-value
mapStillHasKey=true
```

**Interpretation:**

1. `Bean.getName()` is seen by `BeansLinker` as property `name`, so `beanName=Ada`.
2. The Map has entry `empty=map-value`, so `map.isEmpty()` returns false; `GET:PROPERTY|ELEMENT:empty` chooses property first and returns false.
3. `GET:ELEMENT|PROPERTY:empty` chooses the Map entry first and returns `map-value`.
4. The two invokers have the same `MethodType=(Object)Object` but different namespace order. `mapStillHasKey=true` proves these are read operations, with no Map key removal.
5. The `(Object)` cast at `invokeExact` keeps the exact call-site argument/return signature. If you use a `(String)` return cast when the handle has an Object return, you can get a `WrongMethodTypeException`.

This is a **linked execution experiment**, not just printing metadata. It also shows that when designing a DSL, you must choose priority according to the meaning of `obj.name` versus `obj[key]`.

## 16. Workflow Used in a Dynamic Interpreter/Compiler

A frontend can translate DSL expressions into metadata and call sites as follows:

```text
[1] Parse source expression:
      obj.title / obj[key] / obj.method(x) / new Widget(x)
        |
[2] Determine Operation:
      GET / SET / REMOVE / CALL / NEW
        |
[3] Determine namespace(s) if needed:
      PROPERTY, ELEMENT, METHOD; preserve priority
        |
[4] Fixed or dynamic name?
      NamedOperation to pre-bind, or a runtime name argument
        |
[5] Construct MethodType:
      receiver/name/value/callable/args and return type
        |
[6] Attach Lookup:
      new CallSiteDescriptor(lookup, operation, type)
        |
[7] Create RelinkableCallSite, call DynamicLinker.link(site)
        |
[8] Execute via dynamicInvoker(), guards/relink when needed
```

### 16.1. Suggested Mappings for Some Expressions

| Syntax | Illustrative Operation | Illustrative MethodType |
| --- | --- | --- |
| `obj.title` | `GET:PROPERTY:title` | `(Object)Object` |
| `obj[key]` | `GET:ELEMENT|PROPERTY` | `(Object,Object)Object` |
| `obj.title=x` | `SET:PROPERTY:title` | `(Object,Object)void` |
| `delete obj[key]` | `REMOVE:ELEMENT` | `(Object,Object)void` |
| `obj.work(x)` | `GET:METHOD:work` then `CALL` | GET `(Object)Object`; CALL `(Object,Object,Object)Object` |
| `new Thing(x)` | `NEW` (optional label) | `(Object,Object)Object` |

These mappings are **DSL design choices**, not a single set of rules for every language. A language may prioritize ELEMENT in `obj[key]` and PROPERTY in `obj.x`; the compiler needs consistent semantics and must verify them with tests.

### 16.2. Notes on Relink, Caching, and Permissions

`DynamicLinker` can relink by receiver class and invalidation. `CallSiteDescriptor.equals` is not sufficient to reuse a `GuardedInvocation` across all receivers. When caching, consider lookup, method type, ordered namespaces, name, guard, class loader, module context, and invalidation. Do not turn metadata into a capability bypass: `BeansLinker` can invoke Java methods that have side effects.

## 17. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| `IllegalArgumentException` when creating NamespaceOperation | Zero namespaces or base already named/namespaced | Use a simple base operation and ≥1 namespace. |
| `IllegalArgumentException` when creating NamedOperation | Base is already a NamedOperation | Name it exactly once after the namespace. |
| `NullPointerException` in wrapper | Null name or namespace | Validate before creating the operation. |
| `WrongMethodTypeException` at `invokeExact` | Wrong arity/return type compared to MethodType | Print `desc.getMethodType()`, place matching casts. |
| `NoSuchDynamicMethodException` when linking | Linker cannot resolve the operation for the runtime receiver | Check namespace, name, receiver, and conversion. |
| Access denied | Lookup/module/class/member access mismatch | Use the proper caller Lookup; do not arbitrarily replace with publicLookup. |
| Changed descriptor but call site still behaves the same | `changeOperation`/`changeMethodType` does not auto-relink | Create/relink the site per the linker protocol. |
| With Map `empty`, getting false instead of the entry | PROPERTY has higher priority than ELEMENT | Choose namespace order per the DSL. |
| Compile error: Dynalink module not found | `jdk.dynalink` not resolved | Use `--add-modules jdk.dynalink` or JPMS `requires`. |
| Wrong relinkable class name | Typed `MonomorphicCallSite` which is not in the API | Use `jdk.dynalink.support.SimpleRelinkableCallSite`. |
| Named GET still has an extra name parameter | Constructed MethodType like an unnamed operation | Remove the name argument and check the type. |
| Named CALL has an argument removed | Confused with GET/SET/REMOVE | CALL name is diagnostic only; arguments stay unchanged. |

### 17.1. Do Not Parse `Operation.toString()` as a General Protocol

A `NamedOperation` name is an Object that may have a custom `toString`. The display form `GET:PROPERTY|ELEMENT:key` is useful for debugging, but should not replace the `NamedOperation.getName` and `NamespaceOperation.getNamespaces` APIs, especially for custom operations and keys containing delimiters. When you need to serialize metadata for a DSL, define a schema with dedicated validation for operation, namespace order, name type, and MethodType.

## 18. The jdk.dynalink Module and Secure Design

Dynalink belongs to the standard JDK module **`jdk.dynalink`**, separate from `java.base`. When compiling/running on the classpath, pass it explicitly:

```sh
javac --release 21 --add-modules jdk.dynalink MyRuntime.java
java --add-modules jdk.dynalink MyRuntime
```

For a self-built named module:

```java
// Illustrative module-info.java.
module my.runtime {
    requires jdk.dynalink;
}
```

Do not use `jdk.internal.*`. `jdk.dynalink` is a public JDK module with API documentation, though a minimal runtime image may omit the module; check the image and `java --list-modules`. Module dependency is distinct from access permission to private members of an application.

### 18.1. Linking Policy for Untrusted Code

`Operation` only describes intent, not a permission credential. A DSL that accepts property or method names from untrusted users should not arbitrarily link to every Java method: use an allowlist of receivers/operations/members, restrict reflection/Lookup, sandbox at the process level when executing untrusted code, manage quotas, and never let users supply a privileged Lookup themselves. `BeansLinker` can lead to invoking Java code with side effects.

### 18.2. Caching and Performance

`SimpleRelinkableCallSite` uses a monomorphic inline cache; `ChainedCallSite` supports a polymorphic cache. Choose based on receiver-class workload and benchmarks, and do not use an operation name alone as the sole runtime cache key. If updates/invalidations happen frequently, consider switchpoints, guarded invocations, and churn. Description equality does not mean a target has the same validity for every receiver.

## 19. Exercises and Self-Check

**Exercise 1 – Unwrapping wrappers.** Create `GET:ELEMENT|PROPERTY:code` and use static helpers to extract name, root, and namespaces in the right order. Explain why `NamespaceOperation.getNamespaces(named)` directly returns an empty array.

**Exercise 2 – Dynamic vs. fixed key.** Compare `GET:ELEMENT` and `GET:ELEMENT:2`. Write the appropriate Object-based MethodTypes. Answer: `(Object,Object)Object` and `(Object)Object`.

**Exercise 3 – SET/REMOVE.** Determine the MethodTypes for `SET:PROPERTY`, `SET:PROPERTY:title`, `REMOVE:ELEMENT`, `REMOVE:ELEMENT:0`. Why does `SET` still need a value argument when named?

**Exercise 4 – CALL/NEW.** Compare `CALL` with `CALL.named("service.run")`. Use the same method type and explain why this name is a diagnostic label rather than a removed address argument.

**Exercise 5 – Namespace order.** Re-run Lab 5 with a Map containing key `"empty"`. Why do property-first and element-first return different results even though `CallSiteDescriptor.getMethodType` is identical?

**Exercise 6 – Nesting errors.** Create a new NamespaceOperation with zero namespaces; try wrapping NamedOperation twice. Predict `IllegalArgumentException` and distinguish it from null `NullPointerException`.

**Exercise 7 – changeOperation.** Create `GET:PROPERTY:title` with `(Object)Object`, call `changeOperation(GET:PROPERTY)`. State the method type issue; fix it with `changeMethodType((Object,Object)Object)`.

**Exercise 8 – Lookup.** Create descriptors in two different caller classes with the same operation/type. Why can `CallSiteDescriptor.equals` be false, and why do different lookup permissions affect linking a private member?

**Exercise 9 – GET METHOD.** Describe how `obj.work(7)` can use `GET:METHOD:work` and then `CALL`. In CALL, where are the callable and receiver positions?

**Exercise 10 – Runtime receiver.** Modify Lab 5 to invoke the same named `GET:PROPERTY:name` on Bean classes that have different getters. Observe relinking when the receiver class changes; do not use a single run's result as a guarantee of a fixed relink count.

**Exercise 11 – Security.** A DSL allows `GET:METHOD:deleteEverything` on any object provided by the caller. State the risks and a policy to restrict operations, receivers, and Lookup/linker.

**Exercise 12 – Frontend design.** Choose operation, namespace priority, name policy, and MethodType for `obj.x`, `obj[key]`, `obj.x=value`, `obj.x()`, and `new Foo(x)`, explaining which parts are decided by the language's semantics.

### 19.1. Checklist

- [ ] Know that Operation and CallSiteDescriptor are metadata, not MethodHandle.
- [ ] Identify the five StandardOperations and three StandardNamespaces.
- [ ] Distinguish PROPERTY/ELEMENT/METHOD and understand first-applicable priority.
- [ ] Create NamedOperation after NamespaceOperation; do not wrap in the wrong order.
- [ ] Extract name, namespaces, and root using the right helpers.
- [ ] Deduce the argument count of GET/SET/REMOVE when named and when dynamic.
- [ ] Understand that CALL/NEW names do not change MethodType.
- [ ] Build CallSiteDescriptor from Lookup, Operation, MethodType and understand the change APIs.
- [ ] Use `SimpleRelinkableCallSite` properly, link and then invoke.
- [ ] Successfully run all five programs with matching stdout; analyze Map priority and wrapper errors.

## 20. Official Java SE 21 Documentation

- [JDK 21 – module jdk.dynalink](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/module-summary.html): dynamic linking model, call sites, operations, guards.
- [JDK 21 – Operation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/Operation.html): `named`, `withNamespace(s)`.
- [JDK 21 – StandardOperation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/StandardOperation.html): GET, SET, REMOVE, CALL, NEW, and signatures.
- [JDK 21 – StandardNamespace](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/StandardNamespace.html): PROPERTY, ELEMENT, METHOD.
- [JDK 21 – NamespaceOperation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/NamespaceOperation.html): namespace ordering, base, arrays, helper methods.
- [JDK 21 – NamedOperation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/NamedOperation.html): name binding and diagnostic label.
- [JDK 21 – CallSiteDescriptor](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/CallSiteDescriptor.html): Lookup, MethodType, operation, and transformations.
- [JDK 21 – DynamicLinkerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html) and [DynamicLinker](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html): linking/relinking.
- [JDK 21 – BeansLinker](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/beans/BeansLinker.html): JavaBean, Map/List/array linking.
- [JDK 21 – SimpleRelinkableCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html): monomorphic cache implementation.
- [Java 21 – MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html) and [MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): signature, caller permissions.

**Key takeaway:** `Operation` specifies **intent**, `NamespaceOperation` specifies **spaces and priority order**, `NamedOperation` binds a **known name/key**, and `CallSiteDescriptor` pairs them with **MethodType and Lookup**. Only when linked through `DynamicLinker` and `RelinkableCallSite` does the description become real dynamic invocation behavior.
