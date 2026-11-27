# Phased Rollout, Incident Monitoring, and Rollback Planning

Upgrading Spring Authorization Server is a change to a central security component. A new release can alter how clients are authenticated, tokens are issued, authorization codes are processed, consents are read, JWKS is published, or the database is accessed. Rolling out all at once without compatibility verification can disrupt logins, token issuance, and token validation across many applications simultaneously.

Phased rollout limits blast radius, catches failures through operational signals, and expands traffic only once the new version operates stably. A rollback plan must be prepared in advance, covering code, schemas, configuration, signing keys, and OAuth/OIDC state generated during the rollout.

This lesson explains how to plan an upgrade, execute canary or blue-green rollouts, monitor incidents, and roll back to a stable version for a running Spring Authorization Server system.

## 1. Defining the Scope of Change Before Deployment

Not all changes carry the same risk or the same rollback path. Before selecting a rollout strategy, classify the changes and identify which components may be affected.

| Change Group | Examples | Risks to Evaluate |
|---|---|---|
| Application | Upgrading Spring Boot, Spring Security, or Spring Authorization Server | API changes, filter chains, converters, or different token behavior |
| Database | Adding columns, tables, indexes, or changing authorization storage | Old and new versions may read/write incompatibly |
| Client registration | Changing metadata, auth methods, redirect URIs, or policies | Existing clients fail to authenticate or exchange codes for tokens |
| Tokens | Changing claims, audience, TTL, format, or customizers | Resource Servers and clients fail to process new tokens |
| Signing keys | Rotating signing keys, changing algorithms, or KMS | Old JWTs fail verification if public keys are removed early |
| Issuer and endpoints | Changing domain, issuer, or proxy routes | Clients reject tokens due to issuer mismatch; inconsistent discovery |
| Session and authorization state | Changing session store, serialization, or repositories | Users lose sessions; authorization codes, consents, or PAR requests are lost |
| Infrastructure | Changing ingress, TLS, DNS, service mesh, or network policies | Endpoints unreachable, mTLS or forwarded headers misconfigured |

Build a concrete list of affected flows. For an Authorization Server, at minimum consider:

- OIDC Discovery and JWKS.
- Authorization Code Flow, including PKCE.
- Token endpoint and refresh tokens.
- Client authentication at token/PAR endpoints.
- UserInfo and consent.
- Revocation and introspection if implemented.
- Dynamic Client Registration and Pushed Authorization Requests if enabled.
- Login sessions and shared authorization stores.
- Resource servers verifying JWTs issued by the Authorization Server.

If a change only affects a subset of flows, the canary should target those flows specifically. If changing the issuer, signing keys, or authorization schema, the test scope must be broader because many clients and resource servers can be affected.

## 2. Preparing Before Rollout

### 2.1. Locking Down Versions and Compatibility Conditions

Record the currently running versions and planned target versions:

- Java runtime.
- Spring Boot.
- Spring Security.
- Spring Authorization Server.
- JDBC driver, database, and migration tool.
- Redis/Spring Session if used.
- JWT/JWK libraries and KMS integration libraries.
- Container base image and Kubernetes version if relevant changes apply.

Read the release notes and migration guides for the relevant versions. Check deprecated or removed APIs, default behavior changes, security chains, token settings, endpoint settings, and data serialization formats.

Do not upgrade multiple platform layers at once without a clear reason. For instance, upgrading Java, Spring Boot, Spring Security, the database, and the token schema simultaneously makes root-cause analysis difficult if the rollout fails. Split changes into independently verifiable steps whenever deployment constraints allow.

### 2.2. Capturing a Baseline from the Current Version

Before releasing, collect baseline data to understand how the system behaves normally.

Metrics to capture:

- Request success rate and HTTP 5xx rate per endpoint.
- OAuth error rates such as `invalid_client`, `invalid_grant`, `invalid_scope`, `invalid_request`, and token errors.
- p50, p95, and p99 latency for `/oauth2/authorize`, `/oauth2/token`, UserInfo, PAR, and discovery.
- Token issuance, refresh, and revocation rates.
- Database connections, connection pool usage, transaction timeouts, and deadlocks.
- Session store, cache hit/miss rates, and read/write errors.
- Ready pod count, restarts, CPU, memory, and startup time.
- JWT verification failures at resource servers, if telemetry from that side is available.

Distinguish pre-existing errors from newly introduced errors. Without a recorded baseline, it is difficult to conclude whether the new version increased error rates or merely surfaced an existing issue.

### 2.3. Identifying Owners and Communication Channels

An Authorization Server deployment often involves application, platform, security, database teams, and owners of critical clients. Before starting, identify:

- Rollout coordinator and who holds authority to halt deployment.
- Person monitoring dashboards and logs.
- Database migration owner.
- Signing key/KMS owner.
- Contacts for resource servers or clients that may require coordination.
- Incident notification channel and how deployment status updates are posted.

Prepare dashboard links, log queries, deployment revisions, image digests, commit SHAs, migration versions, and runbooks in advance. Do not leave on-call responders searching for these details during an active outage.

### 2.4. Preparing Artifacts and Restore Points

Before rollout, record:

- Image digest of the currently stable version.
- Image digest and commit of the new version.
- Currently running deployment configuration.
- Reviewed new configuration.
- Current database migration version.
- Backups or snapshots per database policy.
- Secret references, certificates, and active key IDs.
- List of feature flags or toggleable settings.

Prefer identifying images by digest to prevent tags from mutating after deployment. Confirm the old image remains stored in the registry and can be pulled if rollback is needed.

Database snapshots provide an extra safety layer. They do not replace backward-compatible migration design, because restoring a snapshot can lose authorizations, refresh tokens, consents, or client registrations created after the snapshot timestamp.

## 3. Designing a Phased Rollout

Phased rollout means limiting the amount of traffic or number of instances running the new version, observing the results, and only then expanding.

A reference sequence:

~~~mermaid
flowchart TD
    A[Prepare artifacts and baseline] --> B[Verify in staging]
    B --> C[Deploy one replica or canary group]
    C --> D{Health and OAuth/OIDC flows pass?}
    D -- No --> E[Halt rollout and triage incident]
    E --> F{Is rollback safe?}
    F -- Yes --> G[Revert to stable version]
    F -- No --> H[Hold traffic at safe level and forward-fix]
    D -- Yes --> I[Expand canary]
    I --> J[Observe stability windows]
    J --> K{Metrics and business flows stable?}
    K -- No --> E
    K -- Yes --> L[Full rollout]
    L --> M[Post-deployment monitoring]
    M --> N[Close rollout and record outcomes]
~~~

Each stage should have concrete go and no-go criteria. Do not use generic criteria such as "pods are green" to decide expansion, because readiness only reflects ability to receive traffic at probe time; it does not prove token issuance flows and client compatibility are working.

### 3.1. Stage 0: Staging Verification

Staging should mirror production in database version, repository type, session store, signing key integration, ingress, and TLS configuration. Use dedicated staging keys and credentials.

At minimum, perform:

1. Start the new version against the migrated schema.
2. Check health, readiness, and startup.
3. Fetch OIDC Discovery and JWKS.
4. Run Authorization Code flow with PKCE.
5. Exchange the authorization code for tokens.
6. Use refresh tokens and test rotation/reuse policies if enabled.
7. Call UserInfo and verify the `sub` claim.
8. Test client authentication.
9. Test revocation/introspection if supported.
10. Test graceful shutdown and restart.
11. Test rolling back the application to the previous version against the new schema.
12. Verify resource servers still validate tokens issued both before and after the upgrade.

A successful staging run does not guarantee production success, but it eliminates reproducible configuration and compatibility defects.

### 3.2. Stage 1: Canary Deployment

Canary shifts a small subset of instances or traffic to the new version. With multi-replica systems, you can spin up a new pod group, a separate deployment, or use ingress/service mesh traffic splitting.

Canaries should be constrained by one or more criteria:

- A single new replica in the cluster.
- A small percentage of traffic.
- A group of internal or pilot clients.
- A selected region or tenant.
- A low-risk endpoint set before opening critical token issuance flows.

For an Authorization Server, random percentage traffic splitting alone may not suffice. An authorization flow typically consists of multiple sequential requests: authorize, login, consent, token. If requests scatter across old and new versions, both versions must be compatible with shared session and authorization state.

If that is not yet guaranteed, start with a group of pilot clients that can be routed deterministically, or deploy the canary before routing real user flows. Avoid creating an authorization code on the new version whose state cannot be read by the old version's token endpoint.

### 3.3. Stage 2: Stepped Expansion

Once the canary is stable, gradually increase traffic or replica counts. Each step needs an observation window long enough to cover realistic usage cycles.

An example plan might use steps of 1 replica, 5%, 20%, 50%, then 100%. These are only examples; appropriate counts and percentages depend on traffic volume, replica count, routing capability, and risk level.

At each step:

- Check health and readiness.
- Compare error rates against baseline.
- Check latency and saturation.
- Run synthetic authorization flows.
- Inspect OAuth error logs.
- Check database, cache, session store, and KMS connectivity.
- Confirm resource servers continue verifying tokens.
- Record the decision to proceed, hold, or roll back.

Do not increase traffic merely because a timer elapsed. Expand only when observed data satisfies agreed criteria.

### 3.4. Stage 3: Completion and Observation Window

Once all instances are on the new version:

- Confirm all pods are ready and no old replicas remain.
- Verify deployment revision and image digest.
- Verify migration version.
- Re-run critical OAuth/OIDC flows.
- Monitor for a sufficiently long post-deployment window.
- Retain artifacts, logs, metrics, and configs for both versions until the defined rollback window closes.
- Remove old resources only after no dependencies remain and rollout closure is approved.

Do not remove old signing keys, session compatibility, or old schemas immediately after the last pod is replaced. Data created before rollout may still be valid afterward.

## 4. Choosing Rolling, Canary, or Blue-Green Strategy

| Strategy | How It Works | Advantages | Risks and Prerequisites |
|---|---|---|---|
| Rolling update | Replaces instance groups within the same deployment | Easy to operate, leverages orchestration mechanisms | Both versions run concurrently; requires compatible schemas and state |
| Canary | Shifts a slice of traffic to the new version | Limits blast radius, direct comparison | Requires traffic routing and telemetry by version/client |
| Blue-green | Runs two separate environments, switches traffic via router | Clear cutover point, fast rollback at routing layer | Resource-heavy; state/database/keys are still shared or must synchronize |
| Shadow traffic | Mirrors requests to evaluate new version without returning responses to users | Can test behavior and load | Must not trigger side effects or unintended business writes |

### 4.1. Rolling Update

A Kubernetes Deployment can configure a RollingUpdate strategy:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authorization-server
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 15
  progressDeadlineSeconds: 600
~~~

`maxSurge` limits how many pods can be created above the desired replica count during updates. `maxUnavailable` limits how many replicas may be unavailable. Setting `maxUnavailable` to 0 requires maintaining full desired ready replicas during rollout while having enough cluster resources to schedule new pods.

These settings do not replace readiness probes. If readiness always returns success even when the database or signing keys are not ready, Kubernetes can still add new pods to the Service too early.

### 4.2. Canary

Canary fits when observing a small group of clients or live traffic. Label metrics and logs with versions for comparison.

Example analysis dimensions:

- `service.version`.
- `deployment.environment`.
- `oauth.client_id` in a form safe under logging policy.
- Endpoint or grant type.
- Region/tenant if permitted.
- Success/failure outcome and OAuth error type.

Never attach access tokens, refresh tokens, authorization codes, or client secrets as metric labels. Avoid high-cardinality client IDs as metric labels if the system has tens of thousands of clients; group by client class or allowlist key clients instead.

### 4.3. Blue-Green

Blue-green creates two application environments—for example, blue as current and green as new. After green passes checks, the load balancer shifts traffic to green. If problems occur, traffic can shift back to blue.

For an Authorization Server, fast traffic switching does not automatically make data compatible. Both blue and green must understand the same:

- Database schema during the transition window.
- Existing authorization codes and refresh tokens.
- Sessions created by the other environment.
- Client registrations and consents.
- PAR requests if unexpired requests exist.
- Signing keys and JWKS.
- Issuer and public endpoints.

If green issues tokens in a format blue cannot verify, switching traffic back to blue can break clients and resource servers. Design tokens and key rotation so both versions can verify them during the rollback window.

## 5. Maintaining Data Compatibility During Upgrades

### 5.1. Expand-Contract Database Migrations

During rolling/canary deployments, old and new versions may read/write the database concurrently. Therefore, migrations must remain compatible with both.

The expand-contract workflow:

1. **Expand:** add new structures that the old version can safely ignore.
2. **Deploy compatible:** release a version capable of reading both old and new schemas.
3. **Backfill:** migrate data in batches with checkpoints and resumability.
4. **Switch:** switch the application to use the new field/structure.
5. **Contract:** drop old structures only after no version or consumer depends on them.

Example:

- Release A adds a nullable `subject_key` column while still reading `user_id`.
- Release B writes both `user_id` and `subject_key`, and can read either.
- A backfill job populates `subject_key` for existing rows.
- Release C reads `subject_key` as primary while keeping a fallback during the compatibility window.
- Release D drops `user_id` only after confirming no consumer needs it.

This is a conceptual example. For Spring Authorization Server's authorization schema, inspect the actual SQL schema and converters before making changes. Never add or drop columns in framework tables without understanding how serializers/repositories use them.

### 5.2. Do Not Run Destructive Migrations During Pod Startup

If every replica runs migrations on startup, multiple pods can contend for locks or alter the schema while old instances are still serving requests.

Prefer a controlled migration step:

- Run a dedicated migration job before application rollout.
- Use locking to prevent concurrent migration jobs.
- Record the migration version.
- Verify results and execution duration.
- Halt rollout if migration fails or exceeds its time threshold.

Expand migrations can usually run before deploying new code. Contract migrations should run in a later release after old versions are gone and the rollback window has ended.

### 5.3. Keeping Authorization State Compatible

An Authorization Server stores state with distinct lifecycles:

- Authorization codes.
- Access tokens and refresh tokens.
- Consents.
- Authorization metadata and attributes.
- PAR requests.
- Login sessions if using Spring Session.

If an upgrade changes how attributes are serialized or read, the old version may fail to read data written by the new version. Test bidirectional compatibility during mixed-version windows:

- Old version reads data created by the new version.
- New version reads data created by the old version.
- Legacy refresh tokens can still be processed per policy.
- Active authorization codes are not lost.
- Consents are not unexpectedly reset.
- Unexpired PAR requests still resolve.
- Session serialization does not log users out en masse.

If bidirectional compatibility cannot be guaranteed, restrict version mixing or design a transition phase to stop creating legacy state formats before rollout.

## 6. Keeping Tokens and Signing Keys Verifiable During Rollback

### 6.1. Do Not Remove Public Keys Too Early

During signing key rotation, tokens signed with the old key may still be valid. Removing the old public key from JWKS immediately after switching to the new signing key can prevent resource servers from verifying old tokens.

A safe sequence typically includes:

1. Generate a new key with a unique `kid`.
2. Publish the new public key in JWKS.
3. Wait for resource servers to fetch/refresh JWKS.
4. Switch signing to the new key.
5. Keep the old public key in JWKS at least until tokens signed with it expire, plus clock skew and cache duration.
6. Remove the old key only when no valid tokens require it.

When rolling back code, the old version must also be able to verify tokens signed by the new key if those tokens may still be present in the system. Keeping key material and verifiers compatible during the rollback window is essential.

### 6.2. Do Not Change the Issuer Simultaneously with Code Upgrades Unless Required

The issuer is the Authorization Server's identifier. Changing the issuer can cause clients to reject ID Tokens and resource servers to reject access tokens. If changing the domain/issuer is mandatory, treat it as a separate migration with plans for discovery, client configs, token validation, and transition windows.

In a routine application upgrade, keeping the issuer stable reduces changing variables and simplifies rollback.

### 6.3. Token Claims and Formats Must Be Compatible

If the new version changes custom claims, audience, lifetimes, token formats, or signing algorithms, verify the resource servers validating those tokens.

For example, if new tokens add a `tenant_id` claim, old resource servers should ignore unknown claims if design permits. If new tokens change `sub` or `iss`, that is a higher-impact change requiring coordinated migration.

If switching from JWT to opaque tokens or vice versa, do not treat it as a routine deployment change. Update resource servers, introspection, caches, and verification paths before issuing tokens in the new format.

## 7. Monitoring Health and Incidents During Rollout

### 7.1. Combining Health Checks with Business Metrics

Health endpoints answer whether an instance can accept traffic. They do not replace metrics for OAuth/OIDC flows.

Monitor the following groups:

| Group | Metrics/Logs to Watch | Anomaly Signs |
|---|---|---|
| Availability | Request counts, HTTP 5xx, readiness, restarts | Ready pods drop or 5xx rises |
| Latency | p50/p95/p99 per endpoint | Token or authorize slower than baseline |
| Authentication | `invalid_client`, assertion errors, mTLS handshakes | Sudden spike in failures for an auth method |
| Authorization | `invalid_grant`, redirect URI mismatches, consent failures | Unusual rejections of authorization codes or refresh tokens |
| Token | Issuance, refresh, revocation, signature validation | Token issuance drops or resource servers report signature failures |
| Database | Pool usage, timeouts, deadlocks, query latency | Authorization persistence slows or errors |
| Session | Read/write errors, expired sessions, login success | Users unexpectedly forced to log in again |
| JWK/KMS | Key lookups, signing latency, KMS errors, JWKS fetches | Unable to sign tokens or verifiers cannot find `kid` |
| PAR/DCR | PAR success/failure, `invalid_request_uri`, registration errors | Clients unable to start authorization flows |
| Runtime | CPU, memory, GC, thread pools | Pods overloaded or restarting from OOM |

Break down metrics by endpoint, application version, and grant type. This helps reveal if the new version fails only on refresh tokens, `private_key_jwt`, or PAR rather than system-wide.

### 7.2. Setting Alerts Based on Baseline and SLOs

Do not use a single fixed threshold for all systems. Define SLOs, baselines, and operational thresholds before rollout.

An alert rule should specify:

- Metric and measurement scope.
- Time window.
- Warning threshold.
- Rollout halt threshold.
- Alert recipients.
- Expected action.

Example system-configurable criteria:

- HTTP 5xx exceeds baseline threshold across consecutive windows.
- `invalid_client` rate spikes after client authentication changes.
- `invalid_grant` rate increases after authorization repository or refresh token changes.
- Token endpoint p95 exceeds SLO.
- New pods continuously restart or flap readiness.
- Resource servers report inability to verify a new `kid`.
- Database connection pool exhausts or timeouts rise.
- Login success drops while authorize request volume stays normal.

Do not auto-rollback on a single isolated metric if that metric could reflect bad input or a single broken client. Combine multiple signals and analyze blast radius.

### 7.3. Distinguishing System Incidents from Client-Specific Errors

A single client sending a wrong redirect URI or an expired secret generates OAuth errors, but is not necessarily a system-wide outage.

Slice by:

- Handling server version.
- Client class and auth method.
- Grant type.
- Endpoint.
- Error type.
- Rollout start time.
- Region or tenant.
- Success ratio within the same cohort.

If only one client fails after metadata changes, contact the client owner and hold rollout at the current level until the cause is understood. If multiple independent clients fail at the token endpoint simultaneously, a server or shared-dependency regression is likely.

### 7.4. Continuous Synthetic Flow Checks

During rollout, run synthetic flows using test clients and test users:

1. Fetch OIDC Discovery.
2. Check JWKS contains valid keys.
3. Run Authorization Code Flow with PKCE.
4. Exchange the code for tokens.
5. Verify ID Token and access token.
6. Call UserInfo.
7. Use refresh tokens per policy.
8. Test critical client authentication methods.
9. Check revocation/introspection if present.

Synthetic flows must use dedicated test accounts, clients, and redirect URIs. Never use real user credentials.

## 8. Defining Rollout Stop Conditions

Before deploying, write explicit criteria for continue, hold, and rollback.

| Decision | Reference Criteria | Action |
|---|---|---|
| Continue | Health stable, metrics within SLO, synthetic flows pass, no notable regressions | Expand traffic to next step |
| Hold | Abnormal signal present, but scope or cause unclear | Keep canary ratio, gather logs/traces, and investigate |
| Rollback | Severe, widespread error, security impact, or unresolvable within allowed window | Halt rollout, shift traffic back to stable version per runbook |
| Forward fix | Rollback unsafe due to changed data/keys or irreversible migration | Hold traffic at safe level and release compatible fix |

Conditions requiring immediate stop and assessment:

- Valid token signatures cannot be verified.
- Tokens are issued with the wrong issuer.
- Private keys or secrets are exposed.
- Widespread client failures exchanging authorization codes or refresh tokens.
- Authorization state is lost or written incorrectly.
- Database migration corrupts data or prevents the old version from running.
- Widespread user session loss.
- Configuration bug unexpectedly widens access on a protected endpoint.

Security incidents may require separate incident response procedures: halting token issuance, revoking credentials/keys per plan, and coordinating with resource servers. Reverting to an old container image alone does not fix an exposed key or already-issued bad tokens.

## 9. Planning Rollback Before Deployment

Rollback is more than redeploying an old image. Answer these questions beforehand:

- Is the old image still in the registry and able to start against the current schema?
- Can the old version read authorization/session state written by the new version?
- Can the old version verify tokens signed with a new key?
- Did the issuer, redirect URIs, or public endpoints change?
- Were destructive or data-converting migrations run?
- Do any feature flags need reverting to old values?
- Were any secrets/certificates rotated, and can the old version use them?
- Did any clients update metadata during the rollout?

If these questions cannot be answered, the rollback plan is not concrete enough.

### 9.1. Distinguishing Code, Config, and Data Rollbacks

| Rollback Type | Example | Key Considerations |
|---|---|---|
| Code | Revert deployment to old image | Old image must be compatible with current schema and state |
| Config | Revert feature flags or properties to prior values | Must know which configs changed and revert order |
| Routing | Shift traffic from green back to blue | Both environments must read shared state and tokens |
| Database | Restore schema/data | Restoring can lose new authorizations/tokens/client registrations |
| Key/certificate | Revert to old key or certificate | Do not delete new key while new tokens remain valid |
| Client metadata | Restore redirect URI/auth method | Avoid breaking active clients or rotated secrets |

Do not assume database rollback is safe by default. With expand migrations, you can usually keep the new schema and roll back code if the old version remains compatible. With contract migrations or irreversibly transformed data, a forward fix or controlled recovery may be needed instead of a full database restore.

### 9.2. Reference Rollback Runbook

A runbook should define clear steps and owners:

1. Halt rollout or stop increasing canary traffic.
2. Record timestamp, deployment revision, image digest, and error correlation IDs.
3. Classify whether the fault lies in code, config, database, keys, or infrastructure.
4. Verify compatibility of the stable version with current schema and state.
5. Shift traffic back to the stable version or scale down the canary per chosen strategy.
6. Retain signing keys/JWKS needed to verify already-issued tokens.
7. Restore altered configs or feature flags if needed.
8. Verify readiness, discovery, JWKS, and OAuth/OIDC flows.
9. Monitor error rates, latency, and token issuance after rollback.
10. Communicate status and open a root-cause investigation.

Kubernetes example:

~~~bash
kubectl rollout history deployment/authorization-server
kubectl rollout undo deployment/authorization-server
kubectl rollout status deployment/authorization-server
kubectl get pods -l app=authorization-server
~~~

These commands operate only on Deployment revisions. They do not automatically revert database migrations, secrets, issuers, key rotations, or client metadata changes. The runbook must include dedicated steps for each category of change performed.

If using Helm or GitOps, perform rollbacks through the active configuration management tool. Do not patch cluster resources directly if the controller will immediately reconcile back to Git state.

### 9.3. Post-Rollback Verification

After traffic returns to the stable version, verify:

- All desired replicas are ready.
- Image digests and config revisions match the stable version.
- OIDC Discovery returns the right issuer and endpoints.
- JWKS still publishes public keys required to verify still-valid tokens.
- New tokens can be issued.
- Legacy tokens and tokens issued during the canary window remain verifiable per policy.
- Valid authorization codes and refresh tokens continue working.
- Sessions, consents, and client registrations remain intact.
- Database contains no half-completed transactions or partially converted rows.
- Error and latency metrics return close to baseline.

Do not delete canary pods or the green environment before collecting logs and state needed for investigation. Do not delete a new key while tokens signed by that key remain accepted.

## 10. Authorization Server–Specific Rollback Scenarios

### 10.1. New Version Issued Tokens with a New Signing Key

If new tokens were already issued, the old version must be able to verify those tokens for their remaining valid lifetime. Keep the new public key in JWKS and ensure the old version's verifier supports that algorithm.

If the old version does not support the new algorithm, stopping new token issuance does not handle already-issued tokens. Keep a compatible verifier on the rollback version, wait for those tokens to expire per policy, or issue a forward fix before shifting traffic completely. Never delete a public key just to force the system back to an old state.

### 10.2. Schema Was Expanded but New Code Fails

If the migration only added compatible structures, you can keep the new schema and roll back code. Verify the old version is unaffected by added columns/tables and that no contract migration has run.

Do not run automated down-migrations if they delete data created by the new version.

### 10.3. Schema Was Contracted or Data Transformed

If the migration dropped old columns or changed formats incompatibly, the old version may fail to run. In that case:

- Stop new traffic to the failing version.
- Evaluate forward-fix feasibility.
- If a restore is required, precisely identify authorization/token data created after the backup.
- Plan data reconciliation before restoring.
- Coordinate with clients/resource servers if tokens or authorization state are affected.

In token-issuing systems, restoring an old database can revive revoked states or lose refresh token rotation state. This is a security risk that must be assessed before acting.

### 10.4. New Version Changed Subject or Issuer

Changing `sub` or `iss` can cause clients to treat users as different identities or reject ID Tokens. Rolling back code can leave new and old tokens coexisting with two subject rules.

If tokens were already issued under the new rule, keep compatible mappings and track the lifetime of those tokens. Never automatically swap new subjects for old subjects in responses without a stable mapping and clear identity policy.

### 10.5. New Version Changed Client Authentication

If moving from `client_secret_basic` to `private_key_jwt` or mTLS, clients may have updated credentials or metadata during rollout. Rolling back the server can prevent updated clients from authenticating.

Prepare a transition plan for both sides:

- Retain the old method during a compatibility window if policy allows.
- Verify stored client registrations and auth methods.
- Do not automatically downgrade authentication methods when new credentials fail.
- Keep a list of modified clients and steps to return metadata to a compatible state.

## 11. Sample Rollout Plan

Example rollout plan for a Spring Authorization Server upgrade:

| Phase | Tasks | Exit Criteria |
|---|---|---|
| T-7 days | Review release notes, API changes, schema, tokens, keys, and client compatibility | Checklist and risk owners assigned |
| T-3 days | Staging tests, load tests, rollback rehearsal | Core flows pass and rollback rehearsed |
| T-1 day | Lock image digests, migrations, dashboards, alerts, and on-call roster | Artifacts and runbooks ready |
| T0 - pre-deploy | Capture baseline, verify database backups, keys, and dependencies | Baseline recorded |
| T0 - canary | Deploy small group, run synthetic flows | No regressions beyond threshold |
| T0 - expansion | Expand traffic in steps | Each step completes stability window |
| T0 - completion | Complete rollout, check replicas and migrations | All instances on new version |
| T+1 day | Monitor delayed errors, refresh tokens, client auth, and resource servers | Metrics stable, no open incidents |
| Post-rollback window | Run contract migration if applicable, clean up old resources | Confirmed no consumers on old version |

Timelines are illustrative. For low-traffic systems or long token lifetimes, the observation window must be long enough to observe real refresh, revocation, and token validation flows.

## 12. Pre-, During-, and Post-Rollout Checklist

### Before Rollout

- [ ] Java, Spring Boot, Spring Security, and Spring Authorization Server versions locked.
- [ ] Release notes and migration guides reviewed.
- [ ] Baseline availability, latency, and OAuth error rates recorded.
- [ ] Affected flows/clients identified.
- [ ] Database schema compatibility verified between old and new versions.
- [ ] Authorization state, session, and PAR persistence verified.
- [ ] Signing keys, JWKS, and issuer compatibility verified.
- [ ] Image digests, config revisions, and migration versions recorded.
- [ ] Backups/snapshots taken and restore limitations understood.
- [ ] Code/config rollback rehearsed in staging.
- [ ] Dashboards, alerts, runbooks, and coordinators in place.

### During Rollout

- [ ] Canary scoped accurately.
- [ ] Readiness and liveness reflect true instance state.
- [ ] Synthetic authorization flows succeed.
- [ ] Token endpoint and refresh tokens show no regressions.
- [ ] UserInfo, discovery, and JWKS work properly.
- [ ] Critical client authentication methods work.
- [ ] Database, session store, cache, and KMS are stable.
- [ ] Metrics analyzed per version.
- [ ] Each rollout step has an explicit continue/hold/rollback decision.
- [ ] Traffic is never expanded while a severe alert remains unexplained.

### After Rollout

- [ ] All replicas run the exact image digest and config revision.
- [ ] Error rates and latency remain within SLO.
- [ ] Old and new tokens validate per policy.
- [ ] Authorization codes, refresh tokens, consents, and sessions operate properly.
- [ ] JWKS retains all keys needed for still-valid tokens.
- [ ] Database migrations verified.
- [ ] No unclassified alerts or incidents remain.
- [ ] Logs, metrics, decisions, and incident timeline archived.
- [ ] Contract migrations executed only after the rollback window closes.
- [ ] Lessons learned documented and runbooks updated.

Phased rollout limits blast radius and provides time to verify real-world behavior. Incident monitoring must combine health checks with business metrics such as authorization, tokens, refresh, client authentication, and JWT verification. Rollback is only safe when old code remains compatible with the current schema, state, issuer, and signing keys; therefore, the rollback procedure must be designed and rehearsed before starting rollout.
