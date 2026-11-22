# Cấu hình TTL mặc định và chính sách riêng từng cache trong Spring Data Redis

Một ứng dụng có thể dùng Redis làm nơi lưu cache cho nhiều loại dữ liệu: danh mục sản phẩm, giá bán, tồn kho, cấu hình ít thay đổi hoặc dữ liệu tìm kiếm. Dù cùng dùng Redis, các dữ liệu này không nên mặc nhiên có thời hạn giống nhau. Giá và tồn kho có thể cần được làm mới thường xuyên, trong khi dữ liệu cấu hình có thể được lưu lâu hơn.

Trong **Spring Cache** kết hợp **Spring Data Redis**, có hai cấp chính sách TTL quan trọng:

1. **TTL mặc định (default TTL):** áp dụng cho các cache không có cấu hình riêng.
2. **TTL theo tên cache (per-cache TTL):** áp dụng riêng cho từng cache, chẳng hạn `products` sống 5 phút, `inventory` sống 30 giây và `settings` sống 6 giờ.

Spring Data Redis dùng `RedisCacheManager` để quản lý các cache và `RedisCacheConfiguration` để mô tả chính sách cho chúng. Spring Boot có thể tự cấu hình một `RedisCacheManager`, đồng thời cho phép đặt TTL mặc định trong `application.yml` hoặc tùy chỉnh Java.

Điểm cần hiểu ngay từ đầu: **TTL được gắn lên từng Redis key của cache entry**. Redis không có một bộ đếm thời gian chung cho cả “vùng cache” Spring. Các entry trong cùng cache được ghi ở thời điểm khác nhau sẽ hết hạn vào những thời điểm khác nhau.

## 1. Spring Cache, RedisCacheManager và Redis key

Spring Framework cung cấp các annotation như:

- `@Cacheable`: kiểm tra cache trước khi gọi phương thức; khi miss, thực thi phương thức và đưa kết quả phù hợp vào cache.
- `@CachePut`: luôn chạy phương thức và cập nhật cache bằng kết quả.
- `@CacheEvict`: loại bỏ entry hoặc các entry của cache theo cấu hình.
- `@EnableCaching`: bật cơ chế xử lý các annotation cache.

Spring Cache là một **abstraction**: nó không tự quyết định dữ liệu được lưu ở đâu. Khi chọn Redis làm cache provider, các thành phần có thể hình dung như sau:

```text
Controller
   |
   v
Service method có @Cacheable(cacheNames = "products")
   |
   v
Spring Cache interceptor
   |
   +--> RedisCacheManager
           |
           +--> RedisCache("products")
           |       TTL = 5 phút
           |
           +--> RedisCache("inventory")
           |       TTL = 30 giây
           |
           +--> RedisCache("settings")
           |       TTL = 6 giờ
           |
           +--> Các cache không cấu hình riêng
                   TTL mặc định = 10 phút
   |
   v
Redis Cache Writer / RedisConnectionFactory
   |
   v
Redis key + value + expiration
```

Ví dụ:

```text
products::p-100       -> một cache entry của cache "products"
inventory::p-100      -> một cache entry của cache "inventory"
settings::tax-rules   -> một cache entry của cache "settings"
```

Mặc định, tiền tố Redis key thường có dạng `<cacheName>::<key>`. Do đó cùng key logic `p-100` ở hai cache khác nhau không trùng Redis key vật lý.

| Thành phần | Trách nhiệm |
|---|---|
| `@Cacheable(cacheNames = "products")` | Chọn cache theo tên cho một phương thức |
| `RedisCacheManager` | Tạo/quản lý các vùng cache và cấu hình tương ứng |
| `RedisCacheConfiguration` | TTL, tiền tố key, serializer, lưu null và các tùy chọn khác |
| `RedisCacheWriter` | Ghi/đọc/xóa key cache trên Redis |
| Redis server | Thực thi expiration trên từng key |

**Phạm vi của bài:** cache entry do Spring Cache và `RedisCacheManager` quản lý. Cơ chế này khác với TTL của một entity Redis Repository khai báo bằng `@RedisHash(timeToLive = ...)`, và khác với TTL được đặt trực tiếp khi dùng `RedisTemplate.opsForValue().set(key, value, timeout)`.

## 2. TTL mặc định của Spring Data Redis là bao nhiêu?

Khi tự dùng:

```java
RedisCacheConfiguration.defaultCacheConfig()
```

thì mặc định **không đặt thời hạn hết hạn** cho cache entry. Nếu ứng dụng không cấu hình TTL và không có thao tác khác đặt expiration, một entry có thể tồn tại cho đến khi bị xóa, thay thế, trục xuất theo chính sách bộ nhớ hoặc Redis được dọn.

Những mặc định đáng chú ý của `RedisCacheConfiguration` gồm:

| Thuộc tính | Giá trị mặc định |
|---|---|
| TTL của cache entry | Không hết hạn do TTL |
| Tiền tố key | Bật; tên cache cộng dấu `::` |
| Serializer của key | `StringRedisSerializer` |
| Serializer của value | `JdkSerializationRedisSerializer` |
| Cho phép cache null | Có |
| Hành vi time-to-idle khi đọc | Không bật |

Đây là mặc định của thư viện Spring Data Redis. Khi chạy dưới Spring Boot, các property hoặc bean cấu hình ứng dụng có thể thay đổi chúng.

**Đừng để dữ liệu có vòng đời ngắn dùng mặc định không hết hạn chỉ vì quên cấu hình.** Chọn TTL phù hợp với độ mới dữ liệu, dung lượng và yêu cầu nghiệp vụ.

## 3. Cách đơn giản nhất: TTL mặc định bằng application.yml

Giả sử ứng dụng dùng Spring Boot và Redis trên máy phát triển. Dependency Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Bật caching:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheEnableConfiguration {
}
```

Ví dụ `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
  cache:
    type: redis
    cache-names:
      - products
      - inventory
      - settings
    redis:
      time-to-live: 10m
      cache-null-values: false
      use-key-prefix: true
```

Ý nghĩa:

- `spring.cache.type: redis` yêu cầu Spring Boot sử dụng Redis Cache nếu hạ tầng tương ứng có sẵn.
- `spring.cache.cache-names` cho biết những tên cache cần khởi tạo trước; đây **không phải** nơi đặt thời hạn riêng cho từng tên.
- `spring.cache.redis.time-to-live: 10m` đặt thời hạn mặc định **10 phút** cho các entry của Redis CacheManager do Spring Boot cấu hình.
- `cache-null-values: false` giúp tránh lưu kết quả null như một entry cache.
- `use-key-prefix: true` giữ không gian tên từng cache tách biệt.

Spring Boot nhận các giá trị `Duration` như `30s`, `10m`, `1h`. Dùng đơn vị tường minh trong YAML để tránh hiểu nhầm mili giây và giây. Với cấu hình này, **products**, **inventory** và **settings** đều có TTL 10 phút cho đến khi được chỉ định chính sách riêng.

Lưu ý: nếu ứng dụng khai báo `CacheManager` bean thủ công, cấu hình tự động của Spring Boot cho CacheManager có thể không còn được sử dụng theo cách ở trên. Khi đó, phải đặt TTL trong chính bean do ứng dụng quản lý.

### 3.1. Ví dụ service dùng default TTL

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductCatalogService {

    private final ProductRepository repository;

    public ProductCatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#productId")
    public ProductView getProduct(String productId) {
        return repository.findViewById(productId);
    }
}
```

`ProductRepository` và `ProductView` là các kiểu nghiệp vụ minh họa; chúng không phải lớp có sẵn trong Spring Data Redis.

Giả sử gọi `getProduct("p-100")`:

1. Lần đầu gọi, cache chưa có key `products::p-100` nên phương thức chạy và lấy dữ liệu từ repository.
2. Spring Cache đưa kết quả vào Redis với TTL 10 phút theo cấu hình mặc định.
3. Lần gọi tiếp theo trong khoảng TTL có thể lấy giá trị trực tiếp từ Redis, bỏ qua việc gọi repository.
4. Khi key đã hết hạn, lần gọi sau là cache miss và phương thức lại chạy để nạp dữ liệu mới.

**Không nên coi `@Cacheable` là cơ chế bảo đảm không bao giờ đọc dữ liệu cũ.** Trong khoảng TTL, cache vẫn có thể trả một giá trị lỗi thời nếu dữ liệu nguồn đã đổi nhưng không có hành động invalidation.

## 4. Cấu hình chính sách riêng từng cache

Một ứng dụng bán hàng có thể dùng các thời hạn:

| Cache | Loại dữ liệu | TTL đề xuất minh họa |
|---|---|---|
| `products` | Tên, hình ảnh, mô tả sản phẩm | 5 phút |
| `inventory` | Số lượng tồn kho hiển thị | 30 giây |
| `settings` | Cấu hình ít thay đổi | 6 giờ |
| Các cache còn lại | Chính sách chung | 10 phút |

Những khoảng thời gian trên là ví dụ thực hành, không phải khuyến nghị mặc định cho mọi hệ thống. Đặc biệt, **tồn kho chính xác để quyết định có bán được hay không** không nên chỉ dựa vào giá trị cache 30 giây; cần kiểm tra ở nguồn dữ liệu có cơ chế kiểm soát đồng thời phù hợp.

Có hai cách cấu hình per-cache thông dụng.

### 4.1. Cách A — Dùng RedisCacheManagerBuilderCustomizer của Spring Boot

Khi đang để Spring Boot tự tạo `RedisCacheManager`, có thể thêm một bean `RedisCacheManagerBuilderCustomizer` để gắn cấu hình riêng cho các tên cache.

Ví dụ sau dùng package của **Spring Boot 3.x**:

```java
import java.time.Duration;
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration(proxyBeanMethods = false)
public class PerCacheTtlConfiguration {

    @Bean
    public RedisCacheManagerBuilderCustomizer perCacheTtlCustomizer() {
        return builder -> builder
                .withCacheConfiguration(
                        "products",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofMinutes(5))
                                .disableCachingNullValues()
                )
                .withCacheConfiguration(
                        "inventory",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofSeconds(30))
                                .disableCachingNullValues()
                )
                .withCacheConfiguration(
                        "settings",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofHours(6))
                                .disableCachingNullValues()
                );
    }
}
```

Giữ YAML trong mục 3 với `time-to-live: 10m`. Trong cấu hình trên:

- Cache `products` dùng thời hạn **5 phút**.
- Cache `inventory` dùng **30 giây**.
- Cache `settings` dùng **6 giờ**.
- Một cache khác được Redis CacheManager tạo theo default configuration sẽ dùng **10 phút**, miễn là CacheManager có cho phép tạo cache động.

**Chú ý về việc kế thừa các tùy chọn khác:** mỗi lần dùng `RedisCacheConfiguration.defaultCacheConfig()` trong customizer là tạo một configuration của thư viện, không tự sao chép tất cả tùy chọn đã được Spring Boot đặt cho cấu hình mặc định như serializer, key prefix tùy biến hoặc null policy. Trong ví dụ, `disableCachingNullValues()` được khai báo lại để các cache riêng cũng không lưu null. Nếu hệ thống đã tùy chỉnh nhiều thuộc tính, nên xây từ **cùng một cấu hình nền** thay vì tạo những cấu hình riêng không nhất quán.

Ở **Spring Boot 4.x**, package của một số lớp auto-configuration, trong đó có `RedisCacheManagerBuilderCustomizer`, đã thay đổi. Khi copy ví dụ, phải chọn import đúng với Spring Boot BOM thực tế, không dùng lẫn package 3.x và 4.x.

### 4.2. Cách B — Tự khai báo RedisCacheManager bean

Nếu muốn kiểm soát rõ toàn bộ default và per-cache, có thể khai báo `RedisCacheManager` bean. Đây là lựa chọn phù hợp khi chính sách TTL cần được đọc và quản lý cùng serializer, tiền tố, null policy và chiến lược clear.

```java
import java.time.Duration;
import java.util.Map;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class RedisCacheConfigurationBean {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10))
                        .disableCachingNullValues();

        Map<String, RedisCacheConfiguration> cachePolicies = Map.of(
                "products",
                defaults.entryTtl(Duration.ofMinutes(5)),
                "inventory",
                defaults.entryTtl(Duration.ofSeconds(30)),
                "settings",
                defaults.entryTtl(Duration.ofHours(6))
        );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(cachePolicies)
                .build();
    }
}
```

Các phương thức cấu hình của `RedisCacheConfiguration` trả về **đối tượng configuration mới**; gọi `defaults.entryTtl(...)` không sửa `defaults` hiện có. Vì thế có thể tạo một cấu hình nền dùng chung rồi tạo các biến thể chỉ khác TTL.

Ý nghĩa của builder:

```text
RedisCacheManager
  |
  +-- cacheDefaults(defaults)
  |     +-- entryTtl(10 phút)
  |     +-- disableCachingNullValues()
  |     +-- key prefix mặc định
  |
  +-- withInitialCacheConfigurations(cachePolicies)
        |
        +-- products  -> entryTtl(5 phút)
        +-- inventory -> entryTtl(30 giây)
        +-- settings  -> entryTtl(6 giờ)
```

Với cách B, **chính bean Java** nắm quyền cấu hình CacheManager. Đừng tiếp tục giả định rằng `spring.cache.redis.time-to-live: 10m` sẽ tự ghi đè TTL trong `cacheDefaults(defaults)`. Muốn các giá trị đọc từ YAML, hãy tự bind chúng qua `@ConfigurationProperties` hay `@Value` và xây `RedisCacheManager` từ cấu hình đó.

### 4.3. Nên chọn cách nào?

| Nhu cầu | Cách phù hợp |
|---|---|
Chỉ muốn một TTL mặc định | YAML `spring.cache.redis.time-to-live` |
Muốn đổi TTL cho vài cache và vẫn dùng Boot auto-configuration | `RedisCacheManagerBuilderCustomizer` |
Muốn cùng một cấu hình nền, per-cache policies, serializer và writer tùy chỉnh | `RedisCacheManager` bean do ứng dụng quản lý |
Muốn TTL khác nhau giữa từng **entry của cùng cache** | `RedisCacheWriter.TtlFunction`, nếu phiên bản hỗ trợ |

Chỉ nên dùng một chiến lược cấu hình chính để tránh nhầm nơi nào quyết định TTL cuối cùng.

## 5. @Cacheable chọn cache; nó không tự định nghĩa TTL

Ví dụ một service truy cập hai vùng cache khác nhau:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogQueryService {

    private final CatalogGateway gateway;

    public CatalogQueryService(CatalogGateway gateway) {
        this.gateway = gateway;
    }

    @Cacheable(cacheNames = "products", key = "#id")
    public ProductView findProduct(String id) {
        return gateway.loadProduct(id);
    }

    @Cacheable(cacheNames = "inventory", key = "#id")
    public InventoryView findInventory(String id) {
        return gateway.loadInventory(id);
    }

    @Cacheable(cacheNames = "settings", key = "#name")
    public SettingView findSetting(String name) {
        return gateway.loadSetting(name);
    }
}
```

`CatalogGateway`, `ProductView`, `InventoryView` và `SettingView` là các lớp do ứng dụng tự định nghĩa.

Ba annotation không cần khai báo thời hạn trực tiếp. Chúng chỉ định **tên cache**; CacheManager tìm đúng `RedisCacheConfiguration` theo tên và áp dụng TTL:

```text
findProduct("p-100")
  --> @Cacheable("products")
  --> products::p-100
  --> TTL 5 phút

findInventory("p-100")
  --> @Cacheable("inventory")
  --> inventory::p-100
  --> TTL 30 giây

findSetting("tax-rules")
  --> @Cacheable("settings")
  --> settings::tax-rules
  --> TTL 6 giờ
```

Không tồn tại thuộc tính `ttl` tiêu chuẩn trên `@Cacheable` của Spring Framework để khai báo `@Cacheable(ttl = "30s")`. Nếu muốn thời hạn khác nhau cho mỗi method, có thể:

- Cho các method dùng những **tên cache khác nhau** với policies riêng.
- Dùng `TtlFunction` tính TTL theo key/value trong cùng cache, khi phiên bản hỗ trợ.
- Dùng một cơ chế cache chuyên biệt khác nếu chính sách yêu cầu logic phức tạp.

Chỉ đổi key SpEL, ví dụ `key = "#id"` hay `key = "#tenantId + ':' + #id"`, **không đổi TTL** nếu vẫn là cùng một vùng cache với một cấu hình cố định.

### 5.1. Tự gọi trong cùng đối tượng và @EnableCaching

Spring Cache thường dựa trên proxy/AOP để chặn lời gọi method. Nếu trong cùng class, method A gọi trực tiếp `this.findProduct(...)`, lời gọi đó thường bỏ qua cache proxy. Vì thế một thử nghiệm có thể cho cảm giác TTL không hoạt động khi thực ra method chưa hề được đi qua cơ chế cache.

Khi kiểm tra:

1. Đảm bảo có `@EnableCaching` hoặc cơ chế bật tương đương.
2. Gọi method qua Spring bean từ đối tượng khác.
3. Xác nhận `CacheManager` đang dùng thực sự là `RedisCacheManager`.
4. Quan sát Redis key và `TTL` sau cache miss.

## 6. TTL được đặt hoặc làm mới khi nào?

Với Spring Data Redis Cache, **time-to-live** thông thường được đặt khi cache entry được **tạo mới hoặc ghi đè**. Đọc một cache entry có sẵn bằng `@Cacheable` không tự gia hạn TTL theo chính sách TTL tiêu chuẩn.

Ví dụ cache `products` có TTL 5 phút:

```text
12:00:00  findProduct("p-100")  cache miss
          -> chạy method, ghi products::p-100
          -> TTL xấp xỉ 300 giây

12:02:00  findProduct("p-100")  cache hit
          -> lấy giá trị cache
          -> TTL còn xấp xỉ 180 giây

12:04:59  findProduct("p-100")  cache hit
          -> TTL còn khoảng 1 giây

12:05:01  findProduct("p-100")  entry đã hết hạn
          -> cache miss, method chạy lại
          -> ghi entry mới, TTL trở lại xấp xỉ 300 giây
```

Tính toán minh họa bỏ qua sai lệch thời gian xử lý và lịch hoạt động thực tế của Redis.

### 6.1. @CachePut thường đặt lại TTL

```java
import org.springframework.cache.annotation.CachePut;

@CachePut(cacheNames = "products", key = "#result.id")
public ProductView refreshProduct(String id) {
    return gateway.loadProduct(id);
}
```

`@CachePut` luôn thực thi method rồi đưa kết quả vào cache. Khi ghi lại entry, TTL được đặt theo cấu hình cache. Với cache `products`, thời gian sống sau lần ghi mới là khoảng 5 phút.

### 6.2. @CacheEvict xóa entry, không “giảm TTL”

```java
import org.springframework.cache.annotation.CacheEvict;

@CacheEvict(cacheNames = "products", key = "#id")
public void invalidateProduct(String id) {
    // Có thể trống nếu nghiệp vụ invalidation nằm ở method này.
}
```

`@CacheEvict` loại bỏ key tương ứng. Sau đó, gọi `findProduct(id)` sẽ cần nạp lại dữ liệu và tạo key với TTL mới. Không có chuyện `@CacheEvict` chỉ rút ngắn thời hạn của entry cũ.

### 6.3. Một method có nhiều cacheNames cần thận trọng

`@Cacheable(cacheNames = {"products", "inventory"})` có thể làm Spring kiểm tra nhiều cache rồi sử dụng kết quả theo semantics của abstraction. Hai cache có TTL và kiểu dữ liệu khác nhau có thể dẫn tới hành vi khó giải thích. Hãy dùng nhiều cache name cho cùng một loại dữ liệu khi có chủ đích; nếu các cache biểu diễn những loại dữ liệu khác nhau, nên tách method.

## 7. Kiểm tra cấu hình TTL bằng Redis CLI

Ví dụ sau giả sử key cache do Spring tạo theo prefix mặc định:

```text
products::p-100
inventory::p-100
settings::tax-rules
```

Sau lần gọi method làm cache miss:

```redis
EXISTS products::p-100
# (integer) 1

TTL products::p-100
# (integer) 298

TTL inventory::p-100
# (integer) 28

TTL settings::tax-rules
# (integer) 21595
```

Các con số chỉ minh họa thời gian đã trôi qua kể từ lần ghi. Nếu cần độ chính xác theo mili giây, dùng:

```redis
PTTL products::p-100
```

Ý nghĩa kết quả `TTL`/`PTTL`:

| Giá trị | Ý nghĩa |
|---|---|
| Số không âm | Thời gian còn lại, đơn vị giây/mi-li giây |
| `-1` | Key tồn tại nhưng không được đặt expiration |
| `-2` | Key không tồn tại hoặc đã hết hạn |

Khi kiểm tra bằng Redis CLI, hãy chắc chắn kết nối tới **cùng Redis server, logical database và namespace** mà ứng dụng đang sử dụng. Nếu đã tùy chỉnh key prefix hay key conversion, tên key thực tế có thể khác ví dụ.

### 7.1. Kiểm tra default TTL đối với cache không có override

Giả sử một cache `recommendations` được tạo động và dùng cấu hình mặc định 10 phút:

```java
@Cacheable(cacheNames = "recommendations", key = "#userId")
public RecommendationView getRecommendations(String userId) {
    return recommendationGateway.load(userId);
}
```

Sau lần gọi đầu:

```redis
TTL recommendations::user-42
# xấp xỉ 600
```

Nếu CacheManager được cấu hình để **không cho tạo cache chưa khai báo**, tên `recommendations` phải được thêm vào danh sách cấu hình trước; nếu không có cache đó, Spring Cache có thể báo lỗi khi resolve cache thay vì tự tạo. Đây là lựa chọn quản trị cache names, độc lập với độ dài TTL.

### 7.2. Nếu TTL trả -1 sau khi cache được ghi

Các hướng cần kiểm tra:

- RedisCacheManager thực tế có phải CacheManager của ứng dụng không?
- TTL mặc định đã được cấu hình trong đúng nhánh YAML chưa?
- Có bean `RedisCacheManager` tự tạo đang bỏ qua property của Spring Boot không?
- Cache đó có cấu hình riêng `entryTtl(Duration.ZERO)` hoặc không thiết lập TTL không?
- Có thao tác `PERSIST`, `SET` không kèm expiration hoặc writer khác đã thay đổi key sau lần ghi cache không?
- Key đang kiểm tra có đúng tiền tố, database và serializer không?

Không suy ra “Redis không hỗ trợ TTL” chỉ từ `-1`: kết quả này có nghĩa key không có expiration **tại thời điểm kiểm tra**.

## 8. Tên cache, key prefix và chính sách TTL

Hai cache có thể sử dụng cùng một key logic:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView findProduct(String id) { ... }

@Cacheable(cacheNames = "inventory", key = "#id")
public InventoryView findInventory(String id) { ... }
```

Với key prefix mặc định:

```text
products::p-100  -> TTL 5 phút
inventory::p-100 -> TTL 30 giây
```

Hai Redis key vật lý khác nhau nên không xung đột dữ liệu hoặc expiration.

Nếu tắt key prefix bằng `disableKeyPrefix()` hoặc `spring.cache.redis.use-key-prefix: false`, cả hai entry có thể cùng tranh tên key `p-100`. Ngoài nguy cơ **giá trị bị ghi đè bởi cache khác**, việc clear cache có thể làm ảnh hưởng dữ liệu khác trên Redis vì thiếu namespace để giới hạn key.

Do đó:

- Giữ prefix theo tên cache trừ khi có thiết kế namespace rất rõ ràng.
- Nếu dùng custom prefix, bảo đảm các cache vẫn tách biệt và có quy tắc ổn định.
- Không thay tiền tố cache trên dữ liệu đang lưu mà không tính cách xử lý các key cũ.

### 8.1. Ví dụ cấu hình prefix riêng

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .computePrefixWith(cacheName ->
                        "shop:v1:" + cacheName + "::");
```

Sau đó tên vật lý có dạng `shop:v1:products::p-100`. TTL vẫn do cấu hình `entryTtl` quy định; prefix chỉ thay đổi **tên key**, không thay đổi thời hạn của entry.

## 9. Cấu hình Serializer và cache null

TTL thường là bước đầu tiên, nhưng cache policy còn cần tính tới cách dữ liệu được mã hóa và hành vi khi method trả `null`.

### 9.1. Cache null có ý nghĩa gì?

Nếu một method có `@Cacheable` nhưng trả `null` khi không tìm thấy dữ liệu, Spring Data Redis mặc định có thể lưu một biểu diễn đặc biệt cho giá trị null. Lần gọi tiếp theo có thể nhận cache hit cho “không tìm thấy” thay vì truy vấn nguồn dữ liệu.

Đây là **negative caching**, có thể hữu ích để giảm truy vấn lặp lại với ID không tồn tại. Nhưng nó cũng có nguy cơ:

1. Người dùng truy cập sản phẩm chưa tồn tại, cache lưu kết quả null.
2. Sản phẩm được tạo thật trong hệ thống.
3. Trong khoảng TTL, cache vẫn trả null đến khi entry hết hạn hoặc được invalidation.

Nếu không muốn lưu null:

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .disableCachingNullValues();
```

Có thể cấu hình khác nhau theo cache: một cache danh mục không lưu null, trong khi cache kết quả tra cứu tốn kém lại có chiến lược negative caching với TTL rất ngắn. Cần xác định rõ chính sách trước khi đưa vào production.

**Lưu ý:** khi `disableCachingNullValues()`, thao tác ghi null trực tiếp qua `Cache.put(key, null)` không phải một lệnh xóa key an toàn; nó có thể báo lỗi. Với annotation, hãy cân nhắc thêm `unless = "#result == null"` trên `@Cacheable` để chủ động tránh ghi null từ method.

```java
@Cacheable(
        cacheNames = "products",
        key = "#id",
        unless = "#result == null")
public ProductView findProduct(String id) {
    return gateway.loadProduct(id);
}
```

### 9.2. Serializer phải tương thích giữa các phiên bản ứng dụng

`RedisCacheConfiguration.defaultCacheConfig()` dùng `StringRedisSerializer` cho key và `JdkSerializationRedisSerializer` cho value. Với ứng dụng Java nhiều instance, việc thay class, đổi `serialVersionUID` hoặc deploy đa phiên bản có thể tác động khả năng đọc giá trị đã cache bằng Java serialization.

Có thể cấu hình serializer khác:

```java
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;

RedisCacheConfiguration jsonCache =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(java.time.Duration.ofMinutes(10))
                .serializeValuesWith(
                        RedisSerializationContext.SerializationPair.fromSerializer(
                                new GenericJackson2JsonRedisSerializer()
                        )
                );
```

Đây là ví dụ cho một lựa chọn serializer, không phải lời khuyên chuyển mọi cache sang cùng một bộ mã hóa. Serializer cần phù hợp với version thư viện, kiểu dữ liệu và chính sách an toàn của ứng dụng. Hãy cân nhắc giới hạn các kiểu có thể deserialize, tương thích payload cũ và kế hoạch xóa/migrate cache khi đổi định dạng.

Nếu mỗi cache dùng serializer khác nhau, điều đó cũng nên được quản lý qua `RedisCacheConfiguration` riêng như TTL; đừng vô tình phá vỡ serializer chung khi tạo per-cache configuration từ `defaultCacheConfig()`.

## 10. TTL theo cache khác TTL động theo từng entry

Cho đến đây, mỗi vùng cache có một thời hạn cố định:

```text
products    -> mọi entry 5 phút
inventory   -> mọi entry 30 giây
settings    -> mọi entry 6 giờ
```

Nhưng đôi khi **các entry trong cùng cache** cần TTL khác nhau. Ví dụ bản tin thay đổi nhanh sống 20 giây, bản tin tĩnh sống 10 phút, dù đều thuộc cache `news`.

Từ **Spring Data Redis 3.2**, `RedisCacheWriter.TtlFunction` cho phép tính thời hạn dựa trên key hoặc value của từng entry:

```java
import java.time.Duration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheWriter;

RedisCacheWriter.TtlFunction newsTtl = (key, value) -> {
    if (value instanceof NewsView news && news.isBreaking()) {
        return Duration.ofSeconds(20);
    }
    return Duration.ofMinutes(10);
};

RedisCacheConfiguration newsConfig =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(newsTtl);
```

`NewsView` là model nghiệp vụ minh họa có phương thức `isBreaking()`. Có thể đưa `newsConfig` vào `withCacheConfiguration("news", newsConfig)`.

Phân biệt:

| Cấp chính sách | Ví dụ | Công cụ |
|---|---|---|
| Default của CacheManager | Mọi cache chưa override: 10 phút | `cacheDefaults(...)` hoặc Spring Boot property |
| Theo tên cache | `products`: 5 phút; `inventory`: 30 giây | `withCacheConfiguration(...)` |
| Theo từng entry | Tin nóng 20 giây; tin thường 10 phút | `entryTtl(TtlFunction)` từ Spring Data Redis 3.2 |

TtlFunction không tự tạo một cơ chế scheduler chạy trong JVM. Nó cung cấp `Duration` tại thời điểm ghi cache entry; Redis vẫn tự quản lý thời điểm hết hạn của Redis key.

**Chú ý:** nếu mọi cache entry của một vùng phải có cùng TTL, không cần tạo TtlFunction. `entryTtl(Duration.ofMinutes(5))` đơn giản hơn và dễ vận hành hơn.

## 11. TTL và TTI: đọc cache có gia hạn không?

**TTL (Time To Live)** theo cơ chế thông thường của Redis Cache được đặt khi ghi. Đọc một entry không gia hạn.

**TTI (Time To Idle)** là chính sách entry hết hạn sau một khoảng thời gian **không được truy cập**. Redis server không có một metadata TTI độc lập, nhưng Spring Data Redis 3.2+ có thể mô phỏng TTI bằng lệnh Redis `GETEX`: vừa đọc giá trị vừa đặt lại expiration.

Ví dụ:

```java
RedisCacheConfiguration frequentlyReadConfig =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(5))
                .enableTimeToIdle();
```

Khi bật TTI:

```text
12:00  ghi entry       -> còn 5 phút
12:03  đọc bằng Cache  -> TTL được đặt lại khoảng 5 phút
12:07  đọc bằng Cache  -> TTL được đặt lại khoảng 5 phút
12:12  không đọc thêm  -> entry có thể đã hết hạn
```

Các điều kiện quan trọng:

- `enableTimeToIdle()` cần Redis **6.2+** vì dựa trên `GETEX`.
- Không thể kỳ vọng một lệnh đọc thô `GET` hoặc một đường truy cập khác không dùng `GETEX` tự làm mới TTL.
- TTI chỉ hoạt động nhất quán khi mọi đường đọc/ghi liên quan tuân theo chính sách. Trộn thao tác Spring Cache với RedisTemplate thô trên cùng key có thể làm thời hạn không như mong muốn.
- TTI có thể giữ những key “nóng” tồn tại rất lâu nếu chúng liên tục được đọc. Cần cân nhắc liệu dữ liệu có phải hết hạn tuyệt đối sau một mốc nghiệp vụ hay không.

Nếu chỉ cần chính sách riêng **theo cache**, không có yêu cầu gia hạn khi đọc, nên giữ TTL tiêu chuẩn; tránh bật TTI chỉ vì muốn tăng cache hit.

## 12. Cập nhật dữ liệu nguồn và invalidation

TTL giới hạn thời gian tồn tại tối đa từ lần ghi cache gần nhất; nó **không biết lúc nào dữ liệu nguồn đã thay đổi**.

Ví dụ người dùng sửa mô tả sản phẩm nhưng `products` đang có TTL 5 phút:

```text
12:00  Cache products::p-100 = "Màu xanh"
12:01  Database đổi thành "Màu đỏ"
12:02  @Cacheable vẫn trả "Màu xanh" nếu chưa evict/update
12:05  Entry hết hạn
12:06  Cache miss -> lấy "Màu đỏ" và ghi entry mới
```

Để giảm khoảng stale, có thể:

1. **Cache-aside với invalidation:** sau khi thay dữ liệu nguồn thành công, xóa entry liên quan bằng `@CacheEvict` hoặc Cache API.
2. **Write-through ở tầng ứng dụng:** dùng `@CachePut` để cập nhật entry sau khi thay dữ liệu nguồn.
3. **TTL ngắn hơn:** phù hợp với dữ liệu ít quan trọng về tính nhất quán tức thời; đánh đổi bằng tăng số lần cache miss.
4. **Versioned keys:** dùng version hoặc revision trong key khi cần cách ly những thế hệ dữ liệu.

Ví dụ invalidation:

```java
import org.springframework.cache.annotation.CacheEvict;

@CacheEvict(cacheNames = "products", key = "#id")
public void updateProductDescription(String id, String description) {
    productRepository.updateDescription(id, description);
}
```

Nếu cập nhật database và xóa Redis cache thuộc **hai hệ thống khác nhau**, nên cân nhắc thứ tự thao tác, retry và lỗi một phần. Một `@Transactional` với database quan hệ không tự biến thao tác Redis thành một atomic commit phân tán. Với nghiệp vụ yêu cầu độ chính xác cao, có thể cần outbox/event xử lý invalidation có retry và idempotency.

### 12.1. TTL không ngăn cache stampede

Khi một key rất phổ biến hết hạn, nhiều request đồng thời có thể cùng gặp cache miss và gọi dữ liệu nguồn. Đây là **cache stampede**.

Có thể giảm tác động bằng:

- Chọn TTL phù hợp và tránh hàng loạt entry hết hạn cùng thời điểm.
- Với Spring Cache, xem xét `@Cacheable(sync = true)` nếu Cache implementation hỗ trợ cơ chế đồng bộ lời gọi nạp dữ liệu. Không mặc định nó tạo distributed lock đầy đủ giữa mọi instance.
- Cân nhắc TTL động có jitter nếu dữ liệu và yêu cầu cho phép, hoặc chiến lược làm mới trước khi hết hạn.
- Bảo vệ nguồn dữ liệu bằng giới hạn concurrency và timeout.

TTL riêng cho từng cache giúp giảm tải bằng cách chọn thời hạn khác nhau cho từng loại dữ liệu; nó không tự giải quyết mọi vấn đề đồng thời ở thời điểm expiration.

## 13. Vận hành Redis Cache khi có nhiều tên cache

### 13.1. Theo dõi keyspace và tránh key không có TTL

Một hệ thống có thể sử dụng nhiều cơ chế cùng lúc:

```text
products::p-100    -> Spring Cache, TTL 5 phút
inventory::p-100   -> Spring Cache, TTL 30 giây
session:abc        -> RedisTemplate, TTL do ứng dụng đặt riêng
orders:o-100       -> Redis Repository, TTL có thể đặt bằng @RedisHash
```

Những key trên có thể cùng sống trong một Redis instance, nhưng **chính sách TTL của RedisCacheManager chỉ áp dụng cho cache entry do CacheManager quản lý**. Cấu hình mặc định `spring.cache.redis.time-to-live` không tự gán TTL cho `session:abc` hoặc Redis Repository entity.

Để vận hành tốt:

- Đặt namespace rõ ràng cho từng loại key.
- Cấu hình TTL tại nơi sở hữu cách ghi dữ liệu.
- Quan sát tỷ lệ key không có expiration nếu dữ liệu lẽ ra phải ngắn hạn.
- Không để một job dọn dẹp dùng pattern quá rộng tác động cả key nghiệp vụ ngoài cache.

### 13.2. Xóa cả vùng cache có thể tốn kém

Khi gọi:

```java
cacheManager.getCache("products").clear();
```

Spring Data Redis thường xóa các key thuộc prefix của cache. Mặc định, chiến lược xóa có thể dùng `KEYS` và `DEL`; `KEYS` quét rộng có thể gây vấn đề hiệu năng trên Redis lớn.

Spring Data Redis có lựa chọn `SCAN` qua `BatchStrategies.scan(...)` khi xây `RedisCacheWriter`:

```java
import org.springframework.data.redis.cache.BatchStrategies;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;

RedisCacheWriter writer =
        RedisCacheWriter.nonLockingRedisCacheWriter(
                connectionFactory,
                BatchStrategies.scan(1000));

RedisCacheManager manager =
        RedisCacheManager.builder(writer)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(cachePolicies)
                .build();
```

Đoạn mã này minh họa **phần thay đổi writer** trong cấu hình bean của mục 4, không phải một bean thứ hai cần đăng ký song song. Theo tài liệu, `SCAN` strategy được hỗ trợ đầy đủ với Lettuce, còn Jedis có giới hạn với Redis Cluster. Cần xác nhận đúng driver và topology trước khi dùng.

TTL không thay thế `clear()`: entry hết hạn theo từng key, còn `clear()` yêu cầu xóa cả vùng cache phù hợp với tên cache.

### 13.3. Số liệu và kiểm chứng policy

Có thể kiểm tra:

```redis
TTL products::p-100
TTL inventory::p-100
TTL settings::tax-rules
INFO stats
INFO memory
```

Ngoài Redis CLI, theo dõi cache hit/miss, tần suất nạp lại dữ liệu, latency của nguồn, dung lượng Redis và số key theo namespace. `RedisCacheManagerBuilder.enableStatistics()` cho phép thống kê cache ở phạm vi local instance của Spring Data Redis; đừng nhầm số liệu local với thống kê toàn cluster ứng dụng.

Thay đổi cấu hình TTL trong bản triển khai mới **không tự sửa expiration của mọi key cũ đã tồn tại**. TTL mới sẽ được áp dụng khi những key đó được ghi/cập nhật theo cấu hình mới. Nếu cần chuyển đổi chính sách ngay lập tức cho toàn bộ cache, hãy thiết kế cách xóa hoặc di chuyển key cũ có kiểm soát.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
|---|---|---|
| Cache `inventory` vẫn có TTL 10 phút | Chưa cấu hình per-cache hoặc tên cache không khớp | Kiểm tra `withCacheConfiguration("inventory", ...)` và `@Cacheable(cacheNames=...)` |
| `spring.cache.redis.time-to-live` dường như không có tác dụng | Ứng dụng tự tạo CacheManager bean | Đặt TTL trong bean hoặc dùng customizer với auto-config |
| Chỉ một số cache lưu null | Per-cache config không kế thừa default null policy | Tạo configuration từ cùng cấu hình nền |
| Đọc nhiều lần nhưng TTL vẫn giảm | Đang dùng TTL, không phải TTI | Đây là hành vi chuẩn; chỉ bật `enableTimeToIdle()` nếu cần |
| Bật TTI rồi Redis báo lỗi lệnh | Server không hỗ trợ `GETEX` | Redis cần phiên bản 6.2+ |
| Entry không hết hạn (`TTL = -1`) | Chưa đặt expiration hoặc key bị ghi lại không có TTL | Xác định đường ghi và configuration thực tế |
| TTL đúng nhưng cache vẫn trả dữ liệu cũ | Dữ liệu nguồn đã đổi trước khi cache hết hạn | Dùng invalidation/refresh bên cạnh TTL |
| Hai cache đè dữ liệu của nhau | Tắt key prefix hoặc custom prefix gây trùng | Giữ prefix tách theo cache |
| Cache miss liên tục | TTL quá ngắn, key khác giữa lần gọi hoặc cache proxy bị bỏ qua | Kiểm tra key, thời hạn và Spring AOP |
| Vừa deploy đổi TTL nhưng key cũ còn thời hạn dài | Cấu hình mới chưa được áp vào key đã lưu | Có kế hoạch clear/refresh hoặc đợi key cũ hết hạn |
| Cache clear gây tải Redis tăng cao | Batch strategy dùng `KEYS` trên keyspace lớn | Cân nhắc `SCAN` theo driver/topology, giới hạn batch |
| Giá trị cache không đọc được sau deploy | Đổi serializer/class mà key cũ vẫn tồn tại | Xác định compatibility hoặc xóa/migrate cache có kiểm soát |

## 15. Bài thực hành hoàn chỉnh

**Mục tiêu:** cấu hình default TTL 10 phút và ba cache có chính sách riêng:

```text
products    5 phút
inventory   30 giây
settings    6 giờ
other       10 phút (default)
```

Các bước:

1. Thêm `spring-boot-starter-cache` và `spring-boot-starter-data-redis`.
2. Bật `@EnableCaching` và cấu hình Redis connection.
3. Trong `application.yml` đặt `spring.cache.type: redis` và `spring.cache.redis.time-to-live: 10m`.
4. Thêm `RedisCacheManagerBuilderCustomizer` định nghĩa TTL riêng cho ba cache, hoặc thay bằng một `RedisCacheManager` bean có default + per-cache map.
5. Tạo method `@Cacheable(cacheNames = "products")` và `@Cacheable(cacheNames = "inventory")` nhận cùng `id`.
6. Gọi mỗi method một lần, sau đó chạy Redis CLI `TTL products::<id>` và `TTL inventory::<id>`. Quan sát khoảng 300 và 30 giây.
7. Gọi lại method trong lúc cache hit; thời gian còn lại tiếp tục giảm nếu chỉ bật TTL.
8. Dùng `@CachePut` hoặc cập nhật entry để quan sát TTL đặt lại; dùng `@CacheEvict` để quan sát key biến mất.
9. Thử một cache chưa có override như `recommendations` để xác nhận default TTL.
10. Đổi TTL của một cache trong mã cấu hình, deploy lên môi trường thử nghiệm và so sánh TTL của key cũ với entry được tạo mới.

**Câu hỏi tự kiểm tra:**

- Nếu `@Cacheable(cacheNames = "inventory")` gọi dữ liệu nguồn mỗi 5 giây nhưng TTL là 30 giây, cache hit có tự gia hạn key không?
- Nếu một cache dùng default TTL 10 phút và một cache khác override 30 giây, hai cache có thể dùng cùng key logic `p-100` hay không?
- Khi dùng `RedisCacheManagerBuilderCustomizer` với `defaultCacheConfig()` riêng, vì sao phải quan tâm serializer và cấu hình lưu null?
- Nếu business yêu cầu dữ liệu tồn kho luôn chính xác khi đặt hàng, TTL 30 giây đã đủ chưa?
- Nếu muốn thời hạn theo từng entry trong cùng cache, nên dùng cơ chế nào ở Spring Data Redis 3.2+?

## 16. Kết luận

Trong Spring Data Redis, **`RedisCacheManager` chọn một `RedisCacheConfiguration` theo tên cache**, còn Redis server quản lý expiration của từng key. TTL mặc định có thể khai báo gọn bằng `spring.cache.redis.time-to-live` khi dùng auto-configuration của Spring Boot. Những cache cần chính sách riêng nên được cấu hình bằng `RedisCacheManagerBuilderCustomizer` hoặc `RedisCacheManager` bean với `cacheDefaults(...)` và `withInitialCacheConfigurations(...)`.

TTL tiêu chuẩn thường **được đặt lại khi ghi**, còn cache hit chỉ đọc dữ liệu và không gia hạn. Nếu cần TTL khác nhau cho từng entry, Spring Data Redis 3.2+ có `RedisCacheWriter.TtlFunction`; nếu cần kéo dài hạn theo lần đọc, `enableTimeToIdle()` dựa trên Redis `GETEX`. Những tính năng này phục vụ nhu cầu khác nhau, không nên thay thế tùy tiện cho một chính sách per-cache đơn giản.

Khi đưa vào vận hành, giữ key prefix để tách các vùng cache, đồng bộ serializer và null policy, xử lý invalidation khi dữ liệu nguồn thay đổi và kiểm chứng TTL bằng Redis CLI. **TTL là công cụ giới hạn độ tuổi cache, không phải lời bảo đảm dữ liệu luôn mới hoặc luôn nhất quán với nguồn.**

## Tài liệu tham khảo

- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, `RedisCacheConfiguration`, chính sách TTL, TTI, serializer, key prefix và cache clearing.
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html): `spring.cache.redis.time-to-live`, `spring.cache.cache-names` và `RedisCacheManagerBuilderCustomizer`.
- [Spring Boot 3.4 — Caching](https://docs.spring.io/spring-boot/3.4/reference/io/caching.html): ví dụ Spring Boot 3.x với import của `RedisCacheManagerBuilderCustomizer`.
- [Spring Data Redis API — RedisCacheConfiguration](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/cache/RedisCacheConfiguration.html): `entryTtl(Duration)`, `entryTtl(TtlFunction)`, `disableCachingNullValues()` và `enableTimeToIdle()`.
- [Spring Framework — Caching](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, key SpEL và các giới hạn của proxy.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): cơ chế expiration trên Redis key.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): đọc thời hạn còn lại và các giá trị đặc biệt `-1`/`-2`.
- [Redis — GETEX](https://redis.io/docs/latest/commands/getex/): đọc và cập nhật expiration của key trong cùng một lệnh.
