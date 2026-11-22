# Dùng @Cacheable, @CachePut và @CacheEvict

Spring Cache cung cấp một lớp trừu tượng để ứng dụng Java sử dụng cache thông qua annotation. Trong ứng dụng **Spring Data Redis**, ta có thể dùng Redis làm nơi lưu cache dùng chung cho nhiều instance, còn các annotation `@Cacheable`, `@CachePut` và `@CacheEvict` quyết định **khi nào đọc, ghi hoặc loại bỏ** kết quả được lưu.

Ba annotation có tên gần nhau nhưng hành vi rất khác:

- **`@Cacheable`:** trước khi chạy phương thức, tra cache theo key; nếu có giá trị hợp lệ, trả ngay giá trị đó và bỏ qua phần thân phương thức; nếu miss, gọi phương thức rồi có thể lưu kết quả.
- **`@CachePut`:** luôn gọi phương thức; sau đó dùng kết quả trả về để cập nhật entry trong cache theo key.
- **`@CacheEvict`:** xóa một entry hoặc nhiều entry theo quy tắc; thường dùng sau khi dữ liệu gốc được thay đổi hoặc xóa.

Phân biệt chính xác ba hành vi này giúp triển khai mô hình **cache-aside** cho thao tác đọc, đồng bộ cache sau ghi và tránh việc cache trả dữ liệu cũ.

## 1. Spring Cache đứng ở đâu trong kiến trúc Redis?

`@Cacheable`, `@CachePut` và `@CacheEvict` thuộc gói `org.springframework.cache.annotation`, không phải các annotation dành riêng cho Redis. Spring dùng `CacheManager` và `Cache` để thực hiện thao tác cache. Khi chọn `RedisCacheManager`, dữ liệu cache được lưu tại Redis.

```text
HTTP Controller
       |
       v
Spring Service (được proxy bởi Spring Cache)
       |
       +-- @Cacheable: kiểm tra Redis trước khi vào method
       |
       +-- Cache HIT ----------------------> Trả kết quả
       |
       +-- Cache MISS --> Method --> Database/API nguồn
                               |
                               v
                         Lưu vào Redis
                               |
                               v
                           Trả kết quả
```

Trong mô hình này, các tầng có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| `@Cacheable` | Chọn kết quả có thể đọc lại từ cache theo key |
| `@CachePut` | Ghi kết quả phương thức vào cache sau khi phương thức chạy |
| `@CacheEvict` | Loại bỏ dữ liệu cache theo key hoặc toàn bộ cache name |
| `CacheManager` | Quản lý các cache theo tên |
| `RedisCacheManager` | Triển khai Spring Cache trên Redis |
| Database/API nguồn | Cung cấp và xác nhận dữ liệu nghiệp vụ gốc |

**Redis Cache là bản sao phục vụ truy vấn**, trừ khi kiến trúc đã thiết kế Redis làm nguồn dữ liệu chính. Đối với đa số ứng dụng dùng database làm nguồn sự thật, cache có thể được tái tạo từ database khi bị xóa hoặc hết hạn.

### Phân biệt Spring Cache với Redis Repository

`@RedisHash`, `@Id` và `@Indexed` phục vụ mapping entity thông qua Spring Data Redis Repository. Còn `@Cacheable` dùng Spring Cache abstraction để lưu **giá trị trả về của phương thức**, theo key do cache resolver/key generator xác định.

Ví dụ, `@RedisHash("products")` và `@Cacheable(cacheNames = "productById")` **không tự chia sẻ cùng một bộ dữ liệu hay cùng serializer**. Cùng kết nối Redis không có nghĩa cache entry sẽ được đọc như một entity Redis Repository.

## 2. Chuẩn bị Spring Boot để sử dụng Redis Cache

Một ứng dụng Spring Boot sử dụng Spring Cache với Redis thường cần các dependency tương ứng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Ví dụ cấu hình kết nối Redis trong `application.yml`:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Thực tế production cần cấu hình kết nối, xác thực, TLS và timeout thích hợp theo Redis deployment. Không hardcode mật khẩu trong ví dụ hoặc mã nguồn.

### 2.1. Bật cơ chế cache

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class SpringCacheConfiguration {
}
```

`@EnableCaching` bật cơ chế phát hiện các annotation Spring Cache và cài đặt các interceptor tương ứng trong Spring context. Khi dùng kiểu cấu hình proxy phổ biến, chỉ những lời gọi đi **qua Spring-managed proxy** mới được áp dụng cache advice.

Nếu không bật caching hoặc bean không được Spring quản lý, annotation trong mã Java không tự làm phát sinh lệnh Redis.

### 2.2. Cấu hình RedisCacheManager và TTL cho từng cache

```java
import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCacheConfigurationExample {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .disableCachingNullValues()
                        .entryTtl(Duration.ofMinutes(2));

        Map<String, RedisCacheConfiguration> perCache = Map.of(
                "productById",
                defaults.entryTtl(Duration.ofMinutes(10)),

                "productAvailability",
                defaults.entryTtl(Duration.ofSeconds(15))
        );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(perCache)
                .transactionAware()
                .build();
    }
}
```

Trong ví dụ:

- `productById` được cấu hình TTL 10 phút.
- `productAvailability` có TTL 15 giây vì cần dữ liệu mới hơn.
- Các cache khác nếu được tạo theo cấu hình mặc định có TTL 2 phút.
- `disableCachingNullValues()` bỏ việc lưu giá trị `null` vào Redis cho cấu hình này.
- `transactionAware()` giúp các thao tác cache `put` và `evict` có thể được hoãn đến giai đoạn transaction Spring commit thành công khi có transaction đang được đồng bộ; điều này không biến Redis và database thành một distributed transaction.

**TTL là chính sách của cache**, còn các annotation quyết định thời điểm tương tác với cache. Các con số trên chỉ minh họa; chọn TTL dựa trên độ mới dữ liệu, chi phí truy vấn nguồn và độ rủi ro khi hiển thị bản cũ.

Chú ý serializer: cấu hình mặc định của `RedisCacheConfiguration` sử dụng serialization của Redis Cache theo các quy tắc mặc định, có thể khác định dạng JSON mà API sử dụng. Với giá trị cần chia sẻ giữa các phiên bản hoặc giữa nhiều ngôn ngữ, phải chọn serializer và hợp đồng schema rõ ràng; không mặc định cache Redis chứa JSON chỉ vì controller trả JSON.

## 3. @Cacheable: chỉ thực thi phương thức khi cần tải dữ liệu

Cú pháp cơ bản:

```java
@Cacheable(cacheNames = "productById", key = "#p0")
public ProductView findById(String productId) {
    return productStore.findById(productId);
}
```

Ở đây:

- `cacheNames = "productById"`: tên cache mà `CacheManager` quản lý.
- `key = "#p0"`: biểu thức SpEL lấy đối số đầu tiên của phương thức.
- `ProductView`: loại kết quả được lưu vào cache.
- `productStore.findById(...)`: đường đọc nguồn khi cache miss.

### 3.1. Luồng thực thi

```text
Gọi findById("p-17")
           |
           v
   Tạo key theo #p0
           |
           v
   Redis cache productById
           |
       +---+---+
       |       |
      HIT     MISS
       |       |
       v       v
    Trả value  Chạy findById
                  |
                  v
             Đọc database
                  |
                  v
           Lưu value vào cache
                  |
                  v
              Trả kết quả
```

Lần đầu gọi `findById("p-17")`, cache chưa có giá trị nên phương thức được thực thi. Những lần tiếp theo, nếu entry vẫn hợp lệ trong Redis, Spring có thể trả bản đã cache mà không gọi database. Khi entry hết TTL hoặc bị evict, lần đọc sau trở thành cache miss và chạy phương thức lại.

### 3.2. Cache key và cache name

Với cấu hình key prefix thường dùng của `RedisCacheManager`, khóa Redis có thể có dạng:

```text
productById::p-17
```

Cần phân biệt:

- `productById` là **tên cache** ở Spring.
- `p-17` là **key logic** bên trong cache, lấy từ `#p0`.
- Chuỗi khóa Redis vật lý có thể được thêm prefix hoặc chuyển đổi bởi cấu hình cache manager và key serializer.

Không nên viết ứng dụng khác thao tác trực tiếp vào key nội bộ nếu chưa chốt quy ước tên và serializer.

Nếu cùng phương thức còn phụ thuộc tenant, locale, currency hoặc quyền truy cập, key phải phản ánh những tham số có thể làm **kết quả khác nhau**. Ví dụ `findById(tenantId, productId)` dùng một mình `#p1` có thể khiến hai tenant trùng product ID dùng chung cache sai.

```java
@Cacheable(
        cacheNames = "productByTenant",
        key = "#p0 + ':' + #p1")
public ProductView findById(String tenantId, String productId) {
    return productStore.findById(tenantId, productId);
}
```

Một thiết kế an toàn còn cần xác thực quyền ở tầng nghiệp vụ. Không xem cache key là cơ chế phân quyền.

### 3.3. Không lưu kết quả null với unless

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        unless = "#result == null")
public ProductView findById(String id) {
    return productStore.findById(id);
}
```

`unless` được đánh giá **sau khi phương thức đã chạy**, nên có thể dùng `#result`. Với ví dụ trên, nếu database không có sản phẩm và trả `null`, kết quả không được cache.

Việc chọn không cache `null` phù hợp khi cần phát hiện sản phẩm mới xuất hiện ngay ở lần truy vấn kế tiếp. Nhưng với những khóa liên tục không tồn tại, caching kết quả “không có dữ liệu” trong một TTL ngắn có thể giảm tải database. Cần thống nhất với chính sách cấu hình `disableCachingNullValues()` của cache manager.

### 3.4. @Cacheable không phù hợp cho thao tác ghi bắt buộc chạy

Ví dụ sai:

```java
@Cacheable(cacheNames = "productById", key = "#p0")
public ProductView update(String id, UpdateCommand command) {
    return productStore.update(id, command);
}
```

Khi cache hit, Spring có thể **không thực thi `update(...)`**, nghĩa là database không được cập nhật. Các phương thức có tác dụng phụ bắt buộc phải chạy không nên dùng `@Cacheable` để bao ngoài.

## 4. @CachePut: luôn chạy phương thức rồi cập nhật cache

`@CachePut` áp dụng khi phương thức phải thực thi, nhưng **kết quả mới của nó cũng nên được ghi vào cache**.

```java
@CachePut(cacheNames = "productById", key = "#p0")
public ProductView update(String id, UpdateCommand command) {
    return productStore.update(id, command);
}
```

Luồng:

```text
Gọi update("p-17", command)
              |
              v
     Chạy method update
              |
              v
      Ghi dữ liệu nguồn
              |
              v
     Nhận ProductView mới
              |
              v
     Cache PUT productById
              |
              v
          Trả kết quả
```

Nếu database cập nhật thành công và phương thức trả `ProductView` mới, Spring Cache sẽ đưa kết quả vào cache theo key `p-17`. Lần gọi `@Cacheable` kế tiếp với cùng cache name và key có thể nhận ngay bản mới.

`@CachePut` **không đọc cache để quyết định bỏ qua method**. Nó phù hợp với lệnh cập nhật có kết quả đúng cùng loại với giá trị mà phương thức đọc cache mong đợi.

### 4.1. Cùng cache name, key và value type

Ví dụ hai phương thức:

```java
@Cacheable(cacheNames = "productById", key = "#p0")
public ProductView findById(String id) { ... }

@CachePut(cacheNames = "productById", key = "#p0")
public ProductView update(String id, UpdateCommand command) { ... }
```

Khi cùng `productById` và `#p0`, cả đọc và ghi cache xác định cùng entry. Nếu method update dùng `key = "#p1"`, đối số thứ hai là `UpdateCommand`, nên nó có thể ghi sang một khóa khác hoàn toàn. Cache của `findById` vẫn giữ bản cũ.

Điều kiện cần đồng nhất gồm **cache name, cách sinh key, kiểu giá trị, phiên bản serialization và chính sách tenant**. Sai một yếu tố cũng có thể dẫn tới cache không đồng bộ hoặc lỗi chuyển đổi kiểu.

### 4.2. @CachePut và dữ liệu trả về

`@CachePut` lưu **kết quả phương thức**, không tự gọi lại phương thức đọc để lấy bản mới. Nếu method update chỉ trả `boolean` nhưng `@Cacheable` đọc `ProductView`, việc dùng chung cache name/key sẽ ghi sai kiểu dữ liệu và làm lần đọc sau thất bại.

Trường hợp method update trả `void`, thường nên dùng `@CacheEvict` để xóa bản cũ, rồi để lần đọc kế tiếp lấy dữ liệu mới từ nguồn. Không trông chờ `@CachePut` tự tìm entity mới khi method không trả entity.

### 4.3. condition và unless

`@CachePut` cũng hỗ trợ điều kiện:

```java
@CachePut(
        cacheNames = "productById",
        key = "#p0",
        condition = "#p0 != null",
        unless = "#result == null")
public ProductView update(String id, UpdateCommand command) {
    return productStore.update(id, command);
}
```

- `condition` quyết định có áp dụng thao tác cache dựa trên ngữ cảnh trước khi chạy method; nó không ngăn chính method cập nhật.
- `unless` có thể ngăn việc lưu kết quả sau method, ví dụ kết quả `null`.
- Đừng dùng điều kiện cache để thay thế validation hoặc authorization của nghiệp vụ.

Nếu update thành công nhưng `unless` chặn put, entry cũ có thể vẫn tồn tại. Khi điều kiện có thể chặn việc cập nhật cache, phải đánh giá khả năng cần **evict bản cũ** thay vì chỉ không put.

## 5. @CacheEvict: xóa cache khi dữ liệu gốc thay đổi

Có nhiều thao tác ghi chỉ trả trạng thái thành công hoặc `void`. Khi đó, **xóa cache theo key** thường đơn giản và ít rủi ro hơn việc tính ra một giá trị mới để put.

```java
@CacheEvict(cacheNames = "productById", key = "#p0")
public void delete(String id) {
    productStore.delete(id);
}
```

Hành vi mặc định của `@CacheEvict` là **evict sau khi phương thức thực thi thành công**. Nếu `delete(...)` ném exception, cache eviction thông thường không được thực hiện vì method không hoàn thành.

Ví dụ cập nhật giá mà không trả đầy đủ `ProductView`:

```java
@CacheEvict(cacheNames = "productById", key = "#p0")
public void changePrice(String id, BigDecimal price) {
    productStore.changePrice(id, price);
}
```

Lần đọc tiếp theo sẽ gặp cache miss và lấy sản phẩm với giá mới từ database.

### 5.1. Evict một key

```java
@CacheEvict(cacheNames = "productById", key = "#p0")
public void removeProduct(String id) {
    productStore.delete(id);
}
```

Chỉ entry có key phù hợp được loại bỏ trong cache `productById`. Đây thường là lựa chọn phù hợp khi biết chính xác ID đã thay đổi.

### 5.2. Evict toàn bộ cache

```java
@CacheEvict(cacheNames = "productById", allEntries = true)
public void rebuildProductCatalog() {
    productStore.rebuildCatalog();
}
```

`allEntries = true` yêu cầu loại bỏ **mọi entry** thuộc cache name này. Nó có thể cần thiết sau một đợt thay đổi quy mô lớn, nhưng dễ tạo nhiều cache miss đồng thời và tăng tải lên database.

Không kết hợp `allEntries = true` và `key = "..."` trong cùng một khai báo `@CacheEvict`: hai lựa chọn này loại trừ nhau về mặt ý nghĩa.

### 5.3. Evict trước khi chạy phương thức

```java
@CacheEvict(
        cacheNames = "productById",
        key = "#p0",
        beforeInvocation = true)
public void invalidateThenRun(String id) {
    productStore.recompute(id);
}
```

Khi `beforeInvocation = true`, cache entry bị xóa **trước khi** phương thức chạy, kể cả khi phương thức sau đó thất bại. Cách này đôi khi phù hợp với một thao tác cần vô hiệu hóa ngay từ đầu, nhưng có rủi ro: request khác có thể miss và nạp lại **dữ liệu cũ trước khi update hoàn tất**.

Đối với cập nhật database, mặc định `beforeInvocation = false` thường thuận lợi hơn vì chỉ evict sau thành công. Tuy vậy, bản thân hành vi “evict sau method” chưa chắc đã đồng nghĩa “evict sau database commit” khi đang có transaction; cần xem phần đồng bộ transaction bên dưới.

## 6. Ví dụ service hoàn chỉnh: đọc, cập nhật và xóa sản phẩm

Ta dùng cùng cache `productById` để minh họa cả ba annotation. Giả sử database là nguồn dữ liệu gốc, còn Redis chỉ là cache đọc.

### 6.1. Kiểu dữ liệu và cổng truy cập nguồn

```java
import java.math.BigDecimal;

public record ProductView(
        String id,
        String name,
        BigDecimal price) {
}
```

```java
import java.math.BigDecimal;

public interface ProductStore {

    // Trả null nếu không có sản phẩm.
    ProductView findById(String id);

    // Cập nhật nguồn và trả bản ProductView mới.
    ProductView update(String id, String name, BigDecimal price);

    // Xóa dữ liệu ở nguồn.
    void delete(String id);
}
```

`ProductStore` là giao diện minh họa; triển khai thực tế có thể dùng Spring Data JPA, JDBC hoặc một API nguồn. Điều cốt lõi là các phương thức có hợp đồng rõ ràng và trả đúng bản dữ liệu vừa lưu.

### 6.2. Dịch vụ truy vấn dùng @Cacheable

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductStore store;

    public ProductQueryService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(
            cacheNames = "productById",
            key = "#p0",
            unless = "#result == null")
    public ProductView findById(String id) {
        return store.findById(id);
    }
}
```

Nếu `productById::p-17` chưa có trong Redis, method sẽ gọi `store.findById("p-17")`. Nếu Redis đã có entry hợp lệ, Spring Cache trả giá trị đó mà không gọi store.

### 6.3. Dịch vụ ghi dùng @CachePut và @CacheEvict

```java
import java.math.BigDecimal;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    private final ProductStore store;

    public ProductCommandService(ProductStore store) {
        this.store = store;
    }

    @Transactional
    @CachePut(cacheNames = "productById", key = "#p0")
    public ProductView update(
            String id, String name, BigDecimal price) {
        return store.update(id, name, price);
    }

    @Transactional
    @CacheEvict(cacheNames = "productById", key = "#p0")
    public void delete(String id) {
        store.delete(id);
    }
}
```

Trong ví dụ:

1. `ProductQueryService.findById("p-17")` lấy từ Redis nếu có, nếu không thì từ nguồn.
2. `ProductCommandService.update("p-17", ...)` luôn ghi database, sau đó lưu `ProductView` mới vào cache.
3. `ProductCommandService.delete("p-17")` luôn xóa dữ liệu ở nguồn, rồi loại bỏ entry cache.
4. Các phương thức được gọi từ bean khác, nên trong cấu hình proxy thông thường, cache interceptor có cơ hội chạy.
5. `@Transactional` có hiệu lực nếu ứng dụng có transaction manager phù hợp với `ProductStore`. Cấu hình Redis Cache transaction-aware ở mục 2 giúp hoãn put/evict khi transaction Spring tương ứng đang active.

Không nên tạo cache riêng có tên khác nhau cho hai đường đọc/ghi cùng một loại giá trị nếu không có lý do; phương thức update phải nhắm đúng key mà phương thức query đã tạo.

### 6.4. Diễn tiến dữ liệu từng bước

Giả sử lúc đầu database lưu:

```text
Product p-17:
  name = "Keyboard"
  price = 500000
```

| Bước | Hành động | Database | Redis cache |
|---|---|---|---|
| 1 | `findById("p-17")` | Được đọc | Miss, sau đó lưu giá 500000 |
| 2 | `findById("p-17")` lần nữa | Không cần đọc lại | Hit, trả giá 500000 |
| 3 | `update("p-17", ..., 450000)` | Cập nhật giá 450000 | `@CachePut` ghi bản mới |
| 4 | `findById("p-17")` | Không cần đọc lại | Hit, trả giá 450000 |
| 5 | `delete("p-17")` | Xóa sản phẩm | `@CacheEvict` xóa entry |
| 6 | `findById("p-17")` | Tìm không thấy | Miss; trả null và không cache null |

Ví dụ giả định các thao tác thành công và không có truy cập cạnh tranh. Trong hệ thống thực, request đồng thời có thể tạo những tình huống cache bị ghi lại bởi một lần đọc cũ.

## 7. Key expression: phần quyết định các annotation có phối hợp đúng không

Nếu cùng một sản phẩm có nhiều cách gọi khác nhau, ví dụ:

```java
findById("p-17")
update("p-17", ...)
delete("p-17")
```

thì tất cả phải hướng tới cùng key `p-17` của cache `productById`.

### 7.1. SpEL trong annotation

Spring Cache hỗ trợ SpEL:

| Biểu thức | Ý nghĩa |
|---|---|
| `#p0` hoặc `#a0` | Tham số đầu tiên |
| `#p1` | Tham số thứ hai |
| `#id` | Tham số được đặt tên `id`, khi metadata tên tham số có thể truy cập |
| `#result` | Giá trị trả về, dùng được trong những ngữ cảnh sau khi method chạy như `unless` hoặc key của `@CachePut` |
| `#root.methodName` | Tên phương thức đang được cache |
| `#root.targetClass` | Class của target trong ngữ cảnh expression |

Dùng `#p0` giúp ví dụ không phụ thuộc việc ứng dụng đã biên dịch giữ tên tham số hay chưa. Với các key phức tạp, một `KeyGenerator` dùng chung có thể phù hợp hơn việc lặp nhiều SpEL string có khả năng sai khác.

### 7.2. Key không đầy đủ có thể lẫn dữ liệu

Ví dụ một API lấy sản phẩm theo tenant và đơn vị tiền:

```java
@Cacheable(
        cacheNames = "priceByTenantAndCurrency",
        key = "#p0 + ':' + #p1 + ':' + #p2")
public BigDecimal getPrice(
        String tenantId, String productId, String currency) {
    return store.loadPrice(tenantId, productId, currency);
}
```

Nếu chỉ cache theo product ID, kết quả bằng USD của tenant A có thể bị dùng cho request lấy VND của tenant B. Tên cache và key phải phản ánh **tất cả đầu vào ảnh hưởng tới kết quả**.

Với giá trị được phép chia sẻ trên nhiều người dùng, phải xác định phạm vi chính xác. Với dữ liệu phụ thuộc người dùng/quyền truy cập, không để cache bypass quy trình kiểm soát quyền.

### 7.3. Key thay đổi theo phiên bản

Khi cấu trúc `ProductView` thay đổi không tương thích, các instance cũ/mới có thể cùng sử dụng Redis. Nếu cache name và serializer giống nhau nhưng kiểu value khác, chúng có thể không deserialize được dữ liệu của nhau.

Có thể sử dụng namespace cache có phiên bản, chẳng hạn `productByIdV2`, hoặc phối hợp triển khai để tránh chia sẻ value không tương thích. Cần tính tới thời gian tồn tại của dữ liệu cũ và cách xóa cache khi đổi phiên bản.

## 8. condition và unless: khi nào kiểm tra điều kiện?

Hai thuộc tính giúp kiểm soát áp dụng cache nhưng ở những thời điểm khác nhau.

### 8.1. condition

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        condition = "#p0 != null")
public ProductView findById(String id) {
    return store.findById(id);
}
```

`condition` được kiểm tra **trước việc sử dụng cache** theo ngữ cảnh method. Nếu điều kiện false, caching cho lời gọi đó bị bỏ qua và method chạy bình thường.

### 8.2. unless

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        unless = "#result == null")
public ProductView findById(String id) {
    return store.findById(id);
}
```

`unless` kiểm tra sau khi method chạy và có kết quả. Nếu false, kết quả được phép cache. Nếu true, kết quả không được đưa vào cache.

**Không dùng `#result` trong `condition` với kỳ vọng method đã chạy**, vì `condition` cần được đánh giá trước khi có kết quả. Với `@CacheEvict(beforeInvocation = true)` cũng chưa có giá trị kết quả sau phương thức.

### 8.3. Điều kiện cache không thay thế quy tắc nghiệp vụ

Ví dụ `condition = "#p0 != null"` chỉ quyết định có cache hay không; method vẫn cần từ chối ID không hợp lệ nếu đó là quy tắc nghiệp vụ. Cũng không dùng `unless` để quyết định có được ghi database hay không: nó chỉ tham gia chính sách cache.

## 9. Xóa nhiều cache sau một lần thay đổi

Một hành động có thể ảnh hưởng nhiều cache khác nhau. Ví dụ khi cập nhật giá sản phẩm, hệ thống có:

- Cache chi tiết `productById`.
- Cache danh sách theo danh mục `productListByCategory`.
- Cache giá theo currency `priceByTenantAndCurrency`.

Chỉ `@CachePut` lên `productById` chưa đủ để cập nhật các cache tổng hợp hoặc danh sách có chứa sản phẩm đó.

Spring cho phép dùng `@Caching` để khai báo nhiều eviction:

```java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Caching;
import org.springframework.transaction.annotation.Transactional;

@Transactional
@Caching(evict = {
        @CacheEvict(cacheNames = "productById", key = "#p0"),
        @CacheEvict(
                cacheNames = "productListByCategory",
                allEntries = true),
        @CacheEvict(
                cacheNames = "priceByTenantAndCurrency",
                allEntries = true)
})
public void changePrice(String productId, BigDecimal newPrice) {
    store.changePrice(productId, newPrice);
}
```

Cách trên đúng về mặt ý tưởng nhưng **xóa toàn bộ hai cache danh sách/giá** có thể tạo nhiều cache miss và dồn tải lên database. Khi có thể xác định key liên quan, nên evict chọn lọc. Nếu không, cần thiết kế index ngược, phiên bản cache key, hoặc event invalidation chuyên biệt cho dữ liệu tổng hợp.

Đặc biệt với một danh sách được cache theo điều kiện lọc/sort/page, một sản phẩm thay đổi có thể ảnh hưởng nhiều kết quả. Không thể chỉ đoán một key danh sách là đủ để đảm bảo đúng dữ liệu.

## 10. TTL và cơ chế xóa chủ động phối hợp thế nào?

TTL giới hạn khoảng thời gian cache entry còn hợp lệ khi không có invalidation. `@CacheEvict` loại bỏ cache dựa trên sự kiện thay đổi nguồn.

Ví dụ:

```text
10:00  findById(p-17)   -> cache giá 500000, TTL 10 phút
10:02  update(p-17)     -> database giá 450000
                          @CachePut ghi cache giá 450000
10:03  findById(p-17)   -> cache trả giá 450000
10:12  Cache hết hạn    -> lần đọc sau lấy lại database
```

Một thiết kế thường phối hợp:

1. **TTL** như hàng rào độ mới khi invalidation bị bỏ lỡ hoặc có dữ liệu ít thay đổi.
2. **`@CachePut`** khi mutation có thể trả chính xác value mới cần cache.
3. **`@CacheEvict`** khi mutation không trả value mới phù hợp hoặc có nhiều đường đọc phụ thuộc.
4. **Event invalidation** nếu nhiều service khác nhau có thể thay đổi dữ liệu nguồn.
5. **Giám sát** để phát hiện dữ liệu cũ, cache miss đồng loạt và lỗi kết nối Redis.

TTL **không tự biết database đã được sửa**. Nếu một ứng dụng khác cập nhật database mà không phát invalidation, cache có thể tiếp tục phục vụ bản cũ đến khi hết hạn.

### Mất khóa trước TTL

Redis có thể evict khóa do áp lực bộ nhớ trước TTL, tùy cấu hình `maxmemory-policy`. Một cache miss không nhất thiết là dữ liệu đã hết hạn đúng lịch.

Ngược lại, Spring Cache có thể tự lưu lại entry khi có miss, do đó TTL của entry mới thường được tính từ lần ghi cache gần nhất.

## 11. Transaction và thời điểm cập nhật Redis Cache

Khi method ghi database có `@Transactional`, người đọc dễ nghĩ:

```java
@Transactional
@CachePut(cacheNames = "productById", key = "#p0")
public ProductView update(...) { ... }
```

chắc chắn cập nhật Redis **sau khi database đã commit**. Nhưng thứ tự Spring AOP advice và cơ chế cache manager quyết định thời điểm thao tác cache thực sự diễn ra.

Nếu một cache put chạy trước database commit rồi database rollback, Redis có thể đã chứa dữ liệu mà database không xác nhận. Nếu cache eviction xảy ra trước commit, một request khác có thể miss và nạp bản cũ.

### Transaction-aware cache manager

Trong cấu hình `RedisCacheManager` ở đầu bài có:

```java
return RedisCacheManager.builder(connectionFactory)
        .cacheDefaults(defaults)
        .withInitialCacheConfigurations(perCache)
        .transactionAware()
        .build();
```

Khi có transaction Spring tương ứng và cơ chế đồng bộ transaction đang active, cache put/evict thông thường có thể được hoãn tới **sau khi commit thành công**. Điều này giảm trường hợp cache được cập nhật khi database rollback.

Nhưng cần hiểu giới hạn:

- Không có distributed transaction nguyên tử giữa database và Redis.
- Database có thể commit thành công nhưng Redis thao tác thất bại ở bước sau commit.
- Lệnh eviction `beforeInvocation = true` có hành vi đặc biệt và không nên kỳ vọng được hoãn giống eviction mặc định.
- Một transaction chưa đăng ký synchronization hoặc một lời gọi không đi qua Spring proxy có thể không được bảo vệ như kỳ vọng.
- Nhiều writer đồng thời vẫn có thể tạo race khi đọc miss và nạp cache.

Với dữ liệu quan trọng, dùng cơ chế event/outbox và đối soát khi cần đảm bảo invalidation được lặp lại sau sự cố. Với cache thông thường, TTL phù hợp cộng invalidation có kiểm soát là một lựa chọn thực dụng.

## 12. Vấn đề stale write khi đọc và cập nhật xảy ra đồng thời

Dù dùng `@Cacheable` và `@CacheEvict` đúng cách, một race vẫn có thể xảy ra:

```text
Request A (GET)                     Request B (UPDATE)
       |                                    |
Cache MISS                                 |
       |                                    |
Đọc DB nhận bản cũ                        |
       |                              Ghi DB bản mới
       |                              Evict cache
       |                                    |
Ghi bản cũ vào Redis                       |
       |                                    |
       +----------- Cache đang cũ ----------+
```

Request A bắt đầu đọc trước khi request B cập nhật, nhưng ghi kết quả cache **sau khi B đã evict**. Cache có thể giữ bản cũ cho tới lần invalidation hoặc TTL tiếp theo.

Đây là lý do caching annotation không tự giải quyết mọi bài toán nhất quán cạnh tranh. Các lựa chọn tùy mức nghiêm ngặt:

- TTL ngắn nếu độ cũ ngắn hạn được chấp nhận.
- Gắn version hoặc timestamp dữ liệu, chỉ thay thế cache khi phiên bản không cũ hơn.
- Dùng invalidation theo event sau commit và lặp/đối soát khi cần.
- Điều phối các thao tác ghi/đọc lại ở nơi thật sự cần bảo đảm mạnh.
- Không dùng cache làm quyết định cuối cùng cho số dư, quyền truy cập, thanh toán hay tồn kho nếu không có cơ chế nhất quán tương ứng.

Cũng cần lưu ý nếu nhiều ứng dụng cập nhật cùng dữ liệu nguồn, mỗi ứng dụng phải thực hiện invalidation đúng key hoặc gửi sự kiện chung. Annotation ở một service không tự giám sát những ghi phát sinh ở service khác.

## 13. Spring AOP proxy và lỗi self-invocation

Một trong những lỗi phổ biến nhất là gọi phương thức cache từ **bên trong chính bean** chứa phương thức đó:

```java
@Service
public class ProductService {

    @Cacheable(cacheNames = "productById", key = "#p0")
    public ProductView findById(String id) {
        return store.findById(id);
    }

    public ProductView loadForExport(String id) {
        // Lời gọi nội bộ qua this:
        return findById(id);
    }
}
```

Trong chế độ proxy Spring Cache thông thường, `loadForExport(...)` gọi trực tiếp `findById(...)` trên cùng object. Lời gọi không đi qua proxy nên **`@Cacheable` có thể bị bỏ qua**: database bị truy vấn mỗi lần dù annotation tồn tại.

Cách rõ ràng là tách lời gọi vào một bean khác và inject qua constructor:

```java
@Service
public class ExportService {

    private final ProductQueryService productQueries;

    public ExportService(ProductQueryService productQueries) {
        this.productQueries = productQueries;
    }

    public ProductView loadForExport(String id) {
        // Lời gọi qua Spring-managed bean/proxy.
        return productQueries.findById(id);
    }
}
```

Tương tự, một method trong cùng class gọi method có `@CacheEvict` có thể bỏ qua eviction. Đây là lỗi nguy hiểm vì database đã đổi nhưng cache vẫn giữ bản cũ. Khi review code, cần biết chính xác điểm gọi đi qua proxy hay chỉ là `this.method()`.

Ngoài self-invocation, các phương thức không được proxy intercept do visibility, final class/method hoặc kiểu proxy/cấu hình không phù hợp cũng có thể làm annotation không được áp dụng.

## 14. @Cacheable(sync = true) và stampede

Khi một key rất nóng hết hạn, nhiều request có thể cùng miss và thực hiện cùng truy vấn database:

```text
100 request cùng gọi findById("p-hot")
                     |
                     v
                 Cache MISS
                     |
          +----------+----------+
          |                     |
       Request A             Request B ... Z
          |                     |
       Đọc database         Đọc database
          |                     |
          +----------+----------+
                     |
                  Ghi cache
```

Spring Cache hỗ trợ:

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        sync = true)
public ProductView findById(String id) {
    return store.findById(id);
}
```

`sync = true` yêu cầu cache provider phối hợp việc tải một key để tránh nhiều luồng cùng tính giá trị, **khi provider hỗ trợ chức năng đồng bộ này**. Không mặc định nó đảm bảo distributed lock với đúng một lần truy vấn nguồn trên tất cả instance. Mức bảo đảm phụ thuộc `Cache` implementation, Redis cache writer và cấu hình.

Một số hạn chế của `sync = true`: chỉ dùng với một cache name, không dùng `unless`, và không kết hợp thao tác cache khác vào cùng method trong cách sử dụng thông thường của Spring Cache.

Nếu có hàng trăm instance cùng miss một khóa hoặc mất Redis đồng loạt, vẫn cần xem xét biện pháp bảo vệ database: giới hạn concurrency, cache warmup, TTL jitter, stale-while-revalidate có kiểm soát hoặc lock phân tán có hợp đồng rõ.

## 15. Lưu null, exception và kết quả lỗi

Với Spring Cache, kết quả method và exception có hành vi khác nhau:

| Trường hợp | `@Cacheable` | `@CachePut` | `@CacheEvict` |
|---|---|---|---|
| Phương thức trả kết quả bình thường | Có thể lưu sau miss | Lưu kết quả trả về | Evict sau thành công theo mặc định |
| Method ném exception | Không lưu kết quả lỗi như value bình thường | Không có kết quả mới để put | Mặc định không evict nếu method không hoàn thành |
| Method trả `null` | Tùy `unless` và cấu hình cache | Tùy `unless` và cấu hình cache | Không phụ thuộc value return để evict |
| Redis không sẵn sàng | Cache lookup/write có thể lỗi | Cache write có thể lỗi | Cache eviction có thể lỗi |

Nếu không muốn cache kết quả `null`, có thể kết hợp `unless = "#result == null"` với `disableCachingNullValues()`.

Đối với response object có field `success=false` hoặc status lỗi nhưng **method vẫn trả object bình thường**, Spring Cache có thể cache object đó nếu không có điều kiện loại trừ. Ví dụ API client trả DTO chứa mã lỗi như một giá trị sẽ bị xem là kết quả để cache nếu annotation không biết phân biệt. Cần xác định rõ kiểu trả về và chính sách `unless` theo nghiệp vụ.

Nếu Redis lỗi, quyết định trả lỗi lên caller hay fallback về nguồn phải được thiết kế có chủ đích bằng `CacheErrorHandler` hoặc logic phù hợp. Đừng âm thầm bỏ qua lỗi eviction sau khi database thay đổi nếu điều đó khiến ứng dụng phục vụ dữ liệu cũ không giới hạn.

## 16. Quan sát cache trong môi trường Redis

Chỉ biết “có annotation” chưa đủ để kết luận hiệu quả. Nên đo theo **cache name**, endpoint và thời gian:

| Chỉ số | Ý nghĩa |
|---|---|
| Cache hit/miss ratio | Cache có giảm các lần đọc nguồn không? |
| Thời gian xử lý p50/p95/p99 | Cache cải thiện trải nghiệm hay tăng latency khi Redis chậm? |
| Tải và độ trễ database/API nguồn | Mức giảm tải có thực hay miss vẫn dồn cục? |
| Số lần put/evict | Có ghi lại/xóa quá thường xuyên không? |
| Thời gian còn lại của TTL | Entry có được đặt hạn đúng như chính sách? |
| Redis command rate, memory, evicted_keys | Redis có bị quá tải hoặc đẩy khóa ra trước TTL? |
| Lỗi serialize/deserialize | Có không tương thích kiểu hoặc phiên bản cache value? |
| Độ cũ dữ liệu trả về | Cache có vượt giới hạn freshness nghiệp vụ? |

Có thể kiểm tra Redis bằng công cụ CLI ở môi trường phù hợp:

```bash
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO memory

# Ví dụ khi đã biết chính xác khóa vật lý và serializer tương ứng:
redis-cli TTL 'productById::p-17'
redis-cli TYPE 'productById::p-17'
```

`TYPE` của Redis Cache entry thường là string value, nhưng cách giải mã nội dung phụ thuộc serializer. `INFO` là thống kê toàn Redis instance, không tách tự động theo cache name hay endpoint; cần thêm metric ở phía Spring/Micrometer hoặc tầng service.

Khi rà soát nhiều khóa, dùng `SCAN` hoặc công cụ phù hợp với giới hạn tải; tránh `KEYS *` trên Redis production lớn. Không log toàn bộ cache key/value nếu chứa thông tin cá nhân hoặc dữ liệu nhạy cảm.

## 17. Khi nào chọn từng annotation?

| Nhu cầu | Annotation ưu tiên | Lý do |
|---|---|---|
| Truy vấn chi tiết sản phẩm ít đổi | `@Cacheable` | Hit bỏ qua truy vấn nguồn |
| Truy vấn kết quả tính toán tốn tài nguyên | `@Cacheable` | Tái sử dụng kết quả đã tính |
| Cập nhật entity và trả về DTO đầy đủ mới | `@CachePut` | Ghi cache bằng kết quả mới |
| Cập nhật entity nhưng method trả `void` | `@CacheEvict` | Không có value mới tin cậy để put |
| Xóa entity | `@CacheEvict` | Không phục vụ dữ liệu đã xóa |
| Đổi dữ liệu ảnh hưởng nhiều cache list/tổng hợp | `@Caching(evict = {...})` hoặc event invalidation | Phải làm mới nhiều view phụ thuộc |
| Làm mới toàn bộ danh mục/cache | `@CacheEvict(allEntries = true)` có cân nhắc | Loại bỏ nhiều entry khi migration hoặc thay đổi lớn |
| Cần ghi cache nhưng không được bỏ qua method | `@CachePut` | Method luôn thực thi |
| Dữ liệu cần nhất quán tức thời ở quyết định quan trọng | Thiết kế nguồn nhất quán phù hợp trước | Annotation cache không thay thế transaction nghiệp vụ |

Không có quy tắc “cập nhật luôn dùng `@CachePut`”. Nếu phương thức trả bản chưa hoàn chỉnh, giá trị tính toán thiếu trường, hoặc một thay đổi ảnh hưởng nhiều read model, eviction thường an toàn và dễ giải thích hơn.

## 18. Bẫy phổ biến và cách tránh

1. **Dùng `@Cacheable` trên hàm update:** cache hit khiến update không chạy. Chọn `@CachePut` hoặc `@CacheEvict`.
2. **`@CachePut` và `@Cacheable` không cùng key:** read cache vẫn giữ bản cũ. Dùng quy ước key chung.
3. **`@CachePut` trả sai kiểu value:** lần đọc sau không deserialize được hoặc trả sai dữ liệu. Đảm bảo kiểu value tương thích.
4. **Chỉ evict cache chi tiết nhưng quên cache danh sách:** API list còn bản cũ. Xác định mọi read model bị ảnh hưởng.
5. **Evict trước khi method cập nhật:** request khác có thể nạp lại dữ liệu cũ. Chọn thời điểm theo nghiệp vụ.
6. **Quên transaction commit:** cache được thay đổi dù database rollback hoặc ngược lại. Dùng transaction-aware cache và cơ chế phục hồi phù hợp.
7. **Gọi method annotation từ cùng bean:** Spring proxy có thể không intercept. Tách service hoặc thay đổi cấu trúc gọi.
8. **Key không có tenant/currency/locale:** dữ liệu bị dùng nhầm giữa ngữ cảnh khác nhau. Bao gồm tất cả đầu vào tạo kết quả.
9. **TTL quá dài:** người dùng đọc dữ liệu đã thay đổi. Chọn TTL theo freshness và invalidate khi cần.
10. **TTL quá ngắn hoặc xóa toàn bộ cache liên tục:** tạo bão cache miss. Đo tải nguồn và phân bố hết hạn.
11. **Không version hóa value serializer:** deployment khác phiên bản cùng đọc Redis có thể lỗi. Chốt schema hoặc đổi namespace.
12. **Tin `sync=true` sẽ khóa phân tán hoàn hảo:** cơ chế thực tế phụ thuộc provider. Kiểm chứng với nhiều instance.
13. **Bỏ qua lỗi Redis sau update:** cache có thể còn bản cũ. Quan sát lỗi và có phương án sửa.
14. **Dùng cache làm nguồn duy nhất của dữ liệu quan trọng:** Redis key có thể hết hạn hoặc bị evict. Xác định nguồn sự thật.

## 19. Quy trình lựa chọn trong một ứng dụng mới

```text
Phương thức có tác dụng phụ bắt buộc chạy?
                     |
              +------+------+
              |             |
            Không           Có
              |             |
              v             v
      Kết quả có thể     Thao tác tạo/cập nhật
      tái sử dụng?       hay xóa dữ liệu nguồn?
              |             |
              v             +-------------------+
        @Cacheable          |                   |
              |           Update               Delete
              |             |                   |
              |             v                   v
     Key đúng tenant?   Trả value đầy đủ     @CacheEvict
     TTL phù hợp?       và đúng kiểu?
     Null có cache?          |
                         +---+---+
                         |       |
                        Có      Không
                         |       |
                         v       v
                    @CachePut @CacheEvict
                         |       |
                         +---+---+
                             |
                             v
                      Cần invalidate
                      cache liên quan?
                             |
                             v
                     @Caching / event
                             |
                             v
                      Đối chiếu thời điểm
                      commit và chống race
```

**Điểm cốt lõi:** `@Cacheable` dùng cho **đọc và tái sử dụng kết quả**, `@CachePut` dùng khi **method phải luôn chạy và kết quả mới đáng tin cậy để ghi cache**, còn `@CacheEvict` dùng để **loại bỏ dữ liệu cache không còn hợp lệ**. Trong Spring Data Redis, ba annotation chỉ hoạt động đúng khi kết hợp với `CacheManager`, key nhất quán, TTL và serializer phù hợp, lời gọi qua Spring proxy, và chính sách xử lý ghi/commit rõ ràng. Khi có nhiều service hoặc request đồng thời, phải thiết kế thêm invalidation và đối soát để dữ liệu Redis không đi chệch nguồn nghiệp vụ.

