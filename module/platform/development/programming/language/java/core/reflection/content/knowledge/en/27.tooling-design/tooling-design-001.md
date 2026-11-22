# Separating Metadata Discovery from Operation Execution in Java Reflection

In tools built on Java Reflection (plugin registries, command runners, tool registration systems, testing frameworks), there are two distinct responsibilities:

- **Discovery / metadata inspection:** finding operations that *can* be provided, reading their names, annotations, parameters, return types, access permissions, and then building a catalog.
- **Execution:** receiving a request to invoke a specific operation, checking permissions and inputs, preparing the receiver, and only then running the actual code.

Both tasks often use `Class<?>` and `Method` objects, but they do not have the same level of impact. A user clicking "View tool list" must not automatically become a call that deletes data, sends emails, or updates state. Separating the two phases helps control side effects, makes testing easier, and records who executed which operation.

## 1. Distinguishing metadata retrieval from behavior invocation

| Activity | Illustrative API | Result | Requires running business method? |
|---|---|---|---|
| Type reference | `SomeType.class` | `Class<?>` | No |
| Load without requiring initialization | `Class.forName(name, false, loader)` | `Class<?>` | No |
| List methods | `type.getDeclaredMethods()` | `Method[]` | No |
| Read signature/annotation | `getName()`, `getParameterTypes()`, `getAnnotation(...)` | Metadata | No |
| Register action | Check annotation/signature, create descriptor | Catalog | No |
| Invoke method | `method.invoke(receiver, args...)` | Result/exception/side effect | **Yes** |
| Invoke constructor | `constructor.newInstance(...)` | New object | **Yes** |
| Read/write field | `field.get(...)` / `field.set(...)` | Value/mutation | Performs real operation on state |

Example:

```java
Method action = Service.class.getDeclaredMethod("process", String.class);
// Only found information about the method so far.

Object result = action.invoke(service, "payload");
// Executed process(...) on the service object.
```

This is an illustrative snippet assuming `Service`, `service`, return type, method, and access permissions are all appropriate. For a static method, the receiver for `Method.invoke` can be `null`.

**Precision note:** discovery does not strictly mean "the JVM does nothing". Loading a class or reading signatures can cause the JVM to load/resolve dependent classes or throw `LinkageError`; a custom class loader can execute its own logic. However, those metadata APIs **do not automatically invoke the business methods being listed**. If you want to avoid triggering class initialization just to read metadata, consider `Class.forName(name, false, loader)` instead of `Class.forName(name)`.

## 2. A clearly separated architecture

```text
Register allowed types / plugins
                 |
                 v
             DISCOVER
   - Class<?> / getDeclaredMethods()
   - read annotations, names, signatures
   - no invoke, no instance creation to "test"
                 |
                 v
             VALIDATE
   - allowlist, unique ID, visibility
   - signature, description, impact level
                 |
                 v
       IMMUTABLE REGISTRY
      /                  \
     v                    v
LIST/DESCRIBE           EXECUTE
Return metadata    1. Resolve action ID
Do not run code    2. Authenticate and authorize
                   3. Validate input / policy
                   4. Prepare receiver if needed
                   5. Invoke, audit, return result
```

**Registry** is the boundary between the catalog and execution. Each entry should have a stable ID, description, input schema, output schema, permission requirements, impact level (read/write/external send), and an **internal** handle or executor.

The client side should only receive safe descriptive fields, not `Method` objects, receivers, or the ability to invoke Reflection directly. When a request sends `actionId="publish"`, the server looks up the registered entry, checks permissions at **execution time**, and only then dispatches.

Things that must be separated:

1. **Discovery is not authorization:** seeing an action does not mean being permitted to run it.
2. **Annotations are not security truth:** `mutates=false` is a declaration provided by the developer; the implementation code must still be evaluated.
3. **Approval of impactful operations** is trusted state managed by the server, not a boolean arbitrarily chosen by the caller.

## 3. Java 17+ example: inspecting metadata without triggering static initializer

The following program introduces a `@ToolAction` annotation, finds valid methods in a class, stores them in a registry, and only executes them on an explicit call. `Actions` has a static initializer to observe **exactly when the class is initialized**.

Save as **`ReflectionToolBoundaryDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Map;
import java.util.TreeMap;

public class ReflectionToolBoundaryDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface ToolAction {
        String name();
        boolean mutates() default false;
    }

    public static class Actions {
        static {
            System.out.println("Actions initialized");
        }

        @ToolAction(name = "preview")
        public static String preview(String payload) {
            return "Preview: " + payload;
        }

        @ToolAction(name = "publish", mutates = true)
        public static String publish(String payload) {
            System.out.println("Published: " + payload);
            return "OK";
        }

        public static String hidden(String payload) {
            throw new AssertionError("not registered");
        }
    }

    record ActionDescriptor(String name, boolean mutates, Method method) {}

    static Map<String, ActionDescriptor> discover(Class<?> type) {
        Map<String, ActionDescriptor> actions = new TreeMap<>();
        for (Method method : type.getDeclaredMethods()) {
            ToolAction config = method.getAnnotation(ToolAction.class);
            if (config == null) continue;

            if (!Modifier.isPublic(method.getModifiers())
                    || !Modifier.isStatic(method.getModifiers())
                    || method.getParameterCount() != 1
                    || method.getParameterTypes()[0] != String.class
                    || method.getReturnType() != String.class) {
                throw new IllegalArgumentException(
                        "Invalid action signature: " + method.getName());
            }

            ActionDescriptor previous = actions.putIfAbsent(config.name(),
                    new ActionDescriptor(config.name(), config.mutates(), method));
            if (previous != null) {
                throw new IllegalArgumentException(
                        "Duplicate action: " + config.name());
            }
        }
        return Map.copyOf(actions);
    }

    static String execute(Map<String, ActionDescriptor> actions,
                          String name, String payload, boolean permitMutation)
            throws ReflectiveOperationException {
        ActionDescriptor descriptor = actions.get(name);
        if (descriptor == null) {
            throw new IllegalArgumentException("Unknown action: " + name);
        }
        if (descriptor.mutates() && !permitMutation) {
            throw new SecurityException("requires authorization");
        }

        try {
            return (String) descriptor.method().invoke(null, payload);
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            if (cause instanceof RuntimeException runtime) throw runtime;
            if (cause instanceof Error error) throw error;
            throw e;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        System.out.println("1. Discovery");
        Class<?> clazz = Actions.class;
        Map<String, ActionDescriptor> registry = discover(clazz);
        registry.keySet().stream().sorted().forEach(
                name -> System.out.println("found: " + name));

        System.out.println("2. Try without authorization");
        try {
            execute(registry, "publish", "Ada", false);
        } catch (SecurityException ex) {
            System.out.println("blocked: " + ex.getMessage());
        }

        System.out.println("3. Execute preview");
        System.out.println(execute(registry, "preview", "Ada", false));

        System.out.println("4. Execute permitted publish");
        System.out.println(execute(registry, "publish", "Ada", true));
    }
}
```

Compile and run commands:

```bash
javac --release 17 -encoding UTF-8 ReflectionToolBoundaryDemo.java
java ReflectionToolBoundaryDemo
```

**Actual stdout verified with this code:**

```text
1. Discovery
found: preview
found: publish
2. Try without authorization
blocked: requires authorization
3. Execute preview
Actions initialized
Preview: Ada
4. Execute permitted publish
Published: Ada
OK
```

**Step-by-step explanation:**

1. `Actions.class` creates a type reference, and `getDeclaredMethods()` along with `getAnnotation(...)` read metadata, so the `Actions initialized` line does not appear yet.
2. Only the two methods annotated with `@ToolAction` are registered. `hidden(String)`, even though public, does **not** become an action. `TreeMap` and `.sorted()` make the output order deterministic because the order returned by `getDeclaredMethods()` is not guaranteed.
3. Unauthorized `publish` is blocked **before** `Method.invoke`. The `Actions` class is still not initialized.
4. `preview` is actually invoked via `invoke(null, "Ada")`. Because it is a static method, the JVM initializes `Actions` if it has not been initialized yet, printing `Actions initialized` exactly once.
5. `publish`, once permitted, prints `Published: Ada`. This call does not re-run the static initializer.
6. `Map.copyOf` prevents the returned registry from being structurally modified through normal `Map` APIs; controlling invoke permissions remains the responsibility of the executor. `ActionDescriptor` retains `Method` for internal use and does not expose it to the client.

**Intentional limitations:** the sample code only accepts `public static` methods with signature `String f(String)`, so no receiver needs to be created. For instance methods, the executor must determine the target lifecycle and use a receiver of the proper type rather than instantiating objects during discovery. `permitMutation` here is only used to demonstrate the blocking point, **not an authentication model**: a real system must derive permissions from server-side authenticated context and must never trust a flag sent by the client.

## 4. Which APIs should be called in each phase?

### Discovery: lookup and inspection only

- `Class.getDeclaredMethods()`: retrieves methods declared as private/package-private/protected/public, but does not grant permission to invoke them.
- `Class.getMethods()`: retrieves public methods, including inherited ones according to API semantics. Choose one of the two based on your needs and discovery constraints.
- `Method.getName()`, `getModifiers()`, `getParameterTypes()`, `getReturnType()`: read the signature.
- `AnnotatedElement.getAnnotation(...)`: reads annotations accessible at runtime; annotations need `@Retention(RUNTIME)` to be discoverable at runtime.
- `Class.getDeclaredConstructors()` / `getDeclaredFields()`: retrieve constructor/field descriptors without executing them.

Do not turn `getDeclaredMethods()` into an automatic tool list. A class may contain internal methods, callbacks, getters with side effects, administrative methods, and `Object` methods. Discovery requires an **allowlist** and type/annotation checks.

### Execution: actions that may have side effects

- `Method.invoke(...)` runs a method; invoking a static method can trigger initialization of the declaring class.
- `Constructor.newInstance(...)` executes a constructor, creates an object, and may run initialization beforehand.
- `Field.get(...)` / `Field.set(...)` access **values**, unlike `getDeclaredField(...)` which only looks up metadata. For static fields, they can trigger initialization.
- `MethodHandle.invoke(...)` / `invokeExact(...)` invoke an already looked-up handle, distinct from looking up the handle.

If you want to load a class solely for inventorying, `Class.forName(binaryName, false, loader)` avoids requiring class initialization of the target type during that call. However, class loading can still fail due to classpath, class loader, modules, or missing dependencies.

## 5. Registering tools properly

A useful registry entry typically has these fields:

| Field | Purpose |
|---|---|
| `actionId` | Stable, non-duplicate name/ID |
| `description` | Explains the action so callers understand it |
| `inputSchema` | Data types, constraints, size limits |
| `outputSchema` | Published result format |
| `effect` | Read data, write/modify, delete, or send externally |
| `requiredPermissions` | Permissions the executor must check |
| `method/handler` (internal) | Execution entry point once authorized |

Best practices:

1. Only inspect registered or allowed classes/packages/plugins. If plugins come from untrusted sources, using Reflection alone **does not create a sandbox**; appropriate isolation mechanisms are needed.
2. Use marker annotations and validate schemas/signatures **before** adding to the registry. Do not expose a method just because it is `public`.
3. Reject duplicate `actionId` values instead of silently overwriting methods; sort the catalog by ID for deterministic output.
4. Do not unconditionally use `setAccessible(true)` to bypass encapsulation; the Java module system can restrict access. Prefer intentional public entry points.
5. Create an immutable registry snapshot after validation. If hot reload is supported, publish the new registry in a controlled swap step so requests never observe a half-built catalog.
6. When exporting metadata as JSON, do not serialize raw `Method`, receiver, `ClassLoader`, secrets, or unnecessary internal details.

## 6. Executing properly and handling errors

A reliable executor should process in order:

1. **Resolve** the action ID from the validated registry. Do not take class/method names directly from client input and invoke Reflection arbitrarily.
2. **Authenticate and authorize** based on identity, role, tenant, target object, data scope, and current state. Permissions must be checked on **every call**.
3. **Validate/bind** input against the schema. Distinguish invalid input from execution errors.
4. **Check impact:** write, delete, and external-send operations require appropriate policy or confirmation; executions with retries need appropriate idempotency mechanisms. Do not treat a method named `preview` or a `readOnly` annotation as a guarantee of harmlessness.
5. **Prepare the receiver** for instance methods according to service/container lifecycle; do not instantiate objects just to inspect metadata.
6. **Invoke** and catch/log errors in a controlled manner; audit action ID, caller, authorization decision, outcome, and correlation ID, while avoiding logging secrets.

| Exception/issue | Where it typically arises | How to handle |
|---|---|---|
| `NoSuchMethodException` | Wrong name or signature lookup during discovery | Report configuration/registration error |
| `ClassNotFoundException`, `LinkageError` | Loading/resolving a class or dependency | Check class loader, module path, dependencies |
| `IllegalAccessException`, `InaccessibleObjectException` | Method access is restricted | Fix visibility or module boundary by design |
| `IllegalArgumentException` | Wrong receiver/parameter binding or input validation | Check schema and argument types |
| `InvocationTargetException` | Invoked method throws an exception | Inspect `getCause()`, classify business error |
| `ExceptionInInitializerError` | Static initialization failed | Identify initialization code, class state, and root cause |
| Timeout, repeated requests | Execution, especially operations with side effects | Resource limits, audit, idempotency; consider isolation |

**Note:** a deadline or timeout does not automatically guarantee that a running method will stop immediately or roll back side effects. Do not automatically retry impactful actions without appropriate safety guarantees.

## 7. Real-world scenarios

**CLI/command runner:** `list` and `help` commands only use the registry; only `run <action>` goes through the executor. Users can inspect system capabilities without modifying state.

**Plugin host:** at startup, register handlers and validate metadata; only when the user selects a plugin are instances created or methods invoked according to lifecycle. Constructors, callback registration, or DI can have side effects, so they must be managed in the right phase.

**Tool-calling system:** the "describe tools" step only returns names, descriptions, input schemas, and constraints. When a caller requests to run a tool, the backend authenticates, authorizes, and dispatches through the registry; sending the catalog to the caller **does not grant Reflection privileges**.

**Testing framework:** discovery lists methods annotated with `@Test`; execution builds fixtures, runs before-hooks, invokes tests, and collects results. Initializing test classes during discovery blurs the boundary between the two phases and makes side effects hard to control.

## 8. Common pitfalls and self-check questions

- **"Having a `Method` means the method has already run."** False: `Method` only holds metadata; `invoke` is an execution path.
- **"`getDeclaredMethods()` automatically sorts in source order."** False: do not rely on this order.
- **"Having an annotation means it is allowed to be called."** False: annotations help with registration or description, while authorization belongs to the executor.
- **"Just reading a class name with `Class.forName(name)` ensures the static block hasn't run."** False: the single-argument overload triggers class initialization.
- **"Not calling business logic during discovery means nothing underneath has any effect."** False: class loading/linkage or custom loaders still have their own behavior, so trust boundaries must be defined.
- **"Read-only tools are always harmless."** Not necessarily: getters can mutate state or perform I/O; you must inspect implementation and policy.
- **"Reporting `InvocationTargetException` to the user is enough."** Not enough: classify the cause to reveal the actual error from the invoked code.

**Question 1:** Why didn't the sample code print `Actions initialized` during discovery?

Because using `Actions.class` and reading `Method` objects/annotations do not require initialization of `Actions`. Invoking the static method `preview` via `invoke` triggers the first initialization.

**Question 2:** Do we need to call `Constructor.newInstance` to get the names of instance methods?

**No.** Method metadata can be read from `Class<?>` without creating an instance. Creating the receiver is execution-time work.

**Question 3:** Why still check permissions after building a safe registry?

Because the registry answers **"what can be offered"**, whereas execution permission depends on the caller, resource, and timing. Those conditions can change between calls.

## References

- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): looking up classes, methods, fields, constructors, and `forName`.
- [Java SE 17 — Method](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): metadata and `invoke`.
- [Java SE 17 — AccessibleObject](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html): Reflection access control.
- Java Language Specification §12.4.1 and JVM Specification §5: loading/linking/initialization rules.

**Key takeaway:** Discovery describes **what operations exist**; execution decides **who is permitted to call which operation with which input** and performs it under control. Do not turn metadata scanning into running business code.
