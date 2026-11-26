# Cân bằng độ cô lập với bằng chứng tích hợp

## 1. Cân bằng là chọn đủ thành phần thật để chứng minh đúng tuyên bố

Một test chạy xanh có thể rất nhanh nhưng **không chứng minh điều bạn tưởng**. Ví dụ test service `orders` dùng mock event publisher, gọi `placeOrder(...)`, rồi `verify(publisher).publishEvent(...)`. Test đã chứng minh service **có ý định phát event**; nó chưa chứng minh Spring Modulith nhận diện đúng module, event contract công khai hợp lệ, listener `inventory` được đăng ký, hay dữ liệu tồn kho được commit.

Ngược lại, khởi động cả ứng dụng với PostgreSQL, Kafka và HTTP sandbox cho **mọi** phép kiểm “số lượng đặt phải lớn hơn 0” sẽ tốn tài nguyên, tăng số nguyên nhân thất bại và làm lỗi domain khó định vị. Đó cũng là chọn chiến lược không tốt.

Trong chương **Chọn chiến lược** của học phần `SPRING_MODULITH_VERIFICATION_TESTING`, mục tiêu là rèn cách kiểm chứng **ranh giới kiến trúc** bằng `ApplicationModules`, quy tắc phụ thuộc module và `@ApplicationModuleTest`; kiểm thử event, database và tích hợp, rồi thiết kế quality gate CI chống phụ thuộc sai/hồi quy. Vì vậy, **độ cô lập** và **bằng chứng tích hợp** là hai biến phải được tối ưu cùng lúc, không phải hai mục tiêu đối lập tuyệt đối.

Một quyết định test cần trả lời bốn câu hỏi:

1. **Tuyên bố:** Khi test PASS, nhóm phát triển được quyền kết luận chính xác điều gì?
2. **Thành phần thật:** Những phần nào **phải chạy thật** để kết luận đó không sai? Domain service, Spring event dispatcher, listener, transaction, database engine, broker hay HTTP adapter?
3. **Điểm cắt:** Những phần nào có thể thay bằng fake/mock mà **không làm mất bằng chứng thiết yếu**?
4. **Rủi ro nhiễm:** Những state nào vượt ngoài test method, như singleton Spring, transaction đã commit, Event Publication Registry, broker offsets, retry jobs hoặc container dùng chung?

### 1.1. Hai lựa chọn cực đoan đều không đủ

| Lựa chọn | Được gì | Mất gì nếu dùng không đúng |
| --- | --- | --- |
| Mock gần như mọi dependency | Test nhanh, một lỗi dễ gắn với một method | Có thể bỏ sót bean wiring, event listener, SQL mapping, module boundary, transaction |
| Chạy toàn bộ ứng dụng cho mọi assertion | Gần runtime hơn, thấy nhiều tương tác thật | Khởi động lâu, flaky do hạ tầng, khó phân biệt nguyên nhân, lỗi thường xuất hiện muộn |
| Kết hợp các test theo ranh giới chứng cứ | Lỗi định vị gần nguồn, vẫn kiểm tra đường tích hợp quan trọng | Cần nêu rõ **mỗi test bảo vệ hợp đồng nào** và duy trì các lớp bằng chứng |

**Quy tắc hành động:** chỉ kéo thêm một thành phần thật vào test nếu có **một loại lỗi cụ thể** mà test hiện tại chưa thể phát hiện. Nếu không thể nêu loại lỗi đó, cân nhắc giữ test ở scope nhỏ.

## 2. Lập bản đồ “bằng chứng → phạm vi” trước khi chọn annotation

Không nên phân loại chỉ bằng tên test `unit`/`integration`; phải đối chiếu **hợp đồng cần kiểm chứng**.

| Tuyên bố cần chứng minh | SUT thật tối thiểu | Thứ có thể cô lập | Bằng chứng hợp lệ | Bằng chứng còn thiếu |
| --- | --- | --- | --- | --- |
| Kiểm tra quantity dương | Domain policy | Tất cả adapter | Input bị từ chối với exception/domain result đúng | Spring wiring, DB, event |
| Use case phát đúng `OrderSubmitted` | Order service + Spring event publisher | External payment/notification port | `PublishedEvents` đúng event ID, order ID và payload | Listener inventory nhận và commit |
| Inventory listener cập nhật reservation từ event | Listener + repository/query + transaction | Producer orders; external gateway | `Scenario` chờ đúng reservation state | Producer thật phát đúng contract |
| Orders thực sự nối được với inventory | Producer + Spring dispatcher + consumer + DB | External PSP/email, nếu ngoài mục tiêu | Gọi producer public API, thấy reservation cùng correlation ID | Broker adapter nếu luồng chỉ là Spring event |
| PostgreSQL unique constraint được áp dụng | DB migration + SQL adapter | HTTP/broker | Insert trùng bị từ chối trong PostgreSQL thật | Use case orchestrate đúng |
| Kafka/RabbitMQ vận chuyển event đúng | Producer/consumer adapter + broker | Các module không liên quan | Topic/queue/group/routing/ack và payload đúng | Hợp đồng domain của cả workflow nếu chỉ test transport |
| Modules tuân thủ dependency rules | `ApplicationModules` trên application class | DB, HTTP, broker | `verify()` PASS và mutation trái boundary FAIL | Runtime event, transaction và network |
| Recovery từ incomplete event publication | Registry provider + storage + retry/listener | Adapter ngoài không liên quan | Publication đúng event/target được hoàn tất hoặc retry hợp đồng | Bản triển khai ở provider khác nếu không được chạy |

Từ bảng này, dựng **danh mục bằng chứng** (*evidence portfolio*) thay vì viết nhiều bài test cùng assert một trạng thái và bỏ trống transaction/broker.

### 2.1. Ba trục chọn phạm vi

**Trục kiến trúc:** chỉ một module, module và direct dependencies, hay nhiều module thực sự giao tiếp?

**Trục hạ tầng:** object local/fake, Spring context và database nhẹ, hay database/broker/API thật?

**Trục vòng đời:** phép kiểm đồng bộ trong method, hay có after-commit, `@Async`, registry retry hoặc redelivery có thể tiếp tục sau method?

Một test có thể **module-scoped nhưng dùng PostgreSQL thật**, hoặc **multi-module nhưng mock PSP bên ngoài**. Không đánh đồng “có Testcontainers” với “đã tích hợp đủ module”, hay “dùng `@SpringBootTest`” với “đã có DB/broker thật”.

### 2.2. Điểm cắt phải tôn trọng kiến trúc

Mock port tới dependency ngoài module; đừng mock chính listener, event bus hoặc repository nếu chúng là **hành vi được kiểm tra**. Nếu chọn stub cho module khác trong test cô lập producer, vẫn cần một test khác xác minh contract giao tiếp thực giữa hai module. Không tạo import từ `inventory.internal` sang `orders` chỉ để “dễ setup fixture”.

## 3. Một luồng mẫu dùng chung cho ba mức kiểm thử

Xét ứng dụng có hai module:

- **`orders`:** nhận lệnh đặt hàng, lưu order và công bố Spring application event `OrderSubmitted`.
- **`inventory`:** lắng nghe `OrderSubmitted`, giữ hàng và ghi reservation trong transaction riêng; cung cấp public query API cho người dùng/đối tác đọc.
- **Dependency ngoài:** email/PSP/broker adapter có thể tồn tại, nhưng **không là trọng tâm** khi chỉ kiểm tra handoff nội bộ orders → inventory.

Hợp đồng kiểm chứng là:

> Khi lệnh đặt hàng hợp lệ được commit, inventory phải tạo **đúng reservation cho order/event đó**, với SKU và quantity phù hợp, và không được lấy state tồn dư của scenario trước làm kết quả.

### 3.1. Event contract và public API minh họa

Các kiểu dưới đây **do ứng dụng ví dụ tự định nghĩa**, không phải Spring Modulith tạo sẵn. Mỗi kiểu `public` cần đặt vào file Java riêng như phần chú thích.

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

```java
// File: com/example/shop/inventory/ReservationView.java
package com.example.shop.inventory;

import java.util.UUID;

public record ReservationView(
        UUID orderId,
        UUID sourceEventId,
        String sku,
        int reservedQuantity,
        boolean reserved) {

    public boolean matches(
            UUID expectedEventId,
            String expectedSku,
            int expectedQuantity) {

        return reserved
                && expectedEventId.equals(sourceEventId)
                && expectedSku.equals(sku)
                && reservedQuantity == expectedQuantity;
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

`PlaceOrderResult` có `eventId` để bài kiểm thử tích hợp truy vết **đúng logical event**. Đây là lựa chọn thiết kế minh họa; dự án khác có thể dùng correlation ID từ command/API hoặc một cách quan sát event đã publish, không buộc mọi use case production phải công khai UUID event.

### 3.2. Công bố boundary qua named interface

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

`inventory` chỉ được dựa vào event contract công khai, không import repository hay entity nội bộ của `orders`. Nếu module còn phụ thuộc interface công khai khác, danh sách `allowedDependencies` thực tế phải khai báo đúng tất cả dependency hợp lệ; ví dụ này giả định chỉ có dependency nêu trên.

Trong implementation thực tế, một listener có thể dùng `@TransactionalEventListener(phase = AFTER_COMMIT)` hoặc listener đồng bộ theo thiết kế. Các test dưới đây **không giả định** mọi loại listener có cùng transaction semantics.

### 3.3. Ba phép kiểm phải có ba kết luận khác nhau

1. **Producer module test:** có phát event đúng payload hay không?
2. **Consumer module test:** khi nhận event hợp lệ, inventory có ghi state đúng không?
3. **Cross-module integration test:** khi đi qua producer thật và Spring dispatch, inventory có nhận/commit đúng không?

Một bộ chỉ có (1) và (2) vẫn có thể bỏ sót lỗi wiring, event listener registration hoặc producer gọi sai overload/loại event. Bộ chỉ có (3) thì lỗi dễ khó khoanh vùng: listener, producer, DB, transaction, config và hạ tầng cùng nằm trong một lần chạy.

## 4. Test producer cô lập: giữ Spring event publication thật, không kéo toàn inventory vào

Trong bài `orders`, ta chỉ muốn chứng minh **lệnh đặt hàng phát đúng event**. Test `@ApplicationModuleTest` chạy module producer và quan sát `PublishedEvents`, không cần bootstrap cả `inventory`.

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

    @Test
    void publishesOneEventForThePlacedOrder(
            PublishedEvents events) {

        String sku = "SKU-" + UUID.randomUUID();
        PlaceOrderResult placed = orders.place(sku, 2);

        assertThat(placed.orderId()).isNotNull();
        assertThat(placed.eventId()).isNotNull();

        var published = events.ofType(OrderSubmitted.class)
                .matching(OrderSubmitted::eventId, placed.eventId());

        assertThat(published).hasSize(1);

        OrderSubmitted event = published.iterator().next();

        assertThat(event.orderId()).isEqualTo(placed.orderId());
        assertThat(event.sku()).isEqualTo(sku);
        assertThat(event.quantity()).isEqualTo(2);
    }
}
```

Ở ví dụ này, `OrderPlacement` cần implementation thật đã được bean-scan trong module, và repository/test datasource phù hợp. Không tự mock `OrderPlacement` hoặc `ApplicationEventPublisher` khi muốn kiểm chứng Spring publication thật. Tên API `PublishedEvents` lấy theo Spring Modulith test support; xác minh dependency/version chính xác trong dự án khi triển khai.

**Bằng chứng sau PASS:** từ public command của module `orders`, một `OrderSubmitted` với correlation/aggregate/payload mong đợi đã được publish trong Spring test context.

**Không được kết luận:** inventory listener đã chạy, reservation đã commit, Event Publication Registry completed, RabbitMQ/Kafka đã nhận message, hay có idempotency khi broker redelivery.

### 4.1. Vì sao không dùng `@SpringBootTest` cho mọi producer event test?

Nếu chỉ kiểm tra publication payload, khởi tạo toàn bộ `inventory` cùng email/PSP adapter có thể làm test fail vì dependency ngoài **không liên quan** tới tuyên bố. Module scope giúp lỗi được khoanh gần code publisher và chạy nhanh hơn.

Nếu producer phụ thuộc PSP, có thể thay **external port** bằng `@MockitoBean` trong test configuration tương thích Spring Framework/Boot; không thay Spring publisher thật bằng mock. Mock port dùng ở đây để **cắt nhiễu**, không để diễn giải sai rằng giao thức PSP đã được kiểm chứng.

### 4.2. Khi nào một producer module test vẫn cần DB thật?

Nếu test có yêu cầu “sự kiện chỉ được phát khi **order transaction commit**”, database/transaction semantics có thể là một phần chứng cứ. Chọn DB phù hợp với mục tiêu; một in-memory database không luôn có cùng isolation/locking hoặc SQL dialect với production PostgreSQL.

Nhưng nếu test chỉ assert số lượng và payload publication, dùng cả broker và HTTP service thật thường không tăng nhiều bằng chứng.

## 5. Test consumer cô lập: chạy listener thật và chờ state qua `Scenario`

Khi mục tiêu là **inventory xử lý event**, không cần đặt hàng qua producer `orders` thật. Test có thể publish một event contract trực tiếp, giữ listener và persistence/query của `inventory` thật, rồi chờ state bằng `Scenario`.

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
class InventoryEventConsumerModuleTests {

    @Autowired InventoryFixture fixture;
    @Autowired ReservationQueries reservations;

    @Test
    void reservesExactlyForTheSubmittedEvent(Scenario scenario) {
        String sku = "SKU-" + UUID.randomUUID();
        UUID orderId = UUID.randomUUID();
        UUID eventId = UUID.randomUUID();

        // Test-support do inventory sở hữu: tạo stock và commit.
        fixture.createStockAndCommit(sku, 10);

        assertThat(reservations.forOrder(orderId)).isEmpty();

        scenario.publish(
                    new OrderSubmitted(eventId, orderId, sku, 2))
                .andWaitAtMost(Duration.ofSeconds(8))
                .forStateChange(
                        () -> reservations.forOrder(orderId),
                        value -> value.filter(
                                view -> view.matches(eventId, sku, 2))
                                .isPresent())
                .andVerify(value -> {
                    ReservationView reserved = value.orElseThrow();

                    assertThat(reserved.orderId()).isEqualTo(orderId);
                    assertThat(reserved.sourceEventId())
                            .isEqualTo(eventId);
                    assertThat(reserved.sku()).isEqualTo(sku);
                    assertThat(reserved.reservedQuantity())
                            .isEqualTo(2);
                });
    }
}
```

`InventoryFixture` là test fixture **do dự án cung cấp**, cần là bean phù hợp với module test, chẳng hạn:

```java
// Test-support API minh họa, không phải Spring Modulith API.
package com.example.shop.inventory;

public interface InventoryFixture {
    void createStockAndCommit(String sku, int quantity);
}
```

Test này yêu cầu listener `inventory` thực sự nhận `OrderSubmitted`, có repository/query adapter, DB/test transaction và stock fixture commit. Dự án cần định nghĩa cách cleanup theo SKU/order/event ID; không dùng `deleteAll()` toàn DB khi test song song.

**Bằng chứng sau PASS:** listener thật trong module `inventory` xử lý đúng event và đưa public state tới reservation mong đợi.

**Không được kết luận:** producer `orders` thực sự publish event; producer/consumer modules có được khởi động cùng nhau trong runtime không; broker adapter có serialize/route đúng; hoặc mọi retry đã hoàn tất.

### 5.1. Chi tiết transaction có thể biến test xanh thành fail giả

Một listener dùng `@TransactionalEventListener(AFTER_COMMIT)` chỉ thực hiện theo phase khi event được phát trong transaction phù hợp **và transaction đó commit**. Nếu test phát event trong một test-managed `@Transactional` mặc định rollback, `AFTER_COMMIT` sẽ không chạy như mong đợi. Ngược lại, publish ngoài transaction hoạt động ra sao phụ thuộc cấu hình listener như `fallbackExecution` và đường code thực.

Vì vậy cần xây đường stimulus có **publisher transaction commit thật** khi listener contract đòi after-commit. `Scenario.publish(...)` là API tiện lợi để diễn đạt kích hoạt/chờ nhưng **không thay thế việc hiểu transaction của producer/listener**. Trong test triển khai, nếu cấu hình listener cần transaction, hãy cho một command/transactional fixture publish và commit đúng như ứng dụng. Không chữa timeout bằng một `Thread.sleep(...)` hoặc tăng chờ vô hạn.

### 5.2. Điều kiện để một predicate đáng tin

- Đọc trạng thái bằng `ReservationQueries.forOrder(orderId)` qua một reader thấy **committed data mới**, không reuse JPA entity cached.
- Lọc theo `sourceEventId` để không pass nhờ reservation của scenario trước.
- Assert SKU và quantity, không chỉ `reserved == true`.
- Đặt timeout hữu hạn để có dấu vết lỗi.
- Nếu listener còn tạo side effect sau commit state, chờ completion của side effect đó **trước cleanup**; state đạt đích không chứng minh mọi công việc đã kết thúc.

## 6. Cross-module integration: gọi producer thật và quan sát consumer thật

Hai bài test ở mục 4–5 chưa chứng minh rằng **wiring thật** kết nối hai module. Ta cần một bài kiểm chứng thêm đường đi:

```text
OrderPlacement.place(...)
    ├── Orders repository COMMIT
    └── OrderSubmitted được publish đúng phase
          └── Inventory listener được đăng ký thật
                └── Inventory reservation COMMIT
                      └── ReservationQueries thấy đúng eventId
```

Một integration test có thể bootstrap những module cần thiết qua cấu hình tích hợp được kiểm soát; ví dụ dưới đây dùng `@SpringBootTest` trên ứng dụng minh họa, đồng thời PostgreSQL Testcontainers để có transaction/schema thật.

### 6.1. JUnit + Spring Boot + PostgreSQL: bằng chứng từ lệnh đến read model

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
class OrderToInventoryIntegrationIT {

    @Container
    @ServiceConnection
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderPlacement orders;
    @Autowired InventoryFixture fixture;
    @Autowired ReservationQueries reservations;

    @Test
    void producerAndConsumerAgreeOnTheSameLogicalEvent() {
        String sku = "SKU-" + UUID.randomUUID();
        int requested = 2;

        // Tạo tồn kho riêng, transaction fixture đã COMMIT.
        fixture.createStockAndCommit(sku, 10);

        // Public API thật phát event khi transaction commit.
        PlaceOrderResult placed = orders.place(sku, requested);

        await()
                .atMost(Duration.ofSeconds(10))
                .untilAsserted(() -> {
                    ReservationView result =
                            reservations.forOrder(placed.orderId())
                                    .orElseThrow();

                    assertThat(result.orderId())
                            .isEqualTo(placed.orderId());
                    assertThat(result.sourceEventId())
                            .isEqualTo(placed.eventId());
                    assertThat(result.sku()).isEqualTo(sku);
                    assertThat(result.reservedQuantity())
                            .isEqualTo(requested);
                    assertThat(result.reserved()).isTrue();
                });
    }
}
```

**Phạm vi và điều kiện thực thi:**

- Class `OrderPlacement`/`PlaceOrderResult`/`ReservationQueries` cùng listener, fixture và migration phải được ứng dụng thật triển khai. `InventoryFixture` là test-support bean thuộc `inventory` (package/import có thể điều chỉnh cho project).
- `@SpringBootTest` cần Spring Boot application class và bean graph hợp lệ; external adapter ngoài phạm vi (PSP/email) cần test profile/stub/fake **đúng port** nếu chúng cản trở khởi động hoặc tạo side effect ngoài ý muốn.
- `@ServiceConnection` phụ thuộc Spring Boot hỗ trợ Testcontainers connection details và dependency tương thích, gồm `spring-boot-testcontainers`, module Testcontainers PostgreSQL, JDBC driver và Docker runtime test. Với stack khác, `@DynamicPropertySource` có thể cấu hình datasource thay thế.
- PostgreSQL image cần đi kèm migration/schema thật. Chỉ khai báo container không chứng minh migration đã chạy.
- Test method **không** đánh dấu `@Transactional` rollback, vì listener `AFTER_COMMIT` và reader ở transaction khác có thể cần commit thực của `orders.place(...)`.
- `orders.place(...)` cần phát event đúng phase; transaction callback thực sự hoàn tất trước khi kết luận về consumer.
- Dùng timeout hữu hạn với Awaitility; không `Thread.sleep(...)`, không đọc một entity cached trước stimulus.

**Bằng chứng sau PASS:** public command từ module producer, Spring event dispatch/listener consumer và PostgreSQL persistence hoạt động cùng nhau để tạo **đúng reservation của event đã phát**.

**Không được kết luận:** RabbitMQ/Kafka routing đã đúng nếu event này chỉ đi qua Spring application event; HTTP PSP thực chạy; registry replay/idempotency khi consumer fail; hoặc cleanup của toàn bộ suite.

### 6.2. Vì sao không dựa vào `BootstrapMode.ALL_DEPENDENCIES` một cách máy móc?

`@ApplicationModuleTest` có các bootstrap modes như `STANDALONE`, `DIRECT_DEPENDENCIES` và `ALL_DEPENDENCIES`. Các mode mở rộng **dependency của module test**; chúng không mặc nhiên có nghĩa sẽ khởi động mọi **consumer downstream** mà module hiện tại phát event tới. Nếu `inventory` phụ thuộc `orders.events`, test `orders` với `ALL_DEPENDENCIES` không thể tự được coi là test của cả `inventory`.

Với mục tiêu liên module, phải xác định bean/module nào thực sự được bootstrap. Có thể dùng một integration slice có các module yêu cầu hoặc `@SpringBootTest` nếu phù hợp; không chỉ nhìn tên annotation để suy rằng toàn bộ chain đã chạy.

### 6.3. Context cache và Testcontainers lifecycle

`static @Container` do JUnit Testcontainers extension quản lý thường có vòng đời theo **test class**. Spring TestContext có thể cache `ApplicationContext` và `DataSource` qua nhiều classes. Nếu context được reuse sau khi container nguồn đã dừng, datasource có thể trỏ endpoint không còn sống.

Bài kiểm chứng này cần chọn cách tổ chức container/context phù hợp: suite/context-scoped container, test configuration tách biệt, hoặc evict context có chủ đích khi resource thật đã hết lifetime. Đừng dùng `@DirtiesContext` vô điều kiện cho mọi method, và cũng đừng gọi container start/stop trong test body khi client/listerners còn dùng.

## 7. Tăng hạ tầng thật ở đúng rủi ro: database, broker, registry và contract

Không phải mọi integration test đều cần tất cả dependency thật. Hãy chọn theo **bug có thể lọt nếu dùng substitute**.

| Rủi ro không muốn lọt | Điểm cắt đang quá cao | Thử nghiệm bổ sung cần có |
| --- | --- | --- |
| Migration thiếu unique constraint; dialect khác PostgreSQL | Repository mock/H2 | DB adapter/integration dùng PostgreSQL container, migration thật |
| Publisher transaction rollback làm listener `AFTER_COMMIT` không chạy | Mock event publisher | Spring integration với transaction commit và listener thật |
| Consumer insert đúng nhưng transaction bị rollback | Mock repository hoặc state in-memory | DB integration + reader thấy committed state |
| Event Publication Registry lưu incomplete publication và resubmit sai | Mock listener/registry | Provider storage thật, failure injection và recovery theo event/target |
| RabbitMQ exchange/binding/routing/ack sai | Mock sender | RabbitMQ container và queue riêng cho transport test |
| Kafka consumer group/offset/rebalance/DLT sai | Fake in-memory bus | Kafka integration với topic, group và correlation ID |
| HTTP adapter serialize sai field hoặc xử lý 409 sai | Mock port caller | HTTP stub server xác minh method/header/body/status |
| PSP/remote sandbox xử lý nghiệp vụ khác giả định | Stub quá đơn giản | Sandbox/contract integration job riêng, không dùng production accounts |
| Cross-module event type/package sai | Producer và consumer được test trực tiếp, riêng | Cross-module integration thật + `ApplicationModules.verify()` |

### 7.1. Giá trị của mock phụ thuộc vị trí mock

Mock `PaymentGateway` khi test quy tắc “PSP từ chối → order không PAID” là hợp lý nếu hợp đồng đã rõ. Mock `ApplicationEventPublisher` **trong bài đang kiểm chứng publisher/consumer integration** sẽ phá điều cần chứng minh. Mock `ReservationQueries` rồi `when(...).thenReturn(reserved)` trong cross-module integration còn nguy hiểm hơn: test có thể PASS dù listener không ghi DB.

**Đặt mock sau ranh giới bằng chứng**, không đặt nó vào chính mắt xích mà test đang tuyên bố hoạt động.

### 7.2. Một adapter contract test có thể rẻ hơn cả hệ thống thật

Để chứng minh HTTP client gửi idempotency header và JSON đúng, HTTP stub server có kiểm tra request thường đủ; không nhất thiết cần PSP sandbox và network. Nhưng nếu production correctness phụ thuộc PostgreSQL lock, mock JDBC không tái hiện được. Vì vậy “integration evidence” là **chọn thực thi phần có semantics quan trọng**, không phải đồng nghĩa “mọi dependency phải thật”.

### 7.3. Event Publication Registry là một chiều bằng chứng riêng

Spring Modulith có thể tracking publication theo listener target và provider. Một event có thể tạo nhiều tracked publications và completed retention khác nhau tùy provider. `PublishedEvents` cho thấy event đã publish; reservation read model cho thấy business state; registry provider kiểm chứng incomplete/completed và replay.

Một recovery test có thể cố ý giữ publication incomplete qua restart, rồi resubmit **cùng logical event**, xác minh idempotency và completion. Hãy cấp registry database/schema riêng cho nhóm này để retry worker không quét publication của test khác. Không kết luận “registry sạch” chỉ từ `PublishedEvents` hoặc `reservation.reserved()`.

## 8. Giữ isolation khi tăng phạm vi: tránh PASS giả và flaky

Càng nhiều thành phần thật, càng nhiều state nằm ngoài test method. **Integration test mạnh về bằng chứng chỉ khi dữ liệu và điểm quan sát thuộc chính scenario**.

### 8.1. Ma trận state vượt scope

| State | Nguy cơ khi dùng chung | Biện pháp |
| --- | --- | --- |
| Spring singleton fake/recorder | Event của test trước còn trong list | Per-test recorder hoặc filter correlation ID |
| Cached `ApplicationContext` | Listener/bean mock đã bị test khác mutate/stop | Không stop production bean; config/ownership phù hợp |
| PostgreSQL committed rows | Lượt sau thấy SKU/reservation cũ | ID/SKU riêng, cleanup theo scope hoặc schema riêng |
| Database transaction | Listener async không thấy fixture chưa commit | Commit fixture trước publish; reader fresh |
| Event Publication Registry | Incomplete event cũ bị retry trong test mới | Provider-aware isolation/recovery suite riêng |
| Kafka topic/group/offset | Observer đọc message cũ hoặc tranh partition | Topic/group riêng; chờ assignment; filter event ID |
| RabbitMQ queue/ack/DLQ | Redelivery message cũ, competing consumers | Queue observer riêng; xử lý ack/retry đúng scope |
| Executor/scheduler | Task từ test A còn chạy khi B cleanup | Completion/quiescence trước teardown |
| Testcontainers | Context giữ client tới container đã dừng | Lifecycle context/container tương thích |
| Static JVM state | Cache/clock/ThreadLocal rò giữa methods | Object local/immutable, `ThreadLocal.remove()` ở worker |

### 8.2. Ba loại false positive cần thử phá

**PASS giả vì state cũ:** assertion `findAnyReserved()` có thể pass nhờ reservation của test khác. Sửa bằng `forOrder(orderId)` và kiểm tra `sourceEventId`.

**PASS giả vì mock:** test cấu hình `ReservationQueries` mock trả `Optional.of(reserved)` rồi kết luận listener đã commit. Sửa bằng query adapter thật cùng database thật khi persistence thuộc phạm vi.

**PASS giả vì async chưa chạy:** test publish event rồi assert “không có receipt trùng” ngay. Listener thứ hai có thể chưa chạy. Cần chờ completion của **attempt thứ hai** trước khi assert bất biến âm.

### 8.3. Cleanup phải chờ đúng terminal signal

Nếu listener đã commit reservation nhưng còn publish `StockReserved` hoặc đánh dấu registry completed, việc quan sát `reserved == true` chưa chắc đủ để dọn broker/registry. Resource nào được cleanup thì phải chờ **phần công việc tương ứng** đã hoàn tất hoặc đã được cô lập an toàn.

Tránh `Thread.sleep(1000)` và global `deleteAll()`. Với test timeout khi worker còn sống, không dọn dữ liệu dùng chung trước khi quiescent; ghi lỗi và có thể hủy môi trường test riêng sau khi worker/consumer đã stop.

### 8.4. Chạy song song phải xét cả bên ngoài JVM

JUnit `@ResourceLock` giúp phối hợp các test trong phạm vi scheduler; nó không khóa hai Gradle JVM forks, hai CI agents hoặc một Kafka consumer ở process khác. Database/queue/topic namespace và lifecycle thực mới là ranh giới cho cross-process isolation.

## 9. Thiết kế quality gate theo “bằng chứng không trùng, lỗ hổng không bỏ sót”

Không nên lấy tỷ lệ test integration cao làm thước đo chất lượng. Hãy xây một **evidence portfolio** cho đường đi có rủi ro, với từng test trả lời **một câu hỏi khác biệt**.

| Gate | Test tối thiểu | Bắt lỗi gì? | Thời điểm khuyến nghị |
| --- | --- | --- | --- |
| **Architecture** | `ApplicationModules.of(...).verify()` | Import nội bộ, cycles, sai `allowedDependencies` | Mọi PR, rất sớm |
| **Domain** | Unit test OrderPlacement policy/stock rule | Invariant, input invalid | Mọi PR, nhanh |
| **Producer module** | `@ApplicationModuleTest` + `PublishedEvents` | Missing/wrong event, sai payload | Mọi PR |
| **Consumer module** | `@ApplicationModuleTest` + `Scenario` | Listener không đổi state, sai mapping | Mọi PR nếu ổn định |
| **Cross-module** | Public command → real listener → public query | Wiring/commit giữa orders và inventory | Mọi PR hoặc nhóm integration chính |
| **DB semantics** | PostgreSQL migration/constraint/locking | Unique/transaction/dialect bugs | Integration gate |
| **Adapter contract** | HTTP stub hoặc serializer test | Header/status/JSON drift | Khi adapter thay đổi, ideally mọi PR |
| **Broker** | Kafka/RabbitMQ real topology | Routing/offset/ack/retry | Integration gate phù hợp |
| **Registry recovery** | Incomplete publication → retry → completed | Durability/replay/idempotency | Job tích hợp riêng nếu tốn thời gian |
| **Isolation/repeatability** | Rerun, random order, parallel subset | Test pollution, race, cleanup | PR có chọn lọc + nightly/stress |

Cách xác định “đủ bằng chứng”: với mỗi failure mode rủi ro cao, phải chỉ ra **test nào sẽ đỏ nếu lỗi xuất hiện**, và vì sao nó không bị một mock che mất.

### 9.1. Kiểm thử mutation trong nhánh học tập

Không cần chạy chaos tooling phức tạp để biết một bài test có giá trị:

- **Mutation A:** đổi `OrderSubmitted.quantity` từ 2 thành 3 khi publish. Producer module test phải đỏ.
- **Mutation B:** không đăng ký listener inventory trong context cross-module. Producer module test vẫn có thể xanh, nhưng cross-module integration phải đỏ.
- **Mutation C:** listener lưu `sourceEventId` sai. Consumer/module hoặc integration state-specific assertion phải đỏ.
- **Mutation D:** bỏ unique index trên DB. Unit mock có thể xanh; PostgreSQL constraint test phải đỏ.
- **Mutation E:** đổi Kafka consumer group/AMQP routing key. Spring application-event module tests có thể xanh, broker integration test cần đỏ.
- **Mutation F:** import `orders.internal.OrderRepository` trong inventory. Business integration có thể xanh, architecture gate phải đỏ.

Đó là cách kiểm tra trực tiếp xem **mỗi tầng có đúng nhiệm vụ**. Tất cả mutation chỉ thực hiện trên nhánh học tập rồi hoàn nguyên, không để lỗi cố ý trong production.

### 9.2. Ngân sách thời gian và môi trường CI

Một nguyên tắc vận hành:

1. Chạy **architecture/unit** trước, không cần Docker.
2. Chạy **module tests** với phạm vi Spring nhỏ và fixture hợp đồng rõ.
3. Chạy một số **cross-module smoke paths** có giá trị cao với DB thật nếu transaction/schema là rủi ro.
4. Chạy **adapter/broker/recovery tests** theo suite riêng có resource ownership, namespace và startup budget.
5. Chạy random order/parallel stress ở nhóm đủ cô lập; lưu seed, correlation IDs, transaction/ack timeline khi lỗi.
6. Không bỏ qua test hạ tầng do Docker thiếu rồi báo chung là “mọi integration tests PASS”; trạng thái NOT_RUN/FAILED phải rõ.
7. Nếu một test flaky, phân biệt lỗi data isolation, async tail, connection pool, broker group hoặc context/container lifecycle trước khi tăng timeout.

Test integration được chọn ít hơn nhưng **oracle mạnh, deterministic và tái hiện được** thường có giá trị hơn một danh sách dài test khởi động toàn ứng dụng rồi chỉ assert HTTP 200.

### 9.3. Architecture gate độc lập với hạ tầng

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ShopModuleArchitectureTests {

    @Test
    void keepsDependenciesWithinDeclaredBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`ShopApplication` là class ứng dụng Spring Boot ví dụ. Test này không cần PostgreSQL/broker để xác minh dependency graph. Nó **không tự phát hiện** listener chưa nhận event, migration thiếu hay transaction visibility sai; các test hành vi bổ sung chứng cứ đó.

## 10. Checklist đánh giá chiến lược và bài tập tự kiểm tra

### 10.1. Checklist chọn scope trước khi viết test

- [ ] Tôi đã viết được **một câu tuyên bố** test cần bảo vệ?
- [ ] Có nêu rõ loại bug cụ thể mà mock/module test hiện tại sẽ bỏ sót?
- [ ] Thành phần **đang được xác minh** có chạy thật, thay vì bị mock ngay trong SUT?
- [ ] Boundary thay bằng fake/mock là external port hoặc thành phần ngoài trách nhiệm test?
- [ ] Producer event test có dùng `PublishedEvents` với event ID/payload đúng?
- [ ] Consumer test có listener và state query thật, dùng `Scenario` với predicate theo event/aggregate ID?
- [ ] Cross-module test có thực sự bootstrap cả producer và consumer, không chỉ `ALL_DEPENDENCIES` theo phỏng đoán?
- [ ] Nếu cần after-commit listener, transaction publisher/fixture đã commit thực?
- [ ] Reader có thấy state đã commit mới, không reuse JPA entity cached?
- [ ] Nếu dùng DB thật, migration/dialect/constraint cần kiểm chứng có thực sự chạy?
- [ ] Nếu dùng Kafka/RabbitMQ thật, topic/queue/group/ack/routing đúng và observer không tranh consumer nghiệp vụ?
- [ ] Event Publication Registry và business state được kiểm chứng riêng theo hợp đồng?
- [ ] Có cleanup theo ID/namespace sau quiescence, không global purge resource dùng chung?
- [ ] Testcontainers và Spring TestContext cache có lifecycle tương thích?
- [ ] Test vẫn PASS khi chạy lại, đổi thứ tự hoặc chạy song song **trong phạm vi đã cam kết**?
- [ ] `ApplicationModules.verify()` vẫn bảo vệ package `internal`/named interfaces?
- [ ] CI phân biệt test PASS với integration suite chưa chạy do thiếu Docker/migration?
- [ ] Có một mutation nhỏ khiến đúng test tầng tương ứng đỏ?

### 10.2. Bài tập A–H

**Bài A — lập bản đồ bằng chứng:** với luồng orders → inventory, viết ba câu “producer phát đúng event”, “consumer xử lý đúng event” và “hai module kết nối thật”. Chỉ định **một oracle khác nhau** cho từng câu. Không dùng cùng một mock để tự chứng minh cả ba.

**Bài B — producer module:** triển khai `OrderPublisherModuleTests`, sửa tạm `quantity` event khác request. Xác nhận `PublishedEvents` assertion đỏ. Giữ inventory ngoài scope.

**Bài C — consumer module:** cho `InventoryEventConsumerModuleTests` nhận `OrderSubmitted` với event ID mới. Thử listener ghi `sourceEventId` cố định; predicate phải fail. Kiểm tra fixture stock đã commit và reader fresh.

**Bài D — wiring tích hợp:** chạy `OrderToInventoryIntegrationIT`. Tạm vô hiệu hóa consumer listener trong test configuration; module producer vẫn có thể PASS, integration phải FAIL. Trả listener về đúng cấu hình.

**Bài E — chứng cứ hạ tầng:** mock repository thì unique key vẫn có thể trả success. Bổ sung PostgreSQL Testcontainers với migration thật để xác nhận duplicate key bị từ chối. Không cần broker thật cho phép kiểm này.

**Bài F — ranh giới transport:** giả định orders gửi Kafka thay vì Spring application event. So sánh một `@ApplicationModuleTest` publish in-process với broker integration kiểm tra group/offset; giải thích vì sao cái trước không chứng minh cái sau.

**Bài G — transaction và retry:** tạo listener `AFTER_COMMIT`, dùng test-managed `@Transactional` rollback. Quan sát listener không chạy như kỳ vọng; sửa publisher stimulus để commit đúng. Sau đó thử incomplete registry publication trong storage riêng, chờ replay và idempotency.

**Bài H — CI quality gate:** chia danh mục kiểm thử thành architecture/unit, module producer/consumer, cross-module, adapter, broker/registry. Cho mỗi nhóm một failure mode và một mutation làm test đỏ. Chỉ tăng scope nếu có khoảng trống bằng chứng.

### 10.3. Tự kiểm tra nhanh, kèm đáp án

1. **Producer module test PASS có chứng minh inventory đã reserve hàng?** Không; nó chỉ chứng minh publication theo hợp đồng test. Cần consumer state hoặc cross-module integration.
2. **Consumer test nhận event trực tiếp có chứng minh producer phát event đúng runtime?** Không; producer cần test riêng và một test nối thực sự.
3. **`@SpringBootTest` luôn có nghĩa là DB và broker production-like?** Không; nó bootstrap Spring context, còn dependency có thật hay không do cấu hình/adapters.
4. **`@ApplicationModuleTest(mode = ALL_DEPENDENCIES)` trên orders tự khởi động mọi consumer downstream?** Không thể kết luận như vậy; scope chủ yếu theo dependencies của module, phải xác minh bean/listener thật được bootstrap.
5. **Mockito gateway là sai trong cross-module integration orders → inventory?** Không nhất thiết. Nếu gateway nằm **ngoài đường chứng cứ đang kiểm tra**, mock để cô lập side effect có thể hợp lý; không mock publisher/consumer/reader của chain đó.
6. **Reservation đã xuất hiện có chứng minh RabbitMQ ack?** Không. Public state và broker acknowledgement là hai hợp đồng khác nhau.
7. **Một integration test xanh nhưng đọc `findAnyReserved()` có đáng tin?** Không; có thể pass nhờ row cũ. Phải đọc theo order và event IDs.
8. **Vì sao cần `ApplicationModules.verify()` khi test runtime đã xanh?** Runtime behavior xanh không bảo đảm không import internal package hay không có dependency cycle trái ranh giới.

### 10.4. Tài liệu tham khảo

- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `PublishedEvents`, `Scenario`.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): `ApplicationModules.verify()` và module boundaries.
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): event processing, Event Publication Registry và retry.
- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): context, transaction và test isolation.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener` và `AFTER_COMMIT`.
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html): `@SpringBootTest`, test configurations và test slices.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): `@ServiceConnection`, integration với container.
- [Testcontainers for Java](https://java.testcontainers.org/): PostgreSQL/Kafka/RabbitMQ test infrastructure.
- [Awaitility](https://github.com/awaitility/awaitility/wiki/Usage): bounded await cho async assertion.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, repetitions và parallel execution.

**Chốt chiến lược:** **cô lập để tìm đúng lỗi, tích hợp để chứng minh đúng điểm nối**. Một bộ kiểm thử tốt không chọn “mock hoặc tất cả thật” một lần duy nhất; nó chọn **những lát cắt bổ trợ nhau**, gắn mỗi lát với một failure mode và một oracle đủ mạnh để kết luận trong phạm vi bằng chứng của nó.
