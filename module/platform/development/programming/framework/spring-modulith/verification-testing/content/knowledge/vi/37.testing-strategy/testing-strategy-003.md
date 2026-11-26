# Chọn @ApplicationModuleTest cho một module

Khi một pull request thay đổi quy tắc giữ chỗ của module `booking`, đội phát triển cần biết: **“Với cùng một yêu cầu, module này chấp nhận hay từ chối chính xác, phát đúng sự kiện và cập nhật trạng thái nội bộ hay không?”** Dùng `@SpringBootTest` để nạp toàn ứng dụng có thể làm phép kiểm tra tốn thời gian, phụ thuộc nhiều hạ tầng và khó xác định module nào gây lỗi. Ngược lại, một unit test thuần Java có thể không phát hiện bean của module không được Spring tạo hoặc listener nội bộ chưa được đăng ký.

**`@ApplicationModuleTest` là lựa chọn dành cho khoảng giữa đó:** khởi tạo một **Spring test context theo ranh giới application module**, sau đó dùng JUnit để kiểm chứng hành vi và wiring của module được chọn. Lựa chọn này chỉ phù hợp khi **đối tượng cần bảo vệ thực sự là một module**, không phải mọi module tiêu thụ event hay toàn bộ giao dịch liên module.

Bài thuộc chương **Chọn chiến lược** trong **SPRING_MODULITH_VERIFICATION_TESTING**. Chúng ta sẽ thiết kế một ví dụ Java/JUnit có thể kiểm tra kết quả, event, state, trường hợp âm và scope; giải thích `STANDALONE`, test double, `DIRECT_DEPENDENCIES`, điều kiện dùng database và giới hạn so với `ApplicationModules.verify()`. Mục tiêu là chọn đúng công cụ theo **bằng chứng cần có**, không chỉ biết cách thêm annotation.

> **Quy tắc:** Chọn `@ApplicationModuleTest` khi muốn kiểm chứng **bean và hành vi chạy bên trong một application module**, có lợi từ Spring DI/event/transaction hỗ trợ, nhưng **chưa cần toàn bộ ứng dụng**. Với invariant “module A không được import nội bộ module B”, giữ một bài `ApplicationModules.verify()` riêng. Với yêu cầu “consumer ngoài module đã hoàn tất”, dùng integration scope chứa consumer.

## 1. Điều kiện chọn `@ApplicationModuleTest` thay vì unit hoặc full integration

Phát biểu mục tiêu dưới dạng một *claim* có thể kiểm tra:

| Claim | Phạm vi hợp lý | Tại sao |
| --- | --- | --- |
| `BookingService` trả kết quả đúng khi ghế còn hoặc đã bị giữ | Unit JUnit **hoặc** module test | Nếu chỉ logic thuần, unit rẻ hơn; nếu cần bean/event, chọn module test |
| Các bean nội bộ `booking` được Spring inject đầy đủ | **`@ApplicationModuleTest`** | Cần context thực trong phạm vi module |
| `booking` phát một `SeatReserved` với ID của stimulus | **`@ApplicationModuleTest` + event recorder** | Kiểm tra event được publish qua Spring |
| Một listener **nằm trong booking** phản ứng đúng event | **`@ApplicationModuleTest`** nếu listener và dependency được nạp | Listener cùng module nằm trong phạm vi kiểm thử |
| Listener của module `notifications` gửi email | **Integration test có notifications**, không chỉ booking standalone | Consumer không tự thuộc module được bootstrap |
| `booking` không tham chiếu kiểu thuộc `payments.internal` | **`ApplicationModules.verify()`** | Kiểm tra dependency graph thay vì runtime path |
| Reservation commit xuống database của booking | Module test **có DB** nếu repo/config của booking được nạp | Ranh giới một module vẫn có thể chứa persistence |
| Request HTTP tạo booking và gửi email hoàn tất | `@SpringBootTest` + hạ tầng phù hợp | Nhiều module/tầng và external side effects |
| Độ trễ p95 production đáp ứng SLO | Metrics/performance test riêng | Một JUnit module test không đại diện traffic production |

Không đánh đồng “một module” với “một bean”: module có thể gồm API, service, listener, repository và các package nội bộ. `@ApplicationModuleTest` giúp kiểm tra **tập bean thuộc module**, trong khi những application module không thuộc bootstrap scope thường không được nạp.

### Câu hỏi quyết định ngắn

1. **Assertion có cần Spring container hoặc event publisher thật?** Nếu không, pure JUnit có thể đủ.
2. **Claim chỉ liên quan module sở hữu behavior?** Nếu có, `STANDALONE` là điểm bắt đầu tốt.
3. **Service phụ thuộc bean do module khác cung cấp?** Cân nhắc test double hoặc mở đến `DIRECT_DEPENDENCIES` theo mục tiêu.
4. **Side effect nằm ở module nhận khác?** Tạo integration test cho toàn luồng; không kết luận từ test publisher.
5. **Claim thuộc kiến trúc tĩnh?** Viết `verify()`; không dùng context test làm oracle.

## 2. Hiểu chính xác “một module” và `BootstrapMode`

Giả sử lớp ứng dụng ở `com.example.ticket.TicketApplication`, module `booking` là package con trực tiếp `com.example.ticket.booking`. Một test nằm trong package đó có thể xác định **module đang kiểm thử** qua cấu trúc test.

```java
package com.example.ticket.booking;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
class BookingSmokeTest {

    @Test
    void contextLoads() {
        // Hữu ích để phát hiện lỗi bootstrap,
        // nhưng chưa chứng minh business rule.
    }
}
```

**Giá trị:** nếu Spring không khởi tạo được bean cần thiết trong phạm vi test, test context có thể FAIL trước method. **Giới hạn:** một method rỗng không chứng minh quy tắc giữ chỗ, event hoặc trạng thái.

### Ba chế độ chọn phạm vi

| Mode | Application modules được bootstrap | Khi nào dùng |
| --- | --- | --- |
| `STANDALONE` (mặc định thường dùng) | Module đang kiểm thử, không tự thêm implementation của các module phụ thuộc | Muốn kiểm tra behavior/wiring nội bộ và cô lập dependency ngoài |
| `DIRECT_DEPENDENCIES` | Module đang kiểm thử **và những module nó phụ thuộc trực tiếp** | Muốn kiểm tra tích hợp gần với dependency thật |
| `ALL_DEPENDENCIES` | Module đang kiểm thử và **các module phụ thuộc bắc cầu** | Muốn kiểm tra chuỗi dependency sâu có chủ đích |

`ALL_DEPENDENCIES` **không có nghĩa toàn bộ ứng dụng**. Module tiêu thụ event của booking không nhất thiết nằm trong dependency graph mà booking phụ thuộc; nạp tất cả *dependency* không tự nạp mọi *dependent/consumer*.

`STANDALONE` không nhất thiết là “JVM chỉ có bean trong một package”: Spring Boot auto-configuration, test configurations và các component hạ tầng được phép vẫn có thể tạo bean ngoài ứng dụng module. Cách hiểu đúng là **thu hẹp phạm vi application modules**, không tắt mọi cơ chế Spring.

### Đừng mở mode chỉ để xóa một lỗi thiếu bean

Nếu test standalone thiếu một collaborator bên ngoài, trước hết xác định: ta muốn **cô lập module** hay **kiểm tra integration với dependency**?

- Cô lập: cung cấp test double theo **interface/contract** ở biên, hoặc dùng cơ chế mock bean phù hợp phiên bản.
- Integration: chọn `DIRECT_DEPENDENCIES` và chạy bean thực của dependency.
- Không biết contract là gì: xem lại thiết kế module và dependency graph trước khi cố nạp nhiều bean.

Đổi mode là một quyết định **về phạm vi bằng chứng**, không phải thủ thuật làm test xanh.

## 3. Ví dụ Java: module `booking` tự khép kín và quan sát được

Ta dùng một module giữ ghế; không có database hay listener ngoài module trong baseline, để việc PASS/FAIL phản ánh rõ **hành vi của booking**.

```text
com.example.ticket
├── TicketApplication.java
├── booking/
│   ├── BookingService.java
│   ├── BookingDecision.java
│   ├── BookingQueries.java
│   ├── SeatReserved.java
│   └── internal/
│       └── SeatInventory.java
└── notifications/
    └── ...                         ← module consumer tùy chọn, không bootstrap
                                     trong booking STANDALONE
```

`TicketApplication` là Spring Boot root class:

```java
// src/main/java/com/example/ticket/TicketApplication.java
package com.example.ticket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TicketApplication {

    public static void main(String[] args) {
        SpringApplication.run(TicketApplication.class, args);
    }
}
```

### 3.1. Hợp đồng kết quả

```java
// booking/BookingDecision.java
package com.example.ticket.booking;

import java.util.Optional;
import java.util.UUID;

public record BookingDecision(
        String seatCode,
        Optional<UUID> reservationId
) {
    public boolean accepted() {
        return reservationId.isPresent();
    }
}
```

Trong ví dụ, một ghế đã bị giữ trả `Optional.empty()`. Đây là cách đơn giản để giữ kết quả có kiểu và tránh ID `null`; sản phẩm thực có thể cần enum lý do từ chối, policy hết hạn và reservation token.

### 3.2. Hợp đồng đọc trạng thái cho test

```java
// booking/BookingQueries.java
package com.example.ticket.booking;

import java.util.Optional;
import java.util.UUID;

public interface BookingQueries {
    Optional<UUID> findReservationId(String seatCode);
}
```

Đặt interface ở package gốc để test và consumer có thể quan sát trạng thái **qua API của module**, thay vì test buộc phải biết cấu trúc internal map.

### 3.3. Implementation state nội bộ

```java
// booking/internal/SeatInventory.java
package com.example.ticket.booking.internal;

import com.example.ticket.booking.BookingQueries;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class SeatInventory implements BookingQueries {

    private final ConcurrentMap<String, UUID> reservations =
            new ConcurrentHashMap<>();

    public Optional<UUID> reserveIfFree(String seatCode) {
        UUID candidate = UUID.randomUUID();
        UUID existing = reservations.putIfAbsent(
                seatCode, candidate
        );
        return existing == null
                ? Optional.of(candidate)
                : Optional.empty();
    }

    @Override
    public Optional<UUID> findReservationId(String seatCode) {
        return Optional.ofNullable(
                reservations.get(seatCode)
        );
    }
}
```

`putIfAbsent` cho phép **tối đa một reservation ID cho mỗi ghế trong một map ở một JVM**, kể cả nếu hai thread thử giữ cùng lúc. Đây **không phải transaction hoặc idempotency bền vững** qua nhiều instance. Nó chỉ tạo baseline không cần database để tập trung vào module test.

`SeatInventory` là `public` theo Java vì `BookingService` ở subpackage khác trong cùng module cần truy cập; nhưng nó nằm dưới `booking.internal` và không nên được các **application module khác** tham chiếu. Java visibility và Spring Modulith module visibility là hai tầng khác nhau.

### 3.4. Event cùng module

```java
// booking/SeatReserved.java
package com.example.ticket.booking;

import java.util.Objects;
import java.util.UUID;

public record SeatReserved(
        UUID reservationId,
        UUID correlationId,
        String seatCode
) {
    public SeatReserved {
        Objects.requireNonNull(reservationId);
        Objects.requireNonNull(correlationId);
        Objects.requireNonNull(seatCode);
    }
}
```

`correlationId` được tạo từ stimulus test và đi theo event; không suy luận nó là cùng một ID với `reservationId`.

### 3.5. Use case có state và event

```java
// booking/BookingService.java
package com.example.ticket.booking;

import com.example.ticket.booking.internal.SeatInventory;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class BookingService {

    private final SeatInventory inventory;
    private final ApplicationEventPublisher events;

    public BookingService(
            SeatInventory inventory,
            ApplicationEventPublisher events) {
        this.inventory = inventory;
        this.events = events;
    }

    public BookingDecision reserve(
            UUID correlationId,
            String seatCode) {

        Objects.requireNonNull(correlationId, "correlationId");

        if (seatCode == null || seatCode.isBlank()) {
            throw new IllegalArgumentException(
                    "Seat code is required"
            );
        }

        Optional<UUID> id =
                inventory.reserveIfFree(seatCode);

        id.ifPresent(reservationId ->
                events.publishEvent(new SeatReserved(
                        reservationId,
                        correlationId,
                        seatCode
                ))
        );

        return new BookingDecision(seatCode, id);
    }
}
```

**Hành vi hợp đồng trong ví dụ:** giữ ghế lần đầu thành công và phát **một** `SeatReserved`; giữ lại cùng ghế từ yêu cầu khác bị từ chối và **không phát event thành công**; dữ liệu đầu vào sai bị từ chối trước khi tác động state.

**Giới hạn có chủ đích:** code không có persistence, transaction, gửi email hay publication registry. Chỉ nên dùng test này để chứng minh behavior **trong Spring context một module**. Muốn chuyển sang đặt vé bền vững cần database, transaction, concurrency/retry semantics và test tích hợp bổ sung.

## 4. Test chính: `@ApplicationModuleTest(STANDALONE)` + assertion nghiệp vụ

Đặt JUnit test ngay trong package `com.example.ticket.booking`. Đây là điểm quan trọng: test thuộc **module booking** nên bootstrap mode có thể chọn đúng module đó.

```java
// src/test/java/com/example/ticket/booking/BookingModuleTest.java
package com.example.ticket.booking;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest(mode = BootstrapMode.STANDALONE)
@RecordApplicationEvents
class BookingModuleTest {

    @Autowired
    BookingService booking;

    @Autowired
    BookingQueries queries;

    @Autowired
    ApplicationEvents events;

    @Test
    void firstReservationUpdatesStateAndPublishesOneEvent() {
        String seat = "A-" + UUID.randomUUID();
        UUID correlationId = UUID.randomUUID();

        BookingDecision result =
                booking.reserve(correlationId, seat);

        assertThat(result.accepted()).isTrue();
        assertThat(result.reservationId()).isPresent();
        assertThat(queries.findReservationId(seat))
                .isEqualTo(result.reservationId());

        var matches = events.stream(SeatReserved.class)
                .filter(event ->
                        correlationId.equals(event.correlationId()))
                .toList();

        assertThat(matches).hasSize(1);
        assertThat(matches.get(0).seatCode()).isEqualTo(seat);
        assertThat(matches.get(0).reservationId())
                .isEqualTo(result.reservationId().orElseThrow());
    }

    @Test
    void sameSeatCannotBeReservedTwice() {
        String seat = "B-" + UUID.randomUUID();
        UUID firstId = UUID.randomUUID();
        UUID secondId = UUID.randomUUID();

        BookingDecision first =
                booking.reserve(firstId, seat);
        BookingDecision second =
                booking.reserve(secondId, seat);

        assertThat(first.accepted()).isTrue();
        assertThat(second.accepted()).isFalse();
        assertThat(second.reservationId()).isEmpty();

        assertThat(queries.findReservationId(seat))
                .isEqualTo(first.reservationId());

        assertThat(events.stream(SeatReserved.class)
                .filter(event ->
                        firstId.equals(event.correlationId()))
                .count()).isEqualTo(1L);

        assertThat(events.stream(SeatReserved.class)
                .filter(event ->
                        secondId.equals(event.correlationId()))
                .count()).isZero();
    }

    @Test
    void invalidSeatDoesNotPublishAnEvent() {
        UUID correlationId = UUID.randomUUID();

        assertThatThrownBy(() ->
                booking.reserve(correlationId, "   "))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(events.stream(SeatReserved.class)
                .filter(event ->
                        correlationId.equals(event.correlationId()))
                .count()).isZero();
    }
}
```

Đây là **kiểm thử hành vi và wiring của một application module**:

- Spring phải tạo được `BookingService`, `SeatInventory` và đưa `SeatInventory` vào `BookingQueries`.
- Việc giữ ghế đầu tiên phải có state và event phù hợp.
- Lần đặt trùng **không** tạo reservation ID mới hoặc event thành công thứ hai.
- Đầu vào không hợp lệ phải bị từ chối mà không phát event của stimulus.

### Vì sao correlation ID và seat code đều mới?

`@ApplicationModuleTest` dùng Spring Test context, có thể **cache context giữa các test**. `SeatInventory` là mutable singleton; nếu dùng hằng số `"A-10"` trong nhiều test, một test trước có thể đã giữ ghế, khiến test sau FAIL tùy thứ tự.

Sử dụng **seat code và correlation ID duy nhất** cho từng test giúp tách biệt stimulus. Với database thật, còn cần test fixture, cleanup hoặc transaction strategy phù hợp; UUID không tự thay thế isolation database ở mọi trường hợp.

### Những kết luận không được rút ra

Bài test **không** chứng minh module `notifications` đã nhận event, một bảng SQL đã commit, hoặc event được lưu bền vững. `@RecordApplicationEvents` chỉ thu thập event được publish trong **Spring Test ApplicationContext**, không phải Event Publication Registry.

Nó cũng **không thay thế** `ApplicationModules.verify()` cho mọi dependency trong codebase. Một class khác có import trái phép vào module ngoài vẫn có thể không ảnh hưởng đến các kịch bản ở đây.

## 5. Phép thử âm để biết `@ApplicationModuleTest` bảo vệ điều gì

Một test chỉ PASS ở baseline chưa chắc mạnh. Thử thay đổi có kiểm soát trên nhánh thực hành, sau đó **hoàn nguyên**:

| Mutation | Kỳ vọng | Test nào bắt? |
| --- | --- | --- |
| Bỏ `events.publishEvent(...)` | State có thể đúng, nhưng contract event bị phá | `firstReservationUpdatesStateAndPublishesOneEvent` FAIL |
| Thay `ifPresent` bằng publish ngay cả khi ghế đã giữ | Duplicate attempt phát event không đúng | `sameSeatCannotBeReservedTwice` FAIL |
| Bỏ check `seatCode.isBlank()` | Dữ liệu trống có thể bị ghi state | `invalidSeatDoesNotPublishAnEvent` FAIL theo exception |
| Mỗi lần gọi đều tạo reservation ID mới | Duplicate seat bị giữ nhiều lần | `sameSeatCannotBeReservedTwice` FAIL |
| Phát event với `UUID.randomUUID()` thay correlation ID đầu vào | Event không còn nối đúng stimulus | Các test lọc theo correlation ID FAIL |
| Chỉ đổi text `LOG.info(...)` | Contract behavior giữ nguyên | Các test trên **vẫn nên PASS** |
| Một class trong booking dùng internal API của module khác | Architecture boundary bị phá | `verify()` phải FAIL, module behavior có thể PASS |
| Consumer ngoài booking không gửi thông báo | Hành vi liên module bị lỗi | Cần integration test; standalone test **không kết luận** |

**Phép thử âm phải nhắm vào assertion cụ thể.** Nếu bỏ event mà test vẫn PASS, có thể test đang chỉ assert state. Nếu tạo duplicate nhưng test vẫn PASS, có thể chưa có một case cùng seat hai lần. Đó là cách phát hiện **test xanh giả**.

### Khi assertion quá rộng

Ví dụ dưới đây yếu:

```java
assertThat(events.stream(SeatReserved.class).count())
        .isGreaterThan(0);
```

Nó có thể PASS vì một event từ test khác hoặc một stimulus khác trong cùng context. Phiên bản đúng hơn phải lọc **`correlationId` của chính stimulus** và xác minh `reservationId`/`seatCode` phù hợp. Với event async, còn cần chờ có timeout thay vì chỉ đọc recorder ngay lập tức.

## 6. Khi dùng `Scenario` thay cho đọc recorder ngay

Với behavior “**kích hoạt stimulus và chờ sự kiện phù hợp**”, Spring Modulith cung cấp `org.springframework.modulith.test.Scenario`. Mô tả dưới dạng DSL thường rõ hơn khi event không xuất hiện ngay trong cùng một luồng:

```java
// Trong @ApplicationModuleTest thuộc package booking.
// Các import: JUnit @Test, UUID, Scenario, AssertJ;
// field BookingService booking đã được @Autowired.
@Test
void scenarioObservesEventForThisReservation(Scenario scenario) {
    UUID correlationId = UUID.randomUUID();
    String seat = "C-" + UUID.randomUUID();

    scenario.stimulate(() ->
                booking.reserve(correlationId, seat))
            .andWaitForEventOfType(SeatReserved.class)
            .matching(event ->
                    correlationId.equals(event.correlationId()))
            .toArriveAndVerify(event -> {
                assertThat(event.seatCode()).isEqualTo(seat);
                assertThat(event.reservationId()).isNotNull();
            });
}
```

Test trích đoạn giả định đã có `booking` được inject và chạy cùng context booking, không phải một file Java đầy đủ khác. Tùy phiên bản Spring Modulith, tùy chọn timeout/giới hạn chờ của DSL có thể khác; sử dụng đúng API trong dependency đang dùng.

**Điều `Scenario` chứng minh:** event loại `SeatReserved` mang đúng correlation ID được quan sát sau stimulus và payload thỏa assertion. **Điều nó không chứng minh:** listener của module `notifications` đã gửi email, event publication trong registry đã completed hoặc transaction DB đã commit.

### Khi nào dùng cách nào?

| Mục tiêu | Cách chọn |
| --- | --- |
| Service phát event đồng bộ, muốn assert payload | `@RecordApplicationEvents` + `ApplicationEvents` thường đơn giản |
| Muốn mô tả stimulus → sự kiện và chờ điều kiện | `Scenario` giúp biểu đạt rõ |
| Muốn xác nhận listener **cùng module** cập nhật state | Chờ/query API state của module với timeout nếu async |
| Muốn xác nhận module **khác** xử lý event | Integration test có consumer được bootstrap |
| Muốn xác nhận transaction/database sau commit | Test database/transaction riêng, không chỉ chờ event type |

Đừng dùng `Thread.sleep(...)` cố định rồi giả định listener đã hoàn tất. Chờ **một trạng thái có thể quan sát** và giới hạn timeout hữu hạn.

## 7. Nếu module cần collaborator ở module khác: stub hay mở bootstrap?

Ví dụ booking hiện tại tự khép kín. Trong hệ thống thật, `BookingService` có thể cần một interface `SeatAvailability` do module `inventory` sở hữu.

Giả sử một biến thể thiết kế dùng contract:

```java
// inventory/SeatAvailability.java
package com.example.ticket.inventory;

public interface SeatAvailability {
    boolean mayReserve(String seatCode);
}
```

Và `booking` được phép phụ thuộc **API mặc định** của inventory:

```java
// booking/package-info.java — biến thể, không áp dụng cho baseline
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.ticket.booking;
```

**Đây là một biến thể của ứng dụng ở phần 3:** cần thay logic `SeatInventory` nội bộ bằng collaborator `SeatAvailability` trong `BookingService`. Không dán nguyên ví dụ này vào baseline mà chưa sửa constructor và logic. Nó minh họa tình huống có **dependency ngoài module** và quyết định scope tương ứng.

### Cách A — `STANDALONE` với test double qua contract

Khi claim là “booking áp dụng quy tắc của nó khi inventory trả kết quả X”, có thể cung cấp bean giả tại test:

```java
// Trích đoạn cấu hình trong BookingModuleTest của biến thể.
import com.example.ticket.inventory.SeatAvailability;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;

@Import(BookingModuleTest.InventoryStub.class)
@ApplicationModuleTest(mode = BootstrapMode.STANDALONE)
class BookingModuleTest {

    @TestConfiguration(proxyBeanMethods = false)
    static class InventoryStub {

        @Bean
        SeatAvailability seatAvailability() {
            return seat -> !"BLOCKED-1".equals(seat);
        }
    }

    // Các test gọi BookingService của biến thể.
}
```

`@TestConfiguration` và `@Import` đưa **test-only bean** vào context mà không cần bootstrap implementation của module inventory. Điều này giúp test module booking độc lập, nhưng **không chứng minh integration thực tế với inventory**.

Cần tránh có đồng thời nhiều bean cùng type không được phân biệt nếu một auto-configuration khác cũng tạo `SeatAvailability`; khi đó xử lý bằng qualification/test configuration đúng chứ không tùy tiện thay logic production.

### Cách B — `DIRECT_DEPENDENCIES` dùng bean thật

Khi mục tiêu là “booking thực sự phối hợp được với module inventory và wiring đúng”, chọn:

```java
package com.example.ticket.booking;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(
        mode = BootstrapMode.DIRECT_DEPENDENCIES
)
class BookingInventoryIntegrationTest {

    @Test
    void startsBookingAndInventoryModules() {
        // Gọi BookingService thật và kiểm tra kết quả
        // cùng contract SeatAvailability thật.
    }
}
```

Đây là **module integration test**, dù vẫn sử dụng `@ApplicationModuleTest`. Chỉ dùng khi inventory implementation, hạ tầng và test data có sẵn. Một method rỗng chỉ chứng minh bootstrap, không đủ cho behavior; trong bài test thực phải bổ sung assertion.

### Câu hỏi quyết định thực tế

| Nếu cần biết… | Chọn |
| --- | --- |
| Booking xử lý correctly khi inventory từ chối | `STANDALONE` + stub/mock ở contract |
| Inventory bean thật được inject và phối hợp đúng | `DIRECT_DEPENDENCIES` |
| Một chuỗi dependency bắc cầu sâu hoạt động | `ALL_DEPENDENCIES` khi scope hợp lý |
| Nhiều consumer không phải dependency của booking cùng chạy | `@SpringBootTest`/integration context chứa consumer |
| Booking có phụ thuộc trái luật vào inventory.internal không | `ApplicationModules.verify()` riêng |

## 8. Database và transaction vẫn có thể được kiểm tra trong *một* module

`@ApplicationModuleTest` **không có nghĩa “không được dùng database”**. Nếu module booking sở hữu repository/entity và claim là “đặt chỗ đã lưu vào DB”, vẫn có thể làm module test với hạ tầng persistence cần thiết.

Tuy nhiên, phải thay baseline `ConcurrentHashMap` bằng **repository và service transaction thực**. Ví dụ phác thảo một test cho biến thể JPA:

```java
// Phần thuộc một @ApplicationModuleTest của module booking
// sau khi đã triển khai booking repository + DB schema.
@Autowired
BookingService booking;

@Autowired
BookingQueries queries;

@Test
void reservationCanBeReadAfterServiceCommits() {
    UUID correlationId = UUID.randomUUID();
    String seat = "DB-" + UUID.randomUUID();

    BookingDecision result =
            booking.reserve(correlationId, seat);

    assertThat(result.accepted()).isTrue();
    assertThat(queries.findReservationId(seat))
            .isEqualTo(result.reservationId());
}
```

Trong **biến thể persistence**, `BookingService.reserve()` phải chạy qua **Spring transactional proxy**, cập nhật DB và commit trước lúc test xác nhận kết quả từ transaction khác/điều kiện đọc phù hợp. Bài test phải có datasource, migrations/schema, repository và profile test đúng. Đoạn trên **không tự chứng minh commit** nếu `BookingQueries` vẫn đọc từ in-memory map; cần thật sự chuyển implementation sang JPA/JDBC.

### Cạm bẫy `@Transactional` tại lớp test

Trong Spring Test, một test được gắn `@Transactional` thường chạy trong transaction do test quản lý và rollback khi kết thúc. Nếu listener cần chạy sau `AFTER_COMMIT`, việc test giữ transaction mở có thể khiến listener **chưa được gọi khi assertion chạy**.

Vì thế với test yêu cầu commit thật:

- Đừng gắn `@Transactional` vào test chỉ theo thói quen.
- Gọi service qua Spring proxy với ranh giới transaction rõ ràng.
- Nếu cần kiểm soát transaction test, dùng `TestTransaction` hoặc `TransactionTemplate` có chủ đích.
- Kiểm tra state sau commit, không chỉ việc event đã được recorder ghi lại.

### Khi nào một module test không còn đủ?

Nếu acceptance criterion là “`notifications` nhận `SeatReserved` và gửi email sau commit”, `@ApplicationModuleTest(STANDALONE)` của booking **không tự nạp notifications**. Cần integration test cho producer + consumer + hạ tầng tương ứng. `Scenario` chờ event của booking cũng **không bảo đảm** một listener ngoài module đã hoàn tất.

## 9. Chẩn đoán FAIL: thiếu bean, sai trạng thái hay sai phạm vi?

Khi một `@ApplicationModuleTest` FAIL, bước đầu tiên là xác định **FAIL xảy ra trước hay trong test method**:

| Triệu chứng | Khả năng | Việc cần làm |
| --- | --- | --- |
| Context không khởi tạo, `UnsatisfiedDependencyException` | Bean collaborator bị loại khỏi standalone scope | Dùng test double qua contract hoặc đổi mode theo mục tiêu |
| Có nhiều bean cùng interface | Test config chồng implementation thật | Xem qualifiers, config và bean scope |
| Service inject được nhưng kết quả sai | Business rule hoặc fixture sai | Assert input/expected và kiểm tra nhánh điều kiện |
| Event count = 0 | Publisher không phát, predicate sai hoặc ngoại lệ trước publish | Xem stimulus, correlation ID và event type |
| Test đầu PASS, test sau FAIL | State mutable và context cache/test order | Dùng dữ liệu unique hoặc cleanup có kiểm soát |
| `Scenario` chờ event mãi | Event không tới hoặc predicate không khớp | Kiểm tra publish/transaction; không tăng timeout tùy tiện |
| Consumer ngoài module không chạy | Không nằm trong bootstrap scope | Dùng integration test có consumer |
| DB test không thấy listener `AFTER_COMMIT` | Test transaction rollback hoặc chưa commit | Kiểm tra transaction boundary |
| `@SpringBootTest` PASS còn standalone FAIL | Full context có thêm dependency bị cô lập | Xác nhận lại phạm vi claim, không vội coi standalone lỗi |
| Module test PASS dù import internal module khác | Behavior test không thay luật kiến trúc | Chạy `ApplicationModules.verify()` |

### Tại sao chỉ “contextLoads” chưa đủ?

Nếu method không có assertion, kết quả PASS chủ yếu xác nhận **bean wiring và bootstrap** cho cấu hình được chọn. Điều đó hữu ích nhưng yếu hơn test thật: một lời gọi `reserve` phải trả đúng decision, cập nhật state và phát đúng event.

Không tăng `BootstrapMode` tới `ALL_DEPENDENCIES` chỉ để làm mất lỗi thiếu bean. Nó có thể kéo nhiều integration/hạ tầng vào test, chậm hơn và khó biết module nào sai.

### Điều cần ghi khi có timeout

Log theo `correlationId`, test class/mode, exception và mốc stimulus/event giúp điều tra. Nhưng **không lấy một chuỗi log làm assertion nghiệp vụ**; hãy giữ assertion trên result, event hoặc DB state. Nếu có thread dump/executor metrics, chúng là **diagnostics**, không thay thế test contract.

## 10. Đưa chiến lược một-module vào CI mà không tạo “xanh giả”

Một quality gate tốt cho Spring Modulith tách các bằng chứng:

| Gate | Nhiệm vụ | Phép kiểm tra chính |
| --- | --- | --- |
| **Architecture** | Ngăn dependency sai giữa modules | `ApplicationModules.of(...).verify()` |
| **Module behavior** | Bảo vệ logic và bean wiring của booking | `@ApplicationModuleTest` + assertions |
| **Event contract** | Bảo vệ `SeatReserved` đúng ID/payload | `ApplicationEvents` hoặc `Scenario` |
| **Persistence** | Bảo vệ transaction/schema nếu có | Module test + DB hoặc integration suite |
| **Cross-module integration** | Bảo vệ consumer ngoài booking | `@SpringBootTest`/integration |
| **Operational** | Chẩn đoán latency, retry, backlog | Logs/metrics/traces, không phải chỉ JUnit |

Với Gradle/JUnit 5:

```bash
./gradlew test
```

Với Maven/Surefire đã cấu hình:

```bash
mvn -B test
```

Không tự giả định một lệnh `test` bao phủ integration test đặt trong task `integrationTest` hoặc Maven Failsafe. Phải chạy **đúng suite được dự án định nghĩa**.

### Ví dụ GitHub Actions

```yaml
name: Modulith booking module verification

on:
  pull_request:

jobs:
  module-gate:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'

      - uses: gradle/actions/setup-gradle@v4

      - name: Architecture and module contract tests
        run: bash ./gradlew --no-daemon test

      # Bật khi project có task integrationTest và hạ tầng DB:
      # - name: Cross-module and database integration tests
      #   run: bash ./gradlew --no-daemon integrationTest

      - name: Save test reports on failure
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: modulith-module-test-reports
          path: |
            **/build/test-results/**/*.xml
            **/build/reports/tests/**
          if-no-files-found: warn
```

Đây là **workflow minh họa**, chưa chạy trong workspace được giao. Cần JDK/Spring Boot/Spring Modulith tương thích, Gradle wrapper, dependencies và test source set đúng. CI thực sự chặn merge chỉ khi repository yêu cầu job `module-gate` thành công qua ruleset/branch protection.

### Assertion nào quyết định PASS/FAIL?

**Đúng:** một `BookingModuleTest` thất bại khi event bị bỏ hoặc state sai, JUnit/Gradle trả mã lỗi, CI job FAIL.

**Sai:** chỉ grep `"Seat reserved"` hoặc `"BUILD SUCCESSFUL"` trong log. Một câu log không chứng minh contract đã đúng; giữ log/JUnit reports để chẩn đoán nguyên nhân sau khi assertion thất bại.

## 11. Bài thực hành và tiêu chí hoàn thành

### Tình huống

Team refactor module `booking` và sắp bổ sung `notifications`. Bạn cần thiết kế test đủ hẹp để phát hiện hồi quy của booking mà không chạy toàn hệ thống ở mỗi lần chỉnh một điều kiện; đồng thời biết lúc nào phải mở rộng test scope.

### Các bước

1. Tạo cấu trúc `TicketApplication` và module `booking` ở phần 3; cài `SeatInventory` trong package `internal`.
2. Viết `BookingService.reserve()`: lần đầu chấp nhận và phát `SeatReserved`; lần sau cùng ghế bị từ chối.
3. Tạo `@ApplicationModuleTest(mode = STANDALONE)` trong package `booking`, inject service và `BookingQueries`.
4. Thêm `@RecordApplicationEvents`, kiểm tra event type, correlation ID, reservation ID và seat code.
5. Kiểm tra ba luồng: thành công, đặt lại cùng ghế và input trống. Dùng seat code unique để tránh phụ thuộc thứ tự.
6. Viết phiên bản `Scenario` chờ `SeatReserved` đúng correlation ID; giải thích event được quan sát **khác** với consumer ngoài module hoàn tất.
7. Cố ý bỏ lệnh publish; xác nhận test event **FAIL** trong khi test state vẫn có thể PASS.
8. Cố ý cho duplicate reservation trả ID mới; xác nhận test chống đặt trùng **FAIL**.
9. Thêm một contract `SeatAvailability` ở module `inventory` dưới dạng biến thể; chọn `STANDALONE` + `@TestConfiguration` stub khi chỉ test booking.
10. Đổi sang `DIRECT_DEPENDENCIES` khi mục tiêu là kiểm tra bean `inventory` thật; xác nhận context và assertion behavior, không chỉ method rỗng.
11. Nếu đưa reservation xuống JPA, thêm module test DB với commit thật. Nếu cần listener của `notifications`, tạo integration test chứa consumer.
12. Chạy `ApplicationModules.verify()` riêng để bảo vệ module boundaries; không coi behavior test thay thế luật tĩnh.
13. Thêm test suites vào CI, lưu JUnit reports, kiểm tra required status check và hoàn nguyên mọi mutation trước merge.

### Ma trận nghiệm thu

| Thay đổi cố ý | Booking module test | Architecture test | Cross-module test |
| --- | --- | --- | --- |
| Baseline đúng | **PASS** | PASS nếu model hợp lệ | Không bắt buộc cho claim một module |
| Bỏ phát `SeatReserved` | **FAIL** ở event assertion | Có thể PASS | Có thể FAIL nếu consumer phụ thuộc event |
| Cho giữ trùng cùng ghế | **FAIL** ở behavior/state | Có thể PASS | Có thể FAIL |
| Đổi correlation ID event | **FAIL** theo predicate | Có thể PASS | Có thể FAIL |
| Không có bean nội bộ `SeatInventory` | **FAIL bootstrap** | Có thể PASS | Có thể FAIL |
| Dependency tới `inventory` không có bean trong `STANDALONE` | FAIL bootstrap nếu chưa cấp stub | Có thể PASS nếu dependency hợp lệ | Mode khác có thể PASS |
| Booking import implementation `inventory.internal` trái luật | Behavior có thể PASS | **FAIL** nếu bị verifier phát hiện | Có thể PASS |
| Notifications listener bị tắt | Có thể PASS | Có thể PASS | **FAIL** nếu kiểm tra notification |
| DB rollback sau event publish | Recorder có thể thấy event | Có thể PASS | **FAIL** nếu assert committed state |

Các kết quả là **kỳ vọng học tập**, không phải kết quả test đã được thực thi.

### Câu hỏi tự đánh giá

**1. Vì sao nên dùng `@ApplicationModuleTest` thay vì `@SpringBootTest` cho rule giữ ghế trong booking?** Vì claim nằm trong một module; module test giữ Spring wiring/event nhưng không cần nạp mọi consumer và hạ tầng ngoài.

**2. `STANDALONE` có đồng nghĩa “không có auto-configuration” không?** Không. Nó giới hạn phạm vi application modules; Spring Boot/test infrastructure vẫn có thể cung cấp bean.

**3. Vì sao một test đặt chỗ chỉ assert `accepted()` chưa đủ?** Vì có thể thiếu event hoặc state không khớp. Nếu claim bao gồm publication/side effect, phải assert chúng riêng.

**4. `@RecordApplicationEvents` chứng minh email đã gửi chưa?** Không. Nó chứng minh event được publish trong test context; module notifications không mặc nhiên được bootstrap.

**5. Khi nào cần `DIRECT_DEPENDENCIES`?** Khi cần kiểm tra sự phối hợp với module dependency trực tiếp thực sự, thay vì dùng stub ở biên.

**6. Một module test có thể truy cập DB không?** Có nếu module sở hữu persistence và test hạ tầng được cấu hình; cần ranh giới transaction phù hợp để xác nhận commit.

**7. Nếu booking có import nội bộ module khác nhưng mọi method test PASS thì sao?** Phải chạy `ApplicationModules.verify()` để kiểm tra dependency tĩnh, không dựa vào test behavior.

### Ghi nhớ

**Chọn `@ApplicationModuleTest` khi điều cần bảo vệ là behavior và bean wiring của một Spring Modulith application module.** Bắt đầu từ `STANDALONE`, đặt test trong package của module, inject API của module, assert **kết quả, event và state** bằng dữ liệu cô lập. Dùng `ApplicationEvents` hoặc `Scenario` cho hợp đồng event, chọn test double khi collaborator ngoài module chỉ là một đầu vào giả lập, và mở sang `DIRECT_DEPENDENCIES` khi mục tiêu là wiring thật. Khi cần database, transaction sau commit hoặc consumer ở module khác, bổ sung test tích hợp đúng phạm vi; với dependency rules, giữ `ApplicationModules.verify()` riêng. Một test context khởi động thành công chưa đủ — **assertion phải FAIL khi hành vi bị phá**.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
