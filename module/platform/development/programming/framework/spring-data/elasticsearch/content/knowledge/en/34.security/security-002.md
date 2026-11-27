# Service Accounts, API Keys, and Least Privilege

A Spring Data Elasticsearch application needs its own identity to authenticate when connecting to Elasticsearch. This identity is often referred to as a service account, though you should distinguish organization-managed technical users from Elastic Stack's built-in service accounts reserved for specific Elastic Stack components. For business applications, a scoped API key is often the right choice; in some environments, a dedicated technical user with minimal roles can also be used.

The security goal is for each application to perform only the operations it needs on its exact indices or data streams. A service that only reads the catalog does not need write access; a worker that only indexes events does not need permission to delete indices or manage users. If a credential is compromised, the blast radius is therefore contained.

This lesson covers choosing an identity, designing roles, creating and using API keys, configuring Spring Data Elasticsearch, managing secrets and rotating credentials, verifying effective privileges, and troubleshooting issues.

## 1. Technical Identities When Connecting to Elasticsearch

### 1.1. Why not use personal accounts?

If multiple applications share a personal account or an administrative account, it becomes very hard to tell which request belongs to which application. When staff changes occur, credentials may have to be rotated in many places. An accidental action executed with broad privileges can also affect data outside the service's scope.

A dedicated identity per workload helps:

- Identify which application or job is calling Elasticsearch.
- Grant permissions independently per environment and function.
- Revoke one service's credential without disrupting other services.
- Monitor activity and investigate incidents more easily.
- Rotate secrets on schedule or upon suspected exposure.
- Limit impact if a credential is misused.

Every significant workload should have its own identity. For example, `catalog-api`, `catalog-indexer`, and `reporting-worker` may need different privileges even while reading or writing the same Elasticsearch cluster.

### 1.2. Distinguishing identity types

| Identity Type | Purpose | When Suitable |
|---|---|---|
| User account | Human identity | Administration, operations, or interactive access |
| Technical user (native/file realm) | Dedicated application identity attached to roles | When a stable organization-managed principal with roles is needed |
| Built-in Elasticsearch service account | Dedicated identity for specific Elastic Stack components | When a supported Elastic component requires that service account |
| Service account token | Credential used to authenticate a built-in service account | When integrating the corresponding component that supports service tokens |
| API key | Credential that can carry scoped role descriptors | Usually suitable for applications or integrations calling Elasticsearch |

Do not call every technical user a built-in service account. Elasticsearch provides built-in service accounts for specific Elastic Stack services; these are predefined principals, not a mechanism for arbitrarily creating a new service account for every business microservice.

### 1.3. When to use an API key?

An API key is suitable when you need a dedicated credential per workload with a clearly scoped permission boundary. You can create a key with:

- A name identifying the workload and environment.
- An expiration period.
- Role descriptors allowing only the required operations.
- Metadata to store operational details such as owner or reference ticket.

An API key cannot automatically exceed the permissions of its creator. The effective privileges of a key are bounded by the intersection of the creator principal's permissions and the declared role descriptors. Therefore, creating a key from an administrative account and assigning broad role descriptors is still risky; use a controlled provisioning process with appropriately scoped key-creation permissions.

### 1.4. When to use a built-in service account?

Built-in service accounts are reserved for specific Elastic Stack components, such as certain Kibana or Fleet components. If a component's deployment documentation requires a service token, use the exact supported namespace/service identity.

Do not use a Kibana or Fleet Server service account token to authenticate an unrelated Spring business application. That couples two different lifecycles and permission boundaries while complicating revocation and auditing.

### 1.5. When to use a dedicated technical user?

A dedicated technical user can be suitable when an organization wants centralized role management and a single long-lived principal per workload. Such a user should:

- Have a name clearly identifying the application and environment.
- Not have interactive login privileges if unnecessary.
- Only be assigned roles dedicated to that workload.
- Not be shared with human operators or other applications.
- Have its password/credential stored in a secret manager with a rotation procedure.

If the application needs credentials that can be issued and revoked independently without changing a user password, API keys are usually more convenient.

## 2. Role-Based Access Control Model

### 2.1. Authentication and authorization are two separate steps

- **Authentication** determines who the caller is: which user, service account, or API key.
- **Authorization** determines what the caller is allowed to do on which cluster, index, data stream, or resource.

A request can authenticate successfully and still be rejected for lacking privileges. Conversely, granting broad roles will not help if the credential is wrong or has been revoked.

| Status | Common Meaning | What to Check |
|---|---|---|
| `401 Unauthorized` | Credential could not be authenticated | Header, secret, expired/revoked key, TLS, and endpoint |
| `403 Forbidden` | Authenticated, but lacks privileges or blocked by policy | Role, index pattern, cluster privilege, DLS/FLS |
| `404 Not Found` | Resource or index does not exist, depending on API | Index/alias/data stream and visibility privileges |
| `429 Too Many Requests` | Overload or request throttling | Not a permission error; check backoff/concurrency |

### 2.2. Roles consist of cluster privileges and index privileges

An Elasticsearch role can define permissions at multiple scopes:

- `cluster`: cluster-level operations, such as certain administrative or monitoring tasks.
- `indices`: operations on designated indices/data streams.
- `applications`: privileges for specific integrated applications, if used.
- `run_as`: privileges to impersonate other users in supported use cases.

Applications querying and writing documents usually only need index privileges. Do not grant cluster privileges if the service does not actually invoke cluster APIs.

### 2.3. Choosing index privileges by operation

Common index privileges include:

| Privilege | General Meaning | Use Case |
|---|---|---|
| `read` | Read/search data | Search APIs, reporting |
| `view_index_metadata` | View required index metadata | Clients needing to read metadata/mappings or certain checks |
| `create_doc` | Only create new documents under supported semantics | Event writers that do not need to overwrite existing documents |
| `create` | Create document/index operations under this privilege | Workloads needing create semantics |
| `index` | Write/index documents | Indexers writing or replacing documents |
| `write` | Broader write group covering common write operations | Services needing to index/update/delete documents |
| `delete` | Delete documents | Grant only when business logic truly requires it |
| `delete_index` | Delete indices | Usually reserved for provisioning/admin jobs |
| `manage` | Manage indices and various index admin operations | Do not grant to ordinary runtime services |

Exact privilege names and scopes can change across Elasticsearch versions. Check the Security privileges reference for your cluster version before deploying.

Do not grant `all` or `manage` just to make a 403 error go away. Identify which API was denied and add the narrowest privilege that satisfies the use case.

### 2.4. Example of functional separation

Suppose there are three workloads:

| Workload | Read products | Write products | Delete index | Manage security |
|---|---:|---:|---:|---:|
| `catalog-api` | Yes | No | No | No |
| `catalog-indexer` | No or read-only for reconciliation | Yes | No | No |
| `index-provisioner` | As needed | As needed | Yes during deployment | Only if dedicated to security tasks |

Separating provisioning from runtime prevents an API service from deleting an index or altering mappings just because it needs to write documents.

### 2.5. Do not grant overly broad index name patterns

If an application only uses `products-prod`, do not grant privileges on a cluster-wide wildcard. If multiple indices per tenant or version are needed, choose a specific pattern like `products-v3-*` and verify the pattern does not accidentally match unrelated indices.

Account for aliases and data streams. Check the actual target resources the application calls, including backing indices if applicable, to ensure the role covers the intended scope.

### 2.6. Metadata privileges are not administrative privileges

Some clients or operations need to read index metadata. If you encounter a 403 when a client checks metadata, identify the exact endpoint called before granting permissions. `view_index_metadata` is typically much narrower than `manage`.

Do not grant `manage` simply because an application needs to read mappings or check index existence.

## 3. Designing Least Privilege

### 3.1. Start from the actual API list

Before creating a role, list the operations the service calls:

| Function | API or Operation | Privileges to Consider |
|---|---|---|
| Find documents | Search/get | `read` |
| Read mappings | Get mapping | `view_index_metadata` |
| Create new documents | Create | `create_doc` or `create` |
| Index/replace documents | Index | `index` or `write` |
| Partial updates | Update | `write` |
| Delete documents | Delete | `delete` or `write` |
| Create indices | Create index | Appropriate index management privilege, separated from runtime if possible |
| Create API keys/users/roles | Security API | Dedicated security privileges, never granted to data applications |

This table is a starting point. Exact privileges depend on the specific API, version, and how the Spring Data/Elasticsearch client executes requests.

### 3.2. Use a dedicated role per workload

Avoid bundling every permission into a single `application-role` and assigning it to all services.

You can create purpose-built roles:

- `catalog_reader`: read catalog only.
- `catalog_writer`: write catalog only.
- `catalog_reindexer`: read source and write target index during reindexing.
- `catalog_provisioner`: create indices/templates or required configuration.

Narrow roles let reviewers see immediately what a service is allowed to do.

### 3.3. Separate administrative privileges from runtime privileges

A deployment workflow can use two principals:

1. A provisioning principal creates indices, mappings, templates, and policies.
2. A runtime principal only reads/writes documents according to the application's contract.

Runtime services should not need `manage`, `manage_security`, `all`, or `superuser`. If the application auto-creates indices at startup, consider moving that step to a migration/deployment job.

### 3.4. An API key cannot escalate its creator's privileges

An API key's role descriptors limit the key's permissions. Effective privileges cannot exceed what the creating principal can grant. This is an important safeguard.

However, if a key is created by an overly broad principal and the role descriptor is not properly constrained, the key can receive broad privileges. Always inspect both the role descriptor and the creating identity.

### 3.5. Document-level and field-level security

If multiple tenants share an index, you may need to restrict which documents each principal can read or which fields a principal can view.

Elasticsearch supports document-level security (DLS) and field-level security (FLS) in corresponding configurations and licenses. Confirm feature availability on your cluster's version and license.

DLS/FLS do not replace application-level authorization. Do not pass an arbitrary client-supplied tenant ID into roles or queries without verifying a trusted source. For workloads with separate indices per tenant, index-level privileges can be simpler and easier to audit.

## 4. Creating Read-Only and Write-Only Roles

### 4.1. Read-only role

Example role that only reads `products-prod-*` indices:

~~~http
PUT /_security/role/products_reader
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-prod-*"],
      "privileges": ["read"]
    }
  ]
}
~~~

This role cannot write documents, delete documents, or manage indices. If the client genuinely needs to read index metadata, evaluate adding `view_index_metadata` after confirming the rejected API.

### 4.2. Document write-only role

Example indexer allowed to write to `products-prod-*`:

~~~http
PUT /_security/role/products_writer
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-prod-*"],
      "privileges": ["index"]
    }
  ]
}
~~~

The `index` privilege fits workloads that index documents under the granted semantics. If the service uses update or delete APIs, grant the corresponding privilege—usually `write` or a version-appropriate combination of privileges.

### 4.3. Read and write role

If a service truly needs both read and write:

~~~http
PUT /_security/role/products_reader_writer
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-prod-*"],
      "privileges": [
        "read",
        "write",
        "view_index_metadata"
      ]
    }
  ]
}
~~~

This is an illustrative example. Do not add `view_index_metadata` out of habit if the client does not need it. Do not add `delete` or `manage` unless required by the use case.

### 4.4. Runtime roles should not create indices

If indices are pre-created by a deployment pipeline, the runtime writer only needs document write privileges. Allowing automatic index creation can lead to:

- Indices created with incorrect default mappings.
- Wrong shard/replica settings.
- Missing lifecycle policies or templates.
- Junk indices caused by typos in index names.
- Runtime services able to alter data structures unexpectedly.

Use a migration/provisioning job to manage schemas and keep runtime privileges narrow.

## 5. Creating Scoped API Keys

### 5.1. API for key creation

An API key can be created via the Security API:

~~~http
POST /_security/api_key
Content-Type: application/json

{
  "name": "catalog-indexer-prod",
  "expiration": "30d",
  "role_descriptors": {
    "catalog_writer": {
      "cluster": [],
      "indices": [
        {
          "names": ["products-prod-*"],
          "privileges": ["index"]
        }
      ]
    }
  },
  "metadata": {
    "application": "catalog-indexer",
    "environment": "production",
    "owner": "search-platform"
  }
}
~~~

The key name should reflect the workload and environment. Expiration prevents credentials from living forever. Role descriptors restrict permissions to the necessary indices.

The creating principal must have appropriate privileges to create API keys. Depending on your governance model, creating keys on behalf of other users may require broader API key management permissions. Do not grant this privilege to a runtime application just so it can mint credentials for itself.

### 5.2. Key creation response

The response may contain fields such as:

~~~json
{
  "id": "api-key-id",
  "name": "catalog-indexer-prod",
  "api_key": "secret-value",
  "encoded": "base64-encoded-id-and-secret",
  "expiration": 1790000000000
}
~~~

This is illustrative data, not a real credential.

- `id` is the key identifier used for management or revocation.
- `api_key` is the key secret.
- `encoded` is the Base64-encoded value formatted for the `Authorization` header.
- `expiration` is the expiration timestamp if the key has an expiration.

Store the `encoded` value or the ID/secret pair according to what your client expects. Do not Base64-encode `encoded` again when using Elasticsearch's standard `Authorization` format.

The secret is usually returned only at creation time. Store it immediately in a secret manager; if lost, create a new key and revoke the old one per procedure.

### 5.3. Authorization header

The API key is sent in the header:

~~~http
Authorization: ApiKey <encoded>
~~~

The `encoded` value is the `encoded` field from the key creation response. Base64 is only encoding, not encryption. Anyone who obtains this value can use the credential within the key's permission scope.

Only transmit credentials over HTTPS with verified certificates. Do not pass API keys in URL query parameters or write them to logs.

### 5.4. API keys inherit the creator principal's limits

A key's role descriptor is not a way to escalate privileges. Effective privileges are bounded by both the creating principal's privileges and the key's role descriptor.

If no role descriptor is specified, the key may inherit the creator's privileges depending on Elasticsearch API key semantics. Always define explicit role descriptors and use a provisioning principal with just-enough permissions.

Do not use the `elastic` or `superuser` account to create application keys if a narrower provisioning principal can be used.

### 5.5. Creating a read-only key

Example key for a reporting worker:

~~~http
POST /_security/api_key
Content-Type: application/json

{
  "name": "reporting-reader-prod",
  "expiration": "30d",
  "role_descriptors": {
    "reporting_reader": {
      "cluster": [],
      "indices": [
        {
          "names": ["products-prod-*", "orders-prod-*"],
          "privileges": ["read"]
        }
      ]
    }
  }
}
~~~

This key cannot index, update, or delete. If the reporting worker needs metadata or aggregations on indices, verify that the `read` privilege covers the APIs invoked in your cluster version.

### 5.6. API keys are not shared secrets

Create separate keys per:

- Application.
- Environment (`development`, `staging`, `production`).
- Workload or function if privileges differ.
- Tenant or integration when isolation is required.

Do not use a single key across all microservices. If one service is compromised, separate keys allow revoking just that credential without disrupting the remaining services.

## 6. Built-In Service Accounts and Service Tokens

### 6.1. Service accounts are identities for specific components

Elasticsearch provides built-in service accounts for Elastic Stack components. They are managed under predefined namespaces and service names.

A service token is the credential used by the corresponding component to authenticate. A token is not a generic password for all applications and should not replace an API key for an arbitrary microservice.

### 6.2. Creating a service token

For supported service accounts, tokens can be created via the Security API or version-appropriate admin tools:

~~~http
POST /_security/service/<namespace>/<service>/credential/token/<token_name>
~~~

The `namespace` and `service` path segments must match a valid built-in service account. Do not invent a `my-app` namespace expecting Elasticsearch to create a custom service account.

The response returns the token secret. Store it in a secret manager and configure the exact component that needs it.

### 6.3. Revoking a service token

When a token is no longer needed, revoke it via the corresponding service-account token API:

~~~http
DELETE /_security/service/<namespace>/<service>/credential/token/<token_name>
~~~

Confirm the API and token management match your cluster version. Revoking a token causes the component using it to lose authentication; deploy a replacement token first if the workload must run continuously.

### 6.4. Choosing a service token or API key?

| Need | Choice |
|---|---|
| Elastic Stack component requiring a built-in service identity | Service account token |
| Business microservice needing scoped index privileges | API key |
| Organization preferring centrally managed roles via dedicated technical user | Dedicated technical user |
| Deployment job needing to create indices/templates | Separate provisioning principal |
| Human operators needing interactive access | Individual user via SSO/appropriate realm |

Use the credential matching the principal type. Do not reuse another component's token simply to reduce configuration work.

## 7. Configuring Spring Data Elasticsearch with an API Key

### 7.1. Never hardcode secrets in source

Do not write API keys directly into:

- Java source files.
- Committed `application.yml`.
- Docker images.
- Public Helm values.
- Logs or exception messages.
- Widely shared sample files.

Applications should receive credentials via a secret manager, environment injection, or the deployment platform's secret management mechanism.

### 7.2. ClientConfiguration example

Spring Data Elasticsearch lets you configure HTTP headers when building the client. Conceptual example:

~~~java
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.http.HttpHeaders;

ClientConfiguration clientConfiguration =
    ClientConfiguration.builder()
        .connectedTo("elasticsearch.internal:9200")
        .usingSsl()
        .withHeaders(() -> {
            HttpHeaders headers = new HttpHeaders();
            headers.add(
                HttpHeaders.AUTHORIZATION,
                "ApiKey " + apiKeyEncoded
            );
            return headers;
        })
        .build();
~~~

`apiKeyEncoded` is read from a secret manager or secure runtime configuration. Method names, SSL configuration, and client factories depend on the Spring Data Elasticsearch version; check the API of the release train you are using.

If using custom certificates, configure trust for the appropriate CA or certificate chain. Do not disable hostname verification or certificate validation just to make the connection work.

### 7.3. Use TLS

An API key is a bearer credential: anyone holding the secret can use it. Always transmit it over HTTPS/TLS across the network.

In production environments:

- Verify the server certificate.
- Trust the internal CA if the cluster uses a private PKI.
- Avoid trust-all configurations.
- Restrict the network path to Elasticsearch.
- Do not send credentials through untrusted proxies.
- Do not record the `Authorization` header in HTTP wire logs.

### 7.4. Integrating with Spring Boot

Property names and how the Elasticsearch client is auto-configured change across Spring Boot/Spring Data Elasticsearch versions. Do not assume every release supports a single standard API key property.

If configuring the client via a custom bean, make sure that bean is actually used by Spring Data templates/repositories. Avoid creating one client with an API key attached while repositories end up using another auto-configured client.

### 7.5. Configuring via a secret manager

A runtime configuration can accept the URL and secret through a configuration object:

~~~java
@ConfigurationProperties(prefix = "app.elasticsearch")
public record ElasticsearchCredentials(
    String url,
    String apiKey
) {
}
~~~

The client configuration bean can receive this object via constructor or method injection:

~~~java
@Configuration
public class ElasticsearchClientConfiguration {

    @Bean
    ClientConfiguration clientConfiguration(
            ElasticsearchCredentials credentials) {

        return ClientConfiguration.builder()
            .connectedTo(credentials.url())
            .usingSsl()
            .withHeaders(() -> {
                HttpHeaders headers = new HttpHeaders();
                headers.add(
                    HttpHeaders.AUTHORIZATION,
                    "ApiKey " + credentials.apiKey()
                );
                return headers;
            })
            .build();
    }
}
~~~

This is a structural example. For production, secrets should be injected from a secret manager or the platform's workload identity integration. Do not put real secret values into committed `application.yml`.

If the key changes at runtime, determine whether the client reads headers dynamically or captures the value at initialization. Many client setups snapshot credential values when the bean is constructed; when rotating, you may need to refresh/recreate the client or perform a controlled rollout restart.

### 7.6. Configuring Basic authentication for technical users

If using a dedicated user/password instead of an API key, configure authentication via the supported client mechanism:

~~~java
ClientConfiguration clientConfiguration =
    ClientConfiguration.builder()
        .connectedTo("elasticsearch.internal:9200")
        .usingSsl()
        .withBasicAuth(username, password)
        .build();
~~~

Use a dedicated user with narrow roles. Do not use default admin accounts for applications. Passwords must also be managed as secrets with expiry/rotation and never logged.

## 8. Managing Secrets Safely

### 8.1. A secret manager is the primary store

Store API keys or service tokens in an appropriate secret management system, such as a vault or cloud/container secret store.

Applications should only receive secrets at runtime. Read permissions on secrets must also be scoped by workload identity.

Do not store secrets in Git, tickets, chat, documentation guides, or broadly shared configuration variables.

### 8.2. Do not confuse Base64 with encryption

`encoded` for an API key is Base64 encoding of the credential string. Anyone holding that string can use the key. Do not treat Base64 as a security layer and do not log that value thinking it "hides" the secret.

### 8.3. Avoid logging the Authorization header

HTTP client debug logging can record request headers. Configure redaction for `Authorization` and secret-related headers.

Check across all channels:

- Application logs.
- HTTP wire logs.
- Reverse proxy/access logs.
- APM/tracing attributes.
- Error reports.
- Crash dumps and diagnostic bundles.

Do not put raw API keys into trace baggage or metric labels.

### 8.4. Separate secrets by environment

Do not use production keys in development or CI. Every environment should have its own keys, roles, and index patterns.

For example:

- `catalog-indexer-dev` only writes `products-dev-*`.
- `catalog-indexer-staging` only writes `products-staging-*`.
- `catalog-indexer-prod` only writes `products-prod-*`.

This reduces the risk of a test job accidentally writing to production.

### 8.5. Restrict secret read permissions

Only the workload identity of the application needing the key should be allowed to read the secret. Developers do not need permission to view production keys just because they can deploy code.

Secret read permissions and Elasticsearch call permissions are two independent layers of control. If a build pipeline is compromised, it should not automatically have access to production credentials.

## 9. Rotating and Revoking Credentials

### 9.1. API keys are normally replaced with a new key

An API key secret is not updated in place like a typical password. The rotation workflow is usually:

1. Create a new API key with the same or narrower privileges.
2. Store the new secret in the secret manager.
3. Deploy/reload the workload to use the new key.
4. Verify requests succeed with the expected identity.
5. Revoke the old key.
6. Monitor authentication errors after revocation.

Do not revoke the old key before the workload has switched to the new key if you need to avoid downtime.

### 9.2. Controlled rotation overlap

There can be a short overlap period where both old and new keys exist simultaneously. The overlap window should be bounded, have an owner, and have an end time.

Do not leave old keys active indefinitely "just in case". Once rollout success is confirmed, revoke the old key.

### 9.3. Revoking an API key

An API key can be invalidated by ID via the Security API:

~~~http
DELETE /_security/api_key
Content-Type: application/json

{
  "ids": ["api-key-id"]
}
~~~

Key management APIs may also support filtering by other attributes depending on version. In automated workflows, prefer storing the key ID alongside metadata for accurate revocation.

Revoking a key causes every client using that key to lose access. Identify the owner and workload before revoking.

### 9.4. When a key is suspected of compromise

If a credential is exposed:

- Revoke the suspected key per incident procedure.
- Create a new key with least privilege.
- Update the secret and roll out the workload.
- Inspect audit/security logs if available.
- Review anomalous requests and the scope of accessible data.
- Remove the secret from the exposed location and remediate Git history/logs per organizational policy.
- Re-evaluate roles and key expiration periods.

Simply deleting a secret from the current file does not invalidate an exposed credential. Revocation in Elasticsearch is what blocks further use.

### 9.5. Expiration and rotation schedules

Set expiration durations aligned with your automated rotation capability. A key that expires before a replacement is deployed will disconnect the application.

An automated rotation workflow should:

- Create a new key before the current one expires.
- Validate the new key.
- Update the secret.
- Roll out instances.
- Confirm all instances have switched over.
- Revoke the old key.
- Alert if rotation has not completed before the deadline.

Do not set an expiration shorter than the deploy/rotation cycle the system can reliably guarantee.

## 10. Verifying Effective Privileges

### 10.1. Confirm the authenticated identity

You can use the authenticate endpoint to check a credential:

~~~http
GET /_security/_authenticate
Authorization: ApiKey <encoded>
~~~

The response indicates the principal and authentication details according to the credential type. Do not write responses containing sensitive metadata into public logs.

### 10.2. Check specific privileges

Elasticsearch provides an API to inspect the current user's privileges. You can use it to verify that a principal has the desired cluster/index privileges according to your cluster version's schema.

Conceptual example:

~~~http
POST /_security/user/_has_privileges
Authorization: ApiKey <encoded>
Content-Type: application/json

{
  "cluster": [],
  "index": [
    {
      "names": ["products-prod-*"],
      "privileges": ["read", "index"]
    }
  ]
}
~~~

The result indicates whether the requested privileges are effective. Use the exact endpoint and payload of the running Elasticsearch version.

### 10.3. Verify with actual operations

Privilege checks do not replace integration tests. Test:

- Searching documents in allowed indices.
- Indexing documents if the service needs write access.
- Updating/deleting only when granted and required.
- Searching or writing to out-of-scope indices to verify denial.
- Calling cluster/security APIs that runtime does not need to verify they are denied.

Negative tests are crucial. A role that works for the intended use case may still be broader than necessary.

### 10.4. Verify through the Spring Data client itself

Use the exact beans/client and credentials that the production application will use. A `curl` call succeeding with an admin credential does not prove the application's client has the right permissions.

Integration tests should run with an API key or technical user having production-equivalent roles. Do not bring production secrets into test environments.

## 11. Security for Indices, Aliases, and Data Streams

### 11.1. Grant privileges on the resource names the application actually uses

Applications may operate through aliases instead of concrete indices. Data streams have backing indices. Check how security privileges apply to the resource names used in API requests and how Elasticsearch handles aliases/data streams in your cluster version.

Do not guess privilege scope solely from an alias name in an entity annotation.

### 11.2. Avoid cluster-wide wildcards

Roles with cluster-wide wildcard `names` are usually too broad for runtime services. Use specific prefixes/patterns and test against similarly named indices.

If multiple environments share a cluster, patterns must cleanly distinguish `dev`, `staging`, and `production`.

### 11.3. Privileges for rollover and index lifecycle

Services writing to a data stream may need privileges matching create/index operations and the configured lifecycle. Rollover, template, ILM, and data stream management operations usually belong to a provisioning/operations principal.

Do not grant lifecycle management privileges to an application just because it sends bulk documents to a data stream.

### 11.4. Write index aliases

If an alias has a write index, the application can write through the alias without knowing the backing index. Ensure the role is granted on the appropriate pattern and the alias does not point to indices outside the service's scope.

Changing aliases or triggering rollovers should be performed by a separate administrative principal.

## 12. Multi-Tenancy and Workload Separation

### 12.1. Separate indices per tenant when strong isolation is needed

If each tenant has its own index, a tenant-specific key can be scoped only to that tenant's index pattern. This establishes a clear authorization boundary in Elasticsearch.

However, the number of roles/keys can grow large. Evaluate operability, naming conventions, and revocation procedures.

### 12.2. Using DLS when sharing an index

If multiple tenants share an index, document-level security can restrict documents via a role query filter if supported by the cluster/license.

Verify carefully that the DLS filter cannot be bypassed through another access path. Do not rely on client-supplied query filters as the sole security mechanism.

### 12.3. Field-level security

FLS can restrict which fields a principal can read. For example, a reporting service only needs name and price, not email or personal data.

Check compatibility with aggregations, sorting, highlighting, and application mappings. Hidden fields can cause certain queries or response mappings to behave unexpectedly.

### 12.4. Do not share API keys across tenants

If a key can read every tenant, adding a tenant filter in Java does not create isolation at the Elasticsearch layer. A query bug or application vulnerability can expose data.

For strict isolation requirements, use separate principals/keys, separate indices, or tested DLS.

## 13. Operating Credentials in Deployment Environments

### 13.1. Kubernetes and containers

In Kubernetes, secrets can be injected via Secret volumes or environment variables per platform policy. Restrict Secret read access by namespace/service account and do not commit plaintext secret manifests.

If secrets are mounted as files, the application needs an appropriate read/refresh mechanism. If the client only loads credentials at bean initialization, instances must restart or recreate the client after rotation.

### 13.2. CI/CD

Deployment pipelines should only have permission to fetch secrets needed for the environment they deploy to. Do not print secret values in job logs.

Separate permissions:

- Build pipeline: builds artifacts, needs no production API key.
- Deploy pipeline: fetches secrets or triggers platform injection.
- Runtime workload: reads credentials while running.
- Provisioning pipeline: creates indices/roles/keys within approved scope.

### 13.3. Local development

Developers should use dedicated cluster/dev keys with restricted privileges. If a shared development environment is used, issue revocable credentials with no production access.

Do not copy production keys to a laptop for debugging. Production data and production secrets must be protected according to organizational policy.

### 13.4. Disaster recovery

Store credential metadata (owner, key ID, role, expiry, environment) in a management system, without storing the secret itself in an insecure location.

Runbooks should document how to create replacement credentials, update workloads, verify, and revoke old credentials. This allows restoring services without falling back to a superuser.

## 14. Common Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `401` after deployment | Wrong API key, missing header, expired/revoked key | Check secret, `Authorization` header, and key status |
| `403` on search | Missing `read` or pattern mismatch | Check role and actual index name |
| `403` when reading mapping | Missing required metadata privilege | Identify denied API, then evaluate `view_index_metadata` |
| `403` on update | Read-only or insufficient write privilege | Choose `write`/privilege matching the operation |
| API key has unexpectedly broad privileges | Over-privileged creator or unconstrained role descriptor | Use a narrow provisioning principal and explicit role descriptor |
| Service account token does not work | Wrong built-in service identity selected | Use the service account built for that specific component |
| Credential works in dev but fails in prod | Role, index pattern, TLS, or secret differs | Compare config/privileges per environment |
| New key created but app still uses old key | Client captured header at initialization | Refresh/recreate client or roll out instances |
| Revoking key disrupts service | Revoked before new key rolled out | Use rotation overlap and confirm cutover |
| Secret appears in logs | HTTP wire logging or exception printing headers | Redact `Authorization` and rotate the exposed key |
| `403` with alias/data stream | Pattern or privilege mismatches resource/backing index | Check resource names and version security semantics |
| Runtime cannot create index | Runtime role lacks index management privileges | Pre-create indices via a separate provisioning job |
| Revoking one service breaks another | Multiple services share the same key | Separate credentials per workload |
| Privilege test only passes with admin | Test does not use a production-like principal | Run integration tests with restricted keys/roles |

## 15. Design and Implementation Workflow

When granting permissions to a Spring Data Elasticsearch application:

1. List the Elasticsearch operations the application actually invokes.
2. Choose the identity: API key, dedicated technical user, or built-in service token matching the use case.
3. Separate provisioning/admin from runtime workloads.
4. Identify exact indices, aliases, and data streams.
5. Create roles with minimal cluster privileges and only required index privileges.
6. Create API keys with clear names, expirations, and constrained role descriptors.
7. Store secrets in a secret manager.
8. Configure the Spring Data client with HTTPS and the `Authorization` header.
9. Verify the client/template/repository actually uses that credential.
10. Confirm identity via the authenticate API.
11. Check privileges and run positive/negative integration tests.
12. Set up rotation, expiry alerts, and revocation procedures.
13. Monitor 401/403 responses, credential usage, and security events.
14. Periodically review roles to prune unused privileges.

## 16. Key Takeaways

- Authentication identifies the caller; authorization determines what the caller can do.
- Elasticsearch built-in service accounts are for specific Elastic Stack components, not arbitrary custom accounts for every microservice.
- API keys are usually well suited for application workloads needing dedicated credentials and scoped role descriptors.
- Dedicated technical users are another option when centrally managed user roles are preferred.
- An API key's effective privileges are bounded by both the creating principal's privileges and its role descriptors.
- Runtime services should only have required index privileges; avoid `all`, `manage`, `manage_security`, and `superuser`.
- Separate read, write, document delete, index management, and security management by function.
- Use specific index patterns; account for aliases and data streams.
- API keys use the `Authorization: ApiKey <encoded>` header over HTTPS.
- Base64 is not encryption; never log or commit credentials.
- Store secrets in a secret manager and separate keys by application and environment.
- Rotation should create a new key, roll out, verify, and only then revoke the old key.
- Test both allowed operations and operations that must be denied.
- The Spring Data client does not make credentials secure on its own; privileges and secret lifecycles must be managed at deployment time.
- Low-level clients and Spring Data operations may have separate configuration paths; verify which client repositories actually use.

Service accounts, API keys, and least privilege form an essential security boundary between the application and Elasticsearch. When each workload has its own credential, can access only its exact resources, and follows clear rotation and revocation procedures, the system becomes easier to operate and the blast radius of any exposed secret is significantly reduced.
