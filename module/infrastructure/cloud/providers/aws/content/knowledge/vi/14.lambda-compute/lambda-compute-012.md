# Quan sát Lambda và kiểm soát chi phí thực thi

> **Chương:** Điện toán Lambda  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá AWS qua Region/Availability Zone (AZ), IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless; thực hành lựa chọn dịch vụ, thiết kế hệ thống an toàn, giám sát, phục hồi và quản lý chi phí.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **metrics, logs, traces, events** và billing data; xây dựng bức tranh observability cho ứng dụng chạy trên **AWS Lambda**.
2. Diễn giải đúng các metric CloudWatch như **Invocations, Errors, Duration, Throttles, ConcurrentExecutions, AsyncEventAge, AsyncEventsDropped** và **IteratorAge**, gồm nguyên tắc chọn thống kê **Sum / Average / Maximum / p95**.
3. Đọc log **START / END / REPORT**, phân biệt **Duration, Billed Duration, Init Duration, Memory Size, Max Memory Used**; sử dụng structured logging, correlation ID, Logs Insights và log retention.
4. Sử dụng **AWS X-Ray**, **CloudWatch Lambda Insights** và những công cụ theo dõi hỗ trợ khác để điều tra cold start, latency, memory, network và dependency.
5. Phân biệt **synchronous invocation**, **asynchronous invocation** và **event source mapping**; quan sát retries, bản tin trùng, DLQ/destination, queue age và stream lag.
6. Ước lượng chi phí theo **requests, GB-seconds, memory, duration**, Provisioned Concurrency, ephemeral storage, SnapStart và chi phí dịch vụ tích hợp.
7. Tối ưu memory/CPU, timeout, SDK reuse, batch, concurrency, logging và network mà **không hy sinh độ tin cậy hoặc bảo mật**.
8. Đọc cấu hình cùng CloudWatch metrics bằng **AWS CLI chỉ đọc**, thiết kế dashboard, cảnh báo và quy trình điều tra sự cố/chi phí.

## 1. Đặt phạm vi: Lambda được quan sát và tính tiền ra sao?

**AWS Lambda** là dịch vụ compute cho phép chạy code khi có request/sự kiện mà không cần tự quản lý việc cung cấp máy chủ theo cách EC2 truyền thống. Ứng dụng có thể được gọi từ API Gateway, ALB, S3, EventBridge, SNS hoặc thông qua event source mapping với SQS, DynamoDB Streams, Kinesis và các nguồn hỗ trợ.

Tính năng và mô hình giá của AWS Lambda hiện có nhiều dạng compute như **Lambda Event Functions**, **Lambda Managed Instances**, cùng các hình thức khác được công bố theo thời điểm. Bài này tập trung vào **Lambda Event Functions theo mô hình on-demand truyền thống**, thường tính phí theo requests và thời gian thực thi đã điều chỉnh theo memory. Không áp dụng máy móc công thức của Event Functions cho mọi hình thức Lambda compute khác.

Một ứng dụng nhỏ có thể chạy đúng trong lab, nhưng ở production cần trả lời:

- Có bao nhiêu lần gọi, bao nhiêu lỗi và lỗi có ảnh hưởng người dùng không?
- Tác vụ chạy bao lâu ở trung bình và **p95/p99**?
- Có cold starts, throttles hoặc giới hạn concurrency không?
- Những event nào bị retry, rơi vào DLQ hoặc quá hạn?
- Chi phí tăng do **tải nhiều hơn**, **mỗi lần chạy lâu hơn**, **memory lớn hơn** hay **logging/egress**?
- Khi quá tải, ứng dụng có gây áp lực lên RDS, SQS, downstream APIs không?

Một metric riêng lẻ không trả lời được tất cả.

~~~mermaid
flowchart TB
    IN["API Gateway / S3 / SQS / EventBridge"] --> L["AWS Lambda function"]
    L --> DB[("RDS / DynamoDB / S3 / API")]
    L --> CW["CloudWatch Metrics"]
    L --> LOG["CloudWatch Logs / log destination"]
    L --> XR["AWS X-Ray / tracing"]
    CW --> DASH["Dashboard + alarms"]
    LOG --> DASH
    XR --> DASH
    BILL["Cost Explorer / CUR / Budgets"] --> COST["Phân tích chi phí và dự báo"]
    DASH --> OPS["Phát hiện, điều tra, giảm rủi ro"]
    COST --> OPS
~~~

Sơ đồ mang tính logic. Metrics, logs, traces và chi phí có hệ thống lưu trữ, quyền, thời gian cập nhật, retention và cách tính phí **khác nhau**. AWS thường phát hành metric kỹ thuật nhanh hơn dữ liệu chi phí tổng hợp, nên không suy rằng Cost Explorer sẽ hiển thị tiền theo từng request tức thì.

### 1.1. Bốn trụ cột quan sát

| Tín hiệu | Trả lời câu hỏi | Ví dụ trong Lambda | Giới hạn |
| --- | --- | --- | --- |
| **Metrics** | Hệ thống đang khỏe không, xu hướng thay đổi thế nào? | Invocations, Errors, Duration p95, ConcurrentExecutions. | Không mô tả đầy đủ một request cụ thể. |
| **Logs** | Một invocation đã làm gì, lỗi nào xảy ra? | Java exception, business status, START/REPORT, requestId. | Lượng log lớn, cần tìm kiếm và bảo vệ dữ liệu nhạy cảm. |
| **Traces** | Thời gian đi qua các thành phần và dependency ở đâu? | API Gateway → Lambda → DynamoDB, X-Ray segments. | Phụ thuộc sampling/instrumentation và có chi phí. |
| **Events/state** | Sự kiện nguồn và trạng thái xử lý có bị chậm, trùng, bỏ sót không? | SQS backlog, DLQ, EventBridge rule failures, DynamoDB stream lag. | Không phải Lambda metric nào cũng thấy toàn bộ trạng thái upstream. |

**Billing/usage data** là một lớp bổ sung để quy chiếu nguyên nhân tăng chi phí và đo hiệu quả tối ưu, không đồng nghĩa real-time health telemetry.

### 1.2. Mục tiêu SLI/SLO trước khi chọn dashboard

Ví dụ sản phẩm có API nhận yêu cầu tạo hóa đơn:

- **Availability SLI:** tỷ lệ request API hoàn tất hợp lệ, không chỉ tỷ lệ Lambda không throw exception.
- **Latency SLI:** p95 end-to-end API dưới 500 ms trong mức tải thông thường.
- **Background processing SLI:** 99% hóa đơn từ queue được xử lý trong 2 phút.
- **Correctness SLI:** không phát hành trùng một hóa đơn khi retry.
- **Cost KPI:** chi phí xử lý mỗi 1.000 hóa đơn hợp lệ, gồm Lambda và downstream.

Nếu chỉ theo dõi **Invocations** và **Errors**, bạn sẽ bỏ sót API trả HTTP 500 như một response hợp lệ về mặt runtime, sự kiện queue chưa tới handler hoặc xử lý nghiệp vụ bị trùng.

## 2. Vòng đời Lambda và thời gian thực thi

Khi có invocation, Lambda dùng một **execution environment** với runtime được cấu hình. Một environment có thể được **khởi tạo mới (cold start)** hoặc **tái sử dụng (warm reuse)**; không nên mặc định mọi invocation đều cold start.

~~~mermaid
sequenceDiagram
    participant E as Event source
    participant S as Lambda service
    participant R as Runtime / extension
    participant H as Function handler
    E->>S: Invoke
    alt Cold start
      S->>R: INIT (runtime, dependencies, init code)
    else Warm reuse
      Note over R: Execution environment đã có
    end
    S->>H: INVOKE event
    H-->>S: Response / error
    S-->>E: Kết quả theo invocation mode
    Note over S,R: Freeze/reuse hoặc shutdown theo lifecycle
~~~

### 2.1. Init, invoke và shutdown

- **INIT:** Lambda tải runtime, layers, dependencies và thực thi initialization code ngoài handler; các extension cũng có thể chạy initialization.
- **INVOKE:** handler xử lý event, gọi dependencies, trả response hoặc ném lỗi.
- **SHUTDOWN:** execution environment được dừng theo lifecycle của Lambda.

Nếu execution environment được reuse, một số đối tượng static, SDK clients hoặc connection pools có thể tồn tại giữa các invocation. **Không có bảo đảm reuse**; code phải hoạt động đúng cả khi được khởi tạo mới.

### 2.2. Cold start không bằng Duration metric

CloudWatch **Duration** đo thời gian thực hiện handler theo định nghĩa metric được công bố, **không tính toàn bộ thời gian cold initialization**. Ngược lại, thời gian khách hàng nhìn thấy ở API Gateway/ALB có thể bao gồm phần cold start và overhead của các lớp network/integration.

Trong REPORT log có thể xuất hiện:

~~~text
START RequestId: a1b2c3d4-EXAMPLE Version: $LATEST
END RequestId: a1b2c3d4-EXAMPLE
REPORT RequestId: a1b2c3d4-EXAMPLE
Duration: 183.42 ms
Billed Duration: 319 ms
Memory Size: 512 MB
Max Memory Used: 207 MB
Init Duration: 135.58 ms
~~~

**Các con số là minh họa**. Nội dung/format REPORT có thể thay đổi theo runtime, loại logging và thời điểm AWS cập nhật.

Nhận xét:

- Handler mất khoảng **183 ms** theo Duration.
- **Billed Duration** có thể lớn hơn vì còn yếu tố init/extension và quy tắc tính phí/rounding tương ứng.
- Lambda được cấu hình **512 MB**, không tính tiền theo **207 MB đã dùng thực tế**.
- **Init Duration** cho biết initialization cost quan sát được, không phải cứ cộng bằng tay vào mỗi Invocation hoặc thay metric Duration.

### 2.3. Suppressed init và timeout

Khi một invocation thất bại, runtime có thể được reset và một initialization tiếp theo có thể diễn ra trong pha INVOKE (được AWS gọi **suppressed init**). Một số trường hợp log REPORT/Duration có thể khó lý giải nếu chỉ nhìn START/END; **Lambda Telemetry API** cho phép xem những lifecycle events chi tiết hơn.

Timeout là lỗi runtime quan trọng:

- Nếu handler vượt **Timeout** đã cấu hình, Lambda dừng invocation.
- CloudWatch **Errors** có thể tăng và REPORT ghi **Status: timeout** theo log format.
- Client/downstream có thể retry hoặc không tùy đường invocation.
- Tăng timeout chỉ làm tác vụ có thể kéo dài hơn; không giải quyết API bị treo vì DB query hoặc không có network egress.

Với Event Functions chuẩn, timeout cấu hình thông dụng có giới hạn **tối đa 900 giây (15 phút)**; các chế độ Lambda compute đặc thù có giới hạn riêng cần đối chiếu tài liệu hiện hành.

## 3. CloudWatch metrics mặc định của Lambda

Lambda tự phát nhiều metric vào namespace **AWS/Lambda**. Khi xem metric phải chọn đúng **Region, FunctionName, Resource hoặc ExecutedVersion**, vì một function/alias/version có thể có các dimension và lượng traffic khác nhau.

### 3.1. Nhóm invocation và lỗi

| Metric | Ý nghĩa | Thống kê nên xem | Hành động khi bất thường |
| --- | --- | --- | --- |
| **Invocations** | Số lần function code được gọi, gồm thành công và function errors; request bị throttle trước khi invoke không được tính. | **Sum** theo phút/giờ. | So sánh traffic source, deployment, retry và chi phí. |
| **Errors** | Số invocations kết thúc bằng function/runtime error, như unhandled exception, timeout. | **Sum**, đồng thời tính tỷ lệ lỗi. | Xem logs, request IDs, downstream, error type. |
| **Throttles** | Số invocation requests bị từ chối vì không đủ concurrency/giới hạn tương ứng. | **Sum**. | Kiểm tra reserved/account concurrency, burst, upstream retry. |
| **DeadLetterErrors** | Lambda không gửi được event bất đồng bộ tới dead-letter queue đã cấu hình. | **Sum**. | Kiểm tra queue/topic, policy và KMS. |
| **DestinationDeliveryFailures** | Gửi record tới destination thất bại với cơ chế hỗ trợ. | **Sum**. | Kiểm tra destination ARN, resource policy, payload, quota. |
| **RecursiveInvocationsDropped** | Lambda chặn invocation bị nghi do vòng lặp đệ quy trong cơ chế phát hiện hỗ trợ. | **Sum**. | Kiểm tra trigger tự gọi, S3 output/event loop và retry. |

**Invocations không phải số HTTP requests của người dùng cuối.** Một request API có thể gọi nhiều Lambda functions, một event SQS batch có thể chứa nhiều messages trong **một invocation**, và retries có thể phát sinh invocations bổ sung.

### 3.2. Tính error rate đúng cách

Trong một khoảng thời gian:

\[
\text{Lambda Error Rate} =
\frac{\text{Sum(Errors)}}{\text{Sum(Invocations)}}\times100\%
\]

Ví dụ 20 Errors trên 4.000 Invocations → **0,5% Lambda error rate**.

Nhưng phải hỏi thêm:

- Nếu **Invocations = 0**, tỷ lệ không xác định; không chia cho 0 rồi xem là 0% hoặc 100%.
- Nếu code bắt exception và trả **HTTP 500** trong body/response một cách có kiểm soát, Lambda runtime có thể đánh dấu invocation **thành công**, metric Errors vẫn bằng 0.
- Nếu API Gateway/ALB bị lỗi **trước khi gọi Lambda**, Lambda Invocations có thể không tăng.
- Nếu một message được retry nhiều lần, mỗi lần handler được invoke và throw error có thể tạo thêm Errors.

Vì vậy dashboard quan trọng cần thêm **API Gateway 4xx/5xx, ALB 5xx, successful business transactions, SQS DLQ/age** hoặc custom metrics.

### 3.3. Nhóm performance

| Metric | Đơn vị/ý nghĩa | Khuyến nghị |
| --- | --- | --- |
| **Duration** | Milliseconds cho việc xử lý handler. | Xem Average, p95/p99 và Maximum theo workload; so trước/sau deploy. |
| **PostRuntimeExtensionsDuration** | Thời gian extensions xử lý hậu runtime theo khả năng đo. | Nếu cao, xem observability/extension overhead. |
| **IteratorAge** | Độ tuổi record stream khi được xử lý, thường Kinesis/DynamoDB/DocumentDB stream sources hỗ trợ. | Xem Maximum hoặc percentile/aggregation phù hợp; cảnh báo stream lag. |
| **OffsetLag** | Độ chậm xử lý offset cho Kafka/MSK khi được hỗ trợ. | Giám sát backlog theo Kafka topic/consumer context. |

**IteratorAge không phải metric backlog của SQS.** Với SQS, dùng **ApproximateAgeOfOldestMessage**, số message visible/in-flight, DLQ và những event source mapping metrics được bật.

### 3.4. Nhóm concurrency

| Metric | Nội dung | Tình huống |
| --- | --- | --- |
| **ConcurrentExecutions** | Số invocations đang thực thi đồng thời. | Phân tích peak và quota. |
| **UnreservedConcurrentExecutions** | Concurrency thuộc pool không được reserve trong Region. | Tranh chấp capacity giữa functions. |
| **ClaimedAccountConcurrency** | Capacity account đã được claim theo định nghĩa AWS. | Ước lượng nguy cơ chạm account concurrency quota. |
| **ProvisionedConcurrentExecutions** | Concurrency đang sử dụng từ provisioned pool của version/alias. | Xem mức sử dụng provisioned capacity. |
| **ProvisionedConcurrencyUtilization** | Tỷ lệ provisioned capacity được sử dụng. | Quyết định giảm/tăng provisioned capacity. |
| **ProvisionedConcurrencyInvocations** | Invocations được xử lý bằng provisioned concurrency. | Đánh giá lợi ích provisioned capacity. |
| **ProvisionedConcurrencySpilloverInvocations** | Invocations tràn sang on-demand vì hết provisioned capacity. | Kiểm tra spikes/cold starts. |

Dùng **Maximum** khi xem concurrency peak; **Sum(ConcurrentExecutions)** theo các periods không có ý nghĩa “tổng số invocations trong giờ” như Sum(Invocations).

### 3.5. Metric dimensions và khoảng thời gian

CloudWatch có thể trả về các time series khác nhau cho:

- **FunctionName:** tổng quan function theo dimension phù hợp.
- **Resource:** function name với alias hoặc version identifier.
- **ExecutedVersion:** version thực sự thực thi.

Khi canary bằng Lambda alias trọng số, chỉ xem tổng FunctionName có thể che lỗi chỉ xảy ra trên **version mới**. Cần phân tách theo alias/version, đồng thời so sánh overall traffic.

**Không tự cộng bừa nhiều dimensions** rồi coi đó là tổng duy nhất: có thể trùng cùng invocation dưới các time series khác nhau. Xác định mục đích thống kê trước khi aggregate.

## 4. Chọn đúng statistic: Sum, Average, Maximum, p95

CloudWatch metrics là những chuỗi số liệu theo period; chọn statistic sai có thể tạo kết luận sai.

| Câu hỏi | Metric/statistic phù hợp | Tránh |
| --- | --- | --- |
| Trong 5 phút có bao nhiêu requests được invoke? | **Invocations — Sum**, period 300 s. | Average như số request tổng. |
| Trong 5 phút có bao nhiêu lần throw exception? | **Errors — Sum**, period 300 s. | Maximum như tổng lỗi. |
| Function chạm concurrency tối đa chưa? | **ConcurrentExecutions — Maximum**. | Sum của các sample concurrency. |
| p95 handler duration là bao nhiêu? | **Duration — p95** theo time window phù hợp. | Chỉ xem Average rồi kết luận không có outliers. |
| Stream có record quá lâu chưa xử lý? | **IteratorAge — Maximum** hoặc thống kê tương ứng. | Chỉ xem Invocations tăng. |
| Async Lambda queue có bị tồn đọng? | **AsyncEventAge — Maximum/p95**, AsyncEventsDropped. | Giả định Errors=0 là không lag. |

### 4.1. Ví dụ Average che khuất tail latency

Một function có 100 invocations:

- 95 invocations xử lý **100 ms**.
- 5 invocations xử lý **5.000 ms**.

Duration trung bình khoảng:

\[
\frac{95\times100+5\times5000}{100}=345 \text{ ms}
\]

Một số người dùng vẫn chịu latency **5 giây** dù Average chỉ 345 ms. **p95/p99 và Maximum** có thể phản ánh tác động tail latency tốt hơn.

Cẩn thận: **p95 Duration** đo handler, không phải end-to-end API. Nếu API Gateway, network hoặc init tạo thêm latency, cần thêm metrics/traces ở tầng request.

### 4.2. Thiếu metric không có nghĩa bằng 0

Khi Lambda không có invocations, một số metrics không phát sample trong khoảng đó. Alarm cần cấu hình **missing data treatment** phù hợp:

- Với error-rate trên function hiếm khi được gọi, Missing có thể là bình thường.
- Với một nhiệm vụ phải chạy mỗi phút, **không có Invocations** có thể là sự cố.
- Với provisioned utilization, không có traffic có thể khiến metric không phát, không đồng nghĩa provisioned concurrency đang sử dụng 0 theo một sample.

Đừng đánh đồng thiếu dữ liệu và trạng thái khỏe; hãy dựa trên **SLO của workload**.

## 5. CloudWatch Logs: từ REPORT đến ứng dụng

Lambda có thể gửi logs tới **Amazon CloudWatch Logs** theo cấu hình. Log group mặc định với Event Function truyền thống thường là:

~~~text
/aws/lambda/<function-name>
~~~

Đây là mẫu tên minh họa; Lambda hỗ trợ tùy chỉnh log group và các đường log destination được hỗ trợ theo tính năng hiện hành.

### 5.1. START, END, REPORT

Với log text, một invocation thường có:

- **START**: request ID và version được execute.
- **END**: kết thúc invocation.
- **REPORT**: Duration, Billed Duration, Memory Size, Max Memory Used và một số thông tin platform khác.

Các log định dạng **JSON** dùng schema tương ứng thay vì nhất thiết phải có ba dòng text giống mẫu. Nếu chọn log-level filtering, một số system log events có thể bị loại theo mức độ.

**RequestId** là khóa tương quan rất quan trọng. Ghi request ID vào logs ở các bước chính để điều tra một invocation cụ thể, nhưng không lưu PII/access tokens vào logs.

### 5.2. Application logging có cấu trúc

Thay vì:

~~~text
Got error. Try again.
~~~

Nên tạo log có đủ thông tin vận hành, ví dụ:

~~~json
{
  "timestamp": "2026-11-20T03:15:00Z",
  "level": "ERROR",
  "service": "invoice-worker",
  "operation": "process-invoice",
  "awsRequestId": "example-request-123",
  "correlationId": "example-correlation-456",
  "errorType": "DatabaseTimeout",
  "durationMs": 3200,
  "attempt": 2
}
~~~

**Đây là JSON app log minh họa.** Khi dùng managed runtime Java, AWS hỗ trợ structured logging cho **LambdaLogger** hoặc **Log4j2** theo điều kiện; có thể cấu hình logging **JSON** qua Lambda LoggingConfig. Không phải cứ in một chuỗi JSON bằng mọi thư viện logging thì Lambda luôn phân loại severity hoàn toàn như mong muốn; cần kiểm tra runtime/logger.

Cần đảm bảo:

- **Correlation ID** xuyên qua API Gateway/SQS/EventBridge khi có thể.
- Ghi **event type** và mã nghiệp vụ hoặc ID đã được phép log, không ghi nguyên payload chứa PII.
- Không log authorization header, cookies, access keys, password, Secrets Manager response hay toàn bộ dữ liệu khách hàng.
- Khi có error, ghi **error type/stack trace** đã được kiểm soát; tránh tạo nhiều log giống nhau ở nhiều layers.
- Có **schema log ổn định** để query dễ hơn và không tràn chi phí do mỗi request in hàng trăm KB.

### 5.3. Advanced logging controls

Lambda cho phép cấu hình những thông số như:

~~~json
{
  "LoggingConfig": {
    "LogFormat": "JSON",
    "ApplicationLogLevel": "INFO",
    "SystemLogLevel": "INFO",
    "LogGroup": "/aws/lambda/invoice-worker"
  }
}
~~~

Đây là **đoạn nội dung cấu hình minh họa** từ Lambda API; không phải toàn bộ request tạo function.

- **LogFormat:** JSON hoặc Text.
- **ApplicationLogLevel:** TRACE, DEBUG, INFO, WARN, ERROR, FATAL theo logger/runtime được hỗ trợ.
- **SystemLogLevel:** DEBUG, INFO, WARN.
- **LogGroup:** log group nhận dữ liệu theo cấu hình.

Giảm log-level từ DEBUG sang INFO/WARN có thể giảm lượng logs và phí CloudWatch, nhưng **không được tắt log lỗi hoặc audit cần thiết** chỉ để tiết kiệm. Bật DEBUG trong thời gian điều tra rồi giảm lại, với quyền quản trị được kiểm soát.

### 5.4. Retention và phân quyền logs

CloudWatch Logs tính phí ingest, lưu trữ và truy vấn theo bảng giá/tính năng liên quan. Nếu không đặt retention thích hợp, log group có thể lưu lâu hơn nhu cầu thực tế.

Ví dụ policy retention:

| Môi trường | Retention tham khảo | Điều kiện |
| --- | --- | --- |
| Dev/sandbox | 7–14 ngày. | Chỉ dùng cho debug ngắn hạn; kiểm tra yêu cầu công ty. |
| Staging | 14–30 ngày. | Hỗ trợ điều tra regression/deployment. |
| Production | 30–90 ngày hoặc theo policy. | Bảo đảm compliance, audit và nhu cầu forensic. |
| Audit bắt buộc lâu dài | Giải pháp archive/retention riêng. | Có kiểm soát truy cập, encryption, bất biến khi cần. |

Đây là **ví dụ chính sách**, không phải mặc định AWS hay khuyến nghị pháp lý. Quy định retention phải được chủ dữ liệu/pháp chế/security phê duyệt.

IAM cần tách:

- Runtime role ghi logs: **logs:CreateLogStream**, **logs:PutLogEvents** và các quyền phù hợp; log group có thể được tạo trước qua IaC.
- Dev/support đọc logs: **logs:DescribeLogGroups**, **logs:FilterLogEvents**, **logs:StartQuery**, **logs:GetQueryResults** theo phạm vi cần.
- Admin thay retention/log destination: quyền riêng, có review.

Không cấp **logs:\*** trên mọi log group chỉ để một handler ghi log.

## 6. CloudWatch Logs Insights: điều tra theo request, lỗi và duration

CloudWatch Logs Insights cho phép truy vấn dữ liệu log theo khoảng thời gian được chọn. Nên khoanh **Region, log groups, time window** và fields để tránh quét quá nhiều dữ liệu gây chi phí.

### 6.1. Tìm lỗi gần đây

~~~text
fields @timestamp, @message, @logStream
| filter @message like /ERROR|Exception|Task timed out/
| sort @timestamp desc
| limit 50
~~~

Câu truy vấn phụ thuộc định dạng log; với JSON structured logs, dùng đúng field được Logs Insights nhận diện, ví dụ **level**, **errorType**, **awsRequestId** nếu schema đã cung cấp.

### 6.2. Phân tích thời gian thực thi từ REPORT (text format)

~~~text
filter @type = "REPORT"
| stats count(*) as requests,
        avg(@duration) as avgDurationMs,
        pct(@duration, 95) as p95DurationMs,
        max(@duration) as maxDurationMs,
        max(@maxMemoryUsed / 1024 / 1024) as peakMemoryMB
  by bin(5m)
| sort bin(5m) desc
~~~

Đây là **mẫu Logs Insights query** dùng những fields do Lambda system logs/Log Insights phát hiện trong format phù hợp. Kiểm tra field discovery hiện hành và log format của function. Nếu fields thiếu, query cần điều chỉnh theo cấu trúc JSON hoặc regex parse tương ứng.

Không đánh đồng **@duration** với **@billedDuration**, hay Max Memory Used với memory được cấu hình. Chi phí Lambda tính theo **memory configured** và **billed duration**, không theo peak memory used.

### 6.3. Tìm requestId

~~~text
fields @timestamp, @message, @requestId
| filter @requestId = "example-request-123"
| sort @timestamp asc
| limit 100
~~~

Nếu ứng dụng tự ghi **awsRequestId** trong JSON, tên field có thể khác **@requestId** của Logs Insights. Trước khi dùng query trong production, kiểm tra các fields thực tế ở log group.

### 6.4. Metric filter và custom alarms

Bạn có thể dùng **CloudWatch Logs metric filters** hoặc **Embedded Metric Format (EMF)** để biến các sự kiện ứng dụng thành custom metrics.

Ví dụ chỉ số nghiệp vụ **InvoiceProcessed** có thể phản ánh số hóa đơn được xử lý thành công, khác với **Lambda Invocations**. Nhưng metric filter/EMF thường tạo thêm charges theo CloudWatch custom metrics và log ingestion.

Đặc biệt tránh **high-cardinality dimensions** như requestId, userId hay orderId: mỗi giá trị dimension mới có thể làm phát sinh một time series mới, khiến chi phí metric lớn và dashboard khó sử dụng.

## 7. AWS X-Ray, Lambda Insights và những lớp telemetry

### 7.1. AWS X-Ray: phân tích request path

X-Ray hỗ trợ tracing phân tán để xem các thành phần mà một yêu cầu đi qua, ví dụ:

~~~mermaid
flowchart LR
    API["API Gateway"] --> L["Lambda invoice-api"]
    L --> DDB[("DynamoDB")]
    L --> EXT["External payment API"]
    API -.->|"Trace context"| XR["X-Ray"]
    L -.-> XR
    DDB -.-> XR
    EXT -.-> XR
~~~

- **Active tracing** cho phép Lambda tạo traces cho sampled invocations và gửi tới X-Ray theo cơ chế hỗ trợ.
- **PassThrough** chuyển ngữ cảnh trace ở các tích hợp hỗ trợ thay vì tự tạo sampled trace theo cách Active.
- Tracing trong Lambda cần execution role có quyền gửi trace, ví dụ quyền từ **AWSXRayDaemonWriteAccess** hoặc policy tương ứng.
- Dùng instrumentation/SDK hoặc **OpenTelemetry** khi cần trace sâu các database calls, AWS SDK calls hoặc custom code paths.
- **Sampling** nghĩa là không phải mọi invocation đều có trace; đừng dựa vào tracing để tạo audit log toàn bộ request.

Một API có 500 ms end-to-end nhưng Lambda handler Duration chỉ 120 ms: trace có thể giúp phân biệt thời gian **API Gateway integration, cold initialization, SDK calls và dependency latency** khi instrumentation đủ.

### 7.2. Lambda Insights: theo dõi runtime/resource

**CloudWatch Lambda Insights** cung cấp thêm metrics/diagnostics ở mức execution environment như **memory, CPU time, disk, network, cold starts** theo khả năng hỗ trợ.

AWS cung cấp extension/layer cho các runtimes tương ứng; khi bật sẽ có thêm metrics và performance log events. Dù giúp điều tra, nó cũng tăng:

- Log ingestion/storage.
- CloudWatch metric charges.
- Extension overhead có thể ảnh hưởng duration và billed time.

Bật Lambda Insights cho workload hoặc giai đoạn cần thông tin chi tiết, theo dõi chi phí, tránh tự động bật mọi extension ở mọi function không có nhu cầu.

### 7.3. CloudWatch Application Signals, Telemetry API và Powertools

Những lựa chọn bổ sung:

- **CloudWatch Application Signals:** quan sát ứng dụng, dịch vụ, operations/SLO theo khả năng tích hợp.
- **Lambda Telemetry API:** extensions nhận lifecycle, platform, function logs và tracing telemetry theo giao diện hỗ trợ.
- **Powertools for AWS Lambda (Java/Python/TypeScript/.NET):** tiện ích thực hành logging, tracing, metrics và idempotency/batch processing theo runtime.
- **OpenTelemetry / ADOT:** instrument nhiều dịch vụ và xuất traces/metrics theo mô hình được hỗ trợ.

Không cần bật tất cả công cụ cùng lúc. Mỗi extension/library có **operational overhead, maintenance, IAM và chi phí**. Ưu tiên quan sát đủ các SLI/SLO rồi tăng độ chi tiết khi điều tra thực tế.

## 8. Ba cơ chế invocation và cách quan sát khác nhau

Lambda nhận sự kiện theo những mô hình khác nhau. Chẩn đoán retries/cost sẽ sai nếu nhầm các mô hình này.

| Kiểu | Ai gọi Lambda? | Xử lý lỗi/retry | Tín hiệu quan trọng |
| --- | --- | --- | --- |
| **Synchronous** | API Gateway, ALB, Invoke API kiểu RequestResponse. | Caller thường nhận response/error; caller quyết định retry. | End-to-end latency, Lambda Errors, API 4xx/5xx, throttles. |
| **Asynchronous** | S3, SNS, EventBridge hoặc Invoke API Event theo tích hợp. | Lambda queue nội bộ rồi retry theo quy tắc async và cấu hình; có DLQ/destination khi thiết lập. | AsyncEventsReceived, AsyncEventAge, AsyncEventsDropped, destination failures. |
| **Event source mapping (ESM)** | Lambda poll SQS, DynamoDB Streams, Kinesis, MSK/Kafka và nguồn hỗ trợ. | Retry, batch, visibility/iterator logic phụ thuộc nguồn. | SQS backlog, IteratorAge, ESM metrics, partial batch, mapping state. |

### 8.1. Synchronous: handler không lỗi nhưng API vẫn lỗi

Ví dụ Java handler bắt exception và trả:

~~~json
{
  "statusCode": 500,
  "body": "{\"error\":\"database unavailable\"}"
}
~~~

Về mặt Lambda runtime, invocation có thể đã **thành công** nếu handler trả object bình thường. Khi đó **Errors metric có thể không tăng**, dù API Gateway/ALB vẫn trả HTTP 500 cho client theo integration response.

**Kết luận:** theo dõi **business/API errors** riêng với **Lambda execution errors**. Đừng đánh giá availability của API chỉ bằng Errors của Lambda.

### 8.2. Asynchronous: đã nhận event chưa có nghĩa đã chạy

Với async invocation, Lambda có thể:

1. Nhận event và xếp vào hàng đợi nội bộ.
2. Đợi execution capacity.
3. Invoke handler.
4. Retry khi handler lỗi hoặc khi bị throttle/system error.
5. Gửi failed-event record tới destination/DLQ khi cấu hình và đủ điều kiện, hoặc drop khi hết retry/tuổi event.

Các defaults về retry của AWS có thể phụ thuộc lỗi. Theo tài liệu, **function error** trong async thường có tối đa **hai lần retry** theo cấu hình mặc định; với **throttling/system errors**, Lambda áp dụng backoff và có thể tiếp tục thử cho tới khi event quá tuổi (mặc định tối đa sáu giờ, tùy cấu hình).

Metrics cần xem:

- **AsyncEventsReceived**: số events được Lambda queue thành công.
- **AsyncEventAge**: thời gian event nằm chờ trước khi handler được invoke.
- **AsyncEventsDropped**: số events bị loại khi không được thực thi thành công.
- **DestinationDeliveryFailures/DeadLetterErrors**: pipeline xử lý failure record cũng có thể lỗi.

**Đừng suy rằng số AsyncEventsReceived bằng số Invocations trong cùng phút.** Sự khác biệt có thể do queue delay, retries hoặc event đã drop.

### 8.3. Event source mapping từ SQS

~~~mermaid
flowchart LR
    P["Producer"] --> Q["SQS Standard"]
    Q -->|"Lambda poller lấy batch"| L["Lambda worker"]
    L -->|"Ghi output"| S3[("S3/DynamoDB")]
    Q -.->|"Redrive khi retry vượt ngưỡng"| DLQ["SQS DLQ"]
    Q --> M["ApproximateAgeOfOldestMessage"]
    L --> CW["Errors, Duration, concurrency"]
~~~

Đối với SQS:

- Lambda poll queue và invoke handler **đồng bộ với một batch**; đó **không** phải hàng đợi async nội bộ giống S3 → Lambda.
- **Một Invocation có thể chứa nhiều SQS messages**.
- Message processing có thể lặp vì SQS/event source mapping có semantics **at-least-once**.
- Khi handler throw lỗi cho toàn batch, các message thành công trong batch có thể bị xử lý lại sau visibility timeout.
- Có thể bật **ReportBatchItemFailures** để báo lỗi từng message, tránh xử lý lại toàn bộ batch.
- Với SQS FIFO, khi một record lỗi cần xử lý tiếp đúng quy tắc thứ tự, thường dừng và trả về các message thất bại/chưa xử lý trong nhóm tương ứng.

Ngoài AWS/Lambda metrics, nên xem:

| SQS metric | Ý nghĩa |
| --- | --- |
| **ApproximateNumberOfMessagesVisible** | Số message đang sẵn sàng được nhận. |
| **ApproximateNumberOfMessagesNotVisible** | Message đang in-flight/ẩn bởi visibility timeout. |
| **ApproximateAgeOfOldestMessage** | Thời gian chờ của một message lâu nhất theo semantics SQS. |
| **NumberOfMessagesSent / Received / Deleted** | Tốc độ enqueue, poll và delete; không đồng nghĩa số business jobs duy nhất. |
| **DLQ visible/age** | Công việc thất bại cần điều tra và replay. |

Một Lambda worker có **Errors = 0** nhưng queue age tăng có thể đang **thiếu concurrency, sai event source mapping, không nhận được message hoặc xử lý quá chậm**.

### 8.4. Stream event sources

Với DynamoDB Streams và Kinesis, Lambda xử lý record batches theo shard và những giới hạn/semantics cụ thể:

- **IteratorAge** tăng có thể gợi ý consumer không theo kịp producer.
- Retry một batch lỗi có thể chặn tiến độ của shard, tùy chính sách xử lý lỗi.
- Partial batch/bisect batch, maximum record age, maximum retry attempts hoặc on-failure destination có thể hỗ trợ theo nguồn và cấu hình.
- Tăng concurrency không phải lúc nào cũng tăng throughput nếu giới hạn **shards, parallelization factor hoặc downstream capacity**.

Không dùng **SQS queue age** và **Kinesis IteratorAge** như hai metric đồng nghĩa trong mọi tình huống.

## 9. Concurrency, throttling và giới hạn downstream

### 9.1. Concurrency từ lưu lượng và duration

Một ước lượng thường dùng:

\[
\text{Concurrent executions trung bình}
\approx
\text{Requests per second}
\times
\text{Average duration (seconds)}
\]

Ví dụ API nhận **120 requests/giây**, trung bình handler mất **0,4 giây**:

\[
120\times0.4=48
\]

Nhu cầu concurrency trung bình vào khoảng **48** trong điều kiện traffic đều và không có các burst hay overhead đáng kể. Peak thực tế có thể cao hơn vì traffic spikes, retries, cold starts, tail latency và biến động thời gian xử lý.

Đây là công thức **ước tính**, không phải một API trả về chính xác số environment cần dự phòng. Khi thiết kế, xem thêm **Maximum ConcurrentExecutions** và concurrency scaling limits hiện hành của Lambda theo Region.

### 9.2. Reserved concurrency

**Reserved concurrency** có hai ý nghĩa:

- Giữ một phần account concurrency quota dành riêng cho function quan trọng.
- Đặt trần concurrency của function để tránh dùng vượt mức và làm nghẽn downstream.

Ví dụ Function A có reserved concurrency **50**. Khi Function A đang xử lý 50 invocations đồng thời, invocations thêm có thể bị **throttle** theo mô hình gọi. 50 units này được reserve cho A ngay cả lúc A không dùng hết, giảm pool cho functions khác.

**Reserved concurrency không có phí capacity riêng**, nhưng cấu hình vẫn ảnh hưởng khả năng phục vụ và có thể gây retries/giảm availability nếu đặt thấp.

**Reserved concurrency = 0** có thể được dùng để cố ý ngừng function được invoke theo cơ chế quản trị, nhưng với async/SQS/events cần đánh giá **event retries, backlog, age và drop**, không coi đây là công tắc dừng miễn phí không hệ quả.

### 9.3. Provisioned concurrency

**Provisioned concurrency** duy trì những execution environments đã khởi tạo sẵn cho một **published version hoặc alias** theo điều kiện hỗ trợ.

Lợi ích: giảm cold start cho workload nhạy latency.

Đổi lại:

- Có **phí provisioned concurrency theo thời gian được provision** ngay cả khi lượng request thấp.
- Compute/invocation pricing khi sử dụng provisioned concurrency có cấu trúc riêng, cần xem bảng giá hiện hành.
- Nếu traffic vượt provisioned capacity, invocations có thể **spill over** sang on-demand trong phạm vi concurrency còn lại và có thể gặp cold starts.
- Provisioned concurrency phải xét account quota, reserved concurrency, alias/version deployment và thời gian cấp phát capacity.

Chỉ bật khi **p95/p99 end-to-end latency** chứng minh cold start là bottleneck và lợi ích vượt phí của capacity duy trì sẵn.

### 9.4. Concurrency là ranh giới bảo vệ database

Giả sử mỗi Lambda invocation mở một DB connection, RDS tối đa chấp nhận 100 connections cho workload này. Nếu function có thể scale lên 1.000 concurrent invocations, backend có thể bị quá tải dù Lambda vẫn hoạt động.

Giải pháp:

- Cấu hình reserved concurrency/ESM maximum concurrency phù hợp.
- Reuse DB connection trong warm execution environment khi an toàn.
- Dùng **RDS Proxy** hoặc cơ chế pooling phù hợp khi sử dụng RDS.
- Thêm backpressure qua SQS/batching và idempotent retries.
- Giám sát **DatabaseConnections**, throttling, latency, failover và transaction duration.

Đừng giải quyết mọi timeout bằng cách tăng reserved concurrency: đó có thể là cách tăng áp lực lên dependency đã quá tải.

## 10. Thiết kế dashboard và alerts phục vụ vận hành

Một dashboard Lambda có thể có bốn khu vực:

~~~mermaid
flowchart TB
    SLO["SLO / Business health"] --> D["Dashboard Lambda"]
    R["Requests, Errors, Throttles"] --> D
    P["Duration p95/p99, ConcurrentExecutions"] --> D
    Q["AsyncEventAge / SQS age / IteratorAge"] --> D
    C["GB-s, requests, logs, Cost Explorer"] --> D
    D --> AL["CloudWatch Alarms / SNS / incident workflow"]
~~~

### 10.1. Mẫu cảnh báo tham khảo

| Tín hiệu | Ngưỡng ví dụ | Mức ưu tiên | Cần điều tra |
| --- | --- | --- | --- |
| Lambda Errors ratio | Trên **1%** trong nhiều phút, khi traffic đủ lớn. | Cao. | Exceptions, timeouts, version mới. |
| Lambda Throttles | Sum > **0** lặp lại trên API quan trọng. | Cao. | Account/reserved limit, peak, caller retry. |
| Duration p95 | Vượt **80% timeout** hoặc SLO latency, liên tục. | Cao/trung bình. | Cold starts, SDK/DB/network, memory. |
| ConcurrentExecutions | Gần **80–90% trần** trong khoảng dài. | Trung bình/cao. | Headroom, burst, quota, downstream. |
| AsyncEventsDropped | Bất kỳ số > **0** khi sự kiện là bắt buộc. | Rất cao. | Retry/age, destination, khả năng replay. |
| DeadLetterErrors/DestinationDeliveryFailures | Bất kỳ > **0**. | Cao. | Quyền resource/KMS, target availability. |
| SQS ApproximateAgeOfOldestMessage | > **3 phút** khi SLO queue là 2 phút. | Cao. | Worker backlog, throttles, lỗi consumer. |
| DynamoDB/Kinesis IteratorAge | Tăng liên tục vượt ngưỡng xử lý cho phép. | Cao. | Shard, consumer retries, batch. |
| Monthly cost forecast | Dự báo vượt ngân sách. | Tài chính/vận hành. | Growth, retries, logs, provisioned capacity. |

**Các ngưỡng chỉ để minh họa.** Với function chạy vài lần/ngày, Error Rate có thể nhảy 100% khi chỉ có một lỗi; alarm cần điều kiện **minimum sample count**, metric math phù hợp hoặc kết hợp với số Errors tuyệt đối.

### 10.2. Alarm chưa phải chiến lược xử lý sự cố

Một alarm tốt có:

1. **Owner:** nhóm chịu trách nhiệm, kênh nhận cảnh báo.
2. **Tác động:** người dùng/hệ thống bị ảnh hưởng.
3. **Runbook:** lệnh/console/metrics cần xem và đường rollback an toàn.
4. **Severity:** phân biệt cảnh báo kiểm tra với sự cố cần phản ứng ngay.
5. **Missing data handling:** phù hợp với workload có hoặc không có traffic.
6. **Rà soát:** hiệu chỉnh sau incident để giảm false positives.

AWS Budgets và Cost Anomaly Detection giúp cảnh báo chi phí; **budget alert không mặc nhiên là hard spend cap** cấm AWS tạo thêm chi phí. Nếu yêu cầu giới hạn nghiêm ngặt, phải thiết kế quota, IAM, concurrency và cleanup procedures phù hợp.

## 11. Quan sát Lambda Java: ví dụ handler và log tương quan

Module học về AWS và ứng dụng Java, nên ví dụ sau dùng **AWS Lambda Java runtime** với interface **RequestHandler** của thư viện **aws-lambda-java-core**.

### 11.1. Java handler minh họa

~~~java
package com.example.lambda;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;
import java.util.Map;

public class InvoiceHandler
        implements RequestHandler<Map<String, Object>, Map<String, Object>> {

    @Override
    public Map<String, Object> handleRequest(
            Map<String, Object> event, Context context) {

        String requestId = context.getAwsRequestId();
        long started = System.nanoTime();

        try {
            Object value = (event == null) ? null : event.get("invoiceId");
            if (!(value instanceof String invoiceId) || invoiceId.isBlank()) {
                throw new IllegalArgumentException("invoiceId is required");
            }

            // Không ghi toàn bộ payload hoặc dữ liệu nhạy cảm vào log.
            context.getLogger().log(
                "operation=invoice.validate status=started requestId=" + requestId
            );

            // TODO: Tách xử lý nghiệp vụ thật ra service idempotent.
            // TODO: Dùng AWS SDK client tái sử dụng, timeout và retry phù hợp.
            context.getLogger().log(
                "operation=invoice.validate status=completed requestId=" + requestId
            );

            return Map.of("status", "accepted");
        } catch (RuntimeException ex) {
            context.getLogger().log(
                "operation=invoice.validate status=failed requestId=" + requestId
                    + " errorType=" + ex.getClass().getSimpleName()
            );
            throw ex; // Để Lambda Errors phản ánh invocation thất bại.
        } finally {
            long durationMs =
                (System.nanoTime() - started) / 1_000_000L;
            context.getLogger().log(
                "operation=invoice.validate elapsedMs=" + durationMs
                    + " requestId=" + requestId
            );
        }
    }
}
~~~

**Lưu ý:** Đây là ví dụ minh họa observability, **không phải production-ready invoice processor**. Để thực sự dùng trong project, cần khai báo phiên bản phù hợp của **aws-lambda-java-core**, build JAR/ZIP đúng Lambda handler, unit tests, cấu hình IAM, input validation và thiết kế idempotency.

Mã:

- Dùng **Context.getAwsRequestId()** để tương quan.
- Không log nguyên event có thể chứa thông tin khách hàng.
- Ném lại lỗi runtime để metric **Errors** phản ánh thực thi thất bại.
- Đo **thời gian nội bộ của method** để hỗ trợ debug; nó **không thay** CloudWatch Duration/Billed Duration.
- Khi dùng structured JSON logging, chọn LambdaLogger/Log4j2 và LoggingConfig tương thích, không giả định chuỗi key=value trở thành JSON chỉ vì Lambda có log group.

### 11.2. Bảo vệ log trước injection và high cardinality

Nếu cần log business identifier, tránh chèn thẳng chuỗi người dùng không kiểm soát vào dòng log; có thể chứa newline hoặc ký tự đặc biệt gây nhiễu truy vấn. Dùng structured logger và encode/sanitize, đồng thời xác định identifier nào được phép ghi theo privacy policy.

Đừng thêm **invoiceId** thành CloudWatch metric dimension. Tỷ lệ invocation lỗi theo môi trường/phiên bản/service là metric tốt; các ID cụ thể nên được tra cứu bằng **log/tracing** có bảo vệ quyền truy cập.

### 11.3. Custom business metric với Embedded Metric Format

Ví dụ một EMF log event thể hiện hai metrics:

~~~json
{
  "_aws": {
    "Timestamp": 1795144500000,
    "CloudWatchMetrics": [
      {
        "Namespace": "Shop/Invoices",
        "Dimensions": [["Service", "Environment"]],
        "Metrics": [
          {"Name": "InvoicesCompleted", "Unit": "Count"},
          {"Name": "ProcessingLatency", "Unit": "Milliseconds"}
        ]
      }
    ]
  },
  "Service": "invoice-worker",
  "Environment": "prod",
  "InvoicesCompleted": 1,
  "ProcessingLatency": 186
}
~~~

CloudWatch EMF cho phép trích xuất custom metrics từ logs theo schema hợp lệ. **Timestamp** trong ví dụ chỉ để minh họa, không đại diện thời điểm thực. EMF có thể có thêm phí log ingest và custom metrics; không tạo một metric time series mới cho từng invoice ID.

Với Java production, cân nhắc **Powertools for AWS Lambda Java Metrics** để chuẩn hóa việc phát EMF, tránh tự viết parser/format cho mọi handler.

## 12. Mô hình chi phí Lambda Event Functions

Với **Lambda Event Functions chạy on-demand**, các thành phần chi phí cốt lõi là:

1. **Request charges:** tính theo số invocations/request units đủ điều kiện theo bảng giá. Với một số async events có payload lớn, quy tắc tính request units phụ thuộc kích thước event.
2. **Compute duration:** dựa trên **memory configured**, **billed duration**, architecture và đơn giá **GB-second** áp dụng theo Region/usage tier.
3. **Provisioned Concurrency:** phí duy trì capacity khởi tạo sẵn và những cấu phần compute/request theo pricing riêng nếu sử dụng.
4. **Ephemeral storage bổ sung:** khi cấp lớn hơn phần dung lượng /tmp miễn phí theo mô hình tiêu chuẩn.
5. **Tính năng bổ sung:** SnapStart có quy tắc phí/giới hạn khác nhau theo runtime, ngoài ra còn tenant isolation hoặc những chế độ Lambda đặc thù khi dùng.
6. **Dịch vụ tích hợp:** CloudWatch Logs/metrics/queries, X-Ray, API Gateway, SQS, EventBridge, S3, RDS, KMS, NAT, data transfer và lưu trữ liên quan.

**Quan trọng:** AWS có nhiều hình thức Lambda compute với cách tính tiền khác nhau theo tài liệu hiện hành. Không áp dụng công thức dưới đây cho **Lambda Managed Instances, MicroVMs, Web Functions hoặc những chế độ đặc thù** mà chưa đối chiếu bảng giá của chúng.

### 12.1. Công thức ước tính GB-seconds

Với on-demand Event Function, bỏ qua các ngoại lệ/discounts:

\[
\text{GB-seconds}
=
N_{\text{invocations}}
\times
\frac{\text{memory configured (MB)}}{1024}
\times
\text{billed duration (seconds)}
\]

Và:

\[
\text{Compute charge}
\approx
\text{GB-seconds}\times\text{Price per GB-second}
\]

Tổng chi phí ước tính:

\[
C_{\text{total}}
\approx C_{\text{requests}}
+C_{\text{compute}}
+C_{\text{provisioned}}
+C_{\text{extra tmp}}
+C_{\text{observability}}
+C_{\text{downstream/network}}
\]

Trong tính toán thật, cần áp dụng **AWS Free Tier, region, architecture, pricing tiers, credits, Savings Plans, time/rounding, provisioned concurrency rules** và các khoản phí khác theo bảng giá hiện hành. Công thức này dùng để so sánh hướng tối ưu, không thay hóa đơn AWS.

### 12.2. Ví dụ so sánh ba cấu hình memory

Giả sử mỗi tháng Lambda xử lý **1.000.000 invocations** và các phép đo trong một thí nghiệm cho thấy:

| Cấu hình | Memory | Billed duration trung bình | GB-s cho 1 triệu invocations |
| --- | ---: | ---: | ---: |
| A | 512 MB | 400 ms | **200.000 GB-s** |
| B | 1.024 MB | 190 ms | **190.000 GB-s** |
| C | 2.048 MB | 120 ms | **240.000 GB-s** |

Cách tính:

- A: 1.000.000 × 0,5 GB × 0,4 s = **200.000 GB-s**.
- B: 1.000.000 × 1 GB × 0,19 s = **190.000 GB-s**.
- C: 1.000.000 × 2 GB × 0,12 s = **240.000 GB-s**.

Cấu hình B nhanh hơn A và, theo **GB-seconds**, còn dùng ít compute hơn A. Cấu hình C nhanh nhất nhưng tiêu thụ nhiều GB-seconds hơn B. Do đó tăng memory **không luôn đắt hơn**, giảm memory **không luôn tiết kiệm**.

Đây là số liệu **giả định** cho bài học, không phải benchmark của AWS. Với workload thật, phải lấy **Billed Duration** chứ không chỉ Duration và chạy đủ samples ở cùng traffic/data shape, cold-start mix và architecture.

### 12.3. Request charges có thể khác “số event nghiệp vụ”

Một message chứa 100 công việc nghiệp vụ có thể được xử lý trong một invocation theo batch, hoặc một công việc có thể bị retry nhiều lần và tạo thêm invocations. Không suy thẳng:

~~~text
1 đơn hàng = 1 AWS Lambda request = 1 lần bị tính phí
~~~

Tùy nguồn:

- **API đồng bộ:** một HTTP request thường có thể dẫn tới một invocation, nhưng retry, authorizer và các functions khác có thể làm tổng lớn hơn.
- **Async events:** số request units có thể phụ thuộc payload size và retries.
- **SQS event source mapping:** một invocation có thể chứa một batch nhiều SQS messages.
- **Fan-out:** một event nguồn kích hoạt ba functions là ba luồng compute riêng, không phải một request.

Vì vậy KPI tài chính nên đo **cost per successful business outcome**, ví dụ chi phí trên 1.000 ảnh được xử lý thành công.

### 12.4. Free Tier và credits

AWS Lambda Event Functions có Free Tier được AWS công bố, chẳng hạn các định mức request và GB-seconds hàng tháng theo chính sách hiện hành. Nhưng:

- Free Tier có phạm vi/điều kiện và có thể chia sẻ tổng usage theo account/organization theo quy định.
- Không được mặc định mọi compute mode, provisioned concurrency hoặc add-on đều được miễn phí như on-demand.
- Đơn giá và chính sách có thể thay đổi theo Region, architecture, thời điểm, account và chương trình credits.

Trong thực tế, sử dụng **AWS Pricing Calculator** cùng **AWS Cost Explorer / Cost and Usage Report (CUR)** để đối chiếu thay vì hard-code một mức USD/triệu requests cho mọi nơi.

## 13. Tối ưu memory, CPU và duration

### 13.1. Memory đồng thời điều khiển CPU

Lambda cấp **CPU power tỷ lệ với memory configured** trong phạm vi dịch vụ hỗ trợ. Cấu hình memory không chỉ tác động đến lượng RAM mà còn tác động tới tốc độ tính toán.

Ví dụ một Java function:

- 128 MB: JVM có thể khởi động chậm, code CPU-bound chạy lâu hoặc OOM.
- 512 MB: đủ RAM và được cấp nhiều CPU hơn, Duration có thể giảm.
- 1.024 MB hoặc cao hơn: Duration có thể tiếp tục giảm, nhưng lợi ích biên cần được đo.
- Quá cao: memory tăng nhưng thời gian chạy gần như không giảm vì bị chặn ở database/network, nên GB-seconds tăng.

Hãy chọn memory theo **cost-performance frontier**, không đơn giản chọn mức tối thiểu.

### 13.2. Thí nghiệm memory tuning

Đề xuất quy trình:

1. Chọn cùng **application version**, handler logic và dataset đại diện.
2. Đo ở những cấu hình memory như **256, 512, 1.024, 2.048 MB** mà workload có thể chạy.
3. Với mỗi cấu hình, gửi lượng request tương đương, phân biệt cold/warm invocation khi có thể.
4. Thu thập **Billed Duration, Duration p50/p95/p99, Max Memory Used, error rate, concurrency**.
5. Tính **GB-seconds**, estimate request/compute costs, đưa vào bảng.
6. Chọn cấu hình thỏa **SLO latency và độ ổn định**, rồi tối thiểu hóa chi phí trong tập hợp hợp lệ.
7. Thử lại khi Java/runtime/library, ARM architecture hoặc workload shape thay đổi.

Công cụ **AWS Lambda Power Tuning** dùng Step Functions để chạy các phép thử nhiều mức memory; cần lưu ý nó **thực sự invoke function** và có thể gây side effects/cost. Không sử dụng tool này trên handler có giao dịch không idempotent nếu chưa chuẩn bị dữ liệu và sandbox thích hợp.

### 13.3. Tối ưu Java initialization và SDK calls

Một số cơ hội trong Java Lambda:

- **Khởi tạo AWS SDK client một lần** bên ngoài handler để tận dụng warm execution environment.
- Đặt **HTTP connect/read timeouts** và retry/backoff hợp lý để không chiếm duration quá lâu do downstream lỗi.
- Dùng dependency injection và framework initialization vừa đủ; loại bỏ modules không cần.
- Tránh tải một lượng lớn configuration/models từ S3 ở mỗi invocation nếu có thể cache an toàn.
- Tối ưu JSON serialization, network calls lặp, DNS resolution và kết nối database.
- Giảm số AWS API calls không cần, vì mỗi API call vừa mất latency vừa có thể phát sinh service charges.
- Kiểm soát connection keep-alive, credential refresh và expiry để reused environment không giữ stale connection/secret mãi mãi.

**Cache chỉ là tối ưu, không phải kho dữ liệu bền.** Execution environment có thể bị loại bất kỳ lúc nào; code phải đọc lại dữ liệu khi cache mất hoặc đã quá hạn.

### 13.4. Timeout là ranh giới latency, không phải tuning duy nhất

Đặt Timeout quá ngắn sẽ làm tăng **Errors** vì tác vụ bị cắt ngang. Đặt quá dài có thể làm một invocation treo vì dependency lỗi và tiếp tục chịu chi phí trong thời gian dài.

Một cách thiết kế:

- Dựa trên p99 của các thao tác nghiệp vụ hợp lệ cộng headroom có chủ đích.
- Đặt timeout riêng cho HTTP calls, SDK calls, database queries **nhỏ hơn Lambda Timeout** để handler còn thời gian xử lý lỗi/cleanup.
- Với SQS worker, xem mối quan hệ giữa Lambda timeout, **SQS visibility timeout** và retry.
- Với API phục vụ người dùng, timeout toàn chuỗi còn bị giới hạn bởi **API Gateway/ALB/client timeout**, không thể kéo dài tùy ý.

Không thay đổi timeout liên tục nếu chưa điều tra nguyên nhân latency.

## 14. Cold starts, SnapStart và Provisioned Concurrency

### 14.1. Phân tích cold start một cách có kiểm chứng

Một request chậm có thể do:

- INIT runtime Java, classloading, dependency initialization.
- VPC/network preparation hoặc kết nối tới dependency.
- Handler CPU-bound hoặc thiếu memory.
- API Gateway/ALB/request path.
- RDS query/lock hoặc external API chậm.
- Extension, instrumentation hoặc logging overhead.

Nếu duration handler thấp nhưng end-to-end p95/p99 cao, xem **Init Duration**, X-Ray trace, proxy/API metrics và SDK spans trước khi quyết định mua Provisioned Concurrency.

### 14.2. AWS Lambda SnapStart

**SnapStart** có thể tối ưu phần initialization bằng cách khởi tạo function khi publish version, lưu một snapshot của môi trường đã khởi tạo và phục hồi snapshot để giảm startup latency. Tính năng hỗ trợ tùy runtime, deployment package, Region và giới hạn được AWS công bố.

Đối với Java:

- Có hỗ trợ cho những **Java managed runtimes được chỉ định** theo điều kiện dịch vụ.
- Chỉ dùng trên **published versions/aliases** phù hợp, không dùng cho **$LATEST** theo mô hình SnapStart.
- Snapshot có thể chứa state được tạo lúc INIT; phải bảo đảm **uniqueness**, PRNG, temporary credentials, connection state, timestamp và external connections được xử lý lại an toàn sau restore.
- Không mặc định **mọi layer, EFS, /tmp tăng lớn, architecture hoặc container image** đều tương thích; kiểm tra tài liệu tính năng đúng thời điểm.

Với các runtime/kiểu package được AWS hỗ trợ, SnapStart có thể giúp giảm cold starts mà không cần giữ nhiều execution environments sẵn như Provisioned Concurrency.

### 14.3. Giá và giới hạn SnapStart

Theo tài liệu AWS, quy tắc **SnapStart pricing** khác nhau theo runtime; đặc biệt Java managed runtimes có những điều kiện về chi phí bổ sung khác các runtime khác. Không coi SnapStart luôn miễn phí với mọi runtime hoặc đồng nghĩa cấu hình Provisioned Concurrency.

Các giới hạn đáng nhớ theo tính năng đã được công bố:

- Không dùng **SnapStart đồng thời với Provisioned Concurrency** trên cùng function version.
- Không hỗ trợ **EFS** hoặc cấu hình **ephemeral storage lớn hơn 512 MB** trong những cấu hình SnapStart theo giới hạn dịch vụ được công bố.
- Có tính năng khác nhau cho runtime ZIP/container image; phải đọc đúng tài liệu platform hiện hành.
- Phải thiết kế và test **before-checkpoint/after-restore hooks** nếu ứng dụng cần sửa state sau khi được restore.

**Không sử dụng snapshot như một nơi lưu session/user state giữa các invocations.**

### 14.4. Khi nào Provisioned Concurrency hợp lý?

Một API Java có SLO p99 rất thấp và traffic dự báo trước có thể hưởng lợi từ provisioned concurrency:

1. Xác nhận cold start là nguyên nhân tail latency.
2. Tính provisioned capacity theo concurrent demand và utilization thực tế.
3. Sử dụng **alias/version** tách staging/production.
4. Đặt lịch hoặc auto scaling cho provisioned concurrency theo khả năng hỗ trợ.
5. Đo p99 end-to-end, **ProvisionedConcurrencyUtilization**, **SpilloverInvocations** và cost.
6. Giảm capacity idle ngoài giờ nếu vẫn đáp ứng SLA.

Với batch ETL/async worker không nhạy vài trăm millisecond cold start, Provisioned Concurrency thường khó biện minh về chi phí hơn.

## 15. Ephemeral storage, network và chi phí phụ trợ

### 15.1. /tmp của Lambda

Lambda cung cấp không gian **/tmp** cho dữ liệu tạm trong execution environment, được mã hóa at rest theo dịch vụ. Ở Event Functions tiêu chuẩn, có thể cấu hình ephemeral storage trong khoảng **512 MB đến 10.240 MB** theo quota/cấu hình hỗ trợ.

Tình huống sử dụng:

- Tải ảnh lớn từ S3 để xử lý.
- Giải nén file tạm cho ETL.
- Tải machine learning model/data phụ trợ trong thời gian invocation.
- Tạo PDF/video hoặc xuất kết quả rồi upload lại S3.

**Không dùng /tmp để lưu dữ liệu bền vững** hoặc kỳ vọng hai execution environments dùng chung file. Khi environment biến mất, dữ liệu tạm không được bảo đảm tồn tại.

### 15.2. Tính phí phần /tmp bổ sung

Phần ephemeral storage **vượt 512 MB** có thể bị tính phí theo GB-second của dung lượng bổ sung và thời gian sử dụng theo quy định hiện hành.

Ví dụ function được cấu hình /tmp **2.048 MB**:

- Baseline: 512 MB.
- Phần bổ sung: **1.536 MB** = **1,5 GB**.
- Nếu billed duration là 2 giây theo điều kiện tính phí tương ứng, lượng extra storage usage minh họa là **3 GB-seconds** cho invocation.

Không đồng nhất lượng **file thực sự chiếm /tmp** với dung lượng storage đã cấu hình để tính phí.

### 15.3. VPC và NAT Gateway

Lambda trong VPC có thể cần giao tiếp với database riêng trong private subnet. Nhưng khi kết nối ra các dịch vụ khác, cần thiết kế network path:

- AWS SDK tới **S3/DynamoDB/CloudWatch/Secrets Manager** có thể cần VPC endpoints hoặc NAT theo kiến trúc.
- NAT Gateway có phí theo giờ và data processing; một workload Lambda có thể tạo chi phí NAT đáng kể dù Lambda compute rẻ.
- VPC interface endpoints có hourly/data processing cost tùy dịch vụ/Region; không mặc định miễn phí.
- Xem security group egress, subnet route, DNS resolution, KMS/secret access và destination timeout.

Không kết luận Lambda chạy trong VPC sẽ **mặc định có Internet egress** chỉ vì subnet nằm trong VPC.

### 15.4. S3, RDS, API Gateway và dữ liệu truyền

Một function được gọi 1 triệu lần có thể:

- Đọc 1 triệu object S3, ghi 1 triệu output objects.
- Ghi log nhiều lần.
- Thực hiện 1 triệu DynamoDB transactions.
- Mở/đóng lượng lớn DB connections.
- Gửi request qua NAT tới external APIs.

Tổng phí những service này có thể **lớn hơn Lambda compute charges**. Tối ưu phải đánh giá **whole pipeline TCO**, không chỉ giảm Billed Duration.

### 15.5. CloudWatch Logs, X-Ray và extension overhead

Nếu function phát 10 KB log mỗi invocation và có 5 triệu invocations/tháng, dữ liệu ingest thô gần **50 GB** trước overhead/retention. Việc bật DEBUG toàn bộ nội dung payload có thể khiến log cost tăng rất mạnh và lộ thông tin nhạy cảm.

Cách kiểm soát:

- Dùng **structured logging**, log ngắn, theo severity.
- Không log event payload lớn hoặc binary content.
- Chỉ ghi stack trace đầy đủ khi thực sự lỗi, tránh duplicate ở nhiều layers.
- Đặt CloudWatch Logs retention đúng mục tiêu.
- Giới hạn Logs Insights query phạm vi thời gian/log group.
- Bật X-Ray sampling/Insights theo nhu cầu quan sát.
- Đo extension overhead và tắt extensions không dùng.

**Không tắt hoàn toàn error logs/alarms để tiết kiệm** vì khi sự cố xảy ra, chi phí khôi phục hoặc mất dữ liệu có thể lớn hơn số tiền logs tiết kiệm được.

## 16. Tối ưu event flow để vừa giảm phí vừa tăng độ bền vững

### 16.1. Loại bỏ event không cần trước khi invoke

Nếu mỗi object upload tới S3 đều kích hoạt Lambda nhưng 80% không cần xử lý:

- Dùng S3 Event Notifications **prefix/suffix filters** hợp lệ.
- Hoặc dùng EventBridge event patterns khi cần lọc phong phú hơn.
- Với SQS/Kinesis/DynamoDB event source mapping, có thể dùng **event filtering** theo khả năng nguồn và schema hỗ trợ.

Filter trước invocation có thể giảm **Invocations, compute, logs và downstream calls**. Nhưng filter sai làm bỏ qua nghiệp vụ, cần test với tập event mẫu và quan sát các metrics như **FilteredOutEventCount** khi được bật.

### 16.2. Batch size: giảm invocations không phải lúc nào cũng giảm tổng chi phí

Ví dụ SQS có **10.000 messages**:

| Batch | Số Lambda invocations lý thuyết | Đổi lại |
| --- | ---: | --- |
| 1 message/batch | 10.000 | Overhead invocation cao, dễ kiểm soát lỗi từng message. |
| 10 messages/batch | 1.000 | Giảm request overhead, nhưng một lỗi có thể khiến batch retry. |
| 100 messages/batch | 100 | Ít invocations, có thể tăng duration/memory, timeout, replay impact. |

Bảng là **ước tính lý tưởng**; batching window, payload sizes, available messages và retry có thể tạo số invocations khác. Với SQS, còn quota batch size và invocation payload limits theo nguồn.

**Giảm Lambda Invocations** có lợi, nhưng nếu batch lớn làm tăng retries, duplicate processing hoặc giữ message quá lâu, phí và độ trễ end-to-end có thể tăng.

### 16.3. Partial batch response cho SQS

Khi Lambda nhận batch gồm messages A, B, C; A/C xử lý thành công nhưng B lỗi, dùng **ReportBatchItemFailures** theo event source mapping phù hợp để chỉ yêu cầu retry B.

Response minh họa:

~~~json
{
  "batchItemFailures": [
    {
      "itemIdentifier": "message-B-id"
    }
  ]
}
~~~

Không phải response dành cho Lambda được S3 trực tiếp invoke. Với queue FIFO, cần tuân thủ yêu cầu preserving order và trả messages chưa xử lý nếu gặp lỗi giữa chừng.

Để kiểm soát chi phí retry:

- Thiết kế handler **idempotent**.
- Đặt **SQS visibility timeout** đủ cho thời gian xử lý/batch/retry.
- Sử dụng DLQ và cảnh báo để tách poison messages.
- Phân biệt lỗi tạm thời (network throttle) và lỗi vĩnh viễn (input schema invalid).
- Không retry vô hạn ở cả **SDK, function logic, SQS và caller** cùng lúc.

### 16.4. Giảm truy cập downstream dư thừa

Một tối ưu có thể lớn hơn giảm memory:

- Gộp SDK calls thành batch APIs khi được hỗ trợ.
- Cache metadata an toàn giữa warm invocations hoặc trong một invocation.
- Tránh lặp **HeadObject** trước **GetObject** nếu không cần thông tin precondition.
- Dùng DynamoDB conditional writes/idempotency keys thay cho query+write dễ race.
- Đánh giá S3 multipart/byte-range reads cho object lớn, không tải toàn bộ khi chỉ cần một phần.
- Chọn đúng Region cho function và data store để giảm latency/cross-Region cost.

**Không hy sinh tính đúng đắn chỉ để giảm số lời gọi**; bulk/batch phải giữ error handling và transaction requirements.

## 17. Phân tích chi phí bằng Cost Explorer, CUR và tagging

### 17.1. Vì sao metrics chưa phải hóa đơn?

CloudWatch **Invocations × Billed Duration × configured memory** giúp ước tính compute usage, nhưng billing thực tế có thể bị ảnh hưởng bởi:

- Architecture **x86_64 / arm64** và pricing tier.
- Free Tier/credits và account/organization billing.
- Provisioned Concurrency cùng những tính năng bổ sung.
- Async request billing rules theo payload size.
- Thời điểm usage được ghi nhận và rounding.
- Data transfer, NAT, log ingestion, X-Ray, KMS, API Gateway và storage.

Không dựng dashboard chi phí “chính xác đến xu” chỉ từ metric Duration.

### 17.2. Các công cụ

| Công cụ | Dùng khi | Lưu ý |
| --- | --- | --- |
| **AWS Cost Explorer** | Xem chi phí theo service, usage type, Region, thời gian, tags khi kích hoạt. | Dữ liệu tổng hợp có độ trễ; không phải real-time alert cho từng invoke. |
| **Cost and Usage Report (CUR) / Data Exports** | Cần phân tích usage/cost sâu, kết hợp SQL/Athena/BI. | Cần lưu trữ, kiểm soát quyền và chi phí query. |
| **AWS Budgets** | Theo dõi budget thực tế/dự báo, gửi cảnh báo. | Alert không mặc định giới hạn cứng mức chi. |
| **Cost Anomaly Detection** | Phát hiện mức tăng khác thường. | Không thay định nghĩa baseline/SLO và phân tích nguyên nhân. |
| **AWS Pricing Calculator** | Ước tính trước khi triển khai/chuyển architecture. | Dựa trên assumptions, cần cập nhật bằng usage thực tế. |
| **CloudWatch metrics/logs** | Nhìn tác nhân kỹ thuật gây tăng chi phí. | Không hiển thị chính xác toàn bộ phí hay credits. |

### 17.3. Tagging và cost allocation

Gợi ý tags ở các resources liên quan:

~~~text
Application = invoice-platform
Environment = prod
Team        = payments
CostCenter  = backend-services
Owner       = platform-team
~~~

Kích hoạt cost allocation tags theo quy định AWS trước khi kỳ vọng Cost Explorer/CUR nhóm được chi phí theo tag. Không phải mọi phí Lambda/CloudWatch/NAT đều có thể phân bổ chính xác cho từng function chỉ bằng một tag; đôi lúc cần **allocation model** dựa trên logs/metrics/usage types.

### 17.4. Cost per successful outcome

Ví dụ một tháng:

- Lambda compute + request: giả định 30 đơn vị tiền.
- API Gateway + SQS/S3 + Logs + KMS + NAT: giả định 70 đơn vị.
- Xử lý thành công **100.000 hóa đơn**.

Chi phí mỗi 1.000 hóa đơn thành công:

\[
\frac{30+70}{100000}\times1000
=1\text{ đơn vị tiền}
\]

Nếu 10.000 hóa đơn bị lỗi và retry 4 lần, tổng invocation có thể tăng trong khi số hóa đơn thành công không tăng. **KPI cost per successful outcome** sẽ cho thấy độ kém hiệu quả rõ hơn chỉ số giá mỗi invocation.

Số liệu trong ví dụ **không phải đơn giá AWS**. Khi tính thật, cần xác định đúng services, tỷ giá, discounts, overhead và cách phân bổ chi phí dùng chung.

## 18. Bảo mật observability và phân quyền

### 18.1. Execution role không phải role của người xem logs

| Principal | Quyền cần thiết điển hình | Không nên cấp rộng |
| --- | --- | --- |
| **Lambda execution role** | Ghi logs, gọi S3/DynamoDB/KMS theo nghiệp vụ, gửi X-Ray traces khi bật. | AdministratorAccess hoặc truy cập tất cả buckets. |
| **Developer read-only** | Xem function config, CloudWatch metrics/logs và traces của ứng dụng được giao. | UpdateFunctionCode/Configuration hoặc quyền đọc secret. |
| **Deployment role** | Cập nhật function, alias, version, event source mapping qua IaC. | IAM wildcard trên toàn account nếu có thể giới hạn. |
| **Finance/FinOps** | Cost Explorer/CUR và usage reports theo chính sách. | Quyền thay đổi network, production resources. |
| **Security/Audit** | CloudTrail, log retention policy, encryption, access reviews. | Quyền chỉnh sửa logs không kiểm soát. |

Execution role cho phép code chạy trong Lambda **truy cập AWS services**. Không được đánh đồng role đó với quyền của nhà phát triển quan sát CloudWatch hoặc người có quyền deploy function.

### 18.2. PII, secrets và dữ liệu nhạy cảm

Sai lầm phổ biến là dùng debug print để ghi:

- Full request body chứa địa chỉ, CCCD, thẻ thanh toán.
- Authorization/JWT và API tokens.
- Database connection strings có password.
- Secrets Manager/SSM Parameter Store responses.
- Nội dung S3 object khách hàng.

Những dữ liệu này có thể đi tới CloudWatch Logs, log subscriptions, archive, security tools và nhiều systems khác, làm mở rộng phạm vi truy cập và rủi ro dữ liệu.

Nên:

1. Có **log schema và data classification**.
2. Chỉ log trường tối thiểu cần điều tra.
3. Mask/pseudonymize identifiers theo policy.
4. Thiết lập IAM/KMS và retention phù hợp.
5. Review metric dimensions để không rò rỉ user IDs qua metric names.
6. Có audit việc đọc logs/traces/billing data trong phạm vi tổ chức.

### 18.3. Quyền và network ảnh hưởng cost

Nếu một Lambda nằm trong VPC để truy cập RDS, VPC endpoints/NAT có thể vừa là yêu cầu network vừa là khoản phí. Không cấp mạng đi toàn Internet cho mọi function chỉ để giải quyết timeout; xác định endpoint nào cần đến và đặt egress rules, routes/SG/KMS phù hợp.

Nếu Lambda bị trigger theo vòng lặp, event source có thể gây **hóa đơn lớn và data corruption** dù function có IAM permissions hợp lệ. Dùng prefix filter, idempotency, reserved concurrency guards, alarm/throttles và vận hành cut-off có kiểm soát.

## 19. AWS CLI chỉ đọc: kiểm tra Lambda và CloudWatch

Các lệnh sau **không tạo, deploy, invoke, sửa hoặc xóa tài nguyên**. Dùng profile có quyền đọc, thay tên function/Region/ARN bằng tài nguyên lab được phép truy cập. Tránh chạy các lệnh update-function-configuration, put-function-concurrency hay put-log-events trong bài này.

### 19.1. Xác định tài khoản/Region

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

Cần chọn đúng account và Region trước khi so sánh CloudWatch metrics với billing; Lambda functions là tài nguyên theo Region.

### 19.2. Liệt kê và xem cấu hình function

~~~bash
aws lambda list-functions \
  --region ap-southeast-1 \
  --query "Functions[].{Name:FunctionName,Runtime:Runtime,MemoryMB:MemorySize,Timeout:Timeout,Updated:LastModified}"

aws lambda get-function-configuration \
  --function-name invoice-worker \
  --region ap-southeast-1 \
  --query "{Name:FunctionName,Runtime:Runtime,MemoryMB:MemorySize,TimeoutSec:Timeout,EphemeralMB:EphemeralStorage.Size,Architecture:Architectures,Tracing:TracingConfig,Logging:LoggingConfig,Role:Role,State:State}"
~~~

Khi điều tra chi phí/performance, cần xem **MemorySize, Timeout, EphemeralStorage, Architectures, Layers, VpcConfig, TracingConfig, LoggingConfig** và version/alias đang nhận traffic.

### 19.3. Kiểm tra concurrency

~~~bash
# Reserved concurrency của function (nếu có).
aws lambda get-function-concurrency \
  --function-name invoice-worker \
  --region ap-southeast-1

# Provisioned concurrency theo các aliases/versions.
aws lambda list-provisioned-concurrency-configs \
  --function-name invoice-worker \
  --region ap-southeast-1

# Quota/usage account Lambda tại Region.
aws lambda get-account-settings \
  --region ap-southeast-1
~~~

Nếu function không có reserved concurrency, get-function-concurrency có thể trả về object không có số reserved; không hiểu “không có setting” thành reserved = 0. Reserved = 0 là cấu hình chủ động rất khác.

### 19.4. Kiểm tra invocation configuration và event source mappings

~~~bash
# Dành cho async invoke configurations nếu đã có.
aws lambda get-function-event-invoke-config \
  --function-name invoice-worker \
  --region ap-southeast-1

# Xem triggers được poll thông qua event source mappings.
aws lambda list-event-source-mappings \
  --function-name invoice-worker \
  --region ap-southeast-1
~~~

Nếu function không có async configuration hoặc ESM, lệnh có thể trả không có config hoặc error tương ứng; cần phân biệt vì trigger **S3/SNS/EventBridge** trực tiếp thường không xuất hiện trong **list-event-source-mappings**.

Event source mapping cho SQS cần xem **BatchSize, MaximumBatchingWindowInSeconds, FunctionResponseTypes, ScalingConfig, State, FilterCriteria** và metrics config khi áp dụng.

### 19.5. CloudWatch: thống kê Invocations và Errors

~~~bash
# Ví dụ cửa sổ lịch sử cố định UTC, thay bằng khoảng cần điều tra.
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=invoice-worker \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --region ap-southeast-1

aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=invoice-worker \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --region ap-southeast-1
~~~

Lưu ý:

- **Sum** cho Invocations/Errors là số lượng, không phải error-rate.
- Kết quả CLI không nhất thiết được sắp theo thời gian; cần sort khi phân tích.
- Time window ở đây chỉ minh họa cho **19/11/2026 đến 20/11/2026 UTC**; dùng khoảng phù hợp sự cố.
- Nếu không có data points, kiểm tra account/Region, FunctionName, dimensions, kỳ quan sát và quyền, không kết luận function chắc chắn khỏe.

### 19.6. CloudWatch: xem p95 Duration

~~~bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=invoice-worker \
  --start-time 2026-11-19T00:00:00Z \
  --end-time 2026-11-20T00:00:00Z \
  --period 300 \
  --extended-statistics p95 \
  --region ap-southeast-1
~~~

**p95 Duration** theo từng 5 phút khác “p95 toàn bộ ngày”. Không lấy trung bình đơn giản của các p95 buckets rồi coi là p95 ngày; khi cần percentile của cả một tập mẫu, hãy lấy thống kê từ dữ liệu/histogram phù hợp.

### 19.7. CloudWatch Logs và retention

~~~bash
aws logs describe-log-groups \
  --log-group-name-prefix "/aws/lambda/invoice-worker" \
  --region ap-southeast-1

aws logs filter-log-events \
  --log-group-name "/aws/lambda/invoice-worker" \
  --filter-pattern "ERROR" \
  --limit 20 \
  --region ap-southeast-1
~~~

Filter pattern **ERROR** có thể bỏ sót JSON logs theo schema cụ thể hoặc log đã bị filter ở source; điều chỉnh theo field/severity. Khi xem log group, kiểm tra **retentionInDays**, encryption, storedBytes và log destination liên quan.

### 19.8. Xem CloudWatch alarms

~~~bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix "invoice-worker" \
  --region ap-southeast-1
~~~

Nếu alarm state = **INSUFFICIENT_DATA**, kiểm tra missing data treatment và metric availability thay vì hiểu là không có lỗi.

### 19.9. Công cụ tài chính

Trong AWS Cost Explorer:

- Chọn cùng một **time window** trước và sau tối ưu.
- Nhóm theo Service/Usage Type/Region/Cost Allocation Tags khi dữ liệu có sẵn.
- Đối chiếu **AWS Lambda**, CloudWatch, API Gateway, SQS, S3, NAT và KMS.
- Đọc cả **Amortized/Unblended/Net costs** khi tổ chức có discounts/credits theo báo cáo phù hợp.

Không cần cấp quyền thao tác production cho Finance chỉ để xem chi phí. Những khoản phí chưa được cập nhật vào Cost Explorer có thể xuất hiện muộn hơn telemetry kỹ thuật.

## 20. Runbook điều tra lỗi và tăng chi phí

### 20.1. Cây quyết định

~~~mermaid
flowchart TD
    START["SLO xấu hoặc chi phí Lambda tăng"] --> Q{"Có spike Invocations?"}
    Q -->|"Có"| A["Kiểm tra traffic source, retries, fan-out, loops"]
    Q -->|"Không"| B{"Billed Duration / Memory / Provisioned tăng?"}
    B -->|"Có"| C["So version, memory, init, SDK, DB, extensions"]
    B -->|"Không"| D["Kiểm tra Logs, X-Ray, NAT, S3, KMS, SQS và phí phụ trợ"]
    A --> E{"Errors / Throttles / EventAge tăng?"}
    E -->|"Có"| F["Phân loại async vs SQS vs synchronous, DLQ/retries"]
    E -->|"Không"| G["Xác minh số business outcomes và hành vi mới"]
    C --> H["So sánh trước/sau bằng p95 và GB-s"]
    D --> H
    F --> H
    G --> H
~~~

### 20.2. Tình huống 1 — Errors tăng sau deploy

1. Xác định **thời điểm deployment và alias/version** đang nhận traffic.
2. Xem **Errors Sum**, Duration p95, throttles, concurrency và tỷ lệ traffic.
3. Tra **requestId/logs**, tìm Runtime.ExitError, exception, timeout hoặc permission denied.
4. Dùng X-Ray để thấy dependency nào chậm khi có trace.
5. So cấu hình memory/timeout/environment variables/secrets với version trước.
6. Nếu release gây lỗi rõ ràng, dùng quy trình rollback/alias traffic shift được phê duyệt.
7. Kiểm tra data migration và event replay; rollback code không tự đảo ngược dữ liệu.

### 20.3. Tình huống 2 — Throttles tăng

1. Xem **ConcurrentExecutions Maximum** và function **reserved concurrency**.
2. Xem account concurrency quota và **ClaimedAccountConcurrency**.
3. Kiểm tra nguồn trigger và burst/retry behavior.
4. Với SQS, kiểm tra mapping max concurrency, queue age và DLQ.
5. Kiểm tra downstream capacity trước khi nâng concurrency.
6. Nếu cần tăng quota hoặc reserved concurrency, phải có kế hoạch kiểm soát budget/DB connections.

**Không chỉ tăng concurrency vì thấy throttles**; Lambda có thể đang bảo vệ một database có giới hạn kết nối.

### 20.4. Tình huống 3 — Duration tăng nhưng Errors = 0

1. So cùng metric/dimension/Region, tránh nhầm alias version.
2. Xem p95/p99 và MAX, không chỉ Average.
3. Đọc logs và traces để tìm long-running calls.
4. Xem memory, CPU, garbage collection/Java init, networking.
5. Kiểm tra dependency như RDS lock, S3 latency, external API rate limiting.
6. Nếu timeout chưa bị chạm, Errors có thể bằng 0 nhưng **người dùng vẫn chờ quá lâu**.
7. Đo API Gateway/ALB latency riêng để xác định có bottleneck ngoài handler.

### 20.5. Tình huống 4 — Async backlog tăng, event mất

1. Kiểm tra **AsyncEventsReceived**, **AsyncEventAge**, **AsyncEventsDropped**.
2. Xem Errors, Throttles, reserved concurrency và error handling config.
3. Kiểm tra destination/DLQ policies, KMS, retention và metric delivery failures.
4. Xác định event source có phát duplicate hoặc spike không.
5. Thiết kế replay từ nguồn lưu bền/failed-event destination khi có; không assume mọi event còn có thể replay.
6. Sửa poison events và idempotency; không chỉ tắt retries để làm Errors đẹp.

### 20.6. Tình huống 5 — Hóa đơn tăng dù traffic không tăng

Kiểm tra ít nhất:

| Nguồn chi phí | Bằng chứng cần tìm |
| --- | --- |
| **Memory configured tăng** | Function configurations/version history, metric Billed Duration. |
| **Duration tăng** | p95/avg/REPORT logs, SDK/DB calls. |
| **Provisioned concurrency idle** | Config provisioned pool theo alias/version, utilization thấp. |
| **Excessive logging** | CloudWatch log ingestion/storage/queries, log-level thay đổi. |
| **Retry/duplicate processing** | Invocations tăng so business transactions, SQS receive/delete, DLQ. |
| **Recursive event loop** | S3/EventBridge/SQS event fan-out, RecursiveInvocationsDropped khi có. |
| **Network/NAT** | Data transfer/NAT usage types, VPC route, S3 requests. |
| **Extra /tmp** | EphemeralStorage.Size > 512 MB. |
| **Extra tracing/Insights** | X-Ray traces/Insights layer và custom metrics/log volume. |
| **More downstream API calls** | S3/DynamoDB/KMS/API Gateway usage. |

Kết luận nên bao gồm **nguyên nhân kỹ thuật, tác động nghiệp vụ, biện pháp sửa, điều kiện rollback và xác nhận hóa đơn trong kỳ billing kế tiếp**.

## 21. Case study: pipeline xử lý ảnh S3 → SQS → Lambda

### 21.1. Yêu cầu

Một hệ thống xử lý **200.000 ảnh/ngày**, mỗi ảnh cần tạo thumbnail và ghi metadata:

- Người dùng upload ảnh lên S3.
- S3 tạo notification cho prefix **incoming/**.
- Notification đi vào **SQS Standard queue**.
- Java Lambda worker nhận message, xử lý ảnh, ghi output S3 và metadata DynamoDB.
- Mục tiêu nghiệp vụ: **99% ảnh được xử lý trong 2 phút**.
- Không xử lý trùng side effects khi S3/SQS retry.
- Chi phí phải dự báo được theo số ảnh thành công.

~~~mermaid
flowchart LR
    USER["Upload ảnh"] --> S3[("S3 incoming/")]
    S3 --> SQS["SQS Standard"]
    SQS --> L["Lambda Java worker"]
    L --> OUT[("S3 thumbnails/")]
    L --> DDB[("DynamoDB status")]
    SQS -.-> DLQ["DLQ"]
    L --> CW["CloudWatch + X-Ray"]
    CW --> OPS["SLO & cost dashboard"]
~~~

### 21.2. Bộ metrics/alarms tối thiểu

| Nhóm | Metric |
| --- | --- |
| S3/SQS đầu vào | NumberOfMessagesSent, ApproximateNumberOfMessagesVisible/NotVisible. |
| Khả năng xử lý đúng hạn | ApproximateAgeOfOldestMessage và custom **ImagesCompleted**. |
| Lỗi | Lambda Errors, DLQ depth, error type; failed-message counters. |
| Hiệu năng | Duration p95/p99, Max Memory Used từ REPORT, processing time by image size. |
| Sức chứa | ConcurrentExecutions/Throttles và event source mapping limits. |
| Chi phí | Lambda invocations/GB-s, S3 GET/PUT, SQS requests, CloudWatch logs, KMS nếu dùng. |

### 21.3. Tối ưu từng bước

1. **Filter prefix/suffix:** chỉ gửi event cho ảnh phù hợp, tránh trigger output thumbnails.
2. **Đo đúng workload:** ảnh 50 KB và 20 MB có duration khác nhau; thử theo các nhóm size.
3. **Tuning memory:** chạy benchmark 512/1.024/2.048 MB; chọn điểm đạt p95 SLA và GB-s tối ưu.
4. **Batch size:** đánh giá 1, 5, 10 SQS records/batch, cân nhắc timeout và partial batch.
5. **Idempotency:** ghi trạng thái theo S3 object key + versionId hoặc khóa nghiệp vụ; tránh thumbnail/metadata bị ghi lỗi thời.
6. **Control concurrency:** ngăn quá tải thư viện image processing, S3/DynamoDB throughput và các quota.
7. **DLQ/alarms:** cảnh báo lỗi không thể xử lý và cho phép replay sau khi sửa.
8. **Output bucket/prefix riêng:** ngăn S3 ObjectCreated loop từ thumbnail mới.
9. **Giảm log noise:** chỉ log input metadata an toàn, errorType, requestId, duration và result.
10. **Đánh giá Cost per image completed**, không chỉ tổng Lambda duration.

### 21.4. Kết quả mong đợi

Một thay đổi được xem là thành công khi **đồng thời**:

- p95/p99 xử lý giảm hoặc không vượt SLO.
- Age of oldest message và DLQ không tăng bất thường.
- Tỷ lệ kết quả đúng, không trùng vẫn đạt.
- Chi phí **trên mỗi ảnh xử lý thành công** giảm sau khi tính cả S3/SQS/Logs/KMS.
- Không sinh rủi ro bảo mật từ logging/permissions hoặc dữ liệu tạm.

Nếu tăng memory giảm mỗi invocation từ 400 xuống 190 ms nhưng bị retry nhiều lần hơn do timeouts ở API khác, tổng chi phí có thể vẫn tăng.

## 22. Case study: API Java Lambda có cold starts và spike

### 22.1. Yêu cầu

Một API Java dùng API Gateway → Lambda → RDS, traffic dao động:

- Ngày thường 10 requests/giây.
- Khi mở bán 100 requests/giây trong vài phút.
- p99 end-to-end latency cần dưới 1 giây.
- RDS có giới hạn kết nối.

### 22.2. Điều tra

1. Xem **API Gateway latency/integration latency** và Lambda Duration p95/p99.
2. Kiểm tra tỷ lệ cold starts qua Init Duration/X-Ray/Insights theo sample.
3. Ước lượng concurrency: 100 RPS × 0,4 giây ≈ **40 concurrent** trước bursts/tail.
4. Nếu database mở một connection mới cho mỗi invocation, nguy cơ DB connection storm có thể lớn hơn vấn đề cold start.
5. So ba cấu hình: memory tuning, Java SnapStart (khi tương thích), Provisioned Concurrency.
6. Đánh giá RDS Proxy, connection pooling, VPC endpoints, request timeouts và cancellation behavior.
7. So **chi phí provisioned capacity idle** với cải thiện p99 và tác động doanh thu.

### 22.3. Lựa chọn hợp lý

- Với Java runtime tương thích, SnapStart có thể là ứng viên để giảm initialization, nhưng cần kiểm tra limitations và state uniqueness.
- Provisioned Concurrency có thể phù hợp vào **giờ mở bán** nếu p99 khắt khe và cold-start optimization chưa đủ; dùng scheduled scaling và đo utilization.
- Reserved concurrency có thể giữ capacity/đặt trần bảo vệ DB, nhưng trần thấp dễ gây throttles khi spike.
- Tăng memory có thể giảm compute duration, nhưng nếu DB query chậm thì không giải quyết được toàn bộ.

**Không chọn một tính năng đắt tiền chỉ vì tên gọi.** So p99 thực, request success rate và total cost ở cùng load.

## 23. Các hiểu lầm cần tránh

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Lambda Invocations bằng số HTTP requests của hệ thống.” | Một request có thể gọi nhiều functions; batch và retry làm số invocations khác business requests. |
| “Errors = 0 nghĩa API không có HTTP 500.” | Code có thể trả statusCode=500 mà runtime không coi invocation lỗi. |
| “Duration bao gồm mọi cold start time.” | Duration metric thông thường không tính toàn bộ init; Billed Duration/REPORT có các thành phần khác. |
| “Tính tiền theo Max Memory Used.” | Compute charge dựa trên **memory configured** và billed duration. |
| “Giảm memory một nửa luôn giảm phí một nửa.” | Memory cũng điều chỉnh CPU, nên thời gian thực thi có thể tăng đáng kể. |
| “p95 Duration tương đương p95 latency người dùng.” | API Gateway/ALB/network, init và client overhead vẫn tồn tại. |
| “CloudWatch Sum(ConcurrentExecutions) là tổng requests.” | Concurrency là số invocations in-flight; xem Maximum/usage phù hợp. |
| “Không có datapoint nghĩa là hệ thống khỏe.” | Metric có thể không phát khi không có invocation/traffic hoặc cấu hình thiếu. |
| “Bật Reserved Concurrency luôn mất tiền giữ chỗ.” | Reserved concurrency không có phí riêng; Provisioned Concurrency có phí. |
| “Provisioned Concurrency và SnapStart là cùng một tính năng.” | Một bên giữ pre-initialized capacity, một bên dùng snapshot initialization và có giới hạn riêng. |
| “SnapStart hỗ trợ mọi runtime/config.” | Phụ thuộc runtime/deployment package/Region và các giới hạn như EFS, /tmp, provisioned capacity. |
| “SQS queue age bằng Lambda IteratorAge.” | IteratorAge dành cho stream sources phù hợp; SQS dùng metric queue age riêng. |
| “Một SQS message là một Lambda invocation.” | Lambda có thể batch nhiều messages trong một invocation. |
| “Retry luôn miễn phí.” | Retries có thể tăng invocations, GB-s, SQS/S3/API charges và side effects. |
| “DLQ tồn tại là tất cả lỗi đều tự phục hồi.” | Phải monitor, sửa lỗi và redrive/replay có kiểm soát. |
| “CloudWatch Logs retention ngắn không cần thiết vì Lambda tự dọn.” | Log group/retention có vòng đời riêng; cần cấu hình theo policy. |
| “Logging nhiều nhất luôn giúp debug tốt nhất.” | Log noise, PII và phí có thể tăng; cần structured logs có chọn lọc. |
| “CloudTrail mặc định lưu mọi Lambda invocation payload.” | CloudTrail control/data events có phạm vi/cấu hình riêng; không thay app logging/tracing. |
| “Cost Explorer là realtime theo từng invocation.” | Billing data tổng hợp thường có độ trễ; dùng metrics để điều tra kỹ thuật sớm. |
| “Tối ưu Lambda duration là đủ giảm tổng AWS bill.” | API Gateway, S3, SQS, NAT, KMS, CloudWatch và RDS có thể chiếm phần lớn tổng phí. |
| “Reserved concurrency 0 chỉ dừng compute không có rủi ro.” | Có thể gây throttles, async retries, event age/drop và backlog. |
| “Lambda chạy trong VPC tự có Internet.” | Cần route và NAT/VPC endpoints thích hợp; network lỗi tăng duration/timeouts. |
| “Một alert budget đặt mức 100 USD sẽ cấm tiêu vượt mức đó.” | Budget alert thường là cảnh báo, không phải hard cap mặc định. |
| “Mọi Lambda compute type có pricing giống Event Functions.” | Managed Instances/MicroVM/Web Functions và features khác có quy tắc riêng. |

## 24. Bài tập và đáp án gợi ý

### Bài tập 1 — Tính error rate

Một Lambda function có **12.000 Invocations**, **180 Errors**, **30 Throttles** trong một giờ.

**Câu hỏi:** Tính error rate của invocations và đánh giá tình trạng hệ thống.

**Lời giải:** Error rate = 180 / 12.000 × 100% = **1,5%**. **Throttles** là invocation requests bị từ chối trước khi handler được gọi nên **không tự nằm trong Invocations hay Errors**. Muốn tỷ lệ request thất bại end-to-end phải xem cả nguồn trigger/API metrics và retry.

### Bài tập 2 — Concurrency

Một function nhận **80 requests/giây**, Duration trung bình **0,25 giây**.

**Lời giải:** Concurrency trung bình xấp xỉ **20**. Cần capacity cho bursts/tail latency, quan sát Maximum ConcurrentExecutions và bảo vệ backend, không reserve đúng 20 rồi mặc định không có throttles.

### Bài tập 3 — So GB-seconds

Hai cấu hình:

- A: 512 MB, billed duration 300 ms.
- B: 1.024 MB, billed duration 120 ms.

**Lời giải cho mỗi invocation:**

- A: 0,5 × 0,3 = **0,15 GB-s**.
- B: 1 × 0,12 = **0,12 GB-s**.

B sử dụng ít GB-seconds hơn dù được cấp memory lớn hơn. Vẫn phải so p95, errors, architecture và các phí bổ sung.

### Bài tập 4 — API trả 500 nhưng Errors không tăng

**Câu hỏi:** Lambda handler bắt exception rồi trả JSON có statusCode=500. Vì sao CloudWatch Errors=0?

**Đáp án:** Lambda runtime nhận kết quả handler trả về bình thường; đây là **business/API failure** nhưng có thể không phải Lambda invocation error. Cần theo dõi API Gateway/ALB 5xx và custom business errors.

### Bài tập 5 — Worker lỗi theo batch

SQS đưa 10 messages vào Lambda. Chỉ message thứ 7 lỗi, nhưng handler ném exception cho toàn batch.

**Đáp án:** Toàn batch có thể bị xử lý lại sau visibility timeout, gây xử lý trùng 9 messages thành công. Thiết kế idempotency, bật **ReportBatchItemFailures** và xử lý errors từng record.

### Bài tập 6 — Log bill tăng bất ngờ

Một function tăng từ 100 byte log/invocation lên 20 KB log/invocation, trong khi invocation count không thay đổi.

**Đáp án:** CloudWatch log ingestion có thể tăng khoảng **200 lần** theo kích thước thô, chưa tính overhead. Rà soát log-level change, log event payload, retention, sensitive data, Logs Insights query. Tối ưu logs, không bỏ qua error/operational signals.

### Bài tập 7 — AsyncEventAge tăng

Async Lambda nhận event bình thường nhưng **AsyncEventAge p95** tăng lên vài phút, **Throttles** cũng tăng.

**Đáp án:** Có thể function/account concurrency bị giới hạn nên events chờ trong internal queue. Xem reserved/account quotas, function duration, retry, AsyncEventsDropped và dead-letter/destination; tăng concurrency chỉ sau khi kiểm tra downstream.

### Bài tập 8 — Cold start và chi phí

API Java có p99 latency cao chỉ trong giờ traffic spike, Duration handler ổn định, REPORT cho thấy Init Duration cao ở những invocations chậm.

**Đáp án:** Điều tra cold start bằng X-Ray/Insights; test Java SnapStart nếu tương thích, memory tuning và cân nhắc Provisioned Concurrency vào giờ peak. So chi phí giữ capacity với cải thiện p99, không bật provisioned 24/7 mà không tính utilization.

### Bài tập 9 — /tmp 5 GB

Một Lambda xử lý video cần lưu file tạm 3 GB.

**Đáp án:** /tmp mặc định 512 MB không đủ, có thể cấu hình ephemeral storage phù hợp trong giới hạn Lambda. Phần vượt 512 MB có thể phát sinh phí; vẫn phải kiểm tra file lifecycle, memory, timeout và kết quả upload S3 vì /tmp không bền vững.

### Bài tập 10 — Tăng concurrency làm tăng lỗi RDS

Function dùng reserved concurrency 100, gọi RDS và tổng DB connections vượt ngưỡng khi traffic tăng.

**Đáp án:** Điều chỉnh concurrency/connection pooling, xem RDS Proxy, reuse connection an toàn, giảm DB calls và đánh giá DB capacity. Tăng reserved concurrency sẽ có thể làm sự cố nặng hơn.

## 25. Câu hỏi tự kiểm tra

**Câu 1.** Hai metric Lambda nào là điểm bắt đầu để tính runtime error rate?  
**Đáp án:** **Errors** và **Invocations**, dùng Sum cùng time window và dimension phù hợp.

**Câu 2.** Vì sao không tính tỷ lệ lỗi khi Invocations = 0?  
**Đáp án:** Không có mẫu quan sát nên mẫu số bằng 0; cần xử lý như không xác định/missing data.

**Câu 3.** Khi đánh giá peak concurrency, nên dùng Sum hay Maximum?  
**Đáp án:** **Maximum** của ConcurrentExecutions theo thời gian phù hợp.

**Câu 4.** Duration p95 có gồm init cold start không?  
**Đáp án:** Duration metric thông thường không gồm cold initialization; xem REPORT/Init Duration, tracing và end-to-end latency.

**Câu 5.** Lambda tính compute charge theo memory cấu hình hay memory thực dùng?  
**Đáp án:** **Memory configured** cùng billed duration và đơn giá GB-second.

**Câu 6.** Nếu tăng memory làm duration giảm hơn một nửa, cost per invoke chắc tăng?  
**Đáp án:** Không; phải so tích **memory × billed duration**, request fees và các yếu tố bổ sung.

**Câu 7.** Reserved concurrency và Provisioned Concurrency khác gì về chi phí?  
**Đáp án:** Reserved concurrency không có phí capacity riêng; Provisioned Concurrency có chi phí duy trì environments đã init sẵn và pricing liên quan.

**Câu 8.** AsyncEventAge đo gì?  
**Đáp án:** Tuổi của event trong async queue của Lambda trước lúc invoke; tăng khi backlog/retry/throttles.

**Câu 9.** SQS worker nên xem metric queue nào để biết delay?  
**Đáp án:** **ApproximateAgeOfOldestMessage**, cùng visible/invisible counts và DLQ.

**Câu 10.** IteratorAge thường dùng với nguồn nào?  
**Đáp án:** Stream sources như DynamoDB Streams, Kinesis và DocumentDB theo hỗ trợ, không phải metric queue age của SQS.

**Câu 11.** Lambda Errors=0 có khẳng định API không trả 500?  
**Đáp án:** Không. Handler có thể trả HTTP 500 như kết quả bình thường mà không throw exception.

**Câu 12.** Có thể dùng /tmp làm nguồn dữ liệu lâu dài không?  
**Đáp án:** Không. /tmp là ephemeral storage theo execution environment, không bảo đảm tồn tại bền vững.

**Câu 13.** Vì sao logger không nên ghi access token hoặc request body?  
**Đáp án:** Dữ liệu nhạy cảm có thể được lưu/truyền tới Logs và các hệ thống downstream, tăng rủi ro rò rỉ/vi phạm chính sách.

**Câu 14.** Provisioned concurrency spillover metric cho biết gì?  
**Đáp án:** Có invocations dùng on-demand khi provisioned capacity đã được dùng hết theo mô hình hỗ trợ.

**Câu 15.** Vì sao giảm số invocations bằng batching cần kiểm thử retry?  
**Đáp án:** Batch lỗi có thể gây reprocess nhiều records, tăng duplicate/latency/cost nếu thiếu partial failure handling.

**Câu 16.** Cách tìm những event bị loại trong async invoke?  
**Đáp án:** Xem **AsyncEventsDropped**, async config, DLQ/on-failure destination, Errors/Throttles và log/replay path.

**Câu 17.** Bật Lambda Insights có thể gây chi phí gì?  
**Đáp án:** Extra metrics và performance logs, cộng overhead/chi phí CloudWatch theo usage.

**Câu 18.** Tại sao Lambda code đặt trong VPC có thể gặp network timeout?  
**Đáp án:** Thiếu route/NAT/VPC endpoint/DNS/SG path phù hợp tới dependency; VPC attachment không tự cấp Internet egress.

**Câu 19.** Khi chi phí AWS tăng, chỉ xem Lambda Pricing có đủ?  
**Đáp án:** Không; phải tính CloudWatch, S3, API Gateway, SQS, KMS, NAT, RDS, data transfer và các resources liên quan.

**Câu 20.** Chỉ số tốt hơn để so hai phương án ảnh thumbnail có số retry khác nhau?  
**Đáp án:** **Cost per successful image**, kết hợp p95 xử lý, error/retry, backlog và đúng đắn kết quả.

## 26. Tổng kết và checklist áp dụng

**Quan sát Lambda** không chỉ là nhìn Errors hoặc mở CloudWatch Logs. Một thiết kế vận hành tốt liên kết:

- **Metrics:** Invocations/Errors/Throttles, Duration p95/p99, concurrency, async/ESM backlogs.
- **Logs:** START/END/REPORT, log ứng dụng có requestId/correlationId, không lộ dữ liệu nhạy cảm.
- **Traces:** AWS X-Ray/other instrumentation để phân tích latency xuyên dịch vụ.
- **Alerts/SLOs:** tác động người dùng, queue age, availability, latency, error budgets và runbook.
- **Billing:** requests, memory × billed duration, provisioned concurrency, /tmp, SnapStart khi áp dụng, logs, network và downstream.
- **Reliability:** idempotency, bounded retries, DLQ/on-failure destination, timeout, concurrency và khả năng replay.

### Checklist production

1. Xác định **SLO** theo người dùng và nguồn event, không chỉ handler metrics.
2. Dashboard có **Errors/Invocations ratio**, Throttles, p95 Duration và Maximum concurrency đúng dimension.
3. Với async: theo dõi **AsyncEventAge, AsyncEventsDropped, destination/DLQ**.
4. Với SQS/streams: theo dõi **queue age/IteratorAge/OffsetLag** đúng nguồn.
5. Log có cấu trúc, log group retention và IAM/KMS phù hợp, không chứa secrets/PII.
6. Tracing/Insights được bật khi có giá trị điều tra, quan sát overhead và chi phí.
7. Memory được benchmark bằng **GB-seconds + latency + errors**, không tối ưu bằng cảm giác.
8. Cold start được kiểm chứng trước khi đầu tư SnapStart/Provisioned Concurrency.
9. Batch, filter, SDK retries và concurrency được điều chỉnh để giữ đúng kết quả nghiệp vụ.
10. Chi phí được phân tích ở **toàn bộ pipeline**, không chỉ hóa đơn Lambda.
11. Có AWS Budgets/Cost Anomaly Detection, nhưng không giả định alert là hard cost limit.
12. Định kỳ load-test, review IAM, thử DLQ/replay, diễn tập rollback và kiểm tra RPO/RTO khi dữ liệu cần phục hồi.

Năng lực quan trọng nhất là **đo được nguyên nhân** và **thay đổi có kiểm chứng**: Lambda chạy nhanh hơn chưa chắc rẻ hơn; Lambda Errors thấp chưa chắc ứng dụng khỏe; request ít hơn chưa chắc tính đúng đắn được giữ. Kết hợp quan sát kỹ thuật với hiệu quả nghiệp vụ sẽ giúp hệ thống AWS an toàn, bền vững và tối ưu chi phí dài hạn.

### Tài liệu AWS chính thức

- [Monitoring Lambda metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html) — giám sát Lambda bằng CloudWatch.
- [Types of metrics for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics-types.html) — Invocations, Errors, Throttles, Duration và metrics theo nguồn.
- [Viewing Lambda logs](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs-view.html) — START/END/REPORT và truy cập logs.
- [Advanced logging controls](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-logs.html) — JSON, log levels và destinations.
- [AWS X-Ray for Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html) — tracing phân tán.
- [CloudWatch Lambda Insights](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-insights.html) — runtime CPU/memory/network telemetry.
- [Understanding Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html) — concurrency, reserved/provisioned và throttles.
- [Configuring Lambda memory](https://docs.aws.amazon.com/lambda/latest/dg/configuration-memory.html) — CPU tỷ lệ theo memory.
- [Configuring ephemeral storage](https://docs.aws.amazon.com/lambda/latest/dg/configuration-ephemeral-storage.html) — /tmp và mức cấu hình.
- [Lambda SnapStart](https://docs.aws.amazon.com/lambda/latest/dg/snapstart.html) — initialization snapshot, runtime và giới hạn.
- [Asynchronous invocation error handling](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html) — retry và event age.
- [SQS error handling and partial batch](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html) — failed message handling.
- [AWS Lambda pricing](https://aws.amazon.com/lambda/pricing/) — các compute modes, requests, duration, provisioned concurrency và tùy chọn khác.
- [AWS Cost Explorer](https://docs.aws.amazon.com/cost-management/latest/userguide/ce-what-is.html) — phân tích chi phí sử dụng AWS.
- [AWS Pricing Calculator](https://calculator.aws/) — dự toán chi phí theo kiến trúc và Region.


