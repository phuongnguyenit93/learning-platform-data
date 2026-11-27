# Authenticating with Configuration Files, Instance Principals, or Resource Principals

Every call to Oracle Cloud Infrastructure (OCI) requires an authenticated identity and appropriate access permissions. Spring Cloud OCI provides a core starter to auto-configure the authentication provider and shared infrastructure for service starters such as Object Storage, Vault, Queue, and Streaming.

There are three common authentication methods covered in this lesson:

- **Configuration file (`FILE`):** the application uses a profile in an OCI config file, typically suitable for developer workstations or environments where private keys can be controlled.
- **Instance Principal:** an application running on OCI Compute uses the identity of the compute instance itself.
- **Resource Principal:** an OCI resource such as a function uses an identity and token issued by OCI for that resource.

All three methods separate authentication from authorization. Authentication answers "who is calling the API"; IAM policies decide "what that identity is allowed to do on which resource". An application that authenticates successfully can still receive HTTP 403 if policies have not granted permission.

This lesson belongs to the **Oracle Cloud** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, focusing on identity and permission configuration when Spring Boot accesses OCI managed services, while placing these choices in the context of integrating storage, messaging, data, and secrets.

## 1. Learning Objectives

After this lesson, learners can:

1. Distinguish authentication, identity, and authorization in OCI.
2. Configure Spring Cloud OCI to use a profile in a config file.
3. Explain profile structure, API signing keys, fingerprints, tenancy, and region.
4. Distinguish `FILE` from `SIMPLE` and `SESSION_TOKEN`.
5. Configure Instance Principal for applications running on OCI Compute.
6. Create dynamic groups and least-privilege policies for instances.
7. Configure Resource Principal for OCI Functions or supported resources.
8. Create dynamic groups/policies for resource principals.
9. Distinguish Resource Principal from OKE Workload Identity.
10. Configure region and compartment according to the proper precedence order.
11. Diagnose 401, 403, wrong region, and expired credential errors.
12. Test actual identities and audit OCI calls.

## 2. Authentication and Authorization Are Two Separate Steps

When Spring Boot calls OCI Object Storage, Vault, or Queue, the SDK must sign requests with a valid identity. OCI verifies the signature/token and then checks IAM policies to decide whether to permit the operation.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Auth as OCI Authentication
    participant IAM as OCI IAM Policy
    participant Svc as OCI Service

    App->>Auth: Obtain credentials / token
    Auth-->>App: Identity + signing capability
    App->>IAM: Send signed request
    IAM->>IAM: Identify principal and policy
    alt Permitted
        IAM->>Svc: Allow operation
        Svc-->>App: API result
    else Missing permission
        IAM-->>App: 403 NotAuthorized
    end
~~~

Examples:

- A `FILE` profile authenticates via an OCI user and API signing key.
- Instance Principal authenticates via the Compute instance's identity.
- Resource Principal authenticates via the resource's identity, e.g., an OCI Function.
- IAM policies grant the principal permission to read objects, write objects, or read secrets.

Do not embed an admin user's API key into a workload just to make 403 errors go away. Identify the actual principal and grant least-privilege permissions to that principal.

## 3. Spring Cloud OCI Core Starter

Spring Cloud OCI provides a core starter to auto-configure OCI authentication and shared infrastructure. Service-specific starters build on this shared configuration.

Maven:

~~~xml
<dependency>
    <groupId>com.oracle.cloud.spring</groupId>
    <artifactId>spring-cloud-oci-starter</artifactId>
    <version>2.0.4</version>
</dependency>
~~~

Gradle:

~~~groovy
dependencies {
    implementation("com.oracle.cloud.spring:spring-cloud-oci-starter:2.0.4")
}
~~~

If the application only needs one service, the corresponding service starter can pull in the core starter transitively. For example, Object Storage uses `spring-cloud-oci-starter-storage`, and Vault uses `spring-cloud-oci-starter-vault`. Inspect the dependency graph for your exact release to see whether core is already pulled in.

Key common properties:

| Property | Meaning |
| --- | --- |
| `spring.cloud.oci.config.type` | Authentication type |
| `spring.cloud.oci.config.profile` | Profile name in the OCI config file |
| `spring.cloud.oci.config.file` | Path to the OCI config file |
| `spring.cloud.oci.config.userId` | User OCID for `SIMPLE` |
| `spring.cloud.oci.config.tenantId` | Tenancy OCID for `SIMPLE` |
| `spring.cloud.oci.config.fingerprint` | Fingerprint of the public API key |
| `spring.cloud.oci.config.privateKey` | Private key path for `SIMPLE` |
| `spring.cloud.oci.config.passPhrase` | Passphrase if the private key is encrypted |
| `spring.cloud.oci.config.region` | Region obtained from auth configuration |
| `spring.cloud.oci.config.federation-endpoint` | Optional token federation endpoint for principal-based auth |
| `spring.cloud.oci.region.static` | Fixed region used for API calls |
| `spring.cloud.oci.compartment.static` | Default compartment |

In Spring Cloud OCI 2.0.4, `FILE` is the default value of `spring.cloud.oci.config.type`. Supported types include `FILE`, `SIMPLE`, `INSTANCE_PRINCIPAL`, `RESOURCE_PRINCIPAL`, `SESSION_TOKEN`, and `WORKLOAD_IDENTITY`. Verify properties against your exact release line.

## 4. Configuration File Authentication (FILE)

`FILE` is the standard approach for local development. The application reads a profile from an OCI SDK/CLI config file. A profile typically contains:

- `user`: OCID of the OCI user.
- `tenancy`: OCID of the tenancy.
- `fingerprint`: fingerprint of the registered public key.
- `key_file`: path to the private API signing key.
- `region`: default region.
- `pass_phrase`: passphrase if the private key is encrypted.

Config file example:

~~~ini
[DEFAULT]
user=ocid1.user.oc1..example
fingerprint=11:22:33:44:55:66:77:88
tenancy=ocid1.tenancy.oc1..example
region=ap-singapore-1
key_file=/home/developer/.oci/oci_api_key.pem

[INVOICE_DEV]
user=ocid1.user.oc1..example
fingerprint=11:22:33:44:55:66:77:88
tenancy=ocid1.tenancy.oc1..example
region=ap-singapore-1
key_file=/home/developer/.oci/invoice_dev_api_key.pem
~~~

This is an illustrative example; do not use fake OCIDs or fingerprints in real environments. The default file is typically located at `~/.oci/config` on Linux/macOS or the `.oci` folder under the user profile on Windows.

### 4.1. Spring Boot Configuration

You can select a specific profile and file:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: INVOICE_DEV
        file: /run/secrets/oci/config
      region:
        static: ap-singapore-1
      compartment:
        static: ocid1.compartment.oc1..example
~~~

If using the default location and `DEFAULT` profile, you may only need:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
~~~

Do not place private key contents into `application.yaml`. The config file should live outside the source repository and only be readable by the required user/process. On Linux, restrict file permissions according to least privilege; never leave private keys world-readable.

### 4.2. Creating a Config File

The OCI CLI can assist with interactive setup. A typical local workflow:

1. Install the OCI CLI following official documentation.
2. Run `oci setup config` or the appropriate bootstrap flow.
3. Generate an API signing key.
4. Register the public key with the OCI user.
5. Store the private key in a protected location.
6. Choose region and profile.
7. Verify the configuration with the OCI CLI.
8. Configure Spring Boot to use the same file/profile.

A successful OCI CLI test verifies the basic profile and key, but it does not prove the application has the exact IAM policies for a specific operation. Test service operations using the exact target identity.

### 4.3. When to Use FILE?

Suitable for:

- Local development.
- Admin tools running on a personal workstation with credential protection.
- Temporary CI jobs with secret injection and controlled key lifecycles.
- On-premises environments lacking suitable federation/workload identity.

Do not use a developer's personal API key as a long-term identity for production Compute/Functions. Keys can be leaked, expire during rotation, or carry broader permissions than the service needs.

## 5. SIMPLE and SESSION_TOKEN: Related Options

Although this lesson focuses on `FILE`, Instance Principal, and Resource Principal, Spring Cloud OCI also supports two common alternatives.

### SIMPLE

`SIMPLE` puts credential fields directly into Spring configuration:

~~~properties
spring.cloud.oci.config.type=SIMPLE
spring.cloud.oci.config.userId=INJECT_USER_OCID
spring.cloud.oci.config.tenantId=INJECT_TENANCY_OCID
spring.cloud.oci.config.fingerprint=INJECT_FINGERPRINT
spring.cloud.oci.config.privateKey=/run/secrets/oci/private-key.pem
spring.cloud.oci.config.passPhrase=INJECT_KEY_PASSPHRASE
spring.cloud.oci.config.region=ap-singapore-1
~~~

`userId`, `tenantId`, `fingerprint`, `privateKey`, and `region` are required per the core starter guide; `passPhrase` is optional. Never put literal private keys or passphrases in the repository. `SIMPLE` is still user API key authentication, not an identity bound to a Compute instance or Function.

### SESSION_TOKEN

`SESSION_TOKEN` uses temporary session tokens, usually created via the OCI CLI through `oci session authenticate`. Session tokens have a short default lifetime (commonly 60 minutes); upon expiration, re-authentication/refresh is needed per workflow.

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: SESSION_TOKEN
        profile: DEFAULT
        file: /run/secrets/oci/session-config
~~~

The profile/file usage must match the session config generated by the OCI CLI. `SESSION_TOKEN` is useful for temporary local workflows, but not a good fit for a continuously running server workload without an appropriate renewal mechanism.

## 6. What Is an Instance Principal?

Instance Principal allows an OCI Compute instance to call OCI APIs using the instance's own identity. The application does not need a developer's OCI user OCID, API key, or config file.

High-level flow:

1. Create a Compute instance.
2. Create a dynamic group and a matching rule identifying the instance.
3. Create IAM policies granting permissions to the dynamic group.
4. Configure Spring Cloud OCI to use `INSTANCE_PRINCIPAL`.
5. The SDK retrieves authentication credentials from the instance identity/authentication endpoint.
6. Requests are signed with the instance's credentials.

Instance Principal is meant for Compute instances/VMs on OCI. Do not select it simply because the application runs in any container; the container must actually run inside a Compute environment supporting that identity.

### 6.1. Spring Boot Configuration

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
      compartment:
        static: ocid1.compartment.oc1..example
~~~

The core starter can accept an optional `federation-endpoint` for Instance Principal, Resource Principal, or Workload Identity. Normally you do not need to set this endpoint manually if the SDK/starter resolves it automatically. Configure it only when your environment or release documentation requires a specific endpoint.

### 6.2. Creating a Dynamic Group

A dynamic group defines a set of OCI resources treated as principals. For example, matching a specific Compute instance:

~~~text
ALL {instance.id = 'ocid1.instance.oc1..example'}
~~~

Or matching instances by compartment/tag. Avoid placing every instance in the tenancy into one dynamic group when a workload only needs minimal permissions.

A dynamic group does not grant permissions on its own. It only defines membership; IAM policies grant permissions to that group.

### 6.3. Granting IAM Policies

Example where an application only needs to read objects in a compartment:

~~~text
Allow dynamic-group InvoiceComputeInstances to read buckets in compartment InvoiceData
Allow dynamic-group InvoiceComputeInstances to read objects in compartment InvoiceData
~~~

If the application needs to upload objects, the policy needs the verb/resource type matching write operations, such as `manage objects` within the required scope. Restrict scope by compartment or bucket condition whenever policy grammar and the use case allow.

Do not grant `manage all-resources in tenancy` just to test quickly. Tailor policies by service and operation.

### 6.4. Verifying Instance Principal

- Verify the instance OCID matches the dynamic group matching rule.
- Verify the dynamic group was created in the right tenancy.
- Verify policies were created in the right tenancy/compartment.
- Verify the region endpoint and network route.
- Check Audit logs to confirm the actual principal of requests.
- Call a small operation matching the granted permission.

After changing a matching rule or policy, allow time for IAM propagation/caching before retrying. Do not immediately switch to a user API key when hitting a 403; inspect the principal and policy first.

## 7. What Is a Resource Principal?

Resource Principal lets a non-Compute OCI resource authenticate with other OCI services. A typical case is OCI Functions calling Object Storage, Vault, or another OCI API.

The OCI runtime supplies tokens and credential material to the resource. The SDK uses these credentials to sign requests. The application does not need to package a developer's API key or manage a static private key.

Resource Principal can be used by OCI resources that support and are configured for it. Do not assume every container or workload outside OCI has a Resource Principal.

### 7.1. Spring Boot Configuration

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: RESOURCE_PRINCIPAL
      region:
        static: ap-singapore-1
      compartment:
        static: ocid1.compartment.oc1..example
~~~

When running in OCI Functions, the SDK fetches resource principal info from the OCI-provided execution environment. Do not craft fake RPST files or copy tokens from a function runtime into a container image. Never log tokens or private keys.

### 7.2. Dynamic Group for OCI Functions

A dynamic group can select functions by resource type and compartment. Example:

~~~text
ALL {
  resource.type = 'fnfunc',
  resource.compartment.id = 'ocid1.compartment.oc1..example'
}
~~~

Matching rules must match the actual resource type/OCID of the environment. You can restrict further by function/application/tag if organizational policy requires it.

### 7.3. IAM Policy for Resource Principal

Example where a function needs to read objects:

~~~text
Allow dynamic-group InvoiceFunctions to read buckets in compartment InvoiceData
Allow dynamic-group InvoiceFunctions to read objects in compartment InvoiceData
~~~

If the function needs to write objects, use a policy permitting writes and restrict scope appropriately. Do not grant function administration or network permissions just because the function needs to read Object Storage; permissions to deploy/operate a function and runtime permissions to access services are two separate policy sets.

### 7.4. Tokens and Caching

Resource Principal relies on runtime-issued tokens/credentials managed by the SDK. Tokens expire and are cached/refreshed by the SDK/runtime mechanism. Do not cache tokens indefinitely yourself or write custom request-signing logic when the OCI SDK already provides the standard provider.

When changing dynamic groups/policies, effects may not appear immediately due to propagation and token caching. Check service-specific documentation for expected wait times; do not assume one universal number for every resource principal.

## 8. Comparing FILE, Instance Principal, and Resource Principal

| Criterion | FILE | Instance Principal | Resource Principal |
| --- | --- | --- | --- |
| Identity | OCI user | OCI Compute instance | OCI resource, e.g., Function |
| Credential | API signing key in config profile | Provided by Compute identity | Token/credential provided by resource runtime |
| Config file | Yes | Not needed | Not needed |
| IAM grant | User/group policy | Dynamic group + policy | Dynamic group + policy |
| Typical environment | Local development | OCI Compute VM | OCI Functions or supported resources |
| Credential lifecycle | Key managed by operator | Managed by OCI/SDK | Managed by OCI runtime/SDK |
| Primary risk | Private key exposure | Overly broad dynamic group/policy | Misconfigured policy/resource matching, token/runtime issues |

Selection rules:

- Developing on a laptop: `FILE` or `SESSION_TOKEN`.
- Running on OCI Compute: prefer Instance Principal.
- Running in OCI Functions: prefer Resource Principal.
- Running on OKE: use Workload Identity specifically.
- Running outside OCI: use organization-approved API key/federation; do not emulate Instance Principal.

## 9. OKE Workload Identity Is Not Resource Principal

OKE has its own Workload Identity mechanism. It identifies workloads by the combination of cluster, namespace, and Kubernetes service account. IAM policies can grant permissions to that exact workload.

In Spring Cloud OCI, configuration is supported via:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: WORKLOAD_IDENTITY
~~~

You must configure an OKE enhanced cluster, namespace, service account, and corresponding policies. Workload identity policies use principal conditions such as `request.principal.type = 'workload'`, namespace, service account, and cluster OCID.

Key differences:

- Workload Identity is built for workloads on OKE.
- It is only available on enhanced clusters per OCI documentation.
- Do not use dynamic groups for OKE workload identity.
- IAM policies bind directly to cluster, namespace, and service account.
- The OCI Java SDK version in use must support workload identity.
- Reuse a single provider instance to leverage token caching rather than creating multiple providers and repeatedly fetching tokens.

Do not switch `WORKLOAD_IDENTITY` to `RESOURCE_PRINCIPAL` just because both use OCI-issued tokens. Pick the right provider for the runtime.

## 10. Region and Compartment

Authentication can succeed while requests still hit the wrong region or target the wrong compartment.

### Region Precedence

Per Spring Cloud OCI core:

`spring.cloud.oci.region.static` takes higher precedence than `spring.cloud.oci.config.region` and the region in the OCI auth config file.

Example:

~~~yaml
spring:
  cloud:
    oci:
      region:
        static: ap-singapore-1
      compartment:
        static: ocid1.compartment.oc1..example
~~~

Set a static region only when you want one default region across clients. If the application operates across multiple regions, configure clients/operations per region explicitly rather than relying on one global default.

### Compartment

Compartments are the management and policy scope for resources. `spring.cloud.oci.compartment.static` sets the default compartment for integrations using this property; it neither grants permissions by itself nor overrides every compartment ID required by specific operations/services.

Verify three values:

1. The region where the resource actually exists.
2. The compartment containing the resource.
3. The policy scope for the principal.

## 11. Configuration by Environment

Separate local, test, and production configs so personal API keys are never carried into workloads.

### Local Profile

~~~yaml
spring:
  config:
    activate:
      on-profile: local
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
        file: /home/developer/.oci/config
      region:
        static: ap-singapore-1
~~~

### Compute Production Profile

~~~yaml
spring:
  config:
    activate:
      on-profile: oci-compute
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: ap-singapore-1
~~~

### Functions Production Profile

~~~yaml
spring:
  config:
    activate:
      on-profile: oci-functions
  cloud:
    oci:
      config:
        type: RESOURCE_PRINCIPAL
      region:
        static: ap-singapore-1
~~~

Do not activate multiple authentication profiles simultaneously in a way that creates ambiguous configuration. Pick one identity strategy per runtime deployment and verify the final resolved configuration after Spring merges profiles and environment variables.

## 12. Least Privilege by Service

A principal should only be granted the exact permissions required for its operations.

| Use Case | Reference Permission | Notes |
| --- | --- | --- |
| List buckets | `read buckets` | Restrict to compartment |
| Read objects | `read objects` | No delete permission needed |
| Upload objects | `manage objects` or matching specific permission | Restrict by bucket/compartment |
| Read secrets | Matching secret bundle read permission | Do not grant Vault admin unless required |
| Send messages to Queue | Matching queue use permission | Separate producer identity if needed |
| Consume messages | Matching consume/queue operation permission | Check service-specific policy docs |
| Write logs | Permission to write logs to log group/log | No full Logging admin required |

Exact verbs and resource types depend on the OCI service. Check the IAM policy reference and policy examples for that service. Overly broad policies can mask misconfigurations while increasing the blast radius if credentials are compromised.

## 13. Testing Authentication

Testing must verify both the principal and operations, not merely that the application context starts.

### Test Matrix

| Environment | How to Test | What to Verify |
| --- | --- | --- |
| Local `FILE` | Use a test profile | Can read permitted buckets/objects |
| Local `SESSION_TOKEN` | Use an unexpired session token | Requests succeed before expiry |
| Compute | Deploy to an instance in the dynamic group | Audit identifies the instance principal |
| Functions | Invoke a function in an app configured with resource principal | Function accesses target services |
| OKE | Pod using configured service account | Audit identifies the workload identity |
| IAM negative test | Omit permission for an operation | Request is properly denied |

### Spring Context Test Example

~~~java
@SpringBootTest
class OciAuthenticationContextTest {

    @Autowired
    ApplicationContext context;

    @Test
    void ociCoreIsConfigured() {
        assertThat(context).isNotNull();
    }
}
~~~

A context test only proves the application context boots. It does not prove the OCI identity has permissions. You need integration tests calling a real API in a test compartment and verifying Audit logs/principals.

### Testing Least Privilege

1. Grant read permission on a test bucket.
2. Verify the read operation succeeds.
3. Attempt to write or delete an object when policy forbids it.
4. Verify the operation is denied.
5. Expand the policy strictly to the required operation.
6. Re-run tests to prove only the necessary permissions are granted.

## 14. Diagnosing Common Errors

### 401 NotAuthenticated or Signature Errors

Check:

- Whether user OCID, tenancy OCID, and fingerprint match the registered public key.
- Whether the private key file and passphrase are correct.
- Whether the config file/profile was loaded.
- Whether the session token has expired.
- Whether the machine has significant clock skew.
- Whether the instance/resource principal provider is running in a supported runtime.
- Whether the region/federation endpoint is correct.

Never paste private keys, session tokens, or full signed requests into tickets or logs.

### 403 NotAuthorizedOrNotFound

Authentication may have succeeded while policies forbid the operation. Check:

- Whether the actual principal is a user, instance, resource, or workload.
- Whether the dynamic group matching rule matches the resource.
- Whether the policy specifies the exact dynamic group name/domain.
- Whether verb/resource type are sufficient.
- Whether compartment/bucket scope is correct.
- Whether policy propagation/token cache has had time to refresh.

Do not switch to an admin API key to "confirm quickly". That masks IAM defects.

### 404 or Resource Not Found

Check region, compartment, namespace/bucket/queue OCID, and endpoint. A resource in another region cannot be found by a default client pointing at the wrong region.

### Works Locally but Fails in Production

A local `FILE` profile and a production Instance/Resource Principal are two different identities. Compare IAM policies, dynamic group membership, runtime, region, compartment, and audit principal. Do not infer production policies from local results.

### Instance Principal Cannot Obtain Credentials

- Confirm the process runs on an OCI Compute instance.
- Verify the instance metadata/authentication endpoint is reachable.
- Check the dynamic group matching rule.
- Check IAM policies.
- Verify SDK/starter versions.
- Ensure network/proxy rules do not block metadata/federation endpoints.

### Resource Principal Does Not Work in a Container

- Confirm the container runs inside OCI Functions or a supported resource runtime.
- Verify resource principal environment/credentials provided by the OCI runtime.
- Check whether the dynamic group rule matches the Function.
- Check policies and region.
- Do not craft fake RPSTs or copy credentials from another function.

### Workload Identity Fails on OKE

- Verify the cluster is an enhanced cluster.
- Check namespace and service account in the Pod spec.
- Check the cluster OCID in the IAM policy.
- Do not create a dynamic group for workload identity.
- Verify the OCI Java SDK version supports it.
- Reuse a single provider so token caching works properly.

## 15. Observability and Auditing

OCI Audit records API activity and the associated principal. Use Audit to determine which identity executed a request and when.

In the application, log non-sensitive fields:

- Selected authentication type.
- Region and compartment ID per logging policy.
- OCI service and operation.
- HTTP status/error code.
- OCI request ID when available.
- Application correlation ID.

Do not log:

- Private keys or passphrases.
- Session tokens/RPSTs.
- Authorization headers or request signatures.
- Secret values.
- Sensitive payload contents.

You can emit metrics by auth type, 401/403 counts, token refresh errors, request latency, and service operations. Avoid high-cardinality metric labels such as user OCID, request ID, or tokens.

## 16. Lab Exercise: Invoice API on Compute and Function

**Context:** Invoice API runs on OCI Compute and needs to read PDF files from Object Storage. An OCI Function processes PDFs upon receiving events and writes results back to an output bucket. Both workloads need separate identities and separate policies.

### Part A — Local Development with FILE

1. Create an OCI CLI config profile for developers.
2. Register the API signing public key.
3. Store the private key outside the repository.
4. Configure Spring Cloud OCI to use `FILE` and the corresponding profile.
5. Call the API to read objects in a test bucket.
6. Verify the policy permits reading only.

### Part B — Compute with Instance Principal

1. Provision a Compute instance for Invoice API.
2. Create a dynamic group matching only that instance or selected tag/compartment.
3. Grant policies to read the needed bucket/objects.
4. Configure `INSTANCE_PRINCIPAL`.
5. Deploy the application and read a PDF.
6. Verify Audit logs identify the instance principal.
7. Attempt writing an object when not permitted by policy and verify it is denied.

### Part C — Function with Resource Principal

1. Create an OCI Function to process PDFs.
2. Create a dynamic group matching the Function resource.
3. Grant permissions to read the input bucket and write the output bucket.
4. Configure `RESOURCE_PRINCIPAL`.
5. Deploy the function and process a test file.
6. Verify no personal API keys exist in the image/config.
7. Inspect Audit logs and the output object.

### Part D — Comparison and Operations

1. Compare the Compute and Function principals.
2. Separate policies so the Function cannot read/delete data outside its scope.
3. Rotate the local API key and verify the production app is unaffected.
4. Collect 401/403 responses and request IDs.
5. Write a runbook for dynamic group or policy changes.

### Deliverables

- `FILE` configuration for local development.
- Instance Principal configuration for Compute.
- Resource Principal configuration for Function.
- Dynamic group matching rules.
- IAM policy matrix by service/operation.
- Integration test evidence for object reads/writes.
- Audit evidence confirming the exact principals.
- Table of 401/403 errors and resolutions.
- Runbook for key rotation and policy updates.

## 17. Self-Check Questions

1. How do authentication and authorization differ?
2. Which fields does a `FILE` profile need to sign requests?
3. Why shouldn't an OCI private key be committed to a repository?
4. How does `SIMPLE` differ from `FILE`?
5. Which workflows suit `SESSION_TOKEN`?
6. Where does an Instance Principal obtain its identity?
7. Does a dynamic group grant permissions on its own?
8. Why does an Instance Principal still need IAM policies?
9. Which runtimes suit Resource Principal?
10. Where does an OCI Function receive resource principal credentials from?
11. Why shouldn't RPSTs or private keys be written to logs?
12. How does OKE Workload Identity differ from Resource Principal?
13. Does Workload Identity use dynamic groups?
14. Does `region.static` take precedence over the region in the config file?
15. Why isn't a 403 necessarily an authentication failure?
16. How can you inspect the actual principal via Audit?
17. How can you test least privilege for Object Storage?

## 18. Key Takeaways

- Spring Cloud OCI core starter auto-configures authentication and shared infrastructure for service starters.
- `FILE` is the default; profiles contain user, tenancy, fingerprint, key file, and region.
- `SIMPLE` also uses a user's API key; it does not turn it into a workload identity.
- `SESSION_TOKEN` uses temporary credentials suitable for local workflows with refresh.
- Instance Principal uses the Compute instance's identity; it requires a dynamic group and IAM policy.
- Resource Principal uses the identity of supported OCI resources, typically OCI Functions; it requires a dynamic group and IAM policy.
- OKE Workload Identity is a distinct mechanism available only on enhanced clusters and does not use dynamic groups.
- `spring.cloud.oci.region.static` takes precedence over the region in the auth config file.
- Successful authentication does not guarantee API permission; 403 errors typically require checking principal, policy, resource type, and compartment.
- Never store API keys, RPSTs, session tokens, or private keys in source control or logs.
- Test in real runtimes and use OCI Audit to verify the principal.
- Grant least-privilege permissions per workload, service, operation, and compartment.

## References

- [Spring Cloud OCI 2.0.4 — OCI Core and authentication](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/)
- [OCI SDK Authentication Methods](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdk_authentication_methods.htm)
- [OCI SDK and CLI Configuration File](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)
- [Calling Services from Instances](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/callingservicesfrominstances.htm)
- [Managing Dynamic Groups](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingdynamicgroups.htm)
- [Accessing OCI Resources from Running Functions](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsaccessingociresources.htm)
- [Granting Workloads Access to OCI Resources](https://docs.oracle.com/en-us/iaas/Content/ContEng/Tasks/contenggrantingworkloadaccesstoresources.htm)
