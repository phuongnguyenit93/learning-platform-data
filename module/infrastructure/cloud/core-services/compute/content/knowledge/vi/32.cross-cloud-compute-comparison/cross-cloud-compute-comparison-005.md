# Đối chiếu mô hình hàm, trigger và điều phối sự kiện

Function serverless cho phép chạy mã theo yêu cầu mà không phải tự quản lý máy chủ. Một function có thể được gọi trực tiếp qua HTTP, được kích hoạt khi có message trong queue, khi object được tạo, khi dữ liệu thay đổi hoặc theo lịch. Khi một nghiệp vụ gồm nhiều bước, các function có thể được nối bằng event bus, queue hoặc workflow orchestration.

AWS, Microsoft Azure và Google Cloud đều cung cấp mô hình function theo sự kiện, nhưng khác nhau ở cách khai báo trigger, cách event được chuyển tới function, mô hình retry, khả năng giữ trạng thái và dịch vụ điều phối. Những khác biệt này ảnh hưởng tới độ tin cậy, độ trễ, chi phí, khả năng quan sát và mức độ phụ thuộc nhà cung cấp. Bài học này đối chiếu các mô hình function, trigger và orchestration để giúp lựa chọn dịch vụ phù hợp cũng như thiết kế workload có thể vận hành hoặc chuyển đổi giữa các cloud.

## 1. Ba lớp cần phân biệt

Khi thiết kế serverless, hãy tách ba lớp:

1. **Function model:** cách mã được đóng gói, khởi chạy, cấp tài nguyên và kết thúc.
2. **Trigger/event source:** sự kiện nào khởi động function và sự kiện được chuyển tới function theo cách nào.
3. **Orchestration:** cách phối hợp nhiều function hoặc dịch vụ thành một quy trình nghiệp vụ có thứ tự, nhánh, retry và trạng thái.

Ba lớp có liên quan nhưng không thay thế lẫn nhau. Một HTTP trigger có thể gọi trực tiếp function mà không cần workflow. Một queue trigger có thể tự retry message theo cơ chế của event source. Một workflow engine có thể gọi nhiều function, chờ kết quả, rẽ nhánh và lưu trạng thái giữa các bước.

~~~mermaid
flowchart TD
    A[Event producer] --> B[Trigger / event source]
    B --> C[Function runtime]
    C --> D[Business logic]
    D --> E[Result or side effect]
    D --> F[Event / queue / service]
    F --> G[Orchestrator]
    G --> H[Function or service step]
    H --> I[Next step / retry / compensation]
~~~

Ví dụ, khi khách hàng đặt hàng:

- API gateway nhận HTTP request và gọi function tạo đơn.
- Function ghi đơn vào database và phát event OrderCreated.
- Queue hoặc event bus chuyển event tới function kiểm tra tồn kho.
- Workflow điều phối thanh toán, đặt vận chuyển và thông báo.
- Nếu thanh toán thất bại, workflow có thể chạy bước bù trừ để giải phóng tồn kho.

## 2. Function model trên ba nền tảng

Các dịch vụ thường được dùng để triển khai function:

| Nền tảng | Mô hình function tiêu biểu | Cách kích hoạt thường gặp | Dịch vụ điều phối liên quan |
|---|---|---|---|
| AWS | AWS Lambda | Gọi trực tiếp, API Gateway, Function URL, event source mapping, event notification | AWS Step Functions, EventBridge |
| Microsoft Azure | Azure Functions | HTTP trigger, Timer trigger, Queue/Service Bus/Event Grid trigger, binding và extension | Durable Functions, Logic Apps |
| Google Cloud | Cloud Functions / Cloud Run functions tùy thế hệ và giao diện sản phẩm | HTTP, Pub/Sub, Eventarc và các event provider | Workflows, Eventarc, Cloud Tasks |

Tên sản phẩm và cách tích hợp có thể thay đổi theo thế hệ dịch vụ, region và trải nghiệm quản trị. Khi triển khai, cần kiểm tra tài liệu của SKU/runtime cụ thể. Bảng này mô tả các mô hình kiến trúc, không phải danh sách đầy đủ mọi trigger.

### 2.1. AWS Lambda

Lambda chạy function trong execution environment do AWS quản lý. Function có thể được gọi đồng bộ qua API hoặc bất đồng bộ qua các dịch vụ phát event. Với một số event source như SQS, Kinesis hoặc DynamoDB Streams, Lambda dùng event source mapping để poll/đọc dữ liệu và chuyển batch tới function.

Các điểm đáng chú ý:

- Event source mapping quản lý việc đọc từ một số stream/queue và gọi function.
- EventBridge định tuyến event theo rule tới nhiều target, trong đó có Lambda.
- API Gateway và Lambda Function URL hỗ trợ mô hình HTTP request-response.
- Step Functions điều phối quy trình nhiều bước và quản lý trạng thái workflow.
- Lambda có các tùy chọn concurrency và provisioned concurrency để điều khiển khả năng phục vụ và cold start.

Cần phân biệt function được gọi trực tiếp với function được kích hoạt qua event source mapping; hai đường đi có semantics retry, batch và ordering khác nhau.

### 2.2. Azure Functions

Azure Functions tổ chức ứng dụng quanh function và trigger. Trigger xác định sự kiện làm function chạy; binding có thể đơn giản hóa việc đọc hoặc ghi tới dịch vụ khác mà không cần tự quản lý toàn bộ client code.

Các điểm đáng chú ý:

- HTTP trigger phục vụ request-response.
- Timer trigger chạy theo lịch.
- Queue Storage, Service Bus, Event Grid, Event Hubs và Blob Storage có thể kích hoạt function thông qua trigger/extension tương ứng.
- Durable Functions bổ sung orchestration stateful, activity, entity và các pattern như fan-out/fan-in.
- Hosting plan ảnh hưởng tới scale, cold start, networking và cách tính phí.

Binding tiện lợi nhưng tạo thêm lớp cấu hình. Với nghiệp vụ cần kiểm soát transaction, retry hoặc client behavior chính xác, cần hiểu binding đang thực hiện thao tác gì và khi nào.

### 2.3. Google Cloud Functions và Cloud Run functions

Google Cloud cung cấp function theo hướng event-driven và HTTP. Cách triển khai, tên sản phẩm và khả năng runtime phụ thuộc thế hệ dịch vụ; các function thế hệ mới gắn với nền tảng Cloud Run và cơ chế Eventarc cho event delivery.

Các điểm đáng chú ý:

- HTTP function xử lý request đồng bộ.
- Event-driven function nhận event thông qua Eventarc hoặc tích hợp sự kiện của dịch vụ.
- Pub/Sub thường được dùng để truyền message và tách producer khỏi consumer.
- Cloud Scheduler có thể phát sự kiện theo lịch, thường qua Pub/Sub hoặc HTTP target.
- Workflows điều phối các bước gọi Google Cloud service hoặc endpoint HTTP.
- Cloud Tasks phù hợp với việc giao task có lịch thực thi, retry và kiểm soát tốc độ tới một endpoint.

Cần phân biệt event routing của Eventarc, messaging của Pub/Sub, task delivery của Cloud Tasks và orchestration state của Workflows. Chúng giải quyết các bài toán liên quan nhưng không cùng chức năng.

## 3. Đối chiếu function execution model

| Tiêu chí | AWS Lambda | Azure Functions | Google Cloud functions |
|---|---|---|---|
| Đơn vị triển khai | Function/package hoặc container image | Function trong Function App | Function/service triển khai theo thế hệ runtime |
| HTTP | API Gateway, Function URL hoặc tích hợp khác | HTTP trigger | HTTP function/Cloud Run functions |
| Event-driven | Event source mapping, direct service invocation, EventBridge | Trigger và extension | Eventarc, Pub/Sub và tích hợp event |
| Lập lịch | EventBridge Scheduler/rule | Timer trigger | Cloud Scheduler |
| Workflow | Step Functions | Durable Functions, Logic Apps | Workflows |
| Message/task delivery | SQS, SNS, EventBridge và dịch vụ liên quan | Storage Queue, Service Bus, Event Grid | Pub/Sub, Cloud Tasks |
| Scaling | Theo concurrency và event source | Theo hosting plan và trigger | Theo cấu hình Cloud Run/function và event source |
| State dài hạn | Thường lưu ngoài function; Step Functions giữ workflow state | Durable Functions hỗ trợ orchestration state | Workflows giữ execution state |
| Ràng buộc chính | IAM, event source mapping, Lambda limits | Hosting plan, extension, binding và trigger semantics | Eventarc/Pub/Sub/Cloud Run integration và quota |

Không nên kết luận nền tảng nào “tốt nhất” chỉ từ tên dịch vụ. Hãy so sánh theo latency, event volume, execution duration, concurrency, networking, state, retry, operational tooling và tổng chi phí.

## 4. HTTP trigger và request-response

HTTP trigger phù hợp khi caller cần nhận phản hồi ngay, ví dụ:

- API đọc thông tin đơn hàng.
- Endpoint xác thực dữ liệu.
- Webhook từ hệ thống đối tác.
- API tạo một tác vụ và trả về task ID.
- Endpoint quản trị hoặc callback.

Luồng cơ bản:

1. Client gửi HTTP request.
2. API gateway hoặc ingress xác thực, áp dụng quota và định tuyến.
3. Function được gọi.
4. Function kiểm tra input và thực hiện logic.
5. Function trả status code và response.
6. Gateway trả kết quả cho client.

HTTP trigger phù hợp với tác vụ ngắn và có deadline rõ ràng. Nếu công việc kéo dài hoặc cần nhiều bước, API nên ghi nhận yêu cầu, đưa message vào queue/workflow và trả 202 Accepted cùng mã theo dõi. Client truy vấn trạng thái sau đó thay vì giữ kết nối mở trong toàn bộ quy trình.

### 4.1. Đồng bộ và bất đồng bộ

| Mô hình | Hành vi | Dùng khi |
|---|---|---|
| Synchronous | Caller chờ kết quả của function | Tác vụ ngắn, kết quả cần ngay |
| Asynchronous event | Producer gửi event và không chờ toàn bộ xử lý | Tác vụ nền, fan-out, xử lý theo sự kiện |
| Queue/task | Message được giữ cho tới khi consumer xử lý hoặc hết retention | Cần buffer, retry và backpressure |
| Workflow | Engine điều phối nhiều bước và lưu tiến trình | Nghiệp vụ nhiều bước, có nhánh/chờ/retry |

Không nên biến mọi HTTP request thành synchronous function chỉ vì cách gọi đơn giản. Giữ kết nối quá lâu có thể gặp timeout của client, gateway hoặc runtime; đồng thời làm tài nguyên bị giữ trong thời gian chờ dependency.

## 5. Trigger là gì và event source khác nhau thế nào?

Trigger là điều kiện hoặc cơ chế làm function được gọi. Event source là hệ thống phát hoặc lưu event. Một số tích hợp đẩy event trực tiếp tới function; một số để nền tảng poll queue/stream; một số dùng event router trung gian.

Các kiểu thường gặp:

- **Push delivery:** nguồn hoặc router gửi event tới endpoint/function.
- **Polling:** adapter/event source mapping đọc queue hoặc stream theo chu kỳ hoặc liên tục.
- **Direct invocation:** service gọi function bằng API.
- **Schedule:** scheduler phát event theo lịch.
- **Webhook:** hệ thống ngoài gọi HTTP endpoint khi có thay đổi.
- **Stream subscription:** consumer đọc liên tục từ stream hoặc partition.

Sự khác biệt ảnh hưởng tới latency, retry, ordering, batch size, checkpoint và chi phí. Cần xác định ai chịu trách nhiệm poll, ai giữ message khi function lỗi và nơi cấu hình retry.

## 6. Các nhóm trigger phổ biến

| Nhóm trigger | AWS | Azure | Google Cloud |
|---|---|---|---|
| HTTP/API | API Gateway, Function URL, ALB integration | HTTP trigger, API Management integration | HTTP function, API Gateway/Cloud Run integration |
| Queue | SQS, SNS subscription | Storage Queue, Service Bus | Pub/Sub, Cloud Tasks |
| Event bus/router | EventBridge | Event Grid | Eventarc |
| Object storage | S3 event notification | Blob Storage trigger, Event Grid | Cloud Storage events qua Eventarc |
| Database/change feed | DynamoDB Streams, một số database stream integration | Cosmos DB trigger/change feed | Firestore events, một số event integration |
| Stream | Kinesis, MSK và nguồn hỗ trợ khác | Event Hubs | Pub/Sub và dịch vụ stream liên quan |
| Schedule | EventBridge Scheduler | Timer trigger | Cloud Scheduler |
| Workflow callback | Step Functions integration/callback | Durable Functions/Logic Apps | Workflows callback/HTTP integration |

Các tên trong bảng là ví dụ đại diện. Trigger cụ thể có thể yêu cầu extension, connector, event source mapping, quyền IAM hoặc cấu hình subscription.

## 7. Push event, polling và event source mapping

### 7.1. Push delivery

Với push delivery, event router hoặc producer gửi request tới function endpoint. Ví dụ, event bus nhận event rồi route tới function target.

Ưu điểm:

- Latency thấp khi nguồn phát event có thể gửi ngay.
- Tách producer khỏi địa chỉ function nhờ event router.
- Có thể lọc và định tuyến theo event type.

Cần quan tâm:

- Endpoint có thể tạm thời không nhận request.
- Router có retry policy và thời gian giữ event riêng.
- Authentication giữa router và function.
- Giới hạn concurrency khi event burst.
- Duplicate delivery và idempotency.

### 7.2. Polling và event source mapping

Với polling, adapter hoặc nền tảng đọc message từ queue/stream rồi gọi function. Ví dụ, Lambda event source mapping đọc SQS hoặc Kinesis; Azure Functions host/extension đọc queue hoặc stream; consumer trên Google Cloud có thể nhận Pub/Sub push hoặc pull theo mô hình tích hợp.

Ưu điểm:

- Consumer có thể xử lý batch.
- Queue/stream hấp thụ burst và tách producer khỏi consumer.
- Backpressure có thể được điều chỉnh qua concurrency, batch và consumer rate.

Cần quan tâm:

- Polling frequency hoặc long polling.
- Visibility timeout/lease/ack deadline.
- Batch size và partial failure.
- Checkpoint hoặc offset commit.
- Scale theo queue depth hoặc lag.
- Retry và poison message.

### 7.3. Chọn mô hình

Dùng push khi cần event routing linh hoạt và nguồn có cơ chế delivery phù hợp. Dùng queue/polling khi cần buffer, kiểm soát tốc độ consumer, xử lý batch hoặc giữ message trong thời gian consumer gián đoạn. Dùng stream khi cần nhiều consumer độc lập, replay hoặc xử lý theo partition/offset.

## 8. Event envelope và hợp đồng dữ liệu

Một event nên có cấu trúc ổn định để consumer không phụ thuộc quá nhiều vào cấu trúc nội bộ của producer.

Ví dụ event envelope trung lập:

~~~json
{
  "id": "evt-8f2a",
  "type": "order.created",
  "source": "checkout-service",
  "subject": "orders/ord-1042",
  "time": "2026-11-22T10:15:00Z",
  "schemaVersion": "1.2",
  "correlationId": "req-77a1",
  "data": {
    "orderId": "ord-1042",
    "customerId": "cus-501",
    "total": 125.50,
    "currency": "USD"
  }
}
~~~

Các trường quan trọng:

- id: định danh duy nhất của event.
- type: loại sự kiện theo domain.
- source: hệ thống phát event.
- subject: đối tượng nghiệp vụ liên quan.
- time: thời điểm event được tạo.
- schemaVersion: phiên bản hợp đồng dữ liệu.
- correlationId: liên kết các bước trong một nghiệp vụ.
- data: payload nghiệp vụ.

Không nên đưa secret, access token hoặc dữ liệu cá nhân không cần thiết vào event. Event thường được lưu trong queue, log hoặc dead-letter storage nên có thể tồn tại lâu hơn request gốc.

## 9. Delivery semantics: at-most-once, at-least-once và effectively-once

Event-driven function thường phải xử lý tình huống message có thể được gửi lại.

| Semantics | Ý nghĩa | Hệ quả |
|---|---|---|
| At-most-once | Event không được gửi lại sau một lần giao | Có thể mất event nếu lỗi ở thời điểm không thuận lợi |
| At-least-once | Event được thử giao cho tới khi đạt điều kiện thành công hoặc hết policy | Có thể xử lý trùng |
| Exactly-once | Mỗi event tạo hiệu ứng đúng một lần theo định nghĩa hệ thống | Khó đạt xuyên suốt nhiều dịch vụ nếu không có transaction chung |
| Effectively-once | Cho phép giao lặp nhưng deduplicate/idempotency để hiệu ứng nghiệp vụ chỉ xảy ra một lần | Cần lưu trạng thái xử lý và thiết kế side effect an toàn |

Nhiều tích hợp serverless có semantics at-least-once hoặc có thể phát lại trong một số tình huống. Không nên giả định event chỉ tới đúng một lần. Đọc tài liệu của từng trigger để hiểu delivery guarantee, retry window và cách xác nhận thành công.

### 9.1. Idempotency

Một handler idempotent có thể nhận cùng event nhiều lần mà không tạo hiệu ứng nghiệp vụ lặp.

Ví dụ:

~~~python
def handle_order_created(event, repository, inventory):
    event_id = event["id"]

    if repository.was_processed(event_id):
        return {"status": "duplicate_ignored"}

    order_id = event["data"]["orderId"]

    # Thực hiện thao tác có khóa/idempotency key phù hợp.
    inventory.reserve_once(
        order_id=order_id,
        idempotency_key=event_id
    )

    repository.mark_processed(event_id)
    return {"status": "processed"}
~~~

Đây là pseudocode: trong hệ thống thực, kiểm tra trùng, side effect và ghi nhận hoàn tất cần được bảo vệ bằng transaction, unique constraint, inbox/outbox pattern hoặc cơ chế idempotency của dịch vụ. Nếu chỉ đánh dấu processed sau side effect mà không có tính nguyên tử, process crash giữa hai thao tác vẫn có thể gây lặp.

## 10. Ordering và partition

Không phải queue hoặc event bus nào cũng bảo đảm thứ tự toàn cục. Một số dịch vụ chỉ bảo đảm thứ tự trong một partition, message group hoặc session key; một số event router không cam kết ordering.

Nếu nghiệp vụ yêu cầu thứ tự, cần xác định:

- Thứ tự được bảo đảm trong phạm vi nào: toàn queue, partition, key hay session.
- Consumer có xử lý đồng thời nhiều message cùng key không.
- Retry có làm message sau vượt message trước không.
- Có cơ chế sequence number hoặc version để phát hiện event cũ không.
- Có thể xử lý event đến muộn bằng state reconciliation không.

Ví dụ, thay đổi số dư tài khoản cần được xử lý theo account key hoặc bằng transaction/version check. Không nên dựa vào thứ tự thời gian event nếu hệ thống phân tán có thể giao event trễ hoặc trùng.

## 11. Retry, dead-letter queue và poison event

Retry giúp khôi phục lỗi tạm thời như network timeout hoặc dịch vụ phụ trợ gián đoạn. Nhưng retry không sửa được payload sai, schema không hợp lệ hoặc lỗi logic tái diễn.

Một chính sách retry cần xác định:

- Lỗi nào retry được.
- Số lần retry hoặc thời hạn retry.
- Backoff và jitter.
- Visibility timeout/ack deadline hoặc thời gian router giữ event.
- Batch có bị retry toàn bộ hay chỉ phần thất bại.
- Khi nào event được chuyển tới dead-letter queue (DLQ) hoặc dead-letter destination.
- Ai xử lý và replay event trong DLQ.

Poison event là message liên tục làm consumer thất bại. Nếu không cách ly, nó có thể chặn partition hoặc tạo vòng retry tốn kém.

### 11.1. Xử lý DLQ

Quy trình DLQ nên gồm:

1. Lưu event gốc và metadata lỗi.
2. Ghi retry count, lần lỗi cuối và correlation ID.
3. Phân loại lỗi dữ liệu, lỗi dependency hay lỗi code.
4. Sửa payload hoặc phát hành bản sửa consumer nếu cần.
5. Kiểm tra idempotency trước replay.
6. Replay theo batch nhỏ và theo dõi kết quả.
7. Giữ audit về ai replay, thời điểm và số event.

Không replay toàn bộ DLQ trực tiếp vào production nếu chưa biết nguyên nhân. Một event có side effect đã xảy ra một phần có thể gây duplicate nếu xử lý lại không an toàn.

## 12. Batch processing và partial failure

Batch giúp giảm overhead khi một invocation xử lý nhiều message. Tuy nhiên, batch tạo ra quyết định quan trọng khi một phần message thất bại.

Các mô hình:

- **All-or-nothing:** cả batch được xem là thất bại nếu một message lỗi; toàn batch có thể được gửi lại.
- **Partial batch response:** function chỉ báo những message thất bại để event source retry phần cần thiết, nếu tích hợp hỗ trợ.
- **Per-record checkpoint:** stream consumer ghi nhận offset/checkpoint theo semantics của nguồn.
- **Split batch:** chia batch lỗi thành các phần nhỏ hơn để cô lập poison message, nếu nền tảng hỗ trợ.

Batch size lớn tăng throughput nhưng cũng tăng memory, duration và phạm vi retry. Cần cân bằng batch size, visibility timeout, function timeout, maximum concurrency và downstream capacity.

## 13. Orchestration và choreography

Có hai cách phổ biến để phối hợp nhiều function:

**Orchestration:** một workflow engine giữ trạng thái và điều khiển bước tiếp theo. Nó biết bước nào đã hoàn thành, bước nào retry, bước nào chờ và nhánh nào cần chạy.

**Choreography:** các service phát event và service khác phản ứng. Không có một bộ điều khiển trung tâm nắm toàn bộ luồng; hợp đồng event và quy tắc domain quyết định bước kế tiếp.

| Tiêu chí | Orchestration | Choreography |
|---|---|---|
| Điều khiển luồng | Tập trung trong workflow | Phân tán giữa các consumer |
| Trạng thái quy trình | Workflow engine lưu trạng thái | Mỗi service quản lý state của mình |
| Quan sát | Có execution history tập trung | Cần correlation ID và trace xuyên service |
| Phụ thuộc | Gắn với engine và workflow definition | Gắn với event contract và broker |
| Phù hợp | Quy trình nhiều bước, nhánh, chờ, timeout | Event-driven domain, fan-out, service độc lập |
| Rủi ro | Workflow trở thành nơi chứa quá nhiều business logic | Luồng tổng thể khó hiểu nếu event graph quá phức tạp |

Có thể kết hợp cả hai: workflow điều phối một saga cấp cao, còn các bước nội bộ phát event để các service khác phản ứng.

## 14. Dịch vụ orchestration trên từng cloud

| Nền tảng | Orchestration tiêu biểu | Mô hình |
|---|---|---|
| AWS | Step Functions | State machine với task, choice, parallel, map, wait, retry, catch và callback |
| Azure | Durable Functions | Orchestrator, activity, entity và pattern fan-out/fan-in |
| Azure | Logic Apps | Workflow tích hợp connector, trigger và action |
| Google Cloud | Workflows | Workflow định nghĩa các bước gọi service/API, nhánh, retry và chờ |
| Đa nền tảng | Temporal hoặc workflow engine độc lập | Orchestration stateful có thể triển khai trên hạ tầng do tổ chức quản lý |

Cần phân biệt workflow orchestration với event routing. EventBridge, Event Grid và Eventarc chủ yếu định tuyến event; Step Functions, Durable Functions và Workflows quản lý tiến trình nhiều bước. Một event router có thể kích hoạt workflow, nhưng không tự động thay thế state machine.

### 14.1. Khi nào nên dùng workflow engine?

Dùng workflow khi:

- Quy trình có nhiều bước phụ thuộc nhau.
- Cần retry theo từng bước thay vì retry toàn quy trình.
- Có nhánh điều kiện hoặc chạy song song.
- Cần chờ timer, callback hoặc sự kiện bên ngoài.
- Cần timeout, compensation hoặc trạng thái execution.
- Muốn có execution history để điều tra.

Không nhất thiết dùng workflow cho một thao tác đơn giản chỉ gọi một function và trả kết quả ngay. Workflow tạo thêm state, latency, chi phí và operational surface.

## 15. Pattern orchestration thường gặp

### 15.1. Sequence

Các bước chạy tuần tự: xác thực → tính phí → ghi đơn → gửi thông báo. Bước sau chỉ bắt đầu khi bước trước đạt điều kiện.

### 15.2. Choice/branch

Chọn nhánh theo dữ liệu: đơn hàng dưới ngưỡng đi qua luồng tự động; đơn hàng giá trị cao cần phê duyệt.

### 15.3. Parallel fan-out/fan-in

Một event được chia cho nhiều bước độc lập, sau đó tổng hợp kết quả. Ví dụ tạo thumbnail, quét malware và trích metadata từ một object.

~~~mermaid
flowchart TD
    A[Object created] --> B[Workflow]
    B --> C[Generate thumbnail]
    B --> D[Scan content]
    B --> E[Extract metadata]
    C --> F[Wait for all results]
    D --> F
    E --> F
    F --> G[Publish processed object]
~~~

Cần đặt giới hạn concurrency, timeout từng nhánh và quy tắc khi một nhánh thất bại. Không để fan-out tạo số lượng invocation vượt capacity của downstream.

### 15.4. Saga và compensation

Một nghiệp vụ phân tán có thể gồm nhiều dịch vụ không chia sẻ một transaction database. Saga chia quy trình thành các bước có hành động bù trừ.

Ví dụ đặt hàng:

1. Reserve inventory.
2. Authorize payment.
3. Create shipment.
4. Confirm order.

Nếu create shipment thất bại sau khi payment đã authorize, compensation có thể void payment và release inventory. Compensation không phải rollback database tự động; nó là một hành động nghiệp vụ mới, có thể thất bại và cần retry/monitor riêng.

### 15.5. Callback và human approval

Một workflow có thể chờ hệ thống ngoài hoặc con người phê duyệt. Cần có:

- Correlation/token an toàn.
- Hạn chờ và timeout.
- Cơ chế tiếp tục workflow.
- Kiểm tra quyền người phê duyệt.
- Audit quyết định.
- Xử lý callback trùng hoặc đến muộn.

Không đưa callback token vào log công khai hoặc event không được bảo vệ.

## 16. So sánh trigger và orchestration theo use case

| Use case | Mô hình phù hợp | Ví dụ dịch vụ |
|---|---|---|
| API trả kết quả nhanh | HTTP function | Lambda + API Gateway; Azure HTTP trigger; Google HTTP function |
| Xử lý file sau upload | Storage event → function | S3 event; Blob/Event Grid; Cloud Storage/Eventarc |
| Xử lý message nền | Queue → consumer function | SQS; Storage Queue/Service Bus; Pub/Sub |
| Phát event tới nhiều service | Event bus/router | EventBridge; Event Grid; Eventarc |
| Chạy theo lịch | Scheduler → function/workflow | EventBridge Scheduler; Timer trigger; Cloud Scheduler |
| Stream processing | Stream consumer | Kinesis; Event Hubs; Pub/Sub hoặc dịch vụ stream |
| Nghiệp vụ nhiều bước | Stateful orchestration | Step Functions; Durable Functions; Workflows |
| Task cần giao lại có retry/rate control | Task queue | SQS; Service Bus; Cloud Tasks |
| Phê duyệt và chờ callback | Workflow có callback | Step Functions callback; Durable Functions external event; Workflows integration |

Dịch vụ tương tự về mục đích chưa chắc có semantics giống nhau. Khi chuyển đổi, cần map cả behavior, không chỉ map tên sản phẩm.

## 17. Ví dụ kiến trúc: xử lý đơn hàng trên ba cloud

Một kiến trúc tham khảo:

~~~mermaid
flowchart TD
    A[Client] --> B[HTTP API]
    B --> C[Create order function]
    C --> D[(Order database)]
    C --> E[OrderCreated event]
    E --> F[Queue / Event bus]
    F --> G[Order workflow]
    G --> H[Reserve inventory]
    G --> I[Authorize payment]
    G --> J[Create shipment]
    G --> K[Notify customer]
    G --> L[Compensation on failure]
~~~

Mapping dịch vụ:

| Thành phần | AWS | Azure | Google Cloud |
|---|---|---|---|
| HTTP entry | API Gateway + Lambda | API Management + HTTP Function | API Gateway/HTTP function |
| Event routing | EventBridge | Event Grid | Eventarc |
| Queue | SQS | Service Bus Queue | Pub/Sub hoặc Cloud Tasks tùy semantics |
| Function | Lambda | Azure Functions | Cloud Functions/Cloud Run functions |
| Orchestration | Step Functions | Durable Functions/Logic Apps | Workflows |
| Schedule/reconciliation | EventBridge Scheduler | Timer trigger | Cloud Scheduler |
| DLQ | SQS DLQ hoặc destination phù hợp | Service Bus dead-letter subqueue | Pub/Sub dead-letter topic hoặc queue pattern phù hợp |

Queue, event bus và workflow có thể cùng xuất hiện. Event bus giúp phân phối event tới nhiều subscriber; queue giúp giữ công việc cho một consumer group; workflow điều khiển thứ tự và trạng thái của một giao dịch nghiệp vụ.

## 18. Event schema và versioning giữa các cloud

Một event contract trung lập giúp producer không phụ thuộc cấu trúc payload riêng của một nhà cung cấp. Khi chuyển từ EventBridge sang Event Grid hoặc Eventarc, lớp adapter có thể ánh xạ envelope của provider sang schema domain.

Cần version hóa:

- Event type.
- Schema version.
- Required/optional fields.
- Timestamp và timezone.
- ID và correlation ID.
- Ordering key hoặc partition key.
- Retry metadata.
- Payload size và encoding.

Khi thêm field, consumer cũ nên bỏ qua field chưa biết nếu contract cho phép. Khi đổi nghĩa hoặc xóa field, dùng version mới hoặc migration có thời gian tương thích. Không thay đổi schema trực tiếp mà không kiểm tra producer và consumer đang hoạt động.

## 19. Bảo đảm idempotency và transaction giữa function

Function thường tương tác với nhiều dịch vụ. Một lỗi có thể xảy ra sau khi side effect đã thành công nhưng trước khi acknowledgement được gửi. Khi event được retry, consumer không biết thao tác trước đã hoàn tất hay chưa.

Các pattern thường dùng:

- **Idempotency key:** khóa nghiệp vụ hoặc event ID để ngăn xử lý lặp.
- **Inbox table:** lưu event ID đã nhận trong cùng transaction với thay đổi dữ liệu.
- **Outbox pattern:** ghi thay đổi nghiệp vụ và event cần phát trong cùng transaction, sau đó publisher gửi event.
- **Deduplication window:** lưu ID trong khoảng thời gian phù hợp với retry/retention.
- **Saga compensation:** thực hiện hành động bù trừ cho side effect đã xảy ra.
- **Optimistic concurrency:** dùng version để ngăn event cũ ghi đè trạng thái mới.

Exactly-once ở một dịch vụ không đồng nghĩa exactly-once xuyên suốt database, queue, function và API bên ngoài. Thiết kế effectively-once bằng idempotency và transaction boundary thực tế hơn.

## 20. Scaling và backpressure

Function có thể scale nhanh hơn database hoặc API downstream. Nếu queue tăng và consumer tự scale không giới hạn, hệ thống phụ trợ có thể quá tải.

Các guardrail:

- Maximum/reserved concurrency.
- Queue depth và age-of-oldest-message threshold.
- Batch size và maximum batching window.
- Rate limit tới downstream.
- Connection pool hoặc database proxy.
- Circuit breaker và retry budget.
- Backpressure bằng cách giảm consumer rate.
- Quota theo tenant hoặc event type.

Đừng chỉ theo dõi số invocation đồng thời. Một function xử lý nhiều request nhưng mỗi request gọi database 20 lần có thể gây tải lớn hơn function khác có cùng concurrency.

## 21. Networking và quyền truy cập dịch vụ

Function cần kết nối tới các dịch vụ mà nó gọi. Có thể dùng public endpoint, private endpoint, VPC/VNet integration hoặc service connector tùy nền tảng.

Cần xác định:

- Function có cần truy cập private database không?
- Event source gọi function qua public hay private path?
- Egress đi qua NAT, firewall hay private service endpoint?
- DNS resolution có đúng trong subnet không?
- Security group/NSG/firewall có cho phép đúng luồng không?
- Function identity có quyền đọc/ghi đúng resource không?
- Secret được lấy từ secret manager hay biến môi trường?
- Connection pool có được tái sử dụng an toàn qua invocation không?

Không đưa credential dài hạn vào event payload. Dùng managed identity/role/service account và cấp quyền tối thiểu. Với trigger cross-account/project/subscription, cần thiết kế trust policy và resource policy phù hợp.

## 22. Observability xuyên function và workflow

Một quy trình event-driven có thể đi qua nhiều function, queue và workflow. Nếu chỉ xem log riêng từng function, rất khó biết event đã dừng ở đâu.

Các trường nên truyền xuyên suốt:

- correlation ID.
- event ID.
- trace context.
- workflow execution ID.
- business entity ID không nhạy cảm.
- function name/version.
- attempt/retry count.
- event type và schema version.

Theo dõi các metric:

| Metric | Mục đích |
|---|---|
| Invocation count | Đo volume |
| Duration p50/p95/p99 | Đo latency |
| Error/timeout count | Đo độ tin cậy |
| Queue depth/age | Phát hiện backlog |
| Retry/DLQ count | Phát hiện lỗi lặp |
| Workflow duration/failure | Đo quy trình end-to-end |
| Concurrency/throttling | Phát hiện giới hạn capacity |
| Downstream latency | Xác định dependency bottleneck |
| Cost per successful operation | Đo hiệu quả kinh tế |

Cần tránh log toàn bộ payload nếu có dữ liệu nhạy cảm. Dùng structured logging, sampling và retention phù hợp.

## 23. Chi phí của trigger và orchestration

Chi phí có thể phát sinh ở nhiều tầng:

- Mỗi invocation hoặc request.
- Duration và tài nguyên function.
- Event bus event ingestion/delivery.
- Queue request, message operation hoặc throughput tier.
- Workflow state transition hoặc execution duration.
- Scheduler invocation.
- Retry và DLQ storage.
- Network egress, NAT và private connectivity.
- Logs, metrics và traces.
- Database, object storage và API phụ trợ.

Một workflow nhiều bước có thể dễ vận hành hơn nhưng tạo thêm state transition và invocation. Một event bus fan-out tới nhiều subscriber có thể làm số lần xử lý tăng theo số consumer. Hãy tính cost per business transaction, bao gồm cả retry và compensation.

## 24. Độ bền, quota và giới hạn thực thi

Khi chọn nền tảng, hãy so sánh các giới hạn có thể ảnh hưởng tới thiết kế:

- Maximum execution duration.
- Memory/CPU tiers.
- Maximum concurrency và scale rate.
- Request/event payload size.
- Batch size và batching window.
- Queue retention và visibility/ack deadline.
- Stream partition/shard/consumer limits.
- Retry window và DLQ behavior.
- Workflow execution duration và history retention.
- Network connection và outbound limits.
- Regional availability và quota.

Các giới hạn thay đổi theo plan, region, runtime và phiên bản dịch vụ. Không lấy một con số từ tài liệu cũ làm mặc định cho mọi workload.

## 25. Portability và mức độ phụ thuộc nhà cung cấp

Function code có thể khá portable nếu dùng runtime phổ biến và tránh SDK-specific behavior. Tuy nhiên, trigger, binding, IAM, workflow definition, retry semantics và event envelope thường tạo coupling.

Các lớp portability:

1. **Code portability:** ngôn ngữ, runtime, package và container.
2. **Event portability:** schema và semantics của event.
3. **Trigger portability:** cách nguồn gọi function.
4. **Workflow portability:** state machine và activity model.
5. **Identity/network portability:** quyền, private connectivity và secret.
6. **Operational portability:** logs, metrics, traces, deployment và cost allocation.

Dùng container có thể giúp đóng gói runtime nhưng không tự làm trigger và workflow portable. Một function chạy trong container vẫn có thể phụ thuộc EventBridge, Service Bus, Eventarc hoặc API đặc thù.

### 25.1. Giảm coupling có chủ đích

- Định nghĩa domain event schema độc lập với provider.
- Tạo adapter giữa provider envelope và domain event.
- Tách business logic khỏi SDK và trigger handler.
- Đặt interface cho queue, object storage và secret access.
- Dùng OpenTelemetry hoặc format telemetry chuẩn khi phù hợp.
- Quản lý workflow definition như artifact có version.
- Kiểm thử contract giữa producer và consumer.
- Ghi lại mapping retry, ordering, timeout và DLQ khi migration.

Không cần loại bỏ mọi dịch vụ managed đặc thù. Nếu dịch vụ mang lại lợi ích vận hành rõ ràng, hãy chấp nhận coupling có chủ đích và có kế hoạch exit phù hợp.

## 26. Quy trình lựa chọn mô hình function, trigger và orchestration

1. Xác định điểm bắt đầu: HTTP, queue, event, stream, storage hay lịch.
2. Xác định caller cần kết quả ngay hay chỉ cần xác nhận đã nhận yêu cầu.
3. Đo event rate, burst, payload size và yêu cầu ordering.
4. Xác định delivery semantics, retry, retention và DLQ.
5. Xác định function duration, memory/CPU và concurrency.
6. Kiểm tra dependency, network path và identity.
7. Xác định nghiệp vụ có nhiều bước, nhánh, chờ hoặc compensation không.
8. Chọn event router, queue hoặc stream theo semantics cần có.
9. Chọn workflow engine nếu cần stateful orchestration.
10. Kiểm tra observability, quota, region và tổng chi phí.
11. Thử failure scenario: duplicate, timeout, poison event, downstream outage và replay.
12. Đánh giá mức coupling và cách migration nếu cần đổi cloud.

### 26.1. Ma trận quyết định nhanh

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Trả kết quả trong vài giây | HTTP function |
| Xử lý nền và hấp thụ burst | Queue-triggered function |
| Phát event tới nhiều hệ thống | Event bus/router |
| Nhiều consumer cần replay độc lập | Stream hoặc pub/sub phù hợp |
| Chạy tác vụ định kỳ | Managed scheduler + function/workflow |
| Nhiều bước có trạng thái và nhánh | Workflow orchestration |
| Giao task có rate limit và retry | Task queue |
| Quy trình có side effect nhiều dịch vụ | Saga với orchestration hoặc choreography có compensation |

## 27. Những lỗi thiết kế thường gặp

**Dùng HTTP function cho job dài.** Request có thể timeout và giữ tài nguyên trong lúc chờ. Chuyển sang queue/workflow và trả task ID.

**Nhầm event bus với queue.** Event bus định tuyến event tới nhiều subscriber; queue giữ công việc cho consumer. Chọn theo delivery và consumption semantics.

**Giả định event chỉ giao một lần.** Retry hoặc redelivery có thể tạo duplicate. Thiết kế idempotency.

**Không kiểm tra ordering.** Consumer song song có thể xử lý event theo thứ tự khác. Dùng partition/session key hoặc version check khi nghiệp vụ yêu cầu.

**Retry mọi lỗi vô hạn.** Poison event tạo vòng lặp và tăng chi phí. Phân loại lỗi, giới hạn retry và dùng DLQ.

**Batch quá lớn.** Một lỗi có thể khiến nhiều record bị retry, memory tăng hoặc function timeout. Benchmark batch và dùng partial failure nếu hỗ trợ.

**Đặt workflow chứa toàn bộ business logic.** Workflow trở nên khó test và khó tái sử dụng. Giữ workflow ở vai trò điều phối, business logic nằm trong function/service.

**Thiếu correlation ID.** Không thể truy vết một giao dịch qua nhiều function. Truyền trace context và business correlation.

**Bỏ qua chi phí orchestration.** Nhiều state transition, event fan-out và retry làm cost tăng. Tính cost per transaction.

**Chuyển cloud chỉ bằng cách đổi SDK.** Trigger, retry, ordering, identity và workflow semantics có thể khác. Thực hiện contract mapping và failure testing.

## 28. Checklist trước khi đưa event-driven function vào production

- [ ] Đã xác định rõ function model và runtime.
- [ ] Đã xác định trigger là HTTP, direct invocation, push, polling, queue, stream hay schedule.
- [ ] Đã hiểu ai poll, ai giữ event và ai retry.
- [ ] Event envelope có ID, type, source, timestamp, schema version và correlation ID.
- [ ] Consumer xử lý duplicate an toàn bằng idempotency.
- [ ] Đã xác định ordering/partition key nếu nghiệp vụ cần thứ tự.
- [ ] Retry có giới hạn, backoff, jitter và phân loại lỗi.
- [ ] Có DLQ/dead-letter destination và quy trình replay.
- [ ] Batch size, partial failure và checkpoint phù hợp.
- [ ] Workflow có timeout, retry, branch và compensation rõ ràng.
- [ ] Function concurrency không vượt khả năng downstream.
- [ ] Identity, secret, network và quyền resource theo least privilege.
- [ ] Logs, metrics và traces có correlation xuyên suốt.
- [ ] Đã tính chi phí invocation, event routing, queue, workflow và dependency.
- [ ] Đã kiểm tra quota, timeout, payload size và regional availability.
- [ ] Đã thử duplicate, poison event, timeout, downstream outage và replay.
- [ ] Đã ghi nhận mức coupling và kế hoạch portability/migration.

## 29. Kết luận

Mô hình function xác định cách mã được triển khai và thực thi; trigger xác định sự kiện nào khởi động function và event đi qua đường push, polling hay invocation trực tiếp; orchestration quản lý thứ tự, trạng thái, retry và compensation của quy trình nhiều bước. AWS Lambda, Azure Functions và Google Cloud functions cung cấp các khả năng tương đương về mặt mục đích, nhưng khác nhau ở event source mapping, binding, event routing, workflow engine và semantics vận hành.

Khi thiết kế hoặc đối chiếu giữa cloud, hãy so sánh hành vi thực tế thay vì chỉ ghép tên sản phẩm. Xác định delivery guarantee, ordering, retry, batch, DLQ, concurrency, state và network access; sau đó kiểm thử duplicate, timeout, poison event và sự cố dependency. Event schema trung lập cùng adapter và idempotency giúp giảm coupling, trong khi workflow phù hợp giữ cho quy trình nhiều bước có trạng thái và có thể quan sát. Lựa chọn tốt là mô hình đáp ứng yêu cầu nghiệp vụ, vận hành và chi phí với semantics được hiểu rõ.
