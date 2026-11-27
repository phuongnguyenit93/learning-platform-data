# Running Smoke Tests for Critical Flows

After a pipeline deploys a new version, a successful deploy status only indicates that the platform executed the requested deployment steps. It does not prove users can log in, create orders, pay, read data, or complete a critical business flow.

A **smoke test** is a small, fast post-deployment check suite that confirms essential functionality still works in the target environment. Smoke tests typically traverse key integration points and verify observable outcomes, helping catch configuration, connectivity, routing, permission, or compatibility errors before expanding traffic or closing a release.

Within the **DEVOPS_CI_CD_FUNDAMENTALS** competency, smoke testing bridges deployment and post-deployment validation. It ensures the CI/CD flow does not merely build and ship artifacts to an environment, but also produces evidence that the deployed version can execute critical flows.

## 1. Purpose and Scope of Smoke Tests

Smoke tests answer the question: are the minimum functions needed for the system to serve users working?

A good smoke test typically:

- Runs quickly and produces clear results.
- Tests flows with high impact on users or business operations.
- Exercises essential dependencies such as databases, caches, brokers, or authentication services.
- Verifies meaningful business outcomes rather than merely checking that a process is running.
- Uses controlled test data that can be cleaned up.
- Has timeouts, logs, and correlation IDs for investigation.
- Has pass/fail criteria clear enough for the pipeline to decide whether to continue, stop, or roll back.

Smoke tests do not replace unit tests, integration tests, regression tests, performance tests, security tests, or exploratory tests. Those tests have different goals and depths. A smoke test is just a brief verification layer after a version has been deployed.

Example for an ordering service:

| Check level | Question | Example |
| --- | --- | --- |
| Process/health | Is the application running? | Process alive, liveness endpoint returns a result |
| Readiness | Can the instance accept requests? | Required config and dependencies are ready |
| Smoke test | Do critical flows work? | Read catalog, create test order, view order status |
| Regression | Do existing behaviors still hold broadly? | Many business, boundary, and error cases |
| Performance | Does the system handle load as expected? | Load testing, latency, and throughput |

A single request to a health endpoint should not be called a complete smoke test if the primary business flow has not been tested.

## 2. Selecting Critical Flows to Test

You do not need to run the entire test suite after every deploy. Choose a handful of flows representative of core serving capability, based on the impact if a flow breaks.

Questions to help select flows:

- What does a user need to do first to use the product?
- Which actions generate primary value or revenue?
- Which component, if broken, would render many features unusable?
- Which flows changed in this release?
- Which dependencies or configurations carry high risk in this deployment?
- Are there operations with irreversible side effects that require a sandbox or simulated data?

Examples:

| System type | Candidate smoke test flows |
| --- | --- |
| E-commerce | Open product page, read price/inventory, create test order, read order status |
| Banking or payments | Authenticate test user, query simulated balance, create sandbox transaction and read result |
| Multi-tenant SaaS | Sign in, load dashboard, read correct tenant data, verify access permissions |
| Digital content | Open page, load content, search, and verify access rights |
| API platform | Authenticate client, call core endpoint, check schema and dependencies |
| Background processing | Send test message, verify consumer processes it and output appears within deadline |

Choose few flows, but meaningful ones. If you only check the homepage, the system could still fail on sign-in or data writes. If you choose too many flows, smoke tests turn into a slow regression suite that is hard to stabilize and hard to use as a fast decision gate.

### 2.1. Covering Critical Paths

For each flow, define:

1. Initial conditions and test identity.
2. Requests or user actions performed.
3. Required dependencies.
4. Expected business outcome.
5. Data or side effects created.
6. How to verify and clean up.

Example order-creation flow:

~~~mermaid
flowchart TD
    A["Smoke test starts"] --> B["Authenticate test user"]
    B --> C["Read catalog and price"]
    C --> D["Create test order with idempotency key"]
    D --> E["Read back order"]
    E --> F["Verify status and total amount"]
    F --> G["Verify event or background task if needed"]
    G --> H["Clean up test data or mark as test"]
    H --> I["Record result and correlation ID"]
~~~

If a step fails, report exactly which step, endpoint, status code, or assertion failed. Never return just "smoke test failed".

## 3. Verifying the Exact Newly Deployed Version

A smoke test can accidentally send requests to an old version if a load balancer, DNS, ingress, or service discovery has not updated yet. Therefore, you must know the test is verifying the exact expected artifact.

Record and reconcile:

- Release ID or deployment ID.
- Commit SHA.
- Artifact version and digest.
- Environment, namespace, region, or slot.
- Deployment and smoke test start timestamps.
- Version/build metadata exposed by the application.

You can provide a read-only metadata endpoint, such as /version or /build-info, returning commit, build ID, and artifact version. This endpoint must not expose secrets, sensitive environment variables, internal configurations, or information that could aid an attacker.

With rolling or blue-green deployments, identify which instance the smoke test is calling. You can call an internal service directly, use a dedicated route, or inspect response headers/build metadata. After cutover, verify that actual traffic reaches the new version rather than testing only a pod that does not yet receive production requests.

Do not rely solely on mutable tag names. If artifacts are managed by digest, link that digest to the deployment record and smoke test results.

## 4. Distinguishing Health, Readiness, and Smoke Tests

These three check types complement each other:

| Check | Purpose | Example |
| --- | --- | --- |
| Liveness | Detect hung processes or processes needing restart | Process responds to health endpoint |
| Readiness | Determine whether an instance can accept traffic | Required dependencies and config are ready |
| Smoke test | Verify critical flows work from the caller/user perspective | Sign in, read data, create a test transaction |

Liveness should not depend on every external service. If a database slows down temporarily and liveness fails, the orchestrator may restart instances en masse, making matters worse.

Readiness can check essential dependencies, though it does not necessarily run a full business transaction. Smoke tests add that check from outside the application or through an appropriate API.

An application can have green liveness and readiness yet still fail due to wrong routing, certificates, user permissions, response schemas, or a business flow. That is why a separate smoke test is needed.

## 5. Designing Safe Tests for Post-Deployment Environments

Production smoke tests must avoid unintended mutations to real data. Before running, clearly define what the test will read, write, send, or trigger.

### 5.1. Using Dedicated Test Accounts and Data

- Use dedicated test accounts or tenants.
- Mark data created by smoke tests with a dedicated prefix or metadata.
- Avoid using real personal data unless necessary.
- Avoid broad administrative accounts just to test a simple flow.
- Create data with unique identifiers tied to the deployment/run ID.
- Restrict permissions and data scope of the test identity.

If tests must verify access controls, use accounts with predefined roles such as viewer and operator. Never use real user credentials.

### 5.2. Controlling Side Effects

Some operations cannot be easily undone:

- Sending real emails or SMS.
- Processing real payments or refunds.
- Sending webhooks to partners.
- Creating shipping labels or delivery requests.
- Sending notifications to users.
- Triggering heavy workflows or large data-processing jobs.

Prefer sandboxes, provider test modes, fake endpoints, or dry-runs. If a real service must be called, use a specially designed flow with minimal amounts/test identifiers, idempotency, and controlled cancellation/completion steps. Do not let smoke tests accidentally create business transactions.

### 5.3. Idempotency and Re-runnability

Pipelines may retry smoke tests when a runner loses connectivity or times out. If a test creates a new resource each time, a rerun can create duplicate orders, transactions, or messages.

Use an idempotency key tied to a single run or test case. On retry, the same logical operation must not produce additional side effects. If the system does not support idempotency, create resources with unique IDs and check before creating.

Do not reuse a fixed ID across multiple parallel pipelines if data could be overwritten. You can combine deployment ID and test case ID to create a distinct namespace.

### 5.4. Data Cleanup

After testing, delete or mark test data according to policy. Cleanup should run even when assertions fail. If data cannot be deleted for audit reasons, mark the test record and set a clear retention period.

Never allow cleanup to delete real user data. All delete queries must be scoped by test tenant, test marker, or resource identifiers created within that exact run.

## 6. Post-Deployment API Checks

API smoke tests are usually faster and more stable than UI interactions. They can check:

- DNS/TLS and endpoint connectivity.
- HTTP status codes.
- Response schema and required fields.
- Key business content.
- Authentication and authorization.
- Ability to read/write test data.
- Dependencies such as databases, caches, or brokers.

Example readiness endpoint check:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [ -z "$BASE_URL" ]; then
  echo "BASE_URL is required" >&2
  exit 2
fi

status_code=$(curl \
  --silent \
  --show-error \
  --output readiness.json \
  --write-out '%{http_code}' \
  --connect-timeout 3 \
  --max-time 10 \
  "$BASE_URL/ready")

if [ "$status_code" != "200" ]; then
  echo "Readiness check failed: HTTP $status_code" >&2
  cat readiness.json
  exit 1
fi

jq -e '.status == "UP"' readiness.json >/dev/null
echo "Readiness check passed"
~~~

This script assumes the runner has curl and jq, the endpoint returns JSON with status UP, and BASE_URL is supplied from environment configuration. In a real system, adjust the schema to match the API and avoid printing responses if the body could contain sensitive data.

### 6.1. Smoke Test for an API Flow

The example below illustrates checking a catalog and a test order. Endpoints, payloads, and response fields must be replaced with your application's actual contract:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

if [ -z "$BASE_URL" ] || [ -z "$SMOKE_TEST_TOKEN" ] || [ -z "$SMOKE_RUN_ID" ]; then
  echo "Required smoke-test configuration is missing" >&2
  exit 2
fi

curl --fail --silent --show-error \
  --connect-timeout 3 \
  --max-time 10 \
  -H "Authorization: Bearer $SMOKE_TEST_TOKEN" \
  "$BASE_URL/api/catalog/health" \
  -o catalog.json

jq -e '.available == true' catalog.json >/dev/null

idempotency_key="smoke-$SMOKE_RUN_ID-order"
http_code=$(curl \
  --silent \
  --show-error \
  --output order.json \
  --write-out '%{http_code}' \
  --connect-timeout 3 \
  --max-time 15 \
  -X POST \
  -H "Authorization: Bearer $SMOKE_TEST_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $idempotency_key" \
  -d '{"testMode":true,"items":[{"sku":"SMOKE-SKU","quantity":1}]}' \
  "$BASE_URL/api/orders")

if [ "$http_code" != "201" ] && [ "$http_code" != "200" ]; then
  echo "Order smoke test failed: HTTP $http_code" >&2
  exit 1
fi

jq -e '.testMode == true and .status != null and .id != null' order.json >/dev/null
echo "Critical API flow passed"
~~~

The example uses a narrowly scoped test token, test mode, and an idempotency key. A real system needs safeguards ensuring clients cannot abuse testMode to bypass business rules or security permissions. Do not log tokens; the CI platform must mask secrets and scope tokens solely to the smoke test job.

In production, if no safe test mode exists, replace the order creation step with a read flow or an operation specifically designed to produce no side effects. If resources are created, perform scoped cleanup and verify the resources belong to the exact run.

## 7. Checking UI and User Experience

UI smoke tests verify that critical components load and users can complete a basic action. Select only a few stable flows and avoid checking every visual detail.

Example with Playwright:

~~~javascript
import { test, expect } from '@playwright/test';

test('user can view an existing smoke order', async ({ page }) => {
  await page.goto(process.env.BASE_URL + '/orders/smoke-order');

  await expect(
    page.getByRole('heading', { name: 'Order details' })
  ).toBeVisible();

  await expect(
    page.getByTestId('order-status')
  ).toHaveText('CONFIRMED');
});
~~~

This example reads a prepared test order. For login flows, use a dedicated test account and do not store passwords in source code. If a UI smoke test creates data, use dedicated test fixtures and clean up afterward.

UI tests are often sensitive to selector changes, animations, and load times. Prefer stable roles, labels, or test IDs; avoid long fixed sleeps when you can wait for specific conditions. When a UI test fails, save screenshots, traces, and secret-filtered console/network errors to assist investigation.

Do not let a failure in an ad, analytics script, or non-critical third-party widget block a release if it is not part of the essential flow. Clearly define which dependencies are mandatory and which can degrade gracefully.

## 8. Checking Synchronous and Asynchronous Dependencies

A critical flow may traverse multiple systems:

- API gateway or ingress.
- Authentication/identity provider.
- Application service.
- Database.
- Cache.
- Message broker.
- Background worker.
- Third-party service.

Smoke tests should verify dependencies genuinely required by the flow, without turning a single test into a check of every system in the architecture.

For asynchronous processing, HTTP 202 or an "accepted" message only means the request was received. Wait within a bounded window to verify the final outcome appears:

1. Send a test message or request with a correlation ID.
2. Receive an acknowledgment response.
3. Poll status or query results by correlation ID.
4. Stop when the expected result arrives, a failed state occurs, or timeout expires.
5. Record queue lag, retries, and consumer errors if incomplete.

Do not poll indefinitely. Timeouts must be based on the flow's SLA and log how long the wait lasted. If a worker runs on a schedule, you may need a separate smoke test or a safe trigger mechanism.

When a non-essential dependency fails, the application may be designed to degrade gracefully. Smoke tests must verify that expected behavior instead of assuming every auxiliary service must always be up.

## 9. Setting Timeouts, Retries, and Assertions

A reliable smoke test requires time bounds and clear result checks:

- **Connect timeout:** maximum time to establish a connection.
- **Request timeout:** maximum time for a single request.
- **Flow timeout:** total time for the entire flow.
- **Retry:** number of retry attempts when an error is considered transient.
- **Backoff:** pause between attempts to avoid load spikes.
- **Assertion:** specific condition determining a valid outcome.

Do not retry every error. HTTP 401 may indicate wrong credentials; HTTP 403 may indicate wrong permissions; HTTP 404 may indicate a nonexistent route; HTTP 500 may indicate an application bug. Unlimited retries delay detection and can amplify incidents.

You can retry transient connection errors or not-yet-ready states within a short window. When time expires, the test must fail and record sufficient evidence.

Assertions should check:

- Expected HTTP status or protocol result.
- Required response fields and data types.
- Business values, such as order status or total amount.
- Ability to read back written data.
- Application version matching the expected release.
- Absence of critical errors or abnormal states in the flow.

Do not check only for non-empty responses or HTTP 200. An API can return 200 with a payload containing a business error.

## 10. Integrating Smoke Tests into the CI/CD Pipeline

Smoke tests typically run after deployment and before the release is marked complete or traffic is expanded.

General flow:

~~~mermaid
flowchart TD
    A["Build and test"] --> B["Quality gates"]
    B --> C["Deploy identified artifact"]
    C --> D["Wait for rollout and readiness"]
    D --> E["Run smoke tests"]
    E --> F{"All critical flows pass?"}
    F -- "Yes" --> G["Monitor post-deploy metrics"]
    G --> H{"Guardrails pass?"}
    H -- "Yes" --> I["Mark release stable / expand traffic"]
    H -- "No" --> J["Halt rollout or roll back"]
    F -- "No" --> J
    J --> K["Collect logs, report error, and record deployment result"]
~~~

Platform-agnostic pipeline example:

~~~yaml
stages:
  - build
  - test
  - deploy
  - smoke
  - observe

deploy-production:
  stage: deploy
  script:
    - ./scripts/deploy.sh "$ARTIFACT_DIGEST" production

smoke-production:
  stage: smoke
  needs:
    - deploy-production
  script:
    - ./scripts/wait-ready.sh
    - ./scripts/smoke-critical-flows.sh

observe-production:
  stage: observe
  needs:
    - smoke-production
  script:
    - ./scripts/check-release-guardrails.sh
~~~

This is an illustrative configuration; `needs`, `stages`, and run conditions depend on the CI platform. A real pipeline must ensure log collection and reporting steps still run when smoke tests fail, while rollback or rollout halt is triggered according to policy.

### 10.1. Smoke Tests After Blue-Green or Canary

With blue-green:

- Run smoke tests directly against green before cutover.
- Verify artifact digest and build metadata.
- After cutover, run checks through the production route to confirm traffic reaches green.
- Keep blue during the rollback window.

With canary:

- Run smoke tests against the canary before opening traffic.
- After opening a small percentage, verify both synthetic flows and real-traffic metrics.
- Increase percentage only when guardrails pass.
- If smoke tests or metrics fail, halt traffic expansion and take the defined action.

Do not confuse a smoke test on an internal canary endpoint with verifying that real users are actually being routed to the canary. Those two checks serve different goals.

## 11. Evaluating Results and Release Decisions

Smoke test results should have clear statuses:

| Status | Meaning | Action |
| --- | --- | --- |
| PASS | All critical assertions pass | Proceed to observation step or expand release |
| FAIL | One or more critical flows fail | Block release, halt rollout, or roll back per policy |
| INCONCLUSIVE | Insufficient data, test environment failure, or indeterminate timeout | Hold rollout, investigate, and perform a controlled rerun |
| SKIPPED | Test did not run per defined policy | Clearly display reason; do not treat as PASS |

Never turn INCONCLUSIVE into PASS just to keep a pipeline green. If the test endpoint is unreachable due to runner or DNS issues, distinguish a test environment error from an application error. During investigation, keep the release status unverified.

For flows of varying criticality, you can distinguish critical and non-critical. A failing auxiliary widget may raise a warning; failing login or payment may have to block the release. Criteria must be agreed upon before deployment.

## 12. Observing After Smoke Tests

Smoke tests typically generate a very small number of requests. They may miss bugs that only appear under load or over extended periods. Therefore, after smoke tests pass, you still need to observe metrics and logs over an appropriate window.

Monitor:

- Error rate and latency by version.
- Request success rate of critical endpoints.
- Database connections, query latency, and locks.
- Cache hit/miss and connection errors.
- Queue lag, retries, dead-letter count, and processing time.
- Crashes, restarts, CPU, memory, and saturation.
- Business metrics such as successful transactions or completion rates.

Tie results to release ID, artifact digest, environment, and timestamp. Use correlation IDs to link logs across gateway, service, and worker.

Do not log access tokens, passwords, personal data, or sensitive payloads in smoke reports. If saving requests/responses for investigation, filter and mask sensitive fields.

## 13. Handling Smoke Test Failures

When a test fails, avoid rerunning blindly without gathering evidence. A short investigation procedure:

1. Identify the release ID, commit, and artifact digest just deployed.
2. Confirm the test is hitting the right environment and version.
3. Record endpoint, timestamp, status code, assertion, and correlation ID.
4. Inspect application, ingress, database, broker, and relevant dependency logs.
5. Distinguish application bugs, configuration, data, permissions, routing, and runner/test harness issues.
6. Determine impact scope and whether real users have already received the new version.
7. Halt rollout or roll back if defined criteria are violated.
8. After remediation, rerun smoke tests and save the new result.

Do not delete test data or container logs before gathering evidence. Do not retry an operation with side effects without knowing whether the prior request was processed; check the idempotency key or transaction state.

### 13.1. When Should You Roll Back?

Roll back or halt rollout when:

- A critical flow cannot complete.
- Written data is incorrect or cannot be read back.
- Authentication/authorization behaves incorrectly.
- An essential dependency is unreachable.
- There is a severe security bug or data leak.
- Post-deploy metrics exceed SLO/guardrail thresholds.

For minor bugs with a workaround that do not affect critical flows, you may keep the release in a warning state while investigating, if policy allows. The decision must be based on actual impact and agreed criteria, not on a desire to keep the pipeline green.

Rolling back a binary does not automatically reverse database migrations, published messages, or completed transactions. Coordinate with data compatibility and business recovery strategies.

## 14. Example UI Smoke Test with Playwright in a Pipeline

A minimal UI test can run post-deploy using a base URL supplied by the environment:

~~~javascript
import { test, expect } from '@playwright/test';

test('critical customer journey is available', async ({ page }) => {
  const baseUrl = process.env.BASE_URL;
  if (!baseUrl) {
    throw new Error('BASE_URL is required');
  }

  await page.goto(baseUrl + '/login');
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible();
  await expect(page.getByLabel('Email')).toBeVisible();
  await expect(page.getByLabel('Password')).toBeVisible();
});
~~~

This example only verifies the login page loads and essential fields appear. A smoke test for an authenticated flow must fetch credentials from a secret store, sign in with a test account, verify key actions, and clean up created data. Never hardcode credentials in test files.

Keep UI tests few in number because browser tests can be slow and sensitive to UI changes. You can use API smoke tests for dependencies and business assertions, then keep one short UI test to verify the core user experience.

## 15. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking only that the deployment job succeeded | No idea if the app can serve users | Run smoke tests after readiness |
| Calling only the liveness endpoint | Dependencies or business flows may still fail | Test critical journeys |
| Testing too many cases | Smoke suite becomes slow and flaky | Keep scope small; run regression suite separately |
| Checking only HTTP 200 | Payload may contain a business error | Assert schema and business values |
| Using real production data | Causes data mutation or side effects | Use dedicated test identities and fixtures |
| No idempotency | Retries create duplicate transactions or resources | Use idempotency keys and check state |
| No timeouts | Pipeline hangs when dependencies fail | Set connect/request/flow timeouts |
| Unlimited retries | Prolongs incidents and adds load | Finite retries, backoff, and error classification |
| Test does not verify version | May test old instances by mistake | Reconcile build metadata/digest |
| Unscoped cleanup deletes data | May delete real user data | Clean up only resources created by the test |
| Treating skipped tests as pass | Release lacks evidence | Use a distinct SKIPPED status |
| Not collecting logs on failure | Hard to investigate and reproduce | Save filtered reports, traces, and correlation IDs |

## 16. Post-Deployment Smoke Test Checklist

**Before running**

- [ ] Critical flows selected based on user/business impact.
- [ ] Environment, release ID, commit, and artifact digest identified.
- [ ] Deployment complete and instances pass readiness.
- [ ] Test accounts, short-lived tokens, and test data prepared.
- [ ] Side effects disabled, mocked, or safely bounded.
- [ ] Idempotency and cleanup in place for write operations.

**During execution**

- [ ] Timeouts set for connect, request, and overall flow.
- [ ] Assertions verify business outcomes, not just HTTP status.
- [ ] Synchronous/asynchronous dependencies verified within time bounds.
- [ ] Logs and correlation IDs saved without leaking secrets/PII.
- [ ] PASS, FAIL, INCONCLUSIVE, or SKIPPED outcomes clearly distinguished.

**After running**

- [ ] Test data cleaned up or marked per policy.
- [ ] Results linked to release and artifact digest.
- [ ] Post-deploy metrics monitored by version.
- [ ] Clear conditions defined to halt rollout and roll back.
- [ ] On failure, evidence preserved before cleanup.
- [ ] Release marked stable only when sufficient evidence meets policy.

## Conclusion

Post-deployment smoke tests verify whether essential flows work on the version just shipped to the target environment. A useful suite should be small, fast, include business assertions, verify the exact artifact/version, use safe data, control side effects, and enforce clear timeouts.

Smoke test results should be linked to the release ID and artifact digest, then combined with metrics/logs over an observation window. If a critical flow fails, the pipeline must block expansion, preserve evidence, and trigger an investigation or rollback per policy. In this way, CI/CD validates deployment outcomes via real behavior rather than relying solely on deploy tool status.
