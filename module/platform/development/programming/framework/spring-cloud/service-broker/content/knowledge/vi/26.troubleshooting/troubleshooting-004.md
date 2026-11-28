# Cấp phát bị gọi lặp và tài nguyên đã tồn tại bên nhà cung cấp

Trong một service broker, yêu cầu provision có thể được gửi lại khi platform không nhận được response, kết nối bị timeout hoặc người vận hành chạy lại thao tác. Đồng thời, provider có thể đã tạo database, bucket, queue hay namespace ở lần gọi trước. Nếu broker xử lý lần gọi tiếp theo như một yêu cầu hoàn toàn mới, nó có thể tạo tài nguyên trùng, nhận lỗi "already exists", hoặc lưu trạng thái không khớp với tài nguyên thực tế.

Với **SPRING_CLOUD_SERVICE_BROKER**, đây là sự cố quan trọng vì Open Service Broker API (OSB API) yêu cầu broker xử lý vòng đời service instance một cách idempotent. Spring Cloud Open Service Broker (SCOSB) cung cấp request/response model và service abstraction; ứng dụng broker chịu trách nhiệm định danh instance, lưu operation, điều phối provider call và khôi phục khi kết quả không chắc chắn.

Bài học này giúp phân biệt request lặp với tài nguyên mồ côi, chẩn đoán lỗi provider báo tài nguyên đã tồn tại, thiết kế idempotency ở broker và provider, xử lý race condition, reconciliation sau timeout, khôi phục trạng thái database và kiểm thử các tình huống cấp phát lặp.

## 1. Nhận diện triệu chứng

Một số dấu hiệu thường gặp:

- Platform gửi nhiều lần PUT provision cho cùng một service instance ID.
- Broker log ghi nhiều lần bắt đầu provision cho cùng một instance.
- Provider trả lỗi như ResourceAlreadyExists, AlreadyExists, DuplicateName hoặc HTTP 409.
- Database broker không có instance record nhưng provider đã có resource.
- Database có instance ở trạng thái PROVISIONING lâu bất thường.
- Có nhiều provider resource mang tên gần giống nhau cho cùng một yêu cầu.
- Platform polling last_operation nhưng operation không tiến triển.
- Worker retry tạo tài nguyên mới dù lần gọi trước có thể đã thành công.
- Provision response bị timeout, trong khi provider console cho thấy resource đã được tạo.
- Một instance record trỏ tới provider resource ID không còn tồn tại.

Không nên kết luận ngay rằng provider bị lỗi chỉ vì response có chữ "already exists". Có thể đây là request lặp hợp lệ, một lần chạy trước đã thành công nhưng broker chưa ghi nhận kết quả, hai worker chạy đồng thời, hoặc tài nguyên tồn tại từ một hệ thống khác.

## 2. Phân biệt bốn tình huống

Cần phân loại tình huống trước khi retry hoặc can thiệp tài nguyên.

| Tình huống | Broker database | Provider | Cách xử lý |
|---|---|---|---|
| Request lặp cùng nội dung | Instance và operation đã có | Resource đã tồn tại và thuộc instance | Trả kết quả idempotent hoặc trạng thái operation hiện tại |
| Provider tạo xong, broker chưa lưu kết quả | Instance/operation đang tạo hoặc thiếu provider ID | Resource đã tồn tại và có ownership marker phù hợp | Reconcile rồi gắn provider resource ID vào instance |
| Hai worker cùng provision | Một operation hoặc hai attempt cạnh tranh | Hai create call có thể chạy gần nhau | Claim/lock và provider idempotency; không tạo side effect lần hai |
| Resource có trước, không thuộc broker | Không có mapping hợp lệ | Resource trùng tên/ID nhưng owner khác hoặc không rõ | Báo conflict; không tự nhận quyền sở hữu hay xóa resource |

Hai khái niệm dễ nhầm:

**Request lặp (duplicate request)** là cùng một yêu cầu nghiệp vụ được gửi lại do retry, timeout hoặc client gửi lại. Nếu dữ liệu có ý nghĩa nghiệp vụ giống nhau và instance ID giống nhau, broker phải xử lý như cùng một lần provision.

**Tài nguyên đã tồn tại (pre-existing resource)** là một resource provider có trước lần provision hiện tại. Nó có thể thuộc chính broker do lần chạy trước, thuộc một instance khác, hoặc do người vận hành/hệ thống khác tạo. Chỉ trường hợp xác minh được ownership và cấu hình mới có thể được reconcile an toàn.

## 3. OSB API yêu cầu idempotency ở đâu?

Provision của OSB API dùng request PUT theo service instance ID:

~~~http
PUT /v2/service_instances/{instance_id}?accepts_incomplete=true
Content-Type: application/json
X-Broker-API-Version: 2.17
~~~

Request thường mang service ID, plan ID, parameters và context. Platform có thể gửi lại cùng request nếu response trước bị mất hoặc không xác định được.

Broker cần bảo đảm:

- Cùng instance ID và cùng nội dung nghiệp vụ không tạo thêm provider resource.
- Request lặp trong khi operation đang chạy không khởi động một operation độc lập.
- Request lặp sau khi provision thành công trả lại kết quả hiện tại theo contract OSB API.
- Cùng instance ID nhưng service, plan hoặc parameters xung đột phải được phát hiện.
- Retry sau timeout phải xác định kết quả lần gọi trước trước khi tạo side effect mới.

Với provision đồng bộ, response lần đầu thường là **201 Created**. Với xử lý bất đồng bộ được chấp nhận, broker trả **202 Accepted** cùng operation identifier. Với request lặp tương đương, broker trả response thành công idempotent theo quy định của phiên bản OSB API; request xung đột với instance đã tồn tại phải được xử lý theo conflict contract, thường là **409 Conflict**.

Không dùng HTTP status để thay thế việc kiểm tra state. Response 202 chỉ nói broker đã nhận operation; nó không chứng minh provider đã tạo xong tài nguyên.

## 4. Xác định khóa định danh của một yêu cầu provision

Không dùng tên resource provider làm khóa idempotency duy nhất. Một tên như **orders-db** có thể được tái sử dụng ở tenant khác, account khác hoặc region khác.

Một định danh nội bộ thường kết hợp:

- Platform hoặc broker registration nếu broker phục vụ nhiều platform.
- Service instance ID do OSB platform gửi.
- Tenant/organization reference đã được xác thực.
- Service ID và plan ID.
- Provider account/region hoặc target đã được policy chọn.
- Operation ID và request fingerprint.

Ví dụ:

~~~text
platform_id = cf-prod
tenant_id = org-42
instance_id = 6bcb...
service_id = svc-postgresql
plan_id = plan-standard
provider_account = aws-account-a
region = ap-southeast-1
~~~

Trong database, có thể dùng unique constraint trên khóa instance phù hợp với phạm vi triển khai:

~~~sql
CREATE TABLE broker_service_instance (
    platform_id VARCHAR(64) NOT NULL,
    instance_id VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL,
    service_id VARCHAR(128) NOT NULL,
    plan_id VARCHAR(128) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    provider_resource_id VARCHAR(256),
    state VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (platform_id, instance_id)
);
~~~

Nếu một broker chỉ phục vụ một platform và OSB instance ID đã duy nhất trong phạm vi đó, schema có thể đơn giản hơn. Hãy chọn khóa theo phạm vi định danh thực tế và bảo đảm unique constraint được database thực thi, không chỉ kiểm tra bằng code.

## 5. Tạo request fingerprint ổn định

Để xác định request lặp hay xung đột, broker có thể tạo fingerprint từ các trường nghiệp vụ có ý nghĩa:

- Service ID.
- Plan ID.
- Parameters sau khi validate và chuẩn hóa.
- Context field có ảnh hưởng đến việc chọn provider hoặc tạo tài nguyên.
- Provider target đã được broker xác định.
- Phiên bản schema hoặc cấu hình provisioning nếu cần.

Ví dụ dữ liệu trước khi tính fingerprint:

~~~json
{
  "service_id": "svc-postgresql",
  "plan_id": "plan-standard",
  "parameters": {
    "storage_gb": 100,
    "region": "ap-southeast-1"
  },
  "provider_target": "aws-account-a/ap-southeast-1"
}
~~~

Cần canonicalize JSON để thứ tự key không làm thay đổi fingerprint. Ví dụ hai payload có thứ tự field khác nhau nhưng cùng giá trị nghiệp vụ phải cho cùng fingerprint.

Không đưa các trường không có ý nghĩa đối với provisioning vào fingerprint, như request timestamp hoặc trace ID. Nếu platform thay đổi metadata không ảnh hưởng resource, broker không nên coi đó là một provision khác.

Nếu parameters có secret, không lưu plaintext trong fingerprint. Có thể dùng HMAC với key quản lý riêng để tạo digest an toàn hơn hash thường; tuyệt đối không log raw parameters. Fingerprint cần có version để thay đổi quy tắc canonicalization không làm broker so sánh sai dữ liệu cũ.

## 6. Quy trình xử lý request lặp tại broker

Một luồng xử lý an toàn:

1. Xác thực request và kiểm tra service/plan.
2. Validate parameters và tính fingerprint.
3. Thử insert instance cùng operation trong transaction database.
4. Nếu insert thành công, ghi outbox event trong cùng transaction.
5. Nếu vi phạm unique constraint, đọc instance hiện có.
6. So sánh tenant, service, plan và fingerprint.
7. Nếu cùng yêu cầu, trả kết quả idempotent hoặc operation hiện tại.
8. Nếu dữ liệu xung đột, trả conflict theo contract.
9. Worker chỉ xử lý operation đã được claim hợp lệ.

Sơ đồ:

~~~mermaid
flowchart TD
    A["OSB provision request"] --> B["Validate and fingerprint"]
    B --> C["Insert instance + operation + outbox"]
    C --> D{"Insert succeeds?"}
    D -->|Yes| E["Commit and return accepted/success"]
    E --> F["Worker provisions provider resource"]
    D -->|Unique conflict| G["Load existing instance"]
    G --> H{"Same tenant and fingerprint?"}
    H -->|Yes| I{"Operation state"}
    I -->|QUEUED / RUNNING| J["Return current operation"]
    I -->|SUCCEEDED| K["Return idempotent success"]
    I -->|FAILED| L["Apply retry/recovery policy"]
    H -->|No| M["Return conflict"]
~~~

Điểm quan trọng là kiểm tra unique constraint ở database. Cách làm "SELECT trước, rồi INSERT" mà không có constraint vẫn có race condition: hai request đồng thời đều thấy chưa có record và cùng tạo mới.

## 7. Xử lý request trùng trong từng trạng thái

Cùng một request lặp có thể đến khi instance đang ở các trạng thái khác nhau.

| Instance/operation state | Hành vi với request cùng fingerprint |
|---|---|
| Chưa có record | Tạo instance và operation mới |
| QUEUED | Không tạo operation thứ hai; trả trạng thái đã nhận |
| CLAIMED/PROVISIONING | Không gọi provider lần nữa; trả operation hiện tại |
| WAITING_PROVIDER | Trả operation đang chờ provider |
| SUCCEEDED/READY | Trả kết quả provision đã có theo OSB contract |
| FAILED rõ ràng, chưa có side effect | Có thể cho phép retry theo policy và idempotency |
| FAILED nhưng kết quả provider chưa rõ | Reconcile trước khi retry |
| RECONCILIATION_REQUIRED | Không tạo operation mới; tiếp tục đối chiếu |

Không được tự động chuyển FAILED sang QUEUED nếu không biết provider đã tạo resource hay chưa. Nếu lần gọi provider timeout sau khi server provider đã nhận request, kết quả có thể là "thành công nhưng response bị mất".

## 8. Phân biệt resource collision và resource do lần chạy trước tạo

Provider trả AlreadyExists không cho biết resource thuộc ai. Broker cần xác minh bằng metadata hoặc truy vấn provider.

Khi tạo resource, nên gắn ownership marker do broker quản lý, ví dụ:

~~~text
managed_by = spring-cloud-service-broker
broker_instance_id = 6bcb...
broker_operation_id = provision-op-100
tenant_reference = org-42
service_id = svc-postgresql
plan_id = plan-standard
~~~

Với Kubernetes, có thể dùng labels/annotations. Với cloud resource, dùng tags hoặc metadata được provider hỗ trợ. Không đưa password, token hoặc dữ liệu cá nhân vào tag.

Khi provider báo resource đã tồn tại:

1. Tìm resource theo external ID hoặc ownership marker ổn định.
2. Đọc metadata của resource.
3. Xác minh broker identity, tenant, instance ID và service.
4. So sánh cấu hình quan trọng với request hiện tại.
5. Xác định resource thuộc operation hiện tại, một attempt trước hay hệ thống khác.
6. Chỉ adopt/reconcile khi ownership và trạng thái được xác minh.
7. Nếu không xác minh được, giữ conflict để người vận hành xử lý.

Không chỉ kiểm tra tên resource trùng. Một resource có cùng tên nhưng thuộc tenant khác không phải tài nguyên để broker tự động nhận.

## 9. Thiết kế provider idempotency key

Nếu provider API hỗ trợ idempotency token, hãy gửi một key ổn định cho cùng một operation:

~~~text
idempotency_key = broker_id + platform_id + instance_id + operation_type
~~~

Với một provision operation, mọi retry phải dùng cùng key. Không tạo UUID mới ở mỗi lần gọi provider vì như vậy provider coi mỗi lần retry là một yêu cầu mới.

Provider idempotency key nên được tạo từ dữ liệu ổn định, giới hạn độ dài theo API provider và không chứa secret. Lưu key cùng operation để worker sau restart có thể dùng lại.

Ví dụ payload nội bộ:

~~~json
{
  "operation_id": "provision-op-100",
  "instance_id": "6bcb...",
  "provider_idempotency_key": "broker-cf-prod-6bcb-provision",
  "attempt": 3
}
~~~

Số attempt thay đổi, nhưng provider idempotency key không thay đổi giữa các lần retry của cùng operation.

Nếu provider không hỗ trợ idempotency token, broker cần dùng external reference ổn định, resource tag hoặc truy vấn theo ownership marker để xác định resource đã được tạo chưa trước khi gọi create lần nữa.

## 10. Provider timeout sau khi tạo resource

Đây là tình huống khó nhất:

1. Worker gửi create request.
2. Provider tạo thành công resource.
3. Response provider bị mất hoặc worker timeout.
4. Broker chưa lưu provider resource ID.
5. Queue giao lại message hoặc worker retry.
6. Provider trả AlreadyExists.

Broker không nên coi AlreadyExists là thất bại cuối cùng ngay lập tức. Cần chuyển sang reconciliation:

~~~mermaid
sequenceDiagram
    participant W as Broker worker
    participant P as Provider
    participant DB as Broker database

    W->>P: Create resource with stable idempotency key
    P->>P: Resource created
    P--xW: Response lost / timeout
    W->>DB: Mark outcome uncertain
    Note over W,DB: Retry/reconciliation starts
    W->>P: Lookup by idempotency key or ownership marker
    P-->>W: Existing resource metadata
    W->>W: Verify owner, tenant and configuration
    W->>DB: Save provider resource ID and READY state
~~~

Các bước reconciliation:

- Dùng provider operation ID hoặc idempotency key để tra cứu nếu có.
- Nếu không có, tìm theo ownership marker duy nhất.
- Kiểm tra trạng thái provisioning của resource.
- Nếu resource còn đang tạo, tiếp tục poll.
- Nếu resource đã sẵn sàng và thuộc đúng instance, ghi mapping và hoàn tất operation.
- Nếu resource không tồn tại, mới xem xét gửi create lại.
- Nếu có resource nhưng ownership/configuration không khớp, đánh dấu conflict cần xử lý.

Không dùng tên resource chung để tìm kiếm nếu tên đó không bảo đảm duy nhất trong account hoặc tenant.

## 11. Transaction boundary giữa broker database và provider

Database broker và provider thường không nằm trong cùng transaction ACID. Không thể rollback cloud resource chỉ bằng cách rollback database.

Một mẫu phù hợp:

- Transaction A: tạo instance, operation và outbox.
- Worker: gọi provider ngoài transaction.
- Transaction B: lưu provider resource ID, state và operation result.
- Nếu kết quả provider không chắc chắn: ghi RECONCILIATION_REQUIRED để worker khác tra cứu tiếp.

Ví dụ bảng operation:

~~~sql
CREATE TABLE broker_operation (
    operation_id VARCHAR(128) PRIMARY KEY,
    platform_id VARCHAR(64) NOT NULL,
    instance_id VARCHAR(128) NOT NULL,
    operation_type VARCHAR(32) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    provider_idempotency_key VARCHAR(256) NOT NULL,
    state VARCHAR(32) NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    provider_resource_id VARCHAR(256),
    last_error_code VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Không giữ database transaction mở trong suốt provider call. Transaction dài có thể giữ lock, làm cạn connection pool và tăng deadlock. Hãy lưu checkpoint trước/sau side effect bằng các transaction ngắn.

## 12. Ngăn hai request hoặc hai worker cùng tạo resource

Có thể có hai kiểu cạnh tranh:

**Request race:** platform gửi hai PUT gần như đồng thời cho cùng instance ID.

**Worker race:** queue giao cùng message nhiều lần, hoặc lease hết hạn khiến worker thứ hai bắt đầu trong khi worker đầu chưa dừng.

Biện pháp ở broker:

- Unique constraint cho instance key.
- Transaction và conditional update khi claim operation.
- Lease có thời hạn và heartbeat.
- Version hoặc fencing token để worker cũ không ghi đè kết quả worker mới.
- Một operation đang chạy chỉ có một owner hợp lệ.
- Consumer idempotency khi nhận queue message lặp.

Ví dụ claim bằng conditional update:

~~~sql
UPDATE broker_operation
SET state = 'CLAIMED',
    worker_id = :worker_id,
    lease_until = now() + interval '60 seconds',
    version = version + 1,
    updated_at = now()
WHERE operation_id = :operation_id
  AND state IN ('QUEUED', 'RETRYABLE')
  AND (lease_until IS NULL OR lease_until < now());
~~~

Worker chỉ tiếp tục khi update thành công đúng một row. Khi lease hết hạn, worker mới phải kiểm tra provider state trước khi lặp side effect. Fencing/version phải được kiểm tra ở các lần ghi database để worker cũ không ghi kết quả muộn.

## 13. Khi provider không hỗ trợ idempotency

Một số provider không nhận idempotency key hoặc không cho tra cứu resource theo request token. Khi đó, broker phải tăng khả năng tự đối chiếu:

- Tạo external resource name có định danh ổn định, nếu provider cho phép.
- Gắn ownership tags/labels/annotations.
- Lưu operation ID trong metadata resource nếu provider hỗ trợ.
- Truy vấn danh sách resource theo marker trước khi create.
- Dùng provider resource ID ngay khi nhận được và lưu nhanh.
- Giới hạn concurrency theo instance/provider account.
- Dùng reconciliation job cho các operation có kết quả không chắc chắn.

Nếu provider không hỗ trợ marker và không có API tra cứu đáng tin cậy, không thể bảo đảm loại bỏ hoàn toàn duplicate side effect chỉ bằng logic broker. Cần chọn một chiến lược có kiểm soát: serialize create theo khóa, sử dụng tên resource duy nhất, hoặc chuyển trường hợp không rõ kết quả sang manual reconciliation. Không tuyên bố exactly-once nếu provider không cung cấp cơ chế cần thiết.

## 14. Resource tồn tại từ trước nhưng không có broker mapping

Có thể provider resource được tạo thủ công trước khi broker quản lý service instance. Khi broker provision với tên tương tự, provider trả AlreadyExists nhưng database broker không có record.

Trước khi adopt resource, cần xác minh:

- Resource có marker managed_by đúng broker không?
- Tenant và account có khớp với request không?
- Resource có thuộc instance ID này không?
- Service type và plan có tương thích không?
- Cấu hình quan trọng như region, storage, network và encryption có khớp không?
- Broker có được phép quản lý resource đã tạo bên ngoài không?
- Việc adopt có được hỗ trợ bởi chính sách và contract sản phẩm không?

Nếu tất cả điều kiện xác minh đạt và sản phẩm cho phép import/adopt, tạo mapping có audit và lưu nguồn gốc resource. Nếu không, trả conflict hoặc chuyển sang quy trình import có phê duyệt. Không tự động adopt chỉ vì tên resource giống nhau.

## 15. Không xóa resource chỉ để làm cho retry thành công

Khi gặp AlreadyExists, một cách xử lý nguy hiểm là xóa resource hiện có rồi tạo lại. Điều này có thể làm mất dữ liệu production hoặc phá binding của instance khác.

Chỉ được xóa resource khi:

- Ownership đã được xác minh.
- Resource được tạo bởi operation hiện tại hoặc một attempt thuộc cùng instance.
- Chính sách cho phép compensation.
- Không có consumer hoặc binding đang sử dụng.
- Có checkpoint và audit cho hành động xóa.
- Có phương án phục hồi dữ liệu nếu resource chứa dữ liệu quan trọng.

Nếu resource thuộc tenant khác hoặc không xác định được owner, không xóa. Nếu resource do lần chạy trước của chính operation tạo ra, ưu tiên reconcile/adopt thay vì xóa và tạo lại.

## 16. Chẩn đoán bằng log, operation và provider metadata

Khi điều tra, cần nối được một request OSB với operation và provider call.

Các trường log hữu ích:

~~~text
event=provision_attempt
platform_id=cf-prod
instance_id=6bcb...
operation_id=provision-op-100
request_fingerprint=v2:...
provider_account=aws-account-a
provider_idempotency_key=broker-cf-prod-6bcb-provision
attempt=3
provider_result=ALREADY_EXISTS
correlation_id=trace-91a2
~~~

Không ghi raw parameters, password, token hoặc toàn bộ provider request body. Nếu fingerprint được tạo từ dữ liệu nhạy cảm, log digest đã giới hạn quyền hoặc một identifier đã mask theo policy.

Khi điều tra, thu thập:

1. Request ID/correlation ID của platform.
2. Instance ID, service ID và plan ID.
3. Operation ID và lịch sử state transition.
4. Request fingerprint và phiên bản canonicalization.
5. Attempt count, worker ID, lease và thời điểm retry.
6. Provider idempotency key hoặc external reference.
7. Provider resource ID và ownership metadata.
8. Error code, HTTP status và thời điểm provider trả lỗi.
9. Database row và outbox/queue delivery history.

Không chỉ nhìn log dòng cuối. Cần xác định thứ tự thời gian: provider đã tạo resource trước hay sau khi broker ghi operation? Worker nào giữ lease? Có response bị timeout không?

## 17. Cây quyết định xử lý AlreadyExists

Có thể áp dụng trình tự sau:

~~~mermaid
flowchart TD
    A["Provider trả AlreadyExists"] --> B["Lookup resource by stable ID/marker"]
    B --> C{"Resource found?"}
    C -->|No| D["Check provider consistency / retry lookup"]
    D --> E{"Still absent?"}
    E -->|Yes| F["Retry create with same idempotency key"]
    E -->|No| G["Continue verification"]
    C -->|Yes| G
    G --> H{"Ownership matches this broker instance?"}
    H -->|No| I["Conflict / manual review"]
    H -->|Yes| J{"Configuration and state match?"}
    J -->|No| K["Reconcile or report conflict"]
    J -->|Yes| L["Adopt mapping and complete operation"]
~~~

Cây quyết định không nên rút gọn thành "AlreadyExists = success". Chỉ khi resource được xác minh thuộc đúng broker instance và cấu hình phù hợp mới có thể hoàn tất operation như thành công.

## 18. Phục hồi operation sau lỗi

Một operation có thể đi qua các trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> QUEUED
    QUEUED --> CLAIMED
    CLAIMED --> PROVISIONING
    PROVISIONING --> SUCCEEDED: Provider confirmed and mapping saved
    PROVISIONING --> RETRYABLE: Safe transient failure
    PROVISIONING --> RECONCILIATION_REQUIRED: Outcome uncertain / AlreadyExists
    RETRYABLE --> QUEUED
    RECONCILIATION_REQUIRED --> PROVISIONING: Resource verified and resume
    RECONCILIATION_REQUIRED --> SUCCEEDED: Existing resource adopted safely
    RECONCILIATION_REQUIRED --> FAILED: Confirmed unrecoverable conflict
~~~

Phân biệt:

- **RETRYABLE:** biết chắc bước trước chưa tạo side effect hoặc provider idempotency bảo đảm retry an toàn.
- **RECONCILIATION_REQUIRED:** kết quả lần trước không rõ, cần tra cứu provider trước khi làm lại.
- **FAILED:** đã xác định lỗi kết thúc và không còn bước tự phục hồi hợp lệ.
- **SUCCEEDED:** provider resource đã được xác minh và broker đã lưu mapping/state.

Không chuyển RECONCILIATION_REQUIRED sang QUEUED một cách mù quáng. Worker phải chạy lookup hoặc reconciliation step trước.

## 19. Ví dụ application service trong Spring

Ví dụ pseudocode minh họa cách xử lý request provision lặp bằng repository và fingerprint:

~~~java
import reactor.core.publisher.Mono;

public class ProvisionApplicationService {

    private final InstanceRepository instanceRepository;
    private final OperationRepository operationRepository;
    private final OutboxRepository outboxRepository;
    private final RequestFingerprint fingerprint;

    public Mono<ProvisionDecision> accept(ProvisionCommand command) {
        String requestHash = fingerprint.of(command);

        return instanceRepository.insertIfAbsent(
                        command.platformId(),
                        command.instanceId(),
                        command.tenantId(),
                        command.serviceId(),
                        command.planId(),
                        requestHash)
                .flatMap(inserted -> {
                    if (inserted) {
                        return operationRepository.createQueued(
                                        command, requestHash)
                                .flatMap(operation ->
                                        outboxRepository.insertProvisionRequested(
                                                        operation.operationId())
                                                .thenReturn(
                                                        ProvisionDecision.accepted(operation)));
                    }

                    return instanceRepository.find(
                                    command.platformId(),
                                    command.instanceId())
                            .flatMap(existing -> {
                                if (!existing.matches(
                                        command.tenantId(),
                                        command.serviceId(),
                                        command.planId(),
                                        requestHash)) {
                                    return Mono.just(
                                            ProvisionDecision.conflict());
                                }

                                return operationRepository.findCurrent(
                                                existing.instanceId())
                                        .map(ProvisionDecision::replay);
                            });
                });
    }
}
~~~

Đây là ví dụ thiết kế, không phải class SCOSB có sẵn. Trong triển khai thực tế:

- insertIfAbsent phải dựa trên unique constraint và xử lý duplicate key ở database.
- Tạo instance, operation và outbox cần nằm trong cùng transaction.
- Nếu insert instance thành công nhưng operation/outbox thất bại, transaction phải rollback.
- Nếu instance đã tồn tại, phải xác minh record thuộc đúng tenant và platform.
- findCurrent cần trả operation đúng với lần provision đang xét, không chọn operation bất kỳ của instance.
- HTTP adapter chuyển ProvisionDecision thành status/response theo OSB API version.
- Không gọi provider trực tiếp trong request handler nếu operation cần chạy bất đồng bộ.

## 20. Worker gọi provider và reconciliation

Worker có thể dùng provider idempotency key ổn định:

~~~java
public Mono<ProviderResource> provisionOrReconcile(
        ProvisionOperation operation) {

    return providerClient.findByIdempotencyKey(
                    operation.providerIdempotencyKey())
            .flatMap(found -> verifyOwnershipAndConfiguration(
                    operation, found))
            .switchIfEmpty(Mono.defer(() ->
                    providerClient.create(
                            operation.command(),
                            operation.providerIdempotencyKey())))
            .flatMap(resource ->
                    instanceRepository.attachProviderResource(
                            operation.instanceId(),
                            resource.id(),
                            resource.state())
                    .then(operationRepository.markSucceeded(
                            operation.operationId(),
                            resource.id()))
                    .thenReturn(resource))
            .onErrorResume(ProviderAlreadyExistsException.class,
                    error -> reconcileExistingResource(operation));
}
~~~

Đây là pseudocode để thể hiện ý tưởng. Provider lookup có thể trả empty khi resource chưa tồn tại, hoặc trả lỗi eventual consistency ngay sau create. Cần retry lookup có giới hạn trước khi kết luận resource vắng mặt.

verifyOwnershipAndConfiguration phải so sánh broker marker, tenant, instance ID, service type và các thuộc tính quan trọng. Nếu không khớp, phát sinh conflict có mã lỗi nội bộ rõ ràng; không attach resource.

Khi lưu mapping, dùng conditional update/version để operation cũ không ghi đè kết quả mới. Chỉ đánh dấu SUCCEEDED sau khi provider resource ID và instance state được lưu bền vững.

## 21. Những tình huống cần kiểm thử

Bộ test cần chứng minh không tạo tài nguyên trùng và không nhận nhầm resource của hệ thống khác.

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| IDEM-001 | Provision lần đầu | Tạo một instance, một operation và một provider resource |
| IDEM-002 | Cùng instance ID, cùng request gửi lại | Không gọi provider create lần hai |
| IDEM-003 | Cùng instance ID nhưng plan khác | Conflict, không side effect |
| IDEM-004 | Cùng instance ID nhưng parameters khác | Conflict theo policy/contract |
| IDEM-005 | Hai request đồng thời cùng instance ID | Chỉ một operation được tạo |
| IDEM-006 | Worker nhận message lặp | Không tạo resource thứ hai |
| IDEM-007 | Provider tạo xong, broker timeout trước khi lưu | Reconciliation tìm và attach resource |
| IDEM-008 | Provider trả AlreadyExists, marker khớp | Xác minh rồi hoàn tất operation |
| IDEM-009 | Provider trả AlreadyExists, owner khác | Conflict, không adopt hoặc xóa |
| IDEM-010 | Resource tồn tại nhưng cấu hình khác | Reconciliation/conflict, không ghi READY giả |
| IDEM-011 | Worker lease hết hạn trong provider call | Worker mới tra cứu trước retry |
| IDEM-012 | Provider không hỗ trợ idempotency key | Dùng marker/lookup hoặc manual reconciliation |
| IDEM-013 | Broker DB lỗi sau provider create | Operation giữ trạng thái chưa kết luận; phục hồi mapping |
| IDEM-014 | Request lặp khi operation đang chạy | Trả operation hiện tại |
| IDEM-015 | Request lặp sau khi READY | Trả kết quả thành công idempotent |
| IDEM-016 | Retry sau FAILED chắc chắn chưa tạo resource | Retry theo policy |
| IDEM-017 | Retry sau lỗi chưa rõ side effect | Reconcile trước khi create |
| IDEM-018 | Provider lookup eventual consistency | Retry lookup có giới hạn, không create mù |
| IDEM-019 | Resource có tên trùng ở tenant khác | Không nhận nhầm tenant |
| IDEM-020 | Deprovision/retry trên mapping đã reconcile | Xóa đúng resource thuộc instance |

Mỗi test nên kiểm tra cả HTTP response, database state, operation history và số lần provider call. Mock provider phải mô phỏng được trường hợp create thành công nhưng response bị mất.

## 22. Kiểm tra vận hành sau khi khắc phục

Sau khi xử lý sự cố:

- Có đúng một broker instance record cho khóa platform/instance.
- Có một operation provision chính đang đại diện cho yêu cầu.
- Provider resource ID được lưu trong mapping.
- Ownership marker trên provider khớp với broker instance.
- Plan, region, tenant và cấu hình quan trọng khớp.
- Operation kết thúc SUCCEEDED hoặc trạng thái cuối cùng theo contract.
- last_operation trả trạng thái đúng.
- Retry request không tạo thêm resource.
- Outbox/queue không còn message bị kẹt không giải thích được.
- Không còn resource mồ côi do attempt cũ.
- Log và audit cho phép truy vết nhưng không lộ secret.

Nếu phải can thiệp thủ công, ghi lại actor, lý do, resource ID, thao tác đã thực hiện và kết quả. Không chỉnh database trực tiếp để đánh dấu READY khi chưa xác minh provider.

## 23. Checklist phòng ngừa

Trước khi phát hành broker, hãy kiểm tra:

- Instance ID có unique constraint đúng phạm vi.
- Request fingerprint được canonicalize và version hóa.
- Cùng request lặp không tạo operation/provider resource mới.
- Request cùng ID nhưng nội dung xung đột bị từ chối.
- Operation và outbox được lưu nguyên tử.
- Provider idempotency key ổn định qua retry.
- Provider resource có ownership marker.
- Worker claim có lease/version/fencing.
- Timeout sau provider create chuyển sang reconciliation.
- AlreadyExists chỉ được coi là thành công sau khi xác minh ownership và configuration.
- Resource ngoài broker không bị auto-adopt hoặc xóa.
- Operation state và last_operation phản ánh đúng kết quả.
- Có test request race, worker duplicate, lost response và eventual consistency.
- Có metric cho duplicate request, AlreadyExists, reconciliation và orphan resource.
- Có runbook cho manual conflict và cleanup có kiểm soát.

## Kết luận

Cấp phát bị gọi lặp và provider báo tài nguyên đã tồn tại là vấn đề về idempotency và đồng bộ trạng thái giữa broker với hệ thống bên ngoài. Broker cần dùng instance ID cùng request fingerprint để nhận diện request lặp, dùng unique constraint và transaction để ngăn tạo record trùng, đồng thời giữ provider idempotency key ổn định qua các lần retry. Khi provider đã tạo resource nhưng response bị mất, broker phải reconciliation bằng provider operation ID, idempotency key hoặc ownership marker trước khi gửi create lại. Chỉ adopt resource khi xác minh được đúng owner, tenant và cấu hình; nếu không, giữ conflict để xử lý có kiểm soát. Cách làm này giúp Spring Cloud Service Broker tránh tạo tài nguyên trùng, không nhận nhầm resource của hệ thống khác và duy trì trạng thái OSB operation chính xác.

## Tài liệu tham khảo

- [Open Service Broker API Specification](https://github.com/openservicebrokerapi/servicebroker/blob/master/spec.md) — provision, asynchronous operation, conflict và service instance lifecycle.
- [Spring Cloud Open Service Broker Reference Documentation](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/reference/) — provision service abstraction và request/response model.
- [AWS API — Making requests idempotent](https://docs.aws.amazon.com/ec2/latest/devguide/ec2-api-idempotency.html) — idempotency token và xử lý request lặp.
- [Kubernetes — Object Names and IDs](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/) — định danh object và phạm vi tên.
- [Kubernetes — Labels and Selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/) — gắn metadata để nhận diện và truy vấn resource.
- [Transactional Outbox pattern](https://microservices.io/patterns/data/transactional-outbox.html) — phối hợp database commit và event delivery.
- [PostgreSQL — INSERT](https://www.postgresql.org/docs/current/sql-insert.html) — unique constraint và ON CONFLICT.

