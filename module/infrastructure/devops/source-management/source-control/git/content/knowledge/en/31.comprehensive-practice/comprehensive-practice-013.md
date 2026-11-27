# Verifying a Clean State, Pushed Content, and Tag Targets Before Handover

Before handing over a branch or publishing a release, you must prove three things: the working tree and index have no unintended changes; the commits to hand over are on the remote; and the release tag exists on the remote and points to the exact commit. Merely seeing a push succeed is not enough without verifying the target ref, upstream branch, and the commit referenced by the tag.

This lab uses a Git repository with an `origin` remote and a release branch `release/1.4`. You will check local state, synchronize remote info, push the branch, create an annotated tag `v1.4.0`, verify both refs from the remote, and compile handover evidence. Adapt branch names, remotes, tags, and test commands to your real project.

## 1. Goals and Prerequisites

Expected outcomes:

- Identify the exact repository root, current branch, and remote.
- Distinguish staged, unstaged, untracked, and ignored changes.
- Confirm local commits are built on the latest remote state.
- Push the exact branch to the remote and verify the remote branch points to the intended commit.
- Create an annotated tag on the verified release commit.
- Push that specific tag and verify the tag object and target commit on the remote.
- Confirm no unintended uncommitted changes remain at handover.
- Record the branch, commit hash, tag, test results, and remote state.

Lab assumptions:

| Component | Example value |
|---|---|
| Remote | origin |
| Handover branch | release/1.4 |
| Release tag | v1.4.0 |
| Commit to hand over | HEAD of release/1.4 |
| Corresponding remote branch | origin/release/1.4 |

Do not push directly to a protected branch if team workflow requires a pull request or release pipeline. In that case, run local verification and prepare the branch/tag per policy, then hand over through the designated review workflow.

## 2. Confirming You Are in the Right Repository and Branch

Start from the project directory:

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git status --short --branch
~~~

Outcomes to verify:

- Repository root matches the project being handed over.
- Current branch is release/1.4.
- You are not accidentally working inside another clone, worktree, or repository.
- Branch status shows upstream if already configured.

View local branches and upstreams:

~~~bash
git branch -vv
~~~

An example line may look like:

~~~text
* release/1.4  a1b2c3d [origin/release/1.4: ahead 2] Prepare release
~~~

This indicates the local branch is two commits ahead of the remote-tracking branch recorded at the last fetch. It does not yet prove the remote currently sits at that commit; you must fetch before drawing conclusions.

Inspect remotes:

~~~bash
git remote -v
~~~

Confirm origin points to the intended target repository. Some URLs may embed credentials; never copy a URL containing tokens or credentials into reports or public channels.

If the remote is not configured yet, verify the URL with the project maintainer before adding it:

~~~bash
git remote add origin https://git.example.com/team/inventory.git
~~~

Never guess a URL or replace an existing remote without confirming the target repository.

## 3. Inspecting All Local Changes

Short status command:

~~~bash
git status --short --branch
~~~

To see every untracked file instead of collapsing directories:

~~~bash
git status --short --untracked-files=all
~~~

Inspect working tree changes alone:

~~~bash
git diff
~~~

Inspect staged changes alone:

~~~bash
git diff --cached
~~~

Check for whitespace errors:

~~~bash
git diff --check
git diff --cached --check
~~~

States to understand:

| State | Meaning | Pre-handover question |
|---|---|---|
| Staged | Index content slated for the next commit | Were any files or hunks staged by mistake? |
| Unstaged | Tracked files modified but not yet in the index | Are these changes needed in a commit or unfinished work? |
| Untracked | New files not yet tracked by Git | Are these source/docs to commit or temporary output? |
| Ignored | Untracked files excluded from normal status by ignore rules | Do they hold local data or secrets that must stay safe? |

To also view ignored files:

~~~bash
git status --short --ignored
~~~

Ignored files are not included in commits by normal add operations, yet they still exist on disk and can hold important data. Do not delete them merely to make status look empty.

List files currently tracked by Git:

~~~bash
git ls-files
~~~

Find files that are already tracked yet match current ignore rules:

~~~bash
git ls-files -ci --exclude-standard
~~~

If the last command lists files, inspect them because already-tracked files remain managed by Git even if an ignore pattern matches them later.

## 4. Deciding How to Handle an Unclean Working Tree

Do not proceed with pushing a release while unclassified changes remain.

### 4.1. Changes Belonging in the Release

If changes are complete and belong in the release:

~~~bash
git add path/to/file
git diff --cached --check
git diff --cached
~~~

Stage only intended paths. After reviewing staged contents, commit with a descriptive message:

~~~bash
git commit -m "fix: validate inventory quantity"
~~~

If multiple independent changes exist, split them into separate commits. After committing, re-check status and history.

### 4.2. Unfinished Changes to Preserve

If you need to keep unfinished work without including it in the release, you can stash it:

~~~bash
git stash push -u -m "WIP before release handoff"
~~~

The -u option includes untracked files but excludes ignored files. Stashes are not long-term storage; keep track of which stash holds your work and restore it after handover.

Do not use stash if project policy requires all work to be committed on a dedicated branch or if stashing would strip context needed for review.

### 4.3. Changes Not Needed

If you have verified a tracked edit is unnecessary, inspect the diff and restore that exact file from the appropriate source. For example, discarding unstaged edits in one file:

~~~bash
git restore --worktree -- path/to/file
~~~

Unstaging a file while keeping its contents on disk:

~~~bash
git restore --staged -- path/to/file
~~~

Never run restore with a broad pathspec like dot without reading the full diff first. For untracked files, restore is not a cleanup tool; verify whether a file can be deleted or must be kept.

## 5. Inspecting Current Commits and History for Handover

Inspect recent commits:

~~~bash
git log -5 --oneline --decorate
git show --stat --oneline HEAD
git show --no-patch --format=fuller HEAD
~~~

Check how many local commits exist that are not yet in the remote-tracking branch after refreshing remote state in the next step.

Before fetching, do not rely on stale ahead/behind counts in git status. Remote-tracking branches only reflect the latest fetch.

## 6. Fetching to Refresh Remote State

Fetch updates from origin:

~~~bash
git fetch --prune origin
~~~

Fetch downloads objects and updates remote-tracking refs without merging or rebasing into your working branch. The --prune option removes remote-tracking refs that no longer exist on the remote.

Re-check the branch:

~~~bash
git status -sb
git branch -vv
~~~

If the branch lacks an upstream, check whether the remote branch exists:

~~~bash
git ls-remote --heads origin refs/heads/release/1.4
~~~

If the remote branch already exists, set the upstream:

~~~bash
git branch --set-upstream-to=origin/release/1.4 release/1.4
~~~

If the remote branch does not exist yet, you will set the upstream on your first push using -u.

## 7. Counting Ahead and Behind Commits

After fetching, compare the local branch against the remote-tracking branch:

~~~bash
git rev-list --left-right --count HEAD...origin/release/1.4
~~~

The output contains two tab-separated numbers:

~~~text
2    1
~~~

The first number is commits unique to HEAD (local ahead). The second number is commits unique to origin/release/1.4 (local behind).

| Output | Interpretation | Action needed |
|---|---|---|
| 0 0 | Both branches share the same tip | No commits to push or pull |
| 2 0 | Local is ahead by two commits | Review both commits, then push |
| 0 1 | Local is behind by one commit | Integrate remote changes per team policy |
| 2 1 | Both sides have diverged | Review both sides, integrate, and re-verify |

View local-only commits:

~~~bash
git log --oneline origin/release/1.4..HEAD
~~~

View remote-only commits:

~~~bash
git log --oneline HEAD..origin/release/1.4
~~~

If local is behind or both sides diverged, do not push yet. Read remote-only commits, coordinate with the team if needed, and integrate according to the repository's merge or rebase policy. After integrating, re-run tests and fetch/compare before pushing.

Verify ancestry relationship:

~~~bash
git merge-base --is-ancestor origin/release/1.4 HEAD
~~~

If exit code is 0, the remote-tracking tip is an ancestor of HEAD; local already incorporates remote history as of the fetch. If the command fails, local does not yet contain that tip or the two histories are unrelated. Never use force push to mask an unclear state.

## 8. Running Tests and Reviewing Release Contents

Run the test suite required by your project. For example:

~~~bash
./mvnw test
~~~

Or with Gradle:

~~~bash
./gradlew test
~~~

Or for a Node project:

~~~bash
npm test
~~~

Run only the command appropriate for the current repository. Record the result, runtime version, and environment if they affect reproducibility.

Review the scope of changes compared to the remote branch:

~~~bash
git diff --stat origin/release/1.4...HEAD
git diff --name-status origin/release/1.4...HEAD
~~~

Check items easily overlooked:

- Were template config files updated alongside code?
- Do lockfiles or dependency manifests match the changes?
- Did any build files, caches, logs, credentials, or local data slip into commits?
- Do README, changelog, and release notes accurately describe this version?
- Do commits have clear messages and exclude out-of-scope changes?

Spot oversized or unexpected files in the change list by reviewing each path individually. Do not rely solely on total file count or total diff size.

## 9. Pushing the Exact Branch to the Remote

Before pushing, confirm:

- Current branch is indeed release/1.4.
- Working tree and index are clean or accounted for.
- Local commits have been reviewed.
- No unintegrated remote-only commits remain.
- Required tests have passed.

You can preview the push operation:

~~~bash
git push --dry-run origin release/1.4
~~~

Dry-run validates the refspec and pushability at that moment, though it does not replace the real push or prove data was written to the remote.

If this is the first push for the branch and you need to set upstream:

~~~bash
git push -u origin release/1.4
~~~

If upstream is already configured:

~~~bash
git push origin release/1.4
~~~

Naming the exact branch avoids accidentally pushing other branches. Do not use git push --all or git push --tags during handover unless you have reviewed every ref that would be sent.

If the remote rejects the push because the branch changed, fetch again and re-check ahead/behind. Integrate new commits per policy and retry. Never use --force or --force-with-lease to bypass rejection without a team-approved plan.

## 10. Verifying the Branch Is Actually on the Remote

After pushing, fetch again:

~~~bash
git fetch origin
~~~

Compare the object IDs of the local and remote-tracking branches:

~~~bash
git rev-parse HEAD
git rev-parse origin/release/1.4
~~~

Both values must match if the goal was to push current HEAD to the remote branch and no subsequent commits landed afterward.

Verify the ref directly on the server:

~~~bash
git ls-remote --heads origin refs/heads/release/1.4
~~~

The output shows the object ID and ref name. The object ID should match your recorded HEAD value.

If someone else pushed a new commit right after your push, the remote may advance past your HEAD. In that case, fetch and inspect the new state; do not assume your push failed just because the remote moved again. Distinguish whether your commit landed or the branch simply received another commit afterward.

## 11. Checking the Release Tag Before Creating It

A tag is a named ref pointing to an object, usually a commit. Before creating a tag, confirm the planned tag does not already exist locally or on the remote:

~~~bash
git tag --list v1.4.0
git ls-remote --tags origin refs/tags/v1.4.0
~~~

Read the local and remote outputs separately. If neither command returns the tag, the tag name is free in both places and safe to create. If the tag exists only locally, inspect it first; if it is already an annotated tag on the exact commit with the right message, you can use it and proceed to pushing. If the tag exists on the remote but not locally, fetch it before inspecting:

~~~bash
git fetch origin tag v1.4.0
~~~

Once the tag exists locally, inspect its target object:

~~~bash
git show --no-patch --decorate v1.4.0
git rev-parse 'v1.4.0^{}'
~~~

Compare against the approved release commit. If the local tag is lightweight when policy requires annotated, or if its metadata/target is wrong, stop and handle per team procedure; never silently overwrite an existing tag. Published release tags should remain immutable.

Verify the commit to be tagged:

~~~bash
git rev-parse HEAD
git show --no-patch --oneline HEAD
~~~

Confirm HEAD is the exact release commit and that the release branch was already pushed and verified in the previous step.

## 12. Creating an Annotated Tag

Create an annotated tag with a release message:

~~~bash
git tag -a v1.4.0 -m "Release v1.4.0"
~~~

An annotated tag creates a dedicated tag object storing the tag name, tagger, date, message, and target object. It fits releases because it preserves metadata describing the release milestone.

If your organization requires signed tags and you have a signing key configured:

~~~bash
git tag -s v1.4.0 -m "Release v1.4.0"
~~~

Use only one of those tag commands for the same name and only when the tag does not yet exist locally. If you already verified an existing local tag matches your target, skip creation and proceed to pushing. Do not create the tag a second time or move an existing tag.

Verify the object type:

~~~bash
git cat-file -t v1.4.0
~~~

For an annotated tag, the output must be `tag`. A lightweight tag normally returns `commit` because the ref points directly to a commit object.

Inspect tag metadata:

~~~bash
git show --no-patch --format=fuller v1.4.0
git cat-file -p v1.4.0
~~~

Confirm the tag peels to the exact commit:

~~~bash
git rev-parse 'v1.4.0^{}'
git rev-parse HEAD
~~~

Both object IDs must match if the tag is meant to mark current HEAD.

If using a signed tag, verify the signature:

~~~bash
git verify-tag v1.4.0
~~~

A valid signature only proves the tag object matches the signature and checked key. The team still needs to confirm through a trusted channel that the key belongs to the authorized releaser.

## 13. Pushing the Specific Tag to the Remote

Push the exact tag you created:

~~~bash
git push origin v1.4.0
~~~

This sends only the named tag. Avoid passing --tags mechanically because that option can push unrelated local tags outside the current release scope.

If the remote reports the tag already exists, stop and inspect the target object on the remote. Never delete or force-update a published release tag without an explicit decision from the release owner.

## 14. Verifying the Tag From the Remote

Query tag info directly from the server:

~~~bash
git ls-remote --tags origin refs/tags/v1.4.0 'refs/tags/v1.4.0^{}'
~~~

For an annotated tag, output typically shows two lines:

- The `refs/tags/v1.4.0` line pointing to the tag object.
- The `refs/tags/v1.4.0^{}` line pointing to the peeled target object, normally the commit.

The peeled ref line lets you compare directly against the recorded release commit. For a lightweight tag, the remote normally prints only one line pointing straight to the commit.

You can also fetch the tag locally and verify:

~~~bash
git fetch origin tag v1.4.0
git cat-file -t v1.4.0
git rev-parse 'v1.4.0^{}'
~~~

Compare the object ID against the handed-over HEAD. If the tag on the remote points to a different commit, the release cannot be considered complete; stop and investigate.

## 15. Confirming Clean State After Pushing and Tagging

Re-check:

~~~bash
git status --short --branch
git diff
git diff --cached
git status --short --untracked-files=all
~~~

If no unexpected tracked, staged, or untracked changes remain, short status output will list nothing. Ignored files may still be present; inspect separately:

~~~bash
git status --short --ignored
~~~

For ignored files, verify they are intentional caches, build outputs, or local configs. Do not delete files just to achieve empty output. If you spot a file containing a secret, keep it out of Git and handle the credential per security policy.

Run a final ref check:

~~~bash
git branch -vv
git tag --list v1.4.0
git rev-parse HEAD
git rev-parse origin/release/1.4
git rev-parse 'v1.4.0^{}'
~~~

Provided no new commits landed on the remote after your push, the three object IDs for HEAD, the remote-tracking branch, and the peeled tag should be identical. If the team allows the branch to keep advancing post-release, note that the tagged commit and branch tip may diverge; the tag must still point to the exact approved release commit.

## 16. Handover Evidence Table

Before announcing completion, record verifiable evidence:

| Item | Evidence to record |
|---|---|
| Repository | Root path or project name |
| Branch | release/1.4 |
| Remote | origin and verified target repository |
| Commit | Full hash of the release commit |
| Branch push | Ref refs/heads/release/1.4 on the remote |
| Tag | v1.4.0 |
| Tag type | Annotated or signed annotated |
| Tag target | Commit hash after peeling the tag |
| Testing | Commands run and pass/fail results |
| Working tree | No unexpected staged, unstaged, or untracked changes |
| Handover owner | Responsible person and timestamp per team process |

Example record:

~~~text
Repository: inventory
Branch: release/1.4
Remote: origin
Commit: <full-commit-id>
Remote branch verified: refs/heads/release/1.4
Tag: v1.4.0 (annotated)
Tag target: <same-full-commit-id>
Tests: PASS
Working tree: clean
Ignored local files: reviewed
~~~

Never put tokens, private keys, credentials, or URLs containing authentication info into handover reports.

## 17. Common Error Scenarios

### Push Succeeded but Local Branch Still Reports Ahead

Fetch again and compare object IDs:

~~~bash
git fetch origin
git rev-parse HEAD
git rev-parse origin/release/1.4
~~~

Upstream may not be configured, the remote-tracking ref may be stale, or the push targeted a different ref. Check refspec and remote URL before pushing again.

### Push Rejected as Non-Fast-Forward

The remote has new commits not yet integrated locally. Fetch, inspect remote-only commits, then merge or rebase per team policy. Run tests and push again after confirming history.

### Local Tag Exists but Remote Lacks It

Check the tag name, remote URL, and push command. Push the specific tag with git push origin v1.4.0 and verify with git ls-remote.

### Remote Tag Exists but Points to a Different Commit

Halt the release process. Inspect the tag object, target commit, and release announcement history. Never unilaterally delete, move, or force-update a published tag.

### Working Tree Is Clean but Holds Important Ignored Files

Git hides ignored files in normal status output. Check git status --ignored and determine whether each file is reproducible output or local data needing protection. A clean working tree does not mean every file on disk is backed up in Git.

### Commit Already Pushed but Bug Discovered Post-Handover

If the branch is shared, consider creating a fix commit or reverting the faulty commit per team workflow. For an already published release tag, follow release policy to cut a new version tag or handle a controlled exception; never silently move the old tag.

## 18. Condensed Handover Sequence

You can run this verification sequence once you understand repository state and confirmed no unclassified changes exist:

~~~bash
git status --short --branch
git fetch --prune origin
git rev-list --left-right --count HEAD...origin/release/1.4
git log --oneline origin/release/1.4..HEAD
git diff --check
git diff --cached --check
git push --dry-run origin release/1.4
git push origin release/1.4
git fetch origin
git rev-parse HEAD
git rev-parse origin/release/1.4
git tag -a v1.4.0 -m "Release v1.4.0"
git rev-parse 'v1.4.0^{}'
git push origin v1.4.0
git ls-remote --tags origin refs/tags/v1.4.0 'refs/tags/v1.4.0^{}'
git status --short --branch
~~~

This is an illustrative sequence, not a script to run blindly. If the ahead/behind count reveals branch divergence, tests fail, the tag already exists, or the remote rejects the push, stop and resolve that issue before continuing subsequent steps.

## 19. Completion Checklist

- [ ] Verified repository root and local branch.
- [ ] Remote URL points to the exact target repository.
- [ ] Classified staged, unstaged, untracked, and ignored files.
- [ ] Confirmed no secrets or generated files slipped into commits unintentionally.
- [ ] Fetched remote before comparing.
- [ ] Checked ahead/behind counts and local-only/remote-only commits.
- [ ] Integrated remote changes per team policy.
- [ ] Ran required test suite and recorded results.
- [ ] Pushed the release branch to the exact remote.
- [ ] Verified remote branch via fetch, object ID, or ls-remote.
- [ ] Created an annotated tag on the exact release commit.
- [ ] Pushed the tag and verified it from the remote.
- [ ] Confirmed working tree and index are clean; reviewed ignored files.
- [ ] Handover evidence includes branch, commit, tag, and test results.

## 20. Key Takeaways

A trustworthy handover requires evidence on both local and remote sides. First classify all changes across the working tree, index, untracked, and ignored files; then fetch to compare ahead/behind counts and integrate remote commits per policy. Push the specific branch, re-fetch, and compare object IDs to prove content landed on the right ref. Create an annotated tag on the verified release commit, push that specific tag, and verify the peeled target from the remote. Finally, record the commit, branch, tag, test results, and clean status so the recipient can verify everything independently.
