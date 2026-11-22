# Defining Conflict Rules, Precedence, and Missing Annotation Cases in Java

When designing annotations, writing an `@interface` is only the first step. The error-prone part lies in the **metadata processing contract**: if both a class and a method have annotations, which value is used? If two conflicting annotations appear at the same location, what should be done? If no annotation is present, should a default be used, inheritance be searched, or an error be reported?

Java only defines the syntax, the locations where annotations can be placed, retention lifecycles, and how APIs retrieve annotations. **Java does not automatically know the business rule for which annotation is “more important” than another.** Precedence order, conflict mechanisms, and behavior when metadata is absent must be **written into a clear, consistent, and testable policy** by you in a library, framework, or annotation processor.

This lesson uses an illustrative access-control scenario to explain. This example is meant to teach **annotation design**, not to serve as a complete security library: only permission-checking code actually invoked at the execution point helps enforce the access policy.

## 1. Learning Objectives

After this lesson, you will be able to:

- Define *conflict*, *override*, *fallback*, *missing*, and *invalid value* in the context of annotations.
- Decide on a precedence policy such as `method > class > default` and explain how two annotations at the **same level** differ from annotations at **different levels**.
- Distinguish “no annotation declared” from “an annotation declared with a default value” and “an explicit configuration to disable or allow”.
- Use `getDeclaredAnnotation(...)` or `getAnnotation(...)` deliberately, without relying on guesswork about `@Inherited`, method overrides, or interfaces.
- Handle missing metadata with a **safe default**, **early error reporting**, or **explicit fallback**, depending on the application contract.
- Write a resolver that does not depend on the return order of `getAnnotations()`.
- Detect conflicts before deciding precedence; do not accidentally mask misconfigurations.
- Create tests following a method/class/missing/conflict/invalid matrix.
- Understand when to shift errors from runtime to compile-time using an annotation processor.

## 2. Why Do Annotations Need a “Conflict Contract”?

Suppose you design two annotations yourself:

~~~java
@PermitAll
@Roles({"admin"})
public void deleteEverything() {}
~~~

`@PermitAll` means “open”, while `@Roles({"admin"})` means “only users with the admin role”. They appear **on the same method**, both describing the same decision. If the code checks `@PermitAll` first, it might allow everyone; if it checks `@Roles` first, it blocks those without the role. Meaning must not depend on the iteration order of an annotation array or an arbitrarily written `if` structure.

On the other hand:

~~~java
@Roles({"staff"})
class Reports {
    @PermitAll
    public void ping() {}
}
~~~

Here, the two annotations are at **different levels**: class and method. You can establish a rule that the method is more specific, so `ping()` is public even though the class default is the `staff` role. That is an **intentional override**, not necessarily a conflict.

Finally:

~~~java
class Unmarked {
    public void probe() {}
}
~~~

Neither the class nor the method has an annotation. The system must know whether to choose **deny**, **allow**, an external configuration value, or a **missing-configuration error**. “Seeing nothing” cannot be interpreted as an arbitrary security choice.

Let’s classify these scenarios before writing code:

| Scenario | Issue Name | Design Question |
| --- | --- | --- |
| Same method has `@PermitAll` and `@Roles` | Same-level conflict | Report an error, or define a precedence rule between the two annotation types? |
| Class has `@Roles`, method has `@PermitAll` | Cross-level override | Is a method allowed to override its class? |
| Missing on method, present on class | Fallback | Use the class configuration? |
| Missing on both method and class | Missing | Safe default or required configuration? |
| `@Roles({})` | Invalid value | What does an empty list mean? Report an error or treat it as deny? |
| Superclass/interface has annotation | Inheritance/lookup | Should superclasses, interfaces, or overridden methods be searched? |
| Same annotation type appears multiple times | Repeatable/aggregate | Merge by union, intersection, precedence, or reject? |

A good library writes down the answers to these rows **before real traffic arrives**.

## 3. Distinguishing Core Concepts

### 3.1. Annotation Type Differs from Annotation Value

`@Roles({"staff"})` and `@Roles({"admin"})` have the **same annotation type** `Roles` but different element values. An annotation type can declare a default value:

~~~java
@interface Priority {
    int value() default 10;
}
~~~

If the source writes `@Priority`, the effective value of `value()` is `10`. That is **different** from not having `@Priority`. When it is absent, `getAnnotation(Priority.class)` returns `null`; when `@Priority` is present, the API returns an annotation instance and `value()` returns `10`.

This distinction is critical when a user wants to say “intentionally use the default” or “let the enclosing class decide”.

### 3.2. “Missing” and “Invalid” Are Not the Same

- **Missing:** neither the method nor the class declares a policy.
- **Invalid:** the author did attach `@Roles({})`, but the library requires at least one role.
- **Conflict:** the same location simultaneously has both `@PermitAll` and `@Roles(...)`.

You should not handle all cases with the same `null -> default allow`. An annotation that is **declared but invalid** needs to be detected and reported as an error, instead of being silently ignored and falling back.

### 3.3. Precedence Is Not the Same as Retention Lifecycle

`@Retention(RUNTIME)` allows an annotation to be read by Reflection at runtime; `@Retention(SOURCE)` suits an annotation processor at compile time. **Retention does not decide which annotation wins**.

`@Target({TYPE, METHOD})` allows placing the annotation on class and method declarations; it also **does not determine whether a method takes precedence over a class**. That is the handler’s policy.

`@Inherited` affects how Java looks up certain annotations on a **class**, but it does not produce a business-rule conflict resolver. This lesson sets an explicit lookup rule so it is not confused with inheritance.

## 4. Choosing a Policy That Can Be Expressed as a Table

In this example, we choose the following contract:

1. **The method level takes precedence** over the class level in determining the decision that applies to a method.
2. **Each level may contain at most one choice** from the set `@PermitAll` and `@Roles`. Having both at the same level is a **configuration error**, rather than silently picking one.
3. **The `@Roles` value must be valid**: the role array is non-empty; each role consists of lowercase English letters (`[a-z]+`) to keep the demo simple.
4. Before applying an override, **validate both the class and method configurations**. An invalid configuration on the class must be reported, even if a particular method has its own annotation.
5. If the method does not declare a policy, **fall back to the class**.
6. If both levels are missing: default to `DENY` in normal mode; if the caller requires a mandatory policy (`required=true`), return a `MISSING` error.
7. In the demo, **only directly declared annotations** on the class and method are considered, without automatically scanning superclasses, interfaces, or overridden methods. If complex inheritance is needed, it must be a separate part of the contract and requires additional tests.

Decision table:

| Method | Class | Result (if both are valid) |
| --- | --- | --- |
| `@PermitAll` | Any valid policy or missing | `ALLOW@method` |
| `@Roles({"admin"})` | Valid policy or missing | `ROLES[admin]@method` |
| None | `@PermitAll` | `ALLOW@class` |
| None | `@Roles({"staff"})` | `ROLES[staff]@class` |
| None | None, `required=false` | `DENY@default` |
| None | None, `required=true` | `MISSING` (error) |
| Two conflicting annotations at the same level | Any | `CONFLICT` (error) |
| `@Roles({})` at a level | Any | `INVALID_ROLES` (error) |

This table represents a **hypothetical application policy**, not an automatic JVM rule. When applied to another domain—such as JSON mapping, a test runner, or dependency injection—you may choose a different policy, but it must still be transparent and consistent.

## 5. Standalone Runnable Java 17+ Example

Create a single file named **`AccessPolicyDemo.java`** (with no `package`). The file below contains the two annotation types, sample classes, the `Decision` record, `PolicyResolver`, and a public class with `main`.

~~~java
import java.lang.annotation.*;
import java.lang.reflect.*;
import java.util.*;

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface PermitAll {}

@Retention(RetentionPolicy.RUNTIME)
@Target({ElementType.TYPE, ElementType.METHOD})
@interface Roles {
    String[] value();
}

@Roles({"staff"})
class Reports {
    public void list() {}
    @PermitAll public void ping() {}
}

@PermitAll
class Portal {
    @Roles({"admin"}) public void delete() {}
    public void home() {}
}

class Unmarked {
    public void probe() {}
    public void strict() {}
}

class Conflicted {
    @PermitAll @Roles({"ops"}) public void broken() {}
}

class InvalidRoles {
    @Roles({}) public void empty() {}
}

@PermitAll @Roles({"ops"})
class InvalidClass {
    @PermitAll public void action() {}
}

record Decision(String rule, String source) {
    @Override public String toString() {
        return rule + "@" + source;
    }
}

class PolicyResolver {
    static Decision read(AnnotatedElement element, String where) {
        PermitAll permitAll = element.getDeclaredAnnotation(PermitAll.class);
        Roles roles = element.getDeclaredAnnotation(Roles.class);

        if (permitAll != null && roles != null) {
            throw new IllegalStateException("CONFLICT@" + where);
        }
        if (roles != null) {
            String[] names = roles.value();
            if (names.length == 0
                    || Arrays.stream(names).anyMatch(
                        name -> name == null
                                || !name.matches("[a-z]+"))) {
                throw new IllegalStateException("INVALID_ROLES@" + where);
            }
            return new Decision("ROLES[" + String.join(",", names) + "]",
                    where);
        }
        return permitAll != null ? new Decision("ALLOW", where) : null;
    }

    static Decision resolve(Class<?> owner, String methodName, boolean required)
            throws NoSuchMethodException {
        Method method = owner.getDeclaredMethod(methodName);
        // Validate class and method independently, even when method overrides.
        Decision classRule = read(owner, "class");
        Decision methodRule = read(method, "method");
        if (methodRule != null) return methodRule;
        if (classRule != null) return classRule;
        if (required) throw new IllegalStateException("MISSING@method+class");
        return new Decision("DENY", "default");
    }
}

public class AccessPolicyDemo {
    static void show(Class<?> owner, String method, boolean required)
            throws NoSuchMethodException {
        try {
            System.out.println(owner.getSimpleName() + "." + method + "="
                    + PolicyResolver.resolve(owner, method, required));
        } catch (IllegalStateException e) {
            System.out.println(owner.getSimpleName() + "." + method
                    + "=ERROR:" + e.getMessage());
        }
    }

    public static void main(String[] args) throws NoSuchMethodException {
        show(Reports.class, "list", false);
        show(Reports.class, "ping", false);
        show(Portal.class, "delete", false);
        show(Portal.class, "home", false);
        show(Unmarked.class, "probe", false);
        show(Unmarked.class, "strict", true);
        show(Conflicted.class, "broken", false);
        show(InvalidRoles.class, "empty", false);
        show(InvalidClass.class, "action", false);
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 AccessPolicyDemo.java
java AccessPolicyDemo
~~~

**Exact stdout:**

~~~text
Reports.list=ROLES[staff]@class
Reports.ping=ALLOW@method
Portal.delete=ROLES[admin]@method
Portal.home=ALLOW@class
Unmarked.probe=DENY@default
Unmarked.strict=ERROR:MISSING@method+class
Conflicted.broken=ERROR:CONFLICT@method
InvalidRoles.empty=ERROR:INVALID_ROLES@method
InvalidClass.action=ERROR:CONFLICT@class
~~~

This result was compiled with `javac --release 17` and run successfully on a JDK supporting Java 17.

### Case-by-Case Analysis

1. **`Reports.list`:** the method has no policy attached, while the class has `@Roles({"staff"})`, so the policy is taken from the class.
2. **`Reports.ping`:** the method has `@PermitAll`, and the class has `@Roles`. The two annotations are at **different levels**, and the policy prioritizes the method, resulting in `ALLOW@method`.
3. **`Portal.delete`:** the class has `@PermitAll`, but the specific method has `@Roles({"admin"})`. The method is allowed to be more restrictive, resulting in `ROLES[admin]@method`.
4. **`Portal.home`:** the method has no policy; `@PermitAll` on the class is used.
5. **`Unmarked.probe`:** neither level has a policy and `required=false`; **defaults to DENY**.
6. **`Unmarked.strict`:** no policy is present, and `required=true`; returns a `MISSING` error rather than silently choosing a default.
7. **`Conflicted.broken`:** **the same method** has both `@PermitAll` and `@Roles({"ops"})`; reports `CONFLICT@method`.
8. **`InvalidRoles.empty`:** `@Roles({})` is present, but the role list is empty; reports `INVALID_ROLES@method`. An empty role list must not be treated as “undeclared”.
9. **`InvalidClass.action`:** the class has two conflicting annotations; even though the method has `@PermitAll`, the resolver still **validates the class first** and reports `CONFLICT@class`. This prevents a method annotation from silently hiding a broken class configuration.

### Why Use `record Decision`?

Java 17 supports records. In the demo, `Decision` carries just two fields: `rule` (the decision) and `source` (where it came from), allowing output to include the **decision source** such as `ALLOW@method`. When debugging or writing tests, source information is very useful: two policies may have identical behavior, yet one is declared directly while the other comes from a fallback.

In a larger application, you should use an enum/strongly typed data model, such as `AccessMode { DENY, ALLOW, ROLES }` plus an immutable list of roles, instead of concatenating the rule into a string. The demo uses `String` to prioritize readability and simple stdout.

## 6. Understanding the Resolver Algorithm in Depth

The four steps of `PolicyResolver.resolve(...)`:

~~~text
1. Read & validate the policy declared on the class
                 |
2. Read & validate the policy declared on the method
                 |
3. If the method has a policy -> use method
   Otherwise, if the class has a policy -> use class
                 |
4. If both are missing:
   required=true  -> report MISSING
   required=false -> return DENY@default
~~~

**Do not arbitrarily reverse the order of “validate” and “resolve precedence”.** If the code picks the method as soon as it sees `@PermitAll` and completely skips the class, an internally conflicting class will go undetected. This lesson’s policy requires **all configurations present at both levels to be valid**.

However, some systems intentionally validate only the effective policy or have rules that discard part of a parent configuration. In that case, you must clearly express the different validation levels and test overridden cases. What matters is not that every framework uses the same order as this lesson, but that **the order must be defined upfront**.

### 6.1. What Does the `read` Method Do?

`read(AnnotatedElement element, String where)`:

- Directly reads the two annotation types.
- If both appear on the same `AnnotatedElement`, reports a conflict error.
- If `@Roles` is present, validates the count and format of the role names.
- If `@PermitAll` is present, creates an ALLOW decision.
- If neither type is found, returns `null` so the resolver knows that **this level is missing a policy**.

Returning `null` here is an **internal signal for “undeclared”**, not a policy like `DENY`. Because of that, the resolver can distinguish a fallback from an explicit deny.

In production code, you can replace `null` with `Optional<Decision>` or a sealed hierarchy describing `Missing`/`Configured`/`Invalid`. However, it is not always necessary to wrap every piece of code in complex types when a small example is already clear.

### 6.2. Do Not Use the Order of `getAnnotations()` as Precedence Order

A poor design approach:

~~~java
// DO NOT use array position as business precedence order.
Annotation[] annotations = method.getAnnotations();
if (annotations.length > 0) {
    Annotation winner = annotations[0];
}
~~~

Java Reflection provides annotations for reading metadata; it does not promise that “an annotation written earlier in the source always wins”. When resolution is needed, read the **exact types** recognized and apply explicit rules. If ordering is required, design a `priority` element with a concrete meaning, specify a tie-breaker, and test it.

Moreover, `@Target` does not prohibit two different annotation types from appearing at the same location. If they are mutually exclusive under business rules, you must validate them yourself (or use an annotation processor to detect them early).

## 7. Distinguishing Class, Method, Superclass, and Interface

In the demo, the resolver uses:

~~~java
element.getDeclaredAnnotation(PermitAll.class);
element.getDeclaredAnnotation(Roles.class);
~~~

`AnnotatedElement.getDeclaredAnnotation(...)` only reads annotations **directly declared** on the element being inspected. Therefore, this lesson’s algorithm does **not** look up policies from superclasses, interfaces, or overridden methods.

This is a deliberate design choice, not a mandatory limitation. If a framework wants to support inheritance, it must specify that in a dedicated contract:

| Policy Location | Demo Default | If You Want to Support It |
| --- | --- | --- |
| Directly declared method | Read | Keep as highest precedence |
| Directly declared class | Read | Keep after method |
| Method on superclass | Not automatically searched | Decide how to locate the original method and handle overrides |
| Superclass | Not automatically searched | Walk the superclass chain or use an appropriate inheritance mechanism |
| Interface and interface method | Not automatically searched | Traverse in a controlled way, defining a tie-breaker if there are multiple interfaces |
| Package/module-level | Not automatically searched | Define a separate fallback level when needed |

### 7.1. `@Inherited` Is Not a General Precedence Rule

`@Inherited` only affects querying that annotation type on a **class**, along the superclass chain and according to Java’s rules, when the annotation type is marked with `@Inherited`. It does not cause an overriding method to automatically inherit the parent method’s annotation, nor does it propagate annotations from interfaces as a general rule.

If you declare:

~~~java
@Inherited
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Region {
    String value();
}
~~~

then `Child.class.getAnnotation(Region.class)` can receive metadata from the superclass when `Child` does not declare `@Region`; whereas `getDeclaredAnnotation(...)` only inspects direct declarations. **Do not confuse Reflection inheritance rules with a precedence order designed by a framework**.

### 7.2. If Fallback to a Superclass Is Needed, Specify Each Level Explicitly

A policy might choose:

~~~text
direct method
  > direct class
  > nearest parent method
  > nearest parent class
  > application-wide configuration
  > default DENY
~~~

However, another policy might choose `parent method` before `direct class` or prioritize annotations on interfaces. You must answer:

- When a class implements two interfaces with different policies, is it a **conflict or a merge**?
- If a subclass declares an annotation of the same type while omitting some elements that have defaults, does it **override entirely** or **merge per element**? Java annotation defaults belong by default to the **annotation type**, and do not automatically take element values from an annotation on the parent class.
- If an overriding method has its own annotation, is that an intentional override of the annotation on the parent method?
- If both an interface method and a class method have annotations, which one wins?
- If no annotation exists anywhere, what is returned?

Do not extend this lesson’s algorithm to a hierarchy without adding these tests. Simply calling `getAnnotation(...)` on a class also does not solve all interface and method cases.

## 8. Another Dimension: Defaults in Annotation Elements

A type can declare:

~~~java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface RetryPolicy {
    int attempts() default 3;
}
~~~

For a class:

~~~java
@RetryPolicy
class A {}
~~~

`A.class.getAnnotation(RetryPolicy.class)` is not `null`, and `attempts()` returns `3`. Meanwhile, for a class without `@RetryPolicy`, `getAnnotation(...)` returns `null`.

Therefore, you must distinguish:

1. **Missing annotation**: `@RetryPolicy` is not present at the location being inspected.
2. **Annotation present with an omitted element**: the `attempts` element uses the default `3` from the annotation type.
3. **Annotation present with the element explicitly set to the default**: `@RetryPolicy(attempts = 3)`. With Reflection on an annotation instance, the effective value in both cases 2 and 3 is `3`.

If you need to distinguish whether an element was **explicitly written** by the source author or taken from a default, ordinary runtime Reflection on an annotation instance is not designed to preserve that information. During annotation processing, `AnnotationMirror.getElementValues()` and `Elements.getElementValuesWithDefaults(...)` can help distinguish explicit vs. default values in the compile-time model.

This matters when designing override/merge behavior: when an annotation on a method leaves some elements unspecified, do not assume the remaining elements are “inherited” from the annotation on the class. Under Java semantics, they take the annotation type’s defaults **unless your processing code defines and implements an additional merge rule**.

## 9. Choosing Behavior When Annotations Are Missing

No single choice fits every problem. Decide based on the risk of the behavior:

| Domain | Common Missing Strategy to Consider | Rationale |
| --- | --- | --- |
| Access control or sensitive data handling | **Fail-closed**, deny when no policy is present; optionally require a mandatory annotation | Prevents granting access due to omitted metadata |
| Required mapping / schema configuration | **Fail-fast**, report a configuration diagnostic or exception | Missing metadata leaves the mapping undefined |
| Optional logging/metrics | Use an **explicit default** such as no special logging | The annotation adds optional behavior; absence is not necessarily an error |
| Test discovery | Without a test annotation, do not register as a test | Do not assume every method is a test |
| Serialization with convention strategy | May fall back to field names or documented defaults | Avoids forcing users to write excessive annotations |
| Dependency injection | Depends on the container: may look up other rules or report a missing dependency | Behavior must be precisely defined per framework |

**Fail-open** (allowing when missing) is a choice that must be considered with extreme care in an access-control system. The demo sets `DENY@default` to illustrate the safe approach of not granting access from the absence of an annotation.

If a system requires every method to declare a policy, `required=true` in the example turns a missing policy into an error. That is a *fail-fast* approach; in a real system, it should be detected at startup or compile-time so failures do not wait until a request arrives.

### Should You Use a Class-Level `@Default` Annotation?

One valid strategy is to declare an annotation like `@DefaultAccess(...)` at the package/module/class level, and allow a method to override it only when an explicit annotation is present. However, the name and scope must be clearly documented; you should not use a “hidden” default that prevents someone reading the method from predicting its behavior.

You must also distinguish a **business default** from a **Java element default**: `@Roles({"staff"})` is a class policy; `roles() default {"user"}` inside an annotation type is an **element** default value. These two layers are independent.

## 10. Conflicts: Report an Error, Merge, or Prioritize?

There are three common strategies.

### 10.1. Report an Error

Choose this when two annotations are **mutually exclusive** and there is no safe or predictable choice if both appear together—for example, `@PermitAll` and `@Roles` on the same method.

Pros: easy to test and audit; users must fix the source code or configuration. Cons: it can fail builds or startup; provide an error message that clearly identifies the location and conflicting annotations.

### 10.2. Prioritize

Choose this when there is a clear **scope** relationship. For example, a method is more specialized than a class, or an application-level configuration takes precedence over a default. You should document a **fixed order** instead of “whichever annotation Reflection returns first”.

In complex systems, you should also define what “more specific” means for nested types, overridden methods, interfaces, abstract superclasses, mixins, packages, modules, and so on. A single natural total order cannot be inferred for every situation.

### 10.3. Merge

Choose this when multiple annotations have **additive** meaning—for example, multiple tags describing a method, multiple route aliases, or multiple filter conditions. When merging, you must clarify:

- **Union or intersection?** For access control, OR and AND have very different consequences.
- Does order matter?
- Are duplicate elements removed?
- How are empty values handled?
- If one value overrides an earlier one, what is the tie-breaker?

For example, if `@Tag("fast")` and `@Tag("unit")` accumulate, you can use `@Repeatable` and read them with `getAnnotationsByType(Tag.class)`. However, **`@Repeatable` only allows multiple annotations of the same type; it does not automatically choose union/intersection or resolve business conflicts**.

### A Sensible Resolution Order

~~~text
Annotation set at each level
       |
       v
Validate syntax/semantics of values
       |
       v
Identify valid annotations or conflicts
       |
       v
Apply merge/override/fallback rules
       |
       v
If still missing: default or error
       |
       v
Return decision + source explanation
~~~

Including the “decision source” in the output helps with debugging, logging, and testing. Do not return only `true`/`false` if the system needs to analyze why a policy was chosen.

## 11. Early Validation with an Annotation Processor

The demo uses Reflection at runtime to illustrate the structure. If annotations are applied to Java source code in a project you are building, an **annotation processor** can inspect the annotated locations and report errors during compilation.

Processing idea:

~~~java
// ILLUSTRATIVE SNIPPET inside an annotation processor:
for (Element element : roundEnv.getElementsAnnotatedWith(PermitAll.class)) {
    if (element.getAnnotation(Roles.class) != null) {
        processingEnv.getMessager().printMessage(
                Diagnostic.Kind.ERROR,
                "@PermitAll and @Roles cannot be used together",
                element);
    }
}
~~~

This is **not** a standalone runnable Java file; it requires `Processor`/`AbstractProcessor`, `RoundEnvironment`, `Element`, `Diagnostic`, and the corresponding annotation types in an annotation processor project.

Differences between compile-time and runtime:

- An annotation processor uses `javax.lang.model.element.Element` and language model APIs, rather than using `java.lang.reflect.Method` by default to inspect the current source.
- It can detect two annotation types at the same location and attach the error directly to the offending class/method.
- If a policy is mandatory for **every method**, scanning only *already annotated* methods is not enough: the processor must traverse methods/classes within the managed scope and also check **locations without annotations**. This is a very common validation design mistake.
- It usually needs to be paired with build integration/tests; not every class is necessarily examined by the processor if it only processes a specific set of sources/modules.
- `SOURCE` retention suits compile-time-only validation; if runtime Reflection is needed like in the main demo, use `RUNTIME`.

For real security configurations, you can combine **fail-fast at startup/compile time** with **default deny at runtime** as a safety net. However, an annotation processor alone must never be treated as the authorization engine for every request.

## 12. Precautions in Production Design

### 12.1. An “ALLOW” Policy Does Not Mean Runtime Security

In the example, `PolicyResolver.resolve(...)` only returns a `Decision` and **does not block method calls**. Application code or middleware must enforce the decision, inspect user identity/roles, and run before sensitive logic. If `Portal.delete()` is called directly bypassing the resolver, the annotation does not protect the method on its own.

In real systems, you must also consider authentication, authorization, method/proxy invocation, internal calls, policy caching, and behavior when the resolver throws an error. The enforcement layer should default to **denying when a policy resolution exception occurs**, rather than allowing execution to proceed.

### 12.2. Cache Policies with the Right Key and Avoid Losing Context

If the runtime resolver incurs Reflection overhead, you can cache `Decision` by **the exact class and method signature**. You should not cache solely by the name `"delete"`, because two different classes can have methods with the same name, and overloading can produce multiple methods with the same name but different parameters.

The main example uses only **parameterless** method names, so `owner.getDeclaredMethod(methodName)` suffices. In production, use `Method` or class + method name + parameter types; you may also need to handle bridge/overriding methods with proper semantics.

### 12.3. Method Overloading and Overriding

If you have:

~~~java
void find(String id) {}
void find(long id) {}
~~~

then `getDeclaredMethod("find")` cannot locate either overload because they take parameters. You must call `getDeclaredMethod("find", String.class)` or `getDeclaredMethod("find", long.class)` accordingly.

If a subclass overrides a method, annotations on the parent method **do not automatically propagate** to the new method via `@Inherited`. To check override inheritance, you must traverse the method hierarchy and interface contracts yourself and include them in the precedence table.

### 12.4. Do Not Rely on `@Inherited` Inadvertently

In the demo, neither annotation declares `@Inherited` and the resolver uses `getDeclaredAnnotation`, so the result inspects only the passed class and directly declared method. Switching to `getAnnotation` without carefully reviewing the contract can alter which policies apply if `@Inherited` is later added to an annotation type.

Before changing rules, clarify backward compatibility: which subclasses/methods will existing annotations on superclasses/interfaces affect?

### 12.5. Do Not Turn Empty Values into Ambiguous Signals

`@Roles({})` might be interpreted by one framework as “deny all”, while another might treat it as “defer to class inheritance”. Without an explicit rule, users will guess wrong. In the demo, an empty array is an **error** to avoid ambiguity. If you want to allow “deny all” as an explicit configuration, create a dedicated `@DenyAll` annotation and add it to the mutually exclusive set and conflict resolution policy.

### 12.6. Do Not Add Multiple Precedence Levels Without Tie-Breaking

A complex resolution tree might include:

~~~text
current method annotation
method annotation on interface A
method annotation on interface B
current class annotation
superclass annotation
global annotation
~~~

If A and B both declare different annotations, there is no automatic rule for “which interface is more right”. Choose to report ambiguity, define a justified deterministic order, or merge if semantics permit. Be sure to write tests for diamond inheritance, matching method names, and source generation.

### 12.7. Java Element Defaults Are Not Scope Fallbacks

To reiterate: an annotation `@RetryPolicy(attempts=...)` with an `attempts() default 3` element does not automatically blend with an annotation on the enclosing class. When a method has `@RetryPolicy`, any omitted elements take the defaults of the **annotation type**. To inherit individual elements from the class, you must design an API to represent “unspecified” (perhaps using a valid sentinel) and write merge logic—which usually adds complexity.

### 12.8. Changing the Policy Is Changing the API Contract

If version 1 uses `method > class > deny` while version 2 uses `class > method > allow`, the source annotations remain unchanged yet runtime behavior changes drastically. When releasing, treat policy precedence and missing behavior as part of the **public contract**: provide documentation, versioning, migration tests, and a changelog. Above all, never change a default deny to allow without evaluating the consequences.

## 13. Common Mistakes and How to Fix Them

**Mistake 1 — Two annotations at the same level, and the code picks whichever it checks first.** This makes precedence depend on code order with no clear rule. Detect the conflict and emit a diagnostic, or design a documented precedence order.

**Mistake 2 — Skipping class validation as soon as a method annotation is found.** If the contract requires all declared metadata to be valid, class conflicts must be detected even when the method overrides. The `InvalidClass.action` example illustrates this.

**Mistake 3 — Treating “no annotation” as allow.** For access policies, this is usually dangerous behavior. Choose deny by default or require an explicit policy, depending on the system.

**Mistake 4 — Confusing `@Roles({})` with having no `@Roles`.** A present annotation with an empty value is a different event from missing. If an empty list is invalid, report an error.

**Mistake 5 — Thinking `@Retention(RUNTIME)` determines priority.** Retention only controls whether Reflection can read metadata at runtime. The resolver itself must define precedence.

**Mistake 6 — Relying on the return order of `getAnnotations()`.** The API does not define a business order for choosing a winner. Read the exact annotation types and apply transparent rules.

**Mistake 7 — Assuming `@Inherited` applies to overridden methods.** It does not. `@Inherited` applies to class annotations under specific rules; the resolver must handle method hierarchies itself.

**Mistake 8 — Treating invalid role names as missing.** For `@Roles({""})` or an invalid role, fail fast instead of falling back just to “make it run”.

**Mistake 9 — Using a hidden global default.** Users will struggle to predict behavior. Document it and expose the source of the decision.

**Mistake 10 — Using `Class.getAnnotation` when you only want direct declarations.** It may inspect inheritance with `@Inherited`. `getDeclaredAnnotation` is useful when the resolver controls the search hierarchy itself.

**Mistake 11 — Applying the policy only during scanning, not at execution time.** Annotations on their own do not block calls; if this is an access policy, the execution point must strictly invoke enforcement.

**Mistake 12 — Not testing the missing case.** Unit tests often contain only annotated methods and thus fail to catch wrong defaults. Add classes and methods with no annotations at all.

**Mistake 13 — Not testing class-level conflicts when a method overrides.** A resolver can accidentally “short-circuit” early and ignore the error. Test cases like `InvalidClass`.

**Mistake 14 — Comparing policies using UI strings instead of data structures.** Strings like `ROLES[staff]` are convenient for illustration, but large systems should use immutable enums/records with explicit fields.

## 14. Practice Exercises

1. **Reverse precedence:** Modify the resolver to pick class before method. Re-run and point out which lines change. Discuss the consequences when a class is open but a method wants to restrict access.
2. **Add an explicit deny:** Create `@DenyAll` and update `read(...)` to detect same-level combinations with `@PermitAll`/`@Roles`. Decide the policy for `@DenyAll` when a method overrides a class.
3. **Mandatory missing check:** Set `required=true` for all methods. Predict the error for `Unmarked.probe` and explain the reason for failing fast.
4. **Role validation:** Try `@Roles({"Admin"})` or `@Roles({""})`. Explain why the error is `INVALID_ROLES` and not `MISSING`.
5. **Class conflict:** Try two annotations on a class and a `@Roles` on a method. Observe that the class error still surfaces before the method is selected.
6. **Method overload:** Create two methods `handle(String)` and `handle(int)` with different policies, and update the resolver to accept the exact parameter types for Reflection resolution.
7. **Superclass:** Create `Base` with `@Roles({"staff"})` and `Child extends Base`. Write a new rule that looks up the parent class when the subclass and current method lack a policy; describe how to handle the case where the subclass has its own annotation.
8. **Interface conflict:** Create two interfaces with a method sharing the same signature but having different policies. Propose at least two strategies (report ambiguity, rule-based precedence, or merge) and the trade-offs of each.
9. **Repeatable annotations:** Design a repeatable `@Tag` annotation and read it with `getAnnotationsByType(Tag.class)`; decide how to merge duplicates and ordering.
10. **Compile-time validation:** Write an annotation processor that detects `@PermitAll` and `@Roles` at the same level. Extend the processor to find methods completely lacking a policy when one is mandatory, instead of iterating only over annotated methods.
11. **Test matrix:** Use JUnit or a main method to assert the 9 stdout lines of `AccessPolicyDemo.java` as a formal contract.
12. **Policy origin:** Extend `Decision` with `originClass`, `originMethod`, or a `Source` enum. Log “where the policy came from” without relying on string messages.
13. **New contract:** Choose a non-security system, such as `@Cache(ttl)` and `@NoCache`. Build your own conflict/precedence/missing table and implement the corresponding resolver.

## 15. Design Checklist Before Publishing an Annotation API

| Question | Required Answer |
| --- | --- |
| Which annotation types are mutually exclusive? | State the conflict set explicitly |
| If one level has multiple valid annotations, merge or reject? | Specific rules, not relying on Reflection order |
| Both class and method have annotations? | Precedence order written as a table |
| Method has no annotation? | Whether it falls back to the class or not |
| Neither level has an annotation? | Transparent default/required/error behavior |
| Annotation has an invalid/empty value? | Validate and report an error with its location |
| Can an override hide a class conflict? | Clear validation policy |
| Should superclass/interface be searched? | Defined scope and tie-breaking rules |
| Is `@Inherited` used? | Understand the class-only limitation and corresponding APIs |
| Do annotation elements have defaults? | Do not confuse element defaults with policy fallbacks |
| Are rules applied at compile-time or runtime? | Choose the appropriate annotation processor/Reflection approach |
| What if the policy is sensitive? | Enforce at the execution point; fail-closed on errors |
| Is the entire matrix tested? | Includes missing, invalid, conflict, and override cases |

**Summary:** Good annotation design is not just declaring an `@interface`. You must clearly define **precedence across levels**, **conflicts within a level**, **missing-configuration cases**, **invalid values**, **inheritance behavior**, and **when errors are detected**. A small resolver with an explicit contract, thorough tests, and no reliance on arbitrary ordering is far more reliable than a system built on a chain of unspecified `if` statements.

### References

- [Java SE 17 — AnnotatedElement: getAnnotation, getDeclaredAnnotation, getAnnotationsByType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html).
- [Java SE 17 — Class: annotation Reflection methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 — ElementType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/ElementType.html).
- [Java SE 17 — RetentionPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/RetentionPolicy.html).
- [Java SE 17 — Inherited](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Inherited.html).
- [Java SE 17 — RoundEnvironment](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/RoundEnvironment.html).
- [Java Language Specification 17 — `9.6, Annotation Interfaces; `9.7, Annotations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html).
