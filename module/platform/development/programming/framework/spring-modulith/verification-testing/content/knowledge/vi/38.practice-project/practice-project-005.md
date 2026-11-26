# Tạo ApplicationModuleTest cho module nghiệp vụ

Trong dự án **Store Modular Monolith**, module `returns` xử lý yêu cầu trả hàng. Nghiệp vụ quy định: khách được yêu cầu trả hàng **trong vòng 30 ngày kể từ khi nhận**, ngày thứ 30 vẫn hợp lệ; mỗi đơn chỉ được tạo một yêu cầu trả hàng đang được ghi nhận; khi chấp nhận, module phát `ReturnAccepted` để những module khác có thể phản ứng sau này.

Làm thế nào để chứng minh ba điều ấy mà **không cần khởi động cả ứng dụng, cơ sở dữ liệu, cổng HTTP và module gửi email**? Đây là bài thực hành tạo **`@ApplicationModuleTest` cho chính module nghiệp vụ**. Test phải khởi tạo bean thật thuộc `returns`, gửi stimulus có dữ liệu riêng, kiểm tra **kết quả — trạng thái — sự kiện**, rồi **FAIL có chủ đích** khi người viết mã phá một quy tắc.

Bài thuộc chương **Dự án thực hành** của **SPRING_MODULITH_VERIFICATION_TESTING**. Chúng ta thực hành trên một module rõ ràng, từ cấu trúc package tới Java/JUnit, `@RecordApplicationEvents`, `Scenario`, phép thử âm và CI. `ApplicationModules.verify()` được giữ như một architecture gate bổ sung, không bị nhầm với bằng chứng rằng nghiệp vụ trả hàng đã chạy đúng.

> **Đầu ra cần đạt:** một `ReturnsModuleTest` dùng `@ApplicationModuleTest(mode = STANDALONE)` có những assertions bảo vệ ranh giới 30 ngày, không xử lý trùng, không tạo sự kiện khi thất bại, và kiểm tra đúng payload `ReturnAccepted`. Module test không được lệ thuộc vào chi tiết log hoặc vào thứ tự chạy test methods.

## 1. Chốt phạm vi và tiêu chí nghiệm thu của dự án

Ta cần kiểm thử **behavior của một application module**, không phải toàn chuỗi giao nhận. Hãy viết các invariant đủ cụ thể để có thể bị bác bỏ:

| Mã | Invariant | Bằng chứng JUnit mong muốn |
| --- | --- | --- |
| **R1** | Đơn nhận hàng **đúng 30 ngày trước** vẫn được chấp nhận | Kết quả `ACCEPTED` và có return ID |
| **R2** | Đơn nhận hàng 31 ngày trước bị từ chối | `OUT_OF_WINDOW`, không ghi state, không phát `ReturnAccepted` |
| **R3** | Một order chỉ có một return ID trong ledger | Lần thứ hai trả `ALREADY_REQUESTED`, ID cũ không đổi |
| **R4** | Chỉ lần chấp nhận đầu tiên phát một `ReturnAccepted` | `ApplicationEvents` lọc `correlationId` và assert cardinality |
| **R5** | Event mang đúng `returnId`, `orderId`, `correlationId` và số ngày | Assertion trên payload, không trên dòng log |
| **R6** | Input không hợp lệ bị từ chối trước khi sửa state | `IllegalArgumentException`, không có event |
| **R7** | Spring tạo và inject được các bean nghiệp vụ nội bộ | `@ApplicationModuleTest` bootstrap + `@Autowired` qua API |
| **R8** | Một module khác không được import mã `returns.internal` | `ApplicationModules.verify()` trong test kiến trúc **riêng** |

**Giới hạn của mô hình:** `daysSinceDelivery` do caller cung cấp để luyện kiểm thử. Ứng dụng production phải tính từ thời điểm giao hàng **đáng tin cậy** (thường từ database và `Clock` được kiểm soát), thay vì tin giá trị ngày do client tự khai. Bộ nhớ trả hàng ở bài này chỉ là `ConcurrentHashMap` trong một JVM: nó **không chứng minh commit, tính bền vững qua restart hay đồng thời nhiều instance**. Đó là nội dung dành cho phép kiểm thử DB/integration sau khi mở rộng dự án.

### Chọn đúng công cụ cho từng claim

- `@ApplicationModuleTest`: chứng minh **business behavior và wiring trong `returns`**.
- `@RecordApplicationEvents` / `ApplicationEvents`: chứng minh event **được publish trong test context** và đếm trong phạm vi test.
- `Scenario`: diễn đạt **stimulus → event phù hợp xuất hiện**.
- `ApplicationModules.verify()`: chứng minh **mối phụ thuộc tĩnh tuân thủ kiến trúc module**, không phải service chạy đúng.
- `@SpringBootTest` + DB: chỉ cần khi acceptance criterion chuyển sang **nhiều module, transaction sau commit, dữ liệu bền vững hoặc consumer side effect**.

## 2. Dựng cấu trúc module để Spring Modulith nhận diện đúng

Lớp ứng dụng nằm tại `com.example.store`. Module `returns` là package con trực tiếp; implementation ở subpackage `returns.internal`; sự kiện được đặt trong `returns.events`. Không đưa test vào package gốc theo thói quen nếu mục tiêu là chọn module `returns`.

```text
src/main/java/com/example/store/
├── StoreApplication.java
└── returns/                              ← application module returns
    ├── ReturnService.java               ← API nghiệp vụ gọi từ bên ngoài
    ├── ReturnResult.java
    ├── ReturnStatus.java
    ├── ReturnQueries.java               ← API đọc trạng thái
    ├── events/
    │   ├── package-info.java           ← contract event công bố tùy nhu cầu
    │   └── ReturnAccepted.java
    └── internal/
        └── ReturnLedger.java            ← mutable state, không public module API

src/test/java/com/example/store/
├── ModulithArchitectureTest.java
└── returns/
    └── ReturnsModuleTest.java
```

Lớp gốc:

```java
// src/main/java/com/example/store/StoreApplication.java
package com.example.store;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication.run(StoreApplication.class, args);
    }
}
```

Với cách phát hiện module mặc định của Spring Modulith, `returns` được tìm thấy từ package dưới `StoreApplication`. Nếu repository dùng **custom module detection**, cần kiểm tra mô hình thật được tìm thấy; đừng tự suy module scope chỉ vì folder đã được tạo.

### Dependencies tối thiểu của ví dụ

Trích đoạn `build.gradle` dưới đây giả định dự án đã cấu hình plugin Spring Boot, Java và **BOM/version management tương thích**; không phải file build hoàn chỉnh:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.modulith:spring-modulith-starter-core'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.modulith:spring-modulith-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Project dùng Java 17+ (record và cú pháp Java trong bài), JUnit Jupiter, AssertJ và Spring Modulith test starter. **Không cần** database, broker, Testcontainers hay web server cho `STANDALONE` test của module này. Nếu dự án có nhiều auto-configurations yêu cầu hạ tầng khác, cần tạo test profile/chọn module context phù hợp; không dùng `@SpringBootTest` toàn ứng dụng chỉ để giải quyết một vấn đề phạm vi chưa được phân tích.

## 3. Định nghĩa business contract mà test sẽ bảo vệ

### 3.1. Trạng thái trả về có nghĩa rõ ràng

```java
// returns/ReturnStatus.java
package com.example.store.returns;

public enum ReturnStatus {
    ACCEPTED,
    OUT_OF_WINDOW,
    ALREADY_REQUESTED
}
```

```java
// returns/ReturnResult.java
package com.example.store.returns;

import java.util.Objects;
import java.util.Optional;
import java.util.UUID;

public record ReturnResult(
        UUID orderId,
        ReturnStatus status,
        Optional<UUID> returnId
) {
    public ReturnResult {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(returnId, "returnId");

        if ((status == ReturnStatus.ACCEPTED)
                != returnId.isPresent()) {
            throw new IllegalArgumentException(
                    "Only accepted returns carry a new returnId"
            );
        }
    }
}
```

Quy ước được chọn: `ACCEPTED` mang một `returnId` mới; `OUT_OF_WINDOW` và `ALREADY_REQUESTED` trả `Optional.empty()`. Return ID đã có của đơn vẫn đọc được qua `ReturnQueries`. Đây là hợp đồng minh họa **nhất quán**, không phải một chuẩn API bắt buộc.

### 3.2. API đọc trạng thái cho test, không rò implementation

```java
// returns/ReturnQueries.java
package com.example.store.returns;

import java.util.Optional;
import java.util.UUID;

public interface ReturnQueries {

    Optional<UUID> findReturnId(UUID orderId);
}
```

Tại sao tạo `ReturnQueries` khi test có thể inject trực tiếp `ReturnLedger`? Vì test nên quan sát **trạng thái nghiệp vụ qua API module**, thay vì mở map nội bộ ra test hoặc tự nhìn vào cấu trúc storage. Khi thay ledger bằng JPA, phần lớn assertions vẫn có thể giữ nguyên.

### 3.3. Hợp đồng event của module

File `returns/events/package-info.java`:

```java
/**
 * Event contract của module returns cho module tiêu thụ được phép sử dụng.
 * Implementation và storage của returns không nằm trong contract này.
 */
@org.springframework.modulith.NamedInterface("events")
package com.example.store.returns.events;
```

Kiểu event:

```java
// returns/events/ReturnAccepted.java
package com.example.store.returns.events;

import java.util.Objects;
import java.util.UUID;

public record ReturnAccepted(
        UUID returnId,
        UUID orderId,
        UUID correlationId,
        int daysSinceDelivery
) {
    public ReturnAccepted {
        Objects.requireNonNull(returnId, "returnId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(correlationId, "correlationId");

        if (daysSinceDelivery < 0 || daysSinceDelivery > 30) {
            throw new IllegalArgumentException(
                    "Accepted return must be within 30 days"
            );
        }
    }
}
```

`returnId` định danh yêu cầu trả hàng được chấp nhận; `orderId` định danh đơn; `correlationId` gắn event với **stimulus cụ thể**. Không dùng cùng một UUID để thay thế mọi loại ID. Test sẽ lọc event theo correlation ID **do chính test tạo** để tránh PASS giả khi có nhiều event cùng loại.

**Lưu ý:** khai báo named interface ở đây phục vụ khả năng mở rộng nếu sau này có module nhận event. Test `returns` không cần tạo một consumer khác để kiểm chứng việc **publish `ReturnAccepted`**.

## 4. Cài đặt collaborator nội bộ và use case thật

### 4.1. Ledger thread-safe trong một JVM

```java
// returns/internal/ReturnLedger.java
package com.example.store.returns.internal;

import com.example.store.returns.ReturnQueries;
import java.util.Optional;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import org.springframework.stereotype.Component;

@Component
public class ReturnLedger implements ReturnQueries {

    private final ConcurrentMap<UUID, UUID> byOrderId =
            new ConcurrentHashMap<>();

    public Optional<UUID> createIfAbsent(UUID orderId) {
        UUID candidate = UUID.randomUUID();
        UUID existing = byOrderId.putIfAbsent(
                orderId, candidate
        );

        return existing == null
                ? Optional.of(candidate)
                : Optional.empty();
    }

    @Override
    public Optional<UUID> findReturnId(UUID orderId) {
        return Optional.ofNullable(byOrderId.get(orderId));
    }
}
```

Với `putIfAbsent`, **chỉ một thread trong cùng JVM** có thể ghi return ID đầu tiên cho mỗi order ID. Đây là một mô phỏng hữu ích để test duplicate request; nó **không phải bảo đảm exactly-once xuyên nhiều instance hoặc bền vững sau restart**.

`ReturnLedger` là Java `public` vì `ReturnService` thuộc package `returns` cần gọi method ở `returns.internal`. Nó vẫn nằm **bên trong cùng application module**; module ngoài không nên import nó. Muốn ẩn Java visibility hơn nữa có thể đưa một facade/package contract thích hợp vào cùng package internal rồi expose service tại root; ở bài này ranh giới Spring Modulith mới là trọng tâm.

### 4.2. Service: validation → quyết định → ghi state → phát event

```java
// returns/ReturnService.java
package com.example.store.returns;

import com.example.store.returns.events.ReturnAccepted;
import com.example.store.returns.internal.ReturnLedger;
import java.util.Objects;
import java.util.Optional;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;

@Service
public class ReturnService {

    private final ReturnLedger ledger;
    private final ApplicationEventPublisher events;

    public ReturnService(
            ReturnLedger ledger,
            ApplicationEventPublisher events) {
        this.ledger = ledger;
        this.events = events;
    }

    public ReturnResult request(
            UUID orderId,
            int daysSinceDelivery,
            UUID correlationId) {

        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(
                correlationId, "correlationId");

        if (daysSinceDelivery < 0) {
            throw new IllegalArgumentException(
                    "Delivery age must not be negative"
            );
        }

        if (daysSinceDelivery > 30) {
            return new ReturnResult(
                    orderId,
                    ReturnStatus.OUT_OF_WINDOW,
                    Optional.empty()
            );
        }

        Optional<UUID> created =
                ledger.createIfAbsent(orderId);

        if (created.isEmpty()) {
            return new ReturnResult(
                    orderId,
                    ReturnStatus.ALREADY_REQUESTED,
                    Optional.empty()
            );
        }

        UUID returnId = created.orElseThrow();

        events.publishEvent(new ReturnAccepted(
                returnId,
                orderId,
                correlationId,
                daysSinceDelivery
        ));

        return new ReturnResult(
                orderId,
                ReturnStatus.ACCEPTED,
                Optional.of(returnId)
        );
    }
}
```

Đây là **nghiệp vụ cụ thể** mà `ReturnsModuleTest` phải bảo vệ. Một request thành công tạo một record trong ledger và publish event. Request ngoài 30 ngày không ghi record. Một order đã có return ID bị từ chối **không phát event chấp nhận mới**.

Có một lựa chọn semantics đáng nêu rõ: service kiểm tra **quá hạn trước khi kiểm tra yêu cầu đã tồn tại**. Vì vậy nếu một order đã từng được chấp nhận rồi người gọi yêu cầu lại sau ngày 30, kết quả là `OUT_OF_WINDOW` chứ không phải `ALREADY_REQUESTED`. Test ở phần sau chủ động dùng ngày trong hạn khi kiểm tra duplicate để không trộn hai quy tắc. Nếu sản phẩm ưu tiên thông báo “đã yêu cầu trước đó” trong mọi trường hợp, cần đổi **contract rồi đổi test**, không đổi ngầm.

**Không giả định transactional event:** baseline chỉ dùng in-memory map và `ApplicationEventPublisher`; không có `@Transactional` hay database. Khi đưa vào production, việc ghi ledger và publish event phải được thiết kế consistency rõ ràng, có thể cần transactional event publication/backend. Một test module PASS ở đây không chứng minh khả năng khôi phục event sau khi JVM chết.

## 5. Viết `@ApplicationModuleTest(STANDALONE)` với assertions trọn vẹn

Đặt test trong **package của module**: `com.example.store.returns`. Annotation `@ApplicationModuleTest` cung cấp bootstrap theo ranh giới module, cho phép inject `ReturnService` và `ReturnQueries` từ **Spring beans thật của module returns**.

```java
// src/test/java/com/example/store/returns/ReturnsModuleTest.java
package com.example.store.returns;

import com.example.store.returns.events.ReturnAccepted;
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
class ReturnsModuleTest {

    @Autowired
    ReturnService returns;

    @Autowired
    ReturnQueries queries;

    @Autowired
    ApplicationEvents recordedEvents;

    @Test
    void dayThirtyIsAcceptedAndPublishesMatchingEvent() {
        UUID orderId = UUID.randomUUID();
        UUID correlationId = UUID.randomUUID();

        ReturnResult result = returns.request(
                orderId, 30, correlationId
        );

        assertThat(result.status())
                .isEqualTo(ReturnStatus.ACCEPTED);
        assertThat(result.orderId()).isEqualTo(orderId);
        assertThat(result.returnId()).isPresent();

        assertThat(queries.findReturnId(orderId))
                .isEqualTo(result.returnId());

        var matching = recordedEvents.stream(
                    ReturnAccepted.class)
                .filter(event ->
                        correlationId.equals(event.correlationId()))
                .toList();

        assertThat(matching).hasSize(1);

        ReturnAccepted event = matching.get(0);
        assertThat(event.returnId())
                .isEqualTo(result.returnId().orElseThrow());
        assertThat(event.orderId()).isEqualTo(orderId);
        assertThat(event.daysSinceDelivery()).isEqualTo(30);
    }

    @Test
    void dayThirtyOneIsRejectedWithoutStateOrEvent() {
        UUID orderId = UUID.randomUUID();
        UUID correlationId = UUID.randomUUID();

        ReturnResult result = returns.request(
                orderId, 31, correlationId
        );

        assertThat(result.status())
                .isEqualTo(ReturnStatus.OUT_OF_WINDOW);
        assertThat(result.returnId()).isEmpty();
        assertThat(queries.findReturnId(orderId)).isEmpty();
        assertThat(eventCountFor(correlationId)).isZero();
    }

    @Test
    void duplicateRequestKeepsTheOriginalReturnId() {
        UUID orderId = UUID.randomUUID();
        UUID firstCorrelation = UUID.randomUUID();
        UUID secondCorrelation = UUID.randomUUID();

        ReturnResult first = returns.request(
                orderId, 4, firstCorrelation);
        ReturnResult second = returns.request(
                orderId, 5, secondCorrelation);

        assertThat(first.status())
                .isEqualTo(ReturnStatus.ACCEPTED);
        assertThat(second.status())
                .isEqualTo(ReturnStatus.ALREADY_REQUESTED);
        assertThat(second.returnId()).isEmpty();
        assertThat(queries.findReturnId(orderId))
                .isEqualTo(first.returnId());

        assertThat(eventCountFor(firstCorrelation))
                .isEqualTo(1L);
        assertThat(eventCountFor(secondCorrelation))
                .isZero();
    }

    @Test
    void invalidInputDoesNotChangeStateOrPublish() {
        UUID orderId = UUID.randomUUID();
        UUID correlationId = UUID.randomUUID();

        assertThatThrownBy(() ->
                returns.request(orderId, -1, correlationId))
                .isInstanceOf(IllegalArgumentException.class);

        assertThatThrownBy(() ->
                returns.request(null, 1, correlationId))
                .isInstanceOf(NullPointerException.class);

        assertThatThrownBy(() ->
                returns.request(orderId, 1, null))
                .isInstanceOf(NullPointerException.class);

        assertThat(queries.findReturnId(orderId)).isEmpty();
        assertThat(eventCountFor(correlationId)).isZero();
    }

    @Test
    void dayZeroIsAValidBoundary() {
        UUID orderId = UUID.randomUUID();
        UUID correlationId = UUID.randomUUID();

        ReturnResult result = returns.request(
                orderId, 0, correlationId);

        assertThat(result.status())
                .isEqualTo(ReturnStatus.ACCEPTED);
        assertThat(result.returnId()).isPresent();
        assertThat(eventCountFor(correlationId)).isEqualTo(1L);
    }

    private long eventCountFor(UUID correlationId) {
        return recordedEvents.stream(ReturnAccepted.class)
                .filter(event ->
                        correlationId.equals(event.correlationId()))
                .count();
    }
}
```

### Tại sao test được đặt ở package này?

`@ApplicationModuleTest` cần xác định module mà class test thuộc về; đặt trong `com.example.store.returns` giúp phạm vi rõ ràng. Nếu chuyển class test lên `com.example.store`, test không còn nằm trong application module `returns` như dự định và có thể thất bại ngay khi xác định module.

### Không chỉ assert kết quả trả về

Nhìn vào `dayThirtyIsAcceptedAndPublishesMatchingEvent`: ba nguồn bằng chứng **độc lập về ý nghĩa** đều được kiểm tra.

| Bằng chứng | Điều được chứng minh | Một lỗi mà nó phát hiện |
| --- | --- | --- |
| `ReturnResult.status == ACCEPTED` | Use case quyết định đúng ở ngày 30 | So sánh `>= 30` thay `> 30` |
| `queries.findReturnId(orderId)` trùng ID trả về | State nội bộ của module được cập nhật | Service trả kết quả nhưng không ghi ledger |
| `ReturnAccepted` đúng payload/correlation ID | Module publish đúng event nghiệp vụ | Bỏ publish, phát event sai order/ID/ngày |

**Câu log `"Return accepted"` không có mặt trong bất kỳ assertion nào.** Log giúp điều tra, nhưng không thay các hợp đồng cần kiểm chứng.

### Vì sao dùng UUID riêng cho từng test?

Spring Test có thể cache `ApplicationContext` giữa test methods. `ReturnLedger` là singleton chứa `ConcurrentHashMap`, nên dùng cùng `orderId` giữa các methods có thể khiến bài test độc lập trở thành phụ thuộc thứ tự. UUID mới giữ mỗi stimulus tách biệt. `@RecordApplicationEvents` ghi nhận sự kiện trong test context cho phép lọc theo `correlationId` do method tự tạo.

Không suy luận rằng UUID riêng sẽ giải quyết **mọi** vấn đề isolation: khi có database thật hoặc các listener async còn chạy sau test, cần cơ chế dữ liệu/lifecycle rõ ràng hơn. Ở baseline event publisher/ledger đồng bộ, cách này phù hợp.

## 6. Khi nào thêm `Scenario` cho luồng stimulus → event?

`ApplicationEvents` rất phù hợp để **đếm event** và kiểm tra **không có event** trên đường lỗi. Nếu muốn diễn đạt một kịch bản theo sự kiện rõ ràng, Spring Modulith có `Scenario`:

```java
// Bổ sung vào ReturnsModuleTest ở phần 5.
// Thêm imports: java.util.UUID, org.springframework.modulith.test.Scenario.

@Test
void scenarioObservesTheAcceptedReturn(Scenario scenario) {
    UUID orderId = UUID.randomUUID();
    UUID correlationId = UUID.randomUUID();

    scenario.stimulate(() ->
                returns.request(orderId, 0, correlationId))
            .andWaitForEventOfType(ReturnAccepted.class)
            .matching(event ->
                    correlationId.equals(event.correlationId())
                    && orderId.equals(event.orderId()))
            .toArriveAndVerify(event -> {
                assertThat(event.daysSinceDelivery()).isZero();
                assertThat(event.returnId()).isNotNull();
                assertThat(queries.findReturnId(orderId))
                        .contains(event.returnId());
            });
}
```

Đây là **đoạn method bổ sung** vào class JUnit ở phần 5, không phải một file Java độc lập. `Scenario` nhận stimulus, chờ event **đúng loại và đúng ID**, rồi xác minh payload. Test nên có timeout hữu hạn theo cơ chế DSL được phiên bản Spring Modulith đang dùng hỗ trợ.

**Phân biệt rõ hai bài kiểm tra:**

- `Scenario` xác nhận **một `ReturnAccepted` phù hợp đã xuất hiện**.
- `ApplicationEvents` với `hasSize(1)` hoặc count xác nhận **số sự kiện được recorder quan sát trong phạm vi test** cho stimulus đồng bộ.

Một producer lỗi có thể publish cùng event hai lần: `Scenario` vẫn có thể PASS khi nhận sự kiện đầu tiên. Nếu invariant yêu cầu **không publish trùng**, giữ assertion cardinality riêng; nếu yêu cầu “consumer không tạo side effect trùng khi event được giao lại”, cần test idempotency ở consumer/database chứ không chỉ đếm publication.

### Ba mốc không được đồng nhất

| Mốc | Bằng chứng phù hợp |
| --- | --- |
| **E1 — Event publish** | `ApplicationEvents` / `Scenario` trong module test |
| **E2 — Transaction commit** | DB/transaction test, chỉ khi service đã có persistence |
| **E3 — Consumer khác module xử lý xong** | Integration test chứa consumer, query side effect sau commit |

`ReturnAccepted` ở baseline chưa có transaction. Nếu sau này thêm `@ApplicationModuleListener` ở module `notifications`, test `returns` standalone **không tự nạp notifications**; việc thấy E1 không chứng minh E3. Event Publication Registry nếu được cấu hình còn có lifecycle pending/completed riêng, không được suy từ recorder.

## 7. Kiểm soát bootstrap scope, dependency và cấu hình test

### 7.1. Vì sao dùng `STANDALONE` cho bài này?

`returns` có đủ `ReturnService`, `ReturnLedger` và API đọc `ReturnQueries` bên trong cùng application module. Test không cần implementation của module nào khác:

```java
@ApplicationModuleTest(
        mode = ApplicationModuleTest.BootstrapMode.STANDALONE
)
class ReturnsModuleTest {
    // inject service, queries và assert behavior
}
```

`STANDALONE` thu hẹp phạm vi **application modules được bootstrap**, không có nghĩa Spring Boot tắt mọi auto-configuration/bean hạ tầng. Vì vậy smoke test context có giá trị, nhưng assertion nghiệp vụ mới là trọng tâm.

### 7.2. Nếu service bắt đầu cần một API từ module `orders`?

Giả sử module `returns` được yêu cầu xác minh **đơn đã được giao** qua `orders::queries`:

```text
returns --(Java dependency)--> orders::queries
```

Đây là **biến thể thiết kế**, không phải code hiện có trong baseline; cần bổ sung public query contract ở orders, khai báo named interface và `allowedDependencies` phù hợp. Khi đó có hai chiến lược:

| Mục tiêu | Cách viết module test |
| --- | --- |
| Kiểm tra riêng rule 30 ngày, giả lập kết quả đã giao | `STANDALONE` + test double cho query API của orders |
| Kiểm tra wiring với bean `orders` thật và cách trả trạng thái | `DIRECT_DEPENDENCIES` để nạp returns + dependency trực tiếp |
| Kiểm tra luồng đặt đơn → giao hàng → nhận trả → hoàn tiền | `@SpringBootTest`/integration scope chứa mọi module liên quan |
| Kiểm tra returns chỉ được import `orders::queries` | `ApplicationModules.verify()` chạy riêng |

Ví dụ **chỉ về cách khai báo test double**, giả sử interface `OrderDeliveryQuery` thuộc package công bố của module orders và service returns của **biến thể** inject nó:

```java
// Trích đoạn test configuration của biến thể,
// không dán nguyên xi vào baseline ReturnService.
@TestConfiguration(proxyBeanMethods = false)
static class DeliveredOrdersStub {

    @Bean
    OrderDeliveryQuery orderDeliveryQuery() {
        return orderId -> true;
    }
}
```

Cần dùng `@Import(DeliveredOrdersStub.class)` trong class test, imports `TestConfiguration`/`Bean`/`Import`, và một contract `OrderDeliveryQuery` thật đã được định nghĩa trong biến thể. **Không khai báo bean giả mà production service không inject** rồi nghĩ đã kiểm tra được dependency.

### 7.3. `DIRECT_DEPENDENCIES` và `ALL_DEPENDENCIES` không phải “mọi module”

- `DIRECT_DEPENDENCIES`: module đang test cùng các application modules mà nó phụ thuộc **trực tiếp**.
- `ALL_DEPENDENCIES`: module đang test và các dependency theo chuỗi **bắc cầu**.
- Một module **tiêu thụ sự kiện** của returns không mặc nhiên là dependency của returns. Nếu cần kiểm tra side effect của nó, viết integration test có consumer thật.

Chọn mode dựa vào **claim**, không chỉ vì `STANDALONE` báo thiếu bean. Đừng nới `allowedDependencies` để làm test bootstrap thành công: rule kiến trúc và việc cung cấp test dependency là hai quyết định riêng.

## 8. Thử phá nghiệp vụ có chủ đích: test phải đỏ đúng chỗ

Một test đầy đủ phải có khả năng FAIL khi luật bị phá. Trong **nhánh thực hành**, thử từng mutation rồi **khôi phục** trước khi thử mutation kế tiếp:

| Mutation trong production code | Assertion phải FAIL | Điều mutation giúp chứng minh |
| --- | --- | --- |
| Thay `daysSinceDelivery > 30` bằng `>= 30` | `dayThirtyIsAcceptedAndPublishesMatchingEvent` | Test bảo vệ **biên ngày 30** |
| Bỏ `ledger.createIfAbsent(orderId)` nhưng vẫn trả `ACCEPTED` | Assert `ReturnQueries.findReturnId` | Không chỉ tin result được dựng sẵn |
| Bỏ `events.publishEvent(...)` | Event count/payload assertion và `Scenario` | Test bảo vệ publication |
| Event chứa `UUID.randomUUID()` thay correlation ID đầu vào | Filter theo correlation ID không khớp | Không nhận nhầm event của stimulus khác |
| Thay `putIfAbsent` bằng `put` và luôn trả ID mới | `duplicateRequestKeepsTheOriginalReturnId` | Test bảo vệ không tạo return thứ hai |
| Cho request ngày 31 vẫn đi qua ledger | `dayThirtyOneIsRejectedWithoutStateOrEvent` | Kiểm tra negative path có state assertion |
| Bỏ check ngày âm | `invalidInputDoesNotChangeStateOrPublish` | Input lỗi phải bị chặn trước side effect |
| Đổi text/level của `LOG.info` nhưng giữ logic | **Không test nghiệp vụ nào nên FAIL** | Tránh phụ thuộc log không ổn định |
| Thêm dependency trái phép đến module internal khác | Architecture `verify()` phải FAIL | Behavior test không thay luật kiến trúc |

**Mutation về ledger:** khi cố ý “bỏ ghi state”, đừng viết code Java không biên dịch được rồi coi compiler error là bằng chứng assertion. Thay bằng một implementation lỗi nhưng **vẫn có method/return types hợp lệ**, sau đó chạy đúng bài test JUnit.

### Đọc đúng kết quả đỏ

- **Context bootstrap FAIL trước test method:** có thể thiếu bean hoặc cấu hình test sai, chưa chứng minh rule 30 ngày sai.
- **Assertion `ReturnStatus` FAIL:** business branch có khả năng sai.
- **State assertion FAIL còn result đúng:** service có thể đã trả kết quả nhưng không ghi ledger.
- **Event assertion FAIL còn state đúng:** publish/payload có vấn đề; không “sửa” bằng cách thêm log.
- **Scenario timeout:** kiểm tra stimulus có chạy, event type, predicate và phạm vi context trước khi tăng timeout.
- **`verify()` FAIL:** vấn đề ở dependency graph hoặc API exposure, không sửa bằng cách đổi kết quả nghiệp vụ.

### Hạn chế của phép kiểm tra đồng thời

`ConcurrentHashMap.putIfAbsent` có thao tác nguyên tử trong **cùng process**, nhưng các test hiện tại mới kiểm tra hai yêu cầu **tuần tự**. Nếu acceptance criterion bao gồm đồng thời, cần một concurrency test với `CountDownLatch`/executor và kiểm tra chỉ một request `ACCEPTED`. Khi chuyển DB, cần unique constraint/locking và integration test cùng engine. Không tuyên bố test duplicate tuần tự đã chứng minh an toàn nhiều thread hoặc nhiều instance.

## 9. Bổ sung architecture gate và CI mà không làm mất phạm vi module test

### 9.1. Kiểm tra cấu trúc là một bài JUnit riêng

Dù `ReturnsModuleTest` PASS, một class khác trong ứng dụng vẫn có thể import vào `returns.internal` hoặc tạo vòng phụ thuộc. Giữ test kiến trúc riêng ở package gốc:

```java
// src/test/java/com/example/store/ModulithArchitectureTest.java
package com.example.store;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModulithArchitectureTest {

    @Test
    void applicationModuleBoundariesRemainValid() {
        ApplicationModules.of(StoreApplication.class).verify();
    }
}
```

Với chỉ một module returns trong baseline, graph rất đơn giản; khi thêm `orders`, `notifications` hoặc `refunds`, test này trở thành gate bảo vệ toàn application module model được phát hiện. Nó **không thay** các assertions nghiệp vụ trong `ReturnsModuleTest`.

Nếu sau này có module tiêu thụ `returns::events`, cần khai báo `allowedDependencies = "returns::events"` cho consumer và kiểm tra cách nó import. Không để consumer dùng `returns.internal.ReturnLedger` chỉ vì class Java là `public`.

### 9.2. Chạy test chọn lọc trong phát triển

```bash
# Một-module behavior và event contract:
./gradlew test --tests 'com.example.store.returns.ReturnsModuleTest'

# Luật kiến trúc application modules:
./gradlew test --tests 'com.example.store.ModulithArchitectureTest'

# Toàn bộ tests thuộc source set test:
./gradlew test
```

Đây là **lệnh hướng dẫn**, không phải kết quả đã chạy trong nhiệm vụ soạn tài liệu. Lệnh `test` chỉ chạy test được cấu hình trong task đó; nếu project tách `integrationTest`, cần gọi thêm suite tương ứng. Với Maven/Surefire được cấu hình, có thể chạy `mvn -B test` và kiểm tra report discovery.

### 9.3. GitHub Actions quality gate

```yaml
name: Modulith returns module gate

on:
  pull_request:

jobs:
  returns-contracts:
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

      - name: Architecture and module behavior tests
        run: bash ./gradlew --no-daemon test

      - name: Preserve JUnit reports when a test fails
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: returns-module-test-reports
          path: |
            **/build/test-results/**/*.xml
            **/build/reports/tests/**
          if-no-files-found: warn
```

Đây là **workflow minh họa** cho project có Gradle wrapper, test task và JUnit Platform đã được cấu hình, không phải workflow đã chạy trên repository của bài. Muốn chặn merge, cần **branch protection/ruleset yêu cầu job `returns-contracts` thành công**. Bước upload với `if: always()` giữ kết quả khi có lỗi, không thay đổi trạng thái FAIL.

### Điều CI thực sự phải chứng minh

Đừng chỉ tìm dòng `BUILD SUCCESSFUL` trong console. Cần kiểm tra JUnit report có **`ReturnsModuleTest` và `ModulithArchitectureTest` được phát hiện**, có số case expected, và một mutation có chủ đích làm job FAIL. Không dùng `-x test`, `-DskipTests` hoặc filter bỏ test architecture rồi báo đã kiểm chứng module.

## 10. Bài tập ngắn, checklist nghiệm thu và hướng mở rộng

### Bài thực hành

**Tình huống:** một developer đổi quy tắc trả hàng thành `daysSinceDelivery >= 30` bị từ chối và bỏ publish event trên nhánh chấp nhận. Một bài test chỉ `assertThat(context).isNotNull()` vẫn có thể PASS; nhiệm vụ là xây test bảo vệ đúng lỗi.

Thực hiện theo thứ tự:

1. Tạo `StoreApplication`, package `returns`, `returns.internal` và `returns.events` như phần 2.
2. Triển khai `ReturnStatus`, `ReturnResult` và `ReturnQueries` đúng contract phần 3.
3. Tạo `ReturnLedger` với `ConcurrentHashMap.putIfAbsent`, không đưa map ra public module API.
4. Viết `ReturnService.request(...)` có validation, rule `> 30`, duplicate và `ReturnAccepted`.
5. Tạo `ReturnsModuleTest` trong **package `returns`**, dùng `@ApplicationModuleTest(STANDALONE)` và `@RecordApplicationEvents`.
6. Viết ít nhất năm test cases: ngày 30, ngày 31, đặt trùng, ngày âm/null và ngày 0.
7. Với yêu cầu được chấp nhận, assert **status, return ID, state đọc qua queries và payload event** có correlation ID chính xác.
8. Thêm một method dùng `Scenario` để chờ `ReturnAccepted` thuộc đúng stimulus; không suy từ event rằng consumer khác module đã xử lý.
9. **Mutation A:** đổi `> 30` thành `>= 30`. Xác nhận test boundary **FAIL**; hoàn nguyên.
10. **Mutation B:** bỏ publish event. Xác nhận event assertion **FAIL** dù ledger đã ghi; hoàn nguyên.
11. **Mutation C:** ghi đè return ID thay vì `putIfAbsent`. Xác nhận duplicate test **FAIL**; hoàn nguyên.
12. Viết `ModulithArchitectureTest` gọi `verify()`. Khi thêm consumer sau này, thử import internal để thấy structural gate FAIL.
13. Đưa suite vào CI, xem JUnit report, bật required check và ghi rõ chưa kiểm thử database/concurrency/retry nếu chưa có.

### Ma trận kết quả kỳ vọng

| Tình huống | Result | State | Event | Architecture |
| --- | --- | --- | --- | --- |
| Baseline ngày 30 | `ACCEPTED` | Có return ID | Một event đúng ID | PASS nếu model hợp lệ |
| Ngày 31 | `OUT_OF_WINDOW` | Không có | Không có | Không bị tác động |
| Hai lần cùng order trong hạn | Lần hai `ALREADY_REQUESTED` | ID đầu giữ nguyên | Chỉ lần đầu phát | Không bị tác động |
| Sai rule biên `>= 30` | **FAIL** ở ngày 30 | Có thể sai | Có thể thiếu | Có thể PASS |
| Bỏ publish event | Result có thể đúng | State có thể đúng | **FAIL** | Có thể PASS |
| Ghi đè return ID | Duplicate assertion **FAIL** | ID thay đổi | Event có thể trùng | Có thể PASS |
| Dùng `returns.internal` từ module khác | Module test có thể PASS | Có thể đúng | Có thể đúng | **FAIL** theo boundary |
| Không bootstrap được `ReturnLedger` | **FAIL context** | Không kiểm tra được | Không kiểm tra được | Có thể PASS |
| Listener ngoài module ngừng xử lý | Producer module test có thể PASS | Ledger returns có thể đúng | E1 có thể đúng | Có thể PASS; cần integration E3 |

Các trạng thái là **kỳ vọng thiết kế cho bài tập**, không phải kết quả Gradle/JUnit đã được thực thi trong workspace.

### Checklist bàn giao

- [ ] Test nằm trong đúng package của module nghiệp vụ `returns`.
- [ ] Có `@ApplicationModuleTest(mode = STANDALONE)` và Spring inject **bean thật** của module.
- [ ] Assertion bao phủ **boundary**, negative branch, duplicate, state và payload event.
- [ ] Event được lọc theo `correlationId` do test tạo; không đếm event “bất kỳ”.
- [ ] Input lỗi không để lại state hoặc event của stimulus ấy.
- [ ] Dữ liệu test tách biệt, không dựa thứ tự chạy methods hay context mới cho từng case.
- [ ] `Scenario` chỉ dùng để xác nhận stimulus → event, không diễn giải quá mức thành commit hoặc consumer completed.
- [ ] Không dùng log string, `Thread.sleep` hoặc “context loads” thay contract assertions.
- [ ] Có một architecture test `ApplicationModules.verify()` riêng cho module boundaries.
- [ ] Các mutation thử nghiệm làm đúng test FAIL, đã hoàn nguyên trước khi merge.
- [ ] CI chạy được các test cần thiết, giữ JUnit reports, và có required check.
- [ ] Giới hạn in-memory, transaction, concurrency, persistence và retry được nêu rõ.

### Ghi nhớ

**Tạo `@ApplicationModuleTest` cho module nghiệp vụ nghĩa là kiểm tra behavior và wiring của chính module đó, không phải chỉ khởi động một Spring context.** Với `returns`, test theo `STANDALONE` phải gọi `ReturnService` thật, đọc state qua `ReturnQueries` và xác minh `ReturnAccepted` bằng `ApplicationEvents` hoặc `Scenario`. Boundary ngày 30/31, duplicate và input lỗi là các case buộc bài test có khả năng FAIL khi nghiệp vụ hồi quy. Khi thêm dependency trực tiếp hoặc persistence, chọn test double/`DIRECT_DEPENDENCIES` hay integration test theo claim mới; giữ `ApplicationModules.verify()` riêng để chặn phụ thuộc tĩnh sai và dùng CI như một quality gate.

### Tài liệu tham khảo

- [Spring Modulith — Integration Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html)
- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
