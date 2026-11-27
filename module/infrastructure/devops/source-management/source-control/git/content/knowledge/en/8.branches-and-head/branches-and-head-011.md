# Branch Naming Rules, Reference Names, and Validation with git check-ref-format

Branches and tags in Git have names so users can easily reference commits. These names are not arbitrary strings: Git enforces rules for a *refname* to avoid ambiguity when parsing revisions, reflogs, refspecs, paths, and storage structures. Therefore, a name like `feature/add-login` is normally valid, whereas `feature//add-login`, `feature name`, or `feature/topic.lock` is invalid.

The `git check-ref-format` command checks whether a reference name complies with Git's syntax rules. When checking a short branch name, use `git check-ref-format --branch`. This command only validates syntax; it does not check whether the name already exists, complies with team conventions, is permitted by the hosting platform, or whether the user has permission to create the branch.

## 1. How Do Branches, Refs, and HEAD Relate?

In Git, a branch is a type of ref pointing to a commit. A branch is not a directory copy or an independent workspace; it is a movable name that advances when you create new commits or update the branch.

Common ref namespaces:

| Reference type | Full name example | Meaning |
|---|---|---|
| Local branch | `refs/heads/main` | The `main` branch in the current repository |
| Grouped local branch | `refs/heads/feature/add-login` | The `feature/add-login` branch |
| Remote-tracking branch | `refs/remotes/origin/main` | State of the `main` branch recorded by the most recent fetch from remote `origin` |
| Tag | `refs/tags/v2.1.0` | The `v2.1.0` tag |
| Notes | `refs/notes/commits` | Git notes namespace |

The branch name users typically type is the portion after `refs/heads/`. For example, `feature/add-login` corresponds to the full ref `refs/heads/feature/add-login`.

`HEAD` is a special reference indicating the current working position. When on a normal branch, `HEAD` is usually a symbolic ref pointing to `refs/heads/<branch>`. In detached HEAD state, `HEAD` points directly to a commit instead of a branch. `HEAD` is not a branch name that you create in the ordinary way.

Check the current branch:

```bash
git branch --show-current
git symbolic-ref --short HEAD
git rev-parse --short HEAD
```

In detached HEAD, `git branch --show-current` may print no branch name and `git symbolic-ref` will not find a symbolic ref; `git rev-parse HEAD` still reports the current commit.

## 2. Why Does Git Restrict Ref Names?

Git uses refnames in many contexts:

- Identifying branches, tags, and other refs.
- Parsing revision expressions such as `HEAD~2`, `main^`, or `v1.0.0^{commit}`.
- Identifying reflog entries with `@{...}` syntax.
- Processing refspecs during fetch/push.
- Storing refs in the repository's file/directory structure or corresponding ref backend.

Certain characters have special meanings in the shell or Git syntax. If allowed arbitrarily, a ref name could be misinterpreted as a revision operator, refspec delimiter, or reflog syntax. Ref naming rules allow tools to process names consistently.

## 3. Main Syntax Rules for a Refname

A standard refname must satisfy the following conditions:

1. Must not contain ASCII control characters, spaces, or forbidden special characters.
2. Must not contain two consecutive dots `..`.
3. Must not end with a dot `.`.
4. Must not begin or end with a slash `/`.
5. Must not contain two consecutive slashes `//`.
6. Must not contain the sequence `@{`.
7. Must not be just the single character `@`.
8. Must not have a path component starting with a dot `.`.
9. Must not have a path component ending with `.lock`.
10. Must not contain a backslash `\`.

Directly forbidden characters include:

| Character/Group | Reason to avoid |
|---|---|
| ASCII control characters (bytes less than `0x20`) and `DEL` (`0x7f`) | Unsuitable for representing ref names and problematic for tooling |
| Space | Causes ambiguity when passing arguments in shells and scripts |
| `~` | Ancestor selection operator in revision syntax |
| `^` | Parent operator in revision syntax |
| `:` | Meaningful in refspec syntax and certain Git expressions |
| `?`, `*`, `[` | Can conflict with patterns/wildcards and pathspec syntax |
| `\` | Causes path interpretation and compatibility issues |

Invalid examples:

```text
feature//login       # Two consecutive /
/feature/login       # Starts with /
feature/login/       # Ends with /
feature..login       # Contains ..
feature/login.       # Ends with .
feature/login.lock   # Component ends with .lock
feature/.private     # Component starts with .
feature/@{backup     # Contains @{
@                    # Single @ character only
feature/login test   # Contains a space
feature/login?       # Contains ?
```

In addition to the rules above, Git also requires a full refname to usually have at least one `/`. Thus `refs/heads/main` is a valid refname, whereas `main` is a one-level name and is only accepted in special checking modes such as `--branch` or `--allow-onelevel`.

## 4. Path Components and the `.lock` Rule

Refnames are organized hierarchically using `/`. Each segment between two `/` characters is a path component.

Example:

```text
refs/heads/feature/add-login
          |       |   |
          |       |   +-- component: add-login
          |       +------ component: feature
          +-------------- namespace: heads
```

No component may begin with a dot. Hence `refs/heads/.hidden` and `refs/heads/feature/.private` are invalid.

No component may end with `.lock`. For example, `refs/heads/feature.lock` and `refs/heads/feature/login.lock` are invalid. This rule prevents conflicts with lock files that Git uses when updating refs.

Git also cannot simultaneously store one ref as a file and another ref needing that exact path as a directory in a file-based ref backend. For example, do not create both a `feature` branch and a `feature/login` branch: the two names have a prefix conflict and can collide in the storage structure. Choose a consistent hierarchical convention, such as always placing feature branches under `feature/<name>` rather than also using `feature` as a standalone branch.

## 5. Checking a Full Ref Name with git check-ref-format

Basic syntax:

```bash
git check-ref-format <refname>
```

Example checking a full branch ref:

```bash
git check-ref-format refs/heads/feature/add-login
```

Checking a tag ref:

```bash
git check-ref-format refs/tags/v2.1.0
```

Checking a remote-tracking ref:

```bash
git check-ref-format refs/remotes/origin/feature/add-login
```

If the refname is valid, the command exits with exit code `0` and usually prints nothing. If invalid, the command returns a non-zero exit code and may display an error message.

In a shell, check the exit code:

```bash
if git check-ref-format "refs/heads/feature/add-login"; then
    echo "Valid ref name"
else
    echo "Invalid ref name"
fi
```

In PowerShell:

```powershell
git check-ref-format "refs/heads/feature/add-login"
if ($LASTEXITCODE -eq 0) {
    "Valid ref name"
} else {
    "Invalid ref name"
}
```

The check command does not create a branch, does not create a tag, and does not modify the repository.

## 6. Checking a Branch Name with --branch

The branch name users enter is typically the short name, such as `feature/add-login`, not the full ref `refs/heads/feature/add-login`. Use `--branch` to check this kind of name properly:

```bash
git check-ref-format --branch feature/add-login
```

Invalid examples:

```bash
git check-ref-format --branch "feature//add-login"
git check-ref-format --branch "feature/login.lock"
git check-ref-format --branch "feature/login test"
```

Distinguishing the two checks:

| Command | Target being checked |
|---|---|
| `git check-ref-format refs/heads/feature/add-login` | Full ref name in the `refs/heads/` namespace |
| `git check-ref-format --branch feature/add-login` | Short branch name |

`--branch` also understands previous-branch syntax such as `@{-1}` and expands it to the previously checked-out branch when possible. If writing a script to validate literal strings entered by a user, be mindful of this special behavior; do not assume every passed string is always checked verbatim.

## 7. Normalizing Ref Names with --normalize

The `--normalize` option normalizes a refname by stripping leading `/` characters and collapsing multiple consecutive `/` characters into a single `/`. If the normalized result is valid, Git prints the normalized name.

Example:

```bash
git check-ref-format --normalize "refs//heads///feature/login"
```

Output:

```text
refs/heads/feature/login
```

This option is useful when you want to check or normalize a full ref in internal tooling. However, do not silently alter a user-entered branch name without notifying them. If a user types `feature//login`, automatically changing it to `feature/login` can mask mistakes or cause the created name to differ from the original intent.

A safe workflow is:

1. Receive the branch name.
2. Validate it directly with `git check-ref-format --branch`.
3. If invalid, return a clear message and ask for re-entry.
4. Normalize only when application policy permits and the user understands the result.

`--normalize` applies to full refnames and cannot be combined with `--branch`.

## 8. The --allow-onelevel and --refspec-pattern Options

### --allow-onelevel

By default, a full refname needs at least one `/`. `--allow-onelevel` relaxes this condition to accept a single-level name:

```bash
git check-ref-format --allow-onelevel release
```

This option is useful when checking refnames in special contexts. For regular branch names, use `--branch`; there is no need to use `--allow-onelevel` to check short names.

### --refspec-pattern

A refspec can use the wildcard `*` to represent part of a ref name. By default, `*` is forbidden in regular refnames. `--refspec-pattern` allows a single `*` in a pattern position:

```bash
git check-ref-format --refspec-pattern "refs/heads/*"
```

This option is intended for validating refspec patterns, not for creating branches with `*` in their names. A pattern may contain at most one `*` under this rule.

## 9. Establishing Team Branch Naming Conventions

`git check-ref-format` only validates Git syntax. Teams still need naming conventions to make searching, filtering branches, and automation easier.

Some common patterns:

| Prefix | Purpose | Example |
|---|---|---|
| `feature/` | Feature development | `feature/checkout-flow` |
| `fix/` | Routine bug fixes | `fix/payment-timeout` |
| `hotfix/` | Urgent bug fixes | `hotfix/critical-auth` |
| `release/` | Release version preparation | `release/2.4.0` |
| `chore/` | Maintenance work | `chore/update-dependencies` |
| `docs/` | Documentation | `docs/git-branch-guide` |

Some recommendations:

- Use lowercase to reduce differences between case-sensitive and case-insensitive filesystems.
- Use hyphens `-` to separate words within each component.
- Avoid spaces, accented characters, or special characters if branches pass through multiple systems and scripts.
- Use short, consistent prefixes such as `feature/`, `fix/`, `release/`.
- If your team uses ticket IDs, place them at the start or end following a single pattern, such as `feature/PROJ-123-checkout`.
- Avoid embedding usernames, customer data, or sensitive information in branch names.
- Do not create branches differing only by uppercase/lowercase if teammates use Windows or case-insensitive filesystems.

These are team conventions, not mandatory Git syntax requirements. A name like `task/123_add-user` may be valid to Git yet still violate an organization's naming policy.

## 10. A Valid Name Does Not Mean the Name Does Not Already Exist

`git check-ref-format` does not check whether a ref already exists. For example, `feature/add-login` may be syntactically valid while a branch of the same name has already been created locally or on the remote.

Check local branch:

```bash
git show-ref --verify --quiet refs/heads/feature/add-login
```

Check remote-tracking branch:

```bash
git show-ref --verify --quiet refs/remotes/origin/feature/add-login
```

Check refs currently advertised by the remote directly:

```bash
git ls-remote --heads origin feature/add-login
```

The commands above check different scopes. A remote may have a branch that local has not fetched yet, so local `git branch --list` or `git show-ref` is not proof that the branch does not exist on the server.

Even when a name does not yet exist, branch creation can still fail due to permissions, branch protection, hooks, or hosting policies. Distinguish syntax, existence status, and operational permissions.

## 11. Validating Before Creating a Branch in Scripts

A script can validate the name before calling `git switch -c`. Bash example:

```bash
branch_name="feature/PROJ-123-checkout"

if ! git check-ref-format --branch "$branch_name"; then
    echo "Invalid branch name: $branch_name" >&2
    exit 1
fi

if git show-ref --verify --quiet "refs/heads/$branch_name"; then
    echo "Local branch already exists: $branch_name" >&2
    exit 1
fi

git switch -c "$branch_name"
```

The script separates two conditions: valid syntax and the local branch not already existing. The `git switch -c` command remains the actual branch creation step; if the remote has a branch of the same name, the script needs to fetch/check the remote separately per workflow.

PowerShell example:

```powershell
$branchName = "feature/PROJ-123-checkout"

git check-ref-format --branch $branchName
if ($LASTEXITCODE -ne 0) {
    throw "Invalid branch name: $branchName"
}

git show-ref --verify --quiet "refs/heads/$branchName"
if ($LASTEXITCODE -eq 0) {
    throw "Local branch already exists: $branchName"
}

git switch -c $branchName
if ($LASTEXITCODE -ne 0) {
    throw "Cannot create branch: $branchName"
}
```

In production scripts, check for empty input, handle Git errors, and enforce team naming policy. Do not interpolate user-provided strings into unquoted shell commands.

## 12. Compatibility Notes Across Operating Systems and Hosting Platforms

Git permits some unusual names that other tools may not handle well. In particular:

- **Case differences:** `Feature/Login` and `feature/login` may be distinct on some filesystems yet collide on case-insensitive filesystems.
- **Names with Unicode characters:** may be accepted by Git, but Unicode normalization, encoding, or display can differ across tools and operating systems.
- **Names with spaces or shell special characters:** many such names are already forbidden by Git; characters that remain allowed still require proper quoting in scripts.
- **Prefix collisions:** `feature` and `feature/login` can collide in ref storage structure.
- **Hosting rules:** platforms may impose additional limits or custom policies beyond Git's rules.

For a repository to operate reliably across environments, use simple ASCII characters, lowercase letters, digits, hyphens, and `/` for hierarchy. Do not rely on uppercase/lowercase differences to distinguish two separate branches.

## 13. Examples of Checking Several Names

The following commands illustrate validation:

```bash
# Valid: hierarchical branch name.
git check-ref-format --branch "feature/add-login"

# Valid: release branch name.
git check-ref-format --branch "release/2.4.0"

# Invalid: two consecutive slashes.
git check-ref-format --branch "feature//add-login"

# Invalid: component starting with a dot.
git check-ref-format --branch "feature/.private"

# Invalid: component ending with .lock.
git check-ref-format --branch "feature/add-login.lock"

# Check a full ref.
git check-ref-format "refs/heads/feature/add-login"
```

In Bash, you can check multiple names and print the results:

```bash
for name in "feature/add-login" "feature//bad" "release/2.4.0"; do
    if git check-ref-format --branch "$name" >/dev/null 2>&1; then
        printf 'OK      %s\n' "$name"
    else
        printf 'INVALID %s\n' "$name"
    fi
done
```

Integrating this check into branch creation scripts or internal tooling catches errors early, before creating refs or calling hosting APIs.

## 14. Common Misconceptions

| Misconception | Correct understanding |
|---|---|
| A branch name is an arbitrary string | A branch is a refname and must follow Git syntax rules |
| `main` and `refs/heads/main` are the same input form | `main` is a short branch name; `refs/heads/main` is a full refname |
| `git check-ref-format` checks if a branch already exists | It only checks name syntax |
| A valid name guarantees branch creation will succeed | Permissions, duplicate refs, hooks, and hosting policies can still reject it |
| You can create both `feature` and `feature/login` simultaneously | The two refs can collide in file/directory storage |
| `--normalize` only checks without modifying the string | It prints the normalized name; do not use the result silently without policy |
| `--refspec-pattern` allows creating a branch containing `*` | The option only allows a wildcard when checking refspec patterns |
| Git handles case sensitivity identically on every machine | Filesystems and hosting platforms may handle it differently; use lowercase consistently |
| `HEAD` is an ordinary branch | `HEAD` is a special reference, which can be symbolic or detached |

## 15. Takeaways

Branches and tags are refs pointing to objects. Local branches live in the `refs/heads/` namespace, remote-tracking branches in `refs/remotes/`, and tags in `refs/tags/`. A short branch name like `feature/add-login` differs from the full ref `refs/heads/feature/add-login`; use `git check-ref-format --branch` to validate the short form and `git check-ref-format <full-ref>` to validate the full name.

A refname must not contain forbidden special characters, spaces, or control characters; no `..`, `@{`, `//`, leading/trailing slashes, components starting with a dot, or components ending with `.lock`. Use `--normalize` to view a full ref name after normalization, `--allow-onelevel` for single-level refs, and `--refspec-pattern` when validating wildcard refspecs.

Finally, valid syntax does not guarantee that a branch does not already exist or that the user has permission to create it. Check local/remote refs and naming policies separately. Use short, lowercase, consistently hierarchical names to reduce errors when collaborating across operating systems and hosting services.
