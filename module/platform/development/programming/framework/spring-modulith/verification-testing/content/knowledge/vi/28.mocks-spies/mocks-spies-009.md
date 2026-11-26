# Mock clock và dữ liệu thời gian

## 1. Một test phụ thuộc đồng hồ thật sẽ có lúc thất bại không vì lỗi nghiệp vụ

Hãy hình dung một đơn hàng chỉ được chấp nhận khi báo giá còn hiệu lực. Code viết rất tự nhiên:

~~~java
if (Instant.now().isBefore(quote.expiresAt())) {
    acceptOrder();
}
~~~

Người viết test tạo một báo giá hết hạn sau một giây, gọi service, rồi khẳng định đơn được chấp nhận. Trên máy cá nhân test xanh; trên CI tải cao, garbage collection hoặc machine scheduling làm lệnh gọi đến muộn hơn một giây, nên test đỏ. Không có refactor nào sửa nghiệp vụ, chỉ có **đồng hồ thật đã chạy**.

Các lỗi liên quan thời gian còn khó phát hiện hơn:

- Một request ở đúng thời điểm hết hạn được chấp nhận do dùng `isAfter` thay vì `isBefore`.
- Dữ liệu `LocalDateTime` thiếu timezone bị diễn giải khác khi server chuyển sang UTC.
- Một báo cáo chạy sát nửa đêm đếm dữ liệu vào sai ngày kinh doanh.
- Java test dùng `Clock.fixed`, nhưng SQL lại dùng `CURRENT_TIMESTAMP` của database.
- Event có `occurredAt` từ application clock, còn listener lấy `Instant.now()` từ clock hệ thống.
- Test đợi scheduler tự động chạy sau khi đổi clock, nhưng scheduler vẫn đợi **thời gian thật**.
- Test bị nhiễu vì một clock mutable được chia sẻ giữa các tests song song.

**Nguyên tắc:** Thời gian là một **input của nghiệp vụ**. Muốn test tái lập được, hãy đưa nguồn thời gian vào một abstraction rõ ràng (thường là `java.time.Clock`), kiểm soát instant và zone trong test, rồi kiểm tra kết quả observable: database, event, exception và transaction.

Bài thuộc chương **Mock và spy** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Học phần rèn kỹ năng kiểm chứng ranh giới kiến trúc Spring Modulith bằng `ApplicationModules`, quy tắc phụ thuộc giữa module, `@ApplicationModuleTest`, kiểm thử sự kiện, database và tích hợp, kết hợp quality gate trong CI để ngăn phụ thuộc sai và hồi quy. Trong phạm vi này, mock/fake clock chỉ là một **test double của thời gian**, không phải vật thay thế cho persistence hoặc event infrastructure.

### Mục tiêu học tập

Sau bài, bạn có thể:

1. Giải thích tại sao `Instant.now()`, `LocalDate.now()` hoặc `System.currentTimeMillis()` gọi trực tiếp làm test khó kiểm soát.
2. Inject `Clock` vào Spring service và dùng `Clock.systemUTC()` trong runtime, `Clock.fixed(...)` trong test.
3. So sánh `Clock.fixed`, `Clock.offset`, `Clock.tick`, `@Mock Clock`, `@MockitoBean Clock` và clock mutable.
4. Viết test **trước hạn, đúng hạn, sau hạn** không có `Thread.sleep`, có quy tắc inclusive/exclusive rõ ràng.
5. Phân biệt `Instant` với `LocalDate`, `LocalDateTime`, `ZonedDateTime`, business timezone và DST.
6. Viết `@ApplicationModuleTest(STANDALONE)` giữ `OrderService`, JPA repository và event publisher thật, chỉ mock API module ngoài.
7. Kiểm tra timestamp trong `OrderEntity` và `OrderPlaced`, biết giới hạn của `PublishedEvents`, database precision và time source khác.
8. Thiết kế integration tests cho scheduler, async listener, TTL/retry, clock skew và CI quality gates.

## 2. Những “nguồn thời gian” cần phân biệt

| Nguồn thời gian | Ví dụ | Rủi ro nếu không kiểm soát |
| --- | --- | --- |
| **Application wall clock** | `Instant.now()`, `Clock.systemUTC().instant()` | Test thay đổi theo thời điểm thực. |
| **Business calendar** | `LocalDate.now(ZoneId.of("Asia/Ho_Chi_Minh"))` | Mốc ngày/nửa đêm, timezone và DST. |
| **Database clock** | SQL `CURRENT_TIMESTAMP`, `now()`, trigger | Có thể khác clock do Spring inject. |
| **JPA/provider-generated time** | `@CreationTimestamp`, auditing provider | Nguồn time và cách truncate tùy provider/config. |
| **Broker timestamp** | Kafka record timestamp, AMQP header | Không tự bằng event `occurredAt`. |
| **Scheduler/timer** | `@Scheduled`, executor delay, Quartz | Đổi `Clock` không mặc nhiên làm timer chạy ngay. |
| **Monotonic elapsed time** | `System.nanoTime()`, stopwatch | Đo duration, không phải ngày giờ UTC. |
| **External service time** | `expiresAt` của payment/quote/token provider | Clock skew và latency giữa hai hệ thống. |

Một bài test chỉ thay `Clock` trong `OrderService` sẽ kiểm soát **những lần đọc thời gian thực sự đi qua bean đó**, không kiểm soát tất cả các nguồn thời gian khác của cả ứng dụng.

### 2.1. Instant và zone là hai khái niệm khác nhau

`Instant` biểu diễn **một điểm trên trục thời gian UTC**. Nó phù hợp để so sánh hạn dùng, event occurrence, deadline và trạng thái expires:

~~~java
Instant expiresAt = Instant.parse("2026-11-26T02:00:00Z");
Instant now = clock.instant();

boolean valid = now.isBefore(expiresAt);
~~~

`ZoneId` dùng khi biến một instant thành ngày/giờ theo **quy tắc vùng**:

~~~java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = LocalDate.ofInstant(
        now, businessZone);
~~~

Không so sánh hạn sử dụng bằng cách chuyển hai instant thành `LocalDateTime` rồi bỏ zone: cùng một instant có thể rơi vào ngày khác nhau tại các vùng khác nhau.

## 3. Clock là abstraction của thời gian, không nhất thiết cần Mockito

Java Time cung cấp `java.time.Clock`:

~~~java
Clock productionClock = Clock.systemUTC();

Clock testClock = Clock.fixed(
        Instant.parse("2026-11-26T02:00:00Z"),
        ZoneOffset.UTC);

Instant productionNow = productionClock.instant();
Instant stableNow = testClock.instant();
~~~

`Clock.fixed` là một **implementation thật, bất biến và deterministic**: mọi lần đọc đều trả cùng instant. Khi chỉ muốn kiểm tra luật về thời gian, nó thường tốt hơn một Mockito mock vì:

- Không cần stub `instant()` và `getZone()` riêng.
- `Instant.now(clock)`, `LocalDate.now(clock)` và `ZonedDateTime.now(clock)` có behavior thời gian/zone hợp lệ.
- Không phụ thuộc số lần application code đọc `clock.instant()`.
- Có thể dùng trong unit test thuần, test module và các class domain mà không cần Mockito.

**Clock cố định không làm thời gian thực ngừng trôi.** Nó chỉ làm những đoạn code **đọc qua Clock đó** nhận cùng timestamp.

### 3.1. Không gọi Instant.now() trong business code nếu đã inject Clock

**Chưa phù hợp:**

~~~java
@Service
class QuotePolicy {
    boolean active(Instant expiresAt) {
        return Instant.now().isBefore(expiresAt);
    }
}
~~~

**Tốt hơn:**

~~~java
@Service
class QuotePolicy {
    private final Clock clock;

    QuotePolicy(Clock clock) {
        this.clock = clock;
    }

    boolean active(Instant expiresAt) {
        return clock.instant().isBefore(expiresAt);
    }
}
~~~

Nếu một module có nhiều service cần thời gian, có thể inject cùng bean `Clock`, hoặc tạo `TimeSource` domain abstraction khi có yêu cầu semantic rõ hơn (ví dụ business day được chuẩn hóa theo thị trường).

## 4. Clock.fixed, offset, tick và mutable test clock

| Phương pháp | Behavior | Phù hợp | Cảnh báo |
| --- | --- | --- | --- |
| `Clock.systemUTC()` | Thời gian hệ thống, zone UTC. | Production default. | Không deterministic cho boundary tests. |
| `Clock.system(zone)` | System instant, zone chỉ định. | Business calendar cần zone. | System clock vẫn chạy. |
| `Clock.fixed(instant, zone)` | Instant **không đổi**. | Test một thời điểm chính xác. | Delay/scheduler không tự tiến. |
| `Clock.offset(base, duration)` | Instant của base + offset. | Mô phỏng lệch clock hoặc dịch thời điểm. | Nếu base chạy thật, kết quả vẫn thay đổi. |
| `Clock.tick(base, duration)` | Instant được làm tròn theo tick. | Test độ phân giải hoặc production tick khi hợp lý. | Không phải fixed clock; có thể cache timestamp. |
| Mockito `@Mock Clock` | Trả stub/default cho methods. | Test rất hẹp cần điều khiển từng read. | `getZone()` có thể trả null, sequence stubs giòn. |
| `MutableClock` riêng | Có thể `set`/`advance`. | Test stateful workflow qua nhiều mốc. | Shared mutable bean và parallel tests dễ nhiễu. |

### 4.1. Clock.offset không thể “đóng băng” system clock

~~~java
Clock stillRunning = Clock.offset(
        Clock.systemUTC(), Duration.ofDays(3));
~~~

Nó nhanh hơn hệ thống ba ngày, nhưng vẫn chạy. Nếu muốn mốc deterministic:

~~~java
Clock fixedBase = Clock.fixed(
        Instant.parse("2026-11-26T02:00:00Z"),
        ZoneOffset.UTC);

Clock tomorrow = Clock.offset(
        fixedBase, Duration.ofDays(1));
~~~

Hai clock sau cố định tại những instant khác nhau. Nếu test cần đi từ “trước hạn” sang “sau hạn”, hai `Clock.fixed` độc lập hoặc một mutable test clock được reset rõ ràng là lựa chọn dễ hiểu.

### 4.2. Clock.tick không dùng để giả lập thời gian trôi theo test

~~~java
Clock secondsClock = Clock.tick(
        Clock.systemUTC(), Duration.ofSeconds(1));
~~~

`secondsClock` vẫn phụ thuộc thời gian thật và trả thời điểm bị làm tròn đến giây. Nó có thể hữu ích khi contract yêu cầu timestamp cấp giây, nhưng **không thay `Clock.fixed`** cho bài test cần một mốc bất biến.

## 5. Test đúng thời điểm biên: isBefore, equals và isAfter

Quy tắc của bài:

> Báo giá còn hiệu lực khi `now < expiresAt`. Tại đúng `expiresAt`, báo giá đã hết hạn.

Vì vậy:

~~~java
boolean valid = clock.instant().isBefore(expiresAt);
~~~

và:

~~~java
boolean expired = !clock.instant().isBefore(expiresAt);
~~~

Đừng viết `now.isAfter(expiresAt)` để xác định hết hạn nếu **thời điểm bằng nhau** cũng phải hết hạn.

| Mốc đọc clock | So sánh | Kết quả |
| --- | --- | --- |
| `2026-11-26T01:59:59.999Z` | now trước expiresAt | Chấp nhận |
| `2026-11-26T02:00:00.000Z` | now bằng expiresAt | Từ chối |
| `2026-11-26T02:00:00.001Z` | now sau expiresAt | Từ chối |

### 5.1. Unit test không sleep

~~~java
import org.junit.jupiter.api.Test;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;

class QuoteDeadlineTests {

    private static final Instant DEADLINE =
            Instant.parse("2026-11-26T02:00:00Z");

    boolean activeAt(Instant moment) {
        Clock clock = Clock.fixed(moment, ZoneOffset.UTC);
        return clock.instant().isBefore(DEADLINE);
    }

    @Test
    void beforeDeadlineIsValid() {
        assertThat(activeAt(DEADLINE.minusNanos(1))).isTrue();
    }

    @Test
    void exactlyAtDeadlineIsExpired() {
        assertThat(activeAt(DEADLINE)).isFalse();
    }

    @Test
    void afterDeadlineIsExpired() {
        assertThat(activeAt(DEADLINE.plusNanos(1))).isFalse();
    }
}
~~~

Ở đây mỗi test tự chọn instant. Không dùng `Thread.sleep(1000)` hoặc `Instant.now().plusSeconds(1)`, nên không phụ thuộc tốc độ CI.

**Chú ý precision:** unit test `Instant` có thể kiểm tra nanosecond. Khi timestamp đã đi qua database, JSON serializer hoặc broker, độ chính xác có thể bị giảm; khi ấy assertion phải phù hợp contract về precision.

## 6. Kiến trúc mẫu: orders phụ thuộc public API của quotes

Giả sử `ShopApplication` nằm tại `com.example.shop`, các package con trực tiếp tạo thành application modules:

~~~text
com.example.shop
├── ShopApplication.java
├── quotes
│   ├── api
│   │   ├── QuoteProvider.java
│   │   ├── QuoteSnapshot.java
│   │   └── package-info.java
│   └── internal
│       ├── QuoteService.java
│       └── QuoteRepository.java
└── orders
    ├── OrderService.java
    ├── QuoteExpiredException.java
    ├── package-info.java
    ├── events
    │   ├── OrderPlaced.java
    │   └── package-info.java
    └── internal
        ├── OrderClockConfiguration.java
        ├── OrderEntity.java
        └── OrderRepository.java
~~~

Module `orders` dùng public API `quotes :: api` để lấy snapshot báo giá, nhưng **không truy cập** repository nội bộ của `quotes`. Hệ thống dùng `Clock` inject vào `OrderService` để xác định một `now` nhất quán cho cả điều kiện hết hạn, `acceptedAt` trong database và `occurredAt` của event.

~~~mermaid
flowchart LR
    T["@ApplicationModuleTest orders"] --> O["OrderService thật"]
    O --> Q["quotes.api.QuoteProvider (MOCK)"]
    O --> C["Clock đã kiểm soát"]
    O --> R["OrderRepository thật"]
    O --> P["ApplicationEventPublisher thật"]
    R --> DB[("Database test")]
    P --> E["PublishedEvents"]
~~~

Trong `STANDALONE`, implementation `quotes.internal.QuoteService` không được bootstrap; test chỉ tạo mock tại public boundary. `OrderService` và repository của `orders` vẫn thật để kiểm chứng transaction/persistence/event.

### 6.1. QuoteSnapshot là hợp đồng bất biến

File `quotes/api/QuoteSnapshot.java`:

~~~java
package com.example.shop.quotes.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record QuoteSnapshot(
        UUID quoteId,
        UUID customerId,
        BigDecimal total,
        Instant expiresAt
) {
    public QuoteSnapshot {
        Objects.requireNonNull(quoteId);
        Objects.requireNonNull(customerId);
        Objects.requireNonNull(total);
        Objects.requireNonNull(expiresAt);
    }
}
~~~

File `quotes/api/QuoteProvider.java`:

~~~java
package com.example.shop.quotes.api;

import java.util.UUID;

public interface QuoteProvider {
    QuoteSnapshot quoteFor(UUID quoteId);
}
~~~

File `quotes/api/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.shop.quotes.api;
~~~

File `orders/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "quotes :: api")
package com.example.shop.orders;
~~~

Khi test `orders`, `QuoteProvider` có thể là mock; **nội dung** `expiresAt` từ collaborator là một input nghiệp vụ, nhưng **thời điểm hiện tại** phải đến từ Clock được kiểm soát. Việc stub quote không đồng nghĩa provider thật đã tuân thủ contract — cần thêm provider tests.

## 7. Spring Clock bean: runtime dùng systemUTC

Spring Boot không tự động cung cấp bean `Clock` trong mọi ứng dụng. Vì vậy module cần đăng ký rõ:

File `orders/internal/OrderClockConfiguration.java`:

~~~java
package com.example.shop.orders.internal;

import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class OrderClockConfiguration {

    @Bean
    Clock orderSystemClock() {
        return Clock.systemUTC();
    }
}
~~~

`Clock.systemUTC()` là clock runtime. Chọn UTC cho instant computations giúp tránh lệ thuộc timezone máy chủ. Nếu business calendar cần một zone riêng, giữ `ZoneId` như dữ liệu cấu hình của policy đó thay vì thay timezone mặc định của JVM.

**Không tự định nghĩa `static final Clock CLOCK = Clock.systemUTC()` bên trong service** rồi nghĩ test có thể override Spring bean: field static không được Spring inject. Hãy dùng constructor injection.

### 7.1. Khi có nhiều Clock beans

Một ứng dụng có thể có clock cho business, clock cho metrics hoặc clock test. Nếu có nhiều bean cùng type, Spring cần `@Primary`, `@Qualifier` hoặc bean name rõ ràng. Với một nguồn thời gian thống nhất cho domain `orders`, ưu tiên **một bean `Clock` duy nhất trong production** và một override có chủ đích trong test.

### 7.2. @TestConfiguration hoặc @MockitoBean?

Hai lựa chọn hợp lệ cho module test:

- **`@TestConfiguration` + `Clock.fixed`:** dùng một clock thật với instant/zone hợp lệ, phù hợp test deterministic chung.
- **`@MockitoBean Clock`:** Spring Test thay/tạo bean mock và cho phép `when(clock.instant()).thenReturn(...)`, phù hợp khi cần từng mốc khác nhau cho từng test, nhưng dễ bỏ sót `getZone` hoặc oververify số lần đọc.

Hai cách nên nằm ở **các test class khác nhau** hoặc có thiết kế bean override rõ ràng. Không vô tình vừa thêm clock `@Primary` vừa dùng mock `Clock` mơ hồ trong cùng context.

## 8. Entity thật lưu thời điểm được chấp nhận

File `orders/internal/OrderEntity.java`:

~~~java
package com.example.shop.orders.internal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Entity
@Table(name = "shop_orders")
public class OrderEntity {

    @Id
    private UUID id;

    @Column(name = "quote_id", nullable = false)
    private UUID quoteId;

    @Column(name = "customer_id", nullable = false)
    private UUID customerId;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal total;

    @Column(name = "accepted_at", nullable = false)
    private Instant acceptedAt;

    protected OrderEntity() {}

    public OrderEntity(UUID id, UUID quoteId, UUID customerId,
                       BigDecimal total, Instant acceptedAt) {
        this.id = Objects.requireNonNull(id);
        this.quoteId = Objects.requireNonNull(quoteId);
        this.customerId = Objects.requireNonNull(customerId);
        this.total = Objects.requireNonNull(total);
        this.acceptedAt = Objects.requireNonNull(acceptedAt);
    }

    public UUID getId() { return id; }
    public UUID getQuoteId() { return quoteId; }
    public UUID getCustomerId() { return customerId; }
    public BigDecimal getTotal() { return total; }
    public Instant getAcceptedAt() { return acceptedAt; }
}
~~~

File `orders/internal/OrderRepository.java`:

~~~java
package com.example.shop.orders.internal;

import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, UUID> {}
~~~

Timestamp `acceptedAt` là dữ liệu nghiệp vụ được **chủ động tính từ Clock đã inject**. Nó khác với một column có default SQL `CURRENT_TIMESTAMP`: SQL default sẽ dùng thời gian do database chọn, không mặc nhiên dùng Clock của service.

### 8.1. Event dùng cùng một thời điểm nghiệp vụ

File `orders/events/OrderPlaced.java`:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        UUID customerId,
        BigDecimal total,
        Instant occurredAt
) {}
~~~

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Nếu receiver module phụ thuộc event, nó được phép import `orders :: events`, không được phụ thuộc `orders.internal.OrderEntity`. `occurredAt` biểu thị thời điểm **nghiệp vụ phát sinh**, không phải thời điểm listener xử lý hoặc broker chuyển tiếp.

## 9. OrderService chỉ đọc clock một lần cho một lệnh

File `orders/QuoteExpiredException.java`:

~~~java
package com.example.shop.orders;

public class QuoteExpiredException extends RuntimeException {
    public QuoteExpiredException() {
        super("Quote has expired");
    }
}
~~~

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.quotes.api.QuoteProvider;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Service
public class OrderService {

    private final QuoteProvider quotes;
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderService(QuoteProvider quotes,
                        OrderRepository orders,
                        ApplicationEventPublisher publisher,
                        Clock clock) {
        this.quotes = quotes;
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void place(UUID orderId, UUID customerId, UUID quoteId) {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(quoteId, "quoteId");

        var quote = Objects.requireNonNull(
                quotes.quoteFor(quoteId), "quote");

        if (!quote.quoteId().equals(quoteId)
                || !quote.customerId().equals(customerId)
                || quote.total().signum() <= 0) {
            throw new IllegalArgumentException(
                    "Invalid quote or customer mismatch");
        }

        // Một snapshot thời gian cho toàn bộ quyết định này.
        Instant now = clock.instant();

        // Contract: hết hạn đúng tại expiresAt (exclusive).
        if (!now.isBefore(quote.expiresAt())) {
            throw new QuoteExpiredException();
        }

        orders.save(new OrderEntity(
                orderId, quoteId, customerId,
                quote.total(), now));

        publisher.publishEvent(new OrderPlaced(
                UUID.randomUUID(), orderId, customerId,
                quote.total(), now));
    }
}
~~~

**Tại sao chỉ đọc một lần?** Nếu service gọi `clock.instant()` cho điều kiện hết hạn, lại gọi thêm lần nữa cho entity và event, ba giá trị có thể khác nhau trên clock thật; tệ hơn, quyết định được đưa ra trước deadline nhưng `acceptedAt` lại sau deadline vì scheduling. Đọc một instant và tái sử dụng nhất quán giúp audit và kiểm thử dễ hiểu.

`place` được gọi qua Spring-managed bean nên `@Transactional` có hiệu lực trong module test; trong unit test khởi tạo bằng `new OrderService(...)`, annotation này **không tự mở transaction**.

**Phạm vi ví dụ:** Không triển khai đầy đủ chống race, đồng bộ clock với provider, chống replay cùng `orderId` hoặc idempotency. Trong production, nếu quote có thể bị hủy/thay đổi hoặc giá được tái định giá đồng thời, cần hợp đồng reservation/optimistic locking hoặc một bước xác nhận atomic thích hợp; so sánh `Instant` một mình không giải quyết được.

## 10. Unit test: dùng Clock.fixed thay vì Thread.sleep

Ở unit test thuần, repository và publisher có thể là Mockito mocks; `Clock` là **một object fixed thật**.

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.quotes.api.QuoteProvider;
import com.example.shop.quotes.api.QuoteSnapshot;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class OrderClockUnitTests {

    static final Instant NOW =
            Instant.parse("2026-11-26T02:00:00Z");
    @Mock QuoteProvider quotes;
    @Mock OrderRepository repository;
    @Mock ApplicationEventPublisher publisher;

    @Test
    void usesFixedClockForEntityAndEventTimestamp() {
        Clock fixed = Clock.fixed(NOW, ZoneOffset.UTC);
        var service = new OrderService(
                quotes, repository, publisher, fixed);

        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        UUID quoteId = UUID.randomUUID();

        when(quotes.quoteFor(quoteId)).thenReturn(
                new QuoteSnapshot(quoteId, customerId,
                        new BigDecimal("100000.00"),
                        NOW.plusSeconds(60)));

        service.place(orderId, customerId, quoteId);

        var entityCaptor = ArgumentCaptor.forClass(
                OrderEntity.class);
        verify(repository).save(entityCaptor.capture());

        var eventCaptor = ArgumentCaptor.forClass(
                OrderPlaced.class);
        verify(publisher).publishEvent(eventCaptor.capture());

        assertThat(entityCaptor.getValue().getAcceptedAt())
                .isEqualTo(NOW);
        assertThat(eventCaptor.getValue().occurredAt())
                .isEqualTo(NOW);
        assertThat(eventCaptor.getValue().orderId())
                .isEqualTo(orderId);
    }
}
~~~

Những gì test **chứng minh**: application code dùng instant của Clock đã inject và gửi entity/event đúng timestamp cho mocks. Những gì test **không chứng minh**: row đã commit, listener sau commit đã xử lý, event registry đã hoàn tất. Vì repository/publisher là mock và service được tạo bằng `new`, đây là unit test đúng nghĩa.

### 10.1. Test từng mốc trước/đúng/sau expiry

~~~java
@Test
void exactlyAtQuoteExpiryDoesNotSaveOrPublish() {
    Instant expiresAt = NOW;
    Clock fixed = Clock.fixed(expiresAt, ZoneOffset.UTC);
    var service = new OrderService(
            quotes, repository, publisher, fixed);

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    UUID quoteId = UUID.randomUUID();

    when(quotes.quoteFor(quoteId)).thenReturn(
            new QuoteSnapshot(quoteId, customerId,
                    new BigDecimal("100000.00"), expiresAt));

    assertThatThrownBy(() ->
            service.place(orderId, customerId, quoteId))
            .isInstanceOf(QuoteExpiredException.class);

    verifyNoInteractions(repository, publisher);
}
~~~

Bổ sung static imports `assertThatThrownBy` và `verifyNoInteractions`. Trường hợp **đúng hạn** phải bị từ chối theo contract, không sleep. Dùng thêm `Clock.fixed(NOW.minusNanos(1), UTC)` và `Clock.fixed(NOW.plusNanos(1), UTC)` cho hai mốc còn lại.

### 10.2. Tránh dùng mốc “một giây sau hiện tại”

**Dễ flaky:**

~~~java
Instant expiresAt = Instant.now().plusMillis(50);
service.place(orderId, customerId, quoteId);
~~~

Kết quả thay đổi nếu máy chạy chậm hơn 50ms. Cả fixture `expiresAt` và business decision phải dựa vào **một instant do test kiểm soát**, không dựa vào thời gian thật của hai lời gọi khác nhau.

## 11. @ApplicationModuleTest: Clock.fixed, repository thật và PublishedEvents

Giả sử module `orders` dùng `OrderClockConfiguration` của mục 7 và có datasource/JPA phù hợp. Test khởi động riêng module `orders`, thay public `QuoteProvider` của module `quotes` bằng `@MockitoBean`, nhưng để `OrderService`, `OrderRepository` và `ApplicationEventPublisher` chạy thật.

Để tránh nhầm hai bean `Clock`, test import một clock **@Primary** có instant xác định:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderPlaced;
import com.example.shop.orders.internal.OrderRepository;
import com.example.shop.quotes.api.QuoteProvider;
import com.example.shop.quotes.api.QuoteSnapshot;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ApplicationModuleTest
@Import(OrderTimeModuleTests.FrozenTime.class)
class OrderTimeModuleTests {

    static final Instant NOW =
            Instant.parse("2026-11-26T02:00:00Z");

    @Autowired OrderService service;
    @Autowired OrderRepository orders;

    // Mock đúng API public ngoài module đang test.
    @MockitoBean QuoteProvider quotes;

    @TestConfiguration(proxyBeanMethods = false)
    static class FrozenTime {

        @Bean
        @Primary
        Clock fixedOrderClock() {
            return Clock.fixed(NOW, ZoneOffset.UTC);
        }
    }

    @Test
    void validQuotePersistsOrderAndPublishesStableTime(
            PublishedEvents events) {

        UUID orderId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();
        UUID quoteId = UUID.randomUUID();
        var total = new BigDecimal("250000.00");

        when(quotes.quoteFor(quoteId))
                .thenReturn(new QuoteSnapshot(
                        quoteId, customerId, total,
                        NOW.plusSeconds(1)));

        service.place(orderId, customerId, quoteId);

        verify(quotes).quoteFor(quoteId);

        // JPA thật: dữ liệu đã được service ghi.
        assertThat(orders.findById(orderId))
                .get()
                .satisfies(entity -> {
                    assertThat(entity.getQuoteId())
                            .isEqualTo(quoteId);
                    assertThat(entity.getCustomerId())
                            .isEqualTo(customerId);
                    assertThat(entity.getTotal())
                            .isEqualByComparingTo(total);
                    assertThat(entity.getAcceptedAt())
                            .isEqualTo(NOW);
                });

        // Publisher thật: event mang cùng một mốc thời gian.
        assertThat(events.ofType(OrderPlaced.class)
                .matching(OrderPlaced::orderId, orderId))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.customerId())
                            .isEqualTo(customerId);
                    assertThat(event.total())
                            .isEqualByComparingTo(total);
                    assertThat(event.occurredAt())
                            .isEqualTo(NOW);
                    assertThat(event.eventId()).isNotNull();
                });
    }
}
~~~

**Đây là bước vượt khỏi unit test:** repository thực sự chạy qua Spring Data JPA và event được quan sát qua Spring event infrastructure. Vì `Clock.fixed` trả instant chính xác ở cấp giây, timestamp trong ví dụ ít gặp khác biệt precision giữa Java và database. Trong dự án khác, hãy đối chiếu precision/type `accepted_at` của database trước khi assert equality tuyệt đối.

### 11.1. Những điều module test này chưa chứng minh

- Quote provider **thật** chấp nhận quote và định nghĩa `expiresAt` đúng contract.
- Module listener khác đã được bootstrap và xử lý `OrderPlaced`.
- Publication Registry đã hoàn tất theo target.
- External broker hoặc email provider đã nhận integration event.
- Tất cả các service/broker/database cùng có cùng clock vật lý.

Nó kiểm chứng rất tốt logic thời gian của module `orders`, nhưng mỗi tầng khác cần test riêng.

### 11.2. Không mock repository và publisher cùng lúc

Một phản ví dụ:

~~~java
@ApplicationModuleTest
class TooIsolatedOrderTests {

    @MockitoBean OrderRepository orders;
    @MockitoBean ApplicationEventPublisher publisher;
    @MockitoBean QuoteProvider quotes;

    // Chỉ verify save(...) và publishEvent(...).
}
~~~

Test này có thể kiểm tra orchestration thuần, nhưng **không có bằng chứng persistence/event publication thực**. Nếu mục tiêu là kiểm tra cùng timestamp đi qua JPA và Spring publisher, phải giữ hai thành phần đó thật. `@ApplicationModuleTest` không tự tạo ra integration evidence nếu chính bạn đã mock các biên quan trọng.

## 12. Test tại đúng thời điểm hết hạn bằng JPA thực

Module test cũng cần negative assertions. Trong lớp `OrderTimeModuleTests`:

~~~java
@Test
void quoteAtExactDeadlineIsRejectedWithoutDbOrEvent(
        PublishedEvents events) {

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    UUID quoteId = UUID.randomUUID();

    // NOW == expiresAt: điều kiện isBefore trả false.
    when(quotes.quoteFor(quoteId))
            .thenReturn(new QuoteSnapshot(
                    quoteId, customerId,
                    new BigDecimal("250000.00"), NOW));

    assertThatThrownBy(() ->
            service.place(orderId, customerId, quoteId))
            .isInstanceOf(QuoteExpiredException.class);

    assertThat(orders.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Đây là một **boundary test** quan trọng: implementation sai `now.isAfter(expiresAt)` sẽ **cho qua** trường hợp bằng nhau, khiến assertion thất bại.

### 12.1. Quote đã hết hạn một giây

~~~java
@Test
void oldQuoteIsRejectedWithoutPersistence(
        PublishedEvents events) {

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    UUID quoteId = UUID.randomUUID();

    when(quotes.quoteFor(quoteId))
            .thenReturn(new QuoteSnapshot(
                    quoteId, customerId,
                    new BigDecimal("250000.00"),
                    NOW.minusSeconds(1)));

    assertThatThrownBy(() ->
            service.place(orderId, customerId, quoteId))
            .isInstanceOf(QuoteExpiredException.class);

    assertThat(orders.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

### 12.2. Quote thuộc khách khác

Test này không chỉ về clock nhưng minh họa cách đặt **validation về quyền sở hữu quote** cạnh điều kiện hết hạn:

~~~java
@Test
void quoteOwnedByAnotherCustomerDoesNotPersist(
        PublishedEvents events) {

    UUID orderId = UUID.randomUUID();
    UUID customerId = UUID.randomUUID();
    UUID otherCustomerId = UUID.randomUUID();
    UUID quoteId = UUID.randomUUID();

    when(quotes.quoteFor(quoteId))
            .thenReturn(new QuoteSnapshot(
                    quoteId, otherCustomerId,
                    new BigDecimal("250000.00"),
                    NOW.plusSeconds(60)));

    assertThatThrownBy(() ->
            service.place(orderId, customerId, quoteId))
            .isInstanceOf(IllegalArgumentException.class);

    assertThat(orders.existsById(orderId)).isFalse();
    assertThat(events.ofType(OrderPlaced.class)
            .matching(OrderPlaced::orderId, orderId))
            .isEmpty();
}
~~~

Các test dùng UUID riêng để tránh dữ liệu fixture đụng nhau. Với mục tiêu test commit và listener `AFTER_COMMIT`, **không bọc toàn bộ test trong `@Transactional` có rollback mặc định**. Nếu service mở transaction qua Spring proxy và trả về bình thường, commit của transaction đó thường đã hoàn tất trước khi test query database.

## 13. @MockitoBean Clock: lựa chọn thay thế và những bẫy

Nếu muốn từng test tự stub thời gian mà không tạo `@TestConfiguration`, có thể dùng Spring Test `@MockitoBean Clock` **trong một test class riêng**:

~~~java
@ApplicationModuleTest
class OrderTimeWithMockitoBeanTests {

    @Autowired OrderService service;
    @Autowired OrderRepository orders;

    @MockitoBean QuoteProvider quotes;
    @MockitoBean Clock clock;

    @Test
    void usesStubbedInstant() {
        Instant testNow =
                Instant.parse("2026-11-26T02:00:00Z");
        when(clock.instant()).thenReturn(testNow);

        UUID orderId = UUID.randomUUID();
        UUID quoteId = UUID.randomUUID();
        UUID customerId = UUID.randomUUID();

        when(quotes.quoteFor(quoteId))
                .thenReturn(new QuoteSnapshot(
                        quoteId, customerId,
                        new BigDecimal("100.00"),
                        testNow.plusSeconds(10)));

        service.place(orderId, customerId, quoteId);

        assertThat(orders.findById(orderId))
                .get()
                .extracting(
                        com.example.shop.orders.internal
                                .OrderEntity::getAcceptedAt)
                .isEqualTo(testNow);
    }
}
~~~

Đây là snippet tập trung vào khác biệt setup; cần imports tương ứng. Với một bean `Clock` của module `orders`, Spring Test có thể thay bằng mock thông qua type; khi có nhiều bean clock cần chọn bằng `@Qualifier` hoặc name chính xác. Test trên chỉ dùng `clock.instant()`, nên stub method ấy là đủ cho **service ví dụ**.

### 13.1. Mock Clock không mặc nhiên là một Clock hợp lệ

Một Mockito mock chưa stub:

~~~java
Clock clock = mock(Clock.class);

clock.instant(); // Có thể trả null.
clock.getZone(); // Có thể trả null.
~~~

Nếu code sau này đổi từ `clock.instant()` sang:

~~~java
LocalDate.now(clock);
~~~

thì `Clock.getZone()` và `Clock.instant()` đều có thể cần giá trị hợp lệ. Mock thiếu stub dễ gây `NullPointerException` không liên quan tới luật nghiệp vụ.

Muốn mock đầy đủ:

~~~java
when(clock.instant()).thenReturn(
        Instant.parse("2026-11-26T02:00:00Z"));
when(clock.getZone()).thenReturn(ZoneOffset.UTC);
~~~

Nhưng **`Clock.fixed` thường đơn giản và chính xác hơn**. Mockito phù hợp khi cần mô phỏng các lần đọc khác nhau có chủ đích, không phải công cụ mặc định cho mọi dependency.

### 13.2. Đừng verify số lần đọc clock nếu không phải contract

~~~java
verify(clock, times(1)).instant();
~~~

Chỉ nên dùng nếu service thực sự cam kết **lấy một snapshot duy nhất**, ví dụ timestamp cho DB/event phải nhất quán dưới clock di chuyển. Thông thường, assert `acceptedAt == occurredAt` và quyết định hết hạn đúng có giá trị mạnh hơn.

Nếu test bắt buộc “đọc instant đúng hai lần”, việc refactor hợp lệ có thể làm test vỡ dù behavior không thay đổi. Đừng biến `Clock` thành collaborator bị over-verify như mọi helper nội bộ.

### 13.3. Chuỗi thenReturn có thể bị lệch bởi một lời gọi phụ

~~~java
when(clock.instant()).thenReturn(
        firstInstant, secondInstant);
~~~

Stubbing này khiến kết quả phụ thuộc vào **thứ tự và số lần đọc** `clock.instant()`. Chỉ một dòng logging/metrics đọc clock sớm có thể làm test nhận mốc sai. Nếu test cần mô phỏng workflow nhiều bước, dùng một clock mutable được điều khiển rõ, hoặc inject một clock riêng cho từng test phase.

## 14. MutableClock: mô phỏng nhiều mốc thời gian trong một scenario

`Clock.fixed` phù hợp test một mốc. Nếu cần cùng một service sống qua nhiều bước, ví dụ:

1. Tạo reservation lúc T0.
2. Truy vấn trạng thái lúc T0 + 3 phút.
3. Cho hết hạn lúc T0 + 6 phút.

có thể dùng một `MutableClock` trong **test source**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

public final class MutableClock extends Clock {

    private final AtomicReference<Instant> current;
    private final ZoneId zone;

    public MutableClock(Instant initial, ZoneId zone) {
        this.current = new AtomicReference<>(
                Objects.requireNonNull(initial));
        this.zone = Objects.requireNonNull(zone);
    }

    @Override
    public Instant instant() {
        return current.get();
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        // Hai clock chia sẻ instant hiện tại nhưng dùng zone khác.
        return new Clock() {
            public Instant instant() {
                return current.get();
            }
            public ZoneId getZone() {
                return newZone;
            }
            public Clock withZone(ZoneId zone) {
                return MutableClock.this.withZone(zone);
            }
        };
    }

    public void set(Instant next) {
        current.set(Objects.requireNonNull(next));
    }

    public void advance(Duration amount) {
        current.updateAndGet(now -> now.plus(amount));
    }
}
~~~

Ví dụ này đủ để mô phỏng instant/zone, nhưng không cần mang vào production nếu chưa có yêu cầu. Một test đơn giản:

~~~java
Instant t0 = Instant.parse("2026-11-26T02:00:00Z");
MutableClock clock = new MutableClock(t0, ZoneOffset.UTC);

assertThat(clock.instant()).isEqualTo(t0);
clock.advance(Duration.ofMinutes(6));
assertThat(clock.instant()).isEqualTo(t0.plusSeconds(360));
~~~

`AtomicReference` làm thao tác đọc/cập nhật **atomic**, nhưng không biến toàn bộ workflow đa thread thành deterministic. Nếu nhiều threads cùng có logic dựa trên clock và shared state, vẫn phải kiểm soát đồng bộ/concurrency.

### 14.1. Rủi ro khi mutable Clock là singleton Spring bean

Spring Test có thể cache `ApplicationContext`; một `MutableClock` @Bean dùng chung giữa test methods có thể giữ mốc sau test trước. Khi chạy song song, test A gọi `advance` có thể khiến test B hết hạn dữ liệu ngoài ý muốn.

Các lựa chọn:

- Reset clock rõ trong `@BeforeEach` khi test chạy tuần tự.
- Tách Spring context/fixture khi test có stateful clock.
- Tránh parallel execution với clock singleton chia sẻ nếu không có isolation.
- Ưu tiên các lớp test dùng `Clock.fixed` khác nhau cho boundary conditions, đơn giản hơn một mutable clock chung.

**Không nên** biến clock global static thành một biến có thể `set` từ test; điều đó gây nhiễu trên toàn JVM, kể cả module không thuộc bài test.

## 15. Instant, LocalDate và business timezone

Một lỗi phổ biến là dùng ngày UTC để thực hiện quy tắc “hết hạn cuối ngày theo thị trường Việt Nam”. Ví dụ cùng một instant:

~~~java
Instant moment = Instant.parse("2026-11-26T17:00:00Z");

LocalDate utcDate = LocalDate.ofInstant(
        moment, ZoneOffset.UTC);

LocalDate hcmDate = LocalDate.ofInstant(
        moment, ZoneId.of("Asia/Ho_Chi_Minh"));

assertThat(utcDate).isEqualTo(
        LocalDate.of(2026, 11, 26));
assertThat(hcmDate).isEqualTo(
        LocalDate.of(2026, 11, 27));
~~~

Tại `17:00 UTC`, ngày ở TP. Hồ Chí Minh đã bước sang **00:00 ngày tiếp theo**. Một test chỉ chạy ban ngày UTC có thể không phát hiện bug chuyển ngày.

### 15.1. Business day có thể cần ZoneId riêng

Thay vì:

~~~java
LocalDate today = LocalDate.now(); // Dùng system default zone.
~~~

nên:

~~~java
LocalDate businessDay = LocalDate.ofInstant(
        clock.instant(),
        ZoneId.of("Asia/Ho_Chi_Minh"));
~~~

Hoặc nếu `Clock` đã được đặt đúng business zone:

~~~java
Clock businessClock =
        clock.withZone(ZoneId.of("Asia/Ho_Chi_Minh"));
LocalDate businessDay = LocalDate.now(businessClock);
~~~

Hai cách có thể cùng đúng khi source instant giống nhau. **Dữ liệu zone là một phần contract kinh doanh** nếu ngày thanh toán, hạn nộp hoặc reporting day phụ thuộc khu vực.

### 15.2. LocalDateTime không biểu thị một instant duy nhất

`LocalDateTime.of(2026, 11, 27, 0, 0)` không biết timezone, offset hay instant cụ thể. Không nên lưu deadline toàn cầu bằng `LocalDateTime` mà không có quy tắc chuyển đổi rõ.

Ưu tiên:

- `Instant` cho timestamp, deadline và event occurrence.
- `LocalDate` cho “ngày sinh”, “ngày giao hàng dự kiến” hoặc business calendar date không gắn một giờ UTC cố định.
- `ZonedDateTime` khi cần giải thích một ngày/giờ theo rule của khu vực.
- `OffsetDateTime` khi cần mang một offset cụ thể, nhưng không thay thế hoàn toàn quy tắc DST của `ZoneId`.

## 16. Daylight Saving Time (DST): kiểm thử cả gap và overlap

Việt Nam hiện không áp dụng DST, nhưng hệ thống phục vụ nhiều thị trường có thể dùng `Europe/Berlin`, `America/New_York` hoặc zone khác có chuyển giờ.

Với `Europe/Berlin` trong năm 2026:

- **29/03/2026:** một khoảng giờ địa phương bị bỏ qua khi chuyển sang giờ mùa hè; ví dụ **02:30** không tồn tại như wall-clock time thông thường.
- **25/10/2026:** một khoảng giờ lặp lại khi lùi đồng hồ; **02:30** có thể ứng với hai instant khác nhau.

~~~java
ZoneId berlin = ZoneId.of("Europe/Berlin");

LocalDateTime gap =
        LocalDateTime.of(2026, 3, 29, 2, 30);
ZonedDateTime resolvedGap = gap.atZone(berlin);

// Java time zone rules xử lý giờ không tồn tại.
assertThat(resolvedGap.toLocalTime())
        .isEqualTo(LocalTime.of(3, 30));

LocalDateTime overlap =
        LocalDateTime.of(2026, 10, 25, 2, 30);
var offsets = berlin.getRules().getValidOffsets(overlap);
assertThat(offsets).hasSize(2);
~~~

Đoạn code cần imports `LocalDateTime`, `ZonedDateTime`, `LocalTime` và AssertJ. Hãy tránh tự cộng 24 giờ bằng `Duration.ofDays(1)` để biểu diễn “ngày mai cùng giờ địa phương” trong những thị trường có DST. `Period.ofDays(1)`, `ZonedDateTime.plusDays(1)` và cộng `Duration.ofHours(24)` có semantics khác nhau quanh chuyển giờ.

### 16.1. Test một instant, nhiều zone

Một bài test nghiệp vụ có thể cố định **cùng một Instant** rồi thử hai zone:

~~~java
Instant fixed = Instant.parse("2026-03-29T01:30:00Z");

Clock utcClock = Clock.fixed(fixed, ZoneOffset.UTC);
Clock berlinClock = utcClock.withZone(
        ZoneId.of("Europe/Berlin"));

assertThat(utcClock.instant()).isEqualTo(
        berlinClock.instant());
assertThat(ZonedDateTime.now(berlinClock).getHour())
        .isEqualTo(3);
~~~

Điều đó bảo vệ sự khác biệt giữa **một điểm trên trục thời gian** và **cách hiển thị lịch địa phương**.

## 17. Database time không tự đi theo Spring Clock

Trong production, `acceptedAt` có thể được thiết lập bởi application code, JPA provider hoặc SQL schema. Ba nguồn này **không tự đồng bộ** chỉ vì bạn override một bean `Clock`.

| Cách tạo timestamp | Ai quyết định giá trị? | Clock.fixed có kiểm soát không? |
| --- | --- | --- |
| `new OrderEntity(..., clock.instant())` | `OrderService` và Clock được inject. | **Có.** |
| `@PrePersist void init() { this.createdAt = Instant.now(); }` | JVM system clock trong callback entity. | **Không**, nếu callback không dùng Clock. |
| `@CreationTimestamp` | Hibernate timestamp generation theo phiên bản và source được chọn. | **Không mặc nhiên.** |
| Spring Data `@CreatedDate` | Spring Data auditing với `DateTimeProvider` của nó. | Chỉ khi auditing được cấu hình dùng Clock tương ứng. |
| `DEFAULT CURRENT_TIMESTAMP` | Database. | **Không.** |
| Trigger `BEFORE INSERT` đặt timestamp | Database trigger. | **Không.** |
| Kafka record timestamp | Producer/broker, tùy cấu hình. | Không chỉ bằng cách inject Clock vào OrderService. |

### 17.1. Ví dụ database CURRENT_TIMESTAMP

~~~sql
CREATE TABLE checkout_sessions (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE
        DEFAULT CURRENT_TIMESTAMP NOT NULL
);
~~~

Nếu test cố định:

~~~java
Clock clock = Clock.fixed(
        Instant.parse("2026-01-01T00:00:00Z"),
        ZoneOffset.UTC);
~~~

nhưng insert không truyền `created_at` mà để database tự sinh, giá trị thực tế vẫn theo **database clock**. Đừng assert nó bằng fixed instant rồi kết luận `Clock.fixed` hỏng.

**Cách chọn test:** Nếu contract yêu cầu mọi module dùng cùng một `business occurredAt`, tính thời gian ở application layer và truyền rõ tới entity/event. Nếu contract dựa vào database clock (ví dụ audit do DB chứng thực), test theo nguồn database thật và dùng các assertion theo khoảng thời gian phù hợp, không ép nó bằng Java Clock.

### 17.2. Spring Data auditing có nguồn thời gian riêng

Với `@CreatedDate`, `@EnableJpaAuditing` và Spring Data auditing infrastructure, có thể cấu hình `DateTimeProvider` dùng injected Clock:

~~~java
import java.time.Clock;
import java.time.temporal.TemporalAccessor;
import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.data.auditing.DateTimeProvider;

@Bean
DateTimeProvider orderAuditingTimeProvider(Clock clock) {
    return () -> Optional.of(
            (TemporalAccessor) clock.instant());
}
~~~

Sau đó tham chiếu provider đúng tên tại cấu hình `@EnableJpaAuditing(dateTimeProviderRef = "orderAuditingTimeProvider")`, với entity listener và các annotations JPA auditing đã được bật phù hợp. Đây là **mẫu cấu hình minh họa**, không khẳng định mọi module test tự động có auditing. Đối chiếu phiên bản Spring Data và cấu hình hiện tại.

Nếu đã chọn domain service là nguồn timestamp, không cần ép mọi `@CreatedDate` đều cùng instant; hãy phân biệt **occurredAt** (business event time) với **createdAt** (database/audit record time).

### 17.3. @CreationTimestamp không đồng nghĩa @CreatedDate

`@CreationTimestamp` là cơ chế của Hibernate; `@CreatedDate` thuộc Spring Data auditing. Chúng có cách cấu hình và time generation khác nhau, có thể sử dụng JVM hoặc database tùy source/version. Một test inject Clock **không chứng minh** cả hai chịu điều khiển.

Nếu hệ thống sử dụng các annotations đó, viết integration test thực với entity mapping và kiểm chứng timestamp sau flush/read-back. Đừng đoán nguồn thời gian từ tên annotation.

## 18. Timestamp precision: Instant nanosecond và SQL không luôn bằng nhau

`Instant` hỗ trợ nanosecond, nhưng database column, JDBC driver và provider có thể lưu microsecond hoặc millisecond, hoặc chuyển đổi timezone theo dialect.

Ví dụ một instant từ Java:

~~~java
Instant detailed =
        Instant.parse("2026-11-26T02:00:00.123456789Z");
~~~

Cơ sở dữ liệu có thể đọc lại thành:

~~~text
2026-11-26T02:00:00.123457Z
~~~

nếu schema/provider làm tròn microsecond. Một test `assertThat(reloaded.getAcceptedAt()).isEqualTo(detailed)` có thể đỏ dù behavior nghiệp vụ không sai nếu contract chỉ yêu cầu precision đến microsecond.

### 18.1. Xác định precision contract trước khi assert

- Nếu contract lưu timestamp **đến giây**, dùng các fixed instants tròn giây rồi assert equality.
- Nếu contract yêu cầu millisecond, chuẩn hóa/round theo **quy tắc được công bố** và test trên database tương ứng.
- Nếu cần nanosecond thật, xác minh cột/driver/provider hỗ trợ và kết quả read-back, không chỉ dựa vào `Instant` Java.
- Nếu kiểm tra deadline, cần quyết định **thời điểm bằng nhau sau khi làm tròn** được xử lý thế nào.
- Đừng giải quyết sai số bằng `isCloseTo(..., within(5, MINUTES))` quá rộng; một lệch timezone hoặc bug cấp phút có thể bị che.

Một predicate với `Instant` trong code có thể rất chính xác, nhưng lưu xuống DB và đọc lại vẫn cần migration/schema test. Module test chỉ dùng H2 có thể không phản ánh PostgreSQL timezone/precision behavior.

### 18.2. Zone SQL và database session

Tên column type `TIMESTAMP WITH TIME ZONE` không bảo đảm các vendor lưu/đọc cùng semantics. Ví dụ PostgreSQL `timestamptz` chuẩn hóa instant và trình bày theo session timezone, còn một số vendor có behavior khác. Hãy:

1. Dùng một quy tắc nhất quán khi lưu `Instant`.
2. Xác định database dialect và JDBC timezone settings.
3. Test bằng database gần production nếu timestamps là hợp đồng quan trọng.
4. So sánh **instant** thay vì chuỗi hiển thị có offset khi mục tiêu là cùng một điểm trên trục thời gian.

## 19. @Scheduled không được tua nhanh bằng Clock.fixed

Giả sử một job cần tìm reservation quá hạn:

~~~java
@Scheduled(fixedDelayString = "${app.reservations.cleanup-delay}")
public void cleanup() {
    expireAllBefore(clock.instant());
}
~~~

Nếu test đổi `Clock` từ T0 sang T0 + một ngày, **không có nghĩa Spring scheduler sẽ lập tức gọi `cleanup()`**. `@Scheduled`/scheduler/executor có cơ chế kích hoạt theo timer hoặc trigger riêng.

### 19.1. Tách “khi nào job được gọi” khỏi “job làm gì”

Một cách thiết kế dễ test hơn:

~~~java
@Service
public class ReservationExpiryService {

    private final ReservationRepository reservations;
    private final Clock clock;

    public ReservationExpiryService(
            ReservationRepository reservations, Clock clock) {
        this.reservations = reservations;
        this.clock = clock;
    }

    @Transactional
    public void expireDue() {
        Instant cutoff = clock.instant();
        reservations.markExpiredBeforeOrAt(cutoff);
    }
}
~~~

Ở một class khác chỉ làm trigger:

~~~java
@Component
class ReservationExpiryScheduler {

    private final ReservationExpiryService expiry;

    ReservationExpiryScheduler(ReservationExpiryService expiry) {
        this.expiry = expiry;
    }

    @Scheduled(fixedDelayString = "${app.reservations.cleanup-delay}")
    public void tick() {
        expiry.expireDue();
    }
}
~~~

Đây là **mô hình minh họa**, cần định nghĩa `ReservationRepository.markExpiredBeforeOrAt`, query/update transaction và enable scheduling. Test business logic gọi `expiry.expireDue()` qua Spring bean với fixed clock, rồi assert DB rows; test schedule registration/timing là một lớp khác.

**Lưu ý:** Ở ví dụ này scheduler gọi một `@Transactional` service riêng qua Spring proxy. Nếu tự gọi method `@Transactional` qua `this` trong cùng bean, proxy có thể bị bypass.

### 19.2. Clock.fixed không phù hợp làm deadline của test polling

Nếu một test viết vòng lặp:

~~~java
Instant deadline = clock.instant().plusSeconds(10);
while (clock.instant().isBefore(deadline)) {
    // Chờ async callback.
}
~~~

với `Clock.fixed`, điều kiện **không bao giờ thay đổi**, vòng lặp có thể không kết thúc. Để chờ trong **thời gian thực**, dùng Awaitility/JUnit timeout hoặc một monotonic timer phù hợp. Chỉ dùng fixed Clock để điều khiển **business time** của SUT.

## 20. Async event listener: occurredAt khác processedAt

Trong ứng dụng Spring Modulith:

~~~text
T0: OrderService chấp nhận order và phát OrderPlaced
T1: Transaction nguồn commit
T2: Listener @ApplicationModuleListener bắt đầu xử lý
T3: Listener lưu side effect, publication hoàn tất
~~~

Event `OrderPlaced.occurredAt` nên mang thời điểm nghiệp vụ T0. Listener có thể cần một `processedAt` do clock của **module nhận** cấp tại T2/T3. Không ép hai thời điểm bằng nhau chỉ để test dễ pass.

~~~mermaid
sequenceDiagram
    participant Orders
    participant DB as Orders DB
    participant Registry as Publication Registry
    participant Listener as Notifications listener
    participant Out as Notifications store
    Orders->>Orders: now = clock.instant()
    Orders->>DB: save acceptedAt = now
    Orders->>Registry: publish OrderPlaced(occurredAt = now)
    Orders-->>DB: COMMIT
    Registry-->>Listener: after-commit delivery
    Listener->>Listener: processedAt = receiverClock.instant()
    Listener->>Out: save processing result
    Listener-->>Registry: completion
~~~

Sơ đồ mang tính khái niệm: Registry, store, listener async và transaction behavior tùy cấu hình/phiên bản. `PublishedEvents` của producer nhìn thấy **event được phát**, không tự chứng minh listener T3 đã completed.

### 20.1. Test listener sau commit

Nếu receiver cần kiểm tra đúng `occurredAt`, hãy trigger event qua Spring event infrastructure trong transaction commit và dùng `Scenario` hoặc Awaitility để chờ side effect:

~~~java
await().atMost(Duration.ofSeconds(10))
        .untilAsserted(() -> {
            var result = notificationRepository
                    .findByOrderId(orderId).orElseThrow();

            assertThat(result.getEventOccurredAt())
                    .isEqualTo(expectedOccurredAt);
        });
~~~

Snippet yêu cầu fixture, repository và import Awaitility; không phải một test class độc lập. Nó bảo vệ **payload time được truyền qua listener**. Nếu muốn khẳng định listener chỉ chạy **sau commit**, cần test commit-vs-rollback có đối chứng và transaction thật.

### 20.2. Không dùng Thread.sleep để “đợi cho qua ngày”

Với fixed Clock, `Thread.sleep(1000)` chỉ chờ thời gian thực **một giây**; SUT vẫn thấy cùng `clock.instant()`. Với async event, dùng condition-based await để chờ trạng thái; với business deadline, thay mốc trên clock hoặc tạo fixed clock mới.

## 21. Transaction và thời gian: snapshot không chứng minh commit

Một module test có thể kiểm tra:

~~~java
assertThat(events.ofType(OrderPlaced.class)
        .matching(OrderPlaced::orderId, orderId))
        .singleElement()
        .satisfies(e ->
                assertThat(e.occurredAt()).isEqualTo(NOW));
~~~

Đây là bằng chứng **event đã được phát với timestamp đúng**. Nó không chứng minh transaction nguồn đã commit; `publisher.publishEvent(...)` có thể xảy ra **trước khi một exception làm transaction rollback**.

Khi cần kiểm tra:

- **Commit:** Query `OrderRepository` sau `OrderService.place` trả về bình thường qua Spring proxy.
- **Rollback:** Tiêm lỗi thật tại một điểm trước commit; assert row không còn, không suy event chưa từng được publish.
- **AFTER_COMMIT listener:** Listener thật có positive control commit và negative control rollback.
- **Publication Registry:** Kiểm tra trạng thái publication per target nếu bật persistence.
- **External effect:** Test transport/idempotency độc lập, không coi `Clock.fixed` là bảo đảm exactly-once.

### 21.1. @Transactional trên test gây hiểu lầm về commit

~~~java
@ApplicationModuleTest
@Transactional
class OrdersRollbackByDefaultTests {
    // ...
}
~~~

Spring Test thường rollback outer transaction cuối method. `OrderService` với propagation `REQUIRED` có thể join transaction ấy, nên một query trong test có thể thấy row **chưa commit**, và listener `AFTER_COMMIT` chưa chạy. Đừng dùng nó làm bằng chứng commit hoặc listener completion.

### 21.2. Timestamp được tạo trước commit có thể sớm hơn nhiều

`acceptedAt = clock.instant()` trong service biểu thị **thời điểm quyết định chấp nhận**, không nhất thiết là thời điểm commit SQL. Nếu transaction bị chậm do locking, chênh lệch có thể đáng kể. Hãy đặt tên timestamp phản ánh semantic thực (acceptedAt, requestedAt, committedAt, processedAt), không dùng một trường `createdAt` mơ hồ cho tất cả.

## 22. Clock skew và thời gian từ hệ thống ngoài

Một báo giá do service `quotes` phát `expiresAt` có thể dựa vào clock của một host khác. Nếu ứng dụng `orders` chạy nhanh hơn **hai phút** do đồng hồ lệch, nó có thể từ chối báo giá sớm; nếu chậm hơn, nó có thể chấp nhận một báo giá mà provider đã coi là hết hạn.

Một test `Clock.fixed` chứng minh **luật so sánh** của module, không chứng minh hai clock vật lý đã đồng bộ.

### 22.1. Chính sách an toàn cần được đặc tả

Với một provider có rủi ro cao, business contract có thể yêu cầu **biên an toàn** trước thời điểm hết hạn:

~~~java
Duration safetyMargin = Duration.ofSeconds(5);
boolean safeToAccept =
        clock.instant().plus(safetyMargin)
                .isBefore(quote.expiresAt());
~~~

Trong policy này, quote bị từ chối **sớm hơn 5 giây** để giảm rủi ro timeout/skew; đó là lựa chọn nghiệp vụ, không phải default của Java Time. Cần test đúng thời điểm `expiresAt.minus(safetyMargin)` (bằng nhau thì từ chối), ngay trước và ngay sau.

Nếu business contract dùng một **grace period sau hạn**, logic sẽ khác. Không tự thêm margin/grace chỉ để sửa test flaky mà không có điều khoản nghiệp vụ.

### 22.2. Clock synchronization và time authority

Đối với security token, payment và distributed leases, phải xác định ai là **time authority**: identity provider, payment service, DB hoặc một hệ thống phân tán khác. NTP/time sync và monitoring drift là biện pháp vận hành, không thay thế tests.

Đặc biệt với JWT `exp`/`nbf`, thư viện security có thể dùng nguồn clock riêng hoặc hỗ trợ clock skew cấu hình. Inject Clock vào `OrderService` không tự kiểm soát validation của thư viện security; cần test ở đúng security integration layer.

## 23. Event time, processing time và thứ tự giao sự kiện

Trong event-driven architecture cần phân biệt:

| Khái niệm | Ví dụ | Bài test phù hợp |
| --- | --- | --- |
| **Occurred time** | Order được chấp nhận lúc T0. | Producer test với injected Clock và `PublishedEvents`. |
| **Published time** | `publishEvent` được gọi trong transaction. | `PublishedEvents`; chưa khẳng định commit. |
| **Committed time** | Database transaction hoàn tất thành công. | Integration test qua transaction manager/DB thật. |
| **Delivered time** | Listener bắt đầu nhận event tại T1. | Receiver/listener integration test. |
| **Processed time** | Side effect được lưu xong tại T2. | Receiver DB state, metrics hoặc acknowledgement. |
| **Retry time** | Publication chưa hoàn tất được phát lại tại T3. | Event Publication Registry và recovery integration test. |

Một event `OrderPlaced` có thể được giao lại **sau vài phút**. Khi replay, `event.occurredAt()` phải giữ nguyên timestamp của nghiệp vụ gốc. Nếu listener tạo `new OrderPlaced(..., Instant.now())` trên mỗi retry, các consumer có thể tưởng đây là sự kiện mới và làm sai logic.

### 23.1. Đến muộn không có nghĩa xảy ra muộn

Giả sử hai event:

~~~text
OrderPlaced A: occurredAt = 09:00, deliveredAt = 09:10
OrderPlaced B: occurredAt = 09:05, deliveredAt = 09:06
~~~

Receiver nhận B trước A. Sắp xếp đơn giản theo **thứ tự callback** sẽ khác sắp xếp theo **thời điểm nghiệp vụ**. Nhưng timestamp `occurredAt` đơn thuần cũng không luôn tạo **ordering có thẩm quyền** nếu nhiều host clocks bị lệch; khi cần ordering nghiêm ngặt, hãy dùng sequence/version, aggregate version, partition ordering hoặc concurrency protocol được thiết kế.

Mockito `InOrder` giữa hai listener mocks không chứng minh thứ tự broker hoặc thứ tự commit trên nhiều node.

### 23.2. Một snapshot instant giúp giữ nhất quán nhưng không atomic ngoài DB

Trong ví dụ `OrderService`, `acceptedAt` và `occurredAt` cùng nhận `now`:

~~~java
Instant now = clock.instant();
orders.save(new OrderEntity(
        orderId, quoteId, customerId, total, now));
publisher.publishEvent(new OrderPlaced(
        UUID.randomUUID(), orderId, customerId, total, now));
~~~

Điều này tạo **nhất quán timestamp** giữa hai dữ liệu. Nhưng atomicity của persistence và event publication còn phụ thuộc transaction, listener phase, publication store và cơ chế externalization. **Một Clock chung không làm database và broker trở thành một transaction phân tán.**

## 24. Parametric boundary tests và mutation analysis

Nếu luật hết hạn là một predicate nhỏ, nên test **ba vùng** thay vì một happy path. Với JUnit 5:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import static org.assertj.core.api.Assertions.assertThat;

class ExpiryBoundaryParameterizedTests {

    private static final Instant EXPIRY =
            Instant.parse("2026-11-26T02:00:00Z");

    @ParameterizedTest
    @CsvSource({
        "-1, true",
        "0, false",
        "1, false"
    })
    void quoteValidOnlyBeforeDeadline(
            long nanosecondDelta, boolean expected) {
        Clock clock = Clock.fixed(
                EXPIRY.plusNanos(nanosecondDelta),
                ZoneOffset.UTC);

        boolean active =
                clock.instant().isBefore(EXPIRY);

        assertThat(active).isEqualTo(expected);
    }
}
~~~

Các giá trị `-1`, `0`, `1` là **nanoseconds quanh ranh giới**, không phải ba giây. Đây là unit test luật thuần. Module test ở mục 11–12 cho bằng chứng thêm rằng đúng nhánh thì repository thật lưu hoặc không lưu và event phù hợp được phát.

### 24.1. Những mutation nên bị bắt

| Mutation trong code | Test cần bắt |
| --- | --- |
| Thay `isBefore` bằng `!isAfter` | Test tại **đúng hạn**, vì equality bị đảo kết quả. |
| Đổi `Clock` injected thành `Instant.now()` | Test fixed instant cách xa hiện tại, timestamp DB/event khác kỳ vọng. |
| Dùng `LocalDate.now()` thay vì business zone | Test ở mốc ngày UTC khác ngày của thị trường. |
| Đọc clock hai lần và dùng khác timestamp DB/event | Assert `acceptedAt` và `occurredAt` cùng snapshot. |
| Bỏ kiểm tra quote thuộc customer | Negative test mismatch không lưu/phát. |
| Dùng database default `CURRENT_TIMESTAMP` thay acceptedAt do service quyết định | JPA read-back test với fixed instant phát hiện lệch. |
| Bỏ `@Transactional` hoặc làm rollback sai | Integration commit/rollback test, không chỉ clock assertion. |
| Listener cập nhật `occurredAt` khi retry | Receiver/replay contract test. |
| Thay `<=` thành `<` trong cleanup query | Test đúng ranh giới `expiresAt == cutoff`. |
| Dùng `Clock.systemDefaultZone()` trong calendar policy | Time-zone CI tests ở những zone khác nhau. |

Không cần một bộ mocks cực lớn để bắt những thay đổi này; cần **assertion ở đúng semantic boundary** và các mốc thời gian test có ý nghĩa.

## 25. Chọn Clock double theo loại test

| Phạm vi | Thời gian | Dependencies khác | Bằng chứng thu được |
| --- | --- | --- | --- |
| Unit test predicate | `Clock.fixed` thật. | Không cần Mockito. | Luật hết hạn trước/đúng/sau. |
| Unit test service | `Clock.fixed`; repository/publisher có thể `@Mock`. | Stub `QuoteProvider`. | Service gửi đúng entity/event timestamp cho mocks. |
| Modulith `STANDALONE` | `@TestConfiguration` + `@Primary Clock.fixed` hoặc `@MockitoBean Clock`. | Mock public `quotes.api`; JPA/publisher thật. | DB/event state và timestamp đúng trong module. |
| Modulith `DIRECT_DEPENDENCIES` | Clock được điều khiển theo contract tích hợp. | Quote provider thật. | Wiring và hợp đồng expiry liên module. |
| JPA slice | Timestamp do fixture/Clock nếu entity support. | Repository/EntityManager thật. | Mapping, precision và SQL/read-back. |
| Scheduler business logic | Clock cố định hoặc mutable test clock. | Job method/repository thật. | Cleanup predicate và state. |
| Scheduler trigger | Scheduler/virtual time mechanism thích hợp. | Có Spring scheduling setup. | Thời điểm job được kích hoạt theo config. |
| Listener async | Clock của receiver theo mục tiêu. | Listener, transaction/event infra thật. | Event time được bảo toàn và side effect cuối. |
| External integration | Clock/time authority phù hợp. | DB/broker/HTTP fake/test environment. | Schema, transport, skew/retry behavior. |

### 25.1. Khi nào nên dùng Mockito.spy(Clock)?

Thông thường **không cần**. Spy trên `Clock.systemUTC()` vẫn đọc **thời gian hệ thống thật** cho các method không stub; một `when(spy.instant())` có thể gọi real method ngay khi stubbing (khác biệt Mockito spy). Nó không nguy hiểm như spy gateway gửi tiền, nhưng gây rối khi cần tính deterministic.

Nếu muốn thay đổi thời gian, dùng `Clock.fixed` hoặc `MutableClock` có kiểm soát. Nếu muốn biết code đọc timestamp mấy lần, dùng Mockito `@Mock Clock` ở unit test rất hẹp; đừng spy chỉ để có một `verify(clock).instant()`.

### 25.2. Một clock cho nhiều module có luôn đúng không?

Một số hệ thống cần chung một `TimeSource` để thống nhất instant; một số cần business zone khác theo tenant hoặc domain. Không tạo shared module dependency tuỳ tiện chỉ vì nhiều module cần `Clock`: `java.time.Clock` là JDK abstraction có thể được cấu hình ở application bootstrap và inject theo nhu cầu.

Nếu thiết kế một **module thời gian dùng chung**, hãy công bố API rõ, kiểm tra dependency bằng `ApplicationModules.verify()` và tránh dependency cycle. Đừng để module `orders` import repository/config internals của `quotes` chỉ để đồng bộ clock.

## 26. Kiểm chứng ranh giới kiến trúc với ApplicationModules

Giả sử `orders` đã khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "quotes :: api")
package com.example.shop.orders;
~~~

Thì class `OrderService` chỉ được phụ thuộc public `QuoteProvider` và `QuoteSnapshot`, không import `quotes.internal.QuoteRepository` để “tự kiểm tra hạn trong database”.

Architecture test:

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`ApplicationModules.verify()` kiểm tra các quy tắc module dependency graph, access đến API không công bố và `allowedDependencies` theo mô hình Spring Modulith. Nó **không thay thế** bài test time boundary/DB event. Một service có thể phụ thuộc đúng module API nhưng vẫn dùng sai `Instant.now()` hoặc timezone.

### 26.1. Test dễ khởi động không đồng nghĩa module hợp lệ

Khi `@ApplicationModuleTest(STANDALONE)` thiếu bean `QuoteProvider`, thay bằng `@MockitoBean QuoteProvider` là hợp lý vì đó là public collaborator ngoài module. Nếu thay bằng mock `quotes.internal.QuoteRepository`, test có thể khởi động nhưng tạo một dependency vi phạm kiến trúc. Mockito không hợp thức hóa import sai ranh giới.

Nếu module `orders` sử dụng `Clock` như JDK abstraction, việc mock/fake Clock **không cần** thêm dependency sang module `quotes`; đó là hai biên độc lập: **nguồn thời gian** và **giá trị expiry**.

## 27. Quality gate CI: không chỉ chạy test với một timezone

| Gate | Điều cần bảo vệ | Công cụ | Lỗi có thể phát hiện |
| --- | --- | --- | --- |
| **Unit time boundary** | `now < expiresAt`, equality hết hạn. | `Clock.fixed`, parameterized tests. | Off-by-one nanosecond/equality. |
| **Unit orchestration** | Timestamp cùng snapshot, đúng payload. | Mockito repository/publisher, captors. | Code bỏ qua injected Clock. |
| **Module persistence** | Order lưu `acceptedAt` đúng. | `@ApplicationModuleTest`, real JPA. | Timestamp không được persist hoặc mapping sai. |
| **Module event publication** | Event có `occurredAt` đúng. | `PublishedEvents`. | Event timestamp dùng system time khác. |
| **Negative expiry** | Quote hết hạn không tạo row/event. | Clock fixed đúng hạn và sau hạn. | Chấp nhận quá hạn. |
| **Business timezone** | Ngày đúng theo vùng quy định. | Clock fixed với `ZoneId` tương ứng. | Lệch ngày lúc UTC midnight. |
| **DST** | Gap/overlap được giải theo policy. | `ZoneId`/real calendar rules. | Lịch chạy nhầm giờ mùa hè. |
| **Database precision** | Timestamps đọc lại theo schema. | `@DataJpaTest`, dialect phù hợp. | Truncate/mapping/zone sai. |
| **Migration/schema** | Column types, defaults và DB time source. | Real migration + DB integration test. | H2/DDL auto che sai lệch production. |
| **Provider contract** | Quote expiry và customer ownership đúng. | Module test của `quotes`. | Mock giả định sai provider behavior. |
| **Wiring** | `orders` nhận quote thật đúng contract. | `DIRECT_DEPENDENCIES` test. | Thiếu bean hoặc mismatch giữa module. |
| **Scheduler** | Cleanup đúng cutoff và trigger đúng. | Unit job method + scheduler integration. | Tưởng đổi Clock sẽ tua timer. |
| **Async/registry** | Listener hoàn tất sau commit, replay giữ event time. | `Scenario`/Awaitility, registry tests. | Event time bị đổi khi retry. |
| **Clock skew** | Hệ thống ngoài có safety margin/authority đúng. | Contract/integration tests. | Chấp nhận quote expired khi drift. |
| **Architecture** | Đúng named interface và dependency rules. | `ApplicationModules.verify()`. | Import `quotes.internal`, cycle. |

### 27.1. Chiến lược CI theo chi phí

PR nên chạy **unit time boundary**, architecture test và những module tests nhanh có JPA. Với sản phẩm hỗ trợ nhiều vùng, hãy dùng dữ liệu cụ thể quanh midnight/DST thay vì chỉ dựa vào timezone môi trường CI.

Các tests có DB thực, broker, scheduler hoặc external provider có thể ở integration stage chuyên biệt, nhưng phải được kích hoạt khi thay đổi ảnh hưởng schema, time handling, event contract hoặc reliability. **Không chuyển tất cả thành mocked-clock unit tests** rồi bỏ qua phần hạ tầng thực cần chứng minh.

### 27.2. Đừng phụ thuộc vào giờ hệ điều hành của CI

Một suite deterministic nên pass dù:

- CI chạy lúc nửa đêm.
- Server timezone là UTC hay vùng khác.
- Thời gian build bị chậm hoặc lịch cron khác.
- Máy chủ lệch múi giờ mặc định của developer.

Nếu business contract cần zone cụ thể, test phải **khai báo zone đó**. Với boundary tests, dùng `Clock.fixed`, không dùng `System.setProperty("user.timezone", ...)` toàn JVM như cách mặc định vì nó có thể nhiễu các tests chạy song song và cache timezone.

## 28. Những anti-pattern thường gặp

### 28.1. Dùng Instant.now() trực tiếp trong service

~~~java
if (Instant.now().isBefore(expiresAt)) {
    // ...
}
~~~

Test không kiểm soát được mốc hiện tại. Inject Clock và dùng `clock.instant()`.

### 28.2. Thread.sleep để qua thời điểm hết hạn

~~~java
Thread.sleep(1_000);
assertThat(service.isExpired()).isTrue();
~~~

Chậm, flaky và không giải quyết nanosecond boundary. Dùng fixed/mutable clock và kiểm tra mốc chính xác.

### 28.3. Mock Clock.instant nhưng quên getZone

~~~java
when(clock.instant()).thenReturn(T0);
// LocalDate.now(clock) có thể cần clock.getZone() hợp lệ.
~~~

Dùng `Clock.fixed(T0, zone)` hoặc stub đầy đủ những methods được SUT dùng.

### 28.4. Clock.offset trên systemUTC nhưng gọi là fixed

~~~java
Clock clock = Clock.offset(
        Clock.systemUTC(), Duration.ofDays(1));
~~~

Clock vẫn chạy theo thời gian thật; không thích hợp để kiểm tra một ranh giới chính xác.

### 28.5. Clock.fixed được dùng để đợi async timeout

Đồng hồ nghiệp vụ không tiến, vòng lặp thời gian có thể không kết thúc; Awaitility hoặc monotonic timeout riêng mới phù hợp.

### 28.6. Mock OrderRepository trong test cần DB

`verify(save)` chỉ là invocation. Giữ repository/JPA thật trong `@ApplicationModuleTest`.

### 28.7. Mock ApplicationEventPublisher trong test cần PublishedEvents

Thay publisher có thể bypass event dispatch. Giữ publisher thật, chỉ mock API ngoài module hoặc I/O boundary.

### 28.8. Nghĩ @CreatedDate tự dùng Clock đã inject

Spring Data auditing có DateTimeProvider riêng; JPA/Hibernate và database có nguồn time khác. Cấu hình rõ và test integration.

### 28.9. So sánh Instant sau DB với nanosecond tuyệt đối

Database có thể giảm precision; test sai contract làm suite đỏ vô nghĩa. Chọn precision và assert theo schema đã công bố.

### 28.10. Dùng LocalDateTime không zone cho expiry xuyên vùng

Giờ địa phương không xác định duy nhất instant, đặc biệt qua DST. Dùng `Instant` cho hạn tuyệt đối và `ZoneId` cho lịch kinh doanh.

### 28.11. Đổi Clock và chờ @Scheduled tự kích hoạt

Clock chỉ điều khiển business time ở code đọc nó; scheduler trigger có thời gian riêng. Tách job logic khỏi trigger.

### 28.12. Clock mutable singleton dùng chung các tests song song

Test A advance Clock của test B, gây flaky. Dùng fixed clock per context hoặc có isolation/reset rõ.

### 28.13. Verify chính xác số lần Clock.instant trong mọi test

Đóng băng implementation detail; ưu tiên assert kết quả timestamp và expiry decision.

### 28.14. Đồng nhất occurredAt và processedAt

Event có thể bị giao lại sau nhiều phút, listener có thời điểm xử lý riêng. Giữ event-time gốc khi retry.

### 28.15. Chỉ test một instant giữa ngày

Không phát hiện equality boundary, timezone midnight, DST, database precision hoặc clock skew. Bổ sung các case có chủ đích.

## 29. Hướng dẫn debug khi test thời gian lúc xanh lúc đỏ

Khi một test liên quan thời gian không ổn định hoặc cho kết quả khác nhau trên developer machine và CI, hãy điều tra có hệ thống:

1. **Source code đọc thời gian từ đâu?** Tìm `Instant.now()`, `LocalDate.now()`, `System.currentTimeMillis()`, `Clock`, SQL `now()`, JPA audit hoặc framework library clock.
2. **Test đã inject đúng bean Clock chưa?** Xem Spring context có nhiều bean clock, `@Primary`, `@Qualifier` hoặc bean override nào đang được sử dụng.
3. **Clock có thật sự fixed không?** `Clock.offset(Clock.systemUTC(), ...)` vẫn chạy; `Clock.tick(...)` cũng vẫn phụ thuộc thời gian hệ thống.
4. **Mockito mock có thiếu getZone không?** `LocalDate.now(clock)` khác `Instant.now(clock)` về nhu cầu zone.
5. **Có nhiều lần đọc now?** Một lần kiểm tra expiry và một lần gán timestamp có thể băng qua deadline.
6. **Equality boundary được định nghĩa ra sao?** `isBefore`, `isAfter`, `!isBefore` và `!isAfter` không tương đương tại đúng hạn.
7. **Timezone trong business contract là gì?** UTC timestamp và business date địa phương khác nhau ở mốc nửa đêm.
8. **Có DST không?** Local time không tồn tại hoặc lặp lại cần được resolve theo policy.
9. **DB có dùng nguồn thời gian khác không?** `CURRENT_TIMESTAMP`, trigger hoặc Hibernate auditing có thể bypass injected Clock.
10. **Precision giữa Java và database giống nhau không?** `Instant` nanosecond có thể bị truncate/round.
11. **Test có đang ở trong outer transaction rollback không?** Một record có thể đọc được trước commit nhưng sau test không tồn tại.
12. **Test có phụ thuộc scheduler/async callback không?** Đổi business clock không tua executor timer; phải chờ side effect theo điều kiện.
13. **Clock có bị chia sẻ giữa tests không?** Mutable singleton, Spring context cache hoặc test song song tạo nhiễu.
14. **Provider ngoài có dùng clock khác không?** Quote expiration, JWT và payment validity có thể phụ thuộc time authority của provider.
15. **Kiến trúc có bị sửa để test dễ chạy không?** Nếu module `orders` import `quotes.internal`, chạy `ApplicationModules.verify()`.

### 29.1. Một workflow debug tối thiểu

Nếu test “quote hết hạn nhưng vẫn được chấp nhận”:

~~~text
1. Ghi rõ quote.expiresAt theo ISO-8601 UTC.
2. Ghi rõ Clock.instant() trong OrderService.
3. Viết test đúng tại expiresAt, không dùng sleep.
4. Assert exception + không có row + không có OrderPlaced.
5. Kiểm tra @MockitoBean QuoteProvider trả đúng customer/quote ID.
6. Xác minh OrderService dùng Clock bean test, không gọi Instant.now().
7. Nếu DB có row dù test báo lỗi, kiểm tra transaction boundary.
8. Nếu listener khác tạo side effect, kiểm tra AFTER_COMMIT riêng.
~~~

Không sửa bằng cách tăng timeout từ một giây lên mười giây mà không hiểu nguồn thời gian; tăng timeout chỉ che lỗi nondeterminism.

## 30. Bài tập tình huống: flash sale, đơn hàng và thời gian xử lý

Một nền tảng Spring Modulith có:

- Module `promotions` công bố public API `PromotionQuote` với `expiresAt` là instant UTC.
- Module `checkout` dùng `Clock` để chấp nhận/loại bỏ quote.
- Module `orders` lưu đơn hàng cùng `acceptedAt` trong PostgreSQL.
- Module `notifications` có `@ApplicationModuleListener` gửi email sau commit.
- Một `@Scheduled` job hủy các reservation đã hết hạn.
- Hệ thống phục vụ khách ở Việt Nam và Đức; một báo cáo tổng kết theo **ngày địa phương của thị trường**.

Contract nghiệp vụ:

1. Quote hết hạn **tại** `expiresAt`, không còn hợp lệ kể từ thời điểm bằng hạn trở đi.
2. Chỉ giao một `Clock` snapshot cho quyết định và timestamp `acceptedAt` của lệnh checkout.
3. Nếu hết hạn, không lưu order và không phát `OrderPlaced`.
4. Nếu order đã commit, event `OrderPlaced.occurredAt` phải giữ nguyên khi listener retry.
5. Report Việt Nam tính ngày theo `Asia/Ho_Chi_Minh`; report Đức tính ngày theo `Europe/Berlin`.
6. Job reservation chỉ chọn record với `expiresAt <= cutoff`, nhưng schedule trigger không phải business clock.

### Câu hỏi

1. Vì sao test `Instant.now().plusMillis(100)` rồi `Thread.sleep(50)` dễ flaky?
2. Với contract hết hạn tại đúng hạn, dùng `isBefore` hay `!isAfter`?
3. Nếu muốn test mốc `expiresAt.minusNanos(1)`, `expiresAt` và `expiresAt.plusNanos(1)`, nên cấp Clock thế nào?
4. `Clock.offset(Clock.systemUTC(), Duration.ofDays(1))` có deterministic không?
5. Vì sao `@Mock Clock` có thể gây `NullPointerException` khi code dùng `LocalDate.now(clock)`?
6. Trong `@ApplicationModuleTest(STANDALONE)` của `checkout`, nên mock public `promotions` API hay repository của `checkout`?
7. Nếu `AcceptedAt` được JPA `@CreationTimestamp` sinh, inject `Clock.fixed` có tự điều khiển giá trị đó không?
8. `PublishedEvents` thấy `OrderPlaced` có chứng minh transaction đã commit không?
9. Nếu ngày UTC còn là 26/11 nhưng tại TP. Hồ Chí Minh đã 27/11, nên dùng kiểu/zone nào để tính business date?
10. Nếu `LocalDateTime` của Đức là 02:30 trong ngày DST overlap, nó có tương ứng một instant duy nhất không?
11. Tăng clock mutable thêm sáu phút có làm `@Scheduled(fixedDelay = 60000)` chạy ngay không?
12. Nếu order đã commit nhưng listener nhận event trễ mười phút, có được thay `occurredAt` bằng `clock.instant()` lúc retry không?
13. PostgreSQL lưu timestamp đến microsecond còn Java có nanosecond, assertion nên chọn thế nào?
14. Khi hai node lệch clock vài giây, chỉ có unit test `Clock.fixed` đã đủ kiểm soát rủi ro quote expiry chưa?
15. Nếu module `checkout` import `promotions.internal.PromotionRepository`, quality gate nào phát hiện?

### Đáp án gợi ý

1. OS scheduling, GC và CI tải cao làm khoảng chờ/độ trễ không ổn định; test có thể băng qua deadline ngoài dự kiến.
2. Hợp lệ khi `now.isBefore(expiresAt)`; tại equality phải từ chối. `!isAfter` sẽ coi equality là hợp lệ, sai contract.
3. Dùng ba `Clock.fixed(instant, ZoneOffset.UTC)` hoặc parameterized test với fixed instant, không sleep.
4. **Không.** Base là system clock vẫn tiến theo thời gian thật; chỉ cộng một offset.
5. Mockito mock chưa stub `getZone()` có thể trả null; `Clock.fixed` có cả instant và zone hợp lệ.
6. Mock **public API `promotions`** khi chỉ test `checkout`; giữ service/repository và event infrastructure của module đang test thật nếu mục tiêu có persistence/event.
7. Không mặc nhiên. Hibernate timestamp generation có nguồn riêng; phải kiểm tra provider/config và JPA read-back.
8. Không. Event có thể được phát trong transaction trước khi rollback; test DB commit/rollback và listener `AFTER_COMMIT` riêng.
9. Tính `LocalDate` từ `Instant` với `ZoneId.of("Asia/Ho_Chi_Minh")`.
10. Không. DST overlap có thể có hai offsets/instants; cần `ZoneId` và chính sách chọn offset rõ.
11. Không. Scheduler trigger/real timer độc lập với business Clock inject vào job; gọi job logic trực tiếp trong unit/integration test khi cần.
12. Không. `occurredAt` là event-time gốc, phải giữ nguyên qua retry; có thể có `processedAt` riêng của receiver.
13. Xác định precision contract, test cùng database/dialect production, chuẩn hóa nếu cần; không so sánh nanoseconds với schema chỉ lưu microseconds một cách mù quáng.
14. Chưa đủ. Cần contract về time authority, clock sync, drift/safety margin nếu có, cùng integration tests.
15. `ApplicationModules.of(...).verify()` phát hiện dependency đến package không được public/named interface hoặc vi phạm `allowedDependencies`.

## 31. Checklist trước khi viết test dữ liệu thời gian

- [ ] Nghiệp vụ đã định nghĩa rõ thời điểm nào là **hợp lệ**, đặc biệt trường hợp bằng hạn.
- [ ] Biết `expiresAt` dùng instant UTC hay ngày địa phương; không trộn `Instant` và `LocalDateTime` vô thức.
- [ ] Domain/service dùng injected `Clock`, không gọi `Instant.now()` trực tiếp tại các điểm cần kiểm soát.
- [ ] Production có bean `Clock` rõ ràng; test override đúng bean, không tạo ambiguity.
- [ ] Unit tests ưu tiên `Clock.fixed` với instant/zone cụ thể.
- [ ] Nếu dùng `@Mock Clock`/`@MockitoBean Clock`, stub đủ `instant()`, `getZone()` theo code thật.
- [ ] Nếu dùng `MutableClock`, có reset/isolation và không chạy song song vô thức.
- [ ] Không dùng `Thread.sleep` để chờ đến business expiry.
- [ ] Test có ba case: trước hạn, **đúng hạn**, sau hạn.
- [ ] Timestamp cho entity/event được lấy từ một snapshot `now` nếu contract yêu cầu nhất quán.
- [ ] Unit mock repository/publisher chỉ được diễn giải là bằng chứng invocation.
- [ ] `@ApplicationModuleTest` giữ service, JPA repository và publisher thật khi cần DB/event assertions.
- [ ] Chỉ mock public collaborator của module khác qua `@MockitoBean` trong `STANDALONE`.
- [ ] Với DB, có read-back và hiểu `@Transactional` ở test có thể ngăn commit thực.
- [ ] Với `@CreatedDate`, `@CreationTimestamp`, SQL default/trigger, đã xác nhận nguồn thời gian riêng.
- [ ] Schema/JDBC precision đã được xác định; không assert nanosecond khi DB không hỗ trợ.
- [ ] Business date dùng ZoneId cụ thể, không phụ thuộc default timezone của CI.
- [ ] Nếu phục vụ thị trường có DST, có test gap/overlap và quy tắc xử lý ngày địa phương.
- [ ] Nếu có `@Scheduled`, business job test tách khỏi scheduler trigger test.
- [ ] Nếu có listener async, chờ observable state bằng `Scenario`/Awaitility, không suy completion từ `PublishedEvents`.
- [ ] Khi event replay/retry, `occurredAt` không bị tái sinh; idempotency key/event ID giữ nguyên.
- [ ] Nếu quote/token đến từ hệ thống ngoài, đã xác định time authority, clock skew và margin theo contract.
- [ ] Provider module có contract tests riêng, không chỉ response do consumer mock tự dựng.
- [ ] Có integration test không override quote provider khi mục tiêu là wiring giữa module thật.
- [ ] `ApplicationModules.verify()` chạy trong CI để giữ named interfaces/`allowedDependencies`.
- [ ] CI bao phủ time boundary, timezone/DST, persistence precision, event semantics và các tầng integration phù hợp.

**Kết luận:** Kiểm thử thời gian tốt không phải là làm hệ thống “chạy nhanh hơn” bằng `Thread.sleep` hay điều chỉnh system clock, mà là **đưa thời gian thành input có thể kiểm soát**. `Clock.fixed` thường là test double đơn giản, đáng tin cậy nhất; Mockito `@Mock Clock` hoặc `@MockitoBean Clock` hữu ích khi cần stub từng read nhưng phải biết giới hạn của chúng. Trong Spring Modulith, hãy mock public API ngoài module, giữ logic/JPA/event publisher thật ở `@ApplicationModuleTest`, kiểm tra ranh giới đúng hạn và timestamp bằng dữ liệu observable; đồng thời phân biệt application clock với DB, scheduler, listener, broker và time authority bên ngoài. Cuối cùng, `ApplicationModules.verify()` và quality gates CI bảo vệ cả kiến trúc lẫn những hồi quy về thời gian khó tái hiện.

### Tài liệu tham khảo

- [Java SE — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): `fixed`, `offset`, `tick`, `instant`, `withZone`.
- [Java SE — Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html): điểm trên UTC timeline, precision và so sánh.
- [Java SE — ZoneId](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/ZoneId.html): time-zone rules và DST.
- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, bootstrap modes, `PublishedEvents`.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listeners, publication registry và reliability.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): module boundaries, named interfaces và verification.
- [Spring Framework — @MockitoBean and @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-mockitobean.html): Spring Test bean override.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `AFTER_COMMIT` và các transaction phases.
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): scheduler triggers và `@Scheduled`.
- [Spring Data — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html): `@CreatedDate` và auditing infrastructure.
- [Mockito — Mockito API](https://javadoc.io/doc/org.mockito/mockito-core/latest/org.mockito/Mockito.html): stubbing, mocks/spies và verification.

> Ghi chú áp dụng: các ví dụ giả định Java 17+ (Java Time APIs), Spring Framework 6.2+ cho `@MockitoBean`, Spring Modulith, Spring Data JPA, JUnit 5 và cấu hình datasource/event infrastructure thích hợp. Một số đoạn là test skeleton hoặc minh họa riêng lẻ cần bổ sung imports, bean, fixtures và schema theo dự án. Chính xác của JPA auditing, SQL timestamp precision, `@Scheduled` và Event Publication Registry phụ thuộc phiên bản/config. Theo quy trình STEP_4, đây là bản biên soạn; chưa chạy Gradle hay Content QA chuyên môn.




