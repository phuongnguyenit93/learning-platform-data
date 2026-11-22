# Handling Invalid Commands with Java Pattern Matching

## 1. Context: Invalid Commands Are Not Just One Kind of Error

In an application that receives commands from a CLI, HTTP API, message queue, or another service, callers can send malformed or invalid data in many ways. For example, an internal account management system supports:

- `CREATE|carol|Carol|30`: creates account `carol`, display name `Carol`, initial credit balance `30`.
- `TRANSFER|alice|bob|40`: transfers `40` credits from `alice` to `bob`.
- `RENAME|bob|Bobby`: changes the display name of account `bob`.

The following inputs are **not the same error**:

| Input / Situation | Error Category | Explanation |
| --- | --- | --- |
| `null` or blank string | Missing input data | There is no command to decode |
| `TRANSFER|alice|bob` | Invalid syntax/arity | Missing the amount argument |
| `TRANSFER|alice|bob|abc` | Invalid field format | Cannot parse `abc` as a `long` |
| `DEPOSIT|alice|5` | Unsupported command | Verb is not in the known command set |
| `TRANSFER|alice|bob|0` | Invalid argument | Transfers require a positive amount |
| `TRANSFER|alice|alice|10` | Domain rule violation | Cannot transfer to the same account |
| `TRANSFER|alice|missing|10` | Resource not found | Target account does not exist |
| `TRANSFER|alice|bob|1000` | Conflict with current state | Source account has insufficient balance |
| `CREATE|alice|Another|10` | Conflict | Account ID already exists |
| Transferring credits to a `Long.MAX_VALUE` balance | Numeric limit error | Addition would overflow `long` if unchecked |

**The goal** is not simply to "catch every exception and return an error." Instead, we should **classify errors at the right layer**, provide stable responses, keep data unmodified when a command is rejected, and continue processing valid commands.

Since Java 21, **pattern matching for `switch`** (JEP 441) helps dispatchers route typed command variants. When combined with `sealed interface`, `record`, and `when`, we get a readable dispatch table checked for exhaustiveness by the compiler. However, pattern matching **does not validate business rules on its own** and **does not replace transactions, authorization, or error handling**.

## 2. Standard Processing Pipeline: Separating Four Stages

A sound pipeline looks like this:

```text
Untrusted input (CLI / HTTP / message)
    |
    v
[1] Parse: identify verb, field count, data types
    |    Error: BAD_REQUEST or UNKNOWN_COMMAND
    v
[2] Typed Command: Create / Transfer / Rename
    |
    v
[3] Validate + authorize + check domain state
    |    Error: INVALID_ARGUMENT / NOT_FOUND / CONFLICT /
    |           authorization error (in a real system)
    v
[4] Execute within a safe scope
    |    Success: OK
    |    Infrastructure error: handle separately per contract
    v
Reply (result code + appropriate message)
```

**Why separate these stages?**

- The parser only knows **input structure**: verb name, argument count, integer syntax. It should not modify account balances.
- The dispatcher only decides **which command type goes to which handler**. It should not contain database update logic inside `when`.
- The handler knows **business invariants**: whether the account exists, whether credits are positive, whether the balance is sufficient.
- The reply uses stable error codes so CLI/API/clients can handle them consistently.

For real JSON/HTTP, the parser would be a JSON parser + schema validation—**do not use `String.split` to read JSON**. This article uses a minimal text protocol solely to make every layer visible in a standalone Java program.

## 3. Modeling the Command Set with `sealed interface` and `record`

A simple model:

```java
sealed interface Command
        permits Create, Transfer, Rename, Unknown, Malformed {}

record Create(String id, String name, long opening)
        implements Command {}

record Transfer(String from, String to, long credits)
        implements Command {}

record Rename(String id, String name)
        implements Command {}

record Unknown(String verb) implements Command {}
record Malformed(String reason) implements Command {}
```

Meaning of each variant:

| Variant | Role |
| --- | --- |
| `Create` | Parsed command: create a new account |
| `Transfer` | Parsed command: transfer an amount of credits |
| `Rename` | Parsed command: change display name |
| `Unknown` | A verb is present, but it is not supported by the application |
| `Malformed` | Missing verb, wrong argument count, or invalid number format |

Here, `Unknown` and `Malformed` are **internal command variants** so the dispatch path can always represent input errors. This is a **design choice**, not a Java requirement. A larger system might use a `ParseResult` like `Success(Command)`/`Failure(ParseError)` to avoid putting parser errors into the domain hierarchy.

The `Create`, `Transfer`, and `Rename` records are **data carriers**. In this example, they allow holding business-invalid values (such as `credits=0`, `name=""`) so the handler can demonstrate validation. In a different domain model, a constructor or factory could reject invalid values immediately. Either way, preserve a **structured error response path** for clients; do not let an unhandled constructor exception leak across an HTTP/service boundary.

`sealed interface` was standardized in **Java 17 (JEP 409)**, records in **Java 16 (JEP 395)**, and record patterns and pattern switch in their current syntax were both standardized in **Java 21 (JEP 440/441)**.

## 4. Distinguishing Parser Errors from Business Errors

### 4.1. The Parser Must Preserve Empty Fields

For the illustrative `|`-delimited protocol:

```java
String[] parts = raw.split("\\|", -1);
```

- `"TRANSFER|alice|bob|10"` produces four fields.
- `"RENAME|bob|"` must produce **three** fields, where the new name is empty.
- `-1` ensures **trailing empty fields are not discarded**; otherwise, missing fields and empty fields could be conflated.
- `\\|` in a Java string literal creates a regex matching a **literal `|` character**, rather than the regex alternation operator.

Handling the command verb:

```java
String verb = parts[0].strip()
        .toUpperCase(java.util.Locale.ROOT);
```

`Locale.ROOT` normalizes the verb consistently, independent of the machine's default locale. Normalizing `create` to `CREATE`, for example, is an **intentional parser rule**. In a case-sensitive protocol, do not normalize without an explicit contract allowing it.

Demo limitation: **there is no escaping mechanism for `|`** in name values. If names must allow `|`, you need quoting/escaping or a standard format with a proper parser (JSON/Protobuf, etc.). Do not treat the demo format as a production-ready protocol.

### 4.2. The Parser Should Only Catch Predictable Exceptions

Parsing a string to `long`:

```java
try {
    long credits = Long.parseLong(rawCredits);
    return new Transfer(from, to, credits);
} catch (NumberFormatException ex) {
    return new Malformed("invalid number");
}
```

This turns an **external data format error** into a controlled result. It also rejects numeric strings outside the `long` range, such as integers with too many digits.

**Avoid:**

```java
// Illustrative anti-pattern:
// try {
//     return executeEverything();
// } catch (RuntimeException ex) {
//     return "INVALID_COMMAND";
// }
```

Catching `RuntimeException` indiscriminately hides `NullPointerException` from programming bugs, service `IllegalStateException`, database errors, and other unexpected exceptions. A system failure is **not** by default an invalid command. Predictable input errors should be mapped to specific codes, while unexpected errors must be reported/monitored and handled according to the system contract.

### 4.3. Unknown Command vs. Malformed Command

`DEPOSIT|alice|5` looks structurally like a valid command, but the verb `DEPOSIT` is not supported yet. Returning `UNKNOWN_COMMAND:DEPOSIT` is more accurate than `BAD_REQUEST:invalid number` or `NullPointerException`.

By contrast, `TRANSFER|alice|bob` has a **valid verb but wrong arity**, so it returns `BAD_REQUEST:TRANSFER needs 3 arguments`.

In a public API, you may not want to echo back the raw verb sent by the user if it could contain sensitive or malicious data. The demo only uses the normalized verb. In a real system, enforce input length limits, validate character sets, classify errors, and avoid reflecting raw payloads into responses or logs.

## 5. Dispatcher Using Record Patterns and `when` Guards

Once the parser returns a `Command`, Java 21 can dispatch it:

```java
return switch (command) {
    case Create(var id, var name, var opening) ->
            create(state, id, name, opening);

    case Transfer(var from, var to, var credits)
            when credits <= 0 ->
            reply("INVALID_ARGUMENT", "credits must be positive");

    case Transfer(var from, var to, var credits) ->
            transfer(state, from, to, credits);

    case Rename(var id, var name) ->
            rename(state, id, name);

    case Unknown(var verb) ->
            reply("UNKNOWN_COMMAND", verb);

    case Malformed(var reason) ->
            reply("BAD_REQUEST", reason);

    case null ->
            reply("BAD_REQUEST", "null command");
};
```

The snippet above is **part of a method** and assumes the records, handlers, and `state` variable are defined as in the complete program in Section 7.

Key points to understand:

1. `case Create(var id, var name, var opening)` is a **record pattern**, extracting the three components in declaration order.
2. `case Transfer(...) when credits <= 0` is a **guarded record pattern**. The guard is evaluated only after the record pattern matches.
3. The unguarded `Transfer` branch must come **after** the guarded branch; if the general branch comes first, it dominates the specific one and the compiler will report a dominated case.
4. The guard `credits <= 0` does not call a database, write logs, or mutate state. It simply expresses a pure business condition.
5. `case Unknown(...)` and `case Malformed(...)` represent two predictable error kinds.
6. `case null` handles a **null command object passed directly**. This differs from a null raw string, which the parser turns into `Malformed`.
7. There is no `default` because `Command` is a sealed hierarchy whose five variants are all covered; **the compiler reminds you to update the switch** if a new command type is added.

**Important:** Pattern matching handles **dispatch by type and structure**; it does not verify that `id` exists, `name` is valid, or `credits` can be transferred safely. Those checks belong in the handler.

### Null Selector vs. Null Component

`case null` only handles `command == null`. For `new Rename("bob", null)`, the `Rename` selector is non-null, while its `name` component is null; the record pattern `Rename(var id, var name)` still binds the null component, and the handler must check `validName(name)`. Do not expect `case null` to catch nulls inside record components.

If you use a **nested record pattern** to deconstruct a nullable record component, you need an explicit fallback; an exhaustive pattern switch can still throw `MatchException` if no label matches at runtime. The main program intentionally uses shallow record patterns and validates nullable data in handlers.

## 6. Invariants to Check Before Mutating State

### 6.1. Create

Before creating an account:

- `id` is valid under the demo policy: starts with an ASCII lowercase letter `a` to `z`, followed by lowercase letters or digits.
- `name` is non-null and non-blank, at most 40 UTF-16 code units under the example's `String.length()` check.
- `opening >= 0`; negative initial balances are not allowed.
- `id` does not already exist; if duplicated, return `CONFLICT`.

**Only after all checks pass** do we call `state.accounts.put(...)`.

### 6.2. Transfer

Before transferring credits:

- `credits > 0` (checked in the guard).
- Both account IDs are valid and **distinct**.
- Both source and target accounts exist.
- Source balance has enough credits.
- Target balance + transfer amount does not overflow `long`.

Call `Math.addExact(target.credits, credits)` before deducting from the source. If addition overflows, catch `ArithmeticException` **at the exact operation expected to overflow** and return an appropriate business error. In the demo, a target account holding `Long.MAX_VALUE` cannot receive even one more credit.

Validating **before mutating** ensures rejected commands do not leave partial state in this **single-threaded, in-memory example**. However, this is **not an atomic transaction guarantee in a real system**: with concurrency, databases, or external services, you need transactions, locking/optimistic versioning, and proper idempotency design.

### 6.3. Rename

Before renaming:

- `id` is valid, `name` is non-blank.
- The account exists.
- Only then update `account.name`.

When `RENAME|bob|` has an empty name part, the parser still creates `Rename("bob", "")` and the handler returns `INVALID_ARGUMENT:bad name`. This clearly illustrates **valid syntax** (three fields present) versus **contract violation**.

## 7. Complete, Standalone Java 21 Program

The program runs single-threaded with in-memory state to demonstrate the parser → dispatcher → handler pipeline. It is **not a real money management system**: it uses `long` "credits" with no database, authentication, authorization, distributed transactions, or concurrency. Handling real money requires proper currency units, precision, authorization, auditing, and transactional consistency.

Save as **`InvalidCommandDemo.java`**:

```java
public class InvalidCommandDemo {
    sealed interface Command
            permits Create, Transfer, Rename, Unknown, Malformed {}

    record Create(String id, String name, long opening)
            implements Command {}

    record Transfer(String from, String to, long credits)
            implements Command {}

    record Rename(String id, String name) implements Command {}
    record Unknown(String verb) implements Command {}
    record Malformed(String reason) implements Command {}

    record Reply(String code, String detail) {
        @Override
        public String toString() {
            return code + ":" + detail;
        }
    }

    static final class Account {
        String name;
        long credits;

        Account(String name, long credits) {
            this.name = name;
            this.credits = credits;
        }
    }

    static final class State {
        final java.util.Map<String, Account> accounts =
                new java.util.LinkedHashMap<>();

        State() {
            accounts.put("alice", new Account("Alice", 100));
            accounts.put("bob", new Account("Bob", 20));
        }
    }

    static Command parse(String raw) {
        if (raw == null || raw.isBlank()) {
            return new Malformed("empty input");
        }

        String[] parts = raw.split("\\|", -1);
        String verb = parts[0].strip()
                .toUpperCase(java.util.Locale.ROOT);

        if (verb.isEmpty()) {
            return new Malformed("missing verb");
        }

        return switch (verb) {
            case "CREATE" -> {
                if (parts.length != 4) {
                    yield new Malformed(
                            "CREATE needs 3 arguments");
                }
                try {
                    yield new Create(
                            parts[1].strip(),
                            parts[2].strip(),
                            Long.parseLong(parts[3].strip()));
                } catch (NumberFormatException ex) {
                    yield new Malformed("invalid number");
                }
            }

            case "TRANSFER" -> {
                if (parts.length != 4) {
                    yield new Malformed(
                            "TRANSFER needs 3 arguments");
                }
                try {
                    yield new Transfer(
                            parts[1].strip(),
                            parts[2].strip(),
                            Long.parseLong(parts[3].strip()));
                } catch (NumberFormatException ex) {
                    yield new Malformed("invalid number");
                }
            }

            case "RENAME" ->
                    parts.length == 3
                            ? new Rename(
                                    parts[1].strip(),
                                    parts[2].strip())
                            : new Malformed(
                                    "RENAME needs 2 arguments");

            default -> new Unknown(verb);
        };
    }

    static Reply reply(String code, String detail) {
        return new Reply(code, detail);
    }

    static boolean validId(String id) {
        return id != null && id.matches("[a-z][a-z0-9]*");
    }

    static boolean validName(String name) {
        return name != null
                && !name.isBlank()
                && name.length() <= 40;
    }

    static Reply dispatch(State state, Command command) {
        java.util.Objects.requireNonNull(state, "state");

        return switch (command) {
            case Create(var id, var name, var opening) ->
                    create(state, id, name, opening);

            case Transfer(var from, var to, var credits)
                    when credits <= 0 ->
                    reply(
                            "INVALID_ARGUMENT",
                            "credits must be positive");

            case Transfer(var from, var to, var credits) ->
                    transfer(state, from, to, credits);

            case Rename(var id, var name) ->
                    rename(state, id, name);

            case Unknown(var verb) ->
                    reply("UNKNOWN_COMMAND", verb);

            case Malformed(var reason) ->
                    reply("BAD_REQUEST", reason);

            case null ->
                    reply("BAD_REQUEST", "null command");
        };
    }

    static Reply create(
            State state, String id, String name, long opening) {
        if (!validId(id)) {
            return reply("INVALID_ARGUMENT", "bad id");
        }
        if (!validName(name)) {
            return reply("INVALID_ARGUMENT", "bad name");
        }
        if (opening < 0) {
            return reply(
                    "INVALID_ARGUMENT",
                    "opening must be nonnegative");
        }
        if (state.accounts.containsKey(id)) {
            return reply("CONFLICT", "account exists");
        }

        state.accounts.put(id, new Account(name, opening));
        return reply("OK", "created " + id);
    }

    static Reply transfer(
            State state, String from, String to, long credits) {
        if (!validId(from) || !validId(to)) {
            return reply("INVALID_ARGUMENT", "bad id");
        }
        if (from.equals(to)) {
            return reply(
                    "INVALID_ARGUMENT",
                    "accounts must differ");
        }

        Account source = state.accounts.get(from);
        Account target = state.accounts.get(to);

        if (source == null || target == null) {
            return reply("NOT_FOUND", "account missing");
        }
        if (source.credits < credits) {
            return reply("CONFLICT", "insufficient balance");
        }

        long newTarget;
        try {
            newTarget = Math.addExact(target.credits, credits);
        } catch (ArithmeticException ex) {
            return reply("CONFLICT", "balance overflow");
        }

        source.credits -= credits;
        target.credits = newTarget;

        return reply("OK", "transferred " + credits);
    }

    static Reply rename(State state, String id, String name) {
        if (!validId(id)) {
            return reply("INVALID_ARGUMENT", "bad id");
        }
        if (!validName(name)) {
            return reply("INVALID_ARGUMENT", "bad name");
        }

        Account target = state.accounts.get(id);
        if (target == null) {
            return reply("NOT_FOUND", "account missing");
        }

        target.name = name;
        return reply("OK", "renamed " + id);
    }

    static java.util.Map<String, String> snapshot(State state) {
        java.util.Map<String, String> copy =
                new java.util.LinkedHashMap<>();

        state.accounts.forEach((id, account) ->
                copy.put(
                        id,
                        account.name + "/" + account.credits));

        return copy;
    }

    static void check(
            State state,
            String label,
            String raw,
            String expected) {
        var before = snapshot(state);
        Reply result = dispatch(state, parse(raw));

        if (!result.toString().equals(expected)) {
            throw new AssertionError(
                    label + ": expected " + expected
                            + ", got " + result);
        }

        if (!result.code().equals("OK")
                && !before.equals(snapshot(state))) {
            throw new AssertionError(
                    label + ": rejected command changed state");
        }

        System.out.println(label + " => " + result);
    }

    public static void main(String[] args) {
        State state = new State();

        check(state, "null-text", null,
                "BAD_REQUEST:empty input");
        check(state, "blank", " ",
                "BAD_REQUEST:empty input");
        check(state, "no-verb", "|alice",
                "BAD_REQUEST:missing verb");
        check(state, "unknown", "DEPOSIT|alice|4",
                "UNKNOWN_COMMAND:DEPOSIT");
        check(state, "arity", "TRANSFER|alice|bob",
                "BAD_REQUEST:TRANSFER needs 3 arguments");
        check(state, "number", "TRANSFER|alice|bob|foo",
                "BAD_REQUEST:invalid number");
        check(state, "zero", "TRANSFER|alice|bob|0",
                "INVALID_ARGUMENT:credits must be positive");
        check(state, "negative", "TRANSFER|alice|bob|-5",
                "INVALID_ARGUMENT:credits must be positive");
        check(state, "same", "TRANSFER|alice|alice|10",
                "INVALID_ARGUMENT:accounts must differ");
        check(state, "not-found", "TRANSFER|alice|nobody|1",
                "NOT_FOUND:account missing");
        check(state, "insufficient",
                "TRANSFER|alice|bob|1000",
                "CONFLICT:insufficient balance");
        check(state, "blank-name", "CREATE|carol| |10",
                "INVALID_ARGUMENT:bad name");
        check(state, "duplicate",
                "CREATE|alice|Another|10",
                "CONFLICT:account exists");

        check(state, "create", "CREATE|carol|Carol|30",
                "OK:created carol");
        check(state, "transfer",
                "TRANSFER|alice|bob|40",
                "OK:transferred 40");
        check(state, "rename", "RENAME|bob|Bobby",
                "OK:renamed bob");

        check(state, "rename-bad", "RENAME|bob|",
                "INVALID_ARGUMENT:bad name");
        check(state, "rename-missing",
                "RENAME|ghost|Ghost",
                "NOT_FOUND:account missing");
        check(state, "huge-create",
                "CREATE|huge|Huge|9223372036854775807",
                "OK:created huge");
        check(state, "overflow",
                "TRANSFER|alice|huge|1",
                "CONFLICT:balance overflow");

        Reply directNull = dispatch(state, null);
        if (!directNull.toString()
                .equals("BAD_REQUEST:null command")) {
            throw new AssertionError("null command");
        }

        System.out.println("direct-null => " + directNull);
        System.out.println("final=" + snapshot(state));
    }
}
```

Compile and run on **JDK 21+** without preview flags:

```bash
javac --release 21 InvalidCommandDemo.java
java InvalidCommandDemo
```

**Exact stdout:**

```text
null-text => BAD_REQUEST:empty input
blank => BAD_REQUEST:empty input
no-verb => BAD_REQUEST:missing verb
unknown => UNKNOWN_COMMAND:DEPOSIT
arity => BAD_REQUEST:TRANSFER needs 3 arguments
number => BAD_REQUEST:invalid number
zero => INVALID_ARGUMENT:credits must be positive
negative => INVALID_ARGUMENT:credits must be positive
same => INVALID_ARGUMENT:accounts must differ
not-found => NOT_FOUND:account missing
insufficient => CONFLICT:insufficient balance
blank-name => INVALID_ARGUMENT:bad name
duplicate => CONFLICT:account exists
create => OK:created carol
transfer => OK:transferred 40
rename => OK:renamed bob
rename-bad => INVALID_ARGUMENT:bad name
rename-missing => NOT_FOUND:account missing
huge-create => OK:created huge
overflow => CONFLICT:balance overflow
direct-null => BAD_REQUEST:null command
final={alice=Alice/60, bob=Bobby/60, carol=Carol/30, huge=Huge/9223372036854775807}
```

The program was verified with **JDK 24 JShell**, using Java 21 syntax and producing 22 lines of stdout. The `check` method asserts both the expected `Reply` and that the before/after state snapshots match whenever a command does **not** return `OK`. If a check diverges, it throws `AssertionError` instead of printing a false success line.

The final balances confirm the behavior: initially `alice=100` and `bob=20`; a valid transfer of 40 credits yields `alice=60`, `bob=60`; a valid rename yields `Bobby`; and transferring 1 credit to an account at `Long.MAX_VALUE` is rejected, leaving `huge` unchanged.

## 8. Detailed Analysis of Error Paths in the Program

### 8.1. `null`/Blank String vs. `null` Command Object

`parse(null)` returns `Malformed("empty input")` because the parser received and classified a raw string with no content. By contrast, `dispatch(state, null)` receives a **`null` command reference** directly, matches `case null`, and returns `BAD_REQUEST:null command`.

Both fail, but they travel through **two different paths**. Distinguishing them is useful when debugging the transport layer versus the typed command handling layer.

### 8.2. Wrong Arity and Invalid Number Format

`TRANSFER|alice|bob` is rejected **before** attempting to read `parts[3]`. This prevents an `ArrayIndexOutOfBoundsException` caused by an unchecked parser.

`TRANSFER|alice|bob|foo` has the right number of arguments, but the fourth value is not a `long`; `NumberFormatException` is intentionally converted to `Malformed("invalid number")`.

An input like `TRANSFER|alice|bob|999999999999999999999999999999` also triggers a format error because it exceeds the `long` range.

### 8.3. Guard for Non-Positive Credits

`case Transfer(...) when credits <= 0` handles 0 and negative amounts before invoking the transfer handler. No authorization or account lookup is needed to know that non-positive credits violate the contract.

In another domain, the error ordering might be designed differently for security or API contract reasons. For instance, an unauthenticated caller should not be able to probe error messages to enumerate which accounts exist. **The demo program has no authentication/authorization**; in production, authentication and authorization must be enforced at the appropriate boundary before revealing sensitive details.

### 8.4. Account Not Found and Insufficient Balance

`TRANSFER|alice|nobody|1` has valid structure and amount, but the target account does not exist. Returning `NOT_FOUND` distinguishes it from `INVALID_ARGUMENT`.

`TRANSFER|alice|bob|1000` has valid accounts, but `alice` only has 100 credits. It returns `CONFLICT:insufficient balance` without modifying balances. Using `CONFLICT` here is a **demo convention**; in a real API, define business error codes and corresponding HTTP statuses according to your contract.

### 8.5. Overflow When Adding to Target Balance

The statement:

```java
long newTarget;
try {
    newTarget = Math.addExact(target.credits, credits);
} catch (ArithmeticException ex) {
    return reply("CONFLICT", "balance overflow");
}
```

computes the new target balance **before modifying** the source. `Math.addExact` checks for signed integer overflow instead of letting `long` silently wrap around into negative values. In the test, `huge` holds `Long.MAX_VALUE`; adding 1 throws `ArithmeticException`, which is turned into a controlled reply. Both source and target balances remain untouched.

This works well for a simple integer model. For concurrent reward points or real money, you must have total-balance checks, limit policies, transactions, and explicit unit precision; **do not assume this is a safe financial system**.

## 9. Exhaustiveness: Why No `default` Is Needed

The command set is defined as:

```java
sealed interface Command
        permits Create, Transfer, Rename, Unknown, Malformed {}
```

The dispatcher handles every variant plus `case null`. With a **`switch` expression on `Command`**, Java 21 can verify that the cases are exhaustive. If you add `record Suspend(String id) implements Command` and update `permits`, `dispatch` will require handling `Suspend` at compile time unless a catch-all pattern covers everything.

This is a helpful safeguard against forgetting a new command. Avoid adding `default -> reply("UNKNOWN_COMMAND", "...")` to every sealed switch just to silence missing-case compiler errors: doing so can hide a **declared variant that has not been implemented yet**.

**`UnknownCommand` is not `default`.** Here, `Unknown` is a **concrete typed record** created by the parser when encountering an unsupported verb. Therefore:

- `Unknown("DEPOSIT")` handles an unregistered raw verb.
- `Suspend` is a **new Java subtype of `Command`** that must be designed and given a handler.
- `null` is an empty selector, with its own case label.

If the domain allows external plugins to define `Command` subtypes, `sealed` may not fit; a registry/visitor or an open interface with a fallback may be needed instead. That is an **architectural decision**, not a limitation of record patterns.

### `MatchException` Is Different from `BAD_REQUEST`

An exhaustive `switch` can throw `MatchException` if a class hierarchy changes after the client was compiled or if a nested pattern fails to match at runtime despite compile-time exhaustiveness. That is **not** a normal `BAD_REQUEST` reply. You should investigate the build environment, library versions, and pattern completeness rather than catching `MatchException` and silently treating it as bad input.

In this program, the dispatcher avoids nested record patterns on nullable components and uses `Malformed`/`Unknown` records for expected errors; thus, ordinary input errors are returned as `Reply` values without relying on exceptions for control flow.

## 10. Error Model: Returning Stable Codes Without Leaking Internal Details

The demo's `Reply(String code, String detail)` is enough for illustration, but a real API should use a data type with a clear contract:

```java
// Design illustration, not a direct drop-in replacement for the demo.
enum ErrorCode {
    BAD_REQUEST,
    UNKNOWN_COMMAND,
    INVALID_ARGUMENT,
    NOT_FOUND,
    CONFLICT,
    FORBIDDEN,
    INTERNAL_ERROR
}

record ApiError(
        ErrorCode code,
        String message,
        String correlationId) {}
```

**Principles:**

- **Code** is stable, machine-readable, and independent of display language.
- **Message** is clear enough for callers, without containing stack traces, SQL queries, tokens, or sensitive account details.
- **Correlation ID** links the response to server logs/tracing without exposing internals.
- **Unexpected exceptions** are logged/monitored safely and mapped to an appropriate system error, never lumped into `INVALID_ARGUMENT`.
- You can add a list of per-field violations (`field`, `reason`) for forms/JSON so callers avoid parsing free-form messages.
- Domain error codes **do not have to map 1:1** to HTTP status codes; HTTP mapping belongs in the API adapter.

A common API mapping **for reference only**: malformed payload → HTTP 400; forbidden → 403; resource not found → 404; conflict → 409. Real endpoints also use 401 (authentication), 422 (validation), or choose not to disclose resource existence. Do not copy this mapping into production without reviewing your security policy and client compatibility.

### Should You Use an `enum` for Error Codes?

Yes, if you want the compiler to check valid codes. `Reply` uses strings to keep the example short; `enum ErrorCode` or sealed result types eliminate typos. Another variant:

```java
sealed interface Outcome permits Success, Failure {}
record Success(String message) implements Outcome {}
record Failure(ErrorCode code, String message)
        implements Outcome {}
```

You can then `switch` on `Outcome` to map to an HTTP/gRPC/CLI response. Still, avoid over-engineering hierarchies when a small `record Reply` already meets your needs.

## 11. Side Effects, Transactions, and Race Conditions

Validating input correctly **does not guarantee safe updates under concurrency**.

In the demo:

```java
if (source.credits < credits) {
    return reply("CONFLICT", "insufficient balance");
}
long newTarget = Math.addExact(target.credits, credits);
source.credits -= credits;
target.credits = newTarget;
```

These four steps have no transaction or lock. If two threads concurrently read the same `source.credits`, both can see sufficient balance and both deduct, causing a **lost update** or violating invariants. In a database-backed system:

- Use **transactions** for updates that must be atomic.
- Apply optimistic locking (version column) or appropriate locking.
- Check the balance against protected state and perform conditional updates.
- Require an **idempotency key** for commands that may be retried, especially credit/money transfers.
- Do not emit events, emails, or notifications before the transaction commits in an uncontrolled way. Consider the transactional outbox pattern if consistency between the DB and message broker is required.
- Distinguish **non-retryable invalid errors** from **transient retryable errors** by policy.

These requirements are beyond what a `switch` pattern can do. Pattern matching makes routing clearer; it does not magically make account updates atomic.

## 12. Authorization, Input Limits, and Data Safety

A command that is well-typed and has a valid payload **may still be unauthorized**.

For example, `RENAME|bob|Bobby` is completely valid syntactically, yet the caller might not own account `bob`. In a real service, check permissions before modifying data.

Key areas to implement:

1. **Authentication:** Who is the caller? Do they have a valid token/session?
2. **Authorization:** Which accounts is the caller allowed to create, transfer from, or rename?
3. **Input limits:** Maximum bytes/characters for raw payloads, field counts, and ID/name lengths to prevent resource exhaustion.
4. **Canonicalization:** If normalizing case, Unicode, or whitespace, keep it consistent across validation, storage, and uniqueness checks.
5. **Sensitive data:** Do not log raw payloads containing credentials/PII; log only necessary metadata.
6. **Rate limits and quotas:** Prevent command spam, including rejected commands.
7. **Replay/duplicate protection:** Commands with side effects need request IDs to detect retries.
8. **Boundary validation:** JSON deserialization can produce nulls, unknown enums, or missing fields regardless of what the compiler sees in a sealed model.

Do not confuse regex `validId` checks with authorization. Regex checks **ID format**, not permission to act on that ID.

## 13. Matrix-Based Testing for Invalid Commands

A good test suite does more than check the "happy path." Organize tests by category:

| Test Category | Examples | Invariant |
| --- | --- | --- |
| Parse | Raw null, blank, missing verb | Returns `BAD_REQUEST`, no unexpected exceptions |
| Arity | Missing or extra arguments | No out-of-bounds array access |
| Numeric | `foo`, numbers exceeding `long` range | Parser returns a format error |
| Unknown verb | Unsupported `DEPOSIT` | Returns `UNKNOWN_COMMAND`, not treated as Create/Transfer |
| Boundary | `credits=0`, `-1`, `1` | Positive boundary is enforced accurately |
| Domain state | Duplicate account, missing account, insufficient balance | Error codes are clearly distinguished |
| Numeric overflow | Adding to `Long.MAX_VALUE` | No wrap-around, balances unchanged |
| Null component | `new Rename("bob", null)` | Handler safely returns `INVALID_ARGUMENT` |
| Null selector | `dispatch(state, null)` | `case null` handles it properly |
| Side effects | Failed commands | Before/after snapshots match |
| Success | Create, Transfer, Rename | Only intended accounts/fields change |
| Extensibility | Adding a command subtype | Compiler/tests prompt updating the dispatcher |

For tests with real side effects, use a **fake repository or database transaction rollback**; never run real money transfers twice to compare. Parser unit tests should be independent of handlers, and integration tests should cover concurrency/retries if the system supports them.

### Useful Properties

- **No state mutation on rejection:** For every command returning a code other than `OK`, the resulting state must equal the initial state (under defined conditions).
- **Total balance conservation:** For a successful Transfer between two distinct accounts, the sum of both accounts' credits remains constant (assuming no fees and no overflow).
- **Parser idempotency:** Parsing a given raw command produces an equivalent structure when no time/randomness is involved.
- **No unexpected exceptions:** Across the supported and expected invalid raw input domain, the parser returns a command/error instead of indexing out of bounds or leaking `NumberFormatException`.
- **No data mutation on `Unknown`/`Malformed`:** Any `Unknown`/`Malformed` command must never update the repository.
- **Exhaustiveness:** Adding a new `Command` subtype must require updating the dispatcher and tests.

**Caution:** "No error ever throws" is too broad a property. Bugs or unexpected infrastructure failures may need exceptions or higher-level failure handling; do not swallow them just to make tests pass.

## 14. Common Pitfalls and How to Avoid Them

1. **Using a single `default` for all commands:** Hides missing handlers when adding a new subtype to a sealed interface.
2. **Conflating unknown verbs with malformed payloads:** Callers cannot tell whether to fix syntax or change the command type.
3. **Catching `RuntimeException` and returning `INVALID_COMMAND`:** Masks programming/infrastructure bugs as user errors.
4. **Putting database writes or event emission inside `when`:** A guard may run even when the branch is not taken, leaving side effects behind.
5. **Placing an unguarded `Transfer` branch before `when credits <= 0`:** Causes domination or skips the specialized check.
6. **Assuming `case null` catches nulls inside every record component:** Selector null and component null are two separate levels.
7. **Calling `String.split("\\|")` without `-1`:** Drops trailing empty fields and misclassifies errors.
8. **Calling `Long.parseLong` without catching the right exception:** Turns invalid input into an exception outside the API contract.
9. **Deducting from the source balance before checking target overflow:** Can leave inconsistent state upon rejection.
10. **Assuming pre-mutation validation suffices for concurrency:** Multiple threads can still read stale state simultaneously; use transactions/locking.
11. **Confusing `validId` with authorization:** An ID matching a regex does not mean the caller owns or may access it.
12. **Logging raw commands or returning exception details to clients:** Leaks sensitive data and internal details.
13. **Omitting input length limits:** Even a simple parser can exhaust resources on huge payloads.
14. **Assuming record constructors validate automatically:** Records have no invariants unless you explicitly write them.
15. **Using `long` for real money without defining units/precision/overflow:** Insufficient for financial applications.
16. **Returning `NOT_FOUND` for every error:** Deprives clients of the distinction between validation, conflict, and missing resources.
17. **Using a record's `toString()` as a data protocol:** Record output can change with schema changes and is not a stable wire format.
18. **Using pattern matching to replace the entire error-handling architecture:** Patterns are a dispatch tool, not a transaction manager or security boundary.

## 15. Pre-Merge Checklist

- [ ] Clearly distinguish parser errors, unknown commands, invalid arguments, domain conflicts, not found, and system failures.
- [ ] Is the `Command` type hierarchy intentionally sealed and covering all current variants?
- [ ] Do record patterns and `when` only express clear matching/conditions without hiding side effects?
- [ ] Does `case null` handle a null selector while null components are validated in handlers?
- [ ] Does the parser check field count **before** indexing arrays and use `split(..., -1)` when trailing empty fields matter?
- [ ] Does numeric parsing catch `NumberFormatException` at the right layer with a stable error message?
- [ ] Are input limits, normalization policies, schemas, and encodings properly defined?
- [ ] Does the handler validate fully before mutation, check arithmetic overflow, and distinguish business conflicts?
- [ ] Does the real system include authentication, authorization, transactions, locking, and idempotency where needed?
- [ ] Do tests verify that rejected commands leave state unchanged?
- [ ] Do tests cover boundary values, unknown verbs, malformed arguments, null components, and null commands?
- [ ] Do error responses omit stack traces/secrets and include a correlation ID when needed?
- [ ] When adding a command subtype, were the dispatcher, parser, permissions, schema, and tests all updated?

**Conclusion:** Handling invalid commands starts with **classifying errors at the right layer**. Java 21 `sealed` + `record` + `switch` patterns make dispatchers readable and exhaustive; `when` is best kept to simple, pure guards. The parser should turn malformed syntax into predictable results, handlers must enforce domain rules **before causing side effects**, and concurrency/security/transactions remain separate responsibilities. That way, invalid commands are rejected cleanly without corrupting state or hiding system failures.

### References

- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 409 — Sealed Classes: https://openjdk.org/jeps/409
- OpenJDK JEP 395 — Records: https://openjdk.org/jeps/395
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java 21 API — `Long.parseLong`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Long.html#parseLong(java.lang.String)
- Oracle Java 21 API — `Math.addExact`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html#addExact(long,long)
