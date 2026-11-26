# Phân biệt event nội bộ với integration event

## 1. Hai loại sự kiện, hai phạm vi cam kết

Trong Spring Modulith, một ứng dụng có thể được chia thành các application module như `orders`, `inventory` và `notifications`. Khi đơn hàng được xác nhận, module `orders` phát một sự kiện nghiệp vụ `OrderConfirmed`. Module `inventory` ở **cùng ứng dụng** lắng nghe để giữ hàng. Đồng thời, một hệ thống vận chuyển **ở tiến trình khác** cũng cần biết đơn hàng đã xác nhận để lập kế hoạch giao hàng.

Hai nhu cầu này trông giống nhau — đều muốn nhận tin “đơn hàng đã xác nhận” — nhưng có những ràng buộc rất khác:

- **Event nội bộ (internal event):** một thông điệp nghiệp vụ hoặc ứng dụng được trao đổi **bên trong ranh giới ứng dụng**; trong Spring Modulith, thường là object Java được phát qua `ApplicationEventPublisher`, xử lý bởi `@EventListener`, `@TransactionalEventListener` hoặc `@ApplicationModuleListener`.
- **Integration event:** thông điệp được công bố **qua ranh giới tiến trình/hệ thống** cho consumer triển khai độc lập; có hợp đồng trên đường truyền về tên sự kiện, phiên bản, cấu trúc payload, định tuyến, thời gian và ngữ nghĩa.

**Event nội bộ không tự trở thành integration event chỉ vì có nhiều module nhận.** Ngược lại, một integration event không nhất thiết phải là một Java class có annotation Spring. Trong Spring Modulith, một sự kiện nội bộ có thể được **chọn và chuyển đổi** thành message công khai bằng event externalization.

### Ví dụ dễ hình dung

~~~text
Ứng dụng Spring Modulith: Shop
┌─────────────────────────────────────────────────────────────┐
│ orders                                                      │
│   OrderService.confirm(orderId)                             │
│      └── publishEvent(OrderConfirmed)                       │
│                  │                                          │
│                  ├── inventory.StockListener                │
│                  │       (event nội bộ, cùng ứng dụng)       │
│                  │                                          │
│                  └── outbound.Externalization               │
│                          └── OrderConfirmedMessageV1       │
└────────────────────────────────┬────────────────────────────┘
                                 │  Broker: sales.orders.v1
                                 ▼
                        Dịch vụ vận chuyển riêng
                        (integration event consumer)
~~~

Bài học thuộc chương **Event publication** của học phần **SPRING_MODULITH_VERIFICATION_TESTING**. Vì học phần chú trọng kiểm chứng ranh giới kiến trúc qua `ApplicationModules`, thực hành `@ApplicationModuleTest`, kiểm thử sự kiện/database và quality gate CI, chúng ta sẽ không chỉ so sánh khái niệm mà còn viết các phép kiểm tra cho **cả hai phía ranh giới**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt event nội bộ và integration event theo người nhận, hợp đồng, thời gian sống, giao thức và mức tương thích.
2. Giải thích vì sao cùng một sự thật nghiệp vụ có thể có **hai biểu diễn**: domain event trong JVM và message contract ngoài hệ thống.
3. Thiết kế một lớp chuyển đổi nội bộ → integration event mà không để module nghiệp vụ phụ thuộc vào Kafka/RabbitMQ.
4. Xác định giới hạn của transaction, Event Publication Registry, broker ack và cơ chế retry.
5. Viết `@ApplicationModuleTest` kiểm tra sự kiện nguồn, contract test kiểm tra payload/routing và integration test kiểm tra broker.
6. Dùng `ApplicationModules.verify()` cùng quality gate CI để ngăn dependency sai và thay đổi message không tương thích.

## 2. Bảng so sánh chi tiết

| Tiêu chí | Event nội bộ | Integration event |
| --- | --- | --- |
| **Ranh giới** | Trong một ứng dụng hoặc các application module thuộc cùng triển khai. | Giữa các ứng dụng, tiến trình, dịch vụ hoặc tổ chức triển khai độc lập. |
| **Người sở hữu hợp đồng** | Chủ yếu các module trong cùng repository/chu kỳ phát hành. | Producer và các consumer có thể thuộc những nhóm/chu kỳ phát hành khác nhau. |
| **Biểu diễn** | Thường là Java `record`/POJO. | JSON, Avro, Protobuf hoặc định dạng đã thỏa thuận trên broker/transport. |
| **Mức tương thích** | Có thể thay đổi và cập nhật các module cùng phiên bản sau khi chạy test. | Phải duy trì backward/forward compatibility hoặc chiến lược version/migration. |
| **Phân phối** | Spring `ApplicationEventPublisher` và listeners trong `ApplicationContext`. | Kafka, AMQP, JMS, webhook hoặc một message transport ngoài tiến trình. |
| **Transaction** | Có thể xử lý đồng bộ hoặc theo các pha transaction. | Thường phát ra sau commit; gửi broker và DB consumer không tự thuộc một transaction chung. |
| **Retry** | Phụ thuộc loại listener và Event Publication Registry/cấu hình. | Phụ thuộc externalization adapter, broker, consumer và các chính sách retry riêng. |
| **Idempotency** | Quan trọng với async/republication. | Gần như bắt buộc khi có redelivery hoặc nhiều replica. |
| **Thứ tự** | Phụ thuộc cơ chế đồng bộ/async và transaction. | Phụ thuộc key, partition, broker, consumer và retry. |
| **Bảo mật** | Giới hạn bởi code/module boundary, nhưng vẫn phải bảo vệ dữ liệu. | Có ACL, mã hóa đường truyền, phân quyền topic, retention và kiểm soát dữ liệu xuất ra ngoài. |
| **Kiểm thử chủ đạo** | `PublishedEvents`, `@ApplicationModuleTest`, listener integration test. | Contract/schema test, routing/serializer test, broker integration và consumer tests. |

**Không nên hiểu “internal = không đáng tin cậy” và “integration = bền vững”.** Một internal event với transactional listener và persistent publication registry có thể được khôi phục sau lỗi; một integration event gửi HTTP kiểu fire-and-forget có thể dễ mất hơn. Độ bền phụ thuộc **thiết kế và cấu hình**, không phải chỉ tên loại event.

## 3. Phân biệt domain event, application event và integration event

Ba thuật ngữ thường bị dùng thay cho nhau:

- **Domain event** diễn tả một sự thật đã xảy ra trong miền nghiệp vụ, ví dụ `OrderConfirmed`. Đây là khái niệm thiết kế theo Domain-Driven Design, không buộc phải gắn với Spring.
- **Application event** là cơ chế phân phối sự kiện ở mức ứng dụng. Một domain event có thể được phát bằng Spring `ApplicationEventPublisher`, nhưng cũng có thể có các application events không phải sự thật nghiệp vụ, như yêu cầu làm mới cache.
- **Integration event** là hợp đồng thông điệp dành cho hệ thống khác, thường được tạo từ một sự thật nghiệp vụ đã được xác nhận và đã commit.

Ví dụ phân loại:

| Tên sự kiện | Phạm vi hợp lý | Giải thích |
| --- | --- | --- |
| `OrderConfirmed` | Internal domain event | Dùng giữa `orders` và `inventory` trong Shop. |
| `RecalculateOrderProjection` | Internal application event | Yêu cầu cập nhật projection nội bộ; không nhất thiết là business fact công khai. |
| `OrderConfirmedMessageV1` | Integration event contract | Thông báo công khai cho dịch vụ shipping qua broker. |
| `PaymentCapturedMessageV1` đến từ payment provider | Incoming integration event | Ứng dụng Shop nhận từ hệ thống ngoài; phải xác thực và chuyển về hành vi nội bộ. |

Một **command** như `ReserveStock` yêu cầu làm việc, còn một **event** như `StockReserved` nói rằng việc đã xảy ra. Không đổi một command thành event chỉ để dùng annotation: tên và ngữ nghĩa phải phản ánh sự thật nghiệp vụ. Trong tích hợp, sự khác biệt này quan trọng vì consumer phải biết có được từ chối một yêu cầu hay không và có thể nhận nhiều lần hay không.

## 4. Cùng một sự thật nghiệp vụ, vì sao cần hai payload?

Event nội bộ có thể chứa chi tiết hữu ích cho những module được phát hành cùng ứng dụng; integration event nên là **hợp đồng công khai tối thiểu, ổn định và không rò rỉ mô hình nội bộ**.

Giả sử nguồn có:

~~~java
package com.example.shop.orders.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant confirmedAt,
        BigDecimal payableAmount,
        String currency,
        int orderVersion
) {}
~~~

Module `inventory` quan tâm `orderId` và `orderVersion`. Hệ thống shipping bên ngoài chỉ cần những thông tin đã cam kết sau:

~~~json
{
  "schemaVersion": 1,
  "eventType": "sales.order-confirmed",
  "eventId": "d35dbff8-c269-41da-89e6-fc5e639c17e1",
  "orderId": "be3b1ac3-2d14-4c08-a6cb-a6ce1547eae5",
  "confirmedAt": "2026-11-26T03:30:00Z",
  "orderVersion": 4
}
~~~

Đây là JSON minh họa. Bên nhận không cần `payableAmount` và `currency` thì không nên đưa chúng vào contract “cho tiện”. Nếu tương lai vận chuyển cần số tiền COD, hãy thiết kế một thay đổi hợp đồng có kiểm soát và làm rõ số tiền đó đã bao gồm thuế/phí hay chưa.

### 4.1. Định danh nào cần ổn định?

Phân biệt:

- `orderId`: định danh thực thể nghiệp vụ, có thể xuất hiện trong nhiều sự kiện theo vòng đời đơn hàng.
- `eventId`: định danh **một sự thật nghiệp vụ**; khi cùng message được redeliver thì giá trị này **không đổi**.
- `orderVersion`: số phiên bản aggregate nếu hệ thống cần phát hiện sự kiện đến sai thứ tự.
- `publicationId`: định danh một **lần giao đến listener target** trong Spring Modulith Event Publication Registry; không thay cho `eventId` công khai.
- Broker offset/message ID: do hạ tầng vận chuyển cấp; thường không phải định danh nghiệp vụ để consumer deduplicate.

Một internal event có thể tạo nhiều target publication: ví dụ tới `inventory`, `notifications` và externalizer. Vì vậy **đếm số publication registry không bằng đếm số lần producer gọi `publishEvent`**.

### 4.2. Tại sao không gửi thẳng JPA entity?

Gửi `OrderEntity` ra broker có thể:

1. Làm lộ field không cần thiết hoặc nhạy cảm.
2. Gây lỗi serialize lazy-loaded associations/proxy.
3. Ràng buộc consumer vào tên package, cấu trúc database và framework của producer.
4. Biến refactor nội bộ thành breaking change của hợp đồng ngoài.
5. Khi replay message cũ, class/entity mới không còn tương thích với dữ liệu cũ.

Một immutable DTO public chỉ chứa field được phê duyệt dễ kiểm thử hơn. **Message contract phải độc lập với chi tiết JPA**, ngay cả khi event nguồn được phát bằng Spring.

## 5. Ví dụ kiến trúc Spring Modulith: orders, inventory và outbound

Giả định `ShopApplication` nằm ở package `com.example.shop`; theo cách phát hiện mặc định, các package con trực tiếp là application module:

~~~text
com.example.shop
├── ShopApplication.java
├── orders
│   ├── OrderService.java
│   ├── internal
│   │   ├── OrderEntity.java
│   │   └── OrderRepository.java
│   └── events
│       ├── OrderConfirmed.java
│       └── package-info.java
├── inventory
│   ├── OrderConfirmationListener.java
│   └── package-info.java
└── outbound
    ├── OrderMessageExternalization.java
    ├── package-info.java
    └── contract
        └── OrderConfirmedMessageV1.java
~~~

### 5.1. Công bố đúng API event nội bộ

File `orders/events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

File `inventory/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.inventory;
~~~

File `outbound/package-info.java`:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.example.shop.outbound;
~~~

Cả `inventory` lẫn `outbound` chỉ được phụ thuộc vào named interface `orders :: events`, không import `orders.internal.OrderRepository`. Lớp `outbound` là **adapter tích hợp**; nó biết hợp đồng broker, còn core của `orders` không phải biết có Kafka hay RabbitMQ.

### 5.2. Module nguồn phát một domain event sau chuyển trạng thái

File `orders/OrderService.java`:

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderConfirmed;
import com.example.shop.orders.internal.OrderRepository;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.NoSuchElementException;
import java.util.UUID;

@Service
public class OrderService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    public void confirm(UUID orderId) {
        var order = orders.findByIdForUpdate(orderId)
                .orElseThrow(() -> new NoSuchElementException(
                        "Order not found"));

        if (!order.confirmIfPending()) {
            return; // Không có chuyển trạng thái mới.
        }

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                orderId,
                Instant.now(),
                order.getPayableAmount(),
                order.getCurrency(),
                order.getVersion()));
    }
}
~~~

Đây là ví dụ có chủ đích tập trung vào event. `OrderRepository` có phương thức đọc khóa phù hợp (ví dụ `@Lock(PESSIMISTIC_WRITE)` với JPA); `OrderEntity` cung cấp `confirmIfPending()`, `getPayableAmount()`, `getCurrency()` và `getVersion()`. Các kiểu entity/repository và schema cần được triển khai khi đưa vào dự án thật.

Một `@Transactional` service gọi `publishEvent` **trong transaction**, nhưng một `@TransactionalEventListener(AFTER_COMMIT)` chỉ chạy khi commit thành công. Nếu transaction nguồn rollback, callback sau commit không được kích hoạt. `PublishedEvents` vẫn có thể quan sát lời gọi publish đã xảy ra trước rollback; không nhầm hai sự kiện đó.

Nếu `orderVersion` là field `@Version` do JPA tăng khi flush/commit, hãy cẩn trọng: đọc nó trước flush có thể chưa phản ánh version cuối cùng. Khi version là một phần hợp đồng, cần định nghĩa rõ cách tạo/version hóa, flush và test transaction để không phát sai sequence. Có thể dùng một sequence nghiệp vụ riêng hoặc phát từ trạng thái đã xác nhận tùy mô hình dữ liệu.

### 5.3. Module nhận trong cùng ứng dụng

File `inventory/OrderConfirmationListener.java`:

~~~java
package com.example.shop.inventory;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderConfirmationListener {

    private final StockReservationService reservations;

    OrderConfirmationListener(StockReservationService reservations) {
        this.reservations = reservations;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        reservations.reserveOnce(event.eventId(), event.orderId());
    }
}
~~~

`StockReservationService` là bean nội bộ của `inventory` cần được triển khai. `@ApplicationModuleListener` có ngữ nghĩa transactional event listener, xử lý bất đồng bộ và transaction mới theo cơ chế Spring Modulith.

Listener được truyền **Java object nội bộ** `OrderConfirmed`, không cần đọc Kafka, parse schema JSON hay biết `OrderConfirmedMessageV1`. Việc xử lý lại có thể xảy ra nếu publication chưa hoàn tất; vì thế `reserveOnce` phải có cơ chế idempotency bền vững.

## 6. Tạo integration event bằng adapter thay vì sửa lõi nghiệp vụ

Định nghĩa public message DTO ở `outbound/contract/OrderConfirmedMessageV1.java`:

~~~java
package com.example.shop.outbound.contract;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmedMessageV1(
        int schemaVersion,
        String eventType,
        UUID eventId,
        UUID orderId,
        Instant confirmedAt,
        int orderVersion
) {}
~~~

DTO bên ngoài **cố ý không chứa** số tiền/currency từ event nội bộ. Nó phản ánh hợp đồng thực sự mà dịch vụ shipping cần.

### 6.1. Cấu hình externalization

Spring Modulith cung cấp `EventExternalizationConfiguration` để chọn event cần gửi ra ngoài, map sang payload public và định tuyến broker. Mẫu sau dùng code thay vì đặt `@Externalized` trực tiếp trên domain event:

~~~java
package com.example.shop.outbound;

import com.example.shop.orders.events.OrderConfirmed;
import com.example.shop.outbound.contract.OrderConfirmedMessageV1;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.modulith.events.EventExternalizationConfiguration;
import org.springframework.modulith.events.RoutingTarget;

import java.util.Map;

@Configuration(proxyBeanMethods = false)
class OrderMessageExternalization {

    @Bean
    EventExternalizationConfiguration externalizationConfiguration() {
        return EventExternalizationConfiguration.externalizing()
                .select(event -> event instanceof OrderConfirmed)
                .mapping(OrderConfirmed.class, event ->
                        new OrderConfirmedMessageV1(
                                1,
                                "sales.order-confirmed",
                                event.eventId(),
                                event.orderId(),
                                event.confirmedAt(),
                                event.orderVersion()))
                .route(OrderConfirmed.class, event ->
                        RoutingTarget.forTarget("sales.orders.v1")
                                .andKey(event.orderId().toString()))
                .headers(OrderConfirmed.class, event -> Map.of(
                        "eventType", "sales.order-confirmed",
                        "schemaVersion", "1",
                        "eventId", event.eventId().toString()))
                .build();
    }
}
~~~

Đây là một ví dụ về **một bean cấu hình externalization**. Không đồng thời khai báo thêm bean khác chọn/gửi cùng event nếu chưa hiểu cách cấu hình hợp nhất, nhằm tránh message trùng hoặc lựa chọn sai.

Các điểm cần kiểm thử:

- `select`: chỉ `OrderConfirmed` đi ra ngoài, không phải mọi event nội bộ.
- `mapping`: chuyển sang `OrderConfirmedMessageV1`, bỏ `payableAmount` và `currency`.
- `route`: logical target `sales.orders.v1`, routing key theo `orderId`; với Kafka, target thường là topic và key ảnh hưởng partitioning.
- `headers`: cung cấp type, version và eventId phục vụ consumer, logging và tracing.

Các phương thức cấu hình và tính năng tương ứng phụ thuộc phiên bản Spring Modulith đang dùng. Phải đối chiếu dependency của dự án trước khi chuyển ví dụ thành code production.

### 6.2. Có thể chọn bằng @Externalized không?

Có. Nếu nhóm chấp nhận đưa annotation tích hợp vào event type, Spring Modulith cung cấp `@Externalized` để chọn event:

~~~java
@Externalized("sales.orders.v1")
public record OrderConfirmed(/* fields */) {}
~~~

Khi cần tránh domain layer phụ thuộc annotation cơ sở hạ tầng, dùng selection programmatic như ở mục 6.1. Hai phong cách có **trade-off**:

| Cách chọn | Ưu điểm | Nhược điểm |
| --- | --- | --- |
| `@Externalized` trên event | Dễ thấy ngay event nào sẽ được đưa ra ngoài. | Domain event biết tới annotation externalization; refactor/đổi contract phải cân nhắc. |
| Selector trong adapter | Tách coupling hạ tầng, dễ kiểm soát whitelist external events. | Cần test để tránh quên đăng ký event mới; cấu hình tập trung hơn. |

Lưu ý `@Externalized` đánh dấu **event type cần externalize**, không tự định nghĩa một contract JSON ổn định hoặc tự cung cấp version migration. Nếu không có mapping, adapter có thể serialize chính Java event gốc — đôi khi phù hợp, nhưng thường cần đánh giá trước khi coi nó là public API lâu dài.

### 6.3. Vì sao không phát hai event thủ công?

Mẫu dễ bị cám dỗ:

~~~java
publisher.publishEvent(new OrderConfirmed(...));
kafkaTemplate.send("sales.orders.v1", jsonPayload);
~~~

Nếu gửi Kafka ngay **trong transaction database**, broker có thể đã nhận message rồi DB rollback. Đồng thời use case nguồn bị ghép chặt với Kafka và serializer.

Mẫu còn tệ hơn là phát cả `OrderConfirmed` và `OrderConfirmedMessageV1` như hai event Spring khác nhau mà không giải thích cho những module nhận: có thể tạo hai luồng thông báo, nhiều publication và khó giữ đồng bộ các ID.

Thay vào đó, nên có **một sự thật nghiệp vụ** tại nguồn và một **adapter explicit** chuyển đổi/đưa ra ngoài sau commit, với cơ chế persistence/recovery phù hợp.

## 7. Ranh giới transaction: internal event không giống broker message

### 7.1. Event được phát trong transaction rồi rollback

~~~java
var transaction = new TransactionTemplate(transactionManager);

transaction.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderConfirmed(
            eventId, orderId, Instant.now(), amount, "VND", 1));
    status.setRollbackOnly();
});
~~~

`publishEvent` đã được gọi, nên `PublishedEvents` có thể quan sát event. Tuy nhiên:

- `@TransactionalEventListener(AFTER_COMMIT)` không được kích hoạt.
- `@ApplicationModuleListener` không xử lý theo nhánh after-commit.
- Externalization adapter dùng after-commit sẽ **không gửi broker message** cho transaction rollback đó.
- Publication Registry ghi trong cùng transaction nguồn (nếu cấu hình đúng) cũng bị rollback.

Điều này **khác** với một `@EventListener` đồng bộ thực hiện side effect ngay lúc publish: gửi HTTP/email trong listener đồng bộ có thể xảy ra **trước** rollback và không được database hoàn tác.

### 7.2. Đã commit nguồn nhưng broker không sẵn sàng

Nếu transaction của `orders` đã commit mà externalizer không kết nối được broker:

- Đơn hàng **vẫn tồn tại**.
- Message chưa chắc đã được broker chấp nhận.
- Với Event Publication Registry có persistence, publication externalizer có thể còn **incomplete**, phục vụ quan sát và xử lý lại.
- Cần chính sách resubmit theo tuổi, lỗi, số lần thử và điều kiện triển khai; không gọi lại `OrderService.confirm(orderId)` để “gửi lại”.

**Không dùng trạng thái transaction nguồn để suy ra broker delivery.** Producer DB commit và broker ack là hai mốc kỹ thuật tách biệt.

### 7.3. Broker nhận message, consumer chưa xử lý

Broker xác nhận nhận message có thể cho phép externalizer đánh dấu publication hoàn tất, nhưng consumer vẫn có thể:

- Chưa đọc message do lag.
- Đọc được nhưng parse lỗi phiên bản schema.
- Đọc thành công rồi transaction database consumer rollback.
- Gặp timeout sau khi đã thực hiện side effect bên ngoài.

Đây là lý do phân biệt rõ:

| Mốc | Bằng chứng có thể xác nhận | Chưa xác nhận được |
| --- | --- | --- |
| `PublishedEvents` thấy `OrderConfirmed` | Mã nguồn đã phát event trong ứng dụng. | Commit, broker send, consumer effect. |
| Registry lưu publication tới externalizer | Có nỗ lực giao sau commit được theo dõi. | Broker nhận thành công. |
| Externalizer completed | Thao tác gửi được adapter coi là thành công theo cơ chế client/ack. | Consumer đã xử lý nghiệp vụ. |
| Consumer đọc được record | Message đã tới consumer. | Side effect được commit; xử lý không trùng. |
| Consumer ghi marker + side effect trong transaction | Hiệu ứng DB thuộc transaction đã commit. | Mọi side effect ngoài DB đều exactly once. |

### 7.4. Trường hợp gửi được nhưng ack thất lạc

1. Broker nhận được `OrderConfirmedMessageV1`.
2. Ứng dụng không ghi được completion (crash hoặc mất ack).
3. Registry vẫn có publication chưa hoàn tất.
4. Recovery gửi lại cùng message.
5. Broker/consumer có thể thấy **hai bản sao của cùng `eventId`**.

Đây là lý do integration consumer phải idempotent. Một event nội bộ không cần gửi qua network vẫn có thể được listener xử lý lại khi publication registry phục hồi; nhưng khi đi qua broker, còn có thêm lỗi mạng, offset, replay và nhiều replica.

## 8. Integration contract và chiến lược phiên bản

### 8.1. Contract không chỉ là JSON schema

Một integration event contract hoàn chỉnh nên quy định:

| Thuộc tính | Câu hỏi cần trả lời |
| --- | --- |
| Tên sự kiện | `sales.order-confirmed` có nghĩa nghiệp vụ gì? |
| Điều kiện phát | Chỉ sau khi đơn hàng đã commit trạng thái `CONFIRMED`? |
| Schema version | Consumer phân biệt `v1`, `v2` thế nào? |
| ID | `eventId` để dedup; `orderId` để tương quan; `orderVersion` để phát hiện sai thứ tự? |
| Thời gian | `confirmedAt` là UTC hay local; ý nghĩa và precision? |
| Target/key | Topic, routing key, partitioning theo order hay theo event? |
| Field bắt buộc | Có chấp nhận null, thiếu field hoặc default không? |
| Delivery | Có thể lặp, đến trễ, đến sai thứ tự, có chính sách replay? |
| Bảo mật | Có PII, mã tenant hoặc dữ liệu hạn chế không? |
| Retention | Message tồn tại trong broker bao lâu, consumer cần replay thế nào? |

**Đừng thay ý nghĩa một field nhưng giữ nguyên schema.** Ví dụ `confirmedAt` từ thời điểm đơn hàng được xác nhận đổi thành thời điểm message được gửi lên Kafka sẽ làm consumer tính SLA sai dù JSON vẫn parse được.

### 8.2. Đánh giá các thay đổi

| Thay đổi | Nguy cơ | Hành động kiểm chứng |
| --- | --- | --- |
| Thêm field optional `deliveryZone` | Có thể an toàn với consumer bỏ qua unknown fields. | Consumer compatibility tests và default. |
| Thêm field required không có giá trị mặc định | Thường breaking. | Tăng version, migration hoặc fallback. |
| Đổi `orderId` từ UUID string thành integer | Breaking. | Version contract/dual-read có quản lý. |
| Đổi tên topic `sales.orders.v1` | Breaking về routing. | Broker subscriptions/ACL và migration. |
| Đổi Kafka key từ `orderId` sang `eventId` | Có thể phá thứ tự theo aggregate. | Test partitioning/order assumptions. |
| Đổi package Java nội bộ, giữ message DTO và wire format | Có thể an toàn. | Serialization/broker contract test. |
| Đổi `confirmedAt` từ UTC sang local time | Breaking về ngữ nghĩa. | Golden fixtures, timezone test. |
| Bổ sung chính sách replay trong broker | Consumer có thể nhận trùng nhiều hơn. | Idempotency test. |

“Thêm field luôn backward-compatible” là kết luận thiếu điều kiện: nhiều consumer cấu hình strict schema/unknown field rejection. Tương thích phải được kiểm tra với serializer, schema registry và consumer cụ thể.

### 8.3. V1 và V2 cùng tồn tại ra sao?

Một hệ thống có thể:

- Giữ **một topic**, thêm `schemaVersion` trong payload, để consumer hỗ trợ nhiều phiên bản.
- Tạo **topic theo major version**, ví dụ `sales.orders.v1` và `sales.orders.v2`, rồi chuyển dần consumer.
- Dùng schema registry nếu công nghệ và kiến trúc cho phép, kiểm tra backward/forward/transitive compatibility.

Không có lựa chọn duy nhất. Nhưng nếu dual-publish cùng sự thật nghiệp vụ tới hai topic, consumer subscribe cả hai có thể xử lý trùng. Hãy giữ **eventId ổn định qua các biểu diễn tương đương** và định nghĩa deduplication/migration rõ ràng.

## 9. Incoming integration event: chiều ngược lại cũng cần ranh giới

Một hệ thống bên ngoài cũng có thể phát `PaymentCapturedMessageV1` vào broker; module `payments` trong ứng dụng Shop cần phản ứng. Không nên cho inbound adapter lấy JSON rồi trực tiếp sửa `OrderEntity` hoặc phát bừa một Spring event giả vờ rằng transaction nội bộ đã commit.

Luồng phù hợp:

~~~mermaid
flowchart LR
    A["Payment provider / broker"] --> B["Inbound adapter"]
    B --> C["Validate schema, auth, idempotency"]
    C --> D["Application service của payments"]
    D --> E["Transaction: lưu kết quả"]
    E --> F["publishEvent(PaymentRecorded)"]
    F --> G["Listener nội bộ sau commit"]
~~~

**Incoming integration event** là dữ liệu từ ngoài trust boundary. Adapter cần:

1. Kiểm tra xác thực/nguồn gửi và quyền truy cập theo broker/transport.
2. Validate schema version, loại event, ID và các giá trị nghiệp vụ.
3. Xử lý trùng message (duplicate delivery) bằng khóa bền vững.
4. Gọi một application service hoặc command handler công khai thay vì truy cập nội bộ module khác.
5. Commit dữ liệu và dấu idempotency trong transaction phù hợp.
6. Nếu cần, phát một **internal event mới** diễn đạt sự thật nghiệp vụ đã được xác nhận trong Shop.

Ví dụ inbound handler ở tầng tích hợp (đoạn rút gọn):

~~~java
@Service
class PaymentCapturedInboundAdapter {

    private final PaymentApplicationService payments;

    PaymentCapturedInboundAdapter(PaymentApplicationService payments) {
        this.payments = payments;
    }

    public void onMessage(PaymentCapturedMessageV1 message) {
        if (message.schemaVersion() != 1) {
            throw new UnsupportedMessageVersionException(
                    message.schemaVersion());
        }

        payments.recordExternalCapture(
                message.eventId(), message.orderId(), message.amount());
    }
}
~~~

`PaymentApplicationService.recordExternalCapture(...)` phải tự thực hiện transaction, lưu marker chống trùng và xác nhận quyền/ngữ nghĩa nghiệp vụ. `PaymentCapturedMessageV1` và exception là hợp đồng/kiểu cần triển khai; ví dụ không tự chạy độc lập.

Một sự kiện bên ngoài “đã thu tiền” không mặc nhiên đồng nghĩa ứng dụng nội bộ “đã hoàn tất đơn hàng”: vẫn có thể có điều kiện xác thực, chống gian lận hoặc đối soát.

## 10. Kiểm thử event nội bộ bằng @ApplicationModuleTest

Trong module `orders`, test ưu tiên **hành vi nguồn**: mỗi chuyển trạng thái xác nhận phát đúng một `OrderConfirmed` với payload nội bộ đúng.

~~~java
package com.example.shop.orders;

import com.example.shop.orders.events.OrderConfirmed;
import com.example.shop.orders.internal.OrderEntity;
import com.example.shop.orders.internal.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

import java.math.BigDecimal;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrderConfirmedPublicationTests {

    @Autowired OrderService orders;
    @Autowired OrderRepository repository;

    @Test
    void confirmsOrderAndPublishesInternalEvent(
            PublishedEvents events) {

        UUID id = UUID.randomUUID();
        repository.saveAndFlush(
                new OrderEntity(id, new BigDecimal("129900"), "VND"));

        orders.confirm(id);

        assertThat(events.ofType(OrderConfirmed.class)
                .matching(OrderConfirmed::orderId, id))
                .singleElement()
                .satisfies(event -> {
                    assertThat(event.eventId()).isNotNull();
                    assertThat(event.confirmedAt()).isNotNull();
                    assertThat(event.currency()).isEqualTo("VND");
                });
    }

    @Test
    void repeatedConfirmationDoesNotPublishAgain(
            PublishedEvents events) {

        UUID id = UUID.randomUUID();
        repository.saveAndFlush(
                new OrderEntity(id, new BigDecimal("129900"), "VND"));

        orders.confirm(id);
        orders.confirm(id);

        assertThat(events.ofType(OrderConfirmed.class)
                .matching(OrderConfirmed::orderId, id))
                .hasSize(1);
    }
}
~~~

Đoạn này giả định repository/entity có những constructor và hành vi đã mô tả ở mục 5.2, test datasource và transaction manager sẵn sàng. **Không gắn `@Transactional` bao ngoài lớp test** khi muốn hai lần gọi service có commit riêng và kiểm chứng after-commit listener ở các test mở rộng.

`PublishedEvents` cho biết application event đã được phát trong phạm vi test. Nó **không khẳng định message trên broker đã được tạo**, càng không chứng minh hệ thống shipping đã xử lý. Đây là điểm phân biệt quan trọng giữa internal-event test và integration-event test.

### 10.1. Test module nhận nội bộ

Ở `inventory`, có thể dùng `@ApplicationModuleTest` với listener và service của chính module nhận. Một bài kiểm thử có ý nghĩa cần:

- Kích hoạt handler với `OrderConfirmed` hợp lệ.
- Xác minh side effect giữ hàng qua repository của module nhận.
- Thử xử lý lại cùng `eventId`; xác minh không tạo hai bản ghi cùng công việc.
- Thử lỗi database rồi kiểm tra transaction listener rollback, publication còn khả năng recovery.

Với `@ApplicationModuleListener` bất đồng bộ, nên dùng `Scenario` của Spring Modulith hoặc chờ theo điều kiện với timeout. Không đặt assertion kiểm tra DB ngay sau `publishEvent` rồi kết luận callback đã hoàn tất nếu xử lý chạy trên executor khác.

## 11. Kiểm thử integration contract: selection, mapping và routing

Một bài test riêng trong package `com.example.shop.outbound` có thể kiểm tra logic adapter **mà không khởi động Kafka**:

~~~java
package com.example.shop.outbound;

import com.example.shop.orders.events.OrderConfirmed;
import com.example.shop.outbound.contract.OrderConfirmedMessageV1;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.events.EventExternalizationConfiguration;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class OrderMessageContractTests {

    private final EventExternalizationConfiguration config =
            new OrderMessageExternalization()
                    .externalizationConfiguration();

    @Test
    void selectsAndConvertsToPublicContract() {
        var event = new OrderConfirmed(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-11-26T03:30:00Z"),
                new BigDecimal("129900"), "VND", 4);

        assertThat(config.supports(event)).isTrue();
        assertThat(config.supports(new Object())).isFalse();

        assertThat(config.map(event)).isEqualTo(
                new OrderConfirmedMessageV1(
                        1,
                        "sales.order-confirmed",
                        event.eventId(),
                        event.orderId(),
                        event.confirmedAt(),
                        event.orderVersion()));

        var target = config.determineTarget(event);
        assertThat(target.getTarget()).isEqualTo("sales.orders.v1");
        assertThat(target.getKey())
                .isEqualTo(event.orderId().toString());

        assertThat(config.getHeadersFor(event))
                .containsEntry("schemaVersion", "1")
                .containsEntry("eventId", event.eventId().toString());
    }
}
~~~

**Phép kiểm tra âm tính** `supports(new Object()).isFalse()` minh họa rằng selector không gửi mọi object. Trong dự án thật hãy dùng một internal event cụ thể mà **tuyệt đối không được externalize** để test hiệu quả hơn, ví dụ `RebuildOrderCache` hoặc một event chứa dữ liệu không được phép xuất.

Test này bảo vệ **selection, mapping, logical routing và headers**, nhưng chưa chứng minh:

- Kafka/AMQP serializer thực sự tạo ra bytes đúng contract.
- Broker đã nhận message.
- Message được gửi **sau commit** chứ không phải trước commit.
- Consumer hiểu schema và xử lý lặp đúng.

### 11.1. Serialization test với golden payload

Nếu chọn JSON, test với **cùng cấu hình Jackson serializer** của ứng dụng. Ví dụ phần assertion (giả định `ObjectMapper objectMapper` và `OrderConfirmedMessageV1 message` đã có):

~~~java
String json = objectMapper.writeValueAsString(message);
var tree = objectMapper.readTree(json);

assertThat(tree.path("schemaVersion").asInt()).isEqualTo(1);
assertThat(tree.path("eventType").asText())
        .isEqualTo("sales.order-confirmed");
assertThat(tree.path("eventId").asText()).isNotBlank();
assertThat(tree.path("orderId").asText()).isNotBlank();
assertThat(tree.path("orderVersion").asInt()).isEqualTo(4);
assertThat(tree.has("payableAmount")).isFalse();
assertThat(tree.has("currency")).isFalse();
~~~

Vì DTO có `Instant`, cần cấu hình Java Time support phù hợp trong serializer; kiểm thử giá trị thời gian UTC và định dạng thực tế của message. **Golden fixture** hoặc JSON schema đã được team consumer phê duyệt sẽ mạnh hơn việc so cùng một DTO với object do chính producer vừa tạo.

### 11.2. Kiểm thử ngữ nghĩa, không chỉ field

Ngoài `json.path(...)`, nên có assertions cho:

- `schemaVersion` được set đúng với contract đang phát.
- `orderVersion` có thể dùng để sắp xếp/phát hiện out-of-order đúng theo mô hình nghiệp vụ.
- `confirmedAt` là thời điểm xác nhận nghiệp vụ, không phải timestamp gọi Kafka producer.
- Event chỉ được tạo **một lần cho chuyển trạng thái**, kể cả khi command được gọi lặp.
- Các field nhạy cảm không vô tình xuất hiện trong DTO hoặc headers.

## 12. Broker integration test: từ contract tới message thật

Một integration test có Kafka/AMQP/JMS tương ứng phải kiểm tra **wire behavior**, không chỉ verify mock publisher. Với Kafka, ví dụ kịch bản:

1. Bootstrap Spring Boot application, Event Publication Registry persistence và Kafka test broker (Testcontainers hoặc embedded broker phù hợp).
2. Provision topic `sales.orders.v1`; cấu hình serializer/deserializer, key và ACL test.
3. Tạo order test và gọi `OrderService.confirm(id)` qua Spring-managed bean để transaction commit thật.
4. Consumer test nhận record của topic sau commit.
5. Assert key `orderId`, schemaVersion, eventType, eventId, confirmedAt, orderVersion và **không có các field nội bộ**.
6. Kiểm tra headers và việc message có thể deserialize bằng **cấu hình consumer**.
7. Có đối chứng rollback: phát event trong một transaction rồi đánh dấu rollback; không có message tương ứng được externalize.

Ví dụ assertion trên `ConsumerRecord<String, String> record` đã đọc bằng test consumer phù hợp:

~~~java
assertThat(record.topic()).isEqualTo("sales.orders.v1");
assertThat(record.key()).isEqualTo(orderId.toString());

var payload = objectMapper.readTree(record.value());
assertThat(payload.path("schemaVersion").asInt()).isEqualTo(1);
assertThat(payload.path("eventType").asText())
        .isEqualTo("sales.order-confirmed");
assertThat(payload.path("orderId").asText())
        .isEqualTo(orderId.toString());
assertThat(payload.has("payableAmount")).isFalse();
~~~

Đây chỉ là **phần assertion**, không phải một test class hoàn chỉnh. Harness cần tự tạo consumer, cô lập offsets, chờ message theo timeout, dọn fixture và dùng deserializer tương thích (nhiều cấu hình Kafka JSON trả về object/byte array chứ không phải `String`).

### 12.1. Tại sao negative assertion khi rollback khó?

Nếu một test không nhận message trong 100 ms, có thể adapter vẫn đang chờ executor hoặc broker đang chậm. “Không thấy ngay” **chưa đủ** chứng minh transaction rollback ngăn externalization. Test đáng tin cậy cần:

- Transaction nguồn được điều khiển rõ bằng `TransactionTemplate` hoặc service ném lỗi.
- Nhánh **commit đối chứng** thật sự nhận được message.
- Lọc theo `eventId` riêng và consumer offset/test topic được cô lập.
- Kiểm tra publication registry không còn bản ghi được commit của event rollback khi cấu hình persistence đúng.
- Deadline quan sát hợp lý; không dựa duy nhất vào `Thread.sleep` cố định.

### 12.2. Test broker lỗi và retry

Tắt hoặc gây lỗi broker có kiểm soát, cho nguồn commit, rồi kiểm tra:

1. Transaction nguồn vẫn được commit theo thiết kế.
2. Publication externalizer còn chưa hoàn tất nếu gửi broker thất bại.
3. Khi broker phục hồi, cơ chế resubmission đưa message đúng target/key/payload ra broker.
4. Cùng eventId có thể xuất hiện hơn một lần trong tình huống broker ack thất lạc; consumer không nhân đôi side effect.

Không nhầm **retry publication externalizer** với **publish lại domain event**; trường hợp thứ hai có thể kích hoạt cả local listeners và externalization thêm lần nữa.

## 13. Kiểm chứng module boundary trong cùng codebase

Việc dùng event nội bộ không có nghĩa không còn phụ thuộc module: `inventory` import `OrderConfirmed` của `orders`; `outbound` cũng vậy. Những phụ thuộc này cần đi qua public named interface.

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTests {

    @Test
    void verifiesDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp phát hiện phụ thuộc vòng, dùng API không công bố và vi phạm `allowedDependencies` theo quy tắc Spring Modulith. Nếu `outbound` import `orders.internal.OrderRepository` để tự tạo message, test kiến trúc có thể phát hiện sai phạm ấy.

**Giới hạn:** `ApplicationModules.verify()` không đọc hợp đồng JSON bên ngoài, không khởi động broker và không bảo đảm consumer sẽ xử lý thành công. Kiến trúc đúng và integration contract đúng là **hai quality gate khác nhau**, đều cần có.

### 13.1. Kiểm tra dependency theo hướng mong muốn

Quan hệ mong muốn:

~~~mermaid
flowchart LR
    O["orders.events (public named interface)"]
    I["inventory (application module)"]
    B["outbound (adapter module)"]
    K["Kafka / AMQP broker"]
    S["Shipping service"]

    I -->|"uses event API"| O
    B -->|"uses event API"| O
    B -->|"externalizes DTO"| K
    K --> S
~~~

Không nên có đường `orders` → `outbound.KafkaAdapter` hoặc `orders` → `shipping service implementation`. Module nghiệp vụ nên giữ vai trò phát **sự thật nội bộ**, còn ranh giới integration được quản lý tại adapter.

## 14. Reliability, idempotency và thứ tự giữa hai thế giới

### 14.1. Một internal event có nhiều lần giao

Với `OrderConfirmed`, registry có thể theo dõi:

- Publication đến `inventory.OrderConfirmationListener`.
- Publication đến externalizer gửi `OrderConfirmedMessageV1`.

Nếu listener `inventory` thành công nhưng broker lỗi, publication nội bộ có thể completed trong khi publication externalizer vẫn incomplete. Cả hai không phải một transaction xử lý chung. Việc externalizer hoàn tất **cũng không** đồng nghĩa consumer shipping đã xử lý.

### 14.2. Idempotency cho local listener và external consumer

Ở local listener, nếu có retry do publication chưa hoàn tất, dùng `eventId` và marker xử lý bền vững để bảo vệ side effect.

Ở external consumer, cùng một event ID có thể đi tới broker nhiều lần do retry sau mất ack. Một chiến lược xử lý database:

~~~java
@Transactional
public void on(OrderConfirmedMessageV1 message) {
    if (processedEvents.existsById(message.eventId())) {
        return;
    }

    shipments.createFromOrder(
            message.orderId(), message.orderVersion());
    processedEvents.save(new ProcessedEvent(message.eventId()));
}
~~~

Đây là **mẫu rút gọn**. Cần có khóa duy nhất trên `eventId`, transaction bao quanh cả side effect và marker, xử lý race khi hai consumer cùng thấy chưa xử lý. Với email/HTTP/payment gateway, database transaction **không tự hoàn tác** các side effect bên ngoài; dùng provider idempotency key hoặc một mô hình dispatch/outbox phù hợp.

### 14.3. Ordering không tự được bảo đảm

Internal `@ApplicationModuleListener` async không mặc nhiên xử lý mọi event của cùng order theo thứ tự chính xác đã phát; external broker cũng có thể nhận event trễ hoặc đảo thứ tự do retry.

Với Kafka, key `orderId` hỗ trợ đưa các message cùng order về một partition theo quy tắc partitioner, nhưng ordering còn phụ thuộc **producer**, số instance, phân phối và recovery. Nếu consumer bắt buộc xử lý `OrderConfirmed` trước `OrderShipped`, phải có `orderVersion`, điều kiện trạng thái hoặc cơ chế buffer/reject event out-of-order phù hợp.

Không coi `orderVersion` là số thứ tự đúng nếu code nguồn chưa bảo đảm tăng và phát chính xác trong transaction; cần test concurrency, flush và commit.

## 15. Chọn kiểu event phù hợp theo tình huống

| Nhu cầu | Nên bắt đầu với | Lý do |
| --- | --- | --- |
| `orders` thông báo cho `inventory` trong cùng Spring Modulith app. | Internal application/domain event. | Module coupling có thể kiểm soát bằng named interface và module tests. |
| `orders` cần cập nhật projection nội bộ. | Internal event hoặc xử lý nội bộ trực tiếp. | Không cần public message contract nếu không có consumer ngoài. |
| Gửi trạng thái đơn hàng cho dịch vụ shipping riêng. | Integration event DTO qua externalization. | Consumer deploy độc lập, cần schema version/routing/delivery semantics. |
| Thông báo thay đổi giá cho 5 hệ thống đối tác. | Integration event contract có governance. | Khác tổ chức/chu kỳ phát hành, cần bảo mật và tương thích. |
| Nhận webhook payment captured từ nhà cung cấp ngoài. | Incoming integration message → adapter → application service. | Không cho dữ liệu ngoài sửa trực tiếp domain entity. |
| Yêu cầu một hệ thống khác **thực hiện** hành động và phản hồi kết quả. | Command/message hoặc API call có contract, tùy semantics. | Phân biệt yêu cầu thực hiện với fact đã xảy ra. |
| Muốn giữ transaction DB nguồn và gửi broker không mất sự kiện. | Internal event + persistent publication registry/đánh giá outbox. | Cần nhất quán khi commit, retry và recovery. |

Sự lựa chọn phụ thuộc **ranh giới triển khai và quyền sở hữu hợp đồng**, không chỉ phụ thuộc tên class kết thúc bằng `Event`.

## 16. Quality gate CI cho internal event và integration event

Học phần `SPRING_MODULITH_VERIFICATION_TESTING` nên kết hợp các phép kiểm tra sau:

| Test/Gate | Bảo vệ điều gì? | Ví dụ assertion |
| --- | --- | --- |
| **Architecture test** | Không import implementation nội bộ của module khác. | `ApplicationModules.of(...).verify()`. |
| **Internal producer test** | Đúng sự thật nghiệp vụ được phát, không phát trùng. | `@ApplicationModuleTest`, `PublishedEvents` lọc `orderId`. |
| **Internal consumer test** | Module nhận xử lý event đúng, có transaction và idempotency. | DB side effect đúng một lần khi replay cùng eventId. |
| **External selection test** | Chỉ event được phép mới ra ngoài. | `config.supports(event)` dương và âm tính. |
| **Mapping test** | DTO ngoài đúng schema, không lộ field nội bộ. | `config.map(event)` bằng expected DTO. |
| **Routing/headers test** | Topic/key/type/version không đổi ngoài hợp đồng. | `determineTarget`, `getHeadersFor`. |
| **Serialization/contract test** | Consumer đọc được wire schema và các fixture cũ. | JSON/Avro/Protobuf schema compatibility. |
| **Commit/rollback test** | Không externalize event thuộc transaction rollback. | TransactionTemplate + broker/registry đối chứng. |
| **Broker integration test** | Adapter thực sự gửi đúng message/headers. | Consumer test nhận record và kiểm tra payload. |
| **Failure/recovery test** | Broker lỗi không làm mất thông tin cần retry. | Incomplete publication → resubmit → completed. |
| **Inbound adapter test** | Dữ liệu từ ngoài được validate, chống trùng, không phá domain. | Invalid schema bị từ chối; replay không nhân side effect. |
| **Security test** | Không xuất dữ liệu nhạy cảm, phân quyền broker đúng. | Contract không chứa PII; ACL/config policy checks. |

Các test nhanh (architecture, module, mapping/contract) nên chạy ở mỗi pull request. Integration test có broker và database có thể chạy ở stage riêng nhưng vẫn phải là **quality gate** đối với thay đổi externalization. Với async listener, đợi theo điều kiện có timeout thay vì dùng `Thread.sleep` cố định.

### Những metrics khác nhau không nên trộn

- **Internal event count:** số sự kiện phát trong ứng dụng.
- **Registry incomplete count:** publication chưa hoàn tất theo listener target, bao gồm externalizer nếu được theo dõi.
- **Broker send error rate:** tỷ lệ lỗi gửi message ra broker.
- **Consumer lag:** message trên broker mà consumer chưa xử lý.
- **Business convergence lag:** độ trễ từ đơn hàng confirmed đến shipping thực sự nhận/xử lý.

Một Registry publication completed cho externalizer **không làm consumer lag bằng không**. Metrics cần đo các mốc khác nhau, không gộp thành một chỉ số “event thành công”.

## 17. Các anti-pattern thường gặp

1. **Dùng chung JPA entity làm internal event và public integration DTO.** Lộ mô hình DB, khó version, dễ serialize lỗi.
2. **Cho rằng một event có nhiều module nghe thì đã là integration event.** Các module trong cùng ứng dụng vẫn thuộc phạm vi nội bộ.
3. **Chỉ đổi tên class thành `IntegrationEvent` rồi coi là đã có contract.** Còn cần schema, semantics, target, key, retry và compatibility.
4. **Để `OrderService` import `KafkaTemplate` và gửi trước commit.** Coupling hạ tầng và nguy cơ broker nhận message cho transaction đã rollback.
5. **Không có mapping/selection whitelist.** Vô tình externalize event nhạy cảm hoặc thay đổi payload ngoài ý muốn.
6. **Dùng tên Java package làm tên topic lâu dài mà không kiểm chứng.** Refactor có thể phá routing.
7. **Nhầm `PublishedEvents` với broker delivery.** Nó kiểm tra lời gọi phát application event, không phải externalization end-to-end.
8. **Nhầm registry completed với consumer completed.** Registry chỉ biết việc xử lý publication ở target của nó, không kiểm soát downstream vô hạn.
9. **Cho rằng gửi broker thành công là đúng một lần.** Mất ack hoặc resubmit có thể gây duplicate.
10. **Không kiểm tra version cũ.** Message nằm trong broker/storage nhiều ngày có thể còn cần deserialize sau nâng cấp.
11. **Bỏ qua ordering và concurrency.** Consumer xử lý version thấp sau version cao có thể làm sai trạng thái.
12. **Cho incoming message từ ngoài quyền truy cập entity nội bộ.** Phá module boundary và bỏ qua validation/idempotency.

## 18. Bài tập thực hành

Một ứng dụng Spring Modulith quản lý thanh toán:

- Module `payments` lưu trạng thái thanh toán và phát `PaymentCaptured`.
- Module `accounting` trong cùng ứng dụng ghi sổ kế toán.
- Dịch vụ `fraud-monitoring` ở một hệ thống khác cần nhận thông báo thanh toán qua Kafka.
- Hợp đồng Kafka `payments.captured.v1` gồm `schemaVersion`, `eventId`, `paymentId`, `capturedAt`, `amountMinor`, `currency`; key theo `paymentId`.

### Câu hỏi

1. `PaymentCaptured` gửi tới `accounting` là internal event hay integration event?
2. Hợp đồng JSON `PaymentCapturedMessageV1` dùng bởi `fraud-monitoring` là gì?
3. Vì sao không đưa `PaymentJpaEntity` nguyên vẹn vào Kafka?
4. Nếu transaction thanh toán rollback sau `publishEvent`, `PublishedEvents` có thể thấy sự kiện không? Broker có nên nhận thông báo không?
5. Nếu broker đã nhận rồi producer mất ack và resubmit, consumer cần điều gì?
6. Nếu đổi field `amountMinor` từ số nguyên sang decimal major units mà vẫn giữ version 1, vấn đề gì xảy ra?
7. Test `ApplicationModules.verify()` đủ chứng minh hợp đồng Kafka không bị phá không?
8. Nếu `accounting` xử lý thành công nhưng Kafka không sẵn sàng, có phải transaction nguồn cần rollback lại không?

### Đáp án gợi ý

1. **Internal event**, vì `accounting` là một module cùng ứng dụng; Spring Modulith có thể giao qua `@ApplicationModuleListener`.
2. **Integration event contract**, vì consumer ngoài ứng dụng có chu kỳ deploy độc lập và phụ thuộc wire schema/routing.
3. Entity có thể chứa proxy, field nhạy cảm và cấu trúc persistence nội bộ; public DTO ổn định hơn.
4. `PublishedEvents` **có thể thấy** lời gọi publish đã diễn ra; externalization theo after-commit **không gửi** thông điệp của transaction rollback.
5. **Idempotency** theo `eventId` cùng transaction/side effect tương ứng; retry có thể giao bản sao.
6. Đây là breaking change về cả kiểu và ngữ nghĩa đơn vị tiền; phải version/migrate và kiểm thử consumer compatibility.
7. Không. `verify()` bảo vệ ranh giới dependency tĩnh, không kiểm tra serializer/topic/schema hoặc consumer ngoài.
8. Không tự rollback được transaction nguồn đã commit; cần registry/retry/recovery và mô hình bù trừ nếu nghiệp vụ yêu cầu.

## 19. Checklist khi thiết kế ranh giới event

- [ ] Đã xác định rõ người nhận: **application module cùng tiến trình** hay **consumer triển khai độc lập**.
- [ ] Event nội bộ diễn đạt một sự thật nghiệp vụ đúng, không dùng tên event để che một command.
- [ ] Một lần chuyển trạng thái hợp lệ chỉ sinh event phù hợp; có guard chống phát trùng.
- [ ] Public event API thuộc `@NamedInterface` và các module nhận khai báo `allowedDependencies` đúng.
- [ ] Core module không trực tiếp phụ thuộc Kafka/RabbitMQ/DTO ngoài nếu muốn giữ kiến trúc tách biệt.
- [ ] Integration DTO là hợp đồng riêng, không serialize toàn bộ JPA entity.
- [ ] Contract có tên, schema version, eventId, aggregate ID, timestamp, payload semantics, target/key/headers.
- [ ] Chỉ externalize event trong allowlist; có test event không được phép xuất.
- [ ] Mapping loại bỏ dữ liệu nhạy cảm và có golden fixture/schema compatibility tests.
- [ ] Externalization gắn với commit nghiệp vụ; có test rollback và commit đối chứng.
- [ ] Có persistent publication registry/chiến lược outbox nếu yêu cầu không mất thông điệp khi broker lỗi.
- [ ] Đã phân biệt broker ack, Registry completed và consumer side effect.
- [ ] Consumer idempotent, chịu được duplicate/retry và có chính sách out-of-order.
- [ ] Có chiến lược schema version/migration và tương thích message tồn đọng qua các phiên bản.
- [ ] Incoming integration event đi qua adapter validate và application service công khai.
- [ ] `@ApplicationModuleTest`, contract tests, broker integration tests và `ApplicationModules.verify()` đều nằm trong CI.

**Kết luận:** **Event nội bộ** là cơ chế diễn đạt và phân phối thông tin giữa các thành phần của một ứng dụng; **integration event** là một hợp đồng message bền vững về ý nghĩa và định dạng giữa các hệ thống độc lập. Spring Modulith có thể chuyển một internal event thành integration message qua externalization, nhưng chính **boundary adapter, schema, routing, transaction semantics, retry/idempotency và bộ kiểm thử hợp đồng** mới bảo vệ hệ thống khi triển khai và nâng cấp độc lập.

### Tài liệu để đối chiếu API và hành vi

- [Spring Modulith — Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listeners, Event Publication Registry, externalization và broker adapters.
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): kiểm chứng cấu trúc và phụ thuộc module.
- [Spring Modulith — Testing Application Modules](https://docs.spring.io/spring-modulith/reference/testing.html): `@ApplicationModuleTest`, `PublishedEvents` và `Scenario`.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): thời điểm thực thi `@TransactionalEventListener`.

> Ghi chú tương thích: các API `EventExternalizationConfiguration`, routing, publication registry và broker adapters cần được đối chiếu với **phiên bản Spring Modulith thực tế**. Đoạn Java trong bài là mẫu thiết kế giảng dạy, không thay thế việc bổ sung entity/repository, cấu hình broker, schema và chạy kiểm thử tích hợp. Vòng Content QA chuyên môn được thực hiện ở bước quy trình tiếp theo.
