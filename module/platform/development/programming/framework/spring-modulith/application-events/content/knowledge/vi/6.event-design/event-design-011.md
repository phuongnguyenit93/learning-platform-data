# Quy tắc mở rộng event trong Spring Modulith

## 1. Vì sao cần quy tắc mở rộng event?

Khi tổ chức giao tiếp giữa các module bằng **Spring Modulith application events**, chúng ta thường bắt đầu với một sự kiện đơn giản như `OrderConfirmed`. Ban đầu chỉ có module `notifications` lắng nghe để gửi email. Vài tháng sau, hệ thống cần thêm `reporting`, `loyalty`, thay đổi dữ liệu event và có thể phải chuyển một phần sự kiện ra message broker để tích hợp hệ thống bên ngoài.

Nếu event không được thiết kế để mở rộng, mỗi yêu cầu mới có thể làm module phát phải sửa logic liên tục, khiến listener phụ thuộc vào entity nội bộ, phá vỡ consumer cũ hoặc làm những publication chưa xử lý trở nên không đọc được.

**Quy tắc mở rộng event** là tập nguyên tắc giúp:

1. **Mở rộng số bên nhận:** thêm listener mới mà không sửa nghiệp vụ của publisher.
2. **Mở rộng contract:** bổ sung dữ liệu mà vẫn kiểm soát được tác động tới listener hiện tại.
3. **Mở rộng quy trình:** thêm tác vụ hậu commit mà không phá vỡ bất biến nghiệp vụ cần nhất quán ngay.
4. **Mở rộng phạm vi tích hợp:** chọn event được công bố ra ngoài tiến trình và quản lý phiên bản payload.
5. **Mở rộng vận hành:** xử lý nhiều listener, failure, retry, duplicate, event tồn đọng và thay đổi phiên bản ứng dụng.

Bài học thuộc chương **Thiết kế event** của module `SPRING_MODULITH_APPLICATION_EVENTS`. Mục tiêu là thiết kế giao tiếp application events giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ, đồng thời làm rõ vai trò publisher, listener sau commit, event publication registry, retry, kiểm thử và quan sát.

### 1.1. Một luồng đơn giản có thể mở rộng

~~~mermaid
flowchart LR
    Orders[Module orders] --> P[ApplicationEventPublisher]
    P --> E[OrderConfirmed]
    E --> N[notifications listener]
    E --> R[reporting listener mới]
    E --> L[loyalty listener mới]
    E -. Chọn externalize .-> X[Integration adapter]
    X --> B[(Message broker)]
    B --> S[Hệ thống bên ngoài]
~~~

Ở đây, `orders` chỉ biết sự thật **đơn hàng được xác nhận**. Nó không cần gọi `NotificationService`, `ReportingService` hay `LoyaltyService`. Tuy vậy, các listener vẫn có phụ thuộc về **ý nghĩa và cấu trúc event**, nên khả năng mở rộng đòi hỏi quản lý contract cẩn thận.

## 2. Phân biệt các hình thức mở rộng

| Hình thức | Ví dụ | Quy tắc trung tâm |
| --- | --- | --- |
| **Thêm consumer** | Thêm listener của `loyalty` | Không làm publisher biết tên hoặc cách xử lý của listener |
| **Thêm trường vào event** | Thêm `salesChannel` cho `OrderConfirmed` | Xem xét tương thích Java và serialization riêng |
| **Thêm loại event** | Bổ sung `OrderReadyForShipment` | Tạo event mới khi ý nghĩa nghiệp vụ mới thực sự khác |
| **Thay đổi ý nghĩa event** | `OrderConfirmed` từ “đã giữ hàng” thành “chờ giữ hàng” | Coi là thay đổi phá vỡ contract, dù tên/kiểu vẫn giống |
| **Đưa event ra ngoài** | Externalize `OrderConfirmed` tới Kafka | Quản lý schema, routing, version và dữ liệu như public contract |
| **Thay đổi thời điểm xử lý** | Chuyển listener sang hậu commit bất đồng bộ | Đánh giá transaction, consistency, rollback và lỗi |
| **Thêm retry/khôi phục** | Phát lại publication chưa hoàn tất | Consumer cần idempotency; kiểm tra payload event tồn đọng |

Không phải mọi hình thức có cùng rủi ro. Thêm một listener độc lập có thể chỉ ảnh hưởng module nhận; thay đổi ngữ nghĩa của event có thể yêu cầu thiết kế lại tất cả consumer.

## 3. Bảo toàn ngữ nghĩa nghiệp vụ là quy tắc đầu tiên

Một event nên biểu đạt **điều đã xảy ra**, có **chủ sở hữu rõ ràng**, và ý nghĩa không phụ thuộc vào cách một listener xử lý nó.

Ví dụ trong hệ thống thương mại điện tử:

- `OrderCreated`: một đơn hàng đã được tạo.
- `OrderConfirmed`: đơn hàng đã thỏa điều kiện xác nhận của module `orders`.
- `PaymentCaptured`: module `payments` đã ghi nhận việc thu tiền thành công.
- `OrderReadyForShipment`: đơn hàng đã đạt điều kiện bàn giao cho logistics.
- `OrderCancelled`: đơn hàng đã được hủy hợp lệ.

Các sự kiện này có thể liên quan nhau nhưng **không thể xem là đồng nghĩa**. Nếu điều kiện “xác nhận” thay đổi, phải đánh giá liệu event hiện tại còn giữ nguyên ý nghĩa hay không.

### 3.1. Khi nào nên mở rộng event cũ?

Mở rộng một event hiện có thường hợp lý khi:

- Sự thật nghiệp vụ **không đổi**.
- Trường mới chỉ cung cấp thêm ngữ cảnh, chẳng hạn kênh bán hàng, thời điểm hoặc phân loại.
- Consumer cũ vẫn có thể hành xử đúng khi không biết trường mới.
- Dữ liệu mới có thể để trống hoặc có giá trị mặc định hợp lệ đối với message cũ.

Ví dụ: bổ sung `salesChannel` cho `OrderConfirmed` nhưng ý nghĩa “đơn đã xác nhận” hoàn toàn giữ nguyên.

### 3.2. Khi nào nên tạo event mới?

Tạo event mới hợp lý khi:

- Có **mốc nghiệp vụ khác biệt**, như `OrderPaid` khác `OrderReadyForShipment`.
- Quy tắc xác định một kết quả đã thay đổi khiến consumer cũ có thể hiểu sai.
- Consumer có thể cần phản ứng với hai sự thật khác nhau ở những thời điểm khác nhau.
- Payload/contract mới không thể diễn giải an toàn bởi consumer hiện có.

Ví dụ không nên “mở rộng ý nghĩa” `OrderConfirmed` để ngầm nói rằng “đơn đã đóng gói và có thể giao”. Việc xác nhận và việc sẵn sàng giao có thể cách nhau nhiều ngày. Đặt tên event mới phản ánh đúng mốc nghiệp vụ giúp listener không xử lý quá sớm.

### 3.3. Chủ sở hữu không thay đổi khi thêm consumer

Nếu `orders` phát `OrderConfirmed`, module `orders` vẫn sở hữu điều kiện và thời điểm phát event. Việc `loyalty` đăng ký listener mới **không** trao quyền cho nó quyết định khi nào một đơn được xác nhận.

~~~text
orders:     quyết định đơn hàng đã xác nhận hay chưa
notifications: quyết định gửi email như thế nào
reporting:  quyết định cập nhật số liệu ra sao
loyalty:    quyết định tích điểm theo chính sách nào
~~~

Mỗi consumer quản lý dữ liệu và kết quả của mình. Không nên cho listener của `loyalty` sửa trực tiếp `OrderRepository` hoặc yêu cầu publisher đưa thêm chi tiết nội bộ chỉ để thuận tiện tính điểm.

## 4. Mở rộng số listener mà không làm tăng phụ thuộc từ publisher

Spring cung cấp `ApplicationEventPublisher` để phát sự kiện trong cùng application context. Spring Modulith bổ sung cách tổ chức theo module, các listener và cơ chế publication phù hợp khi sử dụng transactional events.

Ví dụ contract được module `orders` công bố:

~~~java
package com.example.shop.orders.events;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Nếu event đặt trong package con `orders.events`, module sở hữu có thể công bố nó qua named interface:

~~~java
// com/example/shop/orders/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.orders.events;
~~~

Để giới hạn những kiểu `reporting` được phép tham chiếu từ `orders`:

~~~java
// com/example/shop/reporting/package-info.java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders::events"
)
package com.example.shop.reporting;
~~~

Một listener nội bộ của `reporting`:

~~~java
package com.example.shop.reporting.internal;

import com.example.shop.orders.events.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class SalesReportingListener {
    private final SalesProjectionService projections;

    SalesReportingListener(SalesProjectionService projections) {
        this.projections = projections;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        projections.recordConfirmedOrder(
            event.eventId(), event.orderId()
        );
    }
}
~~~

Trong ví dụ, `SalesProjectionService` là service nội bộ của `reporting` cần được ứng dụng định nghĩa. `@ApplicationModuleListener` là annotation của Spring Modulith có ngữ nghĩa listener bất đồng bộ, theo transaction và xử lý trong transaction riêng. Cần cấu hình dependency, transaction và khả năng thực thi async đúng với phiên bản Spring đang sử dụng.

Muốn thêm listener `loyalty`, đội phát triển có thể thêm một bean/listener trong module `loyalty` với contract `OrderConfirmed` đã được công bố. Service `orders` **không cần được chỉnh để biết** danh sách consumer, miễn sự kiện hiện tại vẫn mang đủ thông tin và listener không đòi thay đổi semantics.

### 4.1. Không đánh đồng “thêm listener” với “không có chi phí”

Mỗi listener mới vẫn có:

- Thời gian khởi tạo và xử lý riêng.
- Sự phụ thuộc vào schema và ngữ nghĩa của event.
- Rủi ro lỗi, retry, duplicate và backlog riêng.
- Nhu cầu theo dõi trạng thái publication nếu tác vụ quan trọng.
- Khả năng gây tải lên database hoặc dịch vụ ngoài nếu không giới hạn concurrency.

Với `@EventListener` đồng bộ mặc định, listener mới còn có thể làm tăng thời gian của request phát sự kiện và làm transaction nguồn thất bại nếu lỗi lan truyền. Khi chuyển sang transactional listener hậu commit, cần xem xét tính nhất quán cuối cùng và xử lý lỗi độc lập.

## 5. Quy tắc mở rộng payload: tương thích không chỉ là thêm một trường

Trong Java, mở rộng record/class **là thay đổi API của mã nguồn**. Khi externalize sang JSON/Avro/Protobuf, mở rộng payload còn là thay đổi **wire contract**. Hai loại tương thích này khác nhau.

### 5.1. Ví dụ event nội bộ ban đầu

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Code phát event:

~~~java
events.publishEvent(new OrderConfirmed(
    UUID.randomUUID(),
    orderId,
    Instant.now()
));
~~~

Giả sử cần thêm thông tin kênh bán hàng:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    String salesChannel
) {}
~~~

**Lưu ý quan trọng:** thêm `salesChannel` vào record khiến constructor ba tham số được Java sinh tự động **không còn tồn tại**. Những đoạn code tạo `new OrderConfirmed(eventId, orderId, occurredAt)` phải cập nhật hoặc được cung cấp constructor tương thích. Các consumer sử dụng accessor cũ như `orderId()` có thể không cần đổi mã nguồn, nhưng ứng dụng vẫn phải build và chạy lại một cách nhất quán.

Nếu cần giai đoạn chuyển đổi, có thể cung cấp constructor ba tham số:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt,
    String salesChannel
) {
    public OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
    ) {
        this(eventId, orderId, occurredAt, "UNKNOWN");
    }
}
~~~

Constructor phụ không tự bảo đảm tương thích nhị phân với tất cả code đã build sẵn hoặc với serializer đang dùng. Ở ứng dụng modular monolith, các module thường được build và phát hành cùng nhau, nên có thể kiểm tra lại toàn bộ code. **Không nên vì thế mà bỏ qua dữ liệu event đã lưu dưới dạng serialized payload** trong registry hoặc consumer ngoài ứng dụng.

### 5.2. Bảng phân loại thay đổi contract

| Thay đổi | Ảnh hưởng thường gặp | Hướng xử lý |
| --- | --- | --- |
| Thêm trường tùy chọn | Consumer cũ có thể bỏ qua nếu deserializer hỗ trợ; producer và code Java cần cập nhật | Cung cấp default/nullable rõ ràng, kiểm thử tương thích |
| Thêm trường bắt buộc | Payload cũ thiếu trường, consumer mới có thể từ chối | Version mới hoặc chiến lược đọc giá trị cũ an toàn |
| Đổi tên trường | Consumer đọc trường cũ bị lỗi hoặc mất dữ liệu | Giai đoạn song song, alias/schema migration nếu được hỗ trợ |
| Xóa trường | Consumer vẫn đang sử dụng trường đó sẽ lỗi | Deprecate, theo dõi sử dụng rồi mới loại bỏ |
| Đổi kiểu dữ liệu | Thay đổi serializer, validation hoặc phép tính | Kiểm tra khả năng đọc của cả producer/consumer; thường cần version |
| Đổi đơn vị | `amount` từ VND sang đơn vị nhỏ nhất | Coi là thay đổi ý nghĩa; tạo trường mới nêu rõ đơn vị |
| Đổi tên loại event | Subscription/routing và hành vi consumer có thể bị ảnh hưởng | Chính sách chuyển đổi hoặc event type mới |
| Đổi thời điểm phát | Event có thể đến trước điều kiện nghiệp vụ mà consumer kỳ vọng | Đánh giá lại semantics, tạo event mới nếu cần |
| Đổi cấu trúc package Java | Listener nội bộ và dữ liệu serialized theo class name có thể bị ảnh hưởng | Dùng API công khai ổn định, kiểm tra đọc lại publication cũ |
| Thêm consumer | Publisher có thể giữ nguyên | Kiểm tra listener, concurrency, idempotency và quan sát |

**Không có một thay đổi “an toàn tuyệt đối” cho mọi serializer.** Ví dụ JSON consumer cấu hình reject unknown properties có thể lỗi khi nhận trường mới; Avro/Protobuf có nguyên tắc schema evolution riêng; sự tương thích phải được kiểm thử trên đúng codec/contract.

### 5.3. Event JSON minh họa trước và sau khi mở rộng

Contract V1:

~~~json
{
  "eventId": "9f8d3bb0-3d26-4593-b293-9fc9cd2a0ac3",
  "eventType": "orders.confirmed",
  "schemaVersion": 1,
  "orderId": "e8a71a83-aeb9-47b3-b8de-3c31a2fd5eef",
  "occurredAt": "2026-11-25T08:00:00Z"
}
~~~

V2 mở rộng một trường tùy chọn:

~~~json
{
  "eventId": "8c3f6e8a-359c-4305-acba-f4df5bf4cf32",
  "eventType": "orders.confirmed",
  "schemaVersion": 2,
  "orderId": "e8a71a83-aeb9-47b3-b8de-3c31a2fd5eef",
  "occurredAt": "2026-11-25T08:05:00Z",
  "salesChannel": "MOBILE"
}
~~~

Đây là **envelope minh họa do nhóm tự thiết kế**, không phải cấu trúc JSON do Spring Modulith áp đặt. Trong hệ thống thật, không nhất thiết tăng major `schemaVersion` cho mỗi trường tùy chọn: cách đánh phiên bản dựa trên quy ước tương thích của tổ chức, schema registry và transport. Mẫu V1/V2 giúp thực hành kiểm tra migration.

Với consumer cũ:

- Nếu được thiết kế để bỏ qua trường chưa biết, consumer vẫn có thể xử lý V2.
- Nếu kiểm tra schema chính xác tuyệt đối, consumer có thể từ chối V2.
- Nếu nghiệp vụ consumer đang phụ thuộc vào một giá trị mặc định sai, dù deserialize thành công vẫn có thể tính sai.

Với consumer mới:

- Phải diễn giải payload V1 thiếu `salesChannel` theo chính sách rõ ràng, ví dụ `UNKNOWN` hoặc không áp dụng chức năng mới.
- Không được ngầm biến trường thiếu thành một giá trị làm thay đổi tiền, tồn kho hoặc điều kiện xác nhận.
- Cần kiểm thử cả V1 lẫn V2 nếu còn message đang lưu hoặc publication chờ phát.

## 6. Tách contract bên trong module và contract ra hệ thống ngoài

Một quy tắc mở rộng quan trọng là không để lựa chọn của consumer bên ngoài điều khiển trực tiếp mô hình domain nội bộ. Spring Modulith xử lý **application events** trong ứng dụng, đồng thời có cơ chế **event externalization** để chọn một số event và đưa ra transport hỗ trợ.

### 6.1. Hai chiến lược thiết kế

**Chiến lược A — Externalize trực tiếp event nghiệp vụ:** đơn giản khi record đã chứa dữ liệu ổn định, đủ cho consumer, không lộ nội bộ. Đổi field của event cần xem xét cả listener nội bộ và consumer ngoài.

**Chiến lược B — Tách integration DTO:** một lớp mapping chuyển `OrderConfirmed` thành một DTO bên ngoài như `OrderConfirmedIntegrationV1`. Domain event vẫn diễn đạt sự thật nghiệp vụ; schema ngoài có version, format và vòng đời riêng.

~~~mermaid
flowchart LR
    Service[orders service] --> Internal[OrderConfirmed - domain event]
    Internal --> Local[Internal listeners]
    Internal --> Mapping[Mapping / externalization policy]
    Mapping --> Contract[orders.confirmed.v1 integration payload]
    Contract --> Broker[(Broker)]
    Broker --> Consumer[External consumer]
~~~

Nếu consumer ngoài cần thêm trường hiển thị mà domain event không cần, việc mở rộng DTO có thể giảm ảnh hưởng ngược lên domain. Nếu phải tra cứu dữ liệu bổ sung ở bước mapping, cần tính tới transaction, độ nhất quán và thời điểm dữ liệu sẵn có; không nên tùy tiện đọc trạng thái có thể thay đổi rồi tuyên bố đó là snapshot tại thời điểm phát.

### 6.2. Một integration DTO tường minh

~~~java
package com.example.shop.orders.integration;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmedIntegrationV1(
    UUID eventId,
    String eventType,
    int schemaVersion,
    UUID orderId,
    Instant occurredAt,
    String salesChannel
) {}
~~~

Adapter ánh xạ event nguồn thành DTO:

~~~java
final class OrderIntegrationMapper {
    private OrderIntegrationMapper() {}

    static OrderConfirmedIntegrationV1 toV1(
        OrderConfirmed source,
        String salesChannel
    ) {
        return new OrderConfirmedIntegrationV1(
            source.eventId(),
            "orders.confirmed",
            1,
            source.orderId(),
            source.occurredAt(),
            salesChannel
        );
    }
}
~~~

Đoạn code có tính minh họa; `OrderConfirmed` phải được import, còn `salesChannel` phải đến từ nguồn dữ liệu có ngữ nghĩa đáng tin cậy. Nếu gắn `V1` lên DTO nhưng thay đổi schema phá vỡ tương thích, tên `V1` sẽ gây hiểu nhầm: cần cơ chế version và migration thống nhất.

Spring Modulith cung cấp cơ chế lựa chọn, ánh xạ và định tuyến event được externalize. API cấu hình cụ thể phụ thuộc phiên bản và loại adapter; việc có DTO riêng không tự cấu hình mapping, serialization hoặc broker. Cần kết nối adapter bằng cấu hình/code phù hợp, kiểm thử với hạ tầng đang dùng.

### 6.3. Contract công khai không đồng nghĩa với entity công khai

Không nên tạo event như sau:

~~~java
// Ví dụ phản diện: làm rò rỉ model persistence
public record OrderConfirmed(OrderJpaEntity order) {}
~~~

Entity có thể chứa:

- Lazy relationship khiến consumer hoặc serializer gặp lỗi khi truy cập.
- State thay đổi theo thời gian, không còn là snapshot của thời điểm event.
- Thông tin cá nhân/nhạy cảm không cần được gửi tới các consumer.
- Chi tiết database và quy tắc nội bộ mà module khác không nên phụ thuộc.

Nên truyền định danh nghiệp vụ, dữ liệu đã được lựa chọn và snapshot bất biến cần thiết. Khi consumer phải truy vấn thêm, hãy cung cấp API đọc công khai có contract và quyền truy cập rõ ràng.

## 7. Duy trì ranh giới module khi mở rộng

Spring Modulith hỗ trợ nhận diện application module theo package và kiểm tra sự phụ thuộc giữa các module. Khi mở rộng, hãy giữ nguyên nguyên tắc:

1. Module phát sở hữu event và thời điểm phát.
2. Module nhận chỉ import contract công khai hoặc named interface của module phát.
3. Listener không truy cập repository/implementation nội bộ của module phát.
4. Module nhận sở hữu xử lý hậu quả, lưu trạng thái và cơ chế retry của mình.
5. Thay đổi định nghĩa API/event phải kèm kiểm tra những module phụ thuộc vào nó.

Ví dụ:

~~~text
com.example.shop
├── orders
│   ├── OrderOperations.java
│   ├── events
│   │   ├── package-info.java  (@NamedInterface("events"))
│   │   └── OrderConfirmed.java
│   └── internal
│       ├── OrderManagement.java
│       └── OrderRepository.java
├── notifications
│   ├── package-info.java
│   └── internal/OrderNotificationListener.java
├── reporting
│   └── internal/SalesReportingListener.java
└── loyalty
    └── internal/LoyaltyListener.java
~~~

Khi module `loyalty` thêm listener, nó được phép phụ thuộc vào `orders::events` nếu cấu hình ràng buộc cho phép. Nó **không** được import `orders.internal.OrderRepository` chỉ để lấy thêm thông tin cần tính điểm.

Kiểm tra kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTest {
    @Test
    void validatesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`modules.verify()` có thể phát hiện vi phạm dependency theo mô hình đã khai báo; nó không tự kiểm tra tính tương thích của JSON bên ngoài, thứ tự message, giao dịch hoặc idempotency.

## 8. Mở rộng event trong bối cảnh transaction và thời điểm xử lý

Sự kiện chỉ nên mô tả một sự thật đã thực sự được xác lập theo quy tắc nghiệp vụ. Nếu `orders` thay đổi trạng thái trong transaction, việc một listener chạy **trước commit** có thể dẫn đến kết quả sai khi transaction sau đó rollback.

### 8.1. So sánh các listener khi thêm tác vụ mới

| Cơ chế | Ngữ nghĩa chính | Rủi ro khi mở rộng |
| --- | --- | --- |
| `@EventListener` mặc định | Thường đồng bộ ngay lúc phát event | Listener mới có thể tăng latency hoặc làm hỏng transaction nguồn nếu exception lan ra |
| `@TransactionalEventListener(AFTER_COMMIT)` | Thực thi sau commit thành công của transaction nguồn | Tác vụ ngoài transaction nguồn; lỗi hậu commit cần quản lý riêng |
| `@ApplicationModuleListener` | Cách tiện dụng của Spring Modulith cho transactional listener chạy bất đồng bộ trong transaction riêng | Cần idempotency, observability và chiến lược recovery phù hợp |

Ví dụ, gửi email, cập nhật báo cáo hoặc tích điểm có thể là tác vụ hậu commit nếu cho phép kết quả cuối cùng đến chậm. Ngược lại, kiểm tra tồn kho bắt buộc trước khi xác nhận đơn không nên chỉ dựa vào listener async chạy sau commit.

### 8.2. Mỗi listener cần một phương án lỗi

Thêm một listener đồng nghĩa thêm một nơi có thể thất bại:

~~~mermaid
sequenceDiagram
    participant O as orders
    participant TX as Transaction
    participant N as notifications
    participant R as reporting
    participant L as loyalty

    O->>TX: Update order + publish OrderConfirmed
    TX-->>O: Commit thành công
    O-->>N: Event after commit
    O-->>R: Event after commit
    O-->>L: Event after commit
    N-->>N: Hoàn tất
    R-->>R: Thất bại tạm thời
    L-->>L: Hoàn tất
    Note over R: Retry publication của reporting nếu cấu hình
~~~

Không nên để một listener gửi email lỗi làm thay đổi sự thật “đơn đã xác nhận” đã commit. Các module nhận cần thể hiện rõ trạng thái đang xử lý, đã hoàn tất hoặc cần retry, tùy nghiệp vụ.

## 9. Publication registry: mở rộng còn phải xét event tồn đọng

Khi Spring Modulith sử dụng **event publication registry** với backend lưu trữ phù hợp, hệ thống có thể theo dõi publication dành cho các transactional listeners và ghi nhận khi từng listener xử lý thành công.

Một event có ba listener có thể tương ứng với **ba publication độc lập**. Listener `notifications` thành công không có nghĩa `reporting` đã hoàn tất. Những publication chưa hoàn tất có thể được xem xét phát lại theo API/chính sách cấu hình tương ứng.

### 9.1. Tại sao nâng cấp schema có thể gây sự cố?

Giả sử:

1. `OrderConfirmed` phiên bản cũ được ghi vào registry.
2. `reporting` bị lỗi nên publication còn dang dở.
3. Hệ thống deploy phiên bản mới đã đổi tên lớp, xóa field hoặc thay đổi kiểu dữ liệu.
4. Cơ chế resubmit cố đọc payload cũ bằng serializer/model mới.

Nếu serialization không tương thích, publication có thể không giải mã hoặc listener có thể diễn giải sai dữ liệu. Đây là lý do **kiểm tra record/class Java hiện tại thôi chưa đủ**.

### 9.2. Quy tắc an toàn khi thay đổi event có publication tồn đọng

- Kiểm tra loại sự kiện và định dạng mà registry/backend đang lưu.
- Xác định còn bao nhiêu publication chưa hoàn tất của loại event sắp sửa thay đổi.
- Bảo đảm phiên bản code mới có thể đọc payload cũ, hoặc có kế hoạch migration rõ ràng.
- Thử resubmit publication cũ trong môi trường kiểm thử tương thích với backend thật.
- Nếu đổi package/class name, cân nhắc ảnh hưởng tới type discriminator/serialization metadata.
- Tránh xóa listener cũ mà không có kế hoạch cho publication đang chờ listener đó.
- Đừng biến “retry thành công” thành việc tạo **nghiệp vụ mới khác ý nghĩa** ban đầu.

Các bước cụ thể phụ thuộc cách cấu hình registry (JDBC, JPA, MongoDB hoặc backend được hỗ trợ), phiên bản Spring Modulith và serializer sử dụng. Registry giúp quản lý trạng thái xử lý **không tự giải quyết mọi vấn đề schema evolution hoặc dữ liệu lịch sử**.

### 9.3. Retry có thể tạo tác dụng phụ lặp

Một listener có thể gửi email thành công nhưng crash trước khi publication được đánh dấu hoàn tất. Lần resubmit tiếp theo có thể gửi lại email.

Ví dụ khóa idempotency:

~~~text
eventId = "evt-123"

notifications:
  nhận evt-123 lần 1
  provider gửi email thành công
  ứng dụng crash trước khi đánh dấu hoàn tất

notifications:
  nhận lại evt-123
  kiểm tra hoặc sử dụng idempotency key
  không gửi trùng nếu đã xử lý thành công
~~~

Chỉ lưu `eventId` trong bộ nhớ không đủ nếu ứng dụng restart hoặc chạy nhiều replica. Việc kiểm tra và ghi nhận event đã xử lý nên dựa trên dữ liệu bền vững, unique constraint hoặc cơ chế đồng bộ đáng tin cậy phù hợp. Với hệ thống bên ngoài, cần idempotency key được đối tác hỗ trợ hoặc quy trình đối soát.

## 10. Thiết kế xử lý lặp, event đến muộn và sai thứ tự

Mở rộng từ một listener sang nhiều consumer đồng thời thường làm các vấn đề **duplicate**, **ordering** và **concurrency** rõ ràng hơn.

### 10.1. Event ID và aggregate version giải quyết vấn đề khác nhau

| Trường | Mục đích |
| --- | --- |
| `eventId` | Nhận biết một lần phát sự kiện cụ thể; hỗ trợ loại bỏ xử lý lặp |
| `aggregateId` hoặc `orderId` | Nhận biết aggregate nghiệp vụ liên quan |
| `aggregateVersion` | Thể hiện thứ tự thay đổi của cùng aggregate nếu hệ thống nguồn tạo nhất quán |
| `occurredAt` | Thời điểm sự kiện phát sinh; hữu ích cho audit, không thay thế sequence |
| `correlationId` | Nối các sự kiện trong một luồng yêu cầu hoặc quy trình |
| `causationId` | Chỉ ra event/command làm phát sinh một event mới khi có mô hình tương ứng |

Hai event khác `eventId` có thể thuộc cùng một `orderId`; nhận lại cùng `eventId` là duplicate của một event, còn nhận event cùng aggregate với version nhỏ hơn là vấn đề **stale/out-of-order**. Không nên xử lý cả hai bằng một kiểm tra thời gian đơn giản.

### 10.2. Ví dụ cập nhật projection có version

~~~java
// Minh họa logic nghiệp vụ; repository và transaction được định nghĩa
// trong module reporting.
void apply(OrderStatusChanged event) {
    var projection = projections.find(event.orderId());
    if (projection != null
            && event.aggregateVersion() <= projection.version()) {
        return; // Event trùng hoặc cũ hơn trạng thái đã áp dụng.
    }
    projections.save(
        new OrderView(
            event.orderId(),
            event.newStatus(),
            event.aggregateVersion()
        )
    );
}
~~~

Đoạn mã trên **chưa đủ để an toàn khi nhiều luồng xử lý đồng thời**: cần transaction, optimistic locking hoặc unique/compare-and-set để hai lần cập nhật không ghi đè sai. Ngoài ra, bỏ qua version thiếu còn tùy logic: một số nghiệp vụ cần xử lý đủ các event tuần tự, không thể nhảy thẳng tới trạng thái mới.

### 10.3. Khi externalize sự kiện

Với Kafka, routing key theo `orderId` có thể giúp nhóm các event của cùng đơn vào một partition khi producer có partitioning nhất quán. Thứ tự trong một partition không bảo đảm thứ tự **toàn cục** giữa các partition, topic, đường retry hoặc nhiều source. Consumer ngoài phải tự xác định chiến lược version/state-machine và idempotency cần thiết.

Không nên giả định “đúng một lần” end-to-end chỉ vì message broker hỗ trợ transaction. Producer, registry, broker, consumer database và các dịch vụ ngoài vẫn có những điểm lỗi độc lập.

## 11. Versioning và chính sách ngừng hỗ trợ contract

Khi event được dùng bởi nhiều module hoặc hệ thống ngoài, cần xác định **vòng đời** của contract.

### 11.1. Một quy trình expand → migrate → contract

~~~mermaid
flowchart LR
    A[Khảo sát consumer hiện có] --> B[Expand: thêm trường/type mới tương thích]
    B --> C[Deploy consumer đọc được cả cũ và mới]
    C --> D[Migrate: producer phát contract mới]
    D --> E[Theo dõi backlog/publication cũ]
    E --> F[Contract: ngừng contract cũ có kiểm soát]
~~~

Ví dụ cần đổi `totalAmount` từ số thực sang số tiền ở đơn vị nhỏ nhất:

1. **Khảo sát:** consumer nào đang sử dụng `totalAmount`, serializer nào được dùng?
2. **Expand:** bổ sung `totalAmountMinor` kèm `currency`, giữ `totalAmount` trong giai đoạn chuyển đổi nếu khả thi.
3. **Consumer migration:** consumer mới hiểu hai biểu diễn và ưu tiên trường mới.
4. **Producer migration:** phát dữ liệu mới cho message tương lai; xác minh công thức làm tròn, đơn vị và dữ liệu lịch sử.
5. **Backlog:** kiểm tra những message cũ còn trên broker/registry trước khi loại mã đọc cũ.
6. **Contract:** ngừng trường cũ sau khi đã kiểm chứng mọi consumer phù hợp.

Việc giữ đồng thời cả hai trường là một lựa chọn migration, không phải yêu cầu phổ quát; nếu dữ liệu cũ không thể diễn giải đáng tin cậy, cần event type/schema version mới rõ ràng.

### 11.2. Phân biệt schema version và semantic version

Một serializer có thể đọc được payload nhưng consumer vẫn sai nghiệp vụ nếu ý nghĩa thay đổi. Ví dụ:

- V1: `OrderConfirmed` chỉ phát sau khi tồn kho đã được giữ thành công.
- V2: `OrderConfirmed` phát ngay khi nhận yêu cầu, trước khi giữ hàng.

JSON có thể **giống hệt nhau**, nhưng consumer giao vận xử lý V2 sẽ bắt đầu quá sớm. Cần **event khác** phản ánh trạng thái mới hoặc thay đổi contract được thông báo, migration và kiểm thử theo quy trình nghiệp vụ.

Tên event là một phần của lời hứa ý nghĩa; không nên tái sử dụng tên cũ cho sự thật nghiệp vụ mới.

### 11.3. Ghi lại contract như một tài sản chung

Một danh mục event tối thiểu có thể gồm:

| Thuộc tính | Ví dụ |
| --- | --- |
| Event type | `orders.confirmed` |
| Module sở hữu | `orders` |
| Ý nghĩa | Đơn được xác nhận hợp lệ theo quy tắc hiện hành |
| Thời điểm phát | Trong transaction thay đổi trạng thái đơn, xử lý bên nhận sau commit |
| Các trường cần thiết | `eventId`, `orderId`, `occurredAt` |
| Consumer nội bộ | `notifications`, `reporting`, `loyalty` |
| Consumer bên ngoài | `shipping-service` nếu được externalize |
| Chính sách version | Đảm bảo đọc schema cũ trong thời gian chuyển tiếp |
| Chính sách lỗi | Registry/outbox cho producer, idempotency của consumer |
| Chủ sở hữu phê duyệt thay đổi | Nhóm phụ trách nghiệp vụ `orders` |

Danh mục giúp nhóm phát hiện sớm thay đổi ảnh hưởng nhiều consumer. Không nhất thiết phải triển khai một hệ thống quản trị phức tạp; tài liệu có thể nằm cùng mã nguồn và được kiểm tra trong quá trình review.

## 12. Quy tắc bảo mật khi event ngày càng phong phú

Việc “thêm cho đủ dữ liệu” có thể khiến event chứa những thông tin consumer không cần:

- Email, địa chỉ nhà và số điện thoại.
- Token truy cập, khóa xác thực hoặc dữ liệu thanh toán nhạy cảm.
- Toàn bộ entity/aggregate gồm cả lịch sử nội bộ.
- Trường nội bộ dùng để tính giá, chấm điểm rủi ro hoặc kiểm soát gian lận.

Quy tắc thực hành:

1. Chỉ thêm trường khi có **nhu cầu nghiệp vụ đã được xác định**.
2. Với consumer nội bộ, xem xét API công khai hoặc snapshot dữ liệu phù hợp thay vì import entity.
3. Với consumer ngoài, áp dụng phân quyền topic/queue và chính sách retention theo loại dữ liệu.
4. Không ghi payload nhạy cảm nguyên văn vào log/trace để debug.
5. Khi field mới thay đổi phạm vi chia sẻ dữ liệu, cần đánh giá lại các consumer hiện có, không chỉ kiểm tra compiler.

Mở rộng event thành công còn phải giữ **ranh giới thông tin**, chứ không chỉ ranh giới package Java.

## 13. Kiểm thử khả năng mở rộng

### 13.1. Kiểm thử module phát

Với `orders`, cần xác minh:

- Chỉ phát `OrderConfirmed` khi các điều kiện xác nhận hợp lệ.
- Không phát ra kết quả nghiệp vụ giả khi transaction rollback.
- Event có định danh, thời điểm, dữ liệu tối thiểu và ngữ nghĩa đúng.
- Thêm listener mới không đòi sửa hành vi nghiệp vụ của `orders`.

Spring Modulith có `@ApplicationModuleTest` để kiểm thử theo ranh giới module; hỗ trợ kiểm tra các event được phát (chẳng hạn qua `PublishedEvents` theo API của phiên bản đang dùng).

### 13.2. Kiểm thử contract

| Kiểm thử | Mục đích |
| --- | --- |
| Producer V2 → consumer V1 | Consumer cũ có chấp nhận thêm trường không? |
| Producer V1 → consumer V2 | Consumer mới xử lý được field thiếu không? |
| Event trước và sau refactor class/package | Payload lưu bền cũ có thể deserialize không? |
| Event có enum/giá trị chưa biết | Consumer có fallback an toàn hay chuyển sang xử lý lỗi? |
| Event type cũ và mới cùng tồn tại | Có double-count, gửi trùng email hay tạo hai shipment không? |
| Consumer khác nhau đọc cùng một event | Mỗi bên chỉ xử lý phần trách nhiệm của mình? |

Không nên chỉ kiểm tra object Java sau khi sửa record; cần chạy contract test với **codec thực tế** như Jackson, Avro, Protobuf và cấu hình của phía nhận nếu có.

### 13.3. Kiểm thử transaction và publication

Các trường hợp quan trọng:

1. Transaction nguồn commit, listener hậu commit xử lý thành công.
2. Transaction nguồn rollback, không có tác vụ hậu commit dựa trên kết quả chưa tồn tại.
3. Listener thất bại sau commit, publication còn có thể được quan sát/khôi phục theo cấu hình.
4. Resubmit cùng `eventId`, consumer không tạo tác dụng phụ lặp.
5. Deploy code mới trong khi registry còn publication dùng payload/event type cũ.
6. Có nhiều listener, một listener lỗi không che mất trạng thái xử lý của listener khác.
7. Khi externalize, broker tạm ngừng và hoạt động lại; event được xử lý phù hợp với chính sách retry.

`ApplicationModules.of(...).verify()` kiểm tra **cấu trúc phụ thuộc**. Nó không thể thay thế các bài test transaction, codec, hạ tầng message hoặc vận hành đa instance.

### 13.4. Quan sát sự tăng trưởng

Theo dõi số lượng event phát, thời gian xử lý listener, publication chờ, lỗi retry, tỷ lệ duplicate và backlog consumer. Khi thêm listener, quan sát metric theo **event type và consumer/module** thay vì chỉ một số lỗi tổng cộng của toàn ứng dụng.

Ví dụ log có cấu trúc do ứng dụng tự thiết kế:

~~~json
{
  "eventType": "orders.confirmed",
  "eventId": "e6b43f7d-5c49-4f7b-a890-24e0155da141",
  "module": "reporting",
  "listener": "SalesReportingListener",
  "status": "retryable_failure",
  "attempt": 2
}
~~~

Tên trường/trạng thái minh họa không phải schema log mặc định của Spring Modulith. Tránh ghi dữ liệu cá nhân vào log; dùng `eventId` và trace/correlation ID phù hợp.

## 14. Ví dụ: phát triển OrderConfirmed qua ba giai đoạn

**Bối cảnh:** Ban đầu ứng dụng chỉ gửi email khi đơn được xác nhận. Sau đó cần thêm tích điểm thành viên và báo cáo kênh bán hàng; cuối cùng phải gửi event sang hệ thống giao vận ngoài ứng dụng.

### Giai đoạn A — Một sự kiện, một listener

~~~text
orders:
  OrderConfirmed(eventId, orderId, occurredAt)

notifications:
  on(OrderConfirmed) → send confirmation
~~~

Ranh giới `orders` sở hữu trạng thái, `notifications` sở hữu gửi thông báo.

### Giai đoạn B — Thêm listener và dữ liệu tùy chọn

~~~text
orders:
  OrderConfirmed(eventId, orderId, occurredAt, salesChannel?)

notifications:
  on(OrderConfirmed) → send confirmation

reporting:
  on(OrderConfirmed) → update sales by channel

loyalty:
  on(OrderConfirmed) → award points
~~~

Cần bảo đảm `salesChannel` có giá trị hợp lệ và được mô hình hóa rõ cho những đơn cũ. `reporting` có thể dùng nhóm `UNKNOWN` trong thống kê nếu chính sách nghiệp vụ cho phép; không nên tự đoán là `WEB`.

`loyalty` cần chống tích điểm trùng khi listener retry. `notifications` có thể tiếp tục sử dụng `orderId` và không cần biết `salesChannel`.

### Giai đoạn C — Externalize event cho logistics

~~~text
orders event
    ├── notifications
    ├── reporting
    ├── loyalty
    └── integration mapper → orders.confirmed.v1 → broker → shipping
~~~

Trước khi externalize:

- Kiểm tra `OrderConfirmed` có thật sự là mốc nghiệp vụ cho phép tạo vận đơn không. Nếu phải chờ đóng gói, tạo `OrderReadyForShipment` thay vì thay đổi ngầm ý nghĩa event cũ.
- Định nghĩa integration DTO/schema độc lập nếu consumer ngoài có vòng đời nâng cấp riêng.
- Cấu hình externalization và backend publication/recovery phù hợp.
- Thiết kế consumer shipping chống tạo shipment trùng, xử lý event cũ và lỗi schema.
- Kiểm thử điều kiện rollback, broker lỗi, publication tồn đọng, duplicate và ordering.

### Bảng quyết định cuối cùng

| Yêu cầu | Quyết định thiết kế |
| --- | --- |
| Thêm email SMS khi đơn xác nhận | Thêm consumer hoặc thay đổi phần của `notifications` |
| Thêm tích điểm | Thêm listener `loyalty`, idempotent theo `eventId` hoặc khóa nghiệp vụ |
| Bổ sung kênh bán hàng vào báo cáo | Mở rộng contract có default/compatibility plan |
| Báo hệ thống logistics bên ngoài | Externalize contract đã chọn, quản lý schema/version |
| Bắt đầu giao hàng chỉ khi đóng gói xong | Tạo event mới phản ánh mốc `ReadyForShipment` |
| Đổi tên package `orders.events` | Kiểm tra module dependencies và serialized publication cũ |
| Listener cũ bị lỗi trước khi deploy | Kiểm tra compatibility và khả năng resubmit trước khi loại contract |

## 15. Những phản ví dụ nên tránh

**Phản ví dụ 1 — Mỗi consumer mới kéo theo lời gọi mới trong publisher.**

~~~java
// Publisher bị gắn trực tiếp với từng bên nhận.
notifications.sendOrderConfirmed(order);
reporting.recordOrder(order);
loyalty.addPoints(order);
~~~

Thiết kế này khiến `orders` biết chi tiết tác vụ hậu quả và có thể kéo các lỗi ngoài nghiệp vụ vào transaction. Event giúp bên phát công bố sự thật, listener tự quản lý trách nhiệm của mình. Tuy nhiên, vẫn giữ lời gọi API trực tiếp cho những điều kiện cần kết quả đồng bộ trước commit.

**Phản ví dụ 2 — Biến event cũ thành một mệnh lệnh khác ý nghĩa.**

Đổi `OrderConfirmed` thành “yêu cầu xác nhận” nhưng vẫn giữ tên khiến consumer tin đơn đã hợp lệ, dẫn tới gửi email/giao hàng quá sớm. Thay vì vậy, dùng command/đối tượng yêu cầu hoặc event mới có tên và ý nghĩa chuẩn.

**Phản ví dụ 3 — Thay đổi schema rồi xóa ngay code đọc cũ.**

Các publication chưa hoàn tất và message còn trên broker có thể mang payload cũ. Cần khảo sát backlog, migrate, kiểm thử serializer và áp dụng chu trình expand → migrate → contract.

**Phản ví dụ 4 — Chuyển toàn bộ entity JPA qua event để tránh mở rộng schema.**

Điều này làm lộ cấu trúc persistence và khiến consumer phụ thuộc vào state nội bộ có thể thay đổi. Hãy dùng event DTO bất biến với dữ liệu được lựa chọn.

**Phản ví dụ 5 — Dùng retry nhưng không có idempotency.**

Retry có thể gửi hai email, cộng hai lần điểm thưởng hoặc tạo hai shipment. Mỗi module nhận phải kiểm soát xử lý trùng và lỗi theo khả năng lưu bền của mình.

**Phản ví dụ 6 — Coi `@ApplicationModuleListener` là giải pháp cho mọi tính nhất quán.**

Listener hậu commit không thể thay thế điều kiện bắt buộc phải đúng trước khi transaction nguồn kết thúc. Chọn đồng bộ hay bất đồng bộ theo bất biến nghiệp vụ.

**Phản ví dụ 7 — Tự cho rằng thêm trường JSON luôn tương thích.**

Consumer strict schema, enum chưa biết, field bắt buộc hoặc serializer khác có thể từ chối payload. Hãy thử compatibility trên đúng codec và code thực tế.

## 16. Bài tập thực hành mở rộng event

### Bài toán

Một Spring Modulith có ba module `orders`, `notifications` và `reporting`. Event hiện tại:

~~~java
public record OrderConfirmed(
    UUID eventId,
    UUID orderId,
    Instant occurredAt
) {}
~~~

Sau khi triển khai, doanh nghiệp yêu cầu:

1. Bổ sung `loyalty` để tích điểm khi xác nhận đơn.
2. Thống kê doanh thu theo `salesChannel`, nhưng một số đơn cũ chưa có dữ liệu này.
3. Gửi sự kiện tới hệ thống logistics chạy ngoài ứng dụng.
4. Đảm bảo listener `loyalty` không cộng điểm hai lần khi publication được phát lại.
5. Duy trì khả năng khôi phục các publication trước lần nâng cấp còn dang dở.
6. Chỉ tạo lệnh giao hàng khi đơn đạt trạng thái `READY_FOR_SHIPMENT`.

### Nhiệm vụ của người học

- **Thiết kế ranh giới:** nêu module nào sở hữu sự thật phát sự kiện, dữ liệu và tác vụ xử lý.
- **Chọn event:** quyết định có giữ `OrderConfirmed` và cần thêm `OrderReadyForShipment` hay không.
- **Thiết kế contract:** xác định trường cũ, trường mới, default và kế hoạch schema evolution.
- **Thiết kế listener:** nêu annotation/ngữ nghĩa transaction, dữ liệu do từng module sở hữu, cách retry và idempotency.
- **Thiết kế externalization:** xác định event nào đưa ra broker và chuẩn hóa payload/schema version.
- **Thiết kế kiểm thử:** viết danh sách case cover schema cũ/mới, rollback, retry, duplicate và broker ngừng hoạt động.
- **Thiết kế vận hành:** xác định thông tin cần theo dõi để chẩn đoán publication chưa hoàn tất.

### Gợi ý tự đối chiếu

| Vấn đề | Một lựa chọn có cơ sở |
| --- | --- |
| Tích điểm | Thêm listener trong `loyalty`, lưu dấu xử lý theo ID ổn định và unique constraint |
| Thống kê kênh | Thêm trường tùy chọn có cách diễn giải `UNKNOWN`; kiểm thử cả payload cũ và mới |
| Gửi logistics | Ưu tiên event `OrderReadyForShipment` nếu shipment chỉ bắt đầu sau bước đóng gói |
| Retry | Sử dụng registry/outbox phù hợp để theo dõi publication và bảo vệ duplicate ở consumer |
| Deploy có event tồn đọng | Đảm bảo code mới đọc được serialized payload cũ hoặc có migration an toàn |
| Bảo vệ boundary | Các module nhận chỉ phụ thuộc event/API công khai, không truy cập `orders.internal` |

## 17. Checklist trước khi chấp nhận một thay đổi event

- [ ] Đã xác nhận module sở hữu event và định nghĩa chính xác điều đã xảy ra.
- [ ] Việc mở rộng có giữ nguyên ý nghĩa nghiệp vụ? Nếu khác, đã xem xét tạo event mới.
- [ ] Consumer nội bộ nào phụ thuộc vào event; có vi phạm ranh giới package hay không?
- [ ] Tác vụ mới có thể chạy hậu commit hay cần kết quả đồng bộ trước khi quyết định nghiệp vụ?
- [ ] Thêm/xóa/đổi field đã được đánh giá trên Java API **và** serialized payload.
- [ ] Producer/consumer cũ và mới có các test schema compatibility tương ứng.
- [ ] Event có dữ liệu tối thiểu, không lộ entity hoặc thông tin nhạy cảm.
- [ ] Trường hợp retry, duplicate, event đến muộn và ordering đã có chính sách.
- [ ] Publication tồn đọng hoặc message lịch sử vẫn có thể đọc và xử lý đúng.
- [ ] Event externalized có target, routing, contract và version phù hợp.
- [ ] Monitoring đủ để xác định listener nào thất bại và publication nào còn chờ.
- [ ] Kế hoạch ngừng hỗ trợ field/event cũ có mốc và tiêu chí nghiệm thu rõ ràng.

**Quy tắc cốt lõi:** mở rộng event phải bảo vệ **sự thật nghiệp vụ, ranh giới sở hữu và khả năng diễn giải của consumer**. Spring Modulith giúp tổ chức việc phát và nhận application events, nhưng sự tương thích về ngữ nghĩa, schema, transaction và khôi phục vẫn cần được thiết kế và kiểm thử có chủ đích.
