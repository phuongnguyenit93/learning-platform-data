# Người tiêu thụ hợp đồng sự kiện trong Spring Modulith

Trong kiến trúc modular monolith, một module có thể phát sự kiện để thông báo rằng một sự thật nghiệp vụ vừa xảy ra. Module khác nhận sự kiện và phản ứng theo trách nhiệm của mình. **Người tiêu thụ hợp đồng** (*contract consumer*) là thành phần dựa vào một hợp đồng đã được công bố để hiểu sự kiện, ra quyết định và thực hiện công việc mà nó sở hữu.

Ví dụ, module `ordering` phát `OrderPlaced` khi đơn hàng được ghi nhận; `notification` dùng hợp đồng này để gửi xác nhận, còn `analytics` dùng nó để cập nhật báo cáo. Cả hai là consumer của **cùng một hợp đồng** nhưng có mục đích, dữ liệu cần dùng, thời hạn xử lý và chính sách lỗi khác nhau.

Bài học thuộc chương **Hợp đồng sự kiện** của `SPRING_MODULITH_APPLICATION_EVENTS`. Trọng tâm là cách tổ chức giao tiếp giữa các module Spring Modulith bằng application events, giảm phụ thuộc và bảo vệ ranh giới nghiệp vụ, đồng thời chuẩn bị cho publisher/listener, xử lý sau commit, event publication registry, retry, kiểm thử và quan sát việc giao sự kiện đáng tin cậy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Xác định **publisher**, **event contract** và **consumer** trong một kiến trúc Spring Modulith.
- Giải thích consumer được phép phụ thuộc vào phần nào của module phát và vì sao hợp đồng sự kiện phải được công bố rõ ràng.
- Phân biệt nhu cầu dữ liệu, kỳ vọng nghiệp vụ và trách nhiệm xử lý lỗi của từng consumer.
- Thiết kế listener dùng `@ApplicationModuleListener` và hiểu ranh giới transaction sau commit.
- Đánh giá tác động của việc thêm, sửa hoặc xóa trường trong event contract tới nhiều consumer.
- Xây dựng chính sách **idempotency**, retry, trạng thái xử lý và quan sát theo từng consumer.
- Lập kế hoạch kiểm thử hợp đồng ở cả phía phát lẫn phía nhận mà không đánh đồng việc publish với xử lý thành công.

## 2. Ai là người tiêu thụ hợp đồng?

Xét luồng đặt hàng:

~~~mermaid
flowchart LR
    O["ordering<br/>Publisher"] --> E["OrderPlaced<br/>Hợp đồng sự kiện"]
    E --> N["notification<br/>Consumer"]
    E --> A["analytics<br/>Consumer"]
    E --> L["loyalty<br/>Consumer"]
~~~

Trong sơ đồ, các mũi tên mô tả **luồng thông tin của sự kiện**. Ở cấp mã nguồn, các consumer phụ thuộc vào kiểu `OrderPlaced` do `ordering` công bố; publisher không cần import các lớp listener. Sơ đồ không ngụ ý các consumer xử lý đồng thời hoặc đã hoàn tất khi `publishEvent(...)` trả về.

Ba vai trò cần phân biệt:

| Vai trò | Sở hữu điều gì? | Không nên phải biết |
| --- | --- | --- |
| **Publisher** — `ordering` | Điều kiện phát `OrderPlaced`, ý nghĩa nghiệp vụ và dữ liệu của event | Có bao nhiêu listener; nội bộ email hoặc báo cáo |
| **Contract** — `OrderPlaced` | Cấu trúc và ý nghĩa dữ liệu được công bố, quy tắc tương thích | Cách từng consumer cài đặt side effect |
| **Consumer** — `notification`, `analytics`, `loyalty` | Quyết định có phản ứng, xử lý như thế nào, ghi nhận kết quả và lỗi | Entity/repository nội bộ của publisher |

Consumer không nhất thiết là một hệ thống bên ngoài. Trong Spring Modulith, nó thường là **một application module trong cùng JVM** có phương thức listener nhận một Java object. Khi sự kiện được externalize sang Kafka, RabbitMQ hoặc hệ thống khác, một ứng dụng bên ngoài cũng có thể trở thành consumer, nhưng hợp đồng truyền tải và việc triển khai sẽ khác.

### Ví dụ về nhu cầu khác nhau của từng consumer

| Consumer | Cần biết | Phản ứng | Mức chịu trễ / lỗi |
| --- | --- | --- | --- |
| `notification` | ID đơn, người nhận hoặc cách tra thông tin liên hệ qua API hợp lệ | Gửi xác nhận | Có thể retry; phải cân nhắc gửi trùng |
| `analytics` | ID đơn, thời gian và có thể là snapshot giá trị đơn | Cập nhật thống kê | Thường chấp nhận trễ ngắn; phải tránh cộng số liệu hai lần |
| `loyalty` | ID đơn, khách hàng, điều kiện áp điểm | Ghi nhận điểm thưởng | Cần kiểm soát idempotency và quy tắc nghiệp vụ |
| `audit` | ID event, thời điểm, loại sự kiện | Ghi log nghiệp vụ có kiểm soát | Cần truy vết rõ ràng và chính sách lưu giữ |

**Cùng một event không bắt buộc chứa mọi dữ liệu mà mọi consumer có thể muốn.** Publisher và consumer cần thống nhất trường nào thuộc ngữ nghĩa chung; phần dữ liệu nhạy cảm hoặc phụ thuộc triển khai không nên đưa vào chỉ để một consumer tiện sử dụng.

## 3. Consumer phụ thuộc vào hợp đồng, không phụ thuộc vào implementation

Giả sử ứng dụng Spring Boot có root package `com.example.shop` và các application module trực tiếp là `ordering`, `notification`, `analytics`:

~~~text
com.example.shop
├── ShopApplication.java
├── ordering/
│   ├── OrderFacade.java                    # API mặc định
│   ├── events/
│   │   ├── package-info.java               # Named interface "events"
│   │   └── OrderPlaced.java                # Hợp đồng công bố
│   └── internal/
│       ├── OrderingService.java
│       ├── OrderRepository.java
│       └── OrderEntity.java
├── notification/
│   ├── package-info.java                   # Giới hạn phụ thuộc
│   └── internal/
│       ├── OrderNotificationListener.java
│       └── ReceiptDelivery.java
└── analytics/
    └── internal/
        ├── OrderAnalyticsListener.java
        └── OrderMetrics.java
~~~

Với cách phát hiện module mặc định, **root package** của một application module là API công khai mặc định; các subpackage khác được xem là nội bộ trừ khi công bố có chủ đích. Vì `OrderPlaced` nằm trong `ordering.events`, cần công bố package này qua **named interface**:

~~~java
// com/example/shop/ordering/events/package-info.java
@org.springframework.modulith.NamedInterface("events")
package com.example.shop.ordering.events;
~~~

Đối với module `notification` chỉ cần hợp đồng sự kiện, có thể giới hạn phụ thuộc:

~~~java
// com/example/shop/notification/package-info.java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "ordering::events"
)
package com.example.shop.notification;
~~~

`ordering::events` nghĩa là consumer được phép phụ thuộc vào **named interface `events` của module `ordering`**. Nó không cấp quyền dùng tất cả kiểu ở `ordering.internal` hoặc tùy tiện gọi `OrderFacade`. Những ràng buộc kiến trúc được kiểm tra bằng Spring Modulith; Java compiler không tự hiểu toàn bộ chính sách `allowedDependencies`.

Ví dụ import nên tránh:

~~~java
import com.example.shop.ordering.internal.OrderRepository;
import com.example.shop.ordering.internal.OrderEntity;
~~~

Ngay cả nếu các class nội bộ này được khai báo `public` và code Java biên dịch được, consumer vẫn vượt qua ranh giới module. Sửa đúng là thiết kế **event payload phù hợp** hoặc **một API truy vấn được công bố rõ**, thay vì mở repository chỉ để listener lấy dữ liệu.

### Hướng phụ thuộc và hướng chạy sự kiện

~~~mermaid
flowchart TD
    subgraph PUB["ordering"]
       S["OrderingService"]
       C["OrderPlaced : public event contract"]
       S -->|"publish"| C
    end
    subgraph CON["notification"]
       R["OrderNotificationListener"]
       D["ReceiptDelivery"]
       R --> D
    end
    R -->|"Java dependency: import contract"| C
~~~

Trong sơ đồ này, `OrderingService` không gọi `ReceiptDelivery`. Module `notification` tham chiếu vào event contract, còn Spring event infrastructure chuyển event tới listener ở runtime. Đây là **giảm phụ thuộc hướng publisher → consumer**, không phải loại bỏ mọi phụ thuộc.

## 4. Consumer cần hiểu cả cấu trúc lẫn ngữ nghĩa hợp đồng

Hợp đồng tốt không chỉ cho biết “record có những trường gì”, mà còn định nghĩa **điều gì đã xảy ra**, **lúc nào sự thật đó có hiệu lực**, **consumer có được suy ra điều gì** và **được phép làm gì với dữ liệu**.

Một event cơ bản:

~~~java
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

| Trường | Cam kết của publisher | Cách consumer nên sử dụng |
| --- | --- | --- |
| `eventId` | Nhận diện **một lần xảy ra sự kiện** | Truy vết và khử trùng lặp khi nhận lại cùng event |
| `orderId` | Nhận diện đơn hàng liên quan | Liên kết nghiệp vụ; không nhầm với event ID |
| `occurredAt` | Thời điểm sự kiện được ghi nhận theo domain | Phân tích thứ tự/thời gian; không coi là thời điểm listener xử lý |

Ví dụ, `OrderPlaced` **không mặc nhiên có nghĩa** “đơn hàng đã thanh toán” hoặc “đã giao hàng”. Nếu `notification` cần gửi email “Thanh toán thành công”, nó nên nghe một sự kiện phù hợp như `PaymentCaptured` hoặc kiểm tra điều kiện nghiệp vụ tương ứng, thay vì tự diễn giải `OrderPlaced`.

### Phân biệt sự thật nghiệp vụ và thời điểm xử lý

Consumer cần phân biệt:

- **Thời điểm xảy ra event** (`occurredAt`): khi publisher ghi nhận sự thật theo quy tắc domain.
- **Thời điểm transaction commit**: dữ liệu của publisher được lưu bền sau commit thành công.
- **Thời điểm listener nhận event**: phụ thuộc cơ chế sync/async, hàng đợi và tải.
- **Thời điểm listener hoàn tất**: sau khi side effect/transaction của consumer hoàn thành theo định nghĩa.

Không nên lấy `occurredAt` để thay cho thời điểm hoàn tất gửi email hoặc thời điểm cập nhật báo cáo. Việc phân biệt các mốc này giúp thiết kế metric chính xác và xử lý sự kiện trễ.

## 5. Consumer có quyền yêu cầu gì ở hợp đồng?

Publisher sở hữu sự thật nghiệp vụ, nhưng hợp đồng được dùng bởi nhiều consumer. Do đó, khi thiết kế contract, **nhu cầu thực tế của consumer phải được xem xét** mà không chuyển ownership nghiệp vụ sang consumer.

Trước khi chốt một event, hãy hỏi:

1. **Consumer quyết định gì sau khi nhận?** Ví dụ gửi email xác nhận, ghi điểm hoặc thống kê.
2. **Cần dữ liệu nào để ra quyết định đúng?** ID đơn, loại sự kiện, timestamp, customer ID hay snapshot amount?
3. **Dữ liệu nào nên truy vấn qua một API công khai?** Việc lookup sau commit có chấp nhận được không?
4. **Cần trạng thái tại thời điểm event hay trạng thái mới nhất?** Snapshot giúp giữ ý nghĩa tại thời điểm xảy ra; query cho phép lấy giá trị hiện tại.
5. **Nếu contract thay đổi, consumer nào bị ảnh hưởng?** Có cần lộ trình migration hoặc schema version?
6. **Độ trễ và xử lý lặp có chấp nhận được không?** Chính sách được ghi rõ ở tiêu chuẩn vận hành của consumer.

Ví dụ, `analytics` muốn báo cáo giá trị đơn ngay lúc đặt:

- Nếu query lại đơn hàng nhiều giờ sau, giá trị có thể đã đổi do điều chỉnh/hoàn tiền.
- Có thể thêm snapshot như `totalAmount` và `currency` vào một event nghiệp vụ đúng ngữ nghĩa, nếu publisher sở hữu và bảo đảm được các giá trị đó.
- Không nên cho consumer truy cập `OrderEntity` hay toàn bộ JPA object graph.

Không có quy tắc tuyệt đối rằng event chỉ được chứa ID, cũng không có lý do mặc định để copy nguyên entity. **Chọn payload dựa trên ý nghĩa, nhu cầu đã được xác nhận, mức độ ổn định và yêu cầu bảo mật.**

### Khi nào một nhu cầu không nên làm phình contract chung?

Nếu chỉ một consumer yêu cầu trường kỹ thuật quá riêng, như tên bảng persistence hoặc cấu hình SMTP, trường đó không thuộc ngôn ngữ nghiệp vụ chung. Lựa chọn phù hợp có thể là API chuyên dụng, một event khác với ngữ nghĩa riêng hoặc logic nằm trong chính consumer.

Thêm trường vào event công khai có chi phí lâu dài: những consumer khác có thể bắt đầu dựa vào nó. **Hợp đồng càng rộng thì càng khó thay đổi an toàn**.

## 6. Một event — nhiều consumer, nhiều chính sách xử lý

Đặt hàng thành công có thể kích hoạt các phản ứng khác nhau:

~~~text
OrderPlaced(E-100, O-200)
    |
    +-- notification: gửi email xác nhận
    |
    +-- analytics: ghi thêm một đơn vào báo cáo
    |
    +-- loyalty: tạo yêu cầu xét thưởng điểm
~~~

Mỗi listener cần sở hữu **cách xử lý lỗi và kết quả nghiệp vụ** của chính nó. Chẳng hạn:

| Điều xảy ra | `notification` | `analytics` | `loyalty` |
| --- | --- | --- | --- |
| Event đến sau vài giây | Thường chấp nhận được | Thường chấp nhận được | Phụ thuộc chính sách điểm |
| Sự kiện được nhận lại | Tránh gửi email trùng nếu có thể | Không cộng trùng | Không tạo hai khoản thưởng |
| Dịch vụ phụ thuộc tạm thời lỗi | Retry hoặc hỗ trợ xử lý thủ công | Retry xử lý thống kê | Retry/bù trừ theo trạng thái điểm |
| Không đủ dữ liệu cần thiết | Dùng API hợp lệ hoặc báo lỗi có thể xử lý | Xác minh hợp đồng snapshot | Từ chối/ghi trạng thái thiếu điều kiện |

Không nên phát nhiều event chỉ vì mỗi consumer muốn một callback mang tên riêng khi tất cả đều phản ứng với cùng một sự thật. Ngược lại, nếu hai event đại diện hai mốc nghiệp vụ thật sự khác nhau (`OrderPlaced` và `OrderPaid`), không nên nhập chúng làm một để giảm số class.

## 7. Viết consumer trong Spring Modulith

Trong Spring Modulith, listener của một module tiêu thụ có thể nhận event qua `@ApplicationModuleListener`. Ví dụ `notification` không cần biết repository của `ordering`:

~~~java
package com.example.shop.notification.internal;

import com.example.shop.ordering.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderNotificationListener {

    private final ReceiptDelivery delivery;

    OrderNotificationListener(ReceiptDelivery delivery) {
        this.delivery = delivery;
    }

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        delivery.sendConfirmationOnce(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

`ReceiptDelivery` là abstraction do **module notification** sở hữu. Phương thức `sendConfirmationOnce(eventId, orderId)` biểu thị **yêu cầu idempotency ở tầng nghiệp vụ**; đây là một API minh họa tự thiết kế, **không phải method sẵn có của Spring Modulith**. Implementation thực tế phải đảm bảo chống gửi trùng theo điều kiện của dịch vụ email và database.

### `@ApplicationModuleListener` mang lại điều gì?

Annotation này tổng hợp các cơ chế listener giao dịch của Spring Modulith: phản ứng ở **pha sau commit**, hỗ trợ xử lý **bất đồng bộ** và thực thi với **transaction mới** cho logic listener. Hành vi thực tế phụ thuộc vào hạ tầng event, transaction và cấu hình executor/async của ứng dụng. Không nên suy ra rằng annotation tự cung cấp persistence, retry hoặc xử lý “exactly once”.

Giả sử publisher gọi:

~~~java
events.publishEvent(new OrderPlaced(
        UUID.randomUUID(),
        orderId,
        clock.instant()
));
~~~

Đoạn code này chỉ cho biết event được đưa vào hệ thống event của Spring. Khi gọi trong một transaction đang hoạt động, transaction **có thể chưa commit** tại thời điểm publish. Với listener sau commit, consumer chỉ nên phản ứng sau khi publisher commit thành công; nếu publisher rollback, listener `AFTER_COMMIT` không chạy cho event đó.

### Khi nào dùng một listener khác?

| Cơ chế | Thời điểm / đặc tính điển hình | Phù hợp khi |
| --- | --- | --- |
| `@EventListener` thông thường | Theo mặc định, xử lý đồng bộ ngay lúc publish | Cần phản ứng tức thì trong luồng hiện tại và đã hiểu rõ hậu quả transaction |
| `@TransactionalEventListener(AFTER_COMMIT)` | Phản ứng sau commit; theo mặc định không chạy nếu không có transaction | Consumer chỉ được phản ứng với dữ liệu đã commit |
| `@ApplicationModuleListener` | Kết hợp sau commit, async và transaction mới theo cấu hình | Phản ứng độc lập giữa application modules |
| Consumer qua message broker | Nhận payload sau bước externalization/transport | Consumer nằm ngoài tiến trình hoặc cần tích hợp riêng |

Ở `@TransactionalEventListener`, `fallbackExecution = true` là lựa chọn có chủ đích khi muốn listener cũng chạy nếu không có transaction; mặc định là `false`. Với callback `AFTER_COMMIT` cần ghi dữ liệu mới, nên tạo transaction mới thích hợp thay vì mặc định cho rằng transaction nguồn vẫn sẵn sàng ghi dữ liệu.

## 8. Ranh giới transaction là một phần kỳ vọng của consumer

Giả sử service đặt hàng:

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
        UUID orderId = orders.save(draft);
        events.publishEvent(new OrderPlaced(
                UUID.randomUUID(),
                orderId,
                clock.instant()
        ));
        return orderId;
    }
}
~~~

`OrderRepository`, `OrderDraft` và bean `Clock` là các thành phần minh họa; mục tiêu của ví dụ là cho thấy **publisher phát sự kiện trong transaction nghiệp vụ**. Việc gọi `publishEvent` không tự xác nhận transaction đã commit.

~~~mermaid
sequenceDiagram
    participant O as ordering
    participant DB as Database
    participant E as Spring events
    participant N as notification
    O->>DB: Ghi đơn hàng trong transaction
    O->>E: publish OrderPlaced
    alt Commit thành công
        O->>DB: Commit
        E-->>N: Sau commit: on(OrderPlaced)
        N->>N: Gửi xác nhận
    else Rollback
        O->>DB: Rollback
        Note over E,N: Listener AFTER_COMMIT không được kích hoạt
    end
~~~

Điều consumer **có thể kỳ vọng** phải được viết rõ:

1. `OrderPlaced` đại diện một trạng thái nghiệp vụ đã được publisher xác định.
2. Nếu listener được cấu hình `AFTER_COMMIT` và event publish trong transaction, consumer chỉ phản ứng khi transaction đó commit.
3. Sau commit, lỗi của listener không thể làm “rollback ngược” transaction đặt hàng đã hoàn tất.
4. Consumer có thể hoàn tất sau publisher và có thể được xử lý lại khi cơ chế khôi phục được cấu hình.

Nếu nghiệp vụ yêu cầu một thao tác bắt buộc **thành công trước khi xác nhận đơn hàng**, consumer xử lý sau commit không phải cơ chế phù hợp duy nhất. Khi đó cần facade/command đồng bộ hoặc workflow có trạng thái và bù trừ được thiết kế rõ.

## 9. Consumer phải chủ động về idempotency

Một event có thể bị xử lý lại khi ứng dụng retry sau lỗi, khi adapter phát lại message hoặc khi tiến trình dừng ở thời điểm nhạy cảm. Vì vậy, consumer nên giả định **có khả năng nhận trùng**, trừ khi có bảo đảm mạnh hơn được chứng minh từ toàn bộ hệ thống.

### 9.1. Phân biệt event ID và aggregate ID

Ví dụ:

~~~text
OrderPlaced(eventId=E1, orderId=O10)
OrderPaid  (eventId=E2, orderId=O10)
~~~

Hai event khác nhau cùng liên quan tới đơn `O10`. Nếu dedupe bằng `orderId`, consumer có thể vô tình chặn sự kiện hợp lệ thứ hai. Nếu dedupe bằng `eventId`, nó nhận diện từng sự kiện độc lập. Trường hợp một consumer xử lý nhiều loại event, khóa dedupe có thể bao gồm `consumerName` và `eventId`.

### 9.2. Thiết kế transaction xử lý local

Đối với consumer chỉ ghi vào database của mình, một chiến lược thường gặp:

1. Bắt đầu transaction của consumer.
2. Ghi dấu `(consumer_name, event_id)` có unique constraint.
3. Thực hiện cập nhật nghiệp vụ của consumer trong **cùng transaction**.
4. Commit; nếu xung đột khóa do event đã được xử lý, bỏ qua theo chính sách.

Ví dụ cấu trúc bảng minh họa:

~~~sql
CREATE TABLE consumed_event (
    consumer_name VARCHAR(120) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

DDL dùng kiểu `UUID` theo database có hỗ trợ; với hệ quản trị khác cần điều chỉnh kiểu dữ liệu. Việc **ghi dấu và cập nhật nghiệp vụ phải cùng transaction** để tránh đánh dấu đã xử lý rồi mất kết quả khi hệ thống lỗi. Cần xử lý đúng lỗi unique constraint nếu nhiều worker cạnh tranh.

### 9.3. Tác dụng phụ bên ngoài khó hơn

Đối với gửi email hoặc gọi API bên ngoài:

~~~text
Gửi email thành công
       |
       v
Ứng dụng crash trước khi ghi nhận "đã xử lý"
       |
       v
Retry có thể gửi lại email
~~~

Không thể mặc định một transaction database local bao trùm cả hệ thống email. Nếu bên nhận hỗ trợ **idempotency key**, có thể truyền `eventId` cùng một khóa ổn định; nếu không, cần chính sách vận hành phù hợp và thừa nhận giới hạn tránh trùng trong những cửa sổ lỗi cụ thể.

**Idempotency là trách nhiệm thiết kế của consumer**, không phải bảo đảm tự động từ tên event hoặc annotation listener.

## 10. Consumer và Event Publication Registry

Spring Modulith cung cấp **Event Publication Registry** để theo dõi các lần công bố tới listener được hỗ trợ khi ứng dụng cấu hình thành phần persistence thích hợp. Registry có thể ghi nhận publication cần xử lý, đánh dấu hoàn tất và giúp phát hiện publication chưa hoàn thành để phục vụ chiến lược khôi phục.

Điều này tác động trực tiếp tới consumer:

- Khi listener xử lý **thành công**, hạ tầng có thể ghi nhận publication đã hoàn tất theo cơ chế registry đang dùng.
- Khi listener xử lý **lỗi**, publication có thể còn ở trạng thái chưa hoàn tất để phục vụ kiểm tra/chạy lại.
- Khi quá trình **retry hoặc resubmission** diễn ra, consumer phải xử lý an toàn một event được gửi tới nhiều lần.

Registry chỉ là một mắt xích của tính tin cậy. Cần phân biệt:

| Câu hỏi | Thành phần chịu trách nhiệm |
| --- | --- |
| Event nào đã được publisher tạo? | Publisher và hợp đồng event |
| Publication nào cần/đã được listener xử lý? | Event Publication Registry và cấu hình ứng dụng |
| Khi nào chạy lại publication thất bại? | Cơ chế recovery/resubmission và chính sách vận hành |
| Chạy lại có tạo kết quả trùng không? | Logic idempotency của consumer |
| Hệ thống ngoài có nhận message không? | Adapter externalization, broker và consumer ngoài |

Không nên kết luận rằng cứ có registry thì mọi event có bảo đảm **exactly-once**, hoặc rằng chỉ cần `@Async` là publication sẽ được lưu bền sau crash. Mức độ delivery thực tế phụ thuộc version, dependency, storage, transaction và cách cấu hình.

## 11. Tương thích hợp đồng dưới góc nhìn consumer

Trong cùng modular monolith, publisher và consumer thường được triển khai trong một bản build; thay đổi Java record sẽ khiến các chỗ sử dụng không còn tương thích **có thể bị phát hiện khi compile**. Nhưng compile thành công **chưa đủ** nếu ý nghĩa của trường đã đổi.

Ví dụ ban đầu:

~~~java
public record OrderPlaced(UUID eventId, UUID orderId, Instant occurredAt) {}
~~~

Sau đó publisher đổi ý nghĩa `occurredAt` từ “thời điểm chấp nhận đơn” thành “thời điểm hoàn thành thanh toán” nhưng vẫn giữ tên và kiểu. `analytics` có thể tiếp tục chạy mà báo cáo sai.

### Ma trận thay đổi hợp đồng

| Thay đổi | Rủi ro cho consumer nội bộ | Cách xử lý |
| --- | --- | --- |
| Thêm trường mới vào Java record | Constructor, deserialization hoặc mã consumer liên quan có thể cần sửa | Kiểm tra toàn bộ consumer, cập nhật fixture và contract tests |
| Đổi tên/loại trường | Mã đọc accessor có thể không còn compile | Migration có kiểm soát, cập nhật đồng thời hoặc duy trì API chuyển tiếp |
| Đổi ý nghĩa trường, giữ nguyên kiểu | **Lỗi ngữ nghĩa âm thầm**, khó phát hiện bằng compile | Mô tả semantics và bổ sung test theo trường hợp nghiệp vụ |
| Đổi thời điểm phát event | Consumer có thể chạy trong trạng thái khác so với trước | Thống nhất mốc nghiệp vụ và test commit/rollback |
| Xóa event hoặc thay event type | Listener cũ không còn nhận đúng thông tin | Rà soát consumer và chuyển đổi theo lộ trình |
| Thêm consumer mới | Không cần sửa publisher nếu contract đã đủ | Đảm bảo ranh giới, tài nguyên và lỗi của consumer mới |

Đối với integration event qua broker, consumer có thể chạy phiên bản độc lập. Khi đó phải quản lý **schema version, serialization, compatibility và thời gian cùng tồn tại của các phiên bản**. Đừng suy từ cách record Java được compile trong cùng JVM rằng consumer ngoài hệ thống cũng được bảo vệ như vậy.

### Consumer-driven contract có nghĩa là gì?

Đây là cách làm trong đó consumer mô tả **những phần của hợp đồng mà nó thực sự phụ thuộc** và xây dựng test để phát hiện thay đổi gây hỏng nhu cầu ấy. Nó giúp publisher hiểu tác động khi phát triển event; không có nghĩa mỗi consumer được tự ý thay đổi định nghĩa sự thật nghiệp vụ.

Ví dụ, `analytics` có thể nêu các kỳ vọng kiểm chứng:

- `orderId` khác `null` và ổn định cho đơn đã ghi nhận.
- `occurredAt` dùng cùng hệ quy chiếu thời gian và phản ánh thời điểm chấp nhận đơn.
- Một event có thể được xử lý nhiều lần mà báo cáo không bị tăng trùng.

`notification` có thể có tập kỳ vọng khác: ID đơn hợp lệ, trigger chỉ sau commit, cơ chế xác định người nhận chính xác và chiến lược xử lý lỗi email.

## 12. Kiểm thử hợp đồng từ cả hai phía

Để bảo vệ consumer, nên kết hợp **kiểm tra kiến trúc**, **kiểm thử publisher**, **kiểm thử logic listener** và **kiểm thử runtime khi có transaction**.

### 12.1. Kiểm tra module không vượt API

~~~java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleArchitectureTest {

    @Test
    void verifyPublicContracts() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này giúp phát hiện phụ thuộc vào kiểu nội bộ, phụ thuộc vòng hoặc vi phạm `allowedDependencies` theo mô hình module và các rule được cấu hình. Nó **không** kiểm tra side effect email hay tính tin cậy của listener.

### 12.2. Kiểm tra publisher phát hợp đồng đúng

Spring Modulith có `PublishedEvents` để test các event được phát trong một module test:

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

    @Autowired
    OrderFacade orders;

    @Test
    void publishesOrderPlaced(PublishedEvents publishedEvents) {
        PlaceOrderRequest request = validOrderRequest();
        UUID orderId = orders.placeOrder(request);

        assertThat(publishedEvents.ofType(OrderPlaced.class))
                .extracting(OrderPlaced::orderId)
                .contains(orderId);
    }

    private PlaceOrderRequest validOrderRequest() {
        // Điền fixture hợp lệ theo domain cụ thể của ứng dụng.
        throw new UnsupportedOperationException("Create test fixture");
    }
}
~~~

Đây là ví dụ cách dùng API kiểm thử; phương thức `validOrderRequest()` là chỗ cần triển khai theo domain thực tế, nên **chưa phải một test hoàn chỉnh có thể chạy ngay**. Assertion `PublishedEvents` chứng minh event đã được **publish trong ngữ cảnh test**, không chứng minh mọi consumer đã nhận hoặc hoàn thành.

### 12.3. Kiểm tra logic của consumer bằng unit test

Ví dụ listener `notification` gọi đúng dịch vụ thuộc module của nó, có truyền `eventId` để hỗ trợ khử trùng lặp:

~~~java
package com.example.shop.notification.internal;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import com.example.shop.ordering.events.OrderPlaced;
import java.time.Instant;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class OrderNotificationListenerTest {

    @Test
    void delegatesEventIdentityToDelivery() {
        ReceiptDelivery delivery = mock(ReceiptDelivery.class);
        OrderNotificationListener listener =
                new OrderNotificationListener(delivery);
        OrderPlaced event = new OrderPlaced(
                UUID.randomUUID(),
                UUID.randomUUID(),
                Instant.parse("2026-11-25T08:00:00Z")
        );

        listener.on(event);

        verify(delivery).sendConfirmationOnce(
                event.eventId(),
                event.orderId()
        );
    }
}
~~~

Test trên kiểm tra **logic truyền hợp đồng vào service consumer**. Do gọi trực tiếp method listener, nó không xác nhận `@ApplicationModuleListener` chạy đúng pha transaction, async hay registry.

### 12.4. Integration test cho commit, rollback và retry

Các kịch bản tối thiểu:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Publisher commit thành công | Listener sau commit có thể phản ứng và ghi nhận kết quả |
| Publisher rollback sau publish | Listener `AFTER_COMMIT` **không** thực hiện side effect |
| Consumer xử lý thành công | Trạng thái hoàn thành phù hợp cơ chế registry đã cấu hình |
| Consumer gặp lỗi tạm thời | Lỗi được ghi nhận; có cơ chế khôi phục hoặc retry theo chính sách |
| Retry cùng event ID | Không tạo kết quả nghiệp vụ trùng |
| Hai consumer cùng nghe event | Mỗi consumer có kết quả/trạng thái độc lập theo cơ chế sử dụng |
| Consumer không còn xử lý event | Có cảnh báo hoặc quy trình phát hiện backlog publication |

Một bẫy kiểm thử: nếu test itself dùng `@Transactional` rồi tự rollback ở cuối, listener `AFTER_COMMIT` có thể **không chạy** dù code production đúng. Cần thiết lập commit/rollback thật sự bằng transaction boundary phù hợp (ví dụ service Spring có `@Transactional`, `TransactionTemplate` hoặc cơ chế test transaction phù hợp), đồng thời chờ kết quả đúng cách nếu listener async.

## 13. Quan sát từ góc nhìn người tiêu thụ

Khi có nhiều consumer, một dòng log “published OrderPlaced” không đủ để khẳng định hệ thống ổn định. Cần quan sát **theo sự kiện và theo từng consumer**.

Ví dụ thông tin nên có:

| Thông tin | Dùng để làm gì? |
| --- | --- |
| `eventId` | Ghép nhiều lần thử xử lý của cùng event |
| `orderId` | Liên hệ event với nghiệp vụ đặt hàng |
| `consumerName` / listener ID | Phân biệt notification với analytics |
| `occurredAt` và thời điểm xử lý | Đo độ trễ end-to-end |
| `attempt` / số lần retry | Phát hiện listener lỗi kéo dài |
| `status` và loại lỗi | Phát hiện backlog, phân loại sự cố |
| `correlationId` hoặc trace ID | Theo dõi luồng qua các thành phần liên quan |

Các metric thường có ích là **số publication chưa hoàn tất**, **độ trễ từ event tới completion**, **tỷ lệ thành công/thất bại theo listener** và **số lần retry**. Tùy hệ thống, có thể phát alert khi backlog vượt ngưỡng hoặc một loại lỗi tăng đột biến.

Không nên ghi toàn bộ payload nhạy cảm vào log để “dễ debug”. Consumer chỉ log các định danh, trường an toàn và mã lỗi cần thiết; tuân thủ quy tắc bảo vệ thông tin cá nhân và lưu giữ dữ liệu của ứng dụng.

## 14. Những sai lầm phổ biến của consumer

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Import `ordering.internal.OrderRepository` để lấy thêm dữ liệu | Phá vỡ ranh giới module và tăng coupling | Sử dụng event payload hoặc public query API |
| Suy `OrderPlaced` nghĩa là đã thanh toán | Kích hoạt hành vi sai trạng thái nghiệp vụ | Định nghĩa và kiểm thử ngữ nghĩa event; dùng event đúng mốc |
| Chạy gửi email bằng `@EventListener` đồng bộ trước commit | Có thể gửi xác nhận cho đơn sau đó rollback | Chọn listener sau commit nếu nghiệp vụ yêu cầu |
| Coi `publishEvent` là bảo đảm consumer hoàn tất | Bỏ sót lỗi và backlog | Tách publish, delivery, processing và completion |
| Dedupe mọi event bằng `orderId` | Có thể bỏ qua event khác của cùng đơn | Phân biệt `eventId` với aggregate ID |
| Ghi dấu đã xử lý ngoài transaction cập nhật dữ liệu | Mất kết quả hoặc báo đã hoàn tất sai | Dùng transaction và ràng buộc duy nhất phù hợp |
| Retry email nhưng không quan tâm gửi trùng | Người dùng nhận nhiều email | Idempotency key hoặc chính sách xử lý giới hạn rõ |
| Sửa ý nghĩa một trường nhưng không thông báo consumer | Lỗi ngữ nghĩa khó nhận biết | Test hợp đồng và quản lý thay đổi |
| Nghĩ `@Async` thay thế registry/broker | Công việc chưa hoàn thành có thể mất khi crash | Thiết kế persistence và recovery theo yêu cầu |
| Chỉ kiểm thử listener bằng gọi trực tiếp method | Không phát hiện lỗi transaction/async cấu hình | Bổ sung integration test theo runtime thật |

## 15. Bài thực hành: ba consumer của một hợp đồng

**Bối cảnh:** Ứng dụng `com.example.shop` có module `ordering` phát `OrderPlaced`, còn `notification`, `analytics` và `loyalty` có ba phản ứng khác nhau.

### Phần A — Xác định trách nhiệm

1. Với mỗi consumer, mô tả **đầu vào cần thiết**, **side effect**, **mức độ chịu trễ**, **điều kiện thành công** và **cách xử lý lặp**.
2. Chỉ ra đâu là dữ liệu thực sự thuộc `OrderPlaced` và đâu là dữ liệu nên lấy từ public query API hoặc do consumer tự quản lý.
3. Giải thích vì sao `ordering` không nên gọi trực tiếp ba service tiêu thụ khi đó chỉ là các phản ứng sau commit.

### Phần B — Tạo hợp đồng và listener

1. Tạo `OrderPlaced(UUID eventId, UUID orderId, Instant occurredAt)` trong `ordering.events`.
2. Công bố `ordering.events` qua `@NamedInterface("events")`.
3. Giới hạn module `notification` bằng `allowedDependencies = "ordering::events"`.
4. Viết `@ApplicationModuleListener` trong `notification.internal`, chỉ dùng event contract và một service thuộc chính module `notification`.
5. Thêm `analytics` listener mà không sửa module publisher; kiểm tra hướng import Java.

### Phần C — Bảo đảm hợp đồng khi có lỗi

1. Tạo test kiến trúc `ApplicationModules.of(ShopApplication.class).verify()`.
2. Kiểm tra publisher phát event đúng `orderId` và `eventId`.
3. Tạo transaction rollback sau khi publish; listener sau commit phải không thực hiện side effect.
4. Mô phỏng listener email lỗi sau commit; theo dõi publication chưa hoàn tất theo hạ tầng đã cấu hình.
5. Thử xử lý lại cùng `eventId` trong từng consumer, xác minh không cộng thống kê hoặc điểm thưởng hai lần.
6. Thử thay đổi ngữ nghĩa `occurredAt` mà không đổi kiểu; giải thích vì sao compile có thể vẫn PASS nhưng consumer có thể diễn giải sai.

### Phần D — Bảng nghiệm thu đề xuất

| Tiêu chí | Bằng chứng mong đợi |
| --- | --- |
| Module consumer chỉ biết hợp đồng công khai | `verify()` PASS, không có import nội bộ |
| Mỗi consumer xử lý nghiệp vụ riêng | Code listener/service trong đúng module sở hữu |
| Sự kiện có ý nghĩa ổn định | Định nghĩa rõ `OrderPlaced` và ba trường |
| Sau rollback không có side effect sau commit | Integration test transaction PASS |
| Retry không nhân đôi kết quả | Test idempotency với cùng `eventId` PASS |
| Có thể chẩn đoán consumer thất bại | Log/metric/registry nhận diện đúng event và listener |

## 16. Câu hỏi tự kiểm tra

**Câu 1. Consumer của `OrderPlaced` có cần biết publisher dùng JDBC hay JPA không?**

Không. Đó là chi tiết triển khai của `ordering`. Consumer chỉ cần hợp đồng sự kiện và, nếu thật sự cần, các API công khai được cho phép.

**Câu 2. Consumer có thể yêu cầu thêm trường vào event không?**

Có thể đề xuất theo nhu cầu nghiệp vụ rõ ràng. Tuy nhiên publisher sở hữu ngữ nghĩa của sự thật; việc thêm trường phải cân nhắc tính ổn định, bảo mật và những consumer khác.

**Câu 3. Hai listener nhận `OrderPlaced` có bắt buộc hoàn tất cùng lúc không?**

Không. Mỗi listener có chính sách xử lý và thời gian hoàn thành riêng. Nếu async, thứ tự và thời gian hoàn tất phụ thuộc hạ tầng thực thi.

**Câu 4. Vì sao `eventId` thường quan trọng với consumer hơn trong retry so với chỉ dùng `orderId`?**

Vì một đơn có thể tạo nhiều sự kiện hợp lệ. `eventId` định danh lần xảy ra cụ thể; `orderId` định danh aggregate nghiệp vụ.

**Câu 5. `PublishedEvents` xác nhận có event là đã đủ chứng minh consumer gửi email thành công chưa?**

Chưa. Nó xác minh việc phát event trong test. Cần test listener, transaction, hạ tầng gửi và cơ chế xử lý lỗi độc lập.

**Câu 6. Event Publication Registry có loại bỏ nhu cầu idempotency ở consumer không?**

Không. Với retry và các cửa sổ lỗi sau side effect, consumer vẫn cần bảo vệ trước xử lý trùng.

## 17. Kết luận

Người tiêu thụ hợp đồng sự kiện là bên **đọc và diễn giải một sự thật nghiệp vụ đã được công bố** rồi tự chịu trách nhiệm về phản ứng tương ứng. Trong Spring Modulith, consumer nên phụ thuộc vào API hoặc named interface công khai của publisher, giữ service/repository nội bộ trong module sở hữu và dùng application events để mở rộng phản ứng mà không buộc publisher biết từng listener.

Hợp đồng có giá trị khi các consumer hiểu thống nhất **ngữ nghĩa dữ liệu, thời điểm sự kiện có hiệu lực, giới hạn của transaction và điều kiện xử lý lại**. Để giao sự kiện đáng tin cậy, cần kết hợp listener sau commit phù hợp, Event Publication Registry và chiến lược recovery khi được cấu hình, idempotency của từng consumer, kiểm thử kiến trúc/hành vi và quan sát kết quả theo event ID. Những yếu tố đó cho phép nhiều module tiến hóa độc lập mà vẫn giữ được trách nhiệm và tính nhất quán của nghiệp vụ.
