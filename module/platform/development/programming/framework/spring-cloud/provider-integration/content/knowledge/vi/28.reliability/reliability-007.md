# Dead-letter, phát lại có kiểm soát và khôi phục sau sự cố

Một message bị đưa vào dead-letter queue (DLQ) thường là dấu hiệu một lần xử lý đã vượt quá chính sách retry hoặc không thể tiếp tục theo luồng bình thường. DLQ giúp cô lập message lỗi để điều tra và phục hồi, nhưng bản thân nó không sửa được dữ liệu, không xác nhận side effect đã xảy ra và không bảo đảm phát lại an toàn.

Trong hệ thống Spring Boot tích hợp Azure Service Bus, Event Hubs, AWS SQS, Kinesis hoặc Google Cloud Pub/Sub, cần thiết kế cả vòng đời của message lỗi: phân loại nguyên nhân, giữ bằng chứng, quyết định retry hay dead-letter, sửa nguyên nhân, xác minh trạng thái nghiệp vụ, phát lại có giới hạn và kiểm tra kết quả sau phục hồi.

**Dead-letter** là cơ chế cô lập một message khỏi luồng xử lý thông thường. **Redrive** là chuyển message từ DLQ trở lại luồng xử lý. **Replay** là phát lại một event/message để tái xử lý hoặc dựng lại projection. **Recovery** là khôi phục hệ thống và trạng thái nghiệp vụ sau sự cố. Các thao tác này có thể liên quan nhưng có mục tiêu và rủi ro khác nhau.

Bài thuộc chương **Độ tin cậy** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt lỗi transient, lỗi vĩnh viễn, poison message và unknown outcome.
2. Xác định điều kiện retry exhaustion và thời điểm chuyển message vào DLQ.
3. So sánh DLQ, retry queue, quarantine, archive và event replay.
4. Bảo toàn message identity, payload, headers, schema version và failure metadata để điều tra.
5. Thiết kế quy trình triage và xác minh side effect trước khi redrive/replay.
6. Phát lại có kiểm soát theo batch, rate limit, ordering và retry budget.
7. Hiểu DLQ/redrive behavior của Azure Service Bus, AWS SQS, Google Cloud Pub/Sub và giới hạn của Event Hubs/Kinesis.
8. Tích hợp dead-letter handling với Spring Cloud Stream binder và native SDK.
9. Khôi phục sau sự cố mà không tạo side effect trùng hoặc làm lùi trạng thái.
10. Xây dựng metrics, audit trail, runbook và failure-injection tests cho DLQ/replay.

## 2. DLQ giải quyết vấn đề gì?

Một consumer có thể thất bại vì dịch vụ tạm thời unavailable, dữ liệu không hợp lệ, schema không tương thích hoặc lỗi lập trình. Nếu broker tiếp tục giao cùng message mà consumer luôn thất bại, message có thể chiếm worker, gây retry storm hoặc chặn các message phía sau.

DLQ tách message cần điều tra khỏi luồng xử lý bình thường để các message khác tiếp tục được xử lý.

~~~mermaid
flowchart TD
    A[Broker giao message] --> B[Spring Boot consumer]
    B --> C{Handler thành công?}
    C -->|Có| D[Commit business state]
    D --> E[ACK / Complete]
    C -->|Lỗi transient| F[Retry có giới hạn]
    F -->|Thành công| D
    F -->|Hết retry budget| G[Dead-letter / DLQ]
    C -->|Lỗi permanent| G
    G --> H[Triage và phân loại]
    H --> I{Đã sửa nguyên nhân và xác minh an toàn?}
    I -->|Có| J[Controlled redrive / replay]
    I -->|Chưa| K[Quarantine / chờ xử lý]
    J --> B
~~~

DLQ có ba giá trị chính:

- **Cô lập:** message lỗi không tiếp tục chiếm luồng xử lý bình thường.
- **Bảo toàn bằng chứng:** giữ message và metadata để điều tra.
- **Phục hồi có kiểm soát:** cho phép sửa nguyên nhân rồi xử lý lại theo quy trình.

DLQ không phải bản sao lưu dài hạn, không phải kho lưu trữ sự kiện bất biến và cũng không phải bằng chứng message chưa tạo side effect. Message có thể đã cập nhật database hoặc gọi API ngoài trước khi lỗi phát sinh.

## 3. Phân biệt các loại lỗi trước khi quyết định dead-letter

Không nên đưa mọi exception vào DLQ ngay lập tức, cũng không nên retry mọi exception đến khi hết số lần nhận.

| Loại lỗi | Ví dụ | Hành động ban đầu |
| --- | --- | --- |
| **Transient failure** | Network reset, service unavailable, throttling | Retry có backoff/jitter trong budget |
| **Permanent technical failure** | Payload không parse được, schema không hỗ trợ | Dead-letter/quarantine |
| **Business rejection** | Đơn hàng đã hủy, trạng thái không cho phép | Ghi nhận kết quả nghiệp vụ; không retry mù |
| **Configuration/authorization** | Sai endpoint, thiếu RBAC, credential invalid | Sửa cấu hình/quyền; retry sau khi xác minh |
| **Unknown outcome** | Timeout sau khi payment provider có thể đã xử lý | Reconcile trước khi retry side effect |
| **Poison message** | Message luôn làm handler crash hoặc vi phạm invariant | Cô lập, điều tra và sửa handler/data |
| **Dependency outage kéo dài** | Database hoặc broker phụ thuộc ngừng hoạt động | Circuit breaker/queue buffering; tránh đẩy toàn bộ backlog vào DLQ quá sớm |

### Poison message

Poison message là message liên tục làm consumer thất bại. Nguyên nhân có thể nằm trong payload, schema, dữ liệu tham chiếu hoặc bug handler.

Ví dụ:

- JSON thiếu trường bắt buộc làm deserializer ném exception.
- Event version mới nhưng consumer chưa hỗ trợ.
- Message chứa số tiền âm trong một command không cho phép.
- Handler giả định order tồn tại nhưng event đến trước OrderCreated.
- Một giá trị đặc biệt khiến mapping hoặc business rule lặp lại cùng lỗi.
- Handler gặp lỗi code deterministic nên retry bao nhiêu lần cũng thất bại.

### Unknown outcome không phải permanent failure

Nếu consumer gọi external API rồi timeout, side effect có thể đã xảy ra. Đưa message vào DLQ không giải quyết sự không chắc chắn. Trước khi redrive, phải tra cứu operation reference/idempotency key hoặc chạy reconciliation.

## 4. Retry, retry queue, DLQ, quarantine và archive

Các cơ chế này không thể thay thế lẫn nhau:

| Cơ chế | Mục tiêu | Thời điểm dùng |
| --- | --- | --- |
| **Immediate retry** | Thử lại nhanh lỗi tạm thời | Lỗi ngắn, có budget |
| **Delayed retry queue/topic** | Chờ lâu hơn rồi thử lại | Dependency cần thời gian phục hồi |
| **DLQ** | Cô lập message đã vượt policy hoặc không thể xử lý | Poison/permanent/exhausted |
| **Quarantine** | Giữ message cần điều tra hoặc không được tự động phát lại | Security, schema conflict, unknown outcome |
| **Archive** | Lưu lịch sử phục vụ audit/rebuild | Retention dài hạn hoặc phân tích |
| **Replay stream** | Đọc lại lịch sử để dựng lại consumer/projection | Rebuild hoặc xử lý lại có chủ đích |

Không dùng DLQ như retry queue vô hạn. Nếu message được redrive ngay mà nguyên nhân chưa sửa, nó có thể quay lại DLQ, tạo vòng lặp tốn chi phí và che khuất incident.

### Chính sách retry trước DLQ

Một policy nên định nghĩa:

- Nhóm exception được retry.
- Số attempt tối đa và cách tính lần đầu.
- Backoff, jitter và Retry-After.
- Deadline/retry budget.
- Thời gian tối đa message được giữ trong luồng retry.
- Điều kiện chuyển DLQ.
- Error code/reason được lưu.
- Hành vi với unknown outcome và lỗi authorization.

Số lần delivery của broker không nhất thiết bằng số lần handler đã chạy. Một lần giao có thể thất bại trước khi handler bắt đầu; retry nội bộ SDK có thể tạo nhiều request trong một delivery. Hãy phân biệt broker delivery count, handler attempt và SDK request attempt.

## 5. Khi nào nên dead-letter ngay?

Một số lỗi nên được cô lập ngay vì retry không thể làm chúng tự phục hồi:

- Payload không hợp lệ hoặc không thể deserialize.
- Schema version không được hỗ trợ và không có upcaster tương thích.
- Message thiếu business identity bắt buộc.
- Cùng event ID nhưng payload fingerprint khác.
- Vi phạm security policy hoặc dữ liệu không được phép xử lý.
- Business invariant bị vi phạm và cần con người/nguồn dữ liệu xác minh.
- Message chứa command hết hạn, không còn hợp lệ theo nghiệp vụ.

Một số lỗi cần sửa cấu hình rồi mới redrive:

- 401/403 do identity/role/scope sai.
- Resource chưa được provision.
- Endpoint/namespace sai.
- Certificate hoặc secret đã hết hạn.

Không nên đưa message vào DLQ chỉ vì dependency đang outage ngắn. Nếu outage kéo dài, có thể tạm dừng consumer, mở circuit breaker hoặc giữ message ở queue/retry queue theo khả năng broker. Chọn thời điểm DLQ theo mục tiêu vận hành, không theo một ngưỡng retry tùy tiện.

## 6. Message metadata cần giữ khi dead-letter

Để điều tra và replay an toàn, cần lưu cả dữ liệu gốc và ngữ cảnh xử lý.

| Trường | Mục đích |
| --- | --- |
| message_id / event_id | Định danh ổn định của message/event |
| correlation_id | Liên kết workflow |
| causation_id | Event/command gây ra message hiện tại |
| aggregate_id / aggregate_version | Xác định đối tượng và thứ tự nghiệp vụ |
| schema_version / content_type | Chọn deserializer/upcaster |
| original_enqueued_at | Thời điểm message vào luồng ban đầu nếu broker cung cấp |
| dead_lettered_at | Thời điểm đưa vào DLQ |
| delivery_count | Số lần broker giao theo semantics của broker |
| handler_attempt | Số lần ứng dụng thực sự chạy handler |
| failure_category | transient/permanent/unknown/business |
| failure_code | Mã lỗi ổn định để thống kê |
| failure_stage | Deserialize, validation, DB, external API, ACK |
| consumer_name / subscription | Thành phần xử lý message |
| replay_count / replay_batch_id | Theo dõi các lần phát lại |
| payload_hash | Phát hiện message ID bị tái sử dụng với payload khác |

Không lưu access token, password, connection string hoặc secret trong metadata. Không sao chép payload nhạy cảm vào log chỉ để điều tra. Có thể giữ payload trong broker DLQ có kiểm soát truy cập và log một fingerprint/reference.

### Failure reason cần có cấu trúc

Tránh chỉ lưu stack trace dài làm dead-letter reason. Nên lưu mã phân loại ổn định, ví dụ:

~~~json
{
  "failureCategory": "SCHEMA_INCOMPATIBLE",
  "failureCode": "ORDER_EVENT_VERSION_UNSUPPORTED",
  "failureStage": "DESERIALIZATION",
  "consumer": "order-projection",
  "schemaVersion": 4,
  "firstFailedAt": "2026-11-24T10:15:00Z",
  "lastFailedAt": "2026-11-24T10:17:30Z"
}
~~~

Stack trace có thể được lưu trong hệ thống log/trace với retention và masking riêng. Broker reason/description thường có giới hạn độ dài; không nhồi toàn bộ exception vào field đó.

## 7. DLQ là bằng chứng về message, không phải trạng thái nghiệp vụ

Trước khi redrive, phải trả lời:

1. Message đã được consumer xử lý một phần chưa?
2. Database transaction đã commit chưa?
3. External API có thể đã tạo side effect chưa?
4. Có idempotency key/provider reference để tra cứu không?
5. Message đã được xử lý bởi consumer khác chưa?
6. Có event mới hơn làm message cũ không còn hợp lệ không?
7. Có thể replay cùng event ID mà không tạo tác dụng phụ thứ hai không?

Một message trong DLQ có thể ở một trong các trạng thái nghiệp vụ:

| Trạng thái business | Ý nghĩa | Quyết định |
| --- | --- | --- |
| Chưa có side effect | Handler thất bại trước commit | Có thể redrive sau khi sửa lỗi |
| Đã commit hoàn toàn nhưng ACK thất bại | Nghiệp vụ xong, broker vẫn dead-letter/redeliver | Không chạy lại side effect; dedupe và settle |
| Đã commit một phần qua nhiều hệ thống | Workflow chưa hoàn tất | Reconcile/compensate trước khi tiếp tục |
| Unknown outcome | Không biết external side effect đã xảy ra chưa | Tra cứu/đối soát, giữ quarantine nếu cần |
| Stale event | Trạng thái mới hơn đã thay thế | Bỏ qua/audit hoặc chạy correction theo domain |

Không lấy trạng thái DLQ làm nguồn sự thật về payment/order. Nguồn sự thật là state nghiệp vụ và các provider reference có thể đối chiếu.

## 8. Quy trình triage DLQ

Một quy trình triage tốt phải phân loại nguyên nhân trước khi phát lại:

~~~mermaid
flowchart TD
    A[DLQ alert] --> B[Snapshot metadata và message]
    B --> C[Phân nhóm theo failure code/consumer]
    C --> D{Có side effect đã xảy ra?}
    D -->|Không| E[Phân loại nguyên nhân]
    D -->|Có hoặc chưa rõ| F[Reconcile business/provider state]
    F --> G{Đã xác định kết quả?}
    G -->|Chưa| H[Quarantine / escalation]
    G -->|Rồi| E
    E --> I{Nguyên nhân đã sửa?}
    I -->|Chưa| H
    I -->|Rồi| J[Dry-run replay và kiểm tra sample]
    J --> K[Redrive có throttle]
    K --> L[Theo dõi kết quả và đối soát]
~~~

### Bước 1 — Bảo toàn bằng chứng

- Ghi nhận queue/subscription, DLQ depth và thời điểm bắt đầu.
- Chụp lại message ID, event ID, correlation ID, delivery count và failure reason.
- Lưu payload theo quyền truy cập và retention phù hợp.
- Ghi nhận phiên bản consumer, binder, SDK và schema.
- Không sửa payload gốc tại chỗ nếu cần audit.

### Bước 2 — Nhóm lỗi

Gom message theo failure code, schema version, consumer, dependency và khoảng thời gian. Một nghìn message cùng một lỗi 403 thường là một incident cấu hình, không phải một nghìn lỗi nghiệp vụ độc lập.

### Bước 3 — Xác định side effect

Tra cứu inbox/outbox, database state, provider operation reference, Blob metadata hoặc ledger. Phân loại message thành chưa xử lý, đã xử lý, xử lý một phần hoặc unknown outcome.

### Bước 4 — Sửa nguyên nhân

Ví dụ: deploy consumer hỗ trợ schema mới, sửa RBAC, provision resource, sửa dữ liệu tham chiếu hoặc khắc phục bug. Không redrive toàn bộ DLQ khi fix chưa được kiểm thử.

### Bước 5 — Dry-run

Chọn sample đại diện, chạy validation/deserialization và kiểm tra business preconditions mà không tạo side effect. Nếu có thể, chạy vào môi trường staging hoặc chế độ validate-only.

### Bước 6 — Redrive theo batch

Bắt đầu với batch nhỏ, giới hạn tốc độ/concurrency và theo dõi kết quả. Chỉ tăng dần khi error rate, duplicate rate và downstream load ở mức chấp nhận được.

### Bước 7 — Đối soát sau phục hồi

Xác nhận số message thành công, số message còn DLQ, business effect, duplicate, event ordering và backlog. Đóng incident khi cả broker state và business state đều nhất quán.

## 9. Redrive khác replay như thế nào?

**Redrive** thường chuyển message đang nằm trong DLQ trở lại queue/topic/subscription để consumer bình thường xử lý. **Replay** thường phát lại event từ archive/log hoặc một nguồn lịch sử để dựng lại một consumer/projection hay chạy lại workflow.

| Tiêu chí | Redrive | Replay |
| --- | --- | --- |
| Nguồn | DLQ | Event archive, stream retention, event store hoặc bản sao |
| Mục tiêu | Tiếp tục xử lý message lỗi | Tái xử lý lịch sử hoặc dựng lại projection |
| Identity | Giữ message/event ID gốc | Giữ event ID gốc; thêm replay metadata |
| Phạm vi | Thường là message đã thất bại | Có thể là một khoảng thời gian/partition/aggregate |
| Rủi ro | Lặp side effect, vòng lặp DLQ | Lặp side effect quy mô lớn, sai thứ tự, tải tăng |
| Kiểm soát | Batch, rate, retry budget, DLQ policy | Consumer riêng, offset/version, dry-run, rate limit |
| Kết quả | Message trở lại luồng xử lý | Projection/workflow được tái tạo/cập nhật |

Không đổi message ID để né deduplication khi redrive cùng một event. Việc đó có thể khiến consumer coi message cũ là một ý định nghiệp vụ mới.

Nếu cần chạy một business action mới dựa trên dữ liệu cũ, hãy tạo **command/event mới** với identity mới và quan hệ causation rõ ràng. Đừng ngụy trang một hành động mới thành replay của event cũ.

## 10. Thiết kế controlled redrive

Một redrive tool/job nên có các tham số và guardrail rõ ràng:

- Nguồn DLQ và đích nhận.
- Bộ lọc theo failure code, thời gian, schema version hoặc message ID.
- Số lượng tối đa mỗi batch.
- Tốc độ publish/receive tối đa.
- Concurrency tối đa.
- Delay giữa các batch.
- Retry budget và số lần redrive tối đa.
- Chế độ dry-run/validate-only.
- Giữ message ID/event ID và payload gốc.
- Ghi replay batch ID, operator/service identity và audit record.
- Cơ chế dừng khẩn cấp nếu error rate hoặc downstream load tăng.

### Không redrive toàn bộ DLQ một lần

Giả sử DLQ có 500.000 message sau một outage. Nếu đẩy tất cả về queue trong vài giây, consumer có thể tạo một đợt tải lớn lên database, Blob, Service Bus hoặc payment provider. Outage có thể tái diễn ngay khi phục hồi.

Một kế hoạch có thể:

1. Lấy 100 message thuộc một failure category đã sửa.
2. Chạy dry-run và xác minh side effect.
3. Redrive 10–20 message đầu với concurrency thấp.
4. Quan sát success rate, latency, 429, DB pool và duplicate.
5. Tăng batch/rate từng bước nếu ổn định.
6. Tạm dừng nếu lỗi tăng hoặc backlog downstream vượt ngưỡng.

Các con số chỉ minh họa. Rate và batch size cần tính theo capacity thực tế, SLO và quota của dependency.

### Replay rate phải tính cùng traffic mới

Tổng tải downstream gồm:

~~~text
total_rate = live_traffic + retry_traffic + redrive_rate + replay_rate
~~~

Nếu downstream đang phục vụ traffic mới, replay phải được cấp một phần capacity có giới hạn. Có thể dùng separate worker pool, rate limiter hoặc queue riêng để tránh replay chiếm hết tài nguyên.

## 11. Idempotency khi redrive và replay

Redrive thường làm message được giao lại. Consumer phải dùng cùng event identity để deduplication hoạt động.

Các nguyên tắc:

- Giữ event ID/message ID gốc khi cùng event được phát lại.
- Giữ aggregate ID và aggregate version.
- Inbox/processed-message record phải còn retention đủ dài.
- Kiểm tra business unique constraint trước khi tạo side effect.
- External API phải dùng cùng provider idempotency key nếu retry cùng operation.
- Nếu inbox record đã hết hạn, tra cứu business state trước khi replay.
- Nếu event đã được áp dụng nhưng handler lỗi ở bước sau, tiếp tục workflow từ state machine thay vì chạy lại toàn bộ.
- Replay projection phải tách khỏi consumer gửi payment/email hoặc các side effect không cần thiết.

### Inbox retention phải bao phủ replay window

Nếu inbox chỉ lưu 7 ngày nhưng DLQ cho phép replay sau 30 ngày, event cũ có thể được coi là mới khi inbox record đã bị xóa. Cần phối hợp:

- Broker retention.
- DLQ retention.
- Archive retention.
- Inbox/idempotency retention.
- Business unique reference.
- Thời gian cho phép vận hành replay.

Đối với ledger/payment, business unique reference thường phải được bảo vệ lâu hơn cache kỹ thuật deduplication.

## 12. Ordering và event cũ trong quá trình replay

Replay có thể đưa event version 12 vào consumer hiện đã áp dụng version 20.

Trước khi phát lại:

1. Đọc aggregate state/version hiện tại.
2. Xác định event là duplicate, stale, missing gap hay correction.
3. Nếu là duplicate, settle mà không lặp side effect.
4. Nếu là stale event, áp dụng domain policy: ignore/audit hoặc correction.
5. Nếu là gap, tìm event thiếu hoặc snapshot phù hợp.
6. Nếu replay projection, dùng projection mới hoặc reset có kiểm soát.
7. Nếu event có side effect ngoài, dùng idempotency/reconciliation riêng.

Không sắp xếp toàn bộ DLQ chỉ theo timestamp rồi replay tuần tự. Timestamp có thể lệch hoặc không thể hiện business sequence. Ưu tiên aggregate version/sequence và ordering scope.

### Replay theo aggregate

Nếu các event của một order phải tuần tự:

- Nhóm theo aggregate ID.
- Sắp xếp theo aggregate version có thẩm quyền.
- Không chạy song song các event cùng aggregate nếu handler không bảo vệ version.
- Các aggregate khác nhau có thể chạy song song.
- Nếu thiếu version, dừng aggregate đó để reconcile thay vì bỏ qua gap.

## 13. Schema evolution và dữ liệu lỗi

Một DLQ lớn có thể xuất hiện sau khi producer triển khai schema mới trước consumer.

Các hướng xử lý:

- **Backward-compatible schema:** consumer cũ có thể đọc payload mới theo quy tắc tương thích.
- **Upcaster/adapter:** chuyển event cũ hoặc mới về canonical model mà handler hiểu.
- **Versioned handler:** dispatch theo schema version.
- **Data repair:** sửa bản ghi tham chiếu hoặc payload thông qua một quy trình audit.
- **Quarantine:** giữ message không thể diễn giải an toàn.

Không sửa payload trong DLQ mà không lưu bản gốc và audit. Nếu cần transform, ghi lại transform version, input hash, output hash và lý do.

### Ví dụ schema dispatch trong Java

~~~java
public interface EventUpcaster {
    boolean supports(int schemaVersion);
    CanonicalOrderEvent upcast(byte[] payload);
}

public final class OrderEventDecoder {

    private final List<EventUpcaster> upcasters;

    public OrderEventDecoder(List<EventUpcaster> upcasters) {
        this.upcasters = List.copyOf(upcasters);
    }

    public CanonicalOrderEvent decode(
            int schemaVersion,
            byte[] payload) {

        return upcasters.stream()
                .filter(candidate -> candidate.supports(schemaVersion))
                .findFirst()
                .orElseThrow(() ->
                        new UnsupportedSchemaException(schemaVersion))
                .upcast(payload);
    }
}
~~~

Đây là ví dụ cấu trúc. Cần định nghĩa canonical schema, kiểm thử dữ liệu lịch sử và bảo đảm upcaster không thay đổi ý nghĩa event.

## 14. Khôi phục sau sự cố: incident recovery lifecycle

DLQ recovery là một phần của incident response. Một incident có thể làm backlog tăng, consumer bị dừng, dependency bị throttling hoặc dữ liệu nghiệp vụ ở trạng thái không xác định.

### Giai đoạn 1 — Contain

- Dừng hoặc giảm consumer nếu handler đang gây side effect sai.
- Mở circuit breaker hoặc giảm concurrency khi dependency quá tải.
- Tạm dừng redrive/replay.
- Giữ message trong broker/queue hoặc DLQ theo retention.
- Bảo vệ dữ liệu và audit trail.
- Tránh xóa message để giảm backlog trước khi xác định nguyên nhân.

### Giai đoạn 2 — Diagnose

- Xác định thời điểm bắt đầu/kết thúc sự cố.
- So sánh deploy/version, schema, identity, RBAC và dependency health.
- Nhóm lỗi theo failure code, consumer và partition.
- Xác định side effect đã commit, chưa commit hay unknown.
- Kiểm tra retry amplification, lock expiry, visibility timeout và checkpoint.
- Xác định có message mất, duplicate hoặc sai thứ tự không.

### Giai đoạn 3 — Correct

- Sửa bug/config/permission/schema.
- Bổ sung migration hoặc upcaster nếu cần.
- Kiểm thử trên sample từ DLQ đã mask dữ liệu.
- Xác minh idempotency và transaction boundary.
- Xác minh consumer mới tương thích với message cũ.

### Giai đoạn 4 — Recover

- Khởi động consumer với concurrency thấp.
- Redrive theo category/batch.
- Theo dõi downstream quota, latency, DB pool và duplicate.
- Dừng nếu error rate hoặc side effect bất thường tăng.
- Chỉ tăng tốc khi capacity đã ổn định.

### Giai đoạn 5 — Reconcile và close

- Đối chiếu số message trong queue, DLQ và archive.
- Đối chiếu số business operation đã commit.
- Kiểm tra payment/ledger/provider reference và side effect ngoài.
- Kiểm tra event ordering và projection version.
- Xác nhận không còn unknown outcome chưa xử lý.
- Ghi incident timeline, root cause, remediation và action items.

~~~mermaid
stateDiagram-v2
    [*] --> Contain
    Contain --> Diagnose
    Diagnose --> Correct
    Correct --> Validate
    Validate --> Recover
    Recover --> Reconcile
    Recover --> Contain: Error rate / load tăng lại
    Reconcile --> Closed
    Closed --> [*]
~~~

## 15. Runbook cho DLQ: checklist vận hành

Một runbook nên nêu rõ ai được phép xem, redrive, replay hoặc purge DLQ. Các hành động này có thể tạo side effect và cần audit.

### Khi DLQ depth tăng đột biến

1. Kiểm tra alert và thời điểm tăng.
2. Xác định queue/subscription/consumer bị ảnh hưởng.
3. Kiểm tra deployment mới, schema version và dependency health.
4. Phân nhóm failure reason.
5. Tạm dừng redrive tự động nếu chưa biết nguyên nhân.
6. Xác định có message nào đã tạo side effect một phần.
7. Mở incident nếu ảnh hưởng SLO hoặc business invariant.
8. Ghi nhận số message, oldest age và tốc độ tăng.

### Trước khi redrive

1. Nguyên nhân đã được sửa và có test xác nhận.
2. Consumer version hỗ trợ schema của message.
3. Side effect đã được tra cứu/reconcile.
4. Idempotency/inbox retention còn hiệu lực.
5. Event ID, aggregate version và correlation metadata được giữ.
6. Batch/rate/concurrency có giới hạn.
7. Có dry-run và sample verification.
8. Có stop condition và người chịu trách nhiệm.
9. Audit record sẽ được tạo.
10. Có phương án rollback/pause nếu lỗi tái diễn.

### Sau khi redrive

1. Theo dõi DLQ depth và queue backlog.
2. Kiểm tra success/failure/duplicate rate.
3. Đối chiếu business state và provider reference.
4. Kiểm tra ordering/gap theo aggregate.
5. Xác nhận retry không lặp vô hạn.
6. Lưu kết quả batch và audit.
7. Đóng incident khi trạng thái broker và business đã nhất quán.

## 16. Azure Service Bus: Dead-letter subqueue

Azure Service Bus có dead-letter subqueue gắn với queue hoặc subscription. Message có thể được dead-letter bởi broker hoặc application.

### Các nguyên nhân thường gặp

- Delivery count vượt MaxDeliveryCount sau nhiều lần abandon/lock expiry.
- Message hết TTL khi dead-letter-on-expiration được cấu hình.
- Filter/rule hoặc forwarding operation thất bại trong một số luồng.
- Consumer chủ động gọi dead-letter vì payload/business error.
- Application đặt dead-letter reason/description để điều tra.

### Dead-letter reason và description

Khi application dead-letter message, nên dùng reason/code ổn định và description ngắn, không chứa secret hoặc payload nhạy cảm. Có thể thêm application properties cho failure category, consumer version và correlation reference.

### Redrive từ Service Bus DLQ

DLQ là subqueue riêng; ứng dụng/tool cần nhận message từ DLQ, xác minh và gửi lại vào entity đích theo quy trình. Khi gửi lại, giữ MessageId/event identity phù hợp với nghiệp vụ và thêm metadata replay nếu cần.

Các điểm phải kiểm tra:

- Duplicate detection window có thể ảnh hưởng message gửi lại với cùng MessageId.
- SessionId/partition/session semantics phải được giữ nếu cần ordering.
- TTL, scheduled enqueue time và application properties có thể cần được đặt lại theo mục tiêu redrive.
- DLQ có retention/quota và lifecycle riêng; không coi nó là archive vô hạn.
- Message có thể đã tạo side effect trước khi bị dead-letter; consumer vẫn cần inbox/idempotency.

Service Bus có cả transfer dead-letter scenario cho forwarding/transfer failure; phân biệt với dead-letter do consumer/application để tìm đúng nguyên nhân.

## 17. AWS SQS: redrive policy và DLQ

SQS sử dụng **redrive policy** để chuyển message từ source queue sang dead-letter queue sau khi số lần receive vượt ngưỡng MaxReceiveCount.

### Các khái niệm

- **Source queue:** queue gốc.
- **DLQ:** queue nhận message đã vượt ngưỡng.
- **maxReceiveCount:** số lần receive được phép theo policy trước khi chuyển DLQ.
- **Redrive allow policy:** kiểm soát source queue nào được phép dùng DLQ.
- **Visibility timeout:** khoảng thời gian message bị ẩn sau khi receive.
- **Redrive task:** thao tác đưa message từ DLQ trở lại source queue theo khả năng dịch vụ.

### Lưu ý khi vận hành

- SQS Standard có at-least-once delivery; duplicate vẫn có thể xảy ra.
- SQS FIFO có message group ordering và deduplication window riêng.
- MaxReceiveCount phản ánh receive count của broker, không phải số lần business handler hoàn tất.
- Visibility timeout quá ngắn có thể khiến message bị giao lại khi handler vẫn chạy.
- DLQ retention phải được cấu hình đủ dài cho điều tra và recovery; retention semantics có khác biệt giữa Standard và FIFO.
- Redrive rate cần giới hạn để không tạo tải đột biến lên source queue và downstream.
- Redrive không bảo đảm side effect trước đó chưa xảy ra.

### FIFO và thứ tự khi redrive

Với FIFO, message group và sequence/order có thể ảnh hưởng việc xử lý tiếp theo. Redrive nhiều message theo batch cần hiểu thứ tự mà dịch vụ đưa chúng trở lại source queue. Không giả định thao tác redrive toàn DLQ tự tái tạo chính xác business order của mọi group.

Kiểm tra message group ID, deduplication ID và business aggregate version trước khi redrive.

## 18. Google Cloud Pub/Sub: dead-letter topic

Pub/Sub hỗ trợ dead-letter topic thông qua dead-letter policy của subscription khi cấu hình phù hợp.

### Cách hoạt động

- Subscription có thể cấu hình dead-letter topic và maximum delivery attempts.
- Message vượt số lần delivery attempt theo semantics dịch vụ có thể được forward sang dead-letter topic.
- Delivery attempt count có thể mang tính ước lượng và phụ thuộc ACK/nack/client behavior; không coi nó là bộ đếm chính xác số lần handler đã chạy.
- Cần cấu hình IAM/service agent để Pub/Sub có quyền publish tới dead-letter topic và subscription nhận DLQ có quyền phù hợp.
- Dead-letter topic cần có subscription để message được giữ/đọc và điều tra theo retention.

### Redrive/replay

Pub/Sub không nên được coi như một thao tác chuyển ngược message tự động từ dead-letter topic về subscription gốc trong mọi trường hợp. Thông thường cần consumer/tool đọc dead-letter subscription rồi publish lại vào topic đích theo controlled replay.

Giữ event ID gốc trong payload/attributes, thêm replay metadata riêng và bảo đảm consumer idempotent. Kiểm tra region, topic/subscription retention, IAM và delivery attempt behavior trước khi vận hành.

## 19. Event Hubs và Kinesis: khi không có DLQ native như queue

Event Hubs và Kinesis là streaming services. Chúng không cung cấp cùng một dead-letter subqueue semantics như Service Bus hoặc SQS queue. Consumer application thường phải tự thiết kế failure store/quarantine.

### Azure Event Hubs

Có thể lưu event không xử lý được vào:

- Một Event Hubs khác dùng làm quarantine stream.
- Blob Storage/Data Lake làm archive.
- Database có trạng thái failure và metadata.
- Một queue/DLQ managed riêng.

Cần ghi partition ID, offset/sequence number, event ID, schema version và failure reason. Checkpoint chỉ tiến qua event sau khi event đã được xử lý hoặc lưu bền vững vào failure store theo policy. Nếu checkpoint trước khi lưu quarantine, event có thể bị bỏ qua.

### Amazon Kinesis Data Streams

Consumer Kinesis thường quản lý checkpoint theo shard. Khi handler thất bại:

- Retry record trong giới hạn.
- Ghi record lỗi vào SQS/S3/DynamoDB hoặc failure stream.
- Chỉ checkpoint qua record khi business effect hoặc failure record đã bền vững.
- Quản lý shard ordering và contiguous completion.
- Dùng event ID/sequence để deduplicate khi record được đọc lại.

Không checkpoint qua record lỗi nếu chưa lưu bằng chứng và quyết định rõ policy. Một record lỗi có thể chặn shard; cần chọn giữa retry, quarantine bền vững hoặc skip có audit.

### Failure store phải bền vững

Nếu consumer chỉ log payload rồi checkpoint, log retention không đủ để đảm bảo replay. Lưu payload/reference và metadata vào nơi có retention, quyền truy cập, encryption và quy trình replay phù hợp.

## 20. Spring Boot/Spring Cloud Stream: dead-letter behavior phụ thuộc binder

Spring Cloud Stream cung cấp function model, nhưng DLQ, retry và settlement là khả năng cụ thể của binder/provider.

Một consumer minh họa:

~~~java
@Bean
Consumer<Message<OrderCreated>> orderCreated(
        OrderEventHandler handler) {
    return message -> handler.handle(message.getPayload());
}
~~~

Không thể suy ra chỉ từ function này rằng message sẽ tự chuyển vào DLQ khi handler ném exception.

### Cần xác minh ở binder

- Binder có hỗ trợ DLQ/dead-letter topic không?
- Tên DLQ và provisioning được cấu hình thế nào?
- Retry xảy ra trong binder, SDK hay application layer?
- Max attempts có tính lần đầu không?
- Exception nào được retry, exception nào bị bỏ qua?
- Khi hết retry, binder dead-letter hay reject/nack message?
- Có giữ original headers, partition key, session ID và message ID không?
- Manual acknowledgment có cần thiết không?
- Với batch consumer, một record lỗi ảnh hưởng cả batch hay chỉ record đó?
- Redrive/replay tool có nằm trong binder hay cần native SDK?

### Tránh nhiều tầng retry chồng nhau

Nếu binder retry 3 lần, Azure/AWS/GCP SDK cũng retry nội bộ và application service lại retry thêm, tổng request có thể tăng theo tích số. DLQ chỉ nên nhận message sau khi retry owner đã dùng hết ngân sách được phân công.

### Phân loại exception

Không để mọi exception trở thành retryable. Có thể định nghĩa exception nội bộ:

~~~java
public class PermanentMessageException extends RuntimeException {
    public PermanentMessageException(String message) {
        super(message);
    }
}

public class RetryableDependencyException extends RuntimeException {
    public RetryableDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Binder configuration phải map các exception này theo khả năng của version. Nếu binder không hỗ trợ phân loại như mong muốn, xử lý trong application layer và dùng native settlement API theo contract.

## 21. Replay tool/job: thiết kế để vận hành an toàn

Một công cụ replay không nên chỉ là vòng lặp đọc DLQ rồi gửi lại. Nó cần hỗ trợ chọn lọc, dry-run, audit, giới hạn tải và dừng khẩn cấp.

### Các thành phần

| Thành phần | Trách nhiệm |
| --- | --- |
| **Selector** | Chọn message theo ID, failure code, thời gian, tenant hoặc schema |
| **Validator** | Kiểm tra payload, schema, business precondition và side effect |
| **Planner** | Ước tính batch size, rate và thứ tự |
| **Executor** | Redrive/replay theo batch |
| **Rate controller** | Giới hạn tốc độ/concurrency |
| **Audit writer** | Lưu ai chạy, lý do, batch, kết quả |
| **Monitor** | Theo dõi lỗi, duplicate, backlog và downstream load |
| **Stop controller** | Dừng khi vượt threshold hoặc có yêu cầu incident commander |

### Chế độ dry-run

Dry-run có thể kiểm tra:

- Message có deserialize được không.
- Schema version có được hỗ trợ không.
- Event ID đã tồn tại trong inbox chưa.
- Aggregate version có stale/gap không.
- Provider operation reference có side effect trước đó không.
- Target queue/topic có đúng không.
- Message có chứa metadata cần thiết không.

Dry-run không được gọi side effect. Nếu một bước validation cần truy vấn external provider, chỉ dùng API đọc/tra cứu có kiểm soát.

### Audit record

Một replay batch record có thể chứa:

~~~json
{
  "replayBatchId": "replay-2026-11-24-001",
  "source": "orders-dlq",
  "target": "orders",
  "selector": {
    "failureCode": "ORDER_EVENT_VERSION_UNSUPPORTED",
    "schemaVersion": 3
  },
  "requestedBy": "recovery-service",
  "reason": "Consumer upgraded to support schema v3",
  "dryRun": false,
  "startedAt": "2026-11-24T11:00:00Z"
}
~~~

Không đưa payload nhạy cảm vào audit record. Lưu message ID/hash và tham chiếu tới kho dữ liệu được bảo vệ.

## 22. Recovery khi có side effect một phần

Một workflow có thể thực hiện nhiều bước:

~~~text
1. Ghi order database
2. Upload document Blob
3. Publish DocumentCreated
4. Gửi notification
~~~

Nếu bước 3 lỗi, message có thể vào DLQ dù bước 1 và 2 đã thành công. Redrive toàn bộ workflow có thể tạo duplicate order/blob hoặc gửi notification trùng.

### Dùng state machine để tiếp tục từ bước chưa hoàn tất

Lưu trạng thái theo operation:

| Bước | Trạng thái |
| --- | --- |
| Order persisted | SUCCEEDED |
| Blob uploaded | SUCCEEDED |
| Event published | PENDING |
| Notification sent | NOT_STARTED |

Recovery worker đọc state và chỉ tiếp tục bước còn thiếu. Mỗi bước cần idempotency key hoặc conditional write riêng.

### Compensation

Nếu không thể tiếp tục workflow, có thể cần compensation:

- Xóa Blob orphan nếu chưa được tham chiếu và policy cho phép.
- Giải phóng reservation.
- Tạo reversal/refund thay vì xóa ledger.
- Phát cancellation/correction event.
- Đánh dấu operation FAILED_FINAL sau khi đối soát.

Compensation là một business action mới có audit, không phải rollback tự động của các hệ thống ngoài.

## 23. Replay projection và replay side effect phải tách biệt

Replay toàn bộ event history để dựng read model khác với replay command để thực hiện payment/email.

| Replay type | Mục tiêu | Quy tắc |
| --- | --- | --- |
| **Projection rebuild** | Dựng lại read model/search index/cache | Dùng projection version/consumer riêng; có thể reset target có kiểm soát |
| **Operational redrive** | Xử lý lại message đã thất bại | Giữ identity, inbox và business state; chỉ tiếp tục bước chưa hoàn tất |
| **External side-effect replay** | Thử lại payment/email/API | Cần provider idempotency, reconciliation hoặc approval theo business policy |
| **Historical backfill** | Nạp dữ liệu lịch sử | Tách pipeline, rate limit và kiểm tra duplicate |
| **Correction/reprocessing** | Sửa dữ liệu sai | Tạo correction event/audit, không giả vờ là event gốc mới |

Không dùng consumer gửi email/payment production để rebuild projection. Có thể tạo một consumer projection-only không có quyền side effect bên ngoài.

## 24. Metrics và cảnh báo cho DLQ/recovery

| Metric | Ý nghĩa |
| --- | --- |
| dlq_message_count | Số message hiện nằm trong DLQ |
| dlq_oldest_message_age_seconds | Tuổi message cũ nhất trong DLQ |
| dlq_ingress_rate | Tốc độ message đi vào DLQ |
| dlq_failure_category_total | Phân bố nguyên nhân dead-letter |
| redrive_attempts_total | Số lần redrive |
| redrive_success_total | Số message redrive được chấp nhận |
| redrive_failed_total | Số redrive thất bại |
| replay_batch_rate | Tốc độ phát lại |
| replay_duplicate_total | Số message replay bị dedupe |
| business_effect_reconciled_total | Số operation đã đối soát |
| unknown_outcome_backlog | Số operation chưa xác định kết quả |
| quarantine_count | Số message cần xử lý thủ công |
| consumer_retry_exhausted_total | Số operation hết retry budget |
| downstream_throttle_total | Số lỗi throttling trong recovery |

### Cảnh báo nên có

- DLQ depth tăng đột biến.
- Oldest message age vượt SLA xử lý.
- Một failure code chiếm tỷ trọng lớn.
- Redrive đang chạy nhưng error rate tăng.
- Duplicate/business conflict tăng trong replay.
- Downstream 429/503 tăng do recovery load.
- Unknown outcome backlog tăng.
- DLQ gần chạm retention/quota.
- Replay batch chạy quá lâu hoặc không có tiến triển.

Không dùng message ID, aggregate ID hoặc tenant ID làm metric label cardinality cao. Dùng log/trace có masking và audit reference.

## 25. Bài thực hành: khôi phục Order consumer sau incident

**Bối cảnh:** Order consumer của Spring Boot xử lý message từ Azure Service Bus hoặc AWS SQS. Sau một lần deploy schema mới, 12.000 message vào DLQ. Một phần message có thể đã cập nhật database nhưng ACK/Complete thất bại. Một số message chưa deserialize được. Consumer mới đã được sửa để hỗ trợ schema cũ và mới.

### Phần A — Điều tra

1. Ghi nhận DLQ depth, oldest age, queue backlog và thời điểm deploy.
2. Nhóm message theo failure code, schema version và consumer version.
3. Chọn sample và kiểm tra payload/hash.
4. Tra cứu inbox/business state để xác định message đã commit chưa.
5. Tra cứu provider reference cho các side effect ngoài.
6. Phân loại chưa xử lý, đã xử lý, partial và unknown outcome.

### Phần B — Sửa nguyên nhân

1. Triển khai consumer có schema compatibility.
2. Kiểm tra RBAC/identity và dependency health.
3. Xác minh handler có transaction/inbox đúng.
4. Kiểm thử duplicate delivery và crash sau commit trước ACK.
5. Xác minh message ID/event ID được giữ qua redrive.
6. Chạy dry-run trên sample DLQ.

### Phần C — Controlled redrive

1. Chọn 100 message thuộc một schema/failure category đã sửa.
2. Redrive batch nhỏ với rate limit thấp.
3. Theo dõi success, duplicate, 429/503 và downstream latency.
4. Đối chiếu số business operation được commit.
5. Tăng batch/rate theo capacity thực tế.
6. Dừng ngay nếu error/duplicate/unknown outcome tăng bất thường.
7. Giữ các message chưa đủ điều kiện trong quarantine.

### Phần D — Đóng incident

1. Đối chiếu queue, DLQ, archive và business database.
2. Xác minh không mất event và không tạo duplicate ledger/order.
3. Xử lý unknown outcome qua reconciliation.
4. Kiểm tra ordering theo aggregate version.
5. Lưu replay audit và incident timeline.
6. Bổ sung alert/runbook và test để ngăn tái diễn.

### Sản phẩm cần nộp

- Bảng phân loại lỗi và chính sách retry/dead-letter.
- Schema failure metadata và replay audit.
- Runbook triage, dry-run, redrive và reconciliation.
- Cấu hình DLQ/redrive theo broker.
- Kết quả test crash window, duplicate, schema incompatibility và replay.
- Metrics DLQ depth, oldest age, redrive rate, duplicate và unknown outcome.

### Câu hỏi tự kiểm tra

1. Vì sao DLQ không chứng minh message chưa tạo side effect?
2. Poison message khác transient failure thế nào?
3. Khi nào nên retry queue và khi nào nên dead-letter?
4. Vì sao unknown outcome cần reconciliation trước redrive?
5. Redrive khác replay projection ở điểm nào?
6. Vì sao phải giữ event ID gốc khi phát lại cùng event?
7. Tại sao replay toàn bộ DLQ một lần có thể gây incident thứ hai?
8. Vì sao inbox retention phải bao phủ DLQ/replay window?
9. Azure Service Bus DLQ khác SQS DLQ và Pub/Sub dead-letter topic ở đâu?
10. Vì sao Event Hubs/Kinesis cần failure store do ứng dụng thiết kế?
11. MaxReceiveCount/delivery attempt có phải số lần business handler đã chạy không?
12. Vì sao Spring Cloud Stream DLQ behavior phải xác minh theo binder?
13. Làm sao tiếp tục workflow khi database và Blob đã thành công nhưng publish thất bại?
14. Khi nào projection rebuild cần consumer riêng?
15. Những điều kiện nào phải đạt trước khi đóng incident DLQ?

## 26. Ghi nhớ

- DLQ cô lập message lỗi để điều tra và phục hồi; nó không sửa business state, không chứng minh side effect chưa xảy ra và không phải archive vô hạn.
- Phân biệt transient, permanent, business rejection, poison message và unknown outcome trước khi retry/dead-letter.
- Giữ message/event identity, payload, schema, aggregate version, delivery metadata và failure reason có cấu trúc; không đưa secret vào DLQ metadata/log.
- Trước redrive, xác minh side effect, idempotency/inbox state, schema compatibility, ordering và nguyên nhân đã được sửa.
- Redrive/replay cần dry-run, batch nhỏ, rate/concurrency limit, audit, stop condition và đối soát sau xử lý.
- Giữ event ID gốc khi phát lại cùng event; dùng identity mới cho một business command/event mới.
- Service Bus, SQS và Pub/Sub có DLQ/redrive semantics riêng; Event Hubs/Kinesis cần failure store/quarantine do ứng dụng thiết kế.
- Spring Cloud Stream DLQ, retry và ACK behavior phụ thuộc binder/version; tránh retry lồng nhau không có ngân sách tổng.
- Side effect một phần cần state machine, provider idempotency, reconciliation hoặc compensation; không chạy lại toàn workflow một cách mù quáng.
- Đóng incident khi broker backlog, DLQ, business state, external provider và unknown outcome đã được đối soát.

## Tài liệu tham khảo

- [Azure Service Bus dead-letter queues](https://learn.microsoft.com/azure/service-bus-messaging/service-bus-dead-letter-queues)
- [Azure Service Bus message locks and settlement](https://learn.microsoft.com/azure/service-bus-messaging/message-transfers-locks-settlement)
- [Azure Event Hubs features and consumer groups](https://learn.microsoft.com/azure/event-hubs/event-hubs-features)
- [Amazon SQS dead-letter queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Amazon SQS redrive to source queues](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-configure-dead-letter-queue-redrive.html)
- [Amazon SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Google Cloud Pub/Sub dead-letter topics](https://cloud.google.com/pubsub/docs/dead-letter-topics)
- [Google Cloud Pub/Sub subscription overview](https://cloud.google.com/pubsub/docs/subscription-overview)
- [Spring Cloud Stream reference](https://docs.spring.io/spring-cloud-stream/reference/)
- [Transactional outbox pattern](https://learn.microsoft.com/azure/architecture/databases/guide/transactional-outbox-cosmos)
- [AWS Prescriptive Guidance — Retry with backoff](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/retry-backoff.html)
