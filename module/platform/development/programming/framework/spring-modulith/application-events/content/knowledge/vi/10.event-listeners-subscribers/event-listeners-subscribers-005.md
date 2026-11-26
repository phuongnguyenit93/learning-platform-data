# Một event nhiều listener

## 1. Tại sao một event có thể có nhiều listener?

Trong **modular monolith**, nhiều module cùng chạy trong một ứng dụng Spring Boot nhưng phải giữ được ranh giới nghiệp vụ độc lập. Ví dụ, khi đơn hàng đã được xác nhận, hệ thống thường cần làm nhiều việc:

- Module `notifications` gửi thông báo xác nhận.
- Module `reporting` cập nhật dữ liệu phục vụ báo cáo.
- Module `loyalty` ghi nhận điều kiện cộng điểm.
- Module `audit` lưu dấu nghiệp vụ để điều tra sự cố.

Nếu `orders` lần lượt gọi bốn service bên trên, mỗi lần bổ sung một tác vụ phụ sẽ phải sửa module sở hữu đơn hàng. `orders` cũng phải biết trực tiếp các module nhận, khiến đồ thị phụ thuộc dễ phình to và phát sinh vòng phụ thuộc.

Với **Spring Application Events**, `orders` chỉ phát một sự thật nghiệp vụ: `OrderConfirmed`. Mỗi module quan tâm tự đăng ký listener cho kiểu event đó. **Một lần publish có thể kích hoạt nhiều listener** mà publisher không cần biết tên, số lượng hoặc thứ tự của chúng.

~~~mermaid
flowchart LR
    C["Yêu cầu xác nhận đơn"] --> O["orders"]
    O -->|"publishEvent"| E(["OrderConfirmed"])
    E --> N["notifications<br/>Gửi email"]
    E --> R["reporting<br/>Cập nhật projection"]
    E --> L["loyalty<br/>Ghi nhận điểm"]
    E --> A["audit<br/>Lưu dấu"]
~~~

Đây là mô hình **fan-out**: một thông tin đầu vào được phân phối tới nhiều consumer có trách nhiệm riêng. Đối với module `SPRING_MODULITH_APPLICATION_EVENTS`, fan-out giúp giảm phụ thuộc giữa các module và làm rõ trách nhiệm của publisher, listener, transaction, Event Publication Registry, retry và giám sát giao sự kiện.

Sau bài này, bạn cần giải thích được vì sao một event có nhiều listener, phân biệt thứ tự và thời điểm thực thi theo từng annotation, triển khai listener cho các module độc lập, cũng như kiểm thử tình huống một listener thành công trong khi listener khác thất bại.

## 2. Publisher và subscriber liên kết bằng kiểu event

Spring cung cấp interface `ApplicationEventPublisher` để công bố sự kiện. Các listener đăng ký một kiểu event mà Spring có thể chuyển đến cho chúng; mỗi listener có thể là một bean khác nhau, đặt ở module khác nhau.

**Publisher không gọi trực tiếp từng listener.** Khi gọi:

~~~java
publisher.publishEvent(new OrderConfirmed(
        eventId, correlationId, orderId, occurredAt));
~~~

Spring chuyển event tới các listener phù hợp với **kiểu event** và điều kiện đăng ký của chúng. Không cần gọi `notificationListener.on(event)`, `reportListener.on(event)` hay `loyaltyListener.on(event)` ở module `orders`.

Tuy nhiên, hướng giao event khi chạy khác với **hướng phụ thuộc mã nguồn**:

~~~mermaid
flowchart TB
    N["notifications"] -->|"import OrderConfirmed"| O["orders (API event)"]
    R["reporting"] -->|"import OrderConfirmed"| O
    L["loyalty"] -->|"import OrderConfirmed"| O
~~~

Mỗi consumer **phụ thuộc vào hợp đồng event công khai** của `orders`; `orders` không cần import bất kỳ service hay listener nào của consumer. Sự phân tách này giúp bổ sung một consumer mới mà không chỉnh sửa hành vi xác nhận đơn, miễn hợp đồng event đã đủ thông tin.

Một event có nhiều listener **không** có nghĩa những listener đó đều phải sửa cùng bảng dữ liệu hoặc có cùng trách nhiệm. Mỗi consumer nên sở hữu dữ liệu, transaction và xử lý lỗi của chính nó. `notifications` có thể lưu trạng thái gửi email; `reporting` lưu projection; `loyalty` lưu sổ điểm. Không cho chúng cập nhật tùy tiện entity/repository nội bộ của `orders`.

## 3. Thiết kế một event cho nhiều người nhận

Khi nhiều consumer cùng đọc một event, **hợp đồng phải ổn định và không lệ thuộc vào một listener cụ thể**. Tên event diễn tả sự thật nghiệp vụ, không phải thao tác của consumer.

Đúng nghĩa:

~~~text
OrderConfirmed
    eventId
    correlationId
    orderId
    occurredAt
~~~

Không nên đặt tên event `SendOrderEmail` nếu nó còn được dùng cho reporting và loyalty: tên ấy mô tả command gửi email, không diễn tả kết quả xác nhận đơn.

Ví dụ record thuộc API công khai của module `orders`:

~~~java
// com/example/shop/orders/OrderConfirmed.java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID correlationId,
        UUID orderId,
        Instant occurredAt
) {
    public OrderConfirmed {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(correlationId, "correlationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
    }
}
~~~

Một số quy tắc quan trọng:

1. **Các listener nhận cùng một event logic:** `eventId` là định danh của `OrderConfirmed` và không thay đổi chỉ vì có thêm subscriber.
2. **`correlationId` dùng để liên kết quy trình:** những event tiếp theo do các listener phát ra có thể kế thừa ID này, nhưng có `eventId` riêng.
3. **Không truyền JPA entity:** listener chạy sau commit có thể không còn persistence context nguồn; entity cũng làm lộ implementation của module phát.
4. **Không nhồi dữ liệu riêng của từng consumer vào event:** khi cần thêm field, kiểm tra nó có thực sự thuộc hợp đồng công khai hay chỉ phục vụ một báo cáo riêng.
5. **Bảo vệ khả năng đọc event cũ:** nếu event được lưu bền để phục hồi, đổi cấu trúc record/enum phải xét đến cách serialize và deserialize publication chưa hoàn tất.

Một record chỉ chứa các giá trị bất biến giúp tránh việc consumer này thay đổi event trong bộ nhớ trước khi consumer khác nhận. Nếu payload chứa đối tượng mutable, cần thiết kế sao cho chúng không bị chia sẻ để chỉnh sửa tùy ý.

## 4. Cấu trúc ví dụ với ba module nhận event

Giả sử Spring Modulith khám phá các package con trực tiếp dưới `com.example.shop` thành application modules:

~~~text
com.example.shop/
├── ShopApplication.java
├── orders/
│   ├── OrderConfirmed.java            # API event công khai
│   └── internal/
│       ├── OrderEntity.java
│       ├── OrderRepository.java
│       └── OrderService.java          # Publisher
├── notifications/
│   └── internal/
│       ├── ConfirmationListener.java  # Listener 1
│       └── NotificationService.java
├── reporting/
│   └── internal/
│       ├── OrderReportListener.java   # Listener 2
│       └── OrderReportService.java
└── loyalty/
    └── internal/
        ├── LoyaltyListener.java       # Listener 3
        └── LoyaltyService.java
~~~

Module `orders` sở hữu thao tác xác nhận đơn. Publisher chỉ gọi Spring API:

~~~java
// com/example/shop/orders/internal/OrderService.java
package com.example.shop.orders.internal;

import com.example.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher events;
    private final Clock clock;

    public OrderService(OrderRepository orders,
                        ApplicationEventPublisher events,
                        Clock clock) {
        this.orders = orders;
        this.events = events;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId, UUID correlationId) {
        OrderEntity order = orders.findById(orderId).orElseThrow();

        if (order.isConfirmed()) {
            return; // Trạng thái không đổi: không phát event mới.
        }

        order.confirm(); // Kiểm tra quy tắc nghiệp vụ thuộc orders.

        events.publishEvent(new OrderConfirmed(
                UUID.randomUUID(),
                correlationId,
                order.getId(),
                Instant.now(clock)));
    }
}
~~~

`OrderEntity`, `OrderRepository` và bean `Clock` là các thành phần minh họa cần được hiện thực/cấu hình. Trong hệ thống thật, kiểm tra trạng thái và chuyển trạng thái phải an toàn khi có nhiều request đồng thời (ví dụ optimistic locking).

**Điểm đáng chú ý:** Trong toàn bộ `OrderService` không có import từ `notifications`, `reporting` hay `loyalty`. Một lần gọi `publishEvent(...)` có thể phục vụ mọi consumer đã được đăng ký.

## 5. Ba listener độc lập cho cùng OrderConfirmed

Với tác vụ phụ chỉ nên bắt đầu sau khi đơn đã commit, Spring Modulith cung cấp `@ApplicationModuleListener`. Annotation này kết hợp xử lý sau commit, bất đồng bộ (`@Async`) và transaction mới (`REQUIRES_NEW`); ứng dụng cần cấu hình hạ tầng async và executor phù hợp.

### 5.1. notifications gửi xác nhận

~~~java
// com/example/shop/notifications/internal/ConfirmationListener.java
package com.example.shop.notifications.internal;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ConfirmationListener {
    private final NotificationService notifications;

    ConfirmationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        notifications.sendConfirmationOnce(
                event.eventId(), event.orderId());
    }
}
~~~

`sendConfirmationOnce(...)` là hợp đồng nghiệp vụ minh họa. Implementation cần cơ chế chống gửi trùng phù hợp; tên phương thức **không tự tạo bảo đảm exactly-once**.

### 5.2. reporting ghi projection

~~~java
// com/example/shop/reporting/internal/OrderReportListener.java
package com.example.shop.reporting.internal;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderReportListener {
    private final OrderReportService reports;

    OrderReportListener(OrderReportService reports) {
        this.reports = reports;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        reports.recordConfirmationOnce(
                event.eventId(), event.orderId(), event.occurredAt());
    }
}
~~~

`OrderReportService` ghi bảng đọc hoặc tổng hợp do `reporting` sở hữu. Không cần sửa bảng `orders` để cập nhật báo cáo. Vì listener chạy sau commit và có thể chậm, projection có thể **nhất quán sau** so với dữ liệu đơn gốc.

### 5.3. loyalty ghi nhận điều kiện thưởng

~~~java
// com/example/shop/loyalty/internal/LoyaltyListener.java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class LoyaltyListener {
    private final LoyaltyService loyalty;

    LoyaltyListener(LoyaltyService loyalty) {
        this.loyalty = loyalty;
    }

    @ApplicationModuleListener
    void on(OrderConfirmed event) {
        loyalty.grantForConfirmedOrderOnce(
                event.orderId(), event.correlationId());
    }
}
~~~

`LoyaltyService` phải tự quản lý quy tắc ghi sổ, transaction, idempotency và khả năng nhiều event cùng cập nhật số dư. Nếu cùng một đơn chỉ được thưởng một lần, ràng buộc unique theo `(orderId, rewardType)` thường phù hợp hơn việc phụ thuộc hoàn toàn vào `eventId`.

**Cả ba listener nhận kiểu `OrderConfirmed`**, nhưng không chia sẻ repository, bảng trạng thái hay trách nhiệm nghiệp vụ. Các implementation của consumer cũng không cần được công bố cho `orders`.

## 6. Listener nào thực thi trước? Có chạy song song không?

Một event có nhiều listener **không mặc định tạo một chuỗi xử lý theo thứ tự nghiệp vụ**. Cần phân biệt các cơ chế:

| Cách khai báo | Thời điểm thường gặp | Quan hệ với publisher | Thứ tự/đồng thời |
| --- | --- | --- | --- |
| `@EventListener` | Ngay khi publish, theo cấu hình multicaster mặc định | Đồng bộ, có thể cùng transaction | Có thể dùng `@Order` cho listener đồng bộ, nhưng không biến thành orchestration nghiệp vụ |
| `@TransactionalEventListener` | Mặc định `AFTER_COMMIT` | Sau khi transaction nguồn commit | Không tự async; thứ tự callback không nên được dùng để tạo phụ thuộc dữ liệu |
| `@ApplicationModuleListener` | Sau commit | Bất đồng bộ, transaction mới | Các listener có thể chạy ở thread khác nhau, hoàn tất không theo thứ tự cố định |

Ví dụ `notifications` có thể hoàn tất trước `reporting`, hoặc `reporting` thành công trong khi `loyalty` đang retry. Hệ thống không được giả định:

~~~text
OrderConfirmed
  -> notifications xong
  -> reporting xong
  -> loyalty xong
~~~

Trong thực tế, fan-out thường biểu diễn ba phản ứng **độc lập**:

~~~mermaid
sequenceDiagram
    participant O as orders
    participant DB as Database
    participant N as notifications
    participant R as reporting
    participant L as loyalty
    O->>DB: Xác nhận đơn (transaction A)
    O->>DB: COMMIT A
    par Các consumer sau commit
        DB-->>N: OrderConfirmed
        N->>N: Gửi xác nhận
    and
        DB-->>R: OrderConfirmed
        R->>R: Ghi projection
    and
        DB-->>L: OrderConfirmed
        L->>L: Cộng điểm
    end
~~~

Sơ đồ mô tả các nhánh **có thể chạy độc lập** chứ không cam kết cả ba nhất định xử lý song song: độ đồng thời còn phụ thuộc executor, số thread, transaction manager và cấu hình thực tế. Đừng dựa vào `@Order` để ép thứ tự hoàn tất của các listener async.

Nếu `notifications` **bắt buộc cần** kết quả cộng điểm trước khi gửi email, quan hệ giữa hai bước đã là một phần quy trình nghiệp vụ. Khi đó có thể để `loyalty` phát `PointsGranted` sau khi ghi điểm thành công, rồi `notifications` lắng nghe `PointsGranted`. Không nên để `ConfirmationListener` tự giả định `LoyaltyListener` luôn chạy trước.

## 7. Transaction nguồn và ba kết quả của consumer

Khi `OrderService.confirm(...)` publish event trong transaction, có hai thời điểm khác nhau: **publish** và **commit**. Với `@ApplicationModuleListener`, listener nhận event sau khi transaction nguồn commit thành công.

Ví dụ kết quả:

| Trạng thái nguồn | notifications | reporting | loyalty | Ý nghĩa |
| --- | --- | --- | --- | --- |
| Transaction `orders` rollback | Không thực thi sau commit | Không thực thi sau commit | Không thực thi sau commit | Đơn chưa xác nhận thành công |
| Transaction `orders` commit | Thành công | Thành công | Thành công | Cả ba tác động đã hoàn tất |
| Transaction `orders` commit | Thành công | Thất bại | Thành công | Đơn đã xác nhận; chỉ reporting cần được phục hồi |
| Transaction `orders` commit | Thất bại | Thành công | Thất bại | Đơn đã xác nhận; hai consumer cần xử lý lỗi |

Một consumer thất bại **không thể rollback transaction của `orders` đã commit**. Với các listener bất đồng bộ trong transaction riêng, lỗi của `reporting` không nên buộc `notifications` phải thực hiện lại công việc đã hoàn tất.

Nếu dùng `@EventListener` **đồng bộ**, tình hình khác: exception từ listener có thể lan về `publishEvent(...)` và làm rollback transaction nguồn. Nếu consumer gửi email trước khi một listener khác ném lỗi, email đã gửi không thể tự động được database rollback. Vì vậy cần chọn annotation theo quy tắc nghiệp vụ và tính nhất quán mong muốn.

`@TransactionalEventListener(AFTER_COMMIT)` mặc định **không chạy** khi event được publish ngoài transaction đang hoạt động, trừ khi đặt `fallbackExecution = true`. `@ApplicationModuleListener` cũng dựa trên ngữ nghĩa transaction sau commit; publisher phải có transaction hợp lệ nếu muốn những listener này nhận event theo quy tắc đã thiết kế.

## 8. Event Publication Registry theo dõi từng listener

Spring Application Events cơ bản phân phối trong bộ nhớ. Nếu JVM dừng sau khi đơn đã commit nhưng trước khi listener async kịp thực thi, công việc phụ có nguy cơ bị bỏ lỡ.

**Event Publication Registry** của Spring Modulith giúp lưu dấu việc giao event tới các transactional listener được theo dõi. Với backend lưu trữ bền vững phù hợp, **một event có nhiều listener có thể tương ứng với nhiều bản ghi publication**: mỗi bản ghi biểu diễn việc giao **event đó cho một listener đích**.

Ví dụ mô hình khái niệm khi `orders` phát `OrderConfirmed(E-100)`:

| Event logic | Listener đích | Trạng thái publication |
| --- | --- | --- |
| `E-100` | `ConfirmationListener` | Hoàn tất |
| `E-100` | `OrderReportListener` | Chưa hoàn tất do lỗi |
| `E-100` | `LoyaltyListener` | Hoàn tất |

`E-100` là **cùng một event**, không phải ba event mới. Registry ghi nhận tiến độ giao nhận theo consumer để hệ thống biết chính xác **bản ghi nào cần được xem xét hoặc phát lại**.

~~~mermaid
flowchart TB
    E["OrderConfirmed / eventId=E-100"]
    E --> N["Publication: notifications"]
    E --> R["Publication: reporting"]
    E --> L["Publication: loyalty"]
    N --> NS["COMPLETED"]
    R --> RF["INCOMPLETE / FAILED"]
    L --> LS["COMPLETED"]
    RF --> REC["Khôi phục reporting"]
~~~

Để sử dụng registry bền vững, ứng dụng phải cấu hình implementation lưu trữ phù hợp, chẳng hạn JDBC/JPA, database/schema và transaction manager. **Chỉ có `@ApplicationModuleListener` không tự bảo đảm đã có kho publication bền vững**. Những `@EventListener` đồng bộ thông thường cũng không nên được coi là consumer được registry bảo đảm theo cùng cơ chế transactional publication.

Thông thường, publication được đăng ký trong transaction nguồn khi event được publish, rồi được đánh dấu hoàn tất sau khi listener xử lý thành công. Chi tiết trạng thái, cách lưu và cách resubmit phụ thuộc phiên bản Spring Modulith và implementation đã cấu hình.

**Không giả định tất cả publication lỗi sẽ tự retry vô hạn.** Cần cấu hình/kích hoạt cơ chế khôi phục theo phiên bản đang dùng, hoặc vận hành tác vụ resubmit phù hợp. Registry giúp nhận diện việc chưa hoàn tất; nó không tự sửa logic sai trong listener.

## 9. Khi một listener lỗi, hai listener còn lại ra sao?

Giả sử `OrderConfirmed(E-100)` đã được commit. `notifications` đã gửi email, `loyalty` đã cộng điểm, nhưng `reporting` thất bại do database tạm thời không kết nối được.

Với fan-out sau commit:

1. Đơn hàng vẫn ở trạng thái đã xác nhận.
2. Email và điểm thưởng đã thành công **không được coi là chưa xảy ra** chỉ vì reporting lỗi.
3. Publication dành cho `OrderReportListener` cần được theo dõi; khi hệ thống phục hồi, đường resubmit có thể xử lý lại **đúng event E-100**.
4. Những consumer đã hoàn tất không cần bị chạy lại chỉ vì một consumer khác thất bại, nếu cơ chế phục hồi hỗ trợ nhắm đúng publication.
5. Nếu một consumer bị gọi lại vì crash trước thời điểm ghi completion, consumer vẫn phải **idempotent**.

Quan trọng: Event Publication Registry **không tạo cam kết exactly-once cho side effect**. Ví dụ email có thể đã gửi, rồi JVM dừng trước khi registry kịp đánh dấu publication của `notifications` hoàn tất. Khi phục hồi, listener có thể nhận lại `E-100` dù việc gửi thực tế đã diễn ra.

Đối với mỗi consumer, nên thiết kế khóa idempotency phù hợp:

| Consumer | Tác động | Khóa chống trùng thường gặp |
| --- | --- | --- |
| `notifications` | Một thông báo xác nhận cho mỗi đơn | `(orderId, notificationType)` |
| `reporting` | Một lần ghi nhận từng event vào projection | `(eventId, projectionName)` |
| `loyalty` | Một khoản thưởng cho mỗi đơn theo chính sách | `(orderId, rewardType)` |

Các khóa này chỉ là mẫu; nếu nghiệp vụ cho phép gửi nhiều lần xác nhận hoặc cộng nhiều loại điểm cho cùng đơn, khóa phải được thiết kế theo **ý nghĩa từng tác động**, không áp dụng máy móc.

Không dùng mỗi `correlationId` để chống trùng: nhiều event hợp lệ trong cùng quy trình có thể chia sẻ correlation ID. `eventId` xác định event logic; còn business key quyết định tác động nào thực sự chỉ được thực hiện một lần.

## 10. Ví dụ ghi idempotency với database

Giả sử `reporting` phải ghi nhận mỗi event xác nhận đúng một lần. Nó có thể sở hữu một bảng projection/log riêng:

~~~sql
-- Ví dụ PostgreSQL, thuộc schema do reporting sở hữu.
CREATE TABLE reporting.confirmed_order_events (
    event_id     UUID PRIMARY KEY,
    order_id     UUID NOT NULL,
    occurred_at  TIMESTAMPTZ NOT NULL
);

INSERT INTO reporting.confirmed_order_events
    (event_id, order_id, occurred_at)
VALUES
    (:eventId, :orderId, :occurredAt)
ON CONFLICT (event_id) DO NOTHING;
~~~

Nếu câu lệnh `INSERT` thực sự tạo một bản ghi mới thì mới cập nhật số liệu tổng hợp. **Thao tác ghi dấu event và tăng aggregate phải cùng transaction**, tránh trường hợp ghi đã xử lý rồi nhưng aggregate chưa được cập nhật (hoặc ngược lại).

Nếu projection chỉ lưu một bản ghi cho mỗi đơn đã xác nhận, unique key trên `orderId` cũng có thể hợp lý hơn. Phải quyết định dựa trên khả năng một đơn có nhiều lần xác nhận hợp lệ hay không.

Khi nhiều listener cùng nhận event, **mỗi listener phải có idempotency riêng cho tác động của mình**. Không nên tạo một cờ `event_processed` dùng chung toàn ứng dụng rồi cho consumer đầu tiên đánh dấu; nếu làm vậy, consumer thứ hai có thể nhầm rằng chính nó đã hoàn thành và bỏ qua xử lý.

## 11. Một event không bảo đảm thứ tự giữa các event khác

Hai request có thể lần lượt tạo `OrderConfirmed(E1)` và `OrderCancelled(E2)`. Các listener sau commit có thể được lên lịch khác nhau. Một projection xử lý E2 trước E1 có nguy cơ quay về trạng thái đã xác nhận sau khi đơn thực tế bị hủy.

Vì vậy, với listener cần duy trì **trạng thái mới nhất**, ngoài idempotency cần có chiến lược xử lý thứ tự:

- Mang `aggregateVersion` hoặc một sequence tăng theo từng aggregate trong event, được cấp ở thời điểm thay đổi dữ liệu nguồn.
- Khi cập nhật projection, chỉ nhận version mới hơn version đang lưu, dùng phép cập nhật nguyên tử hoặc optimistic locking.
- Nếu cần chính xác từng chuyển trạng thái theo thứ tự, tổ chức xử lý tuần tự theo khóa aggregate hoặc dùng cơ chế lưu/replay có kiểm soát.
- Không dựa vào timestamp hoặc thứ tự listener hoàn tất để suy luận thứ tự nghiệp vụ chắc chắn.

~~~text
Event E1: orderId=O-42, aggregateVersion=2, status=CONFIRMED
Event E2: orderId=O-42, aggregateVersion=3, status=CANCELLED

Projection đang ở version 3:
    nhận lại E1 (version 2) -> bỏ qua
    nhận E2 (version 3)     -> không đổi
~~~

Một event nhiều listener và nhiều event cho cùng một aggregate là **hai vấn đề khác nhau**: vấn đề thứ nhất là fan-out độc lập; vấn đề thứ hai là thứ tự xử lý theo thời gian và version.

## 12. Khi nào không nên dùng fan-out độc lập?

Một event nhiều listener phù hợp với các tác vụ phụ có thể xử lý độc lập. Nhưng có những quy trình đòi hỏi quyết định chung:

| Nhu cầu | Cách tổ chức gợi ý | Vì sao |
| --- | --- | --- |
| Gửi email và cập nhật báo cáo sau khi đơn được xác nhận | Hai listener nhận `OrderConfirmed` | Hai tác động độc lập, có thể chấp nhận xử lý muộn |
| Gửi email sau khi điểm thưởng đã được cộng thành công | `loyalty` phát `PointsGranted`; `notifications` nghe event đó | Phản ánh đúng điều kiện tiên quyết |
| Xác nhận đơn chỉ khi đủ hàng và thanh toán được chấp thuận | API đồng bộ hoặc quy trình trạng thái có điều phối rõ | Publisher cần kết quả để quyết định nghiệp vụ |
| Gửi thông báo chỉ sau khi tất cả ba tác vụ phụ hoàn thành | Workflow coordinator theo dõi các kết quả riêng | Fan-out tự nó không có barrier “tất cả xong” |

Nếu cần biết **mọi listener đã hoàn thành**, không lấy kết luận đó từ việc `publishEvent(...)` trả về. Với xử lý async, publisher thường hoàn tất trước consumer. Registry có thể cung cấp thông tin publication, nhưng một quy trình nghiệp vụ cần barrier, timeout hoặc bù trừ phải được thiết kế rõ ràng; registry không tự biến fan-out thành một workflow engine.

## 13. Kiểm thử một event nhiều listener

Cần kiểm tra riêng **publisher**, **mỗi listener** và **tính độc lập khi delivery lỗi**.

### 13.1. Test đơn vị của publisher

Trong unit test, dùng mock `ApplicationEventPublisher` và capture payload:

~~~java
package com.example.shop.orders.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import com.example.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

class OrderServiceTest {

    @Test
    void publishesOneEventForConfirmedOrder() {
        OrderRepository orders = mock(OrderRepository.class);
        OrderEntity order = mock(OrderEntity.class);
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        Clock clock = Clock.fixed(
                Instant.parse("2026-02-03T04:05:06Z"), ZoneOffset.UTC);

        UUID orderId = UUID.randomUUID();
        UUID correlationId = UUID.randomUUID();
        when(orders.findById(orderId)).thenReturn(Optional.of(order));
        when(order.isConfirmed()).thenReturn(false);
        when(order.getId()).thenReturn(orderId);

        new OrderService(orders, publisher, clock)
                .confirm(orderId, correlationId);

        ArgumentCaptor<OrderConfirmed> captor =
                ArgumentCaptor.forClass(OrderConfirmed.class);
        verify(publisher, times(1)).publishEvent(captor.capture());
        assertThat(captor.getValue().orderId()).isEqualTo(orderId);
        assertThat(captor.getValue().correlationId())
                .isEqualTo(correlationId);
    }
}
~~~

Unit test này chỉ khẳng định publisher **phát một event** với dữ liệu đúng. Nó không chứng minh có ba listener nhận được, vì mock publisher không dispatch.

### 13.2. Test tích hợp nhiều listener

Với Spring context và database kiểm thử phù hợp, xây dựng tình huống:

1. **Commit thành công:** gọi `orders.confirm(...)` qua Spring bean, commit transaction nguồn, chờ ba consumer với timeout; xác minh thông báo, báo cáo và điểm thưởng.
2. **Rollback nguồn:** cho `orders` ném lỗi trước commit. Cả ba listener `AFTER_COMMIT` không được thực thi như thể đơn đã được xác nhận.
3. **Một consumer lỗi:** cho reporting ném exception, để notification và loyalty hoàn tất. Kiểm tra đúng publication của reporting vẫn chưa hoàn tất theo registry cấu hình.
4. **Khôi phục reporting:** sửa lỗi, kích hoạt cơ chế recovery/resubmit của phiên bản đang dùng; chỉ kiểm tra reporting xử lý lại `OrderConfirmed` gốc, không yêu cầu publisher tạo event mới.
5. **Crash sau tác động:** mô phỏng nhận lại cùng event tại notifications; xác minh idempotency ngăn thông báo trùng.
6. **Hai event ngược thứ tự:** cho projection nhận `OrderCancelled` trước `OrderConfirmed`, kiểm tra phiên bản aggregate ngăn trạng thái bị ghi lùi nếu nghiệp vụ hỗ trợ version.

Chú ý test có `@Transactional` tự rollback ở cuối thường **không kích hoạt `AFTER_COMMIT`**. Cần bố trí test thực sự commit transaction nguồn, và vì `@ApplicationModuleListener` bất đồng bộ, hãy chờ kết quả theo điều kiện với timeout thay vì assert tức thời.

### 13.3. Kiểm tra ranh giới module

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void modulesRespectTheirPublicApis() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

`verify()` giúp phát hiện phụ thuộc module không hợp lệ, vòng phụ thuộc và việc tham chiếu API nội bộ trong phạm vi Spring Modulith phân tích. Nó không thay thế test publication, transaction, idempotency hoặc SQL truy cập dữ liệu chéo.

## 14. Quan sát fan-out trong vận hành

Khi một event có ba listener, câu hỏi “**event đã thành công chưa?**” không thể trả lời chỉ bằng một boolean của publisher. Nên quan sát ít nhất ba nhóm thông tin:

| Thông tin | Mục đích |
| --- | --- |
| `eventId` và `correlationId` | Tìm event gốc, log publisher và các lần retry |
| Tên listener/consumer cùng trạng thái publication | Biết subscriber nào đã hoàn tất, subscriber nào còn lỗi |
| Thời gian xử lý, số lần retry, lỗi và độ tuổi publication | Phát hiện consumer chậm, lỗi kéo dài hoặc executor nghẽn |

Ví dụ log consumer:

~~~java
log.info("Processing OrderConfirmed eventId={} correlationId={} listener={}",
        event.eventId(), event.correlationId(), "reporting");
~~~

Với listener async, `MDC` hay `ThreadLocal` từ HTTP thread gốc không tự nhiên được đảm bảo tồn tại trong thread mới. Muốn liên kết log sau commit và sau restart, cần đặt ID trong event và thiết lập lại logging context trong listener hoặc dùng propagation/instrumentation phù hợp.

Không dùng UUID `eventId` hay `correlationId` làm metric labels cho từng time series, vì cardinality sẽ tăng rất lớn. Dùng tên event, listener, trạng thái và loại lỗi làm metric tags; tra cứu ID chi tiết trong log hoặc trace.

Một cách trình bày trạng thái vận hành có ích:

~~~text
OrderConfirmed eventId=E-100, orderId=O-42
  notifications: COMPLETED
  reporting:     INCOMPLETE (database timeout)
  loyalty:       COMPLETED

Action: kiểm tra lỗi reporting và resubmit publication của reporting
~~~

Đây là bảng trạng thái **minh họa**; không phải lược đồ bảng hoặc tên enum chính thức mà mọi backend Event Publication Registry đều sử dụng.

## 15. Bài thực hành: thêm consumer mà không sửa orders

Tạo hệ thống Spring Modulith gồm `orders`, `notifications`, `reporting` và `loyalty`. Một lần xác nhận đơn phát đúng một `OrderConfirmed`.

Yêu cầu:

1. Viết record `OrderConfirmed` trong API của `orders`, có `eventId`, `correlationId`, `orderId` và `occurredAt`.
2. Viết `OrderService.confirm(...)` với `@Transactional`; kiểm tra chuyển trạng thái hợp lệ trước khi publish.
3. Tạo ba bean listener `@ApplicationModuleListener` trong ba module nhận, tất cả dùng cùng event nhưng ghi các dữ liệu riêng.
4. Chọn idempotency key cho mỗi consumer; giải thích vì sao không dùng một cờ `processed` chung cho cả ba.
5. Cấu hình Event Publication Registry bền vững và quan sát ba publication của một event khi dùng các listener được registry theo dõi.
6. Chủ động làm `reporting` thất bại, kiểm tra hai consumer còn lại vẫn thành công và đơn vẫn đã xác nhận.
7. Phục hồi reporting qua đường retry/resubmit đã cấu hình, giữ nguyên `eventId` gốc và đảm bảo projection không ghi trùng.
8. Chạy kiểm tra cấu trúc `ApplicationModules.verify()`, xác nhận `orders` không import implementation của consumer.

**Câu hỏi tự đánh giá:**

- Một `OrderConfirmed` được ba listener nhận có phải là ba event khác nhau không?
- Nếu reporting lỗi sau commit, có nên gọi lại `OrderService.confirm(...)` để phát event mới không?
- Vì sao `@Order` không nên được dùng làm cơ chế bảo đảm thứ tự hoàn tất của các listener async?
- Nếu notifications đã gửi email rồi JVM dừng trước khi ghi completion, điều gì ngăn việc gửi lại email khi resubmit?
- Nếu cần notification chỉ chạy sau khi loyalty cộng điểm thành công, nên thay đổi loại event hoặc thiết kế quy trình thế nào?

## 16. Ghi nhớ

**Một event nhiều listener** là cách fan-out một sự thật nghiệp vụ tới nhiều module độc lập. Publisher chỉ biết `ApplicationEventPublisher` và event thuộc API công khai; consumer biết kiểu event nhưng tự sở hữu dữ liệu và hành vi. Số consumer có thể tăng mà không phải thêm các lời gọi trực tiếp từ module phát.

Trong Spring Modulith, `@ApplicationModuleListener` phù hợp với tác vụ phụ sau commit vì chạy bất đồng bộ trong transaction mới. Tuy nhiên, nhiều listener **không tạo thứ tự hoàn tất cố định hoặc bảo đảm tất cả cùng thành công**. Khi cần độ tin cậy, phải cấu hình Event Publication Registry bền vững, quan sát publication theo từng consumer, thiết kế retry có kiểm soát và idempotency riêng của mỗi listener. Khi cần phụ thuộc kết quả giữa các bước, dùng event nối tiếp hoặc một quy trình điều phối có trạng thái rõ ràng.

**Tài liệu tham khảo chính thức:**

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
