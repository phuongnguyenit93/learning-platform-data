# Chẩn đoán Lambda timeout, throttling và backlog hàng đợi

## Mục tiêu bài học

Trong hệ sinh thái CLOUD_PROVIDERS_AWS, AWS Lambda thực thi mã theo sự kiện và tự quản lý hạ tầng compute. Lambda thường được kết nối với Amazon SQS, Kinesis Data Streams, DynamoDB Streams, EventBridge, API Gateway và các dịch vụ AWS khác. Khi tải tăng hoặc dependency chậm, hệ thống có thể gặp timeout, throttling, retry liên tục hoặc backlog ngày càng lớn.

Các triệu chứng này thường liên quan với nhau. Một function timeout có thể khiến message trong SQS không được xóa; message xuất hiện lại sau visibility timeout, được xử lý nhiều lần và làm backlog tăng. Nếu event source mapping tiếp tục scale trong khi database đã quá tải, Lambda concurrency tăng có thể khiến downstream throttling nặng hơn. Vì vậy, chẩn đoán phải nhìn toàn bộ đường đi của event: nguồn phát, cơ chế invoke, Lambda execution, dependency, retry và nơi lưu message chưa xử lý.

Sau bài học, người học có thể:

- Phân biệt synchronous invocation, asynchronous invocation và event source mapping.
- Nhận diện nguyên nhân Lambda timeout, cold start và dependency latency.
- Tính concurrency sơ bộ từ request rate và execution duration.
- Phân biệt account concurrency, reserved concurrency, provisioned concurrency và throttling.
- Chẩn đoán SQS event source mapping khi message bị retry hoặc backlog tăng.
- Cấu hình visibility timeout, batch size, maximum concurrency và dead-letter queue phù hợp.
- Dùng partial batch response để chỉ retry record thất bại.
- Phân biệt retry semantics của SQS với asynchronous Lambda và stream sources.
- Theo dõi CloudWatch metrics, logs, SQS queue metrics và AWS X-Ray.
- Tính tốc độ tiêu backlog và xác định khi nào cần tăng consumer capacity hoặc giảm producer rate.
- Xây dựng runbook xử lý sự cố, replay và bảo vệ downstream bằng idempotency.

## 1. Nhìn toàn bộ luồng xử lý trước khi sửa Lambda

Một Lambda function có thể được gọi theo ba mô hình chính:

| Mô hình | Ai gọi function? | Cách xử lý lỗi |
|---|---|---|
| Synchronous invocation | Client hoặc dịch vụ gọi trực tiếp và chờ response | Caller nhận lỗi và quyết định retry; Lambda không tự retry function error cho synchronous invoke |
| Asynchronous invocation | Dịch vụ gửi event vào hàng đợi nội bộ của Lambda | Lambda quản lý retry theo cấu hình asynchronous invocation và event age |
| Event source mapping | Lambda poll hoặc nhận record từ SQS, Kinesis, DynamoDB Streams và một số nguồn khác | Lambda event source mapping quản lý batch, checkpoint và retry theo semantics của từng source |

Luồng SQS phổ biến:

~~~mermaid
flowchart LR
    P[Producer] --> Q[(Amazon SQS queue)]
    Q --> E[Lambda event source mapping]
    E --> L[Lambda execution]
    L --> D[(Database or downstream API)]
    L -->|Success and delete| Q
    L -->|Failure or timeout| V[Visibility timeout expires]
    V --> Q
    Q -->|Receive count exceeds threshold| DLQ[(Dead-letter queue)]
~~~

Lambda event source mapping poll queue, gom message thành batch và gọi function. Khi function xử lý thành công, Lambda xóa message khỏi queue. Nếu function lỗi hoặc timeout, message không được xóa; khi visibility timeout hết hạn, message có thể được nhận lại. Nếu message tiếp tục thất bại, receive count tăng và redrive policy có thể chuyển message sang DLQ.

Điểm quan trọng: Lambda không phải lúc nào cũng là nơi giữ backlog. Với SQS, message đang chờ vẫn nằm trong queue. Với asynchronous invocation, event được lưu trong hàng đợi nội bộ của Lambda. Với Kinesis/DynamoDB Streams, record nằm trong stream và consumer lag thể hiện khoảng cách so với dữ liệu mới nhất.

Trước khi điều tra, hãy xác định chính xác invocation model và event source mapping. Retry, metric và nơi replay khác nhau giữa ba mô hình.

## 2. Lambda timeout là gì?

Timeout là giới hạn thời gian tối đa một invocation được phép chạy. Khi thời gian thực thi vượt cấu hình, Lambda dừng invocation và ghi lỗi timeout. Timeout mặc định của Lambda là 3 giây; có thể cấu hình tối đa 900 giây (15 phút).

Timeout không chỉ là thời gian CPU chạy code. Nó có thể bao gồm:

- Khởi tạo execution environment và runtime khi cold start.
- Chạy static initialization, import module hoặc tải dependency.
- Thiết lập kết nối tới database, cache hoặc API.
- Đọc/ghi S3, DynamoDB, SQS hoặc dịch vụ bên ngoài.
- Xử lý batch record và gọi downstream.
- Chờ network, DNS, retry, lock hoặc connection pool.
- Flush log, telemetry và cleanup trước khi handler kết thúc.

Một function có thể timeout dù code xử lý rất ít nếu đang chờ một HTTP request, database connection hoặc DNS lookup không có timeout riêng. Ngược lại, tăng Lambda timeout chỉ kéo dài thời gian chờ và có thể làm concurrency bị chiếm lâu hơn.

### 2.1. Công thức thời gian thực thi

Độ trễ mà caller cảm nhận có thể phân tích thành:

\[
T_{total} = T_{init} + T_{handler} + T_{dependency} + T_{overhead}
\]

Trong đó:

- T_init: runtime startup và initialization, có thể xuất hiện ở cold start.
- T_handler: thời gian logic handler thực thi.
- T_dependency: thời gian chờ database, API, queue, storage hoặc network.
- T_overhead: serialization, logging, extension và các phần phụ trợ.

Đây là mô hình phân tích latency tổng thể, không có nghĩa CloudWatch Duration gộp mọi thành phần. Với cold start, kiểm tra thêm Init Duration trong REPORT log; Duration metric chủ yếu phản ánh thời gian xử lý invocation. Hãy tách thời gian initialization khỏi handler/dependency latency khi so sánh các lần chạy.

Đối với synchronous request, timeout cần nhỏ hơn hoặc bằng timeout của upstream caller/gateway để tránh caller đóng kết nối trước khi Lambda hoàn tất. Đối với SQS, timeout cần phối hợp với visibility timeout để message không bị nhận lại khi invocation vẫn còn chạy.

Không đặt timeout theo cảm tính. Hãy dùng p95/p99 duration của workload thực, thêm headroom cho burst và dependency variance, rồi kiểm tra giới hạn của mọi thành phần trong chuỗi.

## 3. Phân biệt timeout với cold start và lỗi dependency

Cold start là thời gian Lambda chuẩn bị execution environment trước khi chạy handler. Nó có thể gồm runtime initialization, tải package, extension startup, static initialization và thiết lập kết nối. Cold start không đồng nghĩa function bị timeout.

Một số dấu hiệu:

| Triệu chứng | Khả năng cần kiểm tra |
|---|---|
| Invocation đầu tiên chậm, các invocation sau nhanh | Cold start, package size, runtime initialization |
| Mọi invocation đều chậm | Logic handler, dependency, network hoặc thiếu memory/CPU |
| Duration tăng cùng database latency | Connection pool, query plan, lock hoặc database saturation |
| Duration tăng sau khi deploy | Dependency/package change, initialization hoặc regression |
| Chỉ timeout ở payload lớn | Batch size, memory pressure, serialization hoặc xử lý tuần tự |
| Chỉ timeout khi function ở VPC | DNS, route, security group, NAT hoặc endpoint connectivity |

Cách giảm cold start:

- Giảm kích thước deployment package và số dependency không cần thiết.
- Chuyển khởi tạo client có thể tái sử dụng ra ngoài handler, nhưng không lưu state nghiệp vụ vào execution environment.
- Chọn runtime và framework có startup time phù hợp.
- Dùng Provisioned Concurrency khi cần giảm biến động cold start và có traffic dự báo.
- Đánh giá Lambda SnapStart cho runtime và phiên bản được hỗ trợ, đồng thời kiểm thử trạng thái sau restore.
- Tránh tạo nhiều kết nối database mới trong mỗi invocation.

Provisioned Concurrency chuẩn bị execution environments trước khi có request. Nó giúp giảm initialization latency nhưng có chi phí capacity được cấp trước và không thay thế việc xử lý throttling hoặc dependency bottleneck.

Tăng memory cũng tăng lượng CPU được cấp cho Lambda. Nếu workload bị giới hạn CPU hoặc cần giải nén/serialize nhiều dữ liệu, tăng memory có thể giảm duration và tổng concurrency cần thiết. Nếu bottleneck là database hoặc network, tăng memory có thể không giúp đáng kể.

## 4. Chẩn đoán timeout theo thứ tự

Khi thấy timeout, cần xác định invocation nào và bước nào chiếm thời gian.

1. Xác định function, alias/version và invocation request ID.
2. So sánh configured timeout với Duration và p95/p99.
3. Đọc CloudWatch log quanh request ID, tìm bước cuối cùng được ghi.
4. Đối chiếu X-Ray trace hoặc custom subsegment nếu đã bật tracing.
5. Kiểm tra dependency latency, network path và retry.
6. Kiểm tra memory, CPU pressure, batch size và payload size.
7. Xác định timeout gây retry ở caller, asynchronous queue hay event source mapping.
8. Kiểm thử với cùng payload và dependency ở staging.

Một log chỉ có START nhưng không có END/REPORT có thể cho thấy runtime bị dừng hoặc log cuối không được ghi; nó chưa đủ để kết luận code đang treo ở đâu. Hãy thêm log có timestamp trước/sau các dependency call và correlation ID để định vị.

Ví dụ log theo bước:

~~~python
import json
import logging
import time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def timed_call(name, operation):
    started = time.monotonic()
    logger.info(json.dumps({
        "event": "dependency_start",
        "dependency": name
    }))
    try:
        result = operation()
        logger.info(json.dumps({
            "event": "dependency_success",
            "dependency": name,
            "duration_ms": round((time.monotonic() - started) * 1000, 2)
        }))
        return result
    except Exception:
        logger.exception(json.dumps({
            "event": "dependency_failure",
            "dependency": name,
            "duration_ms": round((time.monotonic() - started) * 1000, 2)
        }))
        raise
~~~

Không log token, secret, full request body hoặc dữ liệu cá nhân chỉ để debug. Log một correlation ID và các thuộc tính cần thiết để liên kết sự kiện giữa Lambda, SQS và downstream.

## 5. Đặt timeout cho dependency và dùng thời gian còn lại

HTTP client, database driver và SDK cần timeout riêng. Nếu một dependency có thể chờ vô hạn hoặc retry quá lâu, Lambda có thể bị giữ tới hết timeout.

Nguyên tắc:

- Connection timeout ngắn hơn tổng timeout của dependency call.
- Read/request timeout phải nằm trong ngân sách thời gian còn lại của invocation.
- Retry có giới hạn, exponential backoff và jitter.
- Không bắt đầu một thao tác mới nếu thời gian còn lại không đủ để hoàn tất an toàn.
- Nếu không thể xử lý trước deadline, trả lỗi có kiểm soát để source retry theo cơ chế phù hợp.

Lambda context cung cấp thời gian còn lại bằng get_remaining_time_in_millis(). Ví dụ:

~~~python
import json

def lambda_handler(event, context):
    remaining_ms = context.get_remaining_time_in_millis()
    safety_margin_ms = 1500

    if remaining_ms <= safety_margin_ms:
        raise TimeoutError("Insufficient execution time remaining")

    dependency_budget_ms = remaining_ms - safety_margin_ms

    # Pass dependency_budget_ms to the HTTP/database client
    # and ensure its own connection/read timeouts stay within this budget.

    return {
        "statusCode": 200,
        "remainingMsAtStart": remaining_ms,
        "dependencyBudgetMs": dependency_budget_ms
    }
~~~

Đoạn code minh họa cách phân bổ deadline; client thực tế phải hỗ trợ cấu hình timeout và retry. Không chỉ kiểm tra thời gian một lần ở đầu handler nếu sau đó còn nhiều bước có thể kéo dài.

## 6. Lambda concurrency và throttling

Concurrency là số invocation đang chạy đồng thời. Một invocation chiếm một concurrency slot trong suốt thời gian thực thi.

Ước lượng concurrency trung bình theo định luật Little:

\[
Concurrency \approx RequestRate \times AverageDuration
\]

Ví dụ:

- 200 request/giây.
- Duration trung bình 0,25 giây.
- Concurrency trung bình khoảng 50.

Nếu duration tăng lên 2 giây với cùng request rate, concurrency tăng lên khoảng 400. Vì vậy, dependency chậm có thể làm Lambda throttling dù số request đến không đổi.

Throttling xảy ra khi Lambda không thể nhận thêm invocation do concurrency hoặc scaling capacity hiện có. Các nguyên nhân thường gặp:

- Account concurrency quota đã dùng hết.
- Function có Reserved Concurrency thấp hơn nhu cầu.
- Reserved Concurrency bằng 0, tức function bị chủ động throttle.
- Nhiều event source mappings cùng gọi một function.
- Provisioned Concurrency không đủ cho tải cần xử lý ngay và spillover xảy ra trong khi account concurrency bị giới hạn.
- Tốc độ tăng invocation vượt khả năng scale tức thời.
- Downstream throttling làm duration tăng, kéo theo concurrency tăng.

### 6.1. Account concurrency

Lambda có account concurrency quota theo Region. Một phần quota có thể được giữ lại cho các function khác thông qua reserved concurrency. Giá trị quota cụ thể phụ thuộc account và Region; xem Service Quotas và Lambda console thay vì giả định mọi account có cùng giới hạn.

Khi tổng concurrency của các function tiến gần quota, một function tăng tải có thể ảnh hưởng các function khác. Hãy phân tích concurrency ở cấp account, không chỉ function đang lỗi.

### 6.2. Reserved Concurrency

Reserved Concurrency dành riêng một phần account concurrency cho function và đồng thời đặt trần concurrency của function đó.

Dùng khi:

- Cần bảo đảm function quan trọng có capacity trong account.
- Muốn giới hạn một consumer để bảo vệ database hoặc API downstream.
- Cần ngăn một function burst chiếm hết account concurrency.

Nếu Reserved Concurrency quá thấp, Lambda có thể throttling dù account còn quota. Nếu đặt bằng 0, function bị tắt khả năng nhận invocation cho tới khi thay đổi cấu hình.

### 6.3. Provisioned Concurrency

Provisioned Concurrency giữ sẵn execution environments để giảm cold start. Nó không phải cơ chế tăng account concurrency quota và không tự giải quyết downstream throttling.

Dùng Provisioned Concurrency khi latency startup là vấn đề đã được đo và traffic có thể dự báo. Hãy theo dõi ProvisionedConcurrencyUtilization và ProvisionedConcurrencySpilloverInvocations nếu workload dùng tính năng này.

## 7. Cách đọc metric throttling và concurrency

CloudWatch metrics quan trọng của Lambda:

| Metric | Ý nghĩa | Cách dùng khi điều tra |
|---|---|---|
| Invocations | Số invocation được gọi | Xác định tải và traffic pattern |
| Duration | Thời gian thực thi | Tìm duration tăng hoặc gần timeout |
| Errors | Invocation kết thúc bằng lỗi | Đối chiếu log và loại exception |
| Throttles | Invocation bị từ chối do throttling | Kiểm tra account/function concurrency |
| ConcurrentExecutions | Số invocation đồng thời | So sánh với reserved/account quota |
| UnreservedConcurrentExecutions | Concurrency không được reserve | Xác định áp lực lên pool chung |
| ProvisionedConcurrencyUtilization | Mức sử dụng Provisioned Concurrency | Xem capacity cấp trước có đủ không |
| ProvisionedConcurrencySpilloverInvocations | Invocation không được phục vụ bởi provisioned capacity | Xác định spillover |
| AsyncEventAge | Tuổi event trong hàng đợi asynchronous | Phát hiện async backlog |
| AsyncEventsDropped | Event asynchronous bị loại bỏ | Điều tra event age/retry limits |
| IteratorAge | Độ trễ record stream consumer | Theo dõi Kinesis/DynamoDB Streams lag |

Metric Throttles tăng cùng ConcurrentExecutions gần giới hạn thường gợi ý concurrency pressure. Nếu Duration tăng trước rồi Throttles tăng, hãy kiểm tra dependency latency: function có thể giữ slot lâu hơn thay vì chỉ thiếu quota.

Throttles tăng nhưng ConcurrentExecutions thấp có thể do Reserved Concurrency đặt quá thấp, function bị đặt bằng 0, hoặc giới hạn scaling/configuration khác. Hãy kiểm tra function configuration và invocation source.

Không cộng tất cả metric ở các dimension khác nhau một cách tùy tiện. Xem đúng FunctionName, Resource, ExecutedVersion và concurrency type; phân biệt alias/version khi traffic được chia qua nhiều alias.

## 8. SQS event source mapping hoạt động thế nào?

SQS event source mapping là poller do Lambda quản lý. Nó nhận message từ queue, tạo batch và gọi function. Khi function xử lý thành công, Lambda xóa message. Khi invocation thất bại, message vẫn ở queue và có thể được nhận lại sau visibility timeout.

Các cấu hình chính:

| Cấu hình | Vai trò |
|---|---|
| BatchSize | Số message tối đa trong một invocation |
| MaximumBatchingWindowInSeconds | Thời gian tối đa gom batch trước khi invoke |
| FunctionResponseTypes | Bật ReportBatchItemFailures để trả lỗi theo từng message |
| ScalingConfig.MaximumConcurrency | Giới hạn concurrency của event source mapping |
| Queue visibility timeout | Khoảng thời gian message bị ẩn sau khi được receive |
| Redrive policy | Chuyển message sang DLQ sau số lần receive thất bại tối đa |
| FIFO MessageGroupId | Nhóm message giữ thứ tự xử lý |

Với SQS Standard, batch size tối đa có thể lên tới 10.000 message tùy cấu hình; với SQS FIFO tối đa 10 message mỗi batch. Một số batch size lớn hơn 10 yêu cầu MaximumBatchingWindowInSeconds ít nhất 1 giây. Luôn kiểm tra quota hiện hành và giới hạn payload tổng của invocation.

Batch size lớn giảm số lần invoke trên mỗi message nhưng có thể tăng thời gian xử lý, memory pressure và số message bị retry cùng lúc nếu một record lỗi. Batch size nhỏ giúp giảm blast radius nhưng tăng số invocation và overhead.

## 9. Visibility timeout và vòng lặp retry

Visibility timeout là khoảng thời gian message được ẩn khỏi các consumer khác sau khi SQS trả message cho event source mapping. Nếu function không hoàn tất và message chưa bị xóa trước khi timeout hết, message có thể xuất hiện lại.

AWS khuyến nghị visibility timeout của SQS queue tối thiểu bằng sáu lần Lambda function timeout cộng với maximum batching window của event source mapping.

\[
VisibilityTimeout \ge 6 \times FunctionTimeout + BatchingWindow
\]

Ví dụ:

- Lambda timeout: 30 giây.
- Maximum batching window: 5 giây.
- Visibility timeout tối thiểu theo khuyến nghị: 6 × 30 + 5 = 185 giây.

Đặt visibility timeout quá ngắn có thể khiến cùng message được xử lý đồng thời nhiều lần. Đặt quá dài khiến message lỗi phải chờ lâu mới được retry hoặc chuyển DLQ. Chọn giá trị dựa trên thời gian xử lý p99, retry behavior và yêu cầu phục hồi.

Nếu function timeout 30 giây nhưng visibility timeout chỉ 30 giây, message có thể hiện lại khi invocation đầu chưa kết thúc. Hai invocation cùng xử lý một event có thể gây duplicate write hoặc race condition.

## 10. Partial batch response: chỉ retry record thất bại

Mặc định, nếu một invocation xử lý batch SQS thất bại, toàn bộ batch có thể được trả lại queue để retry. Điều này khiến những record đã xử lý thành công bị xử lý lại.

Bật partial batch response bằng FunctionResponseTypes gồm ReportBatchItemFailures trong event source mapping. Function trả danh sách message identifier cần retry.

Ví dụ handler Python:

~~~python
import json

def process_message(record):
    body = json.loads(record["body"])
    # Validate and persist the business event idempotently.
    # Raise an exception when this message cannot be processed.

def lambda_handler(event, context):
    failures = []

    for record in event["Records"]:
        try:
            process_message(record)
        except Exception:
            failures.append({
                "itemIdentifier": record["messageId"]
            })

    return {
        "batchItemFailures": failures
    }
~~~

Khi partial batch response được bật, record không có trong batchItemFailures được xem là đã xử lý thành công và Lambda có thể xóa khỏi queue. Chỉ record được liệt kê sẽ được retry.

Lưu ý:

- Nếu handler throw exception ở cấp invocation, toàn bộ batch vẫn được coi là thất bại.
- Với FIFO queue, khi một record thất bại, nên dừng xử lý các record tiếp theo trong cùng batch và trả về record lỗi cùng các record chưa xử lý để bảo toàn ordering.
- Partial batch response không tự tạo exactly-once; message vẫn có thể được giao lại trong một số tình huống.
- Consumer phải idempotent kể cả khi đã bật partial batch response.

Bật partial batch response bằng AWS CLI:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --function-response-types ReportBatchItemFailures \
  --region ap-southeast-1
~~~

Xác minh cấu hình:

~~~bash
aws lambda get-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --region ap-southeast-1
~~~

## 11. DLQ và redrive cho SQS

Dead-letter queue (DLQ) giữ message không thể xử lý sau số lần receive được cấu hình trong redrive policy của source queue.

Ví dụ redrive policy:

~~~json
{
  "deadLetterTargetArn": "arn:aws:sqs:ap-southeast-1:111122223333:iot-events-dlq",
  "maxReceiveCount": "5"
}
~~~

Số lần nhận tối đa phải đủ để vượt qua lỗi tạm thời nhưng không để poison message làm queue retry vô hạn. Nếu maxReceiveCount quá thấp, một đợt lỗi downstream ngắn có thể đẩy nhiều message hợp lệ sang DLQ. Nếu quá cao, message lỗi có thể chiếm poller và làm chậm dữ liệu mới.

Quy trình redrive:

1. Kiểm tra ApproximateNumberOfMessagesVisible và ApproximateAgeOfOldestMessage của DLQ.
2. Phân nhóm lỗi theo exception, schema version, tenant hoặc downstream.
3. Sửa nguyên nhân trước khi replay.
4. Kiểm tra message có thể xử lý bằng code hiện tại hay cần migration.
5. Dùng SQS redrive task hoặc công cụ replay có kiểm soát.
6. Theo dõi source queue và DLQ trong suốt quá trình.
7. Xác minh idempotency để replay không nhân đôi side effect.

Với SQS Standard, message chuyển sang DLQ giữ original enqueue timestamp; retention của DLQ nên dài hơn source queue để có đủ thời gian điều tra. Với FIFO, enqueue timestamp được reset khi chuyển sang DLQ. Thiết kế retention và replay dựa trên queue type.

DLQ không sửa message hoặc tự chạy lại function. Nó chỉ giữ message bị chuyển qua redrive policy; đội vận hành vẫn cần xử lý và redrive.

## 12. Tìm nguyên nhân backlog tăng

Backlog tăng khi tốc độ message đến lớn hơn tốc độ consumer xử lý và xóa message.

Gọi:

- λ: tốc độ message đến (message/giây).
- μ: tốc độ message xử lý và xóa thành công (message/giây).
- B: số message đang chờ.

Nếu λ lớn hơn μ, backlog tăng xấp xỉ λ − μ message/giây. Nếu μ lớn hơn λ, queue có thể giảm backlog.

Ước lượng thông lượng consumer:

\[
\mu \approx \frac{ConcurrentInvocations \times BatchSize \times SuccessRatio}{AverageBatchDuration}
\]

Đây là mô hình xấp xỉ; batch có thể không đầy, record có thời gian xử lý khác nhau và throttling/downstream latency làm giảm throughput thực tế.

Ví dụ:

- 20 invocation đồng thời.
- Batch size 10.
- Average batch duration 2 giây.
- Success ratio 95%.

Throughput lý thuyết xấp xỉ 20 × 10 × 0,95 / 2 = 95 message/giây.

Nếu producer gửi 120 message/giây, backlog tăng khoảng 25 message/giây. Nếu backlog đang có 90.000 message và producer giảm còn 40 message/giây trong khi consumer xử lý 95 message/giây, thời gian tiêu backlog ước lượng:

\[
DrainTime \approx \frac{Backlog}{\mu - \lambda}
= \frac{90,000}{95 - 40}
\approx 1,636 \text{ giây}
\]

Tương đương khoảng 27 phút. Hãy dùng throughput thành công thực tế thay vì số invocation được khởi chạy.

## 13. CloudWatch metrics cho SQS backlog

Theo dõi các metric SQS trong namespace AWS/SQS:

| Metric | Ý nghĩa | Cách diễn giải |
|---|---|---|
| ApproximateNumberOfMessagesVisible | Message đang chờ và có thể được receive | Backlog chưa xử lý |
| ApproximateNumberOfMessagesNotVisible | Message đang in-flight/được consumer giữ visibility | Consumer đang nhận message hoặc xử lý chậm |
| ApproximateNumberOfMessagesDelayed | Message đang ở trạng thái delayed | Delay queue hoặc per-message delay |
| ApproximateAgeOfOldestMessage | Tuổi của message cũ nhất còn trong queue | Độ trễ end-to-end và nguy cơ vi phạm SLA |
| NumberOfMessagesSent | Message được gửi vào queue | Tốc độ producer |
| NumberOfMessagesReceived | Số lượt message được receive | Có thể lớn hơn số message duy nhất do retry |
| NumberOfMessagesDeleted | Số message được xóa | Gần với throughput xử lý thành công, nhưng cần hiểu metric semantics |
| NumberOfEmptyReceives | Polling không nhận được message | Có thể phản ánh polling dư thừa |

Đọc metrics theo cùng một time window:

- Visible tăng, NotVisible thấp: consumer capacity thấp, mapping disabled hoặc không poll được.
- Visible tăng, NotVisible tăng cao: nhiều message đang in-flight; kiểm tra invocation duration, visibility timeout và downstream.
- AgeOfOldestMessage tăng liên tục: consumer không theo kịp hoặc poison messages đang cản trở.
- Received tăng nhưng Deleted không tăng tương ứng: message được nhận lại, invocation lỗi hoặc visibility timeout lặp.
- DLQ visible tăng: lỗi message đang vượt ngưỡng receive count.

SQS metrics là approximate và được publish theo chu kỳ; đừng dùng một datapoint đơn lẻ để kết luận. So sánh trend, queue type và log thực tế.

## 14. CloudWatch metrics cho Lambda và event source mapping

Kết hợp Lambda metrics với SQS metrics để biết backlog nằm ở đâu.

| Nhóm | Metric | Dấu hiệu |
|---|---|---|
| Execution | Duration | Tăng dần hoặc gần timeout |
| Execution | Errors | Handler lỗi hoặc timeout |
| Capacity | Throttles | Lambda không nhận thêm invocation |
| Capacity | ConcurrentExecutions | Đạt reserved/account concurrency |
| Async | AsyncEventAge | Event chờ lâu trong asynchronous queue |
| Async | AsyncEventsDropped | Event bị bỏ do age/retry policy |
| Streams | IteratorAge | Consumer lag trên Kinesis/DynamoDB Streams |
| Provisioned | ProvisionedConcurrencySpilloverInvocations | Invocation vượt provisioned capacity |
| SQS | ApproximateNumberOfMessagesVisible | Queue backlog |
| SQS | ApproximateAgeOfOldestMessage | Tuổi message cũ nhất |
| SQS | ApproximateNumberOfMessagesNotVisible | Message đang in-flight |

Đối với SQS event source mapping, bật event source mapping metrics nếu cần số liệu chi tiết về polling, invocation và record processing. Các metric này có thể phát sinh chi phí CloudWatch metrics; chỉ bật các nhóm cần cho SLO và troubleshooting.

AWS X-Ray hoặc tracing tương thích giúp theo dõi thời gian ở downstream service. Nếu Lambda chỉ mất 100 ms nhưng database subsegment mất 8 giây, cần điều tra database/query/connection pool thay vì tăng Lambda memory.

## 15. Phân biệt backlog SQS với consumer lag của Kinesis

SQS và Kinesis đều có thể tạo cảm giác backlog nhưng cách đọc và retry khác nhau.

| Đặc điểm | SQS | Kinesis Data Streams |
|---|---|---|
| Đơn vị dữ liệu | Message | Record trong shard |
| Consumer model | Poll qua event source mapping | Poll hoặc Enhanced Fan-Out |
| Dấu hiệu backlog | Visible messages và age | IteratorAge / MillisBehindLatest |
| Xóa dữ liệu sau xử lý | Lambda xóa message thành công | Record vẫn tồn tại theo retention; consumer checkpoint tiến lên |
| Retry | Visibility timeout và redrive policy | Retry batch, checkpoint, shard ordering và on-failure destination |
| Poison record | Có thể chuyển SQS DLQ | Có thể chặn shard progress nếu retry policy không xử lý |
| Scaling | Mapping concurrency và queue throughput | Shard count, parallelization factor và consumer capacity |

Với Kinesis, IteratorAge tăng nghĩa là consumer đang tụt lại so với latest record. Kiểm tra shard hot, batch retry, checkpoint và downstream. Tăng Lambda concurrency không luôn giúp nếu một shard bị giới hạn bởi ordering hoặc partition key.

## 16. Kiểm soát concurrency để bảo vệ downstream

Tăng concurrency có thể tăng throughput, nhưng cũng tăng số kết nối database, API requests và chi phí downstream.

Ví dụ database chỉ chịu được 200 connection. Nếu mỗi Lambda invocation mở 5 connection và function chạy đồng thời 100 lần, nhu cầu lý thuyết là 500 connection, vượt khả năng database.

Các cách kiểm soát:

- Đặt Reserved Concurrency cho function để giới hạn tổng invocation.
- Đặt ScalingConfig.MaximumConcurrency cho từng SQS event source mapping.
- Đảm bảo tổng maximum concurrency của các mappings không vượt reserved concurrency dành cho function.
- Dùng connection reuse và pool có giới hạn.
- Buffer bằng SQS để tách tốc độ ingest khỏi tốc độ downstream.
- Dùng exponential backoff và jitter khi downstream trả 429/5xx.
- Giảm batch size nếu một invocation tạo quá nhiều thao tác song song.
- Tách consumer workload theo queue/priority để message quan trọng không bị backlog bởi batch lớn.

Ví dụ đặt maximum concurrency cho event source mapping:

~~~bash
aws lambda update-event-source-mapping \
  --uuid EVENT_SOURCE_MAPPING_UUID \
  --scaling-config '{"MaximumConcurrency":40}' \
  --region ap-southeast-1
~~~

MaximumConcurrency là giới hạn cho mapping đó. Nếu function có nhiều mapping, phải tính tổng concurrency tối đa của tất cả mapping và cả các nguồn invoke khác.

Không đặt Reserved Concurrency thấp hơn mức concurrency tối đa mà các event source mappings được kỳ vọng sử dụng. Nếu mapping cố scale vượt giới hạn function, Lambda throttling và message sẽ quay lại queue sau visibility timeout.

## 17. Batch size, batching window và xử lý hiệu quả

Batch size ảnh hưởng số message mỗi invocation. Batching window cho phép poller chờ thêm message để tạo batch lớn hơn, đánh đổi latency.

Chọn batch size dựa trên:

- Kích thước payload và giới hạn tổng payload invocation.
- Thời gian xử lý mỗi message.
- Mức độ độc lập giữa các record.
- Khả năng xử lý partial failure.
- Memory và CPU của function.
- Downstream request rate.
- SLA của message age.

Batch size lớn có thể tăng throughput khi handler xử lý vectorized/bulk write. Nhưng nếu một message lỗi làm cả batch thất bại, nhiều record tốt sẽ bị xử lý lại. Bật partial batch response để giảm phạm vi retry.

Batching window hữu ích khi producer gửi message rải rác; poller có thể gom message để giảm invocation count. Không tăng window nếu SLA yêu cầu xử lý gần real-time.

Nếu mỗi message gọi database một lần, cân nhắc batch write API hoặc gom các record theo key trước khi ghi. Hãy đảm bảo bulk operation có thể retry idempotently và xác định rõ record nào đã được commit khi request chỉ thành công một phần.

## 18. Asynchronous invocation: retry và event age

Asynchronous invocation thường dùng với S3 notifications, EventBridge hoặc API Invoke với InvocationType=Event. Lambda nhận event vào hàng đợi nội bộ rồi trả kết quả chấp nhận event cho caller.

Với function error, Lambda mặc định retry hai lần sau lần gọi đầu. Với lỗi throttling hoặc lỗi hệ thống, Lambda có thể retry theo exponential backoff trong khoảng thời gian event còn hợp lệ. Event age và số retry có thể cấu hình; event có thể hết tuổi và bị loại bỏ nếu không xử lý kịp.

Cấu hình asynchronous invocation có thể dùng:

- MaximumEventAgeInSeconds: tuổi tối đa event được giữ trước khi loại bỏ.
- MaximumRetryAttempts: số lần retry function error.
- OnFailure destination hoặc DLQ: lưu event thất bại để điều tra.
- OnSuccess destination: ghi lại kết quả thành công nếu cần audit.

Phân biệt async destination và SQS redrive DLQ:

| Cơ chế | Áp dụng | Chứa gì |
|---|---|---|
| Lambda asynchronous DLQ | Async invocation | Event gốc không xử lý thành công |
| Lambda async OnFailure destination | Async invocation | Thông tin invocation, response/error metadata và event |
| SQS source queue DLQ | SQS event source mapping | Message gốc vượt maxReceiveCount của queue redrive policy |
| Stream on-failure destination | Kinesis/DynamoDB Streams event source mapping | Batch/record thất bại theo cấu hình source mapping |

Không cấu hình một loại DLQ rồi kỳ vọng nó nhận lỗi của mọi invocation model. Hãy xác định event đi qua cơ chế nào.

## 19. Kịch bản xử lý sự cố: timeout làm SQS backlog tăng

Giả sử một SQS queue nhận 500 message/giây. Lambda xử lý mỗi batch 10 message, timeout 30 giây và Reserved Concurrency 100. Database bắt đầu tăng latency từ 200 ms lên 5 giây.

Dấu hiệu:

- Lambda Duration tăng.
- ConcurrentExecutions tăng gần 100.
- Throttles tăng.
- SQS ApproximateNumberOfMessagesVisible tăng.
- ApproximateAgeOfOldestMessage tăng.
- ApproximateNumberOfMessagesNotVisible tăng.
- NumberOfMessagesReceived cao hơn NumberOfMessagesDeleted do retry.

Chuỗi nguyên nhân:

1. Database chậm làm mỗi invocation giữ concurrency lâu hơn.
2. Với cùng message rate, concurrency cần thiết tăng theo request rate × duration.
3. Reserved Concurrency chặn Lambda ở 100.
4. Poller không xử lý kịp message mới; visible backlog tăng.
5. Invocation timeout hoặc lỗi khiến message không bị xóa.
6. Visibility timeout hết hạn, message xuất hiện lại và receive count tăng.
7. Message độc hại hoặc payload gây lỗi lặp lại có thể chuyển sang DLQ.

Runbook:

1. Kiểm tra Lambda Duration, Errors, Throttles và ConcurrentExecutions.
2. Kiểm tra SQS visible, not-visible, age và DLQ.
3. Xác định database/API có throttling, lock, connection exhaustion hoặc latency cao không.
4. Giảm event source mapping maximum concurrency nếu downstream đang quá tải.
5. Khôi phục dependency hoặc chuyển workload sang queue riêng nếu có thể.
6. Bật partial batch response nếu handler chưa hỗ trợ.
7. Kiểm tra visibility timeout tối thiểu theo khuyến nghị.
8. Kiểm tra redrive policy và DLQ; giữ poison messages để điều tra.
9. Sau khi downstream phục hồi, tăng concurrency từ từ và đo drain rate.
10. Xác minh oldest message age giảm, deleted rate lớn hơn sent rate và DLQ không tiếp tục tăng.

Không tăng concurrency vô hạn trong lúc database đã quá tải. Điều đó có thể làm sự cố lan rộng sang hệ thống dữ liệu.

## 20. Cấu hình và quan sát bằng AWS CLI

Lấy cấu hình Lambda:

~~~bash
aws lambda get-function-configuration \
  --function-name orders-consumer \
  --region ap-southeast-1
~~~

Cập nhật timeout và memory sau khi đã đo:

~~~bash
aws lambda update-function-configuration \
  --function-name orders-consumer \
  --timeout 45 \
  --memory-size 1024 \
  --region ap-southeast-1
~~~

Xem concurrency của function:

~~~bash
aws lambda get-function-concurrency \
  --function-name orders-consumer \
  --region ap-southeast-1
~~~

Xem event source mapping:

~~~bash
aws lambda list-event-source-mappings \
  --function-name orders-consumer \
  --region ap-southeast-1
~~~

Xem queue attributes:

~~~bash
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-events \
  --attribute-names All \
  --region ap-southeast-1
~~~

Các lệnh update thay đổi cấu hình production. Hãy dùng change control, kiểm tra alias/version và thử trên staging trước khi áp dụng. Không cập nhật đồng thời timeout, batch size, concurrency và retry settings nếu chưa có baseline; thay đổi từng nhóm để có thể xác định tác động.

## 21. Bảo mật và độ tin cậy khi replay

SQS message và DLQ có thể chứa dữ liệu nghiệp vụ hoặc thông tin nhạy cảm. Chỉ cấp quyền receive/delete/send/redrive cho principal cần thiết. Dùng encryption at rest bằng SQS-managed key hoặc KMS key theo yêu cầu; kiểm tra key policy khi Lambda hoặc operator truy cập queue mã hóa.

Một số quyền thường gặp:

- Lambda execution role cần quyền ghi log và quyền truy cập dependency.
- Lambda execution role cần quyền sqs:ReceiveMessage, sqs:DeleteMessage và sqs:GetQueueAttributes trên source queue; nếu queue dùng customer managed KMS key, kiểm tra thêm quyền kms:Decrypt và key policy.
- Operator cần quyền đọc DLQ và khởi tạo redrive task.
- Producer chỉ cần quyền gửi message vào source queue.
- Không cấp quyền đọc DLQ rộng cho ứng dụng không cần xử lý dữ liệu lỗi.

Replay phải giữ event ID gốc và có thể gắn replay metadata như replayBatchId, replayedAt và originalQueue. Consumer cần phân biệt replay với event mới nếu nghiệp vụ yêu cầu. Trước khi redrive hàng loạt, kiểm tra capacity của target để tránh tạo một burst lớn sau outage.

## 22. Checklist kiểm thử và vận hành

Trước khi đưa Lambda consumer vào production:

- Xác định invocation model và retry semantics.
- Chọn timeout theo p99 duration và deadline của upstream.
- Cấu hình timeout cho HTTP/DB client thấp hơn thời gian Lambda còn lại.
- Đo cold start, memory, CPU và dependency latency.
- Tính concurrency từ request rate × duration.
- Đặt Reserved Concurrency để bảo vệ downstream.
- Đặt MaximumConcurrency cho SQS mapping nếu cần.
- Đảm bảo tổng mapping concurrency phù hợp với reserved/account concurrency.
- Đặt visibility timeout tối thiểu theo khuyến nghị AWS.
- Chọn batch size và batching window theo payload, SLA và downstream.
- Bật partial batch response và kiểm thử record lỗi giữa batch.
- Cấu hình SQS redrive policy và DLQ retention.
- Thiết kế idempotency cho duplicate và replay.
- Tạo dashboard cho Lambda, SQS và downstream.
- Cảnh báo theo oldest message age, visible backlog, throttles, errors và duration.
- Load test với burst, poison message, dependency latency và database throttling.
- Diễn tập DLQ redrive và xác nhận drain rate sau khi phục hồi.

### 22.1. Ma trận kiểm thử

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Handler vượt timeout | Invocation lỗi; source retry theo đúng semantics |
| Database latency tăng | Timeout/remaining time được kiểm soát; concurrency không làm sập DB |
| Reserved Concurrency đạt trần | Throttles được cảnh báo; queue không mất message |
| Batch có một record lỗi | Partial batch response chỉ retry record đó |
| FIFO batch có record lỗi | Record sau lỗi không bị xử lý vượt thứ tự |
| Visibility timeout quá ngắn | Test phát hiện duplicate concurrent processing |
| Poison message | Message chuyển DLQ theo maxReceiveCount |
| Downstream outage | Backlog tăng có kiểm soát và giảm sau recovery |
| Redrive DLQ | Message replay không tạo side effect duplicate |
| Producer burst | Event source mapping scale trong giới hạn downstream |

## Kết luận

Lambda timeout, throttling và queue backlog là ba triệu chứng có thể liên kết thành một vòng lặp: dependency chậm kéo dài invocation, concurrency tăng, Lambda bị throttling, message không được xóa, visibility timeout hết hạn và backlog tiếp tục tăng. Chẩn đoán đúng cần xác định invocation model, đọc Lambda/SQS metrics cùng một time window và tìm dependency thực sự làm chậm handler.

Với SQS, visibility timeout, batch size, partial batch response, maximum concurrency và DLQ quyết định cách hệ thống phục hồi. Reserved Concurrency bảo vệ account và downstream; Provisioned Concurrency giảm cold start. Hai cơ chế này giải quyết vấn đề khác nhau. Tăng concurrency chỉ có ích khi downstream còn capacity.

Một consumer production cần timeout cho dependency, idempotency, retry có giới hạn, DLQ và redrive runbook. Theo dõi oldest message age, visible backlog, receive/delete rate, Lambda duration/errors/throttles và downstream latency để biết backlog có đang được tiêu hay không. Hãy kiểm thử burst, poison message và dependency outage trước khi vận hành tải thật.

## Tài liệu tham khảo

- [AWS Lambda execution environment and timeout](https://docs.aws.amazon.com/lambda/latest/dg/configuration-timeout.html)
- [AWS Lambda concurrency](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [Reserved concurrency](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
- [Provisioned Concurrency](https://docs.aws.amazon.com/lambda/latest/dg/provisioned-concurrency.html)
- [Troubleshooting Lambda function errors](https://docs.aws.amazon.com/lambda/latest/dg/troubleshooting-execution.html)
- [Lambda asynchronous invocation error handling](https://docs.aws.amazon.com/lambda/latest/dg/invocation-async-error-handling.html)
- [Using Lambda with Amazon SQS](https://docs.aws.amazon.com/lambda/latest/dg/with-sqs.html)
- [Configuring an SQS event source mapping](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-configure.html)
- [Handling errors for an SQS event source](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [Partial batch response for SQS](https://docs.aws.amazon.com/lambda/latest/dg/services-sqs-errorhandling.html)
- [SQS visibility timeout](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-visibility-timeout.html)
- [Configuring an SQS dead-letter queue](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [Monitoring Lambda functions with CloudWatch](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics.html)
- [Monitoring Amazon SQS queues using CloudWatch](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-available-cloudwatch-metrics.html)
- [Lambda event source mapping metrics](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-metrics-types.html)
- [AWS X-Ray with Lambda](https://docs.aws.amazon.com/lambda/latest/dg/services-xray.html)
- [Lambda best practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [AWS Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)

