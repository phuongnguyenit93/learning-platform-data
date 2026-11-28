# Operation ở trạng thái in progress quá lâu hoặc không tìm thấy

Khi platform gửi yêu cầu provision, update, deprovision, bind hoặc unbind bất đồng bộ, service broker có thể trả kết quả tiếp nhận trước khi provider hoàn tất công việc. Platform sau đó truy vấn endpoint last_operation để biết operation còn chạy, đã thành công hay thất bại. Nếu broker liên tục trả in progress, platform có thể tiếp tục polling đến khi hết thời gian cho phép. Nếu endpoint trả 404 hoặc broker báo không tìm thấy operation, platform có thể hiểu nhầm rằng tài nguyên không tồn tại hoặc thao tác chưa từng được tạo.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, đây là nhóm sự cố cần điều tra từ đầu đến cuối: request OSB, operation record, outbox/queue, worker, provider và trạng thái mà platform đang lưu. Một operation bị treo không nhất thiết là provider đang chạy lâu; worker có thể đã chết, lease có thể hết hạn, event có thể chưa được publish hoặc kết quả provider đã hoàn tất nhưng broker chưa cập nhật database. Tương tự, “operation không tìm thấy” có thể do sai instance ID, sai operation token, dữ liệu bị xóa quá sớm, đọc nhầm database hoặc broker không lưu trạng thái trước khi trả 202 Accepted.

Bài học này trình bày cách đọc hợp đồng polling của Open Service Broker API (OSB API), xác định endpoint và định danh đúng, phân biệt 404 với 410 Gone, điều tra operation đang chạy quá lâu, xử lý record bị mất và phục hồi an toàn. Các ví dụ dùng Spring Cloud Open Service Broker, Reactor và một kho trạng thái bền vững.

## 1. Hiểu luồng asynchronous operation

Một operation bất đồng bộ thường có các bước:

1. Platform gửi request đến broker.
2. Broker xác thực request, kiểm tra idempotency và ghi nhận operation.
3. Broker trả 202 Accepted nếu request có accepts_incomplete=true và công việc chưa hoàn tất.
4. Platform gọi endpoint last_operation theo chu kỳ.
5. Broker đọc trạng thái operation đã lưu và trả in progress, succeeded hoặc failed.
6. Worker tiếp tục gọi provider, cập nhật tiến độ và ghi kết quả cuối.
7. Platform dừng polling khi nhận succeeded hoặc failed.

Sơ đồ:

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Spring Broker
    participant DB as Operation Store
    participant W as Worker
    participant V as Provider

    P->>B: Provision / Update / Deprovision
    B->>DB: Persist instance + operation + outbox
    DB-->>B: Commit
    B-->>P: 202 Accepted + operation token
    P->>B: GET last_operation
    B->>DB: Read operation state
    DB-->>B: IN_PROGRESS
    B-->>P: 200 state=in progress
    W->>DB: Claim operation
    W->>V: Execute provider action
    V-->>W: Running / result
    W->>DB: Update progress or terminal state
    P->>B: GET last_operation
    B->>DB: Read latest state
    DB-->>B: SUCCEEDED
    B-->>P: 200 state=succeeded
~~~

Điểm quan trọng là platform và broker có hai góc nhìn:

- Platform lưu service instance/binding và operation token mà broker trả về.
- Broker lưu operation state, provider reference và kết quả thực tế.

Hai phía phải liên kết được cùng một operation qua instance ID, binding ID và operation token. Nếu broker chỉ giữ trạng thái trong bộ nhớ của Pod hoặc thread xử lý request, lần polling tiếp theo có thể đến một replica khác và không tìm thấy dữ liệu.

## 2. Xác định đúng endpoint đang được polling

OSB API có endpoint riêng cho service instance và service binding.

| Loại operation | Endpoint last_operation |
|---|---|
| Provision instance | GET /v2/service_instances/{instance_id}/last_operation |
| Update instance | GET /v2/service_instances/{instance_id}/last_operation |
| Deprovision instance | GET /v2/service_instances/{instance_id}/last_operation |
| Create binding | GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}/last_operation |
| Delete binding | GET /v2/service_instances/{instance_id}/service_bindings/{binding_id}/last_operation |

Không dùng endpoint instance để truy vấn trạng thái binding. Với binding, cả instance ID và binding ID đều phải đúng.

Ví dụ request last operation của instance:

~~~http
GET /v2/service_instances/inst-8d31/last_operation?service_id=svc-postgres&plan_id=plan-standard&operation=provision-8d31
X-Broker-API-Version: 2.17
X-Broker-API-Request-Identity: req-5c12
Authorization: Basic ...
~~~

Ví dụ request last operation của binding:

~~~http
GET /v2/service_instances/inst-8d31/service_bindings/bind-2a17/last_operation?service_id=svc-postgres&plan_id=plan-standard&operation=bind-2a17
X-Broker-API-Version: 2.17
~~~

Các ID trong ví dụ chỉ là dữ liệu minh họa. Khi điều tra, lấy URL thật từ access log đã được làm sạch hoặc trace của broker/platform. Không copy Authorization header hoặc credentials vào ticket.

## 3. Các trường trong request cần đối chiếu

Request last_operation có thể chứa các query parameter sau:

| Trường | Ý nghĩa | Điểm cần kiểm tra |
|---|---|---|
| instance_id | ID service instance trong path | Có đúng ID mà broker đã ghi khi provision không |
| binding_id | ID binding trong path binding endpoint | Có đúng binding của instance đó không |
| service_id | ID service offering | Có khớp catalog/instance record không |
| plan_id | ID service plan | Với update đổi plan, platform gửi plan ID trước update |
| operation | Token do broker trả về trong response async | Có được lưu và percent-encode/decode nhất quán không |
| X-Broker-API-Version | Phiên bản OSB API | Broker có hỗ trợ phiên bản platform gửi không |
| X-Broker-API-Request-Identity | Định danh request nếu platform hỗ trợ | Dùng liên kết log và trace |

Một lỗi phổ biến là broker tạo operation token mới ở mỗi lần retry provision. OSB yêu cầu nếu response bất đồng bộ có trường operation, platform phải gửi lại chính giá trị đó khi polling. Token phải ổn định cho cùng operation.

Đối với update đổi plan, OSB quy định plan_id trong request last_operation là ID plan trước khi update. Nếu broker chỉ tra cứu theo plan mới, lookup có thể thất bại dù operation record vẫn tồn tại.

### Percent-encoding của operation

Nếu operation token chứa ký tự đặc biệt, platform gửi nó dưới dạng percent-encoded query parameter. Broker phải dùng giá trị đã được HTTP framework giải mã theo đúng một lần. Không tự decode lần thứ hai hoặc so sánh chuỗi đã encode với chuỗi lưu trong database.

Ưu tiên operation token chỉ dùng ký tự unreserved như chữ, số, dấu gạch ngang và dấu gạch dưới. Điều này giảm lỗi khi đi qua proxy, router và query parser.

## 4. Hợp đồng response của last_operation

Khi truy vấn last_operation hợp lệ, broker trả HTTP 200 OK cùng JSON có state. OSB định nghĩa ba giá trị:

| State | Ý nghĩa | Platform |
|---|---|---|
| in progress | Operation chưa kết thúc | Tiếp tục polling |
| succeeded | Operation hoàn tất thành công | Dừng polling |
| failed | Operation thất bại | Dừng polling |

Ví dụ:

~~~json
{
  "state": "in progress",
  "description": "Đang tạo database và cấu hình quyền truy cập."
}
~~~

Ví dụ kết thúc thành công:

~~~json
{
  "state": "succeeded",
  "description": "Service instance đã sẵn sàng."
}
~~~

Ví dụ thất bại:

~~~json
{
  "state": "failed",
  "description": "Provider không thể hoàn tất thao tác."
}
~~~

Không tự tạo state như pending, running, completed hoặc error trong response OSB nếu không được framework ánh xạ về ba giá trị hợp lệ. Các trạng thái chi tiết hơn có thể tồn tại nội bộ, nhưng response phải dùng đúng enum của giao thức.

Với update hoặc deprovision thất bại, response có thể cần thêm:

- instance_usable: cho biết instance còn sử dụng được hay không.
- update_repeatable: chỉ dành cho lỗi update, cho biết có thể lặp lại cùng update hay không.

Không gửi hai field này cho lỗi operation khác. Giá trị phải phản ánh trạng thái thực tế của tài nguyên, không chỉ dựa vào exception class.

## 5. Phân biệt 200, 400, 404 và 410 Gone

Một trong những nguyên nhân khiến platform polling mãi hoặc xóa nhầm metadata là broker trả sai HTTP status.

| HTTP status | Ngữ nghĩa của OSB last_operation | Cách xử lý |
|---|---|---|
| 200 OK | Đọc và trả được trạng thái operation | Body phải có state hợp lệ |
| 400 Bad Request | Request malformed hoặc thiếu dữ liệu bắt buộc | Kiểm tra URL, query parameter và API request |
| 404 Not Found | Service instance hoặc service binding được truy vấn không tồn tại | Kiểm tra resource ID và record |
| 410 Gone | Chỉ phù hợp với asynchronous delete khi broker xác nhận resource đã gone | Platform coi việc xóa là thành công và quên resource |
| 5xx hoặc status khác | Lỗi hoặc response không hợp lệ theo contract | Platform có thể tiếp tục polling đến giới hạn |

### Không dùng 404 chỉ vì không tìm thấy operation token

404 của endpoint instance last_operation có nghĩa service instance đang được truy vấn không tồn tại. Với endpoint binding last_operation, 404 có nghĩa binding được truy vấn không tồn tại.

OSB không định nghĩa 404 là “operation ID không tồn tại trong bảng operation”. Nếu instance vẫn tồn tại nhưng lookup theo operation token bị lỗi, cần điều tra correlation và state store. Không chuyển lỗi lookup nội bộ thành 404 một cách máy móc.

### 410 Gone chỉ dành cho delete bất đồng bộ

410 Gone phù hợp khi broker đã xác nhận resource được deprovision hoặc binding đã được xóa và platform đang tiếp tục poll kết quả delete. Platform phải xem 410 là thành công và xóa metadata resource tương ứng.

Không trả 410 cho provision hoặc update đang chạy. Không trả 410 cho deprovision chỉ vì broker mất operation record hoặc provider timeout. Nếu resource vẫn có thể tồn tại, broker phải giữ trạng thái để tiếp tục reconcile.

### Giữ tombstone cho delete

Khi deprovision thành công, broker có thể cần xóa record instance chính để hoàn tất cleanup. Tuy nhiên, nếu xóa luôn operation record trước khi platform poll lần cuối, request last_operation có thể trả 404.

Giải pháp là giữ tombstone hoặc bản ghi terminal đủ lâu. Tombstone chứa instance ID, operation ID, operation type, terminal state và thời điểm hoàn tất. Khi resource provider đã chắc chắn bị xóa, broker có thể trả succeeded hoặc 410 theo thiết kế và contract. Sau retention, dữ liệu mới được dọn theo policy.

## 6. Vì sao operation bị in progress quá lâu?

Có nhiều nguyên nhân khác nhau. Không nên bắt đầu bằng việc tăng polling frequency hoặc gửi lại provision.

| Nhóm nguyên nhân | Dấu hiệu | Nơi kiểm tra |
|---|---|---|
| Provider thực sự xử lý lâu | Provider operation vẫn running và có tiến độ | Provider API/console |
| Worker không chạy | Operation có state IN_PROGRESS nhưng heartbeat không đổi | Deployment, scheduler, queue consumer |
| Event chưa publish | Outbox còn unpublished | Outbox publisher và transaction |
| Message bị dead-letter | Queue có message lỗi hoặc hết retry | Queue/DLQ |
| Worker bị mất lease | Lease hết hạn nhưng không có worker nhận lại | Lease table, lock và recovery scheduler |
| Provider timeout không xác định | Broker không biết side effect đã xảy ra chưa | Provider request ID và reconciliation |
| Kết quả không được persist | Provider thành công nhưng operation row vẫn in progress | Database transaction và worker logs |
| Đọc dữ liệu cũ | Database primary đã terminal nhưng API vẫn thấy in progress | Read replica, cache và transaction isolation |
| Sai correlation | Platform poll token khác token operation record | Response 202 và query operation |
| Operation bị khóa | Worker khác giữ lock hoặc operation mutation xung đột | Lock/lease và concurrency policy |
| Dependency không khả dụng | Database, secret manager hoặc provider lỗi | Connection pool, timeout và health |

Hãy phân biệt **operation chậm có tiến triển** với **operation không còn tiến triển**. Hai trường hợp cần hướng xử lý khác nhau.

## 7. Bắt đầu điều tra bằng một mốc thời gian

Thu thập một timeline duy nhất cho operation:

1. Thời điểm platform gửi request provision/update/delete/bind/unbind.
2. Thời điểm broker nhận request và tạo operation record.
3. Thời điểm broker commit operation và outbox.
4. Thời điểm broker trả 202 Accepted.
5. Thời điểm worker claim operation.
6. Thời điểm gọi provider và nhận provider request/operation ID.
7. Các heartbeat hoặc progress update.
8. Thời điểm provider báo terminal.
9. Thời điểm broker ghi terminal state.
10. Các lần platform gọi last_operation và response tương ứng.

Dùng các ID để liên kết:

- service instance ID.
- binding ID nếu có.
- broker operation ID.
- operation token trả cho platform.
- provider operation/request ID.
- correlation ID.
- X-Broker-API-Request-Identity nếu platform gửi.

Đồng bộ thời gian giữa broker, database, worker và provider bằng NTP. Nếu timestamp lệch nhiều, log có thể khiến operator kết luận nhầm rằng worker chạy trước khi request được nhận hoặc provider đã kết thúc sau khi platform hết timeout.

Không ghi credentials hoặc request body nhạy cảm trong timeline. Chỉ dùng opaque reference và metadata được phép.

## 8. Quy trình chẩn đoán operation in progress

Thực hiện theo thứ tự để tránh thay đổi state khi chưa hiểu nguyên nhân.

### Bước 1: Xác nhận request đầu tiên có thật sự asynchronous

Kiểm tra response của operation tạo ra lần polling:

- Có phải HTTP 202 Accepted không?
- Request có accepts_incomplete=true không?
- Response có operation token không?
- Token có được lưu trong platform và broker không?
- Instance ID/binding ID có khớp không?

Theo OSB, nếu broker không thể hoàn tất đồng bộ và request không có accepts_incomplete=true, broker phải trả 422 Unprocessable Entity với error AsyncRequired. Không trả 202 cho một request không cho phép async.

### Bước 2: Gọi last_operation trực tiếp bằng đúng thông tin

Trong môi trường được phép, dùng HTTP client hoặc curl để kiểm tra cùng endpoint, query và API version. Không ghi password trực tiếp vào shell history; dùng secret injection hoặc client có credential store.

Ví dụ:

~~~bash
curl -i \
  -u "$BROKER_USER:$BROKER_PASSWORD" \
  -H "X-Broker-API-Version: 2.17" \
  "https://broker.example.com/v2/service_instances/inst-8d31/last_operation?service_id=svc-postgres&plan_id=plan-standard&operation=provision-8d31"
~~~

Trong production, tránh bật shell tracing và tránh in biến chứa secret. Lệnh trên minh họa cách gọi; endpoint, API version và authentication phải khớp platform thực tế.

Ghi nhận:
- HTTP status.
- state trong JSON.
- description.
- Retry-After nếu có.
- request identity/correlation reference.
- response time.

Nếu request trực tiếp trả succeeded nhưng platform vẫn báo in progress, kiểm tra cache, polling request khác instance ID hoặc platform đang dùng operation token cũ.

### Bước 3: Kiểm tra operation record

Tra cứu operation bằng instance ID và operation token. Kiểm tra:

- Có record không?
- operation type có đúng không?
- State hiện tại là gì?
- started_at và updated_at có hợp lý không?
- heartbeat gần nhất là lúc nào?
- attempt_count có tăng không?
- lease_owner và lease_until có hợp lệ không?
- provider_operation_id đã được ghi chưa?
- terminal result đã commit chưa?

Nếu state IN_PROGRESS nhưng updated_at cũ hơn ngưỡng lease/heartbeat, đánh dấu operation cần phục hồi. Không tự đổi thành SUCCEEDED chỉ vì đã hết timeout.

### Bước 4: Kiểm tra outbox và queue

Nếu broker dùng transactional outbox:

- Có event cho operation không?
- Event đã được publish chưa?
- Publisher có lỗi serialization hoặc authentication không?
- Message có nằm trong queue đúng không?
- Có bị dead-letter không?
- Consumer group có active worker không?
- Message có bị redeliver liên tục không?

Nếu event chưa publish, khôi phục publisher theo cơ chế retry. Nếu message dead-letter, đọc error category và quyết định replay sau khi sửa nguyên nhân. Không xóa message hoặc operation record để làm sạch dashboard.

### Bước 5: Kiểm tra worker

Xác nhận worker có nhận operation và tiến triển:

- Worker replica có healthy không?
- Scheduler có bị disable do profile hoặc cấu hình không?
- Lease có bị giữ bởi process đã chết không?
- Worker có exception trước khi gọi provider không?
- Có connection pool exhaustion không?
- Thread/Reactive pipeline có bị block không?
- Worker có retry vô hạn mà không cập nhật attempt/next_attempt_at không?

Với nhiều worker replica, kiểm tra cơ chế claim có atomic không. Hai worker không được thực hiện cùng side effect đồng thời chỉ vì lease hoặc lock được quản lý sai.

### Bước 6: Kiểm tra provider

Tra cứu provider bằng external operation ID hoặc idempotency key:

- Provider chưa nhận request?
- Provider đang chạy?
- Provider đã thành công nhưng response bị mất?
- Provider đã thất bại?
- Resource đã tồn tại nhưng broker chưa lưu ID?
- Provider đang rate-limit hoặc chờ quota?
- Provider operation đã bị hủy thủ công?

Nếu provider trả kết quả terminal nhưng broker chưa cập nhật, phục hồi từ kết quả đã xác minh. Nếu provider không xác định được kết quả, giữ state UNKNOWN/RECONCILIATION_REQUIRED và tiếp tục đối soát.

### Bước 7: Đối chiếu với platform

Cuối cùng so sánh response broker với trạng thái platform:
- Platform đang poll đúng instance/binding?
- Query operation có giống response ban đầu?
- Có request retry tạo operation mới không?
- Platform có dừng polling do hết maximum polling duration?
- Có proxy/cache trả response cũ?
- Có nhiều platform consumer dùng cùng broker và cùng resource ID không?

Không kết luận broker lỗi chỉ từ dòng “operation in progress” trên UI platform. Cần xem request và response last_operation thực tế.

## 9. Chẩn đoán operation không tìm thấy

“Không tìm thấy operation” thường xuất hiện ở một trong các tầng:

1. Platform không tìm thấy service instance/binding.
2. Broker không tìm thấy instance/binding trong database.
3. Broker có instance nhưng không tìm thấy operation tương ứng.
4. Worker không tìm thấy queue message.
5. Provider không tìm thấy external operation.
6. Một replica đọc sai database hoặc dữ liệu chưa được commit.

Phân loại trước khi xử lý:

| Dấu hiệu | Khả năng | Hướng kiểm tra |
|---|---|---|
| HTTP 404 từ instance last_operation | Instance không có trong broker hoặc sai ID | Instance store, tenant scope, path |
| HTTP 404 từ binding last_operation | Binding không tồn tại | Binding store, instance ID và binding ID |
| Instance tồn tại nhưng operation token lookup rỗng | Token mismatch, record bị xóa hoặc lưu sai | Response 202, query operation và retention |
| Operation record có nhưng queue message không có | Outbox publish lỗi hoặc message đã ack | Outbox, queue, worker audit |
| Queue message có nhưng provider operation không có | Worker chưa gọi provider hoặc request bị reject trước side effect | Worker logs và provider request logs |
| Provider resource có nhưng broker không có instance | Side effect xảy ra trước khi state commit hoặc restore dữ liệu bị lệch | Provider tags/reference và reconciliation |
| Chỉ một replica báo not found | Cấu hình datasource/schema hoặc cache khác nhau | Pod environment, DB endpoint, cache |
| Sau deprovision mới xuất hiện 404 | Xóa operation record quá sớm | Tombstone và retention |

### Kiểm tra instance ID và binding ID

ID trong path là giá trị platform đã gửi trong request provision/bind. Broker phải lưu nguyên định danh đó và dùng cùng quy tắc chuẩn hóa ở tất cả endpoint.

Không:
- lower-case ID nếu OSB/platform không quy định.
- trim hoặc biến đổi ID tùy tiện.
- dùng tên service instance thay cho ID.
- tìm binding chỉ bằng binding ID mà bỏ qua instance ID và tenant/platform scope.
- decode URL path nhiều lần.

Nếu broker có nhiều platform, có thể cần namespace theo platform hoặc tenant. Cùng một ID có thể không được giả định duy nhất giữa các integration nếu broker tự đặt phạm vi định danh. Dữ liệu lookup phải áp dụng đúng scope đã lưu khi tạo instance.

### Kiểm tra operation token

Khi broker trả operation trong response async, token đó phải được lưu bền vững và dùng lại cho request retry cùng operation. Không tạo token ngẫu nhiên mới ở mỗi lần platform gửi lại PUT/DELETE.

Nếu query có operation:
- so sánh sau khi framework đã parse URL.
- không so sánh với chuỗi đã percent-encode.
- kiểm tra token thuộc đúng instance và operation type.
- không để operation token của instance khác truy cập record.
- không dùng token làm bí mật hoặc cơ chế authorization.

Nếu instance tồn tại nhưng token không khớp, đó là lỗi tương quan operation cần điều tra. Không trả 404 chỉ vì truy vấn token không tìm thấy.

## 10. Trường hợp instance đang provision nhưng endpoint khác trả 404

OSB có endpoint GET service instance khi catalog khai báo instances_retrievable=true. Endpoint fetch instance có thể trả 404 khi instance chưa tồn tại hoặc provision vẫn đang in progress. Điều này khác với endpoint last_operation.

Phân biệt:

| Endpoint | 404 có nghĩa |
|---|---|
| GET /v2/service_instances/{id} | Instance không tồn tại hoặc provision còn đang in progress |
| GET /v2/service_instances/{id}/last_operation | Instance được poll không tồn tại |
| GET /v2/service_instances/{id}/service_bindings/{binding_id}/last_operation | Binding được poll không tồn tại |

Nếu UI hoặc log chỉ ghi “404”, hãy lấy request path đầy đủ đã làm sạch trước khi kết luận. Một 404 từ fetch instance trong lúc provision có thể là hành vi theo contract; 404 từ last_operation có thể khiến platform không nhận được trạng thái cần thiết.

## 11. State store và thứ tự commit

Một nguyên nhân quan trọng của operation không tìm thấy là broker trả 202 trước khi dữ liệu được commit.

Thứ tự sai:

1. Nhận request.
2. Trả 202.
3. Tạo operation record bất đồng bộ.
4. Database insert thất bại hoặc Pod restart.
5. Platform poll và không tìm thấy operation.

Thứ tự đúng:

1. Xác thực request và kiểm tra idempotency.
2. Tạo instance/binding record ở trạng thái phù hợp.
3. Tạo operation record với token ổn định.
4. Ghi outbox event trong cùng transaction.
5. Commit transaction.
6. Trả 202 Accepted cùng operation token.
7. Publisher/worker thực thi công việc.

Mẫu bảng operation minh họa:

~~~sql
CREATE TABLE broker_operation (
    operation_id          VARCHAR(255) PRIMARY KEY,
    operation_token       VARCHAR(255) NOT NULL,
    instance_id           VARCHAR(255) NOT NULL,
    binding_id            VARCHAR(255),
    operation_type        VARCHAR(32) NOT NULL,
    state                 VARCHAR(32) NOT NULL,
    progress_percent      INTEGER,
    provider_operation_id VARCHAR(512),
    attempt_count         INTEGER NOT NULL DEFAULT 0,
    lease_owner           VARCHAR(255),
    lease_until           TIMESTAMP,
    started_at            TIMESTAMP NOT NULL,
    updated_at            TIMESTAMP NOT NULL,
    completed_at          TIMESTAMP,
    error_code            VARCHAR(128)
);
~~~

Đây là schema minh họa. Cần bổ sung index, foreign key, unique constraint và tenant/platform scope phù hợp. Có thể đặt unique constraint trên operation token trong phạm vi broker, hoặc trên cặp instance ID + operation token nếu thiết kế cho phép nhiều platform.

### Outbox phải được commit cùng operation

Nếu operation row được commit nhưng event không được publish, worker không chạy và platform thấy in progress mãi. Transactional outbox giải quyết khoảng trống giữa ghi database và publish message:

~~~sql
CREATE TABLE broker_outbox (
    event_id       VARCHAR(255) PRIMARY KEY,
    operation_id   VARCHAR(255) NOT NULL,
    event_type     VARCHAR(128) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP
);
~~~

Publisher đọc event chưa publish, gửi queue và đánh dấu published. Nếu publisher crash sau khi gửi nhưng trước khi đánh dấu, event có thể được gửi lại; worker phải idempotent.

## 12. Kiểm tra worker lease và heartbeat

Worker có thể chết sau khi claim operation. Nếu không có lease, operation có thể bị kẹt ở RUNNING mãi vì hệ thống nghĩ vẫn có worker sở hữu.

Một lease nên có:
- worker ID.
- lease_until.
- heartbeat_at.
- attempt_count.
- trạng thái claim.
- fencing/version token nếu cần ngăn worker cũ ghi đè worker mới.

Quy trình recovery:

1. Tìm operation ở trạng thái RUNNING nhưng lease đã hết hạn.
2. Kiểm tra worker owner còn sống hay không.
3. Tra cứu provider để biết side effect đã xảy ra chưa.
4. Nếu chưa thực hiện, claim lại operation và retry bằng cùng idempotency key.
5. Nếu provider đang chạy, cập nhật provider operation reference và tiếp tục poll.
6. Nếu provider đã thành công, ghi terminal result.
7. Nếu provider đã thất bại, phân loại lỗi và quyết định retry/compensation.

Không reclaim lease chỉ dựa vào thời gian nếu provider request vẫn đang chạy và không idempotent. Worker cũ có thể vẫn tiếp tục sau network partition; fencing token hoặc compare-and-set giúp ngăn nó ghi state cũ sau khi worker mới đã nhận quyền.

## 13. Phân biệt timeout của từng lớp

Một operation có thể bị ảnh hưởng bởi nhiều timeout:

| Timeout | Ý nghĩa | Nếu quá ngắn |
|---|---|---|
| Platform request timeout | Thời gian chờ response provision/update/delete | Platform retry trong khi broker vẫn đang xử lý |
| Reverse proxy timeout | Thời gian proxy giữ HTTP request | Response bị cắt dù broker có thể đã trả |
| Provider connect timeout | Thời gian thiết lập kết nối | Lỗi kết nối sớm |
| Provider read timeout | Thời gian chờ response provider | Unknown outcome nếu provider đã thực hiện side effect |
| Worker step timeout | Giới hạn một bước workflow | Step có thể bị retry khi chưa biết kết quả |
| Operation deadline | Thời gian tối đa workflow được phép chạy | Operation cần chuyển sang terminal/repair policy |
| Platform polling duration | Thời gian platform tiếp tục polling | Platform ngừng polling và coi operation thất bại |

Không tăng tất cả timeout cùng lúc. Xác định lớp nào hết hạn trước và liệu provider có side effect hay chưa.

Với operation dài, dùng asynchronous OSB để trả 202 sớm. Request HTTP đầu tiên không nên chờ toàn bộ thời gian provider. Worker tiếp tục chạy; platform poll last_operation theo chu kỳ.

## 14. Polling interval và maximum polling duration

OSB cho phép response last_operation có header Retry-After để hướng dẫn platform thời gian chờ trước lần poll kế tiếp. Header này giúp giảm request polling quá dày khi provider xử lý lâu.

Catalog của service plan có thể công bố maximum_polling_duration, tính bằng giây. Platform có thể sử dụng giá trị này cùng giới hạn riêng của nó. Nếu maximum polling duration của platform hoặc plan đạt tới, platform SHOULD dừng polling và operation state được xem là failed theo spec.

Broker nên:
- Chọn duration phù hợp với đặc tính provider.
- Không để operation in progress vượt thời hạn mà không có quyết định phục hồi.
- Gửi Retry-After hợp lý khi cần.
- Cập nhật progress description khi có thay đổi thực sự.
- Đưa operation quá hạn sang timeout/reconciliation/manual repair policy.
- Không dùng polling interval quá ngắn như cách tạo thêm tải lên database.

Không giả định mọi platform dùng cùng polling interval hoặc cùng maximum duration. Đối chiếu giá trị catalog, platform config và log thực tế.

## 15. Cách triển khai getLastOperation trong Spring Cloud Open Service Broker

Nếu broker hỗ trợ asynchronous create, update hoặc delete service instance, cần triển khai getLastOperation trong ServiceInstanceService. Nếu hỗ trợ asynchronous create/delete binding, triển khai getLastOperation trong ServiceInstanceBindingService.

Spring Cloud Open Service Broker dùng Reactor Mono cho API reactive. Ví dụ skeleton cho service instance:

~~~java
@Service
public class BrokerServiceInstanceService
        implements ServiceInstanceService {

    private final OperationStore operationStore;

    public BrokerServiceInstanceService(
            OperationStore operationStore) {
        this.operationStore = operationStore;
    }

    @Override
    public Mono<GetLastServiceOperationResponse> getLastOperation(
            GetLastServiceOperationRequest request) {

        String instanceId = request.getServiceInstanceId();
        String operationToken = request.getOperation();

        return operationStore.findForPolling(
                instanceId, operationToken)
            .map(operation -> {
                GetLastServiceOperationResponse
                    .GetLastServiceOperationResponseBuilder response =
                        GetLastServiceOperationResponse.builder()
                            .operationState(toOperationState(
                                operation.state()))
                            .description(
                                operation.safeDescription());

                if (operation.isUpdateFailure()) {
                    response.instanceUsable(
                        operation.instanceUsable());
                    response.updateRepeatable(
                        operation.updateRepeatable());
                }

                return response.build();
            })
            .switchIfEmpty(Mono.defer(() ->
                resolveMissingOperation(instanceId, operationToken)));
    }

    private Mono<GetLastServiceOperationResponse> resolveMissingOperation(
            String instanceId, String operationToken) {
        // Check the durable instance record and any delete tombstone first.
        // If the instance is absent, raise the framework's resource-not-found
        // exception. If it exists but the token is unknown, raise an internal
        // reconciliation error; do not translate that mismatch to HTTP 404.
        return Mono.error(new OperationLookupRequiresReconciliationException(
            instanceId, operationToken));
    }

    private OperationState toOperationState(
            BrokerOperationState state) {
        return switch (state) {
            case QUEUED, RUNNING, RECONCILIATION_REQUIRED ->
                OperationState.IN_PROGRESS;
            case SUCCEEDED -> OperationState.SUCCEEDED;
            case FAILED -> OperationState.FAILED;
        };
    }
}
~~~

Đây là skeleton minh họa. OperationStore và BrokerOperationState là abstraction nội bộ. Trong triển khai thật, khi không tìm thấy operation phải phân biệt:
- Instance không tồn tại.
- Instance tồn tại nhưng operation token không khớp.
- Operation record đã được archive.
- Instance đang được deprovision và có tombstone.
- Dữ liệu state store đang không khả dụng.

Không dùng một nhánh empty chung để trả 404 cho mọi trường hợp.

Với binding, implement getLastOperation(GetLastServiceBindingOperationRequest) trong ServiceInstanceBindingService và trả GetLastServiceBindingOperationResponse với ba state tương ứng. Lookup phải dùng cả instance ID và binding ID.

### Không subscribe thủ công trong getLastOperation

Phương thức chỉ đọc trạng thái đã lưu và trả Mono. Không gọi subscribe() hoặc khởi chạy provider workflow mới trong mỗi lần polling. Platform có thể gọi endpoint nhiều lần; polling phải nhẹ, idempotent và không tạo side effect.

## 16. Ví dụ trạng thái nội bộ và ánh xạ ra OSB

Broker có thể dùng nhiều trạng thái nội bộ hơn ba state của OSB:

| State nội bộ | State trả platform | Ý nghĩa |
|---|---|---|
| ACCEPTED | in progress | Đã ghi nhận request |
| QUEUED | in progress | Đang chờ worker |
| RUNNING | in progress | Worker đang thực hiện |
| WAITING_PROVIDER | in progress | Provider đang xử lý |
| RETRY_WAIT | in progress | Chờ retry có giới hạn |
| RECONCILIATION_REQUIRED | in progress | Cần xác định side effect |
| COMPENSATING | in progress | Đang thu hồi side effect sau lỗi |
| SUCCEEDED | succeeded | Operation hoàn tất |
| FAILED | failed | Operation thất bại theo kết quả đã xác định |
| NEEDS_MANUAL_REPAIR | failed | Operation không thể tiếp tục tự động, đã bàn giao vận hành |

NEEDS_MANUAL_REPAIR không phải state OSB. Nếu broker trả failed, cần mô tả rõ rằng thao tác không thành công và cung cấp support reference. Cleanup nội bộ có thể tiếp tục bằng một workflow riêng được theo dõi, nhưng không giữ platform polling in progress vô thời hạn.

Không ánh xạ UNKNOWN thành succeeded. Khi provider chưa xác định kết quả, tiếp tục reconciliation trong giới hạn operation deadline.

## 17. Xử lý async retry và idempotency

Platform có thể gửi lại request ban đầu do mất response, timeout hoặc retry ở tầng HTTP. Broker phải nhận ra request lặp và trả lại cùng operation đang chạy.

Đối với provision:
- Dùng instance ID và request fingerprint để xác định request lặp.
- Lưu operation token ổn định.
- Nếu instance chưa provision xong, request PUT gửi lại phải trả 202 Accepted với cùng operation.
- Không trả 200 OK chỉ vì instance record đã được tạo trong database trong khi provider chưa sẵn sàng.
- Nếu cùng instance ID nhưng attributes khác, xử lý conflict theo OSB.

Đối với binding:
- Dùng cặp instance ID và binding ID để xác định binding.
- Lưu operation token và trạng thái binding.
- Nếu create binding bất đồng bộ, platform poll binding last_operation.
- Không tạo credentials mới mỗi lần retry cùng một binding request.

Đối với update/deprovision:
- Serialize mutation trên cùng resource nếu broker không hỗ trợ concurrency.
- Trả ConcurrencyError theo OSB khi request xung đột.
- Không cho worker cũ ghi đè kết quả operation mới hơn.

Một idempotency key ổn định có thể được tạo từ operation ID và step key. Không sinh key mới ở mỗi lần retry.

## 18. Khôi phục khi operation record thực sự bị mất

Nếu instance còn tồn tại nhưng operation record bị mất, không được tạo lại tài nguyên ngay. Thực hiện reconciliation:

1. Dừng các request mutation mới trên instance nếu trạng thái chưa rõ.
2. Tra cứu provider theo external reference, instance tag hoặc idempotency key.
3. Kiểm tra audit/outbox/event history và backup state store.
4. Xác định operation đã hoàn tất, đang chạy hay chưa từng được thực hiện.
5. Khôi phục operation record từ dữ liệu có thẩm quyền nếu có.
6. Nếu không thể khôi phục chính xác, tạo recovery operation mới có liên kết đến operation cũ và ghi audit.
7. Chỉ tiếp tục retry hoặc compensation sau khi xác minh ownership và side effect.

Không tạo operation token giả để làm platform ngừng polling nếu không có bằng chứng về kết quả. Nếu operation không thể xác định trong thời hạn, chuyển sang failure/recovery policy rõ ràng và thông báo cho operator.

### Khôi phục record đã xóa nhầm

Nếu database có point-in-time recovery hoặc backup, có thể trích xuất đúng record cần phục hồi. Không restore toàn bộ database production chỉ để lấy một operation row nếu việc đó sẽ ghi đè thay đổi mới. Dùng quy trình restore vào môi trường tạm, đối chiếu rồi merge record theo khóa và version.

Nếu có audit log hoặc event store, có thể dựng lại state từ các event đã commit. Event replay phải idempotent và có checkpoint để không chạy lại side effect provider.

## 19. Deprovision bị mất record và orphan resource

Một tình huống đặc biệt là delete service instance đã bắt đầu, broker xóa record instance rồi platform vẫn poll last_operation. Nếu broker không giữ tombstone, endpoint có thể trả 404 và platform không biết delete đã hoàn tất hay chưa.

Cách xử lý:
- Chỉ xóa instance record chính sau khi provider resource được xác nhận đã xóa.
- Giữ operation/tombstone để phục vụ last_operation.
- Nếu tài nguyên đã gone và operation là asynchronous delete, có thể trả 410 Gone theo OSB.
- Nếu provider chưa xác nhận xóa, tiếp tục trả in progress hoặc failed theo state thực.
- Reconcile orphan resources bằng external reference và ownership metadata.

Với asynchronous provision thất bại, platform có thể cần orphan mitigation. Broker cần lưu đủ thông tin provider resource để xác định và thu hồi tài nguyên đã tạo một phần. Không xóa operation history ngay khi trả failed.

## 20. Cache và read replica có thể làm state cũ

Nếu API Pod đọc operation từ read replica hoặc cache, nó có thể thấy IN_PROGRESS dù primary database đã lưu SUCCEEDED.

Kiểm tra:
- Query last_operation có đọc primary hay read replica?
- Cache key có bao gồm instance ID và operation token?
- Cache TTL có dài hơn polling interval không?
- Worker update có invalidate cache không?
- Transaction isolation có giữ snapshot cũ?
- Replica lag có vượt thời gian bình thường không?

last_operation thường cần dữ liệu trạng thái mới nhất. Tránh cache response in progress lâu. Nếu dùng cache, TTL phải ngắn và invalidation phải được kiểm thử. Với terminal state, giữ dữ liệu bền vững trong operation store thay vì phụ thuộc cache.

Không dùng sticky session để che lỗi đọc replica. Request kế tiếp có thể đến Pod khác; tất cả replica phải đọc được cùng state có thẩm quyền.

## 21. Quan sát operation để phát hiện sớm

Metric hữu ích:

| Metric | Mục đích |
|---|---|
| broker_operation_in_progress | Số operation đang chạy theo type |
| broker_operation_age_seconds | Tuổi operation hiện tại |
| broker_operation_last_progress_age_seconds | Thời gian từ lần progress gần nhất |
| broker_operation_not_found_total | Số lần lookup không tìm thấy resource/operation |
| broker_operation_timeout_total | Số operation vượt deadline |
| broker_worker_lease_expired_total | Số lease hết hạn |
| broker_outbox_unpublished | Event chưa publish |
| broker_queue_lag_seconds | Độ trễ xử lý queue |
| broker_provider_operation_age_seconds | Tuổi provider operation |
| broker_last_operation_latency | Thời gian phản hồi polling |

Alert nên dựa trên tuổi operation và thiếu heartbeat, không chỉ dựa trên tổng số operation in progress. Một operation provider chạy 15 phút có thể bình thường với plan lớn; một operation 2 phút không có heartbeat có thể đáng điều tra.

Log mỗi transition:
- operation ID.
- instance/binding ID đã được bảo vệ.
- operation token dạng opaque hoặc hash nếu phù hợp.
- state trước và sau.
- worker ID.
- provider operation ID an toàn.
- attempt count.
- thời gian và error category.

Không log credentials, Authorization header, request body hoặc secret.

## 22. Các kịch bản troubleshooting thường gặp

### Kịch bản A: Operation in progress, worker không hoạt động

Dấu hiệu:
- operation state RUNNING.
- heartbeat không đổi.
- queue không còn message hoặc message đã dead-letter.
- không có provider operation ID.

Cách xử lý:
1. Kiểm tra worker deployment/scheduler.
2. Kiểm tra outbox publish status.
3. Kiểm tra lease hết hạn.
4. Claim lại operation bằng recovery worker.
5. Dùng cùng idempotency key.
6. Ghi audit cho lần phục hồi.

Không sửa state trực tiếp thành SUCCEEDED.

### Kịch bản B: Provider thành công nhưng broker vẫn in progress

Dấu hiệu:
- provider resource tồn tại.
- provider operation terminal success.
- operation database vẫn RUNNING.

Cách xử lý:
1. Xác minh provider resource thuộc đúng instance/operation.
2. Lấy external resource ID và provider operation result.
3. Chạy recovery handler để ghi kết quả vào state store.
4. Commit terminal state.
5. Kiểm tra endpoint last_operation trả succeeded.
6. Kiểm tra platform đã dừng polling.

Không gọi create lần nữa.

### Kịch bản C: Platform poll operation token khác broker

Dấu hiệu:
- response 202 có token A.
- query last_operation có operation B.
- instance vẫn tồn tại.

Cách xử lý:
1. Kiểm tra serialization response.
2. Kiểm tra URL encoding/decoding.
3. Kiểm tra proxy có rewrite query không.
4. Kiểm tra retry tạo token mới không.
5. Sửa mapping để token ổn định.
6. Không trả 404 cho instance đang tồn tại chỉ vì token mismatch.

### Kịch bản D: Deprovision đã xóa provider nhưng platform nhận 404

Dấu hiệu:
- provider xác nhận resource đã xóa.
- instance row đã bị xóa.
- operation row cũng bị xóa.
- platform vẫn poll last_operation.

Cách xử lý:
1. Khôi phục bằng tombstone nếu còn audit.
2. Xác nhận delete đã hoàn tất.
3. Trả terminal state hoặc 410 Gone theo OSB semantics.
4. Thiết lập retention để không xóa operation quá sớm.
5. Bổ sung test polling sau deprovision.

### Kịch bản E: Một Pod trả in progress, Pod khác trả not found

Dấu hiệu:
- cùng request, kết quả khác theo Pod.
- cấu hình datasource hoặc cache không đồng nhất.

Cách xử lý:
1. So sánh env/config của các Pod.
2. Kiểm tra database/schema/tenant routing.
3. Kiểm tra cache và read replica.
4. Bảo đảm tất cả replica dùng cùng state store.
5. Kiểm tra migration đã chạy trên schema đúng.
6. Không dùng sticky session làm giải pháp lâu dài.

## 23. Quy trình phục hồi an toàn

Khi operation bị treo hoặc không tìm thấy, hãy áp dụng thứ tự:

1. Thu thập instance ID, binding ID, operation token, correlation ID và provider reference.
2. Xác nhận endpoint, query parameter và OSB API version.
3. Đọc operation store trên nguồn dữ liệu có thẩm quyền.
4. Kiểm tra outbox, queue, worker lease và heartbeat.
5. Tra cứu provider để xác định side effect.
6. Chọn retry, reconcile, compensation hoặc manual repair.
7. Ghi state transition và audit.
8. Gọi last_operation và xác nhận response đúng contract.
9. Kiểm tra platform dừng polling khi nhận terminal state.
10. Giữ terminal record/tombstone theo retention.

Không:
- Xóa operation row để dừng cảnh báo.
- Trả succeeded chỉ để platform ngừng polling.
- Trả 410 khi provider resource có thể vẫn tồn tại.
- Trả 404 chỉ vì operation token lookup bị lỗi.
- Gửi lại create/delete khi kết quả provider chưa xác định.
- Sửa database bằng SQL không có audit hoặc không qua recovery procedure.

Nếu phải thao tác thủ công, ghi người thực hiện, thời điểm, bằng chứng provider và kết quả. Sau manual repair, cập nhật broker state để worker không tiếp tục xử lý một operation đã được giải quyết.

## 24. Kiểm thử để ngăn lỗi tái diễn

Dùng integration test với provider stub và state store thật hoặc Testcontainers để mô phỏng:

| Tình huống | Kết quả mong đợi |
|---|---|
| Provision async, worker chạy bình thường | 202, polling in progress rồi succeeded |
| Worker chưa nhận event | Operation vẫn queued; publisher/worker phục hồi |
| Worker crash sau claim | Lease hết hạn và operation được claim lại |
| Provider timeout sau side effect | State unknown; reconcile trước retry |
| Provider thành công, DB update lỗi | Recovery ghi terminal state mà không tạo resource trùng |
| Operation token có ký tự đặc biệt | Query được decode và đối chiếu đúng |
| Operation token mismatch, instance tồn tại | Không trả 404 sai ngữ nghĩa |
| Instance không tồn tại | Instance last_operation trả 404 |
| Binding không tồn tại | Binding last_operation trả 404 |
| Async delete đã xác nhận resource gone | Có thể trả 410 theo contract |
| Create/update bị poll quá hạn | Deadline policy tạo terminal/recovery state |
| Update đổi plan | Poll lookup dùng plan ID trước update |
| Hai request mutation đồng thời | Concurrency được serialize hoặc trả ConcurrencyError |
| Nhiều broker replica | Replica bất kỳ đọc cùng state |
| Terminal state được poll lại | Kết quả vẫn được trả trong retention |
| Cache chứa state cũ | Invalidation/TTL không che terminal state |
| Pod restart giữa operation | Worker phục hồi từ durable state |

Ngoài kiểm thử tự động, cần chạy một kịch bản end-to-end qua platform thật hoặc test client tương thích OSB. Xác nhận platform dừng polling sau succeeded/failed và xử lý 410 đúng cho delete.

## 25. Những lỗi thường gặp

**Trả 202 trước khi commit operation record.** Platform poll ngay nhưng broker chưa có dữ liệu. Commit instance, operation và outbox trước response.

**Sinh operation token mới ở mỗi retry.** Platform poll token cũ và broker không tìm thấy. Giữ token ổn định cho cùng operation.

**Giữ state trong memory.** Request polling tới Pod khác sẽ không thấy operation. Dùng database/queue bền vững.

**Trả in progress dù worker đã chết.** Không có heartbeat hoặc recovery. Dùng lease và scheduler phục hồi.

**Coi 404 là operation ID không tồn tại.** 404 của last_operation biểu thị instance/binding không tồn tại. Phân biệt resource lookup và operation correlation.

**Xóa record ngay sau deprovision.** Platform còn poll và nhận 404. Giữ tombstone hoặc terminal operation record.

**Dùng 410 cho timeout.** 410 có thể khiến platform quên resource dù provider còn tồn tại. Chỉ dùng khi delete đã được xác nhận.

**Để last_operation đọc replica chậm.** Platform thấy state cũ. Đọc từ nguồn nhất quán hoặc kiểm soát replica lag/cache.

**Không lưu plan ID trước update.** Polling update đổi plan có thể lookup sai context. Lưu old plan và new plan trong operation record.

**Polling quá dày.** Gây tải database và broker. Dùng Retry-After và polling duration phù hợp.

**Retry provider trước khi reconcile.** Có thể tạo resource trùng hoặc xóa nhầm. Kiểm tra external operation trước.

**Không giữ terminal state.** Platform có thể poll lại nhưng broker không còn kết quả. Áp dụng retention và tombstone.

## 26. Nguyên tắc triển khai trong Spring Cloud Service Broker

Với Spring Cloud Open Service Broker, triển khai getLastOperation trong ServiceInstanceService nếu create/update/delete có thể bất đồng bộ; triển khai method tương ứng trong ServiceInstanceBindingService nếu create/delete binding có thể bất đồng bộ. Method này chỉ đọc trạng thái đã lưu và trả Mono response; không khởi chạy lại provider operation.

Trước khi trả 202, commit instance/binding state, operation token và outbox event. Worker claim operation bằng lease, gọi provider với idempotency key ổn định, lưu external reference và cập nhật heartbeat/progress. Các replica API phải dùng chung state store và đọc trạng thái mới nhất.

Khi platform poll, đối chiếu đúng instance ID, binding ID, service ID, plan ID và operation token. Trả 200 với state in progress, succeeded hoặc failed. Dùng 404 khi instance/binding thật sự không tồn tại; chỉ dùng 410 Gone cho asynchronous delete đã xác nhận resource gone. Giữ terminal record/tombstone đủ lâu để platform poll lại.

Khi operation vượt thời gian dự kiến, điều tra worker, queue, lease, provider và state store trước khi retry hoặc sửa dữ liệu. Phân biệt operation đang tiến triển với operation mất worker, và phân biệt operation token mismatch với resource not found. Một quy trình recovery có reconciliation, idempotency, audit và deadline rõ ràng sẽ giúp broker tránh tạo tài nguyên trùng, không làm mất operation và giữ trạng thái platform nhất quán với provider.

## Tài liệu tham khảo

- [Open Service Broker API Specification – Polling Last Operation for Service Instances and Bindings](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#polling-last-operation-for-service-instances)
- [Open Service Broker API Specification – Polling Interval and Duration](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#polling-interval-and-duration)
- [Open Service Broker API Specification – Synchronous and Asynchronous Operations](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#synchronous-and-asynchronous-operations)
- [Spring Cloud Open Service Broker Reference 4.4.1 – Service Instances](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/reference/#service-instances)
- [Spring Cloud Open Service Broker API – ServiceInstanceService](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/service/ServiceInstanceService.html)
- [Spring Cloud Open Service Broker API – ServiceInstanceBindingService](https://docs.spring.io/spring-cloud-open-service-broker/docs/4.4.1/apidocs/org/springframework/cloud/servicebroker/service/ServiceInstanceBindingService.html)

