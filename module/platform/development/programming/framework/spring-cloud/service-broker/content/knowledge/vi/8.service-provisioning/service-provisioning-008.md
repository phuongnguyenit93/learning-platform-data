# Lưu kết quả cấp phát và xử lý yêu cầu tạo lại cùng định danh

Trong Open Service Broker API (OSB API), nền tảng gửi yêu cầu provision bằng cách gọi `PUT /v2/service_instances/{instance_id}`. Nền tảng có thể gửi lại cùng request khi timeout, mất kết nối hoặc không nhận được response dù broker đã bắt đầu hay hoàn tất công việc. Vì vậy, service broker phải lưu kết quả cấp phát đủ bền vững để nhận diện request lặp, trả lại trạng thái phù hợp và tránh tạo thêm tài nguyên ngoài ý muốn.

Với `SPRING_CLOUD_SERVICE_BROKER`, đây là trách nhiệm cốt lõi của lớp quản lý vòng đời. Broker cần lưu mối liên hệ giữa định danh OSB, service và plan đã chọn, tenant sở hữu, operation đang chạy và tài nguyên backend thực tế. Khi request đến lần nữa với cùng định danh, broker phải so sánh nội dung đã chuẩn hóa với bản ghi hiện có để quyết định trả kết quả cũ, trả operation đang chạy hay báo xung đột.

## 1. Vì sao phải lưu kết quả provision?

Provision có thể tạo ra tài nguyên tốn chi phí và mất thời gian, chẳng hạn database, cluster, queue hoặc bucket. Một request có thể đi qua nhiều thành phần: nền tảng, mạng, gateway, broker, queue và backend. Kết nối có thể đứt ở bất kỳ thời điểm nào.

Một tình huống phổ biến:

1. Platform gửi yêu cầu tạo instance `orders-db-prod`.
2. Broker gọi backend và database được tạo thành công.
3. Broker lưu kết quả hoặc đang chuẩn bị trả response.
4. Kết nối bị timeout trước khi platform nhận được response.
5. Platform gửi lại cùng request vì không biết lần trước đã thành công hay chưa.

Nếu broker không lưu trạng thái và không có cơ chế nhận diện request lặp, lần thứ hai có thể tạo thêm một database. Kết quả là tài nguyên trùng, chi phí tăng, dữ liệu bị chia tách và nền tảng không biết database nào mới là instance được quản lý.

Lưu kết quả provision giúp broker:

- Nhận diện một instance đã được yêu cầu hoặc đã tồn tại.
- Trả lại kết quả đã lưu mà không gọi backend lần nữa.
- Tiếp tục một operation đang chạy sau khi request HTTP kết thúc.
- Phát hiện cùng ID nhưng nội dung request mâu thuẫn.
- Đối soát tài nguyên khi broker khởi động lại hoặc backend timeout.
- Hỗ trợ update, bind, unbind và deprovision dựa trên ownership đã lưu.

## 2. Định danh của một yêu cầu provision

OSB API sử dụng `instance_id` trong đường dẫn để định danh service instance. Request body thường có `service_id`, `plan_id`, context và parameters. Broker cần lưu các giá trị có ảnh hưởng đến kết quả cấp phát.

Ví dụ request:

~~~http
PUT /v2/service_instances/orders-db-prod?accepts_incomplete=true
Content-Type: application/json
~~~

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-postgresql-production",
  "context": {
    "platform": "cloudfoundry",
    "organization_guid": "org-commerce",
    "space_guid": "space-production"
  },
  "parameters": {
    "database_name": "orders",
    "storage_gb": 500,
    "backup_retention_days": 14
  }
}
~~~

Một bản ghi provision nội bộ nên gắn ít nhất các dữ liệu sau:

| Nhóm | Dữ liệu | Mục đích |
|---|---|---|
| Định danh | `instance_id`, `platform_id`, internal ID | Tìm đúng instance khi request được gửi lại |
| Ownership | `tenant_id`, platform scope | Kiểm tra quyền truy cập và cô lập dữ liệu |
| Lựa chọn dịch vụ | `service_id`, `plan_id` | Biết service và plan được chọn |
| Nội dung yêu cầu | fingerprint của request đã chuẩn hóa | Phân biệt retry tương đương và request mâu thuẫn |
| Trạng thái | lifecycle state, operation state | Biết provision đang chạy, thành công hay thất bại |
| Backend | provider, region, resource ID | Đối chiếu và quản lý tài nguyên thực tế |
| Cấu hình lịch sử | plan/profile snapshot, parameters đã lọc | Quản lý instance khi catalog hoặc profile thay đổi |
| Thời gian | created/updated/completed timestamps | Audit, timeout và reconciliation |

`instance_id` là định danh từ platform. `internal_id` là khóa riêng của broker hoặc database. `backend_resource_id` là định danh tài nguyên do nhà cung cấp hoặc operator trả về. Ba giá trị này có mục đích khác nhau và không nên dùng thay thế cho nhau.

Nếu broker phục vụ nhiều platform, khóa nội bộ phải có phạm vi rõ ràng. Ví dụ, nếu mỗi platform có thể sinh ID riêng, có thể dùng `(platform_id, instance_id)` làm unique key. Nếu hợp đồng của broker yêu cầu ID duy nhất trên toàn broker, dùng unique constraint toàn cục cho `instance_id`. Điều quan trọng là một request path phải ánh xạ duy nhất đến một instance trong phạm vi caller đã xác thực.

## 3. Mô hình dữ liệu lưu kết quả

Có thể tách dữ liệu instance, operation và outbox thành các bảng riêng. Cách tách này giúp vòng đời tài nguyên không bị trộn với lịch sử của từng lần xử lý.

### Service instance

Một bảng service instance có thể chứa:

~~~sql
CREATE TABLE service_instance (
    internal_id UUID PRIMARY KEY,
    platform_id VARCHAR(120) NOT NULL,
    instance_id VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(120) NOT NULL,
    service_id VARCHAR(120) NOT NULL,
    plan_id VARCHAR(120) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    lifecycle_state VARCHAR(40) NOT NULL,
    backend_provider VARCHAR(120),
    backend_resource_id VARCHAR(255),
    plan_snapshot JSONB NOT NULL,
    normalized_parameters JSONB,
    last_operation_id VARCHAR(120),
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    CONSTRAINT uq_instance_platform_id
        UNIQUE (platform_id, instance_id)
);
~~~

Đây là schema minh họa cho PostgreSQL. Unique constraint cần được điều chỉnh theo phạm vi định danh mà broker và các platform thống nhất. `tenant_id` được lưu để kiểm tra ownership; không nên suy ra tenant chỉ từ chuỗi `instance_id`.

### Operation

Mỗi yêu cầu dài hoặc mỗi lần thay đổi vòng đời có thể có một operation record:

~~~sql
CREATE TABLE broker_operation (
    operation_id VARCHAR(120) PRIMARY KEY,
    platform_id VARCHAR(120) NOT NULL,
    instance_id VARCHAR(255) NOT NULL,
    operation_type VARCHAR(40) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    operation_state VARCHAR(40) NOT NULL,
    error_code VARCHAR(120),
    safe_error_description TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);
~~~

Một instance có thể có nhiều operation theo thời gian: provision, update, deprovision. Không nên chỉ giữ một cờ `provisioned=true` vì cờ đó không thể giải thích một thao tác đang chạy, lần update thất bại hoặc một lần deprovision đã bắt đầu.

### Outbox

Nếu broker dùng queue để xử lý bất đồng bộ, có thể lưu outbox event trong cùng transaction với instance và operation:

~~~sql
CREATE TABLE broker_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(80) NOT NULL,
    aggregate_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL
);
~~~

Outbox giúp tránh tình huống database đã ghi operation `PENDING` nhưng broker chết trước khi gửi message vào queue. Publisher có thể đọc những event chưa publish và gửi lại an toàn.

## 4. Fingerprint của request đã chuẩn hóa

Để biết request lặp có tương đương hay không, broker cần tạo fingerprint từ dữ liệu có ý nghĩa nghiệp vụ. Không nên hash trực tiếp body JSON thô vì thứ tự key, khoảng trắng hoặc biểu diễn tương đương có thể khác nhau.

Ví dụ hai object có cùng nội dung nhưng thứ tự key khác:

~~~json
{ "database_name": "orders", "storage_gb": 500 }
~~~

~~~json
{ "storage_gb": 500, "database_name": "orders" }
~~~

Sau khi parse, validate và chuẩn hóa, broker tạo một command có kiểu dữ liệu ổn định. Fingerprint có thể dựa trên:

- Platform đã xác thực và phạm vi tenant.
- `instance_id`.
- Operation type, ở đây là provision.
- `service_id` và `plan_id`.
- Context đã được xác minh, chỉ gồm field ảnh hưởng đến ownership hoặc target.
- Parameters đã chuẩn hóa.
- Profile version hoặc target nếu chúng làm thay đổi tài nguyên được tạo.

Một biểu thức khái niệm:

~~~text
normalized_command = validate_and_normalize(request)

request_fingerprint = SHA-256(
    canonical_json(
        platform_id,
        tenant_id,
        instance_id,
        "PROVISION",
        normalized_command
    )
)
~~~

Trong triển khai thật, cách serialize phải ổn định: thứ tự field, định dạng số, Unicode và biểu diễn null/default cần thống nhất. Chỉ đưa vào fingerprint những field ảnh hưởng đến kết quả. Không đưa timestamp request, trace ID hoặc header thay đổi theo mỗi lần retry.

Nếu parameters có secret, không lưu raw secret trong fingerprint hoặc log. Có thể loại secret khỏi dữ liệu lưu trữ nếu chúng không cần để tạo lại tài nguyên, hoặc dùng HMAC với key được quản lý an toàn khi cần so sánh tính tương đương mà không tiết lộ giá trị. Secret cần được lưu riêng trong secret manager nếu backend thực sự yêu cầu.

Fingerprint không phải bằng chứng xác thực. Broker vẫn phải xác thực platform, kiểm tra tenant ownership và quyền trên instance ở mỗi request.

## 5. Quy tắc xử lý khi cùng instance ID được gửi lại

Sau khi xác thực caller và chuẩn hóa request, broker tra cứu instance theo định danh đã quy định. Có bốn tình huống chính:

| Trạng thái bản ghi | Fingerprint | Cách xử lý |
|---|---|---|
| Chưa có instance | Chưa có | Tạo bản ghi và operation mới |
| Đã có instance, provision đang chạy | Giống | Trả thông tin operation hiện tại, không enqueue công việc tạo mới |
| Instance đã provision thành công | Giống | Trả kết quả đã lưu theo hợp đồng API, không gọi backend tạo lại |
| ID đã tồn tại | Khác | Trả lỗi conflict; không ghi đè service, plan hoặc parameters cũ |

### Request lặp khi provision đang chạy

Nếu operation trước có trạng thái `PENDING` hoặc `IN_PROGRESS`, request lặp cùng nội dung nên nhận lại cùng operation ID hoặc trạng thái tương ứng. Không tạo operation mới chỉ vì platform gửi lại HTTP request.

Điều này đặc biệt quan trọng khi backend đang tạo database mất vài phút. Nhiều request lặp không được biến thành nhiều job độc lập.

### Request lặp sau khi provision thành công

Nếu instance đã ở trạng thái `ACTIVE` và fingerprint giống bản ghi đã lưu, broker trả kết quả đã biết theo response contract của OSB API version đang triển khai. Broker không gọi lại backend provision. Nếu response trước có thông tin operation hoặc dashboard URL cần trả lại, chỉ trả các dữ liệu còn hợp lệ và được phép công bố.

### Cùng ID nhưng khác nội dung

Nếu `instance_id` đã gắn với PostgreSQL plan `production`, nhưng request mới dùng Redis hoặc plan `starter`, đây không còn là retry tương đương. Broker phải báo xung đột và giữ nguyên bản ghi cũ. Không được cập nhật service/plan hoặc tạo thêm resource dưới cùng ID.

Các khác biệt về tenant, platform scope hoặc parameters cũng cần được kiểm tra. Cùng ID từ một platform nhưng context ánh xạ sang tenant khác là tình huống ownership conflict, không phải lý do để chuyển instance sang tenant mới.

## 6. Luồng provision an toàn với transaction và outbox

Không thể bao một transaction database duy nhất quanh cả thao tác lưu trạng thái và API bên ngoài của cloud provider. Vì vậy, broker nên chia công việc thành bước ghi nhận bền vững và bước thực thi backend.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Spring Cloud Broker
    participant DB as State Store
    participant Q as Outbox Publisher / Queue
    participant W as Provision Worker
    participant R as Backend

    P->>B: PUT service_instances/{instance_id}
    B->>B: Authenticate + validate + fingerprint
    B->>DB: Transaction: insert instance, operation, outbox
    DB-->>B: Commit
    B-->>P: 202 Accepted + operation
    Q->>DB: Read unpublished outbox
    Q->>W: Publish provision command
    W->>DB: Claim operation
    W->>R: Provision with stable idempotency key
    R-->>W: Backend resource ID
    W->>DB: Save resource ID, ACTIVE, operation SUCCEEDED
    P->>B: GET last_operation
    B->>DB: Read operation state
    DB-->>B: SUCCEEDED
    B-->>P: Provision completed
~~~

Các bước:

1. Xác thực platform, xác định tenant và kiểm tra service/plan/parameters.
2. Chuẩn hóa command và tính fingerprint.
3. Mở transaction database.
4. Tạo instance record ở trạng thái ban đầu, operation record và outbox event.
5. Commit transaction.
6. Publisher chuyển event sang queue; worker nhận và xử lý.
7. Worker gọi backend bằng khóa idempotency ổn định.
8. Lưu backend resource ID và cập nhật instance/operation trong transaction.
9. Platform truy vấn trạng thái operation qua endpoint OSB tương ứng nếu provision bất đồng bộ.

Nếu broker hỗ trợ xử lý đồng bộ, vẫn nên lưu bản ghi bền vững trước khi gọi backend. Sau khi backend hoàn tất, broker cập nhật kết quả rồi mới trả response thành công. Khi không thể hoàn tất đồng bộ và request không cho phép thao tác bất đồng bộ, broker cần tuân thủ quy tắc phản hồi của OSB API thay vì tự ý trả một trạng thái không hợp lệ.

## 7. Chống request đồng thời tạo trùng

Hai request giống nhau có thể đến gần như cùng lúc. Nếu cả hai cùng thực hiện:

1. SELECT instance — chưa thấy bản ghi.
2. Gọi backend tạo database.
3. INSERT instance.

thì cả hai có thể tạo hai database trước khi một lần insert bị lỗi unique constraint.

Cách xử lý phải dựa vào cơ chế đồng bộ ở database, không chỉ dựa vào đoạn code `if (instance == null)`.

Các biện pháp thường dùng:

- Unique constraint trên khóa instance trong phạm vi đã chọn.
- Insert-first hoặc upsert có xử lý conflict.
- Transaction và row lock khi thao tác trên bản ghi hiện hữu.
- Optimistic locking với cột version cho cập nhật trạng thái.
- Unique constraint trên idempotency key hoặc operation identity.
- Worker claim job bằng cơ chế atomic để một operation không bị nhiều worker thực thi đồng thời.

### Mẫu insert-first

Một luồng khái niệm:

~~~text
BEGIN

INSERT instance(
    platform_id,
    instance_id,
    tenant_id,
    request_fingerprint,
    lifecycle_state
)
VALUES (..., 'PROVISIONING')
ON CONFLICT (platform_id, instance_id) DO NOTHING

SELECT instance
WHERE platform_id = ?
  AND instance_id = ?
FOR UPDATE

IF fingerprint matches AND operation is pending:
    return existing operation
ELSE IF fingerprint matches AND instance is active:
    return stored result
ELSE IF fingerprint differs:
    raise conflict

INSERT operation and outbox only for the newly accepted request

COMMIT
~~~

Đoạn pseudocode cần được triển khai sao cho chỉ request thắng quyền tạo mới mới được ghi operation/outbox provision. Transaction phải bảo đảm request thua cuộc đọc được bản ghi đã commit và so sánh fingerprint. Với isolation level và database cụ thể, cần xử lý retry transaction nếu gặp serialization failure hoặc deadlock.

## 8. Idempotency ở backend

Idempotency tại broker bảo vệ việc tạo instance record và operation. Nhưng nếu worker gọi backend, backend cũng có thể nhận lệnh lặp do timeout hoặc worker restart.

Một tình huống khó:

1. Worker gửi lệnh tạo database.
2. Backend tạo thành công.
3. Response backend bị mất.
4. Worker không biết resource đã được tạo hay chưa.
5. Worker retry.

Nếu backend hỗ trợ idempotency token, broker nên dùng một khóa ổn định gắn với instance và lần provision. Ví dụ:

~~~text
backend_idempotency_key =
    hash(platform_id, instance_id, provision_generation)
~~~

Cùng một operation retry phải dùng cùng khóa. Không tạo UUID mới ở mỗi lần gọi backend, vì khi đó backend sẽ xem mỗi lần retry là một yêu cầu tạo mới.

Nếu backend không hỗ trợ idempotency key, broker có thể:

- Gắn tag/label ổn định vào resource khi tạo, ví dụ `broker-instance-key`.
- Tìm resource theo tag trước khi tạo lại.
- Lưu một external correlation ID nếu backend cho phép.
- Đối soát trạng thái resource sau timeout.
- Giới hạn retry và đưa trường hợp không xác định vào trạng thái cần reconciliation.

Không có cơ chế idempotency hoặc tra cứu tương đương ở backend thì không thể bảo đảm tuyệt đối rằng một lệnh tạo tài nguyên bị timeout chưa từng được thực hiện. Broker cần biểu diễn trạng thái chưa xác định và đối soát trước khi gửi lệnh tạo lại.

## 9. Xử lý các điểm lỗi và khôi phục

Bảng sau mô tả những thời điểm broker có thể gặp sự cố:

| Điểm lỗi | Dữ liệu đã ghi | Cách khôi phục |
|---|---|---|
| Trước transaction commit | Chưa có instance/operation được xác nhận | Platform retry; broker xử lý như request mới |
| Sau commit, trước publish queue | Instance, operation và outbox đã lưu | Publisher đọc lại outbox chưa publish |
| Sau publish, trước khi worker claim | Outbox đã phát, operation còn pending | Queue redelivery hoặc dispatcher quét pending |
| Backend đã tạo resource nhưng response mất | State broker chưa có backend resource ID | Retry bằng backend idempotency key hoặc tìm resource theo tag |
| Worker lưu resource ID nhưng chết trước ACK queue | State đã có kết quả, message có thể giao lại | Worker đọc operation đã hoàn tất và không tạo lại |
| Broker lưu kết quả nhưng response HTTP bị mất | Instance đã active | Request retry nhận kết quả đã lưu |
| Backend tạo một phần rồi báo lỗi | Có thể có tài nguyên chưa được quản lý đầy đủ | Reconcile, retry bước còn thiếu hoặc compensation |

Một hệ thống bền vững cần có reconciliation job. Job này định kỳ tìm các operation quá lâu ở `PENDING`/`IN_PROGRESS`, instance `PROVISIONING` không có tiến triển hoặc resource chưa được đối chiếu. Nó có thể truy vấn backend theo external tag, cập nhật trạng thái hoặc tạo cảnh báo để xử lý thủ công.

Không nên tự động xóa resource chỉ vì broker không tìm thấy backend resource ID trong database. Resource có thể đã được tạo nhưng kết quả chưa kịp lưu. Hãy đối soát bằng correlation ID hoặc tag trước khi kết luận resource không tồn tại.

## 10. Trạng thái instance và trạng thái operation

Instance và operation biểu diễn hai khía cạnh khác nhau:

- **Instance state** mô tả vòng đời tài nguyên.
- **Operation state** mô tả tiến độ của một yêu cầu cụ thể.

Một mô hình instance state tham khảo:

~~~mermaid
stateDiagram-v2
    [*] --> PROVISIONING
    PROVISIONING --> ACTIVE
    PROVISIONING --> FAILED
    FAILED --> PROVISIONING: Retry có kiểm soát
    ACTIVE --> UPDATING
    UPDATING --> ACTIVE
    UPDATING --> FAILED
    ACTIVE --> DEPROVISIONING
    DEPROVISIONING --> DEPROVISIONED
    DEPROVISIONING --> FAILED
~~~

Operation state có thể gồm `PENDING`, `IN_PROGRESS`, `SUCCEEDED` và `FAILED`. Mỗi lần retry có thể là một lần tiếp tục cùng operation hoặc một operation mới tùy semantics được định nghĩa; điều này cần được lưu rõ.

Không dùng một field boolean như `provisioned` để thay thế state machine. Ví dụ, `provisioned=false` không cho biết request chưa từng đến, đang chạy, thất bại hay đã deprovision.

### Lưu lỗi an toàn

Operation thất bại nên lưu mã lỗi ổn định, loại lỗi, thời điểm, bước thực hiện và mô tả đã lọc. Không lưu stack trace hoặc credential vào response OSB. Log nội bộ có thể tham chiếu trace ID để tra cứu chi tiết với quyền phù hợp.

## 11. Phản hồi OSB và truy vấn last operation

Nếu provision hoàn tất đồng bộ, broker trả response thành công theo hợp đồng OSB API. Nếu cần xử lý bất đồng bộ, platform gửi `accepts_incomplete=true`; broker có thể chấp nhận công việc và trả response chứa operation token để platform truy vấn.

Ví dụ response bất đồng bộ minh họa:

~~~http
HTTP/1.1 202 Accepted
Content-Type: application/json
~~~

~~~json
{
  "operation": "op-2026-00821"
}
~~~

Platform có thể gọi endpoint trạng thái:

~~~http
GET /v2/service_instances/orders-db-prod/last_operation?service_id=svc-postgresql&plan_id=plan-postgresql-production&operation=op-2026-00821
~~~

Response minh họa:

~~~json
{
  "state": "in progress",
  "description": "Đang tạo database trên backend"
}
~~~

Khi hoàn tất:

~~~json
{
  "state": "succeeded",
  "description": "Service instance đã sẵn sàng"
}
~~~

Các giá trị response và điều kiện sử dụng `accepts_incomplete` cần tuân thủ phiên bản OSB API broker công bố. Broker phải lưu operation token và trạng thái đủ bền vững để truy vấn được sau khi process restart hoặc request HTTP ban đầu đã kết thúc.

Khi nhận request provision lặp trong lúc operation đang chạy, broker nên trả lại operation hiện có theo contract, không tạo token mới cho cùng một công việc logic. Điều này giúp platform tiếp tục polling đúng operation.

## 12. Xử lý thất bại và retry có kiểm soát

Không phải mọi lỗi đều có thể retry:

| Loại lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Lỗi đầu vào | Plan ID không hợp lệ, parameters sai | Không retry; yêu cầu sửa request |
| Lỗi quyền | Tenant không được dùng plan | Không retry cho đến khi quyền thay đổi |
| Lỗi tạm thời | Backend timeout, rate limit, mạng gián đoạn | Retry có backoff và giới hạn |
| Lỗi tài nguyên | Hết quota hoặc hết capacity | Có thể retry sau khi capacity thay đổi |
| Lỗi không xác định | Timeout sau khi backend có thể đã tạo resource | Reconcile trước khi tạo lại |
| Lỗi cấu hình | Storage class không tồn tại | Dừng và yêu cầu sửa cấu hình |

Một retry policy nên có exponential backoff, jitter, số lần thử tối đa và thời hạn tổng. Mỗi lần thử phải giữ cùng idempotency key cho cùng yêu cầu logic. Không biến lỗi permanent thành một vòng retry vô hạn.

Nếu provision tạo được một phần tài nguyên rồi thất bại, broker cần quyết định tiếp tục hoàn tất, thực hiện compensation hoặc giữ trạng thái cần can thiệp. Quyết định này phụ thuộc tính chất backend và khả năng phục hồi dữ liệu.

## 13. Khi nào được phép tạo lại sau deprovision?

Một instance có thể trải qua provision rồi deprovision. Broker cần phân biệt một request retry cũ với một yêu cầu provision mới sau khi tài nguyên trước đã được thu hồi.

Nên lưu tombstone hoặc lịch sử vòng đời đủ lâu để nhận diện ID đã từng được sử dụng. Chính sách reuse ID cần được xác định rõ theo hợp đồng platform:

- Nếu ID không được tái sử dụng, request mới với ID đã deprovision cần bị từ chối hoặc xử lý theo quy tắc API.
- Nếu broker cho phép reuse, phải xác nhận operation deprovision cũ đã hoàn tất, resource cũ đã được đối soát/xóa và tạo một generation mới.
- Không trả lại kết quả provision cũ như thể tài nguyên vẫn active.
- Không để worker cũ tiếp tục tạo resource sau khi generation mới đã bắt đầu.

Có thể lưu `provision_generation` hoặc `lifecycle_epoch` tăng theo mỗi vòng đời được phép. Backend idempotency key sẽ bao gồm generation để phân biệt lần cấp phát mới với lần retry của generation cũ.

## 14. Triển khai trong Spring Cloud Service Broker

Spring Cloud Service Broker cung cấp các abstraction cho service instance lifecycle và response của các thao tác OSB API. Ứng dụng có thể đặt persistence, idempotency và backend orchestration trong lớp nghiệp vụ riêng.

Một cấu trúc tham khảo:

~~~text
broker/
  instance/
    ServiceInstanceController
    ServiceInstanceService
    ServiceInstanceRepository
    ProvisionRequestFingerprint
  operation/
    BrokerOperation
    OperationRepository
    OperationStatusService
  messaging/
    OutboxEvent
    OutboxPublisher
    ProvisionWorker
  backend/
    ResourceProvisioner
    BackendResourceLookup
  persistence/
    ServiceInstanceEntity
    OperationEntity
    OutboxEntity
~~~

Handler provision nên tập trung vào tiếp nhận request và chuyển qua service nghiệp vụ:

~~~java
public ProvisionResult provision(
        ProvisionCommand command,
        AuthenticatedPlatform platform) {

    NormalizedProvisionRequest normalized =
        requestNormalizer.normalize(command, platform);

    return transactionTemplate.execute(status ->
        provisionCoordinator.acceptOrReplay(normalized)
    );
}
~~~

Coordinator xử lý tạo mới hoặc replay:

~~~java
public ProvisionResult acceptOrReplay(
        NormalizedProvisionRequest request) {

    String fingerprint = fingerprintService.calculate(request);

    Optional<ServiceInstance> existing =
        instanceRepository.findByPlatformAndInstanceId(
            request.platformId(),
            request.instanceId()
        );

    if (existing.isPresent()) {
        ServiceInstance instance = existing.get();

        if (!instance.requestFingerprint().equals(fingerprint)) {
            throw new InstanceConflictException(
                "The instance ID is already associated with another request");
        }

        return resultMapper.fromExisting(instance);
    }

    return createPendingInstanceAndOutbox(request, fingerprint);
}
~~~

Đây là pseudocode minh họa. Trong triển khai thật, truy vấn trước rồi insert có thể gặp race condition. Cần dựa vào unique constraint và xử lý vi phạm unique/insert conflict trong transaction để bảo đảm chỉ một request thắng quyền tạo mới. Không gọi backend bên trong transaction database dài; worker xử lý sau khi transaction ghi nhận request đã commit.

Worker cần kiểm tra trạng thái operation trước khi gọi backend:

~~~java
public void processProvision(String operationId) {
    BrokerOperation operation = operationRepository
        .claimPending(operationId)
        .orElse(null);

    if (operation == null) {
        return;
    }

    ProvisionedResource resource = provisioner.provision(
        operation.resourceSpecification(),
        operation.backendIdempotencyKey()
    );

    transactionTemplate.executeWithoutResult(status -> {
        instanceRepository.markActive(
            operation.instanceId(),
            resource.provider(),
            resource.resourceId()
        );
        operationRepository.markSucceeded(operationId);
    });
}
~~~

Các tên lớp và phương thức trong ví dụ là thiết kế gợi ý, không phải API cố định của thư viện. `claimPending` cần atomic hoặc dùng lock/lease để tránh nhiều worker cùng xử lý một operation. Nếu worker bị dừng sau khi backend tạo resource nhưng trước khi lưu kết quả, lần chạy lại phải dùng cùng backend idempotency key hoặc đối soát resource trước khi gọi tạo mới.

## 15. Bảo mật dữ liệu provision được lưu

Bản ghi provision thường chứa thông tin về tenant, cấu hình dịch vụ và tài nguyên backend. Cần áp dụng quyền truy cập theo vai trò:

- Platform chỉ được truy vấn instance và operation thuộc phạm vi đã xác thực.
- Tenant không được dùng `instance_id` để đọc dữ liệu của tenant khác.
- Backend credential được lưu trong secret manager hoặc kho mã hóa; không ghi vào JSON snapshot.
- Parameters được lưu theo allowlist và loại bỏ secret hoặc dữ liệu không cần thiết.
- Error description được lọc trước khi trả cho platform.
- Log/audit không chứa password, token, private key hoặc connection string có credential.
- Quyền quản trị và thao tác reconciliation phải có audit trail.

Không trả backend resource ID hoặc metadata nội bộ trong response nếu hợp đồng OSB không yêu cầu. Response provision chỉ nên chứa thông tin mà platform được phép nhận.

## 16. Quan sát và reconciliation

Broker cần đo lường khả năng xử lý request lặp và phát hiện resource bị lệch trạng thái.

Metric hữu ích:

- Số provision mới, số request được replay và số conflict.
- Số instance ở `PROVISIONING` quá thời hạn.
- Số operation pending/in progress và tuổi của operation lâu nhất.
- Tỷ lệ backend timeout và số lần retry.
- Số resource được tìm thấy qua reconciliation nhưng chưa có backend ID trong state store.
- Số instance có trạng thái backend khác trạng thái broker.
- Thời gian từ lúc nhận request đến khi instance active.

Audit nên ghi platform ID, tenant ID, instance ID, operation ID, fingerprint hoặc mã tham chiếu an toàn, kết quả và timestamp. Không đưa toàn bộ request parameters vào metric label vì có thể chứa dữ liệu nhạy cảm hoặc làm cardinality tăng mạnh.

Reconciliation job có thể:

1. Tìm operation quá hạn.
2. Đọc instance và operation liên quan.
3. Tra cứu backend theo resource ID hoặc correlation tag.
4. So sánh trạng thái backend với state store.
5. Cập nhật kết quả nếu có bằng chứng rõ ràng.
6. Đưa trường hợp không xác định vào hàng đợi xử lý hoặc cảnh báo.
7. Ghi audit cho mọi hành động sửa trạng thái.

Reconciliation không nên tự động xóa tài nguyên chỉ dựa trên một lần truy vấn thất bại. Cần phân biệt backend không truy cập được với resource thực sự không tồn tại.

## 17. Kiểm thử lưu kết quả và request lặp

Bộ kiểm thử nên bao phủ cả retry tuần tự, request đồng thời và crash recovery.

| Trường hợp | Tình huống | Kết quả mong đợi |
|---|---|---|
| Provision lần đầu | Instance ID chưa tồn tại | Tạo một instance record và một operation |
| Retry khi đang chạy | Cùng ID và fingerprint, operation pending | Trả operation cũ, không tạo job mới |
| Retry sau thành công | Cùng ID và fingerprint, instance active | Trả kết quả đã lưu, không gọi backend |
| Cùng ID, service khác | Request mới đổi service ID | Conflict, giữ bản ghi cũ |
| Cùng ID, plan khác | Request mới đổi plan ID | Conflict, không provision lần hai |
| Cùng ID, parameters khác | Request mới đổi cấu hình có ý nghĩa | Conflict theo fingerprint |
| Tenant khác | Cùng chuỗi ID nhưng caller không có ownership | Không tiết lộ hoặc truy cập instance khác |
| Hai request đồng thời | Cùng platform/ID/fingerprint | Chỉ một lần tạo mới; request còn lại replay |
| Hai request đồng thời khác fingerprint | Cùng ID nhưng nội dung khác | Một request thắng; request kia conflict |
| Commit trước publish | Broker chết sau transaction | Outbox publisher phát lại event |
| Backend thành công, response mất | Worker timeout sau create | Retry/reconcile không tạo resource trùng |
| Worker giao message hai lần | Queue redelivery | Backend không tạo thêm resource |
| Profile thay đổi | Cấu hình mới được deploy khi job cũ chờ | Worker dùng snapshot đã lưu |
| Deprovision đang chạy | Request provision lặp đến | Áp dụng policy trạng thái, không tạo resource song song |
| Reuse sau deprovision | ID được dùng lại theo policy | Generation mới và backend key mới |
| Lỗi permanent | Parameters không hợp lệ | Không retry backend |

Cần có integration test với database thật hoặc Testcontainers để xác minh unique constraint và transaction dưới tải đồng thời. Mock đơn thuần không chứng minh được race condition ở tầng lưu trữ. Với backend, dùng adapter giả lập có khả năng tạo resource rồi làm mất response để kiểm tra recovery.

## 18. Những lỗi thiết kế thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra instance bằng câu lệnh SELECT | Hai request đồng thời có thể cùng tạo tài nguyên | Unique constraint và insert-first |
| Gọi backend trước khi lưu request | Broker crash có thể làm mất dấu tài nguyên đã tạo | Persist operation trước khi thực thi |
| Tạo operation mới cho mỗi retry | Nhiều worker cùng provision một instance | Fingerprint và replay operation cũ |
| Chỉ lưu `provisioned=true` | Không biết trạng thái pending, failed hay deprovisioning | State machine và operation history |
| Dùng UUID mới cho mỗi backend retry | Backend xem retry là resource mới | Stable backend idempotency key |
| Coi timeout là backend chưa chạy | Tạo tài nguyên trùng sau retry | Reconcile bằng idempotency key/tag |
| Ghi đè plan khi cùng ID được gửi khác nội dung | Mất ownership và lịch sử cấu hình | Conflict nếu fingerprint khác |
| Lưu secret trong parameters snapshot | Lộ credential qua database/log | Secret manager và redaction |
| Không có outbox | Operation pending nhưng job bị thất lạc | Transactional outbox |
| Không đối soát operation treo | Instance có thể mắc kẹt mãi ở provisioning | Reconciliation và cảnh báo |
| Xóa tombstone quá sớm | Request cũ có thể bị hiểu thành provision mới | Retention và generation policy |

## 19. Nguyên tắc cần ghi nhớ

Một request provision có thể được gửi nhiều lần, nhưng một yêu cầu logic chỉ nên tạo ra một kết quả tài nguyên được quản lý. Broker đạt được điều đó bằng cách lưu định danh và fingerprint của request, ghi operation bền vững trước khi gọi backend, kiểm soát cạnh tranh bằng transaction/unique constraint và sử dụng idempotency ở backend.

Khi xây dựng bằng Spring Cloud Service Broker, hãy giữ các nguyên tắc sau:

- Định danh platform, tenant và instance phải được xác minh trước khi tra cứu.
- Lưu service ID, plan ID, request fingerprint, ownership, lifecycle state và backend resource ID.
- Chuẩn hóa request trước khi tính fingerprint.
- Cùng ID và cùng nội dung thì replay operation hoặc kết quả đã lưu.
- Cùng ID nhưng nội dung hoặc ownership khác thì báo conflict.
- Dùng transaction cùng outbox để không làm thất lạc công việc bất đồng bộ.
- Dùng unique constraint và cơ chế claim để chống request/worker đồng thời.
- Dùng backend idempotency key hoặc reconciliation tag để xử lý timeout không xác định.
- Giữ operation history, snapshot cấu hình và tombstone theo chính sách vòng đời.
- Không lưu hoặc trả lộ secret trong kết quả provision.

Khi các quy tắc này được áp dụng xuyên suốt, platform có thể retry an toàn sau timeout, broker có thể phục hồi sau restart và backend không bị tạo tài nguyên trùng chỉ vì một response bị thất lạc.

