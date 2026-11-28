# Bù trừ thao tác khi chuỗi cấp phát chỉ thành công một phần

Một yêu cầu provision của service broker có thể phải thực hiện nhiều bước ở các hệ thống khác nhau: giữ quota, tạo network, tạo database, cấu hình user, lưu credentials và kiểm tra khả năng kết nối. Những bước này không nằm trong cùng một transaction database. Vì vậy, một bước có thể thành công trong khi bước tiếp theo thất bại hoặc trả kết quả không xác định.

Trong module **SPRING_CLOUD_SERVICE_BROKER**, broker cần có cơ chế xử lý khi chuỗi cấp phát chỉ hoàn tất một phần. Nếu database đã được tạo nhưng việc cấp quyền thất bại, broker phải quyết định tiếp tục sửa lỗi, thử lại hay thu hồi database và các tài nguyên đã tạo. Cơ chế thường dùng là **compensating transaction** trong một quy trình Saga: mỗi bước có side effect được ghi nhận, và khi quy trình không thể tiếp tục, broker thực hiện hành động bù trừ tương ứng để đưa hệ thống về một trạng thái an toàn.

Bù trừ không phải rollback ACID xuyên nhiều nhà cung cấp. Nó là một quy trình nghiệp vụ độc lập, có thể thất bại, cần retry, idempotency, lưu trạng thái bền vững và reconciliation. Bài học này trình bày cách thiết kế quy trình đó cho service broker xây dựng bằng Spring Cloud, từ mô hình bước cấp phát đến mã điều phối, phục hồi và kiểm thử.

## 1. Vì sao chuỗi provision có thể chỉ thành công một phần?

Một service instance thường được tạo từ nhiều tài nguyên và thao tác phụ thuộc nhau. Ví dụ, để cung cấp một PostgreSQL instance, broker có thể cần:

1. Kiểm tra plan và quyền sử dụng.
2. Reserve quota của tenant.
3. Tạo network endpoint hoặc firewall rule.
4. Tạo database instance ở provider.
5. Tạo database và role dành cho ứng dụng.
6. Sinh credentials và lưu vào secret manager.
7. Cấu hình backup policy và monitoring.
8. Kiểm tra kết nối.
9. Ghi nhận instance là sẵn sàng và trả response cho nền tảng.

Mỗi bước có thể gọi một API riêng, có thời gian hoàn tất và cơ chế lỗi khác nhau. Database provider có thể tạo instance thành công, nhưng secret manager tạm thời không khả dụng. Network rule có thể đã được tạo, nhưng API tạo database trả lỗi quota. Một request có thể timeout sau khi provider đã thực hiện side effect nhưng trước khi broker nhận được response.

Nếu broker chỉ ghi một trạng thái tổng quát như FAILED, nó sẽ không biết tài nguyên nào đã tồn tại và cần xử lý gì. Nếu chỉ retry toàn bộ chuỗi từ đầu, broker có thể tạo trùng network, database hoặc credentials.

### Ví dụ về trạng thái cấp phát một phần

| Bước | Side effect | Kết quả |
|---|---|---|
| Reserve quota | Giữ 100 GB quota | Thành công |
| Create network rule | Tạo firewall rule | Thành công |
| Create database | Tạo database instance | Thành công |
| Create application role | Tạo database role | Thất bại do provider tạm lỗi |
| Store credentials | Lưu secret | Chưa thực hiện |
| Health check | Kiểm tra kết nối | Chưa thực hiện |

Tại thời điểm này, broker chưa thể trả provision thành công. Nhưng ba tài nguyên hoặc reservation đầu tiên đã tồn tại. Broker cần quyết định có thể retry bước tạo role hay phải bù trừ những side effect đã xảy ra.

Nếu lỗi chỉ là tạm thời và retry an toàn, tiếp tục forward recovery có thể tốt hơn xóa toàn bộ. Nếu lỗi cuối cùng khiến plan không thể được cấp phát, broker cần bù trừ theo dependency ngược: xóa database, xóa network rule và giải phóng quota sau khi xác nhận từng bước.

## 2. Phân biệt rollback database và compensating transaction

Rollback ACID đưa các thay đổi trong một transaction database về trạng thái trước khi commit. Cơ sở dữ liệu quản lý tính nguyên tử, consistency, isolation và durability trong phạm vi transaction đó.

Provision service broker thường trải qua nhiều hệ thống độc lập. Transaction database của broker không thể tự rollback một database đã tạo ở cloud provider, một firewall rule đã áp dụng hoặc một secret đã ghi vào hệ thống quản lý khóa.

**Compensating transaction** là hành động nghiệp vụ nhằm đảo ngược hoặc giảm tác động của một bước đã hoàn tất. Ví dụ:

| Bước thuận (forward action) | Hành động bù trừ (compensation) |
|---|---|
| Reserve quota | Release quota reservation |
| Create firewall rule | Delete firewall rule |
| Create database instance | Delete database instance |
| Create database role | Revoke/drop role |
| Create secret | Revoke hoặc destroy secret |
| Register DNS record | Remove DNS record nếu record do operation tạo |
| Create backup snapshot | Delete snapshot nếu policy cho phép |
| Attach volume | Detach volume và xóa volume nếu thuộc quyền sở hữu operation |

Bù trừ không phải lúc nào cũng khôi phục chính xác trạng thái ban đầu. Ví dụ, một notification đã gửi không thể thu hồi khỏi hộp thư người nhận. Một lần sử dụng quota theo thời gian hoặc chi phí provider đã phát sinh có thể không được hoàn lại. Một migration dữ liệu có thể không đảo ngược an toàn.

Do đó, cần xác định rõ bước nào có thể bù trừ, bước nào phải forward-retry, bước nào cần thao tác thủ công và bước nào không thể hoàn tác.

### Compensation là nghiệp vụ riêng

Một lệnh delete có thể thất bại hoặc timeout. Provider có thể yêu cầu thời gian để xóa resource. Một số tài nguyên cần xử lý theo thứ tự. Vì vậy, compensation phải có:

- Định danh riêng cho từng hành động bù trừ.
- Trạng thái và số lần thử.
- Idempotency key ổn định.
- Thông tin tài nguyên đích và quyền sở hữu.
- Chính sách retry và thời hạn xử lý.
- Audit trail và cảnh báo khi không thể hoàn tất.

Không được coi việc gọi API delete là đồng nghĩa với việc bù trừ đã thành công. Chỉ đánh dấu hoàn tất khi provider xác nhận trạng thái cuối cùng hoặc broker có bằng chứng đủ tin cậy theo hợp đồng provider.

## 3. Saga cho quy trình provision nhiều bước

Saga chia một quy trình phân tán thành nhiều bước cục bộ. Mỗi bước thực hiện một side effect và có thể có hành động bù trừ tương ứng. Nếu một bước thất bại, Saga quyết định retry, chuyển sang nhánh phục hồi hoặc chạy compensation theo thứ tự phụ thuộc.

Một Saga provision đơn giản:

~~~mermaid
flowchart TD
    Start["Provision request"] --> Reserve["Reserve quota"]
    Reserve --> Network["Create network rule"]
    Network --> Database["Create database"]
    Database --> Role["Create application role"]
    Role --> Secret["Store credentials"]
    Secret --> Health["Health check"]
    Health --> Success["Mark instance SUCCEEDED"]
    Role -. "Permanent failure" .-> Compensate["Start compensation"]
    Secret -. "Permanent failure" .-> Compensate
    Health -. "Permanent failure" .-> Compensate
    Compensate --> RevokeRole["Revoke role if created"]
    RevokeRole --> DeleteDB["Delete database"]
    DeleteDB --> DeleteNetwork["Delete network rule"]
    DeleteNetwork --> ReleaseQuota["Release quota"]
    ReleaseQuota --> Failed["Mark provision FAILED"]
~~~

Trong thực tế, Saga cần lưu tiến độ sau từng bước. Nếu broker restart, worker phải biết bước nào đã hoàn tất và bước nào đang chạy. Không thể chỉ giữ danh sách kết quả trong bộ nhớ.

Có hai cách tổ chức Saga phổ biến:

**Orchestration**: một coordinator lưu workflow state và quyết định bước tiếp theo. Cách này phù hợp với broker vì broker cần điều phối quota, provider resource, secret và operation.

**Choreography**: các thành phần phát và nhận event để kích hoạt bước kế tiếp. Cách này hữu ích khi các dịch vụ độc lập phối hợp qua event, nhưng luồng bù trừ phức tạp hơn nếu không có một nơi theo dõi toàn bộ operation.

Với một service broker quản lý vòng đời instance, orchestration thường giúp dễ quan sát và đối soát hơn. Có thể dùng message queue để thực thi từng bước nhưng vẫn giữ Saga coordinator làm nguồn trạng thái.

## 4. Thiết kế danh sách bước và hành động bù trừ

Trước khi viết code, cần mô tả mỗi bước với side effect, dữ liệu kết quả và hành động bù trừ.

| Step | Forward action | Kết quả cần lưu | Compensation |
|---|---|---|---|
| QUOTA | Reserve quota | reservation ID, amount | Release reservation |
| NETWORK | Create network rule | provider rule ID | Delete rule |
| DATABASE | Create database | provider resource ID | Delete database |
| ROLE | Create application role | provider binding/user ID | Revoke role |
| SECRET | Store credentials | secret reference | Destroy/revoke secret |
| BACKUP_POLICY | Apply backup policy | policy reference | Restore prior policy hoặc detach |
| HEALTH_CHECK | Verify connectivity | check result | Thường không cần compensation |

Không phải bước nào cũng có compensation. Health check chỉ quan sát nên không tạo side effect. Một số cấu hình có thể được giữ lại nếu chúng được chia sẻ bởi nhiều instance hoặc đã tồn tại trước operation.

### Mỗi bước cần lưu gì?

Một bản ghi Saga step có thể gồm:

| Thuộc tính | Ý nghĩa |
|---|---|
| operationId | Provision operation sở hữu bước |
| stepKey | Định danh ổn định của bước |
| stepType | Loại thao tác |
| sequence | Thứ tự trong workflow |
| state | PENDING, RUNNING, SUCCEEDED, FAILED, UNKNOWN, COMPENSATING, COMPENSATED |
| idempotencyKey | Khóa ổn định gửi tới provider |
| externalResourceId | ID tài nguyên ở provider |
| ownershipReference | External reference chứng minh tài nguyên thuộc operation |
| attemptCount | Số lần thử |
| startedAt, completedAt | Thời gian thực hiện |
| errorCode | Mã lỗi đã làm sạch |
| compensationState | Trạng thái bù trừ riêng |

Lưu dữ liệu kết quả ngay khi đã xác định side effect thành công. Nếu broker dừng sau khi provider tạo resource nhưng trước khi ghi externalResourceId, broker phải có cách tìm lại tài nguyên bằng idempotency key hoặc external reference.

### Không bù trừ tài nguyên không thuộc operation

Một provider resource có thể đã tồn tại trước request hoặc được chia sẻ bởi nhiều instance. Broker chỉ được xóa tài nguyên mà operation có quyền sở hữu.

Hãy gắn metadata ổn định cho resource nếu provider hỗ trợ, ví dụ broker_instance_id, broker_operation_id và step_key. Trước khi xóa, adapter kiểm tra ownership reference và trạng thái hiện tại. Không xóa một network rule hoặc database chỉ vì tên của nó giống tên được suy ra từ instance ID.

## 5. Phân loại lỗi trước khi quyết định compensation

Không phải mọi lỗi đều cần bù trừ ngay. Broker cần phân biệt lỗi tạm thời, lỗi cuối cùng và kết quả chưa xác định.

| Nhóm lỗi | Ví dụ | Hướng xử lý |
|---|---|---|
| Lỗi validation | Plan không hợp lệ, parameters sai schema | Không bắt đầu side effect; từ chối request |
| Lỗi tạm thời | HTTP 429, provider 503, network transient | Retry bước hiện tại với backoff |
| Lỗi cuối cùng | Region không hỗ trợ loại resource, policy từ chối | Dừng forward flow và compensation các bước đã thành công |
| Xung đột | Resource ID đã được dùng bởi request khác | Reconcile ownership; không xóa tài nguyên không thuộc operation |
| Timeout, kết quả chưa rõ | Provider có thể đã tạo resource nhưng response bị mất | Tra cứu provider trước khi retry hoặc bù trừ |
| Lỗi nội bộ | Database không ghi được kết quả, secret store unavailable | Phục hồi trạng thái; không giả định side effect chưa xảy ra |

### Timeout không đồng nghĩa với thất bại

Giả sử broker gọi provider tạo database. Provider tạo thành công nhưng response bị mất do network timeout. Broker không biết database đã tồn tại hay chưa.

Nếu broker đánh dấu step FAILED rồi gọi create lần nữa, có thể tạo database thứ hai. Nếu broker chạy compensation mà chưa xác định resource ID, có thể bỏ sót tài nguyên hoặc xóa nhầm.

Trạng thái đúng ở thời điểm đó là UNKNOWN hoặc RECONCILIATION_REQUIRED. Broker tra cứu theo external reference hoặc idempotency key:

- Nếu resource đã tồn tại và thuộc operation, ghi nhận step SUCCEEDED rồi tiếp tục.
- Nếu provider xác nhận resource chưa được tạo, retry forward action bằng cùng idempotency key.
- Nếu không thể xác định, giữ operation trong trạng thái cần đối soát và cảnh báo vận hành.

Không đưa một kết quả chưa xác định vào nhánh compensation cho đến khi biết side effect nào thực sự đã xảy ra.

## 6. Thứ tự bù trừ theo dependency

Compensation thường chạy theo thứ tự ngược với các bước forward, nhưng phải dựa trên dependency thực tế chứ không chỉ đảo số thứ tự một cách máy móc.

Ví dụ, database role phụ thuộc database instance; database instance phụ thuộc network rule; network rule được giữ bằng quota reservation. Vì vậy, thứ tự thu hồi hợp lý là:

1. Revoke role hoặc quyền truy cập đã tạo.
2. Xóa secret gắn với role sau khi đã thu hồi quyền và không cần secret cho reconciliation.
3. Xóa database instance.
4. Xóa network rule nếu chỉ operation này sở hữu.
5. Release quota reservation.

Nếu xóa database trước khi revoke role, provider có thể vẫn giữ user hoặc credential không cần thiết. Nếu release quota trước khi resource được xác nhận xóa, broker có thể cấp phần quota đó cho instance khác trong khi resource cũ vẫn tiêu thụ capacity.

### Dependency graph

~~~mermaid
flowchart BT
    Quota["Quota reservation"]
    Network["Network rule"]
    Database["Database instance"]
    Role["Application role"]
    Secret["Credential secret"]
    Quota --> Network
    Network --> Database
    Database --> Role
    Role --> Secret
~~~

Sơ đồ thể hiện dependency theo hướng resource phụ thuộc resource nền. Khi bù trừ, bắt đầu từ các node phụ thuộc (secret/role), sau đó đi về tài nguyên nền (database, network, quota).

Nếu các bước độc lập, có thể chạy compensation song song. Ví dụ, hai secret độc lập thuộc cùng operation có thể được revoke đồng thời. Nhưng chỉ làm vậy khi không có dependency và provider rate limit cho phép. Với các tài nguyên có quan hệ phụ thuộc, giữ thứ tự để tránh để lại orphan hoặc làm mất thông tin cần thiết.

### Compensation không nhất thiết là reverse tuyệt đối

Một số forward action có thể cần hành động bù trừ khác về ngữ nghĩa:

- Tạo backup có thể được giữ theo retention thay vì xóa ngay.
- Gửi notification không thể thu hồi; có thể cần gửi thông báo sửa sai.
- Ghi audit event không nên bị xóa; nó cần phản ánh cả hành động thuận và bù trừ.
- Tăng quota usage có thể phải ghi nhận chi phí đã phát sinh dù reservation được giải phóng.
- Chạy migration dữ liệu có thể cần restore từ snapshot hoặc forward-fix thay vì reverse migration.

Hãy mô tả rõ compensation policy cho từng step. Không tự động suy ra hành động bù trừ chỉ bằng cách đổi tên API create thành delete.

## 7. State machine cho provision và compensation

Operation cần biểu diễn riêng tiến độ forward và compensation. Một state machine nội bộ có thể gồm:

~~~mermaid
stateDiagram-v2
    [*] --> ACCEPTED
    ACCEPTED --> PROVISIONING
    PROVISIONING --> SUCCEEDED
    PROVISIONING --> RETRY_WAIT
    RETRY_WAIT --> PROVISIONING
    PROVISIONING --> COMPENSATING
    COMPENSATING --> COMPENSATION_RETRY
    COMPENSATION_RETRY --> COMPENSATING
    COMPENSATING --> COMPENSATED
    COMPENSATING --> COMPENSATION_BLOCKED
    COMPENSATION_BLOCKED --> COMPENSATING
    COMPENSATED --> FAILED
    SUCCEEDED --> [*]
    FAILED --> [*]
~~~

Ý nghĩa các trạng thái:

- **ACCEPTED**: request đã được xác thực và ghi nhận.
- **PROVISIONING**: các bước cấp phát đang chạy.
- **RETRY_WAIT**: một bước gặp lỗi tạm thời và chờ retry.
- **COMPENSATING**: broker đang thu hồi side effect đã tạo.
- **COMPENSATION_RETRY**: một hành động bù trừ cần thử lại.
- **COMPENSATION_BLOCKED**: cần điều kiện bên ngoài hoặc can thiệp vận hành.
- **COMPENSATED**: các hành động bù trừ bắt buộc đã hoàn tất.
- **FAILED**: provision không thành công; kết quả và cleanup đã được ghi nhận theo policy.

Tên trạng thái trên là mô hình nội bộ, không phải enum chuẩn OSB API.

Cần lưu riêng provisionOutcome và cleanupOutcome hoặc các trạng thái tương đương. Provision thất bại không có nghĩa cleanup đã xong. Một operation có thể có kết quả FAILED nhưng vẫn còn cleanup task đang chờ xử lý. Broker không được xóa record operation chỉ vì đã trả lỗi cho nền tảng.

## 8. Ánh xạ compensation với Open Service Broker API

Với OSB API, provision có thể được xử lý đồng bộ hoặc bất đồng bộ tùy khả năng broker và query parameter accepts_incomplete của client.

Nếu client chấp nhận async, broker có thể trả response async và operation ID, sau đó nền tảng truy vấn last operation. Trong thời gian provision hoặc compensation đang chạy, broker cần phản ánh operation là đang xử lý theo hợp đồng. Khi provision không thể hoàn tất và compensation đã hoàn thành hoặc được chuyển sang trạng thái xử lý lỗi có kiểm soát, last operation có thể báo trạng thái failed cùng mô tả an toàn.

Nếu client không chấp nhận async mà broker không thể hoàn tất đồng bộ, broker phải trả lỗi theo hợp đồng OSB API, chẳng hạn AsyncRequired khi phù hợp. Không trả provision thành công chỉ vì đã đưa công việc vào queue.

Một điểm quan trọng: compensation là workflow nội bộ để làm sạch side effect của provision. Nó không phải một thao tác OSB riêng mà nền tảng phải gọi. Broker vẫn chịu trách nhiệm quản lý operation provision và trả trạng thái cuối cùng nhất quán.

### Không báo failed quá sớm nếu cleanup còn đang được điều phối

Nếu broker báo provision failed trong khi vẫn đang tự động thu hồi tài nguyên, nền tảng có thể coi request đã kết thúc và không tiếp tục polling. Tùy cách triển khai, broker có thể giữ operation ở trạng thái in progress trong thời gian compensation tự động có giới hạn.

Nếu cleanup vượt deadline hoặc cần người vận hành, broker cần:
- Ghi nhận provision outcome là failed.
- Lưu cleanup task riêng ở trạng thái blocked/needs-attention.
- Trả kết quả operation theo hợp đồng với error description phù hợp.
- Phát cảnh báo và tiếp tục reconciliation/cleanup nội bộ.
- Giữ metadata đủ để không tạo trùng hoặc bỏ quên tài nguyên.

Không nên giữ last operation ở trạng thái in progress vô thời hạn. Cần có deadline, retry budget và quy trình chuyển sang hàng đợi xử lý lỗi.

## 9. Durable workflow: ghi trạng thái trước và sau side effect

Broker có thể dừng ở bất kỳ thời điểm nào: trước khi gọi provider, sau khi provider thành công, trước khi lưu kết quả hoặc trong lúc compensation. Do đó, workflow phải có trạng thái bền vững.

Một bảng operation có thể lưu:

~~~sql
CREATE TABLE broker_operation (
    operation_id       VARCHAR(255) PRIMARY KEY,
    instance_id        VARCHAR(255) NOT NULL,
    operation_type     VARCHAR(32) NOT NULL,
    state              VARCHAR(32) NOT NULL,
    current_step       VARCHAR(128),
    provision_outcome  VARCHAR(32),
    cleanup_outcome    VARCHAR(32),
    started_at         TIMESTAMP NOT NULL,
    updated_at         TIMESTAMP NOT NULL
);
~~~

Bảng step:

~~~sql
CREATE TABLE broker_operation_step (
    operation_id          VARCHAR(255) NOT NULL,
    step_key              VARCHAR(128) NOT NULL,
    sequence_no           INTEGER NOT NULL,
    step_type             VARCHAR(64) NOT NULL,
    state                 VARCHAR(32) NOT NULL,
    idempotency_key       VARCHAR(255) NOT NULL,
    external_resource_id  VARCHAR(512),
    ownership_reference   VARCHAR(512),
    attempt_count         INTEGER NOT NULL DEFAULT 0,
    error_code            VARCHAR(128),
    started_at            TIMESTAMP,
    completed_at          TIMESTAMP,
    PRIMARY KEY (operation_id, step_key)
);
~~~

Bảng compensation:

~~~sql
CREATE TABLE broker_compensation (
    operation_id          VARCHAR(255) NOT NULL,
    step_key              VARCHAR(128) NOT NULL,
    compensation_key      VARCHAR(255) NOT NULL,
    state                 VARCHAR(32) NOT NULL,
    attempt_count         INTEGER NOT NULL DEFAULT 0,
    next_attempt_at       TIMESTAMP,
    last_error_code       VARCHAR(128),
    completed_at           TIMESTAMP,
    PRIMARY KEY (operation_id, step_key)
);
~~~

Đây là schema minh họa. Cần điều chỉnh kiểu dữ liệu, index, foreign key và constraint theo database. Nếu dùng bảng outbox riêng, event cần được ghi trong cùng transaction với operation hoặc step transition tương ứng.

### Ghi nhận trước và sau mỗi bước

Một bước có side effect nên tuân theo quy trình:

1. Trong transaction ngắn, đánh dấu step RUNNING và lưu idempotency key.
2. Commit transaction.
3. Gọi provider bên ngoài database transaction.
4. Xác định kết quả bằng response hoặc reconciliation.
5. Trong transaction mới, lưu external resource ID và đánh dấu SUCCEEDED.
6. Chỉ sau đó cho phép bước phụ thuộc tiếp theo chạy.

Nếu tiến trình dừng giữa bước 3 và 5, worker phục hồi thấy step RUNNING quá lâu. Nó không được mù quáng gọi lại. Trước tiên cần tra cứu provider theo idempotency key hoặc ownership reference.

## 10. Idempotency cho cả forward action và compensation

Idempotency không chỉ cần ở request provision. Hành động bù trừ cũng có thể được retry nhiều lần vì worker restart, message redelivery hoặc provider timeout.

Ví dụ, broker gọi xóa database nhưng timeout. Worker không biết database đã bị xóa hay chưa. Lần sau, nó phải có thể gửi lại cùng lệnh xóa mà không tạo side effect nguy hiểm hoặc báo lỗi giả.

Một compensation key có thể được tạo ổn định từ operation ID và step key:

~~~text
compensation_key = operation_id + ":" + step_key + ":compensate"
~~~

Không tạo key mới cho mỗi lần retry. Provider adapter nên gửi key này nếu provider hỗ trợ idempotency.

Quy tắc xử lý:

| Trạng thái compensation | Khi worker retry |
|---|---|
| Chưa tạo | Reserve compensation record và bắt đầu |
| RUNNING | Kiểm tra lease; không chạy song song cùng hành động |
| SUCCEEDED | Bỏ qua, không lặp side effect |
| FAILED_TRANSIENT | Retry theo backoff và cùng key |
| UNKNOWN | Tra cứu provider trước khi gửi lại |
| BLOCKED | Chờ điều kiện hoặc can thiệp đã định nghĩa |
| PERMANENT_FAILURE | Chuyển cảnh báo/manual repair theo policy |

### Compensation phải kiểm tra ownership

Trước khi xóa resource, adapter xác minh external resource ID và ownership reference thuộc đúng operation hoặc instance. Nếu resource không tồn tại, hành động delete có thể được xem là đã hoàn tất theo ngữ nghĩa idempotent. Nếu resource tồn tại nhưng thuộc operation khác, dừng và báo conflict; tuyệt đối không xóa.

Với quota reservation, release phải gắn đúng reservation ID. Không giảm quota tổng bằng một phép trừ không có định danh, vì retry có thể giải phóng cùng quota hai lần.

Với secret, revoke/destroy cần kiểm tra secret reference và binding/instance ownership. Không xóa secret chỉ dựa trên tên có thể trùng.

## 11. Retry, backoff và giới hạn xử lý

Retry giúp xử lý lỗi tạm thời, nhưng retry vô hạn có thể làm tăng tải provider và khiến operation không bao giờ kết thúc.

Một policy retry thường có:

- Số lần thử tối đa.
- Exponential backoff.
- Jitter để tránh nhiều worker retry cùng lúc.
- Phân loại lỗi retryable và non-retryable.
- Timeout cho từng lần gọi.
- Deadline tổng của operation.
- Circuit breaker hoặc rate limit khi provider gặp sự cố.
- Dead-letter hoặc hàng đợi manual repair khi vượt retry budget.

Ví dụ khoảng chờ tăng dần:

~~~text
attempt 1: 1 second
attempt 2: 2 seconds
attempt 3: 4 seconds
attempt 4: 8 seconds
...
~~~

Đây là ví dụ, cần thêm jitter và giới hạn tối đa trong hệ thống thật.

Forward retry và compensation retry có thể có policy khác nhau. Provision có thể cần thời gian chờ provider capacity; compensation xóa tài nguyên có thể cần ưu tiên cao hơn để tránh chi phí tiếp tục phát sinh. Tuy nhiên, không retry liên tục một lỗi permanent như quyền bị thu hồi hoặc resource ID không hợp lệ.

Nếu compensation không hoàn tất sau retry budget, chuyển sang trạng thái NEEDS_MANUAL_REPAIR hoặc COMPENSATION_BLOCKED. Tạo alert chứa operation ID, step key, resource reference và mã lỗi đã làm sạch. Không đưa credentials hoặc dữ liệu nhạy cảm vào alert.

## 12. Transactional Outbox và worker phục hồi

Nếu broker dùng message queue để chạy provision hoặc compensation, cần bảo đảm operation state và event được ghi nhất quán.

Transactional outbox ghi event trong cùng transaction với thay đổi database:

~~~sql
CREATE TABLE broker_outbox (
    event_id       VARCHAR(255) PRIMARY KEY,
    operation_id   VARCHAR(255) NOT NULL,
    step_key       VARCHAR(128),
    event_type     VARCHAR(128) NOT NULL,
    payload        TEXT NOT NULL,
    created_at     TIMESTAMP NOT NULL,
    published_at   TIMESTAMP
);
~~~

Ví dụ:
- PROVISION_STEP_REQUESTED
- COMPENSATION_REQUESTED
- COMPENSATION_RETRY_SCHEDULED
- OPERATION_RECONCILIATION_REQUESTED

Publisher có thể gửi event nhiều lần nếu mất xác nhận. Worker cần idempotent theo event ID, operation ID và step key.

Một worker xử lý compensation:

1. Đọc event và claim compensation record bằng lease.
2. Kiểm tra step forward đã thành công hoặc resource đã được xác nhận tồn tại.
3. Kiểm tra dependency: các bước phụ thuộc đã được thu hồi trước chưa.
4. Gọi provider adapter với compensation key ổn định.
5. Tra cứu trạng thái nếu kết quả timeout.
6. Cập nhật compensation record và step state.
7. Tạo event cho compensation kế tiếp nếu dependency cho phép.
8. Khi tất cả compensation bắt buộc hoàn tất, cập nhật cleanup outcome.

Không để worker phụ thuộc vào trạng thái trong bộ nhớ của node đã nhận request ban đầu. Mọi dữ liệu cần để tiếp tục phải được lưu trong database hoặc kho workflow bền vững.

## 13. Ví dụ điều phối Saga trong Spring

Các interface dưới đây là abstraction nội bộ của ứng dụng, không phải class được Spring Cloud Open Service Broker cung cấp sẵn.

Một mô hình step:

~~~java
public record ProvisionStep(
    String key,
    int sequence,
    String action,
    String compensationAction
) {}

public record StepResult(
    String externalResourceId,
    String ownershipReference
) {}
~~~

Provider adapter có thể định nghĩa thao tác thuận và bù trừ:

~~~java
public interface ProvisioningResourceAdapter {

    Mono<StepResult> execute(
        ProvisionCommand command,
        String idempotencyKey);

    Mono<Void> compensate(
        StepResult result,
        String compensationKey);

    Mono<Optional<StepResult>> findByOwnershipReference(
        String ownershipReference);
}
~~~

Một coordinator minh họa:

~~~java
@Service
public class ProvisioningSagaCoordinator {

    private final OperationStore operations;
    private final StepStore steps;
    private final ProvisioningResourceAdapter adapter;
    private final CompensationScheduler compensationScheduler;

    public ProvisioningSagaCoordinator(
            OperationStore operations,
            StepStore steps,
            ProvisioningResourceAdapter adapter,
            CompensationScheduler compensationScheduler) {
        this.operations = operations;
        this.steps = steps;
        this.adapter = adapter;
        this.compensationScheduler = compensationScheduler;
    }

    public Mono<ProvisionResult> start(
            ProvisionCommand command) {

        return operations.reserve(command)
            .flatMap(operation ->
                executeNext(operation, command)
                    .onErrorResume(error ->
                        beginCompensation(operation, error)
                            .then(Mono.error(error))
                    )
            );
    }

    private Mono<ProvisionResult> executeNext(
            BrokerOperation operation,
            ProvisionCommand command) {
        // Load the next durable step, execute with a stable key,
        // persist the provider result, then continue.
        return Mono.error(new UnsupportedOperationException(
            "Illustrative workflow skeleton"));
    }

    private Mono<Void> beginCompensation(
            BrokerOperation operation,
            Throwable cause) {
        return operations.markCompensating(
                operation.operationId(),
                safeFailureCode(cause))
            .then(compensationScheduler.enqueue(
                operation.operationId()));
    }
}
~~~

Đây là skeleton để minh họa ranh giới. Trong triển khai thật, executeNext phải đọc step chưa hoàn tất từ kho bền vững, claim bằng lease, gọi adapter, lưu kết quả và tiếp tục theo dependency. Không nên triển khai Saga bằng một danh sách Mono trong bộ nhớ rồi kỳ vọng chuỗi đó sống qua restart.

### Handler OSB chỉ điều phối hợp đồng

ServiceInstanceService nhận CreateServiceInstanceRequest, kiểm tra request và gọi coordinator. Nếu thao tác hoàn tất đồng bộ, handler trả CreateServiceInstanceResponse thành công. Nếu client chấp nhận async, broker có thể trả operation ID để nền tảng poll last operation trong khi Saga chạy.

Không gọi subscribe() tùy tiện trong handler reactive. Trả Mono cho framework quản lý. Với async workflow, ghi operation và outbox bền vững rồi để worker tiếp tục.

## 14. Khi nào nên retry forward thay vì bù trừ?

Một lỗi tạm thời không nhất thiết yêu cầu hủy mọi tài nguyên đã tạo.

Ví dụ database đã tạo, nhưng secret manager đang bảo trì trong vài phút. Nếu provider resource vẫn an toàn và quota được giữ hợp lệ, broker có thể giữ instance ở PROVISIONING và retry lưu secret. Điều này tránh xóa rồi tạo lại database không cần thiết.

Có thể quyết định theo ma trận:

| Điều kiện | Hướng xử lý |
|---|---|
| Lỗi tạm thời, bước có thể retry idempotent | Retry forward step |
| Provider trả operation đang chạy | Tiếp tục poll hoặc chờ callback |
| Kết quả provider chưa xác định | Reconcile trước khi quyết định |
| Lỗi permanent, resource có thể thu hồi | Bắt đầu compensation |
| Lỗi permanent, side effect không thể đảo ngược | Forward recovery hoặc manual repair |
| Policy/permission thay đổi làm operation không còn được phép | Dừng forward flow, đánh giá compensation an toàn |
| Compensation có nguy cơ gây mất dữ liệu lớn hơn | Chuyển manual review theo policy |

Một số lỗi nên dùng **forward recovery**: sửa cấu hình hoặc retry bước còn thiếu để đưa quy trình đến trạng thái hoàn tất. Ví dụ, provider đã tạo database nhưng tạo role thất bại do một policy tạm thời bị cấu hình sai. Nếu policy có thể sửa an toàn, tiếp tục tạo role có thể tốt hơn xóa database và bắt đầu lại.

Quyết định cần dựa trên service contract, chi phí, dữ liệu đã tạo và khả năng bù trừ. Không mặc định mọi lỗi đều phải rollback.

## 15. Compensation thất bại và manual repair

Compensation có thể thất bại vì provider không khả dụng, quyền xóa bị thu hồi, resource bị khóa hoặc API provider thay đổi. Broker phải có quy trình cho tình huống này.

Một bản ghi manual repair nên chứa:

- operation ID và instance ID.
- Step forward đã thành công.
- Compensation action đang thất bại.
- External resource ID và ownership reference.
- Số lần retry, thời điểm thử gần nhất và lỗi đã làm sạch.
- Bằng chứng reconciliation gần nhất.
- Hành động được đề xuất và quyền cần thiết.
- Người hoặc nhóm chịu trách nhiệm.
- Trạng thái xử lý và audit trail.

Không đưa password, access token hoặc dữ liệu người dùng vào ticket. Cung cấp đủ định danh để người vận hành tra cứu trong hệ thống có quyền.

Khi manual repair hoàn tất, cập nhật compensation state và cleanup outcome trong broker. Không chỉ sửa trực tiếp provider rồi bỏ quên operation record; nếu không, worker reconciliation có thể tiếp tục xóa hoặc retry sai.

### Tài nguyên mồ côi (orphan resource)

Một orphan resource là tài nguyên provider còn tồn tại nhưng broker không có trạng thái tương ứng hoặc operation đã kết thúc mà chưa thu hồi được resource.

Có thể phát hiện bằng:
- Tag hoặc external reference gắn broker instance/operation ID.
- Danh sách resource provider theo project/account.
- Đối chiếu provider resource ID trong database broker.
- Operation có step UNKNOWN hoặc compensation chưa hoàn tất.
- Resource vượt quá thời gian tồn tại dự kiến mà không có instance ACTIVE.

Không tự động xóa mọi resource không tìm thấy trong database broker. Có thể resource thuộc hệ thống khác hoặc metadata broker bị restore từ backup cũ. Cần xác minh ownership và policy trước khi xóa.

## 16. Quan sát, audit và cảnh báo

Một Saga nhiều bước cần khả năng quan sát xuyên suốt. Mỗi log hoặc trace nên gắn các định danh:

- broker instance ID.
- operation ID.
- step key.
- compensation key.
- provider request/operation ID.
- correlation ID.
- attempt number.
- state transition.

Metric hữu ích:

| Metric | Ý nghĩa |
|---|---|
| provision_step_duration | Thời gian thực hiện từng bước |
| provision_partial_failure_total | Số operation thất bại sau một phần side effect |
| compensation_pending | Số compensation đang chờ |
| compensation_failure_total | Số lần compensation thất bại |
| compensation_age_seconds | Tuổi của compensation chưa hoàn tất |
| orphan_resource_count | Số tài nguyên cần reconciliation |
| operation_unknown_total | Số operation có kết quả provider chưa xác định |
| manual_repair_open | Số trường hợp cần người vận hành |

Không đặt instance ID, binding ID hoặc tenant ID có cardinality rất cao vào metric label nếu hệ thống metrics không hỗ trợ tốt. Các định danh chi tiết nên nằm trong log hoặc trace có kiểm soát.

Audit phải ghi cả forward action và compensation. Không xóa event cấp phát chỉ vì đã bù trừ; lịch sử cần cho biết tài nguyên từng được tạo và sau đó bị thu hồi như thế nào.

## 17. Kiểm thử chuỗi cấp phát thành công một phần

Kiểm thử cần mô phỏng lỗi tại từng điểm sau khi một hoặc nhiều side effect đã thành công.

| Tình huống | Kết quả cần xác nhận |
|---|---|
| Bước đầu thất bại trước side effect | Không chạy compensation không cần thiết |
| Database tạo thành công, role thất bại permanent | Revoke/xóa các resource đã tạo theo thứ tự |
| Secret store timeout | Reconcile secret trước khi retry hoặc compensation |
| Provider create timeout nhưng resource đã tồn tại | Tìm resource theo ownership reference, không tạo trùng |
| Delete compensation timeout | Giữ UNKNOWN và reconcile trước khi gọi lại |
| Worker restart khi COMPENSATING | Tiếp tục từ compensation record bền vững |
| Event outbox được gửi hai lần | Không chạy side effect bù trừ hai lần |
| Release quota được retry | Reservation chỉ được giải phóng một lần |
| Resource không thuộc operation | Không xóa, chuyển conflict/manual review |
| Hai compensation độc lập | Có thể chạy song song nếu dependency cho phép |
| Compensation phụ thuộc | Thực hiện đúng thứ tự dependency |
| Một compensation permanent failure | Đánh dấu blocked, cảnh báo và giữ dữ liệu phục hồi |
| Forward retry thành công | Không chạy compensation |
| Operation vượt deadline | Chuyển cleanup sang workflow repair có thể theo dõi |

Nên dùng provider test double có khả năng cấu hình lỗi ở từng bước, timeout trước/sau side effect và trả kết quả không xác định. Với integration test, kiểm tra trạng thái database, số resource provider còn tồn tại, reservation quota, secret store và operation history.

Đừng chỉ kiểm tra cuối cùng instance có state FAILED. Cần xác nhận mọi side effect đã được xử lý đúng hoặc được ghi rõ là cleanup còn tồn đọng.

## 18. Những lỗi thường gặp

**Coi compensation là rollback ACID.** Provider API nằm ngoài transaction database. Hành động bù trừ là workflow riêng, có thể thất bại và cần retry.

**Retry toàn bộ chuỗi từ đầu.** Những bước đã thành công có thể tạo tài nguyên trùng lặp. Lưu trạng thái từng step và tiếp tục từ bước chưa hoàn tất.

**Bù trừ ngay sau timeout.** Provider có thể đã thực hiện side effect. Đánh dấu UNKNOWN và reconcile trước khi xóa hoặc tạo lại.

**Xóa theo tên suy đoán.** Có thể xóa tài nguyên không thuộc operation. Lưu external resource ID và ownership reference.

**Chạy compensation theo thứ tự tùy ý.** Xóa tài nguyên nền trước khi thu hồi tài nguyên phụ có thể để lại orphan. Dựa vào dependency graph.

**Không làm compensation idempotent.** Worker retry có thể release quota hai lần hoặc xóa nhầm tài nguyên mới. Dùng compensation key ổn định và lưu kết quả từng bước.

**Đánh dấu FAILED rồi xóa operation record.** Cleanup có thể chưa xong. Giữ operation, compensation record và tombstone theo retention.

**Giữ workflow trong bộ nhớ.** Restart sẽ làm mất bước tiếp theo. Lưu step state và outbox bền vững.

**Báo success khi mới đưa vào queue.** Provision chỉ thành công khi mọi điều kiện hoàn tất theo hợp đồng; response async phải được thể hiện đúng OSB API.

**Không có manual repair path.** Một số provider error không thể tự khắc phục. Cần cảnh báo, quyền xử lý và audit thay vì retry vô hạn.

## 19. Nguyên tắc triển khai trong Spring Cloud Service Broker

Với Spring Cloud Open Service Broker, hãy để ServiceInstanceService tiếp nhận request OSB và giao phần điều phối nhiều bước cho một Saga coordinator. Mỗi bước cấp phát phải có step key ổn định, idempotency key, kết quả provider và hành động bù trừ được định nghĩa trước. Lưu operation, step và compensation record trong kho dữ liệu bền vững; dùng transaction ngắn và outbox để chuyển việc cho worker.

Khi một bước thất bại, phân loại lỗi trước: retry forward nếu lỗi tạm thời, reconcile nếu kết quả chưa rõ, hoặc bắt đầu compensation khi không thể tiếp tục. Compensation chạy theo dependency ngược, kiểm tra ownership và dùng key ổn định để retry an toàn. Nếu bù trừ không hoàn tất trong retry budget, chuyển sang manual repair nhưng vẫn giữ cleanup task và bằng chứng cần thiết.

Broker chỉ báo provision thành công sau khi chuỗi cấp phát đạt trạng thái sẵn sàng theo hợp đồng. Nếu provision thất bại, operation cần phản ánh đúng kết quả và cleanup phải tiếp tục được theo dõi cho đến khi hoàn tất hoặc được bàn giao có kiểm soát. Cách thiết kế này giúp service broker tránh tài nguyên mồ côi, hạn chế tạo trùng và phục hồi được khi provider hoặc broker gặp sự cố giữa một quy trình cấp phát nhiều bước.

