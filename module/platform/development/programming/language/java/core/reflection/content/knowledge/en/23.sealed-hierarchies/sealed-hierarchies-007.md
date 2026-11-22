# Limits of Using the permits List to Decide All Object Creation

## 1. Permits Answers Type Relationships, Not Object Creation Recipes

A sealed type declares which classes or interfaces are permitted as direct subtypes. Reflection can read those branches with:

~~~java
Class<?>[] direct = root.getPermittedSubclasses();
~~~

This information is very useful when drawing hierarchy diagrams, exploring a domain model, or checking relationships between types.

However, that list alone cannot fully answer:

- Which branch should be chosen for a given input?
- Is that branch a concrete class that can be instantiated?
- Is a constructor, factory, builder, or an existing object needed?
- Where do initialization arguments come from and what validation must they pass?
- Are the necessary access rights and dependencies available?
- What implementations exist on a `non-sealed` branch beyond the direct list?

**Being permitted as a subtype** is not the same as **being selected for this data**, nor is it the same as **being able to call a no-arg constructor to create one immediately**.

A clean design separates three concerns:

~~~text
Inspect hierarchy
    -> understand type relationships

Select variant
    -> determine the type or meaning required from data/context

Create or obtain object
    -> execute the strategy suited to the selected variant
~~~

Do not collapse all three concerns into a single loop over the permitted array.

## 2. What Exactly Does the API Provide?

`Class.getPermittedSubclasses()` returns the **direct** subclasses or subinterfaces permitted by a sealed type that the API obtains.

Important properties of the result:

- Only `Class<?>` objects, not instances.
- May include interfaces or abstract classes.
- Does not automatically expand into all indirect descendants.
- Makes no guarantee about element order.
- For unsealed types, the result is `null`.
- If a type recorded in metadata cannot have a suitable `Class` object obtained, it may be omitted per the API contract.

The [`Class.getPermittedSubclasses`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()) documentation describes this scope.

Therefore, the permitted list is not:

~~~text
List of every concrete instantiable class
    +
Constructor to use
    +
Argument data
    +
Branch selection priority order
~~~

A sealed type may have multiple language-valid subtypes while the application only exposes certain variants in its protocol. The Java hierarchy and the application's variant catalog are related, yet are not automatically one and the same list.

## 3. Things That Cannot Be Inferred Solely from a Class in permits

| Branch kind or design | Why is the permits list not enough? |
| --- | --- |
| Interface | Cannot instantiate directly via a constructor |
| Abstract class | May have constructors, yet cannot directly instantiate that class itself |
| `final` class | Only forbids subclassing; does not guarantee a no-arg constructor |
| Record | Needs a constructor matching its components, often with data validation |
| Factory-backed class | Creation API may be a static method; a private constructor is not a contract for callers |
| Enum | Must select an existing constant; `Constructor.newInstance()` does not allow creating additional enum instances |
| `non-sealed` branch | Further implementations remain open; that branch's own permitted list does not enumerate all descendants |
| Non-static member class | Calling a constructor via Reflection may require an enclosing instance |
| Type needing external dependencies | Metadata does not automatically provide needed configuration, services, resources, or context |

Even when a concrete class has an invocable constructor, choosing that constructor still depends on model semantics. A constructor that "does not throw on this attempt" is not automatically the right constructor for data mapping.

The [`Constructor.newInstance`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)) contract distinguishes conditions such as abstract classes, enums, accessibility, argument types, and exceptions inside constructor bodies.

## 4. Complete Program: One Hierarchy, Multiple Creation Mechanisms

The example below has five direct branches of `Message`:

- `Ping`: a single-component record.
- `Data`: a class with a private constructor and static factory.
- `Failure`: an abstract sealed class, despite having a public no-arg constructor.
- `Provider`: a `non-sealed` interface.
- `Mode`: an enum with pre-existing constants.

The two types `NotFound` and `PluginMessage` are indirect descendants of `Message`.

Save the code to `PermitsAndCreationDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

public class PermitsAndCreationDemo {
    public sealed interface Message
            permits Ping, Data, Failure, Provider, Mode {
        String describe();
    }

    public record Ping(String trace) implements Message {
        public Ping {
            trace = Objects.requireNonNull(trace, "trace").strip();
            if (trace.isEmpty()) {
                throw new IllegalArgumentException("Empty trace");
            }
        }

        @Override
        public String describe() {
            return "ping:" + trace;
        }
    }

    public static final class Data implements Message {
        private final String payload;

        private Data(String payload) {
            this.payload = payload;
        }

        public static Data of(String payload) {
            String normalized = Objects.requireNonNull(payload).strip();
            if (normalized.isEmpty()) {
                throw new IllegalArgumentException("Empty payload");
            }
            return new Data(normalized);
        }

        @Override
        public String describe() {
            return "data:" + payload;
        }
    }

    public static abstract sealed class Failure
            implements Message permits NotFound {
        public Failure() {
        }
    }

    public static final class NotFound extends Failure {
        private final String resource;

        public NotFound(String resource) {
            this.resource = Objects.requireNonNull(resource);
        }

        @Override
        public String describe() {
            return "missing:" + resource;
        }
    }

    public non-sealed interface Provider extends Message {
    }

    public static final class PluginMessage implements Provider {
        private final String payload;

        public PluginMessage(String payload) {
            this.payload = Objects.requireNonNull(payload);
        }

        @Override
        public String describe() {
            return "plugin:" + payload;
        }
    }

    public enum Mode implements Message {
        ON, OFF;

        @Override
        public String describe() {
            return "mode:" + name();
        }
    }

    static final Map<String, Function<Map<String, String>, Message>>
            FACTORIES = Map.of(
                    "ping", fields -> new Ping(required(fields, "trace")),
                    "data", fields -> Data.of(required(fields, "payload")),
                    "missing", fields ->
                            new NotFound(required(fields, "resource")),
                    "plugin", fields ->
                            new PluginMessage(required(fields, "payload")),
                    "mode", fields ->
                            Enum.valueOf(Mode.class, required(fields, "name")));

    static String required(Map<String, String> fields, String key) {
        String value = fields.get(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing field: " + key);
        }
        return value;
    }

    static Message create(String kind, Map<String, String> fields) {
        Objects.requireNonNull(kind, "kind");
        Objects.requireNonNull(fields, "fields");
        Function<Map<String, String>, Message> factory = FACTORIES.get(kind);
        if (factory == null) {
            throw new IllegalArgumentException("Unknown kind: " + kind);
        }
        return Objects.requireNonNull(
                factory.apply(Map.copyOf(fields)), "factory result");
    }

    static String kind(Class<?> type) {
        if (type.isInterface()) {
            return "interface";
        }
        if (type.isEnum()) {
            return "enum";
        }
        if (type.isRecord()) {
            return "record";
        }
        if (Modifier.isAbstract(type.getModifiers())) {
            return "abstract class";
        }
        return "class";
    }

    static boolean hasPublicNoArg(Class<?> type) {
        try {
            type.getConstructor();
            return true;
        } catch (NoSuchMethodException expected) {
            return false;
        }
    }

    static void showFailure(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected failure");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + ": " + expected.getMessage());
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Class<?>[] direct = Message.class.getPermittedSubclasses();
        Arrays.sort(direct, Comparator.comparing(Class::getSimpleName));
        for (Class<?> type : direct) {
            System.out.println(type.getSimpleName()
                    + " -> " + kind(type)
                    + "; publicNoArg=" + hasPublicNoArg(type));
        }

        System.out.println("Failure direct: "
                + Arrays.stream(Failure.class.getPermittedSubclasses())
                        .map(Class::getSimpleName)
                        .sorted()
                        .toList());
        System.out.println("Provider permitted is null: "
                + (Provider.class.getPermittedSubclasses() == null));
        System.out.println("PluginMessage is a Message: "
                + Message.class.isAssignableFrom(PluginMessage.class));
        System.out.println("PluginMessage directly permitted: "
                + Arrays.asList(direct).contains(PluginMessage.class));

        try {
            Failure.class.getConstructor().newInstance();
            throw new AssertionError("Abstract class instantiated");
        } catch (InstantiationException expected) {
            System.out.println("abstract newInstance: InstantiationException");
        }

        System.out.println("factory ping: "
                + create("ping", Map.of("trace", "T-1")).describe());
        System.out.println("factory data: "
                + create("data", Map.of("payload", " hello ")).describe());
        System.out.println("factory missing: "
                + create("missing", Map.of("resource", "/docs")).describe());
        System.out.println("factory plugin: "
                + create("plugin", Map.of("payload", "custom")).describe());
        Message mode = create("mode", Map.of("name", "ON"));
        System.out.println("factory mode: " + mode.describe());
        System.out.println("mode uses existing constant: " + (mode == Mode.ON));

        showFailure("unknown", () -> create("other", Map.of()));
        showFailure("missing input", () -> create("ping", Map.of()));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac --release 17 -encoding UTF-8 PermitsAndCreationDemo.java
java PermitsAndCreationDemo
~~~

Exact output:

~~~text
Data -> class; publicNoArg=false
Failure -> abstract class; publicNoArg=true
Mode -> enum; publicNoArg=false
Ping -> record; publicNoArg=false
Provider -> interface; publicNoArg=false
Failure direct: [NotFound]
Provider permitted is null: true
PluginMessage is a Message: true
PluginMessage directly permitted: false
abstract newInstance: InstantiationException
factory ping: ping:T-1
factory data: data:hello
factory missing: missing:/docs
factory plugin: plugin:custom
factory mode: mode:ON
mode uses existing constant: true
unknown: Unknown kind: other
missing input: Missing field: trace
~~~

When printing direct-branch info, the program explicitly sorts names. It does not use the permitted array order as an object-creation priority order.

## 5. Reading the Limits Through the Experiment

### 5.1. Having a public no-arg constructor is still not enough

The line:

~~~text
Failure -> abstract class; publicNoArg=true
~~~

shows that `Failure` has a public no-arg constructor.

However:

~~~java
Failure.class.getConstructor().newInstance();
~~~

throws `InstantiationException`, because `Failure` is an abstract class. The constructor exists to initialize the superclass portion in subclass objects; it does not make the abstract class itself concrete.

Therefore, checking "has a no-arg constructor" cannot replace checking the nature of the type and choosing a concrete class.

### 5.2. Records need component data

`Ping` has no no-arg constructor in the example. It needs `trace`.

The compact constructor also normalizes and validates the value:

~~~java
public Ping {
    trace = Objects.requireNonNull(trace, "trace").strip();
    if (trace.isEmpty()) {
        throw new IllegalArgumentException("Empty trace");
    }
}
~~~

This is an excerpt from the full program.

Permitted metadata indicates `Ping` is a valid direct branch. It does not specify where the `trace` string in a request comes from or the policy when the string is missing.

If a tool instantiates a record via Reflection, it must determine the canonical constructor from the components, prepare the right argument order and conversions, and preserve the constructor's validation logic. Record constructor rules are described in [JLS §8.10.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10.4).

### 5.3. A class can expose a factory instead of a constructor

`Data` has a private constructor and the factory `Data.of(...)`. The factory normalizes the payload with `strip()` and rejects empty payloads.

The permitted list does not mark `of` as the creation method to use. Nor can a factory be identified merely by finding the first static method returning a matching type: a class can have multiple static methods with different roles.

In the example, the `data` strategy explicitly registers calling `Data.of(...)`. The result:

~~~text
factory data: data:hello
~~~

shows that the string `" hello "` was processed through the factory.

Being able to find a private constructor via Reflection does not make that constructor the initialization contract a tool should pick. Accessibility and model API semantics must be considered separately.

### 5.4. Enums require selecting a constant, not creating a new one

`Mode` is a direct subtype of `Message`, yet not a class for creating new instances in the usual way.

The `mode` factory uses:

~~~java
Enum.valueOf(Mode.class, required(fields, "name"))
~~~

to select the constant with the matching declared name. The check line:

~~~text
mode uses existing constant: true
~~~

confirms the result is `Mode.ON` itself, not a new enum object.

The [`Enum.valueOf`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String)) documentation specifies looking up an existing constant by name. If no constant has that name, it is a lookup error; you should not use a Reflection constructor as a "fallback creation" branch.

### 5.5. Indirect branches still belong to the type family

`Message` directly permits `Provider`; `Provider` is `non-sealed`. `PluginMessage` implements `Provider`, so it is a valid `Message`.

The results:

~~~text
PluginMessage is a Message: true
PluginMessage directly permitted: false
~~~

do not contradict each other. The two checks ask about two different relationships:

- `Message.class.isAssignableFrom(PluginMessage.class)` checks whether an object of that type can be used as a `Message`.
- Checking membership in `Message`'s permitted list checks only the listed direct branches.

If a tool requires every instantiable type to appear **directly** in the root's permitted list, it will wrongly reject indirect descendants like `NotFound` or `PluginMessage`.

Conversely, merely having an assignable relationship does not mean the application wants to expose all such descendants to users. A variant registration policy must still exist.

## 6. Why Not Choose a Branch by Order or Data Shape?

An error-prone approach is iterating over the permitted list and trying to instantiate each in turn:

~~~java
// Illustrates an inadequate algorithm, not a complete factory.
for (Class<?> candidate : Message.class.getPermittedSubclasses()) {
    Object value = candidate.getDeclaredConstructor().newInstance();
}
~~~

The issues go beyond needing a `try/catch` block:

- The permitted array has no API-guaranteed priority order.
- Interfaces and abstract classes are not direct instantiation targets.
- Some classes lack a no-arg constructor.
- Enums are not created that way.
- Factory-backed classes have their own initialization rules.
- Speculatively running multiple constructors can cause side effects before reaching a final result.

Even relying on field names to guess can leave the data ambiguous. In the program, both the `data` and `plugin` variants accept a `payload` key, yet have different meanings and creation mechanisms.

There is not enough information to decide solely from:

~~~text
{payload: "..."}
~~~

If `Data` is chosen merely because its class name sorts before `PluginMessage`, the result is an accidental rule, not the meaning required by the data.

A protocol can use a **variant discriminator**, such as `kind = "data"` or `kind = "plugin"`. Another system might choose by context or explicit configuration. Whichever approach is chosen, it is part of the application contract and cannot be fully inferred from `permits`.

## 7. An Explicit Factory Catalog Supplies the Missing Part

`FACTORIES` in the program maps:

~~~text
variant label -> strategy to read input and return Message
~~~

| Label | Strategy |
| --- | --- |
| `ping` | Read `trace`, invoke record constructor |
| `data` | Read `payload`, invoke static factory |
| `missing` | Read `resource`, construct concrete class under abstract branch |
| `plugin` | Read `payload`, construct implementation under `non-sealed` branch |
| `mode` | Read `name`, return existing enum constant |

Each function is declared to return `Message`, so the wiring in the example is already checked by the compiler for type-family compatibility.

Benefits of this separation:

1. Labels have protocol meaning, independent of Java binary class names.
2. Each variant has one clear strategy.
3. Missing data is reported at the relevant factory.
4. Unregistered variants are rejected explicitly.
5. Indirect descendants can be supported when the application actively registers them.
6. A strategy can construct anew, call a factory, or return an existing object.

The example does not take an arbitrary class name from input, call `Class.forName`, and try every constructor. The catalog in code defines which variants the application supports.

In tools with dynamic registration, check the type relationship at registration time, for example with `root.isAssignableFrom(candidate)` or `candidate.asSubclass(root)`. A concrete creation strategy is still needed afterward; the type relationship does not replace that strategy.

## 8. Permits Still Has a Useful Role

Sealed metadata should not be discarded just because it does not solve all of object creation. It can assist with:

- Generating documentation for direct branches.
- Detecting a registered type with an unexpected hierarchy relationship.
- Organizing variant groups in selection interfaces.
- Checking coverage of a catalog against a defined policy.
- Detecting whether a branch is further `sealed`, `final`, or opened via `non-sealed`.

However, when stating "all variants are supported", the scope must be defined clearly:

- Direct branches only or deeper concrete classes?
- Is an abstract class counted as an instantiable variant?
- Should nested sealed branches be traversed further?
- For a `non-sealed` branch, is the catalog fixed by configuration or open to additional registrations?
- Is an enum counted as its enum type or by its constants?
- How is a class with multiple factories or configuration modes counted?

Even when every branch is closed and a finite hierarchy can be traversed completely, the class list still does not contain full argument data or factory-selection contracts.

In packaging or class-loader environments that do not supply every type recorded in metadata, a shorter Reflection array should also not be treated as proof that the remaining branches do not exist in the design. Runtime observations must be separated from the hierarchy contract and configuration expected by the application.

## 9. Designing an Object Creation Pipeline by Responsibility

A pipeline for a polymorphic data mapper or reader might look like:

~~~text
1. Receive root type and data
2. Read variant label or selection context
3. Look up registered strategy
4. Validate schema and convert data
5. Prepare dependencies or arguments
6. Invoke constructor/factory or retrieve existing object
7. Validate result and return as root type
~~~

Sealed metadata can be used when planning or checking relationships in the steps above. It does not perform the remaining steps on its own.

In the example, `required(...)` checks the required fields read by each factory. Policies such as rejecting extra fields, handling `null` values, converting strings to numbers, or validating nested structures should be added to the schema contract when the application needs them.

If invocation is performed via Reflection:

- Obtain the exact constructor or factory method signature.
- Respect class, package, and module access rules.
- Do not treat `setAccessible(true)` as a substitute for the entire object-creation design.
- Preserve the cause when a constructor or factory throws an error, instead of silently trying another branch.
- Do not expose a bogus valid object when data has not met the model's conditions.

Missing-data errors and variant-selection errors should be caught before running initialization code. Errors from executing initialization code can still happen; metadata does not prove that a constructor or factory will always succeed.

## 10. Self-Check

1. A class appears in `permitted` and has a public no-arg constructor. Is that enough to assert instantiation will succeed?
2. Why does `Failure` in the program have `publicNoArg=true` yet `newInstance()` fails?
3. Why is `Ping`, which has no no-arg constructor, still a valid variant?
4. If `Data` exposes `Data.of(...)`, does `permitted` automatically point to that method?
5. `PluginMessage` is not directly in `Message`'s `permitted` list. Why is it still a `Message`?
6. For enum `Mode`, does the `mode` strategy create a new object or select an existing constant?
7. If two variants both accept a `payload` key, can the right one be selected simply by sorting class names?
8. If all branches of the hierarchy are closed, can the argument schema and factory policy be omitted completely?
9. Why should you not catch all instantiation errors and automatically try the next branch?
10. Does passing an assignable check automatically mean the application must allow exposing that type over its protocol?

Answers:

1. Not yet. Type nature, accessibility, initialization conditions, and constructor behavior also matter.
2. It is an abstract class; having a constructor does not allow directly instantiating that class itself.
3. It is declared as a valid branch; instantiation needs the `trace` argument for the record constructor.
4. No. A factory must be identified via configuration, registration, or an explicit contract.
5. It implements `Provider`, which is a direct `non-sealed` branch of `Message`.
6. Selects an existing constant; the program confirms the result is `Mode.ON` itself.
7. No. A discriminator label or a meaningful selection rule is needed.
8. No. Closing a hierarchy does not supply full input data or creation semantics.
9. It can pick the wrong variant, hide data errors, and cause side effects from earlier attempts.
10. No. Type relationships and the catalog of application-supported variants are two separate decisions.
