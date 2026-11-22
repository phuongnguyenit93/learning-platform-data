# Thông điệp lỗi, hàng đợi lỗi và chính sách xử lý lại trong giao tiếp bất đồng bộ Microservices

> **Ngữ cảnh:** Software Design Architecture → System Architecture → Microservices → Giao tiếp bất đồng bộ.  
> **Mục tiêu:** Hiểu cách phát hiện và phân loại lỗi khi xử lý thông điệp, thiết kế retry có giới hạn, định tuyến bản tin không xử lý được vào Dead Letter Queue (DLQ), vận hành quy trình redrive an toàn, bảo đảm idempotency và quan sát được toàn bộ vòng đời xử lý.

## 1. Bài toán: một message không được xử lý thành công thì đi đâu?

Trong kiến trúc Microservices, một hành vi nghiệp vụ thường phát sinh sự kiện hoặc command bất đồng bộ:

~~~text
Ordering Service
  |
  | OrderSubmitted
  v
Message Broker / Topic
  |
  v
Inventory Consumer
  |
  +--> Inventory Database
  |
  +--> ReservationSucceeded / ReservationRejected
~~~

Consumer có thể xử lý message thành công, nhưng cũng có thể gặp các tình huống:

- Cơ sở dữ liệu tạm thời unavailable, connection pool cạn hoặc quá tải.
- Một HTTP dependency phản hồi timeout, 429 hoặc 503.
- Payload thiếu trường bắt buộc, sai kiểu, không tương thích schema.
- Message đúng schema nhưng vi phạm một quy tắc nghiệp vụ.
- Consumer có bug, code ném exception chưa xử lý.
- Cùng một message được gửi hoặc giao lại nhiều lần.
- Side effect đã được ghi nhận nhưng consumer chết trước khi xác nhận (ACK).
- Message quá hạn; xử lý hôm nay không còn đúng với ý định được phát ba ngày trước.
- Một message lỗi đứng đầu partition/queue làm kẹt các message phía sau.

Chỉ gọi **retry vô hạn** là không đủ. Retry có thể làm tăng tải lúc dependency yếu, giữ một message độc hại làm kẹt luồng, tạo hiệu ứng lặp và gây side effect trùng.

Ngược lại, **ACK ngay khi lỗi** sẽ làm mất message nếu chưa có cơ chế ghi lỗi bền vững. **Đưa mọi message lỗi vào DLQ** cũng không giải quyết nguyên nhân: DLQ sẽ tăng dần, các giao dịch nghiệp vụ bị treo mà không ai chịu trách nhiệm.

Thiết kế cần xác định **mỗi loại lỗi sẽ đi theo luồng xử lý nào, kết quả đã được ghi bền chưa, còn được retry đến khi nào, và ai quyết định xử lý lại hay kết thúc**.

## 2. Những thành phần và thuật ngữ chính

| Thuật ngữ | Ý nghĩa | Tác động |
|---|---|---|
| **Producer** | Dịch vụ phát event/command lên broker | Phải có contract và publish đáng tin cậy |
| **Broker** | Nơi lưu/chuyển message | Có cơ chế delivery, retention, ack/offset |
| **Consumer** | Dịch vụ nhận và xử lý message | Phải xử lý lỗi, trùng lặp và concurrency |
| **Message handler** | Logic của một loại message | Áp đúng business invariants |
| **ACK** | Xác nhận theo semantics broker rằng delivery đã xử lý/được chấp nhận | Có thể làm broker không giao lại delivery đó |
| **NACK/Reject** | Thông báo không xử lý delivery; hành vi tùy broker và cấu hình | Có thể requeue, dead-letter hoặc mất nếu cấu hình sai |
| **Retry** | Thử lại thao tác/message sau lỗi | Cần giới hạn và phân loại lỗi |
| **Backoff** | Khoảng chờ tăng dần giữa attempts | Giảm thác lũ retry |
| **Jitter** | Thành phần ngẫu nhiên trong thời gian chờ | Giảm retry đồng loạt |
| **DLQ / DLT** | Dead Letter Queue / Dead Letter Topic chứa message thất bại cần xử lý riêng | Cho phép cách ly và điều tra |
| **Redrive / Replay** | Chuyển message từ nơi cách ly/nhật ký về đường xử lý | Phải kiểm soát duplicate, ordering, business side effect |
| **Poison message** | Message mà consumer hiện tại liên tục không xử lý được | Có thể do dữ liệu, code, schema hoặc bug |
| **Idempotency** | Xử lý lặp cùng ý định không tạo side effect không mong muốn | Bắt buộc thực tế khi có redelivery |
| **Outbox** | Ghi sự kiện sẽ publish cùng transaction DB nghiệp vụ | Giảm cửa sổ mất event |
| **Inbox / Dedup** | Ghi nhận message đã xử lý/đang xử lý | Giúp chống xử lý trùng |
| **Visibility timeout / offset** | Cơ chế broker quản lý việc giao lại hoặc tiến độ đọc | Cần hiểu chính xác theo broker |

DLQ không phải một giao thức chung: RabbitMQ có queue và dead-letter exchange, Amazon SQS có redrive policy và DLQ, Apache Kafka thường triển khai dead-letter topic hoặc retry topics ở ứng dụng/framework. Đừng bê nguyên semantics ACK/NACK của hệ queue này sang hệ khác.

## 3. Vòng đời của một message

Một sơ đồ tham chiếu:

~~~text
Producer
   |
   | write business state + outbox (khi cần)
   v
Broker: Main Queue / Topic
   |
   v
Consumer receives message
   |
   +--> Parse + validate contract
   |
   +--> Deduplicate / check event version
   |
   +--> Execute business operation
   |        |
   |        +--> success --> commit state --> ACK / commit offset
   |
   +--> failure
            |
            v
      Classify failure
            |
            +--> transient --> bounded retry with delay
            |
            +--> permanent --> DLQ / rejection workflow
            |
            +--> unknown outcome --> lookup / reconcile
            |
            +--> exhausted --> DLQ / alert / owner action

DLQ / quarantine
   |
   +--> investigate + repair cause
   |
   +--> controlled redrive / compensate / discard with reason
~~~

Đây là mô hình logic, không khẳng định mọi broker có native retry queue, delayed delivery hoặc dead-letter tự động. Nhiều hệ thống cần cấu hình exchange/topic, scheduled task hoặc một bộ xử lý lỗi riêng.

### Phân biệt xử lý lỗi và bảo đảm giao nhận

Một consumer có thể:

1. Xử lý thành công và ACK.
2. Xử lý thất bại và không ACK để broker giao lại.
3. Ghi bền message vào nơi retry/DLQ rồi ACK delivery gốc.
4. Reject/NACK với policy dead-letter của broker.
5. Bỏ message không cần xử lý nữa khi business contract quy định rõ và đã audit.

Trong lựa chọn 3, tính an toàn phụ thuộc việc ghi bền ở destination và xác nhận của broker. Nếu ACK nguồn trước khi publish retry/DLQ thành công, message có thể mất. Nếu publish thành công rồi ACK nguồn bị lỗi, message có thể xuất hiện ở cả hai nơi; consumer phải chịu được duplicate. Hệ thống thường cần **at-least-once + idempotency** hoặc hạ tầng transaction tương ứng.

## 4. Phân loại lỗi trước khi thiết kế retry

| Loại lỗi | Ví dụ | Cách xử lý thường hợp lý |
|---|---|---|
| **Transient infrastructure** | DB restart, kết nối timeout ngắn | Retry có delay và giới hạn |
| **Rate limit / overload** | HTTP 429, 503, broker throttling | Retry có backoff, tôn trọng hạn mức |
| **Temporary business dependency** | Inventory chờ dữ liệu đồng bộ đến | Retry có điều kiện, timeout theo nghiệp vụ |
| **Permanent schema/data** | Payload JSON không parse được, thiếu field quan trọng | Không retry nhanh; cách ly, sửa producer/consumer |
| **Permanent business rejection** | SKU không được phép, order đã hủy | Ghi outcome/rejection hợp đồng, thường không retry |
| **Unsupported version** | Consumer không hiểu eventVersion=99 | Quarantine, cập nhật contract hoặc chuyển đổi |
| **Programming defect** | NullPointerException do bug | Cách ly nếu lặp, phát alert, triển khai fix rồi redrive |
| **Unknown side effect** | Payment đã xử lý nhưng response mất | Tra cứu trạng thái/idempotency/reconciliation |
| **Expired/stale message** | Coupon đã hết hạn, reservation quá thời hạn | Kiểm tra rule hiện tại, kết thúc/compensate theo policy |
| **Poison by resource exhaustion** | Payload cực lớn gây OOM hoặc parse đắt | Quarantine, giới hạn kích thước, bảo vệ consumer |

**Transient** nghĩa là có khả năng khắc phục nếu chờ, không phải chắc chắn sẽ thành công. **Permanent** nghĩa là retry cùng payload trong cùng điều kiện không có triển vọng; cần thay đổi dữ liệu, code, phiên bản hoặc quyết định nghiệp vụ.

Không nên chỉ dựa trên HTTP status của một dependency: một 404 có thể là dữ liệu chưa đồng bộ tạm thời trong một workflow, nhưng cũng có thể là mã tài nguyên không tồn tại vĩnh viễn. Contract mới cho biết retry hay reject.

### Lỗi nghiệp vụ không đồng nghĩa lỗi kỹ thuật

Nếu Inventory nhận ReserveStock nhưng không đủ tồn, đó có thể là một kết quả **ReservationRejected** hợp lệ. Consumer nên ghi kết quả nghiệp vụ và ACK delivery, thay vì đẩy command này vào DLQ như sự cố hệ thống. Nếu hợp đồng quy định chờ nhập hàng một thời gian, có thể chuyển sang trạng thái chờ và retry **theo chính sách nghiệp vụ**, chứ không retry vô hạn vì exception.

## 5. Thiết kế envelope để điều tra và xử lý lại

Một message cần đủ thông tin ổn định để xác minh danh tính, schema, mục đích và vòng đời mà không phải phụ thuộc vào trạng thái UI hay log cũ.

Ví dụ event envelope:

~~~json
{
  "messageId": "evt-f68db65f",
  "eventType": "OrderSubmitted",
  "eventVersion": 2,
  "producer": "ordering-service",
  "occurredAt": "2026-11-11T14:00:00Z",
  "aggregateId": "ord-2048",
  "aggregateVersion": 7,
  "correlationId": "journey-18ab",
  "causationId": "cmd-submit-2048",
  "tenantId": "tenant-47",
  "payload": {
    "orderId": "ord-2048",
    "items": [
      {"sku": "book-21", "quantity": 2}
    ]
  }
}
~~~

Ý nghĩa một số trường:

- **messageId/eventId:** định danh message duy nhất giúp dedup và audit.
- **eventType/version:** xác định contract và hướng xử lý.
- **aggregateId/version:** hỗ trợ kiểm tra ordering, cập nhật trạng thái và idempotency theo đối tượng.
- **correlationId/causationId:** nối sự kiện với hành trình hay command phát sinh.
- **occurredAt:** đánh giá freshness, TTL và thời gian chờ.
- **tenantId:** xác định phạm vi quyền; phải được kiểm tra theo nguồn đáng tin.
- **payload:** dữ liệu nghiệp vụ tối thiểu; tránh thông tin nhạy cảm không cần thiết.

Đừng tùy tiện dùng **messageId mới** khi retry cùng một event nếu hệ thống dedup dựa vào messageId gốc. Nếu tạo một retry delivery mới, nên bảo lưu **originalMessageId**, đồng thời có retryDeliveryId riêng nếu cần kiểm toán.

### Metadata dành cho retry

Một bản tin đưa vào retry hoặc DLQ có thể có:

~~~json
{
  "originalMessageId": "evt-f68db65f",
  "failureId": "fail-809",
  "sourceTopic": "orders.submitted.v2",
  "sourcePartition": 4,
  "sourceOffset": 2917,
  "consumerGroup": "inventory-reservation",
  "firstFailureAt": "2026-11-11T14:01:02Z",
  "lastFailureAt": "2026-11-11T14:03:21Z",
  "attempts": 4,
  "lastErrorCode": "INVENTORY_DB_UNAVAILABLE",
  "nextEligibleAt": "2026-11-11T14:08:21Z",
  "redriveCount": 0,
  "payloadReference": "original-message-preserved"
}
~~~

Đây là **schema minh họa**, không phải định dạng tự động của tất cả broker. Kafka offset không áp dụng cho SQS; RabbitMQ có delivery metadata khác. Các trường có thể nằm ở headers, body wrapper hoặc database quarantine do ứng dụng sở hữu.

Đặc biệt: **giữ nguyên nội dung message gốc** để điều tra, không chỉ giữ exception message. Tuy nhiên không ghi payload nhạy cảm vào log hoặc DLQ không có mã hóa/phân quyền phù hợp.

## 6. ACK, NACK, offset và thời điểm commit an toàn

### Quy tắc nền tảng

**Chỉ xác nhận một message đã được xử lý khi kết quả đã được ghi bền ở nơi tương ứng.** Kết quả có thể là state nghiệp vụ thành công, trạng thái từ chối hợp lệ, hoặc bản ghi chuyển sang nơi retry/DLQ được xác nhận an toàn.

Sai lầm phổ biến:

~~~text
receive message
ACK ngay
run database transaction
database throws exception
--> message đã ACK và có thể mất nghiệp vụ
~~~

Một quy trình phù hợp hơn:

~~~text
receive
validate
process in transaction / record durable outcome
commit
ACK / commit offset
~~~

Dù vậy, transaction DB và ACK broker thường **không atomic**: DB có thể commit thành công rồi consumer chết trước ACK. Broker giao lại message và duplicate là bình thường. Cần idempotency.

### RabbitMQ

RabbitMQ có consumer acknowledgement và reject/nack đối với delivery. Tùy cấu hình, **requeue=true** có thể đưa message trở lại queue, còn reject/nack với **requeue=false** có thể dead-letter nếu queue được cấu hình DLX; nếu không có đường đích hợp lệ, message có nguy cơ bị bỏ.

Không lập vòng requeue tức thì không giới hạn cho message độc hại. Một lựa chọn là delayed retry queue có TTL + dead-letter route trở lại main queue, hoặc cơ chế scheduling khác; phải quản lý attempt count, hop count và bảo đảm không có vòng lặp vô hạn.

### Amazon SQS

SQS dùng **visibility timeout**: message đang xử lý tạm ẩn khỏi các consumer khác. Nếu chưa xóa message sau xử lý thành công, message có thể hiển thị lại khi thời gian ẩn hết hạn. Cần quản lý DeleteMessage đúng lúc và visibility phù hợp thời gian xử lý; tác vụ dài có thể cần gia hạn visibility theo policy.

SQS có **redrive policy/maxReceiveCount** để chuyển message sang DLQ khi vượt ngưỡng nhận lại. Số lượt receive không đồng nghĩa số lần business handler thật sự đã thực thi thành công hay số lần toàn bộ workflow bị thử lại; cần telemetry riêng.

### Apache Kafka

Kafka dùng **offset và consumer group**. Không có một ACK/NACK từng record giống RabbitMQ. Commit offset nghĩa là ghi nhận tiến độ tiêu thụ, còn các record vẫn ở Kafka cho đến khi hết retention. Nếu record lỗi và ứng dụng vẫn commit qua nó mà chưa ghi outcome/retry/DLT bền vững, consumer group có thể bỏ lỡ việc xử lý.

Một chiến lược là **block partition** đến khi xử lý xong, hoặc publish record sang retry/DLT rồi commit tiến độ theo cơ chế tin cậy. Kafka transaction có thể phối hợp consume–produce trong Kafka, nhưng **không tự bảo đảm exactly-once với database hay HTTP provider ngoài Kafka**.

## 7. Chọn mô hình retry

Có ba nhóm cách triển khai:

| Mô hình | Cách hoạt động | Phù hợp | Rủi ro |
|---|---|---|---|
| **Immediate in-process retry** | Handler thử lại nhanh trong cùng delivery | Lỗi rất ngắn, ít lần | Giữ thread, giữ partition, retry storm |
| **Delayed broker retry** | Đưa message sang queue/topic delay rồi giao lại | Retry sau vài giây/phút | Phải đảm bảo publish, không lặp vô hạn |
| **Scheduled retry store** | Ghi trạng thái lỗi và nextAttemptAt trong DB/job | Workflow dài, rule phức tạp, phụ thuộc kinh doanh | Cần vận hành scheduler và state machine |
| **Manual redrive từ DLQ** | Con người/hệ thống được quyền chọn message để xử lý lại | Poison hoặc lỗi cần fix | Rủi ro phát lại hàng loạt, đổi trạng thái hiện tại |

Một kiến trúc có thể dùng các tầng:

~~~text
Main Topic / Queue
    |
    v
Handler
    |
    +--> success ------------------> ACK
    |
    +--> transient, attempt 1 -----> Retry short delay
    |                                  |
    |                                  +--> Main/Retry Consumer
    |
    +--> transient, attempt 2 -----> Retry longer delay
    |
    +--> permanent / exhausted ----> DLQ
                                       |
                                       v
                                 Investigation
                                       |
                            +----------+----------+
                            |                     |
                         Fix + redrive         Compensate/close
~~~

Không bắt buộc phải có đúng hai tầng retry; chính sách nên tính theo độ trễ có thể chấp nhận, tổng tuổi message, năng lực hệ thống và rủi ro nghiệp vụ.

### Retry không phải luôn “trả message về main queue”

Khi có nhiều message theo cùng aggregate, việc đưa một message thất bại ra retry rồi tiếp tục các message sau có thể làm đảo thứ tự. Ví dụ OrderSubmitted chưa xử lý nhưng OrderCancelled đến sau được xử lý trước. Trong một số workflow, hệ thống phải **chặn tiến độ của partition/key** hoặc có cơ chế sequence/version để bảo vệ tính đúng đắn.

## 8. Exponential backoff, jitter và giới hạn attempts

Một chính sách minh họa:

\[
d_k = \min(d_{\max}, d_0 \times 2^{k-1})
\]

với \(d_0\) là khoảng chờ đầu, \(d_{\max}\) là giới hạn, k là số lần retry. Để tránh hàng nghìn consumer retry cùng lúc, dùng jitter ngẫu nhiên trong một khoảng hợp lệ.

Ví dụ **full jitter** chọn thời gian chờ ngẫu nhiên trong \([0,d_k]\). Nếu muốn tránh retry quá sớm, có thể chọn biến thể jitter có lower bound. Quan trọng là **thực hiện policy rõ ràng và đo hành vi**, không chỉ gọi tên “exponential”.

Một dãy backoff tối đa minh họa:

| Attempt xử lý | Delay trước attempt kế tiếp (giới hạn) |
|---:|---:|
| 1 | Tối đa 2 giây |
| 2 | Tối đa 4 giây |
| 3 | Tối đa 8 giây |
| 4 | Tối đa 16 giây |
| 5 | Tối đa 30 giây |
| 6 | Chuyển DLQ/đường xử lý khác |

Với jitter, delay thực tế có thể nhỏ hơn mức tối đa. Tùy yêu cầu, một sự cố lâu có thể cần các cấp retry phút/giờ, nhưng mỗi mức phải tính tác động backlog và message age.

### Retry budget là nhiều giới hạn đồng thời

Một policy thực tế nên ràng buộc:

- **maxAttempts:** tổng số lần được phép xử lý, định nghĩa rõ có tính lần đầu hay không.
- **maxElapsedSinceFirstAttempt:** tổng thời gian kể từ lần thử đầu.
- **messageExpiresAt / business deadline:** sau mốc nào hành vi trở nên vô nghĩa hoặc không an toàn.
- **per-attempt timeout:** một attempt không được treo vô hạn.
- **retryable error set:** chỉ những lỗi được contract phân loại có khả năng phục hồi.
- **retry rate/concurrency budget:** giới hạn lưu lượng retry so với lưu lượng mới.
- **maxRedriveCount:** số lần một message đã rời DLQ để thử lại.
- **circuit-breaker/overload policy:** ngừng tăng tải khi dependency vẫn chưa phục hồi.

Nếu reached maxAttempts nhưng hệ thống đã sửa được lỗi trước đó, không nhất thiết tự động redrive mọi DLQ ngay. Cần quyết định theo nghiệp vụ, trạng thái hiện tại và kiểm tra idempotency.

## 9. Phân loại retryable và permanent từ mã lỗi

Một bảng mapping có thể được dùng trong handler:

| Nguyên nhân | Code nội bộ | Retry tự động | Ghi chú |
|---|---|---|---|
| DB timeout thoáng qua | DB_TIMEOUT | Có, có giới hạn | Backoff và circuit breaker |
| DB unique constraint do duplicate event | DUPLICATE_EVENT | Thường không cần | Nếu đã xử lý thành công, ACK theo idempotency |
| HTTP 429 downstream | RATE_LIMITED | Có điều kiện | Tôn trọng Retry-After/capacity |
| HTTP 503 downstream | DEPENDENCY_UNAVAILABLE | Có điều kiện | Đánh giá thời hạn nghiệp vụ |
| JSON không parse | MESSAGE_MALFORMED | Không | Cách ly, kiểm tra producer |
| Event version không hỗ trợ | UNSUPPORTED_EVENT_VERSION | Không | Cần nâng consumer/biến đổi có kiểm soát |
| Order đã CANCELLED | ORDER_STATE_CONFLICT | Không hoặc workflow riêng | Outcome nghiệp vụ |
| Tồn kho không đủ | STOCK_UNAVAILABLE | Theo business policy | Có thể rejection hợp lệ |
| Lỗi NullPointerException | HANDLER_BUG | Không retry nhanh vô hạn | Alert, fix, redrive |
| Provider timeout sau side effect | OUTCOME_UNKNOWN | Không retry mù | Lookup/reconciliation |
| Message quá TTL | MESSAGE_EXPIRED | Không | Audit/compensate theo hợp đồng |

Đây là phân loại **theo semantics của service**, không phải danh sách cố định cho mọi hệ thống. Ví dụ 404 từ read model có thể là tạm thời vì projection lag, nhưng 404 từ canonical entity được xác nhận không tồn tại có thể là permanent. Không dùng mã HTTP đơn lẻ thay thế hiểu biết domain.

### Error taxonomy cho message

Khác với HTTP response gửi client, lỗi message có thể được lưu trong record nội bộ hoặc DLQ metadata:

- **failureCode:** mã máy ổn định.
- **failureCategory:** TRANSIENT, PERMANENT, BUSINESS, UNKNOWN, EXPIRED.
- **detectedAt / firstSeenAt:** thời điểm.
- **attempts, lastAttemptAt, nextEligibleAt:** lịch xử lý.
- **consumerName/version:** xác định bản code xử lý lỗi.
- **originalMessageId, correlationId:** truy vết.
- **diagnosticReference:** link/ID tới log/trace; không nhét stack trace vô hạn vào header broker.
- **resolutionStatus:** OPEN, FIX_IN_PROGRESS, READY_FOR_REDRIVE, REPLAYING, RESOLVED, CLOSED_WITH_REASON.

Không tự sửa original payload trong quá trình “thử lại”. Nếu cần migration schema, tạo payload/command mới có dấu vết, lưu phiên bản và lý do biến đổi để sau này đối soát.

## 10. Poison message và nguy cơ head-of-line blocking

**Poison message** là message hiện không thể xử lý thành công bằng các lần giao lại bình thường. Nó có thể có schema sai, trường bắt buộc rỗng, giá trị độc hại hoặc kích hoạt bug. Nhưng một message cần điều kiện ngoài (chẳng hạn dữ liệu reference chưa đồng bộ) cũng có thể tỏ ra “poison” tại thời điểm đó.

Nếu consumer xử lý tuần tự cùng key hoặc partition:

~~~text
partition P:
  event-101 OK
  event-102 FAIL repeatedly
  event-103 WAITING
  event-104 WAITING
~~~

Retry vô hạn event-102 làm chậm toàn partition. Chuyển event-102 ra DLQ và tiếp tục lại có thể khiến event-103/104 được xử lý khi state từ event-102 chưa được áp dụng. Đây là **đánh đổi ordering với liveness**.

Các lựa chọn:

1. **Block và alert:** giữ thứ tự nghiêm ngặt cho luồng không thể bỏ qua event.
2. **Quarantine + tiếp tục:** chỉ khi downstream có version check, aggregate key, idempotency hoặc quy tắc cho phép.
3. **Repair tại chỗ:** nâng cấp handler, sửa config/bug rồi retry cùng event khi còn hạn.
4. **Compensate/skip có kiểm soát:** khi business xác nhận sự kiện không còn có nghĩa và có record audit.
5. **Đẩy xử lý riêng theo aggregate:** tránh một key xấu làm kẹt toàn bộ luồng nếu kiến trúc và broker hỗ trợ.

Không đặt rule “mọi message lỗi sau 3 lần là bỏ qua” cho event tài chính hoặc event cập nhật trạng thái bắt buộc nếu thiếu cơ chế phục hồi consistency.

## 11. Dead Letter Queue là gì và không phải là gì?

**DLQ** là nơi cách ly message đã không thể xử lý theo pipeline chính sau các điều kiện xác định. Mục tiêu:

- Bảo tồn thông tin để điều tra, tránh vòng retry nóng.
- Giảm tác động tới thông lượng consumer chính.
- Gắn lỗi với owner và nguyên nhân.
- Cho phép sửa dữ liệu, contract hoặc code rồi redrive có kiểm soát.
- Đảm bảo có dấu vết khi quyết định bỏ qua, bù trừ hoặc đóng nghiệp vụ.

DLQ **không tự xử lý lỗi**. Nếu không có ownership, cảnh báo, dashboard, retention và runbook, nó có thể chỉ là “nghĩa địa message”.

Cũng không nên coi DLQ là nguồn sự thật duy nhất của giao dịch. Trạng thái nghiệp vụ cần được ghi nhận trong service owner, và operation quan trọng cần khả năng tra cứu/reconciliation.

### Nội dung nên lưu trong DLQ

Giữ nguyên message gốc và các thông tin:

| Trường | Mục đích |
|---|---|
| original topic/queue | Biết thông điệp đến từ đâu |
| message ID/type/version | Định danh và parse |
| partition/offset hoặc delivery metadata | Hỗ trợ điều tra theo broker |
| producer/consumer/version | Tìm compatibility bug |
| firstFailureAt/lastFailureAt | Biết độ tuổi lỗi |
| attempts/errorCode | Hiểu những gì đã thử |
| correlation/operation/aggregate ID | Liên kết nghiệp vụ |
| failure category | Phân loại hướng xử lý |
| captured payload/reference | Redrive mà không mất nội dung |
| redriveCount/status/owner | Kiểm soát vòng đời |
| security classification | Bảo vệ dữ liệu nhạy cảm |

Thông điệp DLQ có thể chứa PII, dữ liệu thanh toán hoặc bí mật. Áp dụng mã hóa, access control, retention, redaction và audit tương đương hoặc cao hơn main queue.

## 12. Thiết kế route đến DLQ an toàn

Một mô hình:

~~~text
orders.submitted.main
        |
        v
inventory-reservation-consumer
        |
        +--> processed --> business state + ACK/offset
        |
        +--> retryable error
        |        |
        |        v
        |   inventory.retry.delayed
        |        |
        |        +--> eligible time --> reprocess
        |
        +--> permanent/exhausted
                 |
                 v
        inventory.reservation.dlq
                 |
                 v
          operations dashboard
~~~

Cần trả lời:

- Producer của bản tin lỗi là ai: broker tự dead-letter hay consumer publish?
- Nếu publish DLQ thất bại, source message có còn được giao lại?
- Nếu publish thành công nhưng ACK source thất bại, có kiểm soát duplicate không?
- Retry queue có thể lặp về main queue không, và attempt count có tăng đúng không?
- Có circuit breaker khi broker/DLQ unavailable không?
- DLQ có cùng failure domain với main broker không?
- Message có thể bị mất do TTL/retention trước khi điều tra không?
- Có alert khi DLQ tăng hoặc oldest age vượt ngưỡng không?

Không ACK message gốc chỉ vì đã **bắt được exception**. Phải có outcome đã ghi bền hoặc đường replay an toàn, theo bảo đảm cụ thể của hệ thống.

### Một DLQ chung hay theo domain?

Một DLQ tập trung dễ vận hành nền tảng, nhưng có thể làm lẫn dữ liệu nhạy cảm, quyền hạn và owner. DLQ theo consumer/domain thường dễ phân trách nhiệm hơn:

- inventory-reservation.dlq do đội Inventory xử lý.
- payment-authorization.dlq do đội Payment xử lý theo quy trình đặc biệt.
- notification-email.dlq có thể được redrive ít rủi ro hơn.

Tùy quy mô có thể dùng shared tooling và catalog, nhưng vẫn phải xác định **ai chịu trách nhiệm** cho mỗi message và outcome nghiệp vụ.

## 13. So sánh RabbitMQ, SQS và Kafka trong lỗi message

| Khía cạnh | RabbitMQ | Amazon SQS | Apache Kafka |
|---|---|---|---|
| Mô hình tiến độ | ACK/NACK delivery | DeleteMessage và visibility timeout | Consumer group offset |
| Đường DLQ | DLX + queue hoặc publish theo ứng dụng | DLQ + redrive policy/maxReceiveCount | Thường dùng dead-letter topic/retry topic qua ứng dụng |
| Retry delay | TTL/DLX, delayed mechanism hoặc scheduler | Visibility timeout/delay/scheduler theo tính năng | Retry topics, scheduler hoặc pause/seek theo framework |
| Replay | Requeue/publish từ DLQ | Redrive/publish từ DLQ | Publish từ DLT hoặc đọc lại offset khi thích hợp |
| Ordering | Theo queue/consumer/prefetch, phụ thuộc cấu hình | FIFO có ràng buộc nhóm, standard không hứa thứ tự chặt | Thứ tự theo partition |
| Duplicate | Cần giả định redelivery | Standard có thể duplicate; FIFO vẫn cần idempotency | Replay/rebalance có thể giao lại |
| Điểm phải lưu ý | Requeue nóng, cấu hình DLX, publisher confirm | Visibility, retention, maxReceiveCount, group blocking | Commit offset, partition ordering, DLT là topic riêng |

Đây là **so sánh khái niệm**. Cấu hình broker, version, managed service và client library cụ thể có thể thay đổi khả năng. Không dùng một abstraction che giấu các khác biệt có ảnh hưởng correctness.

### RabbitMQ: chọn requeue=false có chủ đích

Nếu queue có dead-letter exchange hợp lệ, reject/nack không requeue có thể đưa message sang DLX. Nếu chưa có cấu hình đích/route hoạt động, message có thể bị loại bỏ. Cần thiết lập route, kiểm thử failure và theo dõi unroutable messages.

Nếu dùng TTL retry queue quay lại main queue, phải chặn vòng lặp vô hạn: đếm attempts ổn định, kiểm soát tuổi, phát hiện chuỗi dead-letter và đưa sang quarantine khi vượt ngưỡng.

### SQS: visibility không phải khóa vĩnh viễn

Message có thể hiển thị lại khi consumer xử lý lâu hơn visibility timeout. Tăng visibility quá dài có thể làm phục hồi sau consumer crash chậm; quá ngắn gây processing trùng khi lần trước chưa hoàn tất. Cần chọn theo thời gian xử lý, có gia hạn khi cần, timeout/retry và idempotency.

Trong FIFO, sử dụng DLQ/redrive có thể làm thay đổi thứ tự xử lý của message group. Nếu thứ tự là bất biến nghiệp vụ, phải có policy cho việc chặn, giải phóng hoặc reconcile theo group.

### Kafka: không giả định có DLQ “mặc định”

Kafka giữ record trong topic đến hết retention; một consumer framework có thể hỗ trợ dead-letter publishing. Cần thiết kế cách producer gửi bản tin sang DLT, cách consumer tiến offset, và bảo đảm đường chuyển không làm mất record.

Commit offset chỉ là ghi nhận tiến độ. Nếu xử lý DB đã commit nhưng offset chưa commit, record có thể xuất hiện lại sau rebalance/crash. Nếu offset commit trước khi ghi DB, có rủi ro bỏ qua công việc. Với side effect ngoài Kafka, idempotency và đối soát vẫn là yêu cầu căn bản.

## 14. Delivery semantics và idempotency

Các thuật ngữ thường gặp:

- **At-most-once:** có thể mất message nhưng không chủ đích giao lại; không phù hợp khi không được phép mất nghiệp vụ.
- **At-least-once:** retry/redelivery giúp tránh mất message nhưng có thể xử lý trùng.
- **Exactly-once:** bảo đảm trong một phạm vi kỹ thuật được định nghĩa chặt, thường không mở rộng tự động qua broker, database và HTTP provider độc lập.

Trong thực tế, nhiều hệ thống Microservices chọn **at-least-once delivery + idempotent handler**. Ví dụ cùng OrderSubmitted được giao hai lần, Inventory chỉ tạo **một reservation hợp lệ**.

### Idempotency theo message ID

Một cách lưu inbox:

~~~sql
CREATE TABLE processed_messages (
    consumer_name VARCHAR(100) NOT NULL,
    message_id VARCHAR(150) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, message_id)
);
~~~

Trong **cùng transaction DB**:

1. Kiểm tra/ghi nhận khóa message ID với unique constraint.
2. Nếu đã xử lý thành công, coi là duplicate và ACK sau khi xác minh policy.
3. Nếu chưa xử lý, thực hiện thay đổi domain hợp lệ.
4. Ghi kết quả nghiệp vụ, domain event/outbox nếu cần.
5. Commit transaction.
6. Sau đó ACK/commit broker progress.

**Quan trọng:** Không chèn processed_messages rồi commit riêng **trước** business transaction; nếu business transaction thất bại sau đó, lần giao lại có thể bị nhận nhầm là đã xử lý. Để an toàn, marker và side effect DB phải cùng transaction hoặc có state machine RECORDED/PROCESSING/COMPLETED với recovery rõ.

### Business idempotency

Message ID khác nhau đôi khi vẫn biểu thị **cùng một ý định nghiệp vụ** do producer retry publish hoặc hai command trùng. Vì vậy có thể cần unique business key, chẳng hạn reservation cho một orderId và reservationPurpose, ngoài message ID.

Đặc biệt với Payment, một HTTP timeout sau khi request đã đến provider không thể giải quyết chỉ bằng inbox database ở consumer. Cần **stable idempotency key với provider**, lookup trạng thái giao dịch và reconciliation.

## 15. Transactional Outbox và Inbox

### Vấn đề dual write ở producer

Nếu Ordering cập nhật Order rồi publish event:

~~~text
DB commit Order=SUBMITTED  --> success
Broker publish event      --> failure
~~~

Service đã đổi trạng thái nhưng các consumer không nhận được event. Đổi thứ tự publish trước rồi commit DB cũng có nguy cơ event xuất hiện dù transaction nghiệp vụ rollback.

**Transactional outbox** ghi state và bản ghi event trong **cùng transaction DB**:

~~~text
Ordering transaction:
  UPDATE order state
  INSERT outbox event
  COMMIT

Outbox dispatcher:
  read unpublished event
  publish broker
  mark published
~~~

Dispatcher có thể publish trùng nếu broker nhận event nhưng response bị mất trước khi mark published. Do đó consumer vẫn phải idempotent.

### Consumer side Inbox

Inbox lưu nhận dạng message/operation để tránh thực thi side effect nhiều lần. Với một handler update DB và phát event mới:

~~~text
Consumer receives
    |
    v
Begin DB transaction
  - Dedup message ID/business operation ID
  - Validate aggregate state/version
  - Apply state change
  - Insert outgoing event into outbox
  - Record processed marker
Commit
    |
    v
ACK source delivery
~~~

Khi source redeliver sau DB commit, unique constraint và trạng thái processed giúp handler ACK mà không tái tạo tác dụng. Nếu transaction rollback, marker cũng rollback, message có thể retry.

Không gộp outbox/inbox thành lời hứa “exactly-once toàn hệ thống”. Chúng giải quyết những cửa sổ lỗi cụ thể của DB và broker, không tự kiểm soát external payment API.

## 16. Xử lý duplicate, out-of-order và missing events

Một consumer không thể chỉ hỏi “đã nhận event ID này chưa?” nếu thứ tự quan trọng.

Ví dụ:

~~~text
OrderSubmitted (aggregateVersion=7)
OrderCancelled (aggregateVersion=8)
~~~

Nếu version 8 đến trước version 7:

- Consumer phải biết có thể xử lý event 8 ngay hay cần chờ event 7.
- Nếu không có state tương ứng, có thể tạm chờ hoặc yêu cầu snapshot/replay.
- Khi event 7 đến muộn, không được làm trạng thái quay ngược từ CANCELLED thành SUBMITTED.

Các chiến lược:

- Partition/routing theo aggregateId để giữ thứ tự khi broker hỗ trợ.
- Ghi aggregateVersion và áp logic monotonic/compare-and-set.
- Dùng business state machine chống transition ngược.
- Xây cơ chế phát hiện thiếu sequence và lấy lại dữ liệu từ nguồn sự thật.
- Có TTL cho buffer chờ, alert cho gap và hướng giải quyết nếu event mất.
- Nếu consumer dùng projection, ghi rõ eventual consistency và update lag.

**Đưa event bị lỗi sang DLQ rồi tiếp tục** có thể phá thứ tự và sinh sai dữ liệu nếu không có versioning. Phương án DLQ phải xét ordering contract ngay từ thiết kế.

## 17. Rủi ro khi redrive từ DLQ

Redrive nghĩa là đưa message cũ trở lại xử lý. Nó có rủi ro vì:

- Code đã thay đổi; cùng payload có thể chạy nhánh mới.
- Dữ liệu hiện tại khác thời điểm ban đầu.
- Event đã quá hạn hoặc một workflow đã được bù trừ.
- Side effect có thể đã thực hiện trước lỗi/ACK thất bại.
- Consumer khác có thể đã xử lý một event mới hơn.
- Tải redrive dồn vào DB/provider có thể vượt capacity.
- Payload có thể cần chuyển đổi schema.
- Một message có thể đã bị operator khác redrive trước đó.

Vì vậy **không chạy “replay all” ngay khi dashboard đỏ**. Cần phân loại và xác minh.

### Các trạng thái quản trị redrive

~~~text
NEW_IN_DLQ
  |
  v
TRIAGED
  |
  +--> WAITING_FOR_FIX
  |        |
  |        v
  |   READY_FOR_REDRIVE
  |
  +--> REQUIRES_MANUAL_RECONCILIATION
  |
  +--> CLOSED_WITH_BUSINESS_REASON
  |
  v
REDRIVING
  |
  +--> RESOLVED
  |
  +--> FAILED_AGAIN ---> triage / capped redrive count
~~~

Cần audit ai ra quyết định, lúc nào, phạm vi nào và dựa trên bằng chứng gì. Trạng thái là mô hình ứng dụng/operations, không phải khả năng mặc định của mọi broker.

### Quy trình redrive có kiểm soát

1. **Khoanh phạm vi:** theo failureCode, message type/version, tenant, thời gian, consumer version, aggregate.
2. **Xác định root cause:** bug, config, provider outage, schema sai hay message không còn hợp lệ.
3. **Sửa nguyên nhân:** deploy fix, bổ sung mapping hoặc khôi phục dependency.
4. **Kiểm tra state hiện tại:** message đã được áp dụng chưa, side effect có thể đã xảy ra chưa, operation có bị cancel/expire không?
5. **Chạy dry-run khi có thể:** dự đoán outcome mà không tạo side effect; kiểm tra schema và authorization.
6. **Redrive ít trước:** chọn lô nhỏ trên môi trường phù hợp hoặc canary production có rào chắn.
7. **Giới hạn rate/concurrency:** không đẩy toàn bộ backlog đồng loạt sang provider.
8. **Theo dõi:** success, duplicate, re-failure, latency, queue lag và business outcome.
9. **Dừng khi có tín hiệu xấu:** tăng lỗi mới, rối thứ tự, phát sinh double side effect.
10. **Đóng sự cố:** lưu record đối soát, message đã xử lý, message không còn cần hoặc yêu cầu bù trừ.

Với dữ liệu tài chính hoặc giao dịch nhạy cảm, nên có tiêu chí kiểm tra/phê duyệt vận hành được xác định từ trước. Không tự động redrive khoản hoàn tiền chỉ vì hệ thống đã lên lại.

## 18. Chỉnh sửa payload hay gửi message mới?

Một số lỗi đến từ payload cũ không còn tương thích. Có ba lựa chọn:

| Lựa chọn | Khi dùng | Điều cần bảo đảm |
|---|---|---|
| **Replay nguyên văn** | Consumer đã được sửa để hiểu contract cũ | Idempotency, state còn hợp lệ |
| **Transform version** | Có migration schema được công bố | Quy tắc chuyển đổi được version/audit |
| **Tạo command bù trừ mới** | Ý định cũ không thể thực thi an toàn | Command mới có owner, quyền và idempotency |
| **Đóng không redrive** | Hành vi đã hết ý nghĩa hoặc được giải quyết ngoài luồng | Lý do, đối soát, audit trail |

Không sửa trực tiếp message gốc trong DLQ rồi làm mất bản ghi nguyên thủy. Giữ original payload (hoặc reference được bảo vệ), bản chuyển đổi, mapping version, người thực hiện và lý do.

Một event là **sự thật đã xảy ra**, nên không “sửa sự thật” của event cũ để phản ánh trạng thái hiện tại. Nếu cần hiệu chỉnh nghiệp vụ, có thể tạo một event/command điều chỉnh mới với semantics riêng.

## 19. Message expiration, TTL và hạn sử dụng nghiệp vụ

Có ít nhất ba loại thời hạn:

1. **Broker TTL/retention:** message còn tồn tại bao lâu trong queue/topic.
2. **Retry deadline:** retry đến khi nào trước khi đưa DLQ/đóng?
3. **Business validity:** sau thời điểm nào ý định không còn đúng nghiệp vụ?

Ví dụ ReserveStock có thể yêu cầu giữ hàng trước 15 phút; xử lý message ba ngày sau không nhất thiết còn hợp lệ. Consumer cần biết **expiresAt** hoặc business deadline và so với state hiện tại.

Nếu message hết hạn:

- Không tiếp tục giữ hàng bằng một yêu cầu lỗi thời.
- Ghi trạng thái EXPIRED/REJECTED theo contract hoặc phát outcome event.
- Nếu đã phát sinh side effect trước đó, chạy compensation/reconciliation phù hợp.
- Cập nhật status của operation để người dùng không chờ vĩnh viễn.

TTL broker không thay thế kiểm tra nghiệp vụ: message có thể được giao trước TTL nhưng handler xử lý chậm qua deadline, hoặc message đã đến DLQ vẫn được giữ lâu để điều tra.

## 20. Retry, timeout và side effect chưa rõ

Ví dụ Payment Service gửi lệnh capture:

~~~text
Consumer receives PaymentRequested
  |
  v
Call payment provider
  |
  +--> Provider captures successfully
  |
  +--> Network response lost
  |
  v
Consumer sees timeout
~~~

Tại thời điểm timeout, outcome **UNKNOWN**. Nếu consumer retry bằng một payment ID mới, có nguy cơ double capture.

Hướng xử lý:

1. Gắn stable business operation ID và idempotency key ngay từ đầu.
2. Provider call dùng cùng key cho cùng ý định theo contract.
3. Timeout → lưu trạng thái UNKNOWN/PENDING_RECONCILIATION.
4. Tra cứu provider theo key/transaction reference nếu có.
5. Chỉ retry khi semantics của provider và hệ thống bảo đảm an toàn.
6. Đối soát và ghi kết quả cuối, bao gồm trường hợp cần hỗ trợ thủ công.
7. ACK event nguồn khi trạng thái cần phục hồi đã được ghi bền theo chính sách, không để lost response tạo vòng retry mù.

Cách làm có thể khác giữa authorization, capture, void và refund. **Một mã lỗi kỹ thuật “timeout” không phải kết quả nghiệp vụ cuối cùng.**

## 21. Lỗi của message nào được coi là hoàn tất?

Không phải mọi consumer failure cần DLQ. Hãy định nghĩa outcomes:

| Outcome | Ví dụ | Có thể ACK khi nào? |
|---|---|---|
| **APPLIED** | Inventory reserve thành công | Sau durable commit |
| **DUPLICATE_ALREADY_APPLIED** | Event ID đã được xử lý | Sau khi xác minh processed record |
| **BUSINESS_REJECTED** | Inventory xác nhận thiếu hàng | Sau khi ghi outcome/rejection đúng hợp đồng |
| **DEFERRED** | Đưa sang workflow có scheduler quản lý | Sau khi durable handoff |
| **QUARANTINED** | Message không parse được và đã đưa DLQ bền vững | Theo broker guarantee/route policy |
| **UNKNOWN_EXTERNAL_OUTCOME** | Payment response mất | Sau khi có durable reconciliation state |
| **UNRECOVERABLE_INTERNAL** | Bug chưa thể xử lý | Cách ly, alert, giữ khả năng redrive |
| **EXPIRED** | Command đã quá business deadline | Sau khi ghi kết quả hết hạn/compensation |

Không ACK chỉ vì handler đã catch exception mà chưa có outcome bền vững. Trong hệ thống thực, “ACK” có thể tương đương commit offset/delete delivery theo broker, nhưng bản chất quyết định là **đã chuyển trách nhiệm xử lý đi đâu một cách an toàn**.

## 22. Mẫu chính sách xử lý lỗi chuẩn theo service

Một policy có thể khai báo như sau:

~~~yaml
consumer: inventory-reservation
input: orders.submitted
owner: inventory-team
deliveryAssumption: at-least-once
idempotency:
  scope: consumer-name-plus-message-id
  businessKey: order-id-plus-reservation-purpose
retry:
  maxAttemptsIncludingFirst: 5
  initialBackoff: 2s
  maxBackoff: 30s
  jitter: full
  maxElapsedSinceFirstAttempt: 10m
  transientErrorCodes:
    - DB_TIMEOUT
    - DEPENDENCY_UNAVAILABLE
    - RATE_LIMITED
  nonRetryableErrorCodes:
    - MESSAGE_MALFORMED
    - UNSUPPORTED_EVENT_VERSION
    - BUSINESS_RULE_REJECTED
deadLetter:
  destination: inventory-reservation.dlq
  retainOriginalPayload: true
  alertOnNewEntries: true
  owner: inventory-team
redrive:
  requireCurrentStateCheck: true
  canaryBatchSize: 20
  maxRedrives: 2
  rateLimitPerSecond: 5
  recordAudit: true
observability:
  trackAttemptCount: true
  trackMessageAge: true
  trackConsumerLag: true
  trackDlqOldestAge: true
~~~

Đây là **mẫu định hướng** cho một policy riêng của ứng dụng, không phải YAML có thể nạp trực tiếp vào mọi broker hoặc Spring framework. Các ngưỡng phải được xác định từ SLO, tải, tuổi nghiệp vụ của message và rủi ro side effect. Những message cần hoàn tất trong 30 giây không nên dùng cùng policy retry 10 phút như notification không khẩn cấp.

### Định nghĩa attempts thống nhất

“5 attempts” có thể được hiểu là 1 lần đầu + 4 retry, hoặc 5 retry sau lần đầu. Hãy ghi rõ và dùng một trường thống nhất. Nếu đếm attempt qua headers, cần phân biệt:

- Delivery được broker giao lại.
- Handler thật sự bắt đầu.
- Side effect đã gọi.
- Side effect đã commit.
- Redrive từ DLQ theo một chiến dịch mới.

Đếm không đúng có thể làm message vượt budget hoặc bị đưa DLQ quá sớm.

## 23. Ví dụ Java: kết quả handler và phân loại lỗi

Để không trộn business rejection với exception kỹ thuật, có thể chuẩn hóa kết quả ở application layer.

~~~java
public enum ProcessingOutcome {
    APPLIED,
    ALREADY_APPLIED,
    BUSINESS_REJECTED,
    DEFERRED
}
~~~

Exception kỹ thuật có phân loại rõ:

~~~java
public enum FailureCategory {
    TRANSIENT,
    PERMANENT,
    UNKNOWN_OUTCOME
}

public record ProcessingFailure(
        String errorCode,
        FailureCategory category,
        String diagnosticMessage
) {}
~~~

Ví dụ interface:

~~~java
public interface MessageProcessor {
    ProcessingOutcome handle(MessageEnvelope envelope)
            throws TransientProcessingException,
                   PermanentProcessingException,
                   UnknownOutcomeException;
}
~~~

Envelope có thể chứa messageId, eventType, version, occurredAt, aggregateId, correlationId và payload. Interface minh họa: các type Exception và MessageEnvelope phải được định nghĩa trong code thực tế, nhưng điều đáng chú ý là **business rejection được mô tả thành outcome**, còn sự cố kỹ thuật được phân loại để retry hoặc chuyển sang quy trình xử lý khác.

Không coi mọi RuntimeException là transient và retry. Một NullPointerException do bug có thể lặp vô hạn; nên giới hạn attempts và alert, đồng thời lưu message để sửa sau.

## 24. Ví dụ Java: thuật toán quyết định retry

Pseudocode Java dưới đây minh họa cách áp policy; phần broker acknowledgement, persistent scheduling và transaction cần adapter tương ứng.

~~~java
public enum FailureAction {
    RETRY,
    DEAD_LETTER,
    RECONCILE,
    RECORD_REJECTION
}

public record RetryPolicy(
        int maxAttemptsIncludingFirst,
        long maxElapsedMillis,
        long initialDelayMillis,
        long maxDelayMillis
) {}

public record FailureContext(
        FailureCategory category,
        int attemptsIncludingCurrent,
        long elapsedSinceFirstAttemptMillis,
        long remainingBusinessValidityMillis
) {}

public final class FailureDecisionService {
    public FailureAction choose(FailureContext ctx, RetryPolicy policy) {
        if (ctx.category() == FailureCategory.UNKNOWN_OUTCOME) {
            return FailureAction.RECONCILE;
        }

        if (ctx.category() == FailureCategory.PERMANENT) {
            return FailureAction.DEAD_LETTER;
        }

        boolean attemptsRemain =
                ctx.attemptsIncludingCurrent() < policy.maxAttemptsIncludingFirst();

        boolean retryTimeRemains =
                ctx.elapsedSinceFirstAttemptMillis() < policy.maxElapsedMillis();

        boolean businessTimeRemains =
                ctx.remainingBusinessValidityMillis() > 0;

        if (attemptsRemain && retryTimeRemains && businessTimeRemains) {
            return FailureAction.RETRY;
        }
        return FailureAction.DEAD_LETTER;
    }
}
~~~

Ở production, decision cần kiểm tra thêm **delay dự kiến**, deadline tổng, code lỗi, capacity budget, circuit breaker, tenant policy và whether message still makes sense. Nếu remainingBusinessValidityMillis=100 ms mà delay tiếp theo 30 giây, không được chọn retry. Không thiết kế test chỉ xác nhận enum: cần mô phỏng failure thực tế và side effect.

### Backoff với jitter (minh họa)

~~~java
import java.util.concurrent.ThreadLocalRandom;

public final class RetryBackoff {
    public static long fullJitterDelayMillis(
            int retryNumber,
            long initialDelayMillis,
            long maxDelayMillis) {

        long cap = initialDelayMillis;

        for (int i = 1; i < retryNumber; i++) {
            if (cap >= maxDelayMillis / 2) {
                cap = maxDelayMillis;
                break;
            }
            cap *= 2;
        }

        cap = Math.min(cap, maxDelayMillis);

        return ThreadLocalRandom.current().nextLong(cap + 1);
    }
}
~~~

Ví dụ này giả định initialDelayMillis > 0, maxDelayMillis > 0 và cap nhỏ hơn Long.MAX_VALUE để phép cap + 1 an toàn; production code cần validation đầu vào và xử lý overflow đầy đủ. Trong thực tế, không sleep dài trong broker consumer thread nếu có delayed retry infrastructure; chuyển công việc sang lịch retry bền vững.

## 25. Ví dụ consumer: chỉ ACK sau durable outcome

Một cấu trúc trung lập với broker:

~~~text
onMessage(delivery):
    envelope = parse(delivery)

    if schema invalid:
        durableQuarantine(envelope, reason=INVALID_SCHEMA)
        ack(delivery) only after confirmed quarantine
        return

    if inbox shows already processed:
        ack(delivery)
        return

    try:
        begin transaction
        insert inbox marker with unique consumer+messageId
        apply domain changes
        insert outbox events if necessary
        commit transaction
        ack(delivery)
    catch DomainRejected:
        persist rejection outcome / event (durable)
        ack(delivery)
    catch TransientFailure:
        decision = retry policy
        if retry:
            durableScheduleRetry(original, nextEligibleAt)
        else:
            durableQuarantine(original, EXHAUSTED)
        ack(delivery) only after durable handoff
    catch UnknownExternalOutcome:
        persist reconciliation state
        ack(delivery) only after durable handoff
~~~

**Hai lưu ý quan trọng về race condition:**

1. Nếu broker giao lại giữa lúc một handler đang xử lý và inbox marker chưa commit, unique constraint và transaction isolation phải ngăn hai side effects chạy đồng thời hoặc có state machine xử lý song song.
2. Nếu quarantine publish thành công nhưng ACK delivery không thành công, message xuất hiện hai lần. Inbox/quarantine phải hỗ trợ dedup; không thể dựa vào ACK như atomic commit xuyên broker và DB.

Đối với handler có external side effect, không đặt HTTP call vào một transaction DB dài với giả định rollback DB sẽ rollback provider. Thường cần durable workflow và idempotency key để phối hợp.

## 26. Ví dụ Spring Boot + RabbitMQ theo khái niệm

Với Spring AMQP, một consumer có thể dùng annotation listener để nhận thông điệp. Đây là một khung minh họa về trách nhiệm, không phải cấu hình production đầy đủ:

~~~java
@Component
public class OrderSubmittedListener {
    private final ReservationUseCase reservationUseCase;

    public OrderSubmittedListener(ReservationUseCase reservationUseCase) {
        this.reservationUseCase = reservationUseCase;
    }

    @RabbitListener(queues = "orders.submitted")
    public void onMessage(OrderSubmittedEvent event) {
        reservationUseCase.reserveOnce(
                event.messageId(),
                event.orderId(),
                event.items()
        );
    }
}
~~~

Khi listener hoàn tất, cơ chế container có thể ACK theo mode được cấu hình. Khi exception xảy ra, error handler, requeue, retry interceptor và DLX quyết định điều gì diễn ra tiếp. Không giả định default của mọi version và container mode là giống nhau.

Một cấu hình ứng dụng phải kiểm tra:

- ACK mode: AUTO hay MANUAL; thời điểm transaction thực sự commit.
- Requeue mặc định khi listener throw exception.
- DLX và dead-letter routing keys có đích hợp lệ.
- Publisher confirms/returns khi ứng dụng tự publish retry/DLQ.
- Retry interceptor có maxAttempts, backoff và xử lý exhausted rõ.
- Prefetch và số consumer đồng thời.
- Schema converter/serializer và cách xử lý message không parse được.
- Metrics về retry, DLQ và lag/backlog.
- Thí nghiệm crash trước ACK và ngay sau DB commit để xác nhận redelivery xử lý đúng.

Nếu dùng manual acknowledgement, cần đảm bảo **không ack trước commit**, và không nack/requeue liên tục khiến consumer nóng. Hành vi reject để dead-letter phải được kiểm tra với cấu hình broker cụ thể.

## 27. Ví dụ Spring Boot + Kafka theo khái niệm

Trong Kafka, consumer thường đọc theo partition/offset. Một bản minh họa:

~~~java
@Component
public class InventoryEventConsumer {
    private final InventoryEventHandler handler;

    public InventoryEventConsumer(InventoryEventHandler handler) {
        this.handler = handler;
    }

    @KafkaListener(
        topics = "orders.submitted",
        groupId = "inventory-reservation"
    )
    public void consume(OrderSubmittedEvent event) {
        handler.processIdempotently(event);
    }
}
~~~

Để triển khai xử lý lỗi trong Spring Kafka, ứng dụng cần chọn cơ chế xử lý exception/retry/DLT phù hợp với **phiên bản thư viện đang sử dụng**, ví dụ listener error handler và dead-letter publishing. Không thể chỉ thêm một annotation và mặc định message lỗi sẽ tự vào DLQ.

Cần kiểm tra:

- Record nào được coi là processed khi handler throw exception?
- Offset được commit trước hay sau khi publish DLT và DB commit?
- Retry có chặn partition hay chuyển sang retry topic?
- Có giữ ordering theo aggregate key không?
- Message serializer/deserializer lỗi sẽ được xử lý như thế nào?
- Consumer rebalance/crash có tạo duplicate không?
- Producer gửi DLT có xác nhận thành công không?
- Khi đọc lại từ offset cũ hoặc DLT, có kiểm soát side effect không?

**Kafka exactly-once semantics** trong phạm vi Kafka transactions không tự bảo đảm exactly-once cho payment provider, email API hoặc database ngoài Kafka. Cần thiết kế idempotency ở từng boundary.

## 28. Tài liệu runbook cho DLQ

Một runbook tốt trả lời được câu hỏi **nhận alert rồi làm gì**.

### Khi có DLQ entry mới

1. Xác định tên consumer, source, message type và owner.
2. Lấy failureCode, attempts, firstFailureAt, lastFailureAt và trace/correlation ID.
3. Xem có lỗi hàng loạt cùng lúc hay chỉ một poison message.
4. Kiểm tra dependency outage, rollout mới, schema migration hoặc bug.
5. Đánh giá tác động nghiệp vụ: bao nhiêu order/payment/shipment đang chờ?
6. Kiểm tra message có còn hợp lệ và có thể đã tạo side effect không.
7. Chọn hướng repair, redrive, compensate hoặc close với lý do.
8. Cập nhật ticket/incident và theo dõi backlog giảm.

### Khi DLQ tăng nhanh

~~~text
DLQ growth spike
    |
    +--> Is producer emitting incompatible schema?
    |      |
    |      +--> stop/rollback producer deployment if appropriate
    |
    +--> Is a dependency unhealthy?
    |      |
    |      +--> reduce retry pressure, restore dependency
    |
    +--> Is the consumer version buggy?
    |      |
    |      +--> rollback/fix consumer, protect pipeline
    |
    +--> Is this overload?
           |
           +--> scale carefully, add backpressure, rate limit redrive
~~~

Chưa xác định root cause mà redrive toàn bộ backlog có thể làm lỗi lặp ở quy mô lớn. Cần một **chế độ pause redrive** hoặc quota thấp khi hệ thống đang bất ổn.

### Khi một message cứ vào DLQ sau redrive

- So sánh failureCode lần trước và lần này.
- Kiểm tra code version hoặc data fix có thật sự được deploy.
- Xác định message còn có business meaning không.
- Đánh giá idempotency/inbox có từ chối đúng hay không.
- Chặn thêm redrive khi chạm maxRedriveCount; escalate tới owner.
- Nếu cần bù trừ, tạo action riêng có audit và phê duyệt phù hợp.

## 29. Observability: đo luồng xử lý lại như một sản phẩm vận hành

Không chỉ theo dõi “consumer đang chạy”. Cần metrics phản ánh message age, completion và hậu quả nghiệp vụ.

| Metric | Ý nghĩa |
|---|---|
| Messages produced/consumed per second | Lưu lượng |
| Consumer backlog/lag | Khả năng theo kịp producer |
| Oldest message age | Tồn đọng có còn trong SLO không |
| Processing duration | Thời gian xử lý handler |
| First-attempt success rate | Chất lượng xử lý bình thường |
| Retry rate/attempt distribution | Tải phát sinh do retry |
| Retry queue depth/oldest age | Tải đang chờ xử lý lại |
| DLQ entry rate/depth | Mức message bị cách ly |
| DLQ oldest unresolved age | Sự cố bị tồn đọng |
| Redrive success/failure rate | Hiệu quả và rủi ro khi replay |
| Duplicate detection rate | Mức độ redelivery và idempotency |
| Schema error by version | Phát hiện contract drift |
| Business rejection rate | Kết quả nghiệp vụ, không gộp vào bug |
| Unknown outcome/reconciliation backlog | Giao dịch có side effect chưa xác định |
| Completion latency | Thời gian từ event đến business outcome cuối |
| Outbox publishing lag | Nguy cơ chậm event hoặc kẹt dispatcher |

Một **consumer completion SLO** có thể định nghĩa: “99,9% OrderSubmitted hợp lệ được Inventory ghi nhận thành một trong các kết quả RESERVATION_SUCCEEDED/REJECTED trong 60 giây”. Điều kiện thành công và denominator phải rõ. Một record bị đưa DLQ thường chưa phải business completion trừ khi workflow có outcome rejection hợp lệ.

### Alert có khả năng hành động

Có thể dùng các tín hiệu:

- DLQ tăng bất thường hoặc có entry mới thuộc loại critical.
- Oldest unresolved message > giới hạn phù hợp nghiệp vụ.
- Retry attempts tăng cùng lúc downstream error/latency.
- Consumer lag tăng liên tục mặc dù traffic không đổi.
- Outbox lag/unknown payment backlog vượt SLO.
- Schema error tăng sau một deployment.
- Redrive failure spike hoặc phát sinh duplicate side effects.

Không page đội vận hành chỉ vì tổng số DLQ cũ lớn nếu đã triage và đóng theo policy; cũng đừng bỏ qua một DLQ entry duy nhất khi nó đại diện cho giao dịch tài chính quan trọng.

## 30. Logs, traces và correlation xuyên async boundary

Một trace HTTP kết thúc khi producer publish message, nhưng workflow có thể tiếp tục phút/giờ sau. Vì vậy:

- Propagate trace context nếu hạ tầng hỗ trợ và phù hợp threat model.
- Ghi correlationId, causationId, operationId và messageId ổn định.
- Với retry/redrive, có thể tạo trace/span mới liên kết tới message gốc.
- Ghi failureCode, attempt, consumer, topic/queue và latency vào log có cấu trúc.
- Không lưu raw payload chứa PII trong log hoặc metric labels.
- Dùng dashboard nối producer publish → broker lag → consumer attempts → DLQ → redrive → final outcome.

Một log record minh họa:

~~~json
{
  "timestamp": "2026-11-11T14:08:00Z",
  "level": "WARN",
  "service": "inventory-service",
  "consumer": "inventory-reservation",
  "messageId": "evt-f68db65f",
  "eventType": "OrderSubmitted",
  "eventVersion": 2,
  "correlationId": "journey-18ab",
  "aggregateId": "ord-2048",
  "attempt": 4,
  "failureCode": "DB_TIMEOUT",
  "failureCategory": "TRANSIENT",
  "action": "DEAD_LETTER",
  "source": "orders.submitted",
  "target": "inventory-reservation.dlq",
  "durationMs": 450
}
~~~

Không đưa exception stack trace vào mỗi lần retry nếu gây spam; có thể ghi root cause ở lần đầu/cuối và aggregate metrics các lần giữa. Nội dung log/tracing phải theo policy retention và access control.

## 31. Security, dữ liệu nhạy cảm và quyền redrive

DLQ thường chứa bản sao của message sản xuất. Nó có thể có thông tin khách hàng, địa chỉ, nghiệp vụ tài chính, tenant và token nội bộ nếu producer đã thiết kế kém. Vì vậy:

- Giảm dữ liệu trong message; dùng reference có quyền nếu phù hợp.
- Mã hóa khi lưu và khi truyền, áp IAM/ACL tối thiểu.
- Tách quyền **đọc DLQ**, **sửa metadata**, **redrive** và **xóa/đóng**.
- Audit actor, phạm vi, thời điểm, số message và kết quả redrive.
- Áp retention hợp pháp/phù hợp và chính sách xóa dữ liệu.
- Không gửi nguyên message sang ticket/chat/email không được bảo vệ.
- Kiểm tra quyền tenant khi redrive; không tin tenantId tự do trong payload nếu nguồn chưa xác thực.
- Bảo vệ consumer trước payload cực lớn, zip bomb, recursion depth và schema độc hại.
- Không cho người vận hành đổi amount/account của PaymentRequested ngay trong DLQ UI nếu không có quy trình nghiệp vụ riêng.
- Giữ một đường có thể tra cứu để xác nhận đã có side effect trước khi replay.

Đối với message sửa/xóa dữ liệu, redrive có thể là hành động làm thay đổi production. Công cụ phải cho người vận hành nhìn trước phạm vi và kết quả dự kiến, giới hạn rate và có stop control.

## 32. Tính toán capacity khi redrive

Giả sử backlog DLQ có **50.000 message**, mỗi consumer xử lý trung bình **50 message/giây** trong điều kiện ổn định nếu chỉ chạy redrive. Thời gian lý thuyết tối thiểu là:

\[
50{,}000 / 50 = 1{,}000\text{ giây} \approx 16.7\text{ phút}.
\]

Nhưng đó chưa kể:

- Message mới vẫn tiếp tục đến.
- Duplicate, retry, dependency limit và các bước kiểm tra idempotency.
- DB/provider có giới hạn throughput riêng.
- Batch size, concurrency, partition assignment và backpressure.
- Business ordering theo key và thời gian xử lý biến động.
- Hệ thống có thể cần ưu tiên traffic mới để không làm hỏng SLO.

Nếu provider chỉ cho phép thêm 10 request/giây cho redrive, 50.000 message cần ít nhất khoảng **5.000 giây (83,3 phút)** theo mô hình đơn giản. Đừng tăng số consumer lên hàng trăm nếu downstream không chịu nổi.

Một policy hợp lý là chia quota capacity giữa **new traffic** và **redrive**, đo saturation, dùng ramp-up theo lô và dừng khi error rate tăng. Mục tiêu không phải “DLQ về 0 nhanh nhất” mà là **khôi phục nghiệp vụ đúng và an toàn**.

## 33. Kịch bản thực hành: OrderSubmitted → ReserveStock

Một thương mại điện tử có Ordering publish OrderSubmitted. Inventory consumer tạo reservation. Có ba message lỗi.

### Case A — DB Inventory unavailable

Message hợp lệ nhưng DB timeout. Đây có thể là transient error.

1. Ghi DB_TIMEOUT và correlation ID.
2. Retry có backoff/jitter, maxAttempts và max elapsed.
3. Không ACK nguồn trước khi durable retry handoff hoặc xử lý thành công.
4. Khi DB phục hồi, inbox/unique business key ngăn tạo reservation trùng.
5. Nếu hết budget, đưa message vào DLQ và đánh dấu operation đang chờ xử lý.
6. Alert dựa trên SLO reservation completion và DLQ age.

Điều kiện kiểm chứng: khi broker redeliver sau DB commit nhưng trước ACK, chỉ có một reservation.

### Case B — eventVersion không hỗ trợ

Consumer chỉ hiểu OrderSubmitted v2, nhưng nhận v99 không có quy tắc tương thích. Retry cùng code và payload sẽ không cải thiện.

1. Phân loại UNSUPPORTED_EVENT_VERSION.
2. Giữ nguyên payload và metadata trong quarantine/DLQ.
3. Báo producer/consumer owner; kiểm tra rollout/schema registry.
4. Deploy consumer hoặc adapter version phù hợp.
5. Chạy canary redrive theo lô nhỏ, kiểm chứng dữ liệu hiện tại.
6. Theo dõi business completion sau xử lý lại.

Điều kiện kiểm chứng: message gốc vẫn truy xuất được, không bị sửa trực tiếp và không có vòng retry nóng.

### Case C — Order đã CANCELLED khi redrive

Một OrderSubmitted bị kẹt 20 phút; trong lúc đó khách hàng đã hủy order theo một workflow hợp lệ. Nếu redrive và reserve stock mới, hệ thống có thể giữ hàng không cần thiết.

1. Tra cứu trạng thái hiện tại bằng orderId/aggregateVersion.
2. Kiểm tra reservation có tồn tại không.
3. Nếu order đã CANCELLED, áp policy: bỏ qua với outcome EXPIRED/SUPERSEDED hoặc compensation nếu có tác dụng cũ.
4. Không tạo reservation mới chỉ vì message cũ là hợp lệ về schema.
5. Ghi audit và đồng bộ trạng thái workflow để không hiển thị PENDING mãi.

Điều kiện kiểm chứng: redrive không làm order quay lại trạng thái hoạt động và không để tồn bị giữ sai.

### Case D — Payment response mất sau capture

PaymentRequested được consumer gửi đến provider; provider capture thành công nhưng consumer nhận timeout.

1. Ghi trạng thái PENDING_RECONCILIATION với stable payment operation key.
2. Tra cứu/cập nhật kết quả từ provider.
3. Không tự động tạo capture mới với key khác.
4. Nếu kết quả xác nhận thành công, ghi PaymentCaptured và ACK theo durable state.
5. Nếu thất bại chắc chắn, ghi PaymentRejected hoặc compensation theo contract.
6. Nếu vẫn unknown, alert theo age và chuyển tới quy trình đối soát.

Điều kiện kiểm chứng: một business payment không bị capture hai lần khi redelivery hoặc redrive.

## 34. Bài tập tính retry và phân loại lỗi

**Đề bài:** Notification consumer xử lý EmailRequested. Giả định:

- Tối đa 4 attempts **tính cả lần đầu**.
- Delays trước retry lần 1/2/3 tối đa lần lượt 2 giây, 4 giây, 8 giây (có jitter).
- Email provider trả 503 trong hai lần đầu, thành công lần ba.
- Message được gửi lại sau khi DB đã ghi delivery result nhưng trước ACK.

**Câu hỏi 1:** Có cần DLQ không?  
**Gợi ý:** Không, nếu attempt thứ ba thành công và kết quả đã được ghi bền, consumer xác nhận theo broker semantics. DLQ chỉ dùng khi vượt chính sách hoặc permanent/unknown cần xử lý riêng.

**Câu hỏi 2:** Tổng thời gian chờ tối đa trước lần thử ba là bao nhiêu (chưa kể thời gian xử lý mỗi attempt)?  
**Gợi ý:** 2 + 4 = **6 giây** theo các mức tối đa minh họa; với full jitter thực tế có thể ngắn hơn. Không coi đây là deadline tổng, còn phải cộng thời gian call thực tế.

**Câu hỏi 3:** Nếu provider đã gửi email nhưng response bị mất, có nên gửi lại?  
**Gợi ý:** Không retry mù nếu email trùng là không chấp nhận được. Cần xác minh provider API có idempotency/message ID hay không, lưu trạng thái và quyết định theo product policy.

**Câu hỏi 4:** Nếu broker redeliver sau DB commit, handler cần làm gì?  
**Gợi ý:** Đọc inbox/business delivery key, xác định outcome đã ghi, ACK mà không tạo side effect mới. Nếu provider không hỗ trợ idempotency và không tra cứu được, phải làm rõ bảo đảm thực tế và phương án đối soát.

**Câu hỏi 5:** Nếu payload không có recipientAddress hợp lệ?  
**Gợi ý:** Permanent validation error; đưa vào quarantine hoặc ghi business rejection đúng contract, thay vì retry 503 policy.

**Câu hỏi 6:** Nếu queue chứa 10.000 message lỗi vì provider outage?  
**Gợi ý:** Dùng backoff, circuit breaker, rate limit retry và alert; không làm “requeue=true liên tục” khiến toàn hệ thống nóng.

## 35. Mẫu checklist trước khi triển khai

### Message contract và dữ liệu

- [ ] Có messageId/eventType/version, business key, timestamp, correlation ID.
- [ ] Producer và consumer thống nhất schema, phiên bản và compatibility policy.
- [ ] Có định nghĩa thời hạn nghiệp vụ và cách xử lý message quá hạn.
- [ ] Consumer kiểm tra authorization và tenant scope tại boundary phù hợp.
- [ ] Payload tối thiểu, tránh thông tin nhạy cảm không cần thiết.

### Xử lý thành công và lỗi

- [ ] Có outcome rõ cho applied, duplicate, business rejection và unknown.
- [ ] ACK/commit offset chỉ sau durable business outcome hoặc durable handoff.
- [ ] Đã thử crash giữa DB commit và ACK để xác nhận duplicate được xử lý an toàn.
- [ ] Các lỗi được phân loại transient, permanent, business, unknown, expired.
- [ ] Không retry vô hạn bug hoặc invalid schema.
- [ ] Retry có maxAttempts, maxElapsed, deadline, backoff và jitter.
- [ ] Retry không làm tăng tải vô hạn khi dependency đang quá tải.
- [ ] Consumer có inbox/business idempotency key phù hợp.
- [ ] External side effects có lookup/reconciliation khi timeout.
- [ ] Không giả định exactly-once tự động qua broker và provider.

### Retry/DLQ

- [ ] Retry destination và DLQ route được cấu hình/kiểm thử.
- [ ] Có kiểm chứng publish/route bền vững trước khi ACK nguồn.
- [ ] Attempt count và redrive count nhất quán qua mọi hop.
- [ ] Có maxAge/TTL/retention phù hợp với nhu cầu điều tra.
- [ ] Ordering/partition key được bảo vệ khi chuyển sang retry/DLQ.
- [ ] DLQ có owner, alert, runbook và chính sách redrive.
- [ ] Redrive kiểm tra business state hiện tại và existing side effects.
- [ ] Có canary batch, rate limit, stop condition và audit.
- [ ] Không chỉnh sửa message gốc không lưu dấu vết.

### Vận hành và bảo mật

- [ ] Có metrics lag, oldest age, retry rate, DLQ growth, redrive outcome.
- [ ] Có SLO completion nghiệp vụ thay vì chỉ đo consumer uptime.
- [ ] Trace/log nối producer → broker → consumer → DLQ → final outcome.
- [ ] DLQ được mã hóa/phân quyền/retention phù hợp.
- [ ] Operator được phân quyền riêng cho xem, redrive và đóng message.
- [ ] Có kiểm thử consumer rebalance, visibility timeout, broker outage.
- [ ] Đã diễn tập message parse lỗi, poison, duplicate, out-of-order.
- [ ] Có kế hoạch đối soát/compensation cho giao dịch quan trọng.

## 36. Mẫu hồ sơ điều tra một message trong DLQ

~~~text
Incident / Ticket:
  ID:
  Owner:
  Severity:
  Created At:

Message:
  Original Message ID:
  Event Type / Version:
  Aggregate ID / Version:
  Correlation ID:
  Producer:
  Consumer / Version:
  Source Queue/Topic:
  Failure Destination:
  First Failure:
  Last Failure:
  Attempts:
  Last Failure Code:
  Last Diagnostic Trace Reference:

Business Impact:
  Expected Operation:
  Current Business State:
  Possible Existing Side Effect:
  Expires At:
  Affected Tenant/Scope (restricted):

Decision:
  Root Cause:
  Remediation:
  Redrive Allowed?:
  Redrive Batch/Rate:
  Idempotency Check:
  Ordering Check:
  Approval/Owner:
  Stop Condition:

Outcome:
  Redriven At:
  Final State:
  Reconciliation Evidence:
  Closed By:
  Closed At:
~~~

Hồ sơ giúp việc DLQ trở thành một quy trình khôi phục có thể truy lại, đặc biệt khi lỗi kéo dài qua nhiều phiên trực hoặc nhiều lần deploy.

## 37. Kết luận thực hành

Giao tiếp bất đồng bộ tạo ra khả năng tách thời gian xử lý và hấp thụ lỗi tạm thời, nhưng đi kèm **redelivery, duplicate, ordering, lag và trạng thái side effect không chắc chắn**. Một pipeline đáng tin cậy cần phân loại lỗi theo semantics, chọn retry có giới hạn và backoff, cách ly message không xử lý được vào DLQ có owner, rồi redrive dựa trên trạng thái nghiệp vụ hiện tại.

Không dùng DLQ như nơi cất lỗi vô thời hạn; không retry vô hạn; không ACK trước khi có kết quả hoặc đường chuyển trách nhiệm bền vững; và không giả định rằng một lần nhận message tương ứng chính xác một lần tạo tác dụng nghiệp vụ.

Khi có **hợp đồng message rõ, outbox/inbox, idempotency, retry budget, DLQ runbook, observability và kiểm thử crash/timeout**, đội ngũ có thể khôi phục message lỗi mà vẫn bảo vệ tính đúng đắn của toàn hệ thống Microservices.
