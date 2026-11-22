# Do Not Use Reflection Just to Avoid Designing Clear APIs

## 1. The Real Problem: Being Able to Invoke Dynamically Does Not Mean You Should

In Java, Reflection lets a program inspect information about classes, constructors, fields, and methods and perform certain operations at runtime. For example:

```java
Method method = target.getClass().getMethod(
        methodName, String.class, String.class);
method.invoke(target, recipient, message);
```

This snippet is an **illustrative fragment**, assuming `target`, `methodName`, `recipient`, `message`, and `import java.lang.reflect.Method;` are already present; the caller must handle Reflection exceptions. It can be useful when the method is genuinely determined only at runtime. However, if the system already knows two business operations `sendEmail(...)` and `sendPush(...)`, accepting a method name string to pick one of the two is usually a sign of **not having defined a clear API contract**.

Reflection is a **technical mechanism for operating on members described by metadata**. It does not replace design decisions:

- Which actions is the caller permitted to perform?
- What parameters does each action accept, what results does it return, and what errors does it throw?
- Which component is responsible for validating data and business rules?
- How is an implementation selected, at compile time or at runtime?
- When a method is renamed or a signature changes, who needs to know and how is the system checked?

If the answer is "concatenate a method name string and try invoking it", that contract information is being pushed from source code and the compiler out to runtime.

**Principle:** When operation kinds and target objects are known during development, prefer APIs with explicit names, data types, and responsibilities. Use Reflection when the genuine need is dynamic member discovery/wiring and the boundaries of that dynamism are clearly defined.

## 2. Why Can Reflection Make APIs Harder to Understand?

### a) Loss of Type Checking at Call Sites

Example of a direct call:

```java
notificationService.send(Channel.EMAIL, "lan@example.com", "Hello");
```

The compiler knows the method name `send`, the `Channel` type, two `String` parameters, and the return type. If a signature changes or the wrong type is passed, many errors appear immediately at compile time.

With a system that assembles calls dynamically:

```java
dispatcher.invoke("sendEmail", "lan@example.com", "Hello");
```

The compiler sees only `invoke(String, Object...)` or a similar generic signature, without automatically verifying that the `sendEmail` operation exists on the real target. Name and overload mistakes may surface only when that code path actually runs.

**Note:** Reflection APIs still perform runtime checks; it is not "no type checking at all". The difference is that most name/signature mistakes are caught **later** and become the responsibility of the dispatcher/framework author.

### b) Contracts Replaced by Strings and Implicit Conventions

A string such as `"sendEmail"` does not self-document its parameters, return type, invocation permissions, validation, or business semantics. If the application resolves method names from client requests, there is also a risk of exposing a broader set of callable actions than intended.

A good API expresses choices in data types, such as `enum Channel { EMAIL, PUSH }`, and centralizes dispatch inside a service with clear responsibility.

### c) Harder Maintenance During Refactoring

IDEs and compilers can assist with renaming methods directly, finding callers, or checking signature changes. Method names inside runtime strings may not be updated or checked to the same degree. Unit tests cover only the branches actually executed; missed reflective branches still carry failure risks.

### d) Wrong Member Kinds, Permissions, and Class Loaders

APIs such as `getMethod` and `getDeclaredMethod` are not identical. `getMethod` looks up public methods according to its rules; `getDeclaredMethod` finds methods declared directly in the class, including non-public ones, yet **finding** does not guarantee **invoking**. Overloads require exact parameter type lists; primitive `int.class` differs from `Integer.class`. Java modules, visibility, receivers, and class loaders add further access conditions.

Choosing Reflection just to call two already known operations saddles the application with these extra diagnostic costs for no commensurate benefit.

### e) Harder Separation of Exceptions and Business Errors

`Method.invoke(...)` can throw `NoSuchMethodException` at lookup time (via `getMethod`), `IllegalAccessException`, `IllegalArgumentException`, or `InvocationTargetException` upon invocation. If the target method throws an exception, `InvocationTargetException` wraps the original error and `getCause()` must be inspected. Explicit typed APIs usually express business errors closer to where they occur and keep stack traces simpler.

Do not rush to lump every case into `catch (Exception) { return null; }`: doing so hides misconfigurations, programming bugs, and domain errors.

## 3. Counterexample: A Dispatcher Calling Methods by Name

Suppose a notification system has two fixed channels. An error-prone design passes the method name to a helper using Reflection:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

class StringMethodDispatcher {
    static void dispatch(
            Object target,
            String methodName,
            String recipient,
            String message)
            throws NoSuchMethodException,
                   IllegalAccessException,
                   InvocationTargetException {
        Method method = target.getClass().getMethod(
                methodName, String.class, String.class);
        method.invoke(target, recipient, message);
    }
}
```

This is a **compilable class as a library component**, without a `main` method, so it is not a standalone runnable program. To succeed, the target class must provide a matching public method and runtime access conditions must allow invocation.

A call like this often appears in the application:

```java
StringMethodDispatcher.dispatch(
        someService, "sendEmail", "lan@example.com", "Hello");
```

The call is illustrative inside a method that already has `someService`. Neither the string `"sendEmail"` nor the `Object` type lets the compiler constrain the specific notification API. Renaming the target method while forgetting the string causes `NoSuchMethodException` at runtime.

Questions to ask before building a dispatcher:

1. Does the set of actions genuinely vary at runtime, or are there only two or three known branches?
2. Why is the caller given authority to pick a **Java member name**, rather than selecting a published business action?
3. If a new action is added, can a controlled interface/enum/registry be updated instead?
4. When an action is invalid, do you want failure at compile time, validation time, or not until Reflection lookup?
5. Do you need to separate Java member accessibility from client business authorization?

In this case, preferring an explicit typed API makes verification much easier.

## 4. Redesign: One Contract, Multiple Implementations

Suppose Email and Push both carry out the same business operation: "send a notification". We can represent that with `interface Sender`, use `enum Channel` as the public choice set, and use `NotificationService` to coordinate.

| Component | Responsibility | Design benefit |
| --- | --- | --- |
| `Sender` | Declares `send(recipient, body)` | Clear shared signature and meaning |
| `EmailSender` / `PushSender` | Implements behavior per channel | Independently replaceable/mockable/testable |
| `Channel` | Defines valid choices | Callers do not know internal method names |
| `NotificationService` | Selects sender and calls interface | Dispatch and unsupported errors controlled in one place |
| `Map<Channel, Sender>` | Registry of selected implementations | Extend specific branches without building a Reflection dispatcher |

The key point here is **polymorphism**: once a `Sender` is selected, code calls `sender.send(...)` directly against the contract. Switching from `EmailSender` to `PushSender` swaps implementations instead of turning method names into strings.

### Runnable Java 17+ Example

Save file **`ClearApiDemo.java`**:

```java
import java.util.Map;

public class ClearApiDemo {
    enum Channel { EMAIL, PUSH }

    interface Sender {
        void send(String recipient, String body);
    }

    static final class EmailSender implements Sender {
        @Override
        public void send(String recipient, String body) {
            System.out.println("EMAIL|" + recipient + "|" + body);
        }
    }

    static final class PushSender implements Sender {
        @Override
        public void send(String recipient, String body) {
            System.out.println("PUSH|" + recipient + "|" + body);
        }
    }

    static final class NotificationService {
        private final Map<Channel, Sender> senders;

        NotificationService(Map<Channel, Sender> senders) {
            this.senders = Map.copyOf(senders);
        }

        void send(Channel channel, String recipient, String body) {
            Sender sender = senders.get(channel);
            if (sender == null) {
                throw new IllegalArgumentException(
                        "Unsupported channel: " + channel);
            }
            sender.send(recipient, body);
        }
    }

    public static void main(String[] args) {
        NotificationService service = new NotificationService(Map.of(
                Channel.EMAIL, new EmailSender(),
                Channel.PUSH, new PushSender()
        ));

        service.send(Channel.EMAIL, "lan@example.com", "Hello");
        service.send(Channel.PUSH, "device-42", "Update");
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ClearApiDemo.java
java ClearApiDemo
```

Exact output:

```text
EMAIL|lan@example.com|Hello
PUSH|device-42|Update
```

Explanation:

1. Callers know only the `send(Channel, String, String)` operation, without needing to know internal method names or implementation class structures.
2. `Map.of(...)` sets up the two-channel registry. `Map.copyOf(...)` creates a map unmodifiable via the service; that **does not** make the senders themselves immutable or thread-safe.
3. `NotificationService.send(...)` picks the implementation by `Channel` and calls `Sender.send(...)` with an explicit signature. There is no `Class.getMethod` or `Method.invoke`.
4. If an SMS channel is added later, you can add `Channel.SMS`, implement `SmsSender implements Sender`, and register it. The compiler verifies that `SmsSender` implements every interface method.
5. A `Map` missing a channel is handled in the service with `IllegalArgumentException`. A real design can add recipient/body validation, auditing, retries, or domain errors as needed at clear boundaries.

For very small applications with a few stable branches, `switch` on an enum is also a valid choice. Do not erect many classes or registries just to avoid a simple `switch` expression. The goal is an API at the **right level of abstraction**, not adding abstractions for decoration.

## 5. Choosing Alternatives According to the API Contract

The starting point is **which data and operations should be published to callers**, not trying to eliminate every line of Reflection. In the notification example, the caller knows the `send` action and `Channel` type; choosing `EmailSender` or `PushSender` belongs to `NotificationService`. When requirements differ, choices differ too:

| Real need | Appropriate mechanism | Preserved contract |
| --- | --- | --- |
| Multiple implementations of the same business operation | Interface and polymorphism; Strategy if selected by context | `Sender.send(String, String)` is compiler-checked |
| One behavior accepting a few compile-time-known data shapes | Overloads, generics, or distinctly named methods | Callers are signature-checked; avoids meaningless `Object...` |
| Selecting and creating an implementation from controlled config | Factory, DI, or `switch` with a small registry | Caller receives type `Sender`, without knowing internal constructors |
| Adding providers with the same contract after packaging | Registry/plugin mechanism, optionally using `ServiceLoader<Sender>` | Plugins must still satisfy the interface and registration policy |
| Exposing data across module/service boundaries | DTOs, `record`s, getters, or explicit mappers | Exposes only contract fields without opening private state |

For example, `void write(String text)` and `void write(byte[] bytes)` can be two valid overloads; if each branch represents a completely different business behavior, use more specific names instead of forcing everything into `execute(Object)`. For data exchange, `record UserSummary(String displayName, int points) {}` expresses a schema more clearly than reflectively exposing every private field of a domain object.

A string-keyed registry still needs key validation, authorization, and duplicate-registration checks. `ServiceLoader` finds only **declared providers** visible on the classpath/module path; it does not scan all classes automatically. Registries/factories must also avoid turning every implementation into a "mega-interface" with dozens of unrelated operations. With two stable branches, `switch` can be clearer than a plugin framework.

## 6. When Does Reflection Still Have a Valid Justification?

Reflection fits when **type or member structure is genuinely known only at runtime**: serializers/ORMs reading metadata of arbitrary models; DI/frameworks analyzing constructors and annotations; test tools, debuggers, or inspectors examining unknown classes; plugin loaders inspecting new class metadata; compatibility adapters for third-party APIs differing across versions.

In these cases, **isolate the reflective step at an appropriate boundary**. For example, a plugin loader may use Reflection to verify a class and instantiate it, yet once it obtains a `Sender`, business logic calls `sender.send(...)` directly. Libraries operating on private members must constrain access rights and JPMS `opens`; dispatchers selecting actions from requests need allowlists, authorization, and schema validation. Frequently repeated Reflection operations can cache validated metadata, though an authorization decision must never be cached globally across all users.

If classes/methods are already known at compile time yet code still looks them up by string name, revisit the contract first. Conversely, if the problem truly is discovering fields/methods/annotations of unknown types, a single typed API cannot replace that introspection capability.

## 7. Using MethodHandle Does Not Automatically Fix a Vague API Design

`java.lang.invoke.MethodHandle` and `VarHandle` have strengths: explicitly typed operations, flexible runtime linking, support for certain optimizations, and memory access distinct from traditional Reflection.

However, if the application already has enough information to write:

```java
userService.activate(userId);
```

and instead builds the path:

```text
"activate" -> look up MethodHandle by name -> invoke -> handle all runtime type errors
```

switching tools from `Method.invoke` to `MethodHandle.invoke` does not solve the design-contract issue. The same business operation is still selected by string; missing-method errors still shift to runtime, and callers still struggle to see the valid action scope.

Choose an invocation mechanism for concrete reasons: framework/VM integration, truly dynamic call sites, or benchmark data. Do not choose Reflection/MethodHandle merely to avoid creating an interface, method overload, or necessary adapter.

## 8. Clear APIs Protect Module Boundaries and Access Rights

A well-designed module usually publishes what outsiders are **allowed to do**, rather than letting callers access every implementation detail. For instance, `AccountService.closeAccount(accountId)` expresses business preconditions; accessing a private `status` field via Reflection and setting it to `CLOSED` can bypass validation, auditing, events, or transactions.

An appropriate boundary:

```text
HTTP / UI / CLI
     |
     v
AccountService.closeAccount(accountId)
     |
     +-- check permissions and state
     +-- execute business logic / transaction
     +-- write audit / emit events if needed
     |
     v
Domain / Persistence
```

If callers use `Field.setAccessible(true)` to mutate state, they can break invariants. In the Java module system, `exports` exposes a package for public API access, whereas `opens` grants reflective access under the relevant conditions. Do not open an entire package just to touch one private field from a client, unless a framework genuinely needs it and the open scope has been evaluated.

An explicit API also provides a clear place to enforce authorization. Never feed user-submitted strings directly into Reflection method names on internal services: even if some methods invoke successfully, that is not a seriously designed business-action control mechanism.

## 9. Migrating from a Reflection Dispatcher to a Clear API

If existing code relies on `invoke(name, args)`, you can migrate incrementally while preserving current behavior:

1. **List all actual actions** from callers/configs and tests. Document business names, input/output types, errors, and permissions. Distinguish static actions from genuinely dynamic extension points.
2. **Group actions by contract.** If multiple implementations do the same job, create an interface. If only a few operations live on the same service, add dedicated public methods or appropriate overloads. Do not cram unrelated business operations into one generic method.
3. **Choose a typed dispatch point.** Callers pass an enum or validated value object; the service uses `switch`/factory/registry to pick the implementation.
4. **Move validation and errors to the right boundary.** Validate input data, unknown actions, unsupported versions, and permissions before calling the service. Keep business logic where it is easy to test.
5. **Add behavioral tests before swapping the call path.** Cover valid cases, invalid actions, missing data, implementation exceptions, and access permissions; compare outputs and side effects.
6. **Migrate callers gradually.** If legacy string APIs must remain for backward compatibility, write a small adapter parsing keys into enums and delegating to the typed service; do not leak Java method names into other layers.
7. **Delete the redundant dispatcher once no callers remain.** Never keep two parallel execution paths where one bypasses validation/auditing.

Example conversion adapter at the boundary, instead of invoking Java members by string:

```java
Channel parseChannel(String text) {
    return switch (text) {
        case "email" -> Channel.EMAIL;
        case "push" -> Channel.PUSH;
        default -> throw new IllegalArgumentException("Unknown channel: " + text);
    };
}
```

This is an **illustrative method** inside a class declaring `enum Channel`, not a standalone runnable file. With `text == null`, `switch` throws `NullPointerException` in this form; production APIs should define how null inputs are handled. The point of the snippet is: parse/validate external strings into domain types once; from that boundary inward, callers use explicit types.

## 10. Comparing the Two Choices on Key Points

| Criterion | Calling members by string via Reflection | Typed API + interface/factory |
| --- | --- | --- |
| Types and signatures | Looked up/checked mostly at runtime | Compiler checks most at call sites |
| Renaming methods | Strings can be missed during refactoring | Rename tools and compiler assist well |
| Access rights | Must resolve member/module access separately | Public contract clearly defines usage boundaries |
| Errors | Lookup/invoke errors, `InvocationTargetException` | Business errors expressed more directly |
| Testability | Must cover every string name/signature | Tested against contract and implementations |
| Dynamism | Flexible runtime member access | Runtime implementation selection via factory/DI/registry still possible |
| Performance | Lookup/invoke overhead; caching can reduce lookups | Often easier to optimize and measure, though benchmark per problem |
| Appropriate cases | Frameworks/tooling inspecting truly dynamic metadata | Business logic and integrations with known contracts |

This table is an architectural guide, **not** a promise that every non-Reflection path is faster than every Reflection path. JIT, call patterns, workloads, and caching design all matter. What counts is that system cost and clarity match the requirements.

## 11. Signs You Should Revisit the Design

If you encounter these patterns, check whether an explicit API fits better:

- A service accepts `String methodName`/`Object[] args` only to pick among a few fixed methods.
- Using `getDeclaredField` + `setAccessible(true)` to read/write state where the module ought to provide clear methods/DTOs.
- Using Reflection to instantiate classes known at compile time instead of constructors/factories/DI.
- Defining business actions by Java method names in databases/API requests and auto-granting invocation rights.
- After every method rename, having to search for hardcoded strings across the entire codebase.
- Most of the code handles `ReflectiveOperationException`, runtime casts, and signature checks rather than business logic.
- Adding a feature forces pasting Java name strings into configs, dispatchers, and UI even though the feature set is centrally managed.

Not every occurrence of a line of Reflection is a design flaw. Judge by **how much genuine dynamism exists** and whether a new abstraction reduces burden for both readers and maintainers.

## 12. Common Mistakes When Refactoring

**Replacing Reflection with a "mega-interface".** If every implementation must implement dozens of unrelated methods, the contract is too broad. Split interfaces by capability (interface segregation).

**Using an enum for unbounded plugins.** `enum` suits closed sets of choices. If third-party providers must be installed at runtime, use a typed registry/ServiceLoader/extension point. Do not force editing core code just to add each plugin when dynamic extensibility is truly required.

**Using `Object` in every API to avoid Reflection.** `Object execute(Object input)` is no better than `Method.invoke` if callers still have to guess types/casts by undocumented conventions. Prefer explicit request/response types; use generics or sealed hierarchies when suitable.

**Putting validation in the controller while skipping the service.** Switching from reflective calls to direct calls does not guarantee authorization/invariants. Services must protect business boundaries properly, even for non-HTTP callers.

**Failing to isolate legacy adapters.** If old names must still arrive over JSON/config, parse and validate them at the boundary. Keep one controlled adapter and let the core operate on typed contracts.

**Building complex registries when there is only one branch.** Sometimes the best API is just a clearly named method. Trade off abstraction for understandability; do not build a plugin framework to replace an ordinary call.

## 13. Self-Check and Exercises

1. A system has three fixed tax formulas selected by country code. Would you choose `switch`, `Strategy`, or Reflection? Explain based on rate of change and extensibility needs.
2. A plugin is loaded after application startup, yet it must conform to `ReportExporter.export(Report)`. Why does a registry/ServiceLoader with a typed contract still support dynamism?
3. Name three errors the compiler can catch when calling `service.send(Channel.EMAIL, String, String)`, which are hard to catch early with `invoke("sendEmail", Object...)`.
4. Why does `MethodHandle` not solve the problem if the method name still comes from user requests?
5. A serializer framework must access many fields of classes unknown at compile time. Is this a valid reason to use Reflection? How should access rights and data validation be constrained?
6. When migrating a system from `getDeclaredMethod` to an interface, what must be tested to preserve behavior, errors, permissions, and compatibility?
7. Starting from `ClearApiDemo`, add an SMS implementation. Would you add an enum value or create a plugin registry? What conditions would change that choice?

**Target outcome:** recognize the difference between **genuine dynamic binding needs** and using Reflection to dodge contract design; know how to favor interfaces, overloads, factories, DTOs, registries, or ServiceLoader appropriately; and keep Reflection inside components that truly need runtime metadata discovery, with clear access and error boundaries.