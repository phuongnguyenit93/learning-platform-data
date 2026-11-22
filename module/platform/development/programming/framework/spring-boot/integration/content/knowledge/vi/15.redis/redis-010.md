# Phân biệt dùng Redis cho dữ liệu, cache, phiên và hàng đợi

> **Chương:** Redis  
> **Module:** SPRING_BOOT_INTEGRATION — tổ chức tích hợp hệ thống trong Spring Boot qua HTTP client, cơ sở dữ liệu, cache, broker thông điệp và adapter Spring Integration; chú trọng hợp đồng dữ liệu, cấu hình, giao dịch, lỗi, trùng lặp, kiểm thử và quan sát.  
> **Mục tiêu:** Chọn đúng vai trò của Redis, xác định nguồn sự thật và giải thích cách bảo vệ dữ liệu khi Redis, ứng dụng hoặc dịch vụ downstream gặp sự cố.

Redis là một hệ thống lưu trữ dữ liệu dạng key–value trong bộ nhớ, hỗ trợ String, Hash, List, Set, Sorted Set, Stream và nhiều kiểu dữ liệu khác. Redis có thể đảm nhiệm vai trò **data store**, **cache**, **session store** hoặc **queue**. Cùng một công nghệ nhưng yêu cầu mất dữ liệu, thời gian sống, tính nhất quán và xử lý lỗi của bốn vai trò rất khác nhau.

Ví dụ trong hệ thống bán hàng dùng Spring Boot:

- PostgreSQL lưu sản phẩm và đơn hàng; Redis giữ **bản sao cache** của sản phẩm để giảm tải đọc.
- Redis lưu **phiên đăng nhập web**, giúp nhiều instance Spring Boot dùng chung trạng thái HttpSession.
- Dịch vụ đơn hàng tạo **email job**; worker nhận job từ Redis Streams để gửi email bất đồng bộ.
- Redis quản lý **bộ đếm lượt xem**, bảng xếp hạng, trạng thái ngắn hạn hoặc rate limiting.

Nếu Redis xóa một khóa cache, hệ thống có thể đọc lại PostgreSQL. Nếu Redis xóa session, người dùng có thể phải đăng nhập lại. Nếu Redis mất message đang chờ xử lý, nghiệp vụ có thể bị bỏ sót. Nếu Redis giữ dữ liệu gốc không có bản sao nào khác, sự cố có thể làm mất dữ liệu nghiệp vụ. Vì vậy trước khi chọn một API Redis, hãy hỏi: **Nếu key này biến mất, tác động thực tế là gì?**

## 1. Bốn vai trò khác nhau ở đâu?

| Vai trò | Dữ liệu chứa trong Redis | Nguồn sự thật | Vòng đời | Rủi ro khi mất key |
| --- | --- | --- | --- | --- |
| **Data store** | Bộ đếm, tập, trạng thái nghiệp vụ, ranking, dữ liệu nóng | Có thể là chính Redis | Theo nghiệp vụ, có thể không TTL | Có thể mất thông tin gốc hoặc phải khôi phục backup |
| **Cache** | Bản sao kết quả từ DB/API hoặc dữ liệu tính toán lại được | DB/API/tập dữ liệu gốc | TTL hoặc invalidation | Cache miss, tăng độ trễ và tải nguồn |
| **Session** | Session ID và thuộc tính phiên đang hoạt động | Redis quản lý phiên; danh tính lâu dài thường ở user DB/IdP | Idle timeout, logout, revoke | Mất phiên, phải xác thực lại |
| **Queue** | Command/event/job chờ worker | Tùy thiết kế; có thể là Stream hoặc DB/outbox | ACK, retry, retention | Mất việc, xử lý lặp hoặc backlog kẹt |

**Từ khóa để quyết định:** khả năng tái tạo, yêu cầu bền vững, giới hạn độ trễ nhất quán, xử lý lỗi một phần và hợp đồng thời hạn. Không nên đánh đồng một Redis key có TTL với cache: session và idempotency key cũng có TTL nhưng mang ý nghĩa nghiệp vụ khác.

~~~mermaid
flowchart LR
    C["Client"] --> A["Spring Boot API"]
    A --> P[("PostgreSQL<br/>Orders, Products")]
    A <--> CA[("Redis<br/>Cache")]
    A <--> SE[("Redis<br/>Sessions")]
    A <--> DA[("Redis<br/>Counters / Rankings")]
    A --> ST[("Redis Streams<br/>Jobs")]
    ST --> W["Async Worker"]
    W --> X["Email / Payment API"]
~~~

Đây là sơ đồ **vai trò logic**, không yêu cầu tất cả dùng một Redis instance. Trong production có thể tách cache khỏi session và queue để giảm việc chia sẻ tài nguyên, eviction và failure domain.

## 2. Redis làm data store: lưu dữ liệu vận hành và nghiệp vụ

Với vai trò data store, ứng dụng ghi trực tiếp dữ liệu vào Redis và có thể không có nguồn nào khác để dựng lại. Những trường hợp thường gặp:

- **INCR** cho lượt xem và bộ đếm giới hạn yêu cầu.
- **SADD / SISMEMBER** cho tập thành viên, key đang hoạt động.
- **ZADD / ZREVRANGE** cho bảng xếp hạng.
- **HSET / HGETALL** cho trạng thái gọn có nhiều trường.
- Trạng thái tạm thời như OTP challenge hoặc dấu hiệu xử lý ngắn hạn.

Ví dụ bộ đếm:

~~~bash
INCR product:SKU-42:views
GET product:SKU-42:views
~~~

**INCR** là phép tăng nguyên tử trên một key, an toàn hơn việc GET → cộng ở Java → SET trong điều kiện nhiều request. Tuy nhiên, **nguyên tử thao tác không đồng nghĩa bền vững khi máy hỏng**. Giá trị vừa tăng vẫn có thể bị mất trong cửa sổ persistence hoặc replication.

Ví dụ Spring Data Redis:

~~~java
package example.integration.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductViewCounter {
    private final StringRedisTemplate redis;

    public ProductViewCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long recordView(String sku) {
        // Validate/normalize sku trước khi tạo key thực tế.
        return redis.opsForValue().increment(
                "product:" + sku + ":views");
    }
}
~~~

Mã ví dụ giả định ứng dụng đã có **spring-boot-starter-data-redis** và RedisConnectionFactory phù hợp. Hãy kiểm tra null/error theo hợp đồng API và kiểm soát đầu vào để tránh tạo key vô hạn. Nếu số lượt xem là thống kê xấp xỉ, mất một số lần đếm có thể được chấp nhận; nếu là số dư tài chính, không nên áp dụng cùng cách quyết định.

### 2.1. Persistence và failover

| Cơ chế | Chức năng | Giới hạn cần hiểu |
| --- | --- | --- |
| **RDB snapshot** | Lưu snapshot định kỳ | Có thể mất cập nhật sau snapshot gần nhất |
| **AOF (Append Only File)** | Ghi log lệnh để phục hồi | fsync policy tạo đánh đổi hiệu năng và cửa sổ mất dữ liệu; everysec có thể mất cập nhật gần sự cố |
| **Replication** | Đồng bộ primary sang replica | Thông thường bất đồng bộ; failover có thể mất write chưa replicate |
| **Sentinel** | Phát hiện sự cố, bầu primary và điều phối failover | Không biến Redis thành hệ thống nhất quán mạnh hoặc loại bỏ mất write |
| **Redis Cluster** | Shard theo hash slot và failover | Giới hạn thao tác nhiều key khác slot; replication/failover vẫn có cửa sổ lỗi |
| **Backup/restore** | Khôi phục sau mất dữ liệu và lỗi thao tác | Cần RPO/RTO và diễn tập restore định kỳ |

Nếu Redis là **nguồn dữ liệu chính** và yêu cầu không mất dữ liệu cao, phải thiết kế persistence, backup, giám sát và phương án phục hồi có kiểm chứng. RDB/AOF và replica làm giảm rủi ro, nhưng không tự biến Redis thành transaction manager chung cho PostgreSQL, HTTP hoặc message broker.

### 2.2. Tính nguyên tử trong Redis

Redis hỗ trợ **MULTI/EXEC**, **WATCH** và Lua script để phối hợp nhiều thao tác trong Redis:

- **MULTI/EXEC** thực thi chuỗi lệnh không bị xen bởi lệnh client khác, nhưng **không rollback toàn bộ lệnh đã chạy** khi một lệnh lỗi lúc thực thi.
- **WATCH** dùng optimistic concurrency; transaction có thể không thực hiện nếu key theo dõi thay đổi trước EXEC.
- **Lua script** thực thi logic Redis nguyên tử trong phạm vi phù hợp, nhưng script lâu có thể chặn xử lý lệnh.
- Trong **Redis Cluster**, các thao tác nhiều key phải tuân theo giới hạn hash slot (có thể dùng hash tag để các key liên quan cùng slot).

**@Transactional** dùng cho JDBC/JPA không tự mở transaction phân tán với Redis. Nếu method vừa ghi PostgreSQL vừa gọi Redis, hai side effect có thể commit không đồng thời và cần cơ chế đối soát/bù trừ riêng.

## 3. Redis làm cache: tăng hiệu năng, chấp nhận khả năng stale

Cache chứa bản sao **có thể tái tạo** từ DB, API hoặc phép tính. Mẫu phổ biến là **cache-aside**:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Product Service
    participant R as Redis Cache
    participant D as PostgreSQL
    C->>A: GET /products/SKU-42
    A->>R: GET product:SKU-42
    alt Cache hit
        R-->>A: Product
    else Cache miss
        R-->>A: nil
        A->>D: SELECT product
        D-->>A: Product
        A->>R: SET product with TTL
    end
    A-->>C: Product
~~~

Khi DB cập nhật, cache có thể chứa bản cũ. TTL chỉ **giới hạn thời gian tồn tại**, không bảo đảm cache đồng bộ tức thì. Những endpoint có quy tắc read-your-writes hoặc invariant quan trọng phải lựa chọn đọc nguồn chính, invalidation sau commit, versioning hoặc phương pháp nhất quán phù hợp.

### 3.1. Spring Cache với RedisCacheManager

Trong Spring Boot, Spring Cache abstractions có thể dùng RedisCacheManager; ví dụ cấu hình:

~~~java
package example.integration.redis;

import java.time.Duration;
import java.util.Map;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class ProductCacheConfiguration {
    @Bean
    CacheManager cacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(Map.of(
                        "products", defaults.entryTtl(Duration.ofMinutes(15))))
                .build();
    }
}
~~~

Ví dụ đọc:

~~~java
package example.integration.redis;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#sku")
    public ProductDto findBySku(String sku) {
        return repository.findBySku(sku)
                .orElseThrow(() -> new ProductNotFoundException(sku));
    }
}
~~~

**ProductRepository**, **ProductDto** và **ProductNotFoundException** là các thành phần nghiệp vụ ví dụ. Với proxy mode thông thường, gọi method **@Cacheable** từ chính bean (self-invocation) không tự kích hoạt cache advice. Kiểm tra key, serializer, TTL và kết quả lỗi/trống theo hợp đồng.

Ví dụ invalidation khi cập nhật:

~~~java
@CacheEvict(cacheNames = "products", key = "#sku")
public void updateProduct(String sku, UpdateProductCommand command) {
    repository.update(sku, command);
}
~~~

**Cẩn trọng:** proxy cache và transaction DB không tự thành một commit nguyên tử. Nếu DB rollback hoặc tiến trình chết giữa DB commit và cache eviction, cache có thể stale. Với yêu cầu cao, tổ chức invalidation **sau DB commit** và có cơ chế retry/outbox event cho các cache nằm ngoài transaction.

### 3.2. Cache thường lỗi như thế nào?

| Vấn đề | Triệu chứng | Biện pháp |
| --- | --- | --- |
| **Cache stampede** | Nhiều request cùng miss một key nóng và đổ về DB | TTL jitter, single-flight, proactive refresh, kiểm soát fallback |
| **Cache penetration** | Đọc liên tục các key không tồn tại | Validate input, rate limit, negative caching TTL ngắn |
| **Cache avalanche** | Nhiều key hết hạn cùng lúc hoặc Redis lỗi | Phân tán TTL, warming, giới hạn tải DB |
| **Stale value** | Trả dữ liệu cũ sau write | Invalidation sau commit, version hoặc TTL phù hợp |
| **Eviction pressure** | Hit rate giảm và DB quá tải | Memory budget, eviction policy, theo dõi evicted_keys |

Cache không sẵn sàng cần có hành vi được định nghĩa rõ. Đọc DB thay thế thường khả thi nhưng phải bảo vệ nguồn bằng timeout, backpressure hoặc circuit breaker, nhất là khi nhiều node đều đồng loạt mất cache.

## 4. Redis làm session store với Spring Session

**Spring Session Data Redis** có thể lưu phiên web ở Redis, giúp nhiều instance Spring Boot đọc cùng một session ID từ cookie của trình duyệt.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Spring Boot Node A
    participant R as Redis Sessions
    participant C as Spring Boot Node B
    B->>A: Login / request
    A->>R: Tạo session và attributes
    A-->>B: Set-Cookie với session ID
    B->>C: Request sau với cookie
    C->>R: Đọc session theo ID
    R-->>C: Session attributes
    C-->>B: Response theo phiên
~~~

Redis lưu **phiên đang hoạt động**; thông tin tài khoản, password hash, lịch sử thanh toán hoặc quyền sở hữu dữ liệu thường ở database/identity provider. Nếu session key hết hạn hoặc biến mất, không thể coi một cache miss rồi tự tái tạo trạng thái đăng nhập như khi đọc lại sản phẩm.

### 4.1. Spring Boot MVC và HttpSession

Thêm **Spring Session Data Redis**, Redis starter và cấu hình kết nối tương ứng với phiên bản Spring Boot. Ví dụ:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379

server:
  servlet:
    session:
      timeout: 30m
~~~

Khi Spring Session Redis được cấu hình/auto-configure đúng cách cho Servlet stack, controller có thể dùng **HttpSession**:

~~~java
package example.integration.redis;

import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionDemoController {
    @GetMapping("/session/visits")
    public int visits(HttpSession session) {
        Integer visits = (Integer) session.getAttribute("visits");
        int next = visits == null ? 1 : visits + 1;
        session.setAttribute("visits", next);
        return next;
    }
}
~~~

Đây là ví dụ **Spring MVC/Servlet**. Với **Spring WebFlux**, cần **WebSession** và Spring Session reactive phù hợp. Với REST API stateless dùng token tự kiểm chứng, server-side session có thể không cần thiết.

### 4.2. TTL, cookie và bảo mật

- Timeout phiên thường dựa trên thời gian không hoạt động; **Spring Session** quản lý các key và expiry cần thiết. Không sửa TTL key Spring Session bằng script cache chung.
- Cookie phiên nên được bảo vệ bằng **Secure**, **HttpOnly**, **SameSite** phù hợp, TLS và chính sách CSRF theo cơ chế xác thực.
- Sau login/đổi mức xác thực, dùng Spring Security để xử lý **session fixation protection**, đổi session ID hoặc invalidation.
- Chỉ lưu thuộc tính phiên thực sự cần; tránh token dài hạn, dữ liệu cá nhân hoặc object graph lớn.
- Khi deploy phiên bản mới, serializer và DTO trong session cần tương thích với các session cũ.
- Nếu Redis bị evict key hoặc failover mất dữ liệu, phiên có thể mất trước timeout; thiết kế UX xác thực lại an toàn.

Không đặt session quan trọng trên cùng instance cache với **allkeys-lru** mà chưa đánh giá ảnh hưởng. Cache có thể bị evict để tăng hiệu năng; session eviction lại khiến người dùng mất trạng thái xác thực. Redis logical DB index cũng không tách riêng RAM/CPU hoặc failure domain.

## 5. Redis làm hàng đợi: Pub/Sub, List hay Streams?

Redis có nhiều cách truyền thông điệp nhưng **độ tin cậy khác nhau**:

| Cách dùng | Khi consumer offline | Xác nhận/khôi phục | Phù hợp |
| --- | --- | --- | --- |
| **Pub/Sub** | Message đang phát sẽ bị bỏ lỡ | Không có ACK và replay built-in | Tín hiệu thời gian thực không bắt buộc lưu |
| **List + LPUSH/BRPOP** | Phần tử chưa pop còn trong list nếu Redis giữ được dữ liệu | Pop xong worker chết có thể mất task | Queue đơn giản, yêu cầu reliability thấp |
| **List + BLMOVE** | Có thể chuyển task từ ready sang processing | Phải tự xây ACK, timeout, reclaim | Queue nhỏ cần tự kiểm soát failure |
| **Redis Streams** | Record có thể ở lại theo retention/persistence | Consumer group, PEL, XACK, claim pending | Công việc bất đồng bộ có retry/replay |
| **Sorted Set** | Entry chờ đến mốc thời gian | Tự xây claim/ACK và đồng bộ worker | Delayed queue đơn giản |

**Pub/Sub không phải durable queue:** subscriber vắng mặt không tự nhận message cũ. **BRPOP không phải ACK:** phần tử biến mất khỏi List ngay khi worker nhận, trước khi chắc chắn xử lý xong. **Streams có pending/ACK nhưng không mặc định exactly-once.**

### 5.1. Pub/Sub

~~~bash
# Client đăng ký nhận
SUBSCRIBE inventory-updates

# Client khác phát tín hiệu
PUBLISH inventory-updates "SKU-42 changed"
~~~

Subscriber đang kết nối có thể nhận tín hiệu để tự tải lại dữ liệu từ nguồn chính. Nếu subscriber mất kết nối, message trong lúc đó không được Redis giữ riêng để giao lại cho subscriber. Vì thế nếu dùng Pub/Sub để invalidation cache, cần TTL/refresh để hội tụ sau downtime.

### 5.2. List và giới hạn khi worker crash

~~~bash
LPUSH jobs:email email-1001
BRPOP jobs:email 0
~~~

Nếu worker đã pop **email-1001** và chết trước khi gửi email, list không còn message. Có thể dùng **BLMOVE** chuyển nguyên tử từ ready sang processing, sau đó xóa khỏi processing khi hoàn tất, nhưng phải tự triển khai sweeper nhận diện task quá hạn và claim lại, retry limit, DLQ và idempotency.

### 5.3. Redis Streams và consumer group

Một email worker có thể dùng Stream để giữ record cho đến khi xử lý thành công và **XACK**:

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant S as Redis Stream
    participant W1 as Worker A
    participant W2 as Worker B
    participant E as Email Provider
    O->>S: XADD jobId=email-1001
    W1->>S: XREADGROUP email-workers
    S-->>W1: Record ID = 1700000000000-0
    W1->>E: Send email
    Note over W1: Crash trước XACK
    W2->>S: XAUTOCLAIM pending quá hạn
    S-->>W2: Cùng record
    W2->>E: Retry với cùng idempotency key
    W2->>S: XACK sau khi hoàn tất
~~~

Ví dụ Redis CLI:

~~~bash
# Tạo stream và consumer group nếu chưa tồn tại.
# ID 0 cho phép group đọc record đã có từ trước.
XGROUP CREATE jobs:emails email-workers 0 MKSTREAM

# Producer ghi một record.
XADD jobs:emails * jobId email-1001 orderId order-42 template order-created

# Nhận record mới chưa giao cho group.
XREADGROUP GROUP email-workers worker-1 COUNT 10 BLOCK 2000 STREAMS jobs:emails >

# Sau khi hoàn tất, ACK bằng ID thực tế của record vừa nhận.
XACK jobs:emails email-workers 1700000000000-0

# Xem record đang pending.
XPENDING jobs:emails email-workers

# Claim record đã idle quá 60 giây (Redis 6.2+).
XAUTOCLAIM jobs:emails email-workers worker-2 60000 0-0 COUNT 10
~~~

ID **0** lúc tạo group nghĩa là bắt đầu đọc record đang có; **$** nghĩa là bắt đầu từ các record được thêm về sau. Với **XREADGROUP ... >**, worker nhận những record **chưa từng được giao cho group**. Record đã giao nhưng chưa ACK nằm trong **pending entries list (PEL)**; cần đọc/claim pending qua quy trình riêng, không chỉ gọi lặp **>**.

**XACK chỉ xóa trạng thái pending trong một consumer group, không xóa record khỏi stream.** Việc **XTRIM/XDEL** hoặc retention phải tính đến các consumer chậm và message pending; nếu payload đã bị trim, PEL có thể còn tham chiếu mà không còn dữ liệu để xử lý lại.

### 5.4. At-least-once và idempotency

Với cơ chế phát lại pending phù hợp, Streams thường được dùng theo **at-least-once processing**. Điều đó có nghĩa là **một record có thể được xử lý nhiều lần**:

1. Worker gọi API gửi email/thu tiền thành công.
2. Worker chết trước XACK.
3. Worker khác reclaim cùng record.
4. Nếu không chống trùng, side effect có thể diễn ra lần nữa.

Không dùng Redis stream ID làm định danh nghiệp vụ duy nhất nếu một outbox event có thể được publish lại thành **record mới** với stream ID khác. Thêm **jobId/eventId ổn định** vào payload và dùng idempotency ở phía consumer/provider.

Ví dụ database lưu dấu event đã xử lý:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Với DB transaction cục bộ, chèn eventId và cập nhật dữ liệu nghiệp vụ trong **cùng transaction**. Nếu transaction commit thành công thì ACK; nếu rollback, để record pending và retry. Với side effect HTTP bên ngoài, transaction DB không rollback được remote API đã xử lý; cần provider idempotency key hoặc truy vấn trạng thái khi timeout.

Một khóa Redis kiểu **SET key value NX EX** có thể giảm xử lý trùng ngắn hạn, nhưng TTL hết hoặc Redis mất dữ liệu có thể khiến hành động lặp. Nó không thay thế cơ chế idempotency bền vững khi trùng gây hậu quả nghiêm trọng.

## 6. Spring Boot: ghi job vào Redis Streams

Spring Data Redis cung cấp các thao tác Stream qua **RedisTemplate.opsForStream()** và các listener container phù hợp. Ví dụ producer:

~~~java
package example.integration.redis;

import java.util.Map;
import java.util.UUID;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class EmailJobPublisher {
    private final StringRedisTemplate redis;

    public EmailJobPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId enqueue(String orderId, String jobId) {
        return redis.opsForStream().add(
                StreamRecords.string(Map.of(
                        "jobId", jobId,
                        "orderId", orderId,
                        "template", "order-created"))
                        .withStreamKey("jobs:emails"));
    }
}
~~~

**jobId** do bên gọi cấp để giữ nguyên qua mọi lần retry. Nếu chỉ là tác vụ độc lập, có thể tạo UUID ở nơi tạo tác vụ. Nếu job xuất phát từ đơn hàng trong PostgreSQL và yêu cầu không mất event, **không XADD trực tiếp rồi tin rằng cùng commit với database**.

### 6.1. Transactional Outbox khi kết hợp DB và Redis

~~~mermaid
flowchart LR
    A["POST /orders"] --> T["PostgreSQL transaction"]
    T --> O["orders"]
    T --> X["outbox_event"]
    X --> P["Outbox publisher"]
    P --> S["Redis Stream"]
    S --> W["Idempotent consumer"]
~~~

Ghi **orders + outbox_event** trong cùng DB transaction; publisher đọc outbox và **XADD**. Nếu crash sau XADD nhưng trước khi đánh dấu đã publish, publisher có thể gửi lại **cùng eventId**, consumer dùng eventId để chống trùng.

Consumer có thể dùng **StreamMessageListenerContainer** hoặc tự đọc group. Quy trình xử lý:

~~~text
readGroup(stream, group, consumer)
for each record:
    try:
        processIdempotently(record.jobId, record.payload)
        ack(stream, group, record.streamId)
    catch transientFailure:
        leavePendingForBoundedRetryAndReclaim()
    catch permanentFailure:
        saveDeadLetterWithReason()
        ackOnlyAfterDeadLetterSafelyRecorded()

periodically:
    inspectPendingAndClaimExpiredRecords()
~~~

Đây là pseudocode, không phải tên method có sẵn của RedisTemplate. Triển khai thực tế cần lifecycle của consumer group, ACK đúng thời điểm, retry có backoff, dead-letter stream hoặc DB, giới hạn số lần, độ trễ và giám sát PEL. Không nên hứa “exactly-once” chỉ vì dùng Stream.

## 7. So sánh Redis Streams với broker chuyên dụng

Redis Streams hữu ích cho hàng đợi tích hợp mức phù hợp, nhưng không phải mọi bài toán messaging đều nên chọn Redis.

| Tiêu chí | Redis Streams | RabbitMQ | Kafka |
| --- | --- | --- | --- |
| Mô hình | Stream + consumer group + PEL | Queue/exchange, ACK và routing | Partitioned event log + consumer offsets |
| Replay | Có nếu record vẫn còn theo retention | Message đã ACK thường không còn để replay bình thường | Theo chính sách retention topic |
| Worker retry | Pending/claim và retry do ứng dụng thiết kế | ACK/requeue/DLX, retry cần policy phù hợp | Consumer retry, topic retry, lag quản lý theo partition |
| Thứ tự | ID tăng theo Stream; consumer song song có thể hoàn thành khác thứ tự | Phụ thuộc queue, concurrency, requeue | Thứ tự trong một partition |
| Vận hành | PEL, trimming, AOF, memory và failover | Queue depth, prefetch, consumer và broker | Partition, retention, replication, lag |
| Khi chọn | Hàng đợi phù hợp với Redis và đã thiết kế ACK/idempotency | Cần routing/worker queue với tính năng broker | Cần event log, replay lâu dài, nhiều nhóm consumer |

Không công nghệ nào tự đảm bảo side effect HTTP/database exactly-once. Producer confirm, persistence, replication, consumer ACK và business idempotency mới quyết định mức bảo đảm thực tế.

## 8. Quản lý TTL, eviction và retention

Ba khái niệm cần tách biệt:

- **TTL:** thời gian hết hạn của **key**, thường dùng cho cache, session và bộ đếm ngắn hạn.
- **Eviction:** Redis chủ động loại key khi chạm giới hạn memory theo policy, có thể trước TTL.
- **Stream trimming/retention:** loại **entry trong Stream** để kiểm soát dữ liệu; độc lập với ACK của từng consumer group.

| Policy | Tác động |
| --- | --- |
| **noeviction** | Khi chạm maxmemory, những lệnh ghi cần thêm memory có thể bị từ chối; phù hợp hơn nếu không được tự loại dữ liệu quan trọng nhưng phải xử lý lỗi ghi |
| **allkeys-lru / allkeys-lfu** | Có thể evict mọi key theo LRU/LFU gần đúng; hữu ích cho cache nhưng có thể làm mất session/message |
| **volatile-lru / volatile-ttl** | Chỉ xét key có TTL; session thường cũng có TTL nên vẫn có thể bị loại |

Đặt cache, session và Stream chung instance có thể tạo xung đột: cache chiếm RAM làm session bị evict hoặc khiến XADD thất bại. **Redis logical DB index không cô lập memory, CPU, quyền truy cập hoặc lỗi toàn server**. Redis Cluster cũng chỉ hỗ trợ database 0. Khi các workload có mức quan trọng khác nhau, cân nhắc tách instance/cluster và thiết lập giới hạn tài nguyên, ACL, cảnh báo riêng.

## 9. Cấu hình và thiết kế key

Cấu hình kết nối mẫu trong Spring Boot:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Timeout chỉ là giá trị minh họa. Production cần TLS, ACL, secret management và network isolation phù hợp; không để password trong source code hay tạo endpoint Redis công khai.

Quy ước key:

~~~text
shop:prod:cache:product:v2:SKU-42
shop:prod:counter:product:SKU-42:views
shop:prod:jobs:emails
shop:prod:dedup:email:email-1001
~~~

**Spring Session** có namespace/schema riêng do thư viện quản lý; không tự viết script quét tất cả key rồi xóa theo prefix chung. Tránh đưa email, token hay dữ liệu nhạy cảm vào key và log. Khi cache DTO thay đổi schema, nên định version hoặc triển khai serializer có chiến lược backward compatibility. Java native serialization mặc định của một số cấu hình Redis không phù hợp cho dữ liệu không tin cậy; chọn serialization an toàn cho từng workload.

## 10. Các lỗi phối hợp PostgreSQL, HTTP và Redis

### 10.1. DB commit nhưng cache eviction thất bại

~~~text
T1: UPDATE product set price=100
T2: COMMIT PostgreSQL thành công
T3: DEL product-cache thất bại
=> Redis vẫn giữ giá cũ tới TTL hoặc lần invalidation sau.
~~~

Xóa cache trước commit cũng có rủi ro: request khác miss rồi đọc giá cũ trước khi DB commit, sau đó đưa dữ liệu cũ trở lại cache. Đường critical cần invalidation sau commit, version key hoặc cơ chế đồng bộ có retry.

### 10.2. DB commit nhưng XADD chưa thực hiện

~~~text
T1: COMMIT order thành công
T2: Process crash
T3: Chưa XADD jobs:emails
=> Có đơn hàng nhưng không có email job.
~~~

Giải pháp thường là transactional outbox trong DB nguồn, publisher retry và consumer idempotent. Annotation **@Transactional** trên Spring service không tự biến PostgreSQL và Redis thành một local transaction nguyên tử.

### 10.3. Worker gọi remote API thành công rồi mất ACK

~~~text
T1: XREADGROUP lấy email-1001
T2: Email provider nhận và gửi thành công
T3: Worker chết trước XACK
T4: Worker khác XAUTOCLAIM cùng record
=> Phải xử lý trùng ở mức business key/provider.
~~~

Nếu provider không hỗ trợ idempotency, thiết kế trạng thái gửi, tra cứu kết quả và phương án xử lý trường hợp không xác định. Không suy luận “timeout nghĩa là remote chưa xử lý”.

## 11. Kiểm thử theo vai trò

### 11.1. Data store

1. Nhiều client cùng **INCR** một key; xác minh không mất cập nhật khi server hoạt động bình thường.
2. Restart Redis với RDB/AOF đúng cấu hình production; đo dữ liệu có thể mất và thời gian phục hồi.
3. Failover primary/replica khi đang ghi; kiểm tra ứng dụng ứng phó với counter lùi hoặc write retry.
4. Kiểm tra memory limit, backup, restore và command errors.

### 11.2. Cache

1. Miss → đọc DB và set TTL; hit → không gọi DB lại.
2. Cập nhật DB rồi đọc lại; xác minh stale window và invalidation.
3. Giả lập Redis mất kết nối/cache stampede; kiểm tra fallback không làm DB quá tải.
4. Thay serializer/DTO schema trong rolling deployment; xác minh key cũ được đọc hoặc invalidated an toàn.

### 11.3. Session

1. Đăng nhập qua node A, request sau qua node B với cùng cookie vẫn đọc được phiên.
2. Logout, session timeout và revoke khiến phiên không còn hợp lệ.
3. Restart/failover Redis; quan sát session survive hoặc bị mất đúng theo RPO mong đợi.
4. Kiểm tra cookie flags, session fixation protection và serializer compatibility.

### 11.4. Queue

1. Producer XADD; consumer group đọc đúng message và XACK sau khi xử lý.
2. Kill worker trước ACK; kiểm tra **XPENDING/XAUTOCLAIM** và việc xử lý lại.
3. Publish cùng eventId hai lần; business side effect chỉ xảy ra một lần hợp lệ.
4. Tạo group với **0** và **$** để chứng minh khác biệt nhận backlog.
5. Consumer gặp message poison; chuyển DLQ và không retry vô hạn.
6. Test stream trimming khi còn PEL, Redis restart, memory pressure và consumer lag.
7. Với outbox, crash giữa DB commit, XADD và đánh dấu published; không mất ý định phát event.

Integration test có thể dùng Redis thực trong môi trường kiểm thử như Testcontainers và PostgreSQL test container nếu có outbox. Mock unit test hữu ích cho code điều phối nhưng không chứng minh được PEL, TTL, failover hoặc persistence của Redis.

## 12. Giám sát và vận hành

| Vai trò | Chỉ số nên theo dõi |
| --- | --- |
| Data store | Persistence failures, replica lag, RDB/AOF status, write errors, backup age |
| Cache | Hit/miss ratio, evicted_keys, Redis latency, DB fallback traffic, stale-data incidents |
| Session | Session count, expiration, read/write failures, tỷ lệ logout bất thường khi failover |
| Streams | Stream length, consumer group lag, pending count, oldest pending age, claim/retry/DLQ, processing latency |
| Hạ tầng | used_memory/maxmemory, blocked clients, connection pool, CPU, network, TLS/ACL errors |

Một queue có ít message trong stream chưa chắc là khỏe nếu pending entries bị kẹt lâu. Một endpoint trả HTTP 200 chưa chứng minh email đã gửi. Đặt cảnh báo theo **thời gian công việc từ khi tạo đến khi hoàn tất**, không chỉ Redis ping/uptime. Gắn **eventId/jobId**, correlation ID và trace ID để đối chiếu pipeline mà không log secret/PII.

## 13. Quy trình chọn Redis cho tính năng mới

~~~mermaid
flowchart TD
    A["Giá trị này có nguồn khác<br/>để tái tạo khi key mất?"] -->|Có| B["Cache: TTL + invalidation + fallback"]
    A -->|Không| C{"Đây là session đăng nhập<br/>có thời hạn?"}
    C -->|Có| D["Spring Session Redis<br/>expiry + security + HA"]
    C -->|Không| E{"Đây là job/message<br/>cần worker ACK?"}
    E -->|Có| F["Redis Streams / broker<br/>ACK + retry + dedup"]
    E -->|Không| G["Đánh giá Redis làm data store<br/>persistence + RPO/RTO"]
~~~

Trước khi triển khai, trả lời:

1. **Nếu mất key, có tái tạo được không?** Nếu không, RPO/backup và recovery là gì?
2. **Ai sở hữu dữ liệu gốc?** Redis, PostgreSQL, identity provider hay một dịch vụ khác?
3. **Thời hạn và ý nghĩa hết hạn là gì?** Cache TTL, session idle timeout, stream retention hay business deadline?
4. **Nếu tác vụ chạy hai lần thì sao?** Cần unique constraint, idempotency key, deduplication hoặc reconciliation?
5. **Nếu Redis chậm hoặc lỗi thì ứng dụng phản ứng thế nào?** Fallback, fail closed, retry có giới hạn hay trả lỗi?
6. **Có metric nào chứng minh đúng nghiệp vụ?** Cache staleness, session validity, backlog age, RPO/RTO, DLQ?

## 14. Những ngộ nhận cần tránh

**“Redis nhanh nên mọi dữ liệu đều nên chuyển sang Redis.”** Tốc độ không thay thế khả năng query, giao dịch, audit, backup và độ bền của nguồn dữ liệu chính.

**“Cache có TTL thì không bao giờ stale.”** Giá trị có thể cũ trong toàn bộ TTL nếu nguồn thay đổi và invalidation thất bại.

**“Redis session chỉ là cache, evict key sớm cũng không sao.”** Eviction session có thể làm người dùng mất phiên trước hạn, ảnh hưởng cả bảo mật và trải nghiệm.

**“Pub/Sub và Stream là queue như nhau.”** Pub/Sub không lưu replay cho client offline; Stream có lưu record, group, pending và ACK theo retention.

**“BRPOP đảm bảo worker xử lý xong.”** Pop khỏi list trước khi hoàn tất khiến task mất nếu worker crash.

**“XACK đồng nghĩa xóa record.”** ACK chỉ cập nhật trạng thái pending của group; muốn dọn entry phải dùng retention/trimming riêng.

**“Redis Streams bảo đảm exactly-once end-to-end.”** Worker có thể xử lý rồi chết trước ACK, gây redelivery; side effect cần idempotent.

**“AOF và replica đảm bảo không mất một write nào.”** fsync và replication bất đồng bộ vẫn có cửa sổ mất dữ liệu, cần kiểm chứng failover/restore.

**“@Transactional rollback được cả PostgreSQL và Redis.”** Thông thường chỉ quản lý một ranh giới resource; luồng tích hợp cần outbox, idempotency hoặc compensation.

**“Một Redis instance có thể chia sẻ thoải mái giữa cache, session và queue.”** Ba workload tranh RAM, CPU, network, eviction và failure domain. Hãy tính isolation và capacity.

## 15. Checklist production

- Phân loại key thành **data store/cache/session/queue**, ghi rõ nguồn sự thật và hành vi khi mất dữ liệu.
- Đặt namespace, schema/version, serializer và dữ liệu nhạy cảm theo hợp đồng; tránh key không giới hạn từ đầu vào.
- Cấu hình RDB/AOF, replication, backup, RPO/RTO và kiểm thử restore theo mức quan trọng.
- Chọn maxmemory/eviction policy phù hợp; cân nhắc tách cache, session và queue.
- Cache có TTL, invalidation sau commit, fallback và chống stampede.
- Session có timeout, cookie/TLS/CSRF/security phù hợp, kiểm thử đa node và logout/revoke.
- Queue có cơ chế ACK, reclaim pending, retry/backoff, DLQ, retention và business idempotency.
- DB + message dùng outbox khi cần giữ ý định phát event cùng transaction nghiệp vụ.
- Giám sát hit ratio, eviction, persistence, session errors, stream lag, pending age và DLQ.
- Tập dượt mất Redis, failover, consumer crash sau side effect và khôi phục công việc.

## Tài liệu tham khảo

- [Redis Documentation — Data Types](https://redis.io/docs/latest/develop/data-types/)
- [Redis Documentation — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis Documentation — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis Documentation — Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Session — Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
- [Spring Boot Reference — Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html)

**Ghi nhớ:** Redis là một công nghệ có thể đảm nhận bốn vai trò với hợp đồng khác nhau. **Data store** phải xác định tính bền vững của dữ liệu gốc; **cache** tối ưu tốc độ đọc và phải chấp nhận miss/stale; **session** quản lý trạng thái xác thực có thời hạn; **queue** cần ACK, retry, retention và chống xử lý trùng. Trong Spring Boot Integration, ranh giới nguồn sự thật và quy trình khôi phục mới quyết định một thiết kế Redis có đáng tin cậy hay không.
