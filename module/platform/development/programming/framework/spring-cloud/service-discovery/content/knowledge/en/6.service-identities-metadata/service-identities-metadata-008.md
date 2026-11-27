# Metadata Size Limits and What Should Not Be Published

## Objectives

After this lesson, you will be able to:

- Explain what instance metadata is used for in service discovery.
- Recognize why metadata must remain small, stable, structured, and bounded in cardinality.
- Identify sensitive data or data unsuitable for publishing in a registry.
- Establish key/value conventions, size budgets, and validate metadata prior to registration.
- Choose appropriate storage for secrets, business configuration, and large data.

## 1. What Is Metadata in Service Discovery?

A service registry stores information about services and the instances providing them. Beyond service ID, instance ID, hostname, port, and status, some registries allow attaching metadata so consumers better understand instance characteristics.

In Spring Cloud, `ServiceInstance` provides `getMetadata()` as a string-typed key/value map. With Eureka, metadata is typically configured via `eureka.instance.metadata-map`. Other implementations may have different conventions, limits, and synchronization behavior.

Metadata is useful when consumers or infrastructure need to make decisions based on stable attributes, for example:

- Deployment region or zone: `region=ap-southeast-1`, `zone=hcm-a`.
- API version supported by the instance: `api-version=v2`.
- Connection protocol or format: `protocol=https`.
- Controlled capability group: `capability=inventory-read`.
- Rollout label: `release-track=canary`.

Metadata does not replace connection addresses, health checks, service IDs, or authorization mechanisms. It is supplementary information enabling discovery consumers to understand an instance and apply appropriate policies.

Eureka configuration example:

~~~~yaml
eureka:
  instance:
    metadata-map:
      region: ap-southeast-1
      zone: hcm-a
      api-version: v2
      protocol: https
      release-track: stable
~~~~

Publish only the keys that consumers actually use. If no consumer or operational workflow needs an attribute, consider omitting it.

## 2. Why Must Metadata Be Small and Bounded?

Metadata is typically transmitted alongside registration details or returned in discovery payloads. The registry may persist, replicate, cache, serialize, and distribute that data to many clients. Consequently, the larger and more frequently changing metadata becomes, the higher the transport, memory, processing, and synchronization overhead.

Common problems:

- **Large payloads:** long JSON strings, multi-paragraph descriptions, or embedded configuration bloat registration and registry response sizes.
- **Unnecessary keys:** every key increases storage, serialization, parsing, and provider-consumer contract maintenance overhead.
- **Repeated values:** identical values across every instance force the registry to carry data consumers could obtain from shared configuration.
- **Frequent updates:** metadata changing per request, user, or short-lived state forces the registry to process unnecessary churn.
- **High cardinality:** generating distinct keys/values per request, user, tenant, or transaction causes variants to grow rapidly and hurts caching, metrics, search, and operations.
- **Fragile compatibility:** embedding arbitrary JSON structures in a string forces consumers to parse an implicit schema that breaks easily when the provider changes.

There is no single size limit that applies across all Spring Cloud implementations and all registries. Practical limits can come from registry APIs, HTTP server request/response limits, reverse proxies, ingress controllers, storage limits, serialization, or platform policies. A value accepted in development is not guaranteed to be suitable for production.

Therefore, the development team should define the system's own metadata budget, validate it on both the provider side and the deployment pipeline, and check the official limits of the registry in use.

## 3. Designing a Size Budget

A simple policy can specify:

| Component | Internal Budget Example |
| --- | --- |
| Number of keys per instance | Up to 10 keys |
| Key length | Up to 64 UTF-8 bytes |
| Value length | Up to 256 UTF-8 bytes |
| Total keys and values | Up to 2 KiB UTF-8 per instance |
| Data type | Short strings with agreed format and semantics |
| Change frequency | Changes only when instance attributes actually change |

The numbers above are only an example of an internal policy to begin reviews; they are not default limits of Eureka, Consul, or Spring Cloud. Adjust them based on instance count, registry response size, refresh frequency, transport limits, and product requirements.

Measure in UTF-8 bytes rather than character count. A single Unicode character can occupy multiple bytes. Total size should account for keys, values, and serialization overhead when comparing against actual request/response limits.

The budget should also leave headroom for new keys in future upgrades. Avoid exhausting the entire transport limit on a single instance's metadata.

## 4. Choosing Valuable Metadata

Good metadata generally has the following traits:

- **Small:** short keys, short values, no paragraphs or large payloads.
- **Stable:** changes only when deployment attributes or instance capabilities change.
- **Structured:** standardized key naming, validated value formats.
- **Purposeful:** consumed by at least one consumer or operational workflow.
- **Clearly scoped:** specifies whether the attribute applies to the instance, service, or environment.
- **Compatible:** consumers ignore unknown keys and have sensible defaults when optional keys are absent.

Example namespaced keys to avoid collisions:

~~~~yaml
eureka:
  instance:
    metadata-map:
      platform.region: ap-southeast-1
      platform.zone: hcm-a
      contract.api-version: v2
      rollout.track: stable
~~~~

Key conventions should be documented: name, type/format, valid values, meaning, owner, and dependent consumers. Avoid using the same key with different meanings across services.

Do not use metadata to hold full application configuration. Consumers needing database addresses, feature flags, or business limits should fetch them from an appropriate configuration system with its own access controls and lifecycle.

## 5. Data That Should Not Be Published in the Registry

Metadata can be returned to clients with registry read access, displayed on dashboards, emitted in logs, or replicated into monitoring systems. Assume that every consumer authorized to read the registry can see instance metadata.

Do not publish the following types of data:

| Data Type | Examples to Exclude from Metadata | More Appropriate Storage |
| --- | --- | --- |
| Authentication secrets | Passwords, API keys, access tokens, refresh tokens, client secrets | Secret manager, Vault, Kubernetes Secrets, or a controlled secrets system |
| Cryptographic keys | Private keys, signing keys, certificate bundles containing private keys | KMS, HSM, or dedicated certificate/secret store |
| Personal data | Emails, phone numbers, addresses, usernames, personal identifiers | Business systems with access control and data protection policies |
| Customer/tenant data | Customer IDs, private tenant IDs, contract or transaction details | Business databases or tenant management systems |
| Session and per-request data | Session IDs, cookies, per-request correlation IDs, personal trace baggage | Session stores, tracing systems, or request context |
| Large payloads | Long JSON configs, lists with thousands of items, file contents | Config server, database, object storage, or dedicated APIs |
| Overly detailed infrastructure info | Sensitive internal topology, admin addresses, hostnames containing secrets | CMDB or access-controlled infrastructure inventory systems |

Never place secrets in metadata and rely on dashboard masking or transport encryption to protect them. TLS protects data in transit; TLS does not restrict who can read metadata once they have access to the registry. Registry authorization and secret managers must still be configured separately.

An instance's IP/hostname and port are a natural part of registration data so consumers can connect. However, publish only addresses reachable by authorized consumers. Do not add admin addresses, debug endpoints, internal paths, or unnecessary network details to metadata.

## 6. Metadata Is Not Storage for Dynamic State

Do not use metadata to publish continuously changing state, for example:

- Current in-flight request count.
- Per-second CPU, memory, or queue depth.
- Number of currently logged-in users.
- Per-order or per-tenant status.
- Short-window error rates.

Such information belongs in metrics, health endpoints, telemetry, or monitoring systems. If a router or load balancer needs to know whether an instance can serve traffic, use health checks and status mechanisms supported by the implementation. Metadata may be cached and does not guarantee real-time freshness.

Nor should you embed secret values or authorization state in metadata and let consumers decide access on their own. Metadata is descriptive data, not authentication proof. Decisions allowing service calls must rely on trustworthy authentication, authorization, and policies.

## 7. Validating Metadata Before Registration

Validate metadata at application startup or before invoking `ServiceRegistry`. The example below illustrates an internal policy with limits on key count, key/value bytes, and total bytes. Numbers must be tuned to your system's rules:

~~~~java
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.regex.Pattern;

public final class MetadataPolicy {

    private static final int MAX_ENTRIES = 10;
    private static final int MAX_KEY_BYTES = 64;
    private static final int MAX_VALUE_BYTES = 256;
    private static final int MAX_TOTAL_BYTES = 2 * 1024;

    private static final Pattern KEY_PATTERN =
            Pattern.compile("[a-zA-Z0-9][a-zA-Z0-9._-]*");

    private MetadataPolicy() {
    }

    public static void validate(Map<String, String> metadata) {
        if (metadata == null) {
            return;
        }

        if (metadata.size() > MAX_ENTRIES) {
            throw new IllegalArgumentException("Too many metadata entries");
        }

        int totalBytes = 0;

        for (Map.Entry<String, String> entry : metadata.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();

            if (key == null || !KEY_PATTERN.matcher(key).matches()) {
                throw new IllegalArgumentException("Invalid metadata key");
            }
            if (value == null) {
                throw new IllegalArgumentException(
                        "Metadata value must not be null");
            }

            int keyBytes = key.getBytes(StandardCharsets.UTF_8).length;
            int valueBytes = value.getBytes(StandardCharsets.UTF_8).length;

            if (keyBytes > MAX_KEY_BYTES) {
                throw new IllegalArgumentException("Metadata key is too large");
            }
            if (valueBytes > MAX_VALUE_BYTES) {
                throw new IllegalArgumentException("Metadata value is too large");
            }

            totalBytes += keyBytes + valueBytes;
            if (totalBytes > MAX_TOTAL_BYTES) {
                throw new IllegalArgumentException(
                        "Metadata exceeds the configured budget");
            }
        }
    }
}
~~~~

The snippet above checks basic structure and size. In production, add a key allowlist, per-key value validation, rejection of sensitive key names, version/zone format checks, and testing against the actual registry. Do not log raw metadata values when validation fails, as those values could contain sensitive information.

A safe registration workflow might include:

1. Construct metadata from controlled configuration.
2. Verify keys are on the allowlist and values match expected formats.
3. Compute UTF-8 byte sizes and check against the budget.
4. Refuse startup or registration if metadata violates policy.
5. Register the instance with the registry.
6. Monitor payload sizes and registration failures in live environments.

## 8. Managing Metadata Changes and Compatibility

Metadata is a contract between providers and consumers. When changing keys or formats, evaluate whether older consumers will continue to work.

Key principles:

- Add new keys in a backward-compatible way; older consumers should ignore unrecognized keys.
- Optional keys must have clear defaults when absent.
- Do not change the meaning of an existing key without a migration plan.
- If a value has multiple schema versions, version it explicitly and limit the number of supported versions.
- Remove keys only after confirming no consumers depend on them.
- Avoid generating dynamic keys on every deployment without a genuine lookup need.

Example of a consumer safely reading metadata:

~~~~java
String apiVersion = instance.getMetadata()
        .getOrDefault("contract.api-version", "v1");

String region = instance.getMetadata()
        .getOrDefault("platform.region", "unknown");
~~~~

Consumers should validate whether values belong to the supported set. Do not blindly trust self-declared provider metadata: an instance can misreport its version, zone, or capabilities. For security requirements, verify workload identity and enforce independent policies.

## 9. Observing and Auditing Metadata

In operations, monitor:

- Average, maximum, and high-percentile metadata size per service.
- Number of keys per instance and count of keys no longer used by any consumer.
- Registration failure rates caused by invalid metadata or oversized payloads.
- Number of value variants/cardinality per key.
- Schema changes and rollout timestamps.
- Unusual registry access or metadata containing prohibited keys.

Periodically audit published keys. When deprecating a key, check whether consumer code, dashboards, routing rules, and automation still reference it. Do not dump entire metadata maps into default logs; log only necessary, approved keys.

## 10. Pre-Publication Metadata Checklist

- [ ] Every key has an explicit consumer or operational purpose.
- [ ] Metadata contains only small, stable, well-formatted descriptive data.
- [ ] Key count, key/value lengths, and total bytes stay within the internal budget.
- [ ] Sizes are measured in UTF-8 bytes, not merely character counts.
- [ ] No passwords, tokens, API keys, private keys, or cookies are included.
- [ ] No personal data, customer IDs, or transaction data are included.
- [ ] No large payloads, unbounded lists, or arbitrary JSON are included.
- [ ] Metadata is not used to replace health checks, metrics, or authorization.
- [ ] The registry is protected by appropriate authentication, authorization, and TLS.
- [ ] Consumers handle optional keys, unknown keys, and invalid values gracefully.
- [ ] Metadata changes have compatibility and rollback plans.

## Key Takeaways

- Metadata supplements service instance information; it does not replace service IDs, endpoints, health checks, or authorization.
- Metadata should be small, stable, structured, purposeful, and bounded in cardinality.
- No single byte limit applies to all registries; check implementation limits and set an internal budget.
- Never publish secrets, private keys, personal data, sessions, customer info, or large payloads.
- Use secret managers for secrets, config servers for configuration, metrics/health for dynamic state, and object storage/databases for large data.
- Validate metadata before registration, control registry read access, and audit consumers when contracts change.
