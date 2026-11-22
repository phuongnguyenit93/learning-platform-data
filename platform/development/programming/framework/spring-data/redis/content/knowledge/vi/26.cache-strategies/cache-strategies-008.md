# Đồng bộ cache với thay đổi dữ liệu bằng sự kiện hoặc outbox trong Spring Data Redis

Trong nhiều ứng dụng Spring Boot, Redis được dùng làm bộ nhớ đệm phía trước cơ sở dữ liệu chính. `@Cacheable` giúp giảm số lần đọc dữ liệu nguồn và cải thiện độ trễ, nhưng làm phát sinh một câu hỏi quan trọng: **khi dữ liệu trong database thay đổi, làm thế nào để những bản sao trong Redis không còn bị sử dụng quá lâu?**

Đặt TTL ngắn là một phần của giải pháp, nhưng không bảo đảm cache được cập nhật ngay sau khi dữ liệu thay đổi. Nếu nghiệp vụ yêu cầu làm mới sớm hơn thời hạn TTL, ứng dụng cần một **chiến lược đồng bộ cache**. Hai hướng thường dùng là:

1. **Phát sự kiện sau khi giao dịch ghi dữ liệu hoàn tất**, sau đó xóa hoặc làm mới cache theo sự kiện.
2. **Transactional outbox**: lưu bản ghi sự kiện vào một bảng outbox trong **cùng giao dịch** với thay đổi dữ liệu, rồi một tiến trình độc lập chuyển sự kiện tới hệ thống thông điệp để các consumer cập nhật cache.

Hai hướng khác nhau chủ yếu ở độ tin cậy khi tiến trình lỗi hoặc mạng gián đoạn. Chúng không biến Redis và SQL thành một giao dịch phân tán có rollback chung. Bài học đi từ cache-aside đơn giản đến giải pháp chịu lỗi có outbox, kèm ví dụ Spring Cache, Spring Data Redis, Spring Transaction và các tình huống dữ liệu cũ có thể quay lại cache.

## 1. Vấn đề: cache hit nhưng dữ liệu đã cũ

Giả sử ứng dụng quản lý sản phẩm:

```text
PostgreSQL (nguồn dữ liệu chính)
  products:
    id   = p-100
    name = "Laptop A"
    price = 1200
    version = 7

Redis (bản sao cache)
  products::p-100:
    {"id":"p-100","name":"Laptop A","price":1200,"version":7}
    TTL = 10 phút
```

Ứng dụng thực hiện một thay đổi trong database:

```sql
UPDATE products
SET price = 1100, version = version + 1
WHERE id = 'p-100';
```

Sau khi commit, database có giá `1100` nhưng Redis vẫn lưu `1200`. Nếu phương thức đọc có:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView findById(String id) {
    return productRepository.findViewById(id);
}
```

thì lần đọc sau có thể là cache hit và **không truy cập database**. Người dùng tiếp tục nhìn thấy giá cũ cho đến khi entry hết hạn hoặc được cập nhật/xóa chủ động.

### Một số khái niệm

| Khái niệm | Ý nghĩa |
|---|---|
| **Source of truth** | Nơi lưu dữ liệu được coi là chuẩn xác, ví dụ PostgreSQL |
| **Cache-aside** | Đọc cache trước; khi miss, đọc DB và ghi kết quả vào cache |
| **Invalidation** | Xóa hoặc đánh dấu một entry cache không còn hợp lệ |
| **Refresh** | Đọc dữ liệu nguồn mới rồi ghi lại vào cache |
| **TTL** | Thời gian sống tối đa tính từ khi một cache entry được ghi hoặc gia hạn |
| **Eventual consistency** | Cache có thể chậm hơn DB, nhưng sẽ hội tụ khi cơ chế đồng bộ hoạt động |
| **Outbox** | Bảng bản ghi sự kiện được lưu cùng transaction với thay đổi dữ liệu |
| **Idempotency** | Xử lý trùng cùng một sự kiện không gây tác động sai lệch |

Với cache có thể tái tạo từ DB, **invalidation** thường là bước khởi đầu an toàn hơn **refresh trực tiếp từ payload sự kiện**. Khi key bị xóa, lần đọc kế tiếp lấy dữ liệu mới từ nguồn; trong khi đó ghi một payload sự kiện cũ vào Redis có thể vô tình ghi đè bản mới hơn.

## 2. Cơ chế cache-aside trong Spring Cache

Luồng đọc:

```text
HTTP GET /products/p-100
          |
          v
@Cacheable("products", key="#id")
          |
       Redis GET
          |
    +-----+-----+
    |           |
  Cache hit   Cache miss
    |           |
    |        Đọc DB
    |           |
    |        Redis SET + TTL
    |           |
    +-----+-----+
          |
          v
    Trả ProductView
```

Đoạn cấu hình đơn giản dùng Redis làm Spring Cache provider:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

```yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
  data:
    redis:
      host: localhost
      port: 6379
```

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

Ví dụ service đọc dữ liệu, giả sử `ProductRepository` cung cấp `findViewById` và `ProductView` là DTO có thể serialize với cache serializer đã cấu hình:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "products", key = "#id",
               unless = "#result == null")
    public ProductView findById(String id) {
        return products.findViewById(id)
                .orElse(null);
    }
}
```

Với tên cache `products` và key logic `p-100`, Redis key thường có dạng `products::p-100`. Tên vật lý có thể khác nếu ứng dụng tùy chỉnh prefix, serializer hoặc key converter.

**Đường ghi dữ liệu** cần phối hợp với chiến lược invalidation. TTL 10 phút chỉ đóng vai trò giới hạn tuổi cache; nó không biết lúc nào database vừa được cập nhật.

## 3. Vì sao xóa cache ngay trước hoặc ngay sau UPDATE có thể sai?

Có thể có ý định đơn giản:

```java
public void changePrice(String id, BigDecimal newPrice) {
    cacheManager.getCache("products").evict(id);
    productRepository.updatePrice(id, newPrice);
}
```

Xóa **trước** khi ghi DB gây nguy cơ:

```text
Writer                      Reader
------                      ------
Xóa Redis key
                            Cache miss
                            Đọc DB -> giá cũ
                            Ghi lại giá cũ vào Redis
Commit giá mới vào DB

Kết quả: DB mới nhưng Redis vẫn cũ.
```

Xóa **sau khi** ghi DB nhưng **trước commit** cũng có thể sai:

```text
Writer (transaction)        Reader
--------------------        ------
UPDATE trong DB
Chưa COMMIT
Xóa Redis key
                            Cache miss
                            Đọc DB ở isolation thông thường
                            -> vẫn thấy dữ liệu đã commit cũ
                            Ghi lại cache cũ
COMMIT DB
```

Vì vậy, nguyên tắc đầu tiên là: **chỉ phát tín hiệu invalidation sau khi transaction ghi dữ liệu đã commit thành công**.

Nhưng ngay cả **xóa sau commit** cũng không loại bỏ mọi race condition. Một reader có thể bắt đầu đọc DB cũ trước commit, rồi ghi giá trị cũ vào Redis **sau** khi writer đã xóa cache. Tình huống này sẽ được giải thích chi tiết ở mục 10.

### Vì sao chỉ dùng @CacheEvict chưa chắc đủ?

```java
@Transactional
@CacheEvict(cacheNames = "products", key = "#id")
public void changePrice(String id, BigDecimal price) {
    productRepository.updatePrice(id, price);
}
```

Code trông hợp lý, nhưng thứ tự thực thi proxy/AOP của cache interceptor và transaction interceptor cần được hiểu rõ. Mặc định `@CacheEvict` thực hiện sau khi method thành công, **không mặc nhiên có nghĩa sau khi database COMMIT** trong mọi cấu hình advice. Không nên lấy thứ tự ngẫu nhiên của các aspect làm bảo đảm nhất quán.

Một cách dễ đọc và chính xác hơn là tạo **event nội bộ**, rồi xử lý tại pha `AFTER_COMMIT` của transaction.

## 4. Hướng 1: sự kiện nội bộ sau commit với Spring

Spring cho phép phát sự kiện trong cùng tiến trình bằng `ApplicationEventPublisher` và đăng ký listener với `@TransactionalEventListener`. Khi dùng `phase = TransactionPhase.AFTER_COMMIT`, listener chỉ xử lý sự kiện gắn với transaction đã commit thành công.

### 4.1. Sơ đồ xử lý

```text
ProductCommandService
      |
      | @Transactional
      v
UPDATE products trong SQL
      |
      v
publishEvent(ProductChanged)
      |
      | Chưa invalidation ngay
      v
COMMIT SQL thành công
      |
      v
@TransactionalEventListener(AFTER_COMMIT)
      |
      v
Cache.evict("p-100")
      |
      v
Lần GET sau: cache miss -> DB mới -> ghi cache mới
```

Nếu transaction rollback, listener `AFTER_COMMIT` **không chạy** cho transaction đó. Điều này tránh xóa cache vì một thay đổi dữ liệu không được commit.

### 4.2. Định nghĩa event

Chỉ cần gửi các thông tin phục vụ invalidation; không nhất thiết đưa toàn bộ entity vào sự kiện:

```java
public record ProductChanged(
        String productId,
        long version
) {
}
```

`productId` cho consumer biết cần xử lý cache entry nào. `version` hữu ích nếu sau này cần lọc sự kiện cũ, so sánh phiên bản hoặc xử lý đồng bộ phức tạp hơn; phiên bản phải xuất phát từ **nguồn dữ liệu chính** chứ không tự tăng trong listener Redis.

### 4.3. Phát sự kiện trong transaction cập nhật dữ liệu

Ví dụ dùng JPA, giả sử `ProductJpaEntity` có phương thức `changePrice`, trường `@Version` và `ProductRepository` là JPA repository:

```java
import java.math.BigDecimal;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    private final ProductRepository products;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository products,
            ApplicationEventPublisher events
    ) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void changePrice(String id, BigDecimal newPrice) {
        ProductJpaEntity product = products.findById(id)
                .orElseThrow();

        product.changePrice(newPrice);
        products.saveAndFlush(product);

        events.publishEvent(new ProductChanged(
                product.getId(),
                product.getVersion()
        ));
    }
}
```

`saveAndFlush` giúp thực hiện lệnh SQL để cập nhật phiên bản trước khi tạo event, nhưng **flush không phải commit**. Transaction vẫn có thể rollback sau khi sự kiện đã được phát vào cơ chế sự kiện nội bộ. `@TransactionalEventListener(AFTER_COMMIT)` chính là lớp bảo vệ để không invalidation trước commit.

Tùy cơ chế versioning, tránh suy đoán rằng `product.getVersion()` đã tăng ngay sau khi gọi setter nếu chưa flush. Cần dùng một phiên bản từ cập nhật dữ liệu đã được ORM/DB xác nhận.

### 4.4. Xóa cache bằng CacheManager trong listener

```java
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
    public void afterProductChanged(ProductChanged event) {
        Cache cache = cacheManager.getCache("products");
        if (cache == null) {
            throw new IllegalStateException(
                    "Cache 'products' is not configured");
        }
        cache.evict(event.productId());
    }
}
```

Ở đây, `cache.evict(event.productId())` sử dụng **key logic** mà Spring Cache dùng cho `@Cacheable(cacheNames = "products", key = "#id")`. Không phải tự ghép chuỗi `"products::"` và gửi `DEL`: để `CacheManager` xử lý namespace, serializer và các cấu hình liên quan.

Nếu một phương thức dùng `key = "#tenantId + ':' + #id"`, listener cũng phải tạo **đúng cùng key logic**; chỉ evict theo ID sẽ không xóa đúng entry.

### 4.5. Điểm mạnh và giới hạn

**Điểm mạnh:**

- Code gọn, không cần message broker hoặc bảng outbox.
- Tránh xóa cache vì transaction bị rollback.
- Phù hợp ứng dụng một tiến trình hoặc hạ tầng Redis cache dùng chung khi dữ liệu ghi đi qua cùng service phát event.
- Dùng `CacheManager` nên không phải biết Redis key vật lý.

**Giới hạn quan trọng:** `ApplicationEventPublisher` không phải hàng đợi lưu bền. Nếu tiến trình crash **sau khi SQL commit nhưng trước khi listener evict Redis**, sự kiện nội bộ có thể mất vĩnh viễn. Nếu Redis không sẵn sàng lúc listener chạy, không có cơ chế durable retry mặc định.

Với listener `AFTER_COMMIT`, việc xóa cache bị lỗi **không thể rollback transaction SQL đã commit**. Ứng dụng cần ghi nhận lỗi, giám sát và khôi phục; không được diễn giải một exception trong listener như bằng chứng DB đã rollback.

Ngoài ra, `@TransactionalEventListener` mặc định chỉ hoạt động nếu sự kiện được phát trong **một transaction đang hoạt động**. Khi không có transaction, listener thường không được gọi trừ khi bật `fallbackExecution = true`; bật fallback phải được cân nhắc vì làm thay đổi ý nghĩa “sau commit”.

## 5. Khi nào sự kiện nội bộ chưa đủ?

Giả sử quy trình sau:

```text
T1: Ứng dụng commit UPDATE products.price = 1100
T2: Tiến trình bị tắt đột ngột
T3: AFTER_COMMIT listener chưa kịp xóa products::p-100
T4: Redis vẫn chứa price = 1200
```

Vì event chỉ ở trong bộ nhớ tiến trình, sau khi khởi động lại không có thông tin chắc chắn “product p-100 đã thay đổi và cache cần xóa”. TTL cuối cùng có thể khiến key hết hạn, nhưng nếu TTL dài, dữ liệu cũ có thể được phục vụ lâu hơn mong muốn.

Tương tự, nếu có nhiều ứng dụng cùng ghi PostgreSQL — một monolith Java, một import job và một dịch vụ quản trị — chỉ phát sự kiện nội bộ ở một nơi sẽ **không** bao quát các đường cập nhật khác.

Nếu thay đổi dữ liệu cần được phát lại đáng tin cậy, hãy lưu **ý định phát sự kiện** vào một nơi bền vững cùng với transaction cập nhật dữ liệu nguồn.

## 6. Hướng 2: Transactional Outbox

**Transactional outbox** là mẫu thiết kế ghi hai loại dữ liệu trong **cùng một transaction SQL**:

1. Trạng thái nghiệp vụ mới, ví dụ giá sản phẩm.
2. Bản ghi outbox mô tả sự kiện cần phát, ví dụ `PRODUCT_CHANGED` cho `p-100`.

Sau commit, một **outbox relay** (poller hoặc CDC connector) đọc các bản ghi outbox và chuyển sang message broker. Cache invalidation consumer nhận event rồi xóa Redis key.

### 6.1. Sơ đồ đầy đủ

```text
                  Transaction SQL
          +--------------------------------+
Command   |                                |
Service --+--> UPDATE products             |
          |           +                    |
          |      INSERT outbox_events      |
          |                                |
          +---------- COMMIT --------------+
                       |
                       v
              Outbox row đã bền vững
                       |
                       v
             Outbox relay / CDC
                       |
                       v
            Durable broker / stream
                       |
                       v
              Cache invalidator
                       |
                       v
              RedisCache.evict(id)
                       |
                       v
          Lần đọc tiếp theo nạp từ DB
```

Nếu transaction SQL rollback, **cả thay đổi product lẫn outbox row đều rollback**. Nếu SQL commit rồi ứng dụng crash trước khi phát message, **outbox row vẫn tồn tại**, nên relay có thể phát lại khi hệ thống hoạt động.

Outbox không bắt Redis và SQL commit đồng thời. Nó **loại bỏ khoảng trống có thể mất sự kiện** giữa việc ghi dữ liệu nguồn và lưu ý định thông báo, với điều kiện tất cả đường ghi được thiết kế sử dụng cùng transaction và relay có cơ chế retry.

### 6.2. Tại sao không trực tiếp cập nhật database và publish broker trong một method?

Ví dụ:

```text
UPDATE product
PUBLISH event
COMMIT SQL
```

Nếu broker nhận event nhưng SQL rollback, consumer xóa cache dù dữ liệu chưa thay đổi. Xóa thừa có thể được chấp nhận, nhưng event “đã thay đổi” là thông tin sai cho consumer khác.

Đổi thành:

```text
UPDATE product
COMMIT SQL
PUBLISH event
```

Nếu tiến trình crash giữa `COMMIT` và `PUBLISH`, sự kiện bị mất. Đây là **dual-write problem**: không có một transaction chung mặc định để đảm bảo atomic commit giữa SQL và broker/Redis.

Outbox chuyển bài toán “ghi database + gửi broker” thành “ghi **hai hàng trong cùng database transaction**”, sau đó giải quyết gửi message theo mô hình retry/idempotency.

## 7. Thiết kế bảng outbox

Ví dụ schema PostgreSQL tối giản:

```sql
CREATE TABLE products (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(15, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(60) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ NULL,
    claim_token UUID NULL,
    claimed_until TIMESTAMPTZ NULL
);

CREATE INDEX outbox_unpublished_idx
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
```

Ý nghĩa các cột:

| Cột | Mục đích |
|---|---|
| `event_id` | Định danh sự kiện duy nhất, phục vụ retry/dedupe |
| `aggregate_type` | Loại đối tượng nghiệp vụ, ví dụ `product` |
| `aggregate_id` | ID sản phẩm cần invalidation |
| `aggregate_version` | Phiên bản dữ liệu nguồn sau lần cập nhật |
| `event_type` | Loại sự kiện, ví dụ `PRODUCT_CHANGED`/`PRODUCT_DELETED` |
| `payload` | Dữ liệu sự kiện, chỉ chứa những field consumer thực sự cần |
| `created_at` | Thời gian tạo event phục vụ quan sát và polling |
| `published_at` | Relay đánh dấu đã gửi thành công theo hợp đồng broker |
| `claim_token`, `claimed_until` | Giúp nhiều relay claim công việc và hồi phục khi worker crash |

Tùy nhu cầu, có thể thêm `schema_version`, `tenant_id`, `correlation_id`, số lần thử, mã lỗi cuối, hoặc một số cột dành cho vận hành. Không đưa thông tin nhạy cảm vào event payload nếu consumer chỉ cần ID để xóa cache.

### Mẫu event envelope

```json
{
  "eventId": "1d4ee073-438d-44fc-8c44-d0dfe354c441",
  "eventType": "PRODUCT_CHANGED",
  "aggregateType": "product",
  "aggregateId": "p-100",
  "aggregateVersion": 8,
  "schemaVersion": 1,
  "occurredAt": "2026-11-13T02:00:00Z"
}
```

`occurredAt` chỉ có ý nghĩa quan sát; không dùng timestamp của các instance khác nhau như bảo đảm thứ tự tuyệt đối. Nếu cần đối chiếu sự kiện, ưu tiên **version tăng đơn điệu theo từng aggregate**.

## 8. Ghi product và outbox trong cùng transaction

Ví dụ dưới sử dụng PostgreSQL, `JdbcTemplate` và `@Transactional` để minh họa rõ ràng ranh giới của transaction. `UPDATE ... RETURNING` là cú pháp PostgreSQL; với RDBMS khác cần dùng cú pháp tương đương.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductOutboxCommandService {

    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    public ProductOutboxCommandService(
            JdbcTemplate jdbc,
            ObjectMapper json
    ) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Transactional
    public void changePrice(String id, BigDecimal newPrice) {
        Long version = jdbc.queryForObject(
                """
                UPDATE products
                   SET price = ?, version = version + 1
                 WHERE id = ?
                RETURNING version
                """,
                Long.class,
                newPrice,
                id
        );

        if (version == null) {
            throw new IllegalStateException(
                    "Product not found or version unavailable: " + id);
        }

        UUID eventId = UUID.randomUUID();
        String payload;
        try {
            payload = json.writeValueAsString(Map.of(
                    "eventId", eventId.toString(),
                    "eventType", "PRODUCT_CHANGED",
                    "aggregateType", "product",
                    "aggregateId", id,
                    "aggregateVersion", version,
                    "schemaVersion", 1
            ));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot encode product change event", ex);
        }

        jdbc.update(
                """
                INSERT INTO outbox_events (
                    event_id, aggregate_type, aggregate_id,
                    aggregate_version, event_type, payload
                ) VALUES (?, 'product', ?, ?, 'PRODUCT_CHANGED', ?::jsonb)
                """,
                eventId, id, version, payload
        );
    }
}
```

Đoạn code cần một transaction manager cho datasource SQL; Spring Boot thường tự cấu hình khi có một datasource phù hợp. Bảng `products` và `outbox_events` phải nằm trong **cùng database transaction thực sự**. Không được đặt outbox ở một datasource độc lập rồi giả định `@Transactional` bao phủ cả hai.

Các tình huống:

| Tình huống | Kết quả trong SQL |
|---|---|
| `UPDATE` thành công và `INSERT outbox` thành công, commit | Cả dữ liệu mới và event được lưu |
| `UPDATE` thành công, `INSERT outbox` lỗi | Toàn transaction rollback |
| `INSERT outbox` thành công, lỗi trước commit | Toàn transaction rollback |
| Commit thành công, JVM crash trước khi relay chạy | Dữ liệu mới và outbox row vẫn tồn tại |

**Chú ý trong ví dụ:** `JdbcTemplate.queryForObject` có thể ném `EmptyResultDataAccessException` khi `UPDATE ... RETURNING` không tìm được hàng; không nhất thiết trả `null`. Ứng dụng nên chuyển exception này thành lỗi “không tìm thấy product” phù hợp với API. Điều này không làm mất tính chất giao dịch của mẫu outbox.

### 8.1. Vì sao cần aggregate_version?

Hai thay đổi gần nhau:

```text
Product p-100 v7 -> v8 (giá 1100)
Product p-100 v8 -> v9 (giá 1050)
```

Outbox có thể chứa hai event:

```text
Event A: PRODUCT_CHANGED p-100 version 8
Event B: PRODUCT_CHANGED p-100 version 9
```

Trong hệ thống nhiều relay hoặc broker partition khác nhau, B có thể được consumer nhận trước A. Nếu consumer **blind refresh** bằng payload A sau khi đã xử lý B, cache có thể bị ghi lùi từ giá mới về giá cũ.

Với chiến lược **invalidation**, cả hai sự kiện chỉ yêu cầu xóa key, nên thường ít nguy hiểm hơn. Nếu cần ghi trực tiếp giá trị vào cache, hãy có cơ chế so sánh version nguyên tử và chỉ chấp nhận bản mới hơn.

## 9. Outbox relay: đọc, gửi, xác nhận và retry

Relay là tiến trình đưa sự kiện từ bảng SQL ra hệ thống truyền tin, ví dụ Kafka, RabbitMQ hoặc Redis Streams. Hai hướng triển khai phổ biến:

- **Polling publisher:** định kỳ query những outbox row chưa được publish.
- **Change Data Capture (CDC):** theo dõi log thay đổi của database và phát các bản ghi outbox mới, ví dụ qua Debezium.

Việc lựa chọn không thay đổi nguyên tắc: **event phải được lưu cùng transaction dữ liệu nguồn**, và consumer phải sẵn sàng nhận trùng.

### 9.1. Polling với nhiều worker

Nếu có nhiều relay, không nên để tất cả cùng chọn mọi hàng chưa phát mà không có cơ chế claim. Với PostgreSQL, có thể dùng `FOR UPDATE SKIP LOCKED` để những worker đang lấy công việc khác nhau.

Ví dụ một transaction ngắn **claim** batch:

```sql
WITH batch AS (
    SELECT event_id
    FROM outbox_events
    WHERE published_at IS NULL
      AND (claimed_until IS NULL OR claimed_until < NOW())
    ORDER BY created_at, event_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events AS e
   SET claim_token = :claim_token,
       claimed_until = NOW() + INTERVAL '30 seconds'
  FROM batch
 WHERE e.event_id = batch.event_id
RETURNING e.event_id, e.aggregate_id, e.aggregate_version,
          e.event_type, e.payload;
```

`:claim_token` là tham số do worker tạo, không phải cú pháp SQL literal. Kết thúc transaction claim nhanh; sau đó publish các event được claim tới broker.

Khi broker xác nhận đã nhận thành công theo giao thức producer được cấu hình, relay cập nhật:

```sql
UPDATE outbox_events
   SET published_at = NOW(),
       claim_token = NULL,
       claimed_until = NULL
 WHERE event_id = :event_id
   AND claim_token = :claim_token
   AND published_at IS NULL;
```

Nếu worker crash sau claim nhưng trước publish, `claimed_until` sẽ hết hạn và worker khác có thể claim lại. Nếu worker crash **sau khi broker nhận event nhưng trước khi đánh dấu `published_at`**, event có thể được gửi **thêm lần nữa**.

Do đó, outbox thường đem lại cơ chế giao nhận **at-least-once** khi relay/consumer được triển khai đúng. Nó **không mặc nhiên bảo đảm exactly-once** ở toàn tuyến database → broker → Redis.

### 9.2. Điều kiện vận hành của relay

- Đặt timeout/lease đủ dài cho thời gian publish bình thường và có cơ chế gia hạn nếu batch lớn.
- Giới hạn số event mỗi batch, số worker và số lần retry để không gây quá tải broker.
- Nếu lỗi do message schema không đọc được, phân loại poison message, ghi lại lỗi và có quy trình sửa hoặc chuyển dead-letter.
- Khi retry, chỉ đánh dấu `published_at` sau khi đã nhận xác nhận thành công của broker theo mức bảo đảm yêu cầu.
- Có chính sách **dọn các event đã publish** hoặc lưu archive để bảng outbox không tăng mãi.
- Theo dõi độ trễ từ `created_at` đến lúc consumer invalidation xong, không chỉ thời điểm relay gửi.
- Nếu nhiều event cho cùng product cần thứ tự, có thể partition theo aggregate ID hoặc thiết kế so sánh version.

### 9.3. Không giữ lock SQL quá lâu khi gọi mạng

Một biến thể đơn giản là giữ transaction SQL mở trong khi gửi broker và đánh dấu published. Cách này làm lock database sống lâu theo độ trễ mạng và có thể gây nghẽn. Mẫu claim-with-lease tách **transaction claim ngắn** khỏi **publish I/O**, đổi lại cần handling lease expiration và duplicate deliveries.

Với CDC, không cần polling và claim theo cách trên, nhưng vẫn cần xử lý sơ đồ event, thứ tự, retry, lỗi connector và việc consumer có thể nhận lại event.

## 10. Consumer: nhận event và xóa Redis cache

Một consumer dùng message broker sẽ nhận những event như:

```json
{
  "eventId": "1d4ee073-438d-44fc-8c44-d0dfe354c441",
  "eventType": "PRODUCT_CHANGED",
  "aggregateId": "p-100",
  "aggregateVersion": 8
}
```

Nhiệm vụ tối thiểu là **xóa đúng entry của cache `products`**.

### 10.1. Tách logic invalidation khỏi transport

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheInvalidationHandler {

    private final CacheManager cacheManager;

    public ProductCacheInvalidationHandler(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public void handle(ProductChangedMessage message) {
        Cache cache = cacheManager.getCache("products");
        if (cache == null) {
            throw new IllegalStateException(
                    "No cache configured with name: products");
        }

        // Đúng key logic từ @Cacheable(key = "#id").
        cache.evict(message.aggregateId());
    }
}

public record ProductChangedMessage(
        String eventId,
        String aggregateId,
        long aggregateVersion
) {
}
```

Handler không quan tâm event đến từ Kafka, RabbitMQ hay Redis Streams. Transport adapter chỉ có trách nhiệm giải mã message, gọi `handle` và xác nhận (ack) **sau khi** công việc cần thiết đã thành công.

Một ví dụ adapter Kafka (giả định ứng dụng có `spring-kafka`, listener container và consumer được cấu hình phù hợp):

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class ProductChangedKafkaListener {

    private final ProductCacheInvalidationHandler handler;

    public ProductChangedKafkaListener(
            ProductCacheInvalidationHandler handler
    ) {
        this.handler = handler;
    }

    @KafkaListener(
        topics = "product-changes",
        groupId = "product-cache-invalidator"
    )
    public void onMessage(ProductChangedMessage message) {
        handler.handle(message);
        // Ack/commit offset theo chính sách của listener container.
    }
}
```

Để JSON message được chuyển thành `ProductChangedMessage`, cần cấu hình Kafka deserializer/message converter và trusted type phù hợp; đoạn code chỉ minh họa ranh giới giữa **broker listener** và **logic invalidation**. Không mặc định Kafka Listener được cấu hình tự động chỉ từ annotation.

### 10.2. Gặp message trùng thì sao?

`cache.evict(id)` thường có tính **idempotent theo trạng thái cuối**: nếu key đã bị xóa, xóa lại vẫn cho kết quả cache miss khi đọc. Vì vậy, invalidation dễ chịu duplicate delivery hơn cơ chế “cộng dồn” hoặc “ghi đè bằng dữ liệu payload”.

Tuy nhiên, việc xử lý trùng vẫn có tác động:

- Tăng chi phí I/O Redis.
- Có thể xóa entry vừa được nạp lại với dữ liệu mới, gây thêm cache miss.
- Nếu một event kích hoạt cả email, webhook hay cập nhật chỉ số nghiệp vụ, cần idempotency riêng cho những side effect đó.

Khi cần chống xử lý trùng, có thể lưu `event_id` vào bảng processed-events hoặc Redis key dedupe có TTL phù hợp. Việc ghi dấu đã xử lý và hoàn tất side effect phải có thứ tự đúng: **không đánh dấu thành công trước khi công việc chính thành công** nếu điều đó khiến retry bị bỏ qua.

### 10.3. Nếu Redis đang lỗi

Nếu Redis tạm thời không truy cập được, consumer không nên xác nhận message như đã đồng bộ xong khi chính sách đòi hỏi invalidation phải thành công. Hãy để transport retry hoặc đưa message vào hàng chờ xử lý lỗi có thể theo dõi.

Redis CacheManager có thể ném exception khi `evict` thất bại. Không nên cấu hình một `CacheErrorHandler` nuốt toàn bộ lỗi rồi coi đồng bộ cache đã thành công nếu bài toán yêu cầu phát lại đáng tin cậy.

Trong ứng dụng lấy DB làm nguồn sự thật, có thể định nghĩa chiến lược fallback khi Redis ngừng hoạt động để dữ liệu vẫn đọc được từ DB, nhưng cần thiết kế rõ đường đọc không sử dụng bản cache stale sau khi Redis hồi phục.

## 11. Race condition: đã evict sau commit nhưng dữ liệu cũ vẫn quay lại

Một tình huống khó nhìn thấy trong thử nghiệm tuần tự:

```text
Thời điểm   Reader (cache miss)          Writer/Consumer
----------------------------------------------------------------
t1          GET Redis -> miss
t2          SELECT DB -> đọc version 7
t3                                        UPDATE DB lên version 8
t4                                        COMMIT DB
t5                                        Event -> EVICT Redis
t6          Redis SET value version 7
t7          GET khác -> nhận version 7 (stale)
```

Ở `t5`, key không tồn tại nên xóa là thao tác bình thường. Nhưng ở `t6`, reader trước đó ghi giá trị **cũ** vào Redis **sau invalidation**. Entry stale có thể tồn tại cho đến hết TTL hoặc tới một sự kiện cập nhật khác.

**Kết luận:** “Phát event sau commit và xóa cache” giảm khoảng thời gian không nhất quán, nhưng **không phải bảo đảm linearizability** cho mọi luồng đọc/ghi đồng thời.

### 11.1. Những cách giảm thiểu

| Cách | Cơ chế | Giới hạn |
|---|---|---|
| TTL đủ ngắn | Giới hạn thời gian tồn tại của entry stale | Không bảo đảm tức thời; tăng cache miss |
| Xóa sau commit + thêm một lần xóa trễ | Có cơ hội xóa giá trị cũ bị reader ghi lại | Cần durable scheduler nếu yêu cầu tin cậy; không chứng minh loại bỏ mọi race |
| Versioned cache key | Đưa version/generation vào key cache | Phải đọc version hiện hành từ nguồn đáng tin cậy |
| Compare-and-set theo version | Không cho bản cũ ghi đè bản mới | Cần lệnh/script nguyên tử và schema cache chứa version |
| Đọc database theo yêu cầu nhất quán cao | Bỏ qua cache ở bước quyết định nghiệp vụ quan trọng | Tăng tải DB |
| Cache writer có phối hợp khóa/version | Điều phối read-fill với invalidation | Phức tạp, dễ nghẽn; cần xét timeout và failure |

Trong nhiều ứng dụng, **TTL + event-driven invalidation + chấp nhận eventual consistency có giới hạn** là đủ. Nếu yêu cầu “không bao giờ đọc giá cũ sau commit”, cần một cơ chế mạnh hơn chứ không chỉ thêm một listener.

### 11.2. Versioned key

Thay vì:

```text
products::p-100
```

có thể dùng:

```text
products::p-100:v7
products::p-100:v8
```

Đường đọc phải biết version mới nhất từ một nguồn đáng tin cậy (ví dụ database hoặc một khóa generation được cập nhật đúng semantics). Khi version hiện hành là 8, cache entry v7 không được chọn, cho dù nó vẫn tồn tại trong Redis đến khi TTL hết hạn.

**Đánh đổi:** bước xác định version có chi phí, và nếu nguồn version cũng stale thì cách này không giải quyết mục tiêu. Cần TTL/dọn dẹp cho cache key phiên bản cũ để không làm tăng bộ nhớ mãi.

### 11.3. Không ghi đè giá trị mới bằng event đến muộn

Giả sử event v9 đến trước v8. Nếu consumer thực hiện:

```text
event v9 -> cache SET "price = 1050"
event v8 -> cache SET "price = 1100"
```

cache bị đưa lùi về giá trị cũ.

Nếu consumer cần **refresh** thay vì evict, không nên dùng `SET` mù quáng với giá trị trong message. Có thể:

- Chỉ evict và để lần đọc sau lấy DB mới nhất.
- Khi nhận event, query DB nguồn để lấy dữ liệu hiện tại và version hiện tại, sau đó cập nhật cache bằng thao tác kiểm tra version nguyên tử.
- Thiết kế một Lua script so sánh version đã lưu trong Redis với version sắp ghi; chỉ cập nhật khi version mới hơn, giữ TTL phù hợp.

Với cache dùng Spring Cache abstraction, chiến lược CAS/version cần tự xây bằng RedisTemplate/script hoặc cache implementation chuyên biệt. `RedisCacheManager` mặc định không có hợp đồng “chỉ ghi nếu aggregateVersion lớn hơn” cho mọi cache entry.

## 12. Đồng bộ cache khi một thay đổi ảnh hưởng nhiều khóa

Ví dụ thay đổi giá sản phẩm có thể làm nhiều cache trở nên lỗi thời:

```text
products::p-100                  - chi tiết sản phẩm
productsByCategory::laptops      - danh sách theo danh mục
featuredProducts::homepage      - danh sách nổi bật
searchResults::laptop-cheap     - kết quả tìm kiếm
priceSummary::category-laptops  - tổng hợp giá
```

Nếu consumer chỉ xóa `products::p-100`, các danh sách và số liệu tổng hợp vẫn có thể chứa giá cũ. Cần **bản đồ phụ thuộc** giữa loại thay đổi dữ liệu và những vùng cache liên quan:

| Thay đổi | Cần cân nhắc invalidation |
|---|---|
| Cập nhật mô tả sản phẩm | Chi tiết sản phẩm; kết quả tìm kiếm chứa mô tả |
| Đổi giá | Chi tiết; danh sách có giá; tổng hợp, ranking theo giá |
| Đổi danh mục | Chi tiết; danh sách danh mục cũ và mới; search facets |
| Xóa sản phẩm | Chi tiết; mọi danh sách/tổng hợp liên quan; negative cache |
| Đổi trạng thái hiển thị | Trang chủ; kết quả tìm kiếm; danh sách công khai |

Một event có thể chứa `productId`, `oldCategoryId`, `newCategoryId` và version nếu đó là những thông tin cần thiết để xác định cache bị ảnh hưởng. Tuy nhiên, không nên biến event invalidation thành bản sao đầy đủ của dữ liệu nghiệp vụ nếu không cần.

### 12.1. Xóa cả vùng cache có thể rất tốn kém

Gọi `cache.clear()` có thể xóa toàn bộ key thuộc cache. Với RedisCacheManager, chiến lược clear mặc định có thể dùng `KEYS` và `DEL`, gây tải lớn trên keyspace rộng. Spring Data Redis hỗ trợ `BatchStrategies.scan(...)` khi cấu hình RedisCacheWriter trong môi trường driver/topology phù hợp.

Ưu tiên evict những key xác định được. Với cache truy vấn tổ hợp không thể tính ngược key từ product ID, có thể:

- Duy trì reverse-index từ product ID đến cache key liên quan.
- Sử dụng namespace version/generation cho vùng cache.
- Dùng TTL ngắn hơn cho các cache danh sách/tìm kiếm.
- Chọn cấu trúc dữ liệu hoặc công cụ truy vấn khác nếu invalidation phụ thuộc phức tạp.

Không thiết kế một event `PRODUCT_CHANGED` khiến mọi instance liên tục `clear()` toàn bộ cache lớn mà không đo tải.

### 12.2. Multi-instance và Redis dùng chung

Khi nhiều instance ứng dụng dùng **cùng Redis CacheManager backend**, lệnh `evict` một Redis key được các instance khác thấy khi chúng truy cập key đó. Không bắt buộc gửi một event nội bộ đến từng instance **chỉ để xóa cùng một Redis key**.

Nhưng nếu ứng dụng đồng thời có **cache L1 trong bộ nhớ JVM** (ví dụ Caffeine) và cache L2 trên Redis, invalidation trên Redis **không tự xóa L1**. Khi đó, event fan-out đến từng instance hoặc một cơ chế version/generation là cần thiết để không giữ bản sao cũ trong bộ nhớ cục bộ.

## 13. Redis Pub/Sub, Redis Streams và message broker

Có nhiều cách chuyển sự kiện tới consumer; nhưng chúng có hợp đồng giao nhận khác nhau.

### 13.1. Redis Pub/Sub

Redis Pub/Sub thích hợp cho các thông báo nhẹ, thời gian thực đến subscriber đang hoạt động:

```redis
PUBLISH product:changed "{\"productId\":\"p-100\"}"
```

Subscriber đang kết nối nhận message; subscriber offline **không tự nhận lại thông báo đã bỏ lỡ**. Pub/Sub theo mô hình **at-most-once delivery**: sau khi server gửi message, không có lịch sử bền vững để consumer phát lại khi bị mất kết nối.

Vì vậy, dùng Redis Pub/Sub đơn thuần để đồng bộ cache có thể chấp nhận khi mất một event chỉ làm cache stale trong giới hạn TTL. Không nên xem nó là bảo đảm durable invalidation khi nghiệp vụ đòi hỏi phải xử lý tất cả sự kiện.

Trong Spring Data Redis, `RedisMessageListenerContainer` là một lựa chọn để đăng ký listener Redis Pub/Sub. Nhưng listener container không tự biến Pub/Sub thành một message queue lưu bền.

### 13.2. Redis Streams

Redis Streams hỗ trợ lưu log event theo stream, consumer groups, pending entries và acknowledgment (`XACK`). Ví dụ ý nghĩa:

```redis
XADD stream:product-changes * eventType PRODUCT_CHANGED productId p-100 version 8
```

So với Pub/Sub, Streams cho phép consumer đọc tiếp và xử lý lại pending messages, nếu event còn tồn tại và hệ thống có chiến lược recovery đúng. Tuy nhiên, độ bền còn phụ thuộc cấu hình persistence/replication của Redis, chính sách trimming, ack, retention và failover.

Một event được ghi vào Redis Stream **sau** khi SQL commit vẫn gặp khoảng trống dual-write nếu tiến trình crash giữa hai thao tác. Outbox tại SQL nguồn giải quyết khoảng trống này; Redis Streams chỉ là một trong những **kênh vận chuyển** có thể nhận event từ relay.

### 13.3. Kafka, RabbitMQ và các broker khác

Broker cung cấp tính năng retry, consumer groups, routing và durability theo từng cấu hình. Chúng có thể phù hợp khi nhiều dịch vụ cần nhận cùng product event. Tuy nhiên, **bản thân broker không bảo đảm SQL update và publish message thuộc cùng transaction**. Transactional outbox hoặc CDC vẫn hữu ích cho producer.

| Cơ chế | Dùng khi | Điều cần nhớ |
|---|---|---|
| Spring `ApplicationEventPublisher` | Một ứng dụng, tác vụ invalidation nhẹ | Event chỉ sống trong tiến trình; dễ mất khi crash |
| Redis Pub/Sub | Thông báo real-time, mất event có thể chịu được | Không có durable replay mặc định |
| Redis Streams | Cần stream/consumer group trên Redis | Phải thiết kế ack, retention, recovery |
| Kafka/RabbitMQ | Nhiều consumer, yêu cầu durability/routing riêng | Vẫn cần giải quyết dual-write ở producer |
| SQL outbox + relay | Cần lưu chắc ý định phát event cùng thay đổi DB | At-least-once; consumer phải idempotent |

## 14. Lỗi trong pipeline đồng bộ và cách hồi phục

Một hệ thống outbox vận hành tốt phải trả lời được các tình huống:

**SQL transaction rollback:** không có event được commit, cache cũ vẫn có thể đúng vì dữ liệu nguồn không thay đổi.

**SQL commit thành công, service crash:** outbox row còn tồn tại. Relay chạy lại và phát event.

**Relay gửi broker thành công nhưng chưa đánh dấu published:** relay sẽ phát lại; consumer phải chịu duplicate.

**Broker hoặc Redis gián đoạn:** có retry với backoff, theo dõi số lượng event chưa xử lý và thời gian chờ. Không đánh dấu thành công khi chưa xử lý theo hợp đồng.

**Message payload lỗi:** ghi lỗi có ngữ cảnh, dùng dead-letter/quarantine và cơ chế sửa dữ liệu; tránh vòng retry vô hạn với poison message.

**Consumer v8 tới sau v9:** invalidation vẫn có thể xóa key mới (tăng cache miss), còn blind refresh có thể gây stale. Muốn tối ưu cần version check.

**Cache fill ghi bản cũ sau invalidation:** giải quyết bằng TTL ngắn hơn hoặc cơ chế version/cas nếu cần mạnh hơn; outbox **không tự loại bỏ race này**.

**Nhiều cache hoặc nhiều vùng dữ liệu phụ thuộc:** cần xác định phạm vi invalidation và tránh chỉ xóa cache chi tiết trong khi cache danh sách vẫn cũ.

### 14.1. Chỉ số cần giám sát

| Chỉ số | Phát hiện vấn đề |
|---|---|
| Số outbox row chưa publish | Relay chậm hoặc ngừng |
| Tuổi của outbox row chưa xử lý cũ nhất | Khoảng trễ đồng bộ dữ liệu |
| Lần thử publish/consume và tỷ lệ lỗi | Broker/Redis không ổn định hoặc poison message |
| Consumer lag theo partition/stream | Năng lực xử lý thiếu hoặc backlog tăng |
| Thời gian SQL commit → Redis eviction | Mức stale do pipeline |
| Cache hit/miss và DB read latency | Chi phí của invalidation quá rộng |
| Version cache so với version DB | Khả năng phát hiện stale theo sampling |
| Số key và dung lượng Redis | Tác động từ TTL, namespace và event-driven refresh |

Không chỉ theo dõi “broker đã nhận event”; điều nghiệp vụ cần biết là **cache đã được đồng bộ thành công chưa** và thời gian chậm nhất từ thay đổi nguồn đến khi các đường đọc có thể thấy dữ liệu mới.

### 14.2. Reconciliation định kỳ

Ngay cả hệ thống có retry vẫn cần cơ chế kiểm tra/khôi phục:

- Đếm event chưa xử lý và cảnh báo khi tuổi backlog vượt ngưỡng.
- Định kỳ đối chiếu version của một mẫu key cache với DB.
- Hỗ trợ replay theo event ID hoặc aggregate ID.
- Có lệnh vận hành xóa cache theo ID/prefix an toàn.
- Giới hạn TTL để trạng thái cũ không tồn tại vô hạn khi một event hiếm gặp bị bỏ lỡ.

Reconciliation không thay thế việc xử lý đúng đường ghi; nó là mạng lưới an toàn cho lỗi vận hành và dữ liệu lịch sử.

## 15. Lựa chọn invalidation hay chủ động refresh

### 15.1. Invalidation thường đơn giản hơn

```text
PRODUCT_CHANGED(p-100, v8)
       |
       v
Cache.evict(p-100)
       |
       v
Lần đọc sau -> DB v8 hoặc mới hơn
```

Ưu điểm:

- Event nhỏ, chỉ cần ID.
- Ít nguy cơ ghi đè dữ liệu bằng payload cũ.
- Không bắt consumer hiểu toàn bộ DTO cache.
- Nếu sản phẩm được xóa, việc xóa cache entry tự nhiên.

Đánh đổi là request đầu sau invalidation có cache miss và tăng độ trễ/tải DB.

### 15.2. Refresh chủ động giúp giảm miss nhưng phức tạp hơn

```text
PRODUCT_CHANGED(p-100, v8)
       |
       v
Đọc DB hiện hành
       |
       v
Ghi cache với version check
```

Refresh có thể hữu ích với dữ liệu cực kỳ phổ biến, nhưng cần giải quyết nhiều vấn đề:

- Có thể có nhiều event cho cùng ID đến gần nhau.
- Event đến muộn không được ghi đè dữ liệu mới hơn.
- Nếu source DB đọc replica có replication lag, consumer có thể lấy bản cũ.
- Refresh ngay sau event có thể tạo burst read lên DB.
- Khi sản phẩm bị xóa, cần tombstone hoặc invalidation thay vì cố tải entity không tồn tại.

Một hướng thường hợp lý là **evict theo event**, còn những key rất nóng được làm mới có kiểm soát bằng background prewarm hoặc refresh có version check.

## 16. Lộ trình triển khai theo độ phức tạp

| Mức | Cách làm | Phù hợp |
|---|---|---|
| 1 | Cache-aside + TTL | Cache không quá nhạy với dữ liệu cũ |
| 2 | TTL + `@TransactionalEventListener(AFTER_COMMIT)` + evict | Monolith hoặc một dịch vụ ghi, chấp nhận khả năng mất event nội bộ |
| 3 | TTL + transactional outbox + broker/stream + consumer evict | Nhiều service hoặc yêu cầu đồng bộ đáng tin cậy |
| 4 | Outbox + versioning/CAS + idempotency + reconciliation | Dữ liệu nhạy với thứ tự, có read/write concurrency cao |
| 5 | Bỏ cache ở bước quyết định hoặc dùng hệ thống dữ liệu/transaction phù hợp | Yêu cầu không thể chấp nhận stale, ví dụ xác nhận số dư chính xác |

Không nhất thiết dùng Kafka, CDC và outbox chỉ cho một cache nhỏ có TTL vài chục giây. Chọn mức độ phức tạp dựa trên **chi phí của dữ liệu stale**, quy mô hệ thống, mục tiêu độ trễ và khả năng vận hành.

### Một bộ quy tắc thiết kế hữu ích

1. **Xác định source of truth.** Redis thường là bản sao có thể tái tạo, không phải nơi quyết định giao dịch chính.
2. **Lập danh sách cache phụ thuộc.** Thay đổi một record có thể ảnh hưởng nhiều cache detail, list và aggregation.
3. **Chỉ invalidation sau DB commit.** Đừng xóa trước commit nếu cần tránh cache fill từ dữ liệu cũ.
4. **Chọn mức độ tin cậy.** Sự kiện nội bộ nhanh và gọn nhưng không durable; outbox lưu được ý định phát event.
5. **Thiết kế at-least-once.** Outbox có thể phát trùng; consumer phải idempotent.
6. **Xử lý thứ tự và race.** Invalidation giảm nguy cơ ghi lùi nhưng không loại bỏ toàn bộ race cache fill.
7. **Giữ TTL làm lớp dự phòng.** Nó giới hạn tuổi cache khi pipeline đồng bộ gặp sự cố.
8. **Giám sát end-to-end.** Mục tiêu là độ trễ từ DB commit đến lúc cache được làm mất hiệu lực, không chỉ số lượng message đã publish.

## 17. Bài thực hành

### Thực hành A — Sự kiện sau commit

1. Tạo cache `products` bằng `@Cacheable(cacheNames = "products", key = "#id")`.
2. Dùng `ProductCommandService.changePrice` phát `ProductChanged` trong transaction.
3. Cấu hình `@TransactionalEventListener(AFTER_COMMIT)` xóa key qua `CacheManager`.
4. Gọi `findById("p-100")` để nạp cache, sau đó cập nhật giá và kiểm tra `EXISTS products::p-100`.
5. Thử gây exception trước commit; quan sát listener sau commit không chạy cho transaction rollback.
6. Dừng ứng dụng tại thời điểm gần commit để thảo luận vì sao listener nội bộ có thể mất event.

### Thực hành B — Transactional outbox

1. Tạo `products` và `outbox_events` như mục 7 trong PostgreSQL test.
2. Viết một method `@Transactional` cập nhật price và insert outbox.
3. Thử làm insert outbox thất bại; kiểm tra cập nhật product cũng rollback.
4. Chạy relay polling có claim theo lease, publish event và đánh dấu published.
5. Dừng relay sau khi broker nhận message nhưng trước khi đánh dấu published; khởi động lại và quan sát duplicate.
6. Viết consumer evict cùng cache key; xác minh xử lý lại một event không khiến dữ liệu sai.

### Thực hành C — Mô phỏng cache fill race

1. Cho reader cache miss và tạm dừng sau khi đọc DB cũ.
2. Cho writer cập nhật DB, commit và gửi invalidation.
3. Cho reader tiếp tục ghi giá trị cũ vào Redis.
4. Quan sát key cũ tồn tại dù invalidation đã chạy.
5. Đề xuất cách giải quyết dựa trên TTL, versioned keys hoặc compare-and-set theo version.

### Thực hành D — Đồng bộ nhiều cache

Tạo `products`, `productsByCategory` và `featuredProducts`. Khi product đổi giá hoặc bị xóa, xác định cache nào cần evict. So sánh một event chỉ chứa ID với event có thêm old/new category, rồi đánh giá chi phí clear toàn vùng cache so với quản lý reverse-index.

## 18. Kết luận

Đồng bộ cache với thay đổi dữ liệu không chỉ là gọi `DEL` sau một câu lệnh `UPDATE`. Với Spring Data Redis, chiến lược cơ bản là **cache-aside + TTL + invalidation sau commit**. `@TransactionalEventListener(AFTER_COMMIT)` giúp xóa cache đúng pha của transaction, nhưng sự kiện chỉ trong bộ nhớ ứng dụng có thể mất khi crash.

Nếu yêu cầu không được mất ý định đồng bộ, **transactional outbox** lưu thay đổi nghiệp vụ và sự kiện trong cùng transaction SQL, sau đó relay phát message và consumer xóa Redis cache. Thiết kế này cải thiện khả năng phục hồi nhưng thường có **at-least-once delivery**: cần xử lý trùng, thứ tự, retry, lỗi từng phần và độ trễ.

Ngay cả sau commit, invalidation có thể gặp **race cache fill** khiến một reader cũ ghi lại dữ liệu stale. Do đó TTL, versioning/CAS và chiến lược đọc dữ liệu nguồn vẫn cần được cân nhắc theo yêu cầu. Với nghiệp vụ không thể chấp nhận dữ liệu cũ, đừng dựa vào cache như nơi quyết định tính đúng đắn cuối cùng.

## Tài liệu tham khảo

- [Spring Framework — Caching](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CacheEvict`, `@CachePut` và nguyên tắc proxy/abstraction.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, Redis key, TTL, prefix, serialization và cache clearing.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, `AFTER_COMMIT` và `fallbackExecution`.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, transaction synchronization và thời điểm commit/rollback.
- [Microservices Patterns — Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html): giải quyết dual-write và vai trò message relay.
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): mô hình CDC chuyển outbox row thành event.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): bản chất at-most-once của Pub/Sub.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): stream, consumer groups và cơ chế xử lý message.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): đọc thời hạn còn lại của từng Redis key.
