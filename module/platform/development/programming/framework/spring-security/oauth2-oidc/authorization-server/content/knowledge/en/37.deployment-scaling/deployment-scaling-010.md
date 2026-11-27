# Health Checks, Readiness, Graceful Shutdown, and Rolling Deployments

An OAuth 2.0 / OpenID Connect Authorization Server is a central trust anchor: it authenticates users, validates clients, records consents, issues authorization codes and tokens, and publishes metadata and public keys so other parties can verify tokens. When running multiple replicas or deploying new versions, the system must continue handling in-flight flows and ensure every replica maintains consistent security state.

In the **Spring Security OAuth2/OIDC Authorization Server** module, deployment and scaling include designing health checks, readiness, graceful shutdown, and rolling deployments. These mechanisms coordinate with Spring Boot Actuator, Spring Security, the authorization store, the signing key source, and orchestration platforms such as Kubernetes. The goal is for the system to receive traffic only when ready, drain an instance from traffic in a controlled way, and swap versions without breaking OAuth/OIDC flows.

## 1. Why does the Authorization Server need a controlled deployment workflow?

A typical web application might only need to check that its process is running and serving HTTP. An Authorization Server has additional security state and resources that must stay synchronized across instances.

| Component | Role in the Authorization Server | Risk in multi-replica deployments |
|---|---|---|
| **RegisteredClientRepository** | Reads client configs, redirect URIs, grant types, scopes, and token policies | Replicas using different client data may accept or reject the same request differently |
| **OAuth2AuthorizationService** | Persists authorization codes, access tokens, refresh tokens, and authorization state | An authorization code created on one replica cannot be found by another; refresh tokens or revocations become inconsistent |
| **OAuth2AuthorizationConsentService** | Persists user consents for clients and scopes | Users are prompted for consent repeatedly or replicas apply divergent consent state |
| Signing key source (**JWKSource**) | Signs JWTs and publishes JWKS for resource servers to verify | Tokens signed by replica A may fail verification on replica B or resource servers |
| HTTP session | Holds login sessions and part of interactive user state | Subsequent requests hitting another replica may lose the session or force users to log in again |
| Issuer and endpoint configuration | Publishes Authorization Server addresses in OIDC Discovery and tokens | Replicas may issue tokens with inconsistent issuers or metadata |
| Database, cache, KMS, or config service | Supplies data and resources required to process authorization flows | An instance may start up successfully yet still lack the ability to issue tokens |

Therefore, a "running process" state is not enough to conclude a replica can accept requests. You must distinguish a healthy process, an initialized application, and an application ready to serve traffic.

## 2. Distinguishing liveness, readiness, and startup probes

Three probe types answer three distinct questions. Misconfiguration can cause Kubernetes to continuously restart the application during a database outage, or add a replica without signing keys into a Service.

| Probe | Question | When it fails | Appropriate checks |
|---|---|---|---|
| Liveness | Is the process alive and able to keep running? | Platform restarts the container | Process status, internal responsiveness, unrecoverable errors |
| Readiness | Can the instance accept business requests right now? | Platform stops sending new traffic to the instance | Spring readiness state, required database, signing key source, and mandatory configuration |
| Startup | Has the application finished starting up? | Platform keeps waiting or restarts if the deadline is exceeded | Configuration loading time, Spring context initialization, initial resource connections, and controlled migrations |

### 2.1. Liveness: determining whether the application can keep running on its own

Liveness should reflect the process's ability to continue executing. For example, if the application deadlocks, an essential core component stops making progress, or the HTTP server stops serving requests, liveness can transition to **DOWN**.

Do not put every external dependency into liveness. If the database temporarily loses connectivity, marking liveness **DOWN** causes Kubernetes to restart all replicas. New instances still cannot connect to the database, creating a restart loop and worsening overload. A dependency outage can make an instance unready, yet restarting the process will not necessarily fix that outage.

### 2.2. Readiness: determining whether the instance can accept traffic

Readiness must reflect the conditions actually required to process requests. For an Authorization Server, these typically include:

- The Spring ApplicationContext has initialized and initial preparation steps are complete.
- The database is reachable if clients, authorizations, or consents are stored there.
- **RegisteredClientRepository**, **OAuth2AuthorizationService**, and **OAuth2AuthorizationConsentService** are properly configured and backed by a shared store.
- Valid signing keys are available if the instance needs to issue JWTs.
- Issuer, redirect URIs, endpoints, and required secrets are loaded.
- The session store is reachable if the system uses centralized sessions to maintain logins.

Not every integrated service belongs in readiness. Include only dependencies without which the instance genuinely cannot perform its assigned role. For example, a system may still serve JWKS and discovery when a federated identity provider experiences a disruption; in that case, putting that provider into readiness could pull instances out of traffic more broadly than necessary.

Health indicators must reflect real state and return quickly. Avoid running a full login or token-issuance flow every few seconds just to check health.

### 2.3. Startup probe: giving startup enough time

A new replica may need time to build the Spring context, read secrets, initialize connection pools, or load keys from KMS. If liveness starts too early, Kubernetes may restart the application before it has a chance to finish booting.

The startup probe provides a dedicated startup window. While the startup probe has not yet succeeded, Kubernetes does not use liveness and readiness to judge the container. Once the startup probe passes, the other two probes govern the instance lifecycle.

## 3. Configuring health endpoints with Spring Boot Actuator

Add Spring Boot Actuator to expose health endpoints. Expose only the endpoints genuinely needed for operations.

Example **application.properties**:

~~~properties
management.endpoints.web.exposure.include=health,info

# Enable health groups for liveness and readiness.
management.endpoint.health.probes.enabled=true

# Do not return dependency details or exceptions on public health requests.
management.endpoint.health.show-details=never
management.endpoint.health.show-components=never

# Readiness includes Spring state, database, and the signing key health indicator.
# Include db only when the database is a mandatory dependency for business requests.
management.endpoint.health.group.readiness.include=readinessState,db,signingKeys

# Stop accepting new requests and wait for in-flight requests to finish on shutdown.
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

When health probes are enabled, Spring Boot exposes two groups:

- **/actuator/health/liveness**
- **/actuator/health/readiness**

The default readiness group reflects **ReadinessState**; the example above adds the **db** and **signingKeys** health contributors. Only declare **signingKeys** when the application defines the corresponding health indicator bean. If not using a database or if a dependency is optional, adjust the **include** list to match your actual architecture. Do not add contributors merely because they exist.

Starting with Spring Boot 3.2, you can also configure:

~~~properties
management.endpoint.health.probes.add-additional-paths=true
~~~

This creates **/livez** and **/readyz** on the application's main HTTP port. It is useful when management endpoints run on a separate port: probes hitting the main port verify the serving health of the business HTTP server rather than proving only that the management port is alive.

If using a separate management port, clearly define which port Kubernetes probes will call and protect the management port with network policies or internal access controls. A management port returning healthy while the main HTTP port is broken creates a false readiness signal.

### 3.1. Creating a health indicator for the signing key source

Spring Boot provides health contributors for common resources such as **DataSource**. For Authorization Server-specific resources, you can create a **HealthIndicator** to verify the signing key source.

~~~java
import org.springframework.boot.actuate.health.Health;
import org.springframework.boot.actuate.health.HealthIndicator;
import org.springframework.stereotype.Component;

@Component("signingKeys")
public class SigningKeysHealthIndicator implements HealthIndicator {

    private final SigningKeyRegistry signingKeyRegistry;

    public SigningKeysHealthIndicator(SigningKeyRegistry signingKeyRegistry) {
        this.signingKeyRegistry = signingKeyRegistry;
    }

    @Override
    public Health health() {
        if (signingKeyRegistry.hasUsableSigningKey()) {
            return Health.up().build();
        }

        return Health.down()
                .withDetail("reason", "No active signing key")
                .build();
    }
}
~~~

**SigningKeyRegistry** in the example is an application abstraction responsible for determining whether an active, valid signing key is available. The check should inspect already-loaded state or perform a lightweight operation. If keys live in KMS, avoid making an expensive KMS call on every Kubernetes probe interval; check connectivity periodically and update internal status instead.

Health endpoints should return only necessary operational status. Never include private keys, secrets, access tokens, refresh tokens, database connection strings, or exceptions containing sensitive data in responses.

### 3.2. Securing Actuator endpoints

Kubernetes needs access to health endpoints, while other management endpoints should not become public APIs. You can separate a **SecurityFilterChain** for Actuator and order it before business filter chains.

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
@Order(0)
SecurityFilterChain actuatorSecurityFilterChain(HttpSecurity http) throws Exception {
    http
        .securityMatcher(EndpointRequest.toAnyEndpoint())
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(EndpointRequest.to("health")).permitAll()
            .anyRequest().hasRole("OPS")
        )
        .httpBasic(Customizer.withDefaults());

    return http.build();
}
~~~

The example permits the health endpoint for kubelet probes and requires operational privileges for other Actuator endpoints. Operational accounts must be configured in an appropriate authentication system; the management port should also be restricted to internal networks. Allowing access to health does not mean allowing access to other management endpoints.

If the application has multiple **SecurityFilterChain** beans, verify the order and matcher of each chain. The Authorization Server chain must not intercept Actuator requests before the management chain. Also verify actual health group paths whenever changing **management.endpoints.web.base-path**.

## 4. Dependencies that must be consistent across replicas

Health checks detect only part of potential issues. For safe rolling deployments, replicas must share compatible state and configuration.

### 4.1. Using a shared store for clients, authorizations, and consents

In a multi-replica environment, the following data must reside in a shared store:

- Registered clients in **RegisteredClientRepository**.
- Authorizations in **OAuth2AuthorizationService**, including authorization code, access token, and refresh token state.
- Consents in **OAuth2AuthorizationConsentService**.

If each replica uses in-memory implementations, an authorize request may be handled on replica A while the subsequent token request hitting replica B fails to find the authorization code. Refresh tokens, revocations, or consents can also produce divergent outcomes depending on which instance handles the request.

With a shared database, every replica reads from and writes to the same data source. Configure appropriate connection pools, timeouts, bounded retries, and database failover handling. Never retry write requests infinitely.

Caching clients or authorizations can reduce load, but requires explicit invalidation rules, TTLs, and revocation handling. A local cache must never allow a disabled client or revoked token to remain accepted beyond policy limits.

### 4.2. Keeping the issuer stable

The issuer is the Authorization Server's public identifier. This value must be identical across all replicas and match the public address used by clients and resource servers.

You can declare the issuer explicitly using **AuthorizationServerSettings**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

Do not derive the issuer from hostnames, internal IPs, or pod names. When placed behind a reverse proxy or ingress, configure forwarded-header handling properly so the application recognizes the public scheme and host. OIDC Discovery and the **iss** claim in tokens must remain consistent across replicas.

### 4.3. Using a consistent signing key source and rotating keys with a transition window

Every replica needs access to the same key set or the same signing service. You can use a protected secret store, KMS, or an appropriate key management system. Never generate random per-pod signing keys at startup: tokens signed by replica A may fail verification when replica B's public key is advertised.

When rotating keys:

1. Create a new key with a unique **kid** and add the new public key to JWKS.
2. Wait so JWKS consumers have time to fetch the new key.
3. Switch signing operations to the new key.
4. Keep the old public key in JWKS at least until tokens signed with the old key expire, plus clock skew and JWKS cache lifetimes.
5. Remove the old key only when no valid tokens remain that require it for verification.

Never publish private keys in JWKS. Readiness checks should verify that the instance can use an active signing key; they should also detect expired keys or incompatible algorithm configurations.

### 4.4. Sharing sessions when login flows require sessions

The authorization endpoint normally interacts with the user's login session. If sessions live only in one pod's memory, a subsequent request routed to another pod can lose the session. You can use Spring Session with Redis or JDBC to share sessions across replicas.

Sticky sessions can reduce how often requests switch pods, but they do not replace a shared session store: pods can still restart, scale down, or lose connectivity. If forcing users to log in again when a pod terminates is acceptable, treat that as an explicit product decision and test the authorize flow accordingly.

## 5. Graceful shutdown in Spring Boot

When a pod is being replaced, the application needs time to finish in-flight requests. If the process terminates immediately, token responses or redirects can be cut off mid-flight.

With Spring Boot's graceful shutdown support, configure:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Upon receiving a shutdown signal, the web server stops accepting new connections or requests according to the server's mechanism and waits for in-flight requests to complete within the configured window. After that deadline, shutdown proceeds.

The pod termination sequence in Kubernetes typically includes:

1. The pod is marked terminating and removed from endpoints serving new traffic.
2. The **preStop** hook, if present, executes.
3. The container receives **SIGTERM**.
4. Spring Boot performs graceful shutdown and waits for in-flight requests.
5. Once **terminationGracePeriodSeconds** expires, Kubernetes may send a forceful termination signal.

Spring's wait duration must be shorter than **terminationGracePeriodSeconds**, leaving headroom for hooks and platform cleanup operations. For example, if Spring waits 30 seconds, you can set the pod termination grace period to 60 seconds. Adjust according to request processing times and real operational procedures.

The **/oauth2/authorize**, **/oauth2/token**, **/oauth2/jwks**, and OIDC Discovery endpoints have different profiles. Token requests usually need fast responses; the authorization endpoint may involve login and redirects. Do not assume every client can safely retry an interrupted request. Authorization codes are single-use; blindly retrying a token request can fail because the code was already consumed or state already changed.

Graceful shutdown also does not replace durable authorization persistence. A request may finish cleanly, yet if authorizations live only in pod memory, state is still lost when the pod is deleted.

## 6. Rolling deployments with Kubernetes

Rolling deployments replace pods in batches with the new version. Kubernetes should add a new pod to the Service only after readiness passes; old pods are removed from traffic when termination starts.

### 6.1. Deployment configuration

The example below illustrates a Deployment with three replicas, startup probe, readiness probe, liveness probe, and graceful termination period.

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: authorization-server
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  minReadySeconds: 10
  progressDeadlineSeconds: 600
  selector:
    matchLabels:
      app: authorization-server
  template:
    metadata:
      labels:
        app: authorization-server
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: authorization-server
          image: registry.example.com/authorization-server:1.8.0
          ports:
            - name: http
              containerPort: 8080
          startupProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 36
          readinessProbe:
            httpGet:
              path: /actuator/health/readiness
              port: http
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /actuator/health/liveness
              port: http
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
~~~

**maxSurge: 1** allows creating one extra pod during updates. **maxUnavailable: 0** requires Kubernetes to keep the configured number of ready replicas available throughout the rollout; the cluster must have enough resources to schedule the new pod. If CPU, memory, or quota is insufficient, the rollout can stall because the new pod cannot be created or become ready.

**minReadySeconds** requires a pod to remain ready for a period before counting as available. **progressDeadlineSeconds** bounds how long a rollout may stall without progress. These values should match the application's startup time and recovery behavior.

The example uses **/actuator/health/...**. If **management.endpoint.health.probes.add-additional-paths=true** is enabled on a supported Spring Boot version, you can use **/livez** and **/readyz** on the main HTTP port. If Actuator uses a separate port, change **port** in the probes to match your actual configuration and separately verify the serving health of the business port.

### 6.2. Flow of replacing a replica

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant S as Service
    participant N as New Pod
    participant O as Old Pod

    K->>N: Create container with new version
    N-->>K: Startup probe succeeds
    N-->>K: Readiness remains DOWN while preparing
    Note over N: Load config, check database and signing keys
    N-->>K: Readiness UP
    K->>S: Add New Pod to serving endpoints
    K->>O: Begin terminating Old Pod
    Note over O: Old Pod stops receiving new traffic
    K->>O: Send SIGTERM
    O->>O: Graceful shutdown, wait for in-flight requests
    O-->>K: Process exits
~~~

While the new pod is not yet ready, the Service continues routing traffic to existing ready pods. Once the new pod passes readiness, it is added to serving endpoints. The old pod is then terminated and Spring Boot has time to drain in-flight requests.

For an Authorization Server, this process is safe only if both versions remain compatible with the database schema, client configuration, session store, and signing keys. If the new version writes data the old version cannot read, the rollout can cause errors even when all probes are green.

## 7. Maintaining data and configuration compatibility during rollout

Rolling deployments normally create a window where two versions run concurrently. Design changes to be backward and forward compatible.

### 7.1. Expand-contract database migrations

A safe workflow typically includes:

1. **Expand:** add new columns, tables, or indexes in a way that keeps the old version working.
2. **Compatible deploy:** release application code that can read/write the expanded schema while still handling legacy data.
3. **Migrate data:** backfill or convert data if needed, tracking progress and resumability.
4. **Contract:** drop old columns or structures only after every old replica has stopped and no consumer depends on them.

Do not let every pod run destructive schema migrations while two versions run side by side. Use controlled migrations, migration locks, or a dedicated deployment step suited to your system.

### 7.2. Keeping configuration compatible during version transitions

Replicas must agree on critical values such as issuer, public endpoints, signing algorithms, token lifetimes, and client settings. When changing secrets or certificates, maintain a transition window so old and new versions both operate smoothly.

When changing **kid**, keys, or signing algorithms, coordinate the order of JWKS publication and signing cutover. When changing cookies or session serialization, ensure the new version can read sessions created by the old version throughout the rollout.

### 7.3. Controlling caches and revocation state

Per-pod local caches can cause replicas to drift out of sync. In particular, client disabling, token revocation, or consent updates require deterministic propagation times. If the system uses caches, define TTLs, invalidation, and behavior when sync events are missed. Never let caches extend acceptance of a disabled client or revoked token beyond policy limits.

## 8. Verifying rollouts and monitoring post-deployment

Probes are only the minimum signal for container orchestration. Operating an Authorization Server also requires monitoring business errors and interoperability with clients and resource servers.

Before and after a rollout, check key endpoints:

~~~bash
curl -i http://localhost:8080/actuator/health/liveness
curl -i http://localhost:8080/actuator/health/readiness

# OIDC Discovery, if OIDC is enabled.
curl -i https://auth.example.com/.well-known/openid-configuration

# Default JWK Set endpoint of Spring Authorization Server.
curl -i https://auth.example.com/oauth2/jwks
~~~

In a Kubernetes environment:

~~~bash
kubectl rollout status deployment/authorization-server
kubectl get pods -l app=authorization-server -w
kubectl describe deployment authorization-server
~~~

If a rollout has problems and needs to revert to the previous version:

~~~bash
kubectl rollout undo deployment/authorization-server
~~~

After a rollout, monitor at minimum:

- HTTP 5xx rates and latencies of **/oauth2/authorize**, **/oauth2/token**, discovery, and JWKS.
- Failure rates for client authentication, redirect URIs, authorization codes, refresh tokens, and consents.
- Database connections, connection pools, timeouts, and authorization write errors.
- Session store health and anomalous spikes in users forced to log in again.
- JWKS availability, count of published **kid** values, and signature verification errors on resource servers.
- Ready replica counts, startup times, restart counts, and readiness state transitions.
- Shutdown logs confirming in-flight requests completed within the allowed window.

You can test rollouts in staging by executing authorization flows, logging in, obtaining authorization codes, exchanging codes for tokens, using refresh tokens, and verifying JWTs while replacing replicas. Also test requests that are actively in flight when a pod receives **SIGTERM**. With real clients, verify redirect URIs and the issuer in discovery/tokens remain unchanged after the version swap.

## 9. Common operational mistakes

| Configuration or deployment mistake | Symptom | Resolution |
|---|---|---|
| Including the database in liveness | All pods restart when the database briefly disconnects | Move database to readiness if it is a mandatory dependency |
| Readiness checks only the process | Pods receive traffic before loading signing keys or connecting to the database | Add health indicators for essential dependencies |
| Each pod generates its own signing key | JWTs from one pod fail verification on another | Use a shared key source and key rotation with overlap |
| Using in-memory repositories across multiple replicas | Authorization codes, refresh tokens, or consents are inconsistent | Use shared, durable persistence implementations |
| Sessions stored only in pod memory | Users lose sessions when requests hit another pod | Use a shared session store or explicitly accept re-login behavior |
| Management port stays healthy while HTTP port fails | Probes pass while business traffic cannot reach the app | Probe on the main port or enable **/livez** and **/readyz** paths |
| Health endpoints blocked by SecurityFilterChain | Kubernetes receives 401/403 and marks pods unready | Separate an Actuator chain and allow controlled access to health |
| Graceful shutdown exceeds pod termination period | Pods are forcefully killed before draining finishes | Align Spring timeout with **terminationGracePeriodSeconds** |
| New schema incompatible with old version | Read/write errors while both versions run concurrently | Use expand-contract migrations |
| Issuer depends on internal hostname | Discovery and **iss** claim differ from public address | Configure a stable issuer and handle forwarded headers properly |

## 10. Pre-production checklist for the Authorization Server

- [ ] Liveness, readiness, and startup probes have distinct purposes, thresholds, and timeouts.
- [ ] Readiness reflects the database, signing key source, and dependencies genuinely required to serve requests.
- [ ] Liveness does not depend on the database or external services that can experience independent outages.
- [ ] Health endpoints do not expose secrets, tokens, private keys, or sensitive infrastructure details.
- [ ] Actuator endpoints have restricted access; Kubernetes can reach probes on the right port and path.
- [ ] **RegisteredClientRepository**, **OAuth2AuthorizationService**, and **OAuth2AuthorizationConsentService** use multi-replica-safe shared storage.
- [ ] Issuer, public endpoints, client settings, and signing key sources are consistent across pods.
- [ ] Sessions are shared, or session loss on pod termination is accepted and tested.
- [ ] Spring Boot graceful shutdown timeout is shorter than the pod termination grace period.
- [ ] Rolling updates have enough resources for **maxSurge** and maintain required ready replica counts.
- [ ] Database migrations and configuration remain compatible while two versions run concurrently.
- [ ] Key rotation keeps old public keys long enough to verify unexpired tokens.
- [ ] Authorization code, token, refresh token, consent, discovery, and JWKS flows have been tested during a rollout.
- [ ] Dashboards and alerts cover token errors, latency, database, sessions, restarts, and readiness.

Health checks indicate whether an instance can keep running or receive traffic. Graceful shutdown lets an instance leave the cluster in a controlled manner. Rolling deployments coordinate those mechanisms to swap versions step by step. For Spring Authorization Server, the safety of that process also depends on sharing authorization state, sessions, the issuer, and signing keys across replicas; these must be designed alongside probes and deployment strategies from the start.
