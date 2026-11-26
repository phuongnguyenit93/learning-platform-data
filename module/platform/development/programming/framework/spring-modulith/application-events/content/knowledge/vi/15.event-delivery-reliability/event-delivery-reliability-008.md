# Điểm xác nhận (Acknowledgment Point) trong giao sự kiện Spring Modulith

Một đơn hàng đã được lưu vào database, event `OrderPlaced` đã được publish và listener `notification` bắt đầu gửi email. Nếu hệ thống dừng ngay lúc ấy, điều gì sẽ được tính là **đã thành công**? Chỉ vì method `publishEvent(...)` trả về bình thường, có thể kết luận email đã được gửi không? Nếu broker đã phản hồi ACK, có thể kết luận module nhận đã cập nhật database chưa? Nếu một listener xử lý thành công còn listener khác thất bại, event được coi là hoàn tất ở đâu?

Những câu hỏi đó dẫn tới khái niệm **điểm xác nhận** (*acknowledgment point* hoặc *completion point*): một mốc trong chuỗi giao sự kiện mà tại đó **một thành phần xác nhận một điều kiện cụ thể đã đạt được**. Chọn sai điểm xác nhận dễ dẫn đến hai loại lỗi đối lập: **mất công việc** khi xác nhận quá sớm, hoặc **xử lý lặp** khi xác nhận quá muộn so với tác dụng phụ.

Bài học **“Điểm xác nhận”** thuộc chương **Đảm bảo tin cậy** của `SPRING_MODULITH_APPLICATION_EVENTS`. Trong bối cảnh giao tiếp giữa các module Spring Modulith qua application events, chúng ta sẽ xem xét publisher, listener sau commit, Event Publication Registry, retry, kiểm thử và quan sát giao sự kiện để giảm phụ thuộc mà vẫn bảo vệ ranh giới nghiệp vụ.

> **Nguyên tắc cốt lõi:** Mỗi ACK chỉ có giá trị trong **phạm vi của thành phần phát ra ACK**. “Broker đã nhận message”, “listener đã chạy xong” và “nghiệp vụ bên ngoài đã hoàn tất” là ba khẳng định khác nhau.

## 1. Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Giải thích **điểm xác nhận** là gì và phân biệt ACK ở publisher, transaction, registry, broker, consumer và hệ thống đích.
2. Xác định được **ranh giới transaction** và các thời điểm event có thể mất hoặc được xử lý lại.
3. Phân tích tác động của việc ACK **trước**, **trong** hoặc **sau** khi xử lý nghiệp vụ.
4. Hiểu cơ chế Event Publication Registry ghi nhận publication và đánh dấu hoàn tất cho các listener phù hợp.
5. Thiết kế consumer tránh đánh dấu hoàn tất trước khi một cập nhật database quan trọng được commit.
6. Hiểu vì sao cần **idempotency** khi retry sau một side effect thành công nhưng ACK chưa được ghi nhận.
7. Phân biệt ACK của message broker với kết quả của application event trong Spring Modulith.
8. Đề xuất test, metric và quy trình vận hành để kiểm tra điểm xác nhận có thực sự tương ứng với cam kết nghiệp vụ.

## 2. “Xác nhận” phải có chủ thể, đối tượng và điều kiện

Một phát biểu “event E1 đã được ACK” là **chưa đủ thông tin**. Cần biết:

- **Ai xác nhận?** Database, publisher, executor, event publication registry, broker, listener hay API đối tác?
- **Xác nhận cái gì?** Việc lưu event, tiếp nhận một task, nhận message, commit một cập nhật, hay hoàn thành một hành động?
- **Xác nhận cho ai?** Một listener cụ thể, một consumer group, một đối tác hay toàn bộ workflow?
- **ACK có bền vững không?** Nếu process chết một giây sau ACK, bằng chứng còn được khôi phục không?
- **Khi không có ACK thì sao?** Retry tự động, giám sát thủ công, dead-letter queue, reconciliation hay chấp nhận mất?

Ví dụ một chuỗi thao tác:

~~~text
T1  OrderingService ghi đơn hàng
T2  OrderingService gọi publishEvent(OrderPlaced)
T3  Database commit transaction đặt hàng
T4  Notification listener bắt đầu xử lý
T5  Provider gửi email báo đã nhận yêu cầu
T6  Listener trả về thành công
T7  Registry đánh dấu publication hoàn tất (nếu cấu hình phù hợp)
~~~

Ở T2, việc publish được gọi **không chứng minh T3 đã xảy ra**. Ở T5, provider trả lời thành công **không nhất thiết chứng minh người nhận đã đọc email**. Ở T6, listener chỉ chứng minh logic mà nó thực hiện đã trả về theo hợp đồng. Ở T7, registry chỉ ghi nhận **publication tương ứng đã hoàn tất theo cơ chế của nó**; không thay thế bằng chứng kết quả ngoài hệ thống.

### Ma trận các điểm xác nhận

| Điểm | Bên xác nhận | Điều có thể kết luận | Điều **chưa thể** kết luận |
| --- | --- | --- | --- |
| Method `publishEvent(...)` trả về | Spring event dispatch tại publisher | Dispatch theo cấu hình đã thực hiện đến mức method trả về | Transaction đã commit; listener async hoàn tất |
| Database commit thành công | Transaction manager/database | Dữ liệu tham gia transaction đã commit | Email đã gửi; broker nhận message |
| Executor nhận task | `TaskExecutor` | Công việc đã vào cơ chế lập lịch | Task được lưu bền; handler hoàn tất |
| Event publication được lưu | Registry/persistence | Có dấu vết publication theo cơ chế lưu | Listener đã xử lý thành công |
| Registry đánh dấu hoàn tất | Registry | Listener/publication đã hoàn tất theo lifecycle của registry | Mọi side effect ngoài đều đạt đúng một lần |
| Broker xác nhận producer write | Broker | Message được chấp nhận theo semantics producer/broker | Consumer đã xử lý và commit dữ liệu |
| Consumer ACK/commit offset | Consumer/broker | Vị trí tiêu thụ đã được xác nhận theo protocol | Bản ghi nghiệp vụ chắc chắn chính xác |
| Đối tác trả HTTP 2xx | API bên ngoài | Đối tác đã phản hồi request theo API contract | Công việc downstream cuối cùng đã hoàn tất |

**Lỗi thường gặp nhất** là dùng một điểm xác nhận của tầng vận chuyển để thay thế cho điểm xác nhận của **nghiệp vụ**.

## 3. Một event được phát cho nhiều module có nhiều điểm hoàn tất

Giả sử `ordering` phát `OrderPlaced` cho `notification`, `analytics` và `loyalty`:

~~~mermaid
flowchart LR
    O["ordering<br/>OrderPlaced E1"] --> P["Spring event dispatch"]
    P --> N["notification<br/>Gửi email"]
    P --> A["analytics<br/>Ghi chỉ số"]
    P --> L["loyalty<br/>Xét điểm"]
    N --> NC["Completion N"]
    A --> AC["Completion A"]
    L --> LC["Completion L"]
~~~

Mỗi consumer sở hữu một công việc. **Hoàn tất ở `analytics` không có nghĩa `notification` đã hoàn tất.** Nếu sử dụng Event Publication Registry với các listener được hỗ trợ, tình trạng publication nên được xem **theo listener/đích nhận**, không chỉ đếm một trạng thái tổng cho event ID.

Định danh nên phân biệt:

| Định danh | Ví dụ | Chức năng |
| --- | --- | --- |
| `eventId` | E1 | Một lần xảy ra sự kiện nghiệp vụ |
| `aggregateId` | O100 | Đơn hàng/sản phẩm/tài khoản liên quan |
| `listenerId` | `notification.on(OrderPlaced)` | Bên nhận cụ thể |
| `publicationId` | P-n | Dấu vết một publication được registry quản lý |
| `correlationId` | R42 | Liên kết nhiều bước trong cùng luồng |

Tùy cách triển khai, registry có định danh và trạng thái riêng; **không được mặc định `eventId` và `publicationId` là cùng một giá trị**. Nếu dùng một event để fan-out cho nhiều listener, câu hỏi “đã ACK chưa?” phải được trả lời cho từng đích liên quan.

## 4. Phân biệt điểm phát và điểm commit của publisher

Trong Spring, application event có thể được publish **ngay trong một transaction chưa commit**:

~~~java
package com.example.shop.ordering.internal;

import com.example.shop.ordering.events.OrderPlaced;
import java.time.Clock;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderingService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    OrderingService(
            OrderRepository orders,
            ApplicationEventPublisher events,
            Clock clock
    ) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public UUID placeOrder(OrderDraft draft) {
        UUID orderId = orders.insert(draft);

        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                clock.instant()
        ));

        return orderId;
    }
}
~~~

Trong ví dụ này, `OrderRepository`, `OrderDraft` và bean `Clock` là các abstraction cần triển khai trong dự án thực. Method trả `orderId` **chưa đồng nghĩa transaction đã được xác nhận thành công ngay tại câu lệnh `return`**: transaction interceptor của Spring còn phải hoàn tất commit khi lời gọi qua proxy kết thúc.

### Hai lớp sự thật khác nhau

1. **Publisher gọi publish:** một Java object đã được gửi vào event infrastructure.
2. **Database commit:** trạng thái đơn hàng đã được lưu bền theo transaction manager.

Với `@EventListener` đồng bộ, handler thường chạy ngay tại `publishEvent(...)` và có thể thấy transaction đang mở. Nếu handler gửi một email, transaction sau đó rollback, email **không tự bị hủy**.

Với `@TransactionalEventListener(phase = AFTER_COMMIT)`, handler chỉ được kích hoạt sau khi transaction nguồn commit thành công nếu event được publish trong một transaction hợp lệ. Điều này giải quyết **điều kiện về thời điểm nghiệp vụ**, nhưng không tự bảo đảm khôi phục listener khi process crash.

## 5. ACK sớm hay ACK muộn: đánh đổi giữa mất và trùng

Giả sử message M1 cần khiến consumer tạo một bản ghi trong database.

### 5.1. ACK trước khi xử lý — có thể mất công việc

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Consumer DB
    B->>C: Gửi M1
    C-->>B: ACK M1 (quá sớm)
    Note over B,C: Broker coi M1 đã xử lý theo chính sách
    C--xD: Process crash trước INSERT
    Note over B,D: M1 có thể không được giao lại
~~~

Nếu broker đã chấp nhận ACK và không còn trách nhiệm phát lại, consumer crash trước khi ghi dữ liệu sẽ tạo **mất kết quả nghiệp vụ**. Đây là cửa sổ đặc trưng của một số thiết kế ưu tiên **at-most-once**.

### 5.2. ACK sau khi xử lý — có thể xử lý trùng

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant C as Consumer
    participant D as Consumer DB
    B->>C: Gửi M1
    C->>D: INSERT + COMMIT
    D-->>C: Thành công
    Note over C,B: Consumer crash trước ACK
    B->>C: Gửi lại M1 sau phục hồi
    C->>D: Nguy cơ INSERT lần 2
~~~

Đợi tới sau commit mới ACK giúp tránh xác nhận một thao tác chưa bền vững, nhưng **không loại bỏ khả năng nhận lại message**. Nếu broker không thấy ACK, nó có thể redeliver theo protocol và chính sách recovery. Consumer phải xử lý trùng an toàn.

### 5.3. Đặt ACK ở đâu phụ thuộc cam kết

| Chiến lược | Điểm ACK thường hướng tới | Đánh đổi |
| --- | --- | --- |
| At-most-once | ACK/commit offset **trước** tác vụ, theo một giao thức phù hợp | Có thể mất kết quả nếu crash sau ACK |
| At-least-once | Hoàn tất tác vụ **trước** ACK; redelivery khi chưa ACK | Có thể thực hiện lại sau crash giữa side effect và ACK |
| Effectively-once về nghiệp vụ | Xử lý lặp an toàn, cập nhật/đánh dấu đã xử lý trong transaction hợp lý | Delivery có thể lặp, nhưng kết quả được chống trùng |
| Exactly-once trong một phạm vi cụ thể | Tích hợp transaction/protocol chuyên biệt | Không tự mở rộng sang email, API ngoài hoặc nhiều hệ thống |

**Không có một thời điểm ACK đơn lẻ tự giải quyết đồng thời mọi failure window trên hai hệ thống không chia sẻ cùng transaction.**

## 6. Chuỗi xác nhận trong Spring Modulith

Với một ứng dụng có Event Publication Registry được cấu hình đúng theo version/dependency/persistence tương ứng, vòng đời thường cần phân biệt:

~~~mermaid
flowchart TD
    A["Publisher phát event trong transaction"] --> B["Đăng ký publication cho listener được hỗ trợ"]
    B --> C{"Transaction nguồn"}
    C -->|Rollback| X["Không có event nghiệp vụ đã commit"]
    C -->|Commit| D["Publication có thể được xử lý sau commit"]
    D --> E["Listener thực hiện công việc"]
    E --> F{"Listener thành công?"}
    F -->|Có| G["Đánh dấu publication hoàn tất"]
    F -->|Không| H["Publication chưa hoàn tất"]
    H --> I["Recovery / resubmission theo cấu hình"]
    I --> E
~~~

Đây là **mô hình khái niệm** của quy trình có registry và listener thích hợp, không phải mã API hay cấu hình mặc định của mọi Spring Modulith version. Việc registry lưu publication vào transaction nào, khi nào đánh dấu completion, cách resubmit và trạng thái khả dụng phụ thuộc implementation cùng cấu hình ứng dụng.

### 6.1. Lưu publication không đồng nghĩa hoàn tất

**Publication recorded** có nghĩa là hạ tầng có dấu vết cần xử lý. **Publication completed** có nghĩa listener tương ứng đã được hạ tầng xem là hoàn tất. Hai trạng thái này cần được phân biệt trong dashboard và vận hành.

Nếu transaction nguồn rollback, publication ghi cùng transaction thường không nên được hiểu là một durable event “đơn đã đặt thành công”. Nếu ứng dụng cần **lưu bền sự kiện thất bại**, phải thiết kế luồng dữ liệu và transaction riêng.

### 6.2. Listener trả về là một điểm xác nhận quan trọng

Ở mô hình registry theo dõi invocation của listener, hạ tầng thường ghi nhận hoàn tất khi listener chạy **thành công** theo hợp đồng. Vì vậy:

- Nếu listener **ném exception**, hạ tầng có thể giữ publication chưa hoàn tất để kiểm tra/retry theo cấu hình.
- Nếu listener **bắt lỗi rồi trả về bình thường**, hạ tầng có thể hiểu là thành công dù thực tế nghiệp vụ chưa hoàn tất.
- Nếu listener chỉ **submit tác vụ khác vào queue** rồi trả về, completion có thể được ghi **trước khi công việc thật kết thúc**.

Đặc biệt nguy hiểm là:

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    try {
        emailSender.sendConfirmation(event.orderId());
    } catch (RuntimeException failure) {
        log.warn("Email failed but ignored", failure);
    }
    // Handler trả về bình thường dù side effect chưa thành công.
}
~~~

Đây là ví dụ **cần tránh khi yêu cầu retry/recovery**. Việc nuốt lỗi làm hạ tầng không còn tín hiệu rõ để phân biệt publication thất bại với publication hoàn tất. Nếu lỗi thực sự được phép bỏ qua, phải xác định chính sách *best-effort* riêng, không mập mờ giữa “xử lý thành công” và “bỏ qua lỗi”.

## 7. Hợp đồng event và ranh giới module

Ví dụ `ordering` phát một hợp đồng công khai:

~~~java
// com/example/shop/ordering/events/OrderPlaced.java
package com.example.shop.ordering.events;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderPlaced {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

Nếu `ordering.events` là subpackage của module, công bố nó qua named interface:

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

Và giới hạn module tiêu thụ:

~~~java
// com/example/shop/analytics/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.analytics;
~~~

`analytics` phụ thuộc vào **hợp đồng**, không vào `ordering.internal.OrderRepository` hoặc `OrderEntity`. Điều này bảo vệ ranh giới kiến trúc dù chính sách giao sự kiện là best-effort hay có recovery. **Điểm ACK** là trách nhiệm runtime; **named interface** là trách nhiệm tổ chức phụ thuộc. Không được coi một cơ chế thay thế cơ chế kia.

### Tại sao cần `eventId`?

`orderId` xác định aggregate; một đơn có thể phát nhiều event khác nhau. `eventId` xác định **lần xảy ra một sự kiện cụ thể**. Khi publication được xử lý lại, consumer có thể dùng cùng `eventId` làm khóa chống trùng. Nếu mỗi lần retry lại sinh một event ID mới cho cùng publication, việc khử trùng lặp sẽ khó hơn.

## 8. Listener hoàn tất việc ghi dữ liệu nội bộ

Một consumer `analytics` cần tăng chỉ số đơn hàng được chấp nhận. Cơ sở dữ liệu của consumer nên bảo đảm rằng **dấu vết đã xử lý event** và **cập nhật chỉ số** nằm trong cùng transaction.

~~~java
package com.example.shop.analytics.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderAnalyticsListener {

    private final OrderStatistics statistics;

    OrderAnalyticsListener(OrderStatistics statistics) {
        this.statistics = statistics;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        statistics.applyPlacedOnce(event.eventId(), event.orderId());
    }
}
~~~

~~~java
package com.example.shop.analytics.internal;

import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderStatistics {

    private final ProcessedEventRepository processedEvents;
    private final OrderMetricsRepository metrics;

    OrderStatistics(
            ProcessedEventRepository processedEvents,
            OrderMetricsRepository metrics
    ) {
        this.processedEvents = processedEvents;
        this.metrics = metrics;
    }

    @Transactional
    public void applyPlacedOnce(UUID eventId, UUID orderId) {
        boolean firstProcessing =
                processedEvents.insertIfAbsent("analytics.order-placed", eventId);

        if (!firstProcessing) {
            return;
        }

        metrics.recordAcceptedOrder(orderId);
    }
}
~~~

`ProcessedEventRepository`, `OrderMetricsRepository` và các method là **abstraction của ứng dụng ví dụ**, không phải Spring Modulith API. Chúng cần được triển khai bằng lưu trữ giao dịch. `@ApplicationModuleListener` đã cung cấp semantics listener sau commit, async và transaction mới; method service có `@Transactional` mặc định có thể tham gia transaction listener nếu phù hợp cấu hình, hoặc tạo transaction của riêng nó khi được gọi bằng proxy.

### Điều kiện để logic trên thật sự idempotent

- Có ràng buộc duy nhất cho `(consumer_name, event_id)` trong database.
- Thao tác đánh dấu đã xử lý và cập nhật chỉ số sử dụng **cùng một transaction thực sự**.
- Khi hai worker xử lý đồng thời cùng event, thao tác `insertIfAbsent` phải nguyên tử. Một cách khả thi trên PostgreSQL là `INSERT ... ON CONFLICT DO NOTHING`, rồi kiểm tra số row được thêm.
- Nếu cập nhật chỉ số thất bại, transaction rollback **cả dấu vết đã xử lý**, để lần tiếp theo vẫn có cơ hội làm lại.
- Lỗi không phải trùng event không được bị nuốt rồi hiểu thành hoàn tất.

Một cấu trúc bảng minh họa:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

DDL dùng kiểu `UUID` cho database có hỗ trợ; cần điều chỉnh với hệ quản trị khác. Đây là cách giảm rủi ro **xử lý trùng**, không tự bảo đảm publication luôn được giao. Registry và consumer persistence giải quyết hai phần khác nhau.

## 9. Điểm xác nhận của `@ApplicationModuleListener`

`@ApplicationModuleListener` là annotation kết hợp của Spring Modulith để phản ứng sau commit, thực thi bất đồng bộ và dùng transaction mới cho xử lý liên module. Nó phù hợp khi `ordering` không cần biết module `analytics` cài đặt thế nào.

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    statistics.applyPlacedOnce(event.eventId(), event.orderId());
}
~~~

Ở đây, cách hiểu có chủ đích là:

1. **Transaction nguồn đã commit** trước khi listener xử lý theo semantics sau commit.
2. Listener thực hiện xử lý bên trong ranh giới transaction của consumer.
3. Khi logic listener **hoàn tất thành công**, cơ chế theo dõi publication nếu được cấu hình có cơ sở đánh dấu hoàn tất.
4. Nếu listener ném lỗi, publication có thể ở trạng thái chưa hoàn tất, tùy cơ chế registry và recovery.

**Chú ý về version/cấu hình:** các chi tiết persistence, transaction boundary và việc resubmit incomplete publications phụ thuộc dependency và phiên bản Spring Modulith đang sử dụng. Không nên khẳng định chỉ cần annotation là registry hoặc job recovery đã được bật.

### Sơ đồ thời gian cho một publication

~~~mermaid
sequenceDiagram
    participant O as ordering
    participant DB as Publisher DB
    participant R as Publication Registry
    participant A as analytics listener
    participant AD as Analytics DB
    O->>DB: Ghi Order trong transaction
    O->>R: Ghi nhận publication (nếu cấu hình)
    O->>DB: Commit
    DB-->>O: Commit thành công
    R-->>A: Kích hoạt xử lý sau commit
    A->>AD: Ghi marker + metric trong transaction
    AD-->>A: Commit thành công
    A-->>R: Listener hoàn tất
    R->>R: Đánh dấu publication hoàn tất
~~~

Sơ đồ mô tả **các mốc khái niệm** chứ không khẳng định thứ tự I/O nội bộ hoặc cách database transaction được chia sẻ giống hệt ở mọi configuration. Điều quan trọng là **marker nghiệp vụ và completion registry không tự là một atomic commit duy nhất** trong tất cả các mô hình.

## 10. Cửa sổ lỗi giữa tác dụng phụ và ACK

Đây là trường hợp trung tâm của reliability:

~~~text
T1 Listener nhận OrderPlaced(E1).
T2 Listener ghi một bản ghi notification và transaction consumer commit.
T3 Process dừng trước khi publication được ghi nhận hoàn tất.
T4 Recovery tìm E1 còn chưa hoàn tất.
T5 Listener có thể nhận lại E1.
~~~

Nếu consumer không khử trùng lặp, nó có thể tạo hai bản ghi notification. Nếu đã ghi dấu E1 và hiệu ứng nghiệp vụ trong cùng transaction, lần xử lý lại ở T5 có thể nhận biết E1 đã được áp dụng và kết thúc an toàn.

**Điểm cần phân biệt:** khi xử lý lại, listener vẫn nên **trả về thành công** nếu event đã được áp dụng trước đó và trạng thái đúng. Như vậy registry có thể đánh dấu hoàn tất, thay vì cứ retry vô hạn một event đã đạt kết quả nghiệp vụ mong muốn.

### Ma trận các cửa sổ lỗi

| Lúc process dừng | Dữ liệu nghiệp vụ | Publication/ACK | Hướng xử lý |
| --- | --- | --- | --- |
| Trước commit của publisher | Đơn có thể rollback | Publication trong transaction có thể không tồn tại bền vững | Không coi event “đơn đã đặt” là hợp lệ |
| Sau publisher commit, trước listener chạy | Đơn đã lưu | Có thể đang chờ nếu registry bền vững | Recovery nếu đã cấu hình |
| Trong consumer transaction trước commit | Chưa có kết quả consumer bền vững | Chưa hoàn tất | Retry có thể xử lý lại |
| Sau consumer commit, trước registry completion | Consumer đã có kết quả | Có thể còn trạng thái chưa hoàn tất | Dedupe bằng event ID |
| Sau registry completion | Consumer được coi đã xử lý theo listener contract | Hoàn tất | Thường không cần retry publication ấy |
| Sau khi gửi email nhưng trước khi lưu chứng cứ gửi | Email có thể đã gửi | Completion còn thiếu | Retry có thể gửi trùng; cần API idempotency hoặc quy trình kiểm tra |

Không có một dòng trạng thái `COMPLETED` nào tự giải thích **tất cả những gì đã xảy ra bên ngoài hệ thống**. Phải biết listener xem điều gì là “thành công”.

## 11. Tác dụng phụ bên ngoài làm ACK khó hơn

Đối với một cập nhật SQL local, marker chống trùng và dữ liệu nghiệp vụ có thể nằm trong cùng transaction. Với **email, webhook hoặc API thanh toán**, database local thường không thể giao dịch nguyên tử cùng hệ thống ngoài.

Ví dụ:

~~~text
1. Listener gửi yêu cầu email cho provider.
2. Provider xử lý email và trả 200 OK.
3. Listener crash trước khi đánh dấu publication completed.
4. Recovery chạy lại listener.
5. Provider có thể nhận thêm yêu cầu gửi lần thứ hai.
~~~

Một ACK HTTP của provider có thể chỉ nghĩa là **yêu cầu được tiếp nhận**, chứ không chứng minh email đã đến hộp thư người nhận. Nếu requirement cần biết “đã gửi” hoặc “đã nhận”, phải định nghĩa thêm trạng thái/protocol (webhook về kết quả, polling trạng thái, reconciliation).

### Các chiến lược giảm rủi ro

1. **Idempotency key:** nếu provider hỗ trợ, truyền một khóa ổn định dựa trên `eventId` hoặc một business operation ID. Cần xem contract provider định nghĩa thời hạn lưu key và phạm vi duy nhất.
2. **Bản ghi công việc local:** chuyển từ xử lý trực tiếp sang trạng thái `PENDING → SENDING → SENT/FAILED` với khóa duy nhất; một worker riêng xử lý và đối chiếu với bên ngoài.
3. **Outbox/inbox:** lưu intent gửi hoặc trạng thái nhận trong database để recovery.
4. **Đối soát:** khi kết quả mơ hồ do timeout, hỏi trạng thái từ hệ thống đích thay vì mặc định gửi lại vô điều kiện.
5. **Chấp nhận giới hạn:** nếu hệ thống ngoài không hỗ trợ idempotency hoặc truy vấn trạng thái, không được hứa “không bao giờ gửi trùng” chỉ dựa trên transaction/registry local.

## 12. Khi nào ACK của broker được gửi?

Spring application events chạy trong cùng JVM không tự có cơ chế ACK như Kafka hoặc RabbitMQ. **ACK của broker** chỉ xuất hiện khi ta dùng hạ tầng messaging hoặc externalization tương ứng.

~~~mermaid
flowchart LR
    I["Internal event<br/>OrderPlaced"] --> X["Integration adapter"]
    X --> B[("Broker")]
    B --> C["External consumer"]
    X -.->|"Producer confirmation"| B
    C -.->|"Consumer ACK / offset"| B
~~~

Cần phân biệt hai hướng:

- **Producer confirmation:** broker báo đã chấp nhận bản ghi theo cơ chế producer/broker.
- **Consumer acknowledgment:** consumer cho biết vị trí/đơn vị message nào có thể coi là đã nhận/xử lý theo protocol.

Chúng **không xảy ra cùng lúc** và không cùng ý nghĩa. Ngay cả khi producer nhận ACK bền vững, consumer có thể chưa bắt đầu xử lý.

### 12.1. Với RabbitMQ: ACK delivery tag

Với manual acknowledgments, consumer thường:

1. Nhận message với `deliveryTag` trên một channel.
2. Kiểm tra payload và xử lý transaction nghiệp vụ.
3. Khi công việc đã hoàn tất theo policy, gọi ACK cho delivery tag.
4. Nếu xử lý thất bại, chọn NACK/requeue/dead-letter theo loại lỗi và chính sách.

Pseudocode:

~~~text
receive M1 (deliveryTag = D1)
try:
    validate(M1)
    commitBusinessChangeOnce(M1.eventId)
    basicAck(D1)                 # Sau khi DB xử lý thành công
catch TransientFailure:
    basicNack(D1, policy)        # Xem retry/backoff/requeue phù hợp
catch InvalidMessage:
    rejectOrDeadLetter(D1)      # Không retry vô hạn
~~~

Đây là **pseudocode**, không phải method signature Java có thể chạy trực tiếp. Trạng thái `basicAck` là trạng thái delivery trên channel của broker, không phải bản ghi audit rằng khách hàng đã nhận email. Channel mất kết nối trước ACK có thể khiến message được giao lại theo cơ chế broker.

### 12.2. Với Kafka: điểm commit offset

Trong Kafka, consumer group dùng offset để quản lý tiến độ đọc. Với record tại offset `N`, việc commit offset kế tiếp thường được hiểu là nhóm đã đi qua tới `N + 1` trong partition đó.

~~~text
Poll record M1 at offset N
Validate M1
Apply business change and commit DB
Commit offset N + 1
~~~

Nếu commit offset **trước** thay đổi nghiệp vụ và process chết, message có thể bị bỏ qua: khuynh hướng at-most-once. Nếu commit **sau** thay đổi nghiệp vụ và process chết giữa hai bước, message có thể được đọc lại: khuynh hướng at-least-once với duplicate.

Các ví dụ này là **mô hình thứ tự thao tác**. Cấu hình auto-commit, rebalance, batch processing, retry, transaction, Spring Kafka container và broker version có thể thay đổi chi tiết. Đặc biệt, bật `enable.auto.commit=true` không phải bằng chứng tự động của một guarantee at-most-once hoặc at-least-once end-to-end.

## 13. Xác nhận qua bridge giữa database và broker

Một tình huống quen thuộc là module `ordering` commit đơn hàng trong database rồi muốn gửi integration message đến dịch vụ vận chuyển.

### 13.1. Dual-write chưa có transaction chung

~~~text
DB commit Order thành công
    |
    +-- Process crash trước khi producer gửi message
          |
          +-- Đơn đã lưu nhưng dịch vụ vận chuyển không biết
~~~

Nếu làm ngược lại:

~~~text
Broker nhận message thành công
    |
    +-- DB transaction đặt hàng rollback
          |
          +-- Đối tác xử lý một đơn chưa tồn tại hợp lệ
~~~

Không thể chỉ chọn một vị trí gọi `publishEvent` hoặc một ACK broker để làm cho **hai hệ thống độc lập** có chung atomic commit.

### 13.2. Transactional outbox

Một giải pháp phổ biến là ghi **trạng thái đơn hàng và outbox message trong cùng transaction database**, rồi có relay gửi outbox qua broker:

~~~mermaid
sequenceDiagram
    participant O as ordering
    participant DB as Database + Outbox
    participant R as Outbox relay
    participant B as Broker
    participant C as External consumer
    O->>DB: Lưu Order + Outbox message cùng transaction
    DB-->>O: Commit
    R->>DB: Đọc outbox chưa gửi
    R->>B: Publish M1
    B-->>R: Producer confirmation
    R->>DB: Đánh dấu trạng thái relay
    B->>C: Giao M1
    C->>C: Idempotent processing
~~~

Đây là kiến trúc **minh họa**. Nếu relay crash sau khi broker nhận M1 nhưng trước khi đánh dấu outbox đã gửi, relay có thể gửi lại M1. Do đó consumer vẫn cần idempotency.

Event Publication Registry trong Spring Modulith có thể giải quyết bài toán theo dõi publication theo cách phù hợp với các listener/hạ tầng được hỗ trợ, nhưng **không mặc định đồng nhất registry với một outbox tùy ý hoặc một message broker ACK**. Khi cần externalization, hãy xác minh đúng cơ chế, storage, transaction và retry đang dùng.

## 14. ACK và retry quyết định delivery semantics

| Điều kiện ACK | Khi lỗi xảy ra | Delivery semantics dự kiến |
| --- | --- | --- |
| ACK trước khi xử lý; broker không redeliver | Có thể mất công việc | At-most-once ở ranh giới consumer |
| ACK sau khi xử lý; chưa ACK được phát lại | Có thể giao nhiều lần | At-least-once nếu công việc được lưu và phục hồi đúng |
| Handler thành công nhưng registry completion chưa ghi | Có thể chạy lại | Cần consumer idempotent |
| Không có publication bền vững, chỉ in-memory async | Crash có thể mất task | Best-effort, không khẳng định durable delivery |
| Consumer nhận nhiều lần nhưng chỉ cập nhật DB một lần | Có thể giao trùng nhưng business effect không tăng | Effectively-once trong phạm vi dữ liệu đã bảo vệ |

**Exactly-once** không phải kết quả tự động khi chuyển ACK sang cuối method listener. Một hệ thống có thể đạt bảo đảm rất mạnh trong một phạm vi transaction/broker cụ thể nhưng không thể tự suy ra side effect bên ngoài (như email) cũng “chính xác một lần”.

### Khi nào nên retry?

- Với timeout, mất kết nối, overload: retry giới hạn với backoff/jitter và giới hạn concurrency.
- Với schema sai, thiếu quyền, vi phạm nghiệp vụ cố định: không retry vô hạn.
- Với kết quả mơ hồ từ đối tác: tra cứu trạng thái nếu có thể trước khi thử lại.
- Với event đã được xử lý: idempotent no-op và ACK thành công theo policy.

Đừng đẩy một event bị lỗi vĩnh viễn qua vòng lặp retry không giới hạn; nó có thể làm nghẽn queue, tăng tải và che khuất các event hợp lệ phía sau.

## 15. Dead-letter là một điểm xác nhận vận hành khác

Trong hệ thống có broker, consumer có thể chuyển message sai hoặc không xử lý được sang dead-letter queue (DLQ), quarantine hoặc một workflow điều tra.

Đây là một **quyết định trạng thái**: hệ thống không tiếp tục retry vô hạn trên luồng chính, nhưng **không có nghĩa nghiệp vụ của message đã hoàn tất**.

| Trạng thái | Có thể nói “đã xong” không? |
| --- | --- |
| Message đã được ACK sau thành công | Hoàn tất theo hợp đồng xử lý của consumer |
| Message bị chuyển DLQ | Đã phân loại/chuyển sang luồng xử lý lỗi, **chưa chắc đạt business effect** |
| Message bị drop do sai schema | Đã kết thúc thử xử lý, nhưng có thể cần audit/cảnh báo |
| Message được replay từ DLQ | Một lần xử lý mới; phải chú ý idempotency và event identity |

DLQ có thể chứa dữ liệu nhạy cảm; cần quyền truy cập, retention, redaction và audit. Việc replay nên có identity, quyền thao tác và dấu vết, tránh làm trùng hậu quả sau khi một sự kiện đã được xử lý thủ công.

## 16. Xác nhận có thể sai do nuốt lỗi hoặc xác nhận quá sớm

Ba mẫu lỗi phổ biến:

### 16.1. Bắt exception rồi trả về bình thường

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    try {
        externalService.call(event.orderId());
    } catch (Exception failure) {
        // Nuốt lỗi và giả vờ thành công: rất nguy hiểm.
    }
}
~~~

Nếu registry dựa trên việc handler hoàn tất thành công, đây là **ACK sai sự thật**: handler không thực hiện được yêu cầu nhưng đã trả về như thành công. Nếu công việc có thể bỏ qua, hãy biểu diễn chính sách bỏ qua rõ ràng; nếu cần retry, đừng giấu lỗi.

### 16.2. Fire-and-forget một công việc con

~~~java
@ApplicationModuleListener
void on(OrderPlaced event) {
    executor.execute(() -> externalService.call(event.orderId()));
    // Handler đã kết thúc trước khi externalService.call(...) hoàn tất.
}
~~~

Đây là ví dụ cần xem lại: listener có thể được đánh dấu hoàn tất ngay sau khi submit, trong khi công việc thật đang nằm trong in-memory executor và có thể mất nếu process crash. Nếu cần theo dõi bền vững, hãy lưu work item/outbox và cho worker xử lý riêng, hoặc để listener chờ đúng kết quả theo contract.

### 16.3. Phân tán side effect và ACK trên nhiều transaction

~~~text
Consumer DB: COMMIT notification record
Email API:    SEND accepted
Registry:     mark COMPLETED
~~~

Ba dòng này không mặc nhiên nằm trong một transaction nguyên tử. Thiết kế phải xác định **điểm kết thúc mà listener cam kết**, còn các bước về sau phải có owner, trạng thái bền vững và recovery riêng.

## 17. Kiểm thử điểm xác nhận

Kiểm thử cần chứng minh **những sự kiện nào được ghi nhận ở mỗi mốc** và hệ thống sẽ ra sao nếu dừng ngay giữa hai mốc.

### 17.1. Test publisher đã phát event

Spring Modulith có `PublishedEvents` để kiểm tra event phát trong module test:

~~~java
package com.example.shop.ordering;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.shop.ordering.events.OrderPlaced;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.PublishedEvents;

@ApplicationModuleTest
class OrderPublisherTest {

    @Autowired OrderFacade orders;

    @Test
    void publishesOrderPlaced(PublishedEvents events) {
        UUID orderId = orders.placeOrder(validOrderRequest());

        assertThat(events.ofType(OrderPlaced.class))
                .extracting(OrderPlaced::orderId)
                .contains(orderId);
    }

    private PlaceOrderRequest validOrderRequest() {
        // Tạo fixture đúng với nghiệp vụ và repository của dự án.
        throw new UnsupportedOperationException("Provide project fixture");
    }
}
~~~

`OrderFacade`, `PlaceOrderRequest` và `validOrderRequest()` là thành phần minh họa cần triển khai trong ứng dụng cụ thể. Test này kiểm chứng **publish**, không chứng minh transaction đã commit, registry hoàn tất hoặc broker/consumer bên ngoài đã ACK.

### 17.2. Test transaction commit và rollback

Với listener `AFTER_COMMIT`, cần xác nhận:

1. Transaction commit thật → listener được kích hoạt theo đúng phase.
2. Transaction rollback sau publish → listener sau commit **không** thực hiện side effect.
3. Khi không có transaction nguồn, listener transaction mặc định **không chạy**, trừ khi có fallback được thiết kế.

Để tránh kết luận sai, lưu ý test gắn `@Transactional` thường rollback cuối method test. Nếu muốn quan sát callback sau commit, hãy tạo ranh giới commit thực bằng service Spring hoặc `TransactionTemplate`, và chờ điều kiện có timeout khi listener bất đồng bộ.

### 17.3. Test lỗi trước và sau cập nhật nghiệp vụ

| Vị trí chèn lỗi | Điều cần thấy nếu có registry/recovery | Điều cần bảo đảm ở consumer |
| --- | --- | --- |
| Trước khi consumer ghi DB | Publication chưa hoàn tất để chạy lại | Chưa có side effect |
| Trong consumer transaction | Lỗi làm transaction rollback | Marker và cập nhật cùng rollback |
| Sau consumer commit nhưng trước registry completion | Có thể còn publication chưa hoàn tất | Retry không nhân đôi cập nhật |
| Sau broker nhận nhưng trước relay đánh dấu sent | Relay có thể gửi trùng | Consumer ngoài dùng event ID/idempotency |
| Message sai schema | Không retry vô hạn | Quarantine/DLQ, audit và quyền truy cập đúng |
| Executor queue đầy | Không mặc định task đã được nhận | Có backpressure/recovery/cảnh báo phù hợp |

Các test liên quan crash window thực sự cần integration environment có thể dừng process, giữ storage và khởi động lại; unit test thuần túy **không chứng minh được durability qua crash**.

### 17.4. Test kiến trúc module

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này kiểm soát package/named interface và phụ thuộc module, **không chứng minh** ACK hoặc completion của listener. Cần kết hợp test hành vi và hạ tầng.

## 18. Quan sát: đo từng điểm xác nhận thay vì một biến “delivered”

Khi có nhiều đích nhận và nhiều bước, chỉ số `delivered=true` là quá mơ hồ. Nên định nghĩa metric, log và trace theo từng giai đoạn.

| Mốc | Metric hoặc thông tin gợi ý |
| --- | --- |
| Publisher tạo event | Số event theo loại, `eventId`, aggregate ID an toàn |
| Transaction nguồn commit | Số transaction thành công/thất bại cho use case |
| Registry ghi publication | Số publication đang chờ theo listener |
| Listener bắt đầu | Thời điểm bắt đầu, consumer identity, attempt count |
| Consumer DB commit | Số event được áp dụng mới và số event dedupe |
| Publication completed | Số completion và độ trễ tới completion |
| Broker publish confirmed | Số producer confirmation thành công/thất bại |
| Broker consumer ACK | Số ACK/NACK/requeue/DLQ theo topic/queue |
| Workflow bên ngoài hoàn tất | Trạng thái business effect và kết quả đối soát |

### 18.1. Những độ trễ nên phân biệt

- `occurredAt → publishedAt`: từ sự kiện nghiệp vụ đến publish.
- `publishedAt → listenerStartedAt`: độ trễ điều phối/queue.
- `listenerStartedAt → listenerFinishedAt`: thời gian xử lý.
- `transactionCommittedAt → publicationCompletedAt`: độ trễ xử lý sau commit.
- `brokerConfirmedAt → externalConsumerCompletedAt`: độ trễ tích hợp.

Các giá trị này chỉ là mô hình quan sát; Spring Modulith không tự cấp tất cả field hoặc metric trên. Ứng dụng cần instrument phù hợp và tránh ghi payload nhạy cảm vào log.

### 18.2. Metric để phát hiện ACK sai

- Tỷ lệ `publicationCompleted` tăng trong khi `businessEffectSucceeded` không tăng tương ứng.
- Publication đang chờ tăng bất thường hoặc có tuổi cao nhất vượt ngưỡng.
- Số retry của một listener tăng mạnh.
- Số event bị dedupe tăng sau một đợt khôi phục.
- Broker producer xác nhận thành công nhưng consumer lag hoặc DLQ tăng.

Không được so sánh tổng số publish với **tổng của tất cả consumer ACK** khi fan-out: một event có thể tạo nhiều publication hợp lệ. Hãy so sánh theo loại event và **consumer identity**.

## 19. Checklist thiết kế điểm xác nhận

Trước khi triển khai một listener mới, trả lời:

1. **Điểm nào được coi là thành công?** Xong code handler, commit DB, API bên ngoài chấp nhận request hay nghiệp vụ cuối cùng hoàn thành?
2. **Ai ghi và lưu trạng thái đó?** Event Publication Registry, database consumer, broker, hay hệ thống khác?
3. **Nếu crash ngay trước ACK, ai xử lý lại?** Có storage/recovery bền vững và owner vận hành không?
4. **Nếu crash ngay sau side effect nhưng trước ACK, retry có an toàn không?** Có idempotency key/unique constraint/đối soát không?
5. **Khi lỗi không thể phục hồi, có phân loại rõ không?** Retry, DLQ, incident hay manual review?
6. **Có nhiều consumer không?** Mỗi listener có trạng thái độc lập không?
7. **Mọi side effect có cùng transaction không?** Nếu không, đâu là bước trung gian có trạng thái?
8. **Event có được phát trong transaction hợp lệ không?** `AFTER_COMMIT`/`AFTER_ROLLBACK` có chạy đúng điều kiện?
9. **Có test crash window và observability chưa?** Không chỉ happy-path.
10. **Đây là yêu cầu độ tin cậy nào?** At-most-once, at-least-once, effectively-once hay một workflow trạng thái bền vững?

Không nên thêm retry vào tất cả event rồi coi là hoàn tất thiết kế. **Retry chỉ an toàn khi một lần xử lý lại không phá vỡ bất biến hoặc gây thêm side effect ngoài ý muốn.**

## 20. Bài thực hành: tìm ACK sai trong luồng đặt hàng

**Bối cảnh:** module `ordering` phát `OrderPlaced`. `analytics` ghi metric đơn hàng trong database, `notification` gửi email qua provider và `shippingintegration` xuất message sang broker. Hệ thống cần khôi phục khi lỗi tạm thời nhưng không được nhân đôi chỉ số.

### Phần A — Lập sơ đồ các điểm xác nhận

1. Vẽ event `OrderPlaced(E1)` từ transaction nguồn tới ba listener.
2. Ghi rõ mốc **commit đơn hàng**, **ghi publication**, **bắt đầu listener**, **consumer commit**, **provider ACK**, **broker ACK** và **publication completion**.
3. Chỉ ra các mốc nào mang ý nghĩa *thành công về hạ tầng*, mốc nào là *thành công nghiệp vụ*.
4. Giải thích vì sao `analytics` hoàn thành không đồng nghĩa email và broker đã hoàn thành.

### Phần B — Implement consumer ghi DB an toàn

1. Công bố `ordering.events.OrderPlaced` qua `@NamedInterface("events")`.
2. Viết `analytics` listener nhận event qua `@ApplicationModuleListener`.
3. Trong cùng transaction consumer, ghi dấu `(consumer_name, event_id)` và cập nhật số đơn.
4. Tạo unique constraint để hai lần xử lý cùng event không làm tăng chỉ số hai lần.
5. Cho listener ném lỗi sau khi thao tác nghiệp vụ thất bại, không bắt rồi nuốt lỗi.

### Phần C — Giả lập lỗi quanh ACK

1. Tạo lỗi **trước** consumer commit; xác nhận chưa có marker hoặc business effect.
2. Mô phỏng **sau** commit nhưng **trước** registry completion; xử lý lại E1 và kiểm tra chỉ số không tăng trùng.
3. Với email, giả lập provider trả thành công rồi process crash; mô tả cách dùng idempotency key hoặc đối soát.
4. Với broker, giả lập ACK trước xử lý và ACK sau xử lý; so sánh nguy cơ mất/trùng.
5. Kiểm tra publication pending, retry count, dedupe count và trạng thái DLQ nếu có.

### Phần D — Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng |
| --- | --- |
| Các module chỉ biết hợp đồng công khai | `ApplicationModules.verify()` PASS |
| Publisher phát event đúng | `PublishedEvents` có event và aggregate ID đúng |
| Không phản ứng khi transaction nguồn rollback | Integration test `AFTER_COMMIT` PASS |
| Marker và cập nhật dữ liệu nguyên tử | Transaction test + unique constraint |
| Retry E1 không cộng số liệu lần hai | Test idempotency PASS |
| Listener lỗi không bị ACK nhầm thành công | Publication vẫn chưa hoàn tất hoặc có trạng thái lỗi theo cấu hình |
| Có thể phân biệt broker ACK với consumer completion | Log/metric theo từng điểm |
| Có recovery cho tác vụ quan trọng | Test xử lý lại từ storage sau lỗi |

## 21. Những hiểu nhầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`publishEvent` trả về là event đã được giao đáng tin cậy.” | Chỉ mô tả mức dispatch hiện tại; async, commit, registry và side effect là mốc khác |
| “Database đã commit nghĩa là email chắc chắn được gửi.” | Transaction local không bao trùm email provider |
| “Registry đã lưu publication là listener hoàn tất.” | Publication recorded và completed là hai trạng thái khác |
| “Listener không ném exception nên chắc chắn thành công.” | Handler có thể nuốt lỗi hoặc chỉ submit công việc phụ rồi trả về |
| “ACK broker nghĩa là consumer đã ghi database.” | Producer confirm, consumer ACK và DB commit khác nhau |
| “ACK sau xử lý thì không thể có duplicate.” | Crash sau side effect nhưng trước ACK có thể gây redelivery |
| “ACK trước xử lý thì không thể mất message.” | Đây là cửa sổ mất công việc điển hình khi crash |
| “`@Async` tự tạo điểm xác nhận bền vững.” | In-memory executor không tự lưu durable job |
| “Có Event Publication Registry là exactly-once.” | Recovery có thể xử lý lại publication; consumer vẫn cần idempotency |
| “Chuyển message sang DLQ nghĩa là nghiệp vụ thành công.” | DLQ chỉ chuyển trạng thái xử lý lỗi; business effect có thể chưa xảy ra |
| “Một event ID tương ứng một trạng thái hoàn tất duy nhất.” | Một event có thể có nhiều listener/publication độc lập |
| “Mỗi retry tạo event ID mới không sao.” | Dedupe và truy vết cùng publication trở nên khó khăn |

## 22. Tự kiểm tra

**Câu 1. Điểm xác nhận là gì?**

Là mốc mà một thành phần ghi nhận một điều kiện đã đạt được. Phải chỉ rõ chủ thể, đối tượng, ý nghĩa, tính bền vững và chính sách khi không nhận ACK.

**Câu 2. `publishEvent(...)` trả về thành công có chứng minh listener bất đồng bộ đã xử lý xong không?**

Không. Nó có thể chỉ chứng minh phần dispatch hoặc lập lịch đã diễn ra theo cấu hình. Listener async còn đang chạy hoặc chưa bắt đầu.

**Câu 3. Vì sao ACK trước khi consumer ghi DB có thể làm mất kết quả?**

Vì broker có thể coi message đã hoàn tất và không gửi lại. Nếu consumer crash sau ACK nhưng trước commit, không còn cơ chế tự động phục hồi message ấy.

**Câu 4. Vì sao ACK sau khi consumer ghi DB có thể tạo duplicate?**

Vì consumer có thể commit thành công rồi crash trước ACK. Broker/registry có thể giao lại, nên cần idempotency để không nhân đôi kết quả.

**Câu 5. Với Spring Modulith, Event Publication Registry có thể xác nhận điều gì?**

Theo cấu hình, registry có thể ghi publication và đánh dấu nó đã hoàn tất theo việc listener được hỗ trợ xử lý thành công. Điều đó không tự chứng minh mọi side effect ngoài ứng dụng đã đạt kết quả cuối cùng.

**Câu 6. Listener gọi email provider thành công rồi crash trước completion; làm sao tránh gửi trùng khi retry?**

Ưu tiên dùng idempotency key/tra cứu trạng thái từ provider hoặc workflow gửi có trạng thái bền vững. Nếu provider không hỗ trợ, cần thừa nhận giới hạn bảo đảm và có chính sách xử lý trùng.

**Câu 7. Một sự kiện được cả `notification` và `analytics` nhận; `analytics` hoàn tất có đồng nghĩa `notification` hoàn tất không?**

Không. Mỗi listener/publication có trạng thái và tác dụng phụ riêng; cần theo dõi theo consumer identity.

**Câu 8. Vì sao không nên nuốt exception trong listener quan trọng?**

Vì hạ tầng có thể hiểu method trả về bình thường là xử lý thành công và đánh dấu completion, làm mất cơ hội retry/recovery dù nghiệp vụ chưa hoàn tất.

## 23. Kết luận

**Điểm xác nhận là ranh giới giữa “đã đến một mốc kỹ thuật” và “đã đạt một cam kết cụ thể”.** Trong Spring Modulith, publisher, transaction nguồn, listener sau commit, Event Publication Registry và hạ tầng messaging có thể xác nhận những điều khác nhau. Sự khác biệt giữa **event đã phát**, **publication đã lưu**, **listener đã xử lý**, **transaction consumer đã commit** và **hệ thống bên ngoài đã thực hiện side effect** là nền tảng của thiết kế giao sự kiện đáng tin cậy.

ACK quá sớm có thể làm mất công việc; ACK sau xử lý nhưng không có idempotency có thể gây trùng khi retry. Với các module có yêu cầu reliability cao, hãy dùng **hợp đồng event ổn định, transaction boundary rõ, publication persistence/recovery phù hợp, consumer idempotent và observability theo từng listener**. Quan trọng nhất, luôn viết ra chính xác **ACK xác nhận điều gì và điều gì vẫn chưa được bảo đảm**, thay vì dựa vào tên annotation hoặc một trạng thái “success” chung cho toàn bộ workflow.
