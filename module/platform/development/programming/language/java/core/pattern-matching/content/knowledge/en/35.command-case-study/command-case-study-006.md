# Using Guards for Permissions or State in Pattern Switch (Java 21)

## 1. The Problem: Command Dispatch Must Check Permissions and State

A business system typically receives multiple **commands** such as creating a task, submitting for review, approving, or canceling a task. Each command carries its own data, yet **not everyone can execute every command** and **not every state accepts every operation**.

For example:

- Only users granted the `CREATE` permission may create a task.
- Only the task owner or someone with the `SUBMIT` permission may submit it for review.
- Someone with the `APPROVE` permission may approve a `SUBMITTED` task, but may not self-approve their own task.
- Someone with the `CANCEL` permission may cancel a task in `DRAFT` or `SUBMITTED` state, but may not cancel a task that is already `APPROVED` or `CANCELLED`.

If all this logic is placed into a long `if / else` chain, the code easily mixes **identifying the command type**, **checking permissions**, **checking state**, and **executing the action**. With Java 21's **pattern matching for switch**, we can use **record patterns** to identify the command and `when` guards to express rules before returning a decision.

Learning objectives:

1. Model commands using a `sealed interface` and `record` types.
2. Understand that a `when` guard runs **after the pattern matches** and before the branch is selected.
3. Distinguish between permission checks (authorization), input validation, and state checks.
4. Order branches to **deny first**, avoid information disclosure, and prevent a broader case from dominating a narrower case.
5. Handle `null`, missing permissions, ownership, invalid state, and anti-self-approval rules.
6. Test decisions with Java 21, including `DENY` paths and error precedence.
7. Understand security boundaries: guards do not replace user authentication, transactions, or state checks at write time.

**Version:** `record patterns` (JEP 440) and `pattern matching for switch` (JEP 441) became standard features in **Java 21**, without needing `--enable-preview`. The runnable code snippets use JDK 21 or later.

## 2. Three Decision Layers to Separate

Before writing a switch, classify the conditions:

| Layer | Question | Example | Result on failure |
| --- | --- | --- | --- |
| Authentication / actor identification | Is there an identity authenticated by the system? | `actor != null` in the demo | `UNAUTHENTICATED` |
| Authorization / permissions | Does the identity have permission to act on this resource? | `actor.can(APPROVE)` or is the owner | `FORBIDDEN` |
| Business state / state | Is the command valid in the current state? | Approve only when `state == SUBMITTED` | `INVALID_STATE` |
| Business constraint / additional rules | Does it conflict with a domain rule? | Self-approval is not allowed | `SELF_APPROVAL` |
| Input validity / data | Do the command and resource have the required data? | Non-null task, non-blank ID | `INVALID_INPUT` |

In a real system, actor authentication is the responsibility of the HTTP/gRPC layer, session, JWT verifier, or a trusted security context. This example only simulates it with `Actor` to focus on the **command case study**; do not treat an arbitrary `Actor` sent by a client as proof that a user is logged in or authorized.

**Important rule:** permissions and state are two different things. Someone with the `APPROVE` permission still cannot approve a task in `DRAFT` state. Conversely, a task being in `SUBMITTED` state does not grant everyone permission to approve it.

## 3. Domain Model: Command, Actor, and State

We define:

```java
enum Permission { CREATE, SUBMIT, APPROVE, CANCEL }
enum State { DRAFT, SUBMITTED, APPROVED, CANCELLED }
```

An actor has an ID and a set of permissions:

```java
record Actor(String id, java.util.Set<Permission> permissions) {
    Actor {
        java.util.Objects.requireNonNull(id, "actor id");
        permissions = java.util.Set.copyOf(
            java.util.Objects.requireNonNull(permissions, "permissions")
        );
    }
    boolean can(Permission permission) {
        return permissions.contains(permission);
    }
}
```

Notable point: `Set.copyOf(...)` creates an unmodifiable permission set detached from the input collection reference and rejects null elements per the API contract. This prevents other code from accidentally mutating the permission set right after creating the `Actor`. It **does not verify the origin** of the permissions; in production, permissions must still be constructed from a trusted data source.

A task has an ID, an owner, and a state:

```java
record Task(String id, String ownerId, State state) {
    Task {
        java.util.Objects.requireNonNull(id, "task id");
        java.util.Objects.requireNonNull(ownerId, "owner id");
        java.util.Objects.requireNonNull(state, "state");
    }
}
```

The constructor above prevents null `id`, `ownerId`, and `state`. This is a basic technical constraint; the code does not yet verify that the ID exists in a database or belongs to the same tenant. A `Task` constructed from untrusted input **does not automatically** become an authoritative resource for permission decisions.

The commands:

```java
sealed interface Command permits Create, Submit, Approve, Cancel {}

record Create(String taskId) implements Command {}
record Submit(Task task) implements Command {}
record Approve(Task task) implements Command {}
record Cancel(Task task) implements Command {}
```

A `sealed interface` restricts its direct permitted implementors. The records `Create`, `Submit`, `Approve`, and `Cancel` are the concrete command forms. Thanks to the closed type hierarchy, a `switch expression` over `Command` can cover all subtypes **without needing `default`**, allowing the compiler to warn when a new command type is added.

Do not confuse `Command` here with Java's `Runnable` or another design pattern just because they share the word "command". In this article, it is a domain data type representing an **intent** that must be evaluated before execution.

## 4. Permission and State Transition Table

Before writing `when`, you should express the rules as a table. This forms the basis for code reviews and tests.

| Command | Who can request it? | Required state/input | Result when accepted |
| --- | --- | --- | --- |
| `Create(taskId)` | Has `CREATE` permission | Non-null, non-blank `taskId` | `ALLOW CREATE` |
| `Submit(task)` | Has `SUBMIT` permission **or** is the owner | Task exists, in `DRAFT` | `ALLOW SUBMIT` |
| `Approve(task)` | Has `APPROVE` permission and **is not the owner** | Task exists, in `SUBMITTED` | `ALLOW APPROVE` |
| `Cancel(task)` | Has `CANCEL` permission | Task exists, in `DRAFT` or `SUBMITTED` | `ALLOW CANCEL` |

In the demo, task creation is not implemented yet; `ALLOW CREATE` is an **authorization decision**, not a notification that a record has been written to a database. Similarly, `ALLOW APPROVE` does not transition `Task.state` to `APPROVED`. This is an intentional separation between **checking** and **execution**.

Denial decisions use these error codes:

- `UNAUTHENTICATED`: no actor is present.
- `INVALID_COMMAND`: null command.
- `FORBIDDEN`: actor is not allowed to execute the command.
- `INVALID_INPUT`: insufficient command data.
- `INVALID_STATE`: current state does not allow the operation.
- `SELF_APPROVAL`: violates separation of duties.

Error precedence affects observable behavior. For instance, with `Approve`, we check **permissions first**, then input data and state, so we do not leak business state information to an actor without `APPROVE` permission. In a real application, even distinguishing whether a resource exists or not may need to be hidden from unauthorized users.

## 5. How the `when` Guard Works in Pattern Switch

In Java 21, a `case` can consist of a pattern and a guard:

```java
case Approve(var task) when !actor.can(Permission.APPROVE)
        -> Decision.deny("FORBIDDEN");
```

Evaluation order:

1. `switch (command)` evaluates the **selector**, which is a `Command` value.
2. The pattern `Approve(var task)` checks whether the command is an `Approve` record.
3. If the pattern matches, the variable `task` is bound from the record component.
4. Java evaluates `when !actor.can(Permission.APPROVE)`.
5. If the guard is true, that case is selected and returns `DENY FORBIDDEN`.
6. If the guard is false, Java evaluates the remaining cases. **A false guard does not mean the entire command is rejected**; another case must handle it.

A `when` guard is a boolean expression executed in the scope of the bound pattern variables. For example:

```java
case Submit(var task) when task.state() != State.DRAFT
        -> Decision.deny("INVALID_STATE");
```

The expression above is only safe if earlier branches have already eliminated `task == null` or the guard itself checks for null. If `task` is null, calling `task.state()` throws `NullPointerException`. In the complete code, the `Submit(var task) when task == null` branch is placed first.

### Switch Guard vs. Guard Clause

**Switch guard**: the condition after `when` that determines whether a case is selected.

**Guard clause**: an `if (!condition) return ...;` statement used to exit early from a method or block.

The two techniques can work together: check for null actor/command using guard clauses first, then use `when` inside the switch to express rules specific to each command type. That is the approach chosen in this article: do not try to cram every check, including actor presence, into complex switch cases.

### Pattern Match Does Not Mean Success

If `command` is `Approve(task)`, the pattern `Approve(var task)` matches **even when the actor lacks permission**. Permission is only evaluated by `when`. Likewise, a record can match the type while containing `task == null`; `var task` can still bind to null. Therefore, you need to test **type match + guard true**, **type match + guard false**, and null components.

## 6. Permission and State Decision Patterns per Command

### 6.1. Create: Permission, Valid ID, and Allow Last

```java
case Create(var taskId) when !actor.can(Permission.CREATE)
        -> Decision.deny("FORBIDDEN");
case Create(var taskId) when taskId == null || taskId.isBlank()
        -> Decision.deny("INVALID_INPUT");
case Create(var taskId) -> Decision.allow("CREATE");
```

The first branch rejects actors lacking permission **before** revealing whether the input is valid. The second branch blocks invalid IDs for actors who do have permission. The final unguarded branch is the remaining path: the command has passed both checks.

If you move the unguarded `Create` branch to the top, the `Create` branches with `when` below it are shadowed. The Java 21 compiler will report a **dominated case label**, and even if a variant somehow didn't fail compilation, the intent of checking permissions first would be broken.

### 6.2. Submit: Owner or Permitted User, Task Must Be DRAFT

```java
case Submit(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Submit(var task) when !actor.can(Permission.SUBMIT)
        && !actor.id().equals(task.ownerId())
        -> Decision.deny("FORBIDDEN");
case Submit(var task) when task.state() != State.DRAFT
        -> Decision.deny("INVALID_STATE");
case Submit(var task) -> Decision.allow("SUBMIT");
```

In the demo, **the owner may submit even without the `SUBMIT` permission**; non-owners require this permission. That is an **illustrative business rule**, not a universal default policy for every organization. If a project requires owners to also hold `SUBMIT`, remove the ownership check from the allow condition.

The null-check branch comes first because the ownership check needs to read `task.ownerId()`. Once the task is non-null, we check whether the actor has permission or is the owner; once authorized, we check `task.state() == DRAFT`.

**Security note:** the code only reads `task.ownerId()` from an in-memory object. In production, you must load/verify the owner from a trusted data store tied to the tenant/scope, and never accept a `Task` whose `ownerId` was freely constructed by a client to grant permissions.

### 6.3. Approve: Permission, Input, Separation of Duties, and State

```java
case Approve(var task) when !actor.can(Permission.APPROVE)
        -> Decision.deny("FORBIDDEN");
case Approve(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Approve(var task) when actor.id().equals(task.ownerId())
        -> Decision.deny("SELF_APPROVAL");
case Approve(var task) when task.state() != State.SUBMITTED
        -> Decision.deny("INVALID_STATE");
case Approve(var task) -> Decision.allow("APPROVE");
```

Note the order:

1. No `APPROVE` permission → deny immediately.
2. Has permission but command has no task → invalid input.
3. Approver is also the owner → `SELF_APPROVAL`.
4. Task is not submitted or already approved/canceled → `INVALID_STATE`.
5. When none of the denial conditions apply → `ALLOW APPROVE`.

This is an example of **separation of duties**. Adding `APPROVE` to the owner's permission set does not bypass the anti-self-approval rule.

### 6.4. Cancel: Permission and Allowed State Set

```java
case Cancel(var task) when !actor.can(Permission.CANCEL)
        -> Decision.deny("FORBIDDEN");
case Cancel(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Cancel(var task) when task.state() == State.APPROVED
        || task.state() == State.CANCELLED
        -> Decision.deny("INVALID_STATE");
case Cancel(var task) -> Decision.allow("CANCEL");
```

The `State` enum in the demo has exactly four states. Because `APPROVED` and `CANCELLED` are excluded, the remaining states are `DRAFT` or `SUBMITTED`, both of which are cancelable. If `ARCHIVED` is added in the future, checking by **listing forbidden states** could accidentally allow canceling `ARCHIVED` tasks.

A **safer way when adding new states** is to write the guard for the **allowed state set**:

```java
// Replacement snippet for the two state/allow branches of Cancel:
case Cancel(var task) when task.state() == State.DRAFT
        || task.state() == State.SUBMITTED
        -> Decision.allow("CANCEL");
case Cancel(var task) -> Decision.deny("INVALID_STATE");
```

This approach *fails closed* on new states. Only use this snippet after the permission and null-task guards, since it reads `task.state()`. In the complete code, the first version is kept to clearly illustrate `when` for denial branches; in production, prefer checking the **allowed** states directly or using a dedicated state machine if the state set can evolve.

## 7. Complete Java 21 Program: 20 Guard Checks

Create the file **`CommandGuardDemo.java`**:

```java
public class CommandGuardDemo {
    enum Permission { CREATE, SUBMIT, APPROVE, CANCEL }
    enum State { DRAFT, SUBMITTED, APPROVED, CANCELLED }

    record Actor(String id, java.util.Set<Permission> permissions) {
        Actor {
            java.util.Objects.requireNonNull(id, "actor id");
            permissions = java.util.Set.copyOf(
                java.util.Objects.requireNonNull(permissions, "permissions")
            );
        }
        boolean can(Permission permission) {
            return permissions.contains(permission);
        }
    }

    record Task(String id, String ownerId, State state) {
        Task {
            java.util.Objects.requireNonNull(id, "task id");
            java.util.Objects.requireNonNull(ownerId, "owner id");
            java.util.Objects.requireNonNull(state, "state");
        }
    }

    sealed interface Command permits Create, Submit, Approve, Cancel {}
    record Create(String taskId) implements Command {}
    record Submit(Task task) implements Command {}
    record Approve(Task task) implements Command {}
    record Cancel(Task task) implements Command {}

    record Decision(boolean allowed, String code) {
        static Decision allow(String code) {
            return new Decision(true, code);
        }
        static Decision deny(String code) {
            return new Decision(false, code);
        }
        public String toString() {
            return (allowed ? "ALLOW " : "DENY ") + code;
        }
    }

    static Decision decide(Actor actor, Command command) {
        if (actor == null) return Decision.deny("UNAUTHENTICATED");
        if (command == null) return Decision.deny("INVALID_COMMAND");

        return switch (command) {
            case Create(var taskId) when !actor.can(Permission.CREATE)
                -> Decision.deny("FORBIDDEN");
            case Create(var taskId) when taskId == null || taskId.isBlank()
                -> Decision.deny("INVALID_INPUT");
            case Create(var taskId) -> Decision.allow("CREATE");

            case Submit(var task) when task == null
                -> Decision.deny("INVALID_INPUT");
            case Submit(var task) when !actor.can(Permission.SUBMIT)
                    && !actor.id().equals(task.ownerId())
                -> Decision.deny("FORBIDDEN");
            case Submit(var task) when task.state() != State.DRAFT
                -> Decision.deny("INVALID_STATE");
            case Submit(var task) -> Decision.allow("SUBMIT");

            case Approve(var task) when !actor.can(Permission.APPROVE)
                -> Decision.deny("FORBIDDEN");
            case Approve(var task) when task == null
                -> Decision.deny("INVALID_INPUT");
            case Approve(var task) when actor.id().equals(task.ownerId())
                -> Decision.deny("SELF_APPROVAL");
            case Approve(var task) when task.state() != State.SUBMITTED
                -> Decision.deny("INVALID_STATE");
            case Approve(var task) -> Decision.allow("APPROVE");

            case Cancel(var task) when !actor.can(Permission.CANCEL)
                -> Decision.deny("FORBIDDEN");
            case Cancel(var task) when task == null
                -> Decision.deny("INVALID_INPUT");
            case Cancel(var task) when task.state() == State.APPROVED
                    || task.state() == State.CANCELLED
                -> Decision.deny("INVALID_STATE");
            case Cancel(var task) -> Decision.allow("CANCEL");
        };
    }

    static int checks;

    static void expect(String label, String expected, Decision decision) {
        String actual = decision.toString();
        if (!expected.equals(actual)) {
            throw new AssertionError(
                label + " expected=" + expected + " actual=" + actual
            );
        }
        checks++;
        System.out.println("PASS " + label + " => " + actual);
    }

    public static void main(String[] args) {
        Actor creator = new Actor("ann", java.util.Set.of(Permission.CREATE));
        Actor owner = new Actor("ann", java.util.Set.of());
        Actor submitter = new Actor("sam", java.util.Set.of(Permission.SUBMIT));
        Actor reviewer = new Actor("bob", java.util.Set.of(Permission.APPROVE));
        Actor approverOwner = new Actor("ann", java.util.Set.of(Permission.APPROVE));
        Actor operator = new Actor("ops", java.util.Set.of(Permission.CANCEL));
        Actor outsider = new Actor("eve", java.util.Set.of());

        Task draft = new Task("T1", "ann", State.DRAFT);
        Task submitted = new Task("T1", "ann", State.SUBMITTED);
        Task approved = new Task("T1", "ann", State.APPROVED);

        expect("create", "ALLOW CREATE", decide(creator, new Create("T1")));
        expect("create-no-permission", "DENY FORBIDDEN",
                decide(outsider, new Create("T1")));
        expect("create-blank", "DENY INVALID_INPUT",
                decide(creator, new Create(" ")));

        expect("submit-owner", "ALLOW SUBMIT", decide(owner, new Submit(draft)));
        expect("submit-permission", "ALLOW SUBMIT",
                decide(submitter, new Submit(draft)));
        expect("submit-forbidden", "DENY FORBIDDEN",
                decide(outsider, new Submit(draft)));
        expect("submit-wrong-state", "DENY INVALID_STATE",
                decide(owner, new Submit(submitted)));
        expect("submit-missing-task", "DENY INVALID_INPUT",
                decide(owner, new Submit(null)));

        expect("approve", "ALLOW APPROVE",
                decide(reviewer, new Approve(submitted)));
        expect("approve-forbidden", "DENY FORBIDDEN",
                decide(owner, new Approve(submitted)));
        expect("approve-self", "DENY SELF_APPROVAL",
                decide(approverOwner, new Approve(submitted)));
        expect("approve-wrong-state", "DENY INVALID_STATE",
                decide(reviewer, new Approve(draft)));
        expect("approve-missing-task", "DENY INVALID_INPUT",
                decide(reviewer, new Approve(null)));

        expect("cancel-draft", "ALLOW CANCEL",
                decide(operator, new Cancel(draft)));
        expect("cancel-submitted", "ALLOW CANCEL",
                decide(operator, new Cancel(submitted)));
        expect("cancel-approved", "DENY INVALID_STATE",
                decide(operator, new Cancel(approved)));
        expect("cancel-forbidden", "DENY FORBIDDEN",
                decide(outsider, new Cancel(draft)));
        expect("cancel-missing-task", "DENY INVALID_INPUT",
                decide(operator, new Cancel(null)));

        expect("no-actor", "DENY UNAUTHENTICATED",
                decide(null, new Create("T1")));
        expect("no-command", "DENY INVALID_COMMAND", decide(owner, null));

        System.out.println("checks=" + checks);
    }
}
```

**Compile and run:**

```bash
javac --release 21 CommandGuardDemo.java
java CommandGuardDemo
```

**Exact stdout:**

```text
PASS create => ALLOW CREATE
PASS create-no-permission => DENY FORBIDDEN
PASS create-blank => DENY INVALID_INPUT
PASS submit-owner => ALLOW SUBMIT
PASS submit-permission => ALLOW SUBMIT
PASS submit-forbidden => DENY FORBIDDEN
PASS submit-wrong-state => DENY INVALID_STATE
PASS submit-missing-task => DENY INVALID_INPUT
PASS approve => ALLOW APPROVE
PASS approve-forbidden => DENY FORBIDDEN
PASS approve-self => DENY SELF_APPROVAL
PASS approve-wrong-state => DENY INVALID_STATE
PASS approve-missing-task => DENY INVALID_INPUT
PASS cancel-draft => ALLOW CANCEL
PASS cancel-submitted => ALLOW CANCEL
PASS cancel-approved => DENY INVALID_STATE
PASS cancel-forbidden => DENY FORBIDDEN
PASS cancel-missing-task => DENY INVALID_INPUT
PASS no-actor => DENY UNAUTHENTICATED
PASS no-command => DENY INVALID_COMMAND
checks=20
```

**Breakdown of check groups:**

- **Create:** a permitted user can create with a valid ID; an unpermitted user gets `FORBIDDEN`; a blank ID is rejected after permission is verified.
- **Submit:** the owner can submit even without `SUBMIT` permission per the demo policy; another user with the permission can also submit; an outsider is denied; a non-`DRAFT` or null task cannot be submitted.
- **Approve:** a permitted reviewer can approve a `SUBMITTED` task; without permission it is denied; an owner with permission is still blocked from self-approving; `DRAFT` and null tasks cannot be approved.
- **Cancel:** a user with `CANCEL` permission can cancel `DRAFT`/`SUBMITTED`; `APPROVED` and null tasks are denied; outsiders are not allowed.
- **Pre-check:** a null actor is rejected before a null command. This is an **intentional priority order** in the program.

`expect` only prints PASS when the actual string equals expected; otherwise it throws `AssertionError`. The line `checks=20` confirms that the **20 checks defined in the demo** passed; it does not prove that every runtime state, permission combination, and data race in a production system has been tested.

## 8. Why Exhaustive Switch Still Needs Permission Testing

The Java 21 compiler knows `Command` only permits the subtypes `Create`, `Submit`, `Approve`, and `Cancel` because the hierarchy is `sealed`. In the main switch:

```java
case Approve(var task) when !actor.can(Permission.APPROVE) -> ...;
case Approve(var task) when task == null -> ...;
case Approve(var task) when actor.id().equals(task.ownerId()) -> ...;
case Approve(var task) when task.state() != State.SUBMITTED -> ...;
case Approve(var task) -> Decision.allow("APPROVE");
```

The final `Approve(var task)` branch **has no guard**, so it covers all remaining `Approve` cases. Likewise, the other three subtypes each end with an unguarded case, making the `switch expression` exhaustive.

However, the compiler only guarantees that a **valid branch path** exists for values of type `Command`; it does **not** guarantee that the authorization policy is correct. For example:

- If you accidentally flip `!actor.can(APPROVE)` to `actor.can(APPROVE)`, the code still compiles, yet authorized users may be denied and unauthorized users may fall through to another branch.
- If you accidentally change `state != SUBMITTED` to `state == SUBMITTED`, the compiler will not detect the inverted logic.
- If you drop the `SELF_APPROVAL` guard, the switch remains exhaustive while violating business rules.

Therefore, **positive/negative** tests are needed for every permission, state, and ownership relationship. `switch` makes the rules easier to read, not a substitute for automated tests or threat modeling.

### 8.1. Adding a New Command Type

Suppose you add `Archive(Task task)` to the hierarchy. If you keep the switch without `default` and haven't added an `Archive` case yet, the compiler will report a non-exhaustive switch expression upon recompilation.

This is a key benefit of `sealed + switch`: when the API adds a new command type, the team must actively review the policy. Using `default -> Decision.allow(...)` would be especially dangerous: new commands could be granted permission by default. For security decisions, **never use a catch-all branch that allows unrecognized commands**.

A `default -> Decision.deny("FORBIDDEN")` branch may suit an open interface, but on a closed sealed hierarchy, omitting `default` lets the compiler help surface unhandled new branches.

## 9. Permission Guards and State Guards: Order Affects Security Too

With the same two conditions, ordering can leak information:

```java
// Structure to avoid if unauthorized users
// can still receive detailed information about the resource state.
case Approve(var task) when task != null && task.state() != State.SUBMITTED
        -> Decision.deny("INVALID_STATE");
case Approve(var task) when !actor.can(Permission.APPROVE)
        -> Decision.deny("FORBIDDEN");
```

In this anti-pattern, an unauthorized actor can infer what state the resource is in from the returned error code. In the main code, the `APPROVE` permission check precedes the state-reading branches. This is only **one measure to reduce information disclosure**, not a guarantee against all forms of information leakage.

A safe ordering when state must be hidden:

1. Identify the trusted principal and scope/tenant.
2. Check the permissions required to access the resource.
3. Validate and load the resource (some steps may be combined depending on policy to avoid confirming existence).
4. Check per-resource authorization: owner, organization, role, separation of duties.
5. Check the state transition.
6. Only then execute the action via a conditional write with appropriate audit logging.

If a command does not contain a valid `Task`, you must check for null before dereferencing; **null-safety** ordering is also mandatory. For example, `Submit(var task) when task == null` comes before `task.ownerId()`.

**Key takeaway:** guard ordering is part of the business and security contract; do not reorder branches just to shorten code without verifying the impact.

## 10. When to Use Nested Record Patterns for Commands?

Beyond `Submit(var task)`, Java 21 supports deep deconstruction:

```java
// Replacement snippet in a switch on Command,
// when Actor actor is authenticated and Task has three components as in the example.
case Submit(Task(var taskId, var ownerId, var state))
        when actor.id().equals(ownerId) && state == State.DRAFT
        -> Decision.allow("SUBMIT");
```

The pattern `Submit(Task(...))` simultaneously requires the command to be `Submit` and its `task` component to be a **non-null** `Task`. It extracts `taskId`, `ownerId`, and `state` directly in the case header.

**Difference when task is null:** `Submit(Task(...))` **does not match** if `task` is null, whereas `Submit(var task)` matches and binds `task = null`. If you need to return `INVALID_INPUT` specifically, add `case Submit(var task) when task == null` in the appropriate position.

You do not have to use nested record patterns for every command. In the main code, `Submit(var task)` and `Approve(var task)` keep the `Task` object intact to clearly illustrate multi-step checks and error precedence. Nested patterns fit better when the code mainly **reads components** and does not need distinct error messages at each structural level.

### Avoid Using on Unsupported Versions

`record patterns` syntax such as `case Submit(Task(var id,...))` requires **Java 21** as a standard feature. On Java 17, you can use `instanceof Submit submit` followed by `submit.task()` and guard clauses in the method. Pattern switch existed as a preview in earlier releases, but preview features should not be used as a default compatibility choice for Java 17 production code.

## 11. Production Security: Guards Are Not a Standalone Security Boundary

This is the most critical section when turning the demo into real code.

### 11.1. Actor Must Come from a Trusted Authentication Source

Do not do this on the server:

```java
// ANTI-PATTERN: do not trust permissions sent by the client.
Actor actor = requestBody.actor();
Decision result = decide(actor, command);
```

If the client controls `actor.permissions`, they can grant themselves `APPROVE` or `CANCEL`. Then `when actor.can(...)` executes valid Java logic, yet the decision is **insecure** because the permission source is untrusted.

Instead, the actor must be constructed/resolved from an authenticated principal and server-side authorization policy. Owner, tenant, and state data must also come from a trusted source; do not rely on a `Task` whose `ownerId` was populated by the caller.

### 11.2. Broad Permissions Are Not Enough for Specific Resources

Having the `APPROVE` permission does not mean being allowed to approve every task across the entire system. Depending on the domain, you must check:

- Does the resource belong to a tenant/organization the actor is allowed to access?
- Does the actor hold an effective role/permission on that workflow or group?
- Are there maker–checker or separation-of-duties rules?
- Are there restrictions due to frozen state, permission conflicts, limits, or approval stages?

General architectural illustration:

```java
// Architectural snippet; collaborators are provided by the application.
Task task = taskRepository.loadAuthorizedView(taskId, trustedPrincipal);
PermissionSet permissions = policyService.effectivePermissions(trustedPrincipal, task);
Decision decision = commandPolicy.decide(trustedPrincipal, permissions, task, command);
```

The names `taskRepository`, `PermissionSet`, and `commandPolicy` are hypothetical application components; they are **not** built-in Java SDK APIs and **not a standalone runnable snippet**. The main point: resolve trusted data and permission scope **before** evaluating guard expressions.

### 11.3. Keep Guards Free of Side Effects

An ideal `when` expression should be simple, predictable, and **mutate no state**:

```java
case Approve(var task) when actor.can(Permission.APPROVE)
        && task != null && task.state() == State.SUBMITTED
        -> Decision.allow("APPROVE");
```

Avoid guards that "attempt a DB update and return a boolean" or call remote services with side effects to pick a case. Guards should only **inspect**, while execution should happen in a separate step with appropriate transactions or conditional writes.

When guards invoke multiple slow or throwing methods, Java's sequential case evaluation can complicate debugging and testing. Extracting logic into pure methods or centralizing policy is usually easier to maintain.

### 11.4. Prevent Decision–Mutation Drift (TOCTOU)

Suppose:

1. `decide(actor, new Approve(task))` sees the task in `SUBMITTED` and returns `ALLOW APPROVE`.
2. Another thread transitions the task to `CANCELLED`.
3. The first thread writes `APPROVED` without re-checking the state.

That is a **time-of-check to time-of-use** bug. A decision computed from a stale snapshot **does not guarantee the state is still valid at write time**.

Solutions at the storage/transaction layer:

- Read the task within an appropriate transaction or use optimistic locking with a version column.
- Perform a conditional update: only transition the state if the ID, tenant/ownership, current state/version, and effective permissions still match.
- Check the actual updated row count; if it does not match expectations, report a conflict/retry per the contract.
- Write audit/event records in the same transaction when needed; avoid reporting success before commit.

A **conceptual** SQL pattern (not a universal schema query):

```sql
UPDATE tasks
SET state = 'APPROVED', version = version + 1
WHERE id = :taskId
  AND tenant_id = :tenantId
  AND state = 'SUBMITTED'
  AND version = :expectedVersion;
```

Even when the update checks state/version, **actor authorization must still be verified on the server**, because this SQL statement only enforces part of the business invariant, not the full authorization policy. If the update affects 0 rows, it may be because the resource does not exist, the state/version changed, or the scope did not match; the application must decide how to return an error without leaking excessive information.

### 11.5. Error Responses and Auditing

In the demo, `Decision.code` distinguishes `FORBIDDEN`, `INVALID_STATE`, and `SELF_APPROVAL` for learning purposes. In production, public responses may need to **collapse sensitive errors** to avoid confirming resource existence or internal state. Audit logs can retain more detail, but must be protected and avoid logging tokens, sensitive secrets, or unnecessary user data.

## 12. Testing Guards: Building a Permission × State Matrix

A common mistake is testing only the happy path. For command policies, **DENY** paths are often more important than ALLOW paths.

Suggested test matrix:

| Command | Actor/permission | State | Expected |
| --- | --- | --- | --- |
| Create | Has CREATE | Valid ID | `ALLOW CREATE` |
| Create | No CREATE | Valid ID | `DENY FORBIDDEN` |
| Create | Has CREATE | Blank ID | `DENY INVALID_INPUT` |
| Submit | Is owner | DRAFT | `ALLOW SUBMIT` |
| Submit | Has SUBMIT, non-owner | DRAFT | `ALLOW SUBMIT` |
| Submit | No SUBMIT, non-owner | DRAFT | `DENY FORBIDDEN` |
| Submit | Is owner | SUBMITTED | `DENY INVALID_STATE` |
| Submit | Null task | — | `DENY INVALID_INPUT` |
| Approve | Has APPROVE, non-owner | SUBMITTED | `ALLOW APPROVE` |
| Approve | No APPROVE | SUBMITTED | `DENY FORBIDDEN` |
| Approve | Has APPROVE, is owner | SUBMITTED | `DENY SELF_APPROVAL` |
| Approve | Has APPROVE, non-owner | DRAFT | `DENY INVALID_STATE` |
| Cancel | Has CANCEL | DRAFT / SUBMITTED | `ALLOW CANCEL` |
| Cancel | Has CANCEL | APPROVED | `DENY INVALID_STATE` |
| Cancel | No CANCEL | DRAFT | `DENY FORBIDDEN` |
| Any | Null actor | — | `DENY UNAUTHENTICATED` |
| Null command | Valid actor | — | `DENY INVALID_COMMAND` |

Also add tests at intersections where multiple errors occur simultaneously to verify precedence. For example, an `Approve` without permission on a `DRAFT` task must return `FORBIDDEN` under the current code, without revealing `INVALID_STATE`. An owner who has `APPROVE` permission attempting to self-approve a `DRAFT` task will receive `SELF_APPROVAL` before `INVALID_STATE`. If the business requires a different precedence, redefine the specification and update the tests rather than reordering cases arbitrarily.

### JUnit Jupiter Suggestion

In a project with the JUnit Jupiter dependency, you can test the policy like this:

```java
// JUnit 5 snippet, placed in the same package as CommandGuardDemo.
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CommandGuardDemoTest {
    @Test
    void unauthorizedActorCannotApproveSubmittedTask() {
        var actor = new CommandGuardDemo.Actor(
            "eve", java.util.Set.of()
        );
        var task = new CommandGuardDemo.Task(
            "T1", "ann", CommandGuardDemo.State.SUBMITTED
        );
        var result = CommandGuardDemo.decide(
            actor, new CommandGuardDemo.Approve(task)
        );
        assertEquals("DENY FORBIDDEN", result.toString());
    }

    @Test
    void approverCannotApproveOwnTask() {
        var actor = new CommandGuardDemo.Actor(
            "ann", java.util.Set.of(CommandGuardDemo.Permission.APPROVE)
        );
        var task = new CommandGuardDemo.Task(
            "T1", "ann", CommandGuardDemo.State.SUBMITTED
        );
        assertEquals(
            "DENY SELF_APPROVAL",
            CommandGuardDemo.decide(
                actor, new CommandGuardDemo.Approve(task)
            ).toString()
        );
    }
}
```

This is a **JUnit 5 test sample**, requiring the dependency/test runner and the same package to access package-private records/methods; it is not part of the standalone program in Section 7. In production applications, test through the official policy service API rather than relying on the demo's visibility modifiers.

Beyond unit tests, you need **integration tests** for loading trusted actors/resources, tenant checks, persistence transactions, idempotency, and concurrent state updates.

## 13. Common Mistakes with Permission/State Guards

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using only `case Approve(var task) -> allow(...)` | Anyone sending Approve is allowed. | Add permission guards and denial branches. |
| Placing an unguarded case before a `when` case of the same type | Specific case is shadowed, possible compile-time error. | Place narrower cases before general cases. |
| Calling `task.state()` when task is null | `NullPointerException`. | Handle null before reading components or use nested patterns with an explicit fallback. |
| Authenticating actor from request body fields | Clients can forge permissions. | Derive actor from a verified security context and trusted permission store. |
| Trusting client-sent `ownerId` | Allows spoofing resource ownership. | Load owner/tenant from the database with scope checks. |
| Checking permission only, skipping state | Approving/canceling tasks in invalid states. | Add state guards after permission checks. |
| Checking state only, skipping permission | Unauthorized users can execute commands. | Verify actor and permissions before sensitive actions. |
| Not testing `when` false | Missing DENY paths. | Test both allowed and denied cases. |
| Adding `default -> allow(...)` | Unrecognized new commands may be granted access. | Fail closed; with a sealed hierarchy, list cases exhaustively. |
| Guard calls DB or mutates state | Unpredictable order, risk of side effects before authorization. | Use pure guards and separate the execution step. |
| Check first, then unconditional update | Race condition/TOCTOU if state or permissions change. | Use transactions, optimistic locking, or conditional updates. |
| Using a denylist of states instead of an allowlist | New states may slip through automatically. | For sensitive actions, prefer a state allowlist. |
| Returning detailed errors to unauthorized actors | May leak resource existence or state. | Choose public error granularity based on your threat model. |
| Treating `ALLOW` as already persisted | Ignores persistence and transaction failures. | Treat `Decision` as an eligibility check; report success only after commit. |
| Treating exhaustive `switch` as sufficient security | Compiler only checks command type coverage. | Test policies, verify principals, and validate real data. |

## 14. Exercises: Extending the Command Policy

### Exercise A — Add `Reopen` for `CANCELLED` Tasks

Extension:

```java
// Additional declaration snippet inside the class containing Command/Task/State.
record Reopen(Task task) implements Command {}
```

Requirements:

- Actor has the new `REOPEN` permission.
- Allowed only when the task is `CANCELLED`.
- Null task must be denied.
- Do not add `default -> allow(...)`.

Suggested case order:

```java
case Reopen(var task) when !actor.can(Permission.REOPEN)
        -> Decision.deny("FORBIDDEN");
case Reopen(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Reopen(var task) when task.state() != State.CANCELLED
        -> Decision.deny("INVALID_STATE");
case Reopen(var task) -> Decision.allow("REOPEN");
```

This is an **extension snippet**, not standalone runnable: you must add `REOPEN` to the `Permission` enum, add `Reopen` to `Command`'s `permits` list, and add the cases above to the switch. The Java 21 compiler will help catch a missing `Reopen` branch if the hierarchy is extended while the switch has no `default`.

### Exercise B — Design a Safe Guard When Adding a New State

If you add `ARCHIVED` to the `State` enum, look at the `Cancel` branch in the demo: it only forbids `APPROVED`/`CANCELLED`, so `ARCHIVED` is **accidentally allowed**.

Rewrite `Cancel` using an allowlist:

```java
case Cancel(var task) when !actor.can(Permission.CANCEL)
        -> Decision.deny("FORBIDDEN");
case Cancel(var task) when task == null
        -> Decision.deny("INVALID_INPUT");
case Cancel(var task) when task.state() == State.DRAFT
        || task.state() == State.SUBMITTED
        -> Decision.allow("CANCEL");
case Cancel(var task) -> Decision.deny("INVALID_STATE");
```

Testing `Cancel(ARCHIVED)` yields `DENY INVALID_STATE`. This is a **fail-closed technique for new states** without needing to list every forbidden state by name.

### Exercise C — Analyze Error Precedence

An actor **lacks the `APPROVE` permission** and tries to approve a `DRAFT` task. According to the demo code, what is the result?

**Answer:** `DENY FORBIDDEN`, because the `!actor.can(APPROVE)` guard precedes the state check. That is intentional behavior to avoid leaking state information to users without permission.

If the actor has `APPROVE` permission and is also the task owner, the result is `DENY SELF_APPROVAL` before checking `state != SUBMITTED`. When changing the order, update both the specification and regression tests.

## 15. Checklist for Bringing Guards into a Real System

1. **Define the trust boundary:** Actor is authenticated on the server; permissions and ownership never come directly from client-editable fields.
2. **Define the policy in a table:** For each command, document permissions, states, ownership rules, ALLOW/DENY outcomes, and error codes.
3. **Close the command set where appropriate:** Use a `sealed interface` and records so the compiler helps catch unhandled new subtypes.
4. **Place narrow guards before broad cases:** `when` branches before unguarded branches of the same type; check null before dereferencing.
5. **Check permissions before revealing state:** Design error messages to match your threat model and prevent resource enumeration.
6. **Consider state allowlists:** Only permit explicitly defined state transitions; new states are denied by default if the policy hasn't been updated.
7. **Keep guards easy to evaluate:** Avoid side effects/I/O in `when`; separate checking from execution.
8. **Re-verify at write time:** Ensure state, scope/tenant, and effective permissions still hold during the transaction; prevent TOCTOU.
9. **Test the matrix:** Every command should have at least ALLOW, missing permission, wrong state, null, and any ownership-specific rules.
10. **Audit and respond at the right level:** Record decision codes needed for investigation, protect logs, and avoid returning sensitive state data to unauthorized actors.
11. **Ensure version compatibility:** Record patterns and `when` guards in switch require Java 21; Java 17 projects need a compatible style.
12. **Do not confuse `Decision` with mutation:** Return actual success only after the command has been executed/committed.

## 16. Summary

**`when` guards in pattern switch** fit a command processor with **many command types** and distinct permission/state conditions very well. With `case Create(...)`, `Submit(...)`, `Approve(...)`, `Cancel(...)`, command-type selection lives in one clear structure; guards express the policy, and the final unguarded branch provides the fallback for each type.

Still, **Java code that compiles does not mean security is correct**. The system must still use trusted actors and resources, handle nulls, deny before leaking state when permissions are insufficient, and prevent self-approval and state-update race conditions. Test both **ALLOW and DENY**, and treat the switch as **where policy is expressed**, not as standalone proof of successful authorization.

**References:**

- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java 21 — Pattern Matching with switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
