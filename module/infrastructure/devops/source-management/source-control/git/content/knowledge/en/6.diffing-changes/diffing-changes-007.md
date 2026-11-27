# Word-Level Diffing and Adjusting Context Lines

When viewing changes with `git diff`, Git normally presents differences line by line. This works very well when adding, deleting, or moving entire lines, but it can be hard to read when a long line only changes a few words, an expression, or a single parameter. For example, changing a condition from `status == "NEW"` to `status != "CANCELLED"` causes the entire line to be marked as changed even though most of its content remains identical.

Git provides **word diff** to highlight changes at the word level and lets you adjust the number of unchanged lines around each diff region. Both capabilities make reviews more accurate: word diff reveals which part of a line actually differs, while context lines provide enough surrounding code or text to understand the setting in which the change sits.

In a source control workflow, choose the display mode suited to the content type and review purpose. Word diffs aid in reading small intra-line changes; context lines help inspect control flow, conditions, and surrounding structure. Both options only alter how Git renders the diff—they do not modify the working tree, staging area, or commits.

## 1. When Do You Need Word Diff?

A line-based diff marks an old line and a new line whenever the line's content changes. For short lines, this is usually clear enough. For long lines, JSON, documentation, queries, or parameter lists, the actual difference can get buried among many identical characters.

Example before and after:

```java
String message = "Payment is pending for order " + orderId;
```

After editing:

```java
String message = "Payment is completed for order " + orderId;
```

A line-based diff marks the entire old line and new line. Word diff pinpoints that `pending` and `completed` are the differing tokens, helping the reviewer focus on the business-logic change.

Word diff is useful when:

- A long line changes only a single word or expression.
- Editing documentation prose, messages, SQL queries, or configuration values.
- Adding or removing parameters in a function call.
- Renaming a variable or replacing a constant in an existing line.
- Reviewing formatting updates with substantial unchanged text on the same line.

Word diff is less useful when:

- Changes primarily involve moving or refactoring multiple lines.
- Content relies heavily on indentation or block structure.
- Files are binary, generated, or use specialized formats.
- You need to verify line ordering, declaration placement, or block scopes.

For source code, read word diffs alongside line-based diffs and surrounding context. A change of just a few characters can alter a condition, permission check, or the behavior of an entire function.

## 2. Basic Word Diff Syntax

Add `--word-diff` to your diff command:

```bash
git diff --word-diff
```

Git marks removed and added words inline. By default, words are delimited by whitespace and the display mode is `plain`.

It can be used with other diff forms:

```bash
# Changes in the working tree vs. the index
git diff --word-diff

# Staged changes vs. HEAD
git diff --cached --word-diff

# Compare two commits
git diff --word-diff HEAD~1 HEAD

# View changes of a single commit
git show --word-diff HEAD
```

By default, `git diff` does not show untracked files. If you just created a new file, you must stage it or use another tool to inspect its content before staging; word diff only operates on content evaluated by the Git comparison.

## 3. Display Modes of --word-diff

Git supports four modes:

| Mode | How It Displays | When to Use |
| --- | --- | --- |
| `color` | Highlights additions and deletions with color in the terminal | Direct review, making small changes easy to spot |
| `plain` | Wraps deletions in `[- -]` and additions in `{+ +}` | Terminal does not support color or plain-text output is needed |
| `porcelain` | Line-oriented output marking additions, deletions, and newlines | Processing output with scripts or other tools |
| `none` | Disables word diff, reverting to standard display | Overriding a word diff setting enabled in configuration |

### Color Mode

```bash
git diff --word-diff=color
```

Removed and added parts are colored according to your Git diff configuration. Exact colors may vary depending on your theme, terminal, and `color.diff` settings.

`color` is usually easiest to read during direct reviews. If your terminal does not render colors, use `plain` or check your color and pager configuration.

### Plain Mode

```bash
git diff --word-diff=plain
```

Illustrative example:

```text
const status = [-"PENDING";-]{+"PAID";+}
```

`[- ... -]` marks removed content; `{+ ... +}` marks added content. These markers are Git presentation delimiters, not characters inserted into the source file.

Plain mode is convenient when copying output to places that do not preserve colors. However, if the actual file contains strings resembling those markers, readers must rely on the diff structure to tell them apart.

### Porcelain Mode

```bash
git diff --word-diff=porcelain
```

Porcelain produces line-oriented output with prefixes denoting unchanged, added, and removed segments. A `~` line is used to represent newline boundaries. This mode is designed for programmatic parsing rather than being the friendliest format for manual review.

If you need to consume the output in a script, consult the documentation for your installed Git version and avoid assuming every token always fits on a single output line.

### None Mode

```bash
git diff --word-diff=none
```

The `none` mode is useful when personal configuration enables word diff by default, but a specific command needs standard line-by-line diffing.

## 4. Using --color-words

The following command is a shorthand:

```bash
git diff --color-words
```

`--color-words` is equivalent to `--word-diff=color`. You can pass a regex to define what counts as a word:

```bash
git diff --color-words='[[:alnum:]_]+'
```

This example treats sequences of letters, digits, and underscores as a word. Note: any characters falling between regex matches are treated as whitespace and ignored when finding differences. Thus, a regex that matches only alphanumeric characters can cause punctuation changes to go unshown. Regex behavior is explained in detail in the next section.

You can use `--word-diff=color --word-diff-regex=...` when you want to specify both the display mode and the token rule explicitly:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

Both approaches colorize word-level changes; the second syntax makes each option explicit and easier to combine with other flags.

## 5. Customizing How Git Recognizes a Word

By default, Git treats any non-whitespace character sequence as a word. In code, this means `paymentTotal;` may be treated as a single token, including the semicolon. When edited to `paymentAmount;`, the entire token is treated as changed.

The `--word-diff-regex=<regex>` option lets you define tokens with a custom rule:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

In this example:

- `[[:alnum:]_]+` matches a sequence of alphanumeric characters or underscores, usually corresponding to identifiers.
- `[^[:space:][:alnum:]_]` matches a single character that is not whitespace, alphanumeric, or an underscore; this keeps punctuation as separate tokens.
- Whitespace characters between tokens are not treated as word content.

With this regex, changing `calculateTotal()` to `calculateAmount()` shows that the identifier changed while parentheses and punctuation are evaluated separately.

### Important Caution About Regexes

Git treats each non-overlapping match of the regex as a word. Text lying between matches is treated as whitespace and ignored when computing differences. If the regex does not match periods, commas, parentheses, or operators, changes to those characters may be hidden.

For example, the regex:

```bash
--word-diff-regex='[[:alnum:]_]+'
```

can be handy when you only care about prose words in documentation, but it is unsuitable for code review when punctuation carries meaning. Changing `a == b` to `a != b` must display the operator change; use a regex that preserves punctuation or use a standard line-based diff.

The regex should match tokens within a single line. Git does not treat a match spanning across a newline as a multi-line word; matches containing newlines are split at line boundaries. Keep regexes simple, test them on a small diff, and cross-check the output against the actual file content.

## 6. Example Regexes by Content Type

The patterns below are suggestions. Verify them with your language, locale, and Git version.

| Purpose | Suggested Regex | Characteristics |
| --- | --- | --- |
| Whitespace-delimited words | Omit regex | Keeps Git's default word splitting |
| Identifiers and punctuation | `[[:alnum:]_]+|[^[:space:][:alnum:]_]` | Keeps identifiers and symbols separate |
| Prose words only | `[[:alnum:]_]+` | Unmatched punctuation and whitespace are ignored |
| Tokens with letters, digits, dots, and hyphens | `[[:alnum:]_.-]+|[^[:space:][:alnum:]_.-]` | Fits certain config keys or version numbers |

### Comparing Prose

When reviewing documentation text, you might only care about words:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+'
```

Example sentence change:

```text
The service accepts pending payments.
The service accepts completed payments.
```

Word diff highlights `pending` and `completed`. However, if a period is changed to a question mark, the regex above might not show the punctuation difference. Therefore, for content requiring spelling, punctuation, or formatting checks, also review with a line-based diff.

### Comparing Code

For source code, keep identifiers and punctuation:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

Example:

```java
if (amount > limit) {
```

changed to:

```java
if (amount >= limit) {
```

The regex above keeps `>` and `=` as separate tokens so the comparison operator change remains visible. This is why you should avoid alphanumeric-only regexes when reviewing code.

### Comparing Configuration or JSON

JSON has many braces, colons, commas, and quotes. If a regex drops punctuation, structural changes can be obscured. Use a regex that preserves punctuation:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

For configuration files with hyphens or dots inside keys, consider including them in the identifier group if you want to treat the entire key as a single token. When JSON or YAML structure changes substantially, a formatter-aware diff or line-based diff may be easier to review.

## 7. Combining Word Diff with Context Lines

Word diff only clarifies what changed inside a line. It does not by itself tell you which function the line sits in, where it is called, or which conditional branch it belongs to. Add context lines to retain unchanged lines around each diff region:

```bash
git diff --word-diff=color -U5
```

`-U5` asks Git to show five lines of context before and after each changed region. You can also use the long form:

```bash
git diff --word-diff=color --unified=5
```

Context lines are unchanged lines included in the output to help readers locate the changes. They are not part of the added or removed content.

## 8. Adjusting Context Lines with -U

The `-U<n>` or `--unified=<n>` option specifies the number of context lines around each hunk:

| Command | Result |
| --- | --- |
| `git diff` | Default is typically 3 lines of context |
| `git diff -U0` | Shows no context lines |
| `git diff -U2` | Shows 2 lines before and after |
| `git diff -U5` | Shows 5 lines before and after |
| `git diff --unified=10` | Shows 10 lines before and after |

### Minimal Context: -U0

```bash
git diff -U0
```

This mode keeps output short, convenient when pinpointing exact changed lines or when another tool already provides surrounding context. However, reviewers may find it difficult to tell which function, conditional block, or config section a change belongs to.

Do not use `-U0` as the sole option for business-logic reviews.

### Moderate Context: -U3 or -U5

```bash
git diff --word-diff=color -U3
git diff --word-diff=color -U5
```

Three lines is the standard unified diff default. Five lines can be helpful when code contains closely spaced conditions or related configuration blocks.

### Extended Context: -U10

```bash
git diff --word-diff=color -U10
```

Increasing context helps reviewers understand surrounding logic, at the cost of longer output. In large files with many changed regions, too much context can make a diff harder to scan quickly.

## 9. Understanding Hunks and Headers in Unified Diffs

A diff is typically split into sections called hunks. A header has the form:

```text
@@ -20,7 +20,8 @@
```

Meaning:

- `-20,7`: the old side starts at line 20 and spans 7 lines in the displayed region.
- `+20,8`: the new side starts at line 20 and spans 8 lines in the displayed region.
- Subsequent lines represent old, new, and unchanged content.

Context lines connect the changed lines to their surroundings. Lowering `-U` shortens hunks; raising `-U` includes more unchanged lines.

Illustrative structural example:

```diff
@@ -20,5 +20,5 @@
 public void settle(Payment payment) {
     validate(payment);
-    payment.complete();
+    payment.completeWithReceipt();
     publishEvent(payment);
 }
```

With `-U0`, `validate`, `publishEvent`, and the braces might not appear. Reviewers see the changed line but have less visibility into the execution flow.

## 10. Using --inter-hunk-context to Merge Nearby Diff Regions

A file can contain multiple separate hunks. When two hunks sit close together, `--inter-hunk-context=<n>` allows Git to include up to `<n>` lines between them and merge them into a single larger hunk:

```bash
git diff --inter-hunk-context=5
```

This option differs from `-U`:

- `-U<n>` adjusts the number of context lines around each hunk.
- `--inter-hunk-context=<n>` controls whether adjacent hunks are merged by showing the lines between them.

Example:

```bash
git diff -U2 --inter-hunk-context=5
```

This command uses two lines of context around changed regions and merges hunks separated by no more than five lines. It is helpful when nearby edits belong to the same logical block.

If you set the value too high, unrelated changes can get lumped into one long hunk. Pick a small value just large enough to preserve relationships between adjacent edits.

## 11. Showing the Entire Function with --function-context

Sometimes a few lines of context are not enough to understand a change. Run:

```bash
git diff --function-context
```

Or the short form:

```bash
git diff -W
```

This option shows the entire function enclosing the changed region according to Git's function-detection rules. It is useful when a single changed line depends on several lines within the same function.

Git does not parse every language like a compiler. Function detection relies on diff drivers and xfuncname patterns known to Git. For custom languages or unusual formats, function context boundaries may not be as accurate as expected.

You can combine function context with word diff:

```bash
git diff --word-diff=color --function-context
```

If a function is very long, the output can become huge. Use it only when reviewers need the entire function body to understand the change.

## 12. Combining Options in Common Workflows

### Reviewing Unstaged Changes

```bash
git diff --word-diff=color -U5
```

This command inspects changes in the working tree compared to the index, highlighting modified words and keeping five lines of context.

### Reviewing Content Ready to Commit

```bash
git diff --cached --word-diff=color -U5
```

`--cached` is an alias for `--staged`. It compares the index with `HEAD`, i.e., the content staged for commit.

### Reviewing a Single Commit

```bash
git show --word-diff=color -U5 <commit>
```

`git show` displays the commit along with its diff. You can add `--function-context` if you need to inspect the entire enclosing function.

### Reviewing Differences Between Two Branches

```bash
git diff --word-diff=color -U5 main...feature/payment
```

With the three-dot syntax, Git compares the merge base of the two branches against the second branch tip. This is typically how you inspect changes introduced by a feature branch since diverging from `main`.

If you want to compare the two snapshots directly:

```bash
git diff --word-diff=color -U5 main feature/payment
```

Two space-separated revisions compare the trees of those two endpoints; the result may differ from the three-dot syntax if the base branch has moved forward.

### Reviewing a Specific File

```bash
git diff --word-diff=color -U5 -- src/PaymentService.java
```

Limiting the path focuses attention on one file and reduces output volume. For filenames starting with a hyphen or containing special characters, use `--` to separate options from paths.

## 13. Saving Defaults with Git Config

If you consistently prefer a particular context line count, you can set a default:

```bash
git config --global diff.context 5
```

This value applies to diff commands that honor the corresponding setting. Whenever you need shorter output, you can still override it per command:

```bash
git diff -U0
```

You can set a default token rule:

```bash
git config --global diff.wordRegex '[[:alnum:]_]+|[^[:space:][:alnum:]_]'
```

Setting a global regex affects word-diff runs that do not specify an explicit regex. Because an incomplete regex can hide punctuation differences, test it on a small diff before applying it across all repositories.

Inspect the value and origin of configuration settings:

```bash
git config --show-origin --get diff.context
git config --show-origin --get diff.wordRegex
```

Remove a global setting when no longer needed:

```bash
git config --global --unset diff.context
git config --global --unset diff.wordRegex
```

If a repository has its own conventions, use `--local` to apply the setting only within the current repository.

## 14. Practical Example: Reviewing a Condition Change

Suppose the original code is:

```java
if (payment.getAmount() > account.getLimit()) {
    reject(payment);
}
```

Updated code:

```java
if (payment.getAmount() >= account.getLimit()) {
    reject(payment);
}
```

A line-based diff marks the entire conditional line. Word diff with a punctuation-preserving regex highlights the operator `>` changing to `>=`:

```bash
git diff --word-diff=color \
  --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]' \
  -U5
```

During review, verify the business rule: should an amount equal to the limit be included or rejected? Word diff only helps you spot the changed characters; it does not determine whether the logic is right.

## 15. Practical Example: Reviewing a Query Change

Before:

```sql
SELECT id, status
FROM payments
WHERE status = 'PENDING' AND deleted_at IS NULL;
```

After:

```sql
SELECT id, status
FROM payments
WHERE status IN ('PENDING', 'PROCESSING') AND deleted_at IS NULL;
```

Run:

```bash
git diff --word-diff=color -U4 -- db/queries/payment.sql
```

Word diff highlights that `=` was replaced by `IN` and the `PROCESSING` status was added. Context lines retain `SELECT`, `FROM`, and surrounding predicates so reviewers understand which table the query filters.

Reviewers still need to verify indexes, cardinality, business results, and performance impact. Diff presentation does not replace running query tests.

## 16. Practical Example: Reviewing a Documentation Change

Before:

```text
The payment request is stored after validation.
```

After:

```text
The payment request is published after validation.
```

Use word diff:

```bash
git diff --word-diff=plain -U2 -- docs/payment-flow.md
```

The output shows that `stored` was replaced with `published`. In documentation, changing a single word can alter architectural meaning or API guarantees; reviewers must verify whether the new description matches actual behavior.

## 17. Reading Output and Avoiding Misinterpretations

Key points to remember:

- Word diff splits tokens by regex; it does not understand programming language semantics.
- Characters not matched by the regex may be ignored during word comparison.
- Different tokenizers can produce different output even when the file is unchanged.
- Context lines only add unchanged lines to the output; they do not change the scope of staged content.
- `--inter-hunk-context` merges nearby hunks; it does not replace context lines around hunks.
- `--function-context` relies on function-recognition rules and is not guaranteed to parse every language accurately.
- Diffs do not automatically include untracked files in the default comparison.

If the output looks unusual, re-run the standard diff:

```bash
git diff
```

Then try each option individually:

```bash
git diff --word-diff=color
git diff -U5
git diff --word-diff=color -U5
```

Comparing the outputs helps isolate whether an oddity stems from the tokenizer, the context setting, or the actual content changes.

## 18. Choosing Appropriate Settings for Reviews

| Purpose | Recommendation |
| --- | --- |
| Routine code review | `git diff --word-diff=color -U3` |
| Reviewing long lines or JSON | Word diff with punctuation-preserving regex, combined with `-U5` |
| Reviewing changes within one function | `--function-context` or `-W` |
| Grouping multiple nearby hunks | `--inter-hunk-context=3` or a suitable small value |
| Short output for automated checks | `-U0` or `--word-diff=porcelain` depending on purpose |
| Reviewing prose and documentation | Word diff with a word regex; double-check punctuation with a normal diff |

No single configuration fits every file type. Choose a display format that lets reviewers clearly see the changes with enough context to assess impact.

## 19. Common Issues

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Word diff does not show punctuation changes | Regex matches only alphanumeric characters, so punctuation is ignored | Use a regex that keeps punctuation or omit the custom regex |
| Word diff marks an entire long token | Default tokenizer splits on whitespace | Choose an appropriate `--word-diff-regex` |
| Output has no color | Mode is not `color`, terminal/pager lacks support, or color is disabled | Use `--word-diff=plain` or check `color.diff` |
| Diff is too short and hard to follow | Using `-U0` or too little context | Increase to `-U3`, `-U5`, or use `-W` |
| Diff is too long | Large context or overly broad hunk merging | Reduce `-U` and `--inter-hunk-context` |
| Two nearby regions remain separate | Distance between hunks exceeds inter-hunk threshold | Increase `--inter-hunk-context` slightly |
| Function context is inaccurate | Git cannot recognize function boundaries for the language | Use fixed context or configure an appropriate diff driver |
| New file does not appear | Untracked files are outside the default comparison | Check status and stage the file when appropriate |

## 20. Recommended Review Workflow

When reviewing changes with long lines or critical logic:

1. Check repository status:

   ```bash
   git status -sb
   ```

2. View the line-based diff to grasp overall scope:

   ```bash
   git diff
   ```

3. Inspect intra-line changes:

   ```bash
   git diff --word-diff=color -U5
   ```

4. If you need to understand the entire enclosing function, run:

   ```bash
   git diff --word-diff=color --function-context
   ```

5. Check staged content specifically:

   ```bash
   git diff --cached --word-diff=color -U5
   ```

6. Run tests, formatters, linters, or domain checks appropriate to the change.
7. Re-read the standard diff before committing to ensure no structural, punctuation, or whitespace changes were missed.

This workflow lets reviewers use word diff to catch subtle edits while still verifying broader structure and context.

## 21. Hands-On Practice

Try these exercises in a test repository:

### Exercise 1 — Word-Level Comparison

1. Create a text file containing a long sentence.
2. Commit the initial version.
3. Change a single word in the middle of the sentence.
4. Run `git diff` and observe the line-based diff.
5. Run `git diff --word-diff=plain` and then `git diff --word-diff=color`.
6. Identify the removed word and the added word.

### Exercise 2 — Testing Regexes

1. Create a line of code containing identifiers and an operator.
2. Change `>` to `>=`.
3. Run word diff with the regex `[[:alnum:]_]+`.
4. Observe whether the operator change is shown.
5. Re-run with a regex that preserves punctuation:

   ```bash
   git diff --word-diff=color \
     --word-diff-regex='[[:alnum:]_]+|[^[:space:][:alnum:]_]'
   ```

6. Explain why the two results differ.

### Exercise 3 — Adjusting Context

1. Edit two regions a few lines apart in the same file.
2. Run `git diff -U0`.
3. Run `git diff -U3` and `git diff -U8`.
4. Run `git diff -U2 --inter-hunk-context=5`.
5. Compare how Git groups the hunks.
6. Use `git diff -W` to view function context and evaluate how helpful it is.

### Exercise 4 — Reviewing Staged Changes

1. Stage part of your changes.
2. Run `git diff --cached --word-diff=color -U5`.
3. Compare with `git diff` to distinguish staged and unstaged changes.
4. Verify the content intended for the commit.

## 22. Self-Check Questions

1. What limitation of line-based diffs does word diff address?
2. How do `--word-diff=color`, `plain`, `porcelain`, and `none` differ?
3. Which option is `--color-words` equivalent to?
4. Why can an alphanumeric-only regex hide punctuation changes?
5. Which part of the output do `-U0`, `-U3`, and `-U10` affect?
6. How does `--inter-hunk-context` differ from `-U`?
7. What mechanism does `--function-context` rely on, and what are its limitations?
8. How do you view a word diff of staged changes?
9. Why should you view a line-based diff alongside word diff when reviewing code?
10. If a new file is unstaged, why might `git diff` not display it?

## Conclusion

`--word-diff` lets you inspect changes at the word level; the `color`, `plain`, `porcelain`, and `none` modes control presentation. `--word-diff-regex` customizes how Git splits tokens, though characters unmatched by the regex can be skipped when finding differences, so regexes used for code should preserve punctuation. `-U<n>` adjusts context line count, `--inter-hunk-context` merges nearby hunks, and `--function-context` expands to the enclosing function according to Git's detection rules. Combining the right options improves review clarity without altering repository contents.
