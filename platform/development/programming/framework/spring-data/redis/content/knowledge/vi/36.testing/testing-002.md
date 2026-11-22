# Mock tại ranh giới dịch vụ thay vì mô phỏng toàn bộ Redis trong Spring Data Redis

## 1. Vấn đề: giả lập Redis càng sâu, test càng dễ tạo cảm giác an toàn giả

Một ứng dụng Spring Boot dùng Spring Data Redis để cache dữ liệu, lưu OTP, giới hạn số lần đăng nhập hoặc giữ trạng thái tạm. Khi viết unit test, lập trình viên có thể thử mock mọi lớp bên dưới:

~~~text
BusinessService
     |
     v
RedisTemplate
     |
     v
ValueOperations / HashOperations / RedisConnection
     |
     v
Lettuce / Jedis / Serializer
     |
     v
Redis server
~~~

Ví dụ:

~~~java
@Mock
RedisTemplate<String, String> redisTemplate;

@Mock
ValueOperations<String, String> operations;

@BeforeEach
void setUp() {
    when(redisTemplate.opsForValue())
        .thenReturn(operations);
}

@Test
void readsFromRedis() {
    when(operations.get("products:v1:p-42"))
        .thenReturn("{\"id\":\"p-42\"}");
    // ...
}
~~~

Một test như vậy có thể hữu ích với lớp adapter hẹp. Nhưng nếu *business service* phải biết Redis key, serializer, command names, TTL và connection mechanics thì test đang bị ràng buộc vào cách triển khai thay vì mục tiêu nghiệp vụ.

Nguy hiểm hơn, Mockito có thể trả `true` hai lần cho `setIfAbsent` trên cùng key dù Redis `SET NX` thực xử lý điều kiện tồn tại theo cách nguyên tử. Mock cũng không tự có TTL, replication lag, Redis Cluster slots, network failure hay behavior của Lua.

**Nguyên tắc:** Unit test chính sách nghiệp vụ bằng mock ở **ranh giới dịch vụ**; kiểm chứng những bảo đảm của Redis bằng **Redis thật** trong integration test.

## 2. Thế nào là ranh giới dịch vụ?

Ranh giới dịch vụ là một hợp đồng mà business layer cần dùng để thực hiện mục tiêu, chẳng hạn:

~~~java
public interface ProductCache {
    Optional<ProductView> find(String id);
    void put(String id, ProductView snapshot, Duration ttl);
    void evict(String id);
}
~~~

Service chỉ biết ý nghĩa `find`, `put` và `evict`. Nó không cần biết:

- Redis key được ghép prefix ra sao.
- Dùng `StringRedisTemplate`, `RedisTemplate` hay Lua.
- Dùng Lettuce hay Jedis.
- JSON serializer hoặc key serializer nào được dùng.
- Redis đang chạy standalone, Sentinel hay Cluster.
- Cách reconnect, pool connections và gửi lệnh thấp cấp.

Kiến trúc:

~~~text
                    ProductQueryService
                           |
                    ProductCache port
                           |
                +----------+-----------+
                |                      |
                v                      v
         Mockito mock            RedisProductCache
         (unit test)              (production)
                                         |
                                         v
                                 StringRedisTemplate
                                         |
                                         v
                                       Redis
~~~

Cùng một hợp đồng `ProductCache` có hai đường kiểm thử: mock để test quyết định nghiệp vụ; adapter thật với Redis thật để xác nhận lưu trữ.

Đây là cách vận dụng ports-and-adapters, không phải quy định bắt buộc phải tạo nhiều tầng interface cho mọi chương trình.

## 3. Phân chia trách nhiệm kiểm thử

| Mức test | Điều cần xác minh | Công cụ |
| --- | --- | --- |
| Unit test business service | Cache hit/miss, lỗi, fallback, quyết định nghiệp vụ | JUnit 5 + Mockito |
| Unit test logic thuần | Mapping DTO, key policy, validation, deadline | JUnit 5, không nhất thiết mock |
| Redis adapter integration | Key, TTL, serializer, lệnh Redis, atomicity | Redis thật/Testcontainers |
| Spring integration | `@Cacheable`, `@CacheEvict`, AOP proxy, transaction, event lifecycle | Spring Test + Redis/database |
| Concurrency test | Hai client có thể cùng thực hiện thao tác không? | Redis thật, nhiều connections/threads |
| Fault/system test | Reconnect, failover, Cluster redirects, replication | Redis multi-node topology |

Không dùng một Mockito test để tuyên bố đã kiểm tra toàn bộ Redis. Nhưng cũng không bắt mọi unit test phải khởi chạy Docker khi chỉ kiểm tra một nhánh logic.

## 4. Ví dụ xuyên suốt: ProductQueryService với cache-aside

Giả sử PostgreSQL là nguồn dữ liệu chuẩn, Redis chỉ là bản sao cache.

DTO:

~~~java
package com.example.products;

import java.math.BigDecimal;

public record ProductView(
    String id,
    String name,
    BigDecimal price
) { }
~~~

Repository port:

~~~java
package com.example.products;

import java.util.Optional;

public interface ProductReadRepository {
    Optional<ProductView> findById(String id);
}
~~~

Cache port:

~~~java
package com.example.products;

import java.time.Duration;
import java.util.Optional;

public interface ProductCache {
    Optional<ProductView> find(String id);
    void put(String id, ProductView snapshot, Duration ttl);
    void evict(String id);
}
~~~

Exception nghiệp vụ:

~~~java
package com.example.products;

public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(String id) {
        super("Product not found: " + id);
    }
}
~~~

Hợp đồng này không chứa bất kỳ API nào của Redis; nó cho phép business test bằng mock và Redis adapter test bằng server thật.

## 5. Business service chỉ quyết định cách dùng cache

~~~java
package com.example.products;

import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private static final Duration CACHE_TTL =
        Duration.ofMinutes(5);

    private final ProductReadRepository products;
    private final ProductCache cache;

    public ProductQueryService(
            ProductReadRepository products,
            ProductCache cache) {
        this.products = products;
        this.cache = cache;
    }

    public ProductView findById(String id) {
        return cache.find(id).orElseGet(() -> {
            ProductView product = products.findById(id)
                .orElseThrow(() ->
                    new ProductNotFoundException(id)
                );
            cache.put(id, product, CACHE_TTL);
            return product;
        });
    }
}
~~~

Luồng:

~~~text
getById(id)
    |
    v
cache.find(id)
    |
    +-- HIT -> trả ProductView
    |
    +-- MISS -> products.findById(id)
                    |
                    +-- NOT FOUND -> lỗi nghiệp vụ
                    |
                    +-- FOUND -> cache.put(id, view, 5 phút)
                                       |
                                       v
                                   trả view
~~~

Đây là **policy cache-aside**. Việc sử dụng `GET`, `SET` hay Redis Hash để triển khai port không ảnh hưởng đến định nghĩa policy.

## 6. Mockito unit test: cache hit không gọi database

~~~java
package com.example.products;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ProductQueryServiceTest {

    @Mock ProductReadRepository products;
    @Mock ProductCache cache;

    ProductQueryService service;

    @BeforeEach
    void init() {
        service = new ProductQueryService(products, cache);
    }

    @Test
    void returnsCacheHitWithoutReadingDatabase() {
        ProductView value = new ProductView(
            "p-42",
            "Spring Book",
            new BigDecimal("120000")
        );

        when(cache.find("p-42"))
            .thenReturn(Optional.of(value));

        ProductView actual = service.findById("p-42");

        assertThat(actual).isEqualTo(value);
        verify(cache).find("p-42");
        verifyNoInteractions(products);
        verify(cache, never()).put(
            anyString(),
            any(ProductView.class),
            any(Duration.class)
        );
    }
}
~~~

Điều test **chứng minh**: service dùng snapshot cache khi có sẵn, không đọc repository và không ghi lại snapshot không cần thiết.

Điều test **không chứng minh**: Redis có chứa key, TTL còn hiệu lực, serializer đọc được JSON, Redis connection hoạt động hoặc replica không bị trễ.

## 7. Mockito unit test: cache miss phải nạp dữ liệu

Trong cùng test class:

~~~java
@Test
void loadsDatabaseAndCachesSnapshotOnMiss() {
    ProductView fromDb = new ProductView(
        "p-42", "Spring Book", new BigDecimal("120000")
    );

    when(cache.find("p-42"))
        .thenReturn(Optional.empty());

    when(products.findById("p-42"))
        .thenReturn(Optional.of(fromDb));

    ProductView result = service.findById("p-42");

    assertThat(result).isEqualTo(fromDb);

    verify(products).findById("p-42");
    verify(cache).put(
        "p-42",
        fromDb,
        Duration.ofMinutes(5)
    );
}
~~~

Test này chỉ nói về hợp đồng:

~~~text
Cache miss -> đọc DB -> ghi cache với TTL -> trả snapshot
~~~

Nó sẽ tiếp tục đúng khi implementation chuyển từ JSON string sang Redis Hash hoặc Lua, miễn ranh giới nghiệp vụ không đổi.

Nếu thứ tự là một bất biến cần xác nhận, dùng `InOrder`:

~~~java
InOrder inOrder = inOrder(cache, products);

inOrder.verify(cache).find("p-42");
inOrder.verify(products).findById("p-42");
inOrder.verify(cache).put(
    "p-42", fromDb, Duration.ofMinutes(5)
);
~~~

Không verify thứ tự mọi method nếu thứ tự không ảnh hưởng đến contract.

## 8. Mockito unit test: không tìm thấy sản phẩm

~~~java
@Test
void doesNotCacheMissingProduct() {
    when(cache.find("missing"))
        .thenReturn(Optional.empty());

    when(products.findById("missing"))
        .thenReturn(Optional.empty());

    assertThatThrownBy(
        () -> service.findById("missing")
    )
        .isInstanceOf(ProductNotFoundException.class)
        .hasMessageContaining("missing");

    verify(products).findById("missing");
    verify(cache, never()).put(
        anyString(),
        any(ProductView.class),
        any(Duration.class)
    );
}
~~~

Cần import:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

Contract hiện tại **không negative-cache** trường hợp không có sản phẩm. Nếu muốn cache kết quả âm trong thời gian ngắn, phải thiết kế representation/TTL/invalidation riêng, thay vì mặc định `null` là sản phẩm giả.

## 9. RedisProductCache: nơi thích hợp để gọi Redis API

Adapter dùng `StringRedisTemplate` và Jackson:

~~~java
package com.example.products.redis;

import java.time.Duration;
import java.util.Optional;

import com.example.products.ProductCache;
import com.example.products.ProductView;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisProductCache implements ProductCache {

    private static final String PREFIX = "products:v1:";

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public RedisProductCache(
            StringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    @Override
    public Optional<ProductView> find(String id) {
        String json = redis.opsForValue().get(key(id));

        if (json == null) {
            return Optional.empty();
        }

        try {
            return Optional.of(
                mapper.readValue(json, ProductView.class)
            );
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Invalid cache payload", ex
            );
        }
    }

    @Override
    public void put(
            String id,
            ProductView value,
            Duration ttl) {
        try {
            String json = mapper.writeValueAsString(value);
            redis.opsForValue().set(key(id), json, ttl);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot serialize product", ex
            );
        }
    }

    @Override
    public void evict(String id) {
        redis.delete(key(id));
    }

    private String key(String id) {
        return PREFIX + id;
    }
}
~~~

Adapter chịu trách nhiệm:

- Key prefix `products:v1:`.
- Serialization/deserialize của DTO.
- Mapping Redis cache miss sang `Optional.empty()`.
- Redis TTL khi `put`.
- Deletion khi `evict`.
- Báo lỗi payload không hợp lệ.

Business service không quan tâm các chi tiết trên. Những chi tiết này phải được kiểm tra trong **integration test của adapter**, không phải mọi unit test service.

## 10. Test adapter: khi nào mock RedisTemplate có ích?

Một unit test nhỏ cho adapter có thể mock `StringRedisTemplate` và `ValueOperations` để xác nhận key được ghép đúng:

~~~java
@Mock StringRedisTemplate redis;
@Mock ValueOperations<String, String> operations;

@BeforeEach
void init() {
    when(redis.opsForValue()).thenReturn(operations);
}
~~~

Nhưng cần hiểu nó chỉ kiểm tra **lời gọi theo stub**. Nó không chứng minh:

- JSON được lưu/đọc đúng.
- Redis tạo TTL dương.
- Redis thực trả `null` khi key không tồn tại.
- Prefix được serialize ra Redis bytes phù hợp.
- Redis timeout, connection refused hoặc permission error có kiểu exception nào.
- Redis Cluster có ràng buộc multi-key.

Với adapter tương đối đơn giản, một Redis integration test có thể có giá trị hơn chuỗi mock phức tạp.

**Không có quy tắc “cấm mock RedisTemplate”**; vấn đề là đặt mock ở đúng phạm vi và không phóng đại điều test chứng minh.

## 11. Tách semantics của port khỏi Redis implementation

Một port được thiết kế tốt phải nói rõ các kết quả:

~~~text
ProductCache.find(id)
  HIT                -> Optional.of(snapshot)
  MISS               -> Optional.empty()
  Redis unavailable  -> exception có ý nghĩa
  Payload invalid    -> exception hoặc policy riêng
~~~

Không nên viết adapter như sau:

~~~java
public Optional<ProductView> find(String id) {
    try {
        return readFromRedis(id);
    } catch (Exception ex) {
        return Optional.empty();
    }
}
~~~

vì nó biến mọi lỗi Redis thành cache miss, che giấu outage và dữ liệu corrupt. Nếu fallback xảy ra hàng nghìn lần/giây, database nguồn chuẩn có thể bị quá tải.

Nên định nghĩa loại lỗi riêng, ví dụ:

~~~java
public class CacheUnavailableException
        extends RuntimeException {

    public CacheUnavailableException(Throwable cause) {
        super("Cache unavailable", cause);
    }
}
~~~

Adapter chuyển những lỗi Redis connectivity phù hợp sang loại này. Không tự động bắt tất cả exceptions nếu chưa định nghĩa chính sách của từng nhóm lỗi.

## 12. Fail-open và fail-closed là quyết định nghiệp vụ

**Redis chỉ là cache sản phẩm:** khi unavailable, service có thể đọc database nếu hệ thống chịu được tải fallback.

**Redis là nơi kiểm tra rate limit, OTP hay lock:** khi unavailable, cho tất cả request đi qua có thể nguy hiểm. Có thể phải từ chối thao tác hoặc dùng cơ chế kiểm soát khác.

Service fail-open minh họa:

~~~java
public ProductView findWithFallback(String id) {
    try {
        Optional<ProductView> cached = cache.find(id);

        if (cached.isPresent()) {
            return cached.get();
        }
    } catch (CacheUnavailableException ex) {
        // Trong production: ghi log và metric.
    }

    ProductView fromDb = products.findById(id)
        .orElseThrow(() ->
            new ProductNotFoundException(id)
        );

    try {
        cache.put(id, fromDb, Duration.ofMinutes(5));
    } catch (CacheUnavailableException ex) {
        // Cache là best effort; trả dữ liệu từ nguồn chuẩn.
    }

    return fromDb;
}
~~~

Method trên có thể được đặt trong service và cần log/metric thực tế, thay vì bỏ qua exception im lặng.

Mockito unit test:

~~~java
@Test
void readsDatabaseWhenCacheIsUnavailable() {
    ProductView fromDb = new ProductView(
        "p-42", "Redis Book", new BigDecimal("120000")
    );

    when(cache.find("p-42"))
        .thenThrow(
            new CacheUnavailableException(
                new RuntimeException("Connection refused")
            )
        );

    when(products.findById("p-42"))
        .thenReturn(Optional.of(fromDb));

    ProductView actual =
        service.findWithFallback("p-42");

    assertThat(actual).isEqualTo(fromDb);
    verify(products).findById("p-42");
}
~~~

Test này xác nhận **fallback policy**, không giả lập được thực tế Lettuce reconnect hoặc Redis failover.

## 13. Tránh một interface chỉ đổi tên Redis API

Một abstraction quá chung:

~~~java
public interface KeyValueStore {
    Object get(String key);
    void set(String key, Object value);
    void delete(String key);
}
~~~

có thể khiến business service vẫn thao tác theo lệnh Redis, chỉ thay tên interface.

Ranh giới theo nghiệp vụ thường tốt hơn:

~~~java
public interface OneTimeTokenStore {
    Optional<TokenPayload> consume(String tokenId);
}
~~~

~~~java
public interface LoginAttemptLimiter {
    boolean tryAcquire(
        String accountId,
        int maxAttempts,
        Duration window
    );
}
~~~

~~~java
public interface InventoryReservationGateway {
    ReservationResult tryReserve(
        String orderId,
        String sku,
        int quantity
    );
}
~~~

Các ports này nêu rõ capability: tiêu thụ token, xin quyền đi qua rate limit, giữ hàng. Business unit test có thể mock kết quả `SUCCESS`/`DENIED`; Redis adapter phải triển khai đúng nguyên tử và chịu integration test độc lập.

## 14. OTP: vì sao không được fake GET rồi DEL là atomic?

Một implementation lỗi:

~~~text
GET otp:123
Nếu tồn tại:
    DEL otp:123
    return token
~~~

Hai requests đồng thời:

~~~text
Thread A                     Thread B
--------                     --------
GET -> token                 GET -> token
DEL                          DEL
return token                 return token
~~~

Cả hai có thể sử dụng cùng OTP, trái với quy tắc một lần.

Hợp đồng tốt:

~~~java
public interface OneTimeTokenStore {
    Optional<TokenPayload> consume(String tokenId);
}
~~~

Adapter Redis có thể dùng `GETDEL` (khi Redis/client version hỗ trợ) hoặc Lua script phù hợp để thực hiện tiêu thụ nguyên tử.

Một unit test business service có thể mock:

~~~java
when(tokens.consume("otp-123"))
    .thenReturn(Optional.empty());

VerificationResult result =
    verificationService.verify("otp-123");

assertThat(result.accepted()).isFalse();
~~~

`TokenPayload`, `VerificationResult` và `verificationService` là types của ví dụ OTP riêng cần được triển khai. Mục đích là minh họa cách mock port, không phải một test class độc lập đã có đủ dependency.

**Unit test này không chứng minh Redis adapter nguyên tử.** Cần concurrency integration test.

## 15. Concurrency integration test cho token tiêu thụ một lần

Một test đúng đối với `consume` nên:

1. Tạo token thật trên Redis test, có TTL.
2. Tạo nhiều clients/connections độc lập.
3. Dùng barrier cho các threads bắt đầu đồng thời.
4. Mỗi thread gọi `OneTimeTokenStore.consume(id)`.
5. Đợi tất cả futures hoàn tất với timeout hữu hạn.
6. Đếm số lần consume thành công.
7. Assert **không quá một** request thành công.
8. Xác nhận Redis token không còn.
9. Lặp lại với token/namespace test mới.

Một `Map` fake không tái hiện chính xác Redis `GETDEL`, Lua, replication hay network. Một Mockito stub chọn trước request nào thành công cũng không chứng minh atomicity thật.

## 16. Lua script và state cuối cùng

Ví dụ một script giảm tồn kho đơn key:

~~~lua
local stock = tonumber(
    redis.call('GET', KEYS[1]) or '0'
)
local qty = tonumber(ARGV[1])

if not qty or qty <= 0 then
    return -1
end

if stock < qty then
    return 0
end

redis.call('DECRBY', KEYS[1], qty)
return 1
~~~

Đây là ví dụ minh họa atomic check-and-decrement. Với reservation thực tế, cần thêm idempotency theo order ID, trạng thái reservation và retry policy.

Unit test service có thể mock `InventoryReservationGateway.tryReserve` trả các kết quả. Nhưng Redis integration test cần xác nhận:

- Lệnh script thực chạy trên Redis.
- Input không hợp lệ không gây write.
- Hai clients cạnh tranh không làm tồn kho âm.
- Mã kết quả đúng.
- Serializer và keys/ARGV khớp.
- Redis Cluster keys của script cùng slot nếu cần multi-key.

**Redis Lua atomicity không đồng nghĩa rollback toàn bộ write đã thực hiện trước khi script gặp runtime error.** Đây là chi tiết Redis thật mà mock không thể tự đảm bảo.

## 17. @Cacheable không chạy khi chỉ new object trong unit test

Ví dụ:

~~~java
@Service
public class ProductQueryWithAnnotation {

    private final ProductReadRepository products;

    public ProductQueryWithAnnotation(
            ProductReadRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView findById(String id) {
        return products.findById(id)
            .orElseThrow(() ->
                new ProductNotFoundException(id)
            );
    }
}
~~~

Nếu unit test viết:

~~~java
var service = new ProductQueryWithAnnotation(
    mockRepository
);

service.findById("p-42");
~~~

thì lời gọi này **không đi qua Spring proxy**. Annotation `@Cacheable` không tự được thực thi bởi đối tượng Java mới tạo.

Test phần body method như vậy hoàn toàn hợp lệ nếu chỉ cần logic repository, nhưng **không chứng minh caching**.

Test caching annotation cần:

- Spring context có `@EnableCaching`.
- `CacheManager` đúng.
- Lời gọi qua Spring-managed bean/proxy.
- Kiểm tra lần đọc sau có được cache.
- Kiểm tra key, serializer và TTL nếu Redis là backing store.

## 18. Self-invocation và Spring AOP

Một service:

~~~java
public void refresh(String id) {
    this.findById(id);
}

@Cacheable(cacheNames = "productById")
public ProductView findById(String id) {
    // ...
}
~~~

Trong chế độ Spring proxy thông thường, lời gọi `this.findById` có thể bypass caching advice. Unit test thuần Java không bắt được vấn đề này.

Vì vậy phải tách hai câu hỏi:

- Business logic của `findById` đúng không? → unit test.
- Lời gọi đi qua Spring proxy, sử dụng RedisCacheManager và caching đúng không? → integration test.

Nếu cần dùng `@CacheEvict` và `@CachePut`, nguyên tắc tương tự.

## 19. @CacheEvict không chứng minh database đã commit

Giả sử:

~~~java
@Transactional
public void changePrice(String id, BigDecimal price) {
    repository.updatePrice(id, price);
    cache.evict(id);
}
~~~

Mockito có thể xác nhận:

~~~java
verify(repository).updatePrice("p-42", newPrice);
verify(cache).evict("p-42");
~~~

Nhưng nó **không chứng minh** eviction chỉ diễn ra sau database commit. Method có thể return rồi transaction rollback, hoặc một reader điền giá trị cũ vào Redis sau eviction.

Các test cần tách:

- Unit: service phát lệnh/sự kiện đúng ID.
- DB+Redis integration: transaction commit/rollback và invalidation timing.
- After-commit: `@TransactionalEventListener(AFTER_COMMIT)` chạy đúng.
- Concurrency: reader cache miss cạnh tranh với writer.
- Recovery: ứng dụng chết sau DB commit trước Redis eviction, cần TTL/outbox không?

Mockito không biến database và Redis thành một transaction nguyên tử.

## 20. Fake, mock, stub và spy khác nhau

| Loại test double | Ví dụ | Vai trò |
| --- | --- | --- |
| Stub | `when(cache.find(id)).thenReturn(...)` | Cung cấp response định sẵn |
| Mock | `verify(cache).evict(id)` | Kiểm tra interaction |
| Fake | Cache in-memory với `Map` | Chạy nhiều bước với state đơn giản |
| Spy | Theo dõi một object thật | Quan sát behavior cụ thể, dùng có chủ đích |
| Real dependency | Redis qua Testcontainers | Xác minh contract Redis thật |

Fake in-memory:

~~~java
public class InMemoryProductCache implements ProductCache {

    private final Map<String, ProductView> values =
        new HashMap<>();

    @Override
    public Optional<ProductView> find(String id) {
        return Optional.ofNullable(values.get(id));
    }

    @Override
    public void put(
            String id,
            ProductView value,
            Duration ttl) {
        values.put(id, value);
    }

    @Override
    public void evict(String id) {
        values.remove(id);
    }
}
~~~

Cần imports `Map`, `HashMap`, `Optional` và `Duration`.

Fake này **không thực hiện TTL** và không giống Redis trong concurrency. Nó chỉ giúp kiểm tra business flow có state, không phải kiểm chứng Redis server.

## 21. Clock injection dành cho deadline nghiệp vụ

Để test chính sách hết hạn mà không sleep:

~~~java
import java.time.Clock;
import java.time.Instant;

public class ExpiryPolicy {

    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }
}
~~~

Unit test:

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-13T10:00:00Z"),
    ZoneOffset.UTC
);

ExpiryPolicy policy = new ExpiryPolicy(fixed);

assertThat(
    policy.isExpired(
        Instant.parse("2026-11-13T09:59:59Z")
    )
).isTrue();
~~~

Cần import `ZoneOffset` và AssertJ.

Test này chứng minh **business deadline policy**, không phải Redis TTL. Thay đổi Java clock không làm server Redis thật tiến tới tương lai.

## 22. Redis TTL thật cần integration test

Khi adapter dùng:

~~~java
redis.opsForValue().set(
    "products:v1:p-42",
    json,
    Duration.ofSeconds(120)
);
~~~

Test với Redis thật có thể kiểm tra:

~~~java
Long ttl = redis.getExpire(
    "products:v1:p-42",
    TimeUnit.SECONDS
);

assertThat(ttl).isNotNull();
assertThat(ttl).isGreaterThan(0L);
assertThat(ttl).isLessThanOrEqualTo(120L);
~~~

Cần `java.util.concurrent.TimeUnit`.

Đừng assert đúng `120L` trong mọi môi trường: thời gian trôi và Redis trả TTL theo đơn vị seconds.

Khi kiểm tra expiration, dùng polling với timeout thay vì `Thread.sleep(120000)` rồi đòi callback đúng mili giây. Redis expired event có thể đến muộn so với deadline logic.

## 23. Testcontainers: Redis thật trong CI

Ví dụ integration test Spring Boot:

~~~java
package com.example.products.redis;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;

import com.example.products.ProductCache;
import com.example.products.ProductView;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisProductCacheIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    ProductCache cache;

    @Test
    void storesReadsAndEvictsProduct() {
        ProductView product = new ProductView(
            "p-test-1",
            "Redis Book",
            new BigDecimal("150000")
        );

        cache.put(
            "p-test-1",
            product,
            Duration.ofMinutes(2)
        );

        assertThat(cache.find("p-test-1"))
            .contains(product);

        cache.evict("p-test-1");

        assertThat(cache.find("p-test-1"))
            .isEmpty();
    }
}
~~~

Mẫu này giả định ứng dụng có bean `RedisProductCache`, ObjectMapper và Redis connection auto-configuration. Nếu ứng dụng còn yêu cầu database hoặc các external services khác để startup, test phải cung cấp test dependencies hoặc tạo Spring context hẹp phù hợp.

Với Spring Boot cũ có thể dùng prefix `spring.redis.*` thay vì `spring.data.redis.*`. Chọn đúng version của project.

Một Redis container standalone **không phải Redis Cluster**. Kiểm thử Cluster/Sentinel cần topology nhiều process/nodes thích hợp.

## 24. Những ca Redis adapter nên kiểm tra

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Đọc key chưa tồn tại | `Optional.empty()` |
| Put + get | DTO round-trip đúng |
| Put TTL | TTL dương và tương ứng policy |
| Evict | Key biến mất |
| Put ghi đè | Snapshot mới được đọc |
| Unicode | Không hỏng ký tự |
| BigDecimal | Không làm sai ý nghĩa số tiền |
| JSON không đọc được | Exception/policy rõ |
| Redis unavailable | Lỗi được map phù hợp |
| Schema cache đổi phiên bản | Backward compatibility hoặc namespace version |
| Nhiều instances dùng chung cache | Không lộ dữ liệu giữa tenant |
| Retry sau timeout | Không tạo tác dụng phụ nguy hiểm |

Bảng này kiểm tra **hợp đồng Redis**, không thể thay thế bằng Mockito stubs.

## 25. Serializer là chi tiết cần thử thật

Spring Data Redis có nhiều cách serialize:

- `StringRedisSerializer`.
- Jackson JSON serializer theo version.
- Custom binary serializer.
- Redis Hash mapping.

Vấn đề cần test:

- Type metadata có tương thích giữa các bản release không?
- Java record, enum, Instant, BigDecimal được khôi phục đúng không?
- Key có được serialize thành chuỗi người vận hành tưởng tượng không?
- Value cũ còn được đọc sau đổi schema không?
- Dữ liệu không tin cậy có bị deserialize đa hình thiếu an toàn không?

Một stub như:

~~~java
when(serializer.deserialize(any()))
    .thenReturn(product);
~~~

không chứng minh bytes thật có hợp lệ. Có thể test serializer trực tiếp bằng DTO/bytes thật, rồi test adapter với Redis server để xác nhận toàn tuyến.

## 26. Redis Cluster không thể bị thay bằng HashMap

Redis Cluster chia keys theo **16.384 hash slots**. Multi-key commands, Lua và transactions có những ràng buộc đồng slot.

Ví dụ cùng slot nhờ hash tag:

~~~text
cart:{user-42}:items
cart:{user-42}:total
~~~

Hai keys sau không có bảo đảm cùng slot:

~~~text
cart:user-42:items
stock:sku-99
~~~

Một fake Map không có hash slots, `CROSSSLOT`, `MOVED`, `ASK`, failover hay topology refresh. Nếu adapter production dùng Cluster, integration test phải chạy một Redis Cluster thật khi cần kiểm chứng những behavior này.

## 27. Pub/Sub và Streams cũng không thể chứng minh bằng mock handler

Một receiver:

~~~java
public class OrderEventReceiver {
    private final OrderProcessor processor;

    public OrderEventReceiver(OrderProcessor processor) {
        this.processor = processor;
    }

    public void receiveMessage(String json) {
        processor.process(json);
    }
}
~~~

Unit test:

~~~java
receiver.receiveMessage("{\"orderId\":\"o-42\"}");

verify(processor).process(
    "{\"orderId\":\"o-42\"}"
);
~~~

Chỉ chứng minh receiver chuyển payload đúng. Không chứng minh:

- `RedisMessageListenerContainer` đã subscribe.
- Adapter có serializer phù hợp.
- Redis Pub/Sub có message replay.
- Subscriber offline có bỏ lỡ event không.
- Nhiều pods có xử lý trùng không.

Redis Pub/Sub là at-most-once và không replay cho subscriber offline. Với công việc bắt buộc, cần durable queue/Stream/outbox và idempotency thích hợp.

## 28. Redis failover và replication cần fault test riêng

Những tình huống như:

~~~text
Primary trả OK
Replica chưa nhận write
Primary chết
Replica được promote
Write có thể không tồn tại ở primary mới
~~~

không thể được mô phỏng chính xác bằng việc mock một Redis connection exception.

Tương tự, `READONLY`, `MOVED`, `ASK`, failover qua Sentinel và reconnect của Lettuce cần môi trường nhiều Redis nodes nếu chúng là yêu cầu vận hành quan trọng.

Mockito rất hữu ích để test cách service **xử lý một exception giả định**, nhưng không chứng minh Redis thực tạo exception đó khi nào, client retry thế nào hay dữ liệu nào còn sau failover.

## 29. Test khi Redis lỗi: phân biệt mapping và policy

Giả sử service nhận `CacheUnavailableException` và fallback database.

- **Unit test** mock port ném `CacheUnavailableException`, xác nhận service fallback.
- **Adapter integration test** khiến Redis unreachable hoặc dùng cơ chế fault injection, xác nhận exception thật được map đúng loại.
- **Load test** xác nhận lượng fallback không làm quá tải database.
- **System test** xem reconnect và failover có đưa service về trạng thái bình thường không.

Nếu chỉ có unit test service, không thể biết adapter có thực sự phát đúng exception mà service đang catch hay không.

## 30. Không verify quá nhiều implementation details

Một test brittle có thể:

~~~java
verify(cache, times(1)).find(id);
verify(products, times(1)).findById(id);
verify(cache, times(1)).put(id, snapshot, ttl);
verifyNoMoreInteractions(cache, products);
~~~

Điều này đôi khi phù hợp nhưng không nên áp dụng máy móc.

Nên ưu tiên:

1. Assert kết quả caller quan tâm.
2. Verify những side effects quan trọng.
3. Verify “không gọi DB khi cache hit” vì đó là một invariant về hiệu năng.
4. Verify thứ tự/count chỉ khi cần.
5. Không verify từng getter, logger, serializer internal của service.
6. Dùng `ArgumentCaptor` khi service biến đổi payload cần được xác nhận.

Ví dụ captor:

~~~java
ArgumentCaptor<ProductView> captor =
    ArgumentCaptor.forClass(ProductView.class);

verify(cache).put(
    eq("p-42"),
    captor.capture(),
    eq(Duration.ofMinutes(5))
);

assertThat(captor.getValue().price())
    .isEqualByComparingTo("120000");
~~~

Nếu service chỉ truyền nguyên snapshot từ repository, có thể verify trực tiếp expected object thay vì dùng captor.

## 31. Cô lập Redis integration test

Để tránh test ảnh hưởng nhau:

- Dùng key prefix riêng và ID ngẫu nhiên cho từng test.
- Xóa key đã tạo khi hoàn tất.
- Không chạy `FLUSHALL` trên một Redis dùng chung ngoài môi trường test.
- Tránh các tests song song cùng key.
- Pin Redis image version cho CI khi cần khả năng tái lập.
- Không trỏ test tới production Redis theo default configuration.
- Trong Spring context được cache, nhớ rằng Redis container có thể còn dữ liệu từ test khác.
- Với Cluster, cleanup phải hiểu phạm vi từng shard.

Một integration test có key duy nhất sẽ ít flaky hơn test dựa trên thứ tự thực thi.

## 32. Test matrix tổng hợp

| Yêu cầu | Mock port unit | Redis thật | Spring context | Multi-node/fault |
| --- | --- | --- | --- | --- |
| Cache hit bỏ qua DB | Có | Không bắt buộc | Nếu dùng annotation | Không |
| Cache miss ghi snapshot | Có | Có để test value/TTL | Có thể | Không |
| TTL dương | Chỉ verify Duration | Có | Có thể | Không |
| Serialize DTO | Không | Có | Có thể | Không |
| Redis `SET NX` atomic | Không đủ | Có, concurrency | Không bắt buộc | Có thể |
| Lua reserve stock | Chỉ kiểm tra result mapping | Có, concurrency | Có thể | Có thể |
| `@Cacheable`/proxy | Không | Có thể | Có | Không |
| Evict sau DB commit | Chỉ ý định/event | Có thể | Có với DB | Có thể |
| Pub/Sub message delivery | Chỉ receiver logic | Có | Có | Có với reconnect |
| Redis Cluster slot constraints | Không | Cluster thật | Có thể | Có |
| Sentinel failover | Không | Không bằng standalone | Không đủ | Có |
| Fallback khi Redis outage | Có | Test exception mapping | Có thể | Load/fault test |

## 33. Tổ chức source và tests

~~~text
src/main/java/com/example/products/
├── domain/
│   ├── ProductView.java
│   ├── ProductReadRepository.java
│   └── ProductCache.java
├── application/
│   └── ProductQueryService.java
├── infrastructure/
│   ├── redis/
│   │   └── RedisProductCache.java
│   └── jpa/
│       └── JpaProductRepositoryAdapter.java
└── web/
    └── ProductController.java

src/test/java/com/example/products/
├── application/
│   └── ProductQueryServiceTest.java
└── infrastructure/redis/
    └── RedisProductCacheIntegrationTest.java
~~~

Không cần máy móc theo đúng cây thư mục này. Điều quan trọng là business layer phụ thuộc **hợp đồng có nghĩa**, còn Redis API tập trung ở adapter để có thể kiểm tra theo lớp.

## 34. Các ngộ nhận thường gặp

**“Mock RedisTemplate càng nhiều nghĩa là unit test càng chính xác.”** Không. Bạn chỉ có nhiều stubs hơn; nếu mô phỏng sai Redis semantics, test vẫn xanh nhưng ứng dụng lỗi.

**“Fake HashMap giống Redis cho mọi test.”** Không. Nó thiếu TTL, serialization, concurrency semantics, network, Cluster, replication và failover.

**“Mockito verify cache.put là chứng minh TTL.”** Không. Chỉ chứng minh service truyền một `Duration`, không chứng minh Redis đặt hạn cho key.

**“Unit test tự new service có `@Cacheable` sẽ dùng cache.”** Không. Spring AOP proxy không tự xuất hiện trong object được tạo thủ công.

**“Mock GET rồi DEL chứng minh OTP một lần.”** Không. Hai lệnh riêng có race; cần command atomic và Redis concurrency test.

**“Redis connection exception mock đủ để kiểm thử failover.”** Không. Test chỉ xác minh error branch, không kiểm thử election, promotion, routing hay reconnect thực.

**“Mọi Redis outage có thể coi là cache miss.”** Không. Redis có thể là nguồn có thẩm quyền cho lock, token hoặc rate limiter; fail-open sai có thể gây lỗi nghiệp vụ.

**“Đã có Redis integration test nên không cần unit test.”** Không. Unit tests nhanh, làm rõ policies; integration tests tập trung vào Redis contract và Spring wiring.

**“Một Redis container là Redis Cluster.”** Không. Cluster có hash slots và topology nhiều nodes.

**“Càng verify nhiều method gọi nội bộ càng an toàn.”** Không. Verify quá nhiều dễ làm test brittle và khó refactor.

## 35. Bài tập A: refactor service đang dùng RedisTemplate

Một service hiện gọi:

~~~java
String json =
    redis.opsForValue().get("products:v1:" + id);

redis.opsForValue().set(
    "products:v1:" + id,
    json,
    Duration.ofMinutes(5)
);
~~~

Hãy:

1. Tạo `ProductCache` có `find/put/evict`.
2. Chuyển key format và JSON vào `RedisProductCache`.
3. Cho service chỉ phụ thuộc port.
4. Viết unit tests cache hit, miss, not-found.
5. Viết integration test key, serializer, TTL và deletion.
6. Giải thích vì sao đổi serializer không làm các business unit tests bị thay đổi.

## 36. Bài tập B: one-time token và concurrency

Hãy thiết kế `OneTimeTokenStore.consume`:

1. Unit test service khi port trả token hoặc empty.
2. Redis adapter dùng atomic operation phù hợp.
3. Tạo nhiều requests cùng token.
4. Assert tối đa một request thành công.
5. Kiểm tra token đã bị tiêu thụ.
6. Thử Redis timeout và giải thích vì sao kết quả có thể không rõ.
7. Xác định idempotency nếu response bị mất sau khi token đã consume.

## 37. Bài tập C: Spring Cache annotation

Với method `@Cacheable`:

1. Unit test logic method qua object thuần Java.
2. Spring integration test qua bean/proxy.
3. Gọi hai lần cùng key, xác nhận cache hit.
4. Evict đúng key rồi đọc lại.
5. Kiểm tra self-invocation có bypass advice không.
6. Nếu cần invalidation sau commit, dùng transaction integration test thay vì mock transaction.

## 38. Bài tập D: cache failure và rate-limit failure

Tạo hai ports:

- `ProductCache`: cache hit/miss, có thể fallback database.
- `LoginAttemptLimiter`: quyết định cho phép login, không mặc định fail-open khi Redis lỗi.

Hãy:

1. Định nghĩa exception contract.
2. Unit test các nhánh lỗi qua mock port.
3. Integration test Redis outage mapping.
4. Xác định metric/fallback/circuit breaker.
5. Đánh giá ảnh hưởng của Redis outage tới database và an ninh.

## 39. Câu hỏi thường gặp

**Có nên cấm mock RedisTemplate hoàn toàn không?**

Không. Mock Redis API có thể hợp lý trong một test adapter nhỏ. Điều cần tránh là làm business service phụ thuộc mọi chi tiết Redis, rồi coi mock framework là Redis server.

**Khi nào nên tạo interface riêng?**

Khi một capability có semantics nghiệp vụ, ranh giới lỗi/atomicity đáng xác định, hoặc giúp cô lập hạ tầng. Không tạo interfaces không cần thiết cho mỗi method một cách máy móc.

**Unit test có kiểm tra được TTL không?**

Chỉ kiểm tra service yêu cầu TTL nào. Việc Redis thật tạo và thực thi TTL thuộc integration test.

**Mock port `consume` có chứng minh token chỉ dùng một lần không?**

Không. Nó cho phép test chính sách service. Redis adapter cần concurrency test trên server thật.

**Tại sao test `@Cacheable` cần Spring context?**

Vì cache annotation thường hoạt động qua Spring AOP proxy. Gọi object tạo bằng `new` không đi qua proxy.

**Redis failover có thể test bằng Mockito không?**

Có thể test phản ứng của business code với exception giả định, nhưng không chứng minh failover/reconnect thực tế. Cần topology Redis phù hợp và fault test.

**Dùng Redis Testcontainers có làm test chậm không?**

Chậm hơn unit test thuần, nên tách nhóm và chạy ở CI khi phù hợp. Đổi lại, nó kiểm tra những lỗi mock không phát hiện.

**Có nên dùng một fake Map cho toàn bộ suite không?**

Chỉ cho những flow không phụ thuộc TTL, nguyên tử hoặc Redis behavior. Fake phải nêu rõ giới hạn.

**Nếu cache miss và Redis lỗi đều trả empty thì sao?**

Service không phân biệt được trường hợp bình thường và outage, dễ tạo fallback không kiểm soát. Nên có error contract rõ.

**Có thể bỏ Redis integration test nếu chỉ cache dữ liệu không quan trọng không?**

Quyết định dựa trên rủi ro, nhưng ngay cả cache đơn giản vẫn có các lỗi key/serializer/TTL đáng kiểm chứng. Không cần mô phỏng Redis để tránh những test đó.

## 40. Ghi nhớ

- **Unit test business service mock ports** như `ProductCache`, `OneTimeTokenStore`, `InventoryReservationGateway` hoặc repository.
- **Không giả lập toàn bộ Redis** bằng Mockito rồi tin đó là bảo đảm về TTL, Lua, atomicity, replication hoặc failover.
- **Redis adapter** chịu trách nhiệm key prefix, serializer, Redis commands, TTL và error mapping.
- **Integration test trên Redis thật** kiểm chứng semantics do Redis cung cấp.
- **Spring integration test** kiểm tra annotation, AOP proxy, transaction và caching lifecycle.
- **Concurrency/fault tests** xác minh race, Cluster/Sentinel và retry theo yêu cầu hệ thống.
- **Mock tại boundary giúp test ít brittle**, vì thay đổi Redis implementation không làm policy service đổi.
- **Hợp đồng lỗi phải rõ**: cache miss khác Redis unavailable; fail-open/fail-closed phụ thuộc vai trò nguồn chuẩn.

Mục tiêu không phải tối đa hóa số lượng mocks hay loại bỏ mọi integration test. Mục tiêu là **kiểm tra từng bảo đảm ở lớp thực sự cung cấp bảo đảm đó**: logic nghiệp vụ bằng unit tests, Redis semantics bằng Redis thật và behavior phân tán bằng topology/fault tests tương ứng.

## Tài liệu tham khảo

- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis – Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html)
- [Spring Data Redis – Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework – Testing](https://docs.spring.io/spring-framework/reference/testing.html)
- [Mockito – Official Documentation](https://site.mockito.org/)
- [JUnit 5 – User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers for Java – Documentation](https://java.testcontainers.org/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – GETDEL](https://redis.io/docs/latest/commands/getdel/)
- [Redis – EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis – Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
