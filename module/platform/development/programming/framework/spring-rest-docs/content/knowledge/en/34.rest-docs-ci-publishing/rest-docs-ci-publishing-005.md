# Synchronizing Code Commits and Generated Documentation

REST API documentation generated with Spring REST Docs is only trustworthy when it can be traced back to the exact source code version that produced it. Generated snippets, Asciidoctor/Markdown pages, test reports, and release artifacts must belong to the same commit or a clearly identified build revision. Mixing snippets from one commit with HTML from another commit, or pulling stale artifacts from a cache, can produce documentation that looks valid while describing the wrong API.

Commit synchronization means the pipeline produces test output and documentation from one deterministic source revision, preserves the link between artifacts, and publishes that exact set of outputs. Never run tests on one revision and then check out a new branch to render or publish using a leftover snippet directory. This lesson covers managing revision identity, artifact provenance, multi-job pipelines, versioning, and rollbacks.

This lesson belongs to the **CI and Publishing** chapter of the `SPRING_REST_DOCS` module. The module creates verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, generates snippets for requests, responses, payloads, parameters, and headers, and then compiles Asciidoctor/Markdown and integrates the build and CI.

## 1. Learning Objectives

After this lesson, you can:

1. Explain why code, tests, snippets, and documentation must share the same revision.
2. Attach commit SHA/build ID to test reports and rendered documentation.
3. Pass generated snippets across CI jobs without mixing revisions.
4. Design a test → snippet → render → artifact → publish pipeline with clear provenance.
5. Distinguish dependency caches from generated artifacts.
6. Version documentation alongside API releases.
7. Detect commit-mismatched artifacts, handle non-reproducible builds, and perform rollbacks.

## 2. Why Must Commits Be Synchronized?

A single API change can modify code, tests, and documentation simultaneously: a controller changes its path/method; the response changes status/headers/JSON; descriptors change field/parameter descriptions; preprocessors change how tokens/hosts are masked; AsciiDoc changes includes or prose.

Spring REST Docs generates snippets while tests run. Therefore, snippets reflect the code and tests at that revision. If rendering or publishing uses snippets from a different revision, the verification link is broken.

### 2.1. Example of a Revision-Mixed Artifact

| Component | Revision |
| --- | --- |
| Application code | Commit A |
| Documentation tests | Commit A |
| Generated snippets | Commit A |
| AsciiDoc source | Commit B |
| Rendered HTML | Commit B |
| Publish artifact | Unknown origin |

HTML may include snippets from A while using AsciiDoc content from B. Reviewers cannot tell which API the documentation accurately represents. Another case is HTML rendered from B while the snippets directory still contains stale files from A due to an uncleaned workspace.

Principle: every input composing a documentation set must have defined provenance and revision compatibility.

## 3. Identifying Revision Identity

CI providers usually provide the commit SHA of the revision being built. The pipeline should record:

- Full commit SHA or immutable revision ID.
- Branch or pull request number, if applicable.
- Build/run ID.
- Application or API release version.
- Build timestamp as metadata, not as a replacement for commit identity.

Do not use branch names as unique identifiers because branches move as new commits arrive. Short SHAs are readable, but keep the full SHA in metadata to prevent collisions.

### 3.1. Storing Metadata with Documentation

You can place revision identity in document attributes:

```asciidoc
:revnumber: 4.2.0
:commit-sha: abcdef1234567890abcdef1234567890abcdef12
:build-id: 1842

= Orders API
:toc:
```

Values are examples only. CI must pass metadata from the revision being built; do not hard-code SHAs in source. You can display the short commit in the footer while artifact metadata retains the full SHA.

### 3.2. Attaching Metadata to Artifacts

```text
rest-docs-4.2.0-commit-abcdef123456-build-1842/
├── generated-snippets/
├── html/
├── test-reports/
└── build-info.txt
```

Build info can contain commit SHA, build ID, API version, toolchain versions, and build time. Do not put secrets or environment credentials into metadata.

## 4. One Pipeline, One Revision

A standard pipeline checks out a fixed revision and keeps that revision throughout all steps:

```text
Checkout immutable commit SHA
             │
             ▼
Clean workspace/build outputs
             │
             ▼
Compile and run documentation tests
             │
             ▼
Generate snippets
             │
             ▼
Render Asciidoctor / Markdown
             │
             ▼
Validate output and provenance
             │
             ▼
Package one documentation artifact
             │
             ▼
Publish that exact artifact
```

Steps can run in a single job or across multiple jobs. Do not check out a moving branch between steps, and never use snippets from another build.

### 4.1. Do Not Re-Checkout a Moving Branch Mid-Pipeline

Incorrect example: the test job checks out commit A and creates snippets; the render job checks out the branch name `main`, which has now moved to commit B, and then includes snippets from A. The result is documentation built from inputs across two revisions.

The right approach is for the render job to receive the source artifact or check out the exact SHA A, and receive the snippets artifact also built from SHA A. If a pipeline checks a PR merge result, use that exact merge revision for both tests and rendering.

## 5. Synchronizing Snippets and Documentation Across Multiple CI Jobs

In a large pipeline, you can split into three jobs:

1. **Test job:** checks out the revision, cleans, runs documentation tests, and generates snippets.
2. **Render job:** fetches source and snippets of the same revision and runs Asciidoctor/Markdown.
3. **Publish job:** fetches the rendered artifact from the same build and publishes it.

Each artifact passed between jobs should include commit SHA/build ID. The render job checks that snippet metadata matches the source revision before running.

### 5.1. Example Artifact Flow

```text
Test job (commit A)
  ├── generated-snippets/
  ├── test-reports/
  └── provenance: SHA A
          │
          ▼
Render job (source SHA A + snippets SHA A)
  ├── index.html
  ├── assets/
  └── provenance: SHA A
          │
          ▼
Publish job (rendered artifact SHA A)
  └── deployed documentation
```

If metadata does not match, rendering/publishing must stop. Never bypass the check or rename artifacts to hide a mismatch.

### 5.2. Pass Artifacts, Not Arbitrary Workspaces

Workspaces across CI jobs are usually isolated. Use the CI provider's artifact upload/download mechanism to transfer snippets and rendered docs. Avoid relying on leftover runner directories or shared directories without clear provenance.

## 6. Distinguishing Cache and Artifacts

| Type | Purpose | Rule for REST Docs |
| --- | --- | --- |
| Dependency cache | Speed up downloading Gradle/Maven dependencies | Can be shared with an appropriate cache key |
| Build cache | Reuse task outputs when inputs are tracked properly | Enable only when tasks declare exact inputs/outputs |
| Generated snippets artifact | Input for rendering documentation | Tied to the commit/build that generated it |
| Rendered documentation artifact | Output for review/publishing | Must use snippets and source from the same revision |
| Release artifact | Officially published documentation set | Immutable or versioned per release policy |

Do not use cache as the source of truth for snippets. If tests do not run yet the renderer fetches old cached snippets, documentation may fail to reflect API changes.

## 7. Documentation Reproducibility

A build is reproducible when the same source revision, locked dependencies/toolchain, and deterministic test data produce equivalent content. For Spring REST Docs, pay attention to:

- Fixtures should not rely on wall-clock time unless necessary.
- Dynamic IDs, timestamps, and request IDs are normalized where appropriate.
- Preprocessors do not depend on runner hostnames or environments.
- Locale, timezone, and encoding are configured deterministically.
- JDK, Gradle/Maven, and Asciidoctor plugin versions are pinned.
- Builds do not pull snippets or include files from stale directories.

### 7.1. Not Every Byte Is Always Identical

Metadata such as build timestamps or PDF files can differ between runs. Distinguish build metadata from API content. The goal is stable snippets and contracts; if byte-for-byte reproducibility is needed, timestamps and other non-deterministic sources must be normalized.

## 8. Versioning Documentation by API Release

Official documentation is typically versioned by API or product release:

```text
docs/
├── 4.1/
│   └── index.html
├── 4.2/
│   └── index.html
└── current/
    └── index.html
```

A `current` alias can point to the active release while older versions remain available for integrators. Do not use a commit SHA as the sole public version if the product has its own version semantics; use the SHA for build traceability.

On a new release: select the source revision/tag; run documentation tests; render and verify artifacts; attach the API/documentation version; publish to the exact versioned path; update the `current` alias after the release completes.

## 9. Verifying Provenance Before Publishing

Before publishing, verify:

- Commit SHA in build metadata matches the checked-out revision.
- Test reports belong to the same commit.
- The snippets artifact was generated from the same commit.
- AsciiDoc/Markdown sources used to render belong to the same revision.
- Rendered HTML/PDF was built from those snippets.
- API/documentation version matches the intended release.
- The artifact being published is the exact artifact that was reviewed.

You can create a manifest:

```text
commit=abcdef1234567890abcdef1234567890abcdef12
build=1842
api-version=4.2.0
test-status=passed
snippets-artifact=rest-docs-snippets-1842
rendered-artifact=rest-docs-html-1842
```

A manifest is metadata for cross-checking, not a replacement for signatures or artifact attestations if the organization requires higher assurance.

## 10. Pull Requests, Merges, and Releases

| Stage | Revision to use | Output |
| --- | --- | --- |
| PR validation | PR head or defined merge revision | Test report, preview docs |
| Main branch build | Merged commit | Docs artifact for main |
| Release build | Immutable release tag/commit | Versioned documentation |
| Publish | Artifact of verified release build | Official documentation |

If a PR is checked using a synthetic merge commit, use that exact merge commit for both testing and rendering. After merge, the main branch pipeline rebuilds from the merged commit to create official artifacts.

## 11. Rollback and Fixing Published Documentation

When a published documentation release is found to be wrong:

1. Identify the published version, commit, and build ID.
2. Pause or mark the affected artifact if needed.
3. Fix sources/tests/descriptors in a new commit.
4. Rerun tests, rendering, and validation.
5. Publish the fix according to the appropriate version/revision policy.
6. Keep history or release notes so users know the documentation was corrected.

Do not overwrite old artifacts without preserving provenance. For versioned documentation, you can publish a patch documentation release or update the same version per product policy; clearly state the change.

## 12. Common Errors and Fixes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| HTML does not match code | Rendering and tests used different revisions | Lock to the same commit SHA |
| Stale snippets appear | Workspace/cache holds output from another build | Clean and generate fresh artifacts |
| Render job missing snippets | Artifact not passed from test job | Upload/download artifacts within the same run |
| Artifacts have different SHAs | Metadata not checked | Add provenance validation |
| Branch build changes between jobs | Checked out branch name instead of SHA | Check out immutable revision |
| Preview is right yet release is wrong | Publish grabbed artifact from another run | Publish the exact reviewed artifact |
| Continuous snippet diffs | Unstable fixtures/timezone/IDs | Normalize test data |
| Docs version mismatches API | Wrong manual version tagging | Derive version from release metadata |
| Rollback lacks clear origin | Artifact overwritten without manifest | Store immutable/versioned artifacts |
| Cache causes false-green render | Cached snippets used despite tests not running | Never treat cache as snippet source |

## 13. Hands-On Exercise

Design a multi-job pipeline for the orders API. The test job creates snippets for the commit; the render job creates HTML; the publish job releases the documentation version matching the release.

**Tasks:**

1. Check out the immutable commit SHA in the test job.
2. Clean output and run documentation tests.
3. Upload snippets along with a manifest containing commit SHA/build ID.
4. Have the render job check out the exact SHA and download the matching snippets artifact.
5. Verify snippet metadata matches the source revision before rendering.
6. Generate HTML/PDF and store provenance alongside the artifact.
7. Have the publish job use only the verified rendered artifact from the same pipeline run.
8. Tag the API/documentation version from the release tag.
9. Test a mismatched artifact SHA scenario and confirm the pipeline halts.
10. Write a rollback procedure for when published documentation is found to be incorrect.

**Completion criteria:** source, tests, snippets, rendered docs, and published artifacts share unified provenance; no mixed revisions; clear documentation versioning; mismatches block publishing; traceable and rollback-ready.

## 14. Key Takeaways

- Snippets are generated from tests of a specific source revision; rendered documentation must use that exact source and snippet revision.
- Attach full commit SHA and build ID to metadata/artifacts for traceability.
- When splitting CI jobs, pass snippets via artifacts with provenance rather than relying on shared workspaces.
- Distinguish dependency caches from generated snippets and rendered artifacts.
- Use immutable revisions rather than moving branch names.
- Version documentation by API release; use SHAs for build traceability.
- Verify provenance before publishing and publish only verified artifacts.
- Keep artifact history to investigate, fix, and roll back incorrect documentation.
