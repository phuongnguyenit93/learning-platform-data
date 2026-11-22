# Khoanh vùng vòng lặp trigger và chi phí tăng đột biến

Một hệ thống serverless có thể tăng số lần chạy function rất nhanh dù lưu lượng người dùng gần như không đổi. Một object được ghi vào storage kích hoạt function; function lại ghi object vào cùng vùng theo dõi và vô tình kích hoạt chính nó. Một consumer đọc message rồi phát lại message vào queue nguồn. Một rule trên event bus khớp cả event đầu vào lẫn event do chính handler tạo ra. Một lỗi tạm thời làm message retry liên tục, trong khi mỗi lần retry lại tạo thêm side effect. Những tình huống này có thể tạo thành vòng lặp trigger, khuếch đại invocation, làm queue backlog tăng và đẩy chi phí lên đột biến.

Mục tiêu của chẩn đoán là tìm được chuỗi nhân quả từ trigger đầu tiên đến các lần chạy lặp, xác định thành phần tạo ra sự khuếch đại, ngăn vòng lặp an toàn và khôi phục backlog mà không làm mất dữ liệu nghiệp vụ. Không nên chỉ nhìn tổng invocation hoặc tổng tiền. Cần nối được event, function, resource, retry, deployment và business operation bằng correlation ID, event ID, trace ID cùng các metric theo từng nguồn kích hoạt.

Trong module **CLOUD_SERVERLESS**, người học xây dựng và vận hành Java function được kích hoạt bởi HTTP, message hoặc event; xử lý trigger, trạng thái, retry, idempotency, mở rộng và chi phí để biết khi nào nên dùng FaaS. Bài này tập trung vào một sự cố vận hành thường gặp: khoanh vùng trigger loop và cost spike.

## 1. Nhận diện sự cố

Các dấu hiệu thường xuất hiện cùng nhau:

- Invocation count của một hoặc vài function tăng nhanh hơn request hoặc business event.
- Queue depth, age of oldest message hoặc số lần receive tăng liên tục.
- Một object, event type hoặc message ID xuất hiện lặp lại trong log.
- Function duration, concurrency, throttling hoặc downstream request tăng đột ngột.
- Storage PUT/GET, event bus ingestion, workflow transition hoặc log ingestion tăng bất thường.
- Chi phí tăng trong khi số đơn hàng, upload, người dùng hoạt động hoặc giao dịch thành công không tăng tương ứng.
- Một deployment, rule, bucket notification, event source mapping hoặc retry policy vừa thay đổi.
- Function liên tục timeout hoặc thất bại rồi được nền tảng gọi lại.

Một spike không tự động có nghĩa là trigger loop. Có thể là traffic hợp lệ, một đợt backfill, batch lớn, retry sau outage, scheduled job hoặc một client bị lỗi gửi request quá nhanh. Chẩn đoán phải phân biệt tải mới, retry và event do hệ thống tự tạo.

### Tín hiệu phân biệt ban đầu

| Dấu hiệu | Burst hợp lệ | Trigger loop | Retry amplification |
|---|---|---|---|
| Event ID | Chủ yếu event mới | Event mới do output tạo tiếp | Một số event lặp lại nhiều lần |
| Invocation / business operation | Tăng gần tương ứng | Tăng nhiều lần trên mỗi operation | Tăng theo attempt |
| Queue age | Có thể tăng rồi giảm | Có xu hướng tăng dai dẳng | Tăng nếu lỗi không được khắc phục |
| Event source | Nhiều producer hoặc client | Một chuỗi producer-consumer khép kín | Cùng nguồn và cùng message |
| Error rate | Có thể bình thường | Có thể bình thường hoặc tăng | Thường tăng |
| Resource write | Phù hợp nghiệp vụ | Output quay lại trigger nguồn | Có thể lặp side effect |
| Kết thúc khi traffic dừng | Thường giảm | Có thể tự tiếp tục | Tiếp tục đến khi retry hết hoặc bị chặn |

## 2. Trigger loop là gì?

Trigger loop xảy ra khi output của một handler trực tiếp hoặc gián tiếp tạo ra input mới khớp với trigger của chính handler đó hoặc một chuỗi handler quay lại điểm ban đầu.

~~~mermaid
flowchart TD
    A[Event source] --> B[Function A]
    B --> C[Write resource]
    C --> D[Resource notification]
    D --> E[Function A]
    E --> F[Write resource again]
    F --> D
~~~

Một vòng lặp có thể nằm trong một function hoặc trải qua nhiều dịch vụ. Ví dụ:

~~~mermaid
flowchart LR
    S[Object storage] --> A[Java intake function]
    A --> Q[Queue]
    Q --> B[Image worker]
    B --> S2[Write derivative object]
    S2 --> S
~~~

Nếu storage notification theo dõi cả prefix input và prefix derivative, việc worker ghi thumbnail sẽ kích hoạt intake function lần nữa. Nếu intake tiếp tục phát queue message và worker tiếp tục ghi output, hệ thống tạo vòng lặp.

Trigger loop khác với retry thông thường. Retry thường là cùng một delivery hoặc operation được thử lại do lỗi. Trigger loop tạo ra một event hoặc operation mới từ side effect của operation trước, dù operation trước có thể đã thành công.

## 3. Phân biệt loop, retry, fan-out và traffic burst

Bốn cơ chế này có thể tạo ra biểu đồ invocation giống nhau nhưng cách khắc phục khác nhau.

**Traffic burst:** nhiều request hoặc event mới đến trong thời gian ngắn. Event ID và business operation ID thường khác nhau. Nếu hệ thống xử lý đúng và backlog giảm sau burst, đây có thể là tải hợp lệ.

**Retry amplification:** cùng một message hoặc operation được xử lý nhiều lần do timeout, lỗi tạm thời, visibility timeout quá ngắn hoặc acknowledgement thất bại. Tìm receive count, attempt number, exception và message ID.

**Fan-out:** một event hợp lệ tạo nhiều task hoặc message cho nhiều consumer. Invocation tăng theo thiết kế. Kiểm tra số nhánh và số consumer dự kiến trên mỗi event.

**Trigger loop:** một side effect tạo event mới quay về trigger trước đó. Có thể không có exception; function chạy thành công nhưng liên tục tạo thêm công việc.

Một hệ thống có thể đồng thời có loop và retry. Khi đó mỗi vòng lặp lại bị retry nhiều lần, khiến mức khuếch đại lớn hơn nhiều.

## 4. Các dạng vòng lặp phổ biến

### Object storage tự kích hoạt

- Function được kích hoạt khi object được tạo trong bucket hoặc container.
- Function ghi thumbnail, metadata JSON hoặc bản chuyển đổi vào cùng bucket.
- Notification filter không giới hạn prefix/suffix.
- Output của function lại kích hoạt function ban đầu.

Cách phòng tránh: tách bucket input và output, hoặc giới hạn trigger vào prefix input cụ thể. Không chỉ dựa vào tên file; kiểm tra chính xác event type và đường dẫn object.

### Queue consumer gửi lại message vào queue nguồn

- Function nhận message từ queue.
- Khi xử lý xong, function publish message mới vào chính queue đó.
- Message mới lại gọi function và lặp vô hạn.

Đây có thể là lỗi route, nhầm queue URL/ARN, hoặc producer và consumer dùng chung queue vì cấu hình copy/paste. Tách command queue, retry queue và output queue.

### Event bus rule khớp event do chính consumer phát

- Rule match quá rộng, ví dụ chỉ lọc source chung hoặc không lọc detail-type.
- Handler nhận event và phát event mới có cùng source/detail.
- Rule tiếp tục kích hoạt handler.

Cần filter theo source, event type, detail fields và version. Event bus không tự hiểu quan hệ nhân quả giữa hai event.

### Database stream hoặc change feed tự quay lại

- Function được kích hoạt bởi row/item change.
- Function cập nhật lại cùng record hoặc ghi record khác trong cùng table.
- Change feed phát event mới và gọi function lần nữa.

Tách bảng/collection cho trạng thái xử lý, loại trừ field không cần theo dõi, hoặc dùng điều kiện update để không phát change event khi dữ liệu không đổi. Kiểm tra semantics filter của database stream.

### HTTP callback hoặc webhook gọi lại chính mình

- Function gọi URL của API Gateway.
- API route lại trỏ tới function đó hoặc một service gọi lại endpoint nguồn.
- Một request ban đầu tạo chuỗi request mới.

Kiểm tra URL, environment, DNS, route mapping, webhook destination và retry của bên gửi. Không dùng URL production trong integration test nếu test có thể tạo side effect thật.

### Workflow tự khởi chạy lại

- Workflow task phát event start execution cho chính workflow.
- Nhánh lỗi hoặc callback gọi API khởi tạo workflow mới.
- Một trạng thái chưa terminal bị hiểu là cần tạo execution mới.

Dùng execution ID, parent execution ID, operation ID và giới hạn số lần khởi chạy theo business operation.

### Scheduler hoặc poller không có checkpoint

- Scheduled function chạy mỗi phút.
- Function xử lý xong nhưng không cập nhật checkpoint.
- Lần chạy sau đọc lại toàn bộ dữ liệu và tạo cùng side effect.
- Một job tạo lịch mới mà không kiểm tra lịch hiện có.

Dùng checkpoint bền vững, idempotency key và lease cho job. Phân biệt lịch định kỳ dự kiến với việc một invocation tự lên lịch lại.

## 5. Retry có thể khuếch đại chi phí như thế nào?

Giả sử một event bị giao lại 5 lần và mỗi attempt lại tạo 2 event mới. Chỉ sau vài vòng, số invocation có thể tăng theo cấp số nhân. Đây là mô hình khuếch đại, không phải dự báo chính xác cho mọi queue hoặc event service.

Nếu mỗi invocation tạo ra trung bình \(b\) event mới quay lại trigger, sau \(n\) thế hệ số event được tạo xấp xỉ:

\[
N = 1 + b + b^2 + \dots + b^n
\]

Khi \(b = 2\), tổng số event sau 6 thế hệ là 127. Nếu retry làm mỗi thế hệ được xử lý nhiều lần, tổng invocation còn cao hơn.

Retry policy có thể làm tình hình nặng hơn khi:

- Timeout xảy ra sau khi side effect đã commit.
- Consumer không acknowledge message dù xử lý thành công.
- Visibility timeout ngắn hơn thời gian xử lý.
- Batch chứa một message lỗi làm cả batch bị retry.
- Retry không có exponential backoff và jitter.
- Không có max receive count hoặc DLQ.
- Client và server cùng retry một request.
- Outbox publisher publish thành công nhưng không lưu trạng thái sent.

Không tăng retry count chỉ để “đảm bảo không mất message”. Cần phân loại lỗi, đặt retry budget và đảm bảo operation idempotent.

## 6. Mô hình đồ thị trigger

Cách chẩn đoán hữu ích là biểu diễn hệ thống thành đồ thị có hướng:

- Node: function, queue, topic, bucket, table, workflow, API route, scheduler.
- Edge: trigger, publish, write, invoke, subscribe, callback hoặc schedule.
- Label: event type, prefix, filter, retry policy và environment.

Ví dụ:

~~~mermaid
flowchart TD
    A[API: create upload] --> B[Upload function]
    B --> C[Input bucket]
    C --> D[Object-created event]
    D --> E[Intake function]
    E --> F[Processing queue]
    F --> G[Image worker]
    G --> H[Output bucket]
    H --> I[Object-created event]
    I --> E
    G --> J[Processed event]
~~~

Trong ví dụ, cạnh H đến I đến E tạo chu trình. Nếu output bucket được tách khỏi input bucket hoặc trigger filter chỉ nhận prefix incoming/, chu trình bị phá vỡ.

Khi vẽ đồ thị, ghi cả cạnh gián tiếp. Function có thể không gọi chính nó, nhưng nó ghi database; database stream kích hoạt function B; function B publish event kích hoạt function A. Chu trình có thể đi qua nhiều account, project hoặc region.

## 7. Xác định điểm bắt đầu và phạm vi ảnh hưởng

Bắt đầu từ thời điểm metric bất thường xuất hiện và xác định:

1. Function nào có invocation tăng mạnh nhất?
2. Trigger source nào đang gọi function đó?
3. Event type hoặc route nào chiếm phần lớn?
4. Queue/topic/bucket/table nào có ingress tăng?
5. Function có deployment/configuration change gần thời điểm đó không?
6. Invocation tăng theo event mới hay attempt của event cũ?
7. Side effect nào do function tạo ra?
8. Side effect có thể quay lại trigger nguồn không?

Phạm vi ảnh hưởng gồm compute, queue, storage, database, event bus, workflow, network egress, log/trace và dependency ngoài. Một function nhỏ có thể gây chi phí lớn ở dịch vụ downstream nếu nó tạo nhiều request hoặc log.

Không dừng lại khi đã tìm thấy function có invocation cao nhất. Đó có thể chỉ là consumer cuối của một loop bắt đầu từ storage hoặc event rule khác.

## 8. Metric cần kiểm tra

| Lớp | Metric | Dấu hiệu đáng chú ý |
|---|---|---|
| Function | Invocations | Tăng nhanh hơn business operations |
| Function | Errors / Throttles | Retry hoặc capacity pressure |
| Function | Duration p50/p95/p99 | Dependency chậm hoặc payload tăng |
| Function | Concurrent executions | Tăng kéo dài hoặc chạm giới hạn |
| Queue | Messages received/deleted | Receive cao nhưng delete thấp |
| Queue | Approximate age of oldest message | Backlog tích tụ |
| Queue | DLQ messages | Poison event hoặc lỗi không hồi phục |
| Event bus | Ingress/matched/failed invocations | Rule quá rộng hoặc consumer lỗi |
| Storage | PUT/GET/HEAD requests | Function ghi lại object liên tục |
| Database | Reads/writes/stream records | Update loop hoặc query amplification |
| Workflow | Executions/transitions | Execution mới được tạo lặp |
| API | Request count/4xx/5xx/latency | Callback hoặc client retry |
| Observability | Log bytes/trace spans | Telemetry bị khuếch đại |
| Billing | Usage theo service/region | Xác định nơi phát sinh tiền |

So sánh các metric trong cùng khoảng thời gian và cùng timezone. Một biểu đồ tổng hợp theo ngày có thể che mất loop chỉ kéo dài 5 phút.

### Invocation amplification ratio

Một chỉ số hữu ích là số invocation trên mỗi business operation thành công:

\[
AmplificationRatio =
\frac{FunctionInvocations}{SuccessfulBusinessOperations}
\]

Không có ngưỡng chung cho mọi hệ thống. Một workflow có 8 bước có thể hợp lệ với ratio 8; một HTTP API một bước có ratio 20 cần được điều tra. Thiết lập baseline theo từng loại operation.

### Retry ratio

\[
RetryRatio =
\frac{TotalDeliveryAttempts - UniqueMessages}{UniqueMessages}
\]

Cần xác định UniqueMessages theo event ID/message ID ổn định và tính theo cùng cửa sổ thời gian. Với queue không cung cấp định danh ổn định giữa các bản sao, dùng business operation ID hoặc dedupe key.

## 9. Log và trace phải mang thông tin nhân quả

Mỗi log của function nên có một nhóm field thống nhất:

- timestamp UTC.
- service/function name và version.
- trigger type và source resource.
- eventId hoặc messageId.
- operationId và correlationId.
- traceId/spanId.
- parentEventId hoặc causationId.
- tenant-safe identifier.
- attempt/receive count nếu có.
- object key/version hoặc resource reference đã được redacted.
- outcome, error class và duration.

Ví dụ structured log:

~~~json
{
  "timestamp": "2026-11-17T15:42:10.250Z",
  "level": "INFO",
  "service": "image-worker",
  "functionVersion": "42",
  "triggerType": "queue",
  "triggerResource": "image-jobs",
  "eventId": "evt-9002",
  "operationId": "upload-781",
  "correlationId": "corr-81",
  "causationId": "evt-9001",
  "attempt": 2,
  "objectKey": "incoming/tenant-4/file-18",
  "outcome": "RETRYABLE_FAILURE",
  "errorClass": "StorageTimeout",
  "durationMs": 840
}
~~~

Không log signed URL, access token, file bytes hoặc thông tin cá nhân không cần thiết. Với object key có dữ liệu nhạy cảm, dùng resource ID hoặc hash ổn định thay vì log nguyên key.

### Correlation ID, event ID và causation ID

- correlationId liên kết toàn bộ user journey hoặc business operation.
- eventId định danh một event cụ thể và ổn định qua retry publish.
- causationId chỉ ra event/command nào đã tạo ra event hiện tại.
- operationId định danh nghiệp vụ như upload, order hoặc report.
- traceId nối các span trong distributed trace.

Một correlation ID đơn lẻ không đủ phát hiện loop nếu một operation hợp lệ có nhiều nhánh. Kết hợp eventId, causationId, parent chain và trigger source.

## 10. Truy vết một chuỗi lặp

Khi phát hiện event lặp, lấy một sample và dựng timeline:

| Thời điểm | Thành phần | Event/operation | Hành động |
|---|---|---|---|
| 15:42:00 | Storage | evt-100 | Object incoming được tạo |
| 15:42:01 | Intake function | evt-100 | Phát evt-101 |
| 15:42:02 | Worker | evt-101 | Ghi thumbnail |
| 15:42:02 | Storage | evt-102 | Thumbnail tạo ObjectCreated |
| 15:42:03 | Intake function | evt-102 | Phát evt-103 |
| 15:42:04 | Worker | evt-103 | Ghi thumbnail của thumbnail |

Chuỗi cho thấy worker output quay lại intake. Nếu không có causationId, dùng correlationId, object key, timestamps, event payload và storage request ID để suy ra chuỗi. Sau sự cố, bổ sung field còn thiếu vào telemetry.

## 11. Phân tích cost spike

Tổng chi phí không chỉ là function invocation:

\[
TotalCost =
Compute + API + Queue + Events + Storage + Database
+ Network + Workflow + Observability
\]

Compute thường phụ thuộc số invocation, memory/CPU allocation, duration và concurrency model. Ngoài ra còn có:

- API Gateway request và data transfer.
- Event bus ingestion, archive/replay và rule invocation.
- Queue request, message retention và DLQ.
- Object storage request, storage GB-month, replication và retrieval.
- Database read/write, stream và provisioned capacity.
- Workflow execution và state transition.
- NAT, inter-zone/inter-region egress và private endpoint.
- Log ingestion, retention, query và trace spans.
- Secret/KMS operations.
- Downstream SaaS/API theo request.

Một loop có thể tạo ít function time nhưng nhiều log bytes hoặc object writes. Vì vậy hãy xem cost theo service, operation, region và resource tag, không chỉ compute.

### Cost per successful operation

\[
CostPerSuccess =
\frac{TotalCostInWindow}{SuccessfulBusinessOperationsInWindow}
\]

Nếu tổng chi phí tăng 5 lần nhưng số operation thành công không đổi, cost per success cũng tăng khoảng 5 lần. Chỉ số này giúp phân biệt tăng trưởng thật với lãng phí do retry/loop.

### Tìm service chịu chi phí

1. So sánh cost theo service với baseline ngày/tuần tương đương.
2. Chuyển sang usage quantity nếu billing dashboard cung cấp.
3. Nhóm theo region, account/project, function và resource tag.
4. Đối chiếu usage timestamp với metrics và deployment timeline.
5. Xác định đơn giá/usage unit của từng thành phần.
6. Kiểm tra data transfer và log ingestion vì chúng có thể bị bỏ qua trong dự báo compute.

Billing data thường có độ trễ. Trong incident đang diễn ra, dùng runtime metrics để containment trước; billing report dùng để xác nhận chi phí sau đó.

## 12. Ví dụ: object storage trigger tự kích hoạt

Giả sử function được cấu hình cho mọi object trong bucket. Khi user upload file vào incoming/, function xử lý rồi ghi kết quả vào processed/. Vì trigger không có prefix filter, processed object lại kích hoạt function.

Một cấu hình khái niệm:

~~~text
Bucket: media
Notification: ObjectCreated/*
Function: media-handler
Input: incoming/*
Output: processed/*
~~~

Cấu hình này an toàn hơn khi notification chỉ nhận incoming/ và function ghi output vào processed/. Nếu cần nhiều loại input, dùng prefix riêng cho từng loại hoặc bucket riêng.

Kiểm tra thêm:

- Function có ghi manifest, log artifact hoặc thumbnail vào prefix được trigger không?
- Có event cho multipart completion lẫn từng part không?
- Output copy có tạo ObjectCreated event mới không?
- Notification có được cấu hình ở cả bucket và prefix khác nhau dẫn đến hai delivery không?
- Một object được ghi bởi replication có phát event ở destination không?

Không giả định tên folder processed/ tự động bị loại khỏi trigger. Phải có filter thực sự ở cấu hình notification và test trên environment.

## 13. Ví dụ: event bus rule quá rộng

Giả sử một rule chỉ match source là com.example.media. Function nhận event media.uploaded rồi phát media.processed với cùng source. Rule lại match media.processed, khiến function chạy tiếp.

Rule nên lọc cả source và detail-type hoặc eventType:

~~~json
{
  "source": ["com.example.media"],
  "detail-type": ["media.uploaded"],
  "detail": {
    "schemaVersion": [1],
    "state": ["ACCEPTED"]
  }
}
~~~

Consumer phát event output với detail-type media.processed. Rule không khớp event đó. Trong hệ thống nhiều rule, kiểm tra cả rule khác có cùng target hoặc pattern overlap.

Không đặt một rule bắt mọi event rồi dựa vào code để bỏ qua hầu hết event. Filter sớm giúp giảm invocation và chi phí.

## 14. Ví dụ: queue consumer tạo vòng lặp

Một consumer nhận message từ image-jobs. Khi xử lý lỗi, nó publish lại message vào image-jobs nhưng queue trigger cũng tự retry message gốc. Mỗi lỗi tạo thêm bản sao.

Cần xác định ai sở hữu retry:

- Queue redelivery xử lý retry của delivery.
- Retry queue hoặc delayed message xử lý retry có chủ đích.
- DLQ giữ message sau số lần nhận tối đa.
- Application retry chỉ dùng khi có lý do cụ thể và có idempotency.

Không kết hợp nhiều cơ chế retry mà không tính tổng attempt. Nếu queue đã retry 5 lần và application tự retry 4 lần mỗi attempt, một message có thể tạo 20 lần gọi dependency.

## 15. Kiểm tra cấu hình trigger và thay đổi gần đây

Tập trung vào những cấu hình có thể tạo chu trình:

- Bucket notification event type, prefix và suffix.
- Event bus rule pattern, target và retry policy.
- Queue event source mapping, batch size, max concurrency và partial failure.
- Database stream filter và table được ghi bởi consumer.
- API Gateway route, custom domain, stage variable và destination URL.
- Webhook callback URL và retry schedule.
- Scheduler expression, target và retry.
- Workflow startExecution, callback và redrive.
- IAM permission cho phép function invoke function hoặc publish lại vào nguồn.
- Environment variable có chứa queue/bucket/topic URL.
- IaC diff và deployment version.

So sánh cấu hình hiện tại với phiên bản tốt gần nhất. Nếu sự cố bắt đầu ngay sau deploy, kiểm tra resource replacement, rule filter bị bỏ, prefix đổi hoặc environment variable trỏ nhầm môi trường.

Không chỉ xem source code. Trigger loop thường xuất phát từ cấu hình infrastructure hoặc một route được thay đổi bên ngoài repository.

## 16. Quy trình chẩn đoán có thứ tự

Dùng trình tự sau để giảm thời gian tìm nguyên nhân:

1. **Xác nhận anomaly:** invocation, queue ingress, storage request hoặc cost tăng so với baseline nào?
2. **Chọn top contributor:** function, queue, rule, bucket hoặc route chiếm phần lớn.
3. **Xác định trigger:** function được gọi bởi HTTP, queue, storage, stream, scheduler hay workflow?
4. **Lấy sample:** chọn event/message và tìm event ID, operation ID, correlation ID.
5. **Dựng lineage:** tìm side effect do invocation tạo ra và event tiếp theo.
6. **Kiểm tra retry:** receive count, attempt, timeout, acknowledgement và DLQ.
7. **Kiểm tra config/deploy:** diff rule, filter, mapping, IAM và environment.
8. **Xác nhận chu trình:** chứng minh output quay lại một trigger đã có trong lineage.
9. **Contain:** chặn cạnh tạo vòng lặp hoặc giảm concurrency có kiểm soát.
10. **Verify:** invocation/ingress giảm, backlog ngừng tăng, business flow quan trọng vẫn chạy.
11. **Recover:** xử lý backlog theo batch nhỏ và idempotent.
12. **Prevent:** thêm filter, guard, test, dashboard và runbook.

Không thay đổi nhiều cấu hình cùng lúc nếu chưa biết nguyên nhân; điều đó làm mất bằng chứng và khó xác định biện pháp nào có tác dụng.

## 17. Dùng log query để tìm event lặp

Tên field và cú pháp query khác nhau giữa CloudWatch Logs Insights, Azure Log Analytics, Google Cloud Logging và hệ thống log nội bộ. Ví dụ SQL-like dưới đây mô tả logic truy vấn:

~~~sql
SELECT
    function_name,
    event_id,
    operation_id,
    trigger_resource,
    COUNT(*) AS attempts,
    MIN(timestamp) AS first_seen,
    MAX(timestamp) AS last_seen
FROM function_invocations
WHERE timestamp >= :incident_start
GROUP BY
    function_name,
    event_id,
    operation_id,
    trigger_resource
HAVING COUNT(*) > 1
ORDER BY attempts DESC;
~~~

Tìm các event có attempt cao, sau đó nhóm theo object key/version hoặc causationId. Nếu eventId khác nhau nhưng operationId giống nhau, có thể producer tạo event mới cho cùng business operation. Nếu eventId giống nhau và attempt tăng, nghiêng về retry/redelivery.

Query thứ hai có thể tìm chuỗi parent-child:

~~~sql
SELECT
    parent_event_id,
    event_id,
    source_function,
    output_resource,
    event_type,
    timestamp
FROM event_lineage
WHERE correlation_id = :correlation_id
ORDER BY timestamp;
~~~

Giữ query trong phạm vi incident window và giới hạn field cần thiết. Tránh query toàn bộ log retention trong lúc hệ thống đang quá tải.

## 18. Quan sát theo từng cloud provider

Tên metric và dịch vụ khác nhau, nhưng phương pháp chung vẫn là nối trigger, invocation, dependency và billing.

| Nền tảng | Nguồn quan sát | Cần kiểm tra |
|---|---|---|
| AWS | CloudWatch metrics/logs, X-Ray, CloudTrail, Cost Explorer | Lambda Invocations/Errors/Throttles/ConcurrentExecutions, SQS ApproximateAgeOfOldestMessage, event rule invocations, S3 request metrics |
| Azure | Azure Monitor, Application Insights, Activity Log, Cost Management | Function execution count/duration, queue length, dependency calls, trigger configuration changes |
| Google Cloud | Cloud Monitoring, Cloud Logging, Cloud Trace, Audit Logs, Billing reports | Function execution count/duration, Pub/Sub backlog/delivery attempts, Eventarc delivery, Storage request usage |
| Multi-cloud | OpenTelemetry, centralized logs/metrics, cost allocation | trace context, service/resource identity, region, environment và tenant |

Không giả định tên metric hoàn toàn giống nhau giữa runtime generations hoặc hosting plans. Dùng metric tương ứng do provider cung cấp và kiểm tra dimension có sẵn.

## 19. Containment trong incident

Khi đã có bằng chứng về loop, ưu tiên ngăn tạo thêm công việc. Chọn biện pháp ít ảnh hưởng nhất tới business flow.

Có thể cân nhắc:

- Thu hẹp event rule/filter để loại output event khỏi trigger.
- Tạm dừng event source mapping hoặc subscription cụ thể.
- Giảm maximum concurrency của consumer gây tải.
- Chuyển event đáng ngờ sang quarantine queue.
- Tạm dừng publisher hoặc scheduler đang tạo vòng lặp.
- Tách output prefix/bucket sau khi kiểm tra tác động.
- Throttle route hoặc tenant gây abuse.
- Tạm disable một trigger có phạm vi rõ ràng trong thời gian điều tra.

Không xóa queue, bucket, event hoặc workflow execution chỉ để làm biểu đồ giảm. Các hành động đó có thể làm mất dữ liệu và bằng chứng. Giữ lại event mẫu, config snapshot, deployment ID và timeline trước khi dọn dẹp.

Nếu chưa rõ cạnh nào tạo loop, giảm concurrency có thể mua thời gian nhưng không sửa nguyên nhân. Theo dõi queue age và downstream pressure để tránh tạo backlog lớn hơn.

## 20. Chọn containment theo loại trigger

| Nguồn loop | Biện pháp ưu tiên | Rủi ro cần xem |
|---|---|---|
| Object storage | Filter prefix/event type hoặc pause notification cụ thể | Upload hợp lệ có thể bị chậm |
| Event bus | Thu hẹp rule pattern hoặc disable target tạm thời | Event khác có thể dùng chung rule |
| Queue | Giảm consumer concurrency, isolate message hoặc pause mapping | Backlog và visibility timeout |
| Database stream | Filter record/attribute hoặc pause consumer | Change feed có retention giới hạn |
| HTTP callback | Disable callback route/destination hoặc rate limit | Partner/client có thể retry |
| Scheduler | Pause schedule cụ thể | Job định kỳ bị bỏ lỡ |
| Workflow | Stop khởi tạo execution mới, giới hạn concurrency | Execution đang chạy có thể cần hoàn tất |
| Retry storm | Sửa timeout/ack và giới hạn retry | Không làm mất message chưa xử lý |

Trước khi disable trigger, xác định resource nào khác đang phụ thuộc vào nó. Ghi thời điểm disable, người thực hiện và cách bật lại.

## 21. Idempotency để giới hạn side effect

Idempotency không tự phá trigger loop, nhưng giảm thiệt hại khi cùng event hoặc operation được giao lại.

Một consumer nên lưu deduplication key bền vững, ví dụ:

- eventId.
- messageId nếu ổn định trong retry.
- operationId + step name.
- bucket + key + versionId + event type.
- business key có unique constraint.

Đặt side effect và inbox record trong cùng transaction khi chúng cùng database. Với external API, truyền idempotency key nếu provider hỗ trợ và lưu external operation reference.

Không dùng timestamp hiện tại hoặc random UUID mới cho mỗi retry làm idempotency key; mỗi attempt sẽ bị coi là operation mới.

## 22. Java: log lineage và attempt

Java function nên nhận metadata trigger từ adapter rồi truyền context vào application service. Pseudocode:

~~~java
public record InvocationContext(
        String functionName,
        String functionVersion,
        String triggerType,
        String triggerResource,
        String eventId,
        String operationId,
        String correlationId,
        String causationId,
        int attempt) {
}

public void handle(StorageEvent event, InvocationContext context) {
    logger.info("serverless_invocation",
            kv("function", context.functionName()),
            kv("version", context.functionVersion()),
            kv("triggerType", context.triggerType()),
            kv("triggerResource", context.triggerResource()),
            kv("eventId", context.eventId()),
            kv("operationId", context.operationId()),
            kv("correlationId", context.correlationId()),
            kv("causationId", context.causationId()),
            kv("attempt", context.attempt()));

    processor.process(event, context);
}
~~~

Đây là pseudocode; adapter cần map các header, message attributes hoặc runtime context tương ứng. Không phải mọi nền tảng đều cung cấp attempt count hoặc event ID theo cùng cách. Nếu không có, producer cần đưa metadata ổn định vào event envelope.

Log một dòng khi bắt đầu và một dòng kết thúc với outcome/duration. Không log toàn bộ payload vì payload lớn làm tăng chi phí và có thể chứa dữ liệu nhạy cảm.

## 23. Java: defense-in-depth chống xử lý event do chính service tạo

Filter ở infrastructure là lớp bảo vệ chính. Code guard là lớp bổ sung để phát hiện event sai tuyến hoặc event nội bộ quay lại consumer.

~~~java
public ProcessingResult process(
        DomainEvent event,
        InvocationContext context) {

    if (event.source().equals("image-worker")
            && event.type().equals("image.derivative.created")) {
        metrics.increment("trigger_loop_guard_rejected");
        logger.warn("unexpected_self_generated_event",
                kv("eventId", event.id()),
                kv("correlationId", context.correlationId()));
        return ProcessingResult.ignored("self-generated event");
    }

    if (event.hopCount() > 5) {
        metrics.increment("event_hop_limit_exceeded");
        quarantine.store(event, "hop-limit-exceeded");
        return ProcessingResult.quarantined();
    }

    return applicationService.execute(event);
}
~~~

Hop count chỉ hữu ích khi producer đáng tin cậy và mọi bước đều duy trì field này. Không dùng nó thay cho event filter hoặc authorization. Một event hợp lệ có thể đi qua nhiều service; đặt ngưỡng dựa trên workflow thực tế và có đường điều tra khi vượt ngưỡng.

Nếu bỏ qua event, phải có metric/log rõ ràng để không biến lỗi routing thành silent data loss. Event bị quarantine cần giữ reference, reason và cách redrive.

## 24. Event filter ở hạ tầng

Một filter tốt mô tả chính xác event nào được phép gọi function. Ví dụ khái niệm:

~~~json
{
  "source": ["com.example.storage"],
  "detail-type": ["ObjectCreated"],
  "detail": {
    "bucket": ["incoming-media"],
    "object": {
      "key": [{
        "prefix": "incoming/"
      }]
    }
  }
}
~~~

Cấu hình thực tế phụ thuộc event service. Có provider dùng prefix/suffix filter trực tiếp ở bucket notification; provider khác dùng event pattern trên bus hoặc filter criteria ở event source mapping.

Nguyên tắc:

- Match source cụ thể.
- Match event type cụ thể.
- Match resource cụ thể.
- Match prefix/suffix hoặc attribute cần thiết.
- Loại trừ output path.
- Tránh wildcard rộng nếu không có lý do.
- Version filter cùng code và test.

Code guard không thay thế filter vì invocation đã phát sinh chi phí trước khi function có thể bỏ qua event.

## 25. Backpressure và giới hạn concurrency

Khi loop hoặc retry làm ingress tăng, function có thể scale nhanh hơn database hoặc downstream. Cần bảo vệ dependency:

- Reserved/max concurrency cho function.
- Maximum concurrency cho event source mapping nếu có.
- Queue buffer và batch size phù hợp.
- Rate limit theo tenant hoặc operation.
- Database connection pool/proxy.
- Circuit breaker cho external API.
- Admission control khi backlog vượt ngưỡng.
- Retry budget và jitter.

Concurrency thấp hơn có thể giảm áp lực nhưng làm queue age tăng. Theo dõi cả queue depth, oldest age, success throughput và downstream saturation. Đừng chỉ nhìn số invocation giảm rồi kết luận incident đã hết.

Với Java, tái sử dụng SDK client an toàn giữa invocation, đặt connection timeout/read timeout, giới hạn connection pool và đóng tài nguyên theo lifecycle runtime. Không tạo thread pool không giới hạn trong function.

## 26. Tối ưu retry policy

Retry cần có:

- Phân loại transient và permanent error.
- Exponential backoff.
- Jitter để tránh nhiều consumer retry cùng lúc.
- Maximum attempts hoặc maximum event age.
- DLQ/quarantine cho poison message.
- Visibility timeout phù hợp.
- Partial batch response nếu runtime hỗ trợ.
- Idempotency cho side effect.
- Runbook redrive có kiểm soát.

Không retry lỗi schema invalid, authorization denied hoặc resource mismatch vô hạn. Các lỗi đó cần reject/quarantine và alert.

Timeout phải được thiết kế từ ngoài vào trong: client timeout lớn hơn hoặc tương thích gateway timeout; gateway timeout lớn hơn function budget nếu synchronous; dependency timeout nhỏ hơn function remaining time để function còn đủ thời gian ghi kết quả và trả response. Với tác vụ dài, dùng async workflow.

## 27. Kiểm tra deployment và configuration drift

Trigger loop có thể xuất hiện sau khi một thay đổi tưởng như vô hại được triển khai:

- Một prefix filter bị xóa khi refactor IaC.
- Một rule được đổi từ eventType cụ thể sang wildcard.
- Output bucket được hợp nhất với input bucket.
- Environment variable trỏ sang queue của production.
- Một function mới được thêm làm target thứ hai.
- Retry count tăng nhưng không có DLQ.
- Event source mapping được tạo trùng.
- Scheduler cũ không được disable sau migration.

Trong incident, lưu IaC plan/deployment diff và so sánh với cấu hình đang chạy. Kiểm tra cả thay đổi ngoài pipeline qua audit log của cloud provider. Đưa trigger rules, queue mapping và resource names vào code review.

## 28. Phân tích cost theo từng lần xử lý

Ước tính chi phí cho một business operation bằng cách đếm số lần gọi và tài nguyên phát sinh:

| Thành phần | Cách đo |
|---|---|
| API/function | Invocation, duration, memory/CPU và request |
| Queue | Send, receive, delete, retry, retention |
| Event bus | Ingress, matched rule, target invocation, archive/replay |
| Storage | PUT, GET, HEAD, copy, GB-month và egress |
| Database | Read/write, stream, connection và capacity |
| Workflow | Execution và state transition |
| Observability | Log bytes, metric cardinality, trace spans |
| Network | NAT, cross-zone, cross-region và public egress |

Tính cost per operation theo baseline. Nếu một file bình thường cần 1 intake + 1 worker + 1 notification, nhưng sau deploy cần 40 intake + 40 worker, chi phí tăng theo amplification ngay cả khi compute duration không đổi.

Dùng cost allocation tags/labels nhất quán: environment, service, owner, function, product hoặc tenant tier. Không gắn user ID làm billing dimension có cardinality quá cao.

## 29. Giới hạn chi phí trong lúc điều tra

Một số biện pháp có thể giảm tốc độ phát sinh chi phí:

- Tạm pause rule/trigger đã xác định gây loop.
- Hạn chế maximum concurrency của consumer.
- Tạm dừng scheduled job hoặc publisher cụ thể.
- Giảm log verbosity cho log debug không cần thiết, vẫn giữ security/audit logs.
- Giới hạn retry và chuyển poison event sang DLQ.
- Chặn tenant/API key có hành vi bất thường theo abuse policy.
- Dừng replay hoặc backfill không liên quan.
- Đặt quota tạm thời cho upload/job creation.

Không tắt toàn bộ observability hoặc audit để giảm bill. Khi giảm log, giữ invocation/error/trigger metadata cần cho incident. Ghi lại thay đổi containment để có thể revert.

## 30. Khôi phục sau khi phá vòng lặp

Sau khi sửa filter hoặc route:

1. Xác nhận ingress mới đã trở về mức dự kiến.
2. Kiểm tra queue backlog và oldest message age.
3. Phân loại message trong queue/DLQ: hợp lệ, duplicate, poison hoặc stale.
4. Đảm bảo consumer idempotent trước khi redrive.
5. Chạy thử một lượng nhỏ event đại diện.
6. Theo dõi event lineage và side effect output.
7. Tăng batch/concurrency dần theo capacity.
8. Xác minh số business operation thành công.
9. Kiểm tra cost per success và log volume.
10. Ghi nhận message bị bỏ hoặc phải replay để reconciliation.

Không xóa DLQ hoặc queue backlog trước khi xác định message có giá trị nghiệp vụ hay không. Với event đã xử lý một phần, dùng operation state và idempotency record để quyết định có thể redrive an toàn.

## 31. Ví dụ incident: chi phí tăng sau khi thêm thumbnail

Một hệ thống nhận 2.000 ảnh/ngày. Sau khi triển khai thumbnail worker, invocation tăng từ khoảng 2.000 lên 18.000/ngày và storage request tăng mạnh. Log cho thấy cùng uploadId xuất hiện qua nhiều event với object key lần lượt là incoming/photo.jpg, processed/photo-small.jpg và processed/photo-small-small.jpg.

Điều tra:

- Bucket notification đang match mọi ObjectCreated.
- Thumbnail worker ghi output vào cùng bucket.
- Output prefix không bị loại khỏi notification.
- Intake function tạo job mới cho mọi object.
- Worker tiếp tục tạo thumbnail cho thumbnail.

Containment và sửa lỗi:

- Tạm thu hẹp notification chỉ nhận prefix incoming/.
- Dừng xử lý các event thuộc processed/ đang nằm trong queue.
- Thêm filter ở IaC và code guard cho event type.
- Dùng object version và operation ID để dedupe.
- Thêm integration test chứng minh derivative không kích hoạt intake.
- Redrive có chọn lọc các upload gốc chưa xử lý.
- Theo dõi invocation/business operation ratio và cost per accepted image.

Sau sửa, mỗi upload gốc chỉ tạo một intake event và một processing job theo thiết kế. Chỉ số thành công là throughput nghiệp vụ được khôi phục, queue age giảm và amplification ratio trở về baseline, không đơn thuần là invocation count giảm.

## 32. Alert và dashboard

Dashboard incident nên hiển thị cùng timeline:

- Invocations, errors, throttles và concurrency theo function.
- Ingress/egress của queue, oldest message age và DLQ.
- Event bus matched rules và failed target delivery.
- Storage PUT/GET theo bucket/prefix.
- Database write/stream count.
- Workflow execution/transition count.
- Cost/usage theo service và region.
- Business operations thành công.
- Amplification ratio, retry ratio và cost per success.

Alert nên dựa trên baseline theo workload. Ví dụ:

- Invocation/business operation ratio vượt baseline nhiều lần trong 10 phút.
- Queue oldest age tăng liên tục.
- DLQ ingress lớn hơn 0 đối với luồng quan trọng.
- Outbox pending age vượt SLA.
- Function concurrency chạm giới hạn cùng lúc với error rate tăng.
- Storage writes trên mỗi upload vượt ngưỡng.
- Cost anomaly theo service vượt budget threshold.

Không đặt một ngưỡng invocation cố định cho mọi function. Function xử lý batch và function HTTP có profile khác nhau.

## 33. Kiểm thử để ngăn trigger loop tái diễn

Test cần xác minh topology và side effect, không chỉ unit test business logic.

| Test | Điều cần chứng minh |
|---|---|
| Upload object input | Chỉ intake trigger được gọi |
| Worker ghi derivative | Derivative không kích hoạt intake |
| Event output cùng source | Rule input không match event output |
| Consumer retry cùng eventId | Side effect chỉ xảy ra một lần |
| Consumer timeout sau commit | Redelivery không tạo duplicate |
| Queue poison message | Sau giới hạn retry đi vào DLQ |
| Batch partial failure | Message thành công không bị xử lý lặp ngoài ý muốn |
| Scheduler chạy hai lần | Checkpoint/idempotency ngăn duplicate job |
| Webhook timeout | Retry không tạo operation thứ hai |
| IaC plan thay filter | Policy test phát hiện rule quá rộng |

Có thể viết architecture test hoặc policy-as-code để cấm trigger bucket output, cấm event rule wildcard trong môi trường production hoặc yêu cầu mọi queue consumer có DLQ. Test phải dựa trên cấu hình thực tế được deploy, không chỉ file mẫu.

## 34. Runbook xử lý trigger loop và cost spike

### Khi nhận alert

1. Ghi incident start time, timezone, service và region.
2. Xác nhận metric bất thường và baseline.
3. Chọn top function/queue/resource theo contribution.
4. Lấy event mẫu, eventId, operationId, correlationId và causationId.
5. Dựng event graph từ producer đến side effect.
6. Kiểm tra retry count, visibility timeout và acknowledgement.
7. Kiểm tra deployment/IaC/config change gần nhất.
8. Xác định cạnh khép kín trong trigger graph.
9. Chọn containment nhỏ nhất có thể.
10. Ghi lại config snapshot và người thực hiện.

### Trong lúc containment

- Theo dõi invocation, ingress, queue age và downstream load.
- Giữ log/audit đủ để điều tra.
- Không xóa queue, event, object hoặc execution tùy tiện.
- Xác định các business operation bị ảnh hưởng.
- Thông báo trạng thái qua kênh incident theo quy trình tổ chức.

### Khi recovery

- Sửa trigger filter/route và triển khai có kiểm soát.
- Chạy test một event đại diện.
- Xác minh không còn chu trình.
- Redrive message theo batch nhỏ.
- Kiểm tra idempotency và trạng thái nghiệp vụ.
- Đối chiếu dữ liệu bị thiếu hoặc duplicate.
- Theo dõi cost per success sau khi backlog giảm.

### Sau incident

- Lưu timeline, event sample, root cause và config diff.
- Ghi rõ trigger nào tạo loop và vì sao guard/filter không bắt được.
- Bổ sung test tự động.
- Cập nhật dashboard, alert và runbook.
- Đặt owner và deadline cho action item.
- Theo dõi cost anomaly trong giai đoạn sau deploy.

## 35. Checklist production

- **Trigger graph:** có sơ đồ producer, resource, function, queue và consumer.
- **Event filters:** source, type, resource và prefix/suffix đủ cụ thể.
- **Output isolation:** output không nằm trong vùng input trigger theo dõi.
- **Event lineage:** có eventId, operationId, correlationId và causationId.
- **Idempotency:** dedupe bền vững cho HTTP command, queue message và event.
- **Retry:** phân loại lỗi, backoff, jitter, max attempts và DLQ.
- **Queue:** visibility timeout, batch size, partial failure và concurrency được cấu hình.
- **Concurrency:** có giới hạn phù hợp với database và downstream capacity.
- **Java runtime:** timeout, connection pool, SDK client reuse và thread usage được kiểm soát.
- **Observability:** invocation, retry, queue age, storage writes và cost được liên kết.
- **Cost allocation:** service, environment, region và owner tags nhất quán.
- **Alert:** amplification ratio, DLQ, backlog, outbox age và cost anomaly có ngưỡng.
- **Containment:** có cách pause rule/mapping/scheduler cụ thể và người có quyền thực hiện.
- **Recovery:** có quy trình redrive, replay và reconciliation.
- **IaC:** trigger filters và event source mapping được review/test.
- **Security:** log không chứa token, signed URL hoặc payload nhạy cảm.
- **Incident evidence:** giữ timeline, config snapshot, event sample và deployment ID.
- **Regression test:** output của consumer không quay lại trigger nguồn.

## 36. Kết luận

Trigger loop và retry amplification có thể khiến một event nhỏ tạo ra hàng nghìn invocation, queue message, storage request hoặc workflow transition. Muốn khoanh vùng nhanh, cần dựng event graph và nối log bằng eventId, operationId, correlationId, causationId cùng trigger resource. Sau đó phân biệt traffic burst, fan-out, retry và loop để chọn biện pháp đúng.

Cách phòng tránh hiệu quả nhất là thiết kế filter hạ tầng cụ thể, tách input/output resource, dùng state transition và idempotency bền vững, giới hạn retry/concurrency và quan sát chi phí theo business operation thành công. Khi incident xảy ra, containment phải ngăn tạo thêm công việc mà vẫn giữ lại dữ liệu và bằng chứng. Chỉ redrive sau khi sửa nguyên nhân và xác nhận consumer có thể xử lý duplicate an toàn.

Một hệ thống serverless vận hành tốt không chỉ scale khi tải tăng; nó còn phải có khả năng giải thích tại sao mỗi function được gọi, event nào đã tạo ra invocation đó và chi phí nào được tạo ra cho mỗi kết quả nghiệp vụ.
