# Choosing Between Annotations and Explicit APIs Based on the Problem in Java

## 1. Design Question: Describing Metadata or Requesting Behavior Execution?

When designing Java libraries and applications, there are several ways to connect a class or method to an external mechanism. For example, if you want to register a handler to process a task, you can write:

```java
@Command("pay")
public String pay() {
    return "paid";
}
```

Or register directly using an API:

```java
registry.register("pay", service::pay);
```

Both approaches can lead to similar final behavior, but they represent **two different contracts**:

- **Annotation:** places descriptive information (*metadata*) on a program declaration. A compiler, annotation processor, framework, or reflection scanner must **actively read** the annotation and decide how to process it.
- **Explicit API:** Java code directly invokes a method/constructor/builder to request an action or create a configuration. The execution path and parameter types are expressed in a standard Java call.

There is no rule that "annotations are always more concise and therefore better" or "explicit APIs are always easier to understand". The choice depends on **when the values are known**, **who owns the behavior lifecycle**, **whether automatic discovery is needed**, **the degree of compiler checking required**, **modifiability and debuggability**, and **the cost of learning/maintaining the framework**.

The most important mindset:

> If the information is a relatively stable characteristic of a **declaration** and will be interpreted by a known tool, an annotation is a good candidate. If the information is **dynamic input, a runtime choice, a sequence of operations, or behavior control**, an explicit API is usually more suitable.

This is a design heuristic, not an absolute boundary. A system can, and often should, combine both.

## 2. What Can an Annotation Do and What Can It Not Do on Its Own?

An annotation type is declared using `@interface`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Command {
    String value();
}
```

The definition above states that:

- `@Command` can be placed on a method declaration.
- `value()` holds the command name of type `String`.
- With `RetentionPolicy.RUNTIME`, Java reflection can read the annotation on the method.
- `@Command` itself **does not invoke the method**, does not create a registry, does not open a connection, does not check permissions, and does not run `pay()` on its own.

For example:

```java
@Command("pay")
public String pay() {
    return "paid";
}
```

Without a processor/framework/runtime scanner reading `@Command` and setting up the dispatch mechanism, the annotation remains just metadata.

Meanwhile:

```java
registry.register("pay", service::pay);
```

is a **regular Java call**. When execution reaches this line, `registry.register(...)` is invoked. The registry can immediately store the handler, check for duplicate names, or report an error according to the programmed logic.

### An Annotation Is Not a Function Call

`@Command("pay")` is an annotation use in Java syntax; it is not equivalent to:

```java
Command("pay"); // Not how to "call an annotation".
```

To trigger logic based on an annotation, you must program a consumer: an annotation processor, a reflective scanner, or a framework capable of understanding that annotation.

## 3. Quick Comparison Table by Design Criteria

| Criterion | Annotation | Explicit API |
|---|---|---|
| Primary meaning | Metadata attached to a declaration | A call requesting behavior or configuration |
| Values | Typically constants or valid annotation structures known at compile time | Can be variables, objects, lambdas, collections, or runtime-computed results |
| Processing time | Source, class file, or runtime depending on `@Retention` and the consumer | When code calls the API; a builder can be invoked at startup |
| Binding to declaration | Very close to the described class/method/field | Can be centralized in bootstrap/configuration code |
| Component discovery | Suits a processor or scanner that scans metadata | Usually registered or called directly |
| Type checking | The compiler checks syntax/element types; business rules require a processor/framework | The compiler checks method signatures and generics; business rules still require API validation |
| Environment adjustment | Difficult if annotation values must change at runtime | Easy to pass values from config, users, or command parameters |
| Control flow | Indirect: requires knowing who scans and when | More explicit: locate the call site and follow the call path |
| Debugging | Adds layers of discovery, retention, scanning, and proxy/processor | Usually follows standard stack traces and regular calls |
| Framework overhead | May require scanning/processor/registration | May require bootstrap/builder, but involves less "magic" |
| Reusability | Metadata can be used by multiple tools designed to support it | Flexible method/interface contract where implementations can be passed |
| Expressiveness | Good for labels, rules, and short mappings | Good for workflows, conditions, branching, and runtime parameters |

The table describes tendencies rather than claiming that every annotation framework uses reflection scanning or that every explicit API executes immediately: some APIs only build configuration to be applied later. What to look at is the **consumer's actual contract**.

## 4. Cases Where Annotations Should Be Preferred

Annotations are useful when metadata is a **declarative and stable** property of an element.

### 4.1. Elements Need to Self-Describe for Multiple Tools

For example, marking a class as belonging to an internal API group:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.CLASS)
@Target(ElementType.TYPE)
@interface InternalApi {
    String owner();
}

@InternalApi(owner = "platform")
class CacheInternal {
}
```

A class-file analysis tool can read the metadata to generate reports or check architecture. If reading only takes place during source compilation, `SOURCE` may also suffice; if runtime reflection is needed, `RUNTIME` must be chosen.

Here, the metadata is attached directly to the **class declaration** and does not depend on the number of requests being processed.

### 4.2. The Framework Actually Has an Annotation-Based Discovery Mechanism

DI frameworks, web routing, persistence, or test frameworks usually define their own annotations. When using the right framework, annotations can help concisely declare the rules that the framework is programmed to read.

However, the presence of a custom-made `@MyRoute` does not automatically make the framework aware of it. You must use an annotation supported by the framework or write a corresponding extension/processor.

### 4.3. Compile-Time Checking or Code Generation Is Needed

A `@GenerateAdapter` annotation can be read from source by an annotation processor, which checks conditions and then generates Java source via `Filer`. If the metadata is only used at compile time, `RetentionPolicy.SOURCE` is usually sufficient.

Declaration example:

```java
@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.TYPE)
@interface GenerateAdapter {}

@GenerateAdapter
interface PaymentPort {}
```

This is only an **illustrative snippet**, without a code-generating processor yet. A processor must be implemented and configured in the build for `@GenerateAdapter` to take effect.

### 4.4. Short Metadata with a Stable Set of Types

Annotations are well suited to a small set of values such as:

- An enum specifying a classification level.
- A string for a logical identifier name.
- An array of `String`, enum, or nested annotation types.
- A class literal `SomeType.class` to describe a referenced type.

If values vary continuously per request or require large runtime objects, an annotation is no longer a natural place to hold them.

## 5. Cases Where Explicit APIs Should Be Preferred

### 5.1. Configuration Based on Runtime Conditions

For example, a timeout obtained from an environment variable, user preference, or configuration system:

```java
int timeoutMillis = Integer.parseInt(
        System.getenv().getOrDefault("PAYMENT_TIMEOUT_MS", "1500"));

client.setTimeoutMillis(timeoutMillis);
```

In this example, `setTimeoutMillis` is an illustrative method belonging to an application-defined client. Since the value is only known at runtime, an API that accepts a runtime `int` is appropriate.

It cannot be replaced with:

```java
@Timeout(milliseconds = Integer.parseInt(
        System.getenv("PAYMENT_TIMEOUT_MS")))
class PaymentClient {}
```

The snippet above is **invalid** in a Java annotation: an `int` element must accept a constant expression, whereas calling a method to read the environment is a runtime computation.

Some frameworks allow **expression strings** inside annotations such as `@Value("\${...}")` and resolve them at runtime; that is a **framework-specific mechanism** and does not change the Java rule that the annotation element holds a string valid at compile time. Designers must weigh the complexity and verifiability of this string-interpretation mechanism.

### 5.2. Behavior Is a Sequence of Steps with Branches or Callbacks

For example:

```java
if (account.isEligible()) {
    workflow.transfer(account, amount);
} else {
    workflow.reject(account);
}
```

This is illustrative code inside an application where `account`, `workflow`, and `amount` have already been declared. Decision flow, object state, and method invocation are tasks well suited to Java code. Using annotations to describe an entire sequence of operations often creates an implicit DSL that is hard to debug.

### 5.3. Passing Lambdas, Objects, Collections, or State Is Needed

Annotation elements only support a limited set of Java types: primitive types, `String`, `Class`, enums, annotations, and one-dimensional arrays of them. They do **not** accept `Supplier<T>`, `Predicate<T>`, `Map`, `List`, or object instances created with `new`.

An explicit API can use:

```java
registry.register(
        "pay",
        () -> service.pay(currentUserId));

Map<String, String> options = Map.of(
        "region", "ap-southeast-1",
        "mode", "safe");
```

This is an illustrative snippet that requires `registry`, `service`, and `currentUserId` in the current scope. The strength of an API is that it accepts runtime-computed objects/closures, is type-checked via generics, and can be validated according to business logic.

### 5.4. Tight Control Over Execution Timing and Order Is Needed

If behavior must occur **at an exact step** during bootstrap, an explicit API makes that point easy to find:

```java
registry.register("pay", service::pay);
registry.validate();
server.start();
```

This is Java pseudocode for a hypothetical API. It illustrates the sequence setup → validation → startup; it is not a standalone program.

With annotations, the discovery/registration order may be controlled by the framework and requires learning additional mechanisms for scanning, sorting, lifecycle hooks, and configuration precedence.

## 6. Three Decision Questions Before Writing `@interface`

Before creating a new annotation type, answer:

**Question A — When are the values known?**

- Fixed at compile time and tied to a class/method: lean toward an annotation.
- Known only when the application runs or varying by user/request: lean toward an API accepting runtime parameters.

**Question B — Who will read and execute the meaning of the metadata?**

- A framework or processor already supports that annotation type: an annotation is viable.
- There is no concrete consumer yet and you would need to build an entire scanner just to save a few lines of registration: consider an API first.
- A processor is needed to detect errors early/generate code: an annotation is advantageous when the build pipeline is controlled.

**Question C — What must be transparent to maintainers?**

- Code readers need to see the label/semantics right at the method: an annotation is good.
- Readers need to trace how a handler is conditionally added, replaced, or removed: an explicit API is good.
- Both metadata and active registry configuration are needed: combine annotations and APIs with clear responsibility boundaries.

When unsure, a **small API with a clear interface** is usually an easier-to-test starting point; add annotations only when the benefits of declarative discovery truly outweigh the consumer and lifecycle costs. This is a design recommendation, not a language rule.

## 7. Complete Java 17+ Example: The Same Task in Two Ways

This example uses a **simple registry** for parameterless actions returning `String`.

- The **annotation** path: `@Action("pay")`, `@Action("audit")` on methods; a runtime scanner uses reflection to register them.
- The **explicit API** path: calls `register("refund", supplier)` directly with a lambda using runtime data.

All classes are in **a single file `AnnotationOrApiDemo.java`**. No external libraries are required.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Supplier;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Action {
    String value();
}

class BillingActions {
    @Action("pay")
    public String pay() {
        return "paid";
    }

    @Action("audit")
    public String audit() {
        return "checked";
    }
}

class Registry {
    private final Map<String, Supplier<String>> actions =
            new TreeMap<>();

    public void register(String name, Supplier<String> callback) {
        if (name == null || name.isBlank() || callback == null) {
            throw new IllegalArgumentException("Invalid registration");
        }
        if (actions.putIfAbsent(name, callback) != null) {
            throw new IllegalArgumentException("Duplicate: " + name);
        }
    }

    public void registerAnnotated(Object instance) {
        for (Method method :
                instance.getClass().getDeclaredMethods()) {

            Action action = method.getAnnotation(Action.class);
            if (action == null) {
                continue;
            }

            if (method.getParameterCount() != 0 ||
                    method.getReturnType() != String.class) {
                throw new IllegalArgumentException(
                        "Expected zero-arg String method: "
                        + method.getName());
            }

            register(action.value(), () -> {
                try {
                    return (String) method.invoke(instance);
                } catch (IllegalAccessException |
                         InvocationTargetException ex) {
                    throw new IllegalStateException(ex);
                }
            });
        }
    }

    public String invoke(String name) {
        Supplier<String> callback = actions.get(name);
        if (callback == null) {
            throw new IllegalArgumentException("Unknown: " + name);
        }
        return callback.get();
    }

    public String names() {
        return actions.keySet().toString();
    }
}

public class AnnotationOrApiDemo {
    public static void main(String[] args) {
        Registry annotated = new Registry();
        annotated.registerAnnotated(new BillingActions());

        System.out.println("annotation names=" + annotated.names());
        System.out.println("annotation pay="
                + annotated.invoke("pay"));

        String orderId = args.length == 0 ? "42" : args[0];
        Registry explicit = new Registry();
        explicit.register("refund", () -> "refunded:" + orderId);

        System.out.println("api names=" + explicit.names());
        System.out.println("api refund="
                + explicit.invoke("refund"));
    }
}
```

Save the file, compile, and run:

```bash
javac AnnotationOrApiDemo.java
java AnnotationOrApiDemo
```

Stdout output when **no command-line argument is passed**:

```text
annotation names=[audit, pay]
annotation pay=paid
api names=[refund]
api refund=refunded:42
```

**Output explanation:**

1. `@Action` has `RetentionPolicy.RUNTIME` and `ElementType.METHOD`, so the scanner can read the metadata on methods.
2. `registerAnnotated(new BillingActions())` finds the methods annotated with `@Action`, checks their signatures, and registers callbacks to invoke later.
3. `TreeMap` ensures the set of names is displayed in the order `audit, pay`, **independent of the return order of `getDeclaredMethods()`**.
4. `invoke("pay")` calls the corresponding handler. The annotation **does not invoke the method itself**; the code in `Registry` does that.
5. The API `register("refund", () -> "refunded:" + orderId)` accepts a closure with `orderId` computed at runtime.
6. If you run `java AnnotationOrApiDemo 99`, the last line becomes `api refund=refunded:99` without modifying or recompiling any annotation.

This example intentionally allows only **public, zero-argument methods returning `String`** in `BillingActions`. In a general-purpose framework, you also need to handle accessibility, proxies, inheritance, parameters, async, duplicate commands, and security. Do not skip method signature checking and assume that annotations make the code safe.

## 8. Decision Analysis from the Example

### Why Is `@Action` Reasonable?

Suppose a module contains many handlers developed by different teams and the framework has a **standard scanner**. Annotating directly on each method helps:

- Metadata stays close to the described logic.
- The framework can automatically discover handlers without each module needing to edit a central registry file.
- Build/test tools can scan to detect duplicate names, missing signatures, or invalid metadata.
- When the command name is a stable property of the method, the `@Action("pay")` syntax is easy to read.

Costs incurred:

- Requires `registerAnnotated` code and a mechanism to define the scope of classes to be scanned.
- Incorrect `@Retention`, `@Target`, or classloader issues can prevent the framework from seeing the annotation.
- The scanner may encounter runtime errors if signature/visibility is only checked at startup.
- Requires documentation on when scanning occurs and how duplicate names are handled.

### Why Is `register(...)` Reasonable?

The refund example uses `orderId` from a command-line argument. This is runtime data and cannot be passed directly as an annotation element under Java rules.

`register("refund", callback)` allows:

- Using flexible closures/generic interfaces instead of a restricted set of annotation element types.
- Knowing exactly **when** the handler is added to the registry.
- Changing the callback based on environment, feature flags, or users.
- Testing registration by providing a mock `Supplier<String>`.

Costs incurred:

- Requires a bootstrap location that calls `register`.
- If there are many handlers and each must repeatedly declare its name, registration code can become verbose and easy to forget.
- When the API is called conditionally, it is hard to see the entire registry from method declarations alone; you need to inspect the bootstrap code.

Neither approach is strictly superior in all cases. **An annotation reduces declaration work at the call site by shifting responsibility to the scanner**, whereas **an explicit API keeps registration responsibility right inside the calling code**.

## 9. Combining Annotations with APIs: Clear Boundaries

A practical architecture often uses both:

1. Annotations describe the **static capabilities** of a class/method.
2. A processor or scanner reads the metadata and builds a **descriptor model**.
3. An explicit API receives the descriptor/runtime configuration to **activate, constrain, or register** behavior.
4. Operators can override certain parameters via a configuration object without modifying annotations.

Conceptual diagram:

```text
Source code
  @Action("pay") on method
           │
           ▼
Scanner or annotation processor
           │
           ▼
List of action descriptors
           │
Runtime config: enabled, timeout, region
           │
           ▼
Registry.register(descriptor, handler, options)
           │
           ▼
Dispatch when a request arrives
```

Here, annotations do not need to hold timeouts fetched from a database or dynamic feature flags. The explicit API does not have to repeat every label on the methods because the scanner has already built the descriptor list.

### Do Not Create Two Conflicting Sources of Truth

If the same command name appears in `@Action("pay")`, in a configuration file, and in a `register("checkout", ...)` call, you must clearly specify which source takes precedence or validate that they are consistent.

A maintainable design could be:

- The annotation defines the **default ID/supported capability**.
- The runtime registry decides **which handlers are enabled**.
- Dynamic options live in an `ActionOptions`/config object.
- On duplicate IDs, the system reports an error instead of silently overwriting.
- Tests verify that descriptors read from annotations and configuration are applied properly.

If responsibilities are not defined, combining them can create higher debugging overhead than either approach on its own.

## 10. Type Safety and When Errors Are Detected

Some people assume that annotations are always "type-safe", while APIs only report errors at runtime. That claim is inaccurate.

The Java compiler checks annotation elements:

```java
@interface Retry {
    int attempts();
}

@Retry(attempts = 3)
class Worker {}
```

However, the standard compiler **does not automatically know** that `attempts` must fall within the range 1–5. Without an annotation processor checking business constraints, `@Retry(attempts = 999)` is still type-valid.

With an API:

```java
config.setAttempts(3);
```

The compiler checks that the method exists and the parameter has the right type, while `setAttempts` can perform validation at runtime. A builder can constrain state and use enums/records/generics to express configuration more clearly.

| Error type | Annotation | Explicit API |
|---|---|---|
| Basic Java type mismatch | Usually caught by the compiler | Usually caught by the compiler |
| Wrong element/method name | Caught by the compiler | Caught by the compiler |
| Business rule violation (e.g., timeout limit) | Requires a processor or consumer to check | Requires validation code or stricter representation types |
| Annotation not scanned by the framework | May only be detected at build/startup/runtime | Direct calls do not depend on scanning, though registration can still be wrong |
| Environment-dependent parameters | Usually requires a framework-specific interpretation mechanism | Runtime values are passed directly |
| Complex state-transition logic | Metadata is usually insufficient to express it | Methods/interfaces/state machines are better suited |

**Conclusion:** Do not use annotations just for the reputation of "compile-time safety". If the goal is to catch business errors **during the build**, you need a processor or static analysis mechanism that actually runs. If the goal is runtime safety, validation is required on both paths.

## 11. Scope of Annotations: Value Types, `@Target`, `@Retention`

### 11.1. Element Type Limitations

Annotation elements only allow primitive types, `String`, valid `Class` types, enums, annotations, and one-dimensional arrays of them.

Allowed:

```java
enum Mode { SAFE, FAST }

@interface Policy {
    String name();
    Mode mode() default Mode.SAFE;
    Class<?> handler();
    String[] tags() default {};
}
```

Not allowed directly as elements:

```java
import java.util.List;

@interface BadPolicy {
    List<String> tags(); // Invalid: List is not an annotation element type.
    Runnable action();   // Invalid: interface Runnable is not in the allowed set.
    Object state();      // Invalid: Object is not in the allowed set.
}
```

These snippets illustrate type categories; `BadPolicy` intentionally does not compile. In an explicit API, `List<String>`, `Runnable`, or state objects are completely valid parameters.

### 11.2. Compile-Time Constants

Primitive/string elements of an annotation are supplied using appropriate constant expressions. For example:

```java
static final int DEFAULT_RETRIES = 3;

@Retry(attempts = DEFAULT_RETRIES)
class InvoiceTask {}
```

This snippet requires `DEFAULT_RETRIES` to be declared in a location accessible from `InvoiceTask` and the `Retry` annotation to already exist; this is a conceptual illustration.

Conversely, `@Retry(attempts = loadRetries())` is invalid when `loadRetries()` is a runtime method call.

### 11.3. Target and Lifecycle

`@Target` determines where an annotation can be placed, such as `TYPE`, `METHOD`, `FIELD`, `PARAMETER`, `PACKAGE`, or `TYPE_USE`. `@Retention` determines how long the information is retained:

- `SOURCE`: for source/compile-time processing; not retained in the class file.
- `CLASS`: metadata is present in the class file but not visible via standard reflection.
- `RUNTIME`: metadata is accessible via normal reflection.

If `@Retention` is not declared, Java defaults to `CLASS`. Set `RUNTIME` when the consumer actually needs runtime reflection, not as a generic way to "enable a feature".

### 11.4. Usability Across Multiple Environments

Annotations become part of the bytecode/artifact when the retention policy requires keeping them. Changing annotation values may require recompiling the annotated class. If metadata depends on tenants, regions, or credentials that change daily, separate those values into runtime configuration/APIs instead of hardcoding them in source.

## 12. Criteria on Discoverability and Debuggability

Annotations aid **declarative discovery**: to find out why a method is registered as a command, look for `@Action` right next to the method. However, to know **when it is activated**, you need to understand the scanner/framework.

Explicit APIs aid **tracing control flow**: an IDE can find call sites of `register`, and a debugger can stop at the registration call or inside the method body.

Ask yourself when choosing a design approach:

- Does a consumer already read this annotation type, or do we have to build the entire scanner ourselves?
- Which packages are within the scanning scope? Does it depend on classpath, modules, proxies, generated classes, or class loaders?
- Is a stable registration order required?
- What happens when two methods both have `@Action("pay")`?
- When an annotation is removed, will the build/tests detect that the handler is missing?
- Can a handler be activated and unregistered at runtime?
- Are there independent tests for the scanner, validation, and actual dispatch?

If the system is small with only a few fixed registrations, a list of API calls can be easier to control than a new scanner. If the scale is large and a standard framework supports annotations with a clear lifecycle, annotations can significantly reduce boilerplate.

**Do not equate fewer lines of code at the call site with lower overall system cost.** Account for infrastructure, tests, configuration errors, and operational paths as well.

## 13. Anti-Patterns to Avoid

### 13.1. "Magic Annotations": Attach It and It Runs on Its Own

Mistake:

```java
@Cacheable
String lookup(String key) {
    return databaseRead(key);
}
```

This snippet only has caching semantics if a framework/proxy/aspect/tool has been configured to understand `@Cacheable`; a custom-named annotation does not cause Java to create a cache automatically.

Better approach: use an annotation supported by a framework, or a direct cache API:

```java
String value = cache.getOrCompute(key, () -> databaseRead(key));
```

This illustrative snippet assumes the variables/methods are already available; the main point is that the caching behavior is invoked explicitly.

### 13.2. Pushing Runtime Data into Annotation Strings

For example, `@Schedule(expression = "\${ENV_RATE}")` does not automatically read environment variables under the Java language rules. A framework can interpret that string, but when building your own system, you are adding a *mini language*, parser, error handling, and escaping rules that must be maintained.

If it is inherently runtime configuration, consider accepting `ScheduleOptions` via an API or a configuration file with a schema.

### 13.3. One Annotation Trying to Cover an Entire Workflow

`@Payment(policy = "...", retry = "...", authorization = "...")` can gradually turn into a large configuration chain, making it hard to express state and handle exceptions.

If the logic requires branching, dynamic retry backoff, cancellation, or transaction orchestration, use an interface, strategy object, or explicit workflow engine. An annotation can hold a label selecting a strategy without needing to describe every step.

### 13.4. Stacking Too Many Annotations Without a Precedence Model

A method with multiple annotations from different frameworks easily causes conflicts: which annotation wins, what is the interceptor order, and how do they take effect on proxies and method overrides? Documentation and integration tests are needed, not just adding yet another annotation.

### 13.5. Using a Reflection Scanner When Only a Few Lines of Registration Are Needed

Reflection carries learning and operational costs. If there are only three handlers and plugin discovery is not needed, `registry.register(...)` can solve the problem faster and more clearly.

### 13.6. Replacing Public APIs with Annotations Just to "Look More Like a Framework"

Annotations lack the flexible generics of APIs, cannot supply objects/lambdas, and do not directly express the contract of a service interface. You should not abandon interfaces or methods well suited to runtime interaction just so users can write `@Something`.

### 13.7. Putting Secrets into Annotation Values

`RUNTIME` annotations are retained in the artifact and can be read via reflection; `CLASS` annotations can still be read from bytecode. **Do not store passwords, tokens, or private keys** in annotations just for code brevity.

## 14. Real-World Scenario Examples and Appropriate Choices

| Problem | Typically suitable choice | Reason |
|---|---|---|
| Marking a class as internal API for lint/CI checks | Annotation | Static metadata attached to the type |
| Generating a mapper from an interface at compile time | Annotation + processor | Automates stable declarations |
| Registering 3 fixed commands in a small application | Explicit API | Avoids building an unnecessary scanner |
| A web framework already supports `@GetMapping`/`@Route` | Annotation per framework contract | Declared close to the handler; handled by the framework |
| Timeout varying by tenant and user | Runtime API/config | Dynamic value |
| Payment workflow with conditional steps/rollback | API/objects/services | Complex behavioral flow |
| Plugin auto-discovering classes provided by third parties | Annotation or interface + discovery | Requires choosing a specific contract and scanning mechanism |
| Using runtime callbacks/lambdas | Explicit API | Annotations do not accept functional objects |
| Build tool checking package architecture | Package annotation + tool or explicit build rules | Package-level metadata; requires a consumer |
| A flag toggled on/off at runtime | API/config/feature flag service | Should not require recompilation to change |
| A test framework that already defines `@Test` | Framework's annotation | The framework knows how to find and run tests |
| Fixed metadata, while the handler can be dynamically enabled/disabled | Combination of annotation + API | Keeps declaration and activation responsibilities separate |

These are conditional recommendations: first consider the **actual framework in use**, the application lifecycle, and testability.

### The Plugin Problem: Annotation or Service Interface?

If a plugin needs to publish multiple implementations, `ServiceLoader` with an interface and provider configuration sometimes offers a clearer contract than building your own classpath scanner. Conversely, if the framework already has effective annotation discovery, metadata may be suitable.

Neither option automatically discovers plugins across all JARs merely because an annotation exists. The design must specify the **discovery mechanism**, class loader boundaries, and error handling.

## 15. Step-by-Step Decision Checklist

Before adding a new `@interface`:

1. **Describe the need in one sentence:** do you need to mark metadata or execute/configure behavior?
2. **List the concrete consumers:** compiler, processor, bytecode scanner, reflection framework, or API caller?
3. **Determine when values are known:** compile time, startup, per request, or per user?
4. **Check the data types:** strings/enums/class literals/constants, or objects/lambdas/lists/maps/runtime callbacks?
5. **Define the lifecycle contract:** who scans, when scanning runs, and whether disabling/re-registering is supported?
6. **Evaluate error handling:** will errors be caught in javac, at bootstrap, or during request execution?
7. **Evaluate testability:** can the annotation processing output or registry be tested directly?
8. **Consider API users:** do they prefer declarations on classes/methods or centralized startup config?
9. **Favor a single source of truth:** if combining both, specify which side owns metadata and which owns runtime overrides.
10. **Measure system-wide complexity:** do not count only the lines of annotations.
11. **Consider version upgrade compatibility:** what is the impact of changing the annotation schema, retention/target, or API signature?
12. **Write a small prototype:** choose the right framework/tool and test both the happy path and misconfiguration cases.

A short decision tree:

```text
Is the information stably tied to the declaration?
        │
       No ──────────────► Prefer explicit API/runtime config
        │ Yes
        ▼
Is there already a consumer that understands the annotation or is a processor genuinely needed?
        │
       No ──────────────► Consider explicit registration/interface
        │ Yes
        ▼
Do the values belong to valid annotation types and represent static metadata?
        │
       No ──────────────► Separate the dynamic part into API/config
        │ Yes
        ▼
An annotation is a reasonable choice
        │
        ▼
Design @Target, @Retention, validation,
discovery, errors, tests, and fallback clearly
```

## 16. Self-Check Exercises and Explanations

Consider the following requirements. Choose **annotation**, **explicit API**, or **combination**.

**Scenario A:** An internal library wants to mark classes that must not depend on the UI module. The CI tool can already read annotations in `.class` files.

**Scenario B:** The timeout duration depends on the region and is adjusted from an admin system at runtime.

**Scenario C:** A DI system already has annotations to declare components; the application needs to select a service implementation based on a feature flag.

**Scenario D:** A build tool generates adapters from labeled interfaces, without needing that metadata in the application after compilation.

**Scenario E:** A library needs to let users pass a `Predicate<Request>` to decide whether to accept a request.

**Scenario F:** Three fixed handlers need to be registered at application startup; the system has no scanner or processor yet.

**Scenario G:** You want the `@Retry(attempts = 3)` annotation to always have a value from 1 to 5, and errors to be reported immediately during the build.

**Scenario H:** You want to change the order of steps in a workflow according to the user's request on each incoming request.

**Suggested answers:**

- **A — Annotation:** stable metadata; choose a retention at least sufficient for the CI tool to read the bytecode (for example `CLASS`) and ensure the tool actually enforces the check.
- **B — Runtime API/config:** the value changes while the application is running and should not be hardcoded into an annotation element.
- **C — Combination:** use annotations to mark capabilities/services for DI; use an API/config/feature flag to control runtime selection according to the framework contract.
- **D — Annotation + processor:** the metadata is used at compile time, so `SOURCE` may suffice if a suitable source-processing processor handles it.
- **E — Explicit API:** annotation elements do not accept `Predicate<Request>`; use a functional interface in Java.
- **F — Explicit API:** calling a registry directly is simpler than building a custom scanner for just three handlers.
- **G — Annotation + validating annotation processor:** the Java compiler only checks the `int` type; a processor running during the build is needed to check the 1–5 range and report errors via `Messager`.
- **H — API/services/workflow object:** dynamic order and state are runtime behavior and are unsuitable for being fully described with constants in annotations.

### Two Additional Questions

1. Does `@Action("pay")` automatically create a route or command? **No.** A consumer/framework is needed.
2. Does changing an annotation from `SOURCE` to `RUNTIME` automatically make a framework recognize a new annotation? **No.** Retention only makes metadata observable via reflection; the framework still has to know how to read and handle it.

## 17. Summary and References

**Choose an annotation when:**

- Metadata is relatively static and genuinely tied to a Java declaration.
- There is a specific consumer that needs to read that metadata.
- You want a framework, compiler, or processor to discover/configure/verify a recurring rule.
- The value types and lifecycle fit within annotation constraints.

**Choose an explicit API when:**

- Behavior or configuration changes at runtime.
- You need to pass objects, generics, collections, lambdas/callbacks, or dynamic conditions.
- You need to represent multi-step workflows, state, and execution order.
- You want easy call-site tracing, error control, and direct unit testing.
- The scale of the problem does not justify the cost of a new scanner/processor.

**Combine them when:** annotations express static capabilities/metadata, while the API receives dynamic config and triggers behavior through a clear contract.

Java SE 17 references to consult when designing your own annotations:

- [Java Language Specification, Chapter 9 — Annotation Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html): syntax, valid element types, and value restrictions.
- [`Retention`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Retention.html) and [`Target`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Target.html): lifecycle and applicable targets.
- [`AnnotatedElement`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AnnotatedElement.html): looking up annotations at runtime.
- [`Processor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/Processor.html): compile-time annotation processing contract.

**Conclusion:** Annotations are a **metadata language attached to a program**; explicit APIs are an **interaction contract written in Java code**. Good decisions stem from execution needs and consumers, not from which syntax is shorter or looks more modern.
