# Unicode filenames, invalid characters, and long paths

A Git repository can be developed across Windows, macOS, and Linux. Each operating system and filesystem handles filenames, letter casing, Unicode, and path length differently. As a result, a filename valid on a Linux machine may fail to check out on Windows; two different names in Git may also be treated as the same file on a case-insensitive drive.

Git stores path names in repository history, while the ability to create, read, and check out files also depends on the operating system and filesystem. For reliable collaboration, teams need to understand these differences, verify filenames before committing, and agree on a portable naming convention.

## 1. How does Git store path names?

In a repository, file and directory names are part of tree objects and the index. Git stores paths as byte sequences; `/` is used to separate path components, and the NUL byte cannot appear in a name. Git does not impose a single universal Unicode normalization rule across all operating systems.

In practice, Git must convert and exchange those paths with operating system APIs. Filesystems may restrict characters, how names are compared, Unicode forms, or path length. Consequently, a repository can contain a commit with filenames that another machine cannot check out or manipulate normally.

Some common differences:

| Environment | Typical characteristics | Collaboration risks |
|---|---|---|
| Linux with ext4 | Usually case-sensitive; allows many characters in names, aside from basic filesystem limits | Can create names invalid on Windows or names differing only by case |
| Windows with NTFS | Usually case-insensitive; has reserved characters and device names | Two distinct paths in Git can collide; some names cannot be created |
| macOS with APFS | Usually configured as case-insensitive, though case-sensitive volumes can be used; has compatibility issues around Unicode representations | Names differing by case or Unicode encoding can cause confusion |

These are common defaults, not absolute rules for every machine. The filesystem, volume formatting options, and Git configuration can alter behavior.

## 2. Unicode filenames and character normalization

Unicode allows a visible character to be represented by multiple equivalent code sequences. For example, the character `é` can be represented by:

- A single precomposed code point: `U+00E9` (LATIN SMALL LETTER E WITH ACUTE).
- Two code points: `U+0065` (LATIN SMALL LETTER E) followed by `U+0301` (COMBINING ACUTE ACCENT).

Two strings may render identically while having different UTF-8 bytes. Normalization form NFC typically uses precomposed characters when possible; NFD represents them using a base character combined with diacritics. Git does not automatically treat visually equivalent Unicode strings as the same path name in the object database.

This can lead to situations where:

- One machine creates a file in NFC form while another creates the name in NFD form.
- The terminal displays both names identically, yet Git treats them as two different byte sequences.
- A platform's filesystem or API normalizes names on read/write, causing collisions or making Git status confusing.

### core.precomposeUnicode on macOS

Git for macOS has the `core.precomposeUnicode` setting to handle decomposed Unicode names returned by macOS filesystems. When enabled, Git converts names to precomposed form when interacting with the repository to reduce discrepancies between filesystem representations and names stored in Git.

Check the active value:

```bash
git config --show-origin --get core.precomposeUnicode
```

If there is no output, the setting may be using the current Git build's default. On macOS, this option is usually enabled to support Unicode names. Only change this configuration when you understand its impact on the repository and collaboration environment; do not toggle it randomly as a guess when filenames look strange.

### Team Unicode conventions

To reduce risk, teams should agree to:

- Use UTF-8 for filenames and text contents.
- Use one consistent Unicode normalization form, typically choosing NFC for new names.
- Avoid creating two names that look identical while differing only in Unicode representation.
- Avoid visually confusable characters across different scripts when filenames have critical operational meaning.
- When batch-renaming Unicode names, check diffs and status on at least one other operating system.

## 3. Case sensitivity

Git distinguishes path names according to the data stored in the repository. However, many Windows and macOS volumes are case-insensitive by default. For example, Git can store two paths:

```text
src/Config.java
src/config.java
```

On a case-sensitive filesystem, these are two distinct files. On a case-insensitive volume, the two names can conflict because the filesystem treats them as the same path.

Another common risk is a case-only rename, such as `readme.md` to `README.md`. A Linux machine records it immediately, whereas on a case-insensitive Windows or macOS machine, the rename may not be detected as expected.

### Checking the core.ignoreCase configuration

Git provides `core.ignoreCase` to adapt to case-insensitive filesystems. When cloning or initializing a repository, Git can automatically set a value suited to the environment. Check the configuration:

```bash
git config --show-origin --get core.ignoreCase
```

Do not arbitrarily set `core.ignoreCase=false` on a case-insensitive volume to force Git to treat names like Linux. Git may display confusing status or fail to create names simultaneously that the filesystem considers duplicates. This setting helps Git adapt to the filesystem; it does not turn the filesystem case-sensitive.

### Case-only renames

If you need to rename `readme.md` to `README.md` on a case-insensitive machine, you can use an intermediate name:

```bash
git mv readme.md readme-temp.md
git mv readme-temp.md README.md
git status --short
```

Then inspect the diff and commit the rename. The intermediate step lets the filesystem recognize two separate rename operations. If the source filename differs from the example, substitute the repository's actual path.

## 4. Reserved characters and names on Windows

Windows imposes common filename restrictions that Linux permits. Within any path component name on Windows, avoid these characters:

```text
< > : " / \ | ? *
```

Additionally, Windows disallows control characters from U+0000 through U+001F in regular names. `/` and `\` are used as path separators; `:` has special meaning in drive syntax and alternate data streams.

Windows also has reserved device names, even when an extension is appended. Common ones include:

```text
CON   PRN   AUX   NUL
COM1  COM2  ... COM9
LPT1  LPT2  ... LPT9
```

For example, `NUL.txt`, `CON.log`, or `COM1.data` can still be treated as reserved device names. Some variants using Unicode superscript digits are also handled as device names by Windows; therefore, a portable rule should avoid this entire family of names rather than checking only a few common strings.

Path component names on Windows also should not end with a period or a space. For example, `report.` and `report ` may be normalized or become inaccessible as expected.

### Examples of risky names

| Name | Issue on Windows | Suggested replacement |
|---|---|---|
| `report:final.txt` | Contains `:` | `report-final.txt` |
| `image?.png` | Contains `?` | `image-1.png` |
| `data*.csv` | Contains `*` | `data-all.csv` |
| `CON` or `CON.txt` | Reserved device name | `console-output.txt` |
| `notes.` | Ends with a period | `notes` or `notes-final` |
| `draft ` | Ends with a space | `draft` |

If a commit created on Linux contains a name invalid on Windows, Windows users may encounter errors when checking out, switching branches, or resetting to that commit. In that case, fix the name in an environment that can access the file, commit the rename, and share the change so other platforms use a compatible name.

## 5. Long paths and the MAX_PATH limit

Path length depends not only on the final filename, but on all parent directories combined. For example, a short filename nested deep inside many directory levels can still produce a very long path:

```text
C:\Users\developer\Documents\workspace\company\platform\services\identity\src\main\java\com\example\security\authentication\AuthenticationConfiguration.java
```

On Windows, the traditional `MAX_PATH` limit is commonly cited as 260 characters for standard Win32-style paths. Modern Windows versions support longer paths if both system policy and applications meet the required conditions. Enabling long path support in Windows therefore does not automatically guarantee every program can handle long paths.

Git for Windows has its own setting to use appropriate APIs when handling long paths:

```bash
git config --show-origin --get core.longpaths
```

If a team uses Git for Windows and hits errors such as `Filename too long`, it can be enabled in the current repository:

```bash
git config core.longpaths true
```

This setting writes local configuration for the repository. It helps Git for Windows handle long paths in supported operations, but it does not change limits in editors, IDEs, compilers, build tools, shells, or other applications. Windows may also need long path support enabled in policy, and applications must support that mechanism.

### Ways to reduce path length

- Clone the repository into a shorter directory, such as `C:\src\project`, instead of deeply nested directories.
- Shorten unnecessary directory names or reduce nesting depth.
- Avoid repeating long module names across multiple directory levels when the structure can be simplified.
- Enable `core.longpaths` in Git for Windows when needed and verify downstream tools in the pipeline.
- Test checkout on actual Windows machines, since success on Linux does not prove every path will work on Windows.

Do not rely solely on long-path settings when designing a repository structure. Short, readable paths help IDEs, build tools, and CI run more reliably.

## 6. Inspecting path names in a repository

Several Git commands let you inspect the filenames a repository manages:

```bash
# List tracked paths in the index.
git ls-files

# View paths with short status.
git status --short

# List paths in a specific commit.
git ls-tree -r --name-only HEAD
```

By default, Git may quote special or non-ASCII characters in output to prevent terminals from misinterpreting them. If you want to display Unicode characters directly for visual inspection:

```bash
git -c core.quotepath=false ls-files
```

If you want to view escaped forms to distinguish bytes or special characters, use the default `core.quotepath=true`:

```bash
git -c core.quotepath=true ls-files
```

Escaped output does not mean a filename is corrupted; it may simply be Git's safe terminal representation. For scripts processing filenames, prefer NUL-delimited output:

```bash
git ls-files -z
```

Do not parse `git ls-files` output by splitting on spaces or newlines if filenames may contain special characters. Use `-z` and process the NUL delimiter to preserve names intact.

## 7. Standardizing filenames for cross-platform compatibility

A simple convention eliminates most issues:

1. Use lowercase ASCII for directory and technical filenames when Unicode is unnecessary.
2. Use hyphens `-` or underscores `_` instead of spaces and special separator characters.
3. Avoid Windows device names, trailing periods, or trailing spaces.
4. Avoid two paths differing only by uppercase/lowercase.
5. For Unicode names, standardize on UTF-8 and NFC normalization.
6. Keep directory structures shallow and path components short and readable.
7. Test rename changes on Windows, macOS, and Linux before releasing.

Examples of converting inconsistent names to portable names:

| Original name | Suggested name |
|---|---|
| `User Profile/` | `user-profile/` |
| `API Response.JSON` | `api-response.json` |
| `cấu hình local/` | `local-config/` if there is no need to keep a Vietnamese name |
| `release:2026.txt` | `release-2026.txt` |
| `Image.PNG` and `image.png` | Pick one unique name, e.g., `image.png` |

Not every accented or Unicode name is invalid. Vietnamese names can work normally if environments handle Unicode consistently. What matters is avoiding equivalent representations with differing bytes, avoiding platform-unsupported names, and testing checkout across the operating systems the team uses.

## 8. Detecting and fixing conflicting names

If you suspect a repository contains two names differing only by case or Unicode form, list the paths and compare them. You can view the names stored by Git with:

```bash
git -c core.quotepath=true ls-files
```

If the current filesystem cannot represent both paths, inspection may need to be done on a case-sensitive volume or a Linux environment. After identifying the canonical name to keep, rename to a single name and commit the change.

Example of renaming a file with Git:

```bash
git mv -- "src/OldName.java" "src/new-name.java"
git status --short
git diff --cached --summary
```

For case-only renames on a case-insensitive filesystem, use an intermediate name as shown earlier:

```bash
git mv -- "src/Config.java" "src/config-temp.java"
git mv -- "src/config-temp.java" "src/config.java"
```

If a file in a commit has a name invalid on Windows and Windows cannot check out that commit, ask a teammate on Linux or a filesystem that supports the name to perform the rename and push a fix commit. Avoid modifying `.git` directly to manually rename objects or index entries.

## 9. Checks in CI and code review workflows

For multi-OS projects, include filename portability checks in your review or CI workflow. A policy can verify:

- No two paths collide when lowercased under the team's comparison rules.
- No Windows-prohibited characters or reserved device names exist.
- No path component ends with a period or space.
- Unicode names follow the agreed normalization form.
- Paths do not exceed internal limits supported by build tools and IDEs.

CI should run checkout and build steps on Windows, macOS, and Linux if those platforms are supported. Running unit tests on only one OS can miss filename errors that occur right at the checkout step.

If the team enforces strict rules, you can write a validation script reading from `git ls-files -z` to process all path names accurately. The script should handle NUL-delimited data, compare case-insensitively per the chosen rules, and check Windows reserved characters/names. Do not use a naive lowercase conversion as the sole Unicode comparison if the project supports multiple languages; explicitly define normalization and case-folding policies.

## 10. Troubleshooting a filename error on a specific platform

Suppose a Windows team member cannot check out a branch recently pushed from Linux and receives an error related to filenames or long paths. You can investigate in this order:

1. Record the exact error message and path name Git is processing.
2. Check current state with `git status` without deleting a working directory that holds data.
3. Inspect the tracked filenames list with `git -c core.quotepath=true ls-files` or `git ls-tree -r --name-only <commit>`.
4. Check whether names contain prohibited characters, device names, trailing dots/spaces, case collisions, or Unicode normalization discrepancies.
5. If the error is a path that is too long, try cloning into a shorter directory and inspect `core.longpaths` along with Windows policy.
6. If a name is invalid on Windows, perform the rename in an environment able to access the file and commit the change.
7. Re-checkout the fixed commit on Windows and run relevant build/test steps.

Diagnostic commands for long paths on Git for Windows:

```bash
git config --show-origin --get core.longpaths
git config --show-origin --get core.ignoreCase
```

The commands above only read configuration. Enable `core.longpaths` only when long-path support is needed on Git for Windows; do not alter `core.ignoreCase` to try to bypass filesystem limits.

## 11. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| Filenames valid on Linux are valid everywhere | Windows has reserved characters and device names; filesystems also differ in case sensitivity |
| Two visually identical Unicode names are always the same name | Unicode strings can have different encoding/normalization forms and different bytes |
| Git automatically normalizes all Unicode names | Git stores paths in objects/index and does not enforce one universal Unicode normalization across all platforms |
| `core.ignoreCase=false` makes Windows case-sensitive | The setting does not change the filesystem's name-comparison capability |
| Enabling `core.longpaths` fixes all long-path errors | It helps Git for Windows; editors, IDEs, build tools, and other apps still have their own limits |
| Git quoting Unicode characters means the name is corrupted | Quoting may just be Git's safe output representation |
| Case-only renames always work identically | On case-insensitive filesystems, use an intermediate name and verify status |

## 12. Takeaways

Path names in Git are stored in the repository, while file operations depend on the filesystem and operating system. When maintaining a cross-platform repository, pay attention to three main risk areas: Unicode and character normalization, case differences alongside Windows reserved characters/names, and total path length.

Use `git ls-files` or `git ls-tree` to inspect stored names; `core.precomposeUnicode` helps with certain Unicode differences on macOS; `core.ignoreCase` helps Git adapt to case-insensitive filesystems; `core.longpaths` helps Git for Windows handle long paths. These settings do not replace a portable filename convention.

Prefer clear, short, consistent names that can be checked out on every platform the team supports. When errors occur, identify the exact issue before changing settings or renaming, then verify by checking out and building on the affected environment.
