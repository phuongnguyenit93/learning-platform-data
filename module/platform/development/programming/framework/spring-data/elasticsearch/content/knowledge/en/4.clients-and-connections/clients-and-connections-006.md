# Configuring Accounts, API Keys, and Authentication Headers

Spring Data Elasticsearch communicates with Elasticsearch through an HTTP client. When security is enabled on Elasticsearch, every request must carry valid authentication credentials. Accounts, passwords, API keys, or tokens allow the server to identify the caller; permissions assigned to that identity determine whether the request may read, write, create indices, or manage the cluster.

This lesson covers how to configure authentication for Spring Boot applications using Spring Data Elasticsearch, how to send custom headers, and how to manage secrets. Examples use HTTPS for remote clusters. With a local Elasticsearch instance where security is disabled in a learning environment, the application can connect over HTTP without credentials; do not apply that pattern to shared clusters or production.

## 1. Authentication and authorization

These two concepts often appear together but answer different questions:

- **Authentication:** who is making the request? The server validates login credentials, an API key, or a token to establish identity.
- **Authorization:** what is that identity allowed to do? Elasticsearch checks permissions on the cluster, indices, and specific operations.

For example, an application may authenticate successfully with an API key that only has read access to the `products` index. When the application calls a search API, the request succeeds; when it attempts to write a document or delete the index, Elasticsearch may return `403 Forbidden` due to insufficient privileges.

Do not grant cluster admin permissions to an application just because it needs to read and write documents. Identify the exact indices and operations required first, and grant the corresponding minimum privileges.

## 2. Common authentication methods

Elasticsearch and systems sitting in front of it may use several ways to transmit credentials:

| Method | HTTP Header | Use Case |
| --- | --- | --- |
| HTTP Basic Authentication | `Authorization: Basic <base64(username:password)>` | Elasticsearch account with username and password. |
| Elasticsearch API key | `Authorization: ApiKey <encoded-api-key>` | Applications or services needing dedicated credentials with scoped permissions and expiration. |
| Bearer token | `Authorization: Bearer <token>` | Service tokens, OAuth/OIDC tokens, or auth systems configured to support Bearer tokens. |
| Custom header | E.g., `X-API-Key: <value>` | API gateway, reverse proxy, or internal auth layer requiring a custom header. |

Do not confuse these schemes. Elasticsearch API keys use the `ApiKey` scheme; they do not automatically work as Bearer tokens or `X-API-Key` headers. Use only the exact header format accepted by Elasticsearch or the gateway in front of it.

### 2.1. Basic Authentication

Basic Authentication sends the username and password in the `Authorization` header. Credentials are Base64-encoded in `username:password` format before sending.

Example header structure:

~~~http
Authorization: Basic <base64-encoded-credentials>
~~~

Base64 is merely a data encoding, not encryption. Anyone able to read the request can decode the username and password. Therefore, Basic Authentication must be sent over HTTPS when connecting across a network.

In a Spring Boot application, configure account credentials via environment variables rather than putting passwords directly in committed config files:

~~~yaml
spring:
  elasticsearch:
    uris: https://elasticsearch.example.com:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
~~~

Spring Boot uses these properties when auto-configuring the Elasticsearch client. The supplied account must have read permissions on the relevant indices, and the server's TLS certificate must be trusted by the JVM.

When running local HTTP with security disabled, the URI can be `http://localhost:9200` with no username/password. Do not put dummy passwords into configuration just to make the application start.

### 2.2. Elasticsearch API key

An API key is a credential generated specifically for an application or purpose. Compared to sharing a personal account password, API keys isolate application permissions, support expiration, and can be revoked independently.

When creating an API key, Elasticsearch returns fields such as `id`, `name`, `api_key`, and `encoded`. The `encoded` field is already Base64-encoded in `id:api_key` format; this is the value used in the authentication header:

~~~http
Authorization: ApiKey <encoded-value-returned-by-Elasticsearch>
~~~

Do not Base64-encode it a second time when using the `encoded` field. Both `api_key` and `encoded` are secrets; display or store them only in protected locations. Elasticsearch returns the secret only once at key creation time, so store it securely immediately upon receiving the response.

### 2.3. Bearer token

Bearer tokens are typically used when a system issues access tokens, such as service tokens or OAuth/OIDC tokens. Requests send the token in the header:

~~~http
Authorization: Bearer <access-token>
~~~

Tokens usually have an expiration. The application must have a mechanism to obtain a fresh token before expiry and send the current token on requests. Do not use `Bearer` for an encoded Elasticsearch API key unless a gateway layer is explicitly designed to accept it that way.

### 2.4. Custom headers

A reverse proxy or API gateway may require custom headers, for example:

~~~http
X-API-Key: <gateway-key>
X-Tenant-ID: learning-team
~~~

Headers like `X-API-Key` are not Elasticsearch's default API key authentication convention. Verify the contract of the gateway or intermediary service before configuring them. If a gateway authenticates requests and forwards them to Elasticsearch, clarify how the gateway propagates caller identity and permissions to the backend.

## 3. Creating a least-privilege API key

An API key should represent a single application and grant access only to the indices that application needs to touch. Keys can be created via Kibana Dev Tools or the Elasticsearch Security API.

Example creating a key for an application managing the `products` index with read, write, and index metadata view privileges:

~~~http
POST /_security/api_key
Content-Type: application/json

{
  "name": "spring-data-products-lab",
  "expiration": "30d",
  "role_descriptors": {
    "products_app": {
      "cluster": [],
      "indices": [
        {
          "names": ["products"],
          "privileges": [
            "read",
            "write",
            "view_index_metadata"
          ]
        }
      ]
    }
  }
}
~~~

This example assumes the `products` index already exists. If the application needs to create the index itself, grant `create_index` for the appropriate index pattern after defining the initialization flow clearly. Never grant `all` or cluster admin privileges simply so a repository can write documents.

The creator of the API key must possess appropriate API key management privileges. The API key's effective privileges are capped by both the creator's privileges and the role descriptors specified at creation; a role descriptor cannot grant an API key more privileges than its creator holds.

Illustrative key creation response structure:

~~~json
{
  "id": "<key-id>",
  "name": "spring-data-products-lab",
  "api_key": "<secret-value-returned-once>",
  "encoded": "<encoded-id-and-secret-for-authorization-header>"
}
~~~

Store the `encoded` field in a secret store or the application's environment variables. Never store real responses containing secrets in Git, tickets, build logs, or shared docs.

You can test the key by calling an Elasticsearch API with the `Authorization: ApiKey ...` header and performing an authorized operation, such as searching the `products` index. Once the key expires, is revoked, or lacks privileges, requests will no longer succeed as before.

## 4. Configuring Basic Authentication in Spring Boot

With Spring Boot auto-configuration, the simplest approach is declaring the URI, username, and password in configuration. For example:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS:https://elasticsearch.example.com:9200}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
~~~

Environment variables can be supplied by the runtime environment, a secret manager, or deployment configuration. Never put real values into Git-managed YAML files.

When multiple endpoints are needed, the `uris` property can hold a list of URIs in the format supported by Spring Boot. All endpoints must belong to the same cluster or an endpoint group with a compatible client contract.

Example configuring via the shell before running the application:

~~~bash
export ELASTICSEARCH_URIS=https://elasticsearch.example.com:9200
export ELASTICSEARCH_USERNAME=products-app
export ELASTICSEARCH_PASSWORD="<secret-from-secret-store>"
~~~

On Windows PowerShell, terminal session environment variables can be set with `$env:ELASTICSEARCH_USERNAME = "products-app"` and `$env:ELASTICSEARCH_PASSWORD = "..."`. Do not write real secrets into shared scripts or command histories that may be persisted.

Once Spring Boot configures the client, Spring Data beans like repositories and `ElasticsearchOperations` share that connection. There is no need to add Basic headers manually on individual repository calls.

## 5. Configuring an API key with Spring Data Elasticsearch

An API key can be sent via custom client headers. With Spring Data Elasticsearch 5.x, you can define `ClientConfiguration` and supply the `Authorization` header when configuring the client.

The example below uses the `encoded` value received from Elasticsearch. `host-and-port` contains only hostname and port without an `https://` prefix; `.usingSsl()` selects HTTPS for the connection.

~~~yaml
app:
  elasticsearch:
    host-and-port: ${ELASTICSEARCH_HOST_AND_PORT:elasticsearch.example.com:9200}
    api-key: ${ELASTICSEARCH_API_KEY}
~~~

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.elasticsearch.client.ClientConfiguration;
import org.springframework.data.elasticsearch.client.elc.ElasticsearchConfiguration;
import org.springframework.http.HttpHeaders;

@Configuration
public class ProductSearchClientConfiguration extends ElasticsearchConfiguration {

    private final String hostAndPort;
    private final String encodedApiKey;

    public ProductSearchClientConfiguration(
            @Value("${app.elasticsearch.host-and-port}") String hostAndPort,
            @Value("${app.elasticsearch.api-key}") String encodedApiKey) {
        this.hostAndPort = hostAndPort;
        this.encodedApiKey = encodedApiKey;
    }

    @Override
    public ClientConfiguration clientConfiguration() {
        return ClientConfiguration.builder()
                .connectedTo(hostAndPort)
                .usingSsl()
                .withHeaders(() -> {
                    HttpHeaders headers = new HttpHeaders();
                    headers.set(HttpHeaders.AUTHORIZATION, "ApiKey " + encodedApiKey);
                    return headers;
                })
                .build();
    }
}
~~~

In this configuration:

- `ElasticsearchConfiguration` provides Spring Data Elasticsearch setup based on `ClientConfiguration`.
- `connectedTo` takes Elasticsearch's host and port.
- `usingSsl()` enables TLS for HTTPS connections.
- `withHeaders` supplies headers for HTTP requests sent by the client.
- `Authorization` uses the `ApiKey` scheme and the `encoded` value returned by Elasticsearch.

If the cluster serves only HTTP in a local lab, omit `.usingSsl()`. Do not omit TLS for remote clusters just to avoid certificate errors; configure the trust chain properly on the JVM side.

This is a manual client configuration approach. When using it, ensure the application has only one active Elasticsearch client configuration and does not accidentally create another client with different credentials or endpoints. Pick one consistent configuration path between Spring Boot auto-configuration and `ElasticsearchConfiguration`.

## 6. Configuring Basic Auth with ClientConfiguration

If you prefer managing the client manually instead of using Spring Boot auto-configuration properties, `ClientConfiguration` also supports Basic Authentication:

~~~java
import org.springframework.data.elasticsearch.client.ClientConfiguration;

ClientConfiguration clientConfiguration = ClientConfiguration.builder()
        .connectedTo("elasticsearch.example.com:9200")
        .usingSsl()
        .withBasicAuth(username, password)
        .build();
~~~

The snippet above shows how to construct the configuration; in a real application, place it inside a Spring Data configuration managed by the Spring container. Obtain `username` and `password` from secret configuration rather than hardcoding them in source code.

Use only one authentication mechanism for an endpoint unless a gateway specifically requires a combination. Declaring Basic Auth while also manually adding `Authorization: ApiKey ...` can conflict because a request should carry a single `Authorization` value expected by the server.

## 7. Sending Bearer tokens or custom headers

`withHeaders` can also be used to send Bearer tokens or headers required by a gateway. For example:

~~~java
import org.springframework.http.HttpHeaders;

ClientConfiguration clientConfiguration = ClientConfiguration.builder()
        .connectedTo("elasticsearch.example.com:9200")
        .usingSsl()
        .withHeaders(() -> {
            HttpHeaders headers = new HttpHeaders();
            headers.setBearerAuth(accessToken);
            headers.set("X-Tenant-ID", tenantId);
            return headers;
        })
        .build();
~~~

In this example, `accessToken` must be a Bearer token issued by the authentication system and `tenantId` a value accepted by the gateway/backend. If using an Elasticsearch API key, replace `setBearerAuth(accessToken)` with the `Authorization` header using the `ApiKey` scheme as shown earlier.

The header supplier is invoked when the client needs to obtain headers for requests. If a token is short-lived, do not hold a static token in configuration for the entire application lifecycle. Integrate a token provider capable of refreshing tokens and handling failures when the identity provider is unavailable. Never log tokens while refreshing or sending requests.

For a gateway's `X-API-Key` header, you can use `headers.set("X-API-Key", gatewayKey)`. This only works when the gateway is explicitly configured to check that header; Elasticsearch does not treat `X-API-Key` as its standard API key scheme.

## 8. Calling the API directly to verify credentials

Before testing repositories, you can verify endpoints and credentials with curl. Example with an API key on an HTTPS endpoint using a private CA certificate:

~~~bash
curl --cacert ./http_ca.crt \
  -H "Authorization: ApiKey ${ELASTICSEARCH_API_KEY}" \
  "https://elasticsearch.example.com:9200/_cluster/health?pretty"
~~~

`ELASTICSEARCH_API_KEY` in the example is the `encoded` value, not the raw `api_key`. The `http_ca.crt` file is the CA certificate the client must trust; the exact filename and location depend on how the cluster is deployed.

With Basic Authentication:

~~~bash
curl --cacert ./http_ca.crt \
  -u "${ELASTICSEARCH_USERNAME}:${ELASTICSEARCH_PASSWORD}" \
  "https://elasticsearch.example.com:9200/_cluster/health?pretty"
~~~

With a Bearer token:

~~~bash
curl --cacert ./http_ca.crt \
  -H "Authorization: Bearer ${ELASTICSEARCH_ACCESS_TOKEN}" \
  "https://elasticsearch.example.com:9200/_cluster/health?pretty"
~~~

When testing, call an API the credential is authorized to invoke. The `_cluster/health` API may require specific cluster privileges; an API key with only index privileges might authenticate fine yet still be denied cluster health access. In that case, test with an API on an authorized index, such as `GET /products/_search`.

Never put credentials in query strings or URLs. URLs frequently appear in access logs, proxy logs, browser history, and request observability tools.

## 9. TLS and digital certificates

Credentials are only protected in transit when the connection uses TLS properly. For remote clusters, use `https://` and ensure the JVM trusts the CA that signed the server certificate.

If your organization provides a PKCS12 truststore, you can configure the JVM when running the application:

~~~bash
java \
  -Djavax.net.ssl.trustStore=/path/to/elasticsearch-truststore.p12 \
  -Djavax.net.ssl.trustStorePassword="${TRUSTSTORE_PASSWORD}" \
  -Djavax.net.ssl.trustStoreType=PKCS12 \
  -jar application.jar
~~~

The truststore holds the CAs or certificates needed by the JVM to verify the server certificate. The truststore password is also sensitive and should come from a secret store or the runtime environment.

Never disable certificate validation, hostname verification, or use a trust-all SSL context in real environments. Those practices eliminate server verification and risk sending credentials to a spoofed endpoint.

In some environments, the client needs a dedicated truststore or SSL context instead of a JVM-wide truststore. In that case, configure SSL according to your Spring Data Elasticsearch and HTTP client versions; avoid copying TLS code from another library version without checking the corresponding API.

## 10. Managing and protecting credentials

Usernames/passwords, API keys, Bearer tokens, and gateway keys are all secrets. Management practices should satisfy these principles:

- **Never commit secrets:** commit only variable names or placeholders, never real values in YAML, `.properties`, Docker Compose, or Java source files.
- **Separate by environment:** use distinct credentials for local, test, staging, and production; never share one API key across unrelated applications.
- **Least privilege:** grant permissions only on the indices and operations the application requires.
- **Set expiration:** API keys and access tokens should have expirations aligned with their usage lifecycle.
- **Rotate:** create a new key, update the secret in the application, verify requests succeed, and then revoke the old key.
- **Revoke on compromise:** if a secret is exposed, revoke it immediately and audit relevant access logs.
- **Do not log headers:** never print `Authorization`, passwords, or tokens in HTTP logs, exceptions, or tracing spans.
- **Protect pipelines:** CI/CD secrets must reside in the platform's secret store and be exposed only to jobs that need them.

To rotate an API key without downtime, create a new key while the old key remains active, update the application secret, restart or reload credentials as designed, verify operation, and then delete the old key. If the client reads credentials only at startup, an explicit restart or refresh mechanism is required for the client to pick up the new key.

Never share API keys via chat, email, screenshots, or sample config files. Replace real secrets with placeholders when writing documentation examples.

## 11. Troubleshooting authentication and connection errors

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `401 Unauthorized` | Missing header, wrong username/password, invalid API key, expired token, or wrong authentication scheme. | Check headers, the secret loaded by the application, and the scheme required by the server. |
| `403 Forbidden` | Authentication succeeded, but privileges on the index or operation are missing. | Check user/API key roles, index patterns, and privileges required for the operation. |
| SSL handshake/certificate error | JVM does not trust the CA, expired certificate, or hostname mismatches SAN. | Check the URL, certificate chain, hostname, and truststore. |
| Connection refused/timeout | Wrong host/port, firewall, service not ready, or unroutable network. | Check the endpoint, Docker port mapping, DNS, and cluster status. |
| Request works with curl but fails in Spring | Application loads a different secret, client ignores expected config, or TLS/header settings differ. | Compare endpoint, scheme, truststore, and client setup; do not print secrets while comparing. |
| API key works for reads but fails on writes/index creation | Key has only read privileges or lacks index management privileges. | Grant the exact privileges needed for the specific index. |

### 11.1. Distinguishing 401 and 403 errors

`401` usually indicates the server could not authenticate the request. Verify whether the client sent the header, whether the scheme is right, whether credentials have stray whitespace or came from the wrong environment, and whether the key/token is still valid.

`403` usually indicates the server recognized the identity, but that identity is not permitted to perform the operation. Check index permissions, operation type, and required cluster privileges. Do not solve `403` errors by switching to a superuser account; grant the smallest privilege set that satisfies the use case.

### 11.2. Inspecting configuration without exposing secrets

You can log endpoints, TLS status, active profile names, or whether a secret is loaded. Never log full username/password values, API keys, access tokens, or `Authorization` header contents.

To confirm the client is using new credentials, call an endpoint checking appropriate permissions and observe the status code. If deeper analysis is needed, enable safe-level client logging and configure header redaction before sharing logs.

## 12. Choosing an authentication method for your application

| Scenario | Recommended Choice |
| --- | --- |
| Local practice lab, Elasticsearch bound to loopback with security disabled | HTTP without credentials, only in a lab environment. |
| Internal application using a stable service account | Basic Authentication over HTTPS, with a least-privilege account. |
| Each application needs its own secret with scoped permissions and independent revocation | Elasticsearch API key. |
| Organization uses OAuth/OIDC or service tokens | Bearer token with proper token issuance and refresh mechanisms. |
| Elasticsearch sits behind an API gateway with custom auth conventions | Header required by the gateway, such as `X-API-Key`, over HTTPS. |

In a Spring Data Elasticsearch application, authentication is configured on the client. Once the client sends the right endpoint, TLS, and headers, repositories operate on indices according to mappings and that identity's privileges. Therefore, when troubleshooting errors, isolate three parts separately: network connectivity, identity authentication, and operation authorization.

## 13. End-to-end configuration workflow

When integrating a Spring Boot application with a security-enabled cluster, follow this sequence:

1. Identify the Elasticsearch endpoint, port, HTTP/HTTPS protocol, and CA certificate.
2. Identify the authentication method supported by the cluster: Basic, API key, Bearer token, or gateway header.
3. Create a dedicated account or API key for the application with minimum privileges on the required indices.
4. Store credentials and truststore passwords in a secret store or runtime environment variables.
5. Configure Spring Boot properties for Basic Authentication, or create a `ClientConfiguration` with headers for API keys/Bearer/custom headers.
6. Verify connectivity and authentication using an API the identity is permitted to call.
7. Test read/write permissions on the actual index with corresponding operations.
8. Monitor expiration, rotate, and revoke credentials according to operational procedures.

Once credentials and headers are properly configured, Spring Data Elasticsearch can use the same client to manipulate documents and indices. Accounts or API keys should carry only the privileges the application needs, while TLS protects credentials in transit and secret management protects them throughout the deployment lifecycle.
