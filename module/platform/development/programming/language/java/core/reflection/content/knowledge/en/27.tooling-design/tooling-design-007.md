# Validating Types and Accessibility Before Batch Execution with Java Reflection

A batch tool using Reflection may receive multiple classes/methods from configuration. If it calls `invoke` as soon as it finds each one, the seventh item having a signature mismatch could be discovered **after the first six items have already caused side effects**. This article builds a **whole-batch preflight** step: checking contract, receiver, signature, accessibility, and inputs; producing a validated plan before running anything.

Preflight only blocks errors detectable early. It does not guarantee the target method will not throw, does not itself provide transactions or rollbacks, and does not replace execution-time authorization. The sections below focus on the accuracy of `isAssignableFrom` and `canAccess` checks, and on keeping the plan and caller consistent.

## 1. The problem: avoiding partial execution due to pre-detectable errors

Suppose a batch receives three steps:

1. `TextNormalizer.normalize(String)` returns `String`.
2. `EmailValidator.validate(String)` returns `String`.
3. `ReportExporter.export(int)` while the runner will pass a `String`.

Executing immediately during traversal:

```text
for each item:
    look up method from metadata
    invoke method immediately
    if error then stop
```

When the third item has a signature mismatch, the program only discovers the error after the first two items have already run. The consequences could be sent emails, written files, DB mutations, or emitted events that cannot be easily reversed.

The **plan-before-invoke** approach:

```text
[Input / configuration]
       |
       v
[Look up class, method, constructor]
       |
       v
[Validate type + signature + receiver + access rights]
       |
       +---- Any error? ----> [Reject whole batch, report failing items, no invoke]
       |
       v
[Build validated invocation plan]
       |
       v
[Execute per policy: sequential / parallel / retry / transaction]
       |
       v
[Collect results and handle runtime errors]
```

**Principle:** configuration errors or Reflection mismatches knowable upfront should be detected before the very first call. Errors inside user code, race conditions, I/O, timeouts, or system changes still must be handled in the execution phase.

## 2. Verification layers required

| Layer | What to prove | Suggested API | If invalid |
| --- | --- | --- | --- |
| Input type | Value is non-`null`; class is in allowed group | `Objects.requireNonNull`, `Class.isInstance`, allowlist | Reject item |
| Inheritance / interface relationship | Class implements the required contract | `RequiredType.class.isAssignableFrom(candidateClass)` | Reject item |
| Member metadata | Method/constructor exists and is uniquely selected | `getMethod`, `getDeclaredMethod`, `getDeclaredMethods`, `getDeclaredConstructor` | Reject if missing/duplicate |
| Signature | Parameter count and types, return type, static/instance, varargs match contract | `getParameterTypes`, `getReturnType`, `Modifier`, `isVarArgs` | Reject before `invoke` |
| Accessibility | Can the caller invoke the method with the actual receiver? | `Method.canAccess(receiver)` | Reject or apply controlled access-opening policy |
| Business rules | Are the class, package, annotation, and action permitted to run? | allowlist, registry, runtime-retained annotations, user permissions | Reject even if Java reflection could invoke |
| Execution plan | Every item is validated before side effects start | immutable list containing `target` and `Method` | Do not build plan if any error exists |

Important: **"accessible in the Java language" does not mean "permitted to run by business rules"**. A `public` method can be valid for Reflection yet still dangerous if received from untrusted configuration. You must verify both access rights and the list of permitted operations.

## 3. Type validation: properly understanding `isInstance`, `isAssignableFrom`, and signatures

### 3.1. Actual object types

- `Expected.class.isInstance(value)` checks whether an **object** is an instance of the required type; for `null` the result is `false`.
- `Expected.class.isAssignableFrom(Candidate.class)` checks whether a **type** can be assigned to a variable declared as `Expected`, including extends/implements relationships.
- Call direction must not be reversed: `Runnable.class.isAssignableFrom(MyRunnable.class)` may be true, whereas `MyRunnable.class.isAssignableFrom(Runnable.class)` is usually false.
- When you only need to check an object against a known interface, `value instanceof MyInterface` or `Expected.class.isInstance(value)` is usually clearer.

Example:

```java
interface Task {}
class EmailTask implements Task {}

boolean a = Task.class.isAssignableFrom(EmailTask.class); // true
boolean b = EmailTask.class.isAssignableFrom(Task.class); // false
boolean c = Task.class.isInstance(new EmailTask());       // true
```

When running multiple plugins, define a stable contract such as a marker interface, base class, or registry, and validate the contract before dynamically looking up members. When the business API already has an interface with the right method, **calling directly through the interface is usually simpler and more type-safe than Reflection**; reserve Reflection for dynamic discovery/configuration where truly needed.

### 3.2. Parameter types and return type

Methods with the same name do not necessarily share the same signature:

```java
void process(String text) {}
void process(Integer number) {}
String process(String text, int retry) { return text; }
```

The snippet above only illustrates valid overloads; a runner requiring `process(String)` returning `String` must check **both parameter types and return type**, because Reflection does not automatically enforce result types for the plan:

```java
// Assume method is a java.lang.reflect.Method already looked up.
boolean takesExactlyOneString =
        java.util.Arrays.equals(
                method.getParameterTypes(),
                new Class<?>[]{String.class});
boolean returnsString = method.getReturnType() == String.class;
```

In a contract with an **exact** signature, comparing `Class<?>` with `==` is right because `Class` objects represent runtime types; this differs from comparing data object contents.

In a contract permitting subtypes, use `isAssignableFrom` in the right direction and account for primitives, boxing/unboxing, `null`, and varargs. Never blindly use `String.class.isAssignableFrom(paramType)`: an API accepting `CharSequence` can still accept a `String`, even though that check direction returns `false`.

For generics such as `List<String>`, `getParameterTypes()` sees `List.class` due to **type erasure**. If a batch requires generic constraints, you can inspect `getGenericParameterTypes()`, though generic metadata **does not automatically validate individual elements at runtime**; a separate validator is required.

### 3.3. Static / instance, receiver, and varargs

`Method.invoke` passes the receiver differently depending on member kind:

| Member kind | Receiver for `invoke` / `canAccess` | What to check |
| --- | --- | --- |
| Instance method | An object of the declaring class or a subtype | Receiver is non-`null`, `declaringClass.isInstance(receiver)` |
| Static method | `null` | `Modifier.isStatic(method.getModifiers())` |
| Constructor | Do not use `Method.invoke`; use `Constructor.newInstance` | Types, arguments, and constructor accessibility |
| Varargs method | Has trailing array parameter | `method.isVarArgs()` and argument-packing policy |

For instance, `canAccess(null)` is invalid for an instance method. For a static method, `canAccess(nonNullReceiver)` is also wrong. Determine the member kind before calling the accessibility check.

**Varargs** needs explicit design: in Reflection, `Method.invoke` itself has a varargs parameter, and the target method may also be varargs. If the runner does not support it, reject `isVarArgs() == true`; if supported, explicitly pack into an array of the proper type to avoid passing mismatched arguments.

### 3.4. Checking for one or multiple methods when scanning annotations

For a tool scanning `@BatchAction`:

- `getDeclaredMethods()` only retrieves methods **declared directly on that class**; includes non-public, does not automatically find inherited methods.
- `getMethods()` returns `public` methods (including inherited ones), under a different policy.
- When scanning annotations, decide whether annotations apply to declared or inherited methods, how overloads are handled, and whether multiple entry points are allowed on the same class.
- Watch out for compiler-generated `synthetic` or `bridge` methods, especially on generic classes. Filter them out with `isSynthetic()`/`isBridge()` when scanning entry points.
- Annotations used for runtime lookup must declare `@Retention(RetentionPolicy.RUNTIME)`; the default does not retain them for this type of scan.

If the contract requires **exactly one** annotated method, verify `count == 1` before execution. Never arbitrarily pick "the first method" because `getDeclaredMethods()` order is not a stable ordering contract.

## 4. Validating accessibility: `canAccess` and JPMS limits

Finding metadata does not mean the member can be invoked.

### 4.1. `public` is a simple condition, not the whole story

`Modifier.isPublic(method.getModifiers())` only inspects the method's access modifier. For actual methods, invocability also depends on the declaring class, package, module, and caller.

`Method.canAccess(receiver)` checks access rights **from the class calling that check API**, with the specific receiver. Call it in the same class/executor layer that will later execute `invoke`:

```java
// Assume method is an instance method and target's type is verified.
if (!method.getDeclaringClass().isInstance(target)
        || !method.canAccess(target)) {
    throw new IllegalArgumentException("Method is not accessible");
}
```

Do not apply `canAccess` from a helper in a different module and assume the executor has the same rights. For static methods, pass `null`. `canAccess` does not execute the target method's body.

### 4.2. `getMethod` and `getDeclaredMethod` differ

- `getMethod("run", String.class)` finds a `public` method by name and parameter types, including matching inherited methods.
- `getDeclaredMethod("run", String.class)` finds a method declared in the current class, regardless of private/protected/package-private/public; does **not** automatically include inherited methods.
- Both can throw `NoSuchMethodException`; convert it into a configuration error with clear context: "which class, which method, which signature".

Using `getDeclaredMethod` to find a private method **does not grant extra permission** to invoke it.

### 4.3. `trySetAccessible`, `setAccessible`, and modules

`trySetAccessible()` can enable bypassing access checks **if** the environment/module permits it; when disallowed, it normally returns `false`. `setAccessible(true)` can throw `InaccessibleObjectException` when access cannot be opened. These are not APIs to "break" every module boundary.

With named modules (Java Platform Module System):

- `exports p` allows public APIs in package `p` to be accessed normally by modules reading it.
- `opens p` or `opens p to other.module` allows appropriate deep reflection mechanisms on that package.
- `privateLookupIn` with `MethodHandles.Lookup` must also satisfy access/module conditions; knowing a method name confers no automatic rights.

For **batch runner tools**, default to rejecting when `canAccess` returns `false`, and describe how to fix it via public API, module descriptor, or plugin contract. Consider `trySetAccessible` only when it is an explicitly approved policy, target objects lie within a trusted boundary, and access control is clear.

## 5. Java 17+ example: validate the whole batch before executing

The example builds a batch runner reading a list of objects under the `Job` contract, finding **exactly one** `@BatchAction` method per class, requiring the exact signature `public String execute(String)`, and executing **only after all steps have been verified**.

Design characteristics:

- `preflight` only inspects metadata and creates `List<Invocation>`; it **never calls** business methods.
- A method with return type `int` is rejected before any `execute` runs.
- `List.copyOf` creates a structurally immutable plan list; this does **not** make target objects immutable.
- `runs` clearly proves an invalid batch causes no side effects from business methods.

Create file **`BatchPreflightDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class BatchPreflightDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    public @interface BatchAction {}

    public interface Job {}

    public static class Upper implements Job {
        @BatchAction
        public String execute(String text) {
            runs++;
            return text.toUpperCase(Locale.ROOT);
        }
    }

    public static class Prefix implements Job {
        @BatchAction
        public String execute(String text) {
            runs++;
            return "OK: " + text;
        }
    }

    public static class Wrong implements Job {
        @BatchAction
        public int execute(String text) {
            runs++;
            return text.length();
        }
    }

    private record Invocation(Object target, Method method) {}
    private static int runs;

    private static List<Invocation> preflight(List<?> targets) {
        List<Invocation> plan = new ArrayList<>();
        for (Object target : targets) {
            if (target == null) {
                throw new IllegalArgumentException("Null target");
            }
            Class<?> type = target.getClass();
            if (!Job.class.isAssignableFrom(type)) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + " does not implement Job");
            }
            List<Method> methods = Arrays.stream(type.getDeclaredMethods())
                    .filter(m -> m.isAnnotationPresent(BatchAction.class))
                    .toList();
            if (methods.size() != 1) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + " must have exactly one @BatchAction");
            }
            Method method = methods.get(0);
            if (!Modifier.isPublic(method.getModifiers())
                    || Modifier.isStatic(method.getModifiers())
                    || method.isSynthetic()
                    || method.isBridge()
                    || method.isVarArgs()) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + ".execute must be a valid public instance method");
            }
            if (!Arrays.equals(method.getParameterTypes(),
                    new Class<?>[]{String.class})) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + ".execute must accept String");
            }
            if (method.getReturnType() != String.class) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + ".execute must return String");
            }
            if (!method.getDeclaringClass().isInstance(target)
                    || !method.canAccess(target)) {
                throw new IllegalArgumentException(type.getSimpleName()
                        + ".execute is not accessible");
            }
            plan.add(new Invocation(target, method));
        }
        return List.copyOf(plan);
    }

    private static void execute(List<Invocation> plan, String input)
            throws IllegalAccessException {
        for (Invocation step : plan) {
            try {
                String result = (String) step.method().invoke(
                        step.target(), input);
                System.out.println(step.target().getClass().getSimpleName()
                        + " -> " + result);
            } catch (InvocationTargetException ex) {
                throw new IllegalStateException("Error executing "
                        + step.target().getClass().getSimpleName(),
                        ex.getCause());
            }
        }
    }

    public static void main(String[] args) throws IllegalAccessException {
        try {
            List<Invocation> invalid =
                    preflight(List.of(new Upper(), new Wrong()));
            execute(invalid, "hello");
        } catch (IllegalArgumentException ex) {
            System.out.println("Batch rejected: " + ex.getMessage());
        }
        System.out.println("Execution count: " + runs);

        List<Invocation> valid =
                preflight(List.of(new Upper(), new Prefix()));
        System.out.println("Preflight: " + valid.size() + " valid steps");
        execute(valid, "hello");
        System.out.println("Execution count: " + runs);
    }
}
```

Compile and run:

```bash
javac BatchPreflightDemo.java
java BatchPreflightDemo
```

Run output:

```text
Batch rejected: Wrong.execute must return String
Execution count: 0
Preflight: 2 valid steps
Upper -> HELLO
Prefix -> OK: hello
Execution count: 2
```

Explanation:

1. `Wrong.execute(String)` has return type `int`. Because `getReturnType() != String.class`, `preflight` throws `IllegalArgumentException` **before** `execute(invalid, ...)`. The `runs` variable remains 0.
2. The second batch consists of `Upper` and `Prefix`: each class has exactly one annotated method with the required signature, and `canAccess(target)` returns `true`.
3. Only after `preflight` returns the complete plan does `execute` call `Method.invoke` step by step. Output matches the program compiled and run on the JDK.
4. This case intentionally uses public nested classes in the same program so the example is standalone, and thus does not demonstrate access failures between two named modules. When integrating real plugins, verify `canAccess` in that deployment environment.
5. The example treats **directly declared** annotated methods as entry points, ignoring inherited methods. To support inherited methods, explicitly update the lookup policy.

## 6. When configuration data is a class name or method name

Some tools receive configuration like:

```text
implementation = "com.acme.plugins.ExportJob"
method         = "execute"
parameterType  = "java.lang.String"
```

This is **input data needing validation**, not a license to call any arbitrary method.

Recommended sequence:

1. **Authenticate requester, configuration source, and allowlist**: allow only approved plugins/classes/actions; never let users arbitrarily enter system classes or dangerous methods.
2. **Controlled class loading**: choose an appropriate `ClassLoader`; `Class.forName(name, false, loader)` can load the class without requiring immediate initialization. Do not assume class loading is completely risk-free.
3. **Validate class**: `expectedInterface.isAssignableFrom(candidate)`, non-abstract/non-interface if instantiation is needed, reject classes violating policy.
4. **Validate constructor**: find the matching signature with `getDeclaredConstructor(...)`; verify access with `constructor.canAccess(null)`. If instantiating via constructor, recognize that `newInstance` itself can run code and have side effects; depending on the tool, defer instantiation to the execution phase or design a dedicated plugin factory.
5. **Validate method**: name, overload, parameters, return type, modifiers, annotations, receiver, access rights, module context.
6. **Build the plan**: store metadata and converted/validated arguments. Tag the configuration source for accurate error reporting.
7. **Execute**: run in deterministic order, apply failure policy, audit/log, and use transactions when required.

**Note on constructors:** If you truly want "no side effects before every item passes preflight", do not invoke plugin constructors during inspection: constructors or static initializers can execute business behavior. The example in section 5 accepts **pre-created instances** and only guarantees `@BatchAction` methods are not called before full validation; creating those instances lies outside preflight.

### How much should be checked upfront?

Preflight should verify conditions **decidable from metadata and inputs**: missing method, signature mismatch, insufficient access rights, unconvertible input, unregistered plugin, conflicting configuration, forbidden method. It cannot predict every exception from target code or runtime resource availability.

If a batch touches files/DB/network, you can add resource and business-permission checks, though those are only point-in-time checks. A resource can vanish right after checking; the executor must still handle errors thoroughly.

## 7. Preflight is not a transaction and does not eliminate all Reflection errors

### What can go wrong after validation succeeds

- A method may throw an exception due to internal logic; `Method.invoke` wraps exceptions from target code in `InvocationTargetException`. Use `getCause()` to inspect the root cause.
- The receiver's state may mutate or a resource may become invalid.
- A `public` method can still throw `IllegalArgumentException` if runtime arguments differ from the validated ones.
- The application may run out of order, be cancelled, time out, or execute redundantly on retry.
- Class loader/redeployment can produce a class with the same name but **different identity**; do not treat a class-name string as proof that an object belongs to the exact `Class<?>` that was checked.
- Instances can hold mutable internal state while waiting. An immutable plan only freezes the step list, not the outside world.

Therefore, when a batch mutates data it needs a clear policy: **fail-fast**, per-item error recording, bounded retries, idempotency keys, compensation, or database transactions where appropriate. Distributed multi-resource transactions do not appear automatically just because preflight completed.

### Classifying errors for accurate reporting

| At which step | Common error/API | Appropriate reporting |
| --- | --- | --- |
| Class lookup | `ClassNotFoundException` or class-loading errors | Name/loader and invalid configuration |
| Member lookup | `NoSuchMethodException`, `NoSuchFieldException` | Name and expected signature |
| Access rights | `canAccess` returns `false`, `IllegalAccessException`, `InaccessibleObjectException` when requesting open | Class, package, module, and permission contract |
| Wrong argument invocation | `IllegalArgumentException`, `WrongMethodTypeException` when using method handle APIs | Actual type and expected type |
| Target code throws | `InvocationTargetException` | Distinguish business error, log root cause |
| Cannot instantiate | `InstantiationException`, constructor failure, abstract class | Instance type to create and cause |

Do not print full sensitive input data into logs; in multi-item batches, report position, step code, and cause sufficient to fix the configuration.

## 8. Designing a checked plan for real systems

For large batches, build a data type recording each step's details, for example:

```java
// Model sketch, not a standalone program.
record CheckedCall(
        String stepId,
        Object target,
        java.lang.reflect.Method method,
        Object[] arguments) {}
```

Each `CheckedCall` can also carry policy, order, log target, permission context, deadline, and validation outcome. Only add to the final plan when every condition is valid. When multiple errors must be handled together, collect all diagnostics in a single pass and reject execution if at least one error exists; avoid fixing items one by one via costly run–fail–fix cycles.

Points to consider:

- **Configuration snapshot**: prevent another thread from mutating the method/argument list after preflight. If arguments are mutable objects, snapshot them or apply proper synchronization; `List.copyOf` does not freeze internal object state.
- **Right caller for `canAccess`**: verify permissions at the executor layer itself (or equivalent permission design), because Java access checks carry class/module context.
- **Difference between metadata and policy**: annotations express registration intent, whereas allowlists/authorization decide which specific user may run.
- **Repeated invocations**: cache metadata or plans when appropriate; invalidate caches when plugins change class loader/version. `Method` can be reused across multiple receivers of the right type.
- **Deterministic order**: do not rely on the return order of `getDeclaredMethods()`; sort or take order from explicit configuration.
- **Resource limits**: verify batch size, timeouts, input lengths, thread counts, and file/network permissions before running.
- **Observability and error reporting**: diagnostics must pinpoint which step, expected/actual signature, access rights, and whether execution had started.

If the problem only needs standardized operations checked through a uniform interface, you can design `List<Processor>` with direct `process(...)` calls. Reflection fits better when a framework must **dynamically discover and wire metadata**, not to replace every strongly typed call.

## 9. Checklist before pressing "Run batch"

1. Are the configuration source and allowed class/method list verified?
2. Do all classes/receivers/constructors match the contract with no `null` or wrong types?
3. Are methods looked up under an explicit policy (declared/public/inherited, annotations, overloads)?
4. Are parameter count/types, return type, modifiers, varargs, and bridge/synthetic checked **precisely**?
5. Is actual permission from the executor verified via `canAccess` with the right receiver type; does JPMS allow it?
6. Are all arguments validated or safely converted so pre-detectable errors do not leak into execute?
7. Are **all steps** checked before the first business invocation? Can the plan be mutated after preflight?
8. Are `InvocationTargetException`, timeouts, retries, per-step failures, and already-occurred side effects handled?
9. Are transactions, idempotency, or rollback/compensation needed to guarantee integrity?
10. Do logs have enough context to fix configuration without leaking sensitive data?

### Self-check questions

- Why does `getDeclaredMethod` finding a private method not prove `invoke` will be permitted?
- In which direction must `isAssignableFrom` be called to check whether a plugin implements an interface?
- If a method expects `String` but the runner passes `Integer`, in which phase should that be detected?
- Is `canAccess(null)` suitable for a static method or an instance method?
- If preflight finishes but step 4 throws an exception, does the system automatically roll back earlier steps?
- If a plugin constructor has side effects, does instantiating it during preflight still preserve the "no business logic run yet" guarantee?

### Official references

- [`Class` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isInstance`, `isAssignableFrom`, method and constructor lookup.
- [`Method` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): signatures, `invoke`, and metadata.
- [`AccessibleObject` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): `canAccess`, `trySetAccessible`, and access limits.
- [`InvocationTargetException` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html): wrapped error when a target method or constructor throws an exception.
- [Java Language Specification `6.6](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): access control rules.
