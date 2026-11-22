# Testing Handlers by Subtype in Java 21

## 1. Case study objectives

In the **Command case study**, a handler typically receives a common parent type (such as `Command`) but must perform **the exact operation corresponding to each subtype**: opening a ticket, assigning it, or closing it. When using Java 21's **sealed interfaces**, **record patterns**, and **pattern matching for switch**, dispatching can be very clean. However, compiling code and a few passing commands **do not prove that the handler is correct for every subtype**.

This lesson focuses on **testing handlers by subtype**: building a closed Command model, defining the output and side-effect contract for each command, testing valid/invalid inputs, verifying event ordering, asserting that rejected commands do not mutate state, and seeing how the compiler helps verify subtype completeness.

After this lesson, you will be able to:

- Design a command set using a `sealed interface` and implementing `record` types; distinguish subtype dispatch from business validation.
- Write `switch (command)` using `case OpenTicket(...) when ...` along with a fallback branch **for the same subtype**.
- Write a test matrix covering each subtype, true/false guards, `null` root, `null` record components, non-existent tickets, conflicting states, and repeated commands.
- Assert not only **return values**, but also **record counts, record contents, event logs, and the absence of side effects when a command fails**.
- Distinguish **compile-time exhaustiveness** from **behavioral coverage** of unit tests.
- Use a standalone Java 21 program with assertions and verified output; translate the ideas into JUnit 5 tests in a real project.

**Version:** Java 21. Pattern matching for `switch` and record patterns became standard in Java 21 (JEP 441 and JEP 440). Type patterns for `instanceof` became standard in Java 16 (JEP 394). The examples run with `javac --release 21`, with no preview flags needed.

## 2. The model: one handler, three Command subtypes

In a simulated ticket management application, we accept three commands:

```java
sealed interface Command permits OpenTicket, AssignTicket, CloseTicket {}

record OpenTicket(String id, String title) implements Command {}
record AssignTicket(String id, String owner) implements Command {}
record CloseTicket(String id) implements Command {}
```

These are **illustrative declarations**, defined inside the complete class in section 6.

Each subtype has its own intent:

| Command subtype | Input data | Successful operation | Rejection cases |
|---|---|---|---|
| `OpenTicket` | ID, title | Creates a new ticket, records an `OPEN` event | Missing ID/title; ID already exists |
| `AssignTicket` | ID, owner | Assigns an owner to an unclosed ticket, records an `ASSIGN` event | Missing ID/owner; ticket does not exist; ticket is already closed |
| `CloseTicket` | ID | Transitions ticket to closed, records a `CLOSE` event | Missing ID; ticket does not exist; ticket is already closed |
| `null` | No command | Executes no operation | Returns code `REJECTED:NULL_COMMAND` |

A ticket is stored in the model as:

```java
record Ticket(String title, String owner, boolean closed) {}
```

**State contract:** `open` creates `Ticket(title, null, false)`; `assign` creates a new `Ticket` record preserving `title` and `closed=false` while updating `owner`; `close` creates a new record preserving `title`/`owner` and setting `closed=true`.

**Event contract:** only commands that **are processed successfully and mutate state** append an event. Commands rejected due to validation, not-found, or conflict **do not** append an event and **do not** mutate state.

**This is a teaching policy**, not a standard Java API or a mandatory rule for real ticket systems. This example allows reassigning an open ticket; a real system may require separate access-control checks, idempotency keys, transactions, and concurrency handling.

## 3. Subtype dispatch differs from business condition checks

In Java 21, a handler can use:

```java
String handle(Command command) {
    return switch (command) {
        case null -> "REJECTED:NULL_COMMAND";

        case OpenTicket(var id, var title)
                when hasText(id) && hasText(title) -> open(id, title);
        case OpenTicket ignored -> "REJECTED:OPEN_FIELDS";

        case AssignTicket(var id, var owner)
                when hasText(id) && hasText(owner) -> assign(id, owner);
        case AssignTicket ignored -> "REJECTED:ASSIGN_FIELDS";

        case CloseTicket(var id) when hasText(id) -> close(id);
        case CloseTicket ignored -> "REJECTED:CLOSE_FIELDS";
    };
}
```

The snippet above is an **illustrative method body**, with the helpers `hasText`, `open`, `assign`, and `close` defined in the full program.

There are three layers of responsibility:

1. **Subtype dispatch:** `case OpenTicket(...)`, `case AssignTicket(...)`, `case CloseTicket(...)` select the command kind based on runtime type and record structure.
2. **Input validation:** `when hasText(...)` decides whether a command of that subtype has sufficient minimal data.
3. **Domain operation:** `open/assign/close` inspect the current repository state and decide the outcome and side effects.

Crucially, `when` **does not turn the command into a new subtype**. For example, `OpenTicket(null, "Bug")` is still an `OpenTicket`, but the guard is not satisfied. Because `case OpenTicket ignored` follows afterward, the handler returns `REJECTED:OPEN_FIELDS` instead of dropping the input.

If you use multiple `case` branches for the same subtype, you must **place the guarded branch before the general branch**. Placing the general branch first can cause the narrower branch below it to be rejected by the compiler as *dominated*.

### 3.1. Why `var` matters when components are null

Record patterns use `var id`, `var title` directly on reference components. Even if `id == null` or `title == null`, the `OpenTicket` record can still match and bind those variables. The `hasText` guard then returns `false`.

With the helper:

```java
static boolean hasText(String value) {
    return value != null && !value.isBlank();
}
```

`&&` evaluates from left to right. `value.isBlank()` is only called after confirming the value is non-null, so a command with null fields does not cause a `NullPointerException`.

A **null at the root** is different: a `switch` receiving a null selector is handled by `case null`. Do not expect a regular `default` to catch null automatically; in Java 21 pattern switches, you must declare an explicit null policy if you want to return a string instead of throwing an exception.

## 4. A test matrix must be built from subtypes and state

Testing only one command of each type on the "happy path" is not enough. A useful matrix has two dimensions: **command subtype** and **current repository condition**.

| Group | Test case | Expected result | Mutates state/event? |
|---|---|---|---|
| Null root | `handle(null)` | `REJECTED:NULL_COMMAND` | No |
| Open — missing data | Null ID or blank title | `REJECTED:OPEN_FIELDS` | No |
| Open — success | Create T1 for the first time | `OPENED:T1` | Yes: adds ticket and event |
| Open — duplicate ID | Create T1 a second time | `CONFLICT:DUPLICATE:T1` | No |
| Assign — missing data | Null owner or empty ID | `REJECTED:ASSIGN_FIELDS` | No |
| Assign — not found | Assign T9 | `NOT_FOUND:T9` | No |
| Assign — success | Assign T1 to Ana | `ASSIGNED:T1` | Yes: updates owner and records event |
| Assign — reassign | Assign T1 to Ben | `ASSIGNED:T1` | Yes: new owner, new event |
| Assign — closed ticket | Assign T1 after close | `CONFLICT:CLOSED:T1` | No |
| Close — missing data | Null ID | `REJECTED:CLOSE_FIELDS` | No |
| Close — not found | Close T9 | `NOT_FOUND:T9` | No |
| Close — success | Close T1 | `CLOSED:T1` | Yes: closed=true, event |
| Close — repeated | Close T1 again | `CONFLICT:ALREADY_CLOSED:T1` | No |

Most dispatch bugs are not about `case OpenTicket` failing to be selected, but about a command **having the right type while its guard is false or the domain state disallows it**. When testing, name each case so a reviewer knows which kind is being verified.

### 4.1. Testing commands per subtype

For each subtype, you should have at least:

- **One happy path** to confirm the case is selected and the operation is correct.
- **One invalid input** to confirm the guarded case is skipped and the same-subtype fallback is selected.
- **One domain state error** if the operation depends on the repository.
- **One side-effect test**: a failed command must not silently mutate data or write an audit entry.
- **One boundary test** for empty, blank, null fields, or repeated states, depending on the subtype's contract.

Subtype coverage **is not the same as branch coverage**. One passing `OpenTicket` test does not cover the validation and duplicate branches. One passing `AssignTicket` test does not guarantee that assigning a closed ticket will be rejected.

### 4.2. Testing before and after state

If you only write:

```java
assertEquals("ASSIGNED:T1", handler.handle(new AssignTicket("T1", "Ana")));
```

then the test can pass even if the handler **did not update the owner** or added two events. Therefore, you need to inspect the actual stored `Ticket` and the event history.

Conversely, a failing command might return the right error code while accidentally calling `tickets.put(...)` or recording an event before returning. That is why you should capture a **state snapshot before calling** and compare it afterward.

## 5. Designing a fake repository for I/O-free testing

The example uses a handler with:

```java
private final Map<String, Ticket> tickets = new HashMap<>();
private final List<String> events = new ArrayList<>();
```

Benefits:

- No database, message broker, HTTP server, or transaction manager required.
- You can directly inspect ticket count, record contents, event count, and event order.
- Tests run fast and are reproducible locally and in CI.
- All state in the example lives in a single `Handler` object, making it easy to follow the command sequence.

**Limitations:** an in-memory fake does not prove database transactions, isolation, retries, multithreaded synchronization, or real-world publish ordering. After unit tests, you still need integration/contract tests for the real system's repository and messaging adapters.

If production code already uses interfaces such as `TicketRepository` and `EventPublisher`, inject fake implementations instead of embedding a `HashMap` into the production handler. The example in this lesson puts everything in one class to provide **a self-contained runnable Java file**; this is a pedagogical choice.

## 6. Complete Java 21 program compiled and run

Save the following code as **`SubtypeHandlerTestDemo.java`**. The program has no dependency on JUnit or external libraries. It checks 17 handler invocations against expected output, ticket count, event count, and state mutation; it also verifies `Ticket` contents and the final order of all events.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

public class SubtypeHandlerTestDemo {
    sealed interface Command permits OpenTicket, AssignTicket, CloseTicket {}
    record OpenTicket(String id, String title) implements Command {}
    record AssignTicket(String id, String owner) implements Command {}
    record CloseTicket(String id) implements Command {}
    record Ticket(String title, String owner, boolean closed) {}

    static boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    static final class Handler {
        private final Map<String, Ticket> tickets = new HashMap<>();
        private final List<String> events = new ArrayList<>();

        String handle(Command command) {
            return switch (command) {
                case null -> "REJECTED:NULL_COMMAND";
                case OpenTicket(var id, var title)
                        when hasText(id) && hasText(title) -> open(id, title);
                case OpenTicket ignored -> "REJECTED:OPEN_FIELDS";
                case AssignTicket(var id, var owner)
                        when hasText(id) && hasText(owner) -> assign(id, owner);
                case AssignTicket ignored -> "REJECTED:ASSIGN_FIELDS";
                case CloseTicket(var id) when hasText(id) -> close(id);
                case CloseTicket ignored -> "REJECTED:CLOSE_FIELDS";
            };
        }

        private String open(String id, String title) {
            if (tickets.containsKey(id)) return "CONFLICT:DUPLICATE:" + id;
            tickets.put(id, new Ticket(title, null, false));
            events.add("OPEN:" + id);
            return "OPENED:" + id;
        }

        private String assign(String id, String owner) {
            Ticket current = tickets.get(id);
            if (current == null) return "NOT_FOUND:" + id;
            if (current.closed()) return "CONFLICT:CLOSED:" + id;
            tickets.put(id, new Ticket(current.title(), owner, false));
            events.add("ASSIGN:" + id + ":" + owner);
            return "ASSIGNED:" + id;
        }

        private String close(String id) {
            Ticket current = tickets.get(id);
            if (current == null) return "NOT_FOUND:" + id;
            if (current.closed()) return "CONFLICT:ALREADY_CLOSED:" + id;
            tickets.put(id, new Ticket(current.title(), current.owner(), true));
            events.add("CLOSE:" + id);
            return "CLOSED:" + id;
        }
    }

    static void expect(String label, Handler handler, Command command,
                       String expectedResult, int expectedCount, int expectedEvents,
                       boolean expectedMutation) {
        Map<String, Ticket> before = new HashMap<>(handler.tickets);
        List<String> auditBefore = new ArrayList<>(handler.events);
        String result = handler.handle(command);
        boolean mutated = !before.equals(handler.tickets)
                || !auditBefore.equals(handler.events);
        if (!Objects.equals(expectedResult, result)
                || handler.tickets.size() != expectedCount
                || handler.events.size() != expectedEvents
                || mutated != expectedMutation) {
            throw new AssertionError(label + ": " + result
                    + " count=" + handler.tickets.size()
                    + " events=" + handler.events.size()
                    + " mutated=" + mutated);
        }
        System.out.println(label + " => " + result + " | mutated=" + mutated);
    }

    static void ticketEquals(Handler handler, String id, Ticket expected) {
        if (!Objects.equals(expected, handler.tickets.get(id))) {
            throw new AssertionError("ticket state mismatch for " + id);
        }
    }

    static void auditEquals(Handler handler, String... expected) {
        if (!handler.events.equals(List.of(expected))) {
            throw new AssertionError("event log mismatch: " + handler.events);
        }
    }

    public static void main(String[] args) {
        Handler handler = new Handler();
        expect("null command", handler, null, "REJECTED:NULL_COMMAND", 0, 0, false);
        expect("open null id", handler, new OpenTicket(null, "Bug"),
                "REJECTED:OPEN_FIELDS", 0, 0, false);
        expect("open blank title", handler, new OpenTicket("T1", " "),
                "REJECTED:OPEN_FIELDS", 0, 0, false);
        expect("open T1", handler, new OpenTicket("T1", "Bug"),
                "OPENED:T1", 1, 1, true);
        ticketEquals(handler, "T1", new Ticket("Bug", null, false));
        expect("duplicate T1", handler, new OpenTicket("T1", "Another"),
                "CONFLICT:DUPLICATE:T1", 1, 1, false);
        expect("open T2", handler, new OpenTicket("T2", "Feature"),
                "OPENED:T2", 2, 2, true);

        expect("assign null owner", handler, new AssignTicket("T1", null),
                "REJECTED:ASSIGN_FIELDS", 2, 2, false);
        expect("assign blank id", handler, new AssignTicket("", "Ana"),
                "REJECTED:ASSIGN_FIELDS", 2, 2, false);
        expect("assign absent", handler, new AssignTicket("T9", "Ana"),
                "NOT_FOUND:T9", 2, 2, false);
        expect("assign T1", handler, new AssignTicket("T1", "Ana"),
                "ASSIGNED:T1", 2, 3, true);
        ticketEquals(handler, "T1", new Ticket("Bug", "Ana", false));
        expect("reassign T1", handler, new AssignTicket("T1", "Ben"),
                "ASSIGNED:T1", 2, 4, true);
        ticketEquals(handler, "T1", new Ticket("Bug", "Ben", false));

        expect("close null id", handler, new CloseTicket(null),
                "REJECTED:CLOSE_FIELDS", 2, 4, false);
        expect("close absent", handler, new CloseTicket("T9"),
                "NOT_FOUND:T9", 2, 4, false);
        expect("close T1", handler, new CloseTicket("T1"),
                "CLOSED:T1", 2, 5, true);
        ticketEquals(handler, "T1", new Ticket("Bug", "Ben", true));
        expect("close T1 twice", handler, new CloseTicket("T1"),
                "CONFLICT:ALREADY_CLOSED:T1", 2, 5, false);
        expect("assign closed", handler, new AssignTicket("T1", "Ana"),
                "CONFLICT:CLOSED:T1", 2, 5, false);
        expect("close T2", handler, new CloseTicket("T2"),
                "CLOSED:T2", 2, 6, true);
        ticketEquals(handler, "T2", new Ticket("Feature", null, true));

        auditEquals(handler, "OPEN:T1", "OPEN:T2", "ASSIGN:T1:Ana",
                "ASSIGN:T1:Ben", "CLOSE:T1", "CLOSE:T2");
        System.out.println("audit => 6 events in expected order");
    }
}
```

### Compile and run

On JDK 21 or higher:

```bash
javac --release 21 SubtypeHandlerTestDemo.java
java SubtypeHandlerTestDemo
```

**Verified actual stdout:**

```text
null command => REJECTED:NULL_COMMAND | mutated=false
open null id => REJECTED:OPEN_FIELDS | mutated=false
open blank title => REJECTED:OPEN_FIELDS | mutated=false
open T1 => OPENED:T1 | mutated=true
duplicate T1 => CONFLICT:DUPLICATE:T1 | mutated=false
open T2 => OPENED:T2 | mutated=true
assign null owner => REJECTED:ASSIGN_FIELDS | mutated=false
assign blank id => REJECTED:ASSIGN_FIELDS | mutated=false
assign absent => NOT_FOUND:T9 | mutated=false
assign T1 => ASSIGNED:T1 | mutated=true
reassign T1 => ASSIGNED:T1 | mutated=true
close null id => REJECTED:CLOSE_FIELDS | mutated=false
close absent => NOT_FOUND:T9 | mutated=false
close T1 => CLOSED:T1 | mutated=true
close T1 twice => CONFLICT:ALREADY_CLOSED:T1 | mutated=false
assign closed => CONFLICT:CLOSED:T1 | mutated=false
close T2 => CLOSED:T2 | mutated=true
audit => 6 events in expected order
```

There are **17 command scenarios** and one final verification of the entire event history. The program throws an `AssertionError` if the return value, repository size, event count, mutation flag, or specific snapshot is wrong. Printing all 18 lines above only happens when every assertion passes.

**Scope of proof:** This test suite demonstrates that the example's logic is correct for the tested inputs and provides evidence of side effects in the fake store. It **does not** prove that a production handler will be safe under database transactions, networking, asynchrony, or multithreaded contention.

## 7. Result analysis by subtype

### 7.1. OpenTicket: validation, success, and duplicate

Three main paths:

```java
case OpenTicket(var id, var title)
        when hasText(id) && hasText(title) -> open(id, title);
case OpenTicket ignored -> "REJECTED:OPEN_FIELDS";
```

- `new OpenTicket(null, "Bug")` is still an `OpenTicket` and the record pattern binds the components, but `hasText(id)` is false, so the fallback returns `REJECTED:OPEN_FIELDS`. There is no state or event change.
- `new OpenTicket("T1", " ")` has a blank title: `hasText(title)` is false, so the fallback is also selected.
- `new OpenTicket("T1", "Bug")` is valid: the guard is true, `open` creates the ticket and records an `OPEN` event.
- An `OpenTicket` command with the same ID but a different title **does not** overwrite the existing ticket: the domain operation returns `CONFLICT:DUPLICATE:T1` with `mutated=false`.

The test does not just assert the string `OPENED:T1`; it also checks that the actual ticket is `Ticket("Bug", null, false)`. If the handler appends an event but forgets to update the map, or updates the map with the wrong title, the test fails.

### 7.2. AssignTicket: validation, missing, update, closed

Branches:

```java
case AssignTicket(var id, var owner)
        when hasText(id) && hasText(owner) -> assign(id, owner);
case AssignTicket ignored -> "REJECTED:ASSIGN_FIELDS";
```

When the ID or owner is invalid, the handler **does not call** the `assign` method. With valid inputs for a non-existent ticket, the method runs and returns `NOT_FOUND:T9` with no side effects.

When ticket T1 is open:

1. Assign to Ana -> Ticket title stays unchanged, `owner="Ana"`, `closed=false`, and an event is appended.
2. Reassign to Ben -> Ticket `owner="Ben"`, preserving title and `closed=false`; a new event is appended.

When Ticket T1 is already closed, the `AssignTicket` command is valid in syntax/fields but **invalid in domain state**. The result is `CONFLICT:CLOSED:T1`, and neither owner nor event log may be modified. This is an important distinction between a **guard match** and a **business rule**.

### 7.3. CloseTicket: missing, success, repeated

Branches:

```java
case CloseTicket(var id) when hasText(id) -> close(id);
case CloseTicket ignored -> "REJECTED:CLOSE_FIELDS";
```

- Null ID -> missing-data fallback.
- Non-existent ID T9 -> `NOT_FOUND:T9`.
- Open ID T1 -> transitions to `closed=true`, records `CLOSE:T1`.
- Already closed ID T1 -> `CONFLICT:ALREADY_CLOSED:T1`, no duplicate event recorded.
- Open ID T2 -> closes successfully, keeping `owner` as `null` if the ticket was never assigned.

The "close twice" test proves a policy that is **not idempotent in its result label**: the second attempt returns a conflict, not `CLOSED` again. In terms of **state effect**, however, the repeated command does not mutate data. A production API might choose to return "already closed" as an idempotent success; what matters is establishing a clear contract and testing against that contract.

### 7.4. Null command

`case null -> "REJECTED:NULL_COMMAND";` is an explicit path. In a Java 21 pattern switch, a general `default` **does not automatically catch a null selector**. Do not assume a handler can omit `case null` and still return the same error code.

## 8. Why checking side effects matters as much as output

In the program, `expect(...)` copies the map and event list before each invocation:

```java
Map<String, Ticket> before = new HashMap<>(handler.tickets);
List<String> auditBefore = new ArrayList<>(handler.events);
String result = handler.handle(command);
boolean mutated = !before.equals(handler.tickets)
        || !auditBefore.equals(handler.events);
```

The `mutated` flag proves that when a command is rejected, the fake store and event history remain unchanged. However, that flag **can only say "there was an observable difference"**; that is why the program also checks counts, expected results, snapshots of each key `Ticket`, and the full final event sequence.

For example, a bug might "mistakenly assign T2 instead of T1": the map size would still be 2 and the event count would still increase by 1. If a test only checks counts, that bug could slip through. Checking the `Ticket("Bug","Ana",false)` snapshot for T1 and the event order catches far more discrepancies.

In applications that use mocks:

- Use a **fake repository** when you need to verify state after a sequence of operations.
- Use a **mock/spy port** when you want to verify that an external dependency call occurred exactly once or did not occur at all.
- If the handler publishes events after commit, you need an integration test for the transaction boundary, not just an in-memory list check.
- If the handler uses a clock, UUID generator, or network, inject those dependencies so tests remain deterministic and reproducible.

**Do not treat "no state change at the end" as absolute proof of "no side effects".** A handler could call an external service and then roll back its local map. In this lesson, all observable side effects live in the map and list, so snapshots are meaningful. In production, you must also account for external side-effect ports.

## 9. JUnit 5: separating tests by responsibility instead of only running main

The program in section 6 is self-contained and compiles with the JDK alone. When moving into a project, you can write a separate test class using **JUnit Jupiter 5** (requiring dependencies in Maven/Gradle). Example in the **same package** as `SubtypeHandlerTestDemo`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

class SubtypeHandlerJUnitTests {
    @Test
    void openTicketCreatesExactlyOneTicket() {
        var handler = new SubtypeHandlerTestDemo.Handler();

        assertEquals("OPENED:T1",
                handler.handle(new SubtypeHandlerTestDemo.OpenTicket("T1", "Bug")));

        SubtypeHandlerTestDemo.ticketEquals(
                handler, "T1", new SubtypeHandlerTestDemo.Ticket("Bug", null, false));
        SubtypeHandlerTestDemo.auditEquals(handler, "OPEN:T1");
    }

    @Test
    void assignUnknownTicketDoesNotProduceEvent() {
        var handler = new SubtypeHandlerTestDemo.Handler();

        assertEquals("NOT_FOUND:T9",
                handler.handle(new SubtypeHandlerTestDemo.AssignTicket("T9", "Ana")));

        SubtypeHandlerTestDemo.auditEquals(handler);
    }

    @Test
    void invalidOpenIsRejectedBySubtypeFallback() {
        var handler = new SubtypeHandlerTestDemo.Handler();

        assertEquals("REJECTED:OPEN_FIELDS",
                handler.handle(new SubtypeHandlerTestDemo.OpenTicket(null, "Bug")));
        SubtypeHandlerTestDemo.auditEquals(handler);
    }
}
```

This is a **supplementary JUnit example**, not code compiled with plain `javac --release 21`. Running it requires JUnit Jupiter 5, an appropriate test runner, and a matching package structure. If you place the main class in a named package, the test class must reside in the same package (or adjust visibility intentionally).

**Better ways to organize tests as a project grows:**

- Give each subtype its own unit test group: `OpenTicketHandlerTest`, `AssignTicketHandlerTest`, `CloseTicketHandlerTest`, or `@Nested` groups within one class.
- Use `@ParameterizedTest` when there are multiple variants of the same rule (such as null, empty, and whitespace-only fields), but **do not lump all subtypes into one shared expected result** if their contracts differ.
- Each test should create a **fresh `Handler`** or build a fake repository from deterministic fixture data to avoid depending on JUnit execution order.
- When you need to test a state sequence such as open -> assign -> close, keep that sequence **inside one clearly named test**, rather than using an open test to prepare state for a close test.
- Assert both the command result and state/event assertions; separate validation, conflict, and not-found assertions so failures immediately point to the cause.

### Suggested JUnit matrix

| Test group | Representative test | Assertion types |
|---|---|---|
| `OpenTicket` valid | Create new ticket | Result, ticket snapshot, event |
| `OpenTicket` invalid | Null ID / blank title | Result, state unchanged, no event |
| `OpenTicket` duplicate | Existing ID | Conflict, no overwrite, no event |
| `AssignTicket` valid | Update owner | Result, new owner, exact event |
| `AssignTicket` not found | Missing ID | Not found, no state/event |
| `AssignTicket` closed | Assign closed ticket | Conflict, state/event preserved |
| `CloseTicket` valid | Close ticket | Result, closed=true, event |
| `CloseTicket` repeated | Close a second time | Conflict, no duplicate event |
| Null command | `handle(null)` | Result, no side effect |
| Workflow | Open -> Assign -> Close | State and event order end-to-end |

**The compiler does not know** that Test A needs to check for an event while Test B needs to check that no event occurred. That is the responsibility of the test contract.

## 10. Exhaustiveness: the compiler checks subtypes, tests check behavior

### 10.1. Sealed design helps catch missing handlers

With:

```java
sealed interface Command permits OpenTicket, AssignTicket, CloseTicket {}
```

and a `switch expression` handling every subtype with an unguarded fallback branch for that exact subtype:

```java
case OpenTicket ignored -> "REJECTED:OPEN_FIELDS";
case AssignTicket ignored -> "REJECTED:ASSIGN_FIELDS";
case CloseTicket ignored -> "REJECTED:CLOSE_FIELDS";
```

the compiler can prove that all non-null commands have a matching branch. If the application adds `ReopenTicket` to `permits` without adding a case for it, the build fails with an exhaustiveness error. This is a **benefit of not adding `default` unnecessarily**.

**Do not confuse them:** exhaustiveness only proves that every subtype has a path. It does not prove that `OpenTicket` actually creates a record, `AssignTicket` updates the owner, or `CloseTicket` emits the right event. Those must be tested.

### 10.2. Example where the compiler rejects a missing subtype

The following standalone file **`MissingSubtypeCase.java`** **intentionally does not compile**:

```java
public class MissingSubtypeCase {
    sealed interface Command permits Open, Close, Retry {}
    record Open() implements Command {}
    record Close() implements Command {}
    record Retry() implements Command {}

    static String handle(Command command) {
        return switch (command) {
            case Open open -> "OPEN";
            case Close close -> "CLOSE";
        };
    }
}
```

Compile:

```bash
javac --release 21 MissingSubtypeCase.java
```

The compiler rejects it because `Retry` is not covered in the `switch expression`. This behavior was verified with `javac --release 21`.

If you replace it with `default -> "IGNORED";`, the code compiles without forcing the team to define the semantics of the new `Retry` command. In a closed command domain, that is risky: a new subtype gets "swallowed" without a build error.

### 10.3. Example where the compiler rejects a dominated branch

The standalone file **`DominatedSubtypeCase.java`** also **intentionally does not compile**:

```java
public class DominatedSubtypeCase {
    sealed interface Command permits Open, Close {}
    record Open() implements Command {}
    record Close() implements Command {}

    static String handle(Command command) {
        return switch (command) {
            case Command any -> "ANY";
            case Open open -> "OPEN";
            case Close close -> "CLOSE";
        };
    }
}
```

Compile:

```bash
javac --release 21 DominatedSubtypeCase.java
```

`case Command any` covers every non-null command, making the two subtype branches below it **dominated**. `javac` was tested and rejects these branches. Fix it by placing the specific subtype cases first (or removing the broad branch when the sealed hierarchy is already exhaustively covered).

### 10.4. Adding a subtype is a new test requirement

When adding a command record:

```java
record ReopenTicket(String id) implements Command {}
```

beyond updating `permits` and `switch`, add **dedicated tests** for `ReopenTicket`'s happy path, validation, domain state errors, side effects, and event ordering. The compiler only reminds you about a missing `case`; it **does not generate tests for you**.

## 11. The difference between match, guard, and domain failure

This is the most important separation when testing a handler:

| Input | Subtype pattern matches? | Guard valid? | Operation called? | Result |
|---|---|---|---|---|
| `new OpenTicket(null,"Bug")` | Yes | No | No | `REJECTED:OPEN_FIELDS` |
| `new OpenTicket("T1","Bug")` first time | Yes | Yes | Yes | `OPENED:T1` |
| `new OpenTicket("T1","Other")` when T1 exists | Yes | Yes | Yes | `CONFLICT:DUPLICATE:T1` |
| `new AssignTicket("T9","Ana")` | Yes | Yes | Yes | `NOT_FOUND:T9` |
| `new AssignTicket("T1","Ana")` when T1 is closed | Yes | Yes | Yes | `CONFLICT:CLOSED:T1` |
| `new CloseTicket(null)` | Yes | No | No | `REJECTED:CLOSE_FIELDS` |
| `new CloseTicket("T1")` when open | Yes | Yes | Yes | `CLOSED:T1` |
| `new CloseTicket("T1")` second time | Yes | Yes | Yes | `CONFLICT:ALREADY_CLOSED:T1` |
| `null` | Not a subtype | Not evaluated | No | `REJECTED:NULL_COMMAND` |

Takeaways from the table:

- **"Pattern does not match"** is different from **"pattern matches, but guard is false"**.
- **"Guard is true"** is different from **"command is accepted in the current domain state"**.
- **"Handler returns a success code"** is different from **"state/events are correct after processing"**.

When writing tests by subtype, be clear about which layer you are protecting. Failures from these three layers should have distinct names in tests for faster diagnosis.

## 12. Common mistakes when testing handlers by subtype

### 12.1. Checking only the return value

Testing `assertEquals("CLOSED:T1", handle(...))` will not catch forgetting to set `closed=true`. Assert the final record and corresponding event.

### 12.2. Checking only the event count

Publishing two events in the wrong order can still produce the right count. Assert **event content and ordering**; in the example, the expected sequence is `OPEN:T1` -> `OPEN:T2` -> `ASSIGN:T1:Ana` -> `ASSIGN:T1:Ben` -> `CLOSE:T1` -> `CLOSE:T2`.

### 12.3. Testing failure after state was silently modified

A handler might update the map before detecting a duplicate or conflict. Tests must prove that state **remains unchanged** on every failure branch, not just that the error code matches expectations.

### 12.4. Ignoring null and blank inputs

`OpenTicket(null,"Bug")` is still the right subtype, but it fails input requirements. If `when` calls `id.isBlank()` before checking for null, a null component can throw an exception. Tests need both null and whitespace strings.

### 12.5. Testing subtypes by class name string

There is no need to write logic like `command.getClass().getSimpleName().equals("OpenTicket")` to verify dispatch. It breaks easily during renaming or refactoring. Use the actual subtype instance and expected behavior; the compiler checks the types.

### 12.6. Using default to "ensure it is always handled"

In a sealed hierarchy, `default` can hide a missing handler for a new subtype. If the command domain is intentionally closed, leverage an exhaustive switch. If the command is an open set of types, use a fallback with a clear policy and test that fallback.

### 12.7. Placing a general case before a specific case

`case Command c` before `case OpenTicket o` makes the narrower case dominated, and the compiler rejects it. Runtime tests cannot fix a compile-time error.

### 12.8. Mixing tests of multiple subtypes into one vague assertion

A giant "all commands work" test with the same expectation for every subtype makes failures hard to diagnose. Use focused tests, name them after the state being tested, and only combine into a workflow when you intentionally want to test interactions between commands.

### 12.9. Making tests depend on JUnit execution order

If an `OpenTicket` test runs first and creates a fixture for an `AssignTicket` test in a shared handler, results become flaky when JUnit reruns or runs tests in parallel. Each test should create its own fixture. The `main` example in section 6 is **an intentional sequential workflow**, not a pattern for multiple tests to depend on each other.

### 12.10. Ignoring concurrency and transactions

A fake `Map` does not simulate two threads executing `OpenTicket` with the same ID simultaneously. Checking `containsKey` and then `put` in the example does not guarantee atomicity under concurrency. For production, you need unique constraints, transactions/locking, or an appropriate idempotency strategy, along with integration tests. Do not conclude from these unit tests that the system is race-condition-safe.

## 13. Pre-merge checklist for a subtype handler

1. **Subtype set:** Does `sealed Command` include all current subtypes? Were new handler branches added when new subtypes were added?
2. **Branch ordering:** Do guarded cases come before the same-subtype fallback? Are any branches dominated?
3. **Null selector:** Is the `case null` policy explicitly defined?
4. **Null components:** Does `var` bind null safely; does `hasText`/validation short-circuit safely?
5. **Happy path per subtype:** Does the handler return the right result and update state/events per the contract?
6. **Invalid input per subtype:** Is the command rejected before calling the domain operation, with no side effects?
7. **Domain conflicts:** Do duplicate/not-found/closed cases return clear labels and leave state unchanged?
8. **Repeated commands:** Does a repeated command behave idempotently or return a conflict according to policy? Is there a repeated-command test?
9. **Event ordering:** Do events have the right content, count, and order?
10. **Test isolation:** Does each JUnit test build its own handler/fixture without depending on run order?
11. **Compiler exhaustiveness:** Are all subtypes covered without adding an arbitrary `default`?
12. **Boundary integration:** Have production repositories/event publishers been tested with appropriate transactions and concurrency?
13. **Source level:** Do tests and builds run on Java 21 with the proper `--release 21` flag and matching runtime?
14. **QA status:** Mark as passing only when both compilation and behavioral assertions pass, not based on style or code coverage alone.

## 14. Self-check exercises

**Exercise 1.** Does `new AssignTicket(null,"Ana")` fail to match `case AssignTicket(var id,var owner)`?

**Answer:** No. The record exists, so the `id` component can bind `null` via `var`. The `hasText(id)` guard is false, causing the guarded branch to be skipped; the fallback `AssignTicket ignored` returns `REJECTED:ASSIGN_FIELDS`.

**Exercise 2.** Ticket T1 is already closed. Which branch does `AssignTicket("T1","Ana")` enter?

**Answer:** The data guard passes, so it enters `assign(id,owner)`. The method sees that the ticket is closed and returns `CONFLICT:CLOSED:T1` without emitting an event. This is not a pattern mismatch error.

**Exercise 3.** Why must a duplicate test also check the title of the existing `Ticket`?

**Answer:** A handler might accidentally overwrite the title on a duplicate ID while still returning a conflict. The snapshot must prove the existing data was preserved.

**Exercise 4.** You add `ReopenTicket` to the sealed hierarchy without adding a case. Why can the build reject it?

**Answer:** The `switch expression` has no `default` and must be exhaustive. The compiler detects that a permitted subtype has no matching branch.

**Exercise 5.** If you add `default -> "IGNORED"`, why is that still insufficient for testing the new subtype?

**Answer:** The compiler may accept the fallback, but the code has not defined the semantics of the new command. You must add the domain operation and appropriate tests rather than masking a missing case.

**Exercise 6.** A handler returns `OPENED:T1` but does not append `OPEN:T1` to the event list. Will a test that only compares the return value catch this?

**Answer:** No. You must check event count and event content, especially for side-effect behaviors.

**Exercise 7.** Why can the `main` test use a single shared `Handler`, whereas multiple JUnit unit tests should not share a mutable `Handler`?

**Answer:** `main` intentionally simulates **an ordered workflow**, whereas unit tests must be isolated so they do not depend on execution order and can run in parallel.

**Exercise 8.** If you need to verify that no email is sent when a command is rejected, but the fake `Map` does not record emails, what should you do?

**Answer:** Extract the email gateway into a dependency/port, and use a mock or fake email gateway to assert **zero invocations**. A `Map` snapshot does not prove there are no side effects outside the `Map`.

**Exercise 9.** How does `case null` relate to subtype exhaustiveness checking?

**Answer:** It defines how a null selector is handled. Subtype cases handle non-null command values; the two concerns should be treated separately.

**Exercise 10.** Why do we need to test `close T1 twice` even after `close T1` has been tested successfully?

**Answer:** Because a repeated command could emit a duplicate event or modify state a second time. The demo policy specifies that the second attempt is a conflict with no mutation.

## Conclusion

To **test handlers by subtype**, do not just invoke each branch once. Treat each subtype as a **contract** consisting of valid input, validation failure, repository state, output, and side effects. `sealed Command` + pattern matching `switch` makes dispatch explicit, reduces manual casts, and provides exhaustiveness checks when new variants are added. `when` guards handle data conditions, while domain operations decide success or conflict.

The best test suite has **independent expected outputs**, before/after state snapshots, ordered event logs, repeated-command tests, and tests verifying **no side effects on failure paths**. The compiler guarantees branch structure, while behavioral tests protect business correctness. As the application grows to include databases, messaging, and concurrency, add integration tests for those boundaries rather than expecting an in-memory fake to prove everything.

## Official references

- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Java SE 21 Language Specification — Switch statements §14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 Language Specification — Patterns §14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
