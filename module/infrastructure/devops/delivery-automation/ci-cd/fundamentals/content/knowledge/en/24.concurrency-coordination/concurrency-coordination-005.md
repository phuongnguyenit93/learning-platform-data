# Controlling Concurrent Publications of the Same Version

In CI/CD, the same release event can be processed multiple times: a webhook is redelivered, an operator triggers a workflow twice, two pipeline branches generate a release simultaneously, or a job is retried after a timeout. If two processes publish the same package and version simultaneously, they can overwrite tags, create inconsistent metadata, or expose two different payloads under the same version name.

Publishing must be treated as a coordinated operation. Every artifact coordinate needs immutable identification rules, duplicate-handling safeguards, and an atomic result-recording point. For the same package and version, identical content can be recognized as a safe repeat; differing content must be rejected as a conflict. The goal is to guarantee that **one version represents exactly one verified artifact**.

## 1. Why Can Two Publications Occur Simultaneously?

Pipelines are frequently triggered from multiple sources:

- Pushing a release tag concurrently with a manual run.
- A webhook from the Git provider being redelivered because the previous delivery timed out.
- Two different workflows processing the same version.
- Two runners retrying simultaneously after failing to receive a response from the registry.
- An older job still running when a newer job starts.
- Two release branches generating the same version due to loose versioning conventions.
- Someone re-running a job while the previous publication has not yet finished.

For example, two runners both check that `payments-api:2.8.1` does not exist yet. Both receive "not found," then both upload and update the tag. If the registry allows tags to be overwritten, the final content depends on whichever process finishes last.

This is a **check-then-act** race condition: two processes inspect the same state and then act on stale results. Checking before uploading is insufficient to protect the final write operation.

## 2. Defining the Right Coordination Scope

Before choosing a lock or queue, determine whether two runs genuinely conflict. Never lock all of CI/CD when only one package version needs protection.

A publish lock is typically based on the artifact coordinate:

| Component | Example | Role |
|---|---|---|
| Registry/repository | `registry.example.com` | Distinguishes the target repository |
| Package/image | `payments-api` | Distinguishes the product |
| Version/tag | `2.8.1` | Identifies the release |
| Platform/variant | `linux/amd64` | Distinguishes variants if published separately |
| Channel | `stable`, `candidate` | Distinguishes release channels if applicable |

Logical lock example:

~~~text
publish:registry.example.com/payments-api:2.8.1
~~~

Two jobs targeting the same package and version must be coordinated. Two jobs publishing `2.8.1` and `2.8.2` can run in parallel if the registry and release process allow it. For multi-architecture images, lock at the manifest index level or the coordinate end users pull; locking only per platform can still let two processes race to update the shared manifest.

Separate publish locks from deploy locks. Publishing a package and deploying a service protect two different resources:

- Publish lock: registry/package/version.
- Deploy lock: environment/service or cluster/namespace/service.
- Migration lock: database/schema.
- Release metadata lock: release record or channel pointer.

Choosing too broad a scope lowers throughput. Choosing too narrow a scope may fail to protect the resource actually under contention.

## 3. Published Versions Must Be Immutable

Once published, a version's content should never change. Human-readable tags such as `2.8.1` should be configured as immutable if the registry supports it. When a fix is needed, publish a new version or a new prerelease version according to project conventions.

For example:

~~~text
payments-api:2.8.1  -> sha256:aaa...
payments-api:2.8.2  -> sha256:bbb...
~~~

If two runs both try to publish `2.8.1`:

- Same digest and matching provenance metadata: the later run can be treated as a duplicate retry and return the existing result.
- Different digest: must report a conflict and halt.
- Version already exists but digest cannot be verified: do not overwrite; escalate for investigation.
- Tag points to an incomplete artifact or lacks provenance: do not treat as a valid release.

Never use `latest` as the sole identifier for a release. That tag is typically mutable and can point to different versions. Channel tags like `stable` or `latest` may be maintained as updatable pointers, but only updated after the immutable version has been published and verified successfully.

## 4. Distinguishing Duplicate Requests from Version Conflicts

A repeated request is not necessarily an error. What matters is determining whether it asks for the exact same outcome or attempts to alter the content of an already-existing version.

| Scenario | Desired outcome |
|---|---|
| Same package, version, and digest | Idempotent success/no-op after verification |
| Same package and version, different digest | Conflict; do not overwrite |
| Same version and digest, different provenance | Check provenance policy; do not silently replace metadata |
| Version does not exist yet | Eligible to receive publish claim |
| Version is being published by another job | Wait, return in-progress status, or fetch result later |
| Repeated request from the same webhook event | Deduplicate by event/request identity |

For example, two webhooks announcing tag `v2.8.1` may simply be a redelivered event. If the artifact digest matches, the second run should read the already-published result and finish as a successful no-op. If two different commits both attempt to claim version `2.8.1`, that is a versioning mistake and must be handled as a conflict.

Never automatically pick "last run wins." Doing so allows a version already referenced in release notes, deployment records, or downstream manifests to silently change content.

## 5. Using Idempotency Keys to Prevent Duplicate Processing

Idempotency means executing the same request multiple times produces only a single final effect. For publishing, an idempotency key can be derived from the package coordinate:

~~~text
publish:<registry>/<package>:<version>
~~~

Example:

~~~text
publish:registry.example.com/payments-api:2.8.1
~~~

When receiving a request, the system records the key along with digest, provenance, and status:

- `requested`: request accepted.
- `publishing`: a worker is actively executing it.
- `published`: artifact has been published and verified.
- `failed`: execution ended with an error.
- `conflict`: coordinate is already bound to different content.

When a duplicate request arrives:

1. Look up the record by idempotency key.
2. Compare the digest and required metadata.
3. If already `published` with matching content, return the prior result.
4. If `publishing`, wait or return an in-progress status.
5. If content differs, return a conflict.
6. If the previous attempt `failed`, allow retry only per policy and inspect registry state before proceeding.

Idempotency keys must remain stable across retries. Never generate a fresh key per attempt, or every retry turns into an independent request.

## 6. Using Unique Constraints to Claim Publish Authority

If a database or release service acts as coordinator, a unique constraint can be placed on the coordinate. The database arbitrates claim creation atomically.

Conceptual schema example:

~~~sql
CREATE TABLE release_publications (
    registry_name  TEXT NOT NULL,
    package_name   TEXT NOT NULL,
    version        TEXT NOT NULL,
    variant        TEXT NOT NULL DEFAULT '',
    artifact_digest TEXT NOT NULL,
    state          TEXT NOT NULL,
    owner_id       TEXT,
    lease_expires_at TIMESTAMPTZ,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (registry_name, package_name, version, variant)
);
~~~

When a worker starts, it attempts to insert a record for the package/version. If the insert succeeds, the worker holds the initial claim. On a primary-key conflict, the worker reads the existing record and compares digest/state.

Operation pattern:

~~~sql
INSERT INTO release_publications (
    registry_name,
    package_name,
    version,
    variant,
    artifact_digest,
    state,
    owner_id
)
VALUES (
    'registry.example.com',
    'payments-api',
    '2.8.1',
    'linux-amd64',
    'sha256:aaa...',
    'publishing',
    'runner-8421'
)
ON CONFLICT (registry_name, package_name, version, variant) DO NOTHING;
~~~

This is a PostgreSQL example. The application must check the inserted row count and read the existing record within an appropriate transaction. Never simply run a `SELECT` to check if the version exists before running `INSERT`, as two workers can both see "does not exist."

A unique constraint protects the database claim, but does not automatically make the registry upload atomic. The final publish step still requires immutable tags, conditional creates, or registry-side conditional writes.

## 7. Using Locks When Publishing Requires a Single Writer

A lock ensures only one process holds permission to operate on a resource at a time. The lock may live in the CI platform, a database, a distributed lock service, or a release controller.

A lock must define:

- Resource key: the package/version being protected.
- Owner: run ID or worker identity.
- Acquisition: how the lock is acquired atomically.
- Lease/TTL: ownership duration if a worker disconnects.
- Renewal: how the lease is extended while work continues.
- Release: how it is freed upon completion.
- Recovery: how abandoned locks are handled after a crash.
- Audit: who acquired the lock, how long they held it, and the outcome.

Locks must be held strictly across the genuinely contended scope. If building takes 15 minutes while publishing takes 30 seconds, build and test first, then acquire the lock right before coordinate verification and publishing. This minimizes lock hold time.

Never use file locks on a runner's local disk to coordinate across multiple machines. Each runner has its own filesystem; two runners can create identically named files unaware of one another.

## 8. Distributed Locks, Leases, and Fencing Tokens

Distributed locks must handle worker disconnects or stalls. A lease with a TTL lets the lock expire automatically if the owner fails to renew.

However, TTL alone is insufficient. For example:

1. Worker A acquires a lock with a 60-second lease.
2. A pauses for more than 60 seconds without its process dying.
3. The lease expires; Worker B acquires a new lock.
4. A resumes and still attempts to write the artifact.
5. Both A and B perform side effects even though the lock service sees only B holding the lease.

This is the stale-owner problem. One solution is a **fencing token**: each lock grant issues an incrementing sequence number. The target system accepts operations only from the newest token.

~~~text
Worker A receives token 41
Lease A expires
Worker B receives token 42
Registry/release service accepts token 42
Late write from A with token 41 is rejected
~~~

Fencing tokens only work if the side-effect target validates the token or provides an equivalent guard. If the registry lacks fencing support, rely on immutable versions, conditional writes, and atomic claims at the publish layer to prevent stale workers from overwriting.

Leases must be renewed via heartbeats. When renewal fails, the worker must stop before causing any further side effects. Never keep publishing merely because the process is still alive.

## 9. Do Not Confuse Locks with Atomic Publishing

Locks coordinate workers that obey the same protocol. They do not guarantee an artifact is never partially written, overwritten by another client, or modified outside the pipeline.

A safe publish workflow should have two layers:

1. **Coordination:** ensures only one valid worker handles a coordinate at a time.
2. **Atomicity/immutability:** ensures the final result appears only when the artifact is complete and the version is unclaimed.

Some registries/object stores support conditional creation or immutable tags. You can upload blobs by digest first, verify checksums, and then create the final manifest/tag using a create-if-absent operation. If the coordinate already exists, read back the digest and apply duplicate/conflict rules.

Never expose a tag to consumers while layers or metadata are still missing. Use a staging/private state during upload, then publish the manifest or release record after all checks complete.

## 10. Safe Publish Flow from Build to Release

Reference flow:

~~~mermaid
flowchart TD
    A[Build and test artifact] --> B[Compute digest and create provenance]
    B --> C[Acquire publish coordination]
    C --> D{Version already exists?}
    D -- Same digest --> E[Cross-check metadata and return prior result]
    D -- Different digest --> F[Conflict, halt publish]
    D -- Does not exist --> G[Upload content-addressed artifact]
    G --> H[Verify checksum/signature]
    H --> I[Create version/tag conditionally]
    I --> J[Commit release record]
    J --> K[Release lock]
    E --> K
    F --> K
~~~

A practical sequence:

1. Build the artifact and run tests outside the lock region.
2. Compute the digest from the actual contents.
3. Generate provenance bound to the commit, workflow, and build run.
4. Acquire the lock or claim for the package/version.
5. Read existing registry state and release records.
6. If the same digest is already published, return an idempotent success.
7. If a different digest exists, stop with a conflict.
8. If absent, upload blobs/layers via content-addressed storage.
9. Verify checksums, signatures, and metadata.
10. Create the immutable version/tag via a conditional operation.
11. Write the release record and audit event.
12. Release the lock on every exit path.

If step 10 succeeds yet the worker loses connectivity before receiving the response, retries must re-read the registry. Never default to re-uploading or overwriting. Actual state in artifact storage is the source of reconciliation.

## 11. Example Coordinating Publishes with GitHub Actions Concurrency

GitHub Actions can prevent workflows/jobs sharing a concurrency group from running simultaneously. The example below keys the group by repository, package, and version:

~~~yaml
name: Publish immutable package

on:
  workflow_dispatch:
    inputs:
      package_name:
        description: Package to publish
        required: true
        type: string
      version:
        description: Immutable release version
        required: true
        type: string
      artifact_digest:
        description: Digest returned by the verified build
        required: true
        type: string

permissions:
  contents: read
  packages: write

jobs:
  publish:
    runs-on: ubuntu-latest
    concurrency:
      group: publish-${{ github.repository }}-${{ inputs.package_name }}-${{ inputs.version }}
      cancel-in-progress: false

    steps:
      - uses: actions/checkout@v4

      - name: Validate release coordinate
        env:
          PACKAGE_NAME: ${{ inputs.package_name }}
          RELEASE_VERSION: ${{ inputs.version }}
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
        run: |
          [[ "$PACKAGE_NAME" =~ ^[a-z0-9][a-z0-9._-]*$ ]]
          [[ "$RELEASE_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.-]+)?$ ]]
          [[ "$ARTIFACT_DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]

      - name: Publish only if absent or identical
        env:
          PACKAGE_NAME: ${{ inputs.package_name }}
          RELEASE_VERSION: ${{ inputs.version }}
          ARTIFACT_DIGEST: ${{ inputs.artifact_digest }}
        run: |
          ./scripts/publish-if-absent.sh \
            --package "$PACKAGE_NAME" \
            --version "$RELEASE_VERSION" \
            --digest "$ARTIFACT_DIGEST"
~~~

This example assumes the artifact was already built, tested, and stored retrievably by digest before the publish job runs. The publish script must retrieve that exact artifact, validate provenance, and perform a safe version creation in the registry. The regex only validates input shape; projects should use version parsers and package naming rules matching their registry. Concurrency groups do not replace immutable tags or conditional writes.

There is an important limitation: a GitHub Actions concurrency group permits only one running run and one pending run in the same group; a new run can replace the pending run. Therefore, it works well to prevent concurrent execution and favor latest state, but it is not a FIFO queue guaranteeing every request executes in turn. If every publish request must be preserved, use a durable queue or release service.

For active publishes, `cancel-in-progress: false` avoids proactively cancelling the current run simply because a new run enters the same group. Scripts must still be designed to tolerate timeouts, runner disconnects, and retries.

## 12. Coordination on Other CI Platforms

Different CI platforms provide their own coordination mechanisms:

| Platform | Common mechanism | Notes |
|---|---|---|
| GitHub Actions | `concurrency.group` at workflow/job level | One running and one pending; not a FIFO queue |
| GitLab CI | `resource_group` | Serializes jobs sharing a resource; choose process mode for ordering needs |
| Jenkins | Lockable Resources plugin | Locks shared resources around the publish block |
| Dedicated release service | Durable queue, database claim, or distributed lock | Centralizes retries, state tracking, and auditing |

Conceptual GitLab CI example:

~~~yaml
publish:
  stage: publish
  resource_group: "publish-payments-api-2.8.1"
  script:
    - ./scripts/publish-if-absent.sh --package payments-api --version 2.8.1
~~~

Resource group names should be built from the actual package/version using safe conventions. If version is an input variable, validate it before use. Resource groups serialize jobs, yet the script must still check version and digest in the registry.

With Jenkins, you can lock by resource name:

~~~groovy
lock(resource: 'publish-payments-api-2.8.1') {
    sh './scripts/publish-if-absent.sh --package payments-api --version 2.8.1'
}
~~~

This example requires the Lockable Resources plugin and proper resource configuration. Never use a single static lock name for every package when independent releases can publish in parallel.

## 13. Handling Retries and Timeouts After Publishing

A tricky scenario occurs when the registry already accepted the artifact, yet the runner timed out before receiving the response. The pipeline does not know whether the publish succeeded.

Never treat a timeout as a definitive publish failure. The retry workflow should:

1. Read coordinate state from the registry and release record.
2. If the version already exists with the same digest, verify metadata and return success.
3. If the version does not exist yet, inspect temporary uploads and proceed safely.
4. If the version exists with a different digest, return a conflict.
5. If state cannot be determined, keep the request in a `pending`/`unknown` state and investigate; never overwrite just to "retry."

Retries must be bounded, with exponential backoff and jitter. If the registry returns 429 or 503, honor `Retry-After` when present. If the error is a version conflict, never auto-retry because the requested content still conflicts.

Each attempt should have its own run ID while sharing the same idempotency key for one logical publish request. This enables per-attempt auditing while still preventing duplicate effects.

## 14. Cancelling Jobs and Releasing Locks Safely

Jobs can be cancelled by users, timeouts, runner crashes, or newer workflows. Locks must not stay held forever, yet releasing locks must also be safe.

Principles:

- Use leases/TTLs if the lock service supports them.
- Renew the lock when publishing takes longer.
- Provide `cleanup`/`finally` logic to release when the job ends normally.
- Allow only the current owner to release its own lock.
- Never delete a lock solely by resource name without checking owner/token.
- Once a lock expires, old workers must be blocked from further writes via fencing or conditional writes.
- Inspect registry state before retrying after cancellation.

Never rely entirely on CI cleanup steps because a runner can be forcibly killed. Leases clean up abandoned locks; fencing/immutable storage handles old workers still trying to write after losing authority.

## 15. Publish Coordination Differs from Deploy Coordination

A release typically involves at least two contention zones:

- Multiple jobs attempting to publish the same package/version.
- Multiple jobs deploying the same service to an environment.

They need separate lock keys:

~~~text
publish:registry.example.com/payments-api:2.8.1
deploy:production:payments-api
migration:production:payments-db
~~~

Two different versions can be built and published in parallel. However, two deployments of the same service to production may need serialization to avoid overwriting rollouts or skewing deployment records.

Never use one global lock for the entire CI/CD module when only a specific resource needs protection. Conversely, never key locks by run ID, as every run would get a distinct key and fail to block runs competing over the same coordinate.

If a workflow needs multiple locks, acquire them in a fixed order to reduce deadlock risk. Avoid holding a publish lock while waiting for human approval or an unrelated long-running task.

## 16. Testing Contention Scenarios

Concurrency controls must be tested with deliberate simultaneous runs, not only a single isolated pipeline.

| Scenario | Expected outcome |
|---|---|
| Two runs with same package/version/digest | One publishes; the other succeeds idempotently |
| Two runs with same package/version, different digests | One wins the claim; the other reports conflict |
| Two runs with different versions | Can publish in parallel if policy allows |
| Redelivered webhook for the same event | Deduplicates without creating a second release |
| Runner dies while holding lock | Lease expires or operator safely recovers |
| Lease expires while old worker continues | Old writes are rejected by fencing/conditional publish |
| Timeout after registry accepted artifact | Retry reads state and verifies without overwriting |
| Two workflows using different lock keys for same resource | Tests must catch the misconfigured key |
| Tag already exists with a different digest | Publish fails without forcing an update |
| Publish succeeds but release metadata write fails | Reconcile from registry and finalize metadata idempotently |

Run tests against a test registry or namespace. You can inject controlled delays between the check and write steps to expose race conditions. Verify the final artifact, digest, release metadata, and audit logs.

## 17. Monitoring and Investigating Publish Activity

A well-coordinated system provides visibility into queue waits, locks, and publish outcomes.

Record:

- Package coordinate and version.
- Artifact digest and provenance reference.
- Idempotency key.
- Workflow run ID, attempt, and actor.
- Lock key, owner, fencing token, or lease expiry if present.
- Lock wait duration and lock hold duration.
- Publish status and registry response.
- Duplicate/no-op or version conflict outcomes.
- Timestamps for upload, verification, and release record commit.
- Errors, retry count, and final outcome.

Useful metrics:

| Metric | Meaning |
|---|---|
| Publish lock wait time | Degree of resource contention |
| Concurrent publish conflict count | Number of requests competing for the same coordinate |
| Duplicate request rate | Frequency of duplicate webhooks/retries |
| Publish duration | Time spent holding the critical section |
| Stale lease count | Number of abnormal lock expirations |
| Immutable version conflict | Attempts to write different content to an existing version |
| Reconciliation backlog | Number of releases needing state synchronization |

Logs must never contain registry tokens, passwords, or secrets. Use run IDs, package coordinates, and digests for tracing.

## 18. Checklist for Controlling Concurrent Publications of the Same Version

Before putting a publish workflow into production, verify:

- [ ] Artifact coordinates and lock scope are defined.
- [ ] Published versions are treated as immutable.
- [ ] Mutable tags like `latest` are not used as the sole release identifier.
- [ ] Identical version and digest requests are handled idempotently.
- [ ] Same version with a different digest is rejected as a conflict.
- [ ] Idempotency keys remain stable across retries.
- [ ] Claims are created via unique constraints or atomic operations.
- [ ] Locks have owners, leases/TTLs, renewals, and recovery paths.
- [ ] Fencing tokens or conditional writes prevent stale workers from writing.
- [ ] The final publish step is atomic or create-if-absent.
- [ ] Artifact upload and verification finish before exposing the version.
- [ ] Release metadata is recorded and reconcilable after timeouts.
- [ ] CI concurrency groups/resource groups use consistent keys.
- [ ] Queuing and cancellation limits of the CI platform are understood.
- [ ] Publish locks are separated from deploy locks and migration locks.
- [ ] Concurrent runs, retries, timeouts, and worker crashes are tested.
- [ ] Audit logs and metrics track locks, conflicts, and duplicate requests.

Controlling concurrent publishes is not just adding a lock to a pipeline. It requires combining immutable version identifiers, idempotency, atomic claims, writer coordination, and conditional publish operations. When two requests arrive together, the system must clearly determine whether it is a safe repeat or a content conflict—never letting the outcome depend on whichever runner happened to finish last.
