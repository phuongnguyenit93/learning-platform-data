# Testing IAM, Service Identity, and Private Network Access

In the `CLOUD_PROVIDERS_GCP` module, learners explore Google Cloud from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases. Deployment scenarios help teams choose services, protect resources, automate releases, and monitor reliability and cost. In the **GCP Application Testing** chapter, testing must not only verify application functionality, but also validate security boundaries when the application runs with its real identity and network path.

This hands-on lesson walks through testing **IAM authorization**, **service identity**, and **private network access** on GCP. The running example is a Spring Boot application `orders-api` running on Cloud Run, reading a sample object from Cloud Storage and connecting to Cloud SQL for PostgreSQL via private IP. We verify both allowed and denied cases while distinguishing IAM, authentication, DNS, routing, firewall, and database credential errors.

## 1. Three Boundaries to Test

A single request can traverse multiple control layers:

| Layer | Question | Common Mechanisms |
| --- | --- | --- |
| **Authentication** | Which identity is the request using? | Application Default Credentials (ADC), OAuth access tokens, OIDC ID tokens, metadata server. |
| **IAM authorization** | What actions may that principal perform on which resources? | IAM allow/deny policies, roles, conditions, principal access boundaries, service-specific policies. |
| **Network reachability** | Can packets reach the required endpoint and port? | Cloud Run Direct VPC egress, Shared VPC, subnets, DNS, routes, firewalls, private IPs. |
| **Destination authorization** | Does the target server accept the request/credentials? | Cloud Run Invoker, database login, TLS, application RBAC. |

A successful TCP connection only proves the socket opened; it does not prove the user can query the database. An HTTP 403 from Cloud Storage proves the Google API rejected the request, but is not enough to conclude only IAM lacked a role: a disabled API, VPC Service Controls, or other policies can also cause it.

~~~mermaid
flowchart LR
    CLIENT[Caller + ID token] --> INGRESS[Cloud Run ingress]
    INGRESS --> INVOKER[Cloud Run invoker IAM]
    INVOKER --> APP[orders-api + runtime SA]
    APP --> ADC[ADC + Google access token]
    ADC --> IAM[Cloud Storage IAM]
    IAM --> BUCKET[(Test bucket/object)]
    APP --> VPC[Direct VPC egress]
    VPC --> NET[DNS / route / firewall]
    NET --> SQL[(Cloud SQL private IP)]
    SQL --> DB[Database login + SQL privileges]
~~~

**Cloud Run ingress** is the policy controlling inbound callers to the service; **Direct VPC egress** is the outbound path from Cloud Run into the VPC. **Service identity** is the service account that code running inside Cloud Run uses to call Google APIs; it differs from the **deployer identity** that deploys Cloud Run and from the **invoker identity** calling the service's HTTP endpoint.

## 2. Designing the Test Matrix

Before writing code, define each case using the structure: **principal + action + resource + network context + expected outcome**. A minimal test matrix:

| ID | Principal / Source | Action | Network Context | Expected |
| --- | --- | --- | --- | --- |
| IAM-01 | `orders-runtime@PROJECT_ID` | Read object `fixtures/ping.json` | Cloud Run staging | ALLOW |
| IAM-02 | `orders-runtime@PROJECT_ID` | Delete sample object | Cloud Run staging | DENY |
| IAM-03 | `denied-runtime@PROJECT_ID` | Read same object | Runner with same connectivity | DENY |
| ID-01 | New Cloud Run revision | Call Storage using ADC | Staging | Caller is `orders-runtime` |
| ID-02 | CI deployer | Attach runtime service account | Deploy step | Only approved deployers hold `iam.serviceAccounts.actAs` |
| RUN-01 | SA with `roles/run.invoker` | Call private Cloud Run endpoint | Source passing ingress | ALLOW |
| RUN-02 | SA without Invoker | Call same endpoint | Same ingress source | DENY |
| NET-01 | `orders-api` | TCP to `10.20.4.5:5432` | Permitted staging VPC | CONNECT |
| NET-02 | Workload blocked by firewall/routing | TCP to same address | Restricted staging network | DENY |
| NET-03 | Public Internet caller | Call internal Cloud Run service | Outside valid ingress | DENY |

All names, IPs, buckets, and project IDs in this lesson are illustrative values. Use **staging**, test objects, and databases containing synthetic data. Every negative test must have a positive control proving the target resource exists and works; otherwise, a `404`, timeout, or DNS error could be a broken fixture rather than an enforced security policy.

### 2.1. Choosing the Right Test Level

- **Policy/static tests:** inspect Terraform plans, IAM bindings, service accounts, ingress/egress, and firewall rules. Catches configuration drift before deployment; does not fully simulate runtime behavior.
- **Integration tests:** execute Google API calls or TCP probes from a workload/runner matching production identity and network topology.
- **End-to-end tests:** caller sends a request to Cloud Run; code traverses IAM and private networking to hit downstream services; verify outcomes and audit evidence.

Unit tests with mocked Google Cloud clients verify Java logic, but do not prove real IAM or private networking. A real GCP environment is required for this testing layer.

## 3. Preparing the Test Environment

### 3.1. Test Fixtures

Prepare the following resources inside a controlled staging project:

| Component | Purpose |
| --- | --- |
| `PROJECT_ID`, `REGION` | Staging project/region. |
| `orders-runtime@PROJECT_ID.iam.gserviceaccount.com` | Runtime SA permitted to read objects. |
| `denied-runtime@PROJECT_ID.iam.gserviceaccount.com` | Runtime SA not granted object read permissions. |
| `test-caller@PROJECT_ID.iam.gserviceaccount.com` | Caller authorized to invoke the service. |
| `denied-caller@PROJECT_ID.iam.gserviceaccount.com` | Caller lacking invoke permissions. |
| `TEST_BUCKET/fixtures/ping.json` | Existing test object containing no sensitive data. |
| `test-vpc` and `test-subnet` | VPC/subnet configured for Direct VPC egress. |
| PostgreSQL test instance | Cloud SQL private IP and a read-only test account. |

If the object does not exist, read tests may receive `404` instead of proving IAM behavior. Verify the fixture using a positive-control principal with read access before running negative tests.

Grant `roles/storage.objectViewer` to `orders-runtime` on the bucket or a narrower scope as required; grant no read permissions to `denied-runtime`. Never use production buckets or objects containing real user data to test permissions.

### 3.2. Identities in Cloud Run

There are three distinct identities to verify:

1. **Deployer:** the principal calling the Cloud Run Admin API. To attach a runtime service account, the deployer must hold `iam.serviceAccounts.actAs` on that service account, commonly granted via `roles/iam.serviceAccountUser`.
2. **Runtime service identity:** the service account attached to the revision. The Cloud Run metadata server issues short-lived access tokens and Google Client Libraries use ADC to call Google APIs.
3. **HTTP caller / invoker:** the principal sending an OIDC ID token when calling an authenticated Cloud Run service. This principal must hold `run.routes.invoke`, typically granted via `roles/run.invoker`.

The `roles/iam.serviceAccountTokenCreator` role for minting access/ID tokens via impersonation differs from `roles/iam.serviceAccountUser` used to attach an identity. Avoid granting Token Creator broadly just to make one test pass.

Inspect service configuration:

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=REGION \
  --format=export
~~~

Check `serviceAccountName`, `ingress`, network/subnet, and VPC egress in the configuration. The revision must use `orders-runtime@PROJECT_ID.iam.gserviceaccount.com` rather than accidentally falling back to the Compute Engine default service account. Re-verify on every deploy because service identity is a per-revision setting.

### 3.3. ADC and Avoiding JSON Keys

On a developer machine, `gcloud auth application-default login` creates personal ADC for the developer; that account may hold broader roles than the runtime SA. Therefore, passing tests on a laptop **does not prove** the production application has equivalent permissions.

In Cloud Run, use a user-managed service account attached to the workload and let Google Client Libraries resolve ADC. Never set `GOOGLE_APPLICATION_CREDENTIALS` pointing to a JSON service account key inside the container. In GKE, use Workload Identity Federation for GKE; in Compute Engine, use a VM-attached service account with appropriate API scopes when applicable. In CI, prefer Workload Identity Federation or short-lived service account impersonation over long-lived key files.

## 4. Testing IAM Allow/Deny

### 4.1. Checking Permissions with Policy Troubleshooter

Open **IAM & Admin → Policy Troubleshooter**. Supply:

- Principal: `orders-runtime@PROJECT_ID.iam.gserviceaccount.com`.
- Resource: selected fixture bucket/object.
- Permission: `storage.objects.get`.
- Expected decision: **Allow** for the runtime SA; **Deny** when checking `storage.objects.delete` or `storage.objects.get` with `denied-runtime`.

Policy Troubleshooter evaluates supported allow/deny policies, IAM Conditions, and principal access boundaries. An **Unknown** result can appear if the caller lacks permission to view policies or condition context is missing. Do not treat Unknown as Deny. This tool also does not simulate VPC Service Controls and has limitations for certain service-level bindings/ACLs.

Illustrative CLI syntax example using a project-level permission:

~~~bash
gcloud policy-intelligence troubleshoot-policy iam \
  //cloudresourcemanager.googleapis.com/projects/PROJECT_ID \
  --principal-email=orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --permission=resourcemanager.projects.get
~~~

The illustrative command above checks `resourcemanager.projects.get`; it does **not** prove `storage.objects.get`. For Storage, supply the full resource name and target permission, then verify with a Storage API integration test. If an IAM Condition checks timestamps, resource tags, or request attributes, supply matching context to avoid misleading conclusions.

### 4.2. Difference from `testIamPermissions`

Many Google Cloud APIs expose `testIamPermissions`, returning which permissions the **current caller** holds on a resource. This method is useful for UIs or self-checks, but does not let you query an arbitrary principal by passing its email. To investigate a different principal, use Policy Troubleshooter and execute tests under that principal's actual identity.

### 4.3. Testing with the Google Cloud Storage Java Client

Use the Google Cloud Storage client version-managed via the project BOM alongside JUnit 5. Example in a Spring Boot Gradle project with dependencies configured:

~~~groovy
dependencies {
    implementation "com.google.cloud:google-cloud-storage"
    testImplementation "org.springframework.boot:spring-boot-starter-test"
}
~~~

Note that `google-cloud-storage` needs its version managed by `com.google.cloud:libraries-bom` or equivalent dependency management; do not leave the dependency unversioned if the project has not imported a BOM.

Positive integration test, executed **in a job/revision running as the valid runtime SA**:

~~~java
package com.example.orders.it;

import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@Tag("gcp-integration")
class StorageAllowedIT {
    @Test
    void canReadExistingFixtureObject() {
        String bucket = System.getenv("TEST_BUCKET");
        Storage storage = StorageOptions.getDefaultInstance().getService();

        Blob blob = storage.get(
            BlobId.of(bucket, "fixtures/ping.json"));

        assertNotNull(blob, "Fixture must exist and be readable");
    }
}
~~~

Negative test, executed in a **separate job running as `denied-runtime`**:

~~~java
package com.example.orders.it;

import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageException;
import com.google.cloud.storage.StorageOptions;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("gcp-integration-negative")
class StorageDeniedIT {
    @Test
    void cannotReadFixtureWithoutIamPermission() {
        String bucket = System.getenv("TEST_BUCKET");
        Storage storage = StorageOptions.getDefaultInstance().getService();

        StorageException exception = assertThrows(
            StorageException.class,
            () -> storage.get(BlobId.of(bucket, "fixtures/ping.json")));

        assertEquals(403, exception.getCode());
    }
}
~~~

These two tests validate allow/deny only if CI genuinely runs them under **two different principals** and the object exists. If personal ADC is reused for both, the tests prove nothing. When status codes deviate from expectations, record the error code, principal, resource, request ID, and relevant Cloud Audit Logs; never log access tokens.

## 5. Testing Runtime Execution Identity (Service Identity)

### 5.1. Verifying the Active Principal Inside the Workload

Cloud Run uses the metadata server to issue short-lived tokens for the runtime service account. Inside an authorized debug job, inspect the runtime service identity's email:

~~~bash
curl -fsS \
  -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email"
~~~

Only call the metadata server **from inside** the GCP workload. That endpoint is unreachable from a laptop. Never log or return the contents of `.../token` to clients, as that returns a live access token. Log diagnostic metadata such as the service account email and revision ID within approved logging boundaries to spot identity drift.

On GKE, the Kubernetes ServiceAccount name does not necessarily match the IAM service account email; workloads may use Workload Identity principals directly or impersonation. Verify bindings/annotations and the effective principal in audit logs. On Compute Engine, check both the service account and VM API access scopes if the VM was created with restricted scopes.

### 5.2. A Common Pitfall

A new revision of `orders-api` is accidentally deployed with the Compute Engine default service account. Its health endpoint still returns 200 because it touches no external resources, yet Storage API calls fail with `PERMISSION_DENIED`. Investigation workflow:

1. Compare `serviceAccountName` between the healthy revision and the failing revision.
2. Verify the application uses ADC rather than a mounted JSON key file from elsewhere.
3. Re-run `StorageAllowedIT` using the exact revision/job configured with that runtime identity.
4. Use Policy Troubleshooter and audit logs to cross-check principal, permission, and resource.
5. Restore the proper service identity through the release process; never grant Owner/Editor to the default SA as a temporary workaround.
6. Add a CI gate validating the expected service account on the staging revision before shifting traffic.

## 6. Testing Cloud Run Invoker Identity

Cloud Run can require callers to present a **Google-signed OIDC ID token** whose `aud` claim matches the target service URL (or configured custom audience). An **OAuth access token** used to call Google APIs cannot substitute for an ID token in Cloud Run service-to-service invocations.

### 6.1. Allow/Deny Testing from the Same Ingress Source

Prepare two caller principals:

- `test-caller` granted `roles/run.invoker` on the target Cloud Run service.
- `denied-caller` lacking that role.

Use a runner whose **inbound path is permitted by the Cloud Run ingress policy**. Example for an operator with controlled impersonation permissions, inside Cloud Shell or a compliant runner when ingress allows:

~~~bash
SERVICE_URL="https://orders-api-EXAMPLE.a.run.app"
TOKEN="$(gcloud auth print-identity-token \
  --impersonate-service-account=test-caller@PROJECT_ID.iam.gserviceaccount.com \
  --audiences="$SERVICE_URL")"

curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "$SERVICE_URL/health"

unset TOKEN
~~~

With a valid caller and healthy endpoint, expect HTTP 200. Repeat using `denied-caller` from the **same network context** and verify the request is rejected at the auth/authorization layer. To mint ID tokens via impersonation, the operator needs `roles/iam.serviceAccountTokenCreator` or equivalent permission on the caller SA; keep this role scoped to testing rather than granting it broadly to all staff.

### 6.2. Ingress Can Block Before IAM

If a Cloud Run service is configured with `ingress=internal`, requests from the public Internet are blocked **before** IAM evaluation. Therefore, you cannot use an HTTP 404/403 from a laptop as proof that IAM Invoker denied the request. Run both Invoker tests from a source recognized by Cloud Run as internal—such as a Cloud Run service/job inside the network and scope matching the ingress policy. Separately test one public Internet request to confirm ingress blocks external traffic as designed.

The audience is normally the **primary service URL**, even when targeting a traffic-tag URL, unless a valid custom audience is configured. Wrong audience, expired tokens, and missing Invoker permissions can all fail a request; logs and policies help distinguish them.

## 7. Testing Private Networking for Cloud Run → Cloud SQL

### 7.1. Conditions That Must All Hold Simultaneously

For Cloud Run to reach PostgreSQL over **private IP**, verify:

1. The Cloud SQL instance exists, has a private IP, and listens on TCP `5432`.
2. Cloud Run is configured with **Direct VPC egress** or an appropriate Serverless VPC Access connector.
3. The VPC/subnet has a valid path to Cloud SQL (including Private Service Access/peering or the designed connectivity model).
4. Routes and firewall rules allow the Cloud Run source to reach the destination IP and port.
5. DNS resolves the DB hostname to the expected private IP if using hostnames.
6. Database user/IAM DB authentication and TLS are properly configured.

Direct VPC egress governs Cloud Run's **outbound traffic**; it does not automatically restrict the Cloud Run HTTP endpoint to private ingress. To lock down inbound access, configure `ingress` and load balancing separately.

### 7.2. Verifying VPC Egress Configuration

~~~bash
gcloud run services describe orders-api \
  --project=PROJECT_ID \
  --region=REGION

gcloud compute networks subnets describe TEST_SUBNET \
  --project=NETWORK_HOST_PROJECT_ID \
  --region=REGION

gcloud sql instances describe TEST_SQL_INSTANCE \
  --project=SQL_PROJECT_ID
~~~

In the outputs, check the network/subnet, egress mode, and Cloud SQL private IP. With Shared VPC, the network host project may differ from the service project, so subnet permissions must be verified in the host project.

| Mode | Meaning |
| --- | --- |
| `private-ranges-only` | Traffic to eligible private/internal ranges routes through the VPC; some traffic to public APIs may follow Cloud Run's default route. |
| `all-traffic` | All outbound traffic routes through the VPC; reaching the Internet requires Cloud NAT or an explicit egress route. |

Never conclude "private egress works" simply because a container reaches `storage.googleapis.com`: Google API traffic may traverse a different network path. Inspect routes, DNS, and egress configuration to prove the actual path.

### 7.3. TCP Probe Inside the Workload

A Java TCP probe confirms the private endpoint's port is reachable. Run the test **inside a Cloud Run Job or runner sharing the same service identity and VPC egress**, never from a laptop to infer Cloud Run's network path.

~~~java
package com.example.orders.it;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("gcp-private-network")
class PrivateSqlPathIT {
    @Test
    void canConnectToPostgresPort() throws IOException {
        String host = System.getenv("PRIVATE_DB_HOST");
        int port = Integer.parseInt(
            System.getenv().getOrDefault("PRIVATE_DB_PORT", "5432"));

        try (Socket socket = new Socket()) {
            socket.connect(new InetSocketAddress(host, port), 5000);
            assertTrue(socket.isConnected());
        }
    }
}
~~~

Passing this test establishes only that the **TCP port is reachable**. Follow up with a JDBC test (PostgreSQL driver + test DB credentials) that opens a connection and executes `SELECT 1`, using a read-only DB user and configured TLS. IAM `roles/cloudsql.client`, when using the Cloud SQL Auth Proxy/connector, does not automatically grant SQL privileges on tables. Database login/privileges and network reachability must be verified separately.

### 7.4. Negative Network Tests

A negative test must target the **exact same private IP and port** from a disallowed workload (blocked by firewall, missing route, or outside the VPC). Expect the socket connection to fail. However, a **timeout** has multiple causes: missing route, firewall deny, down destination, or no listener. Therefore, always pair it with a positive control from an authorized network, verify target health, and cross-check Connectivity Tests or firewall logs.

| Outcome | Interpretation |
| --- | --- |
| DNS lookup fails | Check private DNS zones, forwarding, and hostnames; do not jump to firewall conclusions. |
| TCP timeout | Check routes, firewalls, VPC configuration, and destination health. |
| Connection refused | Packets likely reached the host, but no listener is on that port or a policy rejected it. |
| TCP connected, JDBC auth failed | Network path to DB works; failure is in credentials, TLS, or DB permissions. |
| JDBC query permission denied | DB user lacks data privileges; unrelated to `roles/run.invoker`. |

Do not rely on `ping` as primary proof: many endpoints drop ICMP. Testing from the public Internet toward a private IP also fails to prove workload firewall rules are enforcing as intended, since the public Internet already lacks routes to private IPs.

## 8. Investigating with Connectivity Tests, Firewalls, and DNS

### 8.1. Connectivity Tests

**Network Intelligence Center → Connectivity Tests** analyzes the configured path between endpoints, covering many VPC firewall, route, peering, VPN, and load-balancer scenarios. For supported scenarios, it also performs data-plane probes. Select source, destination, and port matching your test and inspect where packets drop.

Connectivity Tests has limitations by endpoint type and does not replace socket or JDBC integration tests. In hybrid topologies extending outside Google Cloud, the tool cannot necessarily inspect every third-party device beyond GCP.

### 8.2. Checking Firewalls and Routing

When TCP is blocked, ask in order:

- Does Cloud Run egress use the intended network/subnet and network tags?
- Do VPC routes include a path to the target private IP and a return path?
- Do source egress firewall rules and destination ingress firewall rules allow TCP 5432?
- Does a higher-priority deny rule override the expected allow rule?
- With Shared VPC, is the Cloud Run service project attached to the host VPC with required permissions?
- Are Private Service Access, peering, Network Connectivity, or VPC Service Controls policies involved?
- Does DNS resolve to the intended private IP or a public IP?

Enable **Firewall Rules Logging** when observing firewall allow/deny verdicts where supported. **VPC Flow Logs** help analyze traffic at interfaces/subnets, though they do not capture every dropped packet. Keep Connectivity Tests outputs and logs inside staging for investigation without printing secrets.

### 8.3. Private Google Access Does Not Replace IAM

Private Google Access enables resources without external IPs to reach Google APIs over internal paths. It does not replace IAM and does not create private paths to arbitrary application backends. DNS for `private.googleapis.com` or `restricted.googleapis.com` must follow approved architecture and policies; never alter DNS merely to make a test pass.

When testing Google API access over a private path, record the DNS response, route, VPC egress, firewall rules, and IAM verdict separately. Receiving HTTP 200 from an API does not by itself prove traffic traversed the intended private path.

## 9. Test Runners and CI/CD

### 9.1. Splitting Test Jobs by Principal and Network

A pipeline can be structured as:

~~~mermaid
flowchart TD
  PLAN[Review IaC: IAM/VPC configuration] --> DEPLOY[Deploy staging revision]
  DEPLOY --> IA[Identity & ADC checks]
  DEPLOY --> POS[Allowed IAM test]
  DEPLOY --> NEG[Denied IAM test]
  DEPLOY --> INGRESS[Cloud Run Invoker/ingress tests]
  DEPLOY --> NET[Private TCP/JDBC tests]
  IA --> REPORT[Collect evidence]
  POS --> REPORT
  NEG --> REPORT
  INGRESS --> REPORT
  NET --> REPORT
  REPORT --> GATE{Expected outcomes met?}
  GATE -->|Yes| PROMOTE[Eligible for promotion]
  GATE -->|No| STOP[Block and investigate]
~~~

Each job must have an explicit identity and network placement:

- **IAM-positive:** job runs as `orders-runtime`; the fixture object exists and is readable.
- **IAM-negative:** separate job runs as `denied-runtime` against the same object without permission.
- **Invoker:** two distinct caller SAs invoking from the same authorized network source.
- **Network-positive:** runner inside an authorized VPC connecting successfully to the private DB.
- **Network-negative:** runner in a restricted network targeting the same private DB and port.

Use Workload Identity Federation or runner-attached service accounts; restrict `roles/iam.serviceAccountTokenCreator` if impersonation is required. Never grant Owner/Editor to test runners just to avoid failures.

### 9.2. Preconditions and Stability

1. Validate project, region, and test fixtures before running.
2. Record the runner's effective principal, revision, and VPC configuration.
3. Wait for revision readiness and IAM policy propagation using bounded retries.
4. Run positive controls first to confirm the target resource is healthy.
5. Run negative tests and classify exact HTTP status/network errors rather than binary pass/fail.
6. Capture logs/audit evidence and clean up authorized test fixtures afterward.

If a negative test is unexpectedly allowed, check inherited folder/organization IAM roles, group memberships, IAM Conditions, or the actual active principal. Never alter expected outcomes just to turn a pipeline green.

### 9.3. Storing Credential-Free Evidence

Example JSON evidence artifact:

~~~json
{
  "testId": "IAM-03",
  "environment": "staging",
  "principal": "denied-runtime@PROJECT_ID.iam.gserviceaccount.com",
  "resource": "gs://TEST_BUCKET/fixtures/ping.json",
  "action": "storage.objects.get",
  "expected": "DENY",
  "actualHttpStatus": 403,
  "result": "PASS",
  "revision": "orders-api-00012",
  "timestamp": "2026-11-19T10:00:00Z"
}
~~~

You may include request IDs/correlation IDs, but never store access tokens, ID tokens, service account keys, database passwords, or sensitive object contents. Cloud Audit Logs may require enabling Data Access logs to record certain Storage read operations; verify logging policies and audit-log read permissions.

## 10. Investigation Scenario: New Deployment Hits 403 and Timeouts

A new revision of `orders-api` returns `200` on its health endpoint, yet order processing reports Storage `403` and Cloud SQL `timeout`.

Investigate in order:

1. Compare the service identity of the previous and new revisions. If the new one defaulted to the Compute Engine SA, confirm via the metadata server or Cloud Audit Logs.
2. Run the Storage test under the new revision itself. Use Policy Troubleshooter to check principal/permission on the fixture.
3. Inspect audit logs to distinguish IAM deny, VPC Service Controls, or disabled API errors.
4. Verify Direct VPC egress, VPC/subnet, DNS, and Cloud SQL private IP in live configuration.
5. Run the TCP probe from a job on the same network; run Connectivity Tests if connectivity fails.
6. Only once TCP connects should you investigate JDBC credentials, TLS, and database permissions.
7. Roll back the revision or fix identity/network configuration through the release pipeline, then re-run both positive and negative tests before shifting traffic.

Two failures appearing in the same deployment do not imply a single root cause. Storage IAM and the TCP path to Cloud SQL are independent boundaries that must be verified separately.

## 11. Quick Troubleshooting

| Symptom | Common Cause | Action |
| --- | --- | --- |
| Passes locally, Cloud Run returns 403 | Local ADC is more privileged than runtime SA. | Compare principals and revision IAM bindings. |
| Deploys cleanly but cannot read Storage | Runtime SA lacks `storage.objects.get`. | Check bucket/object policies and audit logs. |
| Cannot attach service account | Deployer lacks `iam.serviceAccounts.actAs`. | Check Service Account User binding on the target SA. |
| Caller has Cloud Run Invoker but request is blocked | Internal ingress, missing/wrong token audience, or IAM condition. | Test from valid ingress, then inspect ID token and policies. |
| Policy Troubleshooter returns Unknown | Caller cannot view all policies/roles or lacks condition context. | Request appropriate review permissions and supply context. |
| IAM-negative test unexpectedly passes | Inherited role or wrong active principal. | Check resource hierarchy, groups, and ADC. |
| Storage test returns 404 | Wrong bucket/object fixture or hidden object. | Verify using the positive-control principal. |
| Private DB TCP timeout | Route, firewall, subnet, egress mode, or down destination. | Check Connectivity Tests, firewall logs, and VPC config. |
| TCP connects but JDBC fails | Database authentication, TLS, or SQL privileges. | Verify credentials and DB roles separately. |
| GKE workload fails IAM | Workload Identity Federation mapping mismatch. | Check KSA/IAM binding and actual caller identity. |
| Google API succeeds but private path unproven | DNS or route differs from expectation. | Check private DNS, egress settings, and routes. |

## 12. Completion Checklist

- [ ] Maintain a principal × action × resource × network × expected outcome matrix.
- [ ] Staging fixtures exist with synthetic data and zero production impact.
- [ ] Least-privilege runtime SA and dedicated denied SA are provisioned.
- [ ] Deployer, runtime, and invoker identities are clearly separated.
- [ ] No long-lived JSON keys are used in Cloud Run or CI.
- [ ] Policy Troubleshooter validates allow/deny/conditions on target resources.
- [ ] Positive Storage test passes under the valid runtime SA.
- [ ] Negative Storage test fails as expected under the denied SA.
- [ ] Revision `serviceAccountName` and active runtime principal are verified.
- [ ] Invoker tests run from a source permitted by the ingress policy.
- [ ] VPC egress, subnet, routes, DNS, and firewalls match design.
- [ ] TCP probe runs inside a workload/runner sharing the target network path.
- [ ] Negative network test targets the exact same destination paired with a positive control.
- [ ] TCP reachability is tested separately from database auth/JDBC.
- [ ] Connectivity Tests and firewall logs are used for network failure triage.
- [ ] CI isolates job identities, retains evidence, and sets sensible timeouts/retries.
- [ ] Tests never log tokens, passwords, private keys, or user data.

## References

- [Cloud Run service identity](https://docs.cloud.google.com/run/docs/securing/service-identity) — deployer identity, runtime identity, ADC, and metadata server.
- [Configure service identity](https://docs.cloud.google.com/run/docs/configuring/services/service-identity) — attaching runtime SAs and IAM.
- [Policy Troubleshooter](https://docs.cloud.google.com/policy-intelligence/docs/troubleshoot-access) — checking IAM allow/deny/conditions and limitations.
- [Test IAM permissions](https://docs.cloud.google.com/iam/docs/testing-permissions) — `testIamPermissions` self-check.
- [Cloud Run service-to-service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service) — ID tokens and Invoker.
- [Cloud Run ingress](https://docs.cloud.google.com/run/docs/securing/ingress) — classifying internal sources and network checks.
- [Cloud Run Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc) — networks/subnets, egress modes, and firewalls.
- [Cloud SQL PostgreSQL from Cloud Run](https://docs.cloud.google.com/sql/docs/postgres/connect-run) — private IP and TCP connectivity.
- [Connectivity Tests overview](https://docs.cloud.google.com/network-intelligence-center/docs/connectivity-tests/concepts/overview) — path analysis and data-plane checks.
- [Private Google Access](https://docs.cloud.google.com/vpc/docs/private-google-access) — accessing Google APIs from private networks.
- [Google Cloud Storage Java client](https://cloud.google.com/java/docs/reference/google-cloud-storage/latest/overview) — calling Storage with ADC.
