# Configuring Name, Email, and Distinguishing Author from Committer

Every Git commit records information about who is credited as the author and who created the commit. These two roles normally belong to the same person when you run an ordinary `git commit`, but they can differ when someone applies a commit from another person, cherry-picks, rebases, or rewrites history. To keep project history accurate, you need to configure your Git name and email properly and understand the **Author** and **Committer** fields in a commit.

Git uses `user.name` and `user.email` as the default identity when creating commits. This is metadata stored in the commit object; it is not a username, password, or authentication mechanism for the Git server. Pushing successfully still depends on credentials and remote access permissions.

## 1. Configuring name and email for Git

Set the global name and email for the current user:

```bash
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"
```

These values are used as defaults for the user's repositories unless a configuration in a higher-precedence scope overrides them.

If a repository needs a separate identity, change into that repository and configure it locally:

```bash
git config --local user.name "An Nguyen - Company"
git config --local user.email "an.nguyen@company.example"
```

Local configuration is stored in the repository's `.git/config` and applies only to that repository. This is the right option when you use the same machine for both corporate work and personal projects.

You can open the configuration file to edit multiple values:

```bash
git config --global --edit
git config --local --edit
```

Example content in the configuration file:

```ini
[user]
    name = Nguyen Van An
    email = an@example.com
```

Name and email are metadata strings. You can use accented characters or a display name following your team's conventions; what matters is that the email should be an address you want associated with commit history. If you use GitHub or a similar platform and want to hide your personal email, you can use the noreply address provided by the service in your account settings.

## 2. Configuration scopes and precedence order

Git reads configuration from multiple scopes. For the same key, the value from the higher-precedence scope is used:

| Scope | Command to set | Scope |
|---|---|---|
| System | `git config --system ...` | All users on the machine; usually requires administrative privileges |
| Global | `git config --global ...` | Current user, across multiple repositories |
| Local | `git config --local ...` | Current repository |
| Worktree | `git config --worktree ...` | Current worktree when the repository enables the `worktreeConfig` extension |
| Command | `git -c user.name="..." ...` | Only the Git command invoked with that option |

Among standard scopes, the ascending order of precedence is system, global, local, worktree, and command. Environment variables used to supply author/committer identity can override the identity read from configuration when creating a commit.

For example, if global sets a personal email while a corporate repository sets a corporate email locally, commits in the corporate repository use the local email:

```bash
# User's default value
git config --global user.email "an@example.com"

# Value specific to the current repository
git config --local user.email "an.nguyen@company.example"

# Effective value in the current repository
git config --get user.email
```

There is no need to set `--global` for every situation. Choose the smallest scope that matches your intent so a corporate identity is not accidentally used on a personal repository or vice versa.

## 3. Checking which identity Git is using

View the effective name and email specifically:

```bash
git config --get user.name
git config --get user.email
```

To see which configuration file and scope a value comes from, use:

```bash
git config --show-origin --show-scope --get-regexp '^user\.(name|email)$'
```

This command is useful when there are multiple configuration files or when you do not remember whether you set an identity globally or locally. `--show-origin` shows the file source; `--show-scope` shows the scope.

To see the identities Git will use as author and committer in the current command environment:

```bash
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

These two commands help detect cases where configuration looks right but environment variables are overriding the identity. They display the identity along with the timestamp Git computes for each respective role.

If you want to prevent Git from guessing an identity from your OS username or machine hostname when not explicitly configured, you can enable:

```bash
git config --global user.useConfigOnly true
```

With this enabled, Git requires identity to be explicitly provided via configuration or an appropriate source; commit creation commands will fail with an error if no valid identity is present. This setting is useful on machines used for multiple projects or in automation environments.

## 4. How do Author and Committer differ?

A commit object contains two sets of identity information:

- **Author:** the person credited with originally creating the changes.
- **Committer:** the person or process that created the current commit object and recorded it into history.

When you edit source code yourself and run `git commit`, Author and Committer are usually the same. When you receive a commit written by someone else and recreate that commit in your repository, the two roles can differ.

For example, Linh writes a change and sends a patch to An. An applies the patch and creates a commit in the repository:

```text
commit 8a31...
Author:    Linh Tran <linh@example.com>
Committer: Nguyen Van An <an@example.com>

    Add input validation
```

Linh is the Author because Linh created the change. An is the Committer because An created the commit object in the repository. Recording it this way preserves original attribution while still showing who brought the change into the current history.

Author and Committer are commit metadata. They do not prove legal identity or account permissions. Anyone who can create a commit can supply a name/email string in configuration or environment variables; commit signing is a separate verification mechanism.

## 5. Where does Git get Author and Committer from?

Normally, Git gets both identities from `user.name` and `user.email`. When creating a commit, Git can also use separate environment variables for each role:

| Role | Override environment variables |
|---|---|
| Author | `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL`, `GIT_AUTHOR_DATE` |
| Committer | `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL`, `GIT_COMMITTER_DATE` |

If an environment variable for a field is set, Git uses that value for the corresponding field instead of the regular configuration value. Consequently, a CI script can create a commit whose committer is a bot while preserving the contributor as author.

For example, in a POSIX environment, you can set separate identities for a single command:

```bash
GIT_AUTHOR_NAME="Linh Tran" \
GIT_AUTHOR_EMAIL="linh@example.com" \
GIT_COMMITTER_NAME="Release Bot" \
GIT_COMMITTER_EMAIL="release-bot@example.com" \
git commit -m "Apply reviewed patch"
```

In PowerShell, setting temporary environment variables for the current session uses different syntax:

```powershell
$env:GIT_AUTHOR_NAME = "Linh Tran"
$env:GIT_AUTHOR_EMAIL = "linh@example.com"
$env:GIT_COMMITTER_NAME = "Release Bot"
$env:GIT_COMMITTER_EMAIL = "release-bot@example.com"
git commit -m "Apply reviewed patch"

# Remove variables after use to avoid affecting subsequent commands
Remove-Item Env:GIT_AUTHOR_NAME
Remove-Item Env:GIT_AUTHOR_EMAIL
Remove-Item Env:GIT_COMMITTER_NAME
Remove-Item Env:GIT_COMMITTER_EMAIL
```

Only use environment overrides when there is a clear reason, such as automation or patch-ingestion workflows. If those variables remain set in your terminal longer than intended, subsequent commits may continue recording unintended identities.

## 6. Scenarios where Author and Committer change across operations

| Operation | Author typically recorded | Committer typically recorded |
|---|---|---|
| Regular `git commit` | Current identity | Current identity |
| `git commit --author="..."` | Person specified via `--author` | Current identity |
| `git cherry-pick <commit>` | Author of the source commit is preserved | Person performing the cherry-pick |
| `git rebase` replaying commits | Author of the original commit is typically preserved | Person performing the rebase |
| Creating a merge commit | Person creating the merge commit | Person creating the merge commit |
| `git commit --amend` | Typically keeps the old commit's Author | Person creating the new commit |

The words "typically" in the table emphasize that options and environment variables can change the outcome. For example, `--author`, `--reset-author`, `GIT_AUTHOR_*`, or `GIT_COMMITTER_*` can override the default behavior.

### Cherry-pick

When cherry-picking Linh's commit onto a branch managed by An, Git creates a new commit on the current branch. The Author usually remains Linh; the Committer is An. This reflects that Linh wrote the change while An applied the commit onto the new line of history.

```bash
git cherry-pick 8a31...
git show --format=fuller --no-patch HEAD
```

### Rebase

During a rebase, Git replays commits onto a new base. The recreated commits get new OIDs; the Author is typically preserved from the original commit, while the Committer is updated to the person performing the rebase. Therefore, rebasing can change `CommitDate` even though `AuthorDate` stays the same.

### Amend

`git commit --amend` replaces the tip commit with a new commit. By default, Git preserves the old commit's Author information and updates the Committer information. If you want to claim yourself as the Author of the new commit, use `--reset-author`:

```bash
git commit --amend --reset-author --no-edit
```

This option sets Author to the current identity and refreshes the author timestamp. Because amend creates a new commit, the commit's OID changes.

## 7. Specifying the Author for a single commit

If you are applying changes written by someone else, you can credit the Author with `--author`:

```bash
git add src/validator
git commit --author="Linh Tran <linh@example.com>" -m "Add input validation"
```

In this case, the Author is Linh; the Committer still comes from your current identity or the corresponding committer override source.

If you want to create a new commit and use your current identity as Author—even when amending or reusing information from another commit—you can use `--reset-author` in contexts where Git supports it:

```bash
git commit --amend --reset-author --no-edit
```

Do not arbitrarily change someone else's Author attribution just to make history look uniform. Keep attribution accurate to reality and follow the project's authorship conventions.

## 8. Reading Author and Committer in history

To view the full identities and dates of the current commit:

```bash
git show --format=fuller --no-patch HEAD
```

The output contains `Author`, `AuthorDate`, `Commit`, `CommitDate`, and the commit message. `git log --pretty=fuller` lets you view the same information across multiple commits:

```bash
git log --pretty=fuller -5
```

If you need to inspect the raw contents of the commit object directly:

```bash
git cat-file -p HEAD
```

You will see the `author` and `committer` lines along with timestamps and timezones. This is data stored inside the commit object; Git does not re-query current configuration to display past history.

To print only names/emails and dates in a custom format:

```bash
git log -5 --format="%h | author=%an <%ae> | committer=%cn <%ce>"
git log -5 --format="%h | author-date=%aI | commit-date=%cI"
```

Common placeholders:

| Placeholder | Content |
|---|---|
| `%an`, `%ae` | Author name and email |
| `%cn`, `%ce` | Committer name and email |
| `%aI` | Author date in strict ISO 8601 format |
| `%cI` | Committer date in strict ISO 8601 format |
| `%h`, `%H` | Abbreviated and full commit OID |

## 9. Fixing a misconfigured identity

If new commits are using the wrong name or email, check scopes first:

```bash
git config --show-origin --show-scope --get-regexp '^user\.(name|email)$'
git var GIT_AUTHOR_IDENT
git var GIT_COMMITTER_IDENT
```

Then fix the appropriate scope:

```bash
# Fix defaults for the user
git config --global user.name "Nguyen Van An"
git config --global user.email "an@example.com"

# Or fix only the current repository
git config --local user.name "An Nguyen - Company"
git config --local user.email "an.nguyen@company.example"
```

Changing configuration affects only commits created afterward. It does not automatically fix Author or Committer in existing commits.

If the commit with the wrong identity has not been shared yet, you can recreate the commit with amend:

```bash
git config --local user.name "Nguyen Van An"
git config --local user.email "an@example.com"
git commit --amend --reset-author --no-edit
```

This command replaces the tip commit with a new commit and sets Author to the current identity. If you only need to change the Committer or want to preserve the original Author, do not use `--reset-author`; consider amending with the correct configuration and verifying the result with `git show --format=fuller HEAD`.

If the commit has already been pushed or others have based work on it, fixing the identity rewrites history. Coordinate with your team before amending/rebasing and updating the remote; never force-push a shared branch solely to fix metadata without agreement.

## 10. Git identity is not authentication credentials

`user.name` and `user.email` only specify the information recorded inside commits. They do not grant read or write permissions on a repository. Authenticating with a remote typically uses a credential manager, token, SSH key, or the hosting platform's mechanism.

For example, you can set `user.email` to your corporate email and still be unable to push if your account has not been granted permissions. Conversely, you may have push permissions while commits still record your personal email if your Git configuration is using that email.

If a hosting platform uses email to link commits to a user profile, ensure the email in your commits is a verified address or a valid noreply address for your account. That links contributions to the right profile, but remains a metadata linking mechanism and does not replace authentication.

## 11. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Author and Committer are always the same person | They are usually the same in regular commits, but can differ during cherry-pick, rebase, amend, or patch application. |
| `user.name` is your GitHub/GitLab login username | It is a metadata name inside commits, not an authentication account. |
| Changing `git config user.email` fixes old commits | No. Configuration affects only commits created afterward; old commits must be recreated if they need fixing. |
| Cherry-pick always changes Author to whoever runs the command | Normally cherry-pick preserves the source commit's Author and records the person running it as Committer. |
| Rebase only moves commit positions | Rebase recreates commits; OIDs and Committer info typically change. |
| `--author` changes both Author and Committer | It specifies only Author; Committer still comes from your current identity or a separate override. |
| The email in a commit proves that person authenticated with the remote | No. It is metadata supplied by whoever created the commit; remote access is checked by a separate authentication mechanism. |

## 12. Self-check

1. **Which command sets the default name and email for the current user?**
   - `git config --global user.name "..."` and `git config --global user.email "..."`.
2. **To set a separate identity for a single repository, which scope do you use?**
   - `--local`.
3. **How do Author and Committer differ?**
   - Author is the person credited with creating the change; Committer is the person or process that created the current commit object.
4. **When cherry-picking someone else's commit, who is typically the Author?**
   - The Author of the source commit; the person running cherry-pick typically becomes the Committer.
5. **Which command displays the Author and Committer of the current commit?**
   - `git show --format=fuller --no-patch HEAD`.
6. **Does changing `user.email` update the email in commits already created?**
   - No. You must recreate commits if you want to change the metadata of old commits.

## Conclusion

Configure `user.name` and `user.email` at the right scope so new commits carry the appropriate identity for the repository. Use `git config --show-origin --show-scope`, `git var GIT_AUTHOR_IDENT`, and `git var GIT_COMMITTER_IDENT` to verify effective values. Author records who created the change; Committer records the person or process that created the current commit. The two roles can differ during cherry-pick, rebase, or amend. This identity is historical metadata, separate from authentication credentials and remote access permissions.
