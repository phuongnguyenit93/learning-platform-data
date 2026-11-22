# Kiểm toán hoạt động

Trong một hệ thống DSL (Domain-Specific Language), người dùng có thể khai báo cấu hình, tạo quy trình, thay đổi dữ liệu, gọi API hoặc điều khiển các hành động có ảnh hưởng đến nghiệp vụ. Khi hệ thống được sử dụng trong môi trường thật, tổ chức cần biết **ai đã làm gì, vào lúc nào, trên đối tượng nào, kết quả ra sao và thay đổi được thực hiện qua con đường nào**. Kiểm toán hoạt động (activity auditing) là cơ chế ghi nhận, bảo vệ và tra cứu những hành động quan trọng đó.

Kiểm toán hoạt động khác với log phục vụ debug. Log kỹ thuật thường giúp developer tìm lỗi trong một lần chạy; audit trail cần có cấu trúc, nguồn gốc, tính toàn vẹn và thời hạn lưu giữ phù hợp để hỗ trợ trách nhiệm giải trình, điều tra sự cố, kiểm soát nội bộ và yêu cầu tuân thủ. Một DSL bảo mật nên mô hình hóa những hành động nào phải được audit, thông tin nào được ghi, dữ liệu nhạy cảm nào phải che, ai được đọc audit record và cách các record được bảo vệ khỏi sửa hoặc xóa trái phép.

## 1. Kiểm toán hoạt động là gì?

Kiểm toán hoạt động là việc ghi nhận có hệ thống các hành động quan trọng của người dùng, service, workflow hoặc thành phần tự động. Một audit record thường mô tả actor, action, target, thời điểm, nguồn yêu cầu, kết quả và context liên quan.

Ví dụ một quản trị viên thay đổi quyền của người dùng:

~~~json
{
  "eventType": "AccessPolicyChanged",
  "actor": {
    "type": "user",
    "id": "usr-104"
  },
  "target": {
    "type": "role",
    "id": "billing-operator"
  },
  "action": "update",
  "occurredAt": "2026-11-15T04:00:00Z",
  "outcome": "success",
  "requestId": "req-81d2"
}
~~~

Record này cho biết ai thay đổi role, hành động nào được thực hiện, khi nào và kết quả ra sao. Một audit system đầy đủ có thể lưu thêm trạng thái trước/sau đã được lọc, lý do thay đổi, nguồn xác thực và correlation ID.

### 1.1. Mục tiêu

Kiểm toán hoạt động thường phục vụ các mục tiêu:

- Truy vết thay đổi dữ liệu, cấu hình và quyền truy cập.
- Điều tra hành động bất thường hoặc sự cố bảo mật.
- Chứng minh quy trình phê duyệt và trách nhiệm của actor.
- Hỗ trợ kiểm tra tuân thủ, kiểm soát nội bộ và audit bên ngoài.
- Phát hiện hành vi trái chính sách hoặc truy cập bất thường.
- Phục hồi ngữ cảnh khi cần giải thích một thay đổi.
- Đo lường cách hệ thống và người dùng vận hành.

### 1.2. Audit record khác application log

Application log có thể chứa thông tin debug, stack trace, timing và trạng thái nội bộ. Audit record cần tập trung vào sự kiện có ý nghĩa về trách nhiệm và kiểm soát.

| Đặc điểm | Application log | Audit record |
|---|---|---|
| Mục đích chính | Debug và vận hành | Trách nhiệm giải trình và điều tra |
| Cấu trúc | Có thể là text tự do | Schema có trường xác định |
| Actor/target | Có thể không có | Thường là thành phần cốt lõi |
| Tính toàn vẹn | Theo chính sách log | Cần kiểm soát chống sửa/xóa |
| Truy cập | Developer/operator | Theo quyền và mục đích được duyệt |
| Retention | Theo nhu cầu vận hành | Theo policy, pháp lý và rủi ro |
| Nội dung | Có thể nhiều chi tiết kỹ thuật | Chỉ ghi dữ liệu cần thiết |

Không nên coi mọi dòng log là audit record. Một dòng log có thể bị rotate hoặc thiếu actor/target, trong khi audit trail cần đáp ứng truy vấn và chứng minh nguồn gốc.

### 1.3. Audit không đồng nghĩa với giám sát nhân viên

Audit ghi nhận hoạt động có ý nghĩa đối với hệ thống và nghiệp vụ. Việc thu thập dữ liệu phải có mục đích, phạm vi và quyền truy cập rõ ràng; không nên ghi mọi thao tác hoặc nội dung cá nhân chỉ vì có thể ghi được.

## 2. Phạm vi hoạt động cần kiểm toán

Không phải mọi sự kiện đều có cùng mức độ quan trọng. DSL hoặc nền tảng có thể phân loại hành động theo domain và rủi ro.

Các nhóm hoạt động thường cần audit:

| Nhóm | Ví dụ |
|---|---|
| Authentication | Đăng nhập, đăng xuất, MFA challenge, token revoke |
| Authorization | Thay role, cấp/revoke permission, thay policy |
| Data access | Đọc dữ liệu nhạy cảm, export, bulk download |
| Data mutation | Tạo, sửa, xóa, restore record |
| Configuration | Thay endpoint, profile, feature flag hoặc secret reference |
| Workflow | Khởi chạy, approve, reject, cancel hoặc retry workflow |
| API administration | Tạo key, rotate credential, thay quota |
| DSL authoring | Thay grammar, policy, schema hoặc rule production |
| Deployment | Publish version, promote, rollback |
| Administrative action | Tạo tenant, thay owner, khóa tài khoản |

### 2.1. Audit theo rủi ro

Có thể phân loại event theo mức độ:

- Critical: thay đổi quyền quản trị, xóa dữ liệu lớn, thay security policy.
- High: export dữ liệu nhạy cảm, deploy production, thay cấu hình xác thực.
- Medium: sửa dữ liệu nghiệp vụ quan trọng, approve workflow.
- Low: thay tùy chọn cá nhân hoặc thao tác không ảnh hưởng dữ liệu quan trọng.

Mức độ chỉ giúp ưu tiên lưu trữ, cảnh báo và review. Không nên bỏ audit cho một hành động bắt buộc chỉ vì mức độ được gán thấp.

### 2.2. Successful và failed actions

Audit cần cân nhắc cả hành động thành công lẫn thất bại. Một lần truy cập bị từ chối có thể quan trọng trong điều tra bảo mật; một lần thay đổi thất bại có thể giải thích vì sao người dùng không hoàn tất được nghiệp vụ.

### 2.3. Read access

Đọc dữ liệu nhạy cảm có thể cần audit, đặc biệt với hồ sơ tài chính, dữ liệu cá nhân hoặc thông tin quản trị. Tuy nhiên, ghi mọi lần đọc ở quy mô lớn có thể tạo khối lượng dữ liệu rất lớn. Cần định nghĩa rõ resource và operation nào phải ghi.

### 2.4. Bulk operations

Một thao tác export hoặc cập nhật hàng nghìn bản ghi nên có audit event tổng hợp, kèm phạm vi, số lượng, filter hoặc job ID. Không nhất thiết tạo một record riêng cho từng dòng nếu điều đó làm hệ thống quá tải, nhưng phải bảo đảm có thể truy vết chi tiết theo yêu cầu và policy.

## 3. Mô hình audit event

Một audit event cần schema ổn định và đủ thông tin để truy vấn. Có thể bắt đầu với cấu trúc:

~~~text
AuditEvent
├── id
├── eventType
├── occurredAt
├── recordedAt
├── actor
├── action
├── target
├── outcome
├── source
├── context
├── correlation
└── details
~~~

### 3.1. Event ID

ID duy nhất giúp tham chiếu record trong báo cáo, support case hoặc incident. ID cần ổn định khi record được chuyển qua pipeline lưu trữ.

### 3.2. Event type

Event type mô tả loại sự kiện, ví dụ UserRoleGranted, ConfigurationPublished hoặc SensitiveRecordViewed. Nên dùng tên ổn định theo domain, tránh event name chung chung như Update hoặc Activity.

### 3.3. Occurred time và recorded time

occurredAt là thời điểm hành động thực tế xảy ra theo nguồn phát. recordedAt là thời điểm audit system nhận và lưu record. Hai thời điểm khác nhau giúp phát hiện độ trễ, message đến muộn hoặc đồng hồ nguồn không đồng bộ.

### 3.4. Actor

Actor là chủ thể thực hiện hành động. Actor có thể là user, service account, workflow engine, scheduled job hoặc system process.

Một actor record có thể chứa:

- Loại actor.
- ID ổn định.
- Tên hiển thị tại thời điểm sự kiện nếu cần.
- Tenant hoặc organization.
- Authentication method.
- Delegation/impersonation context nếu có.

Không nên chỉ lưu display name vì tên có thể thay đổi hoặc trùng nhau. ID ổn định là cơ sở để truy vấn lịch sử.

### 3.5. Action

Action mô tả hành động như create, update, delete, approve, deny, export, execute, publish hoặc revoke. Nên chuẩn hóa action vocabulary để báo cáo không phải xử lý nhiều cách viết cùng nghĩa.

### 3.6. Target

Target là đối tượng bị tác động: user, role, order, policy, workflow, configuration hoặc resource khác. Record nên lưu loại và định danh target; tên hiển thị có thể được snapshot nếu cần tra cứu sau khi resource bị xóa.

### 3.7. Outcome

Outcome cho biết success, denied, failed, partially_completed hoặc pending. Cần phân biệt hành động bị từ chối trước khi thực thi với hành động đã bắt đầu nhưng thất bại giữa chừng.

### 3.8. Source và context

Source có thể là API, UI, CLI, scheduled task, integration hoặc workflow. Context có thể chứa request ID, session ID, IP address, client ID, trace ID và phiên bản ứng dụng, nhưng chỉ lưu trường có mục đích rõ ràng.

## 4. Actor, delegation và danh tính

Một thao tác có thể được thực hiện thay mặt người khác hoặc được service thực hiện tự động.

### 4.1. Human actor

Human actor là người dùng đã xác thực. Audit record nên liên kết với identity ổn định và tenant context.

### 4.2. Service actor

Service account hoặc workload identity có thể thực hiện hành động nền. Record cần nhận diện service và phiên bản hoặc deployment identity nếu điều tra cần biết code path nào đã chạy.

### 4.3. Delegation và impersonation

Một quản trị viên có thể thao tác thay mặt người dùng, hoặc một hệ thống hỗ trợ có thể impersonate tài khoản để chẩn đoán. Audit phải phân biệt:

- Initiating actor: người khởi tạo hành động.
- Effective actor: danh tính được dùng để thực hiện.
- Subject: người hoặc tài nguyên mà hành động hướng tới.
- Delegation reason: lý do hoặc ticket cho phép ủy quyền.

Không được ghi nhận thao tác impersonation như thể người dùng được impersonate tự thực hiện. Việc che mất initiating actor làm suy yếu khả năng điều tra.

### 4.4. Anonymous và unauthenticated activity

Một request chưa xác thực vẫn có thể cần audit, ví dụ nhiều lần đăng nhập thất bại hoặc request bị chặn. Khi không có actor ID, record có thể dùng anonymous principal cùng nguồn request đã được lọc.

### 4.5. Identity snapshot

Nếu user bị xóa hoặc đổi tên, ID vẫn cần truy vấn được. Có thể lưu display name snapshot nhưng phải xem đó là thông tin bổ sung, không phải khóa chính.

## 5. Before/after state và thay đổi dữ liệu

Với thao tác update, audit có thể ghi nhận field nào thay đổi và giá trị trước/sau.

Ví dụ:

~~~json
{
  "eventType": "CustomerAddressChanged",
  "target": {
    "type": "customer",
    "id": "cus-204"
  },
  "changes": [
    {
      "field": "deliveryAddress.city",
      "before": "Da Nang",
      "after": "Ho Chi Minh City"
    }
  ]
}
~~~

### 5.1. Field-level audit

Field-level audit hữu ích khi cần biết chính xác thay đổi nào đã xảy ra. Có thể chỉ ghi field được phép audit thay vì serialize toàn bộ object.

### 5.2. Snapshot và diff

Snapshot lưu trạng thái đầy đủ tại một thời điểm; diff lưu các trường thay đổi. Diff thường tiết kiệm hơn nhưng cần có schema/version để diễn giải. Snapshot thuận tiện cho phục hồi nhưng dễ lưu quá nhiều dữ liệu.

### 5.3. Sensitive fields

Password, access token, private key, secret và thông tin thanh toán nhạy cảm không được ghi nguyên văn vào audit. Với dữ liệu cá nhân, cần policy xác định có được ghi, che, hash hoặc chỉ ghi trạng thái thay đổi hay không.

### 5.4. Redaction

Redaction nên diễn ra trước khi record rời khỏi trust boundary. Nếu dữ liệu nhạy cảm đã được ghi vào log trung gian rồi mới che ở UI, bản gốc vẫn có thể bị lộ trong hệ thống log.

### 5.5. Deleted resources

Khi target bị xóa, audit record cần giữ đủ định danh và context để hiểu đối tượng đã bị tác động. Có thể lưu loại resource, ID, owner hoặc tên snapshot theo retention policy, nhưng không giữ toàn bộ nội dung nếu không cần.

## 6. Khai báo audit policy trong DSL

Một DSL bảo mật có thể cho phép định nghĩa policy kiểm toán theo resource và operation.

Ví dụ cú pháp minh họa:

~~~text
audit policy CustomerData {
    on Customer.create
    on Customer.update
        capture changedFields
    on Customer.delete
        capture targetIdentity
    on Customer.read
        when classification >= CONFIDENTIAL
    exclude fields [password, accessToken, secret]
    retention 365d
}
~~~

### 6.1. Audit policy

Policy xác định event nào cần ghi, mức chi tiết, điều kiện kích hoạt và retention class. Policy có thể được gắn với resource, operation, service hoặc domain.

### 6.2. Capture mode

Một số mode thường gặp:

- Metadata only: actor, action, target, time, outcome.
- Changed fields: chỉ ghi các field thay đổi.
- Redacted snapshot: snapshot đã loại bỏ dữ liệu nhạy cảm.
- Reference only: ghi ID của artifact hoặc transaction liên quan.
- Aggregate summary: tổng hợp số lượng cho bulk operation.

### 6.3. Conditional auditing

Có thể audit theo classification, tenant, outcome hoặc mức rủi ro. Điều kiện cần có semantics xác định và không được cho phép client tự tắt audit bắt buộc.

### 6.4. Inherited policies

Policy có thể được kế thừa từ domain hoặc resource cha. Cần quy định policy con có thể mở rộng, thu hẹp hay chỉ tăng mức audit. Với security-critical audit, policy con không nên âm thầm giảm yêu cầu của policy cha.

### 6.5. Explicit exclusions

Exclusion phải được review và có lý do. Danh sách field bị loại khỏi audit không được dùng để né việc ghi nhận hành động bắt buộc.

## 7. Audit cho API và DSL operations

Nếu DSL định nghĩa API hoặc thao tác nghiệp vụ, có thể gắn audit metadata vào operation.

Ví dụ:

~~~text
@audit(
    event = "OrderCancelled",
    capture = [actor, target, reason, outcome]
)
operation cancelOrder(orderId: OrderId, reason: String) {
    authorize "orders.cancel"
    execute cancel(orderId, reason)
}
~~~

### 7.1. Audit ở boundary

Ghi audit tại API boundary giúp nhận diện request, principal và kết quả. Tuy nhiên, nếu nghiệp vụ được xử lý bất đồng bộ, cần thêm event cho kết quả thực thi cuối cùng.

### 7.2. Accepted không đồng nghĩa completed

Một API trả 202 Accepted chỉ xác nhận công việc được nhận. Audit cần phân biệt request accepted với job completed hoặc failed.

### 7.3. Internal operations

Một thao tác nội bộ có thể thay đổi dữ liệu quan trọng mà không đi qua public API. Audit cần đặt ở lớp domain/service hoặc transaction boundary để không bỏ sót các đường thực thi khác.

### 7.4. Bulk API

Với bulk update, record nên lưu operation ID, filter/scope, số lượng dự kiến, số lượng thành công, số lượng thất bại và kết quả cuối. Nếu có thể truy vấn từng item, cần correlation đến item-level outcome.

## 8. Audit cho workflow và sự kiện

Workflow có thể kéo dài nhiều giờ hoặc nhiều ngày, đi qua nhiều service và actor. Audit cần liên kết các bước thành một lịch sử có thể đọc được.

Ví dụ:

~~~text
WorkflowStarted
    |
    v
ApprovalRequested
    |
    v
ApprovalGranted
    |
    v
PaymentCaptured
    |
    v
ShipmentCreated
    |
    v
WorkflowCompleted
~~~

### 8.1. Workflow instance ID

Mỗi lần chạy workflow cần ID riêng. Business key như orderId có thể liên kết nhiều workflow instance nhưng không thay thế workflow ID.

### 8.2. Step audit

Có thể ghi nhận step started, completed, failed, retried, skipped hoặc compensated. Không nhất thiết audit mọi log kỹ thuật bên trong step; cần chọn các mốc có ý nghĩa vận hành và nghiệp vụ.

### 8.3. Human approval

Audit approval nên lưu người duyệt, thời điểm, quyết định, lý do, policy/version và đối tượng được duyệt. Nếu một người thay đổi nội dung sau khi đã duyệt, approval cũ có thể không còn hiệu lực.

### 8.4. Event correlation

Correlation ID và causation ID giúp nối command, event và workflow transition. Audit record nên giữ các ID này để tái dựng chuỗi nguyên nhân.

### 8.5. Retry và compensation

Retry không nên bị ghi như một hành động nghiệp vụ mới nếu chỉ là lần thử kỹ thuật. Tuy nhiên, attempt count và kết quả từng lần có thể cần cho điều tra. Compensation là hành động nghiệp vụ mới và cần audit riêng.

## 9. Tính toàn vẹn và chống sửa đổi audit trail

Audit trail chỉ đáng tin khi có thể phát hiện việc sửa hoặc xóa trái phép.

### 9.1. Append-only storage

Một mô hình phổ biến là chỉ cho phép thêm record, không cho update/delete bằng tài khoản ứng dụng thông thường. Correction được ghi thành record mới liên kết với record gốc.

### 9.2. Hash chaining

Mỗi record có thể chứa hash của record trước đó:

~~~text
H0 = hash(record0)
H1 = hash(record1 || H0)
H2 = hash(record2 || H1)
...
~~~

Nếu một record cũ bị thay đổi, các hash phía sau không còn khớp. Hash chain cần có anchor hoặc checkpoint được bảo vệ độc lập để kẻ tấn công không thể viết lại toàn bộ chuỗi.

### 9.3. Digital signatures

Record hoặc batch có thể được ký bằng khóa được bảo vệ. Verification key cần được quản lý để auditor có thể kiểm tra chữ ký sau này. Cần có key rotation và ghi nhận phiên bản khóa.

### 9.4. WORM storage

Write Once Read Many storage ngăn sửa/xóa trong thời hạn retention được cấu hình. Đây là một lựa chọn cho audit quan trọng, nhưng vẫn cần kiểm soát quyền quản trị storage và backup.

### 9.5. Trusted timestamps

Timestamp từ máy phát có thể sai hoặc bị giả mạo. Có thể ghi cả occurredAt và recordedAt từ hệ thống nhận, đồng bộ clock và dùng timestamp service khi yêu cầu chứng cứ cao hơn.

### 9.6. Tamper detection

Định kỳ xác minh hash, signature, sequence và record count. Nếu phát hiện gap hoặc mismatch, cần tạo security alert và giữ bằng chứng phục vụ điều tra.

## 10. Giao dịch và bảo đảm ghi audit

Một vấn đề quan trọng là hành động nghiệp vụ có thể thành công nhưng audit record lại không được ghi, hoặc audit ghi thành công trong khi giao dịch nghiệp vụ rollback.

### 10.1. Atomic audit write

Nếu audit record và business update nằm trong cùng database, có thể ghi chúng trong cùng transaction. Khi transaction commit, cả hai cùng tồn tại; khi rollback, cả hai cùng bị hủy.

### 10.2. Transactional outbox

Nếu audit được chuyển sang hệ thống riêng, outbox có thể lưu event audit cùng transaction nghiệp vụ. Dispatcher chuyển record đến audit service. Consumer cần deduplicate vì delivery có thể lặp.

### 10.3. Fail-open và fail-closed

Khi audit backend không khả dụng, hệ thống cần policy rõ:

- Fail-closed: từ chối hành động quan trọng nếu không thể ghi audit.
- Fail-open: cho phép hành động nhưng ghi vào buffer bền vững hoặc hàng đợi dự phòng.
- Degraded mode: chỉ cho phép một số thao tác ít rủi ro và cảnh báo vận hành.

Không có lựa chọn chung cho mọi hành động. Quyết định cần dựa trên rủi ro và yêu cầu nghiệp vụ.

### 10.4. Durable buffering

Buffer trong bộ nhớ có thể mất khi process crash. Nếu dùng queue trung gian, cần persistence, retry, monitoring và giới hạn dung lượng. Khi buffer đầy, hệ thống phải có hành vi xác định thay vì âm thầm bỏ record.

### 10.5. Audit write failure

Không nên chỉ log lỗi audit vào cùng backend đang gặp sự cố rồi coi như đã xử lý. Cần metric/alert độc lập và quy trình phục hồi record bị thiếu nếu policy cho phép.

## 11. Truy vấn và tìm kiếm audit

Audit hữu ích khi người có quyền có thể tìm đúng record mà không cần đọc toàn bộ kho dữ liệu.

Các bộ lọc thường gặp:

- Khoảng thời gian.
- Actor ID hoặc actor type.
- Action/event type.
- Target type và target ID.
- Tenant hoặc organization.
- Outcome.
- Request, trace hoặc correlation ID.
- Source system.
- Classification hoặc severity.

### 11.1. Query theo actor

Ví dụ tìm các hành động của một quản trị viên trong một khoảng thời gian để điều tra việc thay quyền.

### 11.2. Query theo target

Tìm lịch sử của một resource cho biết ai đã sửa, xóa, restore hoặc thay quyền truy cập đến nó.

### 11.3. Query theo correlation

Khi một request tạo ra nhiều event và workflow step, correlation ID giúp xem toàn bộ chuỗi liên quan.

### 11.4. Indexing

Index theo timestamp, tenant, actor, target và event type giúp truy vấn nhanh. Không nên index mọi trường payload tùy ý vì làm tăng chi phí và có thể đưa dữ liệu nhạy cảm vào index.

### 11.5. Pagination

Audit query có thể trả lượng dữ liệu lớn. Nên dùng cursor hoặc pagination ổn định, giới hạn page size và có thứ tự tổng như recordedAt cùng event ID.

### 11.6. Export

Export audit data cần audit chính nó. Record export nên chứa người yêu cầu, filter, phạm vi, số lượng, định dạng, thời điểm và nơi nhận. Quyền export thường nhạy cảm hơn quyền xem một record đơn lẻ.

## 12. Phân quyền đọc audit

Audit data có thể chứa thông tin cá nhân, hoạt động quản trị và chi tiết hệ thống. Không phải ai cũng được xem mọi record.

### 12.1. Role-based access

Có thể định nghĩa các role như audit-reader, security-investigator và audit-admin với quyền khác nhau. Audit-reader có thể truy vấn nhưng không quản lý retention; audit-admin có thể cấu hình hệ thống nhưng không nhất thiết được đọc payload nhạy cảm.

### 12.2. Scope theo tenant

Người dùng tenant chỉ được xem audit thuộc tenant của họ. Quản trị viên nền tảng có thể có quyền rộng hơn nhưng cần lý do và audit riêng.

### 12.3. Separation of duties

Người có quyền cấu hình audit không nên đồng thời có khả năng xóa dấu vết của chính mình. Tách quyền giữa application admin, audit operator và storage administrator giúp giảm xung đột lợi ích.

### 12.4. Break-glass access

Trong tình huống khẩn cấp, có thể cấp quyền truy cập tạm thời với justification, thời hạn và approval. Việc dùng break-glass phải được audit ở một kênh độc lập hoặc có bảo vệ mạnh hơn.

### 12.5. Audit của audit

Các hành động đọc, export, thay retention, thay access policy và thay cấu hình integrity của audit store cũng cần được ghi lại. Nếu không, người điều tra không biết ai đã truy cập hoặc thay đổi hệ thống chứng cứ.

## 13. Privacy và data minimization

Audit có thể trở thành kho dữ liệu nhạy cảm nếu ghi mọi request body hoặc snapshot.

### 13.1. Purpose limitation

Mỗi trường được ghi nên có mục đích cụ thể như truy vết, security investigation hoặc compliance. Không nên thu thập thông tin không cần thiết.

### 13.2. Data minimization

Ưu tiên ID, field name, outcome và metadata. Chỉ lưu giá trị trước/sau khi có yêu cầu rõ. Không sao chép toàn bộ request body vào audit một cách mặc định.

### 13.3. Pseudonymization

Có thể thay identity bằng token hoặc ID giả danh trong một số báo cáo. Mapping để giải mã cần được bảo vệ và chỉ cấp cho người có thẩm quyền.

### 13.4. Redaction và masking

Mask một phần thông tin như email hoặc số tài khoản nếu người đọc chỉ cần nhận diện. Với secret, token và password, nên loại bỏ hoàn toàn thay vì chỉ che một phần.

### 13.5. Retention và deletion

Audit retention phải phù hợp mục đích, luật và policy tổ chức. Hết hạn có thể cần xóa an toàn hoặc chuyển archive. Với dữ liệu cá nhân, cần cân bằng nghĩa vụ lưu audit và quyền xóa/giới hạn xử lý theo quy định áp dụng.

### 13.6. Data residency

Audit record có thể chịu yêu cầu lưu tại vùng địa lý nhất định. Pipeline chuyển dữ liệu sang analytics hoặc backup phải tuân thủ phạm vi đó.

## 14. Retention, archive và lifecycle

Không phải mọi audit record đều cần lưu mãi mãi.

Một lifecycle có thể gồm:

~~~text
Hot storage
    |
    | after active query window
    v
Warm storage
    |
    | after retention threshold
    v
Immutable archive
    |
    | legal/policy expiry
    v
Secure deletion
~~~

### 14.1. Hot storage

Dữ liệu gần đây được truy vấn thường xuyên nên cần index và latency thấp.

### 14.2. Warm storage

Dữ liệu ít truy vấn hơn có thể chuyển sang storage chi phí thấp hơn nhưng vẫn có thể tra cứu.

### 14.3. Archive

Archive có thể dùng immutable storage, compression và catalog metadata để đáp ứng audit dài hạn.

### 14.4. Retention class

Có thể gán retention theo event category hoặc classification. Không nên áp dụng một thời hạn duy nhất cho mọi loại event nếu yêu cầu khác nhau.

### 14.5. Legal hold

Khi có điều tra hoặc tranh chấp, một tập record có thể cần được giữ vượt quá retention thông thường. Legal hold cần có owner, phạm vi, thời điểm bắt đầu/kết thúc và audit trail riêng.

### 14.6. Secure deletion

Khi hết hạn, dữ liệu cần được xóa theo policy trên storage chính, replica và backup theo khả năng kỹ thuật. Cần giữ bằng chứng về việc xóa nếu yêu cầu kiểm toán đòi hỏi.

## 15. Cảnh báo và phát hiện bất thường

Audit record có thể là nguồn dữ liệu cho security analytics và alerting.

Ví dụ quy tắc:

~~~text
alert ExcessiveDeniedAccess {
    when count(
        AccessDenied
        by actor.id
        within 5m
    ) > 20
    severity HIGH
}
~~~

### 15.1. Rule-based detection

Có thể phát hiện số lần đăng nhập thất bại lớn, export bất thường, thay quyền quản trị ngoài giờ hoặc nhiều lần truy cập resource không liên quan.

### 15.2. Baseline và anomaly detection

Hệ thống có thể so sánh hành vi hiện tại với baseline theo actor, tenant hoặc service. Kết quả cần được xem là tín hiệu điều tra, không phải bằng chứng chắc chắn về hành vi xấu.

### 15.3. Alert fatigue

Nếu mọi thay đổi đều tạo cảnh báo, operator sẽ bỏ qua. Cần phân biệt audit record (lưu đầy đủ theo policy) với alert (chỉ phát cho trường hợp cần hành động).

### 15.4. Correlation giữa nhiều nguồn

Kết hợp audit của API, identity provider, database, cloud control plane và workflow có thể giúp phát hiện chuỗi hành động đáng ngờ. Cần đồng bộ timestamp và chuẩn hóa identity.

## 16. Audit trong hệ thống phân tán

Một hành động có thể đi qua gateway, service, workflow engine, message broker và database. Mỗi thành phần có thể phát record riêng.

### 16.1. Correlation ID và trace ID

Correlation ID liên kết các sự kiện nghiệp vụ; trace ID liên kết spans kỹ thuật. Nên truyền cả hai qua service boundary nhưng không dùng chúng thay cho actor hoặc target identity.

### 16.2. Duplicate và out-of-order records

Message delivery có thể lặp hoặc đến muộn. Audit ingestion cần deduplicate theo event ID khi phù hợp và giữ occurredAt/recordedAt để phân biệt thứ tự.

### 16.3. Clock skew

Đồng hồ các node có thể lệch. Không nên chỉ dựa vào timestamp từ producer để xác định thứ tự nhân quả. Sequence number hoặc causal metadata có thể cần thiết.

### 16.4. Partial failure

Một service có thể commit thay đổi nhưng không publish audit event. Transactional outbox hoặc CDC có thể giúp giảm khoảng trống này.

### 16.5. Centralized audit service

Audit service tập trung giúp thống nhất schema, retention, access control và query. Tuy nhiên, nó trở thành dependency quan trọng; cần capacity planning, failover và cơ chế buffer.

### 16.6. Tamper boundary

Nếu mọi service đều có quyền ghi và đọc/xóa toàn bộ audit store, centralized storage chưa đủ bảo vệ. Nên dùng append-only ingestion identity và tách quyền quản trị storage.

## 17. Audit cho thay đổi cấu hình và DSL source

Một DSL có thể điều khiển security policy, workflow, API schema hoặc cấu hình production. Thay đổi source DSL có thể ảnh hưởng lớn dù không có thao tác CRUD trực tiếp.

### 17.1. Version và source revision

Audit event khi publish DSL nên ghi version, commit/source revision, author, reviewer và artifact digest. Điều này giúp liên kết hành vi runtime với chính xác định nghĩa ngôn ngữ đã được triển khai.

### 17.2. Policy change

Thay đổi authorization policy cần lưu policy ID, version, diff hoặc reference đến artifact đã ký, người duyệt và thời điểm có hiệu lực.

### 17.3. Configuration promotion

Khi profile được promote từ staging sang production, audit nên ghi artifact/config digest, target environment, actor và approval record.

### 17.4. Rollback

Rollback là hành động mới, không xóa lịch sử release trước. Audit nên ghi phiên bản bị rollback, phiên bản được khôi phục, lý do và kết quả.

### 17.5. DSL execution

Nếu DSL cho phép thực thi script hoặc workflow, cần ghi execution ID, definition version, initiating actor, input reference đã được lọc, kết quả và các side effects quan trọng.

## 18. Thiết kế schema và storage

Audit schema cần đủ linh hoạt để mở rộng nhưng vẫn có trường chuẩn cho truy vấn.

### 18.1. Common envelope

Một envelope chung có thể gồm event ID, event type, schema version, occurredAt, recordedAt, actor, target, action, outcome và context.

### 18.2. Domain-specific details

Chi tiết riêng như changed fields, workflow step hoặc policy diff có thể nằm trong payload theo event type. Không nên biến toàn bộ record thành một blob không có schema vì khó tìm kiếm và kiểm soát.

### 18.3. Schema versioning

Khi thêm trường hoặc thay semantics, cần version schema. Consumer và query tooling phải xử lý version cũ trong thời gian retention.

### 18.4. Index strategy

Index nên ưu tiên các trường thường truy vấn như tenant, time, actor, target và event type. Payload lớn có thể lưu riêng và tham chiếu bằng ID.

### 18.5. Partitioning

Có thể partition theo thời gian hoặc tenant để hỗ trợ retention và query. Partition strategy cần tránh một tenant lớn làm lệch tải và phải giữ được integrity chain nếu dùng hash chaining.

### 18.6. Data normalization

Actor và target có thể được lưu bằng ID cùng snapshot metadata. Tránh join phụ thuộc vào dữ liệu hiện tại nếu tên hoặc trạng thái resource có thể thay đổi sau sự kiện.

## 19. API để đọc và quản lý audit

Audit service thường cung cấp API truy vấn, export và quản lý policy.

Ví dụ API reference:

~~~http
GET /v1/audit-events?actorId=usr-104&from=2026-11-01T00:00:00Z
GET /v1/audit-events/{eventId}
POST /v1/audit-exports
GET /v1/audit-exports/{exportId}
~~~

### 19.1. Query API

Query API cần filter có kiểu, giới hạn thời gian, pagination và authorization. Không nên cho client truy vấn payload tùy ý nếu điều đó làm lộ dữ liệu.

### 19.2. Export job

Export lớn nên chạy bất đồng bộ. API trả job ID, trạng thái, số record và link tải có thời hạn. Việc tạo và tải export đều cần audit.

### 19.3. Policy management

Thay đổi audit policy, retention hoặc redaction rule cần quyền riêng và audit record. Có thể yêu cầu approval hai người với policy critical.

### 19.4. Integrity verification API

Auditor có thể yêu cầu kiểm tra hash chain hoặc chữ ký cho một khoảng record. Kết quả cần có phạm vi, thời điểm, thuật toán và verification status.

## 20. Bảo mật audit pipeline

Audit pipeline cần được bảo vệ như một thành phần security-critical.

Các biện pháp thường dùng:

- Xác thực producer và kiểm tra schema.
- Dùng TLS khi truyền record.
- Mã hóa storage và backup.
- Append-only ingestion.
- Tách quyền ghi, đọc, cấu hình và xóa.
- Quản lý signing key trong HSM hoặc key manager.
- Kiểm soát export và download.
- Rate limit để chống flooding.
- Giám sát ingestion lag và record loss.
- Backup và kiểm tra khả năng restore.
- Audit mọi thay đổi đối với audit system.

### 20.1. Producer spoofing

Không tin actor/source ID do client tự gửi. Identity phải được lấy từ authenticated context hoặc được xác minh bằng chữ ký/service identity.

### 20.2. Log injection

Giá trị người dùng có thể chứa newline hoặc ký tự điều khiển. Structured serialization và escaping giúp tránh giả mạo record khi hiển thị hoặc export.

### 20.3. Resource exhaustion

Kẻ tấn công có thể tạo số lượng event lớn hoặc payload khổng lồ. Cần giới hạn kích thước, quota, sampling chỉ với telemetry không bắt buộc và bảo vệ riêng cho audit bắt buộc.

### 20.4. Storage administrator risk

Người quản trị storage có thể có quyền cao. Immutable storage, key separation, independent checkpoints và external verification giảm nguy cơ một người có thể xóa dấu vết mà không bị phát hiện.

## 21. Kiểm thử và xác minh audit

Audit functionality cần test về coverage, correctness, integrity và failure handling.

Các trường hợp kiểm thử quan trọng:

1. Hành động bắt buộc tạo đúng audit event.
2. Actor, target, action và outcome được gán đúng.
3. Failed/denied operation được ghi theo policy.
4. Sensitive fields bị redacted trước khi persist.
5. Event có correlation/request ID chính xác.
6. Duplicate delivery không tạo record logic trùng.
7. Outbox phục hồi sau process crash.
8. Audit backend unavailable kích hoạt fail policy đúng.
9. Append-only permissions ngăn update/delete trái phép.
10. Hash chain/signature verification phát hiện sửa record.
11. Query authorization giới hạn đúng tenant và role.
12. Export được audit và giới hạn đúng phạm vi.
13. Retention và legal hold hoạt động đúng.
14. Schema version cũ vẫn truy vấn được.
15. Clock skew và late event không làm mất metadata thời gian.
16. Audit của chính audit administration được ghi lại.
17. Bulk operation có summary và item trace phù hợp.
18. Backup/restore không phá integrity metadata.

### 21.1. Coverage tests

Với mỗi operation được đánh dấu cần audit, test phải chứng minh cả đường thành công và các đường thất bại quan trọng đều tạo record theo policy.

### 21.2. Redaction tests

Dùng giá trị sentinel như fake password hoặc token rồi xác nhận chúng không xuất hiện trong audit record, log, export hay diagnostic.

### 21.3. Failure injection

Mô phỏng audit store mất kết nối, queue đầy, dispatcher crash và signature service unavailable. Kiểm tra fail-open/fail-closed theo từng loại action.

### 21.4. Integrity tests

Thay đổi một byte trong fixture hoặc xóa một record để xác nhận verifier phát hiện hash mismatch hoặc sequence gap.

## 22. Những lỗi thiết kế thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
|---|---|---|
| Coi application log là audit trail | Thiếu actor, target, schema và integrity | Dùng audit event có cấu trúc |
| Không ghi failed/denied actions | Bỏ sót dấu hiệu tấn công và lỗi quy trình | Audit cả outcome theo policy |
| Chỉ lưu display name | Không truy được identity sau khi đổi tên | Lưu stable actor ID |
| Ghi toàn bộ request body | Tích lũy secret và dữ liệu cá nhân | Data minimization và redaction |
| Cho phép update/delete record | Có thể sửa lịch sử mà không bị phát hiện | Append-only, signature hoặc WORM |
| Ghi audit sau commit mà không có outbox | Business change có thể không có audit | Atomic write hoặc transactional outbox |
| Không có correlation | Khó nối các bước phân tán | Propagate correlation/trace metadata |
| Không audit export/read sensitive data | Không biết ai đã xem hoặc lấy dữ liệu | Audit access theo classification |
| Cùng một người quản lý và xóa audit | Xung đột lợi ích | Separation of duties và immutable archive |
| Không có retention policy | Lưu quá lâu hoặc xóa quá sớm | Retention class và legal hold |
| Alert cho mọi event | Alert fatigue | Tách audit completeness khỏi alert policy |
| Không audit thay đổi audit policy | Kẻ tấn công có thể tắt kiểm toán | Audit-of-audit và approval |

## 23. Nguyên tắc thiết kế kiểm toán hoạt động cho DSL

Khi xây dựng audit model và runtime, có thể áp dụng các nguyên tắc sau:

1. **Xác định hành động quan trọng.** Phân loại theo resource, operation và rủi ro.
2. **Dùng schema có cấu trúc.** Actor, action, target, time, outcome và correlation phải có trường rõ.
3. **Phân biệt actor và subject.** Giữ initiating identity khi có delegation hoặc impersonation.
4. **Ghi cả thành công và thất bại.** Bao phủ denied, failed, partial và completed theo policy.
5. **Giảm dữ liệu nhạy cảm.** Redact trước khi persist và export.
6. **Bảo đảm tính toàn vẹn.** Append-only, hash chain, signature hoặc immutable storage tùy mức rủi ro.
7. **Gắn audit với transaction.** Dùng atomic write hoặc outbox/inbox để tránh khoảng trống.
8. **Quản lý quyền đọc và export.** Áp dụng tenant scope, separation of duties và audit-of-audit.
9. **Định nghĩa retention.** Có hot/warm/archive, legal hold và secure deletion.
10. **Hỗ trợ truy vấn có kiểm soát.** Index theo actor, target, time, type và correlation.
11. **Theo dõi hệ thống audit.** Giám sát ingestion lag, failure, integrity và storage capacity.
12. **Kiểm thử failure paths.** Không chỉ test đường thành công.
13. **Liên kết với version DSL.** Ghi source revision, policy version và artifact digest khi publish hoặc execute.
14. **Tách audit record khỏi alert.** Lưu đầy đủ theo policy nhưng chỉ cảnh báo khi cần hành động.
15. **Ghi lại thay đổi của chính audit system.** Policy, retention, access và key configuration đều cần được kiểm toán.

## 24. Kết luận

Kiểm toán hoạt động ghi nhận có cấu trúc những hành động quan trọng của người dùng, service và workflow. Một audit record đáng tin cần nhận diện actor, action, target, thời điểm, nguồn và outcome; với thay đổi dữ liệu, có thể ghi field-level diff đã được lọc. Audit trail cần được bảo vệ khỏi sửa/xóa trái phép, liên kết với transaction, có quyền truy cập và retention rõ ràng.

Trong hệ sinh thái DSL, audit policy có thể được khai báo cùng resource và operation, giúp compiler/runtime biết hành động nào phải ghi, capture mode nào được phép và dữ liệu nào cần redaction. Với workflow và hệ thống phân tán, correlation, outbox, idempotency và schema versioning giúp nối các record thành lịch sử có thể giải thích.

Khi audit được thiết kế như một phần của contract và security architecture, tổ chức có thể điều tra sự cố, chứng minh thay đổi, phát hiện hành vi bất thường và đáp ứng yêu cầu kiểm soát mà không thu thập dữ liệu quá mức.
