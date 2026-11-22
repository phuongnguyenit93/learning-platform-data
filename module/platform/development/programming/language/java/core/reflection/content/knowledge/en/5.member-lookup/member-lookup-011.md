# Building an Explicit Cross-Hierarchy Lookup Policy with Java Reflection

## 1. Why Must There Be a Lookup Policy?

When writing tools based on Java Reflection (mappers, serializers, testing frameworks, metadata checkers), the question "find field/method named X" is not clear enough. We also have to decide: inspect only the current class or superclasses too; traverse interfaces or not; include `private`/`protected` members or not; retain hidden/overridden declarations or not; and which declaration takes priority when multiple places share the same name.

For example, `Child` declares field `id` matching `Parent.id`. Both fields **coexist** and each field has a different `getDeclaringClass()`. For an overridden `score()` method, we usually want the declaration closest to the queried class. However, an auditing tool might need **all declarations**, including hidden ones. Therefore, results must come from a policy whose name, scope, and priority order are written explicitly before implementation.

Distinguish three common requirements:

- **Looking up visible public members:** leverage `getField` / `getMethod` / `getFields` / `getMethods`, with the semantics of those APIs.
- **Inventorying declarations level by level:** walk through each `Class<?>` and use `getDeclaredFields` / `getDeclaredMethods`; do not merge duplicate declarations.
- **Selecting a member according to application policy:** define the visited levels, filters, deduplication keys, and priority rules yourself; the code example below implements this approach.

"Found by Reflection" **does not mean** "inherited by the Java language", "has access permission", or "can be invoked". These are four separate concerns.

## 2. APIs and Boundaries to Understand

| API | Scope and Meaning |
| --- | --- |
| `getDeclaredField(name)` / `getDeclaredFields()` | Fields **declared directly** on the class/interface under inspection, regardless of access level; does not automatically climb to superclasses. |
| `getField(name)` / `getFields()` | `public` fields of the class and `public` members inherited/visible from superclasses and interfaces per Reflection rules. |
| `getDeclaredMethod(name, parameterTypes...)` / `getDeclaredMethods()` | Directly declared methods, including `private`; finds methods by name **and parameter types**, not by return type. |
| `getMethod(name, parameterTypes...)` / `getMethods()` | `public` methods provided in the type's public set, including eligible inherited methods; may include methods from `Object`. |
| `getSuperclass()` | Gets the direct superclass; returns `null` for `Object` or interfaces. |
| `getInterfaces()` | Gets directly declared interfaces; to visit superinterfaces too, you must recursively traverse `getInterfaces()`. |
| `getDeclaringClass()` | Identifies the exact location where a `Field`/`Method` is declared, distinct from the class initially queried. |

`getDeclared...` is a key building block of a cross-hierarchy algorithm: each call inspects only **one** type, and then the algorithm explicitly moves to another type. You should not assume the element order returned by `getDeclaredFields()` or `getDeclaredMethods()` is stable; sort if results must be reproducible.

Constructors are not inherited; if the problem requires constructors, use `getDeclaredConstructors()` on the exact type, without applying a superclass search algorithm for constructors.

## 3. Lookup Policy Contract

The following example defines three modes:

1. `DECLARED_ONLY`: only the input type.
2. `CLASS_HIERARCHY`: input type → closest superclass → next superclass; `Object` appears only when `includeObject` is enabled.
3. `WITH_INTERFACES`: first all the classes as above; then declared interfaces from the closest class to more distant ones, walking deeper along superinterfaces, skipping already-visited interfaces.

Two independent flags:

- `publicOnly`: accepts only members with the `public` modifier. If `false`, collects non-public declarations as well; **does not** automatically elevate access permissions.
- `includeObject`: whether to include `Object` in the superclass traversal loop (`false` by default in the example).

The example selects members using a **first match wins** rule: for fields, the deduplication key is the name; for methods, the deduplication key is the name plus the parameter type list. Because closer classes are visited first, hidden fields and overridden methods prioritize the closest declaration. With multiple interfaces having matching signatures/names, the defined interface traversal order selects the first candidate. If business logic does not allow ambiguity, replace first-match selection with validation and an explicit error report. This is a **tool policy**, not claiming to be the Java compiler's resolution algorithm for all method-call cases.

Results use `List.copyOf`/`Optional` so callers receive easily checkable results and cannot mutate the result collection directly.

## 4. Standalone Java 17+ Example

Save as `HierarchyLookupDemo.java`. The program uses nested classes to demonstrate field hiding, covariant return/bridge methods, default interface methods, and private access levels.

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;

public class HierarchyLookupDemo {
    enum Mode {
        DECLARED_ONLY, CLASS_HIERARCHY, WITH_INTERFACES
    }

    record Policy(Mode mode, boolean publicOnly, boolean includeObject) {
        Policy {
            Objects.requireNonNull(mode);
        }
    }

    record Signature(String name, List<Class<?>> parameters) {}

    interface Named {
        default String label() {
            return "named";
        }
    }

    interface Audited extends Named {
        default void audit() {}
    }

    static class Parent {
        public String id;
        private String secret;

        public Number score() {
            return 1;
        }
    }

    static class Middle extends Parent implements Audited {
        public String id; // Hides Parent.id, does not remove Parent.id.
        protected String state;

        @Override
        public Integer score() {
            return 2;
        }
    }

    static final class Leaf extends Middle {
        private String local;

        public void setLocal(String value) {
            local = value;
        }
    }

    // Order: input type -> superclass -> ... -> direct interfaces,
    // then superinterfaces (without duplicate visits in diamond structures).
    static List<Class<?>> owners(Class<?> start, Policy policy) {
        Objects.requireNonNull(start);
        if (policy.mode() == Mode.DECLARED_ONLY) {
            return List.of(start);
        }

        List<Class<?>> classes = new ArrayList<>();
        for (Class<?> current = start;
             current != null;
             current = current.getSuperclass()) {
            if (current == Object.class && !policy.includeObject()) {
                break;
            }
            classes.add(current);
        }

        if (policy.mode() == Mode.CLASS_HIERARCHY) {
            return List.copyOf(classes);
        }

        Set<Class<?>> ordered = new LinkedHashSet<>(classes);
        for (Class<?> type : classes) {
            for (Class<?> iface : type.getInterfaces()) {
                addInterface(iface, ordered);
            }
        }
        return List.copyOf(ordered);
    }

    static void addInterface(Class<?> iface, Set<Class<?>> ordered) {
        if (ordered.add(iface)) {
            for (Class<?> parent : iface.getInterfaces()) {
                addInterface(parent, ordered);
            }
        }
    }

    static List<Field> fields(Class<?> type, Policy policy) {
        Map<String, Field> chosen = new LinkedHashMap<>();
        for (Class<?> owner : owners(type, policy)) {
            Field[] declared = owner.getDeclaredFields();
            Arrays.sort(declared, Comparator.comparing(Field::getName));
            for (Field field : declared) {
                if (field.isSynthetic()) {
                    continue;
                }
                if (policy.publicOnly()
                        && !Modifier.isPublic(field.getModifiers())) {
                    continue;
                }
                chosen.putIfAbsent(field.getName(), field);
            }
        }
        return List.copyOf(chosen.values());
    }

    static Signature signature(Method method) {
        return new Signature(
                method.getName(),
                List.copyOf(Arrays.asList(method.getParameterTypes())));
    }

    static List<Method> methods(Class<?> type, Policy policy) {
        Map<Signature, Method> chosen = new LinkedHashMap<>();
        for (Class<?> owner : owners(type, policy)) {
            Method[] declared = owner.getDeclaredMethods();
            Arrays.sort(declared,
                    Comparator.comparing(Method::getName)
                            .thenComparing(m -> Arrays.toString(
                                    m.getParameterTypes()))
                            .thenComparing(m -> m.getReturnType().getName()));
            for (Method method : declared) {
                // Compiler may generate bridge methods for covariant return types.
                if (method.isBridge() || method.isSynthetic()) {
                    continue;
                }
                if (policy.publicOnly()
                        && !Modifier.isPublic(method.getModifiers())) {
                    continue;
                }
                chosen.putIfAbsent(signature(method), method);
            }
        }
        return List.copyOf(chosen.values());
    }

    static Optional<Field> field(
            Class<?> type, String name, Policy policy) {
        return fields(type, policy).stream()
                .filter(f -> f.getName().equals(name))
                .findFirst();
    }

    static Optional<Method> method(
            Class<?> type, String name, Policy policy,
            Class<?>... parameterTypes) {
        Signature expected = new Signature(
                name, List.copyOf(Arrays.asList(parameterTypes)));
        return methods(type, policy).stream()
                .filter(m -> signature(m).equals(expected))
                .findFirst();
    }

    public static void main(String[] args) {
        Policy deep = new Policy(Mode.WITH_INTERFACES, false, false);
        Policy publicOnly = new Policy(Mode.WITH_INTERFACES, true, false);

        System.out.println("field id: "
                + field(Leaf.class, "id", deep).orElseThrow()
                        .getDeclaringClass().getSimpleName());
        System.out.println("method score(): "
                + method(Leaf.class, "score", deep).orElseThrow()
                        .getDeclaringClass().getSimpleName());
        System.out.println("method label(): "
                + method(Leaf.class, "label", deep).orElseThrow()
                        .getDeclaringClass().getSimpleName());
        System.out.println("private local (deep): "
                + field(Leaf.class, "local", deep).isPresent());
        System.out.println("private local (public-only): "
                + field(Leaf.class, "local", publicOnly).isPresent());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 HierarchyLookupDemo.java
java HierarchyLookupDemo
~~~

Expected output:

~~~text
field id: Middle
method score(): Middle
method label(): Named
private local (deep): true
private local (public-only): false
~~~

Reason for the results: `Middle.id` is evaluated before `Parent.id`; `Middle.score()` is evaluated before `Parent.score()`; `label()` is declared on `Named`, found while traversing `Middle → Audited → Named` in the interface branch; `local` is `private` so it exists only in the mode allowing non-public members. The bridge method generated for `Middle.score()` is filtered out so it does not affect signature selection rules.

The example above **only finds and returns `Field`/`Method` metadata**. It does not call `setAccessible`, `trySetAccessible`, `Field.get`, or `Method.invoke`.

## 5. Policy Variants for Practical Purposes

| Goal | Suitable Rule |
| --- | --- |
| Read only metadata defined by the current type | `DECLARED_ONLY`; store all results if declarations need to be distinguished. |
| Map data by fields of subclass and superclass | `CLASS_HIERARCHY`; define handling for same-named fields; typically skip static/synthetic/transient per mapper requirements. |
| Find annotations on superclass/interface methods | `WITH_INTERFACES`; traverse declarations level by level and use `getDeclaredAnnotation` on each method; define annotation inheritance rules clearly. |
| List the public API of a type | Consider `getMethods()`/`getFields()` or `publicOnly=true`; compare carefully because a custom policy does not have the exact semantics of Java member resolution. |
| Analysis/auditing tools | Do not use `putIfAbsent` to drop duplicate declarations; return `(declaringClass, member)` pairs and conflict locations. |

A common adjustment when writing mappers is filtering out `Modifier.isStatic(...)` and `Modifier.isTransient(...)` for fields. For business-oriented method scanners, you may skip `static` methods, methods on `Object`, invalid getters, or overridden methods, depending on the contract. Do not apply these filters implicitly because they change the results.

**Annotations have their own rules:** `@Inherited` only pertains to querying annotations on a *class* via its superclass; it does not make annotations on methods or interfaces automatically inherited. To merge annotations from parent/interface methods, you must define a matching-method lookup algorithm and an explicit priority policy.

## 6. Limitations and Pitfalls to Avoid

1. **Method name is not a signature:** overloads `load(String)` and `load(int)` are two distinct methods. Parameter types in Reflection reflect generic erasure, and primitive types differ from wrapper types (`int.class` differs from `Integer.class`). Methods with covariant return types may generate bridges; the example filters bridge/synthetic methods to serve business lookup. For bytecode analysis tools, you need to retain them.
2. **Field hiding differs from method overriding:** Java has no polymorphic fields like methods; `Parent.id` still exists when `Middle` declares `id`. If the goal is auditing, merging by name loses information. `private` or `static` methods also do not follow the same overriding rules as overridable instance methods.
3. **Interface members:** interfaces can have default, static, and private methods. An algorithm traversing `getDeclaredMethods()` of interfaces only means it *discovers declarations*, not asserting that every such method is inherited or directly callable by the implementing class. To model language-level callability accurately, you must add conditions for inheritability, static/private, access, overriding, and conflict cases.
4. **Access scope and modules:** finding a `private` member does not grant permission to read/call it. `trySetAccessible()` can return `false`, and `setAccessible(true)` can throw `InaccessibleObjectException` when the Java Platform Module System has not opened the corresponding package; `IllegalAccessException` can occur upon operation. Elevate access only when necessary and permitted, and do not open modules just to "fix lookup errors".
5. **Order and conflicts:** member order returned by Reflection is not guaranteed to match source order; the example sorts for stability. First-match mode must document how ties are chosen when multiple interfaces share a name. Where high precision is needed, return the list of candidates with `declaringClass` and report a conflict rather than silently picking one.
6. **Performance and class loaders:** repeated Reflection over many objects has cost. Cache metadata by `Class<?>` when needed (e.g., `ClassValue`), while avoiding holding unnecessary references to short-lived `ClassLoader` instances. Do not cache policy-dependent results while forgetting to include the policy in the cache key.
7. **Special types:** arrays, primitives, interfaces, records, and proxies have different declaration structures than ordinary classes. Test them separately when your application supports them; the illustrative algorithm focuses on standard class/interface inheritance chains.

## 7. Minimal Test Cases for a Policy

- `DECLARED_ONLY` on `Leaf` finds `local` but does not find `id`.
- `CLASS_HIERARCHY` on `Leaf` finds `id` from `Middle`; does not find `Named.label()` because it does not traverse interfaces.
- `WITH_INTERFACES` on `Leaf` finds `Named.label()`; visits superinterfaces exactly once even in diamond structures.
- `publicOnly=true` does not return `Leaf.local`, `Middle.state`, or `Parent.secret`.
- `includeObject=false` excludes methods declared on `Object` such as `toString()` when not overridden; enabling the flag allows finding them.
- Overload cases distinguish parameters; override/bridge cases prioritize the right declaring type per policy; same-named field cases verify `getDeclaringClass()`.
- When business logic needs to keep all declarations, test that the inventory algorithm does **not** deduplicate like the single-result selection algorithm.

**Implementation principle:** explicitly specify the set of types to traverse, traversal order, filtering conditions, identity key, conflict resolution, and access limits; then implement those choices as testable code. Reflection is a tool for reading metadata, whereas the meaning of "cross-hierarchy lookup" is defined by your application's contract.