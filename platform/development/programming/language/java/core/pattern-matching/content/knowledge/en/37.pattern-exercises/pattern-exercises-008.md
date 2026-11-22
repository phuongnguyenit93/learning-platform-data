# Refactoring a Legacy Module to Pattern Matching in Java 21

## 1. Capstone Practice Objectives

A legacy module often has chains of `if/else if` with `instanceof`, manual casts, deeply nested conditions, getters with side effects, and fallbacks for invalid data. Java 21 allows rewriting dispatch logic using **type patterns**, **record patterns**, **`when` guards**, and **switch expressions**. The goal is not merely to shorten the code, but to **preserve observable behavior while improving clarity and type safety**.

The exercise uses a message routing module with the following data types:

- `TextMessage`: holds text content, with a `readBody()` getter that counts the number of reads.
- `CountMessage`: holds an integer, with a branch for negative numbers.
- `PacketMessage`: has a header and payload, with each getter having a read counter.
- `Header`: an internal record consisting of `channel` and `priority`, with a high threshold = 10.
- `Heartbeat`: a signal-only message type.
- `ExplodingMessage`: intentionally throws an exception to test error preservation.
- `null` and out-of-module types: have explicit fallbacks.

We will compare `legacyRoute(Object)` with `modernRoute(Object)`, using 21 inputs and checking **return values, exceptions, and getter call counts**. In addition, there is a counterexample of a poorly written `when` guard that causes the getter to be called three times, even though the resulting string looks correct.

**Scope:** A "module" is a functional group within an application, not necessarily a Java Platform Module System/`module-info.java` module. The example is organized as a single Java file for easy execution, followed by an explanation of how to apply it to multi-class Maven/Gradle modules and CI.

**Version:** Pattern matching with `instanceof` has been standard since Java 16; record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have been standard since **Java 21**. `--enable-preview` is not required when compiling with `javac --release 21`.

### Expected Outcomes

After this lesson, you will know how to inventory the legacy contract; choose appropriate refactoring targets; preserve public POJO APIs when needed; write `switch` expressions with `when`, `case null`, and `default` correctly; test errors, branch ordering, side effects, and compatibility; and roll out incrementally with rollback support.

## 2. Before Refactoring: Inventorying Contracts and Risks

Do not start by running an automated "Convert to switch" action across the entire module. List the elements that callers actually observe:

| Element | Questions to Answer | Potential Consequences |
| --- | --- | --- |
| Public method signature | What types do methods accept/return? Are there checked exceptions? | Source/binary compatibility |
| Public DTO/POJO | Getters, setters, constructors, subclasses, JSON/JPA binding? | Switching to records may break the API |
| Branch order | When two conditions are both true, which branch is chosen? | Business logic results change |
| `null` selector | Return fallback, throw NPE, or ignore? | Different `switch` semantics |
| Nested `null` | Is the intermediate object null or is a component null? | Pattern does not match or guard fails |
| Unknown types | What does `else`/`default` return? Is there plugin extensibility? | Failures with subclasses/extensions |
| Exceptions | Type, timing, cause, message to preserve? | Callers and logging change behavior |
| Side effects | How many times do getters, audits, metrics, I/O, or mutations run? | Duplicate events or unexpected slowness |
| JDK/toolchain | What are the source/release and production runtime versions? | Build passes in IDE but fails on deploy |
| Tests/monitoring | Are there baselines, CI, integration tests, rollback? | Regressions go undetected |

A real-world module might look like:

```text
message-module/
  src/main/java/com/example/message/
    MessageRouter.java
    TextMessage.java
    CountMessage.java
    PacketMessage.java
    Heartbeat.java
  src/test/java/com/example/message/
    MessageRouterContractTest.java
    MessageRouterIntegrationTest.java
  pom.xml  or build.gradle(.kts)
```

This is only an illustrative layout; you do not need to create these directories to run the file in section 8. For projects with an existing architecture, keep the current conventions.

### 2.1. Do Not Change Public DTOs at the Same Time as Refactoring the Dispatcher

Pattern matching **does not require input classes to be records**. `case TextMessage message` matches a regular POJO class. In the example, `TextMessage`/`CountMessage`/`PacketMessage` remain final classes. Only `Header` is an internal carrier record for practicing record patterns.

If you publicly convert a mutable class to a record, you must also evaluate constructors, getters, setters, inheritance, reflection, framework mapping, serialized schema, identity, and thread-safety. That is a **model/API change**, not automatically considered a pure syntax refactor.

## 3. Recording a Baseline Before Modifying Code

For the sample module, the legacy contract is:

| Case | Expected Result | Accessor Read Count |
| --- | --- | --- |
| `TextMessage(" Java ")` | `text:Java` | 1 |
| `TextMessage(" \\t ")` | `text:<blank>` | 1 |
| `TextMessage(null)` | `text:<null>` | 1 |
| `CountMessage(-1)` | `count:negative` | 0 |
| `CountMessage(0)` | `count:0` | 0 |
| `PacketMessage(Header(" api ",10)," body ")` | `packet:high:api:body` | 2 |
| `PacketMessage(Header("evt",9),"hello")` | `packet:normal:evt:hello` | 2 |
| `PacketMessage(Header(null,10),"body")` | `packet:invalid-channel` | 2 |
| `PacketMessage(null,"body")` | `packet:missing-header` | 2 |
| `ExplodingMessage` | `IllegalStateException("corrupted payload")` | 1 |
| `Heartbeat` | `heartbeat` | 0 |
| Unknown type | `unsupported` | 0 |
| Selector `null` | `null-input` | 0 |

In a real program, add HTTP responses, audit records, transaction boundaries, or error codes if they belong to the module's contract. Do not rely on taking a single UI screenshot as a baseline.

**Important:** A behavior-preserving refactor needs to compare at least three aspects: *values*, *exceptions*, and *side effects*. You may also need to check the **order** of side effects, not just the count.

### 3.1. Locking Down Input Boundaries

In the example, the boundaries are: priority 9/10, count -1/0, null/blank/nonblank strings, null/empty payloads, and an unknown `Object`. Put these boundaries into tests before changing any code. For Unicode strings, `strip()` and `trim()` are not always equivalent; do not change whitespace handling methods without an explicit requirement.

## 4. Legacy Code: `instanceof` and Manual Casts

Here is the legacy-style dispatcher. The classes and helpers are fully defined in section 8:

```java
static String legacyRoute(Object input) {
    if (input == null) return "null-input";

    if (input instanceof TextMessage) {
        TextMessage message = (TextMessage) input;
        String body = message.readBody();
        return textLabel(body);
    }
    if (input instanceof CountMessage) {
        CountMessage count = (CountMessage) input;
        if (count.count() < 0) return "count:negative";
        return "count:" + count.count();
    }
    if (input instanceof PacketMessage) {
        PacketMessage message = (PacketMessage) input;
        Header header = message.header();
        String payload = message.payload();
        return legacyPacket(header, payload);
    }
    if (input instanceof Heartbeat) return "heartbeat";
    if (input instanceof ExplodingMessage) {
        ExplodingMessage message = (ExplodingMessage) input;
        return message.read();
    }
    return "unsupported";
}
```

Note the required properties that must be preserved:

- `null` is handled **before** type checks.
- `readBody()` runs exactly once for the Text branch.
- `header()` and `payload()` run exactly once per getter for Packet.
- For negative Count, the result differs from non-negative Count.
- The `ExplodingMessage` getter throws an error and that error propagates rather than being turned into a fallback.
- Inputs not matching any of the listed classes return `unsupported`.

If legacy code has a direct cast **not guarded** by `instanceof`, it may throw `ClassCastException` or `NullPointerException`. Replacing that cast with `instanceof ... ? value : fallback` changes behavior; separate approval is needed if you want to change the contract.

### 4.1. First Safe Step: Type Pattern `instanceof`

Before using the new switch, you can rewrite just the Text branch:

```java
if (input instanceof TextMessage message) {
    String body = message.readBody();
    return textLabel(body);
}
```

This removes the manual cast while keeping the `if` structure, ordering, and getter call count. Java 16+ already supports this. In projects still targeting Java 17, this can be a suitable small step without having to raise the source level to 21 yet.

## 5. Java 21 Version: Migrating Dispatch to Pattern Switch

Once the baseline is in place, the dispatcher can be written as:

```java
static String modernRoute(Object input) {
    return switch (input) {
        case null -> "null-input";
        case TextMessage message -> textLabel(message.readBody());
        case CountMessage count when count.count() < 0 ->
                "count:negative";
        case CountMessage count -> "count:" + count.count();
        case PacketMessage message ->
                patternPacket(message.header(), message.payload());
        case Heartbeat h -> "heartbeat";
        case ExplodingMessage message -> message.read();
        default -> "unsupported";
    };
}
```

**This is a switch expression**, because the entire switch produces a `String` to return. The `->` is the rule body form; the pattern sits in the `case Type variable` label.

Semantic mapping:

| Legacy | Java 21 | What Must Be Preserved |
| --- | --- | --- |
| `input == null` | `case null` | Same fallback |
| `instanceof TextMessage` + cast | `case TextMessage message` | Same getter/same output |
| `if (count.count() < 0)` | `when count.count() < 0` | Same priority for negative branch |
| `else/count >= 0` | `case CountMessage count` | Unguarded branch comes after |
| `PacketMessage` + nested ifs | `case PacketMessage message` + record pattern helper | Preserve read count/exceptions |
| `Heartbeat` | `case Heartbeat h` | Correct input type |
| `ExplodingMessage.read()` | `case ExplodingMessage message -> message.read()` | Exception still propagates |
| Final `else` | `default` | Unknown inputs remain supported |

If you omit `case null` thinking `default` handles null, an NPE can occur. If you place an unguarded `case CountMessage count` before the case with `when`, the compiler will report **dominance**. If using a common interface/superclass, place specific subtypes before supertypes.

### 5.1. Why Not Automatically Make Legacy Interfaces Sealed?

If the application allows external plugins to implement an interface or extend a public class, changing it to `sealed` can break extensibility. Exhaustiveness of a sealed hierarchy is very useful **when the set of subtypes is truly closed**, but it is not a mandatory requirement for using pattern matching. In the example, the selector is `Object` and `default` is used to keep the unknown type fallback.

## 6. Record Patterns Inside the Module: Refactoring Header

Suppose the header structure is an internal record:

```java
record Header(String channel, int priority) {}
```

Legacy handler:

```java
static String legacyPacket(Header header, String payload) {
    if (header == null) return "packet:missing-header";
    String channel = header.channel();
    int priority = header.priority();

    if (channel == null || channel.isBlank()) {
        return "packet:invalid-channel";
    }
    if (priority >= 10) {
        return "packet:high:" + channel.strip()
                + ":" + payloadLabel(payload);
    }
    return "packet:normal:" + channel.strip()
            + ":" + payloadLabel(payload);
}
```

New version using deconstruction + `when`:

```java
static String patternPacket(Header header, String payload) {
    return switch (header) {
        case Header(var channel, var priority)
                when channel == null || channel.isBlank() ->
                "packet:invalid-channel";
        case Header(var channel, var priority) when priority >= 10 ->
                "packet:high:" + channel.strip()
                        + ":" + payloadLabel(payload);
        case Header(var channel, var priority) ->
                "packet:normal:" + channel.strip()
                        + ":" + payloadLabel(payload);
        case null -> "packet:missing-header";
    };
}
```

**Key points:**

1. `Header(var channel, var priority)` checks that the record object is non-null, reads the components, and binds them to pattern variables.
2. The first guarded branch blocks null/blank channels **before** calling `strip()`.
3. The high branch uses `priority >= 10`: the exact threshold 10 counts as high.
4. The unguarded branch is the fallback for all remaining `Header` instances; it must come after the guarded branches.
5. `case null` handles a null header reference; no `default` is needed because the switch already covers both non-null and null `Header` values.

**Null at two different levels:** `header == null` does not match the record pattern `Header(...)`, whereas `new Header(null,10)` is a non-null `Header` where `var channel` can bind to null. Do not treat a record pattern as an automatic validator for each component.

In Java 21, unconditional nested type patterns for a component's type can have special **null-matching** rules, so changing `var channel` to `String channel` is not a reliable way to forbid a null channel. Check it explicitly in the guard.

### 6.1. Do Not Place the High Guard Before the Invalid Guard

If you write `case Header(var channel,var priority) when priority >= 10` first and the branch body calls `channel.strip()`, a `Header` with high priority but a null channel could throw an NPE instead of returning `packet:invalid-channel`. Case ordering is part of the contract, not a cosmetic detail.

## 7. Side Effects: A Correct Return Value Can Still Be a Broken Refactor

Some getters on legacy classes are not pure. For example:

```java
static final class TextMessage {
    private final String body;
    private int reads;

    TextMessage(String body) { this.body = body; }

    String readBody() {
        reads++;
        return body;
    }

    int reads() { return reads; }
}
```

In the program, both the legacy and modern versions call `readBody()` only once. The **intentionally wrong** refactor below calls it multiple times:

```java
static String naiveTextRoute(Object input) {
    return switch (input) {
        case TextMessage message
                when message.readBody() != null
                        && !message.readBody().isBlank() ->
                "text:" + message.readBody().strip();
        case TextMessage message -> "text:<blank>";
        default -> "unsupported";
    };
}
```

For body `" Java "`, the calls occur in this order:

1. `readBody() != null` — 1st read.
2. `!readBody().isBlank()` — 2nd read.
3. `readBody().strip()` — 3rd read.

The new code returns the right `text:Java` string, but **reads=3**, compared to the old code's **reads=1**. If the getter performs I/O, records a metric, or fetches a time-varying snapshot, this is a serious regression. For a `null` body, the naive version returns `text:<blank>` instead of `text:<null>`: it even changes the output.

**Solution:** call the getter only once and then process the retrieved value, such as `case TextMessage message -> textLabel(message.readBody());`. Use `when` guards for conditions genuinely needed to select a branch, and avoid repeatedly reading data with side effects.

### 7.1. Packet Getters Must Also Preserve Call Count and Order

Both `PacketMessage.header()` and `PacketMessage.payload()` in the demo increment a counter; both versions call each method exactly once. When refactoring:

```java
case PacketMessage message ->
        patternPacket(message.header(), message.payload());
```

Java evaluates method call arguments from left to right, so `header` is read before `payload`. Switching to a guard that calls `message.header()` multiple times can trigger extra side effects. If ordering matters, test with an event log like `["header","payload"]` rather than just summing total read counts.

### 7.2. Custom Record Accessors and Exceptions

Record pattern deconstruction invokes the record's accessors. For the default `Header` record in this exercise, the accessors simply return the components. However, Java allows records to declare custom accessors; they can mutate state or throw exceptions. When applying this to real records, verify getter call count/order and exceptions from deconstruction (if an accessor throws, pattern matching may wrap it in `MatchException` per Java 21 rules).

Do not assume every record pattern does fewer operations than a cast. Choose pattern depth based on the data actually needed.

## 8. Standalone Runnable Program and Differential Tests

Create the file **`LegacyModuleRefactorDemo.java`**. The program requires no JUnit, Maven, or external libraries. It checks the old and new implementations across 21 cases, comparing both return/exception outcomes and read counts. It uses `Supplier<Object>` to produce **two independent instances** with the same initial state.

```java
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Supplier;

public class LegacyModuleRefactorDemo {
    record Header(String channel, int priority) {}

    record Outcome(String result, String errorType, String errorMessage) {
        static Outcome ok(String s) {
            return new Outcome(s, null, null);
        }

        static Outcome error(String type, String message) {
            return new Outcome(null, type, message);
        }

        String display() {
            return errorType == null ? result
                    : errorType + ":" + errorMessage;
        }
    }

    static final class TextMessage {
        private final String body;
        private int reads;

        TextMessage(String body) { this.body = body; }

        String readBody() {
            reads++;
            return body;
        }

        int reads() { return reads; }
    }

    static final class CountMessage {
        private final int count;

        CountMessage(int count) { this.count = count; }

        int count() { return count; }
    }

    static final class PacketMessage {
        private final Header header;
        private final String payload;
        private int headerReads;
        private int payloadReads;

        PacketMessage(Header header, String payload) {
            this.header = header;
            this.payload = payload;
        }

        Header header() {
            headerReads++;
            return header;
        }

        String payload() {
            payloadReads++;
            return payload;
        }

        int reads() { return headerReads + payloadReads; }
    }

    static final class Heartbeat {}

    static final class ExplodingMessage {
        private int reads;

        String read() {
            reads++;
            throw new IllegalStateException("corrupted payload");
        }

        int reads() { return reads; }
    }

    static String textLabel(String body) {
        if (body == null) return "text:<null>";
        if (body.isBlank()) return "text:<blank>";
        return "text:" + body.strip();
    }

    static String payloadLabel(String payload) {
        return payload == null ? "<null>" : payload.strip();
    }

    static String legacyPacket(Header header, String payload) {
        if (header == null) return "packet:missing-header";
        String channel = header.channel();
        int priority = header.priority();

        if (channel == null || channel.isBlank()) {
            return "packet:invalid-channel";
        }
        if (priority >= 10) {
            return "packet:high:" + channel.strip()
                    + ":" + payloadLabel(payload);
        }
        return "packet:normal:" + channel.strip()
                + ":" + payloadLabel(payload);
    }

    static String patternPacket(Header header, String payload) {
        return switch (header) {
            case Header(var channel, var priority)
                    when channel == null || channel.isBlank() ->
                    "packet:invalid-channel";
            case Header(var channel, var priority) when priority >= 10 ->
                    "packet:high:" + channel.strip()
                            + ":" + payloadLabel(payload);
            case Header(var channel, var priority) ->
                    "packet:normal:" + channel.strip()
                            + ":" + payloadLabel(payload);
            case null -> "packet:missing-header";
        };
    }

    static String legacyRoute(Object input) {
        if (input == null) return "null-input";

        if (input instanceof TextMessage) {
            TextMessage message = (TextMessage) input;
            String body = message.readBody();
            return textLabel(body);
        }
        if (input instanceof CountMessage) {
            CountMessage count = (CountMessage) input;
            if (count.count() < 0) return "count:negative";
            return "count:" + count.count();
        }
        if (input instanceof PacketMessage) {
            PacketMessage message = (PacketMessage) input;
            Header header = message.header();
            String payload = message.payload();
            return legacyPacket(header, payload);
        }
        if (input instanceof Heartbeat) return "heartbeat";
        if (input instanceof ExplodingMessage) {
            ExplodingMessage message = (ExplodingMessage) input;
            return message.read();
        }
        return "unsupported";
    }

    static String modernRoute(Object input) {
        return switch (input) {
            case null -> "null-input";
            case TextMessage message ->
                    textLabel(message.readBody());
            case CountMessage count when count.count() < 0 ->
                    "count:negative";
            case CountMessage count -> "count:" + count.count();
            case PacketMessage message ->
                    patternPacket(message.header(), message.payload());
            case Heartbeat h -> "heartbeat";
            case ExplodingMessage message -> message.read();
            default -> "unsupported";
        };
    }

    // Intentionally wrong: reads getter with side effects multiple times.
    static String naiveTextRoute(Object input) {
        return switch (input) {
            case TextMessage message
                    when message.readBody() != null
                            && !message.readBody().isBlank() ->
                    "text:" + message.readBody().strip();
            case TextMessage message -> "text:<blank>";
            default -> "unsupported";
        };
    }

    static Outcome capture(Function<Object, String> fn, Object input) {
        try {
            return Outcome.ok(fn.apply(input));
        } catch (RuntimeException e) {
            return Outcome.error(
                    e.getClass().getSimpleName(), e.getMessage());
        }
    }

    static int reads(Object input) {
        if (input instanceof TextMessage text) return text.reads();
        if (input instanceof PacketMessage packet) return packet.reads();
        if (input instanceof ExplodingMessage bad) return bad.reads();
        return 0;
    }

    static int cases;
    static int assertions;

    static void check(String label, Supplier<Object> inputFactory,
                      Outcome expected, int expectedReads) {
        Object oldInput = inputFactory.get();
        Object newInput = inputFactory.get();
        Outcome before = capture(
                LegacyModuleRefactorDemo::legacyRoute, oldInput);
        Outcome after = capture(
                LegacyModuleRefactorDemo::modernRoute, newInput);

        if (!Objects.equals(before, expected)) {
            throw new AssertionError(
                    label + " legacy: " + before + " vs " + expected);
        }
        assertions++;
        if (!Objects.equals(after, expected)) {
            throw new AssertionError(
                    label + " modern: " + after + " vs " + expected);
        }
        assertions++;
        if (reads(oldInput) != expectedReads) {
            throw new AssertionError(
                    label + " old reads=" + reads(oldInput));
        }
        assertions++;
        if (reads(newInput) != expectedReads) {
            throw new AssertionError(
                    label + " new reads=" + reads(newInput));
        }
        assertions++;

        cases++;
        System.out.println(label + " => " + expected.display()
                + " | reads=" + expectedReads);
    }

    public static void main(String[] args) {
        check("text-trim", () -> new TextMessage(" Java "),
                Outcome.ok("text:Java"), 1);
        check("text-blank", () -> new TextMessage(" \t "),
                Outcome.ok("text:<blank>"), 1);
        check("text-null", () -> new TextMessage(null),
                Outcome.ok("text:<null>"), 1);
        check("text-unicode", () -> new TextMessage(" Xin chào "),
                Outcome.ok("text:Xin chào"), 1);

        check("count-negative", () -> new CountMessage(-1),
                Outcome.ok("count:negative"), 0);
        check("count-zero", () -> new CountMessage(0),
                Outcome.ok("count:0"), 0);
        check("count-positive", () -> new CountMessage(7),
                Outcome.ok("count:7"), 0);
        check("count-max",
                () -> new CountMessage(Integer.MAX_VALUE),
                Outcome.ok("count:2147483647"), 0);

        check("packet-high-boundary",
                () -> new PacketMessage(
                    new Header(" api ", 10), " body "),
                Outcome.ok("packet:high:api:body"), 2);
        check("packet-high",
                () -> new PacketMessage(
                    new Header("evt", 12), "hello"),
                Outcome.ok("packet:high:evt:hello"), 2);
        check("packet-normal-boundary",
                () -> new PacketMessage(
                    new Header("evt", 9), "hello"),
                Outcome.ok("packet:normal:evt:hello"), 2);
        check("packet-normal-negative",
                () -> new PacketMessage(
                    new Header("evt", -5), "hello"),
                Outcome.ok("packet:normal:evt:hello"), 2);
        check("packet-invalid-blank",
                () -> new PacketMessage(
                    new Header(" ", 10), "body"),
                Outcome.ok("packet:invalid-channel"), 2);
        check("packet-invalid-null",
                () -> new PacketMessage(
                    new Header(null, 10), "body"),
                Outcome.ok("packet:invalid-channel"), 2);
        check("packet-missing-header",
                () -> new PacketMessage(null, "body"),
                Outcome.ok("packet:missing-header"), 2);
        check("packet-null-payload",
                () -> new PacketMessage(
                    new Header("evt", 3), null),
                Outcome.ok("packet:normal:evt:<null>"), 2);
        check("packet-empty-payload",
                () -> new PacketMessage(
                    new Header("evt", 3), " "),
                Outcome.ok("packet:normal:evt:"), 2);

        check("heartbeat", Heartbeat::new,
                Outcome.ok("heartbeat"), 0);
        check("exploding", ExplodingMessage::new,
                Outcome.error(
                    "IllegalStateException", "corrupted payload"), 1);
        check("unsupported", Object::new,
                Outcome.ok("unsupported"), 0);
        check("selector-null", () -> null,
                Outcome.ok("null-input"), 0);

        System.out.println("PARITY CASES PASS: " + cases);

        TextMessage unsafe = new TextMessage(" Java ");
        String naive = naiveTextRoute(unsafe);
        if (!"text:Java".equals(naive) || unsafe.reads() != 3) {
            throw new AssertionError("expected naive triple-read");
        }
        assertions++;
        System.out.println("NAIVE GUARD => " + naive
                + " | reads=" + unsafe.reads());
        System.out.println("ASSERTIONS PASS: " + assertions);
    }
}
```

### 8.1. Compile and Run

Use JDK 21+ in the directory containing the file:

```bash
javac --release 21 LegacyModuleRefactorDemo.java
java LegacyModuleRefactorDemo
```

**Verified stdout:**

```text
text-trim => text:Java | reads=1
text-blank => text:<blank> | reads=1
text-null => text:<null> | reads=1
text-unicode => text:Xin chào | reads=1
count-negative => count:negative | reads=0
count-zero => count:0 | reads=0
count-positive => count:7 | reads=0
count-max => count:2147483647 | reads=0
packet-high-boundary => packet:high:api:body | reads=2
packet-high => packet:high:evt:hello | reads=2
packet-normal-boundary => packet:normal:evt:hello | reads=2
packet-normal-negative => packet:normal:evt:hello | reads=2
packet-invalid-blank => packet:invalid-channel | reads=2
packet-invalid-null => packet:invalid-channel | reads=2
packet-missing-header => packet:missing-header | reads=2
packet-null-payload => packet:normal:evt:<null> | reads=2
packet-empty-payload => packet:normal:evt: | reads=2
heartbeat => heartbeat | reads=0
exploding => IllegalStateException:corrupted payload | reads=1
unsupported => unsupported | reads=0
selector-null => null-input | reads=0
PARITY CASES PASS: 21
NAIVE GUARD => text:Java | reads=3
ASSERTIONS PASS: 85
```

### 8.2. Why Are There 85 Assertions?

Each `check(...)` verifies **four conditions**: the old code's value/exception matches expected, the new code's matches expected, the old read count matches, and the new read count matches. For 21 cases: \(21\times4=84\). Then one combined assertion confirms that the counterexample `naiveTextRoute` produces the right text while calling the getter three times: total **85**.

The program uses `throw new AssertionError`, so the JVM `-ea` flag is not needed to enable checks. There are no benchmarks and no real service connections.

### 8.3. Why Must Two Independent Instances Be Created?

The `check` method accepts a `Supplier<Object>` and creates separate `oldInput`/`newInput` instances:

```java
Object oldInput = inputFactory.get();
Object newInput = inputFactory.get();
```

If you ran old and then new on the same `TextMessage`, the counter would already be incremented from the first run, skewing the side-effect comparison. When testing production code with a database or network, use a sandbox or transaction isolation; **do not send two real state-mutating commands** just to check parity.

### 8.4. Limitations of This Test Suite

`capture(...)` only catches `RuntimeException` and compares class name and message; it does not compare stack traces or causes. If a real module must preserve checked exceptions, error codes, logs, audits, transactions, or performance, expand the tests accordingly. The fixtures only cover a finite set of inputs; PASS does not prove every possible state.

## 9. Regression Test Matrix Needed in a Real Module

| Category | Cases to Test | Why It Matters |
| --- | --- | --- |
| Happy path | One valid input per type | Preserves results |
| Null selector | `null` input | Switch does not automatically treat null as default |
| Null nested record | Null header | Record pattern does not match null |
| Null component | Null channel/payload | Guard does not throw an unexpected NPE |
| Blank and Unicode | `" "`, tab, Vietnamese | Preserves normalization |
| Numeric boundary | -1, 0, 9, 10, large values | Preserves `>=` conditions |
| Unknown type | `new Object()`, plugin subtype | Preserves fallback |
| Exception | Getter throws an error | Preserves exception class/contract |
| Getter count/order | Text, Packet, custom record accessor | Does not duplicate side effects |
| Serialization | JSON/XML/JPA binding if public DTOs are involved | Preserves wire/schema contract |
| Integration | Handler → DB/queue/service | Does not alter transactions or events |
| Performance | CPU, latency, allocation after parity PASS | Detects regressions |

Do not just compare the two versions against each other. If both have the same bug, parity tests will still pass. You need **contract-based expected values** or an independent golden baseline, such as `Outcome.ok(...)` and `Outcome.error(...)` in the demo.

For ordered side effects, use a spy that records an event sequence such as `["header","payload","audit"]` and compare old vs. new. Having equal total read counts does not prove the execution order is the same.

## 10. Compile-Time Errors When Writing Pattern Switch

The fragments below are **intentionally invalid**; keep them separate from the runnable file in section 8.

### 10.1. Dominance: Broader Type Before Narrower Type

```java
// INTENTIONALLY WRONG:
return switch (input) {
    case CharSequence seq -> "sequence";
    case String s -> "string";
    default -> "other";
};
```

`String` is a `CharSequence`, so the later branch is dominated. `javac --release 21` reports `this case label is dominated by a preceding case label`. Place the `String` branch first.

### 10.2. Constant `false` Guard

```java
// INTENTIONALLY WRONG:
return switch (header) {
    case Header h when false -> "never";
    default -> "other";
};
```

The Java 21 compiler rejects a label whose guard is the constant expression `false`. Do not use it to temporarily disable a case.

### 10.3. Pattern Variable Out of Scope

```java
// INTENTIONALLY WRONG:
return switch (input) {
    case String s when s.isBlank() -> "blank";
    default -> s;
};
```

The variable `s` does not exist in the `default` branch; the compiler reports `cannot find symbol`. Flow scoping allows using the variable in `when` and in the case body when matched, not arbitrarily outside.

### 10.4. `return` Inside a Switch Expression Block

```java
// INTENTIONALLY WRONG:
return switch (input) {
    case String s -> { return s; }
    default -> "other";
};
```

The compiler reports `attempt to return out of a switch expression`. When using a block, use `yield`:

```java
return switch (input) {
    case String s -> {
        String normalized = s.strip();
        yield normalized;
    }
    default -> "other";
};
```

The four invalid cases above were tested individually with `javac --release 21`. Compiler messages and line numbers may vary slightly across JDK versions. These errors are **compile-time**; you cannot put them into a runtime test and expect the test runner to handle them.

### 10.5. The Compiler Does Not Verify All Business Behavior

A `switch` can be exhaustive and still return the wrong payload, skip null, log twice, or use the wrong threshold. Combine compiler gates with regression tests.

## 11. Step-by-Step Refactoring on a Real Project

A safe process should proceed in a reviewable order:

1. **Scope the module:** identify the API, DTOs, callers, code to refactor, and dependency graph.
2. **Capture the baseline:** test happy paths, null/exceptions, unknown types, and side-effect counts/order; save appropriate test data.
3. **Classify casts:** guarded casts differ from unguarded direct casts; do not drop exception contracts.
4. **If possible, convert `instanceof + cast` to `instanceof Type variable` one by one** first, without changing the overall control flow.
5. **Keep public POJOs stable**; if an internal record adapter is needed, create it in an approved scope and test the mapping.
6. **Migrate the dispatcher to Java 21 `switch` patterns**, using `case null`, `default`, proper case ordering, and `when` where needed.
7. **Refactor internal helpers**, e.g., `Header` record → record pattern, without letting guards read stateful getters multiple times.
8. **Run differential tests on independent fixtures**, comparing outputs, exceptions, and side effects.
9. **Run integration/contract tests** for DB, JSON, queues, audits, and framework bindings if relevant.
10. **Review and run CI against the target Java release**. Do not leave old preview syntax in standard Java 21 code.
11. **Deploy with a rollback plan** via feature flag/canary/revert where supported.
12. **Monitor post-deployment metrics** and remove the old implementation once the transition is complete per policy.

**Do not bundle into a single PR**: converting public classes to records, sealing class hierarchies, upgrading the JDK, changing business logic, and optimizing algorithms. Each of those large changes may be valid on its own, but they need separate decisions, risk assessments, and test suites.

### 11.1. Shadow Comparisons Must Avoid Double Side Effects

If a handler performs real transactions, do not invoke both old and new on the same production event if both write to a DB or send messages. Shadow testing is only safe when the compared logic is pure or runs in an isolated environment. Parity testing must not become a source of duplicate data.

## 12. Configuring Java 21 in Builds and CI

### Maven

In the `<properties>` section of `pom.xml`:

```xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>
```

This is a configuration snippet, not a complete POM. The Maven/compiler plugin must support `release 21`; check Maven Toolchains or parent POMs for overrides. `mvn -version` helps confirm which JVM Maven actually runs on.

```bash
mvn -version
mvn test
```

### Gradle Kotlin DSL

Example in `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(21)
}
```

Ensure a Gradle version compatible with Java 21 and a properly installed/provisioned toolchain. With the Gradle wrapper, use `./gradlew test` or `gradlew.bat test` depending on your OS.

### Deployment Runtime

Compiling to Java 21 classfiles means the production runtime must also support Java 21. Check container images, CI runners, IDE project language levels, Maven/Gradle targets, agent instrumentation, and framework libraries. An IDE accepting Java 21 syntax **does not prove** the module is deployed on the right JDK.

## 13. Using JUnit for Multi-File Modules

The program in section 8 requires no libraries outside the JDK. In projects that already use JUnit Jupiter, move the cases into test classes. The example below assumes the test and `LegacyModuleRefactorDemo` are in the same package so it can access package-private members:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class MessageRouterRefactorTest {
    @Test
    void getterIsReadOnce() {
        var before = new LegacyModuleRefactorDemo.TextMessage(" Java ");
        var after = new LegacyModuleRefactorDemo.TextMessage(" Java ");

        assertEquals("text:Java",
                LegacyModuleRefactorDemo.legacyRoute(before));
        assertEquals("text:Java",
                LegacyModuleRefactorDemo.modernRoute(after));
        assertEquals(1, before.reads());
        assertEquals(1, after.reads());
    }

    @Test
    void nullKeepsFallback() {
        assertEquals("null-input",
                LegacyModuleRefactorDemo.legacyRoute(null));
        assertEquals("null-input",
                LegacyModuleRefactorDemo.modernRoute(null));
    }

    @Test
    void runtimeExceptionIsPreserved() {
        var before = new LegacyModuleRefactorDemo.ExplodingMessage();
        var after = new LegacyModuleRefactorDemo.ExplodingMessage();

        var oldError = assertThrows(IllegalStateException.class,
                () -> LegacyModuleRefactorDemo.legacyRoute(before));
        var newError = assertThrows(IllegalStateException.class,
                () -> LegacyModuleRefactorDemo.modernRoute(after));

        assertEquals(oldError.getMessage(), newError.getMessage());
        assertEquals(1, before.reads());
        assertEquals(1, after.reads());
    }
}
```

This is a **library-dependent JUnit snippet** and will not run with plain JDK `javac` alone. For tests in another package, adjust visibility or move the test into the same package. Do not open up public APIs just to test private internals if a better option exists.

**Parameterized tests:** Use `@MethodSource`/`Arguments` for input/expected tables, but create a fresh instance for each run. For DTOs with mutable state, use fixture factories; do not share one instance across parallel tests.

**Integration tests:** If the module writes to a DB, sends to a queue, or deserializes JSON, verify wire/schema/transaction behavior and emitted events. A type pattern refactor may pass at the unit level, while DTO/serialization changes will need dedicated tests.

## 14. Performance and Post-Refactor Observability

Pattern matching makes code clearer, but it **does not automatically guarantee faster execution** than the old `instanceof`/cast approach. HotSpot/JIT can optimize both. If the module is on a hot path:

- Profile to determine whether time is actually spent in dispatch, getters, regex, DB, or network.
- Measure baseline CPU, allocation, GC, throughput, and p95/p99 latency.
- Use JMH if microbenchmarking dispatch is needed, with diverse inputs and appropriate warm-up/forks.
- Ensure both implementations perform **the same work**; otherwise the benchmark compares the wrong thing.
- Re-measure after deployment and roll back if a regression occurs.

The demo proves that **accessor read count** changes with a naive guard—it is not a speed measurement. Do not report speedup percentages without reliable benchmark data.

## 15. Code Review Checklist

- [ ] Module scope, public API, and callers are properly identified.
- [ ] POJO contracts are preserved; public classes are not arbitrarily converted to records.
- [ ] Toolchain/source release/production runtime support Java 21.
- [ ] `instanceof + cast` is only converted when branch selection and exceptions are preserved.
- [ ] Type patterns on legacy classes work properly; record patterns are only used on appropriate records.
- [ ] `switch` expressions are exhaustive; unsupported types keep `default` when needed.
- [ ] `case null` preserves the null policy without relying on `default` to catch null.
- [ ] `when` guards use valid Java 21 syntax and have no dominated cases.
- [ ] Boundary conditions 9/10 and -1/0 remain accurate.
- [ ] Null selector, null nested record, and null components are tested separately.
- [ ] Getters with side effects are called the exact expected number of times and in the right order.
- [ ] Exception class/message/cause are preserved when part of the contract.
- [ ] Unicode/whitespace output is unchanged; `strip` is not arbitrarily swapped for `trim`.
- [ ] Differential tests use two independent but equivalent fixtures.
- [ ] Independent expected baselines exist, not just comparing old vs. new equality.
- [ ] Unit/integration/CI and compile gates all PASS.
- [ ] Rollout has observability and a rollback/revert plan.
- [ ] No speedup claims are made without measurement evidence.

**Definition of Done:** Java 21 code compiles and runs on the target; the module preserves the agreed API contract; all key baseline cases for output, exceptions, and side effects pass; the PR can be reviewed, deployed, and rolled back cleanly. If the refactor includes business logic changes, document and approve them separately rather than calling them equivalent.

## 16. Common Pitfalls

**1. "Using pattern matching requires converting every class to a record."** No. Type patterns work directly with POJO classes. Converting classes to records has its own API and framework implications.

**2. "New code with fewer lines cannot change behavior."** False. `case null`, `default`, `when` ordering, and getter calls can all change behavior.

**3. "Getters in guards have no side effects."** Not necessarily. The demo uses `TextMessage.readBody()` to show 1 call vs. 3 calls.

**4. "If the compiler accepts the switch, the business logic is right."** The compiler only checks syntax, typing, and certain dominance/exhaustiveness rules; it does not prove priority thresholds or outputs are correct.

**5. "If old and new match, that's enough."** Both could be wrong in the same way. You need contract-based expected values, boundary data, and integration tests.

**6. "Default handles null automatically."** No. When refactoring `if instanceof` to `switch`, handle null explicitly if the old behavior had a fallback.

**7. "Reordering cases makes it faster without any impact."** Order affects dominance and guard precedence; only change it with approval and tests.

**8. "Just replace direct casts with a pattern + fallback."** That can turn a `ClassCastException`/NPE into a different return value.

**9. "Enable sealed on every legacy interface."** Not if callers/plugins are still allowed to extend it.

**10. "Benchmarks matter more than regression tests."** No. Optimizing quickly while breaking behavior fails the goal of a safe refactor.

## 17. Exercises and Suggested Answers

**Exercise 1:** Convert only the `TextMessage` branch from `instanceof + cast` to `instanceof TextMessage message`. Which tests must remain unchanged?  
*Hint:* Output, null behavior, single body read, exceptions.

**Exercise 2:** Remove `case null` in `modernRoute`. Which case fails?  
*Hint:* `selector-null`; the switch can throw an NPE.

**Exercise 3:** Change `priority >= 10` to `priority > 10` in `patternPacket`. Which test catches it?  
*Hint:* `packet-high-boundary` with priority 10.

**Exercise 4:** Change `case PacketMessage message` to `case PacketMessage(...)`. Why does the compiler reject it?  
*Hint:* `PacketMessage` is currently a POJO class, not a record.

**Exercise 5:** Place an unguarded `case CountMessage count` before `when count.count() < 0`. What happens?  
*Hint:* Dominance; the guarded branch can never be selected.

**Exercise 6:** Try calling `naiveTextRoute(new TextMessage(null))`. Compare output and read count with the legacy version.  
*Hint:* The naive version returns text blank instead of text null; the logic changed.

**Exercise 7:** With JUnit, write a test verifying that `ExplodingMessage` throws `IllegalStateException` and calls the getter only once.  
*Hint:* Use `assertThrows` and separate old/new fixtures.

**Exercise 8:** If a public DTO is used by a JSON framework via getters/setters, should you convert it to a record right away in this PR?  
*Hint:* Not yet. Check schema/framework compatibility and separate the migration if needed.

**Exercise 9:** Design an event trace for `PacketMessage` to confirm the order `header()` before `payload()`.  
*Hint:* Record accessor names into a list in a spy; compare the two traces.

**Exercise 10:** Use Maven or Gradle to lock the Java 21 release and run all module tests. Why is changing only the IDE's JDK not enough?  
*Hint:* Build tools, CI, and the production runtime may still use a different JDK/target.

## Official References

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JLS SE 21 §14.11 — Switch Statements and Dominance](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS SE 21 §14.30 — Patterns and Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [JLS SE 21 §6.3 — Scope of Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [Apache Maven Compiler Plugin — Setting compiler release](https://maven.apache.org/components/plugins/maven-compiler-plugin/examples/set-compiler-release.html)
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
