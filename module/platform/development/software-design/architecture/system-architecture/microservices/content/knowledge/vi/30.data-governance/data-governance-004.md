# Nhật ký kiểm toán và truy vết nguồn gốc thay đổi

Trong kiến trúc microservices, một bản ghi có thể được tạo tại một service, cập nhật bởi job nền, phát qua message broker, tổng hợp trong data warehouse rồi xuất hiện trên báo cáo hoặc API khác. Khi khách hàng hỏi “Ai đã đổi trạng thái đơn hàng?”, đội bảo mật hỏi “Quyền truy cập đã được cấp bằng cách nào?” hoặc nhóm dữ liệu hỏi “Chỉ số này được tính từ những bảng nào?”, hệ thống cần có bằng chứng đáng tin cậy chứ không chỉ vài dòng application log rời rạc.

**Nhật ký kiểm toán (audit trail)** ghi lại những hành động và thay đổi cần được giải trình: chủ thể thực hiện, hành động, đối tượng, thời điểm, kết quả và bối cảnh. **Truy vết nguồn gốc thay đổi (change provenance / data lineage)** cho biết dữ liệu được tạo, chuyển đổi và truyền qua những hệ thống, phiên bản, quy trình nào để tạo ra trạng thái hiện tại.

Mục tiêu không phải ghi “mọi thứ vào một log” mà là thiết kế chuỗi bằng chứng **đúng sự kiện, liên kết được, khó sửa trái phép, bảo vệ dữ liệu nhạy cảm, có thể truy vấn và có vòng đời rõ ràng**. Audit log, distributed trace, transaction log và data lineage liên quan nhau nhưng phục vụ các câu hỏi khác nhau.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt audit trail, activity log, operational log, trace, event sourcing, CDC và data lineage.
2. Xác định đối tượng, hành động, kết quả và mức độ chi tiết cần ghi cho các thay đổi quan trọng.
3. Thiết kế schema audit event có `actor`, `subject`, `resource`, `action`, `outcome`, `eventId`, `timestamp`, `correlationId` và `schemaVersion`.
4. Truy vết đường đi của một thay đổi qua HTTP, RPC, message broker, database, CDC, ETL/ELT và báo cáo.
5. Hiểu tính nguyên tử và các dạng lỗi của việc ghi business data đồng thời với audit event.
6. Áp dụng transactional outbox, idempotent consumer và versioning để hạn chế mất/trùng/sai thứ tự sự kiện.
7. Phân tích cơ chế append-only, phân quyền, integrity verification, retention và audit việc truy cập chính nhật ký.
8. Ghi nhận before/after hoặc diff mà không làm lộ token, PII, dữ liệu mật và nội dung nghiệp vụ không cần thiết.
9. Xây dựng câu hỏi truy vấn, kiểm thử và quy trình điều tra dựa trên bằng chứng có nguồn gốc rõ.

## 2. Vì sao microservices khiến kiểm toán khó hơn?

Một giao dịch có thể trải qua nhiều thành phần:

~~~text
Client
  |
  v
API Gateway (xác thực)
  |
  v
Order Service ----------> Order DB
  |                           |
  |                           +-- CDC / Outbox
  |                                  |
  +--> Event Broker <----------------+
         |
         +--> Billing Service ---> Billing DB
         |
         +--> Notification Worker
         |
         +--> Analytics Pipeline ---> Warehouse ---> Dashboard
~~~

Các câu hỏi có thể xuất hiện:

- Ai đã thay địa chỉ giao hàng và được cấp quyền gì lúc đó?
- Trạng thái `PAID` đến từ lời gọi API nào, hay từ reconciliation job?
- Một event `OrderUpdated` có bị replay khiến hệ thống ghi trùng?
- Báo cáo doanh thu đang sử dụng phiên bản transformation SQL nào?
- Khi một dashboard đổi số liệu, nguồn bảng, event schema hoặc code deploy nào đã thay đổi?
- Một admin đã xem dữ liệu nhạy cảm lúc nào, ở tenant nào?
- Có thể chứng minh không có sửa/xóa trái phép audit record không?
- Những sự kiện nào chưa được chuyển từ outbox sang hệ thống lưu trữ kiểm toán?

Một trace ID có thể nối các lần gọi trong một request, nhưng trace thường được sampling và retention ngắn. Một database audit trigger có thể thấy row đổi, nhưng không nhất thiết biết người dùng cuối đã xác thực hoặc lý do nghiệp vụ. Một event broker có thể giữ message, nhưng retention và consumer replay không tự bảo đảm lịch sử đầy đủ. Cần thiết kế mối liên hệ **theo mục đích**, thay vì chọn một loại log rồi kỳ vọng nó giải quyết mọi vấn đề.

## 3. Phân biệt các loại bằng chứng

| Cơ chế | Mục đích chính | Có thể thiếu |
|---|---|---|
| **Audit trail** | Giải trình ai làm gì, với tài nguyên nào, kết quả gì, khi nào | Không mô tả đầy đủ performance hoặc mọi bước kỹ thuật |
| **Application/operational log** | Chẩn đoán lỗi, cảnh báo, tình trạng runtime | Không đủ tính toàn vẹn, retention và nghiệp vụ cho kiểm toán |
| **Distributed tracing** | Theo dõi request qua services, tìm nơi chậm/lỗi | Sampling, thời gian lưu ngắn; không phải ledger mọi thay đổi |
| **Database transaction log / WAL** | Phục hồi và nhân bản thay đổi cấp storage | Không tự gắn identity nghiệp vụ hoặc nguyên nhân hành động |
| **Change Data Capture (CDC)** | Đưa thay đổi database vào pipeline sự kiện | Có thể phản ánh row diff nhưng thiếu authorized actor/reason |
| **Event sourcing** | Lưu chuỗi domain events làm nguồn dựng trạng thái | Không mặc nhiên bao phủ mọi access/admin action |
| **Data lineage** | Truy nguồn/tuyến biến đổi của dữ liệu giữa datasets/jobs | Không luôn chỉ ra ai nhấn nút sửa một bản ghi |
| **Security access log** | Theo dõi đăng nhập, truy vấn, quyền và truy cập dữ liệu | Không thay thế lịch sử trạng thái đối tượng nghiệp vụ |
| **Deployment/change record** | Ghi artifact/config/schema nào được triển khai | Không tự cung cấp data lineage cho một hàng báo cáo |

Ví dụ `GET /users/42` trả 200 có thể là operational access log. Nếu đọc dữ liệu hồ sơ nhạy cảm là hành động bắt buộc kiểm toán, cần một **audit access event** với loại tài nguyên, purpose/justification được quản lý, người thực hiện và outcome; không nên chỉ giữ một dòng `GET /users/42 200` rồi coi như đủ bằng chứng.

**Nguyên tắc:** định nghĩa mục đích pháp lý, bảo mật, vận hành và nghiệp vụ của từng nhóm dữ liệu trước khi quyết định nơi lưu. Không mặc định mọi framework logging đáp ứng yêu cầu kiểm toán của tổ chức.

## 4. Phạm vi những hành động cần kiểm toán

Không cần lưu mọi lần read của tất cả cache keys, nhưng những sự kiện ảnh hưởng dữ liệu hoặc quyền quan trọng thường cần được xem xét:

- Tạo, sửa, xóa, chuyển trạng thái hoặc khôi phục tài nguyên nghiệp vụ.
- Cấp/thu hồi quyền, thay vai trò, khóa/mở tài khoản, đổi chính sách truy cập.
- Xem, xuất, tải xuống hoặc chia sẻ dữ liệu nhạy cảm khi chính sách yêu cầu.
- Thay đổi cấu hình production, feature flag, secret reference hoặc runtime identity.
- Giao dịch tài chính, hoàn tiền, đối soát, sửa dữ liệu thủ công.
- Job migration, backfill, correction, bulk update và replay message.
- Phê duyệt, từ chối, override hoặc thay đổi người sở hữu một quy trình.
- Thay đổi schema, transformation, data quality rules hoặc nguồn dữ liệu của báo cáo.
- Truy vấn/copy/xuất dữ liệu audit hoặc thay đổi policy retention.

### 4.1. Ma trận hành động

| Loại tài nguyên | Ví dụ action | Bằng chứng cần lưu |
|---|---|---|
| Đơn hàng | `ORDER_ADDRESS_CHANGED` | Actor, order ref, các field đã đổi ở mức an toàn, version trước/sau, outcome |
| Thanh toán | `PAYMENT_REFUND_APPROVED` | Ai phê duyệt, role, approval ID, số tham chiếu được phép, kết quả |
| Quyền truy cập | `ROLE_GRANTED` | Actor, target principal, role, scope, policy version, lý do/approval |
| Hồ sơ | `CUSTOMER_RECORD_EXPORTED` | Actor, resource class, số lượng/bộ lọc an toàn, purpose, destination được duyệt |
| Cấu hình | `PROD_CONFIG_UPDATED` | Identity triển khai, config revision, namespace/service, change ticket |
| Pipeline dữ liệu | `TRANSFORM_JOB_COMPLETED` | Input dataset versions, code commit, output version, job run, quality status |
| Dữ liệu hàng loạt | `BULK_CORRECTION_APPLIED` | Change request, số record đã sửa, batch ID, dry-run evidence, outcome |

Chỉ ghi các **trường thực sự có nhu cầu giải trình**. Audit logging không cấp quyền thu thập mọi PII hoặc secret. Những dữ liệu như số thẻ, mật khẩu, token, raw request body và thông tin xác thực không được tự động đưa vào audit event.

## 5. Một audit event phải trả lời những câu hỏi gì?

Một sự kiện kiểm toán có thể theo cấu trúc:

~~~text
Who      = ai/định danh dịch vụ nào thực hiện?
What     = hành động nào, trên loại tài nguyên nào?
When     = lúc nào, theo clock nào?
Where    = service, environment, tenant, region?
Why      = business reason, approval hoặc change request nào?
How      = API/job/command, identity, auth context nào?
Outcome  = succeeded, denied, failed, pending?
Link     = event, request, trace, transaction, version nào liên quan?
~~~

Không phải field nào cũng luôn có. Nhưng schema phải cho phép phân biệt rõ những gì **đã quan sát**, những gì **không biết**, và những gì **chỉ do client tự khai**. Không lấy `userId` từ body rồi xem là actor tin cậy nếu request chưa được xác thực.

### 5.1. Ví dụ JSON sự kiện kiểm toán

~~~json
{
  "eventId": "2df5101d-fd53-4bba-b090-4da9788b8c68",
  "schemaVersion": 2,
  "eventType": "ORDER_SHIPPING_METHOD_CHANGED",
  "occurredAt": "2026-11-12T03:15:24.112Z",
  "recordedAt": "2026-11-12T03:15:24.285Z",
  "environment": "production",
  "service": "order-service",
  "tenantRef": "tenant-42",
  "actor": {
    "type": "USER",
    "subjectRef": "user-ref-7b91",
    "authenticationMethod": "OIDC",
    "onBehalfOf": null
  },
  "resource": {
    "type": "ORDER",
    "reference": "order-ref-7812",
    "versionBefore": 17,
    "versionAfter": 18
  },
  "action": "UPDATE",
  "outcome": "SUCCEEDED",
  "changes": [
    {
      "field": "shippingMethod",
      "before": "STANDARD",
      "after": "EXPRESS"
    }
  ],
  "reasonCode": "CUSTOMER_REQUEST",
  "requestId": "req-8b72",
  "traceId": "acbd18db4cc2f85cedef654fccc4a4d8",
  "changeRequestId": null,
  "origin": {
    "entryPoint": "HTTP_API",
    "operation": "PATCH /orders/{id}"
  }
}
~~~

Định danh trên chỉ là ví dụ và không mang dữ liệu thật. Các trường `subjectRef`, `tenantRef`, `orderRef` dù trông vô hại vẫn có thể liên kết đến cá nhân; chúng cần phân quyền, retention và quy tắc truy xuất. `traceId` giúp điều tra kỹ thuật nhưng **không phải bằng chứng xác thực danh tính**.

### 5.2. Quy tắc schema

- `eventId` toàn cục đủ duy nhất để deduplication, thường UUID hoặc định danh theo chính sách.
- `schemaVersion` cho phép consumer hiểu cấu trúc cũ và mới.
- `eventType` và `action` là enum hữu hạn, tránh biến message tùy ý thành category.
- `occurredAt` là thời điểm nghiệp vụ/hành động xảy ra; `recordedAt` là thời điểm audit system nhận hoặc lưu.
- `actor` được tạo từ security context đã xác thực, có thể là USER, SERVICE, JOB hoặc ADMIN.
- `resource.reference` chỉ rõ đối tượng; nếu đó là ID nhạy cảm thì dùng reference đã được kiểm soát.
- `versionBefore`/`versionAfter` hỗ trợ thứ tự thay đổi của **một thực thể**.
- `outcome` phản ánh kết quả thực tế, không đánh dấu SUCCEEDED trước khi transaction commit.
- `reasonCode` hỗ trợ giải trình; không nhập raw nội dung khách hàng hoặc token.
- `traceId`, `requestId`, `causationId` hỗ trợ liên hệ chéo hệ thống nhưng không thay thế actor.
- `origin` ghi điểm vào có kiểm soát; tránh raw URL chứa query hoặc header.

Không nên dùng sự kiện audit như một object dump chứa toàn bộ bản ghi trước/sau. Nếu muốn biết field nào đổi, một danh sách field allowlist với giá trị đã phân loại thường an toàn hơn.

## 6. Ai là actor khi thay đổi đi qua nhiều service?

Trong một request có nhiều identity khác nhau:

~~~text
End user:         user-ref-7b91
       |
       v
API Gateway:      gateway-service
       |
       v
Order Service:    orders-service-account
       |
       v
Async Worker:     reconciliation-worker
~~~

Nếu Order Service ghi đơn hàng theo yêu cầu người dùng, actor nghiệp vụ thường là **người dùng đã được xác thực** còn executor là workload. Nếu reconciliation-worker chủ động sửa dữ liệu qua job hàng đêm, actor có thể là **SERVICE/JOB**, đồng thời audit có thể lưu `initiatedBy` là scheduler/change ticket.

Các tình huống cần phân biệt:

- Người dùng trực tiếp thực hiện hành động.
- Admin thao tác **on behalf of** khách hàng theo quy trình được phép.
- Automation service thực hiện một thay đổi đã được phê duyệt.
- Batch job diễn ra theo lịch mà không gắn với một user request.
- Sự kiện đến từ một đối tác bên ngoài với thông tin xác thực riêng.
- Worker xử lý lại message có nguồn từ transaction trước đó.

### 6.1. Không tin trường actor do client tự khai

Không nên:

~~~java
String actor = request.getHeader("X-User-Id");
audit.setActor(actor); // Bất kỳ client nào có thể tự đặt header.
~~~

Nên lấy danh tính từ **principal/authentication context đã xác thực** ở ranh giới đáng tin. Nếu gateway truyền thông tin identity cho downstream, phải có cơ chế xác minh giữa các service như token audience phù hợp, mTLS/service identity và chính sách xóa/ghi đè header inbound không đáng tin.

Đừng coi `traceparent`, `baggage` hoặc `requestId` là nguồn xác thực, vì caller có thể tự gửi giá trị. Các trường này dùng cho correlation, không tự chứng minh ai làm gì.

### 6.2. Dấu vết ủy quyền

Nếu admin thay đổi dữ liệu thay người khác, audit có thể cần:

~~~json
{
  "actor": {
    "type": "ADMIN",
    "subjectRef": "admin-ref-12"
  },
  "onBehalfOf": "customer-ref-83",
  "delegation": {
    "approvalId": "approval-2049",
    "scope": "ORDER_CORRECTION",
    "expiresAt": "2026-11-12T04:00:00Z"
  }
}
~~~

Lý do/phê duyệt phải được ghi từ quy trình thực, không chỉ chuỗi tùy ý để hợp thức hóa thao tác. Một audit event ghi “đã được phê duyệt” không tự chứng minh quyền nếu không thể truy vấn quyết định phê duyệt hoặc policy áp dụng tại thời điểm đó.

## 7. Cùng một thao tác có thể có nhiều thời điểm

Một hành động bắt đầu, hoàn tất và được lưu audit ở các thời điểm khác nhau:

~~~text
10:00:00.000 Request accepted
10:00:00.080 Database committed
10:00:00.095 Outbox event created (cùng transaction)
10:00:00.300 Message published
10:00:02.000 Audit sink ingested
10:00:03.100 Warehouse updated
~~~

Các timestamp cần có ý nghĩa rõ:

- `requestedAt`: request được tiếp nhận.
- `occurredAt`: thời điểm nghiệp vụ được coi đã xảy ra.
- `committedAt`: thời điểm thay đổi được commit, nếu hệ thống cung cấp và cần.
- `publishedAt`: thời điểm phát qua broker.
- `ingestedAt`: thời điểm sink nhận.
- `processedAt`: thời điểm consumer áp dụng.

**Clock giữa nhiều node có thể lệch**, và message có thể đến khác thứ tự. Vì vậy không thể xác định thứ tự mọi sự kiện bằng timestamp đơn thuần. Để tái dựng thay đổi của một entity, cần thêm entity version, sequence number hoặc logical ordering. Với nhiều entity/giao dịch khác nhau, một thứ tự toàn cục có thể không tồn tại hoặc quá tốn kém để bảo đảm.

### Tránh sai lầm về timezone

Ghi timestamp theo chuẩn có offset rõ ràng, thường UTC ISO 8601. Giao diện có thể đổi sang múi giờ người xem, nhưng storage và query phải giữ mốc không mơ hồ. Nếu giờ do client tự khai, phân biệt với giờ server xác thực để tránh tạo “quá khứ” tùy ý.

## 8. Before/after và diff: lưu cái gì?

Một audit event mô tả thay đổi có thể chứa:

1. **Chỉ tên field đã thay đổi**: ít nhạy cảm nhưng không thể xem giá trị trước/sau.
2. **Giá trị dạng enum/nhóm đã chuẩn hóa**: hữu ích nếu không quá chi tiết.
3. **Reference tới bản snapshot được bảo vệ**: giảm raw dữ liệu trong audit system.
4. **Version/digest**: chứng minh đang nói tới phiên bản nào, nhưng không tự hiển thị nội dung.
5. **Diff đầy đủ**: dùng khi thật sự cần, với quyền truy cập, mã hóa, masking và retention nghiêm ngặt.

Ví dụ đổi phương thức vận chuyển có thể lưu:

~~~json
{
  "field": "shippingMethod",
  "before": "STANDARD",
  "after": "EXPRESS"
}
~~~

Nhưng đổi địa chỉ giao hàng không nên tự ghi toàn bộ tên, số nhà, số điện thoại và hướng dẫn vận chuyển vào audit record được nhiều nhóm đọc. Thay vào đó, có thể ghi:

~~~json
{
  "field": "shippingAddress",
  "changeType": "UPDATED",
  "beforeRevision": 6,
  "afterRevision": 7,
  "sensitiveValue": "OMITTED"
}
~~~

Nếu bắt buộc tái dựng dữ liệu cũ, có thể lưu các version vào một kho bản ghi được bảo vệ theo quyền nghiệp vụ, rồi audit chỉ giữ reference/version và lý do. Không dùng hash không khóa của email/địa chỉ làm “ẩn danh” vì có thể bị dò từ từ điển.

## 9. Thiết kế schema có thể mở rộng

Một event schema nên được version hóa, có quy tắc tương thích:

~~~yaml
auditEvent:
  schemaVersion: 3
  required:
    - eventId
    - occurredAt
    - eventType
    - actor
    - resource
    - outcome
  optional:
    - requestId
    - traceId
    - causationId
    - approvalRef
    - changeSet
    - dataLineage
~~~

Đây là YAML khái niệm, không phải schema registry thực thi. Một JSON Schema, Protobuf hoặc Avro schema có thể được quản lý trong registry với version và compatibility rules.

Thay đổi kiểu dữ liệu hoặc ý nghĩa field cũ có thể phá consumer, nhất là khi audit record phải đọc được sau nhiều năm. Thường an toàn hơn khi thêm field tùy chọn với semantics rõ, có default ở consumer và tránh đổi ý nghĩa enum đã phát hành. Nếu cần thay đổi phá tương thích, tạo event type/version mới kèm kế hoạch migration/readers cũ.

### Version là một phần của bằng chứng

Một record `ORDER_UPDATED` có schemaVersion=1 không nên được diễn giải bằng business rules của version=4 nếu semantics đã thay đổi. Để điều tra đúng, có thể phải gắn cả:

- Event schema version.
- Producer service artifact revision/commit.
- Data model/schema revision.
- Transformation version nếu đã qua pipeline.
- Policy/authorization rule version khi cần.
- Reference tới change/deployment record.

## 10. Ba chiến lược ghi audit phổ biến

### 10.1. Ghi trực tiếp từ application

Business service gọi audit repository trong code cùng luồng xử lý. Ưu điểm: hiểu rõ actor, lý do, outcome và domain semantics. Nhược điểm: dễ quên ở code path khác nhau; nếu ghi tới hệ thống audit bên ngoài trong cùng request, lỗi kết nối có thể làm tăng latency hoặc khiến sự kiện bị mất.

~~~text
HTTP Request
   |
   v
Business handler
   +--> update order
   +--> write audit record
~~~

Phải xác định **cùng transaction hay hai transaction**. Nếu chỉ ghi audit sau khi update thành công nhưng audit sink mất kết nối, ứng dụng có thể commit order mà không có audit. Nếu ghi audit trước khi DB commit, audit có thể ghi hành động SUCCEEDED dù business transaction sau đó rollback.

### 10.2. Database trigger hoặc lịch sử bảng

Trigger có thể tạo history row mỗi khi dữ liệu bị INSERT/UPDATE/DELETE ở DB. Ưu điểm: bao phủ nhiều đường thay đổi qua cùng DB, kể cả thao tác script trực tiếp. Nhược điểm: thiếu business actor nếu ứng dụng không truyền trusted context; có thể tốn chi phí ghi; logic trigger khó bảo trì và không nắm các hành động chỉ đọc hoặc gọi API ngoài DB.

Trigger cũng không tự phân biệt “đổi địa chỉ theo khách hàng yêu cầu” và “job sửa lỗi dữ liệu”. Nếu ứng dụng dùng chung DB account, transaction-level context phải được thiết kế có nguồn tin cậy; đừng tin một session variable do bất kỳ người có quyền DB nào cũng đặt được mà không xét ranh giới quyền.

### 10.3. CDC từ transaction log

CDC đọc thay đổi được commit từ WAL/binlog tương ứng và phát tới pipeline. Nó phù hợp khi cần chuyển row changes để dựng materialized view hoặc data lineage. Tuy nhiên, CDC thuần có thể biết “bảng/cột đổi” mà không biết *vì sao* hoặc *ai* là actor đã xác thực.

Không nên lộ toàn bộ row chứa dữ liệu nhạy cảm ra audit topic chỉ vì CDC dễ cấu hình. Nếu cần audit nghiệp vụ, có thể lưu **domain audit/outbox event đã tối thiểu hóa**, rồi CDC phát chính outbox table đó.

## 11. Bài toán dual write và transactional outbox

Giả sử Order Service thay trạng thái đơn hàng trong PostgreSQL, sau đó publish `ORDER_STATUS_CHANGED` sang broker:

~~~text
BEGIN TRANSACTION
  UPDATE orders ...
COMMIT

PUBLISH audit event
~~~

Nếu ứng dụng chết **sau commit DB nhưng trước publish**, business record đã đổi mà downstream audit sink không hề nhận event.

Đảo lại cũng không an toàn:

~~~text
PUBLISH audit event
BEGIN TRANSACTION
  UPDATE orders ...
ROLLBACK
~~~

Audit sink có thể nhận “thành công” dù cập nhật dữ liệu thất bại. Đây là bài toán **dual write**: không có transaction nguyên tử mặc định giữa DB và broker.

### 11.1. Transactional outbox

Ghi thay đổi business và outbox event trong **cùng một DB transaction**:

~~~text
Order Service
    |
    v
BEGIN TRANSACTION
    |
    +--> UPDATE orders SET status = ...
    |
    +--> INSERT INTO audit_outbox (...)
    |
COMMIT
    |
    v
Outbox Relay / CDC
    |
    v
Broker -> Audit Consumer -> Audit Store
~~~

Khi transaction commit, cả business change và outbox row cùng tồn tại; rollback thì cả hai mất. Một relay có thể đọc outbox và publish sau đó. Nếu relay crash giữa publish và đánh dấu đã xử lý, message có thể được phát lại; **consumer phải idempotent**.

Ưu điểm: giảm rủi ro mất audit event do ứng dụng chết ở giữa dual write. Giới hạn: không tự bảo đảm exactly-once end-to-end trên broker và sink, không tự giải quyết ordering mọi service, và không bảo vệ nếu DB gốc đã bị can thiệp ngoài đường write có outbox.

### 11.2. Giao hàng ít nhất một lần và deduplication

Một event có `eventId` duy nhất. Audit consumer có thể dùng unique constraint:

~~~sql
CREATE TABLE audit_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_ref TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_ref TEXT NOT NULL,
    resource_version BIGINT,
    outcome TEXT NOT NULL,
    payload JSONB NOT NULL
);
~~~

Khi consumer nhận cùng event nhiều lần, INSERT theo `event_id` cần bảo đảm không tạo trùng. Nhưng “cùng eventId” và “hai hành động tương tự” không giống nhau: không deduplicate chỉ dựa vào `orderId` hoặc `action` vì một đơn hàng có thể được cập nhật nhiều lần hợp lệ.

### 11.3. Thứ tự sự kiện

Nếu hai thay đổi liên tiếp:

~~~text
Order 7812:
  version 17 -> 18  event A
  version 18 -> 19  event B
~~~

Network và retry có thể khiến B đến trước A. Consumer có thể sắp theo `resourceVersion` khi dựng history, nhưng chỉ nên kết luận về thứ tự của **cùng resource** với version monotonic do nguồn tin cậy cấp. Nếu event thiếu version, cần ghi nhận hạn chế ordering thay vì suy ra mọi thứ từ timestamp ingest.

## 12. Ví dụ SQL: bảng nghiệp vụ và outbox

Giả sử PostgreSQL lưu bảng đơn hàng và outbox:

~~~sql
CREATE TABLE orders (
    order_id UUID PRIMARY KEY,
    tenant_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_audit_outbox_unpublished
  ON audit_outbox (occurred_at)
  WHERE published_at IS NULL;
~~~

Ứng dụng thực hiện một transaction:

~~~sql
BEGIN;

UPDATE orders
   SET status = 'PAID',
       version = version + 1,
       updated_at = now()
 WHERE order_id = :order_id
   AND version = :expected_version;

-- Chỉ INSERT outbox khi UPDATE đã tác động đúng một row.
-- Tất cả dữ liệu actor, outcome và version phải được lấy
-- từ đường xử lý đã xác thực và kết quả DB thực tế.

INSERT INTO audit_outbox (
    event_id, aggregate_type, aggregate_id,
    aggregate_version, event_type, schema_version,
    occurred_at, payload
) VALUES (
    :event_id, 'ORDER', :order_id,
    :new_version, 'ORDER_STATUS_CHANGED', 2,
    now(), :safe_audit_payload
);

COMMIT;
~~~

Đây là SQL minh họa; `:order_id`, `:expected_version` và `:safe_audit_payload` là placeholder của tầng ứng dụng/driver, không phải cú pháp literal để chạy trực tiếp bằng psql. Điều kiện `version` là optimistic concurrency control: nếu UPDATE không tác động đúng một hàng, không được ghi audit thành công tương ứng.

Trong thực tế, cần quyết định quyền của relay, batch size, locking, retry, poison event, cleanup và backlog retention. Không nên xóa outbox row trước khi có bằng chứng publish đúng trạng thái, và việc publish có thể lặp sau lỗi.

## 13. Ví dụ Java Spring Boot: tạo audit record theo domain action

Một cách thiết kế là tách kiểu sự kiện audit khỏi entity nghiệp vụ. Đoạn code sau chỉ minh họa cách tạo **payload an toàn** và ghi bằng transaction; những repository và entity cần được xây dựng theo dự án.

~~~java
public record ActorContext(
        String subjectRef,
        String actorType,
        String tenantRef) {}

public record AuditPayload(
        String eventType,
        String outcome,
        String resourceType,
        String resourceRef,
        long versionBefore,
        long versionAfter,
        String reasonCode,
        String actorRef,
        String actorType,
        String tenantRef,
        String correlationId) {}
~~~

Service xử lý thay đổi:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.UUID;

@Service
public class OrderStateService {
    private final OrderRepository orders;
    private final AuditOutboxRepository auditOutbox;

    public OrderStateService(
            OrderRepository orders,
            AuditOutboxRepository auditOutbox) {
        this.orders = orders;
        this.auditOutbox = auditOutbox;
    }

    @Transactional
    public void markPaid(
            UUID orderId,
            ActorContext actor,
            String correlationId) {

        Order order = orders.findByIdForUpdate(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        long oldVersion = order.getVersion();

        // Domain validation nằm ở đây:
        // actor có quyền thực hiện và transition hợp lệ.
        order.transitionToPaid();
        orders.save(order);

        AuditPayload payload = new AuditPayload(
                "ORDER_STATUS_CHANGED",
                "SUCCEEDED",
                "ORDER",
                order.getAuditReference(),
                oldVersion,
                oldVersion + 1,
                "PAYMENT_CONFIRMED",
                actor.subjectRef(),
                actor.actorType(),
                actor.tenantRef(),
                correlationId
        );

        auditOutbox.insert(
                UUID.randomUUID(),
                "ORDER",
                orderId,
                oldVersion + 1,
                payload
        );
    }
}
~~~

Đây là đoạn minh họa kiến trúc, không phải file Java độc lập có thể compile; `OrderRepository`, `Order`, `AuditOutboxRepository` và exception là kiểu do dự án định nghĩa. Khi dùng optimistic locking/JPA, version thực tế có thể được tăng lúc flush; không đoán `oldVersion + 1` nếu mapping không bảo đảm đúng như vậy. Cần lấy phiên bản đã persist hoặc thực thi UPDATE có điều kiện để gắn version chính xác.

Các điểm cần giữ:

- Actor được lấy từ security context, không từ raw user-supplied header.
- Business write và outbox write dùng **cùng transaction** thật.
- Domain payload chỉ chứa enum/reference/version cần thiết, không dump Order entity.
- Sự kiện SUCCEEDED chỉ tồn tại khi transaction commit; failed/denied attempt nếu cần audit phải được ghi qua đường riêng có semantics rõ.
- Relay chuyển event sau commit; consumer deduplicate bằng `eventId`.
- Correlation ID giúp tìm log/trace tương ứng, không dùng làm quyền xác thực.

### 13.1. Audit hành động thất bại

Một request bị từ chối quyền không có business transaction để commit. Tuy vậy, security audit thường cần ghi `ACCESS_DENIED` hoặc `ADMIN_ACTION_REJECTED`.

Có thể thiết kế một kênh audit riêng cho attempt/outcome, với persistence đáng tin, timeout và policy nếu sink không khả dụng. Phải phân biệt:

- `ATTEMPTED`: ai đã thử hành động.
- `DENIED`: hệ thống đã từ chối theo policy.
- `FAILED`: thực thi bắt đầu nhưng gặp lỗi.
- `SUCCEEDED`: thay đổi đã commit hoặc hành động đã hoàn tất theo định nghĩa.

Không phát `SUCCEEDED` trước commit. Với các hành động có yêu cầu kiểm toán bắt buộc, cần xác định **fail closed hay cho xử lý tiếp nếu audit sink lỗi**; không được ngầm bỏ event bằng một `catch (Exception ignored)`.

## 14. Audit trail và event sourcing khác nhau

**Audit trail** lưu bằng chứng về hành động/thay đổi để giải trình. **Event sourcing** coi chuỗi sự kiện domain là nguồn sự thật để dựng lại trạng thái. Chúng có thể dùng chung một số event nhưng không đồng nhất.

Ví dụ event sourcing:

~~~text
OrderPlaced
  |
PaymentAuthorized
  |
OrderConfirmed
  |
ShipmentCreated
~~~

Dựng lại aggregate có thể replay event theo sequence. Nhưng hệ thống vẫn có thể cần audit cho `AdminViewedOrder`, `PermissionDenied`, `PolicyUpdated`, `ExportRequested` và ai đã phê duyệt override. Những sự kiện này không nhất thiết là domain events dùng dựng Order state.

Event sourcing cũng đòi hỏi quản lý event schema evolution, snapshot, replay side effects, retention và quyền xóa dữ liệu. Không chuyển sang event sourcing chỉ để “có audit”, khi yêu cầu thực chỉ là lịch sử hành động được ghi cùng transaction.

## 15. Data lineage: nguồn gốc và tuyến biến đổi dữ liệu

Một báo cáo tính doanh thu có thể đọc nhiều datasets:

~~~text
Order DB (orders, order_lines)
           |
           +--> CDC
                    |
                    v
             Bronze Orders Events
                    |
                    v
           Normalize + Deduplicate
                    |
                    v
             Silver Orders Table
                    |
                    +-----------> Join Payments
                    |                    |
                    v                    v
             Revenue Transformation (SQL/model v7)
                    |
                    v
              Gold Revenue Daily
                    |
                    v
                 Dashboard
~~~

Khi người dùng thấy tổng doanh thu thay đổi đột ngột, lineage giúp trả lời:

- Chỉ số này dựa vào dataset/table nào?
- Những pipeline/job nào đã tạo ra nó?
- Job chạy lúc nào, với input snapshot/watermark nào?
- Transformation SQL/code revision và schema version nào được dùng?
- Có quality check nào thất bại hoặc dữ liệu được backfill không?
- Ai đã thay đổi logic tính metric?
- Có thể tái tính một ngày cụ thể từ input version cũ không?

**Lineage không chỉ là sơ đồ các mũi tên.** Để điều tra, cần metadata có ID ổn định, phiên bản, timestamp, dataset ownership, job run và quan hệ input→output.

### 15.1. Những mức lineage

| Mức | Câu hỏi | Ví dụ |
|---|---|---|
| **System-level** | Hệ thống nguồn/đích nào liên quan? | PostgreSQL → Kafka → Warehouse |
| **Dataset/table-level** | Bảng hoặc dataset nào tạo ra bảng khác? | `orders` + `payments` → `revenue_daily` |
| **Column-level** | Cột output phụ thuộc vào cột input nào? | `net_revenue` từ `paid_amount` và `refund_amount` |
| **Record-level** | Bản ghi output đến từ các bản ghi input nào? | `daily_total_2026-11-12` từ tập order IDs đã xử lý |
| **Run/version-level** | Job/phiên bản nào tạo kết quả? | Job run `etl-7831`, model `v7`, watermark `T` |

Không phải pipeline nào cũng có khả năng/chi phí phù hợp để giữ record-level lineage cho mọi row. Có thể chọn table/column lineage kết hợp batch ID, watermark và object version để đáp ứng phần lớn nhu cầu, rồi lưu record-level cho những luồng cần đối soát cao.

## 16. Metadata của một lineage event

Ví dụ sự kiện hoàn tất pipeline:

~~~json
{
  "lineageEventId": "lin-20261112-001",
  "jobName": "revenue-daily-build",
  "jobRunId": "etl-7831",
  "producer": "analytics-pipeline",
  "startedAt": "2026-11-12T02:00:00Z",
  "finishedAt": "2026-11-12T02:04:11Z",
  "codeRevision": "git:8cf13b0",
  "transformationVersion": "revenue-model-v7",
  "inputs": [
    {
      "dataset": "silver.orders",
      "snapshot": "2026-11-12T01:59:00Z"
    },
    {
      "dataset": "silver.payments",
      "snapshot": "2026-11-12T01:59:00Z"
    }
  ],
  "outputs": [
    {
      "dataset": "gold.revenue_daily",
      "partition": "date=2026-11-11",
      "version": "run-etl-7831"
    }
  ],
  "quality": {
    "schemaValidated": true,
    "reconciliationResult": "PASS"
  }
}
~~~

Đây là ví dụ metadata, không phải định dạng chuẩn bắt buộc. Dùng ID và snapshot/watermark có semantics rõ; nếu input thay đổi sau khi job chạy mà không có snapshot hoặc reproducible source, không thể chắc chắn tái dựng cùng kết quả.

### 16.1. Lineage ở môi trường streaming

Với streaming, “đầu vào” có thể là:

- Topic/partition/offset ranges.
- Event schema version.
- Consumer group và code revision.
- Processing checkpoint hoặc stream state version.
- Watermark và quy tắc xử lý late events.
- Output topic/partition hoặc DB transaction ID.

Một pipeline có thể xử lý lại event hoặc cập nhật cùng một aggregate nhiều lần. Do đó lineage phải phân biệt **event time**, **processing time**, **replay/backfill run** và tác động đến output version.

## 17. Truy vết một thay đổi xuyên HTTP, RPC và message broker

Ví dụ khách hàng cập nhật địa chỉ giao hàng:

~~~text
Client PATCH /orders/{id}
       |
       v
Gateway
  authenticated subject = user-ref-7b91
  requestId = req-8b72
  traceId = trace-A
       |
       v
Order Service
  writes order version 18
  outbox eventId = event-001
       |
       v
Broker
  messageId = msg-201
  causationId = event-001
       |
       +--> Notification Worker
       |      eventId = event-002
       |      causationId = event-001
       |
       +--> Analytics Consumer
              lineage input = event-001
              output batch = etl-7831
~~~

Các định danh có vai trò riêng:

- **`requestId`:** liên hệ toàn bộ một request.
- **`traceId`:** liên hệ các spans kỹ thuật trong distributed tracing; có thể không đầy đủ nếu sampling.
- **`eventId`:** nhận diện một domain/audit event; dùng deduplication.
- **`causationId`:** chỉ ra event/command trực tiếp dẫn đến event hiện tại.
- **`correlationId`:** liên hệ các phần của một workflow nghiệp vụ kéo dài.
- **`transactionId`:** định danh transaction ở một nguồn, không nhất thiết có phạm vi toàn hệ thống.
- **`jobRunId`:** lần chạy pipeline/batch.
- **`resourceVersion`:** thứ tự thay đổi của một entity trong nguồn.

Không tự đồng nhất mọi ID; không lấy secret hoặc user email làm correlation ID. Dùng một ID client tự khai mà không kiểm soát có thể tạo log injection, đoán được tài nguyên hoặc gây va chạm; cần validate/generate lại ở trust boundary khi thích hợp.

### 17.1. W3C Trace Context và baggage

HTTP/gRPC instrumentation thường truyền `traceparent` và `tracestate` để nối trace. W3C Baggage có thể truyền key–value tùy cấu hình. **Không đưa secret, access token, raw user identifier hoặc PII vào baggage** để phục vụ audit; nó có thể lan qua nhiều service và ra ngoài trust boundary.

Actor/authorization context phải được truyền qua cơ chế bảo mật được xác minh, không lấy từ baggage. Audit trail sử dụng trace ID như một đường tìm evidence bổ trợ, không dựa vào trace để thay cho audit event bền vững.

### 17.2. Message replay và quan hệ nhân quả

Một event có thể được xử lý nhiều lần do at-least-once delivery, retry hoặc replay sau sự cố. Nếu consumer thực thi cùng một thay đổi nghiệp vụ nhiều lần, cần idempotency theo eventId/commandId, và audit cần phân biệt:

- Event gốc được phát một lần theo nguồn.
- Delivery attempt số 1, 2, 3...
- Consumer xử lý thành công hay bị duplicate-suppressed.
- Có phát ra event hậu quả mới không.

Ghi mỗi retry vào audit domain history như một thay đổi hợp lệ sẽ khiến lịch sử nhiễu. Có thể audit riêng **processing attempts** ở lớp vận hành nếu có nhu cầu, nhưng domain state change chỉ nên phản ánh sự thay đổi thực tế.

## 18. Chứng minh tính toàn vẹn của audit log

Một audit record có thể bị sửa hoặc xóa nếu người có quyền rộng truy cập storage. Để dùng làm bằng chứng, cần chính sách bảo vệ **confidentiality, integrity, availability**:

- **Append-only:** ứng dụng chỉ được thêm, không update/delete audit events tùy ý.
- **Quyền tách biệt:** business service gửi event; audit writer ghi; audit reader xem; retention admin có quyền theo policy riêng.
- **Immutable/WORM storage khi cần:** cơ chế khóa retention có kiểm soát để giảm khả năng sửa/xóa.
- **Mã hóa:** TLS khi truyền, mã hóa storage/backup, key management và rotation phù hợp.
- **Audit truy cập audit:** xem, export, thay retention hoặc thay policy phải có lịch sử riêng.
- **Giám sát:** phát hiện gap, event drop, thay đổi khối lượng hoặc hành vi xuất dữ liệu bất thường.
- **Integrity verification:** hash chain, signature hoặc checkpoint bất biến theo yêu cầu.

Không thể coi một bảng database chỉ “cấm UPDATE qua API ứng dụng” là bất biến tuyệt đối. Admin DB, chủ hệ thống backup hoặc người có quyền hạ tầng có thể sửa dữ liệu nếu không có kiểm soát độc lập.

### 18.1. Hash chain: hữu ích nhưng có giới hạn

Một thiết kế minh họa:

~~~text
recordHash[0] = H(canonical(record[0]))
recordHash[1] = H(recordHash[0] || canonical(record[1]))
recordHash[2] = H(recordHash[1] || canonical(record[2]))
...
~~~

Mỗi record chứa previous hash để phát hiện sửa đổi/lược bỏ ở giữa một chuỗi **nếu có checkpoint đáng tin**. Cần serialization canonical rõ, thuật toán đã được phê duyệt và cách kiểm soát thứ tự ghi; hai writer song song phải phối hợp tạo chuỗi hoặc dùng batch/partition chains.

**Giới hạn quan trọng:** kẻ có quyền thay toàn bộ dữ liệu lẫn các hash có thể tính lại cả chuỗi nếu không có root hash/signature/checkpoint được giữ ở một nơi độc lập mà họ không kiểm soát. Hash chain đơn thuần không chứng minh ai đã tạo event, không thay thế authorization và không đảm bảo event chưa bao giờ bị bỏ ngay từ nguồn.

Có thể dùng:

- Digital signatures với private key nằm ngoài quyền của audit writer.
- Periodic digest/checkpoint lưu ở kho độc lập hoặc WORM.
- Merkle tree cho batch lớn, cùng cơ chế công bố/neo root đáng tin.
- Key rotation và xác minh signatures qua nhiều phiên bản khóa.
- Gap detection trên event sequence hoặc source checkpoint.

Định nghĩa rõ threat model: bảo vệ trước accidental modification, account compromise, privileged insider hay mất entire region? Không có một cơ chế hashing đơn lẻ giải quyết mọi lớp.

## 19. Lưu trữ audit và retention

Audit logs có thể cần giữ lâu hơn operational logs, nhưng thời gian chính xác phụ thuộc yêu cầu kinh doanh, hợp đồng, pháp luật và phân loại dữ liệu. Không dùng một TTL mặc định cho mọi loại event.

Thiết kế retention cần xác định:

1. Loại event và mức độ nhạy cảm.
2. Mục đích và cơ sở lưu trữ dữ liệu.
3. Thời gian cần để điều tra hoặc đối soát.
4. Quyền đọc/xuất, vùng địa lý lưu trữ và backup.
5. Quá trình archive, delete hoặc legal hold khi áp dụng.
6. Tính toàn vẹn trong suốt vòng đời.
7. Cách xử lý yêu cầu xóa/correction dữ liệu cá nhân và các trường hợp có nghĩa vụ giữ lại.
8. Cách chứng minh xóa theo quy trình mà không làm mất bằng chứng bắt buộc.

**Không có nghĩa audit càng lâu càng tốt.** Việc giữ raw PII vô thời hạn tạo rủi ro riêng tư; ngược lại, xóa sự kiện bắt buộc trước retention yêu cầu có thể phá khả năng điều tra. Giải pháp là tối thiểu hóa dữ liệu trong event, phân tách kho dữ liệu nhạy cảm, quyền, mã hóa và retention theo chính sách.

### 19.1. Địa chỉ hóa mâu thuẫn “immutable” và “xóa dữ liệu”

Nếu cần xóa thông tin nhận dạng nhưng phải giữ evidence thay đổi, có thể thiết kế event không chứa PII thô từ đầu, dùng reference có vòng đời riêng và thực thi các quy tắc pseudonymization, tokenization hoặc crypto-shredding đã được đánh giá. Không tự tuyên bố việc băm email là ẩn danh hoặc việc phá khóa luôn đáp ứng mọi nghĩa vụ pháp lý; phải xét threat model, bản sao và các quy định áp dụng.

## 20. Phân quyền tra cứu và xuất audit

Người dùng hệ thống audit có thể thuộc nhiều vai trò:

| Vai trò | Quyền gợi ý |
|---|---|
| Service writer | Gửi event đúng schema/phạm vi, không đọc toàn bộ lịch sử |
| Service owner | Đọc event của service/resource được phân quyền |
| Security investigator | Tra cứu hành động bảo mật trong phạm vi vụ việc |
| Compliance/audit reviewer | Đọc bằng chứng và evidence bundle được duyệt |
| Platform operator | Quản trị hạ tầng, không mặc định đọc mọi nội dung nhạy cảm |
| Retention administrator | Thực hiện retention/legal hold theo quy trình có audit |
| Key administrator | Quản lý khóa, tách khỏi quyền tùy ý sửa event |

Thực thi:

- Authentication mạnh, least privilege và phân quyền theo tenant/environment/resource.
- Row-level/attribute-level access khi cần.
- Giới hạn tìm kiếm theo thời gian và khối lượng export.
- Masking field nhạy cảm trước UI và API, kết hợp bảo vệ ở storage/pipeline.
- Audit chính hành động truy vấn, export và thay đổi quyền.
- Cơ chế truy cập khẩn cấp có thời hạn, lý do và review sau sử dụng.

Một API `GET /audit?tenantId=...` không an toàn chỉ vì query parameter có tenantId; backend phải xác minh tenant scope với principal. Đừng dựa vào việc client chỉ hiển thị bộ lọc tenant của mình.

## 21. Query điển hình khi điều tra thay đổi

Một investigation có thể bắt đầu từ resource reference và time window:

~~~sql
SELECT
    event_id,
    occurred_at,
    event_type,
    actor_ref,
    resource_version,
    outcome,
    payload ->> 'reasonCode' AS reason_code
FROM audit_events
WHERE resource_type = 'ORDER'
  AND resource_ref = :order_ref
  AND occurred_at >= :window_start
  AND occurred_at < :window_end
ORDER BY resource_version, occurred_at, event_id;
~~~

Với dữ liệu thay đổi có thứ tự version, nên ưu tiên version để tái dựng trạng thái của entity; occurredAt là điểm tham chiếu thời gian. Query phải được thực thi qua một lớp **authorization** kiểm soát user/tenant/resource, không cho người dùng nối SQL tùy ý.

### Một chuỗi điều tra minh họa

1. Xác định order reference và version hiện tại từ nguồn nghiệp vụ.
2. Tìm các audit events làm đổi trạng thái qua time window liên quan.
3. So sánh version tăng liên tiếp, phát hiện gap hoặc duplicate.
4. Kiểm tra actor và policy/approval reference được ghi khi thực thi.
5. Dùng requestId/traceId tìm các bước kỹ thuật, lưu ý tracing có thể sampled.
6. Nếu có async event, theo eventId/causationId đến consumer và downstream.
7. Nếu số liệu báo cáo sai, dùng lineage jobRunId để truy từ output về input versions và transformation revision.
8. Ghi rõ nguồn dữ liệu nào đã kiểm chứng, nguồn nào không có, và giới hạn của kết luận.

Không tự suy ra “không có hành động” chỉ vì không tìm thấy event khi pipeline còn đang lag hoặc retention đã hết. Cần kiểm tra health của audit ingestion, outbox backlog, clock window và partition query.

## 22. Audit đối với thay đổi quyền và truy cập dữ liệu

Hành động cấp quyền, thu hồi quyền và export dữ liệu thường có rủi ro riêng:

~~~text
Admin requests role grant
        |
        v
AuthZ policy evaluation
        |
        +-- DENIED --> Audit denial attempt
        |
        v
Approval check
        |
        +-- FAILED --> Audit rejection
        |
        v
Write role membership
        |
        v
Audit role granted (policy version, actor, target, scope)
~~~

Lưu ý:

- Subject nhận quyền và actor cấp quyền là hai vai trò khác nhau.
- Có thể cần ghi cả requested scope và effective scope sau policy validation.
- Cấp quyền tạm cần expiration và nguyên nhân phê duyệt.
- Đổi policy có thể làm quyền hiệu lực thay đổi mà không có sự kiện cấp role trực tiếp.
- Nếu quyền được cache, audit thời điểm policy commit không tự chứng minh mọi service đã áp dụng ngay; cần theo dõi propagation và correctness.
- Truy cập dữ liệu nhạy cảm có thể phải audit cả **read/export**, không chỉ write.

Audit event không nên chứa access token hoặc full permission claim JWT. Định danh role/policy version và actor reference thường đủ để truy lại quyết định trong kho identity được bảo vệ.

## 23. Audit thay đổi schema, cấu hình và triển khai

Dữ liệu có thể đổi do code mới hoặc migration chứ không phải một người sửa trực tiếp bản ghi.

Một release record có thể chứa:

~~~json
{
  "changeType": "DATABASE_MIGRATION_APPLIED",
  "service": "order-service",
  "environment": "production",
  "migrationId": "V20261112_03__add_order_revision",
  "sourceCommit": "git:8cf13b0",
  "artifactDigest": "sha256:<verified-digest>",
  "changeRequestRef": "chg-204",
  "executor": "deploy-job-service",
  "outcome": "SUCCEEDED",
  "occurredAt": "2026-11-12T03:10:00Z"
}
~~~

Không nhúng secrets/config values thô. Với migrations/backfills, theo dõi:

- Job run, migration script revision và schema version.
- Số bản ghi dự kiến/đã tác động, checkpoint, error count.
- Data quality và integrity checks trước/sau.
- Khả năng rollback/roll-forward hoặc restore.
- Source input snapshot/backup reference khi áp dụng.
- Ai phê duyệt và ai thực thi qua CI/CD.

Nếu một pipeline chạy lại bản SQL mới nhưng dùng cùng `jobName`, output có thể khác dù nguồn dữ liệu không đổi. Vì vậy lineage cần **code revision**, không chỉ tên pipeline.

## 24. Sự kiện audit với các hành động khối lượng lớn

Backfill hàng triệu bản ghi có thể tạo số lượng audit rows rất lớn nếu mỗi row đều ghi đủ before/after.

Các chiến lược:

- **Per-record events** khi yêu cầu forensic chi tiết.
- **Batch summary event** với batch ID, query/filter được phê duyệt, số row, version và output checkpoint.
- **Snapshot/manifest reference** tới danh sách row IDs được bảo vệ khi cần tái dựng.
- **Hybrid:** sự kiện cấp batch và sự kiện chi tiết cho những thay đổi đặc biệt.
- **Chunked migration:** mỗi chunk có ID, range, checksum và trạng thái, hỗ trợ resume.

Trade-off: chỉ lưu tổng số row không thể trả lời cụ thể bản ghi nào đã thay đổi; nhưng giữ toàn bộ giá trị dữ liệu thô trong audit có thể vi phạm tối thiểu hóa. Chọn độ chi tiết dựa trên rủi ro, nghĩa vụ chứng minh và storage/cost.

### Một batch event an toàn

~~~json
{
  "eventType": "BULK_CORRECTION_COMPLETED",
  "batchId": "correction-287",
  "resourceType": "ORDER",
  "selectionRef": "approved-query-19",
  "recordsAttempted": 1200,
  "recordsUpdated": 1187,
  "recordsRejected": 13,
  "sourceSnapshotRef": "snapshot-20261112-001",
  "changeRequestRef": "chg-204",
  "outcome": "PARTIAL_SUCCESS"
}
~~~

Khi có partial success, phải định nghĩa cách tìm và retry những record thất bại mà không nhân đôi sự kiện cho record đã sửa. Cần phân biệt total attempted, actually changed, skipped và failed.

## 25. Dữ liệu nhạy cảm trong audit trail

Audit có thể bị truy cập bởi nhiều bộ phận hơn kho nghiệp vụ. Vì vậy tối thiểu hóa là bắt buộc về thiết kế.

**Không đưa trực tiếp** vào audit: password, API keys, session cookies, access/refresh tokens, private keys, OTP, số thẻ, mã bảo mật, raw authorization header, request/response body không được phân loại, SQL parameter chứa PII.

Nên dùng:

- Field names theo allowlist.
- Enum trạng thái/mã nguyên nhân.
- Version và reference phù hợp.
- Mã tenant được bảo vệ trong index truy vấn.
- Snapshot/secure record reference khi cần đọc dữ liệu cũ qua API có phân quyền.
- Dữ liệu tổng hợp có kích thước/giới hạn, không chứa nội dung khách hàng.

### 25.1. Masking và hashing không phải phép màu

Che bớt email có thể vẫn nhận dạng được người dùng trong tập nhỏ; hash không khóa của email/số điện thoại có thể bị dò. HMAC có khóa hoặc tokenization giúp giảm rủi ro nhất định nhưng vẫn cần quản lý khóa, retention, khả năng liên kết và quyền truy cập. Đừng lưu hash của secret rồi coi như an toàn tuyệt đối, nhất là với secret có không gian đoán nhỏ.

### 25.2. Ranh giới tổ chức và tenant

Một central audit sink nhận events từ nhiều tenant/services phải áp validation: producer nào được gửi event cho resource scope nào? Nếu producer A có thể tự đặt `tenantRef=B`, hệ thống có thể tạo bằng chứng giả hoặc làm lộ dữ liệu qua API. Có thể tách authenticated producer identity, tenant scope và resource ownership để kiểm tra chéo khi ingest.

## 26. Khi audit sink không khả dụng

Thiết kế phải quyết định rõ sự đánh đổi giữa phục vụ nghiệp vụ và bảo đảm audit:

| Tình huống | Rủi ro | Chiến lược |
|---|---|---|
| Audit API đồng bộ timeout | Business request chậm/thất bại | Tránh synchronous external dual write; dùng outbox khi phù hợp |
| Broker không nhận message | Event chưa được chuyển | Outbox còn bền vững; relay retry có giới hạn và alert |
| Audit consumer lỗi deserialize | Có thể bỏ event | Dead-letter/quarantine và quy trình sửa/replay không làm rơi sự kiện |
| Audit database đầy | Ingestion lag tăng | Capacity alert, backpressure, retention/archival có kiểm soát |
| Relay publish rồi crash | Event duplicate | Idempotent consumer dựa trên eventId |
| Source DB transaction rollback | Không nên có success audit | Ghi outbox trong cùng transaction |
| Security denial khi DB không đổi | Bỏ sót attempts nếu chỉ dùng outbox business | Kênh audit attempts riêng có durability và policy |
| Mất network giữa regions | Audit events đến trễ/out of order | Buffer an toàn, ordering theo resourceVersion, watermark và lag metrics |

Một số hành động bảo mật hoặc pháp lý có thể bắt buộc **không thực hiện nếu không thể ghi audit bền vững** (fail closed). Một số hành động đọc public ít rủi ro có thể tiếp tục trong degraded mode. Chính sách này phải được định nghĩa theo event class, không chọn ngầm khi exception xảy ra.

### 26.1. Không nuốt lỗi

Không nên:

~~~java
try {
    auditClient.write(event);
} catch (Exception ignored) {
    // Quên event và tiếp tục xử lý.
}
~~~

Đường ghi audit phải có retry/queue/outbox hoặc cơ chế fail-closed theo chính sách, cùng metric và cảnh báo. Dù dùng outbox, cần monitor backlog để biết khi nào dữ liệu “đã commit nhưng chưa có ở audit sink”.

## 27. Observability cho chính pipeline audit

Nếu không biết audit pipeline có hoạt động hay không, việc “không thấy sự kiện” không phải bằng chứng rằng không có sự kiện.

Các metric minh họa:

| Metric | Ý nghĩa |
|---|---|
| `audit_events_created_total{event_type}` | Event được tạo thành công ở nguồn |
| `audit_outbox_pending_total{service}` | Số outbox rows chưa publish |
| `audit_outbox_oldest_age_seconds` | Tuổi sự kiện cũ nhất chưa gửi |
| `audit_relay_publish_total{outcome}` | Số lần relay publish thành công/thất bại |
| `audit_consumer_ingest_total{outcome}` | Kết quả ingestion ở sink |
| `audit_duplicate_events_total` | Sự kiện trùng bị nhận diện |
| `audit_schema_rejections_total{reason}` | Events không đạt validation |
| `audit_event_lag_seconds` | Chênh lệch thời gian nguồn và sink |
| `audit_sequence_gaps_total` | Phát hiện gap theo entity/partition khi có sequence |
| `audit_integrity_verification_total{result}` | Kết quả kiểm tra hash/signature/checkpoint |
| `lineage_job_runs_total{outcome}` | Số pipeline runs và trạng thái |
| `lineage_output_freshness_seconds` | Độ mới của dataset output |

Tên metric chỉ minh họa. Labels phải có cardinality hữu hạn; không đưa eventId, resourceId, user email, raw tenant ID hoặc token làm label. Dùng logs/traces theo scope bảo mật để điều tra cụ thể nếu cần.

### Cảnh báo có thể quan trọng hơn tỷ lệ lỗi HTTP

- Outbox backlog không giảm qua nhiều lần retry.
- Audit sink ingestion chậm vượt SLO.
- Tăng đột biến denied role-grants hoặc data exports.
- Schema rejection xuất hiện sau rollout producer mới.
- Không tạo audit events trong khi business changes vẫn xảy ra.
- Chuỗi integrity checkpoint không xác minh được.
- Lineage job hoàn tất nhưng data quality hoặc reconciliation thất bại.
- Actor reference biến thành UNKNOWN bất thường trong một service.

## 28. Kiểm thử tính đầy đủ và đúng đắn

Một bộ test nên kiểm tra **sự kiện thực sự được ghi khi nghiệp vụ thành công**, không chỉ unit test serializer.

### 28.1. Unit tests

- Mapping domain action sang eventType và outcome chính xác.
- Không có field cấm trong payload.
- Actor lấy từ trusted security context.
- Missing principal được phân loại rõ, không giả mạo thành user.
- Schema có required fields và enum đúng.
- Sensitive field changes chỉ ghi changeType/version, không ghi raw value.

### 28.2. Integration tests

- Business transaction thành công → entity version tăng và outbox row được commit cùng nhau.
- Business transaction thất bại → không có success event.
- Optimistic lock thất bại → không ghi version mới giả.
- Relay publish success → audit sink nhận đúng event.
- Relay crash sau publish → consumer xử lý duplicate theo eventId.
- Audit sink tạm unavailable → outbox tồn tại và được retry sau khi hồi phục.
- Consumer gặp schema chưa hỗ trợ → quarantine/DLQ, không silently discard.
- Replayed event → không đổi domain state lần thứ hai nếu đã xử lý.
- Actor/tenant giả từ request header → không được tin.
- Query audit với user thuộc tenant khác → bị từ chối.
- Sau migration hoặc bulk update → batch summary và row-level evidence khớp theo policy.

### 28.3. Fault-injection tests

Mô phỏng:

1. Kill service ngay sau business commit.
2. Làm broker timeout khi outbox relay publish.
3. Kill relay giữa publish và mark published.
4. Đưa duplicate messages theo nhiều thứ tự.
5. Làm audit store unavailable trong một khoảng an toàn.
6. Gửi timestamp lệch nhau giữa nhiều services.
7. Chạy schema version cũ/mới cùng lúc khi rollout.
8. Tăng backlog để kiểm tra alert và capacity.
9. Kiểm tra recovery/replay sau failover.
10. Cố sửa/xóa một audit record bằng một identity không có quyền.

Không thử xóa dữ liệu audit production chỉ để kiểm tra immutable policy. Dùng môi trường/định danh test, dữ liệu giả, guardrails và quyền được phê duyệt.

## 29. Đánh giá độ đầy đủ của audit trail

Không thể khẳng định “có audit 100%” chỉ vì mọi request đi qua middleware. Phải xác định **tập thay đổi gốc** để đối chiếu.

Ví dụ:

~~~text
Trong một giờ:
  Số business commits cần audit: 1.000
  Số outbox events đã tạo:      1.000
  Số events sink nhận unique:   995
  Số events đang pending:         5
~~~

Nếu năm event còn trong outbox và chưa quá SLO ingestion, kết quả có thể là pipeline đang trễ chứ chưa mất sự kiện. Nếu sau thời hạn vẫn thiếu, phải điều tra gap. Đối chiếu nên dựa trên transaction/event IDs có nguồn gốc tin cậy và quy tắc dedup, không chỉ tổng count vì duplicates có thể che thiếu.

### Reconciliation theo partition hoặc window

- Source transaction IDs hoặc version ranges.
- Outbox event IDs và commit timestamps.
- Broker offsets/watermarks.
- Sink unique event IDs.
- Gap/duplicate counts.
- Job run/checkpoint của pipeline.
- Data quality checks cho đầu ra.

Khi đạt tiêu chí, lưu evidence của đợt reconciliation. Một dashboard hiện “audit healthy” không tự chứng minh được tất cả thay đổi quá khứ nếu chưa định nghĩa phạm vi kiểm tra.

## 30. Quy trình điều tra một bản ghi bị đổi bất thường

Ví dụ khách hàng báo địa chỉ giao hàng đã bị thay đổi mà họ không thực hiện.

### Bước 1 — Bảo toàn bối cảnh

Ghi reference đơn hàng, time window, thời điểm phát hiện, phiên bản bản ghi và người tiếp nhận yêu cầu. Không copy địa chỉ thật vào kênh điều tra quyền rộng.

### Bước 2 — Truy audit history

Tìm các `ORDER_SHIPPING_ADDRESS_CHANGED` events theo resourceRef, version và timestamp. Ghi eventId, actor type, subjectRef, reasonCode và outcome.

### Bước 3 — Kiểm tra identity

Xác minh principal và authentication decision tại thời điểm thay đổi. Nếu actor là admin acting-on-behalf-of, kiểm tra delegation/approval. Nếu là service, kiểm tra jobRunId/change ticket.

### Bước 4 — Dò quan hệ nhân quả

Dùng requestId/traceId và causationId để tìm API request, async processing, retries và event hậu quả. Không dựa vào trace duy nhất khi sampling làm mất spans.

### Bước 5 — Đối chiếu phiên bản và nguồn dữ liệu

So sánh resource version tại DB, outbox events, sink unique IDs và trạng thái replication. Tìm gap, duplicate hoặc out-of-order events.

### Bước 6 — Xác định ảnh hưởng downstream

Sự kiện đã khiến Notification Worker gửi email hay Analytics pipeline thay đổi dữ liệu chưa? Dò lineage hoặc event chain; ghi rõ hệ thống nào có bản cũ/bản mới.

### Bước 7 — Xử lý theo chính sách

Nếu xác nhận thay đổi sai trái, cần khóa/thu hồi quyền, điều tra an ninh, khôi phục dữ liệu qua thao tác nghiệp vụ có audit riêng và thực hiện nghĩa vụ thông báo nếu có. Không sửa lịch sử audit cũ để “xóa dấu vết”; ghi event correction và lý do.

### Bước 8 — Kết luận có giới hạn

Phân biệt “không thấy event” với “đã chứng minh event không xảy ra”. Đề cập missing telemetry, retention, các đường thay đổi ngoài API, clock skew hoặc gap nếu tồn tại.

## 31. Lineage cho báo cáo bị thay đổi sau backfill

Một ngày báo cáo doanh thu thay đổi từ 1,2 tỷ sang 1,15 tỷ sau khi nhóm dữ liệu chạy backfill.

Đường điều tra:

~~~text
Dashboard metric version
       |
       v
Gold revenue partition date=D
       |
       v
Transform run R2 / code revision v7
       |
       +--> Silver orders snapshot S1
       |
       +--> Silver payments snapshot S2
       |
       +--> Deduplication policy P3
       |
       v
Source event offsets / CDC commits
~~~

Cần phân biệt:

- Báo cáo ban đầu được tính bởi run R1 hay R2?
- Input snapshots/watermark có khác không?
- SQL/model có đổi không?
- Dữ liệu nguồn được correction sau R1 không?
- Quy tắc loại trùng event có thay đổi không?
- R2 có được phê duyệt theo change record không?
- Quality reconciliation có đạt không?
- Có thể tái tính kết quả trước và sau bằng đúng input versions không?

Nếu chỉ biết “pipeline chạy lúc 2 giờ” mà không có input versions và code revision, rất khó chứng minh nguồn gốc số liệu. Audit của việc thay SQL và lineage của run R2 phải được nối với nhau.

## 32. Chống tạo lịch sử giả và kiểm soát nhà sản xuất sự kiện

Một central audit service có thể nhận event từ hàng chục microservices. Nếu mọi service có thể tạo bất kỳ eventType và actorRef, hệ thống dễ bị giả mạo nguồn.

Thiết kế có thể bao gồm:

- Authentication producer bằng mTLS hoặc workload identity.
- Phân quyền event types và resource scopes theo từng producer.
- Schema validation và reject/quarantine payload sai.
- Kiểm tra actor claims dựa trên trusted context, không chỉ chuỗi trong JSON.
- Rate limits và quotas để một service bị lỗi không làm sập sink.
- Gắn authenticated producer identity ở phía ingest, không tin hoàn toàn trường `service` tự khai.
- Kết nối eventId với source transaction/outbox khi có.
- Phân tách quyền writer và quyền quản trị retention/integrity.

Có thể có trường `claimedActor` từ domain và `authenticatedProducer` từ transport để phân biệt hai tầng tin cậy; đừng âm thầm coi cả hai là cùng một identity.

## 33. Chỉ mục và truy vấn ở quy mô lớn

Audit events có thể tăng theo số giao dịch. Một kho dữ liệu kiểm toán cần phục vụ truy vấn phổ biến:

- Theo resourceRef + occurredAt.
- Theo actorRef + time window.
- Theo eventType/outcome + time window.
- Theo tenant/environment theo scope quyền.
- Theo requestId/traceId/eventId.
- Theo jobRunId, data pipeline hoặc schemaVersion.
- Theo approval/change request reference.

Chỉ mục phải cân bằng write throughput, storage overhead, retention và khả năng lọc tenant. Với lượng lớn có thể partition theo thời gian hoặc tenant phù hợp; nhưng cần tránh khiến một investigation phải quét toàn bộ lịch sử không giới hạn.

### Query safety

- Bắt buộc giới hạn time window và số bản ghi trả về.
- Phân quyền server-side trước khi query.
- Giới hạn export, phân trang và audit truy cập.
- Không log raw SQL parameters/PII trong query diagnostic.
- Không cho untrusted client chọn trực tiếp tên bảng/column bất kỳ.
- Có retention/archival strategy để dữ liệu lâu năm vẫn có thể tra cứu theo quy trình.

Không dùng hệ thống observability thông thường làm kho audit duy nhất nếu không đáp ứng yêu cầu integrity, access control và retention đã được xác định.

## 34. Quy trình đưa audit/lineage vào một microservice mới

**Bước 1 — Xác định câu hỏi cần giải trình.** Ai đổi dữ liệu, tại sao, nguồn nào, quyền nào, retention bao lâu? Phân loại hành động bắt buộc.

**Bước 2 — Thiết kế schema event.** Field bắt buộc, enum, actor, resource, outcome, version, correlation, causation và dữ liệu nhạy cảm bị loại.

**Bước 3 — Xác định trust boundary.** Principal từ đâu, service identity từ đâu, tenant scope được kiểm tra ở đâu, có đường admin/job đặc biệt không.

**Bước 4 — Chọn cơ chế capture.** Application domain events, database trigger, CDC hoặc outbox; phân biệt yêu cầu nghiệp vụ với row-level history.

**Bước 5 — Bảo đảm transaction/delivery semantics.** Business commit/outbox atomically nếu dùng chung DB; relay at-least-once, consumer idempotent và có recovery.

**Bước 6 — Chọn kho audit.** Append-only policy, encryption, RBAC, integrity verification, backup và retention.

**Bước 7 — Thiết kế index/query và truy cập.** Resource/actor/time, tenant isolation, export controls và audit việc đọc audit.

**Bước 8 — Nối nguồn gốc dữ liệu.** Dataset IDs, jobRun IDs, input snapshots/watermarks, code revisions, output versions và quality checks.

**Bước 9 — Viết kiểm thử.** Success/fail/denied, rollback, retries, duplicate, out-of-order, sink outage, schema upgrade và actor spoofing.

**Bước 10 — Theo dõi và reconciliation.** Source commits ↔ outbox ↔ broker ↔ sink, lag, gaps và integrity checkpoints.

**Bước 11 — Diễn tập điều tra.** Đưa một thay đổi tổng hợp vào môi trường test rồi yêu cầu nhóm lần ngược được actor, nguyên nhân và downstream effect.

**Bước 12 — Review định kỳ.** Khi thêm service, event schema, API, pipeline hoặc yêu cầu riêng tư mới, cập nhật coverage và policy trước khi có sự cố thật.

## 35. Bài tập tình huống: thay đổi đơn hàng và báo cáo doanh thu

Hệ thống có:

~~~text
Gateway
  |
  v
Order Service ----> PostgreSQL orders
  |                       |
  |                       +-- CDC --> Kafka --> Warehouse
  |
  +--> Kafka OrderUpdated
                    |
                    +--> Billing Service
                    |
                    +--> Notification Worker
~~~

Một admin sửa trạng thái đơn hàng từ `CANCELLED` thành `PAID` sau yêu cầu đối soát. Sau đó báo cáo doanh thu tăng. Hai ngày sau khách hàng khiếu nại rằng họ không đồng ý với thay đổi.

Hãy thiết kế để trả lời:

1. Ai thực hiện thay đổi, với role/approval nào? Làm sao chống giả mạo actor từ HTTP header?
2. Chỉ lưu `ORDER_UPDATED` có đủ không, hay cần reasonCode, version, outcome và field diff?
3. Nếu Order DB commit nhưng Kafka không sẵn sàng, làm sao không mất audit event?
4. Khi relay gửi lại cùng event ba lần, làm sao audit sink không nhân bản lịch sử?
5. Nếu Notification Worker xử lý event B trước event A, làm sao suy ra thứ tự đổi của một order?
6. Nếu địa chỉ hoặc dữ liệu thanh toán xuất hiện trong Order object, có được đưa toàn bộ vào audit JSON không?
7. Lineage của revenue dashboard cần lưu jobRunId, code revision, input versions và output partition nào?
8. Nếu người vận hành xóa audit record bằng quyền DB admin, có phát hiện được không?
9. Nếu audit sink mất 20 phút, hệ thống phải dừng mọi hành động hay có thể dùng outbox?
10. Khi khách hàng yêu cầu correction, nên sửa/xóa audit event cũ hay ghi sự kiện correction mới?

### Hướng phân tích

- Actor phải đến từ authenticated principal; admin acting-on-behalf-of cần approval/delegation evidence.
- Audit event ghi enum hành động, trạng thái, version trước/sau, reasonCode và outcome; chỉ field được phép.
- Transactional outbox ghi cùng business DB commit; relay chuyển sau đó và monitor backlog.
- Consumer deduplicate theo eventId bằng unique constraint.
- Dùng aggregate/resource version hoặc sequence tin cậy; event time và ingest time không bảo đảm thứ tự toàn cục.
- Không dump Order object chứa PII/secret; dùng reference/sensitive field change markers.
- Lineage ghi input source/snapshot/offsets, transformation code revision, run ID, output version và quality.
- Append-only/RBAC + immutable checkpoint/signature giúp phát hiện hoặc giảm khả năng can thiệp, tùy threat model.
- Fail closed hay giữ giao dịch với outbox là policy theo event class và nghĩa vụ kiểm toán; không silently lose.
- Correction phải có sự kiện mới và liên kết bản cũ, không che giấu lịch sử, đồng thời bảo vệ quyền riêng tư.

## 36. Các sai lầm thường gặp

1. **Dùng log debug làm audit trail:** operational logs có thể bị sampling, xóa sớm hoặc thiếu actor và business outcome.
2. **Tin userId từ request body/header:** actor có thể bị giả mạo; lấy từ security context và xác minh trust boundary.
3. **Ghi audit SUCCEEDED trước DB commit:** transaction rollback nhưng bằng chứng sai.
4. **Ghi DB rồi publish broker không có outbox:** crash giữa hai bước làm mất sự kiện.
5. **Coi broker đảm bảo exactly-once end-to-end:** consumer/sink vẫn phải xử lý duplicates và replay.
6. **Sắp theo timestamp để suy ra mọi thứ:** clock skew và out-of-order có thể phá thứ tự; dùng resourceVersion.
7. **Dump toàn bộ before/after object:** dễ lộ password, token và PII; thiết kế allowlist.
8. **Không có schema version:** audit cũ bị reader mới diễn giải sai.
9. **Không phân biệt actor và executor:** worker chạy thay người dùng bị ghi nhầm thành “user trực tiếp”.
10. **Bỏ sót denied attempts:** chỉ quan sát business commits, bỏ qua các nỗ lực truy cập sai.
11. **Cho writer quyền xóa audit:** dễ sửa dấu vết; tách quyền và dùng integrity controls.
12. **Tin hash chain tuyệt đối bất biến:** không có independent checkpoint thì kẻ có quyền vẫn có thể tính lại chuỗi.
13. **Dùng traceId như bằng chứng auth:** trace ID chỉ để correlation.
14. **Dùng một eventType chung cho mọi thay đổi:** thiếu semantics và khó query.
15. **Để audit sink trễ mà không có cảnh báo:** “không thấy event” bị hiểu sai.
16. **Lineage chỉ ghi tên bảng:** thiếu input snapshot, code revision và job run nên không tái lập báo cáo.
17. **Quên backfill/replay:** báo cáo khác mà không biết job chạy lại.
18. **Không phân quyền query/export:** kho audit trở thành điểm tập trung dữ liệu nhạy cảm.
19. **Giữ audit vô thời hạn:** tăng rủi ro riêng tư và chi phí không cần thiết.
20. **Sửa sự kiện cũ để hợp thức hóa kết quả:** làm mất tính giải trình; dùng correction event có liên kết.
21. **Không đối chiếu coverage:** ingestion metrics xanh chưa chứng minh mọi business commit đều có audit.
22. **Trộn tenant trong key/index/query:** làm lộ lịch sử giữa các khách hàng.
23. **Không tính audit throughput khi bulk update:** hệ thống backlog hoặc mất dữ liệu vì quá tải.
24. **Không thử restore và integrity verification:** khi sự cố mới biết history hoặc checkpoint không đáng tin.

## 37. Checklist triển khai

- [ ] Xác định loại hành động bắt buộc audit và owner.
- [ ] Phân biệt domain change, security attempt, operational change và lineage metadata.
- [ ] Actor lấy từ nguồn xác thực; không tin raw user claim.
- [ ] Event có ID duy nhất, schemaVersion, occurredAt/recordedAt, outcome và resource version.
- [ ] Có reason/approval/causation khi nghiệp vụ yêu cầu.
- [ ] Chỉ ghi data fields theo allowlist; loại bỏ secret, token và PII không cần thiết.
- [ ] Success event phản ánh transaction commit thực.
- [ ] Dual write được xử lý bằng outbox/CDC hoặc cơ chế đáng tin tương đương.
- [ ] Delivery/replay có deduplication và ordering semantics rõ.
- [ ] Failed/denied attempts có kênh và policy riêng.
- [ ] Audit store có append-only, encryption, RBAC và kiểm soát export.
- [ ] Có integrity mechanism/checkpoint phù hợp threat model.
- [ ] Có retention, archive và quy trình xử lý dữ liệu cá nhân.
- [ ] Producer identity, tenant scope và schema được xác minh tại ingest.
- [ ] Có query theo resource, actor, time, eventId và correlation.
- [ ] Lineage ghi dataset IDs, input versions, jobRunId, code revision và output version.
- [ ] Có metrics cho backlog, lag, duplicate, schema rejection và integrity.
- [ ] Có reconciliation source commit/outbox/sink.
- [ ] Đã thử sink outage, relay crash, replay, out-of-order và spoofed actor.
- [ ] Đã thực hành một cuộc điều tra thay đổi với dữ liệu synthetic.

## 38. Kết luận

Một hệ thống microservices có thể trả lời “đã xảy ra chuyện gì?” bằng log và trace, nhưng muốn giải trình **ai thay đổi dữ liệu nào, vì sao, phiên bản nào được tạo ra, bằng chứng có đầy đủ và đáng tin hay không** thì cần thiết kế audit trail có cấu trúc. Muốn giải thích “kết quả dữ liệu này đến từ đâu?” cần thêm lineage của các dataset, message, transformation và job runs.

Nhật ký kiểm toán hiệu quả phải **gắn đúng identity và outcome, có transaction semantics, có version/correlation, chống mất/trùng sự kiện và được bảo vệ khỏi sửa/xóa trái phép**. Nguồn gốc dữ liệu phải **truy vết được từ output về input và code/pipeline revision**, không chỉ ghi tên hệ thống. Kết hợp audit, outbox, CDC, lineage, phân quyền, retention và reconciliation giúp tổ chức điều tra thay đổi chính xác hơn mà không biến hệ thống quan sát thành kho sao chép bí mật.
