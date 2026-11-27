# Configuring Cluster Addresses and Authentication Credentials

A Spring Boot application using Spring Data Elasticsearch needs to know the Elasticsearch HTTP endpoint and how to authenticate when sending requests. An incorrect address typically causes DNS errors, connection refused, or timeouts; invalid credentials typically cause HTTP 401 or 403. This lesson covers configuring endpoints, single or multiple nodes, Basic Authentication, HTTPS/TLS, environment-specific secrets, timeouts, and verifying connectivity.

## 1. Determining the Correct Cluster Address

### 1.1. Elasticsearch HTTP Endpoint

An Elasticsearch cluster can consist of one or more nodes. Each node can expose an HTTP endpoint for clients to send search, read, write, or management requests. URIs typically take the form:

~~~text
http://localhost:9200
https://elasticsearch.example.com:9200
~~~

A URI consists of a scheme (`http`/`https`), a host (hostname or IP), a port, and optionally a path prefix when routed through a reverse proxy.

In common default configurations, port `9200` is the HTTP port. Port `9300` is typically reserved for transport communication between Elasticsearch nodes. A Spring Data Elasticsearch application uses an HTTP client, so it needs the HTTP endpoint—usually port 9200 or a port designated by your infrastructure.

Do not use the Kibana address as the Elasticsearch address. Kibana is a separate service; the Spring Data application needs the Elasticsearch endpoint.

### 1.2. Cluster, Node, and Endpoint

- A **Cluster** is a group of nodes operating together and managing data.
- A **Node** is an Elasticsearch process participating in a cluster.
- An **Endpoint** is a network address a client connects to, pointing to a node or a service sitting in front of the cluster.

Applications usually do not need to manage internal topology themselves. They receive one or more reachable HTTP addresses, and the HTTP client sends requests as configured.

| Environment | Common Address |
|---|---|
| Elasticsearch running directly on a developer machine | `http://localhost:9200` |
| Two containers on the same Docker network | `http://elasticsearch:9200` if the service is named `elasticsearch` |
| Kubernetes | Service DNS, e.g. `http://elasticsearch.default.svc:9200` |
| Server or VM | Hostname/IP and HTTP port provided by infrastructure |
| Elastic Cloud / managed service | HTTPS endpoint provided in the management console |

`localhost` always refers to the machine or network namespace where the application process is running. If Spring Boot runs in a container, `localhost` points to the application container itself, not another Elasticsearch container. Two containers on the same Docker network should use service names or internal DNS. If the application runs on the host while Elasticsearch runs in a container, use the port published to the host.

### 1.3. Single Node or Multiple Nodes?

For a simple development environment, one URI may suffice:

~~~yaml
spring:
  elasticsearch:
    uris:
      - http://localhost:9200
~~~

When multiple endpoints belong to the same cluster, you can declare a list:

~~~yaml
spring:
  elasticsearch:
    uris:
      - https://es-node-1.example.com:9200
      - https://es-node-2.example.com:9200
      - https://es-node-3.example.com:9200
~~~

This list provides multiple addresses for the client to connect to. How nodes are selected, retried, and switched depends on the HTTP client and its configuration. A URI list does not create a cluster, does not replace DNS/load balancers, and does not guarantee all nodes are reachable from where the application runs.

Only declare endpoints actually permitted to accept requests from the application. In production, many systems provide a stable load balancer or proxy endpoint rather than having every application know the addresses of all nodes.

### 1.4. Path Prefix

Some systems place Elasticsearch behind a reverse proxy and require requests to include a path prefix:

~~~text
https://gateway.example.com/search/
~~~

You can configure the base URI and path prefix separately:

~~~yaml
spring:
  elasticsearch:
    uris: https://gateway.example.com
    path-prefix: /search
~~~

Only use `path-prefix` when the infrastructure actually routes Elasticsearch under a subpath. Do not append `/products`, `/_search`, or an index name to the base connection URI. Those paths belong to individual API requests, not the cluster address.

## 2. Configuring Connections with Spring Boot

### 2.1. Basic Properties

In Spring Boot 3.3.x, the `spring.elasticsearch` property group configures endpoints and common connection details:

| Property | Purpose |
|---|---|
| `spring.elasticsearch.uris` | One or more HTTP/HTTPS endpoints |
| `spring.elasticsearch.username` | Username for HTTP Basic Authentication |
| `spring.elasticsearch.password` | Password for HTTP Basic Authentication |
| `spring.elasticsearch.connection-timeout` | Time to wait when establishing a connection |
| `spring.elasticsearch.socket-timeout` | Time to wait for data on a socket |
| `spring.elasticsearch.socket-keep-alive` | Enable/disable TCP keep-alive if supported by the client |
| `spring.elasticsearch.path-prefix` | Path prefix when routing through a proxy |

Minimal configuration example for local Elasticsearch without authentication:

~~~yaml
spring:
  elasticsearch:
    uris:
      - http://localhost:9200
    connection-timeout: 5s
    socket-timeout: 30s
~~~

Duration values can use units such as `ms`, `s`, or `m`. Choose timeouts based on network latency and query characteristics. Too short a timeout can interrupt valid requests; too long a timeout makes the application hold resources longer when the cluster has issues.

### 2.2. Configuring Basic Authentication

If Elasticsearch requires HTTP Basic Authentication, declare username and password:

~~~yaml
spring:
  elasticsearch:
    uris:
      - https://elasticsearch.example.com:9200
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 5s
    socket-timeout: 30s
~~~

Spring Boot uses these properties to configure the connection client. Placeholders resolve values from environment variables or supported Spring configuration sources.

Do not place username/password directly inside the URI like `https://user:password@host:9200`. That easily leaks credentials via logs, configuration files, command history, or request inspection tools.

Do not commit real passwords into `application.yml`, shared config files, Docker images, or Git repositories. Config files should only contain reference variable names; real secrets are supplied at deployment time.

### 2.3. Separating Configuration by Environment

Cluster addresses and credentials often differ across personal machines, testing, and production. You can keep shared defaults in `application.yml` and supply environment-specific values via profiles or environment variables.

Example `application.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS:http://localhost:9200}
    connection-timeout: 5s
    socket-timeout: 30s
~~~

Example `application-prod.yml`:

~~~yaml
spring:
  elasticsearch:
    uris: ${ELASTICSEARCH_URIS}
    username: ${ELASTICSEARCH_USERNAME}
    password: ${ELASTICSEARCH_PASSWORD}
    connection-timeout: 5s
    socket-timeout: 30s
~~~

When running in production, activate the `prod` profile and supply the corresponding environment variables. Example variable names:

~~~text
ELASTICSEARCH_URIS=https://es-prod.example.com:9200
ELASTICSEARCH_USERNAME=product-search-service
ELASTICSEARCH_PASSWORD=<secret provided by a secret management system>
~~~

The `<secret ...>` line is purely illustrative, not a valid password. Never store real secrets in committed config files.

Environment variables can be supplied via Docker/Kubernetes secrets, cloud platform secret managers, or CI/CD secret mechanisms. Avoid passing passwords as command-line arguments because command history and process listings can expose values.

Spring Boot follows a property source precedence order. Environment variables or deployment parameters can override values in YAML. If the application connects to the wrong cluster, check the effective values in the running environment, not just the file in the repository.

### 2.4. Client Configuration vs. Server Configuration

`spring.elasticsearch.*` is application-side Spring Boot configuration. It tells the client where to connect and how to authenticate.

Settings such as `cluster.name`, `node.name`, `network.host`, `http.port`, and `path.data` belong to the Elasticsearch server process configuration. Do not place them under `spring.elasticsearch` expecting Spring Boot to reconfigure the cluster.

Example Elasticsearch server configuration:

~~~yaml
cluster.name: product-search
node.name: es-node-1
network.host: 0.0.0.0
http.port: 9200
~~~

The Spring Boot application only needs the endpoint that the server publishes and permits access to. Configuring, starting, opening firewalls, or granting access on the Elasticsearch server is the responsibility of deployment/infrastructure.

## 3. Authentication and Access Permissions

### 3.1. Authentication vs. Authorization

- **Authentication** identifies which identity the application is connecting as.
- **Authorization** determines which operations that identity is permitted to perform.

A valid username/password does not guarantee the application can read or write every index. Elasticsearch may authenticate successfully yet reject an operation due to insufficient permissions.

For example, an account only permitted to search the `products` index may not be allowed to delete indices, create users, or read other indices. Grant permissions according to the principle of least privilege: a service should only have the permissions needed for its business function.

### 3.2. HTTP Basic Authentication

Basic Authentication sends username/password in the HTTP Authorization header using Base64 encoding. Base64 is not encryption; anyone who can read the header can recover the credentials.

Therefore:

- Only use Basic Authentication over HTTPS in production or whenever credentials traverse untrusted networks.
- Do not log the Authorization header.
- Do not share credentials across multiple applications if separate identities can be issued.
- Rotate passwords if credential exposure is suspected or per security policy.
- Assign roles with only the permissions required by the service.

Some development environments may disable security to simplify learning. Do not infer that production is also permitted to connect without authentication.

### 3.3. API Keys and Other Authentication Mechanisms

Elasticsearch also supports API keys and other authentication mechanisms depending on deployment. An API key is typically sent in the Authorization header according to Elasticsearch's specified format.

The `spring.elasticsearch.username` and `spring.elasticsearch.password` properties in the examples above are for Basic Authentication. Do not put an API key into the password field expecting the client to automatically treat it as an API key.

If the system issues an API key, configure the authentication header using the client customization mechanism supported by your Spring Boot/Spring Data Elasticsearch version. With Spring Data Elasticsearch, you may need to customize `ClientConfiguration` or the corresponding HTTP client. Choose the extension point appropriate for your library version; avoid creating a separate client while repositories/operations still use a different auto-configured client.

An API key is also a secret: grant only necessary permissions, store it in a secret manager, and never put it into source code or logs.

### 3.4. Secret Management

Common places where credentials are accidentally leaked include:

- Committed `application-prod.yml` files.
- Dockerfiles or image layers containing passwords.
- Logs printing all environment variables.
- CI jobs printing commands that contain secrets.
- Screenshots or documentation containing real credentials.
- Connection URLs containing username/password.

If credentials have been committed or sent to an insecure location, removing them from the current file is not enough because Git history, logs, or artifacts may still retain the old values. Revoke/rotate the credentials in Elasticsearch and remediate storage history according to your organization's security procedures.

## 4. HTTPS and TLS Certificates

### 4.1. When to Use HTTPS?

With an HTTP endpoint:

~~~text
http://elasticsearch.example.com:9200
~~~

requests are not encrypted at the TLS layer. With an HTTPS endpoint:

~~~text
https://elasticsearch.example.com:9200
~~~

the connection is encrypted and the client can verify the server's identity via a TLS certificate.

In production, especially when credentials travel over the network, use HTTPS. Many modern Elasticsearch installations enable security and TLS by default or per installation guides. Obtain the proper endpoint, CA certificate, and credentials from your administrator or deployment platform.

### 4.2. The Client Must Trust the CA Certificate

When connecting over HTTPS, the JVM must be able to verify the server's certificate chain, and the hostname in the certificate must match the hostname accessed by the client.

If the server uses a certificate issued by a trusted public CA, the JVM may already trust that CA. If the server uses an internal CA or self-signed certificate, add the appropriate CA to the truststore used by the JVM/client or configure an SSL context through a supported mechanism.

Ways to handle this at the JVM level:

- Install the internal CA certificate into the truststore used by the JVM.
- Specify an appropriate truststore using JVM system properties at startup.
- Use an SSL bundle or custom SSL configuration if supported by your Spring Boot and client versions.

Truststore filenames, paths, and passwords must be managed per deployment environment. Do not put private keys or truststore passwords into Git.

### 4.3. Do Not Disable Certificate Verification

When encountering `SSLHandshakeException`, the cause usually lies in the certificate chain, truststore, hostname, or TLS protocol. Inspect the certificates and trust configuration.

Do not use trust-all configurations, disable hostname verification, or skip certificate checks just to get a connection working in production. Those practices eliminate server authentication and can allow credentials to be sent to an impostor server.

If using mutual TLS (mTLS), the server also requires a client certificate. In addition to a truststore to verify the server, the client needs an appropriate keystore/certificate. mTLS configuration depends on infrastructure and how the HTTP client is constructed; basic username/password properties do not automatically configure full mTLS.

## 5. Timeouts and Connectivity

### 5.1. Connection Timeout

Connection timeout limits how long the client waits to establish a connection to the endpoint. If DNS fails to resolve, the host is unreachable, or the server does not accept connections, the operation can fail once this duration expires.

A value that is too low causes false errors under network latency; a value that is too high makes the application take too long to detect an unavailable endpoint.

### 5.2. Socket Timeout

Socket timeout limits how long to wait for data exchange on a connection per client configuration. Search queries can take longer than simple reads, so choose a value based on expected processing time and SLAs.

Do not raise timeouts indefinitely to mask slow queries. If queries frequently time out, investigate the query, mapping, data volume, cluster load, and network latency.

### 5.3. Timeouts, Retries, and Load Control

A timeout only bounds wait time. It does not guarantee a request can be safely retried. When adding retries, distinguish read operations from write operations and understand that a prior request may already have been processed by the server while the response was lost.

Do not retry indefinitely when a cluster is overloaded. Unbounded retry policies can amplify request volume and worsen system overload.

## 6. Spring Boot Auto-Configuration and Spring Data

### 6.1. Auto-Configuration

When a project includes a Spring Data Elasticsearch dependency compatible with its Spring Boot version, Boot can auto-configure client components based on `spring.elasticsearch.*`.

Repositories and `ElasticsearchOperations` use the connection configuration supplied by the application. Therefore, when only standard URIs, Basic Authentication, and timeouts are needed, starting with application configuration is usually sufficient.

Example service injecting a repository:

~~~java
@Service
public class ProductSearchService {

    private final ProductRepository productRepository;

    public ProductSearchService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    // Business methods calling the repository go here.
}
~~~

The service does not need to open sockets manually or attach Authorization headers per request. The client is configured at the integration layer and managed by Spring.

### 6.2. When Is Custom Client Configuration Needed?

Customization may be needed when the system uses API keys, special proxies, mTLS, custom SSL contexts, custom headers, or HTTP client requirements that basic properties cannot express.

Before creating custom configuration, determine your Spring Boot/Spring Data Elasticsearch version and corresponding extension points. If you manually create a `RestClient`, `ElasticsearchClient`, or custom Spring Data configuration, ensure repositories and `ElasticsearchOperations` share that exact client.

Do not accidentally create two connection paths: one auto-configured client from `spring.elasticsearch.*` and one manually created client with different credentials. In that case, repository requests might still go through the old client even though another client bean was configured.

When modifying auto-configuration, verify the actual beans created by Spring and log configuration with secrets masked. Never print passwords, API keys, or Authorization headers to verify them.

## 7. Verifying the Endpoint and Credentials

### 7.1. Testing from the Application Runtime Environment

Before testing Java code, verify that the machine/container running Spring Boot can reach the Elasticsearch endpoint.

A basic check is calling the root endpoint. Example in a POSIX-style terminal:

~~~bash
curl --fail --silent --show-error \
  --user "$ELASTICSEARCH_USERNAME:$ELASTICSEARCH_PASSWORD" \
  "$ELASTICSEARCH_URI/"
~~~

If the endpoint uses an internal CA, supply the issued CA certificate:

~~~bash
curl --fail --silent --show-error \
  --cacert "$ELASTICSEARCH_CA_CERT" \
  --user "$ELASTICSEARCH_USERNAME:$ELASTICSEARCH_PASSWORD" \
  "$ELASTICSEARCH_URI/"
~~~

Variables in the examples must be set in the terminal environment prior to running. Do not replace them with real passwords and save the commands in documentation or shared scripts. For a local endpoint without authentication, you can call the root endpoint without passing `--user`.

The root endpoint typically returns basic cluster/node and version information when the request is accepted. This is an initial endpoint and authentication check; it does not prove the account has permission to query the index the application needs.

### 7.2. Checking Cluster Health When Authorized

You can additionally check:

~~~bash
curl --fail --silent --show-error \
  --user "$ELASTICSEARCH_USERNAME:$ELASTICSEARCH_PASSWORD" \
  "$ELASTICSEARCH_URI/_cluster/health"
~~~

The cluster health API may require cluster monitoring privileges. If a service account is only granted read permission on the `products` index, this request may be rejected even though the application searches products normally.

Do not grant cluster admin privileges just to make a health check work. Use a dedicated monitoring account or check an API the service is actually authorized to access.

### 7.3. Testing Inside the Application

Once the endpoint works from the runtime environment, start the Spring Boot application with the right profile and environment variables. Test a simple repository operation or an authorized query.

If the root endpoint succeeds but search operations fail, check:

- Whether the account has permissions on the target index.
- Whether the index already exists.
- Whether field mappings match the query.
- Whether the application is connecting to the right cluster/profile.
- Whether requests traverse the right proxy or path prefix.

Spring creating a client bean does not necessarily prove the cluster is ready. Execute an actual test request from the application.

## 8. Diagnosing Common Connection Errors

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `UnknownHostException` | Incorrect hostname or DNS resolution failure | Check URI, DNS, and container network |
| `Connection refused` | Wrong port, server not running, or not listening on that address | Check HTTP port and service status |
| `Connect timed out` | Firewall, network routing, or unreachable endpoint | Check network policy, security group, and endpoint |
| HTTP `401 Unauthorized` | Missing or invalid credentials | Check username/password, API key, and auth mechanism |
| HTTP `403 Forbidden` | Authenticated but lacking permissions | Check role/index privileges |
| `SSLHandshakeException` | Untrusted CA, invalid certificate, or incompatible TLS | Check truststore, certificate chain, and hostname |
| HTTP `404 Not Found` | Wrong endpoint, path prefix, or nonexistent resource/index | Check URL and proxy routing |
| HTTP `400 Bad Request` | Invalid request/query or incompatible data type | Read response body and check query/mapping |
| Socket/read timeout | Slow cluster processing, slow network, or too short timeout | Check latency, cluster load, and query |
| Connected but no results returned | Query does not match or index/data differs from expectations | Check index, documents, analyzer, and query |

Categorize errors by layer before changing configuration:

1. **DNS/network**: can the application resolve the host and open a connection?
2. **TLS**: can the client verify the server certificate?
3. **Authentication**: does the server recognize the application's identity?
4. **Authorization**: does that identity have permission to call the required API/index?
5. **Application/query**: does the request use the right endpoint, mapping, and syntax?

Do not change multiple properties at once. Changing one factor at a time based on error evidence identifies the root cause faster.

## 9. Environment Configuration Checklist

Before deploying the application to a new environment, confirm:

- [ ] You have the correct HTTP/HTTPS URI of the Elasticsearch endpoint.
- [ ] The hostname and port are reachable from the actual Spring Boot runtime environment.
- [ ] You have not confused the HTTP port with the transport port or Kibana address.
- [ ] If using Docker/Kubernetes, the hostname fits internal networking/DNS.
- [ ] If using multiple URIs, all are valid endpoints the client is permitted to access.
- [ ] If going through a reverse proxy, the path prefix is configured accurately.
- [ ] The authentication mechanism is identified: Basic Auth, API key, or another mechanism.
- [ ] Credentials are supplied from a secret manager/environment, not stored in Git.
- [ ] The account has the right permissions on required indices and APIs.
- [ ] The HTTPS certificate is trusted by the JVM and hostname verification is enabled.
- [ ] Connection timeout and socket timeout fit the environment.
- [ ] The endpoint has been tested from the runtime environment and an authorized application operation succeeded.
- [ ] Logs do not print passwords, API keys, tokens, or Authorization headers.

Once these items are clear, you can proceed to declaring documents, mappings, and repositories. Those components will use the Spring Boot-configured client to communicate with the cluster.
