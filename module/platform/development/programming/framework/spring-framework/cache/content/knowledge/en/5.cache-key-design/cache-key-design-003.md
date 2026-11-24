# The equals–hashCode Contract of Keys in Spring Cache

## Objectives

After this lesson, you will be able to explain why **equals()** and **hashCode()** determine cache key correctness in the JVM, design immutable keys for Spring Cache yourself, identify bugs when using objects as keys, and distinguish Java's rules from the key identification mechanisms of distributed cache providers.

Context: Spring Framework Cache Abstraction, especially in-memory caches using hash structures such as ConcurrentMapCache and Caffeine in its default strong-keys mode. Spring Cache provides the Cache, CacheManager, and annotation interfaces; Spring does not replace the equals–hashCode contract of Java objects used as keys.

## 1. Why Does a Cache Key Need equals() and hashCode()?

Suppose a method reads product prices by two components: product code and currency. Two different requests create two separate objects, yet with the same code and same currency. They must look up **the same entry**, so data is not recomputed and two redundant entries are not created. Conversely, the same product code with a different currency must look up **two different entries**.

With a hash-table-style cache in the JVM, the idea is:

~~~text
price(new PriceKey("P42", "VND"))
   -> Spring computes the key
   -> CacheManager retrieves cache "prices"
   -> cache uses hashCode() to select the bucket/candidate set
   -> uses equals() to confirm key equivalence
   -> HIT or MISS
~~~

**hashCode()** provides an int hash code to organize lookups. **equals()** determines whether two keys represent the same logical identity. A cache using a hash structure can return wrong hits/misses if these two methods are implemented incompatibly or if the key mutates while sitting in the cache.

Do not assume every provider uses Java's hashCode() directly. For instance, Redis receives keys converted into bytes and looks them up by bytes on the server. Java's rules are foundational for Java in-memory caches, while remote caches additionally require stability of the **key representation after serialization**.

## 2. Java's equals() Contract

A correct equals() implementation must satisfy these properties:

1. **Reflexive:** For any non-null reference x, x.equals(x) is true.
2. **Symmetric:** x.equals(y) and y.equals(x) must return the same result.
3. **Transitive:** If x.equals(y) and y.equals(z) are true, then x.equals(z) must be true.
4. **Consistent:** When the data used for comparison has not changed, multiple invocations of equals() must return the same result.
5. **Comparison with null:** For any non-null x, x.equals(null) is false.

Values x and y are considered **logically equal**, not necessarily the same object. The **==** operator on two references only checks whether they point to the same object. A key object inheriting the default Object.equals() performs reference identity comparison; this is valid under the Java contract but **may be unsuitable for caching**, because two requests creating new objects will not hit each other even if they contain the same data.

For example: new PriceKey("P42", "VND") created the first time and the second time are two different instances. If PriceKey is a record, these two instances will be equals() due to their component values. If it is a class that does not override equals(), they will normally not be equal because of reference comparison.

## 3. The hashCode() Contract and Required Relationship with equals()

Core rule:

> If x.equals(y) == true, then x.hashCode() **must** equal y.hashCode().

Furthermore, while the attributes used by equals() remain unchanged, hashCode() must return a consistent result within the same execution. The reverse is **not required**: two unequal objects can still share the same hashCode(), known as a **hash collision**. Hash structures need equals() to distinguish them.

Example of two different Strings with the same hash code:

~~~java
System.out.println("Aa".hashCode() == "BB".hashCode()); // true
System.out.println("Aa".equals("BB"));                 // false
~~~

This is an illustrative Java expression snippet; the output of the two lines is true and false, respectively. A system that uses **only hashCode() as the key** or treats hashCode as a unique identifier risks mixing data upon collisions.

Verification rules table:

| Scenario | Contract-valid? | Meaning |
| --- | --- | --- |
| equals() true, hashCode() equal | Required | Ensures the same logical key can be looked up |
| equals() true, hashCode() different | **Wrong** | May store/retrieve in different buckets, false cache miss |
| equals() false, hashCode() equal | **Valid** | Collision; equals() distinguishes during lookup |
| equals() false, hashCode() different | Valid | Normal key distribution |
| hashCode() changes after the key is placed in cache | Dangerous | The entry may no longer be found with the mutated key |

More precisely: hashCode() does not need to be unique; it must be **consistent with equals()** and **stable with respect to the state used for identification**.

## 4. Designing Immutable Keys with Java Records

With Java 17+, a record is an appropriate choice when a key consists solely of immutable value components. The compiler automatically generates equals() and hashCode() based on the declared components.

~~~java
import java.util.Objects;

public record PriceKey(String productId, String currency) {
    public PriceKey {
        Objects.requireNonNull(productId, "productId");
        Objects.requireNonNull(currency, "currency");
    }
}
~~~

This is a **type definition snippet**; to compile it separately, save it as PriceKey.java and run javac PriceKey.java (requires Java 17+). String content cannot be modified after creation; the record's two components are also final. Therefore, two instances with equal productId and currency will have equals() true and matching hashCode().

Example of three keys:

~~~text
PriceKey("P42", "VND") ==logical== PriceKey("P42", "VND")
PriceKey("P42", "VND") !=logical!= PriceKey("P42", "USD")
~~~

A key must include **all factors that alter the method's result**. If the same product with a different currency, locale, tenant, data version, or pricing policy yields different outputs, the relevant factors must be in the key, unless the cache name or namespace already separates them reliably.

### Record Does Not Mean Deep Immutability

A record only fixes the **component references**. If a component is a mutable List, an array, or a mutable object, the inner data can still change. When that happens, the record's equals() and hashCode() can also change along with the mutable contents.

Unsafe example:

~~~java
record SearchKey(java.util.List<String> tags) {}

var tags = new java.util.ArrayList<>(java.util.List.of("java"));
var key = new SearchKey(tags);
tags.add("spring"); // Mutated state participating in the key's equals/hashCode.
~~~

To use a List as a key, create an immutable copy at the key creation boundary:

~~~java
record SearchKey(java.util.List<String> tags) {
    public SearchKey {
        tags = java.util.List.copyOf(tags);
    }
}
~~~

This is still only **shallow immutability for the List's elements**. If the inner elements are mutable objects affecting equals/hashCode, a deeper snapshot or normalization into immutable Strings/IDs is needed. Avoid putting mutable arrays into keys; arrays in Java use reference-identity equals/hashCode unless wrapped or compared by content properly.

## 5. When Writing a Regular Class, Implement Both Methods

Not every project wants to expose keys as records. When using a class, identifying fields should be private final; equals() and hashCode() must use **the same set of fields**.

~~~java
import java.util.Objects;

public final class PriceKey {
    private final String productId;
    private final String currency;

    public PriceKey(String productId, String currency) {
        this.productId = Objects.requireNonNull(productId);
        this.currency = Objects.requireNonNull(currency);
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof PriceKey that)) return false;
        return productId.equals(that.productId)
            && currency.equals(that.currency);
    }

    @Override
    public int hashCode() {
        return Objects.hash(productId, currency);
    }
}
~~~

This is a standalone class compilable on Java 17+ when saved to PriceKey.java. **equals() and hashCode() both inspect productId and currency**. Do not pick only one field in hashCode and call it a contract violation: a hashCode using fewer fields can still be contract-valid since it only increases collisions, though distribution quality may suffer. A real bug occurs when two objects considered equal by equals() have different hashCodes, or when the compared field set omits data that defines the key's identity.

With classes involving inheritance, be careful when using instanceof and when subclasses add fields to equals(): inconsistent design between parent and child easily breaks **symmetry or transitivity**. For cache keys, a final class or record with clear value semantics is usually safer.

## 6. Java 17 Example: HashMap Showing Logical Key Equality and Collisions

Before moving to Spring annotations, you can verify the contract with plain JDK. Create **KeyContractDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class KeyContractDemo {
    record PriceKey(String product, String currency) {
        PriceKey {
            Objects.requireNonNull(product);
            Objects.requireNonNull(currency);
        }
    }

    public static void main(String[] args) {
        PriceKey first = new PriceKey("P42", "VND");
        PriceKey same = new PriceKey("P42", "VND");
        PriceKey other = new PriceKey("P42", "USD");

        System.out.println("equals=" + first.equals(same));
        System.out.println("sameHash="
            + (first.hashCode() == same.hashCode()));

        Map<PriceKey, String> cache = new HashMap<>();
        cache.put(first, "price-in-vnd");
        System.out.println("hit=" + cache.get(same));
        System.out.println("otherCurrency=" + cache.get(other));

        Map<String, String> collisions = new HashMap<>();
        collisions.put("Aa", "first");
        collisions.put("BB", "second");
        System.out.println("collision="
            + ("Aa".hashCode() == "BB".hashCode()));
        System.out.println("collisionEntries=" + collisions.size());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 KeyContractDemo.java
java KeyContractDemo
~~~

Exact stdout output:

~~~text
equals=true
sameHash=true
hit=price-in-vnd
otherCurrency=null
collision=true
collisionEntries=2
~~~

Explanation:
- first and same are two separate instances, yet **equals() is true and they share the same hash**, so get(same) reads back first's entry.
- other has a different currency, so no entry is found and get() returns null.
- The two Strings "Aa" and "BB" have the same hashCode but are not equals(); HashMap still stores two entries. HashMap illustrates the key lookup principle, **not the full Spring Cache mechanism** (there are no annotations, interception, TTL, or eviction).

## 7. How Does Spring Cache Generate Default Keys?

When no custom key or keyGenerator is declared, annotation-based caching uses a default mechanism based on method parameters (SimpleKeyGenerator in typical default configurations).

| Parameter pattern | Default key | Impact of equals/hashCode |
| --- | --- | --- |
| No parameters | SimpleKey.EMPTY | All calls to the same cache name with this key form share the same key |
| One non-null, non-array parameter | That parameter object itself | If it is a business object, its equals/hashCode directly determines hits/misses |
| One null parameter or one array | A SimpleKey containing the parameter list | Depends on how SimpleKey compares components; avoid assuming the key is the bare parameter |
| Two or more parameters | SimpleKey containing the parameters | Parameter components must have proper equality semantics; Spring handles the multi-parameter key structure |

Spring's SimpleKey performs deep semantic comparison for the contained element structure, yet **cannot fix** broken equals/hashCode on the business objects inside. A diverse parameter list or mutable object can also make keys hard to keep stable; choose a safe representation.

Example:

~~~java
@Cacheable(cacheNames = "prices")
public String price(PriceKey key) {
    return loadFromSource(key);
}
~~~

The snippet above illustrates the annotation, not a complete class. Since PriceKey is a single non-array parameter, the default key is PriceKey itself; two records with the same productId and currency will be treated as one logical key. The cacheNames part locates the **cache store**, while equals/hashCode locates the **entry** inside the store for this key type.

### Different Methods Can Collide on Keys in the Same Cache

CacheManager and Cache **do not automatically include the method/class name in the default key**. Suppose two methods both use @Cacheable(cacheNames = "prices") and both receive String "P42": by default they can produce the same key "P42". If the two methods return two different types of data, there is a risk of mixing results.

Solutions depending on context: use different cache names; use an operation/namespace-scoped key structure; or use a custom keyGenerator consistently. Do not replace the key with the numeric hashCode of the method/argument because hash collisions can still occur.

## 8. Complete Spring Framework Example: Two Equal Objects Sharing a Cache Entry

This demo project uses **Java 17+, Maven, and Spring Framework**, without needing Spring Boot. The test output shows CacheManager storing by a key with proper equals/hashCode, and then @CacheEvict deleting the entry even when using another equivalent object.

Structure:

~~~text
spring-cache-key-contract/
├── pom.xml
└── src/main/java/demo/CacheKeyApp.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-cache-key-contract</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/CacheKeyApp.java**:

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class CacheKeyApp {
    public record PriceKey(String productId, String currency) {
        public PriceKey {
            Objects.requireNonNull(productId);
            Objects.requireNonNull(currency);
        }
    }

    public static class PriceService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "prices")
        public String price(PriceKey key) {
            int call = loads.incrementAndGet();
            return key.productId() + "/" + key.currency() + " #" + call;
        }

        @CacheEvict(cacheNames = "prices", key = "#p0")
        public void invalidate(PriceKey key) {
            // In a real application, the source update action is handled
            // according to appropriate transaction and consistency rules.
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {
        @Bean
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("prices");
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static void main(String[] args) {
        PriceKey a = new PriceKey("P42", "VND");
        PriceKey b = new PriceKey("P42", "VND");
        PriceKey c = new PriceKey("P42", "USD");

        System.out.println("sameLogicalKey=" + a.equals(b));
        System.out.println("sameHash=" + (a.hashCode() == b.hashCode()));

        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            PriceService service = ctx.getBean(PriceService.class);
            System.out.println(service.price(a));
            System.out.println(service.price(b));
            System.out.println(service.price(c));
            service.invalidate(b);
            System.out.println(service.price(a));
        }
    }
}
~~~

Run inside the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CacheKeyApp
~~~

Stdout from the demo code (excluding Maven's own messages):

~~~text
sameLogicalKey=true
sameHash=true
P42/VND #1
P42/VND #1
P42/USD #2
P42/VND #3
~~~

Step-by-step analysis:
1. a and b are different instances, yet equals() is true and their corresponding hashCodes match.
2. price(a) misses the cache, the real code runs and increments loads to 1.
3. price(b) hits the cache because b is a **value-equivalent** key, so the result stays "#1".
4. price(c) misses the cache due to a different currency, incrementing loads to 2.
5. invalidate(b) uses **the same cache name** and key "#p0" which is PriceKey b; equals/hashCode enables deleting the original entry stored under a.
6. price(a) has no entry left, so the real code runs a third time.

**Exact scope of illustration:** ConcurrentMapCacheManager is an in-memory cache using Java keys; the example does not test TTL, serialization, multi-instance setups, or transactions. For annotations to take effect, you must invoke the PriceService **retrieved from the Spring container through a proxy**. Calling an annotated method from another method on the same instance (self-invocation) normally bypasses the default Spring proxy.

## 9. Broken Key Example: Overriding equals() While Forgetting hashCode()

Suppose a developer creates this class:

~~~java
final class BrokenKey {
    private final String id;
    BrokenKey(String id) { this.id = id; }

    @Override
    public boolean equals(Object obj) {
        return obj instanceof BrokenKey other
            && java.util.Objects.equals(id, other.id);
    }

    // Does not override hashCode(): still uses Object.hashCode().
}
~~~

Two instances with the same id will have equals() true, yet **are not guaranteed to have the same hashCode()**; they typically have different identity hash codes. Thus the class violates the Java contract. Depending on the hashes and map structure, get() with an equivalent instance can miss even when the entry already exists.

The fix is to override hashCode() correspondingly:

~~~java
@Override
public int hashCode() {
    return java.util.Objects.hashCode(id);
}
~~~

This fix is **added to the BrokenKey class**, not a standalone program. When using an IDE, the Generate equals() and hashCode() feature or converting to a record prevents forgetting one of the methods; you still must verify the set of fields carrying identity meaning.

### The Opposite Bug: equals() Compares Too Few Fields

For example, a product price key consists of productId and currency, but equals() only compares productId. Then two requests "P42/VND" and "P42/USD" are treated as the same key and may hit the wrong data. Even if hashCode() also uses only productId and the Java contract **is not violated**, the key design is still **business-wise wrong**.

Distinguish two independent criteria:
- **Java contract validity:** are equals/hashCode compatible, stable, and compliant with the contract properties?
- **Cache identity correctness:** are the fields participating in the key sufficient to distinguish every distinct business output?

Both layers of checking are mandatory when designing keys.

## 10. Mutable Keys: A Dangerous Bug Even When equals/hashCode Are Written Correctly

Consider a class with a mutable id field:

~~~java
import java.util.Objects;

final class MutableKey {
    String id;
    MutableKey(String id) { this.id = id; }

    @Override
    public boolean equals(Object other) {
        return other instanceof MutableKey that
            && Objects.equals(id, that.id);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(id);
    }
}
~~~

At any single instant, equals() and hashCode() are compatible. However, if you put the object into a HashMap/ConcurrentMapCache and then **mutate id**, hashCode() changes. The map may have placed the key in a structure based on the old hash code; looking it up with the new hash code will fail to find the entry, and even looking it up with the original object reference can fail.

~~~java
MutableKey key = new MutableKey("old");
map.put(key, "cached");
key.id = "new";               // Breaks stability of the stored key.
// map.get(key) is now no longer guaranteed to return "cached".
~~~

This is an **illustrative snippet** with an assumed pre-declared map variable. In practice, never rely on any lookup outcome after mutating a key. With keys containing collections, Dates, or business objects whose getters change over time, the same risk occurs at nested levels.

Rule: **do not mutate state affecting equals/hashCode for as long as the object is used as a key**. Create an immutable key snapshot from inputs instead of directly using a mutable JPA entity/DTO or an object with lazy-loading/changing fields.

## 11. Multi-Parameter Keys and Custom KeyGenerators

With a method signature receiving productId, currency, and tenantId, the simple option is letting Spring generate a SimpleKey from the three parameters:

~~~java
@Cacheable(cacheNames = "prices")
public String price(String productId, String currency, String tenantId) {
    // Illustrative snippet: calls data source.
    return findPrice(productId, currency, tenantId);
}
~~~

If all parameters are immutable Strings serving as identifiers, the default key is usually reasonable. Avoid accidentally using objects that differ by equals() when business logic treats them as one value, or vice versa. For example, BigDecimal("1.0") and BigDecimal("1.00") have equals() **false** even though compareTo() returns 0; if the value is used as part of a key, decide explicitly whether to normalize scale.

When a method receives multiple complex objects, convert them into a record containing the proper identifying fields, or use a **KeyGenerator** to centralize normalization logic in one place. Illustrative snippet:

~~~java
@Bean("priceKeyGenerator")
KeyGenerator priceKeyGenerator() {
    return (target, method, params) -> {
        String productId = (String) params[0];
        String currency = (String) params[1];
        String tenantId = (String) params[2];
        return new PriceKeyWithTenant(
            tenantId.trim(),
            productId.trim(),
            currency.trim().toUpperCase(java.util.Locale.ROOT)
        );
    };
}

record PriceKeyWithTenant(String tenantId,
                          String productId,
                          String currency) {}
~~~

This is an **illustrative configuration snippet**, requiring the bean to be declared inside a @Configuration class with imports for org.springframework.cache.interceptor.KeyGenerator and org.springframework.context.annotation.Bean. The example above is only valid when the three arguments are actually non-null Strings in the right order and normalization reflects business rules (do not trim or uppercase if codes are case-sensitive).

Method usage:

~~~java
@Cacheable(cacheNames = "prices", keyGenerator = "priceKeyGenerator")
public String price(String productId, String currency, String tenantId) {
    return findPrice(productId, currency, tenantId);
}
~~~

**Important:** related @CacheEvict or @CachePut operations must produce **the exact same key** (same components, order, normalization, cache name), even if the update method signature has extra parameters. If the operation uses a different signature, KeyGenerator must handle them separately or use an explicit key expression so the results match consistently. Avoid using hashCode() alone, unseparated concatenated Strings, or Object's default toString() as keys; they can collide, be unstable, or depend on object addresses.

## 12. Java In-Memory Keys Differ from Serialized Keys

Do not mechanically apply conclusions from ConcurrentMapCacheManager to every cache system:

| Cache / storage mechanism | Primary lookup identifier | What to check |
| --- | --- | --- |
| ConcurrentMapCache | Java key in ConcurrentMap | equals(), hashCode(), immutability, null-key policy |
| Caffeine with default strong keys | Java equality/hash | Java principles match map keys; expire/evict are separate policies |
| Caffeine with weakKeys | Comparison by **identity**, not value equals() | Two value-equal objects with different identities may not hit the same entry |
| Redis via Spring Data Redis | Serialized key string/bytes + prefix | Stable format, namespace, serializer, compatibility across instances and versions |
| Other distributed stores/providers | Depends on provider and encoder | Check API documentation and actual configuration |

In Redis, two Java objects having equals() true **is not enough** to guarantee they produce the same byte sequence if serializers, normalization, or prefix settings differ. Conversely, Java hashCode() does not need to be unique on the Redis server; what matters is that **the serialized key is identical for the same logical identity and distinct for different identities**.

Dangerous example when concatenating keys manually:

~~~text
tenant="a:b", product="c"  -> "a:b:c"
tenant="a", product="b:c"  -> "a:b:c"
~~~

Better approach: use a structure with clear boundaries, length-prefixed encoding, proper escaping, or a tested serializer/canonicalizer. If the key contains sensitive data, consider avoiding exposing information in keys observable on the cache server, logs, or metrics.

## 13. Contract and Cache Behavior Test Suite

Unit-testing equals/hashCode and integration-testing hits/misses in Spring are two separate steps. For a PriceKey type, test at least these cases:

| Case | Expected outcome |
| --- | --- |
| a.equals(a) | true |
| a and b share all identifying fields | equals() true; matching hashCode() |
| b and a have the same values | symmetry: b.equals(a) true |
| a, b, c have the same values | transitivity: a.equals(c) true |
| One identifying field differs | equals() false |
| a.equals(null) | false |
| Map lookup with another instance where equals() is true | proper cache hit |
| Change one identifying field in a newly created key | proper cache miss |
| Evict using a new key where equals() matches the old key | removes the right entry |
| Multi-tenant and locale/currency | no data mixing across different contexts |

In Spring, you can verify using a real method invocation counter like the example in Section 8. For integration tests, retrieve the service from the ApplicationContext so annotations are applied via proxy. Verify both **positive** cases (logically equivalent keys hit) and **negative** cases (different contexts miss).

Additional valuable checks:
- Map out the set of fields producing the result: query params, tenant, user scope, locale, permissions, feature state, version; put only genuinely needed fields in the key.
- Identify who builds the key, who evicts the key, and whether they use the same normalization.
- For multi-instance systems, verify serializers, prefixes, and stability across deployments.
- If the key structure changes across versions, put a version in the namespace or use a clear invalidation/migration strategy to avoid accidentally reading old data under a new format.
- If using weakKeys or a cache provider with identity semantics, adjust hit/miss expectations; proper equals/hashCode does not turn two separate objects into the same identity.

## 14. Common Errors and How to Fix Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Two value-equal objects miss the cache | Class does not override equals/hashCode or uses object identity | Use a record, final value object, or implement both equals and hashCode |
| equals() is true yet cache lookup fails | hashCode violates contract or key was mutated | Fix hashCode to match equals fields; take an immutable snapshot |
| Cache hits but returns wrong tenant/currency data | Missing business-identity field | Add tenant/currency/locale to key or partition caches |
| Wrong cache hit between two methods | Same cacheNames and same default key but different outputs | Separate cache names or namespace keys per operation |
| Still hits after evicting cache | @CacheEvict generates a different key or bypasses proxy; multiple caches/instances | Synchronize key strategy; verify proxy and topology |
| Manually concatenated String keys collide | Unescaped delimiter or unbounded fields | Use a schema-defined key, explicit encoding, and collision tests |
| Key contains List/array/entity | Mutable or unexpected comparison behavior | Copy immutably, normalize to IDs/values; avoid bare arrays |
| Unexpected misses after switching from local cache to Redis | Different serializer/prefix/canonical form | Check key bytes, versioning, and namespace configuration |
| Assuming matching hashCode means equal keys | Confusing hash collisions with equality | Use full equals(); never store by hashCode alone |

## 15. Self-Check Questions

**1.** Two PriceKey("P42","VND") instances created in two different requests have equals() true. Yet their hashCode() values differ. What bug is this?

**Answer:** A violation of the equals–hashCode contract. Two keys considered equal must have the same hash code; a hash-based cache may falsely miss.

**2.** Two different objects have the same hashCode(). Must they hit the same entry?

**Answer:** No. Collisions are valid; equals() must distinguish two logically different keys.

**3.** Is a record containing a mutable List completely safe to use as a key?

**Answer:** No. The record keeps the reference final, but the List can still be modified. An immutable snapshot is required, and elements participating in equality must also be stable.

**4.** Why can @Cacheable on two methods sharing a cache name reuse the same key even though the methods have different names?

**Answer:** The default key is based on arguments and does not automatically add the class/method name. Design namespaces or cache names corresponding to the data's semantics.

**5.** With Redis, do Java's equals/hashCode automatically guarantee that two instances produce the same Redis key?

**Answer:** No. Redis looks up keys by serialized bytes. You must verify key format, prefix, serializer version, and normalization logic across instances.

## Conclusion

A good cache key must satisfy **two conditions simultaneously**: comply with the Java contract (equals/hashCode and stability), and match **business identity** (identical logical requests produce identical keys; requests with different outputs produce different keys). For in-JVM caches, an immutable record or final value object is a safe starting point. For remote caches, add a consistent serialization contract and namespace.

### References

- Java Object.equals()/hashCode() – https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html
- Java records – https://docs.oracle.com/en/java/javase/17/language/records.html
- Spring Framework caching annotations – https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework cache key generation – https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html#cache-annotations-cacheable-default-key
