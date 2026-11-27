# Impact of clean/smudge filters and `working-tree-encoding`

Git needs a consistent content representation to store in a repository, while files on a developer's machine sometimes need a different format. For instance, a tool may only read UTF-16LE files, a project may need to normalize data before committing, or Git LFS may need to replace large file contents with a small pointer in the repository and fetch the actual contents on checkout.

Git supports content transformation mechanisms via **clean filters**, **smudge filters**, and the **`working-tree-encoding`** attribute. They affect data flow across the working tree, index, and object database. When configured properly, the repository stores content in a canonical form while each working tree can still use the format required by tools on that machine. When misconfigured or missing a filter on a machine, data may be stored in the wrong format, diffs may appear continuously, or content may be transformed unexpectedly.

This lesson explains the transformation flow, how to configure and inspect it, its effects on `git add` and checkout, and the limitations to consider when multiple operating systems and Git versions collaborate on the same repository.

## 1. Where does Git transform content?

A Git-managed file can exist in three places with distinct roles:

- **Working tree:** the file opened and edited by developers and tools.
- **Index (staging area):** the content prepared for the next commit.
- **Object database:** blobs and Git objects saved by commits.

When adding a file, Git reads content from the working tree and converts it into the repository storage format before updating the index. When checking out or writing a file from a commit to the working tree, Git converts the repository-stored content into the format needed on the current machine.

```mermaid
flowchart LR
    W[Working tree\nContent on machine] -->|clean filter / encoding| I[Index]
    I -->|commit| B[Blob in repository]
    B -->|smudge filter / encoding| W2[Working tree after checkout]
```

The model above simplifies steps such as line-ending normalization and other attribute processing, while illustrating the essential transformation directions:

- **Clean:** working tree → canonical form in the index/repository.
- **Smudge:** canonical form in the repository → working tree.

Git does not require both byte representations to be identical. The goal is for transformed content to conform to the project's convention and be reproducibly reconstructed.

## 2. What are clean filters and smudge filters?

Clean and smudge are the two directions of a filter driver configured by a project. An attribute in `.gitattributes` binds a driver to a group of paths; Git configuration on the machine supplies the program performing the transformation.

Example in `.gitattributes`:

```gitattributes
*.data filter=normalize-data
```

The name `normalize-data` is the filter driver name. It is not yet an executable command. Each machine must configure the corresponding driver in Git config.

### 2.1. Clean filter

The clean filter runs when Git moves content from the working tree into the index, typically via `git add`. It transforms data into the canonical form that the repository stores.

For example, a project wants to strip an auto-generated timestamp at the end of a data file before committing. A clean filter can normalize the file so two machines generating equivalent data do not create unnecessary diffs.

```text
File on machine
    |
    v
clean filter
    |
    v
Canonical content added to index and commit
```

### 2.2. Smudge filter

The smudge filter runs in the opposite direction when Git writes content from the repository out to the working tree, such as when checking out a branch, switching branches, or restoring a file from a commit.

For example, a repository stores a template configuration file without machine-specific values. A smudge filter can generate the working-tree version suited to the local environment based on configured conventions.

```text
Blob in repository
    |
    v
smudge filter
    |
    v
File written to working tree
```

A smudge filter does not modify committed blobs. It transforms the data written out to the working tree.

### 2.3. How should clean and smudge work together?

For a normalizing filter, clean output should be stable and deterministic: identical valid input must yield identical canonical content. When canonical data is checked out and then passed back through clean, it should ideally produce the exact original canonical content.

This desired requirement can be expressed as:

```text
clean(smudge(blob)) = blob
```

This is a useful consistency check. Not every filter is a byte-for-byte inverse, yet a filter should be designed so a checkout → add round-trip does not produce spurious changes or lose data.

If a clean filter produces different output on every run—such as inserting the current timestamp—`git status` or the next `git add` may continuously report differences. If smudge creates content that clean cannot normalize back to its original form, Git can generate unwanted diffs.

## 3. Configuring a filter driver

### 3.1. Declaring the driver in `.gitattributes`

`.gitattributes` defines which paths use a filter and the driver name:

```gitattributes
*.data filter=normalize-data
```

The `filter=normalize-data` attribute applies the driver named `normalize-data` to paths matching `*.data` according to attribute pattern rules.

### 3.2. Configuring the command on a machine

The driver is defined in Git config, for example:

```ini
[filter "normalize-data"]
    clean = "python tools/normalize.py clean"
    smudge = "python tools/normalize.py smudge"
    required = true
```

This example assumes the project has a program `tools/normalize.py` accepting `clean` or `smudge` mode. This is an illustrative configuration; the actual command must match the language, path, and runtime environment on each machine.

Filter commands receive content via standard input and return transformed content via standard output. Diagnostic messages should be written to standard error, avoiding printing messages to standard output because Git will treat that output as file content.

Key meanings:

- `clean`: command converting working tree content into canonical form.
- `smudge`: command converting canonical content into working tree form.
- `required = true`: requires the filter to succeed; if missing or failing, Git reports an error instead of silently skipping the filter.

If `required` is not enabled, the filter is treated as optional. When the filter command is absent or fails to run, Git may skip transformation and use the content as-is. This can cause different machines to store different content despite sharing `.gitattributes`.

### 3.3. `.gitattributes` does not automatically install filter programs

A repository can commit `.gitattributes` and filter scripts, while the driver's executable command is configured in Git config on each machine. Cloning a repository does not guarantee every machine already has a working filter driver.

Therefore, onboarding procedures should specify:

- Which tools or runtimes need to be installed.
- How clean/smudge commands are configured.
- Which filter version is compatible with the repository.
- How to verify the filter is available and working properly.
- What happens if a machine lacks the filter.

Do not assume `.gitattributes` will automatically run a script just because that script sits in the repository. Separating attributes from command configuration lets users control their environment while preventing an attributes file from arbitrarily executing commands.

You can set local configuration via commands if the project provides a trusted script:

```bash
git config filter.normalize-data.clean "python tools/normalize.py clean"
git config filter.normalize-data.smudge "python tools/normalize.py smudge"
git config filter.normalize-data.required true
```

The commands above write configuration into `.git/config` of the current repository. Before configuring or running a filter from an unfamiliar project, read and understand the invoked program: filters run with the user's privileges and can read, write, or transmit data depending on the script's contents.

### 3.4. Process filters

Besides the `clean` and `smudge` command pair, Git supports process filters via `filter.<driver>.process`. A process filter is a longer-lived process that exchanges multiple conversion requests over Git's protocol, reducing process startup overhead when handling many files.

A driver using a process filter is typically chosen over launching a separate process for every clean or smudge invocation. Implementation must adhere to Git's process filter protocol; you cannot simply swap a plain clean command for a process filter without implementing that protocol.

## 4. Real-world example: Git LFS

Git LFS is a familiar example of using clean/smudge filters. Instead of storing large contents directly in the regular Git object database, Git LFS stores a small pointer file in the repository; the large content is stored in LFS storage.

A `.gitattributes` file may contain a rule like:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
```

When adding a `.psd` file, Git LFS's clean filter replaces the content in the repository with a pointer. On checkout, Git LFS's smudge/process filter fetches the actual content and writes it to the working tree if the data is available and the user has access permissions.

Result:

- The regular Git repository stores a small pointer.
- The user's working tree can hold the full binary file.
- Machines need Git LFS and access to the LFS store to retrieve the actual content.

If a machine does not have Git LFS installed or the filter is misconfigured, the user may see a pointer instead of the expected binary file, or Git may fail to perform the conversion required by the project. Therefore, Git LFS must be installed and verified on participating machines.

## 5. What is `working-tree-encoding`?

`working-tree-encoding` is a Git attribute used to declare the encoding of a file in the working tree. Git converts content from that encoding to UTF-8 when adding it to the repository and converts from UTF-8 back to the specified encoding when writing the file to the working tree.

For example, some Windows tools require PowerShell files in UTF-16LE with CRLF. You can declare:

```gitattributes
*.ps1 text working-tree-encoding=UTF-16LE eol=crlf
```

Meaning:

- `*.ps1`: applies to files with the `.ps1` extension matching the pattern.
- `text`: enables treating content as text and normalizing line endings per Git rules.
- `working-tree-encoding=UTF-16LE`: working tree uses UTF-16LE; content stored in the repository is converted to UTF-8.
- `eol=crlf`: on checkout, the working tree uses CRLF for these files.

Overview of data flow:

```text
Working tree: UTF-16LE + CRLF
        |
        | git add: convert encoding, normalize content
        v
Repository: UTF-8 with normalized line endings
        |
        | checkout: convert back to declared encoding and EOL
        v
Working tree: UTF-16LE + CRLF
```

As a result, machines can store the same text content in a standardized format inside the repository even when local tools require a different encoding.

### 5.1. Why does Git store UTF-8 in the repository?

UTF-8 is a well-suited storage format for sharing text content across operating systems and modern developer tools. If each machine commits the same text in different encodings, the repository can end up containing different blobs even though the content users see is identical.

`working-tree-encoding` separates the encoding needed by local tools from the repository's canonical encoding. Reviews, diffs, and content processing in the repository therefore stay much more consistent.

### 5.2. Distinguishing from `text` and `eol`

These three attributes are related but distinct:

| Attribute | Role |
|---|---|
| `text` | Specifies the file is treated as text and normalizes line endings when adding to the repository. |
| `eol=lf` or `eol=crlf` | Specifies the working tree line-ending style on checkout. |
| `working-tree-encoding=<encoding>` | Specifies the working tree encoding and converts to/from UTF-8 in the repository. |

Changing line endings alone does not solve encoding issues. Likewise, converting encoding does not necessarily specify the desired line endings. If a tool requires both a specific encoding and EOL, declare and verify both.

## 6. Limitations and risks of `working-tree-encoding`

### 6.1. All clients must support the attribute

Not every Git version or Git client supports `working-tree-encoding`. Older clients that do not understand this attribute may treat content as raw data and store the working tree's bytes verbatim. When that happens, one machine may commit UTF-16LE while another expects the repository to store UTF-8.

Before adopting this attribute in a project:

- Determine the minimum supported Git version.
- Check whether the team's Git GUIs, IDEs, and integrated tools support this attribute.
- Test cloning, checking out, editing, adding, and committing across representative environments.
- Clearly document version requirements in project documentation.

### 6.2. Encodings must be convertible and round-trip safely

Not every encoding has a lossless bidirectional conversion. Some encodings cannot represent every Unicode character or have multiple equivalent byte forms. If conversion drops characters, content after checkout may differ from the original.

Test with non-ASCII characters, Vietnamese diacritics, special characters, and BOM cases if tools use them. Do not test only with a file containing plain English letters.

### 6.3. Do not apply arbitrarily to binary files

`working-tree-encoding` is designed for text content with a defined encoding. Do not use it on images, archives, executables, or arbitrary binary files. Encoding conversion on binary data can corrupt the contents.

For binary files, you typically need a specialized filter or raw byte storage. Declare `-text` if you want to prevent Git from handling line endings as text for those paths.

### 6.4. Overhead and compatibility

Converting encodings and running filters can increase the duration of `git add`, checkout, switch, or file-write operations. External filters also depend on runtimes, scripts, permissions, and per-machine configuration.

Only use conversion mechanisms when there is an actual requirement. If all tools already support UTF-8, keeping UTF-8 in both the working tree and repository is usually simpler.

## 7. What do broken or misconfigured filters cause?

Suppose `.gitattributes` contains:

```gitattributes
*.data filter=normalize-data
```

However, one team member's machine has not configured `filter.normalize-data`. If the filter is optional, Git may skip the filter and use the content as-is. When that member runs `git add`, unnormalized data can enter the index.

If the project requires a mandatory filter, configure:

```ini
[filter "normalize-data"]
    clean = "python tools/normalize.py clean"
    smudge = "python tools/normalize.py smudge"
    required = true
```

When the filter cannot run, Git will report an error rather than silently continuing without conversion. This is usually the right choice when canonical content depends on the filter.

### 7.1. Unstable clean filters

If a clean filter yields different results across runs, you may observe:

- `git status` continuously reporting files as modified even when the user made no meaningful edits.
- Every `git add` producing a different blob.
- One machine committing cleanly while another machine checks out and commits, creating a huge diff.
- Content being lost or altered after multiple clean/smudge cycles.

Filters should have tests with representative data and round-trip verification. Avoid injecting timestamps, absolute paths, usernames, or machine-specific data into the canonical form unless those values are intended to be tracked.

### 7.2. Smudge filters depending on networks or external services

Some filters, such as Git LFS, require accessing external services on checkout. If the network drops, authentication expires, or an object is missing on the server, checkout may fail to retrieve the actual contents.

When errors occur, preserve the error messages, check filter configuration, and verify service connectivity. Do not overwrite pointers or canonical content with placeholder files of unknown origin.

## 8. Inspecting attributes and filter configuration

### 8.1. Viewing effective attributes for a path

```bash
git check-attr --all -- path/to/file.data
```

Or inspect only the relevant attributes:

```bash
git check-attr filter text eol working-tree-encoding -- path/to/file.data
```

This command reveals which attributes the path actually receives from attributes files and related configuration.

### 8.2. Viewing filter configuration on a machine

```bash
git config --show-origin --get-regexp '^filter\.'
```

The output displays filter settings along with their configuration sources, helping identify machines missing clean/smudge commands or inheriting unexpected settings from a global config file.

Do not blindly share configuration output if commands contain tokens, passwords, or internal details.

### 8.3. Viewing canonical content in the repository

For a committed file:

```bash
git cat-file -p HEAD:path/to/file.ps1
```

This command displays the blob content stored in the commit—the canonical form Git manages. If the file uses `working-tree-encoding=UTF-16LE`, the blob content will generally be converted UTF-8 rather than the working tree's UTF-16LE bytes.

To inspect differences between the working tree and the index:

```bash
git diff -- path/to/file.ps1
git diff --cached -- path/to/file.ps1
```

If a filter behaves inconsistently, these commands help pinpoint which step introduces changes.

## 9. Changing attributes on a repository with existing data

When adding `filter` or `working-tree-encoding` to `.gitattributes`, already-committed blobs are not automatically rewritten. Git applies conversions only when processing content through the corresponding operations.

If you want to re-normalize tracked files under the new attributes, you can run:

```bash
git add --renormalize .
```

This command re-applies the clean process to tracked files within the specified scope and updates the index. Before committing:

```bash
git status --short
git diff --cached --stat
git diff --cached
```

Inspect the diff carefully to ensure changes reflect only the intended conversions. If the repository is large or attributes apply only to a subset of files, scope the path instead of normalizing everything.

Do not run renormalize across the whole repository before filters are installed and thoroughly tested in all environments. If a filter is missing, depending on configuration, Git may fail to convert content as expected.

## 10. Workflow for introducing filters or encodings into a project

When a team decides to adopt clean/smudge filters or `working-tree-encoding`, roll it out in a controlled manner:

1. **Define requirements:** which files need conversion, what canonical form is stored in the repository, and what working-tree format tools need.
2. **Choose the mechanism:** use `working-tree-encoding` for text encoding conversion; use filter drivers for custom content transformations; use Git LFS for large content suited to LFS.
3. **Declare `.gitattributes`:** apply attributes only to exact patterns, avoiding accidental impact on binary files or other source code.
4. **Install local configuration:** ensure every machine has the necessary driver, script, runtime, and access permissions.
5. **Configure explicit failures:** if canonical content relies on a filter, consider `required = true` to prevent machines lacking the filter from committing unnormalized data.
6. **Test the conversion round-trip:** check out, edit, add, commit, clone, and check out again; compare contents and diffs.
7. **Test across environments:** verify on Windows, macOS, Linux, IDEs, and the minimum Git version supported by the team.
8. **Normalize existing data:** if needed, run `git add --renormalize` on the verified scope and review the entire diff.
9. **Document:** clearly record filter installation, configuration, verification steps, and troubleshooting for new members.

## 11. Comparison table of mechanisms

| Mechanism | What does it convert? | Where is it configured? | Best suited for |
|---|---|---|---|
| Clean filter | Working tree → canonical content | `.gitattributes` selects driver; Git config provides command | Normalizing or transforming content before storage |
| Smudge filter | Canonical content → working tree | `.gitattributes` selects driver; Git config provides command | Producing machine-usable file formats on checkout |
| Process filter | Clean/smudge via a long-lived process | `filter.<driver>.process` and `.gitattributes` | Filters handling many files that need lower startup overhead |
| `working-tree-encoding` | Working tree encoding ↔ UTF-8 in repository | `.gitattributes` | Tools requiring a specific text encoding |
| `text` / `eol` | Normalizing and choosing line endings | `.gitattributes` | LF/CRLF differences across operating systems |

## 12. Takeaways

- Clean converts content from the working tree to canonical form when Git updates the index/repository.
- Smudge converts canonical content to the form needed in the working tree when Git writes files out.
- `.gitattributes` selects drivers by path; Git config on each machine supplies the filter commands.
- `required = true` makes Git fail if a mandatory filter is unavailable, avoiding silently storing unconverted content.
- Clean filters must be deterministic; the `clean(smudge(blob))` round-trip should return equivalent canonical content.
- `working-tree-encoding` converts working tree encoding to UTF-8 in the repository and converts back on checkout.
- All clients must support the encoding attribute and have corresponding filters installed; otherwise, machines may store content in inconsistent formats.
- `text`/`eol` handles line endings while `working-tree-encoding` handles encoding; both aspects must be verified separately.
- `git check-attr`, `git config --show-origin`, `git cat-file`, and `git diff` help diagnose the transformation flow.
- When changing attributes for tracked files, consider `git add --renormalize` and carefully review diffs before committing.

Before adopting filters in a project, clearly define both the data format stored in the repository and the format required in the working tree. Then test both machines with the filter and machines without it, because a configuration that only works on the author's machine can still break repository consistency once shared.
