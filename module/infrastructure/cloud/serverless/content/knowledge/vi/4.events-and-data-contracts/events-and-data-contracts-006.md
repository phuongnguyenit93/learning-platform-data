# Correlation ID, causation ID và truy vết chuỗi sự kiện

Trong một ứng dụng serverless, một yêu cầu HTTP có thể kích hoạt nhiều function, đi qua event bus, được giữ trong queue rồi tiếp tục bởi nhiều consumer. Một thao tác nghiệp vụ vì vậy thường không nằm trong một lần gọi duy nhất. Khi có lỗi, câu hỏi vận hành không chỉ là function nào thất bại mà còn là: thao tác ban đầu là gì, sự kiện nào dẫn đến lần xử lý này, những bước nào đã hoàn thành và những bước nào còn đang chờ?

Correlation ID và causation ID giúp trả lời hai câu hỏi nghiệp vụ khác nhau. **Correlation ID** nhóm các thông điệp thuộc cùng một quy trình hoặc một yêu cầu nghiệp vụ. **Causation ID** chỉ ra thông điệp trực tiếp đã gây ra thông điệp hiện tại. Khi kết hợp chúng với event ID, distributed trace và log có cấu trúc, nhóm vận hành có thể lần theo một chuỗi xử lý từ HTTP gateway đến function, database, event bus và consumer.

Chủ đề này thuộc Cloud Serverless: function có thể được kích hoạt bởi HTTP, thông điệp hoặc sự kiện; trạng thái và lịch sử quy trình phải tồn tại bên ngoài vòng đời của một function invocation. Các định danh cần được truyền qua đúng ranh giới để quy trình có thể được quan sát ngay cả khi mỗi bước chạy trên một runtime khác nhau.

## 1. Vì sao cần nhiều loại định danh?

Hãy xét luồng đặt hàng. Client gửi yêu cầu tạo đơn hàng. Function lưu đơn hàng và phát `OrderSubmitted`. Một consumer giữ chỗ tồn kho rồi phát `InventoryReserved`. Consumer thanh toán nhận sự kiện này và phát `PaymentAuthorized`. Cuối cùng, consumer giao hàng nhận sự kiện thanh toán để tạo lệnh chuẩn bị giao.

Mỗi bước có thể chạy ở một function khác nhau, vào những thời điểm khác nhau và thậm chí ở các vùng hoặc dịch vụ cloud khác nhau. Log chỉ có tên function và thời gian sẽ không đủ để nối các bước. Nếu dùng một ID duy nhất cho mọi mục đích, hệ thống cũng khó phân biệt một quy trình nghiệp vụ với một lần giao message hoặc một span kỹ thuật.

Các định danh sau có vai trò riêng:

| Định danh | Trả lời câu hỏi | Phạm vi và vòng đời |
|---|---|---|
| `eventId` | Đây là lần phát sự kiện nào? | Duy nhất cho một event envelope; giữ nguyên khi cùng message được giao lại |
| `correlationId` | Sự kiện này thuộc quy trình nghiệp vụ nào? | Được giữ ổn định qua các bước thuộc cùng quy trình |
| `causationId` | Thông điệp trực tiếp nào đã tạo ra thông điệp này? | Thường bằng `eventId` của event cha hoặc ID của command/request gây ra nó |
| `traceId` | Các thao tác kỹ thuật này thuộc distributed trace nào? | Do hệ thống tracing quản lý; có thể thay đổi khi bắt đầu trace mới hoặc tách một quy trình dài |
| `spanId` | Thao tác kỹ thuật cụ thể nào đang được ghi nhận? | Duy nhất cho một span trong trace |
| `requestId` | Lần gọi vào hệ thống này là lần nào? | Thường gắn với một request hoặc invocation ở một ranh giới cụ thể |
| `aggregateId` | Đối tượng nghiệp vụ nào đang thay đổi? | Ổn định theo vòng đời đối tượng, ví dụ `order-1052` |

Không dùng các định danh này thay thế lẫn nhau. `eventId` dùng để nhận diện message, `correlationId` dùng để nhóm quy trình, `causationId` diễn tả quan hệ nguyên nhân trực tiếp, còn `traceId` và `spanId` phục vụ quan sát kỹ thuật. `aggregateId` nhận diện đối tượng nghiệp vụ, không nhận diện một lần xử lý.

## 2. Phân biệt correlation ID và causation ID

**Correlation ID** trả lời: “Những hoạt động nào thuộc cùng một hành trình nghiệp vụ?” Ví dụ, mọi bước từ lúc tiếp nhận đơn hàng đến khi đơn hàng được chuẩn bị giao có thể dùng cùng `correlationId`. Khi một đơn hàng tạo ra nhiều nhánh như thanh toán, thông báo và phân tích, các nhánh vẫn có thể giữ cùng correlation ID.

**Causation ID** trả lời: “Thông điệp trực tiếp nào đã khiến thông điệp này được tạo ra?” Khi consumer nhận `OrderSubmitted` và phát `InventoryReserved`, event mới có `causationId` bằng `eventId` của `OrderSubmitted`. Nếu consumer tiếp tục nhận `InventoryReserved` rồi phát `PaymentAuthorized`, causation ID của event thanh toán trỏ đến event giữ chỗ tồn kho.

Ví dụ quan hệ:

```text
HTTP request
  requestId = req-01
  correlationId = flow-77
  |
  +-- OrderSubmitted
  |     eventId = evt-100
  |     causationId = req-01
  |     correlationId = flow-77
  |     |
  |     +-- InventoryReserved
  |     |     eventId = evt-110
  |     |     causationId = evt-100
  |     |     correlationId = flow-77
  |     |     |
  |     |     +-- PaymentAuthorized
  |     |           eventId = evt-120
  |     |           causationId = evt-110
  |     |           correlationId = flow-77
  |     |
  |     +-- CustomerNotified
  |           eventId = evt-130
  |           causationId = evt-100
  |           correlationId = flow-77
```

Hai event `InventoryReserved` và `CustomerNotified` cùng có correlation ID vì chúng thuộc cùng quy trình đặt hàng. Cả hai có causation ID bằng `evt-100` vì chúng được tạo trực tiếp từ `OrderSubmitted`. `PaymentAuthorized` có cùng correlation ID nhưng causation ID là `evt-110`, phản ánh quan hệ cha-con gần nhất.

Đừng đặt `causationId` bằng correlation ID. Làm như vậy sẽ chỉ cho biết hai event cùng thuộc một quy trình, không cho biết event nào đã trực tiếp tạo event nào. Cũng không nên đặt causation ID bằng aggregate ID: một đơn hàng có thể phát hàng trăm event trong vòng đời của nó.

## 3. Quan hệ giữa business correlation và distributed tracing

Correlation ID và distributed trace thường xuất hiện cùng nhau trong log, nhưng phục vụ hai lớp khác nhau.

- Correlation ID là metadata nghiệp vụ. Nó có thể được lưu trong outbox, event journal, workflow state và audit record để tìm toàn bộ lịch sử của một quy trình trong nhiều ngày hoặc nhiều tuần.
- Trace ID là metadata quan sát kỹ thuật. Nó liên kết các span trong một trace, chẳng hạn HTTP server span, function span, database client span và message consumer span. Trace backend có thể sampling hoặc xóa dữ liệu theo thời hạn lưu trữ.
- Span ID nhận diện một thao tác cụ thể. Một span có thể có parent span hoặc có links đến nhiều span khác.

Một trace không nhất thiết tồn tại suốt vòng đời nghiệp vụ. Một quy trình có thể kéo dài nhiều ngày, vượt thời hạn lưu trace hoặc đi qua một bước được khởi chạy theo lịch. Khi đó correlation ID vẫn cần được giữ, dù mỗi chặng có thể tạo một trace kỹ thuật mới. Ngược lại, một trace có thể chứa nhiều hoạt động kỹ thuật mà không tương ứng một-một với event nghiệp vụ.

W3C Trace Context định nghĩa các trường truyền ngữ cảnh như `traceparent` và `tracestate`. Trong HTTP, chúng thường được truyền qua header. Với message hoặc event, chúng được truyền qua metadata/header của transport nếu nền tảng hỗ trợ. Không nên mặc định đặt `traceparent` vào payload nghiệp vụ: trace context là metadata quan sát, có vòng đời và chính sách riêng. Nếu hệ thống cần một định danh nghiệp vụ bền vững, hãy lưu correlation ID trong event envelope hoặc trường metadata nghiệp vụ đã được chuẩn hóa.

| | Correlation ID | Trace ID |
|---|---|---|
| Mục đích | Nhóm các bước của quy trình nghiệp vụ | Nối các thao tác kỹ thuật trong distributed trace |
| Nơi lưu | Event envelope, workflow state, audit record, log | Trace context trong header/transport metadata và trace backend |
| Thời hạn | Theo thời hạn nghiệp vụ và kiểm toán | Theo sampling và retention của hệ thống tracing |
| Có thể đổi giữa các bước? | Thường không, nếu vẫn cùng quy trình | Có thể đổi khi tách trace mới hoặc tạo workflow dài hạn |
| Dùng để chống xử lý trùng? | Không | Không |

## 4. Quy tắc tạo và truyền định danh

Để các service có thể phối hợp, cần thống nhất nơi tạo ID và cách truyền ID qua từng loại trigger.

### Khi nhận HTTP request

API gateway hoặc function ở biên tạo một correlation ID mới khi bắt đầu một quy trình nghiệp vụ mới. Nếu client gửi request ID hoặc correlation ID, hãy coi đó là dữ liệu đầu vào bên ngoài: kiểm tra định dạng, giới hạn độ dài, tránh ký tự điều khiển và áp dụng quy tắc namespace phù hợp. Không dùng một giá trị do client tùy ý cung cấp làm bằng chứng xác thực hoặc quyền truy cập.

Có thể giữ ID do client gửi trong một trường `clientRequestId` để hỗ trợ đối chiếu, trong khi hệ thống tạo `correlationId` nội bộ. Nếu API cho phép client tiếp tục một quy trình đã tồn tại, phải xác minh người gọi có quyền truy cập quy trình đó trước khi chấp nhận correlation ID cũ.

Mỗi lần nhận HTTP có thể có `requestId` riêng. Nếu client retry cùng thao tác với cùng idempotency key, request ID của từng lần gọi có thể khác nhau, nhưng correlation ID của thao tác đã được tiếp nhận và kết quả idempotent nên được liên kết theo quy tắc của API. Idempotency key là một cơ chế riêng, không thay thế correlation ID.

### Khi function phát event

Khi function tạo event đầu tiên từ một request, event có correlation ID của quy trình và causation ID trỏ đến command hoặc request đã kích hoạt thao tác, nếu command/request có định danh ổn định. Event mới luôn có event ID mới.

Khi consumer xử lý một event rồi phát event tiếp theo:

1. Giữ nguyên correlation ID từ event đầu vào.
2. Tạo event ID mới cho event đầu ra.
3. Đặt causation ID của event đầu ra bằng event ID của event trực tiếp được xử lý.
4. Giữ aggregate ID và tăng aggregate version theo quy tắc của miền nghiệp vụ nếu event phản ánh thay đổi của aggregate đó.
5. Truyền trace context qua transport metadata theo chuẩn tracing.

### Khi gọi HTTP service khác

Truyền correlation ID trong header nghiệp vụ đã thống nhất, ví dụ `X-Correlation-ID`, nếu API đích hỗ trợ. Truyền trace context bằng `traceparent`/`tracestate` thông qua OpenTelemetry propagator hoặc instrumentation của HTTP client. Không tự tạo traceparent bằng cách ghép chuỗi tùy ý; định dạng và quy tắc sinh trace/span ID thuộc thư viện tracing.

### Khi publish vào event bus hoặc queue

Đặt event ID, correlation ID và causation ID trong envelope hoặc các message attributes được chuẩn hóa. Đặt trace context trong metadata của transport để consumer có thể extract. Kiểm tra giới hạn kích thước message và giới hạn số lượng/độ dài attribute của nền tảng đang dùng.

### Khi chạy theo lịch hoặc bắt đầu một quy trình độc lập

Một lần chạy định kỳ độc lập thường bắt đầu correlation ID mới. Nếu lịch chạy chỉ tiếp tục một workflow đã lưu, hãy nạp correlation ID từ workflow state. Không tái sử dụng một correlation ID cố định cho mọi lần chạy của một cron job vì các lần chạy khác nhau sẽ bị nhập làm một.

## 5. Thiết kế event envelope

Event envelope nên cung cấp các trường tối thiểu để nhận diện và truy vết event. Tên trường cần được thống nhất ở cấp hệ thống; các consumer không nên tự suy ra correlation ID từ tên queue hoặc aggregate ID.

Ví dụ envelope JSON:

```json
{
  "eventId": "evt-110",
  "eventType": "InventoryReserved",
  "schemaVersion": 1,
  "occurredAt": "2026-11-17T12:05:12Z",
  "correlationId": "flow-77",
  "causationId": "evt-100",
  "aggregate": {
    "type": "Order",
    "id": "order-1052",
    "version": 2
  },
  "data": {
    "orderId": "order-1052",
    "reservationId": "reservation-501"
  }
}
```

Trong ví dụ này, `eventId` nhận diện event hiện tại; `causationId` trỏ đến `OrderSubmitted`; `correlationId` giữ liên kết với quy trình tạo đơn hàng; `aggregate.version` hỗ trợ phát hiện event cũ hoặc sai thứ tự. `occurredAt` là thời điểm nghiệp vụ phát sinh, khác với thời điểm consumer nhận hoặc xử lý message.

Nếu dùng CloudEvents, các trường chuẩn như `id`, `source`, `type`, `subject`, `time` có thể mang phần lớn metadata cơ bản. Correlation ID và causation ID có thể được biểu diễn bằng extension attributes với tên thống nhất, chẳng hạn `correlationid` và `causationid`. Dù dùng CloudEvents hay envelope tự định nghĩa, cần tài liệu hóa quy tắc tương thích và không đổi ý nghĩa trường giữa các producer.

Không đưa mọi metadata kỹ thuật vào payload nghiệp vụ. Trace context nên ở transport metadata; số lần retry hoặc thông tin worker cũng thường thuộc message attributes/log. Event payload nên tập trung vào sự kiện nghiệp vụ và metadata cần tồn tại lâu dài.

## 6. Ví dụ Java: tạo event con với correlation và causation

Ví dụ sau minh họa hợp đồng metadata trung lập với nhà cung cấp cloud. `EventEnvelope` là kiểu dùng chung ở tầng ứng dụng; adapter của event bus chịu trách nhiệm serialize và ánh xạ sang message attributes của nền tảng.

```java
import java.time.Instant;
import java.util.UUID;

public record EventMetadata(
        String eventId,
        String eventType,
        int schemaVersion,
        Instant occurredAt,
        String correlationId,
        String causationId,
        String aggregateId,
        long aggregateVersion) {}

public record EventEnvelope<T>(EventMetadata metadata, T data) {}

public record OrderSubmitted(String orderId, String customerId) {}
public record InventoryReserved(String orderId, String reservationId) {}

public final class EventFactory {

    public EventEnvelope<InventoryReserved> inventoryReserved(
            EventEnvelope<OrderSubmitted> cause,
            String reservationId,
            long nextAggregateVersion) {

        EventMetadata parent = cause.metadata();
        EventMetadata metadata = new EventMetadata(
                "evt-" + UUID.randomUUID(),
                "InventoryReserved",
                1,
                Instant.now(),
                parent.correlationId(),
                parent.eventId(),
                parent.aggregateId(),
                nextAggregateVersion);

        InventoryReserved data = new InventoryReserved(
                cause.data().orderId(), reservationId);
        return new EventEnvelope<>(metadata, data);
    }
}
```

Điểm quan trọng nằm ở ba thao tác: event mới có ID mới, correlation ID được giữ từ event cha, và causation ID bằng event ID của event cha. Trong ứng dụng thực tế, nên inject `Clock` để kiểm thử thời gian, dùng ID generator phù hợp, xác định aggregate version trong cùng transaction với thay đổi dữ liệu và bảo đảm event cùng bản ghi outbox được commit nguyên tử.

Nếu consumer nhận command thay vì event, causation ID có thể trỏ đến command ID. Hợp đồng cần nói rõ ID đó thuộc loại đối tượng nào hoặc dùng một cấu trúc tham chiếu có `kind` và `id`, tránh trường hợp một consumer hiểu mọi causation ID đều là event ID.

## 7. Truyền trace context bằng OpenTelemetry trong Java

OpenTelemetry cung cấp API để inject trace context vào carrier trước khi gửi message và extract context khi nhận. Carrier có thể là map header, HTTP request builder hoặc message attributes tùy adapter. Ví dụ dưới đây dùng `Map<String, String>` để làm rõ quy trình; trong production, nên ưu tiên instrumentation tự động của HTTP client, messaging client và runtime khi có hỗ trợ.

### Inject khi publish

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.HashMap;
import java.util.Map;

public final class TraceHeaders {
    private final TextMapPropagator propagator;

    public TraceHeaders(OpenTelemetry openTelemetry) {
        this.propagator = openTelemetry.getPropagators()
                .getTextMapPropagator();
    }

    public Map<String, String> injectCurrentContext() {
        Map<String, String> carrier = new HashMap<>();
        propagator.inject(Context.current(), carrier, Map::put);
        return carrier;
    }
}
```

`injectCurrentContext()` tạo các trường propagation theo propagator đã cấu hình, thường gồm `traceparent` và có thể có `tracestate` hoặc baggage nếu được bật. Adapter publish chuyển map này vào message attributes. Không tự đặt `traceId` thành correlation ID để thay thế trường nghiệp vụ.

### Extract khi consume

```java
import io.opentelemetry.api.OpenTelemetry;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapPropagator;
import java.util.Map;

public final class TraceContextExtractor {
    private final TextMapPropagator propagator;

    public TraceContextExtractor(OpenTelemetry openTelemetry) {
        this.propagator = openTelemetry.getPropagators()
                .getTextMapPropagator();
    }

    public void process(Map<String, String> messageAttributes,
                        Runnable businessHandler) {
        Context extracted = propagator.extract(
                Context.root(), messageAttributes, Map::get);

        try (Scope scope = extracted.makeCurrent()) {
            businessHandler.run();
        }
    }
}
```

Đoạn mã minh họa việc khôi phục context trong thread đang xử lý. Với function runtime, cần bảo đảm scope được đóng ngay cả khi handler ném exception; không giữ `Context` trong biến static để dùng cho invocation sau. Nếu framework đã tự động extract context, không tạo thêm một parent span trùng lặp.

Trong ứng dụng đầy đủ, consumer thường tạo span `CONSUMER` cho lần xử lý message. Span có thể dùng context đã extract làm parent khi quan hệ là một chuỗi tuyến tính. Khi một consumer tổng hợp nhiều message độc lập, hãy cân nhắc span links đến các context đầu vào thay vì chọn tùy tiện một message làm parent duy nhất.

## 8. Fan-out, fan-in và quy trình có nhiều nguyên nhân

Fan-out xảy ra khi một event tạo ra nhiều nhánh xử lý. Các event con thường giữ chung correlation ID và cùng causation ID là event cha. Mỗi event con có event ID riêng. Nhờ vậy có thể tìm tất cả nhánh của một quy trình và xác định nhánh nào bắt đầu từ event nào.

Fan-in xảy ra khi một bước cần kết quả từ nhiều event, ví dụ chỉ phát `OrderReady` sau khi cả `PaymentAuthorized` và `InventoryReserved` hoàn tất. Một `causationId` đơn lẻ không diễn tả đầy đủ nhiều nguyên nhân trực tiếp. Trong trường hợp này:

- Giữ correlation ID của workflow.
- Lưu từng event đầu vào trong workflow state hoặc bảng dependency.
- Khi phát event tổng hợp, dùng một trường mở rộng như `causationIds` nếu hợp đồng cho phép, hoặc lưu tham chiếu các event đầu vào trong lịch sử workflow.
- Trong distributed trace, dùng span links để liên kết span tổng hợp với nhiều span đầu vào.

Không chọn một event đầu vào bất kỳ rồi coi đó là nguyên nhân duy nhất của kết quả tổng hợp. Cách làm đó làm mất quan hệ nhân quả thực tế và gây khó khăn khi điều tra sự cố.

## 9. Retry, redelivery và dead-letter queue

Retry là nơi nhiều hệ thống vô tình làm sai ý nghĩa của các ID.

**Khi queue giao lại cùng một message:** giữ nguyên event ID, correlation ID và causation ID. Lần giao lại không phải một event nghiệp vụ mới. Có thể ghi `deliveryAttempt`, `receiveCount`, thời điểm retry hoặc invocation ID trong metadata vận hành/log. Những trường này không được dùng để thay event ID.

**Khi ứng dụng phát một event retry mới:** nếu hệ thống phát `OrderProcessingRetryScheduled` hoặc `PaymentRetryRequested`, đây là một event mới và cần event ID mới. Correlation ID được giữ nếu vẫn thuộc workflow cũ; causation ID trỏ đến event hoặc command đã yêu cầu retry. Có thể bổ sung `retryOfEventId` để chỉ rõ event gốc được thử lại.

**Khi redrive từ DLQ:** nếu đưa nguyên message trở lại queue, giữ nguyên event ID và metadata nghiệp vụ để consumer có thể nhận diện cùng event. Ghi nhận thao tác redrive bằng audit log hoặc metadata vận hành riêng. Nếu công cụ vận hành tạo một command mới yêu cầu xử lý lại, command đó có ID riêng và có thể làm causation của một event retry mới.

Idempotency phải dựa trên event ID hoặc khóa nghiệp vụ phù hợp, kết hợp với tên consumer khi cần. Không dùng correlation ID làm idempotency key: một workflow có thể hợp lệ tạo nhiều event khác nhau và mỗi event cần được xử lý một lần theo chính sách của consumer. Cũng không dùng trace ID làm idempotency key vì trace có thể đổi khi retry hoặc khi bắt đầu trace mới.

## 10. Truy vấn lịch sử và chẩn đoán sự cố

Để truy vết hiệu quả, mỗi log xử lý event nên có tập trường thống nhất:

| Trường log | Mục đích |
|---|---|
| `timestamp` | Thời điểm log được ghi |
| `service` / `function` | Thành phần đang xử lý |
| `eventType` | Loại event đang xử lý |
| `eventId` | Tìm các lần xử lý cùng một event |
| `correlationId` | Tìm toàn bộ hoạt động thuộc một workflow |
| `causationId` | Tìm event cha trực tiếp |
| `traceId` / `spanId` | Mở distributed trace và span tương ứng |
| `aggregateId` / `aggregateVersion` | Theo dõi lịch sử của đối tượng nghiệp vụ |
| `outcome` / `errorCode` | Xác định kết quả và loại lỗi |
| `deliveryAttempt` | Phân biệt lần giao message khi điều tra retry |

Một quy trình điều tra có thể bắt đầu từ correlation ID để lấy toàn bộ event và log. Sau đó dùng causation ID để dựng quan hệ cha-con, event ID để tìm các lần giao lại, aggregate ID/version để kiểm tra thứ tự cập nhật, và trace ID để xem độ trễ giữa các span kỹ thuật.

Ví dụ truy vấn SQL giả định event journal có các cột metadata:

```sql
SELECT event_id,
       event_type,
       correlation_id,
       causation_id,
       aggregate_id,
       aggregate_version,
       occurred_at
FROM event_journal
WHERE correlation_id = :correlation_id
ORDER BY occurred_at, aggregate_version;
```

Truy vấn theo causation ID giúp tìm event con trực tiếp:

```sql
SELECT event_id, event_type, occurred_at
FROM event_journal
WHERE causation_id = :parent_event_id
ORDER BY occurred_at;
```

Trong hệ thống lớn, cần index theo correlation ID, event ID, causation ID và aggregate ID tùy access pattern. Nếu lưu event journal lâu dài, xác định retention, phân vùng dữ liệu và chính sách xóa theo yêu cầu pháp lý/nghiệp vụ. Trace backend thường tối ưu cho điều tra kỹ thuật ngắn hạn; event journal hoặc workflow history phù hợp hơn cho lịch sử nghiệp vụ bền vững.

## 11. Quan sát fan-out và quy trình dài hạn

Với một correlation ID, có thể tổng hợp số event đã phát, số consumer đã hoàn tất, số nhánh thất bại và thời gian từ event đầu đến event cuối. Những số liệu này giúp phát hiện một workflow bị kẹt dù từng function riêng lẻ đều không báo lỗi.

Nên theo dõi:

- Số workflow đang mở và tuổi của workflow cũ nhất.
- Thời gian từ event khởi đầu đến từng mốc nghiệp vụ.
- Số event chưa có consumer hoàn tất hoặc chưa có trạng thái kết thúc.
- Số lần redelivery, retry và số message trong DLQ.
- Độ trễ từ lúc event được phát đến lúc consumer bắt đầu và hoàn tất xử lý.
- Số event bị bỏ qua do duplicate hoặc bị từ chối do sai schema/thiếu metadata.

Không đưa correlation ID, event ID, user ID hoặc aggregate ID làm label của metric có cardinality cao. Những giá trị này phù hợp trong log và trace attributes có kiểm soát. Metric nên dùng nhãn giới hạn như `eventType`, `consumer`, `outcome`, `region` và `errorClass`.

Với workflow kéo dài nhiều giờ hoặc nhiều ngày, không cần giữ một trace mở xuyên suốt toàn bộ quy trình. Có thể tạo trace mới cho từng giai đoạn và thêm span link đến context trước đó nếu hệ thống tracing hỗ trợ. Correlation ID cùng workflow state duy trì liên kết nghiệp vụ. Cách này tránh phụ thuộc vào retention của trace backend và giới hạn kích thước trace.

## 12. Bảo mật và quyền riêng tư của định danh

Correlation ID và causation ID thường được ghi vào log, dashboard và công cụ hỗ trợ, vì vậy không nên nhúng thông tin cá nhân hoặc bí mật vào chúng. Dùng giá trị ngẫu nhiên hoặc ID không thể suy ra danh tính; không tạo ID bằng cách nối email, số điện thoại, access token hay dữ liệu nhạy cảm.

Một correlation ID do client gửi có thể bị giả mạo để làm nhiễu log hoặc cố tình khiến nhiều request xuất hiện như một quy trình. Hệ thống nên tạo ID nội bộ hoặc lưu riêng ID bên ngoài đã được làm sạch. Không dùng correlation ID, trace ID hay causation ID làm cơ chế phân quyền. Quyền truy cập workflow phải được kiểm tra bằng danh tính, tenant và chính sách nghiệp vụ.

Khi đưa ID vào log, cần tránh ghi toàn bộ payload để “dễ truy vết”. Chỉ ghi metadata cần thiết, che hoặc loại bỏ trường nhạy cảm và giới hạn quyền đọc log. Nếu correlation ID có thể được người dùng dùng để tra cứu trạng thái, nó phải là token khó đoán và vẫn cần kiểm tra quyền truy cập ở endpoint trạng thái.

## 13. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng cùng một ID cho correlation, event và trace | Không phân biệt được workflow, message và span | Dùng trường riêng, tài liệu hóa ý nghĩa và nơi sinh |
| Mỗi function tự tạo correlation ID mới | Chuỗi sự kiện bị đứt khi qua async boundary | Kế thừa correlation ID từ message đầu vào |
| Đặt causation ID bằng correlation ID | Mất quan hệ cha-con trực tiếp | Trỏ causation đến event/command trực tiếp gây ra event mới |
| Tạo event ID mới mỗi lần queue redeliver | Idempotency không nhận ra message trùng | Giữ event ID của message gốc qua redelivery |
| Dùng correlation ID làm idempotency key | Các event hợp lệ trong cùng workflow bị coi là trùng | Dùng event ID hoặc khóa nghiệp vụ theo thao tác |
| Chỉ truyền traceparent, không lưu correlation ID | Mất liên kết khi trace bị sampling hoặc hết retention | Lưu correlation ID trong event/workflow metadata |
| Nhét ID vào metric label | Cardinality tăng, chi phí và hiệu năng metric xấu | Giữ ID trong log/trace; metric dùng nhãn có miền giá trị nhỏ |
| Ghi ID do client gửi mà không kiểm tra | Log injection hoặc gom nhầm các request | Validate, giới hạn độ dài và tạo ID nội bộ |
| Chọn một parent tùy ý cho event fan-in | Mô hình nhân quả không phản ánh đủ đầu vào | Lưu nhiều causation reference và dùng span links |

## 14. Checklist cho hợp đồng sự kiện

- [ ] Mỗi event có event ID duy nhất và ổn định qua các lần redelivery.
- [ ] Correlation ID được tạo tại điểm bắt đầu workflow và giữ nguyên qua các bước của workflow đó.
- [ ] Causation ID trỏ đến command/event trực tiếp tạo ra event hiện tại.
- [ ] Event envelope có event type, schema version, occurred time và aggregate identity/version khi cần.
- [ ] Trace context được truyền bằng cơ chế propagation chuẩn qua HTTP và message transport.
- [ ] Correlation metadata nghiệp vụ được lưu bền vững, không phụ thuộc hoàn toàn vào trace backend.
- [ ] Retry, redrive và idempotency có quy tắc rõ ràng cho event ID và các attempt metadata.
- [ ] Fan-out giữ quan hệ nhân quả; fan-in lưu được nhiều nguyên nhân đầu vào.
- [ ] Log có correlation ID, causation ID, event ID và trace/span ID khi có sẵn.
- [ ] Metric không dùng ID có cardinality cao làm label.
- [ ] ID không chứa dữ liệu cá nhân, bí mật và không được dùng để cấp quyền.
- [ ] Có thể truy vấn event journal hoặc workflow history theo correlation ID và causation ID.

## 15. Kết luận

Correlation ID cho biết các hoạt động thuộc cùng một quy trình nghiệp vụ. Causation ID cho biết event hoặc command trực tiếp nào đã tạo ra thông điệp hiện tại. Event ID nhận diện một event cụ thể; trace ID và span ID liên kết các thao tác kỹ thuật; aggregate ID theo dõi đối tượng nghiệp vụ. Khi giữ đúng ý nghĩa của từng trường và truyền chúng qua HTTP, function, outbox, event bus, queue và consumer, nhóm phát triển có thể dựng lại chuỗi sự kiện, chẩn đoán retry, phát hiện workflow bị kẹt và đối chiếu lịch sử nghiệp vụ mà không phụ thuộc vào một function invocation đơn lẻ.
