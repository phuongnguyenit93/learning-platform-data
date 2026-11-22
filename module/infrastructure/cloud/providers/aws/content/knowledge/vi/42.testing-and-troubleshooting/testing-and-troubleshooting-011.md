# Liên kết log, metric, trace và CloudTrail để tìm nguyên nhân

Khi một API trên AWS trả lỗi 500, một Lambda xử lý chậm hoặc một message bị kẹt trong queue, từng dịch vụ thường chỉ cho thấy một phần của sự cố. CloudWatch Logs có thể chứa stack trace, CloudWatch Metrics cho biết tỷ lệ lỗi tăng, AWS X-Ray cho thấy request bị chậm ở dependency nào và AWS CloudTrail ghi nhận ai đã thay đổi policy hoặc cấu hình ngay trước khi sự cố xảy ra. Nếu các tín hiệu này không được liên kết, kỹ sư phải tìm từng nơi, đối chiếu thời gian thủ công và có thể bỏ sót nguyên nhân nằm ở ranh giới giữa các dịch vụ.

Observability là khả năng suy luận trạng thái bên trong hệ thống từ những dữ liệu mà hệ thống phát ra. Ba tín hiệu thường được dùng là logs, metrics và traces. Logs ghi lại sự kiện chi tiết; metrics tổng hợp hành vi theo thời gian; traces thể hiện đường đi của một request qua nhiều thành phần. CloudTrail bổ sung góc nhìn audit về hoạt động API trên tài khoản AWS, đặc biệt hữu ích khi điều tra thay đổi cấu hình, danh tính gọi API và hành động trên tài nguyên.

Không tín hiệu nào tự giải thích toàn bộ sự cố. Một metric cho biết lỗi tăng nhưng không nói request nào bị lỗi. Một trace cho thấy thời gian chờ ở database nhưng không nhất thiết giải thích vì sao security group vừa bị sửa. Một CloudTrail event ghi nhận thay đổi IAM role nhưng không cho biết request nghiệp vụ nào bị ảnh hưởng. Muốn tìm nguyên nhân, cần thống nhất định danh xuyên suốt, đồng bộ thời gian, cấu trúc log, propagation trace context, lưu giữ audit event và một quy trình điều tra có thứ tự.

Bài học này thuộc phạm vi CLOUD_PROVIDERS_AWS: lựa chọn và vận hành dịch vụ có khả năng giám sát, phục hồi và kiểm soát chi phí. Trọng tâm là cách kết hợp CloudWatch Logs, Metrics, Alarms, AWS X-Ray, OpenTelemetry và CloudTrail để nối triệu chứng với request, dependency, thay đổi cấu hình và nguyên nhân gốc.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt logs, metrics, traces và audit events.
- Giải thích vai trò của CloudWatch, AWS X-Ray, OpenTelemetry và CloudTrail.
- Thiết kế structured logging và correlation ID cho ứng dụng phân tán.
- Truyền trace context qua API Gateway, Lambda, queue và service-to-service call.
- Dùng CloudWatch Logs Insights để tìm lỗi và đối chiếu log theo request.
- Dùng metric, alarm, dashboard và anomaly detection để phát hiện triệu chứng.
- Đọc trace, span và service map để xác định dependency gây chậm hoặc lỗi.
- Tìm CloudTrail management event và data event liên quan đến thay đổi AWS resource.
- Kết hợp thời gian, resource ID, principal, request ID và deployment version để dựng timeline.
- Bảo vệ dữ liệu quan sát, giới hạn quyền, retention và chi phí.
- Áp dụng quy trình điều tra từ phát hiện đến xác minh nguyên nhân và theo dõi sau khắc phục.

## 2. Observability và bốn loại tín hiệu

### 2.1. Logs

Log là bản ghi một sự kiện tại một thời điểm. Log có thể chứa:

- Request bắt đầu hoặc kết thúc.
- Kết quả validation và authorization.
- Lỗi exception hoặc timeout.
- Thời gian xử lý một operation.
- ID của request, trace hoặc message.
- Resource và phiên bản ứng dụng.

Log phù hợp để trả lời câu hỏi “điều gì đã xảy ra trong lần thực thi này?”. Log hữu ích nhất khi có cấu trúc, timestamp rõ ràng, mức độ nghiêm trọng và định danh để lọc.

### 2.2. Metrics

Metric là chuỗi số liệu theo thời gian, thường được tổng hợp theo namespace, metric name và dimensions. Ví dụ:

- Số request mỗi phút.
- Tỷ lệ HTTP 5xx.
- Lambda duration p95.
- SQS ApproximateAgeOfOldestMessage.
- Số kết nối database.
- CPU utilization.

Metric phù hợp để trả lời “hệ thống đang hoạt động như thế nào và xu hướng thay đổi ra sao?”. Metric hỗ trợ alarm và dashboard, nhưng thường không chứa đủ chi tiết để giải thích một request riêng lẻ.

### 2.3. Traces

Trace biểu diễn hành trình của một request hoặc transaction xuyên nhiều thành phần. Một trace gồm các span; mỗi span đại diện cho một operation như API handler, Lambda invocation, database query hoặc HTTP call.

Trace phù hợp để trả lời:

- Request đi qua những service nào?
- Thành phần nào chiếm nhiều thời gian?
- Dependency nào trả lỗi?
- Có retry hoặc fan-out không?
- Các span có cùng thuộc một request không?

Trace giúp phân tích latency và quan hệ nhân quả theo luồng request, nhưng sampling có thể khiến không phải mọi request đều có trace đầy đủ.

### 2.4. Audit events

Audit event ghi lại hành động đối với hệ thống hoặc tài nguyên, thường gồm principal, API action, thời gian, nguồn gọi và kết quả. Trên AWS, CloudTrail là nguồn chính để điều tra hoạt động control plane và các data event được cấu hình.

CloudTrail phù hợp để trả lời:

- Ai đã gọi API?
- Hành động nào được thực hiện?
- Tài nguyên nào bị tác động?
- API call thành công hay bị từ chối?
- Thay đổi cấu hình xảy ra trước hay sau thời điểm lỗi?

CloudTrail không thay thế application log, packet capture hoặc trace. Nó ghi nhận hoạt động AWS API theo loại event và cấu hình trail/event data store.

### 2.5. So sánh nhanh

| Tín hiệu | Đơn vị quan sát | Câu hỏi chính | Công cụ AWS thường dùng |
|---|---|---|---|
| Logs | Sự kiện/bản ghi | Điều gì đã xảy ra? | CloudWatch Logs |
| Metrics | Giá trị theo thời gian | Khi nào và mức độ nào? | CloudWatch Metrics |
| Traces | Request và span | Request đi qua đâu, chậm ở đâu? | AWS X-Ray, OpenTelemetry |
| Audit events | Hành động trên tài nguyên | Ai đã thay đổi hoặc gọi API nào? | AWS CloudTrail |

### 2.6. Từ monitoring đến observability

Monitoring thường theo dõi những điều đã biết trước, như CPU cao hoặc tỷ lệ 5xx vượt ngưỡng. Observability giúp điều tra câu hỏi chưa biết trước bằng cách kết hợp log, metric, trace, metadata và audit event.

Một hệ thống có nhiều dashboard nhưng không có correlation ID vẫn khó điều tra. Một hệ thống có trace nhưng không có retention phù hợp có thể mất bằng chứng khi sự cố kéo dài. Vì vậy, thiết kế observability cần bắt đầu từ cách đội vận hành sẽ tìm nguyên nhân, không chỉ từ việc bật từng dịch vụ.

## 3. Kiến trúc quan sát trên AWS

### 3.1. Luồng tín hiệu tổng quát

Một ứng dụng phân tán có thể phát tín hiệu theo luồng:

1. API Gateway nhận request và tạo request context.
2. Lambda hoặc ECS service xử lý, ghi structured log và phát metric.
3. Trace context được truyền tới downstream service.
4. X-Ray hoặc OpenTelemetry collector/exporter gửi span tới backend quan sát.
5. CloudWatch nhận log, metric, alarm và dashboard.
6. CloudTrail ghi lại hoạt động API đối với AWS resource.
7. Người trực vận hành dùng request ID, trace ID, resource ARN và thời gian để đối chiếu.

~~~mermaid
flowchart LR
    U[Client] --> A[API Gateway]
    A --> S[Lambda / ECS services]
    S --> D[(DynamoDB / RDS)]
    S --> Q[SQS / EventBridge]
    Q --> C[Consumers]
    A -. logs .-> L[CloudWatch Logs]
    S -. logs .-> L
    C -. logs .-> L
    S -. metrics .-> M[CloudWatch Metrics]
    C -. metrics .-> M
    A -. trace context .-> X[X-Ray / OpenTelemetry]
    S -. spans .-> X
    C -. spans .-> X
    AWS[AWS API activity] --> T[CloudTrail]
    L --> O[Investigation]
    M --> O
    X --> O
    T --> O
~~~

Sơ đồ thể hiện các nguồn tín hiệu và điểm phân tích. Tùy kiến trúc, log và trace có thể được xuất qua subscription, collector hoặc dịch vụ đối tác; CloudTrail có thể lưu vào S3, CloudWatch Logs hoặc CloudTrail Lake.

### 3.2. CloudWatch là lớp quan sát vận hành

Amazon CloudWatch cung cấp:

- Logs: thu thập, lưu trữ, truy vấn và phân tích log.
- Metrics: lưu chuỗi số liệu và metric tùy chỉnh.
- Alarms: đánh giá metric hoặc biểu thức để phát cảnh báo.
- Dashboards: tổng hợp trạng thái nhiều dịch vụ.
- Logs Insights: truy vấn log bằng ngôn ngữ truy vấn.
- Synthetics: chạy canary kiểm tra endpoint hoặc hành trình.
- Application Signals: quan sát hiệu năng ứng dụng và service dependency cho các workload được hỗ trợ.

CloudWatch nhận metric tự động từ nhiều AWS service. Ứng dụng có thể gửi custom metrics hoặc Embedded Metric Format (EMF) khi cần đo business metric.

### 3.3. AWS X-Ray và OpenTelemetry

AWS X-Ray thu thập và hiển thị trace, service map và thông tin span. Ứng dụng có thể instrument bằng SDK/agent phù hợp hoặc dùng OpenTelemetry với exporter/collector tương thích.

OpenTelemetry là framework mở để tạo, thu thập và export traces, metrics và logs. AWS Distro for OpenTelemetry (ADOT) cung cấp distribution và collector được AWS hỗ trợ cho các môi trường phù hợp. Có thể dùng CloudWatch, X-Ray hoặc backend observability khác làm đích.

Không nên trộn nhiều instrumentation tạo span trùng cho cùng một operation. Chọn một chiến lược instrument nhất quán, xác định service name và propagation format rồi kiểm thử trace xuyên suốt.

### 3.4. CloudTrail bổ sung góc nhìn audit

CloudTrail ghi lại hoạt động API trong AWS account. Event history cho phép xem management events gần đây theo Region; trail có thể chuyển event tới S3 và tùy cấu hình tới CloudWatch Logs; CloudTrail Lake hỗ trợ lưu và truy vấn event theo event data store.

Khi cần điều tra, CloudTrail có thể cho biết policy, security group, route table, Lambda configuration, KMS key hoặc resource khác đã bị thay đổi bởi principal nào. Đối chiếu event đó với application trace và metric để xác định liệu thay đổi có liên quan đến triệu chứng hay không.

## 4. Thiết kế định danh để liên kết tín hiệu

### 4.1. Vì sao cần correlation ID?

Một request có thể tạo nhiều log ở nhiều service và phát sinh event bất đồng bộ. Nếu mỗi service tự tạo ID riêng, rất khó biết các bản ghi thuộc cùng một hành trình.

Correlation ID là định danh ứng dụng dùng để liên kết các log và event trong cùng một nghiệp vụ. Có thể dùng request ID do gateway tạo, hoặc tạo ID ở entry service nếu request đến từ nguồn khác.

Ví dụ:

~~~json
{
  "timestamp": "2026-11-20T10:15:30.123Z",
  "level": "INFO",
  "service": "order-api",
  "environment": "production",
  "event": "order.created",
  "request_id": "req-7f2a",
  "correlation_id": "corr-91bd",
  "trace_id": "1-673ecb36-2a1b4c8d5e6f789012345678",
  "span_id": "4a1b2c3d4e5f6789",
  "order_id": "order-123",
  "duration_ms": 42
}
~~~

Các giá trị trên chỉ minh họa. Không dùng ID chứa email, số điện thoại, access token hoặc thông tin cá nhân.

### 4.2. Phân biệt các ID

| ID | Phạm vi | Mục đích |
|---|---|---|
| requestId | Một lần gọi API hoặc invocation | Tìm request trong log của thành phần nhận |
| correlationId | Một nghiệp vụ xuyên nhiều request/service | Liên kết log và event qua workflow |
| traceId | Một distributed trace | Gom các span của một hành trình |
| spanId | Một operation trong trace | Xác định operation cụ thể |
| messageId/eventId | Một message/event | Deduplicate và truy vết xử lý |
| deploymentId/buildId | Một lần phát hành/build | Liên kết sự cố với phiên bản code/config |

Không dùng một ID duy nhất thay cho tất cả khái niệm. Trace ID thường thay đổi khi bắt đầu một trace mới hoặc khi có ranh giới bất đồng bộ; correlation ID có thể được giữ qua nhiều trace thuộc cùng một nghiệp vụ.

### 4.3. Propagate qua HTTP

Khi service gọi service khác, truyền trace context theo chuẩn được instrumentation hỗ trợ, thường là W3C Trace Context với header traceparent và có thể thêm tracestate. Một số thành phần AWS sử dụng hoặc hiểu header X-Amzn-Trace-Id.

Ứng dụng cũng có thể truyền correlation ID qua header riêng, ví dụ:

~~~http
X-Correlation-Id: corr-91bd
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

Nếu nhận correlation ID từ client, validate độ dài và ký tự hợp lệ. Không cho phép client đưa chuỗi cực dài hoặc nội dung nhạy cảm vào log. Có thể tạo ID mới ở gateway và lưu ID bên ngoài vào trường riêng nếu cần đối chiếu.

### 4.4. Propagate qua queue và event

Với SQS, EventBridge hoặc Kinesis, đặt correlation ID, event ID và trace context vào message attributes hoặc envelope theo hợp đồng của ứng dụng.

Ví dụ event:

~~~json
{
  "eventId": "evt-8831",
  "eventType": "OrderCreated",
  "correlationId": "corr-91bd",
  "traceContext": {
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
  },
  "detail": {
    "orderId": "order-123"
  }
}
~~~

Với luồng bất đồng bộ, consumer có thể tạo span mới và liên kết với context producer bằng parent context hoặc span link theo cách instrumentation hỗ trợ. Không phải mọi trigger tự động truyền mọi custom header; cần kiểm tra envelope và cấu hình propagation của SDK/agent.

### 4.5. Propagate trong Lambda

Lambda cung cấp context object có request ID riêng cho mỗi invocation. Có thể ghi request ID vào log, đồng thời dùng trace context từ trigger hoặc instrumentation. Với Lambda active tracing, X-Ray có thể tạo segment cho invocation và liên kết các downstream call được instrument.

Đối với SQS batch, một invocation có thể xử lý nhiều message. Ghi message ID và correlation ID cho từng record; không dùng một request ID làm định danh duy nhất cho tất cả nghiệp vụ trong batch.

### 4.6. Trace ID không phải correlation ID

Trace thường tập trung vào một đường thực thi kỹ thuật. Một đơn hàng có thể đi qua API request, async consumer, retry và workflow chạy nhiều phút. Mỗi phần có thể có trace riêng, nhưng cùng correlation ID và business ID.

Khi thiết kế hệ thống:

- Trace ID liên kết span.
- Correlation ID liên kết nghiệp vụ.
- Event ID xác định message cụ thể.
- Resource ID xác định tài nguyên AWS.

Sự phân biệt này giúp điều tra cả request đồng bộ lẫn workflow bất đồng bộ kéo dài.

## 5. Structured logging với CloudWatch Logs

### 5.1. Log có cấu trúc

Structured logging ghi dữ liệu theo JSON hoặc định dạng có field rõ ràng. So với log văn bản tự do, JSON dễ lọc theo service, level, request ID, trace ID, tenant đã được pseudonymize và error code.

Một record nên có:

- Timestamp theo UTC.
- Level: DEBUG, INFO, WARN, ERROR.
- Service và environment.
- Event name hoặc operation.
- Request/correlation/trace ID phù hợp.
- Duration và outcome.
- Error type/code, stack trace khi cần.
- Resource hoặc dependency đã gọi.
- Version của ứng dụng.

Không log toàn bộ request/response mặc định. Chỉ ghi các field cần điều tra và đã được phân loại dữ liệu.

### 5.2. Ví dụ Python logging

~~~python
import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def log_event(level, event, **fields):
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "service": os.environ.get("SERVICE_NAME", "order-api"),
        "environment": os.environ.get("ENVIRONMENT", "test"),
        "event": event,
        **fields,
    }
    logger.log(getattr(logging, level), json.dumps(record))
~~~

Ví dụ gọi:

~~~python
log_event(
    "INFO",
    "order.created",
    correlation_id="corr-91bd",
    order_id="order-123",
    duration_ms=42,
)
~~~

Trong production, nên dùng logging library có khả năng quản lý context và redaction. Không cho field tùy ý ghi đè timestamp, level hoặc service nếu điều đó làm sai định dạng log.

### 5.3. Log levels

| Level | Khi sử dụng |
|---|---|
| DEBUG | Chi tiết phục vụ phát triển hoặc điều tra có kiểm soát |
| INFO | Sự kiện bình thường quan trọng |
| WARN | Bất thường có thể tự phục hồi hoặc chưa ảnh hưởng nghiêm trọng |
| ERROR | Operation thất bại cần điều tra |
| FATAL/CRITICAL | Thành phần không thể tiếp tục hoạt động bình thường |

Tránh ghi cùng một exception ở nhiều tầng khiến log nhân bản. Chọn nơi có đủ context để ghi lỗi đầy đủ; các tầng khác có thể bổ sung trạng thái hoặc rethrow.

### 5.4. CloudWatch Logs groups và streams

Log group thường đại diện cho ứng dụng hoặc thành phần; log stream phân chia nguồn ghi, chẳng hạn Lambda execution environment hoặc container. Quy ước tên nên dễ tìm và có environment.

Ví dụ:

~~~text
/aws/lambda/order-api-prod
/ecs/commerce/checkout-prod
/aws/apigateway/commerce-prod
~~~

Đặt retention theo nhu cầu vận hành, audit và quy định. Không để log group giữ vô thời hạn nếu không có yêu cầu. Với log nhạy cảm, cân nhắc encryption bằng KMS, quyền truy cập riêng và subscription filter tới nơi lưu trữ kiểm soát.

### 5.5. CloudWatch Logs Insights

Logs Insights truy vấn log theo time range, field, filter, parse, stats và sort. Với JSON structured logs, field thường được phát hiện tự động.

Tìm lỗi gần đây:

~~~text
fields @timestamp, service, event, correlation_id, trace_id, error_code, @message
| filter level = "ERROR"
| sort @timestamp desc
| limit 100
~~~

Đếm lỗi theo service:

~~~text
fields service, level
| filter level = "ERROR"
| stats count() as errorCount by service
| sort errorCount desc
~~~

Tìm một nghiệp vụ:

~~~text
fields @timestamp, service, event, correlation_id, order_id, trace_id, duration_ms
| filter correlation_id = "corr-91bd"
| sort @timestamp asc
~~~

Tính latency p95:

~~~text
filter ispresent(duration_ms)
| stats pct(duration_ms, 95) as p95, avg(duration_ms) as average by service
~~~

Tên field và kiểu dữ liệu phụ thuộc log thực tế. Chọn time range hẹp trước, sau đó mở rộng nếu cần; truy vấn log lớn có thể tốn thời gian và chi phí.

### 5.6. Metric filters và Embedded Metric Format

Metric filter chuyển pattern trong log thành CloudWatch metric. EMF cho phép ứng dụng ghi JSON log chứa metric definition để CloudWatch trích xuất metric mà không cần gọi PutMetricData cho từng điểm.

EMF hữu ích khi ứng dụng cần đo business metric như:

- orders_created.
- payment_declined.
- inventory_conflict.
- workflow_duration.

Không đưa request ID, user ID hoặc order ID làm metric dimension nếu cardinality cao. Các ID này nên nằm trong log/trace; metric dimension nên dùng thuộc tính có tập giá trị giới hạn như service, environment, operation hoặc region.

### 5.7. Correlation trong log

Mỗi log record nên ghi cùng các trường liên kết khi có thể:

~~~json
{
  "service": "payment-worker",
  "event": "payment.authorized",
  "correlation_id": "corr-91bd",
  "event_id": "evt-8831",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "span_id": "00f067aa0ba902b7",
  "deployment_id": "release-2026-11-20.3"
}
~~~

Nhờ đó, kỹ sư có thể bắt đầu từ correlation ID, tìm log ở nhiều service, mở trace tương ứng và kiểm tra phiên bản release.

## 6. Metrics, alarms và dashboards

### 6.1. Metric namespace và dimensions

Metric trong CloudWatch được tổ chức theo namespace, metric name và dimensions. AWS service phát metric trong namespace riêng; custom application có thể dùng namespace riêng như Commerce/Orders.

Dimension nên đại diện cho thuộc tính có số lượng giá trị hữu hạn. Ví dụ:

- ServiceName.
- Environment.
- Operation.
- Region.
- QueueName.

Tránh dimension là request ID, trace ID, email hoặc order ID. Cardinality cao làm tăng số metric time series và chi phí, đồng thời khiến dashboard khó tổng hợp.

### 6.2. Golden signals

Bốn nhóm tín hiệu thường dùng cho service:

1. **Latency:** thời gian xử lý request.
2. **Traffic:** số request hoặc message.
3. **Errors:** tỷ lệ request thất bại.
4. **Saturation:** mức sử dụng tài nguyên hoặc backlog.

Ví dụ với API:

| Signal | Metric có thể theo dõi |
|---|---|
| Latency | IntegrationLatency, Duration, p95/p99 |
| Traffic | Count, Invocations, requests/sec |
| Errors | 5xx, Errors, Throttles |
| Saturation | ConcurrentExecutions, queue age, DB connections |

Chỉ nhìn CPU thấp không chứng minh service khỏe. Queue backlog tăng có thể báo consumer không theo kịp dù CPU của API vẫn bình thường.

### 6.3. Percentile và average

Average có thể che giấu request chậm ở đuôi phân phối. Ví dụ 99 request mất 50 ms và một request mất 5 giây có thể vẫn tạo average tương đối thấp. Theo dõi p50, p90, p95 và p99 tùy SLA.

Với metric phân phối, chọn statistic và period phù hợp. Không tính percentile từ các average đã tổng hợp nếu cần percentile chính xác; dùng metric type/histogram phù hợp.

### 6.4. CloudWatch Alarms

Alarm đánh giá metric theo period và threshold hoặc anomaly band. Có thể cấu hình:

- Static threshold.
- Metric math.
- Anomaly detection.
- M-of-N evaluation.
- Missing data treatment.
- Alarm action qua SNS, Incident Manager hoặc automation được tích hợp.

Một alarm tốt cần:

- Tín hiệu gắn với user impact.
- Threshold có cơ sở từ baseline/SLO.
- Evaluation period tránh nhiễu.
- Owner và runbook rõ ràng.
- Hành động khi alarm chuyển ALARM/OK.

Không tạo alarm cho mọi metric mà không có người xử lý. Alarm fatigue làm giảm khả năng phản ứng với sự cố thật.

### 6.5. SLO và error budget

Service Level Objective (SLO) xác định mục tiêu độ tin cậy, ví dụ tỷ lệ request thành công hoặc latency dưới ngưỡng trong cửa sổ thời gian. Error budget là phần lỗi được chấp nhận trong SLO.

Ví dụ:

- 99,9% request thành công trong 30 ngày.
- 95% request hoàn tất dưới 300 ms.
- 99% event được xử lý trong vòng 2 phút.

Theo dõi SLO giúp phân biệt lỗi nhỏ, ngắn hạn với xu hướng suy giảm ảnh hưởng người dùng. Burn rate alert có thể cảnh báo khi error budget bị tiêu thụ nhanh.

### 6.6. Dashboard

Dashboard vận hành nên tập trung vào câu hỏi:

- Service có đang phục vụ người dùng không?
- Lỗi và latency bắt đầu từ lúc nào?
- Dependency nào có dấu hiệu bất thường?
- Queue hoặc concurrency có bị bão hòa?
- Phiên bản nào đang chạy?
- Có thay đổi cấu hình gần thời điểm sự cố không?

Một dashboard tổng quan có thể có row cho API, compute, database, queue/event, dependency và deployment. Tạo dashboard theo service ownership và gắn link tới Logs Insights query, trace search và runbook.

### 6.7. Anomaly detection

CloudWatch anomaly detection dùng mô hình để xác định vùng giá trị kỳ vọng theo lịch sử metric. Tính năng hữu ích với tải có chu kỳ ngày/tuần hoặc metric khó đặt threshold cố định.

Anomaly band không tự hiểu tác động nghiệp vụ. Một spike traffic có thể bình thường vào giờ cao điểm; một giá trị nằm trong band vẫn có thể vi phạm SLO. Kết hợp anomaly với error rate, latency và business metric.

## 7. Distributed tracing với AWS X-Ray

### 7.1. Trace và span

Trace là tập hợp các span liên quan tới cùng một request hoặc workflow. Span có:

- Tên operation.
- Start time và duration.
- Parent/child relationship.
- Service/resource identity.
- Status/error.
- Attributes hoặc annotations.

Ví dụ một request:

~~~text
API Gateway
  └── Order Lambda
       ├── DynamoDB PutItem
       └── EventBridge PutEvents
            └── Payment Consumer
                 └── Payment API
~~~

Trace cho phép xác định phần nào chiếm latency và dependency nào trả lỗi.

### 7.2. X-Ray segment và subsegment

Segment đại diện cho công việc của service xử lý request. Subsegment biểu diễn operation bên trong, như gọi AWS SDK, HTTP dependency hoặc database. X-Ray có thể tự động instrument một số AWS integration và SDK call khi cấu hình đúng.

Một trace tốt có service name nhất quán, span name có ý nghĩa và error/status rõ ràng. Không đặt span name chứa user ID hoặc giá trị có cardinality cao.

### 7.3. Bật tracing cho Lambda

Lambda hỗ trợ active tracing với AWS X-Ray. Có thể bật trong cấu hình function hoặc IaC. Khi bật, Lambda tạo trace segment cho invocation và có thể kết nối downstream call được instrument.

Ví dụ CloudFormation rút gọn:

~~~yaml
Resources:
  OrderFunction:
    Type: AWS::Lambda::Function
    Properties:
      TracingConfig:
        Mode: Active
~~~

Role cần quyền ghi trace phù hợp, thường được thêm qua managed policy hoặc permission tối thiểu tương ứng. Kiểm tra trace sampling và quyền IAM sau khi deploy; bật tracing mà thiếu quyền hoặc instrumentation không đúng có thể không tạo được trace mong muốn.

### 7.4. X-Ray trace header

X-Ray sử dụng header X-Amzn-Trace-Id để truyền trace context trong một số tích hợp. Header có thể chứa Root, Parent và Sampled. W3C Trace Context dùng traceparent và tracestate.

Khi kết hợp OpenTelemetry và X-Ray, dùng propagator tương thích và xác minh trace ID được nối xuyên các service. Không tự tạo header giả làm parent nếu không hiểu sampling và trace relationship.

### 7.5. Sampling

Sampling giảm lượng trace được thu thập để kiểm soát chi phí và overhead. X-Ray sampling rules có thể chọn tỷ lệ hoặc reservoir theo service, host, path và điều kiện được hỗ trợ.

Trade-off:

- Sampling thấp giảm chi phí nhưng có thể bỏ lỡ lỗi hiếm.
- Sampling cao tăng khả năng quan sát nhưng tăng dữ liệu và chi phí.
- Có thể dùng tail sampling ở collector trong một số kiến trúc OpenTelemetry để ưu tiên giữ trace lỗi/chậm, nếu pipeline hỗ trợ.

Với sự cố hiếm, bổ sung structured error logs và metrics để phát hiện dù trace không được sample.

### 7.6. Service map

X-Ray service map biểu diễn các service và dependency được suy ra từ trace. Nó giúp phát hiện:

- Service có latency cao.
- Dependency có error rate tăng.
- Request bị dừng ở downstream.
- Quan hệ giữa API, Lambda và AWS service.

Service map phụ thuộc trace được gửi lên và cách instrumentation nhận diện dependency. Nếu thiếu span hoặc trace context không được propagate, bản đồ có thể không phản ánh đầy đủ hệ thống.

### 7.7. Annotations và metadata

X-Ray annotations là các field được index để lọc trace; metadata lưu thông tin bổ sung không nhất thiết được index. Chỉ annotate thuộc tính có giá trị điều tra và cardinality phù hợp như operation, environment, tenant tier hoặc error category.

Không đưa PII, secret, request body đầy đủ hoặc token vào annotation/metadata. Trace có thể được nhiều operator xem và retention có thể khác log.

## 8. OpenTelemetry và CloudWatch Application Signals

### 8.1. OpenTelemetry

OpenTelemetry cung cấp API, SDK, semantic conventions và collector để instrument ứng dụng. Nó giúp tránh khóa chặt code vào một backend quan sát cụ thể.

Các tín hiệu:

- Traces: span và context propagation.
- Metrics: counter, gauge và histogram.
- Logs: record có context.

Ứng dụng instrument bằng OpenTelemetry SDK có thể export qua OTLP tới collector, rồi collector chuyển tiếp tới backend phù hợp.

### 8.2. AWS Distro for OpenTelemetry

AWS Distro for OpenTelemetry (ADOT) là distribution của OpenTelemetry do AWS hỗ trợ cho các môi trường và tích hợp được công bố. ADOT Collector có thể nhận OTLP, xử lý processor và export telemetry tới CloudWatch, X-Ray hoặc đích tương thích.

Ví dụ pipeline collector ở mức khái niệm:

~~~yaml
receivers:
  otlp:
    protocols:
      grpc:
      http:

processors:
  batch:

exporters:
  awsxray:
  awsemf:

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsxray]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [awsemf]
~~~

Cấu hình thực tế phụ thuộc phiên bản collector, exporter, IAM role và môi trường chạy. Cần kiểm tra component availability và schema theo bản ADOT được triển khai.

### 8.3. CloudWatch Application Signals

Application Signals cung cấp góc nhìn application performance monitoring cho các service và dependency được hỗ trợ, gồm service map, latency, error và availability signals. Nó có thể giảm công sức dựng dashboard thủ công khi runtime và instrumentation được hỗ trợ.

Trước khi bật, kiểm tra ngôn ngữ/runtime, deployment model, quyền và Region availability. Application Signals không tự instrument mọi custom protocol hoặc mọi thành phần bên ngoài; vẫn cần bổ sung span/metric cho business operation đặc thù.

### 8.4. Chọn X-Ray SDK hay OpenTelemetry

| Tiêu chí | X-Ray instrumentation | OpenTelemetry/ADOT |
|---|---|---|
| Tích hợp AWS | Trực tiếp với X-Ray và AWS service | Có exporter/collector cho AWS |
| Tính mở | Gắn với X-Ray API/format ở một số phần | Chuẩn mở và nhiều backend |
| Portability | Phù hợp hệ thống AWS-centric | Thuận lợi khi cần nhiều backend |
| Instrumentation | Theo SDK/agent tương ứng | Theo OTel SDK/auto instrumentation |
| Vận hành | Quản lý X-Ray segment và sampling | Quản lý collector, pipeline và exporter |

Chọn một chuẩn propagation và tránh instrument trùng. Với hệ thống mới, cân nhắc OpenTelemetry nếu cần portability; với hệ thống hiện hữu dùng X-Ray, có thể tiếp tục hoặc chuyển dần theo kế hoạch.

## 9. AWS CloudTrail để điều tra thay đổi và hoạt động API

### 9.1. CloudTrail ghi gì?

CloudTrail ghi lại hoạt động trong AWS account dưới dạng event. Một event thường chứa:

- eventTime: thời điểm API call.
- eventSource: dịch vụ AWS gọi tới.
- eventName: tên API operation.
- awsRegion: Region.
- userIdentity: principal hoặc session thực hiện.
- sourceIPAddress: nguồn gọi.
- requestParameters: tham số request, nếu được ghi.
- responseElements: thông tin response, nếu có.
- errorCode và errorMessage: lỗi nếu operation thất bại.
- resources: tài nguyên liên quan.
- eventID và requestID: định danh event/API request.

CloudTrail có thể giúp xác định một IAM policy, route table, security group, Lambda configuration hoặc KMS key đã bị thay đổi. Nội dung chi tiết phụ thuộc API, event type và quy tắc loại bỏ dữ liệu nhạy cảm của dịch vụ.

### 9.2. Management events

Management events ghi nhận hoạt động control plane như tạo, cập nhật hoặc xóa AWS resource, thay đổi policy và cấu hình dịch vụ. CloudTrail Event history cung cấp lịch sử management events gần đây theo Region.

Ví dụ:

- UpdateFunctionConfiguration.
- PutRolePolicy.
- AuthorizeSecurityGroupIngress.
- PutBucketPolicy.
- UpdateTable.

Tên event chính xác phụ thuộc dịch vụ và API operation. Khi điều tra, tìm theo event source, event name, principal và resource.

### 9.3. Data events

Data events ghi nhận thao tác trên data plane của một số loại tài nguyên, ví dụ S3 object-level API hoặc Lambda function invocation theo cấu hình hỗ trợ. Data events thường không được bật mặc định cho mọi resource vì volume và chi phí có thể lớn.

Nếu cần audit ai đã đọc object S3 hoặc gọi function, cấu hình data event selector cho đúng bucket, prefix hoặc function. Chỉ bật phạm vi cần thiết và kiểm thử event có được ghi.

### 9.4. Event history, trail và CloudTrail Lake

| Cách xem | Mục đích | Lưu ý |
|---|---|---|
| Event history | Tìm management events gần đây trong Console/API | Có cửa sổ lịch sử giới hạn; không phải kho lưu trữ dài hạn |
| Trail | Gửi event tới S3 và có thể CloudWatch Logs | Phù hợp audit/retention và phân tích ngoài |
| CloudTrail Lake | Lưu event trong event data store và truy vấn SQL | Có chi phí ingest/retention/query theo mô hình dịch vụ |
| EventBridge integration | Phản ứng gần thời gian thực với event phù hợp | Dùng rule để định tuyến và kích hoạt automation |

Một tổ chức thường dùng trail tập trung, account log archive và CloudTrail Lake cho điều tra nâng cao theo chính sách. Cần xác định owner, retention, encryption và quyền đọc audit data.

### 9.5. Log file integrity validation

CloudTrail hỗ trợ log file integrity validation bằng digest files để kiểm tra file log đã được chuyển tới S3 có bị sửa đổi hoặc xóa sau khi CloudTrail ghi hay không. Bật validation khi yêu cầu audit cần bằng chứng toàn vẹn; lưu digest và log trong bucket có quyền hạn chế.

Integrity validation không chứng minh mọi hoạt động đều được ghi nếu trail/event selector chưa bật đúng. Cần kiểm tra coverage của event trước, sau đó mới kiểm tra tính toàn vẹn file.

### 9.6. CloudTrail Insights

CloudTrail Insights có thể phát hiện hoạt động API bất thường đối với các loại event và điều kiện được hỗ trợ, ví dụ thay đổi đột ngột trong tỷ lệ API call. Đây là tín hiệu điều tra bổ sung, không phải thay thế CloudTrail event hoặc metric ứng dụng.

### 9.7. Ví dụ CloudTrail event

~~~json
{
  "eventTime": "2026-11-20T10:12:00Z",
  "eventSource": "lambda.amazonaws.com",
  "eventName": "UpdateFunctionConfiguration",
  "awsRegion": "ap-southeast-1",
  "userIdentity": {
    "type": "AssumedRole",
    "arn": "arn:aws:sts::123456789012:assumed-role/DeploymentRole/build-482"
  },
  "requestParameters": {
    "functionName": "order-api"
  },
  "responseElements": null,
  "eventID": "example-event-id",
  "requestID": "example-request-id"
}
~~~

Ví dụ chỉ minh họa cấu trúc rút gọn; event thực tế có thể có nhiều field và giá trị nhạy cảm có thể được loại bỏ. Khi điều tra, không dựa vào một field đơn lẻ nếu API hoặc dịch vụ không cung cấp field đó.

## 10. Tìm CloudTrail event bằng truy vấn

### 10.1. Tìm trong Event history

Có thể lọc theo:

- Event name.
- Event source.
- User name hoặc principal.
- Resource name.
- Time range.

Bắt đầu bằng khoảng thời gian ngay trước khi metric lỗi tăng. Nếu không thấy event, kiểm tra Region, account, loại event và việc trail có bao phủ resource hay không.

### 10.2. CloudTrail Lake SQL

CloudTrail Lake cho phép truy vấn event data store bằng SQL. Ví dụ tìm các lần thay đổi cấu hình Lambda:

~~~sql
SELECT
    eventTime,
    eventSource,
    eventName,
    userIdentity.arn,
    sourceIPAddress,
    requestParameters
FROM event_data_store
WHERE eventSource = 'lambda.amazonaws.com'
  AND eventName = 'UpdateFunctionConfiguration'
  AND eventTime > '2026-11-20 09:00:00'
ORDER BY eventTime DESC;
~~~

Tên bảng/event data store và cú pháp trường phải khớp schema của CloudTrail Lake. Ví dụ này minh họa ý tưởng; hãy kiểm tra SQL dialect và field mapping trong môi trường thực tế.

### 10.3. EventBridge để phát hiện thay đổi

Có thể tạo EventBridge rule cho CloudTrail API event, ví dụ khi IAM policy hoặc security group bị thay đổi. Rule có thể gửi event tới SNS, Lambda hoặc workflow xử lý.

Automation nên có guardrail:

- Chỉ match event quan trọng.
- Kiểm tra principal và resource.
- Ghi lại event ID.
- Tránh tự động rollback thay đổi hợp lệ.
- Có human review cho hành động ảnh hưởng lớn.

### 10.4. Không thấy event cần tìm

Các nguyên nhân:

- Đang xem sai Region hoặc account.
- Event là data event nhưng selector chưa bật.
- Trail chưa ghi loại event tương ứng.
- Event history không còn trong cửa sổ lưu trữ.
- Resource ARN hoặc event source filter sai.
- Event được gửi chậm hoặc đang có độ trễ ingest.

Không kết luận “không có thay đổi” chỉ vì Event history không trả kết quả. Trước hết phải xác nhận coverage của audit configuration.

## 11. Quy trình liên kết log, metric, trace và CloudTrail

### 11.1. Bắt đầu từ triệu chứng

Khi có alarm hoặc báo cáo người dùng:

1. Xác định service, operation và thời điểm bắt đầu.
2. Xác định ảnh hưởng: số request, tenant, Region hoặc business flow.
3. Mở dashboard để xem traffic, errors, latency và saturation.
4. Chọn một request hoặc correlation ID đại diện.
5. Tìm log tương ứng.
6. Mở trace nếu có và xác định span chậm/lỗi.
7. Xác định dependency và resource ARN liên quan.
8. Tìm CloudTrail event thay đổi tài nguyên hoặc quyền trong khoảng thời gian liên quan.
9. Dựng timeline và kiểm tra giả thuyết bằng bằng chứng.

### 11.2. Timeline chung

Một timeline có thể gồm:

| Thời gian UTC | Nguồn | Bằng chứng |
|---|---|---|
| 10:00:00 | Deployment system | Release build-482 bắt đầu |
| 10:02:15 | CloudTrail | Lambda configuration được cập nhật |
| 10:03:00 | CloudWatch Metrics | Lambda Errors bắt đầu tăng |
| 10:03:12 | API Gateway | HTTP 5xx tăng |
| 10:03:15 | X-Ray | Span gọi dependency có lỗi |
| 10:03:16 | CloudWatch Logs | AccessDenied với correlation ID |
| 10:05:00 | Operator | Rollback cấu hình |
| 10:06:00 | Metrics | Error rate trở về baseline |

Đây là ví dụ giả định. Trình tự thời gian gợi ý quan hệ nhưng chưa tự chứng minh nguyên nhân. Cần xác minh request, principal, resource, policy và thay đổi cụ thể.

### 11.3. Ví dụ: Lambda đột ngột nhận AccessDenied

Triệu chứng:

- API 5xx tăng.
- Lambda Errors tăng.
- Logs ghi AccessDeniedException khi đọc secret.
- Trace cho thấy lỗi xảy ra ở bước gọi Secrets Manager.

Điều tra:

1. Lấy correlation ID từ API access log.
2. Tìm Lambda log theo correlation ID và invocation request ID.
3. Mở trace để xác định Secrets Manager là dependency lỗi.
4. Ghi nhận secret ARN và execution role ARN.
5. Tìm CloudTrail event PutRolePolicy, AttachRolePolicy hoặc thay đổi liên quan trong khoảng thời gian trước đó.
6. Xác định principal và policy version bị thay đổi.
7. So sánh IAM policy hiện tại với phiên bản trước.
8. Khôi phục quyền tối thiểu đã được phê duyệt.
9. Chạy smoke test và theo dõi error metric.

Không thêm quyền secretsmanager:* chỉ để làm hết lỗi. Cần cấp đúng GetSecretValue trên secret ARN cần thiết và quyền KMS nếu secret dùng customer-managed key.

### 11.4. Ví dụ: API chậm nhưng không tăng lỗi

Triệu chứng:

- p95 latency tăng từ 200 ms lên 2 giây.
- Error rate vẫn thấp.
- Traffic ổn định.

Điều tra:

1. Mở trace của request chậm.
2. Xác định span DynamoDB/RDS/HTTP chiếm phần lớn thời gian.
3. So sánh service map và metric dependency.
4. Kiểm tra queue age, DB connection, throttling hoặc downstream latency.
5. Đối chiếu CloudTrail để xem có thay đổi instance class, security group, route hoặc cấu hình gần thời điểm đó.
6. Kiểm tra log có retry hoặc timeout trước khi response thành công.

Một request thành công vẫn có thể rất chậm do retry. Chỉ nhìn error count sẽ bỏ sót vấn đề.

### 11.5. Ví dụ: consumer xử lý duplicate event

Triệu chứng:

- Một đơn hàng phát sinh hai thông báo.
- SQS consumer log có cùng order ID nhiều lần.
- Queue depth tăng sau một đợt downstream timeout.

Điều tra:

1. Tìm event ID và correlation ID trong producer/consumer logs.
2. Kiểm tra trace hoặc span link của message processing.
3. Xem ApproximateReceiveCount và DLQ metric.
4. Xác định consumer có commit side effect trước khi ACK/delete message không.
5. Kiểm tra CloudTrail thay đổi queue visibility timeout hoặc event source mapping.
6. Kiểm tra idempotency record và transaction boundary.

CloudTrail có thể chỉ ra thay đổi cấu hình queue; log/trace xác định message và code path. Giải pháp thường là idempotent processing, visibility timeout phù hợp và partial batch response nếu dùng Lambda event source mapping.

## 12. Truy vấn điều tra mẫu

### 12.1. Tìm log theo correlation ID

~~~text
fields @timestamp, service, event, level, request_id, trace_id, message_id, @message
| filter correlation_id = "corr-91bd"
| sort @timestamp asc
| limit 500
~~~

### 12.2. Tìm lỗi theo service và error code

~~~text
fields @timestamp, service, error_code, error_type, correlation_id
| filter level = "ERROR"
| stats count() as failures by service, error_code
| sort failures desc
~~~

### 12.3. Tìm request chậm

~~~text
fields @timestamp, service, operation, duration_ms, correlation_id, trace_id
| filter duration_ms > 1000
| sort duration_ms desc
| limit 100
~~~

### 12.4. Phân tích xu hướng lỗi theo phút

~~~text
filter level = "ERROR"
| stats count() as errors by bin(1m)
| sort bin(1m) asc
~~~

### 12.5. Tìm event CloudTrail theo principal

Trong CloudTrail Lake, có thể truy vấn các event do assumed role thực hiện:

~~~sql
SELECT
    eventTime,
    eventSource,
    eventName,
    userIdentity.arn,
    sourceIPAddress,
    errorCode,
    resources
FROM event_data_store
WHERE userIdentity.arn LIKE '%DeploymentRole%'
  AND eventTime > '2026-11-20 09:00:00'
ORDER BY eventTime DESC;
~~~

Kiểu dữ liệu và cách truy cập nested field có thể khác theo event data store schema. Chạy truy vấn trên time range nhỏ trước để tránh scan dữ liệu không cần thiết.

## 13. Liên kết tín hiệu với dịch vụ AWS cụ thể

### 13.1. API Gateway và Lambda

API Gateway có access log và execution log theo loại API/configuration. Lambda ghi application log và metric như Invocations, Errors, Duration, Throttles và ConcurrentExecutions. X-Ray có thể nối API request với Lambda segment khi tracing được cấu hình.

Khi điều tra:

- Dùng API request ID để tìm access log.
- Dùng Lambda request ID để tìm invocation log.
- Dùng trace ID để mở trace.
- Dùng CloudTrail để tìm thay đổi API, integration, stage hoặc Lambda configuration.

API Gateway request ID và Lambda request ID là hai định danh khác nhau; ghi mapping/correlation ID để nối chúng.

### 13.2. SQS và Lambda event source mapping

SQS metric giúp phát hiện backlog; Lambda metric cho thấy consumer có lỗi hoặc throttling; log cung cấp message ID và receive count; trace có thể thể hiện xử lý từng message hoặc batch.

Các metric hữu ích:

- ApproximateNumberOfMessagesVisible.
- ApproximateAgeOfOldestMessage.
- NumberOfMessagesSent/Received/Deleted.
- Lambda Errors, Duration và Throttles.

CloudTrail giúp kiểm tra thay đổi queue policy, redrive policy, event source mapping hoặc visibility timeout.

### 13.3. DynamoDB

DynamoDB cung cấp metric như ConsumedReadCapacityUnits, ConsumedWriteCapacityUnits, ThrottledRequests và latency-related metrics theo cấu hình/namespace. Application log nên ghi operation, table/index và error code; trace nên instrument SDK/database call.

CloudTrail có thể ghi management events như CreateTable/UpdateTable; data events cho thao tác item cần cấu hình theo khả năng và event selector hiện hành. Không giả định mọi GetItem/PutItem đều xuất hiện trong Event history nếu data events chưa được bật.

### 13.4. RDS và Aurora

Kết hợp:

- CloudWatch metrics: CPU, connections, free storage, latency và replication lag.
- Database logs: error log, slow query log hoặc audit log theo engine/cấu hình.
- Application traces: thời gian connection acquisition và query.
- CloudTrail: thay đổi DB instance/cluster, parameter group, subnet group và security group.

Trace cho thấy query chậm; database engine log và Performance Insights/Database Insights có thể cung cấp thêm thông tin về wait event, SQL và contention. Chỉ CloudTrail không thể giải thích một câu SQL cụ thể chạy chậm.

### 13.5. ECS và EKS

Với ECS, thu thập container logs, task/service events, CPU/memory, restart và deployment events. Với EKS, kết hợp application logs, container insights, Kubernetes events, control plane audit logs theo cấu hình và traces.

CloudTrail ghi hoạt động AWS API và thao tác control plane tích hợp, nhưng không thay thế Kubernetes audit log cho mọi hành động trong cluster. Cần bật đúng nguồn audit và kiểm soát retention.

### 13.6. EventBridge và Step Functions

EventBridge metrics và target invocation errors giúp nhận diện lỗi định tuyến. Step Functions execution history cho thấy state nào thất bại, retry hoặc timeout. Logs/traces từ Lambda/task cung cấp chi tiết thực thi; CloudTrail cho biết ai đã thay đổi state machine, rule hoặc target.

Khi workflow dài, correlation ID nên tồn tại trong input/output của state machine để liên kết nhiều execution và downstream event.

## 14. Quy trình incident response

### 14.1. Phân loại sự cố

Trước khi sửa, phân loại:

- Availability: service không truy cập được.
- Latency: request chậm.
- Correctness: kết quả sai hoặc dữ liệu trùng/mất.
- Security: truy cập trái phép hoặc thay đổi không mong muốn.
- Capacity: quota, concurrency hoặc queue backlog.
- Configuration: sai endpoint, policy, route hoặc deployment.

Phân loại giúp chọn tín hiệu cần xem đầu tiên.

### 14.2. Xác định phạm vi ảnh hưởng

Ghi nhận:

- Bắt đầu lúc nào và còn tiếp diễn không.
- Region/account/environment.
- Service và operation.
- Số request/tenant/device bị ảnh hưởng.
- Tỷ lệ lỗi và latency.
- Dữ liệu có mất hoặc bị nhân bản không.
- Có thay đổi deploy/configuration gần thời điểm đó không.

Tránh đưa kết luận nguyên nhân khi mới chỉ biết triệu chứng.

### 14.3. Dựng timeline

Chuẩn hóa thời gian về UTC. Đối chiếu:

- Alert timestamp.
- API access log.
- Application log.
- Trace span time.
- CloudTrail eventTime.
- Deployment/build event.
- Queue/database metrics.

Đồng hồ của thiết bị hoặc máy chủ có thể lệch; ưu tiên timestamp do dịch vụ quản lý ghi nhận và ghi riêng thời gian đo từ client.

### 14.4. Xác minh giả thuyết

Một giả thuyết tốt có thể kiểm tra được. Ví dụ: “Lỗi bắt đầu sau khi execution role mất quyền đọc secret”. Bằng chứng cần gồm:

- Log AccessDenied cho đúng secret ARN.
- Trace chỉ ra call tới Secrets Manager thất bại.
- CloudTrail có thay đổi policy hoặc role trước đó.
- Policy hiện tại thiếu action/resource cần thiết.
- Khôi phục quyền tối thiểu làm lỗi biến mất trong test/smoke.

Nếu thiếu một phần, ghi rõ mức độ chắc chắn và tiếp tục thu thập dữ liệu.

### 14.5. Khắc phục và xác minh

Sau khi sửa:

1. Chạy smoke test trên luồng bị ảnh hưởng.
2. Theo dõi metric error/latency.
3. Kiểm tra trace và log của request mới.
4. Xác minh không phát sinh lỗi phụ.
5. Kiểm tra backlog hoặc dữ liệu tồn đọng.
6. Xác nhận người dùng đã phục hồi.
7. Ghi lại thay đổi và bằng chứng.

Không đóng incident chỉ vì alarm chuyển OK; kiểm tra business outcome và dữ liệu.

## 15. Bảo mật và quyền truy cập observability data

### 15.1. Log và trace cũng là dữ liệu nhạy cảm

Log có thể chứa request payload, customer identifier, token, URL query string hoặc stack trace. Trace có thể chứa SQL statement, HTTP header hoặc annotation. CloudTrail có thể chứa principal ARN, IP address và request parameters.

Áp dụng:

- Data classification.
- Redaction trước khi ghi log.
- Encryption at rest và in transit.
- IAM least privilege.
- Retention theo mục đích.
- Audit truy cập log và trace.
- Tách quyền vận hành và quyền xem dữ liệu nhạy cảm.

### 15.2. Tránh ghi secret

Không ghi:

- Password, access key, session token.
- Authorization header hoặc cookie.
- Private key và certificate private material.
- Nội dung secret manager.
- PII không cần cho troubleshooting.

Nếu cần định danh người dùng, dùng internal subject ID đã pseudonymize. Nếu cần payload để debug, tạo bản đã mask trong test environment.

### 15.3. IAM cho CloudWatch và X-Ray

Cấp quyền đọc log, query Logs Insights, xem metric, alarm và trace theo service/team. Quyền tạo subscription filter, thay retention, xóa log group hoặc sửa alarm có thể ảnh hưởng bằng chứng và vận hành; không cấp rộng cho mọi developer.

CloudTrail data có thể tập trung ở account log archive riêng. Hạn chế quyền xóa bucket, sửa bucket policy hoặc thay đổi lifecycle; dùng organization trail và control phù hợp nếu yêu cầu audit toàn tổ chức.

### 15.4. Retention và archive

Chọn retention theo:

- Thời gian cần điều tra sự cố.
- Quy định audit/compliance.
- Chi phí lưu trữ và truy vấn.
- Tần suất truy cập.
- Mức độ nhạy cảm.

Log vận hành có thể giữ ngắn hơn audit event. Có thể archive CloudWatch Logs sang S3 qua subscription/export pattern hoặc dùng CloudTrail trail trực tiếp tới S3. Xác định cách truy vấn lại dữ liệu archive và quyền giải mã KMS.

### 15.5. Sampling và data minimization

Sampling trace và giảm log verbosity giúp giảm chi phí. Tuy nhiên, không bỏ mất error event quan trọng. Có thể:

- Giữ error log đầy đủ.
- Sample trace theo tỷ lệ với request thành công.
- Ưu tiên trace lỗi hoặc latency cao nếu dùng tail sampling.
- Dùng metric cho xu hướng tổng thể.
- Chỉ lưu payload tối thiểu.

## 16. Chi phí observability và FinOps

### 16.1. Nguồn chi phí

Chi phí có thể đến từ:

- CloudWatch Logs ingestion và storage.
- Logs Insights query scan.
- Custom metrics và high-cardinality dimensions.
- Alarm và dashboard ở quy mô lớn.
- X-Ray trace ingestion/retrieval.
- OpenTelemetry collector compute và network.
- CloudTrail data events, CloudTrail Lake ingestion/retention/query.
- S3 archive và request.
- KMS request và data transfer.

Giá phụ thuộc Region, volume, retention và lựa chọn tính năng. Dùng AWS Pricing Calculator và billing/CUR để đo chi phí thực tế.

### 16.2. Giảm chi phí log

- Dùng structured logs nhưng chỉ ghi field cần thiết.
- Không để DEBUG ở production liên tục.
- Đặt retention cho từng log group.
- Lọc hoặc giảm log noise ở application.
- Tránh log toàn bộ payload và response.
- Chỉ bật verbose logging trong khoảng điều tra có kiểm soát.

### 16.3. Giảm chi phí metric

- Hạn chế dimension cardinality cao.
- Dùng metric aggregation phù hợp.
- Không tạo metric mới cho mỗi request/user.
- Xóa metric không còn dùng theo quy trình.
- Thiết kế dashboard chỉ truy vấn metric cần thiết.

### 16.4. Giảm chi phí trace

- Cấu hình sampling theo traffic và mức độ quan trọng.
- Không tạo span cho operation quá nhỏ nếu không có giá trị.
- Tránh attribute có cardinality rất cao.
- Kiểm tra collector batching và retry.
- Dùng trace lỗi/chậm để điều tra sâu, metric để theo dõi tổng thể.

### 16.5. CloudTrail coverage và chi phí

Data events có thể tạo volume lớn. Chỉ bật selector cho bucket, prefix, function hoặc loại resource cần audit. CloudTrail Lake cần retention và query pattern có chủ đích. Không tắt audit bắt buộc chỉ để giảm chi phí; thay vào đó giới hạn phạm vi, lưu trữ và quyền truy cập đúng yêu cầu.

### 16.6. Cost per incident

Có thể theo dõi chi phí observability theo service hoặc team và so sánh với thời gian điều tra, số incident và thời gian phục hồi. Mục tiêu không phải giảm dữ liệu bằng mọi giá mà là giữ đủ bằng chứng để phát hiện và giải quyết sự cố trong thời gian yêu cầu.

## 17. Ví dụ thực hành: điều tra checkout API

### 17.1. Kiến trúc

Checkout API dùng API Gateway, Lambda, DynamoDB, EventBridge và SQS. Lambda ghi đơn hàng, phát event; consumer gọi payment provider và cập nhật trạng thái. CloudWatch thu log/metric, X-Ray theo dõi trace và CloudTrail ghi nhận thay đổi cấu hình AWS.

~~~mermaid
flowchart TB
    U[Customer] --> A[API Gateway]
    A --> L[Checkout Lambda]
    L --> D[(DynamoDB Orders)]
    L --> E[EventBridge]
    E --> Q[SQS Payment Queue]
    Q --> P[Payment Worker]
    P --> X[Payment Provider]
    P --> D
    A -. request ID .-> C[Correlation ID]
    L -. structured logs .-> CW[CloudWatch]
    P -. structured logs .-> CW
    L -. spans .-> XR[X-Ray / OTel]
    P -. spans .-> XR
    AWS[AWS configuration API] --> CT[CloudTrail]
    CW --> INV[Incident investigation]
    XR --> INV
    CT --> INV
~~~

### 17.2. Chuẩn hóa log

Mỗi service ghi:

- service và environment.
- correlation_id.
- trace_id và span_id khi có.
- request_id hoặc message_id.
- order_id.
- operation và outcome.
- duration_ms.
- deployment_id.

Payment worker ghi thêm SQS receive count và event ID nhưng không log payment credential hoặc card data.

### 17.3. Tạo metric

Business metrics:

- checkout_started.
- checkout_succeeded.
- checkout_failed.
- payment_authorization_latency.
- orders_waiting_for_payment.

Technical metrics:

- API 5xx.
- Lambda Errors/Duration/Throttles.
- SQS ApproximateAgeOfOldestMessage.
- DynamoDB ThrottledRequests.
- Payment provider latency/error rate.

### 17.4. Tình huống lỗi

Giả sử checkout trả 500 trong khi metric payment provider bình thường:

1. CloudWatch alarm báo API 5xx.
2. Logs Insights tìm correlation ID của một request thất bại.
3. Log chỉ ra Lambda bị AccessDenied khi ghi EventBridge.
4. Trace cho thấy DynamoDB write thành công nhưng PutEvents thất bại.
5. CloudTrail cho thấy event bus resource policy vừa được cập nhật.
6. Xác minh policy không còn cho phép role của Checkout Lambda.
7. Khôi phục quyền events:PutEvents trên đúng event bus.
8. Smoke test tạo một order test và xác nhận consumer nhận event.
9. Theo dõi error rate, queue age và business success metric.

Trường hợp này cho thấy log cung cấp error code, trace cho biết vị trí lỗi trong request, CloudTrail cho biết thay đổi cấu hình và metric xác nhận tác động trên diện rộng.

## 18. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ bật application logs | Không biết xu hướng và dependency latency | Kết hợp logs, metrics và traces |
| Mỗi service tự tạo correlation ID | Không nối được một nghiệp vụ | Propagate correlation context qua HTTP/event |
| Nhầm request ID với trace ID | Tìm sai bản ghi hoặc trace | Lưu riêng từng loại ID |
| Log dạng text không cấu trúc | Khó lọc và thống kê | Dùng JSON structured logging |
| Log toàn bộ request/response | Lộ PII/secret và tăng chi phí | Redaction và data minimization |
| Dùng user ID làm metric dimension | Cardinality và chi phí tăng | Đưa ID vào log/trace, giữ dimension có tập giá trị hữu hạn |
| Bật tracing nhưng không kiểm tra propagation | Trace bị đứt giữa service | Kiểm thử trace context xuyên hệ thống |
| Sampling quá thấp | Bỏ lỡ lỗi hiếm | Kết hợp error log/metric và điều chỉnh sampling |
| Dùng CloudTrail thay application log | Không biết chi tiết xử lý nghiệp vụ | Dùng CloudTrail cho audit, logs cho app |
| Không bật data event cần thiết | Không thấy object-level activity | Cấu hình selector cho resource quan trọng |
| Xem event history là audit archive | Mất khả năng tra cứu dài hạn | Dùng trail hoặc CloudTrail Lake theo retention |
| Kết luận nguyên nhân chỉ từ timeline | Nhầm tương quan với quan hệ nhân quả | Xác minh bằng request, resource, policy và thử nghiệm |
| Retention vô thời hạn | Chi phí và rủi ro dữ liệu tăng | Đặt retention/archive theo mục đích |

## 19. Checklist triển khai observability

### Thiết kế

1. Xác định service owner, SLO và các luồng nghiệp vụ quan trọng.
2. Chọn log schema và field định danh thống nhất.
3. Phân biệt request ID, correlation ID, trace ID và event ID.
4. Thiết kế trace propagation qua HTTP, queue và workflow.
5. Chọn metric và dimensions có cardinality hợp lý.
6. Xác định CloudTrail management/data event coverage.
7. Phân loại dữ liệu và đặt retention.

### Triển khai

1. Ghi structured logs với UTC timestamp.
2. Bật CloudWatch metrics, dashboard và alarms.
3. Instrument trace bằng X-Ray hoặc OpenTelemetry/ADOT.
4. Kiểm thử propagation qua service boundaries.
5. Tạo CloudTrail trail/event data store theo yêu cầu audit.
6. Kiểm thử Logs Insights và truy vấn audit.
7. Thiết lập quyền đọc observability data theo least privilege.

### Vận hành

1. Bắt đầu từ alarm và xác định phạm vi ảnh hưởng.
2. Tìm log theo correlation/request ID.
3. Mở trace để xác định dependency hoặc span lỗi.
4. Đối chiếu metric và queue/database health.
5. Tìm CloudTrail event cho thay đổi gần thời điểm sự cố.
6. Dựng timeline và xác minh giả thuyết.
7. Khắc phục, chạy smoke test và theo dõi metric.
8. Lưu incident evidence và cập nhật runbook.
9. Rà soát retention, sampling và chi phí định kỳ.

## 20. Kết luận

Logs, metrics và traces trả lời các câu hỏi khác nhau: log cho biết sự kiện chi tiết, metric thể hiện xu hướng và mức độ, trace mô tả đường đi của request. AWS CloudTrail bổ sung bằng chứng audit về principal và hoạt động API đối với tài nguyên AWS. Khi ứng dụng dùng structured logging, correlation ID và trace context nhất quán, kỹ sư có thể đi từ alarm đến request cụ thể, xác định dependency lỗi rồi đối chiếu với thay đổi cấu hình.

CloudWatch cung cấp nơi tập trung log, metric, alarm, dashboard và truy vấn; X-Ray và OpenTelemetry giúp phân tích distributed trace; CloudTrail hỗ trợ điều tra thay đổi và hoạt động API. Mỗi công cụ cần được cấu hình đúng coverage, quyền, sampling và retention. Không có event trong CloudTrail chưa chắc không có thay đổi nếu loại event chưa được ghi; không có trace chưa chắc request không chạy nếu sampling hoặc propagation chưa đầy đủ.

Một quy trình điều tra hiệu quả bắt đầu từ triệu chứng, xác định phạm vi, tìm log theo định danh, mở trace, kiểm tra metric và đối chiếu CloudTrail theo timeline. Sau khi sửa, cần xác minh bằng smoke test, business metric và dữ liệu mới. Khi thiết kế observability theo cách này, hệ thống AWS dễ chẩn đoán hơn, thời gian phục hồi ngắn hơn và chi phí quan sát được kiểm soát tốt hơn.

## 21. Tài liệu tham khảo chính thức

- [Amazon CloudWatch documentation](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/WhatIsCloudWatch.html)
- [CloudWatch Logs Insights query syntax](https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html)
- [CloudWatch Embedded Metric Format](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch_Embedded_Metric_Format.html)
- [CloudWatch Application Signals](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Application-Monitoring-Sections.html)
- [AWS X-Ray concepts](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html)
- [AWS X-Ray trace header](https://docs.aws.amazon.com/xray/latest/devguide/xray-concepts.html#xray-concepts-tracingheader)
- [AWS Distro for OpenTelemetry](https://aws-otel.github.io/)
- [OpenTelemetry documentation](https://opentelemetry.io/docs/)
- [AWS CloudTrail user guide](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-user-guide.html)
- [CloudTrail event history](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/view-cloudtrail-events.html)
- [CloudTrail data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html)
- [CloudTrail Lake](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-lake.html)
- [CloudTrail log file integrity validation](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-log-file-validation-intro.html)
- [AWS Well-Architected Framework – Operational Excellence](https://docs.aws.amazon.com/wellarchitected/latest/operational-excellence-pillar/welcome.html)
