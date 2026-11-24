# Testing Expressions to Avoid Missing Key Components or Type Mismatches

In Spring Cache, **SpEL** in `@Cacheable`'s **key** attribute determines which calls are allowed to reuse a stored result. An expression can be syntactically valid yet semantically wrong: omitting tenant, currency, or locale; concatenating strings in a way that collides; erasing identifier types; producing null keys; or basing keys on mutable objects. When that happens, a cache hit can return another request's data without running the method body.

The goal of this lesson is **testing the contract of the key expression**, not merely checking whether SpEL parses. Learners will write tests verifying individual dimensions, data types, actual keys, and Spring proxy behavior, while understanding when to test against Redis/Caffeine rather than relying solely on an in-JVM cache.

## 1. What Must a Correct Cache Key Satisfy?

Treat **(cache name, key)** as the unique identifier of a result allowed to be reused in the same context. Before writing tests, identify which inputs genuinely change the result.

For example, **quote(sku, tenantId, currency)** may depend on all three parameters. Invariants to test:

1. **Same context → same key:** Repeating **("P01", "shop-A", "VND")** is allowed to hit the cache.
2. **Changing one result-determining dimension → different key:** Changing only `sku`, only `tenant`, or only `currency` must distinguish entries.
3. **Unrelated parameters do not fragment the cache:** If **traceId** is only for logging, changing `traceId` can keep the same key once excluded from the expression.
4. **Stable key:** Do not use random variables, unnecessary timestamps, object addresses, or mutable DTOs as the identity basis.
5. **Types are not wrongly collapsed:** If **Long 42L** and **String "42"** are two distinct identifiers, the key must preserve that distinction per contract.
6. **Read/write/evict share the same contract:** **@Cacheable**, **@CachePut**, and **@CacheEvict** must target the exact same entry when referring to the same result.

**A high hit ratio does not prove a key is right.** A key based solely on SKU may hit often while returning wrong results across tenants or currencies.

## 2. SpEL Expressions to Understand When Writing Tests

Illustrative example inside a Spring service with a repository, not a standalone Java program:

~~~java
@Cacheable(
    cacheNames = "quotes",
    key = "T(java.util.List).of(#p0, #p1, #p2)"
)
public Quote quote(String sku, String tenantId, String currency) {
    return repository.loadQuote(sku, tenantId, currency);
}
~~~

The call goes through the Spring cache interceptor. **#p0**, **#p1**, and **#p2** are the three parameters by position; **T(java.util.List).of(...)** builds a List key containing three separate elements, suitable for illustrating in a cache storing Java keys. **List.of** rejects null elements and will throw **NullPointerException** if any is null.

| Expression | Meaning | What to Test |
| --- | --- | --- |
| **#p0** or **#a0** | First parameter | Are the second/third parameters omitted? |
| **#p1**, **#p2** | Second, third parameters | After changing method signature, are positions still right? |
| **#root.args[0]** | First parameter via metadata | Right object, right type? |
| **#root.methodName** | Method name | Insufficient to distinguish two classes/overloads sharing a cache |
| **#p0.id** | `id` property of first object | Nulls, getter, uniqueness, remaining fields |
| **#p0?.id** | Null-safe property access | If the result is null, how is the key handled? |
| **'latest'** | String literal in SpEL | Does it collide with another method's constant key? |
| **#p0 + ':' + #p1** | String concatenation | Is it ambiguous when inputs contain **:**? |
| **T(java.util.List).of(#p0, #p1)** | Composite key | Nulls, order, provider serializer |

Parameter names such as **#sku** or **#tenantId** only resolve properly when Spring has Java parameter-name metadata (usually via **-parameters**). **#p0/#p1** do not depend on those names. Never use **#result** to compute **@Cacheable**'s key: the method result does not exist before cache lookup. **unless = "#result == null"** can block storing a result after execution; **condition** can skip caching based on inputs beforehand.

If the **key** attribute is omitted, the default **SimpleKeyGenerator** uses **SimpleKey.EMPTY** for zero parameters, typically the parameter itself for one non-null non-array value, and **SimpleKey(...)** for multiple parameters. Spring does not automatically prepend method/class names to keys. Two methods sharing a cache name must still avoid unintended key collisions.

## 3. Testing Missing Components: Vary Each Dimension Independently

Faulty example:

~~~java
@Cacheable(cacheNames = "quotes", key = "#p0")
public String quote(String sku, String tenant, String currency) {
    return pricingClient.quote(sku, tenant, currency);
}
~~~

Two calls **quote("P01", "shop-A", "VND")** and **quote("P01", "shop-B", "USD")** both generate key **"P01"**. The second call can receive the first call's result despite differing tenant and currency. Changing both tenant and currency together in one test does not prove the expression includes **both**; an expression containing only currency would also pass that test.

Minimum matrix:

| Call Compared to Baseline **(P01, shop-A, VND)** | Expected Key Outcome |
| --- | --- |
| **(P01, shop-A, VND)** repeated | Same key |
| **(P02, shop-A, VND)** | Different key |
| **(P01, shop-B, VND)** | Different key |
| **(P01, shop-A, USD)** | Different key |

Fix with **key = "T(java.util.List).of(#p0, #p1, #p2)"** or use the default key for a three-parameter method when every parameter determines the result. The same applies to `locale`, `includeTax`, `priceTier`, `effectiveDate`, and permission context if they truly affect output. Separating tenant data by key **does not replace authorization checks**.

## 4. Testing Key Collisions from String Concatenation

The expression:

~~~java
@Cacheable(cacheNames = "accounts", key = "#p0 + ':' + #p1")
public String lookup(String tenant, String accountId) {
    return gateway.lookup(tenant, accountId);
}
~~~

can produce the same key for two differently scoped pairs:

~~~text
tenant="a:b", account="c"   => "a:b:c"
tenant="a",   account="b:c" => "a:b:c"
~~~

SpEL parses fine and caching still runs, yet identity is broken. Tests should include delimiters, Unicode, empty strings, and inputs with special normalization rules. You can use a structured key like **T(java.util.List).of(#p0,#p1)** in-JVM, or length-prefixed/explicitly escaped encoding for distributed providers. Simply adding **":"** does not guarantee an unambiguous key.

## 5. Testing Type Mismatches from String Coercion

~~~java
@Cacheable(cacheNames = "ids", key = "'id:' + #p0")
public String lookup(Object id) {
    return repository.lookup(id);
}
~~~

With inputs **42L** (Long) and **"42"** (String), both produce the String key **"id:42"**. If the two identifier types carry different meanings, this is a collision bug. In **ConcurrentMapCache** storing Java keys, **#p0** keeps **Long 42L** and **String "42"** as two distinct keys under **equals**; however, providers like Redis may apply their own key converters/serializers.

~~~text
key="'id:' + #p0"  -> Long 42L   -> "id:42"
key="'id:' + #p0"  -> String "42" -> "id:42"  (collision)

key="#p0" in local Java cache:
Long 42L != String "42"
~~~

Also test **Integer/Long**, **"0012"/"12"**, enum/string, timezone, and **BigDecimal("1.0")/BigDecimal("1.00")**. Normalize only when business rules define the values as equivalent. A key that is right inside the JVM does not guarantee the physical Redis key is also right.

## 6. Testing Layers to Combine

| Level | What It Verifies | Limitations |
| --- | --- | --- |
| Key-function unit test | Distinctness, null/type handling, stability | Does not prove Spring proxy runs annotations |
| Standalone `ExpressionParser` test | Syntax, output given sample variables | Self-built evaluation context may differ from cache interceptor |
| Spring bean integration test | `@Cacheable`, actual key, hit/miss, execution count | Does not verify production Redis/Caffeine config |
| Real provider test | Key converter, serializer, prefix, TTL, multi-instance | Still needs business contract tests |

For critical annotations, test using **beans retrieved from `ApplicationContext`**, observing **cache key**, **output**, and **method body execution count**. Manually creating objects via **new** or self-invoking **this.cachedMethod()** inside the same bean in normal proxy mode will not trigger caching like a call through the Spring proxy.

## 7. Runnable Spring + JUnit 5 Project

The project uses **Java 17**, **Spring Framework 6.1.14**, **JUnit Jupiter 5.10.2**, and **ConcurrentMapCacheManager**. Methods annotated **WRONG** intentionally contain bugs for tests to reproduce, contrasted with **FIX** methods. No database is required; counters increment only when the method body actually runs.

Structure:

~~~text
spel-cache-key-tests/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/keys/CacheKeyConfig.java
└── src/test/java/demo/keys/CacheKeyExpressionTest.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'spel-cache-key-tests'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/keys/CacheKeyConfig.java**:

~~~java
package demo.keys;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheKeyConfig {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
                "unsafeQuotes", "safeQuotes", "ambiguousKeys",
                "tupleKeys", "unsafeTyped", "typedKeys");
    }

    @Bean
    public QuoteService quoteService() {
        return new QuoteService();
    }

    public static class QuoteService {
        private final AtomicInteger bad = new AtomicInteger();
        private final AtomicInteger good = new AtomicInteger();
        private final AtomicInteger ambiguous = new AtomicInteger();
        private final AtomicInteger tuple = new AtomicInteger();
        private final AtomicInteger badType = new AtomicInteger();
        private final AtomicInteger typed = new AtomicInteger();

        // WRONG: Omits tenant and currency.
        @Cacheable(cacheNames = "unsafeQuotes", key = "#p0")
        public String unsafeQuote(String sku, String tenant, String currency) {
            return "bad#" + bad.incrementAndGet()
                    + "/" + sku + "/" + tenant + "/" + currency;
        }

        // FIX: Keeps all three parts distinct.
        @Cacheable(
            cacheNames = "safeQuotes",
            key = "T(java.util.List).of(#p0, #p1, #p2)"
        )
        public String safeQuote(String sku, String tenant, String currency) {
            return "good#" + good.incrementAndGet()
                    + "/" + sku + "/" + tenant + "/" + currency;
        }

        // WRONG: Unescaped delimiter.
        @Cacheable(cacheNames = "ambiguousKeys", key = "#p0 + ':' + #p1")
        public String ambiguous(String tenant, String account) {
            return "amb#" + ambiguous.incrementAndGet()
                    + "/" + tenant + "/" + account;
        }

        // FIX: Keeps both components independent.
        @Cacheable(cacheNames = "tupleKeys", key = "T(java.util.List).of(#p0, #p1)")
        public String tuple(String tenant, String account) {
            return "tuple#" + tuple.incrementAndGet()
                    + "/" + tenant + "/" + account;
        }

        // WRONG: Long 42L and String "42" become the same string.
        @Cacheable(cacheNames = "unsafeTyped", key = "'id:' + #p0")
        public String unsafeTyped(Object id) {
            return "badType#" + badType.incrementAndGet()
                    + "/" + id.getClass().getSimpleName();
        }

        // FIX for local ConcurrentMapCache: preserves original key type.
        @Cacheable(cacheNames = "typedKeys", key = "#p0")
        public String typed(Object id) {
            return "typed#" + typed.incrementAndGet()
                    + "/" + id.getClass().getSimpleName();
        }

        public int unsafeCalls() { return bad.get(); }
        public int safeCalls() { return good.get(); }
        public int ambiguousCalls() { return ambiguous.get(); }
        public int tupleCalls() { return tuple.get(); }
        public int unsafeTypedCalls() { return badType.get(); }
        public int typedCalls() { return typed.get(); }

        public void reset() {
            bad.set(0);
            good.set(0);
            ambiguous.set(0);
            tuple.set(0);
            badType.set(0);
            typed.set(0);
        }
    }
}
~~~

**src/test/java/demo/keys/CacheKeyExpressionTest.java**:

~~~java
package demo.keys;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(CacheKeyConfig.class)
class CacheKeyExpressionTest {

    @Autowired
    CacheKeyConfig.QuoteService service;

    @Autowired
    CacheManager manager;

    @BeforeEach
    void beforeEach() {
        for (String name : List.of(
                "unsafeQuotes", "safeQuotes", "ambiguousKeys",
                "tupleKeys", "unsafeTyped", "typedKeys")) {
            assertNotNull(manager.getCache(name));
            manager.getCache(name).clear();
        }
        service.reset();
    }

    @Test
    void missingTenantAndCurrencyCollide() {
        String a = service.unsafeQuote("P01", "shop-A", "VND");
        String b = service.unsafeQuote("P01", "shop-B", "USD");

        // Test reproducing the intentional bug: two contexts share the same entry.
        assertEquals(a, b);
        assertEquals(1, service.unsafeCalls());
    }

    @Test
    void checksEachDimensionIndependently() {
        String baseline = service.safeQuote("P01", "shop-A", "VND");
        String skuChanged = service.safeQuote("P02", "shop-A", "VND");
        String tenantChanged = service.safeQuote("P01", "shop-B", "VND");
        String currencyChanged = service.safeQuote("P01", "shop-A", "USD");
        String repeated = service.safeQuote("P01", "shop-A", "VND");

        assertNotEquals(baseline, skuChanged);
        assertNotEquals(baseline, tenantChanged);
        assertNotEquals(baseline, currencyChanged);
        assertEquals(baseline, repeated);
        assertEquals(4, service.safeCalls());

        var cache = manager.getCache("safeQuotes");
        assertNotNull(cache.get(List.of("P01", "shop-A", "VND")));
        assertNotNull(cache.get(List.of("P01", "shop-B", "VND")));
        assertNotNull(cache.get(List.of("P01", "shop-A", "USD")));
    }

    @Test
    void delimiterCollisionAndStructuredKey() {
        String a = service.ambiguous("a:b", "c");
        String b = service.ambiguous("a", "b:c");
        assertEquals(a, b);
        assertEquals(1, service.ambiguousCalls());

        String x = service.tuple("a:b", "c");
        String y = service.tuple("a", "b:c");
        assertNotEquals(x, y);
        assertEquals(2, service.tupleCalls());
    }

    @Test
    void stringConversionErasesIdentifierType() {
        String a = service.unsafeTyped(42L);
        String b = service.unsafeTyped("42");
        assertEquals(a, b);
        assertEquals(1, service.unsafeTypedCalls());

        String x = service.typed(42L);
        String y = service.typed("42");
        assertNotEquals(x, y);
        assertEquals(2, service.typedCalls());

        var cache = manager.getCache("typedKeys");
        assertNotNull(cache.get(42L));
        assertNotNull(cache.get("42"));
    }
}
~~~

Run in the project directory with a JDK 17-compatible Gradle (or the project's Gradle wrapper):

~~~bash
gradle test
~~~

**Expected outcome:** JUnit runs **4 tests successfully**, with zero assertion failures. The first test and the "bad" cases intentionally demonstrate buggy expressions causing collisions; they PASS when the bug is accurately reproduced. Detailed output varies by Gradle version/environment, with no fixed stdout. The structure above is a project for learners to create and run; earlier Java snippets are not standalone programs.

Why is this testing close to real behavior? **@SpringJUnitConfig** builds the `ApplicationContext`; **@EnableCaching** activates the interceptor; the service is fetched from Spring so calls pass through the proxy. **@BeforeEach** clears entries and resets counters to keep tests independent. **manager.getCache(...)** lets you inspect the actual key types inside the local cache. This lesson has not yet tested Redis serializers or physical keys in a production cluster.

## 8. Nulls, Object Keys, DTOs, and Other Evaluation Errors

| Expression / Input | Risk to Test |
| --- | --- |
| **#p0.id** with null `p0` | Property access fails |
| **#p0?.id** | Can produce a null key, requiring rejection/skip-cache rules |
| **T(java.util.List).of(#p0, #p1)** with null | **List.of** throws **NullPointerException** |
| **#p0.toString()** | Null or mutable DTO unstable representation |
| **#p0.total + #p1** | Numeric addition, string concatenation, or coercion depending on operand types |
| **#p0.field** when DTO has multiple output-determining fields | Omitting fields can conflate results |
| Object with improper **equals/hashCode** | Equivalent keys split apart, or distinct keys merged |
| Mutable array/collection | Key changes meaning after being stored |
| **BigDecimal("1.0")** and **BigDecimal("1.00")** | Differ under `equals`; normalize only if domain permits |

If null is a valid input, define a key/policy type that explicitly handles null or use **condition** to avoid caching those calls. Never blindly convert null into the string **"null"**, since it can collide with a literal string value. If results depend on tenant/user, authorization checks must still be performed properly in addition to key isolation.

## 9. Symmetry Testing Across `@Cacheable`, `@CachePut`, and `@CacheEvict`

Reading with the right key while updating/evicting with the wrong key still leaves stale data. Example inside a service with a repository:

~~~java
@Cacheable(
    cacheNames = "quotes",
    key = "T(java.util.List).of(#p0, #p1, #p2)"
)
public Quote quote(String sku, String tenant, String currency) {
    return repository.quote(sku, tenant, currency);
}

@CacheEvict(
    cacheNames = "quotes",
    key = "T(java.util.List).of(#p0, #p1, #p2)"
)
public void changePrice(
        String sku, String tenant, String currency, long newPrice) {
    repository.changePrice(sku, tenant, currency, newPrice);
}
~~~

The write method has **four parameters**, whereas the read key has only three. Omitting **key** on **@CacheEvict** would default to a key including **newPrice**, failing to evict the read entry. Tests should follow the flow: read to populate cache → update DB → call write method via Spring → read again → verify the new result and that other entries are unaffected. For **@CachePut**, verify the method returns the final value meant to be cached and uses the same read key rule.

Do not just tweak TTL to mask a wrong key: the newly created entry can still return stale/wrong values. If transactions are involved, whether eviction/update runs before or after commit also needs testing to avoid races that reload uncommitted data.

## 10. Test Matrix to Maintain

| Category | Test Case | Pass Condition |
| --- | --- | --- |
| Valid hit | Same business parameter tuple twice | Method runs only once |
| Varying each dimension | SKU/tenant/currency/locale/variant | Distinct keys whenever output can differ |
| Logging parameter | Varying `traceId`/`correlationId` | Does not create new entries when result is unaffected |
| Separator | Colons `:`, `/`, empty string, Unicode | No ambiguity between two parameter tuples |
| Types | Long/String, Integer/Long, `BigDecimal` scale | Distinguished per business rules |
| Nulls | Null on object/property and tuple element | Skips cache or handles per explicit policy |
| DTOs | Two equivalent value objects, mutable object | Correct and stable identity |
| Cross-method | Two methods sharing cache name/key | Share entries only when semantics match |
| Eviction/put | Read → update → read | Target entry is updated/removed |
| Provider | Additional runs against production-like Redis/Caffeine | Serializer/prefix/physical key match expectations |
| Proxy | Call via bean, verify self-invocation | Know when annotations actually execute |

You can use **parameterized tests** and **property-based tests** to cover more tuples; still explicitly construct single-dimension control cases. Never infer from a handful of inputs that an expression can never collide: pair tests with reasoning about key representation.

## 11. Troubleshooting When Key Tests Fail

1. Record **cache name, method, parameters, runtime types, SpEL expression**, and expected output.
2. Verify the method actually passes through the Spring proxy; do not confuse direct calls with cache hits/misses.
3. Inspect the actual key stored in the cache; identify whether the bug is a missing dimension, delimiter, type, null, equality, namespace, or serializer issue.
4. Fix the expression/`KeyGenerator` or split cache names when two data types should not share a cache.
5. Sync **@CacheEvict/@CachePut**; if changing key formats in a live Redis/shared cache, check existing legacy keys and plan the rollout.
6. Re-run single-dimension, valid hit, null/type, cross-method, concurrency, and real provider tests.

## 12. Self-Check Questions

1. Why does a test changing both tenant and currency simultaneously fail to prove the key includes both?
2. When is **#p0** sufficient, and when must **#p1/#p2** also be included?
3. Why are **("a:b", "c")** and **("a", "b:c")** dangerous when concatenating with a colon?
4. Why can **42L** and **"42"** stay separate in a local cache yet collide under **'id:' + #p0**?
5. When inputs are nullable, why does **T(java.util.List).of(...)** need a different policy?
6. Why does testing the standalone SpEL parser not replace a Spring integration test?
7. If a write method adds **newPrice**, why can **@CacheEvict** not use the default key like the read method?
8. When migrating from `ConcurrentMapCache` to Redis, what must be checked regarding key converters and cache prefixes?

Guiding principle: **only calls that are genuinely allowed to share results should share the same cache name + key**. Design expressions from the data contract, test each component independently, verify actual types/keys, and keep the exact same rule across read, write, and evict paths.

### References

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — @Cacheable, SpEL and key generation: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Spring AOP proxy: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — SimpleKeyGenerator API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html
- Spring Data Redis — Redis Cache: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
