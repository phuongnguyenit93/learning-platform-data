# CloudWatch Logs Insights và truy vấn log ứng dụng

Một dịch vụ Spring Boot chạy trên Amazon ECS, EKS hoặc AWS Lambda có thể tạo hàng nghìn log events mỗi phút. Khi người dùng báo một request trả HTTP 500, đội vận hành cần biết request đó đi qua service nào, lỗi xuất hiện ở bước nào, có liên quan tới DynamoDB hay S3 không và latency tăng từ thời điểm nào. Nếu log chỉ là những dòng text không có cấu trúc, việc tìm kiếm và đối chiếu thường mất nhiều thời gian.

**Amazon CloudWatch Logs Insights** cho phép truy vấn và phân tích log trực tiếp trong CloudWatch Logs bằng ngôn ngữ truy vấn. Bạn có thể lọc event theo thời gian, tìm exception, trích xuất trường từ text, nhóm lỗi theo service hoặc endpoint, tính p50/p95/p99 latency và lần theo correlation ID.

Bài học thuộc chương **Quan sát với CloudWatch** của module **CLOUD_PROVIDERS_AWS**. Chúng ta tập trung vào cách thiết kế log cho ứng dụng Java/Spring Boot, sử dụng CloudWatch Logs Insights Query Language (Logs Insights QL), viết truy vấn điều tra sự cố và tối ưu phạm vi dữ liệu được quét.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả quan hệ giữa log group, log stream và log event.
2. Phân biệt event timestamp, ingestion time và các system fields của CloudWatch Logs.
3. Thiết kế log JSON có cấu trúc cho ứng dụng Java/Spring Boot.
4. Sử dụng MDC/correlation ID để nối log giữa các request và service.
5. Chọn log group và time range phù hợp trước khi chạy query.
6. Dùng các lệnh cơ bản của Logs Insights QL: fields, filter, parse, stats, sort và limit.
7. Truy vấn lỗi, exception, HTTP status và AWS SDK failures.
8. Tính số lượng request, error count và latency percentile theo thời gian.
9. Tìm endpoint chậm, exception phổ biến và request theo trace ID.
10. Dùng parse để trích xuất field từ log text chưa có cấu trúc.
11. Khám phá log patterns và nhận diện thay đổi bất thường.
12. Chạy query từ Console, AWS CLI và API.
13. Tối ưu query để giảm dữ liệu quét và chi phí.
14. Bảo vệ dữ liệu nhạy cảm trong log và giới hạn quyền truy cập.
15. Phân biệt Logs Insights với CloudWatch Metrics, metric filters và alarms.

## 2. CloudWatch Logs: log group, log stream và log event

CloudWatch Logs tổ chức dữ liệu theo ba thành phần:

- **Log group:** nhóm log có chung ứng dụng, workload, môi trường hoặc chính sách retention.
- **Log stream:** luồng event từ một nguồn cụ thể, chẳng hạn một Lambda execution environment, container instance hoặc host.
- **Log event:** một bản ghi log gồm timestamp và message.

Ví dụ cách đặt tên log group:

    /application/orders-api/prod
    /application/payment-service/prod
    /aws/lambda/invoice-worker
    /ecs/cluster-a/orders-api

Một log group có thể chứa nhiều log streams. Khi chạy Logs Insights, bạn thường chọn một hoặc nhiều log groups làm phạm vi query; kết quả có thể tổng hợp log từ nhiều instance/container.

Nên thống nhất naming convention để operator dễ chọn đúng service và môi trường. Tránh gộp development, staging và production vào cùng log group nếu retention, quyền truy cập và yêu cầu bảo mật khác nhau.

### 2.1. System fields

CloudWatch Logs Insights cung cấp các system fields thường dùng:

| Field | Ý nghĩa |
|---|---|
| @timestamp | Timestamp của log event |
| @message | Nội dung message gốc |
| @log | Định danh log group chứa event |
| @logStream | Tên log stream |
| @ingestionTime | Thời điểm CloudWatch Logs nhận event |
| @ptr | Con trỏ nội bộ tới log record |

Một số loại log có thêm system fields đặc thù. Ví dụ Lambda logs có thể có các trường liên quan request hoặc loại log tùy format và runtime.

Không nhầm @timestamp với @ingestionTime. Nếu ứng dụng gửi log chậm hoặc agent buffer log, hai thời điểm có thể lệch nhau. Khi điều tra pipeline log bị trễ, so sánh cả hai.

### 2.2. Event time và ingestion time

`@timestamp` là thời điểm gắn với event khi được gửi vào CloudWatch Logs. `@ingestionTime` là lúc dịch vụ nhận event. Chênh lệch lớn có thể gợi ý:

- Agent hoặc container runtime đang buffer log.
- Network tới CloudWatch Logs không ổn định.
- Ứng dụng gửi event trễ.
- Đồng hồ hệ thống không đồng bộ.
- Batch log được flush sau một khoảng thời gian.

Vì vậy, khi đối chiếu sự kiện với trace, metric và deployment timeline, cần kiểm tra timezone và clock synchronization của workload.

## 3. Chuẩn hóa log JSON cho Java/Spring Boot

Logs Insights có thể tự động khám phá field từ log JSON. Với log có cấu trúc, bạn có thể filter trực tiếp theo `level`, `service`, `statusCode` hoặc `traceId` mà không phải parse từng dòng.

Một event JSON tham khảo:

    {
      "timestamp": "2026-11-20T04:15:23.417Z",
      "level": "ERROR",
      "service": "orders-api",
      "environment": "prod",
      "message": "Unable to load order",
      "traceId": "4bf92f3577b34da6a3ce929d0e0e4736",
      "spanId": "00f067aa0ba902b7",
      "requestId": "req-7f2a91",
      "route": "/orders/{orderId}",
      "method": "GET",
      "statusCode": 503,
      "durationMs": 245,
      "errorType": "SdkClientException",
      "awsService": "DynamoDB",
      "awsOperation": "GetItem"
    }

Các field nên được thiết kế ổn định:

| Field | Mục đích |
|---|---|
| timestamp | Thời điểm do ứng dụng ghi, chuẩn ISO 8601 UTC |
| level | DEBUG, INFO, WARN, ERROR |
| service | Tên service |
| environment | dev, staging, prod |
| message | Mô tả ngắn, dễ đọc |
| traceId/spanId | Liên kết distributed trace |
| requestId | Định danh request tại application boundary |
| route/method | Endpoint và HTTP method |
| statusCode | HTTP status |
| durationMs | Thời gian xử lý |
| errorType/errorCode | Phân loại lỗi |
| awsService/awsOperation | Dependency AWS được gọi |

Giữ tên field và kiểu dữ liệu nhất quán. Ví dụ `durationMs` nên là number thay vì có lúc là `"245ms"`, có lúc là `245`. Dữ liệu số cho phép dùng avg, max và percentile.

Không log password, access token, session cookie, private key, authorization header hoặc dữ liệu cá nhân không cần thiết. Nếu cần nhận diện khách hàng, dùng identifier đã được kiểm soát hoặc pseudonymous ID theo chính sách dữ liệu.

## 4. Đưa log từ ứng dụng lên CloudWatch Logs

CloudWatch Logs Insights chỉ truy vấn dữ liệu đã được gửi vào CloudWatch Logs. Cách thu thập phụ thuộc môi trường chạy:

| Runtime | Cách thu thập thường gặp |
|---|---|
| AWS Lambda | Lambda tích hợp với CloudWatch Logs; execution role cần quyền ghi log |
| Amazon ECS | awslogs log driver hoặc FireLens/Fluent Bit |
| Amazon EKS | Fluent Bit, CloudWatch agent hoặc OpenTelemetry Collector |
| EC2 | CloudWatch Agent hoặc log shipper |
| On-premises/application ngoài AWS | Agent/collector có credentials và network phù hợp |

Với container, nên ghi log ra stdout/stderr và để runtime log driver/collector chuyển tiếp. Tránh để ứng dụng tự quản lý file log lớn trong container filesystem nếu nền tảng đã có cơ chế thu thập log chuẩn.

Một pipeline log cần xác định rõ:

1. Format event (JSON hoặc text).
2. Timestamp và timezone.
3. Multiline handling cho Java stack traces.
4. Log group/stream naming.
5. Batch size và retry khi gửi log.
6. Retention, encryption và access control.
7. Cách xử lý log delivery failure và backpressure.

### 4.1. Java stack trace và multiline

Java exception thường có nhiều dòng. Nếu collector tách từng dòng thành event riêng, stack trace có thể bị phân mảnh và khó tìm.

Ưu tiên một JSON event chứa exception type, message và stack trace được serialize thành một field. Nếu dùng text log, cấu hình multiline parser của agent/Fluent Bit để ghép stack trace theo event boundary.

Không đưa toàn bộ stack trace vào metric dimension hoặc high-cardinality labels. Stack trace phù hợp để điều tra log; metric nên dùng error type/code có giới hạn giá trị.

## 5. Correlation ID và MDC trong Spring Boot

Khi một HTTP request đi qua controller, service và repository, các log cần mang cùng correlation ID. Với distributed tracing, dùng trace context theo W3C Trace Context hoặc OpenTelemetry thay vì tự tạo một hệ thống trace ID riêng biệt.

SLF4J MDC có thể giữ các trường ngữ cảnh trong quá trình xử lý trên cùng thread:

    String traceId = resolveTraceId(request);

    MDC.put("traceId", traceId);
    try {
        filterChain.doFilter(request, response);
    } finally {
        MDC.remove("traceId");
    }

Đây là phần minh họa trong servlet filter. Trong code thực tế, cần validate độ dài/format của header từ client, không dùng correlation ID làm bằng chứng xác thực và bảo đảm dọn MDC trong finally để tránh rò ngữ cảnh giữa các request.

MDC thường dựa trên ThreadLocal. Với async execution, thread pool, Reactor/WebFlux hoặc CompletableFuture, context có thể không tự truyền sang thread khác. Dùng context propagation/instrumentation phù hợp, đặc biệt khi đã tích hợp OpenTelemetry.

Một log JSON nên mang traceId/spanId để có thể truy vấn theo request và chuyển tiếp sang trace backend nếu cần.

## 6. Mở Logs Insights và chọn phạm vi query

Trong AWS Console:

1. Chọn đúng AWS Region.
2. Mở CloudWatch.
3. Chọn Logs Insights.
4. Chọn log groups chứa ứng dụng cần điều tra.
5. Chọn time range phù hợp.
6. Viết query và chạy.
7. Kiểm tra số log events, kết quả và dữ liệu được quét.

Khi truy vấn nhiều log groups, kết quả có thể trộn log từ nhiều service. Hãy đưa field `service` hoặc `environment` vào filter để tránh kết luận nhầm.

Một số điểm cần kiểm tra trước khi query:

- Đúng account và Region.
- Đúng log group, không chọn nhầm staging/prod.
- Time range bao phủ thời điểm sự cố.
- Log retention chưa xóa khoảng thời gian cần điều tra.
- Event đã được ingest; log mới có thể cần một khoảng thời gian trước khi query thấy.
- Query language đang chọn là Logs Insights QL nếu dùng cú pháp trong bài.

## 7. Cấu trúc cơ bản của Logs Insights QL

Một query thường có các command nối bằng dấu pipe `|`:

    fields @timestamp, level, service, message
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 100

Các command được thực hiện theo thứ tự từ trên xuống dưới. Bạn có thể dùng nhiều filter và fields command để thu hẹp hoặc định dạng kết quả.

| Command | Vai trò |
|---|---|
| fields | Chọn hoặc tính toán field hiển thị |
| filter | Giữ lại event thỏa điều kiện |
| parse | Trích field từ message text |
| stats | Tổng hợp, đếm và tính percentile |
| sort | Sắp xếp kết quả |
| limit | Giới hạn số record trả về |
| pattern | Nhóm log thành các pattern tương tự |
| display | Chỉ hiển thị các field được chọn |
| unnest | Tách phần tử trong list thành record riêng |

Bài học dùng Logs Insights QL. CloudWatch Logs Insights còn hỗ trợ các query language khác trong một số trải nghiệm/log source; cú pháp không thể hoán đổi tùy ý giữa QL, SQL và PPL.

## 8. Query đầu tiên: xem log mới nhất

Query xem 100 event mới nhất:

    fields @timestamp, @log, @logStream, @message
    | sort @timestamp desc
    | limit 100

Query này hữu ích khi kiểm tra ứng dụng có đang ghi log hay không và xem event gần nhất.

Nếu log là JSON, ưu tiên field đã được khám phá tự động:

    fields @timestamp, level, service, environment, message, traceId
    | sort @timestamp desc
    | limit 100

`limit 100` chỉ giới hạn số kết quả trả về. Nó không tự giảm lượng dữ liệu phải scan trong time range đã chọn. Muốn giảm dữ liệu quét, hãy chọn time range và log groups nhỏ hơn, rồi filter theo field phù hợp.

## 9. Tìm ERROR và WARN

Tìm tất cả ERROR:

    fields @timestamp, service, message, traceId, errorType
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 200

Tìm cả WARN và ERROR:

    fields @timestamp, level, service, message
    | filter level in ["WARN", "ERROR"]
    | sort @timestamp desc
    | limit 200

Nếu ứng dụng ghi level trong text chứ không có field JSON:

    fields @timestamp, @message
    | filter @message like /ERROR|WARN/
    | sort @timestamp desc
    | limit 200

Dùng field có cấu trúc thường rõ ràng và dễ bảo trì hơn tìm chuỗi trong toàn bộ message.

### 9.1. Lọc theo service và environment

    fields @timestamp, level, service, environment, message
    | filter service = "orders-api"
    | filter environment = "prod"
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 100

Nếu nhiều service dùng chung log group, filter theo service là cần thiết để tránh kết quả của workload khác.

## 10. Tìm lỗi AWS SDK và dependency failures

Ứng dụng Java thường gọi DynamoDB, S3, SQS, Secrets Manager hoặc RDS. Nên log tên AWS service, operation, error code, request ID và trace ID khi thích hợp.

Tìm lỗi liên quan DynamoDB:

    fields @timestamp, service, awsService, awsOperation,
           errorType, errorCode, message, traceId
    | filter awsService = "DynamoDB"
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 100

Đếm lỗi theo AWS operation và error type:

    filter level = "ERROR"
    | stats count(*) as failures by awsService, awsOperation, errorType
    | sort failures desc
    | limit 30

Nếu log event không có field riêng, có thể filter message:

    fields @timestamp, @message
    | filter @message like /ThrottlingException|ProvisionedThroughputExceededException|AccessDeniedException/
    | sort @timestamp desc
    | limit 100

Không log credential, request authorization headers hoặc toàn bộ request payload để phục vụ truy vấn. Hãy log metadata đủ để phân loại và correlate.

## 11. Trích xuất field bằng parse

Với log text cũ, field chưa được tách sẵn. Command `parse` cho phép dùng glob hoặc regular expression để trích giá trị.

Giả sử message có dạng:

    INFO method=GET path=/orders status=200 durationMs=34 traceId=abc123

Query dùng glob:

    parse @message "method=*, path=*, status=*, durationMs=*, traceId=*" as method, path, status, durationMs, traceId
    | fields @timestamp, method, path, status, durationMs, traceId
    | limit 100

Với format phức tạp hơn, dùng regex named capture groups:

    parse @message /method=(?<method>\S+) path=(?<path>\S+) status=(?<status>\d{3}) durationMs=(?<durationMs>\d+)/
    | fields @timestamp, method, path, status, durationMs
    | filter status like /5\d\d/
    | limit 100

Regex parse tạo field từ các named groups. Khi regex không khớp, field có thể không được tạo cho event đó. Hãy kiểm thử pattern với nhiều mẫu log thật, bao gồm message có dấu cách, ký tự đặc biệt và dữ liệu bị thiếu.

### 11.1. Chọn glob hay regex?

| Cách parse | Phù hợp khi |
|---|---|
| Glob | Format cố định, delimiter rõ, đơn giản |
| Regex | Cần nhóm, tùy chọn, pattern phức tạp hoặc trường có cấu trúc biến đổi |

Nếu kiểm soát được ứng dụng, hãy ghi JSON có cấu trúc thay vì parse text ở mỗi query. Parse phù hợp với log legacy hoặc format không thể thay đổi ngay.

## 12. Đếm request và error theo thời gian

Đếm số event theo level trong time range:

    stats count(*) as events by level
    | sort events desc

Đếm lỗi mỗi 5 phút:

    filter level = "ERROR"
    | stats count(*) as errors by bin(5m)

Theo dõi tổng request và HTTP 5xx theo cửa sổ 5 phút:

    stats count(*) as totalRequests,
          sum(if(statusCode >= 500, 1, 0)) as serverErrors
      by bin(5m)

Nếu log có nhiều event cho một request, hãy chỉ đưa access/request completion event vào phép tính request rate. Không đếm tất cả application log lines như số HTTP requests.

Có thể tính tỷ lệ lỗi trong cùng query:

    stats count(*) as totalRequests,
          sum(if(statusCode >= 500, 1, 0)) as serverErrors
      by bin(5m)
    | fields bin(5m), totalRequests, serverErrors,
             100.0 * serverErrors / totalRequests as errorPercent

Dùng field số cho statusCode. Nếu status được parse từ text thành string, chuẩn hóa kiểu dữ liệu hoặc filter theo regex phù hợp trước khi tính.

## 13. Đo latency p50, p95 và p99

Percentile cho biết phân phối thời gian xử lý. Average có thể che giấu một nhóm request rất chậm; p95/p99 giúp nhận diện tail latency.

    filter ispresent(durationMs)
    | stats count(*) as requests,
            avg(durationMs) as avgMs,
            pct(durationMs, 50) as p50Ms,
            pct(durationMs, 95) as p95Ms,
            pct(durationMs, 99) as p99Ms,
            max(durationMs) as maxMs

Phân tích theo endpoint:

    filter ispresent(durationMs)
    | stats count(*) as requests,
            pct(durationMs, 95) as p95Ms,
            pct(durationMs, 99) as p99Ms
      by route
    | sort p95Ms desc
    | limit 20

Phân tích latency theo thời gian:

    filter ispresent(durationMs)
    | stats count(*) as requests,
            pct(durationMs, 50) as p50Ms,
            pct(durationMs, 95) as p95Ms,
            pct(durationMs, 99) as p99Ms
      by bin(5m)

Logs Insights percentile là phép tính thống kê trên tập event được query. Nó không thay thế metric latency được instrument đúng cách cho SLO/alarms; hãy bảo đảm mỗi request chỉ tạo một event latency đại diện.

## 14. Tìm endpoint chậm và request vượt ngưỡng

Tìm request trên 1.000 ms:

    fields @timestamp, route, method, durationMs, statusCode, traceId
    | filter durationMs > 1000
    | sort durationMs desc
    | limit 100

Tìm endpoint có p95 cao:

    filter ispresent(durationMs)
    | stats count(*) as requests,
            pct(durationMs, 95) as p95Ms,
            max(durationMs) as maxMs
      by route
    | filter requests >= 20
    | sort p95Ms desc
    | limit 20

Ngưỡng request count giúp tránh kết luận từ một endpoint chỉ có một vài mẫu. Trong production, chọn ngưỡng phù hợp traffic và time range.

Nếu latency tăng, so sánh với dependency fields như awsService/awsOperation, database query name hoặc downstream status. Tránh log SQL parameter hoặc payload chứa dữ liệu nhạy cảm.

## 15. Lần theo một request bằng traceId

Khi nhận trace ID từ incident, tìm tất cả log event mang ID đó:

    fields @timestamp, service, level, message,
           traceId, spanId, requestId
    | filter traceId = "4bf92f3577b34da6a3ce929d0e0e4736"
    | sort @timestamp asc
    | limit 500

Nếu query nhiều log groups, kết quả có thể cho thấy request đi qua API, order service và worker. Kết hợp traceId với spanId giúp xác định log nào thuộc span cụ thể.

Nếu dùng AWS X-Ray hoặc OpenTelemetry, trace và log là hai tín hiệu bổ sung:

- Trace mô tả đường đi và thời lượng của spans.
- Log cung cấp chi tiết sự kiện, exception và context.
- Metric mô tả xu hướng định lượng và hỗ trợ alarm.

Không dùng trace ID ngẫu nhiên từ client làm dữ liệu định danh nhạy cảm. Giới hạn format/độ dài và tuân thủ trace context propagation.

## 16. Phân tích exception phổ biến

Đếm lỗi theo exception type:

    filter level = "ERROR"
    | stats count(*) as occurrences by errorType
    | sort occurrences desc
    | limit 20

Đếm lỗi theo error code:

    filter ispresent(errorCode)
    | stats count(*) as occurrences by errorCode
    | sort occurrences desc
    | limit 30

Tìm các lỗi timeout:

    fields @timestamp, service, message, errorType, traceId
    | filter @message like /Timeout|timed out|timeout/
    | sort @timestamp desc
    | limit 100

Tìm lỗi authorization:

    fields @timestamp, service, awsService, awsOperation,
           errorCode, message, traceId
    | filter errorCode = "AccessDenied"
    | sort @timestamp desc
    | limit 100

Khi exception type tăng, hãy kiểm tra release version, deployment time, AWS Region, resource policy, credential refresh và dependency health. Không kết luận root cause chỉ từ tên exception.

## 17. Khám phá log patterns

Command `pattern` nhóm các log event có cấu trúc tương tự thành pattern, giúp phát hiện nhóm message lặp lại mà không cần viết filter cho từng chuỗi.

    pattern @message

Có thể dùng pattern analysis để:

- Tìm template message phổ biến.
- Nhận diện một loại exception tăng đột ngột.
- Phát hiện message mới xuất hiện sau deployment.
- Gom nhóm log text có biến động ở ID, timestamp hoặc giá trị động.

Pattern clustering hữu ích khi bắt đầu điều tra một log group lớn. Sau khi thấy pattern đáng chú ý, viết query cụ thể bằng field, filter và stats để định lượng.

Pattern là công cụ khám phá; không thay thế taxonomy errorType/errorCode có chủ đích trong application logs. Nếu message thay đổi tùy tiện, pattern grouping sẽ khó diễn giải.

## 18. Làm việc với JSON fields và nested data

Khi event là JSON hợp lệ, CloudWatch Logs Insights có thể tự động khám phá nhiều field. Bạn có thể truy vấn top-level field trực tiếp:

    fields @timestamp, service, level, durationMs
    | filter service = "orders-api"
    | filter durationMs > 500
    | sort durationMs desc
    | limit 100

Với JSON nested, field có thể truy cập bằng dot notation nếu field discovery nhận diện được:

    fields @timestamp, request.method, request.path,
           response.statusCode, durationMs
    | filter response.statusCode >= 500
    | sort @timestamp desc
    | limit 100

Nếu JSON nằm trong một chuỗi lồng bên trong field khác, cần dùng hàm parse JSON phù hợp hoặc parse command. Đừng giả định mọi field lồng đều tự động được khám phá trong mọi loại log; kiểm tra danh sách discovered fields và thử một query nhỏ.

Tránh đặt tên field có dấu cách hoặc ký tự đặc biệt. Dùng naming convention ổn định như lowerCamelCase hoặc snake_case.

## 19. Truy vấn nhiều log groups và nhiều service

Logs Insights có thể truy vấn nhiều log groups cùng lúc. Điều này hữu ích khi request đi qua nhiều service hoặc khi cần so sánh workload.

Ví dụ query lỗi theo service:

    filter level = "ERROR"
    | stats count(*) as errors by service
    | sort errors desc
    | limit 50

Query theo môi trường và AWS Region:

    fields @timestamp, service, environment, awsRegion, level, message
    | filter environment = "prod"
    | filter awsRegion = "ap-southeast-1"
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 200

Khi truy vấn cross-account observability, cần quyền và cấu hình CloudWatch phù hợp giữa monitoring account và source accounts. Không giả định chọn log group name là đủ để vượt qua ranh giới account.

Nếu log groups có schema khác nhau, query có thể trả nhiều giá trị null hoặc field không đồng nhất. Chuẩn hóa schema trước khi mở rộng truy vấn toàn hệ thống.

## 20. Chạy query bằng AWS CLI

AWS CLI cung cấp API để bắt đầu query, đọc kết quả và dừng query.

Ví dụ bắt đầu query:

    aws logs start-query \
      --log-group-names "/application/orders-api/prod" \
      --start-time <START_EPOCH_SECONDS> \
      --end-time <END_EPOCH_SECONDS> \
      --query-string 'fields @timestamp, level, message, traceId | filter level = "ERROR" | sort @timestamp desc | limit 100'

Lệnh trả về `queryId`. Dùng ID này để lấy kết quả:

    aws logs get-query-results --query-id <QUERY_ID>

Nếu query chạy lâu, có thể gọi get-query-results nhiều lần để xem status. Trạng thái thường gặp gồm Scheduled, Running, Complete, Failed, Cancelled và Timeout. Dừng query đang chạy khi không còn cần:

    aws logs stop-query --query-id <QUERY_ID>

`start-time` và `end-time` là Unix epoch seconds, không phải milliseconds. Hãy tính đúng time range và Region trước khi chạy.

CLI sample dùng placeholder; thay bằng epoch và query ID thực tế. Quoting có thể khác giữa Bash, PowerShell và shell CI. Với script tự động, ưu tiên tạo query string trong file hoặc truyền argument theo quy tắc quoting của shell đang dùng.

## 21. Dùng Logs Insights API trong automation

Ứng dụng hoặc incident tooling có thể gọi CloudWatch Logs Insights API:

- StartQuery: bắt đầu query và nhận query ID.
- GetQueryResults: đọc status và kết quả.
- StopQuery: dừng query không còn cần.
- DescribeQueries: xem các query gần đây theo log group/time range.
- PutQueryDefinition: lưu query definition để tái sử dụng.

Một workflow automation nên:

1. Chọn account/Region và log groups từ cấu hình đã kiểm soát.
2. Tính start/end time theo incident window.
3. Gửi query với giới hạn time range.
4. Lưu query ID và correlation/incident ID.
5. Poll GetQueryResults với backoff phù hợp nếu query chưa hoàn tất.
6. Dừng query khi cancellation hoặc deadline xảy ra.
7. Lưu kết quả theo chính sách dữ liệu, không phát tán log nhạy cảm vào ticket/chat.

IAM role chạy automation cần quyền logs:StartQuery, logs:GetQueryResults và logs:StopQuery trên phạm vi phù hợp. Thêm quyền mô tả/query definitions nếu workflow sử dụng các API đó.

## 22. Tối ưu query và chi phí

Chi phí Logs Insights phụ thuộc dữ liệu được scan theo pricing model của CloudWatch Logs Insights và Region. Query rộng trên log group lớn có thể tốn thời gian và chi phí dù chỉ trả về vài dòng.

Các nguyên tắc tối ưu:

1. Chọn time range nhỏ nhất đủ bao phủ incident.
2. Chỉ chọn log groups cần thiết.
3. Filter theo service/environment/level sớm trong query.
4. Ưu tiên field có cấu trúc thay vì regex trên toàn bộ @message.
5. Chỉ chọn field cần hiển thị.
6. Dùng log class và retention phù hợp workload/query requirements.
7. Lưu query thường dùng để operator không phải viết lại.
8. Dừng query tốn kém hoặc chạy sai phạm vi.
9. Theo dõi bytes scanned và query duration.
10. Dùng metric cho dashboard/alarms định kỳ, tránh query log khối lượng lớn liên tục để làm nhiệm vụ monitoring.

`limit` giúp giới hạn kết quả hiển thị nhưng không đảm bảo giảm bytes scanned. Giảm time range, số log groups và dữ liệu cần phân tích mới là cách kiểm soát phạm vi scan.

### 22.1. Field indexes

CloudWatch Logs hỗ trợ field indexes cho một số loại log group và điều kiện query. Khi tổ chức tạo index policy cho field thường xuyên dùng để lọc, query equality trên field được index có thể giảm lượng dữ liệu phải scan.

Field index không tự động áp dụng cho mọi field hoặc mọi query operator. Kiểm tra log class, index policy và tài liệu hiện hành trước khi dựa vào index để tối ưu. Thiết kế field cardinality và query pattern có chủ đích; không tạo index cho mọi field tùy tiện.

## 23. Retention, log class và bảo vệ dữ liệu

Log group cần retention policy phù hợp. Giữ log vô thời hạn làm tăng chi phí và có thể trái chính sách dữ liệu; retention quá ngắn có thể khiến incident investigation hoặc audit không còn dữ liệu.

Cân nhắc:

- Retention theo môi trường và loại dữ liệu.
- Encryption at rest và KMS key policy khi yêu cầu.
- IAM permission tối thiểu cho logs:FilterLogEvents, logs:StartQuery, logs:GetQueryResults và logs:Unmask nếu có nhu cầu đặc biệt.
- Data protection policy để phát hiện/mask dữ liệu nhạy cảm theo khả năng dịch vụ.
- Log group class phù hợp với tần suất truy vấn và tính năng cần dùng.
- Export/archive sang S3 nếu có yêu cầu lưu trữ dài hạn và analytics riêng.

Không cấp logs:Unmask rộng rãi. Nếu tổ chức dùng data protection, xác định rõ ai có quyền xem nội dung đã bị mask và quy trình audit việc unmask.

Log không phải nơi lưu bí mật. Hãy loại bỏ secret trước khi ghi log; masking là lớp giảm rủi ro, không thay việc ngăn secret đi vào log.

## 24. Logs Insights so với metric filters và alarms

Logs Insights phù hợp cho truy vấn ad-hoc, điều tra và phân tích lịch sử. Nó không nên là cách duy nhất để phát hiện sự cố cần phản ứng nhanh.

| Cơ chế | Phù hợp với | Ví dụ |
|---|---|---|
| Logs Insights | Điều tra, phân tích và truy vấn linh hoạt | Tìm traceId, top exception, p95 theo route |
| Metric filter | Chuyển mẫu log thành metric | Đếm dòng ERROR hoặc AccessDenied |
| CloudWatch Metrics | Dashboard và phân tích chuỗi thời gian | RequestCount, ErrorRate, Duration |
| CloudWatch Alarm | Phát hiện vượt ngưỡng và kích hoạt action | 5xx tăng, CPU cao, queue depth vượt ngưỡng |
| X-Ray/OpenTelemetry tracing | Phân tích đường đi của request | Span chậm ở DynamoDB hoặc downstream service |

Một hệ thống production thường kết hợp cả log, metric và trace. Metric/alarm phát hiện tín hiệu; Logs Insights giúp trả lời điều gì đã xảy ra; trace giúp xác định request bị chậm ở span nào.

Không tạo alarm dựa trên query log chạy thủ công. Nếu cần cảnh báo từ log pattern, thiết kế metric filter hoặc pipeline metric phù hợp.

## 25. Troubleshooting khi query không ra kết quả

### 25.1. Không thấy log event

Kiểm tra đúng Region/account/log group, time range, retention và trạng thái ingest. Xác nhận workload có quyền ghi log và log stream đã được tạo.

### 25.2. Query trả field null

Kiểm tra event có phải JSON hợp lệ không, field có cùng tên/case không và log class có hỗ trợ field discovery theo kỳ vọng không. Mở raw @message để xác minh schema.

### 25.3. Parse không khớp

So sánh regex với message thật. Chú ý khoảng trắng, dấu nháy, ký tự đặc biệt, optional fields và stack trace multiline. Dùng query giới hạn nhỏ để kiểm tra từng bước.

### 25.4. Query quá chậm hoặc scan quá nhiều

Giảm time range, bỏ log groups không liên quan, filter theo service/level, dùng field index khi phù hợp và tránh regex trên toàn bộ message nếu đã có structured fields.

### 25.5. Kết quả không khớp số request

Có thể ứng dụng ghi nhiều event cho một request, retry tạo thêm log, một request đi qua nhiều service hoặc access log và application log đều được tính. Chọn một event chuẩn đại diện request completion và dùng request/trace ID để đối chiếu.

### 25.6. Không truy vấn được log group khác account

Kiểm tra CloudWatch cross-account observability, monitoring/source account configuration, Region và IAM permissions. Không giải quyết bằng cách cấp logs:* trên mọi account.

## 26. Bài tập tình huống

### Bài A — Tìm 100 lỗi gần nhất

Ứng dụng ghi JSON với field level, message và traceId.

**Đáp án:**

    fields @timestamp, level, message, traceId
    | filter level = "ERROR"
    | sort @timestamp desc
    | limit 100

### Bài B — Tìm request mất hơn một giây

**Đáp án:**

    fields @timestamp, route, durationMs, traceId
    | filter durationMs > 1000
    | sort durationMs desc
    | limit 100

### Bài C — Đếm 5xx mỗi 5 phút

**Đáp án:**

    filter statusCode >= 500
    | stats count(*) as serverErrors by bin(5m)

### Bài D — Tìm endpoint có p95 cao nhất

**Đáp án:**

    filter ispresent(durationMs)
    | stats pct(durationMs, 95) as p95Ms by route
    | sort p95Ms desc
    | limit 20

### Bài E — Tìm tất cả log của một trace

**Đáp án:**

    fields @timestamp, service, level, message, traceId, spanId
    | filter traceId = "TRACE_ID"
    | sort @timestamp asc

### Bài F — Log text chưa có JSON

Message dạng `method=GET path=/orders status=503 durationMs=80`.

**Đáp án:** dùng parse glob hoặc regex để tạo field method/path/status/durationMs, rồi filter/status và stats.

### Bài G — ERROR tăng sau deployment

**Đáp án:** chọn time range bao phủ trước/sau deploy, filter theo service/environment, nhóm errorType theo bin(5m), đối chiếu deployment version/commit SHA trong log.

### Bài H — Field durationMs trả null

**Đáp án:** kiểm tra log JSON có đúng field và đúng kiểu number không; kiểm tra event có được auto-discover không và field name có bị thay đổi giữa các version.

### Bài I — Query dùng limit 10 nhưng vẫn scan lớn

**Đáp án:** limit chỉ giới hạn số kết quả. Thu hẹp time range/log groups và dùng filter/index phù hợp để giảm dữ liệu scan.

### Bài J — Java stack trace bị tách thành nhiều event

**Đáp án:** cấu hình JSON exception event hoặc multiline parser ở collector để giữ stack trace trong một event logic.

### Bài K — Query AccessDenied không tìm thấy lỗi

**Đáp án:** kiểm tra application có log errorCode/awsService hay chỉ ghi message; đối chiếu service logs và CloudTrail. Không giả định mọi AccessDenied đều có cùng message text.

### Bài L — Logs Insights được dùng làm alarm mỗi phút

**Đáp án:** xem xét metric filter hoặc custom metrics và CloudWatch alarm cho tín hiệu cần phản ứng liên tục; dùng Logs Insights để điều tra nguyên nhân.

## 27. Câu hỏi ôn tập

1. Log group và log stream khác nhau thế nào?
2. Log event gồm những thành phần cơ bản nào?
3. @timestamp khác @ingestionTime ở đâu?
4. @message chứa gì?
5. Vì sao nên dùng JSON structured logs?
6. Field durationMs nên dùng kiểu dữ liệu nào?
7. MDC giúp làm gì trong ứng dụng Java?
8. Vì sao MDC có thể mất context trong async/reactive flow?
9. Trace ID và request ID có vai trò gì?
10. Logs Insights QL dùng ký hiệu nào để nối command?
11. fields command dùng để làm gì?
12. filter command dùng để làm gì?
13. parse hỗ trợ những cách trích field nào?
14. stats dùng để làm gì?
15. bin(5m) nhóm dữ liệu như thế nào?
16. pct(durationMs, 95) biểu diễn gì?
17. Vì sao p95 có thể hữu ích hơn average?
18. Query theo traceId giúp điều tra vấn đề gì?
19. pattern command có tác dụng gì?
20. Query nhiều log groups có rủi ro gì nếu schema không đồng nhất?
21. start-query nhận time range theo đơn vị nào?
22. GetQueryResults dùng để làm gì?
23. StopQuery có tác dụng gì?
24. limit có đảm bảo giảm bytes scanned không?
25. Cách chính để giảm phạm vi dữ liệu scan là gì?
26. Field indexes giúp gì cho query?
27. Vì sao không nên cache/log secret vào application logs?
28. Log retention cần dựa trên những yếu tố nào?
29. Logs Insights khác CloudWatch Alarm như thế nào?
30. Khi nào nên dùng metric filter thay vì query thủ công?

**Đáp án nhanh:** (1) group chứa nhiều stream; (2) timestamp và message; (3) event time và thời điểm ingest; (4) nội dung log gốc; (5) query trực tiếp theo field; (6) number; (7) gắn context vào log; (8) MDC thường dựa ThreadLocal; (9) liên kết sự kiện/request; (10) pipe; (11) chọn/biến đổi field; (12) lọc event; (13) glob và regex; (14) tổng hợp; (15) nhóm theo cửa sổ 5 phút; (16) percentile 95; (17) phản ánh tail latency; (18) nối log của cùng request; (19) nhóm log thành pattern; (20) field thiếu/null và kết quả khó diễn giải; (21) Unix epoch seconds; (22) lấy status/kết quả query; (23) dừng query; (24) không; (25) giảm time range/log groups và filter thích hợp; (26) giảm scan cho điều kiện hỗ trợ; (27) tránh rò rỉ credential/PII; (28) audit, incident, compliance và cost; (29) query điều tra so với cảnh báo/ngưỡng; (30) khi cần metric liên tục từ log pattern.

## 28. Checklist production

- [ ] Log group naming nhất quán theo service và environment.
- [ ] Log JSON có timestamp UTC, level, service và message.
- [ ] Request/trace ID được truyền xuyên service.
- [ ] Log có route, statusCode, durationMs và errorType cần thiết.
- [ ] Field name và data type ổn định giữa các release.
- [ ] Java stack trace được giữ thành event logic hoặc multiline parse đúng.
- [ ] Không log password, token, cookie, private key hoặc payload nhạy cảm.
- [ ] Workload có quyền ghi log tối thiểu.
- [ ] Operator có quyền query đúng log groups/account/Region.
- [ ] Log retention và encryption được cấu hình.
- [ ] Data protection/masking được áp dụng nếu có yêu cầu.
- [ ] Query chọn time range và log groups nhỏ nhất đủ dùng.
- [ ] Query dùng fields/filter trước khi parse/stats khi phù hợp.
- [ ] p95/p99 được tính trên event đại diện một request.
- [ ] Query thường dùng được lưu và đặt tên rõ ràng.
- [ ] Automation có deadline, cancellation và query ID tracking.
- [ ] Query cost/bytes scanned được quan sát.
- [ ] Field index chỉ được tạo cho query patterns thực sự cần.
- [ ] Metric filters/metrics/alarms được dùng cho cảnh báo liên tục.
- [ ] Trace và logs được liên kết qua traceId/spanId.
- [ ] Có runbook khi log không ingest, query chậm hoặc field null.
- [ ] Có quy trình review quyền truy cập và unmask dữ liệu.

## 29. Tổng kết

CloudWatch Logs Insights giúp biến log ứng dụng thành dữ liệu có thể truy vấn và phân tích:

- Log group tổ chức log theo ứng dụng/môi trường; log stream đại diện nguồn gửi; log event chứa timestamp và message.
- JSON structured logs cho phép filter và aggregate theo level, service, status, duration, traceId và error code.
- Logs Insights QL kết hợp fields, filter, parse, stats, sort, limit và pattern để điều tra.
- Query có thể tìm lỗi, phân tích AWS SDK failures, tính request/error theo bin thời gian, đo p50/p95/p99 và lần theo một trace.
- Parse hữu ích cho log legacy; schema JSON ổn định giúp query đơn giản hơn.
- Query nhiều log groups cần field schema nhất quán và filter theo service/environment.
- CLI/API cho phép automation bằng StartQuery, GetQueryResults và StopQuery.
- Chi phí phụ thuộc dữ liệu scan; limit không tự giảm bytes scanned.
- Retention, IAM, encryption và data protection giúp quản lý rủi ro log.
- Logs Insights bổ sung cho metrics, alarms và distributed tracing; nó không thay thế các tín hiệu cảnh báo liên tục.

Một hệ thống quan sát tốt ghi đủ ngữ cảnh để trả lời câu hỏi vận hành, giữ dữ liệu nhạy cảm ngoài log và có query chuẩn để đội ngũ điều tra sự cố nhanh chóng.

### Tài liệu AWS chính thức

1. CloudWatch Logs Insights query syntax: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax.html
2. CloudWatch Logs Insights QL commands: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_QuerySyntax-operations-functions.html
3. Discover fields in log events: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_AnalyzeLogData-discoverable-fields.html
4. Query log data with CloudWatch Logs Insights: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/AnalyzingLogData.html
5. CloudWatch Logs Insights sample queries: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CWL_AnalyzeLogData_Examples.html
6. StartQuery API: https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_StartQuery.html
7. GetQueryResults API: https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_GetQueryResults.html
8. StopQuery API: https://docs.aws.amazon.com/AmazonCloudWatchLogs/latest/APIReference/API_StopQuery.html
9. CloudWatch Logs field indexes: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/CloudWatchLogs-Field-Indexing.html
10. CloudWatch Logs data protection: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/mask-sensitive-log-data.html
11. CloudWatch Logs retention: https://docs.aws.amazon.com/AmazonCloudWatch/latest/logs/Working-with-log-groups-and-streams.html
12. CloudWatch Logs pricing: https://aws.amazon.com/cloudwatch/pricing/
13. AWS Distro for OpenTelemetry: https://aws-otel.github.io/
14. OpenTelemetry context propagation: https://opentelemetry.io/docs/concepts/context-propagation/
