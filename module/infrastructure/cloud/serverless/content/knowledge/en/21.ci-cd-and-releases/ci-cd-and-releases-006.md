# Blue-Green Deployment for APIs and Functions

Blue-green deployment is a release strategy in which the system maintains two independently runnable environments or versions: **blue** serving current traffic and **green** holding the new version. The team deploys and tests green first, then shifts traffic to green via a stable routing point. If errors are detected, traffic can be shifted back to blue provided the old version and data remain compatible.

In serverless, blue and green are typically two revisions, versions, or deployments of a function/service. The provider manages compute and autoscaling, yet the team must still design routing, configuration, IAM permissions, database migrations, state, queue consumers, and scheduled tasks. A successful code deployment does not guarantee safe rollback if the new version altered schemas or created irreversible side effects.

This lesson focuses on applying blue-green to Java HTTP APIs and event/message-processing functions, controlled traffic shifting, maintaining data compatibility, and defining rollback criteria.

## 1. What Is Blue-Green Deployment?

Blue-green keeps two environments with equivalent configurations. Initially, blue receives all traffic. Green is deployed from a new artifact and verified via smoke tests or test traffic. Once green meets criteria, the router or platform switches traffic to green.

Conceptual flow:

~~~mermaid
flowchart TD
    Build[Build immutable artifact]
    DeployB[Deploy green version]
    Test[Smoke test / readiness / security checks]
    Router[Traffic router or stable alias]
    Blue[Blue: current version]
    Green[Green: new version]
    Observe[Observe metrics and errors]
    Rollback[Route traffic back to blue]

    Build --> DeployB
    DeployB --> Test
    Test -->|Pass| Router
    Test -->|Fail| Rollback
    Router --> Blue
    Router --> Green
    Blue --> Observe
    Green --> Observe
    Observe -->|Healthy| Complete[Promote green]
    Observe -->|Regression| Rollback
    Rollback --> Blue
~~~

The names blue and green are simply labels for two versions. Two physical server clusters are not required. In serverless, the two sides can be:

- Two published Lambda versions and a stable alias.
- Two Cloud Run revisions of the same service.
- Two deployments/slots on a serverless platform supporting slot swaps.
- Two independent functions or services behind an API gateway/load balancer.

### Key Phases

1. **Build:** create an immutable artifact tagged with commit SHA or release ID.
2. **Deploy green:** deploy the new version with required configuration and permissions.
3. **Verify:** check startup, health, API contracts, dependencies, and security.
4. **Switch:** shift part or all of the traffic to green.
5. **Observe:** monitor latency, errors, throttling, business metrics, and dependencies.
6. **Promote or roll back:** keep green as primary or revert to blue per predefined criteria.

Blue-green reduces downtime and creates a fast fallback path. It does not automatically guarantee zero downtime, zero data loss, or reversible side effects.

## 2. How Does Blue-Green Differ from Rolling and Canary?

| Strategy | Release Mechanism | Advantages | Risks/Trade-offs |
|---|---|---|---|
| Rolling | Gradually replace old instances with new ones | No need to maintain two full environments | Multiple versions serve concurrently during rollout; rollback can be slow |
| Blue-green | Maintain blue and green, switch traffic between them | Fast cutover and rollback via router/alias | Extra resource usage while running concurrently; requires data compatibility |
| Canary | Send a small percentage of traffic to new version then ramp up | Catch bugs on a fraction of real traffic | Requires sufficient sample size; more complex routing and analysis |

Canarying is a traffic-shifting pattern often combined with blue-green. For example, blue takes 95% and green takes 5% during observation; then green ramps up to 25%, 50%, and 100%.

Blue-green does not have to switch 100% of traffic in one step. If the platform supports weighted routing, you can use a small share to validate behavior with live traffic. If there is only a stable alias pointing to one version, test green via a separate URL or endpoint first before cutting over completely.

## 3. Organizing Versions for Java APIs and Functions

A release should have an immutable identity. Avoid deploying a mutable artifact tag that can be overwritten, such as latest. Use explicit versions or digests to know precisely which code is running.

A release manifest might store:

~~~yaml
releaseId: order-api-2026.11.17-4
gitCommit: 8f31a9d
artifactDigest: sha256:...
runtime: java21
configRevision: order-api-config-18
databaseSchemaRange:
  minimum: 12
  maximum: 14
~~~

The manifest is metadata for the pipeline; it holds no secrets. Runtime, config, and schema range values help the pipeline verify compatibility before shifting traffic.

### Distinguishing Artifacts, Revisions, and Aliases

- **Artifact:** built JAR, container image, or deployment package.
- **Version/revision:** specific deployment of an artifact and its associated configuration.
- **Alias/stable URL:** stable entry point used by clients.
- **Traffic policy:** rules distributing requests across versions/revisions.

Clients should call a stable endpoint or alias. Do not hardcode specific versions in every client if the goal is swapping backends without updating all callers.

With Java, the same artifact can be deployed as multiple revisions with different per-environment configurations. Record the digest and config revision of each side so that on rollback you know the exact code and config restored.

## 4. Designing Blue-Green for HTTP APIs

HTTP APIs are the easiest case for blue-green because requests are routed via URLs, gateways, aliases, or load balancers.

One architecture:

~~~mermaid
flowchart LR
    Client[API clients]
    Gateway[API Gateway / Load Balancer]
    Blue[Blue API version]
    Green[Green API version]
    DB[(Shared compatible database)]
    Client --> Gateway
    Gateway -->|Current traffic| Blue
    Gateway -.->|Test or weighted traffic| Green
    Blue --> DB
    Green --> DB
~~~

Principles:

- Keep a stable URL for clients.
- Deploy green with an independently testable endpoint or revision.
- Ensure blue and green use compatible database schemas during the transition.
- Maintain backward-compatible API contracts whenever possible.
- Switch traffic at the gateway or stable alias.
- Monitor by version to compare errors and latency.
- Retain blue long enough to roll back within the observation window.

### Testing Green Before Taking Traffic

Smoke tests should verify:

- Health endpoint returns expected results.
- Java runtime initializes cleanly.
- Secrets/config are read under the proper runtime identity.
- Database and dependency connections work.
- Authentication and authorization remain intact.
- API contracts are not broken.
- Invalid requests return appropriate status codes.
- Logs, metrics, and traces carry the release ID or revision label.

Do not check only a `/health` endpoint and declare the release safe. Health checks often only verify the process is alive; smoke tests must exercise critical business paths with safe test data.

## 5. Blue-Green for AWS Lambda Using Published Versions and Aliases

AWS Lambda supports published versions and aliases. A published version is a snapshot of code and certain version-specific settings. An alias is a stable name that points to a version and supports weighted routing between a primary version and a secondary version in supported scenarios.

Example:

- Version 41 is the currently serving blue.
- Version 42 is the new green.
- Alias live is the integration point used by API Gateway or callers.

Do not invoke a version ARN directly in clients if you want to preserve alias-based switching.

### Creating and Testing a New Version

The pipeline can update function code, wait for the update to finish, then publish a version:

~~~bash
aws lambda update-function-code   --function-name order-api   --zip-file fileb://target/order-api.zip

aws lambda wait function-updated   --function-name order-api

aws lambda publish-version   --function-name order-api   --description "release-2026.11.17-4"
~~~

The illustrative command uses a ZIP package. If using a container image, update the image URI by digest and publish the corresponding version. The pipeline must capture the version number returned by publish and save it in release metadata.

### Switching the Alias to Green

After testing the new version, update the alias:

~~~bash
aws lambda update-alias   --function-name order-api   --name live   --function-version 42
~~~

If canarying is desired, keep version 41 as primary and send a small share to version 42:

~~~bash
aws lambda update-alias   --function-name order-api   --name live   --function-version 41   --routing-config '{"AdditionalVersionWeights":{"42":0.05}}'
~~~

In this example, the alias routes most invocations to version 41 and 5% to version 42. Once metrics meet criteria, switch primary to 42 and remove weighted routing. Verify Lambda routing limits and conditions at deployment time.

### Rolling Back the Alias

If green fails, revert the alias to version 41:

~~~bash
aws lambda update-alias   --function-name order-api   --name live   --function-version 41
~~~

Alias rollback can be fast, yet it only reverts code routing. It does not automatically undo database migrations, published messages, sent emails, or side effects executed by version 42.

### API Gateway and Aliases

API Gateway integrations must point to the alias ARN rather than a version ARN to switch traffic via alias. Check resource policies, Lambda permissions, and deployment stages to ensure the gateway still invokes the right alias after release.

For event source mappings, do not assume weighted alias routing behaves like HTTP invocations. Each mapping may maintain its own checkpoint, and enabling two consumers concurrently can process the same record twice. The event-driven section below covers dedicated handling.

## 6. Blue-Green for Cloud Run and Cloud Run Functions

Cloud Run deploys each change as a revision. You can keep multiple revisions and split traffic across them. Cloud Run functions (2nd gen) run on top of Cloud Run; when using traffic management, verify which API manages the service resource and deployment flow.

For example, after deploying a new revision, inspect the revision list and shift traffic:

~~~bash
gcloud run services update-traffic order-api   --region=asia-southeast1   --to-revisions=order-api-00041-abc=90,order-api-00042-def=10
~~~

After observing green and deciding to promote:

~~~bash
gcloud run services update-traffic order-api   --region=asia-southeast1   --to-revisions=order-api-00042-def=100
~~~

Revision names are examples only. Retrieve actual names from deploy output or revision listings. You can assign tags to revisions to test via dedicated URLs before shifting live traffic.

### Configuration and Service Identity

Each revision can have environment variables, secret references, a service account, concurrency, and resource settings. Compare these settings before cutover:

- Does the runtime service account have the right permissions?
- Are secret versions available and active?
- Do VPC egress, ingress, and network routes match requirements?
- Are CPU, memory, timeout, and concurrency appropriate?
- Are min/max instances and startup probes configured properly?

A new revision whose code runs but uses the wrong service account or secret version is still a broken release.

## 7. Blue-Green for Azure Functions and Platforms with Deployment Slots

Some Azure App Service/Azure Functions hosting plans support deployment slots. A staging slot can be deployed and tested before swapping with the production slot. Slot availability depends on the hosting plan and app type; do not assume every plan includes this feature.

On platforms with slot swaps:

1. Deploy the new artifact to the staging slot.
2. Configure proper slot-specific settings and secret references.
3. Test the staging URL.
4. Warm up instances and verify dependencies.
5. Swap staging with production.
6. Monitor production metrics.
7. Swap back if rollback is needed.

Check which settings are marked slot-sticky and which move with the deployment. If connection strings or secrets swap incorrectly, code may run against the wrong data environment.

Other platforms may offer traffic splits, deployment slots, or revision routing under different names. Use the equivalent stable endpoint mechanism and verify the provider's exact semantics.

## 8. Blue-Green for Event-Driven Functions

Functions processing messages or events differ from HTTP APIs. There is no simple router that percentage-splits requests without affecting checkpoints, retries, and ordering.

For example, two Lambda event source mappings reading the same stream or queue may both receive a record. Two independent consumers can maintain separate checkpoints and execute duplicate side effects. Thus, turning on a green consumer alongside blue is not equivalent to an HTTP canary.

### Safer Deployment Approaches

**Approach 1: Switch consumers at a single coordination point**

- Deploy green with triggers disabled or not yet permitted to receive messages.
- Verify the function using test events or replayed data in an isolated environment.
- Stop or disable the blue consumer per procedure.
- Enable the green consumer.
- Monitor lag, errors, retries, and DLQs.
- On rollback, return processing to blue after accounting for in-flight messages.

This yields a clean cutover, though in-flight messages and visibility/lease timeouts must be accounted for.

**Approach 2: Side-effect-free shadow consumer**

Green reads copies or replayed events but only validates and computes results—without sending emails, charging money, writing business state, or calling side-effecting APIs. Compare outputs against blue. Only switch the real consumer once green passes criteria.

**Approach 3: Controlled router or dispatcher**

A single dispatcher receives messages and decides whether to route to blue or green by tenant, partition key, or release cohort. The dispatcher must preserve ordering if required by business logic, and downstream steps must remain idempotent.

Do not let both consumers process live production messages simultaneously just to test 10% traffic. If splitting is required, explicitly define partitioning, checkpoint, retry, and side-effect semantics.

## 9. Idempotency and Duplicates During Version Transitions

In serverless, messages/events typically have at-least-once delivery semantics. Retries, timeouts, or cutovers can redeliver the same event. Blue and green could both see an event if the pipeline is misconfigured.

Use stable idempotency keys:

- Producer-generated event ID.
- Message ID or stream sequence key combined with source.
- Business operation ID such as paymentId or orderVersion.

Deduplication table example:

~~~sql
CREATE TABLE processed_events (
    event_id VARCHAR(128) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL,
    release_id VARCHAR(128)
);
~~~

When processing an event, write the idempotency marker and business update within the same transaction if using the same database. If the event has already been processed, the consumer skips repeating side effects.

Never use release ID as the idempotency key, because blue and green would generate different keys for the same event. Release ID is only useful for tracing/auditing.

### Side Effects Outside the Database

If a function sends emails, processes payments, or calls partner APIs, database transactions cannot wrap every side effect. Use the outbox pattern, provider idempotency keys, or workflow state machines to manage state. When rolling back code, never assume already-sent emails or payments vanish automatically.

## 10. Database Migrations Must Be Two-Version Compatible

This is the most important condition for safe blue-green rollbacks. While blue and green coexist, both may access the same database. If green alters the schema in a way blue cannot understand, rolling back to blue will break the old application.

Use the **expand-contract** strategy:

1. **Expand:** add new tables/columns/indexes while old code keeps working.
2. **Deploy compatible code:** new code can read both old and new schemas.
3. **Backfill:** migrate data in resumable batches.
4. **Switch:** shift traffic to green and verify.
5. **Contract:** drop old columns or structures only after blue is no longer needed and the rollback window has closed.

Example:

- Release A reads the full_name column.
- Expand migration adds first_name and last_name.
- Release B writes both full_name and the two new columns, or uses controlled dual-read/dual-write.
- Backfill historical data.
- Switch traffic to B.
- After a safe period, a subsequent release stops using full_name and drops the column.

Never perform destructive migrations right before switching traffic. Application rollback cannot restore dropped schemas or data without a backup/restore plan.

### API and Event Schema Compatibility

Like databases, event schemas must stay backward-compatible while old and new consumers coexist. Adding optional fields is generally easier than changing semantics or deleting required fields. Use schema versions and safe producer/consumer rollout ordering.

## 11. State, Sessions, and Caches in Blue-Green

Never store critical state solely in blue or green memory. The two versions can run on separate instances without sharing a heap.

Issues to check:

- In-memory sessions may be lost when traffic switches to green.
- Blue and green caches may expect different formats.
- Static singletons may hold stale configuration.
- Tokens or credentials may be cached per revision.
- Scheduled tasks may run simultaneously on both sides.
- WebSockets or long-lived connections may stay pinned to the old version.

Solutions:

- Store sessions in shared stores or use stateless tokens with appropriate lifetimes.
- Caches must include versions, TTLs, and invalidation.
- Design cache keys compatible across versions or use namespaces with a migration plan.
- Store workflow state in databases/queues/state stores.
- Use leader leases or scheduler locks so only one version runs exclusive jobs.
- Handle in-flight requests and long connections per drain policies.

If cache formats change, use versioned keys or dual-reads during the transition. Avoid blindly flushing the entire cache if that could trigger a cache stampede onto the database.

## 12. Scheduled Functions, Cron, and Exclusive Jobs

A scheduled function can be deployed in both blue and green. If both schedulers fire simultaneously, a job can execute twice.

Before cutover:

- Enable the schedule on only one side.
- Or use a distributed lock/lease with an owner and expiration.
- Attach an idempotency key to each scheduled run, such as job name + scheduled timestamp.
- Ensure jobs can resume or rerun safely.
- On rollback, check active leases and running invocations before re-enabling the old scheduler.

Never use a Java static boolean to lock a job system-wide. Static variables are scoped to a single process and do not coordinate across instances.

For cloud-provider-managed cron jobs, verify which revision/alias the trigger targets. Shifting HTTP traffic does not automatically switch schedulers or event source mappings.

## 13. Secrets, Environments, and IAM During Transitions

Blue and green can run concurrently during rollout. Both need valid permissions and settings throughout this window.

Checklist:

- New secrets are created and permissions granted before deploying green.
- Green's runtime identity holds only required permissions.
- Credential rotation includes an overlap window if blue still needs old secrets.
- Config schemas are compatible with both revisions.
- Network egress, VPC connectors, and firewall rules are not unexpectedly altered.
- IAM permissions are not revoked prematurely.
- After promoting green, verify old permissions can be narrowed once blue stops running.

Do not delete blue's secrets or revoke its IAM permissions immediately after shifting traffic if in-flight invocations, rollback windows, or background tasks remain. Yet do not leave old permissions around indefinitely; schedule explicit cleanup.

## 14. Readiness, Warm-Up, and Cold Starts

Green must be verified before taking live traffic. Readiness is more than the process running.

A good readiness check can verify:

- The runtime has initialized.
- Required configuration is valid.
- Critical dependencies are reachable within timeout.
- Database schemas are compatible.
- Secrets are accessible.
- The function can handle a test request.

Do not make health endpoints overly heavy or dependent on every optional service. Distinguish liveness (process is alive) from readiness (eligible to receive traffic).

With Java, cold starts can rise due to JVM startup, class loading, dependency injection, frameworks, and connection pools. Warm-up must be controlled so it does not generate real business requests or overload dependencies. If the platform offers minimum instances, provisioned concurrency, or snapshot/restore, weigh them against latency targets and cost.

Warm-up does not replace cold-start testing. Measure both the first request on a fresh instance and steady-state latency.

## 15. Observability and Traffic-Shifting Criteria

Define criteria before starting rollout. Never decide based on intuition or a single successful call.

Metrics to compare per release/revision:

- Request counts and 4xx/5xx rates.
- p50, p95, and p99 latency.
- Cold start/startup latency.
- CPU, memory, and concurrency.
- Timeouts, throttling, and retries.
- Database connections, query latency, and error rates.
- Queue age, event lag, and DLQ counts.
- Business success rates, such as successful order creation rate.
- Cost per request or per job.

Illustrative policy example:

| Phase | Green Traffic | Criteria |
|---|---:|---|
| Smoke test | 0% production | Dedicated endpoint, auth, dependencies, and contracts |
| Canary 1 | 5% | No spike in severe errors; observe sufficient requests |
| Canary 2 | 25% | Latency and business metrics within thresholds |
| Canary 3 | 50% | No regressions by tenant/region |
| Promote | 100% | Observation window met and rollback plan still viable |

Percentages and thresholds must reflect system traffic, SLAs, and baselines. Under low traffic, 5% might be only a handful of requests and insufficient to draw conclusions.

### Correlation and Release Metadata

Logs and traces should include the release ID or revision. When a request fails, you must know whether blue or green handled it. Avoid using release ID as a metric label if it creates excessive cardinality; use bounded dimensions or logs/tracing instead.

## 16. Rollback Plan

A rollback plan must be prepared before deployment. At minimum, define:

- Is the blue version still active and able to receive traffic?
- How quickly can the alias/router switch back?
- Is the database schema still compatible with blue?
- Are blue's configs and secrets still valid?
- Which queue consumer currently owns messages?
- Did green execute any irreversible side effects?
- Who is authorized to roll back and what is the trigger procedure?
- Which metrics trigger automatic or manual rollback?

### When to Roll Back?

Example triggers:

- 5xx rate breaches threshold over a sustained window.
- p95/p99 spikes sharply over baseline.
- Function timeouts or throttling rise.
- Database connection pools exhaust or query errors climb.
- Business success rate drops.
- Security check or authorization regression occurs.
- Queue age/DLQ exceeds thresholds.

Do not roll back over a brief small-sample spike without analysis, yet do not keep green live simply to avoid marking a release failed. For security bugs or data leaks, halt traffic immediately and run incident response.

### Rollback Is Not Data Rollback

Pointing the alias back to blue only changes which code runs. If green wrote data under new semantics, run compatible migrations or targeted remediation. Avoid automatically running reverse migrations that could destroy valid data.

## 17. Reference CI/CD Pipeline

A blue-green pipeline for a Java API can include:

~~~mermaid
flowchart TD
    Commit[Commit / Pull request]
    Build[Compile and package]
    Test[Unit, integration, contract tests]
    Scan[Dependency and security scan]
    Publish[Publish immutable artifact]
    Deploy[Deploy green revision]
    Verify[Smoke and readiness checks]
    Canary[Shift small traffic]
    Monitor[Compare release metrics]
    Promote[Promote green to 100%]
    Rollback[Route traffic back to blue]

    Commit --> Build --> Test --> Scan --> Publish
    Publish --> Deploy --> Verify
    Verify -->|Fail| Rollback
    Verify -->|Pass| Canary --> Monitor
    Monitor -->|Healthy| Promote
    Monitor -->|Regression| Rollback
~~~

The pipeline should automate repeatable steps, while production promotion relies on defined criteria. For sensitive systems, require approval before shifting 100% of traffic.

### Artifacts to Retain

- JAR/container image digest.
- Git commit and build provenance.
- Release manifest.
- Test and scan reports.
- Blue and green version/revision IDs.
- Database migration version.
- Config revision and secret reference version.
- Traffic change records.
- Smoke test results and metric snapshots.
- Rollback actions/audit logs.

Never store plaintext secrets in artifacts or pipeline logs.

## 18. Testing Blue-Green

Tests must cover both routing and post-cutover behavior:

| Scenario | Expected Outcome |
|---|---|
| Successful green deploy | New revision/version is ready |
| Green missing secret or IAM | Smoke test fails, traffic is not shifted |
| Green schema incompatibility | Pipeline blocks promotion |
| 5% traffic to green | Metrics distinguish blue and green |
| Green 5xx spike | Router can revert to blue |
| Rollback after database expand | Blue still reads/writes compatible schema |
| Duplicate event source mapping enabled | Test catches duplicate consumer/side effect |
| Message retried during cutover | Idempotency prevents duplicate processing |
| Scheduled job runs on both revisions | Lock/idempotency prevents double execution |
| Cache format changes | Blue and green read data cleanly during overlap |
| Long-running in-flight request | Drain/timeout policy prevents lost results |
| IAM/secret rotation | Both versions operate cleanly during overlap window |
| Code rollback | Does not automatically revert data or cause unintended side effects |

Test rollback in staging or a production-equivalent environment. A release pipeline that has never tested rollback proves only that deployment works, not that the system can recover.

## 19. Common Deployment Mistakes

- **Deploying green and switching traffic immediately:** skips smoke tests and observation; validate green first.
- **Not keeping blue active:** loses fast rollback; maintain blue throughout the rollback window.
- **Using mutable artifacts:** impossible to tell which exact version is running; use immutable digests/versions.
- **Rolling back code only:** schema or side-effect changes can break blue; use expand-contract.
- **Enabling two stream consumers simultaneously:** risks duplicate event processing; enforce a single consumer owner or design a side-effect-free shadow.
- **Splitting event traffic like HTTP:** ignores checkpoints and ordering; use proper cutover/dispatchers.
- **Lacking idempotency:** retries and duplicates trigger repeated side effects.
- **Running two schedulers together:** jobs execute twice; use leases or a single schedule owner.
- **Deleting old secrets/IAM too early:** breaks in-flight invocations or rollbacks; maintain overlap and cleanup windows.
- **Not distinguishing metrics by revision:** hard to tell which version failed; attach release metadata.
- **Canary too small or too brief:** insufficient data to evaluate; size samples and duration to traffic.
- **Trusting simple health checks:** process liveness does not prove business logic works; run smoke/contract tests.
- **Holding caches/sessions in memory:** cutover loses or diverges state; use shared stores and versioned caches.
- **Never testing rollback:** recovery procedures may fail right in the middle of an incident.

## 20. Blue-Green Process for Java Serverless

Use the following sequence for a release:

1. Build an immutable artifact and attach commit/release IDs.
2. Run unit, integration, contract, security, and dependency tests.
3. Verify database migrations follow the expand-contract strategy.
4. Create the config revision and secret references needed for green.
5. Deploy green without receiving production traffic.
6. Verify runtime, IAM, networking, databases, and dependencies.
7. Run smoke tests and safe synthetic transactions.
8. Shift a fraction of traffic if supported by the platform; otherwise prepare full cutover.
9. Compare latency, error rates, business metrics, and dependencies by revision.
10. Promote green once predefined criteria are met.
11. Retain blue and the rollback window for the prescribed period.
12. After the rollback window closes, clean up old versions, secrets, and unneeded permissions.
13. Execute contract migrations only when no old code depends on the old schema.
14. Record release outcomes and rollback evidence in the audit trail.

For event-driven functions, add steps to verify consumer ownership, checkpoints, retries, DLQs, idempotency, and handling of in-flight messages before switching triggers.

## 21. Key Takeaways

Blue-green deployment keeps the serving version and the new version side by side during transition, letting you test green before shifting traffic and revert to blue quickly upon regression. For HTTP APIs, stable URLs, aliases, or revision traffic splits orchestrate requests. For event-driven functions, checkpoints, retries, ordering, and duplicates require dedicated handling; running two consumers simultaneously can cause repeated side effects.

Rollback is only safe when database schemas, event contracts, configs, secrets, and state are compatible with both versions. Use expand-contract migrations, idempotency, shared state stores, and scheduler locks for coordinated components.

Define smoke test, canary, promotion, and rollback criteria upfront; monitor metrics per release; keep artifacts immutable; and test rollback before production. Serverless reduces compute management, yet release workflows must still control traffic, data, and side effects to guarantee recovery when a new version fails.
