# TTL, dữ liệu cũ và phối hợp vô hiệu hóa cache sau giao dịch

## 1. Vì sao cache trở thành bài toán nhất quán dữ liệu?

Trong **Spring Boot Integration**, cache thường nằm giữa API và các nguồn dữ liệu như PostgreSQL, MySQL, dịch vụ HTTP, Redis hoặc một read model nhận sự kiện từ broker. Cache giúp giảm số lần truy vấn và thời gian phản hồi, nhưng cùng lúc tạo thêm **một bản sao của dữ liệu**. Khi nguồn chính thay đổi, bản sao này có thể đã cũ.

Giả sử dịch vụ Catalog trả thông tin sản phẩm `P-101`:

1. Client đọc sản phẩm; ứng dụng lưu tên và giá vào Redis trong 60 giây.
2. Nhân viên đổi giá từ 100.000 đồng thành 120.000 đồng trong transaction của database.
3. Database commit thành công, nhưng Redis vẫn còn giá 100.000 đồng.
4. Client khác gọi API trong khoảng này và có thể nhận giá cũ.

Chọn **TTL** ngắn hơn có thể giảm khoảng tồn tại của dữ liệu cũ, nhưng không bảo đảm dữ liệu luôn mới; chỉ gọi `@CacheEvict` ở cuối một phương thức `@Transactional` cũng chưa đủ nếu không hiểu **thứ tự commit, advice và các trường hợp lỗi**.

Bài học tập trung vào ba quyết định gắn chặt với nhau: **dữ liệu được phép cũ bao lâu**, **khi nào cache phải bị vô hiệu hóa**, và **làm thế nào không để lỗi/race condition tạo ra dữ liệu sai sau khi database đã commit**.

~~~mermaid
flowchart LR
    API["Client"] --> Q["Spring Boot Query Service"]
    Q --> C[("Redis cache")]
    C -->|"hit"| Q
    Q -->|"miss"| DB[("Database: nguồn sự thật")]
    DB --> Q
    Q -->|"cache kết quả"| C
    CMD["Command Service"] -->|"transaction update"| DB
    CMD -. "sau commit: evict" .-> C
~~~

Trong sơ đồ, Redis chỉ là cache cho dữ liệu đọc; **database là nguồn sự thật**. Nếu phần đọc có yêu cầu khác (ví dụ số dư thanh toán, quyền truy cập, lượng hàng có thể bán), không nên mặc định cho phép dùng dữ liệu cũ chỉ vì cache giúp truy vấn nhanh.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Ý nghĩa | Hậu quả cần đánh giá |
| --- | --- | --- |
| **TTL (time to live)** | Thời gian một entry được giữ trước khi hết hạn theo chính sách cache. | Entry có thể cũ trong khoảng này nếu không bị evict/update. |
| **Expiration** | Cơ chế cache coi entry hết hạn và không còn phục vụ ở lần đọc phù hợp. | Không đồng nghĩa dữ liệu đã được refresh. |
| **Stale data** | Giá trị cache không còn khớp với trạng thái được chấp nhận tại nguồn chính. | Có thể trả giá, trạng thái đơn hàng hoặc quyền đã lỗi thời. |
| **Cache hit/miss** | Có/không có entry có thể phục vụ cho khóa. | Hit cao chưa có nghĩa dữ liệu đúng; miss cao chưa chắc hiệu năng kém. |
| **Invalidation/eviction** | Xóa/đánh dấu không còn hợp lệ một hoặc nhiều entry. | Truy vấn tiếp theo phải nạp lại; evict thất bại khiến entry cũ tiếp tục được phục vụ. |
| **Cache-aside** | Ứng dụng đọc cache, miss thì lấy dữ liệu từ nguồn rồi đưa vào cache. | Ứng dụng phải phối hợp việc nạp, cập nhật và vô hiệu hóa. |
| **Write-through** | Cập nhật cache gắn với đường ghi dữ liệu. | Hai hệ thống DB và cache thường **không chung một transaction ACID**. |
| **Read-your-writes** | Sau khi ghi thành công, người ghi phải nhìn thấy thay đổi của chính mình. | Cache cũ, replica lag hoặc invalidation trễ có thể vi phạm. |

**TTL không phải cơ chế xác nhận commit.** Nó là một chính sách vòng đời entry. Trong cache-aside, nếu mất lệnh evict sau khi DB commit, entry thường tồn tại cho đến khi TTL kết thúc; nhưng không thể khẳng định dữ liệu luôn mới trong tối đa `TTL` nếu còn các yếu tố như nạp lại từ replica chậm, nhiều tầng cache, sliding expiration hoặc race condition.

### 2.1. Các cơ chế tính thời gian hết hạn

- **Expire-after-write**: entry hết hạn sau một khoảng kể từ khi ghi/cache refresh. Phù hợp khi cần một thời hạn rõ từ lần nạp.
- **Expire-after-access**: thời hạn có thể được gia hạn mỗi lần truy cập. Một entry “nóng” có thể tồn tại lâu hơn mong đợi nếu nguồn dữ liệu đã thay đổi; không dùng khi yêu cầu giới hạn độ cũ theo lần ghi.
- **Absolute expiration**: hết hạn tại một thời điểm cố định, hữu ích với dữ liệu có chu kỳ thay đổi đã biết.
- **Soft TTL + hard TTL**: sau soft TTL, có thể trả kết quả cũ trong khi refresh nền; hard TTL giới hạn thời điểm không còn phục vụ dữ liệu cũ. Đây là cơ chế **stale-while-revalidate** cần triển khai có chủ đích, không phải hành vi mặc định của `@Cacheable`.

Redis thường dùng TTL theo key; các thư viện cache trong bộ nhớ như Caffeine có nhiều chính sách expiration khác nhau. Phải hiểu đúng loại TTL đang cấu hình ở từng lớp.

## 3. Quyết định mức chấp nhận dữ liệu cũ theo nghiệp vụ

Không nên cấu hình mọi cache trong dự án cùng một TTL chỉ để dễ quản lý. Từng loại dữ liệu cần đánh giá hậu quả khi đọc nhầm trạng thái cũ:

| Loại dữ liệu | Mức chấp nhận dữ liệu cũ (minh họa) | Định hướng |
| --- | --- | --- |
| Nội dung giới thiệu, danh mục ít đổi | Vài phút có thể chấp nhận. | TTL tương đối dài, invalidation khi sửa và chống cache stampede. |
| Giá hiển thị trên trang | Có thể chấp nhận trễ ngắn tùy hợp đồng sản phẩm. | TTL ngắn + evict sau commit; **giá chốt đơn kiểm tra ở nguồn có thẩm quyền**. |
| Trạng thái giao hàng | Có thể cập nhật theo sự kiện và hiển thị thời điểm cuối. | Event invalidation/update, theo dõi độ trễ và trạng thái `PENDING`. |
| Tồn kho còn bán được | Không cho phép bán vượt tồn thực; dữ liệu hiển thị có thể chỉ tham khảo. | Quyết định giữ hàng phải dùng transaction/điều phối tại owner Inventory. |
| Quyền truy cập vừa bị thu hồi | Độ cũ có thể gây lỗi bảo mật. | Không dựa vào cache eventual nếu hợp đồng cần thu hồi tức thời; dùng kiểm tra authoritative hoặc thiết kế revocation riêng. |
| Số dư, thanh toán, hạn mức tín dụng | Giá trị cũ có hậu quả tài chính. | Không coi cache là nguồn quyết định giao dịch; đọc nguồn chính/kiểm soát bằng transaction. |

Các khoảng thời gian chỉ để thảo luận; cần thống nhất **SLO dữ liệu mới**, không suy ra từ công nghệ. Một chỉ tiêu có thể viết: “Sau commit đổi giá, 99,9% truy vấn phải thấy phiên bản mới trong 2 giây”. Để kiểm chứng, phải đo **commit-to-visible latency**, không chỉ đo cache hit ratio.

## 4. Cache-aside và TTL trong Spring Boot

Ví dụ dùng **Java 17+, Spring Boot 3.x, Spring Cache, Spring Data JPA và Redis**. Ứng dụng đọc sản phẩm từ database và cache `ProductView` đã được chuyển thành DTO. Với Maven:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-cache</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
</dependencies>
~~~

Để kết nối tới Redis, cần cấu hình `spring.data.redis.*` (URL/host, TLS, mật khẩu, timeout) theo môi trường; phần này giả định Redis đã được cấu hình và bảo vệ phù hợp. Ví dụ `application.yml`:

~~~yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 60s
      cache-null-values: false
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

Đây là cấu hình **môi trường phát triển**. Trong production, dùng địa chỉ DNS, TLS, cơ chế cấp secret và chính sách retry phù hợp. `time-to-live: 60s` là TTL mặc định của cache Redis trong ví dụ. Có thể đặt TTL khác nhau theo từng cache:

~~~java
package com.example.integration.cache;

import java.time.Duration;
import org.springframework.boot.autoconfigure.cache.RedisCacheManagerBuilderCustomizer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {

    @Bean
    RedisCacheManagerBuilderCustomizer ttlByCache() {
        return builder -> builder.withCacheConfiguration(
                "productById",
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofSeconds(30))
                        .disableCachingNullValues());
    }
}
~~~

Ở đây `productById` có TTL **30 giây**, riêng với cache này. Các cache khác có thể tiếp tục dùng cấu hình Boot mặc định; cần kiểm tra toàn bộ customizer/serializer trong dự án nếu muốn giữ các thuộc tính chung. **TTL không được lựa chọn chỉ theo nhu cầu giảm tải**: hãy xác định giới hạn đọc dữ liệu cũ được chấp nhận trước, rồi đo hiệu suất với TTL đó.

### 4.1. Query service và cache key

~~~java
// ProductView.java
package com.example.integration.catalog;

import java.io.Serializable;
import java.math.BigDecimal;
import java.util.UUID;

public record ProductView(
        UUID id,
        String name,
        BigDecimal price,
        long version) implements Serializable {}
~~~

~~~java
// ProductQueryService.java
package com.example.integration.catalog;

import java.util.UUID;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productById", key = "#p0")
    @Transactional(readOnly = true)
    public ProductView byId(UUID productId) {
        ProductEntity product = repository.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found: " + productId));
        return new ProductView(
                product.getId(),
                product.getName(),
                product.getPrice(),
                product.getVersion());
    }
}
~~~

Giả định `ProductRepository` mở rộng `JpaRepository<ProductEntity, UUID>` và `ProductEntity` có getter tương ứng; `version` là trường `@Version` trong JPA. Dùng `#p0` để chỉ tham số đầu tiên làm key, tránh phụ thuộc việc compiler giữ tên tham số.

**Các lưu ý thực tế:**

- `@Cacheable` chỉ có hiệu lực khi lời gọi đi qua proxy Spring. Phương thức gọi nội bộ trong cùng class (**self-invocation**) thường bỏ qua cache advice.
- Không cache trực tiếp JPA entity có lazy association hoặc persistence context gắn với transaction. DTO có cấu trúc ổn định, không chứa credential và đủ trường cho consumer, thường dễ quản lý hơn.
- Với RedisCacheManager, định dạng serialize mặc định có thể là Java serialization tùy cấu hình/version. Ví dụ DTO `Serializable` cho phép minh họa hoạt động; production nên chủ động chọn định dạng JSON/serializer có hợp đồng và quản lý tương thích schema. Không deserialize Java object từ dữ liệu không đáng tin.
- Cache key phải chứa mọi yếu tố quyết định kết quả: `tenantId`, locale, currency, quyền/segment nếu có. Nếu cùng key productId được dùng chung giữa tenant, có nguy cơ trả nhầm dữ liệu.
- Không cache null nếu chưa thiết kế **negative caching**: một bản ghi vừa được tạo có thể bị ẩn vì giá trị “không tồn tại” được cache quá lâu.

## 5. Vì sao vô hiệu hóa trước commit là sai?

Tình huống quan trọng nhất xảy ra khi transaction ghi database vẫn chưa commit nhưng cache đã bị xóa:

~~~mermaid
sequenceDiagram
    participant T1 as Giao dịch đổi giá
    participant DB as Database
    participant C as Redis
    participant T2 as Client đọc
    T1->>DB: UPDATE giá 120.000 (chưa commit)
    T1->>C: Evict product P-101 quá sớm
    T2->>C: Cache miss
    T2->>DB: SELECT giá
    DB-->>T2: 100.000 (giá committed cũ)
    T2->>C: Đặt lại cache = 100.000
    T1->>DB: COMMIT giá 120.000
    Note over DB,C: Cache hiện có giá cũ dù transaction đã commit
~~~

Vô hiệu hóa sớm tạo cửa sổ để một request đồng thời **nạp lại giá cũ từ database**. Sau khi T1 commit, nếu không có lần evict khác, cache có thể giữ giá sai tới hết TTL.

**Rollback** tạo một vấn đề khác: phương thức cập nhật xóa cache trước commit rồi cuối cùng rollback; việc xóa này thường chỉ gây cache miss không cần thiết, nhưng nếu cache đã được `@CachePut` bằng giá chưa commit thì client có thể thấy **dữ liệu chưa bao giờ trở thành sự thật**.

Đừng mặc định kết hợp:

~~~java
@Transactional
@CacheEvict(cacheNames = "productById", key = "#p0")
public void changePrice(UUID productId, BigDecimal newPrice) { ... }
~~~

và cho rằng `@CacheEvict` luôn chạy **sau database commit**. Hai annotation tạo các interceptor/advice độc lập; thứ tự bao ngoài giữa caching và transaction advice quyết định thời điểm cache operation xảy ra. Cần chọn **một cơ chế rõ ràng về thứ tự commit** thay vì dựa vào thứ tự proxy tình cờ.

## 6. Vô hiệu hóa sau commit bằng TransactionalEventListener

Với một ứng dụng có transaction Spring/JPA cục bộ, có thể phát sự kiện nội bộ trong transaction và chỉ evict khi transaction thực sự commit:

~~~java
// ProductChanged.java
package com.example.integration.catalog;

import java.util.UUID;

public record ProductChanged(UUID productId) {}
~~~

~~~java
// ProductCommandService.java
package com.example.integration.catalog;

import java.math.BigDecimal;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void changePrice(UUID productId, BigDecimal newPrice) {
        if (newPrice == null || newPrice.signum() < 0) {
            throw new IllegalArgumentException("Price must be non-negative");
        }

        ProductEntity entity = repository.findById(productId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Product not found: " + productId));
        entity.changePrice(newPrice);

        // Đăng ký sự kiện khi transaction còn hoạt động.
        // Listener AFTER_COMMIT chỉ chạy nếu commit thành công.
        events.publishEvent(new ProductChanged(productId));
    }
}
~~~

~~~java
// ProductCacheInvalidator.java
package com.example.integration.cache;

import com.example.integration.catalog.ProductChanged;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {
    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onProductChanged(ProductChanged event) {
        Cache cache = cacheManager.getCache("productById");
        if (cache == null) {
            throw new IllegalStateException("Cache productById not configured");
        }
        cache.evict(event.productId());
    }
}
~~~

Ở đây `ProductEntity.changePrice(...)` chỉ sửa entity managed; JPA dirty checking sẽ flush/commit trong transaction. Cùng một `productId` là cache key khi đọc và khi evict. Sequence mong muốn:

~~~mermaid
sequenceDiagram
    participant App as ProductCommandService
    participant TX as Spring Transaction
    participant DB as Database
    participant Cache as Redis
    App->>TX: @Transactional changePrice
    TX->>DB: UPDATE product
    App->>TX: publishEvent(ProductChanged)
    TX->>DB: Commit
    DB-->>TX: Thành công
    TX->>Cache: AFTER_COMMIT evict(productId)
    Cache-->>TX: Xóa key
    TX-->>App: Hoàn tất
~~~

**Ý nghĩa của `AFTER_COMMIT`:** listener gắn với transaction đang hoạt động, nên không chạy nếu transaction rollback; khi không có transaction, `@TransactionalEventListener` mặc định **không xử lý sự kiện** (`fallbackExecution=false`). Cần bảo đảm mọi đường ghi tương ứng thực sự chạy qua transaction và phát sự kiện đúng lúc.

**Giới hạn của cách làm này:** Sự kiện nội bộ và callback after-commit không phải message queue bền vững. Nếu process chết sau khi DB commit nhưng trước khi evict, hoặc Redis gặp lỗi, database vẫn đã commit nhưng cache có thể cũ. Exception ở callback cũng không thể rollback giao dịch DB đã hoàn tất; hãy giám sát lỗi và phân loại kết quả nghiệp vụ đúng, tránh nói “ghi database thất bại” khi thực tế chỉ cache invalidation thất bại.

Nếu hệ thống dùng `@Async` cho listener, callback có thể chỉ chuyển công việc sang executor sau commit; executor không cung cấp độ bền qua restart. Đừng biến lỗi mất invalidation thành giả định “async sẽ tự retry”.

### 6.1. Transaction-aware cache manager có thể giúp gì?

Spring có `TransactionAwareCacheManagerProxy` và các cache manager hỗ trợ cấu hình transaction-aware. Chúng có thể trì hoãn một số thao tác như `put`, `evict` hoặc `clear` đến **after commit** khi có transaction đồng bộ đang hoạt động. Tuy nhiên, chính sách hỗ trợ phụ thuộc cache manager và cách gọi; không nên mặc định rằng mọi operation, đặc biệt `putIfAbsent` hoặc `evictIfPresent`, đều được defer.

Chọn **một chiến lược nhất quán** cho đường ghi, kiểm tra ordering thực tế và test rollback. Khi có nhu cầu thông báo xuyên service hoặc cần đảm bảo event không mất, listener after-commit cục bộ chỉ là bước đầu, nên xem transactional outbox ở mục tiếp theo.

## 7. Transactional outbox khi invalidation không được phép thất lạc

Trong một luồng gồm nhiều ứng dụng Spring Boot, có thể tồn tại nhiều Redis cache, Caffeine cache tại từng replica hoặc các read model bất đồng bộ. Gửi invalidation bằng lời gọi HTTP/broker **sau DB commit** trực tiếp vẫn có khoảng hở nếu process chết trước khi gửi.

**Transactional outbox** lưu một sự kiện `ProductChanged` **trong cùng transaction database** với thay đổi sản phẩm. Sau commit, một relay đọc outbox và publish event tới Kafka/RabbitMQ hoặc kênh đáng tin cậy. Các consumer xóa cache tương ứng.

~~~sql
BEGIN;

UPDATE products
SET price = :newPrice, version = version + 1
WHERE id = :productId;

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, schema_version, payload_json, created_at
) VALUES (
    :eventId, :productId, 'ProductChanged', 1, :payloadJson, CURRENT_TIMESTAMP
);

COMMIT;
~~~

SQL trên chỉ minh họa named parameters và schema dự kiến, không phải script đầy đủ chạy trực tiếp. Ứng dụng thực tế nên giữ unique constraint, kiểm soát version và dùng transaction manager thích hợp. Sau commit:

~~~mermaid
flowchart LR
    S["Product Service"] -->|"Transaction update + outbox"| DB[("Product DB")]
    DB --> Relay["Outbox relay"]
    Relay --> Broker[("Kafka / RabbitMQ")]
    Broker --> Consumer["Cache invalidation consumer"]
    Consumer --> RC[("Redis / local cache")]
~~~

Cần xử lý rõ:

1. **Outbox record bền vững cùng commit** giúp sự kiện không bị quên khi tiến trình chết giữa ghi DB và publish.
2. Relay có thể phát **trùng** khi broker đã nhận nhưng relay chưa ghi nhận thành công. **Evict cùng một key nhiều lần thường là thao tác idempotent**; consumer vẫn cần theo dõi event ID và lỗi để vận hành.
3. Event có thể **trễ hoặc đảo thứ tự**. Chỉ evict thường an toàn hơn ghi đè cache bằng payload event cũ; nếu dùng event để cập nhật giá trị cache, phải so `version` và dùng phép cập nhật có điều kiện/atomic để tránh áp lại version cũ.
4. Theo dõi `outbox lag`, tuổi sự kiện chưa phát, consumer lag, số lần retry, DLQ và số lần invalidation không thành công.
5. Nếu invalidation hỏng kéo dài, TTL hữu hạn có thể là một **lưới an toàn** để entry tự hết hạn. TTL không thay thế monitor và đối soát.

Outbox chỉ ràng buộc commit **cùng database**, không tạo transaction ACID xuyên DB–Redis–broker. Với nhiều tầng cache, cần xác định chính xác tier nào nhận event và khi nào mỗi tier ngừng phục vụ bản cũ.

## 8. Race condition: đã evict sau commit vẫn có thể ghi lại dữ liệu cũ

Một lỗi tinh vi hơn **cache miss xen giữa commit và invalidation** là một request đọc cũ **đã bắt đầu trước commit**, nhưng lại ghi giá trị cũ vào cache **sau khi invalidation đã xong**:

~~~mermaid
sequenceDiagram
    participant R as Reader A
    participant DB as Database
    participant W as Writer B
    participant C as Redis cache
    R->>C: GET P-101 -> miss
    R->>DB: SELECT -> giá cũ v7
    W->>DB: UPDATE giá mới v8; COMMIT
    W->>C: AFTER_COMMIT evict P-101
    R->>C: SET P-101 = giá cũ v7
    Note over C: Entry cũ được tái tạo sau evict
~~~

Đây là **stale repopulation race**. Dù đã dùng `@TransactionalEventListener(AFTER_COMMIT)` đúng cách, cache vẫn có thể cũ trong TTL còn lại.

### 8.1. Các cách giảm thiểu theo mức yêu cầu

| Cách | Khi dùng | Giới hạn |
| --- | --- | --- |
| **TTL hữu hạn + evict after commit** | Dữ liệu ít thay đổi, cho phép eventual consistency. | Không loại bỏ race; có cửa sổ stale đến hết hạn key. |
| **Version trong value/key** | Dữ liệu có số phiên bản tăng theo owner; cần tránh giá trị cũ ghi đè mới. | Phải có cách xác minh phiên bản mới và fencing/CAS khi ghi cache; chỉ thêm field version không tự loại race. |
| **Atomic compare-and-set khi populate** | Cache dùng chung hỗ trợ script/transaction thao tác nguyên tử. | Cần thiết kế high-watermark theo product và kiểm thử under concurrency. |
| **Coalesce single-flight theo key** | Nhiều miss cùng lúc gây tải DB và ghi lặp. | Giảm stampede; nếu chỉ lock trong một JVM thì không khóa giữa các replica. |
| **Đọc thẳng nguồn authoritative** | Quyết định quan trọng cần latest/serializable semantics. | Chi phí latency/tải cao hơn; cần transaction/lock/optimistic version phù hợp. |
| **Delayed second eviction** | Giảm xác suất stale repopulation trong thực tế. | Heuristic, **không có bảo đảm tuyệt đối** và tạo thêm lưu lượng. |

Một thiết kế nghiêm ngặt có thể dùng **version fence**: khi database commit version `v8`, một watermark ít nhất `v8` được công bố vào hệ thống dùng chung; writer cache chỉ được lưu snapshot có version **không thấp hơn watermark**, bằng phép so sánh và ghi nguyên tử. Tuy nhiên, việc làm watermark đồng bộ với database cũng có failure window nếu không dùng outbox/đối soát. Vì vậy phải xác định rõ SLO và ranh giới bảo đảm, không gọi một mô hình cache-aside đơn giản là “linearizable”.

**Đừng dùng giá trị `updatedAt` đơn thuần làm thứ tự tuyệt đối** khi nhiều writer hoặc đồng hồ khác nhau: timestamp có thể trùng/đảo. Nếu logic cần so thứ tự, dùng phiên bản monotonic do owner tạo và chính sách xử lý version khi nhận sự kiện.

## 9. Multi-level cache, nhiều replica và cache stampede

Một số hệ thống dùng **L1 Caffeine trong mỗi JVM** và **L2 Redis dùng chung**:

~~~text
API -> L1 Caffeine (per instance) -> L2 Redis -> Database
~~~

Nếu chỉ xóa Redis sau commit, L1 của replica khác **không tự bị xóa**. Để giữ đúng freshness:

- Dùng event invalidation/broadcast tới mọi instance L1 hoặc giới hạn TTL L1 đủ ngắn theo hợp đồng.
- Khi instance restart hoặc bỏ lỡ event, cần kế hoạch phục hồi, version check hoặc TTL bảo vệ.
- Nếu publish/subscribe chỉ đẩy đến subscriber online, việc replica offline có thể bỏ lỡ invalidation; không nhầm Pub/Sub không bền vững với queue/log có replay.
- Bảo đảm cache key nhất quán giữa L1 và L2, có prefix môi trường/tenant và chính sách schema version để tránh đọc dữ liệu của bản triển khai trước.

### 9.1. Cache stampede và hot key

Khi một sản phẩm rất phổ biến hết TTL hoặc vừa bị evict, hàng nghìn request có thể đồng loạt cache miss và đánh vào database:

1. Chọn TTL có **jitter có kiểm soát** để nhiều key không hết hạn đồng loạt; jitter không loại stampede trên cùng một hot key.
2. Dùng **single-flight/locking** để chỉ một tác vụ cho mỗi key nạp lại dữ liệu, các request còn lại chờ có giới hạn hoặc nhận fallback theo chính sách.
3. `@Cacheable(sync = true)` có thể giúp gom lời gọi đồng thời theo **khả năng hỗ trợ của cache provider**; cần kiểm chứng vì không mặc định khóa xuyên replica/Redis cluster.
4. Có thể chủ động refresh cache cho hot key, nhưng việc refresh phải đọc nguồn thật và tránh ghi bản cũ sau một cập nhật mới.
5. Giới hạn concurrency và connection pool khi cache bị lỗi hàng loạt, để fallback DB không trở thành thác lũ truy vấn.

**Stale-while-revalidate** chỉ nên dùng khi nghiệp vụ chấp nhận stale. Nếu dữ liệu là giá thanh toán đã chốt, quyền đã thu hồi hoặc số dư, không trả bản cũ chỉ để giảm latency mà bỏ qua ràng buộc.

## 10. Vô hiệu hóa đúng khóa khi thay đổi nhiều loại dữ liệu

Một thay đổi sản phẩm có thể ảnh hưởng tới nhiều cache:

| Thay đổi | Cache cần xét | Rủi ro nếu chỉ evict `productById` |
| --- | --- | --- |
| Đổi tên/giá | `productById`, `productsByCategory`, `searchResults` | Danh sách và kết quả tìm kiếm vẫn còn tên/giá cũ. |
| Tạo sản phẩm mới | Cache danh sách, số lượng theo category | Negative cache hoặc list cache khiến sản phẩm mới chưa hiển thị. |
| Xóa sản phẩm | Cache chi tiết, danh sách, giỏ hàng dẫn xuất | Bản ghi đã xóa vẫn xuất hiện trong danh sách. |
| Chuyển category | Cache danh sách category cũ và mới | Sản phẩm nằm sai category, có thể xuất hiện hai nơi. |
| Đổi quyền/giá theo tenant | Cache có key tenant và chính sách truy cập | Nguy cơ rò dữ liệu nếu key bỏ qua tenant hoặc quyền. |

Spring Cache cung cấp `@CacheEvict(allEntries = true)` để xóa cả region khi cần, nhưng trên cache lớn việc này có thể gây stampede mạnh và chi phí Redis đáng kể. Nên xác định mô hình key/index các entry phụ thuộc, vùng cache độc lập và cách invalidation chính xác. Trường hợp cache danh sách khó evict từng biến thể, có thể dùng **versioned namespace** hoặc chủ động đánh đổi xóa cả region theo một kế hoạch tải phù hợp.

Các thao tác `UPDATE ...` qua bulk JPQL, native SQL, scheduled job, migration hoặc service khác **không tự đi qua `ProductCommandService`**. Nếu chỉ listener của service này evict cache, các đường ghi còn lại có thể để lại giá cũ. Hãy tập trung hợp đồng thay đổi dữ liệu ở owner, phát outbox event cho **mọi** nguồn cập nhật, hoặc dùng CDC có quy tắc dịch sự kiện phù hợp.

## 11. Lỗi Redis và chính sách degraded mode

Redis là cache nhưng vẫn là một dependency vận hành. Spring Cache có thể ném ngoại lệ khi `get`/`put`/`evict` không truy cập được Redis; đừng mặc định cache “tự fail open”:

| Lỗi | Hậu quả | Chính sách cần định nghĩa |
| --- | --- | --- |
| Redis không truy cập được khi đọc | Request có thể thất bại trước khi query DB. | Có cho fallback DB không? Giới hạn tải fallback thế nào? |
| Redis không truy cập được khi `put` | Query DB đúng nhưng ghi cache thất bại. | Có thể trả dữ liệu đọc được hay bắt buộc báo lỗi? |
| Redis không truy cập được sau DB commit lúc `evict` | Database mới, key Redis cũ. | Alert, retry/event bền vững, TTL và đối soát. |
| Cache miss hàng loạt sau restart/flush | Database nhận lưu lượng đột ngột. | Backpressure, warm-up có giới hạn, single-flight và capacity planning. |
| Redis trả value không deserialize được | Thay đổi schema/serializer hoặc dữ liệu hỏng. | Version prefix, bỏ cache sai định dạng, không im lặng chấp nhận dữ liệu lỗi. |

Có thể cấu hình `CacheErrorHandler` để xử lý lỗi get/put/evict theo chính sách cụ thể. Tuy nhiên, “nuốt” lỗi `evict` sau commit rồi không có retry/monitor sẽ biến lỗi cache tạm thời thành **dữ liệu cũ khó phát hiện**. Với dữ liệu quyết định nghiệp vụ, nên chủ động fail closed hoặc đọc nguồn chính khi không bảo đảm freshness.

Khi triển khai Redis Cluster, cần xem routing key, thời điểm failover, replication lag và hành vi đọc từ replica. Nếu đọc dữ liệu cache ở replica chậm hơn master, việc xóa key ở master không nhất thiết được quan sát ngay ở mọi replica; freshness SLO phải tính cả đường đi thực tế.

## 12. Kiểm thử rollback, concurrency và khôi phục

Chỉ viết test `@Cacheable` hit lần hai chưa xác minh được correctness. Bộ kiểm thử nên mô phỏng **đúng thứ tự commit và interleaving**:

| Ca kiểm thử | Kết quả cần chứng minh |
| --- | --- |
| Cache miss, sau đó cache hit | Lần đầu đọc DB, lần hai dùng DTO từ cache theo key mong muốn. |
| TTL hết hạn | Entry bị coi là expired; truy vấn tiếp theo nạp lại từ nguồn. |
| Update và commit thành công | Invalidation diễn ra **sau commit**; lần đọc tiếp theo thấy phiên bản mới. |
| Update rồi rollback | Listener `AFTER_COMMIT` không evict; DB vẫn ở phiên bản cũ. |
| Evict xảy ra trước commit (fault injection) | Test tái hiện nguy cơ nạp lại giá cũ, bảo đảm thiết kế không dựa vào evict sớm. |
| Redis lỗi ngay sau commit | DB đã cập nhật; có tín hiệu lỗi, đường retry/outbox hoặc freshness fallback theo chính sách. |
| Reader đang tải dữ liệu cũ trong lúc writer commit | Phát hiện race stale repopulation; xác minh cơ chế version fence hoặc chấp nhận TTL đã công bố. |
| Hai replica có cache L1 riêng | Invalidation không chỉ dừng ở Redis; các replica tuân thủ freshness SLO. |
| Outbox relay publish trùng | Consumer xóa cache idempotent, không phục hồi dữ liệu cũ từ event trễ. |
| Entity update bằng bulk SQL / writer khác | Mọi đường ghi được theo dõi và phát invalidation phù hợp. |
| Hai tenant có cùng productId | Cache key không làm rò dữ liệu qua tenant. |
| Cache bị flush khi lưu lượng cao | DB không bị quá tải vì stampede hoặc connection exhaustion. |

Với Spring Boot, kiểm thử tích hợp có thể dùng `@SpringBootTest`, Testcontainers cho database/Redis và một số concurrency test có barrier để kiểm soát thứ tự thao tác. Đối với transaction:

1. Khởi tạo sản phẩm v1 và nạp cache.
2. Thực hiện cập nhật trong transaction độc lập, cố ý rollback; chứng minh giá v1 vẫn đúng.
3. Thực hiện cập nhật trong transaction khác và commit; kiểm tra evict và giá v2.
4. Chủ động gây lỗi Redis khi after-commit; kiểm tra trạng thái DB và tín hiệu vận hành.
5. Cho reader A bắt đầu đọc v1 nhưng trì hoãn `put` cho tới sau lúc writer B commit/evict; ghi nhận xem cơ chế xử lý race có đáp ứng hợp đồng không.

Không đặt toàn bộ integration test trong một transaction test tự động rollback rồi mong `@TransactionalEventListener(AFTER_COMMIT)` được gọi: **nếu test rollback thì không có commit để kích hoạt listener**. Sử dụng `TransactionTemplate`/test method không bao transaction mặc định, hoặc chủ động kết thúc transaction trong test khi cần kiểm tra after-commit.

## 13. Observability: đo độ mới, không chỉ đo hit ratio

Metric cache hit cao có thể là dấu hiệu hiệu năng tốt **hoặc** nhiều client liên tục nhận dữ liệu sai. Nên ghi nhận:

- **Hit/miss/eviction/error** theo cache name, operation và kết quả; tránh gắn productId vào label metric vì cardinality cao.
- **Age of cached value** hoặc version khi response được tạo; giúp chẩn đoán độ cũ.
- **Commit-to-invalidation latency** và **commit-to-visible latency**, nhất là khi event đi qua broker.
- **Outbox backlog**, tuổi event chưa phát, số lần redelivery, DLQ và lỗi consumer.
- **Cache stampede**: miss rate đột biến, DB QPS, query latency, Redis timeout và pool saturation.
- **Độ lệch phiên bản**: so `version` trả từ cache với nguồn chính trong một mẫu kiểm tra/đối soát có kiểm soát.

Trace một ca đổi giá có thể nối `productId` trong log nội bộ được phân quyền, `transactionId`/eventId và correlation ID từ HTTP request tới outbox relay/consumer. Đừng gửi giá trị cá nhân nhạy cảm, token, nội dung user riêng hoặc cache key chứa PII trực tiếp vào log/metrics công khai.

Alert cần gắn với hành động: “invalidation thất bại sau commit”, “outbox event chưa phát quá ngưỡng”, “độ trễ đồng bộ vượt SLO” hoặc “cache miss tăng bất thường”. Nếu hoạt động phục hồi chỉ dựa vào TTL, phải có cảnh báo khi thực tế không evict như thiết kế.

## 14. Checklist thiết kế TTL và invalidation

Trước khi bật cache trong production, xác nhận:

- [ ] Dữ liệu nào là **nguồn sự thật** và dữ liệu nào chỉ là bản sao? Tác vụ nào bắt buộc đọc mới nhất?
- [ ] SLO độ mới và cách đo được xác định theo nghiệp vụ; TTL phù hợp loại dữ liệu, không phải một con số chung tùy ý.
- [ ] Cache key bao gồm đầy đủ tenant, locale, currency và các điều kiện phân quyền/tùy biến nếu có.
- [ ] Có cơ chế invalidation sau commit; đã kiểm thử rollback, thứ tự proxy/advice và trường hợp ghi qua đường khác.
- [ ] Đã đánh giá crash window giữa DB commit và Redis evict; dùng outbox nếu cần đảm bảo sự kiện bền vững.
- [ ] Có cách xử lý stale repopulation race, delayed event, multiple replica và cache L1/L2 theo mức nhất quán yêu cầu.
- [ ] TTL, cache stampede, hot key, negative cache và serializer được kiểm soát.
- [ ] Có chính sách Redis failure, fallback DB/backpressure và đối soát khi invalidation thất bại.
- [ ] Có kiểm thử concurrent update/rollback, đo cache lag và cảnh báo lỗi.

Khi xây dựng tích hợp Spring Boot, **TTL** tạo giới hạn vòng đời cho entry, **vô hiệu hóa sau commit** giúp cache phản ánh thay đổi đã thành sự thật, còn **outbox, idempotency, phiên bản và cơ chế đối soát** hỗ trợ duy trì tính nhất quán khi có tiến trình chết, message trùng hoặc các luồng chạy đồng thời. Cache giúp hệ thống nhanh hơn chỉ khi mức dữ liệu cũ được phép đã được xác định rõ và các lỗi cập nhật cache có thể được phát hiện, kiểm thử và phục hồi.
