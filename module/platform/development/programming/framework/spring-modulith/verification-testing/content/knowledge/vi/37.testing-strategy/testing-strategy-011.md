# Ghi lại phạm vi những gì test không chứng minh

## 1. Viết rõ “không chứng minh” ngay cạnh kết quả PASS

Một test có tên `paymentEventIsPublished()` chạy xanh không có nghĩa payment đã được ghi vào database, listener downstream đã chạy hay broker đã ack. Nó có thể chỉ chứng minh một lời gọi `ApplicationEventPublisher.publishEvent(...)` đã xảy ra. Nếu ghi report là **“payment flow verified end-to-end”**, nhóm phát triển đã suy diễn vượt quá bằng chứng test cung cấp.

**Trọng tâm của bài:** đối với mỗi test quan trọng, ghi rõ **tuyên bố được hỗ trợ** (*supported claim*) và **những điều test không chứng minh** (*non-claims*), kèm điều kiện chạy và test khác có trách nhiệm lấp khoảng trống. Đây không phải lời cảnh báo chung chung “test không thể chứng minh tất cả”; nó là một **đầu ra kỹ thuật có thể review**, xuất hiện ngay trong code, tài liệu test hoặc CI evidence report.

Trong học phần `SPRING_MODULITH_VERIFICATION_TESTING`, ta đang kiểm chứng ranh giới kiến trúc ứng dụng Spring Modulith bằng `ApplicationModules` và quy tắc phụ thuộc module, dùng `@ApplicationModuleTest` cho event/database/integration, rồi tổ chức quality gate trong CI để ngăn phụ thuộc sai và hồi quy. Chương này có tên **Chọn chiến lược**: phạm vi kết luận của mỗi test chính là căn cứ chọn tầng unit, module, adapter hay full integration.

### 1.1. Một phiếu bằng chứng tối thiểu

| Trường ghi nhận | Phải trả lời |
| --- | --- |
| **Claim** | Khi test PASS, điều **cụ thể** nào được xác nhận? |
| **SUT thực sự chạy** | Class/module/adapter/listener/DB/broker nào là thật? |
| **Double và giả định** | Những dependency nào là mock/stub/fake? Cấu hình, transaction, input nào đã giả định? |
| **Stimulus** | Test kích hoạt đường nào: gọi service, publish Spring event, HTTP, gửi Kafka/RabbitMQ? |
| **Oracle** | Test quan sát gì: interaction, `PublishedEvents`, committed state, registry publication hay broker ack? |
| **Non-claims** | Những kết luận hấp dẫn nhưng **không được phép suy ra** từ oracle ấy? |
| **Gap owner** | Test/suite khác nào kiểm tra phần còn thiếu? Nếu chưa có, ai nhận risk? |

Ví dụ:

```text
TEST: OrderPublisherModuleTests.publishesExpectedEvent
CLAIM: orders phát một OrderSubmitted đúng eventId/orderId/SKU/quantity
REAL: OrderPlacement + Spring event publication trong module test
DOUBLE: PSP/email port có thể được stub; inventory listener không bootstrap
ORACLE: PublishedEvents.ofType(OrderSubmitted).matching(eventId)
NON-CLAIMS:
  - inventory đã xử lý hoặc commit reservation
  - Event Publication Registry hoàn tất hoặc retry đúng
  - Kafka/RabbitMQ đã nhận/ack message
  - mọi input hoặc mọi lần chạy đồng thời đều thành công
GAP OWNER:
  - InventoryConsumerModuleTests
  - OrderToInventoryIntegrationIT
  - BrokerTransportIT nếu production dùng broker
```

Đây là **mẫu phiếu**, không phải kết quả chạy thật. Trong dự án, liên kết từng gap tới test ID hoặc issue cụ thể; không tạo một nhãn chung “integration test đã cover” mà không biết test nào và có được chạy trong CI không.

### 1.2. Hai lỗi suy luận cần chặn

1. **Đánh đồng thành công của một thao tác với thành công của workflow:** publisher gọi method ≠ event delivered ≠ listener committed ≠ registry completed ≠ broker acknowledged.
2. **Đánh đồng một lần PASS với đúng trong mọi hoàn cảnh:** một đầu vào, một trạng thái DB, một thứ tự chạy và một profile không chứng minh mọi input, mọi interleaving hoặc deployment production.

Cách viết non-claim tốt là **cụ thể, kiểm chứng được và có bước kế tiếp**. Viết “không bảo đảm tính đúng tuyệt đối” quá mơ hồ; viết “không chạy consumer nên chưa chứng minh reservation được commit” hữu ích hơn.

## 2. Dùng “evidence ledger” để tránh lẫn các lớp kiểm chứng

Một luồng nghiệp vụ mẫu: module `orders` phát `OrderSubmitted`, module `inventory` nhận và ghi `Reservation`; database là PostgreSQL, adapter ngoài có thể gửi thêm message sang RabbitMQ. Những mắt xích khác nhau cần **oracle khác nhau**.

| Test / nguồn bằng chứng | Chứng minh được khi PASS | **Không chứng minh** | Phép kiểm bổ sung |
| --- | --- | --- | --- |
| Mockito unit test use case | Service gọi port với arguments đúng | Port adapter thực, Spring wiring, DB commit | Adapter contract và module tests |
| `ApplicationModules.of(...).verify()` | Module dependencies tuân thủ rules đang cấu hình | Event được publish, listener có side effect | Producer/consumer/integration |
| Producer `@ApplicationModuleTest` + `PublishedEvents` | Đúng Spring event được publish trong module scope | Listener consumer đã chạy, broker ack, DB downstream | Consumer/cross-module tests |
| Consumer `@ApplicationModuleTest` + `Scenario` | Handler thật tạo state đúng từ event test phát | Producer thật đã phát event ấy | Producer test và cross-module integration |
| `@SpringBootTest` producer→consumer | Beans và đường in-process thực tạo business state | Transport broker nếu không đi qua broker; recovery khi restart | Broker/registry recovery tests |
| PostgreSQL Testcontainers repository test | Mapping, SQL/constraint/transaction theo engine được chạy | PSP, Kafka/RabbitMQ, logic ở adapter khác | Contract/integration tests |
| RabbitMQ/Kafka transport test | Routing, serialization, ack/offset trong topology test | Business aggregate nhất thiết đã commit đúng | Consumer/public-state test |
| Registry recovery test | Publication/target được tracking/retry theo provider test | Exactly-once trong mọi crash/restart và provider khác | Idempotency/restart test có scope rõ |
| CI suite xanh | Các task **thực sự chạy** không báo failure theo oracle của chúng | Những task SKIPPED/NOT_RUN hoặc môi trường production | Manifest CI + missing-gap gate |

**Evidence ledger** không phải checklist cho có. Nó phải cho phép reviewer hỏi: *“Nếu sửa lỗi X vào production, test nào sẽ đỏ?”* Nếu không xác định được một phép kiểm với đúng SUT/oracle, thì **khoảng trống bằng chứng vẫn mở**.

### 2.1. Dùng cùng một câu cú khi review test

Với mỗi test, hoàn thành hai mệnh đề:

- **“Test này chứng minh...”** bằng một hành vi và oracle cụ thể: “sau `OrderPlacement.place(...)`, `PublishedEvents` có `OrderSubmitted` cùng event ID và payload”.
- **“Test này không chứng minh...”** bằng một mắt xích chưa chạy: “chưa có `inventory` listener hoặc PostgreSQL commit được quan sát”.

Không viết “integration OK” nếu bài chỉ dùng một mock `ReservationQueries` trả dữ liệu mong đợi. SUT thật là điều kiện bắt buộc để kết luận, bất kể test class có tên `IntegrationTest`.

### 2.2. Xác định mốc quan sát và thời gian quan sát

Một test có thể kiểm tra sự kiện trong **một execution window** hữu hạn. Đó không tự là bằng chứng sự kiện sẽ **không bao giờ** xuất hiện sau này, đặc biệt khi còn retry worker, timer hoặc publication incomplete. Ghi rõ điều kiện chờ: “sau khi attempt 2 báo hoàn tất, count receipts vẫn là 1”, thay vì “không có receipt thứ hai”.

## 3. Unit test Mockito: chứng minh hợp đồng của caller, không phải dependency thật

Giả sử một use case yêu cầu gateway thu tiền, rồi yêu cầu phát `PaymentCaptured`. Unit test có thể cô lập gateway để kiểm tra input và payload, nhưng không được kết luận remote gateway thật đã gửi/nhận yêu cầu hoặc Spring listener đã xử lý.

### 3.1. Các kiểu ví dụ

```java
// File: com/example/shop/payments/ChargePort.java
package com.example.shop.payments;

import java.math.BigDecimal;
import java.util.UUID;

public interface ChargePort {
    ChargeReceipt capture(
            UUID orderId, BigDecimal amount, String idempotencyKey);
}
```

```java
// File: com/example/shop/payments/ChargeReceipt.java
package com.example.shop.payments;

public record ChargeReceipt(String providerReference) {}
```

```java
// File: com/example/shop/payments/events/PaymentCaptured.java
package com.example.shop.payments.events;

import java.util.UUID;

public record PaymentCaptured(
        UUID eventId, UUID orderId, String providerReference) {}
```

```java
// File: com/example/shop/payments/CaptureApplicationService.java
package com.example.shop.payments;

import java.math.BigDecimal;
import java.util.UUID;

import com.example.shop.payments.events.PaymentCaptured;
import org.springframework.context.ApplicationEventPublisher;

public final class CaptureApplicationService {

    private final ChargePort gateway;
    private final ApplicationEventPublisher events;

    public CaptureApplicationService(
            ChargePort gateway, ApplicationEventPublisher events) {
        this.gateway = gateway;
        this.events = events;
    }

    public void capture(
            UUID orderId, BigDecimal amount, String idempotencyKey) {

        ChargeReceipt receipt =
                gateway.capture(orderId, amount, idempotencyKey);

        events.publishEvent(new PaymentCaptured(
                UUID.randomUUID(), orderId, receipt.providerReference()));
    }
}
```

Đây là ví dụ **orchestration tối giản**. Production payment workflow cần transaction/idempotency/unknown outcome/reconciliation phù hợp; việc service publish event ngay sau network response không chứng minh payment đã được ghi bền vào DB.

### 3.2. JUnit/Mockito với non-claims ghi ngay cạnh test

```java
package com.example.shop.payments;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.util.UUID;

import com.example.shop.payments.events.PaymentCaptured;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.context.ApplicationEventPublisher;

@ExtendWith(MockitoExtension.class)
class CaptureApplicationServiceTest {

    @Mock ChargePort gateway;
    @Mock ApplicationEventPublisher publisher;

    /**
     * CLAIM:
     * - Service gọi ChargePort với đúng order/amount/key.
     * - Service yêu cầu publish PaymentCaptured có payload đúng.
     *
     * NON-CLAIMS:
     * - Không chứng minh PSP thật đã capture tiền.
     * - Không chứng minh Spring dispatch tới listener.
     * - Không chứng minh DB/registry/broker đã commit/ack.
     * GAP: ChargeAdapterContractIT, PaymentConsumerModuleTests.
     */
    @Test
    void passesExpectedArgumentsAndRequestsEventPublication() {
        UUID orderId = UUID.randomUUID();
        BigDecimal amount = new BigDecimal("125000.00");
        String key = "payment-" + UUID.randomUUID();

        when(gateway.capture(orderId, amount, key))
                .thenReturn(new ChargeReceipt("psp-ref-001"));

        var service =
                new CaptureApplicationService(gateway, publisher);
        service.capture(orderId, amount, key);

        verify(gateway).capture(orderId, amount, key);

        ArgumentCaptor<PaymentCaptured> captor =
                ArgumentCaptor.forClass(PaymentCaptured.class);
        verify(publisher).publishEvent(captor.capture());

        PaymentCaptured requested = captor.getValue();
        assertThat(requested.eventId()).isNotNull();
        assertThat(requested.orderId()).isEqualTo(orderId);
        assertThat(requested.providerReference())
                .isEqualTo("psp-ref-001");
    }
}
```

**Chứng cứ thực:** mock `gateway` trả receipt; mock `publisher` ghi nhận method call với payload. ApplicationEventPublisher không dispatch thật vì bị mock.

**Non-claims phải có:** mapping lỗi HTTP 409/503, idempotency của PSP, transaction, listener registration, `@TransactionalEventListener(AFTER_COMMIT)`, Event Publication Registry, RabbitMQ/Kafka.

### 3.3. Bẫy khi biến `verify(...)` thành lời cam kết lớn hơn

`verify(publisher).publishEvent(...)` không nói **event đã tới consumer**. `verify(gateway).capture(...)` không nói remote server đã nhận request. Một `@Test` gắn nhãn “payment captured end-to-end” dù chỉ thực thi service và mock chính là **tên gây hiểu nhầm**. Đặt tên theo điều được xác minh: `requestsPublicationWithExpectedPayload`.

Nếu test dùng mock repository có `when(findById).thenReturn(paid)`, việc assert state `PAID` chỉ chứng minh stub trả giá trị đó. Không tạo oracle bằng **chính giá trị đã stub** rồi gọi là đã kiểm thử persistence.

## 4. Producer module test: `PublishedEvents` không phải bằng chứng consumer đã commit

Bài test của module `orders` gọi public command và quan sát event `OrderSubmitted` đã được publish. Đây là mức mạnh hơn Mockito publisher unit test: Spring `ApplicationContext` và publisher/event publication path chạy thật **trong phạm vi module test**.

### 4.1. Event và public command contract

```java
// File: com/example/shop/orders/events/OrderSubmitted.java
package com.example.shop.orders.events;

import java.util.UUID;

public record OrderSubmitted(
        UUID eventId,
        UUID orderId,
        String sku,
        int quantity) {}
```

```java
// File: com/example/shop/orders/PlaceOrderResult.java
package com.example.shop.orders;

import java.util.UUID;

public record PlaceOrderResult(UUID orderId, UUID eventId) {}
```

```java
// File: com/example/shop/orders/OrderPlacement.java
package com.example.shop.orders;

public interface OrderPlacement {
    PlaceOrderResult place(String sku, int quantity);
}
```

Các kiểu trên là **contract do ứng dụng ví dụ tự định nghĩa**, không phải Spring Modulith cung cấp. `PlaceOrderResult.eventId()` được đưa ra để test có correlation ID; ứng dụng thật có thể dùng cơ chế correlation khác.

### 4.2. JUnit producer test và ranh giới chứng minh

```java
package com.example.shop.orders;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import com.example.shop.orders.events.OrderSubmitted;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderPublisherModuleTests {

    @Autowired OrderPlacement orders;

    /**
     * CLAIM: OrderPlacement công bố OrderSubmitted đúng ID/payload
     * qua Spring application event publication trong module test.
     * NON-CLAIMS: Inventory listener chưa chắc được bootstrap;
     * không chứng minh reservation commit hoặc AMQP/Kafka ack.
     * GAP: InventoryConsumerModuleTests, OrderToInventoryIT.
     */
    @Test
    void publishesOrderSubmittedForCurrentOrder(
            PublishedEvents publishedEvents) {

        String sku = "SKU-" + UUID.randomUUID();
        PlaceOrderResult placed = orders.place(sku, 2);

        var matches = publishedEvents.ofType(OrderSubmitted.class)
                .matching(OrderSubmitted::eventId, placed.eventId());

        assertThat(matches).hasSize(1);

        OrderSubmitted event = matches.iterator().next();
        assertThat(event.orderId()).isEqualTo(placed.orderId());
        assertThat(event.sku()).isEqualTo(sku);
        assertThat(event.quantity()).isEqualTo(2);
    }
}
```

**Điều kiện thực thi:** module `orders` phải có implementation `OrderPlacement`, bean/transaction/schema mà command cần. Test không mock `OrderPlacement` hay Spring event publisher. Nếu command gọi external PSP/email, có thể thay đúng **external port** bằng test double để giữ scope theo mục tiêu.

**Kết luận chính xác sau PASS:** producer đã publish một `OrderSubmitted` phù hợp với `eventId` của invocation trong Spring Modulith test context.

**Không được kết luận:**

- `inventory` đã nghe event, tạo reservation hoặc commit stock.
- Mọi subscriber khác đã hoàn tất hoặc Event Publication Registry đã mark completed.
- Event đã đi qua network/broker, offset Kafka đã commit hay RabbitMQ đã ack.
- Sau restart/retry cùng logical event vẫn idempotent.
- Có đúng một event **trong toàn hệ thống** hoặc trên mọi execution; assertion đang áp dụng cho recording/scope của test.

### 4.3. `@ApplicationModuleTest` không tự giải nghĩa tên “integration”

Bootstrap scope của Spring Modulith phụ thuộc module, annotation mode và dependencies. Nếu `inventory` là **consumer downstream** của event `orders`, chạy module test phía `orders` không có nghĩa tự động bootstrap consumer. Ngay cả `ALL_DEPENDENCIES` cũng chủ yếu mở phạm vi **dependencies của module đang test**, không phải “mọi module nghe event của nó”.

Vì vậy hãy ghi vào phiếu bằng chứng **những listener nào thực sự tồn tại trong context**, thay vì khẳng định “đã tích hợp inventory” từ tên annotation.

## 5. Consumer module test: `Scenario` chứng minh handler, không chứng minh producer thật

Bây giờ test module `inventory`: phát trực tiếp một `OrderSubmitted` theo public contract, chờ listener thật cập nhật reservation rồi đọc state qua query API.

### 5.1. Public read model và fixture

```java
// File: com/example/shop/inventory/ReservationView.java
package com.example.shop.inventory;

import java.util.UUID;

public record ReservationView(
        UUID orderId,
        UUID sourceEventId,
        String sku,
        int quantity,
        boolean reserved) {

    public boolean matches(
            UUID expectedEventId, String expectedSku, int expectedQuantity) {
        return reserved
                && expectedEventId.equals(sourceEventId)
                && expectedSku.equals(sku)
                && quantity == expectedQuantity;
    }
}
```

```java
// File: com/example/shop/inventory/ReservationQueries.java
package com.example.shop.inventory;

import java.util.Optional;
import java.util.UUID;

public interface ReservationQueries {
    Optional<ReservationView> forOrder(UUID orderId);
}
```

```java
// File: test-support/com/example/shop/inventory/InventoryFixture.java
package com.example.shop.inventory;

public interface InventoryFixture {
    void seedStockAndCommit(String sku, int initialQuantity);
}
```

`InventoryFixture` là test infrastructure **do ứng dụng triển khai**, không phải Spring Modulith API. Implementation phải commit trước khi listener ở transaction/thread khác đọc, đồng thời cleanup dữ liệu theo test-owned SKU/order ID.

### 5.2. Test với claim và non-claims cụ thể

```java
package com.example.shop.inventory;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.UUID;

import com.example.shop.orders.events.OrderSubmitted;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.Scenario;

@ApplicationModuleTest
class InventoryConsumerModuleTests {

    @Autowired InventoryFixture fixture;
    @Autowired ReservationQueries queries;

    /**
     * CLAIM: inventory listener xử lý OrderSubmitted và tạo
     * reservation đã commit cho đúng orderId/eventId/SKU/quantity.
     * NON-CLAIMS: Không chạy OrderPlacement thật;
     * không chứng minh producer phát event hoặc broker vận chuyển.
     * GAP: OrderPublisherModuleTests và OrderToInventoryIT.
     */
    @Test
    void createsReservationForSubmittedEvent(Scenario scenario) {
        String sku = "SKU-" + UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        fixture.seedStockAndCommit(sku, 10);
        assertThat(queries.forOrder(orderId)).isEmpty();

        scenario.publish(new OrderSubmitted(
                        eventId, orderId, sku, 2))
                .andWaitAtMost(Duration.ofSeconds(8))
                .forStateChange(
                        () -> queries.forOrder(orderId),
                        value -> value.filter(
                                v -> v.matches(eventId, sku, 2))
                                .isPresent())
                .andVerify(value -> {
                    ReservationView result = value.orElseThrow();

                    assertThat(result.orderId()).isEqualTo(orderId);
                    assertThat(result.sourceEventId())
                            .isEqualTo(eventId);
                    assertThat(result.quantity()).isEqualTo(2);
                });
    }
}
```

**Được chứng minh nếu PASS:** trong test context của module `inventory`, listener và DB/query adapter phù hợp đã xử lý event do **test trực tiếp publish**, và state đọc được có đúng `sourceEventId`.

**Không được chứng minh:** `OrderPlacement.place(...)` đã publish cùng loại event; runtime app có bootstrap đúng cả hai modules; một HTTP/Kafka/RabbitMQ adapter đã truyền message; recovery qua restart; mọi listeners khác đã hoàn tất.

### 5.3. Ghi cả điều kiện transaction và reader

Nếu listener dùng `@TransactionalEventListener(phase = AFTER_COMMIT)`, publisher phải phát event trong transaction phù hợp và **commit thật**. Test-managed `@Transactional` mặc định rollback có thể làm `AFTER_COMMIT` không chạy. `Scenario.publish(...)` là công cụ publish/wait, **không miễn** hiểu transaction semantics.

Ngoài ra, supplier `() -> queries.forOrder(orderId)` phải nhìn **state committed mới**. Nếu query giữ một JPA entity được load trước stimulus trong persistence context lâu sống, polling có thể chỉ đọc state cũ.

Ghi điều kiện trong non-claims:

> PASS chứng minh state quan sát được dưới transaction/reader configuration hiện tại; không chứng minh mọi isolation level, nhiều consumer cạnh tranh hoặc durability khi database crash.

## 6. Test tích hợp hai module: đường đi thật vẫn có các giới hạn

Để lấp khoảng trống “producer và consumer có thực sự kết nối?”, dùng một integration test gọi **public command của `orders`**, cho Spring listener `inventory` xử lý, rồi quan sát reservation đã commit qua public query API. Test này không thay các transport/recovery tests nếu production còn có broker/registry.

### 6.1. Ví dụ `@SpringBootTest` + PostgreSQL Testcontainers

```java
package com.example.shop.integration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;

import com.example.shop.orders.OrderPlacement;
import com.example.shop.orders.PlaceOrderResult;
import com.example.shop.inventory.InventoryFixture;
import com.example.shop.inventory.ReservationQueries;
import com.example.shop.inventory.ReservationView;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderToInventoryIT {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderPlacement orders;
    @Autowired InventoryFixture fixture;
    @Autowired ReservationQueries reservations;

    /**
     * CLAIM: producer thật + Spring dispatch + consumer thật
     * tạo reservation trên PostgreSQL cho đúng logical event.
     * NON-CLAIMS: không chứng minh Kafka/RabbitMQ, PSP HTTP,
     * retry qua restart hoặc exactly-once toàn hệ thống.
     */
    @Test
    void connectsOrderCommandToCommittedReservation() {
        String sku = "SKU-" + UUID.randomUUID();
        fixture.seedStockAndCommit(sku, 10);

        PlaceOrderResult order = orders.place(sku, 2);

        await()
                .atMost(Duration.ofSeconds(10))
                .untilAsserted(() -> {
                    ReservationView reservation =
                            reservations.forOrder(order.orderId())
                                    .orElseThrow();

                    assertThat(reservation.orderId())
                            .isEqualTo(order.orderId());
                    assertThat(reservation.sourceEventId())
                            .isEqualTo(order.eventId());
                    assertThat(reservation.sku()).isEqualTo(sku);
                    assertThat(reservation.quantity()).isEqualTo(2);
                    assertThat(reservation.reserved()).isTrue();
                });
    }
}
```

**Điều kiện để dùng trong dự án thực:**

- Có Spring Boot application class/scan, cả hai modules cùng listener và implementation public APIs.
- `InventoryFixture` là test-support bean được đăng ký trong integration context.
- PostgreSQL driver, Testcontainers module và `spring-boot-testcontainers`/Spring Boot version hỗ trợ `@ServiceConnection`; migration tạo schema thật. Nếu không dùng service connection, cấu hình datasource qua `@DynamicPropertySource` tương ứng.
- `orders.place(...)` phải dùng transaction/commit đúng hợp đồng, nhất là khi consumer dùng `AFTER_COMMIT`.
- Không để test method `@Transactional` mặc định rollback khiến producer commit hoặc listener phase không diễn ra như production.
- Dependencies ngoài scope (PSP, email, external APIs) phải được stub ở đúng port, không mock hai modules hoặc read model đang được kiểm chứng.
- Database/container và worker lifecycle phải được quản lý phù hợp với Spring TestContext cache; một `static @Container` có thể dừng ở cuối test class trong khi context cached còn sống.
- Test data cần cleanup hoặc namespace/DB riêng sau khi async work hoàn tất.

**Kết luận hợp lệ:** trên **PostgreSQL image/test profile/test topology** đang dùng, public command và listener thực trong một Spring context đã đưa reservation tới trạng thái đúng. Bài này chứng minh transaction visibility và đường in-process trong điều kiện đó **nếu thật sự đã bootstrap/commit như mô tả**.

**Non-claims vẫn còn:** PostgreSQL 16-alpine không đại diện cho mọi cấu hình production; test không mô phỏng node crash, failover hoặc mọi isolation level; Spring event không tự đồng nghĩa Kafka/RabbitMQ delivery; một lần chờ reservation thành công không chứng minh Event Publication Registry không có incomplete publications ở target khác.

### 6.2. Đừng viết “end-to-end” mà thiếu phạm vi

Nếu hệ thống thực còn PSP, outbox, broker và notification service, bài trên chỉ là **cross-module integration in-process**, không phải E2E của toàn hạ tầng. Đặt tên báo cáo chính xác hơn: “orders→inventory in-process integration with PostgreSQL” thay vì “payment/order pipeline fully verified”.

## 7. Những non-claims thường bị bỏ sót ở architecture, transaction, registry và broker

Những test này rất có giá trị, nhưng mỗi loại chỉ nhìn thấy một tập sự kiện.

### 7.1. `ApplicationModules.verify()` bảo vệ graph, không chứng minh runtime behavior

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ShopArchitectureTests {

    /**
     * CLAIM: dependency graph không vi phạm rules đang khai báo.
     * NON-CLAIMS: không biết listener thực có được đăng ký,
     * SQL migration đúng, business event đã commit hay broker ack.
     */
    @Test
    void respectsDeclaredModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ShopApplication` là Spring Boot application class ví dụ. Để minh họa public event contract:

```java
// File: com/example/shop/orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
```

```java
// File: com/example/shop/inventory/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "orders::events")
package com.example.shop.inventory;
```

Nếu `inventory` import `orders.internal.OrderRepository`, architecture test có thể phát hiện vi phạm dưới cấu hình đúng. **Non-claim:** test này không chứng minh `OrderSubmitted` được publish hoặc `ReservationQueries` trả dữ liệu đã commit.

### 7.2. Ghi rõ điểm transaction test đã hoặc chưa quan sát

| Oracle | Chứng minh | Không chứng minh |
| --- | --- | --- |
| `repository.save(...)` được mock gọi | Use case có ý định ghi qua port | SQL thực, commit, constraint, rollback |
| `saveAndFlush(...)` trả về | SQL có thể đã được flush trong transaction | Transaction đã commit; listener thread khác nhìn thấy row |
| Query DB trong cùng transaction test | Trạng thái nhìn thấy trong transaction đó | Transaction khác có thể đọc; dữ liệu tồn tại sau rollback |
| Query từ transaction/connection mới sau commit | State đã visible theo config/isolation hiện tại | Durability khi node crash/failover hoặc mọi isolation level |
| PostgreSQL unique constraint test | Constraint trong schema/image test hoạt động | Code producer/caller luôn dùng đúng key trong mọi race |

**Điểm thực hành:** một test “DB saved” chỉ dựa vào `@Transactional` test-managed transaction có thể kết thúc bằng rollback. Nếu lời cam kết cần “after-commit event listener nhìn thấy dữ liệu”, hãy thiết kế publisher transaction commit thật và quan sát từ một reader phù hợp.

### 7.3. Event Publication Registry là bằng chứng riêng, không phải synonym với `PublishedEvents`

Spring Modulith có thể lưu tracking publication tới listener target theo provider/cấu hình. Một logical event có thể có nhiều tracked publications; completed rows có retention khác nhau.

| Tín hiệu | Ý nghĩa hợp lệ | Non-claims |
| --- | --- | --- |
| `PublishedEvents` thấy event | Event đã publish trong module test observation scope | Listener/registry target completed |
| Listener ghi business state | Consumer đã tạo state được query thấy | Mọi publication target đã completed |
| Registry không còn incomplete đúng target | Provider hiện tại không báo incomplete cho target/scope đó | Không từng fail; mọi provider hoặc restart đều an toàn |
| Listener retry cùng event và state cuối đúng | Replay trong kịch bản đã chạy đưa state về đúng | Không có double side effect ở những trường hợp chưa kiểm tra |
| Registry row đã xóa/purge | Data retention/cleanup đã xảy ra | Event chắc chắn chưa từng tồn tại hoặc chắc chắn thành công |

**Non-claim quan trọng:** một test “eventually PAID” không thể tự chứng minh listener idempotent với **lần redelivery thứ hai**. Cần chờ attempt thứ hai hoàn tất, rồi kiểm tra receipt/ledger count theo logical event ID.

### 7.4. Kafka/RabbitMQ transport khác business completion

Một Kafka producer future hoàn tất có thể cho biết record được broker xác nhận theo cấu hình producer/topic, **không có nghĩa business consumer đã xử lý và commit database**. Một RabbitMQ publish confirm không đồng nghĩa một consumer đã ack; một message được test observer nhận ở queue khác cũng không chứng minh consumer nghiệp vụ xử lý.

Ghi rõ test dùng **topic/group/offset**, **queue/routing/ack**, correlation IDs và mốc đã kiểm tra. Nếu consumer test observer dùng chung Kafka group hoặc RabbitMQ queue với business consumer, nó còn có thể **cạnh tranh nhận message**, khiến test đổi behavior của hệ thống đang đo.

### 7.5. Adapter contract vs dependency thật

HTTP stub server có thể xác minh method, URL, JSON, header idempotency, status/error translation của client thật. Nó **không** chứng minh PSP production xử lý hợp đồng như stub trên mọi tình huống, trừ khi có cơ chế contract verification/sandbox phù hợp.

Testcontainers chạy PostgreSQL/RabbitMQ/Kafka thật trong image/version được chọn, nhưng **không biến** toàn bộ environment thành production: topology, credentials, TLS, network jitter, pool size, storage durability và deployment có thể khác. Ghi version/config đã test cùng non-claims, không nói “production-like” như một bảo đảm trống.

## 8. Non-claims về thời gian: không quan sát thấy khác với không thể xảy ra

Trong async tests, một lỗi suy luận rất thường gặp:

```java
publisher.publishEvent(event);
assertThat(receipts.countFor(orderId)).isZero();
// Sai nếu dùng để kết luận listener không bao giờ ghi receipt:
// listener có thể chưa chạy hoặc đang retry.
```

Một assertion âm ở thời điểm T chỉ chứng minh **chưa thấy state đó ở mốc quan sát T**. Nó không chứng minh event **sẽ không** xuất hiện ở T+1 hoặc sau restart.

### 8.1. Cần mốc terminal của attempt trước assertion âm

Ví dụ idempotency: cùng logical event được gửi lại hai lần; muốn kết luận không có receipt trùng, cần đợi **attempt thứ hai** hoàn tất và sau đó đọc committed receipt count.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;

import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;

class PaymentRedeliveryContractIT {

    // Đây là test-support do ứng dụng tự định nghĩa.
    CommittedEventPublisher publisher;
    AttemptCompletionProbe completion;
    PaymentReceiptQueries receipts;
    PaymentFixture fixture;

    /**
     * CLAIM: sau 2 delivery attempts đã báo terminal completion,
     * cùng logical event chỉ tạo 1 receipt đã commit.
     * NON-CLAIMS: chưa kiểm tra crash giữa DB commit/ack,
     * mọi lần replay về sau, hay provider deployment khác.
     */
    @Test
    void duplicateEventDoesNotCreateDuplicateReceipt() {
        UUID orderId = fixture.createAwaitingAndCommit();
        UUID eventId = UUID.randomUUID();
        String key = "payment-" + eventId;

        PaymentCaptured event = fixture.eventFor(
                eventId, orderId, key);

        publisher.publishAndCommit(event);

        await().atMost(Duration.ofSeconds(8))
                .untilAsserted(() ->
                        assertThat(completion.completed(eventId))
                                .isGreaterThanOrEqualTo(1));

        publisher.publishAndCommit(event);

        await().atMost(Duration.ofSeconds(8))
                .untilAsserted(() ->
                        assertThat(completion.completed(eventId))
                                .isGreaterThanOrEqualTo(2));

        assertThat(receipts.countCommittedFor(key)).isEqualTo(1);
    }
}
```

**Giới hạn của ví dụ:** `CommittedEventPublisher`, `AttemptCompletionProbe`, `PaymentReceiptQueries`, `PaymentFixture` và `PaymentCaptured` thuộc ứng dụng/test harness, không phải Spring Modulith API. `completed(eventId)` phải tăng **sau** terminal processing/transaction commit theo contract; nếu probe đếm method entry thì assertion vẫn pass giả. Đường publish cần thực sự có hai delivery attempts, không bị dedup tại producer trước khi listener nhận. Với hệ thống có retry/outbox, cách kích hoạt redelivery phải đúng provider.

### 8.2. Một bounded wait vẫn chỉ chứng minh trong cửa sổ đã kiểm tra

```java
await()
    .atMost(Duration.ofSeconds(8))
    .untilAsserted(() ->
            assertThat(queries.paymentOf(orderId).orElseThrow()
                    .processedEventId())
                    .isEqualTo(eventId));
```

Bài trên chứng minh state đích đã quan sát được **trong vòng 8 giây dưới cấu hình test**, không chứng minh P99 production latency, không chứng minh không có các retry sau mốc này và không chứng minh side effects downstream hoàn tất.

Nếu timeout, ghi `lastObservedState`, event ID, attempt/registry status nếu có; **không** tự kết luận “listener chết” chỉ từ exception timeout. Lỗi có thể do publisher transaction chưa commit, reader JPA giữ snapshot cũ, DB lock, thread pool backlog hoặc registry incomplete.

### 8.3. Đừng dùng “không có lỗi” làm bằng chứng “đã cover lỗi”

Một happy-path test không chứng minh xử lý `429/503`, timeout unknown outcome, permanent business decline, invalid schema hoặc crash recovery. Muốn nói “retry đã kiểm chứng”, phải có stimulus gây failure đúng loại, oracle về số attempts/idempotency/terminal outcome và scope của transport/provider thực sự được chạy.

## 9. Biến non-claims thành artifact CI và kế hoạch lấp khoảng trống

Một phiếu non-claims chỉ hữu ích khi **truy vết được**. Gắn tên test, vùng code/config, provider/phiên bản, tầng hạ tầng, oracle và test bù trong review/CI report.

### 9.1. Evidence manifest: hiển thị PASS khác NOT_RUN

Ví dụ **mẫu report**, không phải dữ liệu CI đã chạy:

```yaml
service: SPRING_MODULITH_VERIFICATION_TESTING
scope: pull-request-482
environment:
  springBoot: "version-from-build"
  springModulith: "version-from-build"
  database: "postgres-image-and-migration-hash"
  broker: "not-provisioned"
tests:
  architecture:
    result: PASS
    claim: "declared module dependency rules hold"
  producer-module:
    result: PASS
    claim: "OrderSubmitted published with expected event ID"
  consumer-module:
    result: PASS
    claim: "inventory reservation state reached for test event"
  cross-module:
    result: NOT_RUN
    reason: "integration job not scheduled in PR lane"
  broker-transport:
    result: NOT_RUN
    reason: "broker integration only in nightly lane"
claims_not_established:
  - "orders and inventory wired together in this PR run"
  - "Kafka/RabbitMQ routing and acknowledgements"
  - "recovery after process crash or restart"
next_evidence:
  - "OrderToInventoryIT in integration gate"
  - "BrokerTransportIT in broker gate"
```

**Chính sách:** `NOT_RUN`, `SKIPPED`, `FAILED` và `PASS` là các trạng thái khác nhau. Một pipeline không được tổng hợp “tất cả integration test đã pass” khi thực tế job PostgreSQL/broker không được chạy. Nếu một gap là điều kiện bắt buộc để merge, CI phải chặn merge hoặc báo thiếu gate tương ứng.

### 9.2. Ghép claim với test bù thay vì ghi “cần thêm test” chung chung

| Claim hiện tại | Non-claim đang mở | Test bù gợi ý | Trigger chạy |
| --- | --- | --- | --- |
| Producer phát đúng event | Inventory nhận và commit | `OrderToInventoryIT` | PR liên quan event contract/wiring |
| Consumer xử lý direct event | Producer có phát đúng runtime | `OrderPublisherModuleTests` + cross-module test | PR chạm producer |
| Repository mock cập nhật state | DB constraint/migration thật | `PaymentReceiptPostgresIT` | PR chạm SQL/migration |
| HTTP adapter gọi stub thành công | PSP ngoài thực sự tương thích | Provider sandbox/contract verification | Release/integration policy |
| Registry completed một lần | Recovery sau restart và replay | Recovery/fault-injection IT | CI integration/nightly |
| Broker message được publish | Business consumer commit sau ack/retry | Consumer+state IT | Broker changes |
| Architecture graph hợp lệ | Runtime listener wiring | Module/cross-module integration | PR có event/wiring |

Cách này tạo một **danh mục bằng chứng** mà reviewer và release manager có thể dùng: một thay đổi chạm vào listener sẽ biết những bài kiểm nào cần chạy trước khi phát hành.

### 9.3. Một mutation nhỏ để kiểm tra giới hạn claim

Thử sửa code trong nhánh học tập và quan sát đúng test bị đỏ:

- **Mutation A:** đổi `OrderSubmitted.quantity` từ 2 thành 3. Producer event test phải đỏ; nếu không, oracle yếu.
- **Mutation B:** bỏ đăng ký listener `inventory`. Producer test có thể **vẫn xanh**; consumer/cross-module test phải đỏ.
- **Mutation C:** listener ghi sai `sourceEventId`. Consumer/cross-module test với correlation ID phải đỏ.
- **Mutation D:** bỏ PostgreSQL unique index. Unit Mockito có thể vẫn xanh; DB constraint test phải đỏ.
- **Mutation E:** sửa RabbitMQ routing key hoặc Kafka group. Spring in-process event tests có thể vẫn xanh; broker integration phải đỏ.
- **Mutation F:** import `orders.internal.OrderRepository` từ `inventory`. Business IT có thể vẫn xanh; architecture test phải đỏ.

Sau mỗi mutation, **hoàn nguyên** mã. Mục tiêu không phải đếm số test đỏ mà là chứng minh **sự phân công bằng chứng đúng như đã ghi trong ledger**.

### 9.4. Liên kết non-claims với ranh giới kiến trúc

`ApplicationModules.verify()` thuộc nhóm gate nhanh và độc lập Docker. Khi một test vận hành có scope nhỏ, không mở rộng module dependencies bằng cách import nội bộ module khác cho tiện assertion. Dùng named interfaces hoặc public query API; nếu cần global DB admin trong integration test, đặt ở test infrastructure với quyền sở hữu môi trường, không thêm dependency sai vào production code.

Một PR có test “green” nhưng vi phạm graph vẫn **không đạt quality gate** của học phần. Ngược lại, architecture PASS không cho phép bỏ qua non-claims về event dispatch, DB commit hoặc broker delivery.

## 10. Checklist review và bài tập ghi phạm vi chứng minh

### 10.1. Checklist dùng trước khi gọi một bài test là “đủ”

- [ ] Tên test mô tả **đúng hành vi đã quan sát**, không hứa “E2E” khi chỉ mock port?
- [ ] Có câu **CLAIM** bắt đầu bằng một hành vi cụ thể, loại stimulus và oracle?
- [ ] Có câu **NON-CLAIMS** liệt kê các mắt xích chưa chạy hoặc trạng thái chưa quan sát?
- [ ] Đã ghi SUT thật so với mocks/stubs/fakes và profile/config/DB engine thực tế?
- [ ] Có xác nhận event là Spring in-process hay đã đi qua Kafka/RabbitMQ?
- [ ] Với `PublishedEvents`, có tránh kết luận consumer/registry/broker đã hoàn tất?
- [ ] Với `Scenario`, có nêu rằng test trực tiếp publish event hay producer thật đã chạy?
- [ ] Với DB test, có phân biệt `saveAndFlush`/rollback và commit nhìn thấy từ transaction khác?
- [ ] Với `@TransactionalEventListener(AFTER_COMMIT)`, publisher có commit theo hợp đồng?
- [ ] Với `ApplicationModules.verify()`, có tránh gọi đó là runtime integration proof?
- [ ] Với broker test, có tách publish confirm, consumer ack và business state commit?
- [ ] Với registry test, có nêu event ID/target/provider/retention và phạm vi replay?
- [ ] Với assertion âm, có mốc terminal/completion trước khi nói “không có side effect”?
- [ ] Có ghi rằng một sample, một order và một seed không chứng minh mọi concurrency case?
- [ ] Có test/owner lấp non-claim quan trọng và trigger CI tương ứng?
- [ ] CI phân biệt PASS, FAIL, SKIPPED và NOT_RUN; không báo thành công giả khi thiếu integration job?
- [ ] Mỗi test dùng correlation ID/fixture mới và cleanup an toàn để không PASS nhờ dữ liệu cũ?
- [ ] Có một mutation gây lỗi ở mắt xích cần đo khiến **đúng test** đỏ?
- [ ] Secrets và dữ liệu payment thật không xuất hiện trong evidence report/logs?

### 10.2. Bài thực hành A–H

**Bài A — review một Mockito test:** nhận test chỉ làm `verify(publisher).publishEvent(...)`. Viết một CLAIM, ít nhất ba NON-CLAIMS và test bù tương ứng. Đổi tên test cho đúng mức chứng minh.

**Bài B — producer event:** triển khai `OrderPublisherModuleTests` ở mục 4. Cố ý bỏ listener inventory trong application configuration; xác định vì sao producer test có thể vẫn PASS nhưng cross-module test cần FAIL.

**Bài C — consumer event:** viết `InventoryConsumerModuleTests` dùng `Scenario`, baseline chưa có reservation và predicate đúng `sourceEventId`. Viết rõ NON-CLAIM: producer orders chưa được kiểm tra trong test này.

**Bài D — cross-module:** triển khai `OrderToInventoryIT` với Spring Boot/PostgreSQL Testcontainers. Viết hai NON-CLAIMS: không chứng minh broker ACK, không chứng minh recovery qua restart. Kiểm tra listener thật đã bootstrap.

**Bài E — transaction:** so sánh một test chỉ assert `saveAndFlush(...)` với test query từ transaction mới sau commit. Ghi rõ thay đổi trong claim; đừng dùng “persisted” như một khái niệm mơ hồ.

**Bài F — retry/idempotency:** gửi cùng logical event hai lần, chờ attempt thứ hai hoàn tất và kiểm tra count receipts là 1. Ghi giới hạn: chưa chứng minh mọi crash window hoặc retry sau restart.

**Bài G — CI manifest:** xây một report có producer PASS, consumer PASS nhưng cross-module NOT_RUN. Viết kết luận release trung thực, chỉ ra gap owner và policy cần chặn merge nếu integration bắt buộc.

**Bài H — kiến trúc:** thêm import `orders.internal` trái dependency rules trong nhánh học tập. Chứng minh `ApplicationModules.verify()` đỏ dù behavior IT có thể vẫn xanh; hoàn nguyên sau bài.

### 10.3. Tự kiểm tra ngắn, có đáp án

1. **`PublishedEvents` thấy đúng `OrderSubmitted`, ta có thể ghi “inventory đã reserve hàng” không?** Không. Chưa có consumer state oracle.
2. **Consumer `Scenario` PASS có chứng minh producer đã publish trong production?** Không. Test có thể publish event trực tiếp; cần test producer/cross-module.
3. **`@SpringBootTest` PASS nghĩa là đã dùng PostgreSQL/broker thật?** Không. Phải xem `DataSource`/client thực trỏ đâu và những bean nào đã bootstrap.
4. **`ApplicationModules.verify()` PASS có chứng minh không có lỗi serialization?** Không. Nó kiểm tra dependency graph/rules, không chạy wire protocol.
5. **Đã thấy order `PAID` thì có chứng minh idempotency của lần redelivery thứ hai?** Không. Phải chờ attempt thứ hai rồi kiểm tra side effect.
6. **Một Kafka send future thành công có chứng minh consumer đã commit DB?** Không. Broker acceptance và business commit là hai mốc khác.
7. **Một test không thấy error trong 100 ms có chứng minh lỗi không thể xảy ra?** Không. Chỉ chứng minh chưa quan sát trong cửa sổ ấy.
8. **CI báo PASS cho unit/module nhưng broker job NOT_RUN có được kết luận transport đã verify?** Không. Ghi rõ NON-CLAIM/NOT_RUN và thực hiện gate còn thiếu.
9. **Một Testcontainers test có chứng minh mọi production deployment tương thích?** Không. Kết luận chỉ theo image/config/topology đã chạy.
10. **Vì sao phải ghi cả test bù?** Để non-claims trở thành khoảng trống có người chịu trách nhiệm và có thể được đóng bằng bằng chứng thực.

### 10.4. Tài liệu tham khảo

- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `PublishedEvents` và `Scenario`.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()`, named interfaces và rules.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event publication, Event Publication Registry và retry.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener(AFTER_COMMIT)`.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): transaction scope/rollback trong test.
- [Spring Framework — TestContext Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): Spring context reuse và isolation.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): `@SpringBootTest`, test slices và test configuration.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection` và dependency thật.
- [Testcontainers for Java](https://java.testcontainers.org/): DB/broker integration environments.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): assertions, lifecycle, tags và test execution.
- [Awaitility — Usage](https://github.com/awaitility/awaitility/wiki/Usage): bounded asynchronous observations.

**Kết luận thực hành:** mỗi test nên có một **ranh giới suy luận** được ghi lại: *đã chạy thành phần nào, quan sát trạng thái gì, dưới điều kiện nào, và chưa kiểm tra những mắt xích nào*. Bài test tốt không cần khẳng định “đã chứng minh tất cả”; nó cần **khẳng định chính xác điều đã chứng minh**, chỉ ra non-claims còn mở và liên kết chúng với những phép kiểm bổ sung trong CI.
