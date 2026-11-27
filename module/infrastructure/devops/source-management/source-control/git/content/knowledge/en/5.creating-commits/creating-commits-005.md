# Writing Commit Messages with a Subject, Context, and Rationale

A commit stores a snapshot of the index along with author, committer, timestamps, and a message describing the change. The code shows how the project changed; the commit message helps readers understand what that change was meant to solve and why it was needed. A clear message aids history reviews, regression investigations, selecting commits to revert, or understanding technical decisions months later.

A good message typically has three parts: a short subject stating the main action, a body providing context and rationale, and structured trailers when attaching information such as issues, reviewers, or sign-offs. Not every commit needs all three parts, but writers need to know when a body or trailer adds real value.

After this lesson, you will be able to:

- Write a concise subject that accurately describes the change.
- Write a body explaining context, rationale, and important consequences.
- Distinguish message content from the commit diff.
- Apply consistent phrasing, line length, and verb tense conventions.
- Add trailers such as Refs, Fixes, Reviewed-by, or Signed-off-by appropriately.
- Enter messages via an editor, -m, or a template.
- Inspect messages after committing and improve weak messages.

## 1. How Do Commit Messages Help Readers?

Someone reading history may not know the context in which a change was created. They typically need quick answers to three questions:

1. **What is the main change?** The subject should state the most important action or outcome.
2. **Why is the change needed?** The body explains the problem, requirement, or decision leading to the change.
3. **What work is this change tied to?** Trailers can link issues, record sign-offs, or supply metadata required by team workflow.

Do not use the message to copy out lines of code. The diff already holds those details. The message adds information the diff cannot express on its own, such as the reason for a workaround, compatibility constraints, trade-offs, or operational conditions.

For example:

~~~text
Fix search results when the query contains accents

Normalize the query before matching so that user input and
stored labels use the same comparison form. Keep the original
query for display to avoid changing what the user entered.

Fixes: #184
~~~

The subject states the main outcome. The body explains why normalization is needed and states the decision to preserve the display string. The trailer links the commit to the issue.

## 2. Structure of Subject, Body, and Trailers

A multi-line commit message usually takes this form:

~~~text
Short subject that summarizes the change

Context: what problem or requirement led to this change.
Reason: why this approach is appropriate and what it changes.
Important constraints, side effects, or trade-offs.

Trailer-Name: value
Another-Trailer: value
~~~

| Part | Purpose | Question to Answer |
| --- | --- | --- |
| Subject | Summarize the main change in one line. | What does this commit do? |
| Body | Provide context, rationale, approach, and notable consequences. | Why was this done and what should readers know? |
| Trailer | Record structured metadata at the end of the message. | Which issue, sign-off, or person does the commit relate to? |

Leave one blank line between the subject and the body. If both a body and trailers are present, leave a blank line between the explanation and the trailers for readability.

A small, self-evident commit may need only a subject. A change that affects behavior, fixes a subtle bug, or involves a design decision should usually have a body. Add trailers only when the project has a convention or when that information genuinely needs to be parsed by tools and humans.

## 3. Write a Short, Informative Subject

The subject is what appears in git log --oneline, pull request lists, and commit notifications. Readers should grasp the main point without opening the diff immediately.

A good subject typically:

- Starts with an action verb: Add, Fix, Remove, Prevent, Document, Refactor.
- Names the affected component or behavior.
- Avoids generic phrases like “Update code” or “Fix bug”.
- Omits a trailing period if the team uses imperative sentence-style subjects.
- Focuses on one primary change.

Examples:

| Weak Subject | Clearer Subject |
| --- | --- |
| Update search | Normalize accented search queries |
| Fix bug | Prevent duplicate invoices after retry |
| Changes | Reject expired access tokens |
| Refactor code | Extract date parsing from report service |
| Update files | Document local hook installation |

### Use Imperative or Descriptive Mood?

Many projects choose the imperative mood in subjects—for example, Add retry limit instead of Added retry limit or Adds retry limit. Think of the subject as completing the sentence “If applied, this commit will …”.

This is a convention for consistent history, not a mandatory technical requirement of Git. If the project already has a different style guide, follow the existing convention.

### Subject Length

A common convention is keeping the subject around 50 characters and avoiding exceeding 72 characters. This is a guideline so subjects render cleanly in terminals and review tools, not a hard Git limit. If more length is needed to avoid ambiguity, prioritize clarity and trim filler words.

The subject should not hold the entire explanation. If more rationale is needed, write a body rather than turning the subject into a paragraph.

## 4. The Body Explains Context and Rationale

The body does not need to repeat the subject in different words. Use this section to capture information readers cannot easily deduce from the diff.

Helpful questions when writing a body:

- What problem was occurring?
- What difficulty or risk did the old behavior cause?
- Why was this solution chosen?
- Were any alternatives considered and rejected, and why?
- Are there impacts on APIs, data, performance, or operations?
- Are there limitations or deployment steps others need to know about?

Example body for a bug fix:

~~~text
Prevent duplicate invoices after retry

The payment provider can retry a callback when the first response
times out. The old handler created a new invoice for each callback,
even when the provider sent the same event identifier.

Store the provider event ID with a uniqueness constraint and return
the existing invoice for repeated events. This makes callback
processing idempotent without changing the customer-facing flow.
~~~

The body describes the timeout context, the cause of duplicate records, the fix, and why a uniqueness constraint was chosen. Readers understand the decision without having to piece it together across multiple files.

### Note What Does Not Change When It Matters

A good message can explicitly clarify a boundary that might otherwise be misunderstood. For example, “Keep the original query for display” explains that normalization applies only to matching and does not alter what users see. Do not list everything that stayed unchanged; mention only what matters for review or operations.

### Do Not Turn the Body Into a Copy of the Diff

Avoid statements like:

~~~text
Changed line 10.
Added a new if statement.
Updated method search().
~~~

These describe editing mechanics without stating why. Explain the behavior or problem the change addresses.

## 5. Line Length and Formatting

A common formatting convention:

- Subject around 50 characters.
- Body wrapped around 72 characters per line.
- A blank line between subject and body.
- A blank line before trailers.
- Short paragraphs, each focused on one idea.

This is a readability convention, not a commit format limitation. Git can store longer messages or a single line. What matters is that the message is not truncated, hard to read, or missing context.

Do not insert manual line breaks after every few words in the subject. For a long body, wrap at sentence/line boundaries so terminals and history viewers display it cleanly.

## 6. Writing Messages for Different Types of Changes

### Adding a Feature

The subject should clearly state the new feature or capability:

~~~text
Add export to CSV for monthly reports
~~~

The body can explain who needs the feature, what data is exported, formatting constraints, or why CSV was chosen.

### Fixing a Bug

The subject states the buggy behavior being fixed:

~~~text
Prevent empty passwords from passing validation
~~~

The body explains the conditions triggering the bug, its impact, and the new handling. If the bug only occurs in a specific environment, record that environment when it helps readers understand the root cause.

### Refactoring

The subject describes the structure or responsibility being changed:

~~~text
Extract token parsing into a dedicated service
~~~

The body should explain why extraction was needed, the new responsibility boundary, and confirm whether external behavior is preserved if that is important.

### Documentation or Configuration Changes

~~~text
Document the required local Git hooks
~~~

The body can note the target audience, new setup steps, or how the configuration affects the development environment.

### Breaking Changes

If a change requires clients or dependent systems to adjust, state it clearly in the body and use project-standard trailers if applicable:

~~~text
Remove the legacy token response field

All supported clients now read the token from the response header.
Keeping the old field would expose two competing sources of truth.
Update integrations before deploying this version.

BREAKING CHANGE: The token field is no longer included in the JSON response.
~~~

Do not label internal code refactors as breaking changes. Use this only for actual compatibility changes that users or dependent systems must know about.

## 7. What Are Trailers?

Trailers are structured metadata lines at the end of a commit message. They typically take the form Token: value and are placed after the body.

Common trailers:

| Trailer | Typical Meaning |
| --- | --- |
| Refs: #123 | Links the commit to a related issue or task. |
| Fixes: #123 | Marks the commit as fixing an issue per platform or project convention. |
| Reviewed-by: Name <email> | Records reviewers if required by workflow. |
| Signed-off-by: Name <email> | Records sign-off under the Developer Certificate of Origin or project policy. |
| Co-authored-by: Name <email> | Credits co-authors using a convention supported by tools. |
| BREAKING CHANGE: description | Describes an incompatible change in conventions such as Conventional Commits. |

Not every system automatically understands every trailer. Some platforms recognize Fixes, Closes, or Signed-off-by; other projects use custom tokens. Follow what is configured.

Trailers differ from regular prose sentences because they are structured for tools to extract. Do not invent names or email addresses; record only verified information appropriate for your workflow.

### Inspecting Trailers with Git

Git provides interpret-trailers to parse, add, or normalize trailers:

~~~bash
git interpret-trailers --parse
~~~

The command reads a message from standard input. For example:

~~~bash
git log -1 --format=%B | git interpret-trailers --parse
~~~

To add a trailer to a message file:

~~~bash
git interpret-trailers --trailer "Refs: #184" --in-place commit-message.txt
~~~

Inspect the resulting file before using it as a commit message. Trailer interpretation and duplicate rules are configurable, so do not assume every token is handled identically across projects.

## 8. Conventional Commits Is an Optional Convention

Some teams use Conventional Commits to standardize subjects:

~~~text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
~~~

For example:

~~~text
feat(search): normalize accented queries

Normalize user input before matching so that accented and
unaccented labels can be compared consistently.

Fixes: #184
~~~

Common types:

| Type | Typical Usage |
| --- | --- |
| feat | Add a new feature. |
| fix | Fix a bug. |
| docs | Documentation changes. |
| refactor | Code restructuring without directly adding a feature or fixing a bug. |
| test | Add or update tests. |
| build | Changes to the build system or dependencies. |
| ci | Changes to CI configuration. |
| chore | Other maintenance work per team convention. |

A scope in parentheses narrows the changed area, such as feat(auth): add role-based access checks. An exclamation mark ! after type/scope can indicate a breaking change:

~~~text
feat(api)!: remove the legacy token field
~~~

Conventional Commits is not a mandatory Git format. If a team adopts it, agree on types, scopes, breaking change rules, and issue linking. Avoid mixing multiple conventions in the same history without good reason.

## 9. Writing Commit Messages with an Editor

Normally, run:

~~~bash
git commit
~~~

Git opens the configured editor for writing multi-line messages. Basic pattern:

~~~text
Add retry limit to webhook delivery

The provider retries callbacks when the response is delayed.
Limit repeated attempts and record the final delivery status so
operators can identify callbacks that need manual review.

Refs: #246
~~~

Save and close the editor to create the commit. If the message only has a subject, omit the body and trailers.

Git selects the editor based on core.editor or relevant environment variables. Check configuration:

~~~bash
git config --show-origin --get core.editor
~~~

If the right editor does not open, configure one suited to your environment:

~~~bash
git config --global core.editor "code --wait"
~~~

The example above works when Visual Studio Code is installed and the code command is in PATH. Substitute the editor your team uses if different.

## 10. Using -m for Short Messages

For simple commits, you can pass the subject directly:

~~~bash
git commit -m "Fix null handling in search results"
~~~

To pass a body, use multiple -m options; each value forms a paragraph separated by a blank line:

~~~bash
git commit -m "Fix null handling in search results" -m "The API can return a missing label for archived records. Treat the label as optional so the result list remains available."
~~~

For a long body or trailers, an editor is usually easier to write and review. When using a shell, pay attention to quoting and special characters according to your current shell's syntax.

Do not cram an overly long body into a single -m string if it becomes hard to read or review. The goal is a readable message in history, not merely getting a command to execute.

## 11. Using Templates for Consistent Writing

If a team wants everyone to remember context and rationale, create a template file:

~~~text
<Short subject: action and affected behavior>

Context:
Why is this change needed?

Approach:
What was changed and why was this approach chosen?

Impact:
Any compatibility, data, performance, or operational notes?

Refs:
~~~

Configure the template for a repository:

~~~bash
git config --local commit.template .gitmessage
~~~

Or configure globally to reuse across repositories:

~~~bash
git config --global commit.template ~/.gitmessage
~~~

A template file is a prompt opened in the editor; the writer still must replace sample prompts with real details. Avoid committing templates containing unreplaced placeholders. If a team uses a repository-level template, store the template file in the repository and guide members to configure it locally.

## 12. Viewing the Diff While Writing the Message

To have Git display the staged diff in the editor while creating a commit:

~~~bash
git commit -v
~~~

Verbose mode lets you cross-check the subject and body against actual changes. The diff is placed in an informational section during editing and does not become part of the final commit message after Git runs cleanup.

Before committing, still verify the staging area:

~~~bash
git status
git diff --cached
~~~

A good message cannot compensate for staging the wrong files. Confirm the intended snapshot matches scope before describing it.

## 13. Inspecting the Message After Committing

View the latest commit:

~~~bash
git log -1
~~~

View just the subject:

~~~bash
git log -1 --format=%s
~~~

View the full message body:

~~~bash
git log -1 --format=%B
~~~

View author and committer:

~~~bash
git log -1 --format=fuller
~~~

View the message along with diff stats:

~~~bash
git show --format=fuller --stat HEAD
~~~

Re-read the message from the perspective of someone who was not involved in the change. If the subject is vague or the body fails to explain why, improve it before sharing the commit with the team.

## 14. Amending the Most Recent Commit Message

If the latest commit has not been shared and you only need to fix its message, run:

~~~bash
git commit --amend
~~~

The editor opens the old message for revision. Even if you change only the message without altering staged content, the new commit gets a different object ID because the message is part of the commit object.

You can replace the subject directly:

~~~bash
git commit --amend -m "Clarify search fallback behavior"
~~~

--amend replaces the latest commit with a new commit. If the old commit was already pushed or others built on top of it, amending alters history and may require coordination before updating the remote. For shared commits, follow team policy instead of unilaterally rewriting history.

If amending content as well, inspect the staging area first because Git uses the current index to build the new snapshot:

~~~bash
git status
git diff --cached
git commit --amend
~~~

## 15. Common Mistakes

### Subject Just Says “Update code”

Readers cannot tell which area or behavior changed. Add a specific verb and target, such as Reject expired refresh tokens.

### Body Repeats the Subject

The body should add context, rationale, approach, or consequences. If there is nothing useful to add, a good subject alone may be enough.

### Describing Files Instead of Rationale

“Changed Search.java” does not explain the goal. State what behavior was fixed and what problem was solved.

### Cramming Everything Into the Subject

The subject should summarize. Move causes, trade-offs, and deployment notes into the body.

### Placing Trailers in the Middle of the Body

Place trailers at the end of the message and separate them from the body with a blank line so humans and tools can parse them easily.

### Using Fixes for Issues That Were Not Actually Fixed

Only use issue-closing trailers when the commit truly resolves the issue and the platform understands that syntax. If it is only related, use Refs or the project's configured token.

### Thinking Git Enforces 50-Character Subjects or 72-Character Bodies

These are style guidelines, not hard Git limits. A project may use hooks or CI to enforce its own rules.

### Running --amend After a Commit Has Been Shared

Amend creates a new commit and changes history. Check sharing status and team policy before rewriting commits others have already used.

## 16. Practice Workflow: Writing a Complete Commit Message

Suppose you just fixed a bug where webhooks were sent repeatedly:

~~~bash
# 1. Confirm status
git status --short

# 2. Review exact staged content
git diff --cached

# 3. Open the editor to write subject, body, and trailers
git commit

# 4. Re-read message and metadata
git log -1 --format=fuller

# 5. Inspect the commit snapshot
git show --stat --oneline HEAD
~~~

The message might read:

~~~text
Prevent duplicate invoices after webhook retries

The payment provider can resend an event when the first callback
times out. The previous handler created a second invoice because
it did not check whether the event had already been processed.

Store the provider event ID with a uniqueness constraint and
return the existing invoice for repeated callbacks. This keeps
processing idempotent without changing the customer workflow.

Fixes: #246
~~~

Before finishing, ask yourself:

- Does the subject state the primary action and target?
- Does the body explain context and rationale instead of copying the diff?
- Are trade-offs or impacts that reviewers should know mentioned?
- Do trailers follow the project's syntax and intent?
- Does the message accurately describe what was staged?

## 17. Takeaways

- The subject summarizes the main change; the body explains context, rationale, and notable consequences.
- Leave one blank line between subject and body; place trailers at the end separated by a blank line.
- Prefer specific subjects, usually starting with a verb and naming the changed behavior or target.
- The ~50-character subject and ~72-character body convention is a readability guideline, not a Git limitation.
- Do not copy the diff in the body; explain what the diff cannot say on its own.
- Trailers like Refs, Fixes, Reviewed-by, Signed-off-by, and Co-authored-by should follow project conventions.
- Conventional Commits is an optional style, not a mandatory Git requirement.
- Use an editor for multi-line messages; -m suits short messages.
- Check the staging area before committing and re-read the message with git log afterward.
- git commit --amend creates a new commit and can rewrite shared history.

A good commit message helps readers understand the change, context, and rationale without reconstructing the whole story from the diff. When the subject is clear, the body gives enough context, and trailers follow convention, Git history becomes useful technical documentation for review, maintenance, and incident investigation.
