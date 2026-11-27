# LF, CRLF, and why mass line changes can occur

A text file can use LF or CRLF to end each line. LF is common on Linux and macOS; CRLF is common on Windows. When team members use different operating systems, editors, or Git configurations, a single checkout, file save, or stage can change the line endings of many files. Git may show almost the entire file as modified even though the program logic has not changed.

In the **Multiple Environments** chapter of the **SOURCE_CONTROL_GIT** module, this lesson explains how Git handles line endings between the working tree and the object database, the roles of core.autocrlf, core.eol, and .gitattributes, and how to find the root cause when mass diffs appear. You will learn how to establish a shared convention for a repository and normalize files while still being able to inspect actual content changes.

After this lesson, you will be able to:

- Distinguish between LF, CRLF, and files with mixed line endings.
- Explain why identical text content can produce a large diff when line endings change.
- Understand how Git normalizes content when adding files to the index and on checkout.
- Inspect line ending configurations at the system, user, and repository levels.
- Use .gitattributes to enforce consistent line endings for a team.
- Diagnose issues using git ls-files --eol, git check-attr, and diff commands.
- Normalize tracked files and verify the results safely.

## 1. What are LF and CRLF?

Computers represent text using characters. Line-ending characters indicate where one line stops and the next line begins.

| Type | Character | Common representation |
| --- | --- | --- |
| LF | Line Feed, byte 0A | \n |
| CRLF | Carriage Return followed by Line Feed, bytes 0D 0A | \r\n |
| CR | Carriage Return, byte 0D | \r |

LF is common on modern Linux and macOS. CRLF is common on Windows and is often used by default by some Windows editors or tools. Standalone CR is mainly encountered in legacy data or older systems.

For example, consider the same three lines of text:

~~~text
alpha
beta
gamma
~~~

If the file uses LF, each line ends with a single 0A byte. If it uses CRLF, each line ends with two bytes, 0D 0A. When displayed in an editor, the content may look identical, but the byte sequences in the file are different.

A file can also contain mixed line endings: some lines end with LF, while others end with CRLF. This can happen when combining content from multiple sources, copying and pasting, using editors with inconsistent configurations, or running a conversion tool on only part of a file.

Line endings are different from encoding. UTF-8, UTF-16, BOM, and other character encodings determine how characters are represented; LF and CRLF determine how lines are separated. Changing encoding can alter many other bytes, so when investigating a mass diff, determine whether it is a line-ending change or an encoding change.

## 2. Why do line-ending changes create large diffs?

Git stores file contents as blobs. A blob's hash is computed from its byte content, so two files with the same characters where one uses LF and the other uses CRLF will still produce two different blobs.

Suppose the current commit contains an LF file:

~~~text
alpha<LF>
beta<LF>
gamma<LF>
~~~

An editor re-saves the entire file with CRLF:

~~~text
alpha<CRLF>
beta<CRLF>
gamma<CRLF>
~~~

To Git, every line has changed at the byte level. The diff may mark all old lines as deleted and all new lines as added, even though the words and logic have not changed.

This phenomenon commonly occurs in the following situations:

- A team member checks out files as CRLF and then commits them while the repository stores LF.
- An editor automatically converts the entire file to the operating system's default line endings.
- The core.autocrlf configuration differs across team members' machines.
- The repository is missing .gitattributes or specifies line endings inconsistently.
- A line-ending conversion is mixed together with logic changes in the same commit.
- A file already had mixed line endings and a save tool normalizes the entire file to a single style.

The consequences go beyond hard-to-review pull requests. Noisy diffs also increase merge conflicts, make tracing with blame difficult, and make it harder for reviewers to spot actual functional changes.

## 3. Git processes line endings at two points in time

To understand the configuration, distinguish between two conversion directions:

1. **Check-in**: content moves from the working tree into the index and is then written as a blob in a commit.
2. **Checkout**: content from a commit or the index is written out to the working tree.

When Git applies text normalization, it can normalize CRLF to LF during check-in. On checkout, Git can convert LF in the normalized content into the line-ending style appropriate for the configuration or the file's attributes.

~~~text
Working tree on Windows
        CRLF
         |
         | clean / check-in conversion
         v
Normalized index and blob
         LF
         |
         | checkout conversion
         v
Working tree per convention
        CRLF
~~~

The diagram above illustrates the case where the repository convention stores normalized text with LF and the working tree uses CRLF. Not every file is converted automatically: Git needs the appropriate configuration or the text attribute in .gitattributes.

Without normalization rules, Git may store the exact line-ending bytes present in the file. Therefore, you should not assume every blob in the repository uses LF. To know the actual state, inspect the index, the working tree, and the attributes.

## 4. The core.autocrlf configuration

Git provides the core.autocrlf setting to control automatic line-ending conversion for text files when no more specific attribute rule overrides it.

| Value | When adding content to Git | On checkout |
| --- | --- | --- |
| true | Normalizes CRLF to LF for files detected as text | Converts LF to CRLF in the working tree |
| input | Normalizes CRLF to LF for files detected as text | Does not convert LF to CRLF |
| false | Does not automatically convert via this setting | Does not automatically convert via this setting |

On Windows, some users set:

~~~bash
git config --global core.autocrlf true
~~~

On Linux or macOS, teams often choose:

~~~bash
git config --global core.autocrlf input
~~~

These examples are per-user configurations, not mandatory rules for every machine. When a repository has a clear .gitattributes file, file attributes serve as an important baseline to unify behavior across team members.

Check the value and configuration source:

~~~bash
git config --show-origin --get core.autocrlf
~~~

If there is no output, the value may not be set and Git uses the default. Use --show-origin to see which file the configuration comes from, such as system, global, or local. A repository's local configuration can cause two repositories on the same machine to behave differently.

## 5. The core.eol configuration

core.eol specifies the line-ending style Git uses when checking out text files that are marked for line-ending processing and have no more specific eol attribute.

Common values:

- **lf**: the working tree uses LF.
- **crlf**: the working tree uses CRLF.
- **native**: uses the operating system's native line-ending style.

Example:

~~~bash
git config --global core.eol lf
~~~

Or configure it for the current repository:

~~~bash
git config --local core.eol native
~~~

Check:

~~~bash
git config --show-origin --get core.eol
~~~

core.eol does not automatically treat every file as text. Git needs to recognize a file as text via attributes or the autocrlf mechanism. If you want an explicit policy by file type applied uniformly across the entire team, declare it in .gitattributes.

## 6. Using .gitattributes for repository-wide consistency

.gitattributes is a file that defines attributes for paths in a repository. Because this file is committed alongside the source code, all team members and CI can share the same line-ending policy.

Example of a common policy:

~~~gitattributes
# Auto-detect text files and normalize line endings in the repository
* text=auto

# Shell scripts always use LF
*.sh text eol=lf

# Windows scripts use CRLF in the working tree
*.bat text eol=crlf
*.cmd text eol=crlf

# Binary files do not undergo text conversion
*.png -text
*.jpg -text
*.pdf -text
~~~

Meaning:

- **text=auto** tells Git to auto-detect text files and normalize the line endings of files detected as text on check-in.
- **text eol=lf** marks the file as text and requires the working tree to use LF.
- **text eol=crlf** marks the file as text and requires the working tree to use CRLF.
- **-text** disables text normalization for the specified file type.

If you want common text file types to use LF in the working tree, keep the general auto-detection rule and then explicitly specify the file groups that require LF:

~~~gitattributes
* text=auto
*.txt text eol=lf
*.md text eol=lf
*.java text eol=lf
~~~

Do not set eol=lf broadly for all paths if the repository contains binary files. The eol attribute forces paths to be treated as text; apply it only to identified text file types.

Choose a policy that fits the project's tools and runtime environments. For example, shell scripts usually require LF to run reliably on Linux; some batch files or configurations for Windows tools may require CRLF. Do not apply a single rigid rule to all file types if the project has different requirements.

For binary files, use -text or the binary macro attribute where appropriate. Do not force line-ending normalization on images, PDFs, archives, fonts, or binary data files.

## 7. How do text, eol, and binary attributes differ?

| Attribute | Effect |
| --- | --- |
| text | Treats the file as text and normalizes CRLF to LF on check-in |
| text=auto | Lets Git auto-detect text files before normalizing |
| eol=lf | Enforces LF line endings in the working tree; also enables text handling |
| eol=crlf | Enforces CRLF line endings in the working tree; also enables text handling |
| -text | Does not apply text normalization to the file |
| binary | Attribute macro commonly used for binary files; disables normal text, diff, and text merge handling |

Attributes can be set by extension, directory, or specific filename. For example:

~~~gitattributes
* text=auto
docs/**/*.md text eol=lf
scripts/**/*.sh text eol=lf
windows/**/*.cmd text eol=crlf
assets/** -text
~~~

Path patterns in .gitattributes have their own matching rules. Place the file in the appropriate location and verify the applied result rather than assuming a pattern matches every desired path.

Check the attributes of a file:

~~~bash
git check-attr text eol -- README.md
git check-attr --all -- scripts/build.sh
~~~

The first command shows the text and eol values applied to README.md. The second command lists all attributes applied to the script. If the result is unspecified, the file may be affected by automatic configuration or rules at another level.

## 8. Diagnosing with git ls-files --eol

When many files are reported as modified, the most useful command to compare line endings in the index, the working tree, and attributes is:

~~~bash
git ls-files --eol
~~~

Example output:

~~~text
i/lf    w/crlf  attr/text eol=crlf    src/App.java
i/lf    w/lf    attr/text eol=lf      scripts/build.sh
i/-text w/-text attr/-text            assets/logo.png
~~~

Columns:

- **i/**: line-ending style detected in the index content.
- **w/**: line-ending style detected in the working tree.
- **attr/**: line-ending/text attributes applied to the file.
- End: the file path.

Some possible values you may see:

- lf: Git detected LF.
- crlf: Git detected CRLF.
- mixed: the file has inconsistent line endings.
- none: no line endings detected.
- -text or unspecified: no text normalization according to the corresponding attribute.

Seeing i/lf and w/crlf together with attr/text eol=crlf can be a normal state: the index stores LF-normalized content, while the working tree uses CRLF as configured. There is not necessarily a diff just because the two columns differ.

If you see i/lf and w/crlf when the attributes are not set as expected, check core.autocrlf, core.eol, and .gitattributes. If you see w/mixed, the file may have been edited with a tool that preserved some LF lines while converting other lines to CRLF.

You can check a single file individually:

~~~bash
git ls-files --eol -- src/App.java
~~~

Combine this command with git check-attr and git config --show-origin to determine the origin of the policy.

## 9. Determining whether mass changes are caused only by line endings

When diff reports many modified files, do not rush to stage or commit. Determine the scope and compare from multiple perspectives.

### Check status

~~~bash
git status --short
git diff --stat
git diff --numstat
~~~

If very many files have nearly equal numbers of deleted and added lines, a line-ending conversion or whole-file reformatting may have occurred. This is a clue to investigate, not conclusive proof.

### Ignore differences at the end of lines when comparing

~~~bash
git diff --ignore-space-at-eol
~~~

This option ignores whitespace differences at the end of lines when displaying a diff. It is useful for seeing the remaining logic changes after ignoring end-of-line differences. If the diff almost disappears, the cause may be primarily line endings or trailing whitespace.

You can inspect a single file:

~~~bash
git diff --ignore-space-at-eol -- src/App.java
~~~

Do not use this result as a substitute for inspecting the normal diff. Trailing whitespace can sometimes be meaningful for data files, formatting, or processing tools. Confirm by checking the configuration and the actual byte state.

### Check line endings and attributes

~~~bash
git ls-files --eol
git check-attr --all -- src/App.java
git config --show-origin --get core.autocrlf
git config --show-origin --get core.eol
~~~

Compare the output between an affected file and a similar unaffected file. If the attributes or configuration differ, that may be the reason for inconsistent checkout/check-in behavior.

## 10. Why can team members see different states?

Git config can be set at multiple levels:

| Level | Scope | Example |
| --- | --- | --- |
| system | System-wide | Configuration set by a machine administrator |
| global | Current user | Configuration in the user configuration file |
| local | Current repository | Project-specific configuration |
| worktree | Specific worktree if enabled and supported | Configuration specific to one worktree |

The effective value can come from a higher-precedence level. Therefore, two team members can clone the same repository yet get different line endings due to different core.autocrlf, core.eol, or editor settings.

In addition to Git config, editors can have their own settings:

- Automatically use the operating system's line endings.
- Preserve the line endings of the opened file.
- Convert the entire file to LF or CRLF on save.
- Change line endings only for pasted content.

An .editorconfig file can help editors share the same convention:

~~~editorconfig
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true

[*.{bat,cmd}]
end_of_line = crlf
~~~

.editorconfig guides editors when opening and saving files; .gitattributes defines how Git processes files in the repository. The two files complement each other but do not replace each other. If an editor does not support EditorConfig, the rules in the file may not be applied.

## 11. Establishing a line-ending policy for a team

A maintainable workflow typically includes the following steps:

1. Choose a standard line ending in the repository, usually LF for most text files.
2. Identify file types that need exceptions, such as shell scripts or batch files.
3. Record the policy in .gitattributes and commit it with the repository.
4. Consider adding .editorconfig so team members' editors save with the right style.
5. Instruct team members to check core.autocrlf and not change personal settings arbitrarily without understanding the impact.
6. Normalize the repository in a separate commit, review the diff, and test.

Example of a simple policy:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.png -text
*.jpg -text
*.zip -text
~~~

The rules must reflect the project's reality. If specialized files require different line endings, add specific patterns and verify with git check-attr. Avoid overlapping rules that make it hard for team members to predict the final attribute.

## 12. Normalizing a repository that already has mixed line endings

If the repository already contains many LF/CRLF files, the policy must be agreed upon before converting. Avoid mixing logic edits and full line-ending conversions in the same commit whenever they can be separated.

### Step 1: check the current state

~~~bash
git status --short
git ls-files --eol
~~~

Ensure the working tree is clean or that any in-progress changes are saved separately. Record which files currently have LF, CRLF, or mixed line endings.

### Step 2: add or update .gitattributes

Choose rules by file type. For example:

~~~gitattributes
* text=auto
*.sh text eol=lf
*.bat text eol=crlf
*.cmd text eol=crlf
*.png -text
*.jpg -text
~~~

Verify the attributes for representative files:

~~~bash
git check-attr --all -- src/App.java scripts/build.sh windows/run.cmd assets/logo.png
~~~

### Step 3: re-apply the clean process to tracked files

After choosing and verifying the policy, run:

~~~bash
git add --renormalize .
~~~

The --renormalize option instructs Git to re-apply the clean process to tracked files. The normalization changes will appear in the index. This command does not commit automatically.

Run this only when you understand the policy and have saved any unfinished work. If .gitattributes is wrong, renormalize can produce a large number of unwanted changes.

### Step 4: review what is staged

~~~bash
git status --short
git diff --cached --stat
git diff --cached
git diff --cached --ignore-space-at-eol
~~~

The normal diff shows the staged byte changes. The diff ignoring end-of-line whitespace helps clearly show any actual content changes. Verify that the affected files match the intended scope of the policy.

### Step 5: create a dedicated normalization commit

When the diff contains only the expected line-ending changes and the files to be normalized, create a separate commit with a clear message, for example:

~~~bash
git commit -m "chore: normalize text file line endings"
~~~

A separate commit makes subsequent feature pull requests easier to review and lets investigators know that a large change was solely for line-ending normalization.

### Step 6: verify after committing

~~~bash
git status --short
git ls-files --eol
git diff HEAD^ HEAD --ignore-space-at-eol
~~~

Confirm that the working tree is clean, the EOL states match the attributes, and the diff after ignoring end-of-line differences contains no unexpected logic changes.

## 13. Handling a pull request with a mass diff caused by EOL

When a review reveals that a pull request modifies almost every file, you can follow this workflow:

1. Check git diff --stat to determine the scope.
2. Run git ls-files --eol for representative files.
3. Check .gitattributes and git check-attr.
4. Check core.autocrlf, core.eol, and editor settings.
5. Use git diff --ignore-space-at-eol to identify the remaining logic changes.
6. Coordinate with the author to separate EOL changes from functional changes if needed.

If the line-ending changes occurred only in the working tree and have not been staged, after ensuring there are no edits to keep, you can restore a file to the content of HEAD:

~~~bash
git restore --source=HEAD --worktree -- path/to/file
~~~

This command overwrites the working tree content of the specified file. If the file has real edits, those edits will also be discarded. Back up or commit before running it.

If the changes have already been staged and you want to discard both the index and working tree versions for a file:

~~~bash
git restore --source=HEAD --staged --worktree -- path/to/file
~~~

This command also discards the staged changes for that file. Use it only after confirming the content does not need to be kept. Then apply the .gitattributes policy and re-check the line endings.

Do not use git reset --hard or git clean solely to handle an EOL diff if you have not classified other changes. Those two commands can affect more than just the files under review.

## 14. Considerations for special files and unsafe conversions

### Binary files

Binary files should not be normalized like text files. If Git misidentifies them or a text policy is applied incorrectly, it can corrupt their content. Use the -text or binary attribute for appropriate file types.

### Files with mixed line endings

Normalization can change all line endings in a file. Before staging, inspect the diff and check whether the editor automatically converts all lines to a single style. Do not assume lines that look identical share the same ending bytes.

### Trailing whitespace

CRLF contains a CR character before LF. Some tools display CR as ^M or count it as an end-of-line difference. The ignore-space-at-eol option helps with comparison, but you should not ignore whitespace by default in files where whitespace is meaningful.

### core.safecrlf

You can use core.safecrlf so Git warns or rejects certain potentially irreversible line-ending conversions:

~~~bash
git config --global core.safecrlf warn
~~~

The warn value tells Git to emit a warning when it detects a conversion that may not restore the original state. This option is a detection aid and does not replace .gitattributes or team policy.

### Do not edit blobs directly

You should not edit files in .git/objects with a text editor. If content needs normalization, do it in the working tree, configure attributes, stage with Git, and inspect the diff.

## 15. Common misconceptions

### Does Git always store files with LF?

No. Git can normalize text files to LF if attributes or configuration request it. Without an appropriate rule, a blob can preserve CRLF or other line endings.

### Does i/lf and w/crlf in git ls-files --eol mean the file is broken?

Not necessarily. This can be the expected state when the index is normalized to LF while the working tree is configured to use CRLF.

### Is setting core.autocrlf enough for the whole team?

No. core.autocrlf is a per-machine or per-repository setting and can differ between team members. .gitattributes helps record a shared policy in the repository.

### Does changing line endings change program logic?

Usually not, though Git can still record different bytes and create a large diff. For scripts or specialized data files, the wrong line endings can affect how tools read or execute them.

### Does .editorconfig replace .gitattributes?

No. EditorConfig guides editors; .gitattributes controls Git's file attributes and content processing.

### Should you run git add --renormalize . immediately when you see many modified files?

No. First determine the cause, choose a policy, protect in-progress work, and review the scope. Renormalize should only be run after the repository has the correct attributes.

## 16. Self-check

A Windows team member opens several Java files in an editor and saves them. The subsequent pull request reports 80 modified files, even though the author only changed logic in two files. Some files have the state i/lf w/crlf, the repository does not yet have .gitattributes, and the author's machine has core.autocrlf=true.

Answer the following:

1. Why can Git show mass line changes even when the text characters are identical?
2. What do i/lf and w/crlf indicate?
3. Which command checks the core.autocrlf setting and its configuration source?
4. Why should the team add .gitattributes?
5. After agreeing on attributes, which command re-normalizes tracked files?
6. How can you review the logic changes after ignoring end-of-line differences?
7. Why should a line-ending normalization commit be separated from a feature commit?

**Hint:** Git compares the bytes of blobs and files, so CRLF differs from LF even if the characters are the same. i/lf is the line ending in the index; w/crlf is the line ending in the working tree. Use git config --show-origin --get core.autocrlf to check the value and source. .gitattributes stores the shared policy for the repository. After verifying the attributes, run git add --renormalize . and then review git diff --cached and git diff --cached --ignore-space-at-eol. Separating commits makes reviews, blame, and bug investigations easier.

## Conclusion

LF and CRLF are two ways of representing line endings; if settings across editors, Git, and machines are inconsistent, a single file save can produce a large diff even when logic has not changed. Git can normalize content on check-in and convert line endings on checkout based on core.autocrlf, core.eol, and especially .gitattributes. When encountering mass changes, inspect i/ and w/ with git ls-files --eol, check attributes and configuration sources, and then normalize in a dedicated commit with git add --renormalize . once the policy is confirmed. Clear conventions help teams keep reviews clean and avoid unnecessary conflicts when working across multiple operating systems.
