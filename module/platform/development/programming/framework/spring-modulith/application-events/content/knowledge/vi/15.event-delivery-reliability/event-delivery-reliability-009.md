# Bằng chứng xử lý sự kiện trong Spring Modulith

## 1. Vấn đề: “đã phát event” không đồng nghĩa “đã xử lý xong”

Trong Spring Modulith, module **Orders** có thể phát `OrderConfirmed`, còn **Notifications**, **Inventory** và **Reporting** phản ứng mà không cần Orders gọi trực tiếp từng service. Mô hình này giảm phụ thuộc giữa các module và bảo vệ ranh giới nghiệp vụ. Tuy nhiên, nó dẫn tới một câu hỏi vận hành quan trọng:

> Khi hệ thống thông báo “event đã xử lý”, **bằng chứng nào** chứng minh điều đó, cho **consumer nào**, và đã hoàn thành **bước nào**?

Giả sử Orders đã commit nhưng Notifications bị timeout. Log của publisher vẫn có dòng “Published OrderConfirmed”, còn khách hàng chưa nhận email. Nếu coi log này là bằng chứng gửi email thành công, hệ thống đang đánh đồng các mốc nghiệp vụ khác nhau.

Trong chương **Đảm bảo tin cậy** của `SPRING_MODULITH_APPLICATION_EVENTS`, **bằng chứng xử lý** (*processing evidence*) là thông tin có thể kiểm chứng, gắn với định danh event và consumer, dùng để xác định **trạng thái xử lý nào đã thực sự đạt được**. Chứng cứ có thể là một bản ghi publication, một receipt lưu trong transaction của consumer, một notification job đã commit, hoặc xác nhận từ hệ thống bên ngoài. Mỗi loại chứng cứ chỉ khẳng định được phạm vi của chính nó.

Bài học này tập trung thiết kế, lưu trữ, truy vấn, thử lại và kiểm thử bằng chứng xử lý. Các khái niệm publisher/listener, transaction sau commit, Event Publication Registry, retry và idempotency được đặt trong cùng một luồng bằng chứng end-to-end.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt event được tạo, được publish, được ghi nhận, được xử lý bởi listener và đã gây side effect.
- Mô tả phạm vi bằng chứng do Spring Modulith Event Publication Registry cung cấp.
- Thiết kế một **processing receipt** bền vững gắn với `eventId` và `consumerId`.
- Ghi receipt và thay đổi state của consumer **cùng transaction** để tránh bằng chứng giả.
- Xử lý redelivery, crash, transaction rollback, processing trùng và trạng thái không rõ.
- Phân biệt bằng chứng đã lên lịch email, provider đã nhận yêu cầu và email thật sự được chuyển phát.
- Xây dựng truy vấn đối soát, metrics và test kiểm chứng toàn bộ chuỗi xử lý.

## 2. Bốn câu hỏi khác nhau về một event

Ví dụ một `OrderConfirmed` có thể trải qua nhiều điểm:

~~~mermaid
flowchart LR
    A["Orders xác nhận đơn"] --> B["Transaction Orders commit"]
    B --> C["Publication được theo dõi"]
    C --> D["Notifications listener bắt đầu"]
    D --> E["Notification job commit"]
    E --> F["Email provider chấp nhận"]
    F --> G["Provider báo delivered"]
~~~

Mỗi điểm trả lời một câu hỏi khác nhau:

| Điểm kiểm chứng | Ta có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| `publishEvent(...)` được gọi | Publisher đã yêu cầu phát event trong Spring context | Transaction đã commit hay listener xử lý xong |
| State Orders đã commit | Đơn đã được xác nhận bền vững theo Orders | Notifications đã nhận hoặc gửi email |
| Publication đã được registry lưu | Có bản ghi cần giao cho một listener cụ thể, khi backend phù hợp được cấu hình | Listener đã thực hiện side effect |
| Listener bắt đầu chạy | Có một processing attempt | Attempt đó đã commit thành công |
| Receipt và notification job đã commit trong Notifications | Consumer đã ghi nhận và lên lịch công việc theo đúng transaction | Email đã rời khỏi hệ thống |
| Email provider trả ACK thành công | Provider đã chấp nhận yêu cầu theo contract của provider | Người nhận đã nhận thư ở hộp thư |
| Provider xác nhận delivered | Provider báo trạng thái delivered theo định nghĩa của họ | Người nhận đã đọc thư hoặc nghiệp vụ hoàn thành ngoài hệ thống |

Vì vậy, câu **“event đã xử lý”** nên được viết thành phát biểu cụ thể hơn, ví dụ:

- “Publication cho `Notifications` được đánh dấu completed.”
- “Notifications đã commit notification job có `sourceEventId=E1`.”
- “Provider đã chấp nhận email job `J1`.”
- “Provider phát delivery callback `delivered` cho message `M1`.”

Không thay thế những câu này bằng một cờ `processed=true` dùng cho mọi tầng.

## 3. Phân biệt business evidence, delivery evidence và observability

Bằng chứng xử lý có nhiều nguồn và độ tin cậy khác nhau.

| Loại | Ví dụ | Được dùng để làm gì? |
| --- | --- | --- |
| **Business state evidence** | `orders.status=CONFIRMED` đã commit | Xác minh sự thật nguồn |
| **Publication evidence** | Bản ghi publication trong registry | Biết listener nào đang có công việc cần xử lý |
| **Processing attempt evidence** | Log có `attemptId` và timestamp bắt đầu | Điều tra thời điểm bắt đầu, thread, exception |
| **Consumer transaction evidence** | Receipt + notification job đã commit | Chứng minh thay đổi state nội bộ của consumer đã lưu bền |
| **External acknowledgement** | Provider message ID và ACK | Xác minh phía ngoài đã nhận thao tác theo contract |
| **Business outcome evidence** | Hệ thống vận chuyển xác nhận giao hàng | Xác minh mốc cuối cùng theo quy định nghiệp vụ |

**Log, trace và metric rất có ích để điều tra, nhưng không mặc nhiên là chứng cứ bền vững.** Log có thể bị mất khi crash, được ghi trước commit, bị sampling, hoặc không phản ánh side effect cuối cùng. Ngược lại, receipt DB cũng không tự chứng minh provider đã xử lý nếu nó chỉ lưu ý định gọi provider.

Một hệ thống tốt dùng **log/trace để quan sát** và **state/receipt bền vững để chứng minh mốc nghiệp vụ**.

## 4. Định danh cần thiết để gắn bằng chứng đúng đối tượng

Một sự kiện có thể có nhiều consumer; mỗi consumer cũng có thể nhận lại cùng event qua retry. Vì vậy phải tách các định danh.

| Trường | Ý nghĩa | Quy tắc gợi ý |
| --- | --- | --- |
| `eventId` | Một lần xảy ra domain event | Bất biến qua các lần redelivery của cùng event |
| `eventType` | Loại event, ví dụ `OrderConfirmed` | Ổn định về ngữ nghĩa |
| `aggregateId` | Aggregate tạo ra event, ví dụ `orderId` | Dùng correlation/ordering khi phù hợp |
| `aggregateVersion` | Phiên bản aggregate tại mốc phát | Có ích nếu cần phát hiện event đến muộn |
| `consumerId` | Định danh logic listener/handler | Không dùng tên thread hoặc pod làm định danh |
| `publicationId` | Định danh một bản ghi publication, nếu có | Có thể khác `eventId` và khác giữa các consumer |
| `attemptId` | Một lần thử xử lý | Mỗi retry có thể có attemptId mới |
| `correlationId` | Liên kết nhiều hoạt động trong cùng workflow | Có thể dùng trong tracing/log |
| `externalMessageId` | Mã phía provider/broker trả về | Chỉ có sau khi được phía ngoài tạo/xác nhận |

Một ví dụ:

~~~text
eventId       = E-101
aggregateId   = Order-42
eventType     = OrderConfirmed

consumerId    = notifications.order-confirmed
publicationId = P-901
attemptId     = A-1  -> timeout

consumerId    = notifications.order-confirmed
publicationId = P-901
attemptId     = A-2  -> completed

consumerId    = reporting.order-confirmed
publicationId = P-902
attemptId     = A-3  -> completed
~~~

Một event có **hai consumer** và hai publication riêng. Không dùng “event E-101 đã completed” làm bằng chứng rằng **mọi** subscriber đều hoàn thành nếu chưa kiểm tra từng consumer.

### Không đổi eventId khi giao lại

Nếu một publication chưa hoàn thành được phát lại, nó vẫn đại diện cho **cùng business event**. Đổi `eventId` ở mỗi retry sẽ làm mất khả năng deduplicate ổn định.

Ngược lại, hai lần xác nhận nghiệp vụ khác nhau (nếu domain cho phép) không được dùng chung event ID. `attemptId` của kỹ thuật xử lý phải khác `eventId` của sự kiện nghiệp vụ.

## 5. Phạm vi bằng chứng của Event Publication Registry

Spring Modulith cung cấp **Event Publication Registry** để theo dõi publication tới các **transactional event listeners** khi ứng dụng đã cấu hình backend lưu trữ phù hợp. Mục tiêu là lưu dấu những publication cần xử lý và nhận biết các publication còn chưa hoàn tất.

Ở mức khái niệm:

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Orders
    participant DB as Database
    participant R as Publication Registry
    participant N as Notifications Listener
    O->>DB: Begin TX T1, cập nhật Order
    O->>R: Ghi nhận publication cần xử lý
    O->>DB: COMMIT T1
    R-->>N: Dispatch sau commit
    N->>N: Thực hiện công việc theo T2
    alt Listener hoàn thành theo semantics registry
        N-->>R: Đánh dấu publication completed
    else Listener lỗi hoặc crash
        Note over R: Publication chưa hoàn thành
        R-->>N: Resubmit/retry nếu được cấu hình
    end
~~~

Bản ghi publication có thể cho biết một listener đích đã được đăng ký để xử lý một sự kiện, và trạng thái completion theo cơ chế của registry.

**Giới hạn rất quan trọng:**

1. Registry không tự là kho lưu toàn bộ domain events để replay lịch sử vô hạn.
2. Một publication completed biểu thị **xử lý hoàn tất theo tiêu chí của listener/registry**, không tự chứng minh toàn bộ tác động bên ngoài đã xảy ra.
3. Khi listener **ghi một job PENDING rồi trả về thành công**, registry có thể đánh dấu publication completed; email worker vẫn chưa gửi email.
4. Khi listener **bắt exception rồi nuốt lỗi**, registry có thể quan sát lời gọi như thành công dù nghiệp vụ chưa xong. Vì vậy không nuốt exception không được xử lý.
5. Nếu process crash ở khoảng sau khi consumer commit nhưng trước khi registry ghi completion, cùng publication có thể được giao lại.
6. Registry không tự cung cấp exactly-once cho database consumer, broker, email hoặc HTTP API.
7. Việc tự động resubmission, lựa chọn pending/failed publication, lịch retry và backend cụ thể tùy **phiên bản Spring Modulith cùng cấu hình ứng dụng**.

**Bằng chứng tốt:** dùng registry cho **publication delivery**, còn dùng receipt/state của consumer cho **business processing**.

## 6. Hợp đồng event minh họa: OrderConfirmed

Module Orders định nghĩa một event công khai:

~~~java
package com.acme.shop.orders;

import java.time.Instant;
import java.util.UUID;

public record OrderConfirmed(
        UUID eventId,
        UUID orderId,
        Instant occurredAt
) {}
~~~

Ba trường có trách nhiệm riêng:

- `eventId`: định danh duy nhất của lần xác nhận và không đổi khi replay đúng sự kiện.
- `orderId`: liên kết với aggregate Order.
- `occurredAt`: thời điểm publisher ghi nhận biến cố, không phải thời điểm listener hoàn thành.

Đừng gửi entity JPA, transaction object hoặc service bean trong event. Payload nên gồm dữ liệu bất biến cần thiết; nếu consumer cần snapshot số tiền/trạng thái tại lúc event xảy ra, cần định nghĩa field rõ ràng thay vì lấy nhầm giá trị hiện hành khi retry muộn.

Publisher:

~~~java
package com.acme.shop.orders.internal;

import com.acme.shop.orders.OrderConfirmed;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;
    private final Clock clock;

    public OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher publisher,
            Clock clock
    ) {
        this.orders = orders;
        this.publisher = publisher;
        this.clock = clock;
    }

    @Transactional
    public void confirm(UUID orderId) {
        Order order = orders.findById(orderId).orElseThrow();

        if (order.isConfirmed()) {
            return;
        }

        order.confirm();
        orders.save(order);

        publisher.publishEvent(new OrderConfirmed(
                UUID.randomUUID(), orderId, Instant.now(clock)
        ));
    }
}
~~~

Ví dụ giả định có `Order`, `OrderRepository` và bean `Clock`, chưa bao gồm toàn bộ handling đồng thời. Nếu hai request cùng xác nhận một đơn, cần optimistic locking/constraint hoặc cơ chế domain thích hợp để không tạo hai business events sai.

**Quan trọng:** `publishEvent(...)` được gọi trong T1. Nó không tự chứng minh T1 đã commit; listener sau commit chỉ phản ứng khi T1 commit thành công. Bằng chứng nguồn nên dựa vào state đã commit và publication storage phù hợp, không phải chỉ một log ở vị trí publish.

## 7. Định nghĩa “consumer đã xử lý” trước khi lưu receipt

Mỗi consumer cần định nghĩa **điểm hoàn thành** của mình. Ví dụ, Notifications có hai việc:

1. Khi nhận `OrderConfirmed`: **tạo một notification job** bền vững.
2. Sau đó một worker gửi email qua provider và cập nhật trạng thái job.

Hai mốc có ý nghĩa khác nhau:

| Bằng chứng | Ý nghĩa |
| --- | --- |
| `NOTIFICATION_SCHEDULED` | Consumer đã lưu job gửi email một cách bền vững |
| `PROVIDER_ACCEPTED` | Nhà cung cấp email đã xác nhận nhận yêu cầu |
| `DELIVERY_REPORTED` | Provider có callback/trạng thái phát thư theo contract |
| `CUSTOMER_READ` | Chỉ có nếu hệ thống thật sự có tín hiệu đáng tin cậy; không suy ra từ trạng thái trên |

Nên đặt tên receipt theo công việc listener thực sự thực hiện, ví dụ `ORDER_CONFIRMATION_JOB_SCHEDULED`, thay vì đặt `EMAIL_SENT` khi mới ghi job.

Đối với Reporting, điểm hoàn thành có thể là “projection cập nhật và commit”. Đối với Inventory, có thể là “reservation được ghi nhận”. **Không tồn tại một định nghĩa processing-completed chung** phù hợp cho mọi module.

### Bằng chứng là một lời khẳng định có điều kiện

Một receipt chỉ đáng tin khi:

- Được ghi sau hoặc trong cùng transaction với trạng thái nó khẳng định.
- Có định danh event/consumer để truy hồi.
- Có ràng buộc chống ghi trùng.
- Không được đánh dấu thành công trước khi công việc cần chứng minh thực sự bền vững.
- Có cách phát hiện và khôi phục lỗi/độ lệch trong vận hành.

## 8. Mẫu lưu dữ liệu: receipt và processing attempts

Ví dụ dùng PostgreSQL cho một consumer Notifications:

~~~sql
CREATE TABLE event_processing_receipt (
    event_id          UUID NOT NULL,
    consumer_id       VARCHAR(160) NOT NULL,
    event_type        VARCHAR(160) NOT NULL,
    aggregate_id      UUID NOT NULL,
    result_code       VARCHAR(80) NOT NULL,
    applied_at        TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (event_id, consumer_id)
);

CREATE TABLE event_processing_attempt (
    attempt_id        UUID PRIMARY KEY,
    event_id          UUID NOT NULL,
    consumer_id       VARCHAR(160) NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ,
    outcome           VARCHAR(32) NOT NULL,
    error_category    VARCHAR(80)
);

CREATE TABLE notification_job (
    job_id            UUID PRIMARY KEY,
    source_event_id   UUID NOT NULL UNIQUE,
    order_id          UUID NOT NULL,
    status            VARCHAR(32) NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL
);
~~~

Đây là **schema đề xuất để minh họa**, không phải tên bảng/cột mặc định của Spring Modulith. `event_processing_receipt` là dữ liệu của consumer; publication registry dùng mô hình lưu trữ riêng theo backend/version.

Hai dạng chứng cứ:

- **Receipt chính thức:** duy nhất theo cặp `(event_id, consumer_id)`, mô tả mốc nghiệp vụ đã bền vững. Khi nhận trùng, không tạo thêm receipt tương đương.
- **Attempt history:** có thể có nhiều dòng cho cùng event/consumer vì lỗi, retry và restart. Attempt log phục vụ chẩn đoán; một attempt `STARTED` **không phải** bằng chứng hoàn thành.

### Vì sao không dùng một cờ `processed`?

Vì không thể hiện **ai xử lý**, xử lý **việc gì**, có **commit** chưa, và phần việc bên ngoài còn tiếp diễn hay không. Một trường `result_code` có ngữ nghĩa cụ thể như `JOB_SCHEDULED` hoặc `PROJECTION_APPLIED` dễ kiểm chứng hơn.

Nếu cần nhiều giai đoạn xử lý của cùng consumer, có thể dùng các receipt cho **các bước nghiệp vụ** với khóa riêng hoặc dùng state machine của job. Không cố nhét tất cả mốc vào một boolean.

## 9. Ghi receipt và thay đổi nghiệp vụ trong cùng transaction

Đây là quy tắc cốt lõi.

Sai lầm thường thấy:

~~~text
INSERT processed(eventId) -> COMMIT
Tạo notification job -> lỗi
Retry event -> thấy processed(eventId) -> bỏ qua
Kết quả: có receipt nhưng không có job
~~~

Để tránh, hãy ghi receipt và job trong **cùng transaction T2** của Notifications:

~~~mermaid
flowchart LR
    A["Listener nhận OrderConfirmed"] --> B["BEGIN T2"]
    B --> C["Ghi receipt/idempotency key"]
    C --> D["Tạo notification job"]
    D --> E{"T2 commit?"}
    E -->|"Có"| F["Receipt + job đều bền vững"]
    E -->|"Không"| G["Cả receipt và job rollback"]
~~~

Với PostgreSQL, có thể dùng một insert có unique constraint làm hàng rào idempotency. Một phương thức minh họa dùng `JdbcTemplate`:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import java.sql.Timestamp;
import java.time.Clock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NotificationSchedulingService {

    private static final String CONSUMER =
            "notifications.order-confirmed";

    private final JdbcTemplate jdbc;
    private final Clock clock;

    public NotificationSchedulingService(JdbcTemplate jdbc, Clock clock) {
        this.jdbc = jdbc;
        this.clock = clock;
    }

    @Transactional
    public void scheduleIfAbsent(OrderConfirmed event) {
        Instant now = clock.instant();

        int inserted = jdbc.update("""
                INSERT INTO event_processing_receipt
                    (event_id, consumer_id, event_type, aggregate_id,
                     result_code, applied_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (event_id, consumer_id) DO NOTHING
                """,
                event.eventId(),
                CONSUMER,
                "OrderConfirmed",
                event.orderId(),
                "JOB_SCHEDULED",
                Timestamp.from(now));

        if (inserted == 0) {
            // Một receipt đã commit cho cùng event/consumer.
            // Trong production cần đối chiếu event_type/aggregate_id/result.
            return;
        }

        jdbc.update("""
                INSERT INTO notification_job
                    (job_id, source_event_id, order_id, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                UUID.randomUUID(),
                event.eventId(),
                event.orderId(),
                "PENDING",
                Timestamp.from(now));
    }
}
~~~

**Điều kiện quan trọng của ví dụ:** cả hai câu SQL được thực thi trong cùng transaction DB T2; `JdbcTemplate` tham gia transaction Spring phù hợp; schema và types tương ứng đã tồn tại. Cú pháp `ON CONFLICT` là PostgreSQL-specific, không áp dụng nguyên xi cho mọi database.

Nếu bước tạo job lỗi, T2 rollback **cả receipt**. Khi retry, consumer có thể thử lại thay vì bị một receipt giả làm bỏ qua.

Nếu receipt đã tồn tại và `inserted==0`, production nên kiểm tra receipt có đúng `eventType`, `aggregateId`, `resultCode` không. Trùng `eventId` nhưng payload khác là **xung đột contract**, không nên âm thầm bỏ qua như duplicate hợp lệ. Cũng cần đối soát receipt/job nếu có dữ liệu bị sửa thủ công hoặc migrat​ion lỗi.

### Tại sao không chỉ dùng `existsByEventId` trước khi ghi?

Hai worker đồng thời có thể cùng đọc “chưa tồn tại”, rồi cùng tạo job. **Unique constraint** mới là hàng rào cuối cùng. Với PostgreSQL, `INSERT ... ON CONFLICT DO NOTHING` giúp xử lý duplicate trong cùng transaction mà không phải bắt một unique violation giữa transaction đã bị đánh dấu rollback.

## 10. Listener Spring Modulith kết hợp transaction riêng

Một listener thuộc Notifications:

~~~java
package com.acme.shop.notifications.internal;

import com.acme.shop.orders.OrderConfirmed;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConfirmedListener {

    private final NotificationSchedulingService service;

    public OrderConfirmedListener(NotificationSchedulingService service) {
        this.service = service;
    }

    @ApplicationModuleListener
    public void on(OrderConfirmed event) {
        service.scheduleIfAbsent(event);
    }
}
~~~

`@ApplicationModuleListener` kết hợp listener **sau commit**, `@Async` và transaction xử lý mới theo `REQUIRES_NEW`. Vì vậy:

- T1 của Orders commit trước khi listener xử lý.
- T2 của Notifications chịu trách nhiệm receipt và job.
- `@Transactional` trên `NotificationSchedulingService` với propagation mặc định `REQUIRED` sẽ tham gia T2 nếu transaction đang hoạt động theo cấu hình.
- Nếu T2 rollback, exception phải được bộc lộ phù hợp để publication không bị coi là completed.
- Nếu T2 commit và listener hoàn thành, registry có thể đánh dấu publication completed theo semantics của mình.

Chỉ gọi `service.scheduleIfAbsent` trả về **không chứng minh email đã gửi**. Nó chỉ chứng minh việc lên lịch đã được transaction xử lý như định nghĩa listener.

### Cạm bẫy nuốt lỗi

~~~java
@ApplicationModuleListener
public void on(OrderConfirmed event) {
    try {
        service.scheduleIfAbsent(event);
    } catch (Exception ex) {
        log.warn("Scheduling failed", ex);
        // Sai nếu kết thúc method bình thường và coi như đã xử lý.
    }
}
~~~

Khi lỗi nhưng method trả về bình thường, hạ tầng có thể coi callback thành công và đánh dấu publication completed, trong khi receipt/job không có. Hãy phân biệt:

- Lỗi thật sự cần retry: để lỗi được hạ tầng quan sát hoặc lưu trạng thái thất bại theo cơ chế thiết kế.
- Lỗi duplicate đã có receipt/job đúng: xác nhận idempotency rồi kết thúc bình thường.
- Lỗi contract hoặc dữ liệu không hợp lệ: cần phân loại, alert và xử lý poison publication; không retry vô hạn mù quáng.

## 11. Phân tích crash ở các điểm khác nhau

Giả sử Orders đã commit sự kiện và registry có lưu publication tương ứng.

| Thời điểm crash | Receipt Notifications | Notification job | Publication registry | Hành vi khôi phục |
| --- | --- | --- | --- | --- |
| Trước commit Orders | Không | Không | Publication thuộc T1 không được commit nếu cấu hình atomic | Không coi Order đã xác nhận |
| Sau commit Orders, trước khi listener chạy | Không | Không | Có thể còn pending | Resubmit khi cơ chế recovery được bật |
| T2 đang ghi, chưa commit | Rollback cùng T2 | Rollback cùng T2 | Chưa completed | Retry tạo lại cả receipt/job |
| T2 đã commit, trước khi registry đánh dấu completed | Có | Có | Có thể vẫn pending | Retry gặp receipt, xác nhận duplicate và không tạo job thứ hai |
| Registry đã completed, worker email chưa chạy | Có | `PENDING` | Completed | Email worker tiếp tục từ job DB |
| Provider đã nhận email, ứng dụng mất ACK | Có | Có thể vẫn `SENDING` | Publication có thể đã completed | Cần provider idempotency, status query hoặc reconciliation |

Hình thức lưu publication/đánh dấu completion tùy backend và phiên bản Spring Modulith; bảng mô tả các ranh giới và hành vi mong muốn, **không phải lời hứa rằng retry tự động được bật trong mọi cấu hình**.

### Hai transaction không atomic với nhau

T1 của Orders và T2 của Notifications là các transaction riêng. Không thể dùng T2 rollback để đảo T1 đã commit. Khi consumer lỗi, state giữa các module có thể tạm không nhất quán; cần **eventual consistency có thể quan sát và hồi phục**.

## 12. Bằng chứng hoàn tất của registry khác receipt của consumer

Hãy xét hai trạng thái:

~~~text
Registry:
  OrderConfirmed(E1) -> notifications.order-confirmed = COMPLETED

Notifications DB:
  event_processing_receipt(E1, notifications.order-confirmed) = JOB_SCHEDULED
  notification_job(source_event_id=E1) = PENDING
~~~

Cả ba điều trên có thể đồng thời đúng. Nhưng khách hàng **chưa chắc nhận được email**.

Nếu dashboard chỉ nhìn trạng thái registry COMPLETED rồi hiển thị “Email đã gửi”, dashboard đang công bố sai sự thật.

Ngược lại, có thể xảy ra:

~~~text
Registry:
  OrderConfirmed(E1) -> notifications.order-confirmed = INCOMPLETE

Notifications DB:
  receipt(E1) = JOB_SCHEDULED
  notification_job(E1) = PENDING
~~~

Điều này có thể xảy ra nếu T2 đã commit nhưng process chết trước khi publication được đánh dấu completed. **Hai nguồn bằng chứng không nhất thiết mâu thuẫn**: chúng nói về hai mốc khác nhau. Lần retry có thể dùng receipt để nhận diện công việc đã hoàn thành và cho phép registry chuyển publication sang completed.

### Quy tắc đối soát

Đừng tự xóa receipt khi registry còn pending. Đừng tự đánh dấu registry completed chỉ vì thấy log. Hãy có quy trình đối chiếu:

1. Xác định event ID và consumer ID.
2. Kiểm tra bản ghi publication và trạng thái.
3. Kiểm tra receipt DB, business row và thời điểm commit.
4. Nếu receipt/side effect đã bền vững, cho cơ chế xử lý lại hoàn tất idempotent.
5. Nếu chưa có receipt, chẩn đoán lỗi rồi retry có giới hạn.
6. Nếu dữ liệu xung đột, cô lập và điều tra thay vì coi là duplicate bình thường.

## 13. Xử lý event có nhiều consumer

Một event có thể phát tới ba module:

~~~mermaid
flowchart TD
    E["OrderConfirmed E1"] --> N["Notifications"]
    E --> R["Reporting"]
    E --> F["Fulfillment"]
    N --> N1["Receipt: JOB_SCHEDULED"]
    R --> R1["Receipt: PROJECTION_APPLIED"]
    F --> F1["Pending: Inventory service unavailable"]
~~~

Nếu Notifications và Reporting hoàn tất còn Fulfillment lỗi, không nói chung chung “event hoàn thành”.

Một bảng đối soát:

| Event | Consumer | Publication | Business receipt | Kết luận |
| --- | --- | --- | --- | --- |
| E1 | Notifications | COMPLETED | JOB_SCHEDULED | Đã lên lịch notification |
| E1 | Reporting | COMPLETED | PROJECTION_APPLIED | Đã cập nhật projection |
| E1 | Fulfillment | INCOMPLETE | Không có | Cần khôi phục xử lý |
| E1 | Email worker | Không phải cùng listener publication | Provider chưa có ACK | Chưa có bằng chứng provider nhận |

Một hệ thống có thể định nghĩa một **overall workflow status** riêng: hoàn thành khi các consumer bắt buộc đều đạt điều kiện; nhưng đó là một phép tổng hợp nghiệp vụ, không phải trạng thái duy nhất mà Spring event infrastructure tự tạo sẵn.

### Listener định danh ổn định

Khi đổi tên method, class, package hoặc logic listener, cần xem lại cách registry hiện tại nhận dạng publication target. Không đổi tùy tiện khi còn publication chưa hoàn thành. Với receipt riêng, `consumerId` nên là tên logic ổn định như `notifications.order-confirmed`, không phụ thuộc số pod hoặc tên executor thread.

## 14. Bằng chứng cho side effect ngoài database

Sau khi notification job đã commit, một worker gửi email:

~~~text
notification_job: PENDING
         |
         v
Worker gửi email kèm idempotency key
         |
         +--> Provider ACK -> ACCEPTED + providerMessageId
         |
         +--> Timeout / kết quả chưa rõ -> UNKNOWN
                                      -> đối soát / retry theo chính sách
~~~

### Phân biệt bốn trạng thái

| Trạng thái | Chứng cứ tối thiểu |
| --- | --- |
| `PENDING` | Job được lưu trong DB, chưa ghi nhận thao tác ngoài |
| `SENDING` | Worker đã claim job; chưa chứng minh provider nhận |
| `ACCEPTED` | Provider trả ACK phù hợp, có request/provider message ID |
| `DELIVERED` | Provider báo delivered theo contract/callback cụ thể |
| `UNKNOWN` | Đã gửi yêu cầu nhưng không biết provider nhận hay chưa |
| `FAILED` | Có bằng chứng về lỗi theo chính sách (không đánh đồng timeout với từ chối cuối cùng) |

Nếu API gửi email timeout, **không có phản hồi không có nghĩa email chắc chắn chưa được gửi**. Retry vô điều kiện có thể tạo email trùng. Cần:

- Gửi kèm **idempotency key** khi provider hỗ trợ.
- Lưu provider request ID và correlation ID.
- Có API hỏi trạng thái hoặc đối soát nếu provider hỗ trợ.
- Đặt deadline và policy cho trạng thái UNKNOWN.
- Nếu không có cơ chế chống lặp phía ngoài, chấp nhận rủi ro được tài liệu hóa hoặc thiết kế bù trừ phù hợp.

### ACK của broker cũng không phải ACK của business consumer

Với integration events, producer có thể nhận ACK từ broker. Điều đó chỉ khẳng định broker chấp nhận thông điệp theo cấu hình/quorum/durability, **không chứng minh CRM đã cập nhật database**. Bằng chứng consumer hoàn tất vẫn cần từ consumer receipt/state hoặc acknowledgement có contract rõ.

## 15. Ghi nhận processing attempts và lý do retry

Receipt chứng minh một kết quả đã commit. Attempt log giúp giải thích **đã thử bao nhiêu lần, thất bại vì sao và khi nào sẽ thử lại**.

Một attempt có thể có các trạng thái:

~~~text
STARTED
  |
  +--> SUCCEEDED
  |
  +--> FAILED_RETRYABLE
  |
  +--> FAILED_PERMANENT
  |
  +--> UNKNOWN
~~~

Không nên ghi attempt `SUCCEEDED` **trước khi** transaction nghiệp vụ consumer commit. Nếu application crash trước commit, một log “success” có thể là sai bằng chứng.

Nếu cần lưu attempt lỗi khi transaction xử lý rollback, có thể dùng transaction audit riêng hoặc logging/tracing với giới hạn bảo đảm rõ. Việc ghi attempt failure trong T2 rồi rollback T2 sẽ làm mất chính dòng attempt. Nhưng dùng `REQUIRES_NEW` cho attempt audit cũng cần cân nhắc pool connection và chiến lược đối soát crash.

### Retry policy minh họa

| Loại lỗi | Có thể retry? | Hướng xử lý |
| --- | --- | --- |
| Connection timeout tới DB | Thường có, với backoff và giới hạn | Theo dõi pending/failed publication |
| Lỗi khóa đồng thời tạm thời | Có thể | Retry idempotent |
| Duplicate hợp lệ có receipt và job | Không phải lỗi; coi là đã xử lý | Hoàn thành listener bình thường |
| Event schema không hỗ trợ | Không retry vô hạn | Chặn, alert, nâng cấp consumer hoặc migration |
| Mâu thuẫn `eventId` cùng payload khác | Không xử lý như duplicate | Báo vi phạm contract, điều tra |
| Provider email timeout, outcome không rõ | Không khẳng định success/failure | Query status/idempotency/reconciliation |
| Business invariant không còn thỏa | Phụ thuộc chính sách | Kiểm tra phiên bản aggregate và xử lý event đến muộn |

Không tạo một domain event mới như `OrderConfirmedRetry` chỉ vì Publication Registry phát lại cùng `OrderConfirmed`. Lịch sử attempt thuộc hạ tầng processing, không làm thay đổi sự thật nghiệp vụ gốc.

## 16. Event đến trễ, out-of-order và bằng chứng trạng thái hiện tại

Một hệ thống có thể phát:

~~~text
E1, version 7: OrderConfirmed
E2, version 8: OrderCancelled
~~~

Do retry, một consumer có thể nhận E2 trước E1. Cả hai event đều mô tả sự thật lịch sử; nhưng xử lý E1 muộn không được làm projection quay từ CANCELLED về CONFIRMED nếu policy hiện tại không cho phép.

Bằng chứng xử lý có thể ghi:

- Event E1 đã được **xem xét và bỏ qua theo quy tắc version**.
- Event E2 đã được **áp dụng vào projection**.
- Projection hiện tại là CANCELLED tại version 8.

Nếu consumer bỏ qua E1 vì đã lỗi thời, nên dùng result code có ý nghĩa như `STALE_EVENT_IGNORED` và ghi lại tại sao. **Không đồng nhất “đã xử lý event” với “đã cập nhật state theo mọi event”**. Một event đến muộn có thể được xử lý hợp lệ bằng cách **không áp dụng** nó.

Ví dụ state guard:

~~~java
if (event.orderVersion() <= projection.lastAppliedVersion()) {
    receiptStore.recordIfAbsent(
            event.eventId(), "STALE_EVENT_IGNORED"
    );
    return;
}
~~~

Đây là pseudocode: thực tế cần cập nhật projection và receipt dưới transaction/constraint phù hợp; phải xử lý version gap và nhiều loại event nếu domain có ordering phức tạp.

## 17. Đối soát: khi evidence giữa các tầng khác nhau

Một dashboard vận hành nên cung cấp ít nhất ba góc nhìn:

1. **Source truth:** số Orders đã commit sự kiện cần xử lý.
2. **Delivery ledger:** publication nào còn incomplete hoặc thất bại theo listener.
3. **Consumer truth:** receipt nào đã có và state nghiệp vụ consumer ra sao.

Khi các nguồn không khớp, phân loại trước khi sửa:

| Quan sát | Diễn giải khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| Order committed, không thấy publication | Registry chưa cấu hình, event không được chọn, hoặc lỗi ghi publication | Kiểm tra wiring/transaction và event contract |
| Publication incomplete, receipt không có | Listener chưa chạy hoặc transaction consumer rollback | Xem attempt/error và thử lại |
| Publication incomplete, receipt đã có | Consumer commit nhưng marker completion chưa ghi | Replay idempotent và đối soát |
| Publication completed, receipt không có | Listener không ghi receipt, nuốt lỗi, hoặc kiểm tra sai consumer | Xem contract và mức độ bằng chứng thực tế |
| Receipt JOB_SCHEDULED, không có job | Có lỗi data integrity hoặc transaction boundary sai | Điều tra, sửa dữ liệu theo quy trình |
| Receipt có job PENDING quá lâu | Worker email lỗi/queue backlog | Kiểm tra worker, provider và SLA |
| Provider ACK nhưng DB chưa cập nhật | Crash giữa external call và DB update | Đối soát bằng provider ID và idempotency key |

### SQL đối soát minh họa

~~~sql
-- Các receipt Notifications không khớp với job đã được ghi.
SELECT r.event_id, r.consumer_id, r.applied_at
FROM event_processing_receipt r
LEFT JOIN notification_job j
  ON j.source_event_id = r.event_id
WHERE r.consumer_id = 'notifications.order-confirmed'
  AND r.result_code = 'JOB_SCHEDULED'
  AND j.source_event_id IS NULL;
~~~

Truy vấn này chỉ quan sát dữ liệu consumer đã được mô hình hóa trong bài. Để đối chiếu publication registry, cần đọc backend schema/API đúng phiên bản Spring Modulith; **không giả định tên bảng registry giống các bảng minh họa**.

Không tự ý đánh dấu receipt hay publication completed để “làm sạch dashboard” khi chưa đối chiếu state thật.

## 18. Logging, metrics và tracing hỗ trợ chứng cứ

Chứng cứ bền vững và telemetry phục vụ hai mục tiêu bổ sung.

### Log cấu trúc

~~~text
eventId=E1 eventType=OrderConfirmed consumer=notifications.order-confirmed
publication=P1 attempt=A1 phase=STARTED

eventId=E1 consumer=notifications.order-confirmed
receipt=JOB_SCHEDULED jobId=J1 phase=CONSUMER_COMMITTED

eventId=E1 consumer=notifications.order-confirmed
publication=P1 phase=PUBLICATION_COMPLETED

jobId=J1 providerMessageId=M1 phase=PROVIDER_ACCEPTED
~~~

Log nên tách `phase` khỏi `businessStatus`. Một log “SENT” quá sớm làm người vận hành hiểu nhầm.

### Metrics đáng theo dõi

| Metric | Giải thích |
| --- | --- |
| `event_publications_incomplete` | Publication chưa hoàn thành theo backend registry |
| `event_publication_oldest_age_seconds` | Tuổi publication cũ nhất chưa xử lý |
| `event_processing_attempts_total{consumer,outcome}` | Số lần thử, chia theo loại kết quả |
| `event_processing_receipts_total{consumer,result}` | Số receipt đã commit theo result code |
| `event_processing_latency_seconds` | Độ trễ từ thời điểm phát/commit tới receipt |
| `notification_jobs_pending` | Công việc đã lên lịch nhưng chưa hoàn tất |
| `external_provider_unknown_total` | Số yêu cầu không biết kết quả |

Tên trên chỉ là **đề xuất**, không phải metric tự động có sẵn của Spring Modulith. Cần instrument và kiểm chứng trên phiên bản Micrometer/Actuator của ứng dụng.

Không dùng `eventId` hoặc `orderId` làm metric label vì cardinality quá lớn. Dùng các ID này trong log/trace đã được bảo vệ thông tin và có retention hợp lý.

### Trace xuyên transaction

Một event có thể được xử lý trên executor thread khác và sau restart, nên context dạng `ThreadLocal` không tự tồn tại ở mọi lần retry. Định danh quan trọng phải nằm trong event/record bền vững. Trace ID giúp điều tra, nhưng không thay thế khóa `eventId` dùng cho idempotency và truy vấn receipt.

## 19. Giới hạn của bằng chứng: độ tin cậy, kiểm toán và bảo mật

Một receipt DB cho phép hệ thống nội bộ truy vấn “module nào đã làm gì”. Nhưng độ tin cậy của nó phụ thuộc vào quyền ghi, transaction, backup và chính sách vận hành.

Nếu bài toán mang tính kiểm toán hoặc pháp lý, cần xác định mức đảm bảo cao hơn:

- Ai được phép tạo, sửa hoặc xóa receipt?
- Receipt có thể bị một tài khoản vận hành chỉnh sửa mà không lưu dấu không?
- Khi schema thay đổi, lịch sử được migration ra sao?
- Có cần giữ immutable audit log, append-only store, chữ ký số, hash chain hoặc WORM storage không?
- Dữ liệu nào chứa PII và phải được xóa/ẩn danh theo chính sách?
- Giữ bằng chứng trong bao lâu, có thể trích xuất để đối soát không?

**Một bản ghi database bình thường không tự là bằng chứng chống giả mạo.** Nếu cần xác thực độc lập, phải thiết kế cơ chế audit/security, bảo vệ khóa và quy trình quản trị tương ứng.

Tương tự, “provider báo delivered” là bằng chứng theo contract của provider, không chứng minh người dùng đã mở hoặc đọc email.

### Tránh rò rỉ dữ liệu

Không lưu cả access token, password hoặc payload cá nhân nhạy cảm chỉ vì muốn “có bằng chứng đầy đủ”. Một receipt thường chỉ cần ID, loại event, consumer, outcome, timestamp và thông tin liên kết đã tối thiểu hóa.

## 20. Kiểm thử processing evidence

Kiểm thử cần dựa trên **kết quả đã commit**, không chỉ kiểm tra mock listener được gọi.

### 20.1. Test publisher và ranh giới module

Spring Modulith hỗ trợ kiểm tra module boundary:

~~~java
import com.acme.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleBoundaryTest {

    @Test
    void verifyBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test này phát hiện một số vi phạm dependency; nó không chứng minh Notifications đã commit receipt. Cần test riêng publisher phát đúng event và listener xử lý sau commit.

### 20.2. Test commit và rollback

Với `@ApplicationModuleListener` chạy sau commit:

- Khi Orders commit thành công, event phù hợp được dispatch.
- Khi Orders rollback, listener không xử lý như một business fact đã commit.
- Test phải có **transaction thực sự commit**, không để test framework rollback toàn bộ rồi kỳ vọng `AFTER_COMMIT` chạy.
- Với async, cần chờ điều kiện đầu ra trong một khoảng timeout hữu hạn, không dùng `Thread.sleep(1000)` cứng.

Phác thảo với `TransactionTemplate`:

~~~java
@SpringBootTest
class NotificationEvidenceTest {

    @Autowired TransactionTemplate transactions;
    @Autowired ApplicationEventPublisher publisher;
    @Autowired NotificationJobRepository jobs;
    @Autowired ReceiptRepository receipts;

    @Test
    void committedEventCreatesReceiptAndJob() {
        UUID eventId = UUID.randomUUID();
        UUID orderId = UUID.randomUUID();

        transactions.executeWithoutResult(tx ->
                publisher.publishEvent(
                        new OrderConfirmed(eventId, orderId, Instant.now())
                )
        );

        await().atMost(Duration.ofSeconds(5)).untilAsserted(() -> {
            assertThat(receipts.existsByEventIdAndConsumerId(
                    eventId, "notifications.order-confirmed"
            )).isTrue();
            assertThat(jobs.existsBySourceEventId(eventId)).isTrue();
        });
    }
}
~~~

Đây là ví dụ tích hợp có các class/repository/import giả định, chưa phải test runnable độc lập. `await()` minh họa kiểu chờ điều kiện bằng Awaitility. Với test thực, dùng backend database và transaction manager phù hợp.

### 20.3. Ma trận test bắt buộc

| Tình huống | Kỳ vọng về bằng chứng |
| --- | --- |
| Orders rollback | Không có receipt `JOB_SCHEDULED` cho event chưa commit |
| T2 tạo receipt rồi lỗi khi tạo job | Receipt và job đều rollback |
| T2 commit cả receipt + job | Hai bản ghi cùng tồn tại |
| Hai invocation đồng thời cho cùng `eventId` | Unique constraint chỉ cho một receipt/job hợp lệ |
| Crash sau T2 commit nhưng trước publication completion | Registry có thể incomplete, nhưng retry không tạo job thứ hai |
| Listener nhận duplicate có cùng payload | Xử lý idempotent và hoàn thành bình thường |
| Duplicate `eventId` nhưng payload khác | Phát hiện conflict, không âm thầm bỏ |
| Event phiên bản cũ đến muộn | Receipt phản ánh `STALE_EVENT_IGNORED` nếu policy cho phép |
| Provider timeout sau khi nhận yêu cầu | Không đánh dấu `DELIVERED` khi outcome còn UNKNOWN |
| Registry completed nhưng job vẫn PENDING | Dashboard hiển thị hai trạng thái tách biệt |
| Consumer mới được thêm sau khi event xảy ra | Không giả định registry tự replay lịch sử cho subscriber mới |

### 20.4. Failure injection và crash test

Một unit test không thể chứng minh khả năng khôi phục sau JVM crash. Đối với tính bền vững, cần integration test với backend registry:

1. Đảm bảo event nguồn và publication được commit.
2. Mô phỏng lỗi/stop khi consumer chưa xử lý.
3. Khởi động lại và kích hoạt cơ chế resubmission được cấu hình.
4. Xác minh receipt/job được tạo đúng một lần.
5. Mô phỏng crash **sau T2 commit nhưng trước registry completion**.
6. Kiểm tra redelivery nhận diện receipt cũ, không tạo side effect trùng.
7. Kiểm tra publication cuối cùng có thể được đánh dấu hoàn thành theo cơ chế framework.

Không chạy phá hoại database production để thử. Sử dụng môi trường integration test, dữ liệu cô lập và rollback/cleanup chuẩn bị trước.

## 21. Bài tập thực hành

### Bài 1 — Xây chuỗi bằng chứng

Với một event `OrderConfirmed(E1)`, hãy lập bảng bằng chứng cho Orders commit, publication tới Notifications, T2 ghi job, email provider ACK và delivery callback. Với mỗi dòng, nêu rõ **đã chứng minh điều gì và chưa chứng minh điều gì**.

### Bài 2 — Sửa anti-pattern receipt ghi trước

Một developer ghi `processed_events(E1)` và commit, rồi gọi API tạo shipment. Nếu tạo shipment lỗi, lần retry thấy event đã processed và bỏ qua. Hãy sửa transaction boundary hoặc thiết kế durable job/outbox để receipt không nói quá kết quả.

### Bài 3 — Hai consumer, một event

`OrderPaid` được Loyalty và Reporting xử lý. Loyalty commit thành công, Reporting timeout. Hãy xây một bảng theo `(eventId, consumerId)` và xác định vì sao `eventId` đơn lẻ không đủ để diễn đạt toàn bộ processing outcome.

### Bài 4 — Redelivery và idempotency

T2 đã commit notification job, nhưng crash trước khi Registry completed. Vẽ sequence diagram và viết pseudocode xử lý lại theo `eventId` để chỉ có một job.

### Bài 5 — Provider trả UNKNOWN

Email worker gọi provider rồi timeout. Thiết kế trạng thái job và bằng chứng cần lưu. Nêu khi nào được đánh dấu ACCEPTED, khi nào phải query provider, và vì sao không tự động ghi DELIVERED.

### Bài 6 — Đối soát và SLA

Cho hệ thống có 5.000 publication incomplete, trong đó một phần đã có receipt nhưng registry chưa completed, phần còn lại chưa có receipt. Đề xuất thứ tự kiểm tra, cách phân loại retryable/permanent, alert theo tuổi publication và tiêu chí kết luận đã hồi phục.

## 22. Checklist trước khi đưa processing evidence vào production

- [ ] Định nghĩa rõ “đã xử lý” ở mức publication, consumer transaction và external side effect.
- [ ] Mọi event có `eventId` ổn định qua retry.
- [ ] Phân biệt `consumerId`, `publicationId`, `attemptId` và `aggregateId`.
- [ ] Receipt chứa result code có ngữ nghĩa cụ thể, không chỉ một cờ `processed=true`.
- [ ] Receipt và state nghiệp vụ được ghi **trong cùng transaction** khi chúng chứng minh cùng một mốc.
- [ ] Có unique constraint/idempotency cho `(eventId, consumerId)` hoặc business key thích hợp.
- [ ] Duplicate có cùng nội dung được xử lý an toàn; duplicate ID với payload khác phải được phát hiện.
- [ ] Listener không nuốt exception khiến publication được đánh dấu completed sai.
- [ ] Event Publication Registry có backend, recovery/resubmission và quan sát phù hợp phiên bản.
- [ ] Trạng thái registry không được nhầm với trạng thái email/provider hoặc tác vụ ngoài DB.
- [ ] Có policy rõ cho retry, poison events, UNKNOWN, timeout và reconciliation.
- [ ] Xử lý event đến muộn có version guard hoặc business rule rõ.
- [ ] Có metrics, log/tracing theo ID, cảnh báo tuổi publication và chênh lệch dữ liệu.
- [ ] Test commit, rollback, concurrent duplicate, crash trước/sau commit, provider outcome không rõ.
- [ ] Receipt được bảo vệ quyền ghi, retention, backup và dữ liệu nhạy cảm.
- [ ] Có quy trình đối soát thủ công/tự động, không “xóa lỗi” bằng cách gắn completed vô căn cứ.

## 23. Tổng kết

**Bằng chứng xử lý** không chỉ là log “đã publish”. Nó là một chuỗi phát biểu có thể kiểm chứng: nghiệp vụ nguồn đã commit, publication đã được theo dõi, listener đã xử lý, consumer state đã commit và side effect ngoài hệ thống đã đạt một mốc được định nghĩa rõ.

Trong Spring Modulith, **Event Publication Registry** giúp quản lý publication tới transactional listener với backend phù hợp, hỗ trợ xác định công việc chưa hoàn thành và recovery. Nó không tự chứng minh một email đã delivered hoặc một API bên ngoài đã hoàn tất. Để chứng minh công việc của consumer, hãy ghi **receipt và business state một cách atomic trong transaction consumer**, kết hợp idempotency, unique constraints và xử lý trùng an toàn.

Khi có retry, crash hoặc event đến muộn, chuỗi bằng chứng này giúp trả lời chính xác **đang thiếu bước nào**, thay vì che lỗi sau một cờ thành công chung. Thiết kế đúng bằng chứng, kết hợp quan sát và đối soát, là nền tảng để ứng dụng Spring Modulith giao sự kiện đáng tin cậy.

### Tài liệu tham khảo

- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html): transactional listeners, Event Publication Registry và recovery.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): transaction phases và xử lý sau commit.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): ranh giới transaction và `REQUIRES_NEW`.

> Các bảng receipt, SQL PostgreSQL và class Java trong bài là mẫu thiết kế minh họa, **không phải schema mặc định** của Spring Modulith. Khi triển khai thực tế, cần điều chỉnh theo transaction manager, backend registry, phiên bản framework và yêu cầu nghiệp vụ. Content QA chuyên sâu thực hiện ở bước tiếp theo.
