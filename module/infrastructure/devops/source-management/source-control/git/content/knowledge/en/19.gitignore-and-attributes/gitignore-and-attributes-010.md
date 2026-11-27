# export-ignore, export-subst Attributes and Archive Export Contents

Git does more than store source code history. Git can also produce an archive export from a commit or tag using the **git archive** command. This export is often used as a downloadable source tarball, as input to a packaging workflow, or provided to users who do not need to clone the repository.

The **.gitattributes** file lets you control archive contents using two important attributes:

- **export-ignore:** excludes specified paths from the archive.
- **export-subst:** replaces **$Format:...$** placeholders inside file contents with information from the commit being exported.

These two attributes affect only how Git builds the export. They do not delete files from the repository, do not alter the working tree, and do not replace security controls or build artifact workflows.

## 1. How Does git archive Create an Export?

git archive builds an archive from a tree-ish, typically a commit, branch, or tag. The contents are taken from the snapshot stored in Git at that point.

For example, create a tar file from tag v1.2.0:

~~~sh
git archive --format=tar --prefix=app-v1.2.0/ -o app-v1.2.0.tar v1.2.0
~~~

Create a ZIP file:

~~~sh
git archive --format=zip --prefix=app-v1.2.0/ -o app-v1.2.0.zip v1.2.0
~~~

Where:

- --format=tar or --format=zip selects the archive format.
- --prefix=app-v1.2.0/ places files inside a root directory with a consistent name.
- -o specifies the output file.
- v1.2.0 is the tag used as the content reference.

Without specifying --prefix, paths inside the archive start from the root directory of the exported tree. Using a specific tag ensures every archive rebuild pulls the exact same source snapshot, provided that tag remains unchanged.

git archive exports only the contents stored in the commit's tree. Untracked files or uncommitted changes in the working tree do not automatically appear in the archive. An archive is also not a full clone: it does not carry the full commit history or repository management metadata such as the .git directory.

## 2. .gitattributes Controls Archive Contents

.gitattributes is a per-path attribute configuration file in the repository. Each line typically has the form:

~~~text
<pattern> <attribute> <attribute> ...
~~~

Example:

~~~gitattributes
/.gitattributes export-ignore
/.gitignore export-ignore
/tests/** export-ignore
/docs/internal/** export-ignore
VERSION export-subst
~~~

In this example:

- /.gitattributes export-ignore excludes the root .gitattributes file from the archive.
- /.gitignore export-ignore excludes the root .gitignore file from the archive.
- /tests/** export-ignore excludes files beneath the tests directory from the archive.
- /docs/internal/** export-ignore excludes files beneath docs/internal from the archive.
- VERSION export-subst enables placeholder substitution in the VERSION file when creating an archive.

The lines above are examples of a packaging policy. Not every project should exclude documentation or tests; set export-ignore only for content that recipients of the export package truly do not need.

### 2.1. Pattern Scope

Patterns in .gitattributes are matched against paths relative to the directory containing that .gitattributes file.

- Patterns containing / are matched relative to that path.
- Patterns without / are usually matched against path component names at levels below.
- A leading / anchors the path to the directory containing .gitattributes.
- Wildcards such as *, ? and ** syntax can be used to describe multiple paths.

For example, .gitattributes in the root directory:

~~~gitattributes
/LICENSE export-ignore
/docs/drafts/** export-ignore
*.tmp export-ignore
~~~

/LICENSE targets only the LICENSE file at the root. *.tmp can apply to files ending in .tmp across multiple subdirectories. If .gitattributes is placed inside a subdirectory, patterns in that file are evaluated relative to that subdirectory.

.gitattributes patterns have some differences from .gitignore. Do not use negated lines starting with ! to invert a pattern. The ! symbol in attribute value syntax has a different meaning: it sets the attribute to the unspecified state.

### 2.2. Attributes Can Be Set, Unset, or Left Unspecified

Git supports these attribute assignment forms:

| Syntax | Meaning |
|---|---|
| attr | Set the attribute |
| -attr | Unset the attribute |
| !attr | Set the attribute to the unspecified state |
| attr=value | Assign a value to the attribute |

For the two attributes covered here, typical usage is setting export-ignore or export-subst:

~~~gitattributes
/tests/** export-ignore
VERSION export-subst
~~~

If a broad rule sets an attribute yet a more specific rule needs to remove it, you can use:

~~~gitattributes
*.md export-ignore
/README.md -export-ignore
~~~

In that case, README at the root does not carry the export-ignore attribute, while other Markdown files can still be excluded under the broad rule. Verify with git check-attr rather than guessing pattern results.

### 2.3. Precedence Order of Attributes Files

Git can read attributes from multiple locations. Precedence order from highest to lowest is typically:

1. $GIT_DIR/info/attributes of the current repository.
2. .gitattributes files in the directory containing the path and parent directories; files closer to the path have higher precedence.
3. Global attributes file configured via core.attributesFile.
4. System-level attributes file.

Within the same file, a matching rule on a later line can override the value of the same attribute from an earlier line. Different attributes remain processed independently.

When archiving from a commit or tag, Git uses the .gitattributes files belonging to the exported snapshot. Therefore, an old tag can have different export rules than the current branch. The --worktree-attributes option instructs Git to use .gitattributes files in the working tree instead of the version in the exported tree. This option is useful when testing local rules, but if you want reproducible exports from a tag, commit the rules into the release snapshot itself.

## 3. export-ignore: Excluding Files from the Archive

export-ignore tells Git that the marked path should not appear in archives created by git archive.

A project may want to keep tests, internal documentation, development configs, or contributor support files in the repository while omitting them from source packages meant for end users.

Example .gitattributes:

~~~gitattributes
/tests/** export-ignore
/docs/internal/** export-ignore
/.github/** export-ignore
~~~

After committing the .gitattributes file, create the archive:

~~~sh
git archive --format=tar --prefix=app-v1.2.0/ -o app-v1.2.0.tar v1.2.0
~~~

Paths matching export-ignore will be absent from the archive. They still exist in the repository, still appear when cloning, and remain accessible through Git history.

### 3.1. Contents Commonly Considered for Exclusion from Exports

Depending on the source package's purpose, consider:

- Tests intended only for internal development, if recipients do not need to run them.
- Internal documentation not meant for package users.
- CI configurations or contributor helper scripts unnecessary in the distribution package.
- Sample files, notes, or development data meant only for the team.

Do not mechanically exclude every tests, docs, or .github directory. Some libraries need to distribute tests so downstream packages can self-verify; some products need offline documentation or build scripts so users can package them themselves.

### 3.2. export-ignore Is Not a Secret-Protection Mechanism

This is an important limitation. export-ignore controls only archives created with git archive. It does not:

- Delete files from Git.
- Prevent anyone with repository clone access from reading the file.
- Remove sensitive content from older commits.
- Prevent files from appearing in pull requests, forks, or repository copies.
- Replace access controls, secret managers, or secret-exposure incident procedures.

Do not commit passwords, tokens, private keys, or sensitive data expecting export-ignore to hide them. If a secret has entered Git history, revoke or rotate the secret and clean history per the project's security procedures.

## 4. export-subst: Substituting Placeholders on Export

export-subst allows Git to replace $Format:...$ placeholder strings inside a file when running git archive.

This attribute is useful when a source package needs version or commit identification metadata without modifying files in the working tree before creating the archive.

### 4.1. Declaring the Attribute

In .gitattributes, mark the file for substitution:

~~~gitattributes
VERSION export-subst
~~~

In the VERSION file, place the placeholders:

~~~text
Version: $Format:%H$
Short commit: $Format:%h$
Subject: $Format:%s$
~~~

Placeholders use the pretty formats supported by Git. For example:

- %H: full commit SHA.
- %h: abbreviated SHA.
- %s: commit subject.
- %an: author name.

Include only necessary information in exported files. Avoid putting personal information or internal metadata into release packages if recipients do not need it.

### 4.2. Creating an Archive to Substitute Placeholders

Once .gitattributes and VERSION are committed, create an archive from a tag:

~~~sh
git archive --format=tar --prefix=app-v1.2.0/ -o app-v1.2.0.tar v1.2.0
~~~

Inside the archive, the contents of VERSION will have placeholders replaced with information from the commit to which tag v1.2.0 resolves. The VERSION file in the repository is untouched; when checking out the tag or viewing the file in the working tree, placeholders remain intact.

You can inspect the exported file content with tar:

~~~sh
git archive --format=tar v1.2.0 | tar -xOf - VERSION
~~~

The output will display the substituted values. If a prefix was used when creating the archive, the path passed to tar -xOf must include that prefix.

### 4.3. Substitution Happens Only When the Attribute Is Present

Simply writing $Format:%H$ in a file is not enough. The file must carry the export-subst attribute at the snapshot being archived.

If the .gitattributes file at the tag lacks this rule, Git leaves placeholders untouched in the archive. That is why you should check both file contents and attributes at the exact tag being released.

export-subst applies only during git archive. It does not substitute content when:

- Checking out a branch or tag.
- Cloning a repository.
- Viewing a file with git show.
- Creating a normal commit.
- Running the application directly from the working tree.

If the application needs to read version info at runtime in development, provide a separate build metadata generation mechanism; do not assume placeholders are substituted outside archives.

## 5. Combining export-ignore and export-subst

Both attributes can be used together in a project:

~~~gitattributes
/.gitattributes export-ignore
/.gitignore export-ignore
/tests/** export-ignore
/docs/internal/** export-ignore
VERSION export-subst
~~~

This policy produces a distributable archive:

- Omits Git configuration files and unnecessary development contents.
- Excludes tests and internal docs according to project policy.
- Keeps the VERSION file while replacing placeholders with commit metadata.

Remember that .gitattributes is used to govern the archive, so if you mark it itself with export-ignore, the rules are still read by Git before excluding the file from the output. The absence of .gitattributes inside the archive does not undo the rules used to build that archive.

## 6. Practical Example from Configuration to Archive

Suppose the store-service project wants to release source package v2.3.0. The team wants to keep tests and internal docs in the repository while omitting them from the distribution archive, and also record the commit SHA in the VERSION file.

### Step 1: Create the .gitattributes file

~~~gitattributes
/.gitattributes export-ignore
/.gitignore export-ignore
/tests/** export-ignore
/docs/internal/** export-ignore
VERSION export-subst
~~~

### Step 2: Create the VERSION file

~~~text
Release: $Format:%h$
Commit: $Format:%H$
Subject: $Format:%s$
~~~

### Step 3: Commit the rules and version file

~~~sh
git add .gitattributes VERSION
git commit -m "Configure source archive metadata"
~~~

### Step 4: Integrate and create a release tag

After changes are reviewed, tested, and integrated into the release branch, create an annotated tag:

~~~sh
git tag -a v2.3.0 -m "Release store-service 2.3.0"
git show --no-patch --decorate v2.3.0
git rev-parse "v2.3.0^{commit}"
~~~

### Step 5: Create the archive

~~~sh
git archive --format=tar --prefix=store-service-2.3.0/ -o store-service-2.3.0.tar v2.3.0
git archive --format=zip --prefix=store-service-2.3.0/ -o store-service-2.3.0.zip v2.3.0
~~~

### Step 6: Inspect contents

List files in the tar:

~~~sh
tar -tf store-service-2.3.0.tar
~~~

Check that VERSION was substituted:

~~~sh
tar -xOf store-service-2.3.0.tar store-service-2.3.0/VERSION
~~~

Verify tests and internal docs were excluded from the archive by reviewing the file listing:

~~~sh
tar -tf store-service-2.3.0.tar
~~~

Cross-check the listing against the agreed packaging policy. Do not inspect only the VERSION file; confirm both the paths to keep and the paths to exclude are accurate.

### Step 7: Record release metadata

Record:

- Tag v2.3.0.
- The commit SHA the tag points to.
- Archive filenames and checksums.
- Archive content verification results.
- Release notes and any other artifacts.

An archive built from a tag lets the team reproduce contents from the same Git snapshot. To ensure artifacts remain verifiable, the release pipeline should record checksums and preserve the packaging environment or tooling details needed.

## 7. Checking Attributes Before Releasing

When an archive is missing files or placeholders remain unexpanded, check attributes first.

### 7.1. Using git check-attr

Check attributes on files in the working tree:

~~~sh
git check-attr export-ignore export-subst -- tests/example.test.ts VERSION
~~~

The output shows whether each attribute is set, unset, unspecified, or has a specific value. For example, VERSION should have export-subst: set; a test file configured for archive exclusion should have export-ignore: set.

You can view all attributes applied to a path:

~~~sh
git check-attr --all -- VERSION
~~~

If you need to inspect .gitattributes contents at a specific tag, view the file from that tag:

~~~sh
git show v2.3.0:.gitattributes
~~~

git check-attr checks against the current context by default. When you need to verify the exact archive of an older tag, build the archive from that tag and verify the output directly; do not infer solely from .gitattributes currently in the working tree.

### 7.2. Using --worktree-attributes for Local Testing

By default, Git uses attributes in the tree being exported. If you just edited .gitattributes in the working tree without committing and want to test local rules, you can run:

~~~sh
git archive --worktree-attributes --format=tar HEAD
~~~

The output here may differ from an archive built from a tag or remote commit. Do not use this option for releases that must be reproducible from a tag if the rules have not yet been committed to that tag.

### 7.3. Comparing the Archive Against the Source Snapshot

When inspecting the package, confirm:

- Required application files are present in the archive.
- Files marked export-ignore are absent.
- Files with export-subst contain accurate commit information.
- No temporary files, personal data, or dev-machine configs were included.
- The archive has the prefix and directory structure expected by recipients.

If a needed file is found missing, fix the pattern and recreate the release commit/tag per project workflow. For already-published tags, prefer a new version to preserve consistency of the older milestone.

## 8. Limitations of Archive Exports

git archive is convenient for creating source archives, but it is not a general-purpose packaging tool.

**Does not contain Git history.** The archive holds only a snapshot of the selected tree. Recipients cannot use that archive as a full clone to view all commits, branches, or tags.

**Does not include uncommitted changes.** Untracked files or uncommitted local edits are not present in the tree of the tag/commit.

**Does not automatically fetch submodule contents.** The parent repository stores a gitlink pointing to the submodule commit. An archive of the parent repository does not automatically package nested repositories. If the product needs submodule contents, the build workflow must fetch and package them separately.

**Does not turn source into a runnable artifact.** The archive does not install dependencies, compile, bundle frontends, build containers, or sign packages. Those steps belong to the build pipeline.

**Does not protect secrets.** export-ignore only hides paths from the archive. Anyone with read access to the repository can still retrieve the content from Git.

**Does not guarantee identical output if inputs change.** Moved tags, different attributes, or different packaging tools can yield different archives. Keep tags stable, and record commit SHAs and checksums.

## 9. Distinguishing .gitignore from export-ignore

The two names belong to two different mechanisms:

| Criterion | .gitignore | export-ignore |
|---|---|---|
| Where configured | .gitignore file | Attribute in .gitattributes |
| Purpose | Ignore untracked files when Git checks status/add | Exclude paths from git archive exports |
| Effect on tracked files | Does not remove tracked files from index | Does not delete tracked files from repository |
| Effect on clones | Does not prevent committed files from being cloned | Does not prevent files from being cloned |
| Effect on archives | Not an archive filtering mechanism | Yes |

For example, adding build/ to .gitignore tells Git to ignore untracked build files. If a file inside build/ was already committed, .gitignore does not delete it from history. Similarly, export-ignore can exclude tracked files from an archive while keeping the files intact in the repository.

## 10. Common Errors

**Placeholders remain unexpanded in the archive.** Check whether the file has export-subst in .gitattributes at the tag being exported. Confirm you are using git archive and not merely opening the file in the working tree.

**File still appears despite declaring export-ignore.** Check whether the pattern matches the actual path, whether .gitattributes was committed into the tag, and whether a higher-precedence attributes rule overrides it.

**Archive from an old tag yields different results than the current branch.** This can be expected because Git uses .gitattributes at the tag's snapshot. Check git show <tag>:.gitattributes.

**Misusing --worktree-attributes.** This option takes rules from the working tree, which can prevent archives from being reproducible from commits/tags. Use only when intentionally testing.

**Thinking export-ignore hides secrets.** Files remain in Git and history. Revoke secrets and clean the repository according to security workflows.

**Excluding too much content from the package.** Recipients may need tests, docs, licenses, or build scripts. Validate the archive against actual distribution requirements before releasing.

**Forgetting submodules.** Parent repository archives do not automatically bundle submodule contents. A separate step is needed to fetch the exact commit of each submodule if the package requires them.

## 11. Checklist Before Publishing a Source Archive

**Configuration**

- [ ] Clearly identified which files to keep and which to exclude from the archive.
- [ ] export-ignore patterns match the exact paths.
- [ ] Files needing placeholder expansion have export-subst.
- [ ] .gitattributes has been committed into the release snapshot.
- [ ] export-ignore is not relied upon as a security mechanism.

**Creating the archive**

- [ ] Using a specific commit or tag as input.
- [ ] Archive prefix and format follow conventions.
- [ ] Not using --worktree-attributes outside designated testing.
- [ ] Submodule contents handled if required by the product.

**Inspecting output**

- [ ] Listed archive contents.
- [ ] Required files are present.
- [ ] Excluded files are absent.
- [ ] Placeholders are substituted with accurate info.
- [ ] Directory structure and archive filename are correct.
- [ ] Recorded commit SHA and archive checksum.

## 12. Conclusion

export-ignore and export-subst are two attributes in .gitattributes that control source archives generated by git archive. export-ignore excludes paths from the archive; export-subst replaces $Format:...$ placeholders with metadata from the exported commit.

Configure these attributes in .gitattributes and commit them to the right release milestone. Then create the archive from a specific tag or commit, inspect the file list and substituted contents, and record the commit SHA alongside checksums. These attributes standardize source packages, while security, artifact building, and release publishing still require their own dedicated workflows.
