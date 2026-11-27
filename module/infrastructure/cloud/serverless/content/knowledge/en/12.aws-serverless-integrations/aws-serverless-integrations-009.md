# Combining Cognito, Secrets Manager, and Parameter Store

A Java Lambda function often needs to solve three things at once: identify who is calling the API, verify which operations that caller is permitted to perform, and retrieve configuration or credentials to access backend services. AWS provides specialized services for each: **Amazon Cognito** manages user identities and tokens, **AWS Secrets Manager** stores secrets, and **AWS Systems Manager Parameter Store** manages configuration parameters and `SecureString` values.

These services can work together within a single request flow, but they do not replace one another's permissions. Cognito tokens authenticate the user; the Lambda execution role lets function code read secrets or parameters; API Gateway or resource policies decide who can invoke the function. Designing clear boundaries avoids embedding passwords in source code, avoids trusting client-supplied claims, and scopes access strictly to each role's responsibility.

## Learning Objectives

After this lesson, you will be able to:

- Distinguish between Cognito User Pools and Identity Pools.
- Describe how API Gateway validates Cognito-issued JWTs before invoking Lambda.
- Distinguish identity authentication from business authorization in a Java handler.
- Choose between Secrets Manager and Parameter Store for different types of data.
- Use AWS SDK for Java 2.x to read secrets and parameters.
- Grant least-privilege permissions to the Lambda execution role, including KMS decryption permissions when needed.
- Design caching, TTLs, rotation, and error handling when secrets change.
- Avoid leaking tokens, passwords, API keys, or sensitive data into logs and events.

## 1. Roles of the Three Services

| Service | Primary responsibility | Example data or capabilities |
|---|---|---|
| **Amazon Cognito** | Sign-up, sign-in, user management, and token issuance | User Pool, access token, ID token, refresh token, user groups |
| **AWS Secrets Manager** | Storage, access control, and rotation support for secrets | Database passwords, API keys, external service credentials |
| **AWS Systems Manager Parameter Store** | Named and hierarchical configuration parameters; supports `SecureString` | Simple feature flags, endpoints, queue names, per-environment config, encrypted values |

A request can flow through the following steps:

~~~mermaid
flowchart TD
    A["Client signs in to Cognito"] --> B["Receive JWT"]
    B --> C["Call API Gateway with Bearer token"]
    C --> D["Cognito User Pool / JWT authorizer validates token"]
    D --> E["API Gateway invokes Java Lambda"]
    E --> F["Lambda checks business permissions from claims"]
    F --> G["Lambda execution role reads Secrets Manager / Parameter Store"]
    G --> H["Lambda accesses backend database or API"]
    H --> I["Return response"]
~~~

Cognito does not automatically grant Lambda permission to read Secrets Manager. Likewise, Secrets Manager does not authenticate API callers. Each step requires its own authentication and authorization mechanism.

## 2. Cognito User Pools vs. Identity Pools

The two pool types in Cognito serve different purposes.

### User Pool: Managing Users and Tokens

A **Cognito User Pool** is a user directory supporting registration, sign-in, authentication, and account management. After a user authenticates successfully, Cognito can issue the following tokens. ID tokens and access tokens are JWTs; the refresh token is a separate credential for requesting new tokens, not a JWT used to call business APIs:

- **ID token:** contains claims describing user identity, such as subject, email, or verified attributes.
- **Access token:** represents granted access within application scope and may contain scopes and groups.
- **Refresh token:** used to obtain new tokens per app client policy; do not send refresh tokens to business APIs as access tokens.

APIs typically receive the access token in a header:

~~~http
Authorization: Bearer <access-token>
~~~

Do not place real tokens in URL query strings because URLs can appear in access logs, browser history, or telemetry. Clients must protect tokens and transmit them over HTTPS.

### Identity Pool: Issuing Temporary AWS Credentials

A **Cognito Identity Pool** exchanges authenticated or anonymous identities for temporary AWS credentials via an IAM role. This is useful when a client application needs direct access to limited AWS resources, such as uploading objects to a dedicated prefix.

An Identity Pool does not replace a User Pool. An application can use a User Pool for sign-in and an Identity Pool to issue AWS credentials when direct AWS resource access is needed.

For Java Lambda backends, the common pattern is:

- The client signs in via a User Pool and sends an access token to the API.
- API Gateway validates the token.
- Lambda receives the request along with claims already verified by the authorizer.
- Lambda uses its own execution role to access databases, Secrets Manager, and Parameter Store.

Do not issue broad AWS credentials to clients just so the backend can read secrets. Secrets used by the backend belong under the execution role's permissions and must never be returned to clients.

### Selection Table

| Need | Suitable component |
|---|---|
| Sign-up, sign-in, and account management | Cognito User Pool |
| Authenticate API requests with JWTs | API Gateway Cognito authorizer or JWT authorizer |
| Grant temporary AWS credentials to clients | Cognito Identity Pool |
| Backend retrieves database password | Secrets Manager |
| Backend retrieves endpoints or per-environment config | Parameter Store |
| Backend reads `SecureString` | Parameter Store with IAM/KMS permissions |

## 3. Validating Cognito JWTs Before Invoking Lambda

You can have API Gateway validate JWTs before forwarding requests to Lambda. This keeps requests with invalid tokens out of business processing.

### API Gateway REST API

REST API supports a **Cognito User Pool authorizer**. Configure the authorizer with the User Pool and attach it to protected methods. If the method specifies authorization scopes, API Gateway treats the token as an access token and checks those scopes. If no scopes are configured, API Gateway treats the token as an ID token. Use access tokens for scope-checked routes and configure the app client to issue the appropriate resource server scopes.

### API Gateway HTTP API

HTTP API supports a **JWT authorizer**. With a Cognito User Pool, the issuer typically has the form:

~~~text
https://cognito-idp.<region>.amazonaws.com/<user-pool-id>
~~~

JWT authorizer configuration includes:

- Identity source, typically `$request.header.Authorization`.
- Issuer URL of the User Pool.
- Audience matching the app client ID; Cognito ID tokens usually use the `aud` claim, whereas access tokens use `client_id`.
- Authorization scopes on the route if the API requires specific scopes.

API Gateway verifies the JWT signature against the issuer's public keys, issuer, audience/client, expiration, and required token conditions. When a route requires scopes, the token must contain matching scopes. Exact configuration details differ between REST API and HTTP API, so confirm your API type before following setup instructions.

With HTTP API, configure explicit scopes on routes requiring access tokens; do not rely solely on audience matching to distinguish ID tokens from access tokens. If the application validates JWTs inside Lambda itself, also check `token_use=access` for business APIs.

### Validated Tokens Still Require Business Authorization

Token validation answers “is the token valid and which identity does it belong to?”. Business authorization answers “which resources is this identity allowed to view or modify?”.

For example, a valid access token does not mean the user is allowed to read every order. The Java service must still verify owner, tenant, role, or resource-level permissions. Do not trust `tenantId`, `userId`, or `role` sent by the client in the request body if those values could be forged. Extract subject and claims from the verified authorizer context and check against server-side business data.

If validating JWTs manually in code instead of using an authorizer, verify signature via JWKS, issuer, expiration (`exp`), `nbf` if present, app client/audience, and token type. Never just Base64-decode and trust the payload. With Cognito, distinguish ID tokens from access tokens; the `token_use` claim identifies token type during application-level validation.

### Java Handler: Extracting the Principal from Authorizer Context

Event structures differ between REST API and HTTP API. The adapter should map claims already verified by API Gateway into a clean internal model. The snippets below use Java records, requiring Java 16 or later (available on Lambda Java 17/21 runtimes):

~~~java
public record AuthenticatedPrincipal(
        String subject,
        String tenantId,
        java.util.Set<String> scopes) {
}

public record GetOrderCommand(String orderId) {
}

public final class GetOrderService {
    public OrderView get(
            AuthenticatedPrincipal principal,
            GetOrderCommand command) {

        // Repository must verify the order belongs to an authorized tenant/owner.
        return loadVisibleOrder(
                principal.subject(),
                principal.tenantId(),
                command.orderId());
    }

    private OrderView loadVisibleOrder(
            String subject,
            String tenantId,
            String orderId) {
        // Illustrates query boundary; implement repository in the persistence layer.
        return new OrderView(orderId, "PROCESSING");
    }
}

public record OrderView(String orderId, String status) {
}
~~~

The adapter reads claims from the exact request context structure of the API Gateway type in use and builds `AuthenticatedPrincipal`. Do not read claims from arbitrary client-supplied headers; the API Gateway authorizer context is the trusted source when integration and mapping are configured properly.

If using groups or custom claims for authorization, control who can modify those attributes, token lifetimes, and how permissions are revoked. The `tenantId` claim in the example exists only if the application explicitly injects it into the token via a controlled mechanism; otherwise, look up tenant membership server-side from the subject. Already issued tokens can remain valid until they expire per policy; changing permissions in the User Pool does not immediately alter existing tokens.

## 4. How Do Secrets Manager and Parameter Store Differ?

Both services can store configuration data, and Parameter Store can store encrypted values. However, they are optimized for different needs.

| Criterion | Secrets Manager | Parameter Store |
|---|---|---|
| Primary goal | Secrets management | Configuration parameter and `SecureString` management |
| Data types | Credentials, passwords, API keys, tokens | `String`, `StringList`, `SecureString` |
| Encryption | Encrypted with AWS KMS | `SecureString` encrypted with AWS KMS |
| Rotation | Built-in rotation mechanism, typically with Lambda or supported integrations | No built-in equivalent secret rotation workflow |
| Versioning | Secret versions and staging labels such as `AWSCURRENT`, `AWSPREVIOUS`, `AWSPENDING` | Parameter versions and labels |
| Hierarchy | Secret name/ARN | Hierarchical paths, e.g., `/prod/orders/database/host` |
| Best suited for | Secrets requiring lifecycle control and rotation | Operational config, per-environment parameters, simple `SecureString` values |

Practical selection rules:

- Use Secrets Manager for database passwords, credentials, and API keys requiring rotation or dedicated secret lifecycle management.
- Use Parameter Store for endpoints, queue names, business limits, simple feature configuration, and `SecureString` values when Secrets Manager lifecycle/rotation is unnecessary.
- Do not pick Parameter Store solely for price or simplicity if business requirements call for rotation and dedicated secret management.
- Do not store public configuration in a secret store merely as a substitute for structured configuration management.

Parameter Store has different tiers and limits on size, throughput, features, and cost. Check the tier matching your application's parameter count, size, and read frequency.

## 5. Storing Secrets Securely with Secrets Manager

A database secret can be stored as JSON:

~~~json
{
  "username": "orders_app",
  "password": "<secret-value>",
  "host": "orders-db.example.internal",
  "port": 5432,
  "dbname": "orders"
}
~~~

This example illustrates structure only. Never put real password values in source code, committed config files, Docker images, Lambda events, logs, or deployment docs.

The function usually only needs the secret ARN or name, for example via an environment variable:

~~~text
DB_SECRET_ARN=arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:prod/orders/database-AbCdEf
~~~

An ARN is a reference to the secret, not the secret value. Still, ARNs and secret names can reveal system structure, so share them only as needed.

### Reading Secrets with AWS SDK for Java 2.x

The following example retrieves a `SecretString` from Secrets Manager:

~~~java
import software.amazon.awssdk.services.secretsmanager.SecretsManagerClient;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueRequest;
import software.amazon.awssdk.services.secretsmanager.model.GetSecretValueResponse;

public final class SecretReader {
    private final SecretsManagerClient client;

    public SecretReader(SecretsManagerClient client) {
        this.client = client;
    }

    public String read(String secretArn) {
        GetSecretValueResponse response = client.getSecretValue(
                GetSecretValueRequest.builder()
                        .secretId(secretArn)
                        .build());

        String value = response.secretString();
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(
                    "Secret does not contain a SecretString");
        }
        return value;
    }
}
~~~

In Lambda, create the SDK client once per execution environment lifecycle if the client is thread-safe, then reuse it. Do not create and close the client on every request unnecessarily. Use the default credential provider chain so the SDK obtains credentials from the execution role; never hardcode access keys or secret keys.

If a secret uses `SecretBinary`, read the binary field instead of assuming `SecretString` is always populated. For JSON secrets, parse into a defined record or object, validate required fields, and never log objects containing passwords.

### IAM Permissions for Secrets Manager

Lambda's execution role needs `secretsmanager:GetSecretValue` on the exact secret ARN. Minimal policy example:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "secretsmanager:GetSecretValue",
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:prod/orders/database-*"
    }
  ]
}
~~~

If the secret uses a customer-managed KMS key, the role also needs `kms:Decrypt` on that key and the key policy must allow it. With Secrets Manager's AWS managed key, permission handling may differ; do not grant broad KMS permissions unnecessarily.

A secret's resource policy can be used for cross-account access or additional controls. In that case, evaluate the caller's identity policy, the secret's resource policy, and the KMS key policy together. Do not use a wildcard across all secrets in the account if the function needs only one secret.

## 6. Parameter Store: Hierarchical Configuration and SecureString

Parameter Store organizes parameters by name, commonly using hierarchical paths to separate environments, applications, and components:

~~~text
/prod/orders/api/base-url
/prod/orders/feature/new-checkout
/prod/orders/database/host
/prod/orders/database/password
/staging/orders/api/base-url
/staging/orders/database/host
~~~

Examples:

- `String`: non-sensitive endpoints or queue names.
- `StringList`: simple list of values.
- `SecureString`: values requiring encryption such as a protected password or token.

`SecureString` uses KMS for encryption. When reading with `WithDecryption=true`, SSM returns the decrypted value if the caller has the required permissions. With a customer-managed key, `kms:Decrypt` and an appropriate key policy are required.

### Reading Parameters with AWS SDK for Java 2.x

~~~java
import software.amazon.awssdk.services.ssm.SsmClient;
import software.amazon.awssdk.services.ssm.model.GetParameterRequest;
import software.amazon.awssdk.services.ssm.model.GetParameterResponse;

public final class ParameterReader {
    private final SsmClient ssm;

    public ParameterReader(SsmClient ssm) {
        this.ssm = ssm;
    }

    public String read(String parameterName, boolean secure) {
        GetParameterResponse response = ssm.getParameter(
                GetParameterRequest.builder()
                        .name(parameterName)
                        .withDecryption(secure)
                        .build());

        return response.parameter().value();
    }
}
~~~

For standard parameters, pass `secure=false`; for `SecureString`, pass `secure=true`. Do not log returned values. When reading multiple parameters, use batch APIs where appropriate to reduce request counts, while handling missing or access-denied parameters.

### IAM Permissions for Parameter Store

Example role permitted to read only parameters under the application's production path:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:GetParametersByPath"
      ],
      "Resource": "arn:aws:ssm:ap-southeast-1:123456789012:parameter/prod/orders/*"
    }
  ]
}
~~~

If only one parameter is needed, scope permissions to that specific parameter ARN and only the required action. When using `GetParametersByPath` recursively, read permissions on a parent path can cover child parameters; avoid granting broad paths if sensitive parameters live in sub-paths. When reading `SecureString` encrypted with a customer-managed KMS key, add `kms:Decrypt` scoped to that key. Verify the key policy, because an IAM allow alone may be insufficient if the key policy does not allow the principal to use the key.

### Choosing One Source of Truth per Configuration Value

Avoid storing the same value in environment variables, Parameter Store, and Secrets Manager simultaneously and letting the application pick at runtime. That creates ambiguity over which source is current and how to behave when values diverge.

An easy-to-operate convention:

- Environment variables hold secret names/ARNs, parameter paths, region, or non-sensitive configuration fixed per deployment.
- Parameter Store holds operational configuration that can change independently of code.
- Secrets Manager holds credentials and secrets needing lifecycle management.
- Databases or business services hold authoritative business data.

## 7. Combining Cognito, Lambda, and Secrets in a Single Request

Suppose `GET /orders/{id}` needs to authenticate a Cognito user and query a database using credentials stored in Secrets Manager.

Processing flow:

1. The client signs in to the Cognito User Pool and receives an access token.
2. The client calls API Gateway with an `Authorization: Bearer` header.
3. The API Gateway authorizer checks the token and route scopes.
4. API Gateway forwards the request and authorizer context to the Java Lambda.
5. The adapter builds an `AuthenticatedPrincipal` from verified claims.
6. The service checks whether the user is permitted to view the order belonging to their tenant.
7. The repository retrieves credentials from the secret cache or Secrets Manager using the execution role.
8. The repository queries the database.
9. Lambda returns a response stripped of sensitive data.

Authorization in step 6 must rely on trusted claims and business data. Never return database passwords, secret values, or Cognito tokens to the client.

### Distinguishing Three Permission Types

| Permission | Who uses it? | Example |
|---|---|---|
| API call permission | User/client | Cognito access token with scope `orders/read` |
| Lambda invoke permission | API Gateway or caller | Lambda resource policy allowing API Gateway to invoke the function/alias |
| Secret and database access permission | Java Lambda code | Execution role with `secretsmanager:GetSecretValue`, `ssm:GetParameter`, and network/credential DB access |

A request can pass Cognito authentication while Lambda is still denied secret access because its execution role lacks permissions. Conversely, Lambda having permission to read secrets does not mean every user is allowed to call the API. Monitor and handle these two failure classes independently.

## 8. Caching Secrets and Parameters in Lambda

Reading Secrets Manager or Parameter Store on every invocation increases network calls, latency, and cost. Values can be cached in the execution environment with a bounded TTL.

Because Lambda performs warm reuse, a static cache can persist across multiple invocations within the same environment. However, that cache:

- Is not shared across execution environments.
- Can be lost when Lambda reclaims the environment.
- Can hold stale values after secret rotation or parameter updates.
- Must be thread-safe if multiple threads in the same JVM access it concurrently.

You can use the AWS Secrets Manager caching library for Java or build a custom cache with an appropriate TTL and synchronization. The AWS Parameters and Secrets Lambda Extension is another option to read through a local HTTP endpoint and cache within the execution environment. The extension requires configuration, IAM permissions, and TTL settings; each environment's cache remains independent.

### Example Secret Cache with TTL

This code snippet illustrates caching a secret value within one JVM. In production, consider a supported caching library and add metrics/timeouts as needed.

This snippet also uses Java records, requiring Java 16 or later.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public final class TtlSecretCache {
    private final SecretReader reader;
    private final String secretArn;
    private final Clock clock;
    private final Duration ttl;
    private final Object refreshLock = new Object();

    private volatile CachedValue cached;

    public TtlSecretCache(
            SecretReader reader,
            String secretArn,
            Clock clock,
            Duration ttl) {
        this.reader = reader;
        this.secretArn = secretArn;
        this.clock = clock;
        this.ttl = ttl;
    }

    public String get() {
        CachedValue current = cached;
        if (isFresh(current)) {
            return current.value();
        }

        synchronized (refreshLock) {
            current = cached;
            if (isFresh(current)) {
                return current.value();
            }

            String value = reader.read(secretArn);
            CachedValue refreshed = new CachedValue(
                    value, clock.instant().plus(ttl));
            cached = refreshed;
            return refreshed.value();
        }
    }

    private boolean isFresh(CachedValue value) {
        return value != null && clock.instant().isBefore(value.expiresAt());
    }

    private record CachedValue(String value, Instant expiresAt) {
    }
}
~~~

TTL must be chosen based on rotation requirements and staleness tolerance. Never cache secrets indefinitely. When a cached secret expires and Secrets Manager is unavailable, the application must fail according to defined policy; do not silently fall back to stale credentials indefinitely.

If many invocations refresh the cache simultaneously, `synchronized` in the example coordinates threads only within a single JVM. Other execution environments may still call Secrets Manager concurrently. If system-wide load reduction is needed, use a cache service or an extension/library with appropriate behavior, while still enforcing TTLs and access controls.

## 9. Secret Rotation and Database Connections

Secrets Manager supports secret versioning with staging labels such as:

- `AWSCURRENT`: current active version typically read by consumers.
- `AWSPREVIOUS`: previous version.
- `AWSPENDING`: version being prepared during rotation.

A typical rotation workflow generates new credentials, applies them on the target system, tests the new credentials, and moves the `AWSCURRENT` label to the new version. With Lambda-based rotation, steps are typically structured as `createSecret`, `setSecret`, `testSecret`, and `finishSecret` phases.

Rotation works only when a rotation schedule and appropriate mechanism are configured for the secret/target service type. Not every API key or database rotates automatically simply by creating a secret.

### Applications Must Tolerate Rotation

Suppose a database password is rotated:

1. Secrets Manager generates or receives new credentials.
2. The database begins accepting the new credentials.
3. `AWSCURRENT` shifts to the new version after the rotation workflow completes.
4. Warm Lambda environments caching the old password may keep using it until cache TTL expires.
5. Connection pools may still hold connections opened with the old credentials.

Therefore:

- Cache TTL should be shorter than the business window during which old credentials remain valid.
- When receiving a database authentication error, evict the cache, re-read the secret, and retry once with bounds if the operation is safe.
- Connection pools need a policy to close/recycle old connections; updating a cached password does not change credentials on already open connections.
- Do not retry endlessly when the database rejects credentials.
- Test rotation with warm functions and active connection pools.

For non-idempotent writes, do not blindly rerun business logic just because the first connection attempt failed authentication. Distinguish authentication errors before a transaction starts from errors after the server committed and the response was lost.

## 10. Caching Parameter Store Values and Updating Configuration

Parameter Store versions each parameter. Updating a value creates a new version. Applications can read the current parameter or reference a specific version/label as needed.

If a function caches parameters, changes in Parameter Store do not automatically take effect immediately in running environments. Choose one of these strategies:

- Short TTL so functions refresh periodically on their own.
- Emit an event when configuration changes and trigger consumer invalidation.
- Use versions/labels in deployment configuration to pin tested values.
- Redeploy/restart environments when changes must take effect simultaneously.

Do not use ultra-short TTLs on every request if configuration rarely changes; that increases API calls and latency. Conversely, do not cache for long durations if configuration changes must take effect quickly.

For configuration affecting security or critical behavior, enforce approval workflows, auditing, and parameter version rollback. Parameter Store is a parameter store, not a substitute for application change management.

## 11. Security, Logging, and Error Handling

Apply these principles across the entire flow:

- Never log access tokens, refresh tokens, passwords, API keys, or secret JSON in logs, traces, metrics, or exception messages.
- Do not pass secrets inside event payloads between functions; pass secret ARNs or resource identifiers if a reference is needed.
- Do not store secret values in Lambda environment variables when they can be fetched directly from a secret store.
- Use HTTPS for APIs and TLS for connections to supporting services.
- Use IAM execution roles instead of static access keys.
- Restrict secret/parameter access strictly to the ARNs or paths the function needs.
- Enable CloudTrail/audit logging to monitor secret and policy management operations.
- Distinguish invalid token errors, missing permissions, missing secrets, KMS decrypt denials, and temporary service unavailability.
- Use bounded timeouts and retries; do not retry authorization or misconfiguration errors as transient errors.
- Redact sensitive data before logging, even when SDK exceptions include request context.

Never return internal errors such as full secret ARNs, database names, or KMS details to clients. Clients only need business error codes and a correlation ID for support investigation.

### Example Error Classification

| Error | Where handled | Handling approach |
|---|---|---|
| Expired or invalid JWT signature | API Gateway authorizer | Reject request; client re-authenticates |
| Valid token missing required scope | Authorizer/route or service | Return 403 per API contract |
| User does not own order | Business service | Deny resource access |
| Secrets Manager AccessDenied | Execution role/resource policy | Fix IAM or resource policy; do not retry endlessly |
| KMS Decrypt denied | IAM/key policy | Verify permissions on the exact KMS key |
| Secret temporarily unavailable | Secret provider | Retry with bounded backoff; use valid cached value if policy permits |
| Stale database credentials | Connection/provider layer | Controlled secret refresh, recycle connections, and retry safely |

## 12. Integration Testing

A test that merely invokes Lambda directly with a test event does not prove the full Cognito and secret-permission flow works properly.

Test these scenarios:

| Scenario | What to verify |
|---|---|
| Valid access token with sufficient scopes | Request reaches Lambda and processes the right principal |
| Expired token or wrong issuer | Authorizer rejects before business logic runs |
| Valid token missing required scope | Request is rejected per route policy |
| User A requests User B's order | Service checks owner/tenant and does not return data |
| Lambda lacks `GetSecretValue` permission | Invocation fails with safe logging and triggers an alert |
| Secret uses customer-managed KMS key | Execution role and key policy allow decrypting that specific secret |
| `SecureString` parameter | SDK reads with decryption and exact path |
| Secret rotation | Warm invocations pick up new credentials after TTL or refresh policy |
| Database connection pool holds stale credentials | Pool recycles per policy and requests recover safely |
| Parameter updated | Cache refreshes per TTL/event/version policy |
| Concurrent cache misses | Does not trigger a request storm overwhelming the secret store |
| Secret/parameter does not exist | Error is classified without exposing internal values or configuration |

Use a dedicated test AWS environment and mock secrets. Never use production credentials in unit tests or fixtures. For JWTs, adapter claims can be mocked in unit tests, while integration tests must verify the real authorizer validates tokens and scopes.

## 13. Implementation Checklist

- [ ] Selected User Pool for sign-in and used Identity Pool only when clients need temporary AWS credentials.
- [ ] API Gateway authorizer is configured properly for REST API or HTTP API.
- [ ] Sensitive routes require access tokens and appropriate scopes.
- [ ] Java handler trusts only claims coming from the verified authorizer.
- [ ] Service checks tenant, owner, and business permissions on resources.
- [ ] Secrets are stored in Secrets Manager or appropriate `SecureString`; never committed to source.
- [ ] Non-sensitive configuration is organized under clear Parameter Store paths.
- [ ] Lambda environment variables hold only ARNs/paths and required reference settings.
- [ ] Execution role has `GetSecretValue`/`GetParameter` only on necessary resources.
- [ ] KMS IAM policies and key policies permit decrypting the exact key when needed.
- [ ] Cache uses a TTL aligned with rotation and configuration update requirements.
- [ ] Credential refresh and connection pool recycling processes are in place for rotation.
- [ ] Tokens, secret values, passwords, and unnecessary personal data are excluded from logs.
- [ ] Timeouts, bounded retries, metrics, and alarms exist for secret/config failures.
- [ ] Tested tokens, scopes, tenant isolation, IAM denials, KMS, rotation, and cache expiration.

## Self-Check

1. How does a Cognito User Pool differ from an Identity Pool in purpose and the type of credentials issued?
2. Why is a valid Cognito access token not sufficient on its own to let a user read any order?
3. Which two boundaries do the API Gateway authorizer and Lambda execution role protect?
4. When should you choose Secrets Manager instead of Parameter Store `SecureString`?
5. Why does Lambda need `kms:Decrypt` permission in certain secret or `SecureString` read configurations?
6. What errors can caching a secret too long cause after credential rotation?
7. Why does updating a cached password not automatically update already open database connections?
8. If the secret store is temporarily unavailable, what must be considered before continuing to use a stale cached value?
9. Why should secret values or refresh tokens never be placed in logs or event payloads?

Cognito, Secrets Manager, and Parameter Store solve distinct parts of a serverless application: user identity, secrets, and operational configuration. When API Gateway validates tokens, Java services enforce business authorization, execution roles read only required resources, and caching/rotation are bounded, the application integrates these services while maintaining crisp security boundaries.
