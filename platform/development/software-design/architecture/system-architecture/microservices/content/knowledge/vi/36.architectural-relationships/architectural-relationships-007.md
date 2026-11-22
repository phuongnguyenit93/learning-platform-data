# Serverless trong triển khai một số năng lực của hệ thống

## 1. Serverless là gì và giải quyết bài toán nào?

**Serverless** là mô hình triển khai trong đó đội phát triển tập trung vào logic ứng dụng và hợp đồng dịch vụ, còn nền tảng cloud quản lý phần lớn việc cấp phát, vận hành và mở rộng hạ tầng thực thi. “Không máy chủ” không có nghĩa ứng dụng không chạy trên server; nó có nghĩa nhóm phát triển không phải tự quản lý trực tiếp vòng đời máy chủ cho từng workload như mô hình truyền thống.

Serverless thường xuất hiện dưới hai nhóm dịch vụ:
- **Function as a Service (FaaS):** chạy một function hoặc handler khi có HTTP request, message, event, lịch chạy hoặc trigger khác.
- **Managed serverless services:** dịch vụ dữ liệu, messaging, API, workflow hoặc compute có khả năng tự cấp phát/mở rộng theo yêu cầu và giảm phần vận hành hạ tầng.

Ví dụ trong một hệ thống thương mại điện tử:
- API checkout và order cốt lõi có thể tiếp tục chạy trên Kubernetes hoặc container service vì cần kiểm soát latency, kết nối và runtime lâu dài.
- Xử lý ảnh sản phẩm có thể chạy bằng function khi object được upload.
- Gửi email xác nhận có thể được kích hoạt từ event OrderCreated.
- Tạo báo cáo định kỳ có thể dùng scheduled function hoặc workflow.
- Webhook từ đối tác có thể được xử lý bằng một endpoint serverless với xác thực, idempotency và hàng đợi bền vững.

Serverless có ích khi workload có tính sự kiện, lưu lượng thay đổi, tác vụ ngắn hoặc nhu cầu vận hành hạ tầng tối thiểu. Nó cũng tạo ra những ràng buộc riêng: cold start, timeout, giới hạn runtime, concurrency, quota, chi phí theo request/thời gian, quan sát phân tán và phụ thuộc nhà cung cấp.

**Không có yêu cầu nào buộc toàn bộ hệ thống phải chuyển sang serverless.** Một kiến trúc có thể kết hợp container, Kubernetes, managed database, queue và FaaS theo đặc tính của từng năng lực. Câu hỏi thiết kế là: thành phần nào hưởng lợi từ mô hình event-driven/managed execution, và thành phần nào cần runtime ổn định, kết nối lâu dài, kiểm soát latency hoặc tài nguyên chuyên biệt?

Sau bài học, người học có thể:
1. Giải thích serverless, FaaS, BaaS và managed serverless service.
2. So sánh serverless với VM, container và Kubernetes theo workload.
3. Thiết kế function handler có trigger, contract, idempotency và giới hạn thời gian.
4. Tích hợp serverless vào microservices qua API, event, queue và workflow.
5. Quản lý cold start, concurrency, retries, dead-letter và duplicate delivery.
6. Bảo vệ IAM, secret, network, input validation và dữ liệu.
7. Đo latency, error, invocation, duration, concurrency và chi phí.
8. Đưa ra tiêu chí chọn serverless cho từng capability thay vì chuyển đổi theo xu hướng.

## 2. Các thành phần trong hệ sinh thái serverless

### 2.1. Function as a Service

FaaS cho phép triển khai function hoặc handler mà nền tảng gọi khi có trigger. Người phát triển thường cung cấp code, runtime, cấu hình, permission và giới hạn tài nguyên; nền tảng chịu trách nhiệm khởi tạo execution environment, scale và thu hồi tài nguyên theo mô hình dịch vụ.

Một function thường có:
- **Trigger:** HTTP request, queue message, object event, schedule, stream record hoặc event bus.
- **Handler:** điểm vào xử lý event.
- **Runtime:** Java, Node.js, Python, .NET hoặc runtime được hỗ trợ.
- **Configuration:** memory, CPU theo nền tảng, timeout, concurrency, environment variables.
- **Identity/permissions:** quyền đọc secret, ghi object, publish event hoặc gọi API.
- **Observability:** logs, metrics, traces, invocation ID.
- **Deployment artifact:** package, container image hoặc bundle.

### 2.2. Backend as a Service và managed services

BaaS cung cấp các năng lực backend có sẵn như authentication, object storage, database, push notification hoặc API. Managed serverless service có thể cung cấp database, queue, workflow, API gateway hoặc event bus mà không yêu cầu đội ứng dụng tự quản lý toàn bộ máy chủ.

Không phải mọi managed service đều là FaaS. Một managed database vẫn là database; một event bus vẫn là event bus. “Serverless” mô tả cách nền tảng cung cấp và tính phí/vận hành, không thay đổi trách nhiệm về schema, dữ liệu, quyền truy cập và consistency.

### 2.3. Event source và event router

Event source tạo ra sự kiện; router/bus chọn đích dựa trên rule; function hoặc service consumer xử lý. Ví dụ:
- Object storage phát event khi file mới được tạo.
- Event bus nhận OrderCreated.
- Rule lọc event theo loại và metadata.
- Function gửi email hoặc cập nhật read model.

Cần phân biệt **event notification** với **durable event log/queue**. Một thông báo object-created có thể chỉ báo “có file mới”; nếu consumer mất event và không có retry/replay, hệ thống cần reconciliation hoặc quét lại object state.

## 3. Serverless trong bức tranh kiến trúc tổng thể

Một hệ thống có thể kết hợp các loại runtime:

~~~mermaid
flowchart TD
    C[Web / Mobile] --> G[API Gateway]
    G --> K[Core services on containers]
    K --> DB[(Operational database)]
    K --> EB[Event bus / Queue]
    EB --> F1[Serverless function: notifications]
    EB --> F2[Serverless function: image processing]
    S[Object storage upload] --> F2
    T[Scheduled trigger] --> WF[Serverless workflow]
    WF --> R[Reporting / export workers]
    F1 --> P[Email / SMS provider]
    F2 --> O[Processed object storage]
    R --> W[(Analytics store)]
~~~

Sơ đồ là ví dụ khái niệm. Core service có thể chạy trên Kubernetes, container platform hoặc serverless container tùy nhu cầu. Serverless functions được dùng cho các tác vụ event-driven có ranh giới rõ. Database và event bus có thể là managed service nhưng vẫn cần ownership, backup, retention và DR.

### 3.1. Serverless là lựa chọn ở cấp capability

Một capability là một năng lực nghiệp vụ/kỹ thuật đủ rõ, ví dụ:
- Chuyển đổi ảnh sau upload.
- Gửi notification sau khi order confirmed.
- Tính điểm loyalty khi có transaction event.
- Nhận webhook từ đối tác.
- Tổng hợp số liệu theo lịch.
- Làm sạch file tạm theo lifecycle policy.

Không nhất thiết tách mỗi capability thành một function nhỏ. Chia quá vụn làm tăng số lượng deployment, IAM policies, traces, queues và hợp đồng event. Cần chọn ranh giới dựa trên ownership, thay đổi, scaling, timeout và blast radius.

### 3.2. Phần nào vẫn nên là service chạy liên tục?

Các workload sau có thể phù hợp container/service dài hạn:
- HTTP API cần latency ổn định và lưu lượng đều cao.
- Kết nối WebSocket hoặc streaming kéo dài.
- Worker tiêu thụ stream liên tục với state local/connection pool lâu dài.
- Tác vụ cần thư viện native, runtime tùy chỉnh hoặc thời gian xử lý vượt giới hạn FaaS.
- Workload có chi phí serverless cao do chạy liên tục ở concurrency lớn.
- Thành phần cần kiểm soát networking, kernel/runtime hoặc tài nguyên đặc biệt.

Đây là xu hướng, không phải luật. Một serverless container hoặc managed service có thể đáp ứng nhiều trường hợp; cần đo trên nền tảng thực tế.

## 4. So sánh serverless, VM, container và Kubernetes

| Tiêu chí | VM | Container tự quản lý | Kubernetes | Serverless FaaS |
| --- | --- | --- | --- | --- |
| Đơn vị triển khai | Máy ảo/OS | Container | Pod/workload | Function/handler |
| Quản lý host | Đội vận hành | Đội vận hành hoặc managed platform | Platform/SRE | Nhà cung cấp phần lớn |
| Scale | VM/ASG | Replica/orchestrator | HPA/cluster autoscaler | Theo invocation/concurrency |
| Thời gian chạy | Dài | Dài hoặc theo job | Dài hoặc job | Thường giới hạn theo invocation |
| Networking | Kiểm soát rộng | Tùy nền tảng | Kiểm soát qua service/network policy | Theo tích hợp và giới hạn provider |
| Connection reuse | Chủ động | Chủ động | Chủ động | Có thể reuse trong execution environment nhưng không bảo đảm lâu dài |
| Cold start | Khởi động VM/app | Khởi động container | Scheduling/image/startup | Có thể xảy ra khi tạo execution environment |
| Billing | Thường theo tài nguyên/thời gian | Theo node/container | Theo cluster/node/resource | Thường theo invocation, duration và tài nguyên |
| Phù hợp | Workload đặc thù, legacy | Service đóng gói | Nền tảng nhiều workload | Event-driven, bursty, tác vụ ngắn |

Kubernetes có thể tự động scale pod nhưng vẫn yêu cầu quản lý cluster, node capacity, scheduling, upgrade và networking. FaaS giảm phần đó nhưng chuyển sang giới hạn execution, concurrency, package và provider integration.

### 4.1. So sánh chi phí thực tế

Không nên so sánh “serverless trả tiền theo request” với “Kubernetes luôn phải trả tiền cả ngày” một cách đơn giản. Một workload serverless cần tính:
- Invocation/request count.
- Duration và memory/CPU allocation.
- Concurrency provisioned/minimum instances nếu có.
- API gateway, event bus, logs, traces và network egress.
- Retry, duplicate và failed invocation.
- Data store và connection overhead.
- Cold start hoặc provisioned capacity.

Container cần tính node idle capacity, autoscaling, license, control plane, operations, patching và SRE effort. Một workload chạy liên tục 80% capacity có thể rẻ hơn trên container; một job chỉ chạy vài giây mỗi giờ có thể phù hợp serverless hơn.

Tính tổng chi phí sở hữu (TCO), không chỉ giá compute.

## 5. Chọn capability phù hợp với serverless

Một quyết định ban đầu có thể dùng các câu hỏi:

| Câu hỏi | Nếu câu trả lời là “có” | Tác động tới lựa chọn |
| --- | --- | --- |
| Công việc được kích hoạt bởi event rõ ràng? | Có | FaaS thường phù hợp |
| Thời gian xử lý nằm trong giới hạn nền tảng? | Có | FaaS khả thi |
| Workload bursty hoặc không đều? | Có | Auto-scale có lợi |
| Có thể xử lý duplicate/idempotent? | Có | Dễ vận hành event-driven |
| Cần connection/session kéo dài? | Có | Cân nhắc container/service |
| Cần latency rất ổn định, cold start thấp? | Có | Cân nhắc provisioned capacity hoặc container |
| Cần runtime/kernel/library đặc biệt? | Có | Kiểm tra giới hạn FaaS hoặc dùng container |
| Traffic cao, đều và liên tục? | Có | So sánh TCO với container |
| Cần chạy lâu hơn giới hạn invocation? | Có | Dùng workflow/queue chia bước hoặc worker lâu dài |
| Có thể chấp nhận phụ thuộc cloud provider? | Có | Đánh giá lock-in và portability |

Không có điểm số chung phù hợp mọi tổ chức. Hãy đánh giá theo latency, throughput, cost, operational burden, security và khả năng recovery.

### 5.1. Ma trận capability ví dụ

| Capability | Mô hình có thể phù hợp | Lý do và lưu ý |
| --- | --- | --- |
| Image thumbnail sau upload | Function | Trigger rõ, workload độc lập; giới hạn kích thước và thời gian |
| Gửi email sau OrderCreated | Function/queue worker | Bất đồng bộ, retry và DLQ; cần idempotency |
| REST checkout API tải đều | Container hoặc serverless container | Cần latency và connection behavior dự đoán được |
| WebSocket chat lâu dài | Container/managed realtime | Kết nối kéo dài không phù hợp invocation ngắn |
| Báo cáo chạy hàng đêm | Scheduled function/workflow/batch | Cần checkpoint nếu thời gian dài |
| Webhook đối tác | API gateway + function/queue | ACK nhanh, xử lý bền qua queue |
| Stream processing liên tục | Managed stream processing/containers | State, ordering, throughput và checkpoint |
| Cleanup file hết hạn | Scheduled function + object lifecycle | Nên ưu tiên lifecycle policy khi đủ khả năng |
| Payment authorization | Core service/managed integration | Correctness, idempotency và audit rất quan trọng |
| ML inference lớn | Managed inference/container | Model load, GPU, warm capacity và latency |

Bảng chỉ là gợi ý để bắt đầu đánh giá. Payment có thể dùng serverless trong một thiết kế phù hợp, nhưng yêu cầu transaction, timeout, reconciliation và bảo mật vẫn giữ nguyên.

## 6. Thiết kế function handler

Một handler tốt cần nhỏ về trách nhiệm nhưng đầy đủ về hợp đồng:
1. Nhận event/request theo schema đã định.
2. Xác minh nguồn và quyền.
3. Kiểm tra version/schema.
4. Validate payload và kích thước.
5. Kiểm tra idempotency/deduplication.
6. Thực hiện một bước nghiệp vụ có giới hạn.
7. Ghi state hoặc phát event tiếp theo một cách bền vững.
8. Trả kết quả/ACK theo semantics của trigger.
9. Ghi log/metric/trace với correlation.
10. Xử lý lỗi theo retryable/permanent classification.

Pseudocode:

~~~text
handler(event, context):
    validateEventEnvelope(event)
    identity = authenticateEventSource(event.source)
    tenant = resolveTrustedTenant(event, identity)
    if alreadyProcessed(event.id, tenant):
        return success

    result = executeBoundedBusinessStep(event, tenant)

    persistResultAndOutbox(result)
    markProcessed(event.id, tenant)
    return success
~~~

Đây là logic minh họa. Trong thực tế, deduplication và persist business state phải có transaction hoặc cơ chế atomic phù hợp. Không đánh dấu processed trước khi side effect bền vững; nếu process chết giữa hai bước, event có thể bị mất logic.

### 6.1. Function phải stateless về mặt execution environment

Execution environment có thể được reuse, nhưng provider có thể tạo mới hoặc thu hồi bất kỳ lúc nào. Không lưu trạng thái nghiệp vụ duy nhất trong biến global, local file hoặc memory giữa các invocation.

Có thể reuse:
- HTTP client.
- Database client/pool nếu platform và runtime hỗ trợ phù hợp.
- Immutable configuration.
- Connection manager.
- Compiled regex/serializer.

Không được giả định:
- Cùng một instance xử lý lần kế tiếp.
- Global variable là durable store.
- Temporary filesystem tồn tại vĩnh viễn.
- Scheduled function chỉ chạy một lần.
- Một event không bao giờ được gửi lại.

## 7. Trigger và event sources

### 7.1. HTTP/API trigger

Function có thể được gọi qua API Gateway hoặc HTTP endpoint. Cần xác định:
- Authentication/authorization.
- Request size limit.
- Rate limit/quota.
- Timeout gateway và function.
- CORS nếu browser truy cập.
- Response contract.
- Streaming support.
- Retry behavior của caller/gateway.

Với command dài, endpoint nên ghi job bền rồi trả 202 thay vì giữ HTTP connection tới hết công việc.

### 7.2. Queue trigger

Queue giúp tách producer khỏi consumer và hấp thụ burst. Cần cấu hình:
- Visibility/ack timeout.
- Max receive/delivery attempts.
- Retry/backoff.
- Dead-letter queue.
- Batch size và batch failure behavior.
- Concurrency cap.
- Message retention.
- Idempotency và ordering.

Nếu một batch có 10 message, 9 message thành công và 1 lỗi, behavior retry phụ thuộc nền tảng: có thể gửi lại cả batch hoặc chỉ item lỗi nếu partial batch response được bật. Consumer phải chịu duplicate.

### 7.3. Object storage trigger

Upload file có thể kích hoạt function:
- Kiểm tra object key, tenant ownership và metadata.
- Validate kích thước/content type thật.
- Quét malware hoặc kiểm tra file format khi cần.
- Xử lý version/object generation để không xử lý nhầm overwrite.
- Ghi output vào prefix/bucket riêng và chống loop trigger.
- Idempotent theo object version/event ID.

Không tin extension `.jpg` là file ảnh hợp lệ. Không cho function đọc URL tùy ý từ metadata mà không kiểm soát SSRF.

### 7.4. Schedule trigger

Scheduled function phù hợp tác vụ định kỳ ngắn hoặc điều phối workflow. Scheduler có thể phát event trễ, duplicate hoặc retry theo semantics của provider. Cần:
- Idempotency theo business date/window.
- Timezone rõ ràng.
- Xử lý daylight saving nếu lịch dùng local time.
- Lock/lease hoặc unique constraint chống hai lần chạy đồng thời.
- Catch-up policy khi hệ thống downtime.
- Timeout và checkpoint nếu job dài.

### 7.5. Stream trigger

Stream processor đọc record liên tục và cần hiểu partition, ordering, offset/checkpoint, retry và poison message. Một record lỗi có thể chặn partition hoặc làm lặp các record sau. Cần policy cô lập lỗi, DLQ/quarantine, checkpoint sau khi xử lý bền và kiểm soát concurrency.

## 8. Event envelope và schema compatibility

Một event nên có envelope nhất quán:

~~~json
{
  "eventId": "evt-7f31",
  "eventType": "OrderCreated",
  "schemaVersion": 2,
  "occurredAt": "2026-11-12T09:00:00Z",
  "producer": "order-service",
  "tenantId": "tenant-42",
  "correlationId": "corr-123",
  "aggregateId": "order-1001",
  "aggregateVersion": 7,
  "data": {
    "orderId": "order-1001",
    "currency": "VND",
    "totalAmount": "1250000.00"
  }
}
~~~

Payload minh họa, không phải schema bắt buộc. Cần:
- Event ID duy nhất.
- Event type và schema version.
- Producer identity đáng tin.
- Tenant scope nếu dữ liệu multi-tenant.
- Correlation/causation ID.
- Aggregate ID/version nếu cần ordering.
- Timestamp có nguồn và timezone rõ.
- Payload tối thiểu cần cho consumer.

Schema compatibility nên ưu tiên additive changes và consumer chịu được field mới khi phù hợp. Không đổi meaning field mà giữ nguyên version. Schema registry có thể enforce compatibility, nhưng không tự xác minh logic nghiệp vụ.

## 9. At-least-once delivery và idempotency

Nhiều event source giao message theo at-least-once: cùng một event có thể được xử lý nhiều lần do timeout, crash hoặc ACK bị mất. FaaS không tự làm consumer exactly-once end-to-end.

Ví dụ OrderCreated được giao hai lần:
- Nếu function gửi email trực tiếp hai lần, khách nhận hai email.
- Nếu function cộng loyalty points hai lần, số điểm sai.
- Nếu function tạo invoice hai lần, phát sinh nghiệp vụ trùng.

Cách xử lý:
1. Chọn idempotency key như eventId hoặc business operation ID.
2. Lưu trạng thái đã xử lý trong durable store.
3. Ràng buộc unique key trong database để chống race.
4. Thực hiện side effect và đánh dấu processed bằng transaction/outbox hoặc protocol phù hợp.
5. Với external provider, truyền idempotency key nếu API hỗ trợ.
6. Xác định retention của dedup record đủ dài theo retry/replay window.
7. Có reconciliation khi không biết external side effect đã xảy ra chưa.

Ví dụ bảng:

~~~sql
CREATE TABLE processed_events (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer có thể insert với conflict handling trong cùng transaction với cập nhật state. Nếu side effect nằm ngoài database, cần outbox/saga và trạng thái operation; một transaction local không thể atomically commit với email provider hay payment API.

### 9.1. Idempotency theo business key

Event ID giúp deduplicate một message. Nhưng hai event khác ID có thể đại diện cùng business intent. Ví dụ client gửi hai lệnh tạo order khác correlation ID do retry sai cách. Khi cần, dùng idempotency key ở API command, unique constraint theo tenant/operation và request fingerprint.

## 10. Retry, backoff và Dead-Letter Queue

Một function lỗi tạm thời có thể được retry. Lỗi vĩnh viễn như payload sai schema hoặc quyền bị từ chối không nên retry mãi.

Phân loại:
- **Transient:** timeout mạng, rate limit, dependency tạm unavailable.
- **Permanent:** schema invalid, business rule reject, unsupported event version.
- **Unknown outcome:** request tới provider có thể đã thành công nhưng response mất.
- **Poison message:** một message luôn gây crash/exception hoặc vượt resource limit.

Retry policy cần:
- Số lần tối đa hoặc thời gian retry.
- Exponential backoff và jitter.
- Retry budget.
- Visibility/ack timeout đủ dài so với thời gian xử lý và buffer.
- Phân biệt lỗi item-level và batch-level.
- DLQ/quarantine sau ngưỡng.
- Cảnh báo và công cụ redrive có kiểm soát.

### 10.1. DLQ không phải thùng rác

DLQ giữ message chưa xử lý thành công để điều tra và khôi phục. Cần:
- Owner của queue và DLQ.
- Metric depth/age.
- Alert khi xuất hiện poison message hoặc backlog tăng.
- Quy trình đọc lỗi, sửa nguyên nhân và redrive.
- Kiểm tra idempotency trước replay.
- Giới hạn batch redrive để tránh quá tải.
- Retention và bảo vệ dữ liệu nhạy cảm.

Không redrive hàng triệu message vào một consumer đang yếu mà không rate limit. Không xóa DLQ chỉ để dashboard về zero.

## 11. Timeout, execution duration và deadline

FaaS thường có giới hạn thời gian invocation theo provider/runtime/plan. Phải kiểm tra giới hạn hiện hành và cấu hình timeout rõ ràng.

Một function nên:
- Có deadline tổng nhỏ hơn timeout nền tảng một khoảng an toàn.
- Timeout từng dependency nhỏ hơn thời gian còn lại.
- Dừng nhận công việc mới khi gần hết deadline.
- Ghi checkpoint nếu công việc có thể chia bước.
- Tránh giữ transaction mở khi chờ external HTTP.
- Đưa tác vụ dài sang workflow/queue/batch worker.
- Không giả định function timeout nghĩa side effect đã rollback.

Ví dụ function có timeout 30 giây:
- 2 giây cho khởi tạo/parse/validate.
- 5 giây cho database.
- 8 giây cho provider API.
- 5 giây cho persist result/outbox.
- Phần còn lại dành cho retry hợp lệ, cleanup và response.

Các số chỉ minh họa. Nếu mỗi dependency có timeout 10 giây và function gọi tuần tự ba dependency, tổng có thể vượt 30 giây. Phải phân bổ deadline theo call graph.

### 11.1. API Gateway và function timeout

Gateway có thể có giới hạn integration timeout riêng. Nếu gateway dừng chờ trước function, function có thể vẫn tiếp tục chạy. Client retry có thể kích hoạt side effect trùng. Nên dùng idempotency và async operation resource cho tác vụ dài.

## 12. Cold start và warm execution environment

**Cold start** xảy ra khi nền tảng phải chuẩn bị execution environment mới trước khi chạy handler. Thời gian có thể gồm:
- Cấp phát compute/runtime.
- Khởi tạo container hoặc sandbox.
- Nạp code/package.
- JVM startup hoặc class loading.
- Dependency injection và configuration.
- Thiết lập kết nối cần thiết.
- Khởi tạo framework và JIT.

Cold start phụ thuộc runtime, package size, memory/CPU, network/VPC, provider và cấu hình. Java có thể cần thời gian startup/class loading; native image hoặc framework tối ưu startup có thể giảm nhưng có trade-off build, compatibility và debugging.

### 12.1. Cách giảm cold start

- Giữ artifact/package nhỏ, tránh dependency không dùng.
- Khởi tạo client một cách hợp lý và reuse trong execution environment.
- Tối ưu startup path, tránh gọi nhiều dependency trong static initializer.
- Chọn memory/CPU đủ cho startup nếu billing/runtime cho phép.
- Dùng provisioned concurrency/minimum instances khi latency yêu cầu và chi phí chấp nhận được.
- Xem xét runtime phù hợp, JVM tuning hoặc native compilation sau benchmark.
- Đặt function gần event source/data store để giảm network latency.

Không khởi tạo kết nối database hoặc thực hiện side effect nghiệp vụ trong static initializer. Execution environment có thể khởi tạo lại và function có thể bị invoke đồng thời ở nhiều instance.

### 12.2. Warm instance không phải bảo đảm

Một invocation trước đó có thể để lại environment ấm, nhưng platform có quyền scale down/recycle. Không dùng scheduled “ping” để giữ warm nếu provider policy hoặc chi phí không phù hợp. Nếu latency bắt buộc, dùng tính năng provisioned/minimum capacity có cam kết rõ.

## 13. Concurrency, scaling và backpressure

FaaS có thể tăng số execution environment nhanh khi event burst. Điều này thuận tiện nhưng có thể gây:
- Database connection storm.
- External API rate limit.
- Broker partition pressure.
- Cache stampede.
- Cost spike.
- Downstream overload.

Ví dụ 1.000 message được queue giải phóng cùng lúc, platform tạo hàng trăm function instance. Nếu mỗi instance mở 10 database connections, database có thể nhận hàng nghìn connection mới.

Cần:
- Reserved/account concurrency hoặc per-function concurrency limit.
- Queue-based buffering.
- Maximum batch size và controlled parallelism.
- Connection reuse và pool nhỏ theo execution environment.
- Database proxy/pooler phù hợp.
- Rate limit theo tenant và dependency.
- Backpressure ở consumer.
- Alarm về concurrent executions, throttles và downstream pool usage.

**Scale nhanh không đồng nghĩa dependency scale nhanh.** Đặt concurrency limit dựa trên capacity của downstream, không chỉ dựa trên số function có thể chạy.

### 13.1. Queue depth và oldest message age

Queue depth cho biết số message đang chờ; oldest message age cho biết thời gian message lâu nhất bị trì hoãn. Hai chỉ số cùng cần thiết. Một queue có 10.000 message nhưng consumer xử lý 20.000/s có thể phục hồi nhanh; một queue có 50 message nhưng mỗi message chờ 2 giờ có thể vi phạm SLA.

## 14. Serverless và database connections

Function scale-out tạo ra nhiều execution environment; nếu mỗi environment mở pool lớn, database dễ cạn connection. Một function được gọi 500 concurrency với pool tối đa 10 có thể tạo tiềm năng 5.000 connection.

Giải pháp:
- Giữ pool size nhỏ, phù hợp mỗi invocation/concurrency.
- Reuse client/connection trong environment khi runtime hỗ trợ.
- Dùng managed database proxy hoặc pooler tương thích.
- Giới hạn function concurrency.
- Dùng connection acquisition timeout.
- Tránh transaction dài.
- Cân nhắc database serverless/autoscaling nhưng vẫn kiểm tra max connections, warm-up và cost.
- Theo dõi connection count, wait time, DB CPU và transaction age.

Không giữ connection trong biến global với giả định environment tồn tại vô thời hạn. Khi connection stale, function cần reconnect an toàn. Không mở và đóng pool cho mọi invocation nếu chi phí handshake/latency quá lớn; chọn lifecycle phù hợp provider.

## 15. Serverless Java: runtime và framework

Java là lựa chọn tốt khi tổ chức đã có codebase JVM, thư viện và domain logic Java. Cần xem:
- JDK/runtime version mà provider hỗ trợ.
- Handler interface và event model.
- Package format (JAR, ZIP, container image).
- Startup/class loading.
- Reflection/dynamic proxy nếu dùng native image.
- Dependency injection framework.
- JDBC driver và connection pooling.
- Thread model và async API.
- Observability agent/instrumentation compatibility.

### 15.1. Handler Java minh họa

Ví dụ handler kiểu function:

~~~java
public class OrderNotificationHandler
        implements RequestHandler<OrderCreatedEvent, HandlerResult> {

    private final NotificationService notificationService =
        new NotificationService();

    @Override
    public HandlerResult handleRequest(
            OrderCreatedEvent event,
            Context context) {

        validate(event);

        notificationService.sendOrderConfirmation(event);

        return new HandlerResult(
            event.eventId(),
            "PROCESSED"
        );
    }

    private void validate(OrderCreatedEvent event) {
        if (event == null || event.eventId() == null) {
            throw new IllegalArgumentException("Invalid event");
        }
    }
}
~~~

Ví dụ minh họa theo một kiểu handler interface phổ biến, không phải code portable giữa mọi provider. Package/import, DTO serialization, dependency injection và result type phụ thuộc runtime adapter. Trong production, service không nên được tạo thủ công trong handler nếu cần test/DI phức tạp; có thể dùng constructor/factory phù hợp runtime, và notification cần idempotency.

### 15.2. Reuse dependency và lifecycle

Một số object có thể được tạo một lần mỗi execution environment:
- JSON mapper immutable.
- HTTP client.
- SDK client.
- Connection manager.
- Configuration đã validate.

Các object này phải thread-safe nếu environment xử lý concurrency trong cùng process. Không giữ request-specific mutable state ở field global. Nếu platform chỉ xử lý một invocation mỗi environment, vẫn không nên dựa vào điều đó như một bảo đảm lâu dài.

### 15.3. JVM startup và memory

Memory allocation cao hơn có thể cấp CPU nhiều hơn trên một số platform và giảm startup/duration; nhưng cũng tăng giá. Đo cold start, warm duration, memory max, GC, class loading và dependency initialization. Không tăng memory chỉ để giảm duration nếu workload bị network-bound.

## 16. Tích hợp serverless với Spring Boot

Spring Boot có thể chạy trong function runtime qua adapter hoặc đóng gói container, nhưng cần cân nhắc chi phí khởi tạo application context. Một ứng dụng Spring MVC lớn với nhiều bean, JPA, security và migration auto-run có thể có cold start đáng kể.

Cách tiếp cận:
- Tách module/domain logic khỏi web container khi có thể.
- Tạo handler mỏng gọi application service.
- Không chạy schema migration khi mỗi execution environment khởi động.
- Dùng configuration external và secret manager.
- Tối ưu bean initialization, tránh startup call không cần thiết.
- Kiểm tra compatibility của Spring Cloud Function hoặc adapter tương ứng với phiên bản Spring Boot.
- Benchmark package/JVM/native options trên runtime thật.

### 16.1. Ví dụ function bean khái niệm

~~~java
@Bean
Function<OrderCreatedEvent, NotificationResult> notifyOrder() {
    return event -> notificationService().send(event);
}
~~~

Đây là ví dụ khái niệm, thiếu định nghĩa bean và cách wiring đầy đủ. Cú pháp/function discovery phụ thuộc Spring Cloud Function và deployment adapter. Không thể suy ra chỉ thêm bean Function là artifact đã tương thích mọi FaaS provider.

### 16.2. Tránh biến function thành một monolith mới

Nếu một function handler chứa logic cho 20 event type và 15 dependency, nó trở thành điểm thay đổi chung, khó scale và khó triển khai độc lập. Có thể tách theo capability hoặc event family khi có ranh giới rõ, nhưng không cần một function cho từng method nhỏ. Catalog/ownership, permission và observability phải theo dõi được các handler.

## 17. Serverless và microservices: cách giao tiếp

Có ba cách tích hợp phổ biến:

**Synchronous HTTP:** API Gateway → function → service/database. Phù hợp thao tác ngắn cần response ngay. Cần timeout, authentication, rate limit và deadline.

**Asynchronous event/queue:** service publish event → bus/queue → function. Phù hợp công việc có thể xử lý sau, cần retry, DLQ, idempotency và quan sát lag.

**Workflow orchestration:** state machine điều phối nhiều bước, timeout, retry, branch, compensation và chờ callback. Phù hợp quy trình nhiều bước hơn một handler đơn lẻ.

Không gọi function qua HTTP chỉ vì dễ demo nếu message/event semantics tốt hơn. Cũng không biến mọi API thành event-driven khi client cần kết quả đồng bộ và nghiệp vụ cần validation ngay.

### 17.1. Contract giữa service và function

Cần xác định:
- Ai sở hữu event/API schema?
- Function có được quyền thực hiện side effect nào?
- Timeout và retry ở phía caller hay trigger platform?
- Ai xử lý duplicate và out-of-order?
- Có version compatibility?
- Ai chịu trách nhiệm DLQ?
- Làm sao trace từ request gốc tới function và consumer tiếp theo?
- Data classification và tenant scope đi qua đâu?

## 18. Workflow orchestration và saga

Một function đơn lẻ phù hợp một bước bounded. Một workflow phù hợp điều phối nhiều bước:

~~~mermaid
flowchart TD
    A[Order accepted] --> B[Reserve inventory]
    B --> C{Reserved?}
    C -- No --> F[Mark order rejected]
    C -- Yes --> D[Authorize payment]
    D --> E{Authorized?}
    E -- Yes --> G[Confirm order]
    E -- No --> H[Release inventory]
    H --> I[Mark payment failed]
    G --> J[Publish OrderConfirmed]
~~~

Sơ đồ minh họa một saga đơn giản. Workflow service có thể quản lý state và retry, nhưng mỗi bước vẫn cần idempotency, timeout và compensation. Compensation không phải rollback vật lý của mọi side effect; ví dụ refund payment là một giao dịch mới, có thể thất bại và cần reconciliation.

### 18.1. Chọn orchestration hay choreography

- **Orchestration:** một workflow/state machine điều phối thứ tự, timeout và nhánh. Dễ nhìn toàn bộ process nhưng có thêm orchestrator và state.
- **Choreography:** các service phản ứng với event của nhau. Giảm central coordinator nhưng flow phân tán, khó theo dõi và dễ có vòng phụ thuộc.

Có thể kết hợp: orchestration cho giao dịch dài/cốt lõi, event choreography cho notification và projection. Chọn theo độ phức tạp và yêu cầu audit.

## 19. Security và least privilege cho function

Mỗi function nên có workload identity riêng hoặc role giới hạn theo đúng trách nhiệm:
- Notification function chỉ đọc thông tin cần gửi và gọi provider tương ứng.
- Image function chỉ đọc object input trong vùng cho phép và ghi output prefix.
- Report function chỉ đọc dataset được cấp quyền và ghi file export có retention.
- Không dùng một admin role chung cho toàn bộ function.

Cần:
- IAM least privilege theo resource/action.
- Secret manager, rotation và access audit.
- TLS cho service-to-service.
- Network egress control khi phù hợp.
- Input validation và schema validation.
- Chống SSRF và redirect abuse.
- Không log secret, token, PII không cần thiết.
- Phân tách dev/test/prod identity.
- Bảo vệ event bus và function invocation permission.
- Kiểm tra dependency/package và supply chain.

### 19.1. Event source permission

Không chỉ bảo vệ endpoint HTTP. Một function trigger từ queue/topic cần policy xác định producer nào có thể publish và function nào được subscribe. Nếu một principal tùy ý có thể gửi event giả `PaymentAuthorized`, consumer có thể thực hiện side effect sai.

### 19.2. Tenant isolation

Với SaaS multi-tenant:
- Tenant ID phải đến từ identity/event producer đáng tin.
- Query luôn scope đúng tenant.
- Cache key và object path chứa scope thích hợp.
- Function role không có quyền rộng hơn yêu cầu.
- Logs/traces không làm lộ dữ liệu tenant.
- DLQ và replay tool có access control.
- Per-tenant concurrency/rate limit để chống noisy neighbor.

Không dựa vào một trường tenantId trong JSON mà không xác minh nguồn phát.

## 20. Network và private dependencies

Function có thể chạy trong network public hoặc private/VPC tùy provider. Khi cần truy cập database/private API:
- Thiết kế subnet/route/security group/network policy.
- Xác định NAT/egress và chi phí.
- Kiểm tra DNS và private endpoint.
- Quản lý IP exhaustion khi scale.
- Dùng connection proxy/pooler.
- Tránh function có quyền truy cập toàn bộ private network.
- Kiểm tra cold start và latency khi attach vào VPC/network interface theo nền tảng.

Đặt function trong private network không tự động bảo đảm an toàn. IAM, egress, secret và authorization ở tầng ứng dụng vẫn cần thiết.

## 21. Observability cho serverless

Mỗi invocation cần có:
- Function/service name và version.
- Invocation/request ID.
- Trigger/source.
- Correlation/trace ID.
- Duration, cold-start indicator nếu có.
- Outcome/error classification.
- Retry attempt và delivery count.
- Memory/CPU utilization nếu provider cung cấp.
- Tenant ID ở dạng được phép và có kiểm soát.
- Downstream dependency spans.

### 21.1. Metrics cốt lõi

| Metric | Câu hỏi |
| --- | --- |
| Invocation count | Workload đang chạy bao nhiêu lần? |
| Success/error/throttle count | Có lỗi hay bị giới hạn concurrency? |
| Duration p50/p95/p99 | Function mất bao lâu? |
| Cold start count/duration | Startup có ảnh hưởng latency? |
| Concurrent executions | Có vượt capacity dependency? |
| Queue depth/oldest age | Backlog có tăng? |
| Retry/DLQ count | Event nào không xử lý được? |
| Downstream latency | Chậm ở function hay dependency? |
| Memory utilization | Có gần memory limit/OOM? |
| Cost per invocation/business operation | Chi phí trên một đơn vị giá trị? |

Đừng gắn eventId, orderId hoặc userId vào metric labels nếu cardinality lớn. Dùng logs/traces với access control và sampling để điều tra từng invocation.

### 21.2. Trace propagation

Trace context cần được truyền qua:
- API Gateway → function.
- Producer service → event envelope.
- Event bus → consumer function.
- Function → downstream API.
- Workflow step → function kế tiếp.

Một event được replay có thể mang trace cũ; nên tạo span mới nhưng giữ correlation/causation ID để liên hệ với luồng gốc. Không coi message timestamp là thời gian xử lý.

### 21.3. Business metrics

Invocation success không đồng nghĩa nghiệp vụ thành công. Theo dõi:
- Tỷ lệ order confirmation.
- Tỷ lệ notification được gửi thành công.
- Tỷ lệ file xử lý đúng và sẵn sàng.
- Số operation ở trạng thái pending quá lâu.
- Thời gian từ event phát đến business outcome.
- Số giao dịch cần reconciliation.

## 22. Chi phí và cách tính TCO

Serverless billing thường có thành phần:
- Số invocation.
- Thời gian thực thi.
- Memory/CPU allocation.
- Provisioned/minimum concurrency.
- API Gateway requests.
- Event bus/queue operations.
- Logs/traces ingestion và retention.
- Network egress/NAT.
- Data store connections và I/O.
- Retry, failed invocation, DLQ/redrive.
- KMS/secret access và các dịch vụ phụ.

Ví dụ tính đơn giản:
- 2 triệu invocation/tháng.
- Mỗi invocation chạy 300 ms.
- Memory allocation 512 MB.
- Một phần request có cold start và retry.
- Ngoài compute còn queue, logs, gateway và database.

Không thể kết luận chi phí chỉ từ 2 triệu × 300 ms. Cần lấy bảng giá provider, region, free tier/discount, memory billing granularity, provisioned capacity và network charges hiện hành. Giá thay đổi theo nhà cung cấp và thời điểm; lập model bằng số liệu usage thật.

### 22.1. Chi phí ẩn

- Log debug quá nhiều làm tăng ingestion/storage.
- Retry làm invocation count tăng.
- Function concurrency cao làm database cần nâng cấp.
- NAT/egress và cross-region data transfer.
- Provisioned concurrency để giảm cold start.
- DLQ và replay sau sự cố.
- Engineering effort cho provider-specific adapter.
- Cost spike do event loop hoặc recursive trigger.

Nên có budget/alert theo function, service, environment và tenant tier. Nếu provider hỗ trợ cost allocation tags, dùng serviceId/team/environment và policy tagging chuẩn.

## 23. Vendor lock-in và portability

Serverless thường gắn với event model, IAM, workflow, database API và deployment packaging của provider. Portability có nhiều mức:
- **Code portability:** business logic Java/Python có thể tái sử dụng.
- **Runtime portability:** handler/runtime chạy được trên nhiều nền tảng.
- **Trigger portability:** event source, retry và acknowledgement semantics khác nhau.
- **Infrastructure portability:** IAM, networking, monitoring, workflow và data service có thể rất khác.
- **Operational portability:** runbook, cost model và failure behavior không giống nhau.

Có thể giảm coupling:
- Giữ domain logic độc lập với provider SDK khi hợp lý.
- Chuẩn hóa event envelope/schema.
- Dùng adapter cho cloud-specific trigger.
- Định nghĩa interface cho clock, identity, storage và messaging.
- Infrastructure as Code có module/contract rõ.
- Export dữ liệu và kế hoạch thoát provider.
- Không cố trừu tượng hóa mọi khác biệt đến mức mất khả năng dùng dịch vụ managed có giá trị.

Portability có chi phí. Nếu tổ chức chỉ vận hành một provider và không có yêu cầu chuyển, có thể chấp nhận tích hợp native sau khi đánh giá rủi ro và có data export/DR strategy.

## 24. Local development và testing

Function khó kiểm thử nếu logic bị gắn chặt với runtime event object. Nên tách:
- Domain/application logic.
- Event adapter.
- Provider trigger adapter.
- Persistence/messaging adapter.
- Configuration.
- Observability wrapper.

### 24.1. Các lớp test

1. **Unit test:** business logic, validation, idempotency decision.
2. **Handler test:** event mapping, status/ACK, error classification.
3. **Contract test:** event schema/API compatibility.
4. **Integration test:** database, queue, object storage hoặc emulator/container phù hợp.
5. **Platform integration test:** permission, trigger, timeout, retry, DLQ và network.
6. **Load test:** burst, concurrency, cold/warm duration, downstream capacity.
7. **Failure test:** duplicate event, poison message, dependency timeout, function timeout, partial batch.
8. **Security test:** forged event, cross-tenant access, SSRF, excessive IAM.

Local emulator không nhất thiết tái hiện đầy đủ retry, concurrency, IAM hoặc cold start của cloud thật. Cần có kiểm thử integration ở môi trường cloud được kiểm soát cho các behavior quan trọng.

### 24.2. Kiểm thử idempotency

Test cùng eventId gửi hai lần và đồng thời từ nhiều worker. Chỉ một business effect được ghi nhận. Test crash sau khi gọi provider nhưng trước khi lưu kết quả; xác minh reconciliation hoặc provider idempotency key giải quyết trạng thái không rõ.

### 24.3. Test timeout và cancellation

Mô phỏng dependency phản hồi chậm, body stream chậm, pool exhaustion và caller cancellation. Kiểm tra function dừng trong deadline, tài nguyên được giải phóng và event retry không tạo side effect trùng.

## 25. Deployment và versioning

Function deployment cần:
- Artifact bất biến (digest/version).
- Environment-specific configuration.
- IAM permissions theo version/alias nếu nền tảng hỗ trợ.
- Canary/traffic shifting.
- Rollback strategy.
- Event schema compatibility.
- Trigger mapping và permission.
- Concurrency/reserved capacity.
- Logs/metrics/alarms.
- IaC và audit.

### 25.1. Function version và alias

Một số provider cho phép publish immutable version rồi dùng alias/stage để chuyển traffic. Có thể triển khai:
1. Build và test version mới.
2. Publish artifact/version.
3. Cấu hình alias/canary.
4. Chuyển một phần traffic.
5. Theo dõi error/duration/cold start/business metrics.
6. Tăng traffic hoặc rollback alias.

Với event source mapping, cần kiểm tra cách platform phân phối event trong thời gian rollout; không giả định canary HTTP áp dụng y hệt queue consumer.

### 25.2. Schema và code rollout

Producer có thể phát event version mới trong khi function cũ vẫn xử lý. Nên:
- Deploy consumer tương thích trước.
- Thêm field theo hướng additive.
- Có default và validation phù hợp.
- Chuyển producer sau khi consumer sẵn sàng.
- Chỉ xóa field cũ sau khi hết consumer.
- Theo dõi unknown event type/version và DLQ.

## 26. Serverless failure modes và cách ứng phó

| Sự cố | Nguyên nhân thường gặp | Hành vi/ứng phó |
| --- | --- | --- |
| Cold start tăng | Scale-out, package lớn, VPC startup | Đo cold start, tối ưu startup, provisioned capacity nếu cần |
| Throttling | Vượt concurrency/account quota | Queue buffer, giới hạn producer, xin quota phù hợp |
| DB connection exhaustion | Mỗi environment mở pool quá lớn | Giảm pool, proxy, concurrency cap |
| Timeout | Dependency chậm hoặc workload quá lớn | Deadline, chia bước, async workflow |
| Retry storm | Nhiều layer retry cùng lúc | Retry budget, backoff, jitter, breaker |
| Duplicate side effect | At-least-once delivery | Durable idempotency và reconciliation |
| Poison message | Payload/schema hoặc code lỗi | DLQ/quarantine và redrive có kiểm soát |
| Event loop | Function kích hoạt chính nó hoặc vòng event | Filter, guard, idempotency, limit |
| Cost spike | Burst, retry, log volume | Budget/alert, quota, sampling |
| Secret unavailable | IAM/KMS/network lỗi | Runbook, fallback an toàn, kiểm tra permission |
| Provider outage | Region/service control plane lỗi | Multi-region/DR hoặc degraded mode |
| Data inconsistency | Out-of-order/partial side effect | Version, state machine, reconciliation |

### 26.1. Infinite event loop

Một function ghi object vào bucket mà chính bucket đó kích hoạt lại function có thể tạo vòng lặp vô hạn. Cần:
- Prefix input/output tách biệt.
- Event filter theo object type/path.
- Metadata marker và event version.
- Idempotency.
- Invocation/cost alarm.
- Guard chống recursive trigger.

### 26.2. Function timeout sau side effect

Nếu function charge payment thành công nhưng hết thời gian trước khi ghi trạng thái, event có thể retry và charge lần nữa. Cần idempotency provider, transaction state, operation ID và reconciliation. Không dựa vào function execution status để kết luận side effect.

## 27. Disaster recovery và availability cho serverless

Serverless giảm vận hành compute nhưng không tự cung cấp DR cho toàn bộ hệ thống. Cần khảo sát:
- Function source/artifact có thể deploy lại từ region khác?
- IaC và configuration có bản lưu ngoài vùng?
- Secret và encryption key có thể truy cập/khôi phục?
- Event bus/queue có replication hoặc replay?
- Database có backup/PITR và residency phù hợp?
- DLQ có nằm cùng failure domain?
- API gateway, custom domain, certificate, DNS có phương án?
- Provider quota ở region dự phòng đủ không?
- Dependencies ngoài cloud có hoạt động từ region mới?
- Function URL, event source mapping và IAM permission đã được tạo lại?

### 27.1. RTO/RPO cho event-driven processing

RTO có thể tính tới lúc function nhận và xử lý event thành công theo SLO nghiệp vụ, không chỉ tới lúc deployment status Active. RPO phải xét event đã publish/ack, queue retention, stream checkpoint và database commit.

Nếu event bus trong region bị mất, có thể mất message chưa được replicate. Nếu queue còn message nhưng consumer function chưa được deploy ở vùng dự phòng, hệ thống có thể giữ dữ liệu nhưng không xử lý kịp. Cần test toàn bộ luồng.

### 27.2. Multi-region và data consistency

Multi-region function dễ triển khai compute hơn một số stateful system, nhưng database, queue, object storage và external side effects vẫn là bài toán. Cần:
- Chọn authority cho write.
- Tránh hai region cùng xử lý một business event mà không dedup.
- Dùng idempotency key toàn cục phù hợp.
- Phân vùng tenant/data nếu cần.
- Kiểm tra replication lag và recovery point.
- Cấu hình routing và event source failover.
- Đảm bảo quota, secret, IAM và observability ở region dự phòng.

## 28. Quản trị vòng đời và ownership

Mỗi function vẫn là một thành phần có owner và trách nhiệm:
- Business capability và service/domain owner.
- Repository, artifact, deployment pipeline.
- Trigger/source và producer.
- Consumer/target và dependency.
- IAM role và secret references.
- Timeout, memory, concurrency.
- Dashboard, alert, runbook.
- Data classification, retention và region.
- Cost budget và quota.
- Lifecycle/deprecation.

Không để hàng trăm function vô chủ chỉ vì chúng được tạo nhanh. Catalog cần liên kết function với service sở hữu capability, team on-call và resource phụ thuộc. Function có thể là component riêng trong catalog hoặc workload thuộc một service, tùy mức độc lập triển khai/vận hành.

## 29. Ví dụ xuyên suốt: xử lý ảnh sản phẩm

Một hệ thống catalog chạy trên container nhận thông tin sản phẩm. Ảnh gốc được upload vào object storage. Sự kiện upload kích hoạt function Java:
1. Kiểm tra event source và object ownership.
2. Lấy object version và tenant scope.
3. Validate MIME/content và kích thước.
4. Đọc ảnh, tạo thumbnail và preview.
5. Ghi output vào prefix dẫn xuất.
6. Ghi metadata processing state.
7. Phát ImageProcessed event.
8. Catalog read model cập nhật URL thumbnail.

### 29.1. Thiết kế failure handling

- Event duplicate: unique processing key theo object version.
- File lỗi: ghi trạng thái REJECTED và chuyển thông tin an toàn tới DLQ/quarantine.
- Storage timeout: retry có backoff.
- Function gần timeout: không ghi output một phần như hoàn tất; output nên versioned/atomic theo khả năng storage.
- Catalog update lỗi: outbox/retry event để consumer xử lý lại.
- Object bị xóa trong lúc xử lý: xác minh version/ETag trước khi publish kết quả.
- Tenant vượt quota: throttle hoặc từ chối có mã lỗi và audit.

### 29.2. Khi nào cần container worker?

Nếu ảnh/video rất lớn, thời gian encode dài hoặc cần GPU/library native, function có thể vượt giới hạn runtime/memory. Khi đó dùng queue để giao việc tới container worker hoặc managed media processing. Function vẫn có thể xử lý validation/dispatch ngắn.

## 30. Ví dụ xuyên suốt: notification sau khi tạo đơn

Order-service commit order và outbox event OrderConfirmed. Relay publish event. Notification function:
- Kiểm tra schema và tenant.
- Tra cứu template/config hợp lệ.
- Kiểm tra notification idempotency.
- Gọi email provider với timeout và provider idempotency nếu hỗ trợ.
- Lưu delivery outcome.
- Retry transient error theo policy.
- Đưa permanent failure vào DLQ hoặc trạng thái cần xử lý.
- Expose business metric delivery success và age.

Không gửi email trước khi order đã đạt trạng thái nghiệp vụ cho phép. Nếu provider trả timeout, kết quả có thể chưa rõ; cần query provider hoặc retry với idempotency key để tránh gửi trùng.

## 31. Ví dụ serverless REST webhook

Webhook endpoint nhận thông báo từ payment provider:
1. API Gateway/HTTP adapter giới hạn request size và rate.
2. Xác minh signature/timestamp theo provider.
3. Kiểm tra replay protection và event ID.
4. Ghi event bền vào database/queue.
5. Trả 2xx sau khi durable acceptance thành công.
6. Worker/function xử lý nghiệp vụ bất đồng bộ.
7. Đối soát trạng thái payment nếu event đến trễ/sai thứ tự.

Không giữ HTTP webhook mở trong khi chạy toàn bộ order reconciliation nếu provider yêu cầu ACK nhanh. Nhưng không ACK trước khi event được lưu bền, nếu như vậy có thể mất thông báo khi function chết.

## 32. Checklist review trước production

### Kiến trúc và trigger
- [ ] Capability có ranh giới và owner rõ.
- [ ] Chọn trigger phù hợp HTTP, queue, object, schedule hay stream.
- [ ] Event/API schema và version compatibility.
- [ ] Xác định sync/async behavior.
- [ ] Xác định provider-specific dependency và lock-in.

### Runtime và giới hạn
- [ ] Runtime/version và package được hỗ trợ.
- [ ] Timeout/deadline và dependency timeouts.
- [ ] Memory/CPU và maximum execution duration.
- [ ] Concurrency/reserved capacity.
- [ ] Cold start đã benchmark theo latency requirement.
- [ ] DB connection/pool phù hợp scale-out.
- [ ] Long-running work đã chia bước/workflow phù hợp.

### Đúng đắn và độ bền
- [ ] Handler idempotent.
- [ ] Duplicate/out-of-order event được xử lý.
- [ ] Retry/backoff/jitter và retry budget.
- [ ] DLQ, alert và redrive runbook.
- [ ] External side effects có reconciliation.
- [ ] Durable state không phụ thuộc local memory/filesystem.
- [ ] Cancellation/timeout không làm sai trạng thái transaction.

### Security
- [ ] IAM least privilege.
- [ ] Event source permission được xác minh.
- [ ] Secrets nằm trong secret manager.
- [ ] Tenant scope và resource ownership được enforce.
- [ ] Input/SSRF/redirect được kiểm soát.
- [ ] Log/trace đã redaction.
- [ ] Network egress/private access phù hợp.

### Vận hành và chi phí
- [ ] Dashboard/metrics/traces/alerts.
- [ ] Cost budget và anomaly alert.
- [ ] Capacity downstream và concurrency cap.
- [ ] CI/CD, artifact digest và rollback.
- [ ] DR/backup/replay strategy.
- [ ] Runbook và owner/on-call.
- [ ] Load, failure và platform integration tests.

## 33. Bài tập thực hành

Một hệ thống thương mại điện tử đang chạy các microservices Java trên Kubernetes. Nhóm muốn chuyển ba năng lực sang serverless:
- Tạo thumbnail sau upload ảnh.
- Gửi email khi order được xác nhận.
- Tổng hợp báo cáo doanh thu mỗi đêm.

Hiện tại:
- Các worker chạy liên tục dù phần lớn thời gian idle.
- Một số event bị xử lý lặp.
- Database giới hạn connection.
- Email provider đôi khi timeout nhưng có thể đã gửi.
- Báo cáo có lúc chạy hơn 20 phút.
- Nhóm chưa có dashboard chi phí theo capability.

**Yêu cầu A — Chọn kiến trúc:** quyết định capability nào dùng FaaS, workflow, queue hoặc container worker. Giải thích dựa trên duration, burst, dependency và TCO.

**Yêu cầu B — Event contract:** thiết kế envelope cho ImageUploaded, OrderConfirmed và ReportRequested gồm eventId, schemaVersion, tenantId, aggregate/version và correlation.

**Yêu cầu C — Idempotency:** thiết kế durable deduplication cho từng event; xử lý email provider timeout sau side effect.

**Yêu cầu D — Timeout và concurrency:** đặt deadline từng function, giới hạn concurrency theo database và provider capacity, xử lý job báo cáo dài.

**Yêu cầu E — Failure handling:** phân loại transient/permanent/unknown, cấu hình retry, DLQ, redrive và reconciliation.

**Yêu cầu F — Security:** thiết kế IAM role, object path/tenant scope, event producer authorization và secret access.

**Yêu cầu G — Observability/cost:** chọn metric về duration, cold start, throttling, queue age, business success và cost per operation.

**Yêu cầu H — DR:** mô tả cách phục hồi function, queue, database, secret, API routing và event replay khi region mất.

Một lời giải tốt phải chứng minh serverless giảm gánh nặng vận hành hoặc chi phí cho từng capability, đồng thời không làm mất tính đúng đắn, khả năng quan sát và kiểm soát lỗi.

## 34. Câu hỏi tự kiểm tra

1. Serverless có nghĩa là không còn server không?
2. FaaS khác managed database hoặc event bus ở điểm nào?
3. Vì sao không nên chuyển mọi microservice sang function?
4. Những workload nào thường phù hợp FaaS?
5. Cold start gồm những bước nào và phụ thuộc yếu tố gì?
6. Vì sao warm execution environment không phải nơi lưu state bền?
7. At-least-once delivery có thể tạo side effect trùng ra sao?
8. Idempotency key cần lưu ở đâu và giữ bao lâu?
9. Retry và DLQ khác nhau như thế nào?
10. Tại sao function scale-out nhanh có thể làm database cạn connection?
11. Concurrency limit cần dựa trên capacity của thành phần nào?
12. Timeout function có chứng minh external provider chưa xử lý không?
13. Khi nào nên dùng workflow thay vì một function dài?
14. Serverless container có ưu/nhược gì so với FaaS?
15. Làm sao truyền trace context qua event bus?
16. Những metric nào phản ánh business outcome thay vì invocation success?
17. Chi phí serverless có những thành phần nào ngoài compute?
18. Vendor lock-in xuất hiện ở trigger, IAM, workflow và observability ra sao?
19. Tại sao function cần owner, runbook và lifecycle trong service catalog?
20. DR serverless phải khôi phục những thành phần nào ngoài function code?

## 35. Ghi nhớ

- **Serverless là mô hình vận hành compute và dịch vụ managed**, không phải hệ thống không có máy chủ.
- **FaaS phù hợp với các capability ngắn, event-driven hoặc bursty** khi runtime, concurrency và timeout đáp ứng được yêu cầu.
- Một hệ thống có thể kết hợp Kubernetes/container, managed data services, queue, workflow và function; lựa chọn theo từng capability.
- Function phải coi execution environment là tạm thời, không lưu state nghiệp vụ duy nhất trong memory hoặc filesystem.
- **At-least-once delivery đòi hỏi idempotency**; retry, duplicate và unknown side effect phải được xử lý rõ.
- Concurrency scale-out có thể gây quá tải database và provider; cần queue, rate limit, pool, backpressure và concurrency cap.
- Cold start, execution duration, memory, timeout và cost phải được benchmark trên runtime thực.
- Security dựa trên least privilege, xác minh event source, tenant scope, secret management và kiểm soát egress.
- Observability cần đo cả invocation và business outcome, queue age, retry, DLQ, cold start và cost.
- Serverless không tự giải quyết DR, data consistency hay vendor lock-in; những trách nhiệm này vẫn thuộc kiến trúc tổng thể và đội sở hữu capability.
