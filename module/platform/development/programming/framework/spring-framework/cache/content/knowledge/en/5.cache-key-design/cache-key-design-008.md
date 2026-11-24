# Immutable Keys, Stable Representations, and Size Bounds in Spring Cache

## 1. Why Is Cache Key Design an Architectural Decision?

In Spring Cache, `@Cacheable` determines how Spring looks up stored results for a method call. Each operation normally binds to the pair **(cache name, key)**: the same cache name and an equivalent key can read back the same entry. If the key does not distinguish enough context, the system can return **wrong data**; if the key varies needlessly, the cache always misses; if the key is too large or has unbounded variants, memory and bandwidth are wasted.

Three essential qualities of a good key:

1. **Immutable:** once computed and placed in the cache, the key's logical identity does not change on its own. Components used in `equals()`/`hashCode()` or the serialized value must be locked in.
2. **Stable representation:** the same logical request always produces the exact same key under a deterministic convention; different requests that affect the result are never merged. The convention must stay consistent across read, write, and eviction methods, across service instances, and across deployments intended to share the cache.
3. **Bounded size:** the key has a predictable length measured in bytes of its actual representation (typically UTF-8), and never allows arbitrary input data to inflate keys without bound.

For example, `findProduct(tenantId, productId, locale)` returns a description by language and tenant. Using only `productId` can cause one product to accidentally fetch another tenant's or language's result. Stuffing the entire HTTP request into the key causes a harmless header to create a brand-new entry.

Key design is the problem of **identifying a function's output**, not merely converting parameters into a string. A valid key satisfies the invariant:

> If two invocations can yield **different results** within the same cache validity window, their keys must be distinguishable; if they are considered business-equivalent, normalization should produce the exact same key.

This rule must be paired with TTL, invalidation, data authorization, and versioning policies. A good key does not guarantee data freshness on its own.

## 2. How Does Spring Generate Default Keys?

Spring Cache uses `org.springframework.cache.interceptor.KeyGenerator`. When no custom `key` (SpEL) or `keyGenerator` is specified, the default `SimpleKeyGenerator` works broadly as follows:

| Parameter count | Default key | What to keep in mind |
| --- | --- | --- |
| 0 | `SimpleKey.EMPTY` | If multiple methods share **one cache name** with no parameters, they risk sharing the same key. |
| 1 | The single argument itself if eligible, or `SimpleKey` for special cases like null/array | Depends on the argument's `equals()/hashCode()` semantics; does not automatically detect hidden tenants, API versions, or external values. |
| 2 or more | `SimpleKey` containing the arguments in order | Compares the argument tuple; still risky if any argument has mutable state. |

Spring's `SimpleKey` does not merely take a 32-bit `hashCode()` as the final identity; for local caches it performs element-wise comparison. Even so, the Javadoc warns that `SimpleKey` objects may not suit **every cache backend**. Do not assume Java key objects are interpreted identically by Redis, Memcached, Caffeine, and various serializers.

**Common boundary confusion:** `SimpleKeyGenerator` does not automatically include the method name, target class, tenant, language, access permissions, or release version in the *key value*. Spring uses the cache name to pick the storage region; if two methods write to the same region with the same key, they can collide logically. Use separate cache names or add an explicit operation identity when sharing a region is needed.

The following examples are **illustrative Spring declarations**, which belong inside a Spring bean with real method bodies:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product findById(String productId) {
    // ...
}

@Cacheable(cacheNames = "productViews", key = "#p0 + ':' + #p1")
public ProductView findLocalized(String productId, String locale) {
    // ...
}
~~~

String concatenation in the second example is easy to read, yet safe only when the delimiter cannot cause ambiguity, fields are normalized, and inputs are bounded. For multiple fields or free-form values, use a length-delimited identifier structure or a dedicated canonical encoder.

## 3. Immutable Keys: The Prerequisite for Accurate Lookups

### 3.1. Why Is Key Mutation After Insertion Dangerous?

A `HashMap`/`ConcurrentHashMap` uses hashes and equality at insertion and lookup time. If a property participating in a key object's `hashCode()` changes after insertion, lookups may fail to find the entry even though that object is still inside the map.

Bug illustration:

~~~java
final class MutableProductKey {
    String tenantId;
    String productId;

    MutableProductKey(String tenantId, String productId) {
        this.tenantId = tenantId;
        this.productId = productId;
    }

    @Override
    public boolean equals(Object other) {
        if (!(other instanceof MutableProductKey k)) return false;
        return java.util.Objects.equals(tenantId, k.tenantId)
                && java.util.Objects.equals(productId, k.productId);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hash(tenantId, productId);
    }
}
~~~

This is an **illustrative class** (no `main`). If an instance is placed in a cache/map and `productId` is later modified, the hash value is no longer stable. The problem is not just a miss: the old entry can linger until eviction, bloating the cache and making invalidation unpredictable. Mutating fields of an object cached as a **value** is a separate issue; this lesson focuses on **key** identity.

### 3.2. Using Records, Final Fields, and Snapshots Properly

Java 17 `record` fits keys holding immutable values such as `String`, `int`, `UUID`, or `Instant`. A record auto-generates `equals()/hashCode()` from its components and prevents reassigning component references. However, a record is only immutable at the **reference level** and does not freeze objects inside:

~~~java
record BadKey(String tenant, java.util.List<String> filters) {}

var filters = new java.util.ArrayList<String>();
filters.add("active");
var key = new BadKey("tenant-a", filters);
filters.add("draft");  // key.filters() changes too
~~~

This snippet solely demonstrates shallow immutability bugs; it is an excerpt from a method, not a standalone file. Use `List.copyOf(filters)` in the constructor to take a snapshot. For `List<MutableFilter>`, copying the list still retains mutable elements: each element must be converted to an immutable value or deep-copied.

Practical rules:

- Freeze **all identity-defining fields** before calling the cache; avoid directly passing mutating JPA entities, request builders, `Date`, or mutable `List`s.
- `String`, primitive wrappers, `UUID`, and immutable value objects are easy to control. For arrays, copy the data and use proper content equality rather than relying on `Object.equals()` for arrays.
- Do not put time-varying values such as `System.currentTimeMillis()`, per-call random UUIDs, fresh session tokens, or request timestamps into keys unless they are genuinely part of the output's identity.
- Do not abuse an object's `toString()` as a key: default `Class@hash` depends on identity; IDE-generated formats can change during refactoring or expose sensitive data in logs.
- To use a record directly with an in-memory cache, the key must have durable `equals()/hashCode()`. For distributed caches, also design a stable **wire format** so serializers on all nodes follow the exact same convention.

## 4. Stable Representation and Input Normalization

### 4.1. Define the Schema Before Writing Code

Consider an operation returning results for a tenant/product/locale tuple and a set of tags:

| Field | Included in key? | Example rule |
| --- | --- | --- |
| Operation/version | Yes | `catalog.query:v1`, fixed by contract. |
| `tenantId` | Yes | Keep the exact authenticated tenant identity; never take it arbitrarily from untrusted caller data. |
| `sku` | Yes | If SKUs are case-sensitive, **do not** auto-lowercase. Strip whitespace only when outer spaces have no business meaning. |
| `locale` | Yes | Normalize to BCP 47 language tags, e.g., `vi-VN`. |
| `tags` | Yes if it affects output | Sort and deduplicate **only when** tags form an unordered *set*. |
| Trace ID, logging-only headers | No | If output does not depend on them, adding them to the key only lowers hit rate. |
| Access permissions/data partitioning | Yes if it affects output | Usually separated via tenant or an authorization scope/version; never use raw sensitive details. |

The system must define precisely **when two requests are equivalent**. For instance, `"SKU-A"` and `"sku-a"` can collapse to the same key only if the business domain treats them as one code. Sorting `tags` is valid only when order does not affect output computation. A wrong normalization rule can be more dangerous than no normalization.

### 4.2. Collisions from Ambiguous Encoding

Insufficiently delimited string concatenation can cause collisions:

- `"ab" + "c"` and `"a" + "bc"` both become `"abc"`.
- Joining with `":"` can still be ambiguous if a field contains `":"`, unless properly escaped with a unique decoding algorithm.
- `null`, empty string `""`, the string `"null"`, an absent field, and a default value may represent distinct business states.
- Numbers `1`, `1.0`, and `1.00`; timestamps at the same instant in different timezones; decomposed vs. precomposed Unicode characters; entry ordering in a `HashMap` can all yield different representations.

Usable encoding approaches:

1. **Immutable value objects** as keys in local caches, with business-accurate equality.
2. **Structured binary formats** with fixed field order and explicit field lengths. For example, encode each string as `4-byte length (big-endian) + UTF-8 bytes`. Distinguishes every pair of values even with delimiters or Unicode characters.
3. **Canonical JSON** following one unified specification if all nodes and languages support it: field order, number types, `null`, escaping, and Unicode must follow identical rules. Default JSON serialization from two libraries is not guaranteed to be byte-for-byte identical.
4. **Digest of canonical data** when a fixed-size key is desired: `namespace:version:hex(SHA-256(canonicalBytes))`. Normalize first, then hash.

Never use `Object.hashCode()`, `Objects.hash(...)`, or 32-bit `String.hashCode()` as a **unique distributed identifier**. They are hashes designed for Java data structures, not collision-resistant fingerprints for a large key store. `equals()` is still required to distinguish hash-colliding keys in local maps.

### 4.3. Schemas Must Be Versioned

Even when a digest has fixed length, changing normalization rules or field order changes the digest for the same request. Declaring a namespace/version such as `catalog:query:v1:...` separates keys before and after algorithm changes.

During rolling deployments where multiple application versions share a cache, account for upgraded and non-upgraded nodes. Avoid letting v1 and v2 accidentally share a prefix while interpreting keys differently. You can let the old version expire naturally via TTL, proactively clear the corresponding cache region, or switch to a new cache name; choose based on consistency targets and cache warm-up cost.

## 5. Size Bounds: Byte Count Matters More Than Character Count

Keys are used in lookups, network transfers, serialization, logs/metrics, and provider metadata storage. Even when a backend permits very long keys, multi-kilobyte keys waste memory, bandwidth, and comparison CPU, hurting cache efficiency.

**Spring Cache imposes no universal character limit.** Practical limits depend on the `Cache` implementation, serializer, and backend. Therefore, set an explicit budget for your system and measure **UTF-8 byte length** after encoding:

~~~java
int byteCount = key.getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
if (byteCount > 128) {
    throw new IllegalArgumentException("Cache key exceeds 128-byte policy");
}
~~~

This is an **illustrative code snippet**, where `key` is a pre-built string. The `128-byte` threshold is merely an **example application budget**, not a mandatory limit from Spring or Redis. A Vietnamese character can take multiple UTF-8 bytes; measuring with `String.length()` will not accurately reflect transmission/storage size.

If a key consists of a namespace and a hex-encoded SHA-256 hash, the size is fixed: e.g., `catalog:query:v1:` (17 ASCII bytes) + digest (64 ASCII bytes) = **81 UTF-8 bytes**. Using unpadded Base64URL gives 43 ASCII characters for SHA-256, provided every node agrees on one format. Also consider any cache-name prefix overhead the backend automatically prepends to physical keys.

**Hashing only bounds output size.** It does not solve reading/normalizing huge input payloads: you must bound field count, per-field length, total canonical byte size, and distinct key combinations (*cardinality*). If every request includes a random string, even a 64-character digest still creates a new entry on every call.

### Trade-offs Between Raw Keys and Hashed Keys

| Criterion | Human-readable field string | Digest-based key |
| --- | --- | --- |
| Manual debugging | Easy to spot tenant/id/filters if unredacted | Requires a tool to recompute the fingerprint from normalized inputs |
| Length | Grows with input data | Nearly fixed |
| Data sensitivity | Easily leaks info in Redis monitors/logs | Avoids storing raw content directly, yet hashing is **not secret encryption** |
| Collision risk | Depends on escaping/encoding design | SHA-256 has negligible collision probability, though theoretically non-zero |
| Schema changes | Must be versioned | Also must be versioned |
| CPU cost | Serialize + transmit string | Serialize + compute digest; usually acceptable when inputs are bounded |

Do not confuse plain SHA-256 with PII protection: for small input domains (common emails, guessable IDs), anyone observing keys can mount a dictionary attack. When key guessing must be mitigated, consider **HMAC-SHA-256** with securely managed secrets, explicitly versioned rotation, and never logging raw inputs. HMAC does not replace authorization checks.

## 6. Standalone Java 17+ Example: Snapshots, Canonical Encoding, and an 81-Byte Key

This program uses **standard Java with no Spring dependencies** to test the core key design. Afterward, `cacheKey(...)` can be called from a Spring `KeyGenerator`. Place the full file at `CacheKeyDemo.java`:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public final class CacheKeyDemo {
    private static final int MAX_FIELD_BYTES = 2_048;
    private static final int MAX_CANONICAL_BYTES = 8_192;
    private static final int MAX_KEY_BYTES = 128;
    private static final String KEY_PREFIX = "catalog:query:v1:";

    private CacheKeyDemo() {}

    // This is the logical identity of the request, frozen upon creation.
    public record CatalogQuery(
            String tenantId, String sku, String locale, List<String> tags) {

        public CatalogQuery {
            tenantId = required(tenantId, "tenantId");
            sku = required(sku, "sku");

            String languageTag = required(locale, "locale");
            locale = Locale.forLanguageTag(languageTag).toLanguageTag();
            if ("und".equals(locale)) {
                throw new IllegalArgumentException("Invalid locale");
            }

            // In this example, tags is a SET: order and duplicates do not matter.
            tags = List.copyOf(
                    Objects.requireNonNull(tags, "tags")
                           .stream()
                           .map(tag -> required(tag, "tag"))
                           .distinct()
                           .sorted()
                           .toList()
            );
        }
    }

    private static String required(String value, String field) {
        Objects.requireNonNull(value, field);
        String clean = value.strip();
        if (clean.isEmpty()) {
            throw new IllegalArgumentException(field + " must not be blank");
        }
        return clean;
    }

    private static void writeText(DataOutputStream output, String value)
            throws IOException {
        byte[] utf8 = value.getBytes(StandardCharsets.UTF_8);
        if (utf8.length > MAX_FIELD_BYTES) {
            throw new IllegalArgumentException("Input field too large");
        }
        output.writeInt(utf8.length); // 4-byte big-endian
        output.write(utf8);
    }

    private static byte[] canonicalBytes(CatalogQuery q) {
        Objects.requireNonNull(q, "query");
        try {
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            try (DataOutputStream output = new DataOutputStream(buffer)) {
                // Field order and types are part of the protocol.
                writeText(output, "catalog.query.v1");
                writeText(output, q.tenantId());
                writeText(output, q.sku());
                writeText(output, q.locale());
                output.writeInt(q.tags().size());
                for (String tag : q.tags()) {
                    writeText(output, tag);
                }
            }
            byte[] bytes = buffer.toByteArray();
            if (bytes.length > MAX_CANONICAL_BYTES) {
                throw new IllegalArgumentException("Canonical input too large");
            }
            return bytes;
        } catch (IOException e) {
            throw new IllegalStateException("Cannot encode cache key", e);
        }
    }

    private static byte[] sha256(byte[] value) {
        try {
            return MessageDigest.getInstance("SHA-256").digest(value);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    public static String cacheKey(CatalogQuery query) {
        String result = KEY_PREFIX
                + HexFormat.of().formatHex(sha256(canonicalBytes(query)));
        if (result.getBytes(StandardCharsets.UTF_8).length > MAX_KEY_BYTES) {
            throw new IllegalArgumentException("Cache key too long");
        }
        return result;
    }

    public static void main(String[] args) {
        var sourceTags = new ArrayList<>(List.of("sale", "new"));
        var first = new CatalogQuery(
                "tenant-A", "SKU-42", "vi-VN", sourceTags);
        String key1 = cacheKey(first);

        System.out.println("tags: " + first.tags());

        var same = new CatalogQuery(
                "tenant-A", "SKU-42", "vi-VN", List.of("new", "sale"));
        System.out.println("same logical key: "
                + key1.equals(cacheKey(same)));

        sourceTags.add("vip");
        System.out.println("stable after caller mutation: "
                + key1.equals(cacheKey(first)));

        var anotherTenant = new CatalogQuery(
                "tenant-B", "SKU-42", "vi-VN", List.of("new", "sale"));
        System.out.println("different tenant: "
                + !key1.equals(cacheKey(anotherTenant)));

        System.out.println("UTF-8 bytes: "
                + key1.getBytes(StandardCharsets.UTF_8).length);
    }
}
~~~

Compile and run inside the directory containing the file:

~~~bash
javac --release 17 -encoding UTF-8 CacheKeyDemo.java
java CacheKeyDemo
~~~

Output in exact order:

~~~text
tags: [new, sale]
same logical key: true
stable after caller mutation: true
different tenant: true
UTF-8 bytes: 81
~~~

**Why is the example stable?**

- `CatalogQuery` stores a sorted/deduplicated `List<String>` snapshot. Modifying `sourceTags` afterward does not alter the generated key.
- Tenant, SKU, locale, tags, and version are encoded in fixed order. Each string carries its own byte length, preventing delimiter ambiguity.
- `DataOutputStream.writeInt` uses big-endian; `String.getBytes(UTF_8)` produces UTF-8 bytes. This is a **concrete encoding contract** implementable across processes and languages.
- SHA-256 turns the canonical identity into a 32-byte digest; `HexFormat` yields 64 hex characters, and the prefix brings the total to 81 bytes.
- The example bounds each field to 2,048 bytes, canonical input to 8,192 bytes, and keys to 128 bytes. Adjust these thresholds to real requirements; they are not Spring defaults.
- `strip()` and treating `tags` as a set are **business decisions of this example**. If whitespace or tag ordering becomes meaningful, change the schema and bump the version.

**Note on immutability:** the final key is an immutable `String`. `CatalogQuery` holds only `String`s and an immutable list of `String`s. With mutable nested objects, convert them into truly immutable representations before putting them into the record. For data mutated while building a request, take the snapshot after all normalization steps have completed.

## 7. Wiring Key Rules into Spring Cache

There are two common ways:

- **SpEL `key`:** fits a few simple fields with pre-normalized representations, e.g., `key = "#p0.tenantId() + ':' + #p0.sku()"` when delimiter rules are genuinely safe in that domain.
- **`KeyGenerator` bean:** fits multi-field schemas, canonical encoding, digests, byte-length enforcement, and shared conventions across methods.

The configuration sample below **illustrates integration**, assuming the application already has `CacheKeyDemo.CatalogQuery`/`CacheKeyDemo.cacheKey(...)` from Section 6 and a `repository`/`CatalogView` domain model. Move helper classes into your application package in a real Spring deployment.

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalogViews");
    }

    @Bean("catalogQueryKeyGenerator")
    KeyGenerator catalogQueryKeyGenerator() {
        return (target, method, params) -> {
            if (params.length != 1
                    || !(params[0] instanceof CacheKeyDemo.CatalogQuery q)) {
                throw new IllegalArgumentException(
                        "Expected exactly one CatalogQuery");
            }
            return CacheKeyDemo.cacheKey(q);
        };
    }
}
~~~

Example service using **the exact same key contract** for reads and invalidation:

~~~java
@Cacheable(cacheNames = "catalogViews",
           keyGenerator = "catalogQueryKeyGenerator")
public CatalogView load(CacheKeyDemo.CatalogQuery query) {
    return repository.load(query);
}

@CacheEvict(cacheNames = "catalogViews",
            keyGenerator = "catalogQueryKeyGenerator")
public void invalidate(CacheKeyDemo.CatalogQuery query) {
    // Triggers eviction after business processing succeeds.
}
~~~

The two service methods above are **snippets** that must reside in a Spring-managed bean with a real `repository` and `CatalogView`; they cannot be compiled standalone. If using `@CachePut` to refresh the same entry, it must also use the same cache name and exact key logic.

Checkpoints during integration:

1. `@EnableCaching` is configured; methods are invoked **through the Spring AOP proxy** (self-invocation normally bypasses cache advice in proxy mode).
2. Do not specify `key` and `keyGenerator` simultaneously on the same annotation; Spring treats them as mutually exclusive.
3. `@Cacheable`, `@CachePut`, and `@CacheEvict` follow the same contract when operating on the same entry. Do not use `tenant:sku` on one method and only `sku` on another while expecting eviction to work.
4. `CacheManager`/`CacheResolver` must point to the right cache. The example uses `ConcurrentMapCacheManager` in the same process. With Redis or other backends, verify serializers, key prefixes, TTLs, and size limits.
5. `KeyGenerator` receives `target`, `method`, and `params`; if shared across multiple methods, it may need controlled method identity or per-operation configuration. Do not blindly use `method.toString()`, as reflection strings can vary across signatures/versions.

One advantage of a **dedicated key schema** is that read, update, and eviction callers use one shared contract. The trade-off is needing deliberate migrations whenever that contract changes.

## 8. Designing for Multiple Instances and Cache Backends

### 8.1. Local Cache vs. Distributed Cache

With `ConcurrentMapCache`, key objects are compared in a map via `equals()/hashCode()` within one JVM. With Redis, the final key must be converted to bytes. Some providers concatenate the cache name with the key, use `toString()`, use a configured serializer, or apply other strategies. **There is no guarantee** that two key objects equal in the JVM will always serialize to identical bytes across serializers.

To share caches across service instances:

- Use the same schema/version and charset (typically UTF-8).
- Pin down normalization, number/time formatting, locale, `null`, sorting, endianness, field lengths, and hashing.
- Ensure the same implementation/key policy is deployed across concurrently serving versions.
- Use regression integration tests comparing exact bytes/hex against fixed test vectors across versions. Test read/put/evict keys, especially during rollbacks.
- Never use `System.identityHashCode()`, default `Object.toString()`, or Java object identity as distributed keys.

### 8.2. Cardinality and Cache Pollution

Even an 81-byte key can overload a cache if every input produces a fresh value. For example, queries containing microsecond timestamps or `traceId` will yield virtually zero hits. Conversely, dropping an important filter to lower cardinality can return incorrect results.

Balancing workflow: identify dimensions that genuinely affect output → freeze/normalize meaningful dimensions → bound lengths and allowed values → decide whether edge-case inputs should even be cached → measure hit/miss rates, entry counts, and eviction rates. For queries with huge combinatorial spaces, some endpoints are better off **uncached** rather than forcing a key.

### 8.3. Security and Multi-Tenancy

Tenants must be distinguished in keys if a cache region holds multiple tenants. However, keys do not replace authentication and authorization checks inside business methods or the service layer. For user data, avoid putting raw emails, access tokens, government IDs, or private details verbatim into keys/logs/metrics. Use non-sensitive internal IDs, HMAC over canonical data, or per-scope caches depending on required protection.

Do not turn keys into a secret-transport mechanism. If using HMAC, secrets and key rotation versions must be synchronized across nodes; changing the secret makes new keys unable to read old entries and requires a migration/TTL plan. Adding a random salt per call destroys stability.

## 9. Key Testing Strategy Before Deployment

Do not check only `hashCode()` or a single cache hit. Verify the following properties:

| Property | Test data | Expectation |
| --- | --- | --- |
| Determinism | Call generator twice with identical input | Byte-for-byte identical keys |
| Business equality | Reordered tags when tags are a set | Same key |
| Context isolation | Change tenant, SKU, locale, or output-affecting filter | Different key |
| Defensive copy | Mutate original list after constructing record | Snapshot's key remains unchanged |
| Unambiguous encoding | Pairs `("ab","c")` and `("a","bc")` | Different canonical bytes |
| Null/empty | Null, empty, and missing fields | Rejected or encoded distinctly per spec |
| Unicode | Vietnamese characters, emojis, equivalent Unicode forms | Proper normalization rules and UTF-8 byte lengths |
| Length bounds | Field exceeding limit, too many tags | Rejected before creating backend key |
| Cross-node | Same input run on two supported nodes/versions | Same bytes and namespace |
| Eviction symmetry | `@Cacheable` and `@CacheEvict` for the same identity | Evicts the right entry |
| Schema migration | v1 and v2 | Never accidentally reuses incompatible keys |
| Provider compatibility | Local map, Redis/remote serializer | Lookup/put/evict work under chosen format |

With Java 17, run the Section 6 example to verify the three baseline cases. In Spring tests, enable `@EnableCaching`, fetch the service from the application context, call it twice, and count actual method executions. Remote backend tests should compare *serialized key bytes* or actual provider keys rather than Java objects alone.

**Fixed test vectors** are especially valuable: pick an immutable input set and record exact canonical bytes/digests in unit tests. If someone accidentally alters `strip`, tag sorting, charset, or version, the test catches it immediately. When intentionally changing conventions, update both the schema version and the old-data invalidation plan.

## 10. Common Mistakes and Fixes

**Mistake 1 — Passing a mutable DTO/array as a key.** The DTO mutates after insertion; arrays have unexpected equality. Fix: snapshot into an immutable value object; convert arrays to immutable value lists or encode contents explicitly.

**Mistake 2 — Using only `productId` when output depends on tenant/locale/permissions.** Two calls can share a cached entry. Fix: list every dimension affecting output, attach proper security scope, and test varying each dimension.

**Mistake 3 — Concatenating keys with unescaped delimiters.** Different field pairs can produce the same string. Fix: length-prefixed encoding, structured canonical formats, or standard escaping tested with special characters.

**Mistake 4 — Relying on `toString()` or Java `hashCode()`.** Strings may omit full identity or hashes may be too short. Fix: explicit schema + UTF-8 + cryptographic digest when fixed length is needed.

**Mistake 5 — Inconsistent encoding across nodes.** Map ordering, OS locale, default timezone, serializers, and releases alter keys. Fix: specify exact canonical representation independent of default locale/timezone, add versioning, and test byte-for-byte.

**Mistake 6 — Hashing arbitrary unbounded inputs.** The output key is short, yet every request must parse/hash huge payloads and the cache still explodes in entry count. Fix: validate input limits, field counts, combinations, and cacheability **before** hashing.

**Mistake 7 — Putting raw PII in keys "for debugging".** Keys can surface in logs/providers. Fix: never log raw secrets, pick safe scopes/IDs or HMAC when needed, and restrict cache access.

**Mistake 8 — Changing key generation logic without versioning.** Cache misses spike, evictions miss old entries, or old schemas are misinterpreted. Fix: version prefixes and transition/clear/TTL strategies.

**Mistake 9 — Oversized cache entries despite tiny keys.** Key limits only govern identifiers; **value** size and entry count are separate budgets. Fix: monitor cache memory, max entries, payload sizes, and provider eviction policies.

**Mistake 10 — Assuming hashing means zero collisions and automatic security.** Finite digests still have theoretical collision risk; plain SHA-256 is guessable on small input domains. Fix: choose sufficiently strong digests and HMAC when dictionary resistance is required; evaluate collision risk policies.

## 11. Checklist for Designing a New Key

Before adding `@Cacheable` to a method, answer:

1. What causes **outputs to differ** within the TTL window? Are there tenant, locale, feature flag, authorization scope, sorting, pagination, model version, or data revision factors?
2. Which parameters truly define identity? Are rules for null, blank, case sensitivity, numbers, timezones, Unicode, and collections settled?
3. Is the key immutable, including elements inside records/lists/maps and third-party objects?
4. Does the format have explicit escaping/length-prefixing, versioning, and namespacing? Do all nodes produce identical bytes?
5. What is the actual **byte** length of the key, what is the budget, and what overhead does the provider add? What are maximum input size and maximum cardinality?
6. Do `@CachePut`/`@CacheEvict`/invalidation jobs produce the exact same key? Is there a plan when the schema changes?
7. Could the key leak private info, secrets, or enable cross-tenant access?
8. Are there unit tests, fixed test vectors, and integration tests against the real backend?

## 12. References

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): default keys, custom `key` and `keyGenerator`, annotation policies.
- [SimpleKeyGenerator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html): argument/`SimpleKey` return rules and provider suitability.
- [SimpleKey Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKey.html): compound key object, equality, and hashing.
- [KeyGenerator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/KeyGenerator.html): contract for generating keys from target, method, and parameters.
- [Java SE 17 — MessageDigest](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/MessageDigest.html), [HexFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html), and [DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html): foundations for building canonical representations with predictable size.

**Guiding rule:** identify business identity → take immutable snapshot → normalize per contract → encode unambiguously with versioning → bound inputs and keys by bytes → use the same contract for get/put/evict → test on the real backend.
