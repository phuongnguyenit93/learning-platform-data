# `@CacheResult`, `@CachePut`, `@CacheRemove` và `@CacheRemoveAll` trong Spring Framework

## Mục tiêu học tập

Spring Framework hỗ trợ annotation chuẩn **JCache (JSR-107)** bên cạnh annotation riêng của Spring. Bốn operation chính là `@CacheResult`, `@CachePut`, `@CacheRemove` và `@CacheRemoveAll`. Chúng có tên gần giống annotation Spring nhưng một số ngữ nghĩa khác nhau, đặc biệt **JCache `@CachePut` lấy giá trị từ tham số `@CacheValue`**, trong khi `org.springframework.cache.annotation.CachePut` của Spring lưu giá trị trả về từ method.

Sau bài này, bạn có thể:

1. Giải thích JCache/JSR-107 và cách Spring tích hợp bộ annotation này.
2. Chọn đúng operation cho đọc, ghi, xóa một entry hoặc xóa cả vùng.
3. Dùng `@CacheKey` để chọn tham số sinh khóa và `@CacheValue` để chỉ định giá trị cần ghi.
4. Hiểu `skipGet`, exception caching, `afterInvocation` và tùy chọn xử lý exception.
5. Dùng `@CacheDefaults`, `CacheKeyGenerator` và `CacheResolverFactory`.
6. Cấu hình Spring để xử lý JCache annotations, kể cả khi backend vẫn là `ConcurrentMapCacheManager`.
7. Kiểm thử bằng ví dụ Java 17 + Spring Boot và tránh nhầm lẫn với annotation Spring.

## 1. JCache (JSR-107) là gì?

**JCache** là tên thường dùng của Java Specification Request 107, một chuẩn API và SPI cho caching trong Java. API định nghĩa cách ứng dụng tương tác với cache và cách nhà cung cấp triển khai cache provider. Mục tiêu là giảm phụ thuộc trực tiếp vào một sản phẩm cụ thể, chẳng hạn Ehcache, Hazelcast hoặc Infinispan.

JCache 1.1.1 dùng package `javax.cache` và `javax.cache.annotation`. Trong ứng dụng Java 17 với Spring Framework 6/Spring Boot 3, package JCache 1.1.1 vẫn là `javax.cache`; không tự đổi thành `jakarta.cache`.

Spring hỗ trợ JCache annotations từ Spring Framework 4.1. Chúng được xử lý bởi caching infrastructure của Spring. **Không bắt buộc phải chuyển cache storage sang một JCache provider**: Spring có thể thực thi JCache annotations thông qua abstraction và `CacheManager` hiện tại.

~~~text
Service method
   |
   +-- JCache: @CacheResult / @CachePut
   |           @CacheRemove / @CacheRemoveAll
   |
   v
Spring caching interceptor
   |
   v
Spring Cache abstraction
   |
   +-- ConcurrentMapCacheManager
   +-- CaffeineCacheManager
   +-- RedisCacheManager
   +-- JCacheCacheManager
~~~

Cần tách hai khái niệm:

- **JCache annotation API:** cách khai báo operation trên method.
- **Cache provider/storage:** nơi thực sự lưu key/value, có thể là JCache provider hoặc một implementation Spring Cache khác.

Điều này hữu ích khi muốn dùng annotation chuẩn JSR-107 nhưng vẫn giữ backend Spring Cache đang vận hành.

## 2. Bốn annotation và quan hệ với annotation Spring

| Ý nghĩa | Spring Cache | JCache (JSR-107) | Khác biệt chính |
| --- | --- | --- | --- |
| Đọc, cache kết quả method | `@Cacheable` | `@CacheResult` | JCache hỗ trợ `skipGet` và cache exception riêng |
| Chạy method rồi ghi cache | `@CachePut` | `@CachePut` | Spring lưu return value; JCache lưu tham số `@CacheValue` |
| Xóa một entry | `@CacheEvict` | `@CacheRemove` | JCache có `evictFor`/`noEvictFor` theo exception |
| Xóa toàn bộ entry trong một cache | `@CacheEvict(allEntries=true)` | `@CacheRemoveAll` | Cùng ý nghĩa xóa cả vùng |
| Cấu hình mặc định cấp class | `@CacheConfig` | `@CacheDefaults` | Chia sẻ cache name, resolver/key generator |

Hai annotation cùng tên `@CachePut` **không cùng hợp đồng**. Luôn kiểm tra import:

~~~java
// JCache: value lấy từ tham số @CacheValue.
import javax.cache.annotation.CachePut;

// Spring Cache: value lấy từ kết quả method.
import org.springframework.cache.annotation.CachePut;
~~~

Không import nhầm hai lớp này. Nếu method JCache không có `@CacheValue`, operation không có dữ liệu được chỉ định để ghi. Nếu dùng Spring `@CachePut` nhưng mong Spring tự đọc tham số `@CacheValue`, hành vi đó cũng không tồn tại.

## 3. `@CacheResult`: đọc cache trước, chỉ chạy method khi miss

`@CacheResult` gần tương đương với `@Cacheable`: Spring/provider tạo key, tra cache trước khi gọi method. Nếu có entry, giá trị cache được trả về và thân method có thể được bỏ qua. Nếu miss, method chạy và kết quả được đưa vào cache.

~~~java
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheResult;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    @CacheResult(cacheName = "products")
    public Product findById(@CacheKey String productId) {
        return repository.findById(productId);
    }
}
~~~

Đây là đoạn minh họa trong service có `repository` và `Product` do ứng dụng định nghĩa. JCache dùng thuộc tính số ít `cacheName`, trong khi Spring `@Cacheable` thường dùng `cacheNames`.

### Các thuộc tính đáng chú ý

| Thuộc tính | Tác dụng |
| --- | --- |
| `cacheName` | Tên cache dùng cho kết quả |
| `cacheResolverFactory` | Chọn factory tạo resolver để tìm cache |
| `cacheKeyGenerator` | Chọn thuật toán sinh key |
| `skipGet` | Bỏ bước đọc trước; method luôn được thực thi và kết quả vẫn được cache |
| `exceptionCacheName` | Tên cache riêng dùng lưu exception |
| `cachedExceptions` | Các kiểu exception được phép cache |
| `nonCachedExceptions` | Các kiểu exception không được cache |

`skipGet=true` hữu ích khi cần method **luôn chạy** nhưng vẫn muốn cache return value:

~~~java
// Minh họa: luôn tính lại báo cáo rồi cập nhật cache.
@CacheResult(cacheName = "reports", skipGet = true)
public Report regenerate(@CacheKey String reportId) {
    return reportService.regenerate(reportId);
}
~~~

Khi `skipGet=true`, cache lookup trước invocation bị bỏ qua. Nếu có `exceptionCacheName`, bước tra exception trước invocation cũng bị bỏ qua. Đây là lựa chọn cho luồng refresh/ghi lại kết quả, nhưng không đồng nghĩa với JCache `@CachePut`: `@CachePut` lấy value từ tham số `@CacheValue`, còn `@CacheResult(skipGet=true)` cache kết quả method trả về.

### Cache exception

JCache có thể cache một số exception vào vùng riêng. Ví dụ, nếu ISBN không hợp lệ là lỗi vĩnh viễn, lần gọi tiếp theo với cùng key có thể ném lại exception đã cache thay vì chạy method lần nữa:

~~~java
// Minh họa; InvalidIsbnException và repository do ứng dụng định nghĩa.
@CacheResult(
        cacheName = "books",
        exceptionCacheName = "bookFailures",
        cachedExceptions = InvalidIsbnException.class
)
public Book findBook(@CacheKey String isbn) {
    return repository.findByIsbn(isbn);
}
~~~

Chỉ dùng exception caching khi lỗi thực sự có tính ổn định. Không cache tùy tiện lỗi mạng, timeout, database unavailable hoặc lỗi tạm thời: một exception cũ có thể tiếp tục được trả dù nguồn đã phục hồi. Cần đặt TTL cho vùng exception theo provider và kiểm thử `cachedExceptions`/`nonCachedExceptions`.

## 4. `@CachePut` của JCache: dùng `@CacheValue` để chỉ định giá trị ghi

Đây là điểm khác biệt quan trọng nhất so với Spring `@CachePut`.

Trong JCache, method được gọi; tham số mang `@CacheValue` là **giá trị sẽ được đưa vào cache**. Các tham số khóa được xác định bằng `@CacheKey` hoặc quy tắc key generator.

~~~java
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheValue;

// Minh họa trong một Spring-managed service.
@CachePut(cacheName = "products")
public void update(
        @CacheKey String productId,
        @CacheValue Product updatedProduct) {
    repository.update(updatedProduct);
}
~~~

Sau khi method chạy thành công, `updatedProduct` được put vào cache dưới key sinh từ `productId`. Method có thể trả `void`, vì cache value đã được truyền qua `@CacheValue`.

### Thời điểm put

`afterInvocation` mặc định là `true`:

~~~text
Caller gọi update(P1, updatedProduct)
                 |
                 v
          Chạy method update
                 |
          Method thành công
                 |
                 v
      Lấy tham số @CacheValue
                 |
                 v
     Sinh key từ @CacheKey / generator
                 |
                 v
        Cache.put(key, value)
~~~

Có thể đặt `afterInvocation=false` để put trước khi method chạy:

~~~java
// Minh họa: cache được cập nhật trước khi logic update chạy.
@CachePut(cacheName = "products", afterInvocation = false)
public void update(
        @CacheKey String productId,
        @CacheValue Product updatedProduct) {
    repository.update(updatedProduct);
}
~~~

Cấu hình này cần thận trọng: nếu repository update thất bại, cache có thể đã chứa giá trị mới trong khi nguồn dữ liệu chưa được cập nhật. Mặc định ghi sau invocation thường dễ suy luận hơn.

JCache `@CachePut` còn có `cacheFor` và `noCacheFor` để quy định cách xử lý tham số cache value khi method ném exception và `afterInvocation=true`. Chỉ cấu hình chúng khi nghiệp vụ có chủ đích lưu giá trị dù invocation thất bại; đừng coi cache put là transaction thay thế database.

## 5. `@CacheRemove`: xóa một entry theo key

`@CacheRemove` tương đương gần nhất với `@CacheEvict` khi xóa một entry. Method thực hiện nghiệp vụ, rồi cache entry tương ứng được xóa.

~~~java
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CacheRemove;

// Minh họa trong service có repository.
@CacheRemove(cacheName = "products")
public void delete(@CacheKey String productId) {
    repository.deleteById(productId);
}
~~~

Mặc định `afterInvocation=true`: xóa sau khi method hoàn thành thành công. Nếu method ném exception, remove không xảy ra theo mặc định.

Có thể đặt `afterInvocation=false` để remove trước khi method chạy:

~~~java
@CacheRemove(cacheName = "products", afterInvocation = false)
public void delete(@CacheKey String productId) {
    repository.deleteById(productId);
}
~~~

Khi dùng kiểu này, dù repository delete thất bại, cache entry đã bị loại; lần đọc sau phải tải lại. Điều đó có thể tạo thêm cache miss nhưng tránh giữ bản cũ nếu trạng thái nguồn đang không chắc chắn.

### Xử lý exception khi remove

`@CacheRemove` hỗ trợ:

- `evictFor`: các kiểu exception mà khi method ném ra vẫn thực hiện remove.
- `noEvictFor`: các kiểu exception mà không thực hiện remove.

Các thuộc tính này chỉ áp dụng khi `afterInvocation=true`. Khi cấu hình cả hai, exception phải khớp `evictFor` và không khớp `noEvictFor` để eviction được thực hiện.

~~~java
// Minh họa: remove cả khi delete ném ResourceNotFoundException.
@CacheRemove(
        cacheName = "products",
        evictFor = ResourceNotFoundException.class
)
public void delete(@CacheKey String productId) {
    repository.deleteById(productId);
}
~~~

Đây là lựa chọn nghiệp vụ, không phải mặc định phù hợp cho mọi lỗi. Ví dụ lỗi authorization không nên vô tình kích hoạt cache mutation nếu chưa có chính sách rõ ràng.

## 6. `@CacheRemoveAll`: xóa toàn bộ entry trong một cache

`@CacheRemoveAll` tương đương với `@CacheEvict(allEntries = true)` của Spring. Nó gọi thao tác `removeAll()` trên vùng cache đã chỉ định; không cần tạo key riêng.

~~~java
import javax.cache.annotation.CacheRemoveAll;

// Minh họa trong một Spring-managed service.
@CacheRemoveAll(cacheName = "products")
public void invalidateProductCache() {
    // Có thể ghi nhận sự kiện hoặc chạy logic nghiệp vụ phù hợp.
}
~~~

Mặc định thao tác xóa xảy ra **sau khi method thành công**. Có thể đặt `afterInvocation=false` để xóa trước khi method chạy. Nếu method ném exception, mặc định vùng cache không bị xóa.

`@CacheRemoveAll` chỉ xóa entry của cache `"products"`. Nó **không xóa database**, không tự xóa cache `"productDetails"` hoặc `"searchResults"` và cũng không tự phát thông báo tới local cache ở JVM khác nếu provider không hỗ trợ cơ chế chia sẻ/invalidation tương ứng.

Nếu một thao tác cập nhật ảnh hưởng nhiều vùng cache, có thể cần nhiều method invalidation, một service điều phối hoặc API cache phù hợp. Không dùng `@CacheRemoveAll` quá rộng khi chỉ cần xóa một key.

## 7. Sinh key: `@CacheKey` và `CacheKeyGenerator`

Quy tắc mặc định của JCache:

- Nếu **không có** tham số nào mang `@CacheKey`, tất cả tham số method được dùng để sinh key (ngoại trừ tham số mang vai trò value `@CacheValue` trong operation put).
- Nếu có **ít nhất một** tham số mang `@CacheKey`, chỉ những tham số được đánh dấu mới tham gia key.
- `@CacheValue` đánh dấu value cho `@CachePut`, không phải định danh entry.

Ví dụ tìm sản phẩm có thêm `traceId`:

~~~java
@CacheResult(cacheName = "products")
public Product find(
        @CacheKey String productId,
        String traceId,
        boolean includeInventory) {
    return repository.find(productId, includeInventory);
}
~~~

Key chỉ gồm `productId`. `traceId` bị bỏ qua. Nhưng `includeInventory` cũng bị bỏ qua vì khi đã có `@CacheKey`, chỉ tham số được đánh dấu mới tham gia. Nếu `includeInventory` làm thay đổi kết quả trả về, ví dụ trên là **sai thiết kế**. Hãy đánh dấu cả tham số đó:

~~~java
@CacheResult(cacheName = "products")
public Product find(
        @CacheKey String productId,
        @CacheKey boolean includeInventory,
        String traceId) {
    return repository.find(productId, includeInventory);
}
~~~

### `CacheKeyGenerator`

`javax.cache.annotation.CacheKeyGenerator` tạo một `GeneratedCacheKey` từ `CacheKeyInvocationContext`. Implementation phải thread-safe. `GeneratedCacheKey` phải bất biến, serializable và tuân thủ hợp đồng `equals()`/`hashCode()`; hai key bằng nhau phải có cùng hash code.

Key generator tùy chỉnh hữu ích khi identity gồm tenant, loại projection hoặc chuẩn hóa dữ liệu đặc thù. Đừng chỉ trả `hashCode()` trần làm key vì collision có thể khiến hai kết quả khác nhau bị coi là cùng entry.

### So sánh key generation của Spring và JCache

Spring `SimpleKeyGenerator` mặc định:
- Không tham số → `SimpleKey.EMPTY`.
- Một tham số → chính đối tượng tham số.
- Nhiều tham số → `SimpleKey` chứa tất cả tham số.

JCache mặc định tạo `GeneratedCacheKey` từ các tham số key đã chọn. Vì vậy `@Cacheable(cacheNames="products")` và `@CacheResult(cacheName="products")` có thể không tìm thấy entry của nhau dù cùng truyền `"P1"`.

Nếu hai hệ thống annotation cùng tác động lên **một cache**, phải thống nhất chính xác thuật toán key. Cách dễ bảo trì nhất thường là chọn một annotation family cho mỗi cache/use case, thay vì trộn ngẫu nhiên.

## 8. `@CacheDefaults`: mặc định dùng chung ở cấp class

`@CacheDefaults` của JCache gần tương đương `@CacheConfig` của Spring. Nó cho phép đặt mặc định cho các operation trong class:

- `cacheName`
- `cacheResolverFactory`
- `cacheKeyGenerator`

~~~java
import javax.cache.annotation.CacheDefaults;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheRemove;

@CacheDefaults(cacheName = "products")
public class ProductService {

    @CacheResult
    public Product find(@CacheKey String id) {
        return repository.find(id);
    }

    @CacheRemove
    public void delete(@CacheKey String id) {
        repository.delete(id);
    }
}
~~~

Đây là minh họa cấu trúc; class đầy đủ cần khai báo các import/field tương ứng. Operation có thể ghi đè giá trị mặc định ở cấp class.

Nếu không khai báo `cacheName` trên method và cũng không có `@CacheDefaults`, Spring JCache support có quy tắc tạo cache name mặc định từ tên class đầy đủ, method và kiểu tham số. Điều này có thể tạo nhiều vùng cache khác nhau ngoài ý muốn. Với cache dùng chung giữa các method, hãy đặt tên rõ ràng bằng `@CacheDefaults` hoặc thuộc tính `cacheName`.

### `CacheResolverFactory`

JCache có `CacheResolverFactory` để tạo `CacheResolver` cho operation. Resolver quyết định cache nào được sử dụng trong invocation. Đây là lựa chọn khi cache phụ thuộc vào tenant, ngữ cảnh hoặc provider. JCache resolver chọn **một cache cho mỗi operation**; Spring Cache annotations hỗ trợ danh sách nhiều cache trong một operation.

Factory và generator tùy chỉnh phải an toàn khi nhiều thread cùng gọi. Nếu phụ thuộc request context, cần đảm bảo scope đến từ ngữ cảnh đã xác thực và không làm cache key lẫn giữa tenant.

## 9. Ví dụ hoàn chỉnh: bốn annotation JCache trong Spring Boot

Ví dụ dùng **Java 17, Spring Boot 3.3.5, Maven**. Nó thêm JCache API 1.1.1 nhưng dùng `ConcurrentMapCacheManager` của Spring làm storage. Cách này chứng minh Spring có thể xử lý JCache annotations mà không cần chuyển sang Ehcache/Hazelcast hoặc một JCache provider riêng.

Các bước trong chương trình:

1. `@CacheResult` đọc sản phẩm P1 lần đầu, lần sau hit.
2. `@CachePut` luôn chạy method và ghi `Product` qua tham số `@CacheValue`.
3. `@CacheRemove` xóa entry P1 sau thao tác delete thành công.
4. `@CacheRemoveAll` xóa mọi entry trong cache products.
5. Bộ đếm nguồn chứng minh lần nào method đọc thực sự được chạy.

### Cấu trúc thư mục

~~~text
jcache-annotations-demo/
├── pom.xml
└── src/main/java/example/jcache/
    ├── DemoApplication.java
    └── CatalogService.java
~~~

### `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jcache-annotations-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-cache` mang theo `spring-context-support`; dependency `cache-api` cung cấp annotation JSR-107. **Ví dụ không có JCache provider**: backend được tạo bằng Spring `ConcurrentMapCacheManager`. Spring hỗ trợ JCache annotations thông qua caching abstraction nên đây là cấu hình hợp lệ để học và chạy demo.

### `src/main/java/example/jcache/CatalogService.java`

~~~java
package example.jcache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheRemoveAll;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheValue;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ConcurrentMap<String, Product> source =
            new ConcurrentHashMap<>();
    private final AtomicInteger sourceReads = new AtomicInteger();

    public record Product(String id, String name, int version) {}

    public CatalogService() {
        source.put("P1", new Product("P1", "Pen", 1));
        source.put("P2", new Product("P2", "Marker", 1));
    }

    @CacheResult(cacheName = "products")
    public Product find(@CacheKey String productId) {
        sourceReads.incrementAndGet();
        Product product = source.get(productId);
        if (product == null) {
            throw new IllegalArgumentException("Unknown product: " + productId);
        }
        return product;
    }

    @CachePut(cacheName = "products")
    public void rename(
            @CacheKey String productId,
            @CacheValue Product updatedProduct) {
        if (!productId.equals(updatedProduct.id())) {
            throw new IllegalArgumentException("Product ID mismatch");
        }
        source.put(productId, updatedProduct);
    }

    @CacheRemove(cacheName = "products")
    public void delete(@CacheKey String productId) {
        source.remove(productId);
    }

    @CacheRemoveAll(cacheName = "products")
    public void invalidateAll() {
        // The annotation clears the cache region after this method succeeds.
    }

    // Simulates an external system recreating the product after deletion.
    public void seedFromExternalSystem(Product product) {
        source.put(product.id(), product);
    }

    public int sourceReads() {
        return sourceReads.get();
    }
}
~~~

Điểm cần chú ý:

- `find` dùng `@CacheResult`, nên method chỉ đọc nguồn khi cache miss.
- `rename` dùng JCache `@CachePut`. `@CacheKey` chọn ID, `@CacheValue` chọn object `Product` được put. Method trả `void` vẫn hợp lệ.
- `delete` dùng `@CacheRemove` để xóa đúng entry của ID.
- `invalidateAll` dùng `@CacheRemoveAll` để xóa toàn vùng cache sau khi method thành công.
- `seedFromExternalSystem` mô phỏng một hệ thống khác ghi lại dữ liệu sau delete. Nó giúp chứng minh lần đọc tiếp theo không lấy entry cũ.

### `src/main/java/example/jcache/DemoApplication.java`

~~~java
package example.jcache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    CommandLineRunner demo(CatalogService catalog) {
        return args -> {
            System.out.println("first=" + catalog.find("P1"));
            System.out.println("hit=" + catalog.find("P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            catalog.rename(
                    "P1",
                    new CatalogService.Product("P1", "Blue Pen", 2));
            System.out.println("after-put=" + catalog.find("P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            catalog.delete("P1");
            catalog.seedFromExternalSystem(
                    new CatalogService.Product("P1", "Recreated Pen", 3));
            System.out.println("after-remove=" + catalog.find("P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            System.out.println("second-key=" + catalog.find("P2"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            catalog.invalidateAll();
            System.out.println("after-remove-all-P1=" + catalog.find("P1"));
            System.out.println("after-remove-all-P2=" + catalog.find("P2"));
            System.out.println("sourceReads=" + catalog.sourceReads());
        };
    }
}
~~~

### Chạy chương trình

Trong thư mục `jcache-annotations-demo`, cài JDK 17+ và Maven rồi chạy:

~~~bash
mvn -q spring-boot:run
~~~

Ngoài log khởi động Spring Boot, các dòng do `CommandLineRunner` in sẽ là:

~~~text
first=Product[id=P1, name=Pen, version=1]
hit=Product[id=P1, name=Pen, version=1]
sourceReads=1
after-put=Product[id=P1, name=Blue Pen, version=2]
sourceReads=1
after-remove=Product[id=P1, name=Recreated Pen, version=3]
sourceReads=2
second-key=Product[id=P2, name=Marker, version=1]
sourceReads=3
after-remove-all-P1=Product[id=P1, name=Recreated Pen, version=3]
after-remove-all-P2=Product[id=P2, name=Marker, version=1]
sourceReads=5
~~~

Giải thích:

1. `find("P1")` lần đầu miss, method chạy và đọc nguồn. Lần gọi thứ hai hit nên `sourceReads` vẫn là 1.
2. `rename` luôn chạy, cập nhật nguồn và JCache `@CachePut` ghi `Product(...Blue Pen, version=2)` từ tham số `@CacheValue`. Lần `find` tiếp theo trả bản mới mà không tăng sourceReads.
3. `delete` xóa dữ liệu nguồn và JCache `@CacheRemove` xóa entry P1 sau khi method thành công. Khi hệ thống ngoài ghi lại P1 với tên `Recreated Pen`, lần `find` tiếp theo miss và đọc bản mới; bộ đếm tăng lên 2.
4. `find("P2")` tạo thêm entry thứ hai; bộ đếm thành 3.
5. `invalidateAll` gọi `@CacheRemoveAll`, xóa cả hai entry cache. Nguồn dữ liệu vẫn còn P1 và P2. Hai lần đọc tiếp theo đều miss, nên `sourceReads=5`.

Ví dụ chạy trên cache in-memory trong một JVM; nó không có TTL, persistence, distributed invalidation hoặc transaction database. Mục đích là chứng minh ngữ nghĩa bốn JCache annotations trong Spring.

## 10. Kích hoạt JCache annotations trong Spring

Spring tự bật hỗ trợ JCache annotations cùng với caching annotation thông thường khi có đủ:

1. JSR-107 API (`javax.cache`).
2. Module `spring-context-support`.
3. `@EnableCaching` hoặc XML `<cache:annotation-driven/>`.
4. Một `CacheManager` phù hợp trong Spring context.

Với Spring Boot, `spring-boot-starter-cache` bao gồm `spring-context-support`; thêm JCache API nếu ứng dụng dùng JCache annotations. Không cần tạo riêng một `@EnableJCache`.

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

Đây là cấu hình Spring Cache manager đơn giản dùng được với JCache annotations. Nếu ứng dụng có JCache provider thật như Ehcache 3, Hazelcast hoặc Infinispan, Spring Boot có thể phát hiện `CachingProvider` và tạo `JCacheCacheManager`.

Ví dụ properties khi muốn ép Spring Boot dùng JCache provider:

~~~properties
spring.cache.type=jcache
spring.cache.jcache.provider=org.ehcache.jsr107.EhcacheCachingProvider
spring.cache.jcache.config=classpath:ehcache.xml
~~~

Đoạn này chỉ áp dụng khi dependency Ehcache/provider tương ứng và file `ehcache.xml` tồn tại trong classpath. Nếu có nhiều JCache provider, cần chọn rõ provider. Khi tự khai báo `CacheManager` bean, cần hiểu auto-configuration sẽ không tự thay bean đó bằng provider khác.

## 11. Khi nào chọn JCache annotations, khi nào chọn Spring annotations?

JCache phù hợp khi dự án cần chuẩn annotation JSR-107, muốn code dễ chuyển giữa framework/provider hoặc đang có hệ thống dùng API JCache. Annotation Spring có SpEL và các tùy chọn sát với Spring programming model.

| Tiêu chí | JCache | Spring Cache |
| --- | --- | --- |
| API | Chuẩn JSR-107 | API của Spring |
| Read operation | `@CacheResult` | `@Cacheable` |
| Cache value khi put | Tham số `@CacheValue` | Return value method |
| Chọn key | `@CacheKey`, `CacheKeyGenerator` | `key` SpEL, `KeyGenerator` |
| Cache name | `cacheName` | `cacheNames`/`value` |
| Điều kiện | Không có SpEL `condition`/`unless` tương đương trực tiếp | Có `condition`, `unless` |
| Bỏ qua cache lookup | `skipGet=true` trên `@CacheResult` | Ngữ nghĩa khác, không thay thế trực tiếp |
| Cache exception | Có exception cache riêng | Không có cùng cơ chế annotation chuẩn |
| Xóa entry | `@CacheRemove` | `@CacheEvict` |
| Xóa cả cache | `@CacheRemoveAll` | `@CacheEvict(allEntries=true)` |
| Defaults cấp class | `@CacheDefaults` | `@CacheConfig` |
| Số cache trong một operation | JCache resolver chọn một cache | Spring annotations có thể chỉ định nhiều cache |

Spring Boot khuyến nghị không trộn lẫn hai bộ annotation một cách tùy tiện. Spring Framework cho phép các service khác nhau dùng hai bộ annotation, nhưng nếu chúng cùng tác động **một cache**, phải thống nhất key generation và cache identity.

Ví dụ nguy hiểm:

~~~java
// Spring: key mặc định của một tham số String có thể là chính String đó.
@org.springframework.cache.annotation.Cacheable("products")
public Product findSpring(String id) {
    return repository.find(id);
}

// JCache: key mặc định là GeneratedCacheKey theo tham số.
@javax.cache.annotation.CacheResult(cacheName = "products")
public Product findJCache(String id) {
    return repository.find(id);
}
~~~

Dù cùng tên `"products"` và cùng input `"P1"`, hai cách tạo key mặc định có thể khác nhau. Đừng mặc định chúng dùng chung entry. Nếu buộc phải interoperate, hãy thiết kế và kiểm thử key generator tương thích cho cả hai.

## 12. Giới hạn và lưu ý về dữ liệu

### Không có `condition`/`unless` dạng SpEL

JCache không có thuộc tính SpEL trực tiếp tương đương `condition` và `unless` của Spring `@Cacheable`. `skipGet` chỉ điều khiển có lookup trước hay không; nó không phải bộ lọc kết quả. Nếu cần quyết định phức tạp dựa trên input/result, cân nhắc API cache tường minh, method nghiệp vụ tách riêng hoặc resolver/generator tùy chỉnh.

### Key phải chứa đủ phạm vi dữ liệu

Nếu ID sản phẩm chỉ duy nhất trong tenant, key cần gồm `tenantId` và `productId`. Nếu kết quả thay đổi theo locale, projection hoặc người xem, những yếu tố đó cũng phải được xét. Không để cache hit bỏ qua kiểm tra quyền duy nhất nằm trong thân method; authorization phải chạy ở đường gọi luôn được thực thi.

### TTL và eviction vẫn do provider quản lý

JCache annotations không tự đặt TTL, maximum size hoặc eviction policy. Các chính sách đó đến từ cache provider. `@CacheRemove` và `@CacheRemoveAll` chỉ thực hiện khi operation được gọi theo ngữ nghĩa after/before invocation đã chọn.

### Exception caching có thể giữ lỗi cũ

Nếu một lỗi chỉ là tạm thời, cache exception sẽ khiến caller tiếp tục nhận lỗi cũ trong thời gian entry còn sống. Chỉ cache lỗi có tính ổn định và đặt expiration riêng cho exception cache. Kiểm tra cả `cachedExceptions` và `nonCachedExceptions`.

### Transaction và update cache

Mặc định `@CachePut` ghi sau khi method hoàn thành thành công, nhưng không tự bảo đảm atomicity giữa database và cache. Với transaction rollback, event sau commit, nhiều replica hoặc cập nhật đồng thời, cần xác định thời điểm ghi/xóa và test provider thực. Không dùng `afterInvocation=false` nếu chưa chấp nhận rủi ro cache thay đổi trước khi nghiệp vụ thành công.

### Null và cache provider

Null caching phụ thuộc abstraction/provider. Không giả định mọi JCache provider đều lưu null theo cùng cách; kiểm tra contract và cấu hình của provider. Nếu không có giá trị hợp lệ, thiết kế negative caching hoặc bỏ cache theo chính sách rõ ràng.

## 13. Kiểm thử và chẩn đoán

Một integration test cần chứng minh operation thực sự được intercept và key đúng:

| Ca kiểm thử | Thao tác | Kỳ vọng |
| --- | --- | --- |
| Result miss | Gọi `find(P1)` lần đầu | Method chạy, source counter tăng |
| Result hit | Gọi `find(P1)` lần hai | Method bị bỏ qua, counter không tăng |
| Put | Gọi `rename(P1, updatedProduct)` rồi find | Trả đúng value `@CacheValue` mới |
| Remove | Delete P1 rồi tái tạo nguồn bằng giá trị mới | Lần đọc tiếp theo lấy giá trị mới, không hit entry cũ |
| Remove all | Cache P1 và P2, gọi invalidateAll | Cả hai lần đọc tiếp theo đều miss |
| Key selection | Thêm traceId không đánh dấu `@CacheKey` | TraceId không tham gia key |
| Key scope | Hai tenant có cùng ID | Không dùng chung entry nếu dữ liệu khác nhau |
| Exception | Method ném exception theo cấu hình | Cache/remove tuân theo `cachedExceptions`, `evictFor` và `afterInvocation` |
| Proxy | Gọi qua injected bean | Interceptor được kích hoạt |
| Self-invocation | Gọi `this.find(...)` | Nhận diện việc bypass proxy |
| Provider thực | Chạy với Ehcache/Redis/Hazelcast | Serializer, TTL, key và exception semantics phù hợp |

### Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@CacheResult` không hit | Key khác hoặc cache name khác | Kiểm tra `@CacheKey`, generator và cache name |
| `@CachePut` không ghi đúng value | Thiếu `@CacheValue` hoặc import nhầm Spring annotation | Dùng `javax.cache.annotation.CacheValue` và kiểm tra import |
| Read vẫn thấy dữ liệu cũ sau update | Put key khác key của result | Thống nhất `@CacheKey` giữa read, put và remove |
| Xóa P1 nhưng cache còn | Method ném exception và `afterInvocation=true` | Kiểm tra `evictFor`/`noEvictFor` hoặc thời điểm xóa |
| Xóa cả vùng nhưng chỉ một cache đổi | `cacheName` khác hoặc resolver khác | Kiểm tra tên và resolver |
| Hai annotation family không dùng chung entry | Key generator mặc định khác nhau | Dùng một bộ annotation hoặc key generator tương thích |
| JCache annotation không hoạt động | Thiếu JCache API hoặc `spring-context-support`, chưa bật caching | Kiểm tra dependency và `@EnableCaching` |
| Method cache không được intercept | Self-invocation hoặc bean không do Spring quản lý | Gọi qua proxy |
| Exception cũ tiếp tục được ném | Exception cache chưa hết hạn | Kiểm tra exceptionCacheName và TTL |
| Xóa cache nhưng database cũng bị xóa? | Nhầm `@CacheRemoveAll` là thao tác nghiệp vụ | Annotation chỉ xóa cache; method body mới quyết định dữ liệu nguồn |

## 14. Bài tập tự kiểm tra

**Bài 1.** `@CacheResult(cacheName="products")` được gọi hai lần cùng ID. Lần thứ hai có chạy method không?  
**Đáp án:** nếu entry tồn tại và cache hit, method không chạy; giá trị từ cache được trả về.

**Bài 2.** JCache `@CachePut` lưu return value hay tham số?  
**Đáp án:** tham số được đánh dấu `@CacheValue`. Đây là khác biệt lớn so với Spring `org.springframework.cache.annotation.CachePut`.

**Bài 3.** Method `find(String id, String traceId)` chỉ đánh dấu `id` bằng `@CacheKey`. Trace ID có tham gia key không?  
**Đáp án:** không. Khi có ít nhất một `@CacheKey`, chỉ những tham số được đánh dấu mới dùng tạo key.

**Bài 4.** `@CacheRemove` mặc định xóa trước hay sau method?  
**Đáp án:** sau khi method hoàn thành thành công (`afterInvocation=true`). Có thể đổi thành false để xóa trước invocation.

**Bài 5.** `@CacheRemoveAll` có xóa database không?  
**Đáp án:** không. Nó xóa toàn bộ entry của cache được chỉ định; dữ liệu nguồn chỉ thay đổi nếu method body làm việc đó.

**Bài 6.** Có thể dùng JCache annotation với `ConcurrentMapCacheManager` không?  
**Đáp án:** có. Spring hỗ trợ JCache annotations trên cache abstraction, không bắt buộc cache store phải là JCache provider.

**Bài 7.** Vì sao Spring `@Cacheable` và JCache `@CacheResult` có thể không thấy entry của nhau?  
**Đáp án:** key generator mặc định khác nhau; Spring dùng `SimpleKeyGenerator`, JCache dùng `GeneratedCacheKey` theo tham số được chọn.

**Bài 8.** `skipGet=true` có nghĩa gì?  
**Đáp án:** bỏ bước lookup cache trước khi method chạy; method luôn thực thi và return value vẫn được cache. Nó không giống hệt JCache `@CachePut` dùng `@CacheValue`.

**Bài 9.** Khi nào nên cache exception?  
**Đáp án:** chỉ với lỗi ổn định, có thể tái sử dụng cho cùng key. Lỗi tạm thời như timeout hoặc database unavailable thường không nên bị cache.

## Tài liệu tham khảo chính thức

- Spring Framework – JCache (JSR-107) Annotations: https://docs.spring.io/spring-framework/reference/integration/cache/jsr-107.html
- Spring Framework – Declarative Annotation-based Caching: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Boot – Caching, JCache provider detection và cấu hình: https://docs.spring.io/spring-boot/reference/io/caching.html
- JCache 1.1.1 – `CacheResult`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheResult.html
- JCache 1.1.1 – `CachePut`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CachePut.html
- JCache 1.1.1 – `CacheRemove`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheRemove.html
- JCache 1.1.1 – `CacheRemoveAll`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/CacheRemoveAll.html
- JCache 1.1.1 – `CacheKey`, `CacheValue` và package API: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/package-summary.html

**Ghi nhớ:** `@CacheResult` đọc và cache kết quả method; JCache `@CachePut` luôn thực thi và lưu tham số `@CacheValue`; `@CacheRemove` xóa một key; `@CacheRemoveAll` xóa toàn vùng. Spring hỗ trợ các annotation này khi JCache API và `spring-context-support` có mặt cùng `@EnableCaching`. Hãy đặc biệt chú ý khác biệt key generation và import giữa JCache với Spring `@CachePut`.