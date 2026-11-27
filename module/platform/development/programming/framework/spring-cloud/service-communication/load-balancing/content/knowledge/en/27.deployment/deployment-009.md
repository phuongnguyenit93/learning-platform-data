# Environment-Specific Configuration and Connection Secrets

A Spring Boot application using **Spring Cloud LoadBalancer** normally must run across multiple environments: **development**, **testing**, **staging**, and **production**. Order Service's business code may always call **http://inventory-service/api/stock/{sku}**, yet how instances are discovered, timeout bounds, retry policies, deployment zones, TLS/mTLS, and credentials for calling Inventory Service all vary by environment.

Putting **production host addresses, passwords, API keys, client secrets, or private keys** directly into source code or `application.yml` committed to Git makes every deployment riskier. Manually editing config on individual Pods causes replicas of the same service to run inconsistent policies and trigger 401/403 errors, TLS handshake failures, 503s, or wrong service IDs. The solution is designing a **configuration contract**, defining **sources and precedence**, separating **secrets from public values**, and verifying the final resolved state right inside the deployment pipeline.

In this lesson of the **Deployment** chapter of **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**, we manage environment-specific configuration for **RestClient, WebClient, OpenFeign, and Spring Cloud LoadBalancer**, covering discovery, health checks, caching, retries/timeouts, SSL bundles, OAuth2/API keys, Kubernetes ConfigMaps/Secrets, Spring Cloud Config, testing, config versioning, and rollback.

**Scope note:** The YAML, Java, and Kubernetes manifests are educational examples; hostnames, paths, and timeout values are illustrative. No real credentials appear in this lesson. Choose Spring Boot, Spring Cloud, and HTTP engine versions according to your project's compatible BOM; a setting on Spring Cloud LoadBalancer does not automatically activate identical behavior across every HTTP client.

## 1. Distinguishing operational configuration from connection secrets

**Operational configuration** consists of values determining how the application runs: service IDs, timeouts, cache TTLs, algorithm choices, supporting system URLs, zone names, or profiles.

**Connection secrets** consist of data granting access or proving identity: OAuth2 client secrets, API keys, passwords, mTLS private keys, refresh tokens, and credentials used to read secret/config stores.

| Value | Category | Example | Commit to Git? |
| --- | --- | --- | --- |
| Spring application name | Configuration | order-service | Yes |
| Logical service ID | Configuration | inventory-service | Yes |
| Connect/read timeout | Configuration | 500 ms / 2 s | Yes |
| LoadBalancer cache TTL | Configuration | 35s or measured value | Yes |
| Discovery provider URL without credentials | Configuration | https://registry.internal | Depends on infrastructure policy |
| Caller zone | Configuration | zone-a | Yes if non-sensitive |
| OAuth2 issuer URL | Configuration | https://identity.example.internal | Depends on security model |
| OAuth2 client ID | Application identity | order-inventory | Usually yes, per policy |
| OAuth2 client secret | **Secret** | (never record real values) | **No** |
| Inventory API key | **Secret** | (never record real values) | **No** |
| mTLS client private key | **Secret** | Protected PEM/keystore file | **No** |
| Server CA public certificate | Trust material | inventory-ca.pem | Possible, though lifecycle must be managed |
| Truststore password | **Secret if present** | Secret store | **No** |

**A URL containing a username/password or a token in its query string is still a secret.** Do not assume URLs are always public configuration. Nor is a password safe merely because it is Base64-encoded in a Kubernetes Secret: Base64 is representation encoding, not encryption.

### 1.1. Four principles

1. **Build once, deploy many:** the same artifact/image moves across environments; configuration comes from runtime/deployment.
2. **Least privilege:** each application reads only the secrets and service endpoints it genuinely needs.
3. **Fail closed on required secrets:** missing critical secrets must be caught early rather than silently making unauthenticated HTTP calls.
4. **Traceable provenance and versioning:** know which **image revision + config revision + secret generation** a Pod is running.

Changing a secret does not necessarily require a code change; changing a cache/timeout policy does not necessarily require an image rebuild. Yet both require proper validation and rollback procedures.

## 2. Where does configuration sit on the service-to-service call path?

~~~mermaid
flowchart TD
    A["Application image: Spring Boot + Spring Cloud"] --> B["Spring Environment / Config Data"]
    C["Profile dev/staging/prod"] --> B
    D["ConfigMap / Config Server"] --> B
    E["Secret volume / Secret Manager"] --> F["Credential provider / SSL context"]
    B --> G["HTTP client settings: timeout, retry, SSL bundle refs"]
    B --> H["Discovery + ServiceInstanceListSupplier"]
    B --> I["LB cache/health/zone/algorithm"]
    H --> J["Spring Cloud LoadBalancer selects instance"]
    I --> J
    J --> G
    F --> G
    G --> K["RestClient / WebClient / OpenFeign HTTP request"]
    K --> L["Inventory instance"]
~~~

Key point: **Spring Cloud LoadBalancer only selects a ServiceInstance by service ID**. It does not manage private keys, OAuth2 tokens, passwords, or transport security itself. A call like **http://inventory-service/...** may be rewritten to **http://10.2.0.18:8080/...**; when using HTTPS/mTLS, the HTTP transport must hold trust/key material matching the real hostname and TLS peer identity.

### 2.1. Separating responsibilities by layer

| Layer | What to configure | Who enforces it? |
| --- | --- | --- |
| Spring Boot Config Data | Profiles, files, env vars, configtree imports | Environment / Binder |
| Discovery | Registry endpoint, credentials, namespaces, instance lists | DiscoveryClient / ReactiveDiscoveryClient |
| LoadBalancer | Supplier chain, Round Robin/Random, health, zone, cache TTL | Spring Cloud LoadBalancer |
| HTTP transport | Connect/response/read timeouts, connection pools, TLS | Apache HC5, Reactor Netty, JDK client, etc. |
| HTTP auth | API keys, OAuth2 bearer, mTLS identity | Interceptors/filters/authorized client managers |
| Deployment | ConfigMaps, Secret mounts, RBAC, rollouts/restarts | Kubernetes/CI-CD/secret providers |
| Observability | Request errors, latency, selected instance, config generation | Actuator, Micrometer, tracing, logs |

**Do not mix responsibilities:** setting **spring.cloud.loadbalancer.retry.enabled** does not configure all HTTP transport timeouts; adding **@LoadBalanced** does not guarantee TLS/mTLS is active; and updating a Kubernetes Secret does not automatically make a running RestClient/WebClient/Feign re-read credentials.

## 3. Designing a configuration contract before deployment

A contract table helps dev/ops/security teams agree on where every value originates:

| Key/setting | Purpose | Allowed source | Sensitive? | How changes apply |
| --- | --- | --- | --- | --- |
| spring.application.name | Application identity | application.yml | No | Restart |
| spring.profiles.active | Select environment | Deployment/CLI | No | Restart |
| app.inventory.service-id | Logical target service | Profile/ConfigMap | No | Restart per design |
| spring.cloud.loadbalancer.zone | Caller zone preference | Deployment metadata | No/sensitive per org | Lifecycle dependent |
| spring.cloud.loadbalancer.cache.ttl | Instance list cache | Profile/ConfigMap | No | Usually restart unless tested refresh exists |
| spring.cloud.loadbalancer.retry.* | Retry policy | Profile/ConfigMap | No | Depends on HTTP client/bean lifecycle |
| app.inventory.response-timeout | App-set transport timeout | Profile/ConfigMap | No | Recreate HTTP client when config changes |
| app.inventory.api-key | Inventory API key | Secret volume/Secret Manager | **Yes** | Provider refresh or restart |
| spring.security.oauth2.client.registration...client-secret | OAuth2 client secret | Secret Manager/configtree | **Yes** | Usually requires credential swap/restart |
| spring.ssl.bundle.pem...private-key | mTLS private key | Protected secret file | **Yes** | Consumer-dependent; test or restart |
| SPRING_CONFIG_IMPORT | Required config source | Deployment | No if free of credentials | Startup |

At rollout time, maintain a **config contract version** and **validation schema**: if a deployment lacks a required credential, specifies a wrong service ID, or sets retry counts out of bounds, fail in the pipeline or at startup rather than waiting for production traffic to fail.

### 3.1. Do not use a single "catch-all" environment variable

Anti-pattern example:

~~~text
APP_CONFIG=inventory_url=http://...;password=...;retry=10;tls=false
~~~

Custom monolithic config strings like this are hard to validate, hard to access-control, easy to leak into logs, and prone to inconsistent precedence. Use **@ConfigurationProperties** for ordinary settings and a **secret provider** for credentials. If using SPRING_APPLICATION_JSON, remember it remains an environment variable whose contents can be exposed through operational tools.

## 4. How does Spring Boot prioritize configuration sources?

Spring Boot reads multiple **PropertySources**. There is no simplistic rule like "YAML always wins over env vars" or "profiles always beat command-line flags."

Key rules:

| Source | Example | Typical comparison |
| --- | --- | --- |
| Default properties | SpringApplication defaults | Low precedence |
| Config Data packaged in JAR | application.yml | Baseline |
| Profile-specific Config Data | application-prod.yml | Usually overrides non-profile file at same location |
| Config Data outside JAR | /config/application.yml | Can override packaged config per location group |
| Operating system environment variables | SPRING_PROFILES_ACTIVE | Usually overrides Config Data |
| Java system properties | -D... | Higher precedence than env vars in standard order |
| Command-line arguments | --server.port=... | Higher precedence than file-based config by default |
| SPRING_APPLICATION_JSON | JSON in env/system property | Has its own position in property source order |

The **complete precedence order** also includes test properties, devtools, and other sources; do not rely solely on a condensed table when multiple config groups define the same key. Consult the Spring Boot Reference for the official PropertySource order.

### 4.1. Profile-specific files

Suppose:

~~~yaml
# application.yml — shared configuration, no secrets
spring:
  application:
    name: order-service
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s

app:
  inventory:
    service-id: inventory-service
    response-timeout: 2s
~~~

And:

~~~yaml
# application-prod.yml — only values differing from defaults
app:
  inventory:
    response-timeout: 1s

spring:
  cloud:
    loadbalancer:
      cache:
        ttl: 20s
~~~

When the **prod** profile is active, **app.inventory.response-timeout=1s** and **cache.ttl=20s** in this setup, unless a higher-precedence PropertySource overrides them.

**Never use profiles to hide secrets**: `application-prod.yml` inside source/JAR remains readable by anyone inspecting the artifact. Profiles select **configuration groups**, not encryption or least privilege.

### 4.2. Environment variables and relaxed binding

Spring Boot supports relaxed binding. For example:

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_CLOUD_LOADBALANCER_CACHE_TTL=20s
APP_INVENTORY_RESPONSE_TIMEOUT=1s
~~~

These map to the corresponding properties in standard cases. For hyphenated names, list indices, map keys, or uppercase keys, follow **Binding From Environment Variables** in the Spring Boot Reference rather than inventing a rule that replaces every character with underscores.

### 4.3. Why must you know the final resolved source?

When **application-prod.yml** specifies a 1s timeout yet deployment injects **APP_INVENTORY_RESPONSE_TIMEOUT=5s**, the effective value is **5s**. Debugging merely by reading Git files will mislead you. Inspect effective runtime configuration through **protected and sanitized** diagnostics, never dumping the entire Environment/Secrets to stdout.

## 5. Designing dev, staging, and prod profiles

A system should have a **stable base configuration**, varying only what genuinely depends on the environment:

~~~text
Same JAR / same image digest
  |
  +-- dev:  SimpleDiscoveryClient + localhost backend, fake credentials
  |
  +-- test: MockWebServer/WireMock, deterministic timeouts, no production secrets
  |
  +-- staging: real discovery, TLS and auth mirroring production
  |
  +-- prod: real discovery, secrets from Secret Manager, readiness and alerting
~~~

### 5.1. Dev configuration with SimpleDiscoveryClient

~~~yaml
# application-dev.yml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://127.0.0.1:8091
              - uri: http://127.0.0.1:8092
    loadbalancer:
      retry:
        enabled: false
      cache:
        ttl: 10s

app:
  inventory:
    response-timeout: 3s
~~~

In dev, a static list helps study **Round Robin/Random** and test RestClient, WebClient, and OpenFeign without running Eureka/Consul/Kubernetes discovery.

**Warning:** `127.0.0.1` seen from inside a container/Pod refers to **that container/Pod itself**, not the developer laptop or another Pod. Never copy localhost config verbatim into containerized production environments.

### 5.2. Staging configuration

~~~yaml
# application-staging.yml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 20s
      retry:
        enabled: false

app:
  inventory:
    response-timeout: 2s
~~~

Staging should run with the **same discovery provider/TLS/auth patterns** as production if the goal is deployment verification, differing only in **credentials, namespaces, service endpoints, capacity, and approved config values**.

**Never copy production Secrets into staging** for testing convenience. Use separate credentials, separate scopes, independent rotation, and test data.

### 5.3. Prod configuration

~~~yaml
# application-prod.yml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
      retry:
        enabled: false

app:
  inventory:
    response-timeout: 1500ms
~~~

Values like **35s/1500ms** are illustrative only. A 35-second TTL is a common default in Spring Cloud LoadBalancer docs, not optimal for every system. In production, measure **staleness, registry refresh latency, connection timeouts, retry amplification, and P99** before deciding.

### 5.4. Profiles do not choose the discovery implementation

Setting **spring.profiles.active=prod** alone does not teach Spring Cloud LoadBalancer how to find Pods. An actual discovery source must exist:

- **SimpleDiscoveryClient:** reads instances solely from config.
- **Eureka/Consul:** needs client starters, network/auth, and registration/registry semantics.
- **Spring Cloud Kubernetes DiscoveryClient:** needs the matching Spring Cloud Kubernetes starter/configuration and API permissions if reading Pods/Services.
- **Kubernetes Service DNS:** you can call a Kubernetes Service directly with a plain HTTP client; load balancing then runs at Kubernetes Service/kube-proxy or mesh, **which does not mean Spring Cloud LoadBalancer is picking individual Pods**.

**Do not stack two load-balancing layers blindly:** if a client picks a Pod via Spring Cloud LoadBalancer and then passes through a Service/gateway picking another backend, the logged selected `ServiceInstance` may not match the Pod that handled the request. Pick a deployment model intentionally and verify with traces.

## 6. Putting service IDs and transport settings into a validated type

Instead of scattering **@Value** annotations across classes, use **@ConfigurationProperties** to group non-secret settings:

~~~java
package example.order.config;

import java.time.Duration;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.inventory")
public record InventoryClientSettings(
        @NotBlank String serviceId,
        @NotNull Duration responseTimeout) {
}
~~~

Enable binding:

~~~java
@SpringBootApplication
@EnableConfigurationProperties(InventoryClientSettings.class)
public class OrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

**Dependencies:** the Spring Boot configuration processor is optional for IDE metadata; to enforce **jakarta.validation** constraints at startup, add a Jakarta Bean Validation implementation, usually via **spring-boot-starter-validation** matching your BOM.

When config lacks **app.inventory.service-id** or a Duration fails to parse from a valid string, the app must fail early rather than throwing UnknownHostException or hanging requests in production.

### 6.1. Never place secrets in records logged by default

Java **records** generate **toString()** automatically. If a record holds `apiKey` or `clientSecret`, logging the object leaks the value. Keep **non-secret** parameters in one record and secrets in a dedicated **secret provider**, or implement **toString()/logging** carefully.

Design example:

~~~text
InventoryClientSettings
  serviceId: inventory-service
  responseTimeout: PT1.5S

InventoryCredentialProvider
  getBearerToken(): current token, with expiry/refresh
  getApiKey(): secret, DO NOT log

InventoryTransportFactory
  creates RestClient/WebClient/Feign transport from settings + TLS material
~~~

### 6.2. Cross-validating settings

Validating individual fields in isolation is not enough. For retries/timeouts:

~~~text
connectTimeout     = 500ms
responseTimeout    = 1500ms
retryAttempts      = 3
overallDeadline    = 2s
~~~

If two retries each allow a 1500ms `responseTimeout` plus backoff, **overallDeadline=2s** can cancel the request before all attempts can run. Write tests verifying the **total budget** rather than only checking that properties bind cleanly.

## 7. Config Data imports: external files and configuration trees

Spring Boot supports **spring.config.import** to load configuration outside the JAR, including **file:** and **configtree:**.

### 7.1. A config file mounted outside the JAR

~~~yaml
# application.yml
spring:
  config:
    import: "optional:file:/etc/order/config/overrides.yml"
~~~

If `overrides.yml` exists, its values override the importing document per Config Data precedence. **optional:** means startup continues if the file is absent.

**Do not make everything optional**: if a required secret is missing and the app boots with blank/default settings, that can be a security failure. For critical production secrets, intentionally choose **non-optional imports** plus validation.

### 7.2. Configuration tree from Secret files

Suppose Kubernetes mounts a volume:

~~~text
/etc/order/secrets/
  app.inventory-auth.api-key
  app.inventory-auth.client-secret
~~~

Each **filename** becomes a property key, and file contents become its value. Declare:

~~~yaml
spring:
  config:
    import: "configtree:/etc/order/secrets/"
~~~

After import:

~~~text
app.inventory-auth.api-key       <- contents of file app.inventory-auth.api-key
app.inventory-auth.client-secret <- contents of the other file
~~~

**Never print actual file contents to the console**. Different filenames or nested directories yield different property keys; verify the exact binding contract.

### 7.3. Initializing a fail-closed credential provider

Example startup provider reading a **required** API key from Config Data:

~~~java
package example.order.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;

@Configuration(proxyBeanMethods = false)
class InventoryCredentialConfiguration {

    @Bean
    InventoryApiKeyProvider inventoryApiKeyProvider(
            Environment environment) {
        String key = environment.getProperty(
                "app.inventory-auth.api-key");
        if (key == null || key.isBlank()) {
            throw new IllegalStateException(
                    "Inventory API key is missing");
        }
        return new InventoryApiKeyProvider(key);
    }
}
~~~

Here **InventoryApiKeyProvider** is an application class holding the credential without exposing it via `toString`/logs. This snippet performs **startup validation**; it **does not hot-reload** automatically when volume files change.

If the same artifact runs under a dev profile without an API key, annotate this bean with **@Profile("staging | prod")** or define explicit profile-scoped security modes with validation; never fall back to placeholder strings like `"none"` in production.

## 8. Do not confuse configtree imports with Spring Cloud Config Server

These configuration mechanisms complement each other yet use different sources:

| Mechanism | Source | When appropriate? |
| --- | --- | --- |
| Spring Boot Config Data file | application.yml, external files | Basic config without remote server dependencies |
| configtree: | Volume with one key per file | Kubernetes Secrets/CSI, passwords/API keys, or PEM paths |
| Spring Cloud Config Client | Config Server over HTTP | Centralized management, versions/labels/profiles |
| Spring Cloud Kubernetes PropertySource | Kubernetes ConfigMaps/Secrets via API | When Spring Cloud Kubernetes integration is chosen |
| Vault/Secret Manager SDK or CSI | Secret system | Credentials needing dedicated policies/rotation/auditing |

Do not enable every solution at once. Simultaneously loading Config Server, Kubernetes API, Secret Manager, and multiple local imports for the same key produces confusing precedence, extra credentials to manage, and circular startup dependencies.

## 9. Spring Cloud Config Server: centralizing config without embedding secrets in URLs

When multiple microservices share operational config, Spring Cloud Config Server serves **Config Data by application, profile, and label**. On the client, add the matching starter and configure import:

~~~yaml
# application-prod.yml — used when Spring Cloud Config Client starter is present
spring:
  config:
    import: "configserver:https://config.internal.example"
  cloud:
    config:
      label: release-2026-11
~~~

**Without `optional:`**, the client fails startup if Config Server is unreachable during Config Data loading (per import semantics). If the configuration is strictly non-critical tuning, you may use **optional:configserver:** with appropriate validation, though **never silently fall back to an insecure production config**.

### 9.1. Separating endpoints, credentials, and trust

~~~text
Config Server URL:     https://config.internal.example
Client authorization:  workload identity / mTLS / dedicated credential
TLS trust:             infrastructure CA/truststore
Application config:    service ID, timeouts, cache/health/zone policies
Inventory credential:  still in Secret Manager / Secret volume
~~~

Whenever possible, use **workload identity**, mTLS, or an organization-approved authorization mechanism to access Config Server. **Never embed username/password in the URI** (e.g., `user:password@host`), as URIs easily leak into logs, monitoring, error messages, or deployment diffs.

Config Server helps manage **versioned configuration**, yet does not by itself solve **distribution and rotation of private keys, client secrets, and API keys**. If Config Server also reads Vault, Vault access permissions and credentials must be protected across a separate trust boundary.

### 9.2. Labels and deployment reproducibility

Suppose a deploy uses:

~~~text
image digest = sha256:...
Spring profile = prod
Config Server label = release-2026-11
Secret generation = inventory-key-v7
~~~

A rollback that reverts only the image without reverting the **label/config generation** can create incompatible code–config combinations. Record metadata for every rollout, control who can move labels, and maintain a separate **config revert** procedure if a timeout, zone, or auth setting breaks.

### 9.3. Refresh does not automatically apply to every bean

Spring Cloud provides **EnvironmentChangeEvent**, **@RefreshScope**, and `/actuator/refresh` in supported environments. However:

- An already-built **RestClient/WebClient/Feign instance** holding its request factory, SSLContext, and pool does not automatically rebuild on refresh.
- Constructor-bound/record `@ConfigurationProperties` have refresh limitations depending on bean management.
- Beans that copied values into fields do not update when a new property source arrives.
- Spring Cloud Context refresh has limitations under **AOT/native image** modes.

Unless you have tested the exact **rebind → swap HTTP client/credential → drain old connections** path, prefer a **rolling restart**. Never expose `/actuator/refresh` openly to public traffic.

## 10. Kubernetes ConfigMap: non-sensitive configuration

In Kubernetes, a ConfigMap can supply **environment variables** or mounted files for non-secret parameters.

Example:

~~~yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-service-settings
  namespace: orders
data:
  SPRING_PROFILES_ACTIVE: "prod"
  APP_INVENTORY_RESPONSE_TIMEOUT: "1500ms"
  SPRING_CLOUD_LOADBALANCER_CACHE_TTL: "35s"
  SPRING_CONFIG_IMPORT: "configtree:/etc/order/secrets/"
~~~

Notes:

- **SPRING_PROFILES_ACTIVE=prod** activates the profile config.
- **APP_INVENTORY_RESPONSE_TIMEOUT** can override profile files per property source precedence.
- **SPRING_CLOUD_LOADBALANCER_CACHE_TTL** adjusts LB cache TTL, not HTTP connection pool lifetimes.
- **SPRING_CONFIG_IMPORT** here requires the Secret directory to exist. If mounted wrongly, startup fails rather than running without credentials.

**Put only non-sensitive values in ConfigMaps.** Never put API keys, private keys, OAuth2 client secrets, or passwords in a ConfigMap just because it can be mounted as a file.

### 10.1. Env-based ConfigMaps do not automatically update a running JVM

When a ConfigMap is injected via **envFrom**, environment variables are captured at container start. Updating the ConfigMap **does not replace environment variables inside a running process**.

Thus, after changing **APP_INVENTORY_RESPONSE_TIMEOUT**, updating the Kubernetes ConfigMap object alone is **not enough** to make RestClient use the new timeout. You need:

1. A rolling restart to start new Pods with updated env vars; **or**
2. A tested ConfigMap volume/file watcher and bean/HTTP-client refresh pipeline.

For infrequently changing configs, a **rolling restart with readiness gates** is usually easier to reason about than hot-reloading the entire object graph.

## 11. Kubernetes Secrets: created by security tooling, mounted as files

For example, a Secret containing the Inventory API key is provisioned through a **Secret Manager or secure CI/CD**. For local experiments, you can create a Secret from a local file:

~~~bash
kubectl -n orders create secret generic inventory-auth \
  --from-file=app.inventory-auth.api-key=./secrets/inventory-api-key
~~~

**Never commit real files in `secrets/` to Git** and never pass secret values directly as CLI arguments. The command above is an operational illustration; production should use external-secrets/CSI or credential tooling with auditing, rotation, and least privilege.

If your organization manages Secrets via GitOps manifests, use **encryption/sealed/external secret references** per policy; never commit a Kubernetes Secret with Base64 **data** and treat that as encryption.

### 11.1. Sample Deployment for Order Service

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: order-service
  namespace: orders
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0
      maxSurge: 1
  selector:
    matchLabels:
      app: order-service
  template:
    metadata:
      labels:
        app: order-service
    spec:
      securityContext:
        runAsNonRoot: true
        fsGroup: 2000
      containers:
        - name: order
          image: registry.example.internal/order-service@sha256:REPLACE_DIGEST
          ports:
            - containerPort: 8080
          envFrom:
            - configMapRef:
                name: order-service-settings
          volumeMounts:
            - name: inventory-credentials
              mountPath: /etc/order/secrets
              readOnly: true
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: 8080
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: 8080
            periodSeconds: 10
      volumes:
        - name: inventory-credentials
          secret:
            secretName: inventory-auth
            defaultMode: 0440
~~~

**Items to adjust before production:**

- The **image digest** above is a placeholder; replace with a real digest.
- **Namespace `orders`**, `securityContext`, `fsGroup`, file permissions, and `ServiceAccount` must match your cluster. Mode `0440` with group permissions is readable only if volume ownership/group and Pod `securityContext` align.
- Probe endpoints **/actuator/health/readiness** and **/actuator/health/liveness** must be supported and exposed by Spring Boot/Actuator in your environment. Otherwise Pods will never become ready.
- Configure a dedicated workload identity/ServiceAccount if accessing the Kubernetes API or Secret Manager; never grant `cluster-admin`.
- The Deployment above **does not** enable per-Pod service discovery. If using Spring Cloud Kubernetes DiscoveryClient, add the starter and required RBAC; if calling through Kubernetes Service DNS, design the client accordingly.

### 11.2. How do Secret mounts update?

Kubernetes updates Secret volumes with **eventual consistency**. Per Kubernetes docs, latency includes kubelet sync periods and watch/cache propagation.

Important:

- **Secrets mounted via `subPath` do not automatically update** when the Secret changes.
- **Secrets injected via env vars** keep old values until the container restarts.
- **File volume updates** do not automatically update an API key String, `SSLContext`, or Feign `RequestInterceptor` that cached the old value.

Never attach a file watcher to a private key and consider rotation complete merely because the filesystem shows a new file. Verify that the **new credential generation is actually sent on new requests and accepted downstream**.

### 11.3. Secret access permissions and RBAC

Distinguish minimal permissions:

~~~text
Kubernetes RBAC GET/LIST/WATCH Secrets:
  grant only when the app genuinely reads Secrets via the API

Pod Secret volume:
  kubelet mounts into the declared container
  no need to grant namespace-wide API LIST Secrets to the app

Secret Manager:
  workload identity reads only authorized paths/versions

CI/CD:
  authorized to create/update references or secrets per pipeline
  must never print plaintext into logs/artifacts
~~~

Kubernetes Secrets are not encrypted at rest by default in every cluster unless configured by administrators; verify **encryption at rest**, admission controls, audit logging, and RBAC. Private key protection cannot rely solely on a file sitting in a namespace.

## 12. Spring Cloud Kubernetes and Kubernetes Service DNS are not the same thing

This deployment decision directly governs Spring Cloud LoadBalancer:

| Model | Address caller uses | Who picks backend? | What to verify |
| --- | --- | --- | --- |
| **Kubernetes Service DNS** | http://inventory-service.namespace.svc.cluster.local | Kubernetes Service/network dataplane or service mesh | Routing and TLS at Service/mesh |
| **Spring Cloud Kubernetes DiscoveryClient** | http://inventory-service with `@LoadBalanced` client | Spring Cloud LoadBalancer picks from discovery-provided `ServiceInstance`s | Starter, RBAC, instance metadata, HTTP scheme |
| **Eureka/Consul** | http://inventory-service with `@LoadBalanced` client | Spring Cloud LoadBalancer from registry entries | Registry credentials, metadata, health/TTL |
| **Static SimpleDiscoveryClient** | http://inventory-service with `@LoadBalanced` client | Spring Cloud LoadBalancer from static URIs | Suitable only for fixed/test setups |

If you only want to call a **Kubernetes Service** load-balanced by the cluster, Spring Cloud LoadBalancer **does not necessarily need** to pick individual Pods. Yet if requirements call for zone preferences, hint routing, or custom client policies, pick a discovery integration supplying the right instances and metadata.

### 12.1. Using the Kubernetes API as a property source

Spring Cloud Kubernetes supports:

~~~yaml
spring:
  config:
    import: "kubernetes:"
~~~

With a compatible **Spring Cloud Kubernetes Config starter**, this loads ConfigMaps/Secrets matching **spring.application.name** and namespace. It does not activate automatically just because an app runs in a Pod; the starter, config, and API permissions must all be present.

If you only need mounted Secret files, Spring Boot's **configtree:** already suffices and **avoids** granting the app GET/LIST Kubernetes Secrets permissions over the API.

**Do not mix legacy bootstrap with `spring.config.import` for the same source** if the implementation does not support both together. Spring Cloud Kubernetes documents PropertySource precedence when combining Config Server and Kubernetes; establish the exact order before defining the same key in both.

## 13. Per-environment Spring Cloud LoadBalancer settings

For a caller using service ID **inventory-service**, settings to evaluate per environment typically include:

~~~yaml
spring:
  cloud:
    loadbalancer:
      enabled: true
      cache:
        enabled: true
        ttl: 35s
      retry:
        enabled: false
      eager-load:
        clients:
          - inventory-service
      zone: zone-a
~~~

These are illustrative properties; **zone-a** must come from the caller's actual placement metadata rather than hardcoding one zone for all Pods across multiple Availability Zones.

### 13.1. Cache TTL and discovery sources

Spring Cloud LoadBalancer includes **CachingServiceInstanceListSupplier** depending on configuration, and caching is typically enabled by default (docs describe 35s TTL, capacity 256).

However, a DiscoveryClient such as Eureka may **already cache the instance list**. With two cache tiers:

~~~text
Registry snapshot/cache
       |
       v
Spring Cloud LB cache
       |
       v
ServiceInstanceListSupplier -> LoadBalancer choose()
~~~

scaling in an instance may not be seen by every caller immediately. A low TTL does not mean "zero stale requests," because registry propagation and connection pools remain. Never slash TTL blindly to fix an incident; it can spike registry queries and CPU load.

**When choosing TTL**, measure: Pod restarts, scale-out, scale-in, unhealthy instances, registry/network partitions, and new connection rates.

### 13.2. Health checks need a supplier, not just a property

Example:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
        interval: 25s
~~~

These properties set the health check **path and schedule**, yet **do not automatically wire `HealthCheckServiceInstanceListSupplier` in every app**. Register the proper supplier chain for blocking/reactive discovery per the Spring Cloud reference.

Furthermore, health checks must align with endpoints and security:

- If the endpoint requires a token or mTLS, the health-check client must be configured accordingly.
- An HTTP 200 probe does not guarantee every business endpoint is healthy.
- Never use an expensive protected business endpoint as a continuous heartbeat.
- If the registry already provides reliable health status, evaluate whether an extra health-check supplier is even necessary.

### 13.3. Zone preference and metadata

~~~yaml
spring:
  cloud:
    loadbalancer:
      zone: zone-a
~~~

This sets the **caller's zone**, while backend zones must appear in **metadata or the zone-mapping mechanism** used by the supplier. Setting zone on the caller alone creates no zone metadata on providers.

`ZonePreferenceServiceInstanceListSupplier` typically **prefers same-zone replicas** yet falls back when no same-zone candidates exist; it is not an absolute security/compliance geofence. If data must never leave a region, enforce **network policies, deployment policies, admission guards, and backend authorization**.

### 13.4. Retries differ across HTTP clients

Illustrative configuration:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
~~~

**Never enable retries blindly in production**:

- Blocking `RestTemplate` has classpath/integration requirements such as Spring Retry.
- `WebClient` has its own reactive retry/filter mechanisms.
- `RestClient` behavior depends on the Spring Cloud release train/request factory.
- Spring Cloud OpenFeign has its own Retryer, defaulting to **Retryer.NEVER_RETRY** in many integrated versions.
- Gateways, meshes, or proxies may also retry outside the JVM.

A single logical request can generate many HTTP attempts when multiple layers are active simultaneously. For order-creation/stock-reservation POSTs, enforce an **idempotency key** before retrying transport errors or ambiguous timeouts.

### 13.5. Eager-load is not preconnect

**spring.cloud.loadbalancer.eager-load.clients** eagerly initializes child `ApplicationContext`s for the listed service IDs. It **does not pre-open TCP/TLS connections to every `ServiceInstance`**; connection warm-up depends on the HTTP engine and real requests.

Include only critical service IDs to avoid inflating startup time and memory unnecessarily. If an aggregator app calls 30 downstreams, measure readiness latency impact before eager-loading all 30 contexts at startup.

## 14. Separating LoadBalancer settings from HTTP client transport

A clean mental model:

~~~text
LoadBalancer policy:
  Choose A or B from eligible list

HTTP transport:
  DNS / TCP connect / TLS / connection pool
  response timeout / pool acquire timeout

HTTP application:
  Bearer token / API key / headers / request body

Resilience:
  retry / circuit breaker / fallback / overall deadline
~~~

Setting **spring.cloud.loadbalancer.cache.ttl=10s** **does not change HTTP connect timeouts**; similarly, increasing Feign `readTimeout` does not refresh discovery any faster.

### 14.1. Configuration table by client

| Client | Where service ID is configured | Where transport timeout is configured | Where credentials are attached |
| --- | --- | --- | --- |
| RestClient | `@LoadBalanced RestClient.Builder` + logical URI | `ClientHttpRequestFactory`/HTTP engine | `ClientHttpRequestInterceptor` or OAuth2 client integration |
| RestTemplate | `@LoadBalanced RestTemplate` | `ClientHttpRequestFactory`/HTTP engine | Interceptor or OAuth2 integration |
| WebClient | `@LoadBalanced WebClient.Builder` + logical URI | Reactor Netty `HttpClient`/`ClientHttpConnector` | `ExchangeFilterFunction`/OAuth2 filter |
| OpenFeign | `@FeignClient(name=...)` | Named-client `connectTimeout`/`readTimeout` and underlying engine | Per-client `RequestInterceptor`/OAuth2 integration |

**No single Spring Cloud LoadBalancer property** sets connect/read/response/pool timeouts across all four clients.

## 15. RestClient: configuring by service ID without hardcoding credentials

Example creating a `RestClient` from a LoadBalancer-annotated builder:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder,
            InventoryClientSettings settings,
            InventoryTokenProvider tokens) {

        return builder
                .baseUrl("https://" + settings.serviceId())
                .requestInterceptor((request, body, execution) -> {
                    request.getHeaders().setBearerAuth(
                            tokens.currentValidToken());
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Here **InventoryTokenProvider** is an application-supplied abstraction; it must fetch a valid access token, avoid refresh storms, and never log tokens. For standard OAuth2, prefer Spring Security's **OAuth2AuthorizedClientManager/RestClient OAuth2 interceptor** over rolling your own token management.

**Constraints:**

- HTTPS with a service ID requires certificates/SNI/hostname verification matching the **physical URI after LoadBalancer rewriting**.
- An `Authorization`-attaching interceptor should be scoped to a **dedicated Inventory client**, never shared across Payment or Catalog clients.
- `RestClient.Builder` may need Spring Boot customizers to preserve observations, codecs, TLS, and request factories; do not discard Boot's auto-configuration when defining beans manually.
- **responseTimeout** in `InventoryClientSettings` is not yet wired in the snippet; production must apply it to a suitable **ClientHttpRequestFactory/underlying transport**. Do not consider the snippet complete timeout configuration.

### 15.1. When using RestClientSsl

Spring Boot provides **RestClientSsl** in versions supporting SSL bundles, applied when **building the client**:

~~~java
RestClient client = builder
        .apply(ssl.fromBundle("inventory-client"))
        .baseUrl("https://inventory-service")
        .build();
~~~

Here **ssl** is `RestClientSsl` injected by Spring Boot, **builder** is `@LoadBalanced` when using a service ID, and **inventory-client** is a separately configured bundle. This applies TLS config at client creation time; it **does not automatically hot-reload the `SSLContext` inside outbound connection pools**.

## 16. WebClient: response timeouts, connection pools, and credentials

Reactor Netty configures the HTTP transport:

~~~java
@Bean
HttpClient inventoryHttpClient() {
    return HttpClient.create()
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
            .responseTimeout(Duration.ofSeconds(2));
}

@Bean
@LoadBalanced
WebClient.Builder loadBalancedWebClientBuilder(
        HttpClient inventoryHttpClient) {
    return WebClient.builder().clientConnector(
            new ReactorClientHttpConnector(inventoryHttpClient));
}
~~~

**This is a technical pattern** using classes from Reactor Netty, Netty, and Spring WebFlux/Spring Cloud. Real projects should preserve Spring Boot's `WebClientCustomizer`, codecs, observations, and security filters. To tune pool acquisition/concurrency, inspect **ConnectionProvider** and HTTP client config separately; `responseTimeout` does not replace an overall deadline.

When attaching OAuth2 tokens to `WebClient`, use **ReactiveOAuth2AuthorizedClientManager** with the matching Spring Security filter. Never perform blocking Secret Manager reads or token exchanges on the Netty event loop.

**Never apply Spring Cloud LoadBalancer twice**: an already `@LoadBalanced` `WebClient.Builder` should not also have `ReactorLoadBalancerExchangeFilterFunction` added manually a second time unless the pipeline is intentionally designed and tested for it.

### 16.1. WebClient publishers can be subscribed to multiple times

~~~text
Mono created at T0
Actual HTTP request starts at subscribe T1
retryWhen may subscribe a second time at T2
~~~

If a secret/token is captured prematurely into headers at T0, executions at T1/T2 may send an expired credential. The token provider/filter should resolve credentials at execution time with proper caching and bounded attempt counts.

## 17. OpenFeign: named-client configuration and secrets

Example Feign declaration by service ID:

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

Named-client timeouts:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          inventory-service:
            connectTimeout: 500
            readTimeout: 1500
            loggerLevel: basic
~~~

Feign timeouts in the example are in **milliseconds** per current Feign API/config. They are not Spring Cloud LoadBalancer TTLs, and do not always equal total end-to-end deadlines once DNS, proxies, retries, and pool acquisition are included.

### 17.1. Fixed Feign URLs can bypass LoadBalancer

If configured with **@FeignClient(name="inventory-service", url="https://some-host")** or a named-client `url` property, Feign calls that address directly instead of selecting a `ServiceInstance`. When client-side selection is required, rely on **name/service ID** and avoid accidentally overriding `url` in any environment.

### 17.2. Never leak credentials via a global RequestInterceptor

A `RequestInterceptor` for Inventory must be scoped **exclusively to that Feign named client**, never accidentally component-scanned into a global bean. If a global interceptor attaches Inventory's API key to all Feign clients, tokens can leak to Payment or Catalog.

In mTLS environments, **Apache HC5/OkHttp or the underlying Feign client** owns the `SSLContext` and connection pool, not `@FeignClient` itself. When connection secrets rotate, verify the underlying transport adopts the new material.

## 18. TLS/mTLS: configuring truststores, client certificates, and hostnames

TLS protects the transport channel and authenticates the server. With **mTLS**, the client also presents a **client certificate** so the server verifies the caller workload's identity.

Example Spring Boot **PEM SSL bundle** configuring trust and key material:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        inventory-client:
          truststore:
            certificate: "file:/etc/order/tls/inventory-ca.pem"
          keystore:
            certificate: "file:/etc/order/tls/order-client.crt"
            private-key: "file:/etc/order/tls/order-client.key"
~~~

These files are delivered by a **Secret volume/CSI/PKI**, never packaged in the JAR. Configure only `truststore` for **server TLS** without client certificates; add `keystore`/client keys when downstream requires mTLS.

**Verify version compatibility:** SSL bundles configure TLS material for Spring Boot–supported consumers; the HTTP connector behind **RestClient/WebClient/Feign** must actually apply the bundle. Never assume Feign automatically picks up client certificates just because a bundle name appears in YAML.

### 18.1. TLS identity after LoadBalancer chooses an instance

Suppose:

~~~text
Logical URI: https://inventory-service/stock
Selected ServiceInstance: inventory-b.internal:8443
Physical URI: https://inventory-b.internal:8443/stock
~~~

The server certificate must be valid for the **hostname verified by the HTTP client**, including matching SANs. Issuing a certificate with only DNS SAN `inventory-service` **may fail** if the HTTP connector verifies `inventory-b.internal` or a direct IP.

Never "fix" this by:

- disabling hostname verification;
- installing a trust-all `TrustManager`;
- disabling certificate chain validation;
- forging an arbitrary HTTP `Host` header to pretend TLS identity changed.

Align **discovery addresses, DNS, certificate SANs, SNI, and proxy/mesh topology**. If a mesh sidecar terminates TLS, establish whether **the mesh or Java** owns certificates and verification policy.

### 18.2. When do SSL bundles hot-reload?

Spring Boot supports **reload-on-update** for certain SSL bundle consumers. Current docs explicitly highlight **Tomcat web server** and **Netty web server**:

~~~yaml
spring:
  ssl:
    bundle:
      pem:
        webserver:
          reload-on-update: true
          keystore:
            certificate: "file:/etc/tls/server.crt"
            private-key: "file:/etc/tls/server.key"
server:
  ssl:
    bundle: webserver
~~~

This applies to **inbound web server TLS**, **not** a guarantee that **outbound RestClient, WebClient, and Feign** automatically reload their `SSLContext`/connection pools when files change.

### 18.3. Relationship between TLS rotation and connection pools

~~~text
N:   Old TLS context/connection pool
       |
       +-- open connections carry old TLS sessions

N+1: Secret volume receives new cert/key
       |
       +-- HTTP engine must use new TLS material for new handshakes
       +-- Old pool may still retain old sockets/SSLContext
~~~

If the transport does not support tested dynamic reloading, choose a **rolling restart** or **create a new HTTP client/pool generation and drain the old generation**. Never tear down the old pool instantly while HTTP requests are in flight; conversely, never keep trusting a compromised key solely to preserve availability.

## 19. OAuth2 client_credentials: never confuse client secrets with access tokens

An Order Service using OAuth2 client credentials to call Inventory may configure:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: internal-idp
            client-id: order-inventory
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          internal-idp:
            token-uri: https://identity.internal.example/oauth2/token
~~~

**There is no `client-secret` in this YAML.** The corresponding secret property is:

~~~text
spring.security.oauth2.client.registration.inventory.client-secret
~~~

It must be supplied via a **secret provider or configtree file** when client authentication uses a client secret. If your organization uses `private_key_jwt` or mTLS client authentication, token client setup differs and should be verified against your Identity Provider.

### 19.1. Two separate lifecycles

| Component | Lifecycle | How it changes |
| --- | --- | --- |
| **Access token** | Usually short-lived | `OAuth2AuthorizedClientManager` fetches a fresh token when needed |
| **OAuth2 client secret** | Issued/revoked per Identity Provider policy | Update `ClientRegistration`/credential provider or restart |
| **OAuth2 signing key/JWKS** | Rotated by issuer | Issuer publishes new public key before signing tokens; resource servers refresh verifiers |
| **TLS client certificate** | Cert/key validity window | Swap `SSLContext`/HTTP transport or restart |

Spring Security offers **OAuth2AuthorizedClientManager** for `RestClient` and **ReactiveOAuth2AuthorizedClientManager** for `WebClient`. Never cache an access token forever in a field or call the Token Endpoint on every single request.

### 19.2. Right audience and scopes on tokens

Even when the TLS handshake succeeds, Inventory can still return:

~~~text
401 Unauthorized: missing/expired token, or wrong issuer/audience
403 Forbidden: valid token lacking required scope/permission
~~~

**Never blindly retry 401/403 via LoadBalancer**. If a token expired, the token manager can refresh it with bounded retries per contract; if scopes are wrong, fix authorization. Never send Inventory's Bearer token to another host/Feign client via a global interceptor or uncontrolled redirect.

## 20. Rotating connection secrets while the application runs

A standard rotation workflow requires **both sides**:

~~~mermaid
flowchart TD
    A["Secret Manager/PKI issues generation N+1"] --> B["Receiver accepts new key/cert"]
    B --> C["Distribute secret generation N+1"]
    C --> D["Caller reads and validates new material"]
    D --> E{"Can HTTP client adopt N+1?"}
    E -->|No| F["Rolling restart or build new client/pool"]
    E -->|Yes| G["Publish new generation for new requests"]
    F --> G
    G --> H["Canary HTTPS + auth via service ID"]
    H --> I{"Canary OK?"}
    I -->|No| J["Halt rollout; roll back if old credential is safe"]
    I -->|Yes| K["Drain generation N and revoke old on schedule"]
~~~

### 20.1. Do not treat a file update as completed rotation

Separate states:

~~~text
Secret Manager:          generation 12
Kubernetes Secret:       generation 12
Mounted volume:          generation 12
Spring Environment:      may still be generation 11
HTTP client interceptor: may still be generation 11
TLS connection pool:     may still hold generation 11 TLS sessions
Backend accepts:         generations 11 and 12
~~~

A filesystem update only proves propagation to the **mounted volume**. Verify that **new requests actually carry credential generation 12** and downstream accepts it.

### 20.2. API keys can update per request via a provider

If an interceptor/filter reads **CurrentCredentialProvider** at request execution time, an API key can rotate without rebuilding TCP pools, provided the backend already accepts the new key.

Conversely, if `RestClient`/Feign captures the **API key in its constructor** or a static `defaultHeader`, updating a Secret file does not change the sent header. You must safely reload the bean/credential provider or perform a rolling restart. Never log keys before or after to "prove they changed."

### 20.3. Two-phase CA rotation for mTLS

Typically:

1. **Expand trust:** both client and server trust `CA-old` and `CA-new` where policy permits.
2. **Migrate:** roll out new certificates gradually, verifying each instance and pool.
3. **Contract:** remove `CA-old` once all callers/backends have migrated and revocation conditions are met.

If a private key is compromised, follow **incident response** and revoke immediately rather than extending overlap for deployment convenience.

### 20.4. Rolling restarts with Secret env vars

When credentials are injected via environment variables or the transport does not support dynamic TLS updates:

~~~bash
kubectl -n orders rollout restart deployment/order-service
kubectl -n orders rollout status deployment/order-service
~~~

These commands are operational examples, **not executed in this lesson**. Ensure sufficient replicas, suitable rolling strategies, and readiness probes; with a single replica, restarts can cause downtime.

With Helm/GitOps, update a **Pod template annotation with a controlled config/secret generation or checksum**, triggering the Deployment to roll new Pods in a versioned way. Never place plaintext secrets in annotations or labels.

## 21. Configuring timeouts/retries so credential failures do not trigger retry storms

A defensive policy can be expressed as:

~~~text
Connect timeout:       500 ms
Response timeout:      1500 ms
Maximum HTTP attempts: 2 (only idempotent GETs and permitted errors)
Overall deadline:      2500 ms
Circuit breaker:       per operation
Fallback:              degraded/unknown, never fake success
~~~

These numbers are **illustrative**; tune against real latency plus discovery/TLS/circuit-breaker overhead. HTTP engine timeouts may start at a different point than the **overall deadline**.

### 21.1. Should-we-retry matrix

| Failure | Retry? | Reason |
| --- | --- | --- |
| Connection refused after instance terminated | Possibly, bounded attempts | Retrying another instance can recover |
| Backend HTTP 503 | Possibly, with backoff | Avoid overloading the backend |
| Response read timeout on GET | Possibly, per idempotency | Ensure the HTTP request is safe to replay |
| HTTP 401 expired access token | Via dedicated OAuth2 token refresh | Never blindly retry with the same stale token |
| HTTP 403 insufficient scope | Usually no | Retrying grants no extra permissions |
| `SSLHandshakeException` due to wrong trust/SAN | Never blindly retry | Fix TLS policy/certificate |
| No `ServiceInstance` | Per explicit discovery/retry budget | Do not assume the registry refills immediately |
| HTTP 400/422 invalid input | No | Usually a contract/client bug |
| Order POST timed out after send | Only with idempotency/dedup | Backend may have already committed |

**Enabling multiple retry layers** (LoadBalancer, Reactor, Feign, gateway, service mesh) multiplies HTTP attempts. Environment configuration management must also explicitly assign **which layer owns retries**, rather than setting `maxRetries` everywhere.

## 22. Readiness/liveness do not mean checking every downstream

A Pod may have a **running process** yet should not receive traffic because config is missing, secrets are not mounted, HTTP clients failed to initialize, or service discovery has no valid source. That is a **readiness** issue, not necessarily liveness.

Example enabling health probes in Spring Boot when needed:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: "health,info"
~~~

**Liveness** should reflect whether the process itself can keep running; it should not automatically go DOWN just because Inventory temporarily returns 503. Turning a downstream fault into a liveness failure causes Kubernetes to mass-restart Order Pods, creating cascades.

**Readiness** can refuse traffic until **required credentials/config** are loaded. However, do not blindly wire every supporting downstream into readiness: if Inventory fails briefly while Order can still serve other APIs, degrade the dependent feature or apply contract-safe fallbacks instead of pulling the entire Pod out of service.

### 22.1. Startup gate for secrets

Reasonable flow:

~~~text
Pod starts
  |
  v
Mount Secret volume / inject env vars
  |
  v
Spring Boot Config Data import + binding + validation
  |
  v
Build HTTP clients, TLS/auth providers
  |
  v
Readiness = accepting traffic
  |
  v
Caller sends requests by service ID
~~~

If a required **configtree:** is missing, failing startup early is the right signal. If Secret Manager is temporarily unavailable, choosing **fail-fast, bounded startup retries, or degraded mode** belongs in deployment policy aligned with service functionality.

### 22.2. Preventing circular dependencies during rollouts

Never make Order readiness require Inventory to be ready while Inventory readiness requires Order to be ready. Circular dependencies can keep both out of endpoints forever. Assess each service's own serving ability independently and use timeouts/fallbacks for downstream calls.

## 23. Observing runtime config without exposing secrets

Spring Boot Actuator provides **env**, **configprops**, **health**, **info**, and **metrics**. Per Spring Boot docs, values in `env`/`configprops` are sanitized by default, yet **never treat sanitization as a substitute for network access control**.

### 23.1. Operational metadata safe to expose under control

~~~text
application:           order-service
image digest:          sha256:...
active profile:        prod
config revision:       release-2026-11
credential generation: inventory-key-v7  (non-secret ID)
service ID:            inventory-service
discovery provider:    kubernetes/eureka/consul
loadbalancer policy:   round-robin
retry policy:          enabled=false
health policy:         named supplier chain
~~~

Never expose:

~~~text
Bearer tokens
OAuth2 client secrets
API keys
Private key PEMs
Truststore passwords
Full Config Server auth URLs containing credentials
Database passwords
Kubernetes Secret data
~~~

### 23.2. Suggested metrics

| Metric | Purpose |
| --- | --- |
| config_revision / deployment_info | Identify which config revision a Pod runs |
| credential_generation_age | Track how old active secrets are |
| credential_expiry_seconds | Alert before tokens/certificates expire |
| lb_no_instance_requests | Detect discovery/supplier returning zero replicas |
| lb_requests_success/failed | Health of LoadBalancer-routed calls |
| outbound_http_duration | P50/P95/P99 per service/operation |
| outbound_connect_timeout | Distinguish network faults from auth errors |
| outbound_tls_handshake_failures | Catch CA/SAN/mTLS mismatches |
| outbound_http_401_403 | Detect client secret/scope/policy mismatches |
| outbound_retry_attempts | Control retry amplification |
| refresh_or_rotation_failures | Alert on config/credential update failures |

These are **suggested metric group names**, not default Spring Cloud/Micrometer meter names. In Spring Cloud LoadBalancer, statistics meters exist only when lifecycle metrics integration is configured. Do not copy illustrative names into SLO queries before checking your actual registry.

### 23.3. Tracing with selected instance

A safe trace may record:

~~~text
logical service id: inventory-service
selected instance: inventory-b  (when cardinality/permissions permit)
selected zone: zone-a
http method: GET
uri template: /api/stock/{sku}
outcome: HTTP 200
client credential generation: 7
~~~

Never put SKUs, order IDs, tokens, raw URLs with sensitive query strings, or session IDs into unbounded-cardinality metric tags. When instance IDs are needed, prefer access-controlled sampled traces/logs.

## 24. Deployment pipeline: verifying before admitting traffic

A CI/CD or GitOps workflow may include:

~~~mermaid
flowchart TD
    A["Code + configuration review"] --> B["Secret scanning + policy validation"]
    B --> C["Build image + SBOM + image digest"]
    C --> D["Static YAML/Helm/Kustomize validation"]
    D --> E["Deploy test profile with fake credentials"]
    E --> F["Integration tests: service discovery + auth + TLS"]
    F --> G["Staging canary"]
    G --> H{"SLO + security checks pass?"}
    H -->|No| I["Rollback config/image/credential refs"]
    H -->|Yes| J["Prod rolling rollout/canary"]
    J --> K["Post-deploy smoke + observability"]
~~~

### 24.1. Pre-build checks

- Zero plaintext secrets in source, YAML, logged CI variables, Dockerfiles, or build caches.
- `application.yml` does not hardcode production instance IPs or credentials.
- Property keys are spelled accurately, with no typos like **spring.cloud.loadbalancer.cache.tll**.
- Timeout/TTL values parse cleanly and are non-negative and sensible.
- The `prod` profile does not unintentionally disable TLS validation, auth, or health checks.
- Spring Boot/Spring Cloud/Spring Security BOM dependencies are compatible.

### 24.2. Pre-deploy checks

- ConfigMap and Secret references point to the right namespace/name/key.
- ServiceAccount holds minimal permissions; never grant cluster-wide Secrets `list` unnecessarily.
- Secret volume mount file permissions match process UID/GID.
- **SPRING_CONFIG_IMPORT** points to the valid path inside the Pod.
- TLS certificate SANs match physical hostnames/client routes.
- Registry/DiscoveryClient and service IDs are valid, with no `localhost` leaked from `dev` profile.
- Resource limits and pool settings fit concurrency and latency SLOs.

### 24.3. Post-deploy checks

- Pod readiness stabilizes, with no `CrashLoopBackOff` from missing secrets.
- A safe endpoint succeeds via service ID, confirming which instance handled the call.
- Negative-path check: 401/403 is not masked as a fake HTTP 200.
- Count HTTP attempts under failure to confirm no retry storm.
- Verify non-sensitive config revision and credential generation metadata.
- Watch P95/P99, 503/no-instance, TLS, token renewal, and connection pools.

### 24.4. Same image with different config still requires testing

If the image version stays identical and only a ConfigMap changes timeout from 1s to 5s, that is still a **new behavioral release**. It needs a changelog, owner, environment scope, and rollback plan. Never assume "it is just a YAML edit, no testing needed."

## 25. Testing configuration with Spring Boot Test

A simple test can verify the **dev profile** binds properly:

~~~java
@SpringBootTest
@ActiveProfiles("dev")
class InventorySettingsDevTest {

    @Autowired
    InventoryClientSettings settings;

    @Test
    void resolvesDevSettings() {
        assertEquals("inventory-service", settings.serviceId());
        assertEquals(Duration.ofSeconds(3),
                settings.responseTimeout());
    }
}
~~~

This runs only when the real test project includes **application-dev.yml** as in section 5 and registers **InventoryClientSettings**. Imports come from Spring Boot Test, Spring Test, JUnit 5, and `java.time.Duration`.

### 25.1. Testing startup failure when secrets are missing

In an integration test, construct an `ApplicationContext`/test profile loading only credential config **without placing the required key in `Environment`**, and verify:

~~~text
No app.inventory-auth.api-key
       |
       v
Credential bean initialization fails
       |
       v
Application not ready
~~~

Never write unit tests that print real secret contents in assertion failure messages. Use fake keys in isolated test environments; never run tests against production Secret Manager.

### 25.2. Testing precedence

Create a test with:

~~~text
application.yml:      response-timeout=2s
application-dev.yml:  response-timeout=3s
test env/override:    response-timeout=500ms
~~~

Verify the **final effective value** matches Spring Boot `PropertySource` ordering. When using **@TestPropertySource**, **DynamicPropertySource**, or command-line overrides, remember those test utilities themselves introduce PropertySources with higher precedence than runtime config.

### 25.3. Testing discovery and real routing

Simulate two Inventory backends with **MockWebServer/WireMock**, supply their list via `SimpleDiscoveryClient`, and call by service ID using a **load-balanced RestClient/WebClient/Feign**. Assert:

~~~text
logical URI = http://inventory-service/whoami
selected instance belongs to [A, B]
backend receives exactly expected attempts
Authorization header only sent to allowed downstream
no secret appears in HTTP client logs
~~~

Never mock **DiscoveryClient** alone and conclude the HTTP transport handles TLS and tokens properly; write dedicated integration tests for truststores, mTLS, OAuth2 token endpoints, certificate rotation, and server responses.

### 25.4. Testing runtime secret rotation

Create two generations of fake credentials:

~~~text
generation N   -> backend accepts key-old
generation N+1 -> backend accepts key-new
~~~

Procedure:

1. Caller sends requests with `key-old`, receiving 200.
2. Backend opens an overlap window accepting both `key-old` and `key-new`.
3. Secret provider switches to `key-new` or Pods undergo rolling restart.
4. New requests send `key-new` and receive 200.
5. Backend revokes `key-old`.
6. New requests still succeed, with zero requests using `key-old`.

For mTLS, verify with a **fresh TLS handshake** to each instance, not solely HTTP requests over an existing keep-alive connection.

## 26. Troubleshooting: which configuration is wrong?

Common post-deployment failures can look identical from the caller's perspective despite completely different root causes.

| Symptom | Layer to inspect | How to distinguish |
| --- | --- | --- |
| `UnknownHostException: inventory-service` | HTTP client missing LoadBalancer or URI treated as DNS | Check `@LoadBalanced` builder, filter/interceptor, and Feign URL overrides |
| Spring Cloud LoadBalancer no instance / 503 | Discovery/supplier/health | Empty registry list? Wrong service ID? Zone/health filter dropped all? |
| Connection refused | IP/port/Pod listener | Instance selected, yet transport could not connect |
| Read timeout | Slow backend or transport/deadline | Did request reach backend? Was body processed? |
| TLS handshake failure | Trust, SAN, SNI, mTLS | Peer cert chain, private key, physical URI, system clock |
| HTTP 401 | OAuth2 access token, API key, issuer/audience | Token/key expired, wrong source, or stale generation? |
| HTTP 403 | Authorization policy/scope | Authentication succeeded yet permissions insufficient |
| One Order Pod fails while others succeed | Config/secret generation mismatch across Pods | Compare config revisions, mount versions, rollout status |
| Only `prod` profile fails | `application-prod.yml`, env/Secret/prod registry | Check precedence and config sources |
| Still uses old value after ConfigMap edit | Env vars captured at startup | Did a rolling restart or refresh pipeline run? |
| Still sends old API key after Secret volume edit | Interceptor/provider cached old snapshot | Inspect provider generation and bean lifecycle |
| TLS fails on only some Inventory instances | Rolling certs out of sync | Canary per instance, CA overlap, SANs |
| Error rate rises after lowering cache TTL | Registry/network load or discovery jitter | Check cache misses and registry latency |
| More retries than expected in config | Multiple retry layers enabled together | Count HTTP attempts per layer |
| Actuator exposes raw values | Wrong endpoint exposure/show-values/filters | Lock down access and audit immediately |
| Pod `CrashLoopBackOff` on Config Data import | Secret path unmounted or required import missing | Check volumes, permissions, startup exceptions |

### 26.1. Distinguishing no-instance from backend HTTP 503

~~~text
Scenario A:
  ServiceInstanceListSupplier = []
  LoadBalancer cannot pick a target
  Backend receives 0 requests
  Caller gets error/no-instance (possibly mapped to 503)

Scenario B:
  Supplier = [inventory-a]
  LoadBalancer picks A
  HTTP request reaches A
  Inventory A returns 503
~~~

Both can surface as **503** on the caller side, yet their runbooks and retry decisions differ. Inspect **backend request counts, selected instance, traces, and response origin**.

### 26.2. Wrong profile and wrong service ID

Example:

~~~text
Correct prod service ID: inventory-service
Wrong profile value:    inventory-prod-service

Spring Cloud LB lookup: inventory-prod-service
Registry has only:     inventory-service
Result: no instance
~~~

Do not try to fix this by increasing `readTimeout` or adding retries. Fix the property's **source of truth** and add contract tests for service IDs.

## 27. Runbook for rolling out and rolling back config/secrets

A safe deployment workflow:

### 27.1. Before rollout

1. Record **image digest**, **config revision**, **secret generation**, and change owner.
2. Verify manifest namespaces, ConfigMap/Secret references, RBAC, and file permissions.
3. Verify YAML/`ConfigurationProperties` binding and fail-fast secret validation in staging.
4. Ensure Inventory/Identity Provider already accepts the **new credential** when rotating.
5. Set rollout strategy, readiness, and canary traffic slice.
6. Define rollback thresholds: 401/403, TLS handshake failures, no-instance, timeouts, P95/P99.

### 27.2. During rollout

~~~text
Canary 1 Pod / small group
  -> reads new config/secret generation
  -> ready
  -> test Inventory A/B route per policy
  -> verify Bearer/mTLS
  -> monitor errors and retry attempts
  -> expand rollout gradually
~~~

Never roll all Pods simultaneously when changing **client secrets, CAs, or discovery policies**, because a single mistake can lock out every caller at once.

### 27.3. When errors are detected

1. **Halt rollout** to contain blast radius.
2. Classify **config precedence, discovery, HTTP transport, TLS, auth, or backend 5xx**.
3. Gather non-sensitive metadata: version, selected instance, zone, error class, HTTP status.
4. If the old credential is still safe, roll back config/secret references and restore Pods per procedure.
5. If an old key was compromised, **never roll back to the leaked key**; perform emergency re-issuance/revocation and accept controlled downtime if needed.
6. Confirm recovery with real requests and SLOs, not merely Kubernetes Deployment `Available`.
7. Document incident timeline and update tests/alerts.

### 27.4. Rollback is not just image rollback

~~~text
Image v15 + Config rev-A + Secret gen-7 => OK
Image v15 + Config rev-B + Secret gen-8 => FAIL

Rolling back image v15 alone: does not solve the issue.
~~~

If the change was a **ConfigMap value** or **Secret generation**, rollback must revert **the exact changed source** and trigger the required restart/refresh. Keep config schemas compatible across code versions; new config may introduce keys old code ignores or drop keys old code requires.

## 28. Environment-based troubleshooting exercises

### 28.1. Exercise A: dev works, prod reports no-instance

**Context:** Dev uses `SimpleDiscoveryClient` with `inventory-service` and works fine. Prod deploys Order Pods, yet every call to Inventory fails with no-instance.

**Question:** What to check first?

**Answer:** Verify **spring.profiles.active**, the effective runtime service ID, discovery provider/starter, namespace, registry/`ServiceInstance` list, and supplier filters. Never assume healthy Pods mean LoadBalancer found backends. Never increase retries or hardcode `localhost` into prod.

### 28.2. Exercise B: ConfigMap changed yet timeout stays the same

**Context:** Ops changed `APP_INVENTORY_RESPONSE_TIMEOUT` from `2s` to `500ms` in the ConfigMap. Running Pods still use the old value.

**Answer:** When a ConfigMap is injected via **envFrom**, the process does not pick up env var updates. Trigger a rolling restart or use a tested volume/refresh design. Also verify that beans/HTTP request factories actually **consume** the property rather than only binding it into a record.

### 28.3. Exercise C: Secret rotated yet Feign still gets 401

**Context:** The secret key rotated and the Kubernetes volume shows the new file, yet Feign's `RequestInterceptor` still sends the old API key.

**Answer:** The `RequestInterceptor`/credential provider likely captured the value at startup. File updates do not automatically update Java fields. Have the provider read the live generation per request, recreate the client/bean cleanly, or perform a rolling restart. Also verify Feign configuration is scoped cleanly and not leaking keys to other services.

### 28.4. Exercise D: TLS handshake fails on only one instance

**Context:** Inventory A/B use the new certificate while C still uses the old certificate; Order already removed `CA-old` from its truststore.

**Answer:** This is an **unsynchronized trust rollover**. Use a dual-trust overlap for normal rotation, canary per instance, verify selected physical hosts/SANs, and only then revoke `CA-old`. If `CA-old` was compromised, follow the security runbook and never enable trust-all.

### 28.5. Exercise E: retries generate too many requests

**Context:** Spring Cloud LoadBalancer retries 2 attempts, WebClient Reactor retries 3 attempts, and the mesh retries 2 more times.

**Question:** Why can the backend receive so many calls?

**Answer:** Retry layers **can multiply attempts** when triggered on the same failure. Never assume total attempts equal `max(2,3,2)`. Determine exact nesting semantics per layer and count real backend attempts. Designate one primary retry layer, plus a deadline and idempotency.

### 28.6. Exercise F: Config Server unavailable

**Context:** Prod configures non-optional `spring.config.import=configserver:...`, and Config Server has a temporary outage.

**Answer:** Startup can fail because required Config Data cannot be loaded. That is intentional when essential configuration is missing. Address Config Server availability, TLS/auth, and bounded retries; never switch to **optional:** if doing so lets the app boot with unsafe defaults/auth.

### 28.7. Exercise G: migrating from Kubernetes Service DNS to Spring Cloud LoadBalancer

**Context:** Originally the client called `inventory-service.orders.svc.cluster.local` directly. Now the team wants zone preference based on Pod metadata.

**Answer:** Verify that **Spring Cloud Kubernetes DiscoveryClient** provides Pod endpoints with accurate zone metadata, grant required RBAC, register a `@LoadBalanced` client, preserve valid HTTPS/SANs, and verify the selected `ServiceInstance`. Simply changing the `Host` header or setting **spring.cloud.loadbalancer.zone** does not magically enable Pod discovery.

## 29. Anti-patterns that commonly cause incidents

| Anti-pattern | Consequence | Alternative |
| --- | --- | --- |
| Hardcoding passwords/API keys in `application-prod.yml` | Credential leak via Git/JAR | Secret Manager/configtree |
| Committing Secret manifests with Base64 plaintext | Base64 is not security encryption | External secret/encryption policy |
| Using ConfigMaps for private keys | Improper access controls | Secrets/PKI workload identity |
| Building different artifacts per environment just to swap config | Hard to reproduce and audit | Build once, deploy many |
| Treating profiles as secret "encryption" | Profile files remain readable | Separate secrets from artifacts |
| Enabling Config Server + K8s API + local imports with unclear precedence | Unpredictable runtime config | Define canonical source/priority |
| Marking required secret imports `optional` | App boots missing credentials | Non-optional + validation |
| Copying `localhost` from dev into prod Pods | Pod calls itself instead of Inventory | Proper discovery/Kubernetes Service |
| Assuming Kubernetes Service DNS equals client-side Pod selection | Wrong observability/routing assumptions | Pick explicit architecture |
| Changing `spring.cloud.loadbalancer.cache.ttl` to fix TLS | Wrong layer | Fix certificates/HTTP connector |
| Enabling retries on all exceptions and HTTP methods | Retry storms/duplicate side effects | Classify errors, budget/idempotency |
| Disabling hostname verification to pass TLS | Loses identity verification; MITM risk | Fix URI/SAN/CA |
| Editing Secret env vars expecting the JVM to auto-update | Old value persists | Rolling restart |
| Mounting Secrets via `subPath` expecting auto-rotation | File never updates automatically | Mount directory or restart |
| Reloading only Spring Boot's server SSL bundle assuming outbound updates | Outbound HTTP pools keep old context | Test consumers, rebuild/drain |
| Using a global Feign `RequestInterceptor` for Inventory tokens | Token leaks to other services | Per-client auth provider |
| Logging unsanitized `Environment`/`configprops` | Leaks secrets and URLs | Sanitization + RBAC |
| Tying every downstream into liveness | Restart cascades on dependency outages | Liveness for process health; selective readiness |
| Rolling back image without rolling back config/secret references | Incident persists | Track all three revisions |

## 30. End-to-end scenario: one Order Service image for dev and production

Imagine the exact same image **order-service@sha256:...** promoted across two environments.

### 30.1. Development environment

~~~text
Profile: dev
Service ID: inventory-service
Discovery source: SimpleDiscoveryClient
Instances: 127.0.0.1:8091 and 127.0.0.1:8092
HTTP scheme: local HTTP, no production credentials sent
Retry: disabled
Response timeout: 3s
Observability: local debug, fake trace
~~~

Learners can test Round Robin by running two Inventory processes and recording **`instanceId` returned by the backend**. Neither Secret Manager nor production Config Server is needed.

### 30.2. Production environment

~~~text
Profile: prod
Service ID: inventory-service
Discovery: Spring Cloud Kubernetes DiscoveryClient (if that model is chosen)
Metadata: zone and health per configured policy
HTTP scheme: HTTPS/mTLS if required
Retry: bounded, only for eligible errors/methods
Response timeout: 1500ms per SLO
Config source: ConfigMap + Config Data
Secret source: mounted Secret/Secret Manager
Credential source: OAuth2 authorized client or API key provider
Rollout: 3 replicas, readiness, canary, drain
~~~

Business code still simply calls:

~~~java
StockResponse stock = inventoryRestClient.get()
        .uri("/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

**No environment branching in service methods**:

~~~java
// Avoid this design:
if ("prod".equals(profile)) {
    return client.get("https://hardcoded-production-host");
}
return client.get("http://localhost:8091");
~~~

Instead, the **RestClient bean** and **config/secret providers** decide service ID, transport, trust material, and authorization. The business layer uses one stable abstraction.

### 30.3. Config metadata that should stay visible per request

When request tracing is needed:

~~~text
Request:
  logical service: inventory-service
  selected instance: inventory-b
  environment: prod
  config revision: release-2026-11
  credential generation: v7

Response:
  HTTP 200 / 401 / 503
  elapsed
  retry attempts
~~~

Record these fields only through controlled telemetry. **Never** log `Authorization` headers, private keys, access tokens, or usernames/passwords. If a selected instance violates policy (e.g., zone mismatch), inspect **discovery metadata and the supplier chain** rather than patching the `Host` header after selection.

### 30.4. Scenario acceptance criteria

| Criterion | How to verify |
| --- | --- |
| Identical image digest | Digest across dev/staging/prod stays identical when only config changes |
| Right active profile | Runtime active profiles verified safely |
| Zero secrets in artifacts | Secret scanning and release package inspection |
| Right service ID | Discovery tests and HTTP calls to real instances |
| Valid TLS/auth | HTTPS handshake + HTTP 200/401/403 per policy |
| Timeouts truly enforced | Stub slow backend and observe exceptions/deadlines |
| Bounded retries | Count attempts at both backend and caller |
| Proper readiness | Pod refuses traffic until required config/secrets are ready |
| Valid rotation/rollback | Test credential generations before/after without reusing leaked secrets |
| Diagnosable | Metrics + traces expose no credentials |

## 31. Deployment checklist

### 31.1. Configuration and profiles

- [ ] Business code uses **service IDs/adapters**, never hardcoding host IPs per environment.
- [ ] Clear conventions for **application.yml**, **application-{profile}.yml**, and external config sources.
- [ ] Verified `PropertySource` precedence for overlapping keys.
- [ ] `dev` profile uses mock/local discovery; `prod` uses approved discovery sources.
- [ ] Profiles are never used as encryption or secret storage.
- [ ] Key settings are bound with **@ConfigurationProperties** and validated.
- [ ] Timeouts, retries, TTLs, and endpoints have owners, defaults, and bounds.
- [ ] Required configuration fails fast when missing or invalid.
- [ ] Every rollout tracks **image digest + config revision + secret generation**.

### 31.2. Secrets and authentication

- [ ] Zero real API keys, passwords, client secrets, or private keys in Git, JARs, images, or CI logs.
- [ ] Kubernetes ConfigMaps hold only non-sensitive values.
- [ ] Secrets come from audited credential systems with least-privilege RBAC.
- [ ] Verified Secret volume paths, key names, file permissions, and UID/GID.
- [ ] Never use `subPath` if automatic Secret volume updates are expected.
- [ ] Understand that env vars from Secrets/ConfigMaps **do not auto-update inside the JVM**.
- [ ] OAuth2 access tokens are fetched/refreshed via appropriate managers/providers.
- [ ] Client secrets and mTLS private keys have dedicated rotation workflows.
- [ ] Never use trust-all or disable hostname verification.
- [ ] Never send `Authorization` headers to unauthorized services/audiences.
- [ ] Protect Actuator `env`/`configprops`/`refresh`, never exposing unsanitized values.
- [ ] Have an emergency revocation process on compromise without rolling back to leaked keys.

### 31.3. LoadBalancer and HTTP clients

- [ ] Clearly separated **Kubernetes Service DNS** from **Spring Cloud client-side selection**.
- [ ] `DiscoveryClient` uses the right starter, namespace, credentials, and service ID.
- [ ] `ServiceInstanceListSupplier` chain orders caching/health/zone/hints properly.
- [ ] Cache TTL and registry refresh are measured to avoid prolonged stale instances.
- [ ] Zone preference is not relied upon as a security/compliance boundary.
- [ ] `RestClient`/`RestTemplate`/`WebClient`/Feign are wired cleanly as `@LoadBalanced`.
- [ ] HTTP clients preserve Spring Boot's observability, codecs, TLS, and customizers.
- [ ] Connection pools and connect/read/response/pool timeouts are configured.
- [ ] Retries apply only to safe errors and HTTP methods with explicit attempts/backoff/deadlines.
- [ ] Do not stack unintended retries across client, LoadBalancer, gateway, and mesh.
- [ ] Circuit breakers/fallbacks distinguish unavailability from valid business results.
- [ ] Feign URL overrides do not accidentally bypass LoadBalancer.

### 31.4. Testing and operations

- [ ] Unit tests for configuration, precedence, and `@ConfigurationProperties` validation.
- [ ] Integration tests calling via service ID across multiple backends.
- [ ] Tests for no-instance, 503, connect timeout, read timeout, and auth failures.
- [ ] TLS tests with valid SANs and rotated cert/key generations.
- [ ] Secret rotation/rolling restart tests under active traffic.
- [ ] Deployments configure readiness/liveness without triggering restart cascades.
- [ ] Canary/rolling strategies have rollback thresholds and observation windows.
- [ ] Logs/metrics never expose tokens, passwords, API keys, private keys, or tenant data.
- [ ] Dashboards track 401/403, TLS handshakes, retries, no-instance, and P95/P99.
- [ ] Rollback runbook covers **config, image, and credential references**.
- [ ] Owners and review schedules exist for secret expiry, CA rotation, and config drift.

## 32. Conclusion

Managing environment-specific configuration and connection secrets in a Spring Cloud LoadBalancer system is not merely creating multiple YAML files. It means defining the **source of truth**, **precedence**, **typed contracts**, **HTTP client/credential lifecycles**, **rollout/rollback policies**, and **observability**.

Key principles:

1. **One artifact, many environments:** swap deployment parameters using profiles, environment, Config Data, and config stores rather than embedding hosts/secrets in code.
2. **Configuration differs from secrets:** TTLs/timeouts/service IDs do not share lifecycles or access controls with API keys, OAuth2 client secrets, or mTLS private keys.
3. **LoadBalancer only picks targets:** discovery/health/zones shape the candidate list; HTTP clients handle TLS, `Authorization`, connection pools, and timeouts.
4. **Config updates may not take effect immediately:** updating a ConfigMap/Secret does not automatically rebuild an existing `RestClient`/`WebClient`/Feign or `SSLContext`.
5. **Fail fast, roll out safely:** validation, fail-fast required secrets, canaries, readiness, tests, and rollbacks reduce risk.
6. **Never weaken security to hide deployment bugs:** no trust-all, no hardcoded credentials, and no infinite retries on 401/403/TLS failures.

When designed well, the same Order Service runs across developer laptops, staging, and Kubernetes production via controlled configuration while calls to **inventory-service** stay reliable, verifiable, and secure.

## 33. References

- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): PropertySource precedence, profile-specific files, `spring.config.import`, environment variables, and `configtree`.
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): activating profiles, environment-specific configs, and profile groups.
- [Spring Boot – Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): `@ConfigurationProperties`, binding, and validation.
- [Spring Boot – SSL](https://docs.spring.io/spring-boot/reference/features/ssl.html): PEM/JKS bundles, key/trust material, and SSL reload consumer limits.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): `RestClient`, `WebClient`, request factories, customizers, and SSL helpers.
- [Spring Boot – Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): security, exposure, and sanitization of `env`/`configprops`.
- [Spring Boot – Kubernetes Probes](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html#actuator.endpoints.kubernetes-probes): liveness/readiness in Kubernetes.
- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): `ServiceInstanceListSupplier`, discovery, caching, health, zones, retries, and metrics.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): Spring Cloud LoadBalancer properties.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `@LoadBalanced` `RestClient`, `RestTemplate`, and `WebClient`.
- [Spring Cloud Config – Client](https://docs.spring.io/spring-cloud-config/reference/client.html): `configserver:` imports, optional/fail-fast, profiles/labels, and retries.
- [Spring Cloud Kubernetes – PropertySource Implementations](https://docs.spring.io/spring-cloud-kubernetes/reference/property-source-config.html): Kubernetes ConfigMap/Secret sources, config imports, and precedence.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): named-client timeouts, URL overrides, Feign retries, and LoadBalancer integration.
- [Spring Security – OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `OAuth2AuthorizedClientManager`, client credentials, and token lifecycles.
- [Spring Security – Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive token acquisition and WebClient filters.
- [Kubernetes – ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): distributing config to Pods, env vars, and file volumes.
- [Kubernetes – Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): Secret volume/env behavior, `subPath`, propagation, and security.
- [Kubernetes – Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/concepts/configuration/liveness-readiness-startup-probes/): deciding when Pods accept traffic.
- [Kubernetes – Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/): RollingUpdate, rollouts, and rollbacks.
- [Micrometer – Reference](https://docs.micrometer.io/micrometer/reference/concepts.html): counters, timers, histograms, and cardinality limits.
