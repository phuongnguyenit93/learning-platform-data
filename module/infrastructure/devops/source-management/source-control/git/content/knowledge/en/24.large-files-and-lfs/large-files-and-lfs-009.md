# Choosing Between LFS, an Artifact Registry, or Excluding Files from Version Control

Not every large file belongs directly in Git. Source code, configuration, and documentation need detailed change history; whereas build files, installers, backups, or generated data can rapidly inflate repository size without delivering commensurate value from versioning every binary revision in Git. For binary assets that must remain tied to each commit, Git LFS is an option. For build outputs and release packages, an artifact registry is usually more appropriate. For temporary files or reproducible data, excluding them from version control with `.gitignore` may be the right decision.

The choice should depend on a file's lifecycle and how the team uses it, not on size alone. A 20 MB file might be a critical design document requiring versioning; a 2 GB build directory might simply be reproducible from source code. This lesson presents selection criteria across standard Git, Git LFS, artifact registries, and excluding files from Git, along with a safe transition workflow.

## 1. Why Must You Choose How to Store Large Files?

Git is optimized for storing and comparing content versions. For text files, Git can display line-by-line diffs and generally compresses well. For large binary files such as videos, high-resolution images, 3D models, scientific datasets, or installers, Git typically cannot produce meaningful diffs as it does for source code. Each time the file changes significantly, the repository may have to store another large blob.

Common consequences include:

- The repository grows over time, even after large files are deleted from the current working tree.
- Clones and fetches can become slow because users must download substantial historical data unneeded for their current work.
- Local copies, CI runners, and mirrors consume extra storage space.
- Pull request reviews become harder to understand when changes consist of unreadable binary diffs.
- Sharing and backing up the repository becomes more expensive.

Git LFS and artifact registries solve different needs. `.gitignore` only prevents untracked files from entering Git; it does not automatically move already-committed data out of the repository.

## 2. Four Main Storage Options

| Storage Approach | Best Suited For | Versioning Model | Impact on Git Repository |
| --- | --- | --- | --- |
| Standard Git | Source code, configs, text docs, small files needing diffs | Commits file content directly | Content is stored in the Git object database and history |
| Git LFS | Large binaries that must stay tied to exact commits or branches | Git stores pointers; file content lives on an LFS server | Git clones mainly fetch pointers; LFS files download on demand/config |
| Artifact registry | Build packages, release binaries, internal dependencies, container images, CI outputs | Managed by version, coordinates, tag, digest, or build ID | Git stores only source code, manifests, or artifact references |
| Excluded from version control | Caches, logs, build directories, temp files, reproducible local data | Not versioned in Git; regenerated or stored elsewhere | Adds no new blobs to Git history |

A single project can combine multiple approaches. For example, `.java` files live directly in Git; `.psd` design files are managed via LFS; release `.jar` files go into an artifact registry; and `build/` directories and local logs are excluded from Git.

## 3. Decision Tree for Choosing Storage

Before adding a large file, answer in order:

1. Is the file a temporary output, cache, or reproducible from source code and configuration? If yes, exclude it from Git.
2. Is the file a build package, release binary, container image, or pipeline output distributed by version? If yes, prefer an artifact registry.
3. Must the file appear as part of the commit snapshot so everyone checks out the exact matching version alongside source code? If yes, consider Git LFS.
4. Is the file small, primarily text-based, and in need of direct diffs/reviews? If yes, store it in standard Git.
5. If it is large data changing continuously or needing querying, dataset-level sharing, and independent lifecycle management, consider dedicated data storage or object storage paired with manifests and checksums.

There is no single fixed size threshold for every project. Consider change frequency, number of versions to retain, number of consumers downloading it, reproducibility, backup policies, quotas, and server capabilities.

## 4. When Should You Use Git LFS?

Git LFS (Large File Storage) fits well when a large file is part of the product or project content and must be linked to specific commits. Examples include:

- Graphic design files, source images, or audio/video assets edited across multiple revisions.
- 3D models, game assets, CAD drawings, or binary data that must stay synced across branches.
- Large test fixtures whose results must be reproducible against the exact source commit.
- Binary documents that the team needs to check out with the repository and manage alongside Git history.

LFS fits when a team wants to retain Git's branch, commit, merge, and tag experience for large files. When checking out a commit, Git identifies the file version via the pointer stored in that commit; Git LFS downloads the matching content from the LFS server.

### What Does LFS Store in Git?

When a file is tracked with LFS, Git typically stores a small text pointer file in place of the full binary content. The pointer contains the specification version, content identifier (OID, typically SHA-256), and file size.

Illustrative pointer example:

```text
version https://git-lfs.github.com/spec/v1
oid sha256:4cac19622fc3ada9c0fdeadb33f88f367b541f38b89102a3f1261f6c5b4a4f2f
size 84977953
```

The OID and size above are illustrative examples. The pointer blob lives in Git history; the actual content is stored separately on the LFS service. On checkout, Git LFS uses the pointer to fetch the exact object. Thus, a commit still pins the exact large file version without embedding the entire binary inside Git's object database.

LFS does not make storage costs vanish. The LFS server still stores the objects, and users and CI still download content when needed. Storage providers may apply independent capacity, bandwidth, quota, authentication, and retention policies.

## 5. Installing and Tracking Files with Git LFS

Git LFS must be installed on workstations, and the remote Git service must support LFS.

### Step 1: Install Git LFS

After installing Git LFS for your OS, verify:

```bash
git lfs version
```

Initialize LFS integration for the current account:

```bash
git lfs install
```

This configures the hooks required for Git LFS to work with Git. If you only want to configure the current repository, you can use:

```bash
git lfs install --local
```

### Step 2: Choose Patterns to Track

For example, to manage Photoshop design files and videos with LFS:

```bash
git lfs track "*.psd"
git lfs track "*.mp4"
```

These commands update `.gitattributes` so matching files are handled by LFS. Inspect the attributes file:

```bash
git diff -- .gitattributes
```

Example contents:

```gitattributes
*.psd filter=lfs diff=lfs merge=lfs -text
*.mp4 filter=lfs diff=lfs merge=lfs -text
```

Commit `.gitattributes` alongside changes adding LFS files so teammates and CI receive the same rules. Patterns can be scoped to directories, such as `assets/**/*.psd`; verify actual Git attributes rules for your project paths.

### Step 3: Add and Commit Files

```bash
git add .gitattributes
git add assets/design/mockup.psd
git status --short
git commit -m "Add design assets with Git LFS"
```

When Git stages the file, the LFS filter generates a pointer in the index. The binary content is transferred to LFS storage on push via the LFS workflow.

### Step 4: Verify Files Managed by LFS

```bash
git lfs ls-files
git lfs status
git show HEAD:assets/design/mockup.psd
```

`git lfs ls-files` lists LFS files in the current revision; `git lfs status` shows LFS file status in the working tree and index. `git show` on an LFS file typically outputs the pointer stored in Git rather than the full binary.

### Step 5: Push and Download LFS Content

```bash
git push origin feature/design-assets
```

On push, Git LFS uploads required objects to the LFS server and Git pushes the pointer commits to the remote. If the server lacks LFS support, authentication fails, or quotas are exhausted, the operation can fail even though pointer commits already exist locally.

When cloning the repository, users need Git LFS installed to automatically download matching content under the default smudge configuration. If cloned while skipping LFS downloads, the working tree may hold only pointers. You can pull content later:

```bash
git lfs pull
```

`git lfs pull` fetches LFS objects needed for the current checkout and updates files in the working tree. In CI environments, ensure Git LFS is installed and authentication is configured before checkout or LFS pull steps.

## 6. Benefits and Limitations of Git LFS

**Benefits:**

- Git history stores small pointers, reducing large binary blobs in the main repository.
- Large files remain linked to commits, branches, and tags.
- Team members can download exact asset versions on checkout.
- Patterns in `.gitattributes` allow selecting specific files.

**Limitations to consider:**

- Requires Git LFS installed on developer machines and CI/CD environments.
- The remote must support LFS and provide suitable endpoints, access permissions, storage capacity, and bandwidth.
- Initial clones or checkouts may still transfer large volumes of data if many LFS files exist.
- Git diff cannot review binary content like source code; teams still need preview tools or dedicated review procedures.
- LFS objects require backup and retention independent from the Git object database.
- Deleting a pointer in a new commit does not automatically reclaim the LFS object on the server; cleanup depends on service storage policies.

LFS does not replace an artifact registry when the goal is distributing versioned packages with dependency metadata, access controls, retention, or release workflows. Nor is it a place to store secrets such as tokens, private keys, or credentials.

## 7. When Should You Use an Artifact Registry?

An artifact registry suits files produced by builds, tests, packaging, or releases, especially when multiple systems retrieve them by version. Examples include:

- JAR, WAR, ZIP, installers, executable binaries.
- Internal packages such as Maven, npm, NuGet, or equivalents.
- Container images identified by tags and digests.
- Test reports, coverage reports, SBOMs, build logs, or deployment bundles.
- Datasets, trained models, or large assets generated by pipelines.

### Why Do Artifacts Not Belong in Git?

Artifacts can normally be reproduced from source code, locked dependencies, and build configuration. Every build can produce a new binary; committing every binary into Git bloats history without helping review logic. Artifact registries manage them by version or build ID, enabling consumers to fetch exact packages without cloning full Git history.

A typical workflow:

```text
Git commit / tag
       |
       v
CI checks out source and dependencies
       |
       v
Build + test + package
       |
       v
Publish artifact with version/build ID
       |
       v
Deploy / downstream project downloads artifact
```

Inside Git, store the information needed to reproduce or retrieve artifacts, such as:

- Build configuration files and dependency lockfiles.
- Application version, build ID, or release tag.
- Manifests describing generated artifacts.
- Digests/checksums to verify downloaded content.
- Package paths or coordinates in the artifact registry.

Avoid recording only a URL pointing to `latest`, because the content behind `latest` can change. Use immutable versions or digests to guarantee reproducible builds and deployments.

### Example Manifest Referencing an Artifact

```yaml
application: payment-service
source_commit: 8a21d5c4
version: 2.4.0
artifact:
  repository: releases
  name: payment-service-2.4.0.jar
  sha256: 2a7f...example-digest...
```

This is an illustrative structure; field names and authentication depend on your organization's tooling. Never place tokens or credentials inside manifests. Pipelines should fetch credentials from a secret manager or secure CI mechanism.

## 8. When Should Files Be Excluded from Version Control?

Files should be excluded from Git when they are not shared source inputs requiring history and can be regenerated or stored elsewhere more appropriately. Examples:

- Build directories: `build/`, `dist/`, `target/` when automatically generated.
- Caches: local `.gradle/`, `.m2/`, `node_modules/`, compiler caches.
- Logs, temporary files, crash dumps, and editor-generated files.
- Personal configuration files, environment files containing private data or secrets.
- Large test data files regenerated from fixtures or pipelines.
- Local backups, temporary exports, and downloaded files.

### Using `.gitignore`

Example:

```gitignore
# Build outputs
build/
target/
dist/

# Dependency/cache
node_modules/
.gradle/

# Logs and temporary files
*.log
*.tmp
*.swp

# Local environment and secrets
.env
.env.*.local
*.pem
*.key

# Local IDE settings
.idea/
.vscode/
```

This is only an example. Some IDE config files or `.env.example` may need to be committed to share template settings; distinguish secret-free templates from local files containing private data. Do not ignore an overly broad pattern if the project needs to track certain files of that kind.

### `.gitignore` Does Not Untrack Already-Committed Files

If a file is already tracked by Git, adding a pattern to `.gitignore` does not stop Git from tracking it. To keep the file in the working tree while removing it from the index:

```bash
git rm --cached path/to/large-generated-file.zip
```

Then commit the untracking change:

```bash
git add .gitignore
git commit -m "Stop tracking generated archive"
```

The file remains on the current machine; fresh clones will not receive it from the new commit. If users or pipelines still need the file, store it in an artifact registry or appropriate shared location and update download/generation instructions.

Note: the new commit only removes the file from the current version. Earlier commits still retain the large blob in history. Therefore, the repository may remain large until history is rewritten and older copies are cleaned up.

## 9. Comparing LFS, Artifacts, and Ignore by Scenario

| Scenario | Typically Suitable Option | Reason |
| --- | --- | --- |
| Photoshop file edited frequently and checked out per branch | Git LFS | Each commit references the exact asset version |
| Raw video files used in a content project | Git LFS or versioned object storage | Choose LFS if commit linkage is needed; object storage for independent data lifecycle |
| JAR built by CI for each release | Artifact registry | Versioned packages, metadata, retention, and distribution mechanisms |
| Container images | Container registry | Stores layers, tags, digests, and pull/push permissions |
| `build/` or `target/` directory | `.gitignore` | Reproducible from source and build configuration |
| Local logs or caches | `.gitignore` | Not shared source inputs |
| Config file containing tokens | Secret manager and `.gitignore` | Never put secrets into Git history |
| Large datasets updated in batches and processed by pipelines | Object storage / data versioning with manifests | Manages data, metadata, and lifecycle independently of source |
| Small PDF guide reviewed alongside source code | Standard Git | Easy metadata diffs and kept in the same commit |

Size is only one factor. Ask who needs the file, when they need it, whether exact versions must be checked out with commits, and who is responsible for backup and retention.

## 10. Moving Already Git-Tracked Files to LFS

If a file already exists in the repository and future versions should use LFS, there are two paths.

### Path A: Convert Future Versions

If keeping the large blobs in older history is acceptable, add the LFS pattern and re-commit the file:

```bash
git lfs track "*.psd"
git add .gitattributes
git add --renormalize assets/design/mockup.psd
git status --short
git commit -m "Track design files with Git LFS"
```

Check `git lfs ls-files` to confirm the current file is managed by LFS. Note: merely running `git lfs track` does not convert old commits to LFS; it only affects future adds/commits after attributes take effect.

### Path B: Convert Entire History with `git lfs migrate`

If the repository is too large due to many old file versions, you may need to migrate history to LFS. This operation rewrites commits, changes the hashes of affected commits, and can affect all converted branches/tags.

First, create a backup or mirror clone so you can recover:

```bash
git clone --mirror https://example.com/team/project.git project-backup.git
git -C project-backup.git lfs fetch --all origin
```

A mirror clone copies Git refs and objects; `git lfs fetch --all` downloads LFS objects referenced by those refs so the backup includes binary content as well. Confirm the fetch completes before treating the mirror as a full backup.

Run a dry-run to inspect scope:

```bash
git lfs migrate info --everything --include="*.psd,*.mp4"
git lfs migrate import --dry-run --everything --include="*.psd,*.mp4"
```

After reviewing the output, run the migration in a dedicated clone or backed-up working copy:

```bash
git lfs migrate import --everything --include="*.psd,*.mp4"
```

Inspect history and the LFS file list:

```bash
git lfs ls-files
git log --oneline --all --decorate -20
git status -sb
```

History migration requires coordinating with the entire team because commit hashes change. Local branches, pull requests, tags, and existing clones may need to be updated or re-cloned. When updating the remote, push the rewritten refs including affected branches and tags; this typically requires a force push under an agreed plan. Execute only after verifying scope, backing up both Git and LFS objects, checking write permissions, and scheduling maintenance. Never force-push a shared repository without notifying and aligning with the team.

If reducing old history size is not necessary, Path A is simpler. If the goal is reducing existing Git history size, Path A is insufficient; you must migrate history or keep the existing repository and create a new repository per plan.

## 11. Handling Accidentally Committed Large Files

If a large file was committed to standard Git, deleting it in a new commit does not remove the blob from history. Distinguish three goals:

1. **Stop tracking going forward:** add an ignore rule and run `git rm --cached` so future commits no longer include the file.
2. **Store new versions in LFS:** add the pattern, re-stage the file, and commit the new pointer; old history retains the blob.
3. **Shrink history size:** rewrite history using tools such as `git lfs migrate` or `git filter-repo` after backing up and aligning, since commit hashes change.

If the file contained secrets, credentials, or sensitive data, simply deleting it from new commits is not enough. Revoke/rotate credentials, clean history following security procedures, audit copies/forks/caches, and coordinate with Git service administrators. Never treat history rewriting as a substitute for rotating exposed secrets.

## 12. Establishing a Repository Policy

A practical policy should clearly answer:

- Which file types are committed directly?
- Which patterns are tracked with LFS?
- Which artifacts are produced by CI and where are they stored?
- Which files are ignored and how are they regenerated?
- Who owns access control, quotas, backups, and retention for LFS/artifacts?
- What steps does CI need to download LFS files or artifacts?
- Where are versions and checksums recorded so builds remain reproducible?

Example repository structure:

```text
project/
├── src/                  # Source code: standard Git
├── docs/                 # Text documentation: standard Git
├── assets/               # Versioned binary assets: Git LFS
├── .gitattributes        # LFS rules and Git attributes
├── .gitignore            # Caches, build outputs, local files
├── build.gradle          # Build configuration: standard Git
└── artifact-manifest.yml # Artifact version/digest: standard Git
```

Build outputs and release packages are published by CI to an artifact registry rather than placed in `build/` and committed alongside source. Asset files in `assets/` are managed by LFS if checkout per commit is required. The manifest records versions and digests so pipelines download the exact artifacts.

## 13. Pre-Commit Review Workflow for Large Files

Before staging a large file, check:

```bash
git status --short
git check-attr filter diff merge -- path/to/file
git lfs ls-files
```

If the file lacks an appropriate rule, classify it as source, LFS, artifact, or ignored. Check size as well:

```bash
git diff --stat
git status --short
```

For staged files, review sizes and change summaries before committing. Do not rely solely on host file-size limits: push limits are a last-resort guardrail, not a storage policy.

A review checklist:

1. Does the file need version history in Git?
2. Is checking out the exact version alongside a commit required?
3. Can the file be regenerated from source or pipelines?
4. Is there a suitable artifact registry or object storage available?
5. Does the remote support LFS and have sufficient quota/bandwidth?
6. Are CI and developers configured with Git LFS if required?
7. Have `.gitattributes`, `.gitignore`, and manifests been updated?
8. Are checksums, versions, and download/regeneration instructions provided?

## 14. Common Errors and How to Handle Them

| Symptom | Possible Causes | Resolution |
| --- | --- | --- |
| Push reports file exceeds size limit | File committed directly to Git or host enforces size limit | Evaluate LFS/artifacts; purge from history if old blobs must be reduced |
| LFS file checks out as pointer text | Git LFS not installed, object not downloaded, or smudge skipped | Install LFS, authenticate, and run `git lfs pull` |
| Pointer push succeeds but LFS upload fails | Missing permissions, quota exhausted, or LFS endpoint unavailable | Check remote LFS config, authentication, and service quotas |
| Repository remains large after `git lfs track` | Old blobs remain in history | Migrate history if size reduction is needed, or accept old history |
| File added to `.gitignore` still shows in Git | File was already tracked previously | Run `git rm --cached`, commit, and keep local file if needed |
| CI fetches source but misses LFS assets | Runner lacks LFS or checkout skipped smudge | Install Git LFS and run `git lfs pull` with suitable credentials |
| LFS clone is very slow | Downloading many large objects or limited bandwidth/quota | Fetch only needed LFS objects, consider artifact/object storage, or on-demand download workflows |
| Artifact is not reproducible | Referencing `latest` or missing checksum/build metadata | Use immutable versions, digests, source commits, and manifests |

## 15. Hands-On Practice

Perform this in a test repository; do not use sensitive data or proprietary files not cleared for sharing:

1. Create a small text file, a test binary file, and a dummy build directory.
2. Commit the text file in standard Git.
3. Create `.gitattributes` and use `git lfs track` for the binary file.
4. Stage `.gitattributes` and the binary file, then inspect `git lfs ls-files`.
5. Commit and push to a test remote supporting LFS; clone fresh to verify content downloads.
6. Add the build directory to `.gitignore` and confirm Git excludes new files in that directory from status.
7. Create an already-tracked file then add an ignore pattern; observe that the file remains tracked.
8. Use `git rm --cached` to untrack the test file, commit, and verify the local file stays on disk.
9. Create an artifact manifest with a version, source commit, and sample checksum; discuss how CI publishes and downloads packages.
10. Compare storage usage and history between direct binary commits and LFS; explain why LFS migration requires a history-rewriting plan.

## 16. Knowledge Self-Check

1. Why are large binary files generally ill-suited for standard Git?
2. What does Git LFS store inside Git commits, and where does it store actual content?
3. When should you choose LFS instead of an artifact registry?
4. Why should JARs or container images built by CI usually live in an artifact registry?
5. What effect does `.gitignore` have on already-tracked files?
6. How does `git rm --cached` differ from deleting a file from the working tree?
7. Why does adding a pattern with `git lfs track` not automatically convert old historical blobs?
8. How does `git lfs migrate import` affect commit hashes and other clones?
9. Why should artifacts be referenced by immutable version or digest rather than `latest`?
10. What factors should be verified before deciding to use LFS in CI/CD?

## Conclusion

Store in Git the files that serve as source of truth and need line-level diffs or history alongside code; use Git LFS for large binary assets that must be checked out per commit; use an artifact registry for packages, release binaries, and pipeline outputs; and exclude caches, temporary files, and reproducible data from version control. When transitioning already-committed files, distinguish stopping tracking, switching future versions to LFS, and rewriting full history. A clear policy covering versions, checksums, access controls, quotas, and backups keeps repositories lean while ensuring teams can reliably reproduce and distribute required assets.
