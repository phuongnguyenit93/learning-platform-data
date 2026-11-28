# Tính lặp an toàn cho cấp phát, tạo binding và thu hồi

Trong module **SPRING_CLOUD_SERVICE_BROKER**, service broker nhận các request từ platform để cấp phát service instance, tạo binding cho ứng dụng và thu hồi tài nguyên khi không còn sử dụng. Trong môi trường phân tán, platform, gateway, broker hoặc provider có thể timeout sau khi một side effect đã xảy ra. Client không biết request đã thành công hay chưa nên gửi lại. Nếu broker thực hiện lại toàn bộ thao tác, hệ thống có thể tạo database trùng, tạo nhiều tài khoản cho cùng binding hoặc xóa nhầm tài nguyên còn được sử dụng.

**Idempotency** là khả năng nhận cùng một yêu cầu nhiều lần mà trạng thái cuối và tác động nghiệp vụ tương đương với việc thực hiện yêu cầu một lần. Đây là yêu cầu quan trọng đối với các endpoint vòng đời của Open Service Broker API (OSB API), đặc biệt là provision, bind, unbind và deprovision.

Idempotency không có nghĩa broker bỏ qua mọi request lặp. Broker phải phân biệt retry của cùng một ý định với request mới dùng lại cùng định danh nhưng có nội dung khác. Bài học này trình bày cách dùng instance ID và binding ID làm định danh tài nguyên, lưu dấu vết request, bảo vệ side effect tại provider, xử lý operation bất đồng bộ và triển khai các cơ chế đó trong Spring Cloud Service Broker.

## 1. Vì sao service broker cần idempotency?

HTTP request có thể bị gửi lại vì nhiều nguyên nhân:

- Platform không nhận được response trước khi timeout.
- Load balancer đóng kết nối trong khi broker vẫn tiếp tục xử lý.
- Broker restart sau khi provider đã tạo tài nguyên nhưng trước khi ghi kết quả vào database.
- Worker nhận lại một message do queue giao ít nhất một lần.
- Platform retry sau lỗi mạng mà không biết request trước đã tới broker hay chưa.
- Người vận hành hoặc controller gửi lại cùng thao tác khi trạng thái hiển thị chưa được cập nhật.

Ví dụ, platform gửi PUT provision cho một PostgreSQL instance. Provider đã tạo database thành công, nhưng broker mất kết nối trước khi nhận response. Platform gửi lại request. Nếu broker gọi provider tạo database lần nữa mà không kiểm tra trạng thái, có thể xuất hiện hai database cho cùng một service instance hoặc một tài nguyên mồ côi không được broker quản lý.

Tương tự, khi bind, provider đã tạo user và password nhưng response bị mất. Retry không được tạo thêm một user mới hoặc làm thay đổi password khiến ứng dụng đang dùng credential cũ bị mất kết nối.

Idempotency giúp broker biến các lần retry thành một kết quả nhất quán. Nó giảm tài nguyên trùng, tránh side effect lặp và cho phép hệ thống phục hồi sau sự cố mà không cần giả định mạng luôn đáng tin cậy.

## 2. Idempotency trong hợp đồng OSB API

OSB API dùng các resource identifier do platform cung cấp trong URL:

| Thao tác | HTTP method và resource | Định danh ổn định |
|---|---|---|
| Provision service instance | PUT /v2/service_instances/{instance_id} | instance_id |
| Deprovision service instance | DELETE /v2/service_instances/{instance_id} | instance_id |
| Create service binding | PUT /v2/service_instances/{instance_id}/service_bindings/{binding_id} | instance_id + binding_id |
| Delete service binding | DELETE /v2/service_instances/{instance_id}/service_bindings/{binding_id} | instance_id + binding_id |
| Poll operation | GET /v2/service_instances/{instance_id}/last_operation | instance_id + operation nếu được cung cấp |

Các ID này đại diện cho tài nguyên trong phạm vi platform. Platform giữ nguyên instance ID khi retry provision hoặc deprovision và giữ nguyên binding ID khi retry bind hoặc unbind. Broker nên sử dụng các định danh đó làm khóa nghiệp vụ.

Cần phân biệt:

- **Resource ID:** định danh instance hoặc binding tồn tại qua nhiều request.
- **Request fingerprint:** dấu vết nội dung có ý nghĩa của một yêu cầu, dùng để nhận diện cùng ý định hoặc phát hiện xung đột.
- **Operation token:** định danh một lần xử lý bất đồng bộ để platform poll.
- **Provider resource ID:** định danh database, user, key hoặc tài nguyên thực tế ở nhà cung cấp.
- **Correlation ID:** định danh dùng để nối log và trace.

Các giá trị này có thể được liên kết trong database nhưng không nên dùng thay thế lẫn nhau. Một instance có thể có nhiều operation và nhiều binding; mỗi binding cũng có thể tạo một hoặc nhiều provider-side object theo thiết kế của broker.

OSB API sử dụng PUT và DELETE cho các thao tác vòng đời có semantics lặp an toàn. Tuy nhiên, chỉ dùng HTTP method đúng không tự làm cho implementation idempotent. Broker phải bảo đảm cả database transaction, provider adapter, worker và secret store cùng tuân theo quy tắc này.

## 3. Provision idempotent theo instance_id

Khi nhận PUT provision, broker cần kiểm tra instance ID trước khi tạo tài nguyên mới.

Một quy trình điển hình:

1. Xác thực platform client và kiểm tra phiên bản OSB API.
2. Parse request và validate service ID, plan ID, context, parameters.
3. Tìm service instance theo instance ID.
4. Nếu chưa tồn tại, tạo một bản ghi reservation ở trạng thái PROVISIONING.
5. Ghi fingerprint của yêu cầu và operation nếu cần xử lý bất đồng bộ.
6. Gọi provider với idempotency key hoặc external resource name ổn định.
7. Lưu provider resource ID và trạng thái đã xác nhận.
8. Trả response theo trạng thái operation và hợp đồng OSB API.

Nếu instance đã tồn tại và request lặp có cùng ý định, broker trả kết quả phù hợp với trạng thái hiện tại theo response contract của OSB API. Không tạo thêm tài nguyên. Nếu instance ID đã được dùng cho một yêu cầu khác có service, plan hoặc cấu hình không tương thích, broker phải phát hiện xung đột thay vì ghi đè bản ghi cũ.

Ví dụ request:

~~~http
PUT /v2/service_instances/instance-7f3a?accepts_incomplete=true
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "context": {
    "platform": "kubernetes",
    "namespace": "payments"
  },
  "parameters": {
    "storage_gb": 100,
    "backup_enabled": true
  }
}
~~~

Broker có thể lưu ý định provision đã chuẩn hóa:

~~~json
{
  "instance_id": "instance-7f3a",
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "request_fingerprint": "sha256:...",
  "lifecycle_state": "PROVISIONING"
}
~~~

Fingerprint trong ví dụ chỉ là giá trị minh họa. Không ghi dữ liệu bí mật thô vào fingerprint hoặc log.

### 3.1. Cùng ID, cùng nội dung

Nếu request retry có cùng instance ID và cùng nội dung có ý nghĩa, broker phải tiếp tục hoặc trả lại kết quả của lần provision đã được chấp nhận. Tùy trạng thái:

- Instance đang PROVISIONING: trả thông tin async phù hợp và operation đang theo dõi, nếu workflow bất đồng bộ.
- Instance đã ACTIVE: trả response thành công theo semantics của OSB API, không tạo tài nguyên thứ hai.
- Instance đang FAILED: áp dụng chính sách retry hoặc recovery đã định nghĩa; không tự tạo tài nguyên mới khi chưa đối soát provider.
- Instance đang DEPROVISIONING: từ chối hoặc tuần tự hóa provision mới theo policy; không để hai lifecycle operation chạy ngược chiều.

### 3.2. Cùng ID, khác nội dung

Nếu cùng instance ID nhưng request có plan ID hoặc parameters khác với ý định đã lưu, broker cần trả conflict phù hợp. Không được xem một request có nội dung khác là retry chỉ vì URL giống nhau.

Ví dụ, instance đã được tạo với plan standard và storage 100 GB. Một request mới cùng instance ID nhưng yêu cầu plan enterprise không phải retry của provision cũ; đó là yêu cầu thay đổi dịch vụ và phải đi qua endpoint update với policy tương ứng.

## 4. Create binding idempotent theo instance_id và binding_id

Binding có khóa nghiệp vụ là cặp instance ID và binding ID. Cùng một binding ID trong hai service instance khác nhau là hai quan hệ khác nhau, còn cùng một cặp ID phải luôn tham chiếu một binding cụ thể.

Khi nhận PUT binding, broker nên:

1. Kiểm tra instance tồn tại và đã sẵn sàng.
2. Kiểm tra service offering bindable và caller có quyền bind.
3. Tra cứu binding theo cặp instance ID và binding ID.
4. Nếu chưa có, tạo reservation PENDING/CREATING có unique constraint.
5. Xác định permission profile và credential mode.
6. Tạo principal, key hoặc ACL tại provider bằng tên ổn định hoặc idempotency key.
7. Lưu principal ID và secret reference.
8. Chuyển binding sang ACTIVE rồi trả credentials.
9. Nếu retry cùng yêu cầu, trả lại binding đã có theo quy tắc response và khả năng truy xuất secret.

Ví dụ request:

~~~http
PUT /v2/service_instances/instance-7f3a/service_bindings/binding-billing
X-Broker-API-Version: 2.17
Content-Type: application/json
~~~

~~~json
{
  "service_id": "service-postgresql",
  "plan_id": "plan-standard",
  "bind_resource": {
    "app_guid": "app-billing"
  },
  "parameters": {
    "role": "read_write"
  }
}
~~~

Nếu provider đã tạo user billing_binding nhưng broker mất kết nối trước khi lưu binding record, lần retry phải tìm được principal đó bằng external name hoặc idempotency key. Tạo một user khác mỗi lần retry sẽ để lại principal mồ côi và có thể cấp nhiều credential cho cùng một consumer.

### 4.1. Trả lại credentials nhất quán

Binding response có thể chứa username, password, hostname, port, database hoặc certificate. Nếu response đầu tiên bị mất, platform có thể retry create binding và cần nhận được credentials tương ứng với binding đã tạo.

Nhiều provider không cho đọc lại password sau khi tạo user. Vì vậy broker cần lưu secret an toàn trong secret manager hoặc encrypted store, liên kết bằng credential reference với binding record. Không log credentials hoặc lưu password rõ trong bảng binding.

Nếu broker không thể khôi phục credentials, nó phải có quy trình recovery được định nghĩa rõ, chẳng hạn rotation credential có kiểm soát và cập nhật secret reference. Không tạo thêm principal mới trong im lặng rồi bỏ lại credential cũ chưa được thu hồi.

## 5. Unbind idempotent theo binding ID

Unbind dùng DELETE trên resource binding. Retry unbind không được tạo side effect mới hoặc làm ảnh hưởng binding khác.

Một flow an toàn:

1. Xác thực caller và kiểm tra quyền trên instance/binding.
2. Tìm binding theo instance ID và binding ID.
3. Nếu binding đã REVOKED hoặc không còn tồn tại, trả kết quả phù hợp với semantics của OSB API.
4. Nếu đang ACTIVE, chuyển sang REVOKING để ngăn cấp phát hoặc thao tác cạnh tranh.
5. Thu hồi principal, key, certificate hoặc ACL theo credential mode.
6. Vô hiệu hóa secret reference hoặc quyền truy cập secret.
7. Lưu trạng thái REVOKED và kết quả provider.
8. Trả response thành công theo endpoint contract.

Ví dụ, nếu một binding đã được revoke nhưng platform retry DELETE vì mất response, broker không được gọi provider xóa một principal khác hoặc làm giảm reference count shared credential lần thứ hai.

### 5.1. Tài khoản riêng

Với credential riêng, broker có thể revoke đúng principal gắn với binding. Việc lặp lại thao tác revoke phải an toàn: nếu principal đã bị xóa, adapter có thể xác nhận trạng thái absent là kết quả mong muốn, miễn là xác minh đúng principal thuộc binding.

### 5.2. Credential dùng chung

Với shared credential, broker phải kiểm tra các binding còn tham chiếu principal đó. Retry unbind không được giảm reference count nhiều lần. Cần lưu một trạng thái revoke duy nhất cho binding và thực hiện cập nhật reference count trong transaction có điều kiện.

Chỉ revoke shared principal khi không còn binding active và policy cho phép. Một binding bị xóa không được làm gián đoạn các consumer khác đang dùng cùng credential.

## 6. Deprovision idempotent theo instance_id

Deprovision là thao tác thu hồi service instance. Platform có thể gửi DELETE nhiều lần do timeout hoặc controller retry.

Broker nên giữ một tombstone hoặc bản ghi lifecycle tối thiểu trong khi xử lý để có thể nhận diện request lặp và trả kết quả nhất quán.

Một flow:

1. Xác thực platform và quyền trên instance.
2. Tra cứu instance theo ID.
3. Nếu đã DEPROVISIONED, xử lý request lặp theo response contract; không gọi provider xóa lần nữa nếu không cần.
4. Nếu chưa xóa, đánh dấu DEPROVISIONING và tạo operation nếu async.
5. Thu hồi hoặc kiểm tra các binding còn tồn tại theo policy của broker và platform.
6. Gọi provider xóa đúng tài nguyên đã liên kết.
7. Xác nhận tài nguyên đã absent hoặc được giải phóng.
8. Đánh dấu DEPROVISIONED, lưu tombstone và operation result.
9. Dọn metadata sau thời gian retention thích hợp.

Nếu provider đã xóa database nhưng broker crash trước khi cập nhật state, retry phải tra cứu resource ID hoặc external name để xác nhận tài nguyên đã biến mất. Nếu không còn tài nguyên, broker có thể hoàn tất trạng thái deprovision mà không cần gọi tạo hoặc xóa một resource khác.

Không xóa ngay toàn bộ bản ghi instance khi bắt đầu DELETE nếu broker còn cần dữ liệu để phục hồi operation hoặc trả last operation. Tombstone cần giữ định danh, provider reference đã làm sạch, trạng thái và thời điểm thu hồi theo chính sách retention.

## 7. Request fingerprint và cách so sánh nội dung

Resource ID giúp nhận diện tài nguyên, nhưng broker còn cần xác định hai request cùng ID có cùng ý định hay không. Request fingerprint có thể hỗ trợ điều đó.

Một fingerprint có thể được tạo từ các field có ý nghĩa:

- Operation type: provision, bind, unbind hoặc deprovision.
- Instance ID và binding ID nếu có.
- Service ID và plan ID.
- Parameters sau khi chuẩn hóa.
- Context có ảnh hưởng đến ownership hoặc routing.
- Một số giá trị version/previous values theo semantics của request.

Không đưa vào fingerprint các field thay đổi qua từng lần truyền nhưng không làm thay đổi ý định, chẳng hạn request timestamp, trace ID hoặc header correlation. Nếu đưa các giá trị này vào, cùng một request retry sẽ có fingerprint khác nhau.

### 7.1. Canonicalization trước khi hash

JSON object có thể có thứ tự key khác nhau nhưng mang cùng dữ liệu. Trước khi hash, broker nên chuẩn hóa:

1. Parse JSON thành cấu trúc dữ liệu.
2. Chuẩn hóa key order theo quy tắc ổn định.
3. Chuẩn hóa số và kiểu dữ liệu theo schema.
4. Áp dụng default chỉ khi business contract quy định rõ.
5. Phân biệt absent, null và empty nếu chúng có ý nghĩa khác nhau.
6. Loại bỏ field không thuộc ý định nghiệp vụ.
7. Serialize theo canonical representation.
8. Tính hash bằng thuật toán phù hợp.

Ví dụ hai JSON sau có thể mang cùng ý nghĩa:

~~~json
{
  "storage_gb": 100,
  "backup_enabled": true
}
~~~

~~~json
{
  "backup_enabled": true,
  "storage_gb": 100
}
~~~

Nếu chỉ hash chuỗi JSON thô, hai payload có thể cho hash khác nhau vì thứ tự key. Canonicalization giúp nhận diện cùng nội dung logic.

Không nên tự động coi absent và null là tương đương. Với update parameters, absent có thể nghĩa là giữ nguyên, trong khi null có thể không hợp lệ hoặc có ý nghĩa xóa cấu hình. Fingerprint phải phản ánh đúng semantics của operation.

### 7.2. Không dùng hash làm bằng chứng bảo mật

Fingerprint là công cụ so sánh, không phải cơ chế xác thực. Caller vẫn phải được authenticate và authorize. Nếu request chứa secret, tránh ghi raw fingerprint input hoặc secret vào log. Có thể dùng HMAC hoặc hash trên dữ liệu đã loại bỏ/che giá trị nhạy cảm, tùy mục đích đối chiếu.

## 8. Bảo đảm idempotency ở database

Kiểm tra "nếu chưa tồn tại thì insert" bằng hai câu lệnh riêng không an toàn khi có request đồng thời:

~~~text
Request A: SELECT -> không có instance
Request B: SELECT -> không có instance
Request A: INSERT
Request B: INSERT
~~~

Hai request cùng thấy chưa có dữ liệu rồi cùng tạo reservation. Cần dùng database constraint và transaction để bảo vệ invariant.

Các ràng buộc thường cần:

| Bảng | Unique key gợi ý | Mục đích |
|---|---|---|
| service_instance | instance_id | Một instance ID chỉ có một bản ghi |
| service_binding | instance_id + binding_id | Một binding trong một instance chỉ có một bản ghi |
| operation | operation_token | Operation token không trùng |
| operation | instance_id + active-operation policy | Kiểm soát operation đồng thời theo instance |
| provider_resource | provider + external_resource_key | Tránh liên kết cùng tài nguyên provider nhiều lần |
| outbox | event_id hoặc aggregate_id + sequence | Chống phát event trùng theo invariant |

Ví dụ schema SQL minh họa:

~~~sql
CREATE TABLE service_instance (
    instance_id VARCHAR(128) PRIMARY KEY,
    service_id VARCHAR(128) NOT NULL,
    plan_id VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    lifecycle_state VARCHAR(32) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE service_binding (
    instance_id VARCHAR(128) NOT NULL,
    binding_id VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    principal_id VARCHAR(256),
    credential_ref VARCHAR(512),
    status VARCHAR(32) NOT NULL,
    PRIMARY KEY (instance_id, binding_id)
);
~~~

Đây là ví dụ cấu trúc rút gọn. Production schema cần foreign key, index, timestamp, encryption strategy và migration phù hợp.

Khi hai request cạnh tranh insert cùng khóa, một transaction sẽ thắng. Request còn lại đọc lại bản ghi đã tồn tại rồi so sánh fingerprint và state. Nếu cùng ý định, trả kết quả hiện có; nếu khác, trả conflict theo policy.

Optimistic locking với version hoặc câu lệnh cập nhật có điều kiện giúp tránh hai worker cùng chuyển state từ một phiên bản cũ. Với thao tác provider kéo dài, có thể dùng lease/lock có thời hạn để worker khác tiếp tục khi worker trước chết.

## 9. Idempotency ở provider adapter

Database broker chỉ kiểm soát trạng thái nội bộ. Side effect thật xảy ra ở provider: tạo database, user, key, queue, bucket hoặc xóa tài nguyên. Vì vậy adapter cũng cần idempotency.

Các kỹ thuật có thể dùng:

- Truyền idempotency key nếu provider API hỗ trợ.
- Dùng external resource name ổn định được suy ra từ instance ID hoặc binding ID.
- Thêm tag/label chứa broker instance ID và binding ID vào tài nguyên provider.
- Trước khi tạo, tra cứu tài nguyên theo external key.
- Sau timeout, truy vấn trạng thái provider trước khi gửi lệnh tạo lại.
- Khi delete, xác nhận tài nguyên đã absent trước khi coi thao tác hoàn tất.
- Lưu provider request ID để truy vấn operation phía provider.

Ví dụ tên resource ổn định:

~~~text
broker-pg-instance-7f3a
broker-pg-instance-7f3a-binding-billing
~~~

Tên thực tế cần tuân theo giới hạn ký tự, uniqueness và quy tắc đặt tên của provider. Không nhúng tenant secret hoặc dữ liệu nhạy cảm vào resource name.

Nếu provider không có idempotency key, broker có thể dùng external name và reconciliation. Tuy nhiên, cần xử lý trường hợp provider tạo tài nguyên thành công nhưng response bị mất: adapter tìm resource theo tên/label, xác minh ownership rồi tiếp tục lưu mapping. Không được chỉ dựa vào timeout để kết luận provider chưa làm gì.

## 10. Transactional outbox và worker retry

Với operation bất đồng bộ, broker thường phải ghi operation vào database và gửi message cho worker. Hai việc này có thể thất bại độc lập.

Transactional outbox giải quyết khoảng trống bằng cách ghi operation và event trong cùng transaction:

~~~mermaid
flowchart TD
    A["Nhận request OSB"] --> B["Transaction database"]
    B --> C["Reserve instance hoặc binding"]
    B --> D["Insert operation"]
    B --> E["Insert outbox event"]
    C --> F["Commit"]
    D --> F
    E --> F
    F --> G["Outbox publisher"]
    G --> H["Queue"]
    H --> I["Worker"]
    I --> J["Idempotent provider adapter"]
    J --> K["Persist result và operation state"]
~~~

Publisher có thể gửi event nhiều lần nếu không nhận được xác nhận. Worker phải kiểm tra operation state và thực hiện side effect theo idempotency key. Nếu operation đã terminal, worker không chạy lại tác động cũ.

Không giữ transaction database mở trong suốt thời gian gọi provider. Worker nên:

1. Claim operation bằng lease hoặc compare-and-set.
2. Kiểm tra state và attempt number.
3. Gọi provider ngoài transaction.
4. Xác minh kết quả provider.
5. Mở transaction mới để cập nhật resource mapping, operation state và outbox event tiếp theo.
6. Ack message sau khi commit.

Nếu worker crash sau provider success nhưng trước database commit, worker tiếp theo phải tra cứu provider bằng external key hoặc provider request ID để xác nhận kết quả trước khi retry.

## 11. Idempotency với asynchronous operations

Một request có thể trả HTTP 202 và operation token. Khi platform retry request ban đầu, broker phải quyết định có tiếp tục operation cũ hay tạo operation mới.

Quy tắc gợi ý:

| Trạng thái hiện tại | Request retry cùng nội dung | Hành vi |
|---|---|---|
| ACCEPTED / QUEUED | Cùng resource ID và fingerprint | Trả lại operation hiện có |
| RUNNING | Cùng resource ID và fingerprint | Không tạo worker hoặc provider call thứ hai |
| SUCCEEDED | Cùng resource ID và fingerprint | Trả kết quả đã hoàn tất theo OSB contract |
| FAILED | Cùng fingerprint | Thực hiện retry/recovery theo policy; không tự tạo tài nguyên mới |
| Có operation khác đang chạy | Request có nội dung khác | Conflict hoặc tuần tự hóa |
| Terminal operation cũ, request mới hợp lệ | Ý định mới theo endpoint phù hợp | Tạo operation mới với token mới |

Operation token định danh lần xử lý; nó không thay thế instance ID hoặc binding ID. Một instance có thể có nhiều operation theo thời gian, nhưng chỉ những operation được phép theo state machine mới có thể chạy tiếp.

Endpoint last operation là GET chỉ đọc trạng thái. Gọi polling nhiều lần không được làm tăng attempt count, phát job mới hoặc gọi provider. Response nên được tạo từ operation store đã được worker cập nhật.

## 12. State machine ngăn side effect lặp

Mỗi resource nên có state machine rõ ràng. Ví dụ instance:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> ACTIVE
    PROVISIONING --> FAILED
    ACTIVE --> UPDATING
    UPDATING --> ACTIVE
    UPDATING --> FAILED
    ACTIVE --> DEPROVISIONING
    FAILED --> PROVISIONING: recovery theo policy
    DEPROVISIONING --> DEPROVISIONED
    DEPROVISIONING --> FAILED
    DEPROVISIONED --> [*]
~~~

Binding có thể dùng state riêng:

~~~mermaid
stateDiagram-v2
    [*] --> CREATING
    CREATING --> ACTIVE
    CREATING --> FAILED
    ACTIVE --> REVOKING
    REVOKING --> REVOKED
    REVOKING --> FAILED
    REVOKED --> [*]
~~~

State transition cần có điều kiện:

- Chỉ tạo binding khi instance ACTIVE.
- Không deprovision đồng thời với update đang chạy nếu policy không cho phép.
- Không chuyển instance về ACTIVE trước khi provider xác nhận thao tác hoàn tất.
- Không chuyển binding sang REVOKED nếu credential vẫn còn khả năng truy cập.
- Không cho worker retry một operation đã terminal.
- Khi recovery, kiểm tra provider state trước khi lặp side effect.

State machine là lớp bảo vệ nghiệp vụ. Database constraints bảo vệ uniqueness; provider idempotency bảo vệ side effect; cả ba cần phối hợp.

## 13. Xử lý conflict và lỗi khi request lặp

Không phải request lặp nào cũng là retry hợp lệ. Broker cần phân biệt ít nhất ba tình huống:

1. **Retry cùng ý định:** cùng resource ID, operation và nội dung có ý nghĩa. Tiếp tục hoặc trả kết quả hiện có.
2. **Request xung đột:** cùng resource ID nhưng service, plan hoặc parameters không tương thích với bản ghi hiện tại. Trả conflict phù hợp.
3. **Request stale:** caller gửi previous state hoặc context cũ trong khi instance đã được cập nhật. Kiểm tra version và policy trước khi xử lý.

Một response lỗi nên đủ rõ để platform hoặc operator biết xung đột nằm ở đâu nhưng không tiết lộ dữ liệu nhạy cảm. Không chuyển mọi duplicate thành HTTP 500. Mã status cụ thể phải theo endpoint và phiên bản OSB API.

Ví dụ error body:

~~~json
{
  "description": "The supplied instance identifier is already associated with a different service plan."
}
~~~

Đối với request có thể retry, broker cần phân biệt lỗi tạm thời như timeout provider với lỗi vĩnh viễn như plan không tồn tại hoặc caller không có quyền. Retry vô hạn với lỗi vĩnh viễn sẽ tạo tải và làm operation bị kẹt.

## 14. Spring Cloud Service Broker: tổ chức idempotency ở các lớp

Spring Cloud Open Service Broker cung cấp abstraction để xử lý request OSB. Idempotency nên được triển khai ở application/domain layer và repository/provider adapter, không chỉ dựa vào controller.

Một cấu trúc trách nhiệm:

| Thành phần | Trách nhiệm idempotency |
|---|---|
| OSB request handler | Parse request, xác thực, định tuyến đúng use case |
| Request normalizer | Chuẩn hóa parameters/context và tạo fingerprint |
| Lifecycle coordinator | Kiểm tra state, phân loại retry và conflict |
| Instance repository | Unique instance ID, optimistic locking |
| Binding repository | Unique instance ID + binding ID |
| Operation repository | Lưu operation token, state và request fingerprint |
| Outbox publisher | Phát event có thể retry |
| Worker | Claim operation và không chạy side effect terminal |
| Provider adapter | Idempotency key, external name và reconciliation |
| Secret store adapter | Lưu/truy xuất credential nhất quán cho binding |

Pseudocode provision:

~~~java
public ProvisionResult provision(ProvisionCommand command) {
    String fingerprint = fingerprintService.forProvision(command);

    InstanceReservation reservation =
        instanceRepository.reserveIfAbsent(
            command.instanceId(),
            command.serviceId(),
            command.planId(),
            fingerprint
        );

    if (reservation.isExisting()) {
        if (!reservation.fingerprint().equals(fingerprint)) {
            throw new InstanceRequestConflictException(command.instanceId());
        }

        return provisionResultForExisting(reservation);
    }

    Operation operation = operationService.createProvision(reservation);
    outboxService.appendProvisionRequested(operation, reservation);

    return ProvisionResult.accepted(operation.publicToken());
}
~~~

Pseudocode này mô tả ý tưởng; kiểu request/response và extension point cụ thể phụ thuộc phiên bản Spring Cloud Open Service Broker. Việc reserve cần được bảo vệ bằng unique constraint và transaction, không phải chỉ bằng một lần SELECT trước INSERT.

Pseudocode binding:

~~~java
public BindingResult bind(BindCommand command) {
    String fingerprint = fingerprintService.forBinding(command);

    BindingReservation reservation =
        bindingRepository.reserveIfAbsent(
            command.instanceId(),
            command.bindingId(),
            fingerprint
        );

    if (reservation.isExisting()) {
        if (!reservation.fingerprint().equals(fingerprint)) {
            throw new BindingRequestConflictException(command.bindingId());
        }

        return bindingResultForExisting(reservation);
    }

    ProvisionedCredential credential =
        credentialProvisioner.provisionIdempotently(command);

    return bindingCoordinator.activate(reservation, credential);
}
~~~

Provider adapter cần dùng một idempotency key ổn định dựa trên resource identity. Nếu broker tạo credential trước khi lưu binding, recovery phải có thể tra cứu hoặc revoke principal đã tạo. Với shared credential, reference count phải được cập nhật nguyên tử theo binding state.

## 15. Ví dụ tình huống lỗi và cách phục hồi

### 15.1. Provider tạo database nhưng broker timeout

- Broker đã reserve instance ID và lưu fingerprint.
- Provider tạo database thành công.
- Broker mất kết nối trước khi nhận response.
- Platform retry PUT cùng instance ID.
- Broker tìm reservation hiện có và không tạo reservation thứ hai.
- Adapter tra cứu resource theo external name hoặc provider request ID.
- Broker xác nhận resource đã tồn tại, lưu provider resource ID và tiếp tục operation.

### 15.2. Binding đã tạo user nhưng response bị mất

- Broker tạo principal gắn với binding ID.
- Secret được lưu trong vault và binding record được kích hoạt.
- Response bị mất trên đường về platform.
- Platform retry PUT cùng binding ID.
- Broker tìm binding ACTIVE và cùng fingerprint.
- Broker trả lại credentials từ secret reference đã lưu; không tạo user mới.

### 15.3. Unbind retry làm giảm shared reference count hai lần

- Hai binding cùng dùng một shared principal.
- Unbind binding A chuyển trạng thái ACTIVE sang REVOKING.
- Transaction chỉ giảm reference count khi transition đó được commit lần đầu.
- Retry DELETE thấy binding đã REVOKED và không giảm thêm.
- Principal vẫn tồn tại vì binding B còn active.

### 15.4. Deprovision provider thành công nhưng broker crash

- Broker đánh dấu instance DEPROVISIONING và lưu operation.
- Provider xóa database.
- Broker crash trước khi cập nhật DEPROVISIONED.
- Worker được giao lại operation.
- Adapter kiểm tra external resource đã absent.
- Broker ghi operation succeeded và giữ tombstone theo retention.

Các tình huống này cho thấy idempotency cần được thiết kế qua toàn bộ chuỗi, không chỉ tại endpoint HTTP.

## 16. Kiểm thử idempotency

Kiểm thử nên chạy cả tuần tự, đồng thời và qua failure injection.

| Nhóm kiểm thử | Trường hợp | Kết quả mong đợi |
|---|---|---|
| Provision retry | PUT cùng instance ID và payload hai lần | Một instance/provider resource |
| Provision conflict | Cùng instance ID nhưng plan khác | Conflict, không ghi đè |
| Concurrent provision | Hai request đồng thời cùng ID | Một reservation thắng |
| Bind retry | PUT cùng instance ID + binding ID | Một binding/principal |
| Bind conflict | Cùng binding ID nhưng parameters khác | Conflict |
| Concurrent bind | Hai request đồng thời cùng binding ID | Không tạo hai credential |
| Unbind retry | DELETE cùng binding nhiều lần | Revoke một lần về mặt nghiệp vụ |
| Shared reference | Unbind cùng binding lặp | Reference count chỉ giảm một lần |
| Deprovision retry | DELETE instance sau khi đã xóa | Không tạo side effect sai |
| Provider timeout | Provider success nhưng response bị mất | Reconciliation tìm resource hiện có |
| Worker redelivery | Queue giao message nhiều lần | Một kết quả nghiệp vụ |
| Broker restart | Restart giữa provider side effect và DB commit | Operation phục hồi đúng |
| Async polling | GET last operation lặp lại | Chỉ đọc state, không phát job |
| Secret recovery | Bind retry sau khi response mất | Trả cùng credential hoặc recovery theo policy |
| Version conflict | Optimistic lock phát hiện bản ghi stale | Không ghi đè state mới |

Một test quan trọng là chạy nhiều request đồng thời với cùng resource ID. Unit test tuần tự không phát hiện được race condition giữa SELECT và INSERT. Nên dùng integration test với database thực tế hoặc môi trường test có transaction isolation tương đương production.

Failure injection có thể mô phỏng timeout sau provider success, lỗi ghi database, worker restart và queue redelivery. Test cần kiểm tra số lượng tài nguyên thực tại provider, không chỉ số bản ghi trong database broker.

## 17. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ kiểm tra tồn tại bằng SELECT rồi INSERT | Hai request đồng thời tạo trùng | Unique constraint và transaction |
| Dùng instance ID làm operation token | Không phân biệt nhiều operation | Tách resource ID và operation token |
| Cùng binding ID nhưng tạo user mới mỗi retry | Principal mồ côi, credential không nhất quán | Reservation và provider idempotency |
| Hash JSON thô | Key order khác làm fingerprint khác | Canonicalize trước khi hash |
| Coi absent và null giống nhau | Update sai cấu hình | Định nghĩa semantics rõ |
| Trả success trước khi provider side effect hoàn tất | Platform tin tài nguyên đã sẵn sàng | Chỉ xác nhận theo state đã kiểm chứng |
| Gửi queue sau commit mà không có outbox | Operation mồ côi khi publish lỗi | Transactional outbox |
| Worker không kiểm tra terminal state | Side effect chạy lại sau redelivery | State guard và idempotency key |
| Xóa binding record trước khi revoke provider | Credential vẫn còn hiệu lực nhưng broker mất dấu | Revoke có kiểm soát và tombstone |
| Giảm shared reference count mỗi lần DELETE | Principal bị xóa khi consumer khác còn dùng | Chỉ giảm khi state transition xảy ra lần đầu |
| Không đối soát provider | Tài nguyên mồ côi sau crash | Reconciliation định kỳ |

## 18. Checklist triển khai

Trước khi phát hành broker, hãy xác nhận:

- [ ] Instance ID và binding ID được dùng làm resource identity ổn định.
- [ ] Cùng resource ID và cùng request intent không tạo side effect trùng.
- [ ] Cùng resource ID nhưng payload khác được phát hiện là conflict.
- [ ] Request fingerprint được tạo từ dữ liệu đã canonicalize.
- [ ] Absent, null, empty và default có semantics rõ ràng.
- [ ] Database có unique constraint cho instance và binding.
- [ ] Reservation và operation được ghi trong transaction phù hợp.
- [ ] Provider adapter dùng idempotency key, external name hoặc reconciliation.
- [ ] Binding retry có thể khôi phục credentials an toàn.
- [ ] Unbind retry không revoke nhầm principal hoặc giảm reference count nhiều lần.
- [ ] Deprovision retry xử lý được tài nguyên đã absent.
- [ ] Async operation có token, state bền vững và worker retry an toàn.
- [ ] Transactional outbox hoặc cơ chế tương đương ngăn mất job.
- [ ] Optimistic locking/lease ngăn hai worker xử lý cùng resource đồng thời.
- [ ] Terminal state không bị thay đổi bởi retry đến muộn.
- [ ] Tombstone và retention cho phép recovery sau delete.
- [ ] Có audit và correlation ID nhưng không log secret.
- [ ] Có concurrency, integration và failure-injection tests.

Idempotency là thuộc tính xuyên suốt của vòng đời service broker. Resource ID giúp nhận diện cùng tài nguyên; fingerprint giúp phân biệt retry với request xung đột; database constraint bảo vệ uniqueness; provider adapter và worker ngăn side effect lặp; operation store và outbox giúp phục hồi sau sự cố. Khi provision, binding, unbind và deprovision cùng tuân theo các nguyên tắc này, Spring Cloud Service Broker có thể xử lý retry và lỗi mạng mà vẫn duy trì trạng thái nhất quán giữa platform, broker và provider.
