# Thiết kế định danh tenant và truyền ngữ cảnh xuyên hệ thống

Trong nền tảng đa khách hàng (multi-tenant), nhiều tổ chức cùng sử dụng một sản phẩm hoặc một cụm dịch vụ. Hệ thống cần biết mỗi request đang hành động thay mặt tenant nào, người dùng nào, với quyền gì và trên phạm vi dữ liệu nào. Thông tin này phải được xác định đáng tin cậy ở điểm vào, sau đó truyền xuyên qua API, service, queue, worker, database, cache và object storage.

Nếu tenant context bị thiếu, bị giả mạo hoặc bị thay đổi trên đường đi, hệ thống có thể đọc nhầm dữ liệu của tenant khác, áp nhầm quota, ghi sai audit log hoặc thực hiện tác vụ với quyền vượt phạm vi. Vì vậy, **tenant identity và tenant context là một ranh giới bảo mật cốt lõi**, không chỉ là một trường tenantId được thêm vào request.

Trong module **CLOUD_ARCHITECTURE**, bài học này tập trung vào cách thiết kế định danh tenant, xác thực và ủy quyền, truyền context qua các ranh giới đồng bộ/bất đồng bộ, cô lập dữ liệu, quan sát và kiểm thử. Mục tiêu là giữ được quan hệ đúng giữa **ai đang gọi, đang đại diện cho tenant nào, được phép làm gì và dữ liệu được xử lý thuộc tenant nào** trên toàn bộ hành trình.

## 1. Phân biệt tenant, user, principal và tenant context

Các khái niệm này có liên quan nhưng không đồng nghĩa:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Tenant** | Tổ chức hoặc phạm vi khách hàng sở hữu dữ liệu/cấu hình | Công ty A, nhà bán hàng B, workspace C |
| **User** | Người dùng cuối hoặc thành viên của một tenant | Nhân viên kế toán của công ty A |
| **Principal** | Danh tính đã được xác thực đang thực hiện hành động | User, service account, workload identity |
| **Tenant membership** | Quan hệ giữa principal và tenant cùng vai trò/trạng thái | User 123 là admin của tenant A |
| **Tenant context** | Tập thông tin đã được xác minh để xử lý request trong phạm vi tenant | Tenant ID, actor, roles/scopes, request ID, policy version |
| **Resource owner** | Tenant hoặc phạm vi sở hữu resource được truy cập | Booking 987 thuộc tenant A |

Một user có thể thuộc nhiều tenant. Một service-to-service call có thể không đại diện cho user cụ thể nhưng vẫn phải chạy trong tenant context được ủy quyền. Một resource ID không tự chứng minh quyền truy cập hoặc tenant sở hữu resource.

### Quan hệ cần giữ

~~~mermaid
flowchart TD
    USER["User / workload principal"]
    AUTH["Authentication"]
    MEMBERSHIP["Tenant membership / service grant"]
    TENANT["Selected tenant"]
    POLICY["Authorization policy"]
    RESOURCE["Tenant-owned resource"]
    USER --> AUTH
    AUTH --> MEMBERSHIP
    MEMBERSHIP --> TENANT
    TENANT --> POLICY
    POLICY --> RESOURCE
~~~

Sơ đồ mô tả một đường kiểm tra khái niệm. Thực tế authorization phải kết hợp principal, tenant membership, action, resource ownership, trạng thái tenant và các điều kiện policy khác.

## 2. Tenant ID là định danh, không phải bằng chứng quyền

Tenant ID có thể là UUID, slug nội bộ hoặc identifier do hệ thống cấp. Nó giúp phân vùng dữ liệu và định tuyến request. Nhưng nếu client gửi tenantId=tenant-A, server không được mặc định người gọi có quyền truy cập tenant A.

Một lỗi phổ biến:

~~~http
GET /api/invoices/INV-001
X-Tenant-ID: tenant-A
Authorization: Bearer <user-token>
~~~

Nếu server chỉ lấy X-Tenant-ID rồi truy vấn invoice theo ID, người dùng có thể sửa header thành tenant khác để thử truy cập dữ liệu ngoài quyền. Đây là biến thể của insecure direct object reference/tenant isolation failure.

Quy tắc:

- Tenant ID do client cung cấp chỉ là **tenant được yêu cầu chọn**, không phải nguồn xác thực.
- Server xác thực principal và kiểm tra principal có membership/grant hợp lệ với tenant đó.
- Resource phải được kiểm tra thuộc tenant trong cùng phạm vi truy vấn/authorization.
- Mọi service downstream nhận context từ nguồn đáng tin cậy hoặc xác minh lại credential/delegation.
- Không cho phép request body, query parameter hoặc header tùy ý ghi đè tenant context đã được thiết lập.

### Identifier không phải secret

UUID khó đoán giúp giảm enumeration nhưng không thay thế authorization. Tenant ID có thể xuất hiện trong URL, log hoặc event; không coi việc giữ bí mật ID là một lớp kiểm soát truy cập.

### Canonical tenant ID

Một tenant có thể có tên hiển thị, slug, domain tùy chỉnh và nhiều alias. Hệ thống nên có một internal immutable ID làm khóa liên kết dữ liệu; slug/domain chỉ là tên tra cứu và có thể đổi. Khi tenant đổi tên hoặc domain, không nên phải di chuyển toàn bộ dữ liệu chỉ vì identifier bên ngoài thay đổi.

## 3. Xác định tenant tại điểm vào (tenant resolution)

Một request có thể xác định tenant qua:

- Tenant được chọn trong session hoặc giao diện người dùng.
- Subdomain/custom domain, ví dụ acme.example.com.
- Path segment, ví dụ /tenants/{tenant}/....
- Claim trong access token.
- Header nội bộ giữa các service.
- Mapping từ client/application registration tới tenant.

Không có một cách duy nhất đúng cho mọi sản phẩm. Dù dùng cách nào, server phải xác minh mapping và membership trước khi tạo trusted tenant context.

### Quy trình resolution đề xuất

1. **Authenticate principal:** kiểm tra token/session, issuer, audience, expiry, signature và các claim cần thiết.
2. **Resolve tenant candidate:** lấy tenant từ host/path/session/claim/client registration theo contract.
3. **Validate tenant:** tenant tồn tại, đang active, thuộc đúng environment/region và không bị suspended.
4. **Validate membership/grant:** principal được phép hoạt động trong tenant đó; kiểm tra role, scope, service grant và trạng thái membership.
5. **Authorize action/resource:** kiểm tra action cụ thể trên resource, không chỉ kiểm tra membership chung.
6. **Create trusted context:** tạo context bất biến cho request, gắn actor, tenant, scopes, correlation ID và policy metadata.
7. **Propagate safely:** truyền context qua các call đã xác thực và được ủy quyền.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as API Gateway
    participant I as Identity / Membership
    participant S as Service
    C->>G: Request + credential + tenant candidate
    G->>G: Authenticate principal
    G->>I: Validate membership / service grant
    I-->>G: Tenant membership + scopes
    G->>G: Build trusted tenant context
    G->>S: Forward authenticated request/context
    S->>S: Authorize action + resource ownership
    S-->>C: Response
~~~

Trong một số kiến trúc, gateway chỉ xác thực và service tự resolve/authorize tenant. Cần phân định rõ trách nhiệm để không có endpoint bỏ qua bước kiểm tra.

## 4. Thiết kế token và claim tenant

Access token có thể mang claim tenant hoặc thông tin membership, nhưng cần hiểu phạm vi và thời điểm claim có hiệu lực.

Ví dụ payload minh họa (không phải token có thể sử dụng):

~~~json
{
  "sub": "user-123",
  "iss": "https://identity.example",
  "aud": "booking-api",
  "exp": 1795000000,
  "tenant_id": "tn_7f31",
  "scope": ["booking:read", "booking:create"],
  "roles": ["booking_operator"]
}
~~~

Các điểm cần cân nhắc:

- **Tenant claim đơn:** phù hợp nếu một token chỉ đại diện một tenant context trong suốt thời gian sống.
- **Multi-tenant membership list:** có thể tạo token lớn, chứa thông tin cũ và khó thu hồi vai trò nhanh.
- **Tenant selection exchange:** user xác thực trước, sau đó đổi/trao đổi token cho tenant được chọn với audience và scopes cụ thể.
- **Service identity:** workload token có thể đại diện service; cần grant chỉ rõ service được gọi thay mặt tenant nào và hành động nào.

Không nên nhét toàn bộ danh sách tenant, resource permission và policy chi tiết vào access token dài hạn. Token là snapshot claim tại thời điểm phát hành; membership/role có thể bị thu hồi trước khi token hết hạn. Với quyền nhạy cảm, cần token ngắn hạn, introspection/revocation, policy check server-side hoặc cơ chế tương đương.

### Issuer, audience và subject

Khi xác minh JWT/OIDC token, service phải kiểm tra ít nhất các thuộc tính phù hợp với contract:

- Chữ ký và key issuer hợp lệ.
- Issuer đúng identity provider được tin cậy.
- Audience đúng API/resource server nhận token.
- Expiration và not-before.
- Subject/principal hợp lệ.
- Scope/role/tenant claim đúng schema và semantics.

Không chỉ decode JWT rồi tin nội dung; phải verify chữ ký và claim. Token của API A không được mặc định dùng cho API B nếu audience khác.

### Tránh confused deputy

Service có quyền rộng có thể vô tình dùng quyền của chính nó để truy cập resource tenant khác theo yêu cầu từ caller. Đây là rủi ro confused deputy. Downstream phải kiểm tra delegation/grant của service và tenant, không chỉ dựa vào việc service account có quyền kỹ thuật rộng.

## 5. Tenant context là gì và nên chứa gì?

Tenant context là đối tượng runtime được tạo sau khi xác thực và resolution. Nó nên bất biến trong phạm vi request/job, được truyền tường minh và có cấu trúc.

Ví dụ các trường:

| Trường | Mục đích |
| --- | --- |
| tenantId | Internal immutable tenant identifier |
| principalId | User/service principal đã xác thực |
| actorType | USER, SERVICE hoặc delegated actor |
| subjectUserId | User gốc nếu service đang hành động thay mặt user và policy cho phép |
| scopes / roles | Phạm vi hành động được cấp |
| requestId / traceId | Liên kết log/trace xuyên hệ thống |
| authzPolicyVersion | Phiên bản policy hoặc quyết định liên quan nếu cần audit |
| issuedAt / expiresAt | Thời hạn context/delegation khi được serialize |
| region / environment | Scope định tuyến và vận hành khi cần |

Không phải mọi service cần toàn bộ trường. Cần tối thiểu hóa dữ liệu nhạy cảm và tránh truyền profile/PII không liên quan.

### Context bất biến

Sau khi request đã được authorize, không để một hàm tùy tiện đổi tenant ID trên context. Nếu workflow thực sự phải chuyển sang tenant khác, cần tạo một context mới qua một bước authorization rõ ràng và audit. Không mutate context chung dùng bởi nhiều request/thread.

### Context không phải một quyền vô hạn

Có tenantId và roles trong context không có nghĩa service có thể truy cập mọi resource thuộc tenant. Authorization vẫn cần xét action, resource, trạng thái và điều kiện. Một role operator có thể đọc booking nhưng không được xuất dữ liệu thanh toán, ví dụ.

## 6. Truyền tenant context qua HTTP và API gateway

Trong kiến trúc service, gateway thường là điểm vào để xác thực, rate limit, routing và tạo một số metadata chuẩn. Tuy nhiên, gateway không nên trở thành nơi duy nhất bảo đảm tenant isolation; mỗi service vẫn phải bảo vệ ranh giới dữ liệu mà nó sở hữu.

### Header nội bộ và trusted boundary

Một hệ thống có thể truyền tenant context qua các header nội bộ như:

- X-Internal-Tenant-ID
- X-Internal-Principal-ID
- X-Internal-Actor-Type
- X-Internal-Request-ID
- X-Internal-Delegation-ID

Đây chỉ là tên ví dụ cho contract nội bộ, không phải chuẩn HTTP. Nếu dùng:

1. Edge gateway phải xóa/ghi đè các header cùng tên do Internet client gửi.
2. Chỉ workload được xác thực trong private/service network mới được phép gọi endpoint nội bộ.
3. Downstream phải xác minh service identity và nguồn context.
4. Context được ký hoặc mã hóa nếu đi qua trust boundary cần chống giả mạo; cần quản lý key và thời hạn.
5. Không truyền role/scope tùy tiện nếu downstream không thể kiểm tra nguồn cấp.
6. Không log access token, cookie hoặc payload context nhạy cảm.

### Không dùng header làm chứng cứ nếu không có xác thực kênh

Private IP hoặc internal DNS không tự chứng minh caller đáng tin. Nếu attacker có thể gọi trực tiếp service hoặc chiếm một workload trong cluster, họ có thể tự tạo header tenant. Dùng mTLS/workload identity, authorization giữa service và policy network; downstream chỉ chấp nhận context từ caller được phép.

### Gateway và service cùng chịu trách nhiệm

Gateway có thể kiểm tra token và tenant membership rồi forward context. Service vẫn phải:

- Xác minh caller là service được phép gọi.
- Kiểm tra delegation/tenant grant nếu contract yêu cầu.
- Kiểm tra resource thuộc tenant tương ứng.
- Áp quyền action-level.
- Không tin dữ liệu tenant do request body gửi kèm nếu mâu thuẫn với context đã xác thực.

## 7. Truyền context xuyên các service và ngăn confused deputy

Một service có thể gọi service khác bằng service identity riêng. Cần xác định service đang hành động:

- Thay mặt người dùng (on-behalf-of/delegated).
- Thay mặt tenant theo một grant machine-to-machine.
- Với quyền hệ thống không gắn tenant cụ thể.

Ba trường hợp này khác nhau về principal, audit và phạm vi quyền. Không được gộp thành một service account quản trị toàn hệ thống rồi cho mọi downstream tự suy tenant từ header.

### Delegation context

Nếu Service A nhận request của user rồi gọi Service B, có thể truyền:

- Actor gốc: user đã xác thực.
- Calling service: Service A.
- Tenant context: tenant user đang hoạt động.
- Delegation/grant: phạm vi Service A được phép gọi B.
- Action/scope cụ thể.
- Audience/service đích và thời hạn.
- Request/trace correlation.

Downstream nên kiểm tra token/delegation được phát hành cho đúng audience. Một token dùng giữa A và B không tự có quyền dùng tiếp để gọi C nếu chưa có delegation phù hợp.

### Token exchange và on-behalf-of

Một số identity platform hỗ trợ token exchange/delegated token. Service A đưa token gốc và yêu cầu một token ngắn hạn cho audience của Service B, với scopes hẹp. Điều này giảm nhu cầu tự truyền mọi claim qua header không được bảo vệ. Chi tiết flow phụ thuộc identity provider và chuẩn/hỗ trợ sản phẩm.

Không forward access token gốc tới mọi service nếu token có audience không phù hợp hoặc chứa quyền rộng hơn cần thiết. Không ghi token vào queue hoặc log; với job dài, dùng service credential riêng và lưu reference/delegation có thể thu hồi theo policy.

### Audit actor chain

Audit log nên phân biệt:

| Trường | Ví dụ |
| --- | --- |
| actor | user-123 |
| caller_service | booking-api |
| effective_tenant | tn_7f31 |
| action | invoice.export |
| resource | invoice-001 |
| delegation_id | del-81 |
| request_id | req-xyz |
| decision | allow |

Nhờ vậy, khi một service có quyền thực hiện hành động, đội vận hành vẫn biết ai khởi tạo hành động và service nào thực thi. Audit phải chống sửa/xóa trái phép và tuân theo data retention.

## 8. Truyền tenant context qua queue và event bất đồng bộ

HTTP request kết thúc nhưng công việc có thể tiếp tục qua queue. Consumer không còn request thread hoặc connection ban đầu; tenant context phải được lưu trong message envelope hoặc reference an toàn.

~~~mermaid
flowchart LR
    API["API service"]
    DB["Transaction + outbox"]
    Q["Message broker"]
    WORKER["Background worker"]
    STORAGE["Tenant-scoped storage"]
    API --> DB
    DB --> Q
    Q --> WORKER
    WORKER --> STORAGE
~~~

### Event envelope

Một envelope minh họa:

~~~json
{
  "eventId": "evt-91",
  "eventType": "invoice.export.requested",
  "tenantId": "tn_7f31",
  "actor": {
    "type": "USER",
    "id": "user-123"
  },
  "delegationId": "del-81",
  "correlationId": "req-xyz",
  "occurredAt": "2026-11-18T10:20:30Z",
  "schemaVersion": 2,
  "data": {
    "exportJobId": "job-55"
  }
}
~~~

Không nhất thiết mọi event cần actor user; service-generated schedule hoặc system event có thể có actor type riêng. Payload chỉ nên mang các metadata cần thiết, không nhúng access token hay secret.

### Consumer phải xác minh envelope

Consumer nên kiểm tra:

1. Event đến từ broker/topic/subscription được tin cậy.
2. Producer identity được phép phát event type này.
3. Tenant ID là internal canonical ID và tồn tại/đúng trạng thái.
4. Event schema/version hợp lệ.
5. Tenant và actor/delegation phù hợp với operation được yêu cầu.
6. Job/resource được truy vấn trong tenant scope.
7. Idempotency/event ID chống xử lý lặp.

Không thể tin một field tenantId chỉ vì nó nằm trong JSON của queue. Nếu producer bị compromise, consumer vẫn cần quyền tối thiểu và kiểm tra resource ownership.

### Job chạy dài và context hết hạn

Không lưu access token user dài hạn trong message để worker dùng sau nhiều giờ/ngày. Token có thể hết hạn hoặc bị thu hồi, còn message nằm trong queue. Thay vào đó:

- Lưu operation/job ID và tenant ID canonical.
- Lưu audit actor/delegation reference cần thiết.
- Worker dùng workload identity riêng và kiểm tra job grant còn hiệu lực.
- Nếu cần tiếp tục quyền của user, định nghĩa chính sách reauthorization khi bắt đầu/thực hiện từng bước.
- Có thể yêu cầu user xác nhận lại với thao tác nhạy cảm.

Context của một job nên có expiration và trạng thái; khi tenant bị suspended hoặc quyền bị thu hồi, worker phải kiểm tra policy trước side effect tiếp theo.

## 9. Propagation qua workflow và saga

Workflow nhiều bước có thể chạy qua nhiều service và thời gian dài. Mỗi step cần nhận tenant context và actor lineage phù hợp, song song với workflow ID và state version.

Một saga đặt chỗ có thể gọi Inventory, Payment, Booking và Notification. Các command/event cần:

- Cùng tenant context đã xác minh.
- Correlation/workflow ID để liên kết cả chuỗi.
- Actor/delegation nếu hành động xuất phát từ người dùng.
- Command ID/idempotency key.
- Version/state để chống xử lý sai thứ tự.
- Policy recheck tại những bước nhạy cảm.

### Compensation không được vượt tenant

Khi saga thất bại, action bù như release reservation hoặc refund phải dùng đúng tenant và resource ban đầu. Không lấy tenant từ message mới không liên quan hoặc từ global workflow state có thể bị ghi đè. Lưu tenant owner vào bản ghi workflow bất biến; validate lại khi thực hiện compensation.

### Scheduled job

Job định kỳ có thể chạy cho tất cả tenant. Không tạo một context rỗng rồi query tất cả dữ liệu và trông cậy code từng bước nhớ filter. Một pattern an toàn hơn:

1. Scheduler tạo danh sách tenant đủ điều kiện.
2. Phát một job độc lập cho từng tenant hoặc batch có ranh giới rõ.
3. Mỗi worker tạo context tenant-scoped riêng.
4. Query, cache key, storage path và log đều mang tenant scope.
5. Lỗi của một tenant không làm lộ hoặc chặn ngoài ý muốn tenant khác.

Nếu batch nhiều tenant, cần giới hạn concurrency và kiểm soát context switching; không tái sử dụng mutable context giữa hai tenant.

## 10. Context trong thread, async và reactive execution

Trong ứng dụng Java, request context có thể được giữ trong parameter, scoped object, framework context hoặc thread-local. Cách triển khai phải phù hợp mô hình concurrency.

### Ưu tiên truyền tường minh

Một hàm có thể nhận TenantContext như tham số:

~~~java
public Invoice getInvoice(
        TenantContext context,
        InvoiceId invoiceId
) {
    authorization.require(
            context.principalId(),
            context.tenantId(),
            "invoice:read",
            invoiceId
    );

    return invoiceRepository.findByTenantAndId(
            context.tenantId(),
            invoiceId
    ).orElseThrow(InvoiceNotFoundException::new);
}
~~~

Đây là ví dụ minh họa; kiểu TenantContext và authorization service là thành phần do ứng dụng định nghĩa. Việc truyền tường minh giúp nhìn thấy dependency và dễ test hơn so với lấy tenant từ một global variable.

### ThreadLocal có giới hạn

ThreadLocal có thể thuận tiện trong servlet thread-per-request, nhưng có rủi ro:

- Thread pool tái sử dụng thread; context cũ có thể rò sang request kế tiếp nếu không clear.
- CompletableFuture/Executor chuyển sang thread khác không tự mang ThreadLocal.
- Reactive pipeline không gắn với một thread cố định.
- Async callback có thể chạy sau khi request đã hết hạn hoặc context đã bị cleanup.

Nếu framework có request context propagation được hỗ trợ, dùng cơ chế đó và kiểm tra cleanup. Không tự viết propagation cho mọi executor mà không test.

### Context propagation trong async

Khi submit task, có thể capture một snapshot immutable của context đã authorize và truyền explicit cùng task. Snapshot nên bị giới hạn scope, expiration và không mang secret. Nếu task kéo dài hoặc có side effect, worker cần kiểm tra job state và permission/delegation còn hiệu lực thay vì sử dụng quyền snapshot vô thời hạn.

### Không dùng mutable singleton

Không lưu currentTenantId trong field của singleton service. Nhiều request đồng thời có thể ghi đè context của nhau, gây lộ dữ liệu cross-tenant. Context phải thuộc request/job cụ thể và thread-safe theo cách framework sử dụng.

## 11. Tenant context trong database và query layer

Tenant context cần đi tới mọi truy vấn dữ liệu có phạm vi tenant. Phòng thủ nhiều lớp là cần thiết vì một query quên tenant filter có thể trả dữ liệu của khách hàng khác.

### Tenant discriminator trong schema dùng chung

Một schema shared-table thường có cột tenant_id trong các bảng chứa dữ liệu tenant:

~~~sql
CREATE TABLE invoice (
    tenant_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    status VARCHAR(32) NOT NULL,
    total_amount DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id)
);

CREATE INDEX idx_invoice_tenant_status
    ON invoice (tenant_id, status);
~~~

Khóa chính ghép tenant_id với invoice_id giúp định danh rõ phạm vi; query nên lọc theo cả hai:

~~~sql
SELECT invoice_id, status, total_amount
FROM invoice
WHERE tenant_id = :trusted_tenant_id
  AND invoice_id = :invoice_id;
~~~

trusted_tenant_id phải đến từ TenantContext đã được xác minh, không lấy trực tiếp từ request body. Không nên chỉ truy vấn theo invoice_id dù ID có vẻ duy nhất toàn hệ thống; tenant predicate giúp phòng thủ nhiều lớp và hỗ trợ partition/index.

### Row-level security (RLS)

Một số database hỗ trợ row-level security để enforce filter theo session/role ở tầng database. RLS có thể giảm rủi ro khi một query của ứng dụng quên tenant condition, nhưng phải cấu hình đúng:

- Session variable/context phải được set an toàn cho từng transaction/connection.
- Connection pool phải reset context trước khi tái sử dụng connection.
- Role ứng dụng không được có quyền bypass RLS ngoài ý muốn.
- Background job và migration có quyền rõ ràng, có audit.
- Kiểm thử cả raw SQL, ORM, stored procedure và query path ít dùng.

RLS không thay authorization action-level, cũng không giúp nếu ứng dụng có thể set tenant session variable tùy ý mà không xác thực.

### Connection pool và session leakage

Nếu dùng session variable để giới hạn tenant, một connection có thể được dùng bởi request tiếp theo. Nếu context không được reset hoặc transaction bị rò, request tenant B có thể chạy với context tenant A hoặc ngược lại. Dùng transaction-scoped setting khi database hỗ trợ, reset trong finally/connection lifecycle và có test xen kẽ tenant trên cùng pool.

### Composite foreign key

Các bảng liên quan nên giữ tenant ownership trong quan hệ tham chiếu. Ví dụ line item tham chiếu invoice:

~~~sql
CREATE TABLE invoice_line (
    tenant_id UUID NOT NULL,
    invoice_id UUID NOT NULL,
    line_id UUID NOT NULL,
    description TEXT NOT NULL,
    PRIMARY KEY (tenant_id, invoice_id, line_id),
    FOREIGN KEY (tenant_id, invoice_id)
        REFERENCES invoice (tenant_id, invoice_id)
);
~~~

Composite foreign key giúp ngăn một dòng tenant A tham chiếu invoice tenant B trong database. Cần áp dụng nhất quán cho relation, unique constraint và join.

### Repository API nên yêu cầu context

Tránh repository public method kiểu findById(id) nếu dữ liệu tenant-scoped. Có thể thiết kế method bắt buộc tenant:

- findByTenantAndId(tenantId, id)
- listByTenantAndStatus(tenantId, status)
- updateByTenantAndId(tenantId, id, version)

Không để controller tự nhớ thêm WHERE. Query builder hoặc repository base có thể nhận TenantContext và tự thêm predicate, nhưng phải có test để bảo đảm không bypass được.

## 12. Cache key và tenant context

Cache là một ranh giới dễ bị bỏ sót. Nếu key chỉ dựa trên resource ID nhưng kết quả phụ thuộc tenant, dữ liệu có thể bị trả chéo.

Ví dụ:

- Không an toàn khi giá theo tenant được lưu tại price:product-42.
- Key có scope phù hợp hơn: price:v3:tenant-17:product-42:currency-VND.
- Hồ sơ riêng: profile:v2:tenant-17:user-123.
- Cấu hình tenant: config:v1:tenant-17:feature-set.

### Thành phần phải đưa vào key

Đưa vào mọi yếu tố làm thay đổi kết quả:

- Tenant ID canonical.
- User/principal nếu kết quả được cá nhân hóa.
- Role/permission scope hoặc policy generation nếu response phụ thuộc quyền.
- Region, locale, currency, customer tier.
- Schema/data version nếu payload thay đổi.

Không đưa toàn bộ claim vào key một cách máy móc; key sẽ dài, cardinality tăng và khó invalidation. Phân tích chính xác response variation và tạo fingerprint ổn định.

### Cache collision giữa tenant

Khi cùng product ID xuất hiện ở nhiều tenant nhưng giá/metadata khác nhau, cache key phải phân biệt tenant. Dù cache instance được chia sẻ, key namespace vẫn cần scope. Đồng thời authorization phải được kiểm tra trước khi trả cache hit; biết key không có nghĩa caller có quyền đọc.

### Invalidation và context

Event invalidate nên chứa tenant ID và resource/version. Consumer chỉ xóa key thuộc đúng tenant. Nếu key schema thay đổi, cần chuyển tiếp invalidation cho cả namespace cũ và mới trong thời gian migration. Tránh flush toàn cache khi một tenant thay đổi cấu hình.

## 13. Tenant-scoped object storage và file access

Object storage thường lưu file theo bucket/container và key. Có thể phân tách theo:

- Bucket/container riêng mỗi tenant.
- Prefix riêng mỗi tenant trong bucket dùng chung.
- Account/project/storage account riêng cho nhóm tenant.
- Kết hợp bucket dùng chung với encryption key hoặc access point riêng.

### Chọn mô hình theo isolation và quy mô

| Mô hình | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| Bucket/container per tenant | Policy, retention, quota và xóa tenant rõ hơn | Nhiều resource, policy và quota quản trị |
| Prefix per tenant | Dễ mở rộng số tenant và giảm số bucket | IAM/policy cần chặt; list/delete prefix có rủi ro |
| Account/project per tenant | Isolation mạnh về quyền và blast radius | Chi phí vận hành/control plane cao, nhiều resource |
| Hybrid tiering | Tenant lớn/nhạy cảm tách riêng, tenant nhỏ dùng chung | Cần quy tắc placement và di chuyển tenant |

### Không tin object key do client gửi

Client có thể gửi fileName hoặc path chứa ../, Unicode confusable hoặc prefix của tenant khác. Server cần tự tạo storage key từ tenant ID canonical và object ID; filename gốc chỉ là metadata đã sanitize. Không nối trực tiếp header tenant vào path rồi cho phép client điều khiển suffix tùy ý.

Ví dụ logical key:

~~~text
tenants/tn_7f31/invoices/2026/obj_8b2f.pdf
~~~

Key này chỉ là namespace, không tự bảo vệ object. Dùng IAM/bucket policy, signed URL ngắn hạn, kiểm tra tenant ownership khi tạo signed URL và không cho client tự chọn bucket/prefix.

### Signed URL và delegation

Signed URL thường là bearer capability: ai có URL trong thời hạn hiệu lực có thể thực hiện thao tác đã ký. Khi tạo URL:

1. Xác thực tenant context và quyền trên document.
2. Server xác định bucket/key/version từ metadata trusted.
3. Giới hạn method, content type, size và expiration nếu provider hỗ trợ.
4. Audit actor, tenant, resource và thời hạn URL.
5. Không log URL đầy đủ vì query string có thể chứa signature.

Nếu tenant bị suspended hoặc quyền bị thu hồi, signed URL đã phát hành có thể vẫn dùng được tới khi hết hạn hoặc bị revoke theo tính năng dịch vụ. Vì vậy phải chọn TTL phù hợp và có cơ chế kiểm soát URL cho dữ liệu nhạy cảm.

## 14. Tenant context trong search index và analytics

Search engine, data warehouse và analytics platform thường gom dữ liệu từ nhiều service. Đây là nơi tenant boundary có nguy cơ bị mất vì dữ liệu đã được flatten, denormalize hoặc tổng hợp.

### Search index

Mỗi document/index record cần giữ tenant ownership hoặc một access scope đáng tin cậy. Search query phải thêm tenant filter từ trusted context; không cho client tự gửi filter tenant tùy ý làm nguồn authorization.

Các điểm cần kiểm tra:

- Tenant ID có được ghi vào mọi document cần cách ly không?
- Search alias/index có phân tách tenant hoặc có mandatory filter không?
- Facet, aggregation, autocomplete và suggestion có lọc tenant không?
- Reindex/backfill có giữ tenant ID không?
- Delete/retention request có xóa đúng mọi document/version của tenant không?
- Admin endpoint có quyền truy cập toàn bộ tenant và audit tương ứng không?

Một lỗi hay gặp là search hits được lọc theo tenant nhưng total count, autocomplete hoặc aggregation lại chạy trên toàn bộ index. Metadata thống kê cũng có thể làm lộ quy mô, tên resource hoặc hành vi tenant khác.

### Analytics và data lake

Pipeline ingest phải gắn tenant identity canonical vào event/record, kiểm tra producer và chuẩn hóa schema. Quyền truy vấn có thể dựa trên row-level policy, view riêng hoặc dataset/account riêng tùy yêu cầu isolation. Không dựa vào việc analyst "nhớ thêm WHERE tenant_id" trong mỗi query.

Với báo cáo cross-tenant phục vụ platform operator, cần role đặc quyền riêng, mục đích sử dụng, audit, masking và giới hạn export. Quyền xem toàn nền tảng không nên là mặc định của service account analytics.

### Aggregation và dữ liệu suy luận

Một dashboard chỉ hiển thị tổng số có thể vẫn lộ thông tin tenant nếu nhóm quá nhỏ hoặc có thể suy ngược bằng cách lọc nhiều chiều. Cần xét minimum group size, masking, aggregation policy và quyền export.

## 15. Tenant context qua message broker và dead-letter queue

Broker có thể dùng một cluster chung cho nhiều tenant hoặc tách topic/namespace theo tenant. Dù mô hình nào, producer/consumer phải bảo toàn tenant scope.

### Chọn mô hình topic

| Mô hình | Ưu điểm | Rủi ro/đánh đổi |
| --- | --- | --- |
| Topic chung, tenant ID trong envelope | Ít topic/resource, dễ vận hành ở quy mô lớn | Filter/ACL và consumer logic phải đúng; dễ noisy neighbor |
| Topic per tenant | ACL và quota theo tenant rõ hơn | Số topic lớn, quản trị metadata và consumer phức tạp |
| Topic theo tenant tier/domain | Cân bằng số lượng và cách ly | Cần mapping tenant-to-topic đáng tin cậy |
| Broker/namespace riêng cho tenant lớn | Isolation và capacity riêng | Chi phí và vận hành cao hơn |

### Partition key và ordering

Partition key của message có thể là tenant ID, aggregate ID hoặc entity ID. Tenant ID giúp giữ event của tenant cùng partition nhưng một tenant lớn có thể tạo hot partition. Aggregate ID thường giữ ordering theo entity tốt hơn và phân tán tenant có nhiều entity. Chọn theo ordering requirement và phân bố tải.

Không đưa raw tenant ID do client tự gửi làm partition key trước khi producer đã xác thực context. Dùng canonical tenant ID trong event đã được tạo ở trusted boundary.

### Dead-letter queue và replay

DLQ thường chứa payload gốc. Nó có thể gồm PII, invoice data, tenant identifiers và metadata quyền. Cần:

- ACL giới hạn producer/consumer/operator.
- Encryption và retention phù hợp.
- Tool replay yêu cầu chọn tenant/event type và approval khi cần.
- Replay consumer vẫn xác minh tenant ownership và idempotency.
- Audit người xem/download/replay DLQ message.
- Không copy message sang topic chung làm mất tenant filter.

### Poison message

Nếu một message có tenant ID sai schema hoặc tenant không còn tồn tại, không được fallback sang system tenant hoặc tenant mặc định. Đưa vào quarantine/DLQ có lý do, cảnh báo và xử lý theo runbook.

## 16. Tenant context và định tuyến region

Một tenant có thể được gán home region để đáp ứng data residency, latency hoặc ownership. Tenant context có thể chứa region hint, nhưng server phải xác minh mapping từ registry/control plane.

### Tenant home region

Registry có thể ánh xạ:

| Tenant | Home region | Data classification | Status |
| --- | --- | --- | --- |
| tn-A | region-1 | standard | active |
| tn-B | region-2 | restricted | active |
| tn-C | region-1 | standard | suspended |

Region do client gửi không được quyền ghi đè mapping có thẩm quyền. Nếu request vào edge region khác home region, gateway có thể route sang region chủ quản hoặc phục vụ read-only theo policy.

### Di chuyển tenant

Tenant migration sang region mới cần:

1. Đóng băng/điều phối write theo protocol.
2. Đồng bộ dữ liệu và xác minh replication lag/checksum.
3. Chuyển ownership/mapping qua control plane có audit.
4. Đảm bảo service discovery, cache namespace, queue consumer và storage policy cập nhật.
5. Kiểm tra signed URL, backup, encryption key và data residency.
6. Mở write ở region mới và giữ kế hoạch rollback.

Không chỉ đổi một trường homeRegion rồi giả định mọi service đã định tuyến đúng. Cache, queue, search index, backup và scheduled job cũng phải biết tenant đã chuyển.

### Tenant suspension và deletion

Khi tenant bị suspended, cần chính sách nhất quán cho API, queue, scheduled jobs, signed URL, cache, search và service-to-service grants. Không chỉ chặn đăng nhập giao diện; worker đã xếp hàng có thể tiếp tục xử lý.

Tenant deletion là lifecycle dài: export/retention/legal hold, xóa dữ liệu nguồn, bản sao, cache, index, backup theo policy, key và audit. Cần state machine và bằng chứng hoàn tất; không thực hiện bằng một DELETE tenant record đơn lẻ.

## 17. Observability: giữ tenant context nhưng không làm lộ dữ liệu

Tenant context giúp điều tra sự cố, quota và noisy neighbor. Tuy nhiên, thêm tenant ID vào mọi metric/log cũng có thể tạo cardinality lớn hoặc lộ metadata nhạy cảm.

### Logging

Log nên có các trường cần thiết:

- tenant ID đã chuẩn hóa hoặc pseudonymous ID theo policy.
- principal/actor type theo mức cần thiết.
- service, operation, resource type, decision.
- request ID, trace ID, delegation ID.
- status/error category và latency.

Không ghi access token, signed URL, session secret, dữ liệu invoice hoặc PII vào log thông thường. Kiểm soát ai có thể tìm kiếm log nhiều tenant; platform support cần audit truy cập và lý do.

### Metrics

Metric label có tenant ID cho hàng triệu tenant dễ gây cardinality explosion. Cách tiếp cận:

- Metric tổng hợp theo service/region/tier.
- Top-N tenant theo dashboard có giới hạn và không tạo label vô hạn.
- Tenant-specific telemetry trong hệ thống chuyên biệt với retention/quota riêng.
- Pseudonymized identifier hoặc sampled trace khi cần điều tra.
- Tách metric noisy-neighbor và quota theo tenant theo cách có bounded cardinality.

### Distributed tracing

Trace context cần truyền trace/span ID chuẩn; tenant metadata có thể được thêm vào baggage hoặc span attribute theo policy. Baggage có thể lan tới downstream và ra ngoài trust boundary nếu không lọc. Không đưa secret, PII hoặc toàn bộ role list vào trace.

### Audit access cross-tenant

Các hành động support/admin nhìn dữ liệu nhiều tenant phải được ghi:

- Operator principal và role.
- Tenant/resource được truy cập.
- Mục đích/ticket hoặc approval.
- Hành động đọc/export/sửa/xóa.
- Thời gian và kết quả.

Không nên dùng audit log thông thường làm kho dữ liệu bất biến nếu actor có quyền sửa cùng log; cân nhắc export sang hệ thống audit riêng.

## 18. Noisy neighbor, quota và rate limit theo tenant

Một tenant có thể tạo tải vượt xa phần còn lại. Dù tenant context chính xác, hệ thống vẫn cần dùng nó để phân phối quota và bảo vệ tài nguyên chung.

### Các dimension quota

- Request per second và burst.
- Concurrent requests/jobs.
- Storage bytes và object count.
- Database rows, connections hoặc query cost.
- Message rate, queue depth và retention.
- Export/report size.
- CPU/memory trong workload được dedicated.

### Rate limit theo tenant và principal

Rate limit có thể phân tầng:

- Tenant-level limit bảo vệ tổng tài nguyên.
- User-level limit ngăn một user gây tải lớn trong tenant.
- API/client-level limit bảo vệ credential hoặc integration riêng.
- Resource-level limit cho hot resource.

Không chỉ dựa IP vì nhiều user trong một tenant có thể chia sẻ NAT, hoặc attacker thay IP liên tục. Tenant identity phải đến từ context đã xác thực.

### Fairness

Một số hệ thống dùng weighted fair queuing hoặc per-tenant worker concurrency để một tenant không chiếm hết worker pool. Quota cần có burst allowance, backpressure và hướng dẫn retry. Nếu trả 429, có thể cung cấp Retry-After theo contract. Không áp quota cho tenant suspended theo cùng policy active.

### Tiering

Tenant nhỏ có thể dùng pool shared; tenant lớn có thể được tách cache/database/queue hoặc worker pool. Việc nâng tier cần thay mapping và capacity mà không phá tenant context hoặc quyền truy cập.

## 19. Cô lập dữ liệu: shared schema, schema per tenant và database per tenant

Tenant context phải được áp dụng nhất quán dù dữ liệu dùng chung hay tách riêng.

| Mô hình | Cách tổ chức | Ưu điểm | Đánh đổi |
| --- | --- | --- | --- |
| **Shared tables** | Nhiều tenant trong cùng bảng, discriminator tenant_id | Chi phí thấp, dễ mở rộng tenant count | Cần query/RLS guardrail chặt; noisy neighbor |
| **Schema per tenant** | Mỗi tenant có schema riêng trong một database | Có ranh giới logic và migration theo tenant | Nhiều schema, connection/migration overhead |
| **Database per tenant** | Mỗi tenant có database riêng | Isolation, backup/restore, encryption và tuning riêng | Quản lý nhiều database và chi phí cao |
| **Dedicated account/cluster** | Tenant lớn/nhạy cảm có hạ tầng riêng | Blast radius và capacity isolation tốt hơn | Provisioning, networking và vận hành phức tạp |
| **Hybrid** | Tenant theo tier/chính sách được placement khác nhau | Cân bằng chi phí và isolation | Cần abstraction, migration và registry đáng tin |

### Tenant context vẫn cần ở mô hình dedicated

Database riêng không có nghĩa bỏ tenant authorization. Service vẫn phải xác minh tenant được yêu cầu đúng với database endpoint được resolve, tránh confused deputy hoặc routing bug. Một tenant ID giả mạo có thể khiến service chọn nhầm endpoint nếu registry lookup không được kiểm tra.

### Data placement registry

Control plane có thể quản lý mapping tenant tới database/schema/cluster/region. Registry cần:

- Canonical tenant ID làm primary key.
- Mapping có version và trạng thái active/migrating/suspended.
- Quyền read/write rõ ràng, audit thay đổi.
- Cache TTL/invalidations có kiểm soát.
- Fail-safe khi registry không truy cập được; không fallback ngẫu nhiên sang database mặc định.
- Quy trình migration, rollback và reconciliation.

Khi mapping thay đổi, mọi service phải dùng cùng semantics/version; tránh service A truy vấn cluster mới trong khi service B vẫn ghi cluster cũ.

## 20. Case study: nền tảng SaaS quản lý đặt chỗ cho nhiều công ty

Một SaaS có các tenant là công ty khách hàng. Mỗi tenant có nhân viên, booking, invoice, catalog tùy chỉnh và file chứng từ. Nhân viên có thể thuộc nhiều công ty; một số đối tác tích hợp gọi API bằng client credential.

Yêu cầu:

- User có thể chuyển tenant trong giao diện.
- Không tenant nào đọc được invoice của tenant khác.
- API có thể tạo booking và xuất báo cáo bất đồng bộ.
- File chứng từ lưu trong object storage dùng chung.
- Một số tenant lớn có database riêng.
- Support có thể điều tra sự cố nhưng mọi truy cập tenant phải audit.

### Thiết kế identity

Identity provider xác thực user và phát token subject user. Tenant selection endpoint kiểm tra membership rồi tạo delegated/tenant-scoped token có audience cho booking API và scopes cần thiết. Client không tự chọn role. Với integration service, client registration được ánh xạ tới tenant và grant cụ thể.

### Luồng API đồng bộ

1. Gateway verify token, resolve tenant và kiểm tra membership.
2. Gateway forward trusted service credential/context qua kênh service-to-service có xác thực.
3. Booking service kiểm tra scope và resource ownership.
4. Repository luôn query tenant_id cùng booking/invoice ID; RLS là lớp bổ sung nếu database hỗ trợ.
5. Cache key và object key bao gồm canonical tenant scope.
6. Audit ghi actor, caller service, tenant và operation.

~~~mermaid
flowchart TB
    USER["User / integration client"]
    IDP["Identity provider"]
    GW["Gateway + tenant resolver"]
    BOOK["Booking service"]
    DB["Shared DB / dedicated DB"]
    CACHE["Tenant-scoped cache"]
    OBJ["Tenant-scoped object storage"]
    USER --> IDP
    IDP --> GW
    GW --> BOOK
    BOOK --> DB
    BOOK --> CACHE
    BOOK --> OBJ
~~~

### Luồng export bất đồng bộ

Booking service xác thực quyền export, ghi operation và outbox trong transaction; event mang canonical tenant ID, actor reference và job ID. Worker dùng workload identity, kiểm tra job grant/status, đọc tenant-scoped data, ghi file vào object key của tenant và cập nhật job. Signed URL được tạo sau khi kiểm tra principal có quyền tải report.

Client đóng trình duyệt không tự hủy export đã được chấp nhận. Nếu tenant bị suspended trong lúc worker chạy, worker kiểm tra status trước bước publish file; nếu cần, dừng hoặc cách ly kết quả theo policy.

### Luồng support

Support operator cần truy cập tenant theo ticket/approval. Hệ thống phát delegation ngắn hạn, chỉ cho phép action cần thiết; mọi read/export được audit. Role support không có quyền tùy ý impersonate user hoặc bypass logging.

### Dedicated database cho tenant lớn

Tenant lớn được chuyển từ shared database sang dedicated cluster. Control plane cập nhật mapping có version. Trong migration, service dùng routing layer theo tenant; cutover chỉ khi data copy/checksum và replication lag đạt tiêu chí. Rollback cần biết region/database nào là writer hiện tại để tránh dual-write ngoài ý muốn.

## 21. Case study: service account và machine-to-machine integration

Một đối tác gửi dữ liệu đặt chỗ qua API bằng client credentials. Không có user cuối trong request, nhưng mọi bản ghi vẫn thuộc một tenant.

### Ràng buộc grant

Client registration được ánh xạ tới:

- Tenant canonical ID.
- Client/service principal.
- Audience là API nhận request.
- Scopes như booking:create và booking:read.
- Rate limit/quota.
- Allowed network/IP hoặc mTLS identity nếu cần.
- Credential expiry/rotation và trạng thái revoke.

Tenant ID trong payload từ đối tác không được ghi đè tenant đã gắn với client registration. Nếu integration được phép gửi cho nhiều tenant, phải có grant cụ thể để chọn trong danh sách cho phép.

### Không dùng service credential toàn năng

Một API key dùng chung cho tất cả khách hàng làm giảm khả năng audit và tăng blast radius. Tạo credential riêng theo tenant/integration, quyền hẹp, rotation và revocation riêng. Gắn request ID và idempotency key cho thao tác ghi.

### Audit

Audit actor là client service principal; effective tenant là tenant được grant. Nếu có user gốc ở hệ thống đối tác, có thể lưu external actor reference đã được xác minh, nhưng không coi chuỗi arbitrary trong payload là danh tính tin cậy.

## 22. Quy trình xây dựng TenantContext

Một implementation nên có lifecycle rõ:

1. **Resolve principal:** xác thực credential và dựng principal immutable.
2. **Select tenant candidate:** lấy candidate từ claim, domain, path hoặc service registration theo contract.
3. **Validate membership:** kiểm tra quan hệ active và tenant state.
4. **Derive effective permissions:** lấy scope/role theo tenant và action; không mang quyền từ tenant khác.
5. **Bind resource scope:** kiểm tra resource owner hoặc dùng query buộc tenant predicate.
6. **Create context:** tạo immutable object với request/job ID và expiration.
7. **Propagate:** truyền context explicit hoặc qua giao thức được xác thực.
8. **Reauthorize at boundaries:** queue consumer, scheduled job, export hoặc side effect nhạy cảm kiểm tra grant hiện hành theo policy.
9. **Audit decision:** ghi principal, tenant, action, resource và decision.
10. **Cleanup:** kết thúc request/task thì xóa context khỏi thread/request scope, giải phóng reference và tránh reuse.

### TenantContext nên là type riêng

Không dùng một Map<String,Object> không schema để chứa tenant context. Type rõ ràng giúp bắt lỗi compile-time, validate field và kiểm soát serialization. Nên phân biệt:

- AuthenticatedPrincipal.
- TenantMembership/Delegation.
- TenantContext đã authorize.
- ResourceTenantScope.

Điều này làm rõ trạng thái dữ liệu ở từng bước và giảm nguy cơ truyền tenant candidate chưa được xác minh như một trusted context.

### Không serialize context runtime tùy tiện

TenantContext có thể chứa object reference, quyền nội bộ hoặc thông tin nhạy cảm. Khi đưa vào message, chỉ serialize schema event được định nghĩa; consumer dựng context mới từ envelope đã verify và policy hiện hành. Không dùng Java native serialization hoặc dump nguyên object runtime lên queue.

## 23. Threat scenarios và biện pháp phòng vệ

| Tình huống | Nguyên nhân | Biện pháp |
| --- | --- | --- |
| Tenant spoofing | Tin header/body tenant do client gửi | Resolve từ identity/membership; ghi đè header ở trusted gateway |
| IDOR/cross-tenant read | Truy vấn chỉ theo resource ID | Tenant predicate, ownership check, RLS và negative tests |
| Confused deputy | Service quyền rộng thực thi theo yêu cầu không có delegation | Audience/delegation hẹp, actor chain, authorize downstream |
| Context leakage | ThreadLocal/async context còn sót giữa request | Immutable request scope, cleanup, explicit propagation |
| Queue poisoning | Consumer tin tenant ID trong payload | Verify producer/topic, schema, tenant state và resource ownership |
| Cache collision | Key thiếu tenant/permission dimension | Canonical tenant scope trong key, authorization trước cache hit |
| Search leakage | Aggregation/autocomplete thiếu tenant filter | Mandatory tenant filter và test mọi query mode |
| Signed URL leakage | URL bearer bị log/chia sẻ | TTL ngắn, log redaction, scope object/version, audit |
| Support privilege abuse | Operator impersonate rộng, không audit | Just-in-time access, ticket/approval, session recording/audit |
| Noisy neighbor | Một tenant vượt quota | Per-tenant quota, fair scheduling và tier isolation |
| Stale membership | Token claim còn quyền sau revoke | Token ngắn hạn, recheck/invalidation, sensitive action authorization |
| Tenant migration split-brain | Service route tới hai database writer | Versioned placement registry, cutover protocol, fencing |

### Defense in depth

Không có một lớp đơn lẻ đủ để bảo vệ multi-tenancy. Một request an toàn cần:

- Credential xác thực đúng principal.
- Tenant selection được validate.
- Authorization theo action và resource.
- Service-to-service identity/delegation.
- Data query/storage/cache scope.
- Audit và observability.
- Kiểm thử negative path và vận hành revoke/suspension.

Nếu một lớp có lỗi, lớp kế tiếp nên giảm khả năng dữ liệu tenant khác bị lộ.

## 24. Tenant lifecycle: onboarding, suspend, migration và deletion

Tenant context phải hoạt động cùng lifecycle của tenant. Trạng thái tenant có thể ảnh hưởng tất cả request và job.

### Onboarding

1. Tạo canonical tenant ID.
2. Thiết lập domain/slug và trạng thái provisioning.
3. Tạo data placement, schema/bucket/namespace và encryption policy nếu cần.
4. Thiết lập quota/tier, service grants và default roles.
5. Khởi tạo admin membership qua flow xác minh.
6. Kiểm thử isolation và access trước khi active.
7. Ghi audit provisioning và owner vận hành.

### Suspension

Tenant suspension có thể được kích hoạt do thanh toán, bảo mật, pháp lý hoặc yêu cầu vận hành. Cần định nghĩa:

- API mới bị từ chối hay chỉ read-only?
- User session/token còn hiệu lực tới khi nào?
- Queue jobs đang chạy được tiếp tục, dừng hay quarantine?
- Signed URL đã phát hành xử lý thế nào?
- Scheduled jobs, webhook và integration credential bị disable ra sao?
- Support có quyền đọc/export để xử lý yêu cầu không?

Không chỉ dựa vào một field active trong cache dài hạn; status thay đổi phải lan tới enforcement point trong thời gian SLA.

### Migration

Tenant có thể đổi region, database cluster hoặc tier. Dùng state machine với các trạng thái như PREPARING, COPYING, VERIFYING, CUTOVER, ACTIVE_NEW, ROLLBACK. Placement registry có version; service phải biết writer authoritative. Dùng checksum, replication lag, write freeze/fencing và audit.

### Deletion và retention

Xóa tenant cần kiểm tra:

- Legal hold/retention và nghĩa vụ xuất dữ liệu.
- Database, object, cache, search, analytics, queue và backup.
- Replicas ở region khác và dữ liệu do subprocessor lưu.
- Encryption key và khả năng phục hồi trong thời gian hold.
- Audit cần giữ sau khi dữ liệu tenant bị xóa.
- Bằng chứng deletion và phê duyệt.

Không xóa audit chứng minh việc xử lý dữ liệu chỉ vì tenant record đã bị xóa. Lưu metadata còn lại theo đúng mục đích và policy.

## 25. Tenant registry và consistency

Control plane thường lưu mapping tenant tới domain, membership, region, database, tier, quota và trạng thái. Đây là dữ liệu quyết định routing và authorization nên cần độ tin cậy cao.

### Registry read path

Cache registry có thể giảm độ trễ, nhưng stale status có thể cho phép tenant suspended tiếp tục hoạt động hoặc route nhầm database. Cần:

- Versioned record và event invalidation.
- TTL phù hợp với risk/status change SLA.
- Recheck nguồn mạnh cho thao tác nhạy cảm.
- Fail-closed hoặc degraded mode được định nghĩa khi registry unavailable.
- Audit update và optimistic concurrency để tránh ghi đè placement.

### Tenant context snapshot

Context tạo đầu request có thể chứa tenant status/permission snapshot. Nếu request kéo dài, policy có thể thay đổi giữa chừng. Với thao tác dài, cần recheck ở side-effect boundary hoặc có authorization lease ngắn hạn; không nhất thiết query membership cho mỗi dòng dữ liệu, nhưng phải định nghĩa thời điểm kiểm tra.

### Cache invalidation khi revoke

Khi user bị gỡ khỏi tenant:

1. Membership source commit trạng thái revoked/version mới.
2. Phát event invalidation qua outbox.
3. Gateway/service cache nhận và loại quyền cũ.
4. Token/delegation bị revoke hoặc hết hạn theo policy.
5. Request mới bị từ chối; request đang chạy được xử lý theo side-effect boundary.

Nếu hệ thống không thể bảo đảm invalidation tức thời, ghi rõ maximum revocation latency và không dùng cache stale cho thao tác có tác động cao.

## 26. Kiểm thử tenant isolation và context propagation

Test đa tenant phải có dữ liệu và principal riêng ít nhất hai tenant, rồi chứng minh không có đường đọc/ghi chéo. Happy path một tenant không thể phát hiện lỗi thiếu scope.

| Bài thử | Kịch bản | Kỳ vọng |
| --- | --- | --- |
| Header spoofing | User tenant A gửi X-Tenant-ID tenant B | Gateway/service từ chối nếu không có membership/grant |
| Resource IDOR | User A đoán invoice ID tenant B | Không tiết lộ nội dung hoặc metadata nhạy cảm |
| Query missing predicate | Gọi endpoint list/search/report | Kết quả chỉ thuộc tenant context |
| Cache collision | Cùng resource key ở hai tenant có value khác | Không trả cache entry chéo tenant |
| RLS pool reuse | Dùng connection pool xen kẽ request A/B | Context transaction được reset; không rò dữ liệu |
| Async propagation | Submit task A rồi task B trên cùng executor | Context không bị dùng nhầm |
| Queue forged event | Producer không được phép gửi tenant B | Message bị từ chối/quarantine |
| DLQ replay | Replay event của tenant A bằng operator không có grant | Bị chặn và audit |
| Signed URL | User A yêu cầu URL tới object B | Không tạo URL |
| Search aggregation | Count/facet/autocomplete | Chỉ tính dữ liệu tenant được phép |
| Tenant suspended | Gửi API và xử lý queued job | Hành vi theo policy suspension |
| Membership revoke | Revoke user khi token còn hạn | Sensitive action bị từ chối trong SLA |
| Region migration | Chuyển placement khi request đang chạy | Không dual-writer hoặc route sai |
| Support access | Operator mở resource tenant | Có approval, scope và audit đầy đủ |
| Noisy neighbor | Tenant lớn tạo burst | Quota/fairness bảo vệ tenant khác |

### Property-based isolation test

Có thể sinh ngẫu nhiên tenant A/B/C, user membership, resource owner và action. Với mỗi request, invariant:

- Không principal nào đọc resource tenant khác nếu không có explicit cross-tenant grant.
- Mọi write lưu tenant owner lấy từ trusted context.
- Event tạo từ transaction giữ cùng tenant ID và aggregate ID.
- Cache key có đủ scope ảnh hưởng response.
- Query list/count/search đều lọc đúng tenant.
- Tenant suspended không tạo side effect mới ngoài policy cho phép.

Kiểm thử cần xác minh response, database state, cache, event, object storage và audit; chỉ test HTTP status có thể bỏ sót data leakage qua side channel.

### Fuzzing và negative tests

Thử tenant ID malformed, slug alias, case/Unicode, missing header, duplicate header, expired token, audience sai, mismatched claim, delegated token sai audience, tenant suspended, context null và header bị gateway strip. Đặc biệt test mọi cách gọi trực tiếp service ngoài gateway trong môi trường được kiểm soát.

## 27. Bài tập thực hành và đáp án định hướng

Một SaaS có tenant A và tenant B. User Alice là admin tenant A, Bob là member tenant B. Booking service nhận request qua gateway; Invoice service dùng database shared table; report export chạy qua queue; file lưu object storage chung. Alice có thể gửi request với header X-Tenant-ID: tenant-B.

### Câu 1 — Gateway nên xử lý header tenant thế nào?

**Đáp án:** Không tin header từ client. Gateway xác thực Alice, resolve tenant candidate B rồi kiểm tra membership; vì Alice không thuộc B nên từ chối. Nếu tenant được chọn từ token claim đơn, claim phải được verify và audience/expiry hợp lệ.

### Câu 2 — Invoice service cần bảo vệ query ra sao?

**Đáp án:** Tenant context trusted được truyền từ caller đã xác thực. Query bắt buộc tenant_id cùng invoice_id; composite key/foreign key và RLS có thể là lớp phòng vệ bổ sung. Repository không expose method chỉ query theo ID cho dữ liệu tenant-scoped.

### Câu 3 — Worker nhận export job từ queue cần tin tenantId trong envelope không?

**Đáp án:** Không tin đơn thuần. Xác thực producer/topic, schema, job record và tenant status; kiểm tra export grant và resource ownership. Worker dùng workload identity và reauthorize tại side effect boundary. Không lưu access token Alice dài hạn trong message.

### Câu 4 — Cache key cho invoice nên có gì?

**Đáp án:** Canonical tenant ID, invoice ID, schema version và mọi dimension làm thay đổi response/permission. Authorization vẫn phải được kiểm tra trước khi trả cache hit. Không dùng invoice ID một mình nếu cache chung tenant.

### Câu 5 — Signed URL của file invoice cần kiểm soát gì?

**Đáp án:** Server kiểm tra Alice có quyền với invoice của tenant A, lấy bucket/key/version từ metadata trusted, giới hạn method và TTL ngắn, audit URL issuance và không log signature. Client không được tự truyền object key để ký.

### Câu 6 — Tenant A bị suspend khi report worker đang chạy. Điều gì xảy ra?

**Đáp án:** Theo suspension policy: worker kiểm tra trạng thái tenant trước khi tiếp tục xử lý/publish file; có thể dừng hoặc quarantine output. Không chỉ chặn API login mà để queue job tiếp tục xuất dữ liệu.

### Câu 7 — Làm sao support xem invoice tenant B?

**Đáp án:** Cấp just-in-time delegated access có ticket/approval, scope chỉ đọc đúng resource/phạm vi và thời hạn ngắn. Audit operator, tenant, invoice, purpose và kết quả. Không impersonate tùy ý hoặc bypass audit.

### Câu 8 — Làm sao phát hiện context leakage giữa hai request?

**Đáp án:** Chạy concurrent/async test xen kẽ tenant A/B trên cùng thread pool và connection pool; kiểm tra repository, RLS setting, cache, log và event. Context phải immutable/request-scoped và cleanup sau mỗi lần sử dụng.

## 28. Những sai lầm thường gặp

1. **Tin tenant ID do client gửi:** cho phép tenant spoofing.
2. **Coi UUID là authorization:** ID khó đoán không thay thế policy.
3. **Chỉ kiểm tra role mà không kiểm tra resource owner:** user có role hợp lệ nhưng resource có thể thuộc tenant khác.
4. **Gateway xác thực nhưng downstream tin mọi header:** service bị gọi trực tiếp hoặc caller nội bộ bị compromise có thể giả mạo context.
5. **Forward access token không xét audience:** token có thể dùng sai service hoặc chứa quyền quá rộng.
6. **Dùng service account toàn quyền cho mọi tenant:** confused deputy và blast radius lớn.
7. **Serialize cả runtime context vào queue:** mang secret/claim cũ và không có lifecycle/revocation rõ.
8. **ThreadLocal không cleanup:** context tenant cũ rò sang request mới.
9. **Mutable singleton currentTenant:** race condition giữa request đồng thời.
10. **Query chỉ theo resource ID:** IDOR/cross-tenant data leakage.
11. **RLS dựa trên session variable nhưng pool không reset:** connection reuse làm rò scope.
12. **Cache key thiếu tenant/permission:** trả dữ liệu từ cache sang tenant khác.
13. **Object key lấy từ client:** path traversal/prefix confusion và signed URL sai scope.
14. **Search filter chỉ áp cho hits:** count/facet/autocomplete vẫn lộ dữ liệu.
15. **Queue consumer tin event payload:** producer lỗi/compromise có thể ghi tenant tùy ý.
16. **Tenant suspend chỉ chặn login:** worker, webhook, signed URL và scheduled job vẫn hoạt động.
17. **Support impersonation không audit:** khó truy vết truy cập dữ liệu nhạy cảm.
18. **Metric tenant ID vô hạn:** cardinality explosion và chi phí telemetry.
19. **Migration chỉ đổi registry:** cache, queue, search, backup và writer ownership còn dùng mapping cũ.
20. **Tenant delete chỉ xóa database row:** dữ liệu còn lại trong object, cache, index, replicas và backup.

## 29. Quy trình review thiết kế tenant context

Trong buổi architecture review, có thể đi theo hành trình một request thay vì chỉ xem sơ đồ identity:

1. Chọn một request cụ thể và xác định principal gốc.
2. Chỉ ra tenant candidate đến từ đâu và ai xác minh membership.
3. Kiểm tra context được tạo ở đâu, bất biến ra sao và hết hạn khi nào.
4. Theo request qua từng service, queue và worker; xác định mỗi hop xác thực caller/delegation thế nào.
5. Theo dữ liệu tới database, cache, search, object storage và analytics; tìm mọi nơi có thể bỏ mất tenant scope.
6. Xem side effect và retry: context có còn hiệu lực, resource owner có được kiểm tra lại không?
7. Kiểm tra log/trace/audit có ghi actor/tenant mà không lộ token/PII không.
8. Xem lifecycle: suspend, revoke, migration và deletion lan tới các thành phần ra sao.
9. Xem negative tests: giả mạo tenant, gọi service trực tiếp, connection pool reuse, forged queue event.
10. Ghi owner, policy, SLO revocation, RTO xử lý và trigger review lại.

### Một số câu hỏi cần trả lời bằng bằng chứng

| Câu hỏi review | Bằng chứng |
| --- | --- |
| Ai được chọn tenant? | Identity flow, membership policy, tests |
| Ai có thể thay đổi tenant context? | API contract, immutable context type, trust boundary |
| Service downstream tin ai? | mTLS/workload identity, audience, delegation validation |
| Query nào đảm bảo tenant scope? | Repository contract, SQL/RLS tests, query review |
| Cache/search/object/queue giữ scope thế nào? | Key/envelope/schema/policy và negative tests |
| Khi quyền bị thu hồi, mất bao lâu để có hiệu lực? | Revocation SLA, event/cache invalidation metric, test |
| Khi tenant suspend, job đang chạy xử lý sao? | State machine, runbook, worker checks |
| Operator truy cập tenant có được audit? | Approval workflow, immutable audit trail |
| Tenant lớn có ảnh hưởng tenant khác? | Quota, noisy-neighbor dashboard, load test |
| Migration/deletion có bỏ sót bản sao? | Inventory, registry version, reconciliation report |

## 30. Checklist trước production

- Canonical tenant ID được quản lý tập trung, không phụ thuộc slug/domain có thể đổi.
- Tenant resolution xác thực principal, membership, status và service grant.
- Tenant candidate từ client không được coi là trusted context.
- Token kiểm tra signature, issuer, audience, expiry, subject và scope.
- Delegation/service identity có quyền tối thiểu, audience đúng và thời hạn rõ.
- TenantContext là immutable, request/job scoped và được cleanup.
- HTTP, async, queue, workflow và scheduled job truyền context qua contract được xác thực.
- Database query luôn tenant-scoped; RLS/constraint được cấu hình và kiểm thử khi áp dụng.
- Cache key, search filter, object key, signed URL, analytics và DLQ giữ đúng tenant boundary.
- Support/admin cross-tenant access có approval, just-in-time grant và audit.
- Tenant status/revocation lan tới cache, token, worker, webhook và signed URL trong SLA.
- Region/database placement có version, owner và migration/fencing protocol.
- Quota/fairness bảo vệ tenant khác trước noisy neighbor.
- Logs/traces/metrics không lộ token/PII và không tạo cardinality vô hạn.
- Có negative tests cho spoofing, IDOR, context leakage, forged event và pool reuse.
- Runbook xử lý suspension, breach, tenant migration, export và deletion.

## 31. Đánh giá theo Well-Architected

| Trụ cột | Câu hỏi trọng tâm | Bằng chứng |
| --- | --- | --- |
| **Độ tin cậy** | Context có được truyền đúng qua failover, queue retry, async và tenant migration không? | Contract propagation, versioned registry, idempotency, recovery test |
| **Bảo mật** | Tenant identity có được xác minh ở mọi trust boundary và resource scope không? | Identity/delegation, IAM, RLS, negative cross-tenant tests, audit |
| **Hiệu năng** | Membership/registry lookup, query scope và quota có đáp ứng latency khi tải lớn không? | Cache policy, p95/p99, per-tenant load test, connection metrics |
| **Tối ưu chi phí** | Có thể vận hành nhiều tenant bằng shared infrastructure trong khi tách tenant lớn hợp lý không? | Pool utilization, tier cost, noisy-neighbor metrics, placement plan |
| **Vận hành xuất sắc** | Có thể điều tra, revoke, suspend, migrate và delete một tenant có kiểm soát không? | Dashboard, runbook, approval, audit trail, reconciliation |
| **Tính bền vững** | Tài nguyên và dữ liệu tenant có được tạo, giữ, di chuyển và xóa đúng mục đích không? | Lifecycle policy, quota, retention, deletion evidence |

Một thiết kế tenant context tốt đảm bảo cùng một ngữ nghĩa xuyên suốt: **principal nào đang hành động, tenant nào là phạm vi hiệu lực, quyền nào được cấp và resource nào thuộc phạm vi đó**. Khi context được xác minh, truyền an toàn, kiểm tra lại tại ranh giới quan trọng và quan sát được, nền tảng mới có thể chia sẻ hạ tầng mà vẫn giữ được ranh giới tin cậy giữa các khách hàng.
