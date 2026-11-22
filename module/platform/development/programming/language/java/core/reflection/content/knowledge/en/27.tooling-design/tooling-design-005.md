# Handling Duplicate-Name Fields and Overridden Methods with a Consistent Policy When Using Reflection

When scanning a class hierarchy, **duplicate-name fields** and **overridden methods** require two distinct policies. Fields on a superclass and subclass remain two separate storage locations; overridden methods use dynamic dispatch based on the receiver. `getDeclaredFields()`/`getDeclaredMethods()` only report declarations on each class and do not guarantee order, so keeping the first element encountered can change results.

This article builds a registry with explicit signature keys, traversal order from the concrete class up to superclasses, and an intentional *closest declaration wins* choice. If an application must preserve every field sharing the same name, it must use a key incorporating the declaring class or report a collision, rather than merging silently.

## 1. Field hiding differs from method overriding

### 1.1. Fields with the same name are two separate data slots

~~~java
class Parent {
    public String id = "parent";
}

class Child extends Parent {
    public String id = "child";
}
~~~

`Child.id` **hides** `Parent.id` under source-code name resolution. Yet a `Child` instance still **contains both fields**:

- `child.id` reads the `Child.id` field.
- `((Parent) child).id` reads the `Parent.id` field.
- `Child.class.getDeclaredField("id")` returns the declaration on `Child`.
- `Parent.class.getDeclaredField("id")` returns the declaration on `Parent`.
- `Field.get(child)` reads the exact **field represented by that `Field` object**, even when the receiver is a subclass instance; it does not automatically redirect to a same-named field on the subclass.

Therefore, choosing the subclass's field to represent the `id` key is a **schema-flattening policy**, not an indication that the superclass field vanished. If a serializer must retain both values, it must use keys qualified with the declaring class (e.g., `Parent#id`, `Child#id`) or report a conflict; never silently merge both.

### 1.2. Method overriding is dynamically dispatched behavior

~~~java
class Parent {
    public String label() { return "parent"; }
}

class Child extends Parent {
    @Override
    public String label() { return "child"; }
}
~~~

`Child.label()` **overrides** `Parent.label()`. A normal instance call `new Child().label()` uses `Child`'s implementation. Even when obtaining a `Method` via `Parent.class.getDeclaredMethod("label")` and calling `invoke(child)`, this instance call still uses **dynamic dispatch** and therefore returns `"child"` (per Java overriding rules).

Conversely, `private` methods are not overridden in the normal sense; `static` methods are **hidden**, not dispatched like instance methods; and two methods with the same name but **different parameter type lists** are *overloads*, not overrides. A member scanner must not merge all methods solely by name.

| Scenario | Nature | Appropriate handling rule for a public registry |
| --- | --- | --- |
| `Parent.id` and `Child.id` | Two independent fields; subclass field hides parent field | If one property per name is needed: pick the subclass and record the hiding; if full data is needed: keep both under distinct keys |
| `Parent.label()` and `Child.label()` | Instance method override | One method key by name + parameter type list; keep the valid declaration on the more specific class |
| `set(String)` and `set(int)` | Overload | Keep **two** distinct keys |
| `Parent.staticMethod()` and `Child.staticMethod()` | Static method hiding | Handle separately under static policy; do not treat as override |
| Private methods with the same name/signature in two classes | No normal overriding relationship | If scanning private members, key by declaring class and apply separate access control |
| Compiler-generated methods (`bridge`/`synthetic`) | Bytecode-support members, may collide with source keys | Explicitly choose whether to exclude from the source API model or keep for bytecode analysis |

## 2. What Reflection returns and assumptions to discard

- `getDeclaredFields()` and `getDeclaredMethods()` only retrieve members **declared directly** on the inspected type; they do not automatically add inherited members. The resulting arrays have **no guaranteed order**.
- `getFields()` and `getMethods()` return matching `public` members, including members inherited from superclasses/superinterfaces. The order of these arrays is also **not guaranteed**. In particular, `getMethods()` follows JDK rules for selecting more specific methods, so do not infer behavior based solely on "the first element".
- `getDeclaredMethods()` can return compiler-generated **bridge/synthetic methods**, sometimes with the same name + parameter types but a different return type.
- `getDeclaringClass()` tells you **which class declared the member**. This information is critical when handling hiding, overriding, logging, or metadata caching.
- `getParameterTypes()` reflects **runtime parameter types after type erasure**; `getGenericParameterTypes()` is for retaining generic type metadata. Do not use `getReturnType()` alone to distinguish overloads in Java semantics.
- `getModifiers()`, `Modifier.isPublic(...)`, `Field.isSynthetic()`, `Method.isBridge()`, and `Method.isSynthetic()` aid filtering; however, a member being `public` does not guarantee permission to call it if its **declaring class/package/module** is inaccessible.

Example with covariant return types: `Parent.score(): Number` and `Child.score(): Integer` may require the compiler to emit a **bridge method** in `Child` to preserve compatibility after compilation. If a registry grabs an arbitrary first element of `Child.getDeclaredMethods()`, the dataset may contain both the source method and the bridge, or pick an unintended return type.

## 3. Defining the policy before implementing

An illustrative policy for **a registry of public properties and behaviors of ordinary classes**:

1. **Input**: a `Class<?>` representing a concrete class.
2. **Scope**: only `public instance` members declared by the current class and its superclasses (excluding `Object`); skip `static`, `synthetic`, and `bridge`. Ignore interface/default methods in this simple pass.
3. **Class order**: walk from the concrete class up to the nearest superclass and continue to ancestors. *Closest declaration wins*.
4. **Order within each class**: sort fields by `Field.getName()` and methods by a stable signature key, never relying on Reflection array order.
5. **Field key**: `field.getName()`. On name collision, keep the field from the more specific class. This decision drops the parent's same-named field **from the registry view**, without removing the field from the object.
6. **Method key**: `methodName(parameterType1,parameterType2,...)`, using the ordered list of **runtime parameter types**. Do not merge overloads; do not include return type in the source API key. On key collision, keep the declaration in the more specific class.
7. **Conflict handling**: record both the "selected declaration" and "hidden/overridden declarations" when the product needs auditing or warnings; explicitly decide whether this policy serves a schema, mapper, or dispatcher.

This is a **tool convention**, not a general algorithm replacing all Java inheritance rules. Restricting to `public instance` lets the example avoid many complexities around private, cross-package package-private, protected, cross-module accessibility, interface defaults/diamonds, and generics. If the tool truly must handle those cases, add explicit policies; never widen permissions implicitly.

## 4. Standalone Java 17+ example: ordered scanning with explicit keys

Save the following as **`ToolPolicyDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class ToolPolicyDemo {
    public interface Feature {
        default String tag() { return "interface"; }
    }

    public static class Parent {
        public String id = "parent";
        public String label() { return "parent"; }
        public Number score() { return 10; }
        public void update(String text) {}
    }

    public static class Child extends Parent implements Feature {
        public String id = "child";
        @Override public String label() { return "child"; }
        @Override public Integer score() { return 20; }
        public void update(int number) {}
    }

    static Map<String, Field> fields(Class<?> leaf) {
        Map<String, Field> result = new LinkedHashMap<>();

        for (Class<?> c = leaf; c != null && c != Object.class;
                c = c.getSuperclass()) {
            Arrays.stream(c.getDeclaredFields())
                    .filter(f -> Modifier.isPublic(f.getModifiers())
                            && !Modifier.isStatic(f.getModifiers())
                            && !f.isSynthetic())
                    .sorted(Comparator.comparing(Field::getName))
                    .forEach(f -> result.putIfAbsent(f.getName(), f));
        }
        return result;
    }

    static String key(Method m) {
        String params = Arrays.stream(m.getParameterTypes())
                .map(Class::getTypeName)
                .collect(Collectors.joining(","));
        return m.getName() + "(" + params + ")";
    }

    static Map<String, Method> methods(Class<?> leaf) {
        Map<String, Method> result = new LinkedHashMap<>();

        for (Class<?> c = leaf; c != null && c != Object.class;
                c = c.getSuperclass()) {
            Arrays.stream(c.getDeclaredMethods())
                    .filter(m -> Modifier.isPublic(m.getModifiers())
                            && !Modifier.isStatic(m.getModifiers())
                            && !m.isBridge() && !m.isSynthetic())
                    .sorted(Comparator.comparing(ToolPolicyDemo::key))
                    .forEach(m -> result.putIfAbsent(key(m), m));
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        Child child = new Child();
        Map<String, Field> fieldMap = fields(Child.class);
        Map<String, Method> methodMap = methods(Child.class);

        System.out.println("field owner: " +
                fieldMap.get("id").getDeclaringClass().getSimpleName());
        System.out.println("field values: " +
                fieldMap.get("id").get(child) + "/" + ((Parent) child).id);
        System.out.println("label owner: " +
                methodMap.get("label()").getDeclaringClass().getSimpleName());
        System.out.println("label call: " +
                methodMap.get("label()").invoke(child));
        System.out.println("score return type: " +
                methodMap.get("score()").getReturnType().getSimpleName());
        System.out.println("overloads kept: " +
                methodMap.containsKey("update(int)") + "/" +
                methodMap.containsKey("update(java.lang.String)"));
        System.out.println("bridge count: " +
                Arrays.stream(Child.class.getDeclaredMethods())
                        .filter(Method::isBridge).count());
        System.out.println("base Method.invoke: " +
                Parent.class.getDeclaredMethod("label").invoke(child));
        System.out.println("class-only sees interface default: " +
                methodMap.containsKey("tag()"));
        System.out.println("getMethod sees default: " +
                Child.class.getMethod("tag").invoke(child));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ToolPolicyDemo.java
java ToolPolicyDemo
~~~

Output when compiled with Java 17+ `javac`:

~~~text
field owner: Child
field values: child/parent
label owner: Child
label call: child
score return type: Integer
overloads kept: true/true
bridge count: 1
base Method.invoke: child
class-only sees interface default: false
getMethod sees default: interface
~~~

Interpreting the output under the chosen policy:

- `field owner: Child`: the registry takes the field closest to the target class under name `id`. The next line proves `Parent.id` still exists with a different value; `Field.get(child)` reads the field of its exact declaring class.
- `label owner: Child`: `putIfAbsent` retains the overriding method in the subclass because `Child` is scanned before `Parent`. `label call: child` reflects overriding behavior.
- `score return type: Integer`: the source declaration in `Child` is chosen; the `!m.isBridge()` filter drops the bridge method generated by `javac` due to the covariant return type.
- `overloads kept: true/true`: `update(int)` and `update(String)` have distinct keys so both are kept.
- `bridge count: 1`: the demo reveals the bridge in `Child`'s metadata; this is the outcome of this specific example using `javac`, not a claim that every compiler or every override must emit exactly one bridge.
- `base Method.invoke: child`: choosing a `Method` declared on `Parent` does **not** pin `Parent`'s implementation when invoking an instance method on a `Child`; dynamic dispatch still applies.
- `class-only sees interface default: false`: the algorithm intentionally walks only superclasses and does not inspect `Feature`; however, `Child.class.getMethod("tag")` finds and can invoke the public default method inherited from the interface.

### Why use `LinkedHashMap` and `putIfAbsent`?

`LinkedHashMap` preserves insertion order of entries so results repeat deterministically when inputs and policy do not change. Scanning from subclass to superclass uses `putIfAbsent(key, member)` so the first declaration encountered (most specific class) claims the key. Sorting **before insertion** eliminates reliance on the unguaranteed order of `getDeclaredFields()`/`getDeclaredMethods()`.

In the example, the method signature key is a string for easy inspection. In a system handling multiple class loaders, two distinct classes can share the same binary name. If uniqueness must reflect **`Class<?>` identity**, use a structured key (e.g., a record containing method name and `List<Class<?>>` parameter types) rather than relying solely on `Class.getTypeName()`; normalize module/loader identity as well when persisting caches or exporting metadata across processes.

## 5. Extending the policy to match tool needs

### 5.1. Wanting to keep all hidden fields

If the goal is a debugger, an ORM with explicit metadata, a lossless serializer, or a data inspector across all inheritance levels, a "one name, one field" policy may **not suffice**.

Solution: store `Map<DeclaringClassAndName, Field>` (or a list of same-named fields) with a structured key containing `field.getDeclaringClass()` and `field.getName()`. Then map to explicitly namespaced display names: `Parent#id` and `Child#id`. If the output format only accepts a single `id` key, you need an explicit exclusion policy or intentional collision reporting to avoid silently overwriting the parent's value.

When using annotations to assign logical names (e.g., two physical fields with different names sharing `@JsonProperty`), **logical-name collisions** also differ from Java-name collisions. Keys, precedence rules, and conflict detection must be defined at the right mapping layer.

### 5.2. Wanting to support interface methods and default methods

A registry scanning only superclasses as in the example will miss interface `default` methods. There are two approaches:

- For inherited public APIs, consider `Class.getMethods()` or `getMethod(name, parameterTypes...)` to rely on the public method resolution provided by Reflection, then filter/sort and define grouping policies.
- If you need **declaration location in the interface graph**, actively traverse `getInterfaces()`, deduplicate interfaces, prioritize class methods over interface defaults per Java rules, and handle cases involving multiple interfaces. Sort names/interfaces for deterministic output, while implementation selection must follow inheritance/most-specific rules—**do not substitute alphabetical order for overriding semantics**.

The example in section 4 intentionally shows `methodMap` does not contain `tag()` whereas `getMethod("tag")` does: this is an **explicit limitation of the illustrative policy**, not a Reflection bug.

### 5.3. Static, private, protected, package-private, and modules

- `static` methods with the same signature in two classes are **hidden**, with no dynamic dispatch. If a registry handles static factories, use a separate group and precedence; do not mix them into the instance registry.
- A parent's `private` method is not overridden; if a tool must read private members, the key must include the declaring class or distinguish metadata, never letting a same-named subclass method "replace" the parent's private method under override assumptions.
- `protected` and package-private must account for **package, type relationships, and actual accessibility**. Package-private methods in two different packages do not automatically form an override relationship.
- Beyond `Modifier.isPublic`, module `exports`/`opens`, declaring-class visibility, and lookup context can determine usability. `setAccessible(true)` has restrictions in Java 17+ under JPMS and may throw `InaccessibleObjectException`; do not treat discovering metadata as sufficient permission to invoke.
- Constructors are **not inherited**, so do not feed `getDeclaredConstructors()` into the same override/hiding algorithm.

For tools handling broader cases than the example, verify accessibility using the exact API being used (Reflection, `MethodHandles.Lookup`, `canAccess` when an appropriate object exists) and according to product policy. When permissions are insufficient, report a clear error instead of picking another member arbitrarily.

### 5.4. Generics, bridges, and covariant return types

Java determines overloads primarily from **method name and parameter type list**, and does not create a new overload solely from a different return type. In bytecode/Reflection, the compiler may add bridges after type erasure or when return types are covariant. Therefore:

1. For a **Java source-level API model**, it is usually best to filter out `isBridge()`/`isSynthetic()` before grouping.
2. For a **bytecode analyzer**, it may be necessary to keep bridges as well, in which case keys can include the **return type** and declaring class info, along with bridge/synthetic flags.
3. For generic type metadata, distinguish `getParameterTypes()` (erased runtime types) from `getGenericParameterTypes()`. Generic data is supplemental descriptive metadata; it is not a reason to arbitrarily pick one method among colliding runtime signatures.

If a library must support unusual bytecode or dynamically generated classes, do not assume every duplicate is a bridge; inspect the filtered group and make an explicit decision when collisions remain.

## 6. Consistency checks before shipping into a framework

A reliable scanner should have verifiable properties:

| Criterion | How to verify |
| --- | --- |
| Output independent of Reflection array order | Permute input lists before sorting/grouping; selected results remain identical |
| Same-named fields do not silently lose data | Test `Parent.id`/`Child.id`, verifying the "flatten" or "keep all" policy |
| Overrides differ from overloads | `label()` yields only one entry from the nearest class; `update(String)` and `update(int)` coexist |
| Bridges do not corrupt source-API return types | Test covariant overrides; check `isBridge()` and the return type of the selected entry |
| Interface defaults are handled per published rules | Test `getMethod`, or verify explicit class-only scope |
| Access rights are handled | Test public members on non-public types, private across modules, and access error handling |
| Stable results when cached | Cache keys bind `Class<?>`/ClassLoader and filter policy; do not use class name alone with multiple loaders |
| Excluded members are explainable | For critical data, log original/selected/excluded declarations per policy, avoiding silent collisions |

A common bug to avoid is calling `Map.put(name, member)` inside a loop with undefined order: "last one wins" depends on the order returned by the JVM. Even `putIfAbsent` is only valid when **inputs are already sorted and class traversal order is intentionally designed**.

**Key takeaway:** field hiding retains **multiple storage slots**; method overriding determines **the instance implementation invoked**. A Reflection registry must explicitly state whether it keeps all or chooses one representative, with stable keys and ordering. The illustrative policy uses "subclass first, sort within class, fields by name, methods by name + parameters, filter bridge/synthetic/static" to produce a predictable result; when adding interfaces or non-public members, extend the policy accordingly.

**Java SE 21 documentation references:**
- [`Class`: `getDeclaredFields`, `getDeclaredMethods`, `getMethods`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [`Method`: `invoke`, `isBridge`, `isSynthetic`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [`Field`: `get` and `getDeclaringClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html)