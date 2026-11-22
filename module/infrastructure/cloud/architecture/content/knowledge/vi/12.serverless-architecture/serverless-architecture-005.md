# Thiết kế API đồng bộ và xử lý sự kiện bất đồng bộ

## 1. Chọn đúng kiểu giao tiếp trong kiến trúc serverless

Trong kiến trúc serverless, một request thường đi qua API Gateway, function hoặc một dịch vụ managed; các sự kiện có thể được tiếp nhận bởi queue, event bus, stream hoặc workflow engine. Việc chọn giao tiếp **đồng bộ (synchronous)** hay **bất đồng bộ (asynchronous)** quyết định trải nghiệm người dùng, độ kết hợp giữa các thành phần, khả năng chịu lỗi, độ trễ, chi phí và độ phức tạp vận hành.

API đồng bộ phù hợp khi caller cần nhận kết quả để tiếp tục hành động ngay, ví dụ kiểm tra dữ liệu đầu vào, tra cứu trạng thái hoặc tạo yêu cầu đặt chỗ và nhận mã tiếp nhận. Caller chờ phản hồi trong giới hạn timeout của các lớp tham gia.

Xử lý sự kiện bất đồng bộ phù hợp khi công việc có thể hoàn tất sau request ban đầu, ví dụ gửi email, cập nhật chỉ mục tìm kiếm, phát hành hóa đơn hoặc đồng bộ dữ liệu tới hệ thống phân tích. Producer chuyển thông điệp/sự kiện cho cơ chế trung gian; consumer xử lý độc lập và có thể mở rộng theo backlog.

**Bất đồng bộ không có nghĩa là không cần phản hồi.** API vẫn nên xác nhận request đã được tiếp nhận, trả về mã công việc hoặc tài nguyên để caller tra cứu. **Đồng bộ cũng không có nghĩa mọi công việc phải nằm trong một function**: function có thể gọi dịch vụ khác đồng bộ, nhưng chuỗi phụ thuộc cần được giới hạn và đo lường.

Trong module **CLOUD_ARCHITECTURE**, quyết định này phải gắn với yêu cầu nghiệp vụ và đánh đổi giữa độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Không nên chọn event bus chỉ vì muốn “serverless hoàn toàn”, cũng không nên gọi tuần tự mọi dịch vụ nếu người dùng không cần chờ kết quả.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt API request/response đồng bộ với event/message bất đồng bộ.
2. Thiết kế đường API serverless có timeout, xác thực, giới hạn tải và phản hồi phù hợp.
3. Chọn queue, pub/sub, event bus hoặc workflow theo nhu cầu giao nhận và điều phối.
4. Xử lý giao nhận ít nhất một lần, duplicate, retry, dead-letter queue và idempotency.
5. Nhận diện khoảng trống dual-write và áp dụng transactional outbox hoặc mẫu tương đương.
6. Đánh giá tính nhất quán cuối cùng, quan sát, bảo mật và chi phí trong hệ thống sự kiện.

## 2. Hai mô hình giao tiếp và luồng điển hình

### 2.1. API đồng bộ: caller chờ phản hồi

Ví dụ khách hàng yêu cầu xem trạng thái đặt phòng:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant F as API Function
    participant D as Booking Store
    C->>G: GET /bookings/{id}
    G->>G: AuthN, quota, request validation
    G->>F: Invoke request
    F->>D: Read booking
    D-->>F: Booking status
    F-->>G: 200 + response
    G-->>C: HTTP response
~~~

Caller nhận kết quả trong cùng một chu kỳ request. Thành phần trung gian có thể xác thực, giới hạn tốc độ, định tuyến và biến đổi request. Function có thể scale theo tải, nhưng quota concurrency, thời gian thực thi, payload, network và giới hạn dịch vụ đều cần được xem xét.

### 2.2. Sự kiện bất đồng bộ: producer không chờ consumer hoàn tất

Ví dụ sau khi xác nhận booking, hệ thống cần gửi email và cập nhật analytics:

~~~mermaid
flowchart LR
    API["Booking API"] --> DB[("Booking DB + Outbox")]
    DB --> Relay["Outbox relay"]
    Relay --> Bus[["Event bus / Queue"]]
    Bus --> Mail["Notification consumer"]
    Bus --> Analytics["Analytics consumer"]
    Bus --> Search["Search index consumer"]
    Mail --> Provider["Email provider"]
~~~

Booking API có thể trả trạng thái đã xác nhận sau khi dữ liệu nghiệp vụ commit thành công. Công việc thông báo và cập nhật chỉ mục được xử lý sau. Mỗi consumer có nhịp scale, retry, quyền và vòng đời riêng.

### 2.3. So sánh nhanh

| Tiêu chí | API đồng bộ | Xử lý bất đồng bộ |
|---|---|---|
| Phản hồi caller | Kết quả trong cùng request | Thường trả accepted/job ID; kết quả cuối đến sau |
| Thời gian | Bị giới hạn bởi timeout tổng và timeout dependency | Có thể xử lý dài hơn; vẫn cần giới hạn thời gian/tuổi message |
| Phụ thuộc thời điểm | Caller thường phụ thuộc thành phần cần phản hồi | Producer tách khỏi thời điểm consumer chạy |
| Tải đột biến | Có thể dồn thẳng vào function/DB/dependency | Queue có thể hấp thụ đợt tăng rồi consumer xử lý theo năng lực |
| Giao dịch | Dễ phản ánh kết quả tức thời nhưng nhiều service call có thể tạo chuỗi mong manh | Thường có trạng thái trung gian và eventual consistency |
| Lỗi | Caller thấy lỗi trong request nếu được trả về kịp | Cần retry, DLQ, replay và quy trình tra cứu |
| Độ phức tạp | Quản lý timeout, retry, auth và dependency | Thêm schema event, duplicate, order, backlog và consumer lifecycle |
| Trải nghiệm | Hợp với hành động cần câu trả lời ngay | Hợp với tác vụ chấp nhận hoàn thành sau |

## 3. Thiết kế API đồng bộ cho workload serverless

### 3.1. Phân chia trách nhiệm ở API Gateway và function

Một luồng HTTP serverless thường có các lớp:

| Thành phần | Trách nhiệm thường gặp | Cần cẩn thận |
|---|---|---|
| DNS / edge | Tên miền, TLS entry, routing theo khu vực khi cần | Chứng chỉ, cache, DNS failover và vùng triển khai |
| API Gateway / HTTP front door | Auth integration, routing, quota/rate limit, request size, access logging | Gateway timeout, giới hạn payload, policy và chi phí theo request |
| Function / handler | Validation nghiệp vụ, điều phối ngắn, gọi dependency | Cold start, concurrency, giới hạn runtime, memory và network |
| Data/service dependency | Lưu trạng thái, kiểm tra quyền, thực hiện nghiệp vụ | Connection pool, transaction, rate limit, timeout |
| Observability | Metrics, logs, traces, correlation ID | Redaction dữ liệu, cardinality, sampling và retention |

Không nên nhồi toàn bộ logic nghiệp vụ vào cấu hình gateway. Gateway phù hợp với xác thực/ủy quyền ở tầng vào, định tuyến, giới hạn và một số biến đổi kỹ thuật. Quy tắc nghiệp vụ quan trọng phải được thực thi tại service sở hữu dữ liệu/hành vi.

### 3.2. Đặt timeout theo ngân sách toàn hành trình

Giả sử caller có ngân sách chờ tối đa 2 giây. Nếu gateway timeout là 2 giây, function timeout 10 giây, còn dependency timeout 8 giây, caller có thể đã bị gateway đóng kết nối trong khi function tiếp tục chạy. Điều này tạo **công việc mồ côi**, caller retry và có nguy cơ tác động trùng.

Thiết kế nên xác định:

1. **End-to-end deadline:** thời gian tối đa nghiệp vụ cho phép từ request đến response.
2. **Timeout từng dependency:** nhỏ hơn deadline còn lại, có ngân sách cho xử lý và serialization.
3. **Cancellation:** khi caller hủy hoặc deadline hết, xác định công việc có thể dừng hay cần hoàn tất/đối soát.
4. **Retry:** chỉ retry lỗi tạm thời, giới hạn số lần và tổng thời gian; dùng backoff/jitter.
5. **Idempotency:** với thao tác ghi, đảm bảo caller gửi lại cùng ý định không tạo hiệu ứng nghiệp vụ lặp.

Ví dụ phân bổ timeout minh họa:

| Lớp | Ngân sách |
|---|---:|
| Tổng hành trình từ client | 2.000 ms |
| Gateway/API front door | 1.800 ms |
| Function xử lý và response | 1.500 ms |
| Một dependency DB/API | 700 ms |
| Phần còn lại | Validation, serialization và dự phòng |

Các giá trị này không phải giới hạn mặc định của provider. Phải thiết kế từ SLO, phân vị latency p95/p99 và giới hạn thật của nền tảng.

### 3.3. Định nghĩa hợp đồng HTTP rõ ràng

Một API nên quy định:

- Method, path, schema request/response, versioning và trường bắt buộc.
- Mã HTTP và ý nghĩa lỗi; phân biệt lỗi validation, auth, conflict, throttling và dependency failure.
- Authentication/authorization, tenant scope và quyền truy cập tài nguyên.
- Idempotency key hoặc cơ chế tương đương cho thao tác tạo/thu tiền.
- Timeout, rate limit, payload limit, pagination và caching khi phù hợp.
- Correlation/request ID để nối gateway log, function log và dependency trace.

Ví dụ request tạo yêu cầu đặt chỗ:

~~~http
POST /v1/reservations
Authorization: Bearer <access-token>
Idempotency-Key: 83c2d6f0-3c64-4c8e-a4fd-4bdfb1a8c5c2
Content-Type: application/json

{
  "propertyId": "home-25",
  "checkIn": "2026-12-10",
  "checkOut": "2026-12-14",
  "guestCount": 2
}
~~~

Nếu thao tác hoàn tất đồng bộ trong ngân sách, API có thể trả 201 với resource được tạo. Nếu chỉ mới tiếp nhận một quy trình dài, API nên trả 202 Accepted với job/resource ID và đường dẫn kiểm tra trạng thái; không nên giả vờ đã hoàn tất nghiệp vụ.

Ví dụ phản hồi nhận yêu cầu xử lý bất đồng bộ:

~~~http
HTTP/1.1 202 Accepted
Location: /v1/operations/op-9f24
Content-Type: application/json

{
  "operationId": "op-9f24",
  "status": "ACCEPTED",
  "statusUrl": "/v1/operations/op-9f24"
}
~~~

API trạng thái cần định nghĩa thời hạn lưu, mức độ cập nhật, khả năng polling và quyền truy cập. Polling quá dày có thể tăng tải; có thể dùng webhook, callback có xác thực hoặc notification channel nếu sản phẩm phù hợp.

### 3.4. Bảo vệ API khi traffic tăng đột biến

- **Authentication và authorization:** xác thực caller, kiểm tra tenant/owner và scope. API Gateway xác thực token không thay thế kiểm tra quyền trên từng đối tượng.
- **Rate limiting / throttling:** theo client, API key, tenant hoặc operation; phản hồi 429 với hướng dẫn retry phù hợp khi bị giới hạn.
- **Concurrency control:** giới hạn function concurrency hoặc kết nối DB; scale function không có nghĩa DB scale vô hạn.
- **Payload validation:** giới hạn kích thước và schema; không tin dữ liệu client.
- **WAF / network policy:** bảo vệ điểm vào theo threat model; không thay thế logic nghiệp vụ.
- **Secrets:** lấy từ dịch vụ quản lý bí mật và workload identity; không đóng gói credential tĩnh trong image hoặc source.

## 4. Chọn queue, pub/sub, event bus hay workflow

Các mô hình bất đồng bộ có mục đích khác nhau.

| Mô hình | Cách hoạt động | Dùng khi | Cần chú ý |
|---|---|---|---|
| **Queue / work queue** | Message được phân phối cho một consumer/worker trong nhóm xử lý | Công việc cần được xử lý một lần về mặt nghiệp vụ dù có thể giao lại | Visibility timeout, ack/delete, retry, DLQ, competing consumers |
| **Pub/Sub** | Một thông điệp được phát tới nhiều subscription | Nhiều hệ thống cần nhận cùng thông tin | Mỗi subscription có backlog, retry và quyền độc lập |
| **Event bus** | Event được route theo rule tới target/consumer | Tích hợp nhiều domain/service, lọc theo event type/attribute | Schema, rule ownership, ordering và khả năng giao nhận theo provider |
| **Stream** | Dữ liệu có thứ tự/offset được lưu theo partition trong một khoảng thời gian | Nhiều record liên tục, replay, xử lý theo offset/window | Partition key, consumer lag, retention và throughput |
| **Workflow orchestration** | Trạng thái các bước được điều phối rõ ràng | Quy trình dài có nhánh, wait, retry, compensation | State transitions, timeout, chi phí mỗi bước và quyền |

Tên dịch vụ khác nhau theo cloud provider; không nên coi Queue, Event Bus và Stream có cùng semantics. Trước khi chọn, xác định yêu cầu **fan-out, ordering, retention, replay, throughput, delivery guarantee, latency, DLQ và chi phí**.

### 4.1. Chọn queue cho công việc cần xử lý

Ví dụ: worker gửi email nhận thông điệp SendReservationConfirmation. Queue hấp thụ tải đột biến; nhiều worker có thể xử lý song song. Consumer chỉ xác nhận/delete message sau khi kết quả được ghi nhận phù hợp. Nếu worker chết giữa xử lý, message có thể được giao lại.

### 4.2. Chọn pub/sub hoặc event bus cho nhiều consumer

Sự kiện ReservationConfirmed có thể được Notification, Loyalty và Analytics quan tâm. Producer phát một event theo hợp đồng; các consumer độc lập nhận theo subscription/rule. Một consumer chậm không nhất thiết chặn các consumer khác, tùy khả năng và cấu hình broker.

### 4.3. Chọn workflow cho quy trình nhiều bước

Ví dụ quy trình có các bước giữ chỗ, yêu cầu thanh toán, xác nhận và nếu thất bại thì giải phóng chỗ hoặc hoàn tiền. Một workflow engine có thể lưu trạng thái và điều phối retry/wait/branch. Tuy nhiên workflow không loại bỏ nhu cầu idempotency của activity và xử lý kết quả không chắc chắn từ external provider.

## 5. Thiết kế event contract và quyền sở hữu

### 5.1. Command khác event

- **Command:** yêu cầu một thành phần thực hiện hành động, thường có một owner có trách nhiệm xử lý. Ví dụ CreateReservation hoặc ChargePayment.
- **Event:** thông báo một việc đã xảy ra, ở thì quá khứ, có thể có nhiều consumer quan tâm. Ví dụ ReservationConfirmed hoặc PaymentCaptured.

Không nên phát event tên ReservationCreated khi thực tế reservation mới được yêu cầu và còn đang chờ payment. Tên event phải phản ánh trạng thái đã xảy ra và được commit theo quy tắc nghiệp vụ.

### 5.2. Một event nên chứa gì?

~~~json
{
  "eventId": "evt-84ce",
  "eventType": "reservation.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T03:00:00Z",
  "producer": "booking-service",
  "correlationId": "req-7ab2",
  "reservationId": "rs-1732",
  "propertyId": "home-25"
}
~~~

Một hợp đồng thường cần:

- **eventId:** định danh duy nhất để consumer phát hiện duplicate.
- **eventType và schemaVersion:** ý nghĩa và version schema.
- **occurredAt:** thời điểm nghiệp vụ xảy ra, không nhầm với thời gian consumer nhận.
- **producer/source:** thành phần phát event.
- **correlationId/causationId:** liên kết quy trình và nguyên nhân kích hoạt nếu hữu ích.
- **Business payload tối thiểu:** đủ cho consumer xử lý mà không sao chép dữ liệu nhạy cảm vô cớ.

Event là hợp đồng giữa các thành phần. Không công bố trực tiếp toàn bộ database row/entity nếu điều đó làm consumer phụ thuộc vào cấu trúc nội bộ. Schema tiến hóa nên có chiến lược tương thích ngược, kiểm tra consumer và thời gian loại bỏ version cũ.

### 5.3. Event không phải log

Log ghi lại điều đã xảy ra để chẩn đoán. Event là một hợp đồng tích hợp mà consumer có thể dùng để thay đổi trạng thái nghiệp vụ. Không nên dùng log text không cấu trúc làm message bus; cũng không nên nhồi mọi log kỹ thuật vào event nghiệp vụ.

## 6. Delivery semantics: at-most-once, at-least-once và exactly-once

Phải hiểu semantics của dịch vụ trung gian và hệ thống consumer trước khi hứa hẹn một event chỉ xử lý một lần.

| Semantics | Ý nghĩa khái quát | Hệ quả |
|---|---|---|
| **At-most-once** | Có thể mất thông điệp nhưng không giao lặp trong mô hình được xét | Phù hợp tín hiệu có thể bỏ qua; không phù hợp công việc quan trọng nếu không có cơ chế khác |
| **At-least-once** | Retry/giao lại để tăng khả năng nhận, có thể trùng | Consumer cần idempotency và deduplication |
| **Exactly-once** | Chỉ có thể phát biểu trong phạm vi cơ chế và transaction cụ thể | Không đồng nghĩa toàn bộ business side effect xuyên DB, broker và external API xảy ra đúng một lần |

Nhiều queue/serverless event integration hoạt động theo kiểu **at-least-once** hoặc có khả năng giao lại trong một số tình huống. Lỗi timeout có thể khiến producer/consumer không biết thao tác trước đã thành công hay chưa. Nếu consumer ghi DB xong nhưng chưa ack message, broker có thể gửi lại.

Vì vậy thực tiễn thường là **at-least-once delivery + idempotent processing**. Với external provider, cần dùng idempotency key nếu họ hỗ trợ, lưu trạng thái request/response và có quy trình đối soát trường hợp kết quả không rõ.

## 7. Idempotency: xử lý lặp nhưng không lặp hiệu ứng

Một thao tác idempotent có thể được thực hiện nhiều lần với cùng định danh yêu cầu mà kết quả nghiệp vụ không tạo hiệu ứng trùng ngoài ý muốn.

Ví dụ: consumer nhận ReservationConfirmed hai lần. Nếu chỉ gửi email mỗi lần nhận, khách hàng có thể nhận hai thư. Có thể dùng bảng deduplication theo eventId hoặc khóa nghiệp vụ phù hợp:

~~~sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Luồng logic:

1. Consumer bắt đầu transaction.
2. Thử ghi cặp consumer/eventId vào bảng processed_events.
3. Nếu khóa đã tồn tại, coi đây là duplicate đã xử lý và không lặp side effect.
4. Nếu mới, thực hiện cập nhật DB nghiệp vụ trong cùng transaction.
5. Commit trước khi ack message theo cơ chế broker.

Pseudocode minh họa:

~~~text
handle(message):
    begin transaction
    if insert_processed_event(consumer, message.eventId) conflicts:
        commit
        acknowledge(message)
        return

    apply_business_update(message)
    commit
    acknowledge(message)
~~~

Transaction trong ví dụ chỉ bao phủ DB do consumer kiểm soát. Nếu side effect là gọi email provider hoặc payment API, DB transaction không thể nguyên tử bao trùm mạng ngoài. Dùng idempotency key của provider, trạng thái operation, outbox hoặc đối soát; không tuyên bố exactly-once chỉ vì đã có bảng dedup.

Idempotency cần xác định **phạm vi và thời gian lưu khóa**. Nếu xóa processed-event record quá sớm trong khi broker có thể replay message cũ, thao tác trùng có thể quay lại.

## 8. Retry, backoff, visibility timeout và DLQ

### 8.1. Phân biệt lỗi tạm thời và lỗi không thể khắc phục

| Loại lỗi | Ví dụ | Xử lý thường gặp |
|---|---|---|
| Transient | Timeout mạng, 429, 5xx ngắn hạn, dependency quá tải | Retry có giới hạn và backoff/jitter |
| Permanent/business | Payload sai schema, tài khoản không hợp lệ, không có quyền nghiệp vụ | Không retry vô hạn; ghi nhận lỗi và xử lý theo hợp đồng |
| Unknown outcome | Provider đã xử lý nhưng response bị mất | Tra cứu bằng idempotency key hoặc reconciliation |
| Poison message | Một message luôn làm consumer crash hoặc parse thất bại | Cô lập, DLQ, điều tra và sửa consumer/schema |

### 8.2. Exponential backoff và jitter

Một chiến lược phổ biến là tăng dần thời gian chờ giữa các lần thử, thêm jitter để consumer không đồng loạt retry:

\[
delay_n = \min(maxDelay,\ baseDelay \times 2^n) + jitter
\]

Đây là công thức minh họa. Cần đặt max attempts, max elapsed time, giới hạn song song và chính sách theo loại lỗi. Retry đồng loạt không có jitter có thể tạo **thundering herd** và làm dependency quá tải kéo dài.

### 8.3. Visibility timeout / message lease

Với queue có cơ chế visibility timeout, message được ẩn trong thời gian consumer xử lý. Nếu consumer không ack/delete trước khi timeout, message có thể xuất hiện lại. Giá trị timeout nên đủ lớn cho thời gian xử lý hợp lệ nhưng không quá dài khiến message kẹt lâu khi worker chết.

Nếu xử lý dài hơn dự kiến, một số dịch vụ hỗ trợ gia hạn visibility/lease; phải cẩn trọng với worker bị treo hoặc retry. Visibility timeout không phải lock vĩnh viễn và không thay thế idempotency.

### 8.4. Dead-letter queue

Sau số lần nhận/thử lại hoặc điều kiện lỗi được định nghĩa, message có thể được chuyển tới **dead-letter queue (DLQ)**. DLQ giúp cô lập message không xử lý được để luồng chính tiếp tục, nhưng bản thân nó là một backlog cần quản trị:

- Alert theo số lượng message, tuổi message lâu nhất và tỷ lệ mới vào DLQ.
- Giữ nguyên event ID, source, error category, retry count và correlation ID.
- Chỉ replay sau khi đã sửa nguyên nhân và hiểu tác động duplicate/thứ tự.
- Có quy trình triage, redrive theo batch nhỏ, rate limit và quyền được phê duyệt.
- Thiết lập retention phù hợp; không để DLQ chứa dữ liệu nhạy cảm vô thời hạn.

**DLQ không phải nơi “ném lỗi đi”.** Nó cần owner, runbook, dashboard và quyết định nghiệp vụ cho message không thể xử lý tự động.

## 9. Vấn đề dual-write: commit DB và publish event

Một lỗi phổ biến trong event-driven system:

~~~text
1. Booking function ghi booking vào database.
2. Function publish ReservationConfirmed lên event bus.
~~~

Nếu bước 1 thành công nhưng function chết trước bước 2, booking đã được xác nhận nhưng consumer không nhận event. Nếu publish trước rồi transaction DB rollback, consumer lại nhận một sự kiện chưa có trạng thái nghiệp vụ tương ứng.

### 9.1. Transactional outbox

Outbox ghi thay đổi nghiệp vụ và event cần phát trong **cùng transaction của database**:

~~~sql
BEGIN;

UPDATE reservations
SET status = 'CONFIRMED'
WHERE reservation_id = 'rs-1732';

INSERT INTO outbox_events (
    event_id, event_type, payload, created_at, published_at
) VALUES (
    'evt-84ce',
    'reservation.confirmed',
    '{"reservationId":"rs-1732"}',
    CURRENT_TIMESTAMP,
    NULL
);

COMMIT;
~~~

Một publisher/relay đọc outbox chưa publish, gửi tới broker rồi đánh dấu kết quả theo chiến lược phù hợp. Nếu publisher chết sau publish nhưng trước cập nhật published_at, event có thể được gửi lại; consumer vẫn cần idempotency.

### 9.2. Các lựa chọn triển khai

| Cách làm | Khi phù hợp | Đánh đổi |
|---|---|---|
| **Transactional outbox + polling** | DB quan hệ, lưu lượng vừa, muốn kiểm soát đơn giản | Độ trễ poll, tải query và vận hành publisher |
| **Outbox + CDC** | Lưu lượng/event volume lớn, cần capture thay đổi liên tục | Thêm hạ tầng CDC, schema/offset và monitoring |
| **Provider integration/transaction feature** | Dịch vụ hỗ trợ phát event gắn chặt với transaction/stream | Phụ thuộc semantics và giới hạn của provider |
| **Dual-write trực tiếp** | Chỉ cho trường hợp có cơ chế chấp nhận mất/lặp được mô tả rõ | Có cửa sổ không nhất quán; thường không phù hợp nghiệp vụ quan trọng |

Serverless không tự làm dual-write an toàn. Một function chạy ngắn vẫn có thể bị timeout, retry, process termination hoặc lỗi mạng giữa hai side effect.

## 10. Quy trình dài: Saga và workflow orchestration

Khi quy trình nghiệp vụ trải qua nhiều dịch vụ và không thể dùng một transaction duy nhất, có thể dùng **Saga**: một chuỗi local transaction, mỗi bước có hành động bù trừ (compensating action) khi quy trình không thể tiếp tục.

Ví dụ đặt phòng:

~~~mermaid
flowchart TD
    Start["Yêu cầu đặt chỗ"] --> Hold["Giữ chỗ"]
    Hold --> Charge["Yêu cầu thanh toán"]
    Charge --> Paid{"Thanh toán thành công?"}
    Paid -->|Có| Confirm["Xác nhận booking"]
    Confirm --> Notify["Phát event xác nhận"]
    Notify --> Done["Hoàn tất"]
    Paid -->|Không| Release["Giải phóng chỗ"]
    Release --> Failed["Booking thất bại"]
    Confirm -->|Không thể xác nhận| Refund["Yêu cầu hoàn tiền"]
    Refund --> Compensated["Đối soát / bù trừ"]
~~~

Sơ đồ rút gọn chỉ để minh họa. Thực tế phải xác định trạng thái trung gian, timeout, kết quả thanh toán không rõ, retry, hành động bù trừ thất bại và cách nhân viên can thiệp.

### 10.1. Orchestration và choreography

- **Orchestration:** một workflow/state machine điều phối thứ tự, nhánh, wait, retry và compensation. Dễ quan sát tiến trình trung tâm, nhưng workflow trở thành thành phần cần quản trị và có thể chứa nhiều logic điều phối.
- **Choreography:** các service phản ứng với event của nhau mà không có một bộ điều phối trung tâm. Giảm điều phối trực tiếp nhưng luồng tổng thể khó nhìn, dễ tạo vòng event và khó xác định owner khi trạng thái lệch.

Quyết định dựa trên số bước, nhánh, thời gian chờ, khả năng đối soát và mức cần audit. Không cần Saga cho mọi API gọi qua hai dịch vụ; nếu nghiệp vụ có thể ở trong một transaction tại một ranh giới, hãy giữ đơn giản.

## 11. Kết hợp API đồng bộ và sự kiện bất đồng bộ

Một kiến trúc tốt thường dùng cả hai:

- Client gọi API đồng bộ để xác thực request, kiểm tra quyền, tiếp nhận yêu cầu và trả kết quả/operation ID.
- Thành phần sở hữu nghiệp vụ commit trạng thái và ghi outbox/event.
- Queue/event bus phân phối cho consumer.
- Consumer cập nhật read model, gửi thông báo hoặc thực hiện tác vụ phụ.
- Client đọc trạng thái qua API hoặc nhận callback được xác thực.

Ví dụ:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Booking API
    participant D as DB + Outbox
    participant B as Event Bus
    participant N as Notification
    participant S as Search Index
    C->>A: POST /reservations + idempotency key
    A->>D: Validate + write booking + outbox
    D-->>A: Commit
    A-->>C: 202 / 201 + operation URL
    D->>B: Relay ReservationConfirmed
    B-->>N: Deliver event
    B-->>S: Deliver event
    N->>N: Send confirmation (idempotent)
    S->>S: Update search read model
    C->>A: GET /operations/{id}
    A-->>C: Current business status
~~~

Trạng thái mà API trả về phải phản ánh rõ **đã tiếp nhận**, **đang xử lý** hay **đã xác nhận nghiệp vụ**. Không trả 201 nếu tài nguyên chỉ mới được xếp hàng mà chưa được tạo theo semantics API; có thể trả 202 và operation resource.

### 11.1. Eventual consistency và trải nghiệm

Sau khi booking được xác nhận, search index hoặc loyalty balance có thể cập nhật sau vài giây. UI cần biết dữ liệu đó có thể trễ. Các cách xử lý:

- Trả trạng thái operation và refresh theo khoảng có backoff.
- Hiển thị “đang xử lý” khi chưa có kết quả cuối.
- Đọc trạng thái từ source of truth cho hành động quan trọng, không dùng read model cũ để xác nhận giao dịch.
- Công bố mục tiêu độ trễ event-to-consumer nếu nghiệp vụ cần.
- Có cơ chế đối soát nếu consumer bị bỏ lỡ hoặc DLQ còn message lâu.

## 12. Bảo mật cho API và event-driven system

### API

- Xác thực danh tính caller; kiểm tra quyền trên từng resource/tenant.
- Dùng TLS cho giao tiếp và quản lý chứng chỉ phù hợp.
- Rate limit, schema validation, request size limit và WAF khi phù hợp.
- Không tin API key hoặc header do client tự gửi nếu chưa xác thực.
- Không log access token, secret, payment data hay toàn bộ payload nhạy cảm.
- Function dùng workload identity/role tối thiểu để truy cập DB, queue và secret.

### Queue, topic và event bus

- Producer chỉ có quyền publish loại event cần thiết; consumer chỉ subscribe topic/queue cần dùng.
- Phân tách quyền theo môi trường và trust domain; tránh một function role có thể đọc mọi queue.
- Mã hóa khi truyền và lưu; quản lý key theo yêu cầu dữ liệu.
- Kiểm soát schema registry/event catalog, quyền sửa rule và đăng ký consumer.
- Tránh payload nhạy cảm không cần thiết; dùng reference/token có kiểm soát nếu consumer cần lấy dữ liệu.
- Có audit cho thay đổi policy, queue subscription, redrive và replay.

Event bus là một bề mặt tích hợp. Một producer có thể vô tình phát dữ liệu cá nhân đến nhiều consumer hơn dự kiến; phải thiết kế data minimization và quyền subscribe từ đầu.

## 13. Quan sát và vận hành serverless

Một kiến trúc event-driven cần quan sát xuyên suốt từ request đến sự kiện và consumer, không chỉ xem function invocation count.

| Phạm vi | Metric/log cần theo dõi | Câu hỏi vận hành |
|---|---|---|
| API Gateway | Request count, 4xx/5xx, latency, throttling | Caller có nhận được response trong SLO? |
| Function | Invocation, error, duration, cold start khi có, concurrency, throttle | Có timeout hoặc bị giới hạn concurrency không? |
| Queue | Visible/in-flight messages, oldest message age, receive count | Consumer có xử lý kịp tốc độ producer? |
| Event bus | Matched/delivered/failed invocation, retry, rule failure | Event có route tới đúng target? |
| Consumer | Success/error, duration, idempotency duplicate count | Event có được xử lý đúng nghiệp vụ? |
| DLQ | Message count, age, error category, redrive | Có message bị bỏ quên cần owner xử lý? |
| Workflow | Execution state, duration, failed/timed-out steps | Quy trình bị kẹt ở bước nào? |
| Data/dependency | DB connection, throttling, lock, provider status | Bottleneck ở hệ dữ liệu hay downstream? |

### 13.1. Tracing qua ranh giới bất đồng bộ

Truyền **correlation ID/trace context** theo message attributes hoặc envelope để nối API request với event và các consumer. Không giả định mọi broker/SDK tự động giữ distributed trace context; cần tích hợp và kiểm tra end-to-end.

Một trace bất đồng bộ nên chỉ ra:

1. Request nào tạo event.
2. Event được commit/publish lúc nào.
3. Consumer nhận và bắt đầu xử lý lúc nào.
4. Các bước downstream và kết quả.
5. Event-to-consumer latency, số lần retry và trạng thái cuối.

### 13.2. Cảnh báo theo hành trình nghiệp vụ

Alert queue age tăng có ích nhưng cần liên hệ impact: thông báo xác nhận có đến chậm quá mức hay không; hoá đơn có được phát hành đúng hạn hay không? Đặt SLI/SLO cho cả request và quy trình async, ví dụ tỷ lệ event được xử lý trong ngưỡng thời gian, tỷ lệ operation hoàn tất, số lỗi DLQ.

Không đặt alert trên từng invocation thất bại nếu hệ thống retry có kiểm soát; thay vào đó theo dõi lỗi cuối cùng, backlog, tuổi message và business outcome.

## 14. Chi phí và hiệu năng

Serverless thường gắn chi phí với request/invocation, thời gian thực thi, memory/compute, data transfer, queue/event operations, log và workflow steps. Mô hình bất đồng bộ có thể hấp thụ peak và scale consumer theo backlog, nhưng cũng phát sinh:

- Queue/topic/event bus, storage và thao tác publish/receive/delete.
- Function invocation và thời gian consumer chạy lại do retry.
- DLQ, replay, event retention và observability.
- Network transfer giữa zone/region hoặc tới managed service.
- Log/trace volume và retention.
- Công xây dựng và trực pipeline vận hành, xử lý duplicate và reconciliation.

| Đòn bẩy thiết kế | Có thể cải thiện | Rủi ro/đánh đổi |
|---|---|---|
| Batch message | Giảm số lần invoke và chi phí theo record | Một batch lỗi có thể phải xác định record lỗi; latency tăng |
| Tuning concurrency | Bảo vệ DB và dependency | Backlog tăng nếu giới hạn quá thấp |
| Tuning memory/runtime | Giảm duration hoặc chi phí theo execution model | Memory tăng có thể tăng đơn giá; phải benchmark |
| Retry có giới hạn | Phục hồi lỗi tạm thời | Có thể nhân số lần tính phí và tải |
| Event filtering | Giảm invocation không cần thiết | Rule sai có thể bỏ mất event nghiệp vụ |
| Chọn region/placement | Giảm latency và cross-region traffic | Ràng buộc residency, availability và chi phí |
| Log sampling/retention | Kiểm soát chi phí quan sát | Có thể mất bằng chứng nếu giảm quá mức |

Đừng tối ưu chỉ số cost per invocation. Hãy đo **chi phí trên một giao dịch nghiệp vụ hoàn tất**, bao gồm retry, downstream, log, queue và phần lỗi phải xử lý thủ công.

## 15. Case study: xác nhận đặt phòng và gửi thông báo

**Bối cảnh:** nền tảng cho thuê chỗ ở nhận request đặt phòng qua API. Booking cần xác nhận chỗ, ghi dữ liệu, sau đó gửi email và cập nhật search index. Email provider đôi khi chậm; chiến dịch khuyến mại tạo tải đột biến.

### 15.1. Chọn đường đồng bộ

Các công việc thuộc critical path:

- Xác thực caller và quyền đặt trên tài sản.
- Kiểm tra báo giá/điều kiện hiệu lực.
- Bảo vệ bất biến không xác nhận trùng chỗ.
- Ghi trạng thái booking và trả kết quả/operation ID.

Không nhất thiết phải chờ trong request:

- Gửi email xác nhận.
- Cập nhật search index.
- Cập nhật analytics hoặc điểm thưởng nếu chính sách cho phép chậm.

### 15.2. Kiến trúc đề xuất

~~~mermaid
flowchart TD
    Client["Web / Mobile"] --> Gateway["API Gateway"]
    Gateway --> Function["Booking function"]
    Function --> DB[("Booking DB")]
    Function --> Outbox[("Outbox in same transaction")]
    Outbox --> Publisher["Outbox publisher"]
    Publisher --> Bus[["Event bus / Queue"]]
    Bus --> Email["Notification function"]
    Bus --> Index["Search index function"]
    Email --> Provider["Email provider"]
    Function --> Status["Operation/status API"]
~~~

*Đây là sơ đồ logic. Trong một triển khai, DB và outbox cần ghi trong cùng transaction; publisher có thể là function, scheduled worker hoặc CDC pipeline. API trạng thái có thể đọc cùng DB nghiệp vụ hoặc một read model phù hợp.*

### 15.3. Các trường hợp lỗi phải xử lý

| Tình huống | Hành vi mong muốn | Cơ chế |
|---|---|---|
| Client timeout rồi gửi lại cùng ý định | Không tạo booking trùng | Idempotency key được lưu bền vững và trả kết quả đã có |
| DB commit nhưng publisher chưa chạy | Event vẫn có thể được phát sau | Outbox relay và metric oldest unpublished event |
| Publisher gửi event nhưng chết trước khi đánh dấu published | Consumer có thể nhận duplicate | eventId và idempotent consumer |
| Email provider trả 429/5xx | Retry có giới hạn và backoff; không rollback booking hợp lệ | Queue retry policy, DLQ và alert |
| Search consumer bị lỗi schema | Booking vẫn giữ trạng thái nghiệp vụ đúng | Schema compatibility, DLQ, sửa consumer rồi replay |
| Queue backlog tăng | Bảo vệ consumer dependency, thông báo độ trễ | Concurrency limit, autoscaling theo backlog/age |
| Payment provider trả timeout không rõ kết quả | Không charge lại tùy tiện | Idempotency key phía provider và reconciliation |

### 15.4. Tiêu chí nghiệm thu

- Hai request đồng thời với cùng idempotency key không tạo hai booking.
- Email provider ngừng hoạt động không làm mất booking đã commit.
- Outbox không bị bỏ quên; event chưa publish lâu vượt ngưỡng có cảnh báo.
- Consumer nhận một event nhiều lần vẫn không tạo side effect trùng ngoài ý muốn.
- DLQ có owner, dashboard và quy trình replay có kiểm soát.
- Trạng thái API phân biệt accepted, processing, confirmed và failed theo nghiệp vụ.
- Event payload chỉ chứa dữ liệu cần thiết và consumer có quyền tối thiểu.
- Có dashboard đo request latency, event processing latency, backlog, lỗi cuối và chi phí/giao dịch.

## 16. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
|---|---|---|
| Dùng API đồng bộ cho toàn bộ bước phụ | Request dài, timeout và phụ thuộc lan truyền | Giữ critical path ngắn, chuyển tác vụ phụ sang async khi nghiệp vụ cho phép |
| Chuyển mọi thứ sang async | Caller không có kết quả rõ, trạng thái phân tán phức tạp | Chỉ async khi chấp nhận hoàn thành sau; cung cấp operation status |
| Nghĩ queue đảm bảo đúng một lần | Duplicate tạo charge/email/cập nhật lặp | Idempotency, dedup và reconciliation |
| Commit DB rồi publish trực tiếp | Có cửa sổ mất event hoặc publish sai trạng thái | Transactional outbox/CDC phù hợp |
| Retry vô hạn | Poison message, chi phí và tải tăng | Retry hữu hạn, backoff/jitter, DLQ |
| DLQ không có owner | Message tồn đọng, nghiệp vụ không bao giờ hoàn tất | Alert theo age/count, runbook và replay có kiểm soát |
| Event chứa toàn bộ database record | Coupling schema, rò dữ liệu và khó version | Payload theo business contract, data minimization |
| Không theo dõi consumer lag | API khỏe nhưng downstream tụt xa | Theo dõi tuổi message và event-to-effect latency |
| Tăng function concurrency vô hạn | DB/NAT/provider bị quá tải | Concurrency cap, queue buffer và load test |
| Hứa exactly-once xuyên toàn hệ thống | Sai kỳ vọng và khó đối soát | Nêu rõ semantics từng boundary và thiết kế hiệu ứng idempotent |

## 17. Checklist review API và event-driven design

### API đồng bộ

- [ ] Đường request có deadline và timeout hợp lý theo SLO.
- [ ] Có authentication, authorization theo resource/tenant, TLS và rate limit.
- [ ] Hợp đồng request/response, version và mã lỗi được định nghĩa.
- [ ] Thao tác ghi có idempotency khi caller có thể retry.
- [ ] Concurrency được giới hạn theo sức chịu của DB và dependency.
- [ ] Log/trace có request ID và không lộ secret/dữ liệu không cần thiết.
- [ ] Request dài được chuyển sang operation model thay vì giữ kết nối vô hạn.

### Event và consumer

- [ ] Chọn đúng queue/pub-sub/event bus/stream/workflow theo fan-out, order, replay và latency.
- [ ] Event có eventId, type, schema version, timestamp, source và payload tối thiểu.
- [ ] Producer/consumer có contract evolution và quyền publish/subscribe tối thiểu.
- [ ] Delivery semantics được hiểu; duplicate và idempotency được xử lý.
- [ ] Retry có giới hạn, backoff/jitter, visibility timeout/lease hợp lý và DLQ có owner.
- [ ] Khoảng trống DB commit–event publish được giải quyết bằng outbox/CDC hoặc cơ chế tương đương.
- [ ] Consumer có thể replay/đối soát mà không tạo side effect trùng.
- [ ] Backlog age, consumer lag, failed invocation và event-to-effect latency được quan sát.
- [ ] Payload/retention/log phù hợp yêu cầu bảo mật và chi phí.

### Quy trình nghiệp vụ

- [ ] Trạng thái accepted/processing/succeeded/failed có ý nghĩa rõ với người dùng.
- [ ] Timeout, kết quả không chắc chắn, compensation và human intervention được mô hình hóa.
- [ ] SLO và chi phí được đo theo nghiệp vụ hoàn tất, không chỉ invocation.
- [ ] Có runbook và người sở hữu cho DLQ, workflow bị kẹt và reconciliation.

## 18. Bài tập thực hành

**Bối cảnh:** Một nền tảng thuê chỗ ở nhận API đặt phòng. Sau khi giữ chỗ, hệ thống phải thu tiền, gửi email, cập nhật chỉ mục tìm kiếm và gửi dữ liệu cho hệ thống phân tích. Cổng thanh toán có thể mất vài giây hoặc trả timeout không rõ kết quả; email provider có lúc 429; chiến dịch quảng cáo làm tăng request gấp nhiều lần.

Hãy thiết kế một kiến trúc kết hợp đồng bộ và bất đồng bộ:

1. Chọn bước nào phải hoàn tất trước khi trả response, bước nào có thể chạy async. Giải thích theo quy tắc nghiệp vụ.
2. Định nghĩa hợp đồng API để caller có thể truy vấn trạng thái khi quy trình dài.
3. Chọn queue/event bus/workflow cho từng loại công việc; nêu lý do cần fan-out hay orchestration.
4. Đề xuất event schema cho ReservationConfirmed và PaymentCaptured; xác định dữ liệu nhạy cảm không nên đưa vào payload.
5. Thiết kế idempotency cho caller, consumer và payment provider.
6. Mô tả cách giải quyết DB commit–publish event bằng outbox/CDC.
7. Định nghĩa retry, backoff, DLQ, cảnh báo backlog và quy trình replay.
8. Đặt timeout/concurrency để bảo vệ DB, function và external provider.
9. Nêu SLI/SLO về API response, thời gian hoàn tất workflow, độ trễ email và tỷ lệ thanh toán thành công.
10. Phân tích chi phí, security boundary và cách khôi phục khi một consumer dừng hoạt động.

**Gợi ý tự kiểm tra:** API có thể xác nhận request hoặc trạng thái booking theo đúng semantics; thanh toán có thể cần một workflow có trạng thái và đối soát kết quả không rõ; email và analytics thường có thể bất đồng bộ. Không coi việc publish event là bằng chứng consumer đã xử lý. Hãy thử các tình huống function chết sau DB commit, message giao hai lần, consumer lỗi liên tục và provider đã thu tiền nhưng response bị mất.

## 19. Ghi nhớ

API đồng bộ phù hợp với tương tác cần câu trả lời ngay và phải có deadline, timeout, auth, rate limit và idempotency phù hợp. Xử lý bất đồng bộ phù hợp với công việc có thể hoàn thành sau, giúp tách thời điểm và hấp thụ tải, nhưng cần quản lý **event contract, delivery semantics, duplicate, retry, DLQ, eventual consistency và observability**.

Kiến trúc serverless tốt thường kết hợp cả hai: API tiếp nhận và phản hồi rõ trạng thái; sự kiện điều phối công việc sau commit; consumer xử lý độc lập và có khả năng phục hồi. Thiết kế phải bảo vệ bất biến nghiệp vụ, không để mất event ở khoảng trống dual-write, không tạo hiệu ứng trùng ngoài ý muốn và kiểm chứng bằng số liệu về trải nghiệm, độ tin cậy, bảo mật, hiệu năng và chi phí.
