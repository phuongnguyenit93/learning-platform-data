# Theo dõi Lambda bằng CloudWatch, X-Ray và Lambda Insights

Trong chương **Tích hợp serverless trên AWS**, khả năng quan sát (observability) giúp nhóm vận hành hiểu function đang làm gì, xử lý request mất bao lâu và lỗi xuất hiện ở đâu. Một Lambda có thể chạy thành công ở một lần gọi nhưng thất bại ở lần khác do cold start, dependency chậm, giới hạn concurrency hoặc message được giao lại. Nếu chỉ xem log rời rạc, rất khó nối các dấu hiệu thành nguyên nhân.

AWS cung cấp nhiều công cụ quan sát có vai trò bổ trợ nhau:

- **Amazon CloudWatch** tập trung log, metric, dashboard và alarm.
- **AWS X-Ray** theo dõi đường đi của request qua function và các dịch vụ phụ thuộc.
- **Lambda Insights** bổ sung metric hệ thống và hiệu năng ở cấp execution environment.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học cần theo dõi trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để quyết định cách vận hành FaaS. Bài này kết hợp log, metric và trace thành một quy trình chẩn đoán có thể áp dụng cho Java Lambda trong production.

## 1. Observability: log, metric và trace

Ba loại tín hiệu quan sát trả lời ba câu hỏi khác nhau:

| Tín hiệu | Trả lời câu hỏi | Ví dụ |
|---|---|---|
| Log | Điều gì đã xảy ra trong một lần xử lý? | Request thiếu customerId, database timeout |
| Metric | Hệ thống đang hoạt động ở mức nào theo thời gian? | Error rate, duration p95, concurrency |
| Trace | Một request đi qua những thành phần nào và chậm ở đâu? | API Gateway → Lambda → database → event bus |

Không tín hiệu nào thay thế được hai loại còn lại. Log giải thích chi tiết một sự kiện nhưng khó phát hiện xu hướng nếu không tổng hợp. Metric cho thấy lỗi tăng nhưng không nhất thiết chỉ ra nguyên nhân. Trace thể hiện quan hệ giữa các bước nhưng chỉ hữu ích khi trace context được truyền qua các ranh giới và có đủ dữ liệu được lấy mẫu.

~~~mermaid
flowchart TD
    INV["Lambda invocation"] --> LOG["CloudWatch Logs"]
    INV --> MET["CloudWatch Metrics"]
    INV --> TRACE["AWS X-Ray trace"]
    INV --> INS["Lambda Insights extension"]
    LOG --> DASH["Dashboard / Alarm / Logs Insights"]
    MET --> DASH
    TRACE --> MAP["Trace map / latency analysis"]
    INS --> DASH
    MAP --> FIX["Chẩn đoán và cải thiện"]
    DASH --> FIX
~~~

Một quy trình quan sát tốt phải liên kết được các tín hiệu bằng function name, version, request ID, event ID, correlation ID và trace ID. Khi một cảnh báo xuất hiện, người trực có thể đi từ metric đến log, từ log đến invocation cụ thể, rồi mở trace để xem dependency nào gây chậm.

## 2. CloudWatch Logs cho Lambda

### 2.1. Log group và log stream

Với cấu hình mặc định, Lambda gửi log của function vào CloudWatch Logs. Log group thường có tên:

~~~text
/aws/lambda/<function-name>
~~~

Mỗi execution environment hoặc lần khởi tạo có thể tạo log stream riêng. Một function có nhiều stream khi được scale ra nhiều environment. Vì vậy, không nên giả định toàn bộ log của một function nằm trong một file hoặc một stream duy nhất.

Để function ghi log, execution role cần quyền CloudWatch Logs tương ứng, thường gồm:

- logs:CreateLogGroup
- logs:CreateLogStream
- logs:PutLogEvents

Có thể cấp qua policy AWS được quản lý phù hợp hoặc policy tùy chỉnh theo log group cần dùng. Không cấp quyền quản trị CloudWatch rộng hơn mức cần thiết. Nếu log group đã được tạo sẵn bằng IaC, có thể giới hạn quyền tạo log group tùy cách triển khai.

### 2.2. Log có cấu trúc

Log dạng văn bản tự do khó lọc khi hệ thống có nhiều function. Nên ghi log có cấu trúc, thường là JSON, với các trường nhất quán:

- timestamp: thời điểm ghi log.
- level: INFO, WARN, ERROR hoặc DEBUG.
- message: mô tả ngắn.
- functionName và functionVersion.
- requestId: ID invocation do Lambda cung cấp.
- correlationId hoặc eventId: định danh nghiệp vụ.
- operation: tên thao tác.
- durationMs: thời gian thực hiện nếu có.
- errorCode: mã lỗi ổn định, không phụ thuộc stack trace.

Ví dụ log:

~~~json
{
  "level": "INFO",
  "message": "Order accepted",
  "function": "place-order",
  "requestId": "7b6f4d2a-example",
  "correlationId": "checkout-2026-001",
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "durationMs": 84
}
~~~

Không nên đưa password, token, session cookie, dữ liệu thanh toán hoặc toàn bộ payload chứa thông tin cá nhân vào log. Log thường được tập trung, lưu giữ và cấp quyền cho nhiều nhóm; chỉ ghi dữ liệu tối thiểu cần để điều tra.

### 2.3. Ghi log trong Java Lambda

Java Lambda có thể dùng Lambda Logger, SLF4J với backend logging phù hợp hoặc framework logging của ứng dụng. Ví dụ sau ghi JSON bằng Jackson để minh họa cấu trúc log:

~~~java
import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.LambdaLogger;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

public final class OrderHandler {
    private static final ObjectMapper JSON = new ObjectMapper();

    public OrderResult handleRequest(OrderEvent event, Context context) {
        LambdaLogger logger = context.getLogger();

        try {
            OrderResult result = process(event);

            logger.log(toJson(Map.of(
                    "level", "INFO",
                    "message", "Order accepted",
                    "requestId", context.getAwsRequestId(),
                    "orderId", result.orderId())) + "\n");

            return result;
        } catch (RuntimeException failure) {
            logger.log(toJson(Map.of(
                    "level", "ERROR",
                    "message", "Order processing failed",
                    "requestId", context.getAwsRequestId(),
                    "errorType", failure.getClass().getSimpleName())) + "\n");
            throw failure;
        }
    }

    private String toJson(Object value) {
        try {
            return JSON.writeValueAsString(value);
        } catch (Exception serializationFailure) {
            return "{\"level\":\"ERROR\",\"message\":\"Log serialization failed\"}";
        }
    }

    private OrderResult process(OrderEvent event) {
        // Gọi use case nghiệp vụ tại đây.
        return new OrderResult(event.orderId(), "ACCEPTED");
    }
}
~~~

Các kiểu OrderEvent và OrderResult là DTO minh họa. Trong ứng dụng thật, nên cấu hình logging framework một lần, tránh tạo ObjectMapper mới trong mỗi invocation và bảo đảm logger không ghi dữ liệu nhạy cảm. Nếu dùng logging framework, có thể cấu hình JSON encoder hoặc structured logging theo khả năng của runtime và framework.

Lambda cũng có thể cấu hình định dạng log hệ thống và mức log cho một số runtime được hỗ trợ. Hãy kiểm tra khả năng của runtime Java và framework đang dùng; không giả định mọi logger tự động phát JSON chỉ vì ứng dụng ghi chuỗi JSON.

### 2.4. Log retention

CloudWatch Logs có chính sách lưu giữ theo log group. Nếu không cấu hình retention, log có thể tiếp tục được lưu cho đến khi bị xóa thủ công. Điều này gây phát sinh chi phí và có thể không phù hợp chính sách dữ liệu.

Nên chọn retention dựa trên:

- Thời gian cần điều tra sự cố.
- Yêu cầu kiểm toán và tuân thủ.
- Mức độ nhạy cảm của dữ liệu.
- Chi phí ingest và lưu trữ.
- Nhu cầu export sang kho lưu trữ dài hạn.

Có thể dùng IaC để tạo log group và đặt retention trước khi function chạy. Không dùng log làm kho lưu trữ nghiệp vụ lâu dài.

## 3. Tìm log bằng CloudWatch Logs Insights

CloudWatch Logs Insights cho phép truy vấn log theo trường, từ khóa và khoảng thời gian. Với JSON log, các trường có thể được trích xuất tự động để lọc và tổng hợp.

Ví dụ tìm lỗi gần đây:

~~~sql
fields @timestamp, level, message, requestId, errorType
| filter level = "ERROR"
| sort @timestamp desc
| limit 50
~~~

Tìm các request chậm nếu ứng dụng ghi durationMs:

~~~sql
fields @timestamp, requestId, operation, durationMs
| filter durationMs >= 1000
| sort durationMs desc
| limit 30
~~~

Đếm lỗi theo loại:

~~~sql
fields errorType
| filter level = "ERROR"
| stats count() as failures by errorType
| sort failures desc
~~~

Tìm các invocation theo correlation ID:

~~~sql
fields @timestamp, @message, requestId, correlationId, eventId
| filter correlationId = "checkout-2026-001"
| sort @timestamp asc
~~~

Tên trường phải khớp với định dạng log thực tế. Nếu log là text thuần, cần dùng parser hoặc biểu thức phù hợp. Truy vấn quá rộng trên khoảng thời gian lớn có thể tốn thời gian và chi phí; hãy giới hạn time range và log group khi điều tra.

## 4. CloudWatch Metrics quan trọng của Lambda

CloudWatch nhận các metric tiêu chuẩn trong namespace **AWS/Lambda**. Metric cho biết function đang nhận bao nhiêu invocation, có lỗi hay bị throttling, chạy trong bao lâu và dùng bao nhiêu concurrency.

| Metric | Ý nghĩa | Dùng để theo dõi |
|---|---|---|
| Invocations | Số lần function được gọi | Lưu lượng và xu hướng tải |
| Errors | Số invocation kết thúc với lỗi function/runtime | Error rate |
| Duration | Thời gian thực thi handler/invocation theo cách đo của Lambda | Độ trễ, p95/p99 |
| Throttles | Số lần invocation bị từ chối do giới hạn concurrency | Áp lực concurrency |
| ConcurrentExecutions | Số invocation đang chạy đồng thời | Mức sử dụng concurrency |
| UnreservedConcurrentExecutions | Concurrency đang dùng ngoài phần provisioned reservation | Theo dõi mức concurrency cấp account |
| ProvisionedConcurrencyUtilization | Mức sử dụng provisioned concurrency | Điều chỉnh cấu hình provisioned |
| AsyncEventAge | Tuổi của event bất đồng bộ khi Lambda xử lý | Độ trễ backlog |
| AsyncEventsDropped | Số event bất đồng bộ bị loại bỏ | Sự cố giao nhận hoặc hết retry |
| IteratorAge | Độ trễ record trong stream so với thời điểm được đọc | Backlog của stream consumer |

Metric có thể xuất hiện với tập dimension khác nhau, ví dụ FunctionName, Resource hoặc ExecutedVersion. Khi tạo alarm, cần chọn dimension phù hợp với mục tiêu: toàn function, alias hoặc version cụ thể.

### 4.1. Errors và error rate

Chỉ nhìn số Errors có thể gây hiểu nhầm nếu lưu lượng thay đổi. Một function có 10 lỗi trong 100 invocation có tỷ lệ lỗi khác với 10 lỗi trong 100.000 invocation.

Có thể theo dõi tỷ lệ:

\[
ErrorRate = \frac{Errors}{Invocations} \times 100\%
\]

Khi triển khai alarm, cần tránh chia cho 0 ở thời điểm không có invocation. Có thể dùng metric math hoặc theo dõi cả số lỗi tuyệt đối và tỷ lệ lỗi.

Throttles cần được theo dõi riêng. Invocation bị throttle không giống invocation đã chạy rồi ném exception. Với queue/event source mapping, throttling có thể làm backlog tăng và tuổi message lớn hơn.

### 4.2. Duration và percentile

Duration thường được tổng hợp bằng các thống kê như Average, Maximum và percentile. Average có thể che khuất một nhóm request rất chậm. Với API nhạy độ trễ, theo dõi p95 hoặc p99 giúp phát hiện tail latency.

Metric Duration phản ánh thời gian thực thi function, không bao gồm toàn bộ giai đoạn khởi tạo execution environment. Với cold start, xem thêm trường Init Duration trong dòng REPORT của CloudWatch Logs hoặc telemetry khởi tạo do công cụ quan sát hỗ trợ. Nếu chỉ nhìn Duration, nhóm vận hành có thể bỏ sót phần chậm xảy ra trước khi handler bắt đầu chạy.

Không nên đặt một ngưỡng duration giống nhau cho mọi function. Ngưỡng cần dựa trên SLA, timeout function, thời gian xử lý bình thường và đặc tính của trigger. Một batch consumer có thể có duration dài hơn một HTTP handler đơn giản nhưng vẫn hoạt động đúng.

### 4.3. Metric đặc thù trigger

Với function xử lý queue hoặc stream, cần xem thêm metric của nguồn:

- ApproximateAgeOfOldestMessage hoặc metric tương đương của queue.
- ApproximateNumberOfMessagesVisible và số message đang chờ.
- IteratorAge đối với stream event source mapping.
- DLQ depth hoặc số message chuyển sang dead-letter.
- Batch failure và số lần retry theo khả năng nền tảng.

Một function có Errors thấp nhưng tuổi message tăng liên tục vẫn có thể đang không theo kịp tải. Observability cần theo dõi cả function lẫn hệ thống phát message.

## 5. Custom metrics và Embedded Metric Format

Metric tiêu chuẩn của Lambda không biết các khái niệm nghiệp vụ như số đơn được chấp nhận, số thanh toán thất bại hoặc số lần giữ hàng bị từ chối. Ứng dụng có thể phát custom metrics để theo dõi các kết quả đó.

CloudWatch Embedded Metric Format (EMF) cho phép ghi một JSON log có metadata metric; CloudWatch xử lý log đó và trích xuất metric.

Ví dụ EMF:

~~~json
{
  "_aws": {
    "Timestamp": 1763374530000,
    "CloudWatchMetrics": [
      {
        "Namespace": "Orders/Serverless",
        "Dimensions": [["Service", "Function"]],
        "Metrics": [
          {"Name": "OrdersAccepted", "Unit": "Count"},
          {"Name": "ProcessingLatency", "Unit": "Milliseconds"}
        ]
      }
    ]
  },
  "Service": "orders",
  "Function": "place-order",
  "OrdersAccepted": 1,
  "ProcessingLatency": 84
}
~~~

Các dimension nên có số lượng giá trị hữu hạn. Không dùng orderId, requestId, email hoặc userId làm dimension vì mỗi giá trị tạo một chuỗi metric riêng, làm tăng cardinality và chi phí. Định danh từng invocation nên nằm trong log hoặc trace.

Custom metric có thể hữu ích để xây dashboard nghiệp vụ, ví dụ tỷ lệ đơn thành công hoặc số event bị từ chối. Chỉ phát metric khi có câu hỏi vận hành cụ thể; tránh tạo metric trùng lặp với metric tiêu chuẩn.

## 6. Dashboard và alarm

### 6.1. Dashboard theo góc nhìn vận hành

Một dashboard Lambda nên giúp trả lời nhanh:

- Function có đang nhận tải như bình thường không?
- Error rate và throttling có tăng không?
- Duration p95/p99 có vượt mục tiêu không?
- Concurrency có gần giới hạn không?
- Queue age hoặc iterator age có tăng không?
- Cold start, memory và CPU có bất thường không?
- Function version nào bắt đầu phát sinh lỗi?

Có thể chia dashboard thành các hàng:

1. **Traffic:** Invocations, event count và concurrency.
2. **Reliability:** Errors, throttles, async events dropped và DLQ.
3. **Latency:** Duration p50/p95/p99 và tuổi message.
4. **Resources:** Memory utilization, CPU, network và /tmp từ Lambda Insights.
5. **Dependencies:** Database latency, timeout, external API errors và trace duration.

### 6.2. Alarm theo mục tiêu dịch vụ

Alarm nên gắn với hành động cụ thể. Ví dụ:

- Error rate vượt ngưỡng trong nhiều chu kỳ.
- Throttles xuất hiện liên tục.
- Duration p95 vượt SLA.
- Queue age hoặc IteratorAge tăng quá mức cho phép.
- DLQ có message mới.
- ConcurrentExecutions tiến gần quota hoặc reserved concurrency.
- AsyncEventsDropped lớn hơn 0.

Không đặt alarm chỉ vì một metric khác 0 nếu điều đó là bình thường. Ví dụ Errors có thể tăng nhẹ trong một workload có đầu vào không hợp lệ; cần phân biệt lỗi nghiệp vụ dự kiến và lỗi hệ thống.

Ví dụ tạo alarm theo số Errors:

~~~bash
aws cloudwatch put-metric-alarm \
  --alarm-name place-order-errors \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=place-order \
  --statistic Sum \
  --period 60 \
  --evaluation-periods 3 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions arn:aws:sns:ap-southeast-1:123456789012:ops-alerts
~~~

Ví dụ dùng ngưỡng minh họa, không phải cấu hình phù hợp cho mọi workload. Với function ít invocation, một lỗi đơn lẻ có thể đáng chú ý; với function xử lý hàng triệu message, cần dùng tỷ lệ lỗi hoặc metric theo nhóm lỗi.

### 6.3. Missing data

Không có metric trong một khoảng thời gian có thể nghĩa là function không được gọi, metric chưa được phát hoặc pipeline telemetry gặp vấn đề. Chọn treatMissingData theo mục tiêu:

- notBreaching nếu không có invocation là trạng thái bình thường.
- breaching nếu không có metric cũng có thể biểu thị hệ thống ngừng hoạt động.
- ignore hoặc missing khi cần giữ trạng thái alarm trước đó.

Không áp dụng cùng một chính sách missing data cho mọi metric. Ví dụ, metric traffic không có dữ liệu có thể bình thường vào ban đêm, nhưng metric heartbeat của một tác vụ bắt buộc chạy mỗi phút thì khác.

## 7. AWS X-Ray và distributed tracing

CloudWatch cho biết một function chậm hoặc lỗi; X-Ray giúp xác định request đã đi qua những thành phần nào và thời gian tiêu tốn ở từng chặng.

Một trace có thể gồm:

- **Trace:** toàn bộ hành trình của một request hoặc quy trình.
- **Segment:** phần công việc của một service, chẳng hạn Lambda function.
- **Subsegment:** thao tác con như gọi database, HTTP API hoặc AWS service.
- **Trace ID:** định danh chung để liên kết các segment.
- **Parent ID:** quan hệ cha-con giữa các đoạn xử lý.

Ví dụ luồng đặt hàng:

~~~mermaid
flowchart LR
    C["Client"] --> A["API Gateway"]
    A --> L["Order Lambda"]
    L --> D["Database"]
    L --> E["EventBridge"]
    E --> I["Inventory Lambda"]
    I --> S["Inventory database"]
~~~

Trong X-Ray service map, có thể quan sát các node và cạnh đại diện cho service cùng lời gọi giữa chúng. Trace timeline giúp xác định thời gian ở Lambda, database hoặc HTTP dependency.

X-Ray không tự động biết mọi thao tác nội bộ. Cần instrument code hoặc dùng integration/instrumentation phù hợp để tạo subsegment/span cho dependency.

## 8. Bật active tracing cho Lambda

Lambda có cấu hình tracing mode. Khi bật Active tracing, Lambda tích hợp với X-Ray để thu thập trace cho invocation theo cơ chế lấy mẫu của dịch vụ.

Có thể bật trong console hoặc qua AWS CLI:

~~~bash
aws lambda update-function-configuration \
  --function-name place-order \
  --tracing-config Mode=Active
~~~

Execution role cần quyền ghi trace. Có thể dùng policy AWS được quản lý phù hợp, thường là AWSXRayDaemonWriteAccess, hoặc policy tối thiểu gồm các hành động cần thiết như xray:PutTraceSegments và xray:PutTelemetryRecords theo mô hình triển khai.

Khi tracing ở chế độ Active, Lambda có thể tạo segment cho invocation. Code được instrument có thể bổ sung thông tin về thao tác con. Với PassThrough, function không chủ động yêu cầu Lambda ghi trace; hành vi nhận trace context còn tùy cách caller và integration truyền dữ liệu.

Bật active tracing không có nghĩa mọi request đều được ghi đầy đủ. X-Ray sử dụng sampling để giới hạn lượng trace được thu thập. Khi điều tra lỗi hiếm, cần cân nhắc sampling rule, metric và log để tránh phụ thuộc vào việc một request cụ thể có được lấy mẫu hay không.

## 9. Trace context và truyền qua ranh giới bất đồng bộ

Distributed tracing chỉ hữu ích khi context được truyền từ service này sang service khác. Với HTTP, trace context có thể đi qua header. Với queue hoặc event bus, context cần được truyền bằng message attribute, envelope extension hoặc cơ chế tracing mà integration hỗ trợ.

Các định danh có vai trò khác nhau:

- **Trace ID:** liên kết các span trong cùng một trace.
- **Correlation ID:** liên kết các bước nghiệp vụ, kể cả khi chúng không nằm trong một trace liên tục.
- **Event ID:** định danh một sự kiện cụ thể.
- **Request ID:** định danh một invocation cụ thể của Lambda.

Không thay thế tất cả bằng một ID duy nhất. Một quy trình nghiệp vụ có thể kéo dài nhiều giờ, qua nhiều lần retry và nhiều trace khác nhau; correlation ID có thể ổn định hơn trace ID.

Với asynchronous invocation, queue hoặc stream, khả năng nối trace tự động phụ thuộc integration và loại event source. Nếu cần giữ liên kết, hãy truyền trace context một cách tường minh và kiểm tra bằng trace thực tế. Không giả định mọi event bus hoặc queue đều duy trì một trace duy nhất qua mọi retry và replay.

## 10. Instrument Java bằng OpenTelemetry

Java function có thể được instrument bằng OpenTelemetry (OTel) để tạo span và truyền trace context. AWS Distro for OpenTelemetry (ADOT) cung cấp các thành phần và cách tích hợp phù hợp với hệ sinh thái AWS.

Có thể instrument ở các lớp:

- Handler: span bao quanh một invocation hoặc use case.
- HTTP client: span cho request đến dịch vụ ngoài.
- AWS SDK: instrumentation cho lời gọi AWS service nếu phiên bản và cấu hình hỗ trợ.
- JDBC: instrumentation cho thao tác database nếu driver/instrumentation tương thích.
- Message producer/consumer: inject và extract trace context qua message.

Ví dụ khái niệm tạo span với OpenTelemetry API:

~~~java
import io.opentelemetry.api.GlobalOpenTelemetry;
import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.Tracer;

public final class OrderUseCase {
    private static final Tracer TRACER =
            GlobalOpenTelemetry.getTracer("orders-service");

    public OrderResult execute(OrderCommand command) {
        Span span = TRACER.spanBuilder("OrderUseCase.execute").startSpan();

        try (var scope = span.makeCurrent()) {
            span.setAttribute("order.channel", command.channel());
            return processOrder(command);
        } catch (RuntimeException failure) {
            span.recordException(failure);
            span.setStatus(
                    io.opentelemetry.api.trace.StatusCode.ERROR);
            throw failure;
        } finally {
            span.end();
        }
    }

    private OrderResult processOrder(OrderCommand command) {
        // Logic nghiệp vụ.
        return new OrderResult(command.orderId(), "ACCEPTED");
    }
}
~~~

Ví dụ giả định SDK và exporter đã được cấu hình bởi instrumentation hoặc layer phù hợp. Không tự tạo exporter trong từng invocation. Cần kiểm tra cách triển khai ADOT cho runtime Java, cách đặt wrapper/extension và cấu hình collector theo hướng dẫn AWS hiện hành.

Không nên bật đồng thời nhiều cơ chế instrument cho cùng một thư viện nếu chúng tạo span trùng lặp. Khi dùng auto-instrumentation agent hoặc layer, hãy xác định rõ phần nào được instrument tự động và phần nào cần span thủ công.

## 11. Sampling và chi phí trace

Trace có thể tạo lượng dữ liệu lớn khi function nhận nhiều invocation. Sampling quyết định request nào được ghi chi tiết.

Các cách lấy mẫu thường gặp:

- **Reservoir sampling:** giữ một số lượng mẫu tối thiểu trong một khoảng thời gian.
- **Rate sampling:** lấy một tỷ lệ phần trăm request.
- **Custom sampling rules:** ưu tiên hoặc loại trừ request theo service, resource hoặc thuộc tính phù hợp.

Sampling giúp kiểm soát chi phí và giảm lượng dữ liệu, nhưng có thể bỏ lỡ một request lỗi hiếm. Vì vậy, cần kết hợp trace với metric và log. Metric cho biết lỗi có tăng không; log giữ chi tiết lỗi; trace giúp hiểu dependency của những request đã được lấy mẫu.

Không đặt sampling rate quá cao trong production nếu chưa tính đến lưu lượng và chi phí. Cũng không đặt quá thấp đến mức không có trace hữu ích khi xảy ra sự cố. Hãy đánh giá theo traffic, yêu cầu SLA và khả năng lưu trữ.

## 12. Lambda Insights

Lambda Insights là tiện ích quan sát hiệu năng cho Lambda, bổ sung metric ở cấp execution environment. Nó được triển khai thông qua Lambda extension và layer tương ứng với runtime/kiến trúc, sau đó gửi telemetry đến CloudWatch.

Các loại dữ liệu có thể quan sát gồm:

- Memory đã dùng và mức sử dụng bộ nhớ.
- CPU time và mức hoạt động CPU.
- Network bytes nhận/gửi.
- Dung lượng filesystem tạm thời /tmp.
- Thời gian khởi tạo và thông tin execution environment theo khả năng dịch vụ.
- Một số thông tin hiệu năng khác phục vụ chẩn đoán.

Metric tiêu chuẩn của Lambda không cung cấp đầy đủ memory usage thực tế của từng invocation. Lambda Insights bổ sung góc nhìn này, giúp phát hiện function gần chạm memory limit hoặc sử dụng CPU/network bất thường.

### 12.1. Bật Lambda Insights

Có thể bật Lambda Insights từ console hoặc gắn layer tương ứng. Execution role cần quyền để extension gửi telemetry đến CloudWatch. AWS cung cấp policy được quản lý như **CloudWatchLambdaInsightsExecutionRolePolicy** cho use case này; hãy kiểm tra policy và quyền thực tế trong môi trường của tổ chức.

Layer cần đúng Region, runtime và architecture. Nếu function dùng arm64, phải chọn layer hỗ trợ arm64. Khi triển khai bằng IaC, nên quản lý layer ARN và role policy trong cấu hình thay vì bật thủ công không có dấu vết.

### 12.2. Đọc metric từ Lambda Insights

Ví dụ các câu hỏi có thể trả lời:

- Memory utilization có tiến gần giới hạn cấu hình không?
- CPU time tăng do xử lý payload lớn hay do dependency?
- /tmp có gần đầy do tải file hoặc cache không?
- Network throughput tăng do gọi dịch vụ ngoài?
- Init duration tăng sau khi thêm dependency hoặc layer?

Nếu memory usage thường xuyên gần giới hạn, có thể cần tăng memory hoặc giảm footprint. Với Lambda, cấu hình memory cũng ảnh hưởng lượng CPU được cấp; tăng memory có thể giảm duration và tổng chi phí cho workload CPU-bound, nhưng cần benchmark.

Lambda Insights bổ sung telemetry hệ thống, không thay thế CloudWatch Logs, metric tiêu chuẩn hoặc X-Ray. Nó cũng không tự giải thích logic nghiệp vụ trong code.

## 13. Kết hợp CloudWatch, X-Ray và Lambda Insights

Ba công cụ có thể được dùng theo một luồng điều tra thống nhất:

1. CloudWatch alarm phát hiện Errors hoặc Duration p95 tăng.
2. Dashboard cho biết vấn đề bắt đầu sau khi deploy version mới hoặc khi concurrency tăng.
3. CloudWatch Logs Insights lọc invocation lỗi theo requestId hoặc correlationId.
4. X-Ray mở trace tương ứng để xác định database hoặc HTTP dependency gây chậm.
5. Lambda Insights cho biết memory, CPU, network hoặc /tmp có bất thường không.
6. Nhóm vận hành so sánh với thay đổi cấu hình, dependency và lưu lượng.
7. Sau khi sửa, theo dõi metric và alarm để xác nhận lỗi đã giảm.

Ví dụ: Duration p95 tăng sau khi thêm thư viện xử lý PDF. X-Ray cho thấy thời gian trong Lambda tăng nhưng thời gian gọi database không đổi. Lambda Insights cho thấy CPU time và memory utilization tăng. Logs cho thấy payload file lớn. Từ ba tín hiệu, nhóm phát triển có thể xem xét kích thước file, thuật toán xử lý, memory configuration hoặc chuyển xử lý file lớn sang workflow phù hợp hơn.

## 14. Theo dõi retry, queue và event source mapping

Với Lambda xử lý message, quan sát cần bao gồm cả function lẫn nguồn message. Một function có thể có tỷ lệ Errors thấp nhưng queue backlog vẫn tăng vì concurrency bị giới hạn hoặc batch xử lý chậm.

Cần theo dõi:

- Queue depth và tuổi message lâu nhất.
- AsyncEventAge và AsyncEventsDropped đối với asynchronous invocation.
- IteratorAge với stream event source mapping.
- Số message chuyển DLQ.
- Số lần retry và batch failure theo metric/log của nguồn.
- Throttles và ConcurrentExecutions.
- Duration theo batch size.
- Tỷ lệ message xử lý thành công.

Khi một message lỗi lặp lại, log cần ghi event ID, receive count hoặc attempt metadata nếu trigger cung cấp. Không ghi toàn bộ payload. Dùng idempotency key để tránh xử lý nghiệp vụ trùng khi message được giao lại.

Với stream, IteratorAge tăng có thể chỉ ra consumer không theo kịp tốc độ phát record. Cần xem partition count, batch size, function concurrency, thời gian xử lý và lỗi record. Với queue, tuổi message tăng có thể do backlog, visibility timeout, throttling hoặc dependency chậm.

## 15. Bảo mật và quyền truy cập observability

Log, trace và metric có thể chứa thông tin nhạy cảm hoặc tiết lộ cấu trúc nội bộ. Cần quản lý quyền theo nguyên tắc tối thiểu.

Các điểm cần chú ý:

- Execution role chỉ có quyền ghi log, metric hoặc trace mà function thực sự cần.
- Nhóm vận hành có quyền đọc log và trace theo phạm vi function hoặc account.
- Không cho mọi developer quyền đọc toàn bộ log production nếu không cần.
- Không ghi secret, token, dữ liệu cá nhân hoặc payload thanh toán vào log/span.
- Dùng retention và chính sách lưu trữ phù hợp.
- Bảo vệ dashboard, alarm action và SNS topic nhận cảnh báo.
- Kiểm soát quyền tạo hoặc sửa sampling rule.
- Kiểm tra quyền truy cập dữ liệu trace khi chia sẻ với đội khác.

Nếu dùng X-Ray active tracing, cấp quyền ghi trace cho execution role. Nếu dùng Lambda Insights, thêm quyền telemetry tương ứng cho extension. Quyền ghi log không tự động cấp quyền đọc log; quyền đọc dashboard và truy vấn nên được cấp riêng.

## 16. Chi phí và giới hạn dữ liệu quan sát

Chi phí observability có thể đến từ:

- Log ingestion và log storage.
- Truy vấn CloudWatch Logs Insights.
- Custom metrics và số lượng dimension.
- Dashboard, alarm và metric API theo mô hình tính phí hiện hành.
- X-Ray trace được ghi và truy vấn.
- Lambda Insights telemetry.
- Dữ liệu được export hoặc lưu trữ ở dịch vụ khác.

Có thể kiểm soát chi phí bằng cách:

- Chọn log level phù hợp; hạn chế DEBUG trong production.
- Đặt retention rõ ràng cho từng nhóm log.
- Tránh ghi lặp toàn bộ payload.
- Dùng sampling cho trace.
- Giữ số dimension custom metric ở mức thấp.
- Chỉ tạo dashboard và alarm có mục đích.
- Dùng metric tổng hợp thay vì log mọi thao tác thành metric riêng.
- Đánh giá lượng telemetry sau mỗi lần tăng traffic hoặc bật instrumentation mới.

Không giảm observability đến mức không thể điều tra sự cố. Mục tiêu là thu thập đủ dữ liệu để bảo vệ SLA với chi phí có thể dự đoán.

## 17. Quy trình xây dựng observability cho Java Lambda

Có thể triển khai theo trình tự:

1. **Xác định mục tiêu vận hành:** SLA latency, error rate, throughput, backlog và mức sẵn sàng.
2. **Chuẩn hóa log:** JSON fields, requestId, eventId, correlationId, level và errorCode.
3. **Bật metric tiêu chuẩn:** theo dõi Invocations, Errors, Duration, Throttles và concurrency.
4. **Thêm custom metric cần thiết:** chỉ đo kết quả nghiệp vụ chưa có trong metric tiêu chuẩn.
5. **Tạo dashboard:** traffic, reliability, latency, dependency và resource.
6. **Đặt alarm:** gắn với hành động cụ thể và ngưỡng theo SLO.
7. **Bật X-Ray hoặc OTel:** trace invocation và các dependency quan trọng.
8. **Truyền trace context:** qua HTTP header hoặc message metadata theo integration.
9. **Bật Lambda Insights:** khi cần metric hệ thống và chẩn đoán resource.
10. **Kiểm tra quyền và retention:** role, policy, log group, sampling và thời gian lưu.
11. **Thử tình huống lỗi:** timeout, throttle, cold start, message lặp và dependency chậm.
12. **Đo chi phí:** log volume, trace sampling, custom metrics và Insights telemetry.

## 18. Các lỗi thường gặp

**Chỉ ghi log text tự do:** Khó lọc và liên kết invocation. Chuẩn hóa JSON log và các định danh.

**Log toàn bộ event:** Dễ làm lộ dữ liệu nhạy cảm và tăng chi phí. Chỉ ghi metadata cần thiết.

**Không đặt retention:** Log tồn tại lâu hơn nhu cầu và phát sinh chi phí. Đặt retention theo yêu cầu điều tra và tuân thủ.

**Chỉ xem Errors:** Không thấy throttling hoặc backlog. Theo dõi thêm Throttles, concurrency, queue age và IteratorAge.

**Chỉ xem Average Duration:** Tail latency có thể bị che khuất. Dùng p95/p99 khi SLA cần.

**Không truyền correlation/trace context:** Trace bị đứt khi qua queue hoặc service khác. Truyền context rõ ràng và kiểm thử integration.

**Cho rằng active tracing ghi mọi invocation:** Sampling có thể loại bỏ một số trace. Kết hợp log và metric.

**Instrument trùng lặp:** Auto-instrumentation và instrumentation thủ công có thể tạo span trùng. Xác định phạm vi instrument.

**Không theo dõi memory:** Function có thể tiến gần memory limit dù metric tiêu chuẩn không thể hiện mức sử dụng chi tiết. Dùng Lambda Insights khi cần.

**Đặt alarm không theo SLO:** Cảnh báo quá nhiều hoặc bỏ lỡ vấn đề thật. Chọn ngưỡng dựa trên hành vi và mục tiêu dịch vụ.

**Dimension cardinality quá cao:** Dùng requestId hoặc orderId làm dimension gây nhiều metric riêng. Đưa ID vào log/trace, giữ dimension có số lượng hữu hạn.

**Không quan sát nguồn event:** Function trông khỏe nhưng queue backlog tăng. Theo dõi cả broker, event source mapping và DLQ.

## 19. Checklist trước khi đưa Lambda vào production

- [ ] Log group được tạo đúng và execution role có quyền ghi log tối thiểu.
- [ ] Log có cấu trúc và chứa requestId hoặc eventId phù hợp.
- [ ] Không log secret, token hoặc payload nhạy cảm.
- [ ] Log retention được cấu hình rõ ràng.
- [ ] Invocations, Errors, Duration và Throttles được theo dõi.
- [ ] Có metric concurrency và metric phù hợp với queue/stream.
- [ ] Dashboard thể hiện traffic, reliability, latency và resource.
- [ ] Alarm gắn với SLO và có người/nhóm chịu trách nhiệm.
- [ ] Custom metric có namespace và dimension cardinality hợp lý.
- [ ] Active tracing hoặc OTel được cấu hình khi cần.
- [ ] Trace context được truyền qua các ranh giới quan trọng.
- [ ] Sampling được cân bằng giữa khả năng điều tra và chi phí.
- [ ] Lambda Insights được bật khi cần metric CPU, memory, network và /tmp.
- [ ] Execution role có quyền ghi trace/telemetry tương ứng.
- [ ] Đã kiểm thử log, metric, trace và alarm bằng tình huống lỗi.
- [ ] Có thể tìm một invocation từ requestId/correlationId xuyên các tín hiệu.
- [ ] Chi phí log, metric, trace và telemetry được theo dõi định kỳ.

## Kết luận

CloudWatch cung cấp log, metric, dashboard và alarm để theo dõi hành vi Lambda theo thời gian. X-Ray giúp quan sát đường đi của request và độ trễ qua các dịch vụ phụ thuộc. Lambda Insights bổ sung metric hệ thống như memory, CPU, network và filesystem tạm thời. Khi được liên kết bằng request ID, event ID, correlation ID và trace context, ba công cụ giúp nhóm vận hành chuyển từ phát hiện bất thường sang xác định nguyên nhân.

Với Java Lambda, hãy chuẩn hóa log có cấu trúc, chọn metric phản ánh SLO, instrument dependency quan trọng, truyền trace context qua message và bật Lambda Insights khi cần dữ liệu tài nguyên. Kết hợp quyền tối thiểu, retention, sampling và kiểm soát cardinality để observability đủ sâu cho production mà vẫn quản lý được chi phí.

