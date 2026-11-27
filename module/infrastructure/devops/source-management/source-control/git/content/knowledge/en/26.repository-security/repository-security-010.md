# Untrusted Repositories: Hooks, Filters, Submodules, and External Tools

A Git repository can contain source code, scripts, build configurations, and metadata that control how Git processes files. Cloning a repository does not mean you trust everything inside it. Certain mechanisms only store declarations in the repository yet can invoke external programs during checkout, diff, merge, add, or submodule updates. Before running scripts, installing dependencies, or enabling hooks from an unfamiliar project, identify which components can execute code, where they obtain commands, and which machine resources they can access.

## 1. Establishing trust boundaries

When receiving a repository from an unverified source, distinguish three activities:

- **Reading Git data:** inspecting commits, trees, blobs, diffs, or metadata to understand the repository.
- **Fetching external data:** cloning submodules, downloading Git LFS objects, fetching dependencies, or contacting URLs declared in the project.
- **Executing code:** running hooks, filters, build scripts, package install scripts, tests, IDE tasks, or external tools.

These three carry different levels of risk. Reading a blob via `git show` generally does not execute the blob's contents. By contrast, checking out files can invoke configured filters; running `npm install`, `make`, `gradle`, shell scripts, or IDE tasks can execute code supplied by the repository.

Never assume a repository is safe simply because it is hosted on a familiar platform, has many stars, or clones cleanly. A repository can contain malicious changes, compromised dependencies, submodules from different sources, or configurations that cause local tools to run unintended commands.

## 2. What a normal clone does and does not execute automatically

During a standard clone from a remote, Git does not copy hooks from the repository creator's `.git/hooks/` into your `.git/hooks/`. Sample hook files created locally by Git carry a `.sample` suffix and do not run automatically. Similarly, the repository creator's local `.git/config` is not shared like ordinary commits.

However, that does not mean every step of cloning and checking out is purely passive:

- Git may invoke a locally configured **smudge filter** when checking out files with a `filter` attribute.
- Git LFS may be invoked via a filter to fetch large file contents from an LFS endpoint.
- If `--recurse-submodules` is passed, Git contacts submodule URLs and fetches child repositories.
- IDEs or utilities configured to auto-open projects may trigger custom tasks or extensions.
- Install, build, test, and package manager scripts only run when you or an automated tool invoke them, yet they can perform extensive actions on the machine.

A hook committed inside the source tree, such as `.githooks/pre-commit`, does not become an active hook merely by existing in the clone. It must be activated via `core.hooksPath`, copied into the hooks directory, or installed by a tool. Inspect bootstrap scripts before running them because installation scripts themselves can execute code.

## 3. Hooks: scripts Git invokes at specific points

Hooks are programs or scripts that Git executes at workflow points such as `pre-commit`, `commit-msg`, `pre-push`, `post-checkout`, or `post-merge`. Hooks can run quality checks, but they can also execute arbitrary commands with the privileges of the account running Git.

Check the hook location and path configuration:

```bash
git rev-parse --git-path hooks
git config --show-origin --show-scope --get core.hooksPath
```

Inspect the hooks directory contents and check any files without a `.sample` suffix. If `core.hooksPath` is configured globally or at system scope, Git may use that directory for the current repository. A global hook configuration can apply even when you open an untrusted repository.

Key notes:

- Hooks in `.git/hooks` of a remote clone are usually local hooks installed by a user or tool.
- Hooks committed in `.githooks/` are merely repository files until configuration activates them.
- `git config core.hooksPath .githooks` instructs Git to look there for hooks; configure it only after reviewing the scripts.
- `git commit --no-verify` and `git push --no-verify` can bypass some client-side hooks, so local hooks are not an enforced security boundary.

If a repository was handed to you as a directory already containing `.git` rather than freshly cloned, treat `.git/config` and the hooks directory as untrusted data. They may contain pre-installed local configuration or hooks.

## 4. Filters in `.gitattributes` can invoke external programs

`.gitattributes` can assign attributes per path. Some attributes only control how Git displays or processes content, whereas attributes such as `filter`, `diff`, and `merge` can select a configured driver to run an external program.

For example, a repository may contain:

```gitattributes
*.asset filter=asset-clean diff=asset-view merge=asset-merge
```

This line only names drivers. The actual commands executed usually come from Git configuration on the machine, for example:

```ini
[filter "asset-clean"]
    clean = asset-tool clean
    smudge = asset-tool checkout

[diff "asset-view"]
    textconv = asset-tool render-text

[merge "asset-merge"]
    driver = asset-tool merge %O %A %B %L %P
```

Driver configurations can live in global, system, or local config. If a machine already has a driver configured under the same name, an attribute in the repository can cause Git to invoke that driver at the corresponding stage.

| Mechanism | When the program may be invoked | Risk to inspect |
|---|---|---|
| `filter.<name>.smudge` or `process` | Checkout, restore, or materializing content | Executes commands when writing content to the working tree |
| `filter.<name>.clean` or `process` | Add or processing content into the index | Executes commands when preparing commit content |
| `diff.<name>.textconv` or `command` | Viewing diffs using that driver | Runs external conversion or diff tools |
| `merge.<name>.driver` | Merging files using that driver | Runs an external merge command |

Not every attribute executes code. The key point is that an attribute can select a driver while the driver's command is configured elsewhere. A malicious `.gitattributes` could leverage a trusted driver already installed on the machine to trigger commands when you check out or diff.

## 5. Inspecting attributes and driver configs before use

Read `.gitattributes` files in the repository, including those in subdirectories. You can inspect committed versions without checking out content:

```bash
git show HEAD:.gitattributes
git ls-tree -r --name-only HEAD
```

The second command lists paths in the tree to locate `.gitattributes` files in subdirectories. After finding paths, run `git show HEAD:path/to/.gitattributes` to inspect each file.

Check the attributes Git resolves for a path:

```bash
git check-attr --all -- path/to/file.asset
```

Check filter, diff, and merge driver configs along with their origins:

```bash
git config --show-origin --show-scope --get-regexp '^(filter|diff|merge)\.'
```

Output may contain internal paths or machine-specific commands; review carefully before sharing logs. If you spot an unfamiliar driver, do not check out or diff files that trigger that driver until you verify the command and configuration origin.

Git LFS is a common example of a legitimately installed filter. If a repository uses LFS, inspect `.gitattributes` and `.lfsconfig`, and verify the LFS endpoint and access permissions before downloading content. You can set `GIT_LFS_SKIP_SMUDGE=1` when cloning to defer materializing LFS contents, then download after verifying the source and endpoint.

## 6. Diff and merge can also invoke external tools

Not every seemingly read-only command is guaranteed not to run external programs. When viewing diffs, Git can invoke an external diff or textconv driver if configuration and attributes call for it. When merging, Git can invoke a registered merge driver.

Before using diff/merge tools on an unfamiliar repository:

1. Inspect `.gitattributes` and the drivers assigned to files.
2. Check `diff.*`, `merge.*`, and `diff.external` configs with `git config --show-origin --show-scope`.
3. Verify where the invoked executable comes from and whether you intentionally installed it.
4. If external drivers are unnecessary, use a clean environment or verified safe config to inspect raw contents.

Never run commands found inside `.gitattributes` as if they were trusted instructions. Attributes only name drivers; look up the actual commands in effective Git configuration.

## 7. Submodules: a parent repository can request loading external sources

The `.gitmodules` file declares submodule names, paths, and URLs. When running:

```bash
git clone --recurse-submodules <repository-url>
```

Git accesses submodule URLs and clones child repositories. Those repositories may belong to different organizations, reside on different servers, or have separate histories and codebases. Fetching a submodule does not prove its source is trustworthy.

Before initializing submodules, read the configuration:

```bash
git show HEAD:.gitmodules
git submodule status --recursive
```

Inspect gitlinks in the tree:

```bash
git ls-tree HEAD
```

A gitlink usually has mode `160000` and points to a specific commit in the child repository. Verify the URL, pinned commit, and access permissions for each submodule. Never enable `--recurse-submodules` automatically on an unfamiliar repository before reviewing `.gitmodules`.

An important safeguard: `git submodule init` does not copy custom `!command` update commands from `.gitmodules` into local configuration for security reasons. Even so, submodule URLs can still cause Git to connect to unwanted servers; child repositories can also contain their own filters, build scripts, and dependencies. Evaluate the entire source chain.

## 8. Git LFS and external endpoints

Repositories using Git LFS store pointers in Git and download actual contents from an LFS endpoint. A `.lfsconfig` file can hold shared LFS settings, including the endpoint URL. When cloning or checking out with Git LFS installed, the filter can initiate network requests to download content.

Before downloading LFS content from an untrusted repository:

- Read `.gitattributes` to identify which patterns use `filter=lfs`.
- Read `.lfsconfig` if present and verify the endpoint.
- Confirm the endpoint belongs to the expected provider or organization.
- Use smudge-skip mode to defer downloads if prior review is needed.
- Never supply sensitive credentials to an unverified endpoint.

An LFS object is data and does not execute merely by being downloaded. Execution risk arises when a tool opens, processes, or runs that content; network risk and credential leakage can occur during the download itself if the endpoint or authentication setup is untrusted.

## 9. Build scripts, package managers, and IDEs are additional execution surfaces

Many dangerous actions come not from core Git, but from tools you run after cloning:

- `npm install` or `npm ci` can run package lifecycle scripts.
- Maven and Gradle can execute plugins, tasks, or build scripts.
- `make`, shell scripts, PowerShell, and task runners execute commands declared in the repository.
- IDEs can prompt or automatically trigger tasks, extensions, debuggers, or run configurations.
- Container builds can run commands in a Dockerfile; the base image is also a component requiring trust.

Before running anything, inspect relevant files such as `package.json`, lockfiles, `pom.xml`, `build.gradle`, `settings.gradle`, `Makefile`, Dockerfile, `.vscode/tasks.json`, IDE configs, and bootstrap scripts. Verify that dependencies are pinned and package sources are valid.

Never click "Trust project", enable all extensions, or run install commands just because an IDE suggests them. Enable those features only after verifying the source and understanding what actions they will perform.

## 10. Local configuration in `.git/config` also warrants inspection

During a standard remote clone, Git creates a local `.git/config` for the new repository based on clone options and the remote URL. The repository creator's local configs are not automatically downloaded as part of commits.

However, if you receive a repository folder that already contains `.git`, a disk copy, an archive containing metadata, or an environment prepared by someone else, `.git/config` may contain unwanted settings. Keys to watch closely include:

- `core.hooksPath`: changes where Git looks for hooks.
- `core.fsmonitor`: can specify a helper program for monitoring file changes.
- `filter.*`, `diff.*`, `merge.*`: declare commands for processing content or diffing/merging.
- `credential.helper`: specifies the credential retrieval mechanism.
- `core.sshCommand`, `core.gitProxy`: alters how Git connects to remotes.
- `include.path` and `includeIf.*`: loads additional configuration files from other paths.

Inspect configuration with origins and scopes:

```bash
git config --list --show-origin --show-scope
```

Never copy a raw `.git/config` from an untrusted machine onto a workstation holding credentials. If you must use a pre-packaged repository directory, review every setting before running Git commands that might trigger hooks, filters, or helpers.

## 11. `safe.directory` is not a sandbox

Git includes an ownership check to reduce risks when operating inside directories owned by another user. When Git reports `dubious ownership`, do not solve it by adding a broad wildcard to global configuration:

```bash
git config --global --add safe.directory '*'
```

That setting weakens ownership checks across all repositories. Once you have verified a specific path and have a valid reason to trust it, add only that exact path:

```bash
git config --global --add safe.directory /path/to/trusted/repository
```

On Windows, use an absolute path appropriate for your environment. `safe.directory` only satisfies Git's ownership check; it does not prove source code, hooks, filters, submodules, or build scripts are safe and does not isolate them from the system.

## 12. Verifying origin and integrity is not the same as verifying safety

You can verify commit or tag signatures if the project uses a signing workflow:

```bash
git verify-commit <commit>
git verify-tag <tag>
```

A valid signature indicates the signed object has not changed since signing and the signature matches the verified key. You must still verify that the key belongs to the right person or organization through a trusted channel. A valid signature does not guarantee source code is free of vulnerabilities, contains no malware, or makes no external service calls.

Similarly, checking object integrity with `git fsck` can detect corrupted objects or invalid links, yet it is not a tool for analyzing program behavior. Distinguish data integrity, provenance, and code safety.

## 13. Workflow for opening an untrusted repository

A cautious workflow can be executed step by step:

1. **Verify the source:** inspect the URL, organization, sender, requested commit or tag, and an independent confirmation channel.
2. **Create an isolated environment:** use a disposable VM or container, a non-admin account, no mounted secret directories, and no SSH agent forwarding.
3. **Clone without checking out or fetching submodules:**

   ```bash
   git clone --no-checkout --no-recurse-submodules <repository-url> review-repo
   ```

   This fetches the Git repository while deferring file checkout and skipping automatic submodule downloads. You still need to trust the chosen transport URL and keep Git updated.

4. **Read metadata first:**

   ```bash
   git show HEAD:.gitattributes
   git show HEAD:.gitmodules
   git ls-tree -r HEAD
   git log --oneline --decorate -20
   ```

   If a file does not exist, `git show` reports it not found; that does not necessarily indicate a repository error.

5. **Inspect local and global configuration:**

   ```bash
   git config --list --show-origin --show-scope
   git config --show-origin --show-scope --get-regexp '^(filter|diff|merge)\.'
   git config --show-origin --show-scope --get core.hooksPath
   ```

6. **Evaluate secondary sources:** verify submodule URLs, LFS endpoints, dependency registries, build scripts, IDE tasks, and external tools.
7. **Controlled checkout:** check out files only after evaluating attributes and filters that might be invoked. If no external filters are needed, use a clean environment with no custom drivers installed.
8. **Run code inside a sandbox:** disable or restrict network access; never mount credentials, SSH keys, cloud configs, or personal directories; use dummy data and least privilege.
9. **Monitor behavior:** observe child processes, file accesses, and network connections when evaluating high-risk code.
10. **Destroy the environment after review:** discard the disposable VM/container per procedure without bringing unverified credentials or artifacts back to your main workstation.

Metadata inspection commands can still be influenced by a repository's local configuration or external tools installed on the machine. For a repository handed over with `.git` already present, inspect configs and hooks before running broader commands.

## 14. Isolating execution and protecting credentials

When you must build or run tests on an untrusted repository, use a separate environment:

- Non-admin/non-root user account.
- Disposable VM or container, with read-only mounts where possible.
- Never mount home directories, SSH keys, cloud credentials, browser profiles, or host sockets.
- Never forward the SSH agent and never use credential helpers holding personal tokens.
- Restrict network access to what is required; if builds must fetch dependencies, allow only verified registries.
- Use test data, never production databases or services.
- Keep Git, runtimes, package managers, and base images updated to reduce risks from known vulnerabilities.

Containers are not automatically complete sandboxes. Containers share a kernel with the host; mount permissions, capabilities, sockets, and networking determine the level of isolation. For high-risk code, a disposable VM or dedicated analysis environment may be more appropriate.

## 15. Red flags that warrant stopping and investigating

Stop before executing if you observe any of these signs:

- `.gitattributes` assigns unfamiliar filter/diff/merge drivers or there is corresponding local config of unknown origin.
- `.gitmodules` contains unrelated URLs or URLs using unexpected protocols or hosts.
- `.lfsconfig` redirects endpoints to an unverified host.
- Bootstrap scripts request admin privileges, download and execute commands from unpinned URLs, or modify global config.
- Build scripts read home directories, SSH keys, tokens, cloud environment variables, or send data externally without clear reason.
- An IDE prompts to enable extensions from unknown publishers or run automatic tasks.
- Hooks or helpers perform actions outside check scope without explanation.

You do not have to conclude a repository is definitely malicious from a single sign. Pause potentially executing actions, and verify the component's purpose and origin via maintainers or an independent channel.

## 16. Takeaways

A repository is data that should be evaluated before becoming executed code. Hooks are not carried over automatically in a normal clone, yet filters, external diff/merge drivers, submodules, Git LFS, and build/IDE tools can trigger external actions when invoked. Inspect `.gitattributes`, `.gitmodules`, `.lfsconfig`, and effective Git configuration; defer checkout or dependency downloads when origins are unclear; isolate execution environments and keep credentials out of reach. Signatures and object checks only help verify provenance and integrity—they do not replace evaluating code safety.
