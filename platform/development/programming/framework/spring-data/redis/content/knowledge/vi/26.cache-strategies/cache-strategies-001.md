# Cache-aside và vòng đời đọc dữ liệu qua cache

## 1. Bài toán: dữ liệu nằm ở đâu và vì sao cần cache?

Giả sử một dịch vụ Spring Boot cung cấp API đọc thông tin sản phẩm. Dữ liệu sản phẩm chính thức nằm trong cơ sở dữ liệu quan hệ; Redis được dùng để lưu những kết quả đọc thường xuyên nhằm giảm số lần truy vấn cơ sở dữ liệu và rút ngắn thời gian phản hồi.

Một lần đọc không sử dụng cache:

```text
Client ── GET /products/42 ──> Spring Boot ── SELECT ──> Database
Client <────── ProductView ───── Spring Boot <──── row ───── Database
```

Nếu hàng nghìn request liên tục yêu cầu cùng một sản phẩm, cơ sở dữ liệu phải xử lý rất nhiều truy vấn giống nhau. Với **cache-aside**, ứng dụng chủ động kiểm tra Redis trước, sau đó chỉ đọc cơ sở dữ liệu khi cache không có dữ liệu phù hợp.

```text
                             ┌──────────────────┐
Client ──> Spring Boot ─────> │ Redis cache      │
                 │           └──────────────────┘
                 │                   │
                 │               Hit / Miss
                 │                   │
                 ├──── Hit ──────────┘
                 │       trả kết quả từ cache
                 │
                 └──── Miss ────────> Database
                                          │
                              dữ liệu nguồn
                                          │
                             ghi vào Redis với TTL
                                          │
                              trả kết quả cho client
```

**Cache-aside** còn được gọi là *lazy loading cache*: chỉ khi cần đọc một đối tượng mà cache chưa có, ứng dụng mới lấy dữ liệu nguồn và đưa vào cache. Redis đóng vai trò **bản sao phục vụ đọc**; cơ sở dữ liệu vẫn là **nguồn dữ liệu có thẩm quyền** (*source of truth*).

Bài học này thuộc chương **Chiến lược cache** trong Spring Data Redis. Trọng tâm là vòng đời của một lần đọc: **cache hit → cache miss → đọc nguồn → ghi cache → trả dữ liệu**, cùng những tình huống làm thay đổi vòng đời như TTL, cập nhật dữ liệu, cạnh tranh đồng thời và Redis gặp sự cố.

## 2. Hai nhánh của luồng đọc: cache hit và cache miss

### 2.1. Cache hit: Redis đã có dữ liệu

Giả sử Redis có khóa:

```text
product:detail:v1:42
```

với JSON biểu diễn thông tin sản phẩm. Ứng dụng đọc khóa và nhận được dữ liệu đã lưu:

```text
1. Client gọi GET /products/42.
2. Ứng dụng tạo khóa "product:detail:v1:42".
3. Ứng dụng gọi Redis GET.
4. Redis trả về dữ liệu đã có.
5. Ứng dụng giải mã và trả kết quả.
6. Không cần truy vấn database cho lần đọc đó.
```

Sơ đồ:

```text
Client        ProductService           Redis                 Database
  |                  |                    |                      |
  | get(42)          |                    |                      |
  |----------------->|                    |                      |
  |                  | GET product:42     |                      |
  |                  |------------------->|                      |
  |                  | <--- ProductView --|                      |
  | <--- ProductView |                    |                      |
  |                  |                    |                      |
  |                  |     Database không được gọi              |
```

Lợi ích của hit phụ thuộc vào thời gian đọc Redis, độ lớn giá trị, chi phí giải mã và vị trí Redis so với ứng dụng. Cache không phải lúc nào cũng nhanh hơn mọi cách đọc khác; hiệu quả cần được đo trên workload thật.

### 2.2. Cache miss: khóa không có hoặc đã hết hạn

Redis trả `null` khi khóa không tồn tại (ví dụ dùng `opsForValue().get(key)` với cấu hình thông thường). Ứng dụng đọc dữ liệu nguồn, rồi ghi vào cache:

```text
Client        ProductService           Redis                Database
  |                  |                    |                     |
  | get(42)          |                    |                     |
  |----------------->|                    |                     |
  |                  | GET product:42     |                     |
  |                  |------------------->|                     |
  |                  | <--- null ---------|                     |
  |                  |                    |                     |
  |                  | SELECT product 42                        |
  |                  |----------------------------------------->|
  |                  | <----------------------- ProductView ----|
  |                  |                    |                     |
  |                  | SET product:42 + TTL                     |
  |                  |------------------->|                     |
  |                  | <--- OK -----------|                     |
  | <--- ProductView |                    |                     |
```

Đây là lần đọc **cold** đối với khóa đó. Các lần đọc kế tiếp, nếu khóa vẫn tồn tại và chưa bị xóa/thay thế, có thể trở thành cache hit.

**Lưu ý:** chỉ có `GET` trả `null` không đủ để kết luận sản phẩm không tồn tại. Nó chỉ nói rằng không tìm thấy **bản sao trong Redis**. Muốn biết sản phẩm có tồn tại hay không, ứng dụng phải kiểm tra nguồn dữ liệu.

### 2.3. Cache-aside không tự động xảy ra khi có RedisTemplate

Một đoạn mã dùng `RedisTemplate`:

```java
ProductView cached = redis.opsForValue().get(key);
```

chỉ đọc Redis. RedisTemplate không tự đi truy vấn SQL khi miss, không tự ghi kết quả vào Redis và không tự quyết định TTL. **Ứng dụng phải viết rõ luồng cache-aside**, hoặc sử dụng một trừu tượng cache phù hợp để quản lý các hành vi đó.

## 3. Vòng đời đầy đủ của một khóa cache

Một khóa cache đi qua nhiều trạng thái:

```text
               Chưa tồn tại
                    │
             Request đọc dữ liệu
                    │
             GET từ Redis: miss
                    │
             Đọc nguồn dữ liệu
                    │
             SET vào Redis + TTL
                    │
                    v
              Cache có dữ liệu
                    │
        ┌───────────┼───────────────┐
        │           │               │
   Request đọc   TTL về 0      Dữ liệu nguồn
        │           │           được cập nhật
        v           v               │
       Hit       Hết hạn            DEL/invalidate
        │           │               │
        │           └───────┬───────┘
        │                   │
        └── Tiếp tục đọc    v
                     Không còn cache
                            │
                       Lần đọc sau
                            │
                       Miss và nạp lại
```

Những trạng thái quan trọng:

| Trạng thái | Hành vi của hệ thống |
|---|---|
| **Chưa có cache** | Đọc database và đưa dữ liệu vào Redis |
| **Có cache hợp lệ** | Trả dữ liệu từ Redis |
| **Khóa hết TTL** | Redis coi khóa đã hết hạn; lần đọc sau miss |
| **Khóa bị xóa chủ động** | Lần đọc sau miss và nạp dữ liệu mới |
| **Nguồn bị cập nhật nhưng cache chưa bị vô hiệu hóa** | Cache có thể tiếp tục trả dữ liệu cũ |
| **Redis không khả dụng** | Có thể chuyển sang đọc database nếu ứng dụng thiết kế đường dự phòng |
| **Nhiều request cùng miss** | Nhiều request có thể đồng thời đọc database và ghi cache |

TTL giúp giới hạn tuổi tối đa dự kiến của bản sao; **TTL không đảm bảo dữ liệu trong cache luôn mới nhất ở mọi thời điểm**.

## 4. Thiết kế khóa và giá trị trước khi viết code

### 4.1. Khóa phải có ý nghĩa, ổn định và đủ phạm vi

Có thể đặt khóa:

```text
product:detail:v1:42
```

Trong đó:

- `product`: nhóm nghiệp vụ.
- `detail`: loại dữ liệu cache, ví dụ thông tin chi tiết.
- `v1`: phiên bản cấu trúc dữ liệu trong cache.
- `42`: định danh sản phẩm.

Nếu dữ liệu khác nhau theo tenant, ngôn ngữ hoặc quyền truy cập, khóa phải phản ánh những yếu tố đó:

```text
tenant:acme:product:detail:v1:42:lang:vi
tenant:other:product:detail:v1:42:lang:vi
tenant:acme:product:detail:v1:42:lang:en
```

Nếu bỏ tenant khỏi khóa trong một hệ thống đa khách hàng, ứng dụng có thể trả dữ liệu của tenant này cho tenant khác. Với dữ liệu cá nhân hóa, không được dùng một khóa cache dùng chung cho kết quả khác nhau theo người dùng.

Không đưa thông tin bí mật như token hoặc mật khẩu trực tiếp vào tên khóa; tên khóa có thể xuất hiện trong công cụ quản trị và log.

### 4.2. Chọn giá trị cache phù hợp

Nếu API chỉ cần tên, giá và trạng thái hiển thị, cache nên chứa một **bản dữ liệu phục vụ đọc** (*read model*) ổn định, thay vì serialize toàn bộ thực thể JPA gồm quan hệ lười tải và thuộc tính nội bộ.

Ví dụ Java:

```java
package com.example.cache;

import java.math.BigDecimal;

public record ProductView(
        long id,
        String name,
        BigDecimal price,
        long version
) {
}
```

Một phiên bản dữ liệu (`version`) không bắt buộc trong mọi cache, nhưng hữu ích nếu cần phát hiện giá trị cũ khi có cập nhật đồng thời. Nó khác với `v1` trong tên khóa: `v1` biểu diễn **phiên bản schema**, còn `version` trong object có thể biểu diễn **phiên bản nội dung**.

### 4.3. TTL là chính sách nghiệp vụ

Ví dụ một sản phẩm ít thay đổi có thể cache trong 5 phút:

```redis
SET product:detail:v1:42 "{\"id\":42,\"name\":\"Bàn làm việc\"}" EX 300
```

Khi đọc:

```redis
GET product:detail:v1:42
TTL product:detail:v1:42
```

Kết quả `TTL` có thể là:

| Giá trị | Ý nghĩa |
|---|---|
| Số nguyên dương | Số giây còn lại trước khi khóa hết hạn |
| `-1` | Khóa tồn tại nhưng không có TTL |
| `-2` | Khóa không tồn tại |

Nếu dùng cache-aside cho dữ liệu có thể đổi, nên có chính sách TTL rõ ràng để giới hạn thời gian dữ liệu cũ còn xuất hiện trong trường hợp việc vô hiệu hóa bị bỏ lỡ.

## 5. Triển khai cache-aside với Spring Data Redis

Ví dụ dưới đây dùng Spring Boot, Spring Data Redis và một thành phần truy xuất dữ liệu nguồn. Để thấy rõ **ai quyết định hit, miss và ghi cache**, mã sử dụng `RedisTemplate` thay vì annotation `@Cacheable`.

### 5.1. Cấu hình RedisTemplate dùng JSON

Nếu dùng Spring Data Redis 3.x và Jackson phù hợp, có thể tạo template kiểu cụ thể:

```java
package com.example.cache;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductCacheConfiguration {

    @Bean("productCacheRedisTemplate")
    public RedisTemplate<String, ProductView> productCacheRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, ProductView> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(ProductView.class)
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

Ở đây:

- `keySerializer` quyết định cách biểu diễn tên khóa.
- `valueSerializer` chuyển `ProductView` thành JSON và đọc JSON thành đối tượng Java.
- `opsForValue()` dùng **Redis String** làm kiểu dữ liệu vật lý.
- Template không tự định nghĩa quy tắc nạp dữ liệu nguồn hoặc TTL.

Ví dụ chỉ dùng các thuộc tính có kiểu đơn giản để tập trung vào vòng đời cache. Với kiểu dữ liệu Java đặc biệt, cấu trúc lồng nhau hoặc yêu cầu schema phức tạp, phải cấu hình ObjectMapper/serializer phù hợp với phiên bản thư viện.

### 5.2. Tách nguồn dữ liệu khỏi cơ chế cache

Giả sử ứng dụng có thành phần đọc cơ sở dữ liệu trả về `ProductView`:

```java
package com.example.cache;

import java.util.Optional;

public interface ProductSource {

    Optional<ProductView> findById(long productId);
}
```

Một lớp triển khai có thể sử dụng Spring Data JPA, JDBC hoặc API dịch vụ khác. Trong bài này, `ProductSource` đại diện cho **nguồn có thẩm quyền**. Nó không biết Redis.

### 5.3. Service đọc theo đúng vòng đời cache-aside

```java
package com.example.cache;

import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private static final String KEY_PREFIX = "product:detail:v1:";

    private final RedisTemplate<String, ProductView> redis;
    private final ProductSource source;

    public ProductQueryService(
            @Qualifier("productCacheRedisTemplate")
            RedisTemplate<String, ProductView> redis,
            ProductSource source) {
        this.redis = redis;
        this.source = source;
    }

    public ProductView findById(long productId) {
        if (productId <= 0) {
            throw new IllegalArgumentException(
                    "productId phải là số dương"
            );
        }

        String key = KEY_PREFIX + productId;

        // 1. Đọc cache trước.
        ProductView cached = redis.opsForValue().get(key);

        if (cached != null) {
            // 2. Cache hit: không cần đọc database.
            return cached;
        }

        // 3. Cache miss: truy vấn nguồn có thẩm quyền.
        ProductView loaded = source.findById(productId)
                .orElseThrow(() -> new ProductNotFoundException(productId));

        // 4. Đặt TTL theo chính sách. Jitter giúp giảm
        //    khả năng nhiều khóa cùng hết hạn đồng loạt.
        long ttlSeconds = 300L
                + ThreadLocalRandom.current().nextLong(0, 61);

        redis.opsForValue().set(
                key,
                loaded,
                Duration.ofSeconds(ttlSeconds)
        );

        // 5. Trả dữ liệu vừa đọc từ nguồn.
        return loaded;
    }
}
```

Một ngoại lệ đơn giản cho trường hợp không tìm thấy:

```java
package com.example.cache;

public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(long id) {
        super("Không tìm thấy sản phẩm " + id);
    }
}
```

**Jitter TTL** là phần thời gian lệch nhỏ có kiểm soát. Trong ví dụ, TTL nằm trong khoảng 300–360 giây. Nếu cả một nhóm khóa được nạp đồng thời, chúng ít có khả năng hết hạn cùng một thời điểm hơn so với tất cả đều nhận đúng 300 giây.

### 5.4. Đọc một request diễn ra như thế nào?

Nếu khóa `product:detail:v1:42` có cache:

```text
ProductQueryService.findById(42)
    └── redis GET -> ProductView
        └── return ProductView
```

Nếu Redis không có khóa:

```text
ProductQueryService.findById(42)
    ├── redis GET -> null
    ├── source.findById(42) -> ProductView
    ├── redis SET ProductView EX 300...360
    └── return ProductView
```

Nếu nguồn dữ liệu không tìm thấy sản phẩm, ví dụ này ném `ProductNotFoundException` và **không cache kết quả không tồn tại**. Đây là lựa chọn để giữ ví dụ đơn giản; một hệ thống chịu nhiều yêu cầu tới ID không tồn tại có thể cân nhắc **negative caching** trong phần sau.

## 6. TTL không thay thế việc vô hiệu hóa cache khi cập nhật

Cache-aside có hai luồng liên quan:

- **Đọc:** `GET cache` → nếu miss thì đọc nguồn → `SET cache`.
- **Ghi:** cập nhật nguồn có thẩm quyền → vô hiệu hóa bản sao trong cache.

Giả sử sản phẩm 42 đang có giá 100 và Redis cũng lưu 100. Người quản trị đổi giá thành 120 trong database. Nếu không làm gì với Redis, request sau có thể tiếp tục nhận 100 cho tới khi cache hết TTL.

### 6.1. Vô hiệu hóa sau khi ghi thành công

Với chiến lược phổ biến **invalidate on write**:

```text
Ứng dụng                  Database                   Redis
    |                         |                        |
    | UPDATE price = 120      |                        |
    |------------------------>|                        |
    | <----- COMMIT OK -------|                        |
    |                         |                        |
    | DEL product:detail:v1:42                         |
    |------------------------------------------------->|
    | <------------------------------ deleted ---------|
    |                         |                        |
    | Request đọc mới: cache miss                       |
    |------------------------------ GET --------------->|
    | <------------------------------ null -------------|
    | SELECT sản phẩm 42     |                        |
    |------------------------>|                        |
    | <--------- price=120 ---|                        |
    | SET cache price=120                              |
    |------------------------------------------------->|
```

Ở mức mã:

```java
public void evictProduct(long productId) {
    redis.delete("product:detail:v1:" + productId);
}
```

**Thứ tự rất quan trọng:** trước tiên phải ghi thành công dữ liệu nguồn, sau đó mới xóa bản cache cũ. Nếu xóa cache rồi cập nhật database nhưng cập nhật thất bại, những request chen giữa có thể nạp lại dữ liệu cũ; bản cache sau đó vẫn tồn tại.

### 6.2. Vấn đề với giao dịch database

Nếu service cập nhật sản phẩm trong phương thức `@Transactional`, lệnh Redis được gọi ở giữa phương thức **không mặc nhiên tham gia giao dịch SQL**. Gọi `redis.delete(...)` trước khi SQL transaction commit có thể khiến request khác miss và đọc lại phiên bản database chưa được cập nhật.

Có thể công bố sự kiện ứng dụng trong transaction và xử lý vô hiệu hóa bằng listener chạy **sau khi transaction commit**:

```java
public record ProductChanged(long productId) {
}
```

Ví dụ service ghi dữ liệu nguồn:

```java
@Service
public class ProductCommandService {

    private final ProductJpaRepository products;
    private final ApplicationEventPublisher publisher;

    public ProductCommandService(
            ProductJpaRepository products,
            ApplicationEventPublisher publisher) {
        this.products = products;
        this.publisher = publisher;
    }

    @Transactional
    public void changePrice(long id, BigDecimal newPrice) {
        ProductEntity entity = products.findById(id)
                .orElseThrow();

        entity.changePrice(newPrice);

        // Sự kiện được công bố trong transaction.
        publisher.publishEvent(new ProductChanged(id));
    }
}
```

Và một listener:

```java
@Component
public class ProductCacheInvalidator {

    private final RedisTemplate<String, ProductView> redis;

    public ProductCacheInvalidator(
            @Qualifier("productCacheRedisTemplate")
            RedisTemplate<String, ProductView> redis) {
        this.redis = redis;
    }

    @TransactionalEventListener(
            phase = TransactionPhase.AFTER_COMMIT
    )
    public void onProductChanged(ProductChanged event) {
        redis.delete("product:detail:v1:" + event.productId());
    }
}
```

Cần thêm các import tương ứng từ Spring Framework và các lớp JPA thuộc dự án. Các đoạn này minh họa **điểm thực hiện invalidation sau commit**.

**Giới hạn cần biết:** `@TransactionalEventListener(AFTER_COMMIT)` không biến event thành thông điệp bền vững. Nếu tiến trình dừng ngay sau commit hoặc Redis không khả dụng, thao tác xóa cache có thể không được thực hiện. Với yêu cầu quan trọng, cần cơ chế retry bền vững, chẳng hạn outbox/queue, kết hợp TTL và quan sát lỗi.

### 6.3. Vì sao thường xóa cache thay vì ghi đè ngay giá trị mới?

Khi cập nhật dữ liệu nguồn, ứng dụng có thể:

1. **Delete cache:** xóa bản cũ; lần đọc kế tiếp nạp lại từ nguồn.
2. **Update cache:** ghi ngay bản mới vừa cập nhật.

Xóa thường đơn giản hơn vì không cần đảm bảo mọi code path cập nhật đều xây được bản cache giống nhau. Ghi cache ngay có thể giảm miss sau cập nhật nhưng dễ tạo trạng thái cũ nếu có các cập nhật đồng thời hoặc giao dịch chưa commit.

Không có quy tắc “delete luôn tốt hơn update” cho mọi hệ thống. Lựa chọn phụ thuộc tần suất ghi, độ phức tạp bản dữ liệu phục vụ đọc và yêu cầu nhất quán.

## 7. Những cuộc đua đồng thời trong vòng đời cache-aside

### 7.1. Cache stampede: nhiều request cùng miss

Giả sử một sản phẩm rất được quan tâm, khóa cache vừa hết hạn. Ngay lập tức có 200 request đọc sản phẩm đó:

```text
             cache key vừa hết hạn
                       |
        ┌──────────────┼──────────────┐
        |              |              |
     Request A      Request B      Request C ... 200
        |              |              |
       MISS           MISS           MISS
        |              |              |
        └──────────────┼──────────────┘
                       |
              Nhiều lần SELECT cùng ID
                       |
              Database có thể quá tải
```

Đây là **cache stampede** hoặc **thundering herd**: cache giúp giảm truy vấn khi hit, nhưng vào thời điểm nhiều request cùng miss, tác dụng bảo vệ database có thể biến mất.

Các hướng giảm rủi ro:

- TTL có jitter để tránh nhiều khóa hết hạn đồng thời.
- **Single-flight** trong cùng một instance: gom các yêu cầu miss cùng khóa vào một lượt nạp.
- Khóa phân tán có thời hạn khi nhiều instance cùng nạp một khóa nóng.
- Chủ động làm mới trước hết hạn (*refresh ahead*) hoặc phục vụ dữ liệu cũ có kiểm soát (*stale-while-revalidate*).
- Giới hạn số lượt nạp đồng thời và áp dụng backpressure ở tầng nguồn.
- Dùng TTL dài hơn cho dữ liệu ít thay đổi, kết hợp vô hiệu hóa khi cập nhật.

**Jitter không ngăn hoàn toàn stampede của một khóa nóng**: mọi request đang đợi đúng cùng một khóa có thể miss đồng thời. Nó chủ yếu làm phân tán thời điểm hết hạn của **nhiều khóa khác nhau**.

### 7.2. Cache penetration: liên tục hỏi các ID không tồn tại

Với code ví dụ ở trên, request tới sản phẩm 999999 luôn:

```text
Redis MISS -> Database NOT FOUND -> không ghi cache
```

Nếu nhiều request gửi cùng một ID không tồn tại, database vẫn phải xử lý chúng lặp lại.

Một lựa chọn là **negative caching**: lưu ngắn hạn một dấu hiệu “không tìm thấy”, chẳng hạn một kiểu kết quả có trạng thái rõ ràng:

```text
product:detail:missing:v1:999999 -> "NOT_FOUND" (TTL 15 giây)
```

Khi triển khai, cần phân biệt dấu hiệu này với một `ProductView` hợp lệ và với kết quả `null` do khóa Redis không tồn tại. Đừng ghi một giá trị giả rồi vô tình trả nó như sản phẩm thật.

TTL của negative cache thường nên **ngắn**, vì một ID chưa tồn tại hôm nay có thể được tạo ngay sau đó. Khi tạo mới đối tượng với ID tương ứng, ứng dụng phải vô hiệu hóa cả cache “không tìm thấy” nếu đã dùng.

### 7.3. Cuộc đua giữa nạp cache và cập nhật dữ liệu nguồn

Một trường hợp tinh vi hơn:

```text
T0: Redis không có product:42.
T1: Request A MISS, bắt đầu SELECT database (giá cũ = 100).
T2: Request B cập nhật database giá mới = 120 và COMMIT.
T3: Request B DEL product:42; cache vẫn đang trống.
T4: Request A kết thúc xử lý và SET cache giá cũ = 100.
T5: Request C đọc cache HIT, nhận giá cũ = 100.
```

Dù B đã **xóa cache sau commit**, A vẫn có thể nạp lại dữ liệu cũ **sau thời điểm xóa**. Đây là một giới hạn của cache-aside cơ bản trong hệ thống có đọc/ghi đồng thời.

Nếu dữ liệu cho phép nhất quán cuối cùng (*eventual consistency*), TTL tương đối ngắn có thể giới hạn khoảng thời gian sai lệch. Nếu cần ngăn việc ghi lại giá trị cũ, có thể thiết kế:

- Phiên bản dữ liệu và kiểm tra phiên bản khi ghi cache.
- Khóa/phiên bản namespace thay đổi khi có cập nhật; lượt đọc cũ ghi vào key version cũ không còn được truy cập.
- Đồng bộ việc nạp cache và cập nhật theo khóa trong phạm vi cần thiết.
- Cơ chế cache chuyên biệt có bảo đảm tính nhất quán mạnh hơn hoặc bỏ cache cho đường đọc quan trọng.

**Chỉ dùng DEL sau commit và TTL không tạo ra tính nhất quán mạnh.** Những yêu cầu như kiểm tra số dư, khấu trừ tồn kho hoặc quyết định cấp quyền cần tham chiếu nguồn có thẩm quyền hay cơ chế giao dịch phù hợp.

## 8. Khi Redis gặp sự cố: đọc từ nguồn có được không?

Cache phục vụ tối ưu đọc. Với nhiều API, khi Redis tạm thời không truy cập được, ứng dụng có thể **đọc trực tiếp database** để duy trì dịch vụ. Tuy nhiên điều này cần được chủ động thiết kế:

```text
Request
   |
Redis GET
   |
   +-- HIT -------------> trả cache
   |
   +-- MISS ------------> Database -> SET cache -> trả dữ liệu
   |
   +-- Redis lỗi -------> Database -------------> trả dữ liệu
```

Một ví dụ giới hạn phạm vi fallback cho **lỗi kết nối Redis**:

```java
public ProductView findByIdWithCacheFallback(long id) {
    String key = "product:detail:v1:" + id;
    boolean redisReachable = true;

    try {
        ProductView cached = redis.opsForValue().get(key);

        if (cached != null) {
            return cached;
        }
    } catch (RedisConnectionFailureException ex) {
        redisReachable = false;
        // Ghi metric/log lỗi Redis; hạn chế log từng request.
    }

    ProductView loaded = source.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id));

    if (redisReachable) {
        try {
            redis.opsForValue().set(
                    key, loaded, Duration.ofMinutes(5)
            );
        } catch (RedisConnectionFailureException ex) {
            // Dữ liệu nguồn đã đọc thành công: trả cho caller.
            // Ghi metric/log; không coi ghi cache là ghi nghiệp vụ.
        }
    }

    return loaded;
}
```

Import ngoại lệ: `org.springframework.data.redis.RedisConnectionFailureException`. Ví dụ đặt trong một service đã có `redis` và `source` từ constructor như phần trước.

Điều cần lưu ý:

- **Không nuốt mọi `Exception`** khi truy cập Redis. Lỗi serializer, lỗi lập trình, sai kiểu dữ liệu hoặc dữ liệu cache bị hỏng cần được phát hiện và xử lý thích hợp.
- Khi Redis hỏng, nhiều request cùng đi xuống database có thể gây quá tải. Cần giới hạn đồng thời, timeout phù hợp, circuit breaker hoặc chính sách giảm tải.
- Với tác vụ cache yêu cầu dữ liệu nhạy cảm hoặc hợp đồng nhất quán đặc biệt, không nên bật fallback chỉ vì “cache là tùy chọn” mà chưa xem xét nghiệp vụ.
- Lỗi kết nối **khác** với cache miss. Trên dashboard, phải có metric riêng cho Redis errors.

## 9. Cache-aside không phải giao dịch với database

Một số thao tác nhìn giống giao dịch nhưng thực tế khác:

| Hoạt động | Có cùng giao dịch với database không? |
|---|---|
| `source.findById(id)` rồi `redis.opsForValue().set(...)` | Không tự động |
| `@Transactional` quanh cập nhật JPA rồi `redis.delete(key)` | Redis không mặc nhiên tham gia transaction SQL |
| `@TransactionalEventListener(AFTER_COMMIT)` để xóa cache | Chạy sau commit, nhưng không bảo đảm delivery bền vững |
| `WATCH/MULTI/EXEC` trong Redis | Giao dịch Redis; không tự bao trùm database ngoài Redis |
| TTL hết hạn | Sự kiện vòng đời của khóa Redis, không phải transaction SQL |

Do vậy, cần quyết định rõ **ranh giới tính nhất quán**: đọc cache có chấp nhận trễ vài giây/phút so với nguồn hay không? Nếu không, cấu trúc cache-aside cơ bản có thể không phù hợp cho dữ liệu đó.

Ví dụ danh mục sản phẩm hiển thị có thể chấp nhận trễ nhỏ. Còn nghiệp vụ trừ tiền hoặc xác nhận thanh toán thường cần kiểm tra dữ liệu chính xác từ nguồn có thẩm quyền vào thời điểm thực hiện giao dịch.

## 10. So sánh cache-aside với những chiến lược gần nó

| Chiến lược | Ai quyết định đọc cache? | Khi nào cache được nạp? | Khi ghi dữ liệu nguồn |
|---|---|---|---|
| **Cache-aside** | Ứng dụng | Khi đọc bị miss | Ứng dụng thường invalidates cache |
| **Read-through** | Tầng cache tích hợp loader | Cache tự gọi nguồn khi miss | Phụ thuộc thiết kế cache/loader |
| **Write-through** | Ứng dụng thông qua tầng cache | Khi ghi dữ liệu | Ghi cache và nguồn theo cơ chế của tầng cache |
| **Write-behind/write-back** | Tầng cache | Theo dòng ghi | Cache nhận ghi trước, đẩy xuống nguồn sau |
| **Cache refresh ahead** | Cơ chế làm mới | Trước khi TTL hết hạn | Thường kết hợp chiến lược invalidation riêng |

Cache-aside dễ áp dụng với `RedisTemplate` vì code service có toàn quyền kiểm soát. Đổi lại, các service phải thống nhất chính sách key, TTL, invalidation, lỗi và quan sát hiệu quả.

### Spring Cache abstraction có liên quan thế nào?

Spring cung cấp `@Cacheable`, `@CachePut`, `@CacheEvict` và cơ chế `CacheManager`. Ví dụ:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductView getProduct(long productId) {
    return source.findById(productId)
            .orElseThrow();
}
```

Với `RedisCacheManager` được cấu hình, đường đọc có thể có hành vi tương tự cache-aside: kiểm tra cache trước, gọi phương thức nguồn khi miss, rồi lưu kết quả. Nhưng annotation không tự giải quyết mọi tình huống như stampede giữa các instance, invalidation sau commit, tính nhất quán xuyên hệ thống hoặc chính sách lỗi.

**Hai cách triển khai khác nhau:** ví dụ `RedisTemplate` trong bài minh họa cache-aside **thủ công**; ví dụ `@Cacheable` minh họa việc để Spring Cache abstraction điều phối. Chọn một cơ chế rõ ràng cho cùng đường đọc để tránh vô tình cache hai lớp với những TTL và khóa khác nhau.

## 11. Chọn TTL và chiến lược invalidation

TTL phụ thuộc vào mức độ dữ liệu thay đổi và sự chấp nhận dữ liệu cũ:

| Loại dữ liệu | Đặc điểm | Hướng thiết kế |
|---|---|---|
| Danh mục gần như tĩnh | Ít cập nhật | TTL dài, invalidation khi xuất bản |
| Giá niêm yết | Có cập nhật, cần hạn chế giá cũ | TTL vừa/ngắn và invalidation sau commit |
| Kết quả tìm kiếm tốn chi phí | Tạo ra từ nhiều bản ghi | TTL có giới hạn, khóa chứa tham số truy vấn |
| Phiên đăng nhập | Có ý nghĩa bảo mật và thu hồi | Kiểm tra nghiệp vụ, TTL phù hợp; không dựa độc quyền vào cache-aside |
| Tồn kho thời gian thực | Cạnh tranh cập nhật cao | Dữ liệu nguồn và thao tác kiểm soát đồng thời là quyết định cuối |

Một số gợi ý:

1. **TTL là phương án dự phòng** khi invalidation không xảy ra hoặc bị thất bại. Không coi nó là thông báo dữ liệu đã đổi.
2. **Invalidation theo phạm vi:** nếu cập nhật sản phẩm 42, chỉ xóa những khóa liên quan, trừ khi nghiệp vụ thật sự yêu cầu toàn bộ danh mục.
3. **TTL có jitter:** giảm việc hàng loạt khóa cùng hết hạn khi đã nạp theo một đợt.
4. **Schema version trong khóa:** khi thay đổi cấu trúc serialization, chuyển sang namespace mới để tránh các bản cache cũ không tương thích.
5. **Không có một TTL “tối ưu chung”:** phải đo tỷ lệ hit, tải database và mức dữ liệu cũ chấp nhận được.

## 12. Quan sát và đo hiệu quả cache-aside

Chỉ có Redis hoạt động chưa chứng minh cache mang lại lợi ích. Nên đo ít nhất:

| Chỉ số | Câu hỏi cần trả lời |
|---|---|
| **Cache hit** | Bao nhiêu lần đọc tìm thấy dữ liệu trong cache? |
| **Cache miss** | Bao nhiêu lần đọc phải truy vấn nguồn? |
| **Hit ratio** | Tỷ lệ đọc có thể phục vụ từ cache là bao nhiêu? |
| **Load latency** | Mất bao lâu để đọc database khi miss? |
| **Cache read/write latency** | Redis có nhanh đủ so với nguồn không? |
| **Redis errors** | Bao nhiêu lần bị timeout, mất kết nối hoặc giải mã lỗi? |
| **Database QPS** | Số truy vấn nguồn có giảm thực sự không? |
| **Stale reads** | Có dữ liệu cũ ngoài khoảng cho phép không? |
| **Evictions/expired keys** | Các khóa bị đẩy ra do áp lực bộ nhớ hay hết TTL? |
| **Heap, CPU, network** | Việc serialization/cache có tạo nút cổ chai mới không? |

Tỷ lệ hit cơ bản:

```text
Hit ratio = hits / (hits + misses)
```

Ví dụ 8.000 hit và 2.000 miss thì hit ratio là 80%. Không cộng lỗi kết nối Redis vào số miss một cách mơ hồ: lỗi và miss phản ánh nguyên nhân khác nhau.

Tùy mục tiêu, có thể bổ sung **tỷ lệ đọc nguồn** và **thời gian p95/p99 của request**. Hit ratio cao nhưng cache trả các giá trị JSON quá lớn vẫn có thể không mang lại trải nghiệm như mong muốn.

### 12.1. Phân biệt cold cache và warm cache

- **Cold cache:** hầu hết khóa chưa có; ứng dụng phải đọc nguồn nhiều.
- **Warm cache:** nhiều khóa có sẵn; request có khả năng hit.
- **Mixed workload:** phản ánh thực tế hơn, khi có TTL, thêm/xóa và thay đổi dữ liệu.

Nếu chỉ benchmark warm cache 100% hit, bạn chưa đo được tải database khi cache hết hạn. Nếu chỉ benchmark cold cache, bạn cũng chưa thấy phần lợi ích trong điều kiện thường ngày.

### 12.2. Kiểm tra ảnh hưởng khi Redis không khả dụng

Một kịch bản vận hành cần thử trong môi trường kiểm soát:

```text
Redis hoạt động:
    API -> Redis hit/miss -> database khi cần

Redis không khả dụng:
    API -> lỗi Redis -> database fallback
                          |
                     xem DB QPS/p99
```

Khi bật fallback, cơ sở dữ liệu có thể phải chịu toàn bộ traffic mà Redis trước đó đã hấp thụ. Cần xác định giới hạn, timeout, khả năng giảm tải và thời gian khôi phục.

## 13. Thực hành theo dõi vòng đời của một khóa

Có thể thực hiện trên Redis phát triển, dùng một namespace tách biệt.

### Bước 1: Xóa dữ liệu cache cũ của bài tập

```redis
DEL demo:product:42
```

Xác nhận:

```redis
GET demo:product:42
```

Redis trả `nil`: cache miss.

### Bước 2: Giả lập lấy dữ liệu nguồn và ghi cache

```redis
SET demo:product:42 "{\"id\":42,\"name\":\"Bàn làm việc\",\"price\":100}" EX 60
```

Lệnh này tương đương phần “ghi kết quả đã lấy từ database” trong luồng cache-aside.

### Bước 3: Đọc lại và quan sát TTL

```redis
GET demo:product:42
TTL demo:product:42
```

`GET` trả dữ liệu: cache hit. `TTL` trả số giây còn lại, giảm theo thời gian.

### Bước 4: Giả lập cập nhật nguồn

Trong ứng dụng thật, hãy cập nhật database trước, commit thành công, rồi invalidates cache:

```redis
DEL demo:product:42
```

Lần đọc tiếp theo:

```redis
GET demo:product:42
```

sẽ miss. Ứng dụng sẽ lấy phiên bản mới từ nguồn rồi:

```redis
SET demo:product:42 "{\"id\":42,\"name\":\"Bàn làm việc\",\"price\":120}" EX 60
```

### Bước 5: Quan sát tự hết hạn

Đợi sau thời hạn đã đặt hoặc dùng khóa thử với TTL rất ngắn:

```redis
SET demo:short-lived "value" EX 3
TTL demo:short-lived
```

Sau khi hết hạn, `GET demo:short-lived` trả `nil` và `TTL` thường trả `-2`.

Mục tiêu bài thực hành là nhận biết vòng đời: **không có khóa → miss → nạp → hit → invalidate/expire → miss → nạp lại**.

## 14. Các lỗi thường gặp và cách suy nghĩ để xử lý

### Lỗi 1: Coi Redis là nguồn dữ liệu chính thức

Cache thường có TTL và có thể bị eviction do áp lực bộ nhớ. Nếu cache chỉ là bản sao của database, không được dùng sự tồn tại của khóa để thay thế các ràng buộc nghiệp vụ hoặc giao dịch nguồn.

### Lỗi 2: Không đặt TTL

Cache cũ có thể tồn tại rất lâu nếu invalidation bị bỏ lỡ. TTL cần phản ánh mức độ chấp nhận dữ liệu cũ; không mặc định lưu vô hạn.

### Lỗi 3: Không xóa cache sau cập nhật database

Dữ liệu nguồn đã đổi nhưng Redis vẫn trả bản cũ cho tới khi hết hạn. Xây dựng luồng invalidation sau khi cập nhật thành công.

### Lỗi 4: Xóa cache trước khi transaction commit

Request khác có thể miss rồi đọc lại database cũ. Xác định ranh giới commit và xử lý xóa cache sau commit; với yêu cầu nghiêm ngặt, cần cơ chế bền vững và nhất quán bổ sung.

### Lỗi 5: Cho rằng xóa cache sau commit ngăn mọi dữ liệu cũ

Một request đang miss có thể đọc dữ liệu cũ rồi `SET` sau khi thao tác xóa hoàn tất. Đây là race condition riêng; xử lý bằng versioning/đồng bộ thích hợp nếu yêu cầu.

### Lỗi 6: Bỏ qua stampede

Một khóa hot hết hạn có thể làm nhiều request đồng thời gọi database. Cân nhắc single-flight, khóa phân tán, refresh ahead hoặc giới hạn đồng thời.

### Lỗi 7: Cache dữ liệu không tồn tại quá lâu

Negative cache có thể làm ứng dụng tiếp tục trả “không tìm thấy” sau khi đối tượng được tạo mới. Dùng TTL ngắn và invalidation lúc tạo nếu cần.

### Lỗi 8: Dùng một khóa cho mọi người dùng hoặc tenant

Nếu kết quả phụ thuộc ngôn ngữ, tenant, quyền hoặc cấu hình, khóa phải chứa đủ những chiều đó. Thiết kế khóa sai có thể gây rò rỉ dữ liệu.

### Lỗi 9: Truyền thẳng JPA entity vào JSON serializer

Quan hệ lười tải, vòng tham chiếu, trường nội bộ và thay đổi schema có thể gây lỗi hoặc tạo payload lớn. Dùng read model/DTO phù hợp.

### Lỗi 10: Nuốt mọi lỗi Redis

Lỗi kết nối có thể cho phép fallback, nhưng lỗi serializer hoặc sai định dạng dữ liệu cần được phát hiện. Không coi tất cả ngoại lệ Redis là cache miss.

### Lỗi 11: Đo hiệu quả chỉ bằng hit ratio

Hit ratio cao nhưng JSON rất lớn hoặc Redis ở xa vẫn có thể gây độ trễ. Cần đo p95/p99, QPS database, lỗi và tài nguyên.

### Lỗi 12: Giữ cache cho dữ liệu cần chính xác tức thời

Các quyết định như trừ tồn kho, thanh toán hoặc phân quyền cần kiểm tra nguồn dữ liệu có thẩm quyền và cơ chế đồng thời phù hợp. Cache-aside có thể hỗ trợ hiển thị, nhưng không tự đảm bảo tính nhất quán mạnh.

## 15. Câu hỏi tự kiểm tra

**1. Khi Redis trả `null`, có thể kết luận sản phẩm không tồn tại không?**

Không. Đây là cache miss; phải kiểm tra nguồn có thẩm quyền.

**2. Lần đầu đọc một khóa có cache-aside sẽ diễn ra như thế nào?**

Ứng dụng kiểm tra Redis, miss, đọc database, ghi dữ liệu vào cache với TTL, rồi trả dữ liệu.

**3. Cache hit có truy vấn database không?**

Trong luồng cache-aside cơ bản, cache hit cho phép trả dữ liệu ngay mà không cần truy vấn nguồn cho lần đọc đó.

**4. Vì sao vẫn nên đặt TTL nếu đã xóa cache sau mỗi lần cập nhật?**

Vì invalidation có thể bị lỗi hoặc bỏ lỡ; TTL giúp giới hạn thời gian tồn tại của dữ liệu cũ.

**5. Khi database transaction chưa commit, có nên xóa cache ngay không?**

Cần thận trọng. Request khác có thể nạp lại dữ liệu cũ. Thông thường nên invalidates sau commit thành công, đồng thời tính đến khả năng sự kiện/xóa thất bại.

**6. Hai request cùng miss một khóa thì điều gì xảy ra?**

Cả hai có thể cùng đọc database và ghi cache. Với nhiều request cùng lúc, đây là nguy cơ cache stampede.

**7. Xóa cache sau commit có loại bỏ mọi race condition không?**

Không. Một request đọc nguồn cũ có thể ghi lại cache sau khi request cập nhật đã xóa cache. Nếu cần bảo đảm cao hơn phải thiết kế versioning hoặc cơ chế đồng bộ khác.

**8. Khi Redis mất kết nối, ứng dụng có thể tiếp tục đọc database không?**

Có thể, nếu đường đọc được thiết kế fallback và database đủ khả năng chịu tải. Cần phân biệt lỗi kết nối với lỗi dữ liệu hoặc lỗi serializer.

**9. Hit ratio 90% có đủ chứng minh cache tốt không?**

Không. Phải đánh giá độ trễ API, byte truyền, chi phí serializer, tải database và dữ liệu cũ.

**10. Khi nào không nên lấy dữ liệu cache làm điều kiện quyết định cuối cùng?**

Khi nghiệp vụ yêu cầu trạng thái cập nhật tức thời hoặc tính nhất quán mạnh, chẳng hạn thanh toán, khấu trừ số dư, kiểm tra quyền hay tồn kho cuối cùng.

## 16. Những điểm cần ghi nhớ

- **Cache-aside** là chiến lược ứng dụng chủ động **đọc cache trước, đọc nguồn khi miss, rồi đưa kết quả vào cache**.
- **Redis giữ bản sao phục vụ đọc**; nguồn có thẩm quyền vẫn quyết định dữ liệu chính xác.
- Vòng đời cache gồm **miss → load → set TTL → hit → expire/invalidate → miss**, nhưng nhiều request đồng thời có thể khiến luồng này phức tạp hơn.
- Khi nguồn thay đổi, thường **vô hiệu hóa cache sau commit**. TTL là hàng rào giới hạn tuổi dữ liệu, không phải cơ chế đồng bộ tuyệt đối.
- Cần xử lý **stampede, negative caching, race condition giữa load và invalidate, lỗi Redis và key design** theo mức nhất quán nghiệp vụ yêu cầu.
- Đánh giá hiệu quả bằng **hit/miss, độ trễ, QPS database, bộ nhớ và dữ liệu cũ**, không chỉ bằng tốc độ `GET` của Redis.

### Tài liệu tham khảo

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html).
- [Redis — GET](https://redis.io/docs/latest/commands/get/).
- [Redis — SET](https://redis.io/docs/latest/commands/set/).
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/).
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/).
