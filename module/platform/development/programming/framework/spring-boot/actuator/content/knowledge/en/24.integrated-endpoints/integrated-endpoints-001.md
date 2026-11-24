# Exploring Caches with the `caches` Endpoint and Cache Eviction Scope

## 1. Understanding What You Are Observing

A cache retains results so an application can reuse them instead of recomputing or reading from the data source for every request. In Spring, a `CacheManager` manages named caches; each cache holds entries identified by a key.

For example, consider a retail application with the following structure:

~~~text
Application
├── inventoryCacheManager
│   ├── products
│   │   ├── p1 → inventory-1
│   │   └── p2 → inventory-2
│   └── categories
│       └── c1 → hardware
└── partnerCacheManager
    └── products
        └── p1 → partner-1
~~~

There are two caches both named `products`, but they belong to different managers. Therefore, the reliable operation identifier is the **pair of CacheManager name and cache name**, not just the cache name.

Spring Boot Actuator's built-in `caches` endpoint helps operators discover the caches an application manages and request cache clearing. It bridges operational visibility with Spring's cache abstraction; the underlying cache provider decides how actual data is stored and removed.

Three operations to distinguish:

- **Cache discovery:** knowing which managers and caches exist.
- **Reading entries:** retrieving the value corresponding to a key.
- **Clearing a cache:** removing all entries within the selected scope.

`caches` supports the first and third operations. It does not provide an API to iterate keys or inspect entry values. The class name in the `target` field describes the underlying native cache object, not the contents stored in the cache. See the [endpoint HTTP contract in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/caches.html).

This article uses Spring Boot **3.3.x** and Java **17 or higher**. The runnable example below pins Boot **3.3.0** and Spring Framework **6.1.8** to observe concrete behavior.

## 2. Requirements to Call over HTTP

In a Spring Boot web application, Actuator and `CacheManager` beans must be registered. For example, declare the following Gradle dependencies in a project already managed by Spring Boot 3.3:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

This is a configuration snippet added to an existing Spring Boot project, not a standalone Gradle project.

Example lab configuration in `application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoint:
    caches:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,caches
~~~

In Boot 3.3, **enabled** and **exposed** are two separate conditions: enabling an endpoint does not automatically expose it over HTTP. By default, only `health` is exposed over HTTP; if `exclude` is configured, it takes precedence over `include`. The URLs in this article assume port `8080`, management base path `/actuator`, and no other context path prefix. Source: [Boot 3.3 endpoint configuration and exposure](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

`@EnableCaching` enables processing of annotations such as `@Cacheable`. Do not treat it as an Actuator switch: if you register a `CacheManager` manually and use the `Cache` API directly, those caches can still be observed without using caching annotations.

The following Java snippet illustrates two beans matching the diagram above. Add these methods to a `@Configuration` class in the web application; import `Bean`, `CacheManager`, `ConcurrentMapCacheManager`, and `Objects` accordingly:

~~~java
@Bean
CacheManager inventoryCacheManager() {
    var manager = new ConcurrentMapCacheManager("products", "categories");
    Objects.requireNonNull(manager.getCache("products"))
            .put("p1", "inventory-1");
    Objects.requireNonNull(manager.getCache("categories"))
            .put("c1", "hardware");
    return manager;
}

@Bean
CacheManager partnerCacheManager() {
    var manager = new ConcurrentMapCacheManager("products");
    Objects.requireNonNull(manager.getCache("products"))
            .put("p1", "partner-1");
    return manager;
}
~~~

The default bean name is the method name, so the value used in the `cacheManager` parameter is `inventoryCacheManager` or `partnerCacheManager`.

With `ConcurrentMapCacheManager`, the constructor accepting a list of names creates a fixed set of caches for the lab. The no-argument constructor allows creating caches dynamically when the application requests them; when observing, distinguish between caches already known to the manager and cache names that are only planned in the design. Source: [ConcurrentMapCacheManager API](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/cache/concurrent/ConcurrentMapCacheManager.html).

## 3. Discovering Before Selecting Scope

### 3.1. Listing Caches

In the terminal, call:

~~~shell
curl -i "http://localhost:8080/actuator/caches"
~~~

If using Windows PowerShell where `curl` is an alias, use `curl.exe` to invoke the actual CLI tool. The HTTP commands in this article assume access permissions have already been granted.

The JSON body corresponding to the two beans above has the following structure; the order of JSON properties is not a criterion for determining a correct result:

~~~json
{
  "cacheManagers": {
    "inventoryCacheManager": {
      "caches": {
        "products": {
          "target": "java.util.concurrent.ConcurrentHashMap"
        },
        "categories": {
          "target": "java.util.concurrent.ConcurrentHashMap"
        }
      }
    },
    "partnerCacheManager": {
      "caches": {
        "products": {
          "target": "java.util.concurrent.ConcurrentHashMap"
        }
      }
    }
  }
}
~~~

Read from outside in: manager name → `caches` → cache name → `target`. When working with the endpoint, take the manager name from the actual output rather than inferring it from the Java type name.

### 3.2. Inspecting a Specific Cache

~~~shell
curl -i "http://localhost:8080/actuator/caches/products?cacheManager=inventoryCacheManager"
~~~

Response body:

~~~json
{
  "target": "java.util.concurrent.ConcurrentHashMap",
  "name": "products",
  "cacheManager": "inventoryCacheManager"
}
~~~

For a unique name like `categories`, you can omit the `cacheManager` parameter. For `products`, which appears in both managers, you must specify the manager. These fields and identification rules belong to the [caches endpoint contract](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/caches.html#caches.retrieving-by-name).

**Do not infer entry counts from the JSON above.** A cache with thousands of entries and a newly cleared cache can still return the same metadata. To know whether a key is still stored, you must observe through the application or the cache provider's own mechanism.

## 4. The Four Operations and Their Corresponding Scopes

| HTTP Request | Scope |
| --- | --- |
| `GET /actuator/caches` | Metadata of caches visible to the endpoint |
| `GET /actuator/caches/{name}?cacheManager={manager}` | Metadata of one identified cache |
| `DELETE /actuator/caches/{name}?cacheManager={manager}` | All entries of that specific cache |
| `DELETE /actuator/caches` | All entries in every cache visible to the endpoint, across its managers |

### 4.1. Deleting a Cache by Name Clears All Entries in That Cache

~~~shell
curl -i -X DELETE "http://localhost:8080/actuator/caches/products?cacheManager=inventoryCacheManager"
~~~

In the example, this operation removes both `p1` and `p2` from the inventory's `products` cache. It leaves `categories` and the partner's `products` cache intact.

The name `products` identifies the cache region, not an entry key. If you only want to evict `p1`, the application needs a key-scoped operation, such as `cache.evict("p1")` or a business action using `@CacheEvict`. This built-in endpoint has no `key` parameter and no standard `/actuator/caches/products/p1` path for doing that.

### 4.2. Deleting at the Root Path Has a Broader Scope

~~~shell
curl -i -X DELETE "http://localhost:8080/actuator/caches"
~~~

In the lab, both `products` caches and the `categories` cache are cleared.

**The `cacheManager` parameter only identifies targets for per-cache-name operations.** Do not use `DELETE /actuator/caches?cacheManager=inventoryCacheManager` to mean "clear all caches in one manager": the root `clearCaches()` operation accepts no manager parameter and provides no such filter. To target one manager, you must explicitly identify its caches and operate on each cache individually, or design a custom management action with a clear contract. Compare the signature and scope in the [Boot 3.3 CachesEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/cache/CachesEndpoint.html).

### 4.3. Clearing Does Not Delete the Cache Definition

With the managers in the lab, after DELETE:

- The cache object and the name `products` still exist.
- Old entries in the selected cache are gone.
- A subsequent write or data load can put new entries into the cache.

Therefore, `GET /actuator/caches/products?cacheManager=inventoryCacheManager` continuing to return metadata is the expected result. The cache name still appearing does not prove DELETE failed.

## 5. Cache Selection Mechanism and Meaning of HTTP Statuses

The lookup-by-name flow can be read as follows:

~~~text
Receive cache name and optional manager
    ↓
Search matching caches across CacheManagers
    ↓
0 results → not found
1 result → read metadata or call Cache.clear()
multiple results → ambiguous request, do not auto-select a cache
~~~

In Spring Boot 3.3, `CachesEndpointWebExtension` translates lookup and clear-by-name results into HTTP status codes:

| Scenario | GET by name | DELETE by name |
| --- | --- | --- |
| One cache identified | `200` with metadata | `204`, no body |
| No matching cache found | `404` | `404` |
| Multiple caches share the name, manager missing | `400` | `400` |

These codes assume the request has passed the security layer and routed to the right endpoint. `@Primary` resolves bean selection in appropriate dependency injection contexts; it does not replace the `cacheManager` parameter to bypass ambiguity in the endpoint's lookup.

`204` does not report how many entries were removed. An already empty cache can still receive a successful DELETE. Conversely, a wrong manager name results in no matching pair found, even if a cache with the same name exists in another manager.

The by-name results are verified by the runnable example in the next section. The Java contract for not-found and non-unique names is described in the [CachesEndpoint API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/cache/CachesEndpoint.html#cache(java.lang.String,java.lang.String)).

## 6. Standalone Java Experiment to See Data Before and After Deletion

This example directly invokes `CachesEndpoint` itself and Actuator's web extension class. It **does not start an HTTP server**; the printed numbers are the statuses returned by the web extension. This approach lets you observe in-memory data directly without creating an API to read cache values for operators.

Create a separate lab directory with `pom.xml` and `CachesScopeDemo.java` at the same level. This is a standalone Java program, not attached to a running Spring Boot module.

### 6.1. Lab Dependencies

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>learning</groupId>
    <artifactId>caches-scope-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator</artifactId>
            <version>3.3.0</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.8</version>
        </dependency>
    </dependencies>
</project>
~~~

Maven is only used to resolve the dependency classpath; the commands below use `javac` and `java` directly to compile and run.

### 6.2. Complete Program

~~~java
import java.util.Map;
import java.util.Objects;
import org.springframework.boot.actuate.cache.CachesEndpoint;
import org.springframework.boot.actuate.cache.CachesEndpointWebExtension;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;

public class CachesScopeDemo {
    public static void main(String[] args) {
        CacheManager inventory =
                new ConcurrentMapCacheManager("products", "categories");
        CacheManager partner =
                new ConcurrentMapCacheManager("products");
        Cache products = Objects.requireNonNull(inventory.getCache("products"));
        Cache categories = Objects.requireNonNull(inventory.getCache("categories"));
        Cache partnerProducts = Objects.requireNonNull(partner.getCache("products"));

        products.put("p1", "inventory-1");
        products.put("p2", "inventory-2");
        categories.put("c1", "hardware");
        partnerProducts.put("p1", "partner-1");

        CachesEndpoint endpoint = new CachesEndpoint(Map.of(
                "inventoryCacheManager", inventory,
                "partnerCacheManager", partner));
        CachesEndpointWebExtension web = new CachesEndpointWebExtension(endpoint);

        System.out.println("GET ambiguous = " + web.cache("products", null).getStatus());
        System.out.println("DELETE ambiguous = " + web.clearCache("products", null).getStatus());
        System.out.println("after ambiguous p1 = " + products.get("p1", String.class));

        System.out.println("DELETE selected = "
                + web.clearCache("products", "inventoryCacheManager").getStatus());
        System.out.println("inventory p1 = " + products.get("p1", String.class));
        System.out.println("inventory p2 = " + products.get("p2", String.class));
        System.out.println("partner p1 = " + partnerProducts.get("p1", String.class));
        System.out.println("category c1 = " + categories.get("c1", String.class));
        System.out.println("GET cleared cache = "
                + web.cache("products", "inventoryCacheManager").getStatus());
        System.out.println("DELETE again = "
                + web.clearCache("products", "inventoryCacheManager").getStatus());
        System.out.println("DELETE missing = "
                + web.clearCache("missing", "inventoryCacheManager").getStatus());

        endpoint.clearCaches();
        System.out.println("after all partner p1 = "
                + partnerProducts.get("p1", String.class));
        System.out.println("after all category c1 = "
                + categories.get("c1", String.class));
        System.out.println("GET after all = "
                + web.cache("products", "partnerCacheManager").getStatus());
    }
}
~~~

`Map.of(...)` passes manager names to the endpoint explicitly. In a real Spring Boot application, auto-configuration supplies the `CacheManager` beans to the endpoint.

### 6.3. Compiling and Running

Requires JDK 17+ and Maven; downloading dependencies the first time requires connectivity to the Maven repository.

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$cacheClasspath = (Get-Content -LiteralPath .\classpath.txt -Raw).Trim()
javac --release 17 -cp "$cacheClasspath" CachesScopeDemo.java
java -cp ".;$cacheClasspath" CachesScopeDemo
~~~

Linux/macOS:

~~~shell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
cache_classpath="$(cat classpath.txt)"
javac --release 17 -cp "$cache_classpath" CachesScopeDemo.java
java -cp ".:$cache_classpath" CachesScopeDemo
~~~

Program stdout:

~~~text
GET ambiguous = 400
DELETE ambiguous = 400
after ambiguous p1 = inventory-1
DELETE selected = 204
inventory p1 = null
inventory p2 = null
partner p1 = partner-1
category c1 = hardware
GET cleared cache = 200
DELETE again = 204
DELETE missing = 404
after all partner p1 = null
after all category c1 = null
GET after all = 200
~~~

Interpreting the milestones of the experiment:

1. Omitting the manager when the name is duplicated produces `400`; `inventory-1` remains intact, so an ambiguous clear does not silently pick one cache.
2. Specifying `inventoryCacheManager` removes both `p1` and `p2` from the selected cache. Partner and category data remain.
3. GET on the cleared cache returns `200`, and DELETE again returns `204`: "the cache exists" differs from "the cache still has entries."
4. The `missing` cache returns `404`. When `clearCaches()` is called, partner and category data are also lost; the partner cache metadata remains readable.

The example uses in-memory data with no concurrent writes. A `null` result indicates there is no longer a String value for that key in the lab caches.

## 7. Limitations to Understand Before Reasoning About Production Systems

### 7.1. Discovery Scope Is Determined by CacheManagers

The endpoint works with Spring's `CacheManager` and `Cache` abstractions. A hand-rolled `Map`, a custom library cache not integrated through these managers, browser HTTP caches, or CDNs do not automatically become targets controlled by `caches`.

The list returned by the managers at the time of observation is the basis for operations. For lazily created caches, do not conclude that a missing name means the application's entire caching mechanism is disabled.

### 7.2. Data Scope Also Depends on Storage Location

The experiment uses `ConcurrentMapCacheManager`, so data lives inside the current Java process. If two application instances use separate in-memory caches, sending DELETE to instance A does not automatically clear instance B's memory.

If instances share a remote cache store, the effect can be observed by other instances through the shared data region. You must verify the manager, name prefixes, data store, and actual deployment topology. Do not infer "cluster-wide clear" or "single-host clear" from the endpoint URL alone.

### 7.3. Clearing Cache Is Not a Business Data Update Transaction

In the lab, data exists only in the cache. In an application using a database as the source of truth, a cache operation does not modify the source record; the next read can reload the value from that source.

Therefore, if the data source is still wrong, clearing the cache does not fix the root cause. If a key must be evicted after a business update, place cache invalidation rules in the right business flow rather than relying on operators clearing the entire region.

### 7.4. Success Does Not Guarantee the Cache Remains Empty Forever

Boot 3.3's implementation calls `Cache.clear()` on the selected cache. The contract of `clear()` allows a provider or wrapper to defer removal; do not upgrade a success status code into a synchronous barrier across all providers. See [Spring Framework's Cache.clear() contract](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/cache/Cache.html#clear()).

Furthermore, another application request can repopulate entries immediately after clearing. For the root operation, there is also no single atomic transaction contract spanning all caches and all managers. If a provider fails mid-way, you must recheck each scope rather than assuming everything was rolled back.

## 8. Distinguishing Configuration, Security, and Cache Selection Errors

| Symptom | What to Check |
| --- | --- |
| Root GET returns `404` | Is Actuator present; is the endpoint enabled/exposed; are port and base path correct |
| Root GET lacks expected cache | Which CacheManager beans are visible to the endpoint; is the cache name known to the manager yet |
| GET or DELETE by name returns `400` | Check for duplicate names across managers; add the correct `cacheManager` |
| Request by name returns `404` | Check both the cache name and the manager name, not just one of them |
| GET works but DELETE returns `403` | Check operation permissions and CSRF before concluding the cache provider cannot delete |
| DELETE succeeds but GET still shows the name | GET returns metadata; check entries via experiment or application behavior |
| Data quickly reappears after clearing | Check reload requests, background jobs, multiple instances, and actual store scope |

If Spring Security is present, exposing an endpoint does not automatically grant access. Default CSRF protection can block DELETE even when authenticated. Configuration for metadata readers and delete-authorized operators should reflect operational responsibilities; do not disable CSRF application-wide just to make a DELETE command work. Source: [Boot 3.3 Actuator security and CSRF](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

## 9. Choosing Operation Scope in a Concrete Scenario

Suppose product prices in the data source were fixed, but only the inventory cache data is stale. Partner and category caches are still accurate.

Verifiable procedure:

1. GET the list to confirm the `inventoryCacheManager/products` pair.
2. Check whether only one key needs eviction or if the entire products cache truly needs to be cleared.
3. If the entire inventory products cache must be cleared, call DELETE by name with the manager parameter.
4. Observe the next business read to confirm the price is reloaded from the corrected source.
5. Check remaining scopes when needed, especially if there are multiple application instances or a remote cache.

Choosing root DELETE in this scenario would wipe valid category and partner data too. The consequence could be many requests simultaneously re-reading the database, increasing latency and source load. Only widen the scope when there is a specific reason.

**Self-check exercises:**

- Run the program and explain why DELETE `products` without a manager returns `400` despite having the exact cache name.
- Replace the manager name in the targeted delete command with a nonexistent name. Predict the returned status code and which caches keep their data.
- Re-insert an entry into `products` after a successful DELETE. Explain why that does not contradict the `204` result.
- With two processes using independent `ConcurrentMapCacheManager` instances, determine which process must be observed to verify the effect of a clear command.

When answering, always specify the **manager, cache, and data storage location**. Those three factors determine the actual scope of the operation.
