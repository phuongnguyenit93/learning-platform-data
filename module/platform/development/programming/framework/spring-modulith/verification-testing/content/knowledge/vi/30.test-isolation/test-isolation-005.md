# Cô lập clock, random và identifier trong kiểm thử Spring Modulith

## 1. Vì sao ba nguồn không xác định này làm test thiếu tin cậy?

Một bài kiểm thử module có thể dùng đúng `@ApplicationModuleTest`, chuẩn bị database sạch và không chia sẻ executor, nhưng vẫn thất bại ngẫu nhiên vì ba yếu tố:

- **Clock (đồng hồ):** thời điểm test chạy ảnh hưởng deadline, thời gian hết hạn, lịch retry, TTL, mã ngày và bất biến thời gian.
- **Random (nguồn ngẫu nhiên):** dữ liệu thử nghiệm, lựa chọn nhánh, thời gian backoff hoặc mã tham chiếu thay đổi giữa các lần chạy.
- **Identifier (định danh):** ID của aggregate, event, transaction hoặc correlation bị dùng lại hay tạo không nhất quán, khiến test đọc nhầm trạng thái hoặc thông điệp.

Ví dụ, một đơn hàng có hạn thanh toán 15 phút. Nếu test gọi `Instant.now()` khi tạo order, gọi lần nữa khi gửi event, rồi để listener bất đồng bộ xử lý, kết quả có thể khác nhau tùy thời điểm CI chạy và độ trễ scheduling. Nếu test dùng chung một `orderId` cho mọi scenario, state `PAID` từ bài trước có thể làm bài hiện tại pass **trước khi listener được gọi**.

**Cô lập clock, random và identifier** không phải cố làm mọi thứ giống production ở từng dòng code. Mục tiêu là làm **tiền đề nghiệp vụ xác định, tái hiện được lỗi, và đồng thời không tạo xung đột dữ liệu giữa những scenario độc lập**.

Bài học thuộc chương *Test isolation* trong học phần `SPRING_MODULITH_VERIFICATION_TESTING`. Học phần hướng tới kiểm chứng ranh giới bằng `ApplicationModules` và quy tắc phụ thuộc module, thực hành `@ApplicationModuleTest`, event, database, integration và quality gate CI để ngăn phụ thuộc sai cũng như hồi quy.

Sau bài này, bạn có thể:

1. Đưa `java.time.Clock` vào nghiệp vụ qua dependency injection và viết test thời gian cố định.
2. Tách **business time** khỏi **thời gian thật dùng cho polling/timeout** trong `Scenario`.
3. Dùng seed ngẫu nhiên để tái hiện input mà không để một generator mutable rò state giữa test.
4. Thiết kế ID generator và correlation ID bảo vệ tính độc lập của dữ liệu.
5. Phân biệt ID aggregate, ID của logical event, idempotency key và publication ID của hạ tầng.
6. Kiểm tra interaction với transaction, JPA auditing, timestamp của database, async executor và message broker.
7. Kết hợp các kiểm thử trên với `ApplicationModules.verify()` và CI quality gate.

## 2. Cần cô lập chính xác những gì?

| Nguồn | Ví dụ | Hỏng test theo cách nào? | Thiết kế test |
| --- | --- | --- | --- |
| Đồng hồ JVM | `Instant.now()`, `LocalDate.now()` | Qua nửa đêm; vượt deadline khi CI chậm | Inject `Clock`, cố định thời gian và zone |
| Đồng hồ DB | `CURRENT_TIMESTAMP`, default timestamp | Khác JVM clock hoặc timezone DB | Tách phạm vi test, kiểm soát/kiểm chứng nguồn timestamp |
| Random trong service | `RandomGenerator.nextInt()` | Không tái hiện được input làm lộ bug | Seed cục bộ, ghi seed khi fail |
| Random dùng chung bean | Singleton `Random`/`SplittableRandom` | Các test ăn chung chuỗi pseudo-random | Mỗi scenario một generator hoặc factory |
| Aggregate ID | `orderId`, `reservationId` | Đọc/ghi nhầm dữ liệu bài trước | ID độc lập cho từng scenario |
| Event ID | `eventId` | Đếm event nhầm, replay nhầm | Một ID logical event, giữ nguyên khi retry |
| Idempotency key | `transactionId` | Duplicate side effect hoặc collision | Khóa unique theo hợp đồng nghiệp vụ |
| Consumer correlation | header, trace/correlation ID | Test bắt message của scenario khác | Mang ID xuyên event, broker và query |
| Hạn timeout | `Duration.ofSeconds(...)` | Test treo hoặc flaky | Timeout hữu hạn dựa trên đồng hồ tiến triển thật |

**Không đồng nhất “deterministic” với “ID luôn giống nhau”.** Trong một test đơn lẻ, một ID đã cho có thể là cố định để assertion dễ đọc; nhưng giữa các test cùng database, **ID trùng nhau** lại tạo nhiễm chéo. Có thể dùng ID mới cho từng scenario, trong khi mọi phép so sánh đều sử dụng chính ID được fixture trả về.

## 3. Đưa `Clock` vào business logic

Lời gọi trực tiếp:

```java
if (Instant.now().isAfter(order.paymentDeadline())) {
    throw new PaymentWindowExpiredException();
}
```

trói nghiệp vụ vào đồng hồ hệ thống thật. Khi test ở ranh giới hết hạn, chỉ cần máy CI chạy chậm vài mili-giây là điều kiện có thể đổi khác.

Thay bằng một dependency `Clock`:

```java
package com.example.shop.orders.internal;

import java.time.Clock;
import java.time.Instant;

import org.springframework.stereotype.Service;

@Service
class PaymentWindowPolicy {

    private final Clock clock;

    PaymentWindowPolicy(Clock clock) {
        this.clock = clock;
    }

    boolean canCapture(Instant deadline) {
        Instant now = clock.instant();
        return !now.isAfter(deadline); // cho phép đúng tại deadline
    }
}
```

Ý nghĩa của điều kiện đã rõ: `now <= deadline` được phép. Một ứng dụng khác có thể chọn `now < deadline`; test phải phản ánh **hợp đồng thực tế**, không tự suy luận dấu so sánh.

### 3.1. Bean clock trong production

```java
package com.example.shop;

import java.time.Clock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class TimeConfiguration {

    @Bean
    Clock applicationClock() {
        return Clock.systemUTC();
    }
}
```

Clock production có vùng giờ UTC, nhưng vẫn là đồng hồ thực. Inject một clock dùng chung giúp nhiều service dùng cùng **quy tắc lấy giờ**; nếu cần lấy một snapshot thống nhất cho cả workflow, hãy lấy `Instant` một lần rồi truyền nó vào các hàm liên quan, thay vì mỗi nơi tự gọi `clock.instant()`.

### 3.2. Cố định thời gian bằng `Clock.fixed(...)`

Trong module test, sử dụng một cấu hình test:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
class FixedTimeTestConfiguration {

    static final Instant FIXED_INSTANT =
            Instant.parse("2026-03-01T10:00:00Z");

    @Bean
    @Primary
    Clock fixedApplicationClock() {
        return Clock.fixed(FIXED_INSTANT, ZoneOffset.UTC);
    }
}
```

`@Primary` giúp chọn clock của test khi context có cả clock production; test cần kiểm tra xem ứng dụng có dùng `@Qualifier` hay bean override riêng khiến `@Primary` không đủ hay không. Cấu hình trên là ví dụ cho Spring Boot/Spring Framework có dependency phù hợp, không phải API bắt buộc của Spring Modulith.

Một bean `Clock.fixed(...)` **bất biến** và an toàn khi được tái sử dụng qua Spring TestContext cache, miễn các test không kỳ vọng mỗi method có một thời gian khác.

### 3.3. Test thuần Java cho ranh giới deadline

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;

class PaymentWindowPolicyTests {

    private static final Instant DEADLINE =
            Instant.parse("2026-03-01T10:00:00Z");

    private PaymentWindowPolicy policyAt(Instant at) {
        Clock clock = Clock.fixed(at, ZoneOffset.UTC);
        return new PaymentWindowPolicy(clock);
    }

    @Test
    void allowsPaymentBeforeDeadline() {
        assertThat(policyAt(DEADLINE.minusNanos(1))
                .canCapture(DEADLINE)).isTrue();
    }

    @Test
    void allowsPaymentExactlyAtDeadline() {
        assertThat(policyAt(DEADLINE)
                .canCapture(DEADLINE)).isTrue();
    }

    @Test
    void rejectsPaymentAfterDeadline() {
        assertThat(policyAt(DEADLINE.plusNanos(1))
                .canCapture(DEADLINE)).isFalse();
    }
}
```

Đây là bài **unit test không cần Spring context**, rất nhanh và có khả năng tái hiện tốt. Hãy kiểm tra các mốc âm/dương/bằng nhau theo **độ chính xác mà hệ thống thực sự lưu và so sánh**: nếu database hoặc API chỉ lưu đến mili-giây, test mức nanosecond tại database có thể không phản ánh dữ liệu production.

## 4. Phân biệt `Instant`, timezone và hiển thị ngày giờ

Cố định `Clock` chưa đủ nếu code lưu `LocalDateTime` mà không định nghĩa zone. Các kiểu có vai trò khác nhau:

| Kiểu | Phù hợp với | Lưu ý trong test |
| --- | --- | --- |
| `Instant` | Thời điểm tuyệt đối để so deadline, event timestamp | Không mang timezone hiển thị; thuận lợi cho contract xuyên module |
| `ZonedDateTime` | Lịch/ngày giờ gắn vùng có quy tắc DST | Phải chỉ định `ZoneId` và tình huống DST |
| `OffsetDateTime` | Thời điểm với offset cụ thể | Offset không thay thế toàn bộ quy tắc timezone vùng |
| `LocalDateTime` | Ngày giờ địa phương không có zone | Không tự đại diện một instant duy nhất |
| `LocalDate` | Quy tắc nghiệp vụ theo ngày | Phải hiểu ngày tính theo zone nào |

Ví dụ, hai câu gọi:

```java
LocalDate todayUTC = LocalDate.now(Clock.systemUTC());
LocalDate todayHcm = LocalDate.now(
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
```

có thể cho **hai ngày khác nhau** ở thời điểm gần ranh giới ngày. Trong test, nên cố định một `Instant` và dùng `ZoneId` đúng theo nghiệp vụ; không thay đổi timezone mặc định của JVM toàn cục nếu không có cơ chế cô lập.

### 4.1. Kiểm tra chuyển ngày/DST có chủ đích

Với lịch địa phương, hãy có testcase:

- Đúng trước và sau 00:00 ở timezone của nghiệp vụ.
- Ngày cuối tháng và đầu tháng.
- Năm nhuận nếu dữ liệu có ngày 29/02.
- Giờ trùng/không tồn tại tại vùng có DST, nếu liên quan.
- Timestamp sát deadline và chênh lệch precision khi lưu DB.

Không coi timezone máy CI là một phần tiền đề ngầm. Nếu một ứng dụng dùng `LocalDate.now()` không truyền clock, test đổi `user.timezone` toàn JVM có thể gây ảnh hưởng test khác chạy song song; ưu tiên inject clock và zone trong API nghiệp vụ.

## 5. Khi cần điều khiển thời gian: `Clock.offset` và clock có thể thay đổi

`Clock.fixed(...)` phù hợp với test chỉ cần một thời điểm. Muốn kiểm tra hành vi thay đổi theo thời gian trong cùng scenario, có hai cách.

### 5.1. Dùng clock mới ở mỗi phép kiểm tra

```java
Clock before = Clock.fixed(
        Instant.parse("2026-03-01T09:59:59Z"),
        ZoneOffset.UTC);

Clock after = Clock.fixed(
        Instant.parse("2026-03-01T10:00:01Z"),
        ZoneOffset.UTC);
```

Thay vì mutate một bean Spring, unit test có thể tạo hai instance của service với hai clock khác nhau. Cách này giúp test độc lập, phù hợp cho nhiều bài test domain.

`Clock.offset(baseClock, duration)` cũng có thể tạo một clock với độ lệch cố định. Nhưng **offset trên clock thực vẫn tiếp tục chạy theo thời gian thực**, không phải clock freeze. Để test xác định, dùng base `Clock.fixed(...)`.

### 5.2. Test-only adjustable clock

Khi một integration scenario cần “tiến tới sau hạn” mà không restart context, có thể tạo một clock test có thể điều khiển:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneId;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

final class AdjustableClock extends Clock {

    private final ZoneId zone;
    private final AtomicReference<Instant> instant;

    AdjustableClock(Instant initial, ZoneId zone) {
        this.zone = Objects.requireNonNull(zone);
        this.instant = new AtomicReference<>(
                Objects.requireNonNull(initial));
    }

    void advanceTo(Instant next) {
        instant.set(Objects.requireNonNull(next));
    }

    @Override
    public ZoneId getZone() {
        return zone;
    }

    @Override
    public Clock withZone(ZoneId newZone) {
        AdjustableClock copy = new AdjustableClock(
                instant(), Objects.requireNonNull(newZone));
        return copy;
    }

    @Override
    public Instant instant() {
        return instant.get();
    }
}
```

Đây là test-support class **minh họa**, không có sẵn trong Spring hoặc Spring Modulith. `AtomicReference` giúp lời đọc/ghi instant không bị rách giữa thread, nhưng **không tự tạo isolation giữa test methods**.

**Cảnh báo về bean singleton:** nếu `AdjustableClock` được đăng ký làm Spring singleton và hai test sử dụng lại cùng context, test A gọi `advanceTo(...)` sẽ làm thời gian của test B thay đổi. Tránh dùng chung mutable clock giữa các test song song; nếu cần, hãy tách scope/context hoặc reset có điểm đồng bộ sau khi không còn worker dùng nó.

### 5.3. Thay đổi giờ nghiệp vụ không tự chạy scheduled tasks

Khi gọi `advanceTo(...)`, các đối tượng đang đọc clock đó sẽ thấy thời gian mới. Nhưng điều này **không buộc** scheduler của Spring, Quartz, Kafka retry hoặc hệ điều hành lập tức kích hoạt các task đang lên lịch bằng đồng hồ/trigger riêng.

Với test expiration có scheduler:

1. Unit test chính sách hết hạn bằng clock giả.
2. Module test gọi **use case kiểm tra quá hạn** dưới clock kiểm soát nếu hành vi này được công khai hợp lệ.
3. Test scheduler integration riêng kiểm tra cron/trigger thật và việc dispatch.
4. Nếu cần virtual time toàn diện, sử dụng công cụ chuyên biệt được scheduler/reactive framework hỗ trợ; không giả định `Clock.fixed` đã điều khiển toàn bộ timer.

## 6. Tách **business clock** khỏi **timeout clock**

Một lỗi tinh vi là cho vòng polling của test đo thời gian bằng chính `Clock.fixed(...)` đang bị đóng băng. Nếu thuật toán timeout phụ thuộc clock đó và thời gian không đổi, điều kiện kết thúc có thể không bao giờ đạt.

Spring Modulith `Scenario` cung cấp các cách chờ theo trạng thái với timeout hữu hạn. Trong test, hãy:

- Inject clock giả vào **business service** để điều khiển deadline, expiration, event timestamp.
- Để cơ chế polling/timeout của test dùng nguồn thời gian **tiến triển thực** theo implementation của thư viện.
- Chọn timeout nhỏ nhưng có căn cứ, dựa trên độ trễ commit, async executor và read model.
- Không dùng `Thread.sleep(...)` để giả lập “thời gian nghiệp vụ đã trôi”.
- Không viết supplier chờ state mà tự tăng clock hoặc publish lại event mỗi lượt poll.

Ví dụ ý nghĩa:

```text
Business Clock: 2026-03-01T10:00:00Z (cố định)
    -> listener quyết định order còn hạn hay đã quá hạn.

Wait timeout: 8 giây thực
    -> test được phép chờ listener và DB commit.
    -> khi không thấy state đích, test fail hữu hạn.
```

Cả hai là những khái niệm thời gian khác nhau. *Cố định đồng hồ nghiệp vụ* không có nghĩa cho phép test chờ mãi không giới hạn.

## 7. Random: phân biệt dữ liệu thử nghiệm với bảo mật và identity

Nguồn pseudo-random thường được sử dụng để tạo số lượng, SKU giả, xác suất, backoff, coupon code hoặc ID. Các mục đích ấy không tương đương:

| Mục đích | Nên dùng gì trong test? | Chú ý |
| --- | --- | --- |
| Sinh dữ liệu đa dạng nhưng tái hiện được | `RandomGenerator`/`SplittableRandom` với seed đã ghi lại | Cô lập generator cho mỗi scenario |
| Chọn nhánh lỗi ngẫu nhiên trong test | Chạy case table/parameterized trước, random nếu thật sự có ích | Không để random quyết định test pass/fail mơ hồ |
| Sinh ID aggregate độc lập | UUID mới hoặc ID generator test scoped | Unique giữa scenarios quan trọng hơn chuỗi pseudo-random cố định |
| Kiểm tra backoff jitter | Truyền nguồn random hoặc hàm jitter điều khiển được | Không sleep theo jitter thật ở unit test |
| Sinh khóa bí mật/token bảo mật | CSPRNG như `SecureRandom` trong production | **Không** dùng seed dự đoán được ở production |

Java 17+ có giao diện `java.util.random.RandomGenerator`. Ví dụ một testcase dùng generator cục bộ:

```java
import java.util.SplittableRandom;
import java.util.random.RandomGenerator;

@Test
void handlesGeneratedQuantities() {
    long seed = 20260301L;
    RandomGenerator random = new SplittableRandom(seed);

    int quantity = 1 + random.nextInt(10); // 1..10
    assertThat(quantity).isBetween(1, 10);
}
```

Ví dụ trên chỉ xác minh giới hạn số; một bài test tốt hơn nên dùng quantity để chạy một invariant nghiệp vụ thật. Không dùng random nếu một bảng kịch bản cố định đã bao phủ đủ các nhánh quan trọng.

### 7.1. Seed giúp tái hiện, nhưng không đủ để bảo đảm isolation

```java
static final Random shared = new Random(42L);
```

Một RNG mutable dùng chung sẽ thay đổi trạng thái sau mỗi lần gọi. Test A dùng thêm một số random có thể khiến chuỗi kết quả trong test B khác đi. Khi chạy parallel, thứ tự lấy số càng khó dự đoán.

**Tốt hơn:** tạo generator mới bên trong mỗi test hoặc fixture invocation; ghi seed cùng input khi test thất bại. Nếu test generator được inject qua Spring singleton, hãy thiết kế một **factory** tạo generator riêng cho scenario, không trả cùng mutable object cho mọi method.

### 7.2. Test property-based và fuzz

Với property-based tests, random input giúp khám phá nhiều tình huống; test framework thường cung cấp seed, shrinking và cơ chế tái chạy. Khi phát hiện lỗi:

1. Giữ seed/input gây lỗi trong báo cáo test.
2. Dùng framework để thu nhỏ testcase nếu hỗ trợ.
3. Bổ sung một regression test cố định cho invariant bị vi phạm.
4. Không che lỗi bằng cách đổi seed cho đến khi “xanh”.

Đừng nhầm số lượng input random lớn với kiểm thử tích hợp tốt: database transaction, listener, consumer group hoặc timeout vẫn có thể khiến test thiếu xác định dù seed đã cố định.

### 7.3. Backoff jitter trong event-driven modules

Nếu retry policy dùng jitter, nên tách **tính toán delay** khỏi **thao tác chờ**.

```java
import java.time.Duration;
import java.util.random.RandomGenerator;

final class RetryDelayPolicy {
    private final RandomGenerator random;

    RetryDelayPolicy(RandomGenerator random) {
        this.random = random;
    }

    Duration nextDelay() {
        int millis = 100 + random.nextInt(101); // 100..200
        return Duration.ofMillis(millis);
    }
}
```

Test unit dùng RNG có seed riêng để kiểm tra khoảng delay hoặc test với fake generator cho giá trị cụ thể. Nhưng test integration về retry cần kiểm tra scheduler/ack/offset và idempotency riêng; không giả định một delay được tính đúng đã chứng minh retry được thực thi.

## 8. Identifier: nên điều khiển hay nên tạo mới?

Một identifier có nhiều trách nhiệm. Bảng sau giúp tránh nhầm:

| ID | Chứng minh điều gì? | Quy tắc giữa scenarios | Quy tắc khi retry |
| --- | --- | --- | --- |
| `orderId` | Aggregate order cụ thể | Mỗi scenario một order mới | Giữ nguyên khi event vẫn nhắm cùng order |
| `eventId` | Một logical event | ID mới cho event mới | **Giữ nguyên** khi phát lại cùng logical event |
| `transactionId` | Giao dịch nghiệp vụ/capture | Tránh trùng giữa giao dịch độc lập | Giữ nguyên để phát hiện xử lý trùng của cùng capture |
| `correlationId` | Một workflow hoặc trace | Mỗi workflow test có correlation riêng | Có thể giữ nguyên cho những bước cùng workflow |
| Registry publication ID | Một bản ghi publication hướng tới listener | Provider tạo/quản lý | Không tự suy bằng với `eventId` |
| Kafka key / Rabbit routing key | Định tuyến message | Tùy hợp đồng transport | Không tự đồng nghĩa ID unique của event |

**Không dùng timestamp làm ID duy nhất.** Hai event có thể được tạo cùng mili-giây, nhất là khi clock đã cố định. Nếu code viết `"ORDER-" + clock.instant().toEpochMilli()`, mọi scenario có cùng frozen clock sẽ tạo cùng ID và gặp unique constraint hoặc đọc nhầm aggregate.

### 8.1. Production ID generator

Một hợp đồng nhỏ giúp code nghiệp vụ tách khỏi cơ chế tạo ID:

```java
// File: com/example/shop/orders/OrderIdGenerator.java
package com.example.shop.orders;

import java.util.UUID;

public interface OrderIdGenerator {
    UUID newId();
}
```

```java
// File: com/example/shop/orders/internal/RandomOrderIdGenerator.java
package com.example.shop.orders.internal;

import java.util.UUID;

import org.springframework.stereotype.Component;
import com.example.shop.orders.OrderIdGenerator;

@Component
class RandomOrderIdGenerator implements OrderIdGenerator {
    @Override
    public UUID newId() {
        return UUID.randomUUID();
    }
}
```

Việc thiết kế ID generator thành một interface công khai có phù hợp hay không tùy ownership: nếu chỉ module `orders` dùng nó, interface có thể nằm trong phạm vi nội bộ module thay vì đưa ra bề mặt public API. Ở đây nó được đặt ở package gốc chỉ để làm rõ contract trong ví dụ.

### 8.2. Generator xác định trong unit test

Một test có thể cấp lần lượt ID đã biết:

```java
import java.util.ArrayDeque;
import java.util.Queue;
import java.util.UUID;

final class SequenceOrderIdGenerator implements OrderIdGenerator {

    private final Queue<UUID> ids;

    SequenceOrderIdGenerator(UUID... values) {
        this.ids = new ArrayDeque<>();
        for (UUID value : values) {
            ids.add(value);
        }
    }

    @Override
    public UUID newId() {
        UUID next = ids.poll();
        if (next == null) {
            throw new IllegalStateException(
                    "No more test identifiers available");
        }
        return next;
    }
}
```

Tạo **một instance generator mới cho mỗi unit test**. `ArrayDeque` không thread-safe; ví dụ dành cho test tuần tự. Nếu một service tạo ID trên nhiều thread, cần một generator thread-safe hoặc cơ chế inject riêng cho từng scope.

### 8.3. Khi nào dùng UUID mới trong integration test?

Một bài test sử dụng **database/broker chung** thường có lợi hơn nếu tạo ID mới theo từng scenario:

```java
UUID orderId = UUID.randomUUID();
UUID eventId = UUID.randomUUID();
String transactionId = "CAPTURE-" + eventId;
```

ID mới giảm xung đột dữ liệu, còn tính tái lập đạt được bằng:

- Fixture tạo baseline theo tham số xác định.
- Test lưu ID vừa tạo và dùng **nhất quán** trong stimulus, query và assertion.
- Log correlation ID khi fail.
- Không dựa vào việc ID có cùng giá trị giữa các lần chạy.
- Nếu cần reproduce một lỗi cụ thể, dùng lại input/test ID trong môi trường cô lập phù hợp.

UUID random không phải bằng chứng tuyệt đối rằng không có collision; database unique constraints vẫn là hàng rào cuối. Ngoài ra, một ID mới không tách được test nếu các bài vẫn tranh cùng SKU, account hoặc topic/consumer group.

## 9. Event replay: cố định ID ở đúng phạm vi

Một test **idempotency** có chủ đích publish lại cùng logical event:

```java
PaymentCaptured event = new PaymentCaptured(
        eventId, orderId, transactionId, capturedAt);

// Lần đầu: xử lý bình thường.
publisher.publishEvent(event);

// Lần sau: replay cùng logical event, không tạo eventId mới.
publisher.publishEvent(event);
```

`PaymentCaptured`, `publisher` và các biến là minh họa. Để kiểm tra at-least-once delivery, cần **điểm đồng bộ cho cả hai lần xử lý**: nếu order đã `PAID` sau lần đầu, assertion ngay sau lần hai có thể pass trước khi listener thứ hai chạy.

Nếu bài test đang mô phỏng **hai capture nghiệp vụ độc lập**, phải tạo event/transaction ID mới theo hợp đồng; dùng lại ID sẽ biến bài test thành duplicate test ngoài ý định.

### 9.1. Định danh cho Event Publication Registry

Spring Modulith Event Publication Registry theo dõi publication cho các target listener được cấu hình. Một event có thể có nhiều publication tương ứng những listener khác nhau. Do đó, test registry không nên giả định:

```text
eventId == publicationRowId
hoặc
một event luôn sinh đúng một publication
```

Khi test registry, lọc theo logical event/correlation **và** target identifier, đồng thời tính đến retention của completed publications theo provider. Clock/ID được cố định ở business event không đồng nghĩa registry dùng chính ID đó làm primary key.

## 10. Một kịch bản `@ApplicationModuleTest` với clock và ID cô lập

Giả sử module `payments` công bố `PaymentCaptured`; module `orders` sở hữu trạng thái thanh toán của đơn hàng và nhận event. Yêu cầu nghiệp vụ:

> Một capture trước hạn thanh toán hợp lệ phải chuyển order từ `AWAITING_PAYMENT` thành `PAID`. Thời điểm xử lý được so với deadline bằng clock của module `orders`. Kết quả phải tham chiếu đúng event và transaction.

Các kiểu sau do **ứng dụng ví dụ tự định nghĩa** (mỗi khai báo `public` trong file Java riêng).

```java
// File: com/example/shop/payments/events/PaymentCaptured.java
package com.example.shop.payments.events;

import java.util.UUID;

public record PaymentCaptured(
        UUID eventId,
        UUID orderId,
        String transactionId) {}
```

```java
// File: com/example/shop/orders/OrderPaymentStatus.java
package com.example.shop.orders;

public enum OrderPaymentStatus {
    AWAITING_PAYMENT, PAID, EXPIRED
}
```

```java
// File: com/example/shop/orders/OrderPaymentView.java
package com.example.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderPaymentView(
        UUID orderId,
        OrderPaymentStatus status,
        Instant deadline,
        Instant paidAt,
        UUID capturedEventId,
        String transactionId) {

    public boolean completedFor(
            UUID expectedEventId, String expectedTransactionId) {
        return status == OrderPaymentStatus.PAID
                && paidAt != null
                && capturedEventId != null
                && capturedEventId.equals(expectedEventId)
                && expectedTransactionId.equals(transactionId);
    }
}
```

```java
// File: com/example/shop/orders/OrderQueries.java
package com.example.shop.orders;

import java.util.Optional;
import java.util.UUID;

public interface OrderQueries {
    Optional<OrderPaymentView> paymentOf(UUID orderId);
}
```

Fixture là test-support **do dự án triển khai**, có transaction riêng commit dữ liệu đầu vào trước stimulus:

```java
// File: test-support OrderFixture.java (minh họa)
import java.time.Instant;
import java.util.UUID;

interface OrderFixture {
    UUID awaitingPaymentAndCommit(Instant deadline);
}
```

Bài test trong module `orders`:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.time.Instant;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
@Import(FixedTimeTestConfiguration.class)
class OrderPaymentTimingTests {

    @Autowired OrderFixture fixture;
    @Autowired OrderQueries queries;

    @Test
    void capturedBeforeDeadlineIsPaid(Scenario scenario) {
        Instant now = FixedTimeTestConfiguration.FIXED_INSTANT;
        Instant deadline = now.plus(Duration.ofMinutes(15));

        UUID orderId = fixture.awaitingPaymentAndCommit(deadline);
        UUID eventId = UUID.randomUUID();
        String transactionId = "CAPTURE-" + eventId;

        // Baseline: order mới, chưa thanh toán.
        OrderPaymentView before =
                queries.paymentOf(orderId).orElseThrow();
        assertThat(before.status())
                .isEqualTo(OrderPaymentStatus.AWAITING_PAYMENT);
        assertThat(before.paidAt()).isNull();

        scenario.publish(new PaymentCaptured(
                        eventId, orderId, transactionId))
                .andWaitAtMost(Duration.ofSeconds(8))
                .forStateChange(
                        () -> queries.paymentOf(orderId),
                        view -> view.filter(v ->
                                v.completedFor(eventId, transactionId))
                                .isPresent())
                .andVerify(view -> {
                    OrderPaymentView paid = view.orElseThrow();
                    assertThat(paid.orderId()).isEqualTo(orderId);
                    assertThat(paid.status())
                            .isEqualTo(OrderPaymentStatus.PAID);
                    assertThat(paid.capturedEventId())
                            .isEqualTo(eventId);
                    assertThat(paid.transactionId())
                            .isEqualTo(transactionId);
                    assertThat(paid.paidAt()).isNotNull();
                    assertThat(paid.deadline()).isEqualTo(deadline);
                });
    }
}
```

**Những giả định phải được hiện thực trong dự án:**

1. `FixedTimeTestConfiguration` được Spring chọn đúng `Clock` cho business service.
2. `OrderFixture` được đăng ký vào test context, sinh `orderId` mới và **commit** baseline trước khi trả về.
3. Listener `orders` thực sự xử lý `PaymentCaptured`, dùng `Clock` được inject để quyết định deadline, cập nhật state trong transaction phù hợp.
4. `OrderQueries` trả DTO từ dữ liệu đã commit mà supplier có thể đọc mới mỗi lượt chờ.
5. `Scenario.publish(...)` phải đáp ứng ngữ nghĩa listener của ứng dụng; nếu listener yêu cầu pha `AFTER_COMMIT`, cần bảo đảm event được publish trong transaction **thật sự commit**.
6. `Duration.ofSeconds(8)` là giá trị minh họa, không phải SLA hay khuyến nghị cố định.

**Điểm cô lập quan trọng:** thời gian nghiệp vụ cố định, nhưng `orderId`/`eventId` mới theo scenario. Test không cần giả định clock làm ID unique và không phụ thuộc vào một order cũ. Predicate đợi đúng state **của đúng logical event**, không phải bất kỳ đơn hàng nào đã `PAID`.

### 10.1. Test hết hạn nên thay gì?

Không nên “đợi 15 phút thực” để test đường quá hạn. Có thể viết unit test chính sách với `Clock.fixed(deadline.plusNanos(1))`, hoặc một module test riêng có cấu hình clock/fixture thích hợp.

Khi dùng clock test mutable để đổi giờ giữa baseline và stimulus:

- Chỉ đổi giờ **trước khi** phát stimulus cần kiểm tra.
- Tránh để một handler từ scenario khác còn chạy và đọc giờ mới.
- Reset/tách clock đúng scope.
- Không dùng clock nghiệp vụ để đo timeout chờ test.

Nếu listener có nhiều state/outcome như `PAID` hoặc `EXPIRED`, assertion cần chờ terminal state phù hợp, rồi xác minh business invariant. Không chỉ đợi `Optional.isPresent()` vì order đã tồn tại từ baseline.

## 11. Random/ID trong module test và kiến trúc Modulith

Một module nên công bố **hợp đồng cần thiết**, không để test của module khác import chi tiết triển khai.

Ví dụ, module `orders` có thể định nghĩa `OrderQueries` ở public API; repository, entity, clock-aware policy và ID generator implementation nằm trong `orders.internal`. Module `payments` công bố event contract qua named interface:

```java
// File: com/example/shop/payments/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.payments.events;
```

Module `orders` giới hạn dependency:

```java
// File: com/example/shop/orders/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "payments::events")
package com.example.shop.orders;
```

Tên module và named interface trong ví dụ phải khớp cấu trúc dự án thật. Việc inject `Clock`, `RandomGenerator` hoặc một ID factory **không được dùng làm lý do để import repository `internal` của module khác**. Với module tests:

- Unit/domain tests có thể cấp clock/generator trực tiếp vào constructor.
- Module test có thể dùng `@TestConfiguration` hoặc bean override hợp lệ.
- Integration test xuyên module cần setup qua public command API hoặc test infrastructure ở phạm vi phù hợp.
- Assertion consumer-visible nên đọc state qua public query API của module sở hữu.

Cấu trúc vẫn phải được kiểm chứng độc lập:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureVerificationTests {

    @Test
    void boundariesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ShopApplication` là Spring Boot application class minh họa. `verify()` có thể phát hiện phụ thuộc trái quy tắc giữa module; nó không phát hiện mọi lỗi clock, random hoặc collision ID. Vì vậy, cần **architecture tests + behavioral tests**, không thay một loại bằng loại kia.

## 12. Transaction và đồng hồ: đừng nhầm các mốc thời gian

Trong event-driven module, có nhiều thời điểm có thể ghi nhận:

| Mốc | Ý nghĩa | Cách kiểm chứng |
| --- | --- | --- |
| `event.occurredAt` | Thời điểm nghiệp vụ producer tạo event | Assert payload producer bằng clock/hợp đồng của producer |
| `order.paidAt` | Thời điểm order được xác nhận đã thanh toán | Assert consumer sau transaction commit |
| `publicationDate` | Thời điểm registry ghi nhận event publication | Kiểm tra theo provider/clock thực tế, không mặc định bằng event time |
| `transaction commit time` | Thời điểm DB ghi thay đổi có hiệu lực | Có thể khác `paidAt` và timestamp sự kiện |
| `consumer receivedAt` | Thời điểm message/listener nhận | Phụ thuộc scheduling, broker và retry |
| `read observedAt` | Lúc test đọc được state mới | Có thể muộn hơn commit do cache/replica |

**Không khẳng định tất cả timestamp phải bằng nhau.** Nếu nghiệp vụ lấy `paidAt` từ `Clock` khi handler chạy, nó khác event time khi có xử lý trễ; nếu nghiệp vụ cố ý dùng `event.occurredAt` thì kết quả khác. Test cần quyết định **mốc nào có ý nghĩa nghiệp vụ** rồi kiểm tra mốc đó.

### 12.1. `@CreatedDate`, JPA auditing và DB timestamp

Một bẫy là giả định thay bean `Clock` trong test sẽ tự động điều khiển mọi timestamp được ghi:

- Spring Data JPA auditing qua `@CreatedDate` có thể dùng `DateTimeProvider` của auditing infrastructure, **không nhất thiết** lấy bean `Clock` bạn inject vào service.
- Entity annotation/provider có thể dùng JVM clock của persistence provider.
- Default cột SQL như `CURRENT_TIMESTAMP` dùng đồng hồ/database semantics.
- Trigger, DB-side logic hoặc message broker tạo timestamp theo nguồn riêng.

Vì vậy, nếu test assert chính xác `createdAt == FIXED_INSTANT`, hãy xác minh nguồn giá trị thật và cấu hình nó qua cơ chế phù hợp. Với auditing, có thể cung cấp `DateTimeProvider` dùng clock mong muốn theo cấu hình Spring Data được dự án hỗ trợ; với SQL timestamp sinh từ DB, có thể assert khoảng thời gian hợp lý hoặc dùng database/test infrastructure cho phép kiểm soát timestamp.

Đừng sửa production code chỉ để mọi timestamp “trông giống” nhau nếu chúng đại diện những thời điểm khác nhau.

### 12.2. Precision và so sánh timestamp

Database có thể cắt/tròn nanosecond thành microsecond hoặc millisecond. Khi API đọc ra `Instant`, việc assert equality nanosecond tuyệt đối có thể fail dù hệ thống đúng theo độ chính xác đã cam kết.

Cần xác định:

1. Độ chính xác storage (DB driver, column type, serializer).
2. Hợp đồng API (giữ nguyên instant hay làm tròn).
3. Quy tắc so sánh (exact, truncated hoặc tolerance được định nghĩa).
4. Thứ tự nghiệp vụ phải đúng (ví dụ `paidAt <= deadline`), chứ không chỉ “gần hiện tại”.

Không dùng một tolerance quá rộng để che bug sai timezone hoặc sai deadline.

## 13. Async executor và broker: correlation ID phải đi cùng message

Khi event được xử lý trên worker thread hoặc externalized qua Kafka/RabbitMQ, mọi giả định gắn với thread phát event đều có thể không còn đúng.

Ví dụ:

```text
Test thread:
  orderId = O1
  eventId = E1
  clock = fixed T1
  publish PaymentCaptured(E1, O1)

Executor / broker:
  listener xử lý sau khi test thread đã trả về
  transaction DB commit riêng
  retry có thể mang lại E1 lần nữa

Test assertion:
  đọc order O1
  kiểm tra capturedEventId == E1
  kiểm tra state và invariant
```

Không dựa vào một biến `ThreadLocal` trong test để listener biết event ID. Nếu cần correlation, hãy truyền qua **event payload hoặc message headers**; khi dùng tracing, đảm bảo context propagation theo cấu hình. Giờ nghiệp vụ của listener nên đến từ dependency rõ ràng hoặc timestamp/hợp đồng event, không dựa vào timezone/clock không kiểm soát.

### 13.1. Dừng chờ theo state khác với chờ tất cả side effect xong

Một `Scenario.andWaitForStateChange(...)` có thể dừng khi order trở thành `PAID`, trong khi listener vẫn cần ghi audit, publish event downstream hoặc đánh dấu publication completed. Nếu cleanup ngay lúc đó, message cũ có thể tác động đến test khác.

Khi test cần **khẳng định không có side effect trùng**, phải chờ một tín hiệu xử lý/replay hoàn tất phù hợp trước assertion âm. Không dùng `PAID` sẵn có làm bằng chứng lần retry đã xong.

### 13.2. Clock cố định không làm cho Kafka offsets hoặc RabbitMQ ack cố định

Broker có state riêng: Kafka topic, consumer group/offset; RabbitMQ queue, binding, ack/nack và DLQ. Inject `Clock.fixed` vào domain không tự reset các tài nguyên đó. Tương tự, seed random cố định không ngăn message của test khác chảy vào một queue dùng chung.

Dùng event ID và namespace/topic/group/queue phù hợp, Testcontainers khi cần broker thật, và cleanup sau khi worker đã quiescent. Đây là các chiều isolation **độc lập** với clock và generator.

## 14. Những anti-pattern thường gặp

### 14.1. Một ID sinh từ frozen timestamp

```java
String id = "ORDER-" + clock.instant().toEpochMilli();
```

Nếu clock cố định, mọi lần gọi sinh cùng ID. Ngay cả với clock thật, hai lần gọi trong cùng mili-giây vẫn có thể trùng. Giải pháp: dùng ID generator có hợp đồng uniqueness phù hợp; giữ timestamp như metadata thay vì thay thế identity.

### 14.2. Một RNG static cho toàn bộ suite

```java
static final Random RANDOM = new Random(42L);
```

Chuỗi random sẽ phụ thuộc test nào gọi trước; chạy song song càng khó đoán. Tạo generator mới theo test/scenario hoặc seed độc lập theo case.

### 14.3. Assert bằng giờ hiện tại thay vì business contract

```java
assertThat(saved.getCreatedAt())
        .isEqualTo(Instant.now());
```

Lời gọi thứ hai gần như luôn khác lời gọi mà writer đã dùng; precision, thread scheduling và DB timestamp làm test flaky. Nếu cần kiểm tra thời điểm nghiệp vụ chính xác, inject clock và đọc đúng nguồn; nếu là timestamp infrastructure, định nghĩa khoảng/tolerance có căn cứ hoặc kiểm tra nguồn DB theo hợp đồng.

### 14.4. Dùng ID cố định chung để dễ đọc

```java
static final UUID ORDER_ID =
        UUID.fromString("00000000-0000-0000-0000-000000000001");
```

Giá trị cố định chỉ an toàn khi test có **môi trường dữ liệu độc lập** hoặc cleanup chắc chắn, không được nhiều scenario đồng thời tái sử dụng trên cùng DB. Trong integration tests dùng chung schema, tạo UUID mới theo scenario rồi giữ biến local đến cuối test.

### 14.5. Generator trả một ID giống nhau vô hạn

```java
OrderIdGenerator ids = () -> knownId;
```

Nếu use case tạo hai order mà test double luôn trả cùng ID, test có thể fail vì unique constraint thay vì logic nghiệp vụ. Dùng sequence generator với số ID dự kiến và cho fail rõ khi hết ID; với test concurrency, dùng factory thread-safe.

### 14.6. Polling làm thay đổi state

```java
// Anti-pattern: mỗi lần poll lại phát event hoặc tiến clock.
() -> {
    adjustableClock.advanceTo(nextInstant);
    publisher.publishEvent(event);
    return queries.paymentOf(orderId);
}
```

Supplier của `Scenario` có thể được gọi nhiều lần. Side effect trong supplier khiến một test tự phát nhiều event, lặp business logic và che nguyên nhân lỗi. Hãy kích hoạt stimulus **một lần**, rồi chỉ đọc state trong supplier.

### 14.7. Dùng seed cố định cho mã bảo mật

Không dùng `new SecureRandom(fixedSeed)` hoặc một PRNG dự đoán được để tạo token/khóa production cho dễ test. Nếu cần test mã hóa/authentication, dùng test vectors/fixture tách khỏi cơ chế sinh bí mật production; tạo khóa và token thật bằng CSPRNG thích hợp.

## 15. Test isolation khi chạy song song

Một suite có thể chạy tuần tự tốt nhưng fail ngẫu nhiên ở CI parallel vì:

- Hai test mutate cùng singleton `AdjustableClock`.
- Nhiều test đọc chung một `RandomGenerator` mutable, làm thay đổi thứ tự giá trị.
- Những test với frozen time tạo cùng ID dựa trên timestamp.
- Test A đã seed một record với ID/transaction key mà B dùng lại.
- Consumer broker thấy message từ scenario khác do dùng topic/group/queue chung.
- One-shot event listener/test gate của test cũ chưa kết thúc.

Một chiến lược đáng tin:

| Nguồn | Cô lập theo method | Cô lập theo class/suite | Khi phải chạy tuần tự |
| --- | --- | --- | --- |
| Business clock | Immutable fixed clock hoặc instance riêng | Dùng chung nếu không mutate | Mutable singleton không tách được |
| Random | Generator mới với seed ghi được | Dùng factory chung bất biến | RNG singleton shared mutable |
| Aggregate/event ID | ID local mới cho scenario | Namespace riêng cho environment | Cùng resource không tách được |
| DB | Fixture riêng và cleanup có kiểm soát | Schema/container theo suite | Global truncate/shared quota |
| Executor | Correlation ID, completion signal | Pool phù hợp và lifecycle rõ | Blocking failure injection |
| Broker/registry | Event ID và listener target | Topic/queue/schema riêng | Resubmission quét registry chung |

`@DirtiesContext` có thể làm mới context bị mutate nhưng **không tự reset database hoặc broker ngoài context**, và không bảo đảm async worker đã kết thúc. Hãy chọn mức cô lập theo tài nguyên, đừng dùng reset toàn context như công cụ chữa mọi lỗi.

## 16. Cách kiểm thử tính tái hiện trong CI

Một quy trình CI hợp lý cho `SPRING_MODULITH_VERIFICATION_TESTING`:

1. **Unit tests cho thời gian:** boundary trước/bằng/sau deadline, vùng giờ, precision.
2. **Unit tests cho RNG/ID:** cùng seed → cùng chuỗi input; ID generator không trả trùng trong phạm vi yêu cầu; failure khi hết ID test.
3. **`@ApplicationModuleTest`:** clock cố định, ID riêng, fixture commit, `Scenario` chờ state và invariant qua public API.
4. **Failure tests:** retry/duplicate giữ cùng logical event ID; second attempt có completion signal trước khi assert side effect.
5. **DB/broker integration:** timestamp auditing/DB, serialization, transaction visibility và consumer correlation dưới môi trường phù hợp.
6. **Architecture gate:** `ApplicationModules.of(...).verify()` kiểm tra quan hệ phụ thuộc/named interfaces.
7. **Isolation gate:** chạy test riêng, full suite và parallel với nhóm đủ điều kiện; thu lại seed, event ID, order ID và fixed instant khi fail.
8. **Reporting:** timeout, state sai, dependency sai hoặc ID collision phải làm CI fail; không che flaky bằng retry mù quáng.

Với dự án Gradle đã cấu hình JUnit tests trong task `test`:

```bash
./gradlew test
```

Nếu integration tests/clock-sensitive scheduler tests nằm ở task riêng, pipeline phải chạy thêm các task tương ứng. Không giả định `test` đã bao gồm mọi test tích hợp.

### 16.1. Checklist review

- [ ] Business code dùng clock được inject, không rải `Instant.now()` khó kiểm soát?
- [ ] Timezone và precision được xác định rõ theo nghiệp vụ?
- [ ] Test clock cố định có tránh mutable singleton khi chạy parallel?
- [ ] Timeout/polling dùng một nguồn thời gian vẫn tiến triển thật?
- [ ] Random generator được tạo theo scenario, seed được ghi khi fail?
- [ ] Không dùng deterministic seed để tạo bí mật production?
- [ ] Aggregate ID và event ID được phân biệt, không lấy trực tiếp từ timestamp?
- [ ] Retry của cùng logical event giữ nguyên event ID/idempotency key?
- [ ] Test không dùng ID cố định chung trên DB/broker chưa cô lập?
- [ ] Fixture commit trước async listener và assertion có baseline?
- [ ] Query API đọc đúng snapshot/ID, không phụ thuộc repository nội bộ?
- [ ] JPA auditing và DB timestamp có được xem xét nguồn thời gian riêng?
- [ ] CI chạy kiến trúc module cùng test hành vi?

## 17. Bài thực hành

**Bài A — deadline:** viết `PaymentWindowPolicy` nhận `Clock` và ba unit tests tại `deadline - 1ns`, `deadline`, `deadline + 1ns`. Giải thích quy tắc `<=` hoặc `<` theo hợp đồng thực.

**Bài B — timezone:** cố định một `Instant` gần nửa đêm UTC, chuyển sang hai `ZoneId` khác nhau và xác minh `LocalDate` có thể khác nhau. Thảo luận nguy cơ dùng timezone mặc định của máy CI.

**Bài C — clock mutable:** đăng ký `AdjustableClock` trong một test context, viết hai test thay đổi thời gian. Chứng minh khả năng nhiễm chéo khi reuse context; sửa bằng instance/cấu hình độc lập hoặc reset có điểm đồng bộ.

**Bài D — scheduler:** tạo expiry use case với clock giả; chứng minh việc tăng `AdjustableClock` không tự buộc `@Scheduled` trigger chạy. Tách unit test chính sách expiration và integration test lịch trình.

**Bài E — random seed:** tạo generator cục bộ với seed cố định, sinh nhiều quantity rồi kiểm tra invariant reservation. Ghi seed khi fail, bổ sung regression case từ input gây lỗi.

**Bài F — shared RNG:** cho hai test dùng chung `static Random(42)` và chạy ngược thứ tự; so sánh chuỗi nhận được. Chuyển sang generator per-test để loại bỏ sự phụ thuộc.

**Bài G — timestamp-based IDs:** tạo hai ID bằng epoch millis dưới `Clock.fixed`, quan sát collision. Sửa bằng UUID hoặc ID generator có chính sách uniqueness; giữ timestamp làm metadata.

**Bài H — duplicate event:** publish cùng `eventId` và `transactionId` hai lần trong một scenario; chờ lần xử lý lại hoàn tất rồi kiểm tra không tạo receipt/ledger entry thứ hai.

**Bài I — database auditing:** dùng một entity có `@CreatedDate` hoặc SQL `CURRENT_TIMESTAMP`, so sánh timestamp được lưu với `Clock.fixed` của service. Xác định nguồn timestamp thật và viết assertion đúng precision.

**Bài J — module boundary:** tạo test `@ApplicationModuleTest` dùng clock cố định, ID riêng và `Scenario`; xác minh `ApplicationModules.verify()`. Thử một import `orders.internal` trái ranh giới từ module khác trong nhánh học tập, chạy architecture gate và hoàn nguyên.

**Tiêu chí đạt:** mọi test có thời điểm nghiệp vụ xác định, random input tái hiện được, identifier/correlation không nhiễm giữa scenarios, predicate chờ đúng state của đúng event, và CI bảo vệ cả module boundary lẫn hành vi.

## 18. Ghi nhớ và tài liệu tham khảo

**Clock quyết định “khi nào”; random tạo đầu vào biến thiên; identifier quyết định “đối tượng và lần xử lý nào”.** Muốn kiểm thử Spring Modulith ổn định, phải điều khiển ba yếu tố theo *đúng scope*: freeze business clock, seed generator cục bộ nếu cần, tạo business/event ID riêng từng scenario và giữ nguyên ID khi replay một logical event.

Không dùng frozen clock để đo timeout, không dùng timestamp làm unique ID, không dùng seed bí mật trong production, không để test mutate một clock/RNG singleton dùng chung và không suy ra JPA/DB clock bị điều khiển chỉ vì đã thay `Clock` bean. Kết hợp `@ApplicationModuleTest`, `Scenario`, public query API và `ApplicationModules.verify()` sẽ kiểm chứng được hành vi cùng ranh giới kiến trúc; quality gate CI bảo vệ tính tái hiện khi chạy cả suite.

Tài liệu tham khảo:

- [Java SE 21 — Clock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html): `systemUTC`, `fixed`, `offset`, `withZone`.
- [Java SE 21 — RandomGenerator](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/random/RandomGenerator.html): interface PRNG và các thuật toán.
- [Java SE 21 — SplittableRandom](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SplittableRandom.html): PRNG có seed phù hợp cho test cục bộ.
- [Java SE 21 — UUID](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/UUID.html): kiểu định danh và cách sinh UUID.
- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `Scenario` và state change.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và module boundary.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event publication, listener và Event Publication Registry.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và commit.
- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html): auditing timestamps và date-time provider.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): vòng đời và khả năng tái sử dụng test context.
