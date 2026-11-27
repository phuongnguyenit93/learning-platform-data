# Separating Search Read, Document Write, and Index Administration Privileges

In a Spring Data Elasticsearch application, not every component needs full permissions on Elasticsearch. The search API only needs to read documents; an ingestion service needs to write documents; a deployment process may need to create indices, update mappings, and switch aliases. If all of them share a single account with administrative rights, a bug in an endpoint or an exposed credential can affect all data.

The secure design is **separation of duties and least privilege**:

- **Search/read**: search and read documents in permitted indices.
- **Document write**: create or update documents according to business logic.
- **Index administration**: create/delete indices, modify mappings/settings, and manage aliases during deployment.

You should distinguish permissions across two layers. Spring Security decides which application users can call which endpoints; Elasticsearch Security decides what actions the application's credential is allowed to perform on the cluster and indices. Both layers complement each other; neither replaces the other.

## 1. Why Separate Privileges?

Suppose a catalog system has:

- A Search API serving the website and mobile app.
- A Product service updating documents when products change.
- An Import worker receiving data from external sources.
- A Deployment job creating new index versions and switching aliases.
- An operations team inspecting the cluster and mappings.

If all of them share a single Elasticsearch account with `all` privileges, every component could delete indices or alter mappings even when it does not need that capability.

A role-separated design:

~~~mermaid
flowchart TD
    A["Website / Mobile"] --> B["Spring Search API"]
    B -->|read-only credential| C["Elasticsearch: products-*"]
    D["Product Service"] -->|document-write credential| C
    E["Import Worker"] -->|create/write credential| C
    F["Deployment Pipeline"] -->|index-admin credential| G["Create index / mapping / alias"]
    G --> C
~~~

| Component | Need | Recommended Privileges |
|---|---|---|
| Search API | Search, get documents | `read` |
| Product service | Index/update documents | `write` on required indices |
| Event consumer only creating event documents | Create documents, no modify/delete | `create_doc` if suitable |
| Import worker | Bulk create/index | Write privileges matching operations |
| Migration job | Create indices, mappings, aliases | Bounded index administration |
| Monitoring agent | Read health/metrics | Appropriate `monitor` privileges |
| Operators | Cluster administration | Separate, controlled admin privileges |

A credential should hold only the privileges needed for its own job. The Search API does not need write access; a document-writing service does not need index deletion rights; ordinary runtime applications do not need cluster administration privileges.

## 2. Distinguishing Spring Security and Elasticsearch Security

The two security systems serve different purposes:

| Layer | Controls What? | Example |
|---|---|---|
| Spring Security | Who can call the application's APIs | User with authority `products.read` can call `GET` |
| Elasticsearch Security | Which credential can call which Elasticsearch APIs | API key with only `read` on `products-*` |
| Business authorization | Which scope of data a user can view/edit | User only views products belonging to their tenant |

A search request can pass through multiple checks:

1. Spring Security authenticates the user and allows calling the Search API.
2. The search service uses its dedicated credential to call Elasticsearch.
3. Elasticsearch verifies whether that credential's role/API key has permission to read the target index.
4. The application applies additional filters by tenant, ownership, or data scope.

Elasticsearch usually sees the application's service account or API key, not the end user logged into the website. Therefore, if the application shares one API key across many users, you cannot rely on that Elasticsearch role to replace per-user permission checks.

## 3. Elasticsearch Privilege Groups to Know

Elasticsearch Security has cluster-level and index-level privileges. Choose the right scope when defining roles.

### Index-level privileges

Common index privileges:

| Privilege | Purpose |
|---|---|
| `read` | Search and read documents |
| `view_index_metadata` | Read metadata such as mappings/settings/aliases in supported APIs |
| `create_doc` | Create documents with create semantics, disallowing update/delete |
| `write` | Write documents, covering index/update/delete operations permitted by this privilege |
| `create_index` | Create indices |
| `delete_index` | Delete indices |
| `manage` | Broad index management: mappings, settings, and index admin operations |
| `manage_aliases` | Manage aliases |

Privilege names are Elasticsearch's authorization contract. An API may require multiple privileges depending on the action and version. Check the privilege requirements of specific APIs when narrowing roles.

### Cluster-level privileges

Cluster privileges apply to cluster-wide management or observation APIs, for example:

- `monitor`: read cluster monitoring information.
- `manage_index_templates`: manage index templates.
- `manage_ilm`: manage Index Lifecycle Management policies.
- `manage`: broad cluster administration.
- `manage_security`: manage users, roles, API keys, and security configuration.

Do not confuse the index privilege `manage` with the cluster privilege `manage`. Same name, different scope. A service needing to manage mappings for a group of indices does not thereby need permission to manage users or the entire cluster.

## 4. Creating a Read-Only Role for Search

The Search API usually needs permission to read documents on product indices. Example role creation:

~~~http
POST /_security/role/products_search
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-*"],
      "privileges": [
        "read",
        "view_index_metadata"
      ],
      "allow_restricted_indices": false
    }
  ],
  "applications": [],
  "run_as": [],
  "metadata": {
    "description": "Read-only access for product search API"
  }
}
~~~

Explanation:

- `cluster` is empty because the search service needs no cluster administration.
- `names` restricts the role to indices matching `products-*`.
- `read` allows read/search operations.
- `view_index_metadata` is added only when the client or endpoint needs index metadata.
- `allow_restricted_indices` is set to `false` to avoid accidentally granting access to restricted indices.

If the application only executes search/get and never reads mappings, check whether `view_index_metadata` can be omitted. Granting extra privileges "just in case" makes roles broader than needed.

### Attaching roles to a user or API key

A role does not authenticate requests on its own. Attach the role to a user or create an API key with the corresponding role descriptor.

Example creating a dedicated user for the Search API:

~~~http
POST /_security/user/products-search-service
Content-Type: application/json

{
  "password": "<secret-from-secure-provisioning>",
  "roles": ["products_search"],
  "full_name": "Product search service"
}
~~~

The password in the example is a placeholder. Never commit real passwords to source control, public configuration files, or logs. In production, use a secret manager or your platform's secure provisioning mechanism.

An API key can also be created with a scoped role descriptor:

~~~http
POST /_security/api_key
Content-Type: application/json

{
  "name": "products-search-api",
  "role_descriptors": {
    "products_search": {
      "cluster": [],
      "indices": [
        {
          "names": ["products-*"],
          "privileges": ["read", "view_index_metadata"]
        }
      ]
    }
  }
}
~~~

When using API keys, manage their lifecycle, expiration, revocation, and rotation. Do not send backend API keys to browser/mobile clients.

## 5. Document Write-Only Roles

A service updating documents does not need permission to search the entire index if its logic does not require it. Still, choose privileges matching the operation type.

### Create-only documents

If a worker only uses create operations and never updates or deletes existing documents, consider `create_doc`:

~~~http
POST /_security/role/products_ingest_create
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-*"],
      "privileges": ["create_doc"]
    }
  ],
  "metadata": {
    "description": "Create-only ingestion for product documents"
  }
}
~~~

This privilege fits append-only pipelines using stable IDs and create semantics. When an ID already exists, the create request conflicts; the credential cannot escalate to update or delete documents.

### Index/update/delete needed

The Product service may need to replace documents by ID, partially update sources, or delete documents. This requires a broader write privilege, typically `write`:

~~~http
POST /_security/role/products_document_writer
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-*"],
      "privileges": ["write"]
    }
  ],
  "metadata": {
    "description": "Write product documents without index administration"
  }
}
~~~

This role has no index administration privileges such as creating/deleting indices or changing mappings. If the code also performs search/get checks before updating, add appropriate read privileges rather than assuming `write` implies `read`.

### Do not grant write access to unrelated indices

A product service should not have `write` on `*` if it only needs `products-*`. Restrict both operation types and index names.

## 6. Distinguishing `create_doc`, `write`, and `read`

Avoid lumping every operation into one "application" role with read/write/manage.

| Need | Suggested Privilege | Notes |
|---|---|---|
| Search and get | `read` | Does not allow modifying documents |
| Read mapping metadata when needed | `view_index_metadata` | Add only if required by API/client |
| Create documents only | `create_doc` | Not suitable for update/delete |
| Index/update/delete documents | `write` | Not equivalent to index administration |
| Create index | `create_index` or appropriate management privilege | Applies to target index names |
| Delete index | `delete_index` or appropriate management privilege | Data-loss risk |
| Manage mappings/settings/aliases | `manage` or specialized privileges | Reserved for deployment/admin workflows |

Some APIs require extra metadata or cluster privileges. For example, a bulk request containing mixed action types requires the corresponding privileges for each item; a request-level check does not automatically authorize every sub-action.

## 7. Index Administration Roles

Index administration is more sensitive than document writing. A migration job may need to:

- Create a new index version.
- Set mappings and settings.
- Create or update aliases.
- Verify the index before switching aliases.
- Delete old indices according to retention policy.

Example role for product index administration:

~~~http
POST /_security/role/products_index_admin
Content-Type: application/json

{
  "cluster": [],
  "indices": [
    {
      "names": ["products-*"],
      "privileges": ["manage"],
      "allow_restricted_indices": false
    }
  ],
  "metadata": {
    "description": "Manage product index lifecycle and mappings"
  }
}
~~~

`manage` is a broad index management privilege. Grant it only to deployment/migration identities or operators with a genuine need. If a task only needs a single action, consider specialized privileges like `create_index`, `delete_index`, or `manage_aliases` instead of broad permissions.

If a migration job needs to read documents to verify data after reindexing, `read` can be added. Do not add read access if the job only manipulates mappings/settings and aliases.

### Index templates and ILM are cluster-level privileges

Managing index templates or ILM policies is different from modifying mappings on an existing index. These APIs typically require specialized cluster privileges, such as `manage_index_templates` or `manage_ilm`.

Do not grant these cluster privileges to the runtime Search API or Document Writer. Only deployment pipelines or corresponding administrative services need them.

## 8. Separating Runtime Accounts from Deployment Accounts

A secure deployment model typically uses distinct identities:

~~~text
Runtime application
  ├── search credential
  │     └── read products-*
  ├── document writer credential
  │     └── write products-*
  └── ingestion credential
        └── create_doc products-*

Deployment pipeline
  └── index admin credential
        ├── create index
        ├── update mapping/settings
        └── manage aliases
~~~

Deployment credentials should not reside inside runtime containers if the application does not need to manage indices. If a runtime service is compromised, the blast radius of a document-writer credential is far smaller than a credential with `manage` or cluster-wide `all`.

If a service genuinely needs both read and write, you can attach two roles to one service identity or use a composite role containing only `read` and `write` on the exact indices. Splitting separate credentials for read and write is helpful when you want per-flow isolation or workload-level auditing, though it increases the number of secrets to manage. Choose based on your actual trust boundaries.

## 9. Spring Security Protects Application Endpoints

Elasticsearch roles only govern the credentials calling the cluster. The Search API still needs Spring Security to govern end users.

Example with OAuth2 Resource Server and JWT scopes:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(
                                HttpMethod.GET,
                                "/api/products/**"
                        ).hasAuthority("SCOPE_products.read")
                        .requestMatchers(
                                HttpMethod.POST,
                                "/api/products/**"
                        ).hasAuthority("SCOPE_products.write")
                        .requestMatchers(
                                HttpMethod.PUT,
                                "/api/products/**"
                        ).hasAuthority("SCOPE_products.write")
                        .requestMatchers(
                                HttpMethod.DELETE,
                                "/api/products/**"
                        ).hasAuthority("SCOPE_products.delete")
                        .anyRequest().authenticated()
                )
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt()
                )
                .build();
    }
}
~~~

Scopes are application API permissions. They do not automatically become Elasticsearch privileges. A user with `SCOPE_products.read` is only allowed to call the `GET` endpoint; the backend still uses its separately configured search credential.

For sensitive service operations, method security can be used:

~~~java
@EnableMethodSecurity
@Configuration
class MethodSecurityConfiguration {
}
~~~

~~~java
@Service
public class ProductCommandService {

    @PreAuthorize("hasAuthority('SCOPE_products.write')")
    public void updateProduct(ProductCommand command) {
        // Validate command and update source data.
    }
}
~~~

Explicitly define authority mappings from JWTs or authentication providers. Do not trust arbitrary client-sent headers such as `X-Role: admin` unless a trusted gateway authenticates and overwrites them.

## 10. Per-Tenant and Per-Document Authorization

Elasticsearch roles usually grant permissions by index or index pattern. Many applications must also restrict users by tenant, organization, or owner.

For example, two tenants sharing the `products` index:

~~~json
{
  "productId": "P-1001",
  "tenantId": "tenant-42",
  "name": "Wireless Keyboard"
}
~~~

~~~json
{
  "productId": "P-1001",
  "tenantId": "tenant-77",
  "name": "Wireless Mouse"
}
~~~

A search credential with `read` on `products` can read both tenants. The application must add a tenant filter derived from authentication:

~~~java
Query tenantQuery = Query.of(q -> q
        .term(t -> t
                .field("tenantId")
                .value(authenticatedTenantId)
        )
);

NativeQuery searchQuery = NativeQuery.builder()
        .withQuery(tenantQuery)
        .withPageable(PageRequest.of(0, 25))
        .build();
~~~

`authenticatedTenantId` must come from verified principal/claims, never directly from a query parameter or body without authorization.

For updates/deletes, also verify that the document belongs to the tenant before executing. Do not let a client pass another tenant's ID and let a service credential with index-wide write access modify that document.

Index-per-tenant can be used in some systems, but requires managing index counts, lifecycles, and role patterns. Avoid creating tens of thousands of indices just to replace per-tenant authorization unless your data model requires it.

## 11. Bulk API Privileges

The Bulk API bundles multiple actions into one request. Each action has its own privilege requirement:

- `create` or `index`: requires corresponding create/write privileges.
- `update`: requires corresponding update/write privileges.
- `delete`: requires corresponding delete/write privileges.

An API key with only `create_doc` can work for create-only bulk ingestion. If a bulk request contains update or delete actions, those items will be rejected.

Example create-only bulk:

~~~http
POST /_bulk
Content-Type: application/x-ndjson

{"create":{"_index":"products-v2","_id":"P-1001"}}
{"productId":"P-1001","name":"Wireless Keyboard"}
{"create":{"_index":"products-v2","_id":"P-1002"}}
{"productId":"P-1002","name":"Wireless Mouse"}
~~~

If one item has a conflict or authorization error, other items can still succeed. Bulk is not a transaction. Consumers must inspect every item in the response and classify errors; do not assume all actions failed just because `errors: true` appears.

## 12. Privileges with Aliases and Versioned Indices

A common deployment pattern creates versioned indices and exposes aliases to applications:

~~~text
products-v1
products-v2
products (read/write alias)
~~~

The deployment pipeline needs alias management privileges to switch the alias from the old index to the new one. Runtime search and writers only need privileges on the alias or index pattern matching their actual operations.

Example alias switch:

~~~http
POST /_aliases
Content-Type: application/json

{
  "actions": [
    {
      "remove": {
        "index": "products-v1",
        "alias": "products"
      }
    },
    {
      "add": {
        "index": "products-v2",
        "alias": "products",
        "is_write_index": true
      }
    }
  ]
}
~~~

Alias operations require alias management privileges on the involved indices. Only the deployment identity should hold this privilege if runtime does not switch aliases itself.

Be careful with privileges on aliases vs. backing indices. Roles must match the actual index names checked by API authorization. Test through the alias in staging rather than testing only against a hardcoded index name.

## 13. Configuring Credentials in Spring Data Elasticsearch

Spring Data Elasticsearch uses the Elasticsearch client configured in the application context. Authentication is configured at the client/transport layer; Spring Data repositories and operations use that client when sending requests.

Endpoints and API keys can be supplied via environment variables or a secret manager:

~~~yaml
spring:
  elasticsearch:
    uris: $ELASTICSEARCH_URIS
    api-key: $ELASTICSEARCH_API_KEY
~~~

Property names may vary across Spring Boot/Spring Data Elasticsearch versions and client setup styles. If your application version does not support an `api-key` property directly, configure the Elasticsearch Java API Client/transport with the HTTP `Authorization` header accordingly.

Do not place real API keys in committed YAML files. Use your deployment platform's secret injection and restrict secret read access by service account.

### When multiple Elasticsearch credentials are needed

If the Search API and Writer need different roles, you can define two separate client/operations beans, each using its respective credential. Services inject the bean matching their responsibility.

Diagram:

~~~text
SearchService
   |
   +--> searchOperations
           |
           +--> Elasticsearch client (read API key)

ProductCommandService
   |
   +--> writeOperations
           |
           +--> Elasticsearch client (write API key)
~~~

When configuring multiple clients, give beans explicit names and use `@Qualifier` during injection to avoid mistakes. Do not leave an admin client as the default bean used by every repository simply for convenience.

In some applications, a single service account with scoped read/write privileges on the exact indices is sufficient. Split clients only when permission boundaries or operational needs justify it and the team can manage the corresponding secrets and connection pools.

## 14. Do Not Use Admin Privileges for Health Checks

Health checks and readiness probes normally do not require index administration privileges. Define what the probe needs to check:

- Can the application still reach Elasticsearch?
- Is the cluster healthy enough to serve requests?
- Does the target alias/index exist?
- Can the Search API run a lightweight sample query?

A probe checking connectivity can use a health/cluster endpoint appropriate for `monitor` privileges, or perform a minimal read on a known index. Do not grant `manage` just so a health endpoint can read cluster metadata.

If a probe must read cluster health, use a dedicated monitor credential or minimal `monitor` privileges matching the called API. Do not put administrative credentials in actuator endpoints.

## 15. Testing Roles and Effective Permissions

Valid role JSON does not prove the application behaves properly. Test using the exact user/API key the service will run with.

### Check current identity

~~~http
GET /_security/_authenticate
~~~

The response shows the user/API key identity and effective roles according to security configuration.

### Check specific privileges

Elasticsearch provides an API to verify privileges:

~~~http
POST /_security/user/_has_privileges
Content-Type: application/json

{
  "cluster": [],
  "index": [
    {
      "names": ["products-v2"],
      "privileges": ["read"]
    }
  ]
}
~~~

Use the credential under test to confirm read permissions. You can also test `write`, `create_doc`, or `manage` depending on the role.

### Test actual behavior

| Test | Search Role | Writer Role | Index Admin Role |
|---|---|---|---|
| Search products | Allowed | Only if `read` granted | Per granted privileges |
| Create document | Denied | Allowed if `create`/`write` granted | May be allowed under `manage` |
| Update document | Denied | Allowed if `write` granted | May be allowed under `manage` |
| Delete document | Denied | Only if `write`/`delete` granted | May be allowed under `manage` |
| Create index | Denied | Denied | Allowed |
| Update mapping | Denied | Denied | Allowed |
| Delete index | Denied | Denied | Allowed |
| Manage alias | Denied | Denied | Allowed if role has matching privilege |

Tests must verify both allowed actions and denied actions. Testing only the happy path will not detect overly broad roles.

## 16. Rotating and Revoking Credentials

API keys and service account credentials need a lifecycle:

1. Create a new key with least-privilege roles.
2. Update the secret in the deployment environment.
3. Restart/reload the service to pick up the new key.
4. Confirm authentication and API behavior.
5. Revoke the old key once no workload uses it.
6. Monitor authentication errors after rotation.

Do not share a single API key across unrelated services if you need independent auditing and revocation. If a shared key is compromised, revoking it can take down multiple workloads at once.

Never log `Authorization` headers, API keys, passwords, or full connection URIs containing credentials. Restrict secret read access and API key creation permissions.

## 17. Secure Role Design Principles

A practical set of guidelines:

- Grant permissions by task, not by generic job titles.
- Restrict index names with narrow patterns.
- Never grant `all` to runtime applications.
- Keep search roles read-only.
- Give writer roles only the required document operations.
- Use `create_doc` for create-only ingestion when suitable.
- Use a separate identity for index admin during deployment/migration.
- Grant cluster privileges only when an administrative API truly needs them.
- Never expose admin credentials to browsers/mobile apps or in API responses.
- Test both allow and deny cases.
- Use TLS and a secret manager.
- Rotate, revoke, and audit credentials.
- Enforce tenant/ownership authorization inside the application.
- Revalidate roles whenever adding new APIs or changing bulk/update operations.

## 18. Common Mistakes

### Using one superuser for every service

The Search API could delete indices if its credential holds full rights. Create separate roles for read, write, and index administration.

### Thinking Spring Security replaces Elasticsearch Security

Spring Security protects application endpoints. Elasticsearch still checks backend credentials when receiving requests. Both layers are needed.

### Granting read/write across all indices

Using `*` can open access to unrelated indices. Scope down to `products-*` or the exact index names needed.

### Assuming `write` includes index administration

Document write permissions are distinct from creating/deleting indices or modifying mappings/settings. Grant administrative permissions separately.

### Using `create_doc` for updates

Create-only does not cover update/delete. If operations must replace or update documents, pick the matching privilege and test it.

### Forgetting metadata privileges

Some clients or APIs reading mappings/aliases need `view_index_metadata`. Add it only after confirming the actual request lacks that permission.

### Assigning Elasticsearch roles to end users assuming automatic tenant isolation

If every request flows through a single service account, Elasticsearch sees the same identity. The application must still enforce tenant and ownership filters.

### Putting admin credentials into runtime containers

A bug in the service could delete indices or modify mappings. Keep administrative credentials within deployment/operations workflows.

### Failing to inspect individual bulk items

A bulk request can have both succeeded and rejected items. Inspect `items` and handle partial failures.

### Failing to rotate API keys

Long-lived, widely shared keys increase exposure risk. Use dedicated keys, appropriate expirations, and rotation procedures.

## 19. Privilege Separation Implementation Workflow

When separating read, write, and index administration privileges:

1. List the services and exact Elasticsearch APIs each service calls.
2. Categorize operations into search/read, document create/write/delete, index administration, and cluster administration.
3. Choose narrow index patterns per role.
4. Create the read role with `read`, adding metadata privileges only if needed.
5. Create a create-only role with `create_doc` if ingestion does not update/delete.
6. Create a writer role with `write` for services that update documents.
7. Create a dedicated index admin role for migration/deployment.
8. Grant specialized cluster privileges for templates/ILM only when workflows need them.
9. Create dedicated users/API keys and store secrets in a secret manager.
10. Configure Spring Data clients/operations to use the credential matching each duty.
11. Protect endpoints with Spring Security and check tenant/ownership in services.
12. Test both allowed and denied requests with real credentials.
13. Monitor authorization failures, key usage, and credential rotation.
14. Whenever new operations are added, update roles minimally and retest both allow and deny cases.

## References

- [Elasticsearch — Security privileges](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-privileges.html)
- [Elasticsearch — Defining roles](https://www.elastic.co/guide/en/elasticsearch/reference/current/defining-roles.html)
- [Elasticsearch — Create or update roles API](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-put-role.html)
- [Elasticsearch — Create API key API](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-create-api-key.html)
- [Elasticsearch — Has privileges API](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-has-privileges.html)
- [Elasticsearch — Authentication API](https://www.elastic.co/guide/en/elasticsearch/reference/current/security-api-authenticate.html)
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html)
- [Spring Data Elasticsearch — Configuration](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/clients.html)

## Conclusion

Separating search read, document write, and index administration privileges reduces the blast radius when a credential is exposed or a service malfunctions. Use Elasticsearch index privileges such as `read`, `create_doc`, `write`, and `manage` according to each duty; narrow index patterns and keep cluster administration in dedicated deployment/operations identities. Spring Security continues to govern end users at the API layer, while Elasticsearch Security protects the cluster through backend credentials. In multi-tenant systems, the application must still enforce tenant/ownership checks because one service credential can read across multiple documents in the same index. Test both allowed and denied privileges, manage secrets carefully, and rotate API keys on a clear lifecycle.
