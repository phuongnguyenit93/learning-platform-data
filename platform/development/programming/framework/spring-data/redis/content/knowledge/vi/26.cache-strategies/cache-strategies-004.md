# Cache dữ liệu không tồn tại để giảm truy vấn lặp trong Spring Data Redis

Khi ứng dụng dùng Redis làm cache cho dữ liệu từ cơ sở dữ liệu, ta thường chỉ nghĩ đến trường hợp **tìm thấy dữ liệu**: đọc Redis, nếu chưa có thì truy vấn database rồi lưu kết quả vào cache. Tuy nhiên, một khóa **không tồn tại trong nguồn dữ liệu** cũng có thể bị truy vấn rất nhiều lần. Nếu mỗi lần đều đi xuống database vì Redis không lưu gì cho kết quả “không tìm thấy”, các request lặp lại sẽ tạo tải không cần thiết.

**Negative caching** (*cache kết quả không tồn tại*) giải quyết vấn đề đó bằng cách lưu một dấu hiệu có thời hạn ngắn: “đã kiểm tra nguồn dữ liệu và hiện không tìm thấy đối tượng này”. Những lần hỏi lại cùng khóa có thể trả kết quả không tìm thấy ngay từ Redis, tránh lặp lại truy vấn tốn tài nguyên.

Trong Spring Data Redis có hai cách triển khai phổ biến:

1. Dùng **Spring Cache** với `@Cacheable` và một `RedisCacheManager` cho phép cache `null`/giá trị rỗng theo quy tắc của Spring Cache.
2. Dùng **`StringRedisTemplate` hoặc `RedisTemplate`** để lưu một giá trị đánh dấu (*sentinel*) như `NOT_FOUND`, tách TTL của dữ liệu có thật và dữ liệu không tồn tại.

Negative caching đặc biệt hữu ích cho truy vấn sản phẩm theo ID, hồ sơ, cấu hình, danh mục, kết quả tra cứu từ dịch vụ ngoài hoặc các đường dẫn thường bị request bằng ID không hợp lệ. Tuy vậy, cache “không tìm thấy” cần **TTL ngắn và cơ chế vô hiệu hóa** để tránh tiếp tục trả 404 sau khi dữ liệu mới được tạo.

## 1. Vấn đề: “cache miss” lặp đi lặp lại

Giả sử API:

```http
GET /api/products/p-999
```

Database chưa có sản phẩm `p-999`. Với mẫu *cache-aside* chỉ lưu kết quả tìm thấy, xử lý có thể như sau:

```text
Request 1:
    GET Redis product:p-999  -> không có
    SELECT ... WHERE id=p-999 -> không có
    trả 404

Request 2:
    GET Redis product:p-999  -> không có
    SELECT ... WHERE id=p-999 -> không có
    trả 404

Request 3:
    GET Redis product:p-999  -> không có
    SELECT ... WHERE id=p-999 -> không có
    trả 404
```

Ở tất cả các request, Redis đều không có entry nên database tiếp tục bị truy vấn. Điều này có thể xảy ra do:

- Client cũ tiếp tục truy cập một ID đã bị xóa.
- Người dùng gõ nhầm một mã sản phẩm.
- Crawler hoặc bot thử nhiều URL.
- Ứng dụng liên tục đọc một cấu hình chưa được tạo.
- Một tác vụ định kỳ kiểm tra dữ liệu chưa xuất hiện.
- Client retry cùng một request “không tìm thấy”.

Với negative caching, sau lần truy vấn đầu tiên, ứng dụng lưu một dấu hiệu:

```text
product:lookup:p-999 -> NOT_FOUND   (TTL: 30 giây)
```

Những lần đọc tiếp theo:

```text
GET Redis product:lookup:p-999 -> NOT_FOUND
    |
    +--> trả kết quả không tìm thấy, không truy vấn database
```

Nếu một ID không tồn tại bị hỏi hàng trăm lần mỗi giây, việc cache ngắn hạn có thể giảm đáng kể số lần truy cập database. Mức giảm thực tế phụ thuộc TTL, sự đồng thời ở thời điểm cache còn trống, eviction và cơ chế invalidation.

## 2. Phân biệt ba trạng thái khi đọc Redis

Điều quan trọng nhất là **cache không có key** và **cache có ghi nhận kết quả “không tồn tại”** không phải cùng một trạng thái.

| Trạng thái trong Redis | Ý nghĩa | Ứng dụng cần làm |
|---|---|---|
| **Không có entry** | Chưa tra cứu, TTL đã hết hoặc key đã bị xóa/evict | Truy vấn nguồn dữ liệu |
| **Có entry dữ liệu** | Đã cache giá trị tìm thấy | Giải mã và trả giá trị |
| **Có entry đánh dấu không tồn tại** | Đã kiểm tra nguồn dữ liệu và không tìm thấy trong một khoảng thời gian gần đây | Trả kết quả “không tìm thấy” mà không truy vấn lại |

Ví dụ biểu diễn bằng các chuỗi:

```text
product:lookup:p-101 -> VALUE:{"id":"p-101","name":"Bàn làm việc"}
product:lookup:p-999 -> NOT_FOUND
product:lookup:p-888 -> <key không tồn tại>
```

Luồng quyết định:

```text
                Đọc cache theo productId
                           |
                           v
                   Redis GET(key)
                           |
               +-----------+-----------+
               |                       |
            Có entry                 Không có entry
               |                       |
       +-------+--------+              v
       |                |         Truy vấn database
     VALUE            NOT_FOUND         |
       |                |         +-----+------+
 Trả đối tượng      Trả 404       |            |
                            Tìm thấy      Không tìm thấy
                                |              |
                          Cache VALUE     Cache NOT_FOUND
                          TTL dài hơn      TTL ngắn hơn
                                |              |
                            Trả dữ liệu      Trả 404
```

**Không dùng `redis.opsForValue().get(key) == null` để kết luận bản ghi database không tồn tại.** Giá trị `null` từ Redis ở đây thường chỉ cho biết cache chưa có entry hoặc entry đã biến mất. Chỉ khi chính ứng dụng đã lưu và đọc được dấu hiệu `NOT_FOUND` mới có thông tin negative cache hit.

## 3. Negative caching khác gì cache dữ liệu rỗng?

Một API có thể trả các dạng kết quả:

| Kết quả ở nguồn dữ liệu | Có phải “không tồn tại”? | Cách cân nhắc cache |
|---|---|---|
| `Product` được tìm thấy | Không | Cache giá trị với TTL dương phù hợp |
| Không có hàng theo ID | Có | Cache sentinel hoặc `null` với TTL ngắn |
| Danh sách tìm kiếm rỗng `[]` | Không nhất thiết | Đây là một kết quả truy vấn hợp lệ; cache như dữ liệu bình thường nếu phù hợp |
| Giá sản phẩm bằng `0` | Không | Không được nhầm với “không có dữ liệu” |
| Chuỗi rỗng `""` | Không nhất thiết | Phân biệt giá trị hợp lệ và thiếu bản ghi |
| Database timeout | Không biết | Không cache thành `NOT_FOUND` |
| Database trả lỗi kết nối | Không biết | Không cache thành `NOT_FOUND` |
| Quyền truy cập bị từ chối | Không phải kết luận về sự tồn tại toàn cục | Tránh cache sai phạm vi người dùng/tenant |
| Bản ghi chưa được đồng bộ tạm thời | Chưa chắc | Cần TTL rất ngắn hoặc chiến lược chờ/đồng bộ |

Điểm cốt lõi là **negative caching lưu một kết luận có thể được tin trong khoảng thời gian ngắn**, chứ không biến mọi lỗi thành “không tồn tại”.

Nếu hệ thống dùng `Optional<Product>`, `Optional.empty()` là cách biểu diễn thuận tiện cho việc không tìm thấy. Nếu API trả `null`, cần quy định rõ `null` có nghĩa là “database đã xác nhận không có hàng” hay “đã xảy ra lỗi”. Không nên dùng chung một kết quả cho hai tình huống này.

## 4. Vì sao cần TTL ngắn cho kết quả không tồn tại?

Bản ghi không tồn tại **có thể được tạo sau đó**. Negative cache quá dài làm ứng dụng trả kết quả cũ dù nguồn dữ liệu đã thay đổi.

Ví dụ:

```text
10:00:00  GET product:p-999 -> DB không có -> cache NOT_FOUND, TTL 30 giây
10:00:10  Một request khác tạo product p-999 thành công
10:00:12  GET product:p-999 -> Redis vẫn còn NOT_FOUND
10:00:30  Negative cache hết TTL; lần đọc sau truy vấn DB và thấy sản phẩm
```

Nếu không có thao tác invalidation khi tạo sản phẩm, khoảng thời gian cache còn tồn tại là **cửa sổ trả false negative**: database có dữ liệu nhưng ứng dụng tiếp tục trả “không tìm thấy”.

Hướng chọn TTL:

- **Dữ liệu thường được tạo mới:** dùng negative TTL rất ngắn và chủ động xóa sentinel khi ghi thành công.
- **Dữ liệu gần như không bao giờ được tạo lại:** có thể chọn TTL dài hơn nếu chấp nhận được độ trễ phản ánh thay đổi.
- **ID tùy ý hoặc do bot sinh:** cần chú ý số lượng key negative; TTL ngắn giúp giải phóng các entry ít được hỏi lại.
- **Thông tin nhạy cảm về tính mới:** cân nhắc không dùng negative caching hoặc dùng cơ chế kiểm soát phiên bản/chính xác mạnh hơn.

Ví dụ chính sách minh họa:

| Loại cache | TTL ví dụ | Lý do |
|---|---|---|
| Sản phẩm đã tìm thấy | 10 phút | Giảm đọc dữ liệu tương đối ổn định |
| Sản phẩm không tồn tại | 30 giây | Giảm truy vấn lặp mà giới hạn stale 404 |
| Cấu hình chưa được tạo | 15 giây | Cho phép phát hiện cấu hình mới tương đối nhanh |
| Kết quả tra cứu ngoài hệ thống ít thay đổi | 1–2 phút | Cân bằng độ trễ và số lần gọi API ngoài |

Các con số trên **không phải mặc định của Spring Data Redis**. Cần chọn theo tần suất tạo dữ liệu, yêu cầu nhất quán, lưu lượng truy cập và khả năng chấp nhận kết quả cũ. TTL 30 giây cũng không tự bảo đảm kết quả không còn lỗi thời trong tối đa 30 giây nếu client hoặc các cache khác giữ thêm bản sao.

## 5. Cách 1: Cache `null` bằng `@Cacheable` và `RedisCacheManager`

Spring Cache abstraction có khả năng cache giá trị `null` thông qua biểu diễn nội bộ (thường liên quan đến `NullValue`) khi cache provider và cấu hình serializer hỗ trợ. Với Spring Data Redis, cấu hình Redis Cache mặc định có thể cho phép cache `null`, trừ khi ứng dụng chủ động tắt bằng `disableCachingNullValues()`.

Ví dụ phương thức nghiệp vụ:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductStore store;

    public ProductQueryService(ProductStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "productLookup", key = "#p0")
    public ProductDto findOrNull(String productId) {
        return store.findById(productId).orElse(null);
    }
}
```

`ProductStore` là thành phần lấy dữ liệu nguồn và trả về `Optional<ProductDto>`. Nếu database trả `Optional.empty()`, phương thức trả `null`. Khi cache được cấu hình cho phép `null`, Spring Cache có thể lưu một dấu hiệu null để những lần gọi sau **không chạy lại method**.

Với controller, có thể diễn giải:

```java
@GetMapping("/api/products/{id}")
public ResponseEntity<ProductDto> getProduct(@PathVariable String id) {
    ProductDto product = queryService.findOrNull(id);

    if (product == null) {
        return ResponseEntity.notFound().build();
    }

    return ResponseEntity.ok(product);
}
```

Khi gọi qua Spring bean proxy và caching được bật, lần đầu không tìm thấy vẫn chạy nguồn dữ liệu; các lần đọc sau trong TTL có thể nhận lại `null` từ cache mà không gọi `ProductStore`.

### 5.1. Cấu hình `RedisCacheManager` cho negative caching bằng null

Ví dụ Spring Boot/Spring Data Redis sử dụng Jackson 2 và `GenericJackson2JsonRedisSerializer`:

```java
import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory
    ) {
        RedisCacheConfiguration lookupConfig =
                RedisCacheConfiguration.defaultCacheConfig()
                    .entryTtl(Duration.ofSeconds(30))
                    // Giữ hỗ trợ caching null trong cấu hình.
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

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(lookupConfig)
                .withInitialCacheConfigurations(
                    Map.of("productLookup", lookupConfig)
                )
                .build();
    }
}
```

Trong ví dụ, cả kết quả tìm thấy và không tìm thấy đều dùng **TTL 30 giây**, vì cùng thuộc cache `productLookup`. Cấu hình này đơn giản, nhưng thường không phải lựa chọn tối ưu khi muốn **positive cache 10 phút** và **negative cache 30 giây**.

Một số lưu ý:

1. `@EnableCaching` phải được bật và method phải được gọi **qua Spring proxy**. Self-invocation bằng `this.findOrNull(...)` có thể bỏ qua `@Cacheable`.
2. Với `RedisCacheConfiguration`, **không gọi `disableCachingNullValues()`** nếu đang dùng `null` làm negative value.
3. Không thêm `unless = "#result == null"` vào `@Cacheable`, vì điều kiện này có nghĩa **không lưu** kết quả null và sẽ làm mất cơ chế negative caching.
4. Cần chọn serializer đọc/ghi được marker null của Spring Cache. Với JSON serializer, kiểm tra khả năng hỗ trợ `NullValue` ở phiên bản thư viện và cấu hình ObjectMapper đang dùng.
5. Nếu đã chọn **không cache null** ở manager, việc `@Cacheable` cố ghi null có thể bị từ chối; nên áp dụng `unless` hoặc chọn mô hình sentinel tường minh.
6. Nếu phương thức ném `NotFoundException` thay vì trả `null`, `@Cacheable` thông thường không coi exception là một giá trị để lưu. Hãy chuyển kết quả “không tìm thấy” thành một return value rõ nghĩa nếu muốn negative cache.

### 5.2. `Optional.empty()` có thể tham gia Spring Cache ra sao?

Spring Cache có hỗ trợ phương thức trả về `Optional<T>` trong nhiều phiên bản hiện đại. Khi `Optional.empty()` được trả về, Spring Cache có thể xử lý nó như **giá trị null để caching**, rồi tái tạo dạng `Optional` khi đọc cache theo hợp đồng của abstraction.

Ví dụ ý tưởng:

```java
@Cacheable(cacheNames = "productLookup", key = "#p0")
public Optional<ProductDto> find(String id) {
    return store.findById(id);
}
```

Vì có bước xử lý `Optional` ở tầng Spring Cache, không nên mặc định serializer sẽ lưu trực tiếp một Java `Optional` bình thường. Hãy hiểu cách phiên bản Spring đang dùng xử lý giá trị rỗng và có cấu hình cache null tương thích.

Một ưu điểm của `Optional` là tầng gọi không cần dùng `null` để biểu diễn kết quả. Tuy vậy, **TTL vẫn thuộc cache**, không tự phân biệt `Optional.empty()` và giá trị có thật trừ khi dùng cơ chế TTL động hoặc một mô hình lưu khác.

### 5.3. Khi nào nên chọn cách này?

Cách dùng `@Cacheable` với null phù hợp khi:

- Cần thay đổi ít code.
- Mọi kết quả lookup có cùng TTL chấp nhận được.
- Không cần tự đặt định dạng sentinel.
- Đã hiểu serializer và behavior `null` của cache provider.
- Không có yêu cầu cập nhật nguyên tử hoặc versioning đặc biệt.

Nếu negative và positive cần TTL khác nhau, có chính sách invalidation phức tạp hoặc cần thống kê riêng từng loại, dùng RedisTemplate với sentinel thường trực quan hơn.

## 6. Cách 2: Dùng sentinel với `StringRedisTemplate`

Một mẫu linh hoạt là lưu **giá trị biểu diễn rõ trạng thái**:

```text
NOT_FOUND           -> nguồn dữ liệu đã xác nhận không tồn tại
VALUE:{...json...}  -> đối tượng đã tìm thấy
<no key>            -> cache miss, cần tra nguồn
```

Tiền tố `VALUE:` giúp dữ liệu hợp lệ không vô tình trùng với sentinel `NOT_FOUND`. Nếu cache có thể chứa chuỗi bất kỳ do người dùng cung cấp, mô hình có tiền tố hoặc object wrapper với trường `status` sẽ rõ ràng hơn việc dùng một chuỗi không phân biệt kiểu.

Trong ví dụ dưới đây:

- Positive cache có TTL **10 phút**.
- Negative cache có TTL **30 giây**.
- Redis key phân biệt **tenant** và **product ID**.
- Ghi giá trị và TTL trong **cùng một thao tác `SET`**.
- Database là nguồn sự thật; Redis chỉ là lớp tăng tốc.

### 6.1. Định nghĩa DTO và nguồn dữ liệu

```java
package com.example.catalog;

public record ProductDto(
    String id,
    String name
) {}
```

Một interface trừu tượng hóa nguồn dữ liệu:

```java
package com.example.catalog;

import java.util.Optional;

public interface ProductStore {
    Optional<ProductDto> findById(String tenantId, String productId);
}
```

Implementation của `ProductStore` có thể gọi JPA repository, REST API nội bộ hoặc truy vấn khác. Điểm quan trọng là `Optional.empty()` chỉ được trả khi **nguồn dữ liệu đã xác nhận không tìm thấy**; lỗi timeout hoặc DB unavailable phải được biểu diễn bằng exception hoặc loại lỗi riêng.

### 6.2. Service tra cứu với positive/negative TTL riêng

```java
package com.example.catalog;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Base64;
import java.util.Optional;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupCache {

    private static final Duration FOUND_TTL =
            Duration.ofMinutes(10);

    private static final Duration NOT_FOUND_TTL =
            Duration.ofSeconds(30);

    private static final String NOT_FOUND = "NOT_FOUND";
    private static final String VALUE_PREFIX = "VALUE:";

    private final StringRedisTemplate redis;
    private final ProductStore store;
    private final ObjectMapper objectMapper;

    public ProductLookupCache(
            StringRedisTemplate redis,
            ProductStore store,
            ObjectMapper objectMapper
    ) {
        this.redis = redis;
        this.store = store;
        this.objectMapper = objectMapper;
    }

    public Optional<ProductDto> find(
            String tenantId,
            String productId
    ) {
        String key = cacheKey(tenantId, productId);
        String cached = redis.opsForValue().get(key);

        if (NOT_FOUND.equals(cached)) {
            // Negative cache hit: không cần truy vấn database.
            return Optional.empty();
        }

        if (cached != null && cached.startsWith(VALUE_PREFIX)) {
            // Positive cache hit.
            String json = cached.substring(VALUE_PREFIX.length());
            return Optional.of(readProduct(json));
        }

        // Chỉ khi Redis không có entry mới truy vấn nguồn dữ liệu.
        Optional<ProductDto> fromStore =
                store.findById(tenantId, productId);

        if (fromStore.isPresent()) {
            String json = writeProduct(fromStore.get());

            redis.opsForValue().set(
                key,
                VALUE_PREFIX + json,
                FOUND_TTL
            );
        } else {
            redis.opsForValue().set(
                key,
                NOT_FOUND,
                NOT_FOUND_TTL
            );
        }

        return fromStore;
    }

    public void invalidate(String tenantId, String productId) {
        redis.delete(cacheKey(tenantId, productId));
    }

    private String cacheKey(String tenantId, String productId) {
        return "catalog:product-lookup:v1:"
                + encode(tenantId)
                + ":"
                + encode(productId);
    }

    private String encode(String value) {
        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(
                    value.getBytes(StandardCharsets.UTF_8)
                );
    }

    private String writeProduct(ProductDto product) {
        try {
            return objectMapper.writeValueAsString(product);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Không thể serialize ProductDto",
                ex
            );
        }
    }

    private ProductDto readProduct(String json) {
        try {
            return objectMapper.readValue(json, ProductDto.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Không thể deserialize ProductDto",
                ex
            );
        }
    }
}
```

**Giải thích từng nhánh:**

| Nhánh | Dữ liệu Redis | Lệnh tiếp theo |
|---|---|---|
| `cached == NOT_FOUND` | Negative cache hit | Trả `Optional.empty()` |
| `cached.startsWith("VALUE:")` | Positive cache hit | Deserialize `ProductDto`, trả giá trị |
| `cached == null` | Cache miss | Gọi `store.findById(...)` |
| DB có sản phẩm | Positive lookup | Lưu `VALUE:<json>` với TTL 10 phút |
| DB không có sản phẩm | Negative lookup | Lưu `NOT_FOUND` với TTL 30 giây |

Một số điểm kỹ thuật:

- `opsForValue().set(key, value, Duration)` đặt value và TTL trong một thao tác Redis phù hợp, tránh khoảng trống do gọi `SET` rồi `EXPIRE` riêng.
- Vì `StringRedisTemplate` dùng string serializer, có thể kiểm tra dữ liệu cache qua Redis CLI.
- Biểu diễn `NOT_FOUND` khác hoàn toàn với `null` của lần đọc Redis cache miss.
- `Base64` giúp ghép tenant ID/product ID thành namespace không mơ hồ khi ID chứa dấu `:` hoặc ký tự phân tách.
- `v1` là version của cache schema; nếu đổi định dạng value, có thể tăng version để tránh đọc nhầm các entry cũ.
- Khi chuỗi cache không null nhưng không thuộc định dạng `NOT_FOUND` hoặc `VALUE:`, ví dụ trên sẽ coi nó như miss và ghi lại sau khi tra nguồn. Trong production có thể chọn ghi metric, xóa entry lỗi định dạng hoặc fail fast tùy chính sách dữ liệu.

### 6.3. Vì sao không trả `null` từ Redis là “không tồn tại”?

Nếu code chỉ viết:

```java
String value = redis.opsForValue().get(key);

if (value == null) {
    return Optional.empty(); // SAI: chưa hề kiểm tra DB
}
```

thì lần tra cứu đầu tiên của **một sản phẩm có thật nhưng chưa được cache** cũng bị kết luận là không tồn tại.

Mẫu đúng là:

```java
if (value == null) {
    // Redis cache miss -> kiểm tra nguồn sự thật.
    return store.findById(tenantId, productId);
}
```

Sau khi database trả “không tìm thấy”, mới được lưu negative sentinel có thời hạn.

### 6.4. Có nên dùng `setIfAbsent` cho sentinel?

Một biến thể là:

```java
redis.opsForValue().setIfAbsent(
    key,
    NOT_FOUND,
    NOT_FOUND_TTL
);
```

Lệnh `SET ... NX EX` chỉ ghi sentinel khi Redis key chưa tồn tại ở thời điểm lệnh thực thi. Nó có thể **giảm rủi ro ghi đè một positive cache entry** do request khác vừa nạp lại.

Tuy nhiên, `setIfAbsent` **không giải quyết hoàn toàn race với dữ liệu được tạo mới**. Nếu có một thao tác xóa cache sau commit nhưng request cũ lại đặt sentinel sau lần xóa đó, key vẫn có thể chứa `NOT_FOUND` trong TTL còn lại. Khi cần bảo đảm nhất quán mạnh, phải thiết kế cơ chế version/sequence hoặc đồng bộ quyền ghi cache rõ ràng.

## 7. Cập nhật và vô hiệu negative cache khi dữ liệu được tạo

TTL ngắn giảm thời gian sai lệch, nhưng hệ thống nên **xóa negative cache sau khi ghi dữ liệu mới thành công**.

Giả sử:

```text
t0: GET product:p-999 -> DB không có -> Redis lưu NOT_FOUND
t1: POST /products tạo p-999 thành công
t2: GET product:p-999
```

Nếu entry `NOT_FOUND` vẫn còn ở `t2`, API có thể trả 404 dù DB đã có sản phẩm. Vì vậy đường ghi cần biết key lookup tương ứng và vô hiệu hóa nó.

### 7.1. Luồng đơn giản khi đã ghi thành công

Nếu hàm tạo dữ liệu đảm bảo nguồn sự thật đã commit trước khi trả về:

```java
ProductDto created = productWriter.createCommitted(tenantId, request);

productLookupCache.invalidate(tenantId, created.id());
```

Lần đọc sau sẽ thấy cache miss và tải dữ liệu thật. Tên `createCommitted(...)` ở đây diễn đạt hợp đồng của tầng ghi; trong chương trình thực tế cần xác định chính xác thời điểm commit.

### 7.2. Nếu cập nhật trong transaction database

Khi dữ liệu được tạo trong Spring `@Transactional` với DB quan hệ, nên quan tâm **thời điểm commit**. Xóa cache trước khi DB commit có thể dẫn tới tình huống client khác nạp lại kết quả “không có” từ snapshot cũ.

Một hướng Spring phổ biến là phát event và xử lý sau commit:

```java
public record ProductCreated(
    String tenantId,
    String productId
) {}
```

Service ghi dữ liệu:

```java
@Service
public class ProductWriteService {

    private final ProductJpaStore store;
    private final ApplicationEventPublisher events;

    public ProductWriteService(
            ProductJpaStore store,
            ApplicationEventPublisher events
    ) {
        this.store = store;
        this.events = events;
    }

    @Transactional
    public ProductDto create(String tenantId, CreateProductRequest req) {
        ProductDto created = store.create(tenantId, req);
        events.publishEvent(
            new ProductCreated(tenantId, created.id())
        );
        return created;
    }
}
```

Listener vô hiệu sau commit:

```java
@Component
public class ProductCacheInvalidator {

    private final ProductLookupCache cache;

    public ProductCacheInvalidator(ProductLookupCache cache) {
        this.cache = cache;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void invalidate(ProductCreated event) {
        cache.invalidate(event.tenantId(), event.productId());
    }
}
```

Trong đoạn minh họa, `ProductJpaStore` và `CreateProductRequest` là các kiểu thuộc ứng dụng; cần có implementation tương ứng. Các annotation/type Spring như `@Service`, `@Component`, `@Transactional`, `ApplicationEventPublisher`, `@TransactionalEventListener` và `TransactionPhase` cần được import từ Spring.

**Hạn chế quan trọng:** `@TransactionalEventListener(AFTER_COMMIT)` chạy sau commit khi process còn hoạt động; nó **không phải hàng đợi sự kiện bền vững**. Nếu tiến trình ngừng ngay sau DB commit, invalidation có thể không xảy ra. Có thể dùng transactional outbox và worker retry khi yêu cầu invalidation đáng tin cậy hơn. Negative TTL ngắn đóng vai trò giới hạn thời gian tồn tại của entry cũ nếu bỏ lỡ invalidation.

## 8. Race condition: invalidation xong vẫn có thể bị ghi sentinel cũ

Một race khó nhận biết:

```text
Request A                               Request B
---------                               ---------
Redis GET -> MISS
DB SELECT -> không có

                                        Tạo sản phẩm p-999
                                        DB COMMIT
                                        Redis DEL negative key

Redis SET NOT_FOUND EX 30
```

Kết quả cuối: **DB đã có sản phẩm nhưng Redis lại chứa `NOT_FOUND`** do request A ghi sau khi request B invalidation.

Điều này có thể xảy ra với mẫu cache-aside thông thường, kể cả khi đã xóa cache sau commit. `setIfAbsent` ở riêng bước ghi sentinel vẫn có thể thấy key không tồn tại rồi ghi `NOT_FOUND`.

Các cách xử lý được lựa chọn theo mức độ chấp nhận sai lệch:

1. **Chấp nhận tính nhất quán cuối cùng trong TTL ngắn.** Với catalog có yêu cầu độ mới vừa phải, negative TTL 10–30 giây có thể là một đánh đổi hợp lý.
2. **Ghi positive cache từ đường tạo dữ liệu:** sau commit, dùng dữ liệu mới để cập nhật entry. Cách này giảm nhiều trường hợp stale 404, nhưng vẫn phải xem xét thứ tự giữa các request.
3. **Dùng version/generation hoặc fencing token cho key lookup:** yêu cầu request cũ chỉ được ghi nếu version lúc đọc vẫn hợp lệ; cập nhật version và entry cần có thao tác nguyên tử phù hợp tại Redis.
4. **Dùng cơ chế điều phối ghi và nạp cache:** khóa có TTL/cơ chế singleflight hoặc kiểm tra lại source theo yêu cầu, thiết kế retry và recovery; tránh phụ thuộc vào lock chưa được bảo đảm.
5. **Không negative-cache dữ liệu có yêu cầu read-after-write nghiêm ngặt:** nếu vừa tạo xong buộc phải đọc thấy ngay, hãy dùng đường đọc ưu tiên nguồn dữ liệu hoặc một cơ chế nhất quán mạnh hơn.

Không nên xem `DEL` sau commit là chứng minh tuyệt đối rằng sẽ không bao giờ còn stale negative cache. Với các hệ thống mà 404 sai gây tổn thất, cần thiết kế toàn bộ thứ tự đọc–ghi–invalidate, không chỉ chọn TTL.

## 9. Cache penetration, hot miss và cache stampede

Negative caching thường được thảo luận cùng hai vấn đề liên quan:

### 9.1. Cache penetration

*Cache penetration* là tình huống request liên tục tìm những key **không có trong cache và nguồn dữ liệu**. Nếu mọi request đều bỏ qua cache và truy vấn DB, tải database tăng.

```text
Request lặp cùng ID không tồn tại
    |
Redis MISS -> Database MISS
Redis MISS -> Database MISS
Redis MISS -> Database MISS
```

Negative caching tạo entry `NOT_FOUND` giúp biến những request lặp cho cùng ID thành **negative cache hit**.

### 9.2. Hot miss và cache stampede

Ngay tại thời điểm negative cache chưa có entry, nhiều request đồng thời có thể cùng thấy miss:

```text
100 request đồng thời cho p-999
             |
             v
100 lần Redis GET -> MISS
             |
             v
Có thể có nhiều lần DB SELECT trước khi request đầu tiên ghi NOT_FOUND
```

Negative caching **giảm tải sau khi sentinel đã được lưu**, nhưng không tự bảo đảm chỉ một request truy vấn DB ở đợt miss đầu tiên.

Cân nhắc những giải pháp bổ sung:

- *Singleflight* trong một tiến trình: gom nhiều request đang chờ cùng một key.
- `@Cacheable(sync = true)` nếu dùng Spring Cache và cache provider hỗ trợ phạm vi đồng bộ cần thiết. Không mặc định bảo đảm một loader duy nhất xuyên nhiều JVM.
- Khóa phân tán ngắn hạn có quy tắc ownership, timeout và retry rõ ràng khi thật sự cần.
- Chủ động làm ấm negative cache cho các ID thường bị hỏi sai và đã được xác thực ở nguồn.
- Hạn chế tần suất request theo client hoặc endpoint nếu lưu lượng có dấu hiệu lạm dụng.

Nếu cần ngăn **cache breakdown** ở key cực nóng, có thể kết hợp một vùng chờ ngắn, TTL jitter và fallback theo tải; độ phức tạp cần tương xứng với nguy cơ thực tế.

### 9.3. ID ngẫu nhiên số lượng lớn

Một bot có thể gửi hàng triệu ID khác nhau. Mỗi ID chỉ được hỏi một lần:

```text
GET /products/random-000001
GET /products/random-000002
GET /products/random-000003
...
```

Trong trường hợp này, negative caching có thể **không tiết kiệm đáng kể truy vấn DB** vì không có request lặp cùng key, nhưng vẫn tạo rất nhiều sentinel chiếm bộ nhớ Redis.

Vì vậy cần phối hợp:

- Kiểm tra định dạng ID trước khi truy cập database.
- Rate limiting theo request/tenant hoặc IP theo chính sách vận hành.
- TTL ngắn và giới hạn dung lượng cache.
- Thống kê số lượng unique negative keys để phát hiện cardinality tăng bất thường.
- Khi thích hợp, cân nhắc cấu trúc hỗ trợ membership như Bloom filter **với hiểu biết đúng về false positive và quy trình cập nhật dữ liệu mới**.

Bloom filter không phải giải pháp thay thế trực tiếp cho mọi negative cache. Nếu dùng nó để kết luận “chắc chắn không tồn tại”, dữ liệu mới tạo phải được cập nhật vào filter đúng cách; nếu không, hệ thống có thể trả sai. Và bản thân filter có đặc điểm xác suất, khác với sentinel mang kết luận tạm thời cho một ID cụ thể.

## 10. Thiết kế key để không tạo rò rỉ giữa tenant và người dùng

Nếu sản phẩm chỉ hiện diện với một tenant hoặc một phạm vi quyền truy cập nhất định, cache key phải phản ánh **đúng phạm vi dữ liệu**:

```text
SAI nếu dữ liệu phân quyền theo tenant:
    product:lookup:p-42

ĐÚNG với dữ liệu độc lập theo tenant:
    product:lookup:<tenant-id>:p-42
```

Nếu `p-42` không tồn tại trong tenant A nhưng có trong tenant B, một negative entry dùng chung key có thể khiến B nhận 404 sai.

Tương tự, kết quả “không thấy” có thể do:

- Thực sự không có bản ghi trong hệ thống.
- Bản ghi không thuộc tenant hiện tại.
- Người dùng không có quyền đọc.
- Bản ghi đang bị ẩn theo thời gian, trạng thái hoặc chính sách.
- API cố tình trả 404 thay cho 403 để tránh lộ tài nguyên.

**Không cache một kết luận phụ thuộc quyền truy cập như một kết luận toàn cục.** Nếu negative caching được áp dụng trước bước authorization, có thể tạo lỗi phân quyền hoặc lộ thông tin qua thời gian phản hồi.

Nguyên tắc:

1. Quy định namespace theo tenant, resource type và phiên bản schema.
2. Chỉ dùng các đầu vào ảnh hưởng đến kết quả để tạo cache key.
3. Không dùng negative cache để bỏ qua kiểm tra quyền truy cập bắt buộc.
4. Tách kết quả “không tồn tại” với “không được phép” nếu nghiệp vụ cần.
5. Tránh đưa token, thông tin nhạy cảm hoặc raw PII vào tên key Redis có thể xuất hiện trong log/monitoring.

Khi ID chứa ký tự đặc biệt, nên mã hóa thành key an toàn và không mơ hồ. Ví dụ `Base64 URL-safe` hoặc hashing xác định, đồng thời cân nhắc số lượng key và tính dễ quan sát.

## 11. Negative caching có thể tạo rủi ro nhất quán nào khác?

### 11.1. Xóa rồi tạo lại cùng ID

Giả sử một sản phẩm bị xóa, ứng dụng ghi `NOT_FOUND`; vài giây sau người vận hành khôi phục sản phẩm cùng ID. Nếu cache chưa bị invalidated, API có thể tiếp tục trả 404.

Tốt nhất đường tạo, khôi phục, import hoặc đồng bộ dữ liệu đều hiểu rằng **dữ liệu xuất hiện trở lại** cần xóa negative entry.

### 11.2. Nguồn dữ liệu replica bị trễ

Một service đọc từ read replica. Sau khi ghi vào primary, replica chưa đồng bộ kịp:

```text
Write primary: tạo p-42 thành công
Read replica: chưa thấy p-42
Cache: ghi NOT_FOUND
```

Đây không phải “không tồn tại” ổn định mà là **chậm đồng bộ**. Nếu hệ thống có read replica, cần cân nhắc consistency mode, thời gian lag và TTL negative; đôi khi phải đọc primary cho các trường hợp cần read-after-write.

### 11.3. Lỗi mạng bị hiểu sai thành not-found

Ví dụ code nguy hiểm:

```java
try {
    return database.findById(id);
} catch (Exception ignored) {
    return Optional.empty();
}
```

Nếu database timeout, service ghi `NOT_FOUND` khiến những request sau nhận 404 từ cache dù bản ghi có thật.

Phải phân biệt rõ `Optional.empty()` hợp lệ và lỗi hệ thống:

```java
Optional<ProductDto> result = database.findById(id);
// Nếu database lỗi, để exception được xử lý ở luồng lỗi.
// Chỉ cache NOT_FOUND khi result thực sự empty.
```

### 11.4. Kết quả tra cứu có thể phụ thuộc thời điểm

Ví dụ cấu hình chưa đến ngày có hiệu lực hoặc bài viết có lịch xuất bản. Ở thời điểm hiện tại, API có thể trả “không tìm thấy”, nhưng vài giây sau kết quả tự thay đổi mà không có hành động tạo mới thông thường.

Với trường hợp này, negative TTL nên không vượt quá thời điểm kết quả có thể đổi theo lịch; hoặc không cache negative nếu yêu cầu tính mới chặt.

### 11.5. Eviction làm giảm hiệu quả

Redis có thể loại key sentinel trước TTL khi dùng chính sách eviction phù hợp. Khi đó request lại truy vấn database sớm hơn dự kiến. Negative caching là tối ưu hiệu năng; không phải hợp đồng đảm bảo số lần DB query tuyệt đối.

## 12. TTL jitter và phân bố thời điểm hết hạn

Nếu cùng một thời điểm có rất nhiều request tới những ID không tồn tại, nhiều sentinel có thể được ghi gần như cùng lúc và hết TTL đồng loạt.

Một chiến lược là thêm *jitter* nhỏ vào TTL:

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

int extraSeconds = ThreadLocalRandom.current()
        .nextInt(0, 11); // từ 0 đến 10 giây

Duration negativeTtl =
        Duration.ofSeconds(20 + extraSeconds);

redis.opsForValue().set(key, NOT_FOUND, negativeTtl);
```

Ví dụ TTL dao động từ 20 đến 30 giây. Jitter làm phân tán các đợt hết hạn, nhưng:

- Không thể thay thế invalidation.
- Không ngăn được hoàn toàn cache stampede ở key cực nóng.
- Cần chọn khoảng jitter không vượt yêu cầu về độ mới.
- Một key được truy vấn cực thường xuyên vẫn có thể bị nhiều request cùng miss tại thời điểm hết hạn.

Với ứng dụng cần dự đoán chính xác hành vi trong test, hãy truyền nguồn tạo TTL hoặc random vào thành phần cấu hình để kiểm soát được khi chạy kiểm thử.

## 13. Giới hạn bộ nhớ dành cho sentinel

Mỗi negative key tiêu tốn RAM để lưu key, value, metadata và TTL. Nếu tạo quá nhiều entry không có khả năng được truy cập lại, negative caching có thể cạnh tranh bộ nhớ với positive cache.

Ví dụ với Redis cùng dùng cho cả cache sản phẩm và những key quan trọng khác:

```text
catalog:positive:*    -> dữ liệu có thể tái tạo, nhiều request lặp
catalog:negative:*    -> hàng trăm nghìn ID được hỏi một lần
```

Nếu số lượng negative keys tăng mạnh, Redis có thể bắt đầu eviction những positive entries hữu ích hoặc gặp lỗi ghi tùy `maxmemory-policy`.

Một số hướng kiểm soát:

- Chọn **negative TTL ngắn**.
- Theo dõi `used_memory`, `evicted_keys`, số lượng key theo prefix và tỷ lệ tái sử dụng negative entries.
- Giới hạn độ dài key để tránh key chứa payload tùy ý khổng lồ.
- Kiểm tra định dạng ID và chặn request vô nghĩa trước Redis/DB.
- Tách workload cache theo instance nếu negative traffic quá lớn và có thể ảnh hưởng dữ liệu quan trọng.
- Cân nhắc không cache những ID có xác suất được hỏi lại gần bằng 0, nếu có tín hiệu đáng tin để quyết định.

Không sử dụng `KEYS catalog:negative:*` thường xuyên trên production để đếm key: lệnh này có thể quét keyspace lớn và ảnh hưởng hiệu năng. Ưu tiên metric được thu thập chủ động hoặc dùng `SCAN` với giới hạn hợp lý khi cần điều tra.

## 14. Quan sát hiệu quả negative caching

Một hệ thống nên biết negative cache có thực sự giảm tải DB hay chỉ đang tốn RAM.

Các metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| `lookup.cache.positive_hit` | Có dữ liệu trong cache và trả thành công |
| `lookup.cache.negative_hit` | Có sentinel, không cần gọi DB |
| `lookup.cache.miss` | Redis không có key và cần tra nguồn |
| `lookup.source.found` | Database tìm thấy bản ghi sau cache miss |
| `lookup.source.not_found` | Database xác nhận không có bản ghi |
| `lookup.cache.negative_write` | Số entry `NOT_FOUND` được ghi |
| `lookup.cache.invalidate` | Số lần vô hiệu hóa khi dữ liệu thay đổi |
| `lookup.cache.error` | Lỗi kết nối hoặc serialization của cache |
| `lookup.source.latency` | Độ trễ truy vấn nguồn dữ liệu |
| `lookup.cache.keys_estimate` | Ước lượng cardinality và sức chứa negative cache |

Một tỷ lệ đơn giản để đánh giá hiệu quả trong nhóm request trả “không tìm thấy”:

```text
negative_hit_ratio =
    negative_cache_hits /
    (negative_cache_hits + source_not_found_queries)
```

Tỷ lệ cao cho thấy nhiều request không tìm thấy đã được giải quyết ngay từ Redis; tuy nhiên phải nhìn cùng mức độ **stale 404**, số key khác nhau, lỗi và độ trễ. Không nên tối ưu hit ratio bằng cách tăng TTL quá dài nếu điều đó khiến dữ liệu mới tạo chậm xuất hiện.

### 14.1. Lệnh Redis CLI hỗ trợ quan sát

Với key minh họa:

```redis
GET catalog:product-lookup:v1:<tenant>:<id>
TTL catalog:product-lookup:v1:<tenant>:<id>
PTTL catalog:product-lookup:v1:<tenant>:<id>
INFO stats
INFO memory
```

`TTL` có thể trả:

| Giá trị | Ý nghĩa |
|---|---|
| Số không âm | Số giây còn lại |
| `-1` | Key tồn tại nhưng không có TTL |
| `-2` | Key không tồn tại |

Trong ví dụ `ProductLookupCache`, `<tenant>` và `<id>` là **phần đã mã hóa Base64 URL-safe**, không phải chuỗi raw. Khi kiểm tra CLI, phải dùng chính xác key do ứng dụng tạo ra.

`TTL = -2` chỉ nói Redis không còn key; có thể do chưa từng cache, hết TTL, evict chủ động hoặc eviction theo áp lực bộ nhớ. Nó không cho biết database có bản ghi hay không.

Có thể quan sát lượng key theo prefix trên môi trường thử nghiệm với `SCAN`:

```redis
SCAN 0 MATCH catalog:product-lookup:v1:* COUNT 100
```

`SCAN` có cursor: muốn đi hết phải lặp bằng cursor trả về cho đến `0`; `COUNT` là gợi ý số lượng xử lý mỗi lần, không phải cam kết trả đúng 100 key. Không xem kết quả scan là snapshot nhất quán khi key đang thay đổi đồng thời.

## 15. Xử lý Redis unavailable: không biến lỗi cache thành 404

Nếu Redis timeout, dòng code:

```java
String cached = redis.opsForValue().get(key);
```

có thể ném exception. Với cache chỉ phục vụ tối ưu hiệu năng, có thể chọn chính sách **fail-open**: thử lấy dữ liệu từ database khi Redis lỗi.

Tuy nhiên, cần tách hai tình huống:

1. **Redis lỗi**: không biết giá trị cache; tra lại nguồn dữ liệu nếu cho phép.
2. **Redis có sentinel `NOT_FOUND`**: đã ghi nhận negative hit; có thể trả không tìm thấy trong TTL mà không tra nguồn.

Không được xử lý bằng:

```java
catch (Exception ex) {
    return Optional.empty(); // SAI: Redis lỗi không chứng minh DB không có.
}
```

Một cách thiết kế rõ là tách đọc cache thành kết quả có ba trạng thái `HIT_VALUE`, `HIT_NOT_FOUND`, `MISS`, thêm trạng thái `CACHE_ERROR` được xử lý riêng. Khi cache lỗi nhưng nguồn dữ liệu sẵn sàng, ứng dụng có thể bỏ qua cache và tiếp tục phục vụ request theo chính sách fail-open.

Cần quan sát lỗi cache để tránh trường hợp Redis sập khiến toàn bộ traffic đổ dồn về DB mà không có giới hạn lưu lượng.

## 16. Negative caching với API HTTP: những mã trạng thái nào nên cache?

Negative caching có thể diễn ra ở tầng ứng dụng Redis hoặc ở tầng HTTP cache/CDN, nhưng **hai tầng có quy tắc khác nhau**.

| Trường hợp API | Cân nhắc |
|---|---|
| `404 Not Found` do nguồn xác nhận không tồn tại | Có thể negative cache TTL ngắn nếu kết quả ổn định trong TTL |
| `410 Gone` do tài nguyên bị xóa vĩnh viễn | Có thể cân nhắc TTL dài hơn nếu nghiệp vụ bảo đảm không khôi phục |
| `403 Forbidden` | Là kết quả phân quyền; phải xét danh tính và quyền của caller, không dùng sentinel chung |
| `401 Unauthorized` | Không biến thành negative cache dữ liệu |
| `429 Too Many Requests` | Là giới hạn tần suất, không chứng minh tài nguyên thiếu |
| `500` hoặc `503` | Lỗi hệ thống, không cache như not-found |
| Timeout từ nguồn | Không biết sự tồn tại, không cache negative |
| Danh sách rỗng `200 []` | Có thể cache như một kết quả hợp lệ với TTL phù hợp |

Một endpoint có thể **cố tình trả 404 cho tài nguyên không được phép truy cập**. Vì vậy không lấy HTTP status 404 của một backend bất kỳ rồi coi đó là “ID không tồn tại toàn cục”. Cần xem chính sách ẩn tài nguyên và phạm vi cache key.

## 17. Mô hình sentinel riêng hay cache null của Spring Cache?

| Tiêu chí | `@Cacheable` + null | `StringRedisTemplate` + sentinel |
|---|---|---|
| Số lượng code | Gọn, ít code boilerplate | Nhiều code xử lý key/serializer |
| Cách tích hợp | Spring Cache method interception | Cache-aside chủ động trong service |
| Biểu diễn “not found” | Marker null do cache abstraction quản lý | Sentinel như `NOT_FOUND` |
| TTL positive/negative khác nhau | Cần cơ chế TTL động hoặc cách tổ chức cache phù hợp | Dễ đặt `Duration` khác nhau theo nhánh |
| Xử lý cache miss | Spring Cache gọi method khi miss | Code tự gọi nguồn khi Redis `GET` không có |
| Kiểm soát key | SpEL/key generator + manager prefix | Tự thiết kế key namespace |
| Tránh xung đột với null thật | Phải hiểu semantics null/Optional của phương thức | Sentinel phân biệt trạng thái rõ |
| Metric negative hit riêng | Cần instrument tầng cache/provider | Có thể đếm trực tiếp nhánh sentinel |
| Invalidation | `@CacheEvict`, `Cache.evict` | `redis.delete(key)` |
| Serializer | Theo `RedisCacheConfiguration` | Theo template, ví dụ String/JSON chủ động |
| Phù hợp | Lookup đơn giản, TTL chung | TTL riêng, chính sách invalidation và quan sát chi tiết |

**Không chọn một cách chỉ vì ít dòng code hơn.** Nếu yêu cầu chỉ giảm tải cho những lookup không có dữ liệu, `@Cacheable` với null có thể đủ. Nếu hệ thống cần TTL ngắn cho not-found, TTL dài cho found và đường ghi chủ động xóa sentinel, mô hình sentinel rõ ràng hơn.

Một phương án khác ở những phiên bản Spring Data Redis có hỗ trợ TTL function theo giá trị là cấu hình TTL động ở cache provider. Cách này cần dựa vào API và kiểu đối tượng cache thật sự, đặc biệt cách Spring Cache biểu diễn `null` và `Optional.empty()`, để tránh áp dụng TTL sai.

## 18. Bài thực hành: quan sát negative cache hoạt động

Giả sử dùng `ProductLookupCache` ở phần 6 và có một `ProductStore` trả `Optional.empty()` cho ID `p-999`.

**Bước 1 — Gọi lookup lần đầu.**

```java
Optional<ProductDto> first =
        productLookupCache.find("tenant-A", "p-999");
```

Kết quả: `first.isEmpty() == true`. Redis chưa có entry nên database được hỏi một lần, sau đó ứng dụng ghi `NOT_FOUND` với TTL 30 giây.

**Bước 2 — Gọi lại cùng ID trong TTL.**

```java
Optional<ProductDto> second =
        productLookupCache.find("tenant-A", "p-999");
```

Kết quả vẫn rỗng, nhưng lần này Redis trả sentinel. Database không cần được gọi lại nếu cache còn entry và Redis hoạt động bình thường.

**Bước 3 — Gọi một ID có thật.**

```java
Optional<ProductDto> found =
        productLookupCache.find("tenant-A", "p-101");
```

Lần đầu có thể truy vấn database rồi cache `VALUE:{...}` với TTL 10 phút. Lần sau đọc positive cache hit.

**Bước 4 — Tạo `p-999` trong nguồn dữ liệu.**

Sau khi commit, gọi:

```java
productLookupCache.invalidate("tenant-A", "p-999");
```

Lần đọc tiếp theo không còn sentinel cũ và được phép tải sản phẩm vừa tạo.

**Bước 5 — Xem hiệu ứng khi bỏ invalidation.**

Nếu để sentinel cũ tồn tại, lần đọc ngay sau khi tạo có thể vẫn trả không tìm thấy cho tới khi negative TTL hết. Đây là lý do TTL và invalidation phải được thiết kế cùng nhau.

**Bước 6 — Mô phỏng request đồng thời.**

Gửi nhiều request cùng một ID chưa có trong Redis. Quan sát số lần database được gọi trước khi request đầu tiên ghi sentinel. Nếu phát sinh nhiều truy vấn đồng thời, cân nhắc singleflight/synchronization phù hợp thay vì nghĩ negative caching tự loại bỏ cache stampede.

## 19. Những lỗi thiết kế thường gặp

**Chỉ cache dữ liệu có thật.** Với một ID không tồn tại được hỏi liên tục, mọi request vẫn truy vấn database. Negative caching tạo ra một trạng thái riêng để chặn các truy vấn lặp.

**Dùng `null` của Redis để kết luận database không có dữ liệu.** Redis null chỉ là cache miss. Cần hỏi nguồn ít nhất một lần hoặc đọc sentinel đã được ghi từ lần tra trước.

**Dùng `unless = "#result == null"` rồi mong Spring Cache lưu not-found.** Điều kiện này loại bỏ việc cache null. Với negative caching bằng `@Cacheable`, phải cho phép cache null và serializer phù hợp.

**Bật `disableCachingNullValues()` nhưng method trả null cho not-found.** Không phù hợp với chiến lược cache null. Hãy đổi cấu hình hoặc dùng wrapper/sentinel tường minh.

**Không có TTL cho sentinel.** Sản phẩm mới tạo có thể tiếp tục bị trả 404 trong thời gian không giới hạn, trừ khi invalidation luôn thành công tuyệt đối.

**Dùng cùng TTL rất dài cho positive và negative.** Kết quả không tồn tại thường có nguy cơ đổi trạng thái khác với dữ liệu đã có; nên cân nhắc TTL riêng.

**Cache DB timeout, lỗi mạng hoặc 403 thành `NOT_FOUND`.** Dễ biến lỗi tạm thời hoặc lỗi phân quyền thành kết quả sai trong nhiều request kế tiếp.

**Chỉ xóa cache khi xóa dữ liệu, quên xóa khi tạo lại hoặc khôi phục.** Negative cache cũng cần invalidation khi dữ liệu bắt đầu tồn tại.

**Tưởng xóa sau commit luôn loại bỏ mọi race.** Một request cũ có thể tra DB trước commit rồi ghi sentinel sau lệnh xóa cache. Cần TTL ngắn hoặc cơ chế versioning khi độ mới nghiêm ngặt.

**Không đưa tenant/user scope vào key.** Có thể trả false negative hoặc dữ liệu sai cho những caller khác nhau.

**Cache mọi ID ngẫu nhiên.** Nếu request không lặp, sentinel chỉ tiêu tốn RAM; cần validation, rate limiting và giới hạn cardinality.

**Tưởng negative caching tự loại bỏ stampede.** Tại thời điểm entry chưa có, nhiều request vẫn có thể cùng truy vấn DB.

**Retry thao tác ghi cache mà không xét lỗi và thứ tự.** Việc ghi sentinel sau request khác đã cập nhật positive cache có thể tạo stale negative. Cần xác định bên nào được quyền ghi và quy tắc đồng bộ.

## 20. Thiết kế theo mức độ cần nhất quán

Có thể phân loại như sau:

| Mức yêu cầu | Ví dụ | Chiến lược đề xuất |
|---|---|---|
| Chấp nhận kết quả cũ vài chục giây | Tra cứu sản phẩm công khai | Negative TTL ngắn, xóa sentinel khi tạo |
| Cần phát hiện bản ghi mới nhanh hơn | Cấu hình vận hành | Negative TTL rất ngắn, chủ động invalidation từ luồng thay đổi |
| Bản ghi có thể được tạo ở nhiều service | Catalog phân tán | Event/outbox để invalidation, TTL làm lớp dự phòng |
| Đọc sau ghi phải nhìn thấy ngay | Quyền sở hữu tài nguyên hoặc thao tác quan trọng | Đọc nguồn nhất quán, versioning hoặc không negative-cache ở luồng bắt buộc |
| ID bị quét ngẫu nhiên quy mô lớn | Public API bị bot gọi | Validation, rate limiting, hạn mức memory; negative cache chỉ hỗ trợ các key lặp |
| “Không thấy” phụ thuộc quyền truy cập | Tài nguyên riêng tư | Scope key theo tenant/user và giữ kiểm tra authorization, hoặc không dùng cache chung |

Không phải ứng dụng nào cũng cần cơ chế khóa hoặc versioning phức tạp. Với dữ liệu cache có thể tái tạo, TTL ngắn cùng invalidation có thể đủ. Khi “trả nhầm 404 sau khi tạo” gây hậu quả nghiêm trọng, cần giải quyết tính nhất quán tại thiết kế hệ thống, không chỉ điều chỉnh TTL.

## 21. Quy trình áp dụng negative caching an toàn

Khi thêm negative caching cho một phương thức tra cứu:

1. **Xác định kết quả “không tồn tại” có đáng tin không.** Chỉ cache sau khi nguồn dữ liệu xác nhận, không gom lỗi hệ thống hoặc lỗi quyền truy cập vào cùng trạng thái.
2. **Thiết kế cache key đầy đủ ngữ cảnh.** Bao gồm tenant/resource/version nếu các yếu tố này thay đổi kết quả.
3. **Phân biệt ba trạng thái.** Cache miss, positive hit và negative hit phải có biểu diễn rõ ràng.
4. **Chọn negative TTL theo khả năng tạo dữ liệu mới.** Bắt đầu ngắn, đo tải và độ trễ phản ánh thay đổi.
5. **Thiết kế invalidation trên mọi đường ghi liên quan.** Tạo, khôi phục, import, cập nhật visibility hoặc chuyển tenant có thể làm một kết quả not-found trở thành found.
6. **Kiểm tra race giữa load và invalidation.** Khi cần mạnh hơn eventual consistency, dùng version/sequence hoặc nguồn đọc phù hợp.
7. **Đặt giới hạn cho lưu lượng ID không hợp lệ.** Negative cache không giải quyết hiệu quả bot gửi vô số ID duy nhất.
8. **Đo negative hit riêng.** Theo dõi database queries tránh được, memory, stale 404 và cache errors.
9. **Chuẩn bị đường fallback khi Redis lỗi.** Không trả 404 chỉ vì cache server không phản hồi.
10. **Tôn trọng tính chất cache.** Key có thể hết hạn/evict sớm; request phải xử lý được việc quay lại nguồn dữ liệu.

## 22. Kết luận

**Cache dữ liệu không tồn tại** là một phần của chiến lược cache-aside giúp tránh truy vấn lặp đi lặp lại cho cùng một ID chưa có trong nguồn dữ liệu. Thay vì để Redis luôn báo cache miss rồi truy vấn database, ứng dụng lưu một **negative entry có TTL ngắn** để các lần lookup kế tiếp trả kết quả nhanh từ cache.

Trong Spring Data Redis:

- Với **Spring Cache**, có thể cache `null`/`Optional.empty()` khi `RedisCacheManager` được cấu hình hỗ trợ; không dùng `unless="#result == null"` nếu muốn lưu kết quả null.
- Với **`StringRedisTemplate`**, sentinel `NOT_FOUND` giúp phân biệt rõ negative hit với cache miss và cho phép TTL khác nhau giữa positive/negative entry.
- **TTL ngắn và invalidation sau khi tạo dữ liệu** là hai thành phần quan trọng để tránh giữ kết quả 404 cũ quá lâu.
- **Race condition, replica lag, phân quyền và lỗi hệ thống** có thể làm một kết luận “không thấy” trở nên sai; phải xử lý theo yêu cầu nhất quán của nghiệp vụ.
- **Cache penetration** do cùng một ID bị hỏi lặp là trường hợp negative caching phát huy tác dụng mạnh. Với ID ngẫu nhiên hàng loạt hoặc cache stampede ban đầu, cần kết hợp validation, rate limiting và điều phối request.

Thiết kế đúng không chỉ nhằm tăng hit ratio mà còn bảo đảm rằng **kết quả không tồn tại được cache trong đúng phạm vi, đúng thời hạn và có thể bị vô hiệu khi sự thật thay đổi**.
