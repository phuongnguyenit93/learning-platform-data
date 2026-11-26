# Log event lifecycle

Application event thường đi qua nhiều bước và có thể được xử lý bởi nhiều module. Khi một đơn hàng được tạo, module nguồn phát `OrderPlaced`; các listener có thể giữ hàng, tạo yêu cầu thanh toán hoặc gửi thông báo. Nếu một listener chạy chậm, thất bại hoặc được thử lại sau khi ứng dụng khởi động lại, nhóm phát triển cần lần theo cùng một event qua các bước đó.

Log event lifecycle ghi lại những mốc quan trọng từ lúc event được phát, publication được đăng ký, listener bắt đầu xử lý, listener hoàn tất hoặc thất bại, cho tới khi công việc được phục hồi. Log cần đủ ngữ cảnh để liên kết các bước và chẩn đoán sự cố, đồng thời không biến payload nghiệp vụ thành dữ liệu log tràn lan.

## 1. Vì sao cần log toàn bộ vòng đời event?

Một dòng log như `OrderPlaced processed` không trả lời được nhiều câu hỏi vận hành:

- Event được phát trong transaction nào và transaction đó đã commit chưa?
- Listener nào đã nhận event, listener nào chưa bắt đầu?
- Listener chạy mất bao lâu và có gọi dịch vụ phụ thuộc nào bị lỗi không?
- Event có được giao lại hay đây là lần xử lý đầu tiên?
- Một listener đã hoàn tất nhưng listener khác còn pending hay không?
- Một request của người dùng đã dẫn tới những event và hành động nào?

Nếu mỗi module tự ghi log theo một định dạng khác nhau, việc tìm một event qua nhiều module thường phải dựa vào chuỗi thông báo tự do. Structured logging giải quyết việc này bằng cách ghi các trường có tên và kiểu ổn định, ví dụ `eventId`, `eventType`, `listenerId`, `correlationId`, `outcome` và `durationMs`.

Log lifecycle có ba mục tiêu chính:

1. **Theo dấu:** liên kết event với request, aggregate, publication và listener.
2. **Chẩn đoán:** xác định bước nào thất bại, thời điểm xảy ra và nguyên nhân kỹ thuật.
3. **Vận hành:** hỗ trợ phát hiện backlog, retry, phục hồi và đối chiếu trạng thái với Event Publication Registry.

Log là bản ghi quan sát phục vụ con người và hệ thống phân tích. Nó không thay thế Event Publication Registry, transaction database, metric hoặc trace phân tán.

## 2. Mô hình hóa các mốc trong event lifecycle

Với event được phát trong transaction và xử lý bởi transactional listener, các mốc thường cần quan sát gồm:

| Mốc | Ý nghĩa | Thông tin nên ghi |
| --- | --- | --- |
| `event.published` | Module nguồn phát event trong luồng nghiệp vụ. | Event ID, event type, aggregate ID, correlation ID. |
| `publication.registered` | Publication tới listener được đăng ký trong cơ chế theo dõi. | Listener ID hoặc định danh listener, thời điểm, event ID nếu có. |
| `event.committed` | Transaction nguồn commit thành công. | Transaction outcome hoặc mốc commit được quan sát từ tầng phù hợp. |
| `listener.started` | Listener bắt đầu thực thi. | Listener ID, event ID, attempt nếu có, thời điểm bắt đầu. |
| `listener.succeeded` | Listener hoàn tất công việc. | Listener ID, duration, outcome và business reference. |
| `listener.failed` | Listener kết thúc bằng lỗi. | Listener ID, exception type, lỗi phân loại, duration. |
| `publication.resubmitted` | Publication chưa hoàn tất được yêu cầu gửi lại. | Publication reference, listener, lý do và operator/job nếu có. |
| `listener.recovered` | Một lần xử lý lại đã hoàn tất thành công. | Event ID, listener, attempt/recovery context và outcome. |

Không phải ứng dụng nào cũng có sẵn callback công khai cho mọi mốc trên. Spring Modulith cung cấp `@ApplicationModuleListener` và Event Publication Registry để thực thi, theo dõi publication tới transactional listener. Những mốc bắt đầu/kết thúc listener hoặc correlation cần thiết có thể được ghi ở code ứng dụng, decorator/interceptor hoặc instrumentation phù hợp với phiên bản đang dùng.

Đặc biệt, không nên ghi `publication.registered` hay `event.committed` chỉ vì code đã gọi `publishEvent`. Lệnh phát event trong transaction chưa chứng minh transaction đã commit. Hãy đặt log ở tầng có thể xác nhận chính xác mốc đó; nếu không có instrumentation thích hợp, ghi một mốc ít khẳng định hơn như `event.publish_requested`.

## 3. Dùng định danh ổn định để liên kết log

Một event nên mang định danh và metadata có thể đi xuyên qua các module:

| Trường | Vai trò |
| --- | --- |
| `eventId` | Định danh lần phát logic; giữ ổn định khi cùng event được retry. |
| `eventType` | Tên hợp đồng event, ví dụ `orders.order-placed`. |
| `aggregateId` | Định danh aggregate hoặc thực thể nghiệp vụ liên quan. |
| `aggregateVersion` | Phiên bản/sequence nghiệp vụ để phát hiện event cũ hoặc thiếu. |
| `correlationId` | Liên kết các thao tác thuộc cùng một request hoặc luồng nghiệp vụ. |
| `causationId` | Chỉ ra event/command trực tiếp gây ra event hiện tại. |
| `traceId` | Liên kết trace phân tán nếu hệ thống dùng tracing. |
| `listenerId` | Định danh listener đang xử lý publication. |
| `publicationId` | Định danh publication cụ thể nếu framework/instrumentation cung cấp. |
| `schemaVersion` | Phiên bản cấu trúc payload nếu event contract có version. |

Không đồng nhất các định danh này. `eventId` nhận diện event; `publicationId` nhận diện lần giao tới một listener; `correlationId` nhóm nhiều thao tác; `traceId` liên kết các span trong một trace. Một event có thể có nhiều publication ID, mỗi listener có một trạng thái riêng.

Ví dụ event DTO:

```java
import java.time.Instant;
import java.util.UUID;

public record OrderPlaced(
        UUID eventId,
        UUID orderId,
        long aggregateVersion,
        UUID correlationId,
        Instant occurredAt) {
}
```

`eventId` nên được tạo một lần khi hình thành event và được giữ nguyên qua retry. Không tạo ID mới khi chỉ gửi lại cùng publication, vì log và cơ chế idempotency sẽ xem lần thử lại như một event khác.

Nếu correlation hoặc trace context đến từ HTTP request, hãy truyền context qua cơ chế tracing/MDC phù hợp. Không lấy một giá trị tùy ý từ payload người dùng rồi tin tưởng nó như định danh đáng tin cậy; cần xác thực định dạng và giới hạn độ dài.

## 4. Structured logging thay cho thông điệp tự do

Log dạng chuỗi tự do khó tìm kiếm và tổng hợp. Ví dụ:

```text
Order listener failed for 8b7... because payment service timed out
```

Log có cấu trúc biểu diễn cùng thông tin bằng các trường ổn định:

```json
{
  "timestamp": "2026-11-25T14:20:31.482Z",
  "level": "WARN",
  "message": "Event listener failed",
  "eventId": "5c3e9b0d-6a74-4d3d-9a63-8f3c8a3e2f10",
  "eventType": "orders.order-placed",
  "aggregateId": "e2a1c5a4-3d62-4d0e-8e65-2a7a2c7a9c10",
  "listenerId": "billing-on-order-placed",
  "correlationId": "f1b7d5d0-6e4f-4f7a-a8b5-4f3e1d3a0b22",
  "outcome": "FAILED",
  "durationMs": 1204,
  "exceptionType": "PaymentServiceTimeoutException"
}
```

JSON trên là ví dụ hợp đồng log do ứng dụng định nghĩa, không phải output mặc định của Spring Modulith. Tên field nên thống nhất giữa module để hệ thống log có thể lọc theo `eventId`, `listenerId` hoặc `correlationId`.

Nên có một tập field chung:

- Thời gian, level, service/module và environment.
- Event ID, event type, aggregate ID và schema version.
- Correlation ID, causation ID và trace ID nếu có.
- Listener ID, publication ID nếu có và attempt/recovery context.
- Outcome, duration, exception type và error category.

Các field riêng của từng nghiệp vụ có thể bổ sung, nhưng tránh dùng tên khác nhau cho cùng một khái niệm ở mỗi module. Ví dụ, thống nhất `aggregateId` thay vì module này ghi `order`, module khác ghi `entityKey` và module khác ghi `businessRef` cho cùng một giá trị.

## 5. Ghi log ở module phát event

Module nguồn nên ghi nhận event được tạo và phát trong transaction nghiệp vụ. Log này giúp liên kết command với event, nhưng cần phân biệt yêu cầu phát event với commit thành công.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class OrderApplicationService {

    private static final Logger log =
            LoggerFactory.getLogger(OrderApplicationService.class);

    private final OrderRepository orders;
    private final ApplicationEventPublisher events;

    OrderApplicationService(
            OrderRepository orders,
            ApplicationEventPublisher events) {
        this.orders = orders;
        this.events = events;
    }

    @Transactional
    void placeOrder(OrderRequest request, String correlationId) {
        Order order = orders.save(Order.create(request));
        OrderPlaced event = OrderPlaced.create(order, correlationId);

        log.atInfo()
                .addKeyValue("eventId", event.eventId())
                .addKeyValue("eventType", "orders.order-placed")
                .addKeyValue("aggregateId", event.orderId())
                .addKeyValue("aggregateVersion", event.aggregateVersion())
                .addKeyValue("correlationId", event.correlationId())
                .log("Event publish requested");

        events.publishEvent(event);
    }
}
```

Đây là ví dụ SLF4J fluent logging API; cần dùng phiên bản SLF4J hỗ trợ các phương thức fluent tương ứng. Nếu dự án đang dùng API logger khác, giữ nguyên các trường cấu trúc với cơ chế tương đương.

Log `Event publish requested` chỉ nói rằng code đã gọi publisher. Nếu transaction rollback sau đó, event không trở thành một thay đổi đã commit. Muốn ghi mốc commit, hãy dùng transaction synchronization hoặc instrumentation ở đúng tầng và tránh ghi log thành công trước khi commit thực sự xảy ra.

## 6. Ghi log trong listener

Listener là nơi biết rõ lúc xử lý bắt đầu, kết thúc và exception phát sinh. Ghi hai mốc start và outcome giúp tính duration và xác định listener gây lỗi.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class InventoryOnOrderPlaced {

    private static final Logger log =
            LoggerFactory.getLogger(InventoryOnOrderPlaced.class);

    private final InventoryService inventory;

    InventoryOnOrderPlaced(InventoryService inventory) {
        this.inventory = inventory;
    }

    @ApplicationModuleListener
    void reserve(OrderPlaced event) {
        long startedAt = System.nanoTime();

        log.atInfo()
                .addKeyValue("eventId", event.eventId())
                .addKeyValue("eventType", "orders.order-placed")
                .addKeyValue("aggregateId", event.orderId())
                .addKeyValue("listenerId", "inventory-on-order-placed")
                .addKeyValue("correlationId", event.correlationId())
                .log("Event listener started");

        try {
            inventory.reserveFor(event.orderId());

            log.atInfo()
                    .addKeyValue("eventId", event.eventId())
                    .addKeyValue("eventType", "orders.order-placed")
                    .addKeyValue("aggregateId", event.orderId())
                    .addKeyValue("listenerId", "inventory-on-order-placed")
                    .addKeyValue("outcome", "SUCCEEDED")
                    .addKeyValue("durationMs",
                            (System.nanoTime() - startedAt) / 1_000_000)
                    .log("Event listener completed");
        } catch (RuntimeException ex) {
            log.atError()
                    .addKeyValue("eventId", event.eventId())
                    .addKeyValue("eventType", "orders.order-placed")
                    .addKeyValue("aggregateId", event.orderId())
                    .addKeyValue("listenerId", "inventory-on-order-placed")
                    .addKeyValue("outcome", "FAILED")
                    .addKeyValue("durationMs",
                            (System.nanoTime() - startedAt) / 1_000_000)
                    .addKeyValue("exceptionType", ex.getClass().getName())
                    .setCause(ex)
                    .log("Event listener failed");
            throw ex;
        }
    }
}
```

Ví dụ ghi lại lỗi rồi ném exception để framework nhận biết listener thất bại. Nếu bắt exception và kết thúc bình thường, publication có thể bị xem là hoàn tất dù tác dụng phụ chưa xảy ra. Chỉ chuyển lỗi thành kết quả thành công khi ứng dụng đã xử lý lỗi theo một quy tắc nghiệp vụ rõ ràng.

Trong code production, có thể giảm lặp bằng helper hoặc interceptor để chuẩn hóa field. Tuy nhiên, helper không được che giấu exception, thay đổi transaction boundary hoặc tạo log `SUCCEEDED` trước khi công việc thực sự hoàn tất.

## 7. Dùng MDC để gắn context vào log

Mapped Diagnostic Context (MDC) của SLF4J cho phép gắn các giá trị như `eventId`, `correlationId` và `listenerId` vào mọi log được ghi trong cùng luồng thực thi. Đây là cách tiện lợi khi một listener gọi nhiều service và không muốn truyền lại các trường log qua từng lời gọi.

```java
import org.slf4j.MDC;

@ApplicationModuleListener
void reserve(OrderPlaced event) {
    MDC.put("eventId", event.eventId().toString());
    MDC.put("correlationId", event.correlationId().toString());
    MDC.put("listenerId", "inventory-on-order-placed");

    try {
        inventory.reserveFor(event.orderId());
    } finally {
        MDC.remove("eventId");
        MDC.remove("correlationId");
        MDC.remove("listenerId");
    }
}
```

Luôn dọn MDC trong `finally`. Thread pool tái sử dụng thread; nếu không xóa context, log của event tiếp theo có thể mang nhầm ID của event trước.

MDC thường gắn với thread hiện tại. Khi chuyển sang `CompletableFuture`, executor hoặc reactive pipeline, context có thể không tự truyền sang thread khác. Cần dùng cơ chế context propagation phù hợp với stack của ứng dụng, chẳng hạn task decorator hoặc Micrometer Context Propagation nếu đã được cấu hình. Không giả định MDC tự động đi qua mọi ranh giới bất đồng bộ.

Nếu dùng tracing, ưu tiên tích hợp trace context chuẩn thay vì tự tạo một hệ thống correlation song song. `traceId` và `spanId` có thể được đưa vào log qua logging instrumentation; `correlationId` vẫn hữu ích cho nghiệp vụ và có thể tồn tại lâu hơn một trace.

## 8. Log retry và recovery

Retry là một phần của vòng đời event, không phải một event nghiệp vụ mới. Khi publication chưa hoàn tất được gửi lại, cần giữ nguyên event ID và ghi rõ đây là lần thử tiếp theo.

Các field hữu ích:

- `eventId` và `eventType` của event gốc.
- `listenerId` đang được xử lý.
- `attempt` hoặc `recoveryRunId` nếu ứng dụng có thể xác định chính xác.
- `previousErrorCategory` và `retryReason`.
- `requestedBy` hoặc tên scheduled job đối với thao tác vận hành.
- `outcome` và `durationMs` của lần thử mới.

Ví dụ log retry:

```json
{
  "level": "INFO",
  "message": "Event publication resubmitted",
  "eventId": "5c3e9b0d-6a74-4d3d-9a63-8f3c8a3e2f10",
  "eventType": "orders.order-placed",
  "listenerId": "notification-on-order-placed",
  "attempt": 2,
  "retryReason": "MAIL_PROVIDER_TIMEOUT",
  "outcome": "RESUBMITTED"
}
```

`attempt` chỉ nên được ghi khi ứng dụng hoặc cơ chế retry thực sự cung cấp số lần thử đáng tin cậy. Đừng tự tăng một biến trong bộ nhớ nếu nó sẽ mất sau restart hoặc không đồng bộ giữa nhiều instance. Nếu không biết số lần thử, ghi `recoveryRunId` hoặc `retryRequestedAt` thay vì tạo một con số gây hiểu nhầm.

Spring Modulith cung cấp `IncompleteEventPublications` ở các phiên bản có API tương ứng để truy vấn và resubmit publication chưa hoàn tất. Khi gọi API này từ công cụ vận hành, hãy ghi một log riêng cho yêu cầu resubmit và để listener ghi outcome khi nó thực sự chạy. Log yêu cầu resubmit không có nghĩa listener đã thành công.

## 9. Kết hợp log với Event Publication Registry

Event Publication Registry theo dõi trạng thái giao event tới transactional listener. Với relational adapter, registry lưu publication trong database và có thể cho biết publication nào chưa được đánh dấu hoàn tất. Log bổ sung bối cảnh thời gian, lỗi và các bước bên trong listener.

Hai nguồn thông tin có vai trò khác nhau:

| Nguồn | Câu hỏi trả lời tốt |
| --- | --- |
| Event Publication Registry | Listener nào còn publication chưa hoàn tất? Publication nào đã được ghi nhận hoàn tất? |
| Application log | Listener đã làm gì, bắt đầu lúc nào, lỗi cụ thể nào xảy ra? |
| Metrics | Backlog, latency và error rate đang tăng hay giảm? |
| Distributed trace | Những lời gọi nào nằm trong cùng một request/luồng xử lý và bước nào chiếm thời gian? |

Không nên dùng log làm nguồn trạng thái duy nhất. Log có thể bị sampling, rotate hoặc thất lạc khi hệ thống log gián đoạn. Cũng không nên suy ra publication đã hoàn tất chỉ vì có dòng `listener.succeeded` nếu log được ghi trước khi transaction listener commit. Hãy đặt mốc thành công ở vị trí phù hợp với semantics của công việc và đối chiếu registry khi điều tra.

Không cập nhật trực tiếp bảng publication để làm cho log và registry trông đồng nhất. Nếu trạng thái cần phục hồi, dùng API công khai của registry theo phiên bản đang triển khai.

## 10. Chọn log level theo ý nghĩa vận hành

Log quá nhiều ở mức `INFO` khiến sự kiện bình thường che khuất lỗi. Log quá ít khiến operator không thể biết listener nào đang chậm hoặc thất bại. Nên định nghĩa quy ước nhất quán:

| Level | Trường hợp phù hợp |
| --- | --- |
| `TRACE` | Chi tiết rất nhỏ khi điều tra chuyên sâu; thường tắt ở production. |
| `DEBUG` | Payload metadata hoặc bước nội bộ ít quan trọng, chỉ bật có kiểm soát. |
| `INFO` | Event được phát, listener hoàn tất, recovery được yêu cầu hoặc một chuyển trạng thái bình thường. |
| `WARN` | Lỗi tạm thời, retry, backlog vượt ngưỡng hoặc dependency có dấu hiệu suy giảm. |
| `ERROR` | Listener thất bại không được xử lý, lỗi không thể phục hồi tự động hoặc cần can thiệp. |

Không ghi cùng một exception ở nhiều tầng như thể mỗi tầng là một lỗi mới. Nếu listener ghi log lỗi rồi ném exception, framework hoặc global handler có thể cũng ghi stack trace. Hãy chọn một tầng chịu trách nhiệm ghi stack trace đầy đủ và các tầng còn lại ghi metadata bổ sung ở mức phù hợp.

## 11. Log an toàn: không biến payload thành dữ liệu giám sát

Event có thể chứa tên, email, địa chỉ, số tiền, thông tin thanh toán hoặc dữ liệu nội bộ. Ghi toàn bộ payload vào log làm tăng rủi ro lộ dữ liệu, tăng chi phí lưu trữ và khiến việc kiểm soát retention khó hơn.

Ưu tiên ghi metadata cần cho điều tra:

- Event ID, event type và schema version.
- Aggregate ID hoặc business reference đã được phép ghi.
- Listener ID, outcome, duration và exception category.
- Correlation ID và trace ID.

Tránh ghi:

- Toàn bộ payload hoặc object `toString()` không kiểm soát.
- Access token, mật khẩu, API key, cookie hoặc credential.
- Số thẻ, dữ liệu xác thực hoặc thông tin cá nhân không cần thiết.
- Nội dung request/response bên ngoài nếu chứa dữ liệu nhạy cảm.

Nếu cần lưu một phần dữ liệu để điều tra, hãy dùng allowlist field, masking hoặc hashing theo chính sách dữ liệu của tổ chức. Giới hạn quyền truy cập log, thời gian lưu và khả năng tải xuống. Không dùng email hoặc số điện thoại làm correlation ID.

## 12. Tránh log storm và kiểm soát chi phí

Một listener lỗi liên tục có thể ghi cùng một stack trace hàng nghìn lần. Log storm làm tăng chi phí lưu trữ, ảnh hưởng hiệu năng và che khuất các lỗi khác.

Các biện pháp phù hợp:

- Dùng retry có backoff và jitter thay vì retry liên tục.
- Ghi log đầy đủ ở lần lỗi đầu hoặc khi error category thay đổi; các lần lặp có thể được tổng hợp có kiểm soát.
- Giới hạn stack trace lặp nhưng vẫn giữ exception type, event ID, listener ID và số lần xảy ra.
- Dùng metric để đếm lỗi thường xuyên, thay vì ghi một dòng log cho mọi lần lặp nếu tải quá lớn.
- Cảnh báo khi error rate hoặc publication age vượt ngưỡng, không chỉ dựa vào từng dòng log.
- Giữ log của thao tác recovery và trạng thái cuối để audit.

Sampling có thể hữu ích cho log debug lưu lượng cao, nhưng không được làm mất các bản ghi audit hoặc lỗi cần thiết để điều tra publication chưa hoàn tất. Hãy phân biệt log chẩn đoán có thể sampling với audit record cần độ tin cậy và chính sách lưu trữ riêng.

## 13. Tạo metric từ lifecycle nhưng tránh cardinality cao

Log lưu từng lần xử lý; metric tổng hợp xu hướng. Một bộ metric cơ bản có thể gồm:

| Metric | Kiểu gợi ý | Nhãn phù hợp |
| --- | --- | --- |
| `application_event_published_total` | Counter | `event_type`, `module` |
| `application_event_listener_success_total` | Counter | `event_type`, `listener_id` |
| `application_event_listener_failure_total` | Counter | `event_type`, `listener_id`, `error_category` |
| `application_event_listener_duration` | Timer/histogram | `event_type`, `listener_id` |
| `application_event_publication_pending` | Gauge | `listener_id` |
| `application_event_publication_oldest_age` | Gauge | `listener_id` |

Không đưa `eventId`, `aggregateId`, `correlationId`, `traceId` hoặc exception message vào metric label. Đây là các giá trị có cardinality rất cao, làm tăng bộ nhớ và chi phí của hệ thống metric. Chúng phù hợp với log hoặc trace, nơi có thể truy vấn theo từng giá trị cụ thể.

Metric cũng không thay thế registry. Gauge backlog cần được lấy từ nguồn trạng thái đáng tin cậy hoặc được cập nhật có kiểm soát; không nên chỉ tăng/giảm một biến trong bộ nhớ của một instance nếu ứng dụng chạy nhiều replica.

## 14. Tích hợp log với trace phân tán

Khi một request phát event rồi listener xử lý bất đồng bộ, trace HTTP ban đầu có thể kết thúc trước khi listener chạy. Có hai nhu cầu khác nhau:

- Liên kết event với request đã tạo ra nó.
- Theo dõi thời gian xử lý riêng của listener và các lời gọi dependency.

`correlationId` giúp tìm các log thuộc cùng luồng nghiệp vụ. `traceId` và span biểu diễn quan hệ quan sát trong distributed tracing. Tùy cấu hình OpenTelemetry/Micrometer Tracing, context có thể được truyền qua message hoặc event metadata. Nếu không có context propagation, hãy giữ correlation ID trong event và tạo span mới cho listener, đồng thời liên kết với context gốc bằng cơ chế phù hợp.

Không nên giữ một span đồng bộ mở xuyên suốt một khoảng thời gian dài chỉ để nối event với request. Với xử lý bất đồng bộ, span của listener thường là một span riêng có liên kết (link) tới context phát event hoặc mang cùng correlation metadata. Cách tổ chức cụ thể phụ thuộc tracing backend và instrumentation đang dùng.

Trace giúp xem thời gian từng bước và quan hệ gọi dịch vụ. Log giúp xem nội dung sự kiện và lỗi chi tiết. Kết hợp cả hai bằng trace ID và event ID giúp điều tra từ dashboard tới dòng log cụ thể.

## 15. Ví dụ truy vấn log khi điều tra

Với log JSON có trường ổn định, operator có thể lọc theo event ID để xem toàn bộ vòng đời:

```text
eventId = "5c3e9b0d-6a74-4d3d-9a63-8f3c8a3e2f10"
```

Tìm tất cả lỗi của một listener:

```text
listenerId = "notification-on-order-placed"
AND outcome = "FAILED"
```

Tìm các listener xử lý chậm hơn ngưỡng:

```text
eventType = "orders.order-placed"
AND durationMs > 2000
```

Đây là biểu thức tìm kiếm giả định, không phải cú pháp cố định của một sản phẩm log cụ thể. Hãy ánh xạ theo query language của ELK/OpenSearch, Loki, Splunk hoặc nền tảng đang dùng.

Khi điều tra một publication chưa hoàn tất:

1. Tìm event ID và correlation ID từ log module nguồn.
2. Xác định các listener đã bắt đầu và outcome cuối cùng của từng listener.
3. Đối chiếu publication pending trong Event Publication Registry.
4. Xem exception, trace và dependency liên quan ở listener lỗi.
5. Sau recovery, xác nhận có log resubmit, listener outcome thành công và registry ghi nhận hoàn tất.

## 16. Kiểm thử log lifecycle

Log là một phần của khả năng vận hành. Có thể kiểm tra những field quan trọng mà không khóa test vào toàn bộ câu thông báo hoặc định dạng nội bộ của logger.

Các kịch bản nên có:

- **Publish:** log có event ID, event type, aggregate ID và correlation ID.
- **Listener success:** có mốc bắt đầu/kết thúc, listener ID, outcome và duration không âm.
- **Listener failure:** log chứa exception type và event ID; exception vẫn được truyền ra theo semantics cần thiết.
- **Retry:** log giữ nguyên event ID, xác định đúng listener và phân biệt yêu cầu resubmit với kết quả xử lý.
- **MDC cleanup:** sau khi listener hoàn tất hoặc lỗi, thread không giữ context cũ cho công việc tiếp theo.
- **Context propagation:** correlation/trace context được truyền đúng qua executor hoặc ranh giới bất đồng bộ đã cấu hình.
- **Data safety:** log không chứa token, credential hoặc payload nhạy cảm ngoài allowlist.
- **Metric cardinality:** metric không gắn event ID hoặc aggregate ID làm label.

Không nên assert chính xác toàn bộ stack trace hoặc thứ tự tuyệt đối của các log bất đồng bộ nếu hệ thống không bảo đảm điều đó. Hãy kiểm tra sự hiện diện của các field và mối liên hệ giữa event/listener/outcome.

## 17. Checklist triển khai

- [ ] Event có `eventId` ổn định và metadata correlation cần thiết.
- [ ] Log phân biệt publish requested với transaction commit.
- [ ] Listener ghi được start, success hoặc failure với listener ID.
- [ ] Exception chưa được xử lý được truyền ra để registry nhận biết lỗi.
- [ ] Retry/resubmit được log riêng và giữ event ID gốc.
- [ ] Log dùng structured fields nhất quán giữa các module.
- [ ] MDC được dọn trong `finally` và context được truyền đúng qua executor.
- [ ] Event Publication Registry được dùng để đối chiếu trạng thái publication.
- [ ] Log level phù hợp và không ghi stack trace trùng lặp ở nhiều tầng.
- [ ] Payload nhạy cảm, token và credential không xuất hiện trong log.
- [ ] Log storm được kiểm soát bằng retry/backoff, tổng hợp và metric.
- [ ] Metric không dùng ID có cardinality cao làm label.
- [ ] Log, trace và metric có thể liên kết bằng event/correlation/trace ID.
- [ ] Có kiểm thử cho success, failure, retry, context cleanup và data safety.

Log event lifecycle giúp nhóm phát triển nhìn thấy event đã đi qua những bước nào và listener nào cần được xử lý. Khi định danh ổn định, structured logging, context propagation và Event Publication Registry được dùng đúng vai trò, việc điều tra lỗi và phục hồi giao sự kiện trong Spring Modulith trở nên rõ ràng, nhất quán và an toàn hơn.
