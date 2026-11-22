# Correlation ID và truyền ngữ cảnh qua API, hàng đợi

Một yêu cầu nghiệp vụ trong hệ thống cloud hiếm khi được xử lý bởi một service duy nhất. Một request tạo booking có thể đi qua API gateway, booking service, inventory service, payment service, database, message broker và notification worker. Một phần công việc diễn ra đồng bộ qua HTTP/gRPC; phần còn lại tiếp tục bất đồng bộ qua queue hoặc event stream. Khi có lỗi, log của từng thành phần thường nằm ở nhiều nơi và được ghi tại những thời điểm khác nhau. Nếu không có cách liên kết chúng, đội vận hành khó xác định những log, trace và message nào thuộc cùng một hành trình nghiệp vụ.

**Correlation ID** là định danh được truyền qua các thành phần để liên kết những hoạt động có quan hệ với nhau. **Context propagation** là quá trình chuyển các thông tin ngữ cảnh cần thiết qua ranh giới process, service, protocol và message broker để các thành phần tiếp theo tiếp tục quan sát và xử lý đúng ngữ cảnh. Hai khái niệm hỗ trợ điều tra sự cố, theo dõi workflow, audit và đo latency end-to-end; chúng cũng phải được thiết kế cẩn thận để tránh giả mạo định danh, rò rỉ dữ liệu nhạy cảm hoặc làm tăng cardinality không kiểm soát.

Bài học thuộc chương **Khả năng quan sát** của lộ trình **Cloud Architecture**. Chương trình học cách thiết kế ứng dụng cloud từ yêu cầu nghiệp vụ đến mạng, compute, dữ liệu và mô hình triển khai, cân bằng độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Trong chủ đề này, mục tiêu là làm cho một hành trình qua nhiều service có thể truy vết và giải thích được mà vẫn giữ ranh giới tin cậy và semantics của từng giao thức.

Sau bài học, bạn có thể:

- Phân biệt correlation ID, request ID, trace ID, span ID, message ID và business ID.
- Thiết kế context contract cho HTTP/gRPC, message queue và event envelope.
- Propagate context qua synchronous call, fan-out, async workflow, retry và DLQ.
- Kết hợp correlation ID với distributed tracing và structured logging.
- Xác định trust boundary, tạo lại hoặc xác thực ID đến từ client.
- Truyền tenant context và causation metadata mà không lộ dữ liệu nhạy cảm.
- Xử lý batch, message redelivery, replay và workflow kéo dài.
- Đặt tiêu chuẩn kiểm thử và vận hành cho context propagation.

## 1. Correlation ID giải quyết vấn đề gì?

Giả sử khách hàng gửi yêu cầu tạo booking. API gateway ghi log nhận request, booking service ghi log tạo booking, inventory service ghi log giữ chỗ, payment service ghi log ủy quyền thanh toán và notification worker ghi log gửi email. Nếu mỗi log chỉ có timestamp và tên service, điều tra cần đối chiếu thời gian, payload và thông tin người dùng; việc này dễ sai khi nhiều request diễn ra đồng thời.

Nếu toàn bộ hoạt động chia sẻ một correlation ID, người vận hành có thể tìm theo ID và xem những thành phần đã xử lý hành trình đó.

~~~mermaid
flowchart LR
    C["Client request"] --> G["API Gateway"]
    G --> B["Booking service"]
    B --> I["Inventory service"]
    B --> P["Payment service"]
    B --> Q["Booking event queue"]
    Q --> N["Notification worker"]
    G -. "same correlation ID" .-> B
    B -. "same correlation ID" .-> I
    B -. "same correlation ID" .-> P
    Q -. "propagated context" .-> N
~~~

Correlation ID đặc biệt hữu ích khi:

- Một request đi qua nhiều service và nhiều runtime.
- Một thao tác tiếp tục sau khi HTTP response đã trả về.
- Một event được consumer xử lý sau vài giây hoặc vài giờ.
- Một nghiệp vụ phát sinh nhiều message hoặc retry.
- Một incident ảnh hưởng một nhóm request/tenant cụ thể.
- Cần liên kết audit record, application log và distributed trace.

Correlation ID giúp tìm các hoạt động liên quan, nhưng tự nó không ghi lại quan hệ cha-con giữa các bước và không thay thế trace/span.

## 2. Phân biệt các loại định danh

Các hệ thống thường dùng nhiều ID cùng lúc. Nếu đặt tất cả tên là requestId hoặc correlationId mà không có semantics, công cụ quan sát sẽ khó diễn giải.

| Loại ID | Phạm vi và mục đích | Hành vi thường gặp |
| --- | --- | --- |
| Correlation ID | Liên kết một hành trình hoặc nhóm hoạt động nghiệp vụ liên quan | Có thể được giữ qua nhiều service và message |
| Request ID | Định danh một lần nhận/xử lý request tại một boundary | Request mới thường có ID mới |
| Trace ID | Định danh một distributed trace gồm nhiều span | Giữ nguyên trong cùng trace; chuẩn tracing quy định format |
| Span ID | Định danh một operation/span trong trace | Mỗi span có ID riêng |
| Parent span ID | Chỉ span trực tiếp tạo ra span hiện tại | Xây quan hệ parent-child |
| Message ID | Định danh một message cụ thể | Giữ nguyên qua redelivery của cùng message |
| Causation ID | Chỉ command/event/message trực tiếp gây ra hoạt động hiện tại | Có thể là ID của message trước đó |
| Business ID | Định danh entity/nghiệp vụ như bookingId hoặc paymentId | Có lifecycle nghiệp vụ riêng |
| Idempotency key | Nhận diện các lần gửi lại cùng một thao tác để chống thực thi trùng | Được giữ qua retry theo contract |

Một ví dụ:

- Correlation ID: toàn bộ hành trình đặt thuê.
- Trace ID: một trace kỹ thuật thể hiện call graph có thể gồm gateway, booking và inventory.
- Request ID: một lần HTTP delivery tới booking API.
- Message ID: event BookingCreated được broker lưu.
- Causation ID: command CreateBooking đã dẫn tới event đó.
- Booking ID: đối tượng booking trong domain.

Một workflow kéo dài nhiều giờ hoặc ngày có thể bao gồm nhiều trace riêng nhưng vẫn có cùng correlation ID. Điều này giúp giữ liên kết nghiệp vụ khi trace được kết thúc hoặc bắt đầu lại ở một process khác.

## 3. Correlation ID không phải trace ID

Distributed tracing mô hình hóa operation thành trace và span, thường có parent-child relationship, timing, attributes và status. Correlation ID thường là khóa liên kết đơn giản ở tầng ứng dụng hoặc nghiệp vụ.

Hai loại ID có thể cùng tồn tại:

- Correlation ID trả lời: “Hoạt động này thuộc hành trình nào?”
- Trace ID trả lời: “Các operation kỹ thuật nào nằm trong trace này và liên hệ cha-con ra sao?”
- Span ID trả lời: “Operation cụ thể này là span nào?”

Ví dụ API nhận request, gọi inventory qua HTTP rồi publish event. Trace HTTP có thể kết thúc sau khi publish. Consumer chạy sau đó tiếp tục từ message context và tạo trace mới hoặc một span liên kết với trace producer. Correlation ID vẫn nối producer và consumer thành một hành trình nghiệp vụ.

### 3.1. Khi nào cần link thay vì parent-child?

Một message có thể được tạo từ nhiều hoạt động hoặc batch gồm nhiều message. Không phải lúc nào cũng có một parent span duy nhất. Tracing API có thể hỗ trợ span link để liên hệ với một hoặc nhiều span khác mà không ép chúng thành cây parent-child giả tạo.

Đối với một batch gồm hàng trăm message, một span xử lý batch có thể link tới các context gốc hoặc ghi các message ID trong metadata có giới hạn. Tránh nhồi danh sách không giới hạn vào span attributes.

## 4. Tạo Correlation ID ở đâu?

Correlation ID có thể đến từ client, gateway hoặc service đầu tiên hiểu được ranh giới hành trình. Cần thống nhất ai là nơi cấp phát và điều kiện nào cho phép tin ID từ bên ngoài.

### 4.1. Request từ Internet hoặc client không tin cậy

Một client có thể gửi header X-Correlation-ID. Giá trị đó hữu ích để hỗ trợ người dùng tìm request, nhưng không nên mặc nhiên coi là duy nhất, hợp lệ hoặc đáng tin. Client có thể cố tình reuse cùng ID, gửi chuỗi rất dài hoặc chứa ký tự gây lỗi log.

Một chính sách an toàn:

1. Gateway kiểm tra format, độ dài và charset cho header inbound.
2. Nếu giá trị hợp lệ và contract cho phép giữ lại, ghi nó như external correlation reference.
3. Gateway tạo ID nội bộ có entropy đủ cao cho hành trình được quản lý bởi platform.
4. Ghi mapping giữa external reference và internal correlation ID nếu cần hỗ trợ.
5. Các service nội bộ chỉ tin context do gateway/service identity đáng tin truyền.
6. Không dùng correlation ID để cấp quyền, xác định tenant hoặc xác thực caller.

Trong hệ thống nội bộ có caller đã được xác thực và trust contract rõ, có thể tiếp tục ID upstream. Nhưng ranh giới public ingress nên áp dụng validation và chống giả mạo.

### 4.2. Tạo ID

ID nên:

- Có độ dài và charset giới hạn.
- Có xác suất collision đủ thấp với quy mô hệ thống.
- Không chứa email, số điện thoại, tên khách hoặc dữ liệu định danh.
- Không mã hóa thông tin authorization hoặc tenant secret.
- Không chứa timestamp có độ phân giải quá chi tiết nếu không cần.
- Không được dùng thay security token hoặc idempotency mechanism.

UUID ngẫu nhiên hoặc ID ngẫu nhiên có entropy phù hợp thường là lựa chọn đơn giản. Không cần đưa toàn bộ thông tin nghiệp vụ vào ID vì thông tin đó có thể nằm trong log/trace fields được kiểm soát.

## 5. Context contract cho HTTP

Với HTTP, context thường được truyền qua request headers. Cần chuẩn hóa tên header, format, độ dài, trusted proxy behavior và cách xử lý khi header thiếu hoặc sai.

Ví dụ contract nội bộ:

~~~http
POST /v1/bookings
X-Correlation-ID: 01JCV8MZ6X2B7R6A0F5M6K8N2P
X-Request-ID: req-gateway-7f31
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
Content-Type: application/json
~~~

Header X-Correlation-ID ở đây là ví dụ riêng của ứng dụng. traceparent thuộc chuẩn W3C Trace Context và có grammar/semantics riêng; không tự tạo hoặc chỉnh sửa các trường của nó bằng quy tắc correlation ID.

### 5.1. Header allowlist

Không nên forward tất cả inbound headers tới mọi downstream service. Cần allowlist rõ những header được phép truyền, ví dụ:

- Correlation ID đã được gateway xác thực.
- W3C trace context theo tracing instrumentation.
- Tenant context đã được xác thực và có contract nội bộ.
- Locale hoặc request deadline nếu được hỗ trợ.
- Idempotency key chỉ tới operation cần semantics đó.

Không forward Authorization, Cookie, secret hoặc header nội bộ đặc quyền tới service không cần chúng. Proxy/gateway cần loại bỏ hoặc ghi đè header do client có thể giả mạo.

### 5.2. Gọi downstream

Khi booking service gọi inventory, nó giữ correlation ID của hành trình nhưng tạo request ID/span phù hợp cho lần gọi mới. Không copy cùng một request ID cho tất cả outbound calls vì request ID cần thể hiện boundary cụ thể.

## 6. W3C Trace Context và OpenTelemetry

W3C Trace Context định nghĩa header chuẩn để mang trace context giữa các hệ thống hỗ trợ tracing. Hai header thường gặp là:

- traceparent: mang version, trace ID, parent ID và trace flags theo grammar của chuẩn.
- tracestate: mang vendor-specific tracing state.

OpenTelemetry cung cấp API/SDK và instrumentation để tạo, trích xuất và inject trace context. Correlation ID nghiệp vụ có thể được ghi thành log field hoặc span attribute theo naming convention của tổ chức.

Không tự viết parser traceparent đơn giản rồi tin mọi giá trị inbound. Nên dùng tracing SDK/instrumentation đã được kiểm thử để validate, propagate và xử lý sampling flags.

### 6.1. Không biến baggage thành nơi chứa dữ liệu nhạy cảm

W3C Baggage có thể mang key-value context giữa service, nhưng nó được truyền xuyên nhiều boundary và có thể bị ghi log hoặc chuyển tới bên thứ ba. Không đặt password, access token, email, payment data hoặc PII vào baggage.

Chỉ truyền những metadata nhỏ, cần thiết và không nhạy cảm, ví dụ một routing hint hoặc context version đã được đánh giá. Giới hạn tổng kích thước và allowlist key/value.

## 7. Context contract cho gRPC

gRPC thường sử dụng metadata để truyền context cùng RPC. Interceptor ở client/server có thể inject/extract correlation ID và tracing context.

Các yêu cầu:

- Chuẩn hóa metadata key và charset theo gRPC.
- Giới hạn kích thước metadata.
- Dùng interceptor dùng chung thay vì để từng service tự triển khai.
- Propagate deadline/cancellation.
- Giữ trace context theo instrumentation hỗ trợ.
- Không truyền secret hoặc toàn bộ user token nếu downstream không cần.
- Validate tenant/user identity tại boundary có thẩm quyền.

Nếu một RPC tạo ra nhiều RPC downstream song song, tất cả có thể cùng correlation ID nhưng phải có span/request context riêng cho từng call.

## 8. Context trong message envelope

HTTP headers biến mất khi công việc chuyển thành message. Broker có thể hỗ trợ message headers/properties, nhưng một số hệ thống cũng cần một envelope chuẩn trong payload hoặc metadata layer.

Ví dụ envelope:

~~~json
{
  "messageId": "msg-92317",
  "messageType": "BookingCreated",
  "schemaVersion": 2,
  "occurredAt": "2026-11-18T05:20:00Z",
  "correlationId": "corr-7a92",
  "causationId": "cmd-81b3",
  "traceParent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
  "tenantRef": "tenant-482",
  "data": {
    "bookingId": "booking-1005"
  }
}
~~~

Ví dụ chỉ minh họa cấu trúc. Tenant reference chỉ được đưa vào message khi consumer cần và được phép. Không truyền PII, credential hoặc các claim quyền truy cập chỉ để thuận tiện cho logging.

### 8.1. Broker metadata và payload envelope

Nếu broker có message headers, có thể đặt correlation ID, traceparent, message ID và causation ID ở metadata. Payload giữ domain data. Cần chọn một nguồn sự thật rõ ràng và tránh trường hợp header nói correlation ID A trong khi payload nói ID B.

Một số event format tự mô tả có các trường tương ứng như id, type, source, subject, time và extensions. Khi dùng standard envelope, mapping với broker metadata phải được quy định để consumer không cần đoán.

## 9. Producer: tạo và inject context vào message

Producer nhận context từ request hiện tại, xử lý command và tạo event/message. Context cần được đưa vào outgoing message cùng với business payload và schema version.

~~~text
handle CreateBooking:
    context = currentRequestContext

    event = BookingCreated(
        messageId = newMessageId(),
        correlationId = context.correlationId,
        causationId = context.requestOrCommandId,
        traceContext = currentTraceContext,
        bookingId = result.bookingId
    )

    publish(event)
~~~

Đây là pseudocode khái niệm. Nếu producer ghi database và publish message, cần transactional outbox hoặc cơ chế tương đương để không có trường hợp transaction commit nhưng event bị mất. Context propagation không giải quyết atomicity giữa database và broker.

### 9.1. Giữ context khi publish bất đồng bộ

Một background job có thể chạy sau khi HTTP request đã kết thúc. Khi lưu job/outbox record, cần lưu context metadata được phép giữ lại để worker có thể tiếp tục liên kết. Không lưu cả request object hoặc Authorization header chỉ để dựng context sau này.

## 10. Consumer: extract context và tạo operation mới

Consumer đọc message, xác thực format và extract context theo contract. Nó tạo request/processing span mới và giữ correlation ID gốc.

~~~mermaid
sequenceDiagram
    participant P as Producer service
    participant Q as Message broker
    participant C as Consumer
    participant D as Downstream service

    P->>Q: Publish message + correlation/trace context
    Q-->>C: Deliver message
    C->>C: Extract and validate context
    C->>D: Call with propagated correlation and new span
    D-->>C: Response
    C->>Q: Ack after durable processing
~~~

Consumer cần phân biệt:

- Message ID: định danh message đang nhận.
- Delivery attempt: lần broker giao message hiện tại.
- Correlation ID: hành trình nghiệp vụ liên quan.
- Trace context: quan hệ quan sát giữa producer/consumer.
- Causation ID: nguyên nhân trực tiếp tạo message.

Nếu message thiếu context, consumer nên tạo một correlation ID mới theo policy và ghi rõ nguồn là legacy/missing context. Không được từ chối mọi message hợp lệ chỉ vì context thiếu nếu contract cho phép compatibility; đồng thời phải có metric để loại bỏ dần dữ liệu cũ.

## 11. Fan-out và fan-in

Một event có thể kích hoạt nhiều consumer: notification, analytics, audit và search indexing. Các consumer có thể chạy đồng thời, hoàn tất ở thời điểm khác nhau và phát sinh message con.

### 11.1. Fan-out

Các nhánh có thể giữ correlation ID gốc để liên kết cùng hành trình. Mỗi consumer có trace/span riêng; message con có message ID mới và causation ID trỏ tới event đã xử lý.

~~~mermaid
flowchart TB
    E["BookingCreated<br/>corr-123 / msg-1"] --> N["Notification consumer<br/>msg-2"]
    E --> A["Analytics consumer<br/>msg-3"]
    E --> S["Search consumer<br/>msg-4"]
    N --> M["Email delivery<br/>msg-5"]
~~~

Không nên coi một correlation ID là cách đếm số nhánh hoàn tất. Workflow cần trạng thái/aggregation riêng để xác định tất cả nhánh đã thành công hay timeout.

### 11.2. Fan-in

Khi nhiều nhánh tạo kết quả để một workflow tổng hợp, cần correlation ID để nhóm các hoạt động liên quan, nhưng phải có business key và expected participant set. Nếu chỉ group theo correlation ID, message trùng hoặc nhánh gửi sai có thể làm workflow kết thúc sớm hoặc chờ vô hạn.

## 12. Retry, redelivery và idempotency

Broker thường có thể giao cùng một message nhiều lần, ví dụ consumer xử lý thành công nhưng chết trước khi ack. Message redelivery vẫn có cùng message ID theo contract, nhưng delivery attempt khác nhau.

Khi retry một operation downstream:

- Giữ correlation ID của hành trình.
- Giữ business idempotency key nếu đó vẫn là cùng một command/side effect.
- Tạo attempt ID hoặc ghi attempt number riêng.
- Giữ message ID nguồn và causation ID.
- Không tạo correlation ID mới cho mỗi lần retry nếu muốn tìm toàn bộ lịch sử.
- Không dùng correlation ID để deduplicate; nó thường bao phủ nhiều message/operation.

~~~text
messageId = msg-92317
correlationId = corr-booking-1005
attempts:
    1 -> timeout
    2 -> transient database error
    3 -> processed and acknowledged
~~~

Idempotency phải được enforce tại consumer/business boundary bằng dedup store, unique constraint hoặc cơ chế phù hợp. Correlation metadata chỉ giúp quan sát lần retry nào thuộc hành trình nào.

## 13. Dead-letter queue và replay

Message vào dead-letter queue (DLQ) sau khi vượt chính sách retry hoặc không thể xử lý. Khi đưa message từ DLQ trở lại xử lý, cần giữ metadata gốc để không mất liên kết điều tra.

Một DLQ record nên giữ theo policy:

- Original message ID.
- Original correlation ID và causation ID.
- Trace context gốc nếu còn phù hợp.
- Source queue/topic và partition/offset nếu có.
- Failure reason/error category đã được sanitize.
- Attempt count, first/last delivery time.
- Replay operator/job ID và thời gian replay.
- Schema version và processing version.

Replay là một lần xử lý mới về mặt vận hành nhưng vẫn liên quan tới hành trình hoặc message gốc. Có thể tạo replay execution ID riêng, giữ original correlation ID và gắn replay causation metadata. Không thay message ID gốc nếu cần truy vết đúng bản ghi đã bị lỗi.

Trước khi replay cần xác nhận nguyên nhân đã được sửa, schema tương thích, consumer idempotent và side effect không lặp nguy hiểm. Correlation ID không tự biến replay thành an toàn.

## 14. Workflow dài hạn và Saga

Một saga hoặc process manager có thể kéo dài qua nhiều ngày. HTTP trace ban đầu không còn tồn tại khi bước tiếp theo chạy. Correlation ID có thể kết nối các event/command trong workflow, trong khi mỗi execution tạo trace mới.

Ví dụ booking cần giữ chỗ, thanh toán và chờ bàn giao:

1. CreateBooking command bắt đầu correlation.
2. BookingCreated tạo event.
3. ReservationRequested gửi tới inventory.
4. ReservationAccepted tạo bước tiếp theo.
5. PaymentRequested gọi payment provider.
6. PaymentAuthorized tiếp tục workflow.
7. BookingConfirmed hoàn tất.

Nếu payment thất bại, saga có thể gửi ReleaseReservation. Causation ID chỉ event/command trực tiếp tạo action bù trừ; correlation ID nối toàn bộ saga.

### 14.1. Correlation không thay thế workflow state

Để biết saga đang ở bước nào, cần lưu workflow state, timeout, retry count và participant status. Tìm log theo correlation ID giúp điều tra; nó không phải database trạng thái đáng tin cậy của saga.

## 15. Tenant context và authorization boundary

SaaS multi-tenant thường cần tenant reference để log và route message đúng tenant. Nhưng context metadata không tự chứng minh quyền truy cập.

Một message có tenantRef tenant-A vẫn có thể bị giả mạo nếu producer không đáng tin hoặc broker ACL sai. Consumer cần xác minh producer identity, topic/queue permission và resource ownership theo contract.

Nguyên tắc:

- Tenant identity được thiết lập tại authenticated boundary.
- Producer chỉ phát tenant context đã xác minh.
- Consumer kiểm tra nguồn message và policy trước khi truy cập resource.
- Correlation ID không được chứa tenant secret hoặc thông tin định danh trực tiếp.
- Tenant ID trong log được phân loại và mask/hash nếu policy yêu cầu.
- Cache key, idempotency scope và dedup key phải phù hợp tenant boundary.
- Không dùng correlation ID làm authorization token.

## 16. Bảo mật và giới hạn context

Context được truyền qua nhiều hệ thống, do đó có thể được ghi log, export, lưu trong broker hoặc chuyển tới third-party service. Một context contract cần xác định allowlist và data classification.

Không nên propagate:

- Password, API key, access token, refresh token hoặc private key.
- Authorization header/Cookie nguyên bản.
- Payment card data hoặc dữ liệu nhạy cảm không cần cho operation.
- Toàn bộ payload người dùng.
- PII chỉ để thuận tiện tìm kiếm.
- Internal privilege claim mà downstream không có cơ chế xác thực.

Nên propagate:

- Correlation ID ngẫu nhiên.
- Trace context chuẩn.
- Request/message/causation ID cần thiết.
- Tenant reference đã xác thực khi cần.
- Deadline hoặc locale được phép.
- Schema/context version.
- Operation type và source service.

### 16.1. Log injection và header abuse

Correlation ID từ client cần giới hạn độ dài, charset và format. Không đưa raw control character/newline vào log. Structured logger nên encode giá trị theo field, không ghép chuỗi tùy tiện.

Đối với header hoặc message metadata, đặt max size và reject/normalize theo contract. Một attacker gửi ID cực lớn hoặc hàng nghìn baggage entries có thể tăng CPU, memory và telemetry cost.

## 17. Structured logging

Mỗi log event nên là record có field rõ ràng, thay vì chỉ chứa text. Tối thiểu có thể gồm:

- timestamp.
- severity.
- service.name/service.version.
- environment/region/cell.
- correlation_id.
- request_id hoặc message_id khi phù hợp.
- trace_id và span_id nếu tracing đang active.
- operation/event name.
- status/error category.
- duration và retry attempt.
- tenant reference theo policy.

Ví dụ:

~~~json
{
  "timestamp": "2026-11-18T05:20:01.240Z",
  "severity": "ERROR",
  "service": "booking-service",
  "environment": "production",
  "correlation_id": "corr-7a92",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "message_id": "msg-92317",
  "operation": "reserve_inventory",
  "error_code": "DEPENDENCY_TIMEOUT",
  "attempt": 2
}
~~~

Ví dụ không có request body, token hoặc PII. Trường nên dùng tên nhất quán giữa service để log search, query và dashboard không cần mapping phức tạp.

### 17.1. Cardinality và chi phí

Correlation ID có cardinality rất cao vì mỗi hành trình thường có giá trị riêng. Đây là field phù hợp cho log/trace search, nhưng thường không phù hợp làm metric label/tag trong time-series metrics. Nếu mỗi ID tạo một time series, metric store có thể tăng cardinality và chi phí rất nhanh.

Metrics nên dùng dimension có tập giá trị giới hạn như service, operation, status class, region hoặc queue. Correlation ID dùng để drill down từ metric/alert sang log và trace.

## 18. Truyền context qua batch và scheduled jobs

Một batch job có thể xử lý nhiều record thuộc nhiều hành trình nghiệp vụ khác nhau. Không nên gán một correlation ID duy nhất cho cả batch rồi mất liên kết gốc của từng record.

Có thể dùng:

- Batch/job execution ID cho toàn lần chạy.
- Correlation ID gốc trên từng item nếu có.
- Parent job ID hoặc causation ID để ghi quan hệ.
- Trace link hoặc span theo batch/sub-batch.
- Item ID để xử lý lỗi và retry độc lập.

Ví dụ batch settlement xử lý 10.000 payment. Mỗi payment có correlation riêng; job execution ID liên kết tất cả với một lần chạy. Điều này hỗ trợ vừa tìm toàn bộ lần chạy vừa truy ra một payment cụ thể.

## 19. Context khi schedule và callback

Scheduled task có thể chạy sau khi request tạo lịch đã kết thúc. Cần quyết định correlation ID gắn với lần tạo schedule, lần chạy hay workflow dài hạn. Ba giá trị có thể khác nhau.

Ví dụ:

- Workflow correlation ID: giữ trong suốt vòng đời đặt thuê.
- Schedule ID: định danh lịch nhắc thanh toán.
- Job execution ID: định danh một lần worker thực thi lịch.
- Trace ID: trace mới cho lần execution.

Callback từ external provider cũng cần correlation/reference do provider trả về và ID nội bộ của operation. Không tin correlation header từ callback nếu chữ ký/webhook authentication chưa được xác minh. Xác thực nguồn trước rồi mới liên kết event với workflow.

## 20. Context propagation khi qua third-party

Không phải external provider nào cũng hỗ trợ custom header hoặc metadata. Nếu họ không giữ correlation ID, cần lưu mapping giữa provider request/reference ID và ID nội bộ.

Nguyên tắc:

- Chỉ gửi correlation reference nếu hợp đồng tích hợp cho phép.
- Không gửi trace baggage nội bộ hoặc tenant metadata không cần thiết.
- Ghi provider request ID/transaction reference khi có.
- Xác minh callback signature trước khi dùng reference.
- Lưu mapping có access control và retention rõ.
- Khi nhận callback, tạo trace mới và link tới operation gốc.
- Không giả định external provider sẽ propagate traceparent.

## 21. Context versioning và compatibility

Contract context có thể thay đổi theo thời gian: thêm causation ID, đổi naming, chuyển từ header sang envelope hoặc tích hợp tracing mới. Cần version hoặc quy tắc tương thích.

Khuyến nghị:

- Trường metadata mới nên optional trong giai đoạn đầu.
- Consumer phải xử lý trường thiếu theo policy.
- Producer chỉ phát version mới sau khi downstream tương thích.
- Unknown fields được xử lý theo schema/format contract.
- Không đổi ý nghĩa của correlation ID đang dùng.
- Có telemetry cho consumer legacy chưa hỗ trợ context.
- Version payload/event và version context nên được phân biệt nếu lifecycle khác nhau.

Khi migration từ X-Correlation-ID sang một header chuẩn nội bộ mới, có thể tạm đọc cả hai, phát một nguồn canonical và đo tỷ lệ client cũ trước khi bỏ alias.

## 22. Observability: từ metric tới log và trace

Correlation ID thường là điểm nối khi một alert hoặc metric chỉ ra hành vi bất thường.

Một workflow điều tra:

1. Dashboard cho thấy tỷ lệ booking timeout tăng.
2. Metric dimension chỉ ra booking operation ở region A.
3. Trace hiển thị booking service chờ inventory quá lâu.
4. Log search theo trace/correlation ID cho thấy các lần retry.
5. Tìm message ID trong queue telemetry để xác định event đang bị backlog.
6. Causation ID liên kết message với command ban đầu.
7. Business ID giúp kiểm tra trạng thái booking cuối cùng.
8. Reconciliation xác nhận thao tác đã commit hay chưa.

Không phải mọi request đều được trace do sampling. Correlation ID trong log có thể giúp tìm những operation không có trace đầy đủ, nhưng cần bảo đảm log retention và sampling policy phù hợp.

### 22.1. Sampling và correlation

Nếu trace producer bị sample out, consumer có thể nhận trace context với sampled flag tắt. Instrumentation cần tuân semantics tracing; không tự bật sampled flag chỉ vì correlation ID cần điều tra. Có thể giữ correlation ID trong log theo policy và dùng tail-based sampling/error-focused capture nếu hạ tầng hỗ trợ.

## 23. Kiểm thử context propagation

Context propagation cần được kiểm tra ở từng ranh giới, đặc biệt khi queue retry hoặc service dùng framework khác nhau.

- **HTTP contract test:** inbound ID thiếu/sai/quá dài được xử lý đúng; downstream nhận canonical ID.
- **gRPC interceptor test:** metadata inject/extract đúng và deadline được truyền.
- **Trace propagation test:** traceparent hợp lệ được tiếp tục, invalid context bị xử lý theo SDK policy.
- **Message envelope test:** context được serialize/deserialize không mất hoặc đổi ID.
- **Fan-out test:** nhánh giữ correlation chung nhưng message/request ID riêng.
- **Retry test:** correlation/message ID ổn định, attempt thay đổi và idempotency được enforce.
- **DLQ/replay test:** giữ original IDs và thêm replay metadata.
- **Tenant isolation test:** context không thể làm consumer truy cập tenant khác.
- **Security test:** token/PII không xuất hiện trong headers/log/baggage.
- **Batch test:** job ID và per-item correlation không bị trộn.
- **Legacy compatibility test:** message thiếu field được xử lý và đo lường.
- **Load/cardinality test:** ID dài hoặc metadata lớn không làm tăng tài nguyên bất thường.

## 24. Các lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách phòng tránh |
| --- | --- | --- |
| Mỗi service tự tạo correlation ID mới | Mất liên kết giữa các bước | Tạo/validate tại boundary và propagate canonical ID |
| Dùng correlation ID làm trace ID | Mất span relationship và tracing semantics | Giữ hai khái niệm riêng |
| Dùng correlation ID để deduplicate | Nhiều message hợp lệ cùng hành trình bị bỏ qua | Dùng message ID/idempotency key phù hợp |
| Tin header client mà không validate | ID giả, log injection hoặc collision có chủ ý | Validate, giới hạn và tạo internal ID tại ingress |
| Không propagate qua queue | Log consumer không liên hệ producer | Envelope/metadata contract và interceptor |
| Tạo ID mới mỗi lần retry | Khó gom các lần thất bại | Giữ correlation; tạo attempt ID riêng |
| Dùng một request ID cho mọi downstream call | Không phân biệt từng call boundary | Request/span ID mới cho operation con |
| Copy toàn bộ HTTP headers vào message | Lộ token/cookie và metadata thừa | Allowlist context fields |
| Đưa PII/secret vào baggage | Rò rỉ qua nhiều service/third party | Data minimization và classification |
| Dùng correlation ID làm metric label | Cardinality và cost tăng đột biến | Dùng ID ở logs/traces, metric dimension giới hạn |
| Chỉ dựa vào correlation để hiểu workflow | Không biết trạng thái/quan hệ cha-con đầy đủ | Trace span, causation và durable workflow state |
| Không giữ ID khi DLQ/replay | Mất lịch sử xử lý lỗi | Giữ original metadata và gắn replay execution ID |
| Tenant ID trong context được tin mù quáng | Cross-tenant data access | Authenticate producer và authorize consumer |
| Truyền context không có version | Consumer cũ parse sai hoặc bỏ metadata | Contract compatibility và rollout theo giai đoạn |
| Context quá lớn | Header/message size, memory và log cost tăng | Allowlist, size limit và chỉ truyền metadata cần thiết |

## 25. Quy trình thiết kế và triển khai

1. **Vẽ hành trình:** xác định request, service call, message, callback và job liên quan đến use case.
2. **Chọn semantics ID:** correlation, request, trace, span, message, causation, business và idempotency.
3. **Định nghĩa ingress policy:** ai cấp ID, validate header nào và boundary nào được tin.
4. **Chuẩn hóa HTTP/gRPC contract:** header/metadata, trace context, deadline và allowlist.
5. **Định nghĩa message envelope:** message ID, correlation, causation, trace context, schema version và tenant reference cần thiết.
6. **Triển khai middleware/interceptor:** inject/extract tập trung ở gateway, client, server, producer và consumer.
7. **Thiết kế async lifecycle:** fan-out, retry, DLQ, replay, scheduled job và saga.
8. **Bảo vệ trust boundary:** xác thực producer, tenant context, callback và loại bỏ secret/PII.
9. **Chuẩn hóa telemetry:** structured log fields, trace attributes và metrics dimension giới hạn.
10. **Kiểm thử:** contract, propagation, retry, batch, tenant isolation, security và load.
11. **Rollout:** đo tỷ lệ context thiếu, consumer legacy và propagation failure.
12. **Vận hành:** dashboard, search workflow, retention, ownership và runbook điều tra.

## 26. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi thiết kế |
| --- | --- |
| **Độ tin cậy** | Context có được giữ qua retry, queue, DLQ và replay? Thiếu context có làm workflow dừng sai? Có thể tìm lại operation sau incident? |
| **Bảo mật** | ID inbound có được validate? Tenant context có xác thực? Token/PII có bị propagate hoặc ghi log? |
| **Hiệu quả hiệu năng** | Header/envelope có giới hạn kích thước? Context lookup/cache có tạo latency? Metadata có làm message phình to? |
| **Tối ưu chi phí** | Correlation ID có bị đưa vào metric label gây cardinality? Log/trace retention và sampling phù hợp? |
| **Khả năng vận hành** | Field naming có nhất quán? Có dashboard, search, trace link, DLQ metadata và runbook? |

### Checklist nghiệm thu

- [ ] Phân biệt correlation ID, request ID, trace ID/span ID, message ID, causation ID và idempotency key.
- [ ] Có một canonical correlation ID cho hành trình và quy tắc tạo/validate tại ingress.
- [ ] HTTP/gRPC propagation có contract, allowlist và middleware/interceptor dùng chung.
- [ ] W3C trace context được SDK hỗ trợ; không tự parse/ghi đè sai semantics.
- [ ] Message envelope/metadata giữ correlation, message và causation ID.
- [ ] Fan-out giữ correlation chung nhưng định danh operation/message riêng.
- [ ] Retry giữ ID phù hợp và dùng idempotency cho side effect.
- [ ] DLQ/replay lưu metadata gốc và replay execution context.
- [ ] Workflow dài hạn có durable state; correlation không thay state machine.
- [ ] Tenant context được xác thực và authorization ở consumer.
- [ ] Không propagate token, secret hoặc PII không cần thiết.
- [ ] Log có field structured nhất quán; ID không dùng làm metric label.
- [ ] Header, baggage và envelope có giới hạn kích thước/cardinality.
- [ ] Context contract có version và tương thích message legacy.
- [ ] Có test HTTP, gRPC, queue, retry, batch, DLQ, replay và third-party callback.
- [ ] Có dashboard/alert cho missing context, propagation failure và trace/log correlation gap.

## 27. Bài tập áp dụng

Một nền tảng SaaS đặt thuê thiết bị nhận request tạo booking qua API gateway. Booking service gọi inventory đồng bộ, sau đó ghi database và phát BookingCreated vào broker. Ba consumer xử lý thông báo, analytics và audit. Notification worker gọi một nhà cung cấp email bên ngoài; broker có thể redeliver message và đưa message lỗi vào DLQ. Workflow đôi khi cần retry sau vài giờ.

Hãy thiết kế:

1. Những loại ID nào cần có và ai tạo từng loại?
2. Gateway xử lý X-Correlation-ID từ client thế nào để tránh giả mạo hoặc log injection?
3. Booking service truyền context qua HTTP/gRPC tới inventory ra sao?
4. Message envelope cần trường nào để consumer giữ correlation và causation?
5. Ba consumer fan-out dùng chung correlation ID hay trace ID? Vì sao?
6. Khi notification message redeliver, những ID/attempt nào giữ nguyên hoặc thay đổi?
7. DLQ replay sau vài giờ cần giữ original metadata và thêm replay metadata thế nào?
8. Tenant reference được xác thực ở producer và consumer ra sao?
9. Những trường nào tuyệt đối không đưa vào baggage, headers hoặc logs?
10. Làm thế nào điều tra từ metric booking timeout tới log, trace, message và trạng thái business cuối cùng?

Một thiết kế có cơ sở có thể tạo canonical correlation ID tại gateway; dùng tracing SDK để propagate traceparent; mỗi HTTP request/message có ID riêng; message con giữ correlation ID, đặt causation ID theo message gây ra nó; retry giữ message/idempotency semantics nhưng tăng attempt; DLQ giữ original context và thêm replay execution ID. Consumer vẫn xác thực producer/tenant và không dùng correlation ID để cấp quyền.

**Điểm cốt lõi:** correlation ID liên kết một hành trình nghiệp vụ qua nhiều thành phần; trace/span mô tả quan hệ và thời gian của operation kỹ thuật; message/request/idempotency ID có semantics riêng. Context propagation chỉ đáng tin khi có contract, validation, allowlist, middleware dùng chung và kiểm thử qua cả HTTP lẫn queue. Khi kết hợp structured logs, distributed traces và workflow state, đội vận hành có thể lần theo một hành trình mà không biến metadata quan sát thành một đường rò rỉ dữ liệu hoặc điểm yếu bảo mật.
