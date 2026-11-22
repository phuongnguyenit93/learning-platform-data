# 18.6 GuardingDynamicLinker, LinkRequest, and LinkerServices for a Custom Object Model

**Context:** Java Advance → dynamic-runtime → 18. Dynalink.

Java has `invokedynamic` and `MethodHandle` mechanisms to handle calls linked at runtime. However, if you are writing a dynamic language, template runtime, expression engine, rule engine, or property-map-based object model, a major question arises: **When a caller requests `obj.color`, which logic should the JVM invoke if `obj` is at one time an object defined by our runtime, and at another time a regular JavaBean?**

**Dynalink** (module `jdk.dynalink`) organizes the selection and linking of that behavior. The three core APIs in this lesson are:

- **`GuardingDynamicLinker`:** a component written by the runtime itself to **recognize** objects/operations that it understands, then provide a `MethodHandle` that performs the behavior along with a **guard** that determines when the linkage is still valid.
- **`LinkRequest`:** describes a **link request** at a call site with the operation, `MethodType`, receiver object, the actual argument values at the time the relink occurred, and a signal indicating whether the call site is unstable.
- **`LinkerServices`:** services provided by `DynamicLinker` to the linker to adapt a `MethodHandle` to the call type, check type conversion capability, coordinate language-defined converters, filter internal objects, or delegate to other linkers.

Fundamental point: **linking is not the business call itself**. `GuardingDynamicLinker.getGuardedInvocation` is called when a call site needs to select or re-select a call path. Once a call path is installed, invocations can **go directly through the cached guarded handle**, without calling the linker for each request.

## 1. The Problem: A Non-JavaBean Object Model

Suppose the runtime has a `DynamicRecord` type that stores properties in a `Map<String,String>`:

```text
DynamicRecord {
    fields = {
        "color" : "red",
        "status": "ready"
    }
}
```

A dynamic language access expression might write `obj.color`. In traditional JavaBeans, "color" usually corresponds to `getColor()` or a readable field. But our `DynamicRecord` **does not have a `getColor()` method**; the property is a key in a map. Relying only on reflection on the class, that access has no meaning on its own.

We want a dynamic call site that supports:

```text
GET PROPERTY "color" : (Object)Object
SET PROPERTY "color" : (Object,Object)void
```

These are **call site** signatures, not Java method declarations. The runtime will understand:

- With a `DynamicRecord` receiver: access the `Map` by property name.
- With a regular JavaBean receiver: let Dynalink's **`BeansLinker`** try to resolve the property according to Java conventions.
- If the receiver does not match any linker: let the runtime handle the linking/unsupported operation error according to contract, **without blindly guessing** a target.
- If the receiver of the **same** GET call site changes from record to bean and then back to record: the guard of the old linkage no longer matches, and Dynalink performs a **relink**.

That is when a custom `GuardingDynamicLinker`, `LinkRequest`, and `LinkerServices` are needed.

## 2. Roles in a Dynamic Linkage

```text
                  caller: getColorInvoker.invokeExact(receiver)
                                      |
                                      v
                        RelinkableCallSite
                       (GET PROPERTY "color")
                                      |
                         cached guarded invocation?
                           /                    \
                          yes                    no / guard false
                           |                      |
                           v                      v
                     invoke target          DynamicLinker
                                                 |
                                   create LinkRequest
                                                 |
                              prioritized custom linkers
                                                 |
                                  RecordLinker.getGuardedInvocation(
                                     request, services)
                                      /                 \
                           supports receiver?          no
                                  |                     |
                                  v                     v
                          GuardedInvocation        other linkers,
                          (target + guard)        default BeansLinker
                                  |                     |
                           cache in call site <---------+
                                  |
                        guarded target.invoke(...)
                                  |
                           result to caller
```

| Component | Where is it created/located? | Primary role |
| --- | --- | --- |
| `Operation` | In `CallSiteDescriptor` | Describes GET/SET property, property name; not a fixed Java Method |
| `CallSiteDescriptor` | Attached to `RelinkableCallSite` | Stores lookup context, operation, and `MethodType` of the call site |
| `RelinkableCallSite` | Call site managed by `DynamicLinker.link` | Can replace the cached target when a relink is needed |
| `DynamicLinker` | Created from `DynamicLinkerFactory` | Coordinates linkers, conversions, and installs/relinks targets |
| `GuardingDynamicLinker` | Implemented by runtime or library | Attempts to link operations for its object model |
| `LinkRequest` | Provided by Dynalink during link/relink | Carries current information needed to decide linkage |
| `LinkerServices` | Provided by `DynamicLinker` | API for coordinating type conversions and linkers |
| `GuardedInvocation` | Returned by linker | Target + guard pair, optionally with `SwitchPoint`/exception for invalidation |
| `BeansLinker` | Default fallback of the factory | Supports linking Java objects according to Java semantics |

**A sound design** does not let a custom linker "hijack" every object. It should accurately recognize receivers belonging to its own runtime, support the operations it understands, and **return `null`** for requests it cannot handle so other linkers get a chance. That enables interoperability with Java objects and other languages.

## 3. Defining the Contract of `GuardingDynamicLinker`

Main interface:

```java
public interface GuardingDynamicLinker {
    GuardedInvocation getGuardedInvocation(
            LinkRequest linkRequest,
            LinkerServices linkerServices) throws Exception;
}
```

This is an **API signature with `public/abstract` omitted for illustration**, not a standalone program.

Points in the contract:

1. **Receive `LinkRequest`:** which contains the operation, `MethodType`, receiver, and argument values at link time.
2. **Determine whether it is supported:** if the object does not belong to the linker's model, or the operation is not understood, **return `null`**.
3. **If supported, create an invocation:** a `MethodHandle` that executes the chosen logic, possibly with the property name bound or other specialization.
4. **Create a guard when the invocation is only valid for a group of receivers:** for example, `receiver instanceof DynamicRecord`. If the guard fails, Dynalink is allowed to re-select the linkage.
5. **Keep the signature compatible with the call site:** parameter types are adapted appropriately; return type handling should follow the `LinkerServices.asTypeLosslessReturn`/pre-link transformer policy.
6. **Do not invoke the business target itself during linking** just to return a result: the linker must return an executable handle for future invocations.

**Returning `null` is different from returning a handle whose result is `null`:**

- `return null;` from `getGuardedInvocation` means "this linker does not handle this request; try another linker".
- A `GuardedInvocation` whose invocation returns `null` means "the linker accepted and completed the operation, and the business value is null".
- Throwing an exception on configuration error/inability to create a target is a third situation; do not use exceptions in place of normal fallback.

### A Minimal Guard

For `DynamicRecord` alone, the guard can be a handle:

```java
public static boolean isRecord(Object receiver) {
    return receiver instanceof DynamicRecord;
}
```

This is a **method snippet** (assuming class `DynamicRecord` exists). The `MethodType` of the guard is `(Object)boolean`. It does not inspect the value of `color` but inspects the **object type**. If the same object type continues to be used, the target method can read different data across calls **without needing to relink**.

If the target is bound to **a specific object**, or to **a specific shape/schema version**, a guard that only checks `instanceof` may be **too broad**. In that case, you must add identity, shape, or version checks, or use a `SwitchPoint` for invalidation.

## 4. `LinkRequest`: Information at *Link Time*

Main methods:

| Method | Meaning | Key takeaway |
| --- | --- | --- |
| `getCallSiteDescriptor()` | Descriptor of the call site: lookup, `Operation`, and `MethodType` | Used to know **which behavior** the caller is requesting |
| `getReceiver()` | First argument on the call currently being linked | Usually the object whose property/method is being accessed |
| `getArguments()` | Array of argument values at link time | Can be used for specialization, but is not all future arguments |
| `isCallSiteUnstable()` | Hint that the call site has relinked past the threshold set by the factory | Not a failure guarantee, but a suggestion to choose a broader guard |
| `replaceArguments(...)` | Creates a new request with a different descriptor/arguments | Used when controlled delegation coordination is needed |

**A major misconception:** `LinkRequest` is **not** a callback that receives every business call. In the demo, GET is called twice in a row on a record, yet the linker does not necessarily run twice. `LinkRequest.getArguments()` holds **the values of the call that triggered linking**, not a data source that automatically updates on subsequent consumer calls.

### `getReceiver()` and Argument Count

In the common model, the receiver is at parameter 0 of the call site. In the example:

```text
GET "color": MethodType (Object)Object
  args[0] = record
  getReceiver() == record
  getArguments().length == 1

SET "color": MethodType (Object,Object)void
  args[0] = record
  args[1] = "blue"
  getArguments().length == 2
```

If an operation is designed without the receiver at parameter 0, linker conventions must be reviewed. `LinkRequest.getReceiver()` retrieves the first argument, so receiver-based property/method call patterns are typically arranged as above. Code must check arity if the operation allows multiple variants, rather than accessing `args[1]` arbitrarily.

`getArguments()` returns a copy of the array per the interface contract. Do not write `request.getArguments()[0]=x` expecting to change the arguments of the original call. To create a new request, use `replaceArguments` with a **valid descriptor and values**, usually so one linker can delegate the rest to other linkers.

### Is `isCallSiteUnstable()` Used to Measure Latency?

No. It is a **hint about relink count**, not invocation count, CPU time, or method slowness. `DynamicLinkerFactory.setUnstableRelinkThreshold(int)` configures when Dynalink considers a site unstable; the factory default is 8 if unconfigured. A linker can choose less specialization to avoid ping-ponging if `isCallSiteUnstable()==true`.

In the demo stdout, every time the custom linker is called it prints `unstable=false`, because the threshold has not been exceeded. Do not infer that every application always sees false; when receiver types change continuously, a site can be marked unstable.

## 5. `CallSiteDescriptor` and Operation Names in the Object Model

Dynalink does not force using a special string like `"GET:PROPERTY:color"` to define names. The `Operation` APIs help describe the structure clearly:

```java
Operation op = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("color");
MethodType type = MethodType.methodType(Object.class, Object.class);
CallSiteDescriptor descriptor = new CallSiteDescriptor(
        MethodHandles.lookup(), op, type);
```

This is a **snippet**; you need to import `jdk.dynalink.Operation`, `StandardOperation`, `StandardNamespace`, `CallSiteDescriptor`, and `java.lang.invoke` classes.

- `StandardOperation.GET`: get operation.
- `StandardNamespace.PROPERTY`: property namespace; distinct from `ELEMENT` or `METHOD`.
- `.named("color")`: **fixed name at the call site**. Another site may use the name `"status"`.
- `MethodType.methodType(Object.class,Object.class)`: runtime caller passes an `Object` receiver and receives an `Object` result. The property name does not appear in the signature because it **is bound at link time**.
- `MethodHandles.lookup()`: lookup context so Dynalink can apply appropriate access permissions when invoking Java members is needed.

A custom linker should not just check `method.getName()` like Reflection. It inspects the **`Operation`** of the descriptor, distinguishing `GET` from `SET`, `PROPERTY` from `ELEMENT`, and the name of `NamedOperation`.

In the demo, we compare:

```java
Operation getProperty =
        StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY);
Operation setProperty =
        StandardOperation.SET.withNamespace(StandardNamespace.PROPERTY);
Operation base = named.getBaseOperation();

if (getProperty.equals(base)) {
    // prepare getter
} else if (setProperty.equals(base)) {
    // prepare setter
}
```

This is a snippet from the linker, not a standalone program. For operations with multiple namespaces, it is often necessary to analyze `NamespaceOperation` and namespace order according to your own semantics; do not treat every `GET` as a property getter regardless of namespace.

## 6. `LinkerServices`: Why Not Just Call `MethodHandle.asType` Everywhere?

`LinkerServices` centralizes the services of `DynamicLinker`; it is **not** a `CallSite`, nor is it a place to store values of the object model.

| API | Meaning | When it is useful |
| --- | --- | --- |
| `asType(handle, desiredType)` | Adapts the handle type, including conversions registered by the language runtime via `GuardingTypeConverterFactory` | Matching a target with internal types to the caller's `MethodType` |
| `asTypeLosslessReturn(handle, desiredType)` | Adapts input types and only converts the return type automatically when the conversion does not lose precision/magnitude | Preserving return policy handling at the pre-link stage |
| `canConvert(from,to)` | Checks whether a corresponding conversion **may exist** | Considering overload/converter selection |
| `getTypeConverter(from,to)` | Retrieves a converter `MethodHandle` between two types | When you truly need to reuse a converter outside the `asType` step |
| `compareConversion(source,t1,t2)` | Compares two type conversion paths | Overload resolution |
| `filterInternalObjects(handle)` | Applies configured internal filters, if any | Preventing runtime-internal objects from leaking across the boundary |
| `getGuardedInvocation(linkRequest)` | Asks the dynamic linker to dispatch another link request | Delegation/composition between linkers |
| `getWithLookup(...)` | Runs an operation in the provided lookup context | Converters that depend on lookup permissions when working outside normal relinking |

**In particular:** `canConvert` returning `true` **does not prove that every runtime value will convert successfully**. For example, casting from `Object` to `String` can succeed when the object is a String and fail for an Integer. Do not use `canConvert(Object.class,String.class)==true` as validation that every Object can become a String.

### 6.1 `asTypeLosslessReturn` in the Demo

The internal getter has the signature:

```text
read(DynamicRecord receiver, String propertyName) : String
```

After binding `propertyName="color"` with `MethodHandles.insertArguments`:

```text
readBound : (DynamicRecord)String
```

The call site, however, requests:

```text
GET color : (Object)Object
```

We use:

```java
MethodType siteType = request.getCallSiteDescriptor().getMethodType();
target = services.asTypeLosslessReturn(target, siteType);
```

The resulting `target` in the GET case has a matching type `(Object)Object`: the `Object` receiver is cast/converted to `DynamicRecord` when called, while the `String` return can be safely widened to `Object`. The guard checks `instanceof DynamicRecord` before the target performs the cast. For the setter, the bound target has `(DynamicRecord,String)void` and is adapted to `(Object,Object)void`; the second argument requires a `String` value.

**Why not convert every return type to the site type directly inside the linker?** The `GuardingDynamicLinker` contract recommends that linkers only perform lossless return conversions; the factory has a **pre-link transformer** to handle final adaptation, which by default applies `GuardedInvocation.asType(LinkerServices,MethodType)`. By keeping responsibilities layered, the runtime can apply language policy for precision-losing conversions or special null behavior centrally.

### 6.2 `GuardingTypeConverterFactory` for Custom Language Conversions

If a language runtime has special numeric/string types, a `GuardingDynamicLinker` can additionally implement `GuardingTypeConverterFactory` to provide conversions according to language semantics; `LinkerServices.asType` will coordinate that converter when adapting `MethodHandle`s.

For example, a language might want to coerce `DynamicNumber` to `BigDecimal` or a locale-specific string that cannot rely solely on Java casts and boxing. A converter must define its **failure contract**, null behavior, overflow, thread-safety, and lookup permissions. Do not automatically assume every Object can be parsed into a number, especially when the caller requests a different overload.

`LinkerServices.getTypeConverter` always returns a handle per the API, but it may be an identity/cast that causes a specific value to fail at runtime. You should not just check that the handle is non-null and conclude conversion for every input is safe.

### 6.3 Calling Back into `LinkerServices.getGuardedInvocation`: Easy to Recurse

A complex linker may want to transform one operation into another operation and then ask the full dynamic linker to find a target. In that case, `LinkerServices.getGuardedInvocation(anotherRequest)` can be useful. However, if called again with the **same request** without changing conditions, the dynamic linker may **call back into the current linker itself**, causing infinite recursion.

Design rules:

1. Only delegate when the new request has a **clearly different operation/arguments/descriptor** and guarantees progress.
2. Use `LinkRequest.replaceArguments(...)` to express the replacement request; do not mutate the `getArguments()` array.
3. Check that the result may be `null`; do not assume a linker will always accept it.
4. Design guards/invalidation for the composed result, avoiding capturing the wrong receiver.
5. Do not use delegation as a business target call; this is **the process of finding how to link**, not per-call data processing.

The basic demo does not use this method because it already has enough logic for GET/SET; that is the right choice when advanced composition is not needed.

## 7. Complete Java 17 Program: Custom Property Object and JavaBean Fallback

The program below is a standalone example, runnable with **JDK 17 or later** with the `jdk.dynalink` module. It creates a custom object model `DynamicRecord` storing properties in a map, a `GuardingDynamicLinker` for GET/SET, a regular JavaBean to test fallback, and two explicitly typed call sites.

**Create the file `CustomDynalinkDemo.java`**, with no dependencies outside the JDK. The file name **must match** the public class name.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.HashMap;
import java.util.Map;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.NamedOperation;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.linker.GuardedInvocation;
import jdk.dynalink.linker.GuardingDynamicLinker;
import jdk.dynalink.linker.LinkRequest;
import jdk.dynalink.linker.LinkerServices;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class CustomDynalinkDemo {
    static final class DynamicRecord {
        final Map<String, String> fields = new HashMap<>();
        DynamicRecord(String color) { fields.put("color", color); }
    }

    public static final class JavaBean {
        private final String color;
        public JavaBean(String color) { this.color = color; }
        public String getColor() { return color; }
    }

    public static boolean isRecord(Object receiver) {
        return receiver instanceof DynamicRecord;
    }

    public static String read(DynamicRecord receiver, String key) {
        return receiver.fields.get(key);
    }

    public static void write(DynamicRecord receiver, String key, String value) {
        receiver.fields.put(key, value);
    }

    static final class RecordLinker implements GuardingDynamicLinker {
        static final MethodHandle READ;
        static final MethodHandle WRITE;
        static final MethodHandle GUARD;
        int linkCount;

        static {
            try {
                MethodHandles.Lookup lookup = MethodHandles.lookup();
                READ = lookup.findStatic(CustomDynalinkDemo.class, "read",
                        MethodType.methodType(String.class, DynamicRecord.class, String.class));
                WRITE = lookup.findStatic(CustomDynalinkDemo.class, "write",
                        MethodType.methodType(void.class, DynamicRecord.class, String.class, String.class));
                GUARD = lookup.findStatic(CustomDynalinkDemo.class, "isRecord",
                        MethodType.methodType(boolean.class, Object.class));
            } catch (ReflectiveOperationException ex) {
                throw new ExceptionInInitializerError(ex);
            }
        }

        @Override
        public GuardedInvocation getGuardedInvocation(
                LinkRequest request, LinkerServices services) throws Exception {
            if (!(request.getReceiver() instanceof DynamicRecord)) {
                return null; // let BeansLinker or another linker try
            }
            Operation op = request.getCallSiteDescriptor().getOperation();
            if (!(op instanceof NamedOperation named)
                    || !(named.getName() instanceof String key)) {
                return null;
            }
            Operation base = named.getBaseOperation();
            Operation getProperty =
                    StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY);
            Operation setProperty =
                    StandardOperation.SET.withNamespace(StandardNamespace.PROPERTY);
            MethodHandle target;
            MethodHandle guard = GUARD;
            if (getProperty.equals(base)) {
                target = MethodHandles.insertArguments(READ, 1, key); // (DynamicRecord)String
            } else if (setProperty.equals(base)) {
                target = MethodHandles.insertArguments(WRITE, 1, key); // (DynamicRecord,String)void
                guard = MethodHandles.dropArguments(GUARD, 1, Object.class);
            } else {
                return null;
            }

            MethodType siteType = request.getCallSiteDescriptor().getMethodType();
            target = services.asTypeLosslessReturn(target, siteType);
            linkCount++;
            System.out.println("link:" + (getProperty.equals(base) ? "GET" : "SET")
                    + ":" + key + ":args=" + request.getArguments().length
                    + ":unstable=" + request.isCallSiteUnstable());
            return new GuardedInvocation(target, guard);
        }
    }

    static MethodHandle siteInvoker(DynamicLinker linker,
                                    StandardOperation operation, String name,
                                    MethodType type) {
        CallSiteDescriptor desc = new CallSiteDescriptor(
                MethodHandles.lookup(),
                operation.withNamespace(StandardNamespace.PROPERTY).named(name),
                type);
        return linker.link(new SimpleRelinkableCallSite(desc)).dynamicInvoker();
    }

    public static void main(String[] args) throws Throwable {
        RecordLinker custom = new RecordLinker();
        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setPrioritizedLinker(custom);
        DynamicLinker linker = factory.createLinker();

        MethodHandle get = siteInvoker(linker, StandardOperation.GET, "color",
                MethodType.methodType(Object.class, Object.class));
        MethodHandle set = siteInvoker(linker, StandardOperation.SET, "color",
                MethodType.methodType(void.class, Object.class, Object.class));
        DynamicRecord record = new DynamicRecord("red");
        JavaBean bean = new JavaBean("green");

        System.out.println("get.type=" + get.type());
        System.out.println("set.type=" + set.type());
        System.out.println("record.1=" + (Object) get.invokeExact((Object) record));
        System.out.println("record.2=" + (Object) get.invokeExact((Object) record));
        System.out.println("bean=" + (Object) get.invokeExact((Object) bean));
        System.out.println("record.3=" + (Object) get.invokeExact((Object) record));
        set.invokeExact((Object) record, (Object) "blue");
        System.out.println("record.4=" + (Object) get.invokeExact((Object) record));
        System.out.println("custom.links=" + custom.linkCount);
    }
}
```

### 7.1 Compiling and Running

Run from the directory containing `CustomDynalinkDemo.java` with **JDK 17+**:

```bash
javac --release 17 --add-modules jdk.dynalink -encoding UTF-8 CustomDynalinkDemo.java
java --add-modules jdk.dynalink CustomDynalinkDemo
```

`jdk.dynalink` is a JDK module since Java 9, but it is not in `java.base`; for an application run on the **classpath** like the demo, add `--add-modules jdk.dynalink` to ensure the module is included in the module graph. In a modular application using JPMS, you can declare `requires jdk.dynalink;` in `module-info.java` instead of the classpath configuration in the example.

**Exact stdout of the example verified with `javac --release 17` and a JDK with the Dynalink module:**

```text
get.type=(Object)Object
set.type=(Object,Object)void
link:GET:color:args=1:unstable=false
record.1=red
record.2=red
bean=green
link:GET:color:args=1:unstable=false
record.3=red
link:SET:color:args=2:unstable=false
record.4=blue
custom.links=3
```

### 7.2 Line-by-Line Output Analysis

1. `get.type=(Object)Object` and `set.type=(Object,Object)void` show the **call-site MethodTypes**. They do not have to match the Java signatures of the internal getter/setter.
2. **First GET call:** the receiver is `DynamicRecord`, no guard/link exists yet. Dynalink calls `RecordLinker.getGuardedInvocation`. The linker supports `GET PROPERTY color`, binds `key="color"`, and returns a guarded invocation. The line `link:GET:color:args=1:unstable=false` is printed **during linking**.
3. `record.1=red` is the result of the target `read(DynamicRecord,"color")`. This is the actual business logic.
4. `record.2=red` has no second `link:GET` line: the guard matches and `SimpleRelinkableCallSite` reuses the cached linkage. The linker **does not run again on every request**.
5. `bean=green`: the receiver is `JavaBean`, the `isRecord` guard is no longer true, and Dynalink performs a relink. The custom linker **returns `null`**, then the fallback `BeansLinker` resolves `getColor()` according to JavaBean semantics.
6. `record.3=red`: the receiver switches back to `DynamicRecord`. The monomorphic cache of `SimpleRelinkableCallSite` had switched to the bean, so it must re-link the custom GET. Therefore, there is a second `link:GET...` line.
7. `link:SET:color:args=2:unstable=false`: a **different call site** handles `SET PROPERTY color` with 2 parameters; the custom linker binds the property name and prepares the setter.
8. `record.4=blue`: the setter changes the value in the map. The GET call site still has a matching custom guard, so **no relink is needed** just because the value in the map changed from red to blue. The target reads the map when invoked.
9. `custom.links=3`: in the trace there are three **times the custom linker created a guarded invocation** (first GET record, GET record after bean, SET record). This is not the total number of times `get.invokeExact` executed, nor does it count `BeansLinker` links.

If you replace `DynamicRecord` with an implementation that has a flexible layout/shape, examine the guard carefully. In the demo, the target **does not cache the key's value**, so a guard based only on receiver type is sufficient. If the target is optimized by slot position, field order, or class shape version, a type-only guard may return wrong data after the structure changes.

## 8. Reading the Code by Linkage Construction Steps

### Step A — Prepare `MethodHandle`s for Custom Logic

```java
READ = lookup.findStatic(CustomDynalinkDemo.class, "read",
        MethodType.methodType(String.class, DynamicRecord.class, String.class));
WRITE = lookup.findStatic(CustomDynalinkDemo.class, "write",
        MethodType.methodType(void.class, DynamicRecord.class, String.class, String.class));
GUARD = lookup.findStatic(CustomDynalinkDemo.class, "isRecord",
        MethodType.methodType(boolean.class, Object.class));
```

This is a **snippet** from `RecordLinker`, not standalone. Handle lookup is done once in the static initializer; if the method cannot be found or access is denied, class initialization fails clearly. In a real product, consider managing lookups and bootstrap errors separately.

Initial types:

```text
READ  : (DynamicRecord,String)String
WRITE : (DynamicRecord,String,String)void
GUARD : (Object)boolean
```

### Step B — Check Receiver/Operation

```java
if (!(request.getReceiver() instanceof DynamicRecord)) {
    return null;
}
Operation op = request.getCallSiteDescriptor().getOperation();
if (!(op instanceof NamedOperation named)
        || !(named.getName() instanceof String key)) {
    return null;
}
```

This is **part of the `getGuardedInvocation` method** in the complete code. A linker concerned with `DynamicRecord` needs to reject JavaBeans, plain Java Maps, or other runtime objects; therefore, it should not cast just any receiver to `DynamicRecord`.

### Step C — Bind the Property Name, Not the Value

```java
target = MethodHandles.insertArguments(READ, 1, key);
```

The `key` variable holds the fixed name of the site (e.g. `"color"`); the new `target` has type `(DynamicRecord)String`. When invoked, it still reads `receiver.fields.get("color")` **at call time**, without remembering the `"red"` string from link time.

For the setter:

```java
target = MethodHandles.insertArguments(WRITE, 1, key);
```

The new target has type `(DynamicRecord,String)void`. The remaining two parameters are **the receiver and value actually passed on each call**. You must not bind the `"blue"` value obtained from `LinkRequest.getArguments()[1]` if you want the setter to support all future values.

### Step D — Guards for GET and SET

GET has one receiver argument:

```text
GET target: (Object)Object
GET guard:  (Object)boolean
```

SET has two arguments, so the guard is padded with a second parameter **that is ignored**:

```java
guard = MethodHandles.dropArguments(GUARD, 1, Object.class);
```

Result:

```text
SET target: (Object,Object)void
SET guard:  (Object,Object)boolean
```

The guard only checks that parameter 0 is a `DynamicRecord`. The value parameter does not participate in type ownership checking, because the target will cast the value to `String` per the demo contract. If a language runtime wants to support different value types, a corresponding converter and/or guard must be designed.

### Step E — Adapt via `LinkerServices` and Return `GuardedInvocation`

```java
MethodType siteType = request.getCallSiteDescriptor().getMethodType();
target = services.asTypeLosslessReturn(target, siteType);
return new GuardedInvocation(target, guard);
```

This snippet belongs to the linker method. `GuardedInvocation` holds **invocation + guard**, for `DynamicLinker` to install into `RelinkableCallSite`. The linker does not hold onto the target afterward to run every call itself, unless intentionally designed otherwise. `LinkerServices` converts parameters according to policy, while final adaptation belongs to Dynalink's linking pipeline.

### Step F — Create the Call Site and Obtain a Live Invoker

```java
CallSiteDescriptor desc = new CallSiteDescriptor(
        MethodHandles.lookup(),
        StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY)
                .named("color"),
        MethodType.methodType(Object.class, Object.class));

MethodHandle get = linker.link(
        new SimpleRelinkableCallSite(desc)).dynamicInvoker();
```

The snippet above requires an initialized `DynamicLinker linker`. `DynamicLinker.link(...)` initially installs a relink mechanism; **the first call** with an actual receiver is usually what asks the custom linker to create a guarded invocation. `dynamicInvoker()` continues pointing to the call site, even after the target is relinked; there is no need to obtain a new invoker after each receiver change.

## 9. Guard: Correctness Matters More Than Cache Hit Rate

A `GuardedInvocation` is only safe when the guard describes **sufficient validity conditions** for the invocation.

| Optimization based on | Guard/invalidation to consider |
| --- | --- |
| Only objects of custom model `DynamicRecord` | `instanceof DynamicRecord` may suffice |
| Target bound to a specific instance | Identity check `receiver == capturedReceiver` |
| Target uses shape/property layout offsets | Check shape/version; possibly add `SwitchPoint` |
| Target assumes input value is always String | Guard value class or explicit converter/cast policy |
| Target depends on authorization/tenant | Check policy at invocation or reliable invalidation mechanism |
| Target based on a replaceable method implementation | Invalidate when implementation version changes |

An overly broad guard is a **correctness bug**: the old target is called for an incompatible receiver/shape, potentially returning wrong data or causing type errors. An overly narrow guard is usually data-correct but causes **continuous relinking**, hurting performance.

Do not return an **unguarded** `GuardedInvocation(target)` for a specialized target that only accepts `DynamicRecord`, because the same call site may later be called with a JavaBean. Then Dynalink has no clear signal to relink. Unconditional linkage only makes sense when the invocation truly applies to **all future arguments** of the site.

### Combining `SwitchPoint` with a Guard

A guard like `instanceof` checks the condition at invocation time. A `SwitchPoint` can represent **proactive invalidation** when the runtime changes a schema, method table, module version, or policy. `GuardedInvocation` supports a constructor taking a guard along with a switch point, for example snippet:

```java
SwitchPoint switchPoint = new SwitchPoint();
GuardedInvocation linked =
        new GuardedInvocation(target, guard, switchPoint);

// When model/scheme version is changed:
SwitchPoint.invalidateAll(new SwitchPoint[]{switchPoint});
```

This snippet is **not a standalone program**; it requires `MethodHandle target/guard` with compatible signatures and importing `java.lang.invoke.SwitchPoint`. Invocations built with the switch point can fall back/relink after it is invalidated. An invalidated switch point **cannot be reset**; a new version usually requires a new switch point.

**In practice:** `SwitchPoint` does not automatically synchronize internal mutable fields, does not revoke requests already inside the old target, and does not apply transactions across multiple call sites. Concurrency, lifecycle, and version design require their own rules.

### Exceptions as Relink Conditions

`GuardedInvocation` can also include a `Class<? extends Throwable>` indicating an exception treated as a signal that the linkage is no longer valid. For example, a runtime might use a rare `ClassCastException` to trigger relinking instead of checking `instanceof` every time. This mechanism should only be used if the exception **truly means** "the cached target's assumption is wrong", not using arbitrary business exceptions as a signal to change targets.

If a target throws `IllegalArgumentException` because of invalid user input, you should not automatically treat that as a guard failure and relink infinitely. Distinguish business logic exceptions from exceptions related to type/shape specialization.

## 10. `SimpleRelinkableCallSite`, `ChainedCallSite`, and Relinking Strategy

The example uses `SimpleRelinkableCallSite`, which belongs to the **monomorphic inline cache** category: it keeps only one active guarded invocation. When the receiver changes from `DynamicRecord` to JavaBean, the record target's guard is no longer true, and Dynalink needs to link to the JavaBean. When switching back to record, it needs to link again.

`ChainedCallSite` provides a **polymorphic inline cache** style, able to hold a chain of multiple guarded invocations. It is often suitable when a call site encounters a few stable receiver shapes/types. However, you must benchmark the workload:

| Scenario | `SimpleRelinkableCallSite` | `ChainedCallSite` |
| --- | --- | --- |
| Almost always a single receiver type | Very simple, minimal guard chain | May add unnecessary complexity |
| Alternating 2–4 types | May relink continuously | Can reduce relinks via multi-type cached guards |
| Too many types/shape churn | Many relinks, may become megamorphic | Chain can also become long/expensive; limits and runtime strategy matter |
| Model state changes continuously | Needs proper invalidation | Still needs proper invalidation; does not auto-fix wrong guards |

Dynalink does not read a `Map` on its own to determine an object model. A cache strategy only makes sense if the linker produces the right invocation and guard. Also do not assume `ChainedCallSite` guarantees every object stays cached forever: chain limits, invalidation, and unstable thresholds can trigger resets/relinks.

### Multithreading Semantics

`SimpleRelinkableCallSite` and `ChainedCallSite` are based on the mutable call-site model. `DynamicLinkerFactory.setSyncOnRelink(boolean)` determines whether `MutableCallSite.syncAll(...)` is called on relink to coordinate visibility across threads. The factory Javadoc recommends considering `true` if the runtime supports multiple threads; the default is `false`.

In the demo there is **only one thread**, so there is no need to change the config to demonstrate the meaning of `GuardingDynamicLinker`. Multithreaded applications must consider `setSyncOnRelink(true)` and separate synchronization for target data; **`setSyncOnRelink` does not automatically make a mutable `HashMap` thread-safe**. When a record's getter/setter are called concurrently, the map must be protected (or a concurrent data structure chosen) according to the actual concurrency model.

## 11. Linker Priority and JavaBean Interoperability

`DynamicLinkerFactory` organizes multiple layers:

```text
setPrioritizedLinker(custom)
            |
            v
 custom GuardingDynamicLinker
   -> accepts DynamicRecord?
            |
       yes /    \ no: return null
          |       |
          v       v
       custom    other discovered linkers
       target       |
                    v
                default BeansLinker fallback
                    |
                JavaBean.getColor()
```

An important configuration point:

- `setPrioritizedLinker(custom)` adds the custom linker to a position that is queried early.
- `GuardingDynamicLinkerExporter`s can be automatically discovered via class loader/service loading when configured appropriately; that is an advanced interoperability capability.
- If no other fallback is specified, the factory defaults to having **`BeansLinker`** to handle regular Java objects.
- If `setFallbackLinkers(...)` is called with an empty list, it can remove the default fallback; **do not** assume `BeansLinker` remains at the end of the pipeline after every configuration.
- `getGuardedInvocation` returning `null` is the natural way to pass the opportunity to the next linker; if no linker understands the operation, Dynalink may fail during linking.

In the demo, JavaBean has:

```java
public static final class JavaBean {
    private final String color;
    public JavaBean(String color) { this.color = color; }
    public String getColor() { return color; }
}
```

This is a type snippet already present in the full program. It is **not** a `DynamicRecord` and the custom linker skips it. Default `BeansLinker` accepts `GET PROPERTY color`, uses the public getter `getColor()`, so the console outputs `bean=green` **without a `link:GET` line produced by the custom linker**. This is a live example of coordination between a custom object model and Java semantics.

## 12. Defining the Object Model More Carefully: GET/SET, Missing Properties, and Value Types

The demo chooses a clear goal: property names are `String`, values in `DynamicRecord` are also `String`, GET returns `String`, and SET accepts `String`.

### Missing Property

`Map.get(key)` returns `null` if the key does not exist (and also if the value is null in a map that permits null). The demo does not distinguish these two cases. In a dynamic language, you might want to:

- Return a runtime-defined `undefined` value.
- Throw an exception indicating the property does not exist.
- Allow fallback to a prototype/parent object.
- Automatically create the property with a default value.
- Return `null` as in the demo.

**This is a language/object model policy**, not a mandatory Dynalink default. When there are multiple namespaces (PROPERTY, ELEMENT, METHOD), clear ordering and priority rules must be defined.

### Value Types and Type Conversion

`SET` in the demo has call site `(Object,Object)void` but the internal setter requires `String`. `LinkerServices` adapts the target to the `MethodType`; if the caller passes an `Integer` as the value, an incompatible cast/conversion may throw an exception. Do not treat `canConvert` as a promise that every Object becomes a String semantically.

If your language specifies that `42` must become `"42"`, implement a concrete converter or intentionally normalize the value before calling the target. This should be tested with `null`, numbers, booleans, user-defined objects, and exceptions, without calling `toString()` on everything indiscriminately if there is sensitive data or side effects.

### Bind the **Name**, Not the **Value**

When linking `GET PROPERTY color`, the line:

```java
MethodHandles.insertArguments(READ, 1, key);
```

only fixes the key `"color"`. This is the benefit of `NamedOperation`: the property name is part of the operation descriptor and is usually stable at the call site; the receiver/value changes at runtime. If code accidentally binds the first value `"red"` that it read from `LinkRequest.getArguments()`, a GET after a SET to blue may still return red, even though the type guard is still valid. If you want to cache **values**, you must have appropriate invalidation/guards/versioning.

## 13. Which API Does What During Relinking?

| Practical question | Right place to handle it |
| --- | --- |
| "What are the operation name and call site type?" | `request.getCallSiteDescriptor().getOperation()/getMethodType()` |
| "What object is the receiver for this link?" | `request.getReceiver()` |
| "How many argument values are in this link?" | `request.getArguments().length` |
| "Has the site relinked many times?" | `request.isCallSiteUnstable()` |
| "Does the custom model understand this receiver?" | `GuardingDynamicLinker` logic (return null if not) |
| "Which target handle reads a property from the Map?" | `MethodHandles.findStatic/insertArguments` |
| "Under what condition can the target be used?" | `GuardedInvocation` guard + switch points/exception if needed |
| "How does the target adapt its type to the caller's contract?" | `LinkerServices.asType/asTypeLosslessReturn` and pre-link transformer |
| "How is a JavaBean handled when the custom linker declines?" | Subsequent linkers, usually default `BeansLinker` |
| "When a guard fails, does the user need to rebuild the call site manually?" | No; `RelinkableCallSite` and `DynamicLinker` coordinate relinking |
| "How to keep multiple receiver type specializations?" | See `ChainedCallSite`, guard chains, and unstable threshold |
| "How are Java method permissions enforced?" | `CallSiteDescriptor` lookup context and Java access/module checks |
| "When the schema changes, how to invalidate?" | Version/shape guard or `SwitchPoint` with a proper protocol |

In particular, if you want to log the number of business calls, **do not just put a counter inside `getGuardedInvocation`**. It only counts **link/relink occurrences**. To count all business invocations, add instrumentation to the target handle or the code executed by the target.

## 14. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Not returning `null` when receiver is not in the model | Linker "hijacks" JavaBeans, causing cast/wrong-read errors | Return `null` for unsupported receiver/operation |
| Returning an unconditional invocation specialized for `DynamicRecord` | Later when receiver is a JavaBean it still calls the old target | Return a proper `instanceof`/shape guard |
| Guarding by class while target binds a specific object | Another receiver of the same class uses the old object's target | Guard identity or do not bind the object |
| Guarding by class while target depends on schema version | Cache is still used after schema changes | Version guard/`SwitchPoint` invalidation |
| Using `LinkRequest.getArguments()` as mutable state for every call | Request only provides a **link-time snapshot** | Future calls receive real args via the target signature |
| Mutating the array from `getArguments()` to change dispatch | Contract returns an array clone | Use `replaceArguments` when creating a new request |
| Calling `LinkerServices.getGuardedInvocation` with the same request | Can recurse back into the same linker | Create a genuinely different request or do not delegate |
| Mismatching target/guard `MethodType` | Runtime linkage/adaptation may fail | Print `.type()` and check `MethodType` against the site |
| Using `MethodHandle.asType` arbitrarily, bypassing custom converters | Fails to apply the language runtime's conversion policy | Use `LinkerServices` and a verified policy |
| Returning a value in `getGuardedInvocation` instead of `GuardedInvocation` | Confuses linking with invocation | Create a `MethodHandle` and wrap it per the API |
| Parsing operations using ambiguous string names only | GET property and GET element/method get mixed up | Use `StandardOperation`, `NamespaceOperation`, `NamedOperation` |
| Assuming a fallback always exists | Factory may be configured without `BeansLinker` | Check `setFallbackLinkers` and runtime wiring |
| Counting relinks as counting business requests | One linkage is invoked many times | Instrument the target if you want business call statistics |
| Using `SimpleRelinkableCallSite` when alternating many types | Can ping-pong relink | Consider `ChainedCallSite` and benchmark |
| Thinking `setSyncOnRelink(true)` makes all state safe | Only handles visibility of call site relinks | Synchronize mutable state of the custom object model separately |
| Forgetting `--add-modules jdk.dynalink` on classpath | Module may not be resolved | Add the module at compile/run or use `requires` in JPMS |
| Using `MethodHandles.lookup()` of a class without member access | Handle creation may throw `IllegalAccessException` | Use a valid lookup context, respecting module access |
| Letting linkers mutate shared mutable maps unsynchronized | Data races when multiple threads GET/SET | Concurrent map/locks/immutable version protocol |
| Treating `canConvert` true as guaranteed conversion success | Some values can fail to cast | Test runtime values, validate explicitly |

## 15. Debugging a Dynamic Call Site Returning Wrong Results

Practical investigation workflow:

1. **Print `CallSiteDescriptor`:** inspect `operation`, `MethodType`, lookup context; is the property name correct?
2. **Check the receiver:** what object model is `LinkRequest.getReceiver()`? If null/JavaBean/plain Map, did the custom linker intentionally decline?
3. **Read `getArguments()` to inspect the link call:** but do not confuse it with all subsequent calls.
4. **Check the operation:** does `NamedOperation` have the right name? Is the base operation GET/SET + PROPERTY, not ELEMENT/METHOD?
5. **Check linker order:** was custom actually added via `setPrioritizedLinker` before the fallback?
6. **If custom returns `null`:** check whether other linkers or `BeansLinker` understand the receiver and operation.
7. **Check method handle types:** before and after `insertArguments`, `services.asTypeLosslessReturn`, `new GuardedInvocation(...)`.
8. **Check guard semantics:** does the guard become false properly when the receiver type changes? Is it too broad when object schema changes?
9. **Track relink count:** if types alternate, `SimpleRelinkableCallSite` may relink frequently; consider `ChainedCallSite`.
10. **If it only fails under multithreading:** check `setSyncOnRelink`, target mutable state, invalidation, and races.
11. **If access errors occur:** check `CallSiteDescriptor` lookup, JPMS exports/opens, class loader identity, and target method permissions.
12. **If conversion errors occur:** check `LinkerServices.canConvert/getTypeConverter` and the `GuardingTypeConverterFactory` policy.
13. **If inputs appear stuck after linking:** check whether a value from the request was accidentally bound instead of using the target's runtime parameters.
14. **Do not assume every call invokes the linker:** place tracing at both **linking** and **invocation** with distinct labels.

Inspection snippet at link time, not a standalone program:

```java
CallSiteDescriptor descriptor = request.getCallSiteDescriptor();
System.out.println("operation=" + descriptor.getOperation());
System.out.println("type=" + descriptor.getMethodType());
System.out.println("receiver=" +
        (request.getReceiver() == null
            ? "null" : request.getReceiver().getClass().getName()));
System.out.println("unstable=" + request.isCallSiteUnstable());
```

**Logging note:** do not print `request.getArguments()` verbatim in production if it may contain passwords, tokens, PII data, or objects with expensive/side-effecting `toString()`. Logging the operation name, class identity, and argument count is enough to diagnose most relinking bugs without leaking data.

## 16. Production Design: Access Rights, Lifecycle, Performance, and Boundaries

### 16.1 Java Access and Module Boundaries

`CallSiteDescriptor` contains `MethodHandles.Lookup` to inform linkers of the caller's context. When a custom linker looks up `private`/package-private methods or when `BeansLinker` links Java members, Java language access rules, module exports/opens, and runtime class loader identity all matter.

Do not assume `MethodHandles.lookup()` called inside a linker class always has permission to access a consumer's private members. If you need to support objects from other modules, design public/exported APIs, appropriate lookup capabilities, and reject invalid access. Dynalink is not a tool to automatically "bypass private" in the JVM.

For JPMS apps, the application module should declare `requires jdk.dynalink;`. For classpath demos, add `--add-modules jdk.dynalink`. Do not confuse the Java `jdk.dynalink` module/namespace with the `java.lang.invoke` package: Dynalink is built **on top of** `MethodHandle`/`CallSite`, but provides a higher operation/linker layer.

### 16.2 A Linker Is Not Per-Object Storage

A custom linker should emit target handles for the object model; if a handler needs per-instance storage, use the object receiver/adapter explicitly. Caching `GuardedInvocation` belongs to the call site; it does not mean the system automatically caches property values. In the demo, a fresh property is read from the `HashMap` on each invocation.

If the object model has lazily computed properties or an inheritance/prototype chain, build guards and invalidation to match that model. You should not hide business state in a global static Map on the linker without a concurrency/lifecycle policy.

### 16.3 Avoiding Premature Specialization

If a site usually receives `DynamicRecord`, caching a target by class can be effective. If it receives hundreds of object shapes, long guard chains or continuous linking can be expensive. `isCallSiteUnstable()` provides a signal to choose a less specialized target. Measure: relink count, guard miss rate, fallback path, latency, and GC. Do not measure only linker call time and conclude the runtime is fast/slow: most calls may be using the cached target.

### 16.4 Protecting Data and Errors

A property lookup is not guaranteed valid just because the guard is true. The custom model still needs to handle missing keys, `null` policy, stale snapshots, wrong value types, and errors from the underlying Map/database. Do not use relinking for every business exception; not every error means the cached linkage is no longer valid.

In a runtime executing untrusted code, dynamic property access can also be an access-control point. Guarding by Java type **does not** prove the user is authorized to read every key. Authorization must be checked in the target or via a securely designed invalidation/version policy; replacing a linker does not create a sandbox by itself.

## 17. Exercises and Answers

**Question 1.** Is `GuardingDynamicLinker` where business logic executes on every dynamic call?

**Answer:** No. It creates a `GuardedInvocation` when linking/relinking is needed. After the target is cached, many calls go through the handle without calling the linker again.

**Question 2.** When the receiver is a JavaBean and the custom linker only supports `DynamicRecord`, what value should be returned from `getGuardedInvocation`?

**Answer:** Return **`null`** so subsequent linkers, typically the `BeansLinker` fallback, get a chance to handle it. Do not throw a cast exception as a default fallback mechanism.

**Question 3.** A GET call site has type `(Object)Object`. The internal linker has `read(DynamicRecord,String)String`. What needs to be done?

**Answer:** Bind the property name with `insertArguments` to `(DynamicRecord)String`, then adapt with `LinkerServices.asTypeLosslessReturn` and return a guarded invocation with an appropriate receiver guard.

**Question 4.** Why can an `(Object)boolean` guard that only checks `instanceof DynamicRecord` be right for the demo, yet wrong if the target caches field offsets by schema?

**Answer:** The demo target reads the Map by key name on every invocation. If a cached target depends on shape/version, a type guard is too broad and needs a shape/version guard or switch point invalidation.

**Question 5.** If the same GET call site is called twice in a row on `DynamicRecord`, is `getGuardedInvocation` always called twice?

**Answer:** No. `SimpleRelinkableCallSite` can use the cached guarded invocation on the second call if the guard is valid; the demo stdout reports only one custom link for the first two GET calls.

**Question 6.** How do `LinkRequest.getReceiver()` and `getArguments()` differ?

**Answer:** `getReceiver()` is the first argument of the linking call (avoiding cloning the entire array), whereas `getArguments()` returns a cloned array containing all args at linking time; they are not the values of all future invocations.

**Question 7.** Does `isCallSiteUnstable()` mean the current invocation is too slow?

**Answer:** No. It is a hint that the site has relinked too many times relative to the threshold; the linker can choose a more stable specialization, not a latency measurement.

**Question 8.** `LinkerServices.canConvert(Object.class,String.class)` returns true. Does this guarantee an `Integer` will convert to `String`?

**Answer:** No. `true` only indicates a conversion may exist according to type-level logic; a specific value can still fail.

**Question 9.** A custom linker calls `LinkerServices.getGuardedInvocation(request)` with the very request it is handling. What is the risk?

**Answer:** The dynamic linker may call the same custom linker again with the same request → infinite recursion. You must create a different request with clear progress or not delegate.

**Question 10.** Why does `SimpleRelinkableCallSite` in the demo link the custom GET twice when there is an intermediate call on a JavaBean?

**Answer:** It has a **monomorphic cache**. When the Bean invalidates the record's guard, the cached linkage switches to the Bean; returning to the record requires a custom relink again.

**Question 11.** To keep cached targets for multiple receiver types at one site, which class should be considered?

**Answer:** `ChainedCallSite`, a polymorphic inline cache. You still must ensure guards are correct and benchmark according to the type mix.

**Question 12.** Does `setSyncOnRelink(true)` make a `HashMap` used by a record thread-safe?

**Answer:** No. It is a mechanism to synchronize mutable call-site updates; Map data needs its own concurrency policy.

**Question 13.** SET property in the demo has 2 parameters. How does the guard from `isRecord(Object)` need to be adapted?

**Answer:** Use `MethodHandles.dropArguments(GUARD, 1, Object.class)` to accept the extra value argument while only checking the receiver. The resulting guard is `(Object,Object)boolean`.

**Question 14.** Does a setter changing `red` to `blue` in the same `DynamicRecord` force GET to relink?

**Answer:** No. In the demo, the getter reads the Map at invocation-time and the class guard remains valid. If an implementation caches values, a different invalidation is needed.

**Question 15.** One call site requests GET PROPERTY "color" and another site requests SET PROPERTY "color". Do they share the same `MethodType`?

**Answer:** No. GET uses `(Object)Object`; SET in the demo uses `(Object,Object)void`. Both the operation and the signature differ.

**Question 16.** When the custom model does not support an operation, should the custom linker fall back on its own using `method.invoke(proxy)`?

**Answer:** No. Return `null` so Dynalink asks other linkers, or use `LinkerServices.getGuardedInvocation` with a controlled different request. Calling back into a proxy/call site indiscriminately can create a loop.

**Question 17.** Can a linker return a `GuardedInvocation` without a guard?

**Answer:** Yes when the invocation is truly **unconditional** for all future arguments, but for a type-specialized target there usually must be a guard or another invalidation mechanism.

**Question 18.** How does `NamedOperation` differ from `StandardNamespace.PROPERTY`?

**Answer:** `NamedOperation` attaches a **fixed name** (for example `"color"`) to an operation; `PROPERTY` describes the **namespace** of the action. GET/SET describe the action verb.

## 18. Knowledge Summary

- **Dynalink connects dynamic operations with MethodHandle/CallSite**, rather than replacing the Java language or Java reflection on its own.
- **`GuardingDynamicLinker`** receives `LinkRequest` + `LinkerServices`, chooses a target by receiver/operation, and returns a `GuardedInvocation` with a sufficiently strong guard. **Return null** if unsupported so other linkers can try.
- **`LinkRequest`** describes a link/relink occurrence, including descriptor, receiver, link-time args, and unstable hint; **it is not every business invocation**.
- **`LinkerServices`** handles adaptation/conversions, coordinates type converters, and fallback delegation; `asTypeLosslessReturn` avoids lossy return coercion inside custom linkers.
- **`CallSiteDescriptor`** describes GET/SET PROPERTY names and `MethodType`; `SimpleRelinkableCallSite` is a monomorphic cache while `ChainedCallSite` supports polymorphic caching.
- **Guards determine correctness:** receiver type/identity/shape/version must match the specialized assumptions. When a guard is false or invalidated, Dynalink relinks.
- **Custom object models and JavaBeans can coexist:** a prioritized custom linker handles `DynamicRecord`, while fallback `BeansLinker` handles `getColor()`.
- **Keep boundaries clear:** relinking is different from invocation; caching method handles is different from caching data values; `setSyncOnRelink` is different from synchronizing mutable business state; Dynalink does not bypass Java access controls.

### Official Java SE 17 Documentation

- [`jdk.dynalink` module overview — dynamic operations, language-specific linkers, and JavaBeans interoperability](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html)
- [`GuardingDynamicLinker` — `getGuardedInvocation` contract and guard semantics](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardingDynamicLinker.html)
- [`LinkRequest` — descriptor, receiver, arguments, unstable hint, and replaceArguments](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/LinkRequest.html)
- [`LinkerServices` — asTypeLosslessReturn, asType, canConvert, getTypeConverter, and composition](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/LinkerServices.html)
- [`GuardedInvocation` — invocation, guard, switch points, and exception-based invalidation](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/GuardedInvocation.html)
- [`DynamicLinkerFactory` — priority/fallback linkers, syncOnRelink, and unstable threshold](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html)
- [`DynamicLinker` — linking and `RelinkableCallSite`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html)
- [`SimpleRelinkableCallSite` and `ChainedCallSite` — cache strategies](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html)
