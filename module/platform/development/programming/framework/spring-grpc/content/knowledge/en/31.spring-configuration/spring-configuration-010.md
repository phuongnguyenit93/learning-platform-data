# Local, Test, Staging, and Production Profiles

## Lesson Objectives

In **SPRING_GRPC**, the same service can run on a developer's machine, in integration tests, in staging, and in production. Each environment has different endpoints, certificates, secrets, executor capacity, health policies, and observability settings. If these values are mixed in code or default configuration, the application can easily call the wrong system, accidentally disable TLS, or run test settings in a live deployment.

This lesson focuses on **local, test, staging, and production profiles** in Spring: understanding Spring Profiles and configuration loading order, separating values per environment, binding configuration into typed objects with validation, applying them properly to the gRPC server/channel, managing secrets, activating profiles at deployment, and testing to ensure the application uses the right configuration.

After this lesson, you will be able to:

1. Explain how Spring Boot activates profiles and merges configuration.
2. Design shared configuration alongside `application-local/test/staging/prod` files.
3. Use `@Profile` for environment-specific beans and `@ConfigurationProperties` for typed configuration.
4. Manage gRPC targets, TLS, timeouts, executors, health, and reflection by environment.
5. Separate committed configuration from runtime-injected secrets.
6. Activate and verify profiles in IDEs, tests, containers, and deployments.
7. Test per-profile configuration and detect unsafe production settings.

> **Scope:** Examples use Spring Boot, Spring gRPC, and gRPC Java. Keys in the `app.grpc.*` namespace below are custom application-defined settings for illustration. Actual listener/transport properties must use the exact names and extension points of the installed Spring gRPC version; do not infer starter properties from this example.

## 1. Why are profiles needed?

Profiles allow an application to use different configuration or beans depending on the environment. Common differences for a gRPC service:

| Component | Local | Test | Staging | Production |
| --- | --- | --- | --- | --- |
| Downstream target | localhost or dev service | In-process/fake/Testcontainer | Staging endpoint | Production endpoint/service discovery |
| TLS | Plaintext allowed on loopback | In-process or test TLS | TLS, typically close to prod config | TLS mandatory; mTLS per trust boundary |
| Certificate/CA | Test certificate or dev CA | Test fixtures | Staging secret/certificate | Production secret manager/PKI |
| Executor | Small, easy to debug | Deterministic, bounded | Close to production sizing | Sized for load and capacity |
| Health | Easy local inspection | Assert status | Probed like production | Readiness/liveness per policy |
| Reflection | Can be enabled | Can be enabled for tests | Controlled | Disabled or strictly restricted |
| Logging | More verbose | Collected for assertions | Structured, redacted | Structured, redacted, sampled |
| Dependency | Mock or dev instance | Fake/Testcontainer | Staging instance | Production service |

Profiles do not require building different artifacts. Typically the exact same artifact is deployed with different profiles and runtime configuration. This allows testing the exact artifact that will run in production.

## 2. How does Spring Boot load profiles?

Spring Boot loads base configuration from `application.properties` or `application.yml`, and then loads profile-specific configuration such as `application-local.yml` or `application-prod.yml` when the corresponding profile is active.

Example layout:

```text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
```

Shared configuration belongs in `application.yml`. Profile-specific files override shared values when a profile is enabled. External configuration sources such as environment variables, command-line arguments, mounted config, or secret providers can take higher precedence than files inside the artifact according to Spring Boot's Config Data/property source rules.

Do not copy all of `application.yml` into every profile. Only put values that genuinely differ into environment-specific files to prevent drift and keep reviews clean.

### 2.1. Activating a profile

You can activate a profile via an environment variable:

```bash
SPRING_PROFILES_ACTIVE=local
```

Or via a command-line argument:

```bash
java -jar spring-grpc-service.jar --spring.profiles.active=staging
```

In an IDE, configure the environment variable or program argument in the run configuration. In containers/orchestrators, pass the profile via deployment manifests or environment injection. Never hardcode the production profile in source code.

When multiple profiles are needed at once, Spring can activate a list of profiles—such as `staging` together with an observability profile. Check ordering and override values because profiles are processed in declaration order.

### 2.2. Rules for setting spring.profiles.active

Set `spring.profiles.active` in a non-profile-specific configuration source, such as an environment variable or the base `application.yml`. Do not set `spring.profiles.active` or `spring.profiles.include` inside a document already activated by a profile; Spring Boot restricts these profile-activation properties to non-profile-specific documents.

If using profile groups, declare the group in the base configuration so a single environment name activates multiple related profiles. Only use groups when the group has clear meaning and is tested; avoid creating unpredictable include chains.

### 2.3. Shared vs. environment-specific configuration

Example `application.yml`:

```yaml
spring:
  application:
    name: inventory-grpc

app:
  grpc:
    client:
      inventory:
        deadline: 2s
    observability:
      include-method: true
      include-request-id: true
    reflection:
      enabled: false
```

The `app.grpc.*` keys are application-defined settings in this lesson. They do not change listeners or channels automatically until bound and used in code. Put shared deadlines, logging policies, and safe defaults here; targets, TLS material, and capacity are overridden per environment.

## 3. Binding configuration into typed objects

Do not scatter dozens of `Environment.getProperty` calls across services. Use `@ConfigurationProperties` to group related configuration into a typed, validated object.

Example:

```java
@ConfigurationProperties(prefix = "app.grpc")
@Validated
public record GrpcApplicationProperties(
        @Valid Client client,
        @Valid Reflection reflection) {

    public record Client(
            @Valid Inventory inventory) {}

    public record Inventory(
            @NotBlank String target,
            @NotNull Duration deadline,
            @NotBlank String securityMode,
            String trustBundleLocation) {}

    public record Reflection(boolean enabled) {}
}
```

Register configuration properties via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`:

```java
@Configuration
@EnableConfigurationProperties(GrpcApplicationProperties.class)
class GrpcPropertiesConfiguration {
}
```

You can add validation by security mode: if mode is `tls`, the trust bundle/credential reference must exist; if production enables plaintext, context startup must fail. For nested records, use `@Valid` so validation cascades into child fields. Ensure the corresponding validation dependency is present in the build.

Field names and annotations must match your project's Java/Spring Boot version. The example above illustrates the structure; in real code, define explicit allowed values for `securityMode`, bound deadlines, and validate URIs/targets according to policy.

### 3.1. Using @Profile for environment-specific beans

`@Profile` is appropriate when bean implementations actually differ:

```java
@Configuration
@Profile("local")
class LocalGrpcClientConfiguration {

    @Bean
    InventoryGateway inventoryGateway() {
        return new LocalInventoryGateway();
    }
}
```

Another example is a fake downstream client for integration tests or an observability adapter enabled only locally. Do not duplicate a service implementation per profile merely to swap an endpoint; endpoints and timeouts should usually be configuration data while business behavior stays consistent.

A profile only determines which beans are created in the application context. It does not protect network endpoints on its own and does not replace authentication/authorization.

## 4. Local profile

Local should be optimized for a fast development loop while still keeping critical behavior close to production.

Example `application-local.yml`:

```yaml
app:
  grpc:
    client:
      inventory:
        target: dns:///localhost:9090
        deadline: 3s
        security-mode: plaintext
    reflection:
      enabled: true
```

Locally, plaintext is only appropriate when connecting over loopback or in an isolated dev environment. Never use the local file as the default configuration for containers or clusters. When developing TLS features, use a `local-tls` profile or test certificates to reproduce hostname verification and trust chains.

Local guidelines:

- Use controlled local/dev targets.
- Never include production tokens, private keys, or passwords.
- Reflection can be enabled so `grpcurl` can discover services.
- Logs can be more verbose, but must still redact credentials/payloads.
- A small executor makes thread dumps and debugging easier to read.
- Real dependencies should be dev instances or local containers—never accidentally point at production.

## 5. Test profile

Tests need repeatability, isolation, and no reliance on uncontrolled external services.

Example `application-test.yml`:

```yaml
app:
  grpc:
    client:
      inventory:
        deadline: 500ms
        security-mode: test
    reflection:
      enabled: true
```

The `security-mode=test` value is an internal application choice in this example; it might correspond to an in-process channel, test credentials, or test fixtures. Do not pass such a custom value to a gRPC builder unless your code explicitly defines its semantics.

Testing options:

- **Unit test:** mock gateways/repositories; no need to open a gRPC listener.
- **In-process gRPC test:** use `InProcessServerBuilder` and `InProcessChannelBuilder` to test services, interceptors, metadata, and statuses without opening a TCP port.
- **Transport integration test:** run a real server on a random port to verify HTTP/2, TLS, channels, and server wiring.
- **Testcontainers:** use real dependencies such as databases or brokers when behavior depends on that integration.

Use `@ActiveProfiles("test")` in Spring integration tests to activate test configuration explicitly. If a test uses `@DynamicPropertySource` or `TestPropertyValues`, remember that those values can override `application-test.yml`.

Never share production credentials for tests. Test certificates should be generated separately, have appropriate lifetimes, and never be trusted by production workloads.

## 6. Staging profile

Staging verifies the artifact and production-like configuration before release. It should mirror production's topology, TLS, authentication, proxies, and dependencies while using separate endpoints and identities.

Example `application-staging.yml`:

```yaml
app:
  grpc:
    client:
      inventory:
        target: dns:///inventory.staging.internal:443
        deadline: 2s
        security-mode: tls
        trust-bundle-location: file:/var/run/grpc-certs/staging-ca.pem
    reflection:
      enabled: false
```

The trust bundle path is an example runtime mount; certificate files should not be baked into the image if lifecycle/rotation requires independent updates. When using mTLS, client keys/certificates are supplied by a secret manager or protected volume and never committed to source control.

Staging should verify:

- TLS chain, SAN, SNI, and ALPN `h2`.
- Real authentication/authorization.
- Deadlines, retries, and load balancing.
- Health Check/Watch, readiness, and graceful shutdown.
- Whether the reflection policy matches expectations.
- Executors, queues, and metrics under production-like load.
- Log redaction and trace correlation.

Do not enable reflection in staging just for debugging convenience if production disables it; staging should verify both the disabled configuration and descriptor-set discovery procedures when needed.

## 7. Production profile

Production prioritizes safety, operability, and predictable behavior. Example `application-prod.yml`:

```yaml
app:
  grpc:
    client:
      inventory:
        target: dns:///inventory.internal:443
        deadline: 1500ms
        security-mode: tls
        trust-bundle-location: file:/var/run/grpc-certs/production-ca.pem
    reflection:
      enabled: false
```

This remains an illustrative `app.grpc.*` configuration. Listener ports, server TLS credentials, server executors, and transport properties must be configured using the actual APIs/properties of the Spring gRPC version in use.

Production needs fail-fast checks:

- Targets must be approved endpoints.
- TLS must be enabled for connections over untrusted networks.
- Trust roots and certificate/key references must exist, have proper permissions, and be valid (not expired).
- Deadlines must be finite and aligned with the latency budget.
- Executors/queues must be bounded; never use unbounded pools to mask overload.
- Reflection disabled, or open only within an approved network/operator boundary.
- Health/readiness must reflect actual ability to serve traffic.
- Logs/traces must not contain tokens, private keys, or sensitive payloads.
- Never silently fall back from TLS to plaintext when certificates fail.

The production profile is not a security boundary. Someone could accidentally activate the `local` profile as well or override a property via environment/command line. Therefore, validation and deployment policies must verify the final effective configuration before accepting traffic.

## 8. Configuring gRPC server and client per profile

### 8.1. Client channel

Channels should be built from validated configuration and lifecycle-managed by Spring:

```java
@Bean(destroyMethod = "shutdown")
ManagedChannel inventoryChannel(
        GrpcApplicationProperties properties,
        ChannelCredentialsFactory credentialsFactory) {

    var config = properties.client().inventory();

    return Grpc.newChannelBuilder(
            config.target(),
            credentialsFactory.forMode(
                    config.securityMode(),
                    config.trustBundleLocation()))
            .build();
}
```

`ChannelCredentialsFactory` is an application-defined abstraction for creating the appropriate credentials, not a built-in gRPC class. In a real implementation, it must distinguish plaintext (allowed environments only), TLS trust roots, and mTLS key material. Never create a new channel per RPC; channels are shared resources and must be shut down when the context stops.

Deadlines are usually set on the stub/call per request, based on shared configuration:

```java
InventoryGrpc.InventoryBlockingStub stub =
        InventoryGrpc.newBlockingStub(inventoryChannel)
                .withDeadlineAfter(
                        properties.client().inventory()
                                .deadline().toMillis(),
                        TimeUnit.MILLISECONDS);
```

In real code, inject per-client configuration into the stub factory, and do not use a single long deadline for every method when SLAs differ.

### 8.2. Server listener

The server listener is managed by the Spring gRPC starter. Configure server port, TLS credentials, executor, and service registration via the properties or builder customization published for your exact starter version.

Some settings are transport-level, while others are application-level:

| Configuration | Owning layer |
| --- | --- |
| Listen port, TLS key/certificate, client auth | gRPC server transport/factory |
| Server callback executor | gRPC `ServerBuilder`/transport |
| Business worker pool | Spring application executor |
| `@GrpcService` registration | Spring gRPC service integration |
| Health/reflection service | gRPC service registration |
| Client target, credentials, deadline | gRPC `ManagedChannel`/stub |
| Business feature toggle | Application configuration |

Do not assume the servlet container's `server.ssl.*` automatically configures a native gRPC listener. Similarly, an `Executor` or `ServerInterceptor` bean is not automatically attached to the gRPC server unless registered through an extension point.

## 9. Secrets and external configuration

Keep reviewable configuration in source control; supply secrets at runtime:

| Data | How to manage |
| --- | --- |
| Target host, deadline, feature toggle | Config file/environment |
| CA public certificate | Config artifact or verified mounted trust bundle |
| Server private key | Secret manager/secure volume |
| Client private key and mTLS certificate | Secret manager/secure volume |
| Bearer token/API credential | Secret provider or workload identity |
| Keystore password | Secret manager, never committed |
| Profile activation | Deployment environment/argument |

Spring Boot supports externalized configuration and config tree imports for secrets mounted as files. Use config trees when the deployment platform provides a secret directory; verify filenames, access permissions, and property binding. Never expose the entire `Environment` or Actuator `env` endpoint publicly; configuration endpoints can leak sensitive data if unprotected.

During secret rotation, determine whether running channels/servers hold the old TLS context or support reloading. Replacing a file does not mean credentials have been reloaded; you may need to recreate channels or perform a controlled rolling restart of servers.

## 10. Activating profiles in containers and deployments

In Docker/Kubernetes or similar platforms, profiles should be passed from deployment configuration:

```yaml
env:
  - name: SPRING_PROFILES_ACTIVE
    value: production
```

This snippet is an example environment setting in a deployment manifest, not a Spring application profile file. Do not bake the production profile as the default into a `Dockerfile` if the same image must run across multiple environments.

Individual properties can be overridden via environment variables under Spring Boot's relaxed binding rules. When using multiple config sources, document which source takes precedence. Avoid defining the same property in a ConfigMap, environment variable, command line, and profile file with different values and no clear convention.

At startup, log the active profiles and non-sensitive configuration such as normalized targets, TLS mode, deadlines, and whether reflection is enabled. Never log private certificate material, passwords, or tokens. If production configuration fails validation, the application should fail startup rather than falling back to local defaults.

## 11. Testing each profile

A solid test strategy verifies both configuration contents and behavior after Spring creates beans/channels/servers.

| Test | How to run | What to prove |
| --- | --- | --- |
| Local context | Initialize with `local` profile | Local targets, dev reflection settings |
| Test context | `@ActiveProfiles("test")` | Fake/in-process dependencies and test deadlines |
| Staging smoke test | Deploy artifact with `staging` profile | TLS, auth, health, downstream routing |
| Production config validation | Load production config in tests | No plaintext, no missing trust bundle, reflection per policy |
| Override precedence | Set environment/property overrides | Final value matches the higher-precedence source |
| Missing secret | Omit required trust bundle/credential | Fail-fast startup |
| Wrong hostname | Use test certificate with wrong SAN | TLS handshake/hostname verification fails |
| Channel lifecycle | Close Spring context | `ManagedChannel` shuts down cleanly |
| Server lifecycle | Stop application | Health `NOT_SERVING`, server drains and shuts down |

Use `ApplicationContextRunner` to test configuration properties and bean conditions without starting the full application. Use `@SpringBootTest` when verifying server/channel wiring. For staging, run smoke tests against the real deployed endpoint rather than relying solely on test contexts.

### 11.1. Verifying final effective configuration

Check the bound values after all property sources are loaded:

- Active profiles.
- gRPC target and port.
- Security mode/TLS enabled.
- Existence of referenced trust bundles.
- Deadlines and timeouts.
- Executor max threads/queue capacity.
- Health/reflection policy.
- Feature flags affecting RPC behavior.

Do not expose full configuration through public endpoints. Create a filtered startup summary or health diagnostic containing only minimal status.

## 12. Common errors and solutions

| Symptom | Cause | Solution |
| --- | --- | --- |
| Local app accidentally points to production | `application.yml` contains live environment endpoints | Put safe local targets in `application-local.yml` and check startup summary |
| Staging runs plaintext | Profile not activated or property overridden | Check active profiles and property source precedence; fail-fast if TLS is off |
| Production cannot find CA bundle | Secret mounted at wrong path/permissions | Validate file reference and mount before creating channels |
| Profile-specific bean missing | Wrong active profile or mismatched `@Profile` condition | Check active profiles and context tests |
| Tests depend on dev services | `application-test` fails to override targets | Use in-process/fake/Testcontainers and assert bean config |
| Bean uses stale values | Config bound before override or custom factory caches incorrectly | Check property source order and bean lifecycle |
| Local profile accidentally active in production | Multiple profiles active or deployment override | Check profile list and policy rejecting disallowed profiles |
| Reflection exposed in production | Shared default enabled reflection or bad override | Default `false`, validate production policy, and inspect listener |
| Channel still uses old CA after rotation | TLS credentials loaded at channel creation | Recreate channel or use a supported reload mechanism |
| HTTP server TLS enabled, but gRPC listener is plaintext | Confused servlet config with native gRPC config | Configure the gRPC server factory/transport properly |
| Executor does not change per profile | Executor bean is unconditional or unconfigured | Bind pool settings and verify the actual instance |
| Secrets appear in logs | Dumping `Environment`/exceptions/config objects | Redact, log an allowlist, and protect Actuator |

## 13. Practice exercises

1. Create `application.yml` with shared configuration: default deadline, observability, and reflection disabled by default.
2. Create `application-local.yml` with `localhost` target, plaintext allowed only for loopback, and reflection enabled.
3. Create `application-test.yml` using in-process/fake downstreams and short deadlines.
4. Create `application-staging.yml` using staging DNS targets, a TLS trust bundle, and reflection disabled.
5. Create `application-prod.yml` with mandatory TLS, runtime trust bundle, finite deadlines, and reflection disabled.
6. Bind `app.grpc.*` using `@ConfigurationProperties` and add validation for target, deadline, and security mode.
7. Use `@Profile` for fake gateways/test adapters while keeping business services shared.
8. Run the same artifact under each profile and review the redacted startup summary.
9. Write a test proving the production profile fails fast if TLS/trust bundle configuration is invalid.
10. Verify that the Spring-managed gRPC listener actually uses the configured port/TLS/executor—not merely that beans exist.
11. Rehearse CA rotation and verify new channels pick up the updated trust bundle.
12. Write a deployment runbook documenting profile activation, config source precedence, secret mounts, and rollback.

### Self-check questions

- How does Spring Boot load `application.yml` and `application-{profile}.yml`?
- How can a profile be activated via environment variables and command-line arguments?
- Why should `spring.profiles.active` not be placed inside a profile-specific document?
- How does `@Profile` differ from `@ConfigurationProperties`?
- Why do the `app.grpc.*` examples require binding and wiring before taking effect?
- How do the goals of `local` and `test` differ?
- Why should `staging` closely match `production` in TLS, auth, and health behavior?
- Is the `production` profile a security boundary?
- Which secrets should be injected at runtime rather than committed to the repository?
- Why does servlet server TLS not prove the native gRPC listener has TLS enabled?
- How do you test fail-fast behavior when production lacks a CA bundle?
- When rotating a CA, why might recreating channels or restarting servers be necessary?

## References

- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): profile activation, profile-specific configuration, and profile groups.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, precedence, and config data.
- [Spring Boot — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binding configuration into typed objects.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): `Environment` and profile conditions.
- [Spring Boot — Config Data Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing): importing external config and config trees.
- [gRPC — Authentication](https://grpc.io/docs/guides/auth/): TLS and credentials for gRPC.
- [gRPC Java — ManagedChannelBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ManagedChannelBuilder.html): channel configuration.
- [gRPC Java — ServerBuilder](https://grpc.github.io/grpc-java/javadoc/io/grpc/ServerBuilder.html): configuring server, executor, and services.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): testing application context and configuration.
- [Spring Boot — Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html): readiness/liveness in the lifecycle.

**Expected outcome:** Learners can organize local, test, staging, and production profiles for Spring gRPC, understand how configuration merges and overrides, bind/validate typed configuration, supply secrets safely, activate the right profile at deployment, and write tests that prevent endpoints, TLS, reflection, or executors from leaking across environments.
