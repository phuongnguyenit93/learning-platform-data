# Choosing Semantically Correct Content Instead of Just Removing Conflict Markers

When Git stops on a conflict, deleting the `<<<<<<<`, `=======`, and `>>>>>>>` lines only clears the markers from the file. It does not guarantee the program preserves the intent of both changes. A good merge result must reflect the right requirements, business rules, and contracts between parts of the system. This lesson guides you through reading the sides of a conflict, reasoning about the required outcome, and verifying the result before continuing a merge or rebase.

## 1. Resolving a Conflict Is a Decision About Meaning

Git can point out two content blocks it cannot automatically combine under its rules. Git does not know why the authors changed the code, which business invariants must be preserved, or whether the two changes depend on each other.

For example, one branch increases the retry count because an external service is flaky. Another branch decreases the retry count because a payment operation could create duplicate transactions. If you simply pick one side, you may lose the other branch's purpose. The right outcome might require distinguishing operations that are safe to retry from operations that are not, rather than picking a single number.

Therefore, treat a conflict region as a set of questions to answer:

- What problem is each side trying to solve?
- Which rules or invariants must always hold after combining?
- Are the two changes independent, complementary, or conflicting in requirements?
- What behavior must the final result express, even if the content does not match either side verbatim?

A file free of conflict markers is only a prerequisite for Git to continue. The quality of the decision must be judged by the meaning and behavior of the result.

## 2. Reading All Three Versions Before Editing

In a standard content conflict, inspect the three versions Git stores in the index:

| Version | Meaning in a standard merge |
|---|---|
| Base (stage 1) | Common content before the two branches diverged |
| Ours (stage 2) | Content on the current branch |
| Theirs (stage 3) | Content from the branch being merged in |

Suppose Git displays:

```text
<<<<<<< HEAD
int maxAttempts = 5;
=======
int maxAttempts = 2;
>>>>>>> feature/safe-retry
```

Do not rush to pick `5` or `2`. First, check the original line and change history to understand why the two branches produced different values. You can run:

```bash
git status
git diff --cc -- path/to/RetryPolicy.java
git show :1:path/to/RetryPolicy.java
git show :2:path/to/RetryPolicy.java
git show :3:path/to/RetryPolicy.java
```

`git diff --cc` displays the combined diff of the conflict region. `git show :1:`, `:2:`, and `:3:` read base, ours, and theirs from the index, respectively. Replace the example path with the actual file. Some conflict types do not have all three stages; for example, a newly added or deleted file may lack the corresponding version.

You can use these quick options to compare the working tree against each stage:

```bash
git diff --base -- path/to/file
git diff --ours -- path/to/file
git diff --theirs -- path/to/file
```

If `diff3` or `zdiff3` display style is enabled, Git includes the base section in the marked block, typically looking like:

```text
<<<<<<< HEAD
int maxAttempts = 5;
||||||| parent of ...
int maxAttempts = 3;
=======
int maxAttempts = 2;
>>>>>>> feature/safe-retry
```

The base section makes it clear how each side changed from the initial value. It is especially helpful when the two current blocks differ and the reason for the change is not yet obvious.

**Note during rebase:** Git's assignment of `ours` and `theirs` is easy to confuse. During a rebase, `ours` is usually the state of the target branch (*upstream/onto*) onto which commits are being applied; `theirs` is the commit from the branch being rebased at the current step. Confirm the active operation in `git status` and read the contents of the stages; do not infer solely from branch names or "Current/Incoming" buttons in tools.

## 3. Workflow for Choosing Content by Meaning

### Step 1: Identify the Goal of Each Change

Read commit messages, related diffs, and the file's context. Find out what problem each branch set out to solve. Branch names or commit titles can give hints, but you need to verify against the actual code and requirements.

If the intent cannot be determined from history, talk to the author of the change or the business owner. Do not guess important rules from bare numbers or variable names alone.

### Step 2: Identify Conditions That Must Remain True

Write down the invariants the outcome must satisfy. For example:

- A payment transaction must not be executed multiple times unintentionally.
- Total processing time must stay within SLA limits.
- All call sites must use the new contract.
- Legacy data must remain readable during the migration period.
- Environment configuration must not expose secrets or overwrite required values.

These conditions are the criteria for choosing content. If two requirements genuinely conflict, clarify the product or business decision before concluding.

### Step 3: Identify the Relationship Between the Two Changes

| Relationship | How to reason when combining |
|---|---|
| Two independent changes | Keep both if they do not break shared invariants |
| Two complementary changes | Combine the behavior of both, even if the code needs rearranging |
| Two changes modifying the same rule | Decide based on the active requirement and invariants to preserve |
| One change replaces an old design | Port still-needed logic into the new design, then drop the old part |
| One side deletes, the other edits | Verify whether the file or feature is still in use before keeping or deleting |

### Step 4: Produce a Clear Outcome

Edit the conflict region into complete, valid content. You may keep one side as-is, combine both sides, rewrite the code block, or move logic elsewhere. The result does not have to match either version verbatim.

When rewriting, keep function names, data types, conditions, execution order, and error messages consistent with the surrounding contract. Check imports, call sites, configuration, and related files, because a conflict on one line may reflect a broader change.

### Step 5: Verify Before Continuing

Re-read the entire file after editing, checking conditional branches and edge cases. Then inspect the diff, run appropriate checks, and confirm no conflict markers remain. Only stage the result after you understand the content you are about to place in the index.

## 4. Example: Combining Two Retry Policies

Suppose the base version has:

```java
public Result submit(Payment payment) {
    return gateway.send(payment);
}
```

Branch `feature/retry-network` adds retries on transient network errors. Branch `feature/payment-safety` requires not resending a payment if it is unknown whether the previous attempt was already processed. Both branches may edit the error-handling block and create a conflict.

A wrong resolution is picking the entire retry branch just because it adds resilience. That could submit the same payment multiple times. Picking the entire safety branch could also lose resilience for errors where the request definitely was never sent.

Before writing the result, verify whether the gateway supports an idempotency key and whether failures before versus after request acceptance can be distinguished. If the contract permits safe retries via an idempotency key, the result can be structured as:

```java
public Result submit(Payment payment) {
    String idempotencyKey = payment.id();
    return retryPolicy.execute(() ->
        gateway.send(payment, idempotencyKey)
    );
}
```

This illustrative snippet is only appropriate if `gateway.send` truly supports an idempotency key and the server guarantees repeated requests with the same key do not create a new transaction. Without that guarantee, you cannot conclude that adding a retry loop is safe; you must design a status-query or reconciliation mechanism before resending.

Tests should cover at least:

- Failures occurring before the gateway receives the request.
- Cases where the gateway processed the request but the response was lost in transit.
- Repeated requests with the same idempotency key.
- Reusing an idempotency key for different payment details.
- Exhausting retry attempts or exceeding the allowed processing timeout.

The deciding factor lies in the payment system's contract. Git cannot deduce that contract from two code snippets.

## 5. Example: Porting Logic When One Branch Renames an API

The base has a method:

```java
public Money calculateFee(Order order) {
    return feeCalculator.calculate(order);
}
```

One branch renames the method to `calculateShippingFee` to clarify its scope. The other branch adds a member discount rule to the old method. If you accept only the rename version, the discount rule is lost. If you accept only the discount version, the new naming design is lost.

A semantically sound result can port the discount rule into the new method:

```java
public Money calculateShippingFee(Order order) {
    Money baseFee = feeCalculator.calculate(order);
    return memberDiscount.apply(order.customer(), baseFee);
}
```

Next, find all call sites of `calculateFee` and update them to the new contract, or maintain a compatibility method during the transition period if other modules still depend on the old API. Also verify that `memberDiscount` specifically discounts the shipping fee rather than the entire order total or a different fee.

You can use repository search to audit related calls and definitions, then run compile/test suites for dependent modules. A file having no remaining conflict markers does not guarantee call sites in other files have been updated.

## 6. Example: Deciding When One Side Deletes and the Other Edits

Suppose branch A deletes `LegacyTokenValidator.java` because the system moved to `TokenValidator`. Branch B edits `LegacyTokenValidator.java` to add a token expiration check. Git may report a modify/delete conflict.

Do not restore the file simply because branch B has a new change, and do not delete it immediately just because branch A removed it. Verify:

1. Have all call sites migrated to `TokenValidator`?
2. Does the new validator already include the expiration check rule from branch B?
3. Does any data, configuration, or module still require the old API?
4. Is a temporary adapter needed for backward compatibility?

If the new validator lacks the expiration rule, move that rule into the new validator and keep the deletion of the old file. If clients still depend on the old API, keep an adapter or establish a clear migration plan. The right outcome may be deleting the old file while preserving the behavior introduced by branch B's change.

## 7. Using Conflict Resolution Tools Properly

IDEs and merge editors typically split the screen into the current version, the incoming version, and the final result. They help select blocks or edit the result directly, yet labels like "Accept Current", "Accept Incoming", or "Accept Both" are merely text operations. The resolver must still verify the meaning of the result.

A few notes:

- **Accept Current:** appropriate when requirements confirm that the current side's content is what should be kept for that region.
- **Accept Incoming:** appropriate when the incoming change properly replaces the old logic without dropping any active requirements.
- **Accept Both:** only useful when both blocks can coexist. Concatenating two blocks sequentially can create duplicate code, wrong ordering, or execute the same action twice.
- **Manual editing:** often necessary when combining conditions, restructuring code, or porting logic to a new API.

If using CLI or IDE actions to take one entire side, remember that such an action can overwrite in-progress edits in the working tree. Only do so after inspecting the versions and understanding exactly what will be replaced.

## 8. Verifying the Result Before Marking Resolved

After editing, perform checks appropriate to the type of change:

```bash
git diff -- path/to/file
git diff --check
git status
```

Read the diff to confirm the result contains all required logic from the changes to keep. `git diff --check` catches certain whitespace errors in the diff; it does not prove the code is right and does not replace searching for conflict markers.

You can search for leftover markers in the file being handled using text search, for example:

```bash
rg -n '^(<<<<<<<|=======|>>>>>>>)' path/to/file
```

The search command may match valid delimiter lines in certain document formats; inspect the matches instead of deleting them blindly. Then run unit tests for the modified logic, integration tests for cross-module contracts, and a build appropriate to the scope of the change.

Once the result is verified, mark the path as resolved:

```bash
git add path/to/file
git diff --cached -- path/to/file
git status
```

`git add` puts the working tree version into the index and marks the path as no longer unmerged. Git does not check whether the content still has conflict markers; thus, a file still containing markers can be staged as if resolved. Inspect the staged diff before continuing.

Once all paths are resolved and checks pass, continue the paused operation:

```bash
git merge --continue
```

Or, if rebasing:

```bash
git rebase --continue
```

Only use the command matching the current Git state. If conflicts occur on subsequent commits during a rebase, repeat the review and verification process for those commits as well.

## 9. Self-Check List

Before concluding that a conflict is properly resolved, ask yourself:

- Do I understand the goal of the changes on both sides?
- Have I checked the base or history to see the original content?
- Does the result preserve active business rules and contracts?
- Have I audited call sites, configuration, data, and dependent modules?
- Have error cases, edge cases, and retry/duplicate scenarios been considered?
- Have I reviewed the diff, searched for leftover markers, and run relevant tests?
- Is the content in the index the exact final version I intend to include in the merge or rebase?

## 10. Key Takeaways

Do not judge a resolution by the absence of conflict markers. Read the base and both sides, identify the intent and invariants to preserve, and produce behavior that aligns with the system's contracts. Sometimes you choose one side, and sometimes you must combine or rewrite both. Mark a path as resolved only after verifying its content, dependencies, and runtime behavior.
