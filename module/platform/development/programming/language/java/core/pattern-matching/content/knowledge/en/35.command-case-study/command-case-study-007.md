# Safely Adding a New Command

## 1. The problem: adding a command without breaking existing behavior

In a task management application, a **command** represents a request to perform an action: creating a task, renaming it, marking it as completed, or archiving it. Unlike an event, which describes something that **has already happened**, a command expresses something **requested to happen**; it can be rejected due to insufficient permissions, invalid data, or a current state that does not allow it.

Suppose the first version supports:

- `CreateTask`: creates a task.
- `RenameTask`: renames a task.
- `CompleteTask`: marks a task as completed.

The next version needs to add `ArchiveTask`, but archiving is only allowed for the **ADMIN** role and must not process an already-archived task. This is not just a matter of adding a record:

1. **Define the new command** with a clear structure and validation.
2. **Extend the set of permitted commands** in the domain model.
3. **Force dispatchers to handle the new command**, rather than silently falling into `default`.
4. **Check permissions before changing state**.
5. **Preserve state transition rules** and avoid performing half the work before detecting an error.
6. **Test the new command alongside the existing ones**, including invalid data, unauthorized access, and repeated requests.
7. **Assess compatibility** with APIs, stored data, message queues, and independently released modules.

Since **Java 21**, a `sealed interface` combined with **record patterns** and **pattern matching for `switch`** provides a clear way to express these requirements, especially when the command set is managed within a single module.

**Core principle:** Safely adding a command does not mean merely making the program compile. It means **the new command is properly recognized, checked for permissions and data validity, and mutates state according to contract, while not changing the meaning of existing commands**.

## 2. Modeling commands with a sealed interface

### Initial version

```java
sealed interface TaskCommand
        permits CreateTask, RenameTask, CompleteTask {}

record CreateTask(String id, String title)
        implements TaskCommand {}

record RenameTask(String id, String newTitle)
        implements TaskCommand {}

record CompleteTask(String id)
        implements TaskCommand {}
```

This is a declarative example to explain the design; **there is no validation yet**. Each command is a **record** holding the data needed for a business intent.

Using a `sealed interface` has the following benefits:

- The set of permitted **direct** subtypes is explicitly defined in `permits`.
- Records are `final`, so in this model the command branches cannot be further subclassed.
- Consumers of the command can use a `switch expression` and let the compiler check **exhaustiveness**.
- A module cannot arbitrarily add a direct implementation of `TaskCommand` unless it belongs to the permitted set.

With a **named module**, direct subtypes listed in `permits` must reside in the same module as the sealed type; with an **unnamed module**, they must be in the same package. The nested declarations inside the class in the full runnable example later satisfy this organizational constraint.

### Adding ArchiveTask

When the archiving requirement arrives, we update the contract:

```java
sealed interface TaskCommand
        permits CreateTask, RenameTask, CompleteTask, ArchiveTask {}

record ArchiveTask(String id) implements TaskCommand {}
```

This is the **extended form**; do not place both `TaskCommand` declarations in the same file. The `ArchiveTask` record only needs `id` because its intent is to transition an existing task into the archived state.

Safety does not lie in the `permits` clause alone. **Every place that decides how commands are executed** also needs to be evaluated: command dispatchers, permission checks, validation, auditing, tests, serialization, and API consumers.

## 3. Exhaustiveness: letting the compiler catch unhandled new commands

Suppose the handler in the initial version is:

```java
static String execute(TaskCommand command) {
    return switch (command) {
        case CreateTask create -> createTask(create);
        case RenameTask rename -> renameTask(rename);
        case CompleteTask complete -> completeTask(complete);
        case null -> throw new IllegalArgumentException(
                "command must not be null");
    };
}
```

The snippet above is **illustrative**: the `createTask`, `renameTask`, and `completeTask` methods are not declared in this snippet. It demonstrates a `switch expression` over a closed hierarchy.

When `TaskCommand` only `permits` the three old subtypes, the Java 21 compiler has enough information to verify all non-null branches. However, after adding `ArchiveTask` to `permits`, the handler above **no longer covers all subtypes** and will fail to compile as non-exhaustive when recompiled.

This is a useful signal: the team must decide how `ArchiveTask` should be handled, instead of letting the runtime arbitrarily execute a generic fallback.

### Anti-pattern: adding default just to “silence the compiler error”

```java
return switch (command) {
    case CreateTask create -> createTask(create);
    case RenameTask rename -> renameTask(rename);
    case CompleteTask complete -> completeTask(complete);
    case null -> throw new IllegalArgumentException("Missing command");
    default -> "IGNORED";
};
```

This snippet is also illustrative with undefined helper methods. A `default -> "IGNORED"` causes `ArchiveTask` to produce no archiving behavior; if the caller interprets `"IGNORED"` as a successful outcome, the bug becomes even harder to detect.

**Not every `default` is bad**: for an **open** command extension point or a gateway that must reject unsupported types, `default -> throw new UnsupportedOperationException(...)` can be the right policy. However, in a sealed hierarchy used to model a finite set of commands, it is usually better to **list the business cases explicitly** and not hide the signal of missing handling.

## 4. Record patterns and the dispatcher after adding a command

Since Java 21, a handler can deconstruct records directly in `case`:

```java
static String execute(TaskCommand command, Role role) {
    if (role == null) {
        throw new IllegalArgumentException("role must not be null");
    }

    return switch (command) {
        case CreateTask(String id, String title) ->
                create(id, title);

        case RenameTask(String id, String newTitle) ->
                rename(id, newTitle);

        case CompleteTask(String id) ->
                complete(id);

        case ArchiveTask(String id) when role != Role.ADMIN ->
                throw new SecurityException(
                        "Only ADMIN may archive");

        case ArchiveTask(String id) ->
                archive(id);

        case null ->
                throw new IllegalArgumentException(
                        "command must not be null");
    };
}
```

This is an **illustrative snippet in the domain context**: `Role` and the four operation methods will be defined in the standalone program in Section 9.

Notable points:

- `CreateTask(String id, String title)` is a **record pattern**: it checks the subtype and extracts component values without needing `(CreateTask) command`.
- `ArchiveTask(String id) when role != Role.ADMIN` is a **guarded pattern**. The `when` clause is only evaluated after the record pattern matches.
- When the user lacks permission, the guarded branch throws `SecurityException` **before calling `archive(id)`**, so no archiving operation occurs on that branch.
- The unguarded `case ArchiveTask(String id)` must appear **after** the permission-checking branch to handle authorized cases.
- `case null` explicitly defines the null-command policy. It is **not synonymous** with `default`.
- Because every subtype of `TaskCommand` is covered, the expression does not need a `default` branch.

**Be careful with the source of `role`:** in a real application, permissions must be determined from a **server-authenticated identity or trusted security context**, not by trusting a `"ADMIN"` string sent directly by the client. The `role` parameter in this case study is simply data already resolved at the calling layer, used to illustrate authorization logic.

### When to use a type pattern instead of a record pattern?

If a command has many components or needs to be passed whole to a service, a type pattern can be more readable:

```java
case CreateTask create -> createService.execute(create);
```

This is a conceptual snippet assuming `createService` exists. It is not mandatory to deconstruct every component in every case. Use a record pattern when seeing the `id` and `title` fields directly makes the policy clearer.

## 5. Validate commands right at the entry point

You should not wait until the task-storage map throws an error to notice an empty `id` or a null `title`.

A record can use a **compact constructor** to validate its fields:

```java
record CreateTask(String id, String title)
        implements TaskCommand {
    CreateTask {
        requireNonBlank(id, "id");
        requireNonBlank(title, "title");
    }
}
```

This snippet assumes `requireNonBlank` is defined in the same scope (for example, as a static method of the class enclosing the record), like in the full program below.

The validation helper:

```java
static void requireNonBlank(String text, String field) {
    if (text == null || text.isBlank()) {
        throw new IllegalArgumentException(
                field + " must not be blank");
    }
}
```

Do the same for `RenameTask`, `CompleteTask`, and `ArchiveTask` to ensure that normally constructed commands have a non-null `id` that is not just whitespace.

**Distinguish two validation layers:**

1. **Syntactic/structural validation at the command:** `id` must not be blank, `title` must have content, and values must be within allowed ranges.
2. **State validation at the handler:** whether the task exists, whether it is already archived, whether it is already completed, and whether the caller has permission.

Do not put a rule like “the ID must exist in the database” into a record constructor if that rule depends on external state. The constructor should validate the intrinsic invariants of the command data; business state checks should happen during controlled execution.

### Record patterns and null components

`case CreateTask(String id, String title)` uses **`String` sub-type patterns**. In Java 21, a `null` component does not match a `String` type pattern. In the program below, the compact constructor proactively rejects null, so validly constructed commands have no null components.

If receiving data from an untrusted channel, validate during decoding/deserialization rather than assuming pattern matching will automatically fix invalid components. In another model where null is allowed, you can use `var` with explicit null checks or add a broader subtype branch; do not let a command that is valid by type be skipped because a record pattern failed to match a component.

## 6. Business safety: permissions, state, and mutation

Suppose the task data consists of:

```java
record Task(
        String id,
        String title,
        boolean completed,
        boolean archived) {}
```

Rules in this case study:

- **CreateTask:** create only if `id` does not yet exist.
- **RenameTask:** rename only if the task exists and is not archived.
- **CompleteTask:** complete only if the task exists, is not archived, and is not yet completed.
- **ArchiveTask:** only ADMIN may invoke; the task must exist and not be archived. An already-completed task can still be archived.

These rules are an **illustrative contract**. Another application might allow repeated completion as an idempotent operation, or only allow archiving after completion; in that case, a different contract must be defined and tested—changing `switch` syntax alone is not enough.

### Check before writing state

A rename operation should follow this order:

1. Look up the task by `id`.
2. Reject if it does not exist or is already archived.
3. Create a new `Task` instance with the updated title.
4. Persist the state in a controlled operation.

Do not write:

```java
// Dangerous idea: partially update before checking.
store.put(id, new Task(id, newTitle, false, false));
if (!isAllowedToRename(id)) {
    throw new SecurityException("Denied");
}
```

The names `store` and `isAllowedToRename` are illustrative. By the time the exception is thrown, the data has already been mutated; **throwing an exception does not automatically roll back an in-memory mutation**.

For systems using a database, the check-and-write process must account for **transactions, isolation, or optimistic locking** to prevent race conditions between reading and updating. A `HashMap` or `LinkedHashMap` used in a demo does not provide those guarantees under multiple threads or multiple servers.

### Permission checks before side effects

In the handler, the permission-guarded case precedes the executing `ArchiveTask` case. This structure makes the required permission for the new command obvious to the reader. In a real application, authorization checks should be placed at the trust boundary and repeated in the application service if needed, rather than relying on a UI that merely hides the archive button.

### Errors must be meaningful

Distinguish between:

- `IllegalArgumentException`: invalid command or a reference to a non-existent ID under the example contract.
- `IllegalStateException`: the task exists, but its current state does not allow the operation.
- `SecurityException`: the caller is not permitted to archive.

These generic exceptions can be replaced with a **domain error/result type** if the API needs to return stable error codes or support client recovery. There is no reason for errors to be turned into `"OK"` or `default -> ""`.

## 7. Do not confuse compiler exhaustiveness with runtime safety

With a sealed hierarchy, a `switch expression` without `default` helps catch cases where a subtype is added without updating all branches **in recompiled modules**.

However:

- The compiler does not know permission and state rules that live outside the type system.
- `sealed` does not guarantee that an ID exists, that a title is meaningful, or that the caller is authenticated.
- A new command can be syntactically valid yet execute the wrong side effect if the handler lacks proper transaction handling.
- If modules are built/released out of sync, an older compiled switch may encounter a new subtype at runtime; compatibility must be managed, and `MatchException` can occur when the hierarchy no longer matches compile-time assumptions.
- When sending commands over the network, payloads can also have differing versions/schemas; a single module's Java type system does not automatically keep a distributed system's versions in sync.

**Takeaway:** exhaustiveness is an **additional safety guardrail**, not a replacement for validation, authorization, testing, data consistency mechanisms, and release processes.

## 8. Step-by-step roadmap for adding a new command

A real-world change can be reviewed in the following sequence:

### Step 1 — Finalize the command's semantics

For `ArchiveTask`, define: who can archive, when, for what purpose, whether it is reversible, what repeated archiving returns, and what error outcomes are published.

Avoid vague definitions like “archive is a status update” because they obscure critical constraints.

### Step 2 — Add the record with minimal data

`record ArchiveTask(String id) implements TaskCommand` represents a clear action. If business logic also needs `reason` or `requestedAt`, consider whether that data should be present on the command from the start. Do not let the handler pull important information from uncontrolled global variables.

### Step 3 — Update sealed permits

Add the direct subtype to `TaskCommand` and ensure it is in the appropriate module/package. Because records are final, there is no need to branch with `non-sealed`.

### Step 4 — Compile to find missing cases

Run the build, paying attention to `switch expressions` over `TaskCommand`. Places without `default` can be flagged by the compiler as not handling the new subtype.

Do not mechanically patch them with a generic `default`. For each consumer, decide whether `ArchiveTask` should be executed, logged, transformed, rejected, or treated as non-applicable data.

### Step 5 — Implement controlled logic

Check permissions **before side effects**, check state, and perform atomic mutation according to the storage architecture. Return a meaningful result and handle exceptions according to contract.

### Step 6 — Add tests for both success and failure paths

Add tests for ADMIN/USER, valid/blank IDs, existing/non-existent tasks, and active/archived tasks; re-run the test suite for the three existing commands.

### Step 7 — Verify compatibility and release

If commands travel over REST, queues, event logs, or files, update mappers/schemas, and check old consumers, rollout timing, and stored data. You may need to deploy consumers supporting the new version before producers start sending the new command.

## 9. Standalone Java 21 example: safely adding ArchiveTask

Create the file **`SafeCommandExtensionDemo.java`**. The program demonstrates a command-processing system running **sequentially in a single process**, using a `LinkedHashMap` as temporary storage for deterministic results. It does not implement real transactions or user authentication; those topics are analyzed in Section 11.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;

public class SafeCommandExtensionDemo {
    enum Role {
        USER, ADMIN
    }

    sealed interface TaskCommand
            permits CreateTask, RenameTask, CompleteTask, ArchiveTask {}

    record CreateTask(String id, String title)
            implements TaskCommand {
        CreateTask {
            requireNonBlank(id, "id");
            requireNonBlank(title, "title");
        }
    }

    record RenameTask(String id, String newTitle)
            implements TaskCommand {
        RenameTask {
            requireNonBlank(id, "id");
            requireNonBlank(newTitle, "newTitle");
        }
    }

    record CompleteTask(String id)
            implements TaskCommand {
        CompleteTask {
            requireNonBlank(id, "id");
        }
    }

    // New command added intentionally.
    record ArchiveTask(String id)
            implements TaskCommand {
        ArchiveTask {
            requireNonBlank(id, "id");
        }
    }

    record Task(
            String id,
            String title,
            boolean completed,
            boolean archived) {}

    private static final Map<String, Task> TASKS =
            new LinkedHashMap<>();

    static void requireNonBlank(String text, String field) {
        if (text == null || text.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
    }

    static Task requireActive(String id) {
        Task task = TASKS.get(id);
        if (task == null) {
            throw new IllegalArgumentException(
                    "Task not found: " + id);
        }
        if (task.archived()) {
            throw new IllegalStateException(
                    "Task is archived: " + id);
        }
        return task;
    }

    static String create(String id, String title) {
        if (TASKS.containsKey(id)) {
            throw new IllegalStateException(
                    "Task already exists: " + id);
        }
        TASKS.put(id, new Task(id, title, false, false));
        return "CREATED:" + id;
    }

    static String rename(String id, String newTitle) {
        Task old = requireActive(id);
        TASKS.put(id, new Task(
                id, newTitle, old.completed(), false));
        return "RENAMED:" + id;
    }

    static String complete(String id) {
        Task old = requireActive(id);
        if (old.completed()) {
            throw new IllegalStateException(
                    "Task already completed: " + id);
        }
        TASKS.put(id, new Task(
                id, old.title(), true, false));
        return "COMPLETED:" + id;
    }

    static String archive(String id) {
        Task old = requireActive(id);
        TASKS.put(id, new Task(
                id, old.title(), old.completed(), true));
        return "ARCHIVED:" + id;
    }

    static String execute(TaskCommand command, Role role) {
        if (role == null) {
            throw new IllegalArgumentException(
                    "role must not be null");
        }

        return switch (command) {
            case CreateTask(String id, String title) ->
                    create(id, title);

            case RenameTask(String id, String newTitle) ->
                    rename(id, newTitle);

            case CompleteTask(String id) ->
                    complete(id);

            case ArchiveTask(String id) when role != Role.ADMIN ->
                    throw new SecurityException(
                            "Only ADMIN may archive");

            case ArchiveTask(String id) ->
                    archive(id);

            case null ->
                    throw new IllegalArgumentException(
                            "command must not be null");
        };
    }

    // Only prints exceptions to demonstrate test cases.
    static void attempt(String label, Supplier<String> action) {
        try {
            System.out.println(label + " => " + action.get());
        } catch (RuntimeException ex) {
            System.out.println(label + " => "
                    + ex.getClass().getSimpleName()
                    + ": " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        attempt("create", () ->
                execute(new CreateTask("T-1", "Viết bài Java"),
                        Role.USER));

        attempt("rename", () ->
                execute(new RenameTask(
                        "T-1", "Học pattern matching"), Role.USER));

        attempt("complete", () ->
                execute(new CompleteTask("T-1"), Role.USER));

        attempt("archive-user", () ->
                execute(new ArchiveTask("T-1"), Role.USER));

        attempt("archive-admin", () ->
                execute(new ArchiveTask("T-1"), Role.ADMIN));

        attempt("rename-after-archive", () ->
                execute(new RenameTask("T-1", "Đổi tên"),
                        Role.USER));

        attempt("duplicate-create", () ->
                execute(new CreateTask("T-1", "Bản sao"),
                        Role.USER));

        attempt("missing-task", () ->
                execute(new CompleteTask("T-404"), Role.USER));

        attempt("null-command", () ->
                execute(null, Role.ADMIN));

        attempt("blank-id", () ->
                execute(new ArchiveTask(" "), Role.ADMIN));

        System.out.println("state => " + TASKS.get("T-1"));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 -encoding UTF-8 SafeCommandExtensionDemo.java
java SafeCommandExtensionDemo
```

**Expected standard output:**

```text
create => CREATED:T-1
rename => RENAMED:T-1
complete => COMPLETED:T-1
archive-user => SecurityException: Only ADMIN may archive
archive-admin => ARCHIVED:T-1
rename-after-archive => IllegalStateException: Task is archived: T-1
duplicate-create => IllegalStateException: Task already exists: T-1
missing-task => IllegalArgumentException: Task not found: T-404
null-command => IllegalArgumentException: command must not be null
blank-id => IllegalArgumentException: id must not be blank
state => Task[id=T-1, title=Học pattern matching, completed=true, archived=true]
```

### Reviewing each group of results

1. `create` creates a new task and returns `CREATED:T-1`. `rename` keeps the ID and changes the title to `Học pattern matching`. `complete` transitions `completed` from `false` to `true`.
2. `archive-user` matches `ArchiveTask`, and the guard `role != Role.ADMIN` evaluates to true, so it throws `SecurityException`. Because `archive(id)` is not called, the task is **not** archived at this step.
3. `archive-admin` has the ADMIN role, so the guard evaluates to false; the subsequent `ArchiveTask` case is selected, archiving succeeds, and it returns `ARCHIVED:T-1`.
4. `rename-after-archive` finds the task, but `requireActive` detects `archived=true` and throws `IllegalStateException`.
5. `duplicate-create` detects that ID `T-1` already exists and does not overwrite the task. `missing-task` rejects the non-existent `T-404`.
6. `null-command` selects `case null` and throws `IllegalArgumentException`. `blank-id` is rejected right inside the compact constructor of `ArchiveTask` **before `execute` is even called**.
7. The final line prints the `Task` record. The final title and state are preserved: `completed=true`, `archived=true`. The failed calls above did not write changes to the map.

**Note on the demo:** `attempt` catches `RuntimeException` to print **expected errors** like a manual test, which does not mean the handler turned errors into successes. In production, catching every `RuntimeException` and returning HTTP 200 or `"OK"` must be avoided; the boundary layer must map errors according to policy and preserve error observability.

## 10. Test matrix when adding a command

Do not test only a successful `ArchiveTask` call with ADMIN; you must verify the rejection paths and the previous commands as well.

| Scenario | Expected result | Purpose |
| --- | --- | --- |
| `CreateTask("T-1", validTitle)` with a new ID | `CREATED` | Existing behavior still works. |
| `RenameTask` on an active task | `RENAMED` | Changing the title does not lose completed state. |
| `CompleteTask` the first time | `COMPLETED` | Completion state is accurate. |
| `ArchiveTask` with USER role | `SecurityException`, no mutation | Permission guard and case ordering. |
| `ArchiveTask` with ADMIN, active task | `ARCHIVED` | The new command is executed. |
| Rename after archive | `IllegalStateException` | State transition rules. |
| Re-create an existing ID | `IllegalStateException` | Prevents overwriting an existing task. |
| Complete a non-existent ID | `IllegalArgumentException` | Invalid data reference. |
| `null` command | `IllegalArgumentException` | Null selector policy. |
| Blank or null ID in record | `IllegalArgumentException` | Validation right in the constructor. |
| Repeated archive | `IllegalStateException` in demo | Contract is not yet idempotent; needs a decision for production. |
| Second complete | `IllegalStateException` in demo | Prevents repeated operation against current policy. |

### Example unit tests with JUnit Jupiter

The following snippet is **a standalone test illustration** requiring JUnit Jupiter configured in the project. It assumes `SafeCommandExtensionDemo` is compiled in the same package and only calls operations whose outcomes do not depend on `TASKS` state from other tests.

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertThrows;

class SafeCommandExtensionDemoTest {
    @Test
    void archiveRequiresAdmin() {
        var command = new SafeCommandExtensionDemo.ArchiveTask("A-1");

        assertThrows(SecurityException.class,
                () -> SafeCommandExtensionDemo.execute(
                        command,
                        SafeCommandExtensionDemo.Role.USER));
    }

    @Test
    void blankIdIsRejectedBeforeDispatch() {
        assertThrows(IllegalArgumentException.class,
                () -> new SafeCommandExtensionDemo.ArchiveTask(" "));
    }

    @Test
    void nullCommandIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> SafeCommandExtensionDemo.execute(
                        null, SafeCommandExtensionDemo.Role.ADMIN));
    }
}
```

The cases above mainly test error paths; when writing a full test suite for a system, use a separate store per test or a controlled reset/fixture so tests do not depend on static state from other tests. Verifying **no mutation on permission denial** requires reading the state appropriately, not just `assertThrows`; in the demo, stdout and the final state help observe this, but they do not replace independent state-invariance tests.

## 11. Safely adding commands in real-world systems

### 11.1. Idempotency and retried requests

In networked APIs, a client may send the same command multiple times due to timeouts/retries, even if the first attempt succeeded. In the demo, calling `CreateTask` again with the same ID is rejected; calling `ArchiveTask` a second time is also rejected. **This policy may be fine for an exercise, but it is not enough to consider a system safe against retries.**

If business requirements call for **idempotent** execution, consider:

- Giving the command a stable **idempotency key** for one logical request.
- Recording the key and processed result in durable storage.
- When receiving the same key again, returning the recorded result instead of repeating side effects.
- Distinguishing a retry of the **same command** from a new command with identical content.
- Using unique constraints/transactions to prevent two concurrent requests from both passing the duplicate check.

An in-memory `Map` and a `containsKey` followed by `put` **are not an atomic operation** when multiple threads/servers contend. Production idempotency involves storage and transaction design, not just records/patterns.

### 11.2. Ordering and state consistency

If `ArchiveTask` arrives before `CreateTask` over a message queue, the handler may report that the ID does not exist yet. If two commands arrive nearly simultaneously, you need an **ordering** policy, object versioning, or concurrency control.

For example, optimistic locking can rely on a `version` field on the task: the handler reads the expected version and only updates if the version has not changed. When a conflict occurs, return a meaningful result instead of silently overwriting. The case study does not implement locking because its scope is pattern matching, but this must be checked before using the command model in a concurrent system.

### 11.3. Authorization at the trust boundary

The guard `role != Role.ADMIN` only illustrates a single condition. In a real application:

- Verify the identity/token and obtain the role from a trusted security context.
- Authorize based on specific permissions or resources if the model requires it, rather than a single global enum.
- Ensure other entry points (batch jobs, CLIs, queue consumers) do not bypass checks.
- Perform checks before mutating state and audit critical actions.

Do not treat a single `when` clause as a complete substitute for a security architecture.

### 11.4. Versioning command payloads

When commands are transmitted over REST/queues/JSON, Java subtypes in one module do not describe the entire messaging contract. You must manage:

- A stable **discriminator**, such as the type `"ARCHIVE_TASK"` in the external schema.
- Required/optional fields, default values, and validation rules.
- Schema versioning or compatibility strategies when adding fields.
- Older clients/consumers encountering a new command should **explicitly reject it** or be upgraded before receiving it, rather than treating it as a success.
- Commands and events are distinct: a command is a request, while a `TaskArchived` event (if emitted after execution) describes the outcome that occurred.

When performing a rolling upgrade, a generally safe sequence is to **upgrade consumers to understand the new command first**, and only then enable producers to send it. The exact process depends on the message broker, deployment topology, and backward-compatibility requirements.

### 11.5. Transactions, side effects, and outbox

If archiving both updates a database and emits an event, consider the case where **only one of the two steps succeeds**. A database transaction combined with a **transactional outbox** is one option to synchronize state and event-publishing intent, paired with idempotent consumers. Record patterns do not solve distributed transaction problems on their own.

In the demo program, there is only a single map and no database or event bus; use it to learn how to add a command that the compiler can check, **not** as a complete multi-node deployment architecture.

## 12. Common mistakes when extending a Command hierarchy

### Mistake 1 — Adding a record but forgetting permits

`record ArchiveTask(String id) implements TaskCommand` will not be allowed to directly implement a `sealed interface` if it is not listed in the valid `permits` set. The fix is to intentionally update the type hierarchy, not to remove `sealed` just to make adding types “easier”.

### Mistake 2 — Adding to permits without updating all dispatchers

When a handler is an exhaustive `switch expression` without `default`, the compiler can point out missing cases upon recompilation. Do not fix it with `default -> "SUCCESS"`. Depending on the consumer, handle, reject, or forward `ArchiveTask` according to its specific contract.

### Mistake 3 — Placing a general case before a specific guard

```java
// Wrong order if you want a role-specific check for ArchiveTask:
// case ArchiveTask(String id) -> archive(id);
// case ArchiveTask(String id) when role != Role.ADMIN ->
//         throw new SecurityException("Denied");
```

The first unguarded branch covers every `ArchiveTask`, making the subsequent branch **dominated** and causing a compile-time error. Always place the specifically guarded branch **before** the broader branch, and test both true and false guard cases.

### Mistake 4 — Checking permissions after mutating

Rejecting after already archiving does not automatically restore state. Write handlers that perform checks before side effects and use transactions when there are multiple write steps.

### Mistake 5 — Relying solely on pattern matching and skipping validation

`case CreateTask(String id, String title)` confirms that the components match the type pattern, but it does not prove that `id` or `title` is non-blank, within length limits, or domain-valid. The constructor or boundary must still validate the content.

### Mistake 6 — Assuming default catches null

The `null` selector in a pattern-matching `switch` has its own rules. If a null command is an error, use `case null -> throw ...` or check before the `switch`. Do not let an exception happen accidentally and then catch it generically.

### Mistake 7 — Reusing a command as an event

An `ArchiveTask` is a **request to archive**; `TaskArchived` is an **event that archiving succeeded**. Sending a command as an event can mislead consumers into assuming the operation was accepted even when the handler has not validated permissions and state.

### Mistake 8 — Concluding “it is safe” just because it is sealed

`sealed` helps restrict direct subtypes, whereas business safety requires role checks, state checks, transactions, retry handling, idempotency, compatibility, and observability. Avoid confusing compile-time exhaustiveness with an end-to-end runtime guarantee.

## 13. Trade-off: sealed hierarchy or open interface?

The approach in this article is suitable when **the owning module controls the command set** and wants dispatchers to be forced to update when a new command appears.

If a project exposes a **plugin API** for third parties to add commands/handlers without modifying the core, an open `interface` and a handler registration mechanism may be more appropriate. With an open interface, the compiler cannot inherently prove that a few specific cases cover all future implementations; you need a fallback or dispatch based on a common contract.

Do not abandon `sealed` just because “we might add more commands later”; when the owning module still controls all commands, extending `permits` and updating handlers is a controlled process. Conversely, do not force third-party plugins into a closed `permits` set if the design itself requires independent extensibility.

In particular, using **polymorphism** is also a valuable option:

```java
interface CommandHandler<T> {
    String handle(T command);
}
```

This is only an illustrative contract, without a registry or handler-selection mechanism. If business logic is already encapsulated in separate handlers, a registry that checks for missing handlers may be better than a large `switch`. However, an open-style registry must proactively detect unregistered commands and handle errors explicitly; it does not inherit the exhaustiveness of a sealed switch.

## 14. Checklist for reviewing a pull request that adds a command

1. **Domain meaning:** Does the new command represent a single intent, with a clear name, not confused with an event?
2. **Schema:** Does the record hold the minimal required data and have validation for null/blank/range?
3. **Hierarchy:** Is `permits` updated in the right module/package without breaking old subtypes?
4. **Dispatch:** Does every `switch`/handler have an explicit case for the new subtype or an intentional rejection policy?
5. **Guard:** Are guarded branches placed before general branches; are both true and false guard outcomes tested?
6. **Authorization:** Is the role obtained from a trusted source and checked before mutation?
7. **State transitions:** Can the command be applied to existing, completed, or archived tasks?
8. **Failure:** Are errors prevented from turning into fake successes; are exception/result types meaningful?
9. **Atomicity:** Are partial updates avoided, and are race conditions/transactions handled according to the storage architecture?
10. **Retry/idempotency:** Is there a policy for retried, concurrent, or duplicate-ID commands?
11. **Compatibility:** Are producers, consumers, serializers, schemas, and old data upgraded in the appropriate order?
12. **Tests:** Are there new tests and regression tests for all existing commands, including state after failure?
13. **Build:** Does it compile with official Java 21 without accidentally relying on preview syntax?
14. **Observability:** Are there appropriate logs/metrics/audits without leaking sensitive data?
15. **Ownership:** Who maintains the command set and decides when the next subtype is added?

## 15. Self-check

**Question 1.** Why might a `switch expression` with only the three old cases fail to compile after adding `ArchiveTask` to `permits TaskCommand`?

**Answer:** Because the closed hierarchy now has an additional permitted subtype. Without a catch-all case, the Java 21 compiler detects that the `switch` expression is no longer exhaustive. This is a necessary signal to update the dispatcher.

**Question 2.** Why should you not add `default -> "OK"` just to fix the missing-case error?

**Answer:** The new command could be ignored while the caller believes it was executed. If a command is not supported, it must return a clear error/meaningful failure, not report a fake success.

**Question 3.** Given:

```java
case ArchiveTask(String id) when role != Role.ADMIN ->
        throw new SecurityException("Only ADMIN may archive");
case ArchiveTask(String id) ->
        archive(id);
```

what happens with `Role.USER` and `Role.ADMIN`?

**Answer:** With USER, the first guard evaluates to true and throws `SecurityException`; `archive` is not called. With ADMIN, the first guard evaluates to false, and Java proceeds to the second case and calls `archive`, provided the domain state is valid. This code is a snippet inside a `switch`, not a standalone runnable file.

**Question 4.** When is a command considered idempotent?

**Answer:** When re-executing the same **logical request** according to the contract produces no additional unintended side effects. In an API with retries, this usually requires an idempotency key and a mechanism to store results/ensure uniqueness. The demo intentionally rejects re-archiving, so it cannot claim to have a complete idempotency mechanism.

**Question 5.** Why should `ArchiveTask` not be used as the `TaskArchived` event?

**Answer:** A command is a request that can fail; an event is information that an operation has occurred. Renaming the concept does not solve permission checks, state checks, and persistence results.

## 16. Background references

- **JEP 409 – Sealed Classes:** https://openjdk.org/jeps/409
- **JEP 440 – Record Patterns:** https://openjdk.org/jeps/440
- **JEP 441 – Pattern Matching for switch:** https://openjdk.org/jeps/441
- **Oracle Java 21 – Pattern Matching for switch:** https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- **Java Language Specification 21, `14.30 – Patterns:** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30

**Remember:** Safely adding a command is a **cross-cutting contract change**: command types, `permits`, dispatchers, permissions, validation, state, tests, and compatibility must all be updated consistently. **Java 21 sealed interfaces + record patterns + exhaustive switch** help the compiler catch many missing branches and make dispatching logic easier to read; however, only **authorization before side effects, state/transaction management, and regression testing** make the change safe in a real application.
