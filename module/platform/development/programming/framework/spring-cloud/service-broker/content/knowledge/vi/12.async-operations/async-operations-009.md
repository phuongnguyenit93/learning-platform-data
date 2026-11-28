# Thực thi tác vụ bền vững bằng hàng đợi hoặc bộ xử lý nền do broker quản lý

## Mục tiêu và bối cảnh

Một service broker thường phải thực hiện các công việc kéo dài như tạo database, cấu hình backup, tạo volume, thiết lập network policy hoặc thu hồi tài nguyên trên cloud. Những thao tác này có thể mất vài giây đến vài phút và phụ thuộc vào API của nhà cung cấp. Nếu xử lý toàn bộ công việc ngay trong luồng HTTP, request dễ vượt timeout của platform, load balancer hoặc broker; tiến trình cũng có thể mất công việc khi ứng dụng restart.

Trong module Spring Cloud Service Broker, broker cần tiếp nhận yêu cầu OSB API, ghi nhận trạng thái bền vững và chuyển công việc sang hàng đợi hoặc bộ xử lý nền do broker quản lý. Worker thực hiện tác vụ, cập nhật operation và cho phép platform truy vấn tiến độ. Cách tổ chức này tách thời gian sống của request HTTP khỏi thời gian sống của công việc cấp phát hoặc thu hồi tài nguyên.

Bài học tập trung vào cách thực thi tác vụ bền vững bằng queue hoặc background processor. Sau bài học, bạn có thể:

- Phân biệt xử lý đồng bộ với xử lý bất đồng bộ.
- Thiết kế operation record và event bền vững.
- Sử dụng transactional outbox để không mất công việc giữa database và queue.
- Xây dựng worker có retry, idempotency, timeout và xử lý lỗi.
- Ánh xạ tiến độ nội bộ sang trạng thái operation của OSB API.
- Vận hành nhiều worker mà không xử lý trùng hoặc cập nhật trạng thái sai.
- Kiểm thử các tình huống restart, queue gián đoạn và backend timeout.

## 1. Vì sao cần hàng đợi hoặc bộ xử lý nền?

Một request provision có thể gồm nhiều bước:

1. Kiểm tra service, plan, parameters và quota.
2. Tạo bản ghi service instance.
3. Tạo database hoặc tài nguyên cloud.
4. Cấu hình network, backup và monitoring.
5. Lưu backend reference.
6. Đánh dấu instance READY.

Nếu bước tạo database mất 90 giây, giữ HTTP connection trong toàn bộ thời gian đó sẽ làm tăng nguy cơ timeout và chiếm thread xử lý request. Nếu broker trả lỗi vì client đã timeout nhưng backend vẫn tiếp tục tạo tài nguyên, platform và broker có thể hiểu sai kết quả.

Mô hình bất đồng bộ chia công việc thành hai giai đoạn:

- **Tiếp nhận:** xác thực request, kiểm tra dữ liệu, lưu instance/operation và ghi yêu cầu công việc bền vững.
- **Thực thi:** worker lấy công việc, gọi backend, cập nhật tiến độ và kết quả.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant API as Broker API
    participant DB as Broker Database
    participant Q as Queue / Outbox
    participant W as Background Worker
    participant B as Resource Backend

    P->>API: PUT service_instances
    API->>DB: Lưu instance + operation
    API->>DB: Ghi outbox event
    API-->>P: 202 Accepted + operation token
    Q->>W: Phân phối công việc
    W->>DB: Claim operation
    W->>B: Tạo tài nguyên
    B-->>W: Kết quả
    W->>DB: Cập nhật instance + operation
    P->>API: GET last_operation
    API->>DB: Đọc trạng thái
    API-->>P: in progress / succeeded / failed
~~~

Điểm quan trọng: broker chỉ trả HTTP 202 Accepted sau khi đã lưu bền vững thông tin đủ để tiếp tục công việc. Không trả 202 chỉ vì đã đưa một message vào bộ nhớ hoặc tạo một task trong thread pool.

## 2. Chọn queue hay background processor

Có hai cách tổ chức phổ biến. Chúng có thể được kết hợp trong cùng hệ thống.

| Cách tổ chức | Cách hoạt động | Phù hợp khi |
|---|---|---|
| Message queue | Broker ghi event, publisher gửi message tới RabbitMQ, Kafka hoặc hệ thống queue khác; worker tiêu thụ message | Có nhiều worker, cần phân phối tải, retry và mở rộng độc lập |
| Database-backed processor | Worker định kỳ truy vấn operation/outbox đến hạn và claim công việc trong database | Hệ thống nhỏ, muốn ít thành phần vận hành, công việc có thể được quản lý bằng bảng dữ liệu |
| Scheduler + queue | Scheduler tìm operation đến hạn rồi phát message cho worker | Cần lập lịch, quét timeout hoặc reconciliation kết hợp queue |

Không có một lựa chọn phù hợp cho mọi broker. Hãy cân nhắc độ phức tạp vận hành, khối lượng công việc, thời gian xử lý, yêu cầu throughput, khả năng retry và mức độ sẵn sàng của hạ tầng.

### 2.1. Message queue

Queue tách producer khỏi consumer. Broker API tạo event; worker nhận event và thực hiện tác vụ. Có thể tăng số lượng worker mà không tăng số instance HTTP API.

Ưu điểm:

- Phân phối công việc giữa nhiều worker.
- Có thể cấu hình retry, dead-letter queue và giới hạn consumer.
- Tách vòng đời API khỏi backend worker.
- Hỗ trợ điều chỉnh concurrency theo năng lực backend.

Cần quản lý thêm broker message infrastructure, quyền truy cập, monitoring, schema message và khả năng phục hồi queue. Message broker thường giao message theo mô hình at-least-once; worker phải chịu được message lặp.

### 2.2. Database-backed processor

Worker có thể định kỳ tìm operation ở trạng thái PENDING hoặc RETRY_WAIT, sau đó claim một operation bằng transaction và cập nhật trạng thái RUNNING. Một cách triển khai trên PostgreSQL là dùng FOR UPDATE SKIP LOCKED để nhiều worker lấy các hàng khác nhau.

Ví dụ truy vấn khái niệm:

~~~sql
SELECT operation_id
FROM broker_operation
WHERE state IN ('PENDING', 'RETRY_WAIT')
  AND next_attempt_at <= CURRENT_TIMESTAMP
ORDER BY created_at
FOR UPDATE SKIP LOCKED
LIMIT 20;
~~~

Sau khi chọn được operation, worker cần cập nhật trạng thái và lease trong cùng transaction trước khi commit. Không giữ row lock trong lúc gọi API backend. Worker khác có thể lấy các operation còn lại.

Database-backed processor ít phụ thuộc hạ tầng hơn nhưng cần thiết kế cẩn thận về polling interval, lease, index, tải truy vấn và xử lý operation bị treo.

## 3. Mô hình operation bền vững

Một operation đại diện cho một lần thực hiện nghiệp vụ như provision, update hoặc deprovision. Không nên chỉ lưu một biến trong bộ nhớ hoặc dựa vào trạng thái của message queue để xác định kết quả cuối cùng.

Một bảng broker_operation tham khảo:

| Trường | Ý nghĩa |
|---|---|
| operation_id | ID duy nhất và opaque được dùng làm operation token |
| instance_id | Service instance chịu tác động |
| operation_type | PROVISION, UPDATE hoặc DEPROVISION |
| state | PENDING, RUNNING, RETRY_WAIT, SUCCEEDED hoặc FAILED |
| current_step | Bước workflow hiện tại |
| attempt | Số lần worker đã thử |
| next_attempt_at | Thời điểm được phép retry |
| lease_owner | Worker đang giữ quyền xử lý |
| lease_expires_at | Thời điểm lease hết hạn |
| request_ref | Tham chiếu đến request đã chuẩn hóa |
| error_code | Mã lỗi đã chuẩn hóa |
| description | Mô tả trạng thái an toàn để hiển thị |
| created_at / updated_at | Thời điểm tạo và cập nhật |
| completed_at | Thời điểm kết thúc |

Có thể lưu thêm bảng operation_step nếu một operation gồm nhiều bước. Bảng này giúp biết bước nào đã hoàn thành, bước nào đang chạy và bước nào cần compensation.

### 3.1. State machine

State machine nội bộ có thể như sau:

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING
    RUNNING --> SUCCEEDED
    RUNNING --> RETRY_WAIT
    RUNNING --> FAILED
    RETRY_WAIT --> RUNNING
    RUNNING --> CANCEL_REQUESTED
    CANCEL_REQUESTED --> COMPENSATING
    COMPENSATING --> FAILED
    COMPENSATING --> RETRY_WAIT
~~~

Ý nghĩa:

- PENDING: công việc đã được ghi nhận và chờ worker.
- RUNNING: worker đang thực thi.
- RETRY_WAIT: lỗi tạm thời; chờ đến thời điểm thử lại.
- SUCCEEDED: thao tác đã hoàn tất và hậu điều kiện được xác nhận.
- FAILED: thao tác kết thúc thất bại, không còn retry tự động.
- CANCEL_REQUESTED: có yêu cầu hủy workflow.
- COMPENSATING: đang thu hồi các thay đổi đã thực hiện.

Đây là trạng thái nội bộ, không phải danh sách trạng thái bắt buộc của OSB API. Broker ánh xạ trạng thái nội bộ sang in progress, succeeded hoặc failed khi trả lời endpoint last operation.

### 3.2. Instance state và operation state là hai thứ khác nhau

Service instance có vòng đời riêng như PROVISIONING, READY, UPDATING, DEPROVISIONING, DELETED hoặc FAILED. Operation mô tả một lần thực hiện cụ thể. Một instance READY có thể có nhiều operation đã hoàn tất trong lịch sử.

Không nên ghi đè trạng thái instance thành SUCCEEDED chỉ vì một operation thành công. Ví dụ, operation UPDATE thành công thì instance trở lại READY với cấu hình mới; operation có state SUCCEEDED, còn instance có state READY.

## 4. Tiếp nhận request và ghi công việc bền vững

Khi nhận request OSB, broker nên thực hiện một transaction ngắn để lưu:

- Service instance hoặc thay đổi trạng thái mong muốn.
- Operation record với ID ổn định.
- Request parameters đã validate và chuẩn hóa.
- Event yêu cầu worker thực thi.

Nếu broker ghi database rồi mới publish message bằng hai thao tác độc lập, có thể xảy ra hai lỗi:

1. Database commit thành công nhưng publish thất bại: operation bị treo vì không có worker nhận.
2. Publish thành công nhưng transaction database rollback: worker nhận message nhưng không tìm thấy operation hợp lệ.

### 4.1. Transactional outbox

Transactional outbox giải quyết vấn đề này bằng cách ghi operation và event vào cùng một transaction database. Một publisher riêng đọc các outbox event chưa được gửi và publish chúng tới queue.

~~~mermaid
flowchart LR
    API[OSB API] --> TX[Database Transaction]
    TX --> I[(Service Instance)]
    TX --> O[(Operation)]
    TX --> E[(Outbox Event)]
    E --> PUB[Outbox Publisher]
    PUB --> Q[Message Queue]
    Q --> W[Worker]
    W --> B[Backend Adapter]
    W --> DB[(Operation Result)]
~~~

Ví dụ cấu trúc outbox:

| Trường | Ý nghĩa |
|---|---|
| event_id | ID duy nhất của event |
| aggregate_id | Instance hoặc operation liên quan |
| event_type | PROVISION_REQUESTED, UPDATE_REQUESTED, DEPROVISION_REQUESTED |
| payload | Tham chiếu đến operation và dữ liệu cần thiết |
| created_at | Thời điểm tạo |
| published_at | Thời điểm publish thành công |
| publish_attempt | Số lần thử gửi |
| next_attempt_at | Thời điểm thử gửi tiếp |

Payload nên gọn, có version và ưu tiên mang operation_id thay vì sao chép toàn bộ dữ liệu nhạy cảm. Worker đọc operation từ database theo ID để lấy dữ liệu có thẩm quyền.

Ví dụ ghi nhận trong transaction:

~~~java
@Transactional
public AcceptedOperation acceptProvision(ProvisionCommand command) {
    ServiceInstance instance =
            instanceRepository.save(
                    ServiceInstance.provisioning(command)
            );

    BrokerOperation operation =
            operationRepository.save(
                    BrokerOperation.pendingProvision(
                            command.instanceId()
                    )
            );

    outboxRepository.save(
            OutboxEvent.provisionRequested(
                    operation.id(),
                    instance.id()
            )
    );

    return new AcceptedOperation(operation.id());
}
~~~

Đây là pseudocode thể hiện ranh giới transaction. Các entity và repository thực tế phụ thuộc persistence layer của ứng dụng. Cả ba bản ghi phải commit hoặc rollback cùng nhau.

### 4.2. Khi nào trả 202 Accepted?

Chỉ trả 202 khi các điều kiện sau đã đạt:

- Request đã được xác thực và validate.
- Service instance và operation đã được ghi bền vững.
- Event outbox hoặc bản ghi công việc đã được commit.
- Broker có thể tiếp tục công việc sau khi process restart.
- Platform đã cho phép thao tác bất đồng bộ qua accepts_incomplete=true.

Nếu platform không chấp nhận incomplete operation mà broker không thể hoàn tất trong chế độ đồng bộ, broker phải trả lỗi theo hợp đồng OSB API, thường là lỗi AsyncRequired với HTTP 422. Không được trả 202 cho một task chỉ tồn tại trong RAM.

## 5. Outbox publisher và message delivery

Publisher đọc các outbox event chưa publish, claim theo lease hoặc lock, gửi message và cập nhật published_at khi gửi thành công.

Quy trình:

1. Tìm event đến hạn chưa publish.
2. Claim event trong transaction ngắn.
3. Commit trạng thái claim.
4. Gửi message tới queue.
5. Xác nhận publish theo cơ chế của queue.
6. Cập nhật published_at.
7. Nếu lỗi, tăng publish_attempt và đặt next_attempt_at.

Nếu publisher gửi message thành công nhưng process chết trước khi cập nhật published_at, message có thể được gửi lại. Đây là hành vi bình thường trong mô hình at-least-once. Consumer phải idempotent dựa trên operation_id hoặc event_id.

Không đánh dấu event đã publish trước khi queue xác nhận nhận message. Nếu làm vậy, một lỗi mạng có thể khiến event bị mất mà database vẫn ghi là đã gửi.

## 6. Worker claim và thực thi công việc

Worker không nên tin hoàn toàn nội dung message. Khi nhận operation_id, worker tải operation từ database, kiểm tra state, claim quyền xử lý và xác minh instance vẫn ở trạng thái phù hợp.

Quy trình worker:

1. Nhận message.
2. Đọc operation theo operation_id.
3. Bỏ qua nếu operation đã SUCCEEDED hoặc FAILED.
4. Claim operation bằng lease hoặc cập nhật có điều kiện.
5. Tải instance và cấu hình đã chuẩn hóa.
6. Thực hiện từng bước qua backend adapter.
7. Lưu tiến độ và external resource reference sau mỗi bước.
8. Cập nhật instance và operation khi hoàn tất.
9. ACK message sau khi kết quả đã được lưu bền vững.

Pseudocode:

~~~java
public void handle(OperationMessage message) {
    Optional<BrokerOperation> claimed =
            operationRepository.claim(
                    message.operationId(),
                    workerId,
                    leaseDuration
            );

    if (claimed.isEmpty()) {
        return;
    }

    BrokerOperation operation = claimed.get();

    try {
        OperationResult result =
                workflowExecutor.execute(operation);

        transactionTemplate.executeWithoutResult(status -> {
            operationRepository.markSucceeded(
                    operation.id(),
                    result.safeDescription()
            );
            instanceRepository.applyResult(
                    operation.instanceId(),
                    result
            );
        });
    } catch (RetryableBackendException failure) {
        retryScheduler.schedule(operation, failure);
    } catch (Exception failure) {
        operationRepository.markFailed(
                operation.id(),
                classify(failure),
                safeDescription(failure)
        );
    }
}
~~~

Đây là pseudocode. Trong implementation thật, cần bảo đảm message chỉ được ACK sau khi đã lưu trạng thái tương ứng. Nếu retry được lên lịch bằng database, hãy lưu RETRY_WAIT và next_attempt_at trước khi ACK message hiện tại.

### 6.1. Lease và worker bị treo

Worker có thể chết sau khi claim operation. Nếu chỉ đặt state RUNNING mà không có lease, operation có thể bị kẹt vĩnh viễn.

Lease gồm:

- lease_owner: worker đang giữ operation.
- lease_expires_at: thời điểm quyền xử lý hết hạn.
- heartbeat_at: thời điểm worker cập nhật lần cuối.

Worker gia hạn lease trong khi xử lý tác vụ dài. Một worker khác chỉ được claim lại operation khi lease đã hết hạn và đã xác minh không có tiến trình hợp lệ tiếp tục sở hữu nó.

Lease không thay thế idempotency. Worker cũ có thể tiếp tục chạy sau khi lease hết hạn do pause hoặc mất kết nối tạm thời. Vì vậy, các cập nhật cần fencing token hoặc version tăng dần để worker cũ không ghi đè kết quả của worker mới.

## 7. Retry, backoff và phân loại lỗi

Không phải lỗi nào cũng nên retry. Retry vô hạn có thể làm nghẽn queue và tăng tải lên backend đang gặp sự cố.

| Loại lỗi | Ví dụ | Xử lý |
|---|---|---|
| Lỗi tạm thời | Timeout, HTTP 429, HTTP 503 | Retry với backoff |
| Lỗi xác thực/cấu hình | Credentials backend sai, endpoint sai | Dừng retry tự động và cảnh báo |
| Lỗi nghiệp vụ | Plan không hợp lệ, vượt quota | FAILED, yêu cầu client sửa |
| Xung đột | Instance đang có operation khác | Điều phối hoặc trả conflict |
| Kết quả không xác định | Timeout sau khi backend có thể đã tạo tài nguyên | Tra cứu backend trước khi retry |
| Lỗi dữ liệu | Schema hoặc payload không hợp lệ | Đưa vào dead-letter hoặc FAILED |

Một lịch retry có thể dùng exponential backoff:

~~~text
delay = min(maxDelay, baseDelay * 2^attempt) + jitter
~~~

Jitter giúp nhiều worker không retry đồng thời sau một sự cố diện rộng. Nếu backend trả Retry-After, cần tôn trọng giá trị đó khi phù hợp với giới hạn chính sách.

Ví dụ:

- Lần đầu: thử lại sau 2 giây.
- Lần hai: sau 4 giây.
- Lần ba: sau 8 giây.
- Sau giới hạn: chuyển sang FAILED hoặc chờ can thiệp theo chính sách.

Giá trị thực tế phụ thuộc loại backend và SLA. Không dùng một lịch retry duy nhất cho mọi loại tài nguyên.

### 7.1. Dead-letter queue

Message không thể xử lý sau số lần thử tối đa hoặc có payload lỗi có thể được đưa vào dead-letter queue. Dead-letter giúp giữ lại bằng chứng để điều tra, nhưng không tự giải quyết operation.

Cần có quy trình vận hành:

- Ghi operation_id và event_id.
- Ghi nguyên nhân đã được chuẩn hóa.
- Che dữ liệu nhạy cảm trong payload.
- Cảnh báo khi dead-letter tăng bất thường.
- Cho phép operator retry sau khi sửa lỗi cấu hình.
- Tránh phát lại message cũ nếu operation đã kết thúc.

Không xóa operation record chỉ vì message đã vào dead-letter. Operation là nguồn sự thật cho platform và audit.

## 8. Ánh xạ trạng thái worker sang OSB API

OSB API định nghĩa cách platform theo dõi thao tác bất đồng bộ. Với provision, update và deprovision được chấp nhận bất đồng bộ, broker trả operation token trong response và cung cấp endpoint last operation.

Ví dụ:

~~~http
GET /v2/service_instances/instance-123/last_operation?service_id=service-postgresql&plan_id=plan-standard&operation=op-789
Authorization: Basic <broker-credentials>
X-Broker-API-Version: <supported-version>
~~~

Khi worker còn chạy:

~~~json
{
  "state": "in progress",
  "description": "Dang tao database va cau hinh backup"
}
~~~

Khi hoàn tất:

~~~json
{
  "state": "succeeded",
  "description": "Service instance da san sang"
}
~~~

Khi thất bại:

~~~json
{
  "state": "failed",
  "description": "Khong the tao database do backend tu choi cau hinh"
}
~~~

Operation token nên là ID opaque, ổn định và khó đoán. Platform chỉ dùng token để tham chiếu operation; không cần biết queue name, worker ID hoặc cấu trúc nội bộ.

Endpoint last operation nên đọc từ database operation, không truy vấn queue để suy luận trạng thái. Queue chỉ phân phối công việc; database operation là nguồn trạng thái có thẩm quyền.

### 8.1. Polling và tần suất truy vấn

Platform thường polling last operation cho đến khi nhận succeeded hoặc failed. Broker cần:

- Trả trạng thái nhanh từ database có index phù hợp.
- Không gọi backend trong mỗi lần polling.
- Không thay đổi attempt hoặc tạo side effect khi GET last operation.
- Trả description ngắn gọn và an toàn.
- Giữ operation record đủ lâu theo chính sách audit và yêu cầu platform.
- Cân nhắc giới hạn request và caching ngắn hạn nếu cần, nhưng không để cache che trạng thái mới.

Broker không kiểm soát hoàn toàn chu kỳ polling của platform. Vì vậy endpoint này phải nhẹ và có thể phục vụ nhiều request đồng thời.

## 9. Idempotency ở publisher, worker và backend adapter

Một event có thể được publish nhiều lần, worker có thể nhận message lặp, và backend có thể thực hiện lệnh nhưng response bị mất. Idempotency cần được áp dụng ở nhiều lớp.

| Lớp | Khóa hoặc định danh | Bảo vệ |
|---|---|---|
| API | instance_id + operation type + request fingerprint | Không tạo operation trùng cho cùng request |
| Outbox | event_id | Nhận diện event đã publish |
| Worker | operation_id + step_key | Không chạy lặp bước đã hoàn tất |
| Backend adapter | idempotency key hoặc external resource name | Không tạo tài nguyên trùng |
| Persistence | unique constraint và version | Ngăn ghi trùng hoặc ghi đè cạnh tranh |

Ví dụ idempotency key cho từng bước có thể được tạo từ instance ID và step key. Không tạo key mới mỗi lần retry.

Worker nên kiểm tra trạng thái step trước khi gọi backend. Nếu step đã SUCCEEDED, bỏ qua. Nếu state là UNKNOWN, truy vấn backend bằng external ID hoặc tag trước khi gửi lệnh mới.

Không thể bảo đảm exactly-once chỉ bằng queue hoặc transaction database khi backend là hệ thống độc lập. Thiết kế thực tế thường dùng at-least-once delivery kết hợp handler idempotent và reconciliation.

## 10. Kiểm soát đồng thời và backpressure

Một broker có thể chạy nhiều worker để tăng throughput. Tuy nhiên, hai worker không được cùng thay đổi một instance theo cách xung đột.

Các biện pháp:

- Chỉ cho phép một operation lifecycle tương thích chạy trên một instance tại một thời điểm.
- Dùng unique constraint hoặc conditional update để claim operation.
- Dùng lease và fencing token để ngăn worker cũ cập nhật sau worker mới.
- Giới hạn concurrency theo backend provider.
- Phân vùng queue theo instance ID nếu cần giữ thứ tự.
- Dùng rate limit để tôn trọng quota API nhà cung cấp.

Backpressure là cơ chế điều tiết tốc độ nhận công việc theo khả năng xử lý. Nếu backend chỉ cho phép 50 request đồng thời, broker không nên tăng worker lên hàng trăm mà không có giới hạn. Có thể dùng worker pool giới hạn, semaphore theo provider hoặc queue consumer concurrency.

Cần theo dõi queue depth, tuổi message lâu nhất, số operation RUNNING và thời gian chờ trung bình. Queue tăng liên tục là dấu hiệu worker không theo kịp hoặc backend đang bị nghẽn.

## 11. Tích hợp worker với Spring

Spring Boot cung cấp nhiều cách triển khai background processing:

- @Scheduled để polling operation/outbox theo chu kỳ.
- @Async cho công việc nền đơn giản trong cùng ứng dụng.
- Spring AMQP khi sử dụng RabbitMQ.
- Spring for Apache Kafka khi dùng Kafka.
- Executor hoặc task scheduler có cấu hình thread pool.
- Một worker service triển khai riêng nhưng dùng chung database và message contract.

Không phải cách nào cũng bền vững như nhau. @Async và task executor trong bộ nhớ không tự bảo đảm công việc tồn tại sau khi process restart. Nếu dùng chúng, phải có operation record hoặc outbox bền vững để khôi phục và lập lịch lại công việc.

### 11.1. Ví dụ worker dùng @Scheduled với database polling

~~~java
@Component
public class OperationPollingWorker {

    private final OperationClaimService claimService;
    private final WorkflowExecutor workflowExecutor;

    @Scheduled(fixedDelay = 1000)
    public void poll() {
        List<BrokerOperation> operations =
                claimService.claimBatch(10);

        for (BrokerOperation operation : operations) {
            workflowExecutor.execute(operation);
        }
    }
}
~~~

Ví dụ này chỉ minh họa cách kích hoạt polling. claimBatch phải claim bằng transaction, lease hoặc SKIP LOCKED; không chỉ SELECT các hàng PENDING rồi mới cập nhật ở bước sau. Nếu nhiều application instance cùng chạy scheduler, cơ chế claim phải ngăn chúng nhận cùng operation.

Với công việc dài, không nên thực hiện tất cả trong thread scheduler duy nhất. Scheduler nên claim batch rồi chuyển sang worker executor giới hạn concurrency.

### 11.2. Ví dụ consumer với message queue

~~~java
@RabbitListener(queues = "broker.provision")
public void onProvisionMessage(OperationMessage message) {
    operationWorker.handle(message.operationId());
}
~~~

Đây là ví dụ với Spring AMQP. Consumer chỉ nên ACK sau khi worker đã lưu trạng thái hoàn tất, đã lên lịch retry bền vững hoặc đã ghi nhận lỗi cuối cùng. Cấu hình ACK, retry và dead-letter phải phù hợp với cách queue được vận hành.

### 11.3. Reactive và blocking work

Spring Cloud Open Service Broker có API reactive ở nhiều abstraction. Không nên thực hiện lời gọi blocking kéo dài trực tiếp trên event loop. Có thể:

- Ghi operation/outbox nhanh trong request path.
- Để worker riêng thực hiện lời gọi backend blocking.
- Nếu phải gọi từ reactive pipeline, chuyển sang scheduler phù hợp và giới hạn concurrency.
- Không dùng block() trong luồng reactive phục vụ HTTP nếu không có lý do rõ ràng.

Tách worker khỏi API giúp giữ latency của endpoint thấp và kiểm soát tải backend độc lập.

## 12. Graceful shutdown và phục hồi sau restart

Khi triển khai phiên bản mới hoặc container bị dừng, worker cần có quy trình shutdown an toàn:

1. Ngừng nhận message mới hoặc ngừng claim operation mới.
2. Cho phép công việc đang chạy hoàn tất trong thời gian grace period.
3. Gia hạn lease nếu worker vẫn đang thực thi hợp lệ.
4. Nếu không thể hoàn tất, không đánh dấu operation thành công.
5. Để lease hết hạn hoặc chủ động nhả lease an toàn.
6. Khi process mới khởi động, worker claim lại operation đến hạn.
7. Kiểm tra backend trước khi lặp lại bước có kết quả không xác định.

Không dùng shutdown hook để xóa trạng thái operation hoặc coi mọi công việc đang chạy là FAILED. Một process có thể dừng giữa lệnh backend và ghi database; trạng thái phải đủ thông tin để worker mới xác minh và tiếp tục.

## 13. Quan sát và vận hành worker

Các chỉ số cần theo dõi:

| Metric | Ý nghĩa |
|---|---|
| broker_operations_pending | Số operation đang chờ |
| broker_operations_running | Số operation đang chạy |
| broker_operation_duration_seconds | Thời gian thực hiện operation |
| broker_operation_retry_total | Tổng số lần retry |
| broker_outbox_pending | Số outbox event chưa publish |
| broker_queue_depth | Số message đang chờ trong queue |
| broker_oldest_message_age_seconds | Tuổi message lâu nhất |
| broker_worker_lease_expired_total | Số lease hết hạn |
| broker_dead_letter_total | Số message vào dead-letter |
| broker_backend_request_duration_seconds | Độ trễ gọi backend |

Log và trace nên mang operation_id, instance_id, step_key, worker_id và correlation ID. Không đưa password, token hoặc parameters nhạy cảm vào log hay metric label.

Cần có cảnh báo cho các tình huống:

- Operation PENDING quá lâu.
- Operation RUNNING nhưng heartbeat hoặc lease đã hết hạn.
- Outbox không publish được.
- Queue depth tăng liên tục.
- Dead-letter tăng đột biến.
- Retry vượt ngưỡng.
- Backend timeout hoặc 429 tăng cao.

## 14. Kiểm thử tính bền vững

Kiểm thử happy path là chưa đủ. Cần mô phỏng lỗi ở các điểm giao nhau giữa database, queue, worker và backend.

| Kịch bản | Kết quả mong đợi |
|---|---|
| API commit operation và outbox thành công | Publisher có thể phát event |
| Queue tạm thời không sẵn sàng | Outbox vẫn lưu; publisher thử lại |
| Publisher chết sau khi publish nhưng trước khi đánh dấu | Event có thể được publish lại; worker idempotent |
| Worker chết sau khi claim | Lease hết hạn; worker khác tiếp tục |
| Worker nhận message trùng | Không lặp side effect đã hoàn tất |
| Backend timeout sau khi tạo resource | Step UNKNOWN; tra cứu backend trước khi retry |
| Backend trả 429 | Retry theo backoff và giới hạn |
| Operation đã SUCCEEDED nhưng message tới lại | Worker bỏ qua |
| Broker restart khi operation đang chạy | Operation được phục hồi từ database |
| Platform polling liên tục | last_operation trả trạng thái nhanh, không gọi backend |
| Nhiều worker claim đồng thời | Một worker sở hữu operation tại một thời điểm |
| Shutdown trong lúc xử lý | Công việc không bị đánh dấu thành công giả |

### 14.1. Kiểm thử transactional outbox

Một integration test nên xác nhận operation và outbox event được commit cùng nhau. Nếu ghi outbox thất bại, transaction phải rollback cả operation và state change. Nếu queue ngừng hoạt động sau commit, outbox vẫn còn để publisher gửi lại khi queue phục hồi.

### 14.2. Kiểm thử worker idempotency

Gửi cùng một operation message hai lần và xác nhận:

- Backend không tạo hai tài nguyên.
- Step đã hoàn tất không chạy lại side effect.
- Operation không bị chuyển ngược từ SUCCEEDED sang RUNNING.
- Lease và version không bị worker cũ ghi đè.
- Message lặp được ACK sau khi xác định operation đã kết thúc.

## 15. Những lỗi thiết kế thường gặp

- **Chỉ dùng @Async trong bộ nhớ:** công việc có thể mất khi process restart.
- **Trả 202 trước khi lưu operation:** platform nhận operation token nhưng broker không thể khôi phục công việc.
- **Ghi database và publish queue không nguyên tử:** có thể mất hoặc phát message mồ côi.
- **ACK message trước khi lưu kết quả:** worker chết có thể làm công việc biến mất khỏi queue.
- **Không có lease:** operation bị kẹt khi worker dừng đột ngột.
- **Không có idempotency:** message lặp tạo tài nguyên hoặc side effect trùng.
- **Retry mọi lỗi:** lỗi cấu hình và quyền bị lặp vô hạn.
- **Giữ transaction trong lúc gọi backend:** khóa database kéo dài và giảm throughput.
- **Dùng queue làm nguồn trạng thái:** queue không phải nguồn sự thật cho endpoint last_operation.
- **Không giới hạn concurrency:** broker có thể vượt quota backend.
- **Không có dead-letter và cảnh báo:** lỗi độc hại hoặc không thể phục hồi bị che khuất.
- **Không kiểm thử restart:** workflow có thể chỉ hoạt động khi process không bị gián đoạn.

## 16. Quy trình triển khai một worker bền vững

Khi xây dựng một tác vụ provision, update hoặc deprovision, hãy triển khai theo thứ tự:

1. Xác định các bước nghiệp vụ và hậu điều kiện thành công.
2. Thiết kế operation state machine và step state machine.
3. Tạo operation record cùng instance state trong transaction.
4. Ghi outbox event trong cùng transaction.
5. Xây publisher có claim, retry và xác nhận publish.
6. Xây worker có lease, concurrency limit và idempotency.
7. Gọi backend qua adapter có timeout và phân loại lỗi.
8. Lưu external resource reference và tiến độ từng bước.
9. Lưu retry schedule hoặc kết quả cuối trước khi ACK message.
10. Cung cấp last_operation đọc trạng thái từ database.
11. Thêm reconciliation cho operation treo và kết quả không xác định.
12. Kiểm thử restart, duplicate message, queue outage và backend timeout.
13. Theo dõi queue depth, operation age, retry và dead-letter trong production.

## Kết luận

Hàng đợi hoặc bộ xử lý nền do broker quản lý giúp thực hiện các tác vụ dài mà không phụ thuộc vào thời gian sống của request HTTP. Để bền vững, broker phải lưu operation và yêu cầu công việc trước khi trả 202, dùng transactional outbox để phát event, và xây worker có claim/lease, retry, idempotency cùng khả năng phục hồi sau restart.

Trong Spring Cloud Service Broker, queue chỉ là cơ chế phân phối công việc; trạng thái operation trong database mới là nguồn sự thật để trả lời platform qua last_operation. Khi kết hợp worker có giới hạn concurrency, backend adapter an toàn khi retry, reconciliation và observability, broker có thể xử lý provision, update và deprovision kéo dài mà vẫn duy trì trạng thái nhất quán và khả năng phục hồi.
