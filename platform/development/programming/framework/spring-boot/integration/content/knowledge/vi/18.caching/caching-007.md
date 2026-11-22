# JCache, Hazelcast hoặc Infinispan và phạm vi phụ thuộc cần có

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức tích hợp qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration. Tối ưu cache là một phần của bài toán lớn hơn: quản lý cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, xử lý trùng lặp, kiểm thử và quan sát các luồng tích hợp thực tế.

Giả sử **Catalog Service** gọi HTTP Inventory API và truy vấn PostgreSQL để tạo `ProductAvailability`. Dữ liệu nhiều người đọc nhưng ít thay đổi; cache có thể giảm độ trễ và giảm tải. Ban đầu ứng dụng dùng `ConcurrentMapCacheManager` trong một JVM. Khi chạy nhiều pods, cần cân nhắc một cache **clustered/distributed** như Hazelcast hay Infinispan; hoặc cần một API thống nhất theo JSR-107 (JCache), để ít phụ thuộc vào implementation cụ thể.

Một lỗi kiến trúc rất phổ biến: đội phát triển thêm `spring-boot-starter-cache`, `javax.cache:cache-api`, `hazelcast`, `hazelcast-spring` và `infinispan` cùng lúc, sau đó mong Spring tự “chọn loại cache mạnh nhất”. Thực tế, **Spring Cache là abstraction**, **JCache là specification/API**, còn **Hazelcast/Infinispan là những providers/technologies** với nhiều chế độ triển khai. Mỗi lớp có dependency, `CacheManager`, cấu hình TTL, serialization, clustering và failure mode riêng.

Bài thuộc chương **Bộ nhớ đệm**, đề mục **JCache, Hazelcast hoặc Infinispan và phạm vi phụ thuộc cần có**. Trọng tâm không phải chọn cache “nhanh nhất” theo tên sản phẩm, mà là chọn **đúng mức trừu tượng, đúng topology, đúng dependency scope và đúng consistency contract** cho Spring Boot Integration.

### Sau bài học, bạn có thể

1. Phân biệt `org.springframework.cache.CacheManager` và `javax.cache.CacheManager`.
2. Hiểu JCache/JSR-107 là API, không tự tạo provider, cluster hay Redis replacement.
3. Giải thích khi nào Spring Boot ưu tiên JCache, khi nào cần `spring.cache.type`.
4. Chọn dependency scopes `implementation`, `runtimeOnly`, `testImplementation` đúng mục đích.
5. Cấu hình JCache với Hazelcast hoặc Infinispan và tránh trùng provider.
6. Phân biệt Hazelcast embedded member, client/server và native Spring Cache integration.
7. Phân biệt Infinispan embedded, remote Hot Rod và JCache integration.
8. Hiểu cache names, keys, serialization, TTL, eviction, invalidation và versioning.
9. Thiết kế cache phù hợp với transaction, update API, nhiều replicas, timeout/retry.
10. Kiểm thử configuration selection, clustered visibility, expiration, lỗi kết nối và metrics.

> **Nguyên tắc:** Thư viện mang tên **cache API** không đồng nghĩa đã có cache **provider**; provider tồn tại không đồng nghĩa Spring Boot sẽ chọn **đúng CacheManager**; cache được phân tán không đồng nghĩa dữ liệu luôn nhất quán tức thời với database.

---

## 1. Ba lớp cần phân biệt trước khi thêm dependency

~~~mermaid
flowchart TD
    A["Business Service"] --> S["Spring Cache abstraction"]
    S --> SC["@Cacheable / @CachePut / @CacheEvict"]
    SC --> CM["org.springframework.cache.CacheManager"]
    CM --> J["JCacheCacheManager adapter"]
    CM --> H["Hazelcast native Spring CacheManager"]
    CM --> I["Infinispan Spring CacheManager"]
    J --> API["JSR-107: javax.cache API"]
    API --> P["JCache CachingProvider"]
    P --> HC["Hazelcast JCache provider"]
    P --> IC["Infinispan JCache provider"]
    H --> HM["HazelcastInstance"]
    I --> IM["Infinispan embedded / Hot Rod remote"]
~~~

### 1.1. Spring Cache: annotation và abstraction ở tầng ứng dụng

Spring Framework định nghĩa `org.springframework.cache.Cache`, `org.springframework.cache.CacheManager`, `@Cacheable`, `@CachePut`, `@CacheEvict` và `@Caching`.

Ví dụ:

~~~java
@Service
public class ProductCatalogService {

    private final ProductRepository repository;

    public ProductCatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productsById", key = "#productId")
    public ProductDto findProduct(String productId) {
        return repository.findDto(productId);
    }
}
~~~

`ProductRepository` và `ProductDto` là types ứng dụng. Annotation này không nhắc tên Hazelcast/Infinispan/JCache. Nó chỉ yêu cầu Spring tìm `Cache` tên `productsById` qua `CacheManager`.

`@EnableCaching` cần để bật annotation-driven caching nếu chưa có configuration khác kích hoạt:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CachingConfiguration {
}
~~~

**Không nhầm:** Có `spring-boot-starter-cache` trên classpath chưa bảo đảm `@Cacheable` hoạt động nếu annotation caching không được enable. Tùy cấu hình hiện có, Spring Boot tự cấu hình `CacheManager` nhưng không thay proxy invocation semantics.

### 1.2. JCache/JSR-107: specification và programming model

JCache tên chuẩn là **JSR-107, Java Temporary Caching API**. API 1.x dùng namespace **`javax.cache.*`** (ví dụ `javax.cache.CacheManager`, `javax.cache.configuration.MutableConfiguration`). Tên này tồn tại ngay cả trong nhiều hệ sinh thái Spring Boot 3 dựa trên Jakarta EE; không tự thay mọi import `javax.cache` thành `jakarta.cache`.

JCache định nghĩa một interface chung cho cache provider: `CachingProvider`, `CacheManager`, `Cache`, cấu hình expiry và các annotations như `@CacheResult`, `@CacheRemove`, `@CachePut`, `@CacheRemoveAll`.

**JCache không tự cung cấp một cache implementation.** Chỉ thêm `javax.cache:cache-api` mà không có `CachingProvider` thì không có nơi lưu entry thực tế.

### 1.3. Hazelcast: implementation có nhiều integration

Hazelcast là nền tảng in-memory data grid/distributed data structures; có thể dùng:

- Native Hazelcast APIs (`HazelcastInstance`, distributed `IMap`).
- Native Spring Cache adapter (`HazelcastCacheManager` qua Hazelcast Spring integration).
- JCache provider hỗ trợ JSR-107, khi dependency/version phù hợp.
- Embedded cluster members ngay trong Spring Boot processes.
- Thin clients kết nối tới một Hazelcast cluster chạy riêng.

Không gom cả ba API vào cùng service nếu không có lý do: chúng có thể dùng **tên cache, TTL, serialization, topology và lookup logic khác**.

### 1.4. Infinispan: embedded data grid và remote server

Infinispan cũng cung cấp cache/data grid, với các cách tích hợp:

- Embedded cache manager và clustered caches chạy trong JVM.
- Remote Infinispan Server qua **Hot Rod protocol**.
- Spring Cache integration thông qua adapter/starter đúng phiên bản.
- JCache provider trên những tổ hợp phiên bản/artefact có hỗ trợ.

Không xem `infinispan-core` hoặc Hot Rod client tự động là một JCache provider. Chọn **embedded/remote/JCache** trước khi quyết định dependencies.

---

## 2. Hai CacheManager có tên giống nhau nhưng khác API

Đây là nguồn nhầm lẫn nguy hiểm khi lập dependency và `@Bean`.

| Vai trò | Java type | Ai dùng |
| --- | --- | --- |
| Spring cache abstraction | `org.springframework.cache.CacheManager` | Spring `@Cacheable`, `@CachePut`, `@CacheEvict` |
| JCache standard | `javax.cache.CacheManager` | JCache `Cache<K,V>`, provider APIs |
| Adapter giữa hai lớp | `org.springframework.cache.jcache.JCacheCacheManager` | Spring annotations qua JCache provider |
| Hazelcast native adapter | `com.hazelcast.spring.cache.HazelcastCacheManager` | Spring annotations qua HazelcastInstance |
| Infinispan Spring adapter | Class do Spring integration cho version cụ thể cung cấp | Spring annotations qua embedded/remote |

Khi inject:

~~~java
import org.springframework.cache.CacheManager;

@Component
public class CacheInspector {

    private final CacheManager cacheManager;

    public CacheInspector(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public boolean hasCache(String name) {
        return cacheManager.getCache(name) != null;
    }
}
~~~

Đây là **Spring CacheManager**, không phải JCache manager. Nếu cần thao tác JCache provider-level, dùng `javax.cache.CacheManager` với import rõ ràng:

~~~java
import javax.cache.CacheManager;
import javax.cache.Caching;

CacheManager jcacheManager =
        Caching.getCachingProvider().getCacheManager();
~~~

Đoạn này chỉ thành công nếu đã có **một CachingProvider phù hợp** và cấu hình classloader/provider không mơ hồ. Nên quản lý lifecycle manager qua Spring thay vì tạo ad-hoc nhiều nơi.

### 2.1. Không import nhầm Cache

- `org.springframework.cache.Cache`: abstraction.
- `javax.cache.Cache<K,V>`: JCache entry operations.
- `com.hazelcast.map.IMap<K,V>`: distributed map native Hazelcast.
- Infinispan Cache/RemoteCache types: provider-specific.

`IMap` có distributed semantics riêng; không giả định mọi `IMap` đều là một JCache cache với cùng expiry configuration.

### 2.2. JCache trong Spring Cache là adapter, không đồng nhất annotation

Spring hỗ trợ dùng Spring caching annotations qua `JCacheCacheManager`. Spring cũng có hỗ trợ JCache annotations trong những phiên bản phù hợp. Nhưng:

- `@Cacheable` là `org.springframework.cache.annotation.Cacheable`.
- `@CacheResult` là `javax.cache.annotation.CacheResult`.
- Chúng có quy tắc chọn key, exception caching và cấu hình khác nhau.
- Không gắn cả hai lên một method rồi mặc định được “caching hai lần theo cùng key”.
- Cần kiểm tra proxy interception và provider configuration cụ thể.

Trong một service, nên chọn **một annotation programming model chủ đạo**; dùng adapter khi tích hợp thư viện legacy JCache.

---

## 3. Dependency scopes: một checklist kiến trúc

### 3.1. Các scope Gradle thường dùng

| Scope | Dùng khi | Ví dụ |
| --- | --- | --- |
| `implementation` | Code source cần compile type; hoặc application cần library | `spring-boot-starter-cache` |
| `runtimeOnly` | Chỉ cần ở runtime, không import implementation types trong code | JCache provider được phát hiện qua SPI |
| `compileOnly` | Compile API nhưng không bao gồm runtime | **Không phù hợp** nếu app runtime cần JCache API và không có ai cung cấp |
| `testImplementation` | Chỉ dùng trong test source | Testcontainers, JUnit |
| `testRuntimeOnly` | Driver/provider chỉ có trong test runtime | Test-only provider nếu đang test abstraction |
| Maven `compile` | Gần với implementation | Spring cache dependencies |
| Maven `runtime` | Chỉ cần lúc chạy | Driver/provider runtime |

Một dependency graph *tối thiểu* phụ thuộc vào **code đang import class nào**, **provider nào triển khai API**, và **Boot có auto-config hay không**.

### 3.2. Quy tắc chọn dependency

1. Có dùng `@Cacheable` và Spring Cache API? Thêm `spring-boot-starter-cache`.
2. Có viết code `javax.cache.*` hay cần JCache annotations? Thêm JCache API vào compile classpath (trực tiếp hoặc transitively, nhưng nên kiểm soát rõ).
3. Có yêu cầu JCache manager? Phải có **provider implementation** ở runtime.
4. Có gọi `HazelcastInstance`, `Config`, `IMap`? Cần Hazelcast API/implementation trên compile classpath.
5. Có gọi `HazelcastCacheManager`? Cần Hazelcast Spring integration module phiên bản tương thích.
6. Có dùng Infinispan embedded APIs? Cần embedded core + Spring integration thích hợp.
7. Có dùng remote Hot Rod client? Cần remote client/starter, server chạy riêng, auth/TLS.
8. Chỉ kiểm thử tích hợp mới dùng Testcontainers và mock HTTP/broker dependencies ở `testImplementation`.
9. Khi có nhiều provider, **khóa rõ** `spring.cache.type`, `CacheManager` bean hoặc auto-config exclusions theo version.
10. Không thêm tất cả caches để “có lựa chọn”: provider detection và classpath sẽ khó dự đoán.

### 3.3. Maven/Gradle BOM và version alignment

Với Spring Boot Gradle plugin hoặc Spring Boot dependency BOM, các libraries được Boot quản lý nên để BOM quyết định version phù hợp. Hazelcast/Infinispan Spring integrations thường yêu cầu **ma trận tương thích riêng giữa provider, Spring Framework và Spring Boot major version**.

Không kết luận `org.infinispan:infinispan-spring-boot3-starter-remote` chạy được trên Boot 4 chỉ vì compile. Nên dùng đúng starter `boot3` hoặc adapter được nhà cung cấp hỗ trợ cho Boot 4, và xác minh release notes.

**Đừng loại trừ `javax.cache` khỏi transitive dependencies một cách máy móc** chỉ vì toàn bộ app đang dùng Jakarta EE: JCache 1.x dùng `javax.cache` như namespace API chuẩn.

---

## 4. Bảng lựa chọn nhanh: Spring Cache, JCache, Hazelcast, Infinispan

| Nhu cầu | Hướng đi | Phụ thuộc tối thiểu về mặt vai trò |
| --- | --- | --- |
| Cache đơn giản một JVM | Spring Cache + Caffeine/simple | Starter + một local provider |
| Muốn thay provider qua JSR-107 | Spring Cache → `JCacheCacheManager` | Starter + `javax.cache` API + một JCache provider |
| Cluster map và Hazelcast APIs | Native Hazelcast | Starter + Hazelcast + Hazelcast Spring integration khi dùng annotations |
| Cluster JCache trên Hazelcast | Hazelcast JCache | Starter + JCache API + Hazelcast JCache-capable runtime |
| Infinispan embedded near application | Native Infinispan embedded | Starter + Infinispan embedded Spring integration |
| Infinispan Server shared cluster | Hot Rod remote | Starter + Infinispan remote Spring integration + server |
| Infinispan JCache | JSR-107 interface trên provider | JCache API + đúng Infinispan JCache module/version |
| Chỉ cần shared cache giữa pods, team đã vận hành Redis | Spring Data Redis CacheManager | Starter + Redis starter/connection config |
| Durable business events | Outbox + Kafka/RabbitMQ | **Không dùng cache thay message broker** |

**Không có “provider tốt nhất” chung.** Quyết định phụ thuộc memory footprint, topology Kubernetes, latency, failover, serialization, security, operational cost và consistency semantics.

---

## 5. JCache: JSR-107 API và dependency thực tế

### 5.1. Dependency tối thiểu qua Spring Cache

Một cấu hình Gradle minh họa cho Spring Boot 3.x khi muốn JCache:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    // JCache API: dùng khi source import javax.cache.*.
    implementation 'javax.cache:cache-api:1.1.1'

    // Chọn ĐÚNG MỘT provider có JCache implementation.
    // Ví dụ Hazelcast JCache-capable version phù hợp:
    runtimeOnly 'com.hazelcast:hazelcast'
}
~~~

**Chú ý về versions:** Dùng Boot BOM cho dependencies nó quản lý, hoặc BOM/provider versions của dự án. `cache-api:1.1.1` là một API JSR-107 1.x phổ biến, **không phải chỉ thị pin cứng bất kỳ hệ thống nào**. Hazelcast JCache availability và việc `runtimeOnly` đủ hay không tùy provider version/SPI; nếu source import `com.hazelcast.*`, phải dùng `implementation`.

**Sai lầm:** chỉ có `javax.cache:cache-api` nhưng không có SPI provider → `Caching.getCachingProvider()` không tìm thấy provider. Ngược lại, chỉ thêm Hazelcast native không có JCache API/integration chưa chắc Boot auto-create JCache manager.

### 5.2. Bảo đảm Boot chọn JCache

~~~yaml
spring:
  cache:
    type: jcache
    cache-names:
      - productsById
      - stockSnapshots
~~~

`spring.cache.type=jcache` làm rõ ý định chọn JCache trong những phiên bản Boot hỗ trợ. `cache-names` có cách provision cụ thể theo provider; **không assume** mọi provider tự tạo một named cache y như Caffeine. JCache manager thường đòi cache tồn tại/configured trước khi method `@Cacheable` chạy.

Nếu có nhiều JCache CachingProviders, chọn rõ bằng cấu hình khi Boot version hỗ trợ:

~~~yaml
spring:
  cache:
    type: jcache
    jcache:
      provider: com.hazelcast.cache.HazelcastCachingProvider
~~~

Đây là **tên provider cho các Hazelcast versions có class tương ứng**; phải xác minh actual CachingProvider class trên version đã pin. Không hardcode nhầm provider class của version cũ rồi nghĩ Boot sẽ auto-detect lại.

### 5.3. JCache cache names cần được provision

JCache provider có thể chỉ trả `null` khi `getCache("productsById")` chưa được tạo. Khi Spring `@Cacheable(cacheNames="productsById")` gọi một cache không tồn tại, phương thức có thể fail thay vì âm thầm tạo cache.

Ví dụ minh họa API JCache để tạo named cache với expiry:

~~~java
import java.util.concurrent.TimeUnit;
import javax.cache.CacheManager;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.expiry.CreatedExpiryPolicy;
import javax.cache.expiry.Duration;

public class JCacheDefinitions {

    public static void ensureProductCache(CacheManager manager) {
        if (manager.getCache("productsById") != null) {
            return;
        }

        var configuration =
                new MutableConfiguration<String, ProductDto>()
                        .setTypes(String.class, ProductDto.class)
                        .setStoreByValue(true)
                        .setExpiryPolicyFactory(
                                CreatedExpiryPolicy.factoryOf(
                                        new Duration(
                                                TimeUnit.MINUTES, 5)));

        manager.createCache("productsById", configuration);
    }
}
~~~

`ProductDto` là class ứng dụng. Code trên minh họa **expiry và JCache types**; không phải cluster-safe initialization hoàn chỉnh. Nếu nhiều pods cùng tạo cache, có thể race `getCache` → `createCache`; production nên provision qua provider configuration/Boot customizer với idempotent setup và xử lý race/conflict theo API/version.

### 5.4. JCache expiry có nghĩa gì?

- `CreatedExpiryPolicy`: TTL kể từ lần tạo entry.
- `AccessedExpiryPolicy`: expire dựa trên access theo provider semantics.
- `ModifiedExpiryPolicy`: expire sau modification theo policy.
- `EternalExpiryPolicy`: không tự expire do TTL, có thể vẫn bị eviction vì memory/resource policy.
- Provider khác nhau có cơ chế eviction, time source, cluster replication riêng.

**TTL không phải độ mới bảo đảm**. Với inventory availability, một TTL 5 phút có thể trả trạng thái cũ trong cả 5 phút nếu không có invalidation. Nếu nghiệp vụ cần đọc authoritative stock, không nên cache lệnh kiểm tra tính đủ hàng ngay tại thời điểm reserve mà thiếu validation trên DB source-of-truth.

### 5.5. Store-by-value vs store-by-reference

JCache specification có semantics store-by-value theo config và provider capabilities; `setStoreByValue(true)` thường có chi phí serialization/copy và đòi DTO có hình thức lưu trữ phù hợp. Store-by-reference (khi provider hỗ trợ) có thể làm các threads chia sẻ mutable object, gây lỗi race.

Không cache nguyên JPA entity/session-bound proxy hoặc mutable transaction object. Cache immutable DTO/snapshot rõ version, TTL và size.

### 5.6. JCache annotations khác Spring annotations

Một ví dụ dùng JCache annotation (chỉ khi Spring/JCache annotation support được cấu hình phù hợp):

~~~java
import javax.cache.annotation.CacheResult;

public class PricingService {

    @CacheResult(cacheName = "pricingBySku")
    public PriceDto price(String sku) {
        return lookupPrice(sku);
    }
}
~~~

`@CacheResult` không giống `@Cacheable` về key generation/configuration và exception caching. Đừng đổi từ Spring annotations sang JCache annotations bằng find/replace mà không test cache hits/misses và exceptions.

### 5.7. CacheManager lifecycle

Khi app shutdown, provider/JCache manager cần được close/stop theo Spring lifecycle. Không tạo `Caching.getCachingProvider().getCacheManager()` ad hoc trong mỗi request. Nếu dùng Boot-managed manager, để Boot/Spring điều phối; nếu tự tạo `@Bean`, xác định destroy method đúng và tránh duplicate provider instances.

---

## 6. Hazelcast: chọn native hay JCache trước

### 6.1. Hazelcast embedded member

Một instance Hazelcast member chạy **trong JVM của service**. Nhiều pods có thể lập cluster, chia partitions/replicas dựa trên discovery và membership. Khi pod bị terminate, dữ liệu/membership có thể cần rebalance; capacity phụ thuộc số members, backup count và memory.

Ví dụ Gradle native Spring Cache integration:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.hazelcast:hazelcast'
    implementation 'com.hazelcast:hazelcast-spring'
}
~~~

Nhà cung cấp có thể thay đổi artifact/compatibility ở major releases; kiểm tra Hazelcast Spring integration version đúng với Boot/Spring Framework đang dùng. Nếu chỉ dùng `HazelcastInstance` native không cần annotation integration, `hazelcast-spring` có thể không cần.

### 6.2. Cấu hình native HazelcastInstance + Spring CacheManager

~~~java
import com.hazelcast.config.Config;
import com.hazelcast.config.MapConfig;
import com.hazelcast.core.Hazelcast;
import com.hazelcast.core.HazelcastInstance;
import com.hazelcast.spring.cache.HazelcastCacheManager;
import org.springframework.cache.CacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class HazelcastNativeCacheConfiguration {

    @Bean(destroyMethod = "shutdown")
    HazelcastInstance hazelcastInstance() {
        Config config = new Config();
        config.setClusterName("catalog-cache-dev");

        MapConfig products = new MapConfig("productsById");
        products.setTimeToLiveSeconds(300);
        products.setMaxIdleSeconds(120);
        config.addMapConfig(products);

        return Hazelcast.newHazelcastInstance(config);
    }

    @Bean
    CacheManager cacheManager(HazelcastInstance instance) {
        return new HazelcastCacheManager(instance);
    }
}
~~~

Đây là **mẫu minh họa embedded dev/test**, không phải cấu hình Kubernetes production: cluster discovery, ports, network ACL, TLS, split brain, backup count, max-size/eviction, security và rolling upgrade cần thiết kế riêng.

`new HazelcastCacheManager(instance)` là native Spring Cache integration; **không** phải `javax.cache.CacheManager`. Đừng cấu hình thêm `spring.cache.type=jcache` rồi đồng thời tạo native manager trừ khi đã thiết kế rõ multiple managers.

### 6.3. Spring Boot auto-configuration và custom bean

Nếu ứng dụng tự định nghĩa `@Bean CacheManager`, Spring Boot cache auto-configuration thường **back off** thay vì tạo thêm default manager. Nếu đồng thời có JCache provider, Hazelcast native manager, Infinispan và Caffeine trên classpath, cần test manager thực tế được inject.

Không hardcode `spring.cache.type=hazelcast` rồi tạo một bean `JCacheCacheManager` thủ công và coi cấu hình vẫn “theo YAML”: manual bean có thể quyết định behavior khác.

### 6.4. Hazelcast client/server topology

Trong client/server, Spring Boot instance không nhất thiết là Hazelcast cluster member. Thay vào đó, `HazelcastClient` kết nối tới cache cluster chạy riêng. Đây thường là mô hình hợp lý nếu muốn scale business pods độc lập với cache nodes.

~~~mermaid
flowchart LR
    A["Catalog pod A"] --> C["Hazelcast client"]
    B["Catalog pod B"] --> D["Hazelcast client"]
    C --> H["Hazelcast cluster"]
    D --> H
    H --> M1["Data member 1"]
    H --> M2["Data member 2"]
    H --> M3["Data member 3"]
~~~

Một client vẫn phụ thuộc network connectivity, cluster membership, connection retry và credentials. Nếu cluster down, cache reads/writes có thể throw/time out; **fail-open** với DB fallback hay **fail-closed** cần quyết định theo semantics của từng cache.

### 6.5. Hazelcast native TTL khác JCache TTL config

Hazelcast `MapConfig#setTimeToLiveSeconds` và `setMaxIdleSeconds` cấu hình **native IMap**. Khi dùng JCache provider, cache expiry có thể đến từ `javax.cache.expiry.ExpiryPolicy` hoặc provider-specific config. Không assume hai đường cấu hình tương tác như một bộ cache duy nhất.

### 6.6. Hazelcast JCache dependency tối thiểu

Nếu đã chọn JCache API để giảm phụ thuộc vào Hazelcast types:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'javax.cache:cache-api:1.1.1'
    runtimeOnly 'com.hazelcast:hazelcast'
}
~~~

Đây là **một lựa chọn khác** so với native Hazelcast; không cần `hazelcast-spring` chỉ vì project muốn dùng JCache Spring bridge, nếu provider/version đã đủ. Tuy nhiên, một số Hazelcast class/configuration vẫn cần compile dependency nếu source trực tiếp import chúng.

### 6.7. Khi nào chọn native Hazelcast API?

Chọn native khi thực sự cần distributed `IMap` operations, entry processors, cluster map listeners hoặc semantics đặc thù; đổi lại application phụ thuộc provider và cần review migrations.

Chọn JCache khi muốn standardized cache API và bộ tính năng cần thiết nằm trong chuẩn. Không cố che mọi provider-specific behavior qua JCache nếu requirements là cluster transactions/events/partition awareness phức tạp.

---

## 7. Infinispan: embedded, remote và JCache là ba hướng khác nhau

### 7.1. Embedded cache

Embedded Infinispan chạy trong JVM, hỗ trợ local và clustered caching tùy cấu hình mode/membership. Trong integration, embedded mode có thể phù hợp nếu độ trễ rất thấp và đội kiểm soát cluster topology; nhưng mỗi business pod sẽ đóng vai trò data-grid member.

Gradle **minh họa cho nhánh Spring Boot 3**, phụ thuộc nhà cung cấp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    // Cài đặt đúng dòng starter được Infinispan hỗ trợ
    // cho Spring Boot 3 và version Infinispan đang pin:
    implementation 'org.infinispan:infinispan-spring-boot3-starter-embedded'
}
~~~

Không dùng tên artifact trên như cam kết tự chạy với Boot 4. Kiểm tra Infinispan release/version compatibility và BOM của dự án. Nếu ứng dụng chỉ cần direct Infinispan APIs mà không dùng Spring Cache annotations, provider-specific starter có thể không cần.

### 7.2. Remote Hot Rod

Remote mode có Infinispan Server cluster và Spring Boot sử dụng Hot Rod client. Ưu điểm: tách lifecycle/cache capacity khỏi business pods; đổi lại thêm network, TLS, auth, server HA, data serialization và protocol compatibility.

Gradle minh họa:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    // Nhánh starter remote dành cho Spring Boot 3,
    // cần đối chiếu compatibility của đúng release:
    implementation 'org.infinispan:infinispan-spring-boot3-starter-remote'
}
~~~

Cấu hình connection credentials/server-list phụ thuộc dòng Spring Boot starter và Hot Rod client. Để tránh đưa một property name sai, hãy đọc configuration metadata của **đúng starter/version** trong dự án khi triển khai; cấu hình server address, TLS CA/hostname, SASL auth, timeouts, topology refresh và cache names theo provider docs.

### 7.3. JCache provider của Infinispan

Khi muốn `javax.cache` thay vì Infinispan-specific APIs, một số Infinispan releases cung cấp module JCache như `org.infinispan:infinispan-jcache`, và chế độ remote có thể khác artifact/capabilities.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'javax.cache:cache-api:1.1.1'

    // Chỉ nếu Infinispan release này thực sự cung cấp
    // CachingProvider JSR-107 tương thích:
    runtimeOnly 'org.infinispan:infinispan-jcache'
}
~~~

**Không mặc định dùng được mọi cặp version.** Kiểm tra implementation tương thích với JCache 1.x và Spring major version; xác minh provider bằng SPI, không assume `infinispan-core` hay Hot Rod client tự triển khai JCache.

### 7.4. Topology và cache modes của Infinispan

Các cache modes như local, distributed, replicated hoặc invalidation có semantics/cost khác nhau:

| Mode | Ý tưởng | Rủi ro/cost |
| --- | --- | --- |
| Local | Entry chỉ trong JVM | Mỗi pod thấy cache khác nhau |
| Replicated | Nhân bản nhiều members | Network/memory theo số replicas |
| Distributed | Partition + owners/backup | Rebalance, topology/partition awareness |
| Invalidation | Thông báo invalidation giữa nodes | Cache misses vẫn cần source-of-truth |
| Remote Hot Rod | Client gọi server cluster | Network/auth/TLS/service availability |

**Không nhầm invalidation mode với shared distributed storage**: trong invalidation configuration, các nodes không nhất thiết lưu cùng giá trị; chúng chỉ invalidation local copies khi có update theo protocol.

### 7.5. Serialization của Infinispan không tự như JSON

Remote Hot Rod thường cần marshalling schema/protocol policy rõ, chẳng hạn Protostream/Protobuf ở các Infinispan versions. Native Java serializable DTO, JSON HTTP contract và Hot Rod ProtoStream encoding **không mặc nhiên tương đương**.

Đặc biệt với rolling deployment:

- DTO field added/removed phải có compatibility tests.
- Không gửi JPA entity có lazy proxies/session state.
- Classloader/type aliases có thể làm cache values không đọc được sau deploy.
- Cache key schema cũng có thể thay đổi; không chỉ value schema.
- Chuẩn bị versioned keys hoặc explicit migrations/invalidation.

---

## 8. Tránh nhầm auto-detection của Spring Boot

Khi không tự khai báo `CacheManager`, Spring Boot có thể auto-configure dựa trên classpath và properties. Có nhiều providers cùng hiện diện thì kết quả có thể không như đội dự định.

Một số dòng Boot 3.x ưu tiên **JCache integration khi provider cũng có native implementation**, vì JCache có standardized API. Nhưng thứ tự selection, supported providers và điều kiện back-off là **version-specific**; không đưa ra một thứ tự cố định cho mọi Boot release.

### 8.1. Khóa loại cache rõ trong cấu hình

~~~yaml
spring:
  cache:
    type: jcache
~~~

hoặc theo hệ thống/chế độ native mà release Spring Boot đang hỗ trợ:

~~~yaml
spring:
  cache:
    type: hazelcast
~~~

hoặc:

~~~yaml
spring:
  cache:
    type: infinispan
~~~

**Cảnh báo:** `spring.cache.type=infinispan`/`hazelcast` chỉ có hiệu lực nếu implementation auto-configuration của **Boot + starter/provider** tương ứng tồn tại. Với provider native Spring integration do thư viện bên ngoài tự cấu hình, có thể phải dùng một `@Bean CacheManager` cụ thể và không rely vào Boot `spring.cache.type`.

### 8.2. Nhiều CacheManager có chủ ý

Nếu cần cache khác nhau theo domain, có thể có named CacheManagers và chọn trong annotation:

~~~java
@Cacheable(
        cacheNames = "stockSnapshots",
        key = "#sku",
        cacheManager = "stockCacheManager")
public StockSnapshot getStock(String sku) {
    return inventory.readStock(sku);
}
~~~

Hoặc khai báo `CacheResolver` khi cần routing phức tạp. Nhưng với nhiều managers:

- `@Primary`/qualifier phải rõ.
- Test actual bean type theo environment.
- Cache names/keys không trùng một cách tình cờ.
- Không giả định cache eviction từ manager A ảnh hưởng manager B.
- Nếu có Spring Cache abstraction và JCache annotations song song, cần hiểu interceptor/cache manager nào thực thi.

### 8.3. Xác minh runtime type thay vì đoán

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;

@Component
public class CacheManagerDiagnostics {

    public CacheManagerDiagnostics(CacheManager manager) {
        // Chỉ log class name ở startup, không log secrets/cache data.
        System.out.println("Spring CacheManager: " +
                manager.getClass().getName());
    }
}
~~~

Trong production dùng logger và actuator diagnostics thay `System.out`; kiểm tra cả số instances/provider mode và cluster membership. Nếu kỳ vọng Hazelcast cluster mà nhận `ConcurrentMapCacheManager`, dữ liệu có thể chỉ tồn tại **tại pod hiện tại**, gây stale reads.

---

## 9. Cache names, keys và scope dữ liệu

Một method Spring Cache:

~~~java
@Cacheable(
        cacheNames = "productCatalog",
        key = "#tenantId + ':' + #productId",
        unless = "#result == null")
public ProductDto getProduct(
        String tenantId, String productId) {

    return repository.findProduct(tenantId, productId);
}
~~~

### 9.1. Keys không chứa secrets và phải đầy đủ phân vùng

Key phải bao gồm **mọi input ảnh hưởng business result**, ví dụ `tenantId`, `locale`, `currency`, `catalogVersion`, pricing tier nếu cần. Thiếu tenantId có thể rò dữ liệu tenant A sang tenant B.

Không đưa access token, raw email hay PII vào keys vì keys có thể lộ qua metrics/log/debug tools. Dùng opaque stable IDs được phép và namespacing phù hợp.

### 9.2. Cache key/value schema version

Khi schema/semantics thay đổi, ví dụ cache v1 lưu `amount` theo đơn vị đồng, cache v2 lưu `amountMinor`, nên version key:

~~~text
product:v1:tenant-10:sku-100
product:v2:tenant-10:sku-100
~~~

Một network cache chung giữa pods chạy v1/v2 có thể chứa cả formats. Dù JSON value parse được, dữ liệu có thể sai nghĩa. Versioned keys/serialization adapters và TTL rollout quan trọng như API contract versioning.

### 9.3. Cache keys là data contract lâu hơn một request

Cache value có thể sống qua:

- Rolling deployment và rollback.
- Thay đổi DTO package/class name.
- Failover sang node khác.
- TTL nhiều ngày.
- Persistent store/passivation hoặc disk-tier (nếu provider hỗ trợ).

Nếu cache chỉ là dữ liệu phái sinh, một phương án đơn giản là invalidate versioned namespace cũ. Nhưng việc invalidate hàng triệu keys cùng lúc có thể gây **cache stampede**, đẩy tải lớn về PostgreSQL/HTTP partner. Cần warming/rollout theo từng nhóm.

### 9.4. Không cache mutable JPA entities

Nên cache DTO bất biến:

~~~java
public record ProductSnapshot(
        String productId,
        String displayName,
        long catalogVersion) {
}
~~~

Không cache `EntityManager`, `Connection`, `Session`, mutable transaction context, JPA lazy proxy hoặc authorization-sensitive entity rồi cho nhiều threads/pods dùng chung.

---

## 10. TTL, expiry, eviction và consistency

### 10.1. Tại sao “TTL=5 phút” không là hợp đồng freshness?

Một snapshot tồn kho có TTL 5 phút có thể cũ tới gần 5 phút. Nếu trong lúc đó inventory đã bị giữ hết, đọc cache để **thực hiện reserve** có thể gây oversell nếu không có kiểm tra atomic ở source-of-truth.

Có thể cache:

- Catalog description, product details, feature flags có version.
- Inventory display snapshot với freshness disclaimer.
- Remote reference data không cần strong consistency.
- HTTP partner tokens/metadata khi hợp đồng TTL rõ, không log secrets.

Không nên lấy stale cache làm sự thật cuối cùng cho:

- Kiểm tra số dư thanh toán.
- Trừ tồn kho cuối cùng.
- Authorization/tenant entitlement thay đổi tức thời.
- Distributed lock.
- Idempotency record duy nhất không có persistence phù hợp.

### 10.2. Bảng expiry vs eviction vs invalidation

| Cơ chế | Ý nghĩa | Không bảo đảm |
| --- | --- | --- |
| TTL/expiry | Entry tự hết hạn sau thời gian/policy | DB đã đồng bộ ngay |
| Max idle | Entry hết hạn nếu không truy cập đủ lâu | Business source-of-truth cập nhật |
| Size-based eviction | Provider đẩy entry ra khi memory pressure | LRU/LFU semantics giống nhau giữa providers |
| Explicit eviction | Ứng dụng chủ động loại key | Eviction atomically với DB COMMIT |
| Event-driven invalidation | Consumer nhận change event và xóa/refresh | Không có lag/duplicate/reorder |
| Write-through/write-behind | Provider hỗ trợ write policy | Distributed ACID với DB ngoài |
| Refresh-ahead | Nạp mới trước expiry | Không tăng tải/upstream quota |
| Versioned key | Đổi namespace schema | Dữ liệu thật luôn fresh |

Một cache provider có thể có eviction do memory pressure trước TTL. **TTL không phải minimum retention.**

### 10.3. Cluster replication và stale values

Distributed cache không đồng nghĩa mọi read là **linearizable** hoặc atomic cùng database. Network partition, failover, backup replication policy, async persistence và read-after-write guarantees khác nhau theo provider/config.

Khi thiết kế cần hỏi:

1. Cache là cache-aside hay authoritative state?
2. Mức stale tối đa được chấp nhận là bao nhiêu?
3. Write failure có rollback business transaction không?
4. Node failover có thể mất cache entry không?
5. Khi split brain, cache có cơ chế conflict resolution gì?
6. Client đọc stale có ảnh hưởng tiền/tồn kho/quyền không?

Nếu cần strong invariant, lưu source-of-truth trong database có transactions/constraints phù hợp; cache là performance optimization.

---

## 11. Spring cache annotations: hiểu đúng hit/miss/update

### 11.1. @Cacheable

~~~java
@Cacheable(cacheNames = "productsById", key = "#id")
public ProductDto get(String id) {
    return database.load(id);
}
~~~

- Cache hit: tránh method body theo proxy.
- Cache miss: gọi method, sau đó cache kết quả theo policy.
- Key generator/serialization quyết định identity.
- Exception thường không được cache bởi Spring `@Cacheable` theo cơ chế mặc định.
- `@Cacheable(sync = true)` có giới hạn bởi Cache implementation và **không đồng nghĩa distributed single-flight across pods**.

### 11.2. @CachePut

~~~java
@CachePut(cacheNames = "productsById", key = "#result.id")
public ProductDto update(String id, ProductPatch patch) {
    return database.update(id, patch);
}
~~~

`@CachePut` luôn gọi method rồi cập nhật cache theo result, không phải đọc cache hit. Chú ý result key null/error paths và transactional consistency.

### 11.3. @CacheEvict

~~~java
@CacheEvict(cacheNames = "productsById", key = "#id")
public void delete(String id) {
    database.delete(id);
}
~~~

Cache eviction theo Spring caching interceptor không tự là một transaction với database. Nếu method throw/rollback hoặc transaction callback order khác kỳ vọng, có thể gây stale/cold state.

### 11.4. Self-invocation

~~~java
@Service
class ProductService {

    public ProductDto fetch(String id) {
        return cachedFetch(id); // self-invocation: bỏ qua proxy.
    }

    @Cacheable("productsById")
    public ProductDto cachedFetch(String id) {
        return repository.load(id);
    }
}
~~~

Với Spring proxy-based cache interception, gọi `this.cachedFetch` trong cùng bean không đi qua proxy. Tách method cache sang bean khác hoặc gọi qua Spring-managed proxy; đừng lấy việc cache provider khỏe làm bằng chứng annotation đang chạy.

 
## 12. Transaction boundary: cache update không phải SQL COMMIT

Một cập nhật thông thường:

~~~text
HTTP PUT /products/100
  -> @Transactional service
  -> PostgreSQL UPDATE products
  -> @CachePut / @CacheEvict
  -> SQL COMMIT
~~~

Câu hỏi quan trọng: **Cache được cập nhật trước hay sau khi SQL transaction thực sự COMMIT?** Nếu cache put diễn ra trước commit, một transaction rollback có thể để lại giá trị cache **không tồn tại trong database**. Nếu commit thành công nhưng eviction thất bại, cache có thể tiếp tục trả giá trị cũ.

### 12.1. Những cửa sổ lỗi cần nhận diện

| Cửa sổ | Database | Cache | Rủi ro |
| --- | --- | --- | --- |
| Cache put xong, SQL rollback | Old value | New value | Đọc dữ liệu chưa từng được commit |
| SQL COMMIT xong, cache eviction fail | New value | Old value | Stale cache |
| App crash sau COMMIT trước eviction | New value | Old value | Stale tới TTL/invalidation khác |
| Event invalidation đến trước COMMIT | Chưa có new value | Cache bị xóa rồi tải lại old value | Cache bị repopulate với old value |
| Nhiều pods update cùng key | Bản cuối theo DB/version | Arrival order khác | Cache nhận older update sau newer |
| Cache cluster partition | DB vẫn commit | Một số nodes có stale value | Divergent reads |

**Không có distributed transaction** tự động giữa PostgreSQL và Hazelcast/Infinispan chỉ vì `@Transactional` và `@CacheEvict` cùng nằm trên một method.

### 12.2. Transaction-aware Spring Cache decorator

Spring cung cấp `TransactionAwareCacheManagerProxy`/`TransactionAwareCacheDecorator` để **trì hoãn một số cache put/evict/clear operations đến sau khi transaction commit** khi có transaction synchronization hoạt động.

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.transaction.TransactionAwareCacheManagerProxy;
import org.springframework.context.annotation.Bean;

// Giả sử delegate là native/JCache CacheManager do bạn tạo,
// không phải cùng Spring CacheManager bean này.
@Bean
CacheManager transactionAwareCacheManager(
        @Qualifier("providerCacheManager") CacheManager delegate) {

    return new TransactionAwareCacheManagerProxy(delegate);
}
~~~

Snippets trong bài phải được lắp vào configuration có imports đầy đủ, bean names rõ và **không tạo circular dependency**. Với `@Qualifier`, import `org.springframework.beans.factory.annotation.Qualifier`.

**Giới hạn:** Decorator này không biến cache và DB thành một ACID transaction. Một số thao tác như `putIfAbsent` có semantics immediate; trên path có `beforeInvocation=true` hoặc annotation ordering khác, không assume tất cả eviction được delay. Nếu eviction sau SQL COMMIT thất bại, DB vẫn đã commit. Phải có TTL/reconciliation và test rollback/failure window.

### 12.3. Lộ trình an toàn hơn cho dữ liệu quan trọng

- DB là **source of truth**.
- Trong SQL transaction, update business row và ghi outbox event có `aggregateVersion`.
- Relay/consumer sau COMMIT invalidates/refreshes cache.
- Cache keys có tenant/version scope.
- Consumer xử lý trùng event idempotently.
- Nếu cache unavailable, choose fail-open/fail-closed theo semantics.
- TTL là safety net, không phải bằng chứng mọi pods đều đã thấy update.

~~~mermaid
sequenceDiagram
    participant A as Product API
    participant D as PostgreSQL
    participant O as Outbox worker
    participant C as Cache cluster
    A->>D: BEGIN update product + INSERT outbox
    D-->>A: COMMIT
    O->>D: Claim outbox event
    O->>C: Invalidate product key
    C-->>O: ACK / timeout
    O->>D: Mark event processed or retry
~~~

Trong network partition, cache invalidation có thể thất bại; outbox lưu ý định invalidation để retry. Nếu client đọc cache stale trong khoảng chờ, contract phải chấp nhận eventual consistency hoặc route critical read vào database.

### 12.4. Đừng giữ DB transaction khi chờ cache cluster

Một transaction có thể giữ locks/Hikari connection trong khi chờ cache network timeout. Với cache-aside không critical, tránh chặn SQL COMMIT kéo dài chỉ để cập nhật cache. Transaction boundary nên ngắn; retry/outbox/invalidation nằm ngoài SQL transaction nếu cần.

---

## 13. Cache stampede và thundering herd

Một cache entry thường rất nóng: `product:tenant-1:SKU-100`. Khi TTL hết cùng lúc trên 10 pods, rất nhiều requests cùng thấy cache miss rồi đổ xuống PostgreSQL hoặc HTTP partner.

~~~mermaid
flowchart TD
    A["Cache key expires"] --> B["10 pods × 100 concurrent requests"]
    B --> M["Cache MISS storm"]
    M --> P["PostgreSQL Hikari pool max 12 per pod"]
    M --> H["Inventory HTTP partner quota"]
    P --> E["Connection wait / timeout"]
    H --> F["HTTP 429 / 503"]
    E --> R["Retries amplify load"]
    F --> R
~~~

### 13.1. Vì sao chỉ tăng cache size không giải quyết?

Stampede là vấn đề **đồng thời tạo giá trị**, không chỉ cache capacity. Một key có thể bị evict vì size policy, TTL, deployment invalidation hoặc provider failover.

### 13.2. Giảm stampede theo tầng

| Công cụ | Bảo vệ | Lưu ý |
| --- | --- | --- |
| TTL jitter | Phân tán thời điểm expire nhiều keys | Hot key vẫn có thể bị nhiều requests cùng miss |
| `@Cacheable(sync=true)` | Có thể giảm nhiều threads cùng load **trong một cache implementation/local JVM** | Không tự đảm bảo cluster-wide coordination |
| Local single-flight per key | Coalesce requests cùng key trong pod | Pods khác vẫn cùng fetch |
| Distributed lock/lease | Giảm duplicate refresh xuyên nodes | Phức tạp lease/fencing/failure |
| Stale-while-revalidate | Trả snapshot cũ trong lúc refresh | Chỉ dùng nếu stale hợp lệ |
| Refresh-ahead | Nạp lại trước expire | Tăng upstream load |
| Bounded HTTP/DB concurrency | Ngăn áp lực lên downstream | Có thể tăng wait/reject |
| Prewarming/canary invalidation | Giảm cold-start surge | Cần capacity plan |

Không giữ một distributed lock trong lúc làm network call không có timeout. Khi lock/lease hết hạn, hai refreshers có thể cùng chạy; nếu refresh làm side effect, phải có fencing/idempotency.

### 13.3. @Cacheable(sync=true) không phải distributed mutex

~~~java
@Cacheable(
        cacheNames = "productCatalog",
        key = "#tenantId + ':' + #id",
        sync = true)
public ProductDto get(String tenantId, String id) {
    return database.load(tenantId, id);
}
~~~

`sync=true` yêu cầu Spring cache abstraction đồng bộ hóa value loading khi provider hỗ trợ `Cache.get(key, Callable)`. Cơ chế/độ mạnh khác nhau tùy adapter/provider; **không kết luận** nhiều Hazelcast/Infinispan nodes có một global lock. Viết integration test nhiều pods nếu điều đó là yêu cầu.

### 13.4. Negative caching

Một API hay trả 404 cho SKU không tồn tại có thể cache “not found” để giảm DB calls, nhưng phải định nghĩa TTL ngắn và semantics khi SKU được tạo sau đó.

`@Cacheable(unless = "#result == null")` là một lựa chọn **không cache null**, không phải negative caching. Cách cache “not found” có thể dùng sentinel/optional DTO theo provider capabilities; tránh cache permanent 404 từ một lỗi partner transient.

---

## 14. Resilience: cache unavailable thì làm gì?

Hazelcast/Infinispan cluster có thể unavailable do network partition, rolling restart, auth/TLS fail hoặc capacity exhaustion. Khi đó `@Cacheable` có thể throw ngay trong read/write cache operations.

### 14.1. Fail-open vs fail-closed

| Loại cache | Fail-open về DB/source? | Vì sao |
| --- | --- | --- |
| Product descriptions | Thường có thể | Cache chỉ tối ưu hiệu năng |
| Stock UI snapshot | Có thể, với bounded DB capacity | Cần loại bỏ stale data |
| Auth revocation/entitlement | Không mặc định | Đọc stale có thể tạo security bug |
| Idempotency ledger | **Không** nếu chỉ nằm trong cache | Duplicate side effect |
| Distributed lock | **Không** | Mất mutual exclusion |
| Rate-limit counters | Theo threat model | Fail-open có thể vượt quota/abuse |
| Cached OAuth tokens | Cần contract bảo mật | Token expiry/refresh chính xác |

**Quy tắc:** Chỉ fail-open nếu source-of-truth còn khả dụng và tải miss được kiểm soát. Nếu mọi pods fallback trực tiếp xuống DB với throughput lớn hơn DB chịu được, fail-open có thể biến cache outage thành toàn bộ system outage.

### 14.2. Spring CacheErrorHandler: fail-open có điều kiện

Spring mặc định thường để cache errors lan ra caller. Với dữ liệu **read-only, cache chỉ tối ưu**, có thể bỏ qua cache **GET error** để tính lại từ nguồn nhưng vẫn phải đo, rate-limit và không che lỗi eviction/write.

Ví dụ:

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheErrorPolicy implements CachingConfigurer {

    @Override
    public CacheErrorHandler errorHandler() {
        return new CacheErrorHandler() {
            @Override
            public void handleCacheGetError(
                    RuntimeException exception, Cache cache, Object key) {
                // Log/metric có redaction tại đây.
                // Chỉ nuốt GET error khi contract cho phép
                // fallback về method body và đã giới hạn tải.
            }

            @Override
            public void handleCachePutError(
                    RuntimeException exception, Cache cache,
                    Object key, Object value) {
                throw exception;
            }

            @Override
            public void handleCacheEvictError(
                    RuntimeException exception, Cache cache, Object key) {
                throw exception;
            }

            @Override
            public void handleCacheClearError(
                    RuntimeException exception, Cache cache) {
                throw exception;
            }
        };
    }
}
~~~

**Không dùng cấu hình này nguyên xi cho mọi cache.** Nếu một method `@Cacheable` gọi DB cực đắt, nuốt cache GET error có thể tạo thundering herd. `CacheErrorHandler` không sửa semantics của provider connection retries, transactions hoặc global consistency.

### 14.3. Timeout budget

Một request có deadline tổng 2 giây không thể chờ cache acquire 3 giây rồi database thêm 5 giây. Cần cấu hình:

- Cache client connection timeout.
- Socket/read timeout.
- Number of retries/reconnect attempts.
- Fallback source timeout.
- HTTP request deadline.
- Circuit breaker/bulkhead.
- Graceful degraded response nếu contract cho phép.

Đừng retry một cache operation 10 lần rồi retry cả HTTP request 10 lần; tổng attempts có thể nhân lên.

### 14.4. Cache write failure sau DB COMMIT

Nếu SQL đã COMMIT nhưng cache invalidation throw, client có thể nhận lỗi dù business update đã thành công. Với idempotency-sensitive operations, không retry thành một business command mới. Dùng operationId, persisted receipt và background invalidation retry. Lỗi cache là **lỗi đồng bộ bản sao**, không tự làm business transaction biến mất.

---

## 15. Hazelcast và Infinispan trong Kubernetes

### 15.1. Embedded member vs remote client

~~~mermaid
flowchart TD
    A["Spring Boot pods"] --> E{"Topology?"}
    E --> HM["Embedded members trong mỗi pod"]
    E --> RC["Client-server: thin clients trong pods"]
    HM --> D1["Pod membership + partition/backup rebalance"]
    RC --> D2["Cache cluster/service chạy riêng"]
    D1 --> C["Failover, discovery, capacity, security"]
    D2 --> C
~~~

**Embedded** có ít network hops trong một số trường hợp, nhưng business autoscaling đồng thời thêm/bớt cache members, khiến partitions và backup rebalance. **Remote** tách data-grid lifecycle khỏi business deployment nhưng phụ thuộc Hot Rod/Hazelcast client connectivity và cache cluster vận hành riêng.

### 15.2. Discovery và cluster name

Hazelcast/Infinispan clustering cần node discovery (Kubernetes API, DNS, static addresses hoặc provider-specific mechanisms). Không dùng multicast dev default và mong production K8s có cluster đúng.

- Cluster name và service discovery config phải giống giữa các intended members.
- Tách dev/test/staging/prod và tenants khi yêu cầu.
- Network policies chỉ cho ports/giao thức cần thiết.
- Có split-brain protection/quorum policy nếu dùng cache làm state không thể mất.
- Backup counts phải phù hợp số cache nodes thực.
- Theo dõi rebalancing/partition migration khi autoscale.

### 15.3. Deploy nhiều versions

Một cluster cache chung có thể chứa values do code v1 serialize và code v2 deserialize. Nếu Java serialization chứa class/package name, rolling upgrade có thể lỗi `ClassNotFoundException`, `InvalidClassException` hoặc codec mismatch.

Ưu tiên provider-supported stable schema formats, versioned cache keys/values, test mixed versions và upgrade compatibility. Không cache JPA entity hoặc mutable class có thể thay field ngầm qua Lombok.

### 15.4. Resource accounting

Cache data grid members và application cùng JVM có thể tranh heap, CPU, GC và network. Khi dùng embedded mode:

- Memory cache phải tính cùng heap/GC budget của business service.
- Backup copies/replication làm tăng total memory.
- Large payload serialization gây CPU pressure.
- Cache warmup sau restart có thể gây DB spike.
- Partition migration làm network/CPU tăng.
- Max-size/eviction cần được cấu hình theo provider.

Không chỉ tính `number of keys × average value bytes`: metadata, indexes, backup replicas, serialization buffers và GC overhead cũng đáng kể.

---

## 16. Dependency conflict và classpath hygiene

### 16.1. Những dependencies dễ thêm sai

| Dependency | Dùng cho | **Không** tự có nghĩa |
| --- | --- | --- |
| `spring-boot-starter-cache` | Spring Cache abstraction | Có JCache provider |
| `javax.cache:cache-api` | JSR-107 interfaces | Có implementation |
| `com.hazelcast:hazelcast` | Hazelcast engine/API, JCache support tùy version | Spring native manager luôn được chọn |
| `com.hazelcast:hazelcast-spring` | Native Hazelcast Spring integration | Phải thêm khi chỉ dùng JCache |
| Infinispan embedded starter | Spring/Infinispan embedded integration | Kết nối remote Hot Rod server |
| Infinispan remote starter | Hot Rod remote Spring integration | Embedded cache member |
| `org.infinispan:infinispan-jcache` | JCache provider ở supported versions | Hỗ trợ mọi Boot/provider combination |
| `hibernate-jcache` | Hibernate second-level caching | Tương đương Spring `@Cacheable` |
| `spring-boot-starter-data-redis` | Redis data/cache integration | Dùng chung data/TTL với Hazelcast |
| Testcontainers | Integration test infrastructure | Production cache provider |

### 16.2. Hibernate second-level cache là scope riêng

Nếu JPA/Hibernate dùng second-level cache thông qua JCache, có thể xuất hiện `hibernate-jcache`. Nhưng **Hibernate L2 cache regions** không phải Spring `@Cacheable` regions mặc định.

- Entity L2 cache có persistence context/region invalidation semantics riêng.
- Query cache là một tính năng khác cần cân nhắc invalidation.
- Không bật L2 cache chỉ vì dùng Spring Cache.
- Cùng provider cluster có thể chứa regions khác nhau nhưng phải cấu hình names/TTLs/quota riêng.
- Update entity và Spring business DTO cache không tự invalidate lẫn nhau.

### 16.3. Spring Session khác result cache

Spring Session có backend/session TTL/token isolation riêng. Không trộn session cache với business result cache chỉ vì cùng Hazelcast/Redis/Infinispan instance. Authentication/session state có security invariants và failover policy khác catalog descriptions.

### 16.4. Kiểm tra provider SPI khi dùng JCache

`Caching.getCachingProviders()` có thể trả nhiều providers nếu nhiều implementations có trên classpath. Khi đó `Caching.getCachingProvider()` không có selection rõ theo business config; Boot JCache provider property/explicit provider bean cần được chọn.

~~~java
import javax.cache.Caching;
import javax.cache.spi.CachingProvider;

for (CachingProvider provider : Caching.getCachingProviders()) {
    System.out.println(
            "JCache provider=" + provider.getClass().getName());
}
~~~

Dùng startup diagnostics có kiểm soát; **không in credentials/config secrets**. Nếu provider count >1, phải chỉ định provider mong muốn theo phiên bản đang dùng.

### 16.5. Dependency scopes trong test

Nếu production app chạy Hazelcast native, nhưng unit tests dùng `ConcurrentMapCacheManager`, cần test ít nhất một nhóm với provider thực:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Với provider embedded, có thể tạo 1–2 embedded members riêng biệt trong tests. Với remote Infinispan, dùng container/server tương thích thay vì mock API; nếu dùng Hazelcast/Kubernetes multi-node networking, chạy isolated integration environment theo CI capacity.

Không cần ép tất cả unit tests khởi động distributed cluster; phân tầng test fast vs integration.

---

## 17. Kiểm thử đúng CacheManager và cache provider

### 17.1. Assert provider đã được Boot chọn

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.CacheManager;
import org.springframework.cache.jcache.JCacheCacheManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(properties = "spring.cache.type=jcache")
class JCacheSelectionTest {

    @Autowired
    CacheManager manager;

    @Test
    void usesJCacheBridge() {
        assertInstanceOf(JCacheCacheManager.class, manager);
    }
}
~~~

Test chỉ chạy xanh nếu **JCache provider thực** có trên test/runtime classpath và manager không bị custom bean/transaction-aware wrapper khác bao ngoài. Nếu wrapper dùng `TransactionAwareCacheManagerProxy`, assert class trực tiếp sẽ fail dù delegate là JCache; lúc đó kiểm tra wrapper/delegate qua test setup phù hợp.

Không lạm dụng Spring context mock manager trong test này vì mục đích là xác minh **provider selection**.

### 17.2. Test cache hit/miss qua Spring proxy

Một test nên gọi **Spring bean đã được proxy**, không gọi `new ProductCatalogService(repository)` rồi trông đợi `@Cacheable` có tác dụng.

~~~text
Given cache productsById được tạo
And repository có một product DTO
When Spring bean getProduct("P-100") được gọi hai lần
Then repository được gọi một lần theo contract
And hai kết quả tương đương
~~~

Nếu method self-invocation, proxy intercept không chạy; test trên trực tiếp method có thể vô tình không kiểm tra cache.

### 17.3. Test TTL/expiry không nên dựa sleep cực ngắn

~~~text
Given cache TTL 5 seconds
When write product P-100 at t0
Then before expiry read => HIT
And after expiry => MISS/reload
~~~

Dùng provider clock/test support nếu có; nếu integration test phải chờ TTL thật, đặt timeouts và margin đủ để giảm flaky scheduler; không chọn `Thread.sleep(5)` rồi assert expired.

JCache `CreatedExpiryPolicy` và Hazelcast native map TTL có semantics khác nhau, phải chạy đúng provider test.

### 17.4. Test clustered visibility

~~~text
Given instance A và instance B dùng đúng cluster/namespace
When A put cache entry K
Then B read K theo consistency contract đã công bố
When A evicts K
Then B không trả stale vượt allowed window
~~~

Test một JVM, một manager không chứng minh distributed cache. Có thể cần 2 JVM/pods/clients để loại trừ việc vô tình dùng local fallback.

### 17.5. Test serialization qua nhiều versions

~~~text
Given v1 application writes ProductSnapshotV1 into shared cache
When v2 application reads same key
Then decode thành dữ liệu hợp lệ hoặc chủ động MISS/migrate
And không thay currency/unit/schema nghĩa nghiệp vụ
~~~

Tương tự, rollback v2 → v1 phải xét cache values đã ghi bằng serializer mới. Không kết luận rolling upgrade an toàn chỉ vì v2 đọc được chính data do nó tạo.

### 17.6. Test cache outage và DB fallback

- Chặn cache cluster connection bằng fault proxy/network.
- Gửi truy vấn đọc cacheable.
- Xác minh timeout/fallback đúng policy.
- Không có unbounded queue/retry storms.
- Hikari pending và HTTP partner QPS vẫn nằm trong budget.
- Với auth/idempotency-sensitive cache, xác minh fail-closed.
- Khi cache trở lại, không có stale-data overwrite sau concurrent updates.

---

## 18. Test SQL transaction và invalidate

### 18.1. Rollback scenario

~~~text
Given P-100 version=3 trong PostgreSQL và cache
When transaction update P-100 version=4
And SQL rollback
Then PostgreSQL vẫn version=3
And cache không được phát version=4 như committed
~~~

Nếu dùng `TransactionAwareCacheManagerProxy`, test cả success/rollback và những operations không bị defer. Không chỉ nhìn annotation `@Transactional` để suy luận transaction ordering đúng.

### 18.2. Commit then cache outage

~~~text
Given P-100 version=3 trong cache
When SQL COMMIT version=4
And cache invalidation fails due to cluster outage
Then durable invalidation intent vẫn pending
And business transaction không bị thực hiện lần hai
When cache recovers
Then consumer invalidates/refreshes key
And stale version=3 không vượt consistency SLA
~~~

Outbox relay nên gắn `aggregateVersion`, `eventId` ổn định; với out-of-order invalidations, cần version guard/tombstone policy phù hợp.

### 18.3. “Cache hit” không phải business success

Trong Spring Boot Integration, một method trả cached InventoryStock **không xác nhận** tồn kho đủ để reserve tại thời điểm hiện tại. Lệnh reserve cần transaction/atomic check ở authoritative DB; cache nên chỉ giúp hiển thị/ước lượng theo explicit freshness contract.

---

## 19. Observability và capacity planning

Một số metrics có thể được Micrometer/Actuator, Hazelcast Management Center hoặc Infinispan monitoring cung cấp **tùy phiên bản/cấu hình**. Không assume framework tự export mọi signal.

| Metric/signal | Mục tiêu |
| --- | --- |
| Cache hit/miss ratio per cache | Hiệu quả cache |
| Cache entry count/size | Memory/capacity |
| Cache evictions/expirations | Capacity pressure/TTL behavior |
| Cache load time p95/p99 | Chi phí cache miss |
| Cache get/put/remove errors | Cluster availability |
| Active cluster members/topology | Health/quorum |
| Network RTT/timeout/reconnect | Remote clients |
| Serialization errors | Schema incompatibility |
| Per-key stampede suppression count | Duplicate loads |
| Hikari connections active/pending | Downstream DB pressure |
| HTTP partner 429/503 | Cache miss overload |
| Business stale-read detections | Consistency impact |
| Outbox invalidation lag | Chậm đồng bộ cache |
| Rate of fallback reads | Cache failure blast radius |

### 19.1. Không dùng high-cardinality tags

Hợp lý:

~~~text
cache=productsById
provider=hazelcast
outcome=hit|miss|error
operation=get|put|evict
service=catalog
~~~

Không đưa `productId`, `tenantId` có hàng triệu giá trị, email, access tokens hoặc raw payload vào Prometheus labels. Correlation IDs dùng trong structured logs có retention/access controls.

### 19.2. Đặt alert theo hệ thống, không chỉ hit rate

Hit rate giảm có thể do deployment/cold cache, không nhất thiết là outage. Nhưng nếu cùng lúc cache misses tăng, Hikari pool pending tăng và HTTP 503 tăng, đó là một **cache miss storm ảnh hưởng backend**.

Alert nên xem tổng thể:

- Cache availability.
- Downstream saturation.
- Business latency p95/p99.
- Stale values quá SLA.
- Invalidation backlog age.
- Cluster member restarts/rebalance.

### 19.3. Sizing

Ước lượng:

~~~text
Raw values:
  1 million keys × average 2 KiB ≈ ~2 GiB raw values

Real memory must include:
  key bytes + metadata + serialization overhead
  backup replicas + indexes + fragmentation/GC
  near cache copies (nếu có)
  network buffers and eviction headroom
~~~

Không dùng phép nhân raw value sizes làm sizing production duy nhất. Đo bằng provider-specific tools, load test dữ liệu đại diện, và tính cluster failover khi mất một member.

---

## 20. Runbook theo triệu chứng

| Triệu chứng | Khả năng | Bước kiểm tra |
| --- | --- | --- |
| `@Cacheable` không cache | Chưa `@EnableCaching`, self-invocation | Proxy, annotation scan |
| Bean là `ConcurrentMapCacheManager` | Auto-config chọn local fallback | Runtime CacheManager type, classpath |
| JCache provider not found | Có API nhưng thiếu provider | SPI `Caching.getCachingProviders()` |
| Multiple CachingProviders | Hazelcast + Infinispan cùng classpath | Explicit `spring.cache.jcache.provider` |
| `Cannot find cache named X` | JCache cache chưa được provision | Cache names, provider config |
| Cache TTL không giống kỳ vọng | Native vs JCache expiry config khác | Actual provider/mode |
| Hazelcast members không thấy nhau | K8s discovery/network/cluster name | Cluster membership, ports |
| Cache values biến mất sau pod restart | Local/embedded không backup đúng | Topology/mode/backup |
| Infinispan remote timeout | Hot Rod server/TLS/auth/network | Remote client config |
| `ClassNotFoundException` deserialize | Mixed schema/classloader versions | Versioned cache keys/codec |
| Stale product sau SQL COMMIT | Eviction fail/race/async invalidation lag | Outbox/TTL/version guard |
| DB overload khi cache fail | Fail-open stampede | Bulkhead, stale policy, warming |
| CPU/GC tăng | Serialization, large values, members in app JVM | Heap, payload, cache size |
| Cache có key từ tenant khác | Thiếu tenant in cache key | Key contract, security incident |
| Hikari pending tăng khi key expired | Hot-key stampede | Per-key single-flight + limits |
| Thêm Hibernate JCache không thấy @Cacheable | Nhầm L2 và Spring Cache | Separate cache layers |
| Rollback service không đọc cache mới | Wire/schema compatibility | Key namespace/versioning |
| Cluster split brain | Network partition/health | Quorum/conflict policy |

### 20.1. Điều tra theo đúng thứ tự

1. Xác định use case: query cache, session, Hibernate L2, idempotency store hay distributed lock?
2. Inspect actual **Spring CacheManager class** và provider SPI.
3. Xác nhận cache name và cấu hình JCache/native thực.
4. Xác định topology: local, embedded clustered, remote client/server.
5. Kiểm tra TTL/eviction/serialization và cache key contract.
6. Kiểm tra DB/source-of-truth state và transaction commit.
7. Đo network cluster, provider health, SSL/authentication.
8. Đối chiếu cache hit/miss/errors với Hikari/HTTP partner saturation.
9. Kiểm tra outbox/invalidation lag và stale-read SLA.
10. Reproduce trên integration environment, không thử chaos trên production cache cluster nếu chưa được phép.

---

## 21. Anti-pattern cần tránh

| Anti-pattern | Tại sao sai? | Thay thế |
| --- | --- | --- |
| Chỉ thêm `javax.cache:cache-api` rồi mong có cache | API không có provider | Một JCache implementation/runtime |
| Kéo Hazelcast và Infinispan vào cùng app vô cớ | Provider detection mơ hồ | Chọn một implementation/manager rõ |
| Dùng `CacheManager` import sai package | Hai API cùng tên | Fully qualify/qualifier |
| Dùng `runtimeOnly` khi source import Hazelcast classes | Compile không thấy types | `implementation` |
| `@Cacheable` nhưng không `@EnableCaching` | Interception không bật | Enable caching |
| Self-invocation cached method | Bỏ qua Spring proxy | Gọi qua bean khác |
| Không provision JCache cache names | Missing cache at runtime | Provider config/customizer |
| Lẫn native TTL với JCache ExpiryPolicy | Hai API/configs khác | Quy định provider/mode cụ thể |
| Cache JPA entity đang attached | Lazy proxy/mutable state | Immutable DTO |
| Thiếu tenant trong key | Cross-tenant data leak | Complete key contract |
| Dùng cache làm idempotency ledger duy nhất | Eviction/restart gây duplicate | SQL UNIQUE + receipt |
| Dùng cache lock thay DB invariant | Split brain/lease expiry | Fencing/DB constraint |
| Cập nhật cache trước SQL COMMIT | Rollback để lại stale new value | After-commit/outbox |
| Eviction thất bại nhưng giả định consistency mạnh | DB/cache divergence | TTL + reliable invalidation |
| `@Cacheable(sync=true)` xem như cluster mutex | Không bảo đảm | Per-provider test/bulkhead |
| Fail-open mọi cache exceptions | DB storm/security problems | Per-cache failure policy |
| TTL giống nhau trên hot keys | Miss storm | Jitter/prewarm/single-flight |
| Bỏ code đọc v1 khi data v1 còn trong cache | Deserialize errors | Versioned keys/migration |
| Bật embedded cluster trên autoscaled pods không tính rebalance | Topology churn | Remote cluster hoặc controlled scaling |
| Chỉ test local mock manager | Không test distributed behavior | Real provider integration tests |
| Dùng cache làm durable queue | Không đúng delivery semantics | Broker/outbox |
| Log keys/values chứa PII/secrets | Data leakage | Redaction/low-cardinality metrics |

---

## 22. Checklist chọn dependencies và triển khai

### A. Trước khi chọn provider

- [ ] Đã xác định cache chỉ là optimization hay nằm trên đường critical business.
- [ ] Nêu rõ consistency SLA/stale window, TTL, eviction và fail-open/fail-closed.
- [ ] Đã phân biệt Spring Cache, JCache API và concrete provider.
- [ ] Có lý do chọn JCache compatibility hay native APIs.
- [ ] Topology được quyết định: local, embedded members hoặc remote cluster.
- [ ] Có memory/capacity/network/ops budget theo replicas.

### B. Dependencies và Spring configuration

- [ ] Có `spring-boot-starter-cache` khi dùng Spring Cache annotations.
- [ ] Có `@EnableCaching` nếu chưa được cấu hình ở nơi khác.
- [ ] Nếu dùng JCache, có `javax.cache` API **và** một provider được hỗ trợ.
- [ ] Nếu source import provider types, dùng compile/implementation scope phù hợp.
- [ ] Không kéo `hazelcast-spring` khi không cần native Spring bridge.
- [ ] Infinispan embedded/remote/JCache dùng đúng artifact và release compatible với Boot major.
- [ ] Không nhầm Hibernate L2/JCache với Spring Cache.
- [ ] Đã xác minh actual `CacheManager` bean trong startup test.
- [ ] Khi nhiều managers, bean names/qualifiers/`@Primary` rõ ràng.
- [ ] JCache named caches được provision trước khi dùng.
- [ ] BOM, API namespace, provider SPI và classloader được kiểm tra.
- [ ] Boot 3/Boot 4 differences được review theo release docs.

### C. Data contract, transaction và security

- [ ] Cache keys bao gồm tenant/locale/currency/version nếu ảnh hưởng result.
- [ ] Không có secrets/PII trong keys, logs hoặc metrics tags.
- [ ] Cache values là immutable DTO, có serialization compatibility.
- [ ] TTL, expiry policy, max idle và eviction semantics được test trên provider thật.
- [ ] Source-of-truth vẫn ở DB/service authoritative cho critical invariants.
- [ ] SQL COMMIT và cache invalidation failure windows đã có xử lý.
- [ ] Có outbox/reliable invalidation khi consistency requirements cần.
- [ ] Cache không làm durable idempotency store/queue nếu provider không bảo đảm.
- [ ] Fail-open policy không tạo thundering herd và không bypass auth.
- [ ] TLS, authentication, ACL, secrets rotation và cluster isolation được cấu hình.

### D. Kiểm thử và vận hành

- [ ] Test cache hit/miss qua Spring-managed proxy.
- [ ] Test provider auto-selection, missing names và multiple SPI providers.
- [ ] Test expiration và serialization trên Hazelcast/Infinispan/JCache thực.
- [ ] Test ít nhất 2 clients/pods khi yêu cầu distributed visibility.
- [ ] Test cache unavailable, timeout, DB fallback và stampede.
- [ ] Test rollback/commit rồi invalidation fail.
- [ ] Test rolling upgrade/rollback với old/new cached values.
- [ ] Có metrics hit/miss, eviction, errors, cluster health, Hikari và stale age.
- [ ] Có capacity plan cho cache failover/rebalance/cold start.
- [ ] Có runbook phân biệt lỗi cache với lỗi business DB.

**Ghi nhớ:** **JCache là chuẩn API (JSR-107), Hazelcast và Infinispan là các providers/technologies, Spring Cache là abstraction của ứng dụng.** Dependency đúng chỉ vừa đủ cho programming model được dùng, provider implementation, Spring integration và topology thật. Cấu hình `CacheManager` rõ ràng, quản lý key/TTL/serialization theo hợp đồng, đặt source-of-truth ở hệ thống nghiệp vụ, kiểm thử invalidation sau SQL COMMIT và đảm bảo lỗi cache không biến thành lỗi toàn hệ thống.

## Tài liệu tham khảo

- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, cache manager và proxy.
- [Spring Framework — JCache/JSR-107 Annotations](https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html): `@CacheResult`, interop với Spring caching.
- [Spring Framework — TransactionAwareCacheManagerProxy](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/transaction/TransactionAwareCacheManagerProxy.html): transaction synchronization semantics.
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html): cache auto-config, supported providers, cache type selection.
- [JSR-107 — JCache Specification](https://jcp.org/en/jsr/detail?id=107): standard API và expiry/provider model.
- [JCache API](https://github.com/jsr107/jsr107spec): API namespace `javax.cache`, interfaces, annotations.
- [Hazelcast — Spring Integration](https://docs.hazelcast.com/hazelcast/latest/spring/overview): Hazelcast Spring Cache adapter/usage.
- [Hazelcast — JCache](https://docs.hazelcast.com/hazelcast/latest/jcache/jcache-overview): Hazelcast JCache support, provider config.
- [Hazelcast — Kubernetes](https://docs.hazelcast.com/hazelcast/latest/kubernetes/kubernetes-auto-discovery): member discovery/topology.
- [Infinispan — Documentation](https://infinispan.org/documentation/): embedded/remote Spring integrations, supported releases.
- [Infinispan — Spring Boot Integration](https://infinispan.org/docs/stable/titles/spring/spring.html): embedded và remote Spring starters.
- [Infinispan — Hot Rod Java Client](https://infinispan.org/docs/stable/titles/hotrod_java/hotrod_java.html): remote server/client, serialization.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource/Hikari concurrency và transactions.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries.
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer integration và custom metrics.
- [Testcontainers — Documentation](https://java.testcontainers.org/): provider-backed integration tests.
- [Enterprise Integration Patterns — Idempotent Receiver](https://www.enterpriseintegrationpatterns.com/patterns/messaging/IdempotentReceiver.html): duplicate-safe consumption.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): reliable invalidation intent và retry.
