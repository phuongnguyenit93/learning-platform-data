# Service-to-Service Authentication Using Workload Identity

In a serverless architecture, a Java function often calls a database, queue, object storage, or another HTTP service. The receiving service needs to know who the caller is and what the caller is allowed to do. If every function shares a single static API key or credential, exposing one component can widen the blast radius across the entire system.

Workload identity solves this problem by assigning an identity to the running workload itself. The platform verifies the workload through its runtime, service account, execution role, or federation mechanism, then provides short-lived credentials for calling other services. The identity is bound to the function, service, or Kubernetes workload, independent of a logged-in human user.

This lesson focuses on service-to-service authentication for Java serverless: distinguishing authentication from authorization, obtaining credentials safely from the runtime, calling target services, verifying inbound tokens, restricting permissions, and handling identity errors.

## 1. What Is Workload Identity?

A workload identity is an identity representing a running application or process. Examples:

- A Lambda function using an execution role to call S3 or DynamoDB.
- A Cloud Run service running with a Google service account to access Pub/Sub.
- An Azure Function using a managed identity to read Key Vault.
- A Kubernetes Pod using a service account that can be linked to a cloud identity via workload identity federation.
- A Java service using a client certificate or OIDC token to call an internal service.

This identity enables the security system to answer: which workload is calling, which environment or project does it belong to, and what permissions does it have?

A workload identity typically consists of:

1. **Subject/principal:** identifies the workload, service account, role, or principal.
2. **Trust mechanism:** how the platform proves the running process belongs to that principal.
3. **Credential:** token, signed request, or certificate used when calling services.
4. **Policy:** permissions that the principal is allowed to exercise.
5. **Resource boundary:** which principals the target resource accepts.
6. **Audit trail:** logs recording which principal performed which action.

A credential does not have to be a long-lived secret. Many platforms issue short-lived tokens or credentials through a metadata service, identity endpoint, or security token service.

## 2. Authentication and Authorization

Two concepts that are frequently confused:

- **Authentication:** verifying who the caller is.
- **Authorization:** deciding which actions that caller is allowed to perform on which resources.

For example, a Java worker calls the inventory-api service:

1. The worker acquires its workload identity from the runtime.
2. The worker presents its credential to inventory-api.
3. inventory-api verifies the issuer, signature, audience, and expiration of the credential.
4. The service resolves the principal corresponding to the worker.
5. The authorization policy checks whether the worker has the `invoice.read` permission.
6. The service returns the result or denies the request.

A valid token does not imply permission to access every endpoint. Conversely, a successful network connection does not prove the caller is allowed to read data.

| Layer | Question | Example Mechanism |
|---|---|---|
| Network | Can it connect to the destination? | VPC, firewall, network policy |
| Transport security | Is the channel encrypted and peer-verified? | TLS, mTLS |
| Authentication | Which principal is the caller? | IAM role, service account, OIDC token |
| Authorization | What is the principal allowed to do? | IAM policy, RBAC, application permission |
| Application validation | Are the data and business context valid? | Tenant check, ownership check, schema validation |

These layers complement one another. A private network does not replace authentication; TLS does not automatically grant business permissions; a valid JWT does not replace per-resource permission checks.

## 3. Call Flow Between Two Workloads

Suppose orders-worker needs to call inventory-api to reserve inventory. A secure flow can proceed as follows:

~~~mermaid
sequenceDiagram
    participant W as orders-worker
    participant I as Identity Provider / Runtime
    participant A as inventory-api
    participant P as Authorization Policy
    W->>I: Request credential for inventory-api
    I-->>W: Short-lived credential
    W->>A: HTTPS request + credential
    A->>A: Verify issuer, signature, audience, expiry
    A->>P: Check principal permission on action/resource
    P-->>A: Allow or Deny
    A-->>W: Response
~~~

The credential should be scoped to the exact target. If a token is issued for inventory-api, it should not be used to call another service with a different audience. Binding the audience reduces the risk of a token being replayed in an unintended place.

Workload identity avoids embedding API keys or service account private keys in source code, container images, or configuration files. The runtime or identity provider manages credential issuance and refresh.

## 4. Outbound and Inbound Identities

Both sides of a connection must be designed:

- **Outbound identity:** the Java service proves its identity when calling another service.
- **Inbound identity:** the Java service verifies the caller's identity when receiving requests.

For example, orders-api calling payment-service:

- orders-api needs a credential with an audience matching payment-service.
- payment-service needs to verify the credential and map the principal to a policy.
- The policy allows orders-api to invoke only required operations, such as creating a payment intent.
- orders-api must not by default have permissions to refund, view all transactions, or administer the payment service.

If you only configure outbound credentials while the target service does not verify the caller, the endpoint may still be callable by other principals. If you only verify inbound requests while the caller has no reliable way to obtain credentials, requests will fail.

### 4.1. Service Identity and End-User Identity

A request can carry both a service identity and a user identity:

- The service identity identifies which workload is making the call.
- The end-user identity identifies which user initiated the business action.

For example, the API gateway authenticates user Alice and calls orders-service. The service identity is api-gateway; the user identity is Alice. orders-service needs to know both when the policy requires: the gateway is allowed to call the endpoint, but Alice is only allowed to read her own orders.

Do not replace end-user identity with service identity. If every request is processed as the same service account without preserving the verified user context, per-user authorization can be bypassed.

When propagating user context between services, pass tokens or claims only through a trusted design with clear audience and expiration. Never trust an arbitrary `X-User-Id` header sent directly by a public client.

## 5. Short-Lived Credentials and Lifecycle

Long-lived credentials such as API keys or private keys can remain valid for months. If exposed, an attacker can use them until they are revoked or expire.

Short-lived credentials reduce the exposure window:

1. The runtime proves the workload belongs to a principal.
2. The identity provider issues a token or credential with a short lifetime.
3. The SDK or application uses the credential to sign requests.
4. Credentials are refreshed as needed.
5. Policies can change without rotating keys baked into images.

Some credential types:

| Credential | Used for | Notes |
|---|---|---|
| OAuth 2.0 access token | Calling protected APIs | Has expiry, scope/audience depending on the system |
| OIDC ID token | Proving identity to a specific audience | Not meant by default as an access token substitute for arbitrary APIs |
| AWS temporary credentials | Signing AWS API requests with SigV4 | Contains temporary access key, secret key, and session token |
| X.509 client certificate | Authenticating peers in mTLS | Requires issuance, rotation, and trust chain management |
| Kubernetes projected service account token | Proving a Pod's identity | Has audience and expiry, usable for federation |

Do not confuse access tokens and ID tokens. Access tokens typically represent API access rights; ID tokens carry identity assertions intended for an audience. The target service must verify the exact credential type according to the protocol it supports.

## 6. Cloud Workload Identity Models

Each cloud provider has its own implementation, but the general principle is using a runtime-attached identity and short-lived credentials.

| Platform | Workload identity | Common mechanism |
|---|---|---|
| AWS Lambda | Execution role | STS temporary credentials via runtime credential provider |
| Google Cloud Run / Functions | Service account attached to workload | Application Default Credentials and metadata server |
| Azure Functions | Managed identity | Azure Identity library and token credential |
| Kubernetes | ServiceAccount | Projected token, OIDC federation, or cloud workload identity integration |

Exact API names and permissions differ by service. Do not copy policies verbatim from one platform to another. Use the native identity mechanism of the runtime and official SDKs.

### 6.1. AWS Lambda Execution Role

Each Lambda function can attach its own execution role. When the function runs, AWS provides temporary credentials for the role via the runtime credential provider. AWS SDK for Java v2 automatically discovers credentials using the default credentials provider chain.

Example calling S3 in Java:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

public final class ReportReader {

    private final S3Client s3 = S3Client.create();

    public String readReport(String bucket, String key) {
        var request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();

        return s3.getObjectAsBytes(request).asUtf8String();
    }
}
~~~

`S3Client.create()` uses the AWS SDK default credential provider. Inside Lambda, the SDK retrieves temporary credentials for the execution role. Local development can use a profile or another environment-appropriate credential provider.

Do not create IAM user access keys and package them into Lambda environment variables. Grant `s3:GetObject` on the exact bucket/prefix that needs to be read. If the function only reads reports, do not grant permissions to delete buckets or administer S3.

### 6.2. Google Cloud Service Account

A Cloud Run service or Cloud Functions instance can run under a user-managed service account. The Java application uses Application Default Credentials (ADC) to fetch credentials from the runtime environment.

Example initializing a Google Cloud Storage client:

~~~java
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

public final class StorageAccess {

    private final Storage storage =
            StorageOptions.getDefaultInstance().getService();

    public byte[] readObject(String bucket, String objectName) {
        return storage.readAllBytes(bucket, objectName);
    }
}
~~~

In a properly configured Google Cloud environment, ADC finds the credentials provided by the runtime for the service account. There is no need to load a service account JSON key into the container.

When calling another Cloud Run service protected by IAM, the caller typically needs to obtain an OIDC ID token whose audience is the target service URL/custom audience and hold the `roles/run.invoker` permission on that service. This token authenticates the caller to Cloud Run; it does not replace access tokens used for other Google Cloud APIs.

### 6.3. Azure Managed Identity

Azure Functions can enable a system-assigned or user-assigned managed identity. The Java SDK uses the Azure Identity library to acquire tokens without storing client secrets in the application.

Example accessing Key Vault:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.security.keyvault.secrets.SecretClient;
import com.azure.security.keyvault.secrets.SecretClientBuilder;

public final class VaultAccess {

    private final SecretClient client =
            new SecretClientBuilder()
                    .vaultUrl("https://example-vault.vault.azure.net/")
                    .credential(new DefaultAzureCredentialBuilder().build())
                    .buildClient();

    public String readSecret(String name) {
        return client.getSecret(name).getValue();
    }
}
~~~

`DefaultAzureCredential` selects a credential appropriate for the environment. In an Azure runtime with a managed identity, the SDK can fetch a token from the identity endpoint. Local development can use signed-in developer credentials.

The managed identity still needs the proper role assignment or access policy on Key Vault. Having an identity does not mean default permission to read all secrets.

## 7. Kubernetes Service Account and Workload Identity Federation

When Java workloads run on Kubernetes, a Pod can be assigned a Kubernetes ServiceAccount. The Pod receives a projected token from the service account per cluster configuration. This token can be used to authenticate to the Kubernetes API or exchanged with a cloud identity provider via OIDC federation.

High-level federation flow:

1. The Pod receives a projected service account token.
2. The token asserts the namespace, service account, and audience.
3. The Cloud Security Token Service or identity provider verifies the token against the cluster's OIDC issuer.
4. The trust policy maps allowed subjects/service accounts to a cloud principal.
5. The workload receives short-lived credentials to call cloud APIs.

~~~mermaid
flowchart TD
    P["Java Pod + Kubernetes ServiceAccount"] --> T["Projected OIDC token"]
    T --> S["Cloud STS / Identity Provider"]
    S --> V["Validate issuer, subject, audience"]
    V --> R["Federated role / service account"]
    R --> C["Short-lived cloud credentials"]
    C --> A["Cloud API"]
~~~

Federation avoids storing cloud private keys in Kubernetes Secrets. However, the trust policy must restrict the exact issuer, namespace, service account, and audience. If the trust policy allows every service account in the cluster, a compromised Pod can obtain broader credentials than intended.

Do not attach the same admin service account to all workloads. Create distinct identities per application or responsibility group and grant permissions following least privilege.

## 8. OIDC Token, Issuer, and Audience

An OIDC ID token is typically a signed JWT. Upon receiving a token, the target service must verify at minimum:

- **Signature:** valid signature using a key from the trusted issuer.
- **Issuer (`iss`):** matches the configured identity provider.
- **Audience (`aud`):** token was issued for the current service.
- **Expiry (`exp`):** token has not expired.
- **Not before (`nbf`):** token is already active.
- **Subject (`sub`):** principal matches the policy.
- **Authorized party (`azp`) or client ID:** checked when required by the protocol.
- **Key rotation:** fetch signing keys by `kid` from the issuer's JWKS and handle caching/rotation safely.

Never merely decode a JWT and trust its payload. Decoding does not verify the signature. Never accept arbitrary signing algorithms declared by the token header; configure trusted algorithms and issuers on the server.

Audience is a critical boundary. A token with `aud=inventory-api` must not be accepted by `payment-api` simply because both share the same issuer. Each service should have a stable, explicit audience and accept only tokens issued for it.

If a token carries scopes or roles, the service must still map those claims to specific policies. Never use an arbitrary claim from an unverified token to make authorization decisions.

### 8.1. Verifying JWTs in Java

Use a maintained OIDC/JWT library instead of writing verification algorithms yourself. With Spring Security Resource Server, an application can configure an issuer URI so the framework fetches metadata and JWKS and checks signatures, issuer, expiration, and audience according to configuration.

Example Spring Security configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/health").permitAll()
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

The configuration above illustrates enabling a JWT resource server. The application must configure `issuer-uri` or `jwk-set-uri` in application config. Audience validation may require an additional validator depending on the issuer and framework version; do not assume that configuring only the issuer checks the audience required by your service.

Example properties:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://identity.example.com/
~~~

After authenticating the token, method-level or service-level authorization is needed to verify whether the principal is allowed to invoke the operation and access the specific resource.

## 9. Calling a Cloud Run Service with an OIDC ID Token

A Cloud Run service can require IAM authentication. The calling service needs invoke permission on the target service and must mint an ID token with the matching audience. The audience is typically the service's root URL or a configured custom audience.

Java example using the Google Auth Library to obtain an ID token from ADC:

~~~java
import com.google.auth.oauth2.IdTokenCredentials;
import com.google.auth.oauth2.IdTokenProvider;
import com.google.auth.oauth2.GoogleCredentials;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public final class CloudRunCaller {

    private final HttpClient httpClient = HttpClient.newHttpClient();

    public HttpResponse<String> call(
            String targetUrl,
            String audience) throws Exception {

        GoogleCredentials credentials =
                GoogleCredentials.getApplicationDefault();

        if (!(credentials instanceof IdTokenProvider idTokenProvider)) {
            throw new IllegalStateException(
                    "The runtime credential provider cannot mint ID tokens");
        }

        IdTokenCredentials idTokenCredentials =
                IdTokenCredentials.newBuilder()
                        .setIdTokenProvider(idTokenProvider)
                        .setTargetAudience(audience)
                        .build();

        var idToken = idTokenCredentials.refreshAccessToken();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(targetUrl))
                .header("Authorization", "Bearer " + idToken.getTokenValue())
                .GET()
                .build();

        return httpClient.send(
                request, HttpResponse.BodyHandlers.ofString());
    }
}
~~~

This is an illustrative example; the environment's credential provider must support minting ID tokens. In some environments or library versions, you may need to use `IdTokenProvider` directly from ADC or the corresponding credential API. Ensure the Google Auth Library dependency version is accurate and test in a real runtime.

The audience must match the target service's authentication configuration. The caller also needs the `roles/run.invoker` role on that service. If the token has the wrong audience or the caller lacks permission, the request is usually rejected even if the URL is reachable over the network.

Never send an ID token to an arbitrary URL supplied by user input. If an attacker controls the target URL, the application could inadvertently leak the bearer token to the attacker's server. Use an allowlist for target services and audiences.

## 10. AWS Service-to-Service Authentication

In AWS, many service APIs are protected by IAM and SigV4 signatures rather than bearer ID tokens. A Java service uses the AWS SDK with a credential provider that fetches temporary credentials from the execution role or an assumed role.

A function calling another AWS service typically needs:

1. Its own execution role.
2. Permissions on specific actions and resources.
3. A resource policy on the target service if required by that service.
4. SDK request signing with SigV4.
5. Auditing via CloudTrail or corresponding logs.

If a Lambda calls a private API Gateway or custom HTTP service, it can use IAM authorization/SigV4 if the endpoint supports it, or OIDC/mTLS per system design. Do not assume every HTTP service on AWS automatically authenticates using the execution role.

When cross-account AWS access is required, use `STS AssumeRole` with a trust policy restricting which principals can assume it and a session policy to narrow permissions if needed. Never use a single broad cross-account role across all functions.

## 11. Azure Managed Identity and Service-to-Service

In Azure, managed identities allow workloads to obtain access tokens for a target resource/audience. The target service must verify the token through Microsoft Entra ID and apply appropriate authorization.

A common pattern:

1. Function A has a managed identity.
2. The identity is granted permission to call service B's API or resource.
3. Function A uses the Azure Identity SDK to acquire a token for the corresponding scope/resource.
4. Function A sends the token over HTTPS.
5. Service B verifies the token and checks permissions.

A system-assigned identity is tied to the resource lifecycle; a user-assigned identity can be attached to multiple resources and exist independently. Choose based on lifecycle, reuse, and permission requirements. If multiple workloads share an identity, a compromised workload inherits that identity's full permission scope.

## 12. Least Privilege and Identity Separation

A key principle is that each workload has only the identity and permissions required for its task.

Example:

| Workload | Needed permissions | Should NOT have |
|---|---|---|
| orders-api | Write orders, publish order-created | Payment administration or reading all secrets |
| payment-worker | Call payment provider, update payment state | Deleting orders or administering the cluster |
| report-job | Read reporting data, write result files | Writing source transactional data |
| notification-worker | Send email/SMS via provider | Reading payment credentials if not needed |
| deployment pipeline | Deploy specific service and version | Runtime access to customer data |

Separating service accounts or roles per workload helps limit the blast radius. If one function is compromised, the attacker can only exercise that function's permissions rather than the whole application's permissions.

Avoid wildcard permissions whenever exact actions and resources can be specified. Review both identity policies and resource-based policies, since effective permissions can come from multiple places and be affected by explicit denies, permissions boundaries, or organization policies.

### 12.1. Per-Resource and Per-Tenant Authorization

Service identity only answers which workload is calling. If a service serves multiple tenants, tenant/resource checks are required at the application layer.

For example, `orders-worker` has permission to call `orders-api`, which does not mean it should access every tenant. Requests must carry an authenticated tenant context from a trusted source. The target service must verify which tenant an order belongs to before reading or modifying it.

Never take a tenant ID from an arbitrary unverified header. For events, verify that the producer is allowed to emit events for that tenant and correlate data with an authoritative source record.

## 13. mTLS and Service Mesh

Another option for service-to-service authentication is mutual TLS (mTLS). In standard TLS, the client verifies the server certificate. With mTLS, the server also requires a client certificate to verify the client's identity.

mTLS can be deployed at:

- A service mesh such as Istio or Linkerd.
- A sidecar proxy.
- An API gateway or ingress.
- Directly between HTTP client and server using certificates.

A service mesh can automatically issue and rotate workload certificates, enforce policies between namespaces/service accounts, and encrypt internal traffic.

mTLS authenticates the peer at the transport layer. Applications still require business authorization: a valid service certificate does not imply permission to invoke every operation. Combine mTLS with service-identity policies and application authorization when needed.

When using mTLS, you must manage CA trust, certificate rotation, expiration, SAN identity, and fallback behavior when the proxy/control plane is unavailable. Never create a single shared CA and distribute the CA's private key to every container.

## 14. Rotation, Caching, and Handling Expired Credentials

Short-lived credentials must be refreshed before expiration. Official SDKs usually provide credential providers that auto-refresh. Avoid caching an access token in a static field until expiration without a refresh mechanism.

Principles:

- Prefer the platform's default SDK credential providers.
- Never log access tokens, refresh tokens, session tokens, or private keys.
- Cache tokens per matching audience/scope and respect expiration.
- Refresh before token expiration, adding jitter to avoid all instances refreshing simultaneously.
- When receiving 401 due to an expired token, refresh via library mechanisms and perform bounded retries.
- Do not retry 403 infinitely, as it usually indicates a permission/policy error.
- When rotating certificates or keys, support an overlap period between old and new credentials if the system permits.

If many functions start concurrently and refresh credentials simultaneously, they can create a burst against the identity provider. SDK providers can manage refresh/caching at the process scope; continue monitoring identity endpoint latency and error rates.

## 15. Network, Private Endpoints, and Identity

A service can reside in a private network and still require workload authentication. Network policies restrict where connections can originate; identity determines who is connecting.

For example, only workloads inside a VPC can connect to a database, yet a database user or IAM database authentication still must verify permissions. Similarly, an internal HTTP API with only a private IP still needs mTLS, JWT, or IAM authorization if the data carries risk.

Do not use an IP allowlist as the sole identity. IPs can change during autoscaling, NAT, or redeployments. Use stable identity principals for per-service policies, and use network controls as a complementary layer.

If a service calls through a private endpoint, DNS and TLS hostnames must match the certificate. Never disable certificate verification to bypass hostname errors. Fix DNS, SAN, or endpoint configuration properly.

## 16. Auditing and Observing Identity

When an access incident occurs, you need to answer:

- Which workload made the call?
- Which principal or service account was used?
- Which resource and action were called?
- What were the credential issuer and audience?
- Which policy allowed or denied the request?
- Which revision/version sent the request?
- Were there any IAM or trust policy changes near the time of failure?

Log the principal name, service name, target service, operation, result, request/trace ID, and policy decision code. Never log raw tokens, private keys, session credentials, or full `Authorization` headers.

Cloud audit logs record principals and actions at the cloud layer. Application logs add business context. Trace context connects outbound calls to inbound requests.

Useful metrics:

- 401 and 403 rates by target service.
- Token acquisition latency and error rate.
- Credential refresh failures.
- mTLS handshake failures and certificate expiration.
- IAM denied actions by principal.
- Outbound call latency by service.
- Retry counts caused by auth failures.

A spike in 403s usually signals a policy or resource permission issue; a spike in 401s can indicate missing tokens, wrong issuer/audience, invalid signatures, or expired tokens. Never resolve either by granting broader permissions.

## 17. Testing Service Identity

Test both allowed and denied scenarios:

1. A workload with the right principal calls the right service and operation.
2. A workload with a different principal calling the same operation must be denied.
3. A token with an untrusted issuer.
4. A token with the wrong audience.
5. An expired token or one not yet valid.
6. A token with an invalid signature or obsolete key ID.
7. A valid principal lacking IAM permission.
8. A caller authorized to invoke the service but lacking permission on the tenant/resource.
9. Credential refresh when a token nears expiration.
10. Identity provider temporarily unavailable.
11. Conflicting resource policy and identity policy.
12. A workload deployed in a test environment cannot access production secrets.
13. An expired mTLS certificate or one missing a matching SAN.
14. Logs and traces contain no sensitive credentials.

Integration tests must run in an environment with real identities or an equivalent test identity provider. Unit tests can mock credential providers and authorization services, but they do not prove IAM trust policies or audiences are configured correctly.

## 18. Workload Identity Design Workflow for Java

1. **Map call flows.** Identify which service calls which service and which APIs/resources are accessed.
2. **Assign distinct principals.** Attach roles or service accounts per workload or responsibility group.
3. **Use short-lived credentials.** Prefer execution roles, managed identities, ADC, or federation.
4. **Configure trust.** Restrict issuer, subject, namespace, service account, and audience.
5. **Grant least privilege.** Allow only required actions and resources.
6. **Verify inbound requests.** Check signature, issuer, audience, expiry, and principal.
7. **Enforce business authorization.** Verify operation, tenant, and resource ownership.
8. **Use official SDKs.** Let SDKs manage credential acquisition, signing, and refresh.
9. **Protect the network.** Use TLS/mTLS, private endpoints, and network policies where appropriate.
10. **Audit and alert.** Monitor 401/403s, token refreshes, IAM denies, and certificate expiration.
11. **Test negative cases.** Verify unauthorized workloads are denied and secrets are never leaked.

Workload identity gives every Java function or service its own identity and short-lived credentials. By combining trust policies, audience validation, IAM least privilege, and business authorization, services can call one another securely without sharing a single static key across the entire system.

## 19. Self-Check Questions

- Who does a workload identity represent in the system?
- How does authentication differ from authorization?
- Why does a private network not replace service authentication?
- How do outbound identity and inbound identity differ?
- Why cannot access tokens and ID tokens be used interchangeably?
- How does the audience claim prevent a token from being misused on the wrong target?
- How does an AWS Lambda execution role supply credentials to the Java SDK?
- How do Google ADC and Cloud Run service accounts help avoid service account keys?
- How does an Azure managed identity differ from a client secret?
- Which claims does Kubernetes workload identity federation use to verify a Pod?
- Why does mTLS still require application-layer authorization?
- What should be logged to investigate 401/403s without exposing tokens?
- How do you prevent a service from accessing another tenant's data?
