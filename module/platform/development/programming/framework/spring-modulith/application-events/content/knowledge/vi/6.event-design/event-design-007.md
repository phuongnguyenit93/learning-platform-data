# Correlation identifier

## 1. Tại sao event cần correlation identifier?

Trong một **modular monolith**, một yêu cầu nghiệp vụ có thể tạo ra nhiều application event. Chẳng hạn, khi hệ thống ghi nhận một đơn hàng đã thanh toán, module `orders` phát `OrderPaid`; module `loyalty` cộng điểm rồi phát `PointsGranted`; module `notifications` tiếp tục gửi thông báo. Các bước có thể diễn ra trong những transaction và những luồng thực thi khác nhau.

Khi khách hàng báo “tôi đã thanh toán nhưng chưa nhận được thông báo cộng điểm”, chỉ biết có event `OrderPaid` và `PointsGranted` là chưa đủ. Người vận hành cần trả lời: **những event, bản ghi publication, lần retry và dòng log nào thuộc cùng một quy trình?**

**Correlation identifier (correlation ID, `correlationId`)** là một định danh được **giữ ổn định xuyên suốt các thao tác thuộc cùng một luồng nghiệp vụ**. Mỗi event trong chuỗi mang theo định danh ấy để có thể tìm, đối chiếu và truy vết các bước có liên quan.

Ví dụ:

~~~mermaid
flowchart LR
    R["Yêu cầu ghi nhận thanh toán<br/>correlationId = C-42"] --> O["orders<br/>OrderPaid<br/>eventId = E-1"]
    O --> L["loyalty<br/>PointsGranted<br/>eventId = E-2"]
    L --> N["notifications<br/>Xử lý thông báo"]
    O -.-> CID["correlationId = C-42"]
    L -.-> CID
    N -.-> CID
~~~

Các giá trị `C-42`, `E-1`, `E-2` chỉ là ký hiệu minh họa; hệ thống thực tế nên dùng định dạng có độ duy nhất cao như UUID. **`correlationId` của chuỗi là một**, còn **`eventId` của mỗi event là khác nhau**.

Đối với module `SPRING_MODULITH_APPLICATION_EVENTS`, correlation ID là một thành phần thiết kế hợp đồng event giúp giảm phụ thuộc trực tiếp giữa các module, đồng thời hỗ trợ quan sát các listener chạy sau commit, kiểm tra publication bị lỗi và phân tích lần xử lý lại. Bản thân correlation ID **không tạo ra cơ chế retry hay bảo đảm giao nhận**; nó cung cấp ngữ cảnh để hiểu chúng.

Sau bài học, bạn cần có thể:

- Phân biệt `correlationId`, `eventId`, `causationId`, khóa nghiệp vụ và tracing `traceId`.
- Xác định nơi khởi tạo và cách truyền correlation ID giữa các event, kể cả qua `@ApplicationModuleListener` bất đồng bộ.
- Thiết kế event bất biến mang metadata đủ để tìm chuỗi xử lý sau commit và trong quá trình phục hồi.
- Viết log và test kiểm tra chuỗi correlation, không nhầm correlation ID với khóa chống xử lý trùng.

## 2. Phân biệt các loại định danh

Các hệ thống thường có nhiều định danh cùng xuất hiện trong một event, nhưng mỗi loại trả lời một câu hỏi khác nhau:

| Trường | Câu hỏi trả lời | Phạm vi ổn định | Ví dụ |
| --- | --- | --- | --- |
| `correlationId` | Những công việc nào thuộc cùng một quy trình? | Giữ nguyên cho cả chuỗi sự kiện liên quan | UUID của luồng ghi nhận thanh toán |
| `eventId` | Đây là lần xuất hiện sự kiện nào? | Riêng cho một event logic, giữ nguyên khi phát lại event đó | UUID của `OrderPaid` |
| `causationId` | Event nào trực tiếp dẫn đến event này? | Trỏ tới `eventId` của event nguyên nhân gần nhất | `PointsGranted.causationId = OrderPaid.eventId` |
| `orderId` / business key | Dữ liệu nghiệp vụ nào đang được xử lý? | Theo thực thể/quy tắc nghiệp vụ | UUID đơn hàng |
| `traceId` | Các span kỹ thuật của một trace phân tán nào liên quan? | Theo ngữ cảnh tracing hiện hoạt | ID do hệ tracing quản lý |
| `publicationId` | Bản ghi giao event đến một listener cụ thể nào? | Theo bản ghi trong publication registry | ID nội bộ do registry quản lý |

Những khác biệt cần nhớ:

1. **`eventId` không phải `correlationId`.** Hai event sinh ra trong cùng quy trình có hai `eventId` khác nhau nhưng thường dùng chung một `correlationId`.
2. **`causationId` không phải `correlationId`.** Hai event anh em cùng do `OrderPaid` kích hoạt có thể cùng `causationId` nhưng mỗi event có `eventId` riêng; cả hai chia sẻ `correlationId`.
3. **`orderId` không thay thế `correlationId`.** Một đơn có thể đi qua nhiều quy trình độc lập: đặt hàng, thanh toán, hoàn tiền, xử lý khiếu nại. Các quy trình này có thể cần correlation ID khác nhau.
4. **`traceId` không mặc nhiên là correlation ID nghiệp vụ.** Trace kỹ thuật có thể kết thúc khi HTTP request hoàn thành; một listener được retry ngày hôm sau hoặc một message được nhận ở tiến trình khác có thể có trace mới.
5. **ID của Event Publication Registry không phải ID sự kiện do bạn thiết kế.** Registry theo dõi bản ghi giao nhận cho listener; không nên phụ thuộc vào cấu trúc ID nội bộ của registry để biểu diễn luồng nghiệp vụ.

Correlation ID thường là một **chuỗi định danh opaque**: bên nhận so sánh, ghi log và chuyển tiếp mà không cần phân tích nội dung. UUID là lựa chọn phổ biến, nhưng một chuỗi do tổ chức quản lý cũng có thể phù hợp nếu chuẩn hóa độ dài, cú pháp và nguồn tin cậy.

## 3. Chọn ranh giới của một correlation ID

Câu hỏi khó nhất là “**cùng một quy trình**” nghĩa là gì trong hệ thống cụ thể. Nếu mỗi thao tác nhỏ đều tạo một correlation ID mới, việc truy vết chuỗi sẽ bị đứt. Nếu dùng một ID cho toàn bộ vòng đời khách hàng, tập kết quả quá rộng và mất khả năng phân biệt các công việc.

Một số quy ước thực tế:

| Tình huống | Quy tắc thường phù hợp |
| --- | --- |
| Một lần đặt đơn kích hoạt kiểm tra tồn kho và gửi xác nhận | Tất cả event do lần đặt đơn này gây ra mang cùng correlation ID |
| Một event tạo nhiều event phản ứng ở các module | Mỗi event con có `eventId` riêng, kế thừa `correlationId` của event cha |
| Listener lỗi rồi nhận lại **chính event cũ** | Giữ nguyên `eventId` và `correlationId` của event cũ |
| Người dùng chủ động bắt đầu thao tác hoàn tiền mới cho cùng một đơn | Thường tạo correlation ID mới cho quy trình hoàn tiền; liên kết với đơn qua business key |
| Một tác vụ định kỳ quét 1.000 đơn độc lập | Có thể dùng một `batchId` để liên kết cả lượt chạy và correlation ID riêng cho từng đơn, tùy yêu cầu vận hành |
| Một thao tác từ đối tác có request ID đã xác thực | Có thể dùng hoặc ánh xạ ID upstream theo chính sách; kiểm tra nguồn và định dạng trước khi tin cậy |

**Không tự động coi mọi event có cùng `orderId` là cùng correlation.** Một correlation ID mô tả **một luồng nguyên nhân / công việc**, trong khi business key mô tả **đối tượng mà công việc tác động lên**.

Khi có quy trình cha và quy trình con kéo dài nhiều ngày, có thể giữ thêm `workflowId` hoặc `parentCorrelationId` để liên kết ở cấp cao hơn. Đừng thêm các trường này nếu chưa có nhu cầu truy vết cụ thể và quy ước rõ ràng.

## 4. Đặt metadata ngay trong hợp đồng event

Trong Spring Modulith, các module nên giao tiếp bằng kiểu event công khai, bất biến và có ý nghĩa nghiệp vụ. Correlation ID nên được **mang theo trong payload hoặc metadata bền vững đi cùng event**, thay vì chỉ nằm trong biến của request hiện tại.

Ví dụ `orders` công bố event sau khi đã xác nhận thanh toán thành công:

~~~java
// com/example/shop/orders/OrderPaid.java
package com.example.shop.orders;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

public record OrderPaid(
        UUID eventId,
        UUID correlationId,
        UUID causationId,
        UUID orderId,
        UUID customerId,
        Instant occurredAt
) {
    public OrderPaid {
        Objects.requireNonNull(eventId, "eventId");
        Objects.requireNonNull(correlationId, "correlationId");
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerId, "customerId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        // causationId = null khi đây là event gốc của chuỗi.
    }
}
~~~

Một số lựa chọn thiết kế trong ví dụ:

- `record` làm payload khó bị thay đổi ngoài ý muốn sau khi publish.
- `eventId` xác định duy nhất một event logic; **không tạo lại ID này khi retry cùng event**.
- `correlationId` bắt buộc để listener không phải đoán ngữ cảnh từ request đang chạy.
- `causationId` có thể `null` khi không có event trực tiếp đứng trước; nếu ứng dụng yêu cầu non-null tuyệt đối, có thể mô hình bằng kiểu metadata khác.
- `occurredAt` thể hiện thời điểm xảy ra sự kiện nghiệp vụ, không phải thời điểm listener chạy hoặc được retry.
- `orderId` và `customerId` cung cấp dữ liệu cần thiết để consumer hoạt động; không truyền entity JPA, Spring bean hay đối tượng mutable nội bộ.

Hợp đồng chung kiểu `EventMetadata` cũng có thể được dùng nếu nhiều event cần cùng cấu trúc. Tuy nhiên, không nên buộc toàn bộ module phụ thuộc vào một thư viện “common” chứa cả entity và service nghiệp vụ. Một kiểu metadata nhỏ, ổn định với quy tắc sở hữu rõ ràng là đủ.

Nếu event được lưu bền, externalize hoặc trao đổi với hệ thống khác, **cách serialize/deserialize metadata phải được kiểm thử** theo backend và phiên bản thư viện đang dùng. Thay đổi kiểu dữ liệu của correlation ID có thể làm bản ghi publication cũ không đọc lại được nếu không có chiến lược tương thích.

## 5. Luồng mẫu: orders → loyalty → notifications

Giả sử module `orders` phát `OrderPaid` sau khi đã ghi nhận thanh toán hợp lệ. `loyalty` cộng điểm cho đơn đã thanh toán, phát `PointsGranted` và `notifications` gửi email thông báo điểm. Mỗi module tự sở hữu dữ liệu và hành vi của mình.

~~~mermaid
sequenceDiagram
    participant API as Cổng vào
    participant O as orders
    participant R as Event Publication Registry
    participant L as loyalty
    participant N as notifications
    API->>O: Ghi nhận thanh toán (correlationId=C1)
    O->>O: Commit thay đổi OrderPaid
    O-->>R: Publication của OrderPaid (C1, E1)
    R-->>L: OrderPaid (C1, E1)
    L->>L: Cộng điểm trong transaction riêng
    L-->>R: Publication của PointsGranted (C1, E2, cause=E1)
    R-->>N: PointsGranted (C1, E2)
    N->>N: Ghi nhận/gửi thông báo
~~~

Sơ đồ thể hiện **quan hệ nhân quả**, lược bỏ chi tiết thời điểm registry ghi publication trong transaction nguồn. Khi registry bền vững được cấu hình đúng, các bản ghi publication cho transactional listeners được ghi theo cơ chế transaction của Spring Modulith và dùng để phát hiện lần xử lý chưa hoàn tất.

### 5.1. Tạo correlation ID ở điểm bắt đầu quy trình

Điểm bắt đầu có thể là HTTP controller, webhook đã xác thực, scheduler hoặc một listener bắt đầu quy trình mới. Chính điểm này phải xác định **correlation ID chuẩn của lần xử lý**.

Ví dụ trong lớp tiếp nhận kết quả thanh toán **đã được xác thực**:

~~~java
// Phương thức minh họa tại boundary nhận thông tin thanh toán hợp lệ
public void onVerifiedPayment(UUID orderId) {
    UUID correlationId = UUID.randomUUID();
    orderPaymentService.recordVerifiedPayment(orderId, correlationId);
}
~~~

Ứng dụng thực cần xác thực webhook/chữ ký, kiểm tra giao dịch và chống xử lý lại yêu cầu thanh toán trước khi đánh dấu đơn đã trả tiền. Nếu thao tác do một bước nghiệp vụ trước đó kích hoạt, nên **truyền correlation ID sẵn có** thay vì tạo mới tùy ý.

Với header HTTP như `X-Correlation-ID` do client gửi, không mặc nhiên tin cậy giá trị đó: hãy giới hạn kích thước, kiểm tra định dạng, tránh ký tự có thể làm hỏng log và phân biệt ID bên ngoài với ID nội bộ. Một lựa chọn an toàn là tạo UUID nội bộ và chỉ lưu ID phía đối tác dưới tên riêng (`externalRequestId`) nếu cần đối soát.

### 5.2. Publisher tạo event gốc với correlation ID được truyền vào

~~~java
// com/example/shop/orders/internal/OrderPaymentService.java
package com.example.shop.orders.internal;

import com.example.shop.orders.OrderPaid;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderPaymentService(OrderRepository orders,
                               ApplicationEventPublisher publisher,
                               Clock clock) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void recordVerifiedPayment(UUID orderId, UUID correlationId) {
        OrderEntity order = orders.findById(orderId).orElseThrow();
        if (order.isPaid()) {
            return; // Giao dịch đã ghi nhận, không tạo event mới.
        }
        order.markPaid(); // Kiểm tra quy tắc và cập nhật trạng thái.

        publisher.publishEvent(new OrderPaid(
                UUID.randomUUID(), // eventId riêng cho OrderPaid
                correlationId,      // Giữ từ boundary
                null,               // Event gốc không có causationId
                order.getId(),
                order.getCustomerId(),
                Instant.now(clock)));
    }
}
~~~

`OrderRepository`, `OrderEntity` và bean `Clock` là những thành phần giả định đã có. Mã minh họa tập trung vào thiết kế event: việc kiểm chứng thanh toán và tính nguyên tử khi hai callback đến đồng thời cần được xử lý bởi logic nghiệp vụ/constraint riêng.

**`publishEvent(...)` không đồng nghĩa transaction đã commit.** Listener đồng bộ thông thường có thể chạy ngay; listener sau commit sẽ chỉ chạy sau khi transaction nguồn commit thành công. Nếu transaction nguồn rollback, các listener `AFTER_COMMIT` sẽ không được gọi như thể việc thanh toán đã hoàn tất.

### 5.3. Consumer kế thừa correlation ID khi phát event tiếp theo

`loyalty` công bố event trong public API của chính nó:

~~~java
// com/example/shop/loyalty/PointsGranted.java
package com.example.shop.loyalty;

import java.time.Instant;
import java.util.UUID;

public record PointsGranted(
        UUID eventId,
        UUID correlationId,
        UUID causationId,
        UUID orderId,
        UUID customerId,
        int points,
        Instant occurredAt
) {}
~~~

Listener `loyalty` tiêu thụ API event của `orders`:

~~~java
// com/example/shop/loyalty/internal/OrderPaidListener.java
package com.example.shop.loyalty.internal;

import com.example.shop.orders.OrderPaid;
import com.example.shop.loyalty.PointsGranted;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderPaidListener {
    private final LoyaltyLedger ledger;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    OrderPaidListener(LoyaltyLedger ledger,
                      ApplicationEventPublisher publisher,
                      Clock clock) {
        this.ledger = ledger;
        this.publisher = publisher;
        this.clock = clock;
    }

    @ApplicationModuleListener
    void on(OrderPaid parent) {
        // Trả về true khi thực sự ghi thêm một khoản thưởng mới.
        if (!ledger.creditOnce(parent.orderId(), parent.customerId(), 10)) {
            return;
        }

        publisher.publishEvent(new PointsGranted(
                UUID.randomUUID(),   // Event con có eventId mới
                parent.correlationId(), // Giữ nguyên correlationId
                parent.eventId(),      // Ghi nhận nguyên nhân trực tiếp
                parent.orderId(),
                parent.customerId(),
                10,
                Instant.now(clock)));
    }
}
~~~

`LoyaltyLedger.creditOnce(...)` là hợp đồng minh họa. Cần cài đặt nó với unique constraint phù hợp trên đơn/vai trò phần thưởng, bảo đảm **ghi sổ điểm và cập nhật số dư trong cùng transaction**, đồng thời xử lý cạnh tranh khi hai listener chạy đồng thời.

`@ApplicationModuleListener` của Spring Modulith cung cấp mẫu listener bất đồng bộ, xử lý sau commit và trong transaction mới (`REQUIRES_NEW`). Ứng dụng phải cấu hình hỗ trợ async/executor phù hợp, ví dụ bật `@EnableAsync` nếu cần. Trong transaction của listener, việc ghi điểm và phát `PointsGranted` nên cùng cơ chế commit; nếu dùng Event Publication Registry bền vững, publication cho event con cũng cần được ghi một cách nhất quán.

**Đừng copy `parent.eventId()` vào `PointsGranted.eventId`**: đó là hai sự kiện khác nhau. Event con phải có ID mới; `parent.eventId()` thuộc trường `causationId`. `correlationId` vẫn giữ nguyên.

### 5.4. Listener cuối đọc trực tiếp correlation ID từ event

~~~java
// com/example/shop/notifications/internal/PointsNotificationListener.java
package com.example.shop.notifications.internal;

import com.example.shop.loyalty.PointsGranted;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class PointsNotificationListener {
    private static final Logger log =
            LoggerFactory.getLogger(PointsNotificationListener.class);
    private final NotificationService notifications;

    PointsNotificationListener(NotificationService notifications) {
        this.notifications = notifications;
    }

    @ApplicationModuleListener
    void on(PointsGranted event) {
        String previous = MDC.get("correlationId");
        MDC.put("correlationId", event.correlationId().toString());
        try {
            log.info("Handling PointsGranted eventId={} causationId={} orderId={}",
                    event.eventId(), event.causationId(), event.orderId());
            notifications.sendPointsNoticeOnce(
                    event.orderId(), event.customerId(), event.points());
        } finally {
            if (previous == null) {
                MDC.remove("correlationId");
            } else {
                MDC.put("correlationId", previous);
            }
        }
    }
}
~~~

Để correlation ID thực sự hiện ra trên log, cấu hình logging phải xuất khóa MDC `correlationId` (ví dụ trong pattern hoặc JSON structured logging). `NotificationService` và các bean khác trong ví dụ là hợp đồng minh họa; hiệu ứng gửi email cần cơ chế idempotency riêng.

**Lý do phải lấy ID từ event:** listener `@ApplicationModuleListener` có thể chạy trên thread khác với HTTP request gốc. `MDC` thường là thread-local; giá trị trong thread publisher không được bảo đảm tự xuất hiện ở thread listener. Hơn nữa, khi retry hoặc restart, thread ban đầu không còn tồn tại. Việc phục hồi từ event đã lưu mới là nguồn ngữ cảnh phù hợp.

## 6. Event metadata và context kỹ thuật không phải cùng một thứ

Một request HTTP có thể mang:

- `X-Correlation-ID`: quy ước ứng dụng/đối tác, có thể được sinh hoặc kiểm tra tại boundary.
- `traceparent` theo W3C Trace Context: metadata để hệ thống tracing nối các span kỹ thuật.
- `X-Request-ID`: định danh một HTTP request cụ thể, không nhất thiết bao trùm toàn bộ quy trình event.

Trong hệ thống có Micrometer Tracing/OpenTelemetry, `traceId` giúp xem độ trễ và quan hệ giữa các span. Còn `correlationId` do ứng dụng chọn có thể duy trì **xuyên qua các lần chạy bất đồng bộ và retry** ngay cả khi trace kỹ thuật được tạo mới.

Một sự kiện trong DB có thể được phục hồi sau nhiều giờ. Khi đó:

~~~text
Ngày 1:
  correlationId = C1
  eventId       = E1
  traceId       = T1
  listener lỗi trước khi hoàn tất

Ngày 2:
  correlationId = C1   # Kế thừa từ cùng event được phát lại
  eventId       = E1   # Vẫn là event logic E1
  traceId       = T2   # Trace kỹ thuật có thể khác
~~~

Không giả định Spring Modulith tự đồng bộ `correlationId` với tracing framework. Nếu cần nối trace/span khi xử lý ở thread khác, cấu hình propagation/instrumentation tương ứng và kiểm chứng hành vi. Dù có tracing, việc **ghi correlation ID vào event** vẫn giúp truy vết tại mức nghiệp vụ lâu dài hơn thời gian giữ trace.

Khi thiết kế log và metrics:

1. Ghi `correlationId`, `eventId`, `causationId` và business key cần thiết ở **log/event audit** có kiểm soát quyền truy cập.
2. Ghi trạng thái giao nhận: received, succeeded, failed, resubmitted; dùng timestamp và latency để đối soát.
3. Với hệ metrics, **không đặt UUID correlation ID làm label/tag cho từng time series**: số lượng giá trị khác nhau rất lớn, dễ gây vấn đề cardinality. Dùng tên event, tên module, trạng thái và loại lỗi làm metric tags; ID chi tiết giữ trong log/trace.
4. Không đặt email, token, thông tin thanh toán hay dữ liệu cá nhân vào correlation ID, và không đưa payload nhạy cảm nguyên vẹn vào log.

## 7. Tác dụng khi retry và Event Publication Registry

**Event Publication Registry** của Spring Modulith giúp theo dõi việc publish đến các transactional listeners, nhận diện publication chưa hoàn tất và hỗ trợ phục hồi tùy implementation/cấu hình. Nó không phải cơ chế tự sinh `correlationId`, `eventId` hoặc `causationId` cho domain event của bạn. Các trường ấy phải được thiết kế trong hợp đồng event và bảo toàn trong khi serialize, lưu, phục hồi.

Một ví dụ sự cố:

~~~mermaid
sequenceDiagram
    participant O as orders
    participant R as Publication Registry
    participant L as loyalty
    O->>R: OrderPaid(E1, C1) được ghi publication
    R-->>L: Giao OrderPaid(E1, C1)
    L--xR: Xử lý lỗi, publication chưa hoàn tất
    Note over R,L: Sau khi sửa lỗi / kích hoạt phục hồi
    R-->>L: Giao lại OrderPaid(E1, C1)
    L->>L: Ghi điểm idempotent
    L-->>R: Hoàn tất publication
~~~

Khi giao lại **cùng một event**, ID của event và correlation phải giữ nguyên. Nếu listener sau đó phát một event mới `PointsGranted`, event mới có `eventId` riêng và `causationId = E1`. Điều này giúp truy vấn toàn bộ chuỗi, kể cả đoạn đã từng thất bại.

Lưu ý:

- **Correlation ID không phải khóa idempotency.** Hai event hợp lệ trong cùng quy trình có cùng correlation ID; việc deduplicate toàn bộ sự kiện theo ID này sẽ làm mất event.
- Khi xử lý một event cho một listener, có thể dùng `eventId` làm khóa nhận biết event đã xử lý, hoặc dùng business key như `(orderId, rewardType)` khi chính quy tắc nghiệp vụ yêu cầu chỉ một lần thực hiện. Hai loại khóa giải quyết các mục tiêu khác nhau.
- **Giao lại có thể xảy ra ngay cả sau khi tác động bên ngoài thành công** nếu tiến trình dừng trước khi registry ghi completion. Vì vậy listener cần idempotency; publication registry không tự cung cấp exactly-once cho gửi email hoặc gọi API bên ngoài.
- Cần chọn implementation registry bền vững (ví dụ JDBC/JPA), bảo đảm quản lý transaction và cấu hình chính sách resubmit phù hợp. Không được mặc định tất cả sự kiện lỗi tự retry vô hạn chỉ vì dùng `@ApplicationModuleListener`.
- Đối với dead-letter/đối soát, lưu nguyên correlation ID và event ID trong hồ sơ lỗi để người vận hành thấy đúng quan hệ với event gốc.

Không nên tạo `correlationId` mới mỗi lần listener bắt đầu xử lý. Việc làm này khiến lần xử lý lỗi, retry và các event con không còn cùng một chuỗi khi tra cứu log.

## 8. Trường hợp fan-out, fan-in và quy trình mới

### 8.1. Một event kích hoạt nhiều listener

Ví dụ `OrderPaid(E1, C1)` kích hoạt đồng thời `loyalty` và `reporting`:

~~~text
OrderPaid      eventId=E1, correlationId=C1, causationId=null
├── PointsGranted   eventId=E2, correlationId=C1, causationId=E1
└── RevenueRecorded eventId=E3, correlationId=C1, causationId=E1
~~~

Hai event con chia sẻ correlation ID vì cùng một luồng; cùng causation ID vì do cùng event cha trực tiếp gây ra. Chúng **không chia sẻ event ID**, vì là hai sự kiện khác nhau. Thứ tự hoàn tất của hai listener async không được bảo đảm, nên không được suy luận nhân quả chỉ từ timestamp.

### 8.2. Nhiều event cùng góp phần tạo event mới

Ví dụ một quy trình kết hợp `PaymentCaptured` và `StockReserved` mới phát `OrderReadyToShip`. Lúc này quan hệ nhân quả có **nhiều đầu vào**: một trường `causationId` đơn lẻ có thể không mô tả được mọi nguyên nhân. Có thể lưu danh sách `causationIds` hoặc trạng thái workflow với ID các event liên quan, tùy nhu cầu truy vết.

Không nên tự chọn correlation ID của event đến cuối cùng nếu hai event thuộc hai quy trình độc lập. Cần quy ước rõ **workflow sở hữu quá trình ghép**, khóa liên kết nghiệp vụ và cách tham chiếu hai luồng. Đây là quyết định thiết kế domain, không phải hành vi tự động của Spring Modulith.

### 8.3. Chuyển tiếp ra hệ thống khác

Nếu application event được externalize qua Kafka/RabbitMQ hoặc dịch vụ HTTP khác, `correlationId` cần được chuyển trong payload hay message headers theo hợp đồng của hệ thống đích. Đảm bảo consumer ở phía ngoài có thể đọc ID và đưa lại vào event tiếp theo; đồng thời kiểm soát giá trị header từ những bên không tin cậy.

**ApplicationEventPublisher** cơ bản chỉ giao event trong cùng application Spring. Dùng `correlationId` không tự biến event thành message giữa các tiến trình và không giải quyết việc phát tán bền vững ra broker.

## 9. Thiết kế kiểm thử cho correlation identifier

Kiểm thử phải nhìn vào **hợp đồng event** và hành vi của listener. Có thể chia thành các mức:

| Mức | Điều cần khẳng định | Cách kiểm tra |
| --- | --- | --- |
| Unit test publisher | Event gốc mang đúng correlation ID của boundary | Capture tham số `publishEvent` và kiểm tra `OrderPaid` |
| Unit test listener | Event con kế thừa correlation, tạo event ID mới và đặt causation ID đúng | Stub ledger thành công, capture `PointsGranted` |
| Integration test sau commit | Listener chỉ xử lý khi transaction nguồn commit | Test commit thật và chờ async có timeout |
| Retry/resubmit | Event được phát lại giữ ID, có thể tìm cùng chuỗi log | Gây lỗi listener, khôi phục publication và kiểm tra metadata |
| Idempotency | Hai lần nhận cùng event không tạo hai khoản thưởng | Unique constraint + integration test concurrency |
| Quan sát | Log chứa correlation và event ID ngay cả khi xử lý ở thread khác | Capture structured log/MDC trong listener |

### 9.1. Ví dụ unit test listener

Minh họa kiểm thử bằng JUnit 5, Mockito và AssertJ. `LoyaltyLedger` trả `true` khi thực sự cộng điểm:

~~~java
package com.example.shop.loyalty.internal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.*;

import com.example.shop.loyalty.PointsGranted;
import com.example.shop.orders.OrderPaid;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.context.ApplicationEventPublisher;

class OrderPaidListenerTest {

    @Test
    void propagatesCorrelationAndRecordsCausation() {
        LoyaltyLedger ledger = mock(LoyaltyLedger.class);
        ApplicationEventPublisher publisher =
                mock(ApplicationEventPublisher.class);
        Clock clock = Clock.fixed(
                Instant.parse("2026-01-02T03:04:05Z"), ZoneOffset.UTC);
        when(ledger.creditOnce(any(), any(), anyInt()))
                .thenReturn(true);

        UUID correlationId = UUID.randomUUID();
        UUID parentEventId = UUID.randomUUID();
        OrderPaid parent = new OrderPaid(
                parentEventId, correlationId, null,
                UUID.randomUUID(), UUID.randomUUID(),
                Instant.now(clock));

        new OrderPaidListener(ledger, publisher, clock).on(parent);

        ArgumentCaptor<PointsGranted> captor =
                ArgumentCaptor.forClass(PointsGranted.class);
        verify(publisher).publishEvent(captor.capture());
        PointsGranted child = captor.getValue();

        assertThat(child.correlationId()).isEqualTo(correlationId);
        assertThat(child.causationId()).isEqualTo(parentEventId);
        assertThat(child.eventId()).isNotEqualTo(parentEventId);
        assertThat(child.orderId()).isEqualTo(parent.orderId());
    }
}
~~~

Test trên gọi trực tiếp method listener để kiểm tra **metadata propagation**, không khởi chạy Spring async hoặc transaction. Các lớp event và `OrderPaidListener` là kiểu minh họa đã định nghĩa trong bài. Để kiểm tra việc transaction commit, Event Publication Registry, retries và giải phóng thread, cần integration test chạy Spring context cùng persistence backend thật hoặc database kiểm thử tương thích.

### 9.2. Những tình huống thường bị bỏ sót

1. **Thiếu correlation ID:** publisher không được phát event thiếu correlation theo hợp đồng; hãy xác nhận validation tại boundary và constructor.
2. **Phát lại event:** cùng payload logic cần giữ `eventId`, `correlationId`; chỉ ghi nhận attempt/time xử lý ở metadata riêng.
3. **Event con mới:** ID mới, correlation giữ nguyên, causation trỏ đúng event cha.
4. **Listener chạy bất đồng bộ:** không dựa vào MDC của HTTP thread để suy ra correlation.
5. **Rollback:** sự kiện sau commit không được coi là hoàn tất nếu transaction gốc rollback.
6. **Nhiều listener:** mỗi consumer xử lý idempotent, cùng correlation nhưng có publication record riêng nếu registry hỗ trợ.
7. **Triển khai phiên bản mới:** event cũ lưu bền vẫn phải deserialize được correlation/causation theo quy ước đã chọn.

## 10. Các sai lầm thường gặp

**Tạo ID tại từng listener.** Cách này làm đứt chuỗi nguyên nhân. Hãy khởi tạo ở boundary của workflow, sau đó chuyển nguyên qua event.

**Lấy `UUID.randomUUID()` làm `correlationId` cho mọi event mới.** Điều này tạo một định danh khác cho mỗi event và mất giá trị correlation. `UUID.randomUUID()` nên dùng cho `eventId` của event mới; `correlationId` nhận từ parent.

**Dùng `orderId` làm correlation ID cho mọi quy trình.** Các workflow đặt đơn, thanh toán, hoàn tiền trên cùng một đơn bị nhập chung thành một luồng rất khó phân tích.

**Dùng correlation ID để deduplicate.** Một quy trình chứa nhiều event hợp lệ. Phải dựa trên `eventId` hoặc khóa nghiệp vụ gắn với tác động cần bảo vệ.

**Chỉ dựa vào `MDC` hoặc `ThreadLocal`.** Listener async, job khôi phục và process restart thường mất context ở thread cũ. Hãy mang ID trong dữ liệu event được lưu bền.

**Giả định registry sinh ID nghiệp vụ.** Registry theo dõi publication, không thay bạn định nghĩa hợp đồng event và quan hệ causation.

**Gắn UUID vào metric labels.** Số lượng giá trị ID rất lớn và có thể làm nổ cardinality. Giữ ID trong structured logs/traces, dùng tags hữu hạn cho metrics.

**Tin tưởng ID do bên ngoài cung cấp.** ID chưa được xác thực có thể làm rối truy vết, gây lỗi log injection hoặc đụng ID; cần validation và phân biệt nguồn nội bộ với nguồn ngoài.

## 11. Bài thực hành

Thiết kế một luồng `orders → loyalty → notifications` sử dụng Spring Modulith application events. Một lần ghi nhận thanh toán có correlation ID `C1` và tạo `OrderPaid(E1)`. `loyalty` phát `PointsGranted(E2)`; `notifications` gửi email sau khi nhận event.

Yêu cầu:

1. Đặt `correlationId`, `eventId`, `causationId` trong hai public event. Làm rõ trường nào được kế thừa, trường nào được sinh mới.
2. Sửa publisher để nhận correlation ID từ boundary và đặt `causationId = null` cho event gốc.
3. Sửa listener `loyalty` để dùng `@ApplicationModuleListener`, cộng điểm idempotent và phát event con mang cùng correlation ID.
4. Ghi log có `correlationId`, `eventId` và `causationId` khi `notifications` nhận event; bảo đảm MDC được khôi phục hoặc dọn sạch khi kết thúc.
5. Thử làm listener lỗi sau khi đã commit đơn, sau đó phục hồi publication. Kiểm tra correlation ID và event ID vẫn giữ nguyên trong lần phát lại, và sổ điểm không bị cộng hai lần.
6. Thử một thao tác hoàn tiền mới cho **cùng `orderId`**: quyết định khi nào dùng correlation ID mới, và giải thích khác biệt giữa workflow ID và business key.

**Câu hỏi tự kiểm tra:**

- Vì sao `PointsGranted` cần `eventId` khác với `OrderPaid` nhưng có cùng `correlationId`?
- Nếu cùng event được retry trong một thread khác, vì sao không thể chỉ dùng MDC của request đầu tiên?
- Nếu `OrderPaid` được phát đến hai listener độc lập, nên dùng correlation ID hay event ID để phân biệt hai event con?
- Event Publication Registry giúp phục hồi tác vụ nào, và phần nào vẫn do business listener phải xử lý?

## 12. Tổng kết kỹ thuật

Một **correlation identifier** có giá trị khi tất cả module tham gia cùng một quy trình **chủ động giữ nguyên nó trong metadata của event**. `eventId` xác định từng event riêng; `causationId` mô tả event gây ra event tiếp theo; business key xác định thực thể nghiệp vụ; còn `traceId` phản ánh ngữ cảnh tracing kỹ thuật. Phân biệt đúng các định danh giúp cả thiết kế API lẫn hoạt động giám sát đáng tin cậy.

Với Spring Modulith, kết hợp event bất biến, `@ApplicationModuleListener` sau commit, Event Publication Registry được cấu hình bền vững, listener idempotent và structured logs để lần theo một quy trình qua nhiều transaction, lỗi và retry. **Correlation ID giúp tìm và hiểu điều đã xảy ra; giao nhận tin cậy và tính đúng đắn vẫn do transaction, registry, retry có kiểm soát và quy tắc nghiệp vụ đảm bảo.**

**Đọc thêm (tài liệu chính thức):**

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [Spring Modulith — Application Module Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Framework — Application Events and Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [W3C Trace Context — Traceparent](https://www.w3.org/TR/trace-context/)
