# Refactoring `switch` on a Type Tag Using Pattern Matching (Java 21+)

## 1. The Problem: Type Tags Combined with Manual Casting

A **type tag** is a value indicating the kind of data, for example `"EMAIL"`, `"SMS"`, or `"PUSH"`. In legacy Java code, the typical handling pattern is a **`switch` on a string/enum tag**, followed by **casting** the payload to the corresponding class:

```java
// Illustrative snippet, placed inside a method with tag and payload variables.
switch (tag) {
    case "EMAIL":
        Email email = (Email) payload;
        System.out.println(email.to());
        break;
    case "SMS":
        Sms sms = (Sms) payload;
        System.out.println(sms.phone());
        break;
    default:
        System.out.println("unsupported");
}
```

The core drawback: **`tag` and the actual runtime type of `payload` are two separate sources of truth**. Java cannot automatically prove that `"EMAIL"` is always accompanied by an `Email`. If the tag is `"EMAIL"` but the actual payload is an `Sms`, `(Email) payload` throws a `ClassCastException`. If the payload is `null`, casting to a reference class can succeed and yield `null`, but calling an accessor on it will throw a `NullPointerException`.

The code above also requires repetitive casting branches. When adding a new type, the developer must manually update the enum/tag, the data class, the `switch` branch, and tests to ensure compatibility among them.

**Refactoring goal:** let the **runtime type of the object** serve as the basis for branching when processing internal data, instead of blindly trusting a parallel type tag. With Java 21+, you can use `switch` on objects with **type patterns** or **record patterns**, and commonly use a **sealed hierarchy** so the compiler checks that all variants are handled.

> Distinction: `switch(tag)` may still be needed at the boundary where JSON, message queues, or communication protocols are received. Replacing `switch` on a tag with pattern matching **does not mean removing tags from every protocol**. You should validate the tag and convert to internal types at the boundary, and then avoid depending on the tag in business logic.

## 2. Language Requirements and Refactoring Options

- **Java 16:** Type patterns in `instanceof` became a standard feature (JEP 394); they can be used to remove manual casts even without standard pattern matching for `switch`.
- **Java 21:** Pattern matching for `switch` and record patterns became standard (JEP 441, JEP 440). The examples in this article use `case Email(var to, var text) -> ...` and **JDK 21+**, without needing `--enable-preview`.
- **Sealed types:** standardized since Java 17 (JEP 409); use `sealed interface` and `permits` to represent an intentional, closed set of variants.

Two common levels of refactoring:

1. **Local refactoring:** continue receiving `Object`, and convert `switch(tag) + (TargetType) payload` into `instanceof TargetType t` checks. This eliminates unsafe casts, though it usually still needs `else`/`default` because the type hierarchy is not closed.
2. **Data model refactoring:** define a common `Notice` type with concrete subtypes such as `Email`, `Sms`, and `Push`; use `switch(notice)` with patterns. This removes the tag from the **internal model**, makes valid variants explicit, and lets the compiler check exhaustiveness of the `switch expression`.

You **cannot** simply keep `switch(tag)` with a `String` selector and write `case Email(var to, var text)` on that string. To match by subtype, **the selector must be an object capable of holding that subtype**, such as `Notice notice`.

## 3. Example Model: Receiving a Legacy Envelope and Converting to Internal Types

Suppose we have a legacy source:

```java
record LegacyEnvelope(String tag, Object payload) {}
```

`LegacyEnvelope.tag` is the type name provided by the sender; `payload` has static type `Object`. The internal data model after refactoring:

```java
sealed interface Notice permits Email, Sms, Push {}

record Email(String to, String text) implements Notice {}
record Sms(String phone, String text) implements Notice {}
record Push(String device, String text) implements Notice {}
```

Each record is an explicit variant: `Email` has `to`; `Sms` has `phone`; `Push` has `device`. A valid `Notice` in this model must be one of the three permitted subtypes. The sealed interface lets the compiler know which variants must be considered, while records make it straightforward to create, hold, and read components.

Important: **a type tag from an external source does not automatically turn into a `Notice`**. An adapter function is needed to validate the `tag/payload` pair before entering business logic.

## 4. Legacy Approach: Switching on Tag and Casting

```java
static String legacy(LegacyEnvelope input) {
    if (input == null || input.tag() == null) return "invalid";

    return switch (input.tag()) {
        case "EMAIL" -> {
            Email e = (Email) input.payload();
            yield "email:" + e.to() + ":" + e.text();
        }
        case "SMS" -> {
            Sms s = (Sms) input.payload();
            yield "sms:" + s.phone() + ":" + s.text();
        }
        case "PUSH" -> {
            Push p = (Push) input.payload();
            yield "push:" + p.device() + ":" + p.text();
        }
        default -> "invalid";
    };
}
```

This is still a **legacy design** because it branches on the tag and then casts the payload. So that both versions can run in the **same Java 21 program**, the method above is written using modern `switch expression` syntax (with `yield` in blocks); the `switch tag + cast` idea also exists in older Java code using `case: ... break;`.

The weakness does not lie in `->` or `yield`, but in **casting based on an unverified assertion from the tag**. For example, `new LegacyEnvelope("EMAIL", new Sms("0900", "Code"))` passes the tag branch and then fails when casting to `Email`.

## 5. Transition Step: Validating Tag and Payload at the Boundary

```java
static Notice adapt(LegacyEnvelope input) {
    if (input == null || input.tag() == null) return null;

    return switch (input.tag()) {
        case "EMAIL" -> input.payload() instanceof Email e ? e : null;
        case "SMS" -> input.payload() instanceof Sms s ? s : null;
        case "PUSH" -> input.payload() instanceof Push p ? p : null;
        default -> null;
    };
}
```

The adapter creates a `Notice` only when **both the tag and the actual runtime type are consistent**:

- `"EMAIL"` must be accompanied by an `Email`; `"SMS"` by an `Sms`; `"PUSH"` by a `Push`.
- `instanceof Email e` both checks the runtime type and binds the variable `e`; no `(Email) ...` cast is needed.
- `payload == null` or a tag-payload mismatch → `instanceof` returns `false` and the adapter returns `null`.
- Unknown tags are also mapped to `null`, following the simple policy of this example.

**Important limitation:** using `null` to represent "invalid" is an **illustrative convention** that discards the reason (unknown tag, mismatched payload, missing tag, etc.). In a real application, choose a result carrying error details (`Result`, a sealed outcome type, an exception with an error code, etc.) so you can log, audit, or return accurate HTTP status codes. The adapter still needs external data validation, even after checking the subtype.

Additionally, if the incoming data is raw JSON or a map that has not yet been deserialized into `Email`, `Sms`, or `Push` objects, the adapter will need to **parse and construct** the corresponding object. `instanceof` cannot check "is this an Email" while the payload is still a raw JSON string.

## 6. Modern Approach: Switching on the Actual Subtype with Record Patterns

After the adapter, business logic works with `Notice`:

```java
static String modern(Notice notice) {
    return switch (notice) {
        case null -> "invalid";
        case Email(var to, var text) -> "email:" + to + ":" + text;
        case Sms(var phone, var text) -> "sms:" + phone + ":" + text;
        case Push(var device, var text) -> "push:" + device + ":" + text;
    };
}
```

How to read `case Email(var to, var text)`:

1. Check whether the selector is a non-`null` `Email` object.
2. Deconstruct the two record components **in declaration order**, binding them to `to` and `text`.
3. Execute the expression after `->`, using its result as the value of the `switch expression`.

The three `Email`/`Sms`/`Push` branches cover all permitted subtypes of the sealed interface `Notice`. `case null` is included to handle the absence of an object. **No `default` is needed** in this model; if a new permitted subtype is added and a case is forgotten, the compiler can report that the `switch expression` is no longer exhaustive. Writing a catch-all `default` can hide that missing-branch warning.

**Do not confuse deconstruction with mapping:** Record patterns extract components and match structure; string concatenation to build the result is business logic. Deconstruction does not automatically convert to a new DTO, does not validate email addresses or phone numbers, and does not perform a *deep copy* of mutable references inside the record.

**`null` requires distinguishing two levels:** `case null` handles **the `notice` selector itself being `null`**. If an `Email` record has `to == null`, `case Email(var to, var text)` can still match and bind `to` to `null`. You must add a guard or separate validation if that field is required to be non-null.

## 7. Complete Compilable and Runnable Example

Create the file **`TypeTagRefactorDemo.java`**:

```java
public class TypeTagRefactorDemo {
    record LegacyEnvelope(String tag, Object payload) {}

    sealed interface Notice permits Email, Sms, Push {}
    record Email(String to, String text) implements Notice {}
    record Sms(String phone, String text) implements Notice {}
    record Push(String device, String text) implements Notice {}

    // Legacy approach: trust the tag and cast the payload.
    static String legacy(LegacyEnvelope input) {
        if (input == null || input.tag() == null) return "invalid";
        return switch (input.tag()) {
            case "EMAIL" -> {
                Email e = (Email) input.payload();
                yield "email:" + e.to() + ":" + e.text();
            }
            case "SMS" -> {
                Sms s = (Sms) input.payload();
                yield "sms:" + s.phone() + ":" + s.text();
            }
            case "PUSH" -> {
                Push p = (Push) input.payload();
                yield "push:" + p.device() + ":" + p.text();
            }
            default -> "invalid";
        };
    }

    // Conversion boundary: check both the tag and the payload type.
    static Notice adapt(LegacyEnvelope input) {
        if (input == null || input.tag() == null) return null;
        return switch (input.tag()) {
            case "EMAIL" -> input.payload() instanceof Email e ? e : null;
            case "SMS" -> input.payload() instanceof Sms s ? s : null;
            case "PUSH" -> input.payload() instanceof Push p ? p : null;
            default -> null;
        };
    }

    // Modern approach: switch directly on the actual subtype.
    static String modern(Notice notice) {
        return switch (notice) {
            case null -> "invalid";
            case Email(var to, var text) -> "email:" + to + ":" + text;
            case Sms(var phone, var text) -> "sms:" + phone + ":" + text;
            case Push(var device, var text) -> "push:" + device + ":" + text;
        };
    }

    static void verify(String label, LegacyEnvelope input) {
        String oldValue = legacy(input);
        String newValue = modern(adapt(input));
        if (!oldValue.equals(newValue)) {
            throw new AssertionError(
                    label + ": " + oldValue + " != " + newValue);
        }
        System.out.println(label + " -> " + newValue);
    }

    public static void main(String[] args) {
        verify("email", new LegacyEnvelope("EMAIL",
                new Email("a@example.com", "Hello")));
        verify("sms", new LegacyEnvelope("SMS",
                new Sms("0900", "Code")));
        verify("push", new LegacyEnvelope("PUSH",
                new Push("device-1", "Alert")));

        System.out.println("null -> " + modern(adapt(null)));
        System.out.println("unknown-tag -> " + modern(adapt(
                new LegacyEnvelope("FAX", new Email("a@example.com", "Hi")))));

        LegacyEnvelope mismatch = new LegacyEnvelope("EMAIL",
                new Sms("0900", "Code"));
        System.out.println("tag-mismatch -> " + modern(adapt(mismatch)));

        try {
            legacy(mismatch);
        } catch (ClassCastException ex) {
            System.out.println("legacy mismatch -> ClassCastException");
        }
    }
}
```

Command to compile and run with JDK 21 or later:

```bash
javac --release 21 TypeTagRefactorDemo.java
java TypeTagRefactorDemo
```

**Exact stdout:**

```text
email -> email:a@example.com:Hello
sms -> sms:0900:Code
push -> push:device-1:Alert
null -> invalid
unknown-tag -> invalid
tag-mismatch -> invalid
legacy mismatch -> ClassCastException
```

The program was run and its output verified on JDK 24 using syntax available since Java 21. `verify` checks that the **three valid cases** produce identical old/new results; if they differ, the program throws an `AssertionError`. The subsequent lines intentionally test abnormal scenarios.

### Test Case Analysis

| Input | `legacy` | `adapt` + `modern` | Conclusion |
| --- | --- | --- | --- |
| `"EMAIL"` + `Email` | Returns email string | Returns same email string | Behavior preserved |
| `"SMS"` + `Sms` | Returns SMS string | Returns same SMS string | Behavior preserved |
| `"PUSH"` + `Push` | Returns push string | Returns same push string | Behavior preserved |
| `null` envelope | `"invalid"` due to guard | `adapt` returns null, `case null` returns `"invalid"` | Behavior preserved in example |
| `"FAX"` (unknown tag) | `default` returns `"invalid"` | Adapter returns null, then `"invalid"` | Behavior preserved in example |
| `"EMAIL"` + `Sms` (mismatch) | Throws `ClassCastException` | Adapter rejects it, returns `"invalid"` | **Intentional change**; must be approved during migration |

Another edge case worth checking in real projects: tag `"EMAIL"` with `payload == null`. Casting `null` to a reference type does not throw on its own, but `e.to()` will throw `NullPointerException` in legacy code; the new adapter returns `null` and handles it under the `"invalid"` policy. When strict backward compatibility is required, you must **explicitly decide** whether to keep throwing an exception, switch to a business error, or return a result, and add corresponding tests.

## 8. Comparing the Two Designs and Trade-Offs

| Criterion | Switch on type tag + cast | Switch on subtype/pattern |
| --- | --- | --- |
| Selector | String/enum tag | Typed object, such as `Notice` |
| Data model | Tag and payload can be inconsistent | Subtype defines the internal variant |
| Casting | Usually requires casting in every case | Type/record pattern checks before binding variables |
| Tag/payload mismatch | Can throw `ClassCastException`, `NullPointerException` | Adapter can detect early; business `switch` handles normalized data |
| Compiler missing-case check | With `String tag`, all values are not statically known | With a sealed hierarchy and switch expression, exhaustiveness can be checked |
| Adding a new subtype | Manually synchronize tag, cast, case, and payload creation sites | Update hierarchy and cases; compiler helps find missing coverage |
| JSON/protocol input | Convenient for reading raw tags | Still needs a parser/adapter to recognize subtypes |
| Business guards | Usually `if` statements inside cases | Supports `when` for guarded patterns or checks inside blocks |
| Record components | Call accessors after casting | Record pattern extracts components directly |
| Performance | Depends on actual switch/cast/logic | No guarantee of always being faster; benchmark if critical |
| Version compatibility | Can be written on older Java versions | Pattern switch/record patterns in this example require Java 21+ |

### When Should You Not Switch Immediately?

- Input is still raw protocol data; there is no stable internal model yet.
- Other systems consume the type tag as part of a public schema; changing the schema could break compatibility.
- The project must still compile on Java 8/11/17 and cannot upgrade the toolchain to 21.
- The domain has types extensible by external plugins, which does not fit a closed `sealed` hierarchy. You can still use `instanceof` and a `default` branch on an open hierarchy, or polymorphism, depending on your needs.
- Logic depends on type-specific rules that belong in polymorphic methods on the subtypes rather than a single oversized centralized `switch`.

The goal is to clarify responsibilities and strengthen type checking, **not to force every `switch` to become pattern matching**.

## 9. How to Refactor Safely Step by Step

1. **Inventory type tags and usages:** identify valid tag values, all corresponding payload types, default branches, null handling, behavior on invalid tag/payload, and side effects.
2. **Pin existing behavior with tests:** at minimum cover each valid tag, unknown tag, missing tag, null envelope, null payload, and inconsistent tag/payload. Document which cases must be **preserved** and which are **intentionally changed**.
3. **Define a typed internal model:** create interfaces/classes representing the variants; consider `sealed interface` and `record` when arbitrary extensibility is not needed. Do not remove the type tag at the boundary when external contracts still require it.
4. **Write an adapter at the boundary:** validate the `tag` and data; have the parser or deserializer convert incoming values into internal subtypes. Keep responsibility here for clear error reporting, logging, and guarding against untrusted data.
5. **Migrate business logic:** replace `switch(tag)` in the core with `switch(typedValue)` using type/record patterns; remove casts in branches where types are already guaranteed.
6. **Check exhaustiveness and pattern ordering:** with a sealed hierarchy, prefer exhaustive switch expressions and avoid unnecessary `default` branches. If using guarded cases, place more specific cases before broader ones so cases are not *dominated*.
7. **Run comparison tests and roll out:** verify that valid results remain unchanged, error scenarios follow the agreed policy, and wire/output formats do not change unexpectedly. With live traffic, monitor parse/mismatch errors in the adapter.

**Migration tip:** If you cannot change the data model right away, a simple intermediate step is:

```java
// Illustrative snippet placed inside a method receiving an Object payload.
if (payload instanceof Email email) {
    System.out.println(email.to());
} else if (payload instanceof Sms sms) {
    System.out.println(sms.phone());
} else if (payload instanceof Push push) {
    System.out.println(push.device());
} else {
    System.out.println("unsupported");
}
```

This already eliminates tag-based casts and works on Java 16+. However, it dispatches based on the **actual runtime type**, which changes how mismatched-tag cases are handled. Test thoroughly and only use this when that is the desired contract. This snippet is not standalone; the types must be defined where it is used.

## 10. Guarded Patterns and Variable Scope

If you want to check additional business conditions, Java 21 supports `when` in pattern branches. Example inside a `switch expression` over a declared `Notice notice`:

```java
String result = switch (notice) {
    case null -> "invalid";
    case Email(var to, var text) when to == null || to.isBlank() ->
            "invalid-email";
    case Email(var to, var text) -> "email:" + to + ":" + text;
    case Sms(var phone, var text) -> "sms:" + phone + ":" + text;
    case Push(var device, var text) -> "push:" + device + ":" + text;
};
```

The `when` clause is evaluated **only after the record pattern has matched**. The variables `to` and `text` have *flow scoping* within the guard and the corresponding case branch. Place the guarded `Email` branch **before** the unguarded `Email` branch; if the general branch comes first, the specific branch is shadowed and the compiler will report a dominance error.

The expression `to == null || to.isBlank()` is safe because `||` short-circuits; when `to == null` is true, Java **does not call** `to.isBlank()`. This needs to be explicit because a record pattern does not automatically verify that reference components are non-null.

For non-record subtypes, use a **type pattern**: `case SomeClass s -> ...`. You cannot write `SomeClass(var x)` just to deconstruct a regular class; the `Type(...)` syntax is for records.

## 11. Common Pitfalls During Migration

| Pitfall | Consequence / How to Handle |
| --- | --- |
| Keeping `switch(tag)` but replacing labels with `case Email(...)` | The selector is still a `String`, so it cannot match a record. Change the selector to the subtype object or use an adapter. |
| Removing casts while still trusting an unvalidated tag | Tag and payload can be inconsistent; logic remains broken. Validate the tag-payload pair at the boundary. |
| Adding an arbitrary `default -> "unknown"` in a sealed switch | Can hide warnings about missing new subtypes. Only add `default` when it is genuinely part of the contract. |
| Believing `case null` also checks null components | `case null` only handles the selector; validate fields bound with `var` separately. |
| Writing `Email(var text, var to)` when both components are `String` | Compiles cleanly but swaps their meaning by component position. Always check the record declaration. |
| Placing `case Notice n` before `case Email(...)` | A broader case can dominate a more specific case. Place specific cases first. |
| Changing `ClassCastException` to `"invalid"` silently | Changes behavior; requires tests, logging, and API contract alignment. |
| Assuming `record` provides deep immutability | Record components are `final`, but components can still reference mutable data; no automatic deep copy is performed. |
| Treating external type tags as trusted data | Must parse, validate, handle nulls, and guard against malformed structures at the data boundary. |

## 12. Practice Exercise

Given the legacy model:

```java
record OldCommand(String type, Object payload) {}
record Create(long id) {}
record Delete(long id) {}
```

A legacy function uses `switch(command.type())`; the `"CREATE"` branch casts `payload` to `Create`, and the `"DELETE"` branch casts `payload` to `Delete`. Tasks:

1. Define `sealed interface Command permits CreateCommand, DeleteCommand` and the two corresponding records; do not include a tag inside the new model.
2. Write an adapter from `OldCommand` to `Command`, using `instanceof` to check the actual payload (or converting from external DTOs to the new records).
3. Use `switch (command)` with record patterns to return `"create:<id>"` or `"delete:<id>"`.
4. Write tests for tag `"CREATE"` + payload `Delete`, null input, and unsupported tags. Explicitly decide whether the adapter should return an error result or throw an exception.
5. Try adding an `UpdateCommand` subtype to `permits` without adding a case for it; observe the compiler feedback on the exhaustive `switch expression`.

**Solution hint:** use internal types such as `record CreateCommand(long id) implements Command {}`; branch `case CreateCommand(var id) -> "create:" + id;`. Keep reading the type tag and checking the payload inside the adapter. Do not convert an `OldCommand` directly into a subtype based solely on the `"CREATE"` string without validating the data.

## 13. Summary and References

**Principle:** Do not use a `type` string to justify unchecked casts in business logic. Keep the tag at the boundary when needed, validate and normalize the data, and then use type/record patterns on internal types. A sealed hierarchy + exhaustive switch makes the model clearer and helps catch missing branches as the system evolves. Verify equivalence with tests, especially for legacy cases that previously threw exceptions.

Official references:
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
