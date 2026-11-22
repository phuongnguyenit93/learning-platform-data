# Mono: lưu giá trị được phát thay vì giữ Publisher làm dữ liệu

## 1. Mục tiêu

Với Spring Framework 6.1 trở lên, `@Cacheable` có thể thích nghi với method trả về Reactor `Mono<T>`: cache lưu **giá trị T được publisher phát ra** thay vì lưu chính object `Mono` như một đối tượng nghiệp vụ. Caller vẫn thấy `Mono<T>`, nhưng khi cache hit, Spring có thể tạo luồng phát lại giá trị T đã cache mà không chạy lại nghiệp vụ.

Điểm này đặc biệt quan trọng đối với cold publisher. Nếu một object `Mono` chứa truy vấn database nhưng chỉ được lưu vào Map, mỗi lần subscribe vẫn có thể chạy truy vấn. Khi Spring Cache lưu emitted value T, lần gọi cùng key sau cache hit không cần subscribe lại vào nguồn đó.

Mục tiêu của bài:

- Phân biệt **publisher** và **emitted value**.
- Hiểu Spring proxy, cache lookup, subscription, cache miss và hit.
- Cấu hình cache có hỗ trợ bất đồng bộ, như `CaffeineCacheManager#setAsyncCacheMode(true)`.
- Chạy Java 17 với `Mono<String>` và kiểm tra native business value lưu trong Spring `Cache`.
- Phân biệt `Mono.empty()`, `Mono.error`, cancellation, retry, concurrent misses, TTL và key scope.
- Biết giới hạn của `sync=true`, reactive transaction và nguồn blocking.

Bài thuộc nhóm **Bất đồng bộ** của module Spring Framework Cache. Những kiến thức `Flux` và `CompletableFuture` được trình bày để đối chiếu, không thay thế trọng tâm Mono.

## 2. Vì sao cache object Mono không tương đương cache kết quả?

Đoạn code:

~~~java
Mono<String> publisher = Mono.fromSupplier(() -> {
    System.out.println("DB read");
    return "Product-A";
});
~~~

Đây là snippet cần import `reactor.core.publisher.Mono`. `fromSupplier` tạo **cold Mono**: supplier chạy khi publisher được subscribe, không bắt buộc chạy khi Java tạo object.

~~~java
publisher.block(); // in "DB read"
publisher.block(); // lại in "DB read"
~~~

Nếu viết một cache thủ công:

~~~java
Map<String, Mono<String>> wrongCache = new ConcurrentHashMap<>();
wrongCache.put("A",
    Mono.fromSupplier(() -> database.findTitle("A")));
~~~

Đây là snippet cần imports/database. Map có key `A` không có nghĩa đã cache kết quả query. Map chỉ giữ công thức được tái thực thi khi subscribe vào cold Mono.

Spring Cache 6.1+ hướng tới:

~~~text
"SKU-1"  -->  @Cacheable method: Mono<Product>
     |
     +-- Miss --> subscribe/load --> onNext(Product) --> store Product
     |
     +-- Hit  --> read Product from Cache --> Mono emits Product
~~~

**Cache value là Product, không phải Mono<Product>.** Một cache hit không cần chạy pipeline nguồn chứa HTTP request hay repository query. Nhưng TTL, authorization, key và invalidation phải được thiết kế riêng cho giá trị Product đã lưu.

## 3. Hai tầng type trong Spring Cache

| Vị trí | Type | Ý nghĩa |
| --- | --- | --- |
| Java method contract | `Mono<Product>` | Caller muốn nhận một computation/reactive stream |
| Cache entry sau successful source emission | `Product` | Giá trị business được giữ theo cache key |
| Cache hit trả caller | `Mono<Product>` | Spring thích nghi Product về reactive return type |
| Native async cache implementation | Có thể sử dụng future/stage nội bộ | Cơ chế provider quản lý thời điểm lookup/load; không phải business type |

Đừng nhầm future **nội bộ của cache** với dữ liệu nghiệp vụ: một async provider có thể lưu/điều phối các `CompletableFuture`, nhưng ở mức Spring `Cache`, expected business value của `Mono<Product>` là Product.

Ví dụ code business:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Mono<Product> findProduct(String sku) {
    return reactiveRepository.findBySku(sku);
}
~~~

Đây là snippet chưa độc lập: cần `Product`, repository, Spring-managed bean, `@EnableCaching`. Annotation vẫn là của **Spring** (`org.springframework.cache.annotation.Cacheable`), không thuộc Reactor.

## 4. Luồng xử lý khi miss và hit

Spring caching hoạt động qua proxy/AOP trong cấu hình mặc định:

1. Caller gọi `findProduct("SKU-1")` qua **Spring proxy**; interceptor phân tích `@Cacheable`.
2. Spring xác định cache `products` và key từ SpEL `#p0`.
3. Cache infrastructure hỏi cache manager. Với implementation hỗ trợ async retrieval, `Cache.retrieve(...)`/`CompletableFuture` có thể được dùng để phối hợp lookup/load.
4. Nếu hit, Spring cho caller một Mono phát business value T đã có.
5. Nếu miss, source method trả Mono. Khi downstream subscribe, nguồn có thể thực hiện công việc và phát T.
6. Khi giá trị T hoàn tất thành công và phù hợp policy, Spring đưa T vào cache. Lần gọi sau cùng key sẽ không chạy source nếu entry còn hiệu lực.

~~~mermaid
sequenceDiagram
    participant Caller
    participant Proxy as Spring CacheInterceptor
    participant Cache as Async Cache
    participant Source as Mono source
    Caller->>Proxy: findProduct(key)
    Proxy->>Cache: lookup(key)
    alt hit
        Cache-->>Proxy: T
        Proxy-->>Caller: Mono emits T
    else miss
        Proxy->>Source: obtain Mono<T>
        Caller->>Proxy: subscribe
        Proxy->>Source: subscribe / await
        Source-->>Proxy: onNext(T), onComplete
        Proxy->>Cache: store T
        Proxy-->>Caller: onNext(T), onComplete
    end
~~~

Sơ đồ cho biết ý nghĩa, không khẳng định một thứ tự nội bộ duy nhất của mọi provider. Cache lookup có thể xảy ra trước subscription; source execution còn phụ thuộc Mono có lazy hay không. Với remote cache, future và scheduler tạo thêm các mốc quan sát khác.

## 5. Version từ Spring Framework 6.1 và compatibility switch

| Hệ thống | Điều cần hiểu |
| --- | --- |
| Spring Framework trước 6.1 | Reactive Publisher có thể bị coi như một object trả về thông thường và cache chính object đó |
| Spring Framework 6.1+ mặc định | Hiểu return type `Mono` và cache emitted value, không đơn thuần cache Publisher |
| Hệ thống bật `spring.cache.reactivestreams.ignore=true` | Có thể bỏ qua reactive adaptation để giữ behavior cũ trong version hỗ trợ switch |

Hành vi này là một thay đổi có ảnh hưởng khi nâng phiên bản. Không nên áp dụng lời khuyên dành cho Spring 6.0 vào dự án Spring 6.2 rồi dự đoán cache giữ publisher.

Để xác định hiện trạng, hãy kiểm tra:

- Phiên bản `spring-context` thực tế khi chạy.
- Cấu hình caching, system property compatibility và lựa chọn CacheManager.
- Source method có thật sự đi qua Spring proxy không.
- Giá trị được đọc từ Spring Cache sau khi publisher hoàn tất: T hay publisher.
- Số lần nguồn hoạt động khi gọi hai lần cùng key.

Không coi việc có dependency Reactor trên classpath là đủ để tự kích hoạt caching; vẫn cần `@EnableCaching` hoặc cấu hình tương đương.

## 6. Caffeine async mode và Cache.retrieve

Spring Cache bổ sung khả năng truy xuất bất đồng bộ qua những operation như:

~~~java
CompletableFuture<?> asyncHitOrMiss = cache.retrieve(key);
~~~

Đây là snippet cần `Cache cache`, `key` và import `CompletableFuture`. Không phải mọi provider đều triển khai async retrieval giống nhau; future có thể hoàn tất muộn, có thể bao một `Cache.ValueWrapper` tùy contract của overload.

Với Caffeine, Spring có manager:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableCaching
class CacheConfig {
    @Bean
    CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager();
        manager.setAsyncCacheMode(true);
        manager.setCacheNames(List.of("products"));
        return manager;
    }
}
~~~

Đây là snippet cần Spring annotations/imports, `java.util.List`, `CaffeineCacheManager` và dependency Caffeine. `setAsyncCacheMode(true)` sử dụng async Caffeine caches, là lựa chọn phù hợp cho reactive return types từ Spring 6.1.

Lưu ý rằng native Caffeine là local in-memory cache; cấu hình này không tự tạo distributed coherence, không biến JDBC blocking thành non-blocking và không tự định nghĩa TTL. Với Spring Boot, hãy kiểm tra bean CacheManager mà auto-configuration thực sự sử dụng, tránh giả định async mode luôn bật.

## 7. Ví dụ runnable Java 17: Mono<String> nhưng lưu String

Demo dùng Spring Framework 6.2.14, Reactor Core 3.7.12 và Caffeine 3.1.8. Không cần database/server. Một counter tăng mỗi lần source được subscribe để phân biệt miss và hit.

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>spring-mono-emitted-cache</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.14</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context-support</artifactId>
      <version>6.2.14</version>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.7.12</version>
    </dependency>
    <dependency>
      <groupId>com.github.ben-manes.caffeine</groupId>
      <artifactId>caffeine</artifactId>
      <version>3.1.8</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.1</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.2</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`spring-context-support` chứa Caffeine adapter, `spring-context` chứa annotation/bean infrastructure, Reactor Core chứa `Mono`. Phiên bản minh họa là lựa chọn có chủ đích, không phải quy tắc nâng cấp mọi ứng dụng production.

### 7.2. src/main/java/demo/MonoCacheDemo.java

~~~java
package demo;

import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Mono;

public final class MonoCacheDemo {
    private MonoCacheDemo() {}

    @Configuration(proxyBeanMethods = false)
    @EnableCaching
    public static class Config {
        @Bean
        CacheManager cacheManager() {
            CaffeineCacheManager manager = new CaffeineCacheManager();
            manager.setAsyncCacheMode(true);
            manager.setCacheNames(List.of("products"));
            return manager;
        }

        @Bean
        CatalogService catalogService() {
            return new CatalogService();
        }
    }

    public static class CatalogService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "products", key = "#p0")
        public Mono<String> find(String sku) {
            return Mono.fromSupplier(() -> {
                int n = loads.incrementAndGet();
                System.out.println("source #" + n);
                return "product:" + sku + ":v" + n;
            });
        }

        @CacheEvict(cacheNames = "products", key = "#p0")
        public void evict(String sku) {
            // Không có database trong demo.
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("first=" + service.find("SKU-1").block());
            System.out.println("second=" + service.find("SKU-1").block());

            CacheManager manager = context.getBean(CacheManager.class);
            Cache cache = Objects.requireNonNull(
                    manager.getCache("products"));
            Cache.ValueWrapper wrapper = Objects.requireNonNull(
                    cache.get("SKU-1"));
            Object value = Objects.requireNonNull(wrapper.get());

            System.out.println("stored type=" + value.getClass().getName());
            System.out.println("stored publisher=" + (value instanceof Mono));

            service.evict("SKU-1");
            System.out.println("after evict="
                    + service.find("SKU-1").block());
        }
    }
}
~~~

Các điều kiện quan trọng: service phải được Spring quản lý, method public non-final, có `@EnableCaching` và caller gọi proxy. `Mono.fromSupplier` tạo nguồn lazy. Key là String `SKU-1` trong cache `products`; Caffeine manager bật async mode.

### 7.3. Lệnh chạy

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.MonoCacheDemo
~~~

Stdout dự kiến từ chương trình (không tính log Maven/Spring):

~~~text
source #1
first=product:SKU-1:v1
second=product:SKU-1:v1
stored type=java.lang.String
stored publisher=false
source #2
after evict=product:SKU-1:v2
~~~

Lần đầu miss nên supplier chạy và in `source #1`. Lần hai hit, không in thêm source call. `Cache.ValueWrapper` chứa value `String` chứ không phải `Mono`. Sau eviction key, lần đọc sau miss, source chạy lại và tạo v2.

Ví dụ được rà soát theo API Spring/Reactor nhưng **chưa được biên dịch hoặc chạy thực tế** trong quá trình biên soạn. Khi học cần chạy với dependency/version đã nêu và xác nhận chính sách adapter đang dùng. `block()` ở đây phục vụ console demo; không dùng `block()` trên WebFlux event-loop trong production.

## 8. Cold publisher, hot publisher và Mono.cache()

`Mono.cache()` là operator Reactor memoize tín hiệu của **một instance Publisher**, không phải cùng một tầng với `@Cacheable` của Spring.

~~~java
Mono<String> shared = remoteLookup("SKU-1").cache();
~~~

Snippet này cần `remoteLookup`. Nhiều subscribers của `shared` có thể dùng một kết quả đã memoize. Nhưng nếu mỗi lần gọi method lại tạo `remoteLookup(...).cache()` mới, mỗi instance có state riêng. Trong khi đó, `@Cacheable` có cache name/key/manager và chia sẻ kết quả giữa các method calls theo cache policy.

`Mono.just(value)` chứa giá trị đã có; nếu argument của `just` là một lệnh DB blocking, lệnh đó chạy ngay khi tạo Mono. `Mono.fromSupplier` và `Mono.defer` mới trì hoãn việc tính đến subscription. Một publisher kết nối future/hot source có semantics khác. Cache emitted value tránh phụ thuộc vào kiểu publisher nguồn trong các lần hit, nhưng không loại bỏ yêu cầu xác định timing của lần miss.

## 9. Mono.empty() và cached null

Một `Mono.empty()` kết thúc mà **không có phần tử T**. Reactor không cho phép `Mono.just(null)` hoặc `onNext(null)`.

~~~java
Mono<String> notFound = Mono.empty();
~~~

Đối với Spring reactive caching, completion trống không giống một `onNext(T)` thành công. Adapter có thể thể hiện empty qua null/absent state và provider có thể có policy khác nhau về cache null. **Không mặc định khẳng định empty luôn được negative-cache hoặc luôn miss.**

Cách test:

1. Viết method `@Cacheable` trả `Mono.empty()`, counter tăng khi source được subscribe.
2. Gọi hai lần cùng key, await completion.
3. Đo counter và đọc `Cache.get(key)`, phân biệt wrapper null (miss) với wrapper khác null có value null (hit-null).
4. Thử `unless` và policy `allowNullValues` nếu provider hỗ trợ.
5. Lặp lại khi đổi CacheManager hoặc Spring version.

Nếu cần phân biệt NotFound/Forbidden/Timeout, hãy sử dụng domain result rõ ràng thay vì coi tất cả là empty completion.

## 10. Mono.error, retry và cancellation

`Mono.error(e)` là tín hiệu lỗi, **không phát business value T thành công**. Đừng thiết kế cache error response như một Product hợp lệ chỉ vì method return type là Mono.

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Mono<Product> get(String sku) {
    return webClient.get()
        .uri("/products/{sku}", sku)
        .retrieve()
        .bodyToMono(Product.class);
}
~~~

Snippet cần Spring WebClient và class Product. Khi timeout/HTTP error, cần xử lý theo chính sách domain.

- `onErrorResume(e -> Mono.empty())` biến lỗi thành empty completion; nếu negative caching bật, có thể vô tình ghi nhớ outage như NotFound.
- `retry` bên trong source khác với retry subscription ngoài method. Kiểm tra số lần remote call trên miss.
- Một subscriber hủy subscription không đảm bảo hủy mọi future/loader được chia sẻ với subscriber khác.
- Với async cache, failed future có thể có lifecycle/cleanup riêng. Test error và retry trên provider thực tế.
- Không lấy cùng một test thành công rồi kết luận hành vi error/cancellation.

## 11. condition, unless và sync=true

Ví dụ annotation:

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
public Mono<Product> find(String sku) {
    return repository.findBySku(sku);
}
~~~

Đây là snippet minh họa, cần repository và Product. `condition` đánh giá trước khi result được tạo, dựa vào input; `unless` là veto khi có result. Với reactive support ở Spring mới, hãy xác định `#result` theo **giá trị emitted** thay vì mặc định nghĩ đó luôn là object Mono. Với `Mono.empty()`, thực thi và null adaptation cần test.

`@Cacheable(sync=true)` giúp phối hợp load cùng key khi backend hỗ trợ; **không kết hợp với `unless`** theo contract của Spring. Không dùng cả hai để hy vọng cache tự xử lý empty result.

## 12. Key phải mô tả giá trị, không phải subscription

Nếu một source phụ thuộc sku, currency và tenant:

~~~java
@Cacheable(cacheNames = "prices", key = "#p0")
public Mono<Price> getPrice(
        String sku, String currency, String tenant) {
    return pricingClient.getPrice(sku, currency, tenant);
}
~~~

Snippet cần Price/client. Key chỉ chứa sku là **sai** nếu currency/tenant ảnh hưởng giá. Khi cache hit, emitted value Price cũ được dùng mà **không chạy lại source** nơi có thể có logic chọn tenant.

Thiết kế key gồm đủ dimensions ảnh hưởng output (tenant, user scope, permission, currency, locale, version). Không dùng identity Mono hoặc mỗi subscription làm key. Nếu thông tin quan trọng chỉ nằm trong Reactor Context, hãy đưa vào method arguments hoặc một custom key strategy kiểm thử được; SpEL tạo key ở ranh giới invocation không tự đọc được mọi dữ liệu chỉ xuất hiện lúc subscribe.

Cảnh báo về bảo mật: authorization phải được áp dụng đúng boundary; cache hit không được vô tình bỏ qua kiểm tra quyền do business source đang giữ.

## 13. Concurrent miss và single-flight

Hai callers có thể cùng thấy cache miss và cùng chạy source trước khi một kết quả được lưu. `sync=true` có thể giúp provider thực hiện một load cho cùng key khi hỗ trợ cơ chế này.

~~~java
Mono<String> a = service.find("SKU-1");
Mono<String> b = service.find("SKU-1");
Mono.zip(a, b).block();
~~~

Snippet này chỉ diễn tả ý tưởng; không chắc tạo được concurrent miss thực sự nếu source đồng bộ trên một thread. Muốn đo, hãy dùng source asynchronous có controllable delay/latch và counter.

Nhớ rằng:

- Sync load cần CacheManager hỗ trợ; local guarantee không nhất thiết là distributed single-flight.
- `sync=true` và `unless` không được phối hợp như một cấu hình hợp lệ.
- Error/timeout/cancellation của một load được chia sẻ có thể ảnh hưởng nhiều consumers; test riêng.
- Một duplicate load không nhất thiết là bug nếu ứng dụng không yêu cầu strict single-flight.

## 14. TTL, invalidation và stale emitted values

Khi Spring đã cache T, một cache hit phát T đang lưu; nó **không tự gọi lại** repository để kiểm tra version mới. Freshness phụ thuộc:

- TTL/size/eviction của provider, không phải `Mono.cache(Duration)`.
- `@CacheEvict` hoặc direct `Cache.evict` khi dữ liệu nguồn thay đổi.
- Versioned key, invalidation event và chống race với loader đang chạy.
- Transaction boundary: không mặc định cache eviction sau Java method return nghĩa là sau database commit.
- Remote cache replication và serializer khi ứng dụng có nhiều node.

Một source reactive hoàn tất sau khi entry bị invalidated có thể đưa stale data trở lại cache. Với dữ liệu nhạy, dùng version/generation key hoặc cơ chế điều phối phù hợp.

Với command trả `Mono<Void>`, completion không phát phần tử business; đừng gán logic “cache emitted value” như thể có một Void được phát. Khi dùng reactive transaction, kiểm tra thời điểm transaction commit và cache invalidation theo Reactor Context; không suy ra thread-local transaction-aware decorator áp dụng nguyên xi trong mọi reactive flow.

## 15. Tránh blocking I/O trong source

Sai lầm:

~~~java
public Mono<Product> wrong(String sku) {
    return Mono.just(jdbcRepository.findBySku(sku));
}
~~~

`jdbcRepository.findBySku` đã chạy trước khi Mono được tạo xong; khi gọi trên WebFlux event-loop có thể block thread. Cache hit có thể giảm số lần gọi nguồn, nhưng lần miss vẫn nguy hiểm.

Nếu buộc phải gọi blocking API:

~~~java
public Mono<Product> withBlockingSource(String sku) {
    return Mono.fromCallable(() -> jdbcRepository.findBySku(sku))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Đây là snippet cần imports và repository. `boundedElastic` dời blocking work lên scheduler phù hợp; nó **không biến I/O thành non-blocking**. Nếu có reactive repository/driver thật, nên dùng nó.

## 16. Kiểm thử từng lớp

**Kiểm tra emitted value và số lần source chạy:**

~~~java
String first = service.find("SKU-1").block();
String second = service.find("SKU-1").block();
// Assert first.equals(second) VÀ source counter tăng một lần.
~~~

Hai values bằng nhau chưa chứng minh hit, vì database có thể trả dữ liệu giống nhau hai lần. Counter phải đo **bên trong source**, không chỉ `doOnNext` gắn ở downstream vì subscriber nhận cả cache hit.

**Kiểm tra kiểu value trong cache:**

~~~java
Cache.ValueWrapper wrapper = cache.get("SKU-1");
Object stored = wrapper == null ? null : wrapper.get();
System.out.println(stored == null ? "MISS" : stored.getClass().getName());
~~~

Spring Cache API giúp kiểm tra value thật. Demo dùng `String`. Nhớ phân biệt wrapper null với wrapper chứa null.

**Kiểm tra eviction:**

~~~java
service.evict("SKU-1");
String fresh = service.find("SKU-1").block();
// Source counter tăng và phiên bản value thay đổi.
~~~

Nếu dự án đã có `reactor-test`, có thể dùng:

~~~java
StepVerifier.create(service.find("SKU-1"))
    .expectNext("product:SKU-1:v1")
    .verifyComplete();
~~~

Snippet này cần thêm `io.projectreactor:reactor-test` và import `reactor.test.StepVerifier`; **không thuộc Maven demo**.

### Ma trận trường hợp

| Case | Điều cần xác minh |
| --- | --- |
| Mono phát T | Cache giữ T, source chỉ chạy trên miss |
| Cache hit | Caller vẫn nhận Mono<T>, không chạy source |
| Mono.empty | Negative-cache policy rõ |
| Mono.error/timeout | Lỗi không biến thành cached success |
| Cancel | Future/source state không gây invalid cache |
| Concurrent miss | Duplicate loads hay single-flight đúng yêu cầu |
| TTL hết hạn | Load lại đúng thời điểm |
| Evict | Sau evict, source tạo phiên bản mới |
| Multi-tenant | Key scope và quyền không rò rỉ |
| Đổi Spring/provider | Không tái xuất hiện caching Publisher cold |

## 17. Lỗi phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Lưu cold Mono trong Map rồi coi đã cache dữ liệu | Subscribe vẫn chạy DB | Cache emitted value qua Spring 6.1+ |
| Giả định Spring 6.0 xử lý Mono y hệt 6.2 | Behavior lệch version | Xác nhận version và test |
| Bật `spring.cache.reactivestreams.ignore=true` vô ý | Trở lại behavior cache Publisher | Tắt compatibility switch khi muốn reactive adaptation |
| Quên `@EnableCaching` hoặc tự `new` service | Không có proxy | Lấy bean từ Spring context |
| Gọi `this.find(...)` trong cùng class | Self-invocation bypass caching | Gọi qua Spring bean/proxy |
| CacheManager không có async support phù hợp | Async retrieval sai expectation | Dùng provider phù hợp, thử Caffeine async mode |
| Đếm downstream `doOnNext` làm DB hit count | Đếm cả cache hit | Đo ở supplier/repository |
| `Mono.just(blockingCall())` | Block thread tại assembly | Reactive API hoặc defer + boundedElastic |
| Nhầm `Mono.cache()` với `@Cacheable` | Khác scope/key/TTL/error policy | Chọn đúng tầng cache |
| Key chỉ có SKU nhưng dữ liệu theo tenant | Sai kết quả hoặc lộ dữ liệu | Key đầy đủ tenant/permission |
| Khẳng định Mono.empty luôn được cache | Bỏ qua null/provider/version | Test negative-cache riêng |
| Ghép `sync=true` và `unless` | Không được hỗ trợ | Thiết kế lại policy |
| Cache vô hạn Flux như Mono | Collect vô hạn, rủi ro RAM | Không cache unbounded stream |
| Nghĩ reactive Mono đồng nghĩa non-blocking I/O | Miss vẫn block DB | Sửa nguồn thực tế |

## 18. Checklist và tài liệu chính thức

Checklist trước production:

- [ ] Đã xác nhận Spring 6.1+ và compatibility switch chưa?
- [ ] Method annotated có đi qua Spring proxy, không phải self-invocation?
- [ ] CacheManager hỗ trợ async retrieval đúng kiểu, provider được cấu hình không?
- [ ] Test chứng minh cache giữ T chứ không giữ Mono, có counter nguồn?
- [ ] Xử lý đúng empty/error/cancellation và chính sách negative-cache?
- [ ] Cache key bao quát tenant, currency, locale và permission scope?
- [ ] `sync=true`, `condition`, `unless` có được kết hợp hợp lệ?
- [ ] TTL, eviction, concurrent loader và transaction consistency có test?
- [ ] Trong WebFlux, code không gọi `block()` trên event loop?
- [ ] Khi đổi provider/version, đã chạy lại các integration tests trên?

Tài liệu tham khảo:

- [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): hỗ trợ reactive return types và caching annotations.
- [Spring Framework — Cache Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/Cache.html): `get`, `ValueWrapper` và `retrieve`.
- [Spring Framework — CaffeineCacheManager Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html): async cache mode.
- [Spring Framework — CacheAspectSupport Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/CacheAspectSupport.html): cache interception và compatibility property.
- [Project Reactor — Mono Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): publisher semantics, empty/error, `fromSupplier`, `defer` và `cache`.
- [Project Reactor — Reference](https://projectreactor.io/docs/core/release/reference/): scheduling, backpressure, testing.

**Kết luận:** trong Spring Cache 6.1+ được cấu hình đúng, `@Cacheable` trên `Mono<T>` cache **giá trị T được phát**. Một cache hit trả lại Mono phát T mà không chạy lại source. Hãy kiểm chứng bằng counter, `Cache.ValueWrapper` và eviction; không suy diễn empty/error, multi-node hay transaction behavior mà không test.