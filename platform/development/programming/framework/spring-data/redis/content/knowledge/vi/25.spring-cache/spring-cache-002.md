# Cấu hình `@EnableCaching` và `RedisCacheManager` trong Spring Data Redis

Spring Cache là một lớp trừu tượng cho phép ứng dụng lưu kết quả của phương thức, đọc lại kết quả đã lưu và vô hiệu hóa dữ liệu cũ mà không buộc business code phải tự gọi Redis ở mọi nơi. Khi kết hợp với Spring Data Redis, **`RedisCacheManager`** đóng vai trò quản lý các cache được lưu trong Redis, còn **`@EnableCaching`** bật cơ chế xử lý các annotation như `@Cacheable`, `@CachePut` và `@CacheEvict`.

Hai thành phần phục vụ những mục đích khác nhau:

- **`@EnableCaching`** kích hoạt hạ tầng Spring Cache và cơ chế chặn lời gọi phương thức để áp dụng các quy tắc caching.
- **`RedisCacheManager`** cung cấp các `Cache` thực sự, quyết định cách kết nối Redis, thời gian sống (TTL), cách đặt tên key, serializer và những chính sách lưu cache khác.
- **Annotation trên phương thức** diễn đạt khi nào cần tìm cache, gọi phương thức gốc, lưu kết quả hoặc xóa cache.
- **Redis server** lưu dữ liệu cache dưới dạng key/value và quản lý TTL, giới hạn bộ nhớ cùng chính sách eviction.

Điều cốt lõi: chỉ tạo một `RedisCacheManager` không tự khiến mọi phương thức được cache; chỉ gắn `@EnableCaching` cũng không tự chỉ định Redis là backend khi ứng dụng có nhiều cache provider. Cần hiểu cách hai phần được kết nối và cách hoạt động của proxy trong Spring.

## 1. Luồng xử lý Spring Cache với Redis

Giả sử có phương thức:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findById(String id) {
    return productStore.findById(id);
}
```

Khi một bean khác gọi `findById("p-42")` qua Spring proxy, hạ tầng cache hoạt động theo hướng:

```text
Client / Controller
        |
        v
Spring bean proxy do @EnableCaching kích hoạt
        |
        v
@Cacheable(cacheNames="products", key="p-42")
        |
        v
RedisCacheManager -> Cache "products"
        |
        +---- Cache HIT ----> giải mã giá trị Redis
        |                              |
        |                              v
        |                         trả ProductDto
        |
        +---- Cache MISS ---> gọi findById("p-42")
                                      |
                                      v
                               productStore.findById(...)
                                      |
                                      v
                               serialize kết quả
                                      |
                                      v
                               lưu Redis với TTL
                                      |
                                      v
                               trả ProductDto
```

Spring Cache sử dụng **method result caching**: cache thường lưu *kết quả đã tính* của phương thức, không lưu toàn bộ trạng thái của service.

Ví dụ, hai lời gọi liên tiếp với cùng key:

```java
ProductDto first = productService.findById("p-42");
ProductDto second = productService.findById("p-42");
```

Nếu lần đầu tạo cache entry thành công và entry vẫn còn hợp lệ, lần thứ hai có thể dùng Redis mà không gọi `productStore.findById(...)` lần nữa. Tuy nhiên, cache không phải cam kết rằng key sẽ luôn tồn tại đến cuối TTL: người dùng có thể chủ động xóa, cache có thể bị evict và Redis có thể loại key do áp lực bộ nhớ.

## 2. Những dependency cần có

Trong ứng dụng Spring Boot dùng Redis cho Spring Cache, thường cần hai starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
</dependencies>
```

Với Gradle (cú pháp Groovy):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

**Vai trò:**

| Dependency | Công dụng |
|---|---|
| `spring-boot-starter-cache` | Hỗ trợ Spring Cache abstraction, annotation và các thành phần liên quan |
| `spring-boot-starter-data-redis` | Tích hợp kết nối Redis thông qua Spring Data Redis và Redis client |
| JSON serializer (ví dụ Jackson phù hợp phiên bản) | Chuyển object Java thành dữ liệu lưu Redis và ngược lại nếu ứng dụng chọn JSON |

Ví dụ bên dưới dùng các API quen thuộc của Spring Boot 3.x / Spring Data Redis với Jackson 2. Các phiên bản Spring Boot/Spring Data mới hơn có thể có thay đổi tên API serialization; cần chọn serializer tương thích với bộ thư viện đang chạy.

Ứng dụng phải có một Redis instance truy cập được. Cấu hình ví dụ trong `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

`localhost` chỉ phù hợp khi Redis chạy cùng máy hoặc được ánh xạ cổng thích hợp. Khi ứng dụng chạy trong container, Kubernetes hoặc môi trường cloud, cấu hình endpoint/credentials/TLS tương ứng với hệ thống thực tế. Các giá trị timeout là ví dụ, cần phù hợp với ngân sách độ trễ của request.

## 3. Bật caching bằng `@EnableCaching`

Trong ứng dụng Spring Boot, đặt `@EnableCaching` trên lớp cấu hình:

```java
package com.example.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;

@SpringBootApplication
@EnableCaching
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

Hoặc tạo cấu hình riêng:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheInfrastructureConfiguration {
}
```

`@EnableCaching` bật **annotation-driven caching**. Spring phát hiện những phương thức được đánh dấu `@Cacheable`, `@CacheEvict`, `@CachePut`, `@Caching`, `@CacheConfig` và tạo cơ chế áp dụng thông qua Spring AOP/proxy theo cấu hình mặc định.

### 3.1. Vì sao cần `@EnableCaching`?

Một phương thức có annotation:

```java
@Cacheable("products")
public ProductDto findById(String id) {
    return productStore.findById(id);
}
```

chỉ trở thành lời gọi có xử lý cache khi hạ tầng Spring Cache đã được kích hoạt và đối tượng được gọi thông qua cách Spring quản lý phù hợp.

Nếu không bật caching, annotation có thể chỉ nằm trên method như metadata; không có tác nhân nào chặn lời gọi để tra cache và lưu kết quả.

Tuy nhiên, `@EnableCaching` **không chỉ định Redis cụ thể**. Nó cần một `CacheManager` hoặc `CacheResolver` phù hợp. Spring Boot có thể tự cấu hình cache manager dựa trên các dependency và điều kiện auto-configuration; khi cần cấu hình rõ TTL, serializer và tên cache, ta có thể cung cấp `RedisCacheManager` bean.

### 3.2. Cơ chế proxy và lời gọi nội bộ

Cách mặc định của Spring Cache dựa trên proxy. Vì vậy:

```java
@Service
public class ProductService {

    @Cacheable("products")
    public ProductDto findById(String id) {
        return loadProduct(id);
    }

    public ProductDto findAndLog(String id) {
        return this.findById(id);
    }

    private ProductDto loadProduct(String id) {
        // Lấy dữ liệu nguồn.
        return null;
    }
}
```

Lời gọi `this.findById(id)` trong **cùng object** không đi qua Spring proxy nên có thể bỏ qua cơ chế `@Cacheable`. Đây là lỗi phổ biến khi đánh giá rằng cache “không hoạt động”.

Thông thường nên gọi phương thức cache qua bean do Spring inject vào service/controller khác, hoặc tách trách nhiệm đọc dữ liệu có cache sang một bean độc lập.

Những điểm liên quan:

- Method nên được Spring quản lý và được gọi qua proxy.
- Tạo object bằng `new ProductService()` bên ngoài Spring sẽ không có cache advice.
- Các phương thức `private`, một số phương thức không thể được proxy đúng theo kiểu proxy đang dùng, hoặc self-invocation có giới hạn.
- Chỉ annotation `@Cacheable` không tự làm cho mọi lời gọi nội bộ của object đi qua proxy.
- Khi thiết kế với `final` class/method, cần xét hạn chế của cơ chế proxy và cấu hình Spring AOP tương ứng.

## 4. Dùng cấu hình Spring Boot tự động trước

Nếu ứng dụng chỉ cần các chính sách cache tương đối đơn giản, Spring Boot có thể tự tạo Redis-backed `CacheManager` khi đủ điều kiện và Redis là cache provider được chọn.

Ví dụ:

```yaml
spring:
  cache:
    type: redis
    cache-names:
      - products
      - productLists
      - customerProfiles
    redis:
      time-to-live: 10m
      cache-null-values: false
      use-key-prefix: true
  data:
    redis:
      host: localhost
      port: 6379
```

Giải thích:

| Thuộc tính | Ý nghĩa |
|---|---|
| `spring.cache.type: redis` | Yêu cầu Boot dùng Redis cache provider phù hợp nếu auto-configuration áp dụng |
| `spring.cache.cache-names` | Khai báo tên cache cần khởi tạo |
| `spring.cache.redis.time-to-live` | Đặt TTL mặc định cho entry cache khi Boot dựng cấu hình Redis cache |
| `spring.cache.redis.cache-null-values` | Chọn có cho phép cache kết quả `null` hay không |
| `spring.cache.redis.use-key-prefix` | Dùng tiền tố theo tên cache để tách namespace |
| `spring.data.redis.*` | Kết nối Redis dùng bởi Spring Data Redis |

Các thuộc tính trên thuộc các tính năng của Spring Boot auto-configuration. Khi ứng dụng **tự khai báo `RedisCacheManager` bean**, không nên mặc định rằng mọi `spring.cache.redis.*` sẽ tiếp tục được áp dụng lên bean riêng theo cùng cách Boot tự cấu hình. Nếu tạo manager tùy biến, hãy cấu hình chính sách tương ứng trong code hoặc dùng customizer được hỗ trợ.

### 4.1. Khi nào dùng Boot auto-configuration?

Dùng cấu hình properties là lựa chọn gọn khi:

- Chỉ cần một TTL chung.
- Chưa cần serializer riêng cho từng loại cache.
- Chưa cần chính sách null-value hoặc prefix phức tạp.
- Muốn cấu hình thông qua từng environment mà không thay đổi Java code.

Khi các cache cần TTL khác nhau, yêu cầu serializer JSON, prefix theo phiên bản dữ liệu hoặc behavior cụ thể, tạo một `RedisCacheManager` bean sẽ cho phép kiểm soát nhiều hơn.

## 5. Tạo `RedisCacheManager` bean bằng Java

`RedisCacheManager` dùng `RedisConnectionFactory` để kết nối Redis và `RedisCacheConfiguration` để điều khiển cách một cache lưu các entry.

Ví dụ đầy đủ:

```java
package com.example.catalog.config;

import java.time.Duration;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class RedisCachingConfiguration {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory
    ) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofMinutes(10))
                    .disableCachingNullValues()
                    .serializeKeysWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(new StringRedisSerializer())
                    )
                    .serializeValuesWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(
                                new GenericJackson2JsonRedisSerializer()
                            )
                    )
                    .computePrefixWith(
                        cacheName -> "catalog:v1::" + cacheName + "::"
                    );

        Map<String, RedisCacheConfiguration> perCache =
                Map.of(
                    "products",
                    defaults.entryTtl(Duration.ofMinutes(15)),

                    "productLists",
                    defaults.entryTtl(Duration.ofSeconds(45)),

                    "customerProfiles",
                    defaults.entryTtl(Duration.ofMinutes(5))
                );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(perCache)
                .build();
    }
}
```

Ở đây:

1. `RedisConnectionFactory` do cấu hình Redis của ứng dụng cung cấp.
2. `RedisCacheConfiguration.defaultCacheConfig()` tạo cấu hình ban đầu cho cache.
3. `entryTtl(...)` đặt thời gian sống cho dữ liệu trong Redis.
4. `disableCachingNullValues()` không cho lưu kết quả null dưới dạng entry cache.
5. `serializeKeysWith(...)` chuyển key cache thành byte theo cách mong muốn.
6. `serializeValuesWith(...)` chuyển object Java sang JSON và đọc ngược.
7. `computePrefixWith(...)` tạo namespace rõ ràng cho từng cache.
8. `withInitialCacheConfigurations(...)` đặt cấu hình TTL riêng cho những cache đã biết.
9. `build()` tạo `RedisCacheManager` được Spring đưa vào container dưới dạng bean.

Nếu chỉ có một `CacheManager` phù hợp, các annotation cache có thể sử dụng bean đó theo cách Spring Cache tìm kiếm manager mặc định. Khi có nhiều manager, cần chọn rõ manager dùng cho từng phương thức hoặc cấu hình resolver thích hợp.

### 5.1. Hiểu `RedisCacheManager` và `RedisCacheConfiguration`

`RedisCacheManager` là đối tượng quản lý các cache theo tên, ví dụ `"products"` hoặc `"customerProfiles"`.

Mỗi cache nhận một `RedisCacheConfiguration` chỉ định:

```text
Cache "products"
  |
  +-- TTL: 15 phút
  +-- Key serializer: StringRedisSerializer
  +-- Value serializer: JSON
  +-- Null value: không lưu
  +-- Prefix: catalog:v1::products::

Cache "productLists"
  |
  +-- TTL: 45 giây
  +-- Key serializer: StringRedisSerializer
  +-- Value serializer: JSON
  +-- Null value: không lưu
  +-- Prefix: catalog:v1::productLists::
```

Cách cấu hình này tránh việc mọi loại dữ liệu đều dùng chung TTL. Danh sách sản phẩm có thể cần làm mới thường xuyên hơn thông tin hồ sơ ít thay đổi, còn cache kết quả tổng hợp tốn công có thể có TTL theo nhu cầu thực tế.

Một lưu ý quan trọng: giá trị TTL được đặt trong `RedisCacheConfiguration` điều khiển key cache do **RedisCacheManager** quản lý. Nó **không tự áp dụng** cho mọi key do `StringRedisTemplate`, `RedisRepository` hoặc Lua script khác ghi vào cùng Redis.

### 5.2. Cấu hình `disableCreateOnMissingCache`

Mặc định, `RedisCacheManager` thường cho phép tạo cache mới khi có lời gọi theo một tên cache chưa được khai báo trước. Nếu dự án muốn tránh cache name bị gõ sai rồi lặng lẽ tạo namespace mới, có thể dùng khả năng hạn chế tạo cache động của builder ở những phiên bản hỗ trợ:

```java
return RedisCacheManager.builder(connectionFactory)
        .cacheDefaults(defaults)
        .withInitialCacheConfigurations(perCache)
        .disableCreateOnMissingCache()
        .build();
```

Với chế độ này, tên cache chưa được định nghĩa có thể khiến Spring Cache không lấy được cache tương ứng và báo lỗi khi phương thức được gọi. Điều đó hữu ích trong những hệ thống có danh sách cache cố định.

Cần cân nhắc khi ứng dụng tạo cache name động theo tenant hoặc tính năng, vì chặn tạo cache mới sẽ thay đổi behavior của các luồng đó.

## 6. TTL mặc định và TTL riêng từng cache

TTL (*time to live*) quy định khoảng thời gian từ lúc cache entry được ghi cho đến khi Redis coi key đã hết hạn.

Ví dụ:

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(10));
```

TTL này thường áp dụng cho các entry trong cache sử dụng `defaults`:

```text
12:00:00   @Cacheable lưu products::p-42
12:10:00   Entry hết thời gian sống
12:10:01   Lần gọi tiếp theo phát hiện miss và gọi method gốc
```

Một cấu hình riêng:

```java
RedisCacheConfiguration productCfg =
        defaults.entryTtl(Duration.ofMinutes(20));

RedisCacheConfiguration listCfg =
        defaults.entryTtl(Duration.ofSeconds(30));
```

sẽ cho `products` và `productLists` hai thời hạn khác nhau.

### 6.1. TTL không đồng nghĩa “giữ key ít nhất từng ấy thời gian”

Một cache key vẫn có thể biến mất trước TTL nếu:

- Ứng dụng gọi `@CacheEvict` hoặc `Cache.evict`.
- Tác vụ quản trị xóa key.
- Redis được cấu hình eviction để giải phóng bộ nhớ và key bị chọn.
- Cache bị xóa toàn bộ theo tên hoặc namespace bởi thao tác tương ứng.

Vì vậy, `@Cacheable` phải được thiết kế để cache miss có thể xảy ra bất cứ lúc nào; phương thức gốc cần có khả năng cung cấp kết quả từ nguồn dữ liệu thật.

### 6.2. TTL mặc định không tự được gia hạn khi đọc

Với cấu hình cache thông thường, đọc trúng một entry **không tự làm mới TTL**. Nếu entry được ghi lúc 12:00 với TTL 10 phút, đọc lại lúc 12:08 thường không kéo dài thời hạn đến 12:18.

Đó là khác biệt giữa **time to live** và **time to idle**. Một số phiên bản Spring Data Redis cung cấp tùy chọn time-to-idle bằng lệnh Redis hỗ trợ, nhưng cần bật rõ, đáp ứng phiên bản Redis và đánh giá chi phí đọc/ghi TTL. Không suy luận rằng `@Cacheable` mặc định là sliding expiration.

### 6.3. TTL rất dài hoặc không có TTL

Cấu hình mặc định của Redis Cache có thể cho phép entry tồn tại không thời hạn nếu không đặt TTL tùy môi trường và cách khởi tạo. Khi tự cấu hình, nên chủ động xác định policy thay vì dựa vào default không được ghi thành tài liệu.

Cache không TTL vẫn có thể bị `@CacheEvict`, xóa thủ công hoặc eviction theo policy Redis. Nếu dữ liệu có thể thay đổi mà không có invalidation tin cậy, cache không TTL dễ trở nên lỗi thời.

## 7. Serializer và khả năng đọc lại object

Redis lưu key và value dưới dạng byte. Spring Cache đưa Java object vào cache, vì vậy `RedisCacheManager` phải chuyển đổi chúng thành byte và khôi phục khi đọc.

### 7.1. Key serializer

Với `StringRedisSerializer`, tên key được biểu diễn dưới dạng chuỗi UTF-8. Ví dụ key cache:

```text
catalog:v1::products::p-42
```

dễ kiểm tra bằng Redis CLI:

```redis
TYPE "catalog:v1::products::p-42"
TTL "catalog:v1::products::p-42"
GET "catalog:v1::products::p-42"
```

Tuy nhiên, giá trị `GET` có thể là JSON chứa metadata type hoặc một định dạng byte khác tùy serializer; không thể giả định mọi kết quả của `GET` đều là chuỗi người đọc dễ hiểu.

### 7.2. Value serializer

Nếu dùng:

```java
.serializeValuesWith(
    RedisSerializationContext.SerializationPair
        .fromSerializer(new GenericJackson2JsonRedisSerializer())
)
```

Spring Data Redis có thể lưu object dưới dạng JSON có thông tin cần thiết để deserialize kiểu dữ liệu theo cơ chế của serializer.

Ví dụ DTO:

```java
package com.example.catalog;

import java.math.BigDecimal;

public record ProductDto(
        String id,
        String name,
        BigDecimal price
) {}
```

Về mặt ý tưởng, dữ liệu cache là một biểu diễn JSON của `ProductDto`; chuỗi JSON thực tế có thể có metadata kiểu, tùy serializer và cấu hình.

Cần phân biệt:

| Lựa chọn serializer | Đặc trưng |
|---|---|
| JDK serialization | Dựa trên Java object serialization; không thuận tiện khi đọc CLI, phụ thuộc tương thích class và cần cân nhắc an toàn |
| `StringRedisSerializer` | Phù hợp khi value thực sự là chuỗi |
| JSON serializer | Dễ trao đổi/quan sát hơn, nhưng phải quản lý kiểu đối tượng và thay đổi schema |
| Serializer tùy biến | Cho phép kiểm soát định dạng chính xác, cần tự chịu trách nhiệm đọc ngược và tương thích |

Các ví dụ API ở đây sử dụng `GenericJackson2JsonRedisSerializer` thuộc dòng Spring Data Redis dùng Jackson 2; khi nâng cấp lên stack Jackson 3, hãy lựa chọn API JSON tương ứng được hỗ trợ bởi phiên bản đó.

**An toàn serialization:** không cho phép dữ liệu từ nguồn không đáng tin tự quyết định class Java bất kỳ khi deserialize; kiểm soát polymorphic typing, danh sách kiểu được hỗ trợ và quyền đọc/ghi Redis theo threat model của ứng dụng. Nên có chính sách thay đổi schema khi triển khai nhiều phiên bản ứng dụng cùng đọc một namespace cache.

### 7.3. Vì sao lỗi serializer thường chỉ xuất hiện sau lần cache hit?

Lần đầu gọi:

```java
ProductDto p = service.findById("p-42");
```

cache miss dẫn tới method thật, kết quả được serialize và lưu. Nếu có lỗi serialization, lỗi có thể xuất hiện ở bước lưu.

Ở lần gọi sau, Spring Cache đọc dữ liệu từ Redis và deserialize thành object. Nếu dữ liệu trong Redis được ghi bằng serializer không tương thích, format cũ hoặc class đã thay đổi không tương thích, có thể xuất hiện lỗi khi cache hit.

Khi thay đổi serializer, nên thay đổi namespace cache/version hoặc có phương án xóa/tái tạo cache an toàn, thay vì để hai format không tương thích dùng cùng key.

## 8. Key prefix: tránh đụng độ tên key giữa các cache

Một ứng dụng có thể có nhiều cache sử dụng cùng giá trị key nghiệp vụ:

```text
products       -> key "42"
customerProfiles -> key "42"
```

Nếu không có tiền tố riêng, hai cache có nguy cơ dùng cùng Redis key và ghi đè dữ liệu nhau.

Redis Cache thường thêm prefix theo tên cache, ví dụ:

```text
products::42
customerProfiles::42
```

Khi có nhiều ứng dụng cùng Redis, có thể thêm prefix theo ứng dụng và phiên bản:

```java
.computePrefixWith(
    cacheName -> "catalog:v1::" + cacheName + "::"
)
```

Khi đó:

```text
catalog:v1::products::42
catalog:v1::customerProfiles::42
```

Prefix giúp:

- Tách cache theo service/module.
- Dễ quan sát và khoanh vùng key.
- Tránh va chạm giữa các cache có cùng key nghiệp vụ.
- Hỗ trợ đổi định dạng dữ liệu bằng một namespace phiên bản mới.
- Giảm nguy cơ thao tác clear ảnh hưởng các key không liên quan nếu namespace được thiết kế đúng.

Không nên vô hiệu hóa prefix chỉ để làm key ngắn hơn, trừ khi đã có thiết kế namespace tương đương. Với `Cache.clear()`, thao tác dọn cache có thể dựa trên prefix để nhận biết key thuộc cache; không có prefix làm tăng nguy cơ xóa nhầm.

### 8.1. Đừng nhầm key của Spring Cache với key của Redis Repository

Giả sử:

```java
@RedisHash("products")
public class ProductEntity {
    @Id
    private String id;
}
```

Redis Repository có thể dùng key dạng:

```text
products:p-42
```

Trong khi `@Cacheable(cacheNames = "products", key = "#p0")` có thể dùng:

```text
products::p-42
```

Chúng là **hai cơ chế lưu dữ liệu khác nhau**. `RedisRepository.save(entity)` không tự cập nhật entry do `@Cacheable` tạo, và TTL của Redis Cache không tự áp dụng vào `@RedisHash` entity.

Nếu vừa dùng Redis Repository làm nguồn dữ liệu vừa dùng Spring Cache, cần quản lý nhất quán vòng đời dữ liệu và tránh đặt namespace trùng nhau.

## 9. Áp dụng `@Cacheable`, `@CachePut` và `@CacheEvict`

Dưới đây là một ví dụ dịch vụ đọc và cập nhật sản phẩm. Ta định nghĩa giao diện nguồn dữ liệu để tập trung vào hành vi cache:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.List;

public interface ProductStore {
    ProductDto findById(String productId);

    List<ProductDto> findPage(int page, int size);

    void updatePrice(String productId, BigDecimal newPrice);
}
```

Một bean implement `ProductStore` có thể sử dụng JPA, REST API hoặc một nguồn dữ liệu đáng tin cậy khác. Ứng dụng thực tế cần cung cấp implementation như bình thường.

Service:

```java
package com.example.catalog;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    private final ProductStore store;

    public ProductService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(
        cacheNames = "products",
        key = "#p0",
        unless = "#result == null"
    )
    public ProductDto findById(String productId) {
        return store.findById(productId);
    }

    @Cacheable(
        cacheNames = "productLists",
        key = "'page:' + #p0 + ':size:' + #p1"
    )
    public List<ProductDto> findPage(int page, int size) {
        return store.findPage(page, size);
    }

    @CacheEvict(
        cacheNames = "products",
        key = "#p0"
    )
    public void changePrice(String productId, BigDecimal newPrice) {
        store.updatePrice(productId, newPrice);
    }
}
```

### 9.1. `@Cacheable`: tra trước, chạy method nếu cache miss

```java
@Cacheable(cacheNames = "products", key = "#p0")
```

- `cacheNames`: cache mà manager sẽ lấy để lưu/đọc entry.
- `key`: biểu thức SpEL xác định key.
- `#p0`: đối số ở vị trí đầu tiên, ít phụ thuộc việc compiler giữ tên parameter.
- `unless`: điều kiện kiểm tra **sau khi method chạy**, có thể từ chối lưu kết quả, chẳng hạn `null`.

Cần phân biệt `condition` và `unless`:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
```

`condition` được đánh giá trước để quyết định có dùng caching cho lời gọi hay không; `unless` được đánh giá sau khi method thực thi và có thể xét `#result`.

Cấu hình `disableCachingNullValues()` ở manager cũng ngăn lưu null. Dùng `unless="#result == null"` diễn đạt rõ quy tắc ngay tại phương thức và giúp tránh cố ghi null trong những cấu hình không cho phép.

### 9.2. `@CacheEvict`: vô hiệu hóa sau cập nhật

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void changePrice(String productId, BigDecimal newPrice) {
    store.updatePrice(productId, newPrice);
}
```

Với `beforeInvocation` mặc định là `false`, thao tác evict được thực hiện sau khi phương thức được gọi thành công theo cơ chế Spring Cache. Nếu method ném exception trước khi trả về, eviction thường không diễn ra ở chế độ này.

Khi `products:p-42` ở nguồn dữ liệu đã thay đổi, xóa entry cache `"products"` cho `p-42` khiến lần đọc sau phải lấy dữ liệu mới. Tuy nhiên, nếu `store.updatePrice(...)` chạy bên trong transaction cơ sở dữ liệu chưa commit, cần cân nhắc **thời điểm evict so với commit**; phần transaction phía sau giải thích thêm.

### 9.3. `@CachePut`: luôn chạy method, rồi lưu kết quả

`@CachePut` khác `@Cacheable`:

```java
@CachePut(cacheNames = "products", key = "#result.id()")
public ProductDto refreshProduct(String productId) {
    return store.findById(productId);
}
```

- `@Cacheable` có thể **bỏ qua thực thi method** nếu cache hit.
- `@CachePut` **luôn thực thi method** rồi dùng kết quả để cập nhật cache (theo điều kiện được cấu hình).
- `@CacheEvict` dùng để **xóa entry** thay vì lưu kết quả mới.

Nếu `refreshProduct` có thể trả null, nên xử lý phù hợp với cấu hình `disableCachingNullValues()`; có thể thêm `unless = "#result == null"` ở `@CachePut`.

Khi ghi dữ liệu nguồn, chọn `@CachePut` nếu có kết quả hoàn chỉnh và xác định được cache value chính xác sau cập nhật. Chọn `@CacheEvict` nếu dễ bảo đảm độ mới hơn bằng cách để lần đọc sau tự nạp lại.

### 9.4. `@CacheConfig` cho các method cùng một cache

Có thể giảm việc lặp tên cache:

```java
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
@CacheConfig(cacheNames = "products")
public class ProductReader {

    private final ProductStore store;

    public ProductReader(ProductStore store) {
        this.store = store;
    }

    @Cacheable(key = "#p0", unless = "#result == null")
    public ProductDto findById(String id) {
        return store.findById(id);
    }

    @CacheEvict(key = "#p0")
    public void invalidate(String id) {
        // Method được gọi qua Spring proxy.
    }
}
```

`@CacheConfig` cung cấp cấu hình mặc định cho các annotation cache trong class, nhưng không tự bật caching nếu thiếu `@EnableCaching`.

## 10. Chọn `CacheManager` khi ứng dụng có nhiều backend

Một ứng dụng có thể vừa dùng cache trong bộ nhớ (chẳng hạn Caffeine), vừa dùng Redis cho cache chia sẻ giữa các instance.

Khi có nhiều `CacheManager`, annotation có thể chọn manager bằng tên bean:

```java
@Cacheable(
    cacheManager = "redisCacheManager",
    cacheNames = "products",
    key = "#p0"
)
public ProductDto findById(String id) {
    return store.findById(id);
}
```

Trong ví dụ cấu hình Java ở phần 5, bean được khai báo bằng method:

```java
@Bean
public RedisCacheManager redisCacheManager(...) { ... }
```

nên tên bean mặc định là `redisCacheManager`, phù hợp để chỉ định trong annotation.

Không nên giả định Spring sẽ luôn chọn đúng manager khi có nhiều lựa chọn. Nếu cần quy tắc phức tạp theo request, tenant hoặc phương thức, Spring Cache còn hỗ trợ `CacheResolver` tùy biến. Khi đó cần thiết kế rõ cache nào thuộc backend nào.

### 10.1. Tên cache và tên bean là hai khái niệm khác nhau

Trong:

```java
@Cacheable(
    cacheManager = "redisCacheManager",
    cacheNames = "products"
)
```

- `"redisCacheManager"` là **tên Spring bean**.
- `"products"` là **tên cache** do manager đó cung cấp.

Đừng đặt nhầm tên cache vào thuộc tính `cacheManager` hoặc ngược lại.

## 11. Dữ liệu có nằm trong cùng Redis với `RedisTemplate` không?

Cùng một `RedisConnectionFactory` có thể được dùng cho `RedisCacheManager`, `StringRedisTemplate`, các Redis repository và những API Redis khác.

Ví dụ:

```text
RedisConnectionFactory
     |
     +-- RedisCacheManager
     |      +-- cache "products"
     |      +-- cache "customerProfiles"
     |
     +-- StringRedisTemplate
     |      +-- key "rate-limit:user:42"
     |
     +-- Redis Repository
            +-- key "sessions:session-42"
```

Chúng có thể dùng cùng server nhưng **không mặc nhiên dùng cùng quy tắc serialization và namespace**.

Một cấu hình `RedisCacheManager` dùng JSON cho cache value không tự thay đổi serializer của `StringRedisTemplate`. Ngược lại, cấu hình JSON serializer cho `RedisTemplate` không tự bảo đảm Spring Cache dùng serializer đó.

Vì vậy, khi kiểm tra Redis bằng CLI, phải xác định key thuộc cơ chế nào và cách lưu byte của từng cơ chế. Không nên dùng `StringRedisTemplate` đọc thô một cache object với kỳ vọng luôn nhận được đúng `ProductDto` của Spring Cache.

## 12. Cache key, SpEL và sự nhất quán của key

`RedisCacheManager` có thể đặt prefix, nhưng **key nghiệp vụ** vẫn do Spring Cache tạo ra.

Nếu không chỉ định:

```java
@Cacheable(cacheNames = "products")
public ProductDto findById(String id) { ... }
```

Spring Cache dùng key generator mặc định dựa trên các đối số. Với một tham số đơn giản, key thường tương ứng với tham số đó; với nhiều tham số, có thể dùng một đối tượng tổng hợp kiểu `SimpleKey`.

Chỉ định key rõ ràng thường dễ quan sát hơn:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductDto findById(String id) { ... }
```

Với tìm kiếm có nhiều tham số:

```java
@Cacheable(
    cacheNames = "productLists",
    key = "'page:' + #p0 + ':size:' + #p1"
)
public List<ProductDto> findPage(int page, int size) { ... }
```

Key ở đây chứa cả trang và kích thước; bỏ `size` có thể khiến hai request khác kích thước dùng nhầm kết quả.

### 12.1. Cẩn thận với parameter name

Viết:

```java
key = "#productId"
```

chỉ hoạt động như mong muốn khi Spring có thể xác định tên tham số `productId`, ví dụ qua metadata do compiler cung cấp và cơ chế parameter discovery thích hợp.

Để ví dụ không phụ thuộc cấu hình tên tham số, `#p0`, `#p1` là lựa chọn rõ ràng. Trong dự án có metadata parameter đầy đủ, dùng tên `#productId` có thể giúp code dễ đọc hơn.

### 12.2. Tránh cache nhầm dữ liệu theo người dùng hoặc tenant

Nếu kết quả phụ thuộc người dùng, tenant, locale, quyền truy cập hoặc header mà key chỉ chứa `productId`, những request khác nhau có thể nhận cùng cache entry dù dữ liệu đáng lẽ khác nhau.

Ví dụ về ý tưởng:

```java
@Cacheable(
    cacheNames = "tenantProducts",
    key = "#p0 + ':' + #p1"
)
public ProductDto findForTenant(String tenantId, String productId) {
    return store.findForTenant(tenantId, productId);
}
```

Tầng bảo mật phải tiếp tục kiểm soát quyền truy cập vào dữ liệu nguồn và cache. Không xem cache key là cơ chế xác thực/ủy quyền.

## 13. Xử lý null, collection rỗng và ngoại lệ

Một phương thức được cache có thể trả về:

- Object hợp lệ.
- `null`.
- Danh sách rỗng.
- Một exception.

Các trường hợp này không mang cùng ý nghĩa.

Với:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    unless = "#result == null"
)
public ProductDto findById(String id) {
    return store.findById(id);
}
```

nếu không tìm thấy sản phẩm và trả `null`, cache không ghi kết quả. Lần request tiếp theo có thể tiếp tục truy vấn nguồn dữ liệu; điều này phù hợp khi sản phẩm có thể được tạo ngay sau đó, nhưng có thể làm nguồn chịu tải lớn nếu cùng một ID không tồn tại bị hỏi nhiều lần.

Một **danh sách rỗng** vẫn là kết quả hợp lệ và có thể được cache:

```java
@Cacheable(cacheNames = "productLists")
public List<ProductDto> findPage(int page, int size) {
    return List.of();
}
```

Với những lỗi do nguồn dữ liệu ném exception, Spring Cache không mặc nhiên lưu một exception như giá trị thành công. Nếu muốn cache negative result hay trạng thái “không tồn tại” trong thời gian ngắn, nên mô hình hóa rõ dữ liệu đó và TTL tương ứng thay vì lẫn lộn với `null`.

## 14. Xóa một entry và xóa toàn bộ cache

`@CacheEvict` có thể xóa một key:

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void invalidateProduct(String productId) {
}
```

Hoặc xóa các entry của cả cache:

```java
@CacheEvict(cacheNames = "productLists", allEntries = true)
public void invalidateProductLists() {
}
```

`allEntries = true` áp dụng thao tác clear cho một tên cache, không có nghĩa xóa mọi key trên Redis server nếu namespace được cấu hình đúng. Tuy nhiên, chi phí clear có thể cao khi cache rất lớn.

Với Redis Cache, cơ chế clear thường cần tìm và xóa các key theo prefix. Một cấu hình cache writer mặc định có thể sử dụng cách quét dựa trên `KEYS` rồi xóa theo batch; trên keyspace lớn, điều này gây ảnh hưởng hiệu năng. Spring Data Redis có hỗ trợ batch strategy sử dụng `SCAN` trong những điều kiện/driver phù hợp.

### 14.1. Tùy chọn `SCAN` cho thao tác clear ở môi trường có nhiều key

Một cách cấu hình cache writer với batch strategy:

```java
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;

RedisCacheWriter writer =
        RedisCacheWriter.nonLockingRedisCacheWriter(
            connectionFactory,
            BatchStrategies.scan(1000)
        );

RedisCacheManager manager =
        RedisCacheManager.builder(writer)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(perCache)
            .build();
```

`BatchStrategies.scan(1000)` là minh họa cách chọn strategy với tham số batch; con số này cần được điều chỉnh theo số lượng key và điều kiện vận hành.

Các giới hạn cần nhớ:

- `SCAN` không biến việc xóa toàn bộ cache thành thao tác nguyên tử.
- Redis Cluster và driver đang dùng có những giới hạn khác nhau về cách thực hiện scan.
- Khóa có thể được thêm/sửa/xóa đồng thời trong lúc quá trình quét diễn ra.
- Không tự gọi `FLUSHDB` hoặc `FLUSHALL` để thay thế `Cache.clear()`; chúng ảnh hưởng phạm vi rộng hơn nhiều.

Trong nhiều ứng dụng, tốt hơn nên vô hiệu **chính xác các entry cần thiết** hoặc dùng prefix/version mới, thay vì thường xuyên xóa cả một cache rất lớn.

## 15. `transactionAware()` và thời điểm ghi/xóa cache

Một tình huống phổ biến:

```text
1. Mở transaction DB.
2. Cập nhật giá sản phẩm trong PostgreSQL.
3. Xóa Redis cache products::p-42.
4. Transaction DB commit hoặc rollback.
```

Nếu cache bị xóa ở bước 3 nhưng DB transaction sau đó rollback, dữ liệu cache có thể bị nạp lại từ nguồn theo một thời điểm không mong muốn. Nếu cache được ghi lại khi DB chưa commit, có thể tạo entry không nhất quán.

Spring Data Redis CacheManager có thể được cấu hình transaction-aware:

```java
return RedisCacheManager.builder(connectionFactory)
        .cacheDefaults(defaults)
        .withInitialCacheConfigurations(perCache)
        .transactionAware()
        .build();
```

`transactionAware()` khiến manager sử dụng cơ chế cache decoration tương thích với Spring transaction, cho phép **trì hoãn một số thao tác cache như put/evict/clear đến sau khi transaction Spring commit thành công**, khi có transaction đang hoạt động phù hợp.

Điều này đặc biệt hữu ích với cache invalidation theo sau cập nhật RDBMS.

### 15.1. Giới hạn của `transactionAware()`

`transactionAware()` **không phải distributed transaction giữa Redis và PostgreSQL**. Nó không bảo đảm:

- Redis và DB commit nguyên tử như một resource duy nhất.
- Việc evict chắc chắn thành công nếu tiến trình chết ngay sau DB commit.
- Mọi thao tác đọc cache được chuyển thành snapshot transaction.
- Tất cả lệnh Redis trong code khác tự tham gia cùng transaction.
- Mọi thao tác cache của mọi API đều được trì hoãn; cần xem rõ semantics của phương thức `putIfAbsent` hoặc `evictIfPresent` và các thao tác có tính tức thời theo interface.

Nếu cần bảo đảm eventual invalidation sau khi DB commit, có thể dùng **transactional outbox** với worker retry và TTL. Khi Redis chỉ là cache, một chiến lược đơn giản hơn là cho phép cache miss và tái tạo từ nguồn thật.

### 15.2. `@CacheEvict(beforeInvocation = true)` là trường hợp riêng

```java
@CacheEvict(
    cacheNames = "products",
    key = "#p0",
    beforeInvocation = true
)
```

Cấu hình này yêu cầu evict trước khi method thực thi, không phù hợp nếu mục tiêu là chỉ xóa sau khi thay đổi dữ liệu nguồn thành công. Hãy cân nhắc ý nghĩa nghiệp vụ trước khi bật.

Nếu cần xử lý sau commit chắc chắn hơn, hãy thiết kế quy trình thay đổi nguồn dữ liệu và phát tín hiệu invalidation rõ ràng; không dựa chỉ vào vị trí annotation để tạo bảo đảm giao dịch.

## 16. Cache stampede và các request đồng thời

Giả sử 200 request cùng hỏi `products::p-42` tại thời điểm key vừa hết TTL:

```text
200 request -> cache MISS
              |
              +-- 200 lần gọi store.findById("p-42") nếu không phối hợp
```

Đây là dạng **cache stampede**. `RedisCacheManager` và `@Cacheable` không nên được mặc định xem như một distributed lock có bảo đảm chỉ một request trên mọi instance được quyền tải lại.

Spring Cache có tùy chọn:

```java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    sync = true
)
public ProductDto findById(String id) {
    return store.findById(id);
}
```

`sync = true` yêu cầu cache provider cố phối hợp việc tính giá trị khi nhiều lời gọi cùng key bị miss, nhưng khả năng và phạm vi đồng bộ phụ thuộc triển khai cache cụ thể. Với Redis trên nhiều JVM, **không mặc định** rằng cấu hình này bảo đảm một request duy nhất trên toàn hệ thống. Ngoài ra `sync = true` có các giới hạn đối với cấu hình annotation, ví dụ phối hợp với `unless` hay nhiều cache name tùy Spring Cache.

Nếu nguồn dữ liệu đắt hoặc cần chống thundering herd ở quy mô lớn, hãy cân nhắc key TTL có jitter, cache warming, batch load, lock có giới hạn hoặc cơ chế riêng phù hợp. Mỗi giải pháp đều cần xem xét concurrency và sự cố.

### 16.1. TTL jitter

Nếu hàng nghìn key được ghi cùng lúc với TTL chính xác 10 phút, chúng có thể hết hạn gần như cùng lúc và tạo đợt cache miss lớn.

Một hướng giảm rủi ro là phân tán thời gian hết hạn theo policy có jitter. Khi dùng `RedisCacheManager`, mức độ tùy biến TTL theo entry có thể phụ thuộc phiên bản Spring Data Redis và API TTL function được hỗ trợ. Không nên tự nhận rằng một cấu hình `entryTtl(Duration.ofMinutes(10))` cố định đã có jitter.

## 17. Phân biệt Redis Cache với `RedisTemplate` và Redis Repository

Cùng là Spring Data Redis nhưng mục đích khác nhau:

| Thành phần | Khi nên dùng | Cách thao tác |
|---|---|---|
| `RedisCacheManager` + `@Cacheable` | Lưu kết quả method, giảm truy vấn nguồn dữ liệu | Annotation Spring Cache |
| `StringRedisTemplate` / `RedisTemplate` | Thao tác Redis String, Hash, List, Set, counter, TTL, Lua | `opsForValue`, `opsForHash`, `execute`... |
| Redis Repository với `@RedisHash` | Lưu/đọc entity theo abstraction repository | `save`, `findById`, `deleteById` |
| Redis scripting | Nhiều bước kiểm tra và cập nhật nguyên tử trên server | `RedisScript`, Lua/Redis Function |

Ví dụ `@Cacheable` không yêu cầu class kết quả phải có `@RedisHash`:

```java
public record ExchangeRate(String currency, double value) {}

@Cacheable(cacheNames = "exchangeRates", key = "#p0")
public ExchangeRate findRate(String currency) {
    return rateProvider.load(currency);
}
```

Manager serialize kết quả method rồi lưu vào Redis; không có nghĩa class `ExchangeRate` được lưu như một entity của Redis Repository. Ngược lại, annotation `@RedisHash` không tự kích hoạt method caching.

Khi dùng nhiều abstraction cùng một Redis deployment, nên quy định namespace, TTL, serializer và vai trò của mỗi key rõ ràng để tránh vô tình ghi đè dữ liệu.

## 18. Theo dõi cache hit/miss và Redis metrics

Cấu hình cache mới chỉ là bước đầu; cần biết cache có thực sự giảm tải cho nguồn dữ liệu hay không.

Một số chỉ số hữu ích:

| Chỉ số | Ý nghĩa |
|---|---|
| Cache hit ratio | Tỷ lệ lời gọi có thể dùng kết quả từ cache |
| Cache miss ratio | Tỷ lệ cần gọi lại method gốc/nguồn dữ liệu |
| Latency p95/p99 của lời gọi có cache | Độ trễ khi cả Redis và nguồn dữ liệu có tải |
| Redis memory usage | Sức chứa và áp lực bộ nhớ của cache |
| Redis `evicted_keys` | Số khóa Redis đã loại do policy bộ nhớ |
| Redis `expired_keys` | Số khóa được Redis xử lý do hết TTL |
| Redis CPU/network throughput | Chi phí vận hành và khả năng chạm giới hạn |
| Serializer errors | Lỗi đọc/ghi định dạng, thường bộc lộ lúc cache hit |
| Cache evictions/clear từ ứng dụng | Tần suất invalidation chủ động |

Tùy phiên bản Spring Data Redis, builder của `RedisCacheManager` có khả năng bật local cache statistics:

```java
RedisCacheManager manager =
        RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .enableStatistics()
            .build();
```

Những số liệu này được thống kê ở phạm vi cache manager/instance theo cơ chế được cung cấp; **không tự đồng nghĩa với thống kê Redis toàn cluster**. Khi có nhiều bản sao ứng dụng, cần hiểu metric thuộc instance nào và cách aggregation ở hệ thống monitoring.

Redis server có các lệnh quan sát:

```redis
INFO stats
INFO memory
TTL "catalog:v1::products::p-42"
```

`TTL` trả số giây còn lại nếu key có thời hạn, `-1` nếu key tồn tại nhưng không TTL, `-2` nếu key đã không còn. Một cache miss có thể do chưa từng ghi, hết hạn, evict chủ động hoặc eviction do thiếu bộ nhớ; chỉ nhìn `TTL = -2` không thể phân biệt nguyên nhân.

### 18.1. Kiểm tra cache hoạt động bằng dữ liệu thực tế

Một cách quan sát thủ công trong môi trường phát triển:

1. Gọi `findById("p-42")` lần đầu và ghi nhận số lần nguồn dữ liệu được truy cập.
2. Gọi lại với cùng ID, trước khi TTL hết; thông thường dữ liệu trả từ cache.
3. Xem key Redis tương ứng và TTL bằng CLI, theo đúng prefix/serializer đang dùng.
4. Gọi `changePrice("p-42", ...)` qua Spring bean để thực hiện invalidation.
5. Gọi lại `findById("p-42")` và quan sát lần đọc mới từ nguồn.
6. Chờ TTL hoặc xóa key trong môi trường thử nghiệm rồi xác nhận cache có thể nạp lại.

Bài thực hành này giúp phân biệt lỗi proxy, sai cache key, sai serializer và lỗi invalidation. Kết quả quan sát phụ thuộc cấu hình Redis/server và nguồn dữ liệu thực tế.

## 19. Xử lý lỗi Redis: cache có phải thành phần bắt buộc?

Redis là một hệ thống bên ngoài tiến trình. Dù được dùng như cache, nó vẫn có thể bị timeout hoặc mất kết nối.

Với cache thuần túy và nguồn dữ liệu đáng tin cậy, một số hệ thống chọn **fail-open**: khi không đọc cache được, vẫn gọi nguồn dữ liệu để phục vụ request. Hướng khác là **fail-closed** khi cache chứa dữ liệu cần thiết cho bất biến/giới hạn nào đó.

Spring Cache có `CacheErrorHandler` cho phép tùy biến xử lý lỗi từ thao tác get/put/evict/clear. Không nên chỉ nuốt mọi exception mà không cân nhắc:

- Đọc cache thất bại có thể dẫn đến nhiều request đồng thời đổ về database.
- Ghi cache thất bại thường cho phép request trả kết quả từ nguồn dữ liệu, nếu cache chỉ là tối ưu.
- Evict cache thất bại có thể để lại **dữ liệu cũ**, nguy hiểm hơn một cache miss thuần túy.
- Hệ thống cần metric, alert và cơ chế retry/invalidation phù hợp để tránh stale cache kéo dài.

Vì vậy, quyết định lỗi cache nên dựa trên ý nghĩa từng cache, không phải một `try/catch` bỏ qua mọi lỗi cho toàn hệ thống.

## 20. Những sai lầm cấu hình thường gặp

**Chỉ thêm `@Cacheable` mà không bật caching.** Annotation không được áp dụng theo kỳ vọng nếu thiếu hạ tầng `@EnableCaching`.

**Chỉ thêm `@EnableCaching` và nghĩ chắc chắn Redis được dùng.** Spring Cache có thể chọn provider khác nếu auto-configuration hoặc nhiều manager khiến lựa chọn thay đổi. Xác định rõ manager trong cấu hình.

**Tạo `RedisCacheManager` bean nhưng nghĩ mọi property Boot đều vẫn áp dụng tự động.** Khi tự tạo manager, hãy cấu hình trực tiếp TTL, serializer và prefix hoặc dùng customizer đúng phiên bản.

**Gọi `@Cacheable` từ `this.method()` trong cùng service.** Lời gọi nội bộ bỏ qua proxy caching mặc định.

**Không có key phù hợp cho các phương thức nhiều tham số.** Kết quả của các request khác nhau có thể trùng cache entry nếu key bỏ qua tenant, locale, page hoặc size.

**Không cấu hình TTL và invalidation.** Dữ liệu có thể lỗi thời lâu hơn nghiệp vụ cho phép.

**Dùng serializer không tương thích giữa phiên bản ứng dụng.** Cache hit có thể lỗi deserialize do type metadata hoặc schema đổi.

**Tắt key prefix trong Redis dùng chung.** Dễ đụng độ key giữa cache, repository và các dịch vụ khác.

**Xóa cả cache thường xuyên trên keyspace lớn.** Các thao tác clear có thể đắt và ảnh hưởng Redis; cân nhắc invalidation theo key hoặc chiến lược SCAN phù hợp.

**Dùng `@CachePut` mà kết quả method không phản ánh trạng thái dữ liệu mới.** Cache có thể được cập nhật bằng giá trị chưa hoàn chỉnh hoặc lỗi thời.

**Tin rằng `transactionAware()` bảo đảm đồng bộ Redis và RDBMS nguyên tử.** Nó chỉ phối hợp thời điểm một số thao tác cache với Spring transaction, không phải distributed commit.

**Tin rằng `sync = true` luôn ngăn mọi cache stampede trong toàn cluster.** Khả năng phối hợp phụ thuộc provider và topology.

**Cho rằng TTL làm key không thể bị mất sớm.** Redis eviction vẫn có thể xóa key trước hạn, tùy memory policy.

## 21. Mẫu cấu hình nên bắt đầu cho một dịch vụ đọc sản phẩm

Với một ứng dụng dùng Redis để cache kết quả đọc từ nguồn dữ liệu chính, một cấu hình thực tế có thể bắt đầu bằng:

```java
@Configuration(proxyBeanMethods = false)
@EnableCaching
public class ProductCacheConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory factory
    ) {
        RedisCacheConfiguration base =
                RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofMinutes(10))
                    .disableCachingNullValues()
                    .serializeKeysWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(new StringRedisSerializer())
                    )
                    .serializeValuesWith(
                        RedisSerializationContext.SerializationPair
                            .fromSerializer(
                                new GenericJackson2JsonRedisSerializer()
                            )
                    )
                    .computePrefixWith(
                        name -> "catalog:v1::" + name + "::"
                    );

        return RedisCacheManager.builder(factory)
                .cacheDefaults(base)
                .withInitialCacheConfigurations(Map.of(
                    "products",
                    base.entryTtl(Duration.ofMinutes(15)),

                    "productLists",
                    base.entryTtl(Duration.ofSeconds(45))
                ))
                .transactionAware()
                .build();
    }
}
```

Đoạn này rút gọn phần import; dùng các class đã giới thiệu trong phần cấu hình Java. Ứng dụng chỉ nên khai báo `@EnableCaching` một lần ở một vị trí cấu hình rõ ràng và tránh tạo hai `CacheManager` không chủ định cùng tên/kiểu.

Lớp service:

```java
@Service
public class CatalogReadService {

    private final ProductStore store;

    public CatalogReadService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(
        cacheNames = "products",
        key = "#p0",
        unless = "#result == null"
    )
    public ProductDto product(String productId) {
        return store.findById(productId);
    }

    @Cacheable(
        cacheNames = "productLists",
        key = "'p:' + #p0 + ':s:' + #p1"
    )
    public List<ProductDto> page(int page, int size) {
        return store.findPage(page, size);
    }
}
```

Cách tổ chức này tạo một ranh giới dễ hiểu:

```text
Spring Cache annotation
     |
     v
RedisCacheManager
     |
     +--> cache "products"       TTL 15 phút
     |
     +--> cache "productLists"   TTL 45 giây
     |
     v
Redis với prefix catalog:v1::<cacheName>::
```

Để hệ thống giữ dữ liệu mới, phần ghi dữ liệu nguồn phải có chiến lược evict hoặc update cache phù hợp sau khi thay đổi thành công; không trông chờ TTL là công cụ đồng bộ duy nhất khi thông tin thay đổi thường xuyên.

## 22. Khi nào nên dùng Spring Cache, khi nào thao tác Redis trực tiếp?

Dùng **Spring Cache + `RedisCacheManager`** khi một phương thức có kết quả có thể lưu theo key và được tái tạo lại khi cache miss. Đây là cách gọn để cache kết quả của `findById`, truy vấn danh sách, cấu hình đọc nhiều lần hoặc dữ liệu tổng hợp tốn chi phí.

Dùng **`RedisTemplate` hoặc Lua** khi bài toán đòi hỏi thao tác Redis đặc thù như `INCR`, `SET NX`, quản lý Redis Set/Sorted Set, điều kiện cập nhật nguyên tử, stream processing hoặc các lệnh phụ thuộc trạng thái đang có trên Redis.

Hai cách có thể cùng tồn tại trong một ứng dụng, nhưng cần phân biệt:

- `RedisCacheManager` quản lý **method result cache**.
- `RedisTemplate` thao tác trực tiếp trên cấu trúc dữ liệu Redis.
- Redis Repository quản lý **object entities** qua cơ chế mapping.
- Hạ tầng Spring Cache không biến Redis thành transaction manager của toàn bộ ứng dụng.

## 23. Kết luận

Để cấu hình Spring Cache sử dụng Redis, cần bật **`@EnableCaching`** và có một **`RedisCacheManager`** phù hợp. Spring Boot có thể tự tạo manager từ dependency và properties cho các trường hợp cơ bản; khi cần TTL theo từng cache, JSON serialization, prefix và hành vi giao dịch rõ ràng, nên cấu hình `RedisCacheManager` bằng Java.

Những nguyên tắc quan trọng nhất:

1. `@EnableCaching` kích hoạt hạ tầng annotation, còn `RedisCacheManager` quyết định Redis cache được lưu và quản lý thế nào.
2. `@Cacheable` tra cache trước khi chạy method; `@CachePut` chạy method rồi cập nhật cache; `@CacheEvict` vô hiệu dữ liệu.
3. Mọi lời gọi cần caching phải đi qua Spring proxy theo cấu hình mặc định; **self-invocation** là nguyên nhân phổ biến khiến annotation không có tác dụng.
4. TTL và key prefix cần được thiết kế theo dữ liệu và namespace thực tế; cache miss có thể xảy ra trước hạn vì eviction.
5. Serializer và schema phải nhất quán giữa các phiên bản và các thành phần đọc cùng cache.
6. `transactionAware()` giúp phối hợp một số thao tác cache với commit của Spring transaction, nhưng không tạo distributed transaction.
7. Redis Cache phù hợp với **dữ liệu có thể tái tạo**; khi cần thao tác nguyên tử, giới hạn truy cập hoặc cấu trúc Redis chuyên biệt, nên dùng API Redis phù hợp.

Khi phân biệt rõ vai trò của annotation, manager, Redis connection và vòng đời dữ liệu, ứng dụng có thể tận dụng Spring Cache để giảm độ trễ và tải lên nguồn dữ liệu mà vẫn kiểm soát được tính mới, lỗi và chi phí vận hành.
