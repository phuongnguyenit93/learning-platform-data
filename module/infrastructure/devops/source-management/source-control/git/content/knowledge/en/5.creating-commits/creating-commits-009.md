# Using Trailers to Record Co-Authors and Work References

A commit usually needs to answer two questions: what does this change do, and who or what work does it relate to? The subject and description explain the purpose, while trailers at the end of the commit message can record structured information such as co-authors, reviewers, tickets, or contribution-policy requirements.

For example, a commit might end with:

~~~text
Co-authored-by: Linh Nguyen <linh@example.com>
Reviewed-by: Minh Tran <minh@example.com>
Refs: PAY-482
~~~

These lines are still plain text inside the commit message, yet they follow a trailer format recognized by Git and many platforms. This lesson covers trailer structure, how to add and read them with Git, how to credit co-authors and reference work items, and the differences between trailers, sign-offs, and cryptographic signatures.

This lesson belongs to the **Creating Commits** chapter of the **SOURCE_CONTROL_GIT** module. The module teaches Git from the working tree, staging area, commits, and history through branches, merging, rebasing, remotes, and tags, while building skills in collaborating over branches, resolving conflicts, tracing changes, and recovering from mistakes without losing important history. Using trailers properly keeps commit history traceable and makes attribution clearer.

## 1. What Is a Trailer?

A trailer is a metadata line placed at the end of a commit message. Common form:

~~~text
Token: value
~~~

Examples:

~~~text
Co-authored-by: An Le <an@example.com>
Refs: PROJ-123
Reviewed-by: Binh Pham <binh@example.com>
~~~

Here:

- **Token** is the field name, such as <code>Co-authored-by</code>, <code>Reviewed-by</code>, or <code>Refs</code>.
- **Separator** is typically a colon <code>:</code>.
- **Value** is the field content, such as a name/email or ticket ID.

Trailers usually sit in a dedicated block at the end of the commit message, separated from the description by a blank line. For example:

~~~text
feat(payment): retry request when gateway times out

Retry transient gateway failures with a bounded backoff.
Keep the original request identifier across attempts.

Co-authored-by: An Le <an@example.com>
Refs: PAY-482
Reviewed-by: Binh Pham <binh@example.com>
~~~

The top line is the subject, the next paragraph is the body, and the final lines are trailers. This layout helps readers distinguish explanatory prose from metadata.

### Trailers Are Not a Separate Field in the Commit Object

Git stores the commit message as a text block inside the commit object. Trailers are not stored in an independent metadata table alongside author, committer, tree, and parent. Git has rules to recognize trailer lines at the end of a message, while external tools or platforms decide how each token is interpreted.

Consequently, a custom trailer like <code>Refs: PAY-482</code> can be useful to a team even though core Git does not know which tracking system PAY-482 belongs to. Your project management platform or team scripts can parse it and create links.

## 2. Structure of a Commit Message with Trailers

A readable commit message typically has three parts:

1. A short subject describing the change.
2. A body explaining why or how when needed.
3. Trailers at the end, one line per structured piece of information.

For example:

~~~text
fix(api): handle expired access token

Refresh the access token once before returning an authentication error.
Preserve the request body so the retry does not lose user input.

Co-authored-by: Ha Vo <ha@example.com>
Refs: AUTH-219
Reviewed-by: Nam Do <nam@example.com>
~~~

Not every commit must contain all three parts. A minor fix might need only a subject and a trailer; a complex change may call for an explanatory body.

Keep trailers at the end of the message. Placing normal notes or prose paragraphs after trailers can prevent parsers from recognizing the trailer block as expected.

### Trailers Can Have Multi-Line Values

Some trailers have long values or continuation lines. Continuation lines typically start with whitespace. However, for cross-tool compatibility, prefer concise single-line values unless multi-line content is genuinely needed.

## 3. Crediting Co-Authors with Co-authored-by

In a standard Git commit, the commit object has one <code>author</code> field and one <code>committer</code> field. When multiple people collaborate on a change, the <code>Co-authored-by</code> trailer is a common way to credit additional contributors in the commit message.

Format:

~~~text
Co-authored-by: Full Name <email@example.com>
~~~

Example:

~~~text
feat(checkout): add address validation

Validate required address fields before creating an order.

Co-authored-by: Mai Nguyen <mai@example.com>
Co-authored-by: Khoa Tran <khoa@example.com>
~~~

Multiple <code>Co-authored-by</code> lines can appear in the same commit. Many code hosting platforms recognize this token and display co-authors in the commit view or contribution profiles. Exact display depends on the platform and project settings.

### Which Email Should Be Used?

If a platform needs to link a co-author to an account, the email in the trailer must be an address that the platform associates with that account. Some services support noreply addresses; use the exact address registered by the collaborator or permitted for public use by your organization.

Do not guess a co-author's email. Ask them directly or use the address they provided. Emails in trailers become part of commit history and can become public when the repository is shared.

### Co-authored-by Does Not Change the Author Field

This trailer helps platforms or tools recognize additional collaborators, yet it does not turn the commit object into one with multiple author headers. Git still stores one primary author. To inspect the underlying author/committer:

~~~bash
git show -s --format=fuller HEAD
~~~

To read a commit's trailers:

~~~bash
git show -s --format='%(trailers)' HEAD
~~~

## 4. Referencing Tickets and Work Items

Custom trailers can link a commit to an issue, ticket, task, or change request. For example:

~~~text
Refs: PAY-482
Refs: https://tracker.example.com/browse/PAY-482
~~~

Teams may choose other tokens such as:

| Token | Common Meaning |
|---|---|
| <code>Refs</code> | Reference to a related ticket or issue |
| <code>Issue</code> | Issue ID addressed by the commit |
| <code>Task</code> | Task or work item in a project management system |
| <code>Reviewed-by</code> | Person who reviewed the change |
| <code>Tested-by</code> | Person or system that tested the change |
| <code>Related-to</code> | Related work item |

These tokens are team or platform conventions; not all of them have standardized meaning in core Git. Agree on spelling, ticket system format, and validation rules so everyone uses them consistently.

### Refs Does Not Automatically Close Issues

<code>Refs: PAY-482</code> only records a reference. It does not automatically close the ticket unless the issue tracker is configured to act on that token.

Some platforms support closing keywords in commit messages, such as <code>Fixes #123</code>, <code>Closes #123</code>, or <code>Resolves #123</code>. This is platform-defined syntax; do not assume custom trailers like <code>Issue: #123</code> trigger issue closure automatically. Check your platform's rules and place closing keywords in the supported format.

Example when a team wants both a trailer reference and a closing keyword:

~~~text
fix(api): reject expired refresh token

Return an authentication error when the refresh token is expired.
Fixes #123

Refs: AUTH-219
Reviewed-by: Linh Nguyen <linh@example.com>
~~~

In this example, <code>Refs</code> is metadata per team convention; <code>Fixes #123</code> is a body line matching the issue-closing syntax of a platform that supports it.

## 5. Signed-off-by and the Developer Certificate of Origin

A common trailer in open-source projects is:

~~~text
Signed-off-by: Full Name <email@example.com>
~~~

This trailer is typically used to indicate a contributor certifies compliance with contribution terms, such as the Developer Certificate of Origin (DCO). Project policy defines the exact meaning of sign-off and when it is required.

Git supports adding sign-off with:

~~~bash
git commit -s -m "Fix request validation"
~~~

Depending on identity configuration, Git appends a <code>Signed-off-by</code> trailer using the committer's name and email. Inspect the commit content before pushing to confirm the details are accurate.

### Sign-off Is Not a Cryptographic Signature

<code>Signed-off-by</code> is a plain-text attestation in the commit message. It does not generate a cryptographic signature and does not prove the named person owns a private key.

To sign a commit with a cryptographic key, Git provides the <code>-S</code> option:

~~~bash
git commit -S -m "Fix request validation"
~~~

You can verify the signature:

~~~bash
git verify-commit HEAD
~~~

The two options serve different purposes:

| Option | Result |
|---|---|
| <code>-s</code> | Appends a <code>Signed-off-by</code> trailer |
| <code>-S</code> | Signs the commit with the configured signing key |

A project may require sign-off, cryptographic signatures, or both. Follow your project's contribution policy.

## 6. Adding Trailers When Creating a Commit

There are several ways to write a commit message with trailers. Choose the method that best fits your automation level and review needs.

### Write Directly with Multiple -m Arguments

Each use of <code>-m</code> creates a paragraph in the commit message:

~~~bash
git commit \
  -m "feat(payment): add retry policy" \
  -m "Retry transient gateway failures with a bounded backoff." \
  -m "Co-authored-by: An Le <an@example.com>
Refs: PAY-482"
~~~

With this approach, each <code>-m</code> creates a paragraph. The two trailer lines are placed in the same final argument so they stay in one paragraph. When adding multiple trailers, do not split each trailer into its own <code>-m</code> argument, or they will become separate paragraphs; use a multi-line block as shown or use a message file with <code>git interpret-trailers</code>.

### Use a Commit Message File

Create <code>commit-message.txt</code>:

~~~text
feat(payment): add retry policy

Retry transient gateway failures with a bounded backoff.
Preserve the request identifier across retries.

Co-authored-by: An Le <an@example.com>
Refs: PAY-482
Reviewed-by: Binh Pham <binh@example.com>
~~~

Then:

~~~bash
git commit -F commit-message.txt
~~~

The <code>-F</code> option reads the entire file contents as the commit message. This is convenient for scripts generating messages or when reviewing a message before committing.

### Use git commit --trailer

Git versions that support the <code>--trailer</code> option on <code>git commit</code> can add trailers directly:

~~~bash
git commit \
  -m "feat(payment): add retry policy" \
  --trailer "Co-authored-by: An Le <an@example.com>" \
  --trailer "Refs: PAY-482"
~~~

If the command reports that the option is unsupported, check your Git version and use a message file combined with <code>git interpret-trailers</code> as shown next. Do not assume every machine on the team runs the same Git version.

## 7. Adding and Normalizing Trailers with git interpret-trailers

<code>git interpret-trailers</code> is a plumbing command for reading, adding, and processing trailers in commit messages. It is useful in scripts because it applies consistent rules without writing custom string parsers.

### Add Trailers to a Message File

Create the message file first:

~~~bash
cat > commit-message.txt <<'EOF'
feat(search): improve query normalization

Normalize whitespace before building the search request.
EOF
~~~

Add trailers:

~~~bash
git interpret-trailers \
  --trailer "Co-authored-by: An Le <an@example.com>" \
  --trailer "Refs: SEARCH-91" \
  --in-place commit-message.txt
~~~

Inspect the file:

~~~bash
cat commit-message.txt
~~~

Then create the commit:

~~~bash
git commit -F commit-message.txt
~~~

<code>--in-place</code> updates the message file directly. Without this option, the command normally writes the processed message to standard output for piping or saving elsewhere.

### Read Existing Trailers

To parse trailers from a file:

~~~bash
git interpret-trailers --parse < commit-message.txt
~~~

To view trailers of the current commit:

~~~bash
git show -s --format='%(trailers)' HEAD
~~~

To view the full body and trailers:

~~~bash
git show -s --format='%B' HEAD
~~~

<code>%(trailers)</code> is a placeholder in Git's pretty format. It helps scripts or reviewers extract trailers without manually parsing the entire commit message.

## 8. Configuring Trailer Rules for a Team

Git lets you configure how trailers are added via the <code>trailer.*</code> config namespace. For instance, if a team wants to standardize the <code>Refs</code> token and avoid adding duplicate references:

~~~bash
git config trailer.refs.key "Refs"
git config trailer.refs.ifexists addIfDifferent
git config trailer.refs.ifmissing add
git config trailer.refs.where end
~~~

Then trailers can be added with:

~~~bash
git interpret-trailers --trailer "refs: PAY-482" --in-place commit-message.txt
~~~

In this configuration:

- <code>key</code> defines the canonical trailer name emitted.
- <code>ifexists</code> specifies behavior when the token is already present.
- <code>ifmissing</code> specifies the action when no matching trailer exists yet.
- <code>where</code> specifies where the trailer is inserted.

Common values for <code>ifexists</code> include <code>add</code>, <code>addIfDifferent</code>, <code>addIfDifferentNeighbor</code>, <code>replace</code>, and <code>doNothing</code>. Placement can be configured with choices like <code>end</code>, <code>start</code>, <code>after</code>, or <code>before</code> depending on context and Git version. Consult <code>git help interpret-trailers</code> to verify the exact syntax supported by your installation.

### Avoid Creating Duplicate Trailers

If a script may run multiple times on the same message file, choose an appropriate duplicate-handling policy. For example:

- <code>add</code>: always append, even if the value already exists.
- <code>addIfDifferent</code>: append only if no trailer with the same token and value exists.
- <code>replace</code>: replace existing trailers according to configured rules.
- <code>doNothing</code>: take no action if the token already exists.

Avoid using <code>replace</code> broadly on multi-value tokens like <code>Co-authored-by</code>, because it can overwrite earlier co-author entries.

## 9. Multi-Value Trailers and Ordering

A commit can contain multiple trailers with the same token:

~~~text
Co-authored-by: An Le <an@example.com>
Co-authored-by: Binh Pham <binh@example.com>
Reviewed-by: Chi Nguyen <chi@example.com>
Reviewed-by: Dung Tran <dung@example.com>
Refs: PAY-482
Refs: PAY-496
~~~

Order can matter for workflows or UI rendering. Agree on an ordering convention within the team, for example:

1. Co-authors.
2. Reviewers or testers.
3. Work-item references.
4. Sign-off.

This is only an illustrative convention. If a project already has a commit message template or validation hook, follow the project's template.

### One Token with Multiple Values

For <code>Co-authored-by</code>, give each person their own trailer line rather than combining multiple emails into one value. Separate lines make it easier for tools to recognize each person and reduce formatting errors.

For tickets, a single trailer may contain one or multiple IDs depending on convention. If you want parsers to link each ticket independently, separate <code>Refs</code> lines are usually clearer.

## 10. How Does Git Recognize Trailers?

Git looks for trailers at the end of a commit message based on token and separator format. The trailer block is typically the final paragraph. Normal lines placed after the trailer block can stop parsers from recognizing the trailing section as intended.

Easy-to-recognize example:

~~~text
Add retry handling

Retry the request after transient gateway failures.

Refs: PAY-482
Reviewed-by: Linh Nguyen <linh@example.com>
~~~

Confusing example:

~~~text
Add retry handling

Refs: PAY-482

Additional note: this is still experimental.
~~~

In the second example, the final paragraph is not a trailer block. Place notes before the trailer block so both parsers and human readers recognize trailers clearly.

### Custom Separators and Tokens

By default, a colon is the standard separator:

~~~text
Refs: PAY-482
Reviewed-by: Linh Nguyen <linh@example.com>
~~~

Git can also be configured with other separators via <code>trailer.separators</code>. Teams should use one consistent format rather than mixing separator styles in the same repository.

Token names should not contain separator characters or be invented inconsistently. Pick short, stable, meaningful names and avoid creating variants like <code>Ref</code>, <code>Refs</code>, and <code>Reference</code> for the same purpose.

## 11. Checking Trailers Before Sharing Commits

Before pushing, review the commit message:

~~~bash
git show -s --format=fuller HEAD
git show -s --format='%(trailers)' HEAD
~~~

Check:

- Subject and body accurately describe the change.
- Co-author emails are accurate and approved by the collaborators.
- Referenced tickets or issues are correct.
- Trailers are not duplicated by scripts running multiple times.
- No tokens or secrets appear in trailer values.
- Sign-off is present if required by project policy.

If the commit has not been shared yet, you can edit the commit message with:

~~~bash
git commit --amend
~~~

If the commit has already been pushed and others depend on it, editing the message changes the commit hash. Coordinate with your team before force pushing; if the goal is merely adding missing information, consider a follow-up commit per project workflow.

## 12. Automating Trailer Checks in Hooks or CI

Teams can validate trailers to ensure commits follow conventions. For example, extracting trailers from the current commit:

~~~bash
git show -s --format='%(trailers)' HEAD
~~~

Or checking commits in a range:

~~~bash
git log --format='%h %s%n%(trailers)' origin/main..HEAD
~~~

Scripts can verify that every commit on a release branch includes <code>Refs</code>, or includes <code>Signed-off-by</code> when policy requires it. When validating co-authors, scripts can enforce specific name and email formatting.

Do not assume every commit must carry the exact same trailers. Automated merge commits, documentation fixes, revert commits, or bot-generated commits may follow different rules. Define commit types and check scopes clearly in CI.

### Checking a Trailer Does Not Verify Truth

A script can confirm a <code>Reviewed-by</code> line is present, yet it cannot rely on that line alone to prove a reviewer genuinely approved the change. If approval proof is needed, fetch status from your Pull Request/Merge Request system or change management platform.

Similarly, <code>Co-authored-by</code> records collaborators as declared in the commit message. Team processes still need to ensure the commit author has the co-authors' consent.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Placing trailers in the middle of the body | Tools may fail to recognize them as trailing trailers | Move the trailer block to the end of the message |
| Misspelling a token | Platform ignores it or CI misses it | Use the exact agreed-upon token name |
| Using the wrong email for a co-author | Platform cannot link the account | Confirm the email with the collaborator |
| Combining multiple co-authors on one line | Parsers or UI may fail to split them properly | Use one <code>Co-authored-by</code> line per person |
| Assuming <code>Refs</code> auto-closes issues | Ticket does not update automatically | Use platform-supported closing keywords if needed |
| Confusing <code>Signed-off-by</code> with a cryptographic signature | Misunderstands verification level | Distinguish <code>git commit -s</code> from <code>git commit -S</code> |
| Using <code>replace</code> on multi-value trailers | Can drop earlier co-authors | Choose <code>addIfDifferent</code> or an appropriate policy |
| Script appends duplicate trailers on each run | Commit message contains duplicate metadata | Configure <code>ifexists</code> and check before adding |
| Editing trailers on a shared commit without notifying the team | Commit hash changes, collaborative branches diverge | Coordinate history rewrite or create a follow-up commit |

## 14. Sample Workflow for Pair Programming

Suppose two people pair on implementing a pagination feature:

1. Both agree on who creates the commit and confirm the email to use in the trailer.
2. The commit creator stages the reviewed changes.
3. The commit message includes a subject and body describing the new behavior.
4. Add a <code>Co-authored-by</code> line for the collaborator.
5. Add <code>Refs</code> for the related ticket.
6. If required by the project, add <code>Signed-off-by</code> for the commit creator per DCO policy.
7. Verify the message with <code>git show -s --format='%(trailers)' HEAD</code>.
8. Push the branch and open a Pull Request/Merge Request per team workflow.

Example message:

~~~text
feat(list): add cursor pagination

Return a stable next cursor and avoid duplicate items between pages.

Co-authored-by: Lan Pham <lan@example.com>
Refs: LIST-308
Reviewed-by: Tuan Nguyen <tuan@example.com>
~~~

## 15. Self-Check Exercises

Practice in a test repository:

1. Create a commit with a subject, body, and two trailers: <code>Refs</code> and <code>Reviewed-by</code>.
2. Add two <code>Co-authored-by</code> lines and inspect them using <code>git show</code>.
3. Use <code>git interpret-trailers --parse</code> to extract trailers from a message file.
4. Use <code>git interpret-trailers --trailer</code> to append trailers to a message file.
5. Configure <code>trailer.refs.key</code> and an <code>ifexists</code> policy, then try adding the same reference twice.
6. Create a commit with <code>git commit -s</code> and identify the <code>Signed-off-by</code> line.
7. Create a cryptographically signed commit with <code>git commit -S</code> in an environment with a signing key and verify with <code>git verify-commit</code>.
8. Compare author/committer in the commit object against the <code>Co-authored-by</code> lines.
9. Try placing a paragraph after the trailer block and observe how the parser interprets it.
10. Write a short trailer convention for a team: which tokens are required, which are optional, and how tickets are linked.

Trailers let commit messages carry structured metadata while keeping descriptions readable. Use consistent tokens, place trailers at the end of the message, verify co-author and reference details accurately, and distinguish declarative metadata from actual approval systems or cryptographic signatures.
